"""LMG-3 ``exact(m)`` extraction for the migration reconciliation (BUILD_SPEC LMG-3; dev-guide
DG-PAR-05, DG-KRN-EXP-03; SCREENS_B §5.6.7 RPT-41 "Value representation", rev 1.13; D-98 89): the
reconcile reads, per T-MIG-03 measure, the same exact source the parity reader and the explain
service read — RAW for ``erev.exact`` columns, ``value + rounding_residue`` of the bound trace node
for ``erev.money`` columns, the stored cents for ``billed_cum`` — and never re-scales or divides an
encoded value. Acceptance along Codex's ``PRODUCTION-LMG3-EXTRACTION-ACCEPTANCE-0cb36c14.md``: every
mapping rule on independently supplied producing values, a changed producing input changes its
measure (and only it), signed position / reclass, unchanged billing units, VC count versus row
population, the representation boundary (stored decimal text, never an in-memory ``Fraction``).
Fakes only; no database.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace
from typing import Any

import pytest
from erev_api.domain.migration import exact_values, reconciliation

E18 = "0.000000000000000000"


def _node(value: str, residue: str | None = None) -> Any:
    return SimpleNamespace(value=value, rounding_residue=residue)


def _version(
    contract: str = "Contract 1",
    obligation: str = "POB #1",
    kind: str = "STANDARD",
    **columns: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "contract_external_id": contract,
        "obligation_key": obligation,
        "obligation_kind": kind,
        "original_allocated_exact": Decimal("322.101090188300000000"),
        "remaining_quantity": Decimal("3.000000000000000000"),
        "revenue_cum": Decimal("123.45"),
        "remaining_allocation": Decimal("198.65"),
        "billed_cum": Decimal("300.00"),
        "position_obligation": Decimal("176.55"),
        "netting_reclass_amount": Decimal("0.00"),
        "trace_nodes": {
            "revenue_cum": "n-rev",
            "remaining_allocation": "n-rem",
            "position_obligation": "n-pos",
            "netting_reclass_amount": "n-rec",
        },
    }
    row.update(columns)
    return row


NODES: dict[str, Any] = {
    # posted cents + the exact residue (DG-KRN-EXP-03): exact revenue = 123.4512345678
    "n-rev": _node("123.45", "0.001234567800000000"),
    "n-rem": _node("198.65", "-0.001234567800000000"),
    "n-pos": _node("176.55", "-0.001234567800000000"),
    "n-rec": _node("0.00", None),
}


def test_measure_sources_state_raw_versus_encoded() -> None:
    # The bound source of every T-MIG-03 measure and how it is read (SCREENS_B rev 1.13).
    sources = exact_values.MEASURE_SOURCES
    assert set(sources) == set(reconciliation.OBLIGATION_MEASURES)
    assert sources["ORIGINAL_ALLOCATION"] == (("original_allocated_exact",), "RAW")
    assert sources["REMAINING_QTY"] == (("remaining_quantity",), "RAW")
    assert sources["REVENUE_CUM"] == (("revenue_cum",), "NODE")
    assert sources["ALLOCATION"] == (("revenue_cum", "remaining_allocation"), "NODE")
    assert sources["NET_POSITION"] == (("position_obligation",), "NODE")
    assert sources["RECLASS"] == (("netting_reclass_amount",), "NODE")
    assert sources["BILLED_CUM"] == (("billed_cum",), "STORED")


def test_exact_reads_raw_columns_and_trace_nodes_without_rescaling() -> None:
    row = _version()
    lookup = NODES.get
    # RAW: the erev.exact column as stored (18 places), exactly
    assert exact_values.exact_measure(row, "ORIGINAL_ALLOCATION", lookup) == Fraction(
        Decimal("322.1010901883")
    )
    assert exact_values.exact_measure(row, "REMAINING_QTY", lookup) == Fraction(3)
    # NODE: value + rounding_residue of the bound node, never the posted column alone
    assert exact_values.exact_measure(row, "REVENUE_CUM", lookup) == Fraction(
        Decimal("123.4512345678")
    )
    assert exact_values.exact_measure(row, "ALLOCATION", lookup) == Fraction(
        Decimal("123.4512345678")
    ) + Fraction(Decimal("198.6487654322"))
    assert exact_values.exact_measure(row, "NET_POSITION", lookup) == Fraction(
        Decimal("176.5487654322")
    )
    assert exact_values.exact_measure(row, "RECLASS", lookup) == 0
    # STORED: billed_cum is a cents fact on both sides — the column, not a node
    assert exact_values.exact_measure(row, "BILLED_CUM", lookup) == Fraction(300)
    # the node's encoded text is taken as is: no division, no quantisation
    assert exact_values.node_exact(_node("1.000000000000000001")) == Fraction(
        Decimal("1.000000000000000001")
    )


def test_missing_or_unbound_node_fails_closed() -> None:
    row = _version()
    with pytest.raises(exact_values.ExactSourceError, match="n-rev"):
        exact_values.exact_measure(row, "REVENUE_CUM", lambda _id: None)
    unbound = _version(trace_nodes={})
    with pytest.raises(exact_values.ExactSourceError, match="revenue_cum"):
        exact_values.exact_measure(unbound, "REVENUE_CUM", NODES.get)
    with pytest.raises(exact_values.ExactSourceError, match="original_allocated_exact"):
        exact_values.exact_measure(
            _version(original_allocated_exact=None), "ORIGINAL_ALLOCATION", NODES.get
        )


def test_erev_values_have_the_legacy_values_shape() -> None:
    # Two obligations and a VC line of one contract: per-obligation measures and the contract
    # sums, POB_COUNT excluding VC_LINE, TRANSACTION_PRICE = Σ exact(revenue_cum) +
    # exact(remaining_allocation) — the same keys reconciliation.legacy_values produces.
    rows = [
        _version(),
        _version(
            obligation="POB #2",
            revenue_cum=Decimal("10.00"),
            trace_nodes={
                "revenue_cum": "n-ten",
                "remaining_allocation": "n-rec",
                "position_obligation": "n-rec",
                "netting_reclass_amount": "n-rec",
            },
        ),
        _version(
            obligation="VC-1",
            kind="VC_LINE",
            revenue_cum=Decimal("-5.00"),
            trace_nodes={
                "revenue_cum": "n-neg",
                "remaining_allocation": "n-rec",
                "position_obligation": "n-rec",
                "netting_reclass_amount": "n-rec",
            },
        ),
    ]
    nodes = {
        **NODES,
        "n-ten": _node("10.00", "0.000000000000000000"),
        "n-neg": _node("-5.00", None),
    }
    values = exact_values.erev_values(rows, lambda _row: nodes.get)
    assert values[("Contract 1", None, "POB_COUNT")] == 2
    assert values[("Contract 1", "POB #1", "ORIGINAL_ALLOCATION")] == Fraction(
        Decimal("322.1010901883")
    )
    assert values[("Contract 1", "POB #2", "REVENUE_CUM")] == 10
    assert values[("Contract 1", "VC-1", "REVENUE_CUM")] == -5
    revenue = Fraction(Decimal("123.4512345678")) + 10 - 5
    assert values[("Contract 1", None, "REVENUE_CUM")] == revenue
    assert values[("Contract 1", None, "TRANSACTION_PRICE")] == revenue + Fraction(
        Decimal("198.6487654322")
    )
    assert values[("Contract 1", None, "BILLED_CUM")] == 900
    assert set(k[2] for k in values if k[1] is None) == set(reconciliation.CONTRACT_MEASURES)
    assert set(k[2] for k in values if k[1] == "POB #1") == set(reconciliation.OBLIGATION_MEASURES)
    # keys sort like legacy_values (contract, obligation or "", measure)
    assert list(values) == sorted(values, key=lambda k: (k[0], k[1] or "", k[2]))


def _delta(
    before: dict[reconciliation.LineKey, Fraction], after: dict[reconciliation.LineKey, Fraction]
) -> dict[tuple[str | None, str], Fraction]:
    """The measures whose value changed, keyed (obligation key or None, measure)."""
    assert set(before) == set(after)
    return {
        (key[1], key[2]): after[key] - before[key] for key in before if after[key] != before[key]
    }


def _values(row: dict[str, Any], nodes: dict[str, Any]) -> dict[reconciliation.LineKey, Fraction]:
    return exact_values.erev_values([row], lambda _row: nodes.get)


def test_changing_a_producing_input_changes_its_measure_and_only_its_measure() -> None:
    # Acceptance: independent producing inputs; each moves exactly the measure(s) it produces
    # (and the contract sums over them). A residue-only change moves a NODE measure — the residue
    # is read; a change of the posted column alone moves nothing — the posted cents are not the
    # source of a NODE measure.
    baseline = _values(_version(), NODES)
    one = Fraction(1)
    cases: list[
        tuple[str, dict[str, Any], dict[str, Any], dict[tuple[str | None, str], Fraction]]
    ] = [
        (
            "original_allocated_exact + 1 → ORIGINAL_ALLOCATION only (not ALLOCATION)",
            _version(original_allocated_exact=Decimal("323.101090188300000000")),
            NODES,
            {("POB #1", "ORIGINAL_ALLOCATION"): one},
        ),
        (
            "remaining_quantity + 1 → REMAINING_QTY only",
            _version(remaining_quantity=Decimal("4.000000000000000000")),
            NODES,
            {("POB #1", "REMAINING_QTY"): one},
        ),
        (
            "billed_cum + 1.00 (cents) → BILLED_CUM at both grains, units unchanged",
            _version(billed_cum=Decimal("301.00")),
            NODES,
            {("POB #1", "BILLED_CUM"): one, (None, "BILLED_CUM"): one},
        ),
        (
            "revenue_cum node + 1 → REVENUE_CUM, ALLOCATION and the contract sums over them",
            _version(),
            {**NODES, "n-rev": _node("124.45", "0.001234567800000000")},
            {
                ("POB #1", "REVENUE_CUM"): one,
                ("POB #1", "ALLOCATION"): one,
                (None, "REVENUE_CUM"): one,
                (None, "TRANSACTION_PRICE"): one,
            },
        ),
        (
            "remaining_allocation node + 1 → ALLOCATION and TRANSACTION_PRICE (not REVENUE_CUM)",
            _version(),
            {**NODES, "n-rem": _node("199.65", "-0.001234567800000000")},
            {("POB #1", "ALLOCATION"): one, (None, "TRANSACTION_PRICE"): one},
        ),
        (
            "position node residue-only + 1 → NET_POSITION (the residue is read)",
            _version(),
            {**NODES, "n-pos": _node("176.55", "0.998765432200000000")},
            {("POB #1", "NET_POSITION"): one, (None, "NET_POSITION"): one},
        ),
        (
            "netting_reclass_amount node −1.00 → RECLASS, sign preserved",
            _version(),
            {**NODES, "n-rec": _node("-1.00", None)},
            {("POB #1", "RECLASS"): -one, (None, "RECLASS"): -one},
        ),
        (
            "posted revenue_cum column alone → nothing (not a source of any measure)",
            _version(revenue_cum=Decimal("999.99")),
            NODES,
            {},
        ),
    ]
    for what, row, nodes, expected in cases:
        assert _delta(baseline, _values(row, nodes)) == expected, what
    # VC count versus row population: a VC line leaves POB_COUNT and keeps every monetary row
    vc = _delta(baseline, _values(_version(kind="VC_LINE"), NODES))
    assert vc == {(None, "POB_COUNT"): -one}


def test_signed_position_and_reclass_are_read_as_signed_exacts() -> None:
    nodes = {
        **NODES,
        "n-pos": _node("-176.55", "-0.001234567800000000"),
        "n-rec": _node("-12.34", "0.000000000000000001"),
    }
    assert exact_values.exact_measure(_version(), "NET_POSITION", nodes.get) == Fraction(
        Decimal("-176.5512345678")
    )
    assert exact_values.exact_measure(_version(), "RECLASS", nodes.get) == Fraction(
        Decimal("-12.339999999999999999")
    )


def test_in_memory_fractions_are_refused_at_the_representation_boundary() -> None:
    # The extractor consumes the stored representation (the erev.exact column's decimal, the
    # trace node's format_money / format_exact text). A raw in-memory Fraction — terminating or
    # not — is not that representation: refused, never rounded, never floated.
    for raw in (Fraction(1, 3), Fraction(1, 4)):
        with pytest.raises(exact_values.ExactSourceError, match="not an exact decimal"):
            exact_values.exact_measure(
                _version(original_allocated_exact=raw), "ORIGINAL_ALLOCATION", NODES.get
            )
        with pytest.raises(exact_values.ExactSourceError, match="not an exact decimal"):
            exact_values.node_exact(_node(raw))  # type: ignore[arg-type]
    # finite stored operands sum to a finite decimal the T-MIG-03 writer accepts as it is
    allocation = exact_values.exact_measure(_version(), "ALLOCATION", NODES.get)
    assert reconciliation.exact_decimal_text(allocation) == "322.1"
