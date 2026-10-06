"""Trace coverage of the golden Contract 2 step 09 output (DG-ENG-04; DG-KRN-EXP-01 to 03;
ENGINE_SPEC CV-52, CV-56, Table 0.9-A; DG-PAR-05; BUILD_SPEC END-13).

Every trace node link of the output resolves to a node of the book's trace whose measure is the
linked column, its boundary form ``<column>@<event key>`` or a CV-53 alias (ENGINE_SPEC rev 1.24,
D-97 (8); the rule ``support.trace_linkage`` states) and whose posted value is the column value;
every schedule line and posting line names a node; every formula id is a ``FORMULAS`` key; the
seven CV-56 parity measures are version-state nodes named exactly as their 04 columns. The
``UNLINKED_*`` and ``STALE_CONTRACT_LINKS`` pins record the T-CON-11 / T-CON-08 columns that
carried no link or a stale link when this test was written (measured 2026-09-19: 29 + 5 columns
and two links; OPEN defects T1-F-1 and T1-F-2 returned to the engine owners in
``docs/reviews/loop/sprint/T1.md``); lane ENG-T1F's landing (ENGINE_SPEC rev 1.24) closed them
and the sets are empty since the merge of main 7bf044a5 — a column that loses its link or a link
that goes stale fails this test until its name is pinned again, so the coverage only ratchets
up. Every non-zero balance column is linked under the T-CON-09 mapping (``<m>_txn`` under ``<m>``
in the transaction currency, ``<m>_functional`` under its full name in the functional currency);
every schedule line's node holds its amount in the group currency; every posting line's target
node is in its currency and the matching ``posting_delta`` node holds the signed line amount (debit
positive). The generated-world test proves the same ties on every output the property worlds
produce.
"""

from __future__ import annotations

import functools
from collections.abc import Mapping
from decimal import Decimal
from fractions import Fraction
from typing import Final

from erev_engine import compute
from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.formulas import FORMULAS
from erev_engine.money import EXACT_PLACES, to_fraction
from erev_engine.trace import TraceNode
from hypothesis import given
from support import golden_streams, intent_totals
from support.answer_keys import loader
from support.prop_worlds import WorldSpec, bundle
from support.strategies import world_specs
from support.trace_linkage import ALIASES, FUNCTIONAL, balance_link_columns

VALUE_TYPES: Final = frozenset({"erev.money", "erev.exact"})
# CV-56, Table 0.9-A: the DG-PAR-05 measures, emitted as version-state nodes ``<m>:<ob>:-``.
PARITY_MEASURES: Final = (
    "revenue_cum",
    "remaining_allocation",
    "position_obligation",
    "catch_up_amount",
    "catch_up_cum",
    "netting_reclass_amount",
    "remaining_billing",
)
# Table 0.9-A worked figure: golden Contract 2 POB #1 after step 09 (DG-PAR-07 tolerance).
POB1_REMAINING_ALLOCATION: Final = Fraction("519.6617")
TOLERANCE: Final = Fraction(1, 10_000)
ENCODING_HALF_UNIT: Final = Fraction(1, 2 * 10**EXACT_PLACES)
# T-CON-11 value columns without a ``trace_nodes`` link (T1-F-1): 29 on 2026-09-19 (snapshot inputs,
# stage 05 figures, ``allocated_amount``, ``original_total_contract_price``); none since ENGINE_SPEC
# rev 1.24 — every stored figure links the node that produced it.
UNLINKED_OBLIGATION_COLUMNS: Final = frozenset()  # T1-F-1 closed by ENGINE_SPEC rev 1.24 (D-97 (8))
# T-CON-08 value columns without a link (T1-F-1, contract part): the five sums over the obligation
# versions on 2026-09-19; none since rev 1.24 (a summed column links a sum node of the producing
# stage).
UNLINKED_CONTRACT_COLUMNS: Final = frozenset()  # closed by ENGINE_SPEC rev 1.24 (D-97 (8))
# T-CON-08 columns whose link named the inception build-up node while the column held the last
# reallocating boundary's figure (T1-F-2: ``fixed_consideration`` 1,200.00 against 1,000.00 and
# ``transaction_price`` 1,100.00 against 900.00 on 2026-09-19); none since rev 1.24 — such a column
# links its ``<column>@<event key>`` node. A stale link fails the posted tie below.
STALE_CONTRACT_LINKS: Final = frozenset()  # T1-F-2 closed by ENGINE_SPEC rev 1.24 (D-97 (8))
# R-SGN-01 / L4-3-Q-33: the column is the magnitude of the signed build-up member.
MAGNITUDE_CONTRACT_COLUMNS: Final = frozenset({"vc_constrained_amount"})


