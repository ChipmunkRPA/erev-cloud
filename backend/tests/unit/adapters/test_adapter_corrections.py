"""DIN corrections after Codex's independent review of the DIN-12 / DIN-13 preparation at e5017ac
(PRODUCTION-F-DIN-ADAPTERS-INDEPENDENT-e5017ac.md and PRODUCTION-F-DIN-STRIPE-SCALE-SUPPLEMENT;
supervisor rulings DIN-R1 to DIN-R4 and DIN-G1; 05 rev 1.12 ADP-12, ADP-16, ADP-17; lane F-DIN).

- DIN-R1: the Stripe mock reports continuation exactly and the poll cursor advances over the
  complete consumed event page, events about objects the adapter ignores included.
- DIN-R2: both sweeps exhaust the source's continuation (``nextRecordsUrl`` / ``has_more``) before
  the watermark advances; a page budget exhausted mid-sweep never advances past a partially
  consumed timestamp and never refreshes ``replay_at``.
- DIN-R3: every 5xx is ``Transient`` on the ADP-12 schedule (501 and 507 included); 4xx stays
  ``Permanent`` without a retry.
- DIN-R4: Stripe amounts follow Stripe's API scale table (zero-decimal list; ISK / UGX two-decimal
  by backward compatibility; three-decimal BHD / JOD / KWD / OMR / TND), never the ISO exponent
  alone; an unlisted currency is refused.
- DIN-G1: the Stripe reconciliation sweep recovers a missed credit note, a changed older invoice and
  a changed subscription through the events feed and the ``created``-filtered lists of the three
  object types.

Scripted clients mirror Codex's method (constructed replies, no server, no socket); mock-based cases
mount the mocks as ``create_app`` does. The original WLD-F-31 scenario is unchanged and stays the
ADP-15 oracle; the paging / recovery cases use ``quayside-stripe-recovery-scenario.json``.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

import pytest
from erev_api.adapters.billing import stripe
from erev_api.adapters.crm import salesforce
from erev_api.adapters.gl import netsuite
from erev_api.adapters.mocks import admin
from erev_api.adapters.mocks import salesforce as sf_mock
from erev_api.adapters.mocks import stripe as st_mock
from erev_api.domain.integrations import ports
from erev_api.domain.journals import ports as gl_ports
from erev_api.enums import SourceObjectType
from fastapi import FastAPI
from support.http import asgi_client

MOCKS: Final = "/api/v1/__mocks__"
NOW: Final = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
STALE_AT: Final = NOW - timedelta(hours=73)
SEP1: Final = datetime(2026, 9, 1, tzinfo=UTC)
SEP6: Final = datetime(2026, 9, 6, tzinfo=UTC)
SEP9: Final = datetime(2026, 9, 9, tzinfo=UTC)
RECOVERY: Final = st_mock.FIXTURES / "quayside" / "quayside-stripe-recovery-scenario.json"


def epoch(at: datetime) -> int:
    return int(at.timestamp())


# --- scripted transport (Codex's method) ---------------------------------------------------------


class Reply:
    def __init__(
        self, status: int, body: Any = None, headers: Mapping[str, str] | None = None
    ) -> None:
        self.status_code = status
        self.headers = dict(headers or {})
        self._body = {} if body is None else body

    def json(self) -> Any:
        return self._body


class Scripted:
    """Answers replies in order per URL fragment; records every request (URL and headers)."""

    def __init__(
        self, routes: Mapping[str, list[Reply]] | None = None, default: Reply | None = None
    ) -> None:
        self._routes = {key: list(value) for key, value in (routes or {}).items()}
        self._default = default
        self.requests: list[str] = []
        self.headers: list[Mapping[str, str] | None] = []

    def get(self, url: str, headers: Mapping[str, str] | None = None) -> Reply:
        self.requests.append(url)
        self.headers.append(headers)
        for fragment, replies in self._routes.items():
            if fragment in url and replies:
                return replies.pop(0)
        if self._default is None:
            raise AssertionError(f"no scripted reply for {url}")
        return self._default


def context(client: Any, **config: Any) -> ports.InboundContext:
    return ports.InboundContext(
        tenant_code="quayside",
        base_url="https://inert.invalid/source",
        config={"now": lambda: NOW, **config},
        client=client,
    )


def stale(watermark: datetime | None) -> ports.Checkpoint:
    return ports.Checkpoint(replay_id=5, replay_at=STALE_AT, last_modified_watermark=watermark)


# --- the mocks as create_app mounts them ---------------------------------------------------------


def mock_app(stripe_scenario: Path | None = None) -> FastAPI:
    app = FastAPI()
    app.state.mocks = admin.MockWorld(
        adapters={
            sf_mock.CODE: sf_mock.SalesforceMock(),
            st_mock.CODE: (
                st_mock.StripeMock()
                if stripe_scenario is None
                else st_mock.StripeMock(stripe_scenario)
            ),
        },
        faults=admin.Faults(),
    )
    for router in (admin.router, sf_mock.router, st_mock.router):
        app.include_router(router, prefix=MOCKS, include_in_schema=False)
    return app


def stripe_over(
    app: FastAPI, sleeps: list[float] | None = None, **kwargs: Any
) -> stripe.StripeAdapter:
    ctx = ports.InboundContext(
        tenant_code="quayside",
        base_url=f"{MOCKS}{st_mock.PREFIX}",
        config={"default_legal_entity": "QUAY-US", "now": lambda: NOW},
        client=asgi_client(app),
    )
    return stripe.StripeAdapter(ctx, sleep=(sleeps or []).append, **kwargs)


def salesforce_over(app: FastAPI, **kwargs: Any) -> salesforce.SalesforceAdapter:
    ctx = ports.InboundContext(
        tenant_code="quayside",
        base_url=f"{MOCKS}{sf_mock.PREFIX}",
        config={"default_performing_entity": "QUAY-US", "now": lambda: NOW},
        client=asgi_client(app),
    )
    return salesforce.SalesforceAdapter(ctx, sleep=lambda _: None, **kwargs)


def latest_objects(
    adapter: ports.InboundAdapter, page: ports.ChangePage
) -> dict[str, ports.SourceObject]:
    """Notifications → fetched objects, highest version per external id (ADP-02)."""
    objects: dict[str, ports.SourceObject] = {}
    seen: set[str] = set()
    for item in page.notifications:
        if item.notification_id in seen:
            continue
        seen.add(item.notification_id)
        obj = adapter.fetch_object(item.object_type, item.external_id)
        kept = objects.get(obj.external_id)
        if kept is None or obj.version_order > kept.version_order:
            objects[obj.external_id] = obj
    return objects


# --- DIN-R1 --------------------------------------------------------------------------------------


def test_r1_mock_reports_continuation_and_a_page_traversal_reaches_every_event() -> None:
    """Codex: with limit 2 the mock answered ordinals [1, 2] and has_more=false, so a traversal
    stopped at checkpoint 2; the required population is [1, 2, 3, 4, 5]."""
    adapter = stripe_over(mock_app())
    checkpoint = ports.Checkpoint()
    ordinals: list[int] = []
    pages = 0
    while True:
        page = adapter.fetch_changes(checkpoint, limit=2)
        pages += 1
        ordinals.extend(item.replay_id for item in page.notifications)
        checkpoint = page.checkpoint
        if not page.has_more or pages > 10:
            break
    assert ordinals == [1, 2, 3, 4, 5]
    assert checkpoint.replay_id == 5 and pages == 3


def test_r1_cursor_advances_over_an_ignored_only_page_and_past_a_trailing_ignored_event() -> None:
    """Codex's two cursor cases: from checkpoint 5 a page holding only the ignored ordinal 6 must
    move the cursor to 6 (not repeat starting_after=5); known 7 then ignored 8 must move it to 8."""
    app = mock_app(RECOVERY)
    adapter = stripe_over(app)
    first = adapter.fetch_changes(ports.Checkpoint(replay_id=5, replay_at=NOW), limit=1)
    assert first.notifications == ()
    assert (first.checkpoint.replay_id, first.has_more) == (6, True)
    second = adapter.fetch_changes(first.checkpoint, limit=1)
    served = app.state.mocks.adapters[st_mock.CODE].served
    assert served[-2:] == ["events:5", "events:6"]
    assert [item.replay_id for item in second.notifications] == [7]
    mixed = adapter.fetch_changes(ports.Checkpoint(replay_id=6, replay_at=NOW), limit=2)
    assert [item.replay_id for item in mixed.notifications] == [7]
    assert (mixed.checkpoint.replay_id, mixed.has_more) == (8, True)
    assert [item.notification_id for item in mixed.notifications] == ["evt_DEMO0007"]


# --- DIN-R2 --------------------------------------------------------------------------------------

SF_NEXT: Final = "/services/data/v60.0/query/01gQUAY-2"
SF_PAGE_1: Final = {
    "totalSize": 3,
    "done": False,
    "nextRecordsUrl": SF_NEXT,
    "records": [{"Id": "SF-A", "Version__c": "1", "SystemModstamp": "2026-09-18T01:00:00Z"}],
}
SF_PAGE_2: Final = {
    "totalSize": 3,
    "done": True,
    "records": [
        {"Id": "SF-B", "Version__c": "1", "SystemModstamp": "2026-09-18T01:00:00Z"},
        {"Id": "SF-C", "Version__c": "2", "SystemModstamp": "2026-09-19T08:00:00Z"},
    ],
}


def test_r2_salesforce_sweep_follows_next_records_url_before_the_watermark_advances() -> None:
    """Codex: one page (done=false) was read, the continuation discarded and the watermark set from
    the partial page. Now: SF-B shares SF-A's timestamp on the next page and is not skipped."""
    client = Scripted({"/query": [Reply(200, SF_PAGE_1), Reply(200, SF_PAGE_2)]})
    adapter = salesforce.SalesforceAdapter(context(client), sleep=lambda _: None)
    page = adapter.fetch_changes(stale(SEP1), limit=1)
    assert page.kind == "SWEEP" and page.has_more is False
    assert [item.external_id for item in page.notifications] == ["SF-A", "SF-B", "SF-C"]
    assert page.checkpoint.last_modified_watermark == datetime(2026, 9, 19, 8, tzinfo=UTC)
    assert page.checkpoint.replay_at == NOW
    assert client.requests[1].endswith(SF_NEXT) and page.pages == 2
    assert "ORDER BY LastModifiedDate" in client.requests[0].replace("%20", " ")
    assert client.headers[0] == {"Sforce-Query-Options": "batchSize=1"}


