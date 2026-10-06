"""Stage 13 LEGACY book fold and the delta identity (ENGINE_SPEC_B §13.2.4, §13.3; END-8).

The world: K-13A sells one point-in-time kit for 1,000.00 in US01 over 2026; the entity keeps
``ASC606`` (primary) and ``LEGACY`` with POL-005 ``DELTA``, and the ERP booked pre-standard
revenue through ``PRE_STANDARD_REVENUE_RECORDED`` events. The LEGACY book folds through the real
book loop and posts its JET-15 lines through the real stage 14. EX-13-A's primary lines come from
the real stage 14 over a relief input of 1,000.00, because the stage 09 to 11 adapters bind with
END-9 (D-81). No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    AccountMappingInput,
    BookInput,
    EntityInput,
    EventInput,
    InputBundle,
    MappingRuleInput,
    ModificationInput,
    PostingIntent,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.enums import BookCode
from erev_engine.money import format_money
from erev_engine.stages import STAGES, StageSpec, s01_canonicalize, s12_fx_entities, s14_posting
from erev_engine.stages.s12_fx_entities import FxFlows
from erev_engine.stages.s13_books import book_context, legacy_book, run_books
from erev_engine.stages.s14_posting import PartInputs, PostingState
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    CanonicalBundle,
    PostedIndex,
    RateIndex,
    Target,
)
from erev_engine.trace import SourceRef, Trace, TraceBuilder, reevaluate
from support import bundles

CONTRACT = "K-13A"
ENTITY = bundles.ENTITY_CODE
SUBJECT = f"{CONTRACT}/POB-01"
ADDED = f"{CONTRACT}/POB-02"
INCEPTION = date(2026, 1, 1)
KNOWN_AT = datetime(2026, 12, 31, 23, tzinfo=UTC)
ZERO_SHA = "0" * 64
DELTA: Mapping[str, str | Mapping[str, str]] = {
    "books.enabled": {"primary": "ASC606", "set": "ASC606,LEGACY"},
    "je.posting_mode": "DELTA",
}
CL, REVENUE, PRE = "CONTRACT_LIABILITY", "REVENUE", "PRE_STANDARD_REVENUE"
ACCOUNTS = {
    "ACCOUNTS_RECEIVABLE": "1100",
    "CONTRACT_ASSET": "1200",
    "UNBILLED_RECEIVABLE": "1105",
    CL: "2100",
    REVENUE: "4000",
    PRE: "4900",
}
THROUGH_11 = tuple(spec for spec in STAGES if spec.stage <= "11")
FOLD = tuple(spec for spec in STAGES if spec.stage <= "08")
STAGE_14 = next(spec for spec in STAGES if spec.stage == "14")
# EX-13-A has one period: the kit transfers and the ERP books its pre-standard revenue in January.
EX_13_A_PERIODS = 12


# --- World ---------------------------------------------------------------------------------------


def mapping() -> AccountMappingInput:
    rules = tuple(
        MappingRuleInput(role, None, None, None, None, None, code, {}, 0, 0)
        for role, code in sorted(ACCOUNTS.items())
    )
    return AccountMappingInput("MAP-LEGACY@v1", ZERO_SHA, rules)


def book(code: str, calendar: EntityInput) -> BookInput:
    policies = [
        dataclasses.replace(policy, value=DELTA[policy.code]) if policy.code in DELTA else policy
        for policy in bundles.policy_set(book_code=code, entity=calendar)
    ]
    ordered = tuple(sorted(policies, key=lambda p: (p.code, p.scope, p.subject_key)))
    return BookInput(code, code == "ASC606", (ENTITY,), ordered, mapping())


TEMPLATE = TemplateInput(
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


def ssp(points: Mapping[str, str]) -> SspVersionInput:
    entries = tuple(
        SspEntryInput(
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
            ranges=(SspRangeInput("NONE", None, None, Decimal(point), None, None, None),),
        )
        for product, point in sorted(points.items())
    )
    return SspVersionInput(
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
        entries=entries,
    )


def event(stream: int, kind: str, on: date, payload: Mapping[str, object]) -> EventInput:
    named = payload.get("obligation_key")
    keys = [] if named is None else [str(named)]
    return bundles.event(CONTRACT, stream, kind, on, payload, obligation_keys=keys)


def pre_standard(stream: int, on: date, amount: str, obligation: str = "POB-01") -> EventInput:
    payload = {"obligation_key": obligation, "amount": Decimal(amount)}
    return event(stream, "PRE_STANDARD_REVENUE_RECORDED", on, payload)


def stream(*extra: EventInput) -> list[EventInput]:
    """Booking, activation, delivery and billing on 20 January, pre-standard revenue 1,200.00."""
    line = bundles.booking_line(
        "POB-01", product_code="SKU-KIT", quantity="1", total_price="1000.00", end=INCEPTION
    )
    transfer = date(2026, 1, 20)
    delivery = {"obligation_key": "POB-01", "quantity": Decimal("1"), "trigger": "CONTROL_TRANSFER"}
    invoice = {
        "invoice_number": "INV-1",
        "line_external_id": "INV-1-1",
        "amount": Decimal("1000.00"),
        "issue_date": transfer,
    }
    booked = bundles.event(
        CONTRACT, 1, "CONTRACT_BOOKED", INCEPTION, {"lines": [line]}, obligation_keys=["POB-01"]
    )
    return [
        booked,
        event(2, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}}),
        event(3, "DELIVERY_RECORDED", transfer, delivery),
        event(4, "BILLING_RECORDED", transfer, invoice),
        pre_standard(5, date(2026, 1, 31), "1200.00"),
        *extra,
    ]


def world(
    events: Sequence[EventInput],
    *,
    heads: Sequence[tuple[str, int]] = (),
    modifications: Sequence[ModificationInput] = (),
    books: Sequence[str] = ("ASC606", "LEGACY"),
) -> InputBundle:
    calendar = bundles.entity(months=EX_13_A_PERIODS, books=books)
    header = dataclasses.replace(
        bundles.contract(CONTRACT, inception=INCEPTION), modifications=tuple(modifications)
    )
    products = (
        bundles.product("SKU-KIT", template_code="TPL-PIT", family=None),
        bundles.product("SKU-KIT2", template_code="TPL-PIT", family=None),
    )
    group = dataclasses.replace(
        bundles.group((header,), products=products), previous_stream_heads=tuple(heads)
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=KNOWN_AT,
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=tuple(book(code, calendar) for code in books),
        entities=(calendar,),
        group=group,
        contracts=(header,),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(ssp({"SKU-KIT": "1000.00", "SKU-KIT2": "500.00"}),),
        pob_template_versions=(TEMPLATE,),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def canonical(value: InputBundle) -> CanonicalBundle:
    return s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))


def legacy_posting(cb: CanonicalBundle) -> tuple[legacy_book.LegacyState, Trace, AllocatedState]:
    """The folded primary state, and the LEGACY book posted through the real stage 14."""
    (primary,) = [result for result in run_books(cb, FOLD) if result.book == "ASC606"]
    assert isinstance(primary.state, AllocatedState)
    ctx = book_context(cb, cb.books["LEGACY"])
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    state = legacy_book.run(
        ctx,
        cb,
        tb,
        allocated=primary.state,
        post=lambda fx: STAGE_14.entry(ctx, fx, tb, posted=cb.posted),
    )
    return state, tb.build(root_measures={}), primary.state


@dataclasses.dataclass(frozen=True, slots=True)
class _Costs:
    """A stage 11 output carrying the primary relief (D-81: the adapter binds with END-9)."""

    allocated: AllocatedState
    fx_flows: FxFlows
    part_inputs: PartInputs


def primary_posting(cb: CanonicalBundle, allocated: AllocatedState) -> tuple[PostingState, Trace]:
    """Stage 14 of ASC606 over a relief of 1,000.00 from January (EX-13-A)."""
    ctx = book_context(cb, cb.books["ASC606"])
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    relief: list[Target] = []
    for period in ctx.entities[ENTITY].periods:
        node = tb.node(
            measure="revenue_relief_cum",
            subject_key=SUBJECT,
            period_key=period.period_key,
            value=100000,
            currency="USD",
            minor_unit=2,
            formula_id="rec.catch_up.sum.v1",
            inputs=[
                SourceRef("source_record", f"relief/{period.period_key}", {"value": "1000.00"})
            ],
            narrative_key="rec.catch_up.sum",
        )
        relief.append(
            Target(BookCode.ASC606, ENTITY, SUBJECT, "revenue_relief_cum", period.period_key,
                   None, 100000, None, node)
        )  # fmt: skip
    costs = _Costs(allocated, FxFlows(()), PartInputs(relief=tuple(relief)))
    fx = s12_fx_entities.run(ctx, costs, tb, rates=RateIndex(()))
    state = s14_posting.run(ctx, fx, tb, posted=PostedIndex(()))
    return state, tb.build(root_measures={})


def signed(intents: Iterable[PostingIntent], sign: int = 1) -> dict[tuple[str, str], int]:
    totals: dict[tuple[str, str], int] = {}
    for intent in intents:
        for line in intent.lines:
            key = (line.account_role, line.account_code)
            amount = line.amount_txn if line.side == "D" else -line.amount_txn
            totals[key] = totals.get(key, 0) + sign * amount
    return totals


def assert_reevaluates(trace: Trace) -> None:
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}


def recording(spec: StageSpec, calls: list[tuple[str, str]]) -> StageSpec:
    entry = spec.entry

    def run(ctx: BookContext, state: object, tb: object, **bound: object) -> object:
        calls.append((spec.stage, str(ctx.book_code)))
        return entry(ctx, state, tb, **bound)

    return dataclasses.replace(spec, entry=run)


def targets_by_period(state: legacy_book.LegacyState, subject_key: str) -> dict[str, int]:
    return {t.period_key: t.value for t in state.targets if t.subject_key == subject_key}


# --- Tests ---------------------------------------------------------------------------------------


def test_ex_13_a_delta_identity() -> None:
    cb = canonical(world(stream()))
    legacy, legacy_trace, allocated = legacy_posting(cb)
    primary, primary_trace = primary_posting(cb, allocated)
    assert_reevaluates(legacy_trace)
    assert_reevaluates(primary_trace)
    # Primary: Dr CONTRACT_LIABILITY 1,000.00 / Cr REVENUE 1,000.00 in January.
    assert [(i.posting_period_key, i.entry_kind) for i in primary.posting_intents] == [
        ("FY2026-P01", "REVENUE_RECOGNITION")
    ]
    assert signed(primary.posting_intents) == {(CL, "2100"): 100000, (REVENUE, "4000"): -100000}
    # LEGACY reverses the pre-standard revenue the ERP booked (D-89 L7-6-Q-8; S13-R-08):
    # Dr PRE_STANDARD_REVENUE 1,200.00 / Cr CONTRACT_LIABILITY 1,200.00.
    (entry,) = legacy.posting_intents
    assert (entry.book_code, entry.entity, entry.posting_period_key, entry.entry_kind) == (
        "LEGACY",
        ENTITY,
        "FY2026-P01",
        "PRE_STANDARD_REVENUE",
    )
    lines = [
        (line.side, line.account_role, line.account_code, line.amount_txn) for line in entry.lines
    ]
    assert lines == [("D", PRE, "4900", 120000), ("C", CL, "2100", 120000)]
    # Primary plus LEGACY (S13-INV-03): Dr PRE_STANDARD_REVENUE 1,200.00; Cr REVENUE 1,000.00;
    # Cr CL 200.00.
    delta = signed(primary.posting_intents)
    for key, amount in signed(legacy.posting_intents).items():
        delta[key] = delta.get(key, 0) + amount
    assert {key: value for key, value in delta.items() if value} == {
        (PRE, "4900"): 120000,
        (REVENUE, "4000"): -100000,
        (CL, "2100"): -20000,
    }
    assert sum(delta.values()) == 0  # debits equal credits (S13-INV-03)


def test_s13_r07_legacy_folds_only_pre_standard_events() -> None:
    cb = canonical(world(stream(pre_standard(6, date(2026, 3, 15), "-200.00"))))
    calls: list[tuple[str, str]] = []
    results = run_books(cb, tuple(recording(spec, calls) for spec in THROUGH_11))
    assert [result.book for result in results] == ["ASC606", "LEGACY"]
    assert {book for _, book in calls} == {"ASC606"}  # no stage 02 to 12 for LEGACY (RCP-14)
    # Stages 06 to 08 fold as one step through BOUNDARY_HANDLERS, not through their entries.
    assert [stage for stage, _ in calls] == ["02", "03", "04", "05", "09", "10", "11"]
    legacy = results[1]
    assert isinstance(legacy.state, legacy_book.LegacyState)
    assert {node.measure for node in legacy.trace.nodes} == {"pre_standard_revenue_cum"}
    assert_reevaluates(legacy.trace)
    # Signed pre-standard amounts only: the delivery and the 1,000.00 invoice fold nothing.
    by_period = targets_by_period(legacy.state, SUBJECT)
    assert by_period == {f"FY2026-P{month:02d}": 120000 if month < 3 else 100000
                         for month in range(1, 13)}  # fmt: skip
    node = next(
        n for n in legacy.trace.nodes if n.id == f"pre_standard_revenue_cum:{SUBJECT}:FY2026-P03"
    )
    assert (node.value, node.formula_id) == ("1000.00", "books.legacy_fold.v1")
    assert [
        (ref.ref_id, ref.detail["value"]) for ref in node.inputs if isinstance(ref, SourceRef)
    ] == [
        (f"{CONTRACT}/EV-000005", "1200.00"),
        (f"{CONTRACT}/EV-000006", "-200.00"),
    ]
    assert legacy.state.posting is None and legacy.state.posting_intents == ()


def test_s13_r10_pre_standard_cum_on_primary_versions() -> None:
    # Version 1: every event is new; pre-standard revenue 1,200.00 then (200.00) on 15 March.
    first = stream(pre_standard(6, date(2026, 3, 15), "-200.00"))
    cb = canonical(world(first))
    results = run_books(cb, FOLD)
    primary = results[0]
    ctx = book_context(cb, cb.books["LEGACY"])
    (measures,) = primary.pre_standard
    assert (measures.subject_key, measures.as_of) == (SUBJECT, date(2026, 3, 15))
    assert (measures.cumulative, measures.amount) == (100000, 100000)
    assert measures.cumulative == legacy_book.fold_at(ctx, cb, SUBJECT, measures.as_of)
    legacy = results[1].state
    assert isinstance(legacy, legacy_book.LegacyState)
    assert targets_by_period(legacy, SUBJECT)["FY2026-P03"] == measures.cumulative
    nodes = {node.id: node for node in primary.trace.nodes}
    assert nodes[measures.trace_nodes["pre_standard_revenue_cum"]].value == "1000.00"
    assert nodes[measures.trace_nodes["pre_standard_revenue_amount"]].value == "1000.00"
    assert_reevaluates(primary.trace)

    # Version 2: only a modification on 15 April is new. It carries no pre-standard amount, so the
    # amount is 0 and the cumulative rolls on every obligation version (DEV-050, DEV-051).
    addon = {
        "obligation_key": "POB-02",
        "action": "ADD",
        "product_code": "SKU-KIT2",
        "quantity_delta": Decimal("1"),
        "consideration_delta": Decimal("500.00"),
        "start_date": date(2026, 4, 15),
        "end_date": date(2026, 4, 15),
    }
    modification = ModificationInput(
        modification_key="MOD-02",
        effective_date=date(2026, 4, 15),
        kind="ADD_OBLIGATION",
        template_mode=None,
        status="APPLIED",
        reference=None,
        questionnaire={},
        lines=(addon,),
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
    payload = {
        "modification_id": "MOD-02",
        "treatments": {"POB-01": "PROSPECTIVE", "POB-02": "PROSPECTIVE"},
        "lines": [addon],
        "ssp_basis": {},
    }
    amended = bundles.event(
        CONTRACT, 7, "CONTRACT_AMENDED", date(2026, 4, 15), payload, obligation_keys=["POB-02"]
    )
    later = canonical(
        world([*first, amended], heads=((CONTRACT, 6),), modifications=(modification,))
    )
    version = run_books(later, FOLD)[0]
    assert [(m.subject_key, m.as_of, m.cumulative, m.amount) for m in version.pre_standard] == [
        (SUBJECT, date(2026, 4, 15), 100000, 0),
        (ADDED, date(2026, 4, 15), 0, 0),
    ]
    nodes = {node.id: node for node in version.trace.nodes}
    assert nodes[f"pre_standard_revenue_amount:{SUBJECT}:-"].inputs == ()
    assert nodes[f"pre_standard_revenue_cum:{SUBJECT}:-"].value == "1000.00"
    assert_reevaluates(version.trace)
    # A bundle without the LEGACY book publishes zero pre-standard measures with their own nodes
    # citing no event, so the T-CON-11 zero columns link a node (DG-KRN-EXP-01; D-97 (8)).
    gross = run_books(canonical(world(first, books=("ASC606",))), FOLD)
    (only,) = gross
    assert only.book == "ASC606"
    assert [(m.subject_key, m.cumulative, m.amount) for m in only.pre_standard] == [(SUBJECT, 0, 0)]
    zero_nodes = {node.id: node for node in only.trace.nodes}
    (zero,) = only.pre_standard
    assert zero_nodes[zero.trace_nodes["pre_standard_revenue_cum"]].inputs == ()
    assert zero_nodes[zero.trace_nodes["pre_standard_revenue_cum"]].value == "0.00"


def test_s13_r11_legacy_output_shape() -> None:
    cb = canonical(world(stream()))
    legacy, trace, _ = legacy_posting(cb)
    output = legacy_book.book_output("LEGACY", legacy, trace)
    assert output.book_code == "LEGACY"
    assert output.contract_version is None
    empty = (
        output.status_in_book,
        output.obligation_versions,
        output.balances,
        output.schedules,
        output.cost_asset_versions,
        output.loss_provision_versions,
        output.fx_layer_movements,
        output.proposals,
        output.time_triggers,
    )
    assert empty == ((),) * 9
    assert output.posting_intents == legacy.posting_intents and len(output.posting_intents) == 1
    assert output.trace is trace
    assert {node.measure for node in trace.nodes} == {
        "account_resolution",
        "posting_delta",
        "posting_target",
        "pre_standard_revenue_cum",
    }
    assert_reevaluates(trace)


def test_s13_inv_02_no_revenue_in_legacy() -> None:
    cb = canonical(world(stream(pre_standard(6, date(2026, 3, 15), "-200.00"))))
    legacy, _, allocated = legacy_posting(cb)
    roles = {line.account_role for intent in legacy.posting_intents for line in intent.lines}
    assert roles == {CL, PRE}  # no REVENUE intent
    assert {intent.book_code for intent in legacy.posting_intents} == {"LEGACY"}
    assert {(t.book_code, t.measure) for t in legacy.targets} == {
        (BookCode.LEGACY, "pre_standard_revenue_cum")
    }  # no primary-book target
    # The March reduction posts the reverse lines: Dr CL / Cr PRE_STANDARD_REVENUE 200.00.
    march = [i for i in legacy.posting_intents if i.posting_period_key == "FY2026-P03"]
    assert signed(march) == {(PRE, "4900"): -20000, (CL, "2100"): 20000}
    # JET-15 is a LEGACY template: a framework book refuses pre-standard inputs (POLICIES R6).
    ctx = book_context(cb, cb.books["ASC606"])
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    inputs = PartInputs(pre_standard=legacy.targets)
    fx = s12_fx_entities.run(ctx, _Costs(allocated, FxFlows(()), inputs), tb, rates=RateIndex(()))
    with pytest.raises(ValueError, match="JET-15"):
        s14_posting.run(ctx, fx, tb, posted=PostedIndex(()))
    december = sum(t.value for t in legacy.targets if t.period_key == "FY2026-P12")
    assert format_money(december, 2) == "1000.00"
