"""Calculation trace, formulas and re-evaluation (dev-guide §5.16; ENGINE_SPEC CV-50 to CV-54)."""

from __future__ import annotations

import dataclasses
import re
from fractions import Fraction

import pytest
from erev_engine.errors import EngineError
from erev_engine.formulas import FORMULAS
from erev_engine.money import format_exact
from erev_engine.trace import SourceRef, Trace, TraceBuilder, reevaluate

ENGINE_VERSION = "0.0.0-test"
CUMULATIVE = "sched.cumulative_posted.v1"
DIFFERENCE = "sched.period_difference.v1"


def _value(ref_type: str, ref_id: str, value: str) -> SourceRef:
    return SourceRef(ref_type=ref_type, ref_id=ref_id, detail={"value": value})  # type: ignore[arg-type]


def _ex_09_b_builder() -> TraceBuilder:
    # EX-09-B: A′ 1,350,000.00, costs 502,000.00, EAC v3 850,000.00: round(X × f) = 797,294.12.
    builder = TraceBuilder(engine_version=ENGINE_VERSION)
    builder.node(
        measure="revenue_cum",
        subject_key="K-03/POB-01",
        period_key=None,
        value=79729412,
        currency="USD",
        minor_unit=2,
        exact=Fraction(1350000 * 502000, 850000),
        formula_id=CUMULATIVE,
        inputs=[
            _value("source_record", "K-03/POB-01/allocation_exact", "1350000"),
            _value("source_record", "K-03/POB-01/allocation", "1350000.00"),
            _value("estimate_version", "K-03/EAC/v3", format_exact(Fraction(502000, 850000))),
        ],
        narrative_key="sched.cumulative_posted",
    )
    return builder


def _chk_007_builder(order: tuple[int, ...] = (0, 1, 2, 3)) -> TraceBuilder:
    # CHK-007: X = 1,300 × 368 ÷ 2,018, A = 237.07; one of two units delivered in each period.
    subject = "Contract 1/POB-002"
    exact = Fraction(1300 * 368, 2018)
    allocation = [
        _value("source_record", f"{subject}/allocation_exact", format_exact(exact)),
        _value("source_record", f"{subject}/allocation", "237.07"),
    ]
    cum_p1 = f"revenue_cum:{subject}:FY2023-P01"
    cum_p2 = f"revenue_cum:{subject}:FY2023-P02"
    nodes = [
        {
            "measure": "revenue_cum",
            "period_key": "FY2023-P01",
            "value": 11853,
            "exact": exact / 2,
            "formula_id": CUMULATIVE,
            "inputs": [*allocation, _value("contract_event", "Contract 1/EV-000002", "0.5")],
        },
        {
            "measure": "revenue_cum",
            "period_key": "FY2023-P02",
            "value": 23707,
            "exact": exact,
            "formula_id": CUMULATIVE,
            "inputs": [*allocation, _value("contract_event", "Contract 1/EV-000003", "1")],
        },
        {
            "measure": "revenue",
            "period_key": "FY2023-P01",
            "value": 11853,
            "exact": exact / 2,
            "formula_id": DIFFERENCE,
            "inputs": [cum_p1, _value("source_record", f"{subject}/opening", "0.00")],
        },
        {
            "measure": "revenue",
            "period_key": "FY2023-P02",
            "value": 11854,
            "exact": exact / 2,
            "formula_id": DIFFERENCE,
            "inputs": [cum_p2, cum_p1],
        },
    ]
    builder = TraceBuilder(engine_version=ENGINE_VERSION)
    for index in order:
        spec = nodes[index]
        formula_id = str(spec["formula_id"])
        builder.node(
            measure=str(spec["measure"]),
            subject_key=subject,
            period_key=str(spec["period_key"]),
            value=spec["value"],  # type: ignore[arg-type]
            currency="USD",
            minor_unit=2,
            exact=spec["exact"],  # type: ignore[arg-type]
            formula_id=formula_id,
            inputs=spec["inputs"],  # type: ignore[arg-type]
            narrative_key=formula_id.rsplit(".v", 1)[0],
        )
    return builder


def _chk_007_trace() -> Trace:
    return _chk_007_builder().build(
        root_measures={"revenue_cum": "revenue_cum:Contract 1/POB-002:FY2023-P02"}
    )


def test_node_id_and_posted_value_encoding() -> None:
    trace = _ex_09_b_builder().build(root_measures={"revenue_cum": "revenue_cum:K-03/POB-01:-"})
    (node,) = trace.nodes
    assert node.id == "revenue_cum:K-03/POB-01:-"
    assert node.value == "797294.12"
    assert node.params["minor_unit"] == "2"
    assert node.rounding_residue is not None
    exact = Fraction(1350000 * 502000, 850000)
    assert format_exact(Fraction(node.value) + Fraction(node.rounding_residue)) == format_exact(
        exact
    )
    assert format_exact(Fraction(node.rounding_residue), places=6) == "-0.002353"
    assert reevaluate(trace) == {node.id: "797294.12"}

    # An exact node holds format_exact and no residue.
    builder = TraceBuilder(engine_version=ENGINE_VERSION)
    exact_id = builder.node(
        measure="revenue_delta_exact",
        subject_key="K-03/POB-01",
        period_key="FY2026-P09",
        value=Fraction(2, 3),
        currency="USD",
        minor_unit=None,
        formula_id=DIFFERENCE,
        inputs=[_value("source_record", "a", "1"), _value("source_record", "b", "0.5")],
        narrative_key="sched.period_difference",
    )
    (exact_node,) = builder.build(root_measures={}).nodes
    assert exact_id == "revenue_delta_exact:K-03/POB-01:FY2026-P09"
    assert exact_node.value == "0.666666666666666667"
    assert exact_node.rounding_residue is None


