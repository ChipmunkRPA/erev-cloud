"""Stage 05 posted allocations (legacy 01 §7.3 TC-setup-08, TC-setup-09; BUILD_SPEC ENA-11).

Golden Contracts 1, 2 and 4 replay under the parity preset; the equal-thirds case is a native
bundle. Stages 01 to 05 run for real. No database fixture (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    InputBundle,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.enums import BookCode
from erev_engine.stages import (
    s01_canonicalize,
    s02_contract_identification,
    s03_pob_builder,
    s04_transaction_price,
    s05_allocation,
)
from erev_engine.stages.state import AllocatedState, BookContext, PolicyResolver
from erev_engine.trace import TraceBuilder
from support import bundles, golden_streams

INCEPTION = date(2026, 1, 1)
ZERO = "0" * 64


def context(value: InputBundle) -> BookContext:
    book = value.books[0]
    return BookContext(
        book_code=BookCode(book.book_code),
        framework=BookCode(book.book_code),
        currencies=value.currencies,
        txn_currency=value.group.transaction_currency,
        entities={entity.code: entity for entity in value.entities},
        horizon={entity.code: entity.periods[-1].period_key for entity in value.entities},
        policies=PolicyResolver(book.policies),
        mapping=book.account_mapping,
        trigger=value.trigger,
        tenant_preset=value.tenant_preset,
    )


def allocate(value: InputBundle) -> AllocatedState:
    ctx = context(value)
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    identified = s02_contract_identification.run(
        ctx, cb, TraceBuilder(engine_version=ENGINE_VERSION)
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    priced = s04_transaction_price.run(ctx, s03_pob_builder.run(ctx, identified, tb), tb)
    return s05_allocation.run(ctx, priced, tb)


def test_tc_setup_08_posted_allocations_sum() -> None:
    expected = {
        ("Contract 1", "02"): ([32_210, 23_707, 9_663, 64_420], 130_000),
        ("Contract 2", "02"): ([47_077, 31_385, 11_538, 0], 90_000),
        ("Contract 4", "03"): ([44_518, 39_571, 10_911, 0], 95_000),
    }
    for (contract, step), (amounts, total) in expected.items():
        value = golden_streams.stream(contract, step).input_bundle(preset="LEGACY_PARITY")
        allocated = allocate(value)
        assert allocated.findings == ()
        posted = [ob.original_allocation.a_posted for ob in allocated.obligations]
        assert posted == amounts, contract
        assert sum(posted) == total, contract


def template() -> TemplateInput:
    return TemplateInput(
        template_code="TPL-PIT",
        version_key="TPL-PIT@v1",
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


def point(product: str, value: str) -> SspEntryInput:
    return SspEntryInput(
        entry_key=f"BOOK-A@v1/{product}//-/USD",
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
        ranges=(SspRangeInput("NONE", None, None, Decimal(value), None, None, None),),
    )


def test_tc_setup_09_equal_ssp_thirds() -> None:
    calendar = bundles.entity(start=INCEPTION, months=12)
    header = bundles.contract("K-01", inception=INCEPTION)
    rows = (
        ("POB-001", "SKU-A", "40.00"),
        ("POB-002", "SKU-B", "30.00"),
        ("POB-003", "SKU-C", "30.00"),
    )
    lines = [
        bundles.booking_line(key, product_code=product, total_price=price, start=INCEPTION)
        for key, product, price in rows
    ]
    booked = bundles.event(
        "K-01",
        1,
        "CONTRACT_BOOKED",
        INCEPTION,
        {"lines": lines},
        obligation_keys=[key for key, _, _ in rows],
    )
    book = SspVersionInput(
        ssp_book_code="BOOK-A",
        version_key="BOOK-A@v1",
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
        entries=(point("SKU-A", "50"), point("SKU-B", "50"), point("SKU-C", "50")),
    )
    products = tuple(
        bundles.product(code, template_code="TPL-PIT", family=None)
        for code in ("SKU-A", "SKU-B", "SKU-C")
    )
    value = dataclasses.replace(
        bundles.minimal_contract(),
        known_at=datetime(2026, 1, 31, 23, tzinfo=UTC),
        books=(bundles.book(entity=calendar),),
        entities=(calendar,),
        group=bundles.group((header,), products=products),
        contracts=(header,),
        events=(booked,),
        ssp_versions=(book,),
        pob_template_versions=(template(),),
    )
    allocated = allocate(value)
    assert allocated.findings == ()
    assert [ob.original_allocation.a_posted for ob in allocated.obligations] == [
        3_334,
        3_333,
        3_333,
    ]
