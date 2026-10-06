"""ADP-15 GL adapter contract suite (05 §5.2 ``GLAdapter``, ADP-10 to ADP-15, §5.3 ADP-20 to
ADP-23; 03 REQ-JE-011, REQ-JE-012, REQ-JE-014, REQ-JE-015, REQ-INT-009; PRD WLD-B-07, WLD-F-32;
BUILD_SPEC CLO-13, CLO-15).

One parametrised suite over every GL adapter. ``CSV_GL`` has no ERP and no mock router, so its cases
are the happy path, a permanent validation failure (unknown account) and an idempotent repeat by
external id. ``NETSUITE`` and ``QUICKBOOKS_ONLINE`` run against their in-process mock routers over
ASGI (no socket): happy path, 429 with ``Retry-After``, 5xx then success, a timeout after which
``get_posting`` finds the document, a permanent validation failure, and ``Duplicate`` with the
ERP's document id. The relay's recording of those outcomes is witnessed in
``tests/domain/journals/test_export.py``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Final
from urllib.parse import parse_qs, urlsplit
from uuid import NAMESPACE_URL, uuid5

import pytest
from erev_api.adapters.gl import netsuite, quickbooks
from erev_api.adapters.gl.csv import CsvGl
from erev_api.adapters.mocks import admin
from erev_api.adapters.mocks import netsuite as ns_mock
from erev_api.adapters.mocks import qbo as qbo_mock
from erev_api.domain.journals.ports import (
    Accepted,
    AccountRef,
    ChunkLine,
    Duplicate,
    EntityRef,
    GLAdapter,
    GLContext,
    JournalChunk,
    PeriodRef,
    Permanent,
    Transient,
    TrialBalanceDetail,
    TrialBalanceLine,
)
from fastapi import FastAPI
from support.http import asgi_client, recording_asgi_client

CHART: Final = (
    AccountRef(code="21001", name="Contract liability", account_type="LIABILITY"),
    AccountRef(code="5001", name="Revenue - Hardware 1", account_type="REVENUE"),
)
CONTEXT: Final = GLContext(tenant_code="acme-test", accounts=CHART)
MOCKS: Final = "/api/v1/__mocks__"
REALM: Final = "4620816365012345670"
SEPTEMBER: Final = PeriodRef("FY2026-P09", date(2026, 9, 1), date(2026, 9, 30))


def _line(line_no: int, account: str, role: str, debit: str, credit: str) -> ChunkLine:
    return ChunkLine(
        je_no="JE-AVM-US-000001",
        line_no=line_no,
        account_code=account,
        account_name=f"Account {account}",
        account_role=role,
        debit=Decimal(debit),
        credit=Decimal(credit),
        debit_functional=Decimal(debit),
        credit_functional=Decimal(credit),
        dimensions={"department": "D100"},
        memo="AVM-US Jan 2023 revenue recognition",
        source_references="Contract 1; journal_line=probe; source_lines=1",
    )


def _chunk(
    *,
    batch_no: int,
    revenue_account: str,
    run_no: str = "JR-000001",
    credit: str = "128.84",
    tenant: str = "acme-test",
    entity: str = "AVM-US",
    period: str = "FY2023-P01",
    period_end: date = date(2023, 1, 31),
    liability_account: str = "21001",
) -> JournalChunk:
    return JournalChunk(
        external_id=f"erev:{tenant}:{run_no}:{batch_no}:1",
        run_no=run_no,
        batch_no=batch_no,
        chunk_no=1,
        entity_code=entity,
        posting_period=period,
        period_end_date=period_end,
        txn_currency="USD",
        functional_currency="USD",
        lines=(
            _line(1, liability_account, "CONTRACT_LIABILITY", "128.84", "0"),
            _line(2, revenue_account, "REVENUE", "0", credit),
        ),
    )


# --- CSV_GL ---------------------------------------------------------------------------------------


def _csv_suite() -> None:
    factory: Callable[[GLContext], GLAdapter] = CsvGl
    adapter = factory(CONTEXT)

    # Happy path: the chunk's accounts are in the chart and the posting answers its external id.
    happy = _chunk(batch_no=1, revenue_account="5001")
    assert adapter.validate_accounts(happy.accounts, happy.dimensions).ok
    posted = adapter.post_chunk(happy)
    assert (posted.external_id, posted.status, posted.gl_document_id) == (
        happy.external_id,
        "EXPORTED",
        None,
    )
    assert posted.artifact is not None
    assert posted.response_sha256 == hashlib.sha256(posted.artifact).hexdigest()
    archive = zipfile.ZipFile(io.BytesIO(posted.artifact))
    name = "erev_acme-test_JR-000001_1_1"
    assert sorted(archive.namelist()) == [f"{name}.csv", f"{name}.manifest.json"]
    csv_bytes = archive.read(f"{name}.csv")
    [header, *rows] = list(csv.reader(io.StringIO(csv_bytes.decode("utf-8"))))
    assert header[5:8] == ["account", "debit", "credit"]
    assert [(row[5], row[6], row[7]) for row in rows] == [
        ("21001", "128.84", "0.00"),
        ("5001", "0.00", "128.84"),
    ]
    manifest = json.loads(archive.read(f"{name}.manifest.json"))
    assert (manifest["row_count"], manifest["totals"], manifest["sha256"]) == (
        2,
        {"debit": "128.84", "credit": "128.84"},
        hashlib.sha256(csv_bytes).hexdigest(),
    )

    # Idempotent repeat by external id: the same result, found again by get_posting (ADP-10); a
    # fresh adapter renders the same bytes for the same chunk.
    assert adapter.post_chunk(happy) == posted
    assert adapter.get_posting(happy.external_id) == posted
    assert factory(CONTEXT).post_chunk(happy).artifact == posted.artifact

    # Permanent validation failure: an unknown account posts nothing (ADP-12).
    unknown = _chunk(batch_no=2, revenue_account="9999")
    checked = adapter.validate_accounts(unknown.accounts, unknown.dimensions)
    assert checked.errors == ("Account 9999 is not in the chart of accounts.",)
    with pytest.raises(Permanent, match="Account 9999 is not in the chart of accounts"):
        adapter.post_chunk(unknown)
    assert adapter.get_posting(unknown.external_id) is None
    assert [account.code for account in adapter.pull_chart_of_accounts()] == ["21001", "5001"]


# --- the ERP adapters against their mock routers --------------------------------------------------


def _mock_app() -> FastAPI:
    app = FastAPI()
    app.state.mocks = admin.MockWorld(
        adapters={ns_mock.CODE: ns_mock.NetSuiteMock(), qbo_mock.CODE: qbo_mock.QboMock()},
        faults=admin.Faults(),
    )
    for router in (admin.router, ns_mock.router, qbo_mock.router):
        app.include_router(router, prefix=MOCKS, include_in_schema=False)
    return app


def _send(app: FastAPI, path: str, body: dict[str, Any]) -> None:
    with asgi_client(app) as client:
        response = client.post(f"{MOCKS}{path}", json=body)
        assert response.status_code == 201, response.text


def _fault(app: FastAPI, route: str, kind: str, count: int = 1) -> None:
    _send(app, "/__admin/faults", {"route": route, "kind": kind, "count": count})


@dataclass
class Erp:
    """One ERP adapter over its mock: what the suite needs to know about either."""

    app: FastAPI
    adapter: GLAdapter
    journal_route: str
    postings: Callable[[], int]
    first_document: str
    unbalanced: str  # the ERP's message for a journal that does not balance
    unknown_account: str
    sleeps: list[float] = field(default_factory=list)


def _netsuite_erp() -> Erp:
    app = _mock_app()
    # The company's chart as NetSuite holds it (the mock's packaged chart is Quayside's).
    accounts = [
        {"acctNumber": "21001", "acctName": "Contract liability", "acctType": "DeferRevenue"},
        {"acctNumber": "5001", "acctName": "Revenue - Hardware 1", "acctType": "Income"},
    ]
    _send(app, f"{ns_mock.PREFIX}/__erp/accounts", {"accounts": accounts})
    sleeps: list[float] = []
    mock = app.state.mocks.adapters[ns_mock.CODE]
    return Erp(
        app=app,
        adapter=netsuite.NetSuiteGl(
            CONTEXT,
            client=asgi_client(app),
            base_url=f"{MOCKS}{ns_mock.PREFIX}",
            sleep=sleeps.append,
        ),
        journal_route=ns_mock.JOURNAL_ROUTE,
        postings=lambda: mock.posting_count,
        first_document="JE-NS-88001",
        unbalanced="The amounts in a journal entry must balance.",
        unknown_account="Account 9999 is not in the NetSuite chart of accounts.",
        sleeps=sleeps,
    )


def _quickbooks_erp() -> Erp:
    app = _mock_app()
    sleeps: list[float] = []
    mock = app.state.mocks.adapters[qbo_mock.CODE]
    return Erp(
        app=app,
        adapter=quickbooks.QuickBooksGl(
            CONTEXT,
            client=asgi_client(app),
            base_url=f"{MOCKS}{qbo_mock.PREFIX}",
            realm_id=REALM,
            sleep=sleeps.append,
        ),
        journal_route=qbo_mock.JOURNAL_ROUTE,
        postings=lambda: mock.posting_count(REALM),
        first_document="145",
        unbalanced="Debits must equal credits.",
        unknown_account="Account 9999 is not in the chart of accounts.",
        sleeps=sleeps,
    )


def _erp_suite(build: Callable[[], Erp]) -> None:
    erp = build()
    adapter = erp.adapter

    # Happy path: accounts known, the ERP answers with its document (ADP-31).
    happy = _chunk(batch_no=1, revenue_account="5001")
    assert adapter.validate_accounts(happy.accounts, happy.dimensions).ok
    posted = adapter.post_chunk(happy)
    assert (posted.external_id, posted.status, posted.gl_document_id, posted.gl_posted_date) == (
        happy.external_id,
        "POSTED",
        erp.first_document,
        date(2023, 1, 31),
    )
    assert posted.response_sha256 is not None and posted.artifact is None
    assert erp.postings() == 1
    # Idempotent by external id (ADP-10, ADP-23): the same document, no second posting.
    assert adapter.post_chunk(happy).gl_document_id == erp.first_document
    found = adapter.get_posting(happy.external_id)
    assert found is not None and found.gl_document_id == erp.first_document
    assert erp.postings() == 1

    # 429 with Retry-After: Transient carrying the wait the ERP states; nothing was posted.
    second = _chunk(batch_no=2, revenue_account="5001")
    _fault(erp.app, erp.journal_route, "RATE_LIMIT")
    with pytest.raises(Transient) as limited:
        adapter.post_chunk(second)
    assert limited.value.retry_after == float(admin.RATE_LIMIT_RETRY_SECONDS)
    assert erp.postings() == 1 and adapter.get_posting(second.external_id) is None
    # 5xx then success.
    _fault(erp.app, erp.journal_route, "SERVER_ERROR")
    with pytest.raises(Transient) as failed:
        adapter.post_chunk(second)
    assert failed.value.retry_after is None and erp.postings() == 1
    after = adapter.post_chunk(second)
    assert after.status == "POSTED" and after.gl_document_id != erp.first_document
    assert erp.postings() == 2

    # Timeout after the ERP accepted: the answer is lost, get_posting finds the document, and a
    # repeated post changes nothing (ADP-12).
    third = _chunk(batch_no=3, revenue_account="5001")
    _fault(erp.app, erp.journal_route, "TIMEOUT")
    with pytest.raises(Transient):
        adapter.post_chunk(third)
    recovered = adapter.get_posting(third.external_id)
    assert recovered is not None and recovered.status == "POSTED"
    assert erp.postings() == 3
    assert adapter.post_chunk(third).gl_document_id == recovered.gl_document_id
    assert erp.postings() == 3

    # Permanent validation failure: an unknown account is named before anything is sent, and a
    # journal the ERP refuses is Permanent with the ERP's message; nothing is posted.
    unknown = _chunk(batch_no=4, revenue_account="9999")
    checked = adapter.validate_accounts(unknown.accounts, unknown.dimensions)
    assert checked.errors == (erp.unknown_account,)
    unbalanced = _chunk(batch_no=5, revenue_account="5001", credit="128.83")
    with pytest.raises(Permanent) as refused:
        adapter.post_chunk(unbalanced)
    assert str(refused.value) == erp.unbalanced
    _fault(erp.app, erp.journal_route, "PERMANENT_ERROR")
    with pytest.raises(Permanent):
        adapter.post_chunk(_chunk(batch_no=6, revenue_account="5001"))
    assert erp.postings() == 3
    assert adapter.get_posting(unbalanced.external_id) is None

    # Duplicate: the ERP reports that the external id exists and names its document (ADP-12); the
    # relay records a DUPLICATE receipt with that id.
    _fault(erp.app, erp.journal_route, "DUPLICATE")
    with pytest.raises(Duplicate) as duplicate:
        adapter.post_chunk(happy)
    assert (duplicate.value.external_id, duplicate.value.gl_document_id) == (
        happy.external_id,
        erp.first_document,
    )
    assert erp.postings() == 3
    # One attempt per call: the export relay owns the ADP-12 schedule, the adapter never waits.
    assert erp.sleeps == []


SUITES: Final = [
    pytest.param(_csv_suite, id="CSV_GL"),
    pytest.param(lambda: _erp_suite(_netsuite_erp), id="NETSUITE"),
    pytest.param(lambda: _erp_suite(_quickbooks_erp), id="QUICKBOOKS_ONLINE"),
]


@pytest.mark.parametrize("suite", SUITES)
def test_contract_suite(suite: Callable[[], None]) -> None:
    suite()


@pytest.mark.control("CTL-021")
def test_ctl_021_netsuite_upsert_idempotent() -> None:
    """CTL-021 (ADP-23; PRD J-13-AC-4): posting one chunk twice returns the same document id and
    the mock's posting count stays 1 — also through a second adapter, as a second relay would."""
    erp = _netsuite_erp()
    chunk = _chunk(batch_no=1, revenue_account="5001")
    first = erp.adapter.post_chunk(chunk)
    again = erp.adapter.post_chunk(chunk)
    other = netsuite.NetSuiteGl(
        CONTEXT, client=asgi_client(erp.app), base_url=f"{MOCKS}{ns_mock.PREFIX}"
    ).post_chunk(chunk)
    assert first.gl_document_id == again.gl_document_id == other.gl_document_id == "JE-NS-88001"
    assert erp.postings() == 1
    # a changed body under the same external id changes nothing either (ADP-13)
    changed = _chunk(batch_no=1, revenue_account="5001", period_end=date(2023, 2, 28))
    assert erp.adapter.post_chunk(changed).gl_posted_date == date(2023, 1, 31)
    assert erp.postings() == 1


