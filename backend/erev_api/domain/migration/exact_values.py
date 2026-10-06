"""``exact(m)`` extraction for the migration reconciliation (BUILD_SPEC LMG-3
``MIGRATION_RECONCILE``; 04 T-MIG-03; dev-guide §9.6 DG-PAR-05, §5 DG-KRN-EXP-03; SCREENS_B
§5.6.7 RPT-41 "Value representation", rev 1.13; D-98 89).

The reconcile obtains, for each T-MIG-03 measure of a legacy obligation, the EXACT eRev value from
the measure's bound producing source on the ``obligation_version`` the batch's bound comparison
population names (``population.py``: the captured computation's own contract / version / trace
identities — never a latest live version) — the same source the parity reader
(``tests/support/parity/values.py``) and the explain service read, so the report shows the value
the engine produced, never a re-derived one:

- **RAW** — an ``erev.exact`` column read as stored: ``ORIGINAL_ALLOCATION`` ←
  ``original_allocated_exact``; ``REMAINING_QTY`` ← ``remaining_quantity``. The column holds the
  exact quota at the type's 18-place scale (TY-02); ``Fraction(Decimal(stored))`` is exact.
- **NODE** — an ``erev.money`` column whose posted cents are rounded, read as the bound
  calc-trace node's ``value + rounding_residue`` (DG-KRN-EXP-03: both are ``format_money`` /
  ``format_exact`` text; their sum is the exact amount): ``REVENUE_CUM`` ← ``revenue_cum``;
  ``ALLOCATION`` ← ``revenue_cum`` + ``remaining_allocation``; ``NET_POSITION`` ←
  ``position_obligation``; ``RECLASS`` ← ``netting_reclass_amount``. The node id comes from
  ``obligation_version.trace_nodes`` (measure name → node id) and the node from the contract
  version's calc trace.
- **STORED** — ``BILLED_CUM`` ← ``billed_cum``, a billing fact carried in cents on both sides (the
  parity reader's ``stored=True``).

Encoded text is consumed as text → ``Decimal`` → ``Fraction``: nothing here divides, multiplies,
quantises or re-scales an encoded value (the D-98 117 class of defect — a producer dividing encoded
nodes where the rule wants raw operands — cannot arise in a reader that only sums exact fractions).
The operands are the STORED representation — the exact column's decimal (its normal Q18 encoding
by ``ExactType``), the node's ``format_money`` / ``format_exact`` text; RAW therefore means "the
persisted exact column as stored", not an unrecorded pre-encoding rational, and NODE recovers the
represented exact measure. An in-memory ``Fraction`` (terminating or not) is not that
representation and is refused (``ExactSourceError``), never rounded, floated or widened; the
finite operands sum to finite decimals the T-MIG-03 writer (``exact_decimal_text``) accepts.
Contract-level measures are the sums the legacy side also uses (``reconciliation.legacy_values``):
``TRANSACTION_PRICE`` = Σ (exact revenue + exact remaining allocation), ``REVENUE_CUM`` /
``BILLED_CUM`` / ``NET_POSITION`` / ``RECLASS`` = Σ, ``POB_COUNT`` = the obligations that are not
``VC_LINE``. A missing column, an unbound measure or a node the trace does not hold fails closed
(``ExactSourceError``); the job maps it to a problem — no silent zero.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any, Final, Literal, Protocol

from erev_api.domain.migration.reconciliation import (
    CONTRACT_MEASURES,
    OBLIGATION_MEASURES,
    LineKey,
)

__all__ = [
    "MEASURE_SOURCES",
    "VC_LINE",
    "ExactSourceError",
    "NodeLookup",
    "NodesForRow",
    "TraceNodeLike",
    "erev_values",
    "exact_column",
    "exact_measure",
    "node_exact",
]

type ReadMode = Literal["RAW", "NODE", "STORED"]
VC_LINE: Final = "VC_LINE"  # E-18: a legacy VC row is not an obligation for POB_COUNT (POL-213)
# T-MIG-03 obligation measure → (the obligation_version columns summed, how each is read).
MEASURE_SOURCES: Final[Mapping[str, tuple[tuple[str, ...], ReadMode]]] = {
    "ORIGINAL_ALLOCATION": (("original_allocated_exact",), "RAW"),
    "ALLOCATION": (("revenue_cum", "remaining_allocation"), "NODE"),
    "REVENUE_CUM": (("revenue_cum",), "NODE"),
    "BILLED_CUM": (("billed_cum",), "STORED"),
    "NET_POSITION": (("position_obligation",), "NODE"),
    "RECLASS": (("netting_reclass_amount",), "NODE"),
    "REMAINING_QTY": (("remaining_quantity",), "RAW"),
}
# Contract-level sums over the obligations' exact values (dev-guide §9.6 ``contract_position``).
_CONTRACT_SUMS: Final[Mapping[str, str]] = {
    "TRANSACTION_PRICE": "ALLOCATION",
    "REVENUE_CUM": "REVENUE_CUM",
    "BILLED_CUM": "BILLED_CUM",
    "NET_POSITION": "NET_POSITION",
    "RECLASS": "RECLASS",
}
_ZERO: Final = Fraction(0)


class ExactSourceError(ValueError):
    """The bound exact source of a measure is missing: an absent column value, an unbound measure
    in ``trace_nodes`` or a node the calc trace does not hold. The reconcile fails closed."""


class TraceNodeLike(Protocol):
    @property
    def value(self) -> str: ...

    @property
    def rounding_residue(self) -> str | None: ...


NodeLookup = Callable[[str], TraceNodeLike | None]


def _fraction(text: object, what: str) -> Fraction:
    if text is None:
        raise ExactSourceError(f"{what} is NULL")
    try:
        return Fraction(Decimal(str(text)))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ExactSourceError(f"{what} is not an exact decimal: {text!r}") from error


def node_exact(node: TraceNodeLike) -> Fraction:
    """DG-KRN-EXP-03: the exact value of a trace node is ``value + rounding_residue`` — the encoded
    text read as it is, never re-scaled."""
    value = _fraction(node.value, "trace node value")
    if node.rounding_residue is not None:
        value += _fraction(node.rounding_residue, "trace node rounding_residue")
    return value


def exact_column(
    row: Mapping[str, Any], column: str, mode: ReadMode, nodes: NodeLookup
) -> Fraction:
    """``exact(m)`` of one ``obligation_version`` column under its read mode."""
    if mode in ("RAW", "STORED"):
        return _fraction(row.get(column), f"obligation_version.{column}")
    names: Mapping[str, Any] = row.get("trace_nodes") or {}
    node_id = names.get(column)
    if not isinstance(node_id, str):
        raise ExactSourceError(
            f"obligation_version.trace_nodes binds no node to the erev.money column {column}"
        )
    node = nodes(node_id)
    if node is None:
        raise ExactSourceError(f"trace node {node_id} of {column} is not in the calc trace")
    return node_exact(node)


def exact_measure(row: Mapping[str, Any], measure: str, nodes: NodeLookup) -> Fraction:
    """The exact eRev value of one T-MIG-03 obligation measure of an ``obligation_version`` row
    (columns and ``trace_nodes`` as stored; ``nodes`` resolves a node id in the version's trace)."""
    try:
        columns, mode = MEASURE_SOURCES[measure]
    except KeyError:
        raise ExactSourceError(f"{measure} is not an obligation measure") from None
    return sum((exact_column(row, column, mode, nodes) for column in columns), _ZERO)


NodesForRow = Callable[[Mapping[str, Any]], NodeLookup]


def erev_values(
    rows: Iterable[Mapping[str, Any]], nodes_for: NodesForRow
) -> dict[LineKey, Fraction]:
    """The eRev side of the reconciliation in the shape of ``reconciliation.legacy_values``: every
    obligation measure per (contract external id, obligation key) and the contract sums, over the
    latest obligation versions ``rows`` (each carrying ``contract_external_id``, ``obligation_key``,
    ``obligation_kind``, the measure columns and ``trace_nodes``); ``nodes_for(row)`` is the node
    lookup of the row's own contract version (node ids repeat across traces)."""
    values: dict[LineKey, Fraction] = {}
    totals: dict[tuple[str, str], Fraction] = {}
    for row in rows:
        contract, obligation = str(row["contract_external_id"]), str(row["obligation_key"])
        nodes = nodes_for(row)
        per_row: dict[str, Fraction] = {
            str(name): exact_measure(row, name, nodes) for name in OBLIGATION_MEASURES
        }
        for name, amount in per_row.items():
            values[(contract, obligation, name)] = amount
        for total, source in _CONTRACT_SUMS.items():
            totals[(contract, total)] = totals.get((contract, total), _ZERO) + per_row[source]
        if row.get("obligation_kind") != VC_LINE:
            totals[(contract, "POB_COUNT")] = totals.get((contract, "POB_COUNT"), _ZERO) + 1
        else:
            totals.setdefault((contract, "POB_COUNT"), _ZERO)
    for (contract_id, total_name), amount in totals.items():
        values[(contract_id, None, total_name)] = amount
    for contract_id in {key[0] for key in values}:
        for contract_measure in CONTRACT_MEASURES:
            values.setdefault((contract_id, None, str(contract_measure)), _ZERO)
    ordered = sorted(values.items(), key=lambda item: (item[0][0], item[0][1] or "", item[0][2]))
    return dict(ordered)
