"""What a reconciliation read, and when a reviewed one is out of date (item REC-GEN-LOCK-1; 04
T-CLS-06 rev 1.259; the supervisor's rulings of 2026-10-01 21:41 and 22:52 and of 2026-10-02 00:09
and 01:41), without a database.

A generation records the book's ledger chain position and how many documents it depends on beside
the ledger; the gate's ``overtaken`` asks for a line sealed after that position or a count that
differs. The statements are pinned as PostgreSQL receives them: the generation and the gate read
under the SAME conditions (``gates.source_invoices_of``, ``billing_streams_of``,
``ledger_documents``), the position is a plain read without a lock, and a row generated before
revision 0121 — NULL in all three columns — keeps the test by time.

The ledger kind's number has two terms (``gates.ledger_documents``): the contract events of the
entity dated through the period's last day, and the inclusions of those events in a contract
version of the book (T-CON-08 ``cause_event_ids``) — an event moves it when it is recorded and
again when it is first computed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from erev_api.db.tables import reconciliation
from erev_api.domain.close import gates, reconciliations
from erev_api.domain.close.gates import PeriodScope
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

ENTITY = UUID("00000000-0000-0000-0000-0000000000e1")
PERIOD = UUID("00000000-0000-0000-0000-0000000000a1")
SCOPE = PeriodScope(
    state_id=PERIOD,
    entity_id=ENTITY,
    entity_code="AVM-US",
    functional_currency="USD",
    book_code="ASC606",
    period_id=PERIOD,
    period_key="FY2026-P01",
    period_name="Jan 2026",
    start_date=date(2026, 1, 1),
    end_date=date(2026, 1, 31),
    state="open",
    current_lock_id=None,
    row_version=1,
)
AS_OF = datetime(2026, 2, 3, 9, tzinfo=UTC)

# The pinned statements are plain templates filled by name (no SQL is built from input here).
# The populations, as conditions.
LINE_OF_PERIOD = (
    "erev.subledger_line.tenant_id = erev.reconciliation.tenant_id "
    f"AND erev.subledger_line.entity_id = '{ENTITY}' "
    "AND erev.subledger_line.book_code = 'ASC606' "
    "AND (erev.reconciliation.kind = 'SUBLEDGER_TO_GL' "
    "AND erev.subledger_line.period_end_date <= '2026-01-31' "
    "OR erev.reconciliation.kind != 'SUBLEDGER_TO_GL' "
    "AND erev.subledger_line.period_end_date = '2026-01-31' "
    f"AND erev.subledger_line.period_id = '{PERIOD}')"
)
SOURCE_INVOICES = (
    "erev.source_invoice.legal_entity_code = 'AVM-US' "
    "AND erev.source_invoice.issue_date >= '2026-01-01' "
    "AND erev.source_invoice.issue_date <= '2026-01-31'"
)
_BILLED_CONTRACTS = (
    "SELECT DISTINCT erev.contract_event.contract_id FROM erev.contract_event "
    "WHERE erev.contract_event.contracting_entity_id = '{entity}' "
    "AND erev.contract_event.event_type IN ('BILLING_RECORDED', 'CREDIT_MEMO_RECORDED') "
    "AND erev.contract_event.effective_date >= '2026-01-01' "
    "AND erev.contract_event.effective_date <= '2026-01-31'"
)
BILLED_CONTRACTS = _BILLED_CONTRACTS.format(entity=ENTITY)
BILLING_STREAMS = (
    f"erev.contract_event.contract_id IN ({BILLED_CONTRACTS}) "
    "AND (erev.contract_event.event_type IN ('BILLING_RECORDED', 'CREDIT_MEMO_RECORDED') "
    "AND erev.contract_event.effective_date <= '2026-01-31' "
    "OR erev.contract_event.event_type IN ('EVENT_VOIDED', 'CONTRACT_VOIDED'))"
)
EVENTS_THROUGH = (
    f"erev.contract_event.contracting_entity_id = '{ENTITY}' "
    "AND erev.contract_event.effective_date <= '2026-01-31'"
)
# The ledger kind's number: the events, plus their inclusions in a version of the book. A count
# is labelled by its place in the statement that holds it ({first}, {second}). The gate counts
# every row there is; a generation bounds each term by its own instant ({recorded}, {known}).
_LEDGER_DOCUMENTS = (
    "(SELECT count(*) AS count_{first} FROM erev.contract_event WHERE {events}{recorded}) + "
    "(SELECT count(*) AS count_{second} FROM erev.contract_version "
    "JOIN unnest(erev.contract_version.cause_event_ids) AS included(event_id) ON true "
    "JOIN erev.contract_event ON erev.contract_event.tenant_id = erev.contract_version.tenant_id "
    "AND erev.contract_event.id = included.event_id "
    "WHERE erev.contract_version.book_code = 'ASC606' AND {events}{known})"
)
RECORDED_BY = " AND erev.contract_event.recorded_at <= '2026-02-03 09:00:00+00:00'"
KNOWN_BY = " AND erev.contract_version.known_at <= '2026-02-03 09:00:00+00:00'"
# ``gates.overtaken`` in four parts: a later line, then what moved beside the ledger.
_LATER_SEAL = (
    "erev.reconciliation.ledger_chain_seq IS NOT NULL AND (EXISTS (SELECT * FROM "
    "erev.subledger_line, erev.subledger_posting_seal WHERE {line} "
    "AND erev.subledger_posting_seal.tenant_id = erev.subledger_line.tenant_id "
    "AND erev.subledger_posting_seal.subledger_posting_id = "
    "erev.subledger_line.subledger_posting_id "
    "AND erev.subledger_posting_seal.chain_seq > erev.reconciliation.ledger_chain_seq))"
)
_LINE_BY_TIME = (
    "erev.reconciliation.ledger_chain_seq IS NULL AND (EXISTS (SELECT * FROM erev.subledger_line "
    "WHERE {line} AND erev.subledger_line.recorded_at > erev.reconciliation.as_of_known_at))"
)
_SOURCE_MOVED = (
    "erev.reconciliation.kind = 'BILLING_TO_SUBLEDGER' AND "
    "(erev.reconciliation.source_documents_read IS NOT NULL "
    "AND erev.reconciliation.source_documents_read != (SELECT count(*) AS count_1 FROM "
    "erev.source_invoice WHERE {invoices}) OR erev.reconciliation.source_documents_read IS NULL "
    "AND (EXISTS (SELECT * FROM erev.source_invoice WHERE erev.source_invoice.tenant_id = "
    "erev.reconciliation.tenant_id AND {invoices} AND erev.source_invoice.created_at > "
    "erev.reconciliation.as_of_known_at)))"
)
_SUBLEDGER_MOVED = (
    "erev.reconciliation.subledger_documents_read IS NOT NULL AND "
    "(erev.reconciliation.kind = 'BILLING_TO_SUBLEDGER' "
    "AND erev.reconciliation.subledger_documents_read != (SELECT count(*) AS count_2 FROM "
    "erev.contract_event WHERE {streams}) OR erev.reconciliation.kind = 'SUBLEDGER_TO_GL' "
    "AND erev.reconciliation.subledger_documents_read != {ledger})"
)
_OVERTAKEN = (
    "SELECT erev.reconciliation.id FROM erev.reconciliation WHERE erev.reconciliation.status IN "
    "('REVIEWED', 'AUTO_CERTIFIED') AND ({later_seal} OR {line_by_time} OR {source_moved} OR "
    "{subledger_moved})"
)
OVERTAKEN = _OVERTAKEN.format(
    later_seal=_LATER_SEAL.format(line=LINE_OF_PERIOD),
    line_by_time=_LINE_BY_TIME.format(line=LINE_OF_PERIOD),
    source_moved=_SOURCE_MOVED.format(invoices=SOURCE_INVOICES),
    subledger_moved=_SUBLEDGER_MOVED.format(
        streams=BILLING_STREAMS,
        ledger=_LEDGER_DOCUMENTS.format(
            first=3, second=4, events=EVENTS_THROUGH, recorded="", known=""
        ),
    ),
)
_SOURCE_READ = "FROM erev.source_invoice WHERE {invoices} ORDER BY erev.source_invoice.id"
_STREAMS_READ = (
    "FROM erev.contract_event WHERE {streams} ORDER BY erev.contract_event.effective_date, "
    "erev.contract_event.record_seq, erev.contract_event.id"
)
_LEDGER_COUNTED = "SELECT {ledger} AS anon_1"


def _sql(statement: Any) -> str:
    compiled = statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    return " ".join(str(compiled).split())


class _Session:
    """Records the statements it is handed and answers each with ``rows``."""

    def __init__(self, rows: Any = ()) -> None:
        self.statements: list[Any] = []
        self._rows = rows

    def execute(self, statement: Any) -> Any:
        self.statements.append(statement)
        rows = self._rows

        first = len(self.statements) == 1

        class _Found:
            def mappings(self) -> Any:
                return iter(rows if first else ())

            def tuples(self) -> Any:
                return iter(())

            def all(self) -> Any:
                return list(rows)

            def scalar_one(self) -> Any:
                return rows

            def scalar_one_or_none(self) -> Any:
                return rows

            def __iter__(self) -> Any:
                return iter(rows)

        return _Found()


def test_a_reviewed_reconciliation_is_out_of_date_by_a_later_seal_or_a_count_that_differs() -> None:
    """``gates.overtaken``: the whole condition. The position decides "a later line" for a row
    that holds one and the time test only for a row that holds none; the source count belongs to
    billing to subledger, the subledger count to each kind by its own population."""
    assert _sql(select(reconciliation.c.id).where(gates.overtaken(SCOPE))) == OVERTAKEN


def test_the_gate_counts_under_the_conditions_a_generation_reads_under() -> None:
    """The three populations are stated once (``gates``) and the generation reads its rows under
    the very conditions the gate counts under: a count the gate takes is a count of what a
    generation would read now."""
    session: Any = _Session()
    documents, read = reconciliations.source_documents(session, SCOPE)
    assert (documents, read) == ([], 0)
    assert _sql(session.statements[0]).endswith(_SOURCE_READ.format(invoices=SOURCE_INVOICES))
    session = _Session()
    documents, read = reconciliations.billed_documents(session, SCOPE)
    assert (documents, read) == ([], 0)
    assert _sql(session.statements[0]).endswith(_STREAMS_READ.format(streams=BILLING_STREAMS))
    # the ledger kind: the gate's expression, bounded by the reconciliation's own instant — the
    # events recorded and the versions known at or before it, which is what the attach reads
    session = _Session(41)
    assert reconciliations.ledger_events_read(session, SCOPE, AS_OF) == 41
    assert _sql(session.statements[0]) == _LEDGER_COUNTED.format(
        ledger=_LEDGER_DOCUMENTS.format(
            first=1, second=2, events=EVENTS_THROUGH, recorded=RECORDED_BY, known=KNOWN_BY
        )
    )
    assert _sql(select(gates.ledger_documents(SCOPE))) == _LEDGER_COUNTED.format(
        ledger=_LEDGER_DOCUMENTS.format(
            first=1, second=2, events=EVENTS_THROUGH, recorded="", known=""
        )
    )


def test_a_generation_counts_every_row_it_read() -> None:
    """The counts are of rows READ, not of documents compared: every stored version of a source
    invoice counts though only the newest is compared, and a void counts though it is no
    document — a new version or a new void changes the comparison."""
    invoice = {
        "source_system": "CSV_V2",
        "external_invoice_id": "INV-US-1001",
        "invoice_number": "INV-US-1001",
        "document_kind": "INVOICE",
        "currency": "USD",
    }
    versions = [
        {**invoice, "id": UUID(int=1), "external_version": "1", "total_amount": "100.00"},
        {**invoice, "id": UUID(int=2), "external_version": "2", "total_amount": "120.00"},
    ]
    documents, read = reconciliations.source_documents(_Session(versions), SCOPE)  # type: ignore[arg-type]
    assert read == 2 and [(item.invoice_number, str(item.amount)) for item in documents] == [
        ("INV-US-1001", "120.00")
    ]
    contract_id = UUID(int=7)
    billed = {
        "id": UUID(int=11),
        "contract_id": contract_id,
        "event_type": "BILLING_RECORDED",
        "effective_date": date(2026, 1, 5),
        "record_seq": 1,
        "payload": {
            "invoice_number": "INV-US-1001",
            "line_external_id": "INV-US-1001-1",
            "amount": {"amount": "120.00", "currency": "USD"},
        },
        "supersedes_event_id": None,
    }
    void = {
        "id": UUID(int=12),
        "contract_id": contract_id,
        "event_type": "EVENT_VOIDED",
        "effective_date": date(2026, 1, 5),
        "record_seq": 2,
        "payload": {},
        "supersedes_event_id": UUID(int=11),
    }
    documents, read = reconciliations.billed_documents(_Session([billed, void]), SCOPE)  # type: ignore[arg-type]
    assert (documents, read) == ([], 2)  # the voided invoice is no document; both events were read


def test_the_chain_position_is_a_plain_read_of_the_books_head() -> None:
    """``chain_position``: the head of the run's book as the session reads it — no ``FOR
    UPDATE`` and no ``FOR SHARE``: nothing waits for a generation, and a generation waits for
    nothing. A book without a head row has sealed nothing: position 0, which every seal is
    later than."""
    session: Any = _Session(17)
    assert reconciliations.chain_position(session, SCOPE) == 17
    assert _sql(session.statements[0]) == (
        "SELECT erev.ledger_chain_head.last_chain_seq FROM erev.ledger_chain_head "
        "WHERE erev.ledger_chain_head.book_code = 'ASC606'"
    )
    assert reconciliations.chain_position(_Session(None), SCOPE) == 0  # type: ignore[arg-type]


def test_the_subledger_side_is_the_lines_sealed_up_to_the_position() -> None:
    """``_subledger_side``: with a chain position the lines of the postings sealed up to it are
    held and a later seal counts as later; without one — a row generated before revision 0121 —
    the lines recorded at or before the reconciliation's ``as_of_known_at``."""
    windows = reconciliations._Windows(
        fiscal_year=2026, year_start=date(2026, 1, 1), period_end=date(2026, 1, 31)
    )
    seal = (
        "JOIN erev.subledger_posting_seal ON erev.subledger_posting_seal.tenant_id = "
        "erev.subledger_line.tenant_id AND erev.subledger_posting_seal.subledger_posting_id = "
        "erev.subledger_line.subledger_posting_id"
    )
    session: Any = _Session()
    reconciliations._subledger_side(session, SCOPE, windows, AS_OF, 7)
    by_position = _sql(session.statements[0])
    assert seal in by_position
    assert "FILTER (WHERE erev.subledger_posting_seal.chain_seq <= 7)" in by_position
    assert "FILTER (WHERE erev.subledger_posting_seal.chain_seq > 7) AS later" in by_position
    assert "recorded_at" not in by_position
    session = _Session()
    reconciliations._subledger_side(session, SCOPE, windows, AS_OF)
    by_time = _sql(session.statements[0])
    assert "subledger_posting_seal" not in by_time
    assert (
        "FILTER (WHERE erev.subledger_line.recorded_at <= '2026-02-03 09:00:00+00:00')" in by_time
    )
    assert (
        "FILTER (WHERE erev.subledger_line.recorded_at > '2026-02-03 09:00:00+00:00') AS later"
        in by_time
    )
