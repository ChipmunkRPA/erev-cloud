"""Journal run reads (04 §16.7 API-S-JournalRun, API-S-JournalLine, API-S-PostingAck,
API-S-JournalRunSummary; T-SL-06 drill-back note; 05 RCP-27; BUILD_SPEC CLO-8).

Every read runs in the caller's read-only tenant session, so row-level security scopes runs,
batches, entries and lines to the principal's entities. The drill of a journal line re-derives the
grouping key of every line the run summarized — the lines of its seal ranges that its own record
does not name as left out (S14-R-17), and the lines it took over — and keeps those whose key
hashes to the line's ``source_grouping_sha256`` at the grain the journal line was summarised at:
the run's, or the split grain of an entry larger than its ledger's chunk (S14-R-21).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final

from erev_engine.currencies import ISO_4217
from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from erev_api.auth.principal import RequestContext
from erev_api.db.session import system_entity_scope, tenant_session
from erev_api.db.tables import (
    contract,
    gl_account,
    journal_batch,
    journal_entry,
    journal_line,
    journal_run,
    legal_entity,
    obligation,
    period,
    posting_ack,
    subledger_line,
    subledger_posting,
)
from erev_api.domain.journals import completeness, subledger, summarise
from erev_api.domain.platform import approval_queries
from erev_api.enums import BookCode, GlAdapter, JournalRunGrain, JournalRunMode
from erev_api.money import MoneyOut, money_out
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.journals import (
    JournalBalanceCheckOut,
    JournalBatchOut,
    JournalEntryOut,
    JournalLineOut,
    JournalRunOut,
    JournalRunSummaryOut,
    JournalSummaryLineOut,
    PostingAckOut,
)

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.files.store import FileStore

DRILL_HREF: Final = "/api/v1/journal-lines/{line_id}/drill"


def read[T](ctx: RequestContext, fn: Callable[[Session], T]) -> T:
    """Run ``fn`` in a read-only tenant session of the caller."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return fn(session)


def _money(amount: object, currency: object) -> MoneyOut:
    return money_out(Decimal(str(amount)), str(currency).strip(), ISO_4217)


# --- runs ----------------------------------------------------------------------------------------

RUN_COLUMNS: Final = (
    journal_run.c.id,
    journal_run.c.run_no,
    journal_run.c.entity_id,
    legal_entity.c.code.label("entity_code"),
    legal_entity.c.name.label("entity_name"),
    journal_run.c.book_code,
    journal_run.c.period_id,
    period.c.period_key,
    period.c.name.label("period_name"),
    period.c.start_date,
    period.c.end_date,
    journal_run.c.mode,
    journal_run.c.delta_book_code,
    journal_run.c.grain,
    journal_run.c.state,
    journal_run.c.cutoff_known_at,
    journal_run.c.from_chain_seq,
    journal_run.c.to_chain_seq,
    journal_run.c.delta_from_chain_seq,
    journal_run.c.delta_to_chain_seq,
    journal_run.c.functional_currency,
    journal_run.c.line_count,
    journal_run.c.total_debit_functional,
    journal_run.c.total_credit_functional,
    journal_run.c.approval_request_id,
    journal_run.c.approved_at,
    journal_run.c.exported_at,
    journal_run.c.acknowledged_at,
    journal_run.c.cancelled_at,
    journal_run.c.created_by,
    journal_run.c.created_by_kind,
    journal_run.c.created_at,
    journal_run.c.updated_at,
    journal_run.c.row_version,
)


def runs_statement() -> Select[Any]:
    """API-S-JournalRun rows: runs joined to their entity and period."""
    tenant_id = journal_run.c.tenant_id
    joined = journal_run.join(
        legal_entity,
        and_(legal_entity.c.tenant_id == tenant_id, legal_entity.c.id == journal_run.c.entity_id),
    ).join(period, and_(period.c.tenant_id == tenant_id, period.c.id == journal_run.c.period_id))
    return select(*RUN_COLUMNS).select_from(joined)


def batches_statement() -> Select[Any]:
    return select(journal_batch)


