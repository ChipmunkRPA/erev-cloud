"""How a functional amount reaches the general ledger (item JE-CSV-FUNCTIONAL-1; supervisor ruling
R-110, pending the independent accountant as candidate AD-55; 03 REQ-JE-011 rev 1.68; 04 T-SL-07
"The currencies of an exported batch", §16.7; 05 ADP-10 rev 1.92, ADP-11; BUILD_SPEC CLO-15).

The world is the sibling module's (``test_fx_remeasurement_recompute``): AVM-UK keeps GBP books and
its contract ``NS-SO-UK-7001`` is in USD. The journals of two periods, each one batch of two lines:

- July (FY2026-P07): revenue of USD 54,000.00 measured at the July average 0.81 — Dr contract
  liability 2100 / Cr revenue 4000, GBP 43,740.00. Both lines carry both amounts.
- August (FY2026-P08): the invoice of 20 August settles the layer at spot — JET-10 Dr contract
  liability 2100 / Cr foreign exchange gain or loss 7200, GBP 1,080.00. Both lines are of entry
  kind ``FX_REMEASUREMENT``: a functional amount and no transaction amount.

Before the ruling an ERP adapter stated the batch in USD with the transaction amounts: the August
lines carried no amount, the 1,080.00 reached no ledger and the CSV showed 0.00 / 0.00. Each test
runs the product's own path — the Integration Admin's connection, ``POST /journal-runs`` and its
job, submit, the Controller's approval, ``POST /journal-runs/{id}/export`` and the relay — against
the app's own NetSuite or QuickBooks Online mock, with the adapter registered as the worker
registers it (``connection_factory``; DG-LAY-03).
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.adapters import mocks
from erev_api.adapters.gl import netsuite, quickbooks
from erev_api.adapters.mocks import netsuite as ns_mock
from erev_api.adapters.mocks import qbo as qbo_mock
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import gl_account, journal_run, subledger_line, tenant
from erev_api.domain.journals import ports
from erev_api.enums import GlAdapter
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import and_, func, select
from support import close_runs as runs
from support import reconciliations as recon
from support.close_world import acknowledge_run
from support.db import TestDatabase
from support.http import asgi_client
from support.principals import Actor, colleague, enrolled
from support.reference import approve, assign, get, patch, post
from test_fx_remeasurement_recompute import (
    ENTITY,
    World,
    _invoice,
    _recorded,
    delivered,
)
from test_fx_remeasurement_recompute import world as avm_uk_world  # noqa: F401 - a fixture

INTEGRATIONS: Final = "/api/v1/integrations"
JOURNAL_RUNS: Final = "/api/v1/journal-runs"
BATCHES: Final = "/api/v1/journal-batches"
RUN_ID_HEADER: Final = "X-Erev-Journal-Run-Id"
GRAIN: Final = "ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS"
JULY: Final = "FY2026-P07"
AUGUST: Final = "FY2026-P08"
REALM: Final = "4620816365012345670"
REVENUE_MEMO: Final = "AVM-UK Jul 2026 revenue recognition"
FX_MEMO: Final = "AVM-UK Aug 2026 fx remeasurement"
# (account, debit, credit) of a batch's lines: the transaction and the functional amounts.
JULY_TXN: Final = [("2100", "54000.00", "0.00"), ("4000", "0.00", "54000.00")]
JULY_FUNCTIONAL: Final = [("2100", "43740.00", "0.00"), ("4000", "0.00", "43740.00")]
AUGUST_TXN: Final = [("2100", "0.00", "0.00"), ("7200", "0.00", "0.00")]
AUGUST_FUNCTIONAL: Final = [("2100", "1080.00", "0.00"), ("7200", "0.00", "1080.00")]
# ``billing.posting = ERP`` (POLICIES POL-004): the ERP posts INV-UK-7001 itself — Dr receivable /
# Cr contract liability at the issue date (supervisor ruling R-74 (e)): USD 54,000.00 at the 20
# August spot 0.84, GBP 45,360.00.
ERP_INVOICE: Final = "INV-UK-7001"
ERP_INVOICE_DATE: Final = "2026-08-20"
ERP_INVOICE_GBP: Final = Decimal("45360.00")
RECEIVABLE: Final = "1100"  # accounts receivable, which the ERP keeps


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(request: pytest.FixtureRequest) -> World:
    """The sibling module's world: its fixture is registered here as ``avm_uk_world`` and built
    over this module's ``app``."""
    built: World = request.getfixturevalue("avm_uk_world")
    return built


