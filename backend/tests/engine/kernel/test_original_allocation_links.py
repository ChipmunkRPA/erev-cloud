"""D-98 candidate 121 (Codex production-20260921-0247; assigned to lane ENG-T1F): the CV-50 links
of
``original_allocated_exact`` and ``original_allocated_amount`` name the node that produced the
CURRENT original allocation, never the partial or stale version-state node:

- targeted inception (S05-R-14): the columns publish the S05-R-10 total — the relative share of the
  remainder PLUS the targeted shares — while the version-state nodes ``original_allocated_*:<ob>:-``
  hold the relative share alone (Codex's witness: 301/2 published, 101/2 linked); stage 05 now emits
  the sum nodes ``<column>@<booking event>:<ob>:-`` over the relative node and the shares and the
  assembler links them;
- an approved SSP repin (S06-R-26) replaces the quota; the columns link the repin's
  ``<column>@<event>`` pair over its ``mod_share@`` node, not the retained inception node
  (Codex's witness: 2000/3 published, 600 linked);
- an obligation a boundary creates links its creation pair over the creation producer.

Controls: an obligation with no share and a world with no targeted element keep their relative
node; restoring the partial link fails under the EXISTING checker (``trace_linkage.check_book``,
half a unit at 18 places — no new tolerance, exception or skip).

Fail-first on the committed engine 4d472356 (``.run/t1f2/fail-first-121-4d472356.log``): the
targeted world fails ``check_book`` (node 5050, column 15050), the repin world fails (node 60000,
column 66667), the created obligation of ``ex_09_a`` has no allocation links at all.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType, ModuleType

import pytest
from erev_engine import compute
from erev_engine.bundle import BookOutput, InputBundle, ObligationVersionOut
from erev_engine.formulas import EXACT_INPUT_FORMULAS
from erev_engine.money import format_exact
from erev_engine.stages.s05_allocation import targeted
from erev_engine.trace import TraceNode, reevaluate
from support import allocation_worlds as worlds
from support import trace_linkage

S06_TESTS = Path(__file__).resolve().parents[1] / "s06_modifications"
NO_EXCEPTIONS = MappingProxyType(
    {
        "obligation_version": frozenset(),
        "contract_version": frozenset(),
        "contract_version_balance": frozenset(),
    }
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


def _booking_event(bundle: InputBundle) -> str:
    (event,) = [item for item in bundle.events if item.event_type == "CONTRACT_BOOKED"]
    return event.event_key


def _assert_pair(
    version: ObligationVersionOut,
    nodes: dict[str, TraceNode],
    event_key: str,
    components: tuple[str, ...],
    currency: str,
) -> None:
    """Both columns link the ``<column>@<event>`` pair over ``components``, with the stored value,
    subject, currency, provenance (the components as inputs) and an exact replay."""
    subject = version.subject_key
    quota = version.columns["original_allocated_exact"]
    amount = version.columns["original_allocated_amount"]
    assert isinstance(quota, Fraction) and isinstance(amount, int)
    exact_id = f"original_allocated_exact@{event_key}:{subject}:-"
    amount_id = f"original_allocated_amount@{event_key}:{subject}:-"
    assert version.trace_nodes["original_allocated_exact"] == exact_id
    assert version.trace_nodes["original_allocated_amount"] == amount_id
    exact, posted = nodes[exact_id], nodes[amount_id]
    assert exact.value == format_exact(quota) and exact.rounding_residue is None
    assert exact.currency == currency and posted.currency == currency
    assert exact.formula_id == "alloc.original_total.v1" in EXACT_INPUT_FORMULAS
    assert posted.formula_id == "alloc.original_total_amount.v1"
    assert exact.params["exact"] == f"{quota.numerator}/{quota.denominator}".removesuffix("/1")
    assert set(exact.inputs) == set(components) and len(exact.inputs) == len(components)
    assert Fraction(posted.value) * 10 ** int(posted.params["minor_unit"]) == amount
    assert Fraction(posted.value) + Fraction(posted.rounding_residue or 0) == quota or (
        abs(Fraction(posted.value) + Fraction(posted.rounding_residue or 0) - quota)
        <= Fraction(1, 2 * 10**18)
    )


def test_targeted_inception_links_the_sum_nodes_not_the_relative_node() -> None:
    """A / B SSP 100 / 100, fixed 51 / 50, targeted 100 → A: A publishes 301/2 = 101/2 + 100 and
    links the S05-R-10 sum nodes under the booking event, whose inputs are the relative node and
    the share; B (no share) keeps its relative node; the book passes the existing checker; the
    trace replays; the partial link fails the checker."""
    element = worlds.element("100", keys=["A"])
    bundle = worlds.targeted_world(
        lines=(("A", "PROD-A", "51"), ("B", "PROD-B", "50")), estimates=[element]
    )
    book = _book(bundle)
    nodes = {node.id: node for node in book.trace.nodes}
    booking = _booking_event(bundle)
    a = _version(book, "A")
    subject = a.subject_key
    relative_exact = f"original_allocated_exact:{subject}:-"
    relative_amount = f"original_allocated_amount:{subject}:-"
    share = targeted.share_node(element.estimate_key, subject)
    assert a.columns["original_allocated_exact"] == Fraction(301, 2)
    assert Fraction(nodes[relative_exact].value) == Fraction(101, 2)  # the partial node, kept
    _assert_pair(a, nodes, booking, (relative_exact, share), bundle.group.transaction_currency)
    posted = nodes[f"original_allocated_amount@{booking}:{subject}:-"]
    assert set(posted.inputs) == {relative_amount, share}
    b = _version(book, "B")
    assert (
        b.trace_nodes["original_allocated_exact"] == f"original_allocated_exact:{b.subject_key}:-"
    )
    assert b.trace_nodes["original_allocated_amount"] == (
        f"original_allocated_amount:{b.subject_key}:-"
    )
    assert not any(
        node.measure.startswith("original_allocated_exact@")
        for node in nodes.values()
        if node.id.endswith(f":{b.subject_key}:-")
    )
    trace_linkage.check_book(book, bundle, exceptions=NO_EXCEPTIONS)
    replayed = reevaluate(book.trace)
    for node_id in (
        f"original_allocated_exact@{booking}:{subject}:-",
        f"original_allocated_amount@{booking}:{subject}:-",
    ):
        assert replayed[node_id] == nodes[node_id].value
    # restoring the partial link fails under the existing checker (half a unit at 18 places)
    partial = dataclasses.replace(
        a,
        trace_nodes=MappingProxyType({**a.trace_nodes, "original_allocated_exact": relative_exact}),
    )
    mutated = dataclasses.replace(
        book,
        obligation_versions=tuple(
            partial if v.subject_key == subject else v for v in book.obligation_versions
        ),
    )
    with pytest.raises(AssertionError, match="original_allocated_exact"):
        trace_linkage.check_book(mutated, bundle, exceptions=NO_EXCEPTIONS)


def test_multiple_targeted_components_are_counted_once() -> None:
    """Two targeted elements both → A (100 and 50) beside the untargeted remainder: A's total is
    the relative share plus BOTH shares, each cited once; C (no share) keeps its relative node."""
    first = worlds.element("100", keys=["A"])
    second = dataclasses.replace(
        worlds.element("50", keys=["A"]),
        estimate_key="K-01/VC-2",
        element_code="VC-2",
        version_key="K-01/VC-2@v1",
    )
    bundle = worlds.targeted_world(
        lines=(("A", "PROD-A", "50"), ("B", "PROD-B", "100"), ("C", "PROD-C", "150")),
        ssp={"PROD-A": "100", "PROD-B": "200", "PROD-C": "300"},
        estimates=[first, second],
    )
    book = _book(bundle)
    nodes = {node.id: node for node in book.trace.nodes}
    booking = _booking_event(bundle)
    a = _version(book, "A")
    subject = a.subject_key
    relative = f"original_allocated_exact:{subject}:-"
    shares = tuple(targeted.share_node(item.estimate_key, subject) for item in (first, second))
    quota = a.columns["original_allocated_exact"]
    assert isinstance(quota, Fraction)
    assert quota == Fraction(nodes[relative].value) + sum(
        (Fraction(nodes[s].value) + Fraction(nodes[s].rounding_residue or 0) for s in shares),
        Fraction(0),
    )
    assert quota == Fraction(50) + 100 + 50  # 300 fixed at 1:2:3 → 50; the two shares
    _assert_pair(a, nodes, booking, (relative, *shares), bundle.group.transaction_currency)
    c = _version(book, "C")
    assert (
        c.trace_nodes["original_allocated_exact"] == f"original_allocated_exact:{c.subject_key}:-"
    )
    trace_linkage.check_book(book, bundle, exceptions=NO_EXCEPTIONS)
    assert reevaluate(book.trace)[a.trace_nodes["original_allocated_exact"]] == format_exact(quota)


def test_no_target_world_keeps_the_relative_nodes() -> None:
    """Control: without a targeted element no sum node exists and both obligations link their
    stage 05 version-state nodes; the checker passes as before."""
    bundle = worlds.targeted_world(lines=(("A", "PROD-A", "51"), ("B", "PROD-B", "50")))
    book = _book(bundle)
    nodes = {node.id: node for node in book.trace.nodes}
    assert not any("original_allocated_exact@" in node_id for node_id in nodes)
    for key in ("A", "B"):
        version = _version(book, key)
        assert version.trace_nodes["original_allocated_exact"] == (
            f"original_allocated_exact:{version.subject_key}:-"
        )
        assert version.trace_nodes["original_allocated_amount"] == (
            f"original_allocated_amount:{version.subject_key}:-"
        )
    trace_linkage.check_book(book, bundle, exceptions=NO_EXCEPTIONS)


def test_repin_links_the_repin_pair_not_the_inception_node() -> None:
    """The admitted A / B repin fixture (600 / 400 → 800 / 400): A publishes 2000/3 and links the
    repin's pair over its ``mod_share@`` node; the inception node (600) stays in the trace as the
    retained history and is not the link; every obligation of the group is re-measured."""
    exercise = _module("test_s06_exercise")
    bundle = exercise.attribute_bundle()
    book = _book(bundle)
    nodes = {node.id: node for node in book.trace.nodes}
    a = _version(book, "A")
    subject = a.subject_key
    assert a.columns["original_allocated_exact"] == Fraction(2000, 3)
    (repin,) = [
        node_id
        for node_id in nodes
        if node_id.startswith("mod_share@") and node_id.endswith(f":{subject}:-")
    ]
    event_key = repin[len("mod_share@") : -len(f":{subject}:-")]
    assert nodes[f"original_allocated_exact:{subject}:-"].value == "600"  # retained, not linked
    _assert_pair(a, nodes, event_key, (repin,), bundle.group.transaction_currency)
    b = _version(book, "B")
    _assert_pair(
        b,
        nodes,
        event_key,
        (f"mod_share@{event_key}:{b.subject_key}:-",),
        bundle.group.transaction_currency,
    )
    # D-98 123 (ENGINE_SPEC 1.29): the repin's corrected ``original_ssp_selected`` and its
    # dependents now link their ``@<event>`` producers too, so the whole-book checker PASSES on
    # this fixture with no exceptions (the known red of the first 121 slice is gone; the 123 / 124
    # module asserts the dependents). The two allocation links are also put through the checker's
    # own value primitives for A and B.
    trace_linkage.check_book(book, bundle, exceptions=NO_EXCEPTIONS)
    currency = bundle.group.transaction_currency
    minor_unit = bundle.currencies[currency].minor_unit
    for version in (a, b):
        where: tuple[object, ...] = ("obligation_version", "ASC606", version.subject_key)
        exact = nodes[version.trace_nodes["original_allocated_exact"]]
        trace_linkage._assert_exact(
            exact,
            version.columns["original_allocated_exact"],
            where,
            "original_allocated_exact",
            currency,
        )
        posted = nodes[version.trace_nodes["original_allocated_amount"]]
        trace_linkage._assert_money(
            posted, version.columns["original_allocated_amount"], minor_unit, where, magnitude=False
        )
        # restoring the inception link fails the same primitive (600 against 2000/3; 60000 / 66667)
        with pytest.raises(AssertionError):
            trace_linkage._assert_exact(
                nodes[f"original_allocated_exact:{version.subject_key}:-"],
                version.columns["original_allocated_exact"],
                where,
                "original_allocated_exact",
                currency,
            )
    replayed = reevaluate(book.trace)
    assert replayed[a.trace_nodes["original_allocated_exact"]] == format_exact(Fraction(2000, 3))
    # the rate's numerator source is the repin share (0235: source-correct) — not the pair node
    rate = nodes[a.trace_nodes["original_unit_revenue_rate"]]
    assert rate.inputs[0] == repin


def test_created_obligation_links_its_creation_pair() -> None:
    """The native added good of ``ex_09_a`` (POB-02) links the creating boundary's pair over its
    ``mod_share@`` node; the two allocation columns are linked where before none of the created
    obligation's columns was (the other six snapshot columns stay unlinked — reported)."""
    prospective = _module("test_s06_prospective")
    bundle = prospective.ex_09_a()
    book = _book(bundle)
    nodes = {node.id: node for node in book.trace.nodes}
    added = _version(book, "POB-02")
    subject = added.subject_key
    (producer,) = [
        node_id
        for node_id in nodes
        if node_id.startswith("mod_share@") and node_id.endswith(f":{subject}:-")
    ]
    event_key = producer[len("mod_share@") : -len(f":{subject}:-")]
    _assert_pair(added, nodes, event_key, (producer,), bundle.group.transaction_currency)
    assert f"original_allocated_exact:{subject}:-" not in nodes  # no inception node fabricated
    replayed = reevaluate(book.trace)
    assert (
        replayed[added.trace_nodes["original_allocated_exact"]]
        == nodes[added.trace_nodes["original_allocated_exact"]].value
    )