def handed_over_at(row: Mapping[str, Any]) -> datetime | None:
    """API-S-JournalRun ``batches`` ``handed_over_at`` (04 §16.7 rev 1.221): the instant a failed
    batch of an ERP adapter was handed over for manual posting, else None. Derived from the
    T-SL-07 row: a hand-over stores the batch's file and stamps ``exported_at``
    (``failed_exits._hand_over``), an ERP adapter that posts a batch stores no file, and the file
    of a ``CSV`` batch is its export — so it is the export time of a batch that holds a file and
    whose adapter is not ``CSV``."""
    adapter = str(getattr(row["adapter"], "value", row["adapter"]))
    if adapter == GlAdapter.CSV.value or row["export_file_id"] is None:
        return None
    exported: datetime | None = row["exported_at"]
    return exported


def batch_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[JournalBatchOut]:
    """T-SL-07 rows with their acknowledgements."""
    ids = [row["id"] for row in rows]
    acks: dict[uuid.UUID, list[Mapping[str, Any]]] = {}
    if ids:
        for ack in session.execute(
            select(posting_ack)
            # one bound value whatever the number of chunks (``summarise.among``)
            .where(summarise.among(posting_ack.c.journal_batch_id, ids))
            .order_by(posting_ack.c.received_at, posting_ack.c.id)
        ).mappings():
            acks.setdefault(ack["journal_batch_id"], []).append(dict(ack))
    names = approval_queries.display_names(
        session, (ack["created_by"] for items in acks.values() for ack in items)
    )
    outs: list[JournalBatchOut] = []
    for row in rows:
        txn, functional = row["txn_currency"], row["functional_currency"]
        outs.append(
            JournalBatchOut(
                id=row["id"],
                journal_run_id=row["journal_run_id"],
                batch_no=row["batch_no"],
                chunk_no=row["chunk_no"],
                txn_currency=str(txn).strip(),
                functional_currency=str(functional).strip(),
                state=row["state"],
                line_count=row["line_count"],
                total_debit_txn=_money(row["total_debit_txn"], txn),
                total_credit_txn=_money(row["total_credit_txn"], txn),
                total_debit_functional=_money(row["total_debit_functional"], functional),
                total_credit_functional=_money(row["total_credit_functional"], functional),
                external_id=row["external_id"],
                adapter=row["adapter"],
                detail_file_id=row["detail_file_id"],
                detail_sha256=None if row["detail_sha256"] is None else str(row["detail_sha256"]),
                attempt_count=row["attempt_count"],
                last_error=row["last_error"],
                exported_at=row["exported_at"],
                acknowledged_at=row["acknowledged_at"],
                handed_over_at=handed_over_at(row),
                acknowledgements=[
                    PostingAckOut(
                        id=ack["id"],
                        ack_kind=ack["ack_kind"],
                        gl_document_id=ack["gl_document_id"],
                        gl_posted_date=ack["gl_posted_date"],
                        message=ack["message"],
                        response_sha256=ack["response_sha256"],
                        received_at=ack["received_at"],
                        recorded_by=approval_queries.actor(
                            ack["created_by"], str(ack["created_by_kind"]), names
                        ),
                    )
                    for ack in acks.get(row["id"], [])
                ],
                row_version=row["row_version"],
            )
        )
    return outs


