"""Stage 09 catch-up disclosure measures at full precision (ENGINE_SPEC Table 0.9-A, CV-56;
ENGINE_SPEC_B S09-R-36; dev-guide DG-PAR-05, DG-OQ-05).

``catch_up_amount``, ``catch_up_cum`` and ``catch_up_*_cum`` sum the stage 06 and stage 08
``catch_up@<event key>`` nodes. Their posted value is Σ CU_posted, and their exact value
(``value + rounding_residue``) is Σ CU_exact of the cited nodes. The figures are those of EX-06-F
and EX-06-G (golden Contract 2 after steps 08 and 09). Exact values are encoded at
``EXACT_PLACES`` (``format_exact``), so they are compared within 10^−12.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal
from fractions import Fraction

from erev_engine import ENGINE_VERSION, compute
from erev_engine.money import format_money
from erev_engine.stages.s09_recognition import components, decompose
from erev_engine.stages.state import SegmentCause
from erev_engine.trace import SourceRef, TraceBuilder, TraceNode, reevaluate
from support import golden_streams, intent_totals
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    emit_catch_up_nodes,
    event_view,
    obligation,
    segment,
    usd,
)

O1 = f"{CONTRACT_KEY}/POB-01"
# EX-06-F: r_c = 1,300 ÷ 1,377; CU_exact = r_c × SSPDel − E before the event.
R_C = Fraction(1300, 1377)
CU_08_POB1 = R_C * Fraction(153, 2) - Fraction(900 * 612, 1170) / 8  # +13.3761
CU_08_POB3 = R_C * 60 - Fraction(900 * 150, 1170) * Fraction(2, 5)  # +10.4910
# EX-06-G: CU = M × D ÷ W = −200.00 × 76.5 ÷ 819.
CU_09_POB1 = Fraction(-200) * Fraction(153, 2) / 819  # −18.6813
PRECISION = Fraction(1, 10**12)
TOLERANCE = Fraction(1, 10000)  # D-17


def _exact(node: TraceNode) -> Fraction:
    value = Fraction(Decimal(node.value))
    if node.rounding_residue is None:
        return value
    return value + Fraction(Decimal(node.rounding_residue))


def _near(actual: Fraction | None, expected: Fraction) -> bool:
    return actual is not None and abs(actual - expected) <= PRECISION


def test_s09_r36_catch_up_measures_carry_the_exact_value_of_the_cited_nodes() -> None:
    ctx = book_context()
    service = segment(
        Fraction(12000), usd("12000.00"), start=date(2026, 1, 1), end=date(2026, 12, 31)
    )
    ob = obligation("POB-01", [service], convention="MONTHLY_EVEN")
    earlier = event_view(
        CONTRACT_KEY,
        2,
        "CONTRACT_AMENDED",
        date(2026, 3, 31),
        {"modification_id": "MOD-08"},
        obligation_keys=["POB-01"],
    )
    earlier = dataclasses.replace(earlier, is_new=False)  # included in an earlier version
    later = event_view(
        CONTRACT_KEY,
        3,
        "CONTRACT_AMENDED",
        date(2026, 5, 31),
        {"modification_id": "MOD-09"},
        obligation_keys=["POB-01"],
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    points: list[decompose.CausePoint] = []
    # Stages 06 and 08 publish CU_posted with CU_exact on catch_up@<event key> (S06-R-17).
    for ev, posted, exact in (
        (earlier, usd("13.37"), CU_08_POB1),
        (later, usd("-18.68"), CU_09_POB1),
    ):
        detail = {"member": "catch_up", "value": format_money(posted, 2)}
        node_id = tb.node(
            measure=f"catch_up@{ev.event_key}",
            subject_key=O1,
            period_key=None,
            value=posted,
            currency="USD",
            minor_unit=2,
            formula_id=decompose.CATCH_UP_FORMULA,
            inputs=[SourceRef("contract_event", ev.event_key, detail)],
            exact=exact,
            narrative_key="rec.catch_up.sum",
        )
        assert node_id == decompose.catch_up_node_id(ev.event_key, O1)
        points.append(decompose.CausePoint(ev, "MODIFICATION", posted, node_id))

    ids = decompose.emit_catch_up_measures(tb, ctx, ob, points, as_of=date(2026, 12, 31), mu=2)

    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    nodes = {node.id: node for node in trace.nodes}
    cumulative = CU_08_POB1 + CU_09_POB1  # 13.376068 − 18.681319 = −5.305250
    expected = {
        "catch_up_modification_cum": ("-5.31", cumulative),
        "catch_up_tp_change_cum": ("0.00", Fraction(0)),
        "catch_up_estimate_cum": ("0.00", Fraction(0)),
        "catch_up_cum": ("-5.31", cumulative),
        "catch_up_amount": ("-18.68", CU_09_POB1),  # the event first included in the version
    }
    for measure, (posted, exact) in expected.items():
        node = nodes[ids[measure]]
        assert node.value == posted and _near(_exact(node), exact), (measure, node)
    assert _near(tb.exact(ids["catch_up_cum"]), cumulative)
    assert abs(cumulative - Fraction(Decimal("-5.305250305250304"))) <= PRECISION  # legacy

    # A builder without the stage 06 node: the sum falls back to the posted catch-up.
    bare = TraceBuilder(engine_version=ENGINE_VERSION)
    assert bare.exact(points[1].catch_up_node or "") is None
    only = decompose.emit_catch_up_measures(bare, ctx, ob, points, as_of=date(2026, 12, 31), mu=2)
    assert bare.exact(only["catch_up_cum"]) == Fraction(-531, 100)


def test_s09_r36_boundary_delta_is_the_cited_node_never_recomputed() -> None:
    """D-88 L7-5-Q-13 (MOD-CHK-112 at-termination; MOD-FS-09): stage 06 measures a time-elapsed
    boundary on the close of d − 1 (EX-09-A), so a termination on 30 June publishes CU = June's
    month, while stage 09's segment target at d does not move across the event. The boundary delta
    is the cited catch_up@ node, never recomputed (S09-R-36), so the catch-up measures reproduce
    under reevaluate; a builder that holds no node keeps C_after(d) − C_before(d)."""
    ctx = book_context()
    terminated = event_view(
        CONTRACT_KEY,
        7,
        "CONTRACT_TERMINATED",
        date(2026, 6, 30),
        {"modification_id": "MOD-TERM"},
        obligation_keys=["POB-01"],
    )
    service = segment(
        Fraction(12000), usd("12000.00"), start=date(2026, 1, 1), end=date(2026, 12, 31)
    )
    ended = segment(
        Fraction(6000),
        usd("6000.00"),
        start=date(2026, 1, 1),
        end=date(2026, 6, 30),
        effective=date(2026, 6, 30),
        event_key=terminated.event_key,
        cause=SegmentCause.TERMINATION,
    )
    ob = obligation("POB-01", [service, ended], convention="MONTHLY_EVEN")
    st = allocated_state([ob], events=[terminated])
    evaluator = components.Evaluator(ctx, st, ob)
    (recomputed,) = decompose.boundary_points(st, ob, segments=evaluator.segment_value)
    assert (recomputed.cause, recomputed.delta) == ("MODIFICATION", 0)  # June is in both targets

    key = (terminated.event_key, O1)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    assert emit_catch_up_nodes(tb, ctx, st, {key: usd("1000.00")}) == {key: usd("1000.00")}
    cited = decompose.cited_posted(tb, 2)
    (point,) = decompose.boundary_points(st, ob, segments=evaluator.segment_value, cited=cited)
    assert (point.delta, point.catch_up_node) == (usd("1000.00"), recomputed.catch_up_node)
    ids = decompose.emit_catch_up_measures(tb, ctx, ob, (point,), as_of=date(2026, 12, 31), mu=2)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    nodes = {node.id: node for node in trace.nodes}
    measures = ("catch_up_modification_cum", "catch_up_cum", "catch_up_amount")
    assert [nodes[ids[measure]].value for measure in measures] == ["1000.00"] * 3

    # Recomputed, the sums publish 0.00 while citing the 1,000.00 node (the DG-AK-54 stop).
    stale = TraceBuilder(engine_version=ENGINE_VERSION)
    emit_catch_up_nodes(stale, ctx, st, {key: usd("1000.00")})
    decompose.emit_catch_up_measures(stale, ctx, ob, (recomputed,), as_of=date(2026, 12, 31), mu=2)
    rebuilt = stale.build(root_measures={})
    assert reevaluate(rebuilt) != {node.id: node.value for node in rebuilt.nodes}

    # A builder without the node keeps the recomputed delta.
    bare = decompose.cited_posted(TraceBuilder(engine_version=ENGINE_VERSION), 2)
    assert decompose.boundary_points(st, ob, segments=evaluator.segment_value, cited=bare) == (
        recomputed,
    )


def _asc606(step: str) -> tuple[dict[str, dict[str, str]], dict[str, TraceNode]]:
    """``compute`` over golden Contract 2 through ``step`` under ``LEGACY_PARITY``: the trace
    nodes of each obligation by obligation key, and the ASC606 trace."""
    stream = golden_streams.stream("Contract 2", step)
    value = stream.input_bundle(preset="LEGACY_PARITY", books=intent_totals.BOOKS)
    output = compute(intent_totals.activated(value))
    book = next(item for item in output.books if item.book_code == "ASC606")
    by_key = {
        str(item.columns["obligation_key"]): dict(item.trace_nodes)
        for item in book.obligation_versions
    }
    return by_key, {node.id: node for node in book.trace.nodes}


def test_table_0_9_a_golden_contract2_catch_up_exact_values() -> None:
    # EX-06-F (golden step 08, LEGACY_RETROSPECTIVE on 2023-05-15). Before the fix every sum
    # node held residue 0: POB #1 13.37 and POB #3 10.49, Σ 23.86 against the golden 23.8671.
    versions, nodes = _asc606("08")
    for key, posted, exact in (("POB #1", "13.37", CU_08_POB1), ("POB #3", "10.49", CU_08_POB3)):
        for measure in ("catch_up_amount", "catch_up_cum", "catch_up_modification_cum"):
            node = nodes[versions[key][measure]]
            assert node.value == posted and _near(_exact(node), exact), (key, measure, node)
    total = sum((_exact(nodes[names["catch_up_cum"]]) for names in versions.values()), Fraction(0))
    assert _near(total, CU_08_POB1 + CU_08_POB3)
    assert abs(total - Fraction(Decimal("23.8671"))) <= TOLERANCE  # rollforward-08-Contract2

    # EX-06-G (golden step 09, LEGACY_POB_VC −200.00 on POB #1 on 2023-05-31).
    versions, nodes = _asc606("09")
    (pob_vc,) = [
        node
        for node_id, node in nodes.items()
        if node_id.startswith("catch_up@") and node.value == "-18.68"
    ]
    assert _near(_exact(pob_vc), CU_09_POB1)
    pob1 = nodes[versions["POB #1"]["catch_up_cum"]]
    assert pob1.value == "-5.31" and _near(_exact(pob1), CU_08_POB1 + CU_09_POB1)
    pob3 = nodes[versions["POB #3"]["catch_up_cum"]]
    assert pob3.value == "10.49" and _near(_exact(pob3), CU_08_POB3)
    total = sum((_exact(nodes[names["catch_up_cum"]]) for names in versions.values()), Fraction(0))
    assert abs(total - Fraction(Decimal("5.1858"))) <= TOLERANCE  # rollforward-09-Contract2