class Sent:
    """The HTTP client the worker's factory builds, over the app's own mocks: every JSON body an
    adapter sends is kept as sent."""

    def __init__(self, app: Any) -> None:
        self._client = asgi_client(app)
        self.bodies: list[dict[str, Any]] = []

    def request(self, method: str, url: str, json: Any = None) -> Any:
        if json is not None:
            self.bodies.append(dict(json))
        return self._client.request(method, url, json=json)

    def get(self, url: str) -> Any:
        return self._client.get(url)


@dataclass(frozen=True)
class Ledger:
    """One ERP adapter as the suite needs it: its connection, its worker factory, the mock's
    chart where the ledger keeps one, and what a journal body states."""

    adapter: GlAdapter
    connection: dict[str, Any]
    factory: Callable[[Callable[[str], Any]], ports.GLAdapterFactory]
    stated: Callable[[dict[str, Any]], tuple[Any, ...]]
    documents: tuple[str, str]
    chart: tuple[dict[str, str], ...] = ()


def _netsuite_stated(body: dict[str, Any]) -> tuple[Any, ...]:
    """(currency, transaction currency, [(account, debit, credit, transaction debit, transaction
    credit)]) of a NetSuite journal entry."""
    return (
        body["currency"]["refName"],
        body.get(netsuite.TXN_CURRENCY_FIELD),
        [
            (
                item["account"]["acctNumber"],
                item.get("debit"),
                item.get("credit"),
                item.get(netsuite.TXN_DEBIT_FIELD),
                item.get(netsuite.TXN_CREDIT_FIELD),
            )
            for item in body["line"]["items"]
        ],
    )


def _quickbooks_stated(body: dict[str, Any]) -> tuple[Any, ...]:
    """(currency, [(account, posting type, amount, description)]) of a QuickBooks JournalEntry."""
    return (
        body["CurrencyRef"]["value"],
        [
            (
                line["JournalEntryLineDetail"]["AccountRef"]["value"],
                line["JournalEntryLineDetail"]["PostingType"],
                line["Amount"],
                line["Description"],
            )
            for line in body["Line"]
        ],
    )


LEDGERS: Final = {
    "NETSUITE": Ledger(
        adapter=GlAdapter.NETSUITE,
        connection={
            "code": "netsuite-mock",
            "name": "NetSuite (mock)",
            "adapter": "NETSUITE",
            "base_url": f"{mocks.MOCKS_PREFIX}{ns_mock.PREFIX}",
        },
        factory=netsuite.connection_factory,
        stated=_netsuite_stated,
        documents=("JE-NS-88001", "JE-NS-88002"),
        # the company's chart as NetSuite holds it (the mock's packaged chart is Quayside's)
        chart=(
            {"acctNumber": "2100", "acctName": "Contract liability", "acctType": "DeferRevenue"},
            {"acctNumber": "4000", "acctName": "Revenue", "acctType": "Income"},
            {"acctNumber": "7200", "acctName": "FX gain or loss", "acctType": "Expense"},
        ),
    ),
    "QUICKBOOKS_ONLINE": Ledger(
        adapter=GlAdapter.QUICKBOOKS_ONLINE,
        connection={
            "code": "quickbooks-mock",
            "name": "QuickBooks Online (mock)",
            "adapter": "QUICKBOOKS_ONLINE",
            "base_url": f"{mocks.MOCKS_PREFIX}{qbo_mock.PREFIX}",
            "config": {"realm_id": REALM},
        },
        factory=quickbooks.connection_factory,
        stated=_quickbooks_stated,
        documents=("145", "146"),
    ),
}
# What each ledger receives (05 ADP-10 rev 1.92): the document in GBP with the functional amounts;
# USD and the USD amounts as information, where a line has a transaction amount.
STATED: Final = {
    "NETSUITE": {
        JULY: (
            "GBP",
            "USD",
            [
                ("2100", "43740.00", None, "54000.00", None),
                ("4000", None, "43740.00", None, "54000.00"),
            ],
        ),
        AUGUST: (
            "GBP",
            "USD",
            [("2100", "1080.00", None, None, None), ("7200", None, "1080.00", None, None)],
        ),
    },
    "QUICKBOOKS_ONLINE": {
        JULY: (
            "GBP",
            [
                ("2100", "Debit", "43740.00", f"{REVENUE_MEMO} [USD debit 54000.00]"),
                ("4000", "Credit", "43740.00", f"{REVENUE_MEMO} [USD credit 54000.00]"),
            ],
        ),
        AUGUST: (
            "GBP",
            [("2100", "Debit", "1080.00", FX_MEMO), ("7200", "Credit", "1080.00", FX_MEMO)],
        ),
    },
}


