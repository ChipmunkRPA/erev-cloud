"""CLO-10 completeness assertions as pure rules (REQ-JE-005; BUILD_SPEC CLO-10; F-CLO record
§25.18).

CPU-only: ``completeness.assess`` over activity lines, per-mode journal totals and per-run entry
sequences — the same function ``assert_completeness`` feeds from the database. Coverage is
journalisation with line identities alongside totals (Codex production-20260921-0845 §4, 0908 §5,
0920 §2 / §3, 1054 §2 R1 / R2): offsetting uncovered activity is two findings; covered activity a
run legitimately netted away (S14-R-18) is complete without a journal line; a held line is named
with its hold; a released hold recovers nothing until a run journalises the line; a ``DELTA`` run's
LEGACY addition is compared mode-aware; JE continuity is per run. These tests supply the
``covered_by`` flags themselves — except the ``coverage_of`` witnesses, which derive them from
run ranges and each run's recorded exclusions (Codex 1317 R5-ORDER-1: no timestamp order) — and
the database reconstruction is exercised by ``tests/domain/journals/test_completeness.py`` (NOT RUN
without a lane database). The finding unit is the sealed posting (Codex 1317 CLO-FIXTURE-SEAL-1)."""

from __future__ import annotations

from decimal import Decimal
from typing import Final
from uuid import UUID

from erev_api.domain.journals import completeness, summarise
from erev_api.enums import ChecklistStatus

LINE_A: Final = UUID("00000000-0000-4000-8000-00000000a001")
LINE_B: Final = UUID("00000000-0000-4000-8000-00000000a002")
LINE_C: Final = UUID("00000000-0000-4000-8000-00000000a003")
LINE_L: Final = UUID("00000000-0000-4000-8000-00000000a00e")
SCHEDULE_LINE: Final = UUID("00000000-0000-4000-8000-00000000c001")
CONTRACT: Final = UUID("00000000-0000-4000-8000-00000000d001")
HOLD: Final = UUID("00000000-0000-4000-8000-00000000e001")
GROSS: Final = frozenset({"GROSS"})
DELTA: Final = frozenset({"DELTA"})
NONE: Final = frozenset()


def _activity(
    line_id: UUID,
    chain_seq: int,
    amount: str,
    *,
    account: str = "5001",
    schedule_line_id: UUID | None = SCHEDULE_LINE,
    covered_by: frozenset[str] = GROSS,
    hold_id: UUID | None = None,
    book: str = "ASC606",
) -> completeness.ActivityLine:
    return completeness.ActivityLine(
        subledger_line_id=line_id,
        chain_seq=chain_seq,
        account_code=account,
        amount_functional=Decimal(amount),
        schedule_line_id=schedule_line_id,
        contract_id=CONTRACT,
        obligation_id=None,
        book_code=book,
        covered_by=covered_by,
        hold_id=hold_id,
    )


def _gross(**totals: str) -> dict[str, dict[str, Decimal]]:
    return {"GROSS": {code: Decimal(value) for code, value in totals.items()}}


def test_sequence_gaps_name_the_entry_before_the_gap() -> None:
    assert completeness.sequence_gaps([1, 2, 4]) == (2,)
    assert completeness.sequence_gaps([4, 2, 1]) == (2,)
    assert completeness.sequence_gaps([1, 2, 3]) == ()
    assert completeness.sequence_gaps([]) == ()
    assert completeness.sequence_gaps([2, 3]) == ()  # a run's numbering starts where it starts
    assert completeness.sequence_gaps([1, 1, 2]) == ()  # duplicates are not gaps


def test_continuity_is_per_run_because_the_je_series_is_per_entity() -> None:
    """1054 R2: period A, period B and period A again allocate 1, 2, 3 of one entity series; the
    two runs of period A hold [1] and [3] — no gap. A missing entry inside one run's block is."""
    assert completeness.run_sequence_gaps([[1], [3]]) == ()
    assert completeness.run_sequence_gaps([[1], [2], [3]]) == ()
    assert completeness.run_sequence_gaps([[5, 6], [9, 10]]) == ()
    assert completeness.run_sequence_gaps([[1, 2, 4]]) == (2,)
    assert completeness.run_sequence_gaps([[1, 3], [7, 9]]) == (1, 7)


