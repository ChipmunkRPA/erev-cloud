"""CLO-17 subledger-to-GL reconciliation and auto-certification (BUILD_SPEC CLO-17 acceptance; 03
REQ-CLS-016, REQ-CLS-017, REQ-INT-009; 04 T-CLS-06, T-CLS-07, T-INT-02, §16.8
API-S-ReconciliationAttach; PRD J-13.10 to J-13.12, WLD-B-07, WLD-F-32; SCREENS_B §2.2; controls
CTL-025, CTL-026; supervisor rulings R-38 (v), R-54 (e), R-58 (e), R-69 and R-74).

Worlds, each through the product's own commands:

- ``_january``: ``worlds.k01_pellworth`` through 31 Jan 2026. The January journal run holds every
  January line of AVM-US: the revenue of the month, Dr contract liability 2100 / Cr revenue 4010
  (INV-US-1001 is ingested and not posted: ``billing.posting = ERP``, POLICIES JET-03). The run is
  the oracle of the subledger's posted lines by account: its lines through
  ``GET /journal-runs/{id}/lines``, debits less credits. On the role basis (supervisor rulings
  R-69 (a), R-74) the contract liability is compared per role: the subledger states the stored
  closing contract balance — INV-US-1001 120,000.00 less the month's revenue, the −103,430.14
  ruling R-69 measured — and a ledger the ERP keeps holds the same, because the ERP posts its own
  invoice to account 2100 (``_held``).
- a GL the test states: ``_Ledger`` answers ``GLAdapter.pull_trial_balance`` for the ``NETSUITE``
  code (registered as a composition root registers an adapter, DG-LAY-03) through a NetSuite
  connection an Integration Admin created; an upload states the same balances as a file.
- ``support.reconciliations.ingested_k01`` for the auto-certification of a billing reconciliation.
- the NetSuite mock with WLD-F-32 for CTL-025: lane F-CLO-A's BUILD_SPEC CLO-15 (module note at
  ``test_ctl_025_direct_gl_entry_flagged``).

Amounts are debit positive and credit negative; ``difference`` = GL − subledger.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.adapters import mocks
from erev_api.adapters.gl import netsuite
from erev_api.adapters.mocks import netsuite as ns_mock
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    combination_group,
    contract,
    contract_event,
    customer,
    gl_account,
    job,
    journal_batch,
    legal_entity,
    reconciliation,
    signoff,
    sync_run,
    tenant,
)
from erev_api.domain.close import reconciliations as reconciliation_domain
from erev_api.domain.journals import export
from erev_api.domain.journals import ports as gl_ports
from erev_api.domain.reports import tie_outs
from erev_api.enums import ContractEventType, GlAdapter, RuleSetKind
from erev_api.events.payloads import BillingRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from erev_api.money import MoneyIn
from erev_api.problems import ProblemError
from fastapi import FastAPI
from sqlalchemy import insert, select, update
from support import close_run_worlds, worlds
from support import close_runs as runs
from support import reconciliations as recon
from support.close_world import JOURNAL_RUNS, acknowledge_run, actor_with_role
from support.db import TestDatabase
from support.factories import appended, k11_world
from support.http import HttpResponse, asgi_client
from support.principals import carrying, colleague, enrolled
from support.reference import approve, assign, get, holding, patch, post, slug
from support.rows import (
    combination_group_values,
    contract_values,
    customer_values,
    legal_entity_values,
    publish_rule_set,
)
from support.shred_in_flight import beside_a_shred
from support.worlds import K01, ReportWorld, journal_run, k01_pellworth

JANUARY = "FY2026-P01"
AUGUST = "FY2026-P08"
SEPTEMBER = "FY2026-P09"
USD = "USD"
INTEGRATIONS = "/api/v1/integrations"
RECONCILIATIONS = "/api/v1/reconciliations"
RULE_SETS = "/api/v1/rule-sets"
VERSIONS = "/api/v1/rule-set-versions"
MOCK_BASE = f"{mocks.MOCKS_PREFIX}{ns_mock.PREFIX}"
# PRD WLD-B-07 / WLD-F-32: the direct GL entry of the NetSuite trial balance.
DIRECT_DOCUMENT = "JE-NS-88121"
DIRECT_AMOUNT = Decimal("250.00")
DIRECT_ACCOUNT = "2100"
# PRD WLD-K-01: INV-US-1001 120,000.00 of 01 Jan 2026. Under ``billing.posting = ERP`` the ERP
# posts it itself — Dr receivable / Cr contract liability 2100 (POLICIES JET-03; supervisor ruling
# R-74 (e)) — and the subledger holds it in the stored contract balance, not in a line.
INVOICE_NUMBER = "INV-US-1001"
INVOICE_AMOUNT = Decimal("120000.00")
LIABILITY = "2100"
RECEIVABLE = "1100"  # WLD-K-01 chart: accounts receivable, which the ERP keeps
CL = "CONTRACT_LIABILITY"
CA = "CONTRACT_ASSET"
UR = "UNBILLED_RECEIVABLE"
# PRD J-13.11: Maya's explanation of the difference.
EXPLANATION = "Manual accrual posted in NetSuite by AP; reversed on 01 Oct 2026 by JE-NS-88410."
# BUILD_SPEC CLO-17, BS4-D-09: rule AUTO-REC-01 version 1.
AUTO_REC_01: dict[str, Any] = {
    "rule_key": "AUTO-REC-01",
    "priority": 0,
    "conditions": [
        {"field": "reconciliation.kind", "op": "eq", "value": "BILLING_TO_SUBLEDGER"},
        {"field": "reconciliation.variance_count", "op": "eq", "value": 0},
    ],
    "outputs": {"auto_approve": True},
}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def runtime(clock: FrozenClock, keyring: KeyRing, files: LocalFileStore) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=files)


def _money(amount: Decimal | str, currency: str = USD) -> dict[str, str]:
    return {"amount": format(Decimal(amount).quantize(Decimal("0.01")), "f"), "currency": currency}


def _rows(tenant_id: UUID, statement: Any) -> list[dict[str, Any]]:
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


# --- the January world and its journal ------------------------------------------------------------


def _january(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> ReportWorld:
    """WLD-K-01 through 31 Jan 2026 (module docstring); Priya also holds Revenue Reviewer
    (``journal.approve``, ``recon.signoff``; PRD ACT-34)."""
    world = k01_pellworth(app, keyring, clock, files, through=date(2026, 1, 31))
    assign(world.priya.member, "revenue_reviewer")
    return world


def _net_by_account(world: ReportWorld, run_id: str) -> dict[str, Decimal]:
    """The run's functional amount by account code, debits less credits: what the subledger holds
    on each account, because the run journalises every line of the period."""
    listed = get(world.app, f"{JOURNAL_RUNS}/{run_id}/lines", world.maya, {"limit": 200})
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["next_cursor"] is None, "the run's lines fit one page"
    net: dict[str, Decimal] = {}
    for line in body["items"]:
        assert line["debit_functional"]["currency"] == USD
        code = str(line["account"]["code"])
        net[code] = (
            net.get(code, Decimal(0))
            + Decimal(line["debit_functional"]["amount"])
            - Decimal(line["credit_functional"]["amount"])
        )
    return net


def _january_run(world: ReportWorld) -> tuple[dict[str, Any], dict[str, Decimal]]:
    """The January journal run as calculated (``draft``) and its amounts by account."""
    run = journal_run(world, period_key=JANUARY)
    net = _net_by_account(world, str(run["id"]))
    # Revenue relieves the contract liability: one debit and one credit of the same amount.
    assert set(net) == {"2100", "4010"}
    assert net["2100"] > 0 and net["2100"] == -net["4010"]
    return run, net


def _shown_run(world: ReportWorld, run_id: str) -> dict[str, Any]:
    shown = get(world.app, f"{JOURNAL_RUNS}/{run_id}", world.maya)
    assert shown.status_code == 200, shown.text
    return dict(shown.json())


def _approved(world: ReportWorld, run: Mapping[str, Any]) -> dict[str, Any]:
    """Maya submits the run and Priya approves it: its batch is ``approved`` and not exported."""
    submitted = post(world.app, f"{JOURNAL_RUNS}/{run['id']}/submit", world.maya, {})
    assert submitted.status_code == 200, submitted.text
    decided = approve(world.app, str(submitted.json()["approval_request_id"]), world.priya)
    assert decided.status_code == 200, decided.text
    shown = _shown_run(world, str(run["id"]))
    assert (shown["state"], [batch["state"] for batch in shown["batches"]]) == (
        "approved",
        ["approved"],
    )
    return shown


def _acknowledged(world: ReportWorld, run: Mapping[str, Any], clock: FrozenClock) -> None:
    """The GL holds the run: acknowledged, as the lock tests state it until BUILD_SPEC CLO-14's
    acknowledgement path (``support.close_world.acknowledge_run``)."""
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        acknowledge_run(session, UUID(str(run["id"])), now=clock.now())


def _generated(
    world: ReportWorld, runtime: JobRuntime, period_key: str = JANUARY
) -> dict[str, Any]:
    """A subledger-to-GL reconciliation as generated: a draft without a source."""
    draft = recon.generated(
        world.app,
        world.maya,
        runtime,
        entity_code="AVM-US",
        period_key=period_key,
        kind=recon.SUBLEDGER_TO_GL,
    )
    assert (draft["kind"], draft["status"], draft["totals"], draft["variance_count"]) == (
        "SUBLEDGER_TO_GL",
        "DRAFT",
        [],
        0,
    )
    assert (draft["source_file_id"], draft["sync_run_id"], draft["is_current"]) == (
        None,
        None,
        True,
    )
    # Nothing is compared yet: no key figures, and no attach request was made.
    assert (draft["summary"], draft["trial_balance"]) == ([], None)
    return draft


def _facts(item: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        item["item_kind"],
        item["account_code"],
        item["subledger_amount"],
        item["source_amount"],
        item["difference"],
        item["gl_document_reference"],
        item["is_high_risk"],
    )


def _key_figures(
    accounts: int, subledger: Decimal | str, stated: Decimal | str, currency: str = USD
) -> dict[str, Any]:
    """One API-S-Reconciliation ``summary`` row: the sums of the currency's ``totals`` rows."""
    return {
        "currency": currency,
        "account_count": accounts,
        "subledger_amount": _money(subledger, currency),
        "source_amount": _money(stated, currency),
        "difference": _money(Decimal(stated) - Decimal(subledger), currency),
        "not_stated_count": 0,
    }


def _listed(world: ReportWorld, **filters: str) -> list[str]:
    """The reconciliation numbers ``GET /reconciliations`` answers for AVM-US January, oldest
    first."""
    found = get(
        world.app,
        RECONCILIATIONS,
        world.maya,
        {"entity": "AVM-US", "period": JANUARY, "sort": "id", **filters},
    )
    assert found.status_code == 200, found.text
    return [str(item["reconciliation_no"]) for item in found.json()["items"]]


