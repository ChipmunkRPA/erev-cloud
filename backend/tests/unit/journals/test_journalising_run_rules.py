"""Item SUBLEDGER-LINE-JOURNAL-RUN-1 as pure rules (register index 265; 04 T-SL-06 drill-back and
API-S-SubledgerLine ``journal_run_id``, rev 1.288; the supervisor's ruling of 2026-10-02).
CPU-only: the one rule of what a run journalises, and who reads it. The database witnesses are
``tests/domain/journals/test_drill_record.py`` and ``test_line_journal_run.py``.
"""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, NamedTuple
from uuid import UUID

from erev_api.api.v1 import contracts as contracts_api
from erev_api.api.v1 import journal_runs as journal_runs_api
from erev_api.api.v1 import subledger as subledger_api
from erev_api.domain.contracts import queries as contract_queries
from erev_api.domain.journals import completeness, queries, subledger
from erev_api.domain.journals.completeness import (
    ActivityLine,
    RunCoverage,
    RunRecord,
    SealedLine,
)

DOCS: Final = Path(__file__).resolve().parents[4] / "docs"
RUN: Final = UUID(int=1)
TAKING: Final = UUID(int=2)
LATER: Final = UUID(int=3)
IN_RANGE, LEFT_OUT, TAKEN, BEYOND = (UUID(int=number) for number in (11, 12, 13, 14))
ENTITY, PERIOD, POSTING = (UUID(int=number) for number in (21, 22, 23))
INSTANT: Final = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)  # a run's created_at
LATER_AT: Final = datetime(2026, 10, 3, 9, 30, tzinfo=UTC)  # another run's, a month later
EVENT: Final = {
    "counts": {"held_lines": 1},
    "held_detail_file_id": str(UUID(int=99)),
    "held_detail_sha256": "0" * 64,
}
NO_HELD: Final = {"held_subledger_line_ids": []}  # the explicit zero-held state of an event
# the member's three statements, by the table each asks
TABLES: Final = ("subledger_posting_seal", "journal_run", "audit_event")


def _line(line_id: UUID, chain_seq: int) -> ActivityLine:
    return ActivityLine(
        subledger_line_id=line_id,
        chain_seq=chain_seq,
        account_code="4010",
        amount_functional=Decimal("-100.00"),
        schedule_line_id=None,
        contract_id=None,
        obligation_id=None,
    )


def _run(excluded: frozenset[UUID] | None) -> RunCoverage:
    return RunCoverage(
        id=RUN,
        mode="GROSS",
        from_chain_seq=0,
        to_chain_seq=5,
        excluded=excluded,
        included=frozenset({TAKEN}),
    )


class _Events:
    """A session that answers one run's CALCULATE event, counts the statements and counts the
    held detail files it is asked for (a file is read in a savepoint)."""

    def __init__(self, after: dict[str, Any] | None) -> None:
        self.after = after
        self.statements = 0
        self.files_asked = 0

    def begin_nested(self) -> Any:
        self.files_asked += 1
        raise AssertionError("a held detail file was asked for")

    def execute(self, statement: Any) -> _Events:
        self.statements += 1
        return self

    def all(self) -> list[tuple[UUID, dict[str, Any]]]:
        return [] if self.after is None else [(RUN, self.after)]


