"""D-98 candidate 89 — exact trace-sourced values for the legacy exports (04 §17.1 rules 4 and 4a
rev 1.75; SCREENS_B §5.6.2 RPT-10 rev 1.24; dev-guide DG-PAR-05 and DG-KRN-EXP-08; Codex
production-20260921-1155 §1 and -2215 §3 / §4; lane F-LMG record §27).

``attach_exact_texts`` gives every export row (an ``obligation_version`` row with
``trace_nodes`` and ``contract_version_id``) the exact decimal text of the
``legacy_columns.EXACT_TEXT_COLUMNS`` under ``legacy_columns.EXACT_TEXT_KEY``: for each column the
node ``obligation_version.trace_nodes[column]`` of the row's OWN contract version's stored calc
trace (``explain.store.load_trace``; one load per distinct contract version among the rows
given — current and previous alike).

Rule 4 — the six ``EXACT_COLUMNS``: the node is read as ``exact_values.node_exact`` (``value +
rounding_residue``, text → Decimal → Fraction, never re-scaled — the D-98 117 class cannot
arise) and rendered by ``reconciliation.exact_decimal_text`` (the exact finite expansion; node
values and residues are ``format_money`` / ``format_exact`` text, so the sum is finite; a
non-terminating value would raise, never be rounded silently). A row whose version has no
stored trace, whose ``trace_nodes`` binds no node for a column, or whose trace lacks the bound
node refuses the WHOLE run by name (422 ``validation-failed``, rule ``DG-PAR-05``; no partial
file), naming EVERY offending (contract version, obligation version, column) with its reason —
``trace missing``, ``node absent (pre-provenance trace)``, ``hash mismatch`` — never the first
only (RULING 1, Q-89-2), a wholly missing or hash-invalid trace expanded to one finding per
requested column of the row (Codex 1535 LMG89-FINDINGS-1: complete diagnostics, never a wildcard);
the posted cents are never written in its place. The linkage is ACTUAL,
not a matching value (Codex 1521 §3 (a)): the node is the one the row's own ``trace_nodes`` binds,
in the stored trace of the row's own contract version (which fixes the book), and the node's
currency is POPULATED and equals the version's transaction currency (``txn_currency``), as rule
4a requires (CL55-RULE4-CURRENCY-1, 04 rev 1.87; Codex 0431 §4) — a node carrying no currency,
a version without a transaction currency, or a node in another currency refuses like a missing
node (``currency missing`` / ``currency mismatch``). An adjusted target's cumulative is posted-only
BY RULE (the node's residue is ``0``); it is rendered as that rule value.

Rule 4a — the exact ACTIVITY ``ACTIVITY_COLUMNS`` (``revenue_amount``, LM-CL-55; D-98 89 RULING 2
+ AMENDMENT 1; D-98 candidate 149; ENG-T1F's CV-64 rev 1.30 companion contract): the bound node is
the POSTED ``revenue_amount`` node, linked exactly as rule 4 (own version, own trace, actual node,
the version's currency); its exact is NEVER ``value + rounding_residue`` (DG-KRN-EXP-08: signed
half-up at 18 places does not commute with translation by P on opposite-signed ties, D-98 134
AMENDMENT 1) but the OWN serialized value of the companion the node names in
``params["exact_node"]`` (``revenue_amount_exact:<subject>``, an exact-class node). Availability is
decided BEFORE the shared checker: ``params["exact_basis"]`` present → UNAVAILABLE, the cell is
the literal ``legacy_columns.UNAVAILABLE_TEXT`` (an adjusted target is a legitimate state, never
posted-as-exact, never blank); neither param → LEGACY, a pre-provenance trace, refused by name
like an absent node; ``exact_node`` present → the companion must be in the trace (else ``companion
missing``), the node's own exact measure (else ``companion redirected``), exact-class and in the
version's currency, and THEN ``erev_engine.trace.exact_companion_failures(trace,
reevaluate(trace))`` — computed once per loaded trace — must report nothing for the posted node
(else ``companion invalid: <every failure>``); the checker skips nodes without ``exact_node``, so
its silence alone never proves availability. Every refusal is run-level, named per (contract
version, obligation version, column) under the same ``DG-PAR-05`` rule id; only the UNAVAILABLE
branch writes a cell.

CL55-BINDING-1 (Codex production-20260922-0233 §2–§3): the binding is checked BEFORE availability —
the bound posted node's measure is ``revenue_amount`` (``measure mismatch`` otherwise: a retained
trace binding the column to another posted node, ``revenue_cum`` say, refuses even when that node
carries ``exact_basis`` — never ``unavailable``) and its currency is POPULATED and equals the
version's transaction currency (``currency missing`` / ``currency mismatch``); for SUPPORTED, before
acceptance, the companion's measure is ``revenue_amount_exact`` and its currency is populated and
matches. The store admits those fields under their canonical hash and the numerical replay does not
validate them, so the consumer does.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final
from uuid import UUID

from erev_engine.errors import EngineError
from erev_engine.trace import Trace, TraceNode, exact_companion_failures, reevaluate

from erev_api.domain.migration.exact_values import ExactSourceError, node_exact
from erev_api.domain.migration.reconciliation import exact_decimal_text
from erev_api.domain.reports.legacy_columns import (
    ACTIVITY_COLUMNS,
    EXACT_TEXT_COLUMNS,
    EXACT_TEXT_KEY,
    UNAVAILABLE_TEXT,
)
from erev_api.explain import store
from erev_api.explain.store import TraceIntegrityError
from erev_api.problems import Problem, ProblemError

__all__ = [
    "REASON_COMPANION_INVALID",
    "REASON_COMPANION_MISSING",
    "REASON_COMPANION_REDIRECTED",
    "REASON_CURRENCY_MISMATCH",
    "REASON_CURRENCY_MISSING",
    "REASON_HASH_MISMATCH",
    "REASON_MEASURE_MISMATCH",
    "REASON_NODE_ABSENT",
    "REASON_TRACE_MISSING",
    "RULE",
    "Finding",
    "LoadedTrace",
    "TraceLoader",
    "attach_exact_texts",
    "exact_texts_of",
    "refusal",
]

RULE: Final = "DG-PAR-05"
# RULING 1 (D-98 89, Q-89-2): the three distinct named reasons of a run-level refusal
REASON_TRACE_MISSING: Final = "trace missing"
REASON_NODE_ABSENT: Final = "node absent (pre-provenance trace)"
REASON_HASH_MISMATCH: Final = "hash mismatch"
REASON_CURRENCY_MISMATCH: Final = "currency mismatch"  # Codex 1521 §3 (a): the linkage is actual
# 04 §17.1 rule 4a (D-98 89 RULING 2; D-98 candidate 149): the named companion refusals of the
# exact activity — a producer defect, never posted cents, never the posted node's own residue
REASON_COMPANION_MISSING: Final = "companion missing"
REASON_COMPANION_REDIRECTED: Final = "companion redirected"
REASON_COMPANION_INVALID: Final = "companion invalid"
# CL55-BINDING-1 (Codex 0233): the binding checks of rule 4a (2), BEFORE availability and acceptance
REASON_MEASURE_MISMATCH: Final = "measure mismatch"
REASON_CURRENCY_MISSING: Final = "currency missing"
_ACTIVITY: Final = frozenset(ACTIVITY_COLUMNS)
type TraceLoader = Callable[[Any, UUID], Trace | None]


@dataclass(frozen=True, slots=True)
class Finding:
    """One offending (contract version, obligation version, column) of a refused export run."""

    contract_version_id: str
    obligation_version_id: str
    column: (
        str  # one finding per (version, obligation, column) — a wholly unusable trace is expanded
    )
    reason: str

    @property
    def field(self) -> str:
        return f"rows[{self.obligation_version_id}].{self.column}"

    @property
    def message(self) -> str:
        return (
            f"contract version {self.contract_version_id}, obligation version "
            f"{self.obligation_version_id}, {self.column}: {self.reason} — the legacy export "
            "writes "
            "DG-PAR-05 exact(m), never the posted cents (D-98 candidate 89)"
        )


@dataclass(slots=True)
class LoadedTrace:
    """One stored calc trace: its node map and — computed once, on the first exact-activity read
    — the shared checker's failures grouped by posted node (rule 4a step (4); the whole trace is
    replayed with ``reevaluate`` so the companion's replayed encoding is compared too)."""

    trace: Trace
    nodes: dict[str, TraceNode]
    _failures: dict[str, list[str]] | None = field(default=None, repr=False)

    @classmethod
    def of(cls, trace: Trace) -> LoadedTrace:
        return cls(trace, {node.id: node for node in trace.nodes})

    def companion_failures(self, node_id: str) -> list[str]:
        """Every ``exact_companion_failures`` line about the posted node ``node_id`` (none when the
        companion validates); a trace that does not replay at all is one failure for every node
        asked, named — never silently treated as validated."""
        if self._failures is None:
            grouped: dict[str, list[str]] = {}
            try:
                for failure in exact_companion_failures(self.trace, reevaluate(self.trace)):
                    head = failure.split(": ", 1)[0]
                    grouped.setdefault(head, []).append(failure)
            except (ValueError, EngineError) as error:
                grouped = {"": [f"the calc trace does not replay: {error}"]}
            self._failures = grouped
        broken = self._failures.get("")
        if broken is not None:
            return list(broken)
        return list(self._failures.get(node_id, ()))