def test_r2_salesforce_partial_sweep_advances_only_past_fully_consumed_timestamps() -> None:
    first = {
        **SF_PAGE_1,
        "records": [
            {"Id": "SF-A0", "Version__c": "1", "SystemModstamp": "2026-09-17T12:00:00Z"},
            *SF_PAGE_1["records"],
        ],
    }
    client = Scripted({"/query": [Reply(200, first)]})
    adapter = salesforce.SalesforceAdapter(context(client), sleep=lambda _: None, max_sweep_pages=1)
    page = adapter.fetch_changes(stale(SEP1), limit=2)
    assert page.has_more is True and page.pages == 1
    assert [item.external_id for item in page.notifications] == ["SF-A0", "SF-A"]
    # SF-A's timestamp may continue on the next page: the watermark stops at SF-A0's.
    assert page.checkpoint.last_modified_watermark == datetime(2026, 9, 17, 12, tzinfo=UTC)
    assert page.checkpoint.replay_at == STALE_AT  # a partial sweep does not re-baseline
    single = Scripted({"/query": [Reply(200, SF_PAGE_1)]})
    only = salesforce.SalesforceAdapter(context(single), sleep=lambda _: None, max_sweep_pages=1)
    kept = only.fetch_changes(stale(SEP1), limit=1)
    assert kept.has_more is True and kept.checkpoint.last_modified_watermark == SEP1


