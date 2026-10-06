"""Stage 05 relative-SSP allocation (ENGINE_SPEC §5.4 to §5.6; EX-05-A, EX-05-B; BUILD_SPEC ENA-11).

Golden Contracts 1, 2 and 4 replay under the parity preset (``support.golden_streams``); native
bundles are built here with ``support.bundles``. Stages 01 to 05 run for real. No database fixture
(DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

import erev_engine
import pytest
from erev_engine import ENGINE_VERSION, money
from erev_engine.bundle import (
    EstimateVersionInput,
    EventInput,
    InputBundle,
    MaterialRightInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.enums import BookCode, ScopeFlag
from erev_engine.errors import EngineError
from erev_engine.stages import (
    s01_canonicalize,
    s02_contract_identification,
    s03_pob_builder,
    s04_transaction_price,
    s05_allocation,
)
from erev_engine.stages.s04_transaction_price import PricedState
from erev_engine.stages.state import AllocatedState, BookContext, ObligationState, PolicyResolver
from erev_engine.trace import TraceBuilder, TraceNode
from support import bundles, golden_streams

CONTRACT = "K-01"
INCEPTION = date(2026, 1, 1)
END = date(2026, 12, 31)
ZERO = "0" * 64
BOOK = "BOOK-A"
VOUCHER = "SKU-VOUCHER"
LIKELIHOOD = f"{CONTRACT}/LIKELIHOOD-1"
GOLDEN = (("Contract 1", "02"), ("Contract 2", "02"), ("Contract 4", "03"))

PolicyValue = str | Mapping[str, str]


def template(code: str, kind: str = "STANDARD") -> TemplateInput:
    return TemplateInput(
        template_code=code,
        version_key=f"{code}@v1",
        version_no=1,
        content_sha256=ZERO,
        obligation_kind=kind,
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


def entry(
    product: str,
    *,
    point: str | None = None,
    legacy: tuple[str, str, str] | None = None,
    observable: str | None = None,
) -> SspEntryInput:
    """A point entry (``observable``, one ``NONE`` row) or a ``legacy_range`` entry (L, d, r)."""
    list_price, discount, spread = legacy or (None, None, None)
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
        method="observable" if legacy is None else "legacy_range",
        value_basis="AMOUNT",
        unit_list_price=None if list_price is None else Decimal(list_price),
        midpoint_discount_ratio=None if discount is None else Decimal(discount),
        range_ratio=None if spread is None else Decimal(spread),
        cost_basis=None,
        margin_ratio=None,
        distinctness="distinct",
        revenue_account_code=None,
        observable_point=None if observable is None else Decimal(observable),
        ranges=()
        if point is None
        else (SspRangeInput("NONE", None, None, Decimal(point), None, None, None),),
    )


def booking_line(
    key: str, product: str, price: str, quantity: str = "1", **members: object
) -> dict[str, object]:
    line = bundles.booking_line(
        key, product_code=product, quantity=quantity, total_price=price, start=INCEPTION, end=END
    )
    return {**line, **members}


def native(
    *lines: dict[str, object],
    entries: Sequence[SspEntryInput],
    overrides: Mapping[str, PolicyValue] | None = None,
    rights: Sequence[MaterialRightInput] = (),
    estimates: Sequence[EstimateVersionInput] = (),
) -> InputBundle:
    calendar = bundles.entity(start=INCEPTION, months=24)
    base = bundles.book("ASC606", entity=calendar)
    values = overrides or {}
    policies = tuple(
        dataclasses.replace(policy, value=values[policy.code])
        if policy.code in values and policy.scope == "GROUP"
        else policy
        for policy in base.policies
    )
    header = dataclasses.replace(
        bundles.contract(CONTRACT, inception=INCEPTION), material_rights=tuple(rights)
    )
    codes = sorted({str(line["product_code"]) for line in lines})
    products = tuple(
        bundles.product(code, template_code="TPL-MR" if code == VOUCHER else "TPL-PIT", family=None)
        for code in codes
    )
    keys = [str(line["obligation_key"]) for line in lines]
    events: list[EventInput] = [
        bundles.event(
            CONTRACT, 1, "CONTRACT_BOOKED", INCEPTION, {"lines": list(lines)}, obligation_keys=keys
        )
    ]
    for number, version in enumerate(estimates, start=2):
        payload = {"estimate_version_id": version.version_key}
        events.append(bundles.event(CONTRACT, number, "ESTIMATE_CHANGED", INCEPTION, payload))
    book = SspVersionInput(
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
        entries=tuple(sorted(entries, key=lambda e: e.product_code)),
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
        events=tuple(events),
        ssp_versions=(book,),
        pob_template_versions=(template("TPL-MR", "MATERIAL_RIGHT"), template("TPL-PIT")),
        rule_set_versions=(),
        estimate_versions=tuple(estimates),
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


def fold(
    value: InputBundle,
) -> tuple[BookContext, PricedState, AllocatedState, dict[str, TraceNode]]:
    """Stages 01 to 05 with one trace builder for stages 03 to 05 (§0.3)."""
    ctx = context(value)
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    identified = s02_contract_identification.run(
        ctx, cb, TraceBuilder(engine_version=ENGINE_VERSION)
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    priced = s04_transaction_price.run(ctx, s03_pob_builder.run(ctx, identified, tb), tb)
    allocated = s05_allocation.run(ctx, priced, tb)
    return ctx, priced, allocated, {node.id: node for node in tb.build(root_measures={}).nodes}


def golden(
    contract: str, step: str
) -> tuple[BookContext, PricedState, AllocatedState, dict[str, TraceNode]]:
    return fold(golden_streams.stream(contract, step).input_bundle(preset="LEGACY_PARITY"))


def posted(allocated: AllocatedState) -> list[int]:
    return [ob.original_allocation.a_posted for ob in allocated.obligations]


def exact_4dp(allocated: AllocatedState) -> list[int]:
    return [money.round_half_up(ob.original_allocation.x_exact, 4) for ob in allocated.obligations]


def by_key(allocated: AllocatedState, key: str) -> ObligationState:
    return next(ob for ob in allocated.obligations if ob.obligation_key == key)


def test_ex_05_a_golden_contract2() -> None:
    _, priced, allocated, traced = golden("Contract 2", "02")
    assert allocated.findings == ()
    obligations = allocated.obligations
    assert [ob.obligation_key for ob in obligations] == ["POB #1", "POB #2", "POB #3", "VC #1"]
    snapshots = [ob.ssp for ob in obligations]
    assert all(ssp is not None for ssp in snapshots)
    assert [(s.low, s.mid, s.high) for s in snapshots if s is not None] == [
        (612, 720, 828),
        (408, 480, 552),
        (150, 150, 150),
        (0, 0, 0),
    ]
    assert [s.selected for s in snapshots if s is not None] == [612, 408, 150, 0]
    assert priced.tp.allocation_basis.posted == 90_000
    assert traced["total_ssp:CG-Contract 2:-"].value == "1170"
    keys = [ob.subject_key for ob in obligations]
    weights = [Fraction(612), Fraction(408), Fraction(150), Fraction(0)]
    assert money.largest_remainder(90_000, weights, keys) == [47_077, 31_385, 11_538, 0]
    assert posted(allocated) == [47_077, 31_385, 11_538, 0]
    assert exact_4dp(allocated) == [4_707_692, 3_138_462, 1_153_846, 0]
    amount = traced["original_allocated_amount:Contract 2/POB %231:-"]
    assert (amount.formula_id, amount.value, amount.rounding_residue) == (
        "alloc.largest_remainder.v1",
        "470.77",
        money.format_exact(Fraction(612 * 900, 1170) - Fraction(47_077, 100)),
    )
    weight = traced["allocation_weight:Contract 2/POB %231:-"]
    assert (weight.formula_id, weight.value) == (
        "alloc.relative_ssp.v1",
        money.format_exact(Fraction(612, 1170)),
    )
    assert traced["original_allocated_exact:Contract 2/VC %231:-"].value == "0"


def test_chk_002_contracts_1_and_4() -> None:
    _, _, allocated, _ = golden("Contract 1", "02")
    assert [ob.ssp.selected for ob in allocated.obligations if ob.ssp is not None] == [
        500,
        368,
        150,
        1000,
    ]
    assert posted(allocated) == [32_210, 23_707, 9_663, 64_420]
    assert exact_4dp(allocated) == [3_221_011, 2_370_664, 966_303, 6_442_022]
    _, _, allocated, _ = golden("Contract 4", "03")
    assert [ob.ssp.selected for ob in allocated.obligations if ob.ssp is not None] == [
        612,
        544,
        150,
        0,
    ]
    assert posted(allocated) == [44_518, 39_571, 10_911, 0]
    assert exact_4dp(allocated) == [4_451_761, 3_957_121, 1_091_118, 0]


def likelihood(rate: str) -> EstimateVersionInput:
    return EstimateVersionInput(
        estimate_key=LIKELIHOOD,
        estimate_kind="EXERCISE_LIKELIHOOD",
        element_code="LIKELIHOOD-1",
        method="ENTERED_AMOUNT",
        vc_element_type=None,
        allocation_target="CONTRACT",
        target_obligation_keys=(),
        obligation_key="POB-02",
        version_key=f"{LIKELIHOOD}@v1",
        version_no=1,
        status="APPROVED",
        effective_date=INCEPTION,
        scenarios=(),
        parameters={},
        unconstrained_amount=None,
        most_conservative_amount=None,
        constrained_amount=None,
        rate=Decimal(rate),
        expected_total_amount=None,
        expected_quantity=None,
        amortization_months=None,
        currency=None,
        supersedes_version_key=None,
        judgement_key=None,
        content_sha256=ZERO,
    )


def test_chk_054_voucher_allocation() -> None:
    right = MaterialRightInput(
        obligation_key="POB-02",
        option_type="OTHER",
        incremental_discount_ratio=Decimal("0.30"),  # 40 % voucher less 10 % without the contract
        is_discount_available_without_contract=False,
        expected_purchase_amount=Decimal("50.00"),
        currency="USD",
        ssp_method="DISCOUNT_X_LIKELIHOOD",
        expiry_date=None,
        likelihood_estimate_key=LIKELIHOOD,
        is_legacy_quantity_ssp_dollars=False,
    )
    value = native(
        booking_line("POB-01", "SKU-A", "100.00"),
        booking_line("POB-02", VOUCHER, "0.00"),
        entries=[entry("SKU-A", point="100"), entry(VOUCHER, point="0")],
        rights=[right],
        estimates=[likelihood("0.80")],
    )
    _, _, allocated, _ = fold(value)
    assert allocated.findings == ()
    assert [ob.ssp.selected for ob in allocated.obligations if ob.ssp is not None] == [100, 12]
    assert posted(allocated) == [8_929, 1_071]
    assert exact_4dp(allocated) == [892_857, 107_143]
    option = by_key(allocated, "POB-02")
    assert option.material_right is not None and option.material_right.option_ssp == 12


def ex_05_b(policy: str, observable: str | None = None) -> InputBundle:
    return native(
        booking_line("POB-01", "SKU-LIC", "120.00"),
        booking_line("POB-02", "SKU-SVC", "300.00"),
        entries=[
            entry("SKU-LIC", legacy=("200", "0.20", "0.15"), observable=observable),
            entry("SKU-SVC", point="300"),
        ],
        overrides={"ssp.outside_range_point": policy},
    )


def test_chk_030_allocations() -> None:
    cases = (
        ("NEAREST_BOUND", None, [13_101, 28_899]),
        ("LOW_POINT", None, [13_101, 28_899]),
        ("MIDPOINT", None, [14_609, 27_391]),
        ("HIGH_POINT", None, [15_967, 26_033]),
        ("OBSERVABLE_POINT", "150", [14_000, 28_000]),
    )
    for policy, observable, expected in cases:
        _, priced, allocated, _ = fold(ex_05_b(policy, observable))
        assert priced.tp.allocation_basis.posted == 42_000
        assert allocated.findings == ()
        assert posted(allocated) == expected, policy


def test_l8_d_routed_out_lease_leaves_the_transaction_price() -> None:
    # D-88 L7-5-Q-6 on the CHK-118 world: the pool stays gross, the price excludes the lease.
    value = native(
        booking_line("POB-01", "SKU-LEASE", "7000.00", scope_flag="LEASE_842"),
        booking_line("POB-02", "SKU-MAINT", "3000.00"),
        entries=[entry("SKU-LEASE", point="9000"), entry("SKU-MAINT", point="3000")],
    )
    (book,) = erev_engine.compute(value).books
    version = book.contract_version
    assert version is not None
    rows = {row.columns["obligation_key"]: row.columns for row in book.obligation_versions}
    assert {key: (row["scope_flag"], row["allocated_amount"]) for key, row in rows.items()} == {
        "POB-01": ("LEASE_842", 750_000),
        "POB-02": ("IN_SCOPE_606", 250_000),
    }
    columns = version.columns
    assert (columns["fixed_consideration"], columns["out_of_scope_amount"]) == (1_000_000, 700_000)
    # transaction_price = total.posted − Σ a_posted of routed-out LEASE_842 obligations.
    assert columns["transaction_price"] == 1_000_000 - 750_000
    # DB-17 V1 over IN_SCOPE_606 rows; the gross sum would not tie.
    in_scope = sum(
        row["allocated_amount"] for row in rows.values() if row["scope_flag"] == "IN_SCOPE_606"
    )
    assert in_scope == columns["transaction_price"] - columns["consideration_payable_amount"]
    # D-97 (8) T1F-Q-1 (A): the routed-out lease re-measurement links its own node holding the
    # stored price (books.version_adjustment.v1), never the build-up node that still includes it.
    traced = {node.id: node for node in book.trace.nodes}
    priced_node = traced[version.trace_nodes["transaction_price"]]
    assert priced_node.measure.startswith("transaction_price@")
    assert Decimal(priced_node.value) * 100 == columns["transaction_price"]


def test_chk_118_embedded_lease_allocation() -> None:
    value = native(
        booking_line("POB-01", "SKU-LEASE", "7000.00", scope_flag="LEASE_842"),
        booking_line("POB-02", "SKU-MAINT", "3000.00"),
        entries=[entry("SKU-LEASE", point="9000"), entry("SKU-MAINT", point="3000")],
    )
    _, priced, allocated, _ = fold(value)
    assert priced.tp.allocation_basis.posted == 1_000_000
    lease, maintenance = allocated.obligations
    assert (lease.scope_flag, lease.original_allocation.a_posted) == (ScopeFlag.LEASE_842, 750_000)
    assert (maintenance.scope_flag, maintenance.original_allocation.a_posted) == (
        ScopeFlag.IN_SCOPE_606,
        250_000,
    )


def test_s05_r10_total_ssp_zero() -> None:
    value = native(
        booking_line("POB-01", "SKU-A", "10.00"),
        booking_line("POB-02", "SKU-B", "20.00"),
        entries=[entry("SKU-A", point="0"), entry("SKU-B", point="0")],
    )
    ctx, priced, allocated, _ = fold(value)
    assert allocated.obligations == ()
    (finding,) = allocated.findings
    assert (finding.code, finding.severity, finding.subject_key, finding.stage) == (
        "TOTAL_SSP_ZERO",
        "ERROR",
        "CG-1",
        5,
    )
    assert ctx.policies.value("alloc.zero_total_ssp") == "REJECT"  # POL-077 FORCED
    with pytest.raises(EngineError) as raised:
        s05_allocation.allocate(
            ctx,
            priced.tp,
            [Fraction(0), Fraction(0)],
            ["K-01/POB-01", "K-01/POB-02"],
            group_key="CG-1",
        )
    assert raised.value.code == "TOTAL_SSP_ZERO"


def test_s05_r16_original_columns_and_allocation_adjustment() -> None:
    _, _, allocated, traced = golden("Contract 1", "02")
    assert allocated.findings == ()
    for ob in allocated.obligations:
        assert ob.original_total_contract_price == 1300
        assert ob.original_total_contract_ssp == 2018
    first = by_key(allocated, "POB #1")
    adjustment = traced["allocation_adjustment:Contract 1/POB %231:-"]
    assert adjustment.value == "-177.90"
    assert adjustment.inputs == (
        "original_allocated_amount:Contract 1/POB %231:-",
        "stated_price:Contract 1/POB %231:-",
    )
    total = sum(
        Decimal(traced[f"allocation_adjustment:{ob.subject_key}:-"].value)
        for ob in allocated.obligations
    )
    assert total == Decimal("0.00")
    assert sum(ob.original_allocation.a_posted for ob in allocated.obligations) == 130_000
    assert first.ssp is not None and (first.ssp.low, first.ssp.mid, first.ssp.high) == (
        Fraction("382.5"),
        450,
        Fraction("517.5"),
    )
    assert (first.stated_price, first.original_stated_price, first.original_quantity) == (
        500,
        500,
        5,
    )
    assert first.resolved_ssp == 500
    assert first.account_overrides["REVENUE"] == "5001"  # REQ-SSP-014 snapshot
    assert first.account_overrides["CONTRACT_LIABILITY"] == "21001"
    (segment,) = first.segments
    assert (segment.component, segment.cause, segment.basis, segment.event_key) == (
        "FIXED",
        "INCEPTION",
        "INCEPTION",
        None,
    )
    assert (segment.effective_date, segment.a_posted, segment.x_exact) == (
        date(2023, 1, 1),
        32_210,
        first.original_allocation.x_exact,
    )
    assert (segment.unit_ssp, segment.remaining_ssp, segment.remaining_billing_plan) == (
        100,
        500,
        500,
    )
    assert (segment.progress_measure, segment.modification_boundary_no) == ("UNITS_DELIVERED", 0)
    assert segment.totals.quantity == 5
    # original_unit_revenue_rate = x_p ÷ Q
    assert segment.x_exact / segment.totals.quantity == Fraction(1300 * 500, 2018 * 5)
    right = by_key(allocated, "POB #4")
    assert right.material_right is not None and right.material_right.option_ssp == 1000
    assert allocated.tp_history[0].total.posted == 130_000


def test_s05_inv_02_quota_within_one_minor_unit() -> None:
    for contract, step in GOLDEN:
        ctx, priced, allocated, _ = golden(contract, step)
        assert allocated.findings == ()
        for ob in allocated.obligations:
            quota = ob.original_allocation
            assert abs(quota.x_exact * 100 - quota.a_posted) < 1, ob.subject_key
        basis = priced.tp.allocation_basis.posted
        assert sum(posted(allocated)) == basis  # S05-INV-01
        keys = [ob.subject_key for ob in allocated.obligations]
        weights = [ob.resolved_ssp for ob in allocated.obligations]
        again = s05_allocation.allocate(
            ctx, priced.tp, weights[::-1], keys[::-1], group_key=priced.group_key
        )
        assert [quota.a_posted for quota in again[::-1]] == posted(allocated)  # S05-INV-03


def test_s03_r13_immaterial_promise_merge() -> None:
    lines = (
        booking_line("POB-01", "SKU-LIC", "1000.00"),
        booking_line("POB-02", "SKU-TRN", "20.00"),
        booking_line("POB-03", "SKU-SUP", "80.00"),
    )
    entries = [
        entry("SKU-LIC", point="1000"),
        entry("SKU-SUP", point="80"),
        entry("SKU-TRN", point="20"),
    ]
    _, _, allocated, _ = fold(native(*lines, entries=entries))
    assert [ob.obligation_key for ob in allocated.obligations] == ["POB-01", "POB-02", "POB-03"]
    relief = {
        "pob.immaterial_promise_relief": {
            "immaterial_threshold_pct": "0.05",
            "option": "APPLY_RELIEF",
        }
    }
    _, _, allocated, traced = fold(native(*lines, entries=entries, overrides=relief))
    assert allocated.findings == ()
    host, support = allocated.obligations
    assert (host.obligation_key, support.obligation_key) == ("POB-01", "POB-03")
    assert host.ssp is not None and host.ssp.selected == 1020  # 20 ÷ 1,100 < 0.05 joins the host
    assert (host.quantity, host.stated_price) == (2, 1020)
    assert support.ssp is not None and support.ssp.selected == 80  # 80 ÷ 1,100 ≥ 0.05 stays
    assert posted(allocated) == [102_000, 8_000]
    node = traced["original_ssp_selected:K-01/POB-01:-"]
    assert (node.value, node.params["merged"]) == ("1020", "K-01/POB-02")
    assert traced["allocation_weight:K-01/POB-01:-"].value == money.format_exact(
        Fraction(1020, 1100)
    )
    assert "original_ssp_selected:K-01/POB-02:-" not in traced


def test_s05_r17_parity_preset_values() -> None:
    ctx, _, allocated, traced = golden("Contract 2", "02")
    assert dict(s05_allocation.PARITY_PRESET_VALUES) == {
        "ssp.version_basis": "NAMED_VERSION",  # POL-070
        "ssp.inside_range_point": "CONTRACT_PRICE",  # POL-071
        "ssp.outside_range_point": "NEAREST_BOUND",  # POL-072
        "ssp.range_validation": "NOT_ENFORCED",  # POL-073
        "alloc.discount_exception": "DISABLED",  # POL-076
        "vc.targeted_allocation_tolerance": "NOT_ENFORCED",  # POL-044
    }
    header = allocated.contracts[0].header
    entity = header.contracting_entity_code
    period = ctx.entities[entity].periods[0].period_key
    for code, literal in s05_allocation.PARITY_PRESET_VALUES.items():
        value = ctx.policies.value(code, contract=header.external_id, entity=entity, period=period)
        assert value == literal, code
    policies = {
        traced[f"original_ssp_selected:{ob.subject_key}:-"].params["policy"]
        for ob in allocated.obligations
    }
    assert policies == {"NEAREST_BOUND", "VC_LINE"}
    assert {ob.ssp.version_key for ob in allocated.obligations if ob.ssp is not None} == {
        "LEGACY-SKU-SSP@v1"
    }


def test_d98_78_no_obligation_with_nonzero_basis_still_raises_total_ssp_zero() -> None:
    """D-88 L7-5-Q-10 (1) in its general form (D-98 78 addendum): the skip needs BOTH no
    obligation and a zero allocation basis. A priced state stripped of its obligations while the
    basis stays 10.00 reaches ``allocate`` over zero keys and raises ``TOTAL_SSP_ZERO`` — the
    "T ≠ 0 with no obligation still raises" clause, pinned explicitly."""
    value = native(booking_line("POB-01", "SKU-A", "10.00"), entries=[entry("SKU-A", point="10")])
    ctx, priced, _, _ = fold(value)
    assert priced.tp.allocation_basis.posted == 1_000
    bare = dataclasses.replace(
        priced, pob=dataclasses.replace(priced.pob, obligations=(), routed_out=())
    )
    allocated = s05_allocation.run(ctx, bare, TraceBuilder(engine_version=ENGINE_VERSION))
    assert allocated.obligations == ()
    assert [(f.code, f.severity, f.stage) for f in allocated.findings] == [
        ("TOTAL_SSP_ZERO", "ERROR", 5)
    ]
