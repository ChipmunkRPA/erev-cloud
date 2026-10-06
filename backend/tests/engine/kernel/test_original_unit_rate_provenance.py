"""D-98 candidate 117, F1 (Codex production-20260921-0144 on ad466e60): the original unit revenue
rate's numerator must be bound to the node that actually produced the CURRENT original allocation.
After an approved SSP repin (``LINE_ATTRIBUTES_CHANGED`` naming an approved SSP version, S06-R-26),
``attributes.reallocate`` replaces ``original_allocation`` with the corrected exact share whose
producer is the repin's ``mod_share@<event>:<ob>:-`` node; the inception
``original_allocated_exact`` node is then a stale citation. The admitted A / B fixture (prices
600.00 / 400.00, quantity 1,
approved repin 600 / 400 → 800 / 400): the corrected raw quota of A is 2000/3, the rate 2000/3 ÷ 1.

The regression checks the rate, the cited numerator node (the repin producer, not the inception
node), that the formula's params bind to the cited inputs at the inputs' own precision, and that a
stale inception citation beside the same params is REJECTED on replay (``reevaluate`` raises).

Second form of the same finding (found by the correction itself, eight stage 08 / 15 tests): at
inception with a targeted variable-consideration element (S05-R-14) the current original allocation
is the relative share of the remainder PLUS the targeted share (S05-R-10 ``totals``), produced by
two nodes — ``original_allocated_exact:<ob>:-`` and ``targeted_vc_allocated@<estimate>:<ob>:-`` —
neither of which alone holds the quota. The state carries the producing ids
(``original_allocation_nodes``); the rate cites all of them, the quantity node last, and the
formula binds the ``allocation`` param to the SUM of the cited allocation inputs."""

from __future__ import annotations

import dataclasses
import importlib
import importlib.util
import sys
from fractions import Fraction
from pathlib import Path

import pytest
from erev_engine import compute
from erev_engine.formulas import EXACT_INPUT_FORMULAS, FORMULAS, binds_encoded, rational_param
from erev_engine.money import EXACT_PLACES, format_exact
from erev_engine.stages.s05_allocation import targeted
from erev_engine.trace import Trace, reevaluate
from support import allocation_worlds as worlds

FIXTURE = Path(__file__).parents[1] / "s06_modifications" / "test_s06_exercise.py"


