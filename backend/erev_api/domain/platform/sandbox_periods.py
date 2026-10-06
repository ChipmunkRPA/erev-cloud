"""The SBX-04 period replay of a sandbox load (05 §10 SBX-04; 04 T-REF-06 / T-REF-07 and DB-07,
T-CLS-04 and D-98 61; D-98 candidate 137 amendment 3 — Codex production-20260921-1623 §1 PERIOD-1
/ REPLAY-2 / LOCK-3).

``prepare`` takes the three REPLAY_REFERENCE populations DECODED BY THEIR SCHEMA (the loader's
``typed_references``; REPLAY-2), builds the validated plan of ``snapshot_replay`` (identity,
chronology, lock consistency), checks it against the exported end state (``verify_end_state``) and
pairs every lock-bearing transition with its lock — all before any write, refusing by ``ValueError``
that the loader names. ``execute`` then runs every step through the close domain's governed
mutable-period path: the transition row first and the state update after it (DB-07), the lock row
first for a lock (the 0047 deferred key, D-98 61), with the normal guards — the requesting user's
copied membership and its permissions, ``period_machine.decide`` on the COPIED approval evidence
(preparer, approver, the approver's recorded MFA time at the decision), the fourteen close gates
evaluated in the sandbox, BR-CLS-05 and the permanent-lock order (PERIOD-1, LOCK-3). One gate is
taken from the source: ``CLOSE_RUN_COMPLETED`` (item CLO-GATE-RUN-1; supervisor ruling R-116 (e)). A
sandbox copies no close run — the source's are derived and the sandbox runs its own — so the
replay of a source lock lays the result that lock certified over the sandbox's evaluation of this
gate alone and marks it ``replayed`` in the sandbox lock's certification; a source lock that
certified no such result leaves the sandbox's own evaluation, which refuses the lock by name. Lock,
transition, previous-lock and current-lock identities are the source's; timestamps and the acting
principal are the load's. A refusal of a normal command — a ``Problem``, or the database's own named
guard (SQLSTATE P0001 ``EREV-…``) — leaves the period at its last reachable state and is reported
as a ``BlockedPeriod`` (ruling (3)); every other error propagates: a parser or programming error is
never disguised as that business refusal. ``BR-CLS-03`` (the next period opens at a lock) is not
re-run here: the source's own ``future → open`` transition of that period is a step of the plan.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from erev_api.approvals import engine as approvals
from erev_api.approvals import subjects
from erev_api.audit import writer as audit_writer
from erev_api.auth.dependencies import require_for_entity
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    entity_book,
    period_state,
    period_state_transition,
)
from erev_api.domain.close import (
    certification,
    dependencies,
    freeze,
    gates,
    period_machine,
    relock_diff,
    snapshots,
)
from erev_api.domain.close import commands as close
from erev_api.domain.platform import setup
from erev_api.domain.platform import snapshot_replay as replay
from erev_api.domain.platform.attachments import authorize
from erev_api.domain.platform.snapshot_replay import BlockedPeriod, ReplayStep
from erev_api.domain.reference import periods as period_rules
from erev_api.enums import (
    ApprovalDecisionKind,
    ChecklistStatus,
    ControlResult,
    LockKind,
    NotificationKind,
    PeriodState,
    PrincipalKind,
    ReasonCode,
)
from erev_api.events.notifications import notify, role_holders
from erev_api.jobs.context import system_unit_of_work
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.auth.principal import Principal
    from erev_api.jobs.context import JobRuntime
    from erev_api.uow import UnitOfWork

__all__ = [
    "REFERENCE_DATASETS",
    "BlockedPeriod",
    "Paired",
    "Prepared",
    "Replay",
    "ReplayResult",
    "blocked_reason",
    "execute",
    "open_step",
    "pair_steps",
    "prepare",
]

# The REPLAY_REFERENCE datasets, in the registry's order (snapshot_dataset.RULES).
REFERENCE_DATASETS: Final = ("period_state", "period_state_transition", "period_lock")
REPLAY_COMMENT: Final = "Replayed from the source at the sandbox load (SBX-04)."
_LOCK_STATES: Final = frozenset(replay.LOCK_TARGETS.values())
_KIND_OF_STATE: Final[Mapping[PeriodState, LockKind]] = {
    target: kind for kind, target in replay.LOCK_TARGETS.items()
}


@dataclass(frozen=True, slots=True)
class Paired:
    """One transition step and, for a lock-bearing transition, the lock step it creates."""

    step: ReplayStep
    lock: ReplayStep | None


@dataclass(frozen=True, slots=True)
class Prepared:
    """The validated plan of a replay, before any write."""

    states: tuple[Mapping[str, Any], ...]
    transitions: Mapping[UUID, Mapping[str, Any]]
    locks: Mapping[UUID, Mapping[str, Any]]
    plan: tuple[ReplayStep, ...]
    paired: tuple[Paired, ...]


@dataclass(frozen=True, slots=True)
class ReplayResult:
    applied: int
    blocked: tuple[BlockedPeriod, ...]
    reached: Mapping[UUID, tuple[str, UUID | None]]  # per period state: (state, current lock)


def _ends_soft_close_under_reopen(step: ReplayStep) -> bool:
    """``closing → reopened`` (04 T-REF-07 rev 1.170): the end of a soft close of a period that
    had been locked before. It reaches a state the lock kinds target and writes no
    ``period_lock`` row — the period stays under its ``REOPEN`` record."""
    return (
        step.from_state is PeriodState.CLOSING
        and step.to_state is period_machine.CANCEL_CLOSE_AFTER_LOCK
    )


def pair_steps(plan: Iterable[ReplayStep]) -> tuple[Paired, ...]:
    """Pair each lock-bearing transition (to ``closed``, ``permanently_locked``, or to
    ``reopened`` from ``closed``) with the lock step that immediately follows it; ``ValueError``
    names a transition to a locked state without its lock, or a lock step without its
    transition. ``closing → reopened`` bears no lock (``_ends_soft_close_under_reopen``): it is
    paired with none and replays through ``_move``."""
    steps = tuple(plan)
    paired: list[Paired] = []
    index = 0
    while index < len(steps):
        step = steps[index]
        if step.kind == "lock":
            raise ValueError(f"period_lock {step.id}: a lock step without its transition")
        if step.to_state in _LOCK_STATES and not _ends_soft_close_under_reopen(step):
            following = steps[index + 1] if index + 1 < len(steps) else None
            if (
                following is None
                or following.kind != "lock"
                or following.transition_id != step.id
                or following.lock_kind is None
                or replay.LOCK_TARGETS[following.lock_kind] is not step.to_state
            ):
                raise ValueError(
                    f"period_state_transition {step.id}: a transition to {step.to_state} "
                    "without its period_lock row"
                )
            paired.append(Paired(step, following))
            index += 2
            continue
        paired.append(Paired(step, None))
        index += 1
    return tuple(paired)


def prepare(references: Mapping[str, Sequence[Mapping[str, Any]]]) -> Prepared:
    """The validated plan over TYPED reference rows (REPLAY-2); ``ValueError`` names the first
    inconsistency — of the datasets (the planner), of the exported end state (``verify_end_state``)
    or of the lock pairing — before any write."""
    states = tuple(references.get("period_state", ()))
    transitions = tuple(references.get("period_state_transition", ()))
    locks = tuple(references.get("period_lock", ()))
    plan = replay.replay_plan(states, transitions, locks)
    findings = replay.verify_end_state(plan, states)
    if findings:
        raise ValueError(
            "the exported transitions do not reproduce the exported period states: "
            + "; ".join(findings)
        )
    return Prepared(
        states=states,
        transitions={UUID(str(row["id"])): row for row in transitions},
        locks={UUID(str(row["id"])): row for row in locks},
        plan=plan,
        paired=pair_steps(plan),
    )


def blocked_reason(error: BaseException) -> str | None:
    """The reason when ``error`` is a normal command's refusal — a ``Problem``, or the database's
    own named guard (SQLSTATE P0001 with an ``EREV-`` message: DB-07 ``EREV-PER-001``, the posting
    guard) — else None: any other error is a defect and propagates."""
    if isinstance(error, Problem):
        rules = sorted({e.rule_id for e in error.errors if e.rule_id})
        text = error.detail or error.title
        suffix = f" [{', '.join(rules)}]" if rules else ""
        return f"{error.slug}{suffix}: {text}"[:400]
    if isinstance(error, sa.exc.DBAPIError):
        original = error.orig
        diag = getattr(original, "diag", None)
        sqlstate = getattr(original, "sqlstate", None) or getattr(diag, "sqlstate", None)
        message = str(original).splitlines()[0] if original is not None else ""
        if sqlstate == "P0001" and "EREV-" in message:
            return message[:400]
    return None


# --- execution ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Evidence:
    """The copied approval evidence a lock or reopen is replayed with."""

    request_id: UUID
    preparer_id: UUID | None
    comment: str | None
    reason_code: ReasonCode | None
    decided_at: Any
    approver_id: UUID | None
    mfa_verified_at: Any


def _evidence(session: Session, request_id: UUID) -> _Evidence:
    request = (
        session.execute(
            select(
                approval_request.c.preparer_id,
                approval_request.c.comment,
                approval_request.c.reason_code,
                approval_request.c.decided_at,
                approval_request.c.status,
            ).where(approval_request.c.id == request_id)
        )
        .mappings()
        .one_or_none()
    )
    if request is None:
        raise Problem(
            "not-found", f"the approval request {request_id} of the source lock was not copied."
        )
    decision = (
        session.execute(
            select(
                approval_decision.c.approver_id,
                approval_decision.c.mfa_verified_at,
                approval_decision.c.decided_at,
            )
            .where(
                approval_decision.c.approval_request_id == request_id,
                approval_decision.c.decision == ApprovalDecisionKind.APPROVE.value,
                approval_decision.c.approver_kind == PrincipalKind.USER.value,
            )
            .order_by(approval_decision.c.decided_at.desc(), approval_decision.c.id.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    reason = request["reason_code"]
    return _Evidence(
        request_id=request_id,
        preparer_id=None if request["preparer_id"] is None else UUID(str(request["preparer_id"])),
        comment=request["comment"],
        reason_code=None if reason is None else ReasonCode(str(getattr(reason, "value", reason))),
        decided_at=request["decided_at"],
        approver_id=None
        if decision is None or decision["approver_id"] is None
        else UUID(str(decision["approver_id"])),
        mfa_verified_at=None if decision is None else decision["mfa_verified_at"],
    )


def _no_approver(evidence: _Evidence) -> Problem:
    message = (
        f"no approving decision of request {evidence.request_id} was copied; the lock cannot "
        "be replayed the same way."
    )
    return Problem(
        "invalid-transition",
        message,
        errors=[ProblemError(rule_id=period_rules.RULE_TRANSITION, message=message)],
    )


def _scope(uow: UnitOfWork, step: ReplayStep) -> gates.PeriodScope:
    """The locked scope of the step's period state, the close permission held for its entity."""
    scope = gates.period_scope(uow.session, step.period_state_id, lock=True)
    if scope is None:
        raise Problem("not-found")
    require_for_entity(uow.ctx, period_rules.CLOSE_PERMISSION, scope.entity_id)
    return scope