def _runtime(world: World) -> JobRuntime:
    place = world.place
    return JobRuntime(clock=place.clock, keyring=place.keyring, files=place.files)


def _job(world: World, job_id: str) -> dict[str, Any]:
    finished = recon.job_run(world.place.tenant_id, _runtime(world), UUID(job_id))
    assert str(finished["state"]) == "SUCCEEDED", finished
    return finished


def _connected(world: World, ledger: Ledger, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Sent]:
    """The ledger's ``ACTIVE`` connection, created and enabled by an Integration Admin, and the
    adapter registered as the worker registers it; returns the connection id and what is sent."""
    someone = colleague(world.place.tenant_id, "nikhil")
    assign(someone, "integration_admin")
    admin: Actor = enrolled(world.app, world.place.clock, someone)
    created = post(world.app, INTEGRATIONS, admin, {"direction": "BOTH", **ledger.connection})
    assert created.status_code == 201, created.text
    enabled = patch(
        world.app,
        f"{INTEGRATIONS}/{created.json()['id']}",
        admin,
        {"status": "ACTIVE"},
        if_match='"r1"',
    )
    assert enabled.status_code == 200, enabled.text
    sent = Sent(world.app)
    monkeypatch.setitem(ports.GL_ADAPTERS, ledger.adapter, ledger.factory(lambda base_url: sent))
    if ledger.chart:
        with asgi_client(world.app) as client:
            seeded = client.post(
                f"{ledger.connection['base_url']}/__erp/accounts",
                json={"accounts": list(ledger.chart)},
            )
            assert seeded.status_code == 201, seeded.text
    return str(enabled.json()["id"]), sent


def _erp_books_its_invoice(world: World, ledger: Ledger) -> None:
    """The ledger an ERP keeps holds the invoice the ERP posts itself (constants above). A mock
    ledger holds a document made in the ERP only when it is told one (``POST /__erp/documents``:
    NetSuite by workspace and subsidiary, QuickBooks Online by realm)."""
    document: dict[str, Any] = {
        "reference": ERP_INVOICE,
        "date": ERP_INVOICE_DATE,
        "currency": "GBP",
        "lines": [
            {"account": RECEIVABLE, "amount": str(ERP_INVOICE_GBP)},
            {"account": "2100", "amount": str(-ERP_INVOICE_GBP)},
        ],
    }
    if ledger.adapter is GlAdapter.NETSUITE:
        workspace_code = world.place.scalar(
            select(tenant.c.code).where(tenant.c.id == world.place.tenant_id)
        )
        document |= {"account": str(workspace_code), "subsidiary": ENTITY, "period": AUGUST}
    else:
        document |= {"account": REALM}
    with asgi_client(world.app) as client:
        told = client.post(f"{ledger.connection['base_url']}/__erp/documents", json=document)
    assert told.status_code == 201, told.text


def _run(world: World, run_id: str) -> dict[str, Any]:
    shown = get(world.app, f"{JOURNAL_RUNS}/{run_id}", world.maya)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def _calculated(world: World, period_key: str) -> dict[str, Any]:
    created = post(
        world.app,
        JOURNAL_RUNS,
        world.maya,
        {"entity_code": ENTITY, "period_key": period_key, "grain": GRAIN},
    )
    assert created.status_code == 202, created.text
    _job(world, str(created.json()["id"]))
    return _run(world, str(created.headers[RUN_ID_HEADER]))