def refusal(findings: Sequence[Finding]) -> Problem:
    """The WHOLE run refused by name: one finding per offending (version, obligation, column)."""
    count = len(findings)
    return Problem(
        "validation-failed",
        f"{count} field{'s' if count != 1 else ''} need{'s' if count == 1 else ''} attention.",
        errors=[
            ProblemError(field=item.field, rule_id=RULE, message=item.message) for item in findings
        ],
    )


def _activity_text(
    node: TraceNode, loaded: LoadedTrace, currency: Any
) -> tuple[str | None, str | None]:
    """Rule 4a steps (3) to (5) for the posted activity node: ``(cell text, None)`` on the SUPPORTED
    and UNAVAILABLE branches, ``(None, reason)`` on every refused branch."""
    basis = node.params.get("exact_basis")
    companion_id = node.params.get("exact_node")
    if basis is not None and companion_id is not None:
        return None, (
            f"{REASON_COMPANION_INVALID}: {node.id} names both exact_node {companion_id!r} and "
            f"exact_basis {basis!r} (04 §17.1 rule 4a)"
        )
    if basis is not None:
        # UNAVAILABLE by the producer's own word (an adjusted or unauthored endpoint): the literal,
        # never the posted cents, never blank (D-98 candidate 149 (i))
        return UNAVAILABLE_TEXT, None
    if companion_id is None:
        return None, (
            f"{REASON_NODE_ABSENT}: {node.id} names no exact companion and no exact_basis — a "
            "trace without exact-activity provenance (04 §17.1 rule 4a)"
        )
    companion = loaded.nodes.get(companion_id)
    if companion is None:
        return None, f"{REASON_COMPANION_MISSING}: {companion_id} is not in the calc trace"
    expected_id = f"{node.measure}_exact:{node.id.split(':', 1)[1]}"
    if companion_id != expected_id:
        return None, (
            f"{REASON_COMPANION_REDIRECTED}: {node.id} names {companion_id!r}, not its own exact "
            f"measure {expected_id!r}"
        )
    if companion.rounding_residue is not None:
        return None, (
            f"{REASON_COMPANION_INVALID}: {companion_id} is a posted node, not the exact-class "
            "companion"
        )
    # CL55-BINDING-1 (iii) / (iv): the companion's own measure and a populated, matching currency
    if companion.measure != f"{node.measure}_exact":
        return None, (
            f"{REASON_MEASURE_MISMATCH}: companion {companion_id} measures {companion.measure!r}, "
            f"not {node.measure + '_exact'!r} (04 §17.1 rule 4a)"
        )
    if companion.currency is None:
        return None, (
            f"{REASON_CURRENCY_MISSING}: companion {companion_id} carries no currency; the "
            f"version's transaction currency is {currency}"
        )
    if str(companion.currency) != str(currency):
        return None, (
            f"{REASON_CURRENCY_MISMATCH}: companion {companion_id} carries {companion.currency}, "
            f"the version's transaction currency is {currency}"
        )
    failures = loaded.companion_failures(node.id)
    if failures:
        return None, f"{REASON_COMPANION_INVALID}: {'; '.join(failures)}"
    try:
        # the companion's OWN serialized value (residue None — nothing is added, nothing rescaled)
        return exact_decimal_text(node_exact(companion)), None
    except (ExactSourceError, ValueError) as error:
        return None, f"unrepresentable companion value: {error}"


