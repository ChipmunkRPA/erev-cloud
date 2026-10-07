"""Record §19: the read side, mock-executed over ``FakeTables`` (rows per table, no database).

Fail-first (`.run/f-rps-e1/fail-first-read-side.log`, head 4b24d11c): every checkpoint block of
the five keys is ``not_run`` on the mock DB platform ("reads from persisted rows (following
slice)"), the adapter has no ``reads`` / ``jobs``, and ``workspace_reads`` does not exist.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db.tables import (
    approval_request,
    audit_event,
    calc_trace,
    combination_group,
    combination_group_member,
    contract,
    contract_computation,
    contract_version,
    contract_version_balance,
    gl_account,
    journal_batch,
    journal_entry,
    journal_line,
    journal_run,
    legal_entity,
    obligation,
    obligation_version,
    outbox_message,
    period,
    period_state,
    period_state_transition,
    report_run,
    role,
    subledger_line,
    subledger_posting,
    subledger_posting_seal,
)
from erev_api.domain.platform import provisioning
from erev_api.enums import ApprovalSubjectType, OutboxTopic, PrincipalKind
from erev_api.events import outbox
from erev_api.explain.store import trace_document
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from erev_engine.trace import Trace, TraceNode
from sqlalchemy import Table
from support.answer_keys.ledger_resolver import LedgerResolver, UnresolvedHandle
from support.answer_keys.platform_plan import (
    JOURNAL,
    PLATFORM_KEY_IDS,
    PREPARER,
    H,
    load_platform_key,
    plan,
)
from support.answer_keys.platform_runner import JournalLine, NotProvisioned
from support.answer_keys.request_models import adapt
from support.answer_keys.runners import CheckpointRun, _Assembler
from support.answer_keys.workspace_adapter import (
    Call,
    JournalAnswer,
    LedgerEntry,
    RecordingInvoker,
    WorkspaceAdapter,
    WorkspaceJobs,
    missing_balances,
)
from support.answer_keys.workspace_reads import (
    NOT_PERSISTED,
    PersistedReads,
    WorkspaceRows,
    money_columns,
    under_group_name,
)

POS_012, DLT, EX21, EX42, POS_117 = PLATFORM_KEY_IDS
T0 = datetime(2026, 1, 10, 12, tzinfo=UTC)


def uid(*parts: object) -> UUID:
    return uuid5(NAMESPACE_URL, "erev://reads/" + "/".join(str(part) for part in parts))


class FakeTables:
    """``TableSource`` with rows per table and files per id; equality filters like the real one."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.files: dict[UUID, bytes] = {}
        self.tenant = uid("tenant")

    @property
    def tenant_id(self) -> UUID:
        return self.tenant

    def add(self, table: Table, **row: Any) -> dict[str, Any]:
        row.setdefault("id", uid(table.name, len(self.tables.get(table.name, []))))
        self.tables.setdefault(table.name, []).append(row)
        return row

    def table_rows(self, table: Table, **equals: object) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.tables.get(table.name, [])
            if all(row.get(name) == value for name, value in equals.items())
        ]

    def aggregate(self, table: Table, column: str) -> tuple[int, object]:
        rows = self.tables.get(table.name, [])
        values = [row[column] for row in rows if row.get(column) is not None]
        return len(rows), (max(values) if values else None)

    def file_bytes(self, file_id: UUID) -> bytes:
        return self.files[file_id]


class FakeJobs:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, datetime]] = []
        self.run_id = uid("run")

    def report_run(self, block: object, known_at: datetime) -> UUID:
        self.calls.append(("report", block, known_at))
        return self.run_id


def _entry(call: Call, result: object) -> LedgerEntry:
    return LedgerEntry(call, call.actor, T0, T0, None, result)


# --- READ-3: approvals ----------------------------------------------------------------------------


def test_approval_pairs_read_the_pending_request_of_each_subject() -> None:
    tables = FakeTables()
    x, y, z = uid("contract", "X"), uid("contract", "Y"), uid("contract", "Z")
    kind = ApprovalSubjectType.CONTRACT_ACTIVATION
    tables.add(
        approval_request,
        subject_type=kind.value,
        subject_id=x,
        status="APPROVED",
        subject_content_sha256="a" * 64,
    )
    pending_x = tables.add(
        approval_request,
        subject_type=kind.value,
        subject_id=x,
        status="PENDING",
        subject_content_sha256="c" * 64,
    )
    pending_y = tables.add(
        approval_request,
        subject_type=kind.value,
        subject_id=y,
        status="PENDING",
        subject_content_sha256="b" * 64,
    )
    reads = PersistedReads(tables)
    assert reads.approval_pairs(kind, [x, y], where="t") == (
        (pending_x["id"], "c" * 64),
        (pending_y["id"], "b" * 64),
    )
    with pytest.raises(NotProvisioned, match="0 pending approval requests"):
        reads.approval_pairs(kind, [z], where="t")
    tables.add(approval_request, subject_type=kind.value, subject_id=y, status="PENDING")
    with pytest.raises(NotProvisioned, match="2 pending approval requests"):
        reads.approval_pairs(kind, [y], where="t")
    tables.add(approval_request, subject_type=kind.value, subject_id=z, status="PENDING")
    with pytest.raises(NotProvisioned, match="no subject_content_sha256"):
        reads.approval_pairs(kind, [z], where="t")


def test_res_r1_scenario_reads_ys_own_hash_from_ys_pending_request() -> None:
    """Codex's RES-R1 inputs with the read side: Y's digest comes from Y's own PENDING request
    (never X's); a result id that is not the subject's pending request refuses; a None-return
    submit resolves its subject through the ledger and the read."""
    loaded = load_platform_key(POS_012)
    steps = plan(loaded).steps

    def step(handler: str, seq: int):  # noqa: ANN202
        # the item's own TIMELINE step: the runner's steps before an activation share its seq
        return next(
            s for s in steps if s.seq == seq and s.handler == handler and s.phase == "TIMELINE"
        )

    x_contract, y_contract = uid("contract", "X"), uid("contract", "Y")
    x_id = UUID("00000000-0000-0000-0000-00000000002e")
    y_id = UUID("00000000-0000-0000-0000-00000000003e")
    book_x = Call(H["book"], PREPARER, {"contract": "C-POS-012-X"}, step(H["book"], 1))
    book_y = Call(H["book"], PREPARER, {"contract": "C-POS-012-Y"}, step(H["book"], 3))
    submit_x = Call(
        H["submit_activation"],
        PREPARER,
        {"contract": "C-POS-012-X"},
        step(H["submit_activation"], 2),
    )
    decide_x = Call(H["decide"], "ak-approver", {}, step(H["decide"], 2))
    submit_y = Call(
        H["submit_activation"],
        PREPARER,
        {"contract": "C-POS-012-Y"},
        step(H["submit_activation"], 4),
    )
    ledger = [
        _entry(
            book_x, SimpleNamespace(contract={"id": x_contract}, combination_group={"id": uid("g")})
        ),
        _entry(submit_x, SimpleNamespace(contract={"id": x_contract}, approval_request_id=x_id)),
        _entry(decide_x, {"id": x_id, "status": "APPROVED", "subject_content_sha256": "a" * 64}),
        _entry(
            book_y, SimpleNamespace(contract={"id": y_contract}, combination_group={"id": uid("h")})
        ),
        _entry(submit_y, SimpleNamespace(contract={"id": y_contract}, approval_request_id=y_id)),
    ]
    tables = FakeTables()
    kind = ApprovalSubjectType.CONTRACT_ACTIVATION
    tables.add(
        approval_request,
        id=x_id,
        subject_type=kind.value,
        subject_id=x_contract,
        status="APPROVED",
        subject_content_sha256="a" * 64,
    )
    tables.add(
        approval_request,
        id=y_id,
        subject_type=kind.value,
        subject_id=y_contract,
        status="PENDING",
        subject_content_sha256="b" * 64,
    )
    resolver = LedgerResolver(ledger, PersistedReads(tables))
    assert resolver.pending_approval_id() == y_id
    assert resolver.subject_sha256() == "b" * 64  # Y's own, read back; never X's a×64
    assert resolver.pending_approvals() == ((y_id, "b" * 64),)
    (decided,) = adapt(
        Call(H["decide"], "ak-approver", {}, step(H["decide"], 4)), loaded.key, resolver
    )
    assert (decided["approval_request_id"], decided["subject_content_sha256"]) == (y_id, "b" * 64)
    # Without reads the ledger-only rule holds (RES-2): the digest is refused, never borrowed.
    with pytest.raises(UnresolvedHandle, match="seq 4 C-POS-012-Y"):
        LedgerResolver(ledger).subject_sha256()
    # The result's id must be the subject's pending request.
    other = FakeTables()
    other.add(
        approval_request,
        id=uid("other"),
        subject_type=kind.value,
        subject_id=y_contract,
        status="PENDING",
        subject_content_sha256="d" * 64,
    )
    with pytest.raises(UnresolvedHandle, match="names request"):
        LedgerResolver(ledger, PersistedReads(other)).pending_approvals()
    # A None-return submit (SSP) resolves its subject id from the ledger and reads its request.
    version_id = uid("ssp", "B", 1)
    ssp_version = next(s for s in steps if s.handler == H["ssp_version"])
    ssp_submit = next(s for s in steps if s.handler == H["ssp_submit"])
    ssp_ledger = [
        _entry(
            Call(H["ssp_version"], PREPARER, {"code": "B", "version": 1}, ssp_version), version_id
        ),
        _entry(Call(H["ssp_submit"], PREPARER, {"code": "B", "version": 1}, ssp_submit), None),
    ]
    ssp_tables = FakeTables()
    request = ssp_tables.add(
        approval_request,
        subject_type=ApprovalSubjectType.SSP_BOOK_VERSION.value,
        subject_id=version_id,
        status="PENDING",
        subject_content_sha256="e" * 64,
    )
    read = LedgerResolver(ssp_ledger, PersistedReads(ssp_tables))
    assert read.pending_approvals() == ((request["id"], "e" * 64),)
    with pytest.raises(UnresolvedHandle, match="submit_ssp_book_version"):
        LedgerResolver(ssp_ledger).pending_approval_id()


