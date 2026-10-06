"""RPT-15 ``je_population`` Journal entry population (SCREENS_B §5.6.3 RPT-15; ENGINE_SPEC_B
§15.2.7 ``JE_POPULATION``, S15-R-18a, S15-R-18b; 04 T-CLS-05, E-64; 03 REQ-JE-018, REQ-PLT-030;
D-98 candidates 85, 96; BUILD_SPEC RPS-5).

One row per journal line of the selected journal runs — ``row_key`` ``line:<je no>:<line no>``,
ordered by entity, period, ``je_no``, ``line_no`` — with the frozen-dataset column shape of
S15-R-18a: the key code columns first (``entity_code``, ``book``, ``je_no``, ``line_no``; F-CLO's
KeySpec names, D-98 85), then the code and measure columns, and the display attributes last
(``description``, ``created_by``, ``approved_by``). The four money columns are typed Money
(``{"amount", "currency"}`` at the currency's minor unit; ``tie_outs.money``): the transaction
amounts in the line's transaction currency, the functional amounts in its functional currency
(Codex C6-RPT-R1). ``dimensions`` renders the stored ``journal_line.dimensions`` mapping as stable
``<dimension>:<member>`` pairs in dimension order (C6-RPT-R2). Control totals: ``row_count``,
``entry_count`` (distinct entries), and per currency ``debit_txn_total`` / ``credit_txn_total``
(transaction) and ``debit_functional_total`` / ``credit_functional_total`` (functional). Tie-out
``TO_JE_POPULATION_EQ_RUNS``: Σ ``debit_functional`` of the population per functional currency
equals Σ ``journal_run.total_debit_functional`` of the runs it draws on (every entry balances, so
the debit side carries the comparison).

Sources (S15-R-18b; REQ-PLT-030; C6-RPT-R4; D-98 102 Q3 and Q5). The population is the journal
lines created by the run's ``known_at`` — under ``DATASET_FREEZE`` the freeze instant, so the
close's own journal runs are part of the frozen dataset — and every mutable value is
reconstructed as of ``known_at`` (``state_as_of``): a run whose last mutation is at or before the
cutoff reports its stored state; a run mutated after the cutoff reports its latest transition at
or before the cutoff across every cycle of its life — the run's FULL SOP-7 transition history
(``_transitions``: every audit record shape that changes a run's state — ``journal_run`` with
``after.state`` for approve / cancel, and the batch export roll-up ``journal_batch`` with
``after.run_state`` mapped to the run through its batch — read for every run in the population
regardless of its current state and ordered by (``occurred_at``, audit ``chain_seq``): the
chain's durable sequence breaks equal-time ties, never the state's spelling; D-98 102a, 102c)
together with the stored timestamps, which carry no chain position (a stored timestamp the chain
also recorded at the same instant is the same transition; one the chain did not record sorts
before the chain's records of that instant, and stored-only ties resolve to the later E-34 stage
— a fallback that arises only for transitions the writer does not audit: ``export.py`` defers the
``failed`` batch state and ``EXPORT_FAILED`` to CLO-14, so the retry writer / reader integration
is unproved without a database; the helper-supplied ``Transition`` tests are not end-to-end
acceptance); the ``failed`` transition (no timestamp) exists only through its audit event, never
the current time, and a run currently failed whose failure has neither is unknown as of the
cutoff and refused by name (``JOURNAL_RUN_STATE_UNKNOWN_AS_OF``). Its
approver is the latest ``APPROVE`` /
``AUTO_APPROVE`` decision at or before the cutoff, ``acknowledged_at`` and ``gl_document_id`` come
from acknowledgements received by the cutoff, and a run cancelled after the cutoff stays in the
population (``include_cancelled`` governs runs cancelled by the cutoff). A ``period_lock_id``
source reads the lock snapshot (S15-R-19); until the framework's snapshot branch lands (lane
F-CLO, CLO-8) it is refused by name (``refuse_locked_source``) rather than served from current
tables under an "as locked" label.

``rows_from``, ``control_totals``, ``tie_out``, ``dimension_pairs`` and ``state_as_of`` are pure
over flat records so the shape and the as-of rules are CPU-testable; ``build`` reads the records
through the unit of work. [J] ``approved_by`` / ``approved_at`` come from the run's approval request
(its latest approving decision by the cutoff). ``created_by`` names the run's preparer (SCREENS_B
RPT-15 rev 1.25; the definition's "with preparer, approver and UTC timestamps"): the principal
that requested the run's calculation — 04 T-PLT-27 ``job.created_by`` of the run's job, the
runner BR-JE-01 bars from approving it — because the calculation job writes every entry as the
system principal; an entry of a run no principal requested keeps the entry's own creator.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Final, NamedTuple
from uuid import UUID

from sqlalchemy import and_, select

from erev_api.db.tables import (
    api_client,
    approval_decision,
    audit_event,
    contract,
    gl_account,
    job,
    journal_batch,
    journal_entry,
    journal_line,
    journal_run,
    legal_entity,
    obligation,
    period,
    posting_ack,
)
from erev_api.domain.platform import approval_queries
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.enums import ApprovalDecisionKind, JournalState, PrincipalKind
from erev_api.problems import Problem, ProblemError
from erev_api.uow import UnitOfWork

CODE: Final = "je_population"
TIE_OUT: Final = "TO_JE_POPULATION_EQ_RUNS"
STATE_UNKNOWN_AS_OF: Final = "JOURNAL_RUN_STATE_UNKNOWN_AS_OF"
JOURNAL_RUN_OBJECT: Final = "journal_run"  # SOP-7 audit object of approve / cancel (after.state)
JOURNAL_BATCH_OBJECT: Final = "journal_batch"  # the export roll-up (after.run_state) per batch
# E-34 literals are lower case.
DRAFT: Final = JournalState.DRAFT.value
APPROVED: Final = JournalState.APPROVED.value
EXPORTED: Final = JournalState.EXPORTED.value
ACKNOWLEDGED: Final = JournalState.ACKNOWLEDGED.value
FAILED: Final = JournalState.FAILED.value
CANCELLED: Final = JournalState.CANCELLED.value
# Transition -> the record member carrying its stored time (S15-R-18b Q3); ``failed`` has none and
# exists only in the audit history (D-98 102a).
TRANSITION_TIMES: Final = (
    (APPROVED, "run_approved_at"),
    (EXPORTED, "run_exported_at"),
    (ACKNOWLEDGED, "run_acknowledged_at"),
    (CANCELLED, "run_cancelled_at"),
)
# E-34 lifecycle order: the tie-break of stored-only transitions at one instant (D-98 102c) — an
# explicit stage order, never the spelling; audit records never need it (chain_seq is unique).
LIFECYCLE_RANK: Final = {
    DRAFT: 0,
    APPROVED: 1,
    EXPORTED: 2,
    FAILED: 3,
    ACKNOWLEDGED: 4,
    CANCELLED: 5,
}
NO_SEQ: Final = -1  # a stored timestamp has no chain position: before the chain's records at T


class Transition(NamedTuple):
    """One audited state transition of a journal run: its occurrence time, the audit chain's
    durable sequence (``audit_event.chain_seq``; None only for a stored timestamp the chain did
    not record) and the state it entered."""

    at: datetime
    seq: int | None
    state: str


APPROVED_DECISIONS: Final = (
    ApprovalDecisionKind.APPROVE.value,
    ApprovalDecisionKind.AUTO_APPROVE.value,
)
# S15-R-18a: the row key as code columns first (F-CLO KeySpec: entity_code, book, je_no, line_no).
KEY_COLUMNS: Final = ("entity_code", "book", "je_no", "line_no")
COLUMNS: Final = (
    Column("entity_code", "Entity", "code"),
    Column("book", "Book", "code"),
    Column("je_no", "Journal entry", "code"),
    Column("line_no", "Line", "integer"),
    Column("period_key", "Period", "code"),
    Column("je_type", "Type", "code"),
    Column("account_code", "Account", "code"),
    Column("account_role", "Account role", "code"),
    Column("dimensions", "Dimensions", "codes"),
    Column("txn_currency", "Currency", "code"),
    Column("debit_txn", "Debit (txn)", "money"),
    Column("credit_txn", "Credit (txn)", "money"),
    Column("functional_currency", "Functional currency", "code"),
    Column("debit_functional", "Debit (functional)", "money"),
    Column("credit_functional", "Credit (functional)", "money"),
    Column("contract_external_id", "Contract", "code"),
    Column("obligation_key", "Obligation", "code"),
    Column("origin_period_key", "Origin period", "code"),
    Column("is_post_close", "Post-close", "boolean"),
    Column("is_manual", "Manual", "boolean"),
    Column("run_no", "Run", "code"),
    Column("run_state", "Run state", "code"),
    Column("batch_external_id", "Batch external id", "code"),
    Column("gl_document_id", "GL document", "code"),
    Column("source_line_count", "Source lines", "integer"),
    Column("created_at", "Created at", "timestamp"),
    Column("approved_at", "Approved at", "timestamp"),
    Column("acknowledged_at", "Posted at", "timestamp"),
    # attributes (display labels; never key)
    Column("description", "Description", "text"),
    Column("created_by", "Created by", "actor"),
    Column("approved_by", "Approved by", "actor"),
)
MANUAL_TYPE: Final = "MANUAL"
API_CLIENT: Final = PrincipalKind.API_CLIENT.value
ZERO: Final = Decimal(0)
LOCKED_SOURCE_PENDING: Final = (
    "Locked-source runs of this report read the lock snapshot (ENGINE_SPEC_B S15-R-19); that "
    "branch is not available yet — run the report as of a time instead (S15-R-18b)."
)


def refuse_locked_source(params: ReportParams) -> None:
    """S15-R-18b / REQ-PLT-030: a ``period_lock_id`` source is refused by name until the framework
    reads lock snapshots (CLO-8); current tables are never served under an "as locked" label."""
    if params.period_lock_id is not None:
        raise tie_outs.invalid("period_lock_id", LOCKED_SOURCE_PENDING)


@dataclass(frozen=True, slots=True)
class AsOfState:
    """The journal run's state, approval and acknowledgement as of a cutoff (S15-R-18b)."""

    run_state: str
    approved_at: datetime | None
    acknowledged_at: datetime | None
    cancelled: bool


