"""05 SBX-11 isolation proof (BUILD_SPEC SNP-2; lane F-SNP): a sandbox session appending a stream
event with the SOURCE tenant's id fails by RLS.

The COPY PHASE of a sandbox load runs under the provisioning platform scope (05 SBX-04 rev 1.30;
04 §14.3 rev 1.85), so the same proof is given for a copy-phase transaction — the ruling's DB
witness, compensating control 2: the scope lifts five guards and none of them is row-level
security. ``sandboxes.copy_transaction`` is driven directly, as the loader drives it; the CPU
guards of controls 1 and 4 are in ``tests/unit/test_sandbox_copy_phase.py``.
"""

from __future__ import annotations

import secrets
from contextlib import AbstractContextManager
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import contract_event, security_event, sod_rule, tenant
from erev_api.domain.platform import sandboxes as sb
from erev_api.enums import ConfigStatus
from erev_api.problems import Problem
from sqlalchemy import exc, func, insert, select, update
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import (
    contract_event_values,
    insert_app_user,
    insert_contract_rows,
    insert_sandbox_tenant,
    sod_rule_values,
)

pytestmark = pytest.mark.pg

INSUFFICIENT_PRIVILEGE = "42501"  # row-level security WITH CHECK, and a missing column grant


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def test_sandbox_session_cannot_write_source(committed_db: TestDatabase, keyring: KeyRing) -> None:
    """A session under the sandbox tenant context inserting a ``contract_event`` that names the
    source tenant fails by row-level security (RLS-T WITH CHECK); nothing reaches the source."""
    source = tenant_id_of(tenant_factory(keyring=keyring))
    sandbox = insert_sandbox_tenant(keyring)
    with tenant_session(_context(source)) as session:
        rows = insert_contract_rows(session, source, head_stream_version=1)
    with tenant_session(_context(sandbox)) as session:
        with pytest.raises(exc.DBAPIError) as info:
            session.execute(
                insert(contract_event).values(
                    **contract_event_values(
                        source,  # the SOURCE tenant's id from a sandbox session
                        contract_id=rows.contract_id,
                        contracting_entity_id=rows.entity_id,
                        stream_version=1,
                    )
                )
            )
        assert getattr(info.value.orig, "sqlstate", None) == "42501"  # RLS refusal


def _requester() -> UUID:
    with identity_session(request_id="tests-copy-phase-requester") as session:
        return insert_app_user(session)


def _published_rule(tenant_id: UUID) -> dict[str, object]:
    """A PUBLISHED ``sod_rule`` version as a snapshot carries it: the row the batch-#8 copy died
    on (the DB-04 insert guard admits a non-DRAFT version only under the provisioning scope)."""
    return sod_rule_values(
        tenant_id, code=f"copy-{secrets.token_hex(4)}", status=ConfigStatus.PUBLISHED
    )


def _copy(
    sandbox: UUID, requester: UUID, keyring: KeyRing, request_id: str
) -> AbstractContextManager[Session]:
    return sb.copy_transaction(
        sandbox_tenant_id=sandbox,
        requested_by=requester,
        request_id=request_id,
        keyring=keyring,
        step="the copy of sod_rule",
    )


def _scope_events(request_id: str) -> list[tuple[object, ...]]:
    with identity_session(request_id="tests-copy-phase-events") as session:
        return [
            tuple(row)
            for row in session.execute(
                select(
                    security_event.c.kind,
                    security_event.c.tenant_id,
                    security_event.c.user_id,
                    security_event.c.detail,
                ).where(security_event.c.request_id == request_id)
            )
        ]


def _rules(tenant_id: UUID) -> int:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return int(session.execute(select(func.count()).select_from(sod_rule)).scalar_one())