def _exported(world: World, run: dict[str, Any]) -> dict[str, Any]:
    """Maya submits, Marcus approves, Maya exports and the relay dispatches the run's batches."""
    submitted = post(world.app, f"{JOURNAL_RUNS}/{run['id']}/submit", world.maya, {})
    assert submitted.status_code == 200, submitted.text
    decided = approve(world.app, str(submitted.json()["approval_request_id"]), world.marcus)
    assert decided.status_code == 200, decided.text
    requested = post(world.app, f"{JOURNAL_RUNS}/{run['id']}/export", world.maya, {})
    assert requested.status_code == 202, requested.text
    _job(world, str(requested.json()["id"]))
    return _run(world, run["id"])


def _lines(world: World, run_id: str) -> list[dict[str, Any]]:
    listed = get(world.app, f"{JOURNAL_RUNS}/{run_id}/lines", world.maya, {"limit": 200})
    assert listed.status_code == 200, listed.text
    return sorted(listed.json()["items"], key=lambda item: item["line_no"])


def _amounts(lines: list[dict[str, Any]], kind: str) -> list[tuple[str, str, str]]:
    return [
        (line["account"]["code"], line[f"debit_{kind}"]["amount"], line[f"credit_{kind}"]["amount"])
        for line in lines
    ]


def _downloaded(world: World, batch: dict[str, Any]) -> tuple[list[list[str]], dict[str, Any]]:
    """The REQ-JE-011 file of a batch: the CSV's rows (header first) and the manifest."""
    response = get(world.app, f"{BATCHES}/{batch['id']}/download", world.maya)
    assert response.status_code == 200, response.text
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    name = str(batch["external_id"]).replace(":", "_")
    rows = list(csv.reader(io.StringIO(archive.read(f"{name}.csv").decode("utf-8"))))
    return rows, dict(json.loads(archive.read(f"{name}.manifest.json")))