@functools.cache
def golden() -> tuple[InputBundle, OutputBundle]:
    stream = golden_streams.stream("Contract 2", "09")
    value = intent_totals.activated(
        stream.input_bundle(preset="LEGACY_PARITY", books=intent_totals.BOOKS)
    )
    return value, compute(value)


def _exact(node: TraceNode) -> Fraction:
    value = to_fraction(node.value)
    return value if node.rounding_residue is None else value + to_fraction(node.rounding_residue)


def _assert_measure(node: TraceNode, column: str, where: object) -> None:
    """CV-50 / CV-53 (ENGINE_SPEC rev 1.24, D-97 (8)): a link names the column's own node, the
    column's boundary form ``<column>@<event key>`` (the last reallocating boundary re-measured the
    column) or a CV-53 alias (``support.trace_linkage.ALIASES``: one value, one node)."""
    ok = (
        node.measure == column
        or node.measure.startswith(f"{column}@")
        or node.measure in ALIASES.get(column, frozenset())
    )
    assert ok, (where, node.id, f"link names measure {node.measure!r}, not {column!r}")


def _assert_exact_tie(node: TraceNode, held: object, subject: tuple[str, str]) -> None:
    """An exact column equals its node's value within the node's 18-place encoding (half a unit)."""
    assert isinstance(held, Fraction | Decimal | int) and not isinstance(held, bool), subject
    assert abs(to_fraction(node.value) - to_fraction(held)) <= ENCODING_HALF_UNIT, subject


def _posted(node: TraceNode, minor_unit: int) -> int:
    scaled = to_fraction(node.value) * 10**minor_unit
    assert scaled.denominator == 1, node.id
    return scaled.numerator


def test_every_output_value_has_a_node() -> None:
    value, output = golden()
    minor_unit = value.currencies[value.group.transaction_currency].minor_unit
    obligation_types = loader.obligation_columns()
    contract_types = loader.contract_version_columns()
    for book in output.books:
        nodes = {node.id: node for node in book.trace.nodes}
        assert (
            sorted({n.formula_id for n in book.trace.nodes if n.formula_id not in FORMULAS}) == []
        )
        version = book.contract_version
        if version is not None:
            for column, node_id in version.trace_nodes.items():
                node = nodes[node_id]
                _assert_measure(node, column, version.subject_key)
                if contract_types.get(column) != "erev.money":
                    continue
                posted = _posted(node, minor_unit)
                held = version.columns[column]
                if column in STALE_CONTRACT_LINKS:
                    assert posted != held, f"T1-F-2 closed for {column}: remove it from the set"
                elif column in MAGNITUDE_CONTRACT_COLUMNS:
                    assert abs(posted) == held, column
                else:
                    assert posted == held, column
            unlinked = {
                column
                for column, held in version.columns.items()
                if held is not None
                and contract_types.get(column) in VALUE_TYPES
                and column not in version.trace_nodes
            }
            assert unlinked == UNLINKED_CONTRACT_COLUMNS
        for item in book.obligation_versions:
            for column, node_id in item.trace_nodes.items():
                node = nodes[node_id]
                _assert_measure(node, column, item.subject_key)
                if obligation_types.get(column) == "erev.money":
                    assert _posted(node, minor_unit) == item.columns[column], (
                        item.subject_key,
                        column,
                    )
                elif obligation_types.get(column) == "erev.exact":
                    _assert_exact_tie(node, item.columns[column], (item.subject_key, column))
            unlinked = {
                column
                for column, held in item.columns.items()
                if held is not None
                and obligation_types.get(column) in VALUE_TYPES
                and column not in item.trace_nodes
            }
            assert unlinked == UNLINKED_OBLIGATION_COLUMNS, item.subject_key
        _assert_output_ties(book, nodes, value.group.transaction_currency, minor_unit)