def test_r2_salesforce_mock_pages_by_batch_size_and_the_sweep_finds_every_order() -> None:
    """The original WLD-F-31 fixture: a sweep with no watermark and batch size 1 crosses three
    pages and still finds all three orders with the latest modification as the watermark."""
    app = mock_app()
    adapter = salesforce_over(app)
    page = adapter.fetch_changes(stale(None), limit=1)
    assert sorted(item.external_id for item in page.notifications) == [
        "SF-ORD-Q-001",
        "SF-ORD-Q-002",
        "SF-ORD-Q-003",
    ]
    assert page.checkpoint.last_modified_watermark == datetime(2026, 9, 5, 16, 45, tzinfo=UTC)
    assert page.has_more is False and page.pages == 3


ST_INVOICE_PAGE_1: Final = {
    "object": "list",
    "data": [{"id": "in_B", "object": "invoice", "version": "1", "created": epoch(SEP9)}],
    "has_more": True,
}
ST_INVOICE_PAGE_2: Final = {
    "object": "list",
    "data": [{"id": "in_A", "object": "invoice", "version": "1", "created": epoch(SEP9)}],
    "has_more": False,
}
ST_EMPTY: Final = Reply(200, {"object": "list", "data": [], "has_more": False})


def test_r2_stripe_sweep_exhausts_has_more_before_the_watermark_advances() -> None:
    client = Scripted(
        {"/v1/invoices": [Reply(200, ST_INVOICE_PAGE_1), Reply(200, ST_INVOICE_PAGE_2)]},
        default=ST_EMPTY,
    )
    adapter = stripe.StripeAdapter(context(client), sleep=lambda _: None)
    page = adapter.fetch_changes(stale(SEP1), limit=1)
    assert page.kind == "SWEEP" and page.has_more is False
    invoices = [item.external_id for item in page.notifications]
    assert invoices == ["in_B", "in_A"]
    assert page.checkpoint.last_modified_watermark == SEP9
    invoice_requests = [url for url in client.requests if "/v1/invoices" in url]
    assert len(invoice_requests) == 2 and "starting_after=in_B" in invoice_requests[1]
    assert all("limit=1" in url for url in invoice_requests)


