"""Stage 13 book loop, stage keys and framework switches (ENGINE_SPEC_B §13.2.1 to §13.2.3; END-7).

EX-13-B folds the CHK-131 world (EX-11-A) through the real stages 01 to 11 for ``ASC606`` and
``IFRS15``, books whose resolved values are equal for every key of stages 02 to 10 and differ in
POL-144. Stage 12 reads the stage 09 to 11 flows that bind with END-9 (L2-5-Q-21), stage 14 reads
the stage 12 state, and stage 15 lands with EDS-1, so stages 12, 14 and 15 are recording stand-ins
that pass their state on (D-81). No database (DG-TST-18).
"""

from __future__ import annotations

import ast
import dataclasses
import functools
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest
from erev_api.registry.policies import POLICY_PARAMETERS
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    BookInput,
    EntityInput,
    EstimateVersionInput,
    EventInput,
    InputBundle,
    PeriodInput,
    ResolvedPolicyInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.enums import BookCode
from erev_engine.errors import EngineError
from erev_engine.stages import STAGES, StageSpec, s01_canonicalize, s13_books
from erev_engine.stages.s11_costs_loss import CostLossState
from erev_engine.stages.s13_books import book_context, memo, run_books
from erev_engine.stages.s13_books.switches import IFRS15_SWITCHES, Switch
from erev_engine.stages.state import AllocatedState, CanonicalBundle, PolicyResolver
from erev_engine.trace import Trace, TraceBuilder, TraceNode, reevaluate
from support import bundles
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.runners import _build_checkpoint_bundles
from support.fold import fold_trace
from support.recognition import estimate_version, usd

CONTRACT = "K-131"
ENTITY = bundles.ENTITY_CODE
INCEPTION = date(2026, 1, 1)
KNOWN_AT = datetime(2029, 12, 31, 23, tzinfo=UTC)
ZERO_SHA = "0" * 64
ALIAS_PARAMS = ("alias_of_book", "stage_key")
STAGES_ROOT = Path(__file__).resolve().parents[3] / "erev_engine" / "stages"
FOLD = tuple(spec for spec in STAGES if spec.stage <= "08")
THROUGH_11 = tuple(spec for spec in STAGES if spec.stage <= "11")

Calls = list[tuple[str, str]]


# --- The CHK-131 world as an input bundle (EX-11-A; ENGINE_SPEC_B §11.7) -------------------------


def annual(books: Sequence[str] = ("ASC606", "IFRS15"), years: int = 4) -> EntityInput:
    """One accounting period per calendar year from 2026, open in every book."""
    periods = tuple(
        PeriodInput(
            f"FY{year}-P01",
            year,
            1,
            date(year, 1, 1),
            date(year, 12, 31),
            tuple((code, "open") for code in sorted(books)),
        )
        for year in range(2026, 2026 + years)
    )
    return EntityInput(ENTITY, "USD", "America/New_York", "MONTHLY", periods)


