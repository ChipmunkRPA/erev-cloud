"""Stage 03 options, warranties, principal or agent, licences and time triggers.

ENGINE_SPEC S03-R-07 to S03-R-10, §3.4 (S03-INV-04, S03-INV-05, ``PRINCIPAL_AGENT_NOT_ASSESSED``,
``pob.option_ssp.v1``, ``pob.agent_net.v1``), §3.5 EX-03-B to EX-03-E, CV-27; POLICIES ALG-05
§2.6.1 (CHK-054); BUILD_SPEC ENA-4. Bundles come from ``support.bundles`` (DG-ENG-11); no database
fixture (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION, dates
from erev_engine.bundle import (
    ContractInput,
    EstimateVersionInput,
    EventInput,
    InputBundle,
    JudgementInput,
    MaterialRightInput,
    ProductInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
    TimeTrigger,
)
from erev_engine.enums import (
    BookCode,
    LicenceNature,
    ObligationKind,
    PrincipalAgent,
    RecognitionMethod,
    SatisfactionPattern,
    WarrantyType,
)
from erev_engine.errors import EngineError
from erev_engine.stages import (
    s01_canonicalize,
    s02_contract_identification,
    s03_pob_builder,
    s04_transaction_price,
    s05_allocation,
)
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder import PobDraft, PobState, WarrantyAccrual
from erev_engine.stages.s04_transaction_price import PricedState
from erev_engine.stages.state import AllocatedState, BookContext, PolicyResolver
from erev_engine.trace import TraceBuilder, TraceNode
from support import bundles

CONTRACT = "K-01"
INCEPTION = date(2026, 1, 1)
END = date(2026, 12, 31)
ZERO = "0" * 64
SSP_BOOK = "SSP-MAIN"
LIKELIHOOD = f"{CONTRACT}/LIKELIHOOD-1"
BOTH_BOOKS = ("ASC606", "IFRS15")

PolicyValue = str | Mapping[str, str]


def template(code: str = "TPL-PIT", **changes: object) -> TemplateInput:
    base = TemplateInput(
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
        effective_from=date(2020, 1, 1),
        effective_to=None,
    )
    return dataclasses.replace(base, **changes)


def product(code: str, template_code: str = "TPL-PIT", **changes: object) -> ProductInput:
    return dataclasses.replace(
        bundles.product(code, template_code=template_code, family=None), **changes
    )


def line(
    key: str,
    product_code: str,
    price: str,
    *,
    quantity: str = "1",
    start: date = INCEPTION,
    end: date = END,
    **members: object,
) -> dict[str, object]:
    base = bundles.booking_line(
        key, product_code=product_code, quantity=quantity, total_price=price, start=start, end=end
    )
    return {**base, **members}


def booked(*lines: Mapping[str, object], on: date = INCEPTION) -> EventInput:
    keys = [str(item["obligation_key"]) for item in lines]
    payload = {"lines": list(lines)}
    return bundles.event(CONTRACT, 1, "CONTRACT_BOOKED", on, payload, obligation_keys=keys)


def activated(stream: int, on: date = INCEPTION) -> EventInput:
    return bundles.event(CONTRACT, stream, "CONTRACT_ACTIVATED", on, {"checklist": {}})


def entry(product_code: str, point: str) -> SspEntryInput:
    return SspEntryInput(
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


def ssp_book(*entries: SspEntryInput) -> SspVersionInput:
    return SspVersionInput(
        ssp_book_code=SSP_BOOK,
        version_key=f"{SSP_BOOK}@v1",
        version_no=1,
        resolution_mode="EFFECTIVE_DATE",
        legacy_version_label=None,
        effective_from_date=date(2020, 1, 1),
        effective_to_date=None,
        status="APPROVED",
        approved_at=datetime(2020, 1, 1, tzinfo=UTC),
        content_sha256=ZERO,
        scope_entity_code=None,
        scope_currency=None,
        scope_channel=None,
        scope_segment=None,
        entries=tuple(sorted(entries, key=lambda e: e.product_code)),
    )


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


def header(**changes: object) -> ContractInput:
    inception = changes.pop("inception", INCEPTION)
    assert isinstance(inception, date)
    return dataclasses.replace(bundles.contract(CONTRACT, inception=inception), **changes)


def world(
    *events: EventInput,
    products: Iterable[ProductInput],
    templates: Iterable[TemplateInput],
    contract: ContractInput | None = None,
    ssp: Sequence[SspVersionInput] = (),
    estimates: Sequence[EstimateVersionInput] = (),
    books: tuple[str, ...] = ("ASC606",),
    start: date = INCEPTION,
    months: int = 24,
    policies: Mapping[str, Mapping[str, PolicyValue]] | None = None,
) -> InputBundle:
    calendar = bundles.entity(start=start, months=months, books=books)
    headers = (contract or header(),)
    overrides = policies or {}
    book_inputs = []
    for code in books:
        base = bundles.book(code, entity=calendar)
        values = overrides.get(code, {})
        policy_rows = tuple(
            dataclasses.replace(policy, value=values[policy.code])
            if policy.code in values
            else policy
            for policy in base.policies
        )
        book_inputs.append(dataclasses.replace(base, policies=policy_rows))
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2027, 12, 31, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=tuple(book_inputs),
        entities=(calendar,),
        group=bundles.group(headers, products=tuple(products)),
        contracts=headers,
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=tuple(ssp),
        pob_template_versions=tuple(
            sorted(templates, key=lambda t: (t.template_code, t.version_no))
        ),
        rule_set_versions=(),
        estimate_versions=tuple(sorted(estimates, key=lambda v: (v.estimate_key, v.version_no))),
        fx_rates=(),
        posted=(),
    )


def context(value: InputBundle, book_code: str = "ASC606") -> BookContext:
    book = next(b for b in value.books if b.book_code == book_code)
    return BookContext(
        book_code=BookCode(book_code),
        framework=BookCode(book_code),
        currencies=value.currencies,
        txn_currency=value.group.transaction_currency,
        entities={entity.code: entity for entity in value.entities},
        horizon={entity.code: entity.periods[-1].period_key for entity in value.entities},
        policies=PolicyResolver(book.policies),
        mapping=book.account_mapping,
        trigger=value.trigger,
        tenant_preset=value.tenant_preset,
    )


def identify(value: InputBundle, book_code: str = "ASC606") -> tuple[BookContext, IdentifiedState]:
    ctx = context(value, book_code)
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    return ctx, s02_contract_identification.run(
        ctx, cb, TraceBuilder(engine_version=ENGINE_VERSION)
    )


def fold(
    value: InputBundle, book_code: str = "ASC606"
) -> tuple[PobState, PricedState, AllocatedState | None, dict[str, TraceNode]]:
    """Stages 01 to 05 with one trace builder for stages 03 to 05 (§0.3); stage 05 runs only
    when the bundle carries an SSP book."""
    ctx, identified = identify(value, book_code)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    pob = s03_pob_builder.run(ctx, identified, tb)
    priced = s04_transaction_price.run(ctx, pob, tb)
    allocated = s05_allocation.run(ctx, priced, tb) if value.ssp_versions else None
    return pob, priced, allocated, {node.id: node for node in tb.build(root_measures={}).nodes}


def pob_only(
    value: InputBundle, book_code: str = "ASC606"
) -> tuple[PobState, dict[str, TraceNode]]:
    ctx, identified = identify(value, book_code)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    pob = s03_pob_builder.run(ctx, identified, tb)
    return pob, {node.id: node for node in tb.build(root_measures={}).nodes}


def by_key(st: PobState) -> dict[str, PobDraft]:
    return {ob.obligation_key: ob for ob in st.obligations}


# --- S03-R-07 material rights (EX-03-B; CHK-054) ------------------------------------------------


def voucher(ratio: str = "0.30", *, expiry: date | None = None) -> MaterialRightInput:
    return MaterialRightInput(
        obligation_key="POB-02",
        option_type="DISCOUNT_VOUCHER",
        incremental_discount_ratio=Decimal(ratio),  # 40 % voucher less 10 % without the contract
        is_discount_available_without_contract=True,
        expected_purchase_amount=Decimal("50.00"),
        currency="USD",
        ssp_method="DISCOUNT_X_LIKELIHOOD",
        expiry_date=expiry,
        likelihood_estimate_key=LIKELIHOOD,
        is_legacy_quantity_ssp_dollars=False,
    )


def ex_03_b(ratio: str = "0.30", rate: str = "0.80", *, expiry: date | None = None) -> InputBundle:
    events = (
        booked(line("POB-01", "SKU-A", "100.00"), line("POB-02", "VOUCHER", "0.00")),
        bundles.event(
            CONTRACT, 2, "ESTIMATE_CHANGED", INCEPTION, {"estimate_version_id": f"{LIKELIHOOD}@v1"}
        ),
    )
    return world(
        *events,
        products=[product("SKU-A"), product("VOUCHER", "TPL-MR")],
        templates=[
            template(),
            template(
                "TPL-MR", obligation_kind="MATERIAL_RIGHT", recognition_method="UNITS_DELIVERED"
            ),
        ],
        contract=header(material_rights=(voucher(ratio, expiry=expiry),)),
        ssp=[ssp_book(entry("SKU-A", "100"), entry("VOUCHER", "0"))],
        estimates=[likelihood(rate)],
    )


def test_chk_054_option_ssp() -> None:
    value = ex_03_b()
    ctx = context(value)
    assert ctx.policies.value("material_right.ssp_method") == "DISCOUNT_X_LIKELIHOOD"  # POL-026
    pob, _, allocated, nodes = fold(value)
    assert pob.findings == ()
    option = by_key(pob)["POB-02"]
    assert option.material_right == voucher()
    assert option.option_ssp == Fraction(12)  # 50.00 × (0.40 − 0.10) × 0.80; S03-INV-04
    node = nodes["option_ssp:K-01/POB-02:-"]
    assert (node.value, node.formula_id) == ("12.00", "pob.option_ssp.v1")
    assert (
        node.params["method"],
        node.params["expected_purchase_amount"],
        node.params["incremental_discount_ratio"],
        node.params["likelihood"],
    ) == ("DISCOUNT_X_LIKELIHOOD", "50", "0.3", "0.8")
    assert "option_ssp:K-01/POB-01:-" not in nodes
    # EX-03-B: stage 05 allocates 100.00 over weights 100 and 12.
    assert allocated is not None and allocated.findings == ()
    posted = [ob.original_allocation.a_posted for ob in allocated.obligations]
    assert posted == [8_929, 1_071]
    option_state = next(ob for ob in allocated.obligations if ob.obligation_key == "POB-02")
    assert option_state.material_right is not None
    assert option_state.material_right.option_ssp == 12

    # 606-10-55-43: no incremental discount, no material right and no obligation.
    unmaterial, _, _, nodes = fold(ex_03_b("0"))
    assert sorted(by_key(unmaterial)) == ["POB-01"]
    assert unmaterial.excluded == (("K-01/POB-02", "S03-R-07"),)
    zero = nodes["option_ssp:K-01/POB-02:-"]
    assert (zero.value, zero.params["reason"]) == ("0.00", "NOT_MATERIAL")

    # L outside [0, 1] is NON_FINITE_AMOUNT (ERROR) at stage 03.
    invalid, _ = pob_only(ex_03_b(rate="1.20"))
    assert [(f.code, f.severity, f.subject_key, f.stage) for f in invalid.findings] == [
        ("NON_FINITE_AMOUNT", "ERROR", "K-01/POB-02", 3)
    ]


def test_cv_27_material_right_expiry_trigger() -> None:
    pob, _, allocated, _ = fold(ex_03_b(expiry=date(2026, 12, 31)))
    assert pob.time_triggers == (
        TimeTrigger("MATERIAL_RIGHT_EXPIRY", date(2026, 12, 31), "K-01/POB-02"),
    )
    assert {trigger.kind for trigger in pob.time_triggers} == {"MATERIAL_RIGHT_EXPIRY"}
    assert allocated is not None and allocated.time_triggers == pob.time_triggers
    open_ended, _ = pob_only(ex_03_b())
    assert open_ended.time_triggers == ()


# --- S03-R-08 warranties (EX-03-E; CHK-134) ------------------------------------------------------


def ex_03_e(
    cost: str | None = "200.00", policies: Mapping[str, Mapping[str, PolicyValue]] | None = None
) -> InputBundle:
    statutory = JudgementInput(
        "J-WTY-1",
        "WARRANTY_TYPE",
        CONTRACT,
        None,
        {"obligation_key": "WTY-12", "warranty_type": "ASSURANCE"},
    )
    events = (
        booked(
            line("EQ-1", "EQUIP", "10500.00"),
            line("WTY-12", "STATWTY", "0.00", bundle_parent_obligation_key="EQ-1"),
            line("WTY-24", "EXTWTY", "0.00", start=date(2027, 1, 1), end=date(2027, 12, 31)),
        ),
    )
    equipment = product(
        "EQUIP", "TPL-EQUIP", assurance_cost_per_unit=None if cost is None else Decimal(cost)
    )
    return world(
        *events,
        products=[equipment, product("EXTWTY", "TPL-WTY"), product("STATWTY", "TPL-WTY")],
        templates=[
            template("TPL-EQUIP", warranty_type="ASSURANCE"),
            template("TPL-WTY", obligation_kind="SERVICE_WARRANTY", warranty_type="SERVICE"),
        ],
        contract=header(judgements=(statutory,)),
        ssp=[ssp_book(entry("EQUIP", "10000"), entry("EXTWTY", "1000"), entry("STATWTY", "0"))],
        policies=policies,
    )


def test_ex_03_e_warranty_split() -> None:
    pob, _, allocated, _ = fold(ex_03_e())
    assert pob.findings == ()
    obligations = by_key(pob)
    assert sorted(obligations) == ["EQ-1", "WTY-24"]
    equipment, extended = obligations["EQ-1"], obligations["WTY-24"]
    assert (equipment.obligation_kind, equipment.satisfaction_pattern, equipment.warranty_type) == (
        ObligationKind.STANDARD,
        SatisfactionPattern.POINT_IN_TIME,
        WarrantyType.ASSURANCE,
    )
    assert (
        extended.obligation_kind,
        extended.satisfaction_pattern,
        extended.recognition_method,
        extended.start_date,
        extended.end_date,
    ) == (
        ObligationKind.SERVICE_WARRANTY,
        SatisfactionPattern.OVER_TIME,
        RecognitionMethod.TIME_ELAPSED,
        date(2027, 1, 1),  # month 13
        date(2027, 12, 31),  # month 24
    )
    # The statutory assurance warranty is no obligation; the product carries the cost rate.
    assert pob.excluded == (("K-01/WTY-12", "S03-R-08"),)
    assert pob.warranty_accruals == (WarrantyAccrual("K-01/EQ-1", "EQUIP", Fraction(200), None),)
    assert allocated is not None and allocated.findings == ()
    posted = {ob.obligation_key: ob.original_allocation.a_posted for ob in allocated.obligations}
    assert posted == {"EQ-1": 954_545, "WTY-24": 95_455}  # 9,545.45 and 954.55
    assert next(
        ob.assurance_cost_per_unit for ob in allocated.obligations if ob.obligation_key == "EQ-1"
    ) == Fraction(200)

    uncosted, _ = pob_only(ex_03_e(cost=None))
    assert uncosted.warranty_accruals == (
        WarrantyAccrual("K-01/EQ-1", "EQUIP", None, "NO_COST_RATE"),
    )
    external = {
        "ASC606": {"pob.assurance_warranty_accrual": "EXTERNAL"},
    }
    outside, _ = pob_only(ex_03_e(policies=external))
    assert outside.warranty_accruals == ()
    assert sorted(by_key(outside)) == ["EQ-1", "WTY-24"]


# --- S03-R-09 principal versus agent (EX-03-C) ---------------------------------------------------


def marketplace(outcome: Mapping[str, str], **product_changes: object) -> InputBundle:
    record = JudgementInput(
        "J-PA-1", "PRINCIPAL_AGENT", CONTRACT, None, {"obligation_key": "MKT-1", **outcome}
    )
    return world(
        booked(line("MKT-1", "MARKET", "500.00")),
        products=[product("MARKET", **product_changes)],
        templates=[template()],
        contract=header(judgements=(record,)),
    )


def test_ex_03_c_agent_net() -> None:
    commission = {"conclusion": "AGENT", "gross_to_net_basis": "COMMISSION_RATE", "rate": "0.10"}
    pob, priced, _, nodes = fold(marketplace(commission))
    assert pob.findings == ()
    order = by_key(pob)["MKT-1"]
    assert (order.principal_agent, order.stated_price, order.original_stated_price) == (
        PrincipalAgent.AGENT,
        Fraction(50),
        Fraction(50),
    )
    assert order.gross_amount_memo == Fraction(500)
    assert order.gross_to_net is not None
    assert (order.gross_to_net["retained"], order.gross_to_net["supplier"]) == ("50", "450")
    retained = nodes["stated_price:K-01/MKT-1:-"]
    assert (retained.value, retained.formula_id, retained.params["role"]) == (
        "50.00",
        "pob.agent_net.v1",
        "retained",
    )
    gross = nodes["gross_amount_memo:K-01/MKT-1:-"]
    assert (gross.value, gross.formula_id) == ("500.00", "pob.agent_net.v1")
    # 606-10-32-2: the supplier share 450.00 is excluded from the transaction price.
    assert (priced.tp.fixed.posted, priced.tp.total.posted) == (5_000, 5_000)

    fixed_fee, _ = pob_only(
        marketplace({"conclusion": "AGENT", "gross_to_net_basis": "FIXED_FEE", "amount": "60.00"})
    )
    assert by_key(fixed_fee)["MKT-1"].stated_price == Fraction(60)
    supplier_cost, _ = pob_only(
        marketplace(
            {"conclusion": "AGENT", "gross_to_net_basis": "SUPPLIER_COST", "amount": "420.00"}
        )
    )
    assert by_key(supplier_cost)["MKT-1"].stated_price == Fraction(80)
    with pytest.raises(EngineError) as raised:  # S03-INV-05: 0 ≤ R ≤ P
        pob_only(
            marketplace(
                {"conclusion": "AGENT", "gross_to_net_basis": "FIXED_FEE", "amount": "600.00"}
            )
        )
    assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert raised.value.detail["invariant"] == "S03-INV-05"


def test_s03_r09_principal_agent_not_assessed() -> None:
    def assessed(*events: EventInput) -> PobState:
        value = world(
            booked(line("POB-01", "SKU-X", "300.00")),
            *events,
            products=[product("SKU-X", principal_agent="NOT_ASSESSED")],
            templates=[template()],
        )
        return pob_only(value)[0]

    active = assessed(activated(2))
    assert [(f.code, f.severity, f.subject_key, f.stage) for f in active.findings] == [
        ("PRINCIPAL_AGENT_NOT_ASSESSED", "ERROR", "K-01/POB-01", 3)
    ]
    draft = assessed()
    assert draft.findings == ()
    assert by_key(draft)["POB-01"].principal_agent == PrincipalAgent.NOT_ASSESSED


# --- S03-R-10 licences (EX-03-D) -----------------------------------------------------------------


LICENCE_START = date(2021, 1, 1)


def ex_03_d(judgements: Sequence[JudgementInput] = ()) -> InputBundle:
    delivery = bundles.event(
        CONTRACT,
        2,
        "DELIVERY_RECORDED",
        LICENCE_START,
        {"obligation_key": "L-1", "quantity": Decimal("1"), "trigger": "DELIVERY"},
        obligation_keys=["L-1"],
    )
    events = (
        booked(
            line("L-1", "REC", "240000.00", start=LICENCE_START, end=date(2022, 12, 31)),
            on=LICENCE_START,
        ),
        delivery,
    )
    return world(
        *events,
        products=[product("REC", "TPL-LIC")],
        templates=[template("TPL-LIC", obligation_kind="LICENCE", licence_nature="FUNCTIONAL")],
        contract=header(inception=LICENCE_START, judgements=tuple(judgements)),
        books=BOTH_BOOKS,
        start=LICENCE_START,
        months=48,
    )


def test_ex_03_d_licence_renewal_start() -> None:
    value = ex_03_d()
    renewal = line("L-2", "REC", "240000.00", start=date(2023, 1, 1), end=date(2024, 12, 31))
    agreed = date(2021, 12, 31)  # renewed before the end of the current term
    starts: dict[str, date | None] = {}
    for book_code in BOTH_BOOKS:
        ctx, identified = identify(value, book_code)
        pob = s03_pob_builder.run(ctx, identified, TraceBuilder(engine_version=ENGINE_VERSION))
        original = by_key(pob)["L-1"]
        assert (original.licence_nature, original.satisfaction_pattern) == (
            LicenceNature.FUNCTIONAL,
            SatisfactionPattern.POINT_IN_TIME,
        )  # right to use
        assert original.recognition_start_date == LICENCE_START  # max(start, availability)
        tb = TraceBuilder(engine_version=ENGINE_VERSION)
        (added,) = s03_pob_builder.build_lines(ctx, identified, [renewal], agreed, tb, renewal=True)
        starts[book_code] = added.recognition_start_date
        (plain,) = s03_pob_builder.build_lines(
            ctx, identified, [renewal], agreed, TraceBuilder(engine_version=ENGINE_VERSION)
        )
        assert plain.recognition_start_date == date(2023, 1, 1)
    # POL-025: RENEWAL_PERIOD_START (ASC606); LATER_OF_AGREEMENT_AND_AVAILABILITY (IFRS15).
    assert starts == {"ASC606": date(2023, 1, 1), "IFRS15": agreed}

    access = ex_03_d(
        [
            JudgementInput(
                "J-LIC-1",
                "LICENCE_NATURE",
                CONTRACT,
                "ASC606",
                {"obligation_key": "L-1", "nature": "SYMBOLIC"},
            ),
            JudgementInput(
                "J-LIC-2",
                "LICENCE_NATURE",
                CONTRACT,
                "IFRS15",
                {
                    "obligation_key": "L-1",
                    "nature": "FUNCTIONAL",
                    "activities_significantly_affect_ip": "true",
                },
            ),
        ]
    )
    for book_code in BOTH_BOOKS:
        st, _ = pob_only(access, book_code)
        licence = by_key(st)["L-1"]
        assert (licence.satisfaction_pattern, licence.recognition_method) == (
            SatisfactionPattern.OVER_TIME,
            RecognitionMethod.TIME_ELAPSED,
        )  # right to access over the licence period


def test_s03_specialist_policy_periods() -> None:
    """POL-022 is period-scoped (pin P): the accrual policy is read in the inception period."""
    value = ex_03_e()
    ctx = context(value)
    entity = value.entities[0]
    period = dates.period_of(entity, INCEPTION).period_key
    policy = ctx.policies.value("pob.assurance_warranty_accrual", entity=entity.code, period=period)
    assert policy == "ENGINE"


# --- S03-R-10 rev 1.6: the 606-10-55-62 functional-IP exception (D-91 gaps (viii); ENA-4b) --------

from erev_engine import compute  # noqa: E402

LICENCE_A = "functionality_expected_to_change_substantively"
LICENCE_B = "customer_required_to_use_updated_ip"


def licence_world(
    judgements: Sequence[JudgementInput],
    *,
    availability: date = INCEPTION,
    books: tuple[str, ...] = ("ASC606",),
    months: int = 12,
) -> InputBundle:
    """A 12,000.00 annual FUNCTIONAL licence delivered on ``availability`` (55-58C) under the
    MONTHLY_EVEN convention (POL-090)."""
    delivery = bundles.event(
        CONTRACT,
        3,
        "DELIVERY_RECORDED",
        availability,
        {"obligation_key": "L-1", "quantity": Decimal("1"), "trigger": "DELIVERY"},
        obligation_keys=["L-1"],
    )
    return world(
        booked(line("L-1", "LICENCE", "12000.00", start=INCEPTION, end=END)),
        activated(2),
        delivery,
        products=[product("LICENCE", "TPL-LIC")],
        templates=[
            template(
                "TPL-LIC",
                obligation_kind="LICENCE",
                licence_nature="FUNCTIONAL",
                ratable_convention="MONTHLY_EVEN",
            )
        ],
        contract=header(judgements=tuple(judgements)),
        ssp=[ssp_book(entry("LICENCE", "12000.00"))],
        books=books,
        months=months,
        policies={code: {"recognition.time_convention": "MONTHLY_EVEN"} for code in books},
    )


def licence_record(
    outcome: Mapping[str, str], book: str | None = "ASC606", key: str = "J-LIC"
) -> JudgementInput:
    return JudgementInput(
        key, "LICENCE_NATURE", CONTRACT, book, {"obligation_key": "L-1", **outcome}
    )


def revenue_by_period(value: InputBundle, book_code: str = "ASC606") -> dict[str, int]:
    output = compute(value)
    book = next(item for item in output.books if item.book_code == book_code)
    credits: dict[str, int] = {}
    for intent in book.posting_intents:
        for item in intent.lines:
            if item.account_role == "REVENUE":
                sign = 1 if item.side == "C" else -1
                credits[intent.posting_period_key] = (
                    credits.get(intent.posting_period_key, 0) + sign * item.amount_txn
                )
    return dict(sorted(credits.items()))


def test_s03_r10_functional_ip_meeting_55_62_is_a_right_to_access() -> None:
    """Both criteria true on a reviewed ASC606 record: OVER_TIME TIME_ELAPSED, 100,000 minor a month
    (12,000.00 ÷ 12); a book-less record applies too; availability 1 February gives 109,091 minor in
    the first month (12,000.00 × 1/11) and nothing in January."""
    both = {"nature": "FUNCTIONAL", LICENCE_A: "true", LICENCE_B: "true"}
    for record in (licence_record(both), licence_record(both, book=None)):
        st, _ = pob_only(licence_world([record]))
        licence = by_key(st)["L-1"]
        assert (
            licence.licence_nature,
            licence.satisfaction_pattern,
            licence.recognition_method,
        ) == (
            LicenceNature.FUNCTIONAL,
            SatisfactionPattern.OVER_TIME,
            RecognitionMethod.TIME_ELAPSED,
        )
    monthly = revenue_by_period(licence_world([licence_record(both)]))
    assert monthly == {f"FY2026-P{m:02d}": 100000 for m in range(1, 13)}
    february = revenue_by_period(
        licence_world([licence_record(both)], availability=date(2026, 2, 1))
    )
    assert february["FY2026-P02"] == 109091 and "FY2026-P01" not in february
    assert sum(february.values()) == 1200000


@pytest.mark.parametrize(
    "outcome",
    [
        {"nature": "FUNCTIONAL", LICENCE_A: "true", LICENCE_B: "false"},
        {"nature": "FUNCTIONAL", LICENCE_A: "false", LICENCE_B: "true"},
        {"nature": "FUNCTIONAL", "activities_significantly_affect_ip": "true"},
        {"nature": "FUNCTIONAL"},
    ],
    ids=["only-a", "only-b", "ifrs-flag-only", "no-criteria"],
)
def test_s03_r10_one_criterion_or_the_ifrs_flag_keeps_the_right_to_use(
    outcome: Mapping[str, str],
) -> None:
    """One criterion alone, the IFRS-only activities flag, or no criteria: POINT_IN_TIME, 12,000.00
    in January (the availability); the members are read, never ignored."""
    st, _ = pob_only(licence_world([licence_record(outcome)]))
    licence = by_key(st)["L-1"]
    assert (licence.satisfaction_pattern, licence.recognition_method) == (
        SatisfactionPattern.POINT_IN_TIME,
        RecognitionMethod.POINT_IN_TIME,
    )
    assert revenue_by_period(licence_world([licence_record(outcome)])) == {"FY2026-P01": 1200000}


def test_s03_r10_no_record_and_book_scope() -> None:
    """Without a record the template nature governs (right to use); an IFRS15-scoped record with
    both criteria is not read in the ASC606 book, and the IFRS15 book reads its own activities
    test, not the 55-62 members."""
    none, _ = pob_only(licence_world([]))
    assert by_key(none)["L-1"].satisfaction_pattern == SatisfactionPattern.POINT_IN_TIME
    both_ifrs = licence_record(
        {"nature": "FUNCTIONAL", LICENCE_A: "true", LICENCE_B: "true"}, book="IFRS15"
    )
    value = licence_world([both_ifrs], books=BOTH_BOOKS)
    asc, _ = pob_only(value, "ASC606")
    ifrs, _ = pob_only(value, "IFRS15")
    assert by_key(asc)["L-1"].satisfaction_pattern == SatisfactionPattern.POINT_IN_TIME
    assert by_key(ifrs)["L-1"].satisfaction_pattern == SatisfactionPattern.POINT_IN_TIME


def test_s03_r10_stored_members_are_read_never_ignored() -> None:
    """A member outside true/false, or one 55-62 member without the other, is refused (T-CON-19,
    CV-45) instead of being ignored."""
    with pytest.raises(ValueError, match="neither true nor false"):
        pob_only(
            licence_world(
                [licence_record({"nature": "FUNCTIONAL", LICENCE_A: "yes", LICENCE_B: "true"})]
            )
        )
    with pytest.raises(ValueError, match="answered together"):
        pob_only(licence_world([licence_record({"nature": "FUNCTIONAL", LICENCE_A: "true"})]))
