"""D-98 candidates 123 and 124 (ENGINE_SPEC 1.29; the supervisor's engineering rulings on Codex
production-20260921-0354 / -0327 §C; lane ENG-T1F): the six snapshot columns —
``original_ssp_selected``, ``original_unit_ssp``, ``original_total_contract_ssp``,
``original_stated_price``, ``original_total_contract_price``, ``allocation_weight`` — link the node
that produced the CURRENT value.

123: after an S06-R-26 repin the target publishes the corrected SSP (800) while its link was the
inception node (600); now the target links ``original_ssp_selected@<event>`` (stage 05's own
resolution emitted at the repin over the corrected version's canonical sources), its unit SSP over
that node, and every reallocated obligation links ``original_total_contract_ssp@<event>`` over the
repin's ``mod_weight@`` weight nodes; the inception nodes stay in the trace as history.

124: a created obligation had none of the six linked and ``allocation_weight`` = 0 by default; now
the creating boundary's ``<column>@<event>`` nodes over its own producers link them, and the weight
is the constructor's governed ratio w ÷ Σw (native: the added line's SSP over the pooled and added
boundary weights), never 0.

Whole-book ``check_book`` runs with NO exceptions on the repin fixture and on the native creation
world (the known reds of 123 / 124 are gone); per-column assertion sets collect every failure
before asserting (Codex 0354: whole-book checks that stop at the first failure prove nothing about
the dependents). The legacy and continuation constructors are stage-06 → stage-13 seams (the
assembler's ``_snapshot_links`` over the applied state), disclosed as such."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType, ModuleType

import pytest
from erev_engine import ENGINE_VERSION, _snapshot_links, compute
from erev_engine.bundle import BookOutput, InputBundle, ObligationVersionOut
from erev_engine.formulas import FORMULAS
from erev_engine.money import format_exact
from erev_engine.stages import s03_pob_builder, s06_modifications
from erev_engine.stages.s01_canonicalize import encode_key
from erev_engine.stages.s05_allocation import provenance
from erev_engine.stages.s13_books import _trace_boundary_price
from erev_engine.stages.state import AllocatedState, ObligationState
from erev_engine.trace import SourceRef, TraceBuilder, TraceNode, reevaluate
from support import trace_linkage

S06_TESTS = Path(__file__).resolve().parents[1] / "s06_modifications"
NO_EXCEPTIONS = MappingProxyType(
    {
        "obligation_version": frozenset(),
        "contract_version": frozenset(),
        "contract_version_balance": frozenset(),
    }
)
SIX = (
    "original_ssp_selected",
    "original_unit_ssp",
    "original_total_contract_ssp",
    "original_stated_price",
    "original_total_contract_price",
    "allocation_weight",
)


def _module(name: str) -> ModuleType:
    if str(S06_TESTS) not in sys.path:
        sys.path.insert(0, str(S06_TESTS))
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, S06_TESTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _book(bundle: InputBundle) -> BookOutput:
    output = compute(bundle)
    return next(item for item in output.books if item.book_code == "ASC606")


def _version(book: BookOutput, key: str) -> ObligationVersionOut:
    return next(item for item in book.obligation_versions if item.columns["obligation_key"] == key)


def _failures(
    version: ObligationVersionOut,
    nodes: dict[str, TraceNode],
    event_key: str,
    expected_columns: tuple[str, ...],
    currency: str,
) -> list[str]:
    """Every failure of the per-column contract for ``expected_columns`` (link present, names the
    boundary node of ``event_key``, holds the value, subject, currency class), collected."""
    found: list[str] = []
    for column in expected_columns:
        held = version.columns.get(column)
        link = version.trace_nodes.get(column)
        if link is None:
            found.append(f"{column}: unlinked (value {held!r})")
            continue
        node = nodes.get(link)
        if node is None:
            found.append(f"{column}: link {link} not in the trace")
            continue
        if not node.measure.startswith(f"{column}@{event_key}"):
            found.append(f"{column}: link {link} is not the boundary node of {event_key}")
        if not link.endswith(f":{version.subject_key}:-"):
            found.append(f"{column}: link {link} is not the obligation's version-state node")
        if column == "allocation_weight":
            if node.currency is not None:
                found.append(f"{column}: dimensionless node carries currency {node.currency!r}")
        elif node.currency != currency:
            found.append(f"{column}: node currency {node.currency!r} != {currency!r}")
        exact = Fraction(node.value) + Fraction(node.rounding_residue or 0)
        if isinstance(held, int) and not isinstance(held, bool):
            if Fraction(node.value) * 10 ** int(node.params.get("minor_unit", "0")) != held:
                found.append(f"{column}: node {node.value} != column {held}")
        elif isinstance(held, Fraction):
            if abs(exact - held) > Fraction(1, 2 * 10**18):
                found.append(f"{column}: node {node.value} != column {held}")
        else:
            found.append(f"{column}: unexpected column type {type(held).__name__}")
    return found


def test_repin_links_the_corrected_ssp_and_its_dependents_whole_book() -> None:
    """123 on the admitted A / B repin fixture: whole-book check_book passes with NO exceptions;
    A links original_ssp_selected@<repin> (800; ssp.point.v1 over the corrected version's
    canonical ssp_entry sources) and original_unit_ssp@<repin> (800 ÷ 1); A and B link
    original_total_contract_ssp@<repin> (1,200 over the two mod_weight@ nodes); the inception
    node (600) is retained and is not the link; the trace replays."""
    exercise = _module("test_s06_exercise")
    bundle = exercise.attribute_bundle()
    book = _book(bundle)
    nodes = {node.id: node for node in book.trace.nodes}
    currency = bundle.group.transaction_currency
    a, b = _version(book, "A"), _version(book, "B")
    (repin,) = [
        node_id
        for node_id in nodes
        if node_id.startswith("mod_share@") and node_id.endswith(f":{a.subject_key}:-")
    ]
    event_key = repin[len("mod_share@") : -len(f":{a.subject_key}:-")]
    assert a.columns["original_ssp_selected"] == 800
    assert nodes[f"original_ssp_selected:{a.subject_key}:-"].value == "600"  # history, kept
    dependents = ("original_ssp_selected", "original_unit_ssp", "original_total_contract_ssp")
    failures = _failures(
        a,
        nodes,
        event_key,
        ("original_ssp_selected", "original_unit_ssp", "original_total_contract_ssp"),
        currency,
    )
    failures += _failures(b, nodes, event_key, ("original_total_contract_ssp",), currency)
    assert failures == [], failures
    selected = nodes[a.trace_nodes["original_ssp_selected"]]
    assert selected.formula_id == "ssp.point.v1" and selected.value == "800"
    assert all(
        isinstance(item, SourceRef) and item.ref_type == "ssp_entry" for item in selected.inputs
    )
    assert b.trace_nodes["original_ssp_selected"] == f"original_ssp_selected:{b.subject_key}:-"
    total = nodes[a.trace_nodes["original_total_contract_ssp"]]
    assert set(total.inputs) == {
        f"mod_weight@{event_key}:{a.subject_key}:-",
        f"mod_weight@{event_key}:{b.subject_key}:-",
    }
    assert (
        a.columns["original_total_contract_ssp"] == 1200 == b.columns["original_total_contract_ssp"]
    )
    unit = nodes[a.trace_nodes["original_unit_ssp"]]
    assert unit.inputs == (
        a.trace_nodes["original_ssp_selected"],
        f"original_quantity:{a.subject_key}:-",
    )
    trace_linkage.check_book(book, bundle, exceptions=NO_EXCEPTIONS)  # the 123 red is gone
    replayed = reevaluate(book.trace)
    for version in (a, b):
        for column in dependents:
            node_id = version.trace_nodes[column]
            assert replayed[node_id] == nodes[node_id].value


def test_native_created_obligation_links_all_six_and_carries_its_ratio_whole_book() -> None:
    """124 on ex_09_a (POB-02 added 16 Sep 2026 for 60,000.00): the six columns link the creating
    boundary's nodes; allocation_weight is the added line's SSP over the pooled + added boundary
    weights (non-zero), valued as the ratio of the traced weights; the stated price echoes the
    boundary state's stated_price@ node, the total price echoes the boundary's transaction_price@
    build-up traced by stage 13;
    whole-book check_book passes with NO exceptions; the trace replays."""
    prospective = _module("test_s06_prospective")
    bundle = prospective.ex_09_a()
    book = _book(bundle)
    nodes = {node.id: node for node in book.trace.nodes}
    currency = bundle.group.transaction_currency
    added = _version(book, "POB-02")
    subject = added.subject_key
    (producer,) = [
        node_id
        for node_id in nodes
        if node_id.startswith("mod_share@") and node_id.endswith(f":{subject}:-")
    ]
    event_key = producer[len("mod_share@") : -len(f":{subject}:-")]
    failures = _failures(added, nodes, event_key, SIX, currency)
    assert failures == [], failures
    weight = nodes[added.trace_nodes["allocation_weight"]]
    own, total = weight.inputs
    assert own == f"mod_weight@{event_key}:{subject}:-"
    assert total == added.trace_nodes["original_total_contract_ssp"]
    assert weight.formula_id == "alloc.original_weight.v1"
    raw = Fraction(weight.params["weight"]) / Fraction(weight.params["total"])  # the raw ratio
    assert raw == Fraction(77500, 232500) != 0 and weight.value == format_exact(raw)
    assert added.columns["allocation_weight"] == Fraction(weight.value)  # the node's encoding
    assert Fraction(nodes[own].value) == 77500  # SSP-US@v2 SKU-SEATS 77,500.00 at the boundary
    assert Fraction(nodes[total].value) == 155000 + 77500  # the pooled remaining SSP + the added
    stated = nodes[added.trace_nodes["original_stated_price"]]
    assert stated.formula_id == "input.echo.v1"
    assert stated.inputs == (f"stated_price@{event_key}:{subject}:-",)  # the boundary state's node
    assert f"stated_price:{subject}:-" not in nodes  # the draft's stage 03 node is NOT re-emitted
    price = nodes[added.trace_nodes["original_total_contract_price"]]
    assert price.formula_id == "input.echo.v1"
    (price_input,) = price.inputs
    assert isinstance(price_input, str) and price_input.startswith(
        f"transaction_price@{event_key}:"
    )
    selected = nodes[added.trace_nodes["original_ssp_selected"]]
    assert selected.formula_id == "ssp.point.v1" and Fraction(selected.value) == 77500
    trace_linkage.check_book(book, bundle, exceptions=NO_EXCEPTIONS)  # the 124 red is gone
    replayed = reevaluate(book.trace)
    for column in SIX:
        node_id = added.trace_nodes[column]
        assert replayed[node_id] == nodes[node_id].value


def _trace_price_as_stage_13(
    ctx: object, identified: object, after: AllocatedState, ev: object, tb: TraceBuilder
) -> None:
    """What stage 13's fold does right after a boundary handler: trace the boundary price
    build-up and emit the created obligations' reserved total-price echoes (the seam otherwise
    stops at the handler)."""
    scratch = TraceBuilder(engine_version=ENGINE_VERSION)
    pob = s03_pob_builder.run(ctx, identified, scratch)  # type: ignore[arg-type]
    _trace_boundary_price(ctx, pob, after, ev, tb)  # type: ignore[arg-type]
    group = encode_key(pob.group_key)
    price_node = f"transaction_price@{ev.event_key}:{group}:-"  # type: ignore[attr-defined]
    provenance.emit_price_echoes(
        ctx,  # type: ignore[arg-type]
        tb,
        ev,  # type: ignore[arg-type]
        after.obligations,
        total=after.tp_history[-1].total,
        price_node=price_node,
    )


def _seam_failures(
    ob: ObligationState, after: AllocatedState, tb: TraceBuilder, event_key: str, currency: str
) -> tuple[list[str], dict[str, str]]:
    """The assembler's own link selection over the applied stage 06 state (a seam, not whole-engine
    execution): the six stamped links resolve, name the boundary's nodes and hold the values."""
    nodes = {node.id: node for node in tb.build(root_measures={}).nodes}
    columns: dict[str, object] = {
        "original_ssp_selected": ob.ssp.selected if ob.ssp is not None else Fraction(0),
        "original_unit_ssp": None
        if ob.ssp is None or ob.original_quantity == 0
        else ob.ssp.selected / ob.original_quantity,
        "original_total_contract_ssp": ob.original_total_contract_ssp,
        "original_stated_price": round(ob.original_stated_price * 100),
        "original_total_contract_price": round(ob.original_total_contract_price * 100),
        "allocation_weight": None,
    }
    minor_unit = 2
    weight_node = nodes.get(ob.snapshot_producer_links.get("allocation_weight", ""))
    if weight_node is not None:
        columns["allocation_weight"] = Fraction(weight_node.value)
    links = _snapshot_links(ob, after, columns, nodes, minor_unit)
    failures: list[str] = []
    for column in SIX:
        if columns[column] is None:
            continue
        link = links.get(column)
        if link is None:
            failures.append(f"{column}: unlinked")
            continue
        if not link.startswith(f"{column}@{event_key}:{ob.subject_key}:"):
            failures.append(f"{column}: {link} is not the boundary's node")
        node = nodes[link]
        if column != "allocation_weight" and node.currency != currency:
            failures.append(f"{column}: currency {node.currency!r}")
    return failures, links


