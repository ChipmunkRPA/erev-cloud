"""T1F-89-1 (ENGINE_SPEC CV-64 rev 1.30; ENGINE_SPEC_B §9.5 rev 1.36; D-98 candidate 134; Codex
production-20260921-1155 §1 / -1249 §2): the ``revenue_amount`` node keeps its posted value
P = Σ (C_after − C_before) and binds the exact activity A = Σ (E_after − E_before) — the exact
segment target at each admitted event's OWN ENG-06 before / after positions — as its exact
(``rounding_residue`` = A − P), through an independently replayable chain: per event and side the
endpoint progress node, the ``FIXED`` exact endpoint (the production ``rec.target_exact.*``
formula) and the endpoint sum (``rec.exact_endpoint.v1``); per event ``revenue_exact_delta@``
(``rec.exact_difference.v1``, raw operands bound to the cited endpoints); the companion
``revenue_amount_exact`` (``rec.exact_activity.v1`` over exactly the admitted deltas), named in the
posted node's ``params.exact_node`` and cross-checked by ``exact_companion_failures``. An adjusted
endpoint makes the exact activity UNAVAILABLE by name (no chain, residue 0, never posted-as-exact).
"""

from __future__ import annotations

import dataclasses
from datetime import date
from fractions import Fraction

import pytest
from erev_engine import _assert_exact_companions, compute
from erev_engine.bundle import BookOutput, InputBundle
from erev_engine.errors import EngineError
from erev_engine.formulas import rational_param
from erev_engine.money import format_exact
from erev_engine.trace import SourceRef, Trace, exact_companion_failures, reevaluate
from support import (
    allocation_worlds,
    bundles,
    cpc_worlds,
    golden_streams,
    intent_totals,
    trace_linkage,
)
from support.recognition import allocated_state
from test_s09_causes_manual_holds import CTX, O1, YEAR_START, _adjustment, _ratable, _run

ENDPOINT = "rec.exact_endpoint.v1"
DIFFERENCE = "rec.exact_difference.v1"
ACTIVITY = "rec.exact_activity.v1"


def _world() -> InputBundle:
    return intent_totals.activated(
        golden_streams.stream("Contract 2", "09").input_bundle(
            preset="LEGACY_PARITY", books=("ASC606", "IFRS15")
        )
    )


def _book(bundle: InputBundle) -> BookOutput:
    output = compute(bundle)
    return next(item for item in output.books if item.book_code == "ASC606")


def _version(book: BookOutput, key: str):  # noqa: ANN202 — ObligationVersionOut
    return next(item for item in book.obligation_versions if item.columns["obligation_key"] == key)


def _chain(book: BookOutput, key: str) -> tuple[dict, object, object, object]:  # noqa: ANN401
    nodes = {node.id: node for node in book.trace.nodes}
    version = _version(book, key)
    posted = nodes[version.trace_nodes["revenue_amount"]]
    companion = nodes[posted.params["exact_node"]]
    return nodes, version, posted, companion