def test_multi_pool_posted_cents_are_summed_not_rerounded() -> None:
    """Codex 0312's conservation witness: a one-cent fixed pool over three equal SSPs gives one key
    a posted cent whose raw share (1/300) rounds to zero; two more one-cent targeted pools over the
    same three keys give it two more cents. The amount node is Σ of the posted contributions (the
    column's actual computation) and the exact node the raw total; re-rounding the raw total would
    move cents, and the per-pool posted sums are conserved."""
    from erev_engine.money import round_half_up

    first = worlds.element("0.01", keys=["A", "B", "C"])
    second = dataclasses.replace(
        worlds.element("0.01", keys=["A", "B", "C"]),
        estimate_key="K-01/VC-2",
        element_code="VC-2",
        version_key="K-01/VC-2@v1",
    )
    bundle = worlds.targeted_world(
        lines=(("A", "PROD-A", "0.01"), ("B", "PROD-B", "0"), ("C", "PROD-C", "0")),
        estimates=[first, second],
    )
    book = _book(bundle)
    nodes = {node.id: node for node in book.trace.nodes}
    booking = _booking_event(bundle)
    posted_total = 0
    rerounded_total = 0
    moved = False
    for key in ("A", "B", "C"):
        version = _version(book, key)
        subject = version.subject_key
        quota, amount = (
            version.columns["original_allocated_exact"],
            version.columns["original_allocated_amount"],
        )
        assert isinstance(quota, Fraction) and isinstance(amount, int)
        exact_id = f"original_allocated_exact@{booking}:{subject}:-"
        amount_id = f"original_allocated_amount@{booking}:{subject}:-"
        assert version.trace_nodes["original_allocated_exact"] == exact_id
        assert version.trace_nodes["original_allocated_amount"] == amount_id
        components = nodes[amount_id].inputs
        assert len(components) == 3  # the base share and the two targeted shares, each once
        summed = sum((Fraction(nodes[str(c)].value) for c in components), Fraction(0))
        assert summed * 100 == amount  # Σ posted contributions == a_posted exactly
        assert nodes[exact_id].value == format_exact(quota)
        posted_total += amount
        rerounded_total += round_half_up(quota, 2)
        moved = moved or round_half_up(quota, 2) != amount
    assert posted_total == 3  # 0.01 fixed + 0.01 + 0.01 targeted: three cents conserved
    assert moved, "re-rounding the raw totals would move at least one cent"
    assert rerounded_total != posted_total or moved
    trace_linkage.check_book(book, bundle, exceptions=NO_EXCEPTIONS)
    replayed = reevaluate(book.trace)
    for key in ("A", "B", "C"):
        version = _version(book, key)
        for column in ("original_allocated_exact", "original_allocated_amount"):
            node_id = version.trace_nodes[column]
            assert replayed[node_id] == nodes[node_id].value