@pytest.mark.slow
@pytest.mark.parametrize("code", sorted(LEDGERS))
def test_r110_a_foreign_currency_entity_s_batches_reach_the_ledger_in_its_functional_currency(
    world: World, monkeypatch: pytest.MonkeyPatch, code: str
) -> None:
    """Supervisor ruling R-110, through each ERP adapter and the CSV.

    1. July's batch carries both amounts: the ledger receives GBP 43,740.00, with USD 54,000.00
       as information.
    2. August's batch — the two ``FX_REMEASUREMENT`` lines of GBP 1,080.00 — is received with its
       amounts and acknowledged; the run, the batch key and the external id are what they were.
    3. Every entry's functional debits equal its credits in the chunk the ledger receives
       (ADP-11): nothing is converted, no rounding line arises.
    4. The CSV states both amounts of every line; its manifest both totals.
    5. The trial balance pulled for August answers GBP alone, so ``attach-trial-balance`` is not
       refused (BUILD_SPEC CLO-17 ``CURRENCY_NOT_FUNCTIONAL``), and the settlement is in the
       ledger: accounts 4000 and 7200 tie. Account 2100 is the row of the contract liability
       role (the role basis; supervisor rulings R-69 (a), R-74): the ledger holds the invoice the
       ERP posts itself, and the row differs by July's period-end remeasurement, which this
       world — journal runs and no close run — never posts.
    """
    ledger = LEDGERS[code]
    contract_id, _group_id = delivered(world)
    _recorded(world, contract_id, 3, _invoice("INV-UK-7001", "2026-08-20", "54000.00"))
    connection_id, sent = _connected(world, ledger, monkeypatch)

    runs: dict[str, dict[str, Any]] = {}
    for period_key, document in zip((JULY, AUGUST), ledger.documents, strict=True):
        run = _calculated(world, period_key)
        [batch] = run["batches"]
        # one batch per run and transaction currency, as before the ruling (04 T-SL-07)
        assert (batch["adapter"], batch["txn_currency"], batch["functional_currency"]) == (
            code,
            "USD",
            "GBP",
        )
        assert (batch["batch_no"], batch["chunk_no"], batch["line_count"]) == (1, 1, 2)
        assert batch["external_id"].endswith(f":{run['run_no']}:1:1")
        shown = _exported(world, run)
        [exported] = shown["batches"]
        assert (shown["state"], exported["state"]) == ("acknowledged", "acknowledged")
        assert exported["external_id"] == batch["external_id"]
        # the ledger's own receipt: its document, recorded without a manual confirmation
        assert [
            (receipt["ack_kind"], receipt["gl_document_id"])
            for receipt in exported["acknowledgements"]
        ] == [("POSTED", document)]
        runs[period_key] = shown

    # 1 and 2: what each ledger received, in the order the batches were sent
    assert [ledger.stated(body) for body in sent.bodies] == [
        STATED[code][JULY],
        STATED[code][AUGUST],
    ]

    # 3: the lines of each run as the product holds them, and each entry in balance
    july, august = _lines(world, runs[JULY]["id"]), _lines(world, runs[AUGUST]["id"])
    assert (_amounts(july, "txn"), _amounts(july, "functional")) == (JULY_TXN, JULY_FUNCTIONAL)
    assert (_amounts(august, "txn"), _amounts(august, "functional")) == (
        AUGUST_TXN,
        AUGUST_FUNCTIONAL,
    )
    assert {line["je_type"] for line in august} == {"automated"}
    for lines in (july, august):
        entries: dict[str, Decimal] = {}
        for line in lines:
            net = Decimal(line["debit_functional"]["amount"]) - Decimal(
                line["credit_functional"]["amount"]
            )
            entries[line["je_no"]] = entries.get(line["je_no"], Decimal(0)) + net
        assert len(entries) == 1 and set(entries.values()) == {Decimal(0)}

    # 4: the CSV of both batches
    for period_key, txn, functional, totals in (
        (JULY, JULY_TXN, JULY_FUNCTIONAL, ("54000.00", "43740.00")),
        (AUGUST, AUGUST_TXN, AUGUST_FUNCTIONAL, ("0.00", "1080.00")),
    ):
        [batch] = runs[period_key]["batches"]
        [header, *rows], manifest = _downloaded(world, batch)
        assert header[11:] == ["functional_currency", "debit_functional", "credit_functional"]
        assert [(row[2], row[11]) for row in rows] == [("USD", "GBP")] * 2
        assert [(row[5], row[6], row[7]) for row in rows] == txn
        assert [(row[5], row[12], row[13]) for row in rows] == functional
        assert (manifest["currency"], manifest["functional_currency"]) == ("USD", "GBP")
        assert (manifest["totals"], manifest["totals_functional"]) == (
            {"debit": totals[0], "credit": totals[0]},
            {"debit": totals[1], "credit": totals[1]},
        )

    # 5: the pull of August through the product's own command. On the role basis (04 T-CLS-06
    # rev 1.253) account 2100 is the row of the contract liability role. The subledger states the
    # stored closing balance: billed USD 54,000.00 less revenue USD 54,000.00, nothing. The ledger
    # holds the two batches and the invoice the ERP posts itself:
    #     43,740.00 + 1,080.00 - 45,360.00 = -540.00.
    # What is left is July's period-end remeasurement — the layer carried at the July closing
    # rate, 44,280.00 against 43,740.00 — which only a close run of July posts, and this world
    # runs none; with it the account is at nothing:
    #     43,740.00 + 540.00 + 1,080.00 - 45,360.00 = 0.00.
    # The ERP's own invoice raises no item (R-74 (d)). Until the role basis the row compared the
    # account's lines on both sides, 44,820.00 and 44,820.00, and tied by construction: STALE
    # EXPECTATION by the supervisor's ruling of 2026-10-02 01:41 under R-69 (a) and R-74.
    _erp_books_its_invoice(world, ledger)
    draft = recon.generated(
        world.app,
        world.maya,
        _runtime(world),
        entity_code=ENTITY,
        period_key=AUGUST,
        kind=recon.SUBLEDGER_TO_GL,
    )
    pulled = recon.attached(
        world.app,
        world.maya,
        _runtime(world),
        draft["id"],
        {"source": "ADAPTER", "integration_connection_id": connection_id},
    )
    assert (pulled["status"], pulled["variance_count"]) == ("DRAFT", 1)
    assert pulled["sync_run_id"] is not None
    assert [
        (
            total["account_code"],
            total["currency"],
            total["subledger_amount"]["amount"],
            total["source_amount"]["amount"],
            total["difference"]["amount"],
        )
        for total in pulled["totals"]
    ] == [
        ("2100", "GBP", "0.00", "-540.00", "-540.00"),
        ("4000", "GBP", "-43740.00", "-43740.00", "0.00"),
        ("7200", "GBP", "-1080.00", "-1080.00", "0.00"),
    ]
    (item,) = recon.items_of(world.app, world.maya, draft["id"])
    assert (
        item["item_kind"],
        item["account_code"],
        item["account_role"],
        item["difference"]["amount"],
    ) == ("OTHER", "2100", "CONTRACT_LIABILITY", "-540.00")


