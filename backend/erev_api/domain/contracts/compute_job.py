"""The fact-capture computation and the ``CONTRACT_COMPUTE`` job (dev-guide DG-CMD-09, DG-CMD-10,
§5.12; 05 RCP-18 to RCP-22, §3.9, §5.6; 04 T-CON-07, T-IMP-05, §15.4; 03 REQ-CLS-013; BUILD_SPEC
CTR-5).

``compute_group(uow, group_id)`` is unit of work B of a fact-capture command and the body of one
chunk of a ``CONTRACT_COMPUTE`` job:

1. The group row is locked ``FOR UPDATE`` before the bundle is assembled, so computations of one
   group serialise (RCP-22; TXN-05).
2. In a savepoint it builds the bundle at ``uow.now``, calls the engine once and persists the output
   (``computation.persist``; RCP-21 answers a replay). The non-blocking engine findings of a new
   computation (``OutputBundle.diagnostics``, CV-41) become ``WARNING`` or ``INFO`` exception items
   (05 §3.9 row 2), for example ``LATE_EVENT`` on the late event (D-19).
3. When the engine time exceeds ``budget_seconds`` before persisting, the savepoint rolls back and
   the result is deferred: the caller defers ``CONTRACT_COMPUTE``, and the group stays dirty
   (RCP-18).
4. An ``EngineError`` rolls the savepoint back and stores a ``QUARANTINED`` computation with a
   problem and a ``BLOCKING`` exception item (source ``ENGINE``, the §15.4 code, ``dedupe_key``
   ``ENGINE:<code>:<group id>``; RCP-20). Engine codes outside §15.4 (``ENGINE_INVARIANT_VIOLATED``,
   ``FLOAT_DETECTED``, ``ENGINE_VERSION_MISMATCH``, ``TRACE_DUPLICATE_NODE``) raise
   ``ENGINE_INVARIANT_VIOLATION`` (table 15.4-S), whose message is PRD IMP-75 and names the
   engine's rule with its detail (for example the period and the book of CV-13), as does the
   problem's error (supervisor ruling R-58 (c)); the other codes keep their copy.
5. Any other exception is logged with its stack trace and stores a ``FAILED`` computation with an
   ``about:blank`` problem (04 table 15.2-S) and the same exception item. The events committed by
   unit of work A stay, and the group stays dirty (DG-CMD-09). One kind is not a result of the
   computation and is raised again with nothing stored (item RES-53-COMPUTE-1; DG-CMD-09 rev 1.97;
   05 RCP-20): a database error that says the server could not do it at that moment
   (``db_errors.server_unavailable``) — the caller's transaction rolls back, a command answers
   503 and a job attempt fails for retry by its policy.

[J] L4-1-Q-3: a refused computation does not move ``combination_group.head_computation_id`` or the
members' ``latest_computation_id``, which keep naming the latest SUCCEEDED computation; the FAILED
item uses ``ENGINE_INVARIANT_VIOLATION`` because §15.4 has no code for a programming error; the
events and the refused computation commit together, because unit of work B runs in a savepoint of
the command's transaction.

[J] L4-1-Q-8: the rc engine assigns late postings (stage 14 ``reason_code = LATE_EVENT``) but never
publishes the S08-R-10 ``LATE_EVENT`` findings, because nothing calls stage 08 ``late_events``, so
the platform raises the closed-period clause itself after a new computation; the out-of-order
clause waits for the engine.

The job takes ``{"combination_group_ids": [...], "trigger": <E-87>, "contract_id"?}`` and computes
each group in its own transaction (RCP-19); ``{"mode": "PREVIEW", ...}`` runs the event impact
preview of ``events.run_preview`` and ``{"mode": "ESTIMATE_PREVIEW", ...}`` the estimate-version
preview of ``estimates.run_preview`` (SCREENS R-16; BUILD_SPEC CTR-12); ``{"mode":
"ADJUSTMENT_PREVIEW", ...}`` runs the manual-adjustment preview of ``journals.adjustments``
(BUILD_SPEC CLO-12).
"""

from __future__ import annotations

import time
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import Diagnostic, InputBundle, OutputBundle
from erev_engine.canonical import sha256_hex
from erev_engine.errors import EngineError
from sqlalchemy import func, insert, select