def test_netsuite_raises_accepted_when_the_ledger_does_not_show_what_it_took() -> None:
    """05 ADP-12 and ADP-21 rev 1.175 (item JRN-EXIT-SETTLE-1; review finding F9): under the
    mock's ``READ_LAG`` the upsert is accepted and the journal is in none of the ledger's reads,
    so the adapter's read-back finds nothing and it raises ``Accepted`` — a ``Transient`` for
    the relay, a class of its own for the exits of a failed batch. A repeated post is accepted
    again and shows nothing more, ``get_posting`` answers None and the trial balance leaves the
    journal out, while the ledger holds one journal throughout. Once the ledger releases it the
    external id reads back as the document it was given, and the trial balance states it."""
    app = _mock_app()
    gl = _netsuite_for(app, "t-lag")
    chunk = _september_chunk("t-lag", 1)
    mock = app.state.mocks.adapters[ns_mock.CODE]
    _fault(app, ns_mock.JOURNAL_ROUTE, "READ_LAG")
    for _ in range(2):  # the one use of the fault hides the journal until it is released
        with pytest.raises(Accepted) as lagging:
            gl.post_chunk(chunk)
        assert isinstance(lagging.value, Transient) and lagging.value.retry_after is None
        assert str(lagging.value) == f"{chunk.external_id} was accepted and cannot be read back yet"
        assert gl.get_posting(chunk.external_id) is None
        assert mock.posting_count == 1
    hidden = gl.pull_trial_balance(EntityRef("AVM-US"), SEPTEMBER, ["2100", "4010"])
    assert {line.account_code: line.amount for line in hidden.lines} == {"2100": Decimal("250.00")}

    with asgi_client(app) as client:
        state = client.get(f"{MOCKS}/__admin/state").json()["adapters"][ns_mock.CODE]
        assert (state["journals"], state["unreleased_journals"]) == (1, 1)
        shown = client.post(f"{MOCKS}{ns_mock.PREFIX}/__erp/journals/release")
        assert shown.status_code == 200, shown.text
        assert (shown.json()["released"], shown.json()["unreleased_journals"]) == (1, 0)
        again = client.post(f"{MOCKS}{ns_mock.PREFIX}/__erp/journals/release")
        assert again.json()["released"] == 0
    found = gl.get_posting(chunk.external_id)
    assert found is not None and (found.status, found.gl_document_id) == ("POSTED", "JE-NS-88001")
    assert gl.post_chunk(chunk).gl_document_id == "JE-NS-88001" and mock.posting_count == 1
    stated = gl.pull_trial_balance(EntityRef("AVM-US"), SEPTEMBER, ["2100", "4010"])
    assert {line.account_code: line.amount for line in stated.lines} == {
        "2100": Decimal("128.84") + Decimal("250.00"),
        "4010": Decimal("-128.84"),
    }