def run_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[JournalRunOut]:
    """API-S-JournalRun of each ``runs_statement`` row."""
    ids = [row["id"] for row in rows]
    batches: dict[uuid.UUID, list[JournalBatchOut]] = {}
    ranges: dict[uuid.UUID, list[tuple[int, str]]] = {}
    if ids:
        batch_rows = [
            dict(item)
            for item in session.execute(
                select(journal_batch)
                .where(journal_batch.c.journal_run_id.in_(ids))
                .order_by(journal_batch.c.batch_no, journal_batch.c.chunk_no)
            ).mappings()
        ]
        for out in batch_outs(session, batch_rows):
            batches.setdefault(out.journal_run_id, []).append(out)
        numbered = session.execute(
            select(journal_batch.c.journal_run_id, journal_entry.c.je_seq, journal_entry.c.je_no)
            .select_from(
                journal_entry.join(
                    journal_batch,
                    and_(
                        journal_batch.c.tenant_id == journal_entry.c.tenant_id,
                        journal_batch.c.id == journal_entry.c.journal_batch_id,
                    ),
                )
            )
            .where(journal_batch.c.journal_run_id.in_(ids))
        ).tuples()
        for run_id, seq, number in numbered:
            ranges.setdefault(run_id, []).append((int(seq), str(number)))
    names = approval_queries.display_names(session, (row["created_by"] for row in rows))
    outs: list[JournalRunOut] = []
    for row in rows:
        currency = row["functional_currency"]
        debit, credit = row["total_debit_functional"], row["total_credit_functional"]
        numbers = sorted(ranges.get(row["id"], []))
        outs.append(
            JournalRunOut.model_validate(
                {
                    "id": row["id"],
                    "run_no": row["run_no"],
                    "entity": {
                        "id": row["entity_id"],
                        "code": row["entity_code"],
                        "name": row["entity_name"],
                    },
                    "book": row["book_code"],
                    "period": {
                        "id": row["period_id"],
                        "period_key": row["period_key"],
                        "name": row["period_name"],
                        "start_date": row["start_date"],
                        "end_date": row["end_date"],
                    },
                    "mode": row["mode"],
                    "delta_book": row["delta_book_code"],
                    "grain": row["grain"],
                    "state": row["state"],
                    "cutoff_known_at": row["cutoff_known_at"],
                    "coverage": {
                        "from_chain_seq": row["from_chain_seq"],
                        "to_chain_seq": row["to_chain_seq"],
                        "delta_from_chain_seq": row["delta_from_chain_seq"],
                        "delta_to_chain_seq": row["delta_to_chain_seq"],
                    },
                    "totals": {
                        "line_count": row["line_count"],
                        "debit_functional": _money(debit, currency),
                        "credit_functional": _money(credit, currency),
                        "balanced": Decimal(debit) == Decimal(credit),
                    },
                    "batches": batches.get(row["id"], []),
                    "je_range": {
                        "first_je_no": numbers[0][1] if numbers else None,
                        "last_je_no": numbers[-1][1] if numbers else None,
                        "count": len(numbers),
                    },
                    "approval_request_id": row["approval_request_id"],
                    "approved_at": row["approved_at"],
                    "exported_at": row["exported_at"],
                    "acknowledged_at": row["acknowledged_at"],
                    "cancelled_at": row["cancelled_at"],
                    "created_by": approval_queries.actor(
                        row["created_by"], str(row["created_by_kind"]), names
                    ),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "row_version": row["row_version"],
                }
            )
        )
    return outs


def run_row(session: Session, run_id: uuid.UUID) -> Mapping[str, Any]:
    """The visible run, else 404 ``not-found``."""
    row = session.execute(runs_statement().where(journal_run.c.id == run_id)).mappings().first()
    if row is None:
        raise Problem("not-found")
    return dict(row)


def get_run(session: Session, run_id: uuid.UUID) -> JournalRunOut:
    return run_outs(session, [run_row(session, run_id)])[0]


def get_batch(session: Session, batch_id: uuid.UUID) -> JournalBatchOut:
    row = (
        session.execute(select(journal_batch).where(journal_batch.c.id == batch_id))
        .mappings()
        .first()
    )
    if row is None:
        raise Problem("not-found")
    return batch_outs(session, [dict(row)])[0]


# --- entries and lines ---------------------------------------------------------------------------


def _in_run(run_id: uuid.UUID) -> Any:
    return journal_batch.c.journal_run_id == run_id


