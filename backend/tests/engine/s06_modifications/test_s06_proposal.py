"""Stage 06 modification proposal (ENGINE_SPEC §6.2 S06-R-01 to S06-R-05; §6.7 EX-06-C; ENB-1).

``AllocatedState`` comes from stage 05, which ENA-10 builds, so the tests assemble it from the stage
01 and 02 state and hand-built obligations with one ``INCEPTION`` segment (ENGINE_SPEC §0.11
contract). Bundles come from ``support.bundles``; no database fixture (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION, dates
from erev_engine.bundle import (
    BookInput,
    EventInput,
    InputBundle,
    ModificationInput,
    ProductInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.enums import (
    BookCode,
    Distinctness,
    LicenceNature,
    ModificationTreatment,
    ObligationKind,
    PrincipalAgent,
    RatableConvention,
    RecognitionMethod,
    SatisfactionPattern,
    ScopeFlag,
    WarrantyType,
)
from erev_engine.money import format_exact, to_fraction
from erev_engine.stages import s01_canonicalize, s02_contract_identification, s06_modifications
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s06_modifications import ModificationView, Proposal
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    ObligationState,
    PolicyResolver,
    ProgressBase,
    ProgressTotals,
    Quota,
    SegmentCause,
    SpecialistTargets,
)
from erev_engine.trace import TraceBuilder, TraceNode
from support import bundles, golden_streams

CONTRACT = "K-01"
INCEPTION = date(2026, 1, 1)
END = date(2026, 12, 31)
ZERO = "0" * 64
PolicyValue = str | Mapping[str, str]


def template(
    code: str,
    *,
    distinctness: str = "distinct",
    method: str = "UNITS_DELIVERED",
    pattern: str = "POINT_IN_TIME",
    convention: str | None = None,
) -> TemplateInput:
    return TemplateInput(
        template_code=code,
        version_key=f"{code}@v1",
        version_no=1,
        content_sha256=ZERO,
        obligation_kind="STANDARD",
        distinctness=distinctness,
        series_increment_unit="month" if distinctness == "series" else None,
        satisfaction_pattern=pattern,
        over_time_criterion="OT_A" if pattern == "OVER_TIME" else "NOT_APPLICABLE",
        recognition_method=method,
        ratable_convention=convention,
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
    template("TPL-SER", distinctness="series", method="TIME_ELAPSED", pattern="OVER_TIME"),
    template("TPL-SVC", distinctness="nondistinct", method="TIME_ELAPSED", pattern="OVER_TIME"),
    template("TPL-UNITS"),
    template("TPL-UNITS-ND", distinctness="nondistinct"),
)


def product(code: str, template_code: str) -> ProductInput:
    return bundles.product(code, template_code=template_code, family=None)


def point_entry(version_key: str, product_code: str, point: str) -> SspEntryInput:
    return SspEntryInput(
        entry_key=f"{version_key}/{product_code}//-/USD",
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


def range_entry(
    version_key: str, product_code: str, price: str, discount: str, spread: str, flag: str
) -> SspEntryInput:
    mid = Decimal(price) * (1 - Decimal(discount))
    return dataclasses.replace(
        point_entry(version_key, product_code, "0"),
        method="legacy_range",
        unit_list_price=Decimal(price),
        midpoint_discount_ratio=Decimal(discount),
        range_ratio=Decimal(spread),
        distinctness=flag,
        ranges=(
            SspRangeInput(
                "NONE",
                None,
                None,
                None,
                mid * (1 - Decimal(spread)),
                mid,
                mid * (1 + Decimal(spread)),
            ),
        ),
    )


def ssp_version(
    number: int,
    entries: Iterable[SspEntryInput],
    effective_from: date,
    effective_to: date | None = None,
) -> SspVersionInput:
    return SspVersionInput(
        ssp_book_code="SSP-US",
        version_key=f"SSP-US@v{number}",
        version_no=number,
        resolution_mode="EFFECTIVE_DATE",
        legacy_version_label=None,
        effective_from_date=effective_from,
        effective_to_date=effective_to,
        status="APPROVED",
        approved_at=datetime(2025, 12, 1, tzinfo=UTC),
        content_sha256=ZERO,
        scope_entity_code=None,
        scope_currency=None,
        scope_channel=None,
        scope_segment=None,
        entries=tuple(sorted(entries, key=lambda entry: entry.product_code)),
    )


def book_with(preset: str, overrides: Mapping[str, PolicyValue]) -> BookInput:
    base = bundles.book("ASC606", preset=preset, entity=bundles.entity(start=INCEPTION, months=24))
    policies = tuple(
        dataclasses.replace(policy, value=overrides[policy.code])
        if policy.code in overrides and policy.scope == "GROUP"
        else policy
        for policy in base.policies
    )
    return dataclasses.replace(base, policies=policies)


def bundle(
    *events: EventInput,
    products: Sequence[ProductInput],
    ssp: Sequence[SspVersionInput],
    overrides: Mapping[str, PolicyValue] | None = None,
) -> InputBundle:
    header = bundles.contract(CONTRACT, inception=INCEPTION)
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2026, 12, 31, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(book_with("DEFAULT", overrides or {}),),
        entities=(bundles.entity(start=INCEPTION, months=24),),
        group=bundles.group((header,), products=products),
        contracts=(header,),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=tuple(ssp),
        pob_template_versions=TEMPLATES,
        rule_set_versions=(),
        estimate_versions=(),
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


def identify(value: InputBundle) -> tuple[BookContext, IdentifiedState]:
    ctx = context(value)
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    return ctx, s02_contract_identification.run(
        ctx, cb, TraceBuilder(engine_version=ENGINE_VERSION)
    )


def booked(*lines: Mapping[str, object]) -> EventInput:
    keys = [str(line["obligation_key"]) for line in lines]
    payload = {"lines": list(lines)}
    return bundles.event(CONTRACT, 1, "CONTRACT_BOOKED", INCEPTION, payload, obligation_keys=keys)


def line(
    key: str, product_code: str, quantity: str, price: str, start: date = INCEPTION
) -> dict[str, object]:
    return bundles.booking_line(
        key, product_code=product_code, quantity=quantity, total_price=price, start=start, end=END
    )


def delivered(stream: int, key: str, quantity: str, on: date) -> EventInput:
    payload = {"obligation_key": key, "quantity": Decimal(quantity), "trigger": "DELIVERY"}
    return bundles.event(CONTRACT, stream, "DELIVERY_RECORDED", on, payload, obligation_keys=[key])


def obligation(
    key: str,
    *,
    quantity: str,
    price: str,
    method: RecognitionMethod = RecognitionMethod.UNITS_DELIVERED,
    distinctness: Distinctness = Distinctness.DISTINCT,
    start: date = INCEPTION,
    product_code: str = "SKU-P",
    contract: str = CONTRACT,
) -> ObligationState:
    """One obligation with its INCEPTION segment (ENGINE_SPEC §0.11; CV-61)."""
    q, x = to_fraction(quantity), to_fraction(price)
    cents = int(x * 100)
    timed = method == RecognitionMethod.TIME_ELAPSED
    segment = AllocationSegment(
        component="FIXED",
        effective_date=INCEPTION,
        event_key=None,
        cause=SegmentCause.INCEPTION,
        basis="INCEPTION",
        x_exact=x,
        a_posted=cents,
        base_revenue_posted=0,
        base_revenue_exact=Fraction(0),
        base_progress=ProgressBase.zero(),
        totals=ProgressTotals(q, None, start, END),
        progress_measure=method.value,
        unit_ssp=x / q,
        remaining_ssp=x,
        remaining_billing_plan=x,
        estimate_pair=(None, None),
        modification_boundary_no=0,
    )
    return ObligationState(
        subject_key=obligation_subject_key(contract, key),
        contract_key=contract,
        obligation_key=key,
        obligation_kind=ObligationKind.STANDARD,
        distinctness=distinctness,
        satisfaction_pattern=SatisfactionPattern.OVER_TIME
        if timed
        else SatisfactionPattern.POINT_IN_TIME,
        recognition_method=method,
        ratable_convention=RatableConvention.DAILY if timed else None,
        principal_agent=PrincipalAgent.PRINCIPAL,
        licence_nature=LicenceNature.NOT_APPLICABLE,
        scope_flag=ScopeFlag.IN_SCOPE_606,
        start_date=start,
        end_date=END,
        recognition_start_date=None,
        contracting_entity=bundles.ENTITY_CODE,
        performing_entity=bundles.ENTITY_CODE,
        quantity=q,
        resolved_ssp=x,
        revenue_category=None,
        dimensions={},
        account_overrides={},
        segments=(segment,),
        opening=None,
        terminated_on=None,
        template_version_key="TPL-UNITS@v1",
        product_code=product_code,
        sku_number=None,
        stratification=None,
        series_increment_unit="month" if distinctness == Distinctness.SERIES else None,
        over_time_criterion="OT_A" if timed else "NOT_APPLICABLE",
        warranty_type=WarrantyType.NONE,
        material_right=None,
        ssp=None,
        original_quantity=q,
        original_stated_price=x,
        stated_price=x,
        original_allocation=Quota(x, cents),
        original_total_contract_price=x,
        original_total_contract_ssp=x,
        is_vc_line=False,
        gross_to_net=None,
        lineage_pre_modification=(),
        assurance_cost_per_unit=None,
        last_modification_key=None,
        inception_weight=x,
    )


def allocated(
    identified: IdentifiedState, obligations: Iterable[ObligationState]
) -> AllocatedState:
    cb = identified.canonical
    return AllocatedState(
        group_code=identified.group_code,
        inception_date=identified.inception_date,
        contracts=identified.contracts,
        obligations=tuple(sorted(obligations, key=lambda ob: ob.subject_key)),
        events=cb.events,
        measure_events=cb.measure_events,
        ledger=cb.ledger,
        return_paths={},
        estimates=cb.estimates,
        tp_unconstrained={},
        specialist_targets=SpecialistTargets((), (), (), (), ()),
        proposals=(),
        time_triggers=(),
        tp_history=(),
        targeted_vc_quotas={},
        targeted_vc_quota_history={},
        refund_components={},
        findings=(),
    )


def modification(
    key: str,
    effective: date,
    *lines: Mapping[str, object],
    questionnaire: Mapping[str, object] | None = None,
    kind: str = "ADD_OBLIGATION",
    template_mode: str | None = None,
    contract: str = CONTRACT,
) -> ModificationView:
    value = ModificationInput(
        modification_key=key,
        effective_date=effective,
        kind=kind,
        template_mode=template_mode,
        status="SUBMITTED",
        reference=None,
        questionnaire=questionnaire or {},
        lines=tuple(lines),
        price_change_amount=None,
        noncash_consideration=None,
        consideration_payable=None,
        scope_605_35=None,
        currency="USD",
        proposed_treatments={},
        chosen_treatments={},
        treatment_summary=None,
        ssp_basis={},
        judgement_key=None,
        content_sha256=None,
    )
    return ModificationView.of(contract, value)


def mod_line(
    key: str,
    action: str,
    product_code: str,
    quantity: str,
    consideration: str,
    *,
    start: date | None = None,
) -> dict[str, object]:
    members: dict[str, object] = {
        "obligation_key": key,
        "action": action,
        "product_code": product_code,
        "quantity_delta": Decimal(quantity),
        "consideration_delta": Decimal(consideration),
    }
    if start is not None:
        members.update({"start_date": start, "end_date": END})
    return members


def nodes(tb: TraceBuilder) -> dict[str, TraceNode]:
    return {node.id: node for node in tb.build(root_measures={}).nodes}


# --- EX-06-C (research 04 S6-EX5 Case A) ---------------------------------------------------------

MOD_DATE = date(2026, 6, 15)
TOLERANCE_0 = {"option": "WITHIN_MOD_DATE_RANGE", "point_tolerance_pct": "0.00"}


def ex_06_c(
    overrides: Mapping[str, PolicyValue] | None = None,
) -> tuple[BookContext, IdentifiedState, AllocatedState]:
    """120 products at 100.00; 60 transferred by 31 May 2026; mod-date SSP point 95.00."""
    value = bundle(
        booked(line("POB-01", "SKU-P", "120", "12000.00")),
        delivered(2, "POB-01", "60", date(2026, 5, 31)),
        products=[product("SKU-P", "TPL-UNITS")],
        ssp=[
            ssp_version(
                1,
                [point_entry("SSP-US@v1", "SKU-P", "100.00")],
                date(2025, 1, 1),
                date(2026, 5, 31),
            ),
            ssp_version(2, [point_entry("SSP-US@v2", "SKU-P", "95.00")], date(2026, 6, 1)),
        ],
        overrides={"mod.separate_contract_price_test": TOLERANCE_0, **(overrides or {})},
    )
    ctx, identified = identify(value)
    st = allocated(identified, [obligation("POB-01", quantity="120", price="12000.00")])
    return ctx, identified, st


def test_ex_06_c_separate_contract_proposal() -> None:
    ctx, identified, st = ex_06_c()
    addon = mod_line("POB-02", "ADD", "SKU-P", "30", "2850.00", start=MOD_DATE)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    proposal = s06_modifications.propose(
        ctx, st, modification("MOD-1", MOD_DATE, addon), tb, identified=identified
    )
    assert proposal.summary == ModificationTreatment.SEPARATE_CONTRACT
    assert proposal.treatments == {"POB-02": ModificationTreatment.SEPARATE_CONTRACT}
    assert proposal.findings == ()
    assert proposal.classification == {"POB-01": "D", "POB-02": "D"}
    test = nodes(tb)["mod_price_test@K-01/MOD-1:K-01/POB-02:-"]
    assert (test.formula_id, test.params["basis"], test.params["passed"]) == (
        "mod.price_test.v1",
        "POINT",
        "true",
    )
    assert to_fraction(test.params["point"]) == 2850
    assert test.params["version_key"] == "SSP-US@v2"
    out = proposal.out()
    assert (out.kind, out.summary, out.treatments) == (
        "MODIFICATION_TREATMENT",
        "SEPARATE_CONTRACT",
        {"POB-02": "SEPARATE_CONTRACT"},
    )
    # 96.00 a unit departs from the point 95.00: no separate contract with a zero tolerance.
    dearer = mod_line("POB-02", "ADD", "SKU-P", "30", "2880.00", start=MOD_DATE)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    pooled = s06_modifications.propose(
        ctx, st, modification("MOD-2", MOD_DATE, dearer), tb, identified=identified
    )
    assert pooled.summary == ModificationTreatment.PROSPECTIVE
    assert pooled.treatments == {
        "POB-01": ModificationTreatment.PROSPECTIVE,
        "POB-02": ModificationTreatment.PROSPECTIVE,
    }
    assert nodes(tb)["mod_price_test@K-01/MOD-2:K-01/POB-02:-"].params["passed"] == "false"
    tolerant = {"option": "WITHIN_MOD_DATE_RANGE", "point_tolerance_pct": "0.02"}
    ctx, identified, st = ex_06_c({"mod.separate_contract_price_test": tolerant})
    within = s06_modifications.propose(
        ctx,
        st,
        modification("MOD-2", MOD_DATE, dearer),
        TraceBuilder(engine_version=ENGINE_VERSION),
        identified=identified,
    )
    assert within.summary == ModificationTreatment.SEPARATE_CONTRACT
    # The preparer's approved attestation "priced at SSP" passes the test whatever the point.
    ctx, identified, st = ex_06_c()
    answers = {"POB-02": {"priced_at_ssp": True}}
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    attested = s06_modifications.propose(
        ctx,
        st,
        modification("MOD-3", MOD_DATE, dearer, questionnaire=answers),
        tb,
        identified=identified,
    )
    assert attested.summary == ModificationTreatment.SEPARATE_CONTRACT
    assert nodes(tb)["mod_price_test@K-01/MOD-3:K-01/POB-02:-"].params["basis"] == "ATTESTED"


def test_s06_r05_classes() -> None:
    value = bundle(
        booked(
            line("POB-S", "SKU-P", "1", "500.00"),
            line("POB-D", "SKU-P", "10", "1000.00"),
            line("POB-N", "SKU-SVC", "1", "1200.00"),
            line("POB-U", "SKU-SVC", "1", "600.00", start=date(2026, 8, 1)),
            line("POB-Q", "SKU-SVC", "1", "900.00"),
            line("POB-SER", "SKU-SER", "12", "2400.00"),
        ),
        delivered(2, "POB-S", "1", date(2026, 2, 1)),
        delivered(3, "POB-D", "4", date(2026, 3, 31)),
        products=[
            product("SKU-P", "TPL-UNITS"),
            product("SKU-SER", "TPL-SER"),
            product("SKU-SVC", "TPL-SVC"),
        ],
        ssp=[ssp_version(1, [point_entry("SSP-US@v1", "SKU-P", "100.00")], date(2025, 1, 1))],
    )
    ctx, identified = identify(value)
    timed = RecognitionMethod.TIME_ELAPSED
    nondistinct = Distinctness.NONDISTINCT
    st = allocated(
        identified,
        [
            obligation(
                "POB-S", quantity="1", price="500.00", method=RecognitionMethod.POINT_IN_TIME
            ),
            obligation("POB-D", quantity="10", price="1000.00"),
            obligation(
                "POB-N", quantity="1", price="1200.00", method=timed, distinctness=nondistinct
            ),
            obligation(
                "POB-U",
                quantity="1",
                price="600.00",
                method=timed,
                distinctness=nondistinct,
                start=date(2026, 8, 1),
            ),
            obligation(
                "POB-Q", quantity="1", price="900.00", method=timed, distinctness=nondistinct
            ),
            obligation(
                "POB-SER",
                quantity="12",
                price="2400.00",
                method=timed,
                distinctness=Distinctness.SERIES,
            ),
        ],
    )
    d = date(2026, 7, 1)
    questionnaire = {"POB-Q": {"remaining_goods_distinct_from_transferred": True}}
    change = mod_line("POB-D", "CHANGE", "SKU-P", "2", "200.00")
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    proposal = s06_modifications.propose(
        ctx,
        st,
        modification("MOD-A", d, change, questionnaire=questionnaire, kind="QUANTITY_CHANGE"),
        tb,
        identified=identified,
    )
    assert proposal.findings == ()
    assert proposal.classification == {
        "POB-D": "D",
        "POB-N": "N",
        "POB-Q": "D",
        "POB-S": "S",
        "POB-SER": "D",
        "POB-U": "D",
    }
    prospective, catch_up = (
        ModificationTreatment.PROSPECTIVE,
        ModificationTreatment.CUMULATIVE_CATCH_UP,
    )
    assert proposal.treatments == {
        "POB-D": prospective,
        "POB-N": catch_up,
        "POB-Q": prospective,
        "POB-SER": prospective,
        "POB-U": prospective,
    }
    assert proposal.summary == ModificationTreatment.MIXED
    traced = nodes(tb)
    reasons = {
        key: traced[f"mod_class@K-01/MOD-A:K-01/{key}:-"].params["reason"]
        for key in proposal.classification
    }
    assert reasons == {
        "POB-D": "DISTINCT_UNITS",
        "POB-N": "PARTIALLY_SATISFIED",
        "POB-Q": "QUESTIONNAIRE",
        "POB-S": "SATISFIED",
        "POB-SER": "SERIES",
        "POB-U": "UNSTARTED",
    }
    elapsed = Fraction(dates.days_inclusive(INCEPTION, d), dates.days_inclusive(INCEPTION, END))
    assert traced["mod_class@K-01/MOD-A:K-01/POB-N:-"].value == format_exact(elapsed)
    assert traced["mod_class@K-01/MOD-A:K-01/POB-D:-"].value == "0.4"
    # A quantity line on the satisfied obligation blocks the modification.
    more = mod_line("POB-S", "CHANGE", "SKU-P", "1", "500.00")
    blocked = s06_modifications.propose(
        ctx,
        st,
        modification("MOD-B", d, more, kind="QUANTITY_CHANGE"),
        TraceBuilder(engine_version=ENGINE_VERSION),
        identified=identified,
    )
    assert [(f.code, f.severity, f.subject_key, f.stage) for f in blocked.findings] == [
        ("MOD_QTY_ON_SATISFIED_POB", "ERROR", "K-01/POB-S", 6)
    ]
    assert blocked.classification["POB-S"] == "S"
    assert "POB-S" not in blocked.treatments


def test_s06_r02_dry_run_same_proposal() -> None:
    ctx, identified, st = ex_06_c()
    addon = mod_line("POB-02", "ADD", "SKU-P", "30", "2850.00", start=MOD_DATE)
    proposals: list[Proposal] = []
    traced: list[dict[str, str]] = []
    for trigger in ("COMMAND", "DRY_RUN"):
        tb = TraceBuilder(engine_version=ENGINE_VERSION)
        proposals.append(
            s06_modifications.propose(
                dataclasses.replace(ctx, trigger=trigger),
                st,
                modification("MOD-1", MOD_DATE, addon),
                tb,
                identified=identified,
            )
        )
        traced.append({node.id: node.value for node in nodes(tb).values()})
    assert proposals[0] == proposals[1]
    assert proposals[0].out() == proposals[1].out()
    assert traced[0] == traced[1]


def test_tc_prospective_07_discounted_addon_as_separate_contract() -> None:
    """Probe P-16b inputs (legacy 03 §6.3 A-01): a discounted contract, +1 hardware at SSP 90."""
    entries = [
        range_entry("SSP-US@v1", "Consulting 1", "300", "0.5", "0", "nondistinct"),
        range_entry("SSP-US@v1", "Hardware 1", "100", "0.1", "0.15", "distinct"),
    ]
    value = bundle(
        booked(
            line("POB #1", "Hardware 1", "5", "400.00"),
            line("POB #2", "Consulting 1", "1", "150.00"),
        ),
        delivered(2, "POB #1", "2", date(2026, 2, 28)),
        delivered(3, "POB #2", "0.5", date(2026, 2, 28)),
        products=[product("Consulting 1", "TPL-UNITS-ND"), product("Hardware 1", "TPL-UNITS")],
        ssp=[ssp_version(1, entries, date(2025, 1, 1))],
    )
    ctx, identified = identify(value)
    obligations = (
        obligation("POB #1", quantity="5", price="400.00", product_code="Hardware 1"),
        obligation(
            "POB #2",
            quantity="1",
            price="150.00",
            distinctness=Distinctness.NONDISTINCT,
            product_code="Consulting 1",
        ),
    )
    st = allocated(identified, obligations)
    d = date(2026, 3, 15)
    addon = mod_line("POB #3", "ADD", "Hardware 1", "1", "90.00", start=d)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    proposal = s06_modifications.propose(
        ctx, st, modification("MOD-P16B", d, addon), tb, identified=identified
    )
    assert proposal.summary == ModificationTreatment.SEPARATE_CONTRACT
    assert proposal.treatments == {"POB #3": ModificationTreatment.SEPARATE_CONTRACT}
    assert proposal.findings == ()
    traced = nodes(tb)
    test = traced["mod_price_test@K-01/MOD-P16B:K-01/POB %233:-"]
    assert test.params["basis"] == "RANGE"
    assert (to_fraction(test.params["low"]), to_fraction(test.params["high"])) == (
        Fraction("76.5"),
        Fraction("103.5"),
    )
    # The existing obligations receive no segment and no catch-up: the proposal changes no state.
    assert st.obligations == obligations
    assert all(len(ob.segments) == 1 for ob in st.obligations)
    assert not [node for node in traced if node.startswith("catch_up@")]
    assert {node.split(":")[0] for node in traced} == {
        "mod_class@K-01/MOD-P16B",
        "mod_price_test@K-01/MOD-P16B",
    }
    # Priced above the band, the add-on pools with the contract (legacy A-01 behaviour).
    dearer = mod_line("POB #3", "ADD", "Hardware 1", "1", "110.00", start=d)
    pooled = s06_modifications.propose(
        ctx,
        st,
        modification("MOD-P16B-2", d, dearer),
        TraceBuilder(engine_version=ENGINE_VERSION),
        identified=identified,
    )
    assert pooled.summary == ModificationTreatment.MIXED
    assert pooled.treatments == {
        "POB #1": ModificationTreatment.PROSPECTIVE,
        "POB #2": ModificationTreatment.CUMULATIVE_CATCH_UP,
        "POB #3": ModificationTreatment.PROSPECTIVE,
    }


def test_s06_r01_parity_template_treatments() -> None:
    """POL-100 USER_SELECTED_TEMPLATE: UAT 06.15.2023 (golden step 10) is LEGACY_PROSPECTIVE."""
    stream = golden_streams.stream("Contract 1", "10")
    value = stream.input_bundle()
    ctx = context(value)
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    identified = s02_contract_identification.run(
        ctx, cb, TraceBuilder(engine_version=ENGINE_VERSION)
    )
    obligations = [
        obligation(key, quantity="1", price="0", contract="Contract 1")
        for key in ("POB #1", "POB #2", "POB #3", "POB #4")
    ]
    st = allocated(identified, obligations)
    (mod_input,) = stream.contracts[0].modifications
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    proposal = s06_modifications.propose(
        ctx, st, ModificationView.of("Contract 1", mod_input), tb, identified=identified
    )
    legacy = ModificationTreatment.LEGACY_PROSPECTIVE
    assert proposal.summary == legacy
    assert proposal.treatments == {key: legacy for key in ("POB #1", "POB #2", "POB #3", "POB #4")}
    assert proposal.classification == {}
    assert nodes(tb) == {}