TEMPLATE = TemplateInput(
    template_code="TPL-SVC",
    version_key="TPL-SVC@v1",
    version_no=1,
    content_sha256=ZERO_SHA,
    obligation_kind="STANDARD",
    distinctness="distinct",
    series_increment_unit=None,
    satisfaction_pattern="OVER_TIME",
    over_time_criterion="OT_A",
    recognition_method="TIME_ELAPSED",
    ratable_convention="MONTHLY_EVEN",
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


def point_version(points: Mapping[str, str]) -> SspVersionInput:
    """SSP-US v1: an observable point per product in USD (T-REF-31)."""
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


MONTHLY_EVEN = ResolvedPolicyInput(
    "recognition.time_convention", "ENTITY", ENTITY, "MONTHLY_EVEN", "E", "OVR-TEST", "K"
)


def book(
    code: str,
    calendar: EntityInput,
    *,
    entities: Sequence[str] = (ENTITY,),
    replace: Mapping[str, str | Mapping[str, str]] | None = None,
) -> BookInput:
    """The DEFAULT policy set with an entity-level MONTHLY_EVEN convention and the values of
    ``replace`` at every scope of their codes."""
    changes = replace or {}
    resolved = [
        dataclasses.replace(policy, value=changes[policy.code])
        if policy.code in changes
        else policy
        for policy in bundles.policy_set(entity=calendar)
    ]
    resolved.append(MONTHLY_EVEN)
    ordered = tuple(sorted(resolved, key=lambda p: (p.code, p.scope, p.subject_key)))
    return BookInput(code, code == "ASC606", tuple(entities), ordered, bundles.account_mapping())


def estimate_event(stream: int, version: EstimateVersionInput) -> EventInput:
    payload = {"estimate_version_id": version.version_key}
    event = bundles.event(CONTRACT, stream, "ESTIMATE_CHANGED", version.effective_date, payload)
    return dataclasses.replace(event, estimate_version_key=version.version_key)


def cost(stream: int, when: date, purpose: str, amount: str, **members: object) -> EventInput:
    payload: dict[str, object] = {"purpose": purpose, "amount": Decimal(amount), **members}
    named = members.get("obligation_key")
    keys = [] if named is None else [str(named)]
    return bundles.event(CONTRACT, stream, "COST_INCURRED", when, payload, obligation_keys=keys)


def chk_131(books: Sequence[BookInput], calendar: EntityInput) -> InputBundle:
    """CHK-131: services of 150,000.00 over 2026 and 2027; a cost to obtain of 40,000.00 amortised
    over 48 months with 25,000.00 of anticipated renewals; EAC 170,000.00 from 31 December 2026
    with 85,000.00 of costs in each year."""
    header = bundles.contract(CONTRACT, inception=INCEPTION)
    line = bundles.booking_line(
        "P1",
        product_code="SKU-SVC",
        quantity="1",
        total_price="150000.00",
        start=INCEPTION,
        end=date(2027, 12, 31),
    )
    renewal = dataclasses.replace(
        estimate_version(f"{CONTRACT}/AMORT", "RENEWAL_EXPECTATION", 1, INCEPTION),
        amortization_months=48,
        expected_total_amount=Decimal("25000.00"),
    )
    eac = dataclasses.replace(
        estimate_version(f"{CONTRACT}/EAC", "EAC", 1, date(2026, 12, 31)),
        expected_total_amount=Decimal("170000.00"),
    )
    events = [
        bundles.event(
            CONTRACT, 1, "CONTRACT_BOOKED", INCEPTION, {"lines": [line]}, obligation_keys=["P1"]
        ),
        estimate_event(2, renewal),
        cost(3, INCEPTION, "COST_TO_OBTAIN", "40000.00", plan_code="COMM-131", is_incremental=True),
        cost(4, date(2026, 12, 31), "PROGRESS_INPUT", "85000.00", obligation_key="P1"),
        estimate_event(5, eac),
        cost(6, date(2027, 12, 31), "PROGRESS_INPUT", "85000.00", obligation_key="P1"),
        bundles.event(CONTRACT, 7, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}}),
    ]
    order = s13_books.BOOK_ORDER
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=KNOWN_AT,
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=tuple(sorted(books, key=lambda item: order.index(item.book_code))),
        entities=(calendar,),
        group=bundles.group(
            (header,), products=(bundles.product("SKU-SVC", template_code="TPL-SVC", family=None),)
        ),
        contracts=(header,),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(point_version({"SKU-SVC": "150000.00"}),),
        pob_template_versions=(TEMPLATE,),
        rule_set_versions=(),
        estimate_versions=(renewal, eac),
        fx_rates=(),
        posted=(),
    )


def ex_13_b(books: Sequence[str] = ("ASC606", "IFRS15")) -> tuple[CanonicalBundle, EntityInput]:
    calendar = annual(books)
    reversal = {"costs.impairment_reversal": "REQUIRED_CAPPED"}
    inputs = [
        book(code, calendar, replace=reversal if code == "IFRS15" else None) for code in books
    ]
    return canonical(chk_131(inputs, calendar)), calendar


def canonical(value: InputBundle) -> CanonicalBundle:
    return s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))


def recording(spec: StageSpec, calls: Calls) -> StageSpec:
    entry = spec.entry

    def run(ctx: object, state: object, tb: object, **bound: object) -> object:
        calls.append((spec.stage, str(ctx.book_code)))
        return entry(ctx, state, tb, **bound)

    return dataclasses.replace(spec, entry=run)