# --- READ-5: period state -------------------------------------------------------------------------


def test_period_state_is_placed_by_the_transaction_that_wrote_each_transition() -> None:
    """READ-5 as amended (dev-guide rev 1.246; the supervisor's ruling of 2026-10-01 on
    AK-CLOSE-RUN-STEP-1, (b)). A transition's ``created_at`` is the application clock's — here
    one business instant for both transitions, later than every cutoff, as it is when the plan's
    clock stands at an item's business time — and places nothing. A transition is at or before a
    checkpoint when the transaction that wrote it (``created_txid``) began before the horizon the
    runner read with the checkpoint's stamp. STALE EXPECTATION: the test compared ``created_at``
    and ``state_changed_at`` with ``known_at``, which answered every checkpoint of a runner
    world with the period's latest state."""
    tables = FakeTables()
    calendar = uid("calendar")
    entity = tables.add(legal_entity, code="US01", calendar_id=calendar)
    p01 = tables.add(period, calendar_id=calendar, period_key="FY2026-P01")
    business = T0 + timedelta(days=400)  # the application clock of both transitions
    state = tables.add(
        period_state,
        entity_id=entity["id"],
        book_code="ASC606",
        period_id=p01["id"],
        state="closed",
        state_changed_at=business,
    )
    tables.add(
        period_state_transition,
        period_state_id=state["id"],
        from_state="closing",
        to_state="closed",
        created_at=business,
        created_txid=130,
    )
    tables.add(
        period_state_transition,
        period_state_id=state["id"],
        from_state="open",
        to_state="closing",
        created_at=business,
        created_txid=120,
    )
    reads = PersistedReads(tables)

    def at(horizon: int | None, period_key: str = "FY2026-P01", entity_code: str = "US01") -> str:
        return reads.period_state(entity_code, "ASC606", period_key, T0, horizon)

    assert at(120) == "open"  # before the first change: the state it left
    assert at(121) == at(130) == "closing"  # the first transaction began before the horizon
    assert at(131) == "closed"
    # ``known_at`` decides nothing: every stamp of the rows is later than it, and no cutoff
    # however late moves the answer of one horizon.
    late = T0 + timedelta(days=4000)
    assert reads.period_state("US01", "ASC606", "FY2026-P01", late, 120) == "open"
    with pytest.raises(NotProvisioned, match="legal_entity"):
        at(131, entity_code="XX99")
    with pytest.raises(NotProvisioned, match="period rows"):
        at(131, period_key="FY2026-P09")
    # A platform that kept no horizon cannot place a transition: refused by name, never guessed.
    with pytest.raises(NotProvisioned, match="kept no transaction horizon") as unplaced:
        at(None)
    assert "rule READ-5 amended; dev-guide rev 1.246" in str(unplaced.value)
    assert "erev_api.domain.close.queries.period_view" in str(unplaced.value)
    # A state row with no transition: the product writes one with the row and with every change
    # (04 DB-07), so nothing places this one — its own stamp is the application clock's.
    p02 = tables.add(period, calendar_id=calendar, period_key="FY2026-P02")
    tables.add(
        period_state,
        entity_id=entity["id"],
        book_code="ASC606",
        period_id=p02["id"],
        state="open",
        state_changed_at=T0 - timedelta(days=1),
    )
    with pytest.raises(NotProvisioned, match="holds no transition") as bare:
        at(131, period_key="FY2026-P02")
    assert "04 DB-07" in str(bare.value)
    # Two transitions of one transaction keep the order they were written in.
    p03 = tables.add(period, calendar_id=calendar, period_key="FY2026-P03")
    third = tables.add(
        period_state, entity_id=entity["id"], book_code="ASC606", period_id=p03["id"], state="open"
    )
    for index, (before, after) in enumerate(((None, "future"), ("future", "open"))):
        tables.add(
            period_state_transition,
            id=uid("p03-transition", index),
            period_state_id=third["id"],
            from_state=before,
            to_state=after,
            created_at=business + timedelta(microseconds=index),
            created_txid=140,
        )
    assert at(141, period_key="FY2026-P03") == "open"
    with pytest.raises(NotProvisioned, match="names no from_state"):
        at(140, period_key="FY2026-P03")  # before the row existed


# --- READ-6: journal lines and report rows ------------------------------------------------------


def test_journal_lines_net_per_contract_account_and_currency() -> None:
    tables = FakeTables()
    run_id = uid("journal-run")
    c1 = tables.add(contract, external_id="C-1")
    batch = tables.add(journal_batch, journal_run_id=run_id)
    entry = tables.add(journal_entry, journal_batch_id=batch["id"])

    def line(account: str, debit: str, credit: str) -> None:
        tables.add(
            journal_line,
            journal_entry_id=entry["id"],
            gl_account_code=account,
            debit_txn=Decimal(debit),
            credit_txn=Decimal(credit),
            txn_currency="USD",
            contract_id=c1["id"],
        )

    line("4000", "100.00", "0"), line("4000", "0", "40.00"), line("1200", "0", "60.00")
    line("2400", "5.00", "5.00")  # a zero net is dropped
    reads = PersistedReads(tables)
    assert reads.journal_lines(run_id, per_contract=True) == (
        JournalLine("1200", Fraction(-60), "USD", "C-1"),
        JournalLine("4000", Fraction(60), "USD", "C-1"),
    )
    assert reads.journal_lines(run_id, per_contract=False) == (
        JournalLine("1200", Fraction(-60), "USD", None),
        JournalLine("4000", Fraction(60), "USD", None),
    )
    assert reads.journal_lines(uid("no-run"), per_contract=True) == ()


def test_the_journal_runs_of_a_period_are_read_oldest_first_and_the_books_last_seal() -> None:
    """Item AK-JOURNAL-RUN-PLAN-1: what the step of a journals block reads before it decides.
    ``journal_runs`` are the runs of one entity, book and period — the key of a run's coverage
    (04 DB-16) — the cancelled ones among them, oldest first: by creation, and the runs of one
    instant in the order of their numbers, a longer number being a later one, as the product
    orders them. ``sealed_to`` is the greatest ``chain_seq`` sealed in a book, 0 for none."""
    tables = FakeTables()
    calendar = uid("calendar")
    us = tables.add(legal_entity, code="US01", calendar_id=calendar)
    uk = tables.add(legal_entity, code="UK01", calendar_id=calendar)
    p01 = tables.add(period, calendar_id=calendar, period_key="FY2026-P01")
    p02 = tables.add(period, calendar_id=calendar, period_key="FY2026-P02")

    def run(number: str, at: datetime, **columns: Any) -> None:
        row = {
            "run_no": number,
            "created_at": at,
            "state": "draft",
            "entity_id": us["id"],
            "book_code": "ASC606",
            "period_id": p01["id"],
        }
        tables.add(journal_run, **{**row, **columns})

    later = T0 + timedelta(seconds=1)
    run("JR-999999", later)
    run("JR-000002", later, state="cancelled")
    run("JR-1000000", later)  # a seventh digit: after every six-digit number of its instant
    run("JR-000003", T0)
    run("JR-000004", T0, entity_id=uk["id"])  # another entity
    run("JR-000005", T0, book_code="IFRS15")  # another book
    run("JR-000006", T0, period_id=p02["id"])  # another period
    reads = PersistedReads(tables)
    found = reads.journal_runs("US01", "ASC606", "FY2026-P01")
    assert [(row["run_no"], row["state"]) for row in found] == [
        ("JR-000003", "draft"),
        ("JR-000002", "cancelled"),
        ("JR-999999", "draft"),
        ("JR-1000000", "draft"),
    ]
    assert [row["run_no"] for row in reads.journal_runs("UK01", "ASC606", "FY2026-P01")] == [
        "JR-000004"
    ]
    assert reads.journal_runs("US01", "ASC606", "FY2026-P02")[0]["run_no"] == "JR-000006"
    assert reads.journal_runs("UK01", "IFRS15", "FY2026-P02") == []
    with pytest.raises(NotProvisioned, match="0 legal_entity rows"):
        reads.journal_runs("XX01", "ASC606", "FY2026-P01")
    assert (reads.sealed_to("ASC606"), reads.sealed_to("LEGACY")) == (0, 0)
    for book, seq in (("ASC606", 2), ("ASC606", 7), ("ASC606", 3), ("LEGACY", 5)):
        tables.add(subledger_posting_seal, book_code=book, chain_seq=seq)
    assert (reads.sealed_to("ASC606"), reads.sealed_to("LEGACY")) == (7, 5)
    assert reads.sealed_to("IFRS15") == 0