def exact_texts_of(
    row: Mapping[str, Any], loaded: LoadedTrace, columns: Iterable[str] = EXACT_TEXT_COLUMNS
) -> tuple[dict[str, str], list[Finding]]:
    """``{column: exact decimal text}`` of one row over ITS contract version's loaded trace, and the
    findings of the columns that have no usable source (every one, not the first). An activity
    column (rule 4a) yields the companion's own value, or the ``unavailable`` literal."""
    bound: Mapping[str, Any] = row.get("trace_nodes") or {}
    version = str(row.get("contract_version_id"))
    obligation = str(row.get("id"))
    texts: dict[str, str] = {}
    findings: list[Finding] = []
    for column in columns:
        node_id = bound.get(column)
        if not isinstance(node_id, str):
            findings.append(
                Finding(
                    version,
                    obligation,
                    column,
                    f"{REASON_NODE_ABSENT}: trace_nodes binds no node for {column}",
                )
            )
            continue
        node = loaded.nodes.get(node_id)
        if node is None:
            findings.append(
                Finding(
                    version,
                    obligation,
                    column,
                    f"{REASON_NODE_ABSENT}: {node_id} is not in the calc trace",
                )
            )
            continue
        currency = row.get("txn_currency")
        node_currency = getattr(node, "currency", None)
        if column in _ACTIVITY:
            # CL55-BINDING-1 (i) / (ii): the binding BEFORE availability — the posted node's own
            # measure, and a populated currency equal to the version's (Codex 0233 §2–§3)
            reason: str | None
            if node.measure != column:
                reason = (
                    f"{REASON_MEASURE_MISMATCH}: node {node_id} measures {node.measure!r}, the "
                    f"bound column is {column!r} (04 §17.1 rule 4a)"
                )
            elif currency is None or node_currency is None:
                reason = (
                    f"{REASON_CURRENCY_MISSING}: node {node_id} carries {node_currency!r}, the "
                    f"version's transaction currency is {currency!r} — both must be populated and "
                    "equal (04 §17.1 rule 4a)"
                )
            elif str(node_currency) != str(currency):
                reason = (
                    f"{REASON_CURRENCY_MISMATCH}: node {node_id} carries {node_currency}, the "
                    f"version's transaction currency is {currency}"
                )
            else:
                text, reason = _activity_text(node, loaded, currency)
                if reason is None and text is not None:
                    texts[column] = text
            if reason is not None:
                findings.append(Finding(version, obligation, column, reason))
            continue
        # CL55-RULE4-CURRENCY-1 (04 §17.1 rule 4 rev 1.87; Codex 0431 §4): the binding requires a
        # POPULATED node currency equal to the version's — as rule 4a; a NULL on either side is a
        # refusal by name, never a silent pass (the golden population carries none)
        if currency is None or node_currency is None:
            findings.append(
                Finding(
                    version,
                    obligation,
                    column,
                    f"{REASON_CURRENCY_MISSING}: node {node_id} carries {node_currency!r}, the "
                    f"version's transaction currency is {currency!r} — both must be populated and "
                    "equal (04 §17.1 rule 4)",
                )
            )
            continue
        if str(node_currency) != str(currency):
            findings.append(
                Finding(
                    version,
                    obligation,
                    column,
                    f"{REASON_CURRENCY_MISMATCH}: node {node_id} carries {node_currency}, the "
                    f"version's transaction currency is {currency}",
                )
            )
            continue
        try:
            texts[column] = exact_decimal_text(node_exact(node))
        except (ExactSourceError, ValueError) as error:
            findings.append(
                Finding(version, obligation, column, f"unrepresentable node value: {error}")
            )
    return texts, findings