def entries_statement(run_id: uuid.UUID) -> Select[Any]:
    """The entries of a run with their line counts."""
    counted = (
        select(func.count())
        .select_from(journal_line)
        .where(
            journal_line.c.tenant_id == journal_entry.c.tenant_id,
            journal_line.c.journal_entry_id == journal_entry.c.id,
        )
        .scalar_subquery()
    )
    joined = journal_entry.join(
        journal_batch,
        and_(
            journal_batch.c.tenant_id == journal_entry.c.tenant_id,
            journal_batch.c.id == journal_entry.c.journal_batch_id,
        ),
    )
    return (
        select(
            journal_entry.c.id,
            journal_entry.c.journal_batch_id,
            journal_entry.c.je_seq,
            journal_entry.c.je_no,
            journal_entry.c.je_type,
            journal_entry.c.entry_kind,
            journal_entry.c.description,
            journal_entry.c.is_post_close,
            journal_entry.c.source_event_ids,
            journal_entry.c.manual_adjustment_id,
            journal_entry.c.reverses_journal_entry_id,
            journal_entry.c.created_at,
            counted.label("line_count"),
        )
        .select_from(joined)
        .where(_in_run(run_id))
    )


def entry_outs(rows: Sequence[Mapping[str, Any]]) -> list[JournalEntryOut]:
    return [JournalEntryOut.model_validate(dict(row)) for row in rows]


COUNTERPARTY: Final = legal_entity.alias("counterparty")
ORIGIN: Final = period.alias("origin")


def lines_statement(
    run_id: uuid.UUID, *, contract_id: uuid.UUID | None = None, batch_id: uuid.UUID | None = None
) -> Select[Any]:
    """API-S-JournalLine rows of a run (filters ``contract`` and ``batch_id``)."""
    tenant_id = journal_line.c.tenant_id
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
            gl_account,
            and_(
                gl_account.c.tenant_id == tenant_id, gl_account.c.id == journal_line.c.gl_account_id
            ),
        )
        .outerjoin(
            contract,
            and_(contract.c.tenant_id == tenant_id, contract.c.id == journal_line.c.contract_id),
        )
        # 04 API-S-JournalLine rev 1.245: the obligation by its key AND by the joined contract's
        # id (T-CON-10 is RLS-T, the contract RLS-TE), so that the key is null wherever the
        # contract's name is — as on API-S-SubledgerLine (``subledger.OBLIGATION_JOIN``).
        .outerjoin(
            obligation,
            and_(
                obligation.c.tenant_id == tenant_id,
                obligation.c.id == journal_line.c.obligation_id,
                obligation.c.contract_id == contract.c.id,
            ),
        )
        .outerjoin(
            COUNTERPARTY,
            and_(
                COUNTERPARTY.c.tenant_id == tenant_id,
                COUNTERPARTY.c.id == journal_line.c.counterparty_entity_id,
            ),
        )
        .outerjoin(
            ORIGIN,
            and_(ORIGIN.c.tenant_id == tenant_id, ORIGIN.c.id == journal_line.c.origin_period_id),
        )
    )
    statement = (
        select(
            journal_line.c.id,
            journal_line.c.journal_batch_id,
            journal_entry.c.je_no,
            journal_entry.c.je_type,
            journal_entry.c.is_post_close,
            journal_line.c.line_no,
            journal_line.c.gl_account_id,
            journal_line.c.gl_account_code,
            gl_account.c.name.label("account_name"),
            journal_line.c.account_role,
            journal_line.c.dimensions,
            journal_line.c.txn_currency,
            journal_line.c.debit_txn,
            journal_line.c.credit_txn,
            journal_line.c.functional_currency,
            journal_line.c.debit_functional,
            journal_line.c.credit_functional,
            journal_line.c.contract_id,
            contract.c.external_id.label("contract_external_id"),
            obligation.c.obligation_key,
            journal_line.c.legacy_key,
            journal_line.c.counterparty_entity_id,
            COUNTERPARTY.c.code.label("counterparty_code"),
            COUNTERPARTY.c.name.label("counterparty_name"),
            ORIGIN.c.period_key.label("origin_period_key"),
            journal_line.c.fx_rate_ids,
            journal_line.c.memo,
            journal_line.c.source_line_count,
            journal_line.c.source_grouping_sha256,
        )
        .select_from(joined)
        .where(_in_run(run_id))
    )
    if contract_id is not None:
        statement = statement.where(journal_line.c.contract_id == contract_id)
    if batch_id is not None:
        statement = statement.where(journal_line.c.journal_batch_id == batch_id)
    return statement