def test_pob_3_binds_the_exact_activity_through_a_replayable_endpoint_chain() -> None:
    """Contract 2 step 09 (LEGACY_PARITY, activated), POB #3 at 2023-05-31: posted 56.64 over the
    two moving events (46.15 + 10.49) — unchanged; exact 600/13 + 62600/5967 = 26000/459; residue
    56/11475; the companion equals value + residue exactly and replays; every admitted event has
    its delta over its own two endpoint chains (guarded or measured), the moving deltas replaying
    the production progress and target formulas; the posted formula and replay are unchanged."""
    bundle = _world()
    book = _book(bundle)
    nodes, version, posted, companion = _chain(book, "POB #3")
    subject = version.subject_key
    assert posted.value == "56.64" and version.columns["revenue_amount"] == 5664
    assert posted.formula_id == "rec.activity_sum.v1" and "exact_basis" not in posted.params
    assert posted.rounding_residue == format_exact(Fraction(56, 11475)) == "0.004880174291938998"
    assert companion.id == f"revenue_amount_exact:{subject}:-"
    assert companion.formula_id == ACTIVITY and companion.rounding_residue is None
    assert companion.value == format_exact(Fraction(26000, 459))
    assert companion.params["exact"] == rational_param(Fraction(26000, 459))
    # here (no signed tie) value + residue happens to equal the companion; the RULE is per field
    assert companion.value == format_exact(Fraction(26000, 459))
    assert posted.rounding_residue == format_exact(Fraction(26000, 459) - Fraction("56.64"))
    cited = [item for item in posted.inputs if isinstance(item, SourceRef)]
    assert len(companion.inputs) == len(cited) == int(companion.params["events"])  # one delta each
    for ref, delta_id in zip(cited, companion.inputs, strict=True):
        assert delta_id == f"revenue_exact_delta@{ref.ref_id}:{subject}:-"
        delta = nodes[delta_id]
        assert delta.formula_id == DIFFERENCE
        assert delta.inputs == (
            f"revenue_exact_after@{ref.ref_id}:{subject}:-",
            f"revenue_exact_before@{ref.ref_id}:{subject}:-",
        )
        for endpoint_id in delta.inputs:
            endpoint = nodes[endpoint_id]
            assert endpoint.formula_id == ENDPOINT
            assert endpoint.params["event"] == ref.ref_id
            if "guard" in endpoint.params:
                assert endpoint.inputs == () and Fraction(endpoint.value) == 0
            else:
                (fixed_id,) = endpoint.inputs  # the FIXED exact endpoint; no PERIOD_VC here
                assert isinstance(fixed_id, str) and fixed_id.startswith("revenue_target_exact_")
                fixed = nodes[fixed_id]
                # inception before the 15 May amendment, prospective after it (CV-62 / CV-63)
                assert fixed.formula_id in {
                    "rec.target_exact.inception.v1",
                    "rec.target_exact.prospective.v1",
                }
                (progress_id,) = fixed.inputs
                assert isinstance(progress_id, str) and progress_id.startswith("progress_ratio_")
                assert nodes[progress_id].formula_id == "rec.progress.units.v1"
    moving = {
        Fraction(nodes[delta_id].value)
        for delta_id in companion.inputs
        if Fraction(nodes[delta_id].value) != 0
    }
    assert moving == {
        Fraction(format_exact(Fraction(600, 13))),
        Fraction(format_exact(Fraction(62600, 5967))),
    }
    replayed = reevaluate(book.trace)
    assert replayed[posted.id] == posted.value  # the posted chain is unchanged
    for node_id in (companion.id, *companion.inputs):
        assert replayed[node_id] == nodes[node_id].value
    assert exact_companion_failures(book.trace, replayed) == []
    trace_linkage.check_book(book, bundle)  # whole-book linkage incl. the companion cross-check


def test_negative_and_zero_activity_carry_their_exact_companions() -> None:
    """POB #1 (three events: +58.85, +13.37, −18.68): residue 37/40950 with a negative delta in
    the companion; VC #1 (no revenue effect): the defined exact sum 0, residue 0, companion 0."""
    book = _book(_world())
    nodes, version, posted, companion = _chain(book, "POB #1")
    assert posted.value == "53.54"
    assert posted.rounding_residue == format_exact(Fraction(37, 40950))
    assert companion.value == format_exact(Fraction(43850, 819))
    assert min(Fraction(nodes[delta_id].value) for delta_id in companion.inputs) < 0
    nodes, version, posted, companion = _chain(book, "VC #1")
    assert posted.value == "0.00" and posted.rounding_residue == "0"
    assert Fraction(companion.value) == 0 and companion.inputs  # events admitted, no effect
    assert exact_companion_failures(book.trace) == []


def test_an_adjusted_endpoint_makes_the_exact_activity_unavailable_by_name() -> None:
    """A version whose admitted event is a manual release (S09-R-38): the event's AFTER endpoint is
    an adjusted target defined in posted units — no exact chain is emitted, the posted node keeps
    residue 0 and names the basis (event and side); the segment exact is never substituted."""
    release = _adjustment(2, date(2026, 6, 15), "MANUAL_RELEASE", "FY2026-P06", ratio="0.5")
    st = allocated_state([_ratable()], events=[release], statuses=((YEAR_START, "ACTIVE"),))
    state, trace = _run(CTX, st)
    nodes = {node.id: node for node in trace.nodes}
    posted = nodes[f"revenue_amount:{O1}:-"]
    assert posted.rounding_residue == "0" and "exact_node" not in posted.params
    assert posted.params["exact_basis"] == (
        f"unavailable: adjusted:manual-adjustment {release.event_key} after"
    )
    assert f"revenue_amount_exact:{O1}:-" not in nodes
    assert not any(node_id.startswith("revenue_exact_") for node_id in nodes)
    measures = next(item for item in state.obligation_measures.values() if item.subject_key == O1)
    assert Fraction(posted.value) == Fraction(measures.revenue_amount, 100)  # posted unchanged
    assert exact_companion_failures(trace) == []


