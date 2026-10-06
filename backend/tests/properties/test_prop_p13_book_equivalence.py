"""PROP:P13: books whose resolved policy subsets hash identically produce identical allocation
outputs (dev-guide §9.7 P13; ENGINE_SPEC_B S13-INV-01, S13-R-04; BUILD_SPEC END-7).

Two framework books of one group run stages 02 to 08 through ``s13_books.run_books``. The IFRS15
book differs from the ASC606 book in 0 to 3 keys of stage 11 and, when drawn, in the level of one
stage 05 value. Equal stage keys mean identical allocations and aliased nodes; a changed stage 05
key recomputes stages 05 to 08, which reproduce the same allocations.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    BookInput,
    InputBundle,
    ResolvedPolicyInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.stages import STAGES, s01_canonicalize
from erev_engine.stages.s13_books import book_context, memo, run_books
from erev_engine.stages.state import AllocatedState
from erev_engine.trace import TraceBuilder
from hypothesis import given
from hypothesis import strategies as st
from support import bundles

pytestmark = pytest.mark.property

CONTRACT = "K-P13"
FOLD = tuple(spec for spec in STAGES if spec.stage <= "08")
ZERO_SHA = "0" * 64
# Stage 11 keys and IFRS15 literals (POLICIES §6.2 rows 10 and 11).
LATER = (
    ("costs.impairment_reversal", "REQUIRED_CAPPED"),
    ("loss.cost_basis", "IAS37_68A_COSTS"),
    ("loss.scope", "ALL_CONTRACTS_WITH_EAC"),
)
TEMPLATE = TemplateInput(
    template_code="TPL-RATABLE",
    version_key="TPL-RATABLE@v1",
    version_no=1,
    content_sha256=ZERO_SHA,
    obligation_kind="STANDARD",
    distinctness="distinct",
    series_increment_unit=None,
    satisfaction_pattern="OVER_TIME",
    over_time_criterion="OT_A",
    recognition_method="TIME_ELAPSED",
    ratable_convention="DAILY",
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

World = tuple[tuple[int, ...], tuple[int, ...], tuple[tuple[str, str], ...], bool]


@st.composite
def worlds(draw: st.DrawFn) -> World:
    count = draw(st.integers(1, 4))
    prices = draw(st.lists(st.integers(1, 10**9), min_size=count, max_size=count))
    points = draw(st.lists(st.integers(1, 10**9), min_size=count, max_size=count))
    later = draw(st.lists(st.sampled_from(LATER), unique=True, max_size=len(LATER)))
    return tuple(prices), tuple(points), tuple(later), draw(st.booleans())


def money(minor: int) -> Decimal:
    return Decimal(minor).scaleb(-2)


def entry(product: str, point: int) -> SspEntryInput:
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
        ranges=(SspRangeInput("NONE", None, None, money(point), None, None, None),),
    )


def bundle(world: World) -> InputBundle:
    prices, points, later, diverge = world
    calendar = bundles.entity(months=12, books=("ASC606", "IFRS15"))
    us = bundles.book("ASC606", entity=calendar)
    changes = dict(later)
    policies: list[ResolvedPolicyInput] = [
        dataclasses.replace(policy, value=changes[policy.code])
        if policy.code in changes
        else policy
        for policy in us.policies
    ]
    if diverge:  # the same value at another level: a different stage 05 key (S13-R-04)
        index = next(
            number
            for number, policy in enumerate(policies)
            if policy.code in memo.STAGE_POLICY_KEYS["05"] and policy.scope == "GROUP"
        )
        policies[index] = dataclasses.replace(policies[index], level="T")
    ifrs = BookInput("IFRS15", False, us.entity_codes, tuple(policies), us.account_mapping)
    products = [f"SKU-{number}" for number in range(1, len(prices) + 1)]
    lines = [
        bundles.booking_line(
            f"POB-{number:02d}",
            product_code=product,
            quantity="1",
            total_price=str(money(price)),
            end=date(2026, 12, 31),
        )
        for number, (product, price) in enumerate(zip(products, prices, strict=True), start=1)
    ]
    header = bundles.contract(CONTRACT)
    booked = bundles.event(
        CONTRACT,
        1,
        "CONTRACT_BOOKED",
        bundles.INCEPTION,
        {"lines": lines},
        obligation_keys=[str(line["obligation_key"]) for line in lines],
    )
    activated = bundles.event(
        CONTRACT, 2, "CONTRACT_ACTIVATED", bundles.INCEPTION, {"checklist": {}}
    )
    version = SspVersionInput(
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
        entries=tuple(
            entry(product, point) for product, point in zip(products, points, strict=True)
        ),
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2027, 1, 1, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(us, ifrs),
        entities=(calendar,),
        group=bundles.group(
            (header,),
            products=[
                bundles.product(code, template_code="TPL-RATABLE", family=None) for code in products
            ],
        ),
        contracts=(header,),
        events=(booked, activated),
        ssp_versions=(version,),
        pob_template_versions=(TEMPLATE,),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


@given(worlds())
def test_p13_equal_policy_hashes_equal_allocations(world: World) -> None:
    cb = s01_canonicalize.run(bundle(world), TraceBuilder(engine_version=ENGINE_VERSION))
    us, ifrs = run_books(cb, FOLD)
    us_keys = memo.chain(cb, book_context(cb, cb.books["ASC606"]), FOLD)
    ifrs_keys = memo.chain(cb, book_context(cb, cb.books["IFRS15"]), FOLD)
    diverge = world[3]
    # Stage 11 keys never enter the keys of stages 02 to 08; the stage 05 level does.
    assert (us_keys == ifrs_keys) == (not diverge)
    assert isinstance(us.state, AllocatedState) and isinstance(ifrs.state, AllocatedState)
    assert us.state.obligations == ifrs.state.obligations
    assert us.state.tp_history == ifrs.state.tp_history
    values = {node.id: node.value for node in us.trace.nodes}
    assert {node.id: node.value for node in ifrs.trace.nodes} == values
    aliased = [node for node in ifrs.trace.nodes if "alias_of_book" in node.params]
    if us_keys == ifrs_keys:
        assert len(aliased) == len(ifrs.trace.nodes)  # S13-INV-01: every node aliased
    else:
        assert len(aliased) < len(ifrs.trace.nodes)  # stages 05 to 08 recomputed