def counterparties(
    session: Session, rows: Sequence[Mapping[str, Any]]
) -> dict[uuid.UUID, dict[str, Any]]:
    """The references of the counterparty entities that ``lines_statement`` could not name: an
    intercompany line states its counterparty by id, and ``legal_entity`` is RLS-TE, so the outer
    join finds no row for an entity outside the caller's entity scope. Who reads the line reads
    whose counterparty it has: the id, the code and the name, nothing else of the entity, are
    read under the tenant's scope for this one statement (04 API-S-JournalLine rev 1.245; the way
    of ``contracts.queries._entity_refs``, supervisor ruling R-85 (d)). Until rev 1.245 such a
    line failed the read with 500: API-S-Ref types code and name as strings."""
    missing = sorted(
        {
            uuid.UUID(str(row["counterparty_entity_id"]))
            for row in rows
            if row["counterparty_entity_id"] is not None and row["counterparty_code"] is None
        },
        key=str,
    )
    if not missing:
        return {}
    with system_entity_scope(session):
        found = session.execute(
            select(legal_entity.c.id, legal_entity.c.code, legal_entity.c.name).where(
                legal_entity.c.id.in_(missing)
            )
        ).all()
    return {
        uuid.UUID(str(item.id)): {"id": item.id, "code": item.code, "name": item.name}
        for item in found
    }


def line_outs(
    rows: Sequence[Mapping[str, Any]],
    named: Mapping[uuid.UUID, Mapping[str, Any]] | None = None,
) -> list[JournalLineOut]:
    """API-S-JournalLine of each ``lines_statement`` row; ``named`` are the counterparty
    references the statement could not join (``counterparties``)."""
    outs: list[JournalLineOut] = []
    elsewhere = named or {}
    for row in rows:
        txn, functional = row["txn_currency"], row["functional_currency"]
        counterparty: Mapping[str, Any] | None = None
        if row["counterparty_entity_id"] is not None:
            counterparty = elsewhere.get(uuid.UUID(str(row["counterparty_entity_id"]))) or {
                "id": row["counterparty_entity_id"],
                "code": row["counterparty_code"],
                "name": row["counterparty_name"],
            }
        outs.append(
            JournalLineOut(
                id=row["id"],
                journal_batch_id=row["journal_batch_id"],
                je_no=row["je_no"],
                je_type=row["je_type"],
                line_no=row["line_no"],
                account={
                    "id": row["gl_account_id"],
                    "code": row["gl_account_code"],
                    "name": row["account_name"],
                },
                account_role=row["account_role"],
                dimensions={
                    str(key): str(value) for key, value in (row["dimensions"] or {}).items()
                },
                txn_currency=str(txn).strip(),
                debit_txn=_money(row["debit_txn"], txn),
                credit_txn=_money(row["credit_txn"], txn),
                debit_functional=_money(row["debit_functional"], functional),
                credit_functional=_money(row["credit_functional"], functional),
                contract=None
                if row["contract_id"] is None
                else {"id": row["contract_id"], "external_id": row["contract_external_id"]},
                obligation_key=row["obligation_key"],
                legacy_key=row["legacy_key"],
                counterparty_entity=counterparty,
                origin_period_key=row["origin_period_key"],
                is_post_close=row["is_post_close"],
                fx_rate_ids=list(row["fx_rate_ids"] or []),
                memo=row["memo"],
                source_line_count=row["source_line_count"],
                source_grouping_sha256=str(row["source_grouping_sha256"]),
                links={"drill": DRILL_HREF.format(line_id=row["id"])},
            )
        )
    return outs