# --- the same world with July's close: account 2100 ties (the supervisor's ruling of 2026-10-02
# 01:41, R3, with item REC-GEN-LOCK-1) ---------------------------------------------------------


def _ledger_by_account(world: World, through: date) -> dict[str, Decimal]:
    """What the subledger's ledger holds on each account at ``through`` in GBP, debit positive:
    the sum of its ASC 606 lines dated on or before that day (AVM-UK is the world's one
    entity)."""
    rows = world.place.rows(
        select(gl_account.c.code, func.sum(subledger_line.c.amount_functional).label("net"))
        .select_from(
            subledger_line.join(
                gl_account,
                and_(
                    gl_account.c.tenant_id == subledger_line.c.tenant_id,
                    gl_account.c.id == subledger_line.c.gl_account_id,
                ),
            )
        )
        .where(subledger_line.c.book_code == "ASC606", subledger_line.c.effective_date <= through)
        .group_by(gl_account.c.code)
    )
    return {str(row["code"]): Decimal(row["net"]).quantize(Decimal("0.01")) for row in rows}


def _the_ledger_holds_every_journal(world: World) -> None:
    """Every journal run of the workspace is acknowledged by the ledger, as the lock tests state
    it until the acknowledgement path is the product's (``support.close_world.acknowledge_run``)."""
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        for run_id in session.scalars(select(journal_run.c.id).order_by(journal_run.c.id)).all():
            acknowledge_run(session, UUID(str(run_id)), now=world.place.clock.now())