def test_legacy_retrospective_created_obligation_links_all_six_seam() -> None:
    """124, constructor 2 (tc_rm_11: golden Contract 2 step 07, POB #4 added retrospectively):
    the six stamped links resolve through the assembler over the applied state; the weight is the
    template's own ratio (CRS + SSPDel) ÷ SSP_c re-evaluated from its parameters, the total the
    template's Σ RemSSP′; the nodes replay through their registered formula."""
    rm = _module("test_tc_rm")
    value = rm.golden_streams.stream("Contract 2", "07").input_bundle(preset="LEGACY_PARITY")
    software = rm.template_line(value, "POB #2", "1", "170")
    add = {
        **software,
        "obligation_key": "POB #4",
        "action": "ADD",
        "start_date": date(2023, 1, 1),
        "end_date": date(2023, 12, 31),
    }
    folded = rm.fold(
        rm.amended(
            value, "MOD-RM11", date(2023, 5, 15), "retrospective", [add], "LEGACY_RETROSPECTIVE"
        )
    )
    (ev,) = rm.amendments(folded.state)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = rm.apply(folded, folded.state, ev, tb)
    assert after.findings == ()
    _trace_price_as_stage_13(folded.ctx, folded.identified, after, ev, tb)
    added = rm.obligation(after, "POB #4")
    failures, links = _seam_failures(
        added, after, tb, ev.event_key, value.group.transaction_currency
    )
    assert failures == [], failures
    nodes = {node.id: node for node in tb.build(root_measures={}).nodes}
    weight = nodes[links["allocation_weight"]]
    assert weight.formula_id == "mod.legacy.retrospective.v1" and weight.params["role"] == "weight"
    assert Fraction(weight.value) != 0
    total = nodes[links["original_total_contract_ssp"]]
    assert total.params["role"] == "total_ssp"
    assert abs(Fraction(total.value) - added.original_total_contract_ssp) <= Fraction(1, 2 * 10**18)
    # per-node P14 (the seam's builder lacks the inception nodes the boundary price cites, so the
    # whole-trace ``reevaluate`` is the full-compute tests' matter): each stamped node replays
    for column in SIX:
        assert _exact_replay(nodes[links[column]], nodes) == nodes[links[column]].value