def _current(scope: gates.PeriodScope) -> dict[str, Any]:
    return {
        "entity_id": scope.entity_id,
        "book_code": scope.book_code,
        "period_id": scope.period_id,
        "row_version": scope.row_version,
    }


def _expect_state(scope: gates.PeriodScope, step: ReplayStep) -> None:
    """The DB-07 pair the step names must start from the state the sandbox reached."""
    if step.from_state is not None and PeriodState(scope.state) is not step.from_state:
        message = (
            f"{scope.period_key} is {scope.state}; the source moved it from "
            f"{step.from_state.value} to {step.to_state}."
        )
        raise Problem(
            "invalid-transition",
            message,
            errors=[ProblemError(rule_id=period_rules.RULE_TRANSITION, message=message)],
        )


def _expect_previous_lock(scope: gates.PeriodScope, lock: ReplayStep) -> None:
    """The source lock's ``previous_lock_id`` is the lock the sandbox currently holds — an
    identity the replay preserved earlier; a difference is a defect, never a refusal."""
    if scope.current_lock_id != lock.previous_lock_id:
        raise RuntimeError(
            f"period_lock {lock.id}: previous_lock_id {lock.previous_lock_id} but the sandbox's "
            f"current lock is {scope.current_lock_id}"
        )


def _comment(prepared: Prepared, step: ReplayStep) -> str | None:
    row = prepared.transitions.get(step.id)
    value = None if row is None else row.get("comment")
    return REPLAY_COMMENT if value is None else str(value)