@pytest.mark.slow
def test_role_basis_a_foreign_currency_entity_ties_once_julys_close_has_run(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The world of R-110's witness with the one thing it leaves out: July's close run. Then the
    subledger-to-GL reconciliation of August ties on the role basis, and account 2100 — the row
    of the contract liability role — is at nothing on both sides (supervisor rulings R-69 (a),
    R-74; the ruling of 2026-10-02 01:41, R3).

    - July's close run SUCCEEDS. Its FX pass posts the period-end remeasurement of the asset
      layer, USD 54,000.00 carried at the July closing rate 0.82 against the average 0.81: Dr
      2100 / Cr 7200 GBP 540.00, dated 31 July. Its reclass presents the layer as a contract
      asset on 31 July (Dr 1200 / Cr 2100 GBP 44,280.00) and takes that back on 1 August.
    - 20 August: INV-UK-7001 settles the layer at spot 0.84, 45,360.00 against 44,280.00 — Dr
      2100 / Cr 7200 GBP 1,080.00, posted at compute.
    - At 31 August the subledger's ledger holds 43,740.00 + 540.00 + 1,080.00 = 45,360.00 on
      account 2100, and the ERP — which posts the invoice itself under ``billing.posting = ERP``
      — credits it with the same 45,360.00: a ledger the ERP keeps holds 0.00.
    - The subledger states the stored closing contract liability: billed USD 54,000.00 less
      revenue USD 54,000.00, 0.00. The row ties, and so does every other: variance 0, no item.

    In R-110's witness, which runs journal runs and no close run, the same row differs by the
    540.00 this run posts (``test_r110_...``, step 5)."""
    contract_id, _group_id = delivered(world)

    # --- July's close run: the period-end remeasurement is posted --------------------------------
    runs.unattended(monkeypatch)
    run_id, job_id = runs.started(world.app, world.maya, entity_code=ENTITY, period_key=JULY)
    runs.work(world.place.tenant_id, _runtime(world), job_id)
    july = runs.shown(world.app, world.maya, run_id)
    assert (july["status"], july["current_step_code"]) == ("SUCCEEDED", None), july
    assert [
        (
            str(line["entry_kind"]),
            line["period_key"],
            line["account_code"],
            Decimal(line["amount_functional"]),
            str(line["effective_date"]),
        )
        for line in runs.posted(world.place.tenant_id, run_id)
    ] == [
        ("FX_REMEASUREMENT", JULY, "2100", Decimal("540.00"), "2026-07-31"),
        ("FX_REMEASUREMENT", JULY, "7200", Decimal("-540.00"), "2026-07-31"),
        ("NETTING_RECLASS_REVERSAL", AUGUST, "1200", Decimal("-44280.00"), "2026-08-01"),
        ("NETTING_RECLASS_REVERSAL", AUGUST, "2100", Decimal("44280.00"), "2026-08-01"),
        ("NETTING_RECLASS", JULY, "1200", Decimal("44280.00"), "2026-07-31"),
        ("NETTING_RECLASS", JULY, "2100", Decimal("-44280.00"), "2026-07-31"),
    ]
    assert _ledger_by_account(world, date(2026, 7, 31)) == {
        "1200": Decimal("44280.00"),  # the layer at the July closing rate, presented as an asset
        "2100": Decimal("0.00"),
        "4000": Decimal("-43740.00"),
        "7200": Decimal("-540.00"),
    }

    # --- 20 August: the invoice settles the layer at spot ----------------------------------------
    _recorded(world, contract_id, 3, _invoice(ERP_INVOICE, ERP_INVOICE_DATE, "54000.00"))
    posted = _ledger_by_account(world, date(2026, 8, 31))
    assert posted == {
        "1200": Decimal("0.00"),
        "2100": Decimal("45360.00"),  # 43,740.00 + 540.00 + 1,080.00
        "4000": Decimal("-43740.00"),
        "7200": Decimal("-1620.00"),  # 540.00 + 1,080.00
    }
    assert posted["2100"] == ERP_INVOICE_GBP  # the layer is settled at what the ERP invoices

    # --- the ledger the ERP keeps: every journal, and the invoice the ERP posts itself -----------
    _calculated(world, AUGUST)  # August's lines journalised; July's were by the close run
    _the_ledger_holds_every_journal(world)
    stated = {**posted, "2100": posted["2100"] - ERP_INVOICE_GBP}
    assert stated["2100"] == Decimal("0.00")

    # --- August's reconciliation on the role basis ------------------------------------------------
    draft = recon.generated(
        world.app,
        world.maya,
        _runtime(world),
        entity_code=ENTITY,
        period_key=AUGUST,
        kind=recon.SUBLEDGER_TO_GL,
    )
    content = recon.trial_balance_csv([(code, "GBP", stated[code]) for code in sorted(stated)])
    file_id = recon.uploaded(world.app, world.maya, "avm-uk-tb-2026-08.csv", content)
    compared = recon.attached(
        world.app, world.maya, _runtime(world), draft["id"], {"file_id": file_id}
    )
    assert (compared["status"], compared["variance_count"]) == ("DRAFT", 0)
    assert [
        (
            total["account_code"],
            total["account_role"],
            total["currency"],
            total["subledger_amount"]["amount"],
            total["source_amount"]["amount"],
            total["difference"]["amount"],
        )
        for total in compared["totals"]
    ] == [
        ("1200", "CONTRACT_ASSET", "GBP", "0.00", "0.00", "0.00"),
        ("2100", "CONTRACT_LIABILITY", "GBP", "0.00", "0.00", "0.00"),
        ("4000", None, "GBP", "-43740.00", "-43740.00", "0.00"),
        ("7200", None, "GBP", "-1620.00", "-1620.00", "0.00"),
    ]
    assert recon.items_of(world.app, world.maya, draft["id"]) == []
