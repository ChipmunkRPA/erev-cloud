"""Migration reconciliation (BUILD_SPEC LMG-3; 04 T-MIG-03; SCREENS_B §5.6.7 RPT-41; PRD BR-MIG-02,
WLD-X-27, WLD-X-28; D-17; ``docs/legacy/DEVIATIONS.md`` §2.2, §7.2) and the GPB-3 point-in-time
equivalence oracle (BUILD_SPEC GPB-3; dev-guide §9.6 kind ``point_in_time_equivalence``;
DEVIATIONS OQ-D7; legacy 07 GT-20; ``docs/legacy/golden/compare-shipped/``).

Reconciliation lines. ``legacy_values`` reads the nine T-MIG-03 measures (04 rev 1.35) from the
latest legacy rows per contract (``POB_COUNT``, ``TRANSACTION_PRICE``, ``REVENUE_CUM``,
``BILLED_CUM``, ``NET_POSITION``, ``RECLASS``) and per obligation (``ORIGINAL_ALLOCATION`` — the
creation-time allocation, legacy ``Original Allocation`` LM-CL-29, eRev
``original_allocated_exact``, D-98 candidate 48 — ``ALLOCATION``, ``REVENUE_CUM``,
``BILLED_CUM``, ``NET_POSITION``, ``RECLASS``, ``REMAINING_QTY``); ``lines`` compares them with
the eRev values the caller read (the contract and obligation versions of the staged or replayed
contracts) within ``0.0001`` (D-17), attaches a ``deviation_ref`` only when
``docs/legacy/golden/deviations.json`` documents, for the contract, obligation and measure, the
applicable difference the line shows (its source value is the documented legacy value and its
eRev value the documented corrected value — equality as DG-PAR-07 defines it for a documented
value, within the entry's own tolerance; Codex review of ed5173f, finding R1), and marks every
other difference as needing an exception item (T-MIG-03; source ``MIGRATION``). A golden field
explains a line only when it IS that T-MIG-03 measure (dev-guide §9.6 kind sources): ``Original
allocation`` is ``ORIGINAL_ALLOCATION`` (so DEV-052 explains the creation-time allocation line of
Contract 3 POB #5 for its documented pair NULL → 1,268.1139, PRD J-21.3), while ``Remaining
allocation`` and the other fields that are no measure never explain a line; documented
differences on such fields are kept as ``DeviationIndex.unmeasured`` (empty over the shipped
documents since 04 rev 1.35).
``control_totals`` and ``tie_out_result`` give RPT-41's totals and
``TO_MIGRATION_UNEXPLAINED_ZERO``, which promotion requires to pass (BR-MIG-02; CTL-048).

Point-in-time equivalence. ``compare_point_in_time`` aligns the shipped ``Contract_Live`` rows
with the eRev export rows (the 71 legacy names as keys, ``legacy_columns.legacy_row``) by
version rank and ``Record Unique ID without time``, excludes ``Processing Time Log`` and
``Record Unique ID``, compares the columns whose legacy declared type is numeric within
``0.0001`` and every other column as text, exactly, and reports ``rows``,
``columns_with_mismatch`` and one status row per column in the shape of the harness's
``point_in_time_column_diffs.csv``. Standard library only.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any, Final, Literal

from erev_api.domain.migration import legacy_db
from erev_api.domain.migration.legacy_db import LegacyColumn, LegacyRow

__all__ = [
    "CONTRACT_MEASURES",
    "EXCLUDED_COLUMNS",
    "FIELD_MEASURES",
    "MEASURES",
    "OBLIGATION_MEASURES",
    "TIE_OUT",
    "TOLERANCE",
    "EXCLUDED",
    "MATCH",
    "MISMATCH",
    "NUMERIC",
    "ROWS_COLUMN",
    "TEXT",
    "ColumnStatus",
    "ControlTotals",
    "Deviation",
    "DeviationIndex",
    "EquivalenceResult",
    "Line",
    "LineKey",
    "Mismatch",
    "compare_point_in_time",
    "control_totals",
    "EMPTY_KEY_MARKER",
    "encode_key_component",
    "exact_decimal",
    "exact_decimal_text",
    "legacy_values",
    "lines",
    "tie_out_result",
]

type Measure = Literal[
    "POB_COUNT",
    "TRANSACTION_PRICE",
    "ORIGINAL_ALLOCATION",
    "ALLOCATION",
    "REVENUE_CUM",
    "BILLED_CUM",
    "NET_POSITION",
    "RECLASS",
    "REMAINING_QTY",
]
type LineKey = tuple[
    str, str | None, str
]  # (contract external id, obligation key or None, measure)

MEASURES: Final[tuple[Measure, ...]] = (
    "POB_COUNT",
    "TRANSACTION_PRICE",
    "ORIGINAL_ALLOCATION",
    "ALLOCATION",
    "REVENUE_CUM",
    "BILLED_CUM",
    "NET_POSITION",
    "RECLASS",
    "REMAINING_QTY",
)
CONTRACT_MEASURES: Final[tuple[Measure, ...]] = (
    "POB_COUNT",
    "TRANSACTION_PRICE",
    "REVENUE_CUM",
    "BILLED_CUM",
    "NET_POSITION",
    "RECLASS",
)
OBLIGATION_MEASURES: Final[tuple[Measure, ...]] = (
    "ORIGINAL_ALLOCATION",
    "ALLOCATION",
    "REVENUE_CUM",
    "BILLED_CUM",
    "NET_POSITION",
    "RECLASS",
    "REMAINING_QTY",
)
TOLERANCE: Final = Fraction(1, 10000)  # D-17; T-MIG-03 default
TIE_OUT: Final = "TO_MIGRATION_UNEXPLAINED_ZERO"
EXCLUDED_COLUMNS: Final = frozenset({legacy_db.PROCESSING_TIME_LOG, legacy_db.RECORD_UNIQUE_ID})
# Legacy columns each obligation-level measure reads (04 §17.2).
_ORIGINAL_ALLOCATION: Final = "Original Allocation"  # LM-CL-29 (rev 1.35 measure)
_REVENUE_CUM: Final = "Current Rev Rec - Cumulative"
_REMAINING_ALLOCATION: Final = "Current Remaining Allocation"
_BILLED_CUM: Final = "Current Billing - Cumulative"
_POSITION_POB: Final = "Current Contract Position - POB"
_RECLASS: Final = "Current Reclass to UAR"
_REMAINING_QTY: Final = "Current Remaining Qty"
# Golden kind-table field names (dev-guide §9.6 ``pob_position`` / ``contract_position`` sources)
# that ARE a T-MIG-03 measure. Not listed, so never an explanation (Codex R1): ``Remaining
# allocation`` (``exact(remaining_allocation)``), ``Qty delivered cum``, ``Catch-up cum
# (disclosure)``, ``tp_billing_basis``. ``Original allocation`` is its own measure since 04 rev
# 1.19 (D-98 candidate 48), never the final ``ALLOCATION``.
FIELD_MEASURES: Final[Mapping[str, Measure]] = {
    "Original allocation": "ORIGINAL_ALLOCATION",
    "Final allocation (rev cum + remaining)": "ALLOCATION",
    "Revenue cum": "REVENUE_CUM",
    "revenue_cum": "REVENUE_CUM",
    "Billing cum": "BILLED_CUM",
    "billing_cum": "BILLED_CUM",
    "Position POB": "NET_POSITION",
    "position": "NET_POSITION",
    "Remaining qty": "REMAINING_QTY",
    "tp_allocation_basis": "TRANSACTION_PRICE",
    "uar_reclass_field": "RECLASS",
}
_ZERO: Final = Fraction(0)


def _fraction(text: str | None) -> Fraction:
    value = legacy_db.decimal_of(text)
    return _ZERO if value is None else Fraction(value)


def exact_decimal_text(value: Fraction) -> str:
    """The exact finite decimal expansion of ``value`` as text, trailing zeros trimmed (RPT-41
    "exact decimal text"; T-MIG-03 ``erev.exact`` values): integer arithmetic on a denominator
    2^a·5^b, no rounding and no ``Decimal`` context; ``ValueError`` for a non-terminating value,
    so nothing is rounded silently (Codex review of ed5173f, finding R3)."""
    if value.denominator == 1:
        return str(value.numerator)
    rest, twos, fives = value.denominator, 0, 0
    while rest % 2 == 0:
        rest, twos = rest // 2, twos + 1
    while rest % 5 == 0:
        rest, fives = rest // 5, fives + 1
    if rest != 1:
        raise ValueError(f"{value} has no finite decimal expansion")
    places = max(twos, fives)
    scaled = abs(value.numerator) * 10**places // value.denominator
    digits = str(scaled).rjust(places + 1, "0")
    whole, fraction = digits[:-places], digits[-places:].rstrip("0")
    text = whole if not fraction else f"{whole}.{fraction}"
    return f"-{text}" if value < 0 and text != "0" else text


def exact_decimal(value: Fraction) -> Decimal:
    """``exact_decimal_text`` as a ``Decimal`` (the T-MIG-03 ``erev.exact`` column value)."""
    return Decimal(exact_decimal_text(value))


def legacy_values(latest: Iterable[LegacyRow]) -> dict[LineKey, Fraction]:
    """The T-MIG-03 source values of every contract and obligation of the latest legacy rows: the
    obligation measures from LM-CL-29 (``ORIGINAL_ALLOCATION``; a legacy NULL reads 0, as DEV-052's
    Contract 3 POB #5), LM-CL-48, -61, -63, -66, -68 and the contract measures as their sums,
    ``POB_COUNT`` counting the non-``VC`` rows, ``TRANSACTION_PRICE`` = Σ (revenue_cum +
    remaining_allocation) (the allocation basis, dev-guide §9.6 ``tp_allocation_basis``).
    """
    values: dict[LineKey, Fraction] = {}
    totals: dict[tuple[str, str], Fraction] = {}
    for row in latest:
        contract, pob = row.contract_external_id, row.obligation_key
        revenue = _fraction(row.values.get(_REVENUE_CUM))
        allocation = revenue + _fraction(row.values.get(_REMAINING_ALLOCATION))
        per_row: dict[str, Fraction] = {
            "ORIGINAL_ALLOCATION": _fraction(row.values.get(_ORIGINAL_ALLOCATION)),
            "ALLOCATION": allocation,
            "REVENUE_CUM": revenue,
            "BILLED_CUM": _fraction(row.values.get(_BILLED_CUM)),
            "NET_POSITION": _fraction(row.values.get(_POSITION_POB)),
            "RECLASS": _fraction(row.values.get(_RECLASS)),
            "REMAINING_QTY": _fraction(row.values.get(_REMAINING_QTY)),
        }
        for measure, amount in per_row.items():
            values[(contract, pob, measure)] = amount
        totals[(contract, "TRANSACTION_PRICE")] = totals.get(
            (contract, "TRANSACTION_PRICE"), _ZERO
        ) + (allocation)
        for measure in ("REVENUE_CUM", "BILLED_CUM", "NET_POSITION", "RECLASS"):
            totals[(contract, measure)] = totals.get((contract, measure), _ZERO) + per_row[measure]
        if row.values.get(legacy_db.STRATIFICATION) != "VC":
            totals[(contract, "POB_COUNT")] = totals.get((contract, "POB_COUNT"), _ZERO) + 1
    for (contract, measure), amount in totals.items():
        values[(contract, None, measure)] = amount
    ordered = sorted(values.items(), key=lambda item: (item[0][0], item[0][1] or "", item[0][2]))
    return dict(ordered)


@dataclass(frozen=True, slots=True)
class Deviation:
    """One documented applicable difference of a T-MIG-03 line: the DEVIATIONS.md id and the
    (legacy value, corrected value) pair the golden documents record for the contract, obligation
    and measure. A line is explained by it only when its source value is ``legacy_value`` and its
    eRev value ``corrected_value``, each within the tolerance (Codex R1)."""

    dev_id: str
    legacy_value: Fraction
    corrected_value: Fraction
    tolerance: Fraction = TOLERANCE  # the deviations.json entry's own tolerance (DG-PAR-07)


@dataclass(frozen=True, slots=True)
class DeviationIndex:
    """``deviation_ref`` candidates per (contract, obligation, measure) from the golden documents:
    a B-case test of ``golden-tests.json`` whose ``deviations.json`` entry carries a ``dev_id``
    contributes, for its contract and POB, every field that IS a T-MIG-03 measure
    (``FIELD_MEASURES``) and whose corrected expected value differs from the legacy value, as a
    ``Deviation`` holding that pair. ``unmeasured`` keeps the documented differences of fields that
    are NOT a T-MIG-03 measure, keyed by (contract, POB, golden field name) — evidence exposed for
    the report, never an explanation of a measured line. ``source_digests`` records the SHA-256 of
    the documents the index was built from (ruling Q-3 follow-up), empty for a hand-built index."""

    refs: Mapping[tuple[str, str | None, str], Deviation]
    source_digests: Mapping[str, str] = field(default_factory=dict)
    unmeasured: Mapping[tuple[str, str | None, str], Deviation] = field(default_factory=dict)

    def lookup(self, contract: str, obligation: str | None, measure: str) -> Deviation | None:
        return self.refs.get((contract, obligation, measure))

    def explain(
        self,
        contract: str,
        obligation: str | None,
        measure: str,
        *,
        source_value: Fraction,
        erev_value: Fraction,
    ) -> str | None:
        """The deviation id that explains this line, or None: the line's source value must be the
        documented legacy value and its eRev value the documented corrected value (equality as
        DG-PAR-07 defines it for a documented value: within the entry's own tolerance, not the
        caller's). A different difference on the same key (Codex R1: eRev 1,368.1139 or 1,168.1139
        against the equal final allocation 1,268.1139 of Contract 3 POB #5) is not explained."""
        found = self.refs.get((contract, obligation, measure))
        if found is None:
            return None
        if abs(source_value - found.legacy_value) > found.tolerance:
            return None
        if abs(erev_value - found.corrected_value) > found.tolerance:
            return None
        return found.dev_id

    @classmethod
    def empty(cls) -> DeviationIndex:
        return cls({})

    @classmethod
    def from_golden(cls, golden_tests: Path, deviations: Path) -> DeviationIndex:
        """Read the B cases (DEVIATIONS §2.1: a legacy defect with a corrected expected value):
        ``golden-tests.json`` holds the legacy oracle values under ``expected`` and
        ``deviations.json`` the corrected ones. A field that is a T-MIG-03 measure and whose two
        values differ contributes a ``Deviation`` for its contract, POB and measure. Over the
        shipped documents the index is empty: DEV-052 documents ``Original allocation`` null →
        1,268.1139 on Contract 3 POB #5, which is not a T-MIG-03 measure, and the final allocation
        (the ``ALLOCATION`` measure) is 1,268.1139 on both sides (DEVIATIONS §7.2)."""
        golden = json.loads(golden_tests.read_text(encoding="utf-8"))
        adjudicated = json.loads(deviations.read_text(encoding="utf-8"))["tests"]
        refs: dict[tuple[str, str | None, str], Deviation] = {}
        unmeasured: dict[tuple[str, str | None, str], Deviation] = {}
        for test in golden["tests"]:
            entry = adjudicated.get(test["id"])
            if entry is None or entry.get("classification") != "B":
                continue
            dev_id, contract = entry.get("dev_id"), test.get("contract")
            if not dev_id or not contract:
                continue
            pob = None if test.get("pob") is None else str(test.get("pob"))
            legacy = test.get("expected") or {}
            corrected = entry.get("expected") or {}
            tolerance = _fraction_of(entry.get("tolerance")) or TOLERANCE
            for field_name, value in corrected.items():
                before, after = _fraction_of(legacy.get(field_name)), _fraction_of(value)
                if before is None or after is None or before == after:
                    continue
                found = Deviation(str(dev_id), before, after, tolerance)
                measure = FIELD_MEASURES.get(field_name)
                if measure is None:
                    unmeasured.setdefault((str(contract), pob, str(field_name)), found)
                else:
                    refs.setdefault((str(contract), pob, measure), found)

        def _order(item: tuple[tuple[str, str | None, str], Deviation]) -> tuple[str, str, str]:
            return (item[0][0], item[0][1] or "", item[0][2])

        digests = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (golden_tests, deviations)
        }
        return cls(
            dict(sorted(refs.items(), key=_order)),
            digests,
            dict(sorted(unmeasured.items(), key=_order)),
        )


def _fraction_of(value: object) -> Fraction | None:
    """A golden value as an exact fraction; ``None`` (a legacy NULL) reads as 0, the value a
    T-MIG-03 line carries for it (``legacy_values``); text that is no number is ``None``."""
    if value is None:
        return _ZERO
    try:
        return Fraction(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return None


@dataclass(frozen=True, slots=True)
class Line:
    """One T-MIG-03 ``migration_reconciliation_line`` (values exact)."""

    contract_external_id: str
    obligation_key: str | None
    measure: str
    source_value: Fraction
    erev_value: Fraction
    difference: Fraction
    tolerance: Fraction
    is_within_tolerance: bool
    deviation_ref: str | None
    needs_exception: bool  # outside tolerance and no deviation reference
    exception_ref: str | None = None  # the exception number (or id) shown for an unexplained line

    @property
    def key(self) -> LineKey:
        """The line's identity: (contract external id, obligation key or None, measure) — what the
        exception association and every consumer match on, never the display key."""
        return (self.contract_external_id, self.obligation_key, self.measure)

    @property
    def row_key(self) -> str:
        """RPT-41 ``line:<contract>:<obligation>:<measure>`` (SCREENS_B rev 1.13; Codex RPT41-ID-1):
        each component percent-encoded so the key is injective, the contract level an EMPTY
        obligation component — never a word that could be a legitimate obligation key; an
        obligation key that is itself the empty string encodes as ``%``, which no encoded
        component can otherwise produce (Codex packet 1006)."""
        if self.obligation_key is None:
            obligation = ""
        else:
            obligation = encode_key_component(self.obligation_key) or EMPTY_KEY_MARKER
        return (
            f"line:{encode_key_component(self.contract_external_id)}:{obligation}:"
            f"{encode_key_component(self.measure)}"
        )


EMPTY_KEY_MARKER: Final = "%"  # an empty-string component; unreachable by encoding


def encode_key_component(text: str) -> str:
    """The CV-21 key convention: ``%`` → ``%25`` first, then ``:`` → ``%3A``; injective, no
    identifier prohibited."""
    return text.replace("%", "%25").replace(":", "%3A")


def lines(
    source: Mapping[LineKey, Fraction],
    erev: Mapping[LineKey, Fraction],
    deviations: DeviationIndex | None = None,
    *,
    tolerance: Fraction = TOLERANCE,
) -> tuple[Line, ...]:
    """The reconciliation lines over the union of both key sets; a value one side lacks is 0 for
    that side, so the line shows the whole amount as a difference (never silently dropped).
    """
    index = DeviationIndex.empty() if deviations is None else deviations
    found: list[Line] = []
    for key in sorted(set(source) | set(erev), key=lambda item: (item[0], item[1] or "", item[2])):
        contract, obligation, measure = key
        legacy = source.get(key, _ZERO)
        actual = erev.get(key, _ZERO)
        difference = actual - legacy
        within = abs(difference) <= tolerance
        ref = (
            None
            if within
            else index.explain(
                contract, obligation, measure, source_value=legacy, erev_value=actual
            )
        )
        found.append(
            Line(
                contract_external_id=contract,
                obligation_key=obligation,
                measure=measure,
                source_value=legacy,
                erev_value=actual,
                difference=difference,
                tolerance=tolerance,
                is_within_tolerance=within,
                deviation_ref=ref,
                needs_exception=not within and ref is None,
            )
        )
    return tuple(found)


@dataclass(frozen=True, slots=True)
class ControlTotals:
    """RPT-41 control totals (SCREENS_B §5.6.7)."""

    line_count: int
    differences_above_tolerance: int
    explained: int
    unexplained: int

    def as_json(self) -> dict[str, int]:
        return {
            "line_count": self.line_count,
            "differences_above_tolerance": self.differences_above_tolerance,
            "explained": self.explained,
            "unexplained": self.unexplained,
        }


def control_totals(found: Sequence[Line]) -> ControlTotals:
    above = [line for line in found if not line.is_within_tolerance]
    explained = sum(1 for line in above if line.deviation_ref is not None)
    return ControlTotals(len(found), len(above), explained, len(above) - explained)


def tie_out_result(totals: ControlTotals) -> dict[str, Any]:
    """``TO_MIGRATION_UNEXPLAINED_ZERO``: PASS when no difference lacks a deviation reference
    (BR-MIG-02). Expected and actual are counts, so API-S-ReportRun ``difference`` is null (04
    §16.9: computed only over API-S-Money lists).
    """
    return {
        "code": TIE_OUT,
        "result": "PASS" if totals.unexplained == 0 else "FAIL",
        "expected": 0,
        "actual": totals.unexplained,
    }


# --- point-in-time equivalence (GPB-3) ------------------------------------------------------------

ROWS_COLUMN: Final = "__rows__"  # synthetic column: legacy or eRev rows without a partner
MATCH: Final = "match"
MISMATCH: Final = "mismatch"
EXCLUDED: Final = "excluded"
NUMERIC: Final = "numeric"
TEXT: Final = "text"


@dataclass(frozen=True, slots=True)
class Mismatch:
    """One differing cell (or an unpartnered row): the aligned row key, both values, the
    difference (numeric columns) — never a float."""

    row_key: str  # "<version rank>:<Record Unique ID without time>"
    legacy: str | None
    erev: str | None
    diff: Fraction | None


@dataclass(frozen=True, slots=True)
class ColumnStatus:
    """One compared column: its kind (``numeric`` or ``text``, the harness CSV ``status``
    column), whether it matched, every mismatch and the greatest absolute difference."""

    column: str
    kind: str  # NUMERIC | TEXT
    status: str  # MATCH | MISMATCH | EXCLUDED
    mismatches: tuple[Mismatch, ...]
    max_abs_diff: Fraction | None

    @property
    def mismatch_count(self) -> int:
        return len(self.mismatches)

    def to_json(self) -> dict[str, Any]:
        """One row of ``compare-shipped/point_in_time_column_diffs.csv``."""
        return {
            "column": self.column,
            "status": self.kind,
            "mismatches": self.mismatch_count,
            "max_abs_diff": _decimal_text(self.max_abs_diff),
        }


@dataclass(frozen=True, slots=True)
class EquivalenceResult:
    """The GPB-3 oracle (dev-guide §9.6): ``rows`` aligned rows and ``columns_with_mismatch``
    (sorted), with a ``ColumnStatus`` per column including the excluded ones and the synthetic
    ``__rows__`` column for rows one side lacks. Values are ``Fraction`` or text, never floats
    (DG-ENG-03; T1's reader walks the result with ``guards.no_floats``)."""

    rows: int
    columns_with_mismatch: tuple[str, ...]
    columns: Mapping[str, ColumnStatus]
    legacy_rows: int
    erev_rows: int

    @property
    def unmatched_legacy(self) -> tuple[str, ...]:
        return tuple(m.row_key for m in self.columns[ROWS_COLUMN].mismatches if m.erev is None)

    @property
    def unmatched_erev(self) -> tuple[str, ...]:
        return tuple(m.row_key for m in self.columns[ROWS_COLUMN].mismatches if m.legacy is None)

    def to_json(self) -> dict[str, Any]:
        """``rows``, ``columns_with_mismatch`` and the per-column rows in the harness CSV shape."""
        return {
            "rows": self.rows,
            "columns_with_mismatch": list(self.columns_with_mismatch),
            "columns": [
                status.to_json()
                for status in self.columns.values()
                if status.status != EXCLUDED and status.column != ROWS_COLUMN
            ],
            "legacy_rows": self.legacy_rows,
            "erev_rows": self.erev_rows,
            "unmatched_legacy": list(self.unmatched_legacy),
            "unmatched_erev": list(self.unmatched_erev),
        }

    as_json = to_json


def _decimal_text(value: Fraction | None) -> str | None:
    if value is None:
        return None
    if value.denominator == 1:
        return str(value.numerator)
    return str(Decimal(value.numerator) / Decimal(value.denominator))


def _null(value: object) -> bool:
    return value is None or value == ""


def _text(value: object) -> str | None:
    return None if _null(value) else str(value)


def _numeric(value: object) -> Fraction | None:
    if _null(value):
        return None
    return Fraction(Decimal(str(value)))


def _parses(value: object) -> bool:
    try:
        Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    return True


def _aligned(
    rows: Sequence[Mapping[str, object]], *, time_log: str, record_key: str
) -> dict[str, Mapping[str, object]]:
    """Rows keyed by ``"<version rank>:<record key>"``; the rank is the ordinal of the row's
    ``Processing Time Log`` among the side's distinct values (the harness's ``ordinal``)."""
    tokens = sorted({str(row.get(time_log) or "") for row in rows})
    rank = {token: index + 1 for index, token in enumerate(tokens)}
    aligned: dict[str, Mapping[str, object]] = {}
    for row in rows:
        key = f"{rank[str(row.get(time_log) or '')]}:{row.get(record_key) or ''}"
        if key in aligned:
            raise ValueError(f"duplicate row for {key!r}")
        aligned[key] = row
    return aligned


def _column_names(
    legacy: Mapping[str, Mapping[str, object]],
    erev: Mapping[str, Mapping[str, object]],
    schema: Sequence[LegacyColumn] | None,
) -> list[str]:
    if schema is not None:
        return [column.name for column in schema]
    names: list[str] = []
    for side in (legacy, erev):
        for row in side.values():
            for name in row:
                if name not in names:
                    names.append(name)
            break
    return names


def _is_numeric(
    name: str,
    schema: Sequence[LegacyColumn] | None,
    legacy: Mapping[str, Mapping[str, object]],
    erev: Mapping[str, Mapping[str, object]],
    shared: Sequence[str],
) -> bool:
    """Numeric when the legacy declared type says so; without a schema, when every non-null value
    of both sides parses as a decimal and at least one exists (the harness rule)."""
    if schema is not None:
        return any(column.name == name and column.is_numeric for column in schema)
    values = [legacy[key].get(name) for key in shared] + [erev[key].get(name) for key in shared]
    present = [value for value in values if not _null(value)]
    return bool(present) and all(_parses(value) for value in present)


def _sorted_keys(keys: Iterable[str]) -> list[str]:
    return sorted(keys, key=lambda key: (int(key.split(":", 1)[0]), key))


def compare_point_in_time(
    legacy_rows: Sequence[Mapping[str, object]],
    erev_rows: Sequence[Mapping[str, object]],
    *,
    schema: Sequence[LegacyColumn] | None = None,
    tolerance: Fraction = TOLERANCE,
    excluded: Iterable[str] = EXCLUDED_COLUMNS,
) -> EquivalenceResult:
    """The point-in-time equivalence of the shipped ``Contract_Live`` rows and the eRev export
    rows (GPB-3; DEVIATIONS OQ-D7): rows aligned by version rank and record key; ``excluded``
    columns reported with status ``excluded`` and never compared; a numeric column (legacy
    declared type, else both sides decimal) compares within ``tolerance`` with NULL equal to
    NULL, a text column exactly with NULL equal to empty; rows one side lacks are mismatches of
    the synthetic ``__rows__`` column, so ``rows`` is a real assertion."""
    skipped = frozenset(excluded)
    legacy = _aligned(
        legacy_rows, time_log=legacy_db.PROCESSING_TIME_LOG, record_key=legacy_db.RECORD_KEY
    )
    erev = _aligned(
        erev_rows, time_log=legacy_db.PROCESSING_TIME_LOG, record_key=legacy_db.RECORD_KEY
    )
    shared = _sorted_keys(set(legacy) & set(erev))
    columns: dict[str, ColumnStatus] = {}
    for name in _column_names(legacy, erev, schema):
        if name in skipped:
            columns[name] = ColumnStatus(name, TEXT, EXCLUDED, (), None)
            continue
        present = any(name in erev[key] for key in shared)
        found: list[Mismatch] = []
        largest: Fraction | None = None
        numeric = _is_numeric(name, schema, legacy, erev, shared)
        if shared and not present:
            found = [Mismatch(key, _text(legacy[key].get(name)), None, None) for key in shared]
        elif numeric:
            for key in shared:
                a, b = _numeric(legacy[key].get(name)), _numeric(erev[key].get(name))
                if a is None or b is None:
                    if (a is None) != (b is None):
                        found.append(
                            Mismatch(
                                key, _text(legacy[key].get(name)), _text(erev[key].get(name)), None
                            )
                        )
                    continue
                diff = abs(a - b)
                if largest is None or diff > largest:
                    largest = diff
                if diff > tolerance:
                    found.append(
                        Mismatch(
                            key, _text(legacy[key].get(name)), _text(erev[key].get(name)), b - a
                        )
                    )
            if largest is None:
                largest = _ZERO
        else:
            for key in shared:
                left, right = legacy[key].get(name), erev[key].get(name)
                if _null(left) and _null(right):
                    continue
                if str(left) != str(right):
                    found.append(Mismatch(key, _text(left), _text(right), None))
        columns[name] = ColumnStatus(
            name, NUMERIC if numeric else TEXT, MISMATCH if found else MATCH, tuple(found), largest
        )
    unpartnered = [
        Mismatch(key, "row", None, None) for key in _sorted_keys(set(legacy) - set(erev))
    ] + [Mismatch(key, None, "row", None) for key in _sorted_keys(set(erev) - set(legacy))]
    columns[ROWS_COLUMN] = ColumnStatus(
        ROWS_COLUMN, TEXT, MISMATCH if unpartnered else MATCH, tuple(unpartnered), None
    )
    return EquivalenceResult(
        rows=len(shared),
        columns_with_mismatch=tuple(
            sorted(name for name, status in columns.items() if status.status == MISMATCH)
        ),
        columns=columns,
        legacy_rows=len(legacy),
        erev_rows=len(erev),
    )
