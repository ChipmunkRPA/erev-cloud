"""ADP-15 inbound adapter contract suite (05 §5.2 ``InboundAdapter``, ADP-01 to ADP-05, ADP-12,
ADP-16, ADP-17, ADP-20 to ADP-22; PRD WLD-F-31, J-23.4, J-23.6; BUILD_SPEC DIN-12, DIN-13; lane
F-DIN preparation).

One parametrised suite over every inbound adapter (``SALESFORCE``, ``STRIPE``) against its mock
router through ``httpx.ASGITransport`` (no socket, ARC-06) on a bare FastAPI app that mounts the
mocks the way ``create_app`` does; per-adapter expectations under ``tests/fixtures/adapters/``.
The ten ADP-15 cases: happy path; duplicate webhook; out-of-order versions; 429 with
``Retry-After``; 5xx then success; timeout then re-fetch finds the object; permanent validation
failure; checkpoint resume; reconciliation sweep; control-total mismatch — plus webhook signature
verification and the fault-injection admin route (ADP-21, ADP-22). Each case is a test of its own,
and ``test_adapter_contract[<ADAPTER>]`` — the node BUILD_SPEC DIN-13 names (BS3-D-24: CLO adds the
outbound GL adapters to the same parametrisation) — runs all ten for one adapter. No database: the
sync-run ledger and the ``SYNC_RUN`` job are tested in ``tests/domain/integrations``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, cast

import pytest
from erev_api.adapters.billing import stripe
from erev_api.adapters.crm import salesforce
from erev_api.adapters.mocks import admin
from erev_api.adapters.mocks import salesforce as sf_mock
from erev_api.adapters.mocks import stripe as st_mock
from erev_api.domain.integrations import ports
from erev_api.enums import SourceObjectType, SyncRunStatus
from fastapi import FastAPI
from pydantic import SecretStr
from support.http import asgi_client

FIXTURES: Final = Path(__file__).resolve().parents[2] / "fixtures" / "adapters"
MOCKS: Final = "/api/v1/__mocks__"
NOW: Final = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


def expected_of(code: str) -> dict[str, Any]:
    return dict(json.loads((FIXTURES / f"{code.lower()}-quayside-expected.json").read_text()))


def mock_app() -> FastAPI:
    """The mocks mounted as ``adapters.mocks.mount`` mounts them, without settings or a database."""
    app = FastAPI()
    app.state.mocks = admin.MockWorld(
        adapters={sf_mock.CODE: sf_mock.SalesforceMock(), st_mock.CODE: st_mock.StripeMock()},
        faults=admin.Faults(),
    )
    for router in (admin.router, sf_mock.router, st_mock.router):
        app.include_router(router, prefix=MOCKS, include_in_schema=False)
    return app


@dataclasses.dataclass(frozen=True, slots=True)
class Case:
    """One adapter under test: its factory, mock prefix, mapping version and webhook secret."""

    code: str
    build: Callable[[ports.InboundContext, Callable[[float], None]], ports.InboundAdapter]
    prefix: str
    mapping_version: str
    secret: str
    sign_path: str
    default_config: dict[str, Any]

    def adapter(self, app: FastAPI, sleeps: list[float]) -> ports.InboundAdapter:
        context = ports.InboundContext(
            tenant_code="quayside",
            base_url=f"{MOCKS}{self.prefix}",
            config={**self.default_config, "now": lambda: NOW},
            client=asgi_client(app),
        )
        return self.build(context, sleeps.append)


CASES: Final = [
    pytest.param(
        Case(
            "SALESFORCE",
            lambda context, sleep: salesforce.SalesforceAdapter(context, sleep=sleep),
            sf_mock.PREFIX,
            salesforce.MAPPING_VERSION,
            sf_mock.SHARED_SECRET,
            f"{MOCKS}{sf_mock.PREFIX}/webhooks/sign",
            {"default_performing_entity": "QUAY-US"},
        ),
        id="SALESFORCE",
    ),
    pytest.param(
        Case(
            "STRIPE",
            lambda context, sleep: stripe.StripeAdapter(context, sleep=sleep),
            st_mock.PREFIX,
            stripe.MAPPING_VERSION,
            st_mock.SHARED_SECRET,
            f"{MOCKS}{st_mock.PREFIX}/webhooks/sign",
            {"default_legal_entity": "QUAY-US"},
        ),
        id="STRIPE",
    ),
]


def queue_fault(app: FastAPI, route: str, kind: str, count: int = 1) -> None:
    with asgi_client(app) as client:
        response = client.post(
            f"{MOCKS}/__admin/faults", json={"route": route, "kind": kind, "count": count}
        )
        assert response.status_code == 201, response.text


def fetch_all(
    adapter: ports.InboundAdapter, page: ports.ChangePage
) -> dict[str, ports.SourceObject]:
    """Notifications → objects, once per notification id, highest version wins (ADP-02)."""
    seen: set[str] = set()
    objects: dict[str, ports.SourceObject] = {}
    for item in page.notifications:
        if item.notification_id in seen:
            continue  # duplicate webhook: recorded once
        seen.add(item.notification_id)
        obj = adapter.fetch_object(item.object_type, item.external_id)
        kept = objects.get(obj.external_id)
        if kept is None or obj.version_order > kept.version_order:
            objects[obj.external_id] = obj
    return objects


def total_of(records: ports.NormalisedRecords) -> Decimal:
    return sum((o.total for o in records.orders), Decimal(0)) + sum(
        (d.total for d in records.invoices), Decimal(0)
    )


@pytest.mark.parametrize("case", CASES)
def test_happy_path_ingests_the_scenario(case: Case) -> None:
    expected = expected_of(case.code)
    sleeps: list[float] = []
    adapter = case.adapter(mock_app(), sleeps)
    assert adapter.code == case.code
    page = adapter.fetch_changes(ports.Checkpoint(), limit=100)
    assert page.kind == "POLL" and len(page.notifications) == expected["notifications"]
    assert page.checkpoint.replay_id == expected["resume"]["latest"]
    assert page.checkpoint.replay_at == NOW
    objects = fetch_all(adapter, page)
    assert sorted(objects) == sorted(expected["object_totals"])
    assert len(objects) == expected["unique_objects"]
    totals = adapter.control_totals(list(objects.values()))
    assert totals.count == expected["control_totals"]["count"]
    assert {c: format(a, "f") for c, a in totals.amount_by_currency.items()} == expected[
        "control_totals"
    ]["amount_by_currency"]
    for external_id, total in expected["object_totals"].items():
        records = adapter.normalise(objects[external_id], case.mapping_version)
        assert format(total_of(records), "f") == total
    assert sleeps == []  # nothing retried on the happy path


@pytest.mark.parametrize("case", CASES)
def test_duplicate_webhook_is_recorded_once(case: Case) -> None:
    expected = expected_of(case.code)
    page = case.adapter(mock_app(), []).fetch_changes(ports.Checkpoint(), limit=100)
    ids = [item.notification_id for item in page.notifications]
    for duplicate in expected["duplicate_notification_ids"]:
        assert ids.count(duplicate) == 2
    assert len(set(ids)) == expected["notifications"] - len(expected["duplicate_notification_ids"])


@pytest.mark.parametrize("case", CASES)
def test_out_of_order_version_is_stale(case: Case) -> None:
    """ADP-02: the older version arrives after the newer one and never overrides it."""
    expected = expected_of(case.code)
    adapter = case.adapter(mock_app(), [])
    page = adapter.fetch_changes(ports.Checkpoint(), limit=100)
    [stale] = expected["stale_versions"]
    versions = [
        item.external_version for item in page.notifications if item.external_id == stale["object"]
    ]
    assert versions[:2] == [stale["highest"], stale["version"]]
    kept = fetch_all(adapter, page)[stale["object"]]
    assert kept.external_version == stale["highest"]
    assert int(stale["version"]) < kept.version_order


@pytest.mark.parametrize("case", CASES)
def test_rate_limit_is_retried_after_retry_after(case: Case) -> None:
    expected = expected_of(case.code)
    app = mock_app()
    sleeps: list[float] = []
    adapter = case.adapter(app, sleeps)
    queue_fault(app, expected["fault_route"], "RATE_LIMIT")
    target = expected["fault_object"]
    obj = adapter.fetch_object(SourceObjectType(target["type"]), target["id"])
    assert obj.external_version == target["version"]
    assert sleeps == [30.0]  # the ADP-12 first backoff, at least the mock's Retry-After of 1 s
    statuses = [status for _, status in cast("Any", adapter).attempts]
    assert statuses == [429, 200]


@pytest.mark.parametrize("case", CASES)
def test_server_error_then_success(case: Case) -> None:
    expected = expected_of(case.code)
    app = mock_app()
    sleeps: list[float] = []
    adapter = case.adapter(app, sleeps)
    queue_fault(app, expected["fault_route"], "SERVER_ERROR", count=2)
    target = expected["fault_object"]
    obj = adapter.fetch_object(SourceObjectType(target["type"]), target["id"])
    assert obj.external_id == target["id"]
    assert sleeps == [30.0, 60.0]  # 30 s × 2^n


@pytest.mark.parametrize("case", CASES)
def test_timeout_then_refetch_finds_the_object(case: Case) -> None:
    expected = expected_of(case.code)
    app = mock_app()
    adapter = case.adapter(app, [])
    queue_fault(app, expected["fault_route"], "TIMEOUT")
    target = expected["fault_object"]
    obj = adapter.fetch_object(SourceObjectType(target["type"]), target["id"])
    assert obj.external_version == target["version"]


@pytest.mark.parametrize("case", CASES)
def test_permanent_failure_is_never_retried(case: Case) -> None:
    expected = expected_of(case.code)
    app = mock_app()
    sleeps: list[float] = []
    adapter = case.adapter(app, sleeps)
    queue_fault(app, expected["fault_route"], "PERMANENT_ERROR")
    target = expected["fault_object"]
    with pytest.raises(ports.Permanent) as raised:
        adapter.fetch_object(SourceObjectType(target["type"]), target["id"])
    assert raised.value.status == 400 and sleeps == []
    missing = expected["missing_object"]
    with pytest.raises(ports.Permanent) as absent:
        adapter.fetch_object(SourceObjectType(missing["type"]), missing["id"])
    assert absent.value.status == 404


@pytest.mark.parametrize("case", CASES)
def test_checkpoint_resume_delivers_only_later_notifications(case: Case) -> None:
    expected = expected_of(case.code)["resume"]
    adapter = case.adapter(mock_app(), [])
    checkpoint = ports.Checkpoint(replay_id=expected["replay_id"], replay_at=NOW)
    resumed = adapter.fetch_changes(checkpoint, limit=100)
    assert [item.replay_id for item in resumed.notifications] == expected["later"]
    assert resumed.checkpoint.replay_id == expected["latest"]
    again = adapter.fetch_changes(resumed.checkpoint, limit=100)
    assert again.notifications == () and again.checkpoint.replay_id == expected["latest"]


@pytest.mark.parametrize("case", CASES)
def test_stale_checkpoint_triggers_a_reconciliation_sweep(case: Case) -> None:
    """ADP-16: a replay id older than 72 hours sweeps by last-modified time; the watermark moves
    to the latest modification found (or stays when nothing newer exists). ``fetch_changes`` runs
    the adapter's default sweep — for Stripe the ADP-17 rev 1.12 recovery mode
    (``recovery_sweep``); the original creation-only row ``sweep`` is tested on its own mode."""
    oracle = expected_of(case.code)
    expected = oracle.get("recovery_sweep", oracle["sweep"])
    adapter = case.adapter(mock_app(), [])
    watermark = datetime.fromisoformat(expected["watermark"])
    stale = ports.Checkpoint(
        replay_id=5, replay_at=NOW - timedelta(hours=73), last_modified_watermark=watermark
    )
    assert ports.sweep_due(stale, NOW) is True
    page = adapter.fetch_changes(stale, limit=100)
    assert page.kind == "SWEEP"
    assert sorted(item.external_id for item in page.notifications) == expected["found"]
    assert page.checkpoint.last_modified_watermark == datetime.fromisoformat(
        expected["watermark_after"]
    )
    assert page.checkpoint.replay_at == NOW
    fresh = ports.Checkpoint(replay_id=5, replay_at=NOW - timedelta(hours=1))
    assert ports.sweep_due(fresh, NOW) is False


@pytest.mark.parametrize("case", CASES)
def test_control_total_mismatch(case: Case) -> None:
    expected = expected_of(case.code)
    adapter = case.adapter(mock_app(), [])
    page = adapter.fetch_changes(ports.Checkpoint(), limit=100)
    objects = list(fetch_all(adapter, page).values())
    source = adapter.control_totals(objects)
    assert ports.compare_totals(source, adapter.control_totals(objects)) == "SUCCEEDED"
    loaded = adapter.control_totals(objects[:-1])
    assert ports.compare_totals(source, loaded) == "CONTROL_TOTAL_MISMATCH"
    assert (
        source.as_json()["amount_by_currency"] == expected["control_totals"]["amount_by_currency"]
    )
    assert len(source.sha256) == 64 and source.sha256 != loaded.sha256


# 05 ADP-15 "Required cases", in its order; "timeout then get_posting finds the document" is the
# outbound wording of the inbound "timeout then re-fetch finds the object".
ADP_15_CASES: Final[tuple[tuple[str, Callable[[Case], None]], ...]] = (
    ("happy path", test_happy_path_ingests_the_scenario),
    ("duplicate webhook", test_duplicate_webhook_is_recorded_once),
    ("out-of-order versions", test_out_of_order_version_is_stale),
    ("429 with Retry-After", test_rate_limit_is_retried_after_retry_after),
    ("5xx then success", test_server_error_then_success),
    ("timeout then re-fetch", test_timeout_then_refetch_finds_the_object),
    ("permanent validation failure", test_permanent_failure_is_never_retried),
    ("checkpoint resume", test_checkpoint_resume_delivers_only_later_notifications),
    (
        "reconciliation sweep finds a missed object",
        test_stale_checkpoint_triggers_a_reconciliation_sweep,
    ),
    ("control-total mismatch", test_control_total_mismatch),
)


@pytest.mark.parametrize("case", CASES)
def test_adapter_contract(case: Case) -> None:
    """BUILD_SPEC DIN-13; 05 ADP-15; 03 REQ-INT-002, REQ-INT-003: every inbound adapter passes every
    required case against its mock router through ``httpx.ASGITransport`` — each case on a fresh
    mock app, so no state crosses cases and no socket leaves the process (DG-TST-15 refuses any
    non-loopback socket for the whole suite)."""
    assert [name for name, _ in ADP_15_CASES] == [
        "happy path",
        "duplicate webhook",
        "out-of-order versions",
        "429 with Retry-After",
        "5xx then success",
        "timeout then re-fetch",
        "permanent validation failure",
        "checkpoint resume",
        "reconciliation sweep finds a missed object",
        "control-total mismatch",
    ]
    for _name, run in ADP_15_CASES:
        run(case)
    # "reconciliation sweep finds a missed object": the sweep's oracle names at least one object.
    oracle = expected_of(case.code)
    assert oracle.get("recovery_sweep", oracle["sweep"])["found"], case.code
    # "control-total mismatch sets CONTROL_TOTAL_MISMATCH (E-72)": the literal is the enum's.
    assert SyncRunStatus.CONTROL_TOTAL_MISMATCH.value == "CONTROL_TOTAL_MISMATCH"


@pytest.mark.parametrize("case", CASES)
def test_webhook_signature_is_verified_and_the_secret_never_stored(case: Case) -> None:
    """ADP-01, ADP-14: a valid signature admits the notifications; a wrong one admits nothing."""
    app = mock_app()
    adapter = case.adapter(app, [])
    with asgi_client(app) as client:
        feed = client.get(
            f"{MOCKS}{case.prefix}/events?replayId=0&limit=2"
            if case.code == "SALESFORCE"
            else f"{MOCKS}{case.prefix}/v1/events?starting_after=0&limit=2"
        ).json()
        body = json.dumps(feed).encode()
        # The source signs at the moment it sends: the adapter's clock (a scheme that signs its
        # timestamp is held to the ADP-01 replay window; Salesforce's ignores the parameter).
        signed = client.post(f"{case.sign_path}?t={int(NOW.timestamp())}", content=body).json()
    secret = SecretStr(case.secret)
    notice = adapter.verify_webhook({signed["header"]: signed["signature"]}, body, secret)
    assert notice.verified is True and len(notice.notifications) == 2
    wrong_value = "t=1,v1=" + "00" * 32 if case.code == "STRIPE" else "00" * 32
    wrong = adapter.verify_webhook({signed["header"]: wrong_value}, body, secret)
    assert (wrong.verified, wrong.notifications, wrong.reason) == (False, (), "signature mismatch")
    assert case.secret not in json.dumps(dataclasses.asdict(notice), default=str)


def test_adp_01_a_signed_timestamp_outside_the_replay_window_is_refused() -> None:
    """05 ADP-01 rev 1.47 (supervisor ruling R-48 (f)): where the scheme signs its timestamp —
    Stripe's ``t`` — a notification is accepted only within 300 seconds of it, either way. The
    signature was checked and the timestamp ignored, so a captured notification could be replayed
    at any later time."""
    [case] = [param.values[0] for param in CASES if param.values[0].code == "STRIPE"]
    app = mock_app()
    adapter = case.adapter(app, [])
    secret = SecretStr(case.secret)
    with asgi_client(app) as client:
        feed = client.get(f"{MOCKS}{case.prefix}/v1/events?starting_after=0&limit=2").json()
        body = json.dumps(feed).encode()

        def signed_at(offset: int) -> ports.WebhookNotice:
            stamp = int(NOW.timestamp()) + offset
            signed = client.post(f"{case.sign_path}?t={stamp}", content=body).json()
            return adapter.verify_webhook({signed["header"]: signed["signature"]}, body, secret)

        for offset in (-301, 301, -86_400):  # captured earlier, post-dated, a day old
            replayed = signed_at(offset)
            assert (replayed.verified, replayed.notifications, replayed.reason) == (
                False,
                (),
                "timestamp outside the replay window",
            ), offset
        for offset in (-300, 0, 300):  # positive controls: inside the window, both edges
            fresh = signed_at(offset)
            assert fresh.verified is True and len(fresh.notifications) == 2, offset
        # A timestamp that is no number is refused even when the signature over it is right.
        digest = hmac.new(case.secret.encode(), b"soon." + body, hashlib.sha256).hexdigest()
        odd = adapter.verify_webhook({"Stripe-Signature": f"t=soon,v1={digest}"}, body, secret)
        assert (odd.verified, odd.reason) == (False, "signature timestamp malformed")


def test_fault_injection_admin_route() -> None:
    """ADP-21, ADP-22: a queued RATE_LIMIT makes the next matching request 429 with Retry-After;
    ``/__admin/reset`` clears the queue and restores the seeded state."""
    app = mock_app()
    with asgi_client(app) as client:
        route = f"{sf_mock.PREFIX}/sobjects/Order"
        queue_fault(app, route, "RATE_LIMIT")
        limited = client.get(
            f"{MOCKS}{sf_mock.PREFIX}/services/data/v60.0/sobjects/Order/SF-ORD-Q-001"
        )
        assert limited.status_code == 429 and limited.headers["Retry-After"] == "1"
        ok = client.get(f"{MOCKS}{sf_mock.PREFIX}/services/data/v60.0/sobjects/Order/SF-ORD-Q-001")
        assert ok.status_code == 200
        state = client.get(f"{MOCKS}/__admin/state").json()
        assert state["adapters"]["salesforce"]["served"] == 1 and state["faults"] == []
        queue_fault(app, route, "SERVER_ERROR", count=3)
        assert client.post(f"{MOCKS}/__admin/reset").status_code == 204
        reset = client.get(f"{MOCKS}/__admin/state").json()
        assert reset["faults"] == [] and reset["adapters"]["salesforce"]["served"] == 0
        assert reset["adapters"]["stripe"]["events"] == 5


# --- Salesforce-specific (J-23.4) -----------------------------------------------------------------


def test_unmapped_product_is_visible_to_the_sync_as_a_product_code() -> None:
    """J-23.4: the adapter does not know the catalogue; it surfaces ``SF-PROD-X99`` as a product
    code the sync resolves (PRODUCT_UNMAPPED, remediable) — nothing is dropped or guessed."""
    [sf] = [param.values[0] for param in CASES if param.id == "SALESFORCE"]
    adapter = sf.adapter(mock_app(), [])
    obj = adapter.fetch_object(SourceObjectType.ORDER, "SF-ORD-Q-003")
    (draft,) = adapter.normalise(obj, salesforce.MAPPING_VERSION).orders
    codes = [line.product_code for line in draft.lines]
    assert codes == ["QUAY-PLAT", *expected_of("SALESFORCE")["unmapped_products"]["SF-ORD-Q-003"]]
    assert draft.total == Decimal("55000.00")


def test_salesforce_normalise_is_pure_and_refuses_what_the_profile_cannot_map() -> None:
    order = sf_mock.SalesforceMock().order("SF-ORD-Q-001", None)
    assert order is not None
    draft = salesforce.normalise_order(order, default_entity="QUAY-US")
    assert (draft.order_number, draft.po_number, draft.customer_external_id) == (
        "Q-001",
        "PO-88101",
        "ACC-QUAY-1001",
    )
    assert [format(line.total_price, "f") for line in draft.lines] == ["100000.00", "20000.00"]
    with pytest.raises(ports.Permanent):
        salesforce.normalise_order({**order, "Status": "Draft"}, default_entity="QUAY-US")
    with pytest.raises(ports.Permanent):
        salesforce.normalise_order(order, mapping_version="SF-ORDERS-v0", default_entity="QUAY-US")
    amended = salesforce.normalise_order(
        {**order, "Parent_Order__c": "SF-ORD-Q-000"}, default_entity="QUAY-US"
    )
    assert amended.is_amendment is True  # ADP-05: a candidate modification, never CONTRACT_AMENDED


def test_salesforce_order_states_the_two_terms_of_a_booking_or_states_nothing() -> None:
    """05 ADP-16 rev 1.204 (item ACT-FLAGS-1): ``Acceptance_Clause__c`` and ``Side_Letter__c``
    are the order's statement of the two terms a booking carries. The scenario's orders state
    both false; an order without a field states nothing of that term — the activation's routing
    then flags the contract ``TERMS_NOT_STATED`` — and a value that is neither true nor false is
    refused, never presumed."""
    mock = sf_mock.SalesforceMock()
    for order_id in ("SF-ORD-Q-001", "SF-ORD-Q-002", "SF-ORD-Q-003"):
        stated = salesforce.normalise_order(mock.order(order_id, None) or {})
        assert (stated.acceptance_clause, stated.side_letter) == (False, False), order_id
    order = mock.order("SF-ORD-Q-001", None) or {}
    silent = {key: value for key, value in order.items() if not key.endswith("_Letter__c")}
    half = salesforce.normalise_order({**silent, "Acceptance_Clause__c": True})
    assert (half.acceptance_clause, half.side_letter) == (True, None)
    neither = {key: value for key, value in silent.items() if key != "Acceptance_Clause__c"}
    unstated = salesforce.normalise_order(neither)
    assert (unstated.acceptance_clause, unstated.side_letter) == (None, None)
    with pytest.raises(ports.Permanent, match="Side_Letter__c is neither true nor false"):
        salesforce.normalise_order({**order, "Side_Letter__c": "yes"})


# --- Stripe-specific (J-23.6, ADP-17) -------------------------------------------------------------


def test_stripe_subscription_invoice_and_credit_note_normalise_purely() -> None:
    """J-23.6: ``sub_DEMO0001`` (1,200.00 per year) is the contract source with its item as a
    line; ``in_DEMO0001`` carries the service period 01 Sep 2026 – 31 Aug 2027 as the
    BILLING_RECORDED hint; the credit note names the invoice it credits (CREDIT_MEMO_RECORDED)."""
    mock = st_mock.StripeMock()
    sub = mock.subscription("sub_DEMO0001")
    assert sub is not None
    order = stripe.normalise_subscription(sub)
    assert (order.order_number, order.legal_entity_code, format(order.total, "f")) == (
        "sub_DEMO0001",
        "QUAY-US",
        "1200.00",
    )
    assert order.lines[0].product_code == "QUAY-PLAT"
    invoice = stripe.normalise_invoice(mock.invoice("in_DEMO0001", None) or {})
    expected = expected_of("STRIPE")["service_period"]
    (line,) = invoice.lines
    assert (invoice.document_kind, invoice.invoice_number, format(invoice.total, "f")) == (
        "INVOICE",
        "QUAY-0001",
        "1200.00",
    )
    assert (str(line.service_period_start), str(line.service_period_end)) == (
        expected["start"],
        expected["end"],
    )
    assert line.contract_ref == "sub_DEMO0001"
    note = stripe.normalise_credit_note(mock.credit_note("cn_DEMO0001") or {})
    assert (note.document_kind, note.credited_invoice_external_id, format(note.total, "f")) == (
        "CREDIT_MEMO",
        "in_DEMO0001",
        "-100.00",
    )
    with pytest.raises(ports.Permanent):
        stripe.normalise_invoice({**(mock.invoice("in_DEMO0001", None) or {}), "status": "draft"})
    with pytest.raises(ports.Permanent):
        stripe.normalise_credit_note({**(mock.credit_note("cn_DEMO0001") or {}), "invoice": None})
    assert stripe.money(120000, "usd") == Decimal("1200.00") and stripe.money(1200, "JPY") == 1200


def test_stripe_subscription_states_the_two_terms_in_its_metadata_or_states_nothing() -> None:
    """05 ADP-17 rev 1.204 (item ACT-FLAGS-1; the supervisor's ruling of 2026-10-02, condition 1):
    the metadata keys ``acceptance_clause`` and ``side_letter`` of a subscription, read as
    ``legal_entity`` is — a metadata value is a string. Both scenarios' subscriptions state both
    false: without the keys no subscription's contract could be a standard item."""
    recovery = st_mock.SCENARIO_FIXTURE.with_name("quayside-stripe-recovery-scenario.json")
    for mock in (st_mock.StripeMock(), st_mock.StripeMock(recovery)):
        sub = mock.subscription("sub_DEMO0001") or {}
        stated = stripe.normalise_subscription(sub)
        assert (stated.acceptance_clause, stated.side_letter) == (False, False)
    sub = st_mock.StripeMock().subscription("sub_DEMO0001") or {}
    silent = stripe.normalise_subscription({**sub, "metadata": {"legal_entity": "QUAY-US"}})
    assert (silent.acceptance_clause, silent.side_letter) == (None, None)
    half = stripe.normalise_subscription(
        {**sub, "metadata": {"legal_entity": "QUAY-US", "side_letter": "true"}}
    )
    assert (half.acceptance_clause, half.side_letter) == (None, True)
    with pytest.raises(ports.Permanent, match="acceptance_clause is neither true nor false"):
        stripe.normalise_subscription(
            {**sub, "metadata": {**sub["metadata"], "acceptance_clause": "1"}}
        )


def test_stripe_creation_only_sweep_mode_keeps_its_original_expectation() -> None:
    """The original ADP-15 sweep oracle (``sweep``: 1 Sep watermark, nothing found, watermark
    unchanged) stays true on the distinct ``INVOICES_CREATED`` mode (supervisor ruling on DIN-G1:
    recovery is defined beside the original oracle, not by rewriting it); the recovery mode is
    ``recovery_sweep``."""
    [case] = [param.values[0] for param in CASES if param.id == "STRIPE"]
    oracle = expected_of("STRIPE")
    adapter = cast("stripe.StripeAdapter", case.adapter(mock_app(), []))
    for key, mode in (("sweep", "INVOICES_CREATED"), ("recovery_sweep", "RECOVERY")):
        expected = oracle[key]
        stale = ports.Checkpoint(
            replay_id=5,
            replay_at=NOW - timedelta(hours=73),
            last_modified_watermark=datetime.fromisoformat(expected["watermark"]),
        )
        page = adapter.sweep(stale, 100, mode=cast("stripe.SweepMode", mode))
        assert page.kind == "SWEEP" and page.has_more is False, key
        assert sorted(item.external_id for item in page.notifications) == expected["found"], key
        assert page.checkpoint.last_modified_watermark == datetime.fromisoformat(
            expected["watermark_after"]
        ), key


def test_registry_builds_the_adapter_for_its_code() -> None:
    salesforce.register()
    stripe.register()
    context = ports.InboundContext(
        tenant_code="quayside", base_url="/x", config={}, client=asgi_client(mock_app())
    )
    assert ports.inbound_adapter_for("SALESFORCE", context).code == "SALESFORCE"
    assert ports.inbound_adapter_for("STRIPE", context).code == "STRIPE"
    with pytest.raises(LookupError):
        ports.inbound_adapter_for("FAXMODEM", context)
    assert ports.Checkpoint.from_json(ports.Checkpoint(replay_id=7, replay_at=NOW).as_json()) == (
        ports.Checkpoint(replay_id=7, replay_at=NOW)
    )