def test_one_rule_decides_what_a_run_journalises() -> None:
    """``completeness.summarized``: a run journalises a line it took over, wherever the line
    lies, and a line of its range that its record of the lines it left out does not name. A run
    whose record cannot be read journalises nothing of its range — what it took over it still
    names. The completeness assertion and the drill read this rule and no other: the drill
    decides nothing by a hold's timestamps any more."""
    run = _run(frozenset({LEFT_OUT}))
    assert completeness.summarized(run, IN_RANGE, in_range=True)
    assert not completeness.summarized(run, LEFT_OUT, in_range=True)
    assert completeness.summarized(run, TAKEN, in_range=False)
    assert not completeness.summarized(run, BEYOND, in_range=False)
    unreadable = _run(None)
    assert not completeness.summarized(unreadable, IN_RANGE, in_range=True)
    assert completeness.summarized(unreadable, TAKEN, in_range=False)

    # the completeness assertion: covered by the modes of the runs that journalise the line
    lines = [_line(IN_RANGE, 3), _line(LEFT_OUT, 4), _line(TAKEN, 9), _line(BEYOND, 8)]
    covered = completeness.coverage_of(lines, [run], primary_book="ASC606")
    assert [bool(line.covered_by) for line in covered] == [True, False, True, False]
    assert "summarized(" in inspect.getsource(completeness.coverage_of)

    # the drill: the same rule over the run's record, and no timestamp of a hold
    drill = inspect.getsource(queries.drill_ids)
    read = drill[drill.index("completeness.run_records(") : drill.index(")[run_id]")]
    for handed in (
        "files=files,",
        "keyring=keyring,",
        'calculated_at={run_id: run["created_at"]},',
    ):
        assert read.count(handed) == 1, handed
    assert drill.count("completeness.summarized(recorded, item.id, in_range=") == 2
    # ... and the lines it summarized are grouped at the grain the journal line was summarised
    # at, the split grain of S14-R-21 included (tests/unit/journals/test_chunking_rules.py)
    assert drill.count("summarise.lines_of_group(summarized, target, grain=grain") == 1
    assert "grouping_sha256(" not in drill
    assert not hasattr(queries, "_held_at")
    module = inspect.getsource(queries)
    assert "applied_at" not in module and "released_at" not in module


def test_a_runs_record_is_read_once_and_only_with_the_store_and_the_key_ring() -> None:
    """``completeness.run_records`` reads the runs' CALCULATE events by one statement. An event
    that names the ids is the record. An event of before the ids that counts held lines names
    its held detail file: that file is read only by a reader that hands the file store and the
    key ring, and for one that hands neither the record cannot be read — which is why the gate,
    the member and the drill each hand both. A run without an event has no record."""
    named = _Events(
        {"held_subledger_line_ids": [str(LEFT_OUT)], completeness.TAKEN_OVER: [str(TAKEN)]}
    )
    assert completeness.run_records(named, [RUN]) == {  # type: ignore[arg-type]
        RUN: RunRecord(excluded=frozenset({LEFT_OUT}), taken_over=frozenset({TAKEN}))
    }
    assert named.statements == 1
    none_held = _Events({"counts": {"held_lines": 0}})
    assert completeness.run_records(none_held, [RUN])[RUN].excluded == frozenset()  # type: ignore[arg-type]
    before_the_ids = _Events(EVENT)
    assert completeness.run_records(before_the_ids, [RUN])[RUN].excluded is None  # type: ignore[arg-type]
    # no file is asked for without the store and the ring
    assert (before_the_ids.statements, before_the_ids.files_asked) == (1, 0)
    assert completeness.run_records(_Events(None), [RUN]) == {RUN: RunRecord()}  # type: ignore[arg-type]
    assert completeness.run_records(_Events(EVENT), []) == {}  # type: ignore[arg-type]
    # the gate's own reader and the drill's hand both on
    assert "files=files, keyring=keyring" in inspect.getsource(completeness.completeness_of)
    assert "files=deps.files, keyring=deps.keyring" in inspect.getsource(
        journal_runs_api.journal_lines_drill
    )