def test_sequence_gap_is_a_failed_result_with_the_governed_detail() -> None:
    result = completeness.assess(
        activity=[_activity(LINE_A, 1, "-100.00")],
        journal_totals=_gross(**{"5001": "-100.00"}),
        entry_seqs=[[1, 2, 4]],
        covered_to=1,
        run_count=1,
    )
    assert (result.status, result.count) == (ChecklistStatus.FAILED, 1)
    assert result.detail == "JE sequence gap after 2"
    assert result.gaps == (2,)


def test_interleaved_runs_of_other_periods_are_not_a_gap() -> None:
    """1054 R2 witness: this period's two runs hold entries 1 and 3 (2 belongs to another
    period or book): PASSED, no gap."""
    result = completeness.assess(
        activity=[_activity(LINE_A, 1, "-100.00"), _activity(LINE_B, 2, "-50.00")],
        journal_totals=_gross(**{"5001": "-150.00"}),
        entry_seqs=[[1], [3]],
        covered_to=2,
        run_count=2,
    )
    assert (result.status, result.count, result.gaps) == (ChecklistStatus.PASSED, 0, ())


def test_covered_and_equal_activity_passes() -> None:
    result = completeness.assess(
        activity=[_activity(LINE_A, 3, "-250.00"), _activity(LINE_B, 5, "-750.00")],
        journal_totals=_gross(**{"5001": "-1000.00"}),
        entry_seqs=[[1, 2]],
        covered_to=5,
        run_count=1,
    )
    assert (result.status, result.count, result.detail) == (ChecklistStatus.PASSED, 0, None)
    assert result.uncovered == () and result.held == ()
    assert result.differences == () and result.gaps == ()
    assert result.modes == ("GROSS",)


def test_new_activity_after_the_covered_range_names_the_account_and_schedule_line() -> None:
    """CTL-019: a delivery after the run adds revenue; the assertion names account 5001 and the
    uncovered schedule line with count 1. The totals compare journal to covered activity, so the
    uncovered line is one finding, not a finding plus a difference."""
    result = completeness.assess(
        activity=[
            _activity(LINE_A, 3, "-250.00"),
            _activity(LINE_B, 7, "-250.00", covered_by=NONE),
        ],
        journal_totals=_gross(**{"5001": "-250.00"}),
        entry_seqs=[[1]],
        covered_to=5,
        run_count=1,
    )
    assert (result.status, result.count) == (ChecklistStatus.FAILED, 1)
    (uncovered,) = result.uncovered
    assert (uncovered.subledger_line_id, uncovered.account_code, uncovered.schedule_line_id) == (
        LINE_B,
        "5001",
        SCHEDULE_LINE,
    )
    assert result.detail is not None
    assert "5001" in result.detail and str(SCHEDULE_LINE) in result.detail
    assert result.differences == ()


def test_offsetting_uncovered_lines_are_two_findings() -> None:
    """Codex 0908 §5 / 0920 §2 witness: two uncovered lines of +100 and −100 leave the account
    total equal to the journal total and are still two uncovered lines — matching aggregates never
    pass completeness while activity remains uncovered."""
    result = completeness.assess(
        activity=[
            _activity(LINE_A, 2, "-100.00"),
            _activity(LINE_B, 8, "100.00", schedule_line_id=None, covered_by=NONE),
            _activity(LINE_C, 9, "-100.00", schedule_line_id=None, covered_by=NONE),
        ],
        journal_totals=_gross(**{"5001": "-100.00"}),
        entry_seqs=[[1]],
        covered_to=9,  # the run range holds them; the range alone is not coverage
        run_count=1,
    )
    assert (result.status, result.count) == (ChecklistStatus.FAILED, 2)
    assert result.differences == ()
    assert [item.subledger_line_id for item in result.uncovered] == [LINE_B, LINE_C]
    assert result.detail is not None and result.detail.count("uncovered line") == 2