def test_report_rows_come_from_the_runs_json_dataset() -> None:
    tables = FakeTables()
    file_id = uid("file")
    run = tables.add(report_run, output_file_id=file_id, status="SUCCEEDED")
    tables.files[file_id] = json.dumps(
        {"rows": [{"row_key": "total", "amount": "10.00", "currency": "USD"}], "row_count": 1}
    ).encode("utf-8")
    reads = PersistedReads(tables)
    assert reads.report_rows(run["id"], where="t") == [
        {"row_key": "total", "amount": "10.00", "currency": "USD"}
    ]
    failed = tables.add(report_run, output_file_id=None, status="FAILED", problem="boom")
    with pytest.raises(NotProvisioned, match="no output .*FAILED"):
        reads.report_rows(failed["id"], where="t")
    with pytest.raises(NotProvisioned, match="0 report_run rows"):
        reads.report_rows(uid("missing"), where="t")


# --- READ-4: fingerprint --------------------------------------------------------------------------


def test_fingerprint_is_deterministic_and_moves_with_the_rows() -> None:
    tables = FakeTables()
    reads = PersistedReads(tables)
    before = reads.fingerprint()
    assert before == reads.fingerprint() and len(before) == 64
    tables.add(audit_event, chain_seq=1)
    after = reads.fingerprint()
    assert after != before and after == reads.fingerprint()


# --- READ-1 / READ-2: the books from rows ---------------------------------------------------------


# The application clock of the fixture's postings: a business time far from every cutoff below.
# ``subledger.post`` stamps a posting with ``uow.now``, and the runner sets that clock to an
# item's business time, so the stamp places nothing at a server-time cutoff — and the reader
# does not read it.
BUSINESS_TIME = datetime(2031, 1, 31, 17, tzinfo=UTC)


