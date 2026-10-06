"""DIN-12 pure logic of the sync run, the commands and the queries (05 ADP-01, ADP-02, ADP-05,
ADP-16; 04 §16.14; BUILD_SPEC DIN-12) — CPU only, no database: the receiver id, notification
deduplication and ordering, the forced sweep, the mechanical amendment diff, the response shapes,
the composition-root hooks and the pins the domain shares with the adapters.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.adapters.billing import stripe
from erev_api.adapters.crm import salesforce
from erev_api.clock import FrozenClock
from erev_api.domain.integrations import commands, ports, queries, sync
from erev_api.domain.integrations import outbox as sync_outbox
from erev_api.enums import (
    ExceptionSource,
    ModificationKind,
    OutboxTopic,
    SourceObjectType,
    SourceSystem,
)
from erev_api.events import outbox
from erev_api.schemas import integrations as schemas

TENANT = UUID(int=0xA1)
CONNECTION = UUID(int=0xC1)
NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def _notification(
    external_id: str, version: str, replay_id: int, nid: str | None = None
) -> ports.Notification:
    return ports.Notification(
        notification_id=nid or f"NTF-{replay_id}",
        object_type=SourceObjectType.ORDER,
        external_id=external_id,
        external_version=version,
        replay_id=replay_id,
    )


def _object(external_id: str, version: str, **payload: Any) -> ports.SourceObject:
    return ports.SourceObject(
        source_system=SourceSystem.SALESFORCE,
        object_type=SourceObjectType.ORDER,
        external_id=external_id,
        external_version=version,
        version_order=int(version),
        payload={"Id": external_id, "Version__c": version, **payload},
    )


# --- receiver id (ADP-01; API-R-02 pattern) -------------------------------------------------------


def test_receiver_id_round_trips_and_refuses_other_strings() -> None:
    receiver = commands.receiver_id(TENANT, CONNECTION)
    assert receiver == f"erevw_{TENANT.hex}_{CONNECTION.hex}"
    assert commands.parse_receiver_id(receiver) == (TENANT, CONNECTION)
    for bad in ("", str(CONNECTION), receiver.upper(), receiver[:-1], f"erevc_{TENANT.hex}_x"):
        assert commands.parse_receiver_id(bad) is None


# --- notifications: dedupe, fetch once, order (ADP-01, ADP-02) ------------------------------------


def test_unique_notifications_counts_exact_repeats_only() -> None:
    items = [
        _notification("SF-ORD-Q-001", "1", 1, "NTF-Q-0001"),
        _notification("SF-ORD-Q-002", "2", 2),
        _notification("SF-ORD-Q-002", "1", 3),
        _notification("SF-ORD-Q-003", "1", 4),
        _notification("SF-ORD-Q-001", "1", 5, "NTF-Q-0001"),  # the duplicate webhook
    ]
    unique, repeats = sync.unique_notifications(items)
    assert repeats == 1
    assert [(n.external_id, n.external_version) for n in unique] == [
        ("SF-ORD-Q-001", "1"),
        ("SF-ORD-Q-002", "2"),
        ("SF-ORD-Q-002", "1"),
        ("SF-ORD-Q-003", "1"),
    ]


class _Adapter:
    """Answers ``fetch_object`` from a table, recording every call; other methods unused."""

    code = "SALESFORCE"

    def __init__(
        self, objects: dict[str, ports.SourceObject], *, missing: set[str] = frozenset()
    ) -> None:
        self.objects = objects
        self.missing = missing
        self.fetched: list[str] = []
        self.pages: list[ports.Checkpoint] = []

    def fetch_object(self, object_type: SourceObjectType, external_id: str) -> ports.SourceObject:
        self.fetched.append(external_id)
        if external_id in self.missing:
            raise ports.Permanent("HTTP 404", status=404)
        return self.objects[external_id]

    def fetch_changes(self, checkpoint: ports.Checkpoint, limit: int) -> ports.ChangePage:
        self.pages.append(checkpoint)
        page = len(self.pages)
        return ports.ChangePage(
            notifications=(_notification(f"O-{page}", "1", page),),
            checkpoint=ports.Checkpoint(replay_id=page, replay_at=NOW),
            has_more=page < 3,
        )


def test_fetch_objects_fetches_each_object_once_and_records_permanent_failures() -> None:
    adapter = _Adapter(
        {
            "SF-ORD-Q-001": _object("SF-ORD-Q-001", "1"),
            "SF-ORD-Q-002": _object("SF-ORD-Q-002", "2"),
        },
        missing={"SF-ORD-Q-404"},
    )
    unique = [
        _notification("SF-ORD-Q-001", "1", 1),
        _notification("SF-ORD-Q-002", "2", 2),
        _notification("SF-ORD-Q-002", "1", 3),
        _notification("SF-ORD-Q-404", "1", 4),
    ]
    fetched = sync.fetch_objects(adapter, unique)
    assert adapter.fetched == ["SF-ORD-Q-001", "SF-ORD-Q-002", "SF-ORD-Q-404"]  # once per object
    assert fetched.attempts == 3
    assert [obj.external_id for obj in fetched.objects] == ["SF-ORD-Q-001", "SF-ORD-Q-002"]
    assert fetched.notified_versions[(SourceObjectType.ORDER, "SF-ORD-Q-002")] == ("2", "1")
    assert [f["external_id"] for f in fetched.failures] == ["SF-ORD-Q-404"]
    assert fetched.failures[0]["error"].startswith("Permanent: HTTP 404")


def test_ordered_for_processing_puts_the_highest_version_of_an_object_first() -> None:
    objects = [_object("A", "1"), _object("B", "3"), _object("A", "2"), _object("B", "1")]
    ordered = sync.ordered_for_processing(objects)
    assert [(o.external_id, o.external_version) for o in ordered] == [
        ("A", "2"),
        ("A", "1"),
        ("B", "3"),
        ("B", "1"),
    ]


def test_version_rank_orders_integers_numerically_and_agrees_with_the_salesforce_adapter() -> None:
    assert sync.version_rank("2") > sync.version_rank("1")
    assert sync.version_rank("10") > sync.version_rank("9")
    assert sync.version_rank("v2") > sync.version_rank("10")  # non-integers after every integer
    for text in ("1", "2", "10"):
        assert sync.version_rank(text)[1] == salesforce.version_order(text)


# --- collect: poll pages, forced sweep, webhook batch (ADP-16) ------------------------------------


def test_collect_changes_pages_until_has_more_is_false() -> None:
    adapter = _Adapter({})
    collected = sync.collect_changes(
        adapter, kind="INBOUND_POLL", checkpoint=ports.Checkpoint(), notifications=None
    )
    assert collected.pages == 3
    assert [n.external_id for n in collected.notifications] == ["O-1", "O-2", "O-3"]
    assert collected.checkpoint_after.replay_id == 3
    assert collected.cancelled is False


def test_collect_changes_stops_at_the_page_budget_and_on_cancellation() -> None:
    adapter = _Adapter({})
    budget = sync.collect_changes(
        adapter, kind="INBOUND_POLL", checkpoint=ports.Checkpoint(), notifications=None, max_pages=2
    )
    assert budget.pages == 2 and budget.checkpoint_after.replay_id == 2
    cancelled = sync.collect_changes(
        _Adapter({}),
        kind="INBOUND_POLL",
        checkpoint=ports.Checkpoint(),
        notifications=None,
        cancelled=lambda: True,
    )
    assert cancelled.cancelled is True and cancelled.pages == 0


def test_collect_changes_takes_a_webhook_batch_from_the_params() -> None:
    params = commands.notification_params([_notification("SF-ORD-Q-001", "1", 1, "NTF-Q-0001")])
    assert params == [
        {
            "notification_id": "NTF-Q-0001",
            "object_type": "ORDER",
            "external_id": "SF-ORD-Q-001",
            "external_version": "1",
            "replay_id": 1,
        }
    ]
    adapter = _Adapter({})
    checkpoint = ports.Checkpoint(replay_id=7, replay_at=NOW)
    collected = sync.collect_changes(
        adapter, kind="WEBHOOK_BATCH", checkpoint=checkpoint, notifications=params
    )
    assert adapter.pages == []  # nothing polled: the batch names its objects (ADP-01)
    assert collected.notifications == (_notification("SF-ORD-Q-001", "1", 1, "NTF-Q-0001"),)
    assert collected.checkpoint_after == checkpoint


def test_force_sweep_makes_sweep_due_true_for_every_checkpoint_shape() -> None:
    fresh = sync.force_sweep(ports.Checkpoint())
    assert fresh.last_modified_watermark == sync.SWEEP_EPOCH and ports.sweep_due(fresh, NOW)
    polled = sync.force_sweep(ports.Checkpoint(replay_id=5, replay_at=NOW))
    assert polled.replay_id == 5 and polled.replay_at is None and ports.sweep_due(polled, NOW)
    resuming = ports.Checkpoint(replay_id=5, replay_at=NOW, sweep_cursor={"locator": "x"})
    assert sync.force_sweep(resuming) == resuming  # a sweep in progress resumes as it is


def test_default_mapping_versions_pin_the_adapter_constants() -> None:
    assert sync.DEFAULT_MAPPING_VERSIONS["SALESFORCE"] == salesforce.MAPPING_VERSION
    assert sync.DEFAULT_MAPPING_VERSIONS["STRIPE"] == stripe.MAPPING_VERSION
    assert sync.mapping_version_of({"adapter": "SALESFORCE", "config": {}}) == "SF-ORDERS-v1"
    assert (
        sync.mapping_version_of({"adapter": "SALESFORCE", "config": {"mapping_version": "SF-X"}})
        == "SF-X"
    )


# --- amendment diff (ADP-05; pending Q-B) ---------------------------------------------------------


def _draft(lines: tuple[ports.NormalisedLine, ...], **over: Any) -> ports.NormalisedOrderDraft:
    values: dict[str, Any] = {
        "source_system": SourceSystem.SALESFORCE,
        "external_order_id": "SF-ORD-Q-009",
        "external_version": "1",
        "order_number": "Q-009",
        "order_date": date(2026, 9, 10),
        "customer_external_id": "ACC-QUAY-1001",
        "legal_entity_code": "QUAY-US",
        "transaction_currency": "USD",
        "lines": lines,
        "parent_order_external_id": "SF-ORD-Q-001",
        "amendment_reason": "Upsell",
    }
    values.update(over)
    return ports.NormalisedOrderDraft(**values)


def _line(key: str, code: str, quantity: str, total: str) -> ports.NormalisedLine:
    return ports.NormalisedLine(
        line_external_id=key,
        product_code=code,
        quantity=Decimal(quantity),
        total_price=Decimal(total),
    )


def _parent(key: str, code: str, quantity: str, total: str) -> dict[str, Any]:
    return {
        "line_external_id": key,
        "product_code": code,
        "quantity": Decimal(quantity),
        "total_price": Decimal(total),
        "start_date": None,
        "end_date": None,
    }


def test_amendment_lines_add_change_remove_with_signed_deltas() -> None:
    draft = _draft(
        (_line("L1", "QUAY-PLAT", "1", "120000.00"), _line("L3", "QUAY-SVC", "10", "5000.00"))
    )
    parent = {
        "L1": _parent("L1", "QUAY-PLAT", "1", "100000.00"),
        "L2": _parent("L2", "QUAY-ADDON", "10", "12000.00"),
    }
    lines, kind = sync.amendment_lines(draft, parent)
    by_key = {line["obligation_key"]: line for line in lines}
    assert by_key["L1"]["action"] == "CHANGE"
    assert by_key["L1"]["consideration_delta"] == {"amount": "20000.00", "currency": "USD"}
    assert by_key["L1"]["quantity_delta"] == "0"
    assert by_key["L3"]["action"] == "ADD" and by_key["L3"]["product_code"] == "QUAY-SVC"
    assert by_key["L2"]["action"] == "REMOVE"
    assert by_key["L2"]["consideration_delta"] == {"amount": "-12000.00", "currency": "USD"}
    assert by_key["L2"]["quantity_delta"] == "-10"
    assert kind is ModificationKind.ADD_OBLIGATION  # any ADD wins the provisional kind


def test_amendment_lines_price_and_quantity_kinds_and_no_change() -> None:
    parent = {"L1": _parent("L1", "QUAY-PLAT", "1", "100000.00")}
    _, price = sync.amendment_lines(_draft((_line("L1", "QUAY-PLAT", "1", "90000.00"),)), parent)
    assert price is ModificationKind.PRICE_CHANGE
    _, quantity = sync.amendment_lines(
        _draft((_line("L1", "QUAY-PLAT", "2", "100000.00"),)), parent
    )
    assert quantity is ModificationKind.QUANTITY_CHANGE
    unchanged, kind = sync.amendment_lines(
        _draft((_line("L1", "QUAY-PLAT", "1", "100000.00"),)), parent
    )
    assert unchanged == [] and kind is ModificationKind.TERM_CHANGE
    assert _draft(()).is_amendment is True
    assert (
        dataclasses.replace(
            _draft(()), parent_order_external_id=None, amendment_reason=None
        ).is_amendment
        is False
    )


# --- shapes (04 §16.14) ---------------------------------------------------------------------------


def test_duration_and_last_sync_run_shapes() -> None:
    assert queries.duration_seconds(None, None) is None
    assert queries.duration_seconds(NOW, None) is None
    later = datetime(2026, 9, 21, 12, 1, 30, tzinfo=UTC)
    assert queries.duration_seconds(NOW, later) == 90
    run = {
        "tenant_id": TENANT,
        "id": UUID(int=9),
        "integration_connection_id": CONNECTION,
        "kind": "INBOUND_POLL",
        "status": "SUCCEEDED",
        "checkpoint_before": {},
        "checkpoint_after": {"replay_id": 5},
        "source_totals": {"count": 3},
        "loaded_totals": {"count": 3},
        "record_count": 3,
        "exception_count": 1,
        "problem": None,
        "job_id": UUID(int=8),
        "started_at": NOW,
        "finished_at": later,
        "created_at": NOW,
        "updated_at": later,
        "row_version": 3,
    }
    out = schemas.SyncRunOut.model_validate(queries.sync_run_out(run))
    assert out.duration_seconds == 90 and out.status == "SUCCEEDED"
    assert queries.last_sync_run_out(run) == {
        "id": UUID(int=9),
        "status": "SUCCEEDED",
        "finished_at": later,
        "result": {"record_count": 3, "exception_count": 1},
    }
    assert queries.last_sync_run_out(None) is None


def test_connection_out_carries_the_reference_name_only_and_the_newest_run() -> None:
    row = {
        "tenant_id": TENANT,
        "id": CONNECTION,
        "code": "sf-quayside",
        "name": "Salesforce (mock)",
        "adapter": "SALESFORCE",
        "direction": "INBOUND",
        "entity_ids": [],
        "base_url": "/api/v1/__mocks__/salesforce",
        "config": {"default_performing_entity": "QUAY-US"},
        "secret_ref": "EREV_QUAYSIDE_SF_CLIENT_SECRET",
        "status": "DISABLED",
        "checkpoint": {},
        "last_test_at": None,
        "last_test_result": None,
        "last_test_detail": None,
        "created_at": NOW,
        "updated_at": NOW,
        "row_version": 1,
    }
    out = schemas.IntegrationConnectionOut.model_validate(queries.connection_out(row, None))
    dumped = out.model_dump()
    assert dumped["secret_ref"] == "EREV_QUAYSIDE_SF_CLIENT_SECRET"
    assert "secret" not in {key.replace("secret_ref", "") for key in dumped}
    assert out.last_sync_run is None
    assert "tenant_id" not in dumped


def test_connection_schema_lists_equal_the_04_check_literals() -> None:
    from typing import get_args

    assert set(get_args(schemas.Adapter)) == {
        "SALESFORCE",
        "STRIPE",
        "NETSUITE",
        "QUICKBOOKS_ONLINE",
        "CSV_GL",
    }
    assert set(get_args(schemas.SyncRunKind)) == {
        "INBOUND_POLL",
        "WEBHOOK_BATCH",
        "RECONCILIATION_SWEEP",
        "COA_SYNC",
        "TRIAL_BALANCE_PULL",
        "JOURNAL_EXPORT",
        "TEST_CONNECTION",
    }
    assert schemas.SyncRequestIn().kind == "INBOUND_POLL"
    with pytest.raises(ValueError):
        schemas.IntegrationConnectionIn.model_validate(
            {"code": "x", "name": "y", "adapter": "HUBSPOT", "direction": "INBOUND"}
        )


# --- composition-root hooks (DG-LAY-03) -----------------------------------------------------------


def test_http_client_factory_hook_fails_closed_until_registered() -> None:
    previous = sync._HOOKS.get("http")
    try:
        sync.register_http_client_factory(None)
        with pytest.raises(LookupError):
            sync.http_client("http://127.0.0.1:1")
        built: list[str] = []
        sync.register_http_client_factory(lambda base_url: built.append(base_url) or object())
        assert sync.http_client("http://127.0.0.1:1") is not None
        assert built == ["http://127.0.0.1:1"]
    finally:
        sync.register_http_client_factory(previous)


def billing_context() -> ports.InboundContext:
    return ports.InboundContext(
        tenant_code="quayside", base_url="/api/v1/__mocks__/stripe", config={}, client=object()
    )


def test_adapter_for_refuses_a_connection_without_base_url_and_reads_config_overrides() -> None:
    with pytest.raises(ports.Permanent):
        sync.adapter_for(
            {"adapter": "SALESFORCE", "base_url": None, "config": {}}, tenant_code="quayside"
        )
    salesforce.register()
    adapter = sync.adapter_for(
        {
            "adapter": "SALESFORCE",
            "base_url": "/api/v1/__mocks__/salesforce",
            "config": {"max_attempts": 4},
        },
        tenant_code="quayside",
        client=object(),
        config={"max_attempts": 1},
    )
    assert isinstance(adapter, salesforce.SalesforceAdapter)
    assert adapter._max_attempts == 1  # the probe's single attempt overrides the connection's
    stripe.register()
    billing: Any = sync.adapter_for(
        {"adapter": "STRIPE", "base_url": "/api/v1/__mocks__/stripe", "config": {}},
        tenant_code="quayside",
        client=object(),
        config={"max_attempts": 1},
    )
    assert isinstance(billing, stripe.StripeAdapter)
    assert billing._max_attempts == 1  # a Stripe probe is a single attempt too (04 §16.14)
    assert stripe.StripeAdapter(billing_context())._max_attempts == stripe.MAX_ATTEMPTS


def test_adapter_for_hands_the_callers_clock_to_the_adapter() -> None:
    """05 ADP-16; DG-KRN-TIME-06: an adapter reads the time through its ``now`` hook, and
    ``adapter_for`` sets the hook to the caller's clock — the sync job's, the probe's — so the 72
    hours of the sweep decision and the ``replay_at`` of a poll are measured on the application
    clock. A stored config member of that name never wins. The job built its adapter without the
    clock, so both read the wall clock."""
    salesforce.register()
    stripe.register()
    for code in ("SALESFORCE", "STRIPE"):
        clock = FrozenClock(NOW)
        adapter: Any = sync.adapter_for(
            {
                "adapter": code,
                "base_url": "/api/v1/__mocks__/source",
                "config": {ports.NOW_HOOK: "2000-01-01T00:00:00Z"},
            },
            tenant_code="quayside",
            client=object(),
            clock=clock,
        )
        assert adapter._now() == NOW, code
        clock.advance(timedelta(hours=73))
        assert adapter._now() == NOW + timedelta(hours=73), code


def test_sync_principal_holds_exactly_the_sync_permissions() -> None:
    principal = sync.sync_principal(TENANT, on_behalf_of=UUID(int=3))
    assert (
        principal.permissions
        == sync.SYNC_PERMISSIONS
        == {
            "contract.create",
            "masterdata.maintain",
            "modification.create",
        }
    )
    assert dict(principal.permission_scopes) == {code: "*" for code in sync.SYNC_PERMISSIONS}
    assert principal.on_behalf_of_id == UUID(int=3) and principal.id is None


def test_sync_request_outbox_handler_is_registered_with_its_dedupe_key() -> None:
    assert outbox.HANDLERS[OutboxTopic.SYNC_REQUEST] is sync_outbox.dispatch_sync_request
    assert outbox.PENDING_OUTBOX_HANDLERS == ()
    assert sync_outbox.sync_request_key(CONNECTION, "INBOUND_POLL", "2026-09-21T12") == (
        f"sync:{CONNECTION}:INBOUND_POLL:2026-09-21T12"
    )


def test_sync_kind_rules_for_an_inbound_connection() -> None:
    connection = {"adapter": "SALESFORCE", "status": "ACTIVE"}
    assert commands._kind_errors(connection, "INBOUND_POLL") == []
    assert commands._kind_errors(connection, "RECONCILIATION_SWEEP") == []
    for refused in ("WEBHOOK_BATCH", "TEST_CONNECTION", "COA_SYNC", "JOURNAL_EXPORT"):
        [error] = commands._kind_errors(connection, refused)
        assert error.field == "kind" and error.rule_id == "T-INT-02"
    [gl] = commands._kind_errors({"adapter": "NETSUITE", "status": "ACTIVE"}, "INBOUND_POLL")
    assert "NETSUITE" in gl.message


def test_counts_json_and_problem_shape() -> None:
    """SYNC-PROBLEM-SHAPE-1 (04 T-INT-02 rev 1.90; PRD ERR-56): the run's own problem is the
    T-PLT-27 RFC 9457 envelope of ``sync-objects-not-applied`` with the failure records verbatim in
    the extension member ``failures`` and an empty API-C-05 ``errors``; None when every object was
    applied; the cancelled run carries the cancelled detail."""
    from erev_api.jobs.registry import failure_problem
    from erev_api.problems import TYPE_BASE
    from erev_api.schemas.common import ProblemOut

    run_id = UUID(int=0x51)
    counts = sync.Counts(notifications=5, duplicates=1, fetched=3, records=3, stale=1, exceptions=2)
    counts.failures.append({"step": "book", "external_id": "X", "external_version": "1"})
    assert counts.as_json()["failures"] == 1 and counts.as_json()["notifications"] == 5
    fetch_failure = {"step": "fetch", "external_id": "Y", "external_versions": ["2"], "error": "e"}
    problem = sync._problem(counts, run_id=run_id, fetch_failures=(fetch_failure,), cancelled=False)
    assert problem is not None
    # the envelope: failure_problem's key set plus the ``failures`` extension
    reference = failure_problem(RuntimeError("x"), UUID(int=1))
    assert set(problem) == set(reference) | {"failures"}
    assert problem["type"] == TYPE_BASE + "sync-objects-not-applied"
    assert problem["title"] == "Some source objects were not applied" and problem["status"] == 422
    assert problem["instance"] == f"/api/v1/sync-runs/{run_id}" and problem["code"] is None
    assert problem["errors"] == []  # API-C-05-shaped, homogeneous across problems
    assert problem["failures"] == [
        fetch_failure,
        {"step": "book", "external_id": "X", "external_version": "1"},
    ]  # the records verbatim, fetch failures first
    assert problem["detail"] == (
        "2 of 4 source objects were not applied. Each failure names the object and why it was not"
        " applied. Fix the named objects in the source system, then run the sync again."
    )
    ProblemOut.model_validate(problem)  # errors[] validates as ProblemErrorOut items
    assert sync._problem(sync.Counts(), run_id=run_id, fetch_failures=(), cancelled=False) is None
    cancelled = sync._problem(
        sync.Counts(records=2), run_id=run_id, fetch_failures=(), cancelled=True
    )
    assert cancelled is not None and cancelled["failures"] == []
    assert cancelled["title"] == "Some source objects were not applied"
    assert cancelled["detail"] == (
        "The run was cancelled after 2 objects. The next run starts again from the last checkpoint."
    )


def test_probe_failure_problem_is_the_t_plt_27_envelope() -> None:
    """PRD ERR-57: the failed TEST_CONNECTION probe stores the ``connection-test-failed`` envelope
    with the probe's reason in the detail and no failure records."""
    from erev_api.problems import TYPE_BASE
    from erev_api.schemas.common import ProblemOut

    run_id = UUID(int=0x52)
    problem = sync.run_problem(
        sync.CONNECTION_TEST_FAILED,
        sync.PROBE_FAILED_DETAIL.format(reason="HTTP 401 from the token endpoint"),
        run_id=run_id,
        failures=[],
    )
    assert problem["type"] == TYPE_BASE + "connection-test-failed"
    assert problem["title"] == "Test connection failed" and problem["status"] == 422
    assert problem["detail"] == (
        "The connection could not be verified: HTTP 401 from the token endpoint. Check the base URL"
        " and the secret reference, then test again."
    )
    assert problem["instance"] == f"/api/v1/sync-runs/{run_id}"
    assert problem["errors"] == [] and problem["failures"] == []
    ProblemOut.model_validate(problem)