def test_covered_activity_netted_away_by_the_run_is_complete() -> None:
    """Codex 0920 §2 witness: two covered lines of +100 and −100 on one account form a group whose
    transaction and functional nets are zero; S14-R-18 drops the group, so no journal line exists
    for the account — and none is demanded: the assertion passes with count 0."""
    result = completeness.assess(
        activity=[
            _activity(LINE_A, 3, "-250.00"),
            _activity(LINE_B, 4, "100.00", account="2100", schedule_line_id=None),
            _activity(LINE_C, 4, "-100.00", account="2100", schedule_line_id=None),
        ],
        journal_totals=_gross(**{"5001": "-250.00"}),
        entry_seqs=[[1]],
        covered_to=4,
        run_count=1,
    )
    assert (result.status, result.count, result.detail) == (ChecklistStatus.PASSED, 0, None)


def test_netted_covered_activity_beside_offsetting_uncovered_activity() -> None:
    """The two witnesses together: the covered zero-net pair is complete, the uncovered offsetting
    pair is two findings — completeness distinguishes valid zero-net grouping from omitted
    activity."""
    result = completeness.assess(
        activity=[
            _activity(LINE_A, 4, "100.00", account="2100", schedule_line_id=None),
            _activity(LINE_B, 4, "-100.00", account="2100", schedule_line_id=None),
            _activity(UUID(int=7), 7, "100.00", account="2100", covered_by=NONE),
            _activity(UUID(int=8), 8, "-100.00", account="2100", covered_by=NONE),
        ],
        journal_totals={},
        entry_seqs=[[]],
        covered_to=8,
        run_count=1,
    )
    assert (result.status, result.count) == (ChecklistStatus.FAILED, 2)
    assert result.differences == ()
    assert {item.subledger_line_id for item in result.uncovered} == {UUID(int=7), UUID(int=8)}


def test_journal_total_that_differs_from_covered_activity_counts_once_per_account() -> None:
    result = completeness.assess(
        activity=[_activity(LINE_A, 3, "-250.00")],
        journal_totals=_gross(**{"5001": "-200.00", "2100": "50.00"}),
        entry_seqs=[[1]],
        covered_to=5,
        run_count=1,
    )
    assert (result.status, result.count) == (ChecklistStatus.FAILED, 2)
    assert [(item.account_code, item.mode) for item in result.differences] == [
        ("2100", "GROSS"),
        ("5001", "GROSS"),
    ]
    assert result.detail is not None and "GROSS journal -200.00" in result.detail


def test_delta_run_is_compared_with_primary_plus_legacy_coverage() -> None:
    """1054 R1 witness: a ``DELTA`` run journalises the primary line (−250) and the LEGACY book's
    line (+100, no negation — S14-R-23) as one group of −150. Mode-aware, the DELTA journal total
    −150 equals the activity that DELTA run covered (−250 + 100): PASSED. A comparison with the
    primary book alone (−250) would have reported a false difference."""
    result = completeness.assess(
        activity=[
            _activity(LINE_A, 3, "-250.00", covered_by=DELTA),
            _activity(LINE_L, 1, "100.00", schedule_line_id=None, covered_by=DELTA, book="LEGACY"),
        ],
        journal_totals={"DELTA": {"5001": Decimal("-150.00")}},
        entry_seqs=[[1]],
        covered_to=3,
        run_count=1,
    )
    assert (result.status, result.count, result.detail) == (ChecklistStatus.PASSED, 0, None)
    assert result.modes == ("DELTA",)


def test_uncovered_legacy_line_of_a_delta_scope_is_named_with_its_book() -> None:
    """A LEGACY line sealed after the DELTA run's delta range is uncovered and named with its
    book; the DELTA totals still match what the run covered."""
    result = completeness.assess(
        activity=[
            _activity(LINE_A, 3, "-250.00", covered_by=DELTA),
            _activity(LINE_L, 1, "100.00", schedule_line_id=None, covered_by=DELTA, book="LEGACY"),
            _activity(LINE_B, 2, "50.00", schedule_line_id=None, covered_by=NONE, book="LEGACY"),
        ],
        journal_totals={"DELTA": {"5001": Decimal("-150.00")}},
        entry_seqs=[[1]],
        covered_to=3,
        run_count=1,
    )
    assert (result.status, result.count) == (ChecklistStatus.FAILED, 1)
    (uncovered,) = result.uncovered
    assert (uncovered.subledger_line_id, uncovered.book_code) == (LINE_B, "LEGACY")
    assert result.detail == f"Account 5001 (LEGACY): uncovered line {LINE_B} (chain 2, 50.00)"
    assert result.differences == ()


