"""PROP:P8 replay determinism (dev-guide §9.7 P8, DG-ENG-02; ENGINE_SPEC CV-26; ENGINE_SPEC_B
S09-INV-12; BUILD_SPEC END-13).

Part (a): computing one bundle twice gives byte-identical canonical output, so an identical
``OutputBundle.sha256()``; the golden Contract 2 step 09 bundle hashes identically in another
process. Part (b): a shuffled arrival of commuting events, an interleaving of the contract streams
of a group that keeps each stream's own order, gives identical obligation versions, balances,
schedules, posting intents, diagnostics and trace values outside the stage 12 layer lineage, whose
per-period totals agree. The output hash is not compared in part (b): it covers ``input_sha256``,
which encodes the arrival order, and the layer keys of same-date layers carry the arriving event
(dev-guide §9.7 rev 1.10; T1-Q-1).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from fractions import Fraction
from pathlib import Path
from typing import Final

import pytest
from erev_engine import compute
from erev_engine.bundle import FxLayerMovementOut, InputBundle, OutputBundle
from erev_engine.canonical import canonical_bytes
from erev_engine.money import to_fraction
from erev_engine.trace import Trace, TraceNode
from hypothesis import assume, given
from hypothesis import strategies as st
from support import golden_streams, intent_totals
from support.prop_worlds import (
    LineSpec,
    MeasureSpec,
    WorldSpec,
    arrival_labels,
    bundle,
    interleaved,
)
from support.strategies import world_specs

pytestmark = pytest.mark.property

REPO_ROOT: Final = Path(__file__).resolve().parents[3]
# Stage 12 layer lineage: same-date layers are keyed by the arriving event (S12; L2-5-Q-12).
LINEAGE: Final = frozenset(
    {"fx_layer_created", "fx_layer_consumed", "fx_layer_remeasured", "fx_layer_settled"}
)
GOLDEN_SCRIPT: Final = (
    "from erev_engine import compute\n"
    "from support import golden_streams, intent_totals\n"
    "stream = golden_streams.stream('Contract 2', '09')\n"
    "value = intent_totals.activated("
    "stream.input_bundle(preset='LEGACY_PARITY', books=intent_totals.BOOKS))\n"
    "print(compute(value).sha256())\n"
)


def golden_contract2_step09() -> InputBundle:
    """The activated golden Contract 2 stream through step 09 under ``LEGACY_PARITY`` with the
    books ASC606 and LEGACY (as ``support.intent_totals.golden`` builds it)."""
    stream = golden_streams.stream("Contract 2", "09")
    return intent_totals.activated(
        stream.input_bundle(preset="LEGACY_PARITY", books=intent_totals.BOOKS)
    )


@given(spec=world_specs())
def test_p08_recompute_is_byte_identical(spec: WorldSpec) -> None:
    value = bundle(spec, books=("ASC606", "IFRS15"))
    first, second = compute(value), compute(value)
    assert canonical_bytes(first) == canonical_bytes(second)
    assert first.sha256() == second.sha256()
    assert first.input_sha256 == value.sha256() == second.input_sha256
    for one, other in zip(first.books, second.books, strict=True):
        assert canonical_bytes(one.trace) == canonical_bytes(other.trace)
        assert one.trace.sha256() == other.trace.sha256()
        assert one.posting_intents == other.posting_intents


def test_p08_golden_contract2_step09_hash_across_processes() -> None:
    """CV-26: the same hash across runs and processes (``backend/.venv/bin/python -c …``)."""
    value = golden_contract2_step09()
    in_process = compute(value)
    assert in_process.sha256() == compute(value).sha256()
    env = {**os.environ, "PYTHONPATH": "backend/tests", "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(  # the interpreter running this test, over a fixed script
        [sys.executable, "-c", GOLDEN_SCRIPT],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=600,
    )
    assert result.stdout.strip() == in_process.sha256()


def _period(node_id: str) -> str:
    return node_id.rsplit(":", 1)[1]


def _lineage_totals(nodes: Iterable[TraceNode]) -> dict[tuple[str, str], Fraction]:
    totals: dict[tuple[str, str], Fraction] = Counter()
    for node in nodes:
        totals[(node.measure, _period(node.id))] += to_fraction(node.value)
    return {key: value for key, value in totals.items() if value}


def _movement_totals(movements: Iterable[FxLayerMovementOut]) -> dict[tuple[object, ...], int]:
    totals: dict[tuple[object, ...], int] = Counter()
    for movement in movements:
        columns = movement.columns
        key = tuple(
            columns[name]
            for name in (
                "book_code",
                "entity",
                "movement_kind",
                "balance_role",
                "effective_date",
                "txn_currency",
                "functional_currency",
                "reason",
            )
        )
        totals[(*key, "txn")] += int(str(columns["amount_txn"]))
        totals[(*key, "functional")] += int(str(columns["amount_functional"]))
    return {key: value for key, value in totals.items() if value}


def _assert_traces_agree(left: Trace, right: Trace) -> None:
    """Every node outside the layer lineage is identical (inputs and params included unless they
    cite a lineage node); the lineage agrees in its per-measure, per-period totals."""
    one: Mapping[str, TraceNode] = {node.id: node for node in left.nodes}
    other: Mapping[str, TraceNode] = {node.id: node for node in right.nodes}
    lineage_one = {node_id for node_id, node in one.items() if node.measure in LINEAGE}
    lineage_other = {node_id for node_id, node in other.items() if node.measure in LINEAGE}
    assert set(one) - lineage_one == set(other) - lineage_other
    for node_id in sorted(set(one) - lineage_one):
        x, y = one[node_id], other[node_id]
        assert (x.measure, x.value, x.currency, x.formula_id, x.rounding_residue) == (
            y.measure,
            y.value,
            y.currency,
            y.formula_id,
            y.rounding_residue,
        ), node_id
        cites_lineage = any(isinstance(item, str) and item in lineage_one for item in x.inputs)
        if not cites_lineage:
            assert (x.inputs, x.params, x.narrative_key) == (y.inputs, y.params, y.narrative_key)
    assert _lineage_totals(one[i] for i in lineage_one) == _lineage_totals(
        other[i] for i in lineage_other
    )


def _assert_only_arrival_differs(base: InputBundle, other: InputBundle) -> None:
    """The interleaving changed the record sequence of at least one event and nothing else: the
    same event keys with the same payloads, effective dates and stream versions."""
    one = {event.event_key: event for event in base.events}
    two = {event.event_key: event for event in other.events}
    assert set(one) == set(two)
    for key, x in one.items():
        y = two[key]
        assert (x.payload, x.effective_date, x.stream_version, x.event_type) == (
            y.payload,
            y.effective_date,
            y.stream_version,
            y.event_type,
        ), key
    assert any(one[key].record_seq != two[key].record_seq for key in one)


def _assert_commuting_equivalent(base: OutputBundle, other: OutputBundle) -> None:
    assert other.engine_version == base.engine_version
    assert other.diagnostics == base.diagnostics
    for one, two in zip(base.books, other.books, strict=True):
        assert one.book_code == two.book_code
        assert one.contract_version == two.contract_version
        assert one.status_in_book == two.status_in_book
        assert one.obligation_versions == two.obligation_versions
        assert one.balances == two.balances
        assert one.schedules == two.schedules
        assert one.cost_asset_versions == two.cost_asset_versions
        assert one.loss_provision_versions == two.loss_provision_versions
        assert one.posting_intents == two.posting_intents
        assert one.proposals == two.proposals
        assert one.time_triggers == two.time_triggers
        assert one.line_rates == two.line_rates
        assert _movement_totals(one.fx_layer_movements) == _movement_totals(two.fx_layer_movements)
        _assert_traces_agree(one.trace, two.trace)


@given(spec=world_specs(), data=st.data())
def test_p08_shuffled_commuting_arrivals(spec: WorldSpec, data: st.DataObject) -> None:
    labels = arrival_labels(spec)
    order = tuple(data.draw(st.permutations(labels)))
    assume(order != labels)  # a one-contract or empty stream admits only the identity
    original, shuffled = bundle(spec), bundle(interleaved(spec, order))
    _assert_only_arrival_differs(original, shuffled)
    _assert_commuting_equivalent(compute(original), compute(shuffled))


def test_p08_reversed_same_date_arrivals_control() -> None:
    """Two contracts, each billing and delivering on the same two days; the second stream arrives
    first. Only record sequences differ between the bundles; every figure agrees."""
    spec = WorldSpec(
        currency="USD",
        contracts=(
            ("K-1", (LineSpec("POB-01", "PIT", 500000, 300000, 2, 0, 0),)),
            ("K-2", (LineSpec("POB-01", "MONTHLY_EVEN", 3600000, 3000000, 1, 0, 12),)),
        ),
        measures=(
            MeasureSpec("K-1", "POB-01", "DELIVERY", 40, 1),
            MeasureSpec("K-2", "POB-01", "BILLING", 40, 300000),
            MeasureSpec("K-1", "POB-01", "BILLING", 40, 100000),
            MeasureSpec("K-2", "POB-01", "BILLING", 120, 300000),
            MeasureSpec("K-1", "POB-01", "DELIVERY", 120, 1),
        ),
    )
    reversed_order = ("K-2", "K-1", "K-2", "K-1", "K-1")
    original, shuffled = bundle(spec), bundle(interleaved(spec, reversed_order))
    _assert_only_arrival_differs(original, shuffled)
    _assert_commuting_equivalent(compute(original), compute(shuffled))
