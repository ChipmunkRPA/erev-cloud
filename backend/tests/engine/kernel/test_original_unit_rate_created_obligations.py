"""D-98 candidate 117 F1 coverage (Codex production-20260921-0226, relayed by the supervisor; lane
ENG-T1F): the committed state writers create obligations at THREE modification boundaries, each
installing an original quota and an original quantity (``_added_obligation``), and each such
obligation is OWED an original unit revenue rate whose numerator cites the node that produced its
quota at creation and whose denominator cites a real ``original_quantity`` node:

1. native added goods (``s06 _native`` → ``mod_share@<event>:<ob>:-``, S06-R-14);
2. legacy retrospective additions (``s06 _template`` → ``allocated_amount@<event>:<ob>:-``,
   S06-R-29, ``legacy_templates``);
3. material-right CONTINUATION goods (``s06 _continuation`` → ``allocated_amount@<event>:<ob>:-``,
   S06-R-23, ``exercise``).

Their stage 03 drafts are built in SCRATCH trace builders (``classify.added_lines``,
``exercise.goods``), so the real trace held no ``original_quantity`` node for them; stage 06 now
emits it at creation (``s03_pob_builder.emit_original_quantity``) citing the creating event's line.
Before this coverage the emitter published NULL and no node for every created obligation.

Cases 2 and 3 are measured at the stage 06 ``apply`` level (their golden worlds do not compute end
to end in this suite) with the stage 13 emitter run over the resulting state and trace; the rate
node is replayed from its cited inputs' values and params through its registered formula (P14)."""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
from datetime import date
from fractions import Fraction
from pathlib import Path
from types import ModuleType

from erev_engine import ENGINE_VERSION, compute
from erev_engine.formulas import EXACT_INPUT_FORMULAS, FORMULAS, binds_encoded, rational_param
from erev_engine.money import format_exact, to_fraction
from erev_engine.stages import s06_modifications
from erev_engine.stages.s13_books.output_measures import unit_revenue_rates
from erev_engine.stages.state import AllocatedState, ObligationState
from erev_engine.trace import SourceRef, Trace, TraceBuilder, TraceNode, reevaluate

S06_TESTS = Path(__file__).resolve().parents[1] / "s06_modifications"


def _module(name: str) -> ModuleType:
    """A stage 06 test module by file (its sibling imports resolve through ``sys.path``)."""
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


def _quantity_node(nodes: dict[str, TraceNode], subject: str, event_key: str, line: str) -> None:
    """The created obligation's ``original_quantity`` node cites the creating event's line."""
    node = nodes[f"original_quantity:{subject}:-"]
    assert node.formula_id == "pob.template_match.v1"
    (source,) = node.inputs
    assert isinstance(source, SourceRef)
    assert source.ref_type == "contract_event" and source.ref_id == event_key
    assert source.detail["line"] == line and source.detail["value"] == node.value


def _replayed(node: TraceNode, nodes: dict[str, TraceNode]) -> str:
    """P14 for one node as ``reevaluate`` feeds it: the cited inputs' exact values (value +
    stored residue) for a formula in ``EXACT_INPUT_FORMULAS``, and its params."""
    assert node.formula_id in EXACT_INPUT_FORMULAS
    inputs = [
        to_fraction(nodes[item].value) + to_fraction(nodes[item].rounding_residue or "0")
        for item in node.inputs
        if isinstance(item, str)
    ]
    return format_exact(FORMULAS[node.formula_id](inputs, node.params))