# --- the parent's governed basis (Codex 0339 §1 DIN12-AMENDMENT-BASIS-1) -------------------------


def test_same_id_amendment_diffs_against_the_booked_basis_not_its_own_candidate() -> None:
    """A / v1 L1 100 booked; A / v2 L1 120 with an Amendment_Reason and no Parent_Order: the basis
    is the BOOKED line, so the delta is +20 (PRICE_CHANGE), never 120 − 120."""
    basis = {"L1": _parent("L1", "QUAY-PLAT", "1", "100.00")}  # the booked line is the basis
    v2 = _draft(
        (_line("L1", "QUAY-PLAT", "1", "120.00"),),
        external_order_id="A",
        external_version="2",
        parent_order_external_id=None,
        amendment_reason="Upsell",
    )
    assert v2.is_amendment is True
    lines, kind = sync.amendment_lines(v2, basis)
    assert [
        (line["obligation_key"], line["action"], line["consideration_delta"]["amount"])
        for line in lines
    ] == [("L1", "CHANGE", "20.00")]
    assert kind is ModificationKind.PRICE_CHANGE


class _BasisResult:
    def __init__(self, scalar: Any = None, rows: tuple[Any, ...] = ()) -> None:
        self._scalar, self.rows = scalar, rows

    def scalar(self) -> Any:  # ``queries.primary_book`` reads ``.scalar()``
        return self._scalar

    def scalar_one_or_none(self) -> Any:
        return self._scalar

    def mappings(self) -> Any:
        return iter(self.rows)


