"""CLO-6 lock with certification, lock snapshots and permanent lock (BUILD_SPEC CLO-6 acceptance;
REQ-CLS-009, -010, -020; SM-07 ``closing → closed``, ``closed → permanently_locked``; BR-CLS-01 to
-03; BR-PLT-06; ERR-14; T-CLS-04, T-CLS-05; rulings Q-3, Q-6, Q-10, D-98 61, D-98 63 of the F-CLO
record).

DB-bound (``CloseWorld`` plus Controller personas of the same tenant). NOT RUN on the authoring
worktree (databases not provisioned); measured by the integrated batch on merged main. Two facts
about this tree bound what these scenarios can show (F-CLO record §20):

- ``JE_COMPLETE`` reads the real CLO-10 signal (``completeness.assert_completeness``): the
  acknowledged, balanced run of ``_pass_gates`` carries its ``journal_run.calculate`` audit
  (``record_run_calculation``; without it the run is unverifiable under R5-ORDER-1 and the gate
  FAILED — batch #8) and covers a period without sealed activity, so the gate is PASSED 0 and the
  lock-executing scenarios run the finished path. Until CLO-10 the gate failed
  "not evaluated" by construction (batch #4 / #5 on main); the retired
  ``test_request_lock_blocked_only_by_je_complete_until_clo_10`` became
  ``test_request_lock_passes_je_complete_with_the_real_signal``.
- The producers other lanes own (P4 ``record_execution``, F-RPS ``SNAPSHOT_DATASETS``, the EDS-6
  engine) are resolved by name at the decision and refuse when absent (``ProducerMissing``); that
  refusal is the unit contract ``tests/unit/close/test_dependencies.py``, not these tests.

Codex CLO6-R3 (1) to (9) corrections are noted at each scenario.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from zipfile import ZipFile
from zoneinfo import ZoneInfo

import pytest
from erev_api.approvals.engine import ROLE_REQUIRED_DETAIL
from erev_api.audit import verify as audit_verify
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    approval_step,
    audit_event,
    close_checklist_item,
    close_checklist_template,
    contract,
    contract_event,
    contract_hold,
    control_execution,
    evidence_pack,
    exception_item,
    file_object,
    integration_connection,
    judgement_record,
    ledger_chain_head,
    lock_snapshot,
    period_lock,
    period_state,
    period_state_transition,
    reconciliation,
    role,
    role_permission,
    sync_run,
)
from erev_api.db.transitions import apply
from erev_api.domain.close import commands as close_commands
from erev_api.domain.close import dependencies as close_dependencies
from erev_api.domain.close import gates, queries
from erev_api.domain.reports import (
    evidence_archive,
    evidence_assembly,
    evidence_certification,
    evidence_readiness,
    evidence_reconciliation_population,
    evidence_selection,
    evidence_sources,
    evidence_storage,
)
from erev_api.enums import (
    ApprovalRequestStatus,
    BookCode,
    ChecklistStatus,
    FilePurpose,
    JobKind,
    LockKind,
    PeriodState,
    RegistryCategory,
    SnapshotKind,
)
from erev_api.events.payloads import HoldReleasedV1
from erev_api.files.store import LocalFileStore, open_file
from erev_api.main import create_app
from erev_api.problems import Problem
from erev_api.registry.resolve import resolve as resolve_setting
from erev_api.schemas.evidence_packs import ClosePackCreateIn
from erev_api.schemas.periods import PeriodLockRequestIn, PeriodPermanentLockRequestIn
from erev_engine.canonical import sha256_hex
from fastapi import FastAPI
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from support.close_world import (
    BOOK,
    JOURNAL_RUN_ID_HEADER,
    JOURNAL_RUNS,
    CloseWorld,
    acknowledge_run,
    acknowledged_run,
    close_run_succeeded,
    close_run_succeeded_for,
    close_world,
    contract_of,
    earlier_periods_closed,
    identity_duplicates,
    other_entity,
    periods_closed_before,
    reviewed_error_judgement,
    reviewed_reconciliations,
    reviewed_reconciliations_for,
    run_journal_job,
    submitted_judgement,
    system_session,
    wld_b,
)
from support.db import TestDatabase
from support.factories import Workspace
from support.principals import Actor, carrying, colleague, enrolled, sign_in, step_up
from support.principals import workspace as signed_actor
from support.reference import (
    APPROVALS,
    PERIODS,
    approve,
    assign,
    get,
    holding,
    periods,
    post,
    slug,
)
from support.rows import (
    contract_event_values,
    contract_hold_values,
    evidence_pack_values,
    exception_item_values,
    integration_connection_values,
    publish_registry_version,
)

COMMENT = "September 2026 close complete"
PERMANENT_COMMENT = "Audit complete; freeze September 2026"
NEW_YORK = ZoneInfo("America/New_York")
TWELVE_KINDS = tuple(kind.value for kind in SnapshotKind)  # E-64, T-CLS-05
RECORDER_FAILURE = "CTL-016 recorder failed after every lock write (test double)"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> CloseWorld:
    return close_world(app, keyring, clock, files)


# --- personas and world state ------------------------------------------------------------------


def _controller(app: FastAPI, clock: FrozenClock, tenant_id: UUID, *, name: str = "cora") -> Actor:
    """An enrolled Controller of the world's tenant with a fresh TOTP (BR-PLT-06). ``member`` would
    provision another tenant (record §20.1 (10)); ``colleague`` joins this one. The confirmed
    enrolment is that fresh verification (``mfa.confirm`` rotates the session with
    ``mfa_verified_at = now``): a second code at the same frozen TOTP step is a spent code, refused
    by design (T-PLT-04 ``last_used_step``; ``close_world.actor_with_role`` since abf100d7)."""
    return enrolled(app, clock, _assigned_controller(tenant_id, name))


def _assigned_controller(tenant_id: UUID, name: str) -> Any:
    someone = colleague(tenant_id, name)
    assign(someone, "controller")
    return someone


def _value(stored: Any) -> str:
    return str(getattr(stored, "value", stored))


def _state(world: CloseWorld, key: str = "FY2026-P09") -> dict[str, Any]:
    (found,) = [
        item
        for item in periods(world.app, world.maya, entity="AVM-US")
        if item["period"]["period_key"] == key
    ]
    return found


def _start_close(world: CloseWorld, key: str = "FY2026-P09") -> dict[str, Any]:
    """Soft-close the period on its way to the lock. The earlier periods of AVM-US are closed
    first (PRD WLD-P-02: January to August 2026 ``closed``; BR-CLS-08, supervisor ruling R-6: a
    period is submitted for lock only when no earlier period is postable)."""
    earlier_periods_closed(world, before=key)
    shown = _state(world, key)
    started = post(
        world.app,
        f"{PERIODS}/{shown['id']}/start-close",
        world.maya,
        {"comment": f"{key} close in progress"},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    return shown


def _pass_gates(world: CloseWorld, period_id: UUID | None = None) -> None:
    """Every automatic gate green, ``JE_COMPLETE`` included: an acknowledged, balanced run of the
    period carrying the ``journal_run.calculate`` audit ``acknowledged_run`` records (R5-ORDER-1: a
    run without it is unverifiable, covers nothing and the gate FAILED "held detail unverifiable" —
    integrated batch #8 on main 0091cc21, F-CLO record §25.25); the run covers a period without
    sealed activity, so completeness is PASSED 0; the two required reconciliations reviewed
    (BR-CLS-01); and the period's close run succeeded — a row, fixture state for the gate
    ``CLOSE_RUN_COMPLETED`` (supervisor ruling R-114 (b))."""
    acknowledged_run(world, period_id)
    with system_session(world) as session:
        reviewed_reconciliations(session, world, period_id)
        close_run_succeeded(session, world, period_id)


def _clear_blockers(world: CloseWorld) -> None:
    """Clear the WLD-B blockers in place so the automatic gates pass (CLO6-R3 (1), (5)): the
    requests VOIDED, the items DISMISSED, the hold released — ``released_at`` set, which is what
    HOLDS_REVIEWED reads — and the judgement REVIEWED."""
    now = world.place.clock.now()
    with system_session(world) as session:
        session.execute(
            update(approval_request)
            .where(approval_request.c.status == ApprovalRequestStatus.PENDING.value)
            .values(
                status=ApprovalRequestStatus.VOIDED.value,
                void_reason="WITHDRAWN_BY_PREPARER",  # ck_approval_request__void_reason (0013)
                voided_at=now,
            )
        )
        session.execute(
            update(exception_item)
            .where(exception_item.c.status == "OPEN")
            .values(status="DISMISSED", resolved_at=now)
        )
        # ck_contract_hold__release: (released_event_id IS NULL) = (released_at IS NULL) — a
        # release is an appended HOLD_RELEASED event of the held contract (T-CON-05 is append-only),
        # named by the hold (batch #4 on main c9110467).
        open_holds = session.execute(
            select(
                contract_hold.c.id,
                contract_hold.c.contract_id,
                contract.c.contracting_entity_id,
                contract.c.head_stream_version,
            )
            .select_from(contract_hold.join(contract, contract.c.id == contract_hold.c.contract_id))
            .where(contract_hold.c.released_at.is_(None))
        ).all()
        heads: dict[UUID, int] = {}
        for hold in open_holds:
            # DB-08 (0038 tg_contract_event__insert, EREV-EVT-001): an event's stream_version is
            # never above the contract head — events.stream.append_events advances the head first
            # (DB-18 admits the head rising), then inserts the event (Codex 0829 R2). The head
            # evolves per contract, so two holds on one contract get consecutive versions.
            contract_id = UUID(str(hold.contract_id))
            next_version = heads.get(contract_id, int(hold.head_stream_version)) + 1
            heads[contract_id] = next_version
            session.execute(
                update(contract)
                .where(contract.c.id == contract_id)
                .values(head_stream_version=next_version)
            )
            # 04 §16.3 `HOLD_RELEASED`: `hold_id` (R) and `comment` (R) — the event identifies the
            # hold it releases and carries the canonical hash of that payload (Codex 0845 §3).
            payload = HoldReleasedV1(
                hold_id=UUID(str(hold.id)), comment="Released for the CTL-016 lock probe"
            ).model_dump(mode="json")
            release = contract_event_values(
                world.tenant_id,
                contract_id=contract_id,
                contracting_entity_id=hold.contracting_entity_id,
                stream_version=next_version,
                event_type="HOLD_RELEASED",
                effective_date=now.date(),
                payload=payload,
                payload_sha256=sha256_hex(payload),
            )
            session.execute(insert(contract_event).values(**release))
            session.execute(
                update(contract_hold)
                .where(contract_hold.c.id == hold.id)
                .values(released_at=now, released_event_id=release["id"])
            )
        session.execute(
            update(judgement_record)
            .where(judgement_record.c.status == "SUBMITTED")
            .values(status="REVIEWED", reviewed_at=now)
        )


def _request_lock(
    world: CloseWorld, state_id: UUID | None = None, comment: str = COMMENT
) -> tuple[UUID, list[Any]]:
    with world.place.uow() as uow:
        out = close_commands.request_lock(
            uow,
            state_id=world.state_id if state_id is None else state_id,
            body=PeriodLockRequestIn(certification_comment=comment),
            check_version=lambda actual: None,
        )
        uow.commit()
    return out.approval_request_id, out.gate_results


def _submit_for_lock(world: CloseWorld, submitter: Actor) -> UUID:
    """``POST /periods/{id}/request-lock`` as ``submitter`` (``period.close``; ACT-26): the
    ``PERIOD_LOCK`` request's preparer is the submitter, whose own decision is BR-CLS-02's case."""
    shown = _state(world)
    requested = post(
        world.app,
        f"{PERIODS}/{shown['id']}/request-lock",
        submitter,
        {"certification_comment": COMMENT},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert requested.status_code == 200, requested.text
    return UUID(str(requested.json()["approval_request_id"]))


def _refused_lock(world: CloseWorld) -> Problem:
    with pytest.raises(Problem) as caught, world.place.uow() as uow:
        close_commands.request_lock(
            uow,
            state_id=world.state_id,
            body=PeriodLockRequestIn(certification_comment=COMMENT),
            check_version=lambda actual: None,
        )
    return caught.value


def _lock_row(world: CloseWorld, period_id: UUID | None = None) -> Mapping[str, Any]:
    period = world.period_id if period_id is None else period_id
    with system_session(world) as session:
        return dict(
            session.execute(
                select(period_lock).where(
                    period_lock.c.period_id == period, period_lock.c.kind == LockKind.LOCK.value
                )
            )
            .mappings()
            .one()
        )


def _scope(session: Session, state_id: UUID) -> gates.PeriodScope:
    scope = gates.period_scope(session, state_id, lock=True)
    assert scope is not None
    return scope


def _lock_earlier_periods(world: CloseWorld) -> None:
    """FY2026-P01 to P08 ``permanently_locked`` through the close domain's own writers (CLO6-R3
    (5); ``close_world.earlier_periods_closed``): fixture state for the SM-07 ordering rule (Q-6),
    never the rule. The periods are already ``closed`` when September was soft-closed
    (``_start_close``)."""
    earlier_periods_closed(world, permanently=True)


# --- snapshot evidence -------------------------------------------------------------------------


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest(hashes: Mapping[str, str]) -> str:
    """S15-R-19: SHA-256 of the lines ``<snapshot kind>:<file_sha256>`` sorted by kind and joined
    with a newline (ENGINE_SPEC_B §15.2.7)."""
    lines = "\n".join(f"{kind}:{hashes[kind]}" for kind in sorted(hashes))
    return _sha256(lines.encode("utf-8"))


def _dataset_bytes(session: Session, place: Workspace, file_id: UUID) -> bytes:
    """The plaintext bytes the lock stored for one dataset (T-PLT-29 store, PRV-06 decryption)."""
    _, stream = open_file(session, file_id, files=place.files, keyring=place.keyring)
    return stream.read()


def _snapshots_of(session: Session, lock_id: UUID) -> list[Mapping[str, Any]]:
    return [
        dict(row)
        for row in session.execute(
            select(lock_snapshot).where(lock_snapshot.c.period_lock_id == lock_id)
        ).mappings()
    ]


def _dataset_rows(data: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(data.decode("utf-8"))))


# --- the CLO-6 domain tests --------------------------------------------------------------------


@pytest.mark.control("CTL-016")
def test_ctl_016_lock_blocked_until_gates_pass(world: CloseWorld) -> None:
    """Each blocker keeps the request refused with its own gate named; once every automatic gate
    passes the request is created and routed to ``period.lock`` (twelve PASSED, CONTROLLER_CERTIFIED
    not among them). CLO6-R3 (1): the blockers are cleared in place — no second world."""
    _start_close(world)
    # An empty world fails JE_BALANCED, BATCHES_ACKNOWLEDGED and RECONCILIATIONS_GENERATED.
    refused = _refused_lock(world)
    assert refused.slug == "close-gates-failed"
    failing = {error.rule_id for error in refused.errors}
    assert {"JE_BALANCED", "BATCHES_ACKNOWLEDGED", "RECONCILIATIONS_GENERATED"} <= failing
    wld_b(world)
    refused = _refused_lock(world)
    named = {error.rule_id for error in refused.errors}
    assert {
        "APPROVALS_CLEARED",
        "EXCEPTIONS_CLEARED",
        "HOLDS_REVIEWED",
        "JUDGEMENTS_REVIEWED",
    } <= named
    _clear_blockers(world)
    _pass_gates(world)
    request_id, results = _request_lock(world)
    passed = {r.gate_check_code for r in results if r.status is ChecklistStatus.PASSED}
    # thirteen of the fourteen gates (04 T-CLS-02 rev 1.172): every gate but the certification
    assert len(passed) == 13 and gates.CONTROLLER_CERTIFIED not in passed
    with system_session(world) as session:
        row = session.execute(
            select(approval_request.c.subject_type, approval_request.c.status).where(
                approval_request.c.id == request_id
            )
        ).one()
    assert (_value(row.subject_type), _value(row.status)) == ("PERIOD_LOCK", "PENDING")


def test_request_lock_passes_je_complete_with_the_real_signal(world: CloseWorld) -> None:
    """Retired ``test_request_lock_blocked_only_by_je_complete_until_clo_10`` (record §20 (6); its
    docstring asked for this with CLO-10): with every other automatic gate passing, ``JE_COMPLETE``
    now carries the real completeness signal — the acknowledged run of ``_pass_gates`` covers a
    period without sealed activity, so it is PASSED 0 (never "not evaluated") and the request is
    accepted with twelve gates passed; only ``CONTROLLER_CERTIFIED`` awaits the decision."""
    _start_close(world)
    _pass_gates(world)
    _, results = _request_lock(world)
    by_code = {result.gate_check_code: result for result in results}
    assert (by_code[gates.JE_COMPLETE].status, by_code[gates.JE_COMPLETE].count) == (
        ChecklistStatus.PASSED,
        0,
    )
    assert by_code[gates.JE_COMPLETE].detail != gates.NOT_EVALUATED
    passed = {code for code, result in by_code.items() if result.status is ChecklistStatus.PASSED}
    # thirteen of the fourteen gates (04 T-CLS-02 rev 1.172): every gate but the certification
    assert len(passed) == 13 and gates.CONTROLLER_CERTIFIED not in passed


@pytest.mark.control("CTL-002")
def test_ctl_002_failed_interface_batch_blocks_lock(world: CloseWorld) -> None:
    _start_close(world)
    _pass_gates(world)
    wld_b(world, findings_named=False)  # WLD-B-04: CONTROL_TOTALS_MISMATCH import items
    refused = _refused_lock(world)
    assert refused.slug == "close-gates-failed"
    assert "INTERFACES_COMPLETE" in {error.rule_id for error in refused.errors}


@pytest.mark.control("CTL-049")
def test_ctl_049_unreviewed_judgement_blocks_lock(world: CloseWorld) -> None:
    _start_close(world)
    _pass_gates(world)
    with system_session(world) as session:
        contract_id, _, _ = contract_of(session, world)
        submitted_judgement(session, world, contract_id)
    refused = _refused_lock(world)
    assert refused.slug == "close-gates-failed"
    assert "JUDGEMENTS_REVIEWED" in {error.rule_id for error in refused.errors}


def test_lock_decided_by_another_controller(world: CloseWorld, clock: FrozenClock) -> None:
    _start_close(world)
    _pass_gates(world)
    # BR-CLS-02 isolated: ``engine.decide`` requires the step permission, the step role and an
    # MFA-verified session BEFORE it refuses the preparer (DG-KRN-APR-02; BR-PLT-06), so the
    # submitter is an otherwise authorised Controller with a fresh TOTP — nothing but self-approval
    # can refuse their own decision (the D-98 140 AMENDMENT 7 TEST-CTL007-1 pattern; Maya, a Revenue
    # Accountant without enrolment, is refused for her missing step-up before BR-CLS-02 is read).
    submitter = _controller(world.app, clock, world.tenant_id, name="marcus")
    request_id = _submit_for_lock(world, submitter)
    # The submitter's own approval: 403 self-approval (BR-CLS-02).
    own = approve(world.app, str(request_id), submitter)
    assert (own.status_code, slug(own)) == (403, "self-approval"), own.text
    # Another Controller of the tenant without a fresh TOTP: 403 mfa-step-up-required (BR-PLT-06).
    stale = enrolled(world.app, clock, _assigned_controller(world.tenant_id, "cora"))
    clock.advance(timedelta(minutes=6))
    refused = approve(world.app, str(request_id), stale)
    assert (refused.status_code, slug(refused)) == (403, "mfa-step-up-required"), refused.text
    # With a fresh TOTP the lock executes.
    decided = approve(world.app, str(request_id), step_up(world.app, clock, stale))
    assert decided.status_code == 200, decided.text
    assert _state(world)["state"] == PeriodState.CLOSED.value


def test_lock_approval_takes_the_controller_role(world: CloseWorld, clock: FrozenClock) -> None:
    """Supervisor ruling R-41 (7); PRD §2.5 ``PERIOD_LOCK`` "1: period.lock (Controller)"; 04
    §16.10 rev 1.104: the subject's own step names the Controller role, so holding ``period.lock``
    through another role does not decide a lock. This world publishes no routing rule: the step is
    the subject's own and carries the role (T-PLT-18 ``required_role_id``). Rhea holds
    ``period.lock`` for every entity through a role that is not Controller: 403 ``forbidden``
    naming the role, no decision, the period still closing. A Controller decides. Before the ruling
    the role stood only in the sample world's routing rule, and wherever no such rule was
    published any holder of the permission locked the period."""
    ctx = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    _start_close(world)
    _pass_gates(world)
    submitter = _controller(world.app, clock, world.tenant_id, name="marcus")
    request_id = _submit_for_lock(world, submitter)
    with tenant_session(ctx) as session:
        roles = {
            str(code): UUID(str(role_id))
            for code, role_id in session.execute(select(role.c.code, role.c.id))
        }
        steps = session.execute(
            select(
                approval_step.c.step_no,
                approval_step.c.required_permission,
                approval_step.c.min_approvers,
                approval_step.c.required_role_id,
            ).where(approval_step.c.approval_request_id == request_id)
        ).all()
        routed_by = session.execute(
            select(approval_request.c.routing_rule_id).where(approval_request.c.id == request_id)
        ).scalar_one()
        # The permission without the role: the Revenue Reviewer role is given ``period.lock``.
        session.execute(
            insert(role_permission).values(
                tenant_id=world.tenant_id,
                role_id=roles["revenue_reviewer"],
                permission_code="period.lock",
                created_at=clock.now(),
                created_by_kind="SYSTEM",
            )
        )
    assert routed_by is None
    assert [tuple(step) for step in steps] == [(1, "period.lock", 1, roles["controller"])]
    rhea_member = colleague(world.tenant_id, "rhea")
    assign(rhea_member, "revenue_reviewer")
    rhea = enrolled(world.app, clock, rhea_member)

    shown = get(world.app, f"{APPROVALS}/{request_id}", rhea)
    assert shown.status_code == 200, shown.text
    assert shown.json()["can_decide"] is False
    refused = approve(world.app, str(request_id), rhea)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    assert refused.json()["detail"] == ROLE_REQUIRED_DETAIL.format(role="Controller")
    with tenant_session(ctx, read_only=True) as session:
        decisions = session.execute(
            select(approval_decision.c.id).where(
                approval_decision.c.approval_request_id == request_id
            )
        ).all()
    assert decisions == []
    assert _state(world)["state"] == PeriodState.CLOSING.value

    decided = approve(world.app, str(request_id), _controller(world.app, clock, world.tenant_id))
    assert decided.status_code == 200, decided.text
    assert _state(world)["state"] == PeriodState.CLOSED.value


@pytest.mark.control("CTL-015")
def test_sc1_the_lock_decision_does_not_wait_for_a_held_next_period_row(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """SC-1, the deadlock order (04 DB-07 rev 1.113, third row): BR-CLS-03 takes the ``future``
    next period's state row without waiting. Another transaction holds October's row ``FOR
    UPDATE`` — as ``open_future_period`` does from its first read, and goes on doing while its
    re-dirtying waits for a combination group — and the lock decision of September is answered
    409 ``lock-conflict``: the database's "could not obtain lock", not the end of a wait. Nothing
    is written and the request stays pending; once the other transaction has ended, the same
    request locks September and opens October.

    Fail-first (``FOR UPDATE`` without ``NOWAIT``): the statement waits for the row — to
    ``lock_timeout`` here, and beside a posting that holds a group the opening needs while it
    waits for September's row, until the deadlock detector ends one of the three."""
    _start_close(world)
    _pass_gates(world)
    request_id, _ = _request_lock(world)
    controller = _controller(world.app, clock, world.tenant_id)
    october = UUID(str(_state(world, "FY2026-P10")["id"]))
    before = _observations(world, request_id)
    with system_session(world) as holder:
        held = holder.execute(
            select(period_state.c.state).where(period_state.c.id == october).with_for_update()
        ).scalar_one()
        assert _value(held) == PeriodState.FUTURE.value
        # the statement of the decision, under the closing period's row as the decision holds it.
        # Since 04 DB-07 rev 1.182 (supervisor ruling R-116 (h), review finding F8) that statement
        # is ``_hold_future_next_period``'s, at the decision's start, and its 55P03 is answered by
        # name; the database's refusal is the same and is the named problem's cause.
        with world.place.uow() as uow, pytest.raises(Problem) as refused:
            close_commands._hold_future_next_period(
                uow.session, _scope(uow.session, world.state_id)
            )
        cause = refused.value.__cause__
        assert isinstance(cause, DBAPIError)
        assert getattr(cause.orig, "sqlstate", None) == "55P03"
        assert "could not obtain lock on row" in str(cause.orig)
        assert [error.rule_id for error in refused.value.errors] == ["NEXT_PERIOD_HELD"]
        # the decision through the public path
        decided = approve(world.app, str(request_id), controller)
        assert (decided.status_code, slug(decided)) == (409, "lock-conflict"), decided.text
        assert [error["rule_id"] for error in decided.json()["errors"]] == ["NEXT_PERIOD_HELD"]
        assert _observations(world, request_id) == before
        holder.rollback()
    again = approve(world.app, str(request_id), controller)
    assert again.status_code == 200, again.text
    assert _state(world)["state"] == PeriodState.CLOSED.value
    assert _state(world, "FY2026-P10")["state"] == PeriodState.OPEN.value