def _rate_checks(
    ob: ObligationState,
    producer: str,
    values: dict[str, Fraction],
    node: TraceNode,
    nodes: dict[str, TraceNode],
) -> None:
    subject = ob.subject_key
    assert ob.original_allocation_nodes == (producer,)
    assert ob.original_quantity != 0
    expected = ob.original_allocation.x_exact / ob.original_quantity
    assert values["original_unit_revenue_rate"] == expected
    assert node.inputs == (producer, f"original_quantity:{subject}:-")
    assert node.params["allocation"] == rational_param(ob.original_allocation.x_exact)
    assert node.params["quantity"] == rational_param(ob.original_quantity)
    # the producer's exact value (value + residue) binds the raw quota within the CV-51 limit
    exact = Fraction(nodes[producer].value) + Fraction(nodes[producer].rounding_residue or 0)
    assert binds_encoded(ob.original_allocation.x_exact, [exact])
    assert node.value == format_exact(expected)
    assert _replayed(node, nodes) == node.value


def _assembler_links(
    ob: ObligationState, after: AllocatedState, nodes: dict[str, TraceNode]
) -> None:
    """D-98 121 through the assembler on a stage-06 → stage-13 seam: the two allocation columns
    link the creation pair the constructor stamped, and both nodes hold the published values."""
    from erev_engine import _snapshot_links

    assert ob.original_allocation_links is not None
    exact_id, amount_id = ob.original_allocation_links
    minor_unit = 2
    columns = {
        "original_allocated_exact": ob.original_allocation.x_exact,
        "original_allocated_amount": ob.original_allocation.a_posted,
    }
    links = _snapshot_links(ob, after, columns, nodes, minor_unit)
    assert links["original_allocated_exact"] == exact_id
    assert links["original_allocated_amount"] == amount_id
    assert exact_id.startswith("original_allocated_exact@") and exact_id.endswith(
        f":{ob.subject_key}:-"
    )
    assert nodes[exact_id].value == format_exact(ob.original_allocation.x_exact)
    assert Fraction(nodes[amount_id].value) * 10**minor_unit == ob.original_allocation.a_posted
    assert nodes[exact_id].inputs == nodes[amount_id].inputs == (ob.original_allocation_nodes[0],)


def test_native_added_good_cites_its_mod_share_producer_and_a_real_quantity_node() -> None:
    """Constructor 1 (the prospective-addition world ``ex_09_a``: O2 added 16 Sep 2026 for
    60,000.00 as POB-02): the rate is the raw quota over the raw quantity, cites the boundary's
    ``mod_share@<event>`` share and the obligation's ``original_quantity`` node emitted at
    creation (source: the amendment's line), carries the share's residue, replays exactly through
    the whole trace."""
    prospective = _module("test_s06_prospective")
    output = compute(prospective.ex_09_a())
    book = next(item for item in output.books if item.book_code == "ASC606")
    nodes = {node.id: node for node in book.trace.nodes}
    version = next(
        item for item in book.obligation_versions if item.columns["obligation_key"] == "POB-02"
    )
    subject = version.subject_key
    quota = version.columns["original_allocated_exact"]
    assert quota == Fraction(5379452, 75) and version.columns["original_quantity"] == 1
    node = nodes[version.trace_nodes["original_unit_revenue_rate"]]
    producer, quantity_node = node.inputs
    assert isinstance(producer, str) and producer.startswith("mod_share@")
    assert producer.endswith(f":{subject}:-")
    event_key = producer[len("mod_share@") : -len(f":{subject}:-")]
    assert quantity_node == f"original_quantity:{subject}:-"
    _quantity_node(nodes, subject, event_key, "POB-02")
    assert version.trace_nodes["original_quantity"] == quantity_node  # CV-50 link now real
    share = nodes[producer]
    # the share's exact value (value + its 18-place residue) binds the raw quota within the CV-51
    # bound; 5379452/75 = 71726.0266…, non-terminating, so no node holds it exactly
    assert binds_encoded(quota, [Fraction(share.value) + Fraction(share.rounding_residue or 0)])
    assert Fraction(share.value) + Fraction(share.rounding_residue or 0) != quota
    assert node.params["allocation"] == "5379452/75" and node.params["quantity"] == "1"
    assert version.columns["original_unit_revenue_rate"] == quota
    assert node.value == format_exact(quota)
    assert reevaluate(book.trace)[node.id] == node.value
    # a citation of the (absent) inception node is not fabricated: no such node exists
    assert f"original_allocated_exact:{subject}:-" not in nodes