def state_as_of(
    record: Mapping[str, Any], known_at: datetime, history: Sequence[Transition] = ()
) -> AsOfState:
    """The run state as of ``known_at`` (S15-R-18b; D-98 102 Q3, 102a) from a record carrying the
    stored ``run_state`` and ``run_no``, the timestamps ``run_updated_at``, ``run_approved_at``,
    ``run_exported_at``, ``run_acknowledged_at``, ``run_cancelled_at`` and
    ``batch_acknowledged_at``, and the run's audited transition ``history`` (the reader's
    ``Transition`` rows across every cycle: approval, failure, retry, success). A run whose last
    mutation is at or before the cutoff reports its stored state; a run mutated after the cutoff
    reports its latest transition at or before the cutoff over the stored timestamps and the
    history, so a later approval, export, acknowledgement, failure or cancellation never appears
    in an earlier report and an earlier eligible failure is never displaced by a later one. A run
    currently ``failed`` with no audited failure at all cannot be placed against the cutoff and is
    refused by name, never dated "now"."""

    def at(name: str) -> datetime | None:
        value = record.get(name)
        return value if value is not None and value <= known_at else None

    updated_at = record.get("run_updated_at")
    if updated_at is not None and updated_at <= known_at:
        state = str(record.get("run_state") or DRAFT)
        return AsOfState(
            run_state=state,
            approved_at=record.get("run_approved_at"),
            acknowledged_at=at("batch_acknowledged_at"),
            cancelled=state == CANCELLED,
        )
    if record.get("run_state") == FAILED and not any(item.state == FAILED for item in history):
        raise state_unknown_as_of(record, known_at)
    audited = [item for item in history if item.at <= known_at]
    recorded = {(item.at, str(item.state)) for item in audited}
    # (occurrence, chain position, E-34 stage): the chain breaks equal-time ties; a stored
    # timestamp the chain also recorded is the same transition; the stage order is the fallback
    # for stored-only ties only (D-98 102c) — the state's spelling never decides.
    ordered: list[tuple[datetime, int, int, str]] = [
        (moment, NO_SEQ, LIFECYCLE_RANK.get(state, 0), state)
        for state, name in TRANSITION_TIMES
        if (moment := at(name)) is not None and (moment, state) not in recorded
    ]
    ordered.extend(
        (
            item.at,
            NO_SEQ if item.seq is None else int(item.seq),
            LIFECYCLE_RANK.get(item.state, 0),
            str(item.state),
        )
        for item in audited
    )
    state = max(ordered, key=lambda item: item[:3])[3] if ordered else DRAFT
    return AsOfState(
        run_state=state,
        approved_at=at("run_approved_at"),
        acknowledged_at=at("batch_acknowledged_at"),
        cancelled=state == CANCELLED,
    )