def test_material_right_continuation_good_links_all_six_seam() -> None:
    """124, constructor 3 (contract_3_exercised: the optioned good G): the six stamped links resolve
    through the assembler; the weight is G's weight over the optioned goods' weights (the posted /
    exact transfer budgets untouched), the total Σ of those weights; replay exact."""
    ex = _module("test_s06_exercise")
    value = ex.contract_3_exercised()
    folded = ex.fold_at(value, "MATERIAL_RIGHT_EXERCISED")
    st, ev = ex.after_step_12(folded.state), folded.amended
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s06_modifications.apply(
        folded.ctx, st, ev, tb, identified=folded.identified, price_at=ex.price_function("1300.00")
    )
    assert after.findings == ()
    _trace_price_as_stage_13(folded.ctx, folded.identified, after, ev, tb)
    known = {ob.subject_key for ob in st.obligations}
    created = [ob for ob in after.obligations if ob.subject_key not in known]
    assert created
    nodes = {node.id: node for node in tb.build(root_measures={}).nodes}
    for ob in created:
        failures, links = _seam_failures(
            ob, after, tb, ev.event_key, value.group.transaction_currency
        )
        assert failures == [], failures
        weight = nodes[links["allocation_weight"]]
        own, total = weight.inputs
        assert own == f"mod_weight@{ev.event_key}:{ob.subject_key}:-"
        assert total == links["original_total_contract_ssp"]
        assert weight.formula_id == "alloc.original_weight.v1"
        raw = Fraction(weight.params["weight"]) / Fraction(weight.params["total"])
        assert raw != 0 and weight.value == format_exact(raw)
        for column in SIX:
            if column in links:  # per-node P14 (see the legacy seam)
                assert _exact_replay(nodes[links[column]], nodes) == nodes[links[column]].value