def _create_states(uow: UnitOfWork, prepared: Prepared, creations: Sequence[ReplayStep]) -> None:
    """Every source period state as ``future`` with its source id, then the plan's NULL → future
    transitions with their source ids (the ``_sync_period_states`` shape of the reference
    domain), summarised in one AUD-FACT."""
    principal = uow.principal
    for row in prepared.states:
        uow.session.execute(
            insert(period_state).values(
                tenant_id=principal.tenant_id,
                id=UUID(str(row["id"])),
                entity_id=UUID(str(row["entity_id"])),
                book_code=str(row["book_code"]),
                period_id=UUID(str(row["period_id"])),
                period_end_date=row["period_end_date"],
                state=PeriodState.FUTURE.value,
                current_lock_id=None,
                state_changed_at=uow.now,
                updated_at=uow.now,
                updated_by=principal.id,
                updated_by_kind=principal.kind.value,
            )
        )
    for step in creations:
        uow.session.execute(
            insert(period_state_transition).values(
                tenant_id=principal.tenant_id,
                id=step.id,
                period_state_id=step.period_state_id,
                entity_id=step.entity_id,
                book_code=step.book_code,
                period_id=step.period_id,
                from_state=None,
                to_state=PeriodState.FUTURE.value,
                reason_code=None,
                comment=_comment(prepared, step),
                created_at=uow.now,
                created_by=principal.id,
                created_by_kind=principal.kind.value,
            )
        )
    if creations:
        audit_writer.record_facts(
            uow,
            action=period_rules.CREATE_TRANSITIONS_ACTION,
            object_type=period_rules.TRANSITION_OBJECT,
            ids=[step.id for step in creations],
            detail={"to_state": PeriodState.FUTURE.value, "replayed": True},
        )


