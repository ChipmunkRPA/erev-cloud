"""Stage 08 ``LATE_EVENT`` findings published through ``compute`` (ENGINE_SPEC §8.4 S08-R-10,
S08-R-11; ENGINE_SPEC §0.5 diagnostics, CV-43; L4-1-Q-8; lane L5-5).

``late_events`` computed the findings, but no orchestration called it, so a delivery effective in a
closed period posted with ``reason_code = LATE_EVENT`` and raised no finding. The book loop now
runs it once per book after the boundary fold, and ``compute`` returns its findings as diagnostics.
The world sells one point-in-time kit for 1,000.00 in US01 (ASC606) and delivers it in January
2026. No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from erev_engine import ENGINE_VERSION, compute
from erev_engine.bundle import (
    BookInput,
    EntityInput,
    EventInput,
    InputBundle,
    OutputBundle,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.trace import reevaluate
from support import bundles

CONTRACT = "K-LATE"
ENTITY = bundles.ENTITY_CODE
INCEPTION = date(2026, 1, 1)
KNOWN_AT = datetime(2026, 2, 10, 23, tzinfo=UTC)
ZERO_SHA = "0" * 64
KEYS = ("POB-01", "POB-02")


def _template() -> TemplateInput:
    return TemplateInput(
        template_code="TPL-PIT",
        version_key="TPL-PIT@v1",
        version_no=1,
        content_sha256=ZERO_SHA,
        obligation_kind="STANDARD",
        distinctness="distinct",
        series_increment_unit=None,
        satisfaction_pattern="POINT_IN_TIME",
        over_time_criterion="NOT_APPLICABLE",
        recognition_method="POINT_IN_TIME",
        ratable_convention=None,
        start_date_rule="LINE_START",
        end_date_rule="LINE_END",
        term_months=None,
        principal_agent="PRINCIPAL",
        warranty_type="NONE",
        licence_nature="NOT_APPLICABLE",
        sfc_assessment_required=False,
        revenue_category=None,
        disaggregation={},
        account_role_overrides={},
        stratification_label=None,
        is_excluded_from_netting_attribution=False,
        policy_values={},
        effective_from=date(2020, 1, 1),
        effective_to=None,
    )


def _entry(product: str) -> SspEntryInput:
    return SspEntryInput(
        entry_key=f"SSP-US@v1/{product}//-/USD",
        product_code=product,
        stratification="",
        region=None,
        channel=None,
        segment=None,
        deal_size_band=None,
        term_band=None,
        currency="USD",
        method="observable",
        value_basis="AMOUNT",
        unit_list_price=None,
        midpoint_discount_ratio=None,
        range_ratio=None,
        cost_basis=None,
        margin_ratio=None,
        distinctness="distinct",
        revenue_account_code=None,
        observable_point=None,
        ranges=(SspRangeInput("NONE", None, None, Decimal("1000.00"), None, None, None),),
    )


def _ssp() -> SspVersionInput:
    return SspVersionInput(
        ssp_book_code="SSP-US",
        version_key="SSP-US@v1",
        version_no=1,
        resolution_mode="EFFECTIVE_DATE",
        legacy_version_label=None,
        effective_from_date=date(2020, 1, 1),
        effective_to_date=None,
        status="APPROVED",
        approved_at=datetime(2020, 1, 1, tzinfo=UTC),
        content_sha256=ZERO_SHA,
        scope_entity_code=None,
        scope_currency=None,
        scope_channel=None,
        scope_segment=None,
        entries=tuple(_entry(f"KIT-{key}") for key in KEYS),
    )


def _event(
    stream: int, kind: str, on: date, payload: Mapping[str, object], keys: Sequence[str] = ()
) -> EventInput:
    return bundles.event(CONTRACT, stream, kind, on, payload, obligation_keys=list(keys))


def _delivery(stream: int, key: str, on: date) -> EventInput:
    payload = {"obligation_key": key, "quantity": Decimal("1"), "trigger": "CONTROL_TRANSFER"}
    return _event(stream, "DELIVERY_RECORDED", on, payload, [key])


def _world(
    deliveries: Sequence[EventInput],
    *,
    states: Mapping[str, str],
    previous_heads: int = 0,
) -> InputBundle:
    calendar: EntityInput = bundles.entity(months=12, states=states)
    header = bundles.contract(CONTRACT, inception=INCEPTION)
    booking = [
        bundles.booking_line(
            key, product_code=f"KIT-{key}", quantity="1", total_price="1000.00", end=INCEPTION
        )
        for key in KEYS
    ]
    events = [
        _event(1, "CONTRACT_BOOKED", INCEPTION, {"lines": booking}, KEYS),
        _event(2, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}}),
        *deliveries,
    ]
    products = tuple(
        bundles.product(f"KIT-{key}", template_code="TPL-PIT", family=None) for key in KEYS
    )
    group = dataclasses.replace(
        bundles.group((header,), group_key=f"CG-{CONTRACT}", products=products),
        previous_stream_heads=((CONTRACT, previous_heads),) if previous_heads else (),
    )
    book = BookInput(
        "ASC606",
        True,
        (ENTITY,),
        bundles.policy_set(book_code="ASC606", entity=calendar),
        bundles.account_mapping(),
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=KNOWN_AT,
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(book,),
        entities=(calendar,),
        group=group,
        contracts=(header,),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(_ssp(),),
        pob_template_versions=(_template(),),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def _late(
    output: OutputBundle,
) -> list[tuple[str, str | None, str | None, str | None, dict[str, str]]]:
    return [
        (d.severity, d.book_code, d.subject_key, d.event_key, dict(d.detail))
        for d in output.diagnostics
        if d.code == "LATE_EVENT"
    ]


def test_late_event_in_closed_period_is_published() -> None:
    # Booked and activated before the January close; both deliveries are recorded afterwards.
    deliveries = [
        _delivery(3, "POB-01", date(2026, 1, 20)),
        _delivery(4, "POB-02", date(2026, 1, 20)),
    ]
    output = compute(_world(deliveries, states={"FY2026-P01": "closed"}, previous_heads=2))
    detail = {
        "origin_period_key": "FY2026-P01",
        "posting_period_key": "FY2026-P02",
        "reason": "CLOSED_PERIOD",
        "rule": "S08-R-10",
    }
    assert _late(output) == [
        ("WARNING", "ASC606", f"{CONTRACT}/POB-01", f"{CONTRACT}/EV-000003",
         {"event_key": f"{CONTRACT}/EV-000003", **detail}),
        ("WARNING", "ASC606", f"{CONTRACT}/POB-02", f"{CONTRACT}/EV-000004",
         {"event_key": f"{CONTRACT}/EV-000004", **detail}),
    ]  # fmt: skip
    (book,) = output.books
    node = next(
        n for n in book.trace.nodes if n.id == f"late_assign@{CONTRACT}/EV-000003:{CONTRACT}:-"
    )
    assert (node.value, node.formula_id) == ("1", "late.assign.v1")
    assert node.params["states"] == "closed|open"
    values = reevaluate(book.trace)
    assert all(values[n.id] == n.value for n in book.trace.nodes if n.measure.startswith("late_"))


def test_events_of_the_previous_computation_raise_nothing() -> None:
    deliveries = [
        _delivery(3, "POB-01", date(2026, 1, 20)),
        _delivery(4, "POB-02", date(2026, 1, 20)),
    ]
    output = compute(_world(deliveries, states={"FY2026-P01": "closed"}, previous_heads=4))
    assert _late(output) == []


def test_out_of_order_arrival_is_published() -> None:
    # All periods open; POB-02's delivery is recorded after POB-01's, effective earlier (DEV-024).
    deliveries = [
        _delivery(3, "POB-01", date(2026, 1, 25)),
        _delivery(4, "POB-02", date(2026, 1, 20)),
    ]
    output = compute(_world(deliveries, states={}))
    assert _late(output) == [
        ("WARNING", "ASC606", f"{CONTRACT}/POB-02", f"{CONTRACT}/EV-000004",
         {"event_key": f"{CONTRACT}/EV-000004", "origin_period_key": "-",
          "posting_period_key": "FY2026-P01", "reason": "OUT_OF_ORDER", "rule": "S08-R-10"}),
    ]  # fmt: skip