def stand_in(stage: str, package: str, calls: Calls) -> StageSpec:
    def run(ctx: object, state: object, tb: object, **bound: object) -> object:
        calls.append((stage, str(ctx.book_code)))
        return state

    return StageSpec(stage, package, run, (), ())


def assert_reevaluates(trace: Trace) -> None:
    """Posted nodes exactly; exact nodes within 1e-12 (stage 05 exact inputs, L2-2-Q-40)."""
    recomputed = reevaluate(trace)
    for node in trace.nodes:
        if node.rounding_residue is not None:
            assert recomputed[node.id] == node.value, node.id
        else:
            gap = abs(Fraction(Decimal(recomputed[node.id])) - Fraction(Decimal(node.value)))
            assert gap <= Fraction(1, 10**12), (node.id, node.value, recomputed[node.id])


def unaliased(node: TraceNode) -> tuple[object, ...]:
    params = {name: value for name, value in node.params.items() if name not in ALIAS_PARAMS}
    return (node.value, node.formula_id, node.inputs, params)


# --- Tests ---------------------------------------------------------------------------------------


def test_ex_13_b_stage_keys_and_aliases() -> None:
    cb, _ = ex_13_b()
    calls: Calls = []
    stages = (
        *(recording(spec, calls) for spec in THROUGH_11),
        stand_in("12", "s12_fx_entities", calls),
        stand_in("14", "s14_posting", calls),
        stand_in("15", "s15_disclosures", calls),
    )
    us, ifrs = run_books(cb, stages)
    assert (us.book, ifrs.book) == ("ASC606", "IFRS15")
    us_keys = memo.chain(cb, book_context(cb, cb.books["ASC606"]), stages)
    ifrs_keys = memo.chain(cb, book_context(cb, cb.books["IFRS15"]), stages)
    shared = [
        stage for (stage, key), (_, other) in zip(us_keys, ifrs_keys, strict=True) if key == other
    ]
    assert shared == ["02", "03", "04", "05", "06", "07", "08", "09", "10"]

    # Stages 02 to 10 run once, for ASC606; stages 11, 12, 14 and 15 run again for IFRS15.
    assert [stage for stage, code in calls if code == "ASC606"] == [
        "02", "03", "04", "05", "09", "10", "11", "12", "14", "15"
    ]  # fmt: skip
    assert [stage for stage, code in calls if code == "IFRS15"] == ["11", "12", "14", "15"]

    # The IFRS15 book aliases the nodes of stages 02 to 10 with alias_of_book and stage_key.
    us_nodes = {node.id: node for node in us.trace.nodes}
    aliased = {node.id: node for node in ifrs.trace.nodes if "alias_of_book" in node.params}
    own = {node.id: node for node in ifrs.trace.nodes if "alias_of_book" not in node.params}
    assert aliased and own
    assert set(aliased) | set(own) == set(us_nodes) and not set(aliased) & set(own)
    keys = dict(us_keys)
    shared_keys = {keys[stage] for stage in ("02", "03", "04", "05", "08", "09", "10")}
    for node_id, node in aliased.items():
        assert node.params["alias_of_book"] == "ASC606", node_id
        assert node.params["stage_key"] in shared_keys, node_id
        assert unaliased(node) == unaliased(us_nodes[node_id]), node_id
    assert not any("alias_of_book" in node.params for node in us.trace.nodes)
    assert_reevaluates(ifrs.trace)

    # The Year 2 reversal of 10,000.00 exists only in the IFRS15 book (EX-11-A; CHK-131).
    us_state, ifrs_state = us.state, ifrs.state
    assert isinstance(us_state, CostLossState) and isinstance(ifrs_state, CostLossState)
    assert {m.impairment_reversed_cum for m in us_state.cost_asset_measures.values()} == {0}
    (asset,) = {key for (key, _), m in ifrs_state.cost_asset_measures.items() if m.impaired_cum}
    year_2 = (asset, "FY2027-P01")
    ifrs_2 = ifrs_state.cost_asset_measures[year_2]
    assert (ifrs_2.impairment_reversed_cum, ifrs_2.carrying_amount) == (
        usd("10000.00"),
        usd("20000.00"),
    )
    assert us_state.cost_asset_measures[year_2].carrying_amount == usd("10000.00")
    reversal = own[f"cost_impairment_reversed_cum:{asset}:FY2027-P01"]
    assert reversal.value == "10000.00"
    # The reused stage 02 state carries the IFRS15 label (L3-2-Q-6).
    (contract,) = ifrs_state.allocated.contracts
    assert set(contract.status_in_book) == {BookCode.IFRS15}