def test_a_reader_of_every_page_asks_the_events_at_the_instants_of_its_runs() -> None:
    """``completeness.run_records`` with ``calculated_at`` — the run's ``created_at``: the read
    asks the audit log at those instants alone, since a calculation writes its run and its
    CALCULATE event at one instant and the log is partitioned by it. The record is the same
    with the bound and without it: a run whose event is not at its instant is asked for again
    without the bound, by a second statement, and a run without an event has no record either
    way. The member and the drill hand the instants; the gate reads as it did."""
    record = {RUN: RunRecord(excluded=frozenset(), taken_over=frozenset())}
    at = {RUN: INSTANT, TAKING: INSTANT}

    def read(session: _Pages, **bound: Any) -> dict[UUID, RunRecord]:
        return completeness.run_records(session, [RUN], **bound)  # type: ignore[arg-type]

    unbounded = _Pages([(RUN, NO_HELD)])
    assert read(unbounded) == record
    assert len(unbounded.statements) == 1 and "occurred_at" not in unbounded.statements[0]
    found = _Pages([(RUN, NO_HELD)])
    assert read(found, calculated_at=at) == record
    assert len(found.statements) == 1 and "audit_event.occurred_at IN" in found.statements[0]
    elsewhere = _Pages([], [(RUN, NO_HELD)])  # not at the run's instant: asked for again
    assert read(elsewhere, calculated_at=at) == record
    assert ["audit_event.occurred_at IN" in sent for sent in elsewhere.statements] == [True, False]
    nowhere = _Pages([], [])
    assert read(nowhere, calculated_at=at) == {RUN: RunRecord()}
    assert len(nowhere.statements) == 2
    # two runs, one event at its instant: the second statement finds the other
    two = _Pages([(RUN, NO_HELD)], [(TAKING, {"held_subledger_line_ids": [str(LEFT_OUT)]})])
    both = completeness.run_records(two, [RUN, TAKING], calculated_at=at)  # type: ignore[arg-type]
    assert both == {**record, TAKING: RunRecord(excluded=frozenset({LEFT_OUT}))}
    assert len(two.statements) == 2
    # who hands the instants: the member and the drill; the gate's reader is as it was
    assert "calculated_at={UUID(str(row.id)): row.created_at for row in rows}" in (
        inspect.getsource(completeness.journalising_runs)
    )
    assert 'calculated_at={run_id: run["created_at"]}' in inspect.getsource(queries.drill_ids)
    assert "calculated_at" not in inspect.getsource(completeness.completeness_of)


def test_a_line_names_the_run_that_took_it_over_or_the_run_of_its_range() -> None:
    """``completeness.journalising_run`` — 04 API-S-SubledgerLine ``journal_run_id``: the run
    that took the line over, or the run whose range holds the line's seal and whose record does
    not name it; none otherwise. In one posting book at most one run journalises a line,
    whatever the order the runs are asked in. A run of another book does not hold the line by
    its sequence, and a LEGACY line is held by the delta range of a ``DELTA`` run alone."""
    first = RunCoverage(
        id=RUN, mode="GROSS", from_chain_seq=0, to_chain_seq=5, excluded=frozenset({LEFT_OUT})
    )
    taking = RunCoverage(
        id=TAKING,
        mode="GROSS",
        from_chain_seq=5,
        to_chain_seq=5,
        excluded=frozenset(),
        included=frozenset({LEFT_OUT}),
    )
    runs = [("ASC606", first), ("ASC606", taking)]
    named = completeness.journalising_run
    for asked in (runs, list(reversed(runs))):
        assert named(IN_RANGE, "ASC606", 3, asked) == RUN
        # taken over: the taking run, though the line's seal lies in the first run's range
        assert named(LEFT_OUT, "ASC606", 4, asked) == TAKING
        assert named(BEYOND, "ASC606", 9, asked) is None  # beyond the runs
    # a line taken over is named though it is not sealed in any range the reader was handed
    assert named(LEFT_OUT, "ASC606", None, runs) == TAKING
    # left out and taken over by none; not sealed
    assert named(LEFT_OUT, "ASC606", 4, [("ASC606", first)]) is None
    assert named(IN_RANGE, "ASC606", None, runs) is None
    assert named(IN_RANGE, "ASC606", 3, []) is None  # every run of the key is cancelled
    # a run whose record cannot be read journalises nothing of its range
    assert named(IN_RANGE, "ASC606", 3, [("ASC606", _run(None))]) is None
    # another book's chain: its sequences are not this run's
    assert named(IN_RANGE, "ASC606", 3, [("IFRS15", first)]) is None
    # a LEGACY line: the delta range of a DELTA run of a posting book, and no GROSS run
    delta = _delta(TAKING)
    assert named(BEYOND, "LEGACY", 2, [("ASC606", delta)]) == TAKING
    assert named(BEYOND, "LEGACY", 3, [("ASC606", delta)]) is None
    assert named(BEYOND, "LEGACY", 2, [("ASC606", first)]) is None


