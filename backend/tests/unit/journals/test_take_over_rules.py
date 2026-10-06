"""Item JRN-HELD-AFTER-EXPORT-1 as pure rules (the supervisor's ruling of 2026-10-02; register
index 223; ENGINE_SPEC_B S14-R-17 rev 1.164; 04 DB-16 and T-CLS-02 rev 1.267). CPU-only: which
lines the key's next run may take over, what coverage counts for the run that took them, and
where the calculation and the drill read the set. The database witnesses are
``tests/domain/journals/test_held_after_export.py``.
"""

from __future__ import annotations

import inspect
from decimal import Decimal
from pathlib import Path
from typing import Final
from uuid import UUID

from erev_api.domain.journals import completeness, queries, summarise
from erev_api.domain.journals.completeness import ActivityLine, RunCoverage, RunRecord

DOCS: Final = Path(__file__).resolve().parents[4] / "docs"
RUN_1, RUN_2, RUN_3 = (UUID(int=number) for number in (1, 2, 3))
LINE_A, LINE_B, LINE_C = (UUID(int=number) for number in (11, 12, 13))


def _line(line_id: UUID, chain_seq: int, book_code: str = "ASC606") -> ActivityLine:
    return ActivityLine(
        subledger_line_id=line_id,
        chain_seq=chain_seq,
        account_code="4010",
        amount_functional=Decimal("-100.00"),
        schedule_line_id=None,
        contract_id=None,
        obligation_id=None,
        book_code=book_code,
    )


def test_the_next_run_may_take_what_a_run_left_out_and_none_has_taken() -> None:
    """S14-R-17 rev 1.164: the set is every line that a run of the key which is not cancelled
    left out as held, less every line such a run has taken over — each with the run that left it
    out. A run whose exclusions cannot be verified names no line. The records are those of the
    runs that are not cancelled, so the cancel of a taking run gives its lines back and a line a
    cancelled run left out is in no set: it lies in the next run's range again."""
    left = completeness.left_out(
        {
            RUN_1: RunRecord(excluded=frozenset({LINE_A, LINE_B})),
            RUN_2: RunRecord(excluded=frozenset({LINE_C}), taken_over=frozenset({LINE_A})),
        }
    )
    assert left == {LINE_B: RUN_1, LINE_C: RUN_2}
    # taken once: with the taking run among the records the line is in no later set
    again = completeness.left_out(
        {
            RUN_1: RunRecord(excluded=frozenset({LINE_A})),
            RUN_2: RunRecord(excluded=frozenset(), taken_over=frozenset({LINE_A})),
            RUN_3: RunRecord(excluded=frozenset()),
        }
    )
    assert again == {}
    # the taking run cancelled: its record is not among them, and the line is back
    assert completeness.left_out({RUN_1: RunRecord(excluded=frozenset({LINE_A}))}) == {
        LINE_A: RUN_1
    }
    # a run whose held detail cannot be verified names nothing; nothing is taken from it
    assert completeness.left_out({RUN_1: RunRecord(excluded=None)}) == {}
    assert completeness.left_out({}) == {}


def test_a_run_covers_the_lines_it_took_over_wherever_their_chain_sequence_lies() -> None:
    """04 T-CLS-02 rev 1.267: a line is covered by the run whose range holds it and that did not
    leave it out, or by the run that took it over. The taking run's range (2, 2] holds nothing;
    the line of chain sequence 2 it took over is covered by it, and the line that is still left
    out is covered by no run."""
    leaving = RunCoverage(
        id=RUN_1,
        mode="GROSS",
        from_chain_seq=0,
        to_chain_seq=2,
        excluded=frozenset({LINE_A, LINE_B}),
    )
    taking = RunCoverage(
        id=RUN_2,
        mode="GROSS",
        from_chain_seq=2,
        to_chain_seq=2,
        excluded=frozenset(),
        included=frozenset({LINE_A}),
    )
    lines = [_line(LINE_A, 2), _line(LINE_B, 2), _line(LINE_C, 1)]
    covered = completeness.coverage_of(lines, [leaving, taking], primary_book="ASC606")
    assert [(item.subledger_line_id, sorted(item.covered_by)) for item in covered] == [
        (LINE_A, ["GROSS"]),
        (LINE_B, []),
        (LINE_C, ["GROSS"]),
    ]
    # without the taking run both left-out lines are uncovered, as before the revision
    alone = completeness.coverage_of(lines, [leaving], primary_book="ASC606")
    assert [sorted(item.covered_by) for item in alone] == [[], [], ["GROSS"]]
    # a run whose exclusions cannot be verified covers nothing of its range, and still covers
    # what it took over: that record is its own
    unverified = RunCoverage(
        id=RUN_3,
        mode="GROSS",
        from_chain_seq=0,
        to_chain_seq=2,
        excluded=None,
        included=frozenset({LINE_B}),
    )
    only = completeness.coverage_of(lines, [unverified], primary_book="ASC606")
    assert [sorted(item.covered_by) for item in only] == [[], ["GROSS"], []]