def test_qbo_request_id() -> None:
    """ADP-10 / REQ-JE-015: ``requestid`` equals ``uuid5(uuid5(NAMESPACE_URL,
    "https://erev.dev/ns/journal"), external_id)``; ``DocNumber`` is at most 21 characters;
    ``PrivateNote`` holds the full external id."""
    app = _mock_app()
    requested: list[str] = []
    adapter = quickbooks.QuickBooksGl(
        CONTEXT,
        client=recording_asgi_client(app, requested),
        base_url=f"{MOCKS}{qbo_mock.PREFIX}",
        realm_id=REALM,
    )
    namespace = uuid5(NAMESPACE_URL, "https://erev.dev/ns/journal")
    chunk = _chunk(batch_no=1, revenue_account="5001")
    adapter.post_chunk(chunk)
    [sent] = requested
    url = urlsplit(sent)
    assert url.path == f"{MOCKS}{qbo_mock.PREFIX}/v3/company/{REALM}/journalentry"
    assert parse_qs(url.query) == {"requestid": [str(uuid5(namespace, chunk.external_id))]}
    assert quickbooks.request_id(chunk.external_id) == uuid5(namespace, chunk.external_id)
    body = quickbooks.journal_body(chunk)
    assert (body["DocNumber"], body["PrivateNote"]) == ("JR-000001-1-1", chunk.external_id)
    assert [
        (line["JournalEntryLineDetail"]["PostingType"], line["Amount"]) for line in body["Line"]
    ] == [("Debit", "128.84"), ("Credit", "128.84")]
    # a long run number: the document number is cut at 21 characters, the note keeps the whole id
    long_run = _chunk(batch_no=12, revenue_account="5001", run_no="JR-2026-0000001234567")
    cut = quickbooks.journal_body(long_run)
    assert (cut["DocNumber"], len(cut["DocNumber"])) == ("JR-2026-0000001234567", 21)
    assert cut["PrivateNote"] == long_run.external_id == "erev:acme-test:JR-2026-0000001234567:12:1"
    posted = adapter.post_chunk(long_run)
    found = adapter.get_posting(long_run.external_id)
    assert found is not None and found.gl_document_id == posted.gl_document_id
    # the same request id returns the stored first response: no second entry (ADP-23)
    mock = app.state.mocks.adapters[qbo_mock.CODE]
    assert adapter.post_chunk(chunk).gl_document_id == "145" and mock.posting_count(REALM) == 2


