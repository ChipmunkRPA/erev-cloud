"""D-98 candidate 143 GUARD-TRN-1 (dev-guide 1.62 DG-KRN-DB-09; 04 §1.5 IM-S; revisions 0068 /
0069): for every DB-03 spec with an editable status, a DIRECT UPDATE of a DRAFT row to a status
that is not one of its listed pairs is refused by name at the database layer (``EREV-TRN-001``),
while a listed pair from DRAFT is accepted — the trigger enforces the state machine in every
status; ``editable_while`` relaxes only the column freeze.

DB-bound: written for the lane database and recorded NOT RUN in the CTR-17 slice (the lane
database is Ray-side). The rows come from ``support.rows.ROW_BUILDERS`` (the RLS isolation
fixtures), forced to ``DRAFT`` before the probe; each probe runs in a savepoint.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db import tables
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.transitions import TRANSITIONS, transition_trigger_sql
from sqlalchemy import exc, insert, text, update
from sqlalchemy.engine import CursorResult
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import ROW_BUILDERS, RowContext, insert_app_user

pytestmark = pytest.mark.pg

EDITABLE = sorted(name for name, spec in TRANSITIONS.items() if spec.editable_while)


def _targets(table: str) -> tuple[str, str]:
    """(a listed target from DRAFT, a status the spec never reaches from DRAFT)."""
    spec = TRANSITIONS[table]
    from_draft = {target for source, target in spec.pairs if source == "DRAFT"}
    listed = sorted(from_draft)[0]
    unreachable = sorted({target for _, target in spec.pairs} - from_draft - {"DRAFT"})[0]
    return listed, unreachable


def _error(excinfo: pytest.ExceptionInfo[exc.DBAPIError]) -> tuple[str, str]:
    """(SQLSTATE, the server's primary message) as the committed PG helpers read them
    (``tests/pg/test_db_invariants.py::_error``; D-98 140-A10 GUARD W1)."""
    origin = excinfo.value.orig
    diag = getattr(origin, "diag", None)
    return str(getattr(origin, "sqlstate", "") or ""), str(
        getattr(diag, "message_primary", "") or ""
    )


# D-98 candidate 143 AMENDMENT 1 (measured on the lane database, fail-first 2026-09-21): a DIRECT
# UPDATE of ``erev.contract``'s status is refused first by DB-18 (``tg_contract__projection``,
# ``EREV-CON-001`` — the header changes only with an appended event), so the pair guard of
# ``contract`` is reachable only through the event projection (``events/stream.append_events``);
# its behaviour is witnessed on that path in ``tests/domain/contracts/test_activation.py``
# (``test_activation_pair_1_…``); the direct-UPDATE probe below covers the other six specs.
DIRECT_UPDATE_PROBED = [name for name in EDITABLE if name != "contract"]


@pytest.mark.parametrize("table_name", DIRECT_UPDATE_PROBED)
def test_guard_trn_1_draft_row_moves_only_along_a_listed_pair(
    table_name: str, committed_db: TestDatabase, keyring: KeyRing
) -> None:
    assert table_name in ROW_BUILDERS, table_name  # every editable spec has a row fixture
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    table = tables.metadata.tables[f"erev.{table_name}"]
    listed, unreachable = _targets(table_name)
    with tenant_session(context) as session:
        user_id = insert_app_user(session)
        row = dict(ROW_BUILDERS[table_name](RowContext(tenant_id, user_id), session))
        row["status"] = "DRAFT"
        session.execute(insert(table).values(**row))
        own = table.c.id == row["id"]
        # 1. a status the pairs never reach from DRAFT is refused by name — the very UPDATE the
        #    previous renderer let through on a DRAFT row
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as refused:
            session.execute(update(table).where(own).values(status=unreachable))
        savepoint.rollback()
        sqlstate, message = _error(refused)
        assert sqlstate == "P0001", (table_name, sqlstate)
        assert "EREV-TRN-001" in message and "cannot change from DRAFT to" in message, message
        # 2. a listed pair from DRAFT is accepted (the editable row may also change its columns)
        moved = session.execute(update(table).where(own).values(status=listed))
        assert cast(CursorResult[Any], moved).rowcount == 1, (table_name, listed)
        session.rollback()


def test_activation_pair_1_contract_direct_update_is_refused_by_db_18_before_the_pair_guard(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    """The ordering the fail-first run measured: a direct status UPDATE of a DRAFT ``contract`` row
    (even to a listed target) is refused by DB-18 ``EREV-CON-001`` — the header changes only with
    an appended event — before ``tg_contract__transition`` can judge the pair; so the (DRAFT,
    ACTIVE) behaviour is witnessed through the projection path in the activation module."""
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    table = tables.contract
    with tenant_session(context) as session:
        user_id = insert_app_user(session)
        row = dict(ROW_BUILDERS["contract"](RowContext(tenant_id, user_id), session))
        row["status"] = "DRAFT"
        session.execute(insert(table).values(**row))
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as refused:
            session.execute(update(table).where(table.c.id == row["id"]).values(status="ACTIVE"))
        savepoint.rollback()
        sqlstate, message = _error(refused)
        assert sqlstate == "P0001" and message.startswith("EREV-CON-001"), (sqlstate, message)
        session.rollback()


def test_activation_pair_1_the_installed_contract_function_lists_the_stored_activation_pair(
    committed_db: TestDatabase,
) -> None:
    """D-98 candidate 143 AMENDMENT 1: the INSTALLED ``tg_contract__transition`` (revision 0070)
    lists the pair ``DRAFT>ACTIVE`` — the stored move of the approved SM-02 / SYSTEM activation —
    and equals the fresh rendering (DG-ARC-07). Fail-first: on 0069 the installed source lacked the
    pair and every approved activation raised EREV-TRN-001 (main 0959b560)."""
    with committed_db.owner_engine.connect() as connection:
        source = connection.execute(
            text(
                "SELECT p.prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'erev' AND p.proname = 'tg_contract__transition'"
            )
        ).scalar_one()
    assert "'DRAFT>ACTIVE'" in source
    assert source == transition_trigger_sql("contract")


def test_activation_pair_1_downgrade_to_0069_restores_the_previous_body_byte_exactly(
    committed_db: TestDatabase,
) -> None:
    """D-98 candidate 143 AMENDMENT 1 (Codex 0147 §2): the 0070 downgrade restores 0069's
    ``tg_contract__transition`` body LITERALLY — the installed source after ``downgrade 0069``
    equals 0069's ``BODIES["contract"]`` byte for byte (and 0070's ``PREVIOUS``), and
    ``upgrade head`` installs 0070's ``BODY`` again (DG-MIG-04; DG-ARC-07). The database is left
    at head.

    The walk descends from a data-free head (``fresh_head``; FLMG-WALK-RESET-1): it passes every
    later revision's downgrade first, and a row that carries an enum label a later revision added
    makes that revision refuse (DG-MIG-06, by design) — since revision 0092 any MFA enrolment of
    an earlier test leaves such a row in ``security_event``."""
    import importlib.util
    from pathlib import Path

    from alembic import command
    from support.db import alembic_config, fresh_head

    versions = Path(__file__).resolve().parents[3] / "backend/erev_api/db/migrations/versions"

    def load(stem: str) -> Any:
        spec = importlib.util.spec_from_file_location(stem, versions / f"{stem}.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def installed() -> str:
        with committed_db.owner_engine.connect() as connection:
            return str(
                connection.execute(
                    text(
                        "SELECT p.prosrc FROM pg_proc p "
                        "JOIN pg_namespace n ON n.oid = p.pronamespace "
                        "WHERE n.nspname = 'erev' AND p.proname = 'tg_contract__transition'"
                    )
                ).scalar_one()
            )

    previous = load("0069_transition_pair_guard_rerender").BODIES["contract"]
    current = load("0070_contract_activation_pair")
    assert current.PREVIOUS == previous  # the literal the downgrade restores
    fresh_head()
    committed_db.app_engine.dispose()
    committed_db.owner_engine.dispose()
    assert installed() == current.BODY
    command.downgrade(alembic_config(), "0069")
    try:
        assert installed() == previous  # byte-exact
        assert "'DRAFT>ACTIVE'" not in installed()
    finally:
        command.upgrade(alembic_config(), "head")
    assert installed() == current.BODY