def test_r2_stripe_partial_sweep_never_advances_the_watermark() -> None:
    client = Scripted(default=Reply(200, ST_INVOICE_PAGE_1))
    adapter = stripe.StripeAdapter(context(client), sleep=lambda _: None, max_sweep_pages=1)
    page = adapter.fetch_changes(stale(SEP1), limit=1)
    assert page.has_more is True and page.pages == 1
    assert page.checkpoint.last_modified_watermark == SEP1
    assert page.checkpoint.replay_at == STALE_AT


# --- DIN-R3 --------------------------------------------------------------------------------------

SF_ORDER: Final = {"Id": "SF-1", "Version__c": "1", "SystemModstamp": "2026-09-18T01:00:00Z"}
ST_INVOICE: Final = {"id": "in_1", "object": "invoice", "version": "1", "created": epoch(SEP9)}
NS_DEPARTMENTS: Final = {"items": [], "hasMore": False}


@pytest.mark.parametrize("status", [501, 507])
def test_r3_every_5xx_is_transient_on_the_adp12_schedule(status: int) -> None:
    """Codex: 501 and 507 raised Permanent without a retry on both adapters; ADP-12 says 5xx."""
    sleeps: list[float] = []
    sf_client = Scripted(
        default=None, routes={"/sobjects/Order": [Reply(status), Reply(200, SF_ORDER)]}
    )
    sf = salesforce.SalesforceAdapter(context(sf_client), sleep=sleeps.append)
    assert sf.fetch_object(SourceObjectType.ORDER, "SF-1").external_id == "SF-1"
    st_client = Scripted(routes={"/v1/invoices": [Reply(status), Reply(200, ST_INVOICE)]})
    st = stripe.StripeAdapter(context(st_client), sleep=sleeps.append)
    assert st.fetch_object(SourceObjectType.INVOICE, "in_1").external_id == "in_1"
    ns_client = Scripted(routes={"/department": [Reply(status), Reply(200, NS_DEPARTMENTS)]})
    gl = netsuite.NetSuiteGl(
        gl_ports.GLContext(tenant_code="quayside", accounts=()),
        client=ns_client,
        base_url="https://inert.invalid/ns",
        sleep=sleeps.append,
    )
    assert gl.pull_dimension_values("department") == ()
    assert sleeps == [30.0, 30.0, 30.0]
    assert [s for _, s in sf.attempts] == [status, 200]
    assert [s for _, s in st.attempts] == [status, 200]