def test_delta_journal_that_omits_the_legacy_addition_is_a_named_difference() -> None:
    """The mismatch 1054 R1 protects: a DELTA run whose journal total is the primary line alone
    (−250) while the run covered −250 + 100 — a real difference, not suppressed."""
    result = completeness.assess(
        activity=[
            _activity(LINE_A, 3, "-250.00", covered_by=DELTA),
            _activity(LINE_L, 1, "100.00", schedule_line_id=None, covered_by=DELTA, book="LEGACY"),
        ],
        journal_totals={"DELTA": {"5001": Decimal("-250.00")}},
        entry_seqs=[[1]],
        covered_to=3,
        run_count=1,
    )
    assert (result.status, result.count) == (ChecklistStatus.FAILED, 1)
    assert result.differences == (
        completeness.AccountDifference(
            account_code="5001",
            journal_total=Decimal("-250.00"),
            activity_total=Decimal("-150.00"),
            mode="DELTA",
        ),
    )


def test_gross_and_delta_runs_of_one_period_are_compared_each_with_their_own_coverage() -> None:
    """A GROSS run and a later DELTA run of one period: DB-16 (04 rev 1.106; security finding SC-7)
    lets each seal be journalised by one run only, so the DELTA run covers the primary line sealed
    after the GROSS run (−120) plus the LEGACY line (+100), and each mode's journal is compared with
    what that mode's runs covered. Until revision 0085 this case held one line covered by both
    modes — the double coverage the coverage guard now refuses."""
    result = completeness.assess(
        activity=[
            _activity(LINE_A, 3, "-250.00", covered_by=GROSS),
            _activity(LINE_B, 4, "-120.00", covered_by=DELTA),
            _activity(LINE_L, 1, "100.00", schedule_line_id=None, covered_by=DELTA, book="LEGACY"),
        ],
        journal_totals={
            "GROSS": {"5001": Decimal("-250.00")},
            "DELTA": {"5001": Decimal("-20.00")},
        },
        entry_seqs=[[1], [2]],
        covered_to=4,
        run_count=2,
    )
    assert (result.status, result.count) == (ChecklistStatus.PASSED, 0)
    assert result.modes == ("DELTA", "GROSS")
    # The comparison stays per mode: a DELTA journal that repeated the GROSS run's line (−250 on
    # top of its own −20) is a named difference of the DELTA mode, not netted against GROSS.
    repeated = completeness.assess(
        activity=[
            _activity(LINE_A, 3, "-250.00", covered_by=GROSS),
            _activity(LINE_B, 4, "-120.00", covered_by=DELTA),
            _activity(LINE_L, 1, "100.00", schedule_line_id=None, covered_by=DELTA, book="LEGACY"),
        ],
        journal_totals={
            "GROSS": {"5001": Decimal("-250.00")},
            "DELTA": {"5001": Decimal("-270.00")},
        },
        entry_seqs=[[1], [2]],
        covered_to=4,
        run_count=2,
    )
    assert (repeated.status, repeated.count) == (ChecklistStatus.FAILED, 1)
    assert repeated.differences == (
        completeness.AccountDifference(
            account_code="5001",
            journal_total=Decimal("-270.00"),
            activity_total=Decimal("-20.00"),
            mode="DELTA",
        ),
    )