def state_unknown_as_of(record: Mapping[str, Any], known_at: datetime) -> Problem:
    """The named refusal of S15-R-18b Q3: the run's ``failed`` transition has neither a stored
    timestamp nor an audit event, so its state as of the cutoff is unknown."""
    return Problem(
        "validation-failed",
        "1 journal run cannot be placed against the report cutoff (S15-R-18b).",
        errors=[
            ProblemError(
                field="parameters.known_at",
                rule_id=STATE_UNKNOWN_AS_OF,
                message=(
                    f"journal run {record.get('run_no')} is failed with no stored timestamp and "
                    f"no audit event of the transition; its state as of "
                    f"{known_at.isoformat()} is unknown (S15-R-18b)"
                ),
            )
        ],
    )


def dimension_pairs(value: object) -> tuple[str, ...]:
    """The ``codes`` cell of the stored ``journal_line.dimensions`` mapping:
    ``<dimension>:<member>`` pairs in dimension order (C6-RPT-R2); an empty mapping is an empty
    list. A pre-rendered sequence of pairs (the historical fixture shape) is kept, sorted."""
    if value is None:
        return ()
    if isinstance(value, Mapping):
        return tuple(f"{code}:{member}" for code, member in sorted(value.items(), key=_dimension))
    if isinstance(value, str | bytes) or not isinstance(value, Iterable):
        raise ValueError("dimensions are a mapping or a sequence of rendered pairs (T-SL-09)")
    return tuple(sorted(str(item) for item in value))


