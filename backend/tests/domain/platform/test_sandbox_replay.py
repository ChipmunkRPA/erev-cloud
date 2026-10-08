"""SNP-2 period replay through the governed close path (05 §10 SBX-04; 04 DB-07, T-CLS-04, D-98
61; D-98 candidate 137 amendment 3 — Codex production-20260921-1623 §1 PERIOD-1 / REPLAY-2 /
LOCK-3). DB-bound, lane F-SNP, written without a database; first measured in a lane database by
lane FIX-D1 (2026-09-29), which added the row-for-row copy witness at the end of the module.

The source's lock chain is written directly (the sanctioned precedent of ``tests/domain/close/
test_gates.py::_lock`` and ``test_reopen.py::_lock_by_writer``), exported through the registered
``TENANT_SNAPSHOT`` job as real JSONL, and REPLAYED by the loader through the close domain's
commands with the copied approval evidence — nothing is monkeypatched. ``test_replay_reaches_the_
source_lock_chain`` is the acceptance of the FINISHED path and is pinned ``xfail(strict=True)``
by supervisor ruling R-10 (2026-09-29) until SNP-2b "sandbox-side close replay" lands: measured
in a lane database (lane FIX-D1), the first ``LOCK`` of the replay is refused ``close-gates-
failed`` by FOUR gates — ``BATCHES_ACKNOWLEDGED``, ``JE_BALANCED``, ``JE_COMPLETE`` and
``RECONCILIATIONS_GENERATED`` — because the sandbox has no calculated journal run of its own, no
acknowledged batch and no reconciliation (none is copied, all are REGENERATED), i.e. it needs
CLO-14, CLO-16 / CLO-17 and the close run of CLO-19 / CLO-20. The docstring's earlier prediction
(green once CLO-10's ``JE_COMPLETE`` evaluated) was wrong. What the same world reaches today is
``test_replay_on_the_k01_chain_restores_everything_the_sandbox_can_reach``, and the governed
behaviour until SNP-2b is 05 SBX-04's blocked path (D-98 137 (3)), witnessed by
``test_replay_refused_by_a_gate_is_a_warning``: an open BLOCKING exception of the entity makes
``EXCEPTIONS_CLEARED`` fail, so the lock is refused by name (``close-gates-failed``), the period
stays ``closing`` and the load SUCCEEDS with the ``SANDBOX_REPLAY_BLOCKED`` warning (ruling (3);
IMP-116).

D-98 137 amendment 4 (Codex production-20260921-1713 §3): the source's approval evidence is
built through the LIVE decision guard (a PENDING request and an ACTIVE step take the decisions,
then the DB-03 kernel applies the permitted finalization — R2) and the loader restores the
finalized graph the same governed way (``snapshot_dataset.FINALIZATIONS`` — R3: the sandbox's
requests are APPROVED with their decided_at, the steps APPROVED, every decision present by id);
the lock chain and the recompute witness live on ``support.worlds.k01_pellworth`` — Pellworth's
activated, billed and computed contract — so the recompute runs on OPEN sandbox periods with a
real posting target (R1: the computation SUCCEEDS with the ``MIGRATION`` trigger, its schedule
lines exist in the sandbox, no group is left un-recomputed, ``derived_mismatches = 0``) BEFORE the
close replay. Postings of the subledger are released by the journal run, not by the recompute;
the witness asserts the computed schedule and the SUCCEEDED computation — the posting targets
CV-13 refused while the periods were absent.

D-98 137 amendment 5 (Codex production-20260921-1739 §1–§2): the loader restores approval graphs
root by root in submission order (APPROVAL-UNIQUE-1: the lock and the re-lock of one period state
are never PENDING together under ``ux_approval_request__pending_subject``) and the witness compares
the restored graphs EXACTLY with the source (every column but the remapped tenant); the recompute
witness asserts that the recompute is THIS load's (WITNESS-1 — by the request id of its audit
event: 04 NC-06 leaves no ``job_id`` a sandbox row could carry, supervisor ruling R-8), the exact
source period-state ids and states
(WITNESS-2: nine opened FY2026 periods, January closed with its re-lock where the chain applies,
every other row ``future`` — never a subset); the source record-time timeline is world → chain →
cutoff (WITNESS-3).

D-98 137 amendment 6 (Codex production-20260921-1757 §1–§2): a copied membership that ended
SUSPENDED / REMOVED loads in its activation state so the approver's historical decisions pass the
live 0013 guard, and its final status is applied after the approval graphs (MEMBERSHIP-1 —
``test_suspended_approver_s_decision_is_restored``); the shared injected clock advances to the
cutoff before every dispatch (WITNESS-3 residual).

D-98 137 amendment 7 (Codex production-20260921-1824 §1): a finalized membership row carries the
sandbox's own DB-02 stamps — the exact comparison excludes ``updated_at`` and ``row_version`` by
name and asserts ``row_version`` = source + 1 and a later ``updated_at`` (STAMPS-1); a supported
refusal after the membership load settles the held final statuses before it returns
(``test_refusal_after_the_membership_load_leaves_no_member_reactivated``; REFUSAL-1).
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import ModuleType
from typing import Any
from uuid import UUID

import erev_engine
import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db import transitions as tx
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    approval_step,
    audit_event,
    contract_computation,
    contract_event,
    contract_version,
    entity_book,
    exception_item,
    fiscal_calendar,
    legal_entity,
    metadata,
    notification,
    obligation_version,
    period,
    period_lock,
    period_state,
    period_state_transition,
    schedule_line,
    security_event,
    subledger_line,
    tenant_membership,
    tenant_snapshot,
)
from erev_api.domain.contracts import computation, compute_job
from erev_api.domain.imports import exceptions
from erev_api.domain.platform import sandbox_periods as sp
from erev_api.domain.platform import sandboxes as sb
from erev_api.domain.platform import snapshot_dataset as sd
from erev_api.domain.platform import snapshot_export as sx
from erev_api.enums import (
    ApprovalRequestStatus,
    ApprovalSubjectType,
    ComputationStatus,
    ContractEventType,
    JobKind,
    LockKind,
    PeriodState,
)
from erev_api.events.payloads import BillingRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore, open_file
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime, system_unit_of_work
from erev_api.main import create_app
from erev_api.money import MoneyIn
from erev_api.problems import Problem
from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.errors import EngineError
from fastapi import FastAPI
from perf.support import sandbox as perf_sandbox
from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session
from support.clock import FROZEN_AT
from support.db import TestDatabase
from support.factories import (
    K02_EXTERNAL_ID,
    appended,
    booked_contract,
    computed,
    customer_id,
    k02_seat_month_body,
    stamp_test_release,
)
from support.principals import Member, colleague, enrolled, member
from support.reference import approve, assign, get, periods, post
from support.rows import (
    approval_decision_values,
    approval_request_values,
    entity_book_values,
    exception_item_values,
    fiscal_calendar_values,
    insert_approval_step,
    legal_entity_values,
    period_state_transition_values,
    period_values,
    tenant_snapshot_values,
)
from support.snapshots import (
    confirm_retention,
    cutoff_after,
    enter_workspace,
    load_chain,
    load_outcome,
    run_dispatched_snapshot,
    unexplained_load_events,
)
from support.worlds import K01, ReportWorld, estimate_version_ready, k01_events, k01_pellworth

# WITNESS-3 (Codex 1739 §2): the source record-time timeline is the world FIRST (the product's
# own rows at the frozen clock), THEN the close / approval / MFA chain, THEN the snapshot cutoff —
# so the planner's (created_at, id) order and the export cutoffs hold without weakening either.
# The cutoff is not a constant: a world lives on two clocks — the frozen application clock, and
# the database's real one, which stamps DB-08 ``recorded_at`` and the defaulted ``created_at`` of
# every directly inserted row (calendars, entities, memberships, approval requests) LATER than
# any instant of the frozen timeline — so ``_copy`` takes ``known_at`` from the database once the
# world and its chain are complete (``support.snapshots.cutoff_after``). A cutoff on the frozen
# timeline cuts those rows, and the rows that reference them, out of the snapshot (ruling Q-6).
T0 = FROZEN_AT + timedelta(minutes=10)  # the source's close of FY2026-P01 starts here
RETENTION_FROM = FROZEN_AT - timedelta(days=1)  # the retention confirmation, in force before T0
LOCK_COMMENT = "January 2026 close complete and certified"
REOPEN_COMMENT = "Late invoice correction for January 2026"
BOOK = "ASC606"


@pytest.fixture
def job() -> Iterator[ModuleType]:
    """The handler module, registered for the test, with the engine release stamped as the worker's
    startup stamps it (05 REL-03): an unstamped process refuses to export, and the autouse conftest
    fixture forgets the stamp after every test (05 REL-05) — so the stamp is per test, the shape of
    ``test_snapshots.py``."""
    from erev_api.domain.platform import snapshot_job

    stamp_test_release()
    present = JobKind.TENANT_SNAPSHOT in registry.HANDLERS  # the worker registers it (DG-ARC-08)
    if not present:
        registry.HANDLERS[JobKind.TENANT_SNAPSHOT] = registry.HandlerSpec(
            handler=snapshot_job.tenant_snapshot_export,
            retry=snapshot_job.SNAPSHOT_RETRY,
            on_failure=snapshot_job.snapshot_failed,
        )
    yield snapshot_job
    if not present:
        registry.HANDLERS.pop(JobKind.TENANT_SNAPSHOT, None)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


@dataclass(frozen=True, slots=True)
class Chain:
    """The source's FY2026-P01 lock chain and its identities."""

    admin: Member
    cora: Member
    priya: Member
    entity_id: UUID
    january_state_id: UUID
    february_state_id: UUID
    january_id: UUID
    transitions: dict[str, UUID]  # by pair, e.g. "closing>closed#2"
    lock_id: UUID
    reopen_id: UUID
    relock_id: UUID
    requests: tuple[UUID, ...]  # the three approval requests (lock, reopen, re-lock)
    group_id: UUID | None = None  # Pellworth's combination group when the chain is on the k01 world
    requester: Member | None = None  # the sandbox requester when not the admin


def _approved(
    session: Session,
    tenant_id: UUID,
    *,
    subject_type: ApprovalSubjectType,
    state_id: UUID,
    entity_id: UUID,
    preparer: Member,
    approvers: list[Member],
    at: datetime,
    comment: str,
    reason_code: str | None = None,
) -> UUID:
    """A request of ``preparer`` APPROVED by ``approvers`` at ``at`` — built the way the source
    engine builds it, under the LIVE 0013 decision guard (R2): the request is inserted PENDING
    with its step ACTIVE, each APPROVE decision (the approver's MFA verified at the decision) is
    inserted while they are, then the permitted finalization goes through the DB-03 kernel — the
    step ``ACTIVE → APPROVED`` with ``completed_at``, the request ``PENDING → APPROVED`` with
    ``decided_at``. Never a bypassed or removed guard."""
    request = approval_request_values(
        tenant_id,
        status=ApprovalRequestStatus.PENDING,
        preparer_id=preparer.user_id,
        subject_id=state_id,
        entity_id=entity_id,
        subject_type=subject_type.value,
        summary=f"{subject_type.value} of the January period",
        comment=comment,
        reason_code=reason_code,
        submitted_at=at - timedelta(minutes=10),
    )
    session.execute(insert(approval_request).values(**request))
    request_id = UUID(str(request["id"]))
    step_id = insert_approval_step(
        session,
        tenant_id=tenant_id,
        approval_request_id=request_id,
        activated_at=at - timedelta(minutes=10),
        min_approvers=len(approvers),
    )
    for offset, approver in enumerate(approvers):
        decided = at - timedelta(minutes=len(approvers) - offset - 1)
        session.execute(
            insert(approval_decision).values(
                **approval_decision_values(
                    tenant_id,
                    approval_request_id=request_id,
                    approval_step_id=step_id,
                    approver_id=approver.user_id,
                    mfa_verified_at=decided - timedelta(seconds=30),
                    decided_at=decided,
                    comment="OK",
                )
            )
        )
    tx.apply(
        session,
        "approval_step",
        step_id,
        to_status="APPROVED",
        set_values={"completed_at": at},
        expected_status="ACTIVE",
    )
    tx.apply(
        session,
        "approval_request",
        request_id,
        to_status="APPROVED",
        set_values={"decided_at": at},
        expected_status="PENDING",
    )
    return request_id