def test_the_assembler_links_by_identity_and_fails_closed_on_a_stale_producer() -> None:
    """The link is the stamped producer identity, never a node chosen by value: on the targeted
    inception state (stages 01 to 05 over one builder) the assembler links exactly the pair the
    state stamped; when the identified producer does not hold the published column it refuses
    (an invariant), it does not search for another node that happens to hold it."""
    from erev_engine import ENGINE_VERSION, _snapshot_links
    from erev_engine.errors import EngineError
    from erev_engine.stages import (
        s01_canonicalize,
        s02_contract_identification,
        s03_pob_builder,
        s04_transaction_price,
        s05_allocation,
    )
    from erev_engine.trace import TraceBuilder

    element = worlds.element("100", keys=["A"])
    bundle = worlds.targeted_world(
        lines=(("A", "PROD-A", "51"), ("B", "PROD-B", "50")), estimates=[element]
    )
    ctx = worlds.context(bundle)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    cb = s01_canonicalize.run(bundle, tb)
    identified = s02_contract_identification.run(ctx, cb, tb)
    priced = s04_transaction_price.run(ctx, s03_pob_builder.run(ctx, identified, tb), tb)
    state = s05_allocation.run(ctx, priced, tb)
    nodes = {node.id: node for node in tb.build(root_measures={}).nodes}
    minor_unit = bundle.currencies[bundle.group.transaction_currency].minor_unit
    a = next(item for item in state.obligations if item.obligation_key == "A")
    b = next(item for item in state.obligations if item.obligation_key == "B")
    assert a.original_allocation_links is not None and b.original_allocation_links is None
    columns = {
        "original_allocated_exact": a.original_allocation.x_exact,
        "original_allocated_amount": a.original_allocation.a_posted,
    }
    links = _snapshot_links(a, state, columns, nodes, minor_unit)
    assert links["original_allocated_exact"] == a.original_allocation_links[0]
    assert links["original_allocated_amount"] == a.original_allocation_links[1]
    plain = _snapshot_links(
        b,
        state,
        {
            "original_allocated_exact": b.original_allocation.x_exact,
            "original_allocated_amount": b.original_allocation.a_posted,
        },
        nodes,
        minor_unit,
    )
    assert plain["original_allocated_exact"] == f"original_allocated_exact:{b.subject_key}:-"
    # the identified producer no longer holds the column: refused, never replaced by another node
    with pytest.raises(EngineError) as refused:
        _snapshot_links(
            a,
            state,
            {**columns, "original_allocated_exact": a.original_allocation.x_exact + 1},
            nodes,
            minor_unit,
        )
    assert refused.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert refused.value.detail["rule"] == "CV-50"
    assert refused.value.detail["node_id"] == a.original_allocation_links[0]
    # Codex 0327's control-flow witness: the CURRENT pair is present and does not hold the column
    # while an OLDER node (the relative version-state node, 101/2 / 5050) matches it exactly — the
    # assembler must refuse the current producer, never walk back to value-matching history.
    relative_exact = Fraction(nodes[f"original_allocated_exact:{a.subject_key}:-"].value)
    relative_amount = nodes[f"original_allocated_amount:{a.subject_key}:-"]
    history = {
        "original_allocated_exact": relative_exact,
        "original_allocated_amount": round(Fraction(relative_amount.value) * 10**minor_unit),
    }
    assert history["original_allocated_exact"] == Fraction(101, 2)
    with pytest.raises(EngineError) as walked_back:
        _snapshot_links(a, state, history, nodes, minor_unit)
    assert walked_back.value.detail["node_id"] == a.original_allocation_links[1]  # amount first
    assert walked_back.value.detail["rule"] == "CV-50"