def _apply_level(
    ctx: object, after: AllocatedState, tb: TraceBuilder
) -> tuple[dict[str, dict[str, Fraction]], dict[str, dict[str, str]], dict[str, TraceNode]]:
    values, node_ids = unit_revenue_rates(ctx, after, tb)  # type: ignore[arg-type]
    trace: Trace = tb.build(root_measures={})
    nodes = {node.id: node for node in trace.nodes}
    return (
        {k: dict(v) for k, v in values.items()},
        {k: dict(v) for k, v in node_ids.items()},
        nodes,
    )


def test_legacy_retrospective_addition_cites_its_allocated_amount_producer() -> None:
    """Constructor 2 (``test_tc_rm_11_new_pob_joins_the_pool``: golden Contract 2 step 07 under
    LEGACY_PARITY, POB #4 Software 1 +1 / +170.00 added retrospectively on 2023-05-15): the created
    obligation's producer is the template's ``allocated_amount@<event>`` node; its
    ``original_quantity`` node is emitted at creation from the amendment's line; the stage 13
    emitter over the applied state gives the raw quotient with the producer's residue."""
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
    added = rm.obligation(after, "POB #4")
    assert added.original_quantity == 1
    producer = f"allocated_amount@{ev.event_key}:{added.subject_key}:-"
    values, node_ids, nodes = _apply_level(folded.ctx, after, tb)
    _quantity_node(nodes, added.subject_key, ev.event_key, "POB #4")
    node = nodes[node_ids[added.subject_key]["original_unit_revenue_rate"]]
    _rate_checks(added, producer, values[added.subject_key], node, nodes)
    _assembler_links(added, after, nodes)  # the two 121 final column links, through the assembler
    # the pre-existing obligations keep citing their inception producers (absent here: NULL)
    for key in ("POB #1", "POB #2", "POB #3"):
        assert "original_unit_revenue_rate" not in values.get(
            rm.obligation(after, key).subject_key, {}
        )


def test_material_right_continuation_good_cites_its_allocated_amount_producer() -> None:
    """Constructor 3 (``contract_3_exercised``: golden Contract 3 step 13, the 09.15 material right
    exercised under POL-028 CONTINUATION with POB #5 +5 units for 1,000.00 as the new good): the
    good's producer is ``exercise``'s ``allocated_amount@<event>`` node, its ``original_quantity``
    node is emitted at creation from the exercise event's line, and the rate is the raw quotient
    with the producer's residue."""
    ex = _module("test_s06_exercise")
    value = ex.contract_3_exercised()
    folded = ex.fold_at(value, "MATERIAL_RIGHT_EXERCISED")
    st, ev = ex.after_step_12(folded.state), folded.amended
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    after = s06_modifications.apply(
        folded.ctx, st, ev, tb, identified=folded.identified, price_at=ex.price_function("1300.00")
    )
    assert after.findings == ()
    known = {ob.subject_key for ob in st.obligations}
    created = [ob for ob in after.obligations if ob.subject_key not in known]
    assert created, "the exercise creates the optioned good"
    values, node_ids, nodes = _apply_level(folded.ctx, after, tb)
    for ob in created:
        producer = f"allocated_amount@{ev.event_key}:{ob.subject_key}:-"
        _quantity_node(nodes, ob.subject_key, ev.event_key, ob.obligation_key)
        node = nodes[node_ids[ob.subject_key]["original_unit_revenue_rate"]]
        _rate_checks(ob, producer, values[ob.subject_key], node, nodes)
        assert dataclasses.replace(ob).original_allocation_nodes == (producer,)
        _assembler_links(ob, after, nodes)  # the two 121 final column links, through the assembler
