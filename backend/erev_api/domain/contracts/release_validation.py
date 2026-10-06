"""Release validation state machine (05 REL-06, RCP-28a, RCP-29; 04 T-PLT-43 to T-PLT-45; D-96).

Pure functions over injected facts — no session, no engine, no clock. The platform side supplies
the facts from T-PLT-38/43/44/45 and the group tables and applies the returned transitions (lane
P5 integration, after the P2 merge). Everything here is deterministic and unit-tested DB-free.

- **Level** (REL-06, D-96 (3)): ``semver_level`` and the per-tenant ``effective_level`` over the
  chain of declared ``validation_level`` values between the tenant's last enabled release and the
  candidate; a globally PATCH build is MINOR/MAJOR for a lagging tenant when the chain says so.
- **Creation** (D-96 (7), C): ``initial_validation`` — PATCH rows are ``PASSED`` at creation;
  ``BOOTSTRAP`` only for a tenant proven to have no successful computation and no engine posting;
  a non-empty tenant without a ``BASELINE`` is ``INCOMPLETE`` (``PREPARATION_MISSING``);
  ``baseline_row`` names the preparation artifact's own release.
- **Population** (RCP-29): ``select_population`` — open activity, ``NO_SOURCE``, nominal size,
  strata over every enabled book, the deterministic two-pass selection by ``rank_sha256``.
- **Orchestration and aggregation** (B): ``orchestration_after_job``, ``accept_pointer`` and
  ``aggregate`` — the attempt aggregates when every group job is terminal, never by waiting for
  an accepted result; exhausted, cancelled, unverifiable or integrity-mismatch results make it
  ``INCOMPLETE``; MINOR fails on any ``DIFFERENCES``; MAJOR routes them to approval.
- **Enablement** (D-96 (6)): ``TRANSITIONS`` (the DB-03 table), ``enablement_transition`` and
  ``persist_admission`` (the one choke point ``computation.persist()`` consults).
- **Execution lock and token** (B): ``ExecutionToken``, ``execution_lock_key`` and
  ``verification_write`` over a ``VerificationStore`` port and an ``ExecutionLock`` port.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import timedelta
from typing import Final, Literal, Protocol
from uuid import UUID

from erev_api.controls.validation_level import semver_level
from erev_api.enums import (
    BookCode,
    JobKind,
    RecognitionMethod,
    ReleaseValidationStatus,
    ValidationGroupOrchestrationState,
    VerificationOutcome,
)

__all__ = [
    "MINIMUM_SAMPLE",
    "PAUSED_JOB_KINDS",
    "RELEASE_VALIDATION_PENDING",
    "RELEASE_VALIDATION_REDEFER",
    "SAMPLE_FRACTION",
    "TRANSITIONS",
    "Admission",
    "Aggregate",
    "EffectiveLevel",
    "ExecutionLock",
    "ExecutionToken",
    "GroupFacts",
    "GroupResult",
    "GroupSelection",
    "Level",
    "Population",
    "TenantHistory",
    "ValidationCreation",
    "VerificationStore",
    "WriteResult",
    "accept_pointer",
    "aggregate",
    "baseline_row",
    "effective_level",
    "enablement_transition",
    "execution_lock_key",
    "initial_validation",
    "orchestration_after_job",
    "persist_admission",
    "rank_sha256",
    "release_enabled",
    "select_population",
    "semver_level",
    "verification_write",
]

Level = Literal["PATCH", "MINOR", "MAJOR"]
EffectiveLevel = Literal["PATCH", "MINOR", "MAJOR", "BASELINE", "BOOTSTRAP"]
_LEVEL_RANK: Final[Mapping[str, int]] = {"PATCH": 0, "MINOR": 1, "MAJOR": 2}

RELEASE_VALIDATION_PENDING: Final = "release-validation-pending"  # 04 §15.2, 503
RELEASE_VALIDATION_REDEFER: Final = timedelta(seconds=30)  # unbounded, distinct from REL-05
PAUSED_JOB_KINDS: Final = (
    JobKind.CONTRACT_COMPUTE,
    JobKind.CLOSE_RUN,
    JobKind.JOURNAL_RUN_CALCULATE,
    JobKind.IMPORT_COMMIT,
)
SAMPLE_FRACTION: Final = 0.05
MINIMUM_SAMPLE: Final = 20
PREPARATION_MISSING: Final = "PREPARATION_MISSING"
# D-98 59: a same-version new build's row starts PENDING; the REL-06 preparation path enables it.
SAME_VERSION_REBUILD: Final = "SAME_VERSION_REBUILD"


# --- Level ---------------------------------------------------------------------------------------


def _parse(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"{version!r} is not a MAJOR.MINOR.PATCH engine version (DG-ENG-10)")
    major, minor, patch = (int(part) for part in parts)
    return major, minor, patch


# ``semver_level`` lives in the kernel (controls.validation_level) so that the stamping hook may use
# it without an upward import; re-exported here for the state machine's callers.


def effective_level(
    tenant_last_enabled: str, candidate: str, declared: Mapping[str, Level]
) -> Level:
    """D-96 (3): ``max(semver_level(last → candidate), max(validation_level of every release in
    (last, candidate]))``. ``declared`` maps each release version in that half-open range to its
    author-declared level (T-PLT-38 ``validation_level``); the candidate's own declaration must be
    present."""
    if candidate not in declared:
        raise ValueError("the candidate release declares no validation_level (REL-01)")
    low, high = _parse(tenant_last_enabled), _parse(candidate)
    levels = [semver_level(tenant_last_enabled, candidate)]
    for version, level in declared.items():
        if low < _parse(version) <= high:
            levels.append(level)
    return max(levels, key=lambda level: _LEVEL_RANK[level])


# --- Creation (C) ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TenantHistory:
    """What the creating transaction proved about the tenant (D-96 (7))."""

    has_successful_computation: bool
    has_engine_posting: bool
    last_enabled_version: str | None  # the tenant's last enabled release, None without one
    baseline_release_id: UUID | None  # the BASELINE row's release, when the artifact wrote one


@dataclass(frozen=True, slots=True)
class ValidationCreation:
    """The T-PLT-43 row to insert (``ON CONFLICT DO NOTHING`` on (tenant, engine_release))."""

    engine_release_id: UUID
    source_engine_release_id: UUID | None
    effective_level: EffectiveLevel
    status: ReleaseValidationStatus
    enabled_at_creation: bool
    population: Mapping[str, object]
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.enabled_at_creation and self.status is not ReleaseValidationStatus.PASSED:
            raise ValueError("enabled_at is set only with PASSED or APPROVED")


def initial_validation(
    *,
    candidate_release_id: UUID,
    candidate_version: str,
    history: TenantHistory,
    declared: Mapping[str, Level],
    source_release_id: UUID | None,
) -> ValidationCreation:
    """The row a candidate release creates for a tenant (REL-06; D-96 (7), C)."""
    if history.last_enabled_version is None:
        if not history.has_successful_computation and not history.has_engine_posting:
            return ValidationCreation(
                candidate_release_id,
                None,
                "BOOTSTRAP",
                ReleaseValidationStatus.PASSED,
                True,
                {"bootstrap": {"computations": 0, "postings": 0}},
            )
        # Non-empty history and no enabled predecessor: the preparation artifact must first write
        # the BASELINE row; nothing is inferred and nothing is enabled.
        return ValidationCreation(
            candidate_release_id,
            None,
            "MAJOR",
            ReleaseValidationStatus.INCOMPLETE,
            False,
            {"preparation": "missing"},
            PREPARATION_MISSING,
        )
    if history.last_enabled_version == candidate_version:
        # D-98 59: a same-version new build (the preparation artifact, or any non-engine release) is
        # recorded at stamping and starts PENDING here, so ``persist_admission`` refuses with
        # ``release-validation-pending`` until ``prepare_release_baseline`` (BASELINE) or a
        # validation enables it; the same-version declaration is judged there (Codex P5-PREP R2).
        return ValidationCreation(
            candidate_release_id,
            source_release_id,
            "PATCH",
            ReleaseValidationStatus.PENDING,
            False,
            {"preparation": "pending", "same_version": candidate_version},
            SAME_VERSION_REBUILD,
        )
    level = effective_level(history.last_enabled_version, candidate_version, declared)
    if level == "PATCH":
        return ValidationCreation(
            candidate_release_id,
            source_release_id,
            "PATCH",
            ReleaseValidationStatus.PASSED,
            True,
            {"population": "none"},
        )
    return ValidationCreation(
        candidate_release_id,
        source_release_id,
        level,
        ReleaseValidationStatus.PENDING,
        False,
        {},
    )


def baseline_row(
    *, preparation_release_id: UUID, historical_release_id: UUID | None
) -> ValidationCreation:
    """The BASELINE row the preparation artifact writes for its **own** release, so its own
    recomputations pass the per-process-release gate (D-96 (7), v4 C/E)."""
    return ValidationCreation(
        preparation_release_id,
        historical_release_id,
        "BASELINE",
        ReleaseValidationStatus.PASSED,
        True,
        {"baseline": True},
    )


# --- Population (RCP-29) --------------------------------------------------------------------------

Selection = Literal["OPEN_ACTIVITY", "SAMPLED"]
Stratum = tuple[str, str]  # (book_code, recognition_method)


@dataclass(frozen=True, slots=True)
class GroupFacts:
    group_id: UUID
    head_computation_id: UUID | None
    open_activity: bool
    strata: frozenset[Stratum]  # {book, method} pairs over every enabled book


@dataclass(frozen=True, slots=True)
class GroupSelection:
    """One T-PLT-45 row: frozen selection, written once before any child job."""

    group_id: UUID
    source_computation_id: UUID | None
    selection: Selection
    strata: tuple[Stratum, ...]
    rank_sha256: str

    @property
    def no_source(self) -> bool:
        return self.source_computation_id is None


@dataclass(frozen=True, slots=True)
class Population:
    selected: tuple[GroupSelection, ...]
    summary: Mapping[str, object]  # T-PLT-44 ``population``


def rank_sha256(seed: int, tenant_id: UUID, group_id: UUID) -> str:
    """SHA-256 of ``seed‖tenant_id‖group_id``: the decimal seed and the canonical lowercase UUID
    texts concatenated without separators, UTF-8."""
    return hashlib.sha256(f"{seed}{tenant_id}{group_id}".encode()).hexdigest()


def _stratum_order(stratum: Stratum) -> tuple[int, int]:
    books = [code.value for code in BookCode]
    methods = [method.value for method in RecognitionMethod]
    book, method = stratum
    return (
        books.index(book) if book in books else len(books),
        methods.index(method) if method in methods else len(methods),
    )


def select_population(groups: Iterable[GroupFacts], *, seed: int, tenant_id: UUID) -> Population:
    """RCP-29 (D-96): every open-activity group (``NO_SOURCE`` when it has no head), plus a
    deterministic stratified sample of the remaining groups."""
    facts = sorted(groups, key=lambda item: str(item.group_id))
    ranks = {item.group_id: rank_sha256(seed, tenant_id, item.group_id) for item in facts}

    def by_rank(item: GroupFacts) -> tuple[str, str]:
        return ranks[item.group_id], str(item.group_id)

    open_groups = [item for item in facts if item.open_activity]
    remaining = sorted((item for item in facts if not item.open_activity), key=by_rank)
    total = len(remaining)
    nominal = min(total, max(MINIMUM_SAMPLE, math.ceil(SAMPLE_FRACTION * total))) if total else 0
    present = sorted({stratum for item in remaining for stratum in item.strata}, key=_stratum_order)
    chosen: list[GroupFacts] = []
    covered: set[Stratum] = set()
    # Pass 1: every stratum pair present keeps at least one group (lowest rank not yet chosen).
    for stratum in present:
        if stratum in covered:
            continue
        candidate = next(
            (item for item in remaining if stratum in item.strata and item not in chosen), None
        )
        if candidate is not None:
            chosen.append(candidate)
            covered |= candidate.strata
    # Pass 2: fill to the nominal size by rank; coverage may already exceed it.
    for item in remaining:
        if len(chosen) >= nominal:
            break
        if item not in chosen:
            chosen.append(item)
    chosen.sort(key=by_rank)

    def selection(item: GroupFacts, kind: Selection) -> GroupSelection:
        return GroupSelection(
            item.group_id,
            item.head_computation_id,
            kind,
            tuple(sorted(item.strata, key=_stratum_order)),
            ranks[item.group_id],
        )

    selected = tuple(
        [selection(item, "OPEN_ACTIVITY") for item in open_groups]
        + [selection(item, "SAMPLED") for item in chosen]
    )
    strata_summary = [
        {
            "book": book,
            "method": method,
            "present": sum(1 for item in remaining if (book, method) in item.strata),
            "sampled": sum(1 for item in chosen if (book, method) in item.strata),
        }
        for book, method in present
    ]
    summary: dict[str, object] = {
        "groups": len(facts),
        "open_activity": len(open_groups),
        "remaining": total,
        "nominal": nominal,
        "sampled": len(chosen),
        "strata": strata_summary,
        "no_source": sum(1 for item in selected if item.no_source),
        "no_head": sum(1 for item in facts if item.head_computation_id is None),
        "seed": seed,
    }
    return Population(selected, summary)


# --- Orchestration and aggregation (B) -----------------------------------------------------------

JobState = Literal[
    "QUEUED", "RUNNING", "SUCCEEDED", "SUCCEEDED_WITH_EXCEPTIONS", "FAILED", "CANCELLED"
]
_TERMINAL: Final = frozenset(
    {
        ValidationGroupOrchestrationState.COMPLETE,
        ValidationGroupOrchestrationState.FAILED_EXHAUSTED,
        ValidationGroupOrchestrationState.CANCELLED,
    }
)


def orchestration_after_job(
    job_state: JobState, *, retries_left: bool
) -> ValidationGroupOrchestrationState:
    """The T-PLT-45 ``orchestration_state`` that mirrors the child job's lifecycle (E-129)."""
    if job_state == "QUEUED":
        return ValidationGroupOrchestrationState.PENDING
    if job_state == "RUNNING":
        return ValidationGroupOrchestrationState.RUNNING
    if job_state in ("SUCCEEDED", "SUCCEEDED_WITH_EXCEPTIONS"):
        return ValidationGroupOrchestrationState.COMPLETE
    if job_state == "CANCELLED":
        return ValidationGroupOrchestrationState.CANCELLED
    return (
        ValidationGroupOrchestrationState.RETRYABLE
        if retries_left
        else ValidationGroupOrchestrationState.FAILED_EXHAUSTED
    )