def test_a_stamped_snapshot_producer_that_does_not_hold_the_column_is_refused() -> None:
    """Identity, then assertion: on the legacy seam, a published column that the stamped producer
    does not hold makes the assembler refuse (CV-50) — never a fallback to the stage 05 node,
    never a search for a node that happens to hold it."""
    from erev_engine.errors import EngineError

    rm = _module("test_tc_rm")
    value = rm.golden_streams.stream("Contract 2", "07").input_bundle(preset="LEGACY_PARITY")
    software = rm.template_line(value, "POB #2", "1", "170")
    add = {
        **software,
        "obligation_key": "POB #4",
        "action": "ADD",
        "start_date": date(2023, 1, 1),
        "end_date": date(2023, 12, 31),
    }
    folded = rm.fold(
        rm.amended(
            value, "MOD-RM11", date(2023, 5, 15), "retrospective", [add], "LEGACY_RETROSPECTIVE"
        )
    )
    (ev,) = rm.amendments(folded.state)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = rm.apply(folded, folded.state, ev, tb)
    added = rm.obligation(after, "POB #4")
    nodes = {node.id: node for node in tb.build(root_measures={}).nodes}
    assert "original_total_contract_ssp" in added.snapshot_producer_links
    columns: dict[str, object] = {
        "original_total_contract_ssp": added.original_total_contract_ssp + 1,  # not what it holds
    }
    with pytest.raises(EngineError) as refused:
        _snapshot_links(added, after, columns, nodes, 2)
    assert refused.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert refused.value.detail["rule"] == "CV-50"
    assert (
        refused.value.detail["node_id"]
        == added.snapshot_producer_links["original_total_contract_ssp"]
    )