def _open(uow: UnitOfWork, prepared: Prepared, step: ReplayStep) -> None:
    """``future → open`` as ``reference.commands.open_period`` does: API-R-18 authorisation, the
    state ``future``, the book kept, then the transition row and the state update."""
    session = uow.session
    completed = setup.rule_ended(uow)
    authorize(
        uow.ctx,
        period_rules.open_permissions(setup_completed=completed),
        keyring=uow.keyring,
        action=period_rules.OPEN_ACTION,
        object_type=period_rules.STATE_OBJECT,
        object_id=step.period_state_id,
    )
    scope = gates.period_scope(session, step.period_state_id, lock=True)
    if scope is None:
        raise Problem("not-found")
    _expect_state(scope, step)
    kept = session.execute(
        select(entity_book.c.is_enabled).where(
            entity_book.c.entity_id == scope.entity_id,
            entity_book.c.book_code == scope.book_code,
        )
    ).scalar_one_or_none()
    if kept is not True:
        message = f"{scope.entity_code} does not keep the book {scope.book_code}."
        raise Problem(
            "invalid-transition",
            message,
            errors=[ProblemError(rule_id=period_rules.RULE_TRANSITION, message=message)],
        )
    close._record_transition(  # noqa: SLF001 — the close domain's DB-07 writer (Codex 1623 §1)
        uow,
        state_id=step.period_state_id,
        current=_current(scope),
        from_state=PeriodState.FUTURE,
        to_state=PeriodState.OPEN,
        action=period_rules.OPEN_ACTION,
        reason_code=None,
        comment=_comment(prepared, step),
        transition_id=step.id,
    )


def _move(uow: UnitOfWork, prepared: Prepared, step: ReplayStep) -> None:
    """``open`` / ``reopened → closing`` and the end of a soft close — ``closing → open`` or, for a
    period that had been locked before, ``closing → reopened`` (04 T-REF-07 rev 1.170) — as
    ``close.commands.start_close`` and ``cancel_close`` do (permission, the allowed pair, the
    reason subset). The replay writes the pair the source recorded: a history written before
    rev 1.170 ends a reopened period's soft close in ``open``, and that pair stays a DB-07 pair."""
    scope = _scope(uow, step)
    _expect_state(scope, step)
    state = PeriodState(scope.state)
    reason: ReasonCode | None = None
    if step.to_state is PeriodState.CLOSING:
        if state not in close.START_FROM:
            message = close.NOT_STARTABLE.format(period_key=scope.period_key, state=state.value)
            raise Problem(
                "invalid-transition",
                message,
                errors=[ProblemError(rule_id=period_rules.RULE_TRANSITION, message=message)],
                code=close.TRANSITION_CODE,
            )
        action = close.START_CLOSE_ACTION
    elif state is PeriodState.CLOSING and step.to_state in (
        PeriodState.OPEN,
        period_machine.CANCEL_CLOSE_AFTER_LOCK,
    ):
        reason = None if step.reason_code is None else ReasonCode(step.reason_code)
        if reason not in close.CANCEL_CLOSE_REASONS:
            error = ProblemError(
                field="reason_code", rule_id=close.RULE_REASON, message=close.REASON_NOT_ALLOWED
            )
            raise Problem("validation-failed", "1 field needs attention.", errors=[error])
        action = close.CANCEL_CLOSE_ACTION
    else:
        message = f"{scope.period_key}: {state.value} → {step.to_state} is not a DB-07 pair."
        raise Problem(
            "invalid-transition",
            message,
            errors=[ProblemError(rule_id=period_rules.RULE_TRANSITION, message=message)],
        )
    assert step.to_state is not None
    close._record_transition(  # noqa: SLF001
        uow,
        state_id=step.period_state_id,
        current=_current(scope),
        from_state=state,
        to_state=step.to_state,
        action=action,
        reason_code=reason,
        comment=_comment(prepared, step),
        transition_id=step.id,
    )


def _gate_detail(
    certified: Sequence[gates.GateResult], uow: UnitOfWork, lock_id: UUID, cutoff: datetime
) -> dict[str, Any]:
    return {
        "gates": [
            {"gate_check_code": r.gate_check_code, "status": r.status.value, "count": r.count}
            for r in certified
        ],
        "evaluated_at": uow.now.isoformat(),
        "cutoff_known_at": cutoff.isoformat(),  # as `close.commands` records it (S15-R-18c)
        "period_lock_id": str(lock_id),
        "replayed": True,
    }


def _with_source_close_run(
    results: gates.GateResults, lock_row: Mapping[str, Any], *, passed_only: bool
) -> gates.GateResults:
    """``results`` with ``CLOSE_RUN_COMPLETED`` as the source lock certified it (module
    docstring): its status, count and evaluation time, marked ``replayed``; every other gate as the
    sandbox evaluated it. ``passed_only`` — a ``LOCK``, whose gates are judged — lays a ``PASSED``
    result alone. Without such a result in the source lock's certification ``results`` stay as
    they are."""
    code = gates.CLOSE_RUN_COMPLETED
    source = next(
        (row for row in lock_row.get("certification") or () if row.get("gate_check_code") == code),
        None,
    )
    if source is None:
        return results
    status = ChecklistStatus(str(source["status"]))
    if passed_only and status is not ChecklistStatus.PASSED:
        return results
    laid = tuple(
        dataclasses.replace(
            result,
            status=status,
            count=source.get("count"),
            detail=None,
            evaluated_at=datetime.fromisoformat(str(source["evaluated_at"])),
            replayed=True,
        )
        if result.gate_check_code == code
        else result
        for result in results
    )
    return gates.GateResults(laid, results.blocking_tasks)