def test_r3_4xx_stays_permanent_without_a_retry() -> None:
    sleeps: list[float] = []
    client = Scripted(routes={"/v1/invoices": [Reply(422)]})
    adapter = stripe.StripeAdapter(context(client), sleep=sleeps.append)
    with pytest.raises(ports.Permanent) as raised:
        adapter.fetch_object(SourceObjectType.INVOICE, "in_1")
    assert raised.value.status == 422 and sleeps == []
    assert ports.transient_status(408) and ports.transient_status(429)
    assert all(ports.transient_status(s) for s in (500, 501, 502, 503, 504, 507, 599))
    assert not any(ports.transient_status(s) for s in (400, 401, 403, 404, 409, 422))


# --- DIN-R4 --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("minor", "currency", "expected"),
    [
        (500, "USD", "5.00"),
        (500, "JPY", "500"),
        (500, "KRW", "500"),
        (500, "ISK", "5"),  # Stripe special case: two-decimal representation of a whole amount
        (500, "UGX", "5"),  # idem
        (500, "HUF", "5.00"),  # two-decimal charges; the payout rule does not change the scale
        (500, "TWD", "5.00"),
        (120000, "BIF", "120000"),  # Codex's original R4 row (zero-decimal on Stripe and ISO)
        (120000, "KWD", "120.000"),  # Codex's original R4 row (three-decimal)
        (5120, "KWD", "5.120"),
        (1000, "BHD", "1.000"),
        (1000, "JOD", "1.000"),
        (1000, "OMR", "1.000"),
        (1000, "TND", "1.000"),
    ],
)
def test_r4_money_follows_stripes_api_scale_table(minor: int, currency: str, expected: str) -> None:
    # the three-decimal rows carry the account allowlist the supervisor's ruling requires
    value = stripe.money(minor, currency.lower(), enabled=stripe.THREE_DECIMAL)
    assert value == Decimal(expected), (currency, value)


def test_r4_unlisted_currencies_and_malformed_three_decimal_amounts_are_refused() -> None:
    for code in ("XYZ", "ZWL", "SLL", "VEF"):
        with pytest.raises(ports.Permanent):
            stripe.money(500, code)
    with pytest.raises(ports.Permanent):
        stripe.money(5124, "KWD", enabled={"kwd"})  # the last digit of a three-decimal amount is 0
    # Supervisor ruling on DIN-R4: three-decimal currencies are refused with a named reason until
    # the connection's account-level allowlist admits them (not in the presentment list retrieved
    # 2026-09-20; KWD availability is account-dependent). The scale table stays for that day.
    for code in sorted(stripe.THREE_DECIMAL):
        with pytest.raises(ports.Permanent) as refused:
            stripe.money(1000, code)
        assert str(refused.value).startswith(stripe.CURRENCY_NOT_ENABLED + ":"), code
    assert stripe.api_scale("KWD", enabled=("KWD",)) == 3
    assert stripe.ZERO_DECIMAL == frozenset(
        "BIF CLP DJF GNF JPY KMF KRW MGA PYG RWF UGX VND VUV XAF XOF XPF".split()
    )
    assert stripe.TWO_DECIMAL_BY_COMPATIBILITY == frozenset({"ISK", "UGX"})
    assert stripe.THREE_DECIMAL == frozenset({"BHD", "JOD", "KWD", "OMR", "TND"})
    assert (stripe.api_scale("ISK"), stripe.api_scale("JPY")) == (2, 0)
    assert stripe.api_scale("usd") == 2 and stripe.api_scale("HUF") == 2
    assert len(stripe.PRESENTMENT) == 130 and {"USD", "EUR", "HUF", "TWD"} <= stripe.PRESENTMENT