def _post(
    tables: FakeTables,
    built: dict[str, Any],
    *,
    computation_id: UUID | None,
    book: str,
    amount: str = "60.50",
    kind: str = "ENGINE_COMPUTE",
    txid: int = 100,
    close_run_id: UUID | None = None,
    of_group: bool = True,
    contract_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One sealed posting with one balanced RECOGNITION entry: of the fixture's group, or — a
    close run's FX or reclass posting — of the entity, naming no group (``of_group`` false).
    ``txid`` is the transaction that wrote it (``created_txid``, the server's)."""
    posting = tables.add(
        subledger_posting,
        combination_group_id=built["group_id"] if of_group else None,
        contract_computation_id=computation_id,
        close_run_id=close_run_id,
        book_code=book,
        posting_kind=kind,
        created_at=BUSINESS_TIME,
        created_txid=txid,
    )
    for account, signed, side in (
        (built["receivable"], amount, "D"),
        (built["revenue"], f"-{amount}", "C"),
    ):
        tables.add(
            subledger_line,
            subledger_posting_id=posting["id"],
            entry_no=1,
            entry_kind="RECOGNITION",
            account_role="RECEIVABLE" if side == "D" else "REVENUE",
            clearing_purpose=None,
            gl_account_id=account["id"],
            entity_id=built["entity"]["id"],
            period_id=built["p01"]["id"],
            origin_period_id=None,
            txn_currency="USD",
            amount_txn=Decimal(signed),
            functional_currency="USD",
            amount_functional=Decimal(signed),
            dr_cr=side,
            contract_id=(contract_row or built["c1"])["id"],
            obligation_id=built["l1"]["id"] if contract_row is None else None,
            counterparty_entity_id=None,
            dimensions={"contract_key": "C-1"},
            reason_code=None,
            trace_node_id="n2",
        )
    return posting


def _computed(tables: FakeTables, built: dict[str, Any], *, known_at: datetime) -> dict[str, Any]:
    """A further computation of the fixture's group, known at ``known_at``, with its ASC606
    version and that version's (empty) trace — what a later event's computation leaves."""
    computation = tables.add(
        contract_computation,
        combination_group_id=built["group_id"],
        known_at=known_at,
        close_run_id=None,
        engine_version="0.3.0",
        input_sha256="9" * 64,
        status="SUCCEEDED",
    )
    version = tables.add(
        contract_version,
        combination_group_id=built["group_id"],
        contract_computation_id=computation["id"],
        book_code="ASC606",
        version_no=len(tables.tables[contract_version.name]) + 1,
        known_at=known_at,
        transaction_currency="USD",
        status_in_book="ACTIVE",
    )
    trace = Trace(format_version=1, engine_version="0.3.0", nodes=(), root_measures={})
    tables.add(
        calc_trace,
        contract_version_id=version["id"],
        format_version=1,
        engine_version="0.3.0",
        trace=trace_document(trace),
        root_measures={},
        trace_sha256=trace.sha256(),
    )
    return computation


def _group(tables: FakeTables, *, known_at: datetime) -> dict[str, Any]:
    """One booked contract C-1 (obligation L1) computed once: version, obligation, trace, postings
    for ASC606 and a LEGACY posting."""
    calendar = uid("calendar")
    entity = tables.add(legal_entity, code="US01", calendar_id=calendar, functional_currency="USD")
    p01 = tables.add(period, calendar_id=calendar, period_key="FY2026-P01")
    group_id = uid("group")
    tables.add(combination_group, id=group_id, code="CG-C-1")
    c1 = tables.add(contract, external_id="C-1", combination_group_id=group_id)
    tables.add(  # T-CON-04 history: a member since before the computation, still a member
        combination_group_member,
        combination_group_id=group_id,
        contract_id=c1["id"],
        valid_from_known_at=known_at - timedelta(days=1),
        valid_to_known_at=None,
    )
    l1 = tables.add(obligation, contract_id=c1["id"], obligation_key="L1")
    receivable = tables.add(gl_account, code="1200")
    revenue = tables.add(gl_account, code="4000")
    computation = tables.add(
        contract_computation,
        combination_group_id=group_id,
        known_at=known_at,  # the record time of its latest event (DB-08), as its versions carry it
        close_run_id=None,
        engine_version="0.3.0",
        input_sha256="f" * 64,
        status="SUCCEEDED",
    )
    version_money = sorted(money_columns(contract_version))
    obligation_money = sorted(money_columns(obligation_version))
    version = tables.add(
        contract_version,
        combination_group_id=group_id,
        contract_computation_id=computation["id"],
        book_code="ASC606",
        version_no=1,
        known_at=known_at,
        transaction_currency="USD",
        status_in_book="ACTIVE",
        modification_boundary_no=0,
        **{version_money[0]: Decimal("100.00")},
    )
    tables.add(
        obligation_version,
        contract_version_id=version["id"],
        contract_id=c1["id"],
        obligation_key="L1",
        satisfaction_status="PARTIAL",
        trace_nodes={"allocated_amount": "n1"},
        **{obligation_money[0]: Decimal("60.50")},
    )

    def balance_node(measure: str, period_key: str, value: str) -> TraceNode:
        return TraceNode(
            id=f"{measure}:C-1@US01:{period_key}",
            measure=measure,
            value=value,
            currency="USD",
            formula_id="bal.member.v1",
            inputs=(),
            params={"minor_unit": "2"},
            rounding_residue="0",
            narrative_key="bal.member",
        )

    trace = Trace(
        format_version=1,
        engine_version="0.3.0",
        nodes=(
            balance_node("contract_liability", "FY2026-P01", "120.00"),
            balance_node("contract_asset", "FY2026-P01", "0.00"),
            balance_node("unbilled_receivable", "FY2026-P01", "15.50"),
            balance_node("contract_liability", "FY2026-P02", "80.00"),
        ),
        root_measures={},
    )
    tables.add(
        contract_version_balance,
        contract_version_id=version["id"],
        contract_id=c1["id"],
        entity_id=entity["id"],
        book_code="ASC606",
        txn_currency="USD",
        functional_currency="USD",
        contract_liability_txn=Decimal("80.00"),  # T-CON-09: the latest period (P02), unnamed
    )
    tables.add(
        calc_trace,
        contract_version_id=version["id"],
        format_version=1,
        engine_version="0.3.0",
        trace=trace_document(trace),
        root_measures={},
        trace_sha256=trace.sha256(),
    )
    built = {
        "group_id": group_id,
        "computation": computation,
        "version": version,
        "version_money": version_money[0],
        "obligation_money": obligation_money[0],
        "entity": entity,
        "p01": p01,
        "c1": c1,
        "l1": l1,
        "receivable": receivable,
        "revenue": revenue,
    }
    for book in ("ASC606", "LEGACY"):
        _post(tables, built, computation_id=computation["id"], book=book)
    return built


def test_output_bundle_rebuilds_the_books_from_rows_as_of_known_at() -> None:
    tables = FakeTables()
    built = _group(tables, known_at=T0)
    reads = PersistedReads(tables)
    where = "checkpoint t"
    output = reads.output_bundle(
        group_id=built["group_id"],
        group_key="CG-C-1",
        members=("C-1",),
        books=("ASC606", "LEGACY"),
        known_at=T0 + timedelta(seconds=1),
        where=where,
    )
    assert output.engine_version == "0.3.0" and output.input_sha256 == "f" * 64
    asc, legacy = output.books
    assert asc.book_code == "ASC606" and asc.contract_version is not None
    columns = asc.contract_version.columns
    assert columns[built["version_money"]] == 10000  # NUMERIC 100.00 → int minor units (XR-03)
    assert columns["modification_boundary_no"] == 0
    assert "combination_group_id" not in columns and "tenant_id" not in columns
    assert asc.status_in_book == (("C-1", "ACTIVE"),)
    (l1,) = asc.obligation_versions
    assert l1.subject_key == obligation_subject_key("C-1", "L1")
    assert l1.columns[built["obligation_money"]] == 6050 and l1.trace_nodes == {
        "allocated_amount": "n1"
    }
    assert asc.trace.engine_version == "0.3.0" and len(asc.trace.nodes) == 4
    (intent,) = asc.posting_intents
    assert (intent.entity, intent.posting_period_key, intent.entry_kind) == (
        "US01",
        "FY2026-P01",
        "RECOGNITION",
    )
    assert intent.subject_key == obligation_subject_key("C-1", "L1")
    assert intent.posting_class == NOT_PERSISTED
    sides = sorted((line.side, line.account_code, line.amount_txn) for line in intent.lines)
    assert sides == [("C", "4000", 6050), ("D", "1200", 6050)]
    assert all(line.dimensions == {"contract_key": "C-1"} for line in intent.lines)
    assert legacy.contract_version is None and legacy.trace.nodes == ()
    # READ-2 (amended): balances from the member-balance trace nodes, per (subject, period).
    by_period = {balance.period_key: balance for balance in asc.balances}
    assert set(by_period) == {"FY2026-P01", "FY2026-P02"}
    p01 = by_period["FY2026-P01"]
    assert p01.subject_key == "C-1@US01"
    assert (p01.columns["contract_liability_txn"], p01.columns["unbilled_receivable_txn"]) == (
        12000,
        1550,
    )
    assert p01.columns["contract_asset_txn"] == 0 and p01.columns["refund_liability_txn"] == 0
    assert p01.columns["contract_liability_functional"] == 12000  # USD entity: same currency
    assert p01.columns["entity"] == "US01" and p01.trace_nodes["contract_liability"].startswith(
        "contract_liability:C-1@US01:"
    )
    assert by_period["FY2026-P02"].columns["contract_liability_txn"] == 8000
    assert len(legacy.posting_intents) == 1 and legacy.status_in_book == ()
    # READ-1: a known_at before the version's commit finds no version; a later version of another
    # computation does not replace the as-of one.
    with pytest.raises(NotProvisioned, match="no contract version"):
        reads.output_bundle(
            group_id=built["group_id"],
            group_key="CG-C-1",
            members=("C-1",),
            books=("ASC606",),
            known_at=T0 - timedelta(seconds=1),
            where=where,
        )
    later = _computed(tables, built, known_at=T0 + timedelta(days=1))
    _post(tables, built, computation_id=later["id"], book="ASC606", amount="9.00")
    again = reads.output_bundle(
        group_id=built["group_id"],
        group_key="CG-C-1",
        members=("C-1",),
        books=("ASC606",),
        known_at=T0 + timedelta(hours=1),
        where=where,
    )
    assert again.input_sha256 == "f" * 64  # version 1's computation, not the later one
    assert len(again.books[0].posting_intents) == 1  # nor the later computation's posting


def test_the_subledger_is_the_groups_postings_of_every_computation_through_the_cutoff() -> None:
    """READ-2 as amended (dev-guide rev 1.219). The product posts each computation's increments,
    so a checkpoint's ledger is the posting of every computation of the group known at or before
    its cutoff — not the as-of computation's alone, and none that came after. A posting is
    placed by its computation's ``known_at``; its own stamps are the application clock's (here a
    business time years after every cutoff) and place nothing."""
    tables = FakeTables()
    built = _group(tables, known_at=T0)
    reads = PersistedReads(tables)
    second = _computed(tables, built, known_at=T0 + timedelta(hours=1))
    increment = _post(tables, built, computation_id=second["id"], book="ASC606", amount="9.00")
    third = _computed(tables, built, known_at=T0 + timedelta(hours=2))  # posts nothing itself

    def intents(at: datetime, book: str = "ASC606") -> list[tuple[str, int]]:
        output = reads.output_bundle(
            group_id=built["group_id"],
            group_key="CG-C-1",
            members=("C-1",),
            books=("ASC606", "LEGACY"),
            known_at=at,
            where="checkpoint t",
        )
        (found,) = (item for item in output.books if item.book_code == book)
        return [
            (intent.entry_key, sum(line.amount_txn for line in intent.lines if line.side == "D"))
            for intent in found.posting_intents
        ]

    first_posting = tables.table_rows(
        subledger_posting, contract_computation_id=built["computation"]["id"], book_code="ASC606"
    )[0]
    first_key = f"ENGINE_COMPUTE:{first_posting['id']}:1"
    increment_key = f"ENGINE_COMPUTE:{increment['id']}:1"
    assert BUSINESS_TIME > T0 + timedelta(days=365)  # no cutoff below reaches the postings' stamp
    assert intents(T0 + timedelta(seconds=1)) == [(first_key, 6050)]
    # At the second computation's cutoff: both postings, in the computations' order, each entry
    # under its own key although both are entry 1 of a posting of the same kind.
    assert intents(T0 + timedelta(hours=1)) == [(first_key, 6050), (increment_key, 900)]
    # The as-of computation is the third, which posted nothing: its checkpoint still holds both.
    after_third = reads.output_bundle(
        group_id=built["group_id"],
        group_key="CG-C-1",
        members=("C-1",),
        books=("ASC606",),
        known_at=T0 + timedelta(hours=3),
        where="checkpoint t",
    )
    assert after_third.input_sha256 == "9" * 64
    assert tables.table_rows(subledger_posting, contract_computation_id=third["id"]) == []
    assert intents(T0 + timedelta(hours=3)) == [(first_key, 6050), (increment_key, 900)]
    # The LEGACY book likewise holds its own postings and no other book's.
    assert [amount for _, amount in intents(T0 + timedelta(hours=3), "LEGACY")] == [6050]


def test_without_a_horizon_a_posting_no_events_computation_wrote_is_refused_by_name() -> None:
    """A platform that kept no transaction horizon cannot place the pass of a close run or a
    manual adjustment at a checkpoint (dev-guide rev 1.246): a posting of the group that names
    no computation, and one whose computation a close run ran, refuse the read by name. A
    posting whose computation is known only after the cutoff is later whatever wrote it, and is
    left out. STALE EXPECTATION: the refusal named item AK-CLOSE-RUN-STEP-1, which has since
    given the read its horizon (the next test)."""
    tables = FakeTables()
    built = _group(tables, known_at=T0)
    reads = PersistedReads(tables)
    common = {
        "group_id": built["group_id"],
        "group_key": "CG-C-1",
        "members": ("C-1",),
        "books": ("ASC606",),
        "where": "checkpoint t",
    }
    cutoff = T0 + timedelta(seconds=1)
    pass_computation = tables.add(
        contract_computation,
        combination_group_id=built["group_id"],
        known_at=T0 + timedelta(hours=1),
        close_run_id=uid("close-run"),
        engine_version="0.3.0",
        input_sha256="8" * 64,
        status="SUCCEEDED",
    )
    of_pass = _post(
        tables, built, computation_id=pass_computation["id"], book="ASC606", kind="CLOSE_RUN"
    )
    (asc,) = reads.output_bundle(**common, known_at=cutoff).books
    assert len(asc.posting_intents) == 1  # known after the cutoff: left out, not refused
    tables.tables[contract_computation.name][-1]["known_at"] = T0  # no event since: known by then
    with pytest.raises(NotProvisioned, match="kept no transaction horizon") as refused:
        reads.output_bundle(**common, known_at=cutoff)
    assert f"posting {of_pass['id']} (CLOSE_RUN) of book ASC606" in str(refused.value)
    assert "rule READ-2 amended; dev-guide rev 1.246" in str(refused.value)
    assert "erev_api.domain.journals.subledger.list_lines" in str(refused.value)
    tables.tables[subledger_posting.name].pop()
    adjustment = _post(tables, built, computation_id=None, book="ASC606", kind="MANUAL_ADJUSTMENT")
    with pytest.raises(
        NotProvisioned, match="is not the posting of an event's computation"
    ) as bare:
        reads.output_bundle(**common, known_at=cutoff)
    assert f"posting {adjustment['id']} (MANUAL_ADJUSTMENT)" in str(bare.value)


def test_a_close_runs_posting_is_placed_by_the_transaction_that_wrote_it() -> None:
    """READ-2 as amended by dev-guide rev 1.246 (item AK-CLOSE-RUN-STEP-1; the supervisor's
    ruling of 2026-10-01, (b)). A posting no event's computation wrote carries the application
    clock's stamps only — here ``BUSINESS_TIME``, years after every cutoff. It is at or before a
    checkpoint when the transaction that wrote it (``created_txid``) began before the horizon the
    runner read with the checkpoint's stamp: a close run's release posting of the group, its
    reclass posting of the entity — which names no group, and of which the group takes the
    entries whose lines name one of its contracts — and a manual adjustment alike."""
    tables = FakeTables()
    built = _group(tables, known_at=T0)
    reads = PersistedReads(tables)
    run = uid("close-run")
    other = tables.add(contract, external_id="C-9", combination_group_id=uid("other-group"))
    release = _post(
        tables,
        built,
        computation_id=None,
        book="ASC606",
        amount="7.00",
        kind="CLOSE_RELEASE",
        txid=210,
        close_run_id=run,
    )
    reclass = _post(
        tables,
        built,
        computation_id=None,
        book="ASC606",
        amount="30.00",
        kind="NETTING_RECLASS",
        txid=211,
        close_run_id=run,
        of_group=False,
    )
    # the same entity posting holds another group's entry: entry 2, of contract C-9
    for account, signed, side in (
        (built["receivable"], "5.00", "D"),
        (built["revenue"], "-5.00", "C"),
    ):
        tables.add(
            subledger_line,
            subledger_posting_id=reclass["id"],
            entry_no=2,
            entry_kind="NETTING_RECLASS",
            account_role="RECEIVABLE" if side == "D" else "REVENUE",
            clearing_purpose=None,
            gl_account_id=account["id"],
            entity_id=built["entity"]["id"],
            period_id=built["p01"]["id"],
            origin_period_id=None,
            txn_currency="USD",
            amount_txn=Decimal(signed),
            functional_currency="USD",
            amount_functional=Decimal(signed),
            dr_cr=side,
            contract_id=other["id"],
            obligation_id=None,
            counterparty_entity_id=None,
            dimensions={},
            reason_code=None,
            trace_node_id=None,
        )
    adjustment = _post(
        tables,
        built,
        computation_id=None,
        book="ASC606",
        amount="2.00",
        kind="MANUAL_ADJUSTMENT",
        txid=230,
    )

    def debits(horizon: int | None) -> list[tuple[str, int]]:
        (asc,) = reads.output_bundle(
            group_id=built["group_id"],
            group_key="CG-C-1",
            members=("C-1",),
            books=("ASC606",),
            known_at=T0 + timedelta(seconds=1),
            where="checkpoint t",
            horizon=horizon,
        ).books
        return [
            (intent.entry_key, sum(line.amount_txn for line in intent.lines if line.side == "D"))
            for intent in asc.posting_intents
        ]

    first = tables.table_rows(
        subledger_posting, contract_computation_id=built["computation"]["id"], book_code="ASC606"
    )[0]
    computed = (f"ENGINE_COMPUTE:{first['id']}:1", 6050)
    released = (f"CLOSE_RELEASE:{release['id']}:1", 700)
    reclassed = (f"NETTING_RECLASS:{reclass['id']}:1", 3000)
    adjusted = (f"MANUAL_ADJUSTMENT:{adjustment['id']}:1", 200)
    assert BUSINESS_TIME > T0 + timedelta(days=365)  # no stamp of a posting reaches the cutoff
    # Before the close run's transactions: the computation's posting alone.
    assert debits(210) == [computed]
    # The horizon is the first transaction not yet begun: 210 is before 211, not before 210.
    assert debits(211) == [computed, released]
    # After the run: its release of the group and the group's entry of the entity's reclass —
    # entry 2 is another group's and is left out.
    assert debits(212) == debits(230) == [computed, released, reclassed]
    assert debits(231) == [computed, released, reclassed, adjusted]
    # Without a horizon none of the three is placed: refused by name.
    with pytest.raises(NotProvisioned, match="kept no transaction horizon"):
        debits(None)
    # A posting of neither a group nor a close run says nothing of whose lines it holds.
    stray = _post(
        tables,
        built,
        computation_id=None,
        book="ASC606",
        kind="MANUAL_ADJUSTMENT",
        txid=240,
        of_group=False,
    )
    with pytest.raises(NotProvisioned, match="names no group and no close run") as nobody:
        debits(300)
    assert f"posting {stray['id']} (MANUAL_ADJUSTMENT) of book ASC606" in str(nobody.value)


def _node(node_id: str, *inputs: str) -> TraceNode:
    measure = node_id.partition(":")[0].partition("@")[0]
    return TraceNode(
        id=node_id,
        measure=measure,
        value="1.00",
        currency="USD",
        formula_id="f.v1",
        inputs=inputs,
        params={"minor_unit": "2"},
        rounding_residue="0",
        narrative_key="n",
    )


def test_the_trace_names_the_group_as_the_key_names_it() -> None:
    """READ-2 as amended (dev-guide rev 1.219): the product numbers its groups (``CG-CON-000001``)
    and the comparison knows the key's group name only. The reader hands the trace over under
    that name: every node whose subject is the group — itself, ``<group>@<entity>`` or
    ``<group>@<entity>/<KIND>/<source>`` — is renamed in its id, among the inputs of every node
    and in the root measures; a member's, an obligation's and another group's nodes keep their
    names, and no value moves."""
    group_ids = [
        "transaction_price:CG-CON-000001:FY2026-P01",
        "contract_liability:CG-CON-000001@US01:FY2026-P01",
        "refund_liability:CG-CON-000001@US01/RETURN/C-1/L1:FY2026-P01",
        "allocated_amount@C-1/EV-000002:CG-CON-000001:FY2026-P01",
    ]
    other_ids = [
        "contract_liability:C-1@US01:FY2026-P01",  # a member
        "allocated_amount:C-1/L1:FY2026-P01",  # an obligation
        "transaction_price:CG-CON-0000012:FY2026-P01",  # another group whose code starts alike
        "revenue@CG-CON-000001/EV-000001:C-1/L1:FY2026-P01",  # the code in an event key only
    ]
    trace = Trace(
        format_version=1,
        engine_version="0.3.0",
        nodes=tuple(
            sorted(
                [
                    *(_node(node_id) for node_id in group_ids[1:]),
                    _node(group_ids[0], group_ids[1], other_ids[0]),
                    *(_node(node_id, group_ids[0]) for node_id in other_ids),
                ],
                key=lambda node: node.id,
            )
        ),
        root_measures={"transaction_price": group_ids[0], "member": other_ids[0]},
    )
    named = under_group_name(trace, "CG-CON-000001", "CG-C-1")
    renamed = [
        "transaction_price:CG-C-1:FY2026-P01",
        "contract_liability:CG-C-1@US01:FY2026-P01",
        "refund_liability:CG-C-1@US01/RETURN/C-1/L1:FY2026-P01",
        "allocated_amount@C-1/EV-000002:CG-C-1:FY2026-P01",
    ]
    assert sorted(node.id for node in named.nodes) == sorted([*renamed, *other_ids])
    assert [node.id for node in named.nodes] == sorted(node.id for node in named.nodes)
    by_id = {node.id: node for node in named.nodes}
    assert by_id[renamed[0]].inputs == (renamed[1], other_ids[0])
    assert all(by_id[node_id].inputs == (renamed[0],) for node_id in other_ids)
    assert dict(named.root_measures) == {"transaction_price": renamed[0], "member": other_ids[0]}
    now_named = {**dict(zip(group_ids, renamed, strict=True)), **{i: i for i in other_ids}}
    before = {now_named[node.id]: node for node in trace.nodes}
    for node_id, node in by_id.items():
        was = before[node_id]
        assert (node.measure, node.value, node.currency, node.formula_id, dict(node.params)) == (
            was.measure,
            was.value,
            was.currency,
            was.formula_id,
            dict(was.params),
        )
    assert under_group_name(trace, "CG-C-1", "CG-C-1") is trace  # the same name: nothing to do
    # A name that holds a separator is renamed in its CV-21 encoded form, on both sides.
    encoded = Trace(
        format_version=1,
        engine_version="0.3.0",
        nodes=(_node("transaction_price:CG%3AONE:FY2026-P01"),),
        root_measures={},
    )
    assert [node.id for node in under_group_name(encoded, "CG:ONE", "KEY/GROUP").nodes] == [
        "transaction_price:KEY%2FGROUP:FY2026-P01"
    ]


def test_the_books_name_the_group_as_the_key_names_it() -> None:
    """The persisted group is still found by its own code (READ2-R2: a plan that names another
    code refuses); what the comparison receives carries the key's name — the contract version's
    subject and the group nodes of the trace — and the member rows are untouched."""
    tables = FakeTables()
    built = _group(tables, known_at=T0)
    (row,) = tables.tables[calc_trace.name]
    trace = Trace(
        format_version=1,
        engine_version="0.3.0",
        nodes=(
            _node("contract_liability:C-1@US01:FY2026-P01"),
            _node(
                "contract_liability:CG-C-1@US01:FY2026-P01",
                "contract_liability:C-1@US01:FY2026-P01",
            ),
            _node("transaction_price:CG-C-1:FY2026-P01"),
        ),
        root_measures={"transaction_price": "transaction_price:CG-C-1:FY2026-P01"},
    )
    row.update(
        trace=trace_document(trace),
        root_measures=dict(trace.root_measures),
        trace_sha256=trace.sha256(),
    )
    tables.tables[contract_version_balance.name].clear()
    reads = PersistedReads(tables)
    common = {
        "group_id": built["group_id"],
        "members": ("C-1",),
        "books": ("ASC606",),
        "known_at": T0 + timedelta(seconds=1),
        "where": "checkpoint t",
    }
    (as_stored,) = reads.output_bundle(**common, group_key="CG-C-1").books
    assert as_stored.contract_version is not None
    assert as_stored.contract_version.subject_key == "CG-C-1"
    assert as_stored.trace == trace
    (named,) = reads.output_bundle(**common, group_key="CG-C-1", named_group="KEY GROUP 1").books
    assert named.contract_version is not None
    assert named.contract_version.subject_key == "KEY GROUP 1"
    assert [node.id for node in named.trace.nodes] == [
        "contract_liability:C-1@US01:FY2026-P01",
        "contract_liability:KEY GROUP 1@US01:FY2026-P01",
        "transaction_price:KEY GROUP 1:FY2026-P01",
    ]
    assert named.trace.nodes[1].inputs == ("contract_liability:C-1@US01:FY2026-P01",)
    assert dict(named.trace.root_measures) == {
        "transaction_price": "transaction_price:KEY GROUP 1:FY2026-P01"
    }
    # the group's own row never becomes a member row, under either name
    assert [balance.subject_key for balance in named.balances] == ["C-1@US01"]
    assert [balance.subject_key for balance in as_stored.balances] == ["C-1@US01"]
    with pytest.raises(NotProvisioned, match="persisted group code is 'CG-C-1'"):
        reads.output_bundle(**common, group_key="KEY GROUP 1", named_group="KEY GROUP 1")


def test_an_obligation_is_handed_its_entity_codes_back() -> None:
    """The engine names an obligation's entities by code and the row keeps their ids; the reader
    reads the codes back through the entity rows (layer 11). Without ``performing_entity_code``
    the comparison cannot find the obligation's period at a checkpoint's as-of date."""
    tables = FakeTables()
    built = _group(tables, known_at=T0)
    other = tables.add(
        legal_entity, code="DE01", calendar_id=uid("calendar"), functional_currency="EUR"
    )
    (row,) = tables.tables[obligation_version.name]
    row.update(performing_entity_id=other["id"], contracting_entity_id=built["entity"]["id"])
    (asc,) = (
        PersistedReads(tables)
        .output_bundle(
            group_id=built["group_id"],
            group_key="CG-C-1",
            members=("C-1",),
            books=("ASC606",),
            known_at=T0 + timedelta(seconds=1),
            where="checkpoint t",
        )
        .books
    )
    (l1,) = asc.obligation_versions
    assert (l1.columns["performing_entity_code"], l1.columns["contracting_entity_code"]) == (
        "DE01",
        "US01",
    )
    assert l1.columns["performing_entity_id"] == other["id"]  # the row's own members stay


def test_a_judgement_records_approval_is_read_from_its_request() -> None:
    """READ-3 for a judgement record (layer 4: the runner's Step 1 record and distinct reviews).
    The digest a decision states is the request's — the subject content of a record that names a
    contract also holds the contract's group and stream head (04 §16.10 rev 1.49) — never the
    ``content_sha256`` the submission's result carries. And an approval states the digest of the
    impact preview its request shows, when it shows one (REQ-PLT-015)."""
    loaded = load_platform_key(POS_012)
    steps = plan(loaded).steps
    create = next(s for s in steps if s.handler == H["judgement"])
    submit = next(s for s in steps if s.handler == H["judgement_submit"])
    review = next(s for s in steps if s.handler == H["distinct_review"])
    decide = next(s for s in steps if s.handler == H["decide"] and s.phase == "CONTRACTS")
    record_id, request_id = uid("record"), uid("request")
    kwargs = {"contract": "C-POS-012-X", "handle": "ak-step1"}
    ledger = [
        _entry(Call(H["judgement"], PREPARER, kwargs, create), SimpleNamespace(id=record_id)),
        _entry(
            Call(H["judgement_submit"], PREPARER, kwargs, submit),
            SimpleNamespace(id=record_id, approval_request_id=request_id, content_sha256="d" * 64),
        ),
    ]
    tables = FakeTables()
    tables.add(
        approval_request,
        id=request_id,
        subject_type=ApprovalSubjectType.JUDGEMENT_RECORD.value,
        subject_id=record_id,
        status="PENDING",
        subject_content_sha256="e" * 64,
        impact_preview_sha256=None,
    )
    resolver = LedgerResolver(ledger, PersistedReads(tables))
    assert resolver.pending_approvals() == ((request_id, "e" * 64),)  # the request's, not d×64
    (decided,) = adapt(Call(H["decide"], "ak-approver", {}, decide), loaded.key, resolver)
    assert (decided["subject_content_sha256"], decided["impact_preview_sha256"]) == ("e" * 64, None)
    # A distinct review makes and submits its record at once: the subject is the record its own
    # result names.
    reviewed_id, review_request = uid("reviewed"), uid("review-request")
    review_kwargs = {"contract": "C-POS-012-X", "obligation_key": "X1-LICENCE"}
    ledger.append(
        _entry(
            Call(H["distinct_review"], PREPARER, review_kwargs, review),
            SimpleNamespace(judgement_record_id=reviewed_id, approval_request_id=review_request),
        )
    )
    tables.add(
        approval_request,
        id=review_request,
        subject_type=ApprovalSubjectType.JUDGEMENT_RECORD.value,
        subject_id=reviewed_id,
        status="PENDING",
        subject_content_sha256="f" * 64,
        impact_preview_sha256="9" * 64,
    )
    assert resolver.pending_approvals() == ((review_request, "f" * 64),)
    (decided,) = adapt(Call(H["decide"], "ak-approver", {}, decide), loaded.key, resolver)
    assert decided["approval_request_id"] == review_request
    assert decided["impact_preview_sha256"] == "9" * 64  # the preview the request shows
    assert PersistedReads(tables).impact_preview_sha256(request_id) is None
    with pytest.raises(NotProvisioned, match="0 approval_request rows"):
        PersistedReads(tables).impact_preview_sha256(uid("no-request"))
    assert LedgerResolver(ledger).impact_preview_sha256(review_request) is None  # no reads: none


# --- the adapter over the reads -----------------------------------------------------------------


class _Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


class _JournalRuns(RecordingInvoker):
    """The recording invoker, answering the step of a journals block as the database
    invoker does: the run it made and that run's lines — here one line that names the
    block, so that a read can be told from the read of another block."""

    def __call__(self, call: Call) -> object:
        super().__call__(call)
        if call.step.phase != JOURNAL:
            return None
        line = JournalLine(call.step.subject, Fraction(1), "USD", None)
        return JournalAnswer(uid("run", call.step.subject), False, (), (line,))


def _ran(key_id: str, **extra: Any) -> WorkspaceAdapter:
    loaded = load_platform_key(key_id)
    adapter = WorkspaceAdapter(
        loaded,
        invoker=extra.pop("invoker", None) or RecordingInvoker(),
        clock=_Clock(),
        fingerprint=lambda: "mock-fixture",
        **extra,
    )
    for step in plan(loaded).steps:
        if step.phase in ("CHECKPOINT", "RUNNER") or step.gap is not None:
            continue
        adapter.run(step)
    return adapter


def test_adapter_reads_refuse_by_name_without_reads_or_stamps() -> None:
    loaded = load_platform_key(DLT)
    checkpoint = loaded.key.checkpoints[0]
    bare = WorkspaceAdapter(loaded)
    with pytest.raises(NotProvisioned, match="no persisted reads"):
        bare.checkpoint_run(checkpoint)
    with pytest.raises(NotProvisioned, match="no persisted reads"):
        bare.period_state("ME1", "ASC606", "FY2023-P01", T0)
    assert checkpoint.journals is not None
    # A journals block is read from what its step of the plan kept (item
    # AK-JOURNAL-RUN-PLAN-1): with no step run there is nothing to read, whatever reads the
    # adapter has. STALE EXPECTATION: until that item the read made the run and asked for
    # the persisted reads first ("no persisted reads").
    with pytest.raises(NotProvisioned, match="journal run after seq 13 did not run"):
        bare.journal_run(checkpoint, checkpoint.journals[0])
    unrun = WorkspaceAdapter(loaded, reads=PersistedReads(FakeTables()), jobs=FakeJobs())
    with pytest.raises(NotProvisioned, match="known_at of seq 13 is not in the ledger"):
        unrun.checkpoint_run(checkpoint)  # READ-1: the item never executed
    pos = load_platform_key(POS_012)
    with_balances = WorkspaceAdapter(pos, reads=PersistedReads(FakeTables()))
    with pytest.raises(NotProvisioned, match="known_at of seq 9 is not in the ledger"):
        with_balances.checkpoint_run(pos.key.checkpoints[0])  # READ-1 first; balances read after


def test_adapter_routes_the_reads_through_the_ledger_stamps_and_the_job_runner() -> None:
    jobs = FakeJobs()
    tables = FakeTables()
    adapter = _ran(DLT, reads=PersistedReads(tables), jobs=jobs, invoker=_JournalRuns())
    checkpoint = adapter.key.checkpoints[0]
    stamp = adapter.known_at_of(int(checkpoint.after_seq), "t")
    # Item 13 is stamped by its own step and again by the close run the plan runs after it:
    # the checkpoint reads at the later stamp (dev-guide rev 1.246, ruling (a) of 2026-10-01).
    stamped = [e for e in adapter.ledger if e.call.step.seq == 13 and e.known_at is not None]
    assert [e.call.step.phase for e in stamped] == ["TIMELINE", "CLOSE"]
    assert stamp == stamped[1].known_at and stamped[1].known_at > stamped[0].known_at
    # checkpoint_run reaches the group id, which the None results of the recording invoker
    # cannot supply: refused by name (RES-1), no invented id.
    with pytest.raises(UnresolvedHandle, match="group"):
        adapter.checkpoint_run(checkpoint)
    assert checkpoint.journals is not None
    # Item AK-JOURNAL-RUN-PLAN-1: each journals block is answered with the lines its own
    # step of the plan kept in the ledger — the four steps follow the close run of item 13
    # — and the read makes no run: the job runner is not asked. STALE EXPECTATION: until
    # that item the read created the run through the job runner, at the checkpoint's stamp.
    made = [e.call.step.subject for e in adapter.ledger if e.call.step.phase == JOURNAL]
    assert made == [
        "journals ME1 FY2023-P01 GROSS",
        "journals ME1 FY2023-P01 DELTA",
        "journals ME2 FY2023-P01 GROSS",
        "journals ME2 FY2023-P01 DELTA",
    ]
    for block, subject in zip(checkpoint.journals, made, strict=True):
        assert adapter.journal_run(checkpoint, block) == (
            JournalLine(subject, Fraction(1), "USD", None),
        )
    assert jobs.calls == []
    # A step that ran and kept no run (the plain recording invoker answers None) is not a
    # block answered with nothing: refused by name. And a block of another checkpoint's
    # name has no step.
    kept_nothing = _ran(DLT, reads=PersistedReads(tables), jobs=jobs)
    with pytest.raises(NotProvisioned, match="ran and kept no journal run"):
        kept_nothing.journal_run(checkpoint, checkpoint.journals[0])
    elsewhere = checkpoint.model_copy(update={"name": "another-checkpoint"})
    with pytest.raises(NotProvisioned, match="journal run after seq 13 did not run"):
        adapter.journal_run(elsewhere, checkpoint.journals[0])
    ex42 = _ran(EX42, reads=PersistedReads(tables), jobs=jobs)
    rpo = ex42.key.checkpoints[0]
    assert rpo.reports is not None
    file_id = uid("rpo-file")
    tables.add(report_run, id=jobs.run_id, output_file_id=file_id, status="SUCCEEDED")
    tables.files[file_id] = json.dumps(
        {"rows": [{"row_key": "band:12", "amount": "1.00"}]}
    ).encode()
    rows = ex42.report_rows(rpo, rpo.reports[0])
    assert rows == [{"row_key": "band:12", "amount": "1.00"}]
    assert jobs.calls[-1][0] == "report" and jobs.calls[-1][2] == ex42.known_at_of(13, "t")
    pos = _ran(POS_117, reads=PersistedReads(tables), jobs=jobs)
    aging = pos.key.checkpoints[0]
    assert aging.reports is not None
    assert pos.report_rows(aging, aging.reports[0]) == rows
    assert jobs.calls[-1][0] == "report"


class _Horizon:
    """A server whose every read of the transaction horizon finds ten more transactions begun."""

    def __init__(self) -> None:
        self.next = 1000

    def __call__(self) -> int:
        self.next += 10
        return self.next


class _PeriodReads:
    """The reads as the adapter asks them for a period's state: what it was handed."""

    def __init__(self) -> None:
        self.asked: list[tuple[object, ...]] = []

    def period_state(self, *asked: object) -> str:
        self.asked.append(asked)
        return "open"


def test_the_ledger_keeps_the_transaction_horizon_beside_the_clock() -> None:
    """Dev-guide rev 1.246, ruling (b): what the product stamps with the application clock is
    placed by the transaction that wrote it, against the horizon the runner read with the
    checkpoint's stamp. The ledger keeps that horizon with every entry, read after the clock;
    the checkpoint's is the one read with its stamp — after its close run — and the reads are
    handed it. An adapter without the read keeps none, and says so by handing over None."""
    reads = _PeriodReads()
    adapter = _ran(POS_012, reads=reads, horizon=_Horizon())
    horizons = [entry.horizon for entry in adapter.ledger]
    assert horizons == [1000 + 10 * count for count in range(1, len(adapter.ledger) + 1)]
    stamped = [e for e in adapter.ledger if e.call.step.seq == 9 and e.known_at is not None]
    assert [e.call.step.phase for e in stamped] == ["TIMELINE", "CLOSE"]
    own, closed = stamped
    assert closed.horizon is not None and own.horizon is not None
    assert closed.horizon > own.horizon
    cutoff = adapter.known_at_of(9, "t")
    assert cutoff == closed.known_at
    assert adapter.horizon_at(cutoff) == closed.horizon  # after the close run
    assert adapter.horizon_at(own.known_at) == own.horizon  # the item's own: before the run
    assert adapter.horizon_at(T0 - timedelta(days=1)) is None  # no stamp, no horizon
    assert adapter.period_state("US01", "ASC606", "FY2026-P01", cutoff) == "open"
    assert reads.asked == [("US01", "ASC606", "FY2026-P01", cutoff, closed.horizon)]
    bare = _ran(POS_012, reads=_PeriodReads())
    assert {entry.horizon for entry in bare.ledger} == {None}
    assert bare.horizon_at(bare.known_at_of(9, "t")) is None


def test_for_database_wires_reads_jobs_and_the_row_fingerprint() -> None:
    class _NoDatabase:
        clock = None
        keyring = None
        files = None
        tenant_id = uid("tenant")

        def uow(self, principal=None):  # noqa: ANN001, ANN201
            raise NotProvisioned("workspace unit of work", "support.factories.Workspace.uow")

        def rows(self, statement):  # noqa: ANN001, ANN201
            raise NotProvisioned("workspace rows", "support.factories.Workspace.rows")

    loaded = load_platform_key(POS_012)
    adapter = WorkspaceAdapter.for_database(loaded, _NoDatabase())
    assert isinstance(adapter.reads, PersistedReads)
    assert isinstance(adapter.reads.source, WorkspaceRows)
    assert isinstance(adapter.jobs, WorkspaceJobs)
    assert adapter.fingerprint == adapter.reads.fingerprint  # READ-4: a read, not a constant
    with pytest.raises(NotProvisioned, match="workspace rows"):
        adapter.fingerprint()
    assert loaded.key.checkpoints[0].subledger is not None
    # ACT-1 for the run the job collaborator starts: a report run (a journals block's run is
    # a step of the plan since item AK-JOURNAL-RUN-PLAN-1, proven by the invoker).
    with pytest.raises(NotProvisioned, match="Workspace.uow\\(None\\) is never used"):
        WorkspaceJobs(_NoDatabase(), {}).report_run(
            SimpleNamespace(report_code="disaggregation", parameters={}), T0
        )


# --- READ-7: roles and period-state ids ---------------------------------------------------------


def test_roles_and_period_state_ids_are_read_from_rows_when_no_result_carries_them() -> None:
    tables = FakeTables()
    controller = tables.add(role, code="controller")
    calendar = uid("calendar")
    entity = tables.add(legal_entity, code="US01", calendar_id=calendar)
    p01 = tables.add(period, calendar_id=calendar, period_key="FY2026-P01")
    state = tables.add(
        period_state, entity_id=entity["id"], book_code="ASC606", period_id=p01["id"], state="open"
    )
    reads = PersistedReads(tables)
    assert reads.role_id("controller") == controller["id"]
    with pytest.raises(NotProvisioned, match="0 role rows"):
        reads.role_id("auditor")
    assert reads.period_state_id("US01", "ASC606", "FY2026-P01") == state["id"]
    with pytest.raises(NotProvisioned, match="period_state rows"):
        reads.period_state_id("US01", "IFRS15", "FY2026-P01")
    # The resolver: a result that carries the handle wins (RES-1); else the reads; else refused.
    loaded = load_platform_key(POS_012)
    steps = plan(loaded).steps
    provision = next(s for s in steps if s.handler == H["provision"])
    entity_book = next(s for s in steps if s.handler == H["entity_book"])
    ledger = [
        _entry(
            Call(H["provision"], "operator", {}, provision),
            SimpleNamespace(tenant={"id": uid("t")}, admin_membership_id=uid("m"), roles=None),
        ),
        _entry(
            Call(
                H["entity_book"], PREPARER, {"entity_code": "US01", "book": "ASC606"}, entity_book
            ),
            {"id": uid("eb")},
        ),
    ]
    with_reads = LedgerResolver(ledger, reads)
    assert with_reads.role_id("controller") == controller["id"]
    assert with_reads.period_state_id("US01", "ASC606", "FY2026-P01") == state["id"]
    without = LedgerResolver(ledger)
    with pytest.raises(UnresolvedHandle, match="READ-7"):
        without.role_id("controller")
    with pytest.raises(UnresolvedHandle, match="READ-7"):
        without.period_state_id("US01", "ASC606", "FY2026-P01")
    carried = LedgerResolver(
        [
            _entry(
                Call(H["provision"], "operator", {}, provision),
                SimpleNamespace(tenant={"id": uid("t")}, roles={"controller": uid("from-result")}),
            )
        ],
        reads,
    )
    assert carried.role_id("controller") == uid("from-result")  # the result first (RES-1)


def test_t_con_09_row_cross_checks_the_trace_balance_only_at_its_latest_period() -> None:
    tables = FakeTables()
    built = _group(tables, known_at=T0)
    reads = PersistedReads(tables)
    common = {
        "group_id": built["group_id"],
        "group_key": "CG-C-1",
        "members": ("C-1",),
        "books": ("ASC606",),
        "known_at": T0 + timedelta(seconds=1),
        "where": "checkpoint t",
    }
    # The row (latest period P02, 80.00) matches the P02 trace balance: the check passes.
    reads.output_bundle(**common, as_of_periods={"US01": "FY2026-P02"})
    # An earlier as-of period never consults the row (the trace is the source).
    tables.tables[contract_version_balance.name][0]["contract_liability_txn"] = Decimal("81.00")
    reads.output_bundle(**common, as_of_periods={"US01": "FY2026-P01"})
    # At the row's own period a difference refuses by name; the row is never the source.
    with pytest.raises(NotProvisioned, match="contract_liability_txn = 81.00 differs"):
        reads.output_bundle(**common, as_of_periods={"US01": "FY2026-P02"})


def test_as_of_periods_and_missing_balances_name_the_checkpoints_requirement() -> None:
    pos = load_platform_key(POS_012)
    checkpoint = pos.key.checkpoints[0]
    adapter = WorkspaceAdapter(pos, reads=PersistedReads(FakeTables()))
    as_of = checkpoint.as_of
    expected = f"FY{as_of[:4]}-P{int(as_of[5:7]):02d}"
    assert adapter.as_of_periods(checkpoint, "t") == {"US01": expected}
    bundles = next(item for item in _Assembler(pos).checkpoints() if item.name == checkpoint.name)
    missing = missing_balances(checkpoint, CheckpointRun(bundles, ()), {"US01": expected})
    assert missing == [f"C-POS-012-X@US01 {expected}", f"C-POS-012-Y@US01 {expected}"]
    assert missing_balances(checkpoint, CheckpointRun(bundles, ()), {}) == [
        "C-POS-012-X@US01 ?",
        "C-POS-012-Y@US01 ?",
    ]


def test_output_bundle_takes_the_member_identities_from_the_persisted_rows() -> None:
    """READ2-R2: the members and the group code come from the contract / combination_group rows;
    a plan that names other members or another group refuses by name; no prefix is inspected."""
    tables = FakeTables()
    built = _group(tables, known_at=T0)
    reads = PersistedReads(tables)
    common = {
        "group_id": built["group_id"],
        "books": ("ASC606",),
        "known_at": T0 + timedelta(seconds=1),
        "where": "checkpoint t",
    }
    output = reads.output_bundle(**common, group_key="CG-C-1", members=("C-1",))
    (asc,) = output.books
    assert {balance.subject_key for balance in asc.balances} == {"C-1@US01"}
    assert asc.status_in_book == (("C-1", "ACTIVE"),)  # the persisted member identity
    with pytest.raises(NotProvisioned, match=r"persisted group CG-C-1 holds \['C-1'\]"):
        reads.output_bundle(**common, group_key="CG-C-1", members=("C-9",))
    with pytest.raises(NotProvisioned, match="persisted group code is 'CG-C-1'"):
        reads.output_bundle(**common, group_key="OTHER", members=("C-1",))


def test_membership_is_read_as_of_the_cutoff_from_the_t_con_04_history() -> None:
    """D-98 74 (Codex F-RPS-ID-R1): the member moves to a new group one second AFTER the cutoff
    (old row valid_to = cutoff + 1 s; new row valid_from = cutoff + 1 s; the current contract row
    points at the new group). The checkpoint at the cutoff reconstructs with the original
    membership; a checkpoint after the move sees the new membership; the current column is never
    consulted."""
    tables = FakeTables()
    built = _group(tables, known_at=T0)
    cutoff = T0 + timedelta(seconds=1)
    old_group, new_group = built["group_id"], uid("group-new")
    c1 = tables.table_rows(contract, external_id="C-1")[0]
    (membership,) = tables.tables[combination_group_member.name]
    membership["valid_from_known_at"] = cutoff - timedelta(days=1)
    membership["valid_to_known_at"] = cutoff + timedelta(seconds=1)
    tables.add(
        combination_group_member,
        combination_group_id=new_group,
        contract_id=c1["id"],
        valid_from_known_at=cutoff + timedelta(seconds=1),
        valid_to_known_at=None,
    )
    tables.add(combination_group, id=new_group, code="CG-C-1-NEW")
    tables.tables[contract.name][0]["combination_group_id"] = new_group  # the CURRENT column
    reads = PersistedReads(tables)
    assert reads.members_at(old_group, cutoff) == ("C-1",)
    assert reads.members_at(new_group, cutoff) == ()
    later = cutoff + timedelta(minutes=1)
    assert reads.members_at(old_group, later) == ()
    assert reads.members_at(new_group, later) == ("C-1",)
    output = reads.output_bundle(
        group_id=old_group,
        group_key="CG-C-1",
        members=("C-1",),
        books=("ASC606",),
        known_at=cutoff,
        where="checkpoint at the original cutoff",
    )
    assert [b.subject_key for b in output.books[0].balances] == ["C-1@US01", "C-1@US01"]
    assert output.books[0].status_in_book == (("C-1", "ACTIVE"),)
    with pytest.raises(NotProvisioned, match=r"holds \[\] at .* \(rule READ-2, D-98 74\)"):
        reads.output_bundle(
            group_id=old_group,
            group_key="CG-C-1",
            members=("C-1",),
            books=("ASC606",),
            known_at=later,  # after the move the old group no longer holds the planned member
            where="checkpoint after the move",
        )
    # A member the history holds at the cutoff that the plan omits refuses too.
    with pytest.raises(NotProvisioned, match=r"names members \['C-9'\] but the persisted group"):
        reads.output_bundle(
            group_id=old_group,
            group_key="CG-C-1",
            members=("C-9",),
            books=("ASC606",),
            known_at=cutoff,
            where="checkpoint at the original cutoff",
        )


def test_the_invitation_token_is_the_one_in_the_email_the_membership_was_sent(
    keyring: KeyRing,
) -> None:
    """An invited user follows the link of the invitation email (04 T-PLT-07). The outbox row
    holds neither the token nor its hash: it keeps the place for it and names it (04 T-INT-03
    ``payload`` rev 1.151), and the link is composed when the mail goes out. The read composes it
    the same way for the ONE invitation of a membership; no invitation, two of them, or a mail of
    another kind to the same membership is refused by name — the runner never accepts on a token
    it made up."""
    tables = FakeTables()
    membership, other = uid("membership", "ak-preparer"), uid("membership", "ak-approver")

    def invited(member: UUID, *, dedupe_key: str | None = None) -> str:
        issued = provisioning.invitation_token(keyring)
        row = provisioning.invitation_message(
            tenant_id=tables.tenant_id,
            membership_id=member,
            email="ak-preparer@answer-keys.test",
            workspace_name="Answer keys",
            link_reference=issued.reference,
            key_id=issued.key_id,
            expires_at=T0 + timedelta(days=7),
            created_by=None,
            created_by_kind=PrincipalKind.OPERATOR,
            now=T0,
            dedupe_key=dedupe_key,
        )
        assert issued.token not in json.dumps(row["payload"])  # named, never held
        tables.add(outbox_message, **row)
        return issued.token

    token = invited(membership)
    reads = PersistedReads(tables, keyring=keyring)
    where = "invitation of ak-preparer"
    assert reads.invitation_token(membership, where=where) == token
    # without a key ring of its own the read composes with the test session's — the same keys
    assert PersistedReads(tables).invitation_token(membership, where=where) == token
    with pytest.raises(NotProvisioned, match="0 invitation messages sent to membership"):
        reads.invitation_token(other, where="invitation of ak-approver")
    tables.add(
        outbox_message,
        **outbox.message_values(
            tenant_id=tables.tenant_id,
            topic=OutboxTopic.EMAIL,
            aggregate_type="tenant_membership",
            aggregate_id=other,
            dedupe_key="notification:1",
            payload={
                "to": "ak-approver@answer-keys.test",
                "subject": "An approval is waiting",
                "text": "An approval is waiting for you.",
                "link_path": "/approvals",
                "reference": str(other),
                "notification_id": None,
            },
            now=T0,
            created_by=None,
            created_by_kind=PrincipalKind.SYSTEM,
        ),
    )
    with pytest.raises(NotProvisioned, match="0 invitation messages sent to membership"):
        reads.invitation_token(other, where="invitation of ak-approver")
    invited(membership, dedupe_key="invitation:sent-again")
    with pytest.raises(NotProvisioned, match="2 invitation messages sent to membership"):
        reads.invitation_token(membership, where=where)