def attach_exact_texts(
    session: Any,
    rows: Iterable[MutableMapping[str, Any]],
    *,
    loader: TraceLoader | None = None,
    columns: Iterable[str] = EXACT_TEXT_COLUMNS,
) -> int:
    """Attach ``EXACT_TEXT_KEY`` to every row from its OWN contract version's stored trace (one load
    per distinct contract version; ``loader`` defaults to ``explain.store.load_trace``, resolved at
    call time). With ANY missing source the whole run is refused once, every offending (contract
    version, obligation version, column) named with its reason — no partial attachment is relied
    on, no posted fallback. Returns the number of distinct traces loaded."""
    load = store.load_trace if loader is None else loader
    wanted = tuple(columns)
    # the loaded trace of each version, or the reason the version has none
    traces: dict[UUID, LoadedTrace | str] = {}
    findings: list[Finding] = []
    for row in rows:
        version_id = UUID(str(row["contract_version_id"]))
        cached = traces.get(version_id)
        if cached is None:
            try:
                trace = load(session, version_id)
            except TraceIntegrityError as error:
                cached = f"{REASON_HASH_MISMATCH}: {error}"
            else:
                cached = REASON_TRACE_MISSING if trace is None else LoadedTrace.of(trace)
            traces[version_id] = cached
        if isinstance(cached, str):
            # LMG89-FINDINGS-1 (Codex 1535): the unusable trace is named for EVERY requested column
            # of the row — one finding per (contract version, obligation version, column)
            findings.extend(
                Finding(str(version_id), str(row.get("id")), column, cached) for column in wanted
            )
            continue
        texts, row_findings = exact_texts_of(row, cached, wanted)
        if row_findings:
            findings.extend(row_findings)
            continue
        row[EXACT_TEXT_KEY] = texts
    if findings:
        raise refusal(findings)
    return sum(1 for cached in traces.values() if not isinstance(cached, str))