def accept_pointer(
    current: UUID | None, *, row_id: UUID, outcome: VerificationOutcome
) -> UUID | None:
    """``accepted_verification_id``: the first terminal non-``ERROR`` row; never moved afterwards
    and never an ``ERROR`` row (B)."""
    if current is not None or outcome is VerificationOutcome.ERROR:
        return current
    return row_id


@dataclass(frozen=True, slots=True)
class GroupResult:
    orchestration_state: ValidationGroupOrchestrationState
    accepted_outcome: VerificationOutcome | None


@dataclass(frozen=True, slots=True)
class Aggregate:
    """``status`` is None while any group job is not terminal."""

    status: ReleaseValidationStatus | None
    counts: Mapping[str, int]
    reasons: tuple[str, ...] = ()


_BLOCKING: Final = frozenset({VerificationOutcome.UNVERIFIABLE, VerificationOutcome.MISMATCH})


def aggregate(level: Level, groups: Sequence[GroupResult]) -> Aggregate:
    """REL-06 / RCP-28a (B): evaluated only when every group's orchestration state is terminal."""
    counts: dict[str, int] = {}
    for group in groups:
        key = group.orchestration_state.value
        counts[key] = counts.get(key, 0) + 1
        if group.accepted_outcome is not None:
            counts[group.accepted_outcome.value] = counts.get(group.accepted_outcome.value, 0) + 1
    if any(group.orchestration_state not in _TERMINAL for group in groups):
        return Aggregate(None, counts)
    reasons: list[str] = []
    for group in groups:
        state = group.orchestration_state
        if state is not ValidationGroupOrchestrationState.COMPLETE:
            reasons.append(state.value)
        elif group.accepted_outcome is None:
            reasons.append("NO_USABLE_RESULT")
        elif group.accepted_outcome in _BLOCKING:
            reasons.append(group.accepted_outcome.value)
    if reasons:
        return Aggregate(ReleaseValidationStatus.INCOMPLETE, counts, tuple(sorted(set(reasons))))
    differences = any(group.accepted_outcome is VerificationOutcome.DIFFERENCES for group in groups)
    if not differences:
        return Aggregate(ReleaseValidationStatus.PASSED, counts)
    if level == "MINOR":
        return Aggregate(ReleaseValidationStatus.FAILED, counts, ("DIFFERENCES",))
    if level == "MAJOR":
        return Aggregate(ReleaseValidationStatus.PENDING_APPROVAL, counts, ("DIFFERENCES",))
    raise ValueError("a PATCH validation has no population to aggregate")