def _lock(
    uow: UnitOfWork, paired: Paired, evidence: _Evidence, lock_row: Mapping[str, Any]
) -> None:
    """``closing → closed`` with a ``LOCK`` as ``close.commands._period_lock_approved`` does, on
    the copied evidence: the gates evaluated here, ``period_machine.decide`` with the preparer, the
    approver and the approver's recorded MFA time at the decision, the producers resolved by name,
    the datasets frozen, the lock row first (D-98 61), the snapshots, the gate results, the
    reconciliations, CTL-016, NTF-06 and the audit — with the source's lock and transition ids and
    without BR-CLS-03 (the plan carries the next period's own opening).

    The freeze is the product's (supervisor rulings R-19 and R-42 (e); ENGINE_SPEC_B S15-R-18c):
    the datasets are frozen at ``freeze.freeze_cutoff`` — the later of the application instant and
    this transaction's timestamp, the rule contract versions are stamped by — passed as ``known_at``
    and ``frozen_at``; a dataset the registry will not freeze and an artefact it will not reuse
    are refused by name; and ``freeze.assert_covered`` is asked after the freeze, before any lock
    write, and again as the last read. Each refusal is a ``Problem``, so the replay records the
    period as blocked (05 SBX-04) — it is never a defect disguised as one, and never a lock over
    datasets that do not hold the period."""
    step, lock = paired.step, paired.lock
    assert lock is not None
    session = uow.session
    scope = _scope(uow, step)
    _expect_state(scope, step)
    _expect_previous_lock(scope, lock)
    if evidence.approver_id is None:
        raise _no_approver(evidence)
    results = _with_source_close_run(
        gates.evaluate_gates(uow, scope.entity_id, scope.book_code, scope.period_id),
        lock_row,
        passed_only=True,
    )
    outcome = period_machine.decide(
        PeriodState(scope.state),
        period_machine.Command.LOCK,
        period_machine.Guards(
            comment=evidence.comment,
            gate_results=results,
            requester_id=evidence.preparer_id,
            approver_id=evidence.approver_id,
            mfa_verified_at=evidence.mfa_verified_at,
            now=evidence.decided_at,
        ),
        ctx=close._context(scope),  # noqa: SLF001
    )
    close._refuse(outcome)  # noqa: SLF001
    control = dependencies.control_evidence()
    engine = dependencies.snapshot_engine()
    registry = dependencies.snapshot_registry()
    certified = certification.certify(results, at=uow.now)
    cutoff = freeze.freeze_cutoff(session, uow.now)
    freeze.allow_idle(session)  # 05 TXN-03 rev 1.121: idle while the reader produces a dataset
    at_freeze = freeze.activity_before_freeze(uow.principal.tenant_id, scope)
    try:
        datasets = snapshots.freeze_datasets(
            uow,
            scope.entity_id,
            scope.book_code,
            scope.period_id,
            cutoff,
            frozen_at=cutoff,
            registry=registry.datasets,
            scope_type=registry.scope,
            engine=engine,
        )
    except registry.refusal as refused:
        raise freeze.dataset_refused(
            scope, str(getattr(refused, "kind", "")), str(getattr(refused, "reason", refused))
        ) from refused
    except snapshots.MachineArtefactRefused as refused:
        raise freeze.artefact_refused(scope, str(refused)) from refused
    freeze.assert_covered(uow.principal.tenant_id, scope, cutoff, at_freeze)
    manifest = snapshots.manifest_of(datasets, engine=engine)
    certified_rows = certification.certification(certified)
    previous_lock_id = close._previous_lock(session, scope)  # noqa: SLF001
    diff_report_file_id = None
    if previous_lock_id is not None:
        diff_report_file_id = relock_diff.store_report(
            uow,
            relock_diff.report(
                uow,
                previous_lock_id=previous_lock_id,
                lock_id=lock.id,
                manifest_sha256=manifest,
                certification=certified_rows,
                datasets=datasets,
            ),
            period_key=scope.period_key,
        )
    close._persist_lock(  # noqa: SLF001
        uow,
        scope,
        kind=LockKind.LOCK,
        lock_id=lock.id,
        transition_id=step.id,
        from_state=PeriodState.CLOSING,
        to_state=PeriodState.CLOSED,
        action=close.LOCK_ACTION,
        approval_request_id=evidence.request_id,
        comment=evidence.comment,
        certification=certified_rows,
        snapshot_manifest_sha256=manifest,
        heads=close._heads(session, scope),  # noqa: SLF001
        diff_report_file_id=diff_report_file_id,
        # 04 T-CLS-04 (rev 1.113): the instant the replayed datasets above are frozen at
        cutoff_known_at=cutoff,
    )
    snapshots.write_lock_snapshots(uow, lock.id, datasets)
    gates.store_results(uow, certified, scope)
    reconciliations = close._certify_reconciliations(uow, scope, lock.id)  # noqa: SLF001
    control.record_execution(
        uow,
        control_id=close.CONTROL_CLOSE_GATES,
        run_ref_type=control.run_ref_type.PERIOD_LOCK,
        run_ref_id=evidence.request_id,
        population_count=len(certified),
        exception_count=0,
        result=ControlResult.PASS,
        detail=_gate_detail(certified, uow, lock.id, cutoff),
        entity_id=scope.entity_id,
        book_code=scope.book_code,
        period_id=scope.period_id,
    )
    # again, after every lock write
    freeze.assert_covered(uow.principal.tenant_id, scope, cutoff, at_freeze)
    notify(
        uow,
        recipient_membership_ids=role_holders(
            session,
            role_codes=close.LOCK_NOTIFIED_ROLES,
            entity_id=scope.entity_id,
            at=uow.now,
        ),
        kind=NotificationKind.PERIOD_LOCKED,
        title=close.LOCKED_TITLE.format(entity=scope.entity_code, period_key=scope.period_key),
        body=close.LOCKED_BODY.format(
            period_key=scope.period_key, entity=scope.entity_code, book=scope.book_code
        ),
        link_path=subjects.PERIOD_LINK.format(state_id=step.period_state_id),
        subject_type=period_rules.STATE_OBJECT,
        subject_id=step.period_state_id,
    )
    uow.audit(
        action=close.LOCK_ACTION,
        object_type=close.LOCK_OBJECT,
        object_id=lock.id,
        object_version="1",
        after={
            "kind": LockKind.LOCK.value,
            "period_state_id": str(step.period_state_id),
            "approval_request_id": str(evidence.request_id),
            "snapshot_manifest_sha256": manifest,
            "datasets": len(datasets),
            "reconciliations_certified": reconciliations,
            "previous_lock_id": None
            if lock.previous_lock_id is None
            else str(lock.previous_lock_id),
            "relock_of": None if previous_lock_id is None else str(previous_lock_id),
            "diff_report_file_id": None
            if diff_report_file_id is None
            else str(diff_report_file_id),
            "replayed": True,
        },
        comment=evidence.comment,
    )