def _total(
    account: str,
    subledger: Decimal | None,
    stated: Decimal | None,
    *,
    role: str | None = None,
    currency: str = USD,
) -> dict[str, Any]:
    """One API-S-Reconciliation ``totals`` row: an account row, or — with ``role`` — the row of a
    contract balance role that has this one account."""
    difference = (stated or Decimal(0)) - (subledger or Decimal(0))
    return {
        "account_code": account,
        "account_role": role,
        "account_codes": [] if role is None else [account],
        "currency": currency,
        "subledger_amount": None if subledger is None else _money(subledger, currency),
        "source_amount": None if stated is None else _money(stated, currency),
        "difference": _money(difference, currency),
        "not_stated": None,
    }


def _held(net: Mapping[str, Decimal]) -> dict[str, Decimal]:
    """What the subledger states by account for January on the role basis: the contract liability
    2100 is the stored closing contract balance — the posted revenue of the month against
    INV-US-1001, a credit of 103,430.14 (supervisor ruling R-69's measurement) — and every other
    account its posted lines. A ledger the ERP keeps, holding the January run and the ERP's own
    invoice, states the same."""
    held = dict(net)
    held[LIABILITY] = net[LIABILITY] - INVOICE_AMOUNT
    assert held[LIABILITY] == Decimal("-103430.14")
    return held


def _totals(held: Mapping[str, Decimal], stated: Mapping[str, Decimal]) -> list[dict[str, Any]]:
    """The January ``totals`` rows: the contract liability as a role row, the rest by account."""
    return [
        _total(code, held[code], stated[code], role=CL if code == LIABILITY else None)
        for code in sorted(held)
    ]


# --- a GL the tests state -------------------------------------------------------------------------


@dataclass
class _Ledger:
    """What ``pull_trial_balance`` answers, and what it was asked."""

    lines: tuple[gl_ports.TrialBalanceLine, ...] = ()
    details: tuple[gl_ports.TrialBalanceDetail, ...] = ()
    failure: Exception | None = None
    asked: list[tuple[str, str, date, date, tuple[str, ...]]] = field(default_factory=list)

    def factory(self, context: gl_ports.GLContext) -> gl_ports.GLAdapter:
        return _LedgerAdapter(self)


class _LedgerAdapter:
    """The ``GLAdapter`` of ``_Ledger``: only the trial balance is served."""

    code: gl_ports.AdapterCode = "NETSUITE"

    def __init__(self, ledger: _Ledger) -> None:
        self._ledger = ledger

    def validate_accounts(
        self, accounts: Sequence[gl_ports.AccountRef], dimensions: Sequence[gl_ports.DimensionRef]
    ) -> gl_ports.ValidationResult:
        raise NotImplementedError

    def post_chunk(self, chunk: gl_ports.JournalChunk) -> gl_ports.PostingResult:
        raise NotImplementedError

    def get_posting(self, external_id: str) -> gl_ports.PostingResult | None:
        raise NotImplementedError

    def pull_chart_of_accounts(self) -> Sequence[gl_ports.AccountRef]:
        raise NotImplementedError

    def pull_trial_balance(
        self, entity: gl_ports.EntityRef, period: gl_ports.PeriodRef, accounts: Sequence[str]
    ) -> gl_ports.TrialBalance:
        ledger = self._ledger
        ledger.asked.append(
            (entity.code, period.period_key, period.start_date, period.end_date, tuple(accounts))
        )
        if ledger.failure is not None:
            raise ledger.failure
        return gl_ports.TrialBalance(
            entity_code=entity.code,
            period_key=period.period_key,
            balances={line.account_code: line.amount for line in ledger.lines},
            lines=ledger.lines,
            details=ledger.details,
        )


def _netsuite_connection(
    app: FastAPI, clock: FrozenClock, tenant_id: UUID, **over: Any
) -> dict[str, Any]:
    """An ``ACTIVE`` GL connection of the tenant, created and enabled by an Integration Admin
    (``integration.manage``; PRD ACT-45)."""
    nikhil = actor_with_role(app, clock, tenant_id, "integration_admin", name="nikhil")
    body: dict[str, Any] = {
        "code": "netsuite-avenmoor",
        "name": "NetSuite (mock)",
        "adapter": "NETSUITE",
        "direction": "BOTH",
        "base_url": MOCK_BASE,
    }
    body.update(over)
    created = post(app, INTEGRATIONS, nikhil, body)
    assert created.status_code == 201, created.text
    enabled = patch(
        app,
        f"{INTEGRATIONS}/{created.json()['id']}",
        nikhil,
        {"status": "ACTIVE"},
        if_match='"r1"',
    )
    assert enabled.status_code == 200, enabled.text
    return dict(enabled.json())


def _stated_with_the_direct_entry(
    run: Mapping[str, Any], net: Mapping[str, Decimal]
) -> tuple[tuple[gl_ports.TrialBalanceLine, ...], tuple[gl_ports.TrialBalanceDetail, ...]]:
    """A GL the ERP keeps, holding the January run, the ERP's own invoice and WLD-B-07's
    document: the closing balances (2100 carries 250.00 more than the subledger) and the documents
    of the period — the run's own, under its ADP-10 external id; ``INV-US-1001`` as the ERP posts
    it to the contract liability account (supervisor ruling R-74 (e)); and ``JE-NS-88121``, made
    in the ERP."""
    (batch,) = run["batches"]
    stated = _held(net)
    stated[DIRECT_ACCOUNT] += DIRECT_AMOUNT
    lines = tuple(
        gl_ports.TrialBalanceLine(account_code=code, currency=USD, amount=amount)
        for code, amount in sorted(stated.items())
    )
    own = tuple(
        gl_ports.TrialBalanceDetail(
            account_code=code,
            currency=USD,
            amount=amount,
            document_reference="JE-NS-88001",
            external_id=str(batch["external_id"]),
            posted_date=date(2026, 1, 31),
        )
        for code, amount in sorted(net.items())
    )
    invoice = gl_ports.TrialBalanceDetail(
        account_code=LIABILITY,
        currency=USD,
        amount=-INVOICE_AMOUNT,
        document_reference=INVOICE_NUMBER,
        external_id=None,
        posted_date=date(2026, 1, 1),
    )
    direct = gl_ports.TrialBalanceDetail(
        account_code=DIRECT_ACCOUNT,
        currency=USD,
        amount=DIRECT_AMOUNT,
        document_reference=DIRECT_DOCUMENT,
        external_id=None,
        posted_date=date(2026, 1, 28),
    )
    return lines, (*own, invoice, direct)


def _erp_books_its_invoices(app: FastAPI, world: ReportWorld, tenant_code: str) -> list[str]:
    """WLD-K-01 keeps ``billing.posting = ERP``: the ERP books its own invoices — Dr receivable /
    Cr contract liability, at the issue date (supervisor ruling R-74 (e)). The mock ledger holds a
    document made in the ERP only when it is told one (``POST /__erp/documents``), so the world's
    billing events are stated to it as the ERP posts them; their numbers are returned."""
    billed = _rows(
        world.tenant_id,
        select(contract_event.c.payload, contract_event.c.effective_date)
        .where(contract_event.c.event_type == ContractEventType.BILLING_RECORDED.value)
        .order_by(contract_event.c.effective_date, contract_event.c.record_seq),
    )
    numbers: list[str] = []
    with asgi_client(app) as client:
        for row in billed:
            payload, issued = row["payload"], row["effective_date"]
            amount = Decimal(str(payload["amount"]["amount"]))
            told = client.post(
                f"{MOCK_BASE}/__erp/documents",
                json={
                    "account": tenant_code,
                    "subsidiary": "AVM-US",
                    "reference": str(payload["invoice_number"]),
                    "date": issued.isoformat(),
                    "period": f"FY{issued.year}-P{issued.month:02d}",
                    "currency": USD,
                    "lines": [
                        {"account": RECEIVABLE, "amount": str(amount)},
                        {"account": LIABILITY, "amount": str(-amount)},
                    ],
                },
            )
            assert told.status_code == 201, told.text
            numbers.append(str(payload["invoice_number"]))
    return numbers


# --- CTL-025: the NetSuite mock -------------------------------------------------------------------