# --- trial balance (REQ-INT-009) ------------------------------------------------------------------


def _netsuite_for(app: FastAPI, tenant: str) -> netsuite.NetSuiteGl:
    return netsuite.NetSuiteGl(
        GLContext(tenant_code=tenant, accounts=()),
        client=asgi_client(app),
        base_url=f"{MOCKS}{ns_mock.PREFIX}",
        sleep=lambda seconds: None,
    )


def _september_chunk(tenant: str, batch_no: int, **over: Any) -> JournalChunk:
    values: dict[str, Any] = {
        "batch_no": batch_no,
        "revenue_account": "4010",
        "liability_account": "2100",
        "tenant": tenant,
        "period": "FY2026-P09",
        "period_end": date(2026, 9, 30),
    }
    values.update(over)
    return _chunk(**values)


def test_trial_balance_pull_avm_us_sep_2026() -> None:
    """BUILD_SPEC CLO-15 (WLD-B-07; WLD-F-32; REQ-INT-009): ``pull_trial_balance`` for AVM-US Sep
    2026 against the packaged fixture returns account 2100 with detail ``JE-NS-88121`` USD
    250.00 — a document made in the ERP, so it carries no external id."""
    app = _mock_app()
    gl = _netsuite_for(app, "avenmoor")
    pulled = gl.pull_trial_balance(EntityRef("AVM-US"), SEPTEMBER, ["2100", "4010"])
    direct = TrialBalanceDetail(
        account_code="2100",
        currency="USD",
        amount=Decimal("250.00"),
        document_reference="JE-NS-88121",
        external_id=None,
        posted_date=date(2026, 9, 30),
    )
    assert (pulled.entity_code, pulled.period_key) == ("AVM-US", "FY2026-P09")
    assert pulled.lines == (TrialBalanceLine("2100", "USD", Decimal("250.00")),)
    assert pulled.details == (direct,)
    assert pulled.balances == {"2100": Decimal("250.00")}
    # the account filter is the adapter's question (REQ-INT-009: subledger-controlled accounts)
    assert gl.pull_trial_balance(EntityRef("AVM-US"), SEPTEMBER, ["4010"]).lines == ()
    # another subsidiary, and the period before, hold no such document
    assert gl.pull_trial_balance(EntityRef("AVM-UK"), SEPTEMBER, ["2100"]).details == ()
    august = PeriodRef("FY2026-P08", date(2026, 8, 1), date(2026, 8, 31))
    assert gl.pull_trial_balance(EntityRef("AVM-US"), august, ["2100"]).lines == ()