def test_the_cross_check_rejects_a_tampered_residue_or_companion() -> None:
    """The governed cross-check is what verifies a bound residue: a doctored residue or a doctored
    companion value is reported (the replay alone recomputes values, never stored residues)."""
    book = _book(_world())
    nodes, version, posted, companion = _chain(book, "POB #3")

    def with_node(trace: Trace, replacement) -> Trace:  # noqa: ANN001
        return dataclasses.replace(
            trace,
            nodes=tuple(replacement if node.id == replacement.id else node for node in trace.nodes),
        )

    doctored_residue = with_node(book.trace, dataclasses.replace(posted, rounding_residue="0"))
    assert exact_companion_failures(doctored_residue) == [
        f"{posted.id}: rounding_residue 0 != Q18(A_replayed − P) {posted.rounding_residue}"
    ]
    doctored_companion = with_node(
        book.trace, dataclasses.replace(companion, value=format_exact(Fraction(26000, 459) + 1))
    )
    failures = exact_companion_failures(doctored_companion, reevaluate(book.trace))
    assert failures[0] == (
        f"{posted.id}: companion {companion.id!r} value {format_exact(Fraction(26000, 459) + 1)} "
        f"!= Q18(A_replayed) {companion.value}"
    )
    assert len(failures) == 2 and failures[1].startswith(f"{posted.id}: companion")  # + replay
    # a REDIRECTED companion annotation (another exact node of the trace) is refused by identity
    (endpoint_id,) = [item for item in nodes[companion.inputs[0]].inputs if isinstance(item, str)][
        :1
    ]
    redirected = with_node(
        book.trace,
        dataclasses.replace(posted, params={**posted.params, "exact_node": endpoint_id}),
    )
    (failure,) = exact_companion_failures(redirected)
    assert failure.startswith(f"{posted.id}: exact companion {endpoint_id!r} is not its own")
    # a MISSING companion annotation on a legacy / unavailable node is NOT a failure (no claim)
    silent = with_node(
        book.trace,
        dataclasses.replace(
            posted,
            params={k: v for k, v in posted.params.items() if k != "exact_node"},
            rounding_residue="0",
        ),
    )
    assert exact_companion_failures(silent) == []
    # the PRODUCTION side: the engine's post-assembly validation refuses the doctored book
    with pytest.raises(EngineError) as refused:
        _assert_exact_companions(dataclasses.replace(book, trace=doctored_residue))
    assert refused.value.detail["rule"] == "CV-64"
    assert posted.id in refused.value.detail["failures"]
    _assert_exact_companions(book)  # the real book reconstructs


def _signed_tie_world() -> InputBundle:
    """Codex production-20260921-1422's class in its own units through the REAL input path: one
    point-in-time obligation, quantity 4, allocation X = 2.00 (posted 200 cents), activated, then
    deliveries of 0.005 and 2.009999999999999999 units (18 fractional digits, admitted)."""
    line = bundles.booking_line(
        "U",
        product_code="PROD-U",
        quantity="4",
        total_price="2.00",
        start=allocation_worlds.INCEPTION,
        end=allocation_worlds.END,
    )
    base = allocation_worlds.native(
        line,
        entries=[allocation_worlds.entry("PROD-U", point="0.50")],
        overrides={allocation_worlds.TOLERANCE: "NOT_ENFORCED"},
        activated=True,
    )
    events = list(base.events)
    events = cpc_worlds.delivered(events, "U", date(2026, 1, 10), "0.005")
    events = cpc_worlds.delivered(events, "U", date(2026, 1, 20), "2.009999999999999999")
    ordered = sorted(
        events, key=lambda item: (item.effective_date, item.record_seq, item.event_key)
    )
    return dataclasses.replace(base, events=tuple(ordered))