@pytest.mark.control("CTL-025")
def test_ctl_025_direct_gl_entry_flagged(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUILD_SPEC CLO-17, control CTL-025: a ``SUBLEDGER_TO_GL`` reconciliation for AVM-US Sep 2026
    with the trial balance pulled from the NetSuite mock (WLD-F-32) shows one item
    ``DIRECT_GL_ENTRY`` on account 2100, difference 250.00, ``is_high_risk = true``,
    ``gl_document_reference = 'JE-NS-88121'`` (REQ-CLS-016; PRD J-13.11).

    The GL is the NetSuite mock itself: the world's journal runs are posted to it through the
    ``NETSUITE`` adapter (``post_chunk``, as the export relay posts a chunk), and the mock's trial
    balance is what was posted to it through the period plus the direct entry of its WLD-F-32
    fixture (supervisor ruling R-54 (e) and its requirement on BUILD_SPEC CLO-15).

    The ledger is one the ERP keeps (STALE TEST WORLD under supervisor ruling R-69; the
    supervisor's ruling of 2026-10-01 21:23): WLD-K-01 is in ERP billing mode, so NetSuite itself
    books INV-US-1001 and INV-US-1044 to the contract liability account, and on the role basis
    the row of that role states the stored closing balance, which carries them. The mock holds an
    ERP's own document only when told, so the world tells it both. The expectation stands: one
    ``DIRECT_GL_ENTRY`` of 250.00 on account 2100."""
    world = k01_pellworth(app, keyring, clock, files)
    tenant_id = world.tenant_id
    monkeypatch.setitem(
        gl_ports.GL_ADAPTERS,
        GlAdapter.NETSUITE,
        netsuite.netsuite_factory(asgi_client(app), MOCK_BASE),
    )
    # WLD-K-01 posts revenue in every month from January to September: each period is journalised
    # and held by the GL, so the GL's closing balances of September are the subledger's.
    runs = [journal_run(world, period_key=f"FY2026-P{month:02d}") for month in range(1, 10)]
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        tenant_code = str(
            session.execute(select(tenant.c.code).where(tenant.c.id == tenant_id)).scalar_one()
        )
        chart = tuple(
            gl_ports.AccountRef(code=str(code), name=str(name))
            for code, name in session.execute(
                select(gl_account.c.code, gl_account.c.name).order_by(gl_account.c.code)
            )
        )
        adapter = gl_ports.gl_adapter_for(
            GlAdapter.NETSUITE, gl_ports.GLContext(tenant_code=tenant_code, accounts=chart)
        )
        batch_ids = session.execute(
            select(journal_batch.c.id)
            .where(journal_batch.c.journal_run_id.in_([UUID(str(run["id"])) for run in runs]))
            .order_by(journal_batch.c.external_id)
        ).scalars()
        for batch_id in list(batch_ids):
            posted = adapter.post_chunk(export.chunk_of(session, UUID(str(batch_id))))
            assert posted.status in ("POSTED", "DUPLICATE"), posted
        for run in runs:
            acknowledge_run(session, UUID(str(run["id"])), now=clock.now())
    assert _erp_books_its_invoices(app, world, tenant_code) == [INVOICE_NUMBER, "INV-US-1044"]
    connection = _netsuite_connection(app, clock, tenant_id)

    draft = _generated(world, runtime, SEPTEMBER)
    pulled = recon.attached(
        app,
        world.maya,
        runtime,
        draft["id"],
        {"source": "ADAPTER", "integration_connection_id": connection["id"]},
    )
    assert (pulled["status"], pulled["variance_count"]) == ("DRAFT", 1)
    assert pulled["sync_run_id"] is not None and pulled["source_file_id"] is None
    (item,) = recon.items_of(app, world.maya, draft["id"])
    assert (item["item_kind"], item["account_code"]) == ("DIRECT_GL_ENTRY", DIRECT_ACCOUNT)
    assert item["difference"] == _money(DIRECT_AMOUNT)
    assert item["is_high_risk"] is True
    assert item["gl_document_reference"] == DIRECT_DOCUMENT
    assert (item["subledger_amount"], item["source_amount"]) == (
        _money("0.00"),
        _money(DIRECT_AMOUNT),
    )
    assert (item["explanation"], item["resolved_at"]) == (None, None)
    differing = [total for total in pulled["totals"] if total["difference"] != _money("0.00")]
    assert [(total["account_code"], total["difference"]) for total in differing] == [
        (DIRECT_ACCOUNT, _money(DIRECT_AMOUNT))
    ]
    # The control's evidence: every account compared, one exception, the direct entry counted.
    (evidence,) = recon.control_executions(tenant_id, "CTL-025", draft["id"])
    assert (evidence["exception_count"], str(evidence["result"])) == (1, "FAIL")
    assert evidence["population_count"] == len(pulled["totals"])
    assert evidence["detail"]["direct_gl_entries"] == 1


# --- classification -------------------------------------------------------------------------------


def test_unposted_batch_classification(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore, runtime: JobRuntime
) -> None:
    """BUILD_SPEC CLO-17: subledger activity of an approved but unexported batch appears as
    ``UNPOSTED_BATCH`` with the batch amount as difference — one item per account the batch
    posts to, the batch's amount on the account against a GL that holds none of it."""
    world = _january(app, keyring, clock, files)
    run, net = _january_run(world)
    approved = _approved(world, run)
    (batch,) = approved["batches"]

    draft = _generated(world, runtime)
    held = _held(net)
    # The GL holds nothing of the January run yet: it states the invoice the ERP posted itself on
    # the contract liability account, and every other account at zero.
    without_the_run = {code: Decimal(0) for code in net} | {LIABILITY: -INVOICE_AMOUNT}
    nothing_posted = recon.trial_balance_csv(
        [(code, USD, without_the_run[code]) for code in sorted(net)]
    )
    file_id = recon.uploaded(app, world.maya, "avm-us-tb-2026-01.csv", nothing_posted)
    compared = recon.attached(app, world.maya, runtime, draft["id"], {"file_id": file_id})

    assert (compared["status"], compared["variance_count"]) == ("DRAFT", 2)
    assert (compared["source_file_id"], compared["sync_run_id"]) == (file_id, None)
    assert compared["totals"] == _totals(held, without_the_run)
    items = recon.items_of(app, world.maya, draft["id"])
    assert [_facts(item) for item in items] == [
        (
            "UNPOSTED_BATCH",
            code,
            _money(net[code]),
            _money("0.00"),
            _money(-net[code]),
            batch["external_id"],
            False,
        )
        for code in sorted(net)
    ]
    # The batch's debit of the contract liability is what the GL lacks on account 2100, and its
    # credit of revenue what it lacks on 4010: each difference is the batch's amount, reversed.
    liability, revenue = items
    assert Decimal(liability["difference"]["amount"]) == -net["2100"] < 0
    assert Decimal(revenue["difference"]["amount"]) == -net["4010"] > 0
    assert all(item["currency"] == USD and item["contract"] is None for item in items)
    # The batch's line on the contract liability account is an item of the role's row.
    assert [item["account_role"] for item in items] == [CL, None]
    # The items explain the whole difference of every account: nothing is left as OTHER.
    assert sum((Decimal(item["difference"]["amount"]) for item in items), Decimal(0)) == Decimal(0)
    (evidence,) = recon.control_executions(world.tenant_id, "CTL-025", draft["id"])
    assert (
        evidence["run_ref_type"],
        evidence["population_count"],
        evidence["exception_count"],
        str(evidence["result"]),
    ) == ("RECONCILIATION_RUN", 2, 2, "FAIL")
    assert (evidence["detail"]["direct_gl_entries"], evidence["detail"]["rows_not_compared"]) == (
        0,
        0,
    )
    # Auto-certification is a billing reconciliation's (REC-AUTO-GL-1): no CTL-026 execution here.
    assert recon.control_executions(world.tenant_id, "CTL-026", draft["id"]) == []

    # Once the GL acknowledges the batch and states its balances, nothing differs.
    _acknowledged(world, run, clock)
    again = _generated(world, runtime)
    posted = recon.trial_balance_csv([(code, USD, held[code]) for code in sorted(held)])
    clean = recon.attached(
        app,
        world.maya,
        runtime,
        again["id"],
        {"file_id": recon.uploaded(app, world.maya, "avm-us-tb-2026-01-posted.csv", posted)},
    )
    assert (clean["variance_count"], clean["status"]) == (0, "DRAFT")
    assert clean["totals"] == _totals(held, held)
    assert recon.items_of(app, world.maya, again["id"]) == []
    (passed,) = recon.control_executions(world.tenant_id, "CTL-025", again["id"])
    assert (passed["population_count"], passed["exception_count"], str(passed["result"])) == (
        2,
        0,
        "PASS",
    )
    assert recon.shown(app, world.maya, draft["id"])["is_current"] is False


def test_csv_trial_balance_upload(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUILD_SPEC CLO-17: ``attach-trial-balance`` with an uploaded CSV of account, currency and
    amount produces the same totals as the adapter pull for equal content. The pull also names the
    GL document, so its difference is a direct GL entry; the file names none, so its difference
    is ``OTHER``."""
    world = _january(app, keyring, clock, files)
    tenant_id = world.tenant_id
    run, net = _january_run(world)
    _acknowledged(world, run, clock)
    lines, details = _stated_with_the_direct_entry(_shown_run(world, str(run["id"])), net)
    ledger = _Ledger(lines=lines, details=details)
    monkeypatch.setitem(gl_ports.GL_ADAPTERS, GlAdapter.NETSUITE, ledger.factory)
    connection = _netsuite_connection(app, clock, tenant_id)

    first = _generated(world, runtime)
    pulled = recon.attached(
        app,
        world.maya,
        runtime,
        first["id"],
        {"source": "ADAPTER", "integration_connection_id": connection["id"]},
    )
    # REQ-INT-009: the pull asks for the subledger-controlled accounts of the entity and period —
    # the accounts the subledger posts to and those of the three contract balance roles (supervisor
    # ruling R-74 (b)): AVM-MAP-2026-01 gives the unbilled receivable 1210, which carries no line.
    # It also names 1200, the receivable the ERP keeps: not a controlled account.
    assert ledger.asked == [
        ("AVM-US", JANUARY, date(2026, 1, 1), date(2026, 1, 31), ("1210", "2100", "4010"))
    ]
    assert pulled["source_file_id"] is None
    (pull,) = _rows(tenant_id, select(sync_run).where(sync_run.c.id == UUID(pulled["sync_run_id"])))
    total = sum((line.amount for line in lines), Decimal(0))
    assert (str(pull["kind"]), str(pull["status"]), pull["record_count"]) == (
        "TRIAL_BALANCE_PULL",
        "SUCCEEDED",
        2,
    )
    assert str(pull["integration_connection_id"]) == connection["id"]
    assert pull["source_totals"] == pull["loaded_totals"]
    assert (pull["source_totals"]["count"], pull["source_totals"]["amount_by_currency"]) == (
        2,
        {USD: format(total, "f")},
    )
    assert pull["problem"] is None and pull["started_at"] is not None
    assert pull["finished_at"] is not None and pull["job_id"] is not None

    second = _generated(world, runtime)
    content = recon.trial_balance_csv(
        [(line.account_code, line.currency, line.amount) for line in lines]
    )
    file_id = recon.uploaded(app, world.maya, "avm-us-tb-2026-01.csv", content)
    read = recon.attached(app, world.maya, runtime, second["id"], {"file_id": file_id})

    assert read["totals"] == pulled["totals"]
    held = _held(net)
    assert pulled["totals"] == _totals(held, {line.account_code: line.amount for line in lines})
    assert [total["difference"] for total in pulled["totals"]] == [
        _money(DIRECT_AMOUNT),
        _money("0.00"),
    ]
    assert (read["source_file_id"], read["sync_run_id"]) == (file_id, None)
    assert (pulled["variance_count"], read["variance_count"]) == (1, 1)
    assert [_facts(item) for item in recon.items_of(app, world.maya, first["id"])] == [
        (
            "DIRECT_GL_ENTRY",
            DIRECT_ACCOUNT,
            _money("0.00"),
            _money(DIRECT_AMOUNT),
            _money(DIRECT_AMOUNT),
            DIRECT_DOCUMENT,
            True,
        )
    ]
    assert [_facts(item) for item in recon.items_of(app, world.maya, second["id"])] == [
        ("OTHER", DIRECT_ACCOUNT, None, None, _money(DIRECT_AMOUNT), None, False)
    ]
    # Both items belong to the row of the contract liability role.
    assert [
        item["account_role"]
        for found in (first, second)
        for item in recon.items_of(app, world.maya, found["id"])
    ] == [CL, CL]
    direct = {
        kind: recon.control_executions(tenant_id, "CTL-025", found["id"])[0]["detail"]
        for kind, found in (("pull", first), ("file", second))
    }
    assert (direct["pull"]["direct_gl_entries"], direct["file"]["direct_gl_entries"]) == (1, 0)
    # Supervisor ruling R-74 (d): INV-US-1001 is the ERP's own invoice — the stored balance holds
    # it — and raises no item; a file names no document.
    assert (
        direct["pull"]["erp_billing_documents"],
        direct["file"]["erp_billing_documents"],
    ) == (1, 0)
    assert (direct["pull"]["roles_not_stated"], direct["file"]["roles_not_stated"]) == (0, 0)
    # The later generation is the current one; both keep the trial balance they were given.
    assert [
        recon.shown(app, world.maya, found["id"])["is_current"] for found in (first, second)
    ] == [
        False,
        True,
    ]
    # SCREENS_B §2.1 reads the list with the filter: one current reconciliation per kind.
    assert _listed(world) == [first["reconciliation_no"], second["reconciliation_no"]]
    assert _listed(world, is_current="true") == [second["reconciliation_no"]]
    assert _listed(world, is_current="false") == [first["reconciliation_no"]]
    # SCREENS_B §2.2 key figures: the server's sums of `totals` — the subledger's revenue line
    # and the month's relief of the liability net to nothing, which leaves the invoice of
    # 120,000.00 in the stored balance; the GL states 250.00 more.
    assert pulled["summary"] == read["summary"] == [_key_figures(2, "-120000.00", "-119750.00")]
    # ... and the source of each: the connection the first was pulled through, the file the second
    # was given, each with the job of its request and the instant it was compared.
    taken = pulled["trial_balance"]
    assert (taken["source"], taken["file"]) == ("ADAPTER", None)
    assert taken["integration_connection"] == {"id": connection["id"], "name": "NetSuite (mock)"}
    assert (taken["job"]["id"], taken["job"]["state"], taken["job"]["problem"]) == (
        str(pull["job_id"]),
        "SUCCEEDED",
        None,
    )
    # The job is its requester's: Maya asked for the pull.
    assert (taken["job"]["created_by"]["id"], taken["job"]["created_by"]["kind"]) == (
        str(world.maya.member.user_id),
        "USER",
    )
    assert sorted(taken["job"]) == [
        "created_at",
        "created_by",
        "finished_at",
        "id",
        "problem",
        "state",
    ]
    # "pulled <time>": the end of the pull's sync run, which is when it was compared.
    assert datetime.fromisoformat(taken["attached_at"]) == pull["finished_at"]
    assert datetime.fromisoformat(taken["job"]["created_at"]) <= pull["finished_at"]
    given = read["trial_balance"]
    assert (given["source"], given["integration_connection"]) == ("FILE", None)
    assert given["file"] == {"id": file_id, "name": "avm-us-tb-2026-01.csv"}
    assert (given["job"]["state"], given["job"]["problem"]) == ("SUCCEEDED", None)
    (compared_at,) = [
        found["executed_at"]
        for found in recon.control_executions(tenant_id, "CTL-025", second["id"])
    ]
    assert datetime.fromisoformat(given["attached_at"]) == compared_at
    # Supervisor ruling R-68 (c): the connections a trial balance can be pulled through are named
    # to a preparer of the entity (Maya, `recon.prepare`) and to nobody else (Priya reviews).
    assert pulled["gl_connections"] == [{"id": connection["id"], "name": "NetSuite (mock)"}]
    reviewer = recon.shown(app, world.priya, first["id"])
    assert reviewer["gl_connections"] == []
    assert reviewer["trial_balance"] == pulled["trial_balance"]


def test_attach_is_refused_by_name(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """04 §16.8 API-S-ReconciliationAttach: the source is written once, on the current draft
    subledger-to-GL reconciliation, from one file or one GL connection that serves a trial balance;
    a file that cannot be compared is refused with its rows."""
    world = _january(app, keyring, clock, files)
    tenant_id = world.tenant_id
    run, net = _january_run(world)
    _acknowledged(world, run, clock)
    maya = world.maya
    held = _held(net)
    balances = [(code, USD, held[code]) for code in sorted(held)]
    good = recon.uploaded(app, maya, "tb.csv", recon.trial_balance_csv(balances))
    ledger = _Ledger()
    monkeypatch.setitem(gl_ports.GL_ADAPTERS, GlAdapter.NETSUITE, ledger.factory)
    connection = _netsuite_connection(app, clock, tenant_id)

    def refused(response: Any, status: int, problem: str) -> dict[str, Any]:
        assert (response.status_code, slug(response)) == (status, problem), response.text
        return dict(response.json())

    # A billing reconciliation takes no trial balance.
    billing = recon.generated(app, maya, runtime, entity_code="AVM-US", period_key=JANUARY)
    body = refused(
        recon.attach(app, maya, billing["id"], {"file_id": good}), 409, "invalid-transition"
    )
    assert "Only a subledger-to-GL one takes a trial balance." in body["detail"]

    draft = _generated(world, runtime)
    # One source, named: neither, both, a file of another purpose, an unknown connection.
    for wrong in (
        {},
        {"source": "ADAPTER"},
        {"file_id": good, "integration_connection_id": connection["id"]},
        {"file_id": good, "source": "ADAPTER"},
        {"file_id": str(tenant_id)},
        {"source": "ADAPTER", "integration_connection_id": str(tenant_id)},
    ):
        refused(recon.attach(app, maya, draft["id"], wrong), 422, "validation-failed")
    # A file that is no trial balance: every row that cannot be compared is named.
    euro = recon.uploaded(
        app,
        maya,
        "tb-eur.csv",
        recon.trial_balance_csv(
            [("1200", "EUR", "120000.00"), ("2100", USD, "1,000.00"), ("2100", USD, "5.00")]
        ),
    )
    body = refused(
        recon.attach(app, maya, draft["id"], {"file_id": euro}), 422, "validation-failed"
    )
    assert [(error["row"], error["field"], error["sheet"]) for error in body["errors"]] == [
        (2, "currency", "CSV"),
        (3, "amount", "CSV"),
        (4, "account", "CSV"),
    ]
    assert body["detail"] == "3 fields need attention."
    headed = recon.uploaded(
        app,
        maya,
        "tb-headers.csv",
        recon.trial_balance_csv(balances, headers=("account", "currency", "balance")),
    )
    body = refused(
        recon.attach(app, maya, draft["id"], {"file_id": headed}), 422, "validation-failed"
    )
    assert [error["message"] for error in body["errors"]] == [
        "Give exactly the columns account, currency and amount."
    ]
    # A connection that serves no trial balance, or is disabled.
    csv_gl = _netsuite_connection(
        app, clock, tenant_id, code="csv-gl", name="CSV export", adapter="CSV_GL", base_url=None
    )
    body = refused(
        recon.attach(
            app, maya, draft["id"], {"source": "ADAPTER", "integration_connection_id": csv_gl["id"]}
        ),
        422,
        "validation-failed",
    )
    assert body["errors"][0]["message"] == (
        "CSV export has no trial balance to pull. Upload a CSV instead."
    )
    # Nothing was attached by a refused request; the reconciliation is not signed without a source.
    assert recon.shown(app, maya, draft["id"])["source_file_id"] is None
    maya = preparer = enrolled(app, clock, maya.member)
    # From here Maya and the world work with the verified session: with a factor, her earlier
    # one owes the challenge (REQ-PLT-005).
    world = carrying(world, maya=maya)
    body = refused(recon.prepare(app, preparer, draft["id"]), 409, "invalid-transition")
    assert (
        body["detail"] == f"Attach a trial balance to {draft['reconciliation_no']} before signing."
    )

    # Written once: a second trial balance needs another generation.
    attached = recon.attached(app, maya, runtime, draft["id"], {"file_id": good})
    assert (attached["source_file_id"], attached["variance_count"]) == (good, 0)
    body = refused(
        recon.attach(app, maya, draft["id"], {"file_id": good}), 409, "invalid-transition"
    )
    assert body["detail"] == (
        f"{draft['reconciliation_no']} already has a trial balance. Generate the reconciliation "
        "again to compare another one."
    )
    # A reconciliation that a later generation replaced takes none.
    earlier = _generated(world, runtime)
    later = _generated(world, runtime)
    body = refused(
        recon.attach(app, maya, earlier["id"], {"file_id": good}), 409, "invalid-transition"
    )
    assert earlier["reconciliation_no"] in body["detail"]
    assert later["reconciliation_no"] in body["detail"]
    # A prepared one is past its trial balance.
    current = recon.attached(app, maya, runtime, later["id"], {"file_id": good})
    assert recon.prepare(app, preparer, current["id"]).status_code == 200
    another = _generated(world, runtime)
    assert recon.shown(app, maya, current["id"])["is_current"] is False
    assert recon.shown(app, maya, another["id"])["status"] == "DRAFT"
    assert ledger.asked == []


def test_req_plt_012_a_trial_balance_is_a_file_its_preparer_may_read(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore, runtime: JobRuntime
) -> None:
    """Independent review of the platform security merge, finding 1 (ruling R-111 (1), item
    FILE-BIND-READABLE-1; 04 T-PLT-29 "Binding"). ``attach-trial-balance`` took any
    ``IMPORT_SOURCE`` file id: a preparer named a colleague's upload — another entity's trial
    balance — the job stored it as the reconciliation's source and the registry then served its
    content to the reconciliation's readers; and the 422s before that told a missing file from
    one of a wrong shape. A file the caller may not read is answered as a missing one, before
    anything of it is read."""
    world = _january(app, keyring, clock, files)
    tenant_id = world.tenant_id
    run, net = _january_run(world)
    _acknowledged(world, run, clock)
    maya = world.maya
    # A colleague's uploads, which nothing owns yet: a trial balance, and a file that is none.
    ines = actor_with_role(app, clock, tenant_id, "revenue_accountant", name="ines")
    other = [(code, USD, net[code] + Decimal("1.00")) for code in sorted(net)]
    theirs = recon.uploaded(app, ines, "other-entity-tb.csv", recon.trial_balance_csv(other))
    shapeless = recon.uploaded(
        app,
        ines,
        "other-entity-notes.csv",
        recon.trial_balance_csv(other, headers=("account", "currency", "balance")),
    )
    draft = _generated(world, runtime)

    def attach_jobs() -> int:
        deferred = _rows(tenant_id, select(job.c.id).where(job.c.params.has_key("attach")))
        return len(deferred)

    before = attach_jobs()
    unknown = recon.attach(app, maya, draft["id"], {"file_id": str(tenant_id)})
    assert (unknown.status_code, slug(unknown)) == (422, "validation-failed"), unknown.text
    assert [error["message"] for error in unknown.json()["errors"]] == [
        "Upload the file with purpose IMPORT_SOURCE first."
    ]
    for file_id in (theirs, shapeless):
        refused = recon.attach(app, maya, draft["id"], {"file_id": file_id})
        assert refused.status_code == 422, refused.text
        assert slug(refused) == "validation-failed"
        # Word for word the answer of a file that does not exist: nothing of the file is told,
        # not even that its columns are wrong.
        assert refused.json()["errors"] == unknown.json()["errors"]
        assert refused.json()["detail"] == unknown.json()["detail"]
    assert attach_jobs() == before
    assert recon.shown(app, maya, draft["id"])["source_file_id"] is None

    # Positive control: the member who may read the file names it on the same reconciliation.
    attached = recon.attached(app, ines, runtime, draft["id"], {"file_id": theirs})
    assert attached["source_file_id"] == theirs
    # From then on the reconciliation owns the file, and its preparer reads it through it.
    shown = get(app, f"/api/v1/files/{theirs}", maya)
    assert shown.status_code == 200, shown.text


def test_contract_balance_accounts_are_controlled_before_their_first_line(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore, runtime: JobRuntime
) -> None:
    """Supervisor rulings R-69 (c) and R-74 (b), (c): the accounts the mapping in force gives the
    ``CONTRACT_LIABILITY``, ``CONTRACT_ASSET`` and ``UNBILLED_RECEIVABLE`` roles are
    subledger-controlled before the subledger's first line on them, so a balance the GL states
    there is a difference; an account of another role without a line (the receivable, which the
    ERP owns under ``billing.posting = ERP``) is not compared. Each role is one row: the
    subledger states its balance — nothing yet — and a role neither side holds anything for (the
    unbilled receivable 1105, which the file does not name) has no row."""
    world = k11_world(app, keyring, clock, files)  # AVM-DE (EUR); K11_CHART; nothing posted yet
    maya = world.place.author
    draft = recon.generated(
        app,
        maya,
        runtime,
        entity_code="AVM-DE",
        period_key="FY2026-P08",
        kind=recon.SUBLEDGER_TO_GL,
    )
    stated = recon.trial_balance_csv(
        [
            ("1100", "EUR", "48000.00"),  # ACCOUNTS_RECEIVABLE: the ERP's
            ("1200", "EUR", "75.00"),  # CONTRACT_ASSET
            ("2100", "EUR", "0.00"),  # CONTRACT_LIABILITY
            ("4000", "EUR", "-10.00"),  # REVENUE: no line yet, so not controlled yet
        ]
    )
    file_id = recon.uploaded(app, maya, "avm-de-tb-2026-08.csv", stated)
    compared = recon.attached(app, maya, runtime, draft["id"], {"file_id": file_id})
    assert compared["totals"] == [
        _total("1200", Decimal(0), Decimal("75.00"), role=CA, currency="EUR"),
        _total("2100", Decimal(0), Decimal(0), role=CL, currency="EUR"),
    ]
    assert compared["summary"] == [_key_figures(2, "0.00", "75.00", "EUR")]
    items = recon.items_of(app, maya, draft["id"])
    assert [_facts(item) for item in items] == [
        ("OTHER", "1200", None, None, _money("75.00", "EUR"), None, False)
    ]
    assert [item["account_role"] for item in items] == [CA]
    (evidence,) = recon.control_executions(world.place.tenant_id, "CTL-025", draft["id"])
    assert (evidence["population_count"], evidence["exception_count"]) == (2, 1)
    assert evidence["detail"]["rows_not_compared"] == 2


def test_failed_pull_leaves_the_reconciliation_without_a_source(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SCREENS_B §2.2 "Pull failed": a pull the GL does not answer ends the job and its
    ``TRIAL_BALANCE_PULL`` sync run ``FAILED`` with ``sync-objects-not-applied`` naming the trial
    balance; nothing is attached, and the trial balance is uploaded instead."""
    world = _january(app, keyring, clock, files)
    tenant_id = world.tenant_id
    run, net = _january_run(world)
    _acknowledged(world, run, clock)
    ledger = _Ledger(failure=gl_ports.Transient("the GL did not answer"))
    monkeypatch.setitem(gl_ports.GL_ADAPTERS, GlAdapter.NETSUITE, ledger.factory)
    connection = _netsuite_connection(app, clock, tenant_id)

    draft = _generated(world, runtime)
    started = recon.attach(
        app,
        world.maya,
        draft["id"],
        {"source": "ADAPTER", "integration_connection_id": connection["id"]},
    )
    assert started.status_code == 202, started.text
    # While the pull is queued a second request is refused.
    busy = recon.attach(
        app,
        world.maya,
        draft["id"],
        {"source": "ADAPTER", "integration_connection_id": connection["id"]},
    )
    assert (busy.status_code, slug(busy)) == (409, "invalid-transition"), busy.text
    finished = recon.job_run(tenant_id, runtime, UUID(str(started.json()["id"])))
    assert str(finished["state"]) == "FAILED", finished
    problem = finished["problem"]
    assert (problem["type"].rsplit("/", 1)[-1], problem["status"], problem["title"]) == (
        "sync-objects-not-applied",
        422,
        "Some source objects were not applied",
    )
    assert problem["failures"] == [
        {
            "step": "fetch",
            "object_type": "trial_balance",
            "external_id": f"AVM-US:{JANUARY}",
            "external_versions": [],
            "error": "Transient: the GL did not answer",
        }
    ]
    assert len(ledger.asked) == 2  # 05 §5.6: the job's two attempts
    (pull,) = _rows(tenant_id, select(sync_run).where(sync_run.c.kind == "TRIAL_BALANCE_PULL"))
    assert (str(pull["status"]), pull["finished_at"] is not None) == ("FAILED", True)
    assert pull["problem"]["instance"] == f"/api/v1/sync-runs/{pull['id']}"
    assert pull["problem"]["failures"] == problem["failures"]
    after = recon.shown(app, world.maya, draft["id"])
    assert (after["status"], after["sync_run_id"], after["source_file_id"], after["totals"]) == (
        "DRAFT",
        None,
        None,
        [],
    )
    # The banner reads the reconciliation: the connection, the job's state and the four base
    # members of its problem. The adapter's own message stays with the job and the sync run,
    # which the initiator and an auditor read (04 API-R-11).
    failed = after["trial_balance"]
    assert (failed["source"], failed["file"], failed["attached_at"]) == ("ADAPTER", None, None)
    assert failed["integration_connection"] == {"id": connection["id"], "name": "NetSuite (mock)"}
    assert (failed["job"]["id"], failed["job"]["state"]) == (started.json()["id"], "FAILED")
    assert failed["job"]["problem"] == {
        "type": problem["type"],
        "title": "Some source objects were not applied",
        "status": 422,
        "detail": problem["detail"],
    }
    assert "did not answer" not in str(failed)
    assert recon.shown(app, world.priya, draft["id"])["trial_balance"] == failed
    # "Upload a CSV instead."
    held = _held(net)
    content = recon.trial_balance_csv([(code, USD, held[code]) for code in sorted(held)])
    file_id = recon.uploaded(app, world.maya, "avm-us-tb-2026-01.csv", content)
    read = recon.attached(app, world.maya, runtime, draft["id"], {"file_id": file_id})
    assert (read["source_file_id"], read["variance_count"]) == (file_id, 0)
    # The latest request is the upload: it attached, and the failed pull is no longer shown.
    given = read["trial_balance"]
    assert (given["source"], given["job"]["state"], given["job"]["problem"]) == (
        "FILE",
        "SUCCEEDED",
        None,
    )
    assert given["attached_at"] is not None and given["integration_connection"] is None


def test_explained_then_signed(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BUILD_SPEC CLO-17 (PRD J-13.11, J-13.12): explanation "Manual accrual posted in NetSuite by
    AP; reversed on 01 Oct 2026 by JE-NS-88410." then preparer signature (``PREPARED``) and reviewer
    signature by another user (``REVIEWED``); the snapshot hash is stored on the sign-off."""
    world = _january(app, keyring, clock, files)
    tenant_id = world.tenant_id
    run, net = _january_run(world)
    _acknowledged(world, run, clock)
    lines, details = _stated_with_the_direct_entry(_shown_run(world, str(run["id"])), net)
    ledger = _Ledger(lines=lines, details=details)
    monkeypatch.setitem(gl_ports.GL_ADAPTERS, GlAdapter.NETSUITE, ledger.factory)
    connection = _netsuite_connection(app, clock, tenant_id)
    maya = enrolled(app, clock, world.maya.member)  # a sign-off needs an MFA-verified session
    # From here Maya and the world work with the verified session: with a factor, her earlier
    # one owes the challenge (REQ-PLT-005).
    world = carrying(world, maya=maya)
    priya = world.priya

    draft = _generated(world, runtime)
    pulled = recon.attached(
        app,
        maya,
        runtime,
        draft["id"],
        {"source": "ADAPTER", "integration_connection_id": connection["id"]},
    )
    (item,) = recon.items_of(app, maya, draft["id"])
    assert _facts(item) == (
        "DIRECT_GL_ENTRY",
        DIRECT_ACCOUNT,
        _money("0.00"),
        _money(DIRECT_AMOUNT),
        _money(DIRECT_AMOUNT),
        DIRECT_DOCUMENT,
        True,
    )
    # A difference is never signed away unexplained (SM-09).
    early = recon.prepare(app, maya, draft["id"])
    assert (early.status_code, slug(early)) == (409, "invalid-transition"), early.text
    assert early.json()["detail"] == "Explain 1 differences above the threshold before signing."

    explained = recon.explain(app, maya, item, EXPLANATION)
    assert explained.status_code == 200, explained.text
    assert explained.json()["explanation"] == EXPLANATION
    prepared = recon.prepare(app, maya, draft["id"])
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()["status"] == "PREPARED"
    own = recon.sign(app, maya, draft["id"])
    assert own.status_code == 403, own.text  # Maya holds no recon.signoff, and prepared it
    reviewed = recon.sign(app, priya, draft["id"])
    assert reviewed.status_code == 200, reviewed.text
    body = reviewed.json()
    assert body["status"] == "REVIEWED"
    assert [(signed["role"], signed["signer"]["id"]) for signed in body["signoffs"]] == [
        ("PREPARER", str(maya.member.user_id)),
        ("REVIEWER", str(priya.member.user_id)),
    ]
    # One snapshot was frozen for review: both sign-offs store its hash, and the stored rows do.
    hashes = {signed["subject_content_sha256"] for signed in body["signoffs"]}
    assert len(hashes) == 1 and len(next(iter(hashes))) == 64
    stored = _rows(
        tenant_id,
        select(signoff.c.role, signoff.c.subject_content_sha256, signoff.c.mfa_verified_at).where(
            signoff.c.subject_type == "reconciliation", signoff.c.subject_id == UUID(draft["id"])
        ),
    )
    assert sorted(str(row["role"]) for row in stored) == ["PREPARER", "REVIEWER"]
    assert {str(row["subject_content_sha256"]) for row in stored} == hashes
    assert all(row["mfa_verified_at"] is not None for row in stored)
    # The snapshot names the trial balance it was compared with.
    assert body["sync_run_id"] == pulled["sync_run_id"]
    # An explanation no longer changes once the reconciliation is signed.
    late = recon.explain(app, maya, explained.json(), "A later explanation of the difference.")
    assert (late.status_code, slug(late)) == (409, "invalid-transition"), late.text


# --- the role basis (supervisor rulings R-69 (a), R-74) -------------------------------------------


def test_role_basis_ties_a_ledger_the_erp_keeps(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Supervisor rulings R-69 (a) and R-74: the contract balance roles are compared per role
    against the stored closing contract balances. WLD-K-01 through 31 Jan 2026 under
    ``billing.posting = ERP``: the subledger posts Dr 2100 / Cr 4010 16,569.86 and no billing
    line; the ERP posts INV-US-1001 120,000.00 itself, Dr receivable 1200 / Cr contract liability
    2100, so its ledger holds 2100 at −103,430.14 (R-69's measurement). The reconciliation ties:
    the role's row states the stored balance, and the ERP's own invoice document raises no item
    (R-74 (d)). A document made in the ERP under a number that is no invoice of the entity stays
    a direct GL entry."""
    world = _january(app, keyring, clock, files)
    tenant_id = world.tenant_id
    run, net = _january_run(world)
    assert (net[LIABILITY], net["4010"]) == (Decimal("16569.86"), Decimal("-16569.86"))
    _acknowledged(world, run, clock)
    (batch,) = _shown_run(world, str(run["id"]))["batches"]
    held = _held(net)

    def line(code: str, amount: Decimal) -> gl_ports.TrialBalanceLine:
        return gl_ports.TrialBalanceLine(account_code=code, currency=USD, amount=amount)

    def document(
        code: str, amount: Decimal, reference: str, day: date, external_id: str | None = None
    ) -> gl_ports.TrialBalanceDetail:
        return gl_ports.TrialBalanceDetail(
            account_code=code,
            currency=USD,
            amount=amount,
            document_reference=reference,
            external_id=external_id,
            posted_date=day,
        )

    own = tuple(
        document(code, amount, "JE-NS-88001", date(2026, 1, 31), str(batch["external_id"]))
        for code, amount in sorted(net.items())
    )
    invoice = (
        document("1200", INVOICE_AMOUNT, INVOICE_NUMBER, date(2026, 1, 1)),
        document(LIABILITY, -INVOICE_AMOUNT, INVOICE_NUMBER, date(2026, 1, 1)),
    )
    ledger = _Ledger(
        # the receivable is the ERP's: its row is stated and not compared
        lines=(line("1200", INVOICE_AMOUNT), *(line(code, held[code]) for code in sorted(held))),
        details=(*own, *invoice),
    )
    monkeypatch.setitem(gl_ports.GL_ADAPTERS, GlAdapter.NETSUITE, ledger.factory)
    connection = _netsuite_connection(app, clock, tenant_id)
    pull = {"source": "ADAPTER", "integration_connection_id": connection["id"]}

    draft = _generated(world, runtime)
    tied = recon.attached(app, world.maya, runtime, draft["id"], pull)
    assert (tied["status"], tied["variance_count"]) == ("DRAFT", 0)
    assert tied["totals"] == _totals(held, held)
    liability, revenue = tied["totals"]
    assert (liability["account_role"], liability["account_codes"]) == (CL, [LIABILITY])
    assert liability["subledger_amount"] == liability["source_amount"] == _money("-103430.14")
    assert (revenue["account_role"], revenue["subledger_amount"]) == (None, _money("-16569.86"))
    assert recon.items_of(app, world.maya, draft["id"]) == []
    assert tied["summary"] == [_key_figures(2, "-120000.00", "-120000.00")]
    (evidence,) = recon.control_executions(tenant_id, "CTL-025", draft["id"])
    assert (evidence["population_count"], evidence["exception_count"], str(evidence["result"])) == (
        2,
        0,
        "PASS",
    )
    detail = evidence["detail"]
    # the invoice's line on the contract liability account is the ERP's billing; its line on the
    # receivable is on no controlled account
    assert (detail["erp_billing_documents"], detail["direct_gl_entries"]) == (1, 0)
    assert (detail["roles_not_stated"], detail["rows_not_compared"]) == (0, 1)

    # A number that is no invoice of the entity: a direct entry, itemised under the role's row.
    unknown = document(LIABILITY, Decimal("-500.00"), "INV-US-9999", date(2026, 1, 15))
    ledger.lines = (
        line("1200", INVOICE_AMOUNT),
        line(LIABILITY, held[LIABILITY] - Decimal("500.00")),
        line("4010", held["4010"]),
    )
    ledger.details = (*own, *invoice, unknown)
    again = _generated(world, runtime)
    differing = recon.attached(app, world.maya, runtime, again["id"], pull)
    assert differing["variance_count"] == 1
    (item,) = recon.items_of(app, world.maya, again["id"])
    assert _facts(item) == (
        "DIRECT_GL_ENTRY",
        LIABILITY,
        _money("0.00"),
        _money("-500.00"),
        _money("-500.00"),
        "INV-US-9999",
        True,
    )
    assert item["account_role"] == CL
    (flagged,) = recon.control_executions(tenant_id, "CTL-025", again["id"])
    assert (flagged["detail"]["erp_billing_documents"], flagged["detail"]["direct_gl_entries"]) == (
        1,
        1,
    )


def _contract_of_another_entity(tenant_id: UUID, entity_id: UUID) -> tuple[str, str]:
    """(id, external id) of a contract a SECOND legal entity of the tenant contracted — fixture
    rows — named beside the first contract in ``not_stated`` of the tenant's latest subledger-to-GL
    reconciliation of ``entity_id`` (a fixture write of the stored ``totals``)."""
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        calendar_id = session.execute(
            select(legal_entity.c.calendar_id).where(legal_entity.c.id == entity_id)
        ).scalar_one()
        entity = legal_entity_values(tenant_id, calendar_id=calendar_id, code="AVM-DE-FIXTURE")
        session.execute(insert(legal_entity).values(**entity))
        buyer = customer_values(tenant_id)
        session.execute(insert(customer).values(**buyer))
        group = combination_group_values(tenant_id)
        session.execute(insert(combination_group).values(**group))
        row = contract_values(
            tenant_id,
            customer_id=buyer["id"],
            contracting_entity_id=entity["id"],
            combination_group_id=group["id"],
        )
        session.execute(insert(contract).values(**row))
        found = session.execute(
            select(reconciliation.c.id, reconciliation.c.totals, reconciliation.c.row_version)
            .where(
                reconciliation.c.entity_id == entity_id,
                reconciliation.c.kind == recon.SUBLEDGER_TO_GL,
            )
            .order_by(reconciliation.c.as_of_known_at.desc())
            .limit(1)
        ).one()
        totals = [dict(total) for total in found.totals]
        (stated,) = [total for total in totals if total.get("not_stated")]
        stated["not_stated"] = {
            **stated["not_stated"],
            "contracts": [
                *stated["not_stated"]["contracts"],
                {"id": str(row["id"]), "external_id": str(row["external_id"])},
            ],
        }
        session.execute(
            update(reconciliation)
            .where(reconciliation.c.id == found.id)
            .values(totals=totals, row_version=found.row_version + 1)
        )
        session.commit()
    return str(row["id"]), str(row["external_id"])


def _not_stated(shown: Mapping[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """(the contracts named, the contracts counted) of the one not-stated row of ``shown``."""
    (stated,) = [total["not_stated"] for total in shown["totals"] if total["not_stated"]]
    return list(stated["contracts"]), int(stated["contract_count"])


def test_role_not_stated_for_a_balance_held_in_another_currency(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Supervisor ruling R-74 (a): a stored balance is in the contract's transaction currency and
    its functional amount is stored for the version's latest period only; the platform translates
    no balance. ``close_run_worlds.eur_receivable``: AVM-US keeps USD and ``SF-ORD-EU-3001``
    holds an unbilled receivable of EUR 10,000.00 from 31 Aug 2026; August and September are
    closed by their runs and their journals reach the ledger, which so carries the receivable at
    the closing rates — 11,050.00 at 31 Aug (1.105000) and 11,200.00 at 30 Sep (1.120000) on
    account 1105.

    August is not the version's latest period: the unbilled receivable is not stated — no
    subledger amount, no difference, the contract and the reason named — and its one
    ``NOT_STATED`` item carries the ledger's 11,050.00 for the preparer to explain. September is:
    the row states 11,200.00 and ties.

    The contracts of a not-stated row are named to a reader who reads them and counted for one
    who does not (``not_stated.contract_count``; 04 §16.8 rev 1.253)."""
    world = close_run_worlds.eur_receivable(app, keyring, clock, files)
    runtime = world.runtime
    maya = world.maya
    for period_key in (AUGUST, SEPTEMBER):
        closed = runs.closed(world, monkeypatch, entity_code="AVM-US", period_key=period_key)
        assert closed["status"] == "SUCCEEDED"
        # the ledger holds the period's journal: approved, exported and acknowledged (PRD SM-08)
        world = runs.journal_posted(world, clock, closed["journal_run_id"])
    contract_id = str(world.contracts[close_run_worlds.EUR_CONTRACT].contract["id"])

    def reconciled(period_key: str, stated: Mapping[str, str]) -> dict[str, Any]:
        draft = recon.generated(
            app,
            maya,
            runtime,
            entity_code="AVM-US",
            period_key=period_key,
            kind=recon.SUBLEDGER_TO_GL,
        )
        content = recon.trial_balance_csv([(code, USD, stated[code]) for code in sorted(stated)])
        file_id = recon.uploaded(app, maya, f"avm-us-tb-{period_key}.csv", content)
        return recon.attached(app, maya, runtime, draft["id"], {"file_id": file_id})

    # 31 Aug 2026: revenue 11,000.00 (EUR 10,000.00 at 1.100000), the remeasurement gain 50.00,
    # the receivable reclassified at 11,050.00 out of the contract liability account
    august = reconciled(
        AUGUST, {"1105": "11050.00", "2100": "0.00", "4010": "-11000.00", "7200": "-50.00"}
    )
    assert august["variance_count"] == 1
    receivable, liability, revenue, gain = august["totals"]
    assert receivable == {
        "account_code": "1105",
        "account_role": UR,
        "account_codes": ["1105"],
        "currency": USD,
        "subledger_amount": None,
        "source_amount": _money("11050.00"),
        "difference": None,
        "not_stated": {
            "reason": (
                "1 contract(s) in another currency than USD hold no USD balance at FY2026-P08: "
                "the functional balance is stored for a contract version's latest period only."
            ),
            "contracts": [{"id": contract_id, "external_id": close_run_worlds.EUR_CONTRACT}],
            "contract_count": 1,
        },
    }
    assert liability == _total("2100", Decimal(0), Decimal(0), role=CL)
    assert revenue == _total("4010", Decimal("-11000.00"), Decimal("-11000.00"))
    assert gain == _total("7200", Decimal("-50.00"), Decimal("-50.00"))
    (item,) = recon.items_of(app, maya, august["id"])
    assert _facts(item) == (
        "NOT_STATED",
        "1105",
        None,
        _money("11050.00"),
        _money("11050.00"),
        None,
        False,
    )
    assert (item["account_role"], item["explanation"]) == (UR, None)
    # the key figures add nothing for the row that is not stated, and count it
    assert august["summary"] == [
        {
            "currency": USD,
            "account_count": 4,
            "subledger_amount": _money("-11050.00"),
            "source_amount": _money("0.00"),
            "difference": _money("0.00"),
            "not_stated_count": 1,
        }
    ]
    (evidence,) = recon.control_executions(world.tenant_id, "CTL-025", august["id"])
    assert (evidence["exception_count"], str(evidence["result"])) == (1, "FAIL")
    assert evidence["detail"]["roles_not_stated"] == 1
    # a variance like any other: the preparer does not sign before it is explained
    preparer = enrolled(app, clock, maya.member)
    early = recon.prepare(app, preparer, august["id"])
    assert (early.status_code, slug(early)) == (409, "invalid-transition"), early.text
    assert early.json()["detail"] == "Explain 1 differences above the threshold before signing."

    # Who is named to whom (the supervisor's ruling of 2026-10-01 21:23, point 4). ``totals`` is
    # stored once for every reader. The second contract is a fixture: a contract row of another
    # contracting entity, added to the stored ``not_stated``. No posting of the engine writes
    # such an entry — a contract's balances are held with its own contracting entity (04 T-CLS-06
    # "Role basis", the correction of rev 1.259) — though T-CON-09's key would allow one. What is
    # witnessed is the read: a reader of AVM-US alone is told there are two contracts and is named
    # the one she reads; a reader of every entity is named both.
    other_id, other_external = _contract_of_another_entity(world.tenant_id, world.entity_id)
    reader = holding(
        app, colleague(world.tenant_id, "noor"), "revenue_accountant", entity_ids=[world.entity_id]
    )
    named = [
        {"id": contract_id, "external_id": close_run_worlds.EUR_CONTRACT},
        {"id": other_id, "external_id": other_external},
    ]
    assert _not_stated(recon.shown(app, preparer, august["id"])) == (named, 2)
    assert _not_stated(recon.shown(app, reader, august["id"])) == (named[:1], 2)
    (listed,) = [
        row
        for row in get(app, RECONCILIATIONS, reader, {"limit": 50}).json()["items"]
        if row["id"] == august["id"]
    ]
    assert _not_stated(listed) == (named[:1], 2)  # the list answers what the single read answers

    # 30 Sep 2026, the version's latest period: the receivable is stated at 11,200.00
    maya = preparer
    september = reconciled(
        SEPTEMBER, {"1105": "11200.00", "2100": "0.00", "4010": "-11000.00", "7200": "-200.00"}
    )
    assert september["variance_count"] == 0
    assert september["totals"] == [
        _total("1105", Decimal("11200.00"), Decimal("11200.00"), role=UR),
        _total("2100", Decimal(0), Decimal(0), role=CL),
        _total("4010", Decimal("-11000.00"), Decimal("-11000.00")),
        _total("7200", Decimal("-200.00"), Decimal("-200.00")),
    ]
    assert september["summary"] == [_key_figures(4, "0.00", "0.00")]


def test_roles_the_subledger_cannot_tell_apart_or_read(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two lane judgements under R-74, witnessed on the function that states the roles
    (``reconciliations._role_balances``) over WLD-K-01's January: an account that two of the
    three roles reach makes both "not stated" — the ledger does not tell them apart — and is
    carried once, on the row of the first; and balances the reader refuses by name
    (``BalanceUnreadable``, ENGINE_SPEC_B S15-R-07a) make all three roles "not stated", naming
    the contract: no figure is served in place of a balance."""
    world = _january(app, keyring, clock, files)
    state = worlds.period_state(world, "AVM-US", JANUARY)
    contract_id = str(world.contracts[K01].contract["id"])
    late = datetime(2100, 1, 1, tzinfo=UTC)  # every line and version is known by then
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        scope = reconciliation_domain.period_scope_of(
            session, world.entity_id, "ASC606", UUID(str(state["period"]["id"]))
        )
        side = reconciliation_domain._subledger_side(
            session, scope, reconciliation_domain._windows(session, scope), late
        )

        def stated(mapped: Mapping[str, frozenset[str]]) -> dict[str, Any]:
            return {
                role.account_role: role
                for role in reconciliation_domain._role_balances(session, scope, late, side, mapped)
            }

        # as the world maps them: the liability on 2100, stated; the unbilled receivable on 1210
        # with no balance; no contract asset account
        plain = stated({CL: frozenset({"2100"}), UR: frozenset({"1210"})})
        assert (plain[CL].account_codes, plain[CL].amount) == (("2100",), Decimal("-103430.14"))
        assert (plain[UR].account_codes, plain[UR].amount, plain[UR].not_stated) == (
            ("1210",),
            Decimal(0),
            None,
        )
        assert CA not in plain  # a role without an account and without a balance has no row

        # one account for the contract asset and the unbilled receivable
        shared = stated({CL: frozenset({"2100"}), CA: frozenset({"1210"}), UR: frozenset({"1210"})})
        assert shared[CL].not_stated is None
        assert (shared[CA].account_codes, shared[UR].account_codes) == (("1210",), ())
        assert (shared[CA].amount, shared[UR].amount) == (None, None)
        assert shared[CA].not_stated is not None and shared[UR].not_stated is not None
        assert shared[CA].not_stated.reason == (
            "Account(s) 1210 carry CONTRACT_ASSET and UNBILLED_RECEIVABLE; the ledger does not "
            "tell them apart. Map each contract balance role to accounts of its own."
        )
        assert shared[UR].not_stated.reason == (
            "Account(s) 1210 carry UNBILLED_RECEIVABLE and CONTRACT_ASSET; the ledger does not "
            "tell them apart. Map each contract balance role to accounts of its own."
        )
        assert (shared[CA].not_stated.contracts, shared[UR].not_stated.contracts) == ((), ())

        # balances the reader refuses
        def unreadable(*_: Any, **__: Any) -> Any:
            raise tie_outs.BalanceUnreadable(
                [
                    ProblemError(
                        field=f"balances[{K01}@AVM-US]",
                        rule_id="S15-R-07a",
                        message="the calc trace holds no balance node",
                    )
                ]
            )

        monkeypatch.setattr(tie_outs, "balances_at", unreadable)
        refused = stated({CL: frozenset({"2100"}), UR: frozenset({"1210"})})
        assert sorted(refused) == sorted((CL, CA, UR))
        for role in refused.values():
            assert role.amount is None and role.not_stated is not None
            assert role.not_stated.reason == (
                "The balances of 1 contract(s) at FY2026-P01 cannot be read from their "
                "calculation traces."
            )
            assert role.not_stated.contracts == ((contract_id, K01),)
        assert [refused[role].account_codes for role in (CL, CA, UR)] == [("2100",), (), ("1210",)]


# --- CTL-026: auto-certification ------------------------------------------------------------------


def _published_auto_rec_01(world: ReportWorld) -> tuple[str, str]:
    """Rule ``AUTO-REC-01`` version 1, authored and tested by Maya (``config.author``) and approved
    — so published — by Marcus (``config.approve``): (rule set version id, rule id)."""
    app, maya = world.app, world.maya
    created = post(app, RULE_SETS, maya, {"code": "AUTO-REC-01", "kind": "AUTO_APPROVAL"})
    assert created.status_code == 201, created.text
    version = post(app, f"{RULE_SETS}/{created.json()['id']}/versions", maya, {})
    assert version.status_code == 201, version.text
    version_id = str(version.json()["id"])
    added = post(app, f"{VERSIONS}/{version_id}/rules", maya, AUTO_REC_01)
    assert added.status_code in (200, 201), added.text
    cases = (
        (
            "A billing reconciliation without a variance",
            {"reconciliation.kind": "BILLING_TO_SUBLEDGER", "reconciliation.variance_count": 0},
            {"matched": True, "rule_key": "AUTO-REC-01", "outputs": {"auto_approve": True}},
        ),
        (
            "A billing reconciliation with a variance",
            {"reconciliation.kind": "BILLING_TO_SUBLEDGER", "reconciliation.variance_count": 1},
            {"matched": False},
        ),
        (
            "A subledger-to-GL reconciliation",
            {"reconciliation.kind": "SUBLEDGER_TO_GL", "reconciliation.variance_count": 0},
            {"matched": False},
        ),
    )
    for name, facts, expected in cases:
        case = post(
            app,
            f"{VERSIONS}/{version_id}/test-cases",
            maya,
            {"name": name, "input": facts, "expected_output": expected},
        )
        assert case.status_code == 201, case.text
    tested = post(app, f"{VERSIONS}/{version_id}/test", maya, {})
    assert (tested.status_code, tested.json()["status"]) == (200, "TESTED"), tested.text
    submitted = post(app, f"{VERSIONS}/{version_id}/submit", maya, {"comment": "Ready for review"})
    assert submitted.status_code == 200, submitted.text
    decided = approve(app, str(submitted.json()["approval_request_id"]), world.marcus)
    assert decided.status_code == 200, decided.text
    shown = get(app, f"{VERSIONS}/{version_id}", maya)
    assert shown.status_code == 200, shown.text
    assert (shown.json()["status"], shown.json()["version_no"]) == ("PUBLISHED", 1)
    return version_id, str(added.json()["id"])


@pytest.mark.control("CTL-026")
def test_ctl_026_auto_certification_zero_variance(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore, runtime: JobRuntime
) -> None:
    """BUILD_SPEC CLO-17, control CTL-026: with published rule ``AUTO-REC-01`` version 1
    (``reconciliation.kind eq BILLING_TO_SUBLEDGER``, ``reconciliation.variance_count eq 0``), a
    zero-variance billing reconciliation becomes ``AUTO_CERTIFIED`` with
    ``auto_certify_rule_set_version_id`` and ``auto_certify_rule_id`` set; with one variance it
    stays ``DRAFT`` and routes to preparer and reviewer (REQ-CLS-017; PRD J-13.10)."""
    world = recon.ingested_k01(app, keyring, clock, files, runtime)
    tenant_id = world.tenant_id
    maya = world.maya

    def february() -> dict[str, Any]:
        return recon.generated(app, maya, runtime, entity_code="AVM-US", period_key="FY2026-P02")

    # An AUTO_APPROVAL rule without ``reconciliation.kind`` is the approval engine's and certifies
    # no reconciliation, whatever else it matches (supervisor ruling R-38 (v)). It is written as a
    # row: the rule-set API no longer accepts a rule that names neither discriminator.
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        publish_rule_set(
            session,
            tenant_id=tenant_id,
            kind=RuleSetKind.AUTO_APPROVAL,
            code="AUTO-ANY-ZERO",
            rules=[
                {
                    "rule_key": "AUTO-ANY-ZERO",
                    "conditions": [
                        {"field": "reconciliation.variance_count", "op": "eq", "value": 0}
                    ],
                    "outputs": {"auto_approve": True},
                }
            ],
        )
    before = february()
    assert (before["status"], before["variance_count"], before["auto_certify_rule"]) == (
        "DRAFT",
        0,
        None,
    )
    (unused,) = recon.control_executions(tenant_id, "CTL-026", before["id"])
    assert (unused["population_count"], unused["exception_count"], str(unused["result"])) == (
        0,
        0,
        "NOT_APPLICABLE",
    )
    assert (unused["detail"]["auto_certified"], unused["detail"]["rule"]) == (False, None)

    version_id, rule_id = _published_auto_rec_01(world)

    # INV-US-1044 15,000.00 on both sides: no variance, so the rule certifies the reconciliation.
    certified = february()
    assert (certified["status"], certified["variance_count"]) == ("AUTO_CERTIFIED", 0)
    assert certified["totals"] == [
        {
            "account_code": None,
            "account_role": None,
            "account_codes": [],
            "currency": USD,
            "subledger_amount": _money("15000.00"),
            "source_amount": _money("15000.00"),
            "difference": _money("0.00"),
            "not_stated": None,
        }
    ]
    # Key figures of a billing reconciliation: no account, both sides 15,000.00; it takes no
    # trial balance and names no connection.
    assert certified["summary"] == [_key_figures(0, "15000.00", "15000.00")]
    assert (certified["trial_balance"], certified["gl_connections"]) == (None, [])
    assert certified["auto_certify_rule"] == {
        "rule_set_version_id": version_id,
        "rule_id": rule_id,
        "rule_set_code": "AUTO-REC-01",
        "version_no": 1,
        "rule_key": "AUTO-REC-01",
    }
    assert (certified["signoffs"], certified["is_current"]) == ([], True)
    (stored,) = _rows(
        tenant_id,
        select(
            reconciliation.c.auto_certify_rule_set_version_id,
            reconciliation.c.auto_certify_rule_id,
            reconciliation.c.status,
            reconciliation.c.certified_at,
        ).where(reconciliation.c.id == UUID(certified["id"])),
    )
    assert (
        str(stored["auto_certify_rule_set_version_id"]),
        str(stored["auto_certify_rule_id"]),
        str(stored["status"]),
        stored["certified_at"],  # set by the lock, which certifies (SM-09)
    ) == (version_id, rule_id, "AUTO_CERTIFIED", None)
    (evidence,) = recon.control_executions(tenant_id, "CTL-026", certified["id"])
    assert (
        evidence["run_ref_type"],
        evidence["population_count"],
        evidence["exception_count"],
        str(evidence["result"]),
    ) == ("RECONCILIATION_RUN", 1, 0, "PASS")
    assert evidence["detail"]["rule"] == certified["auto_certify_rule"]
    assert evidence["detail"]["auto_certified"] is True
    # The reconciliation's own control still names what it compared.
    (compared,) = recon.control_executions(tenant_id, "CTL-024", certified["id"])
    assert (compared["population_count"], str(compared["result"])) == (1, "PASS")
    assert compared["detail"]["auto_certified"] is True
    # An auto-certified reconciliation takes no sign-off.
    maya = preparer = enrolled(app, clock, maya.member)
    # From here Maya and the world work with the verified session: with a factor, her earlier
    # one owes the challenge (REQ-PLT-005).
    world = carrying(world, maya=maya)
    late = recon.prepare(app, preparer, certified["id"])
    assert (late.status_code, slug(late)) == (409, "invalid-transition"), late.text

    # One variance: a billing line of March that the billing system does not hold.
    booked = world.contracts[K01]
    contract_id = UUID(str(booked.contract["id"]))
    (head,) = _rows(
        tenant_id, select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )
    appended(
        world.place,
        contract_id,
        int(head["head_stream_version"]),
        [
            EventIn(
                event_type=ContractEventType.BILLING_RECORDED,
                effective_date=date(2026, 3, 16),
                payload=BillingRecordedV1(
                    invoice_number="INV-US-1090",
                    line_external_id="1",
                    obligation_key="O2",
                    amount=MoneyIn(amount="750.00", currency=USD),
                    issue_date=date(2026, 3, 16),
                ),
            )
        ],
    )
    march = recon.generated(app, maya, runtime, entity_code="AVM-US", period_key="FY2026-P03")
    assert (march["status"], march["variance_count"], march["auto_certify_rule"]) == (
        "DRAFT",
        1,
        None,
    )
    (left,) = recon.control_executions(tenant_id, "CTL-026", march["id"])
    assert (left["population_count"], str(left["result"])) == (0, "NOT_APPLICABLE")
    assert (left["detail"]["variance_count"], left["detail"]["auto_certified"]) == (1, False)
    # It routes to its preparer and its reviewer: explained and signed by Maya, reviewed by Priya.
    (item,) = recon.items_of(app, preparer, march["id"])
    assert (item["item_kind"], item["invoice_number"], item["difference"]) == (
        "UNMATCHED_SUBLEDGER",
        "INV-US-1090",
        _money("-750.00"),
    )
    assert recon.explain(app, preparer, item, "Invoice INV-US-1090 follows.").status_code == 200
    assert recon.prepare(app, preparer, march["id"]).json()["status"] == "PREPARED"
    assert recon.sign(app, world.priya, march["id"]).json()["status"] == "REVIEWED"
    # A subledger-to-GL reconciliation is outside AUTO-REC-01 and is never auto-certified.
    ledger_draft = recon.generated(
        app,
        maya,
        runtime,
        entity_code="AVM-US",
        period_key="FY2026-P02",
        kind=recon.SUBLEDGER_TO_GL,
    )
    assert (ledger_draft["status"], ledger_draft["auto_certify_rule"]) == ("DRAFT", None)
    assert recon.control_executions(tenant_id, "CTL-026", ledger_draft["id"]) == []
    assert _rows(tenant_id, select(job.c.id).where(job.c.state == "FAILED")) == []


# --- a document a rule asks for is one whose file can still be read ------------------------------
# Item EVIDENCE-COUNT-SHREDDED-1 (supervisor rulings R-119 (g), R-120 (g), R-121 (l); 04 rev 1.216
# T-PLT-29 "A document a rule asks for", T-CLS-06; 03 rev 1.131 REQ-CLS-016).

FILES = "/api/v1/files"
SHRED_REASON = "DSR-2026-0917: erase the person's data in this document"


def _answer(response: HttpResponse) -> tuple[int, str | None]:
    """(status, problem) — no problem for an answer that is none."""
    return (response.status_code, slug(response) if response.status_code >= 400 else None)


def _signing_january(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> tuple[ReportWorld, dict[str, Decimal]]:
    """The January world with its run acknowledged and Maya on an MFA-verified session (a
    sign-off needs one); what the subledger states by account on the role basis (``_held``: the
    contract liability is the stored closing contract balance, which a ledger the ERP keeps
    holds too — supervisor rulings R-69 (a), R-74)."""
    world = _january(app, keyring, clock, files)
    run, net = _january_run(world)
    _acknowledged(world, run, clock)
    return carrying(world, maya=enrolled(app, clock, world.maya.member)), _held(net)


def _with_a_file(
    world: ReportWorld, runtime: JobRuntime, held: Mapping[str, Decimal], name: str, *, order: int
) -> tuple[dict[str, Any], str]:
    """A subledger-to-GL reconciliation generated now, with an uploaded trial balance that
    states ``held``, the subledger's own balances — nothing to explain. ``order`` turns the
    rows, so that two files of one test have bytes of their own. (The reconciliation, the
    file's id.)"""
    draft = _generated(world, runtime)
    rows = [(code, USD, held[code]) for code in sorted(held)][::order]
    file_id = recon.uploaded(world.app, world.maya, name, recon.trial_balance_csv(rows))
    read = recon.attached(world.app, world.maya, runtime, draft["id"], {"file_id": file_id})
    assert (read["source_file_id"], read["variance_count"]) == (file_id, 0)
    return read, file_id


def test_evidence_count_shredded_1_a_shredded_trial_balance_is_no_source(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore, runtime: JobRuntime
) -> None:
    """A subledger-to-GL reconciliation is signed by its preparer only with a trial balance
    (REQ-CLS-016). The file of a DRAFT is no evidence yet and ``file.shred`` erases it; the row
    keeps its ``source_file_id`` — and that counted: the preparer signed a comparison with a
    document that no longer exists. The sign-off is refused by name, and a reconciliation
    generated again takes a trial balance that can be read. A reconciliation that is already
    signed keeps its sign-offs when its trial balance is shredded by approval (ruling R-121
    (l)), and its reviewer still signs."""
    world, held = _signing_january(app, keyring, clock, files)
    maya = world.maya
    tess = actor_with_role(app, clock, world.tenant_id, "tenant_admin", name="tess")

    draft, file_id = _with_a_file(world, runtime, held, "avm-us-tb-2026-01.csv", order=1)
    erased = post(app, f"{FILES}/{file_id}/shred", tess, {"reason": SHRED_REASON})
    assert erased.status_code == 200 and erased.json()["shredded_at"] is not None, erased.text
    refused = recon.prepare(app, maya, draft["id"])
    assert _answer(refused) == (409, "invalid-transition"), refused.text
    (error,) = refused.json()["errors"]
    assert (error["field"], error["rule_id"]) == ("source", "REQ-CLS-016"), error
    assert error["message"] == (
        f"The trial balance of {draft['reconciliation_no']} was shredded. Generate the "
        "reconciliation again and attach a trial balance before signing."
    )
    assert recon.shown(app, maya, draft["id"])["status"] == "DRAFT"

    # Positive control: generated again, with a trial balance that can be read.
    current, kept = _with_a_file(world, runtime, held, "avm-us-tb-2026-01-b.csv", order=-1)
    prepared = recon.prepare(app, maya, current["id"])
    assert prepared.status_code == 200 and prepared.json()["status"] == "PREPARED", prepared.text

    # Signed: the file is evidence now, erased only by an approved request — and the
    # reconciliation keeps what was signed.
    alone = post(app, f"{FILES}/{kept}/shred", tess, {"reason": SHRED_REASON})
    assert _answer(alone) == (409, "invalid-transition"), alone.text
    asked = post(app, f"{FILES}/{kept}/request-shred", tess, {"reason": SHRED_REASON})
    assert asked.status_code == 200, asked.text
    lifted = approve(app, str(asked.json()["approval_request_id"]), world.marcus)
    assert lifted.status_code == 200, lifted.text
    after = recon.shown(app, maya, current["id"])
    assert (after["status"], [signed["role"] for signed in after["signoffs"]]) == (
        "PREPARED",
        ["PREPARER"],
    )
    reviewed = recon.sign(app, world.priya, current["id"])
    assert reviewed.status_code == 200 and reviewed.json()["status"] == "REVIEWED", reviewed.text


def test_evidence_count_shredded_1_the_preparers_sign_off_waits_for_a_shred(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore, runtime: JobRuntime
) -> None:
    """The file row is locked by the sign-off that counts the trial balance, as by the shred, so
    the later of the two sees what the earlier committed. A shred in flight — the row locked
    and marked, not committed — holds the preparer's sign-off back; when it commits, the
    sign-off finds no trial balance."""
    world, held = _signing_january(app, keyring, clock, files)
    draft, file_id = _with_a_file(world, runtime, held, "avm-us-tb-2026-01.csv", order=1)
    signed = beside_a_shred(
        world.tenant_id,
        UUID(file_id),
        lambda: recon.prepare(app, world.maya, draft["id"]),
        at=clock.now(),
    )
    assert (signed.waited, *_answer(signed.response)) == (True, 409, "invalid-transition")
    assert recon.shown(app, world.maya, draft["id"])["status"] == "DRAFT"