# --- Enablement (D-96 (6)) -----------------------------------------------------------------------

_S = ReleaseValidationStatus
# DB-03 transition table of T-PLT-43 (04 rev 1.13): the platform's ``transitions.TRANSITIONS``
# entry is generated from this mapping at integration.
TRANSITIONS: Final[Mapping[ReleaseValidationStatus, frozenset[ReleaseValidationStatus]]] = {
    _S.PENDING: frozenset({_S.RUNNING}),
    _S.RUNNING: frozenset({_S.INCOMPLETE, _S.PASSED, _S.FAILED, _S.PENDING_APPROVAL}),
    _S.INCOMPLETE: frozenset({_S.RUNNING}),
    _S.PENDING_APPROVAL: frozenset({_S.APPROVED, _S.REJECTED}),
    _S.PASSED: frozenset(),
    _S.FAILED: frozenset(),
    _S.APPROVED: frozenset(),
    _S.REJECTED: frozenset(),
}
_ENABLING: Final = frozenset({_S.PASSED, _S.APPROVED})


def enablement_transition(
    current: ReleaseValidationStatus, target: ReleaseValidationStatus
) -> tuple[ReleaseValidationStatus, bool]:
    """The allowed transition and whether ``enabled_at`` is set in the same statement."""
    if target not in TRANSITIONS[current]:
        raise ValueError(f"invalid release_validation transition {current.value} → {target.value}")
    return target, target in _ENABLING