BOOKED_100: Final = {
    "id": UUID(int=1),
    "event_type": "CONTRACT_BOOKED",
    "supersedes_event_id": None,
    "payload": {
        "lines": [
            {
                "obligation_key": "L1",
                "product_code": "QUAY-PLAT",
                "quantity": "2",
                "total_price": {"amount": "100.00", "currency": "USD"},
            },
            {
                "obligation_key": "L2",
                "product_code": "QUAY-SVC",
                "quantity": "10",
                "total_price": {"amount": "5000.00", "currency": "USD"},
            },
        ]
    },
}


def _projection_session(
    rows: tuple[dict[str, Any], ...],
    calls: list[str],
    monkeypatch: pytest.MonkeyPatch,
    *,
    recorded_head: int | None = 3,
    dirty: bool = False,
    booked: dict[str, Any] | None = None,
) -> Any:
    """A fake session answering every read of ``_parent_basis`` — the staleness reads (recorded
    stream head, dirty_since), the primary book, the head version, the obligation versions joined
    to their obligations — and the stream read of the booked lines; anything else fails by name."""
    from datetime import datetime as _dt

    from erev_api.domain.contracts import repo
    from sqlalchemy.dialects import postgresql

    monkeypatch.setattr(repo, "stream", lambda session, contract_id: [booked or BOOKED_100])

    class Session:
        def execute(self, statement: Any) -> _BasisResult:
            sql = str(statement.compile(dialect=postgresql.dialect()))
            calls.append(sql)
            if "FROM erev.contract_computation" in sql:
                heads = None if recorded_head is None else {str(UUID(int=0x99)): recorded_head}
                return _BasisResult(scalar=heads)
            if "FROM erev.combination_group" in sql:
                return _BasisResult(scalar=_dt(2026, 9, 21, tzinfo=UTC) if dirty else None)
            if "FROM erev.book" in sql:
                return _BasisResult(scalar="ASC606")
            if "FROM erev.contract_version" in sql:
                return _BasisResult(scalar=UUID(int=0x55))
            if "FROM erev.obligation_version" in sql:
                return _BasisResult(rows=rows)
            raise AssertionError(sql)

    return Session()