def test_trial_balance_is_what_was_posted_plus_what_the_erp_booked() -> None:
    """Supervisor rulings R-54 (e) and R-74 (e): the mock's trial balance is every journal posted
    to it through the period end, the packaged direct entry and the documents the ERP itself
    booked (an invoice in ERP billing mode: Dr receivable / Cr contract liability), per workspace
    and subsidiary; a document of this subledger carries its ADP-10 external id."""
    app = _mock_app()
    gl = _netsuite_for(app, "t-pellworth")  # any workspace: the direct entry is the subsidiary's
    august = _september_chunk("t-pellworth", 1, period="FY2026-P08", period_end=date(2026, 8, 31))
    september = _september_chunk("t-pellworth", 2)
    october = _september_chunk("t-pellworth", 3, period="FY2026-P10", period_end=date(2026, 10, 31))
    for chunk in (august, september, october):
        assert gl.post_chunk(chunk).status == "POSTED"
    other = _netsuite_for(app, "t-other")  # another workspace's NetSuite account
    other.post_chunk(_september_chunk("t-other", 1))
    _send(
        app,
        f"{ns_mock.PREFIX}/__erp/documents",
        {
            "account": "t-pellworth",
            "subsidiary": "AVM-US",
            "reference": "INV-US-1009",
            "date": "2026-09-15",
            "period": "FY2026-P09",
            "currency": "USD",
            "lines": [
                {"account": "1100", "amount": "9000.00"},
                {"account": "2100", "amount": "-9000.00"},
            ],
        },
    )
    pulled = gl.pull_trial_balance(EntityRef("AVM-US"), SEPTEMBER, ["1100", "2100", "4010"])
    # 2100: two journals of 128.84 (debit), the invoice's credit and the direct entry
    assert {line.account_code: line.amount for line in pulled.lines} == {
        "1100": Decimal("9000.00"),
        "2100": Decimal("128.84") * 2 - Decimal("9000.00") + Decimal("250.00"),
        "4010": Decimal("-128.84") * 2,
    }
    assert {line.currency for line in pulled.lines} == {"USD"}
    assert [
        (item.document_reference, item.account_code, item.amount, item.external_id)
        for item in pulled.details
    ] == [
        ("INV-US-1009", "1100", Decimal("9000.00"), None),
        ("INV-US-1009", "2100", Decimal("-9000.00"), None),
        ("JE-NS-88002", "2100", Decimal("128.84"), september.external_id),
        ("JE-NS-88002", "4010", Decimal("-128.84"), september.external_id),
        ("JE-NS-88121", "2100", Decimal("250.00"), None),
    ]
    assert {item.posted_date for item in pulled.details} == {date(2026, 9, 15), date(2026, 9, 30)}
    # the other workspace sees its own journal and the packaged direct entry, not these
    theirs = other.pull_trial_balance(EntityRef("AVM-US"), SEPTEMBER, ["2100"])
    assert [line.amount for line in theirs.lines] == [Decimal("128.84") + Decimal("250.00")]


def test_income_statement_accounts_are_fiscal_year_to_date() -> None:
    """The port's closing balance (ruling R-54 (e)): a balance sheet account is cumulative, an
    income statement account is stated for the fiscal year of the period asked — by the account
    type the chart holds, or the one a journal line states for an account the ledger opens."""
    app = _mock_app()
    typed = GLContext(
        tenant_code="t-years",
        accounts=(
            AccountRef("2100", "Contract liability", "LIABILITY"),
            AccountRef("4010", "Revenue", "REVENUE"),
        ),
    )
    gl = netsuite.NetSuiteGl(
        typed, client=asgi_client(app), base_url=f"{MOCKS}{ns_mock.PREFIX}", sleep=lambda s: None
    )
    last_year = _september_chunk(
        "t-years", 1, period="FY2025-P12", period_end=date(2025, 12, 31), entity="AVM-UK"
    )
    this_year = _september_chunk("t-years", 2, entity="AVM-UK")
    assert netsuite.journal_body(this_year, {"4010": "REVENUE"})["line"]["items"][1]["account"] == {
        "acctNumber": "4010",
        "acctName": "Account 4010",
        "acctType": "Income",
    }
    for chunk in (last_year, this_year):
        gl.post_chunk(chunk)
    pulled = gl.pull_trial_balance(EntityRef("AVM-UK"), SEPTEMBER, ["2100", "4010"])
    assert {line.account_code: line.amount for line in pulled.lines} == {
        "2100": Decimal("257.68"),  # both years
        "4010": Decimal("-128.84"),  # FY2026 only
    }


def test_a_fixture_that_states_balances_fixes_them(tmp_path: Path) -> None:
    """The demo's fixed trial balance (ADP-22; BUILD_SPEC CLO-22 fills it): a packaged fixture of
    the asking workspace that states ``balances`` for the subsidiary and period answers them as
    the closing balances; the documents of the period are listed all the same."""
    folder = tmp_path / "avenmoor"
    folder.mkdir()
    (folder / "netsuite-tb-avm-us-2026-09.json").write_text(
        json.dumps(
            {
                "tenant_code": "avenmoor",
                "subsidiary": "AVM-US",
                "period": "FY2026-P09",
                "currency": "USD",
                "documents": [
                    {
                        "reference": "JE-NS-88121",
                        "date": "2026-09-30",
                        "period": "FY2026-P09",
                        "lines": [{"account": "2100", "amount": "250.00"}],
                    }
                ],
                "balances": [
                    {"account": "2100", "amount": "-103180.14"},
                    {"account": "4010", "amount": "-88855.89"},
                ],
            }
        ),
        encoding="utf-8",
    )
    app = FastAPI()
    app.state.mocks = admin.MockWorld(
        adapters={ns_mock.CODE: ns_mock.NetSuiteMock(fixtures=tmp_path)}, faults=admin.Faults()
    )
    app.include_router(ns_mock.router, prefix=MOCKS, include_in_schema=False)
    fixed = _netsuite_for(app, "avenmoor").pull_trial_balance(
        EntityRef("AVM-US"), SEPTEMBER, ["2100", "4010"]
    )
    assert {line.account_code: line.amount for line in fixed.lines} == {
        "2100": Decimal("-103180.14"),
        "4010": Decimal("-88855.89"),
    }
    assert [item.document_reference for item in fixed.details] == ["JE-NS-88121"]
    # another workspace asking for the same subsidiary gets the computed balances
    computed = _netsuite_for(app, "t-pellworth").pull_trial_balance(
        EntityRef("AVM-US"), SEPTEMBER, ["2100", "4010"]
    )
    assert computed.lines == (TrialBalanceLine("2100", "USD", Decimal("250.00")),)