from erev_api.audit.writer import record_facts
from erev_api.controls.evidence import RunRefType, record_execution
from erev_api.controls.release import current_environment, current_release
from erev_api.controls.stamping import process_release_id
from erev_api.db import errors as db_errors
from erev_api.db import new_id
from erev_api.db.session import require_tenant_scope
from erev_api.db.tables import (
    combination_group_member,
    contract,
    contract_computation,
    engine_release,
    obligation,
)
from erev_api.domain.contracts import bundles, computation, period_ends, queries, repo
from erev_api.domain.imports.exceptions import (
    GROUP_OBJECT,
    dedupe_key,
    raise_exception_item,
    settle_reprocess,
    severity_of,
)
from erev_api.domain.imports.job_items import failed_item
from erev_api.enums import (
    BookCode,
    ComputationStatus,
    ComputationTrigger,
    ControlResult,
    ExceptionSeverity,
    ExceptionSource,
    JobKind,
)
from erev_api.jobs.registry import FailedSubject, JobOutcome, task
from erev_api.logging import get_logger
from erev_api.periods import posting_period
from erev_api.problems import INSTANCE_BASE, Problem, ProblemError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from erev_api.jobs.context import JobContext
    from erev_api.uow import UnitOfWork

__all__ = [
    "ENGINE_BUDGET_SECONDS",
    "OBLIGATION_BUDGET",
    "GroupComputation",
    "compute_group",
    "contract_compute",
    "defer_compute",
    "obligation_count",
]

OBLIGATION_BUDGET: Final = 200  # DG-CMD-09: more obligations in the group defer the computation
ENGINE_BUDGET_SECONDS: Final = 30.0  # DG-CMD-09, RCP-18: engine time measured before persisting
QUARANTINE_CODE: Final = "ENGINE_INVARIANT_VIOLATION"  # table 15.4-S ENG-QUARANTINE
ENGINE_ONLY_CODES: Final = frozenset(
    {
        "ENGINE_INVARIANT_VIOLATED",
        "FLOAT_DETECTED",
        "ENGINE_VERSION_MISMATCH",
        "TRACE_DUPLICATE_NODE",
    }
)
RULE_MEMBERS: Final = ("rule", "invariant")  # the detail member in which the engine names a rule
LATE_EVENT: Final = "LATE_EVENT"
ABSENT: Final = "-"
COMPUTATION_OBJECT: Final = "contract_computation"
PREVIEW_MODE: Final = "PREVIEW"
ESTIMATE_PREVIEW_MODE: Final = "ESTIMATE_PREVIEW"
MODIFICATION_PREVIEW_MODE: Final = "MODIFICATION_PREVIEW"  # CTR-17 (D-98 140)
ADJUSTMENT_PREVIEW_MODE: Final = "ADJUSTMENT_PREVIEW"  # CLO-12 (04 §16.14 API-R-37 shapes)
CONTRACT_SUBJECT: Final = "contract"
CONTRACT_HREF: Final = "/api/v1/contracts/{contract_id}"


@dataclass(frozen=True, slots=True)
class GroupComputation:
    """The outcome of ``compute_group``; ``status`` is None when the engine exceeded its budget."""

    status: ComputationStatus | None
    computation: Mapping[str, Any] | None
    exception_item_ids: tuple[UUID, ...] = ()

    @property
    def deferred(self) -> bool:
        return self.status is None


def obligation_count(session: Session, group_id: UUID) -> int:
    """The obligations of the group's current members (DG-CMD-09 budget)."""
    members = select(combination_group_member.c.contract_id).where(
        combination_group_member.c.combination_group_id == group_id,
        combination_group_member.c.valid_to_known_at.is_(None),
    )
    statement = (
        select(func.count()).select_from(obligation).where(obligation.c.contract_id.in_(members))
    )
    return int(session.execute(statement).scalar_one())