def test_lock_writes_certification_and_snapshots(world: CloseWorld, clock: FrozenClock) -> None:
    """T-CLS-04 certification of the fourteen gates; T-CLS-05 rows for the twelve E-64 kinds, each
    hashing the bytes the lock stored (S15-R-18) and the S15-R-19 manifest over them (CLO6-R3 (7):
    exact kinds, actual file hashes, sorted-hash manifest — no fallback); ``report_run_id`` NULL
    (Q-10); BR-CLS-03 opens October."""
    _start_close(world)
    _pass_gates(world)
    request_id, _ = _request_lock(world)
    decided = approve(world.app, str(request_id), _controller(world.app, clock, world.tenant_id))
    assert decided.status_code == 200, decided.text
    lock = _lock_row(world)
    certification = lock["certification"]
    assert [row["gate_check_code"] for row in certification] == list(gates.GATE_CHECK_CODES)
    assert all(row["status"] == "PASSED" for row in certification)
    hashes: dict[str, str] = {}
    with system_session(world) as session:
        snapshots = _snapshots_of(session, UUID(str(lock["id"])))
        for snapshot in snapshots:
            file_id = UUID(str(snapshot["file_id"]))
            stored = session.execute(
                select(file_object.c.sha256, file_object.c.purpose).where(
                    file_object.c.id == file_id
                )
            ).one()
            data = _dataset_bytes(session, world.place, file_id)
            expected = str(snapshot["file_sha256"])
            assert (str(stored.sha256), _value(stored.purpose)) == (
                expected,
                FilePurpose.SNAPSHOT_DATASET.value,
            )
            assert _sha256(data) == expected
            header_and_rows = sum(1 for _ in csv.reader(io.StringIO(data.decode("utf-8"))))
            assert int(snapshot["row_count"]) == header_and_rows - 1
            assert snapshot["report_run_id"] is None  # ruling Q-10
            hashes[_value(snapshot["snapshot_kind"])] = expected
        head = session.execute(
            select(ledger_chain_head.c.last_chain_seq).where(ledger_chain_head.c.book_code == BOOK)
        ).scalar_one()
        october = session.execute(
            select(period_state.c.state).where(
                period_state.c.entity_id == world.entity_id,
                period_state.c.period_end_date == date(2026, 10, 31),
            )
        ).scalar_one()
    assert len(snapshots) == 12 and sorted(hashes) == sorted(TWELVE_KINDS)
    assert lock["snapshot_manifest_sha256"] == _manifest(hashes)
    assert lock["ledger_head_chain_seq"] == head
    assert _state(world)["state"] == PeriodState.CLOSED.value
    assert _value(october) == PeriodState.OPEN.value  # BR-CLS-03