def _delta(
    run_id: UUID,
    *,
    excluded: frozenset[UUID] = frozenset(),
    included: frozenset[UUID] = frozenset(),
    delta: tuple[int, int] = (0, 2),
) -> RunCoverage:
    """A ``DELTA`` run whose delta range — the LEGACY book's — is ``delta``."""
    return RunCoverage(
        id=run_id,
        mode="DELTA",
        from_chain_seq=0,
        to_chain_seq=5,
        delta_from_chain_seq=delta[0],
        delta_to_chain_seq=delta[1],
        excluded=excluded,
        included=included,
    )


def test_a_legacy_line_of_two_posting_books_names_the_first_run_asked() -> None:
    """A LEGACY line takes no run of its own book: where its entity keeps two posting books, a
    ``DELTA`` run of each can journalise it. ``journalising_run`` names the first of the runs
    it is handed that journalises the line — a run that took the line over as much as a run of
    its range — so the order of the runs decides, and ``journalising_runs`` hands them with the
    primary book's first."""
    named = completeness.journalising_run
    legacy = BEYOND
    ours, theirs, later = RUN, TAKING, LATER
    # both runs hold the line in their delta range: the first asked
    both = [("IFRS15", _delta(ours)), ("ASC606", _delta(theirs))]
    assert named(legacy, "LEGACY", 2, both) == ours
    assert named(legacy, "LEGACY", 2, list(reversed(both))) == theirs
    # the first book's run left the line out: the other book's run is named ...
    held = [("IFRS15", _delta(ours, excluded=frozenset({legacy}))), ("ASC606", _delta(theirs))]
    assert named(legacy, "LEGACY", 2, held) == theirs
    # ... until a run of the first book takes the line over
    taken = [
        *held[:1],
        ("IFRS15", _delta(later, included=frozenset({legacy}), delta=(2, 2))),
        *held[1:],
    ]
    assert named(legacy, "LEGACY", 2, taken) == later
    # a run of the first book's range is named before a run of the other book that took it over
    range_first = [
        ("IFRS15", _delta(ours)),
        ("ASC606", _delta(theirs, excluded=frozenset({legacy}))),
        ("ASC606", _delta(later, included=frozenset({legacy}), delta=(2, 2))),
    ]
    assert named(legacy, "LEGACY", 2, range_first) == ours


class _Pages:
    """A session that answers the member's statements in their order — the seals of the page's
    postings, the runs of its keys, the runs' CALCULATE events — and counts them."""

    def __init__(self, *answers: Sequence[tuple[Any, ...]]) -> None:
        self.answers = list(answers)
        self.statements: list[str] = []
        self.binds: list[list[Any]] = []  # the bound values of each statement
        self.files_asked = 0

    def begin_nested(self) -> Any:
        self.files_asked += 1
        raise AssertionError("a held detail file was asked for")

    def execute(self, statement: Any) -> _Pages:
        self.statements.append(str(statement))
        self.binds.append(list(statement.compile().params.values()))
        return self

    def all(self) -> Sequence[tuple[Any, ...]]:
        return self.answers[len(self.statements) - 1]


class _RunRow(NamedTuple):
    """A row of the member's statement on the runs."""

    id: UUID
    entity_id: UUID
    period_id: UUID
    book_code: str
    mode: str
    from_chain_seq: int
    to_chain_seq: int
    delta_from_chain_seq: int | None
    delta_to_chain_seq: int | None
    created_at: datetime
    of_primary_book: bool | None