def defer_compute(
    uow: UnitOfWork,
    group_id: UUID,
    *,
    contract_id: UUID | None = None,
    trigger: ComputationTrigger = ComputationTrigger.COMMAND,
    result: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Defer ``CONTRACT_COMPUTE`` for one group on queue ``compute`` (RCP-18; API-R-30 202).
    ``result`` holds members the deferring command states for the job's result — what its 201
    body would have said (04 §16.3 ``step1_gate``; supervisor ruling R-77 (6)).

    A command that defers stores no computation of what it recorded, so the period pin is asked
    here (PRD ERR-72; ``period_ends.refuse_appends_a_lock_met``; supervisor ruling R-122 (j)): the
    job that computes later records nothing and is not judged."""
    period_ends.refuse_appends_a_lock_met(uow, [group_id])
    params: dict[str, Any] = {
        "combination_group_ids": [str(group_id)],
        "trigger": trigger.value,
    }
    if contract_id is not None:
        params["contract_id"] = str(contract_id)
    if result:
        params["result"] = dict(result)
    return uow.defer(
        JobKind.CONTRACT_COMPUTE,
        params,
        subject_type=None if contract_id is None else CONTRACT_SUBJECT,
        subject_id=contract_id,
    )


def _catalogue_code(engine_code: str) -> str:
    return QUARANTINE_CODE if engine_code in ENGINE_ONLY_CODES else engine_code


def _engine_detail(error: EngineError, *, skip: Collection[str] = ()) -> str:
    """The engine's detail members as ``<name> <value>, ...`` in the engine's member order: the
    rule, period, book, date or amount a reader needs to act on the refusal."""
    return ", ".join(f"{name} {value}" for name, value in error.detail.items() if name not in skip)


def _engine_message(error: EngineError) -> str:
    """The engine's message followed by its detail (``problem.errors[].message``)."""
    members = _engine_detail(error)
    return error.message + (f" ({members})" if members else "")


def _invariant(error: EngineError) -> str:
    """PRD IMP-75 ``<invariant>``: the rule the engine names (detail ``rule`` or ``invariant``,
    else its code), with its message, its subject and the remaining detail."""
    rule = next((error.detail[name] for name in RULE_MEMBERS if name in error.detail), error.code)
    subject = [] if error.subject_key is None else [f"subject {error.subject_key}"]
    members = ", ".join([*subject, *filter(None, [_engine_detail(error, skip=RULE_MEMBERS)])])
    return f"{rule} ({error.message}" + (f": {members})" if members else ")")


def _members(session: Session, group_id: UUID) -> list[dict[str, Any]]:
    statement = (
        select(
            contract.c.id,
            contract.c.external_id,
            contract.c.head_stream_version,
            contract.c.contracting_entity_id,
        )
        .select_from(
            combination_group_member.join(
                contract,
                (contract.c.tenant_id == combination_group_member.c.tenant_id)
                & (contract.c.id == combination_group_member.c.contract_id),
            )
        )
        .where(
            combination_group_member.c.combination_group_id == group_id,
            combination_group_member.c.valid_to_known_at.is_(None),
        )
        .order_by(contract.c.external_id)
    )
    return [dict(row) for row in session.execute(statement).mappings()]


def _release_id(session: Session, engine_version: str) -> UUID:
    """The process's own release row for an output of ``engine_version`` (05 REL-03 consumers,
    rev 1.15; ``controls.stamping``); the latest row of that version is only the dev / test
    fallback, and a process row of another version is ``release-mismatch``."""

    def latest_for_version() -> UUID | None:
        found = session.execute(
            select(engine_release.c.id)
            .where(engine_release.c.engine_version == engine_version)
            .order_by(engine_release.c.deployed_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        return None if found is None else UUID(str(found))

    return process_release_id(
        current_release(),
        env=current_environment(),
        engine_version=engine_version,
        latest_for_version=latest_for_version,
    )


def _pinned(session: Session, bundle: InputBundle | None) -> dict[str, Any]:
    if bundle is None:
        return {}
    try:
        return bundles.pinned_refs(session, bundle, bundles.index(session, bundle))
    except (LookupError, ValueError, KeyError):
        return {}


def _obligation_id(
    session: Session, members: Sequence[Mapping[str, Any]], subject_key: str | None
) -> UUID | None:
    """The obligation a ``<contract>/<obligation key>`` subject names, when it is a member's."""
    if subject_key is None or "/" not in subject_key:
        return None
    external_id, key = subject_key.rsplit("/", 1)
    contract_ids = [row["id"] for row in members if str(row["external_id"]) == external_id]
    if not contract_ids:
        return None
    found = session.execute(
        select(obligation.c.id).where(
            obligation.c.contract_id == contract_ids[0], obligation.c.obligation_key == key
        )
    ).scalar_one_or_none()
    return None if found is None else UUID(str(found))


def _refused(
    uow: UnitOfWork,
    group_id: UUID,
    bundle: InputBundle | None,
    *,
    trigger: ComputationTrigger,
    status: ComputationStatus,
    error: EngineError | None,
    duration_ms: int,
    job_id: UUID | None,
) -> GroupComputation:
    """Store a QUARANTINED or FAILED computation and its exception item (RCP-20; §3.9), as
    SYSTEM under the tenant's scope like the computation it stands for (05 TXN-10).

    No version is stored, so ``computation.persist`` and its period pin were not reached, while
    an event the command recorded stays: the pin is asked first (PRD ERR-72;
    ``period_ends.refuse_appends_a_lock_met``; supervisor ruling R-122 (j))."""
    session = uow.session
    require_tenant_scope(session)
    period_ends.refuse_appends_a_lock_met(uow, [group_id])
    members = _members(session, group_id)
    external_ids = [str(row["external_id"]) for row in members]
    code = QUARANTINE_CODE if error is None else _catalogue_code(error.code)
    subject_key = None if error is None else error.subject_key
    names = ", ".join(external_ids) or str(group_id)
    if error is None:
        message = (
            f"{names} could not be calculated and was quarantined. Nothing was posted for it. "
            f"Reference {uow.ctx.request_id}."
        )
        problem: dict[str, Any] = {
            "type": "about:blank",
            "title": "Internal Server Error",
            "status": 500,
            "instance": INSTANCE_BASE + uow.ctx.request_id,
        }
    else:
        if code == QUARANTINE_CODE:
            # PRD IMP-75: the item names the invariant, with the period and book it concerns.
            message = (
                f"{names} failed invariant {_invariant(error)} and was quarantined. "
                f"Nothing was posted for it. Reference {uow.ctx.request_id}."
            )
            reason = _engine_message(error)
        else:
            subject = "" if subject_key is None else f" for {subject_key}"
            message = (
                f"{names}: the calculation stopped with {error.code}{subject} and was "
                "quarantined. Nothing was posted for it."
            )
            reason = error.message
        problem = Problem(
            "validation-failed",
            message,
            code=code,
            errors=[ProblemError(field=subject_key, rule_id=code, message=reason)],
        ).to_json(instance=INSTANCE_BASE + uow.ctx.request_id)
    computation_id = new_id()
    engine_version = ENGINE_VERSION if bundle is None else bundle.engine_version
    input_sha256 = (
        sha256_hex({"combination_group_id": str(group_id), "known_at": uow.now.isoformat()})
        if bundle is None
        else bundle.sha256()
    )
    principal = uow.principal
    row: dict[str, Any] = {
        "tenant_id": principal.tenant_id,
        "id": computation_id,
        "combination_group_id": group_id,
        "stream_heads": {str(item["id"]): int(item["head_stream_version"]) for item in members},
        "known_at": uow.now if bundle is None else bundle.known_at,
        # 04 T-CON-07 rev 1.302: the bound the bundle admitted by; none without a bundle.
        "cutoff_at": None if bundle is None else bundle.known_at,
        "trigger": trigger.value,
        "engine_release_id": _release_id(session, engine_version),
        "engine_version": engine_version,
        "input_sha256": input_sha256,
        "pinned_refs": _pinned(session, bundle),
        "status": status.value,
        "problem": problem,
        "duration_ms": duration_ms,
        "job_id": job_id,
        "close_run_id": None,
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
    }
    session.execute(insert(contract_computation).values(**row))
    # SOP-1 CTL-012: a refused computation is one exception of the fail-closed invariant.
    record_execution(
        uow,
        control_id="CTL-012",
        run_ref_type=RunRefType.CONTRACT_COMPUTATION,
        run_ref_id=computation_id,
        population_count=obligation_count(session, group_id),
        exception_count=1,
        result=ControlResult.FAIL,
        detail={"status": status.value, "code": code},
    )
    record_facts(
        uow,
        action=f"{COMPUTATION_OBJECT}.create",
        object_type=COMPUTATION_OBJECT,
        ids=[computation_id],
        detail={"combination_group_id": str(group_id), "status": status.value, "code": code},
        contract_ids=[UUID(str(item["id"])) for item in members],
    )
    single = members[0] if len(members) == 1 else None
    item = raise_exception_item(
        uow,
        source=ExceptionSource.ENGINE,
        code=code,
        severity=ExceptionSeverity.BLOCKING,
        message=message,
        dedupe=dedupe_key(ExceptionSource.ENGINE, code, group_id),
        contract_id=None if single is None else UUID(str(single["id"])),
        obligation_id=_obligation_id(session, members, subject_key),
        combination_group_id=group_id,
        entity_id=None if single is None else UUID(str(single["contracting_entity_id"])),
        source_payload={
            "contract_computation_id": str(computation_id),
            "engine_code": None if error is None else error.code,
            "subject_key": subject_key,
            "detail": {} if error is None else dict(error.detail),
        },
    )
    return GroupComputation(status=status, computation=row, exception_item_ids=(item.id,))


def _no_finding_of_a_bundle_behind(uow: UnitOfWork, bundle: InputBundle | None) -> None:
    """What the engine, or a crash, answers to a bundle that is behind its group is no finding
    about the group as it stands (05 RCP-20 rev 1.207; item COMPUTE-BEHIND-GROUP-1): it is not
    stored ``QUARANTINED`` or ``FAILED`` with an exception item, but ends as the computation
    itself would have ended at ``persist`` — 409 ``lock-conflict``
    (``computation.refuse_a_bundle_behind_its_group``). The group row is held since
    ``_compute`` began. A bundle that could not be built, or cannot be indexed, is judged as
    before."""
    if bundle is None:
        return
    try:
        found = bundles.index(uow.session, bundle)
    except (LookupError, ValueError, KeyError):
        return
    computation.refuse_a_bundle_behind_its_group(uow, bundle, found)


def _entity_code(found: bundles.BundleIndex, entity_id: object) -> str | None:
    for code, row in found.entities.items():
        if row["id"] == entity_id:
            return code
    return None


def _diagnostic_message(item: Diagnostic, effective: str | None, contract_key: str | None) -> str:
    detail = item.detail
    origin = detail.get("origin_period_key", ABSENT)
    posting = detail.get("posting_period_key", ABSENT)
    if item.code == LATE_EVENT and origin != ABSENT:
        # PRD IMP-39.
        return (
            f"Effective {effective} in closed period {origin}. The effect posts to {posting} "
            f"with origin period {origin}."
        )
    if item.code == LATE_EVENT:
        return f"Effective {effective} is earlier than a committed later event of {contract_key}."
    members = ", ".join(f"{name} {value}" for name, value in sorted(detail.items()))
    subject = item.subject_key or contract_key or ABSENT
    return f"{subject}: {item.code}" + (f" ({members})." if members else ".")


def _raise_diagnostics(
    uow: UnitOfWork, bundle: InputBundle, output: OutputBundle, group_id: UUID
) -> tuple[UUID, ...]:
    """05 §3.9 row 2: one exception item per diagnostic code and subject of a new computation, then
    the platform's ``LATE_EVENT`` items of the new events (L4-1-Q-8)."""
    session = uow.session
    found = bundles.index(session, bundle)
    events = {event.event_key: event for event in bundle.events}
    raised: dict[tuple[str, str], UUID] = {}
    for item in output.diagnostics:
        event = None if item.event_key is None else events.get(item.event_key)
        contract_key = None if event is None else event.contract_key
        if contract_key is None and len(found.contracts) == 1:
            contract_key = next(iter(found.contracts))
        contract_row = None if contract_key is None else found.contracts.get(contract_key)
        event_id = (
            None if event is None else found.events.get((event.contract_key, event.stream_version))
        )
        obligation_row = (
            None if item.subject_key is None else found.obligations.get(item.subject_key)
        )
        subject: object = event_id or (
            obligation_row["id"] if obligation_row is not None else group_id
        )
        if (item.code, str(subject)) in raised:
            continue
        entity_id = None if contract_row is None else contract_row["contracting_entity_id"]
        period_id: UUID | None = None
        origin = item.detail.get("origin_period_key", ABSENT)
        code = None if entity_id is None else _entity_code(found, entity_id)
        if origin != ABSENT and code is not None and (code, origin) in found.periods:
            period_id = found.periods[(code, origin)][0]
        raised_item = raise_exception_item(
            uow,
            source=ExceptionSource.ENGINE,
            code=item.code,
            severity=severity_of(item.severity),
            message=_diagnostic_message(
                item, None if event is None else event.effective_date.isoformat(), contract_key
            ),
            dedupe=dedupe_key(ExceptionSource.ENGINE, item.code, subject),
            contract_id=None if contract_row is None else UUID(str(contract_row["id"])),
            obligation_id=None if obligation_row is None else UUID(str(obligation_row["id"])),
            combination_group_id=group_id,
            entity_id=None if entity_id is None else UUID(str(entity_id)),
            period_id=period_id,
            source_payload={
                "book_code": item.book_code,
                "event_key": item.event_key,
                "subject_key": item.subject_key,
                "detail": dict(item.detail),
            },
        )
        raised[(item.code, str(subject))] = raised_item.id
    _raise_late_events(uow, bundle, found, group_id, raised)
    return tuple(raised.values())


def _raise_late_events(
    uow: UnitOfWork,
    bundle: InputBundle,
    found: bundles.BundleIndex,
    group_id: UUID,
    raised: dict[tuple[str, str], UUID],
) -> None:
    """[J] L4-1-Q-8: ``LATE_EVENT`` (``WARNING``, D-19) for each event the computation includes
    first whose effective period is not postable, through DG-KRN-TIME-04 ``posting_period``. The
    dedupe key equals the diagnostic path's, so an engine finding of the same event counts on the
    same open item."""
    session = uow.session
    previous = dict(bundle.group.previous_stream_heads)
    book_code = BookCode(queries.primary_book(session))
    for event in bundle.events:
        if event.stream_version <= previous.get(event.contract_key, 0):
            continue
        event_id = found.events.get((event.contract_key, event.stream_version))
        contract_row = found.contracts.get(event.contract_key)
        if event_id is None or contract_row is None or (LATE_EVENT, str(event_id)) in raised:
            continue
        entity_id = UUID(str(contract_row["contracting_entity_id"]))
        try:
            posting, origin = posting_period(
                session,
                entity_id=entity_id,
                book_code=book_code,
                effective_date=event.effective_date,
            )
        except Problem:
            continue
        if origin is None:
            continue
        obligation_ids = [
            UUID(str(row["id"]))
            for row in found.obligations.values()
            if row["contract_id"] == contract_row["id"]
            and str(row["obligation_key"]) in event.obligation_keys
        ]
        item = raise_exception_item(
            uow,
            source=ExceptionSource.ENGINE,
            code=LATE_EVENT,
            severity=ExceptionSeverity.WARNING,
            # PRD IMP-39.
            message=(
                f"Effective {event.effective_date.isoformat()} in closed period "
                f"{origin.period_key}. The effect posts to {posting.period_key} with origin "
                f"period {origin.period_key}."
            ),
            dedupe=dedupe_key(ExceptionSource.ENGINE, LATE_EVENT, event_id),
            contract_id=UUID(str(contract_row["id"])),
            obligation_id=obligation_ids[0] if len(obligation_ids) == 1 else None,
            combination_group_id=group_id,
            entity_id=entity_id,
            period_id=origin.id,
            source_payload={
                "book_code": book_code.value,
                "event_key": event.event_key,
                "origin_period_key": origin.period_key,
                "posting_period_key": posting.period_key,
                "rule": "S08-R-10",
            },
        )
        raised[(LATE_EVENT, str(event_id))] = item.id


def compute_group(
    uow: UnitOfWork,
    group_id: UUID,
    *,
    trigger: ComputationTrigger = ComputationTrigger.COMMAND,
    engine: computation.Engine | None = None,
    job_id: UUID | None = None,
    budget_seconds: float | None = None,
) -> GroupComputation:
    """Compute the group in ``uow``; refused computations are stored, not raised (DG-CMD-09).

    The computation is reader-independent (05 RCP-18 rev 1.82, TXN-10; supervisor rulings R-95 and
    R-98 (3)): it runs as SYSTEM on behalf of ``uow``'s principal under the tenant's scope,
    whatever entities that principal may see and whatever scope an import narrowed the transaction
    to, and the caller's settings are re-issued when it ends (DG-KRN-UOW-05). The scope is entered
    before the savepoint, so the rows of a refused computation are written under it too.

    What is stored and what propagates (05 RCP-20 rev 1.82; supervisor rulings R-97 (5) and
    R-105), by the class of what the computation raised:

    - an ``EngineError`` — the engine's answer about the group, a reason a person can act on — is
      stored ``QUARANTINED`` with its exception item;
    - a ``Problem`` is the command's answer: the savepoint is rolled back and it propagates;
    - a TRANSIENT database error (``db.errors.is_transient``: a lock timeout, a deadlock, a
      serialization failure, a statement timeout, resources, the connection, the period guard's
      refusal, a class nobody listed) says nothing about the group: the savepoint is rolled back
      and it propagates; no computation row, no exception item, no control execution;
    - a DETERMINISTIC database error (a constraint, a trigger other than the period guard) and
      any other exception are a crash of the engine or of the orchestrator on this group, which
      a retry would meet again: stored ``FAILED`` with its exception item, so that the command's
      fact is recorded and the groups beside it go on (RCP-20)."""
    with uow.as_system():
        return _compute(
            uow,
            group_id,
            trigger=trigger,
            engine=engine,
            job_id=job_id,
            budget_seconds=budget_seconds,
        )


def _compute(
    uow: UnitOfWork,
    group_id: UUID,
    *,
    trigger: ComputationTrigger,
    engine: computation.Engine | None,
    job_id: UUID | None,
    budget_seconds: float | None,
) -> GroupComputation:
    """``compute_group`` as SYSTEM under the tenant's scope."""
    session = uow.session
    run = engine if engine is not None else computation.default_engine()
    repo.lock_group(session, group_id)
    savepoint = session.begin_nested()
    bundle: InputBundle | None = None
    started = time.perf_counter()
    try:
        bundle = bundles.build(session, group_id, uow.now, (), trigger)
        started = time.perf_counter()
        output = run(bundle)
        seconds = time.perf_counter() - started
        if budget_seconds is not None and seconds > budget_seconds:
            savepoint.rollback()
            return GroupComputation(status=None, computation=None)
        stored = computation.persist(
            uow, bundle, output, duration_ms=int(seconds * 1000), job_id=job_id
        )
        items = () if stored["replayed"] else _raise_diagnostics(uow, bundle, output, group_id)
    except Problem:
        savepoint.rollback()
        raise
    except EngineError as error:
        savepoint.rollback()
        _no_finding_of_a_bundle_behind(uow, bundle)
        return _refused(
            uow,
            group_id,
            bundle,
            trigger=trigger,
            status=ComputationStatus.QUARANTINED,
            error=error,
            duration_ms=int((time.perf_counter() - started) * 1000),
            job_id=job_id,
        )
    except Exception as error:
        if db_errors.server_unavailable_in(error):
            # RES-53-COMPUTE-1: the server could not do it now (a full lock table, a lost
            # connection). Not a result of the computation: nothing is stored, and the caller's
            # unit of work rolls the whole transaction back.
            raise
        savepoint.rollback()
        raised = db_errors.database_error_in(error)
        if raised is not None and db_errors.is_transient(raised):
            # 05 RCP-20 rev 1.82: a wait is not a finding about the group. The command answers
            # through ``from_db_error``; the job fails its attempt and is retried.
            raise
        _no_finding_of_a_bundle_behind(uow, bundle)
        get_logger(__name__).exception(
            "contract.computation_failed", combination_group_id=str(group_id)
        )
        return _refused(
            uow,
            group_id,
            bundle,
            trigger=trigger,
            status=ComputationStatus.FAILED,
            error=None,
            duration_ms=int((time.perf_counter() - started) * 1000),
            job_id=job_id,
        )
    savepoint.commit()
    if not stored["replayed"]:
        # SOP-1 CTL-012: the allocation invariant held for every obligation the engine allocated.
        record_execution(
            uow,
            control_id="CTL-012",
            run_ref_type=RunRefType.CONTRACT_COMPUTATION,
            run_ref_id=UUID(str(stored["id"])),
            population_count=obligation_count(session, group_id),
            exception_count=0,
            result=ControlResult.PASS,
            detail={"status": str(stored["status"]), "trigger": trigger.value},
        )
    return GroupComputation(
        status=ComputationStatus(str(stored["status"])),
        computation=stored,
        exception_item_ids=items,
    )


def failed_compute(
    session: Session, subject_type: str | None, subject_id: UUID, params: Mapping[str, Any]
) -> FailedSubject | None:
    """05 JOB-07 rev 1.165: what the exception item of a failed computation names — the contract
    and its contracting entity, or the contract group when every contract of the group is one
    entity's. Nothing for a preview (any ``mode``): a dry run keeps nothing, and its failure is
    told to the person who asked for it. Nothing for a group of contracts of several entities:
    an item names one entity (05 RCP-20 leaves the group's own items without one for the same
    reason)."""
    if params.get("mode") is not None:
        return None
    if subject_type == CONTRACT_SUBJECT:
        entity_id = session.execute(
            select(contract.c.contracting_entity_id).where(contract.c.id == subject_id)
        ).scalar_one_or_none()
        if entity_id is None:
            return None
        return FailedSubject(entity_id=UUID(str(entity_id)), contract_id=subject_id)
    if subject_type == GROUP_OBJECT:  # the subject of a reprocess job (04 T-PLT-27)
        entities = {
            UUID(str(value))
            for value in session.execute(
                select(contract.c.contracting_entity_id).where(
                    contract.c.combination_group_id == subject_id
                )
            ).scalars()
        }
        if len(entities) != 1:
            return None
        return FailedSubject(entity_id=entities.pop(), combination_group_id=subject_id)
    return None


@task(
    JobKind.CONTRACT_COMPUTE,
    failed_item=failed_item(ExceptionSource.ENGINE, failed_compute),
)
def contract_compute(ctx: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``CONTRACT_COMPUTE`` (05 §5.6 queue ``compute``): one transaction per group (RCP-19)."""
    if params.get("mode") == PREVIEW_MODE:
        # Imported here: the events module defers this job kind.
        from erev_api.domain.contracts import events

        return events.run_preview(ctx, params)
    if params.get("mode") == ESTIMATE_PREVIEW_MODE:
        # Imported here: the estimates module defers this job kind.
        from erev_api.domain.contracts import estimates

        return estimates.run_preview(ctx, params)
    if params.get("mode") == MODIFICATION_PREVIEW_MODE:
        # Imported here: the modifications module defers this job kind (CTR-17).
        from erev_api.domain.contracts import modifications

        return modifications.run_preview(ctx, params)
    if params.get("mode") == ADJUSTMENT_PREVIEW_MODE:
        # Imported here: the adjustments module defers this job kind (CLO-12).
        from erev_api.domain.journals import adjustments

        return adjustments.run_preview(ctx, params)
    group_ids = [UUID(str(value)) for value in params["combination_group_ids"]]
    trigger = ComputationTrigger(str(params.get("trigger", ComputationTrigger.COMMAND.value)))
    counts = {"groups": len(group_ids), "succeeded": 0, "quarantined": 0, "failed": 0}
    # BUILD_SPEC DIN-11: ``POST /exceptions/{id}/reprocess`` names the item the computation settles.
    reprocessed = params.get("exception_item_id")
    for done, group_id in enumerate(group_ids, start=1):
        with ctx.unit_of_work() as uow:
            outcome = compute_group(uow, group_id, trigger=trigger, job_id=ctx.job_id)
            if reprocessed is not None:
                settle_reprocess(
                    uow,
                    UUID(str(reprocessed)),
                    status=outcome.status,
                    computation=outcome.computation,
                    raised=outcome.exception_item_ids,
                )
            uow.commit()
        status = outcome.status or ComputationStatus.FAILED
        counts[status.value.lower()] += 1
        ctx.progress(done, len(group_ids))
    contract_id = params.get("contract_id")
    href = None if contract_id is None else CONTRACT_HREF.format(contract_id=contract_id)
    clean = counts["quarantined"] == 0 and counts["failed"] == 0
    return JobOutcome(
        state="SUCCEEDED" if clean else "SUCCEEDED_WITH_EXCEPTIONS",
        result={**dict(params.get("result") or {}), "href": href, "counts": counts},
    )
