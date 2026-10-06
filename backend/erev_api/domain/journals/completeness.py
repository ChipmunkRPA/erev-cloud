"""CLO-10 completeness assertions (03 REQ-JE-005; BUILD_SPEC CLO-10; 04 T-CLS-02 ``JE_COMPLETE``;
ENGINE_SPEC_B §15.2.1 recognised activity, S14-R-16, S14-R-17, S14-R-18, S14-R-23; F-CLO record
§25.18).

Before a lock: no schedule line with non-zero period activity lacks a journal line; journal totals
by account and entity equal the period's journalised activity; JE sequences have no gaps.
``assess`` is the pure rule over the period's sealed activity lines (each with its book, the chain
sequence it was sealed at, the run MODES whose non-cancelled runs journalised it and the open
``journal_export`` hold on its contract if any), the journal totals of the period's non-cancelled
runs by mode and account, and each run's entry sequences — plus the coverage boundary
(``covered_to``: the highest primary ``to_chain_seq``; DB-16 keeps the runs of one entity, book and
period contiguous from zero whatever their mode, 04 rev 1.106), the number of runs and the runs
whose exclusions could not be verified.
``assert_completeness`` reads the inputs from the database for one (entity, book, period).

Coverage is journalisation bound to what each run actually excluded (Codex production-20260921-0845
§4, 0908 §5, 0920 §2 / §3, 1054 §2, 1317 R5-ORDER-1): a run covers a line when the run's range for
the line's book holds its chain sequence AND the line is not among the lines that run left out as
held — or when the run took the line over (below). The excluded identities are the ones the
generator itself recorded — ``held_subledger_line_ids``
in the run's CALCULATE audit event (an empty list is the explicit zero-held state; D-98 132), or the
hash-bound held detail file the same event names — never a timestamp comparison, so the order of a
hold's release and a run's calculation at one instant is read from the run, not reconstructed. A run
whose exclusions cannot be verified covers nothing and is itself a named finding (fail closed).
``coverage_of`` is that pure rule. The finding unit is the sealed posting — the unit a run covers
(one seal, one chain sequence): every uncovered or held posting counts once and every one of its
lines is named, whether or not the posting's lines net — two uncovered postings of +100 and −100 are
two findings; an uncovered posting whose contract is held now is named as held (the hold named);
releasing the hold does not recover it — only a run that journalises it does.

Taking over (item JRN-HELD-AFTER-EXPORT-1; ENGINE_SPEC_B S14-R-17 rev 1.164; 04 DB-16 and T-CLS-02
rev 1.267): the run that journalises a released line is the key's next run. Beside its range it
summarizes every line that a run of the key which is not cancelled left out as held, that no such
run has taken over since and whose contract is under no open hold now, and it records them by id —
``taken_over_subledger_line_ids`` in its CALCULATE event. ``left_out`` is the pure rule of that
set, ``left_out_of`` reads it for a key; a run covers the lines it took over, wherever their chain
sequence lies. A line is taken over once; the cancel of the taking run gives it back, because a
cancelled run's record counts for nothing. Until that revision a line left out by a run that was
then exported was reached by no run: the period could not be locked. The comparison is
MODE-AWARE (1054 R1): a ``GROSS`` run journalises the primary book's lines in its range; a ``DELTA``
run journalises the primary lines in its range plus the LEGACY book's lines in its delta range with
no negation (S14-R-23), so LEGACY lines join the expected population only when a ``DELTA`` run
exists, and each mode's journal totals are compared with the activity that mode's runs covered. A
group S14-R-18 legitimately drops (transaction and functional nets both zero) is complete without
any journal line. JE numbers are allocated per entity across periods and books, so continuity is
asserted per run (1054 R2). A period without a run fails closed by name.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, and_, func, select, tuple_
from sqlalchemy.orm import Session

from erev_api.db import errors as db_errors
from erev_api.db.tables import (
    audit_event,
    book,
    contract_hold,
    gl_account,
    journal_batch,
    journal_entry,
    journal_line,
    journal_run,
    subledger_line,
    subledger_posting_seal,
)
from erev_api.enums import BookCode, ChecklistStatus, HoldType, JournalRunMode, JournalState
from erev_api.files.store import open_file

if TYPE_CHECKING:
    from datetime import datetime

    from erev_api.auth.keyring import KeyRing
    from erev_api.files.store import FileStore
    from erev_api.uow import UnitOfWork

RUN_NOT_CALCULATED: Final = "Journal run not calculated"
GAP_DETAIL: Final = "JE sequence gap after {seq}"
UNCOVERED_DETAIL: Final = "Account {account}{book}: uncovered {what} (chain {seq}, {amount})"
HELD_DETAIL: Final = "Account {account}{book}: held {what} (chain {seq}, {amount}; hold {hold})"
DIFFERENCE_DETAIL: Final = (
    "Account {account}: {mode} journal {journal} differs from covered activity {activity}"
)
UNVERIFIABLE_DETAIL: Final = "Run {run}: held detail unverifiable"
# The generator's audit facts (``summarise.CALCULATE_ACTION`` / ``OBJECT_TYPE``; pinned equal by the
# unit rules) — the retained link of a run's held identities (D-98 132).
CALCULATE_ACTION: Final = "journal_run.calculate"
RUN_OBJECT_TYPE: Final = "journal_run"
# The member of that event which names the lines a run took over (rev 1.267; the generator writes
# it under this name, ``summarise.calculate``).
TAKEN_OVER: Final = "taken_over_subledger_line_ids"
LEGACY: Final = BookCode.LEGACY.value
GROSS: Final = JournalRunMode.GROSS.value
DELTA: Final = JournalRunMode.DELTA.value
ZERO: Final = Decimal(0)
PostingKey = tuple[str, int]  # (book_code, chain_seq): one sealed posting


@dataclass(frozen=True, slots=True)
class ActivityLine:
    """One sealed T-SL-04 line of the period as the assertion reads it (functional, signed)."""

    subledger_line_id: UUID
    chain_seq: int
    account_code: str
    amount_functional: Decimal
    schedule_line_id: UUID | None
    contract_id: UUID | None
    obligation_id: UUID | None
    book_code: str = BookCode.ASC606.value
    covered_by: frozenset[str] = frozenset()  # run modes whose runs journalised it (docstring)
    hold_id: UUID | None = None  # the open journal_export hold on its contract now

    @property
    def covered(self) -> bool:
        return bool(self.covered_by)

    @property
    def posting(self) -> PostingKey:
        return (self.book_code, self.chain_seq)


@dataclass(frozen=True, slots=True)
class RunCoverage:
    """One non-cancelled run as coverage reads it: its mode, its ranges per book (S14-R-16; the
    delta range is the LEGACY book's, S14-R-23), the line ids it excluded as held — ``None``
    when that identity could not be verified (the run then covers nothing of its range) — and the
    line ids it took over from runs that had left them out (``included``; rev 1.267)."""

    id: UUID
    mode: str
    from_chain_seq: int
    to_chain_seq: int
    delta_from_chain_seq: int | None = None
    delta_to_chain_seq: int | None = None
    excluded: frozenset[UUID] | None = frozenset()
    included: frozenset[UUID] = frozenset()

    def holds(self, line: ActivityLine, primary_book: str) -> bool:
        return self.holds_seal(line.book_code, line.chain_seq, primary_book)

    def holds_seal(self, book_code: str, chain_seq: int, primary_book: str) -> bool:
        """Whether the run's range for a line's book holds the chain sequence the line's posting
        was sealed at; ``primary_book`` is the run's own book."""
        if book_code == LEGACY and primary_book != LEGACY:
            if self.mode != DELTA or self.delta_to_chain_seq is None:
                return False
            low = self.delta_from_chain_seq or 0
            return low < chain_seq <= self.delta_to_chain_seq
        return self.from_chain_seq < chain_seq <= self.to_chain_seq


def summarized(run: RunCoverage, line_id: UUID, *, in_range: bool) -> bool:
    """THE rule of what a run journalises (item SUBLEDGER-LINE-JOURNAL-RUN-1; 04 T-SL-06
    drill-back and API-S-SubledgerLine ``journal_run_id``, rev 1.288) — one rule, read by the
    completeness assertion (``coverage_of``), by the member (``journalising_run``) and by the
    drill of a journal line (``queries.drill_ids``): the run took the line over, or the line
    lies in the run's range for its book (``in_range``) and the run's record of the lines it left
    out as held does not name it. A run whose record cannot be read (``excluded is None``)
    journalises nothing of its range. Never a timestamp: which lines a run left out is what the
    run recorded."""
    return line_id in run.included or (
        run.excluded is not None and in_range and line_id not in run.excluded
    )


@dataclass(frozen=True, slots=True)
class UncoveredLine:
    subledger_line_id: UUID
    chain_seq: int
    account_code: str
    amount_functional: Decimal
    schedule_line_id: UUID | None
    contract_id: UUID | None
    obligation_id: UUID | None
    book_code: str = BookCode.ASC606.value


@dataclass(frozen=True, slots=True)
class HeldLine:
    """An unjournalised line whose contract is under an open ``journal_export`` hold (S14-R-17)."""

    subledger_line_id: UUID
    chain_seq: int
    account_code: str
    amount_functional: Decimal
    schedule_line_id: UUID | None
    contract_id: UUID | None
    obligation_id: UUID | None
    hold_id: UUID
    book_code: str = BookCode.ASC606.value


@dataclass(frozen=True, slots=True)
class AccountDifference:
    account_code: str
    journal_total: Decimal
    activity_total: Decimal
    mode: str = GROSS


@dataclass(frozen=True, slots=True)
class CompletenessResult:
    """The ``JE_COMPLETE`` signal: ``count`` failing items (postings, account differences, gaps,
    unverifiable runs) and their named detail."""

    status: ChecklistStatus
    count: int
    detail: str | None
    covered_to: int = 0
    run_count: int = 0
    modes: tuple[str, ...] = ()
    held: tuple[HeldLine, ...] = ()
    uncovered: tuple[UncoveredLine, ...] = ()
    uncovered_postings: tuple[PostingKey, ...] = ()
    held_postings: tuple[PostingKey, ...] = ()
    differences: tuple[AccountDifference, ...] = ()
    gaps: tuple[int, ...] = field(default_factory=tuple)
    unverifiable_runs: tuple[UUID, ...] = ()


def sequence_gaps(seqs: Iterable[int]) -> tuple[int, ...]:
    """The entry sequence numbers after which the next present number is not the successor; the
    numbering starts wherever the first entry starts and duplicates are not gaps (REQ-JE-005)."""
    ordered = sorted(set(int(seq) for seq in seqs))
    return tuple(a for a, b in zip(ordered, ordered[1:], strict=False) if b != a + 1)


def run_sequence_gaps(runs: Iterable[Iterable[int]]) -> tuple[int, ...]:
    """``sequence_gaps`` per run, united: a run's entries are one consecutive block of the
    entity's JE series (``next_numbers``) — the allocation unit the entity-wide sequence is checked
    against — while other periods and books interleave between runs (1054 R2), so [1] and [3] in two
    runs are not a gap and [1, 2, 4] in one run is."""
    found: set[int] = set()
    for seqs in runs:
        found.update(sequence_gaps(seqs))
    return tuple(sorted(found))


def coverage_of(
    activity: Sequence[ActivityLine], runs: Sequence[RunCoverage], *, primary_book: str
) -> list[ActivityLine]:
    """The pure coverage rule (module docstring): each line with ``covered_by`` = the modes of the
    runs whose range for its book holds its chain sequence and whose recorded exclusions do not
    name it, and of the runs that took it over. A run with unverified exclusions (``excluded is
    None``) covers nothing of its range."""
    return [
        ActivityLine(
            subledger_line_id=line.subledger_line_id,
            chain_seq=line.chain_seq,
            account_code=line.account_code,
            amount_functional=line.amount_functional,
            schedule_line_id=line.schedule_line_id,
            contract_id=line.contract_id,
            obligation_id=line.obligation_id,
            book_code=line.book_code,
            covered_by=frozenset(
                run.mode
                for run in runs
                if summarized(run, line.subledger_line_id, in_range=run.holds(line, primary_book))
            ),
            hold_id=line.hold_id,
        )
        for line in activity
    ]


def _money(value: Decimal) -> str:
    return format(value, "f")


def _what(schedule_line_id: UUID | None, line_id: UUID) -> str:
    return (
        f"schedule line {schedule_line_id}" if schedule_line_id is not None else f"line {line_id}"
    )


def _book(book_code: str, primary: str) -> str:
    return "" if book_code == primary else f" ({book_code})"


def _postings(lines: Iterable[ActivityLine]) -> tuple[PostingKey, ...]:
    return tuple(sorted({line.posting for line in lines}, key=lambda key: (key[1], key[0])))


def assess(
    *,
    activity: Sequence[ActivityLine],
    journal_totals: Mapping[str, Mapping[str, Decimal]],
    entry_seqs: Sequence[Sequence[int]],
    covered_to: int,
    run_count: int,
    primary_book: str = BookCode.ASC606.value,
    unverifiable_runs: Sequence[UUID] = (),
) -> CompletenessResult:
    """The pure rule (module docstring). ``journal_totals`` is mode → account → Σ(debit − credit)
    over that mode's non-cancelled runs; ``entry_seqs`` holds each run's ``je_seq`` list;
    ``unverifiable_runs`` names the runs whose exclusions could not be read."""
    if run_count == 0:
        return CompletenessResult(ChecklistStatus.FAILED, 1, RUN_NOT_CALCULATED, covered_to, 0)
    ordered = sorted(activity, key=lambda item: (item.chain_seq, str(item.subledger_line_id)))
    held_lines = [line for line in ordered if not line.covered and line.hold_id is not None]
    uncovered_lines = [line for line in ordered if not line.covered and line.hold_id is None]
    held = tuple(
        HeldLine(
            subledger_line_id=line.subledger_line_id,
            chain_seq=line.chain_seq,
            account_code=line.account_code,
            amount_functional=line.amount_functional,
            schedule_line_id=line.schedule_line_id,
            contract_id=line.contract_id,
            obligation_id=line.obligation_id,
            hold_id=line.hold_id,
            book_code=line.book_code,
        )
        for line in held_lines
        if line.hold_id is not None
    )
    uncovered = tuple(
        UncoveredLine(
            subledger_line_id=line.subledger_line_id,
            chain_seq=line.chain_seq,
            account_code=line.account_code,
            amount_functional=line.amount_functional,
            schedule_line_id=line.schedule_line_id,
            contract_id=line.contract_id,
            obligation_id=line.obligation_id,
            book_code=line.book_code,
        )
        for line in uncovered_lines
    )
    uncovered_postings = _postings(uncovered_lines)
    held_postings = _postings(held_lines)
    modes = sorted(set(journal_totals) | {mode for line in ordered for mode in line.covered_by})
    differences: list[AccountDifference] = []
    for mode in modes:
        covered_totals: dict[str, Decimal] = {}
        for line in ordered:
            if mode in line.covered_by:
                covered_totals[line.account_code] = (
                    covered_totals.get(line.account_code, ZERO) + line.amount_functional
                )
        totals = journal_totals.get(mode, {})
        for account in sorted(set(covered_totals) | set(totals)):
            journal_total = totals.get(account, ZERO)
            activity_total = covered_totals.get(account, ZERO)
            if journal_total != activity_total:
                differences.append(
                    AccountDifference(
                        account_code=account,
                        journal_total=journal_total,
                        activity_total=activity_total,
                        mode=mode,
                    )
                )
    gaps = run_sequence_gaps(entry_seqs)
    unverifiable = tuple(sorted(unverifiable_runs, key=str))
    count = (
        len(uncovered_postings)
        + len(held_postings)
        + len(differences)
        + len(gaps)
        + len(unverifiable)
    )
    parts = [
        UNCOVERED_DETAIL.format(
            account=line.account_code,
            book=_book(line.book_code, primary_book),
            what=_what(line.schedule_line_id, line.subledger_line_id),
            seq=line.chain_seq,
            amount=_money(line.amount_functional),
        )
        for line in uncovered
    ]
    parts += [
        HELD_DETAIL.format(
            account=line.account_code,
            book=_book(line.book_code, primary_book),
            what=_what(line.schedule_line_id, line.subledger_line_id),
            seq=line.chain_seq,
            amount=_money(line.amount_functional),
            hold=line.hold_id,
        )
        for line in held
    ]
    parts += [
        DIFFERENCE_DETAIL.format(
            account=item.account_code,
            mode=item.mode,
            journal=_money(item.journal_total),
            activity=_money(item.activity_total),
        )
        for item in differences
    ]
    parts += [GAP_DETAIL.format(seq=seq) for seq in gaps]
    parts += [UNVERIFIABLE_DETAIL.format(run=run) for run in unverifiable]
    status = ChecklistStatus.PASSED if count == 0 else ChecklistStatus.FAILED
    return CompletenessResult(
        status=status,
        count=count,
        detail="; ".join(parts) if parts else None,
        covered_to=covered_to,
        run_count=run_count,
        modes=tuple(modes),
        held=held,
        uncovered=uncovered,
        uncovered_postings=uncovered_postings,
        held_postings=held_postings,
        differences=tuple(differences),
        gaps=gaps,
        unverifiable_runs=unverifiable,
    )


# --- database ------------------------------------------------------------------------------------


def _run_scope(entity_id: UUID, book_code: str, period_id: UUID) -> list[ColumnElement[bool]]:
    return [
        journal_run.c.entity_id == entity_id,
        journal_run.c.book_code == book_code,
        journal_run.c.period_id == period_id,
        journal_run.c.state != JournalState.CANCELLED.value,
    ]


def activity_lines(
    session: Session, *, entity_id: UUID, book_code: str, period_id: UUID, legacy: bool = False
) -> list[ActivityLine]:
    """Every sealed line of (entity, book, period) — and of the LEGACY book when ``legacy`` (a
    ``DELTA`` run exists) — with its seal's chain sequence, account code and the open
    ``journal_export`` hold on its contract now, if any; coverage is added by ``coverage_of``."""
    tenant_id = subledger_line.c.tenant_id
    open_hold = (
        select(contract_hold.c.id)
        .where(
            contract_hold.c.tenant_id == tenant_id,
            contract_hold.c.contract_id == subledger_line.c.contract_id,
            contract_hold.c.hold_type == HoldType.JOURNAL_EXPORT.value,
            contract_hold.c.released_at.is_(None),
        )
        .order_by(contract_hold.c.applied_at)
        .limit(1)
        .scalar_subquery()
    )
    books = [book_code, LEGACY] if legacy and book_code != LEGACY else [book_code]
    rows = session.execute(
        select(
            subledger_line.c.id,
            subledger_posting_seal.c.chain_seq,
            gl_account.c.code,
            subledger_line.c.amount_functional,
            subledger_line.c.schedule_line_id,
            subledger_line.c.contract_id,
            subledger_line.c.obligation_id,
            subledger_line.c.book_code,
            open_hold.label("hold_id"),
        )
        .select_from(
            subledger_line.join(
                subledger_posting_seal,
                and_(
                    subledger_posting_seal.c.tenant_id == tenant_id,
                    subledger_posting_seal.c.subledger_posting_id
                    == subledger_line.c.subledger_posting_id,
                ),
            ).join(
                gl_account,
                and_(
                    gl_account.c.tenant_id == tenant_id,
                    gl_account.c.id == subledger_line.c.gl_account_id,
                ),
            )
        )
        .where(
            subledger_line.c.entity_id == entity_id,
            subledger_line.c.book_code.in_(books),
            subledger_line.c.period_id == period_id,
        )
        .order_by(subledger_posting_seal.c.chain_seq, subledger_line.c.id)
    ).all()
    return [
        ActivityLine(
            subledger_line_id=UUID(str(row[0])),
            chain_seq=int(row[1]),
            account_code=str(row[2]),
            amount_functional=Decimal(row[3]),
            schedule_line_id=None if row[4] is None else UUID(str(row[4])),
            contract_id=None if row[5] is None else UUID(str(row[5])),
            obligation_id=None if row[6] is None else UUID(str(row[6])),
            book_code=str(row[7]),
            hold_id=None if row[8] is None else UUID(str(row[8])),
        )
        for row in rows
    ]


def held_ids_from_document(content: bytes, expected_sha256: str) -> frozenset[UUID] | None:
    """The pure reader of a run's held detail document (Codex production-20260921-1535): the
    bytes must hash as the CALCULATE audit recorded and parse as a JSON object whose ``held``
    member is a list of objects carrying a UUID ``subledger_line_id``. ``{"held": []}`` is the
    explicit zero-held state → an EMPTY exclusion set; a hash mismatch, malformed JSON, a
    non-object document, a missing or non-list ``held`` member, or an item without a UUID id →
    ``None`` (the run is unverifiable — it covers nothing and is a named finding; never a silent
    empty set)."""
    if hashlib.sha256(content).hexdigest() != str(expected_sha256):
        return None
    try:
        document = json.loads(content)
    except ValueError:
        return None
    if not isinstance(document, dict) or not isinstance(document.get("held"), list):
        return None
    ids: set[UUID] = set()
    for item in document["held"]:
        if not isinstance(item, dict) or "subledger_line_id" not in item:
            return None
        try:
            ids.add(UUID(str(item["subledger_line_id"])))
        except ValueError:
            return None
    return frozenset(ids)


def _held_ids_from_file(
    session: Session, after: Mapping[str, Any], *, files: FileStore, keyring: KeyRing
) -> frozenset[UUID] | None:
    """The held line ids of a run's hash-bound held detail file: read inside one guard, then
    ``held_ids_from_document``; ``None`` when the file is missing, shredded, unreadable,
    mis-hashed or malformed (the run is then unverifiable).

    "Unverifiable" is a statement about the file, so the guard does not answer it for the
    database (item JRN-COMPLETENESS-TRANSIENT-1; dev-guide DG-CMD-09 rev 1.234): a transient
    database error, an unavailable server and a pool timeout are re-raised, by the table the
    computation reads (``db.errors``) — the caller's transaction ends and its command answers as
    for any such error. The read runs in a savepoint: a database error that is not re-raised
    is rolled back to it and leaves the transaction usable for the statements of the assertion
    that follow. Until rev 1.234 the guard caught everything: a lock timeout or a lost
    connection read as "unverifiable", and the statements after it met an aborted
    transaction."""
    file_id, expected = after.get("held_detail_file_id"), after.get("held_detail_sha256")
    if not file_id or not expected:
        return None
    try:
        with session.begin_nested():
            _, stream = open_file(session, UUID(str(file_id)), files=files, keyring=keyring)
            content = stream.read()
    except Exception as error:
        if not_about_the_file(error):
            raise
        return None  # a failure of the file is "unverifiable", never coverage
    return held_ids_from_document(content, str(expected))


def not_about_the_file(error: BaseException) -> bool:
    """Whether a failure to read a held detail file says nothing about the file: the server
    was unavailable, the pool gave no connection, or the database error is transient
    (``db.errors.is_transient``). Such a failure is re-raised; every other one — no row, a
    shredded or missing object, a key that does not open it, a deterministic database error — is
    what "unverifiable" means."""
    if db_errors.server_unavailable_in(error) or db_errors.pool_timeout_in(error):
        return True
    raised = db_errors.database_error_in(error)
    return raised is not None and db_errors.is_transient(raised)


@dataclass(frozen=True, slots=True)
class RunRecord:
    """What a run's CALCULATE audit event says of the lines outside its ordinary coverage: those
    it left out as held (``None`` when that cannot be verified) and those it took over."""

    excluded: frozenset[UUID] | None = None
    taken_over: frozenset[UUID] = frozenset()


def left_out(records: Mapping[UUID, RunRecord]) -> dict[UUID, UUID]:
    """The pure rule of what the key's next run may take over (module docstring): line id → the
    run that left it out, over the records of the key's runs that are not cancelled — every line
    a run left out as held that no run has taken over. A run whose exclusions cannot be verified
    names no line here (it covers nothing and is a finding of its own). Whether a line's contract
    is still under a hold is the calculation's question, asked at its instant."""
    taken = {line for record in records.values() for line in record.taken_over}
    return {
        line: run_id
        for run_id, record in sorted(records.items(), key=lambda item: str(item[0]))
        for line in sorted(record.excluded or (), key=str)
        if line not in taken
    }


def run_records(
    session: Session,
    run_ids: Sequence[UUID],
    *,
    files: FileStore | None = None,
    keyring: KeyRing | None = None,
    calculated_at: Mapping[UUID, datetime] | None = None,
) -> dict[UUID, RunRecord]:
    """``RunRecord`` per run, by ONE read of the runs' CALCULATE events: the lines each left
    out as held (``excluded_of``) and the ``taken_over_subledger_line_ids`` of the same event —
    an event without that member, written before rev 1.267, took nothing over. A run without an
    event has no record: it left out nothing that can be verified and took nothing over.

    ``calculated_at`` — run id → the run's ``created_at`` — lets the read ask the audit log at
    those instants alone (``_calculate_events``): a reader that asks on every page of a list
    hands it, so that the read plans the partitions of the runs' months and not every month of
    the log. The record it answers is the same with it and without it."""
    events = _calculate_events(session, run_ids, calculated_at)
    records: dict[UUID, RunRecord] = {}
    for run_id in (UUID(str(value)) for value in run_ids):
        after = events.get(run_id)
        if after is None:
            records[run_id] = RunRecord()
            continue
        taken = after.get(TAKEN_OVER) or ()
        records[run_id] = RunRecord(
            excluded=excluded_of(session, after, files=files, keyring=keyring),
            taken_over=frozenset(UUID(str(value)) for value in taken),
        )
    return records


def _calculate_events(
    session: Session,
    run_ids: Sequence[UUID],
    calculated_at: Mapping[UUID, datetime] | None = None,
) -> dict[UUID, Mapping[str, Any]]:
    """The ``after`` of each run's CALCULATE audit event (one statement; none for no run).

    With ``calculated_at`` the statement asks the events at the instants the runs were created
    at. A calculation writes its run and its CALCULATE event in one unit of work, at one instant
    (dev-guide DG-KRN-AUD-01: ``occurred_at`` is the unit of work's ``now``, and so is the run's
    ``created_at``), and ``audit_event`` is partitioned by ``occurred_at``: bounded so, the read
    plans and locks the partitions of the runs' months, where without the bound it plans every
    month of the log. A run whose event is not found at its instant — the product writes none
    such — is asked for again without the bound (a second statement), so every reader of a
    run's record reads the same event whether it hands the instants or not."""
    if not run_ids:
        return {}

    def read(ids: Sequence[UUID], *bound: ColumnElement[bool]) -> dict[UUID, Mapping[str, Any]]:
        rows = session.execute(
            select(audit_event.c.object_id, audit_event.c.after).where(
                audit_event.c.action == CALCULATE_ACTION,
                audit_event.c.object_type == RUN_OBJECT_TYPE,
                audit_event.c.object_id.in_(list(ids)),
                *bound,
            )
        ).all()
        return {UUID(str(object_id)): (after or {}) for object_id, after in rows}

    if calculated_at is None:
        return read(run_ids)
    wanted = [UUID(str(value)) for value in run_ids]
    instants = sorted({calculated_at[run_id] for run_id in wanted if run_id in calculated_at})
    found = read(wanted, audit_event.c.occurred_at.in_(instants)) if instants else {}
    missing = [run_id for run_id in wanted if run_id not in found]
    if missing:
        found.update(read(missing))
    return found


def excluded_of(
    session: Session,
    after: Mapping[str, Any],
    *,
    files: FileStore | None = None,
    keyring: KeyRing | None = None,
) -> frozenset[UUID] | None:
    """The line ids a run left out as held, from its CALCULATE event: the ids the event names
    (``held_subledger_line_ids``; an empty list is the explicit zero-held state) or, for an
    event that predates that member, none when it counts no held line, else the ids of the held
    detail file it names (hash-verified) — read only when the caller hands the file store and
    the key ring. ``None`` when nothing verifies: the run then journalises nothing (fail
    closed). Every reader of a run's record hands both, as the gate does, so that a run of
    before the ids reads the same for the gate, the member and the drill (rev 1.288)."""
    ids = after.get("held_subledger_line_ids")
    if ids is not None:
        return frozenset(UUID(str(value)) for value in ids)
    counts = after.get("counts") or {}
    if counts.get("held_lines") == 0:
        return frozenset()
    if files is not None and keyring is not None:
        return _held_ids_from_file(session, after, files=files, keyring=keyring)
    return None


def left_out_of(
    session: Session,
    *,
    entity_id: UUID,
    book_code: str,
    period_id: UUID,
    files: FileStore | None = None,
    keyring: KeyRing | None = None,
) -> dict[UUID, UUID]:
    """``left_out`` over the runs of the entity, book and period that are not cancelled. The
    calculation reads it under the key's coverage lock, which a cancel holds too, so two runs
    never take one line."""
    run_ids = [
        UUID(str(value))
        for value in session.execute(
            select(journal_run.c.id).where(*_run_scope(entity_id, book_code, period_id))
        ).scalars()
    ]
    return left_out(run_records(session, run_ids, files=files, keyring=keyring))


@dataclass(frozen=True, slots=True)
class SealedLine:
    """A subledger line as ``journalising_runs`` reads it: where it lies and its posting."""

    id: UUID
    entity_id: UUID
    period_id: UUID
    book_code: str
    subledger_posting_id: UUID


def journalising_run(
    line_id: UUID,
    book_code: str,
    chain_seq: int | None,
    runs: Sequence[tuple[str, RunCoverage]],
) -> UUID | None:
    """The run that journalises a line — 04 API-S-SubledgerLine ``journal_run_id`` (rev 1.288) —
    among ``runs``: the runs of the line's entity and period that are not cancelled, each with
    its own book, in the order ``journalising_runs`` puts them (the primary book's first). A run
    journalises the line when it took the line over, or when its range holds the line's seal —
    the range of the line's own book, or for a LEGACY line the delta range of a ``DELTA`` run —
    and its record of the lines it left out does not name the line (``summarized``, the rule
    ``JE_COMPLETE`` reads). None when no run does: a line that is not sealed or lies beyond the
    runs; a line a run left out that no run has taken over; a line in the range of a run whose
    record cannot be read.

    In one posting book at most one run journalises a line: the ranges of a key's runs do not
    overlap (04 DB-16) and a line is taken over once (S14-R-17). A LEGACY line has no run of its
    own book (04 "DB-07 and the LEGACY book") and can be journalised in each posting book its
    entity keeps, by a ``DELTA`` run of each: the first of ``runs`` that journalises it is
    named."""
    for run_book, run in runs:
        in_range = (
            chain_seq is not None
            # another book's chain: its sequences are not this run's
            and book_code in (run_book, LEGACY)
            and run.holds_seal(book_code, chain_seq, run_book)
        )
        if summarized(run, line_id, in_range=in_range):
            return run.id
    return None


def _code(value: Any) -> str:
    """The text of an enumerated column, whether the driver hands the member or its value."""
    return str(getattr(value, "value", value))


def journalising_runs(
    session: Session,
    lines: Sequence[SealedLine],
    *,
    files: FileStore | None,
    keyring: KeyRing | None,
) -> dict[UUID, UUID]:
    """Line id → the run that journalises it (``journalising_run``), for the lines of one page
    of a read: three statements whatever the number of lines — the seals of the lines'
    postings, the runs of their entities and periods that are not cancelled, and those runs'
    CALCULATE events (``run_records``) — two when no such run stands, none for no line. The
    page's own statement is not touched. ``files`` and ``keyring`` are handed on to the record's
    reader, as the gate hands them: without them a run of before the recorded ids would read as
    unreadable here while ``JE_COMPLETE`` reads its held detail file. The events are asked at
    the instants the runs were created at (``_calculate_events``): this read runs on every page
    of a list, and the audit log is partitioned by month.

    The runs of a key are asked in one order: the primary book's first — the LEGACY book
    follows the primary book (04 "DB-07 and the LEGACY book") — then by book code, and within a
    book by their ranges. It decides only for a LEGACY line that a ``DELTA`` run of more than
    one posting book journalises; without a primary book the order is the books' codes, which
    puts ASC606 first as ``primary_book`` does."""
    if not lines:
        return {}
    postings = sorted({line.subledger_posting_id for line in lines}, key=str)
    seals = {
        UUID(str(posting_id)): int(chain_seq)
        for posting_id, chain_seq in session.execute(
            select(
                subledger_posting_seal.c.subledger_posting_id, subledger_posting_seal.c.chain_seq
            ).where(subledger_posting_seal.c.subledger_posting_id.in_(postings))
        ).all()
    }
    keys = sorted({(line.entity_id, line.period_id) for line in lines}, key=str)
    primary = select(book.c.code).where(book.c.is_primary.is_(True)).scalar_subquery()
    rows = session.execute(
        select(
            journal_run.c.id,
            journal_run.c.entity_id,
            journal_run.c.period_id,
            journal_run.c.book_code,
            journal_run.c.mode,
            journal_run.c.from_chain_seq,
            journal_run.c.to_chain_seq,
            journal_run.c.delta_from_chain_seq,
            journal_run.c.delta_to_chain_seq,
            journal_run.c.created_at,
            (journal_run.c.book_code == primary).label("of_primary_book"),
        ).where(
            journal_run.c.state != JournalState.CANCELLED.value,
            tuple_(journal_run.c.entity_id, journal_run.c.period_id).in_(keys),
        )
    ).all()
    if not rows:
        return {}
    records = run_records(
        session,
        [UUID(str(row.id)) for row in rows],
        files=files,
        keyring=keyring,
        calculated_at={UUID(str(row.id)): row.created_at for row in rows},
    )
    by_key: dict[tuple[UUID, UUID], list[tuple[str, RunCoverage]]] = {}
    for row in sorted(
        rows,
        key=lambda row: (
            not row.of_primary_book,
            _code(row.book_code),
            int(row.from_chain_seq),
            str(row.id),
        ),
    ):
        run_id = UUID(str(row.id))
        delta_from, delta_to = row.delta_from_chain_seq, row.delta_to_chain_seq
        by_key.setdefault((UUID(str(row.entity_id)), UUID(str(row.period_id))), []).append(
            (
                _code(row.book_code),
                RunCoverage(
                    id=run_id,
                    mode=_code(row.mode),
                    from_chain_seq=int(row.from_chain_seq),
                    to_chain_seq=int(row.to_chain_seq),
                    delta_from_chain_seq=None if delta_from is None else int(delta_from),
                    delta_to_chain_seq=None if delta_to is None else int(delta_to),
                    excluded=records[run_id].excluded,
                    included=records[run_id].taken_over,
                ),
            )
        )
    found: dict[UUID, UUID] = {}
    for line in lines:
        journalised = journalising_run(
            line.id,
            line.book_code,
            seals.get(line.subledger_posting_id),
            by_key.get((line.entity_id, line.period_id), ()),
        )
        if journalised is not None:
            found[line.id] = journalised
    return found


def run_exclusions(
    session: Session,
    run_ids: Sequence[UUID],
    *,
    files: FileStore | None = None,
    keyring: KeyRing | None = None,
) -> dict[UUID, frozenset[UUID] | None]:
    """Per run, the line ids it excluded as held (``excluded_of`` over its CALCULATE audit
    event); ``None`` when that does not verify, and for a run without an event — the run then
    covers nothing (fail closed)."""
    return {
        run_id: record.excluded
        for run_id, record in run_records(session, run_ids, files=files, keyring=keyring).items()
    }


def completeness_of(
    session: Session,
    *,
    entity_id: UUID,
    book_code: str,
    period_id: UUID,
    files: FileStore | None = None,
    keyring: KeyRing | None = None,
) -> CompletenessResult:
    """``assess`` over the database: the non-cancelled runs of the scope (their modes, ranges and
    recorded exclusions), each mode's journal totals by account (debit less credit, functional),
    each run's entry sequences, and the period's sealed activity — the LEGACY book's too when a
    ``DELTA`` run exists (S14-R-23). ``files`` / ``keyring`` let the held detail file stand in for
    an audit event without ``held_subledger_line_ids``."""
    rows = session.execute(
        select(
            journal_run.c.id,
            journal_run.c.mode,
            journal_run.c.from_chain_seq,
            journal_run.c.to_chain_seq,
            journal_run.c.delta_from_chain_seq,
            journal_run.c.delta_to_chain_seq,
        ).where(*_run_scope(entity_id, book_code, period_id))
    ).all()
    run_ids = [UUID(str(row[0])) for row in rows]
    records = run_records(session, run_ids, files=files, keyring=keyring)
    runs = [
        RunCoverage(
            id=UUID(str(row[0])),
            mode=str(row[1]),
            from_chain_seq=int(row[2]),
            to_chain_seq=int(row[3]),
            delta_from_chain_seq=None if row[4] is None else int(row[4]),
            delta_to_chain_seq=None if row[5] is None else int(row[5]),
            excluded=records[UUID(str(row[0]))].excluded,
            included=records[UUID(str(row[0]))].taken_over,
        )
        for row in rows
    ]
    covered_to = max((run.to_chain_seq for run in runs), default=0)
    legacy = any(run.mode == DELTA for run in runs)
    journal_totals: dict[str, dict[str, Decimal]] = {}
    entry_seqs: dict[UUID, list[int]] = {run.id: [] for run in runs}
    if run_ids:
        batches_of_runs = journal_batch.join(
            journal_run,
            and_(
                journal_run.c.tenant_id == journal_batch.c.tenant_id,
                journal_run.c.id == journal_batch.c.journal_run_id,
            ),
        )
        for mode, code, total in session.execute(
            select(
                journal_run.c.mode,
                journal_line.c.gl_account_code,
                func.sum(journal_line.c.debit_functional - journal_line.c.credit_functional),
            )
            .select_from(
                journal_line.join(
                    batches_of_runs,
                    and_(
                        journal_batch.c.tenant_id == journal_line.c.tenant_id,
                        journal_batch.c.id == journal_line.c.journal_batch_id,
                    ),
                )
            )
            .where(journal_batch.c.journal_run_id.in_(run_ids))
            .group_by(journal_run.c.mode, journal_line.c.gl_account_code)
        ).all():
            journal_totals.setdefault(str(mode), {})[str(code)] = Decimal(total or 0)
        for run_id, seq in session.execute(
            select(journal_batch.c.journal_run_id, journal_entry.c.je_seq)
            .select_from(
                journal_entry.join(
                    journal_batch,
                    and_(
                        journal_batch.c.tenant_id == journal_entry.c.tenant_id,
                        journal_batch.c.id == journal_entry.c.journal_batch_id,
                    ),
                )
            )
            .where(journal_batch.c.journal_run_id.in_(run_ids))
        ).all():
            entry_seqs.setdefault(UUID(str(run_id)), []).append(int(seq))
    lines = activity_lines(
        session, entity_id=entity_id, book_code=book_code, period_id=period_id, legacy=legacy
    )
    return assess(
        activity=coverage_of(lines, runs, primary_book=book_code),
        journal_totals=journal_totals,
        entry_seqs=list(entry_seqs.values()),
        covered_to=covered_to,
        run_count=len(run_ids),
        primary_book=book_code,
        unverifiable_runs=[run.id for run in runs if run.excluded is None],
    )


def assert_completeness(
    uow: UnitOfWork, entity_id: UUID, book_code: str, period_id: UUID
) -> CompletenessResult:
    """BUILD_SPEC CLO-10 entry point over a unit of work (its file store and key ring read a run's
    held detail file when the audit event carries no ``held_subledger_line_ids``)."""
    return completeness_of(
        uow.session,
        entity_id=entity_id,
        book_code=book_code,
        period_id=period_id,
        files=uow.files,
        keyring=uow.keyring,
    )