def _transition(
    session: Session,
    tenant_id: UUID,
    *,
    state_id: UUID,
    entity_id: UUID,
    period_id: UUID,
    pair: tuple[str | None, str],
    at: datetime,
    actor: Member,
    approval_request_id: UUID | None = None,
    lock: dict[str, Any] | None = None,
    reason_code: str | None = None,
) -> UUID:
    """One DB-07 step of the source, written directly: the lock row first (the deferred key),
    then the transition, then the state — the order ``close.commands._persist_lock`` uses.
    ``reason_code`` is the transition's (T-REF-07: required for ``closing → open``, ``closing →
    reopened`` and ``closed → reopened``; a missing one is refused since revision 0113)."""
    from_state, to_state = pair
    transition = period_state_transition_values(
        tenant_id,
        period_state_id=state_id,
        entity_id=entity_id,
        period_id=period_id,
        from_state=from_state,
        to_state=to_state,
        created_at=at,
        created_by=actor.user_id,
        created_by_kind="USER",
        approval_request_id=approval_request_id,
        period_lock_id=None if lock is None else lock["id"],
        reason_code=reason_code,
        comment=f"{from_state} → {to_state} in the source",
    )
    if lock is not None:
        # 04 T-CLS-04 rev 1.113 (supervisor ruling R-40 (c)): a LOCK row names the cutoff its
        # datasets are frozen at — here the source decision's instant; no other kind carries one
        cutoff = at if lock["kind"] == LockKind.LOCK.value else None
        session.execute(
            insert(period_lock).values(
                **{
                    **lock,
                    "period_state_transition_id": transition["id"],
                    "created_at": at,
                    "cutoff_known_at": cutoff,
                }
            )
        )
    session.execute(insert(period_state_transition).values(**transition))
    moved: dict[str, Any] = {
        "state": to_state,
        "state_changed_at": at,
        "updated_at": at,
        "updated_by": actor.user_id,
        "updated_by_kind": "USER",
    }
    if lock is not None:
        moved["current_lock_id"] = lock["id"]
    if from_state is not None:
        session.execute(update(period_state).where(period_state.c.id == state_id).values(**moved))
    return UUID(str(transition["id"]))


def _lock_values(
    tenant_id: UUID,
    *,
    kind: LockKind,
    entity_id: UUID,
    period_id: UUID,
    approval_request_id: UUID,
    actor: Member,
    previous_lock_id: UUID | None,
    comment: str,
    reason_code: str | None = None,
) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "kind": kind.value,
        "entity_id": entity_id,
        "book_code": BOOK,
        "period_id": period_id,
        "approval_request_id": approval_request_id,
        "reason_code": reason_code,
        "comment": comment,
        "certification": [],
        "ledger_head_chain_seq": 0,
        "ledger_head_sha256": None,
        "audit_head_chain_seq": 0,
        "audit_head_hmac": None,
        "snapshot_manifest_sha256": None,
        "previous_lock_id": previous_lock_id,
        "diff_report_file_id": None,
        "created_by": actor.user_id,
        "created_by_kind": "USER",
    }


def _chain(keyring: KeyRing, clock: FrozenClock) -> Chain:
    """A production tenant whose admin is a Controller (``period.close``; the sandbox requester),
    two more Controllers (the approvers), a January calendar with two periods and one entity keeping
    ASC606 from January. January: NULL → future → open → closing → closed (LOCK by cora) →
    reopened (REOPEN by cora and priya, ERROR_CORRECTION) → closing → closed (LOCK, previous =
    the REOPEN). February: NULL → future → open. Written directly (precedent named in the module
    docstring); every transition has its own ``created_at`` so the export orders them."""
    admin = member(keyring, clock)
    assign(admin, "controller")
    cora, priya = colleague(admin.tenant_id, "cora"), colleague(admin.tenant_id, "priya")
    assign(cora, "controller")
    assign(priya, "controller")
    tenant_id = admin.tenant_id
    transitions: dict[str, UUID] = {}
    with tenant_session(_context(tenant_id)) as session:
        confirm_retention(session, tenant_id, at=RETENTION_FROM)
        calendar = fiscal_calendar_values(tenant_id)
        session.execute(insert(fiscal_calendar).values(**calendar))
        january = period_values(tenant_id, calendar_id=calendar["id"])
        february = period_values(
            tenant_id,
            calendar_id=calendar["id"],
            period_no=2,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
        )
        session.execute(insert(period).values(**january))
        session.execute(insert(period).values(**february))
        entity = legal_entity_values(tenant_id, calendar_id=calendar["id"])
        session.execute(insert(legal_entity).values(**entity))
        entity_id = UUID(str(entity["id"]))
        session.execute(
            insert(entity_book).values(
                **entity_book_values(tenant_id, entity_id=entity_id, first_period_id=january["id"])
            )
        )
        states: dict[str, UUID] = {}
        for key, row in (("january", january), ("february", february)):
            state_id = new_id()
            states[key] = state_id
            session.execute(
                insert(period_state).values(
                    tenant_id=tenant_id,
                    id=state_id,
                    entity_id=entity_id,
                    book_code=BOOK,
                    period_id=row["id"],
                    period_end_date=row["end_date"],
                    state="future",
                    state_changed_at=FROZEN_AT + timedelta(minutes=1),
                    updated_at=FROZEN_AT + timedelta(minutes=1),
                    updated_by=admin.user_id,
                    updated_by_kind="USER",
                )
            )
            at = FROZEN_AT + timedelta(minutes=1)
            transitions[f"{key}:>future"] = _transition(
                session,
                tenant_id,
                state_id=state_id,
                entity_id=entity_id,
                period_id=UUID(str(row["id"])),
                pair=(None, "future"),
                at=at,
                actor=admin,
            )
            transitions[f"{key}:future>open"] = _transition(
                session,
                tenant_id,
                state_id=state_id,
                entity_id=entity_id,
                period_id=UUID(str(row["id"])),
                pair=("future", "open"),
                at=at + timedelta(minutes=1),
                actor=admin,
            )
        january_id = UUID(str(january["id"]))
        state_id = states["january"]
        common = {"state_id": state_id, "entity_id": entity_id, "period_id": january_id}
        transitions["january:open>closing#1"] = _transition(
            session, tenant_id, pair=("open", "closing"), at=T0, actor=admin, **common
        )
        lock_request = _approved(
            session,
            tenant_id,
            subject_type=ApprovalSubjectType.PERIOD_LOCK,
            state_id=state_id,
            entity_id=entity_id,
            preparer=admin,
            approvers=[cora],
            at=T0 + timedelta(minutes=10),
            comment=LOCK_COMMENT,
        )
        lock = _lock_values(
            tenant_id,
            kind=LockKind.LOCK,
            entity_id=entity_id,
            period_id=january_id,
            approval_request_id=lock_request,
            actor=cora,
            previous_lock_id=None,
            comment=LOCK_COMMENT,
        )
        transitions["january:closing>closed#1"] = _transition(
            session,
            tenant_id,
            pair=("closing", "closed"),
            at=T0 + timedelta(minutes=10),
            actor=cora,
            approval_request_id=lock_request,
            lock=lock,
            **common,
        )
        reopen_request = _approved(
            session,
            tenant_id,
            subject_type=ApprovalSubjectType.PERIOD_REOPEN,
            state_id=state_id,
            entity_id=entity_id,
            preparer=admin,
            approvers=[cora, priya],
            at=T0 + timedelta(minutes=30),
            comment=REOPEN_COMMENT,
            reason_code="ERROR_CORRECTION",
        )
        reopen = _lock_values(
            tenant_id,
            kind=LockKind.REOPEN,
            entity_id=entity_id,
            period_id=january_id,
            approval_request_id=reopen_request,
            actor=priya,
            previous_lock_id=UUID(str(lock["id"])),
            comment=REOPEN_COMMENT,
            reason_code="ERROR_CORRECTION",
        )
        transitions["january:closed>reopened"] = _transition(
            session,
            tenant_id,
            pair=("closed", "reopened"),
            at=T0 + timedelta(minutes=30),
            actor=priya,
            approval_request_id=reopen_request,
            lock=reopen,
            reason_code="ERROR_CORRECTION",
            **common,
        )
        transitions["january:reopened>closing"] = _transition(
            session,
            tenant_id,
            pair=("reopened", "closing"),
            at=T0 + timedelta(minutes=40),
            actor=admin,
            **common,
        )
        relock_request = _approved(
            session,
            tenant_id,
            subject_type=ApprovalSubjectType.PERIOD_LOCK,
            state_id=state_id,
            entity_id=entity_id,
            preparer=admin,
            approvers=[cora],
            at=T0 + timedelta(minutes=50),
            comment=LOCK_COMMENT,
        )
        relock = _lock_values(
            tenant_id,
            kind=LockKind.LOCK,
            entity_id=entity_id,
            period_id=january_id,
            approval_request_id=relock_request,
            actor=cora,
            previous_lock_id=UUID(str(reopen["id"])),
            comment=LOCK_COMMENT,
        )
        transitions["january:closing>closed#2"] = _transition(
            session,
            tenant_id,
            pair=("closing", "closed"),
            at=T0 + timedelta(minutes=50),
            actor=cora,
            approval_request_id=relock_request,
            lock=relock,
            **common,
        )
    return Chain(
        admin=admin,
        cora=cora,
        priya=priya,
        entity_id=entity_id,
        january_state_id=states["january"],
        february_state_id=states["february"],
        january_id=january_id,
        transitions=transitions,
        lock_id=UUID(str(lock["id"])),
        reopen_id=UUID(str(reopen["id"])),
        relock_id=UUID(str(relock["id"])),
        requests=(lock_request, reopen_request, relock_request),
    )


def _january_chain_on(
    world: ReportWorld,
    session: Session,
    *,
    state_id: UUID,
    period_id: UUID,
    entity_id: UUID,
    preparer: Member,
    approvers: tuple[Member, Member],
) -> tuple[dict[str, UUID], dict[str, Any], dict[str, Any], dict[str, Any], tuple[UUID, ...]]:
    """January's close chain written on an OPEN period of a product-built world (the k01 world):
    open → closing → closed (LOCK) → reopened (REOPEN) → closing → closed (re-LOCK)."""
    tenant_id = world.tenant_id
    cora, dan = approvers
    transitions: dict[str, UUID] = {}
    common = {"state_id": state_id, "entity_id": entity_id, "period_id": period_id}
    transitions["january:open>closing#1"] = _transition(
        session, tenant_id, pair=("open", "closing"), at=T0, actor=preparer, **common
    )
    lock_request = _approved(
        session,
        tenant_id,
        subject_type=ApprovalSubjectType.PERIOD_LOCK,
        state_id=state_id,
        entity_id=entity_id,
        preparer=preparer,
        approvers=[cora],
        at=T0 + timedelta(minutes=10),
        comment=LOCK_COMMENT,
    )
    lock = _lock_values(
        tenant_id,
        kind=LockKind.LOCK,
        entity_id=entity_id,
        period_id=period_id,
        approval_request_id=lock_request,
        actor=cora,
        previous_lock_id=None,
        comment=LOCK_COMMENT,
    )
    transitions["january:closing>closed#1"] = _transition(
        session,
        tenant_id,
        pair=("closing", "closed"),
        at=T0 + timedelta(minutes=10),
        actor=cora,
        approval_request_id=lock_request,
        lock=lock,
        **common,
    )
    reopen_request = _approved(
        session,
        tenant_id,
        subject_type=ApprovalSubjectType.PERIOD_REOPEN,
        state_id=state_id,
        entity_id=entity_id,
        preparer=preparer,
        approvers=[cora, dan],
        at=T0 + timedelta(minutes=30),
        comment=REOPEN_COMMENT,
        reason_code="ERROR_CORRECTION",
    )
    reopen = _lock_values(
        tenant_id,
        kind=LockKind.REOPEN,
        entity_id=entity_id,
        period_id=period_id,
        approval_request_id=reopen_request,
        actor=dan,
        previous_lock_id=UUID(str(lock["id"])),
        comment=REOPEN_COMMENT,
        reason_code="ERROR_CORRECTION",
    )
    transitions["january:closed>reopened"] = _transition(
        session,
        tenant_id,
        pair=("closed", "reopened"),
        at=T0 + timedelta(minutes=30),
        actor=dan,
        approval_request_id=reopen_request,
        lock=reopen,
        reason_code="ERROR_CORRECTION",
        **common,
    )
    transitions["january:reopened>closing"] = _transition(
        session,
        tenant_id,
        pair=("reopened", "closing"),
        at=T0 + timedelta(minutes=40),
        actor=preparer,
        **common,
    )
    relock_request = _approved(
        session,
        tenant_id,
        subject_type=ApprovalSubjectType.PERIOD_LOCK,
        state_id=state_id,
        entity_id=entity_id,
        preparer=preparer,
        approvers=[cora],
        at=T0 + timedelta(minutes=50),
        comment=LOCK_COMMENT,
    )
    relock = _lock_values(
        tenant_id,
        kind=LockKind.LOCK,
        entity_id=entity_id,
        period_id=period_id,
        approval_request_id=relock_request,
        actor=cora,
        previous_lock_id=UUID(str(reopen["id"])),
        comment=LOCK_COMMENT,
    )
    transitions["january:closing>closed#2"] = _transition(
        session,
        tenant_id,
        pair=("closing", "closed"),
        at=T0 + timedelta(minutes=50),
        actor=cora,
        approval_request_id=relock_request,
        lock=relock,
        **common,
    )
    return transitions, lock, reopen, relock, (lock_request, reopen_request, relock_request)


def _k01_world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> ReportWorld:
    """Pellworth (WLD-K-01) booked, activated, billed and computed through the product's commands,
    FY2026-P01 to P09 open; Marcus (Controller: ``period.close``, ``tenant.snapshot``) is the
    sandbox requester; retention confirmed."""
    world = k01_pellworth(app, keyring, clock, files)
    with tenant_session(_context(world.tenant_id)) as session:
        confirm_retention(session, world.tenant_id, at=RETENTION_FROM)
    return world