def summary(session: Session, run_id: uuid.UUID) -> JournalRunSummaryOut:
    """API-S-JournalRunSummary: sums per (GL account, transaction currency), and the balance checks
    per (entity, currency) in transaction and functional currency (DB-16)."""
    run = run_row(session, run_id)
    rows = [dict(item) for item in session.execute(lines_statement(run_id)).mappings()]
    by_account: dict[tuple[str, str], list[Any]] = {}
    checks: dict[tuple[str, str], list[Decimal]] = {}
    for row in rows:
        txn, functional = str(row["txn_currency"]).strip(), str(row["functional_currency"]).strip()
        found = by_account.setdefault(
            (row["gl_account_code"], txn), [row["account_name"], Decimal(0), Decimal(0)]
        )
        found[1] += Decimal(row["debit_txn"])
        found[2] += Decimal(row["credit_txn"])
        for basis, currency, debit, credit in (
            ("TRANSACTION", txn, row["debit_txn"], row["credit_txn"]),
            ("FUNCTIONAL", functional, row["debit_functional"], row["credit_functional"]),
        ):
            sums = checks.setdefault((basis, currency), [Decimal(0), Decimal(0)])
            sums[0] += Decimal(debit)
            sums[1] += Decimal(credit)
    lines = [
        JournalSummaryLineOut(
            account_code=code,
            account_name=str(values[0]),
            currency=currency,
            debit=_money(values[1], currency),
            credit=_money(values[2], currency),
        )
        for (code, currency), values in sorted(by_account.items())
    ]
    balance = [
        JournalBalanceCheckOut(
            entity_code=str(run["entity_code"]),
            currency=currency,
            basis=basis,
            debit=_money(debit, currency),
            credit=_money(credit, currency),
            difference=_money(debit - credit, currency),
        )
        for (basis, currency), (debit, credit) in sorted(
            checks.items(), key=lambda item: (item[0][0] != "TRANSACTION", item[0][1])
        )
    ]
    return JournalRunSummaryOut(lines=lines, balance_checks=balance)


# --- drill (RCP-27) -------------------------------------------------------------------------------


RECORD_UNREADABLE: Final = (
    "Journal run {run} cannot be traced to its source lines: the record of the lines it left out "
    "cannot be read."
)
RULE_RECORD_UNREADABLE: Final = "RUN_RECORD_UNREADABLE"