def _dimension(item: tuple[object, object]) -> str:
    return str(item[0])


def row_key(je_no: str, line_no: int) -> str:
    return f"line:{je_no}:{line_no}"


def rows_from(records: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """The population rows from flat records (one per journal line), in the RPT-15 order
    (entity, period, je_no, line_no); every column of ``COLUMNS`` is present on every row and the
    money columns are typed Money in the line's transaction / functional currency."""
    rows: list[dict[str, Any]] = []
    for record in records:
        je_no = str(record["je_no"])
        line_no = int(record["line_no"])
        je_type = str(record.get("je_type") or "")
        txn_currency = str(record["txn_currency"]).strip()
        functional_currency = str(record["functional_currency"]).strip()
        row: dict[str, Any] = {
            "row_key": row_key(je_no, line_no),
            "entity_code": str(record["entity_code"]),
            "book": str(record["book"]),
            "je_no": je_no,
            "line_no": line_no,
            "period_key": str(record["period_key"]),
            "je_type": je_type,
            "account_code": str(record.get("account_code") or ""),
            "account_role": str(record.get("account_role") or ""),
            "dimensions": dimension_pairs(record.get("dimensions")),
            "txn_currency": txn_currency,
            "debit_txn": _money(record.get("debit_txn"), txn_currency),
            "credit_txn": _money(record.get("credit_txn"), txn_currency),
            "functional_currency": functional_currency,
            "debit_functional": _money(record.get("debit_functional"), functional_currency),
            "credit_functional": _money(record.get("credit_functional"), functional_currency),
            "contract_external_id": _text(record.get("contract_external_id")),
            "obligation_key": _text(record.get("obligation_key")),
            "origin_period_key": _text(record.get("origin_period_key")),
            "is_post_close": bool(record.get("is_post_close")),
            "is_manual": je_type.upper() == MANUAL_TYPE,
            "run_no": _text(record.get("run_no")),
            "run_state": _text(record.get("run_state")),
            "batch_external_id": _text(record.get("batch_external_id")),
            "gl_document_id": _text(record.get("gl_document_id")),
            "source_line_count": int(record.get("source_line_count") or 0),
            "created_at": record.get("created_at"),
            "approved_at": record.get("approved_at"),
            "acknowledged_at": record.get("acknowledged_at"),
            "description": _text(record.get("description")),
            "created_by": record.get("created_by"),
            "approved_by": record.get("approved_by"),
        }
        rows.append(row)
    rows.sort(key=lambda r: (r["entity_code"], r["period_key"], r["je_no"], r["line_no"]))
    return tuple(rows)


def control_totals(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """``row_count``, ``entry_count`` and the per-currency debit / credit totals of both currencies
    (S15-R-18a; SCREENS_B RPT-15)."""
    debit_txn: dict[str, Decimal] = {}
    credit_txn: dict[str, Decimal] = {}
    debit_functional: dict[str, Decimal] = {}
    credit_functional: dict[str, Decimal] = {}
    entries: set[tuple[str, str, str]] = set()
    for row in rows:
        entries.add((str(row["entity_code"]), str(row["book"]), str(row["je_no"])))
        _accumulate(debit_txn, row["debit_txn"])
        _accumulate(credit_txn, row["credit_txn"])
        _accumulate(debit_functional, row["debit_functional"])
        _accumulate(credit_functional, row["credit_functional"])
    return {
        "row_count": len(rows),
        "entry_count": len(entries),
        "debit_txn_total": tie_outs.by_currency(debit_txn),
        "credit_txn_total": tie_outs.by_currency(credit_txn),
        "debit_functional_total": tie_outs.by_currency(debit_functional),
        "credit_functional_total": tie_outs.by_currency(credit_functional),
    }


def tie_out(rows: Sequence[Mapping[str, Any]], run_debits: Mapping[str, Decimal]) -> dict[str, Any]:
    """``TO_JE_POPULATION_EQ_RUNS``: Σ ``debit_functional`` of the population per functional
    currency (actual) against Σ ``journal_run.total_debit_functional`` of the runs drawn on
    (expected)."""
    actual: dict[str, Decimal] = {}
    for row in rows:
        _accumulate(actual, row["debit_functional"])
    return tie_outs.compared(TIE_OUT, dict(run_debits), actual)


def _money(value: object, currency: str) -> dict[str, str]:
    return tie_outs.money(Decimal(str(value)) if value is not None else ZERO, currency)


def _accumulate(totals: dict[str, Decimal], cell: Mapping[str, str]) -> None:
    tie_outs.add(totals, str(cell["currency"]), Decimal(str(cell["amount"])))


def _text(value: object) -> str | None:
    return None if value is None else str(value)


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    refuse_locked_source(params)
    session = uow.session
    known_at = params.known_at
    book_code = tie_outs.book_of(session, params)
    include_cancelled = bool(params.parameters.get("include_cancelled"))
    found = tie_outs.entities(session, params.entity_ids)
    calendars = tie_outs.calendars(session, found)
    period_ids: list[UUID] = []
    for entity in found:
        for item in tie_outs.range_of(params, calendars[entity.id], entity):
            period_ids.append(item.id)
    records: list[dict[str, Any]] = []
    run_debits: dict[str, Decimal] = {}
    if found and period_ids:
        tenant_id = journal_line.c.tenant_id
        origin = period.alias("origin_period")
        joined = (
            journal_line.join(
                journal_entry,
                and_(
                    journal_entry.c.tenant_id == tenant_id,
                    journal_entry.c.id == journal_line.c.journal_entry_id,
                ),
            )
            .join(
                journal_batch,
                and_(
                    journal_batch.c.tenant_id == tenant_id,
                    journal_batch.c.id == journal_line.c.journal_batch_id,
                ),
            )
            .join(
                journal_run,
                and_(
                    journal_run.c.tenant_id == tenant_id,
                    journal_run.c.id == journal_batch.c.journal_run_id,
                ),
            )
            .join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == tenant_id,
                    legal_entity.c.id == journal_line.c.entity_id,
                ),
            )
            .join(
                period,
                and_(period.c.tenant_id == tenant_id, period.c.id == journal_line.c.period_id),
            )
            .outerjoin(
                origin,
                and_(
                    origin.c.tenant_id == tenant_id, origin.c.id == journal_line.c.origin_period_id
                ),
            )
            .outerjoin(
                gl_account,
                and_(
                    gl_account.c.tenant_id == tenant_id,
                    gl_account.c.id == journal_line.c.gl_account_id,
                ),
            )
            .outerjoin(
                contract,
                and_(
                    contract.c.tenant_id == tenant_id, contract.c.id == journal_line.c.contract_id
                ),
            )
            .outerjoin(
                obligation,
                and_(
                    obligation.c.tenant_id == tenant_id,
                    obligation.c.id == journal_line.c.obligation_id,
                ),
            )
        )
        # S15-R-18b: lines created by the cutoff (under DATASET_FREEZE the freeze instant, so
        # the close's own journal runs are in the population; D-98 102 Q5).
        in_population = journal_line.c.created_at <= known_at
        statement = (
            select(
                legal_entity.c.code.label("entity_code"),
                journal_line.c.book_code.label("book"),
                journal_entry.c.je_no,
                journal_line.c.line_no,
                period.c.period_key,
                journal_entry.c.je_type,
                journal_line.c.gl_account_code.label("account_code"),
                journal_line.c.account_role,
                journal_line.c.dimensions,
                journal_line.c.txn_currency,
                journal_line.c.debit_txn,
                journal_line.c.credit_txn,
                journal_line.c.functional_currency,
                journal_line.c.debit_functional,
                journal_line.c.credit_functional,
                contract.c.external_id.label("contract_external_id"),
                obligation.c.obligation_key,
                origin.c.period_key.label("origin_period_key"),
                journal_entry.c.is_post_close,
                journal_run.c.id.label("run_id"),
                journal_run.c.run_no,
                journal_run.c.state.label("run_state"),
                journal_run.c.updated_at.label("run_updated_at"),
                journal_run.c.approved_at.label("run_approved_at"),
                journal_run.c.exported_at.label("run_exported_at"),
                journal_run.c.acknowledged_at.label("run_acknowledged_at"),
                journal_run.c.cancelled_at.label("run_cancelled_at"),
                journal_run.c.approval_request_id,
                journal_run.c.job_id.label("run_job_id"),
                journal_run.c.functional_currency.label("run_functional_currency"),
                journal_run.c.total_debit_functional.label("run_total_debit_functional"),
                journal_batch.c.id.label("batch_id"),
                journal_batch.c.external_id.label("batch_external_id"),
                journal_batch.c.acknowledged_at.label("batch_acknowledged_at"),
                journal_line.c.source_line_count,
                journal_entry.c.description,
                journal_entry.c.created_at,
                journal_entry.c.created_by,
                journal_entry.c.created_by_kind,
            )
            .select_from(joined)
            .where(
                journal_line.c.book_code == book_code,
                journal_line.c.entity_id.in_([entity.id for entity in found]),
                journal_line.c.period_id.in_(period_ids),
                in_population,
            )
        )
        rows = list(session.execute(statement).mappings())
        batch_ids = sorted({UUID(str(row["batch_id"])) for row in rows}, key=str)
        request_ids = sorted(
            {
                UUID(str(row["approval_request_id"]))
                for row in rows
                if row["approval_request_id"] is not None
            },
            key=str,
        )
        documents = _gl_documents(session, batch_ids, known_at)
        approvals = _approvals(session, request_ids, known_at)
        # D-98 102a / 102c: the full transition history of every run in the population,
        # regardless of its current state, over both audit shapes (run and batch roll-up).
        histories = _transitions(
            session,
            sorted({UUID(str(row["run_id"])) for row in rows}, key=str),
            {UUID(str(row["batch_id"])): UUID(str(row["run_id"])) for row in rows},
        )
        preparers = _preparers(
            session,
            sorted(
                {UUID(str(row["run_job_id"])) for row in rows if row["run_job_id"] is not None},
                key=str,
            ),
        )
        names = approval_queries.display_names(
            session,
            [row["created_by"] for row in rows]
            + [item[0] for item in approvals.values()]
            + [item[0] for item in preparers.values()],
        )
        names |= _client_names(session, preparers.values())
        seen_runs: set[UUID] = set()
        for row in rows:
            as_of = state_as_of(dict(row), known_at, histories.get(UUID(str(row["run_id"])), ()))
            if as_of.cancelled and not include_cancelled:
                continue
            run_id = UUID(str(row["run_id"]))
            if run_id not in seen_runs:
                seen_runs.add(run_id)
                tie_outs.add(
                    run_debits,
                    str(row["run_functional_currency"]).strip(),
                    Decimal(row["run_total_debit_functional"] or ZERO),
                )
            request_id = (
                None
                if row["approval_request_id"] is None
                else UUID(str(row["approval_request_id"]))
            )
            approver = (
                approvals.get(request_id)
                if request_id is not None and as_of.approved_at is not None
                else None
            )
            record = dict(row)
            record["run_state"] = as_of.run_state
            record["approved_at"] = as_of.approved_at
            record["acknowledged_at"] = as_of.acknowledged_at
            record["gl_document_id"] = documents.get(UUID(str(row["batch_id"])))
            preparer = (
                None if row["run_job_id"] is None else preparers.get(UUID(str(row["run_job_id"])))
            )
            record["created_by"] = (
                approval_queries.actor(
                    None if row["created_by"] is None else UUID(str(row["created_by"])),
                    str(row["created_by_kind"]),
                    names,
                )
                if preparer is None
                else approval_queries.actor(preparer[0], preparer[1], names)
            )
            record["approved_by"] = (
                None
                if approver is None
                else approval_queries.actor(approver[0], approver[1], names)
            )
            records.append(record)
    items = rows_from(records)
    return ReportData(
        columns=COLUMNS,
        rows=items,
        control_totals=control_totals(items),
        tie_out_results=(tie_out(items, run_debits),),
    )


