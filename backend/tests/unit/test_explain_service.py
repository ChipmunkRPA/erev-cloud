"""Explain service core (dev-guide §5.16 DG-KRN-EXP-06, DG-KRN-EXP-07; BUILD_SPEC PLF-20)."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import pytest
from erev_api.explain.narratives import NARRATIVES, format_amount, format_date, render
from erev_api.explain.service import (
    DEFAULT_DEPTH,
    MAX_DEPTH,
    NOT_TRACED,
    NodeInput,
    SourceInput,
    _linked_node_id,
    _subject,
    build_explain,
)
from erev_api.problems import Problem
from erev_engine import ENGINE_VERSION
from erev_engine.formulas import FORMULAS
from erev_engine.trace import (
    ABSENT_NO_RESOLUTION,
    ABSENT_ZERO_TOTAL,
    SourceRef,
    Trace,
    TraceBuilder,
    reevaluate,
)

CHAIN_LENGTH = 25


def chain_trace() -> tuple[Trace, list[str]]:
    """25 revenue nodes, each the previous node less a zero source amount; root first."""
    builder = TraceBuilder(engine_version=ENGINE_VERSION)
    ids: list[str] = []
    for index in range(1, CHAIN_LENGTH + 1):
        first: str | SourceRef = (
            ids[-1] if ids else SourceRef("source_record", "OPENING", {"value": "1234567.89"})
        )
        ids.append(
            builder.node(
                measure="revenue",
                subject_key=f"POB #{index}",
                period_key="FY2026-P09",
                value=123456789,
                currency="USD",
                minor_unit=2,
                formula_id="sched.period_difference.v1",
                inputs=[first, SourceRef("source_record", f"ZERO-{index}", {"value": "0"})],
                narrative_key="sched.period_difference",
            )
        )
    trace = builder.build(root_measures={"revenue": ids[-1]})
    assert set(reevaluate(trace).values()) == {"1234567.89"}
    return trace, list(reversed(ids))


def test_krn_exp_06_depth_limit() -> None:
    trace, chain = chain_trace()
    assert (DEFAULT_DEPTH, MAX_DEPTH) == (6, 20)

    default = build_explain(trace, chain[0])
    assert [node.id for node in default.nodes] == chain[:7]
    assert len(default.narrative) == 7
    # The deepest returned node still names the input the depth limit left out.
    assert default.nodes[-1].inputs[0] == NodeInput(node_id=chain[7])

    deep = build_explain(trace, chain[0], depth=20)
    assert [node.id for node in deep.nodes] == chain[:21]

    root_only = build_explain(trace, chain[0], depth=0)
    assert [node.id for node in root_only.nodes] == chain[:1]

    for depth in (21, -1):
        with pytest.raises(Problem) as excinfo:
            build_explain(trace, chain[0], depth=depth)
        problem = excinfo.value
        assert (problem.status, problem.slug) == (422, "validation-failed")
        assert [(error.field, error.rule_id) for error in problem.errors] == [
            ("depth", "DG-KRN-EXP-06")
        ]

    with pytest.raises(Problem) as missing:
        build_explain(trace, "revenue:POB #99:FY2026-P09")
    assert (missing.value.status, missing.value.slug) == (404, "not-found")


def test_krn_exp_06_value_equals_node() -> None:
    trace, chain = chain_trace()
    root = next(node for node in trace.nodes if node.id == chain[0])
    explanation = build_explain(trace, chain[0])
    assert explanation.value == root.value == "1234567.89"
    assert (explanation.root_node_id, explanation.measure, explanation.currency) == (
        chain[0],
        "revenue",
        "USD",
    )
    assert explanation.engine_version == ENGINE_VERSION
    returned = explanation.nodes[0]
    assert (returned.value, returned.rounding_residue, returned.params) == (
        root.value,
        root.rounding_residue,
        root.params,
    )
    assert returned.inputs == (
        NodeInput(node_id=chain[1]),
        SourceInput(ref_type="source_record", ref_id="ZERO-25", label="source_record ZERO-25"),
    )
    assert explanation.narrative[0] == (
        "Amount for FY2026-P09 = cumulative USD 1,234,567.89 − previous cumulative 0 "
        "= USD 1,234,567.89."
    )


def test_krn_exp_07_narrative_formats() -> None:
    builder = TraceBuilder(engine_version=ENGINE_VERSION)
    node_id = builder.node(
        measure="revenue_cum",
        subject_key="POB #1",
        period_key="FY2026-P09",
        value=123456789,
        currency="USD",
        minor_unit=2,
        formula_id="sched.cumulative_posted.v1",
        inputs=[
            SourceRef("source_record", "ALLOCATION-EXACT", {"value": "2469135.78"}),
            SourceRef("source_record", "ALLOCATION-POSTED", {"value": "2469135.78"}),
            SourceRef("estimate_version", "PROGRESS", {"value": "0.5"}),
        ],
        params={"as_of": "2026-09-07"},
        narrative_key="sched.cumulative_posted",
    )
    trace = builder.build(root_measures={"revenue_cum": node_id})
    assert reevaluate(trace) == {node_id: "1234567.89"}

    text = render(trace.nodes[0], {})
    assert "USD 1,234,567.89" in text
    assert "07 Sep 2026" in text
    assert text == (
        "Cumulative amount to 07 Sep 2026 = 2,469,135.78 × 0.5, rounded half up to the minor unit "
        "and bounded by the allocation 2,469,135.78 = USD 1,234,567.89."
    )

    assert format_amount("-1234", "EUR", 2) == "EUR (1,234.00)"
    assert format_amount("1000.5", "BHD") == "BHD 1,000.500"
    assert format_amount("1500", "JPY") == "JPY 1,500"
    assert format_amount("-0.333333333333333333", None) == "(0.333333333333333333)"
    assert format_date("2026-01-31") == "31 Jan 2026"
    with pytest.raises(ValueError):
        format_date("20260907")


def test_narratives_cover_referenced_keys() -> None:
    trace, _ = chain_trace()
    assert {node.narrative_key for node in trace.nodes} <= set(NARRATIVES)
    # Every registered formula can be explained (05 RCP-26).
    assert {formula_id.rsplit(".v", 1)[0] for formula_id in FORMULAS} <= set(NARRATIVES)

    builder = TraceBuilder(engine_version=ENGINE_VERSION)
    probe = builder.node(
        measure="probe",
        subject_key="POB #1",
        period_key=None,
        value=1,
        currency=None,
        minor_unit=None,
        formula_id="probe.unregistered.v1",
        inputs=[],
        narrative_key="probe.unregistered",
    )
    node = builder.build(root_measures={"probe": probe}).nodes[0]
    with pytest.raises(KeyError):
        render(node, {})


def test_cpc_share_based_narrative_renders_with_the_node_value() -> None:
    """D-91 C606-03: ``tp.cpc_share_based`` explains the element node from its inputs (the award
    source, the related obligations' posted revenue and concession nodes) with the node value; the
    revised ``tp.cpc_release`` covers the ordinary release, the composed release and the derived
    asset."""
    builder = TraceBuilder(engine_version=ENGINE_VERSION)
    revenue = builder.node(
        measure="revenue_cum",
        subject_key="C-WARRANT/L1-SUPPLY",
        period_key="FY2026-P06",
        value=40_000_000,
        currency="USD",
        minor_unit=2,
        formula_id="sched.period_difference.v1",
        inputs=[
            SourceRef("source_record", "GROSS", {"value": "400000.00"}),
            SourceRef("source_record", "NONE", {"value": "0"}),
        ],
        narrative_key="sched.period_difference",
    )
    element = builder.node(
        measure="share_based_reduction_element_cum",
        subject_key="C-WARRANT/SBC-WARRANT",
        period_key="FY2026-P06",
        value=2_000_000,
        currency="USD",
        minor_unit=2,
        formula_id="tp.cpc_share_based.v1",
        inputs=[
            SourceRef("estimate_version", "C-WARRANT/SBC-WARRANT@v1", {"value": "50000"}),
            revenue,
        ],
        params={
            "signs": "+",
            "expected": "1000000",
            "vesting_probable": "true",
            "grant_date": "2026-01-01",
            "period_end": "2026-06-30",
            "timing": "LATER_OF_RELATED_REVENUE_AND_GRANT",
        },
        narrative_key="tp.cpc_share_based",
    )
    trace = builder.build(root_measures={"share_based_reduction_element_cum": element})
    assert reevaluate(trace)[element] == "20000.00"
    node = next(item for item in trace.nodes if item.id == element)
    text = render(node, {})
    assert "USD 20,000.00" in text
    assert "grant-date fair value" in text and "expected related revenue" in text
    assert "ordinary release" in NARRATIVES["tp.cpc_release"]
    assert "share-based" in NARRATIVES["tp.cpc_release"]


def test_unmeasured_reclass_narrative_renders_without_an_input() -> None:
    """ENGINE_SPEC_B S10-R-22 rev 1.100 (ENG-S10-FUTURE-INCEPTION-1): the version-state
    ``netting_reclass_amount`` of an obligation whose contracting entity has no measured period is
    a node without an input; its sentence names no input and the explanation is built."""
    builder = TraceBuilder(engine_version=ENGINE_VERSION)
    node_id = builder.node(
        measure="netting_reclass_amount",
        subject_key="C-MAY/L1",
        period_key=None,
        value=0,
        currency="USD",
        minor_unit=2,
        formula_id="pos.reclass_attribution.no_measured_period.v1",
        inputs=[],
        params={"as_of": "2026-05-01", "key": "C-MAY/L1"},
        exact=Fraction(0),
        narrative_key="pos.reclass_attribution.no_measured_period",
    )
    trace = builder.build(root_measures={"netting_reclass_amount": node_id})
    assert reevaluate(trace) == {node_id: "0.00"}
    explanation = build_explain(trace, node_id)
    assert explanation.narrative == (
        "Period-end reclass at the version date 01 May 2026: no accounting period from the "
        "contract's inception on is open for its contracting entity yet, so none is evaluated "
        "and nothing is attributed to this obligation = USD 0.00.",
    )


def test_cv_50_named_absence_link_is_not_traced_and_names_the_absence() -> None:
    """CV-50 rev 1.29: a row's ``trace_nodes`` entry that names the contract-permitted absence
    admitted for its column over the stored display 0 (DEV-054's Σw = 0 ratio; a LEGACY-VC
    created line) binds no node BY CONTRACT — the explain answers not-found naming the absence; a
    node id passes through; an unbound column is None (the same not-traced 404 downstream); every
    malformed stored state is a 422 validation problem on the column, rule CV-50."""
    zero = Decimal("0.000000000000000000")
    for column, absence in (
        ("allocation_weight", ABSENT_ZERO_TOTAL),
        ("original_ssp_selected", ABSENT_NO_RESOLUTION),
    ):
        with pytest.raises(Problem) as absent:
            _linked_node_id(column, absence, zero)
        assert (absent.value.status, absent.value.slug) == (404, "not-found")
        assert absent.value.detail == f"{NOT_TRACED} {absence}"
    node_id = "revenue_cum:Contract 1/POB %231:-"
    assert _linked_node_id("revenue_cum", node_id, Decimal("1.5")) == node_id
    assert _linked_node_id("revenue_cum", None, None) is None
    assert _linked_node_id("revenue_cum", 7, None) is None
    # the shared recognition (column + value), never a prefix test — Codex 1054 §1 R1 / 1101 §1:
    # an unknown reason, a swapped reason, a marker on the REQUIRED zero total's column, an
    # admitted reason over a non-zero or NULL value are MALFORMED states, never a legitimate absence
    for column, link, value in (
        ("allocation_weight", "absent:unknown-reason", zero),
        ("original_ssp_selected", ABSENT_ZERO_TOTAL, zero),
        ("allocation_weight", ABSENT_NO_RESOLUTION, zero),
        ("original_total_contract_ssp", ABSENT_ZERO_TOTAL, zero),
        ("original_total_contract_ssp", ABSENT_NO_RESOLUTION, zero),
        ("allocation_weight", ABSENT_ZERO_TOTAL, Decimal("0.25")),
        ("original_ssp_selected", ABSENT_NO_RESOLUTION, Decimal("600")),
        ("allocation_weight", ABSENT_ZERO_TOTAL, None),
    ):
        with pytest.raises(Problem) as malformed:
            _linked_node_id(column, link, value)
        assert (malformed.value.status, malformed.value.slug) == (422, "validation-failed")
        assert [(error.field, error.rule_id) for error in malformed.value.errors] == [
            (column, "CV-50")
        ]


def test_the_obligation_subject_is_the_anchors_or_the_engines_key_never_a_raw_join() -> None:
    """Key audit of supervisor ruling R-16 (ENGINE_SPEC CV-21): the subject of an obligation's
    period nodes is the middle part of its ``revenue_cum`` node id; without that anchor it is the
    engine's own key of the contract and the obligation — the raw join ``Contract 1/POB #1`` names
    no node of the legacy UAT contract."""
    contract_row = {"external_id": "Contract 1"}
    row = {"obligation_key": "POB #1"}
    anchored = {"revenue_cum": "revenue_cum:Contract 1/POB %231:-"}
    assert _subject(anchored, contract_row, row) == "Contract 1/POB %231"
    assert _subject({}, contract_row, row) == "Contract 1/POB %231"
    assert _subject({}, {"external_id": "A:B"}, {"obligation_key": "C/D"}) == "A%3AB/C%2FD"