def drill_ids(
    session: Session,
    line_id: uuid.UUID,
    *,
    files: FileStore | None = None,
    keyring: KeyRing | None = None,
) -> list[uuid.UUID]:
    """The contributing subledger lines of a journal line (T-SL-06 drill-back; RCP-27): the
    lines its run summarized, grouped as the journal line.

    Which lines of its range a run left out as held is read from the run's own record — the ids
    its CALCULATE event names, else its held detail file — by the one rule the completeness
    assertion reads (``completeness.summarized``; 04 T-SL-06 rev 1.288, item
    SUBLEDGER-LINE-JOURNAL-RUN-1). Until that revision the drill decided by the holds'
    timestamps (held when applied by the run's ``created_at`` and released later or never)
    while the calculation had decided by the holds open in its transaction: where a hold or a
    release shared the run's instant, the drill named lines the run had left out, or hid lines
    it had summarized, and the drilled amounts did not sum to the journal line. ``files`` and
    ``keyring`` go to the record's reader, as the gate hands them. A run whose record cannot be
    read journalises nothing, and its drill is refused — 409 ``invalid-transition``, rule
    ``RUN_RECORD_UNREADABLE`` (PRD ERR-101) — rather than answered by a guess."""
    line = (
        session.execute(
            select(
                journal_line.c.source_grouping_sha256,
                journal_line.c.txn_currency,
                journal_batch.c.journal_run_id,
            )
            .select_from(
                journal_line.join(
                    journal_batch,
                    and_(
                        journal_batch.c.tenant_id == journal_line.c.tenant_id,
                        journal_batch.c.id == journal_line.c.journal_batch_id,
                    ),
                )
            )
            .where(journal_line.c.id == line_id)
        )
        .mappings()
        .first()
    )
    if line is None:
        raise Problem("not-found")
    run = (
        session.execute(select(journal_run).where(journal_run.c.id == line["journal_run_id"]))
        .mappings()
        .one()
    )
    grain = JournalRunGrain(str(run["grain"]))
    candidates = summarise.detail_lines(
        session,
        summarise.detail_statement(
            entity_id=run["entity_id"],
            book_code=str(run["book_code"]),
            period_id=run["period_id"],
            from_seq=int(run["from_chain_seq"]),
            to_seq=int(run["to_chain_seq"]),
        ),
    )
    if JournalRunMode(str(run["mode"])) is JournalRunMode.DELTA:
        candidates += summarise.detail_lines(
            session,
            summarise.detail_statement(
                entity_id=run["entity_id"],
                book_code=BookCode.LEGACY.value,
                period_id=run["period_id"],
                from_seq=int(run["delta_from_chain_seq"] or 0),
                to_seq=int(run["delta_to_chain_seq"] or 0),
            ),
            sign=1,  # DELTA = primary + LEGACY lines (S14-R-23; D-89 L7-6-Q-8)
        )
    run_id = uuid.UUID(str(run["id"]))
    # the event is asked at the instant the run was created at: one month of the audit log
    record = completeness.run_records(
        session,
        [run_id],
        files=files,
        keyring=keyring,
        calculated_at={run_id: run["created_at"]},
    )[run_id]
    if record.excluded is None:
        detail = RECORD_UNREADABLE.format(run=run["run_no"])
        error = ProblemError(rule_id=RULE_RECORD_UNREADABLE, message=detail)
        raise Problem("invalid-transition", detail, errors=[error])
    recorded = completeness.RunCoverage(
        id=run_id,
        mode=str(run["mode"]),
        from_chain_seq=int(run["from_chain_seq"]),
        to_chain_seq=int(run["to_chain_seq"]),
        excluded=record.excluded,
        included=record.taken_over,
    )
    # The lines the run took over from runs of its key that had left them out (S14-R-17 rev
    # 1.164; 04 DB-16 rev 1.267): named by id in its CALCULATE event, outside its range, and
    # summarized with it — so they are among the lines a journal line of the run drills to.
    taken = record.taken_over
    taken_lines: list[summarise.DetailLine] = []
    if taken:
        taken_lines = summarise.detail_lines(
            session,
            summarise.left_out_statement(
                entity_id=run["entity_id"],
                book_codes=[str(run["book_code"]), BookCode.LEGACY.value],
                period_id=run["period_id"],
                line_ids=sorted(taken, key=str),
            ),
        )
    codes = summarise.dimension_codes(session)
    target = str(line["source_grouping_sha256"])
    summarized = [
        *(item for item in candidates if completeness.summarized(recorded, item.id, in_range=True)),
        *(
            item
            for item in taken_lines
            if completeness.summarized(recorded, item.id, in_range=False)
        ),
    ]
    # at the grain the journal line was summarised at: the run's, or the split grain of an entry
    # larger than its ledger's chunk (S14-R-21) — ``summarise.lines_of_group``
    return [
        item.id
        for item in summarise.lines_of_group(summarized, target, grain=grain, dimension_codes=codes)
    ]


def drill_statement(line_ids: Sequence[uuid.UUID]) -> Select[Any]:
    """API-S-SubledgerLine rows of the given lines, in any book (``subledger.LINE_COLUMNS``)."""
    tenant_id = subledger_line.c.tenant_id
    joined = (
        subledger_line.join(
            subledger_posting,
            and_(
                subledger_posting.c.tenant_id == tenant_id,
                subledger_posting.c.id == subledger_line.c.subledger_posting_id,
            ),
        )
        .join(
            legal_entity,
            and_(
                legal_entity.c.tenant_id == tenant_id,
                legal_entity.c.id == subledger_line.c.entity_id,
            ),
        )
        .join(
            gl_account,
            and_(
                gl_account.c.tenant_id == tenant_id,
                gl_account.c.id == subledger_line.c.gl_account_id,
            ),
        )
        .join(
            period, and_(period.c.tenant_id == tenant_id, period.c.id == subledger_line.c.period_id)
        )
        .outerjoin(
            subledger.ORIGIN_PERIOD,
            and_(
                subledger.ORIGIN_PERIOD.c.tenant_id == tenant_id,
                subledger.ORIGIN_PERIOD.c.id == subledger_line.c.origin_period_id,
            ),
        )
        .outerjoin(contract, subledger.CONTRACT_JOIN)
        .outerjoin(obligation, subledger.OBLIGATION_JOIN)
    )
    return (
        select(*subledger.LINE_COLUMNS)
        .select_from(joined)
        # one bound value whatever the number of lines (``summarise.among``)
        .where(summarise.among(subledger_line.c.id, line_ids))
    )