def _preparers(session: Any, job_ids: Sequence[UUID]) -> dict[UUID, tuple[UUID, str]]:
    """Per calculation job: the principal that requested it (id, principal kind) — the run's
    preparer. A job no principal requested (the system's own) has no entry."""
    if not job_ids:
        return {}
    rows = session.execute(
        select(job.c.id, job.c.created_by, job.c.created_by_kind).where(
            job.c.id.in_(list(job_ids)), job.c.created_by.is_not(None)
        )
    ).mappings()
    return {
        UUID(str(row["id"])): (
            UUID(str(row["created_by"])),
            str(getattr(row["created_by_kind"], "value", row["created_by_kind"])),
        )
        for row in rows
    }


def _client_names(session: Any, principals: Iterable[tuple[UUID, str]]) -> dict[UUID, str]:
    """The names of the API clients among ``principals`` (a user's display name is read by
    ``approval_queries.display_names``)."""
    ids = sorted({found for found, kind in principals if kind == API_CLIENT}, key=str)
    if not ids:
        return {}
    rows = session.execute(
        select(api_client.c.id, api_client.c.name).where(api_client.c.id.in_(ids))
    )
    return {UUID(str(client_id)): str(name) for client_id, name in rows.tuples()}


def _gl_documents(session: Any, batch_ids: Sequence[UUID], known_at: datetime) -> dict[UUID, str]:
    """The latest ``gl_document_id`` per batch among the acknowledgements received by the cutoff."""
    if not batch_ids:
        return {}
    rows = session.execute(
        select(
            posting_ack.c.journal_batch_id, posting_ack.c.gl_document_id, posting_ack.c.received_at
        )
        .where(
            posting_ack.c.journal_batch_id.in_(list(batch_ids)),
            posting_ack.c.received_at <= known_at,
        )
        .order_by(posting_ack.c.received_at)
    ).mappings()
    found: dict[UUID, str] = {}
    for row in rows:
        if row["gl_document_id"] is not None:
            found[UUID(str(row["journal_batch_id"]))] = str(row["gl_document_id"])
    return found