def release_enabled(enabled_at: object) -> bool:
    return enabled_at is not None


@dataclass(frozen=True, slots=True)
class Admission:
    allowed: bool
    problem: str | None  # ``release-validation-pending`` when refused


def persist_admission(
    process_release_id: UUID, validations: Mapping[UUID, object | None]
) -> Admission:
    """The one choke point: ``computation.persist()`` may write for a tenant only when the
    **process** release has an enabled T-PLT-43 row (``validations`` maps release id →
    ``enabled_at``). Verification never calls ``persist()`` and is never gated."""
    if release_enabled(validations.get(process_release_id)):
        return Admission(True, None)
    return Admission(False, RELEASE_VALIDATION_PENDING)


# --- Execution token, lock and write (B) ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExecutionToken:
    """``(job_id, task_id, attempt)``: the Procrastinate task the job row names and its attempt
    (DG-KRN-JOB-12); redelivery of the same task carries the same token."""

    job_id: UUID
    task_id: int
    attempt: int


def execution_lock_key(attempt_id: UUID, group_id: UUID) -> str:
    """The advisory-lock key taken in the writing transaction (TXN-05 pattern)."""
    return f"erev.verify:{attempt_id}:{group_id}"


class ExecutionLock(Protocol):
    def acquire(self, key: str) -> AbstractContextManager[None]: ...