def _attribute_bundle():  # noqa: ANN202 — the fixture module's own return type
    for entry in (str(FIXTURE.parent), str(Path(__file__).parents[2])):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    spec = importlib.util.spec_from_file_location("t06_exercise", FIXTURE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.attribute_bundle()


def test_original_rate_after_a_repin_cites_the_repin_producer() -> None:
    bundle = _attribute_bundle()
    output = compute(bundle)
    book = next(item for item in output.books if item.book_code == "ASC606")
    nodes = {node.id: node for node in book.trace.nodes}
    version = next(
        item for item in book.obligation_versions if item.columns["obligation_key"] == "A"
    )
    repin = next(
        event
        for event in bundle.events
        if event.event_type == "LINE_ATTRIBUTES_CHANGED"
        and "ssp_book_version_id" in dict(event.payload.get("changes", {}))  # type: ignore[arg-type]
    )
    subject = version.subject_key
    raw_quota = Fraction(2000, 3)  # 1,000.00 × 800 / 1,200 after the repin
    assert version.columns["original_allocated_exact"] == raw_quota
    assert version.columns["original_quantity"] == 1
    assert version.columns["original_unit_revenue_rate"] == raw_quota
    node = nodes[version.trace_nodes["original_unit_revenue_rate"]]
    assert node.value == format_exact(raw_quota) == "666.666666666666666667"
    producer, quantity_node = node.inputs
    # the numerator source is the repin's share producer, not the stale inception node
    assert producer == f"mod_share@{repin.event_key}:{subject}:-", producer
    assert producer != f"original_allocated_exact:{subject}:-"
    assert nodes[f"original_allocated_exact:{subject}:-"].value == "600"  # inception, stale
    assert quantity_node == f"original_quantity:{subject}:-"
    assert node.params["allocation"] == "2000/3" and node.params["quantity"] == "1"
    assert reevaluate(book.trace)[node.id] == node.value
    # a stale inception citation beside the same params is rejected on replay
    stale = dataclasses.replace(
        node, inputs=(f"original_allocated_exact:{subject}:-", quantity_node)
    )
    trace = Trace(
        format_version=book.trace.format_version,
        engine_version=book.trace.engine_version,
        nodes=tuple(stale if item.id == node.id else item for item in book.trace.nodes),
        root_measures=book.trace.root_measures,
    )
    with pytest.raises(ValueError, match="cited"):
        reevaluate(trace)


def test_inception_rate_cites_the_inception_node() -> None:
    """Without a repin the producer of the current original allocation is the inception node."""
    bundle = _attribute_bundle()
    output = compute(bundle)
    book = next(item for item in output.books if item.book_code == "ASC606")
    nodes = {node.id: node for node in book.trace.nodes}
    version = next(
        item for item in book.obligation_versions if item.columns["obligation_key"] == "B"
    )
    node = nodes[version.trace_nodes["original_unit_revenue_rate"]]
    # B is not the repin target but the repin re-apportions the whole group: B's current original
    # allocation (1,000.00 × 400 / 1,200 = 1000/3) is produced by the repin share as well
    assert version.columns["original_unit_revenue_rate"] == Fraction(1000, 3)
    assert node.inputs[0].startswith("mod_share@") and node.inputs[0].endswith(
        f":{version.subject_key}:-"
    )


def test_targeted_inception_cites_the_relative_node_and_the_targeted_share() -> None:
    """A / B SSP 100 / 100, fixed 51 / 50, a targeted element of 100 → A (the stage 08 R-07
    world): A's current original allocation is 50.5 + 100 = 301/2, the relative node holding 101/2
    and the targeted share node 100; the rate cites both producers and the quantity node, its
    ``allocation`` param is the raw total, its replay exact; B (no share) cites its relative node
    alone; a citation of A's relative node alone — the pre-F1 emitter — is rejected on replay."""
    element = worlds.element("100", keys=["A"])
    bundle = worlds.targeted_world(
        lines=(("A", "PROD-A", "51"), ("B", "PROD-B", "50")), estimates=[element]
    )
    output = compute(bundle)
    book = next(item for item in output.books if item.book_code == "ASC606")
    nodes = {node.id: node for node in book.trace.nodes}
    versions = {item.columns["obligation_key"]: item for item in book.obligation_versions}
    version = versions["A"]
    subject = version.subject_key
    relative_id = f"original_allocated_exact:{subject}:-"
    share_id = targeted.share_node(element.estimate_key, subject)
    quantity_id = f"original_quantity:{subject}:-"
    quota, quantity = (
        version.columns["original_allocated_exact"],
        version.columns["original_quantity"],
    )
    assert quota == Fraction(301, 2) and quantity == 1
    relative, share = nodes[relative_id], nodes[share_id]
    assert Fraction(relative.value) == Fraction(101, 2)  # the relative share alone: stale
    assert Fraction(share.value) + Fraction(share.rounding_residue or 0) == 100
    node = nodes[version.trace_nodes["original_unit_revenue_rate"]]
    assert node.inputs == (relative_id, share_id, quantity_id)
    assert node.params["allocation"] == "301/2" and node.params["quantity"] == "1"
    assert version.columns["original_unit_revenue_rate"] == Fraction(301, 2)
    assert node.value == format_exact(Fraction(301, 2))
    replayed = reevaluate(book.trace)
    assert replayed[node.id] == node.value
    other = versions["B"]
    other_node = nodes[other.trace_nodes["original_unit_revenue_rate"]]
    assert other_node.inputs == (
        f"original_allocated_exact:{other.subject_key}:-",
        f"original_quantity:{other.subject_key}:-",
    )
    assert other.columns["original_unit_revenue_rate"] == Fraction(101, 2)
    assert replayed[other_node.id] == other_node.value
    # the relative node alone (the pre-F1 citation) is rejected beside the raw total
    stale = dataclasses.replace(node, inputs=(relative_id, quantity_id))
    trace = Trace(
        format_version=book.trace.format_version,
        engine_version=book.trace.engine_version,
        nodes=tuple(stale if item.id == node.id else item for item in book.trace.nodes),
        root_measures=book.trace.root_measures,
    )
    with pytest.raises(ValueError, match="cited"):
        reevaluate(trace)


def test_binding_semantics_are_the_stated_bounds() -> None:
    """ONE reconstruction at both levels (CV-47 (b); D-98 117 F1; Codex 0235): the raw operand
    binds to the cited nodes' EXACT values (value + rounding_residue) within half a unit at 18
    places per independently encoded component, exact equality when they terminate. At emission
    the step reads them through ``TraceBuilder.exact``; at re-evaluation ``reevaluate`` supplies
    them to ``books.unit_revenue_rate.v1`` (``EXACT_INPUT_FORMULAS``). The posted-only value that
    P14 used to feed (666.67 for 2000/3, error 1/300) is refused, so the two paths cannot
    disagree; near-integer and quantity adversaries are refused."""
    half = Fraction(1, 2 * 10**EXACT_PLACES)
    encoded = Fraction("0.333333333333333333")  # format_exact(1/3): no node holds 1/3 itself
    assert binds_encoded(Fraction(1, 3), [encoded])  # 1/3 − encoded = 1/3 of a unit at 18 places
    assert binds_encoded(encoded + half, [encoded])  # at the limit: half a unit per cited node
    assert not binds_encoded(encoded + 2 * half, [encoded])
    assert not binds_encoded(Fraction(1, 3) + half, [encoded])  # 5/6 of a unit off: refused
    assert binds_encoded(Fraction(301, 2), [Fraction(101, 2), Fraction(100)])  # terminating: exact
    assert not binds_encoded(Fraction(301, 2), [Fraction(101, 2), Fraction(100) + 3 * half])  # n=2
    formula = FORMULAS["books.unit_revenue_rate.v1"]
    assert "books.unit_revenue_rate.v1" in EXACT_INPUT_FORMULAS
    both = {"allocation": "2000/3", "quantity": "1"}
    # the repin share: posted 666.67, residue −0.003333333333333333 → exact 666.666666666666666667
    reconstructed = Fraction("666.67") + Fraction("-0.003333333333333333")
    assert abs(reconstructed - Fraction(2000, 3)) == Fraction(1, 3 * 10**EXACT_PLACES)
    assert formula([reconstructed, Fraction(1)], both) == Fraction(2000, 3)
    with pytest.raises(ValueError, match="not bound to the cited input"):
        formula([Fraction("666.67"), Fraction(1)], both)  # the posted value alone: 1/300 off
    with pytest.raises(ValueError, match="not bound to the cited input"):
        formula([Fraction(600), Fraction(1)], both)  # the stale inception node
    near = {"allocation": "1201/2", "quantity": "1"}
    with pytest.raises(ValueError, match="not bound to the cited input"):
        formula([Fraction(600), Fraction(1)], near)  # cited 600 beside raw 600.5
    with pytest.raises(ValueError, match="not bound to the cited input"):
        formula([Fraction(600), Fraction(1)], {"allocation": "600", "quantity": "2"})  # Q 1 vs 2
    with pytest.raises(ValueError, match="not bound to the cited input"):
        formula([Fraction(1, 3), Fraction("0.1")], {"allocation": "1/3", "quantity": "1/5"})
    assert formula(
        [Fraction(1, 3), Fraction("0.1")], {"allocation": "1/3", "quantity": "1/10"}
    ) == (Fraction(10, 3))
    total = {"allocation": "301/2", "quantity": "1"}
    assert formula([Fraction("50.5"), Fraction(100), Fraction(1)], total) == Fraction(301, 2)
    with pytest.raises(ValueError, match="not bound to the cited input"):
        formula([Fraction("50.5"), Fraction(1)], total)  # the relative share alone


def _folded(bundle):  # type: ignore[no-untyped-def]
    """Stages 01 to 05 over one trace builder: the inception state and its nodes."""
    from erev_engine import ENGINE_VERSION
    from erev_engine.stages import (
        s01_canonicalize,
        s02_contract_identification,
        s03_pob_builder,
        s04_transaction_price,
        s05_allocation,
    )
    from erev_engine.trace import TraceBuilder

    ctx = worlds.context(bundle)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    cb = s01_canonicalize.run(bundle, tb)
    identified = s02_contract_identification.run(ctx, cb, tb)
    priced = s04_transaction_price.run(ctx, s03_pob_builder.run(ctx, identified, tb), tb)
    return ctx, s05_allocation.run(ctx, priced, tb), tb


@pytest.mark.parametrize(
    ("key", "field", "raw", "message"),
    [
        ("A", "original_allocation", Fraction(1201, 2), "cited 600 beside raw 600.5"),
        ("A", "original_quantity", Fraction(2), "cited Q 1 beside raw 2"),
    ],
)
def test_emission_refuses_operands_that_do_not_bind_to_the_cited_producers(
    key: str, field: str, raw: Fraction, message: str
) -> None:
    """Codex 0235's adversaries at the EMISSION level: the stage 13 emitter, run over a state whose
    raw operand disagrees with the cited producer by half a unit / a whole unit, refuses with
    ``ENGINE_INVARIANT_VIOLATED`` — no rounded-source rate, no silent substitution."""
    from erev_engine.errors import EngineError
    from erev_engine.stages.s13_books.output_measures import unit_revenue_rates
    from erev_engine.stages.state import Quota

    bundle = worlds.targeted_world(
        lines=(("A", "PROD-A", "600"), ("B", "PROD-B", "400")),
        ssp={"PROD-A": "600", "PROD-B": "400"},  # relative allocation 600 / 400 of TP 1,000
    )
    ctx, st, tb = _folded(bundle)
    ob = next(item for item in st.obligations if item.obligation_key == key)
    assert ob.original_allocation.x_exact == 600 and ob.original_quantity == 1
    assert unit_revenue_rates(ctx, st, tb)[0][ob.subject_key]["original_unit_revenue_rate"] == 600
    doctored = (
        dataclasses.replace(ob, original_allocation=Quota(raw, ob.original_allocation.a_posted))
        if field == "original_allocation"
        else dataclasses.replace(ob, original_quantity=raw)
    )
    state = dataclasses.replace(
        st,
        obligations=tuple(
            doctored if item.subject_key == ob.subject_key else item for item in st.obligations
        ),
    )
    with pytest.raises(EngineError) as refused:
        unit_revenue_rates(ctx, state, tb)
    assert refused.value.code == "ENGINE_INVARIANT_VIOLATED", message
    assert refused.value.detail["rule"] == "CV-47"


def test_emission_refuses_a_fractional_quantity_that_does_not_bind() -> None:
    """Cited Q 0.1 beside raw 0.2 is refused at emission (the K-P117 world's POB-01)."""
    from erev_engine.errors import EngineError
    from erev_engine.stages.s13_books.output_measures import unit_revenue_rates

    raw_module = importlib.import_module("test_original_unit_rate_raw_operands")
    ctx, st, tb = _folded(raw_module._world())
    ob = next(item for item in st.obligations if item.obligation_key == "POB-01")
    assert ob.original_quantity == Fraction(1, 10)
    assert unit_revenue_rates(ctx, st, tb)[0][ob.subject_key]["original_unit_revenue_rate"] == (
        Fraction(10, 3)
    )
    doctored = dataclasses.replace(ob, original_quantity=Fraction(1, 5))
    state = dataclasses.replace(
        st,
        obligations=tuple(
            doctored if item.subject_key == ob.subject_key else item for item in st.obligations
        ),
    )
    with pytest.raises(EngineError) as refused:
        unit_revenue_rates(ctx, state, tb)
    assert refused.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert refused.value.detail["operand"] == "1/5" and refused.value.detail["cited"] == "1/10"


def test_replay_refuses_the_same_adversaries_on_the_real_trace() -> None:
    """Codex 0235's adversaries at the REPLAY level on the admitted repin fixture: Trace variants
    carrying a raw 600.5 beside the cited 600 (B's inception node), a quantity 2 beside the cited
    1, and the stale inception citation beside 2000/3 all make ``reevaluate`` raise; the genuine
    node (2000/3 against posted 666.67 with its residue) replays exactly."""
    bundle = _attribute_bundle()
    output = compute(bundle)
    book = next(item for item in output.books if item.book_code == "ASC606")
    nodes = {node.id: node for node in book.trace.nodes}
    a = next(item for item in book.obligation_versions if item.columns["obligation_key"] == "A")
    b = next(item for item in book.obligation_versions if item.columns["obligation_key"] == "B")
    rate_a = nodes[a.trace_nodes["original_unit_revenue_rate"]]
    rate_b = nodes[b.trace_nodes["original_unit_revenue_rate"]]
    assert reevaluate(book.trace)[rate_a.id] == rate_a.value == "666.666666666666666667"
    producer_b = rate_b.inputs[0]
    assert isinstance(producer_b, str) and producer_b.startswith("mod_share@")
    posted_b = Fraction(nodes[producer_b].value) + Fraction(nodes[producer_b].rounding_residue or 0)
    variants = {
        "cited share beside raw + 0.5": dataclasses.replace(
            rate_b,
            params={
                **rate_b.params,
                "allocation": rational_param(posted_b + Fraction(1, 2)),
            },
        ),
        "cited Q 1 beside raw 2": dataclasses.replace(
            rate_b, params={**rate_b.params, "quantity": "2"}
        ),
        "stale inception node beside 2000/3": dataclasses.replace(
            rate_a, inputs=(f"original_allocated_exact:{a.subject_key}:-", rate_a.inputs[1])
        ),
    }
    for label, variant in variants.items():
        trace = Trace(
            format_version=book.trace.format_version,
            engine_version=book.trace.engine_version,
            nodes=tuple(variant if item.id == variant.id else item for item in book.trace.nodes),
            root_measures=book.trace.root_measures,
        )
        with pytest.raises(ValueError, match="not bound to the cited input"):
            reevaluate(trace)
        del label


def test_a_doctored_stored_residue_is_refused_at_emission_and_at_replay() -> None:
    """Route 1 authentication (Codex 0304; dev-guide DG-KRN-EXP-04 rev 1.52): the residue that
    reconstructs a producer's exact value is the node's STORED ``rounding_residue`` — trace data
    read by the emitter through ``TraceBuilder.exact`` and by ``reevaluate`` alike. Doctoring it
    (value + residue ≠ the producer's exact) is refused on both paths: no copy exists that a
    recomputed posted value could pair with to fake a match."""
    from erev_engine.errors import EngineError
    from erev_engine.stages.s13_books.output_measures import unit_revenue_rates

    element = worlds.element("100", keys=["A"])
    bundle = worlds.targeted_world(
        lines=(("A", "PROD-A", "51"), ("B", "PROD-B", "50")), estimates=[element]
    )
    ctx, st, tb = _folded(bundle)
    ob = next(item for item in st.obligations if item.obligation_key == "A")
    share_id = targeted.share_node(element.estimate_key, ob.subject_key)
    assert unit_revenue_rates(ctx, st, tb)[0][ob.subject_key]["original_unit_revenue_rate"] == (
        Fraction(301, 2)
    )
    # emission: the stage 13 emitter reads the STORED residue of the cited share node
    genuine = tb._nodes[share_id]  # noqa: SLF001 — the doctoring needs the builder's store
    assert genuine.rounding_residue is not None
    tb._nodes[share_id] = dataclasses.replace(  # noqa: SLF001
        genuine,
        rounding_residue=format_exact(Fraction(genuine.rounding_residue) + Fraction(1, 100)),
    )
    with pytest.raises(EngineError) as refused:
        unit_revenue_rates(ctx, st, tb)
    assert refused.value.code == "ENGINE_INVARIANT_VIOLATED"
    tb._nodes[share_id] = genuine  # noqa: SLF001
    # replay: the same doctoring on the committed trace of the whole computation
    output = compute(bundle)
    book = next(item for item in output.books if item.book_code == "ASC606")
    nodes = {node.id: node for node in book.trace.nodes}
    share = nodes[share_id]
    assert reevaluate(book.trace)[
        nodes[
            next(
                v for v in book.obligation_versions if v.columns["obligation_key"] == "A"
            ).trace_nodes["original_unit_revenue_rate"]
        ].id
    ]
    doctored = dataclasses.replace(
        share,
        rounding_residue=format_exact(Fraction(share.rounding_residue or 0) + Fraction(1, 100)),
    )
    trace = Trace(
        format_version=book.trace.format_version,
        engine_version=book.trace.engine_version,
        nodes=tuple(doctored if item.id == share_id else item for item in book.trace.nodes),
        root_measures=book.trace.root_measures,
    )
    with pytest.raises(ValueError, match="not bound to the cited input"):
        reevaluate(trace)