def test_s13_r01_book_order_and_entity_sets() -> None:
    books = ("ASC606", "IFRS15", "LEGACY")
    cb, calendar = ex_13_b(books)
    results = run_books(cb, FOLD, order=("LEGACY", "IFRS15", "ASC606"))
    assert [result.book for result in results] == ["ASC606", "IFRS15", "LEGACY"]
    us, ifrs, legacy = results
    assert isinstance(us.state, AllocatedState) and isinstance(ifrs.state, AllocatedState)
    assert us.state.obligations == ifrs.state.obligations
    # The LEGACY book folds its pre-standard revenue only, after the framework books (END-8).
    assert isinstance(legacy.state, s13_books.legacy_book.LegacyState)
    assert {node.measure for node in legacy.trace.nodes} == {"pre_standard_revenue_cum"}
    assert legacy.state.posting is None  # FOLD holds no stage 14
    # A book whose entity set is empty produces no result (POL-007).
    idle = [
        book("ASC606", calendar),
        book("IFRS15", calendar, entities=()),
        book("LEGACY", calendar),
    ]
    found = run_books(canonical(chk_131(idle, calendar)), FOLD)
    assert [result.book for result in found] == ["ASC606", "LEGACY"]


def module_state() -> dict[tuple[str, str], object]:
    """Every mutable module-level container of ``erev_engine`` with its content (DG-ENG-08)."""
    found: dict[tuple[str, str], object] = {}
    for name, module in sorted(sys.modules.items()):
        if name != "erev_engine" and not name.startswith("erev_engine."):
            continue
        members = vars(module)
        found[(name, "__names__")] = tuple(sorted(members))
        for attribute, value in members.items():
            assert not hasattr(value, "cache_info"), f"{name}.{attribute} caches (DG-ENG-08)"
            if isinstance(value, dict):
                found[(name, attribute)] = list(value.items())
            elif isinstance(value, list | set | bytearray):
                found[(name, attribute)] = list(value)
    return found