def _exact_replay(node: TraceNode, nodes: dict[str, TraceNode]) -> str:
    """P14 for one node as ``reevaluate`` feeds it (exact inputs for the registered formulas)."""
    from erev_engine.formulas import EXACT_INPUT_FORMULAS
    from erev_engine.money import to_fraction

    values = []
    for item in node.inputs:
        if isinstance(item, SourceRef):  # a canonical source: its cited value (DG-KRN-EXP-04)
            values.append(to_fraction(item.detail.get("value", node.params.get("value", "0"))))
            continue
        cited = nodes[item]
        value = to_fraction(cited.value)
        if node.formula_id in EXACT_INPUT_FORMULAS and cited.rounding_residue is not None:
            value += to_fraction(cited.rounding_residue)
        values.append(value)
    from erev_engine.trace import _encode  # the engine's own encoding of a replayed result

    return _encode(node, FORMULAS[node.formula_id](values, node.params))


def _hand_builder() -> tuple[TraceBuilder, object]:
    from support import allocation_worlds as worlds

    bundle = worlds.targeted_world(lines=(("A", "PROD-A", "51"), ("B", "PROD-B", "50")))
    return TraceBuilder(engine_version=ENGINE_VERSION), worlds.context(bundle)


def test_witness_converted_nonterminating_ssp_over_a_fractional_quantity_replays() -> None:
    """Codex 0954 §1a: a converted SSP 1/3 (an AMOUNT point 10 at inverse rate 3) over quantity
    0.1 — the column publishes 10/3; the producer's Q18 encoding 0.333333333333333333 over 0.1
    would give 3.33333333333333333 (short by 1/(3·10¹⁷)). With the raw operands as bound params
    the node stores and REPLAYS the raw quotient; a foreign raw operand is refused."""
    tb, ctx = _hand_builder()
    subject = "K-W/S"
    selected = tb.node(
        measure="original_ssp_selected@K-W/EV-1",
        subject_key=subject,
        period_key=None,
        value=Fraction(1, 3),
        currency=ctx.txn_currency,  # type: ignore[attr-defined]
        minor_unit=None,
        formula_id="ssp.point.v1",
        inputs=[],
        params={"value": format_exact(Fraction(1, 3))},
        narrative_key="ssp.point",
    )
    tb.node(
        measure="original_quantity",
        subject_key=subject,
        period_key=None,
        value=Fraction(1, 10),
        currency=None,
        minor_unit=None,
        formula_id="pob.template_match.v1",
        inputs=[],
        params={"value": "0.1"},
        narrative_key="pob.template_match",
    )
    links = provenance.emit_snapshot_columns(
        ctx,  # type: ignore[arg-type]
        tb,
        "K-W/EV-1",
        subject,
        selected_node=selected,
        selected=Fraction(1, 3),
        quantity=Fraction(1, 10),
        stated_price=None,
        price=None,
        rule="TEST",
    )
    nodes = {node.id: node for node in tb.build(root_measures={}).nodes}
    unit = nodes[links["original_unit_ssp"]]
    assert unit.value == format_exact(Fraction(10, 3)) == "3.333333333333333333"
    assert unit.params["ssp"] == "1/3" and unit.params["quantity"] == "1/10"
    assert _exact_replay(unit, nodes) == unit.value  # the raw quotient replays
    decoded = Fraction(nodes[selected].value) / Fraction("0.1")
    assert format_exact(decoded) == "3.33333333333333333" != unit.value  # the old defect
    with pytest.raises(ValueError, match="not bound"):
        FORMULAS["alloc.unit_ssp.v1"](
            [Fraction(nodes[selected].value), Fraction("0.1")], {"ssp": "1/2", "quantity": "1/10"}
        )


