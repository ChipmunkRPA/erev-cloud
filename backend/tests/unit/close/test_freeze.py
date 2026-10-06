"""The lock freeze's cutoff and coverage guard (supervisor ruling R-19, 2026-09-30; ENGINE_SPEC_B
S15-R-18c; ``erev_api.domain.close.freeze``). No database: the cutoff over a stub session, the
findings over a ``Coverage`` and the named refusals."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.close import dependencies, freeze, gates
from erev_api.problems import Problem

APPLICATION = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)  # the decision's application instant
SERVER = datetime(2026, 9, 12, 12, 0, 3, tzinfo=UTC)  # the server clock, three seconds ahead
SCOPE = gates.PeriodScope(
    state_id=UUID("00000000-0000-0000-0000-00000000cc01"),
    entity_id=UUID("00000000-0000-0000-0000-0000000000e1"),
    entity_code="AVM-US",
    functional_currency="USD",
    book_code="ASC606",
    period_id=UUID("00000000-0000-0000-0000-000000000f08"),
    period_key="FY2026-P08",
    period_name="Aug 2026",
    start_date=date(2026, 8, 1),
    end_date=date(2026, 8, 31),
    state="closing",
    current_lock_id=None,
    row_version=3,
)


class _Session:
    """Answers ``transaction_timestamp()`` with the given value."""

    def __init__(self, started: Any) -> None:
        self.started = started

    def execute(self, statement: Any) -> _Session:
        assert "transaction_timestamp" in str(statement)
        return self

    def scalar_one(self) -> Any:
        return self.started


def test_the_cutoff_is_the_later_of_the_application_instant_and_the_transaction_timestamp() -> None:
    """R-19 (a): a server clock ahead of the application clock moves the cutoff to the server's —
    where the versions committed before the decision are stamped; an application clock ahead
    keeps its own instant. Fail-first: the cutoff was ``uow.now`` whatever the server clock."""
    assert freeze.freeze_cutoff(_Session(SERVER), APPLICATION) == SERVER  # type: ignore[arg-type]
    behind = APPLICATION - timedelta(seconds=5)
    assert freeze.freeze_cutoff(_Session(behind), APPLICATION) == APPLICATION  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        freeze.freeze_cutoff(_Session(None), APPLICATION)  # type: ignore[arg-type]


def test_a_period_within_the_cutoff_has_no_finding() -> None:
    assert freeze.coverage_findings(freeze.Coverage(cutoff=SERVER)) == ()


def test_everything_beyond_the_cutoff_is_named() -> None:
    """R-19 (b): lines of the period recorded after the cutoff, journal runs created after it and
    each contract whose posting version is known only after it — with the instants."""
    later = SERVER + timedelta(seconds=2)
    found = freeze.Coverage(
        cutoff=SERVER,
        late_lines=2,
        latest_line_at=later,
        late_runs=1,
        latest_run_at=later,
        late_versions=(
            freeze.LateVersion("A:B", later),
            freeze.LateVersion("SF-ORD-10001", later + timedelta(seconds=1)),
        ),
    )
    reasons = freeze.coverage_findings(found)
    assert reasons == (
        "2 subledger line(s) of the period are recorded after the freeze cutoff "
        "2026-09-12T12:00:03+00:00 (the latest at 2026-09-12T12:00:05+00:00); the frozen datasets "
        "would not hold them.",
        "1 journal run(s) of the period are created after the freeze cutoff "
        "2026-09-12T12:00:03+00:00 (the latest at 2026-09-12T12:00:05+00:00); the frozen journal "
        "population would not hold them.",
        "contract A:B has subledger lines of the period within the freeze cutoff "
        "2026-09-12T12:00:03+00:00, and the contract version that posted them is known only at "
        "2026-09-12T12:00:05+00:00; the version-based datasets would not hold the contract.",
        "contract SF-ORD-10001 has subledger lines of the period within the freeze cutoff "
        "2026-09-12T12:00:03+00:00, and the contract version that posted them is known only at "
        "2026-09-12T12:00:06+00:00; the version-based datasets would not hold the contract.",
    )
    many = freeze.Coverage(
        cutoff=SERVER,
        late_versions=tuple(freeze.LateVersion(f"K-{n:03d}", later) for n in range(45)),
    )
    assert len(freeze.coverage_findings(many)) == freeze.NAMED_CONTRACTS  # the first twenty


def test_a_period_that_moved_while_the_lock_was_decided_is_named() -> None:
    """R-19 (b): a posting or a journal run another transaction committed into the period after
    the freeze began — whatever its stamps — shows as ``Activity`` that is no longer what it was
    before the freeze. An unchanged period has no finding."""
    before = freeze.Activity(lines=2, runs=1)
    assert (
        freeze.coverage_findings(freeze.Coverage(cutoff=SERVER, at_freeze=before, now=before)) == ()
    )
    moved = freeze.Coverage(cutoff=SERVER, at_freeze=before, now=freeze.Activity(lines=4, runs=2))
    assert freeze.coverage_findings(moved) == (
        "subledger lines were posted into the period while the lock was being decided (2 at the "
        "freeze, 4 now); the frozen datasets do not hold them all.",
        "the journal runs of the period changed while the lock was being decided (1 at the "
        "freeze, 2 now); the frozen journal population is not theirs.",
    )
    cancelled = freeze.Coverage(
        cutoff=SERVER, at_freeze=before, now=freeze.Activity(lines=2, runs=0)
    )
    assert freeze.coverage_findings(cancelled) == (
        "the journal runs of the period changed while the lock was being decided (1 at the "
        "freeze, 0 now); the frozen journal population is not theirs.",
    )


def _refused(problem: Problem, rule_id: str) -> list[str]:
    assert (problem.slug, problem.status) == ("invalid-transition", 409)
    assert {error.rule_id for error in problem.errors} == {rule_id}
    assert all(error.field is None for error in problem.errors)
    assert str(problem.detail).startswith("FY2026-P08 of AVM-US in book ASC606 is not locked: ")
    return [error.message for error in problem.errors]


def test_the_refusals_name_the_period_and_every_reason() -> None:
    """R-19 (b) and (c): 409 ``invalid-transition`` — the rule is S15-R-18c for the coverage
    guard and S15-R-18 for a dataset the registry refuses; the detail names the period, the
    entity, the book and the reason; every reason is an ``errors[]`` entry."""
    reasons = ("first reason.", "second reason.")
    problem = freeze.not_covered(SCOPE, reasons)
    assert _refused(problem, "S15-R-18c") == list(reasons)
    assert problem.detail == (
        "FY2026-P08 of AVM-US in book ASC606 is not locked: 2 findings; the first: first reason."
    )
    single = freeze.not_covered(SCOPE, reasons[:1])
    assert single.detail == "FY2026-P08 of AVM-US in book ASC606 is not locked: first reason."
    refused = freeze.dataset_refused(
        SCOPE, "CONTRACT_BALANCE_ROLLFORWARD", "row OPENING lacks the required column currency"
    )
    assert _refused(refused, "S15-R-18") == [
        "the CONTRACT_BALANCE_ROLLFORWARD dataset cannot be frozen (row OPENING lacks the required "
        "column currency)."
    ]
    retained = freeze.artefact_refused(SCOPE, "SNAPSHOT_DATASET RPO is retained as text/csv")
    assert _refused(retained, "S15-R-18") == [
        "a retained dataset cannot be reused (SNAPSHOT_DATASET RPO is retained as text/csv)."
    ]


def test_the_registry_handle_carries_the_registrys_own_refusal_type() -> None:
    """R-19 (c): the decision catches the refusal the registry raises — resolved by name with the
    registry, as its datasets and scope are."""
    from erev_api.domain.reports import snapshots as registry

    resolved = dependencies.snapshot_registry()
    assert resolved.refusal is registry.SnapshotRefusal
    assert issubclass(registry.SnapshotDependencyMissing, resolved.refusal)
    raised = registry.SnapshotRefusal("RPO", "row r1: the required column currency is empty")
    assert (raised.kind, raised.reason) == ("RPO", "row r1: the required column currency is empty")
