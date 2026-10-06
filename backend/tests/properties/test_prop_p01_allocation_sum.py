"""PROP:P1: posted allocations sum to the allocation basis (dev-guide §9.7 P1; ENGINE_SPEC §5.5
S05-INV-01, S05-R-10, S05-R-14; DG-ENG-05; BUILD_SPEC ENA-13 stage 05 part, END-9 ``compute``
part)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION, compute
from erev_engine.bundle import (
    BookInput,
    InputBundle,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.enums import BookCode
from erev_engine.money import format_money
from erev_engine.stages import s05_allocation
from erev_engine.stages.state import BookContext, PolicyResolver, Quota1, TpBuildUp, VcElementView
from hypothesis import given
from hypothesis import strategies as st
from support import bundles
from support.strategies import AllocationCase, allocation_cases, transaction_totals

pytestmark = pytest.mark.property

GROUP = "CG-P1"
COMPUTE_CURRENCIES = ("BHD", "CLF", "JPY", "USD")  # minor units 3, 4, 0, 2 (DG-PROP-03)
ZERO_SHA = "0" * 64
PIT = TemplateInput(
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
ZERO = Quota1(Fraction(0), 0)
# (K in minor units, positions of the targets) per targeted VC element.
Targeted = tuple[tuple[int, tuple[int, ...]], ...]


@st.composite
def targeted_groups(draw: st.DrawFn) -> tuple[AllocationCase, Targeted]:
    """A group (1 to 200 obligations; JPY, USD, BHD, CLF; SSP weights with zeros; positive and
    negative prices) with 0 to 3 targeted VC elements, each on a subset holding a positive SSP."""
    case = draw(allocation_cases())
    positive = [index for index, weight in enumerate(case.weights) if weight > 0]
    count = len(case.weights)
    elements: list[tuple[int, tuple[int, ...]]] = []
    for _ in range(draw(st.integers(0, 3))):
        anchor = draw(st.sampled_from(positive))
        others = draw(st.lists(st.integers(0, count - 1), max_size=8, unique=True))
        elements.append((draw(transaction_totals()), tuple(sorted({anchor, *others}))))
    return case, tuple(elements)


def context(currency: str) -> BookContext:
    book = bundles.book()
    return BookContext(
        book_code=BookCode.ASC606,
        framework=BookCode.ASC606,
        currencies=bundles.currencies(currency),
        txn_currency=currency,
        entities={},
        horizon={},
        policies=PolicyResolver(book.policies),
        mapping=book.account_mapping,
        trigger="COMMAND",
        tenant_preset="DEFAULT",
    )


def buildup(case: AllocationCase, elements: Targeted) -> TpBuildUp:
    """A build-up whose allocation basis is the generated price, targeted elements included."""
    scale: int = 10**case.minor_unit
    views = tuple(
        VcElementView(
            estimate_key=f"K-P1/VC-{number}",
            element_code=f"VC-{number}",
            version_key=f"K-P1/VC-{number}@v1",
            amount=Quota1(Fraction(amount, scale), amount),
            allocation_target="OBLIGATIONS",
            obligation_keys=tuple(case.keys[index] for index in members),
        )
        for number, (amount, members) in enumerate(elements)
    )
    basis = Quota1(Fraction(case.total_minor, scale), case.total_minor)
    return TpBuildUp(
        at=date(2026, 1, 1),
        before_event_key=None,
        fixed=basis,
        vc_constrained=ZERO,
        vc_excluded=ZERO,
        expected_returns=ZERO,
        consideration_payable=ZERO,
        financing_adjustment=ZERO,
        noncash=ZERO,
        sales_tax_excluded=ZERO,
        out_of_scope=ZERO,
        total=basis,
        allocation_basis=basis,
        elements=views,
    )


@given(group=targeted_groups())
def test_p01_stage05_allocation_sum(group: tuple[AllocationCase, Targeted]) -> None:
    case, elements = group
    tp = buildup(case, elements)
    targets = {view.estimate_key: view.obligation_keys for view in tp.elements}
    quotas = s05_allocation.allocate(
        context(case.currency), tp, case.weights, case.keys, group_key=GROUP, targets=targets
    )
    assert len(quotas) == len(case.keys)
    assert sum(quota.a_posted for quota in quotas) == tp.allocation_basis.posted
    scale: int = 10**case.minor_unit
    assert sum((quota.x_exact for quota in quotas), Fraction(0)) * scale == case.total_minor
    # CV-34 holds per pool: the remainder and each targeted element.
    for quota in quotas:
        assert abs(quota.x_exact * scale - quota.a_posted) < 1 + len(elements)


# --- compute part (END-9) ------------------------------------------------------------------------


@st.composite
def computed_groups(draw: st.DrawFn) -> InputBundle:
    """One contract of 1 to 6 point-in-time obligations in BHD, CLF, JPY or USD, with positive line
    prices and positive SSP points drawn in minor units, booked and activated."""
    currency = draw(st.sampled_from(COMPUTE_CURRENCIES))
    minor_unit = bundles.currencies(currency)[currency].minor_unit
    count = draw(st.integers(1, 6))
    prices = draw(st.lists(st.integers(1, 10**7), min_size=count, max_size=count))
    points = draw(st.lists(st.integers(1, 10**6), min_size=count, max_size=count))
    keys = [f"POB-{number:02d}" for number in range(1, count + 1)]
    inception = date(2026, 1, 1)
    calendar = bundles.entity(functional_currency=currency, months=12)
    header = bundles.contract("K-P1", currency=currency, inception=inception)
    lines = [
        bundles.booking_line(
            key,
            product_code=f"SKU-{key}",
            quantity="1",
            total_price=format_money(price, minor_unit),
            end=inception,
        )
        for key, price in zip(keys, prices, strict=True)
    ]
    entries = tuple(
        SspEntryInput(
            entry_key=f"SSP-P1@v1/SKU-{key}//-/{currency}",
            product_code=f"SKU-{key}",
            stratification="",
            region=None,
            channel=None,
            segment=None,
            deal_size_band=None,
            term_band=None,
            currency=currency,
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
            ranges=(
                SspRangeInput(
                    "NONE", None, None, Decimal(format_money(point, minor_unit)), None, None, None
                ),
            ),
        )
        for key, point in zip(keys, points, strict=True)
    )
    version = SspVersionInput(
        ssp_book_code="SSP-P1",
        version_key="SSP-P1@v1",
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
        entries=entries,
    )
    events = (
        bundles.event(
            "K-P1", 1, "CONTRACT_BOOKED", inception, {"lines": lines}, obligation_keys=keys
        ),
        bundles.event("K-P1", 2, "CONTRACT_ACTIVATED", inception, {"checklist": {}}),
    )
    book = BookInput(
        "ASC606",
        True,
        (calendar.code,),
        bundles.policy_set(entity=calendar),
        bundles.account_mapping(),
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2026, 12, 31, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies(currency),
        books=(book,),
        entities=(calendar,),
        group=bundles.group(
            (header,),
            group_key=GROUP,
            products=tuple(
                bundles.product(f"SKU-{key}", template_code="TPL-PIT", family=None) for key in keys
            ),
        ),
        contracts=(header,),
        events=events,
        ssp_versions=(version,),
        pob_template_versions=(PIT,),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


@given(bundle=computed_groups())
def test_p01_compute_level(bundle: InputBundle) -> None:
    output = compute(bundle)
    currency = bundle.group.transaction_currency
    scale: int = 10 ** bundle.currencies[currency].minor_unit
    for book in output.books:
        version = book.contract_version
        assert version is not None
        allocated = [item.columns["allocated_amount"] for item in book.obligation_versions]
        assert all(isinstance(amount, int) for amount in allocated)
        total = sum(amount for amount in allocated if isinstance(amount, int))
        # Σ a_posted = allocation basis per group and book (S04-R-02; the basis node of §4.4).
        node = next(
            item for item in book.trace.nodes if item.id == f"tp_allocation_basis:{GROUP}:-"
        )
        basis = Fraction(Decimal(node.value)) * scale
        returns = version.columns["expected_returns_amount"]
        assert isinstance(returns, int) and basis.denominator == 1
        assert total - returns == basis.numerator
        # Σ allocated_amount = transaction_price − consideration_payable_amount (DB-17 V1).
        price = version.columns["transaction_price"]
        payable = version.columns["consideration_payable_amount"]
        assert isinstance(price, int) and isinstance(payable, int)
        assert total == price - payable