def _projection_row(
    key: str | None,
    code: str,
    quantity: str,
    stated: str,
    *,
    original_quantity: str | None = None,
    original_stated: str | None = None,
    principal_agent: str = "PRINCIPAL",
    parent_obligation_id: UUID | None = None,
    regrouped_from_obligation_id: UUID | None = None,
) -> dict[str, Any]:
    """One current obligation version joined to its obligation; the inception values default to
    the BOOKED_100 lines (L1 2 / 100, L2 10 / 5000) so a row is an unchanged source line unless a
    test says otherwise."""
    defaults = {"L1": ("2", "100.00"), "L2": ("10", "5000.00")}
    o_qty, o_price = defaults.get(key or "", (quantity, stated))
    return {
        "obligation_id": UUID(int=hash(key or "x") & 0xFFFF),
        "obligation_key": key,
        "product_code": code,
        "quantity": Decimal(quantity),
        "stated_price": Decimal(stated),
        "original_quantity": Decimal(original_quantity or o_qty),
        "original_stated_price": Decimal(original_stated or o_price),
        "principal_agent": principal_agent,
        "start_date": None,
        "end_date": None,
        "parent_obligation_id": parent_obligation_id,
        "regrouped_from_obligation_id": regrouped_from_obligation_id,
    }


def _parent_row(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": UUID(int=0x99),
        "external_id": "Q-001",
        "latest_computation_id": UUID(int=0x44),
        "head_stream_version": 3,
        "combination_group_id": UUID(int=0x66),
        "status": "ACTIVE",
    }
    row.update(over)
    return row