def _k01_chain(world: ReportWorld) -> Chain:
    """The January chain on the k01 world's AVM-US FY2026-P01 (its state OPEN with the product's
    own NULL → future → open transitions), Marcus the preparer, two more Controllers the
    approvers."""
    cora, dan = colleague(world.tenant_id, "cora"), colleague(world.tenant_id, "dan")
    assign(cora, "controller")
    assign(dan, "controller")
    listed = periods(world.app, world.maya, entity="AVM-US")
    (january,) = [item for item in listed if item["period"]["period_key"] == "FY2026-P01"]
    (february,) = [item for item in listed if item["period"]["period_key"] == "FY2026-P02"]
    state_id = UUID(str(january["id"]))
    period_id = UUID(str(january["period"]["id"]))
    marcus = world.marcus.member
    with tenant_session(_context(world.tenant_id)) as session:
        transitions, lock, reopen, relock, requests = _january_chain_on(
            world,
            session,
            state_id=state_id,
            period_id=period_id,
            entity_id=world.entity_id,
            preparer=marcus,
            approvers=(cora, dan),
        )
    return Chain(
        admin=marcus,
        cora=cora,
        priya=dan,
        entity_id=world.entity_id,
        january_state_id=state_id,
        february_state_id=UUID(str(february["id"])),
        january_id=period_id,
        transitions=transitions,
        lock_id=UUID(str(lock["id"])),
        reopen_id=UUID(str(reopen["id"])),
        relock_id=UUID(str(relock["id"])),
        requests=requests,
        group_id=UUID(str(world.contracts[K01].combination_group["id"])),
        requester=marcus,
    )


def _copy(
    chain: Chain, runtime: JobRuntime, name: str, *, clock: FrozenClock
) -> tuple[UUID, dict[str, Any]]:
    """A SANDBOX_COPY through the dispatched job: export, load, replay; returns the sandbox id and
    the job outcome. The cutoff is the database clock read NOW, after the world and the chain, and
    the shared injected ``FrozenClock`` ADVANCES to it first (WITNESS-3 residual, Codex 1757 §2):
    the world and the chain were built at ``FROZEN_AT`` and after, their database-stamped rows
    later still, and ``snapshot_job._check_row`` admits ``known_at ≤ now`` on the runtime clock —
    stamping the queued job alone is not enough."""
    known_at = cutoff_after(chain.admin.tenant_id, clock)
    with tenant_session(_context(chain.admin.tenant_id)) as session:
        row = tenant_snapshot_values(
            chain.admin.tenant_id, known_at=known_at, purpose="SANDBOX_COPY"
        )
        session.execute(insert(tenant_snapshot).values(**row))
    sandbox_id = UUID(int=int(row["id"]) ^ 1)
    params = {
        "tenant_snapshot_id": str(row["id"]),
        "known_at": known_at.isoformat(),
        "purpose": "SANDBOX_COPY",
        **sb.load_params_of(
            sandbox_tenant_id=sandbox_id,
            name=name,
            requested_by=(chain.requester or chain.admin).user_id,
            restore=False,
        ),
    }
    result = run_dispatched_snapshot(chain.admin.tenant_id, params, runtime=runtime, now=known_at)
    return sandbox_id, result


def _period_rows(sandbox_id: UUID) -> dict[str, Any]:
    with tenant_session(_context(sandbox_id), read_only=True) as session:
        states = {
            UUID(str(r["id"])): dict(r) for r in session.execute(select(period_state)).mappings()
        }
        locks = {
            UUID(str(r["id"])): dict(r) for r in session.execute(select(period_lock)).mappings()
        }
        transitions = {
            UUID(str(r["id"])): dict(r)
            for r in session.execute(select(period_state_transition)).mappings()
        }
        warnings = [
            dict(r)
            for r in session.execute(
                select(exception_item).where(exception_item.c.code == sb.EXCEPTION_REPLAY_BLOCKED)
            ).mappings()
        ]
        requests = {
            UUID(str(r["id"])): dict(r)
            for r in session.execute(select(approval_request)).mappings()
        }
        steps = {
            UUID(str(r["id"])): dict(r) for r in session.execute(select(approval_step)).mappings()
        }
        decisions = [dict(r) for r in session.execute(select(approval_decision)).mappings()]
    return {
        "states": states,
        "locks": locks,
        "transitions": transitions,
        "warnings": warnings,
        "requests": requests,
        "steps": steps,
        "decisions": decisions,
    }


_REMAPPED = frozenset({"tenant_id"})  # the ONLY governed remapping of a copied approval row


def _approval_graph(tenant_id: UUID, request_ids: tuple[UUID, ...]) -> dict[str, Any]:
    """The requests, steps and decisions of ``request_ids`` in ``tenant_id``, every column but the
    remapped tenant, keyed by id — the exact comparison source → restored."""

    def strip(row: Any) -> dict[str, Any]:
        return {k: v for k, v in dict(row).items() if k not in _REMAPPED}

    with tenant_session(_context(tenant_id), read_only=True) as session:
        requests = {
            UUID(str(r["id"])): strip(r)
            for r in session.execute(
                select(approval_request).where(approval_request.c.id.in_(request_ids))
            ).mappings()
        }
        steps = {
            UUID(str(r["id"])): strip(r)
            for r in session.execute(
                select(approval_step).where(approval_step.c.approval_request_id.in_(request_ids))
            ).mappings()
        }
        decisions = {
            UUID(str(r["id"])): strip(r)
            for r in session.execute(
                select(approval_decision).where(
                    approval_decision.c.approval_request_id.in_(request_ids)
                )
            ).mappings()
        }
    return {"requests": requests, "steps": steps, "decisions": decisions}


def _assert_approval_graph_restored(sandbox_id: UUID, chain: Chain) -> None:
    """R3 / APPROVAL-UNIQUE-1 at the real loader boundary: the finalized source graphs are in the
    sandbox EXACTLY — every request, step and decision by id with the same hash, subject,
    timestamps, decision kinds, MFA times and final states (the tenant is the only remapping) —
    restored root by root under the live decision guard (each request PENDING and its step ACTIVE
    while ITS copied decisions inserted, finalized before the next request of the same period
    state inserted, so ``ux_approval_request__pending_subject`` never saw two at once)."""
    source = _approval_graph(chain.admin.tenant_id, chain.requests)
    restored = _approval_graph(sandbox_id, chain.requests)
    assert set(source["requests"]) == set(chain.requests)
    assert restored == source
    assert all(r["status"] == "APPROVED" for r in restored["requests"].values())
    assert all(s["status"] == "APPROVED" for s in restored["steps"].values())
    assert len(restored["decisions"]) == 4  # lock 1, reopen 2, re-lock 1 — none omitted
    assert all(
        d["decision"] == "APPROVE" and d["mfa_verified_at"] is not None
        for d in restored["decisions"].values()
    )


def _state_map(tenant_id: UUID) -> dict[UUID, tuple[str, UUID | None]]:
    """Every period state of the tenant by id: (state, current lock)."""
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return {
            UUID(str(r["id"])): (
                str(r["state"]),
                None if r["current_lock_id"] is None else UUID(str(r["current_lock_id"])),
            )
            for r in session.execute(
                select(period_state.c.id, period_state.c.state, period_state.c.current_lock_id)
            ).mappings()
        }


def _load_report(sandbox_id: UUID, runtime: JobRuntime, keyring: KeyRing) -> dict[str, Any]:
    """The AUDIT_DIGEST load report the sandbox's ``tenant.snapshot_loaded`` event references."""
    with tenant_session(_context(sandbox_id), read_only=True) as session:
        detail = session.execute(
            select(audit_event.c.detail)
            .where(audit_event.c.action == sb.ACTION_LOADED)
            .order_by(audit_event.c.chain_seq)
        ).scalar_one()
        _, stream = open_file(
            session, UUID(str(detail["load_report_file_id"])), files=runtime.files, keyring=keyring
        )  # type: ignore[arg-type]
        return dict(json.loads(stream.read()))


def _computation_rows(sandbox_id: UUID, group_id: UUID) -> dict[str, Any]:
    with tenant_session(_context(sandbox_id), read_only=True) as session:
        computations = [
            dict(r)
            for r in session.execute(
                select(contract_computation)
                .where(contract_computation.c.combination_group_id == group_id)
                .order_by(contract_computation.c.created_at)
            ).mappings()
        ]
        lines = int(session.execute(select(func.count()).select_from(schedule_line)).scalar_one())
    return {"computations": computations, "schedule_lines": lines}


def _unlocked(world: ReportWorld) -> Chain:
    """The k01 world as it is built — its nine periods open, no lock chain — with Marcus the
    sandbox requester."""
    marcus = world.marcus.member
    return Chain(
        admin=marcus,
        cora=marcus,
        priya=marcus,
        entity_id=world.entity_id,
        january_state_id=UUID(int=0),
        february_state_id=UUID(int=0),
        january_id=UUID(int=0),
        transitions={},
        lock_id=UUID(int=0),
        reopen_id=UUID(int=0),
        relock_id=UUID(int=0),
        requests=(),
        group_id=UUID(str(world.contracts[K01].combination_group["id"])),
        requester=marcus,
    )


def _version_hashes(tenant_id: UUID, group_id: UUID) -> dict[str, tuple[str, str]]:
    """Per book of the group, its LATEST version: the stored ``output_sha256`` (T-CON-08) and the
    ``input_sha256`` of the computation that wrote it (T-CON-07)."""
    with tenant_session(_context(tenant_id), read_only=True) as session:
        rows = session.execute(
            select(
                contract_version.c.book_code,
                contract_version.c.output_sha256,
                contract_computation.c.input_sha256,
            )
            .join(
                contract_computation,
                contract_computation.c.id == contract_version.c.contract_computation_id,
            )
            .where(contract_version.c.combination_group_id == group_id)
            .order_by(contract_version.c.version_no)
        ).all()
    return {str(book): (str(output), str(input_)) for book, output, input_ in rows}


