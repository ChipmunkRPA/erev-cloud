"""Independent legacy monthly outputs from retained Contract_Live history (RPT-42).

Only this compatibility projection uses binary64 arithmetic: four-place component
rounding, two-place pre-filter, compensated group sum, and two-place final rounding.
The resulting cents enter the exact comparison layer. No eRev engine output is used.
Source authorization, file integrity and migration entity mapping belong to the reader.
"""

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any

from erev_engine.canonical import sha256_hex

from erev_api.domain.migration.legacy_db import LegacyRow, latest_rows
from erev_api.domain.reports.parallel_comparison import Balance, Journal, Period, Snapshot
from erev_api.domain.reports.tie_outs import minor_unit
from erev_api.problems import Problem


def _refuse(detail: str) -> Problem:
    return Problem("validation-failed", f"Legacy parallel-run source: {detail}")


def _number(row: LegacyRow, column: str) -> float:
    raw = row.values.get(column)
    try:
        number = float(raw) if raw is not None and raw != "" else math.nan
    except (ValueError, OverflowError) as error:
        raise _refuse(f"row {row.source_rowid} has an invalid {column}.") from error
    if not math.isfinite(number):
        raise _refuse(f"row {row.source_rowid} has no finite {column}.")
    return number


def _rounded(value: float, places: int) -> float:
    # Array-style binary64 scale/rint/unscale, not Python round(value, places).
    scale = float(10**places)
    scaled = value * scale
    if not math.isfinite(scaled) or abs(scaled) >= 2**52:
        raise _refuse("an amount exceeds the supported binary64 rounding range.")
    return round(scaled) / scale


def _sum(values: Iterable[float]) -> float:
    total = 0.0
    correction = 0.0
    for value in values:
        adjusted = value - correction
        updated = total + adjusted
        correction = (updated - total) - adjusted
        total = updated
    return total


def _cents(value: float) -> Decimal:
    return Decimal(format(_rounded(value, 2), ".2f"))


def _ref(row: LegacyRow) -> str:
    return f"legacy-row:{row.source_rowid}:{row.sha256}"


