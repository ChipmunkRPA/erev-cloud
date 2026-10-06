"""Inception fold over stages 01 to 05 (ENGINE_SPEC §0.3 CV-10; §2.6 EX-02-B; POLICIES CHK-002;
BUILD_SPEC ENA-13).

``support.fold.fold_inception`` runs the stages for real. No database fixture (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    EventInput,
    InputBundle,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.money import to_fraction
from erev_engine.trace import Trace, TraceBuilder, reevaluate
from support import bundles, golden_streams
from support.fold import fold_inception

ZERO = "0" * 64
BOOK = "SSP-MAIN"
LICENCE_ON, SERVICES_ON = date(2026, 1, 10), date(2026, 1, 20)
# CHK-002 posted allocations of the golden setup contracts, obligations in subject-key order.
GOLDEN = (
    ("Contract 1", "02", [32_210, 23_707, 9_663, 64_420]),
    ("Contract 2", "02", [47_077, 31_385, 11_538, 0]),
    ("Contract 3", "03", [32_210, 23_707, 9_663, 64_420]),
    ("Contract 4", "03", [44_518, 39_571, 10_911, 0]),
)


def template(code: str) -> TemplateInput:
    return TemplateInput(
        template_code=code,
        version_key=f"{code}@v1",
        version_no=1,
        content_sha256=ZERO,
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
        effective_from=date(2025, 1, 1),
        effective_to=None,
    )


def point_entry(product: str, point: str) -> SspEntryInput:
    return SspEntryInput(
        entry_key=f"{BOOK}@v1/{product}//-/USD",
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
        ranges=(SspRangeInput("NONE", None, None, Decimal(point), None, None, None),),
    )


def booking(contract: str, on: date, product: str, price: str, end: date) -> EventInput:
    line = bundles.booking_line(
        "POB-01", product_code=product, quantity="1", total_price=price, start=on, end=end
    )
    return bundles.event(
        contract, 1, "CONTRACT_BOOKED", on, {"lines": [line]}, obligation_keys=["POB-01"]
    )


def ex_02_b() -> InputBundle:
    """C-1 (licence at 90,000.00, SSP 100,000) and C-2 (services at 60,000.00, SSP 50,000),
    negotiated as a package and combined under 25-9(a) (EX-02-B)."""
    calendar = bundles.entity(start=date(2026, 1, 1), months=24)
    contracts = (
        bundles.contract("C-1", inception=LICENCE_ON),
        bundles.contract("C-2", inception=SERVICES_ON),
    )
    events = [
        booking("C-1", LICENCE_ON, "LICENCE", "90000.00", date(2026, 12, 31)),
        booking("C-2", SERVICES_ON, "SERVICES", "60000.00", date(2026, 3, 31)),
        bundles.event("C-1", 2, "CONTRACT_ACTIVATED", SERVICES_ON, {"checklist": {}}),
        bundles.event("C-2", 2, "CONTRACT_ACTIVATED", SERVICES_ON, {"checklist": {}}),
    ]
    products = [
        bundles.product(code, template_code="TPL-PIT", family=None)
        for code in ("LICENCE", "SERVICES")
    ]
    group = dataclasses.replace(bundles.group(contracts, products=products), criterion="25_9_A")
    ssp = SspVersionInput(
        ssp_book_code=BOOK,
        version_key=f"{BOOK}@v1",
        version_no=1,
        resolution_mode="EFFECTIVE_DATE",
        legacy_version_label=None,
        effective_from_date=date(2025, 1, 1),
        effective_to_date=None,
        status="APPROVED",
        approved_at=datetime(2025, 12, 1, tzinfo=UTC),
        content_sha256=ZERO,
        scope_entity_code=None,
        scope_currency=None,
        scope_channel=None,
        scope_segment=None,
        entries=(point_entry("LICENCE", "100000"), point_entry("SERVICES", "50000")),
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2026, 2, 1, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(bundles.book(entity=calendar),),
        entities=(calendar,),
        group=group,
        contracts=contracts,
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(ssp,),
        pob_template_versions=(template("TPL-PIT"),),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def assert_reevaluates(trace: Trace) -> None:
    """DG-KRN-EXP-04 over the registered formulas: posted nodes reproduce exactly; an exact node
    re-evaluated from inputs encoded at 18 places reproduces within 1e-12 (L2-2-Q-40)."""
    recomputed = reevaluate(trace)
    for node in trace.nodes:
        if node.rounding_residue is None:
            gap = abs(to_fraction(recomputed[node.id]) - to_fraction(node.value))
            assert gap <= Fraction(1, 10**12), (node.id, node.value, recomputed[node.id])
        else:
            assert recomputed[node.id] == node.value, (node.id, node.value, recomputed[node.id])


def test_ex_02_b_combined_allocation() -> None:
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    allocated = fold_inception(ex_02_b(), "ASC606", tb)
    assert allocated.findings == ()
    assert [view.header.external_id for view in allocated.contracts] == ["C-1", "C-2"]
    assert allocated.inception_date == LICENCE_ON
    (tp,) = allocated.tp_history
    assert (tp.total.posted, tp.allocation_basis.posted) == (15_000_000, 15_000_000)
    allocations = {ob.subject_key: ob.original_allocation for ob in allocated.obligations}
    assert {key: quota.a_posted for key, quota in allocations.items()} == {
        "C-1/POB-01": 10_000_000,
        "C-2/POB-01": 5_000_000,
    }
    assert {key: quota.x_exact for key, quota in allocations.items()} == {
        "C-1/POB-01": 100_000,
        "C-2/POB-01": 50_000,
    }
    assert {ob.original_total_contract_price for ob in allocated.obligations} == {150_000}
    trace = tb.build(root_measures={})
    assert {node.id for node in trace.nodes} >= {
        "tp_allocation_basis:CG-1:-",
        "original_allocated_amount:C-1/POB-01:-",
        "original_allocated_amount:C-2/POB-01:-",
    }
    assert_reevaluates(trace)


def test_fold_golden_setup_contracts() -> None:
    for contract, step, expected in GOLDEN:
        tb = TraceBuilder(engine_version=ENGINE_VERSION)
        value = golden_streams.stream(contract, step).input_bundle(preset="LEGACY_PARITY")
        allocated = fold_inception(value, "ASC606", tb)
        assert allocated.findings == (), contract
        posted = [ob.original_allocation.a_posted for ob in allocated.obligations]
        assert posted == expected, contract
        assert sum(posted) == allocated.tp_history[0].allocation_basis.posted
        assert_reevaluates(tb.build(root_measures={}))