def test_witness_mismatched_quantity_is_refused_at_emission_and_replay() -> None:
    """Codex 1025 §1: the emitter bound the raw SSP to its cited node but took the raw QUANTITY on
    the quantity node's mere existence — cited SSP 10 / quantity 1 with a raw quantity 2 EMITTED a
    unit node 5 that replay then refused (a local emission / replay asymmetry; no admitted-world
    failure). Now both operands are bound at emission under the same CV-51 rule: the mismatch is
    refused before any node exists, replay keeps refusing a doctored quantity param, and the honest
    emission is unchanged."""
    from erev_engine.errors import EngineError

    tb, ctx = _hand_builder()
    subject = "K-W/S"
    selected = tb.node(
        measure="original_ssp_selected@K-W/EV-1",
        subject_key=subject,
        period_key=None,
        value=Fraction(10),
        currency=ctx.txn_currency,  # type: ignore[attr-defined]
        minor_unit=None,
        formula_id="ssp.point.v1",
        inputs=[],
        params={"value": format_exact(Fraction(10))},
        narrative_key="ssp.point",
    )
    quantity_node = tb.node(
        measure="original_quantity",
        subject_key=subject,
        period_key=None,
        value=Fraction(1),
        currency=None,
        minor_unit=None,
        formula_id="pob.template_match.v1",
        inputs=[],
        params={"value": "1"},
        narrative_key="pob.template_match",
    )
    with pytest.raises(EngineError, match="raw quantity") as refused:
        provenance.emit_snapshot_columns(
            ctx,  # type: ignore[arg-type]
            tb,
            "K-W/EV-1",
            subject,
            selected_node=selected,
            selected=Fraction(10),
            quantity=Fraction(2),  # the raw operand disagrees with the cited node (1)
            stated_price=None,
            price=None,
            rule="TEST",
        )
    assert refused.value.detail == {
        "rule": "TEST",
        "node_id": quantity_node,
        "operand": "2",
        "cited": "1",
    }
    nodes = {node.id: node for node in tb.build(root_measures={}).nodes}
    assert not any(node_id.startswith("original_unit_ssp@") for node_id in nodes)  # nothing emitted
    # replay refuses the same doctored quantity param over the cited values (unchanged)
    with pytest.raises(ValueError, match="not bound"):
        FORMULAS["alloc.unit_ssp.v1"]([Fraction(10), Fraction(1)], {"ssp": "10", "quantity": "2"})
    # the honest emission (quantity 1) is unchanged: the node stores 10 and replays it
    links = provenance.emit_snapshot_columns(
        ctx,  # type: ignore[arg-type]
        tb,
        "K-W/EV-1",
        subject,
        selected_node=selected,
        selected=Fraction(10),
        quantity=Fraction(1),
        stated_price=None,
        price=None,
        rule="TEST",
    )
    nodes = {node.id: node for node in tb.build(root_measures={}).nodes}
    unit = nodes[links["original_unit_ssp"]]
    assert unit.value == format_exact(Fraction(10)) and unit.params["quantity"] == "1"
    assert _exact_replay(unit, nodes) == unit.value