def test_parent_basis_is_the_head_projection_including_a_legacy_amendment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex 0403 §3's REQUIRED witness: a real principal parent booked 2 / 100, an applied
    row-less legacy amendment +1 / +20 (current 3 / 120), an incoming 4 / 150 → +1 / +30; then
    ANOTHER amendment (5 / 170) diffs against the same unchanged baseline (+2 / +50): unapplied and
    newer candidates never enter it. Neither ``source_order`` nor T-CON-06 is read."""
    calls: list[str] = []
    session = _projection_session(
        (
            _projection_row("L1", "QUAY-PLAT", "3", "120.00"),  # 2 / 100 + legacy 1 / 20
            _projection_row("L2", "QUAY-SVC", "10", "5000.00"),
        ),
        calls,
        monkeypatch,
    )
    found = sync._parent_basis(session, _parent_row())
    assert found.refused is None and found.unkeyed == ()
    basis = dict(found.lines)
    assert basis["L1"]["quantity"] == Decimal(3) and basis["L1"]["total_price"] == Decimal("120.00")
    assert not any("source_order" in sql or "erev.modification" in sql for sql in calls)
    first = _draft(
        (_line("L1", "QUAY-PLAT", "4", "150.00"), _line("L2", "QUAY-SVC", "10", "5000.00")),
        amendment_reason="Upsell",
    )
    lines, kind = sync.amendment_lines(first, basis)
    assert [
        (
            line["obligation_key"],
            line["action"],
            line["quantity_delta"],
            line["consideration_delta"]["amount"],
        )
        for line in lines
    ] == [("L1", "CHANGE", "1", "30.00")]
    assert kind is ModificationKind.PRICE_CHANGE
    # the first draft is UNAPPLIED: the second amendment sees the same baseline
    again = sync._parent_basis(
        _projection_session(
            (
                _projection_row("L1", "QUAY-PLAT", "3", "120.00"),
                _projection_row("L2", "QUAY-SVC", "10", "5000.00"),
            ),
            [],
            monkeypatch,
        ),
        _parent_row(),
    )
    second = _draft(
        (_line("L1", "QUAY-PLAT", "5", "170.00"), _line("L2", "QUAY-SVC", "10", "5000.00")),
        external_version="3",
        amendment_reason="Upsell again",
    )
    lines2, _ = sync.amendment_lines(second, dict(again.lines))
    assert [(line["quantity_delta"], line["consideration_delta"]["amount"]) for line in lines2] == [
        ("2", "50.00")
    ]


def test_parent_basis_refuses_netted_split_and_merged_obligations_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex 0403 §3: an unchanged gross 100 whose obligation retains a NET 20 (s03 agent) must
    not yield a false +80 — refused by name; so are a bundle component (split), a regrouped
    obligation, an obligation key that is no booked line, and a booked line without an obligation
    of its own (merged)."""
    netted = _projection_session(
        (
            _projection_row(
                "L1", "QUAY-PLAT", "2", "20.00", original_stated="20.00", principal_agent="AGENT"
            ),
            _projection_row("L2", "QUAY-SVC", "10", "5000.00"),
        ),
        [],
        monkeypatch,
    )
    found = sync._parent_basis(netted, _parent_row())
    assert found.refused == "BASIS_UNSUPPORTED_TRANSFORMATION"
    assert found.message.startswith("The parent contract's obligations are not one unchanged")
    reasons = list(found.detail["reasons"])
    assert "L1: net presentation (agent)" in reasons
    assert "L1: inception basis 2 / 20.00 differs from the booked gross line 2 / 100.00" in reasons
    assert found.lines == {}  # no basis, hence no +80 and no draft
    split = _projection_session(
        (
            _projection_row("L1/a", "QUAY-PLAT-A", "1", "60.00", parent_obligation_id=UUID(int=7)),
            _projection_row("L1/b", "QUAY-PLAT-B", "1", "40.00", parent_obligation_id=UUID(int=7)),
            _projection_row("L2", "QUAY-SVC", "10", "5000.00"),
        ),
        [],
        monkeypatch,
    )
    refused = "; ".join(sync._parent_basis(split, _parent_row()).detail["reasons"])
    assert "L1/a: not a booked source line (split or renamed)" in refused
    assert "L1: booked source line without an obligation of its own (merged)" in refused
    merged = _projection_session(
        (
            _projection_row(
                "L1",
                "QUAY-PLAT",
                "12",
                "5100.00",
                original_quantity="12",
                original_stated="5100.00",
            ),
        ),
        [],
        monkeypatch,
    )
    refused = "; ".join(sync._parent_basis(merged, _parent_row()).detail["reasons"])
    assert (
        "L1: inception basis 12 / 5100.00 differs from the booked gross line 2 / 100.00" in refused
    )
    assert "L2: booked source line without an obligation of its own (merged)" in refused
    regrouped = _projection_session(
        (
            _projection_row(
                "L1", "QUAY-PLAT", "2", "100.00", regrouped_from_obligation_id=UUID(int=8)
            ),
            _projection_row("L2", "QUAY-SVC", "10", "5000.00"),
        ),
        [],
        monkeypatch,
    )
    assert (
        "L1: regrouped obligation" in sync._parent_basis(regrouped, _parent_row()).detail["reasons"]
    )