def _transitions(
    session: Any, run_ids: Sequence[UUID], batch_runs: Mapping[UUID, UUID]
) -> dict[UUID, tuple[Transition, ...]]:
    """Each run's full SOP-7 transition history over every audit record shape that changes a run's
    state — ``journal_run`` records carrying ``after.state`` (approve, cancel) and the batch export
    roll-up ``journal_batch`` records carrying ``after.run_state``, mapped to the run through
    ``batch_runs`` — in (``occurred_at``, ``chain_seq``) order, with no cutoff and no filter on the
    current state (S15-R-18b Q3; D-98 102a, 102c); ``state_as_of`` selects the transition eligible
    at the cutoff."""
    if not run_ids:
        return {}
    run_state = audit_event.c.after["state"].astext
    run_rows = session.execute(
        select(
            audit_event.c.object_id,
            audit_event.c.occurred_at,
            audit_event.c.chain_seq,
            run_state.label("state"),
        ).where(
            audit_event.c.object_type == JOURNAL_RUN_OBJECT,
            audit_event.c.object_id.in_(list(run_ids)),
            run_state.is_not(None),
        )
    ).mappings()
    found: dict[UUID, list[Transition]] = {}
    for row in run_rows:
        found.setdefault(UUID(str(row["object_id"])), []).append(
            Transition(row["occurred_at"], int(row["chain_seq"]), str(row["state"]))
        )
    batch_ids = sorted({batch for batch, run in batch_runs.items() if run in set(run_ids)}, key=str)
    if batch_ids:
        batch_state = audit_event.c.after["run_state"].astext
        batch_rows = session.execute(
            select(
                audit_event.c.object_id,
                audit_event.c.occurred_at,
                audit_event.c.chain_seq,
                batch_state.label("state"),
            ).where(
                audit_event.c.object_type == JOURNAL_BATCH_OBJECT,
                audit_event.c.object_id.in_(batch_ids),
                batch_state.is_not(None),
            )
        ).mappings()
        for row in batch_rows:
            run_id = batch_runs[UUID(str(row["object_id"]))]
            found.setdefault(run_id, []).append(
                Transition(row["occurred_at"], int(row["chain_seq"]), str(row["state"]))
            )
    return {
        run_id: tuple(
            sorted(items, key=lambda item: (item.at, NO_SEQ if item.seq is None else item.seq))
        )
        for run_id, items in found.items()
    }


def _approvals(
    session: Any, request_ids: Sequence[UUID], known_at: datetime
) -> dict[UUID, tuple[UUID | None, str]]:
    """The latest approving decision's approver per request (id, principal kind) among the
    decisions taken by the cutoff."""
    if not request_ids:
        return {}
    rows = session.execute(
        select(
            approval_decision.c.approval_request_id,
            approval_decision.c.approver_id,
            approval_decision.c.approver_kind,
            approval_decision.c.decided_at,
        )
        .where(
            approval_decision.c.approval_request_id.in_(list(request_ids)),
            approval_decision.c.decision.in_(list(APPROVED_DECISIONS)),
            approval_decision.c.decided_at <= known_at,
        )
        .order_by(approval_decision.c.decided_at, approval_decision.c.id)
    ).mappings()
    found: dict[UUID, tuple[UUID | None, str]] = {}
    for row in rows:
        approver = None if row["approver_id"] is None else UUID(str(row["approver_id"]))
        found[UUID(str(row["approval_request_id"]))] = (approver, str(row["approver_kind"]))
    return found