def _run_row(run_id: UUID, book: str, of_primary_book: bool | None) -> _RunRow:
    """A ``DELTA`` run of ``book`` for the key (ENTITY, PERIOD) whose delta range is (0, 2]."""
    return _RunRow(run_id, ENTITY, PERIOD, book, "DELTA", 0, 5, 0, 2, INSTANT, of_primary_book)


def _member(session: _Pages, lines: list[SealedLine], store: Any = None) -> dict[UUID, UUID]:
    """The member of ``lines``; ``store`` stands for the file store and for the key ring."""
    return completeness.journalising_runs(
        session,  # type: ignore[arg-type]
        lines,
        files=store,
        keyring=store,
    )


def test_the_member_asks_the_runs_of_the_primary_book_first_from_three_statements() -> None:
    """``completeness.journalising_runs`` — the member of one page: three statements whatever
    the number of lines (the seals of the lines' postings, the runs of their entities and
    periods that are not cancelled, those runs' CALCULATE events), two when no run stands and
    none for no line; none of them asks the page's own table. The runs of a key are asked with
    the primary book's first, whatever the order the database hands them in: a LEGACY line that
    a ``DELTA`` run of two posting books journalises names the primary book's run. Without a
    primary book the books' codes order the runs."""
    ours, theirs = RUN, TAKING
    lines = [
        SealedLine(
            id=BEYOND,
            entity_id=ENTITY,
            period_id=PERIOD,
            book_code="LEGACY",
            subledger_posting_id=POSTING,
        )
    ]
    seals: list[tuple[Any, ...]] = [(POSTING, 2)]
    events: list[tuple[Any, ...]] = [(ours, NO_HELD), (theirs, NO_HELD)]

    def named(rows: Sequence[tuple[Any, ...]]) -> tuple[UUID | None, int]:
        session = _Pages(seals, rows, events)
        return _member(session, lines).get(BEYOND), len(session.statements)

    # IFRS15 is the primary book here: its run is named, in whichever order the rows arrive
    rows = [_run_row(theirs, "ASC606", False), _run_row(ours, "IFRS15", True)]
    assert named(rows) == (ours, 3)
    assert named(list(reversed(rows))) == (ours, 3)
    # no primary book: the books' codes, so ASC606's
    unflagged = [_run_row(ours, "IFRS15", None), _run_row(theirs, "ASC606", None)]
    assert named(unflagged) == (theirs, 3)
    assert named(list(reversed(unflagged))) == (theirs, 3)
    # the three statements, by the table each asks; the second reads which book is primary
    session = _Pages(seals, rows, events)
    _member(session, lines)
    sent = [statement.replace("erev.", "") for statement in session.statements]
    assert [
        next(table for table in TABLES if f"FROM {table}" in statement) for statement in sent
    ] == list(TABLES)
    assert "book.is_primary IS true" in sent[1]
    assert "audit_event.occurred_at IN" in sent[2]  # at the instants the runs were created at
    assert not any("subledger_line" in statement for statement in sent)
    # an event that is not at its run's instant is asked for again: the same answer, a fourth
    # statement — the product writes no such event
    late = _Pages(seals, rows, events[1:], events[:1])
    assert _member(late, lines) == {BEYOND: ours} and len(late.statements) == 4
    # no run: the events are not asked; no line: nothing is
    assert named([]) == (None, 2)
    nothing = _Pages()
    assert _member(nothing, []) == {} and nothing.statements == []
    # the file store and the key ring go on to the reader of a run's record: an event of before
    # the recorded ids is read from its held detail file only by a reader that is handed both
    # (here the file cannot be opened, so the run journalises nothing either way)
    before_the_ids = [(ours, EVENT), (theirs, NO_HELD)]
    handed, bare = (_Pages(seals, rows, before_the_ids) for _ in range(2))
    assert _member(handed, lines, store=object()) == {BEYOND: theirs} == _member(bare, lines)
    assert (handed.files_asked, bare.files_asked) == (1, 0)


