"""Stage 03 scope routing, repurchase outcomes, elections, measure and legacy templates.

ENGINE_SPEC S03-R-11 to S03-R-18; BUILD_SPEC ENA-5. Bundles come from ``support.bundles``
(DG-ENG-11); no database fixture (DG-TST-18).
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
    BookInput,
    ContractInput,
    EntityInput,
    EventInput,
    InputBundle,
    JudgementInput,
    ProductInput,
    ResolvedPolicyInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.enums import (
    BookCode,
    Distinctness,
    ObligationKind,
    RatableConvention,
    RecognitionMethod,
    SatisfactionPattern,
    ScopeFlag,
)
from erev_engine.stages import s01_canonicalize, s02_contract_identification, s03_pob_builder
from erev_engine.stages.s03_pob_builder import PobDraft, PobState
from erev_engine.stages.state import BookContext, PolicyResolver
from erev_engine.trace import TraceBuilder, TraceNode
from support import bundles

CONTRACT = "K-01"
INCEPTION = date(2026, 1, 1)
END = date(2026, 12, 31)
ZERO = "0" * 64
BOTH_BOOKS = ("ASC606", "IFRS15")
OVER_TIME = {
    "satisfaction_pattern": "OVER_TIME",
    "over_time_criterion": "OT_A",
    "recognition_method": "TIME_ELAPSED",
    "ratable_convention": "DAILY",
}

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
        effective_from=date(2025, 1, 1),
        effective_to=None,
    )
    return dataclasses.replace(base, **changes)


def product(
    code: str, template_code: str | None = "TPL-PIT", *, preopening: bool = False
) -> ProductInput:
    base = bundles.product(code, template_code=template_code, family=None)
    return dataclasses.replace(base, is_franchisor_preopening_service=preopening)


def line(
    key: str,
    product_code: str,
    *,
    price: str = "1000.00",
    quantity: str = "1",
    start: date = INCEPTION,
    end: date = END,
    **members: object,
) -> dict[str, object]:
    base = bundles.booking_line(
        key, product_code=product_code, quantity=quantity, total_price=price, start=start, end=end
    )
    return {**base, **members}


def booked(*lines: Mapping[str, object]) -> EventInput:
    keys = [str(item["obligation_key"]) for item in lines]
    payload = {"lines": list(lines)}
    return bundles.event(CONTRACT, 1, "CONTRACT_BOOKED", INCEPTION, payload, obligation_keys=keys)


def header(**changes: object) -> ContractInput:
    return dataclasses.replace(bundles.contract(CONTRACT, inception=INCEPTION), **changes)


def entry(
    product_code: str,
    point: str | None = None,
    *,
    stratification: str = "",
    distinctness: str = "distinct",
) -> SspEntryInput:
    observable = point is not None
    ranges = (SspRangeInput("NONE", None, None, Decimal(point), None, None, None),) if point else ()
    return SspEntryInput(
        entry_key=f"SSP/{product_code}/{stratification}/-/USD",
        product_code=product_code,
        stratification=stratification,
        region=None,
        channel=None,
        segment=None,
        deal_size_band=None,
        term_band=None,
        currency="USD",
        method="observable" if observable else "legacy_range",
        value_basis="AMOUNT",
        unit_list_price=None if observable else Decimal("300"),
        midpoint_discount_ratio=None if observable else Decimal("0.5"),
        range_ratio=None if observable else Decimal("0"),
        cost_basis=None,
        margin_ratio=None,
        distinctness=distinctness,
        revenue_account_code=None,
        observable_point=None,
        ranges=ranges,
    )


def ssp_version(
    *entries: SspEntryInput, code: str = "SSP-US", label: str | None = None
) -> SspVersionInput:
    return SspVersionInput(
        ssp_book_code=code,
        version_key=f"{code}@v1",
        version_no=1,
        resolution_mode="EFFECTIVE_DATE" if label is None else "BY_LABEL",
        legacy_version_label=label,
        effective_from_date=date(2025, 1, 1) if label is None else None,
        effective_to_date=None,
        status="APPROVED",
        approved_at=datetime(2025, 12, 1, tzinfo=UTC),
        content_sha256=ZERO,
        scope_entity_code=None,
        scope_currency=None,
        scope_channel=None,
        scope_segment=None,
        entries=tuple(sorted(entries, key=lambda e: (e.product_code, e.stratification))),
    )


def points(**values: str) -> SspVersionInput:
    return ssp_version(*(entry(code, value) for code, value in values.items()))


def policy(code: str, scope: str, subject: str, value: str, *, level: str) -> ResolvedPolicyInput:
    return ResolvedPolicyInput(code, scope, subject, value, level, "OVR-TEST", "K")


def book(
    code: str,
    preset: str,
    calendar: EntityInput,
    overrides: Mapping[str, PolicyValue],
    extra: Sequence[ResolvedPolicyInput],
) -> BookInput:
    base = bundles.book(code, preset=preset, entity=calendar)
    policies = [
        dataclasses.replace(p, value=overrides[p.code])
        if p.code in overrides and p.scope == "GROUP"
        else p
        for p in base.policies
    ]
    ordered = sorted([*policies, *extra], key=lambda p: (p.code, p.scope, p.subject_key))
    return dataclasses.replace(base, policies=tuple(ordered))


def bundle(
    *events: EventInput,
    products: Iterable[ProductInput],
    templates: Iterable[TemplateInput] | None = None,
    ssp: Iterable[SspVersionInput] = (),
    contracts: Iterable[ContractInput] | None = None,
    books: tuple[str, ...] = ("ASC606",),
    preset: str = "DEFAULT",
    policies: Mapping[str, Mapping[str, PolicyValue]] | None = None,
    extra: Sequence[ResolvedPolicyInput] = (),
) -> InputBundle:
    calendar = bundles.entity(start=INCEPTION, months=24, books=books)
    headers = tuple(contracts or (header(),))
    overrides = policies or {}
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2026, 12, 31, 23, tzinfo=UTC),
        tenant_preset=preset,
        currencies=bundles.currencies("USD"),
        books=tuple(book(code, preset, calendar, overrides.get(code, {}), extra) for code in books),
        entities=(calendar,),
        group=bundles.group(headers, products=tuple(products)),
        contracts=headers,
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=tuple(ssp),
        pob_template_versions=tuple(
            sorted(templates or (template(),), key=lambda t: (t.template_code, t.version_no))
        ),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def context(value: InputBundle, book_code: str) -> BookContext:
    book_input = next(b for b in value.books if b.book_code == book_code)
    horizon = {}
    for entity in value.entities:
        postable = [
            p for p in entity.periods if dates.period_state(p, book_code) in dates.POSTABLE_STATES
        ]
        if postable:
            horizon[entity.code] = postable[-1].period_key
    return BookContext(
        book_code=BookCode(book_code),
        framework=BookCode(book_code),
        currencies=value.currencies,
        txn_currency=value.group.transaction_currency,
        entities={entity.code: entity for entity in value.entities},
        horizon=horizon,
        policies=PolicyResolver(book_input.policies),
        mapping=book_input.account_mapping,
        trigger=value.trigger,
        tenant_preset=value.tenant_preset,
    )


def fold(value: InputBundle, book_code: str = "ASC606") -> tuple[PobState, dict[str, TraceNode]]:
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    ctx = context(value, book_code)
    identified = s02_contract_identification.run(
        ctx, cb, TraceBuilder(engine_version=ENGINE_VERSION)
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    st = s03_pob_builder.run(ctx, identified, tb)
    return st, {node.id: node for node in tb.build(root_measures={}).nodes}


def by_key(st: PobState) -> dict[str, PobDraft]:
    return {obligation.subject_key: obligation for obligation in st.obligations}


def test_s03_r11_scope_routing() -> None:
    events = booked(
        line("POB-01", "MAINT", price="2500.00"),
        line(
            "LEASE-1",
            "EQUIP",
            price="7500.00",
            scope_flag="LEASE_842",
            out_of_scope_amount=Decimal("7500.00"),
        ),
        line(
            "INS-1",
            "COVER",
            price="200.00",
            scope_flag="INSURANCE_944",
            out_of_scope_amount=Decimal("200.00"),
        ),
    )
    st, nodes = fold(
        bundle(events, products=[product("COVER"), product("EQUIP"), product("MAINT")])
    )
    assert st.findings == ()
    obligations = by_key(st)
    assert sorted(obligations) == ["K-01/LEASE-1", "K-01/POB-01"]
    lease = obligations["K-01/LEASE-1"]  # PT-09: an allocation target that is routed out
    assert (lease.scope_flag, lease.routed_out, lease.stated_price) == (
        ScopeFlag.LEASE_842,
        True,
        Fraction(7500),
    )
    assert obligations["K-01/POB-01"].routed_out is False
    assert [(d.subject_key, d.scope_flag, d.out_of_scope_amount) for d in st.routed_out] == [
        ("K-01/INS-1", ScopeFlag.INSURANCE_944, Fraction(200))
    ]
    assert "stated_price:K-01/INS-1:-" not in nodes


def test_s03_r12_repurchase_lease_outcome() -> None:
    judgements = (
        JudgementInput(
            "J-01",
            "REPURCHASE_CLASSIFICATION",
            CONTRACT,
            None,
            {"obligation_key": "POB-01", "outcome": "LEASE"},
        ),
        JudgementInput(
            "J-02",
            "REPURCHASE_CLASSIFICATION",
            "K-01/POB-02",
            None,
            {"obligation_key": "POB-02", "outcome": "RIGHT_OF_RETURN"},
        ),
    )
    events = booked(line("POB-01", "VESSEL"), line("POB-02", "PARTS", price="300.00"))
    value = bundle(
        events,
        products=[product("PARTS"), product("VESSEL")],
        contracts=[header(judgements=judgements)],
    )
    st, _ = fold(value)
    leased, returnable = by_key(st)["K-01/POB-01"], by_key(st)["K-01/POB-02"]
    assert (leased.scope_flag, leased.routed_out, leased.repurchase_outcome) == (
        ScopeFlag.LEASE_842,
        True,
        "LEASE",
    )
    assert (returnable.scope_flag, returnable.routed_out, returnable.repurchase_outcome) == (
        ScopeFlag.IN_SCOPE_606,
        False,
        "RIGHT_OF_RETURN",
    )
    assert st.routed_out == ()


def test_s03_r13_immaterial_promise_candidates() -> None:
    events = booked(
        line("POB-01", "HW", price="9800.00"),
        line("POB-02", "MANUAL", price="50.00"),
        line("MR-1", "VOUCHER", price="0.00"),
    )
    products = [product("HW"), product("MANUAL"), product("VOUCHER", "TPL-MR")]
    templates = [
        template(),
        template("TPL-MR", obligation_kind="MATERIAL_RIGHT", recognition_method="UNITS_DELIVERED"),
    ]
    relief = {"option": "APPLY_RELIEF", "immaterial_threshold_pct": "0.02"}
    value = bundle(
        events,
        products=products,
        templates=templates,
        books=BOTH_BOOKS,
        policies={"ASC606": {"pob.immaterial_promise_relief": relief}},
    )
    asc, _ = fold(value, "ASC606")
    assert asc.immaterial_candidates == ("K-01/POB-01", "K-01/POB-02")
    assert [(o.obligation_key, o.immaterial_threshold_pct) for o in asc.obligations] == [
        ("MR-1", None),  # 606-10-25-16B: never an option
        ("POB-01", Fraction(2, 100)),
        ("POB-02", Fraction(2, 100)),
    ]
    ifrs, _ = fold(value, "IFRS15")  # POLICIES §6.2 row 3: ASSESS_ALL
    assert ifrs.immaterial_candidates == ()
    assert all(o.immaterial_threshold_pct is None for o in ifrs.obligations)

    literal = bundle(
        events,
        products=products,
        templates=templates,
        policies={"ASC606": {"pob.immaterial_promise_relief": "APPLY_RELIEF"}},
    )
    st, _ = fold(literal)
    assert {o.immaterial_threshold_pct for o in st.obligations} == {None, Fraction(1, 100)}


def test_s03_r14_shipping_election() -> None:
    freight = template("TPL-SHIP", obligation_kind="SHIPPING")
    products = [product("FREIGHT", "TPL-SHIP"), product("HW"), product("SW")]
    events = booked(line("POB-01", "HW", price="1000.00"), line("SHIP-1", "FREIGHT", price="50.00"))
    value = bundle(events, products=products, templates=[template(), freight], books=BOTH_BOOKS)
    asc, nodes = fold(value, "ASC606")
    assert asc.findings == ()
    assert [o.subject_key for o in asc.obligations] == ["K-01/POB-01"]
    host = asc.obligations[0]
    assert (host.stated_price, host.quantity) == (Fraction(1050), Fraction(1))
    assert [(m.obligation_key, m.rule, m.weighted) for m in host.members] == [
        ("POB-01", "LINE", True),
        ("SHIP-1", "S03-R-14", False),
    ]
    node = nodes["stated_price:K-01/POB-01:-"]
    assert (node.value, node.formula_id) == ("1050", "pob.merge.v1")
    assert nodes["original_quantity:K-01/POB-01:-"].value == "1"
    ifrs, _ = fold(value, "IFRS15")  # POL-021 FALSE forced (POLICIES §6.2 row 4)
    assert [(o.obligation_key, o.stated_price) for o in ifrs.obligations] == [
        ("POB-01", Fraction(1000)),
        ("SHIP-1", Fraction(50)),
    ]

    events = booked(
        line("POB-01", "HW", price="1000.00"),
        line("POB-02", "SW", price="800.00"),
        line("SHIP-1", "FREIGHT", price="50.00"),
        line("SHIP-2", "FREIGHT", price="30.00", bundle_parent_obligation_key="POB-01"),
    )
    value = bundle(
        events,
        products=products,
        templates=[template(), freight],
        ssp=[points(HW="900.00", SW="1200.00")],
    )
    st, _ = fold(value)
    assert [(o.obligation_key, o.stated_price) for o in st.obligations] == [
        ("POB-01", Fraction(1030)),  # bundle parent host
        ("POB-02", Fraction(850)),  # largest SSP host
    ]


def test_s03_r15_franchisor_expedient() -> None:
    licence = template("TPL-LIC", obligation_kind="LICENCE", licence_nature="SYMBOLIC", **OVER_TIME)
    templates = [licence, template("TPL-ND", distinctness="nondistinct")]
    preopening = product("PREOPEN", "TPL-ND", preopening=True)
    franchise = line("L2-LIC", "FRAN-LIC", price="50000.00", end=date(2035, 12, 31))
    services = line("L1-PREOPEN", "PREOPEN", price="0.00", bundle_parent_obligation_key="L2-LIC")
    elect = {"franchisor.preopening_expedient": "ELECT_DISTINCT_SERVICES"}
    value = bundle(
        booked(services, franchise),
        products=[product("FRAN-LIC", "TPL-LIC"), preopening],
        templates=templates,
        books=BOTH_BOOKS,
        policies={"ASC606": elect, "IFRS15": elect},
    )
    asc, _ = fold(value, "ASC606")
    assert [(o.obligation_key, o.distinctness, len(o.members)) for o in asc.obligations] == [
        ("L1-PREOPEN", Distinctness.DISTINCT, 1),
        ("L2-LIC", Distinctness.DISTINCT, 1),
    ]
    ifrs, _ = fold(value, "IFRS15")  # not available: S03-R-05 merges into the licence
    assert [
        (o.obligation_key, [m.obligation_key for m in o.members]) for o in ifrs.obligations
    ] == [("L2-LIC", ["L1-PREOPEN", "L2-LIC"])]

    site = line("L3-SITE", "SITE", price="0.00")
    single = bundle(
        booked(services, franchise, site),
        products=[
            product("FRAN-LIC", "TPL-LIC"),
            preopening,
            product("SITE", "TPL-ND", preopening=True),
        ],
        templates=templates,
        policies={"ASC606": {"franchisor.preopening_expedient": "ELECT_SINGLE_SERVICES_POB"}},
    )
    st, _ = fold(single)
    assert [
        (o.obligation_key, [(m.obligation_key, m.rule) for m in o.members]) for o in st.obligations
    ] == [
        ("L1-PREOPEN", [("L1-PREOPEN", "LINE"), ("L3-SITE", "S03-R-15")]),
        ("L2-LIC", [("L2-LIC", "LINE")]),
    ]


def test_s03_r16_custodial_obligation() -> None:
    storage = template("TPL-CUST", obligation_kind="CUSTODIAL")
    events = booked(
        line("POB-01", "HW", price="9500.00"),
        line("HOLD-1", "STORAGE", price="500.00", start=date(2026, 3, 1), end=date(2026, 8, 31)),
    )
    products = [product("HW"), product("STORAGE", "TPL-CUST")]
    templates = [template(), storage]
    priced = points(HW="9500.00", STORAGE="500.00")
    st, _ = fold(bundle(events, products=products, templates=templates, ssp=[priced]))
    hold = by_key(st)["K-01/HOLD-1"]
    assert (hold.obligation_kind, hold.recognition_method, hold.satisfaction_pattern) == (
        ObligationKind.CUSTODIAL,
        RecognitionMethod.TIME_ELAPSED,
        SatisfactionPattern.OVER_TIME,
    )
    assert (hold.start_date, hold.end_date, hold.ratable_convention) == (
        date(2026, 3, 1),
        date(2026, 8, 31),
        RatableConvention.DAILY,
    )
    assert st.excluded == ()
    variants = (
        bundle(events, products=products, templates=templates, ssp=[points(HW="9500.00")]),
        bundle(
            events,
            products=products,
            templates=templates,
            ssp=[priced],
            policies={"ASC606": {"bill_and_hold.custodial_pob": "NEVER"}},
        ),
    )
    for value in variants:
        st, _ = fold(value)
        assert sorted(by_key(st)) == ["K-01/POB-01"]
        assert st.excluded == (("K-01/HOLD-1", "S03-R-16"),)


def test_s03_r17_one_measure_per_obligation() -> None:
    products = [product("BUILD", "TPL-OT"), product("SAAS", "TPL-OT")]
    events = booked(line("POB-01", "SAAS"), line("POB-02", "BUILD"))
    measure = "recognition.measure_of_progress"
    extra = (
        policy(measure, "GROUP", "", "UNITS_DELIVERED", level="T"),  # not an obligation override
        policy(measure, "OBLIGATION", "K-01/POB-02", "COST_TO_COST", level="O"),
    )
    value = bundle(
        events,
        products=products,
        templates=[template("TPL-OT", **OVER_TIME)],
        policies={"ASC606": {"recognition.time_convention": "MONTHLY_EVEN"}},
        extra=extra,
    )
    st, _ = fold(value)
    saas, build = by_key(st)["K-01/POB-01"], by_key(st)["K-01/POB-02"]
    assert (saas.recognition_method, saas.ratable_convention) == (
        RecognitionMethod.TIME_ELAPSED,
        RatableConvention.MONTHLY_EVEN,  # POL-090 pin K
    )
    assert (build.recognition_method, build.ratable_convention) == (
        RecognitionMethod.COST_TO_COST,
        None,
    )
    invalid = policy(measure, "OBLIGATION", "K-01/POB-02", "SPEED", level="O")
    with pytest.raises(ValueError, match="POL-091"):
        fold(
            bundle(
                events,
                products=products,
                templates=[template("TPL-OT", **OVER_TIME)],
                extra=[invalid],
            )
        )


def test_s03_r18_legacy_templates() -> None:
    legacy = [
        template(
            code, obligation_kind=kind, distinctness=flag, recognition_method="UNITS_DELIVERED"
        )
        for code, kind, flag in (
            ("LEGACY-DISTINCT", "STANDARD", "distinct"),
            ("LEGACY-MATERIAL-RIGHT", "MATERIAL_RIGHT", "distinct"),
            ("LEGACY-NONDISTINCT", "STANDARD", "nondistinct"),
            ("LEGACY-VC", "VC_LINE", "distinct"),
        )
    ]
    label = {"ssp_version_label": "2023-01-01"}
    events = booked(
        line("POB #1", "Hardware 1", price="600.00", stratification="Hardware 1", **label),
        line("POB #2", "Consulting 1", price="0.00", stratification="Consulting 1", **label),
        line(
            "POB #3",
            "Material Right - Hardware",
            quantity="1000",
            price="0.00",
            stratification="Material Right - Hardware",
            **label,
        ),
        line("VC #1", "VC #1", price="-100.00", stratification="VC", **label),
    )
    products = [
        product("Consulting 1"),  # the SSP entry flag, not the product default, decides
        product("Hardware 1"),
        product("Material Right - Hardware", "LEGACY-MATERIAL-RIGHT"),
        product("VC #1"),
    ]
    book = ssp_version(
        entry("Consulting 1", stratification="Consulting 1", distinctness="nondistinct"),
        entry("Hardware 1", stratification="Hardware 1"),
        code="LEGACY-SKU-SSP",
        label="2023-01-01",
    )
    value = bundle(
        events,
        products=products,
        templates=[*legacy, template()],
        ssp=[book],
        preset="LEGACY_PARITY",
    )
    st, _ = fold(value)
    assert st.findings == ()
    rows = [(o.obligation_key, o.template_code, o.obligation_kind) for o in st.obligations]
    assert rows == [
        ("POB #1", "LEGACY-DISTINCT", ObligationKind.STANDARD),
        ("POB #2", "LEGACY-NONDISTINCT", ObligationKind.STANDARD),
        ("POB #3", "LEGACY-MATERIAL-RIGHT", ObligationKind.MATERIAL_RIGHT),
        ("VC #1", "LEGACY-VC", ObligationKind.VC_LINE),
    ]
    assert {o.template_basis for o in st.obligations} == {"LEGACY_PARITY"}
    assert {o.recognition_method for o in st.obligations} == {RecognitionMethod.UNITS_DELIVERED}
    assert by_key(st)["K-01/VC %231"].is_vc_line
