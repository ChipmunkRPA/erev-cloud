"""Stage 04 significant financing component.

ENGINE_SPEC §4.3 S04-R-10 to S04-R-13 with S04-R-12a (rev 1.3), §4.4 S04-INV-04 and trace params
``suspended_until``, §4.5 EX-04-B, EX-04-B2, EX-04-H; POLICIES POL-046, POL-047 notes, JET-11
(CHK-136, CHK-137, FASB Example 26); ADJUDICATION.md B3-AK-01, R-SFC-04, R-SFC-05; BUILD_SPEC ENA-8.
Bundles come from ``support.bundles``; stages 01 to 05 run for real. No database fixture
(DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION, dates, money
from erev_engine.bundle import (
    EstimateVersionInput,
    EventInput,
    InputBundle,
    JudgementInput,
    PaymentPointInput,
    ProductInput,
    ResolvedPolicyInput,
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
from erev_engine.stages.s04_transaction_price import PricedState
from erev_engine.stages.state import AllocatedState, BookContext, PolicyResolver, Target
from erev_engine.trace import TraceBuilder, TraceNode
from support import bundles

ENTITY = bundles.ENTITY_CODE
JANUARY_2026 = date(2026, 1, 1)
ZERO = "0" * 64
SSP_BOOK = "SSP-MAIN"
RATE_POLICY = "sfc.discount_rate_basis"
LINE = "L1"


def template(code: str, *, sfc_required: bool = False) -> TemplateInput:
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
        sfc_assessment_required=sfc_required,
        revenue_category=None,
        disaggregation={},
        account_role_overrides={},
        stratification_label=None,
        is_excluded_from_netting_attribution=False,
        policy_values={},
        effective_from=date(2025, 1, 1),
        effective_to=None,
    )


def product(code: str, *, returnable: bool = False) -> ProductInput:
    values = {"returns.model": "EXPECTED_RETURNS"} if returnable else {}
    return dataclasses.replace(
        bundles.product(code, template_code="TPL-PIT", family=None), policy_values=values
    )


def assessed(
    contract: str, *, significant: str = "true", exception: str = "NONE"
) -> JudgementInput:
    """A reviewed ``SFC_ASSESSMENT`` naming every obligation (``obligation_key`` empty)."""
    outcome = {"exception_32_17": exception, "obligation_key": "", "significant": significant}
    return JudgementInput(f"J-SFC-{contract}", "SFC_ASSESSMENT", contract, None, outcome)


def return_rate(contract: str, window: date) -> EstimateVersionInput:
    """A ``RETURN_RATE`` pin expecting the one unit back until ``window``."""
    key = f"{contract}/RET-1"
    return EstimateVersionInput(
        estimate_key=key,
        estimate_kind="RETURN_RATE",
        element_code="RET-1",
        method="RATE",
        vc_element_type=None,
        allocation_target="CONTRACT",
        target_obligation_keys=(),
        obligation_key=LINE,
        version_key=f"{key}@v1",
        version_no=1,
        status="APPROVED",
        effective_date=JANUARY_2026,
        scenarios=(),
        parameters={
            "carrying_cost_per_unit": "80.00",
            "recovery_cost_per_unit": "0.00",
            "window_end_date": window.isoformat(),
        },
        unconstrained_amount=None,
        most_conservative_amount=None,
        constrained_amount=None,
        rate=Decimal("1.00"),
        expected_total_amount=None,
        expected_quantity=Decimal("1"),
        amortization_months=None,
        currency="USD",
        supersedes_version_key=None,
        judgement_key=None,
        content_sha256=ZERO,
    )


def ssp_book(product_code: str, point: str) -> SspVersionInput:
    entry = SspEntryInput(
        entry_key=f"{SSP_BOOK}@v1/{product_code}//-/USD",
        product_code=product_code,
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
    return SspVersionInput(
        ssp_book_code=SSP_BOOK,
        version_key=f"{SSP_BOOK}@v1",
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
        entries=(entry,),
    )


def single(
    contract: str,
    *,
    price: str,
    transfer: date,
    points: Sequence[tuple[date, str]],
    judgements: Sequence[JudgementInput] = (),
    rate: Mapping[str, str] | None = None,
    policies: Mapping[str, str] | None = None,
    sfc_required: bool = False,
    returnable: bool = False,
    estimates: Sequence[EstimateVersionInput] = (),
    extra: Sequence[tuple[str, date, Mapping[str, object]]] = (),
    ssp: bool = False,
    months: int = 24,
    activated: bool = True,
) -> InputBundle:
    """One contract with one point-in-time line transferred on ``transfer``, its payment schedule,
    the reviewed judgements and the approved contract-level POL-047 override ``rate``."""
    code = f"PROD-{contract}"
    header = dataclasses.replace(
        bundles.contract(
            contract,
            inception=JANUARY_2026,
            payment_schedule=[PaymentPointInput(on, Decimal(amount)) for on, amount in points],
        ),
        judgements=tuple(judgements),
    )
    line = bundles.booking_line(
        LINE, product_code=code, quantity="1", total_price=price, start=transfer, end=transfer
    )
    events: list[EventInput] = [
        bundles.event(
            contract, 1, "CONTRACT_BOOKED", JANUARY_2026, {"lines": [line]}, obligation_keys=[LINE]
        )
    ]
    if activated:
        events.append(bundles.event(contract, 2, "CONTRACT_ACTIVATED", JANUARY_2026, {}))
    for version in estimates:
        payload = {"estimate_version_id": version.version_key}
        on = version.effective_date
        events.append(bundles.event(contract, len(events) + 1, "ESTIMATE_CHANGED", on, payload))
    for kind, on, payload in extra:
        keys = [LINE] if "obligation_key" in payload else []
        events.append(
            bundles.event(contract, len(events) + 1, kind, on, payload, obligation_keys=keys)
        )
    calendar = bundles.entity(start=JANUARY_2026, months=months)
    book = bundles.book("ASC606", entity=calendar)
    rows = [
        dataclasses.replace(row, value=(policies or {})[row.code])
        if row.code in (policies or {})
        else row
        for row in book.policies
    ]
    if rate is not None:
        source = f"{contract}/policy_overrides/0"
        rows.append(
            ResolvedPolicyInput(RATE_POLICY, "CONTRACT", contract, dict(rate), "C", source, "K")
        )
    book = dataclasses.replace(
        book, policies=tuple(sorted(rows, key=lambda p: (p.code, p.scope, p.subject_key)))
    )
    last = max(event.effective_date for event in events)
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(last.year, last.month, last.day, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(book,),
        entities=(calendar,),
        group=bundles.group((header,), products=[product(code, returnable=returnable)]),
        contracts=(header,),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(ssp_book(code, price),) if ssp else (),
        pob_template_versions=(template("TPL-PIT", sfc_required=sfc_required),),
        rule_set_versions=(),
        estimate_versions=tuple(sorted(estimates, key=lambda v: (v.estimate_key, v.version_no))),
        fx_rates=(),
        posted=(),
    )


def context(value: InputBundle) -> BookContext:
    (book,) = value.books
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
) -> tuple[BookContext, PricedState, AllocatedState | None, dict[str, TraceNode]]:
    """Stages 01 to 05 with one trace builder for stages 03 to 05; stage 05 runs only when the
    bundle carries an SSP book."""
    ctx = context(value)
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    identified = s02_contract_identification.run(
        ctx, cb, TraceBuilder(engine_version=ENGINE_VERSION)
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    priced = s04_transaction_price.run(ctx, s03_pob_builder.run(ctx, identified, tb), tb)
    allocated = s05_allocation.run(ctx, priced, tb) if value.ssp_versions else None
    return ctx, priced, allocated, {node.id: node for node in tb.build(root_measures={}).nodes}


def series(priced: PricedState, measure: str) -> dict[str, Target]:
    return {t.period_key: t for t in priced.specialist_targets.financing if t.measure == measure}


def month_end(year: int, month: int) -> date:
    return dates.month_end(date(year, month, 1))


# --- EX-04-B advance payment (CHK-136) ----------------------------------------------------------

ADV = "K-ADV"
ADV_TRANSFER = date(2028, 1, 1)


def advance(compounding: str = "MONTHLY", *, window: date | None = None) -> InputBundle:
    """EX-04-B: 4,000.00 paid on 1 January 2026 for an asset transferred on 1 January 2028."""
    return single(
        ADV,
        price="4000.00",
        transfer=ADV_TRANSFER,
        points=[(JANUARY_2026, "4000.00")],
        judgements=[assessed(ADV)],
        rate={"annual_rate": "0.06", "basis": "ENTITY_BORROWING_RATE", "compounding": compounding},
        returnable=window is not None,
        estimates=[] if window is None else [return_rate(ADV, window)],
        months=25,
    )


def test_ex_04_b_advance_monthly() -> None:
    _, priced, _, nodes = fold(advance())
    assert priced.findings == ()
    interest = series(priced, "financing_interest_cum")
    assert (interest["FY2026-P01"].value, interest["FY2026-P12"].value) == (2_000, 24_671)
    assert interest["FY2027-P12"].value == 50_864
    assert interest["FY2026-P12"].value - interest["FY2026-P11"].value == 2_113  # month 12 21.13
    assert interest["FY2027-P12"].value - interest["FY2027-P11"].value == 2_243  # month 24 22.43
    assert (interest["FY2027-P12"].cause, interest["FY2027-P12"].entity) == ("ADVANCE", ENTITY)
    assert interest["FY2027-P12"].subject_key == f"{ADV}@{ENTITY}"
    balance = series(priced, "financed_balance")  # contract liability 4,246.71 and 4,508.64
    assert (balance["FY2026-P12"].value, balance["FY2027-P12"].value) == (424_671, 450_864)
    assert balance["FY2028-P01"].value == 0  # relieved by revenue at transfer
    tp = priced.tp
    assert (tp.financing_adjustment.posted, tp.total.posted, tp.allocation_basis.posted) == (
        50_864,
        450_864,
        450_864,
    )
    assert nodes["financing_adjustment_amount:CG-1:-"].value == "508.64"
    assert nodes["transaction_price:CG-1:-"].value == "4508.64"
    csp = nodes[f"cash_selling_price:{ADV}/{LINE}:-"]
    assert (csp.value, csp.formula_id, csp.params["kind"]) == (
        "4508.64",
        "sfc.cash_selling_price.v1",
        "ADVANCE",
    )
    node = nodes[f"financing_interest_cum:{ADV}@{ENTITY}:FY2026-P01"]
    assert (node.value, node.formula_id, node.params["compounding"]) == (
        "20.00",
        "sfc.effective_interest.monthly.v1",
        "MONTHLY",
    )
    gap = nodes[f"financing_gap_test:{ADV}/{LINE}:-"]
    assert (gap.formula_id, gap.params["reason"], gap.params["adjust"]) == (
        "sfc.gap_test.v1",
        "SIGNIFICANT_GAP",
        "true",
    )


def test_ex_04_b_advance_annual() -> None:
    _, priced, _, nodes = fold(advance("ANNUAL"))
    assert priced.findings == ()
    interest = series(priced, "financing_interest_cum")
    assert [interest[f"FY2026-P{m:02d}"].value for m in (1, 2, 12)] == [2_000, 4_000, 24_000]
    assert interest["FY2027-P12"].value - interest["FY2026-P12"].value == 25_440
    assert interest["FY2027-P01"].value - interest["FY2026-P12"].value == 2_120  # 21.20 a month
    assert (priced.tp.financing_adjustment.posted, priced.tp.total.posted) == (49_440, 449_440)
    node = nodes[f"financing_interest_cum:{ADV}@{ENTITY}:FY2027-P12"]
    assert (node.formula_id, node.value) == ("sfc.effective_interest.annual.v1", "494.40")


# --- EX-04-B2 deferred payment (CHK-137) --------------------------------------------------------

FIN = "C-FIN-B"
INSTALMENTS = [(month_end(2026 + k // 12, k % 12 + 1), "18871.00") for k in range(60)]


def instalments() -> InputBundle:
    """EX-04-B2: 60 monthly instalments of 18,871.00 after a transfer on 1 January 2026."""
    return single(
        FIN,
        price="1132260.00",
        transfer=JANUARY_2026,
        points=INSTALMENTS,
        judgements=[assessed(FIN)],
        rate={"annual_rate": "0.12", "basis": "CUSTOMER_CREDIT_RATE", "compounding": "MONTHLY"},
        months=60,
    )


def test_ex_04_b2_deferred_payment() -> None:
    _, priced, _, nodes = fold(instalments())
    assert priced.findings == ()
    csp = nodes[f"cash_selling_price:{FIN}/{LINE}:-"]
    assert (csp.value, csp.params["kind"]) == ("848346.53", "DEFERRED")
    tp = priced.tp
    assert (tp.financing_adjustment.posted, tp.total.posted) == (-28_391_347, 84_834_653)
    interest = series(priced, "financing_interest_cum")
    assert interest["FY2026-P01"].value == 848_347  # round(848,346.5298… × 0.01)
    assert interest["FY2026-P01"].cause == "DEFERRED"
    assert interest["FY2026-P02"].value == 1_686_306  # month 2 8,379.59 (key end-of-month-2)
    assert interest["FY2030-P12"].value == 113_226_000 - 84_834_653


def test_s04_r10_review_required_and_expedient() -> None:
    far = [(date(2028, 1, 31), "1000.00")]
    _, priced, _, nodes = fold(single("K-GAP", price="1000.00", transfer=JANUARY_2026, points=far))
    review = [f for f in priced.findings if f.code == "SFC_REVIEW_REQUIRED"]
    assert [(f.severity, f.subject_key, f.stage, f.detail["reason"]) for f in review] == [
        ("ERROR", f"K-GAP/{LINE}", 4, "SIGNIFICANT_GAP")
    ]
    assert nodes[f"financing_gap_test:K-GAP/{LINE}:-"].params["significant"] == "true"
    # A reviewed judgement that concludes no significant financing or attests a 32-17 exception.
    for judgement, reason in (
        (assessed("K-GAP", significant="false"), "NOT_SIGNIFICANT"),
        (assessed("K-GAP", exception="A"), "EXCEPTION_32_17"),
    ):
        bundle = single(
            "K-GAP", price="1000.00", transfer=JANUARY_2026, points=far, judgements=[judgement]
        )
        _, priced, _, nodes = fold(bundle)
        assert (priced.findings, priced.tp.financing_adjustment.posted) == ((), 0)
        assert nodes[f"financing_gap_test:K-GAP/{LINE}:-"].params["reason"] == reason
    # A draft contract raises no review finding; the adjustment still needs a rate.
    _, priced, _, _ = fold(
        single("K-GAP", price="1000.00", transfer=JANUARY_2026, points=far, activated=False)
    )
    assert [f.code for f in priced.findings] == ["SFC_RATE_MISSING"]
    # POL-046 APPLY: a gap of 12 months or less gives no adjustment and no finding.
    near = [(date(2026, 12, 31), "1000.00")]
    _, priced, _, nodes = fold(
        single("K-NEAR", price="1000.00", transfer=JANUARY_2026, points=near)
    )
    assert (priced.findings, priced.tp.financing_adjustment.posted) == ((), 0)
    assert priced.specialist_targets.financing == ()
    gap = nodes[f"financing_gap_test:K-NEAR/{LINE}:-"]
    assert (gap.params["reason"], gap.params["significant"], gap.value) == (
        "WITHIN_ONE_YEAR",
        "false",
        "364",
    )
    # Without a payment schedule the test is not run; a template requiring the assessment raises
    # SFC_REVIEW_REQUIRED unless the reviewed record exists.
    _, priced, _, nodes = fold(
        single("K-NONE", price="1000.00", transfer=JANUARY_2026, points=[], sfc_required=True)
    )
    assert [(f.code, f.detail["reason"]) for f in priced.findings] == [
        ("SFC_REVIEW_REQUIRED", "NO_PAYMENT_SCHEDULE")
    ]
    assert nodes[f"financing_gap_test:K-NONE/{LINE}:-"].params["reason"] == "NO_PAYMENT_SCHEDULE"
    bundle = single(
        "K-NONE",
        price="1000.00",
        transfer=JANUARY_2026,
        points=[],
        sfc_required=True,
        judgements=[assessed("K-NONE")],
    )
    assert fold(bundle)[1].findings == ()


def test_s04_r11_rate_missing() -> None:
    bundle = single(
        "K-RATE",
        price="121.00",
        transfer=JANUARY_2026,
        points=[(date(2027, 12, 31), "121.00")],
        judgements=[assessed("K-RATE")],
    )
    _, priced, _, _ = fold(bundle)
    assert [
        (f.code, f.severity, f.subject_key, f.detail["obligation_keys"]) for f in priced.findings
    ] == [("SFC_RATE_MISSING", "ERROR", "K-RATE", LINE)]
    assert (priced.tp.financing_adjustment.posted, priced.specialist_targets.financing) == (0, ())
    # A framework default without annual_rate is not an approved override.
    default = [p for p in context(bundle).policies.all() if p.code == RATE_POLICY]
    assert [(p.scope, p.level, "annual_rate" in dict(p.value)) for p in default] == [
        ("GROUP", "DEFAULT", False)
    ]


def ex_26(*payments: tuple[date, str]) -> InputBundle:
    """FASB Example 26 without the return right: 121.00 payable on 31 December 2027 for a product
    transferred on 1 January 2026, CUSTOMER_CREDIT_RATE 0.10 ANNUAL; ``payments`` are the cash
    receipts."""
    return single(
        "K-EX26",
        price="121.00",
        transfer=JANUARY_2026,
        points=[(date(2027, 12, 31), "121.00")],
        judgements=[assessed("K-EX26")],
        rate={"annual_rate": "0.10", "basis": "CUSTOMER_CREDIT_RATE", "compounding": "ANNUAL"},
        extra=[
            (
                "PAYMENT_RECEIVED",
                on,
                {
                    "receipt_reference": f"R-{on.isoformat()}",
                    "amount": Decimal(amount),
                    "receipt_date": on,
                },
            )
            for on, amount in payments
        ],
    )


def test_s04_r12_schedule_unsettled() -> None:
    _, priced, _, _ = fold(ex_26((date(2026, 6, 30), "121.00")))
    (finding,) = priced.findings
    assert (finding.code, finding.severity, finding.subject_key, finding.event_key) == (
        "SFC_SCHEDULE_UNSETTLED",
        "ERROR",
        f"K-EX26@{ENTITY}",
        "K-EX26/EV-000003",
    )
    assert (finding.detail["received"], finding.detail["available"]) == ("121", "105")
    # Paying the scheduled amount on its date settles the schedule (S04-INV-04).
    _, priced, _, _ = fold(ex_26((date(2027, 12, 31), "121.00")))
    assert priced.findings == ()
    balance = series(priced, "financed_balance")
    assert balance["FY2027-P11"].value == 12_008  # 110.00 + 11 × 11.00 ÷ 12
    settled = balance["FY2027-P12"]
    assert settled.value == 0 and settled.exact is not None
    assert abs(settled.exact) < Fraction(1, 100)
    assert series(priced, "financing_interest_cum")["FY2027-P12"].value == 2_100
    # CHK-137 settles at the 60th instalment.
    _, priced, _, _ = fold(instalments())
    final = series(priced, "financed_balance")["FY2030-P12"]
    assert (final.value, final.exact) == (0, Fraction(0))


def test_s04_r12_month_count_calendar_month_ends() -> None:
    # A payment on 31 January 2026 after a transfer on 1 January 2026 has n = 1.
    bundle = single(
        "K-M1",
        price="1010.00",
        transfer=JANUARY_2026,
        points=[(date(2026, 1, 31), "1010.00")],
        judgements=[assessed("K-M1")],
        rate={"annual_rate": "0.12", "basis": "CUSTOMER_CREDIT_RATE", "compounding": "MONTHLY"},
        policies={"sfc.one_year_expedient": "DO_NOT_APPLY"},
    )
    _, priced, _, nodes = fold(bundle)
    csp = nodes[f"cash_selling_price:K-M1/{LINE}:-"]
    assert (csp.params["months"], csp.params["counts"], csp.value) == ("1", "1", "1000.00")
    assert nodes[f"financing_gap_test:K-M1/{LINE}:-"].params["reason"] == "EXPEDIENT_NOT_APPLIED"
    # CHK-137: instalment k has n = k.
    _, _, _, nodes = fold(instalments())
    csp = nodes[f"cash_selling_price:{FIN}/{LINE}:-"]
    assert csp.params["counts"] == ",".join(str(k) for k in range(1, 61))
    assert csp.value == "848346.53"
    # A floor of whole months (n = k − 1) would give 856,830.00; the engine does not use it.
    floor = sum(
        (Fraction(18_871) / Fraction(101, 100) ** (k - 1) for k in range(1, 61)), Fraction(0)
    )
    assert money.format_money(money.round_half_up(floor, 2), 2) == "856830.00"
    # CHK-136: the advance of 1 January 2026 for a transfer on 1 January 2028 has n = 24, and
    # ⌊24 ÷ 12⌋ = 2 whole years under ANNUAL.
    for compounding, counts in (("MONTHLY", "24"), ("ANNUAL", "2")):
        _, _, _, nodes = fold(advance(compounding))
        csp = nodes[f"cash_selling_price:{ADV}/{LINE}:-"]
        assert (csp.params["months"], csp.params["counts"]) == ("24", counts)


# --- EX-04-H accretion while expected returns exclude the whole consideration -------------------

EX26R = "C-EX26R"


def ex_04_h(window: date) -> InputBundle:
    return single(
        EX26R,
        price="121.00",
        transfer=JANUARY_2026,
        points=[(date(2027, 12, 31), "121.00")],
        judgements=[assessed(EX26R)],
        rate={"annual_rate": "0.10", "basis": "CUSTOMER_CREDIT_RATE", "compounding": "ANNUAL"},
        sfc_required=True,
        returnable=True,
        estimates=[return_rate(EX26R, window)],
        extra=[
            (
                "DELIVERY_RECORDED",
                JANUARY_2026,
                {"obligation_key": LINE, "quantity": Decimal("1"), "trigger": "CONTROL_TRANSFER"},
            )
        ],
        ssp=True,
    )


def test_ex_04_h_accretion_suspended_while_returns_exclude_consideration() -> None:
    _, priced, allocated, nodes = fold(ex_04_h(date(2026, 3, 31)))
    assert priced.findings == ()
    assert allocated is not None and allocated.findings == ()
    (tp,) = allocated.tp_history
    assert (tp.financing_adjustment.posted, tp.expected_returns.posted, tp.total.posted) == (
        -2_100,
        -10_000,
        0,
    )
    assert tp.allocation_basis.posted == 10_000
    csp = nodes[f"cash_selling_price:{EX26R}/{LINE}:-"]
    assert (csp.value, csp.params["months"], csp.params["counts"]) == ("100.00", "24", "2")
    assert (csp.params["annual_rate"], csp.params["compounding"]) == ("0.1", "ANNUAL")
    interest = series(allocated_or(priced, allocated), "financing_interest_cum")
    assert [interest[f"FY2026-P{m:02d}"].value for m in (1, 2, 3)] == [0, 0, 0]
    node = nodes[f"financing_interest_cum:{EX26R}@{ENTITY}:FY2026-P03"]
    # D-87 L6-5-Q-25: E = 0 from the window end date, so L is 31 March 2026.
    assert (node.value, node.params["suspended_until"]) == ("0.00", "2026-03-31")
    assert interest["FY2026-P04"].value == 95  # April 2026: round(21 × (10 ÷ 12) ÷ 18.5)
    assert interest["FY2026-P12"].value == 851  # months 4 to 12: round(21 × 7.5 ÷ 18.5)
    assert interest["FY2027-P11"].value == 1_996
    assert interest["FY2027-P12"].value - interest["FY2027-P11"].value == 104
    assert interest["FY2027-P12"].value - interest["FY2026-P12"].value == 1_249  # months 13 to 24
    assert interest["FY2027-P12"].value == 2_100
    april = nodes[f"financing_interest_cum:{EX26R}@{ENTITY}:FY2026-P04"]
    assert (april.params["suspended_interest"], april.params["suspended_until"]) == (
        "21",
        "2026-03-31",
    )
    # With the window ending on 20 January 2026 no month end falls on or before L = 20 January.
    _, priced, allocated, nodes = fold(ex_04_h(date(2026, 1, 20)))
    assert allocated is not None and allocated.findings == ()
    assert allocated.tp_history[0].financing_adjustment.posted == -2_100
    interest = series(priced, "financing_interest_cum")
    assert [interest[p].value for p in ("FY2026-P01", "FY2026-P12", "FY2027-P12")] == [
        83,
        1_000,
        2_100,
    ]
    assert all(
        "suspended_until" not in node.params
        for node_id, node in nodes.items()
        if node_id.startswith("financing_interest_cum:")
    )


def allocated_or(priced: PricedState, allocated: AllocatedState | None) -> PricedState:
    """The priced state; the allocated state carries the same specialist targets."""
    assert allocated is None or allocated.specialist_targets == priced.specialist_targets
    return priced


def test_s04_r12a_advance_payment_never_suspended() -> None:
    _, priced, _, nodes = fold(advance(window=date(2028, 3, 31)))
    assert priced.returns_pending and priced.findings == ()
    interest = series(priced, "financing_interest_cum")
    assert (interest["FY2026-P01"].value, interest["FY2027-P12"].value) == (2_000, 50_864)
    interest_nodes = [n for i, n in nodes.items() if i.startswith("financing_interest_cum:")]
    assert interest_nodes and all("suspended_until" not in n.params for n in interest_nodes)