def _schedule_total(tenant_id: UUID) -> Decimal:
    """The sum of every stored schedule line amount of the tenant."""
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return Decimal(
            session.execute(select(func.coalesce(func.sum(schedule_line.c.amount), 0))).scalar_one()
        )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "SNP-2b (supervisor ruling R-10, 2026-09-29): sandbox-side close replay needs CLO-14, "
        "CLO-16/17 and CLO-19/20; SBX-04 blocked path governs until then"
    ),
)
def test_replay_reaches_the_source_lock_chain(
    committed_db: TestDatabase,
    app: FastAPI,
    files: LocalFileStore,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """Acceptance of the finished path, pinned until SNP-2b (module docstring; the assertions are
    unchanged). What is missing is NOT CLO-10 alone, as this docstring once predicted: the first
    ``LOCK`` of the replay is refused ``close-gates-failed`` by ``BATCHES_ACKNOWLEDGED``,
    ``JE_BALANCED``, ``JE_COMPLETE`` and ``RECONCILIATIONS_GENERATED`` — the sandbox has no
    calculated journal run, no acknowledged batch and no reconciliation of its own, so January
    stays ``closing`` (SANDBOX_REPLAY_BLOCKED) and every assertion about the lock chain below is
    unreachable. When the path works: the exported January chain — open, closing, LOCK, REOPEN,
    closing, re-LOCK — is replayed through the governed commands with the copied approvals, so
    the sandbox's January is
    ``closed`` with the SOURCE relock as its current lock; the three locks keep their ids, kinds,
    transitions and ``previous_lock_id`` chain (LOCK ← REOPEN ← re-LOCK); every transition keeps
    its id and its ``period_lock_id``; the re-lock stores its diff report (CLO-7); February is
    ``open``; no period is blocked and the load SUCCEEDED. On the k01 world (R1): Pellworth's
    group recomputed SUCCEEDED with the ``MIGRATION`` trigger on the OPEN sandbox periods before
    the close replay, its schedule lines exist, no group is left un-recomputed and
    ``derived_mismatches = 0``; the finalized approval graph is restored (R3)."""
    world = _k01_world(app, keyring, clock, files)
    chain = _k01_chain(world)
    runtime = world.runtime
    sandbox_id, result = _copy(chain, runtime, "Replay chain", clock=clock)
    assert result["state"] == "SUCCEEDED", result["problem"]
    counts = result["result"]["counts"]
    assert counts["blocked_periods"] == 0 and counts["derived_mismatches"] == 0, load_outcome(
        counts
    )
    assert counts["groups_recomputed"] == 1 and counts["groups_not_recomputed"] == 0
    assert chain.group_id is not None
    computed = _computation_rows(sandbox_id, chain.group_id)
    (recomputed,) = computed["computations"]  # REGENERATED: the sandbox's own, none copied
    assert recomputed["status"] == "SUCCEEDED" and recomputed["trigger"] == "MIGRATION"
    assert computed["schedule_lines"] > 0  # the posting targets CV-13 refused without periods
    rows = _period_rows(sandbox_id)
    _assert_approval_graph_restored(sandbox_id, chain)
    source_states = _state_map(world.tenant_id)
    assert (
        _state_map(sandbox_id) == source_states
    )  # WITNESS-2: exact ids and states, never a subset
    assert source_states[chain.january_state_id] == ("closed", chain.relock_id)
    assert sum(1 for state, _ in source_states.values() if state == "open") == 8  # P02..P09
    assert all(state in ("open", "closed", "future") for state, _ in source_states.values())
    january = rows["states"][chain.january_state_id]
    assert january["state"] == "closed" and january["current_lock_id"] == chain.relock_id
    assert rows["states"][chain.february_state_id]["state"] == "open"
    assert rows["states"][chain.february_state_id]["current_lock_id"] is None
    locks = rows["locks"]
    assert set(locks) == {chain.lock_id, chain.reopen_id, chain.relock_id}
    assert (
        locks[chain.lock_id]["kind"] == "LOCK" and locks[chain.lock_id]["previous_lock_id"] is None
    )
    assert locks[chain.reopen_id]["kind"] == "REOPEN"
    assert locks[chain.reopen_id]["previous_lock_id"] == chain.lock_id
    assert locks[chain.relock_id]["kind"] == "LOCK"
    assert locks[chain.relock_id]["previous_lock_id"] == chain.reopen_id
    assert locks[chain.relock_id]["diff_report_file_id"] is not None  # CLO-7 re-lock diff
    for key, lock_id in (
        ("january:closing>closed#1", chain.lock_id),
        ("january:closed>reopened", chain.reopen_id),
        ("january:closing>closed#2", chain.relock_id),
    ):
        transition = rows["transitions"][chain.transitions[key]]
        assert transition["period_lock_id"] == lock_id
        assert locks[lock_id]["period_state_transition_id"] == chain.transitions[key]
    for key, transition_id in chain.transitions.items():
        assert transition_id in rows["transitions"], key  # every source transition, by id
    assert (
        rows["transitions"][chain.transitions["january:closing>closed#2"]]["created_by"]
        == chain.admin.user_id
    )  # the replay's actor is the requester's copied membership, not the source approver
    assert rows["warnings"] == []
    report = _load_report(sandbox_id, runtime, keyring)
    assert report["groups_recomputed"] == 1 and report["mismatches"] == []


def test_replay_on_the_k01_chain_restores_everything_the_sandbox_can_reach(
    committed_db: TestDatabase,
    app: FastAPI,
    files: LocalFileStore,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """What ``test_replay_reaches_the_source_lock_chain`` asserts and the product delivers TODAY
    (split out by supervisor ruling R-10, so its strict xfail covers only the unreachable part),
    on the same world and the same copy. The load SUCCEEDS. R1: Pellworth's group recomputes
    SUCCEEDED with the ``MIGRATION`` trigger on the OPEN sandbox periods before the close replay,
    its schedule lines exist, no group is left un-recomputed and ``derived_mismatches = 0``. R3:
    the finalized approval graph of the lock, the reopen and the re-lock is restored exactly.
    WITNESS-2 on the reachable part: every period state but January's equals the source's by id
    and state; February is ``open`` without a lock.

    January is where the path stops, as 05 SBX-04 rules it (D-98 137 (3)): the replay opens it
    and starts its close, and the first ``LOCK`` is refused ``close-gates-failed`` by exactly five
    gates — ``BATCHES_ACKNOWLEDGED``, ``CLOSE_RUN_COMPLETED``, ``JE_BALANCED``, ``JE_COMPLETE``,
    ``RECONCILIATIONS_GENERATED`` — so the period stays ``closing`` without a lock row, is named
    ONCE in ``blocked_periods`` and raises one ``SANDBOX_REPLAY_BLOCKED`` warning. The pin is
    exact on purpose: the day a gate stops failing here, SNP-2b has moved and this case and the
    xfail are to be merged back.

    ``CLOSE_RUN_COMPLETED`` is the fifth since 04 rev 1.172 (item CLO-GATE-RUN-1; supervisor
    ruling R-116 (e); 05 SBX-04 rev 1.111): a replayed lock takes that gate from the source lock's
    certification, and the chain's locks, written directly, certify nothing
    (``_lock_values``) — a source lock without the result leaves the sandbox's own evaluation, and
    the sandbox has no close run. A chain whose locks carry the result loses this gate here."""
    world = _k01_world(app, keyring, clock, files)
    chain = _k01_chain(world)
    runtime = world.runtime
    sandbox_id, result = _copy(chain, runtime, "Replay chain, reachable", clock=clock)
    assert result["state"] == "SUCCEEDED", result["problem"]
    counts = result["result"]["counts"]
    assert counts["derived_mismatches"] == 0, load_outcome(counts)
    assert counts["groups_recomputed"] == 1 and counts["groups_not_recomputed"] == 0
    assert chain.group_id is not None
    computed = _computation_rows(sandbox_id, chain.group_id)
    (recomputed,) = computed["computations"]  # REGENERATED: the sandbox's own, none copied
    assert recomputed["status"] == "SUCCEEDED" and recomputed["trigger"] == "MIGRATION"
    assert computed["schedule_lines"] > 0  # the posting targets CV-13 refused without periods
    rows = _period_rows(sandbox_id)
    _assert_approval_graph_restored(sandbox_id, chain)
    source_states = _state_map(world.tenant_id)
    assert source_states[chain.january_state_id] == ("closed", chain.relock_id)
    assert sum(1 for state, _ in source_states.values() if state == "open") == 8  # P02..P09
    assert all(state in ("open", "closed", "future") for state, _ in source_states.values())
    reached = _state_map(sandbox_id)
    january = chain.january_state_id
    assert set(reached) == set(source_states)  # every source period state, by id
    assert {key: value for key, value in reached.items() if key != january} == {
        key: value for key, value in source_states.items() if key != january
    }
    assert rows["states"][chain.february_state_id]["state"] == "open"
    assert rows["states"][chain.february_state_id]["current_lock_id"] is None
    report = _load_report(sandbox_id, runtime, keyring)
    assert report["groups_recomputed"] == 1 and report["mismatches"] == []
    # where the path stops: January, at its last reachable state
    assert counts["blocked_periods"] == 1
    assert reached[january] == ("closing", None) and rows["locks"] == {}
    assert chain.transitions["january:open>closing#1"] in rows["transitions"]
    assert chain.transitions["january:closing>closed#1"] not in rows["transitions"]
    (blocked,) = report["blocked_periods"]
    assert blocked["period_state_id"] == str(january)
    assert (blocked["attempted"], blocked["reached"]) == ("closing → closed", "closing")
    assert str(blocked["reason"]).startswith(
        "close-gates-failed "
        "[BATCHES_ACKNOWLEDGED, CLOSE_RUN_COMPLETED, JE_BALANCED, JE_COMPLETE, "
        "RECONCILIATIONS_GENERATED]"
    )
    (warning,) = rows["warnings"]
    assert warning["severity"] == "WARNING" and warning["period_id"] == chain.january_id


def test_blocked_periods_are_queryable_and_refuse_point_in_time_consumers(
    committed_db: TestDatabase,
    app: FastAPI,
    files: LocalFileStore,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """05 SBX-04 rev 1.64 (supervisor ruling R-43 (d)): ``blocked_periods`` has a queryable home
    and the refusal the rule promises consumers. On the k01 chain world January's lock cannot be
    replayed (SNP-2b). The sandbox's API-S-Tenant — ``GET /tenant`` as Marcus inside it —
    answers ``sandbox_load`` with the seed snapshot, ``derived_mismatches = 0``,
    ``blocked_periods`` = January's period state, and the load report's id and SHA-256 as the
    summary event carries them. ``sandboxes.require_point_in_time`` refuses in that sandbox with
    412 ``precondition-failed``, rule id ``SANDBOX_PERIODS_BLOCKED``, naming the period state;
    it passes in the source, where the question does not arise."""
    world = _k01_world(app, keyring, clock, files)
    chain = _k01_chain(world)
    sandbox_id, result = _copy(chain, world.runtime, "Blocked, queryable", clock=clock)
    assert result["state"] == "SUCCEEDED", result["problem"]
    counts = result["result"]["counts"]
    assert (counts["blocked_periods"], counts["derived_mismatches"]) == (1, 0), load_outcome(counts)
    january = chain.january_state_id
    with tenant_session(_context(sandbox_id), read_only=True) as session:
        with pytest.raises(Problem) as refused:
            sb.require_point_in_time(session, sandbox_id)
    assert (refused.value.slug, refused.value.status) == ("precondition-failed", 412)
    (error,) = refused.value.errors
    assert (error.field, error.rule_id) == ("blocked_periods", sb.RULE_PERIODS_BLOCKED)
    assert str(january) in error.message
    with tenant_session(_context(world.tenant_id), read_only=True) as session:
        sb.require_point_in_time(session, world.tenant_id)
    marcus = enter_workspace(app, clock, world.marcus, sandbox_id)
    shown = get(app, "/api/v1/tenant", marcus)
    assert shown.status_code == 200, shown.text
    assert shown.headers["X-Erev-Tenant-Kind"] == "sandbox"
    loaded = shown.json()["sandbox_load"]
    detail = load_chain(sandbox_id).summary["detail"]
    assert loaded["blocked_periods"] == [str(january)] == detail["blocked_periods"]
    assert loaded["derived_mismatches"] == 0
    assert loaded["tenant_snapshot_id"] == str(UUID(int=int(sandbox_id) ^ 1))  # ``_copy``
    assert loaded["load_report_file_id"] == detail["load_report_file_id"]
    assert loaded["load_report_sha256"] == detail["load_report_sha256"]
    source = get(app, "/api/v1/tenant", enter_workspace(app, clock, world.marcus, world.tenant_id))
    assert source.status_code == 200 and source.json()["sandbox_load"] is None, source.text


def test_recompute_runs_on_open_periods_before_the_close_replay(
    committed_db: TestDatabase,
    app: FastAPI,
    files: LocalFileStore,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """R1 alone, independent of the close replay: the k01 world without a lock chain (its nine
    periods open) copies into a sandbox whose nine period states are ``open`` with the product's
    own creation and opening transitions by id BEFORE the recompute — so Pellworth's group
    recomputes SUCCEEDED (``MIGRATION``), its schedule lines exist, the recompute is THIS load's,
    ``groups_not_recomputed = 0`` and ``derived_mismatches = 0``. Before amendment 4 the recompute
    ran on a sandbox without period states, CV-13 quarantined the computation and the loader
    counted it as recomputed.

    WITNESS-1 (STALE EXPECTATION; supervisor ruling R-8, 2026-09-30): the case asserted
    ``recomputed["job_id"] == <the load job's id>``. That value cannot exist — 04 NC-06: "A
    reference to a tenant-owned row is a column ``<target>_id uuid`` plus a composite foreign key
    ``(tenant_id, <target>_id)`` ... Cross-tenant references are impossible by construction" — the
    load job is a row of the SOURCE tenant and the computation a row of the sandbox, and writing
    it was the ForeignKeyViolation (``fk_contract_computation__job``) that failed every load of a
    tenant holding a combination group (PRODUCT DEFECT; this case is its witness: the load
    SUCCEEDS and the group is recomputed). So ``job_id`` is NULL, and the intent of the witness —
    the recompute is attributable to this load — is asserted on what the product does record:
    the computation's ``contract_computation.create`` audit event sits in the sandbox's chain
    under the request id ``job-<load job>-recompute-<group>``, before the load's summary event,
    whose load report counts the group as recomputed."""
    world = _k01_world(app, keyring, clock, files)
    marcus = world.marcus.member
    chain = Chain(
        admin=marcus,
        cora=marcus,
        priya=marcus,
        entity_id=world.entity_id,
        january_state_id=UUID(int=0),
        february_state_id=UUID(int=0),
        january_id=UUID(int=0),
        transitions={},
        lock_id=UUID(int=0),
        reopen_id=UUID(int=0),
        relock_id=UUID(int=0),
        requests=(),
        group_id=UUID(str(world.contracts[K01].combination_group["id"])),
        requester=marcus,
    )
    sandbox_id, result = _copy(chain, world.runtime, "Recompute on open periods", clock=clock)
    assert result["state"] == "SUCCEEDED", result["problem"]
    counts = result["result"]["counts"]
    assert counts["groups_recomputed"] == 1 and counts["groups_not_recomputed"] == 0
    assert counts["derived_mismatches"] == 0 and counts["blocked_periods"] == 0, load_outcome(
        counts
    )
    assert chain.group_id is not None
    computed = _computation_rows(sandbox_id, chain.group_id)
    (recomputed,) = computed["computations"]
    assert recomputed["status"] == "SUCCEEDED" and recomputed["trigger"] == "MIGRATION"
    assert recomputed["job_id"] is None  # 04 NC-06: no sandbox row names the source's job (R-8)
    # WITNESS-1: the recompute is this load's, by the audit event the product writes for it
    events = load_chain(sandbox_id)
    assert unexplained_load_events(events, result["id"]) == []
    (created,) = events.of(f"{computation.COMPUTATION_OBJECT}.{computation.CREATE}")
    assert created["request_id"] == f"job-{result['id']}-recompute-{chain.group_id}"
    assert created["detail"]["ids"] == [str(recomputed["id"])]
    assert created["detail"]["trigger"] == "MIGRATION"
    assert created["chain_seq"] < events.summary["chain_seq"]  # before the load's summary
    assert _load_report(sandbox_id, world.runtime, keyring)["groups_recomputed"] == 1
    assert computed["schedule_lines"] > 0
    rows = _period_rows(sandbox_id)
    source_states = _state_map(world.tenant_id)
    assert _state_map(sandbox_id) == source_states  # every source period state by id (WITNESS-2)
    assert sum(1 for state, _ in source_states.values() if state == "open") == 9  # FY2026-P01..P09
    assert all(state in ("open", "future") for state, _ in source_states.values())
    assert all(lock is None for _, lock in source_states.values())
    source_transitions = {
        UUID(str(t["id"])) for t in periods_transitions(world.tenant_id, world.entity_id)
    }
    assert source_transitions <= set(rows["transitions"])  # every source transition, by id
    assert rows["warnings"] == [] and rows["locks"] == {}


def periods_transitions(tenant_id: UUID, entity_id: UUID) -> list[dict[str, Any]]:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return [
            dict(r)
            for r in session.execute(
                select(period_state_transition).where(
                    period_state_transition.c.entity_id == entity_id
                )
            ).mappings()
        ]


def test_replay_refused_by_a_gate_is_a_warning(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """The genuine guarded refusal (ruling (3)): an OPEN BLOCKING exception of the entity in
    January is copied into the sandbox, so ``EXCEPTIONS_CLEARED`` fails and the first LOCK is
    refused by name (``close-gates-failed``) — the period stays ``closing`` (its last reachable
    state), no lock row exists, the later steps of that period are skipped, February still opens,
    the load SUCCEEDS, the load report and the ``tenant.snapshot_loaded`` event name the blocked
    period, and one ``SANDBOX_REPLAY_BLOCKED`` WARNING item (IMP-116) is raised in the sandbox."""
    chain = _chain(keyring, clock)
    with tenant_session(_context(chain.admin.tenant_id)) as session:
        session.execute(
            insert(exception_item).values(
                **exception_item_values(
                    chain.admin.tenant_id,
                    entity_id=chain.entity_id,
                    period_id=chain.january_id,
                    created_at=FROZEN_AT + timedelta(minutes=5),
                )
            )
        )
    runtime = _runtime(app_settings, keyring, clock)
    sandbox_id, result = _copy(chain, runtime, "Replay blocked", clock=clock)
    assert result["state"] == "SUCCEEDED", result["problem"]
    assert result["result"]["counts"]["blocked_periods"] == 1
    rows = _period_rows(sandbox_id)
    january = rows["states"][chain.january_state_id]
    assert january["state"] == "closing" and january["current_lock_id"] is None
    assert rows["locks"] == {}
    assert rows["states"][chain.february_state_id]["state"] == "open"
    expected = dict(_state_map(chain.admin.tenant_id))
    expected[chain.january_state_id] = ("closing", None)  # the last reachable state (ruling (3))
    assert _state_map(sandbox_id) == expected  # WITNESS-2: every source period state by id
    assert chain.transitions["january:open>closing#1"] in rows["transitions"]
    assert chain.transitions["january:closing>closed#1"] not in rows["transitions"]
    _assert_approval_graph_restored(sandbox_id, chain)  # R3 is independent of the gates
    (warning,) = rows["warnings"]
    assert warning["severity"] == "WARNING" and warning["period_id"] == chain.january_id
    assert "close-gates-failed" in warning["message"]
    with tenant_session(_context(sandbox_id), read_only=True) as session:
        from erev_api.db.tables import audit_event

        detail = session.execute(
            select(audit_event.c.detail).where(audit_event.c.action == sb.ACTION_LOADED)
        ).scalar_one()
    assert detail["blocked_periods"] == [str(chain.january_state_id)]


def test_the_end_of_a_soft_close_under_reopen_replays_through_the_governed_move(
    committed_db: TestDatabase,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
) -> None:
    """04 T-REF-07 rev 1.170 (``closing → reopened``: the end of a soft close of a period that had
    been locked before) in the replay — the database witness owed since CLO-CANCEL-CLOSE-
    REOPENED-1 (supervisor ruling R-117 (c)).

    The source's January goes on after its re-lock: it is reopened again (REOPEN by cora and
    priya), soft-closed again, and the source then ENDED that soft close — the row the export
    holds as ``closing → reopened`` with its cancel reason and neither an approval request nor a
    lock record, January ``reopened`` under the second REOPEN. ``sandbox_periods.prepare`` plans
    that history and pairs no lock with the pair, and the plan's own step moves the period
    through the governed path (``_apply`` → ``_move`` → ``close.commands._record_transition``):
    ``reopened`` again, still under the REOPEN record, the transition written with the source's
    id, reason and comment.

    Fail-first (the pairing as CLO-CANCEL-CLOSE-REOPENED-1 left it): ``prepare`` raised "a
    transition to reopened without its period_lock row", which the loader answers not-loadable —
    a tenant whose history holds the pair could not be loaded as a sandbox.

    The step is applied to the tenant the rows were written in, not to a loaded sandbox: a load
    stops at a period's first LOCK until SNP-2b (``test_replay_reaches_the_source_lock_chain``,
    strict xfail), so no sandbox period reaches a soft close under a REOPEN record today."""
    chain = _chain(keyring, clock)
    tenant_id = chain.admin.tenant_id
    common = {
        "state_id": chain.january_state_id,
        "entity_id": chain.entity_id,
        "period_id": chain.january_id,
    }
    with tenant_session(_context(tenant_id)) as session:
        again = _approved(
            session,
            tenant_id,
            subject_type=ApprovalSubjectType.PERIOD_REOPEN,
            state_id=chain.january_state_id,
            entity_id=chain.entity_id,
            preparer=chain.admin,
            approvers=[chain.cora, chain.priya],
            at=T0 + timedelta(minutes=70),
            comment=REOPEN_COMMENT,
            reason_code="ERROR_CORRECTION",
        )
        reopen = _lock_values(
            tenant_id,
            kind=LockKind.REOPEN,
            entity_id=chain.entity_id,
            period_id=chain.january_id,
            approval_request_id=again,
            actor=chain.priya,
            previous_lock_id=chain.relock_id,
            comment=REOPEN_COMMENT,
            reason_code="ERROR_CORRECTION",
        )
        _transition(
            session,
            tenant_id,
            pair=("closed", "reopened"),
            at=T0 + timedelta(minutes=70),
            actor=chain.priya,
            approval_request_id=again,
            lock=reopen,
            reason_code="ERROR_CORRECTION",
            **common,
        )
        _transition(
            session,
            tenant_id,
            pair=("reopened", "closing"),
            at=T0 + timedelta(minutes=80),
            actor=chain.admin,
            **common,
        )
    reopen_id = UUID(str(reopen["id"]))
    tables = {
        "period_state": period_state,
        "period_state_transition": period_state_transition,
        "period_lock": period_lock,
    }
    with tenant_session(_context(tenant_id), read_only=True) as session:
        references = {
            name: [dict(row) for row in session.execute(select(table)).mappings()]
            for name, table in tables.items()
        }
    assert set(references) == set(sp.REFERENCE_DATASETS)
    # what the source's export holds one step later: the ended soft close, and January reopened
    ended_id = new_id()
    ended_comment = "January close restarted in the source"
    (soft_close,) = [
        row
        for row in references["period_state_transition"]
        if (row["from_state"], row["to_state"]) == ("reopened", "closing")
        and row["created_at"] == T0 + timedelta(minutes=80)
    ]
    references["period_state_transition"].append(
        {
            **soft_close,
            "id": ended_id,
            "from_state": "closing",
            "to_state": "reopened",
            "reason_code": "CLOSE_RESTARTED",
            "comment": ended_comment,
            "approval_request_id": None,
            "period_lock_id": None,
            "created_at": T0 + timedelta(minutes=90),
        }
    )
    for row in references["period_state"]:
        if row["id"] == chain.january_state_id:
            assert (row["state"], row["current_lock_id"]) == ("closing", reopen_id)
            row["state"] = "reopened"
    prepared = sp.prepare(references)
    (ended,) = [paired for paired in prepared.paired if paired.step.id == ended_id]
    assert ended.lock is None  # the pair bears no lock: it is not paired with one
    assert (ended.step.from_state, ended.step.to_state, ended.step.reason_code) == (
        PeriodState.CLOSING,
        PeriodState.REOPENED,
        "CLOSE_RESTARTED",
    )
    runtime = _runtime(app_settings, keyring, clock)
    actor = sb.sandbox_actor(tenant_id, chain.admin.user_id, at=clock.now())
    with system_unit_of_work(runtime, actor, request_id="test-replay-ended-soft-close") as uow:
        sp._apply(uow, prepared, ended)  # noqa: SLF001 - the replay's dispatcher for one step
        uow.commit()
    with tenant_session(_context(tenant_id), read_only=True) as session:
        january = session.execute(
            select(period_state.c.state, period_state.c.current_lock_id).where(
                period_state.c.id == chain.january_state_id
            )
        ).one()
        written = (
            session.execute(
                select(period_state_transition).where(period_state_transition.c.id == ended_id)
            )
            .mappings()
            .one()
        )
        locks = session.execute(
            select(func.count())
            .select_from(period_lock)
            .where(period_lock.c.period_id == chain.january_id)
        ).scalar_one()
    assert (january.state, january.current_lock_id) == ("reopened", reopen_id)
    assert (written["from_state"], written["to_state"]) == ("closing", "reopened")
    assert (
        str(getattr(written["reason_code"], "value", written["reason_code"])) == "CLOSE_RESTARTED"
    )
    assert (written["approval_request_id"], written["period_lock_id"]) == (None, None)
    assert written["comment"] == ended_comment  # the source's comment, not the replay's default
    assert written["created_by"] == chain.admin.user_id  # the replay's actor
    assert locks == 4  # LOCK, REOPEN, re-LOCK, REOPEN: the ended soft close wrote none


def test_determinism_is_verified_under_the_source_input_hash(
    committed_db: TestDatabase,
    app: FastAPI,
    files: LocalFileStore,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """05 SBX-05 rev 1.34 (supervisor ruling R-9): ``derived_mismatches = 0`` for the right
    reason, on the k01 world. The engine is observed, never replaced — a spy keeps the output
    of the sandbox's recompute. For every book of Pellworth's group: the sandbox's own
    ``input_sha256`` differs from the source's (CV-25 covers the re-stamped ``record_seq`` /
    ``recorded_at`` and the ``MIGRATION`` trigger), so the RAW stored output hashes differ too
    (CV-26 (a)) — which is why they are not what SBX-05 compares; and the sandbox's output hashed
    with the SOURCE computation's ``input_sha256`` in place of its own IS the source version's
    stored ``output_sha256``. That equality, not the count, is the witness."""
    kept: list[tuple[InputBundle, OutputBundle]] = []
    real = erev_engine.compute

    def spy(bundle: InputBundle) -> OutputBundle:
        output = real(bundle)
        kept.append((bundle, output))
        return output

    monkeypatch.setattr(erev_engine, "compute", spy)
    world = _k01_world(app, keyring, clock, files)
    chain = _unlocked(world)
    assert chain.group_id is not None
    sandbox_id, result = _copy(chain, world.runtime, "Verified", clock=clock)
    assert result["state"] == "SUCCEEDED", result["problem"]
    assert result["result"]["counts"]["derived_mismatches"] == 0, load_outcome(
        result["result"]["counts"]
    )
    (recomputed,) = [output for bundle, output in kept if bundle.trigger == "MIGRATION"]
    source = _version_hashes(world.tenant_id, chain.group_id)
    sandbox = _version_hashes(sandbox_id, chain.group_id)
    assert source and set(sandbox) == set(source)  # a version per book, on both sides
    for book, (source_output_sha256, source_input_sha256) in source.items():
        stored_sha256, own_input_sha256 = sandbox[book]
        assert own_input_sha256 != source_input_sha256  # CV-25: arrivals re-stamped, MIGRATION
        assert stored_sha256 != source_output_sha256  # CV-26 (a): never equal, never compared
        assert stored_sha256 == recomputed.sha256()  # the spy kept what the load persisted
        substituted = dataclasses.replace(recomputed, input_sha256=source_input_sha256)
        assert substituted.sha256() == source_output_sha256, book  # what SBX-05 verifies
    report = _load_report(sandbox_id, world.runtime, keyring)
    assert report["compared"] == len(source) and report["mismatches"] == []
    # every pair is a FIRST computation of its group: verified by the hash as well as the state
    assert report["first_computations"] == len(source)
    events = load_chain(sandbox_id)
    assert events.summary["detail"]["derived_mismatches"] == 0
    assert events.after == ()  # no warning item beside the summary


@pytest.mark.parametrize("changed_table", ["schedule_line", "fx_layer_movement"])
def test_a_differing_sandbox_output_is_a_determinism_mismatch(
    committed_db: TestDatabase,
    app: FastAPI,
    files: LocalFileStore,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    changed_table: str,
) -> None:
    """The NEGATIVE witness of 05 SBX-05 (supervisor rulings R-9 and R-43 (a) — "a check that
    cannot fail is worth nothing"). The source is built with the real engine; then a controlled
    fault is planted in the engine for the sandbox's recompute only: ONE schedule line amount,
    or both amounts of one same-currency FX movement, one minor unit higher. No stored row is
    edited, no guard bypassed, and the
    differing output is persisted through the governed path as a SUCCEEDED computation. The real
    comparison counts the pair as a mismatch of the MONETARY STATE and NAMES THE MEMBER — that
    schedule line's ``amount`` or movement's ``amount_txn``, one minor unit apart;
    the load still SUCCEEDS; the load report carries the source's hash and input hash, the
    sandbox's stored hash and the compared hash beside it; ONE ``SANDBOX_DETERMINISM_MISMATCH``
    WARNING naming the member is raised in the sandbox beside the summary event; and the
    requester is notified in the source."""
    world = _k01_world(app, keyring, clock, files)
    chain = _unlocked(world)
    assert chain.group_id is not None
    real = erev_engine.compute

    def off_by_one_minor_unit(bundle: InputBundle) -> OutputBundle:
        output = real(bundle)
        if bundle.trigger != "MIGRATION":
            return output
        book = output.books[0]
        if changed_table == "schedule_line":
            line = book.schedules[0]
            schedules = (dataclasses.replace(line, amount=line.amount + 1), *book.schedules[1:])
            changed = dataclasses.replace(book, schedules=schedules)
        else:
            movement = book.fx_layer_movements[0]
            columns = dict(movement.columns)
            columns["amount_txn"] += 1
            columns["amount_functional"] += 1
            changed = dataclasses.replace(
                book,
                fx_layer_movements=(
                    dataclasses.replace(movement, columns=columns),
                    *book.fx_layer_movements[1:],
                ),
            )
        return dataclasses.replace(output, books=(changed, *output.books[1:]))

    monkeypatch.setattr(erev_engine, "compute", off_by_one_minor_unit)
    sandbox_id, result = _copy(
        chain, world.runtime, f"Differing output {changed_table}", clock=clock
    )
    assert result["state"] == "SUCCEEDED", json.dumps(result["problem"])
    counts = result["result"]["counts"]
    source = _version_hashes(world.tenant_id, chain.group_id)
    sandbox = _version_hashes(sandbox_id, chain.group_id)
    assert source and set(sandbox) == set(source)
    assert counts["groups_recomputed"] == 1 and counts["groups_not_recomputed"] == 0
    assert counts["derived_mismatches"] == len(source)
    # the fault is one real member of the stored output: USD, so one minor unit is 0.01
    assert _schedule_total(sandbox_id) - _schedule_total(world.tenant_id) == (
        Decimal("0.01") if changed_table == "schedule_line" else Decimal(0)
    )
    report = _load_report(sandbox_id, world.runtime, keyring)
    assert (report["compared"], report["derived_mismatches"]) == (len(source), len(source))
    assert sorted(m["book_code"] for m in report["mismatches"]) == sorted(source)
    for mismatch in report["mismatches"]:
        source_output_sha256, source_input_sha256 = source[mismatch["book_code"]]
        assert mismatch["combination_group_id"] == str(chain.group_id)
        assert mismatch["source_sha256"] == source_output_sha256
        assert mismatch["source_input_sha256"] == source_input_sha256
        assert mismatch["sandbox_sha256"] == sandbox[mismatch["book_code"]][0]
        assert mismatch["comparable_sha256"] not in (
            source_output_sha256,
            mismatch["sandbox_sha256"],
        )
        assert mismatch["sandbox_computation"] == "SUCCEEDED"
        # the member: one schedule line's amount, the two values one minor unit apart
        assert mismatch["comparison"] == sx.COMPARISON_STATE
        assert str(mismatch["member"]).startswith(f"{changed_table}[")
        column = "amount" if changed_table == "schedule_line" else "amount_txn"
        assert str(mismatch["member"]).endswith(f"].{column}")
        assert Decimal(mismatch["sandbox"]) - Decimal(mismatch["source"]) == Decimal("0.01")
    with tenant_session(_context(sandbox_id), read_only=True) as session:
        items = [
            (str(code), str(severity), str(message))
            for code, severity, message in session.execute(
                select(
                    exception_item.c.code, exception_item.c.severity, exception_item.c.message
                ).where(exception_item.c.code == sb.EXCEPTION_DETERMINISM)
            )
        ]
    assert [item[:2] for item in items] == [(sb.EXCEPTION_DETERMINISM, "WARNING")]
    assert str(report["mismatches"][0]["member"]) in items[0][2]  # the warning names it too
    events = load_chain(sandbox_id)
    assert unexplained_load_events(events, result["id"]) == []
    assert events.summary["detail"]["derived_mismatches"] == len(source)
    assert [event["action"] for event in events.after] == [exceptions.CREATE_ACTION]
    snapshot_id = UUID(int=int(sandbox_id) ^ 1)  # ``_copy`` pre-allocates the sandbox id from it
    with tenant_session(_context(world.tenant_id), read_only=True) as session:
        notified = session.execute(
            select(func.count())
            .select_from(notification)
            .where(
                notification.c.recipient_membership_id == world.marcus.member.membership_id,
                notification.c.subject_id == snapshot_id,
            )
        ).scalar_one()
    assert notified == 1  # the requester, in the source (05 SBX-05)


def test_a_recompute_that_fails_is_reported_as_a_one_sided_mismatch(
    committed_db: TestDatabase,
    app: FastAPI,
    files: LocalFileStore,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """05 SBX-05: a group whose recompute does not end SUCCEEDED is REPORTED, never passed. The
    source is built with the real engine; then a fault is planted in the engine for the sandbox's
    recompute only — an error that is no engine refusal, the class an infrastructure failure (a
    lock timeout under contention) arrives as. ``compute_group`` stores it as a FAILED computation
    (DG-CMD-09: a refused computation is stored, not raised), so the sandbox holds no version of
    the group. The load still SUCCEEDS; the group counts as NOT recomputed (D-98 137 amendment 4
    R1); each pair of the group is a ONE-SIDED mismatch that names no member and carries
    ``sandbox_computation = FAILED``; and the one warning says that a group did not recompute.
    ``derived_mismatches = 1`` with ``groups_not_recomputed = 1`` is therefore the signature of a
    failed recompute, not of a differing result."""
    world = _k01_world(app, keyring, clock, files)
    chain = _unlocked(world)
    assert chain.group_id is not None
    real = erev_engine.compute

    def failing_in_the_sandbox(bundle: InputBundle) -> OutputBundle:
        if bundle.trigger == "MIGRATION":
            raise RuntimeError("planted infrastructure fault")
        return real(bundle)

    monkeypatch.setattr(erev_engine, "compute", failing_in_the_sandbox)
    sandbox_id, result = _copy(chain, world.runtime, "Failed recompute", clock=clock)
    assert result["state"] == "SUCCEEDED", result["problem"]
    counts = result["result"]["counts"]
    source = _version_hashes(world.tenant_id, chain.group_id)
    assert source and _version_hashes(sandbox_id, chain.group_id) == {}
    assert (counts["groups_recomputed"], counts["groups_not_recomputed"]) == (0, 1), load_outcome(
        counts
    )
    assert counts["derived_mismatches"] == len(source)
    (stored,) = _computation_rows(sandbox_id, chain.group_id)["computations"]
    assert (stored["status"], stored["trigger"]) == ("FAILED", "MIGRATION")
    report = _load_report(sandbox_id, world.runtime, keyring)
    assert (report["groups_recomputed"], report["first_computations"]) == (0, 0)
    assert (report["compared"], report["derived_mismatches"]) == (len(source), len(source))
    assert sorted(m["book_code"] for m in report["mismatches"]) == sorted(source)
    for mismatch in report["mismatches"]:
        assert mismatch["combination_group_id"] == str(chain.group_id)
        assert (mismatch["comparison"], mismatch["member"]) == (sx.COMPARISON_ONE_SIDED, None)
        assert mismatch["source"] == mismatch["source_sha256"] == source[mismatch["book_code"]][0]
        assert mismatch["sandbox"] is None and mismatch["sandbox_sha256"] is None
        assert mismatch["sandbox_computation"] == "FAILED"
    with tenant_session(_context(sandbox_id), read_only=True) as session:
        messages = [
            str(message)
            for (message,) in session.execute(
                select(exception_item.c.message).where(
                    exception_item.c.code == sb.EXCEPTION_DETERMINISM
                )
            )
        ]
    (message,) = messages
    assert "has a version in the source only" in message
    assert "1 group(s) did not recompute" in message


def test_a_group_the_engine_refuses_in_the_source_and_in_the_sandbox_is_no_mismatch(
    committed_db: TestDatabase,
    app: FastAPI,
    files: LocalFileStore,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """05 SBX-05: the verification compares the (group, book) pairs the SOURCE holds a version
    for. A group the engine refuses there — a booked draft whose computation is QUARANTINED, so it
    has no version — is refused alike by the sandbox's recompute: it counts as NOT recomputed, it
    has no pair and it is no determinism mismatch. ``groups_not_recomputed = 1`` with
    ``derived_mismatches = 0`` is the signature of "refused on both sides", against
    ``derived_mismatches = 1`` of the failed recompute above, where the source had a version.

    The refusal is this test's own: an ``EngineError`` planted for the one draft, in the source
    and in the sandbox. The Avenmoor key contract that used to show the case, K-10, computes
    since ENG-CAL-PREBOOK-1 (main 1a0f5d3c) and is verified in ``test_sandbox_avenmoor.py``."""
    world = _k01_world(app, keyring, clock, files)
    chain = _unlocked(world)
    assert chain.group_id is not None
    real = erev_engine.compute

    def refusing_the_draft(bundle: InputBundle) -> OutputBundle:
        if K02_EXTERNAL_ID in bundle.group.member_contract_keys:
            raise EngineError("SSP_KEY_NOT_FOUND", "No approved SSP for the key.")
        return real(bundle)

    monkeypatch.setattr(erev_engine, "compute", refusing_the_draft)
    customer = customer_id(app, world.maya, code="C-02-DRAFT", name="Marrowby Health Partners")
    draft = booked_contract(world.place, k02_seat_month_body(customer), activate=False)
    draft_group = UUID(str(draft.combination_group["id"]))
    with world.place.uow() as uow:
        refused = compute_job.compute_group(uow, draft_group)  # as the booking's computation does
        uow.commit()
    assert refused.status is ComputationStatus.QUARANTINED
    assert _version_hashes(world.tenant_id, draft_group) == {}  # no version in the source

    sandbox_id, result = _copy(chain, world.runtime, "Refused on both sides", clock=clock)
    assert result["state"] == "SUCCEEDED", result["problem"]
    counts = result["result"]["counts"]
    assert (counts["groups_recomputed"], counts["groups_not_recomputed"]) == (1, 1), load_outcome(
        counts
    )
    assert counts["derived_mismatches"] == 0, load_outcome(counts)
    source = _version_hashes(world.tenant_id, chain.group_id)
    report = _load_report(sandbox_id, world.runtime, keyring)
    assert source and (report["compared"], report["mismatches"]) == (len(source), [])
    assert _version_hashes(sandbox_id, chain.group_id).keys() == source.keys()
    # the draft: refused again by the sandbox's one recompute, and still without a version
    assert _version_hashes(sandbox_id, draft_group) == {}
    (stored,) = _computation_rows(sandbox_id, draft_group)["computations"]
    assert (stored["status"], stored["trigger"]) == ("QUARANTINED", "MIGRATION")
    with tenant_session(_context(sandbox_id), read_only=True) as session:
        warned = session.execute(
            select(func.count())
            .select_from(exception_item)
            .where(exception_item.c.code == sb.EXCEPTION_DETERMINISM)
        ).scalar_one()
    assert warned == 0  # nothing to warn about: no pair differs and none is one-sided


def _stream_head(tenant_id: UUID, contract_id: UUID) -> int:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return int(
            session.execute(
                select(func.max(contract_event.c.stream_version)).where(
                    contract_event.c.contract_id == contract_id
                )
            ).scalar_one()
        )


def _latest_obligation_versions(tenant_id: UUID) -> dict[str, dict[str, Any]]:
    """The obligation versions of the tenant's LATEST contract version, by obligation key."""
    with tenant_session(_context(tenant_id), read_only=True) as session:
        latest = session.execute(select(func.max(obligation_version.c.version_no))).scalar_one()
        return {
            str(row["obligation_key"]): dict(row)
            for row in session.execute(
                select(obligation_version).where(obligation_version.c.version_no == latest)
            ).mappings()
        }


def _revenue_by_period(tenant_id: UUID) -> dict[UUID, Decimal]:
    """The REVENUE the tenant's subledger carries, per posting period."""
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return {
            UUID(str(period_id)): Decimal(total)
            for period_id, total in session.execute(
                select(subledger_line.c.period_id, func.sum(subledger_line.c.amount_functional))
                .where(subledger_line.c.account_role == "REVENUE")
                .group_by(subledger_line.c.period_id)
            )
        }


def test_a_group_computed_many_times_verifies_by_its_monetary_state(
    committed_db: TestDatabase,
    app: FastAPI,
    files: LocalFileStore,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """05 SBX-05 rev 1.50 (supervisor ruling R-43 (a)) — the case every real tenant is: a group
    the source computed MORE THAN ONCE. Pellworth's contract is computed through January; the
    February progress and invoice are appended and computed; a go-live bonus of 1,000.00 on the
    already satisfied O2 is approved (a cumulative catch-up on both obligations) and computed;
    the bonus is invoiced and computed. The source's latest version is the last step of that
    history: its ACTIVITY columns hold what its last computation added — no catch-up, no
    revenue, the bonus invoice — and its output hash can equal nobody's.

    The sandbox recomputes the same stream ONCE. Its activity columns hold the whole stream's —
    the pinned difference below, in exactly three of the six ``ACTIVITY_COLUMNS`` — and the raw
    and comparable hashes differ from the source's; every MEMBER OF THE MONETARY STATE is equal,
    so the pair is VERIFIED: ``derived_mismatches = 0``, no warning, and DG-PERF-02's reader
    accepts the load."""
    world = k01_pellworth(app, keyring, clock, files, through=date(2026, 1, 31))
    with tenant_session(_context(world.tenant_id)) as session:
        confirm_retention(session, world.tenant_id, at=RETENTION_FROM)
    contract_id = UUID(str(world.contracts[K01].contract["id"]))
    chain = _unlocked(world)
    assert chain.group_id is not None
    appended(
        world.place,
        contract_id,
        _stream_head(world.tenant_id, contract_id),
        k01_events(after=date(2026, 1, 31)),
    )
    computed(world.place, chain.group_id)
    assign(world.priya.member, "revenue_reviewer")
    _approved_estimate(
        world,
        element="BONUS-GOLIVE-01",
        kind="BONUS",
        obligation_key="O2",
        effective="2026-03-01",
        amount="1000.00",
    )
    bonus_invoice = EventIn(
        event_type=ContractEventType.BILLING_RECORDED,
        effective_date=date(2026, 3, 15),
        payload=BillingRecordedV1(
            invoice_number="INV-US-1099",
            line_external_id="INV-US-1099-1",
            obligation_key="O2",
            amount=MoneyIn(amount="1000.00", currency="USD"),
            issue_date=date(2026, 3, 15),
        ),
    )
    appended(world.place, contract_id, _stream_head(world.tenant_id, contract_id), [bonus_invoice])
    computed(world.place, chain.group_id)
    source = _latest_obligation_versions(world.tenant_id)
    assert all(int(row["version_no"]) >= 4 for row in source.values())  # a history, not one step

    sandbox_id, result = _copy(chain, world.runtime, "Computed many times", clock=clock)
    assert result["state"] == "SUCCEEDED", result["problem"]
    counts = result["result"]["counts"]
    assert counts["groups_recomputed"] == 1 and counts["groups_not_recomputed"] == 0
    assert counts["derived_mismatches"] == 0, load_outcome(counts)
    assert perf_sandbox.require_deterministic(counts) == 0  # DG-PERF-02's reader
    report = _load_report(sandbox_id, world.runtime, keyring)
    assert (report["compared"], report["mismatches"]) == (1, [])
    assert report["first_computations"] == 0  # verified by the monetary state alone
    # why the hashes could not verify it: the two outputs really differ ...
    hashes = _version_hashes(world.tenant_id, chain.group_id)
    recomputed = _version_hashes(sandbox_id, chain.group_id)
    assert set(recomputed) == set(hashes) == {BOOK}
    assert recomputed[BOOK][0] != hashes[BOOK][0]
    # ... in the activity of the last computation against the activity of the whole stream
    sandbox = _latest_obligation_versions(sandbox_id)
    assert set(sandbox) == set(source) == {"O1", "O2"}
    members = set(sx.monetary_members("obligation_version"))
    differing = {
        column
        for key, row in sandbox.items()
        for column, value in row.items()
        if column in members | sx.ACTIVITY_COLUMNS and source[key][column] != value
    }
    assert differing == {"revenue_amount", "billed_amount", "catch_up_amount"}
    assert differing <= sx.ACTIVITY_COLUMNS and not differing & members
    for key in ("O1", "O2"):
        assert source[key]["catch_up_amount"] == 0 != sandbox[key]["catch_up_amount"]
        assert sandbox[key]["catch_up_amount"] == sandbox[key]["catch_up_cum"]
        for cumulative in ("catch_up_cum", "revenue_cum", "billed_cum", "allocated_amount"):
            assert source[key][cumulative] == sandbox[key][cumulative], (key, cumulative)
    assert source["O2"]["billed_amount"] == Decimal("1000.00")  # the last invoice only
    assert sandbox["O2"]["billed_amount"] == sandbox["O2"]["billed_cum"]  # every invoice
    assert load_chain(sandbox_id).after == ()  # no warning item


def test_a_late_event_in_a_closed_source_period_verifies_and_posts_elsewhere(
    committed_db: TestDatabase,
    app: FastAPI,
    files: LocalFileStore,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """What 05 SBX-05 verifies and what it does not (rev 1.50; supervisor ruling R-43 (a):
    "ledger period attribution is NOT verified by SBX-05 ... it belongs to SNP-2b"). In the
    source January is CLOSED (the lock chain of this module) when a bonus effective 15 January
    is approved — a late event: the source recomputes with January closed and posts the catch-up
    where its periods allow. The sandbox recomputes with every period open and its January then
    stays ``closing`` (the blocked path of SBX-04).

    The MONETARY STATE is equal all the same — no schedule line, balance or version amount
    depends on the state a period had when the source computed — so ``derived_mismatches = 0``.
    The LEDGER differs, exactly as the rule says: both tenants carry the same revenue in total,
    and not in the same periods. That difference is SNP-2b's, and the load names the period it
    could not close in ``blocked_periods``."""
    world = _k01_world(app, keyring, clock, files)
    chain = _k01_chain(world)  # January closed in the source
    assert chain.group_id is not None
    assign(world.priya.member, "revenue_reviewer")
    _approved_estimate(
        world,
        element="BONUS-GOLIVE-01",
        kind="BONUS",
        obligation_key="O2",
        effective="2026-01-15",
        amount="1000.00",
    )
    sandbox_id, result = _copy(chain, world.runtime, "Late in a closed period", clock=clock)
    assert result["state"] == "SUCCEEDED", result["problem"]
    counts = result["result"]["counts"]
    assert counts["groups_recomputed"] == 1 and counts["derived_mismatches"] == 0, load_outcome(
        counts
    )
    assert counts["blocked_periods"] == 1
    report = _load_report(sandbox_id, world.runtime, keyring)
    assert (report["compared"], report["mismatches"]) == (1, [])
    assert [b["period_state_id"] for b in report["blocked_periods"]] == [
        str(chain.january_state_id)
    ]
    assert _state_map(world.tenant_id)[chain.january_state_id][0] == "closed"
    assert _state_map(sandbox_id)[chain.january_state_id] == ("closing", None)
    ledger, replayed = _revenue_by_period(world.tenant_id), _revenue_by_period(sandbox_id)
    assert sum(ledger.values()) == sum(replayed.values()) != 0  # the same revenue in total
    assert ledger != replayed  # carried in other periods: not SBX-05's subject
    assert ledger[chain.january_id] != replayed[chain.january_id]


def _approved_estimate(
    world: ReportWorld,
    *,
    element: str,
    kind: str,
    obligation_key: str | None,
    effective: str,
    amount: str = "0.00",
) -> tuple[UUID, UUID]:
    """An estimated element of Pellworth's contract with its version 1 of ``amount`` (most likely
    amount, unconstrained), through the product's commands: Maya creates the element — on
    ``obligation_key``, or contract-level — and the version, gives it what its submission asks
    (04 §16.14 rev 1.241: its evidence and the ``CONSTRAINT`` record of the element, a record of
    the version that Priya reviews) and submits it, and Priya (Revenue Reviewer) approves it,
    which appends ``ESTIMATE_CHANGED`` naming the version and recomputes the group. Returns
    (estimate id, version id)."""
    contract_id = world.contracts[K01].contract["id"]
    body: dict[str, Any] = {
        "estimate_kind": "VARIABLE_CONSIDERATION",
        "element_code": element,
        "vc_element_type": kind,
        "method": "MOST_LIKELY_AMOUNT",
    }
    if obligation_key is not None:
        body["obligation_key"] = obligation_key
    created = post(world.app, f"/api/v1/contracts/{contract_id}/estimates", world.maya, body)
    assert created.status_code == 201, created.text
    drafted = post(
        world.app,
        f"/api/v1/estimates/{created.json()['id']}/versions",
        world.maya,
        {
            "effective_date": effective,
            "scenarios": [{"outcome": "The most likely outcome", "amount": amount}],
            "unconstrained_amount": amount,
            "most_conservative_amount": amount,
            "constrained_amount": amount,
            "rationale": "Assessed with the delivery team at the reporting date.",
        },
    )
    assert drafted.status_code == 201, drafted.text
    version_id = str(drafted.json()["id"])
    estimate_version_ready(
        world.app, world.maya, version_id, constraint_of=element, reviewer=world.priya
    )
    sent = post(
        world.app, f"/api/v1/estimate-versions/{version_id}/submit", world.maya, {"comment": "OK"}
    )
    assert sent.status_code == 200, sent.text
    decided = approve(world.app, str(sent.json()["approval_request_id"]), world.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    return UUID(str(created.json()["id"])), UUID(version_id)


def test_an_event_naming_an_estimate_version_loads_with_it(
    committed_db: TestDatabase,
    app: FastAPI,
    files: LocalFileStore,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """05 SBX-04 rev 1.50 (supervisor ruling R-43 (b)) — the row-ordered ``stream`` component.
    Pellworth's contract gains two estimated elements through the product's commands, each with
    an APPROVED version 1: a contract-level rebate and a bonus on obligation O2. Each approval
    appended an ``ESTIMATE_CHANGED`` event naming its version — ``contract_event`` is IM-A, the
    version names its estimate, the second estimate names an obligation, and the obligation names
    the event that created it, so no table order and no fixup UPDATE can restore the reference
    (before slice 2 this load FAILED: 42501 on ``UPDATE contract_event SET estimate_version_id``).

    The component loads as one unit: the load SUCCEEDS; both events name their versions in the
    sandbox; every event equals its source row but for the DB-08 stamps, and the stream keeps its
    order; obligations, estimates and estimate versions equal their source rows outright (each
    arrived complete, nothing was UPDATEd); the five tables took ONE copy-phase transaction,
    ``load-stream``; and the group recomputes and verifies."""
    world = _k01_world(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")
    _, rebate_version = _approved_estimate(
        world, element="REBATE-PW-01", kind="REBATE", obligation_key=None, effective="2026-03-01"
    )
    bonus, bonus_version = _approved_estimate(
        world, element="BONUS-GOLIVE-01", kind="BONUS", obligation_key="O2", effective="2026-03-01"
    )
    chain = _unlocked(world)
    assert chain.group_id is not None
    computed(world.place, chain.group_id)  # the source's version carries both elements
    sandbox_id, result = _copy(chain, world.runtime, "Stream component", clock=clock)
    assert result["state"] == "SUCCEEDED", result["problem"]
    counts = result["result"]["counts"]
    assert counts["groups_recomputed"] == 1 and counts["groups_not_recomputed"] == 0
    assert counts["derived_mismatches"] == 0, load_outcome(counts)
    events = _copied_rows(world.tenant_id, "contract_event")
    replayed = _copied_rows(sandbox_id, "contract_event")
    assert set(replayed) == set(events)
    stamps = {"recorded_at", "record_seq"}  # DB-08: the sandbox's own
    for key, row in replayed.items():
        assert {c: v for c, v in row.items() if c not in stamps} == {
            c: v for c, v in events[key].items() if c not in stamps
        }, key
    assert sorted(events, key=lambda key: events[key]["record_seq"]) == sorted(
        replayed, key=lambda key: replayed[key]["record_seq"]
    )
    named = {
        str(row["event_type"]): row["estimate_version_id"]
        for row in replayed.values()
        if row["estimate_version_id"] is not None
    }
    assert set(named) == {"ESTIMATE_CHANGED"}
    assert {row["estimate_version_id"] for row in replayed.values()} - {None} == {
        rebate_version,
        bonus_version,
    }
    for name in ("obligation", "estimate", "estimate_version", "manual_adjustment"):
        assert _copied_rows(sandbox_id, name) == _copied_rows(world.tenant_id, name), name
    estimates = _copied_rows(sandbox_id, "estimate")
    obligations = _copied_rows(sandbox_id, "obligation")
    assert len(estimates) == 2 and len(_copied_rows(sandbox_id, "estimate_version")) == 2
    assert estimates[str(bonus)]["obligation_id"] is not None  # the chain through an obligation
    assert str(estimates[str(bonus)]["obligation_id"]) in obligations
    # one copy-phase transaction for the whole component, none per member table
    prefix = f"job-{result['id']}-"
    with identity_session(request_id="tests-stream-component") as session:
        steps = [
            str(request_id).removeprefix(prefix)
            for request_id in session.scalars(
                select(security_event.c.request_id).where(
                    security_event.c.tenant_id == sandbox_id,
                    security_event.c.kind == "PLATFORM_SCOPE_USED",
                )
            )
        ]
    component = sd.COMPONENTS["contract_event"]
    assert steps.count(f"load-{component.name}") == 1
    assert not {f"load-{name}" for name in component.tables} & set(steps)


# STAMPS-1 (Codex 1824 §1; D-98 137 amendment 7): a finalized membership row carries the sandbox's
# own
# DB-02 stamps — these two columns are excluded from the exact comparison BY NAME and asserted by
# their relations instead (row_version = source + 1; updated_at later than the source's).
_DB02_STAMPS = frozenset({"updated_at", "row_version"})


def _membership_rows(tenant_id: UUID, user_ids: tuple[UUID, ...]) -> dict[UUID, dict[str, Any]]:
    """The memberships of ``user_ids`` by id, every column but the remapped tenant."""
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return {
            UUID(str(r["id"])): {k: v for k, v in dict(r).items() if k not in _REMAPPED}
            for r in session.execute(
                select(tenant_membership).where(tenant_membership.c.user_id.in_(user_ids))
            ).mappings()
        }


def _without_stamps(rows: dict[UUID, dict[str, Any]]) -> dict[UUID, dict[str, Any]]:
    return {k: {c: v for c, v in row.items() if c not in _DB02_STAMPS} for k, row in rows.items()}


def _assert_membership_restored(
    source: dict[UUID, dict[str, Any]], restored: dict[UUID, dict[str, Any]], *, finalized: UUID
) -> None:
    """Every column equal but the remapped tenant and the DB-02 stamps; on the FINALIZED row
    ``row_version`` = source + 1 and ``updated_at`` later than the source's (the finalization
    instant); on a row that needed no finalization the stamps are equal (STAMPS-1)."""
    assert _without_stamps(restored) == _without_stamps(source)
    for membership_id, row in restored.items():
        before = source[membership_id]
        if membership_id == finalized:
            assert row["row_version"] == before["row_version"] + 1
            assert row["updated_at"] > before["updated_at"]
        else:
            assert (row["row_version"], row["updated_at"]) == (
                before["row_version"],
                before["updated_at"],
            )


def _suspended_chain(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> tuple[Chain, dict[UUID, dict[str, Any]]]:
    """The light chain (the lock APPROVED by cora), then cora suspended by the workspace admin
    through the product's ``POST /users/{id}/suspend``; returns the chain and the source
    membership rows of cora and the admin."""
    chain = _chain(keyring, clock)
    assign(chain.admin, "tenant_admin")  # user.manage (MFA) for the suspension
    admin = enrolled(app, clock, chain.admin)
    suspended = post(
        app,
        f"/api/v1/users/{chain.cora.membership_id}/suspend",
        admin,
        {"reason": "Left the revenue team in September"},
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "SUSPENDED"
    source = _membership_rows(chain.admin.tenant_id, (chain.cora.user_id, chain.admin.user_id))
    assert source[chain.cora.membership_id]["status"] == "SUSPENDED"
    return chain, source


def test_suspended_approver_s_decision_is_restored(
    committed_db: TestDatabase,
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """MEMBERSHIP-1 (Codex 1757 §1; D-98 137 amendment 6): the January lock is APPROVED by cora,
    then the workspace admin suspends cora through the product's ``POST /users/{id}/suspend``
    (her source membership SUSPENDED); the export and the load run with the admin as the active
    requester. The live 0013 guard requires the approver's CURRENT membership ACTIVE, so the
    loader restores cora's membership in its activation state, loads the approval graphs under the
    guard and applies her final SUSPENDED status after: the restored graphs equal the source
    exactly, her membership row equals the source row (SUSPENDED, the exported stamps), the
    requester's is ACTIVE — no permanent reactivation, no omitted or re-approved decision."""
    chain, source_memberships = _suspended_chain(app, keyring, clock)
    runtime = _runtime(app_settings, keyring, clock)
    sandbox_id, result = _copy(chain, runtime, "Suspended approver", clock=clock)
    assert result["state"] == "SUCCEEDED", result["problem"]
    _assert_approval_graph_restored(sandbox_id, chain)  # cora's decisions, exactly
    restored = _membership_rows(sandbox_id, (chain.cora.user_id, chain.admin.user_id))
    _assert_membership_restored(source_memberships, restored, finalized=chain.cora.membership_id)
    assert restored[chain.cora.membership_id]["status"] == "SUSPENDED"
    assert restored[chain.admin.membership_id]["status"] == "ACTIVE"


def test_early_refusal_before_any_graph_leaves_no_member_reactivated(
    committed_db: TestDatabase,
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MEMBERSHIP-REFUSAL-1 (Codex 1824 §1 and 1834 §2; D-98 137 amendment 7): an EARLY supported
    refusal — after the membership load, BEFORE any approval graph — injected at the loader's pure
    ``graph_batches`` seam (a named substitution: the parse / not_loadable exit every graph passes
    through) fails the job with the ORIGINAL refusal (``SNAPSHOT_NOT_LOADABLE`` naming the graph
    inconsistency) and leaves cora's copied membership at its final status in the sandbox:
    SUSPENDED with the held fields, the sandbox's DB-02 stamps — never ACTIVE behind a refused
    load."""
    chain, source_memberships = _suspended_chain(app, keyring, clock)

    def refuse(*_: Any, **__: Any) -> Any:
        raise ValueError("injected refusal after the membership load")

    monkeypatch.setattr(sb, "graph_batches", refuse)
    runtime = _runtime(app_settings, keyring, clock)
    sandbox_id, result = _copy(chain, runtime, "Refused after memberships", clock=clock)
    assert result["state"] == "FAILED", result
    assert result["problem"] is not None
    assert "injected refusal" in json.dumps(result["problem"])
    assert sb.RULE_NOT_LOADABLE in json.dumps(result["problem"])
    restored = _membership_rows(sandbox_id, (chain.cora.user_id, chain.admin.user_id))
    _assert_membership_restored(source_memberships, restored, finalized=chain.cora.membership_id)
    assert restored[chain.cora.membership_id]["status"] == "SUSPENDED"
    assert restored[chain.admin.membership_id]["status"] == "ACTIVE"
    with tenant_session(_context(sandbox_id), read_only=True) as session:
        graphs = session.execute(select(func.count()).select_from(approval_request)).scalar_one()
    assert graphs == 0  # the refusal preceded every graph


def test_late_refusal_between_graphs_leaves_no_member_reactivated(
    committed_db: TestDatabase,
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MEMBERSHIP-REFUSAL-1, the LATE case (Codex 1834 §2): a supported refusal BETWEEN graphs —
    the DB-03 kernel refusing the second request's finalization (a named substitution at
    ``transitions.apply``, the seam every graph's finalization passes through; the first graph is
    already committed) — fails the job with the ORIGINAL ``invalid-transition`` refusal; the first
    request is restored APPROVED, the second and third are absent (their transaction rolled back),
    and cora's membership is SUSPENDED with the held fields and the DB-02 stamps — never ACTIVE."""
    from erev_api.db import transitions as tx_kernel

    chain, source_memberships = _suspended_chain(app, keyring, clock)
    original = tx_kernel.apply
    second = chain.requests[1]  # the reopen request: the second graph by submission order

    def refuse_second(session: Any, table: str, row_id: UUID, **kwargs: Any) -> Any:
        if table == "approval_request" and row_id == second:
            raise Problem("invalid-transition", "injected late refusal between graphs")
        return original(session, table, row_id, **kwargs)

    monkeypatch.setattr(tx_kernel, "apply", refuse_second)
    runtime = _runtime(app_settings, keyring, clock)
    sandbox_id, result = _copy(chain, runtime, "Refused between graphs", clock=clock)
    assert result["state"] == "FAILED", result
    assert "injected late refusal" in json.dumps(result["problem"])
    assert "invalid-transition" in json.dumps(result["problem"])
    restored = _membership_rows(sandbox_id, (chain.cora.user_id, chain.admin.user_id))
    _assert_membership_restored(source_memberships, restored, finalized=chain.cora.membership_id)
    assert restored[chain.cora.membership_id]["status"] == "SUSPENDED"
    graphs = _approval_graph(sandbox_id, chain.requests)
    assert set(graphs["requests"]) == {chain.requests[0]}  # the first graph committed, finalized
    assert graphs["requests"][chain.requests[0]]["status"] == "APPROVED"
    assert {d["approval_request_id"] for d in graphs["decisions"].values()} == {chain.requests[0]}


# FIX-D1: the columns in which a copied row may differ from its source row, and why. Exact — a
# column that stops differing leaves this table, a new one is explained here first.
# What DB-02 moves on a row its transaction updates. ``updated_by`` and ``updated_by_kind`` left
# this set with 05 TXN-10 rev 1.82 (supervisor rulings R-95 and R-103 (b)): a computation writes
# the heads below as SYSTEM in the source as in the sandbox, whoever's command asked for it —
# until then the source's synchronous computation stamped its caller, and the two differed.
_SC_M = frozenset({"updated_at", "row_version"})
_RESTAMPED: dict[str, frozenset[str]] = {
    # DB-08: the sandbox's own record time and sequence — "known at copy time" (05 SBX-04)
    "contract_event": frozenset({"recorded_at", "record_seq"}),
    # restored by the fixup step: an UPDATE, so DB-02 stamps the row (row_version = source + 1)
    "pob_template_version": frozenset({"updated_at", "row_version"}),
    # the recompute names the sandbox's own computation and DB-02 stamps the row
    "combination_group": frozenset({"head_computation_id"}) | _SC_M,
    "contract": frozenset({"latest_computation_id"}) | _SC_M,
}
# Columns that MAY differ and are asserted neither way: the numbers the sandbox's own activity
# draws. The load's warning items (SANDBOX_DETERMINISM_MISMATCH, SANDBOX_REPLAY_BLOCKED) take one
# from the EXCEPTION series each when they are raised — whether one is raised is not this
# witness's subject.
_SANDBOX_DRAWN: dict[str, frozenset[str]] = {"numbering_series": frozenset({"next_value"})}


def _copied_rows(tenant_id: UUID, name: str) -> dict[str, dict[str, Any]]:
    """Every row of the copied table ``name`` by its identity, without the remapped tenant."""
    table = metadata.tables[f"erev.{name}"]
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return {
            sd.row_identity(name, row): {k: v for k, v in dict(row).items() if k not in _REMAPPED}
            for row in session.execute(select(table)).mappings()
        }


def test_every_copied_row_equals_its_source_row_except_the_stated_columns(
    committed_db: TestDatabase,
    app: FastAPI,
    files: LocalFileStore,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    job: ModuleType,
) -> None:
    """The copy phase, row for row, on the product-built k01 world: every COPIED table of the
    sandbox holds exactly the source's rows by identity, equal on every column except the
    remapped tenant and the columns ``_RESTAMPED`` names with their reason (a series counter the
    sandbox may draw from is compared neither way, ``_SANDBOX_DRAWN``). This pins what the
    loader does with the references the database freezes: a self-reference and an
    ``approval_request_id`` on an IM-S / IM-A row arrive WITH the row (nothing stamped, so the
    row is equal outright), a lifecycle reference of an IM-P version is restored by the fixup
    step (``pob_template_version.approval_request_id`` — equal, the row DB-02-stamped), and a
    GENERATED column is derived again by the database to the same value
    (``account_mapping_rule.specificity``)."""
    world = _k01_world(app, keyring, clock, files)
    marcus = world.marcus.member
    chain = Chain(
        admin=marcus,
        cora=marcus,
        priya=marcus,
        entity_id=world.entity_id,
        january_state_id=UUID(int=0),
        february_state_id=UUID(int=0),
        january_id=UUID(int=0),
        transitions={},
        lock_id=UUID(int=0),
        reopen_id=UUID(int=0),
        relock_id=UUID(int=0),
        requests=(),
        group_id=UUID(str(world.contracts[K01].combination_group["id"])),
        requester=marcus,
    )
    sandbox_id, result = _copy(chain, world.runtime, "Row for row", clock=clock)
    assert result["state"] == "SUCCEEDED", result["problem"]
    differing: dict[str, set[str]] = {}
    populated: set[str] = set()
    for dataset in sd.inventory().datasets:
        if dataset.snapshot_class is not sd.SnapshotClass.COPIED:
            continue
        name = dataset.name
        source, copied = _copied_rows(world.tenant_id, name), _copied_rows(sandbox_id, name)
        if name == "file_object":
            # a file no copied row references never leaves the source (snapshot_export; 05
            # SBX-03): the snapshot's own dataset files and manifest, and the outputs of the
            # source's report runs (reports are never copied); the load report is the sandbox's
            source_only = {source[key]["purpose"] for key in set(source) - set(copied)}
            sandbox_only = {copied[key]["purpose"] for key in set(copied) - set(source)}
            assert source_only == {"SNAPSHOT_DATASET", "REPORT_OUTPUT"}
            assert sandbox_only == {"AUDIT_DIGEST"}
            source = {key: row for key, row in source.items() if key in copied}
            copied = {key: row for key, row in copied.items() if key in source}
        assert set(copied) == set(source), name
        if copied:
            populated.add(name)
        for key, row in copied.items():
            for column, value in row.items():
                if column in _SANDBOX_DRAWN.get(name, ()):
                    continue
                if source[key][column] != value:
                    differing.setdefault(name, set()).add(column)
    assert differing == {name: set(columns) for name, columns in _RESTAMPED.items()}
    # the world exercises each mechanism (a vacuous equality would prove nothing)
    assert {
        "role_assignment",
        "approval_request",
        "approval_decision",
        "registry_version",
        "account_mapping_rule",
        "pob_template_version",
        "contract_event",
        "obligation",
    } <= populated
    templates = _copied_rows(world.tenant_id, "pob_template_version")
    restored = _copied_rows(sandbox_id, "pob_template_version")
    requests = _copied_rows(sandbox_id, "approval_request")
    for key, row in restored.items():
        assert row["approval_request_id"] is not None  # published through an approval
        assert str(row["approval_request_id"]) in requests
        assert row["row_version"] == templates[key]["row_version"] + 1  # one fixup UPDATE
    grants = _copied_rows(sandbox_id, "role_assignment").values()
    assert {str(g["approval_request_id"]) for g in grants if g["approval_request_id"]} <= set(
        requests
    )
    assert any(g["approval_request_id"] is not None for g in grants)
    assert _copied_rows(sandbox_id, "account_mapping_rule")  # its generated column is equal
    # DB-08: the stream keeps its order — the sandbox's new record_seq ranks as the source's did
    events = _copied_rows(world.tenant_id, "contract_event")
    replayed = _copied_rows(sandbox_id, "contract_event")
    assert sorted(events, key=lambda key: events[key]["record_seq"]) == sorted(
        replayed, key=lambda key: replayed[key]["record_seq"]
    )
    assert min(row["record_seq"] for row in replayed.values()) > max(
        row["record_seq"] for row in events.values()
    )
