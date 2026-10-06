"""Stage 04 transaction price build-up (ENGINE_SPEC §4.2 to §4.5; EX-04-A; BUILD_SPEC ENA-6).

Bundles come from ``support.bundles`` and ``support.golden_streams``; stages 01 to 03 run for real.
No database fixture (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION, money
from erev_engine.bundle import (
    EstimateVersionInput,
    EventInput,
    InputBundle,
    JudgementInput,
    ProductInput,
    TemplateInput,
)
from erev_engine.dates import month_end
from erev_engine.enums import BookCode
from erev_engine.errors import EngineError
from erev_engine.stages import (
    s01_canonicalize,
    s02_contract_identification,
    s03_pob_builder,
    s04_transaction_price,
)
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from erev_engine.stages.s04_transaction_price import PricedState, vc
from erev_engine.stages.state import BookContext, EventView, PolicyResolver, Quota1
from erev_engine.trace import TraceBuilder, TraceNode, reevaluate
from support import bundles, golden_streams

CONTRACT = "K-01"
INCEPTION = date(2026, 1, 1)
END = date(2026, 12, 31)
ZERO = "0" * 64


def template(code: str, *, method: str, pattern: str) -> TemplateInput:
    return TemplateInput(
        template_code=code,
        version_key=f"{code}@v1",
        version_no=1,
        content_sha256=ZERO,
        obligation_kind="STANDARD",
        distinctness="distinct",
        series_increment_unit=None,
        satisfaction_pattern=pattern,
        over_time_criterion="OT_A" if pattern == "OVER_TIME" else "NOT_APPLICABLE",
        recognition_method=method,
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


TEMPLATES = (
    template("TPL-PIT", method="POINT_IN_TIME", pattern="POINT_IN_TIME"),
    template("TPL-USAGE", method="USAGE", pattern="OVER_TIME"),
)


def product(code: str, template_code: str) -> ProductInput:
    return bundles.product(code, template_code=template_code, family=None)


def version(
    element: str,
    *,
    method: str,
    vc_type: str | None,
    scenarios: Sequence[tuple[str, str]] = (),
    unconstrained: str | None = None,
    conservative: str | None = None,
    constrained: str | None = None,
    direction: str | None = None,
) -> EstimateVersionInput:
    key = obligation_subject_key(CONTRACT, element)
    return EstimateVersionInput(
        estimate_key=key,
        estimate_kind="VARIABLE_CONSIDERATION",
        element_code=element,
        method=method,
        vc_element_type=vc_type,
        direction=direction,
        allocation_target="CONTRACT",
        target_obligation_keys=(),
        obligation_key=None,
        version_key=f"{key}@v1",
        version_no=1,
        status="APPROVED",
        effective_date=INCEPTION,
        scenarios=tuple(
            {"amount": Decimal(amount), "probability": Decimal(probability)}
            for amount, probability in scenarios
        ),
        parameters={},
        unconstrained_amount=None if unconstrained is None else Decimal(unconstrained),
        most_conservative_amount=None if conservative is None else Decimal(conservative),
        constrained_amount=None if constrained is None else Decimal(constrained),
        rate=None,
        expected_total_amount=None,
        expected_quantity=None,
        amortization_months=None,
        currency="USD",
        supersedes_version_key=None,
        judgement_key=None,
        content_sha256=ZERO,
    )


def changed(stream: int, applied: EstimateVersionInput) -> EventInput:
    payload = {"estimate_version_id": applied.version_key}
    return bundles.event(CONTRACT, stream, "ESTIMATE_CHANGED", INCEPTION, payload)


def booking(price: str = "2500000.00", product_code: str = "SKU-1") -> EventInput:
    line = bundles.booking_line(
        "POB-01", product_code=product_code, quantity="1", total_price=price, end=END
    )
    return bundles.event(
        CONTRACT, 1, "CONTRACT_BOOKED", INCEPTION, {"lines": [line]}, obligation_keys=["POB-01"]
    )


def bundle(
    *events: EventInput,
    versions: Iterable[EstimateVersionInput] = (),
    products: Sequence[ProductInput] = (product("SKU-1", "TPL-PIT"),),
    overrides: Mapping[str, str] | None = None,
    judgements: Sequence[JudgementInput] = (),
) -> InputBundle:
    calendar = bundles.entity(start=INCEPTION, months=24)
    base = bundles.book("ASC606", entity=calendar)
    policies = tuple(
        dataclasses.replace(policy, value=(overrides or {})[policy.code])
        if policy.code in (overrides or {}) and policy.scope == "GROUP"
        else policy
        for policy in base.policies
    )
    header = dataclasses.replace(
        bundles.contract(CONTRACT, inception=INCEPTION), judgements=tuple(judgements)
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2026, 12, 31, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(dataclasses.replace(base, policies=policies),),
        entities=(calendar,),
        group=bundles.group((header,), products=products),
        contracts=(header,),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(),
        pob_template_versions=TEMPLATES,
        rule_set_versions=(),
        estimate_versions=tuple(sorted(versions, key=lambda v: (v.estimate_key, v.version_no))),
        fx_rates=(),
        posted=(),
    )


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


def fold(value: InputBundle) -> tuple[BookContext, PricedState, dict[str, TraceNode]]:
    """Stages 01 to 04 with one trace builder for stages 03 and 04 (§0.3)."""
    ctx = context(value)
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    identified = s02_contract_identification.run(
        ctx, cb, TraceBuilder(engine_version=ENGINE_VERSION)
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    pob = s03_pob_builder.run(ctx, identified, tb)
    priced = s04_transaction_price.run(ctx, pob, tb)
    return ctx, priced, {node.id: node for node in tb.build(root_measures={}).nodes}


def event_of(priced: PricedState, key: str) -> EventView:
    return next(e for e in priced.pob.identified.canonical.events if e.event_key == key)


INCENTIVE = version(
    "VC-INCENTIVE",
    method="EXPECTED_VALUE",
    vc_type="PERFORMANCE_INCENTIVE",
    scenarios=(("100000.00", "0.2"), ("0.00", "0.5"), ("-50000.00", "0.3")),
    unconstrained="5000.00",
    constrained="5000.00",
)
BONUS = version(
    "VC-BONUS",
    method="MOST_LIKELY_AMOUNT",
    vc_type="BONUS",
    scenarios=(("150000.00", "0.7"), ("0.00", "0.3")),
    unconstrained="150000.00",
    conservative="0.00",
    constrained="0.00",
)


def ex_04_a() -> InputBundle:
    return bundle(booking(), changed(2, INCENTIVE), changed(3, BONUS), versions=(INCENTIVE, BONUS))


def test_ex_04_a_expected_value_and_most_likely() -> None:
    _, priced, traced = fold(ex_04_a())
    tp = priced.tp
    assert priced.findings == ()
    assert (tp.fixed.posted, tp.vc_constrained.posted, tp.vc_excluded.posted) == (
        250_000_000,
        500_000,
        15_000_000,
    )
    assert tp.total == tp.allocation_basis == Quota1(Fraction(2_505_000), 250_500_000)
    assert [(e.estimate_key, e.version_key, e.amount.posted) for e in tp.elements] == [
        ("K-01/VC-BONUS", "K-01/VC-BONUS@v1", 0),
        ("K-01/VC-INCENTIVE", "K-01/VC-INCENTIVE@v1", 500_000),
    ]
    incentive = traced["vc_unconstrained:K-01/VC-INCENTIVE:-"]
    assert (incentive.formula_id, incentive.value) == ("tp.vc_expected_value.v1", "5000.00")
    assert incentive.params["probabilities"] == "0.2,0.5,0.3"
    bonus = traced["vc_unconstrained:K-01/VC-BONUS:-"]
    assert (bonus.formula_id, bonus.value) == ("tp.vc_most_likely.v1", "150000.00")
    assert traced["vc_constrained:K-01/VC-BONUS:-"].value == "0.00"
    # EX-04-A: with progress 40 % the revenue target is 1,002,000.00.
    basis = tp.allocation_basis
    assert money.cumulative_posted(basis.exact, basis.posted, Fraction(2, 5), 2) == 100_200_000


def test_s04_r02_version_state_nodes() -> None:
    ctx, priced, traced = fold(ex_04_a())
    tp = priced.tp
    for column in (
        "transaction_price",
        "fixed_consideration",
        "vc_constrained_amount",
        "vc_excluded_amount",
        "tp_allocation_basis",
    ):
        assert f"{column}:CG-1:-" in traced, column
    assert {f"{column}:CG-1:-" for _, column in s04_transaction_price.TP_COMPONENTS} <= set(traced)
    members = (
        tp.fixed,
        tp.vc_constrained,
        tp.expected_returns,
        tp.consideration_payable,
        tp.financing_adjustment,
        tp.noncash,
    )
    assert tp.total.exact == sum((member.exact for member in members), Fraction(0))  # S04-INV-01
    total = traced["transaction_price:CG-1:-"]
    assert (total.formula_id, total.value, total.params["signs"]) == (
        "tp.buildup.v1",
        "2505000.00",
        "+,+,+,+,+,+",
    )
    assert total.inputs[:2] == ("fixed_consideration:CG-1:-", "vc_constrained_amount:CG-1:-")
    fixed = traced["fixed_consideration:CG-1:-"]
    assert (fixed.formula_id, fixed.inputs) == ("tp.fixed.v1", ("stated_price:K-01/POB-01:-",))
    assert traced["tp_allocation_basis:CG-1:-"].value == "2505000.00"
    assert list(s04_transaction_price.POLICY_KEYS) == sorted(set(s04_transaction_price.POLICY_KEYS))
    assert list(s04_transaction_price.FORMULA_IDS) == sorted(set(s04_transaction_price.FORMULA_IDS))
    # S04-R-01: the boundary nodes carry @<key>. Both versions are in force at inception, so they
    # count at every position, before the bonus event too: the inception price holds a version
    # wherever its event stands (rev 1.145; item ENG-INCEPTION-ESTIMATE-1). The position rule is
    # ``test_s04_r01_a_version_dated_after_the_inception_counts_from_its_event``.
    bonus_event = event_of(priced, "K-01/EV-000003")
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    before = s04_transaction_price.price_at(ctx, priced.pob, INCEPTION, tb, before=bonus_event)
    assert (before.total.posted, before.vc_excluded.posted, before.before_event_key) == (
        250_500_000,
        15_000_000,
        "K-01/EV-000003",
    )
    boundary = {node.id: node for node in tb.build(root_measures={}).nodes}
    assert boundary["transaction_price@K-01/EV-000003:CG-1:-"].value == "2505000.00"
    assert s04_transaction_price.price_at(ctx, priced.pob, INCEPTION, None) == tp


def test_s04_r01_a_version_dated_after_the_inception_counts_from_its_event() -> None:
    """S04-R-01: a version pin counts only when its event precedes ``before``. The bonus of
    EX-04-A dated one month after the inception: the inception price and the price before the
    bonus event hold the incentive alone, and the price after the event excludes the constrained
    bonus of 150,000.00. Until rev 1.145 ``test_s04_r02_version_state_nodes`` asserted this at the
    inception date, where a version now counts at every position (S01-R-18)."""
    later = date(2026, 2, 1)
    bonus = dataclasses.replace(BONUS, effective_date=later)
    payload = {"estimate_version_id": bonus.version_key}
    bonus_changed = bundles.event(CONTRACT, 3, "ESTIMATE_CHANGED", later, payload)
    world = bundle(booking(), changed(2, INCENTIVE), bonus_changed, versions=(INCENTIVE, bonus))
    ctx, priced, _ = fold(world)
    assert (priced.tp.total.posted, priced.tp.vc_excluded.posted) == (250_500_000, 0)
    bonus_event = event_of(priced, "K-01/EV-000003")
    before = s04_transaction_price.price_at(ctx, priced.pob, later, None, before=bonus_event)
    assert (before.total.posted, before.vc_excluded.posted, before.before_event_key) == (
        250_500_000,
        0,
        "K-01/EV-000003",
    )
    after = s04_transaction_price.price_at(ctx, priced.pob, later, None)
    assert (after.total.posted, after.vc_excluded.posted, after.before_event_key) == (
        250_500_000,
        15_000_000,
        None,
    )


def routed_line(key: str, product_code: str, price: str, flag: str) -> dict[str, object]:
    line = bundles.booking_line(key, product_code=product_code, total_price=price, end=END)
    return {**line, "scope_flag": flag, "out_of_scope_amount": Decimal(price) - 500}


def test_s04_r03_out_of_scope_counts_lease_targets() -> None:
    # S03-R-11, S04-R-03: a LEASE_842 target stays in fixed consideration and reports its
    # out_of_scope_amount in the memo, beside a line excluded from obligations (ALC-CHK-118;
    # L3-1-Q-44, found at the L3 merge gate).
    lines = [
        bundles.booking_line("POB-01", product_code="SKU-1", total_price="2500.00", end=END),
        routed_line("POB-02", "SKU-LEASE", "8000.00", "LEASE_842"),
        routed_line("POB-03", "SKU-INS", "700.00", "INSURANCE_944"),
    ]
    booked = bundles.event(
        CONTRACT,
        1,
        "CONTRACT_BOOKED",
        INCEPTION,
        {"lines": lines},
        obligation_keys=["POB-01", "POB-02", "POB-03"],
    )
    products = tuple(product(code, "TPL-PIT") for code in ("SKU-1", "SKU-INS", "SKU-LEASE"))
    _, priced, traced = fold(bundle(booked, products=products))
    tp = priced.tp
    assert [(ob.subject_key, ob.routed_out) for ob in priced.pob.obligations] == [
        ("K-01/POB-01", False),
        ("K-01/POB-02", True),
    ]
    assert (tp.fixed.posted, tp.out_of_scope.posted, tp.total.posted) == (
        1_050_000,
        770_000,
        1_050_000,
    )
    memo = traced["out_of_scope_amount:CG-1:-"]
    assert (memo.value, memo.params["signs"]) == ("7700.00", "+,+")
    assert priced.tp_unconstrained[CONTRACT].at(INCEPTION).out_of_scope.posted == 770_000


def test_s04_inv_02_constraint_between_bounds() -> None:
    outside = dataclasses.replace(
        BONUS, most_conservative_amount=Decimal("20000.00"), constrained_amount=Decimal("10000.00")
    )
    with pytest.raises(EngineError) as raised:
        fold(bundle(booking(), changed(2, outside), versions=(outside,)))
    assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert raised.value.detail["invariant"] == "S04-INV-02"
    assert raised.value.detail["estimate_version_key"] == "K-01/VC-BONUS@v1"


def test_s04_r05_method_rules() -> None:
    tie = version(
        "VC-TIE",
        method="MOST_LIKELY_AMOUNT",
        vc_type="BONUS",
        scenarios=(("150000.00", "0.5"), ("0.00", "0.5")),
        constrained="0.00",
    )
    _, priced, _ = fold(bundle(booking(), changed(2, tie), versions=(tie,)))
    assert (priced.tp.vc_constrained.posted, priced.tp.vc_excluded.posted) == (0, 0)
    stored = dataclasses.replace(INCENTIVE, unconstrained_amount=Decimal("5001.00"))
    with pytest.raises(EngineError) as raised:
        fold(bundle(booking(), changed(2, stored), versions=(stored,)))
    assert raised.value.detail["rule"] == "S04-R-05"
    skewed = dataclasses.replace(
        INCENTIVE,
        scenarios=({"amount": Decimal("100000.00"), "probability": Decimal("0.9")},),
        unconstrained_amount=None,
    )
    with pytest.raises(ValueError, match="probabilities"):
        fold(bundle(booking(), changed(2, skewed), versions=(skewed,)))


def test_s04_r05_entered_amount_under_preset() -> None:
    stream = golden_streams.stream("Contract 2", "02")
    ctx, priced, traced = fold(stream.input_bundle(preset="LEGACY_PARITY"))
    tp = priced.tp
    assert priced.pob.findings == ()
    assert s04_transaction_price.first_boundary(priced.pob) is None
    assert (tp.fixed.posted, tp.vc_constrained.posted, tp.vc_excluded.posted) == (
        100_000,
        -10_000,
        0,
    )
    assert (tp.total.posted, tp.allocation_basis.posted) == (90_000, 90_000)
    (element,) = tp.elements
    assert (element.estimate_key, element.amount.posted) == ("Contract 2/VC-VC %231", -10_000)
    entered = traced["vc_unconstrained:Contract 2/VC-VC %231:-"]
    assert (entered.formula_id, entered.value) == ("tp.vc_entered.v1", "-100.00")
    assert traced["vc_constrained:Contract 2/VC-VC %231:-"].params["constraint"] == "NOT_APPLIED"
    assert traced["transaction_price:CG-Contract 2:-"].value == "900.00"
    assert s04_transaction_price.price_at(ctx, priced.pob, date(2023, 1, 1), None) == tp


def _usage(stream: int, month: int, rated: str, reported: date) -> EventInput:
    start = date(2026, month, 1)
    payload = {
        "obligation_key": "POB-01",
        "usage_period_start": start,
        "usage_period_end": month_end(start),
        "metric": "API_CALLS",
        "quantity": Decimal("1000"),
        "rated_amount": Decimal(rated),
    }
    return bundles.event(
        CONTRACT, stream, "USAGE_REPORTED", reported, payload, obligation_keys=["POB-01"]
    )


def test_s04_r06_realised_usage() -> None:
    events = (
        booking(price="0.00", product_code="SKU-U"),
        _usage(2, 1, "120.00", date(2026, 2, 3)),
        _usage(3, 2, "80.00", date(2026, 3, 2)),
        _usage(4, 3, "50.00", date(2026, 4, 2)),
    )
    products = (product("SKU-U", "TPL-USAGE"),)
    ctx, priced, traced = fold(bundle(*events, products=products))
    assert priced.tp.vc_constrained.posted == 0  # no usage period ended by inception
    assert traced["realised_usage:K-01/POB-01:-"].value == "0.00"
    pob = priced.pob
    at_feb = s04_transaction_price.price_at(ctx, pob, date(2026, 2, 28), None)
    assert (at_feb.vc_constrained.posted, at_feb.total.posted) == (20_000, 20_000)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    at_mar = s04_transaction_price.price_at(ctx, pob, date(2026, 3, 31), tb)
    assert at_mar.vc_constrained.posted == 25_000
    node = {n.id: n for n in tb.build(root_measures={}).nodes}["realised_usage:K-01/POB-01:-"]
    assert (node.formula_id, node.value, len(node.inputs)) == ("tp.realised_usage.v1", "250.00", 3)
    march_report = event_of(priced, "K-01/EV-000004")
    before_march = s04_transaction_price.price_at(
        ctx, pob, date(2026, 3, 31), None, before=march_report
    )
    assert before_march.vc_constrained.posted == 20_000
    estimated = {"usage.tier_minimum_method": "ESTIMATE_MEASUREMENT_PERIOD_TP"}
    ctx, priced, _ = fold(bundle(*events, products=products, overrides=estimated))
    at_mar = s04_transaction_price.price_at(ctx, priced.pob, date(2026, 3, 31), None)
    assert at_mar.vc_constrained.posted == 0


def test_s04_r04_rebate_direction() -> None:
    rebate = version("VC-REBATE", method="ENTERED_AMOUNT", vc_type="REBATE", constrained="300.00")
    claim = version("VC-CLAIM", method="ENTERED_AMOUNT", vc_type="CLAIM", constrained="1000.00")
    events = (booking(price="10000.00"), changed(2, rebate), changed(3, claim))
    _, priced, traced = fold(bundle(*events, versions=(rebate, claim)))
    tp = priced.tp
    assert (tp.vc_constrained.posted, tp.total.posted) == (-30_000, 970_000)
    assert [element.estimate_key for element in tp.elements] == ["K-01/VC-REBATE"]
    node = traced["vc_constrained:K-01/VC-REBATE:-"]
    assert (node.value, node.params["direction"]) == ("-300.00", "DECREASE")
    enforceable = JudgementInput(
        judgement_key="J-CLAIM-1",
        topic="OTHER",
        subject_key=CONTRACT,
        book_code=None,
        outcome={"claim_enforceable": "true", "estimate_key": "K-01/VC-CLAIM"},
    )
    _, priced, _ = fold(bundle(*events, versions=(rebate, claim), judgements=(enforceable,)))
    assert (priced.tp.vc_constrained.posted, priced.tp.total.posted) == (70_000, 1_070_000)


def test_l8_d_contract_royalty_accrual_enters_vc_constrained() -> None:
    """D-88 L7-5-Q-8 on the ALC-S4-EX35-CASEB world: a ``ROYALTY_ACCRUAL`` element with
    allocation_target CONTRACT on a contract with no royalty or usage obligation is VC of the
    contract. Under POL-056 ACCRUE_ESTIMATE its January pin (200.00) enters vc_constrained once
    the usage period has ended, and a royalty statement for that period removes it (S04-R-06)."""
    key = obligation_subject_key(CONTRACT, "ROY-2026-01")
    january = date(2026, 1, 31)
    accrual = dataclasses.replace(
        version("ROY-2026-01", method="ENTERED_AMOUNT", vc_type=None),
        estimate_kind="ROYALTY_ACCRUAL",
        effective_date=january,
        expected_total_amount=Decimal("200.00"),
        parameters={"usage_period_start_date": "2026-01-01", "usage_period_end_date": "2026-01-31"},
    )
    lines = [
        bundles.booking_line(
            "L1-X", product_code="LIC-X", quantity="1", total_price="150.00", end=END
        ),
        bundles.booking_line(
            "L2-Y", product_code="LIC-Y", quantity="1", total_price="150.00", end=END
        ),
    ]
    booked = bundles.event(
        CONTRACT,
        1,
        "CONTRACT_BOOKED",
        INCEPTION,
        {"lines": lines},
        obligation_keys=["L1-X", "L2-Y"],
    )
    applied = bundles.event(
        CONTRACT, 2, "ESTIMATE_CHANGED", january, {"estimate_version_id": accrual.version_key}
    )
    products = (product("LIC-X", "TPL-PIT"), product("LIC-Y", "TPL-PIT"))
    ctx, priced, _ = fold(bundle(booked, applied, versions=(accrual,), products=products))
    assert (priced.tp.vc_constrained.posted, priced.tp.total.posted) == (0, 30_000)  # inception

    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    at_january = s04_transaction_price.price_at(ctx, priced.pob, january, tb)
    assert (at_january.vc_constrained.posted, at_january.total.posted) == (20_000, 50_000)
    assert at_january.allocation_basis.posted == 50_000
    nodes = {n.id: n for n in tb.build(root_measures={}).nodes}
    node = nodes[f"realised_royalty_accrual:{key}:-"]
    assert (node.formula_id, node.value) == ("tp.realised_usage.v1", "200.00")
    (source,) = node.inputs
    assert not isinstance(source, str)
    assert (source.ref_id, dict(source.detail or {})) == (
        accrual.version_key,
        {"member": "expected_total_amount", "value": "200"},
    )
    assert node.id in nodes["vc_constrained_amount:CG-1:-"].inputs
    before = event_of(priced, "K-01/EV-000002")
    assert (
        s04_transaction_price.price_at(ctx, priced.pob, january, None, before=before).total.posted
        == 30_000
    )

    statement = bundles.event(
        CONTRACT,
        3,
        "USAGE_REPORTED",
        date(2026, 2, 5),
        {
            "obligation_key": "L2-Y",
            "usage_period_start": date(2026, 1, 1),
            "usage_period_end": january,
            "metric": "LICENSEE_SALES",
            "quantity": Decimal("4000"),
            "rated_amount": Decimal("200.00"),
            "is_royalty_statement": True,
        },
        obligation_keys=["L2-Y"],
    )
    ctx, priced, _ = fold(
        bundle(booked, applied, statement, versions=(accrual,), products=products)
    )
    at_february = s04_transaction_price.price_at(ctx, priced.pob, date(2026, 2, 28), None)
    assert at_february.vc_constrained.posted == 0


# --- ENC-VC-direction: the T-CON-12 direction carried on the bundle (04 B3-D16; B3-DG-17) -------

# (vc_element_type, the B3-DG-17 default when the bundle carries no direction)
DIRECTION_DEFAULTS = (
    ("VOLUME_TIER", "DECREASE"),
    ("REBATE", "DECREASE"),
    ("PRICE_PROTECTION", "DECREASE"),
    ("SLA_CREDIT", "DECREASE"),
    ("DISCOUNT", "DECREASE"),
    ("RETURN", "DECREASE"),
    ("REFUND", "DECREASE"),
    ("PENALTY", "DECREASE"),
    ("IMPLICIT_PRICE_CONCESSION", "DECREASE"),
    ("BONUS", "INCREASE"),
    ("PERFORMANCE_INCENTIVE", "INCREASE"),
    ("MILESTONE", "INCREASE"),
    ("UNPRICED_CHANGE_ORDER", "INCREASE"),
    (None, "INCREASE"),  # the legacy VC element of S01-R-06
)


def _fold_traced(applied: EstimateVersionInput) -> tuple[PricedState, dict[str, TraceNode]]:
    _, priced, traced = fold(
        bundle(booking(price="10000.00"), changed(2, applied), versions=(applied,))
    )
    return priced, traced


def _reevaluates(applied: EstimateVersionInput) -> None:
    """DG-ENG-04 / PROP:P14: every stage 04 node of the element re-evaluates from its inputs."""
    value = bundle(booking(price="10000.00"), changed(2, applied), versions=(applied,))
    ctx = context(value)
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    identified = s02_contract_identification.run(
        ctx, cb, TraceBuilder(engine_version=ENGINE_VERSION)
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    pob = s03_pob_builder.run(ctx, identified, tb)
    s04_transaction_price.run(ctx, pob, tb)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}


@pytest.mark.parametrize(("vc_type", "default"), DIRECTION_DEFAULTS, ids=str)
def test_enc_vc_direction_absent_keeps_the_b3_dg_17_default(
    vc_type: str | None, default: str
) -> None:
    """A version without a direction is measured under the documented default (VOLUME_TIER absent
    is still DECREASE); the trace records the resolved direction and its sign."""
    applied = version("VC-D", method="ENTERED_AMOUNT", vc_type=vc_type, constrained="300.00")
    assert applied.direction is None
    assert vc.direction(applied) == default
    priced, traced = _fold_traced(applied)
    sign = -1 if default == "DECREASE" else 1
    assert (priced.tp.vc_constrained.posted, priced.tp.total.posted) == (
        sign * 30_000,
        1_000_000 + sign * 30_000,
    )
    node = traced["vc_constrained:K-01/VC-D:-"]
    assert (node.value, node.params["direction"], node.params["sign"]) == (
        f"{sign * 300}.00",
        default,
        str(sign),
    )
    _reevaluates(applied)


@pytest.mark.parametrize(("vc_type", "_default"), DIRECTION_DEFAULTS, ids=str)
@pytest.mark.parametrize("explicit", ["INCREASE", "DECREASE"])
def test_enc_vc_direction_explicit_governs_every_type(
    vc_type: str | None, _default: str, explicit: str
) -> None:
    """An explicit T-CON-12 direction governs the sign whatever the type's default: a positive
    VOLUME_TIER overage (INCREASE) adds to the price, a DECREASE BONUS reduces it (B3-D16)."""
    applied = version(
        "VC-D", method="ENTERED_AMOUNT", vc_type=vc_type, constrained="300.00", direction=explicit
    )
    assert vc.direction(applied) == explicit
    priced, traced = _fold_traced(applied)
    sign = -1 if explicit == "DECREASE" else 1
    assert (priced.tp.vc_constrained.posted, priced.tp.total.posted) == (
        sign * 30_000,
        1_000_000 + sign * 30_000,
    )
    unconstrained = traced["vc_unconstrained:K-01/VC-D:-"]
    constrained = traced["vc_constrained:K-01/VC-D:-"]
    assert (unconstrained.params["direction"], unconstrained.params["sign"]) == (
        explicit,
        str(sign),
    )
    assert (constrained.value, constrained.params["direction"]) == (f"{sign * 300}.00", explicit)
    _reevaluates(applied)


def test_enc_vc_direction_volume_tier_increase_versus_default() -> None:
    """VC-FS-02's element shape: VOLUME_TIER, EXPECTED_VALUE over magnitude scenarios, constrained
    20,000.00. Absent: −20,000.00 (B3-DG-17). Explicit INCREASE: +20,000.00, the scenarios still
    magnitudes in the trace and the sign on the formula (tp.vc_expected_value.v1)."""
    scenarios = (("0.00", "0.25"), ("40000.00", "0.50"), ("80000.00", "0.25"))
    absent = version(
        "VC-OVG",
        method="EXPECTED_VALUE",
        vc_type="VOLUME_TIER",
        scenarios=scenarios,
        unconstrained="40000.00",
        conservative="0.00",
        constrained="20000.00",
    )
    increase = dataclasses.replace(absent, direction="INCREASE")
    decrease = dataclasses.replace(absent, direction="DECREASE")
    for applied, sign in ((absent, -1), (decrease, -1), (increase, 1)):
        priced, traced = _fold_traced(applied)
        tp = priced.tp
        # vc_excluded = Σ (U − K) carries the direction's sign (S04-R-07; the 50-15 narrative).
        assert (tp.vc_constrained.posted, tp.vc_excluded.posted) == (
            sign * 2_000_000,
            sign * 2_000_000,
        )
        assert tp.total.posted == 1_000_000 + sign * 2_000_000
        unconstrained = traced["vc_unconstrained:K-01/VC-OVG:-"]
        assert unconstrained.value == f"{sign * 40000}.00"
        assert [
            ref.detail["value"] for ref in unconstrained.inputs if not isinstance(ref, str)
        ] == [
            "0",
            "40000",
            "80000",
        ]
        assert (unconstrained.params["sign"], unconstrained.params["probabilities"]) == (
            str(sign),
            "0.25,0.5,0.25",
        )
        constrained = traced["vc_constrained:K-01/VC-OVG:-"]
        assert (constrained.value, constrained.params["source"]) == (
            f"{sign * 20000}.00",
            "constrained_amount",
        )
        _reevaluates(applied)


def test_enc_vc_direction_most_likely_tie_breaks_towards_the_lower_price() -> None:
    """S04-R-05 [J]: equally likely outcomes take the amount giving the lower transaction price,
    so the tie-break follows the direction: INCREASE picks the smaller magnitude, DECREASE the
    larger one."""
    scenarios = (("100.00", "0.5"), ("300.00", "0.5"))
    for explicit, magnitude, sign in (("INCREASE", 100, 1), ("DECREASE", 300, -1)):
        applied = version(
            "VC-TIE",
            method="MOST_LIKELY_AMOUNT",
            vc_type="BONUS",
            scenarios=scenarios,
            direction=explicit,
        )
        priced, traced = _fold_traced(applied)
        assert priced.tp.vc_constrained.posted == sign * magnitude * 100
        assert traced["vc_unconstrained:K-01/VC-TIE:-"].value == f"{sign * magnitude}.00"


def test_enc_vc_direction_malformed_literal_fails_closed() -> None:
    """A direction outside {INCREASE, DECREASE} is malformed input (T-CON-12; CV-45)."""
    applied = version(
        "VC-BAD", method="ENTERED_AMOUNT", vc_type="BONUS", constrained="1.00", direction="UP"
    )
    with pytest.raises(ValueError, match="not INCREASE or DECREASE"):
        fold(bundle(booking(), changed(2, applied), versions=(applied,)))