def test_s13_r02_memo_scoped_to_call(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[memo.Memo] = []

    class Recording(memo.Memo):
        __slots__ = ()

        def __init__(self) -> None:
            super().__init__()
            created.append(self)

    monkeypatch.setattr(s13_books, "Memo", Recording)
    cb, _ = ex_13_b()
    before = module_state()
    first = run_books(cb, FOLD)
    second = run_books(cb, FOLD)
    assert len(created) == 2 and created[0] is not created[1]
    # Stages 02 to 05, the boundary fold and the post-stage output step (pre-standard measures and
    # T-CON-08 output measures, memoised like a stage so an equal-policy book aliases its nodes;
    # S13-INV-01, lane ENG-T1F) are computed once per call, by ASC606.
    assert [entry.book_code for entry in created[0].entries()] == ["ASC606"] * 6
    outputs = [{id(entry.output) for entry in item.entries()} for item in created]
    assert outputs[0] and not outputs[0] & outputs[1]  # nothing crosses calls
    assert first == second
    assert module_state() == before


# S13-R-06: modules comparing the book with a book literal. Stages with the Table 13-A `book_code`
# member may; otherwise only a guard restating a FORCED IFRS15 value (POLICIES §6.2 rows 3 and 14,
# the business-combination row) may.
FORCED_GUARDS: Mapping[str, tuple[str, ...]] = {
    "s03_pob_builder/elections.py": (
        "franchisor.preopening_expedient",
        "pob.immaterial_promise_relief",
    ),
    "s07_onboarding/__init__.py": ("bc.acquired_contract_measurement",),
    "s07_onboarding/opening.py": ("bc.acquired_contract_measurement",),
}


@functools.cache
def book_branches() -> tuple[str, ...]:
    literals = {code.value for code in BookCode}
    found: set[str] = set()
    for path in sorted(STAGES_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            operands = [node.left, *node.comparators]
            reads = any(
                isinstance(item, ast.Attribute) and item.attr in ("book_code", "framework")
                for item in operands
            )
            literal = any(
                (isinstance(item, ast.Constant) and item.value in literals)
                or (
                    isinstance(item, ast.Attribute)
                    and isinstance(item.value, ast.Name)
                    and item.value.id == "BookCode"
                )
                for item in operands
            )
            if reads and literal:
                found.add(path.relative_to(STAGES_ROOT).as_posix())
    return tuple(sorted(found))


ROWS = tuple(switch for switch in IFRS15_SWITCHES if switch.row != "extra")


@pytest.mark.parametrize("switch", ROWS, ids=[f"row-{switch.row}" for switch in ROWS])
def test_s13_r06_ifrs_switch_list(switch: Switch) -> None:
    assert [item.row for item in ROWS] == [str(number) for number in range(1, 19)]
    calendar = bundles.entity(books=("ASC606", "IFRS15"))
    resolver = PolicyResolver(bundles.policy_set("DEFAULT", book_code="IFRS15", entity=calendar))
    period = calendar.periods[0].period_key
    declared = {spec.stage: spec.policy_keys for spec in STAGES}
    for code, literal in switch.ifrs15.items():
        spec = POLICY_PARAMETERS[code]
        assert spec.pol_id in switch.pol_ids, code
        if spec.pin == "P":
            value = resolver.value(code, entity=calendar.code, period=period)
        else:
            value = resolver.value(code)
        if literal is not None:
            assert value == literal, code
        for stage in switch.stages:
            assert code in memo.STAGE_POLICY_KEYS[stage], (code, stage)
            if stage in declared:  # the stage declares the key it reads through ctx.policies
                assert code in declared[stage], (code, stage)
    book_stages = {
        stage for stage, members in memo.STAGE_CONTEXT_MEMBERS.items() if "book_code" in members
    }
    branches = book_branches()
    for module in branches:
        if module[1:3] in book_stages:
            continue
        assert module in FORCED_GUARDS, module
        for code in FORCED_GUARDS[module]:
            assert POLICY_PARAMETERS[code].is_forced_ifrs15, code
    assert set(FORCED_GUARDS) <= set(branches)


def test_s13_inv_04_book_order_independent() -> None:
    cb, _ = ex_13_b()
    forward = run_books(cb, THROUGH_11)
    swapped = run_books(cb, THROUGH_11, order=("IFRS15", "ASC606", "LEGACY"))
    assert [result.book for result in swapped] == ["ASC606", "IFRS15"]
    for first, second in zip(forward, swapped, strict=True):
        assert first.state == second.state, first.book
        assert {node.id: unaliased(node) for node in first.trace.nodes} == {
            node.id: unaliased(node) for node in second.trace.nodes
        }
    # The processing order only decides which book computes and which aliases.
    assert any(node.params.get("alias_of_book") == "ASC606" for node in forward[1].trace.nodes)
    assert any(node.params.get("alias_of_book") == "IFRS15" for node in swapped[0].trace.nodes)


def test_s13_inv_05_delta_requires_legacy_book() -> None:
    calendar = annual(("ASC606",))
    delta = book("ASC606", calendar, replace={"je.posting_mode": "DELTA"})
    with pytest.raises(EngineError) as raised:
        run_books(canonical(chk_131([delta], calendar)), FOLD)
    assert raised.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert (raised.value.detail["invariant"], raised.value.detail["book_code"]) == (
        "S13-INV-05",
        "ASC606",
    )
    assert raised.value.detail["scope"] == f"{ENTITY}@FY2026-P01"
    # With LEGACY in POL-007 for the entity and period the loop runs.
    calendar = annual(("ASC606", "LEGACY"))
    enabled = {"primary": "ASC606", "set": "ASC606,LEGACY"}
    replace = {"je.posting_mode": "DELTA", "books.enabled": enabled}
    books = [book("ASC606", calendar, replace=replace), book("LEGACY", calendar, replace=replace)]
    results = run_books(canonical(chk_131(books, calendar)), FOLD)
    assert [result.book for result in results] == ["ASC606", "LEGACY"]


# --- Boundary price nodes (CV-50; L4-3-Q-15; docs/reviews/loop/sprint/L5-3.md) -------------------


def test_cv_50_boundary_price_nodes_after_a_reallocating_estimate() -> None:
    """VC-CHK-110 at the end of Q2: the 30 June usage re-estimate reallocates (S08-R-03), and its
    price is traced as ``<column>@<event key>`` nodes, measured where stage 08 measured it. The
    inception version-state nodes that stage 05 cites keep 140,000.00; DG-AK-54 reads the latest
    basis node (L5-3-Q-2)."""
    loaded = load(ANSWER_KEY_ROOT / "vc" / "VC-CHK-110.yaml")
    checkpoint = next(c for c in _build_checkpoint_bundles(loaded) if c.name == "end-q2")
    (bundle,) = checkpoint.bundles
    state, trace = fold_trace(bundle, "ASC606")
    nodes = {node.id: node for node in trace.nodes}
    (estimate,) = [
        event
        for event in bundle.events
        if event.event_type == "ESTIMATE_CHANGED" and event.effective_date == date(2026, 6, 30)
    ]
    assert state.tp_history[-1].allocation_basis.posted == usd("120000.00")
    assert nodes["tp_allocation_basis:CG-C-USAGE:-"].value == "140000.00"
    basis = nodes[f"tp_allocation_basis@{estimate.event_key}:CG-C-USAGE:-"]
    price = nodes[f"transaction_price@{estimate.event_key}:CG-C-USAGE:-"]
    assert (basis.value, price.value) == ("120000.00", "120000.00")
    values = reevaluate(trace)
    assert (values[basis.id], values[price.id]) == (basis.value, price.value)
    # The inception estimate is part of the inception price, so it traces no boundary price.
    first = next(event for event in bundle.events if event.event_type == "ESTIMATE_CHANGED")
    assert f"transaction_price@{first.event_key}:CG-C-USAGE:-" not in nodes


def _boundary_price_nodes(
    key: str, checkpoint_name: str, event_type: str, group: str
) -> tuple[dict[str, TraceNode], Mapping[str, str], str, AllocatedState]:
    loaded = load(next(ANSWER_KEY_ROOT.rglob(f"{key}.yaml")))
    checkpoint = next(c for c in _build_checkpoint_bundles(loaded) if c.name == checkpoint_name)
    (bundle,) = checkpoint.bundles
    state, trace = fold_trace(bundle, "ASC606")
    (event,) = [item for item in bundle.events if item.event_type == event_type]
    return {node.id: node for node in trace.nodes}, reevaluate(trace), event.event_key, state


def test_l5_3_boundary_price_nodes_cite_the_consideration_an_exercise_adds() -> None:
    """MR-CHK-050-CONTINUATION after the exercise: the customer pays 300.00 more, which the price
    binding adds to the booking lines (S06-R-23). The boundary price is traced with the addition as
    a source reference of ``fixed_consideration@<event key>``, so the latest basis node holds
    1,300.00 where the inception node keeps 1,000.00 (CV-50, CV-53; L5-3-Q-17)."""
    group = "CG-C-CHK050"
    nodes, values, event_key, state = _boundary_price_nodes(
        "MR-CHK-050-CONTINUATION", "after-exercise", "MATERIAL_RIGHT_EXERCISED", group
    )
    assert state.tp_history[-1].allocation_basis.posted == usd("1300.00")
    assert nodes[f"tp_allocation_basis:{group}:-"].value == "1000.00"
    names = ("fixed_consideration", "transaction_price", "tp_allocation_basis")
    boundary = [nodes[f"{name}@{event_key}:{group}:-"] for name in names]
    assert [node.value for node in boundary] == ["1300.00", "1300.00", "1300.00"]
    assert [values[node.id] for node in boundary] == ["1300.00", "1300.00", "1300.00"]
    (added,) = [item for item in boundary[0].inputs if not isinstance(item, str)]
    assert (added.ref_type, added.ref_id) == ("contract_event", event_key)
    assert dict(added.detail) == {"member": "additional_consideration", "value": "300"}


def test_l5_3_boundary_price_nodes_cite_a_price_only_concession() -> None:
    """RND-CHK-003C after the credit: a modification without lines reduces the price by 100.00
    (S06-R-07, S06-R-09; L4-3-Q-12). The boundary basis is 200.00 and cites the event's
    ``price_change_amount`` (L5-3-Q-17)."""
    group = "CG-C-CREDIT"
    nodes, values, event_key, _ = _boundary_price_nodes(
        "RND-CHK-003C", "after-credit", "CONTRACT_AMENDED", group
    )
    assert nodes[f"tp_allocation_basis:{group}:-"].value == "300.00"
    basis = nodes[f"tp_allocation_basis@{event_key}:{group}:-"]
    assert (basis.value, values[basis.id]) == ("200.00", "200.00")
    fixed = nodes[f"fixed_consideration@{event_key}:{group}:-"]
    (added,) = [item for item in fixed.inputs if not isinstance(item, str)]
    assert dict(added.detail) == {"member": "price_change_amount", "value": "-100"}


# --- Modification proposals in the fold (S06-R-01; CV-16; docs/reviews/loop/sprint/L5-3.md) -------


def test_l5_3_fold_publishes_the_proposal_of_an_applied_amendment() -> None:
    """MOD-LEGACY-PROS-GT12: the June amendment applies the chosen legacy template, and the fold
    publishes the stage 06 proposal measured over the state before the event. POL-100
    ``USER_SELECTED_TEMPLATE`` with mode ``prospective`` proposes ``LEGACY_PROSPECTIVE`` for every
    obligation of the contract (S06-R-01; ENGINE_SPEC §6.2; L4-3-Q-23, L5-3-Q-18)."""
    loaded = load(ANSWER_KEY_ROOT / "mod" / "MOD-LEGACY-PROS-GT12.yaml")
    checkpoint = next(
        c for c in _build_checkpoint_bundles(loaded) if c.name == "end-june-after-prospective"
    )
    bundle = next(b for b in checkpoint.bundles if "Contract 1" in b.group.member_contract_keys)
    state, _ = fold_trace(bundle, "ASC606")
    (proposal,) = [p for p in state.proposals if p.kind == "MODIFICATION_TREATMENT"]
    assert (proposal.subject_key, proposal.summary) == ("Contract 1", "LEGACY_PROSPECTIVE")
    assert proposal.detail["modification_key"] == "MOD-C1-0615"
    assert dict(proposal.treatments) == {f"POB #{n}": "LEGACY_PROSPECTIVE" for n in (1, 2, 3, 4)}


def test_l5_3_fold_publishes_the_proposal_of_a_modification_no_event_applies() -> None:
    """MOD-S6-EX5-CASEA without its amendment event: the 30 added units priced at the modification
    date SSP are proposed as ``SEPARATE_CONTRACT`` (S06-R-04; EX-06-C). No event applies the
    modification, so the fold proposes it after the stream, and the price keeps 12,000.00
    (S06-R-03; L5-3-Q-18)."""
    loaded = load(ANSWER_KEY_ROOT / "mod" / "MOD-S6-EX5-CASEA.yaml")
    checkpoint = next(
        c for c in _build_checkpoint_bundles(loaded) if c.name == "after-modification"
    )
    (bundle,) = checkpoint.bundles
    events = tuple(event for event in bundle.events if event.event_type != "CONTRACT_AMENDED")
    state, _ = fold_trace(dataclasses.replace(bundle, events=events), "ASC606")
    (proposal,) = [p for p in state.proposals if p.kind == "MODIFICATION_TREATMENT"]
    assert (proposal.subject_key, proposal.summary) == ("C-EX5A", "SEPARATE_CONTRACT")
    assert proposal.detail["modification_key"] == "MOD-5A"
    assert dict(proposal.treatments) == {"L2-ADD": "SEPARATE_CONTRACT"}
    assert state.tp_history[-1].allocation_basis.posted == usd("12000.00")