def test_signed_half_up_tie_is_admitted_and_validated_per_field() -> None:
    """D-98 134 amendment 1 (Codex 1422 T1F-CV64-ENC-1), the production compute seam and the
    explanation-verification seam: E 0 → 0.0025 → 1.0074999999999999995 (C 0 → 0.00 → 1.01), so
    A = 1.0074999999999999995 and A − P = −0.0025000000000000005 sit on opposite-signed ties —
    Q18(A) = 1.0075 while Q18(A − P) = −0.002500000000000001, and P + residue ≠ Q18(A). Fail-first
    at 55582a9f: ``compute`` REFUSED this admitted input (ENGINE_INVARIANT_VIOLATED CV-64, "value +
    rounding_residue 1.007499999999999999 != companion 1.0075"). Now each field is validated
    against its own encoding of the replayed exact: compute admits, the explain seam's check is
    clean, and one negative per field is still refused by name."""
    bundle = _signed_tie_world()
    book = _book(bundle)  # compute → assert_identities → _assert_exact_companions admits
    nodes, version, posted, companion = _chain(book, "U")
    assert posted.value == "1.01" and version.columns["revenue_amount"] == 101
    assert companion.value == format_exact(Fraction("1.0074999999999999995")) == "1.0075"
    assert posted.rounding_residue == "-0.002500000000000001"
    assert posted.rounding_residue == format_exact(
        Fraction("1.0074999999999999995") - Fraction("1.01")
    )
    # the withdrawn premise fails here by one unit in the 18th place — and that is not a defect
    assert Fraction(posted.value) + Fraction(posted.rounding_residue) != Fraction(companion.value)
    _assert_exact_companions(book)
    replayed = reevaluate(book.trace)
    assert exact_companion_failures(book.trace, replayed) == []  # the explain seam's call
    assert replayed[companion.id] == companion.value

    def with_node(trace: Trace, replacement) -> Trace:  # noqa: ANN001
        return dataclasses.replace(
            trace,
            nodes=tuple(replacement if node.id == replacement.id else node for node in trace.nodes),
        )

    (residue_failure,) = exact_companion_failures(
        with_node(book.trace, dataclasses.replace(posted, rounding_residue="-0.0025"))
    )
    assert residue_failure == (
        f"{posted.id}: rounding_residue -0.0025 != Q18(A_replayed − P) -0.002500000000000001"
    )
    value_failure = exact_companion_failures(
        with_node(book.trace, dataclasses.replace(companion, value="1.007499999999999999"))
    )[0]
    assert value_failure == (
        f"{posted.id}: companion {companion.id!r} value 1.007499999999999999 != Q18(A_replayed) "
        "1.0075"
    )
    with pytest.raises(EngineError) as refused:
        _assert_exact_companions(
            dataclasses.replace(
                book, trace=with_node(book.trace, dataclasses.replace(posted, rounding_residue="0"))
            )
        )
    assert refused.value.detail["rule"] == "CV-64"


def test_legacy_unavailable_is_distinct_from_a_named_but_missing_companion() -> None:
    """D-98 134 amendment 1, condition (2): a posted node WITHOUT ``exact_node`` (a legacy trace or
    an explicitly unavailable activity) makes no claim and is not checked — production admits it;
    a node that NAMES a companion absent from the trace is refused by name at every path (the
    checker, the production post-assembly pass)."""
    book = _book(_world())
    nodes, version, posted, companion = _chain(book, "POB #3")

    def with_node(trace: Trace, replacement) -> Trace:  # noqa: ANN001
        return dataclasses.replace(
            trace,
            nodes=tuple(replacement if node.id == replacement.id else node for node in trace.nodes),
        )

    legacy = with_node(
        book.trace,
        dataclasses.replace(
            posted,
            params={k: v for k, v in posted.params.items() if k != "exact_node"},
            rounding_residue="0",
        ),
    )
    assert exact_companion_failures(legacy, reevaluate(legacy)) == []
    _assert_exact_companions(dataclasses.replace(book, trace=legacy))  # no claim → admitted
    unavailable = with_node(
        book.trace,
        dataclasses.replace(
            posted,
            params={
                **{k: v for k, v in posted.params.items() if k != "exact_node"},
                "exact_basis": "unavailable: adjusted:hold Contract 2/EV-000099 after",
            },
            rounding_residue="0",
        ),
    )
    assert exact_companion_failures(unavailable) == []  # explicitly unavailable: no claim either
    missing_id = f"revenue_amount_exact:{version.subject_key}:-"
    missing = dataclasses.replace(
        book.trace, nodes=tuple(node for node in book.trace.nodes if node.id != missing_id)
    )
    assert exact_companion_failures(missing) == [
        f"{posted.id}: exact companion {missing_id!r} is not in the trace"
    ]
    with pytest.raises(EngineError) as refused:
        _assert_exact_companions(dataclasses.replace(book, trace=missing))
    assert (
        refused.value.detail["rule"] == "CV-64" and missing_id in refused.value.detail["failures"]
    )