def test_parent_basis_is_refused_by_name_when_the_computation_predates_the_stream_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Team-lead's guard (Codex 0339 §1): a computation whose recorded head of the contract is
    older than the contract's head, or a dirty group, gives a NAMED refusal and no lines — never a
    silent fallback to the booked payload."""
    rows = (
        _projection_row("L1", "QUAY-PLAT", "2", "100.00"),
        _projection_row("L2", "QUAY-SVC", "10", "5000.00"),
    )
    calls: list[str] = []
    older = sync._parent_basis(
        _projection_session(rows, calls, monkeypatch, recorded_head=2), _parent_row()
    )
    assert older.refused == "BASIS_STALE" and older.message.endswith("retry after the recompute.")
    assert older.detail["computed_head"] == 2 and older.detail["stream_head"] == 3
    assert older.lines == {} and not any("obligation_version" in sql for sql in calls)
    dirty = sync._parent_basis(
        _projection_session(rows, [], monkeypatch, dirty=True), _parent_row()
    )
    assert dirty.refused is not None and dirty.lines == {}
    current = sync._parent_basis(_projection_session(rows, [], monkeypatch), _parent_row())
    assert current.refused is None and current.lines["L1"]["total_price"] == Decimal("100.00")


def test_active_parent_without_a_computation_is_refused_never_reset_to_inception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex 0417 §1: the booked-payload fallback is for a DRAFT (never computed) parent only; an
    ACTIVE parent without a computation, or without a primary-book version of its latest
    computation, is refused BASIS_STALE — never silently reset to its inception lines."""
    from erev_api.domain.contracts import repo
    from sqlalchemy.dialects import postgresql

    monkeypatch.setattr(repo, "stream", lambda session, contract_id: [BOOKED_100])
    active = _parent_row(latest_computation_id=None, status="ACTIVE")
    found = sync._parent_basis(object(), active)  # type: ignore[arg-type]
    assert found.refused == "BASIS_STALE" and found.lines == {}
    assert found.detail["reason"] == "no computation" and found.detail["computed_head"] is None
    draft = _parent_row(latest_computation_id=None, status="DRAFT")
    lines = sync._parent_basis(object(), draft).lines  # type: ignore[arg-type]
    assert lines["L1"]["total_price"] == Decimal("100.00")
    # a computation without a primary-book version: refused for an ACTIVE parent too
    session = _projection_session((), [], monkeypatch)
    original = session.execute

    def execute(statement: Any) -> Any:
        sql = str(statement.compile(dialect=postgresql.dialect()))
        if "FROM erev.contract_version" in sql:
            return _BasisResult(scalar=None)
        return original(statement)

    session.execute = execute  # type: ignore[method-assign]
    found = sync._parent_basis(session, _parent_row(status="ACTIVE"))
    assert found.refused == "BASIS_STALE" and "no primary-book version" in found.detail["reason"]


def test_agent_netted_parent_never_drafts_the_gross_minus_net_delta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex 0417 §1's exact case: the parent's gross 100 was netted to a stated_price of 20 (s03
    agent); an incoming gross 120 must NOT draft +100 (120 − 20). The seam is the refusal:
    ``_route_amendment`` records ``BASIS_UNSUPPORTED_TRANSFORMATION`` and returns BEFORE
    ``amendment_lines`` — no candidate rows, no CHANGE line, no kind, no draft (Codex 0505 §2 (b):
    the helper is not what prevents the +100)."""
    netted = _projection_session(
        (
            _projection_row(
                "L1", "QUAY-PLAT", "2", "20.00", original_stated="20.00", principal_agent="AGENT"
            ),
            _projection_row("L2", "QUAY-SVC", "10", "5000.00"),
        ),
        [],
        monkeypatch,
    )
    found = sync._parent_basis(netted, _parent_row())
    assert found.refused == "BASIS_UNSUPPORTED_TRANSFORMATION" and found.lines == {}
    assert found.message.endswith("make the modification by hand.")
    incoming = _draft(
        (_line("L1", "QUAY-PLAT", "2", "120.00"), _line("L2", "QUAY-SVC", "10", "5000.00")),
        amendment_reason="Upsell",
    )
    # Production never calls amendment_lines on a refused basis (see _route_amendment). Fed the
    # refused, EMPTY basis directly, the helper would treat every line as new (ADD) rather than
    # diff the gross 120 against the netted 20 — shown only to record that the +100 could not come
    # from the helper either; the refusal above is the witness.
    lines, _ = sync.amendment_lines(incoming, dict(found.lines))
    assert all(line["action"] == "ADD" for line in lines)  # no CHANGE line at all
    assert not any(line["consideration_delta"]["amount"] == "100.00" for line in lines)


def test_parent_basis_reports_an_obligation_without_a_line_external_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _projection_session(
        (
            _projection_row("L1", "QUAY-PLAT", "2", "100.00"),
            _projection_row("L2", "QUAY-SVC", "10", "5000.00"),
            _projection_row(None, "QUAY-ADDON", "1", "1.00"),
        ),
        [],
        monkeypatch,
    )
    found = sync._parent_basis(session, _parent_row())
    assert found.refused is None and set(found.lines) == {"L1", "L2"} and len(found.unkeyed) == 1


def test_parent_basis_of_an_uncomputed_draft_is_its_booked_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A DRAFT never computed has no projection: the stream's latest non-voided CONTRACT_BOOKED
    payload is the basis; candidates are not events, so they cannot be in it."""
    booked = {
        "id": UUID(int=1),
        "event_type": "CONTRACT_BOOKED",
        "supersedes_event_id": None,
        "payload": {
            "lines": [
                {
                    "obligation_key": "L1",
                    "product_code": "QUAY-PLAT",
                    "quantity": "1",
                    "total_price": {"amount": "100.00", "currency": "USD"},
                    "start_date": "2026-09-01",
                },
            ]
        },
    }
    from erev_api.domain.contracts import repo

    monkeypatch.setattr(repo, "stream", lambda session, contract_id: [booked])
    found = sync._parent_basis(
        object(),  # type: ignore[arg-type]
        {"id": UUID(int=0x99), "latest_computation_id": None, "status": "DRAFT"},
    )
    assert found.unkeyed == () and found.refused is None
    assert found.lines["L1"]["total_price"] == Decimal("100.00")
    assert found.lines["L1"]["start_date"] == date(2026, 9, 1)


def test_parent_basis_prefers_the_latest_non_voided_booking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = {
        "id": UUID(int=1),
        "event_type": "CONTRACT_BOOKED",
        "supersedes_event_id": None,
        "payload": {
            "lines": [
                {
                    "obligation_key": "L1",
                    "product_code": "P",
                    "quantity": "1",
                    "total_price": {"amount": "1.00", "currency": "USD"},
                }
            ]
        },
    }
    second = {
        "id": UUID(int=2),
        "event_type": "CONTRACT_BOOKED",
        "supersedes_event_id": UUID(int=1),
        "payload": {
            "lines": [
                {
                    "obligation_key": "L1",
                    "product_code": "P",
                    "quantity": "1",
                    "total_price": {"amount": "2.00", "currency": "USD"},
                }
            ]
        },
    }
    from erev_api.domain.contracts import repo

    monkeypatch.setattr(repo, "stream", lambda session, contract_id: [first, second])
    found = sync._parent_basis(
        object(),  # type: ignore[arg-type]
        {"id": UUID(int=0x99), "latest_computation_id": None, "status": "DRAFT"},
    )
    basis = dict(found.lines)
    assert basis["L1"]["total_price"] == Decimal(
        "2.00"
    )  # the superseding booking, not the voided one


# --- remediation path (04 §16.14 rev 1.81; team-lead's rulings on Codex 0339 §2) ------------------


def test_reprocessable_admits_a_sync_item_only_through_the_registered_reprocessor() -> None:
    from erev_api.domain.imports import exceptions as queue

    def row(**over: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "disposition": "remediable",
            "source": "SYNC",
            "combination_group_id": None,
            "source_record_id": UUID(int=5),
        }
        base.update(over)
        return base

    assert ExceptionSource.SYNC in queue.REPROCESSORS  # registered by the sync module at import
    assert queue.REPROCESSORS[ExceptionSource.SYNC] is sync.request_record_reprocess
    assert queue._reprocessable(row()) is True
    assert queue._reprocessable(row(source_record_id=None)) is False  # no stored record to re-run
    assert queue._reprocessable(row(disposition="discarded")) is False
    assert queue._reprocessable(row(source="IMPORT")) is False  # no reprocessor registered
    assert queue._reprocessable(row(source="ENGINE", combination_group_id=UUID(int=9))) is True
    assert queue._reprocessable(row(source="ENGINE")) is False