def test_copy_phase_transaction_cannot_touch_another_tenant(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    """05 SBX-04 rev 1.30, compensating control 2: a copy-phase transaction — the provisioning
    platform scope with the sandbox tenant context — writes the sandbox's copied rows in their
    exported status (the DB-04 insert guard yields), and row-level security still isolates it:
    it cannot insert a row naming the source tenant, cannot see the source's rows and cannot
    update them. Control 1: an INSERT into ``tenant`` — the capability the scope retains — never
    leaves the session. Control 3: the committed transaction recorded ONE ``PLATFORM_SCOPE_USED``
    event naming the sandbox tenant and the requester."""
    source = tenant_id_of(tenant_factory(keyring=keyring))
    sandbox = insert_sandbox_tenant(keyring)
    requester = _requester()
    request_id = f"tests-copy-phase-{secrets.token_hex(4)}"
    source_rules = _rules(source)
    assert source_rules == 7  # the provisioning seed (04 §14.3)
    own = _published_rule(sandbox)
    with _copy(sandbox, requester, keyring, request_id) as session:
        session.execute(insert(sod_rule).values(**own))  # admitted: the scope's purpose
        with pytest.raises(exc.DBAPIError) as refused:
            with session.begin_nested():
                session.execute(insert(sod_rule).values(**_published_rule(source)))
        assert getattr(refused.value.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE
        # the source's rows are invisible, so nothing of the source can be read or changed
        assert session.execute(select(func.count()).select_from(sod_rule)).scalar_one() == 1
        visible = session.execute(
            select(func.count()).select_from(sod_rule).where(sod_rule.c.tenant_id == source)
        ).scalar_one()
        assert visible == 0
        changed = session.execute(
            update(sod_rule).where(sod_rule.c.tenant_id == source).values(rationale="taken over")
        )
        assert changed.rowcount == 0
        with pytest.raises(RuntimeError, match="copied LOAD_ORDER tables only, not 'tenant'"):
            session.execute(insert(tenant).values(id=source, code="never-written"))
    assert _rules(source) == source_rules and _rules(sandbox) == 1
    with tenant_session(_context(source), read_only=True) as session:
        rationales = set(session.execute(select(sod_rule.c.rationale)).scalars())
    assert "taken over" not in rationales
    assert _scope_events(request_id) == [
        ("PLATFORM_SCOPE_USED", sandbox, requester, {"scope": "provisioning"})
    ]


def test_copy_phase_names_a_guards_refusal_and_keeps_every_other_guard(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    """Control 4 and the limits of the scope: outside it the copied PUBLISHED version is refused by
    DB-04 (the batch-#8 return itself), so the scope is what admits it; inside it DB-04 still
    freezes the version against an UPDATE — that refusal (SQLSTATE P0001, ``EREV-CFG-002``) leaves
    the copy phase as the named ``SNAPSHOT_NOT_LOADABLE`` with the guard's first line, the
    transaction rolled back and no ``PLATFORM_SCOPE_USED`` event left behind. An error that is not
    a guard's refusal (a row of another tenant, 42501) propagates untouched."""
    source = tenant_id_of(tenant_factory(keyring=keyring))
    sandbox = insert_sandbox_tenant(keyring)
    requester = _requester()
    row = _published_rule(sandbox)
    with pytest.raises(exc.DBAPIError) as outside:
        with tenant_session(_context(sandbox)) as session:
            session.execute(insert(sod_rule).values(**row))
    assert getattr(outside.value.orig, "sqlstate", None) == "P0001"
    assert str(outside.value.orig).startswith(
        "EREV-CFG-002: a version of erev.sod_rule is inserted as DRAFT, not PUBLISHED"
    )

    request_id = f"tests-copy-phase-{secrets.token_hex(4)}"
    with pytest.raises(Problem) as named:
        with _copy(sandbox, requester, keyring, request_id) as session:
            session.execute(insert(sod_rule).values(**row))
            session.execute(
                update(sod_rule).where(sod_rule.c.id == row["id"]).values(name="Renamed")
            )
    problem = named.value
    assert (problem.slug, problem.status) == ("precondition-failed", 412)
    assert problem.detail == (
        "EREV-CFG-002: columns name of erev.sod_rule cannot change in status PUBLISHED"
    )
    assert [error.rule_id for error in problem.errors] == [sb.RULE_NOT_LOADABLE]
    assert problem.errors[0].message == (
        f"the copy of sod_rule was refused by a database guard: {problem.detail}"
    )
    assert isinstance(problem.__cause__, exc.DBAPIError)
    assert _rules(sandbox) == 0  # rolled back with the refused statement
    assert _scope_events(request_id) == []  # the event is part of the transaction it describes

    request_id = f"tests-copy-phase-{secrets.token_hex(4)}"
    with pytest.raises(exc.DBAPIError) as defect:
        with _copy(sandbox, requester, keyring, request_id) as session:
            session.execute(insert(sod_rule).values(**_published_rule(source)))
    assert getattr(defect.value.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE
    assert _rules(sandbox) == 0 and _scope_events(request_id) == []