def test_duplicate_node_raises() -> None:
    builder = _ex_09_b_builder()
    with pytest.raises(EngineError) as duplicate:
        builder.node(
            measure="revenue_cum",
            subject_key="K-03/POB-01",
            period_key=None,
            value=0,
            currency="USD",
            minor_unit=2,
            formula_id=CUMULATIVE,
            inputs=[],
            narrative_key="sched.cumulative_posted",
        )
    assert duplicate.value.code == "TRACE_DUPLICATE_NODE"
    assert duplicate.value.detail == {"node_id": "revenue_cum:K-03/POB-01:-"}


def test_trace_sha256_independent_of_insertion_order() -> None:
    forward = _chk_007_builder((0, 1, 2, 3)).build(
        root_measures={"revenue": "revenue:Contract 1/POB-002:FY2023-P02"}
    )
    backward = _chk_007_builder((3, 1, 2, 0)).build(
        root_measures={"revenue": "revenue:Contract 1/POB-002:FY2023-P02"}
    )
    assert forward.sha256() == backward.sha256()
    assert re.fullmatch(r"[0-9a-f]{64}", forward.sha256())
    ids = [node.id for node in forward.nodes]
    assert ids == sorted(ids)
    assert [node.id for node in backward.nodes] == ids
    assert forward.format_version == 1
    assert forward.engine_version == ENGINE_VERSION


def test_reevaluate_reproduces_and_detects_tampering() -> None:
    trace = _chk_007_trace()
    stored = {node.id: node.value for node in trace.nodes}
    recomputed = reevaluate(trace)
    assert recomputed == stored
    assert recomputed["revenue_cum:Contract 1/POB-002:FY2023-P01"] == "118.53"
    assert recomputed["revenue:Contract 1/POB-002:FY2023-P02"] == "118.54"

    tampered_id = "revenue_cum:Contract 1/POB-002:FY2023-P01"
    tampered = dataclasses.replace(
        trace,
        nodes=tuple(
            dataclasses.replace(node, value="118.54") if node.id == tampered_id else node
            for node in trace.nodes
        ),
    )
    assert reevaluate(tampered)[tampered_id] != "118.54"
    assert reevaluate(tampered)[tampered_id] == "118.53"


def test_formula_ids_registered_and_well_formed() -> None:
    pattern = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+\.v[0-9]+$")
    assert FORMULAS
    for formula_id in FORMULAS:
        assert pattern.fullmatch(formula_id)
    for trace in (_chk_007_trace(), _ex_09_b_builder().build(root_measures={})):
        for node in trace.nodes:
            assert node.formula_id in FORMULAS


def test_builder_and_reevaluate_reject_malformed_input() -> None:
    builder = TraceBuilder(engine_version=ENGINE_VERSION)

    def attempt(measure: str, value: Fraction | int, formula_id: str, narrative_key: str) -> str:
        return builder.node(
            measure=measure,
            subject_key="K/POB-01",
            period_key=None,
            value=value,
            currency="USD",
            minor_unit=2,
            formula_id=formula_id,
            inputs=[],
            narrative_key=narrative_key,
        )

    with pytest.raises(ValueError, match="CV-50"):
        attempt("a:b", 1, CUMULATIVE, "sched.cumulative_posted")
    with pytest.raises(ValueError, match="CV-52"):
        attempt("m", 1, "Sched.x", "Sched.x")
    with pytest.raises(ValueError, match="CV-54"):
        attempt("m", 1, CUMULATIVE, "sched.other")
    with pytest.raises(TypeError):
        attempt("m", Fraction(1), CUMULATIVE, "sched.cumulative_posted")
    with pytest.raises(ValueError, match="unknown node"):
        builder.build(root_measures={"revenue": "missing:K:-"})
    with pytest.raises(ValueError, match="unknown source reference type"):
        SourceRef(ref_type="invoice", ref_id="x")  # type: ignore[arg-type]

    trace = _chk_007_trace()
    source_only = next(node for node in trace.nodes if node.id.startswith("revenue_cum:"))
    unregistered = dataclasses.replace(
        trace, nodes=(dataclasses.replace(source_only, formula_id="sched.unknown.v1"),)
    )
    with pytest.raises(ValueError, match="not registered"):
        reevaluate(unregistered)
    orphan = dataclasses.replace(trace, nodes=trace.nodes[:1])  # revenue:P01 without its inputs
    with pytest.raises(ValueError, match="unknown input"):
        reevaluate(orphan)
