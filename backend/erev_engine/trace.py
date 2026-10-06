"""Calculation trace (dev-guide §5.16 DG-KRN-EXP-01 to 04; ENGINE_SPEC CV-50 to CV-54).

Every engine output value has a node emitted by the code that computed it. Node ids are
``<measure>:<subject key>:<period key or '-'>``. A posted node holds ``format_money`` and
``rounding_residue = format_exact(exact − posted)``; an exact node holds ``format_exact`` and no
residue. ``reevaluate`` recomputes every node through ``FORMULAS`` (PROP:P14). Standard library
only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Final, Literal, get_args

from erev_engine.canonical import sha256_hex
from erev_engine.errors import EngineError
from erev_engine.formulas import EXACT_INPUT_FORMULAS, FORMULA_ID, FORMULAS, minor_unit_of
from erev_engine.money import format_exact, format_money, to_fraction

# CV-50 rev 1.29 (D-98 candidates 123 / 124): a snapshot column's producer link may name, instead
# of a node id, a contract-permitted ABSENCE of the producer — a STABLE identifier: the fixed prefix
# and a closed enumeration of reasons declared here once (the explanation lives in ENGINE_SPEC,
# never in the stored marker). Each reason is admitted only for its column, from its identified
# constructor state, and the assembler asserts it BY IDENTITY — never by prefix; a missing REQUIRED
# producer keeps refusing.
ABSENT_PREFIX: Final = "absent:"
ABSENT_ZERO_TOTAL: Final = "absent:zero-total"  # legacy PROSPECTIVE Σw = 0 (DEV-054): no ratio
ABSENT_NO_RESOLUTION: Final = "absent:no-ssp-resolution"  # a LEGACY-VC created line: selected 0
ABSENCE_COLUMNS: Final[Mapping[str, str]] = MappingProxyType(
    {"allocation_weight": ABSENT_ZERO_TOTAL, "original_ssp_selected": ABSENT_NO_RESOLUTION}
)


def admitted_absence(column: str, link: object) -> str | None:
    """The contract-permitted absence ``link`` names for ``column`` (CV-50 rev 1.29), or None —
    by identity against ``ABSENCE_COLUMNS`` (a node id, an unknown or malformed reason, or a
    reason stamped on another column — a REQUIRED producer's column included — is None)."""
    return link if isinstance(link, str) and ABSENCE_COLUMNS.get(column) == link else None


AbsenceState = Literal["absent", "malformed"]


def absence_state(column: str, link: object, value: object) -> AbsenceState | None:
    """The ONE shared recognition of a stamped absence (CV-50 rev 1.29) for the assembler, the
    explain service and the linkage checker — column AND value aware: ``"absent"`` when ``link``
    is the reason admitted for ``column`` (``admitted_absence``) and the column publishes the
    contract display 0; ``"malformed"`` when ``link`` carries the ``absent:`` prefix but is an
    unknown reason, a reason stamped on another column (a REQUIRED producer's column included) or
    an admitted reason over a non-zero / NULL value — a state the assembler refuses and no
    consumer may read as a legitimate absence; None for anything else (a node id, unbound)."""
    if not isinstance(link, str) or not link.startswith(ABSENT_PREFIX):
        return None
    if admitted_absence(column, link) is None:
        return "malformed"
    try:
        zero = value is not None and not isinstance(value, bool) and value == 0
    except TypeError:
        zero = False
    return "absent" if zero else "malformed"


__all__ = [
    "TRACE_FORMAT_VERSION",
    "SourceRef",
    "SourceRefType",
    "Trace",
    "TraceBuilder",
    "TraceNode",
    "exact_companion_failures",
    "reevaluate",
]

SourceRefType = Literal[
    "contract_event",
    "ssp_entry",
    "ssp_range",
    "rule",
    "fx_rate",
    "estimate_version",
    "registry_version",
    "policy_override",
    "import_row",
    "source_record",
]
_SOURCE_REF_TYPES: Final = frozenset(get_args(SourceRefType))
TRACE_FORMAT_VERSION: Final = 1


def _str_mapping(mapping: Mapping[str, str], name: str) -> dict[str, str]:
    for key, value in mapping.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError(f"{name} must map str to str")
    return dict(sorted(mapping.items()))


@dataclass(frozen=True, slots=True)
class SourceRef:
    """A natural-key reference to a source row (CV-53); ``detail["value"]`` may carry its value."""

    ref_type: SourceRefType
    ref_id: str
    detail: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.ref_type not in _SOURCE_REF_TYPES:
            raise ValueError(f"unknown source reference type {self.ref_type!r}")
        object.__setattr__(self, "detail", _str_mapping(self.detail, "detail"))


@dataclass(frozen=True, slots=True)
class TraceNode:
    id: str
    measure: str
    value: str
    currency: str | None
    formula_id: str
    inputs: tuple[str | SourceRef, ...]
    params: Mapping[str, str]
    rounding_residue: str | None
    narrative_key: str


@dataclass(frozen=True, slots=True)
class Trace:
    format_version: int
    engine_version: str
    nodes: tuple[TraceNode, ...]
    root_measures: Mapping[str, str]

    def sha256(self) -> str:
        """SHA-256 of the canonical JSON of the trace (DG-KRN-EXP-05)."""
        return sha256_hex(self)


class TraceBuilder:
    """Collects the nodes of one computation; ``build`` sorts them by id."""

    def __init__(self, *, engine_version: str) -> None:
        self._engine_version = engine_version
        self._nodes: dict[str, TraceNode] = {}

    def node(
        self,
        *,
        measure: str,
        subject_key: str,
        period_key: str | None,
        value: Fraction | Decimal | int,
        currency: str | None,
        minor_unit: int | None,
        formula_id: str,
        inputs: Sequence[str | SourceRef],
        params: Mapping[str, str] | None = None,
        exact: Fraction | None = None,
        narrative_key: str,
    ) -> str:
        """Add a node and return its id (DG-KRN-EXP-02, 03).

        A posted node (``minor_unit`` given) takes ``value`` in integer minor units and ``exact``
        for its residue; without ``exact`` the residue is ``"0"``. An exact node takes ``value``.
        """
        if not measure or ":" in measure:
            raise ValueError("a measure is non-empty and never contains ':' (CV-50)")
        if not FORMULA_ID.fullmatch(formula_id):
            raise ValueError(f"formula id {formula_id!r} is not <area>.<name>.v<n> (CV-52)")
        if narrative_key != formula_id.rsplit(".v", 1)[0]:
            raise ValueError("narrative_key is the formula id without its version suffix (CV-54)")
        node_id = f"{measure}:{subject_key}:{'-' if period_key is None else period_key}"
        if node_id in self._nodes:
            raise EngineError(
                "TRACE_DUPLICATE_NODE",
                "a trace node id was emitted twice",
                subject_key=subject_key,
                formula_id=formula_id,
                detail={"node_id": node_id},
            )
        for item in inputs:
            if not isinstance(item, str | SourceRef):
                raise TypeError(
                    f"a node input is a node id or SourceRef, not {type(item).__name__}"
                )
        node_params = _str_mapping(params or {}, "params")
        residue: str | None
        if minor_unit is None:
            if exact is not None:
                raise ValueError("an exact node holds its value in value, not exact")
            encoded = format_exact(to_fraction(value))
            residue = None
        else:
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError("a posted node value is int minor units")
            if currency is None:
                raise ValueError("a posted node requires a currency")
            encoded = format_money(value, minor_unit)
            if node_params.get("minor_unit", str(minor_unit)) != str(minor_unit):
                raise ValueError("params minor_unit disagrees with minor_unit")
            node_params = _str_mapping({**node_params, "minor_unit": str(minor_unit)}, "params")
            scale: int = 10**minor_unit
            posted = Fraction(value, scale)
            residue = format_exact((posted if exact is None else to_fraction(exact)) - posted)
        self._nodes[node_id] = TraceNode(
            id=node_id,
            measure=measure,
            value=encoded,
            currency=currency,
            formula_id=formula_id,
            inputs=tuple(inputs),
            params=node_params,
            rounding_residue=residue,
            narrative_key=narrative_key,
        )
        return node_id

    def value(self, node_id: str) -> str | None:
        """The encoded ``value`` of an emitted node, or ``None`` when this builder holds no node
        ``node_id``."""
        found = self._nodes.get(node_id)
        return None if found is None else found.value

    def exact(self, node_id: str) -> Fraction | None:
        """The exact value of an emitted node, ``value + rounding_residue`` (DG-KRN-EXP-03), or
        ``None`` when this builder holds no node ``node_id``."""
        found = self._nodes.get(node_id)
        if found is None:
            return None
        value = to_fraction(found.value)
        if found.rounding_residue is None:
            return value
        return value + to_fraction(found.rounding_residue)

    def build(self, *, root_measures: Mapping[str, str]) -> Trace:
        roots = _str_mapping(root_measures, "root_measures")
        for node_id in roots.values():
            if node_id not in self._nodes:
                raise ValueError(f"root measure names an unknown node {node_id!r}")
        return Trace(
            format_version=TRACE_FORMAT_VERSION,
            engine_version=self._engine_version,
            nodes=tuple(self._nodes[node_id] for node_id in sorted(self._nodes)),
            root_measures=roots,
        )


def reevaluate(trace: Trace) -> Mapping[str, str]:
    """Recompute every node value from its inputs and params in topological order (DG-KRN-EXP-04).

    A node-id input contributes the recomputed value of that node; a source input contributes
    ``detail["value"]``, or ``params["value"]`` of the consuming node when the detail holds none.
    For a formula registered in ``EXACT_INPUT_FORMULAS`` a node-id input contributes its
    DG-KRN-EXP-03 exact value — the recomputed value plus the input node's stored
    ``rounding_residue`` (trace data, not recomputed; the value itself for an exact node) — so the
    formula binds raw operands against the reconstruction the emitting step used (D-98 candidate
    117 F1; dev-guide clause pending its number).
    """
    nodes: dict[str, TraceNode] = {}
    for node in trace.nodes:
        if node.id in nodes:
            raise EngineError(
                "TRACE_DUPLICATE_NODE",
                "a trace node id appears twice",
                detail={"node_id": node.id},
            )
        nodes[node.id] = node
    values: dict[str, str] = {}
    for node_id in _topological_order(nodes):
        node = nodes[node_id]
        formula = FORMULAS.get(node.formula_id)
        if formula is None:
            raise ValueError(f"formula {node.formula_id!r} is not registered")
        exact_inputs = node.formula_id in EXACT_INPUT_FORMULAS
        arguments = [
            _input_value(item, node, nodes, values, exact_inputs)
            if isinstance(item, str)
            else _source_value(item, node)
            for item in node.inputs
        ]
        values[node_id] = _encode(node, formula(arguments, node.params))
    return dict(sorted(values.items()))


def exact_companion_failures(trace: Trace, replayed: Mapping[str, str] | None = None) -> list[str]:
    """ENGINE_SPEC CV-64 rev 1.30 as amended (D-98 134 amendment 1; Codex production-20260921-1422
    T1F-CV64-ENC-1): every posted node naming an exact companion in ``params["exact_node"]`` is
    validated PER STORED FIELD against that field's OWN encoding of the replayed exact —
    ``companion.value == Q18(A_replayed)`` and ``rounding_residue == Q18(A_replayed − P)`` — where
    A_replayed is the RAW rational the companion's own formula chain returns under replay
    (``rec.exact_activity.v1`` over the ``rec.exact_difference.v1`` deltas over the bound endpoint
    operands; never a raw params copy read at face value) and P is the posted value. The two
    checks are independent: signed half-up at 18 places does not commute with translation by P
    when A and A − P sit on opposite-signed ties (1.0049999999999999995 encodes 1.005 while
    1.0049999999999999995 − 1.01 encodes −0.005000000000000001), so ``value + rounding_residue``
    is NOT required to equal the companion. The companion must be this node's own exact measure
    (``<measure>_exact``, same subject and period) and exact-class; a named companion that is
    missing, redirected, posted, or that does not replay is a failure by name. With ``replayed``
    (``reevaluate``'s result) the companion's replayed encoding must also equal its stored value.
    A node WITHOUT ``exact_node`` makes no claim (a legacy trace or an explicitly unavailable
    activity) and is not checked. Returns every failure; a bound residue is thereby verified,
    not asserted — ``reevaluate`` recomputes values, never stored residues."""
    nodes = {node.id: node for node in trace.nodes}
    failures: list[str] = []
    for node in trace.nodes:
        companion_id = node.params.get("exact_node")
        if companion_id is None:
            continue
        companion = nodes.get(companion_id)
        if companion is None:
            failures.append(f"{node.id}: exact companion {companion_id!r} is not in the trace")
            continue
        if node.rounding_residue is None:
            failures.append(f"{node.id}: names an exact companion but is not a posted node")
            continue
        if companion.rounding_residue is not None:
            failures.append(f"{node.id}: exact companion {companion_id!r} is a posted node")
            continue
        expected_id = f"{node.measure}_exact:{node.id.split(':', 1)[1]}"
        if companion_id != expected_id:
            failures.append(
                f"{node.id}: exact companion {companion_id!r} is not its own exact measure "
                f"{expected_id!r}"
            )
            continue
        try:
            raw = _replay_raw(nodes, companion_id)
        except (ValueError, EngineError) as error:
            failures.append(f"{node.id}: exact companion {companion_id!r} does not replay: {error}")
            continue
        expected_value = format_exact(raw)
        if companion.value != expected_value:
            failures.append(
                f"{node.id}: companion {companion_id!r} value {companion.value} != "
                f"Q18(A_replayed) {expected_value}"
            )
        expected_residue = format_exact(raw - to_fraction(node.value))
        if node.rounding_residue != expected_residue:
            failures.append(
                f"{node.id}: rounding_residue {node.rounding_residue} != Q18(A_replayed − P) "
                f"{expected_residue}"
            )
        if replayed is not None and replayed.get(companion_id) != companion.value:
            failures.append(
                f"{node.id}: companion {companion_id!r} replays {replayed.get(companion_id)!r}, "
                f"stored {companion.value!r}"
            )
    return failures


def _replay_raw(nodes: Mapping[str, TraceNode], root: str) -> Fraction:
    """The RAW rational ``root``'s formula returns under the same replay ``reevaluate`` performs,
    restricted to ``root`` and its ancestors (values encoded level by level exactly as
    ``reevaluate`` does; the root's own result kept before encoding). The chain's raw operands
    travel as CV-51-bound params and are returned raw when bound, so the root's rational is the
    emitter's exact — the encoded node values are the checkpoints the bindings are verified
    against (the bindings do sum encoded inputs for their checks) and are never substituted as
    the authoritative raw total; the raw root is authoritative for the two final encodings
    only."""
    ancestors: dict[str, TraceNode] = {}
    pending = [root]
    while pending:
        node_id = pending.pop()
        if node_id in ancestors:
            continue
        node = nodes.get(node_id)
        if node is None:
            raise ValueError(f"node {node_id!r} is not in the trace")
        ancestors[node_id] = node
        pending.extend(_node_inputs(node))
    values: dict[str, str] = {}
    result: Fraction | None = None
    for node_id in _topological_order(ancestors):
        node = ancestors[node_id]
        formula = FORMULAS.get(node.formula_id)
        if formula is None:
            raise ValueError(f"formula {node.formula_id!r} is not registered")
        exact_inputs = node.formula_id in EXACT_INPUT_FORMULAS
        arguments = [
            _input_value(item, node, ancestors, values, exact_inputs)
            if isinstance(item, str)
            else _source_value(item, node)
            for item in node.inputs
        ]
        computed = formula(arguments, node.params)
        values[node_id] = _encode(node, computed)
        if node_id == root:
            result = computed
    assert result is not None  # the root is always in its own ancestor set
    return result


def _node_inputs(node: TraceNode) -> Iterator[str]:
    return (item for item in node.inputs if isinstance(item, str))


def _topological_order(nodes: Mapping[str, TraceNode]) -> list[str]:
    order: list[str] = []
    done: dict[str, bool] = {}  # False while on the stack, True once ordered
    for root in sorted(nodes):
        if root in done:
            continue
        done[root] = False
        stack: list[tuple[str, Iterator[str]]] = [(root, _node_inputs(nodes[root]))]
        while stack:
            current, pending = stack[-1]
            for child in pending:
                if child not in nodes:
                    raise ValueError(f"node {current!r} names an unknown input {child!r}")
                if child not in done:
                    done[child] = False
                    stack.append((child, _node_inputs(nodes[child])))
                    break
                if not done[child]:
                    raise ValueError(f"trace nodes form a cycle through {child!r}")
            else:
                done[current] = True
                order.append(current)
                stack.pop()
    return order


def _input_value(
    item: str,
    node: TraceNode,
    nodes: Mapping[str, TraceNode],
    values: Mapping[str, str],
    exact: bool,
) -> Fraction:
    """A node-id input of ``node``: the recomputed value, plus the input node's stored
    ``rounding_residue`` when the consuming formula takes exact inputs (DG-KRN-EXP-03)."""
    value = to_fraction(values[item])
    residue = nodes[item].rounding_residue
    if exact and residue is not None:
        value += to_fraction(residue)
    return value


def _source_value(ref: SourceRef, node: TraceNode) -> Fraction:
    value = ref.detail.get("value", node.params.get("value"))
    if value is None:
        raise ValueError(f"source input {ref.ref_id!r} of {node.id!r} carries no value")
    return to_fraction(value)


def _encode(node: TraceNode, result: Fraction) -> str:
    if node.rounding_residue is None:
        return format_exact(result)
    minor_unit = minor_unit_of(node.params)
    scale: int = 10**minor_unit
    scaled = result * scale
    if scaled.denominator != 1:
        raise ValueError(
            f"formula {node.formula_id!r} returned a posted value below the minor unit"
        )
    return format_money(scaled.numerator, minor_unit)