def test_trial_balance_pull_retries_on_the_adp_12_schedule() -> None:
    app = _mock_app()
    sleeps: list[float] = []
    gl = netsuite.NetSuiteGl(
        GLContext(tenant_code="avenmoor", accounts=()),
        client=asgi_client(app),
        base_url=f"{MOCKS}{ns_mock.PREFIX}",
        sleep=sleeps.append,
    )
    _fault(app, ns_mock.TRIAL_BALANCE_ROUTE, "RATE_LIMIT")
    _fault(app, ns_mock.TRIAL_BALANCE_ROUTE, "SERVER_ERROR")
    pulled = gl.pull_trial_balance(EntityRef("AVM-US"), SEPTEMBER, ["2100"])
    assert pulled.balances == {"2100": Decimal("250.00")} and sleeps == [30.0, 60.0]
    _fault(app, ns_mock.TRIAL_BALANCE_ROUTE, "PERMANENT_ERROR")
    with pytest.raises(Permanent):
        gl.pull_trial_balance(EntityRef("AVM-US"), SEPTEMBER, ["2100"])


def test_quickbooks_trial_balance_and_documents() -> None:
    """REQ-INT-009 for QuickBooks Online: the closing balances from the ``TrialBalance`` report and
    the documents of the period from ``TransactionList``; a company's own document carries no
    external id."""
    erp = _quickbooks_erp()
    september = _september_chunk("acme-test", 1)
    erp.adapter.post_chunk(september)
    _send(
        erp.app,
        f"{qbo_mock.PREFIX}/__erp/documents",
        {
            "account": REALM,
            "reference": "JE-QB-7001",
            "date": "2026-09-18",
            "currency": "USD",
            "lines": [{"account": "2100", "amount": "250.00"}],
        },
    )
    pulled = erp.adapter.pull_trial_balance(EntityRef("AVM-US"), SEPTEMBER, ["2100", "4010"])
    assert pulled.lines == (
        TrialBalanceLine("2100", "USD", Decimal("378.84")),
        TrialBalanceLine("4010", "USD", Decimal("-128.84")),
    )
    assert [
        (item.document_reference, item.account_code, item.amount, item.external_id)
        for item in pulled.details
    ] == [
        ("JE-QB-7001", "2100", Decimal("250.00"), None),
        ("JR-000001-1-1", "2100", Decimal("128.84"), september.external_id),
        ("JR-000001-1-1", "4010", Decimal("-128.84"), september.external_id),
    ]
    assert erp.sleeps == []


# --- what a batch states: the functional currency (05 ADP-10 rev 1.92; supervisor ruling R-110) ---

AUGUST: Final = PeriodRef("FY2026-P08", date(2026, 8, 1), date(2026, 8, 31))
REVENUE_MEMO: Final = "AVM-UK Jul 2026 revenue recognition"
FX_MEMO: Final = "AVM-UK Aug 2026 fx remeasurement"


def _uk_line(
    line_no: int,
    account: str,
    role: str,
    *,
    txn: tuple[str, str] = ("0", "0"),
    functional: tuple[str, str],
    je_no: str,
    memo: str,
) -> ChunkLine:
    """One line of AVM-UK, which keeps GBP books: (debit, credit) in the transaction and in the
    functional currency."""
    return ChunkLine(
        je_no=je_no,
        line_no=line_no,
        account_code=account,
        account_name=f"Account {account}",
        account_role=role,
        debit=Decimal(txn[0]),
        credit=Decimal(txn[1]),
        debit_functional=Decimal(functional[0]),
        credit_functional=Decimal(functional[1]),
        dimensions={},
        memo=memo,
        source_references="NS-SO-UK-7001",
    )


def _uk_chunk(
    run_no: str,
    period: str,
    period_end: date,
    lines: tuple[ChunkLine, ...],
    *,
    tenant: str = "t-fx",
    txn_currency: str = "USD",
    functional_currency: str = "GBP",
) -> JournalChunk:
    return JournalChunk(
        external_id=f"erev:{tenant}:{run_no}:1:1",
        run_no=run_no,
        batch_no=1,
        chunk_no=1,
        entity_code="AVM-UK",
        posting_period=period,
        period_end_date=period_end,
        txn_currency=txn_currency,
        functional_currency=functional_currency,
        lines=lines,
    )


def _july_revenue(tenant: str = "t-fx") -> JournalChunk:
    """AVM-UK's July batch of the contract NS-SO-UK-7001 in USD: revenue of USD 54,000.00
    measured at the July average 0.81, GBP 43,740.00."""
    je = {"je_no": "JE-AVM-UK-000001", "memo": REVENUE_MEMO}
    return _uk_chunk(
        "JR-000001",
        "FY2026-P07",
        date(2026, 7, 31),
        (
            _uk_line(
                1,
                "2100",
                "CONTRACT_LIABILITY",
                txn=("54000.00", "0"),
                functional=("43740.00", "0"),
                **je,
            ),
            _uk_line(
                2, "4000", "REVENUE", txn=("0", "54000.00"), functional=("0", "43740.00"), **je
            ),
        ),
        tenant=tenant,
    )


def _august_remeasurement(tenant: str = "t-fx") -> JournalChunk:
    """AVM-UK's August batch: the JET-10 settlement of GBP 1,080.00 — two lines of entry kind
    ``FX_REMEASUREMENT`` with a functional amount and no transaction amount."""
    je = {"je_no": "JE-AVM-UK-000002", "memo": FX_MEMO}
    return _uk_chunk(
        "JR-000002",
        "FY2026-P08",
        date(2026, 8, 31),
        (
            _uk_line(1, "2100", "CONTRACT_LIABILITY", functional=("1080.00", "0"), **je),
            _uk_line(2, "7200", "FX_GAIN_LOSS", functional=("0", "1080.00"), **je),
        ),
        tenant=tenant,
    )


UK_TYPES: Final = {"2100": "LIABILITY", "4000": "REVENUE", "7200": "EXPENSE"}