def test_witness_two_nonterminating_weights_total_and_ratio_replay() -> None:
    """Codex 0954 §1b: two converted weights 1/3 + 1/3 — the raw total 2/3 stores as
    0.666666666666666667 while the sum of the encodings replays to 0.666666666666666666; the
    ratio 1/2 stores as 0.5 while the decoded quotient gives 0.499999999999999999. The raw
    operands as bound params make the stored values and the replays identical."""
    tb, ctx = _hand_builder()
    subject, other = "K-W/A", "K-W/B"
    ids = []
    for key in (subject, other):
        ids.append(
            tb.node(
                measure="mod_weight@K-W/EV-1",
                subject_key=key,
                period_key=None,
                value=Fraction(1, 3),
                currency=None,
                minor_unit=None,
                formula_id="mod.weights.d18.v1",
                inputs=[],
                params={"value": format_exact(Fraction(1, 3))},
                narrative_key="mod.weights.d18",
            )
        )
    links = provenance.emit_snapshot_columns(
        ctx,  # type: ignore[arg-type]
        tb,
        "K-W/EV-1",
        subject,
        selected_node=None,
        selected=None,
        quantity=Fraction(1),
        stated_price=None,
        price=None,
        rule="TEST",
        total_inputs=ids,
        total_value=Fraction(2, 3),
        weight_input=ids[0],
        weight_value=Fraction(1, 3),
    )
    nodes = {node.id: node for node in tb.build(root_measures={}).nodes}
    total = nodes[links["original_total_contract_ssp"]]
    weight = nodes[links["allocation_weight"]]
    assert total.value == "0.666666666666666667" and total.formula_id == "alloc.original_total.v1"
    assert _exact_replay(total, nodes) == total.value
    assert format_exact(sum(Fraction(nodes[i].value) for i in ids)) == "0.666666666666666666"
    assert weight.value == "0.5" and weight.formula_id == "alloc.original_weight.v1"
    assert _exact_replay(weight, nodes) == weight.value
    decoded = Fraction(nodes[ids[0]].value) / Fraction(total.value)
    assert format_exact(decoded) == "0.499999999999999999" != weight.value


def test_required_producers_refuse_when_absent() -> None:
    """Codex 0954 §2: a stamped snapshot producer absent from the trace refuses the assembly;
    the reserved total-price echo refuses when stage 13 traced no build-up for the event."""
    from erev_engine.errors import EngineError

    rm = _module("test_tc_rm")
    value = rm.golden_streams.stream("Contract 2", "07").input_bundle(preset="LEGACY_PARITY")
    software = rm.template_line(value, "POB #2", "1", "170")
    add = {
        **software,
        "obligation_key": "POB #4",
        "action": "ADD",
        "start_date": date(2023, 1, 1),
        "end_date": date(2023, 12, 31),
    }
    folded = rm.fold(
        rm.amended(
            value, "MOD-RM11", date(2023, 5, 15), "retrospective", [add], "LEGACY_RETROSPECTIVE"
        )
    )
    (ev,) = rm.amendments(folded.state)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = rm.apply(folded, folded.state, ev, tb)
    added = rm.obligation(after, "POB #4")
    nodes = {node.id: node for node in tb.build(root_measures={}).nodes}
    # the reserved total-price link has no node before stage 13 traces the price: REFUSED
    columns = {"original_total_contract_price": round(added.original_total_contract_price * 100)}
    with pytest.raises(EngineError) as absent:
        _snapshot_links(added, after, columns, nodes, 2)
    assert absent.value.detail["rule"] == "CV-50"
    assert (
        absent.value.detail["node_id"]
        == added.snapshot_producer_links["original_total_contract_price"]
    )
    # the echo emitter refuses when the build-up it must cite was not traced
    with pytest.raises(EngineError, match="traced no transaction_price"):
        provenance.emit_price_echoes(
            folded.ctx,
            tb,
            ev,
            after.obligations,
            total=after.tp_history[-1].total,
            price_node=f"transaction_price@{ev.event_key}:no-such-group:-",
        )
