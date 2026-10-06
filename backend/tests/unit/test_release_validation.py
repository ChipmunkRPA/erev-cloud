"""``erev_api.domain.contracts.release_validation``: level derivation, creation and bootstrap,
RCP-29 population selection, orchestration/aggregation, enablement and the execution-lock write
(05 REL-06, RCP-28a, RCP-29; D-96 (3), (4), (6), (7), (B), (C); lane P5 preparation slice).

DB-free: every fact is injected; the store and the lock are in-memory fakes.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from uuid import UUID, uuid4

import pytest
from erev_api.domain.contracts.release_validation import (
    MINIMUM_SAMPLE,
    PAUSED_JOB_KINDS,
    RELEASE_VALIDATION_PENDING,
    TRANSITIONS,
    ExecutionToken,
    GroupFacts,
    GroupResult,
    TenantHistory,
    accept_pointer,
    aggregate,
    baseline_row,
    effective_level,
    enablement_transition,
    execution_lock_key,
    initial_validation,
    orchestration_after_job,
    persist_admission,
    rank_sha256,
    select_population,
    semver_level,
    verification_write,
)
from erev_api.enums import (
    JobKind,
    ReleaseValidationStatus,
    ValidationGroupOrchestrationState,
    VerificationOutcome,
)

TENANT = UUID("00000000-0000-0000-0000-00000000aaaa")
SEED = 20260912
OS = ValidationGroupOrchestrationState
V = VerificationOutcome
S = ReleaseValidationStatus


# --- level (D-96 (3)) -----------------------------------------------------------------------------


def test_semver_level_and_per_tenant_effective_level() -> None:
    assert semver_level("0.2.0", "0.2.1") == "PATCH"
    assert semver_level("0.2.0", "0.3.0") == "MINOR"
    assert semver_level("0.9.0", "1.0.0") == "MAJOR"
    with pytest.raises(ValueError):
        semver_level("0.3.0", "0.2.0")
    with pytest.raises(ValueError):
        semver_level("0.3", "0.4.0")
    # A globally PATCH build (0.3.1, declared PATCH) is MAJOR for a tenant that skipped 0.3.0,
    # which the author declared MAJOR (the D-93 (5) 0.x changed-result case).
    declared = {"0.3.0": "MAJOR", "0.3.1": "PATCH"}
    assert effective_level("0.2.0", "0.3.1", declared) == "MAJOR"
    assert effective_level("0.3.0", "0.3.1", declared) == "PATCH"
    assert effective_level("0.2.9", "0.3.0", {"0.3.0": "MINOR"}) == "MINOR"
    with pytest.raises(ValueError, match="validation_level"):
        effective_level("0.2.0", "0.3.1", {"0.3.0": "MAJOR"})


# --- creation and bootstrap (D-96 (7), C) --------------------------------------------------------


def test_bootstrap_only_for_a_proven_empty_tenant() -> None:
    candidate = uuid4()
    empty = TenantHistory(False, False, None, None)
    row = initial_validation(
        candidate_release_id=candidate,
        candidate_version="0.3.0",
        history=empty,
        declared={"0.3.0": "MINOR"},
        source_release_id=None,
    )
    assert row.effective_level == "BOOTSTRAP" and row.status is S.PASSED and row.enabled_at_creation
    assert row.population == {"bootstrap": {"computations": 0, "postings": 0}}
    # Old heads or postings without a validation row: never auto-passed, never enabled.
    for history in (
        TenantHistory(True, False, None, None),
        TenantHistory(False, True, None, None),
        TenantHistory(True, True, None, None),
    ):
        row = initial_validation(
            candidate_release_id=candidate,
            candidate_version="0.3.0",
            history=history,
            declared={"0.3.0": "MINOR"},
            source_release_id=None,
        )
        assert row.status is S.INCOMPLETE and not row.enabled_at_creation
        assert row.reason == "PREPARATION_MISSING"


def test_patch_passes_at_creation_and_minor_major_start_pending() -> None:
    source = uuid4()
    history = TenantHistory(True, True, "0.3.0", source)
    patch = initial_validation(
        candidate_release_id=uuid4(),
        candidate_version="0.3.1",
        history=history,
        declared={"0.3.1": "PATCH"},
        source_release_id=source,
    )
    assert (
        patch.effective_level == "PATCH" and patch.status is S.PASSED and patch.enabled_at_creation
    )
    minor = initial_validation(
        candidate_release_id=uuid4(),
        candidate_version="0.4.0",
        history=history,
        declared={"0.4.0": "MINOR"},
        source_release_id=source,
    )
    assert minor.effective_level == "MINOR" and minor.status is S.PENDING
    assert not minor.enabled_at_creation and minor.source_engine_release_id == source


def test_baseline_names_the_preparation_release_itself() -> None:
    preparation, historical = uuid4(), uuid4()
    row = baseline_row(preparation_release_id=preparation, historical_release_id=historical)
    assert row.engine_release_id == preparation  # the artifact's own row, not the old build
    assert row.source_engine_release_id == historical
    assert row.effective_level == "BASELINE" and row.status is S.PASSED and row.enabled_at_creation
    # Its own persist() passes the per-process-release gate; the historical id alone would not.
    assert persist_admission(preparation, {preparation: "2026-09-19T00:00:00Z"}).allowed
    assert not persist_admission(historical, {preparation: "2026-09-19T00:00:00Z"}).allowed


# --- population (RCP-29) --------------------------------------------------------------------------


def _groups(
    open_count: int, remaining: int, *, methods: tuple[str, ...] = ("TIME_ELAPSED",)
) -> list[GroupFacts]:
    facts: list[GroupFacts] = []
    for index in range(open_count):
        facts.append(
            GroupFacts(
                UUID(int=1000 + index),
                UUID(int=5000 + index),
                True,
                frozenset({("ASC606", "TIME_ELAPSED")}),
            )
        )
    for index in range(remaining):
        method = methods[index % len(methods)]
        facts.append(
            GroupFacts(
                UUID(int=2000 + index),
                UUID(int=6000 + index),
                False,
                frozenset({("ASC606", method)}),
            )
        )
    return facts


def test_sampling_3_plus_20_with_400_and_with_100_remaining_and_fewer_than_20() -> None:
    for remaining in (400, 100):
        population = select_population(_groups(3, remaining), seed=SEED, tenant_id=TENANT)
        opens = [item for item in population.selected if item.selection == "OPEN_ACTIVITY"]
        sampled = [item for item in population.selected if item.selection == "SAMPLED"]
        assert len(opens) == 3 and len(sampled) == MINIMUM_SAMPLE
        assert population.summary["nominal"] == 20 and population.summary["sampled"] == 20
        assert len({item.group_id for item in population.selected}) == 23  # no duplicates
    small = select_population(_groups(0, 7), seed=SEED, tenant_id=TENANT)
    assert len(small.selected) == 7  # fewer than 20 eligible: all of them
    boundary = select_population(_groups(0, 401), seed=SEED, tenant_id=TENANT)
    assert boundary.summary["nominal"] == 21  # ceil(5% of 401)


def test_sampling_is_deterministic_stratified_and_frozen_by_rank() -> None:
    groups = _groups(0, 120, methods=("TIME_ELAPSED", "USAGE", "MILESTONE"))
    # A rare secondary-book-only method must still keep one group (all enabled books count).
    rare = GroupFacts(UUID(int=9999), UUID(int=8888), False, frozenset({("IFRS15", "ROYALTY")}))
    first = select_population([*groups, rare], seed=SEED, tenant_id=TENANT)
    second = select_population([rare, *reversed(groups)], seed=SEED, tenant_id=TENANT)
    assert [item.group_id for item in first.selected] == [item.group_id for item in second.selected]
    covered = {stratum for item in first.selected for stratum in item.strata}
    assert ("IFRS15", "ROYALTY") in covered
    assert {("ASC606", m) for m in ("TIME_ELAPSED", "USAGE", "MILESTONE")} <= covered
    assert first.summary["sampled"] >= first.summary["nominal"]  # coverage may exceed nominal
    other_seed = select_population([*groups, rare], seed=SEED + 1, tenant_id=TENANT)
    assert [i.group_id for i in other_seed.selected] != [i.group_id for i in first.selected]
    ranks = [item.rank_sha256 for item in first.selected]
    assert ranks == sorted(ranks) and all(len(r) == 64 for r in ranks)
    assert rank_sha256(SEED, TENANT, UUID(int=1)) != rank_sha256(SEED, TENANT, UUID(int=2))
    assert first.summary["seed"] == SEED
    # The selection is the frozen T-PLT-45 content: rerunning never redraws.
    assert select_population([*groups, rare], seed=SEED, tenant_id=TENANT) == first


def test_open_activity_group_without_a_head_is_no_source_and_never_blocks() -> None:
    headless = GroupFacts(UUID(int=42), None, True, frozenset({("ASC606", "USAGE")}))
    population = select_population([headless, *_groups(0, 5)], seed=SEED, tenant_id=TENANT)
    row = next(item for item in population.selected if item.group_id == headless.group_id)
    assert row.no_source and row.selection == "OPEN_ACTIVITY"
    assert population.summary["no_source"] == 1 and population.summary["no_head"] == 1
    result = aggregate(
        "MINOR", [GroupResult(OS.COMPLETE, V.NO_SOURCE), GroupResult(OS.COMPLETE, V.MATCH)]
    )
    assert result.status is S.PASSED


# --- orchestration and aggregation (B) -----------------------------------------------------------


def test_orchestration_state_mirrors_the_job_and_the_pointer_never_accepts_error() -> None:
    assert orchestration_after_job("QUEUED", retries_left=True) is OS.PENDING
    assert orchestration_after_job("RUNNING", retries_left=True) is OS.RUNNING
    assert orchestration_after_job("SUCCEEDED_WITH_EXCEPTIONS", retries_left=False) is OS.COMPLETE
    assert orchestration_after_job("FAILED", retries_left=True) is OS.RETRYABLE
    assert orchestration_after_job("FAILED", retries_left=False) is OS.FAILED_EXHAUSTED
    assert orchestration_after_job("CANCELLED", retries_left=True) is OS.CANCELLED
    first, second = uuid4(), uuid4()
    assert accept_pointer(None, row_id=first, outcome=V.ERROR) is None
    assert accept_pointer(None, row_id=second, outcome=V.MATCH) == second
    assert accept_pointer(second, row_id=first, outcome=V.MATCH) == second  # never moved


def test_aggregation_waits_for_terminal_jobs_not_for_accepted_results() -> None:
    pending = [GroupResult(OS.COMPLETE, V.MATCH), GroupResult(OS.RETRYABLE, None)]
    assert aggregate("MINOR", pending).status is None
    exhausted = [GroupResult(OS.COMPLETE, V.MATCH), GroupResult(OS.FAILED_EXHAUSTED, None)]
    result = aggregate("MINOR", exhausted)
    assert result.status is S.INCOMPLETE and result.reasons == ("FAILED_EXHAUSTED",)
    cancelled = aggregate("MAJOR", [GroupResult(OS.CANCELLED, None)])
    assert cancelled.status is S.INCOMPLETE
    # COMPLETE with no usable result (only ERROR rows) is INCOMPLETE, not a silent pass.
    assert aggregate("MINOR", [GroupResult(OS.COMPLETE, None)]).reasons == ("NO_USABLE_RESULT",)


def test_minor_fails_on_any_l1_difference_and_major_routes_to_approval() -> None:
    mixed = [GroupResult(OS.COMPLETE, V.MATCH)] * 22 + [GroupResult(OS.COMPLETE, V.DIFFERENCES)]
    minor = aggregate("MINOR", mixed)
    assert minor.status is S.FAILED and minor.reasons == ("DIFFERENCES",)
    major = aggregate("MAJOR", mixed)
    assert major.status is S.PENDING_APPROVAL
    clean = [GroupResult(OS.COMPLETE, V.MATCH)] * 23
    assert aggregate("MINOR", clean).status is S.PASSED
    assert aggregate("MAJOR", clean).status is S.PASSED
    assert minor.counts["DIFFERENCES"] == 1 and minor.counts["COMPLETE"] == 23


def test_integrity_mismatch_and_unverifiable_block_and_are_never_approvable() -> None:
    for blocking in (V.MISMATCH, V.UNVERIFIABLE):
        rows = [GroupResult(OS.COMPLETE, V.DIFFERENCES), GroupResult(OS.COMPLETE, blocking)]
        result = aggregate("MAJOR", rows)
        assert result.status is S.INCOMPLETE and blocking.value in result.reasons
        assert result.status is not S.PENDING_APPROVAL


# --- enablement (D-96 (6)) ------------------------------------------------------------------------


def test_transitions_and_enabled_at_only_with_passed_or_approved() -> None:
    assert enablement_transition(S.PENDING, S.RUNNING) == (S.RUNNING, False)
    assert enablement_transition(S.RUNNING, S.PASSED) == (S.PASSED, True)
    assert enablement_transition(S.RUNNING, S.PENDING_APPROVAL) == (S.PENDING_APPROVAL, False)
    assert enablement_transition(S.PENDING_APPROVAL, S.APPROVED) == (S.APPROVED, True)
    assert enablement_transition(S.PENDING_APPROVAL, S.REJECTED) == (S.REJECTED, False)
    assert enablement_transition(S.INCOMPLETE, S.RUNNING) == (S.RUNNING, False)
    for terminal in (S.PASSED, S.FAILED, S.APPROVED, S.REJECTED):
        assert TRANSITIONS[terminal] == frozenset()
    with pytest.raises(ValueError, match="invalid release_validation transition"):
        enablement_transition(S.FAILED, S.PASSED)  # a failed MINOR never becomes accepted
    with pytest.raises(ValueError):
        enablement_transition(S.RUNNING, S.APPROVED)


def test_persist_admission_is_per_process_release() -> None:
    enabled, candidate = uuid4(), uuid4()
    rows = {enabled: "2026-09-19T00:00:00Z", candidate: None}
    assert persist_admission(enabled, rows).allowed
    refused = persist_admission(candidate, rows)
    assert not refused.allowed and refused.problem == RELEASE_VALIDATION_PENDING
    assert persist_admission(uuid4(), rows).problem == RELEASE_VALIDATION_PENDING
    assert PAUSED_JOB_KINDS == (
        JobKind.CONTRACT_COMPUTE,
        JobKind.CLOSE_RUN,
        JobKind.JOURNAL_RUN_CALCULATE,
        JobKind.IMPORT_COMMIT,
    )


# --- execution token, lock and write (B) ----------------------------------------------------------


class _Store:
    def __init__(self) -> None:
        self.rows: dict[tuple[UUID, UUID, UUID, int], UUID] = {}
        self.accepted_ids: dict[tuple[UUID, UUID], UUID] = {}
        self.states: dict[tuple[UUID, UUID], ValidationGroupOrchestrationState] = {}
        self.inserts = 0

    def row_by_token(self, attempt_id: UUID, group_id: UUID, token: ExecutionToken) -> UUID | None:
        return self.rows.get((attempt_id, group_id, token.job_id, token.task_id))

    def accepted(self, attempt_id: UUID, group_id: UUID) -> UUID | None:
        return self.accepted_ids.get((attempt_id, group_id))

    def insert(
        self,
        attempt_id: UUID,
        group_id: UUID,
        token: ExecutionToken,
        row_id: UUID,
        outcome: VerificationOutcome,
    ) -> None:
        self.rows[(attempt_id, group_id, token.job_id, token.task_id)] = row_id
        self.inserts += 1

    def set_accepted(self, attempt_id: UUID, group_id: UUID, row_id: UUID) -> None:
        self.accepted_ids[(attempt_id, group_id)] = row_id

    def set_orchestration(
        self, attempt_id: UUID, group_id: UUID, state: ValidationGroupOrchestrationState
    ) -> None:
        self.states[(attempt_id, group_id)] = state


class _Lock:
    """An execution lock that records acquisitions and refuses re-entry by another holder."""

    def __init__(self) -> None:
        self.keys: list[str] = []
        self._held: str | None = None
        self._guard = threading.Lock()

    @contextmanager
    def _acquire(self, key: str) -> Iterator[None]:
        with self._guard:
            assert self._held is None, "a second holder entered the execution lock"
            self._held = key
            self.keys.append(key)
        try:
            yield
        finally:
            self._held = None

    def acquire(self, key: str) -> AbstractContextManager[None]:
        return self._acquire(key)


def test_execution_lock_two_jobs_same_group_second_writes_nothing_new() -> None:
    store, lock = _Store(), _Lock()
    attempt, group = uuid4(), uuid4()
    first_job = ExecutionToken(uuid4(), 101, 1)
    first_row = uuid4()
    first = verification_write(
        store,
        lock,
        attempt_id=attempt,
        group_id=group,
        token=first_job,
        row_id=first_row,
        outcome=V.MATCH,
        still_owner=lambda: True,
    )
    assert first.result == "inserted" and first.accepted_id == first_row
    assert store.states[(attempt, group)] is OS.COMPLETE
    # A second, distinct job for the same group (deferred while the first ran) waits on the lock,
    # then finds the accepted result and writes nothing new.
    second_job = ExecutionToken(uuid4(), 202, 1)
    second = verification_write(
        store,
        lock,
        attempt_id=attempt,
        group_id=group,
        token=second_job,
        row_id=uuid4(),
        outcome=V.MATCH,
        still_owner=lambda: True,
    )
    assert second.result == "already_accepted" and second.accepted_id == first_row
    assert store.inserts == 1
    assert lock.keys == [execution_lock_key(attempt, group)] * 2
    assert execution_lock_key(attempt, group) == f"erev.verify:{attempt}:{group}"


def test_error_then_retry_keeps_both_rows_and_accepts_the_second() -> None:
    store, lock = _Store(), _Lock()
    attempt, group, job = uuid4(), uuid4(), uuid4()
    error_row, match_row = uuid4(), uuid4()
    first = verification_write(
        store,
        lock,
        attempt_id=attempt,
        group_id=group,
        token=ExecutionToken(job, 1, 1),
        row_id=error_row,
        outcome=V.ERROR,
        still_owner=lambda: True,
    )
    assert first.result == "inserted" and first.accepted_id is None  # ERROR is never accepted
    retry = verification_write(
        store,
        lock,
        attempt_id=attempt,
        group_id=group,
        token=ExecutionToken(job, 2, 2),
        row_id=match_row,
        outcome=V.MATCH,
        still_owner=lambda: True,
    )
    assert retry.result == "inserted" and retry.accepted_id == match_row
    assert store.inserts == 2  # the prior failure evidence is immutable and retained


def test_duplicate_delivery_and_stale_task_write_nothing() -> None:
    store, lock = _Store(), _Lock()
    attempt, group = uuid4(), uuid4()
    token = ExecutionToken(uuid4(), 7, 1)
    row = uuid4()
    verification_write(
        store,
        lock,
        attempt_id=attempt,
        group_id=group,
        token=token,
        row_id=row,
        outcome=V.DIFFERENCES,
        still_owner=lambda: True,
    )
    duplicate = verification_write(
        store,
        lock,
        attempt_id=attempt,
        group_id=group,
        token=token,
        row_id=uuid4(),
        outcome=V.DIFFERENCES,
        still_owner=lambda: True,
    )
    assert duplicate.result == "duplicate" and duplicate.row_id == row and store.inserts == 1
    stale = verification_write(
        _Store(),
        lock,
        attempt_id=attempt,
        group_id=group,
        token=ExecutionToken(uuid4(), 8, 1),
        row_id=uuid4(),
        outcome=V.MATCH,
        still_owner=lambda: False,
    )
    assert stale.result == "fenced" and stale.row_id is None


def test_same_version_rebuild_starts_pending_until_the_preparation_path() -> None:
    """D-98 59 (slice 1b): a same-version new build is recorded at stamping, and its T-PLT-43 row
    is created PENDING (reason SAME_VERSION_REBUILD) so ``persist_admission`` refuses with
    ``release-validation-pending`` until the REL-06 preparation path or a validation enables it;
    the bare same-version declaration path stays refused (Codex P5-PREP R2)."""
    from uuid import UUID

    from erev_api.controls.validation_level import SAME_VERSION_REBUILD as REFUSAL
    from erev_api.controls.validation_level import check_declaration
    from erev_api.domain.contracts.release_validation import (
        SAME_VERSION_REBUILD,
        TenantHistory,
        initial_validation,
        persist_admission,
    )
    from erev_api.enums import ReleaseValidationStatus

    candidate = UUID(int=11)
    history = TenantHistory(True, True, "0.3.0", None)  # a served tenant on the same version
    row = initial_validation(
        candidate_release_id=candidate,
        candidate_version="0.3.0",
        history=history,
        declared={"0.3.0": "PATCH"},
        source_release_id=UUID(int=10),
    )
    assert row.status is ReleaseValidationStatus.PENDING and not row.enabled_at_creation
    assert row.effective_level == "PATCH" and row.reason == SAME_VERSION_REBUILD
    assert row.source_engine_release_id == UUID(int=10)
    # The gate holds: a PENDING row (enabled_at NULL) and an absent row both refuse.
    for validations in ({candidate: None}, {}):
        admission = persist_admission(candidate, validations)
        assert not admission.allowed and admission.problem == "release-validation-pending"
    with pytest.raises(ValueError, match=REFUSAL):
        check_declaration(
            "PATCH",
            previous_version="0.3.0",
            candidate_version="0.3.0",
            previous_build="a" * 40,
            candidate_build="b" * 40,
        )
