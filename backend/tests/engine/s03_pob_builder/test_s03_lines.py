"""Stage 03 POB builder: lines, templates, bundles, distinctness and series (ENGINE_SPEC §3.2 to
§3.5; BUILD_SPEC ENA-3).

Bundles come from ``support.bundles`` (DG-ENG-11); no database fixture (DG-TST-18).
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
    BundleComponentInput,
    ContractInput,
    EventInput,
    InputBundle,
    JudgementInput,
    ProductInput,
    RuleInput,
    RuleSetInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.enums import BookCode, Distinctness, ObligationKind, RecognitionMethod
from erev_engine.errors import EngineError
from erev_engine.money import largest_remainder
from erev_engine.stages import s01_canonicalize, s02_contract_identification, s03_pob_builder
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder import PobDraft, PobState
from erev_engine.stages.state import BookContext, Finding, PolicyResolver
from erev_engine.trace import SourceRef, TraceBuilder, TraceNode
from support import bundles

CONTRACT = "K-01"
INCEPTION = date(2026, 1, 1)
END = date(2026, 12, 31)
ZERO = "0" * 64


def template(
    code: str = "TPL-PIT",
    *,
    version_no: int = 1,
    effective_from: date = date(2025, 1, 1),
    effective_to: date | None = None,
    **changes: object,
) -> TemplateInput:
    base = TemplateInput(
        template_code=code,
        version_key=f"{code}@v{version_no}",
        version_no=version_no,
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
        effective_from=effective_from,
        effective_to=effective_to,
    )
    return dataclasses.replace(base, **changes)


OVER_TIME = {
    "satisfaction_pattern": "OVER_TIME",
    "over_time_criterion": "OT_A",
    "recognition_method": "TIME_ELAPSED",
    "ratable_convention": "DAILY",
}


def product(
    code: str,
    *,
    template_code: str | None = "TPL-PIT",
    family: str | None = None,
    components: Sequence[BundleComponentInput] = (),
) -> ProductInput:
    base = bundles.product(code, template_code=template_code, family=family)
    return dataclasses.replace(base, is_bundle=bool(components), components=tuple(components))


def component(
    code: str, sequence: int, *, basis: str = "relative_ssp", ratio: str | None = None
) -> BundleComponentInput:
    split_ratio = None if ratio is None else Decimal(ratio)
    return BundleComponentInput(code, Decimal("1"), basis, split_ratio, sequence, INCEPTION, None)


def line(
    key: str,
    product_code: str = "SKU-1",
    *,
    quantity: str = "1",
    price: str = "1000.00",
    start: date = INCEPTION,
    end: date = END,
    **members: object,
) -> dict[str, object]:
    base = bundles.booking_line(
        key, product_code=product_code, quantity=quantity, total_price=price, start=start, end=end
    )
    return {**base, **members}


def booked(*lines: Mapping[str, object], contract: str = CONTRACT) -> EventInput:
    keys = [str(item["obligation_key"]) for item in lines]
    payload = {"lines": list(lines)}
    return bundles.event(contract, 1, "CONTRACT_BOOKED", INCEPTION, payload, obligation_keys=keys)


def header(contract: str = CONTRACT, **changes: object) -> ContractInput:
    return dataclasses.replace(bundles.contract(contract, inception=INCEPTION), **changes)


def rule(
    key: str, template_code: str, *conditions: Mapping[str, object], priority: int = 0
) -> RuleInput:
    fields = {str(condition["field"]) for condition in conditions}
    outputs = {"pob_template_code": template_code}
    return RuleInput(key, priority, len(fields), tuple(conditions), outputs)


def rule_set(*items: RuleInput, code: str = "RS-POB") -> RuleSetInput:
    ordered = tuple(sorted(items, key=lambda r: (-r.specificity, -r.priority, r.rule_key)))
    return RuleSetInput(
        code, "POB_ASSIGNMENT", f"{code}@v1", 1, ZERO, date(2025, 1, 1), None, ordered
    )


def ssp_version(points: Mapping[str, str], *, code: str = "SSP-US") -> SspVersionInput:
    entries = tuple(
        SspEntryInput(
            entry_key=f"{code}@v1/{product_code}//-/USD",
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
            ranges=(SspRangeInput("NONE", None, None, Decimal(value), None, None, None),),
        )
        for product_code, value in sorted(points.items())
    )
    return SspVersionInput(
        ssp_book_code=code,
        version_key=f"{code}@v1",
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
        entries=entries,
    )


def with_policies(book: BookInput, overrides: Mapping[str, str]) -> BookInput:
    policies = tuple(
        dataclasses.replace(policy, value=overrides[policy.code])
        if policy.code in overrides and policy.scope == "GROUP"
        else policy
        for policy in book.policies
    )
    return dataclasses.replace(book, policies=policies)


def bundle(
    *events: EventInput,
    products: Iterable[ProductInput] = (),
    templates: Iterable[TemplateInput] | None = None,
    rule_sets: Iterable[RuleSetInput] = (),
    ssp: Iterable[SspVersionInput] = (),
    contracts: Iterable[ContractInput] | None = None,
    preset: str = "DEFAULT",
    policies: Mapping[str, str] | None = None,
) -> InputBundle:
    calendar = bundles.entity(start=INCEPTION, months=24)
    headers = tuple(contracts or (header(),))
    book = bundles.book("ASC606", preset=preset, entity=calendar)
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2026, 12, 31, 23, tzinfo=UTC),
        tenant_preset=preset,
        currencies=bundles.currencies("USD"),
        books=(with_policies(book, policies or {}),),
        entities=(calendar,),
        group=bundles.group(headers, products=tuple(products)),
        contracts=headers,
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=tuple(ssp),
        pob_template_versions=tuple(
            sorted(templates or (template(),), key=lambda t: (t.template_code, t.version_no))
        ),
        rule_set_versions=tuple(rule_sets),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def context(value: InputBundle, book_code: str = "ASC606") -> BookContext:
    book = next(b for b in value.books if b.book_code == book_code)
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
        policies=PolicyResolver(book.policies),
        mapping=book.account_mapping,
        trigger=value.trigger,
        tenant_preset=value.tenant_preset,
    )


def identify(value: InputBundle) -> tuple[BookContext, IdentifiedState]:
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    ctx = context(value)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    return ctx, s02_contract_identification.run(ctx, cb, tb)


def fold(value: InputBundle) -> tuple[PobState, dict[str, TraceNode]]:
    ctx, identified = identify(value)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    st = s03_pob_builder.run(ctx, identified, tb)
    return st, {node.id: node for node in tb.build(root_measures={}).nodes}


def by_key(st: PobState) -> dict[str, PobDraft]:
    return {obligation.subject_key: obligation for obligation in st.obligations}


def test_s03_r02_template_resolution() -> None:
    family = {"field": "product.product_family", "op": "eq", "value": "Software"}
    currency = {"field": "contract.currency", "op": "in", "value": ["USD", "EUR"]}
    rules = rule_set(
        rule("R-SAAS", "TPL-SAAS", family, currency),
        rule("R-SW", "TPL-PIT", family, priority=9),
    )
    saas = (
        template("TPL-SAAS", effective_to=INCEPTION, **OVER_TIME),
        template("TPL-SAAS", version_no=2, effective_from=INCEPTION, **OVER_TIME),
    )
    value = bundle(
        booked(
            line("POB-01", "SKU-HW"),
            line("POB-02", "SKU-SW"),
            line("POB-03", "SKU-GONE"),
            line("POB-04", "SKU-NONE"),
        ),
        products=[
            product("SKU-HW", family="Hardware"),
            product("SKU-SW", family="Software"),
            product("SKU-NONE", template_code=None),
        ],
        templates=[template(), *saas],
        rule_sets=[rules],
    )
    st, nodes = fold(value)
    obligations = by_key(st)
    assert sorted(obligations) == ["K-01/POB-01", "K-01/POB-02"]
    hardware, software = obligations["K-01/POB-01"], obligations["K-01/POB-02"]
    assert (hardware.template_code, hardware.template_basis, hardware.rule_key) == (
        "TPL-PIT",
        "PRODUCT_DEFAULT",
        None,
    )
    assert (software.template_code, software.template_version_key, software.rule_key) == (
        "TPL-SAAS",
        "TPL-SAAS@v2",
        "R-SAAS",
    )
    assert software.recognition_method == RecognitionMethod.TIME_ELAPSED
    node = nodes["original_quantity:K-01/POB-02:-"]
    assert node.formula_id == "pob.template_match.v1"
    assert (node.params["rule_key"], node.params["version_key"]) == ("R-SAAS", "TPL-SAAS@v2")
    assert node.params["basis"] == "RULE"
    assert nodes["original_quantity:K-01/POB-01:-"].params["rule_key"] == ""
    assert [(f.code, f.severity, f.subject_key, f.stage) for f in st.findings] == [
        ("PRODUCT_UNMAPPED", "ERROR", "K-01/POB-03", 3),
        ("PRODUCT_UNMAPPED", "ERROR", "K-01/POB-04", 3),
    ]
    assert st.findings[0].detail == {"obligation_key": "POB-03", "product_code": "SKU-GONE"}


def test_ex_03_a_bundle_explosion() -> None:
    relative = (component("HW", 1), component("SUP", 2))
    parts = [product("HW"), product("SUP")]

    def explode(
        components: Sequence[BundleComponentInput], ssp: Iterable[SspVersionInput]
    ) -> tuple[PobState, dict[str, TraceNode]]:
        bundle_product = product("BND", template_code=None, components=components)
        return fold(
            bundle(booked(line("BND-1", "BND")), products=[bundle_product, *parts], ssp=ssp)
        )

    st, nodes = explode(relative, [ssp_version({"HW": "700.00", "SUP": "800.00"})])
    assert st.findings == ()
    assert largest_remainder(100000, [Fraction(700), Fraction(800)], ["BND-1.01", "BND-1.02"]) == [
        46667,
        53333,
    ]
    obligations = by_key(st)
    assert sorted(obligations) == ["K-01/BND-1.01", "K-01/BND-1.02"]
    hardware, support = obligations["K-01/BND-1.01"], obligations["K-01/BND-1.02"]
    assert (hardware.product_code, hardware.stated_price, hardware.bundle_product_code) == (
        "HW",
        Fraction(46667, 100),
        "BND",
    )
    assert (support.product_code, support.stated_price) == ("SUP", Fraction(53333, 100))
    assert hardware.bundle_parent_obligation_key == "BND-1"
    node = nodes["stated_price:K-01/BND-1.01:-"]
    assert (node.value, node.formula_id, node.currency) == ("466.67", "pob.bundle_split.v1", "USD")
    assert (node.params["keys"], node.params["weights"]) == ("BND-1.01,BND-1.02", "700,800")
    assert node.inputs == (
        SourceRef("contract_event", "K-01/EV-000001", {"line": "BND-1", "value": "1000"}),
    )
    assert nodes["stated_price:K-01/BND-1.02:-"].value == "533.33"
    assert "stated_price:K-01/BND-1:-" not in nodes  # the bundle line creates no obligation

    fixed = (
        component("HW", 1, basis="fixed_percentage", ratio="0.25"),
        component("SUP", 2, basis="fixed_percentage", ratio="0.75"),
    )
    st, _ = explode(fixed, [])
    assert [o.stated_price for o in st.obligations] == [Fraction(250), Fraction(750)]

    st, _ = explode(relative, [ssp_version({"HW": "700.00"})])
    assert [(f.code, f.severity, f.subject_key) for f in st.findings] == [
        ("SSP_KEY_NOT_FOUND", "ERROR", "K-01/BND-1.02")
    ]
    assert st.obligations == ()


def test_s03_r04_negative_and_zero_price_lines() -> None:
    native = bundle(
        booked(
            line("POB-01", quantity="-1", price="100.00"),
            line("POB-02", price="-90.00"),
            line("POB-03", price="0.00"),
        ),
        products=[product("SKU-1")],
    )
    st, nodes = fold(native)
    assert [(f.code, f.severity, f.subject_key) for f in st.findings] == [
        ("NEGATIVE_BOOKING_LINE", "ERROR", "K-01/POB-01"),
        ("NEGATIVE_BOOKING_LINE", "ERROR", "K-01/POB-02"),
    ]
    free = by_key(st)["K-01/POB-03"]  # REQ-POB-002: a distinct $0 line is an obligation
    assert (free.stated_price, free.distinctness) == (Fraction(0), Distinctness.DISTINCT)
    assert nodes["stated_price:K-01/POB-03:-"].value == "0"

    parity = bundle(
        booked(
            line("POB #1", "Hardware 1", price="600.00", stratification="Hardware 1"),
            line("VC #1", "VC #1", price="-100.00", stratification="VC"),
        ),
        products=[
            product("Hardware 1", template_code="LEGACY-DISTINCT"),
            product("VC #1", template_code="LEGACY-VC"),
        ],
        templates=[
            template("LEGACY-DISTINCT", recognition_method="UNITS_DELIVERED"),
            template("LEGACY-VC", obligation_kind="VC_LINE", recognition_method="UNITS_DELIVERED"),
        ],
        preset="LEGACY_PARITY",
    )
    st, _ = fold(parity)
    assert st.findings == ()
    vc = by_key(st)["K-01/VC %231"]
    assert (vc.obligation_kind, vc.is_vc_line, vc.stated_price) == (
        ObligationKind.VC_LINE,
        True,
        Fraction(-100),
    )

    with pytest.raises(EngineError) as raised:
        fold(bundle(booked(line("POB-01", quantity="0")), products=[product("SKU-1")]))
    assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert raised.value.detail == {"rule": "S03-R-04"}


def test_s03_r05_nondistinct_merge() -> None:
    outcome = {
        "obligation_key": "POB-02",
        "distinctness": "nondistinct",
        "integrates_into_obligation_key": "POB-01",
    }
    override = JudgementInput("J-01", "POB_DISTINCT_OVERRIDE", CONTRACT, None, outcome)
    events = booked(
        line("POB-01", "HW", end=date(2026, 6, 30)),
        line("POB-02", "INSTALL", price="200.00", start=date(2026, 2, 1)),
        line("POB-03", "TRAIN", price="300.00"),
        line("POB-04", "CABLE", quantity="2", price="50.00", bundle_parent_obligation_key="POB-01"),
    )
    products = [
        product("CABLE", template_code="TPL-ND"),
        product("HW"),
        product("INSTALL"),
        product("TRAIN", template_code="TPL-ND"),
    ]
    templates = [template(), template("TPL-ND", distinctness="nondistinct")]
    contract = header(judgements=(override,))
    st, nodes = fold(bundle(events, products=products, templates=templates, contracts=[contract]))
    assert st.findings == ()
    obligations = by_key(st)
    assert sorted(obligations) == ["K-01/POB-01", "K-01/POB-03"]
    host = obligations["K-01/POB-01"]
    assert [(m.obligation_key, m.rule) for m in host.members] == [
        ("POB-01", "LINE"),
        ("POB-02", "S03-R-05"),
        ("POB-04", "S03-R-05"),
    ]
    assert (host.quantity, host.stated_price, host.start_date, host.end_date) == (
        Fraction(4),
        Fraction(1250),
        INCEPTION,
        END,
    )
    assert (host.template_code, host.recognition_method, host.price_basis) == (
        "TPL-PIT",
        RecognitionMethod.POINT_IN_TIME,
        "MERGED",
    )
    node = nodes["stated_price:K-01/POB-01:-"]
    assert (node.value, node.formula_id) == ("1250", "pob.merge.v1")
    assert [ref.detail["line"] for ref in node.inputs if isinstance(ref, SourceRef)] == [
        "POB-01",
        "POB-02",
        "POB-04",
    ]
    assert nodes["original_quantity:K-01/POB-01:-"].value == "4"
    unmerged = obligations["K-01/POB-03"]  # 25-22: its own obligation without a target
    assert (unmerged.distinctness, len(unmerged.members)) == (Distinctness.NONDISTINCT, 1)
    members = sorted(m.subject_key for o in st.obligations for m in o.members)
    assert members == ["K-01/POB-01", "K-01/POB-02", "K-01/POB-03", "K-01/POB-04"]  # S03-INV-01

    single, _ = fold(
        bundle(
            events,
            products=products,
            templates=templates,
            contracts=[contract],
            policies={"migration.nondistinct_mapping": "SINGLE_POB"},
        )
    )
    assert len(single.obligations) == 4  # POL-211 SINGLE_POB never merges


def test_s03_r06_series_increment_unit() -> None:
    series = template(
        "TPL-SERIES", distinctness="series", series_increment_unit="month", **OVER_TIME
    )
    outcome = {"obligation_key": "POB-02", "series_increment_unit": "day"}
    classification = JudgementInput("J-01", "SERIES_CLASSIFICATION", CONTRACT, None, outcome)
    events = booked(line("POB-01", "SAAS"), line("POB-02"), line("POB-03"))
    products = [product("SAAS", template_code="TPL-SERIES"), product("SKU-1")]
    contract = header(judgements=(classification,))
    st, _ = fold(
        bundle(events, products=products, templates=[template(), series], contracts=[contract])
    )
    obligations = by_key(st)
    assert [(o.distinctness, o.series_increment_unit) for o in obligations.values()] == [
        (Distinctness.SERIES, "month"),
        (Distinctness.SERIES, "day"),
        (Distinctness.DISTINCT, None),
    ]

    without_unit = dataclasses.replace(series, series_increment_unit=None)
    week = JudgementInput(
        "J-01",
        "SERIES_CLASSIFICATION",
        CONTRACT,
        None,
        {**outcome, "series_increment_unit": "week"},
    )
    invalid = (
        bundle(events, products=products, templates=[template(), without_unit]),
        bundle(
            events,
            products=products,
            templates=[template(), series],
            contracts=[header(judgements=(week,))],
        ),
    )
    for value in invalid:
        with pytest.raises(EngineError) as raised:
            fold(value)
        assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
        assert raised.value.detail["rule"] == "S03-R-06"


def test_s03_subject_keys_continuous_identity() -> None:
    contract = "Contract 1"
    templates = [template(), template(version_no=2, effective_from=date(2026, 6, 1))]
    value = bundle(
        booked(line("POB #1"), line("POB/2", price="500.00"), contract=contract),
        products=[product("SKU-1")],
        templates=templates,
        contracts=[header(contract)],
    )
    first, nodes = fold(value)
    second, _ = fold(value)
    keys = [obligation.subject_key for obligation in first.obligations]
    assert keys == ["Contract 1/POB %231", "Contract 1/POB%2F2"]
    assert len(set(keys)) == len(keys)  # S03-INV-02
    assert first.obligations == second.obligations
    assert {o.template_version_key for o in first.obligations} == {"TPL-PIT@v1"}
    assert "stated_price:Contract 1/POB %231:-" in nodes

    ctx, identified = identify(value)
    added_on = date(2026, 7, 1)
    added = line("POB #5", quantity="3", price="300.00", start=added_on)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    drafts = s03_pob_builder.build_lines(ctx, identified, [added], added_on, tb)
    assert [
        (d.subject_key, d.pricing_date, d.original_quantity, d.original_stated_price)
        for d in drafts
    ] == [("Contract 1/POB %235", added_on, Fraction(3), Fraction(300))]
    assert drafts[0].template_version_key == "TPL-PIT@v2"  # effective at the pricing date
    node_ids = {node.id for node in tb.build(root_measures={}).nodes}
    assert node_ids == {
        "original_quantity:Contract 1/POB %235:-",
        "stated_price:Contract 1/POB %235:-",
    }

    unmapped = [line("POB #6", "SKU-GONE")]
    with pytest.raises(EngineError) as raised:
        s03_pob_builder.build_lines(
            ctx, identified, unmapped, added_on, TraceBuilder(engine_version=ENGINE_VERSION)
        )
    assert raised.value.code == "PRODUCT_UNMAPPED"
    findings: list[Finding] = []
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    assert (
        s03_pob_builder.build_lines(ctx, identified, unmapped, added_on, tb, findings=findings)
        == ()
    )
    assert [f.code for f in findings] == ["PRODUCT_UNMAPPED"]
    assert s03_pob_builder.POLICY_KEYS == tuple(sorted(s03_pob_builder.POLICY_KEYS))