def _amounts(items: list[dict[str, Any]], *members: str) -> list[tuple[Any, ...]]:
    return [tuple(item.get(member) for member in members) for item in items]


def test_r110_a_foreign_currency_batch_is_stated_in_the_functional_currency() -> None:
    """Supervisor ruling R-110 (05 ADP-10 rev 1.92): a batch whose lines carry both amounts — July's
    revenue of AVM-UK, USD 54,000.00 measured at GBP 43,740.00 — is one document in GBP with the
    functional amounts; USD and the USD amounts go along as information and are not booked."""
    chunk = _july_revenue()
    body = netsuite.journal_body(chunk, UK_TYPES)
    assert body["currency"] == {"refName": "GBP"}
    assert body[netsuite.TXN_CURRENCY_FIELD] == "USD"
    items = body["line"]["items"]
    assert _amounts(items, "debit", "credit") == [("43740.00", None), (None, "43740.00")]
    assert _amounts(items, netsuite.TXN_DEBIT_FIELD, netsuite.TXN_CREDIT_FIELD) == [
        ("54000.00", None),
        (None, "54000.00"),
    ]
    entry = quickbooks.journal_body(chunk, UK_TYPES)
    assert entry["CurrencyRef"] == {"value": "GBP"}
    assert [
        (line["JournalEntryLineDetail"]["PostingType"], line["Amount"], line["Description"])
        for line in entry["Line"]
    ] == [
        ("Debit", "43740.00", f"{REVENUE_MEMO} [USD debit 54000.00]"),
        ("Credit", "43740.00", f"{REVENUE_MEMO} [USD credit 54000.00]"),
    ]
    # the run, the batch and its external id are what they were: only the statement changed
    assert (body["externalId"], entry["PrivateNote"]) == (chunk.external_id, chunk.external_id)


def test_r110_both_lines_of_a_remeasurement_reach_the_ledger() -> None:
    """Supervisor ruling R-110, the defect of item JE-CSV-FUNCTIONAL-1: AVM-UK's August batch is
    the two ``FX_REMEASUREMENT`` lines of GBP 1,080.00, which have no transaction amount. Both
    adapters state them with their functional amount, both ledgers book them, and the trial
    balance of August answers GBP alone — July's revenue at the rate the engine measured it at,
    not at a rate of the ledger."""
    july, august = _july_revenue(), _august_remeasurement()
    body = netsuite.journal_body(august, UK_TYPES)
    items = body["line"]["items"]
    assert body["currency"] == {"refName": "GBP"} and body[netsuite.TXN_CURRENCY_FIELD] == "USD"
    assert _amounts(items, "debit", "credit") == [("1080.00", None), (None, "1080.00")]
    # a line without a transaction amount has no informational amount to state
    assert all(
        netsuite.TXN_DEBIT_FIELD not in item and netsuite.TXN_CREDIT_FIELD not in item
        for item in items
    )
    entry = quickbooks.journal_body(august, UK_TYPES)
    assert [
        (line["JournalEntryLineDetail"]["PostingType"], line["Amount"], line["Description"])
        for line in entry["Line"]
    ] == [("Debit", "1080.00", FX_MEMO), ("Credit", "1080.00", FX_MEMO)]

    app = _mock_app()
    context = GLContext(
        tenant_code="t-fx",
        accounts=tuple(
            AccountRef(code, f"Account {code}", kind) for code, kind in UK_TYPES.items()
        ),
    )
    ledgers: dict[str, GLAdapter] = {
        "NETSUITE": netsuite.NetSuiteGl(
            context,
            client=asgi_client(app),
            base_url=f"{MOCKS}{ns_mock.PREFIX}",
            sleep=lambda seconds: None,
        ),
        "QUICKBOOKS_ONLINE": quickbooks.QuickBooksGl(
            context,
            client=asgi_client(app),
            base_url=f"{MOCKS}{qbo_mock.PREFIX}",
            realm_id=REALM,
            sleep=lambda seconds: None,
        ),
    }
    for code, gl in ledgers.items():
        assert [gl.post_chunk(chunk).status for chunk in (july, august)] == ["POSTED"] * 2, code
        pulled = gl.pull_trial_balance(EntityRef("AVM-UK"), AUGUST, ["2100", "4000", "7200"])
        assert pulled.lines == (
            TrialBalanceLine("2100", "GBP", Decimal("44820.00")),
            TrialBalanceLine("4000", "GBP", Decimal("-43740.00")),
            TrialBalanceLine("7200", "GBP", Decimal("-1080.00")),
        ), code
        # the documents of August: the remeasurement alone, under the chunk's external id
        assert [
            (item.account_code, item.currency, item.amount, item.external_id)
            for item in pulled.details
        ] == [
            ("2100", "GBP", Decimal("1080.00"), august.external_id),
            ("7200", "GBP", Decimal("-1080.00"), august.external_id),
        ], code


def test_r110_a_line_netted_to_opposite_sides_states_both() -> None:
    """Supervisor ruling R-110: a summarised line is a net per currency, so its transaction net
    and its functional net can lie on opposite sides — a debit of USD 100.00 measured at GBP
    80.00 and a credit of USD 90.00 measured at GBP 85.50 net to a transaction debit of 10.00
    and a functional credit of 5.50. The ledger books the functional credit; the transaction
    debit goes along as information on that same line, in both adapters."""
    je = {"je_no": "JE-AVM-UK-000003", "memo": "AVM-UK Aug 2026 revenue recognition"}
    chunk = _uk_chunk(
        "JR-000003",
        "FY2026-P08",
        date(2026, 8, 31),
        (
            _uk_line(
                1, "2100", "CONTRACT_LIABILITY", txn=("10.00", "0"), functional=("0", "5.50"), **je
            ),
            _uk_line(2, "4000", "REVENUE", txn=("0", "10.00"), functional=("5.50", "0"), **je),
        ),
    )
    items = netsuite.journal_body(chunk, UK_TYPES)["line"]["items"]
    assert _amounts(items, "debit", "credit") == [(None, "5.50"), ("5.50", None)]
    assert _amounts(items, netsuite.TXN_DEBIT_FIELD, netsuite.TXN_CREDIT_FIELD) == [
        ("10.00", None),
        (None, "10.00"),
    ]
    assert [
        (line["JournalEntryLineDetail"]["PostingType"], line["Amount"], line["Description"])
        for line in quickbooks.journal_body(chunk, UK_TYPES)["Line"]
    ] == [
        ("Credit", "5.50", f"{je['memo']} [USD debit 10.00]"),
        ("Debit", "5.50", f"{je['memo']} [USD credit 10.00]"),
    ]