def test_request_reprocess_dispatches_a_sync_item_to_the_registered_reprocessor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from erev_api.domain.imports import exceptions as queue

    item = {
        "id": UUID(int=0x1E),
        "source": "SYNC",
        "code": "SOURCE_RECORD_REJECTED",
        "disposition": "remediable",
        "source_record_id": UUID(int=5),
        "contract_id": None,
        "combination_group_id": None,
        "source_payload": None,
        "entity_id": None,
        "status": "OPEN",
    }
    calls: list[tuple[Any, Any]] = []
    monkeypatch.setattr(queue, "_locked", lambda uow, item_id: dict(item))
    monkeypatch.setattr(queue, "_require", lambda uow, row, action: None)

    def reprocessor(uow: Any, row: Any) -> Any:
        calls.append((uow, row))
        return SimpleNamespace(id=UUID(int=0x0B))

    monkeypatch.setitem(queue.REPROCESSORS, ExceptionSource.SYNC, reprocessor)
    audited: list[dict[str, Any]] = []
    uow = SimpleNamespace(audit=lambda **kw: audited.append(kw), session=object())
    job = queue.request_reprocess(uow, item_id=UUID(int=0x1E))  # type: ignore[arg-type]
    assert job.id == UUID(int=0x0B) and calls[0][1]["source_record_id"] == UUID(int=5)
    assert audited[0]["action"] == "exception_item.reprocess"
    assert audited[0]["after"] == {
        "job_id": str(UUID(int=0x0B)),
        "source_record_id": str(UUID(int=5)),
    }
    assert audited[0]["contract_ids"] == []  # the item names no contract (04 T-PLT-19)


def test_resolve_products_uses_the_connection_alias_for_unknown_codes() -> None:
    from sqlalchemy.dialects import postgresql

    calls: list[str] = []
    addon = UUID(int=0xAD)

    class Session:
        def execute(self, statement: Any) -> Any:
            sql = str(statement.compile(dialect=postgresql.dialect()))
            calls.append(sql)
            if (
                "FROM erev.product" in sql
                and "external_id" not in sql
                and "product.id IN" not in sql
            ):
                return iter([("QUAY-PLAT", UUID(int=0xA1))])
            if "FROM erev.external_id_map" in sql:
                assert "external_id_map.object_type =" in sql  # the product alias only
                return iter([("SF-PROD-X99", addon)])
            if "FROM erev.product" in sql and "product.id IN" in sql:
                return iter([(addon, "QUAY-ADDON")])
            raise AssertionError(sql)

    found = sync.resolve_products(Session(), CONNECTION, ["QUAY-PLAT", "SF-PROD-X99", "SF-NOPE"])  # type: ignore[arg-type]
    assert found["QUAY-PLAT"].product_code == "QUAY-PLAT" and found["QUAY-PLAT"].via_alias is False
    assert found["SF-PROD-X99"].product_code == "QUAY-ADDON" and found["SF-PROD-X99"].via_alias
    assert found["SF-PROD-X99"].product_id == addon
    assert "SF-NOPE" not in found  # still unmapped → PRODUCT_UNMAPPED


def test_partial_booking_splits_the_mapped_and_unmapped_lines() -> None:
    draft = _draft(
        (_line("L1", "QUAY-PLAT", "1", "50000.00"), _line("L2", "SF-PROD-X99", "1", "5000.00")),
        parent_order_external_id=None,
        amendment_reason=None,
    )
    resolved = {"QUAY-PLAT": sync.ResolvedProduct(UUID(int=0xA1), "QUAY-PLAT", False)}
    assert sync.obj_lines(draft, resolved) == [True, False]
    aliased = {
        "QUAY-PLAT": sync.ResolvedProduct(UUID(int=0xA1), "QUAY-PLAT", False),
        "SF-PROD-X99": sync.ResolvedProduct(UUID(int=0xAD), "QUAY-ADDON", True),
    }
    mapped = sync._with_resolved_codes(draft, aliased)
    assert [line.product_code for line in mapped.lines] == ["QUAY-PLAT", "QUAY-ADDON"]
    assert sync.obj_lines(mapped, aliased) == [True, True]
    assert [line.product_code for line in draft.lines] == ["QUAY-PLAT", "SF-PROD-X99"]  # pure


def test_stored_objects_rebuild_source_objects_with_their_identity() -> None:
    from sqlalchemy.dialects import postgresql

    class Session:
        def execute(self, statement: Any) -> Any:
            sql = str(statement.compile(dialect=postgresql.dialect()))
            assert "FROM erev.source_record" in sql

            class R:
                def mappings(self) -> Any:
                    return iter(
                        [
                            {
                                "id": UUID(int=5),
                                "source_system": "SALESFORCE",
                                "object_type": "ORDER",
                                "external_id": "SF-ORD-Q-003",
                                "external_version": "1",
                                "version_order": 1,
                                "payload": {"Id": "SF-ORD-Q-003", "Status": "Activated"},
                            }
                        ]
                    )

            return R()

    [(record_id, obj)] = sync.stored_objects(Session(), [UUID(int=5)])  # type: ignore[arg-type]
    assert record_id == UUID(int=5) and obj.external_id == "SF-ORD-Q-003"
    assert obj.source_system is SourceSystem.SALESFORCE and obj.version_order == 1
    assert obj.payload["Status"] == "Activated"


def _settle_world(
    monkeypatch: pytest.MonkeyPatch, item: dict[str, Any], identity: tuple[str, str] | None
) -> tuple[Any, list[tuple[UUID, bool]]]:
    from erev_api.domain.imports import exceptions as queue
    from sqlalchemy.dialects import postgresql

    class Session:
        def execute(self, statement: Any) -> Any:
            sql = str(statement.compile(dialect=postgresql.dialect()))
            if "FROM erev.source_record" in sql:
                return SimpleNamespace(one_or_none=lambda: identity)
            assert "FROM erev.exception_item" in sql

            class R:
                def mappings(self) -> Any:
                    return self

                def one_or_none(self) -> Any:
                    return item

            return R()

    settled: list[tuple[UUID, bool]] = []
    monkeypatch.setattr(
        queue,
        "settle_record_reprocess",
        lambda uow, item_id, *, resolved, resolution=None: settled.append((item_id, resolved)),
    )
    from types import SimpleNamespace

    return SimpleNamespace(session=Session()), settled


