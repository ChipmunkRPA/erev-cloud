"""CLO-22 the seeded close of the demo world, a stage of ``erev seed demo --with-close``
(docs/02-PRD.md §2.1 WLD-R-02, §2.2 WLD-P-02, WLD-P-04; BUILD_SPEC CLO-22; dev-guide DG-MK-seed;
supervisor ruling of 2026-10-01 on lane F-ADM-WEB's design line, item 12).

WLD-T-01 is seeded once through ``seed_demo`` with the stage, under a stand-in tenant code and the
PRD §2.3 cast at module-unique ``demo.erev`` addresses, as the CTR-20 module seeds it without. The
tests read what the persona commands wrote: AVM-US, book ASC606, January to August 2026 ``closed``,
each month through a succeeded close run, an acknowledged journal, two reviewed reconciliations and
a lock that ``marcus`` decided on ``maya``'s request; every other entity and book as the default
seed leaves it; the open-period items of the background contracts made after the locks.

The clock of a test stands still, so no verification would ever be older than the step-up window
and no persona would be asked to verify again. The fixture therefore lets six minutes pass before
the first review and before the first lock decision, as they pass under the wall clock, and the
stage's own call verifies the persona again.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pyotp
import pytest
from erev_api.adapters.gl.csv import CsvGl
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, identity_session, platform_session, tenant_session
from erev_api.db.tables import (
    app_user,
    approval_decision,
    approval_request,
    audit_event,
    close_run,
    contract,
    contract_hold,
    exception_item,
    journal_batch,
    journal_run,
    judgement_record,
    legal_entity,
    period,
    period_lock,
    period_state,
    posting_ack,
    reconciliation,
    reconciliation_item,
    security_event,
    signoff,
    tenant,
)
from erev_api.domain.close import gates, reconciliations
from erev_api.domain.demo import close_history, closing, personas, seed, sessions, tenants
from erev_api.domain.demo.avenmoor import background
from erev_api.domain.demo.personas import Persona
from erev_api.domain.journals import ports as gl_ports
from erev_api.enums import GlAdapter
from erev_api.files.store import LocalFileStore
from sqlalchemy import and_, func, select
from support.clock import frozen_clock
from support.db import TestDatabase
from support.factories import stamp_test_release

# Seeding Avenmoor and closing eight of its months through close runs takes tens of minutes.
pytestmark = pytest.mark.slow

REQUEST_ID = "tests-clo-22"
AVENMOOR = tenants.CATALOGUE[1]  # WLD-T-01
ENTITY, BOOK = "AVM-US", "ASC606"
CLOSED_MONTHS = [date(2026, month, 1) for month in range(1, 9)]  # WLD-P-02: January to August
SEPTEMBER = date(2026, 9, 1)
STALE = timedelta(minutes=6)  # longer than the step-up window of BR-PLT-06


@dataclass(frozen=True, slots=True)
class World:
    tenant_id: UUID
    code: str
    user_ids: Mapping[str, UUID]  # persona key → app_user id
    cast: tuple[Persona, ...]
    env: tuple[str, str]
    clock: FrozenClock
    root: Path
    asked: tuple[str, ...]  # the persona keys the stage asked to step up, in order


def _read(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _rows(tenant_id: UUID, statement: Any) -> list[dict[str, Any]]:
    with tenant_session(_read(tenant_id), read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _seed(
    code: str,
    *,
    clock: FrozenClock,
    keyring: KeyRing,
    root: Path,
    env: tuple[str, str],
    cast: tuple[Persona, ...],
) -> seed.SeedResult:
    """``erev seed demo --tenants <code> --with-close`` as the command calls it."""
    return seed.seed_demo(
        [code],
        clock,
        keyring=keyring,
        files=LocalFileStore(root / "files"),
        secrets=seed.DemoSecrets(password=env[0], totp_secret=env[1]),
        credentials_path=root / "run" / seed.CREDENTIALS_FILE,
        request_id=REQUEST_ID,
        personas=cast,
        with_close=True,
    )


@pytest.fixture(scope="module")
def csv_ledger() -> Iterator[None]:
    """The composition root's part (DG-LAY-03): ``erev seed demo --with-close`` registers the CSV
    general-ledger adapter before it seeds; here the fixture does."""
    previous = gl_ports.GL_ADAPTERS.get(GlAdapter.CSV)
    gl_ports.register_gl_adapter(GlAdapter.CSV, CsvGl)
    yield
    if previous is None:
        gl_ports.GL_ADAPTERS.pop(GlAdapter.CSV, None)
    else:
        gl_ports.register_gl_adapter(GlAdapter.CSV, previous)


@pytest.fixture(scope="module")
def world(
    test_database: TestDatabase,
    keyring: KeyRing,
    csv_ledger: None,
    tmp_path_factory: pytest.TempPathFactory,
) -> World:
    """A stand-in WLD-T-01 seeded once with its close through ``seed_demo``."""
    stamp_test_release()  # 05 REL-03: the release row a computation names
    root = tmp_path_factory.mktemp("clo-22")
    code = f"avm-{secrets.token_hex(4)}"
    suffix = secrets.token_hex(3)
    cast = tuple(
        replace(persona, email=f"{persona.key}.{suffix}@{personas.DEMO_DOMAIN}")
        for persona in personas.PERSONAS
    )
    env = (f"Seed-{secrets.token_urlsafe(12)}", pyotp.random_base32())
    clock = frozen_clock()
    asked: list[str] = []
    verify_again = sessions.PersonaRun.step_up

    def step_up(run: sessions.PersonaRun, persona: Persona) -> None:
        # Module docstring: time passes before a persona's first step-up, so hers is stale.
        if persona.key not in asked:
            clock.advance(STALE)
        asked.append(persona.key)
        verify_again(run, persona)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tenants, "CATALOGUE", (*tenants.CATALOGUE, replace(AVENMOOR, code=code)))
        patch.setattr(sessions.PersonaRun, "step_up", step_up)
        result = _seed(code, clock=clock, keyring=keyring, root=root, env=env, cast=cast)
    assert result.outcomes == ((code, "seeded"),)
    with platform_session("tenant_directory", actor_user_id=None, request_id=REQUEST_ID) as db:
        tenant_id = db.execute(select(tenant.c.id).where(tenant.c.code == code)).scalar_one()
    emails = {persona.email: persona.key for persona in cast}
    with identity_session(request_id=REQUEST_ID) as db:
        found = db.execute(
            select(app_user.c.email, app_user.c.id).where(app_user.c.email.in_(sorted(emails)))
        ).all()
    return World(
        tenant_id=UUID(str(tenant_id)),
        code=code,
        user_ids={emails[str(email)]: UUID(str(user_id)) for email, user_id in found},
        cast=cast,
        env=env,
        clock=clock,
        root=root,
        asked=tuple(asked),
    )


def _states(world: World) -> list[dict[str, Any]]:
    """Every period state of the tenant with its entity, book and month."""
    return _rows(
        world.tenant_id,
        select(
            period_state.c.id,
            period_state.c.state,
            period_state.c.book_code,
            period_state.c.entity_id,
            period_state.c.period_id,
            legal_entity.c.code,
            period.c.start_date,
            period.c.period_key,
        ).select_from(
            period_state.join(
                period,
                and_(
                    period.c.tenant_id == period_state.c.tenant_id,
                    period.c.id == period_state.c.period_id,
                ),
            ).join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == period_state.c.tenant_id,
                    legal_entity.c.id == period_state.c.entity_id,
                ),
            )
        ),
    )


def _closed(world: World) -> list[dict[str, Any]]:
    """The eight period states the stage closes, in month order."""
    found = sorted(
        (
            row
            for row in _states(world)
            if row["code"] == ENTITY
            and str(row["book_code"]) == BOOK
            and row["start_date"] in CLOSED_MONTHS
        ),
        key=lambda row: row["start_date"],
    )
    assert [row["start_date"] for row in found] == CLOSED_MONTHS
    return found


def test_seeded_period_states(world: World) -> None:
    """WLD-P-02 as the stage builds it: AVM-US ASC606 January to August ``closed``, September
    ``open``, October onward ``future``; each closed month through ONE succeeded close run that
    ``maya`` started and a lock that ``marcus`` decided on her request; every other entity and
    book as the default seed leaves it — January to September ``open``."""
    maya, marcus = world.user_ids["maya"], world.user_ids["marcus"]
    assert tuple(row["period_key"] for row in _closed(world)) == close_history.PERIOD_KEYS
    by_book: dict[tuple[str, str], dict[date, str]] = {}
    for row in _states(world):
        by_book.setdefault((str(row["code"]), str(row["book_code"])), {})[row["start_date"]] = (
            _value(row["state"])
        )
    assert sorted(by_book) == [
        ("AVM-DE", "ASC606"),
        ("AVM-JP", "ASC606"),
        ("AVM-UK", "ASC606"),
        ("AVM-UK", "IFRS15"),
        ("AVM-US", "ASC606"),
        ("AVM-US", "IFRS15"),
    ]
    for scope, months in by_book.items():
        through_september = {day: state for day, state in months.items() if day <= SEPTEMBER}
        later = {state for day, state in months.items() if day > SEPTEMBER}
        assert later == {"future"}, scope
        if scope == (ENTITY, BOOK):
            assert through_september == {
                **dict.fromkeys(CLOSED_MONTHS, "closed"),
                SEPTEMBER: "open",
            }
        else:
            assert set(through_september.values()) == {"open"}, scope
            assert len(through_september) == 9, scope

    for at in _closed(world):
        runs = _rows(
            world.tenant_id,
            select(close_run.c.status, close_run.c.created_by).where(
                close_run.c.entity_id == at["entity_id"],
                close_run.c.book_code == BOOK,
                close_run.c.period_id == at["period_id"],
            ),
        )
        assert [(_value(run["status"]), run["created_by"]) for run in runs] == [
            ("SUCCEEDED", maya)
        ], at["period_key"]
        [lock] = _rows(
            world.tenant_id,
            select(period_lock.c.kind, period_lock.c.approval_request_id).where(
                period_lock.c.entity_id == at["entity_id"],
                period_lock.c.book_code == BOOK,
                period_lock.c.period_id == at["period_id"],
            ),
        )
        assert _value(lock["kind"]) == "LOCK"
        [request] = _rows(
            world.tenant_id,
            select(
                approval_request.c.subject_type,
                approval_request.c.subject_id,
                approval_request.c.status,
                approval_request.c.preparer_id,
            ).where(approval_request.c.id == lock["approval_request_id"]),
        )
        assert (
            _value(request["subject_type"]),
            request["subject_id"],
            _value(request["status"]),
            request["preparer_id"],
        ) == ("PERIOD_LOCK", at["id"], "APPROVED", maya)
        decisions = _rows(
            world.tenant_id,
            select(approval_decision.c.decision, approval_decision.c.approver_id).where(
                approval_decision.c.approval_request_id == lock["approval_request_id"]
            ),
        )
        assert [(_value(d["decision"]), d["approver_id"]) for d in decisions] == [
            ("APPROVE", marcus)
        ]
    # No other period of the world has a close run or a lock.
    [counts] = _rows(
        world.tenant_id,
        select(
            select(func.count()).select_from(close_run).scalar_subquery().label("runs"),
            select(func.count()).select_from(period_lock).scalar_subquery().label("locks"),
        ),
    )
    assert (counts["runs"], counts["locks"]) == (8, 8)


def test_each_closed_month_has_its_acknowledged_journal(world: World) -> None:
    """A batch without a connection is a CSV batch, and the preparer's record of the ledger's
    document reference is what acknowledges it (BR-JE-03): every journal run of a closed month
    is ``acknowledged``, approved by ``priya`` on ``maya``'s submission, each of its batches by a
    ``MANUAL_CONFIRMATION`` that ``maya`` recorded."""
    maya, priya = world.user_ids["maya"], world.user_ids["priya"]
    for at in _closed(world):
        runs = _rows(
            world.tenant_id,
            select(journal_run.c.id, journal_run.c.state, journal_run.c.approval_request_id).where(
                journal_run.c.entity_id == at["entity_id"],
                journal_run.c.book_code == BOOK,
                journal_run.c.period_id == at["period_id"],
            ),
        )
        assert runs, at["period_key"]
        for run in runs:
            assert _value(run["state"]) == "acknowledged", at["period_key"]
            [request] = _rows(
                world.tenant_id,
                select(approval_request.c.status, approval_request.c.preparer_id).where(
                    approval_request.c.id == run["approval_request_id"]
                ),
            )
            assert (_value(request["status"]), request["preparer_id"]) == ("APPROVED", maya)
            approvers = _rows(
                world.tenant_id,
                select(approval_decision.c.approver_id).where(
                    approval_decision.c.approval_request_id == run["approval_request_id"]
                ),
            )
            assert [row["approver_id"] for row in approvers] == [priya]
            batches = _rows(
                world.tenant_id,
                select(
                    journal_batch.c.id,
                    journal_batch.c.state,
                    journal_batch.c.adapter,
                    journal_batch.c.batch_no,
                    journal_batch.c.chunk_no,
                    journal_batch.c.integration_connection_id,
                    journal_batch.c.export_file_id,
                ).where(journal_batch.c.journal_run_id == run["id"]),
            )
            assert batches, at["period_key"]
            for batch in batches:
                assert (
                    _value(batch["state"]),
                    _value(batch["adapter"]),
                    batch["integration_connection_id"],
                ) == ("acknowledged", "CSV", None)
                assert batch["export_file_id"] is not None
                [ack] = _rows(
                    world.tenant_id,
                    select(
                        posting_ack.c.ack_kind,
                        posting_ack.c.gl_document_id,
                        posting_ack.c.gl_posted_date,
                        posting_ack.c.created_by,
                    ).where(posting_ack.c.journal_batch_id == batch["id"]),
                )
                assert (
                    _value(ack["ack_kind"]),
                    ack["gl_document_id"],
                    ack["created_by"],
                ) == (
                    "MANUAL_CONFIRMATION",
                    closing.document_reference(
                        ENTITY, at["period_key"], int(batch["batch_no"]), int(batch["chunk_no"])
                    ),
                    maya,
                )


def test_each_closed_month_has_its_reconciliations(world: World) -> None:
    """Both reconciliations a lock requires, for every closed month: prepared by ``maya``,
    reviewed by ``priya`` and certified by the lock. The subledger-to-GL one holds the uploaded
    trial balance and no variance; every difference of the billing one carries its explanation."""
    maya, priya = world.user_ids["maya"], world.user_ids["priya"]
    for at in _closed(world):
        found = _rows(
            world.tenant_id,
            select(
                reconciliation.c.id,
                reconciliation.c.kind,
                reconciliation.c.status,
                reconciliation.c.variance_count,
                reconciliation.c.source_file_id,
                reconciliation.c.period_lock_id,
            ).where(
                reconciliation.c.entity_id == at["entity_id"],
                reconciliation.c.book_code == BOOK,
                reconciliation.c.period_id == at["period_id"],
            ),
        )
        by_kind = {_value(row["kind"]): row for row in found}
        assert sorted(by_kind) == ["BILLING_TO_SUBLEDGER", "SUBLEDGER_TO_GL"], at["period_key"]
        assert len(found) == 2  # one generation of each kind
        for row in found:
            assert _value(row["status"]) == "CERTIFIED", at["period_key"]
            assert row["period_lock_id"] is not None
            signers = _rows(
                world.tenant_id,
                select(signoff.c.role, signoff.c.signer_id).where(
                    signoff.c.subject_type == reconciliations.OBJECT_TYPE,
                    signoff.c.subject_id == row["id"],
                ),
            )
            assert sorted((_value(s["role"]), s["signer_id"]) for s in signers) == sorted(
                [("PREPARER", maya), ("REVIEWER", priya)]
            )
        ledger = by_kind["SUBLEDGER_TO_GL"]
        assert ledger["source_file_id"] is not None and int(ledger["variance_count"]) == 0
        billing = by_kind["BILLING_TO_SUBLEDGER"]
        items = _rows(
            world.tenant_id,
            select(reconciliation_item.c.difference, reconciliation_item.c.explanation).where(
                reconciliation_item.c.reconciliation_id == billing["id"]
            ),
        )
        differing = [item for item in items if Decimal(item["difference"]) != 0]
        assert len(differing) == int(billing["variance_count"])
        assert {item["explanation"] for item in differing} <= {closing.BILLING_EXPLANATION}


def test_the_open_period_items_follow_the_close(world: World) -> None:
    """WLD-B-01, WLD-B-03 and WLD-B-05 hold every period of AVM-US while they stand, so the stage
    closes first and makes them afterwards (WLD-P-04): they are in the world as the default seed
    has them, and September — the open month — is the period they hold."""
    maya = world.user_ids["maya"]
    ids = {
        str(row["external_id"]): row
        for row in _rows(
            world.tenant_id,
            select(contract.c.id, contract.c.external_id, contract.c.status).where(
                contract.c.external_id.in_(
                    (background.PENDING_ACTIVATION, background.HELD, background.JUDGED)
                )
            ),
        )
    }
    [pending] = _rows(
        world.tenant_id,
        select(approval_request.c.status, approval_request.c.preparer_id).where(
            approval_request.c.subject_type == "CONTRACT_ACTIVATION",
            approval_request.c.subject_id == ids[background.PENDING_ACTIVATION]["id"],
        ),
    )
    assert (_value(pending["status"]), pending["preparer_id"]) == ("PENDING", maya)
    assert _value(ids[background.PENDING_ACTIVATION]["status"]) == "DRAFT"
    [held] = _rows(
        world.tenant_id,
        select(contract_hold.c.reason, contract_hold.c.released_at).where(
            contract_hold.c.contract_id == ids[background.HELD]["id"]
        ),
    )
    assert (held["reason"], held["released_at"]) == (background.HOLD_REASON, None)
    [judged] = _rows(
        world.tenant_id,
        select(judgement_record.c.status, judgement_record.c.created_by).where(
            judgement_record.c.contract_id == ids[background.JUDGED]["id"],
            judgement_record.c.topic == "PRINCIPAL_AGENT",
        ),
    )
    assert (_value(judged["status"]), judged["created_by"]) == ("SUBMITTED", maya)
    # REQ-POL-010: the unreviewed judgement record holds its contract, a second open hold.
    [system_hold] = _rows(
        world.tenant_id,
        select(contract_hold.c.hold_source, contract_hold.c.released_at).where(
            contract_hold.c.contract_id == ids[background.JUDGED]["id"]
        ),
    )
    assert (_value(system_hold["hold_source"]), system_hold["released_at"]) == ("SYSTEM", None)
    # WLD-B-04, the imports builder's two items, after the stage as before it.
    over_delivery = _rows(
        world.tenant_id,
        select(exception_item.c.status).where(exception_item.c.code == "PROGRESS_OVER_DELIVERY"),
    )
    assert [_value(item["status"]) for item in over_delivery] == ["OPEN", "OPEN"]

    # September counts them: the hold of WLD-B-05 and the one of the unreviewed record; the
    # activation of WLD-B-01 and the review of WLD-B-03 (WLD-B-02 is not seeded); WLD-B-04's two.
    blockers = _september_blockers(world)
    assert (blockers["holds_open"], blockers["judgements_unreviewed"]) == (2, 1)
    assert (blockers["approvals_pending"], blockers["exceptions_open"]) == (2, 2)


def _september_blockers(world: World) -> dict[str, int]:
    """The blocker counts of AVM-US ASC606 September 2026, the month the stage leaves open."""
    [september] = [
        row
        for row in _states(world)
        if row["code"] == ENTITY
        and str(row["book_code"]) == BOOK
        and row["start_date"] == SEPTEMBER
    ]
    with tenant_session(_read(world.tenant_id), read_only=True) as session:
        scope = gates.period_scope(session, september["id"])
        assert scope is not None
        return gates.blocker_counts(session, scope)


def _step_ups(world: World) -> dict[UUID, int]:
    """How often each persona passed the MFA challenge as a step-up (``security_event``)."""
    with identity_session(request_id=REQUEST_ID) as db:
        passed = db.execute(
            select(security_event.c.user_id, security_event.c.detail).where(
                security_event.c.kind == "MFA_CHALLENGE_PASSED",
                security_event.c.user_id.in_(list(world.user_ids.values())),
            )
        ).all()
    found: dict[UUID, int] = {}
    for user_id, detail in passed:
        if dict(detail or {}).get("step_up") is True:
            found[UUID(str(user_id))] = found.get(UUID(str(user_id)), 0) + 1
    return found


def test_a_stale_step_up_is_verified_again_before_a_review_and_a_lock_decision(
    world: World,
) -> None:
    """BR-PLT-06: the review of a reconciliation and the lock decision ask for a verification at
    most five minutes old. The stage asks the reviewer before each of the sixteen reviews and the
    controller before each of the eight decisions; a stale verification is renewed by the step-up
    command, a fresh one is left alone — ``maya``, who prepares, is never asked."""
    assert sorted(set(world.asked)) == ["marcus", "priya"]
    assert world.asked.count("priya") == 16 and world.asked.count("marcus") == 8
    # priya: stale before her first review, and again after the six minutes that pass before the
    # first lock decision; marcus: stale before his first decision. Nobody else, and no more.
    assert _step_ups(world) == {world.user_ids["priya"]: 2, world.user_ids["marcus"]: 1}


def test_seed_deterministic_and_idempotent(world: World, keyring: KeyRing) -> None:
    """``demo_seed.complete`` names what the stage closed, and a second run with the stage skips
    the tenant and leaves the close runs, locks, journals and reconciliations as they are."""
    [complete] = _rows(
        world.tenant_id,
        select(audit_event.c.after).where(audit_event.c.action == seed.COMPLETE_ACTION),
    )
    assert (
        complete["after"][seed.CLOSE_MEMBER]
        == close_history.closed_scopes()
        == [
            {
                "entity_code": ENTITY,
                "book": BOOK,
                "from_period_key": "FY2026-P01",
                "to_period_key": "FY2026-P08",
            }
        ]
    )

    def counts() -> dict[str, int]:
        with tenant_session(_read(world.tenant_id), read_only=True) as session:
            return {
                table.name: int(
                    session.execute(select(func.count()).select_from(table)).scalar_one()
                )
                for table in (close_run, period_lock, journal_run, journal_batch, reconciliation)
            }

    before = counts()
    assert (before["close_run"], before["period_lock"], before["reconciliation"]) == (8, 8, 16)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            tenants, "CATALOGUE", (*tenants.CATALOGUE, replace(AVENMOOR, code=world.code))
        )
        again = _seed(
            world.code,
            clock=world.clock,
            keyring=keyring,
            root=world.root,
            env=world.env,
            cast=world.cast,
        )
    assert again.outcomes == ((world.code, "skipped"),)
    assert counts() == before