def test_held_uncovered_line_is_named_with_its_hold_and_counted() -> None:
    """S14-R-17: a line the run left out because its contract was under a ``journal_export`` hold
    is not journalised; it is a named blocker (the hold named) until a run journalises it — the run
    range holding its chain sequence is not coverage (Codex 0920 §3)."""
    result = completeness.assess(
        activity=[
            _activity(LINE_A, 3, "-250.00"),
            _activity(LINE_B, 4, "-99.00", covered_by=NONE, hold_id=HOLD),
        ],
        journal_totals=_gross(**{"5001": "-250.00"}),
        entry_seqs=[[1]],
        covered_to=4,
        run_count=1,
    )
    assert (result.status, result.count) == (ChecklistStatus.FAILED, 1)
    (held,) = result.held
    assert (held.subledger_line_id, held.hold_id, held.account_code) == (LINE_B, HOLD, "5001")
    assert result.uncovered == () and result.differences == ()
    assert result.detail == (
        f"Account 5001: held schedule line {SCHEDULE_LINE} (chain 4, -99.00; hold {HOLD})"
    )


def test_released_hold_recovers_nothing_until_a_run_journalises_the_line() -> None:
    """Release ≠ recovery (Codex 0920 §3): after the hold is released the line is simply uncovered
    — a fresh run starting after the prior range does not reach it; only a run that journalises
    it (cancel and recalculate from zero) makes the period complete. The flag comes from the
    database reconstruction; the exclusion ordering it rests on is established there."""
    result = completeness.assess(
        activity=[
            _activity(LINE_A, 3, "-250.00"),
            _activity(LINE_B, 4, "-99.00", covered_by=NONE, hold_id=None),
        ],
        journal_totals=_gross(**{"5001": "-250.00"}),
        entry_seqs=[[1], []],
        covered_to=6,
        run_count=2,
    )
    assert (result.status, result.count) == (ChecklistStatus.FAILED, 1)
    assert result.held == ()
    assert [item.subledger_line_id for item in result.uncovered] == [LINE_B]


def test_journalised_line_under_a_later_hold_is_covered() -> None:
    """A hold applied after the run journalised the line blocks the export, not completeness."""
    result = completeness.assess(
        activity=[_activity(LINE_A, 3, "-250.00", hold_id=HOLD)],
        journal_totals=_gross(**{"5001": "-250.00"}),
        entry_seqs=[[1]],
        covered_to=3,
        run_count=1,
    )
    assert (result.status, result.count) == (ChecklistStatus.PASSED, 0)
    assert result.held == ()


def test_no_run_fails_closed_by_name() -> None:
    result = completeness.assess(
        activity=[_activity(LINE_A, 3, "-250.00", covered_by=NONE)],
        journal_totals={},
        entry_seqs=[],
        covered_to=0,
        run_count=0,
    )
    assert (result.status, result.count, result.detail) == (
        ChecklistStatus.FAILED,
        1,
        completeness.RUN_NOT_CALCULATED,
    )


RUN_1: Final = UUID("00000000-0000-4000-8000-00000000f001")
RUN_2: Final = UUID("00000000-0000-4000-8000-00000000f002")


def _run(
    run_id: UUID,
    to_seq: int,
    *,
    excluded: frozenset[UUID] | None = frozenset(),
    mode: str = "GROSS",
    from_seq: int = 0,
) -> completeness.RunCoverage:
    return completeness.RunCoverage(
        id=run_id, mode=mode, from_chain_seq=from_seq, to_chain_seq=to_seq, excluded=excluded
    )


def _raw(
    line_id: UUID,
    chain_seq: int,
    amount: str,
    *,
    schedule_line_id: UUID | None = SCHEDULE_LINE,
    book: str = "ASC606",
) -> completeness.ActivityLine:
    return _activity(
        line_id, chain_seq, amount, schedule_line_id=schedule_line_id, covered_by=NONE, book=book
    )


def test_audit_facts_are_the_generators() -> None:
    """The exclusions are read from the run's CALCULATE audit event, which ``summarise`` writes."""
    assert completeness.CALCULATE_ACTION == summarise.CALCULATE_ACTION
    assert completeness.RUN_OBJECT_TYPE == summarise.OBJECT_TYPE