def _reopen(uow: UnitOfWork, paired: Paired, evidence: _Evidence) -> None:
    """``closed → reopened`` with a ``REOPEN`` as ``_period_reopen_approved`` does, on the copied
    request and its decisions (two approvers with a Controller, none the requester; BR-CLS-05 on
    the sandbox's state), the lock row first with ``previous_lock_id`` = the lock reopened."""
    step, lock = paired.step, paired.lock
    assert lock is not None
    session = uow.session
    scope = _scope(uow, step)
    _expect_state(scope, step)
    _expect_previous_lock(scope, lock)
    at = evidence.decided_at if evidence.decided_at is not None else step.at
    decisions = approvals.decisions_of(
        session, evidence.request_id, tenant_id=uow.principal.tenant_id, at=at
    )
    outcome = period_machine.decide(
        PeriodState(scope.state),
        period_machine.Command.REOPEN,
        period_machine.Guards(
            comment=evidence.comment,
            reason_code=evidence.reason_code,
            requester_id=evidence.preparer_id,
            approvals=decisions,
            later_closed_period_key=close._later_closed(session, scope),  # noqa: SLF001
        ),
        ctx=close._context(scope),  # noqa: SLF001
    )
    close._refuse(outcome)  # noqa: SLF001
    if isinstance(outcome, period_machine.Pending | period_machine.Rejected):
        raise Problem("invalid-transition", close.REOPEN_INCONSISTENT.format(reason=outcome.reason))
    close._persist_lock(  # noqa: SLF001
        uow,
        scope,
        kind=LockKind.REOPEN,
        lock_id=lock.id,
        transition_id=step.id,
        from_state=PeriodState.CLOSED,
        to_state=PeriodState.REOPENED,
        action=close.REOPEN_ACTION,
        approval_request_id=evidence.request_id,
        comment=evidence.comment,
        certification=[],
        snapshot_manifest_sha256=None,
        heads=close._heads(session, scope),  # noqa: SLF001
        reason_code=evidence.reason_code,
    )
    reopened = close._reopen_reconciliations(uow, scope)  # noqa: SLF001
    approvers = [
        decision.actor_id for decision in decisions if decision.kind is ApprovalDecisionKind.APPROVE
    ]
    reason_text = evidence.comment or (
        evidence.reason_code.value if evidence.reason_code is not None else ""
    )
    notify(
        uow,
        recipient_membership_ids=role_holders(
            session,
            role_codes=close.LOCK_NOTIFIED_ROLES,
            entity_id=scope.entity_id,
            at=uow.now,
        ),
        kind=NotificationKind.PERIOD_REOPENED,
        title=close.REOPENED_TITLE.format(entity=scope.entity_code, period_key=scope.period_key),
        body=close.REOPENED_BODY.format(
            requester=close._display_name(session, evidence.preparer_id),  # noqa: SLF001
            period_key=scope.period_key,
            reason=reason_text,
            approvers=" and ".join(
                close._display_name(session, approver)  # noqa: SLF001
                for approver in approvers
            ),
        ),
        link_path=subjects.PERIOD_LINK.format(state_id=step.period_state_id),
        subject_type=period_rules.STATE_OBJECT,
        subject_id=step.period_state_id,
    )
    uow.audit(
        action=close.REOPEN_ACTION,
        object_type=close.LOCK_OBJECT,
        object_id=lock.id,
        object_version="1",
        after={
            "kind": LockKind.REOPEN.value,
            "period_state_id": str(step.period_state_id),
            "approval_request_id": str(evidence.request_id),
            "previous_lock_id": None
            if lock.previous_lock_id is None
            else str(lock.previous_lock_id),
            "reason_code": None if evidence.reason_code is None else evidence.reason_code.value,
            "approvers": [str(approver) for approver in approvers],
            "reconciliations_reopened": reopened,
            "snapshots": "kept",
            "replayed": True,
        },
        reason_code=None if evidence.reason_code is None else evidence.reason_code.value,
        comment=evidence.comment,
    )