def _assert_output_ties(
    book: OutputBundle | object, nodes: Mapping[str, TraceNode], currency: str, minor_unit: int
) -> None:
    """Balances, schedule lines and posting lines tie to nodes by value, unit and lineage; the
    generated and golden worlds have one currency, so the functional minor unit is
    ``minor_unit``."""
    from erev_engine.bundle import BookOutput

    assert isinstance(book, BookOutput)
    for balance in book.balances:
        # T-CON-09 links (ENGINE_SPEC rev 1.24, D-97 (8); ``support.trace_linkage``): a
        # ``<m>_txn`` column links under ``<m>`` to a transaction-currency node; a
        # ``<m>_functional`` column links under its full name to a functional-currency node whose
        # measure is the key or its base.
        links = balance_link_columns(balance.columns)
        functional = str(balance.columns["functional_currency"])
        for key, node_id in balance.trace_nodes.items():
            node = nodes[node_id]
            column = links[key]
            base = key[: -len(FUNCTIONAL)] if key.endswith(FUNCTIONAL) else key
            assert node.measure in (key, base), (node_id, key)
            expected_currency = functional if key.endswith(FUNCTIONAL) else currency
            assert node.currency == expected_currency, node_id
            assert _posted(node, minor_unit) == balance.columns[column], node_id
        unlinked_non_zero = {
            column
            for key, column in links.items()
            if balance.columns[column] != 0 and key not in balance.trace_nodes
        }
        assert unlinked_non_zero == set(), (balance.subject_key, balance.period_key)
    for line in book.schedules:
        node = nodes[line.trace_node_id]
        assert node.currency == currency, line.subject_key
        assert _posted(node, minor_unit) == line.amount, (line.subject_key, line.period_key)
    for intent in book.posting_intents:
        for posting_line in intent.lines:
            target = nodes[posting_line.trace_node_id]
            assert target.measure == "posting_target", intent.entry_key
            assert target.currency == posting_line.txn_currency, intent.entry_key
            body, period = target.id[len("posting_target:") :].rsplit(":", 1)
            delta = nodes[f"posting_delta:{body}/{intent.posting_class}:{period}"]
            assert delta.currency == posting_line.txn_currency, intent.entry_key
            signed = (
                posting_line.amount_txn if posting_line.side == "D" else -posting_line.amount_txn
            )
            assert _posted(delta, minor_unit) == signed, (intent.entry_key, posting_line.line_key)


def test_cv_56_parity_measures() -> None:
    value, output = golden()
    book = next(item for item in output.books if item.book_code == "ASC606")
    nodes = {node.id: node for node in book.trace.nodes}
    assert book.obligation_versions
    for item in book.obligation_versions:
        for measure in PARITY_MEASURES:
            node_id = item.trace_nodes[measure]
            assert node_id == f"{measure}:{item.subject_key}:-", (item.subject_key, measure)
            node = nodes[node_id]
            assert node.measure == measure and node.currency == "USD"
            assert node.rounding_residue is not None  # a posted node with its exact residue
    pob1 = next(
        item for item in book.obligation_versions if item.columns["obligation_key"] == "POB #1"
    )
    remaining = _exact(nodes[pob1.trace_nodes["remaining_allocation"]])
    assert abs(remaining - POB1_REMAINING_ALLOCATION) <= TOLERANCE
    assert pob1.columns["remaining_allocation"] == 51966
    # Table 0.9-A: exact revenue_cum + exact remaining_allocation = x_k, the exact allocation.
    revenue = _exact(nodes[pob1.trace_nodes["revenue_cum"]])
    allocated = pob1.columns["allocated_exact"]
    assert isinstance(allocated, Fraction)
    assert abs(revenue + remaining - allocated) <= Fraction(1, 10**15)
    assert abs(allocated - Fraction("573.2026")) <= TOLERANCE


@given(spec=world_specs())
def test_trace_links_tie_on_generated_worlds(spec: WorldSpec) -> None:
    """Every output link of a generated world resolves to a node whose measure is the column and
    whose posted value is the column value; balances, schedule lines and posting lines tie by
    value, unit and lineage (DG-KRN-EXP-01 to 03)."""
    output = compute(bundle(spec, books=("ASC606", "IFRS15")))
    obligation_types = loader.obligation_columns()
    contract_types = loader.contract_version_columns()
    for book in output.books:
        nodes = {node.id: node for node in book.trace.nodes}
        version = book.contract_version
        assert version is not None
        for column, node_id in version.trace_nodes.items():
            node = nodes[node_id]
            _assert_measure(node, column, version.subject_key)
            if contract_types.get(column) == "erev.money":
                posted = _posted(node, spec.minor_unit)
                held = version.columns[column]
                assert (abs(posted) if column in MAGNITUDE_CONTRACT_COLUMNS else posted) == held, (
                    column
                )
        for item in book.obligation_versions:
            for column, node_id in item.trace_nodes.items():
                node = nodes[node_id]
                _assert_measure(node, column, item.subject_key)
                if obligation_types.get(column) == "erev.money":
                    assert _posted(node, spec.minor_unit) == item.columns[column], (
                        item.subject_key,
                        column,
                    )
                elif obligation_types.get(column) == "erev.exact":
                    _assert_exact_tie(node, item.columns[column], (item.subject_key, column))
        _assert_output_ties(book, nodes, spec.currency, spec.minor_unit)