def test_r110_a_batch_in_the_functional_currency_carries_no_informational_member() -> None:
    """Supervisor ruling R-110: the informational members are stated only for a batch whose
    transaction currency is not the entity's functional currency."""
    chunk = _chunk(batch_no=1, revenue_account="5001")
    body = netsuite.journal_body(chunk)
    assert body["currency"] == {"refName": "USD"} and netsuite.TXN_CURRENCY_FIELD not in body
    assert all(
        netsuite.TXN_DEBIT_FIELD not in item and netsuite.TXN_CREDIT_FIELD not in item
        for item in body["line"]["items"]
    )
    assert _amounts(body["line"]["items"], "debit", "credit") == [
        ("128.84", None),
        (None, "128.84"),
    ]
    assert [line["Description"] for line in quickbooks.journal_body(chunk)["Line"]] == [
        "AVM-US Jan 2023 revenue recognition"
    ] * 2


def test_r110_a_line_whose_functional_amount_is_nil_books_nothing() -> None:
    """Supervisor ruling R-110, the remaining edge: a line with a transaction amount whose
    functional amount is nil — KRW 3 in USD books converts to less than half a cent; the corpus
    holds no such line. It stays in the document, without an amount (NetSuite) or with ``Amount``
    0.00 on its transaction side (QuickBooks Online), carries its transaction amount as
    information and books nothing; the entry still balances in the functional currency."""
    je = {"je_no": "JE-AVM-US-000009", "memo": "AVM-US Sep 2026 revenue recognition"}
    chunk = _uk_chunk(
        "JR-000009",
        "FY2026-P09",
        date(2026, 9, 30),
        (
            _uk_line(
                1, "2100", "CONTRACT_LIABILITY", txn=("3", "0"), functional=("0.00", "0"), **je
            ),
            _uk_line(2, "4010", "REVENUE", txn=("0", "3"), functional=("0", "0.00"), **je),
            _uk_line(
                3,
                "2100",
                "CONTRACT_LIABILITY",
                txn=("150000", "0"),
                functional=("108.00", "0"),
                **je,
            ),
            _uk_line(4, "4010", "REVENUE", txn=("0", "150000"), functional=("0", "108.00"), **je),
        ),
        tenant="t-krw",
        txn_currency="KRW",
        functional_currency="USD",
    )
    types = {"2100": "LIABILITY", "4010": "REVENUE"}
    body = netsuite.journal_body(chunk, types)
    items = body["line"]["items"]
    assert _amounts(items, "debit", "credit") == [
        (None, None),
        (None, None),
        ("108.00", None),
        (None, "108.00"),
    ]
    assert _amounts(items, netsuite.TXN_DEBIT_FIELD, netsuite.TXN_CREDIT_FIELD) == [
        ("3", None),
        (None, "3"),
        ("150000", None),
        (None, "150000"),
    ]
    entry = quickbooks.journal_body(chunk, types)
    assert [
        (line["JournalEntryLineDetail"]["PostingType"], line["Amount"], line["Description"])
        for line in entry["Line"]
    ] == [
        ("Debit", "0.00", f"{je['memo']} [KRW debit 3]"),
        ("Credit", "0.00", f"{je['memo']} [KRW credit 3]"),
        ("Debit", "108.00", f"{je['memo']} [KRW debit 150000]"),
        ("Credit", "108.00", f"{je['memo']} [KRW credit 150000]"),
    ]
    app = _mock_app()
    gl = _netsuite_for(app, "t-krw")
    assert gl.post_chunk(chunk).status == "POSTED"
    pulled = gl.pull_trial_balance(EntityRef("AVM-UK"), SEPTEMBER, ["2100", "4010"])
    # one amount per account: the two nil lines added nothing
    assert pulled.lines == (
        TrialBalanceLine("2100", "USD", Decimal("108.00")),
        TrialBalanceLine("4010", "USD", Decimal("-108.00")),
    )
    assert [(item.account_code, item.amount) for item in pulled.details] == [
        ("2100", Decimal("108.00")),
        ("4010", Decimal("-108.00")),
    ]


def test_r110_the_quickbooks_mock_keeps_one_currency() -> None:
    """The QuickBooks Online mock's company has one home currency — that of its first document —
    and holds no exchange rates: a document in another currency is refused, so its reports never
    add amounts of two currencies."""
    erp = _quickbooks_erp()
    erp.adapter.post_chunk(_september_chunk("acme-test", 1))
    # another run of the same workspace, stated in GBP (the July chunk would repeat the first
    # chunk's external id and replay its stored response, ADP-23)
    with pytest.raises(Permanent, match="keeps its ledger in USD"):
        erp.adapter.post_chunk(_august_remeasurement("acme-test"))
    with asgi_client(erp.app) as client:
        refused = client.post(
            f"{MOCKS}{qbo_mock.PREFIX}/__erp/documents",
            json={
                "account": REALM,
                "reference": "JE-QB-7002",
                "date": "2026-09-18",
                "currency": "GBP",
                "lines": [{"account": "2100", "amount": "10.00"}],
            },
        )
    assert refused.status_code == 400, refused.text
    assert erp.postings() == 1