def test_the_calculation_and_the_drill_read_the_set_the_run_recorded() -> None:
    """The calculation reads the set under the key's coverage lock (``read_detail``, called by
    ``calculate`` after ``lock_coverage``), keeps the lines of the mode's books whose contract is
    under no open hold, summarizes them with the lines of its range and records them under the
    name coverage reads; the drill of a journal line adds the lines its run took over."""
    detail = inspect.getsource(summarise.read_detail)
    assert "left = completeness.left_out_of(" in detail
    taken = (
        "taken = [(line, left[line.id]) for line in candidates if line.contract_id not in holds]"
    )
    assert taken in detail
    assert "kept=[*kept, *(line for line, _ in taken)]," in detail
    assert "if mode is JournalRunMode.DELTA and book_code != BookCode.LEGACY.value:" in detail
    calculation = inspect.getsource(summarise.calculate)
    assert calculation.index("lock_coverage(") < calculation.index("found = read_detail(")
    assert f'"{completeness.TAKEN_OVER}": sorted(str(line.id) for line, _ in taken),' in calculation
    assert completeness.TAKEN_OVER == "taken_over_subledger_line_ids"
    records = inspect.getsource(completeness.run_records)
    assert ".get(TAKEN_OVER)" in records
    drill = inspect.getsource(queries.drill_ids)
    # rev 1.288 (item SUBLEDGER-LINE-JOURNAL-RUN-1): the drill reads the run's whole record by
    # one call — what it left out and what it took over — with the store and the key ring, and
    # at the instant the run was created at
    assert drill.count("completeness.run_records(") == 1
    read = drill[drill.index("completeness.run_records(") : drill.index(")[run_id]")]
    assert all(part in read for part in ("[run_id],", "files=files,", "keyring=keyring,"))
    assert "taken = record.taken_over" in drill
    assert "summarise.left_out_statement(" in drill


def _line_of(document: str, start: str) -> str:
    """The one line of a governed document that starts with ``start``."""
    lines = (DOCS / document).read_text(encoding="utf-8").splitlines()
    [found] = [line for line in lines if line.startswith(start)]
    return found


def test_the_rows_state_the_taking_over() -> None:
    """ENGINE_SPEC_B S14-R-17 rev 1.164 and 04 T-SL-06 \"Taking over\" rev 1.267 state the rule
    the code follows, under the member name the code writes: who takes a line over, once, what
    the cancel gives back, and what ``JE_COMPLETE`` counts. The close run's step asks for every
    posting no run journalised that is under no hold (``close_runs._journal_pending``)."""
    from erev_api.domain.close import close_runs

    rule = _line_of("accounting/ENGINE_SPEC_B.md", "| S14-R-17 |")
    assert (
        "**a released line is journalised by the next run of its entity, book and period.**" in rule
    )
    assert f"`{completeness.TAKEN_OVER}`" in rule
    assert "so a line is taken over once; the cancel of the taking run gives it back" in rule
    assert "a LEGACY line is taken over by a `DELTA` run alone (S14-R-23)" in rule
    taking = _line_of("04-DATA_MODEL.md", "Taking over (rev 1.267;")
    assert f"`{completeness.TAKEN_OVER}`, an empty list where it took none" in taking
    assert "`taken_over_detail_file_id`, `taken_over_detail_sha256`" in taking
    assert "or by the run that took it over" in taking
    assert "No table, column, type, trigger or migration" in taking
    pending = inspect.getsource(close_runs._journal_pending)
    assert "return found.run_count == 0 or bool(found.uncovered_postings)" in pending