@pytest.mark.parametrize(
    ("currency", "amount", "expected"),
    [
        ("usd", 120000, "1200.00"),
        ("jpy", 120000, "120000"),
        ("bif", 120000, "120000"),
        ("kwd", 120000, "120.000"),
        ("isk", 500, "5"),
        ("ugx", 500, "5"),
        ("usd", 500, "5.00"),
        ("jpy", 500, "500"),
    ],
)
def test_r4_invoice_totals_follow_the_provider_scale(
    currency: str, amount: int, expected: str
) -> None:
    """Codex's native controls: the fixture invoice with only currency and amounts changed."""
    original = st_mock.StripeMock().invoice("in_DEMO0001", None)
    assert original is not None
    value = copy.deepcopy(dict(original))
    value["currency"] = currency
    value["amount_due"] = amount
    value["amount_paid"] = amount
    value["lines"]["data"][0]["amount"] = amount
    if currency.upper() in stripe.THREE_DECIMAL:
        with pytest.raises(ports.Permanent) as refused:  # default: no account allowlist
            stripe.normalise_invoice(value, default_entity="QUAY-US")
        assert str(refused.value).startswith(stripe.CURRENCY_NOT_ENABLED + ":")
    draft = stripe.normalise_invoice(
        value, default_entity="QUAY-US", enabled_currencies=stripe.THREE_DECIMAL
    )
    assert draft.total == Decimal(expected) and draft.lines[0].amount == Decimal(expected)
    assert draft.currency == currency.upper()


# --- DIN-G1 --------------------------------------------------------------------------------------


def test_g1_original_scenario_september_1_sweep_recovers_the_september_6_credit_note() -> None:
    """Codex's coverage assertion on the unchanged WLD-F-31 scenario: the invoice-creation-only
    sweep omitted cn_DEMO0001 (created 6 Sep, USD -100.00)."""
    adapter = stripe_over(mock_app())
    page = adapter.fetch_changes(stale(SEP1), limit=100)
    assert page.kind == "SWEEP" and page.has_more is False
    found = {item.external_id for item in page.notifications}
    assert "cn_DEMO0001" in found
    note = adapter.fetch_object(SourceObjectType.CREDIT_MEMO, "cn_DEMO0001")
    (draft,) = adapter.normalise(note, stripe.MAPPING_VERSION).invoices
    assert (draft.document_kind, draft.total) == ("CREDIT_MEMO", Decimal("-100.00"))
    assert page.checkpoint.last_modified_watermark == SEP6
    assert page.checkpoint.replay_at == NOW


def test_g1_sweep_recovers_changed_older_objects_and_created_objects_to_exhaustion() -> None:
    """Recovery scenario, watermark 1 Sep, page size 2: the events feed brings the changed older
    invoice (in_DEMO0001 v2, 7 Sep) and the changed subscription (sub_DEMO0001 v2, 8 Sep); the
    created-filtered lists bring the invoices of 3 Sep (two, same timestamp) and 5 Sep and the
    credit note of 6 Sep; nothing about customers or charges is notified; every list is paged to
    exhaustion and the watermark is the latest consumed timestamp (9 Sep)."""
    app = mock_app(RECOVERY)
    adapter = stripe_over(app)
    page = adapter.fetch_changes(stale(SEP1), limit=2)
    assert page.kind == "SWEEP" and page.has_more is False and page.pages >= 5
    assert {item.object_type for item in page.notifications} <= set(stripe.EVENT_OBJECTS.values())
    objects = latest_objects(adapter, page)
    assert sorted(objects) == [
        "cn_DEMO0001",
        "in_DEMO0001",
        "in_DEMO0002",
        "in_DEMO0003",
        "in_DEMO0004",
        "sub_DEMO0001",
    ]
    assert objects["in_DEMO0001"].external_version == "2"
    assert objects["sub_DEMO0001"].external_version == "2"
    assert page.checkpoint.last_modified_watermark == SEP9
    totals = adapter.control_totals(list(objects.values()))
    assert totals.count == 6
    # 2 × 1,200.00 (subscription v2) + 1,200.00 + 50.00 + 70.00 + 90.00 − 100.00
    assert totals.amount_by_currency == {"USD": Decimal("3710.00")}
    budgeted = stripe_over(app, max_sweep_pages=1)
    partial = budgeted.fetch_changes(stale(SEP1), limit=2)
    assert partial.has_more is True and partial.checkpoint.last_modified_watermark == SEP1