class VerificationStore(Protocol):
    """The shared-state port the write transition uses (T-CON-26 + T-PLT-45 columns)."""

    def row_by_token(
        self, attempt_id: UUID, group_id: UUID, token: ExecutionToken
    ) -> UUID | None: ...

    def accepted(self, attempt_id: UUID, group_id: UUID) -> UUID | None: ...

    def insert(
        self,
        attempt_id: UUID,
        group_id: UUID,
        token: ExecutionToken,
        row_id: UUID,
        outcome: VerificationOutcome,
    ) -> None: ...

    def set_accepted(self, attempt_id: UUID, group_id: UUID, row_id: UUID) -> None: ...

    def set_orchestration(
        self, attempt_id: UUID, group_id: UUID, state: ValidationGroupOrchestrationState
    ) -> None: ...


WriteResult = Literal["inserted", "duplicate", "already_accepted", "fenced"]


@dataclass(frozen=True, slots=True)
class VerificationWrite:
    result: WriteResult
    row_id: UUID | None
    accepted_id: UUID | None


def verification_write(
    store: VerificationStore,
    lock: ExecutionLock,
    *,
    attempt_id: UUID,
    group_id: UUID,
    token: ExecutionToken,
    row_id: UUID,
    outcome: VerificationOutcome,
    still_owner: Callable[[], bool],
) -> VerificationWrite:
    """The one-transaction shared-state transition (B): under the advisory lock, a duplicate
    delivery of the same token finds its row and writes nothing; a job that lost its task
    ownership (D-80) writes nothing; a group whose result another job already accepted writes
    nothing new; otherwise the row is inserted, the pointer set for a non-``ERROR`` outcome and
    the orchestration state moved to ``COMPLETE``."""
    with lock.acquire(execution_lock_key(attempt_id, group_id)):
        existing = store.row_by_token(attempt_id, group_id, token)
        if existing is not None:
            return VerificationWrite("duplicate", existing, store.accepted(attempt_id, group_id))
        if not still_owner():
            return VerificationWrite("fenced", None, store.accepted(attempt_id, group_id))
        accepted = store.accepted(attempt_id, group_id)
        if accepted is not None:
            return VerificationWrite("already_accepted", None, accepted)
        store.insert(attempt_id, group_id, token, row_id, outcome)
        pointer = accept_pointer(None, row_id=row_id, outcome=outcome)
        if pointer is not None:
            store.set_accepted(attempt_id, group_id, pointer)
        store.set_orchestration(attempt_id, group_id, ValidationGroupOrchestrationState.COMPLETE)
        return VerificationWrite("inserted", row_id, pointer)