def test_the_member_asks_the_runs_of_each_lines_own_entity_and_period_whatever_their_state() -> (
    None
):
    """The runs that can journalise a line are those of ITS entity and period (04 DB-16 keys a
    run's coverage on entity, book and period, and every key's ranges start at zero) that are
    not cancelled. Three lines of three keys, each sealed inside the range of the one run on the
    page: only the line of the run's own key names it — keyed by the entity alone, or by the
    period alone, the run would be named for a line it never read. The statement asks the runs
    by the pairs of the page and by ``state != cancelled``, whatever else their state is; and
    the events of runs created at two instants are asked at both."""
    other_period, other_entity = UUID(int=31), UUID(int=32)
    mine, another_period, another_entity = (UUID(int=number) for number in (41, 42, 43))
    lines = [
        SealedLine(mine, ENTITY, PERIOD, "ASC606", POSTING),
        SealedLine(another_period, ENTITY, other_period, "ASC606", POSTING),
        SealedLine(another_entity, other_entity, PERIOD, "ASC606", POSTING),
    ]
    run = _RunRow(RUN, ENTITY, PERIOD, "ASC606", "GROSS", 0, 5, None, None, INSTANT, True)
    session = _Pages([(POSTING, 2)], [run], [(RUN, NO_HELD)])
    assert _member(session, lines) == {mine: RUN}
    # what the statement on the runs asks: the page's pairs, and every state but cancelled
    asked = session.statements[1].replace("erev.", "")
    assert "journal_run.state != " in asked
    assert "(journal_run.entity_id, journal_run.period_id) IN " in asked
    assert "cancelled" in session.binds[1]
    pairs = sorted({(line.entity_id, line.period_id) for line in lines}, key=str)
    assert pairs in session.binds[1] and len(pairs) == 3
    # two runs created at two instants: the one statement on the events asks at both
    later = _RunRow(
        TAKING, ENTITY, other_period, "ASC606", "GROSS", 0, 5, None, None, LATER_AT, True
    )
    both = _Pages([(POSTING, 2)], [run, later], [(RUN, NO_HELD), (TAKING, NO_HELD)])
    assert _member(both, lines) == {mine: RUN, another_period: TAKING}
    assert len(both.statements) == 3 and [INSTANT, LATER_AT] in both.binds[2]


def test_every_read_of_the_schema_hands_the_store_and_the_key_ring() -> None:
    """The member's reader of a run's record is handed the file store and the key ring by each
    of the three reads of API-S-SubledgerLine, as the gate hands them (the supervisor's first
    condition): the three functions between a route and the record take both without a default,
    so a read that left them out — and would read a run of before the recorded ids as
    unreadable where the gate reads its file — fails the type check and its first call.
    ``line_outs`` takes the page's runs without a default either: no read builds the schema
    without the member."""
    for reader in (
        completeness.journalising_runs,
        subledger.journal_runs_of,
        contract_queries.subledger_items,
    ):
        parameters = inspect.signature(reader).parameters
        assert {parameters[name].default for name in ("files", "keyring")} == {
            inspect.Parameter.empty
        }, reader.__name__
    runs = inspect.signature(subledger.line_outs).parameters["journal_runs"]
    assert runs.default is inspect.Parameter.empty
    for route, hands in (
        (subledger_api.subledger_lines_list, 1),
        (contracts_api.contract_subledger_lines_list, 1),
        (journal_runs_api.journal_lines_drill, 2),  # the drill's ids, then the member
    ):
        handed = inspect.getsource(route).count("files=deps.files, keyring=deps.keyring")
        assert handed == hands, route.__name__


