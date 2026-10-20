"""RPT-38 monetary endpoints from frozen closes, without inferred driver attribution.

Only the three frozen monetary datasets supply figures. Labels and amounts never
come from current contracts. RPO exemptions are excluded from disclosed RPO, and
currencies are separate keys. The event replay needed for change-by-driver remains
a separate step: these endpoints are evidence, not a completed RPT-38 report.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Final

from erev_api.domain.migration.reconciliation import exact_decimal_text
from erev_api.domain.reports import locked
from erev_api.domain.reports.evidence_close import FrozenClose
from erev_api.enums import LockKind
from erev_api.problems import Problem

FORMAT: Final = "erev.frozen_close_measure_changes.v1"
_DECIMAL: Final = re.compile(r"-?\d+(?:\.\d+)?\Z")
_KEYS: Final = {
    "WATERFALL": ("entity_code", "contract_external_id", "obligation_key", "period_key"),
    "CONTRACT_BALANCES": ("entity_code", "contract_external_id"),
    "RPO": ("entity_code", "contract_external_id", "obligation_key"),
}
_VALUES: Final = {
    "WATERFALL": ("recognised",),
    "CONTRACT_BALANCES": ("contract_liability", "contract_asset", "unbilled_receivable"),
    "RPO": ("section", "total"),
}


@dataclass(frozen=True, order=True)
class MeasureKey:
    contract_external_id: str
    currency: str
    measure: str


@dataclass(frozen=True)
class Endpoint:
    amount: Fraction
    source_rows: tuple[str, ...]


def _refuse(detail: str) -> Problem:
    return Problem("validation-failed", f"Frozen close comparison: {detail}")


def _amount(row: Mapping[str, str], column: str) -> Fraction:
    value = row[column]
    if _DECIMAL.fullmatch(value) is None:
        raise _refuse(f"{column} is missing or is not a finite decimal.")
    return Fraction(value)


def endpoints(
    source: FrozenClose, currency_view: str = "transaction"
) -> dict[MeasureKey, Endpoint]:
    """Aggregate frozen rows exactly, retaining their contribution identities.

    Blank monetary cells never become zero. Zero is used only for a contract/measure
    absent from an otherwise complete, validated dataset on one side of a comparison.
    """
    datasets = {report.dataset.kind: report.dataset for report in source.reports}
    if len(datasets) != len(source.reports) or not set(_KEYS) <= datasets.keys():
        raise _refuse("the monetary dataset set is incomplete or duplicated.")
    amounts: dict[MeasureKey, Fraction] = {}
    contributors: dict[MeasureKey, list[str]] = {}
    for kind, keys in _KEYS.items():
        dataset = datasets[kind]
        if dataset.lock_id != source.scope.lock_id:
            raise _refuse("a monetary dataset belongs to another lock.")
        locked.verify(dataset)
        headers, reader, _ = locked.currency_rows(dataset, currency_view)
        required = {"row_key", "currency", *keys, *_VALUES[kind]}
        if len(headers) != len(set(headers)) or not required <= set(headers):
            raise _refuse(f"{kind} has missing or duplicated columns.")
        seen_rows: set[str] = set()
        seen_keys: set[tuple[str, ...]] = set()
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise _refuse(f"{kind} has a malformed row.")
            identity = tuple(row[key] for key in keys)
            row_key = row["row_key"]
            if not row_key or not all(identity) or row_key in seen_rows or identity in seen_keys:
                raise _refuse(f"{kind} has an empty or duplicated row identity.")
            seen_rows.add(row_key)
            seen_keys.add(identity)
            if row["entity_code"] != source.scope.entity_code:
                raise _refuse(f"{kind} contains another entity.")
            if kind == "WATERFALL" and row["period_key"] != source.scope.period_key:
                raise _refuse("WATERFALL contains another period.")
            currency = row["currency"]
            if re.fullmatch(r"[A-Z]{3}", currency) is None:
                raise _refuse(f"{kind} has no valid currency.")
            if kind == "WATERFALL":
                values = {"REVENUE": _amount(row, "recognised")}
            elif kind == "CONTRACT_BALANCES":
                values = {
                    "CONTRACT_LIABILITY": _amount(row, "contract_liability"),
                    "CONTRACT_ASSET_AND_UNBILLED": (
                        _amount(row, "contract_asset") + _amount(row, "unbilled_receivable")
                    ),
                }
            else:
                if row["section"] == "2":
                    continue  # the frozen RPO producer's exempt obligations
                if row["section"] != "1":
                    raise _refuse("RPO has an unknown section.")
                values = {"RPO": _amount(row, "total")}
            for measure, amount in values.items():
                key = MeasureKey(row["contract_external_id"], currency, measure)
                amounts[key] = amounts.get(key, Fraction(0)) + amount
                contributors.setdefault(key, []).append(row_key)
    return {
        key: Endpoint(amount, tuple(sorted(contributors[key])))
        for key, amount in sorted(amounts.items())
    }


def compare(
    previous: FrozenClose, current: FrozenClose, currency_view: str = "transaction"
) -> dict[str, Any]:
    """Exact contract movements and totals from two verified, ordered LOCK sources."""
    before, after = previous.scope, current.scope
    if before.kind != LockKind.LOCK or after.kind != LockKind.LOCK:
        raise _refuse("both records must be dataset-producing locks.")
    if (before.entity_id, before.book_code, before.period_id) != (
        after.entity_id,
        after.book_code,
        after.period_id,
    ):
        raise _refuse("the locks must belong to one entity, book and period.")
    if (
        before.lock_id == after.lock_id
        or previous.record["created_at"] >= current.record["created_at"]
    ):
        raise _refuse("the later lock must be recorded after the earlier lock.")
    earlier, later = endpoints(previous, currency_view), endpoints(current, currency_view)
    zero = Endpoint(Fraction(0), ())
    rows = []
    totals: dict[tuple[str, str], Fraction] = {}
    for key in sorted(earlier.keys() | later.keys()):
        was, now = earlier.get(key, zero), later.get(key, zero)
        delta = now.amount - was.amount
        if not delta:
            continue
        rows.append(
            {
                "contract_external_id": key.contract_external_id,
                "currency": key.currency,
                "measure": key.measure,
                "earlier_value": exact_decimal_text(was.amount),
                "later_value": exact_decimal_text(now.amount),
                "change": exact_decimal_text(delta),
                "earlier_source_rows": list(was.source_rows),
                "later_source_rows": list(now.source_rows),
            }
        )
        total_key = (key.currency, key.measure)
        totals[total_key] = totals.get(total_key, Fraction(0)) + delta
    return {
        "format": FORMAT,
        "from_period_lock_id": str(before.lock_id),
        "to_period_lock_id": str(after.lock_id),
        "earlier_recorded_at": previous.record["created_at"],
        "later_recorded_at": current.record["created_at"],
        "entity_code": before.entity_code,
        "book": before.book_code,
        "period_key": before.period_key,
        "driver_attribution": "not_computed",
        "sources": [
            {
                "period_lock_id": str(source.scope.lock_id),
                "snapshot_manifest_sha256": source.record["snapshot_manifest_sha256"],
                "datasets": [
                    {
                        "kind": report.dataset.kind,
                        "file_id": str(report.dataset.file_id),
                        "file_sha256": report.dataset.file_sha256,
                    }
                    for report in sorted(source.reports, key=lambda item: item.dataset.kind)
                    if report.dataset.kind in _KEYS
                ],
            }
            for source in (previous, current)
        ],
        "rows": rows,
        "totals": [
            {"currency": currency, "measure": measure, "change": exact_decimal_text(value)}
            for (currency, measure), value in sorted(totals.items())
        ],
    }