def _permanent_lock(
    uow: UnitOfWork, paired: Paired, evidence: _Evidence, lock_row: Mapping[str, Any]
) -> None:
    """``closed → permanently_locked`` as ``_period_lock_approved`` and ``_execute_permanent_lock``
    do: the decision on the copied evidence, every earlier period permanently locked (ruled Q-6),
    the ``PERMANENT_LOCK`` row first. Its certification records ``CLOSE_RUN_COMPLETED`` as the
    source's permanent lock recorded it (``_with_source_close_run``)."""
    step, lock = paired.step, paired.lock
    assert lock is not None
    session = uow.session
    scope = _scope(uow, step)
    _expect_state(scope, step)
    _expect_previous_lock(scope, lock)
    if evidence.approver_id is None:
        raise _no_approver(evidence)
    results = _with_source_close_run(
        gates.evaluate_gates(uow, scope.entity_id, scope.book_code, scope.period_id),
        lock_row,
        passed_only=False,
    )
    outcome = period_machine.decide(
        PeriodState(scope.state),
        period_machine.Command.PERMANENT_LOCK,
        period_machine.Guards(
            comment=evidence.comment,
            gate_results=results,
            requester_id=evidence.preparer_id,
            approver_id=evidence.approver_id,
            mfa_verified_at=evidence.mfa_verified_at,
            now=evidence.decided_at,
        ),
        ctx=close._context(scope),  # noqa: SLF001
    )
    close._refuse(outcome)  # noqa: SLF001
    earlier = close._earlier_unlocked(session, scope)  # noqa: SLF001
    if earlier is not None:
        message = period_machine.PERMANENT_LOCK_ORDER.format(
            earlier=earlier, entity=scope.entity_code, book=scope.book_code
        )
        raise Problem(
            "invalid-transition",
            message,
            errors=[ProblemError(rule_id=period_machine.RULE_PERMANENT_ORDER, message=message)],
        )
    close._persist_lock(  # noqa: SLF001
        uow,
        scope,
        kind=LockKind.PERMANENT_LOCK,
        lock_id=lock.id,
        transition_id=step.id,
        from_state=PeriodState.CLOSED,
        to_state=PeriodState.PERMANENTLY_LOCKED,
        action=close.PERMANENT_LOCK_ACTION,
        approval_request_id=evidence.request_id,
        comment=evidence.comment,
        certification=certification.certification(results),
        snapshot_manifest_sha256=None,
        heads=close._heads(session, scope),  # noqa: SLF001
    )
    uow.audit(
        action=close.PERMANENT_LOCK_ACTION,
        object_type=close.LOCK_OBJECT,
        object_id=lock.id,
        object_version="1",
        after={
            "kind": LockKind.PERMANENT_LOCK.value,
            "period_state_id": str(step.period_state_id),
            "approval_request_id": str(evidence.request_id),
            "previous_lock_id": None
            if lock.previous_lock_id is None
            else str(lock.previous_lock_id),
            "replayed": True,
        },
        comment=evidence.comment,
    )


def _apply(uow: UnitOfWork, prepared: Prepared, paired: Paired) -> None:
    """One paired step through the governed path of its DB-07 pair."""
    step = paired.step
    if paired.lock is None:
        if step.from_state is PeriodState.FUTURE and step.to_state is PeriodState.OPEN:
            _open(uow, prepared, step)
        else:
            _move(uow, prepared, step)
        return
    kind = paired.lock.lock_kind
    lock_row = prepared.locks[paired.lock.id]
    evidence = _evidence(uow.session, UUID(str(lock_row["approval_request_id"])))
    if kind is LockKind.LOCK:
        _lock(uow, paired, evidence, lock_row)
    elif kind is LockKind.REOPEN:
        _reopen(uow, paired, evidence)
    elif kind is LockKind.PERMANENT_LOCK:
        _permanent_lock(uow, paired, evidence, lock_row)
    else:  # pragma: no cover - LockKind is closed
        raise RuntimeError(f"period_lock {paired.lock.id}: unknown kind {kind}")


def _attempted(step: ReplayStep) -> str:
    origin = "" if step.from_state is None else step.from_state.value
    return f"{origin} → {'' if step.to_state is None else step.to_state.value}"