def test_contract_balances_snapshot_k01(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """With ``worlds.k01_pellworth`` through 31 Aug 2026 and Aug 2026 locked, the stored
    ``CONTRACT_BALANCES`` dataset (RPT-02 columns; read back from the store) carries contract
    liability 39,708.49 for ``SF-ORD-10001`` (WLD-X-03). CLO6-R3 (8): the evidence is what the lock
    stored, not a ``control_totals`` shape. Residual (1): Maya (the report world's Revenue
    Accountant, ``period.close``) soft-closes August — Priya holds only ``ssp_approver`` — and
    August carries the acknowledged run and reviewed reconciliations a lock needs. The run is the
    one the product calculates over K-01's sealed August activity (``POST /journal-runs`` and its
    job): ``JE_COMPLETE`` is the CLO-10 completeness assertion over sealed lines (REQ-JE-005), and
    a fixture run of ``acknowledged_run_for`` covers the chain range (0, 0] — it journalises none
    of a world that has activity, which the gate rightly refuses ("Journals complete"). The close
    runs on the record-time clock: the lock freezes each dataset on the historical basis at its
    execution instant (ENGINE_SPEC_B S15-R-18; READ-1), and ``contract_version.known_at`` is the
    greatest server-stamped ``recorded_at`` of its events (04 T-CON-07, T-CON-08; DB-08), later
    than the FrozenClock the world was built at — a lock at the business clock freezes
    ``CONTRACT_BALANCES`` without K-01."""
    from support.worlds import k01_pellworth, resigned, run_now

    pellworth = k01_pellworth(app, keyring, clock, files, through=date(2026, 8, 31))
    # F-RPS-CUTOFF-R1: one server read after the world's last commit is the record-time clock;
    # the jump of days ends every session at the 12-hour limit (SAR-10), so the personas re-sign.
    stamp = pellworth.place.scalar(select(func.clock_timestamp()))
    clock.set(stamp + timedelta(seconds=1))
    pellworth = resigned(pellworth)
    maya = pellworth.maya
    # PRD WLD-P-02 / BR-CLS-08 (supervisor ruling R-6): K-01's January to July are closed before
    # August is brought to its lock — fixture state; their sealed lines stay as they are.
    periods_closed_before(
        pellworth.place, app, maya, entity_id=pellworth.entity_id, before="FY2026-P08"
    )
    (august,) = [
        item
        for item in periods(app, maya, entity="AVM-US")
        if item["period"]["period_key"] == "FY2026-P08"
    ]
    started = post(
        app,
        f"{PERIODS}/{august['id']}/start-close",
        maya,
        {"comment": "August close"},
        if_match=f'"r{august["row_version"]}"',
    )
    assert started.status_code == 200, started.text
    period_id = UUID(str(august["period"]["id"]))
    requested = post(app, JOURNAL_RUNS, maya, {"entity_code": "AVM-US", "period_key": "FY2026-P08"})
    assert requested.status_code == 202, requested.text
    calculated = run_now(pellworth, UUID(str(requested.json()["id"])))
    assert calculated["state"] == "SUCCEEDED", calculated
    context = DbContext(tenant_id=pellworth.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        acknowledge_run(
            session, UUID(str(requested.headers[JOURNAL_RUN_ID_HEADER])), now=clock.now()
        )
        reviewed_reconciliations_for(
            session,
            tenant_id=pellworth.tenant_id,
            entity_id=pellworth.entity_id,
            period_id=period_id,
            now=clock.now(),
        )
        close_run_succeeded_for(
            session,
            tenant_id=pellworth.tenant_id,
            entity_id=pellworth.entity_id,
            period_id=period_id,
            now=clock.now(),
        )
    with pellworth.place.uow() as uow:
        out = close_commands.request_lock(
            uow,
            state_id=UUID(str(august["id"])),
            body=PeriodLockRequestIn(certification_comment="August 2026 close complete"),
            check_version=lambda actual: None,
        )
        uow.commit()
    controller = _controller(app, clock, pellworth.tenant_id)
    decided = approve(app, str(out.approval_request_id), controller)
    assert decided.status_code == 200, decided.text
    with pellworth.place.uow() as uow:
        session = uow.session
        lock_id = session.execute(
            select(period_lock.c.id).where(
                period_lock.c.period_id == period_id, period_lock.c.kind == LockKind.LOCK.value
            )
        ).scalar_one()
        (snapshot,) = [
            row
            for row in _snapshots_of(session, UUID(str(lock_id)))
            if _value(row["snapshot_kind"]) == SnapshotKind.CONTRACT_BALANCES.value
        ]
        data = _dataset_bytes(session, pellworth.place, UUID(str(snapshot["file_id"])))
    assert _sha256(data) == str(snapshot["file_sha256"])
    (k01,) = [row for row in _dataset_rows(data) if row["contract_external_id"] == "SF-ORD-10001"]
    assert Decimal(k01["contract_liability"]) == Decimal("39708.49")


def test_lock_certifies_reconciliations(world: CloseWorld, clock: FrozenClock) -> None:
    """REVIEWED and AUTO_CERTIFIED reconciliations of the period become CERTIFIED with
    ``certified_at`` and the lock's id written once (SM-09; T-CLS-06 rev 1.23, D-98 63). Residual
    (2): the source statuses are reached along the admitted pairs (DRAFT → PREPARED → REVIEWED;
    DRAFT → AUTO_CERTIFIED) — REVIEWED → AUTO_CERTIFIED is not a transition and the rule stays."""
    _start_close(world)
    acknowledged_run(world)
    with system_session(world) as session:
        reviewed_reconciliations(session, world, kinds=("SUBLEDGER_TO_GL",), status="REVIEWED")
        reviewed_reconciliations(
            session, world, kinds=("BILLING_TO_SUBLEDGER",), status="AUTO_CERTIFIED"
        )
        close_run_succeeded(session, world)
        before = sorted(
            (_value(row.kind), _value(row.status))
            for row in session.execute(
                select(reconciliation.c.kind, reconciliation.c.status).where(
                    reconciliation.c.period_id == world.period_id
                )
            )
        )
    assert before == [("BILLING_TO_SUBLEDGER", "AUTO_CERTIFIED"), ("SUBLEDGER_TO_GL", "REVIEWED")]
    request_id, _ = _request_lock(world)
    decided = approve(world.app, str(request_id), _controller(world.app, clock, world.tenant_id))
    assert decided.status_code == 200, decided.text
    lock = _lock_row(world)
    with system_session(world) as session:
        rows = session.execute(
            select(
                reconciliation.c.status,
                reconciliation.c.certified_at,
                reconciliation.c.period_lock_id,
            ).where(reconciliation.c.period_id == world.period_id)
        ).all()
    assert len(rows) == 2
    assert all(_value(row.status) == "CERTIFIED" and row.certified_at is not None for row in rows)
    assert all(row.period_lock_id == lock["id"] for row in rows)


def _request_permanent_lock(world: CloseWorld, actor: Actor) -> Any:
    """``POST /periods/{id}/request-permanent-lock`` as ``actor``."""
    shown = _state(world)
    return post(
        world.app,
        f"{PERIODS}/{shown['id']}/request-permanent-lock",
        actor,
        {"comment": PERMANENT_COMMENT},
        if_match=f'"r{shown["row_version"]}"',
    )


def _permanent_lock_requests(world: CloseWorld) -> list[str]:
    """The statuses of the ``PERIOD_LOCK`` requests of September that are not yet decided."""
    with system_session(world) as session:
        return [
            _value(status)
            for status in session.execute(
                select(approval_request.c.status).where(
                    approval_request.c.subject_type == "PERIOD_LOCK",
                    approval_request.c.subject_id == world.state_id,
                    approval_request.c.status == "PENDING",
                )
            ).scalars()
        ]


def test_permanent_lock_needs_second_controller(world: CloseWorld, clock: FrozenClock) -> None:
    """``closed → permanently_locked`` is requested by a Controller and decided by a second one
    (PRD ACT-27, SM-07 "Permanently lock": ``period.lock``; supervisor ruling R-83 (a), item
    CLO-PERMLOCK-PERM-1 — the request took ``period.close``, so a Revenue Accountant requested it
    and one Controller sufficed). Q-6: every earlier period of the entity and book is permanently
    locked first (CLO6-R3 (5): the fixture drives FY2026-P01 to P08 there through the domain's own
    writers); afterwards no reopen (SM-07)."""
    _start_close(world)
    _pass_gates(world)
    request_id, _ = _request_lock(world)
    first = _controller(world.app, clock, world.tenant_id, name="cora")
    assert approve(world.app, str(request_id), first).status_code == 200
    assert _state(world)["state"] == PeriodState.CLOSED.value
    _lock_earlier_periods(world)

    # A holder of ``period.close`` alone does not request it: the route refuses Maya, and the
    # domain's own check refuses her unit of work; no request is written.
    refused = _request_permanent_lock(world, world.maya)
    assert (refused.status_code, slug(refused)) == (403, "forbidden"), refused.text
    with pytest.raises(Problem) as caught, world.place.uow() as uow:
        close_commands.request_permanent_lock(
            uow,
            state_id=world.state_id,
            body=PeriodPermanentLockRequestIn(comment=PERMANENT_COMMENT),
            check_version=lambda actual: None,
        )
    assert caught.value.slug == "not-found"  # ``require_for_entity``: DG-KRN-AUTH-04
    # ``period.lock`` is needed for the period's own entity: Rita closes the books of AVM-US and is
    # a Controller of AVM-UK only, so she sees the period and is not its Controller.
    with system_session(world) as session:
        uk = other_entity(session, world)
    rita_member = colleague(world.tenant_id, "rita")
    assign(rita_member, "revenue_accountant", entity_ids=[world.entity_id])
    assign(rita_member, "controller", entity_ids=[uk])
    elsewhere = _request_permanent_lock(world, enrolled(world.app, clock, rita_member))
    assert (elsewhere.status_code, slug(elsewhere)) == (404, "not-found"), elsewhere.text
    assert _permanent_lock_requests(world) == []

    # A Controller requests it. Her own decision is self-approval (BR-CLS-02's rule in the approval
    # kernel); the routing finds the second holder of ``period.lock``, who decides.
    requested = _request_permanent_lock(world, first)
    assert requested.status_code == 200, requested.text
    permanent_id = str(requested.json()["approval_request_id"])
    with system_session(world) as session:
        kind = session.execute(
            select(approval_request.c.subject_type).where(
                approval_request.c.id == UUID(permanent_id)
            )
        ).scalar_one()
    assert _value(kind) == "PERIOD_LOCK"
    assert _permanent_lock_requests(world) == ["PENDING"]
    own = approve(world.app, permanent_id, first)
    assert (own.status_code, slug(own)) == (403, "self-approval"), own.text
    assert _state(world)["state"] == PeriodState.CLOSED.value
    second = _controller(world.app, clock, world.tenant_id, name="dana")
    assert approve(world.app, permanent_id, second).status_code == 200
    assert _state(world)["state"] == PeriodState.PERMANENTLY_LOCKED.value
    with system_session(world) as session:
        kinds = (
            session.execute(
                select(period_lock.c.kind).where(period_lock.c.period_id == world.period_id)
            )
            .scalars()
            .all()
        )
    assert sorted(_value(k) for k in kinds) == [
        LockKind.LOCK.value,
        LockKind.PERMANENT_LOCK.value,
    ]
    # The requester holds ``period.reopen_request`` (PRD §5.6: Revenue Reviewer and Controller;
    # ACT-28 — the CLO-7 route's permission), so the refusal is SM-07's, not the permission's.
    reopen = post(
        world.app,
        f"{PERIODS}/{world.state_id}/request-reopen",
        second,
        {
            "judgement_record_id": str(reviewed_error_judgement(world)),
            "reason_code": "ERROR_CORRECTION",
            "comment": "Late September costs",
        },
        if_match=f'"r{_state(world)["row_version"]}"',
    )
    assert (reopen.status_code, slug(reopen)) == (409, "invalid-transition"), reopen.text


def test_days_to_close_last_three(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """``kpis.days_to_close_last_three``: June, July and August 2026, each locked at 09:00
    America/New_York 5, 4 and 6 days after its period's end, give 5, 4 and 6 days (REQ-CLS-020;
    [J] D-88 L7-2-Q-8). CLO6-R3 (2): ``FrozenClock.set`` takes an aware datetime; the world is
    built at the first instant and each step signs Maya in afresh so no session outlives the
    clock.

    The three instants are computed from the period ends and lie behind the fixture's frozen
    instant — the last is 6 September 2026 — and so behind the server's clock on every day the
    suite runs (dev-guide DG-TST-14 rev 1.276; the supervisor's ruling of 2026-10-02 08:53).
    Until then the test locked July to September, the last on 6 October 2026: an instant the
    server's clock had still to pass, on which the third lock's cutoff would have changed from
    the application instant to the transaction timestamp. The answer did not depend on it —
    this world holds no contract, line or version — but a test's instants do not wait for a
    calendar day."""
    frozen = clock.now()
    months = (("FY2026-P06", date(2026, 6, 30), 5), ("FY2026-P07", date(2026, 7, 31), 4))
    months += (("FY2026-P08", date(2026, 8, 31), 6),)
    lock_instants = tuple(
        (key, end, datetime.combine(end + timedelta(days=days), time(9), tzinfo=NEW_YORK))
        for key, end, days in months
    )
    assert all(at < frozen for _, _, at in lock_instants)
    clock.set(lock_instants[0][2])
    world = close_world(app, keyring, clock, files)
    state_id = world.state_id
    for key, end, at in lock_instants:
        clock.set(at)
        maya = world.maya.member
        world = replace(world, maya=signed_actor(app, maya, sign_in(app, maya.email)))
        shown = _start_close(world, key)
        assert shown["period"]["end_date"] == end.isoformat()  # the instants follow the calendar
        period_id = UUID(str(shown["period"]["id"]))
        state_id = UUID(str(shown["id"]))
        _pass_gates(world, period_id)
        request_id, _ = _request_lock(world, state_id, f"{key} close complete")
        decided = approve(app, str(request_id), _controller(app, clock, world.tenant_id))
        assert decided.status_code == 200, decided.text
    with world.place.uow() as uow:
        scope = gates.period_scope(uow.session, state_id)  # August's cockpit
        assert scope is not None
        kpis = queries.days_to_close(uow.session, scope)
    assert [(row["period_key"], row["days"]) for row in kpis] == [
        ("FY2026-P06", 5),
        ("FY2026-P07", 4),
        ("FY2026-P08", 6),
    ]


def test_checklist_items_carry_the_certified_result(world: CloseWorld, clock: FrozenClock) -> None:
    """After the lock the CONTROLLER_CERTIFIED item is PASSED (``gates.store_results`` at lock)."""
    _start_close(world)
    _pass_gates(world)
    request_id, _ = _request_lock(world)
    decided = approve(world.app, str(request_id), _controller(world.app, clock, world.tenant_id))
    assert decided.status_code == 200, decided.text
    with system_session(world) as session:
        status = _certified_item_status(session, world)
    assert status == ChecklistStatus.PASSED.value


def _certified_item_status(session: Session, world: CloseWorld) -> str:
    return _value(
        session.execute(
            select(close_checklist_item.c.status)
            .select_from(
                close_checklist_item.join(
                    close_checklist_template,
                    close_checklist_template.c.id
                    == close_checklist_item.c.close_checklist_template_id,
                )
            )
            .where(
                close_checklist_item.c.period_id == world.period_id,
                close_checklist_template.c.gate_check_code == gates.CONTROLLER_CERTIFIED,
            )
        ).scalar_one()
    )


def test_refused_lock_persists_nothing(world: CloseWorld, clock: FrozenClock) -> None:
    """D-98 61: the gate, checklist and approval statements that precede a refusal rely on same-UOW
    rollback — after a refused lock decision nothing is persisted (no lock row, state and version
    unchanged). The decision is refused because a gate fails at execution time (a hold appears after
    the request; Q-3: the request stays PENDING)."""
    _start_close(world)
    _pass_gates(world)
    request_id, _ = _request_lock(world)
    before = _state(world)
    with system_session(world) as session:
        contract_id, event_id, _ = contract_of(session, world)
        session.execute(
            insert(contract_hold).values(
                **contract_hold_values(
                    world.tenant_id, contract_id=contract_id, applied_event_id=event_id
                )
            )
        )
    decided = approve(world.app, str(request_id), _controller(world.app, clock, world.tenant_id))
    assert (decided.status_code, slug(decided)) == (409, "close-gates-failed"), decided.text
    after = _state(world)
    assert (after["state"], after["row_version"]) == (before["state"], before["row_version"])
    with system_session(world) as session:
        locks = session.execute(
            select(period_lock.c.id).where(period_lock.c.period_id == world.period_id)
        ).all()
        status = session.execute(
            select(approval_request.c.status).where(approval_request.c.id == request_id)
        ).scalar_one()
    assert locks == [] and _value(status) == "PENDING"


def _observations(world: CloseWorld, request_id: UUID) -> dict[str, Any]:
    """Everything a lock decision writes, read back for the before / after comparison (R3 (9))."""
    shown = _state(world)
    with system_session(world) as session:
        count = lambda table, *where: int(  # noqa: E731
            session.execute(select(func.count()).select_from(table).where(*where)).scalar_one()
        )
        return {
            "state": shown["state"],
            "row_version": shown["row_version"],
            "transitions": count(
                period_state_transition, period_state_transition.c.period_state_id == world.state_id
            ),
            "locks": count(period_lock, period_lock.c.period_id == world.period_id),
            "snapshots": count(lock_snapshot),
            "dataset_files": count(
                file_object, file_object.c.purpose == FilePurpose.SNAPSHOT_DATASET.value
            ),
            "decisions": count(
                approval_decision, approval_decision.c.approval_request_id == request_id
            ),
            "request_status": _value(
                session.execute(
                    select(approval_request.c.status).where(approval_request.c.id == request_id)
                ).scalar_one()
            ),
            "reconciliations": sorted(
                (_value(row.kind), _value(row.status), row.certified_at, row.period_lock_id)
                for row in session.execute(
                    select(
                        reconciliation.c.kind,
                        reconciliation.c.status,
                        reconciliation.c.certified_at,
                        reconciliation.c.period_lock_id,
                    ).where(reconciliation.c.period_id == world.period_id)
                )
            ),
            "certified_item": _certified_item_status(session, world),
            "october": _value(
                session.execute(
                    select(period_state.c.state).where(
                        period_state.c.entity_id == world.entity_id,
                        period_state.c.period_end_date == date(2026, 10, 31),
                    )
                ).scalar_one()
            ),
        }


def _writes_seen(session: Session, world: CloseWorld) -> dict[str, Any]:
    """What the lock has written so far, read through the callback's own session (uncommitted)."""
    state = session.execute(
        select(period_state.c.state, period_state.c.current_lock_id).where(
            period_state.c.id == world.state_id
        )
    ).one()
    locks = session.execute(
        select(period_lock.c.id, period_lock.c.kind).where(
            period_lock.c.period_id == world.period_id
        )
    ).all()
    lock_ids = [UUID(str(row.id)) for row in locks]
    snapshots = (
        0
        if not lock_ids
        else int(
            session.execute(
                select(func.count())
                .select_from(lock_snapshot)
                .where(lock_snapshot.c.period_lock_id.in_(lock_ids))
            ).scalar_one()
        )
    )
    return {
        "state": _value(state.state),
        "current_lock_is_the_lock": lock_ids == [state.current_lock_id],
        "locks": [_value(row.kind) for row in locks],
        "lock_ids": [str(lock_id) for lock_id in lock_ids],
        "snapshots": snapshots,
        "certified_item": _certified_item_status(session, world),
        "reconciliations": sorted(
            (_value(row.status), row.period_lock_id in lock_ids and row.certified_at is not None)
            for row in session.execute(
                select(
                    reconciliation.c.status,
                    reconciliation.c.certified_at,
                    reconciliation.c.period_lock_id,
                ).where(reconciliation.c.period_id == world.period_id)
            )
        ),
        "october": _value(
            session.execute(
                select(period_state.c.state).where(
                    period_state.c.entity_id == world.entity_id,
                    period_state.c.period_end_date == date(2026, 10, 31),
                )
            ).scalar_one()
        ),
    }


def test_failed_lock_callback_rolls_back_everything(
    world: CloseWorld, clock: FrozenClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Durable rollback (CLO6-R3 (9); residual (3)): when the ``PERIOD_LOCK`` callback fails after
    every write — the lock row, transition and current lock, the snapshot rows and dataset files,
    the certified checklist results, the reconciliation certification and the October opening —
    the request's transaction rolls back as a whole. The proof has two halves, and a 500 alone is
    neither: (a) the injected CTL-016 recorder executed AFTER the intended writes — it records,
    through the callback's own session, the lock, twelve snapshots, CONTROLLER_CERTIFIED PASSED,
    both reconciliations CERTIFIED against the lock and October open, plus the CTL-016 arguments it
    was given, before raising; a missing producer or an earlier error leaves that record empty;
    (b) nothing of it persists: no decision, the request PENDING, state / version / history
    unchanged, no lock, no snapshot, no dataset ``file_object`` (store objects, if any, are the
    SCH-14 orphan sweep's), CONTROLLER_CERTIFIED still FAILED, reconciliations unchanged, October
    still ``future``. The only test double is the recorder; the run-reference enum, the snapshot
    registry and the engine are the real producers by name."""
    _start_close(world)
    _pass_gates(world)
    request_id, _ = _request_lock(world)
    before = _observations(world, request_id)
    assert (before["state"], before["request_status"], before["locks"]) == ("closing", "PENDING", 0)
    assert (before["certified_item"], before["october"]) == ("FAILED", PeriodState.FUTURE.value)
    assert [row[1:] for row in before["reconciliations"]] == [("REVIEWED", None, None)] * 2
    resolve_recorder = close_dependencies.control_evidence
    reached: list[dict[str, Any]] = []

    def failing_recorder() -> close_dependencies.ControlEvidence:
        real = resolve_recorder()  # P4's registry by name; ProducerMissing when absent

        def record_execution(uow: Any, **kwargs: Any) -> None:
            reached.append({"writes": _writes_seen(uow.session, world), "call": dict(kwargs)})
            raise RuntimeError(RECORDER_FAILURE)

        return close_dependencies.ControlEvidence(
            run_ref_type=real.run_ref_type, record_execution=record_execution
        )

    monkeypatch.setattr(close_dependencies, "control_evidence", failing_recorder)
    decided = approve(world.app, str(request_id), _controller(world.app, clock, world.tenant_id))
    assert decided.status_code == 500, decided.text
    # (a) the failure was injected after every intended write.
    (seen,) = reached
    writes = dict(seen["writes"])
    (observed_lock_id,) = writes.pop("lock_ids")  # the lock the callback saw, rolled back below
    assert writes == {
        "state": PeriodState.CLOSED.value,
        "current_lock_is_the_lock": True,
        "locks": [LockKind.LOCK.value],
        "snapshots": 12,
        "certified_item": ChecklistStatus.PASSED.value,
        "reconciliations": [("CERTIFIED", True), ("CERTIFIED", True)],
        "october": PeriodState.OPEN.value,
    }
    call = seen["call"]
    assert (call["control_id"], _value(call["run_ref_type"]), call["run_ref_id"]) == (
        close_commands.CONTROL_CLOSE_GATES,
        "PERIOD_LOCK",
        request_id,
    )
    assert (call["population_count"], call["exception_count"], _value(call["result"])) == (
        len(gates.GATE_CHECK_CODES),
        0,
        "PASS",
    )
    assert (call["entity_id"], call["book_code"], call["period_id"]) == (
        world.entity_id,
        BOOK,
        world.period_id,
    )
    # The CTL-016 detail names exactly the lock the callback observed (Codex CLO6-R3 residuals
    # closure, coverage gap): equality, not merely a well-formed id.
    assert call["detail"]["period_lock_id"] == observed_lock_id
    # (b) nothing of it persisted.
    assert _observations(world, request_id) == before


# --- CLO-GATE-SCOPE-1: a gate's result does not depend on who evaluates it (ruling R-42 (d)) ----


def _failure_item(world: CloseWorld, run_id: UUID, *, entity_id: UUID | None, status: str) -> UUID:
    """One failure item of a sync run in the exception queue, naming ``entity_id`` or no entity."""
    item = exception_item_values(
        world.tenant_id,
        source="SYNC",
        code="PRODUCT_UNMAPPED",
        title="Interface run failure",
        sync_run_id=run_id,
        entity_id=entity_id,
        status=status,
        resolution=None if status == "OPEN" else "Product mapped.",
    )
    with system_session(world) as session:
        session.execute(insert(exception_item).values(**item))
    return UUID(str(item["id"]))


def _gate_errors(response: Any) -> list[str]:
    return [error["rule_id"] for error in response.json()["errors"]]


def test_lock_gates_read_every_entity_whoever_asks(world: CloseWorld, clock: FrozenClock) -> None:
    """CLO-GATE-SCOPE-1 (supervisor ruling R-42 (d)): "a control's result must not depend on who
    decides". A failed sync run of a connection that serves every entity has one failure item
    that names another entity; row-level security hides that item from callers whose roles name
    AVM-US alone (T-IMP-05: ``entity_id IS NULL OR entity_in_scope(entity_id)``), so under their
    own row scope the run read as cleared and the interface gate passed. The gates now read every
    entity of the tenant at the lock request and at the lock decision."""
    app = world.app
    _start_close(world)
    _pass_gates(world)
    with system_session(world) as session:
        uk = other_entity(session, world)
        connection = integration_connection_values(world.tenant_id, name="Salesforce (orders)")
        session.execute(insert(integration_connection).values(**connection))
        run_id = new_id()
        session.execute(
            insert(sync_run).values(
                tenant_id=world.tenant_id,
                id=run_id,
                integration_connection_id=connection["id"],
                kind="WEBHOOK_BATCH",
                status="FAILED",
                checkpoint_before={},
                created_by_kind="SYSTEM",
                updated_by_kind="SYSTEM",
            )
        )
    _failure_item(world, run_id, entity_id=None, status="RESOLVED")
    hidden = _failure_item(world, run_id, entity_id=uk, status="OPEN")
    # Personas whose roles name AVM-US alone: a Revenue Accountant and a Controller (fresh TOTP).
    rita = holding(
        app, colleague(world.tenant_id, "rita"), "revenue_accountant", entity_ids=[world.entity_id]
    )
    cole_member = colleague(world.tenant_id, "cole")
    assign(cole_member, "controller", entity_ids=[world.entity_id])
    cole = enrolled(app, clock, cole_member)

    def request_lock(actor: Actor) -> Any:
        shown = _state(world)
        return post(
            app,
            f"{PERIODS}/{shown['id']}/request-lock",
            actor,
            {"certification_comment": COMMENT},
            if_match=f'"r{shown["row_version"]}"',
        )

    # At the request: the tenant-wide accountant and the AVM-US-only accountant get one answer.
    for actor in (world.maya, rita):
        refused = request_lock(actor)
        assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
        assert _gate_errors(refused) == ["INTERFACES_COMPLETE"]
        assert refused.json()["errors"][0]["message"] == (
            "Interface batch not complete: Salesforce (orders) (1 runs)"
        )

    # The item is resolved: the AVM-US-only accountant submits the period for lock.
    with system_session(world) as session:
        session.execute(
            update(exception_item)
            .where(exception_item.c.id == hidden)
            .values(status="RESOLVED", resolution="Product mapped.", updated_by_kind="SYSTEM")
        )
    requested = request_lock(rita)
    assert requested.status_code == 200, requested.text
    request_id = str(requested.json()["approval_request_id"])

    # At the decision: a new failure item names the other entity; the AVM-US-only Controller's
    # approval evaluates the same gates as anyone's and refuses the lock.
    late = _failure_item(world, run_id, entity_id=uk, status="OPEN")
    blocked = approve(app, request_id, cole)
    assert (blocked.status_code, slug(blocked)) == (409, "close-gates-failed"), blocked.text
    assert _gate_errors(blocked) == ["INTERFACES_COMPLETE"]
    assert _state(world)["state"] == PeriodState.CLOSING.value
    with system_session(world) as session:
        locks = session.execute(
            select(func.count())
            .select_from(period_lock)
            .where(period_lock.c.period_id == world.period_id)
        ).scalar_one()
    assert locks == 0  # nothing of the refused lock was written (September's; R-6 fixture aside)

    # Positive control: with the item cleared the same Controller locks the period.
    with system_session(world) as session:
        session.execute(
            update(exception_item)
            .where(exception_item.c.id == late)
            .values(status="DISMISSED", resolution="Superseded.", updated_by_kind="SYSTEM")
        )
    decided = approve(app, request_id, cole)
    assert decided.status_code == 200, decided.text
    assert _state(world)["state"] == PeriodState.CLOSED.value


# --- SC-N4: tenant tasks and waivers in the lock decision (supervisor rulings R-54 (h), R-55) ---

TEMPLATES = "/api/v1/close-checklist-templates"


def _checklist(world: CloseWorld, actor: Actor) -> dict[str, dict[str, Any]]:
    """The cockpit's checklist rows of September by code, with the period's ``If-Match``."""
    shown = get(world.app, f"{PERIODS}/{world.state_id}/cockpit", actor)
    assert shown.status_code == 200, shown.text
    return {item["code"]: item for item in shown.json()["checklist"]}


def _lock_request(world: CloseWorld, actor: Actor) -> Any:
    shown = _state(world)
    return post(
        world.app,
        f"{PERIODS}/{shown['id']}/request-lock",
        actor,
        {"certification_comment": COMMENT},
        if_match=f'"r{shown["row_version"]}"',
    )


def _errors(response: Any) -> list[tuple[str, str]]:
    return [(error["rule_id"], error["message"]) for error in response.json()["errors"]]


def test_unsigned_blocking_close_task_refuses_the_lock(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """SC-N4 / supervisor ruling R-55 (a); PRD BR-CLS-01 "custom close tasks signed": with every
    system gate passed, a blocking tenant task that is not signed refuses the lock request and the
    lock decision — 409 ``close-gates-failed`` naming the task by its template code — and a task
    with ``is_blocking = false`` never does. Until this fix the server decided on the system gates
    alone; only the screen held the rule (D-88 L7-2-Q-16)."""
    app = world.app
    _start_close(world)
    _pass_gates(world)
    admin_member = colleague(world.tenant_id, "tess")
    assign(admin_member, "tenant_admin")
    admin = enrolled(app, clock, admin_member)  # settings.manage needs an MFA-verified session
    for body in (
        {"code": "SALES-TAX-REVIEW", "name": "Sales tax review", "gate_kind": "MANUAL"},
        {
            "code": "FYI-NOTE",
            "name": "Note for next period",
            "gate_kind": "MANUAL",
            "is_blocking": False,
        },
    ):
        created = post(app, TEMPLATES, admin, {"is_blocking": True, "due_offset_days": 3, **body})
        assert created.status_code == 201, created.text

    # At the request: the unsigned blocking task refuses, the non-blocking one is not named.
    refused = _lock_request(world, world.maya)
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    assert refused.json()["detail"] == "1 close gates have not passed: Sales tax review."
    assert _errors(refused) == [("SALES-TAX-REVIEW", "Close task not signed: Sales tax review")]

    # Signed (MFA-verified preparer), the request is accepted; the note stays unsigned throughout.
    signer = enrolled(app, clock, world.maya.member)
    # 03 REQ-PLT-005: with a factor her earlier session owes the second step; the world's
    # helpers go on with the verified one.
    world = carrying(world, maya=signer)
    rows = _checklist(world, signer)
    assert (rows["SALES-TAX-REVIEW"]["is_blocking"], rows["FYI-NOTE"]["is_blocking"]) == (
        True,
        False,
    )
    shown = _state(world)
    signed = post(
        app,
        f"{PERIODS}/{shown['id']}/checklist/{rows['SALES-TAX-REVIEW']['id']}/sign",
        signer,
        {"statement_accepted": True},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert signed.status_code == 200, signed.text
    requested = _lock_request(world, world.maya)
    assert requested.status_code == 200, requested.text
    request_id = str(requested.json()["approval_request_id"])
    assert _checklist(world, world.maya)["FYI-NOTE"]["status"] == "NOT_STARTED"

    # At the decision: a blocking task defined after the request refuses the Controller's lock.
    late = post(
        app,
        TEMPLATES,
        admin,
        {"code": "CUTOFF-MEMO", "name": "Cut-off memo", "gate_kind": "MANUAL", "is_blocking": True},
    )
    assert late.status_code == 201, late.text
    controller = _controller(app, clock, world.tenant_id)
    blocked = approve(app, request_id, controller)
    assert (blocked.status_code, slug(blocked)) == (409, "close-gates-failed"), blocked.text
    assert _errors(blocked) == [("CUTOFF-MEMO", "Close task not signed: Cut-off memo")]
    assert _state(world)["state"] == PeriodState.CLOSING.value

    # Positive control: the memo signed, the same Controller locks the period; the certification
    # holds the system gates only (a task's evidence is its sign-off).
    rows = _checklist(world, signer)
    shown = _state(world)
    signed = post(
        app,
        f"{PERIODS}/{shown['id']}/checklist/{rows['CUTOFF-MEMO']['id']}/sign",
        signer,
        {"statement_accepted": True},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert signed.status_code == 200, signed.text
    decided = approve(app, request_id, controller)
    assert decided.status_code == 200, decided.text
    assert _state(world)["state"] == PeriodState.CLOSED.value
    certification = _lock_row(world)["certification"]
    assert [row["gate_check_code"] for row in certification] == list(gates.GATE_CHECK_CODES)


def test_approved_waiver_clears_its_gate_for_the_lock(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """SC-N4 / supervisor ruling R-55 (b): a gate waived through an EXCEPTION_WAIVER that another
    user approved no longer refuses the lock request or the lock decision (SCREENS_B SF-05: "The
    gate counts as cleared once another user approves it"); a pending waiver has no effect. The
    lock request's gate result and the lock's certification name the waiver request and both
    counts: what the gate computes at the decision and what it held when the waiver was approved.
    Until this fix the decision read the computed results alone, so an approved waiver never let
    a period lock.

    Item CLO-WAIVER-COVERS-LATER-1 (the supervisor's ruling of 2026-10-02 17:32; 04 T-CLS-03 rev
    1.305): the waiver covers the COUNT it was approved for. A second exception fails the gate
    again, by the sentence that names the waiver; a waiver of what stands is approved at 2; one
    of the two exceptions is then waived itself (SM-06), so the gate computes 1 where its waiver
    covered 2 — the two counts the request's row and the certification still tell apart."""
    app = world.app
    _start_close(world)
    _pass_gates(world)

    def open_exception() -> UUID:
        item = exception_item_values(world.tenant_id, entity_id=world.entity_id)
        with system_session(world) as session:
            session.execute(insert(exception_item).values(**item))
        return UUID(str(item["id"]))

    open_exception()
    refused = _lock_request(world, world.maya)
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    assert _errors(refused) == [("EXCEPTIONS_CLEARED", "Open exceptions: 1")]

    # Maya asks for the waiver. Pending, it changes nothing (and is itself a pending approval).
    gate = _checklist(world, world.maya)["EXCEPTIONS_CLEARED"]
    assert (gate["status"], gate["is_waivable"], gate["result"]["count"]) == ("FAILED", True, 1)
    shown = _state(world)
    waiver = post(
        app,
        f"{PERIODS}/{shown['id']}/checklist/{gate['id']}/waive",
        world.maya,
        {"reason": "Accepted by the controller for this period."},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert waiver.status_code == 200, waiver.text
    waiver_id = str(waiver.json()["approval_request_id"])
    pending = _lock_request(world, world.maya)
    assert (pending.status_code, slug(pending)) == (409, "close-gates-failed"), pending.text
    assert [rule for rule, _ in _errors(pending)] == ["APPROVALS_CLEARED", "EXCEPTIONS_CLEARED"]

    # Another user approves it (exception.waive, fresh TOTP): the item is WAIVED at count 1.
    reviewer_member = colleague(world.tenant_id, "priya")
    assign(reviewer_member, "revenue_reviewer")
    reviewer = enrolled(app, clock, reviewer_member)
    approved = approve(app, waiver_id, reviewer)
    assert approved.status_code == 200, approved.text
    waived = _checklist(world, world.maya)["EXCEPTIONS_CLEARED"]
    assert (waived["status"], waived["waiver_approval_request_id"]) == ("WAIVED", waiver_id)

    # A second exception arrives: the gate counts 2, more than the waiver was approved for, and
    # fails again by the sentence that names the waiver (item CLO-WAIVER-COVERS-LATER-1; 04
    # T-CLS-03 rev 1.305). STALE EXPECTATION by the supervisor's ruling of 2026-10-02 17:32:
    # under R-55 (d) a waiver covered its gate whatever the gate counted afterwards, so this
    # request went through as ("WAIVED", 2, 1) and the period locked over an exception no
    # approver had seen.
    second_item = open_exception()
    outgrown = f"Open exceptions: 2 The waiver {waiver.json()['request_no']} covered 1."
    refused = _lock_request(world, world.maya)
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    assert _errors(refused) == [("EXCEPTIONS_CLEARED", outgrown)]
    failed = _checklist(world, world.maya)["EXCEPTIONS_CLEARED"]
    assert (
        failed["status"],
        failed["result"]["count"],
        failed["result"]["detail"],
        failed["waiver_approval_request_id"],
        failed["is_waivable"],
    ) == ("FAILED", 2, outgrown, None, True)

    # A waiver of what stands, asked and approved: the item is WAIVED at count 2.
    shown = _state(world)
    again = post(
        app,
        f"{PERIODS}/{shown['id']}/checklist/{gate['id']}/waive",
        world.maya,
        {"reason": "Both accepted by the controller for this period."},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert again.status_code == 200, again.text
    waiver_id = str(again.json()["approval_request_id"])
    assert approve(app, waiver_id, reviewer).status_code == 200

    # One of the two exceptions is then waived itself (SM-06; dismissal is refused for input that
    # was committed): a waived item stops counting, so the gate computes 1 where its waiver
    # covered 2 — both counts on the lock request and in the certification.
    item_waiver = post(
        app,
        f"/api/v1/exceptions/{second_item}/request-waiver",
        world.maya,
        {"comment": "Raised a second time for the same calculation."},
    )
    assert item_waiver.status_code == 200, item_waiver.text
    assert approve(app, str(item_waiver.json()["approval_request_id"]), reviewer).status_code == 200
    requested = _lock_request(world, world.maya)
    assert requested.status_code == 200, requested.text
    (at_request,) = [
        row
        for row in requested.json()["gate_results"]
        if row["gate_check_code"] == "EXCEPTIONS_CLEARED"
    ]
    assert (
        at_request["status"],
        at_request["count"],
        at_request["waived_count"],
        at_request["waiver_approval_request_id"],
    ) == ("WAIVED", 1, 2, waiver_id)
    request_id = str(requested.json()["approval_request_id"])
    decided = approve(app, request_id, _controller(app, clock, world.tenant_id))
    assert decided.status_code == 200, decided.text
    assert _state(world)["state"] == PeriodState.CLOSED.value
    certification = {row["gate_check_code"]: row for row in _lock_row(world)["certification"]}
    certified = certification["EXCEPTIONS_CLEARED"]
    assert {key: certified[key] for key in certified if key != "evaluated_at"} == {
        "gate_check_code": "EXCEPTIONS_CLEARED",
        "status": "WAIVED",
        "count": 1,
        "waiver_approval_request_id": waiver_id,
        "waived_count": 2,
    }
    assert set(certification["APPROVALS_CLEARED"]) == {
        "gate_check_code",
        "status",
        "count",
        "evaluated_at",
    }
    assert certification["CONTROLLER_CERTIFIED"]["status"] == "PASSED"
    # Collect the actual approved waiver and decision, not today's mutable checklist result.
    reader = replace(
        world.place.principal,
        permissions=frozenset({"report.run", "audit.read"}),
        permission_scopes={"report.run": "*", "audit.read": "*"},
    )
    with world.place.uow(reader) as uow:
        selection = evidence_selection.resolve(
            uow,
            ClosePackCreateIn.model_validate(
                {
                    "kind": "CLOSE",
                    "entity_code": "AVM-US",
                    "book": "ASC606",
                    "period_key": "FY2026-P09",
                    "period_lock_id": _lock_row(world)["id"],
                }
            ),
        )
        packed = evidence_certification.collect(uow, selection)
        assert evidence_certification.collect(uow, selection) == packed
        proof = json.loads(packed[0].content)
        (saved_waiver,) = proof["waivers"]
        assert saved_waiver["request"]["id"] == waiver_id
        assert (saved_waiver["count"], saved_waiver["waived_count"]) == (1, 2)
        assert saved_waiver["decisions"][0]["decision"] == "APPROVE"
        original = saved_waiver["basis"]["subject"]
        assert sha256_hex(original) == saved_waiver["request"]["subject_content_sha256"]
        assert original["gate_check_code"] == "EXCEPTIONS_CLEARED"
        assert original["count"] == len(original["members"]) == 2
        assert saved_waiver["basis"]["audit_chain_seq"] <= _lock_row(world)["audit_head_chain_seq"]
        assert str(second_item) in " ".join(original["members"])

        valid = {
            "request_id": UUID(proof["lock_approval"]["request"]["id"]),
            "subject_type": "PERIOD_LOCK",
            "subject_id": world.state_id,
            "entity_id": world.entity_id,
            "locked_at": uow.now,
        }
        for mismatch in (
            {"request_id": new_id()},
            {"subject_id": new_id()},
            {"entity_id": new_id()},
            {
                "locked_at": datetime.fromisoformat(proof["lock_approval"]["request"]["decided_at"])
                - timedelta(microseconds=1)
            },
        ):
            with pytest.raises(Problem, match="missing or mismatched"):
                evidence_certification._approval(uow, **{**valid, **mismatch})
        # A valid approval for a different subject must not be relabelled as a lock approval.
        with pytest.raises(Problem, match="missing or mismatched"):
            evidence_certification._approval(
                uow,
                UUID(waiver_id),
                subject_type="PERIOD_LOCK",
                subject_id=world.state_id,
                entity_id=world.entity_id,
                locked_at=uow.now,
            )


def _soft_close(world: CloseWorld, key: str) -> None:
    """``start-close`` alone: the earlier periods stay as they are (``_start_close`` closes
    them)."""
    shown = _state(world, key)
    started = post(
        world.app,
        f"{PERIODS}/{shown['id']}/start-close",
        world.maya,
        {"comment": f"{key} close in progress"},
        if_match=f'"r{shown["row_version"]}"',
    )
    assert started.status_code == 200, started.text


def _lock_requests(world: CloseWorld) -> int:
    """The ``PERIOD_LOCK`` requests of September (the fixture locks of the earlier periods name
    their own period states)."""
    with system_session(world) as session:
        return int(
            session.execute(
                select(func.count())
                .select_from(approval_request)
                .where(
                    approval_request.c.subject_type == "PERIOD_LOCK",
                    approval_request.c.subject_id == world.state_id,
                )
            ).scalar_one()
        )


def test_br_cls_08_lock_request_refused_while_an_earlier_period_is_postable(
    world: CloseWorld,
) -> None:
    """PRD BR-CLS-08 / ERR-65 (supervisor ruling R-6, item CLO-LOCK-ORDER-1; 04 §16.8 rev 1.106).
    September is in soft close with every automatic gate passing, and January to August are still
    open: a posting into one of them would move September's opening balance after its figures
    were frozen. ``request-lock`` answers 409 ``earlier-period-open`` naming the earliest postable
    period, opens no request, and says so before the gates are judged; a period in soft close is
    postable too. Positive control: with every earlier period closed the same request is
    accepted. Until this ruling the request was accepted in every one of these states."""
    _soft_close(world, "FY2026-P09")
    _pass_gates(world)
    refused = _lock_request(world, world.maya)
    assert (refused.status_code, slug(refused)) == (409, "earlier-period-open"), refused.text
    assert refused.json()["detail"] == (
        "Lock Jan 2026 first. An earlier period of AVM-US in book ASC606 is not closed."
    )
    assert refused.json()["errors"] == []
    assert _lock_requests(world) == 0

    # The guard precedes the gates: with the WLD-B blockers open the answer is the same one.
    wld_b(world)
    again = _lock_request(world, world.maya)
    assert (again.status_code, slug(again)) == (409, "earlier-period-open"), again.text
    _clear_blockers(world)

    # January to July closed and August in soft close: August is named.
    earlier_periods_closed(world, before="FY2026-P08")
    _soft_close(world, "FY2026-P08")
    closing = _lock_request(world, world.maya)
    assert (closing.status_code, slug(closing)) == (409, "earlier-period-open"), closing.text
    assert closing.json()["detail"] == (
        "Lock Aug 2026 first. An earlier period of AVM-US in book ASC606 is not closed."
    )
    assert (_lock_requests(world), _state(world)["state"]) == (0, PeriodState.CLOSING.value)

    # Positive control: August closed, September is submitted for lock.
    earlier_periods_closed(world)
    accepted = _lock_request(world, world.maya)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["approval_request_id"]
    assert _lock_requests(world) == 1


def test_br_cls_08_lock_request_never_decides_on_an_earlier_period_that_is_changing(
    world: CloseWorld,
) -> None:
    """04 §16.8 "Chronological lock and opening" (rev 1.106): the earlier state rows are read
    ``FOR SHARE NOWAIT``. While another transaction holds the row of an earlier period for a
    change — a reopen or a lock being decided — the lock request does not wait and does not
    decide on a state about to change: 409 ``lock-conflict``. Once that transaction has ended the
    request reads the settled state."""
    _start_close(world)
    _pass_gates(world)
    august = UUID(str(_state(world, "FY2026-P08")["id"]))
    with system_session(world) as holder:
        held = holder.execute(
            select(period_state.c.state).where(period_state.c.id == august).with_for_update()
        ).scalar_one()
        assert _value(held) == PeriodState.CLOSED.value
        refused = _lock_request(world, world.maya)
        assert (refused.status_code, slug(refused)) == (409, "lock-conflict"), refused.text
        assert _lock_requests(world) == 0
    accepted = _lock_request(world, world.maya)
    assert accepted.status_code == 200, accepted.text


def test_r_62_c_an_approved_waiver_of_a_data_quality_error_lets_the_period_lock(
    world: CloseWorld, clock: FrozenClock
) -> None:
    """Supervisor ruling R-62 (c), item DQ-WAIVER-STICKY-1, on the public path (04 T-IMP-05 rev
    1.106 "Standing waiver"; PRD BR-CLS-01 "exceptions resolved, waived or dismissed"; SM-06). The
    monitors run as the first statement of ``request-lock`` (SC-8) and find a duplicate invoice
    (ERROR): its item holds ``DATA_QUALITY_CLEAR`` and ``EXCEPTIONS_CLEARED``. Once another user
    approves the item's waiver, the next request runs the monitors again, the finding stands
    waived — no second item — and the period is submitted for lock and locked. Until this ruling
    that run raised the finding again as a new OPEN item, so the approved waiver never reached the
    gates."""
    app = world.app
    _start_close(world)
    # The duplicate is in the data before the reconciliations are reviewed: a source invoice
    # recorded after the review would leave it out of date (supervisor ruling R-58 (e)) and a
    # third gate would refuse beside the two this test is about.
    with system_session(world) as session:
        identity_duplicates(session, world, issue_date=date(2026, 9, 3))
    _pass_gates(world)

    def findings() -> list[tuple[UUID, str]]:
        with system_session(world) as session:
            rows = session.execute(
                select(exception_item.c.id, exception_item.c.status)
                .where(exception_item.c.code == "DQ_DUPLICATE_INVOICE")
                .order_by(exception_item.c.created_at, exception_item.c.exception_no)
            ).all()
        return [(UUID(str(found)), _value(status)) for found, status in rows]

    refused = _lock_request(world, world.maya)
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    assert {rule for rule, _ in _errors(refused)} == {"EXCEPTIONS_CLEARED", "DATA_QUALITY_CLEAR"}
    ((item_id, status),) = findings()
    assert status == "OPEN"

    # Maya asks for the item's waiver; Priya (exception.waive, a fresh TOTP) approves it.
    requested = post(
        app,
        f"/api/v1/exceptions/{item_id}/request-waiver",
        world.maya,
        {"comment": "The second copy is a re-send of INV-DUP; billing confirmed one invoice."},
    )
    assert requested.status_code == 200, requested.text
    waiver_id = str(requested.json()["approval_request_id"])
    reviewer_member = colleague(world.tenant_id, "priya")
    assign(reviewer_member, "revenue_reviewer")
    approved = approve(app, waiver_id, enrolled(app, clock, reviewer_member))
    assert approved.status_code == 200, approved.text
    assert findings() == [(item_id, "WAIVED")]

    # The request runs the monitors first: the duplicate is still in the data and stands waived.
    accepted = _lock_request(world, world.maya)
    assert accepted.status_code == 200, accepted.text
    assert findings() == [(item_id, "WAIVED")]
    by_code = {row["gate_check_code"]: row for row in accepted.json()["gate_results"]}
    assert (by_code["DATA_QUALITY_CLEAR"]["status"], by_code["DATA_QUALITY_CLEAR"]["count"]) == (
        "PASSED",
        0,
    )
    assert (by_code["EXCEPTIONS_CLEARED"]["status"], by_code["EXCEPTIONS_CLEARED"]["count"]) == (
        "PASSED",
        0,
    )
    decided = approve(
        app, str(accepted.json()["approval_request_id"]), _controller(app, clock, world.tenant_id)
    )
    assert decided.status_code == 200, decided.text
    assert _state(world)["state"] == PeriodState.CLOSED.value
    assert findings() == [(item_id, "WAIVED")]


@pytest.mark.control("CTL-019")
@pytest.mark.parametrize("nested", [False, True])
def test_failed_completeness_evidence_survives_refused_request(
    world: CloseWorld,
    committed_db: TestDatabase,
    nested: bool,
) -> None:
    _start_close(world)
    before = _state(world)
    if nested:
        with pytest.raises(Problem) as caught, world.place.uow():
            _request_lock(world)
        refused = caught.value
    else:
        refused = _refused_lock(world)
    assert refused.slug == "close-gates-failed"
    assert gates.JE_COMPLETE in {error.rule_id for error in refused.errors}
    after = _state(world)
    assert (after["state"], after["row_version"]) == (before["state"], before["row_version"])
    with system_session(world) as session:
        record = (
            session.execute(
                select(control_execution).where(
                    control_execution.c.control_id == "CTL-019",
                    control_execution.c.run_ref_id == world.state_id,
                )
            )
            .mappings()
            .one()
        )
        assert str(record["result"]) == "FAIL"
        assert record["run_ref_type"] == "PERIOD_STATE"
        assert record["exception_count"] == 1
        assert record["entity_id"] == world.entity_id
        assert record["period_id"] == world.period_id
        assert record["detail"]["gate"] == gates.JE_COMPLETE
        assert record["detail"]["detail"] == gates.RUN_NOT_CALCULATED
        assert (
            session.scalar(
                select(audit_event.c.id).where(
                    audit_event.c.object_id == record["id"],
                    audit_event.c.action == "control_execution.refusal",
                )
            )
            is not None
        )
        assert not session.execute(
            select(period_lock.c.id).where(period_lock.c.period_id == world.period_id)
        ).all()

    # Without tenant context, downgrade still refuses to erase the new evidence scope.
    import importlib

    from erev_api.db import migration_ops
    from sqlalchemy.exc import IntegrityError

    migration = importlib.import_module(
        "erev_api.db.migrations.versions.0141_control_refusal_scope"
    )
    with committed_db.owner_engine.connect() as connection:
        transaction = connection.begin()
        try:
            with (
                migration_ops.bound_to(connection),
                pytest.raises(IntegrityError, match="ck_control_execution__run_ref_type"),
            ):
                migration.downgrade()
        finally:
            transaction.rollback()


@pytest.mark.control("CTL-019")
def test_failed_completeness_at_approval_keeps_decision_pending(
    world: CloseWorld,
    clock: FrozenClock,
) -> None:
    from erev_api.db.tables import gl_account
    from support.close_world import sealed_activity
    from support.rows import gl_account_values

    _start_close(world)
    _pass_gates(world)
    request_id, _ = _request_lock(world)
    before = _state(world)
    with system_session(world) as session:
        account = gl_account_values(world.tenant_id, code="7770")
        session.execute(insert(gl_account).values(**account))
        sealed_activity(
            session,
            world,
            account=account,
            period_id=world.period_id,
            period_end_date=date(2026, 9, 30),
            amounts=[Decimal("100"), Decimal("-100")],
        )
    decided = approve(world.app, str(request_id), _controller(world.app, clock, world.tenant_id))
    assert (decided.status_code, slug(decided)) == (409, "close-gates-failed"), decided.text
    assert gates.JE_COMPLETE in {error["rule_id"] for error in decided.json()["errors"]}
    after = _state(world)
    assert (after["state"], after["row_version"]) == (before["state"], before["row_version"])
    with system_session(world) as session:
        record = (
            session.execute(
                select(control_execution).where(
                    control_execution.c.control_id == "CTL-019",
                    control_execution.c.run_ref_id == world.state_id,
                )
            )
            .mappings()
            .one()
        )
        assert str(record["result"]) == "FAIL" and record["exception_count"] > 0
        assert (
            _value(
                session.scalar(
                    select(approval_request.c.status).where(approval_request.c.id == request_id)
                )
            )
            == "PENDING"
        )
        assert not session.execute(
            select(approval_decision.c.id).where(
                approval_decision.c.approval_request_id == request_id
            )
        ).all()
        assert not session.execute(
            select(period_lock.c.id).where(period_lock.c.period_id == world.period_id)
        ).all()


@pytest.mark.control("CTL-019")
def test_refusal_evidence_write_failure_never_commits_business_or_partial_evidence(
    world: CloseWorld,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from erev_api.controls.evidence import ControlRefusal

    _start_close(world)
    before = _state(world)
    retain = ControlRefusal.retain

    def fail_after_insert(refused: ControlRefusal, uow: Any) -> None:
        retain(refused, uow)
        raise RuntimeError("evidence persistence unavailable")

    monkeypatch.setattr(ControlRefusal, "retain", fail_after_insert)
    with pytest.raises(RuntimeError, match="evidence persistence unavailable"):
        _request_lock(world)
    after = _state(world)
    assert (after["state"], after["row_version"]) == (before["state"], before["row_version"])
    with system_session(world) as session:
        assert not session.execute(
            select(control_execution.c.id).where(
                control_execution.c.control_id == "CTL-019",
                control_execution.c.run_ref_id == world.state_id,
            )
        ).all()
        assert not session.execute(
            select(audit_event.c.id).where(
                audit_event.c.action == "control_execution.refusal",
            )
        ).all()
        assert not session.execute(
            select(period_lock.c.id).where(
                period_lock.c.period_id == world.period_id,
            )
        ).all()


@pytest.mark.control("CTL-025")
@pytest.mark.parametrize("chain_position", [None, 0], ids=["legacy-time", "sealed-position"])
@pytest.mark.parametrize(
    ("posting_month", "posting_book", "other_entity", "expected"),
    [
        (7, "ASC606", False, {"SUBLEDGER_TO_GL"}),
        (8, "ASC606", False, {"SUBLEDGER_TO_GL", "BILLING_TO_SUBLEDGER"}),
        (9, "ASC606", False, set()),
        (7, "IFRS15", False, set()),
        (7, "ASC606", True, set()),
    ],
)
def test_reconciliation_freshness_covers_ledger_history(
    world: CloseWorld,
    chain_position: int | None,
    posting_month: int,
    posting_book: str,
    other_entity: bool,
    expected: set[str],
) -> None:
    """A later seal in earlier history invalidates GL only; future/other-book seals do not."""
    from calendar import monthrange

    from erev_api.db import transitions
    from erev_api.db.tables import gl_account, period
    from erev_api.enums import BookCode
    from support.close_world import sealed_activity
    from support.factories import open_periods
    from support.reference import entity
    from support.rows import gl_account_values, period_state_values, reconciliation_values

    with system_session(world) as session:
        target_period = session.scalar(
            select(period.c.id).where(period.c.end_date == date(2026, 8, 31))
        )
        assert target_period is not None
        for kind in ("SUBLEDGER_TO_GL", "BILLING_TO_SUBLEDGER"):
            row = reconciliation_values(
                world.tenant_id,
                entity_id=world.entity_id,
                period_id=target_period,
                kind=kind,
                ledger_chain_seq=chain_position,
                as_of_known_at=world.place.clock.now() - timedelta(days=1),
            )
            session.execute(insert(reconciliation).values(**row))
            transitions.apply(
                session,
                "reconciliation",
                row["id"],
                to_status="PREPARED",
                expected_status="DRAFT",
                set_values={},
            )
            transitions.apply(
                session,
                "reconciliation",
                row["id"],
                to_status="REVIEWED",
                expected_status="PREPARED",
                set_values={},
            )
    posting_world = world
    if other_entity:
        with system_session(world) as session:
            calendar_id = session.scalar(
                select(period.c.calendar_id).where(period.c.id == target_period)
            )
        created = entity(world.app, world.maya, code="OTHER", calendar_id=str(calendar_id))
        open_periods(
            world.app,
            world.maya,
            entity_code="OTHER",
            keys=[f"FY2026-P{m:02d}" for m in range(1, 8)],
        )
        posting_world = replace(world, entity_id=UUID(created["id"]))
    with system_session(world) as session:
        scope = gates.scope_of_period(session, world.entity_id, "ASC606", target_period)
        assert scope is not None
        assert not session.scalars(
            select(reconciliation.c.kind).where(gates.overtaken(scope))
        ).all()
        end = date(2026, posting_month, monthrange(2026, posting_month)[1])
        posting_period = session.scalar(select(period.c.id).where(period.c.end_date == end))
        assert posting_period is not None
        if posting_book != "ASC606":
            session.execute(
                insert(period_state).values(
                    **period_state_values(
                        world.tenant_id,
                        entity_id=world.entity_id,
                        period_id=posting_period,
                        period_end_date=end,
                        book_code=BookCode(posting_book),
                        state="open",
                    )
                )
            )
        account = gl_account_values(world.tenant_id, code="7771")
        session.execute(insert(gl_account).values(**account))
        offset = gl_account_values(world.tenant_id, code="7772")
        session.execute(insert(gl_account).values(**offset))
        sealed_activity(
            session,
            posting_world,
            account=account,
            period_id=posting_period,
            period_end_date=end,
            amounts=[Decimal("100")],
            offset_account=offset,
            book_code=posting_book,
            recorded_at=world.place.clock.now(),
        )
    with system_session(world) as session:
        actual = session.scalars(select(reconciliation.c.kind).where(gates.overtaken(scope))).all()
        assert {str(kind) for kind in actual} == expected
        assert gates.blocker_counts(session, scope)["reconciliations_unsigned"] == len(expected)


def _close_for_population(
    world: CloseWorld, clock: FrozenClock, *, waive_missing: bool
) -> tuple[Mapping[str, Any], str | None]:
    waiver_id = None
    _start_close(world)
    if waive_missing:
        acknowledged_run(world)
        with system_session(world) as session:
            close_run_succeeded(session, world)
        gate = _checklist(world, world.maya)["RECONCILIATIONS_GENERATED"]
        assert gate["result"]["count"] == 2
        shown = _state(world)
        response = post(
            world.app,
            f"{PERIODS}/{shown['id']}/checklist/{gate['id']}/waive",
            world.maya,
            {"reason": "Both missing statements accepted for this test close."},
            if_match=f'"r{shown["row_version"]}"',
        )
        assert response.status_code == 200, response.text
        waiver_id = response.json()["approval_request_id"]
        member = colleague(world.tenant_id, "population-reviewer")
        assign(member, "revenue_reviewer")
        response = approve(world.app, waiver_id, enrolled(world.app, clock, member))
        assert response.status_code == 200, response.text
    else:
        _pass_gates(world)
    requested = _lock_request(world, world.maya)
    assert requested.status_code == 200, requested.text
    approved = approve(
        world.app,
        requested.json()["approval_request_id"],
        _controller(world.app, clock, world.tenant_id),
    )
    assert approved.status_code == 200, approved.text
    lock = _lock_row(world)
    return lock, waiver_id


@pytest.mark.parametrize("waive_missing", [False, True])
def test_close_pack_reconciliation_population_has_required_statements_or_exact_waiver(
    world: CloseWorld, clock: FrozenClock, waive_missing: bool
) -> None:
    lock, waiver_id = _close_for_population(world, clock, waive_missing=waive_missing)
    reader = replace(
        world.place.principal,
        permissions=frozenset({"report.run", "audit.read", "contract.read"}),
        permission_scopes={"report.run": "*", "audit.read": "*", "contract.read": "*"},
    )
    with world.place.uow(reader) as uow:
        selected = evidence_selection.resolve(
            uow,
            ClosePackCreateIn.model_validate(
                {
                    "kind": "CLOSE",
                    "entity_code": "AVM-US",
                    "book": "ASC606",
                    "period_key": "FY2026-P09",
                    "period_lock_id": lock["id"],
                }
            ),
        )
        files = evidence_reconciliation_population.collect(uow, selected)
        assert evidence_reconciliation_population.collect(uow, selected) == files
        assert files[0].path == "reconciliations/population.json"
        population = json.loads(files[0].content)
        assert population["policy"]["value"] is True
        assert set(population["required_kinds"]) == set(gates.REQUIRED_KINDS)
        if waive_missing:
            assert population["certified"] == []
            assert set(population["waived_absent_kinds"]) == set(gates.REQUIRED_KINDS)
            assert population["waiver"]["request"]["id"] == waiver_id
            assert set(population["waiver"]["basis"]["subject"]["members"]) == {
                f"reconciliation:{kind}:missing" for kind in gates.REQUIRED_KINDS
            }
        else:
            assert {row["kind"] for row in population["certified"]} == set(gates.REQUIRED_KINDS)
            assert population["waived_absent_kinds"] == []
            assert population["waiver"] is None
    # Seed a later published policy through the normal registry state transitions. This is
    # historical-reader evidence, not an end-to-end configuration-publication witness.
    clock.set(lock["cutoff_known_at"] + timedelta(seconds=1))
    with system_session(world) as session:
        publish_registry_version(
            session,
            tenant_id=world.tenant_id,
            category=RegistryCategory.CLOSE,
            values={gates.REQUIRE_RECONCILIATIONS: False},
            at=clock.now(),
        )
    with world.place.uow(reader) as uow:
        assert (
            resolve_setting(
                uow.session,
                gates.REQUIRE_RECONCILIATIONS,
                book_code=BookCode.ASC606,
                entity_id=world.entity_id,
                known_at=uow.now,
            ).value
            is False
        )
        assert evidence_reconciliation_population.collect(uow, selected) == files
    denied = replace(
        reader, permission_scopes={**reader.permission_scopes, "contract.read": frozenset()}
    )
    with world.place.uow(denied) as uow, pytest.raises(Problem) as error:
        evidence_reconciliation_population.collect(uow, selected)
    assert error.value.slug == "not-found"


@pytest.mark.parametrize("waive_missing", [False, True])
def test_first_close_archive_verifies_every_component_before_returning_bytes(
    world: CloseWorld,
    clock: FrozenClock,
    waive_missing: bool,
) -> None:
    """Real close/waiver approval and source jobs; journal/close-run gate setup is seeded."""
    lock, waiver_id = _close_for_population(world, clock, waive_missing=waive_missing)
    clock.set(lock["cutoff_known_at"] + timedelta(seconds=1))
    with world.place.uow() as uow:
        verification = audit_verify.record_tenant_verification(
            uow, trigger="ON_DEMAND", job_id=None
        )
        verification_id = verification["id"]
        uow.commit()
    permissions = frozenset(
        {"report.run", "report.export", "audit.read", "contract.read", "evidence.export"}
    )
    reader = replace(
        world.place.principal,
        permissions=permissions,
        permission_scopes={permission: "*" for permission in permissions},
    )
    request = ClosePackCreateIn.model_validate(
        {
            "kind": "CLOSE",
            "entity_code": "AVM-US",
            "book": "ASC606",
            "period_key": "FY2026-P09",
            "period_lock_id": lock["id"],
        }
    )
    with world.place.uow(reader) as uow:
        bound = evidence_sources.prepare_close(uow, request, verification_id=verification_id)
        pack = evidence_pack_values(world.tenant_id, **bound.pack_values(), created_at=uow.now)
        parent = uow.defer(
            JobKind.EVIDENCE_PACK,
            {"evidence_pack_id": str(pack["id"])},
            subject_type="evidence_pack",
            subject_id=pack["id"],
        )
        pack["job_id"] = parent["id"]
        uow.session.execute(insert(evidence_pack).values(**pack))
        uow.commit()
    with world.place.uow(reader) as uow, pytest.raises(Problem) as error:
        evidence_assembly.assemble_close(uow, pack["id"])
    if not waive_missing:
        # The gate fixture marked rows REVIEWED without real signatures. Assembly must
        # reject those rows even though their population and saved close gate pass.
        assert "distinct preparer" in error.value.detail
        return
    assert "supporting report differs" in error.value.detail
    with world.place.uow(reader) as uow:
        assert not evidence_readiness.close_ready(uow.session, parent["id"], parent["params"])
    # Readiness rejects terminal children and contradictory job/report states. These
    # legal state transitions are rolled back after each fault so the real workers can run.
    source = bound.supporting_reports[0]
    for terminal in ("FAILED", "CANCELLED", "SUCCEEDED"):
        with world.place.uow(reader) as uow:
            apply(
                uow.session,
                "job",
                source.job_id,
                to_status="RUNNING",
                expected_status="QUEUED",
                set_values={},
            )
            apply(
                uow.session,
                "job",
                source.job_id,
                to_status=terminal,
                expected_status="RUNNING",
                set_values={},
            )
            with pytest.raises(Problem) as refused:
                evidence_readiness.close_ready(uow.session, parent["id"], parent["params"])
            assert refused.value.slug == "validation-failed"
    with world.place.uow(reader) as uow:
        apply(
            uow.session,
            "report_run",
            source.run_id,
            to_status="FAILED",
            expected_status="QUEUED",
            set_values={},
        )
        with pytest.raises(Problem, match="failed or was cancelled"):
            evidence_readiness.close_ready(uow.session, parent["id"], parent["params"])
    with world.place.uow(reader) as uow:
        with pytest.raises(Problem, match="does not match"):
            evidence_readiness.close_ready(uow.session, source.job_id, parent["params"])
        with pytest.raises(Problem, match="no valid pack id"):
            evidence_readiness.close_ready(uow.session, parent["id"], {})
    with world.place.uow(reader) as uow, pytest.raises(Problem, match="Only a running"):
        evidence_storage.finish_close(uow, pack["id"])
    with world.place.uow(reader) as uow:
        apply(
            uow.session,
            "evidence_pack",
            pack["id"],
            to_status="RUNNING",
            expected_status="QUEUED",
            set_values={},
        )
        uow.commit()
    with world.place.uow(reader) as uow, pytest.raises(Problem, match="supporting report differs"):
        evidence_storage.finish_close(uow, pack["id"])
    for report in bound.supporting_reports:
        finished = run_journal_job(world, report.job_id, attempts=1)
        assert finished["state"] == "SUCCEEDED", finished
    with world.place.uow(reader) as uow:
        assert evidence_readiness.close_ready(uow.session, parent["id"], parent["params"])
        archive = evidence_assembly.assemble_close(uow, pack["id"])
        assert evidence_assembly.assemble_close(uow, pack["id"]) == archive
    manifest = evidence_archive.verify(
        archive.content, expected_manifest_sha256=archive.manifest_sha256
    )
    assert len(manifest["files"]) == 36
    with ZipFile(io.BytesIO(archive.content)) as opened:
        assert set(opened.namelist()) == {row["path"] for row in manifest["files"]} | {
            "manifest.json"
        }
        for row in manifest["files"]:
            content = opened.read(row["path"])
            assert hashlib.sha256(content).hexdigest() == row["sha256"]
            assert len(content) == row["bytes"]
        population = json.loads(opened.read("reconciliations/population.json"))
        assert set(population["waived_absent_kinds"]) == set(gates.REQUIRED_KINDS)
        assert population["waiver"]["request"]["id"] == waiver_id
        journals = json.loads(opened.read("journals/batch_register.json"))
        assert journals["batches"] and all(row["balanced"] for row in journals["batches"])
        assert opened.read("journals/je_population.csv").count(b"\n") > 1
        saved = json.loads(opened.read("lock/source_binding.json"))
        assert saved == bound.model_dump(mode="json")
        audit = json.loads(opened.read("audit/sources.json"))
        assert audit["verification_id"] == str(verification_id)
    # Permission is checked again on every assembly; no successful cached ZIP bypass.
    for permission in ("report.export", "audit.read", "contract.read"):
        denied = replace(reader, permissions=reader.permissions - {permission})
        with world.place.uow(denied) as uow, pytest.raises(Problem) as error:
            evidence_assembly.assemble_close(uow, pack["id"])
        assert error.value.slug == "forbidden"

    # Output/file row and success are one transaction; an interrupted completion leaves neither.
    with world.place.uow(reader) as uow:
        before_files = uow.session.scalar(select(func.count()).select_from(file_object))
    with world.place.uow(reader) as uow, pytest.raises(RuntimeError, match="rollback witness"):
        retained = evidence_storage.finish_close(uow, pack["id"])
        assert retained.archive == archive
        raise RuntimeError("rollback witness")
    with world.place.uow(reader) as uow:
        saved = (
            uow.session.execute(select(evidence_pack).where(evidence_pack.c.id == pack["id"]))
            .mappings()
            .one()
        )
        assert (saved["status"], saved["file_id"], saved["manifest"]) == ("RUNNING", None, None)
        assert uow.session.scalar(select(func.count()).select_from(file_object)) == before_files
        retained = evidence_storage.finish_close(uow, pack["id"])
        uow.commit()
    with world.place.uow(reader) as uow:
        assert evidence_storage.finish_close(uow, pack["id"]) == retained
        metadata, stream = open_file(
            uow.session, retained.file_id, files=uow.files, keyring=uow.keyring
        )
        with stream:
            assert stream.read() == archive.content
        assert metadata["purpose"] == "EVIDENCE_PACK"
        assert uow.session.scalar(select(func.count()).select_from(file_object)) == before_files + 1
        finishes = uow.session.scalar(
            select(func.count())
            .select_from(audit_event)
            .where(audit_event.c.action == "evidence.finish", audit_event.c.object_id == pack["id"])
        )
        assert finishes == 1
    for permission in permissions:
        denied = replace(reader, permissions=reader.permissions - {permission})
        with world.place.uow(denied) as uow, pytest.raises(Problem) as error:
            evidence_storage.finish_close(uow, pack["id"])
        assert error.value.slug == "forbidden"