def test_the_rows_state_the_member_and_the_drill() -> None:
    """04 rev 1.288 states the member and the drill's source word for word; PRD ERR-101's copy
    is the sentence the drill answers; fragment 14 rev 1.77 names the witnesses."""
    model = (DOCS / "04-DATA_MODEL.md").read_text(encoding="utf-8")
    for sentence in (
        "the journal run that journalises the line — in a posting book at most one, the one "
        "`JE_COMPLETE` counts for it",
        "It is the run that took the line over — its `CALCULATE` event names the line — or else "
        "the run of the line's entity and period that is not cancelled, whose range holds the "
        "line's seal",
        "A LEGACY line takes no run of its own book",
        "the member then names the primary book's run — the LEGACY book follows the primary "
        "book — and another posting book's run only where no run of the primary book "
        "journalises the line",
        "three statements a page, whatever its number of lines, and leave the page's own "
        "statement as it is",
        "asked at the instants the runs were created at",
        "is asked for again without that bound, by a fourth statement, so the record is the "
        "one the gate reads",
        "WHICH those are is read from the run's own record",
        "the drill of its journal lines answers 409 `invalid-transition`, `rule_id` "
        "`RUN_RECORD_UNREADABLE`",
        "hashes to `journal_line.source_grouping_sha256` at the grain the journal line was "
        "summarised at — the run's, or `CONTRACT_ACCOUNT_DIMENSIONS` for a line of an entry "
        "that was larger than its ledger's chunk and split by contract",
    ):
        assert model.count(sentence) == 1, sentence
    copy = queries.RECORD_UNREADABLE.format(run="<run>")
    assert copy == (
        "Journal run <run> cannot be traced to its source lines: the record of the lines it "
        "left out cannot be read."
    )
    assert f'"{copy}" (PRD ERR-101)' in model
    [row] = [
        line
        for line in (DOCS / "02-PRD.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("| ERR-101 |")
    ]
    assert f'`errors[].rule_id = "{queries.RULE_RECORD_UNREADABLE}"` | 409 |' in row
    assert row.endswith(f'`detail` and `errors[].message` "{copy}" |')
    fragment = (DOCS / "build-spec/14-close-reports-ai-demo-release.md").read_text(encoding="utf-8")
    journals = "backend/tests/domain/journals"
    for witness in (
        f"`{journals}/test_drill_record.py::test_the_drill_leaves_out_what_the_run_left_out_"
        "though_the_hold_was_released_at_its_instant`",
        "`::test_the_drill_of_a_run_whose_record_cannot_be_read_is_refused` — that file gone",
        f"`{journals}/test_line_journal_run.py::test_a_line_names_the_run_that_journalises_it`",
        "`::test_a_legacy_line_of_two_posting_books_names_the_primary_books_run` — an entity",
        "`::test_a_line_names_a_run_of_its_own_entity_and_period_whatever_the_runs_state` — a",
        "`::test_the_member_costs_the_same_for_one_line_and_for_a_page` — the statements",
        f"`{journals}/test_chunking.py::test_the_drill_of_a_line_of_a_split_entry_names_its_"
        "source_lines`",
        "`backend/tests/unit/journals/test_chunking_rules.py::test_s14_r21_a_line_of_a_split_"
        "entry_is_traced_at_the_grain_it_was_summarised_at`",
        "`::test_a_reader_of_every_page_asks_the_events_at_the_instants_of_its_runs`",
        "`::test_a_legacy_line_of_two_posting_books_names_the_first_run_asked`",
        "`::test_the_member_asks_the_runs_of_the_primary_book_first_from_three_statements`",
        "`::test_every_read_of_the_schema_hands_the_store_and_the_key_ring`",
    ):
        assert fragment.count(witness) == 1, witness
    # every rule of this module is named there, and no name of a rule that is gone
    rules = sorted(name for name in globals() if name.startswith("test_"))
    assert all(fragment.count(f"::{name}`") == 1 for name in rules), rules
    assert "took_it_over_before_the_run_of_its_range" not in fragment