def _read_back(session: Session, prepared: Prepared) -> dict[UUID, tuple[str, UUID | None]]:
    ids = [UUID(str(row["id"])) for row in prepared.states]
    if not ids:
        return {}
    rows = session.execute(
        select(period_state.c.id, period_state.c.state, period_state.c.current_lock_id).where(
            period_state.c.id.in_(ids)
        )
    ).all()
    return {
        UUID(str(state_id)): (
            str(state),
            None if current_lock_id is None else UUID(str(current_lock_id)),
        )
        for state_id, state, current_lock_id in rows
    }


def open_step(paired: Paired) -> bool:
    """A step of the OPEN phase (05 SBX-04: every period opens before the recompute): the plan's
    creation transitions and every ``future → open``; closing, cancel, lock, reopen and permanent
    lock steps belong to the CLOSE phase after the recompute."""
    step = paired.step
    if paired.lock is not None:
        return False
    return step.from_state is None or (
        step.from_state is PeriodState.FUTURE and step.to_state is PeriodState.OPEN
    )


class Replay:
    """The prepared plan executed in the sandbox as ``actor`` (the requesting user's copied
    membership) in TWO phases around the recompute (05 SBX-04; Codex 1713 §3 R1): ``open_periods``
    creates every source period state ``future`` with the plan's creation transitions and replays
    every ``future → open``; the loader recomputes the groups; ``close_periods`` replays every
    remaining step in plan order; ``result`` reads the reached (``state``, ``current_lock_id``) of
    every period back and requires equality with the source's for every unblocked period. One
    transaction per step (TXN-08); a normal refusal blocks that period and skips its later steps
    (ruling (3)); any other error propagates."""

    def __init__(
        self,
        prepared: Prepared,
        *,
        runtime: JobRuntime,
        actor: Principal,
        request_prefix: str,
        beat: Callable[[], None] = lambda: None,
    ) -> None:
        self.prepared = prepared
        self._runtime = runtime
        self._actor = actor
        self._prefix = request_prefix
        self._beat = beat
        self.current: dict[UUID, str] = {
            UUID(str(row["id"])): PeriodState.FUTURE.value for row in prepared.states
        }
        self.blocked: list[BlockedPeriod] = []
        self.skipped: set[UUID] = set()
        self.applied = 0
        self._done: set[UUID] = set()
        self._opened = False

    def open_periods(self) -> None:
        creations = tuple(
            p.step for p in self.prepared.paired if p.step.from_state is None and p.lock is None
        )
        with system_unit_of_work(
            self._runtime, self._actor, request_id=f"{self._prefix}-periods"
        ) as uow:
            _create_states(uow, self.prepared, creations)
            uow.commit()
        self._done.update(step.id for step in creations)
        self._opened = True
        self._beat()
        for paired in self.prepared.paired:
            if open_step(paired) and paired.step.id not in self._done:
                self._apply(paired)

    def close_periods(self) -> None:
        if not self._opened:
            raise RuntimeError("open_periods runs before close_periods")
        for paired in self.prepared.paired:
            if paired.step.id not in self._done:
                self._apply(paired)

    def _apply(self, paired: Paired) -> None:
        step = paired.step
        self._done.add(step.id)
        if step.period_state_id in self.skipped:
            return
        try:
            with system_unit_of_work(
                self._runtime, self._actor, request_id=f"{self._prefix}-replay-{step.id}"
            ) as uow:
                _apply(uow, self.prepared, paired)
                uow.commit()
        except Exception as error:
            reason = blocked_reason(error)
            if reason is None:
                raise  # a defect, never disguised as a business refusal
            self.blocked.append(
                BlockedPeriod(
                    step.period_state_id,
                    step.entity_id,
                    step.book_code,
                    step.period_id,
                    _attempted(step),
                    self.current[step.period_state_id],
                    reason,
                )
            )
            self.skipped.add(step.period_state_id)
            return
        assert step.to_state is not None
        self.current[step.period_state_id] = step.to_state.value
        self.applied += 1
        self._beat()

    def result(self) -> ReplayResult:
        if not self._opened:
            raise RuntimeError("open_periods runs before result")
        with system_unit_of_work(
            self._runtime, self._actor, request_id=f"{self._prefix}-replayed"
        ) as uow:
            reached = _read_back(uow.session, self.prepared)
        for row in self.prepared.states:
            state_id = UUID(str(row["id"]))
            if state_id in self.skipped:
                continue
            expected = (
                str(row["state"]),
                None if row.get("current_lock_id") is None else UUID(str(row["current_lock_id"])),
            )
            if reached.get(state_id) != expected:
                raise RuntimeError(
                    f"period_state {state_id}: the replay reached {reached.get(state_id)} but the "
                    f"source shows {expected}"
                )
        return ReplayResult(self.applied, tuple(self.blocked), reached)


def execute(
    prepared: Prepared,
    *,
    runtime: JobRuntime,
    actor: Principal,
    request_prefix: str,
    beat: Callable[[], None] = lambda: None,
) -> ReplayResult:
    """Both phases back to back (no recompute in between); the loader uses :class:`Replay`."""
    run = Replay(prepared, runtime=runtime, actor=actor, request_prefix=request_prefix, beat=beat)
    run.open_periods()
    run.close_periods()
    return run.result()