def snapshot(
    history: Iterable[LegacyRow],
    *,
    source_id: str,
    periods: Iterable[Period],
    entity_mapping: Mapping[str, str],
) -> Snapshot:
    """Project complete requested periods through the last source economic date.

    Source currency is the migration's reporting currency, supplied in Period. The
    legacy format has no currency column. A contract spanning selling entities is
    refused because its legacy consolidated journal cannot be attributed reliably.
    Periods after the last source date are not declared as zero-activity outputs.
    """
    if not source_id:
        raise _refuse("a retained source identity is required.")
    records = tuple(sorted(history, key=lambda row: row.source_rowid))
    if len({row.source_rowid for row in records}) != len(records):
        raise _refuse("source row identities are duplicated.")
    row_refs = {row.source_rowid: _ref(row) for row in records}
    dates = []
    contract_entities: dict[str, set[str]] = defaultdict(set)
    for row in records:
        if row.current_period is None or not row.record_key or not row.contract_external_id:
            raise _refuse(f"row {row.source_rowid} has no valid period or contract identity.")
        dates.append(row.current_period)
        selling = row.values.get("Selling Entity") or ""
        if selling not in entity_mapping:
            raise _refuse(f"selling entity {selling!r} has no migration mapping.")
        contract_entities[row.contract_external_id].add(entity_mapping[selling])
    if any(len(entities) != 1 for entities in contract_entities.values()):
        raise _refuse("a contract spans multiple selling entities.")
    requested = tuple(sorted(periods))
    if len(set(requested)) != len(requested):
        raise _refuse("requested periods are duplicated.")
    # This legacy journal format is explicitly two-decimal, including its zero filter.
    if len({p.currency for p in requested}) > 1:
        raise _refuse("the legacy source has one reporting currency, not per-row currencies.")
    if any(
        p.book_code != "ASC606" or p.entity_code not in entity_mapping.values() for p in requested
    ):
        raise _refuse("requested periods must belong to mapped entities and the ASC606 book.")
    if any(minor_unit(p.currency) != 2 for p in requested):
        raise _refuse("legacy journals require a two-decimal reporting currency.")
    valid = frozenset(p for p in requested if dates and p.end <= max(dates) and p.end >= min(dates))
    journals = []
    balances = []
    for period in sorted(valid):
        scoped = [
            r
            for r in records
            if entity_mapping[r.values["Selling Entity"] or ""] == period.entity_code
        ]
        selected = [
            r
            for r in scoped
            if r.current_period is not None and period.start <= r.current_period <= period.end
        ]
        # Component-major ordering preserves the original concatenation order before groupby.
        components = (
            ("Current Rev Rec", "Deferred Revenue Account", 1, False),
            ("Current Rev Rec", "Revenue Account", -1, True),
            ("Previous Reclass to UAR", "Deferred Revenue Account", 1, False),
            ("Previous Reclass to UAR", "Unbilled A/R Account", -1, False),
            ("Current Reclass to UAR", "Deferred Revenue Account", -1, False),
            ("Current Reclass to UAR", "Unbilled A/R Account", 1, False),
        )
        values: dict[tuple[str, str], list[float]] = defaultdict(list)
        references: dict[tuple[str, str], set[str]] = defaultdict(set)
        for measure, account_column, sign, obligation in components:
            for row in selected:
                amount = sign * _rounded(_number(row, measure), 4)
                if _rounded(amount, 2) == 0:
                    continue
                raw_account = row.values.get(account_column)
                if not raw_account:
                    raise _refuse(f"row {row.source_rowid} has no {account_column}.")
                try:
                    account_number = Decimal(raw_account)
                except InvalidOperation as error:
                    raise _refuse("a legacy account code is not numeric.") from error
                if (
                    not account_number.is_finite()
                    or account_number != account_number.to_integral_value()
                    or account_number.copy_abs() > 2**63 - 1
                ):
                    raise _refuse("legacy account codes must be integral numbers.")
                account = str(int(account_number))
                key = (row.record_key if obligation else row.contract_external_id, account)
                values[key].append(amount)
                references[key].add(row_refs[row.source_rowid])
        by_account: dict[str, list[Decimal]] = defaultdict(list)
        account_refs: dict[str, set[str]] = defaultdict(set)
        for key, amounts in sorted(values.items()):
            rounded_amount = _cents(_sum(amounts))
            if rounded_amount == 0:
                continue
            by_account[key[1]].append(rounded_amount)
            account_refs[key[1]].update(references[key])
        for account, cents in sorted(by_account.items()):
            # Summing final cents exactly cannot alter the legacy displayed line amounts.
            debit = sum((Fraction(v) for v in cents if v > 0), Fraction())
            credit = -sum((Fraction(v) for v in cents if v < 0), Fraction())

            def decimal_cents(value: Fraction) -> Decimal:
                integer = value.numerator * (100 // value.denominator)
                return Decimal(f"{integer // 100}.{integer % 100:02d}")

            journals.append(
                Journal(
                    period,
                    account,
                    decimal_cents(debit),
                    decimal_cents(credit),
                    tuple(sorted(account_refs[account])),
                )
            )
        before_end = [
            r for r in scoped if r.current_period is not None and r.current_period <= period.end
        ]
        latest = latest_rows(before_end)
        by_contract: dict[str, list[LegacyRow]] = defaultdict(list)
        for row in latest:
            by_contract[row.contract_external_id].append(row)
        for contract, rows in sorted(by_contract.items()):
            # Sum obligation positions; the contract-level legacy field is repeated on every POB.
            position = _sum(_number(row, "Current Contract Position - POB") for row in rows)
            balances.append(
                Balance(
                    period,
                    contract,
                    _cents(position),
                    tuple(row_refs[r.source_rowid] for r in rows),
                )
            )
    facts: dict[str, Any] = {
        "version": 1,
        "source_id": source_id,
        "rows": [{"rowid": r.source_rowid, "sha256": r.sha256} for r in records],
        "entity_mapping": dict(sorted(entity_mapping.items())),
        "requested_periods": [
            {
                "entity": p.entity_code,
                "book": p.book_code,
                "currency": p.currency,
                "key": p.key,
                "start": p.start.isoformat(),
                "end": p.end.isoformat(),
            }
            for p in requested
        ],
    }
    return Snapshot(source_id, sha256_hex(facts), valid, tuple(journals), tuple(balances))