def test_g1_mock_lists_page_newest_first_with_exact_continuation() -> None:
    """The mock's Stripe list shape: ``limit``, ``starting_after`` and an exact ``has_more`` for
    subscriptions, invoices, credit notes and events (with ``created`` on every event)."""
    app = mock_app(RECOVERY)
    with asgi_client(app) as client:
        base = f"{MOCKS}{st_mock.PREFIX}"
        first = client.get(f"{base}/v1/invoices?created[gt]={epoch(SEP1)}&limit=2").json()
        assert [row["id"] for row in first["data"]] == ["in_DEMO0004", "in_DEMO0003"]
        assert first["has_more"] is True
        rest = client.get(
            f"{base}/v1/invoices?created[gt]={epoch(SEP1)}&limit=2&starting_after=in_DEMO0003"
        ).json()
        assert [row["id"] for row in rest["data"]] == ["in_DEMO0002"] and rest["has_more"] is False
        subs = client.get(f"{base}/v1/subscriptions?created[gt]={epoch(SEP1)}&limit=2").json()
        assert subs["data"] == [] and subs["has_more"] is False
        notes = client.get(f"{base}/v1/credit_notes?created[gt]={epoch(SEP1)}&limit=2").json()
        assert [row["id"] for row in notes["data"]] == ["cn_DEMO0001"]
        events = client.get(f"{base}/v1/events?created[gt]={epoch(SEP1)}&limit=3").json()
        assert [e["ordinal"] for e in events["data"]] == [2, 4, 5] and events["has_more"] is True
        assert all(isinstance(e["created"], int) for e in events["data"])
        original = st_mock.StripeMock()
        body = original.events(0, 100)[0][3]  # the credit-note event of the original scenario
        assert body["created"] == 1788652800  # derived from the credit note's created (6 Sep)
    scenario = json.loads(RECOVERY.read_text())
    assert [e["ordinal"] for e in scenario["events"]] == list(range(1, 10))


# --- DIN-R2 residual: a budget-stopped sweep resumes where it stopped -----------------------------

SAME_STAMP: Final = "2026-09-18T01:00:00Z"
SF_RESUME_NEXT: Final = "/services/data/v60.0/query/01gRESUME-1"
SF_PAGE_A: Final = {
    "totalSize": 2,
    "done": False,
    "nextRecordsUrl": SF_RESUME_NEXT,
    "records": [{"Id": "SF-A", "Version__c": "1", "SystemModstamp": SAME_STAMP}],
}
SF_PAGE_B: Final = {
    "totalSize": 2,
    "done": True,
    "records": [{"Id": "SF-B", "Version__c": "1", "SystemModstamp": SAME_STAMP}],
}
ST_PAGE_A: Final = {
    "object": "list",
    "data": [{"id": "in_A", "object": "invoice", "version": "1", "created": epoch(SEP9)}],
    "has_more": True,
}
ST_PAGE_B: Final = {
    "object": "list",
    "data": [{"id": "in_B", "object": "invoice", "version": "1", "created": epoch(SEP9)}],
    "has_more": False,
}


def test_r2_residual_salesforce_budget_stopped_sweep_resumes_at_its_locator() -> None:
    """Codex (PRODUCTION-F-DIN-R2-CONTINUATION-8011326): with rows A / B of one timestamp, page
    size 1 and a budget of one page, the second call restarted at A forever. Now the checkpoint
    carries the query locator: call 2 reads B through nextRecordsUrl, and the watermark moves only
    once the timestamp is fully consumed."""
    client = Scripted({"/query": [Reply(200, SF_PAGE_A), Reply(200, SF_PAGE_B)]})
    adapter = salesforce.SalesforceAdapter(context(client), sleep=lambda _: None, max_sweep_pages=1)
    first = adapter.fetch_changes(stale(SEP1), limit=1)
    assert [item.external_id for item in first.notifications] == ["SF-A"]
    assert first.has_more is True and first.checkpoint.last_modified_watermark == SEP1
    assert first.checkpoint.sweep_cursor is not None
    second = adapter.fetch_changes(first.checkpoint, limit=1)
    assert [item.external_id for item in second.notifications] == ["SF-B"]
    assert second.has_more is False and second.checkpoint.sweep_cursor is None
    assert second.checkpoint.last_modified_watermark == datetime(2026, 9, 18, 1, tzinfo=UTC)
    assert second.checkpoint.replay_at == NOW
    assert client.requests[1].endswith(SF_RESUME_NEXT) and len(client.requests) == 2
    restored = ports.Checkpoint.from_json(first.checkpoint.as_json())
    assert restored == first.checkpoint