def test_settle_item_resolves_only_a_processed_record_not_raised_again_without_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """04 §16.14 rev 1.81 (Codex 0545 §2 R2 / 0606): (a) processed in this run, (b) its own dedupe
    key not raised again, (c) no failure record carrying the record's identity — each alone keeps
    the item open; the product repair resolves it; a record the reprocess did not run over is not
    touched at all (``reprocessed_at`` stays truthful)."""
    from types import SimpleNamespace  # noqa: F401 — the helper imports it

    record = UUID(int=5)
    item = {
        "id": UUID(int=0x1E),
        "business_key": "SF-ORD-Q-003",
        "dedupe_key": "SYNC:PRODUCT_UNMAPPED:SF-ORD-Q-003:SF-PROD-X99",
        "source_record_id": record,
    }
    uow, settled = _settle_world(monkeypatch, item, ("SF-ORD-Q-003", "1"))
    counts = sync.Counts()
    counts.processed_records.add(record)
    # the product repair: processed, not raised again, no failure → RESOLVED
    assert sync._settle_item(uow, item["id"], counts, attempted={record}) is True
    # not run over by this reprocess → untouched (no settle call at all)
    assert sync._settle_item(uow, item["id"], counts, attempted=set()) is False
    assert len(settled) == 1
    # (a) run over but NOT processed (a refusal or failure excluded it) → stays open
    assert sync._settle_item(uow, item["id"], sync.Counts(), attempted={record}) is False
    # (b) another key of the same order (a partially repaired order) does not block; the item's own
    # key raised again does
    counts.raised_keys.add("SYNC:PRODUCT_UNMAPPED:SF-ORD-Q-003:SF-PROD-Y77")
    assert sync._settle_item(uow, item["id"], counts, attempted={record}) is True
    counts.raised_keys.add(item["dedupe_key"])
    assert sync._settle_item(uow, item["id"], counts, attempted={record}) is False
    # (c) a failure record carrying the record's identity → stays open; another version's does not
    counts = sync.Counts()
    counts.processed_records.add(record)
    counts.failures.append(
        {"step": "rebook", "external_id": "SF-ORD-Q-003", "external_version": "2"}
    )
    assert sync._settle_item(uow, item["id"], counts, attempted={record}) is True
    counts.failures.append(
        {"step": "rebook", "external_id": "SF-ORD-Q-003", "external_version": "1"}
    )
    assert sync._settle_item(uow, item["id"], counts, attempted={record}) is False
    assert [resolved for _, resolved in settled] == [True, False, True, False, True, False]


def test_raise_remembers_the_items_dedupe_key(monkeypatch: pytest.MonkeyPatch) -> None:
    raised: list[dict[str, Any]] = []
    monkeypatch.setattr(sync, "raise_exception_item", lambda uow, **kw: raised.append(kw))
    counts = sync.Counts()
    sync._raise(object(), counts, dedupe="SYNC:X:1", code="X", message="m")  # type: ignore[arg-type]
    assert counts.raised_keys == {"SYNC:X:1"} and raised[0]["dedupe"] == "SYNC:X:1"


def test_apply_object_true_is_totals_inclusion_and_processed_is_a_distinct_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex 0606 R2: ``apply_object`` returns True (counted in the control totals) even when the
    ingestion recorded a refusal or raised an item; only a clean application marks the record
    PROCESSED."""
    from types import SimpleNamespace

    draft = _draft((_line("L1", "QUAY-PLAT", "1", "100.00"),), parent_order_external_id=None)

    class Adapter:
        def normalise(self, obj: Any, mapping_version: str) -> Any:
            return ports.NormalisedRecords(mapping_version=mapping_version, orders=(draft,))

    connection = {"id": CONNECTION, "adapter": "SALESFORCE", "config": {}}
    obj = _object("SF-ORD-Q-009", "1")
    record = UUID(int=5)

    def refused(uow: Any, connection: Any, draft: Any, obj: Any, **kw: Any) -> None:
        sync._failure(
            kw["counts"], "reuse", obj, "differs", rule_id="SOURCE_ORDER_CONTENT_MISMATCH"
        )

    def raised(uow: Any, connection: Any, draft: Any, obj: Any, **kw: Any) -> None:
        kw["counts"].raised_keys.add("SYNC:PRODUCT_UNMAPPED:SF-ORD-Q-009:X")

    def clean(uow: Any, connection: Any, draft: Any, obj: Any, **kw: Any) -> None:
        kw["counts"].contracts_booked += 1

    for ingest, processed in ((refused, False), (raised, False), (clean, True)):
        monkeypatch.setattr(sync, "ingest_draft", ingest)
        counts = sync.Counts()
        loaded: list[tuple[str, str, str, Decimal]] = []
        included = sync.apply_object(
            SimpleNamespace(session=object()),  # type: ignore[arg-type]
            Adapter(),  # type: ignore[arg-type]
            connection,
            obj,
            notified_versions=("1",),
            sync_run_id=UUID(int=9),
            counts=counts,
            loaded=loaded,
            stored_id=record,  # a reprocess: the stored record, no store
        )
        assert included is True and len(loaded) == 1  # counted in the totals regardless
        assert (record in counts.processed_records) is processed
        assert counts.reprocessed == 1 and counts.records == 1


# --- F-ADM-ROUTE-DETAIL-1: the failure record names the refused object; the detail nests -------


def test_refused_amendment_failure_record_names_the_amendment_and_nests_the_parent_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Team-lead's ruling on the a7b328b1 observation: ``_route_amendment`` records the refused
    AMENDMENT's external id on the failure record and the parent's external id, the heads and the
    reasons under ``detail`` — each id in its own place (exception-evidence traceability)."""
    from types import SimpleNamespace

    parent = {"id": UUID(int=0xC0), "external_id": "SF-ORD-P", "status": "ACTIVE"}
    stale = {"external_id": "SF-ORD-P", "computed_head": 2, "stream_head": 3, "dirty_since": None}
    monkeypatch.setattr(sync, "_parent_contract", lambda session, connection_id, external: parent)
    monkeypatch.setattr(
        sync,
        "_parent_basis",
        lambda session, row: sync.ParentBasis({}, refused=sync.BASIS_STALE, detail=stale),
    )
    recorded: list[Any] = []
    monkeypatch.setattr(
        sync.grouping, "record_candidate", lambda uow, order: recorded.append(order)
    )
    draft = _draft(
        (_line("SF-OI-P-1", "AVM-SEAT-MO", "4", "150.00"),),
        external_order_id="SF-ORD-P-A0",
        parent_order_external_id="SF-ORD-P",
    )
    obj = _object("SF-ORD-P-A0", "1", Parent_Order__c="SF-ORD-P")
    counts = sync.Counts()
    sync._route_amendment(
        SimpleNamespace(session=object()),  # type: ignore[arg-type]
        {"id": CONNECTION},
        draft,
        SimpleNamespace(),  # type: ignore[arg-type]  # never recorded: the refusal comes first
        obj,
        source_record_id=UUID(int=5),
        sync_run_id=UUID(int=6),
        counts=counts,
    )
    assert recorded == [] and counts.candidates == 0 and counts.modifications_drafted == 0
    [failure] = counts.failures
    assert failure["external_id"] == "SF-ORD-P-A0"  # the REFUSED amendment, not the parent
    assert failure["external_version"] == "1" and failure["object_type"] == "ORDER"
    assert failure["step"] == "amendment" and failure["rule_id"] == "BASIS_STALE"
    assert failure["error"] == sync.BASIS_STALE_MESSAGE
    assert failure["detail"] == stale  # the parent's id and the heads, nested, in their place
    assert "computed_head" not in failure and "stream_head" not in failure


def test_failure_record_identity_members_are_never_overwritten_by_extra_keys() -> None:
    """The identity members are written last: a colliding extra key cannot rename the record."""
    counts = sync.Counts()
    obj = _object("SF-ORD-X", "7")
    sync._failure(
        counts, "probe", obj, "boom", external_id="SOMEONE-ELSE", external_version="0", note="n"
    )
    [failure] = counts.failures
    assert (failure["external_id"], failure["external_version"]) == ("SF-ORD-X", "7")
    assert failure["note"] == "n" and failure["error"] == "boom" and failure["step"] == "probe"