def test_coverage_follows_the_range_and_the_recorded_exclusions_not_timestamps() -> None:
    """1317 R5-ORDER-1: the run's own record of what it left out decides. Hold → calculate →
    release at one instant: the run recorded the lines as held → not covered. Release → calculate
    at the same instant: the run recorded nothing held (explicit zero-held) → covered. No clock is
    consulted."""
    lines = [_raw(LINE_A, 3, "-100.00"), _raw(LINE_B, 3, "100.00", schedule_line_id=None)]
    excluded = completeness.coverage_of(
        lines, [_run(RUN_1, 5, excluded=frozenset({LINE_A, LINE_B}))], primary_book="ASC606"
    )
    assert [line.covered_by for line in excluded] == [NONE, NONE]
    released_first = completeness.coverage_of(lines, [_run(RUN_1, 5)], primary_book="ASC606")
    assert [line.covered_by for line in released_first] == [GROSS, GROSS]


def test_a_later_run_covers_what_an_earlier_run_excluded_only_when_its_range_reaches_it() -> None:
    """Release ≠ recovery: the second run starts after the first range (DB-16) and cannot reach the
    excluded lines; only a run whose range holds them and whose exclusions do not name them does."""
    lines = [_raw(LINE_A, 3, "-100.00")]
    later = _run(RUN_2, 8, from_seq=5)
    assert (
        completeness.coverage_of(
            lines, [_run(RUN_1, 5, excluded=frozenset({LINE_A})), later], primary_book="ASC606"
        )[0].covered_by
        == NONE
    )
    recalculated = _run(RUN_2, 8, from_seq=0)
    assert (
        completeness.coverage_of(
            lines,
            [_run(RUN_1, 5, excluded=frozenset({LINE_A})), recalculated],
            primary_book="ASC606",
        )[0].covered_by
        == GROSS
    )


def test_an_unverifiable_run_covers_nothing_and_is_a_named_finding() -> None:
    lines = completeness.coverage_of(
        [_raw(LINE_A, 3, "-100.00")], [_run(RUN_1, 5, excluded=None)], primary_book="ASC606"
    )
    assert lines[0].covered_by == NONE
    result = completeness.assess(
        activity=lines,
        journal_totals={},
        entry_seqs=[[]],
        covered_to=5,
        run_count=1,
        unverifiable_runs=[RUN_1],
    )
    assert (result.status, result.count) == (ChecklistStatus.FAILED, 2)  # the posting + the run
    assert result.detail is not None and f"Run {RUN_1}: held detail unverifiable" in result.detail


def test_delta_coverage_reads_the_legacy_range_for_legacy_lines() -> None:
    run = completeness.RunCoverage(
        id=RUN_1,
        mode="DELTA",
        from_chain_seq=0,
        to_chain_seq=3,
        delta_from_chain_seq=0,
        delta_to_chain_seq=1,
    )
    lines = [
        _raw(LINE_A, 3, "-250.00"),
        _raw(LINE_L, 1, "100.00", schedule_line_id=None, book="LEGACY"),
        _raw(LINE_B, 2, "50.00", schedule_line_id=None, book="LEGACY"),
    ]
    covered = completeness.coverage_of(lines, [run], primary_book="ASC606")
    assert [line.covered_by for line in covered] == [DELTA, DELTA, NONE]


def test_the_finding_unit_is_the_sealed_posting() -> None:
    """1317 CLO-FIXTURE-SEAL-1: a posting carries at least two balancing lines (0040 requires it);
    an uncovered posting counts once and names every line — its lines netting to zero never makes
    it complete."""
    result = completeness.assess(
        activity=[
            _activity(LINE_A, 7, "-250.00", covered_by=NONE),
            _activity(LINE_B, 7, "250.00", account="1201", schedule_line_id=None, covered_by=NONE),
        ],
        journal_totals={},
        entry_seqs=[[]],
        covered_to=7,
        run_count=1,
    )
    assert (result.status, result.count) == (ChecklistStatus.FAILED, 1)
    assert result.uncovered_postings == (("ASC606", 7),)
    assert [item.account_code for item in result.uncovered] == ["5001", "1201"]
    assert result.detail is not None and "5001" in result.detail and "1201" in result.detail