def test_r2_residual_stripe_budget_stopped_sweep_resumes_at_its_cursor() -> None:
    client = Scripted(
        {"/v1/invoices": [Reply(200, ST_PAGE_A), Reply(200, ST_PAGE_B)]}, default=ST_EMPTY
    )
    adapter = stripe.StripeAdapter(context(client), sleep=lambda _: None, max_sweep_pages=1)
    checkpoint = stale(SEP1)
    seen: list[str] = []
    calls = 0
    while True:
        page = adapter.fetch_changes(checkpoint, limit=1)
        calls += 1
        seen.extend(item.external_id for item in page.notifications)
        checkpoint = page.checkpoint
        if not page.has_more or calls > 8:
            break
        assert checkpoint.last_modified_watermark == SEP1  # unchanged until exhaustion
        assert checkpoint.sweep_cursor is not None and checkpoint.replay_at == STALE_AT
    assert seen == ["in_A", "in_B"]
    assert checkpoint.sweep_cursor is None and checkpoint.last_modified_watermark == SEP9
    assert checkpoint.replay_at == NOW
    invoice_requests = [url for url in client.requests if "/v1/invoices" in url]
    assert len(invoice_requests) == 2 and "starting_after=in_A" in invoice_requests[1]
    # events, subscriptions, invoices ×2, credit notes: one page per call, five calls
    assert calls == 5


def test_r2_residual_mock_sweeps_complete_across_budget_one_calls() -> None:
    """Salesforce (original fixture, batch size 1) and Stripe (recovery scenario, page size 2)
    complete their sweeps over repeated budget-one calls, each resuming where the last stopped."""
    app = mock_app(RECOVERY)
    sf = salesforce_over(app, max_sweep_pages=1)
    checkpoint = stale(None)
    found: list[str] = []
    for _ in range(6):
        page = sf.fetch_changes(checkpoint, limit=1)
        found.extend(item.external_id for item in page.notifications)
        checkpoint = page.checkpoint
        if not page.has_more:
            break
    assert found == ["SF-ORD-Q-001", "SF-ORD-Q-002", "SF-ORD-Q-003"]
    assert checkpoint.last_modified_watermark == datetime(2026, 9, 5, 16, 45, tzinfo=UTC)
    st = stripe_over(app, max_sweep_pages=1)
    checkpoint = stale(SEP1)
    objects: dict[str, ports.SourceObject] = {}
    for _ in range(12):
        page = st.fetch_changes(checkpoint, limit=2)
        objects.update(latest_objects(st, page))
        checkpoint = page.checkpoint
        if not page.has_more:
            break
    assert sorted(objects) == [
        "cn_DEMO0001",
        "in_DEMO0001",
        "in_DEMO0002",
        "in_DEMO0003",
        "in_DEMO0004",
        "sub_DEMO0001",
    ]
    assert checkpoint.sweep_cursor is None and checkpoint.last_modified_watermark == SEP9


def test_r2_residual_salesforce_expired_locator_restarts_from_the_watermark() -> None:
    """A stale locator (Salesforce expires them) answers 404: the sweep restarts from the watermark
    it never advanced past unconsumed rows, so nothing is skipped."""
    app = mock_app()
    sf = salesforce_over(app, max_sweep_pages=1)
    expired = ports.Checkpoint(
        replay_id=5,
        replay_at=STALE_AT,
        last_modified_watermark=None,
        sweep_cursor={"source": "SALESFORCE", "next": "/services/data/v60.0/query/01gGONE-1"},
    )
    page = sf.fetch_changes(expired, limit=100)
    assert sorted(item.external_id for item in page.notifications) == [
        "SF-ORD-Q-001",
        "SF-ORD-Q-002",
        "SF-ORD-Q-003",
    ]
    assert page.has_more is False and page.checkpoint.sweep_cursor is None
