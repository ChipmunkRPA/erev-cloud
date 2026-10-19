"""RPT-42 comparison of independently produced monthly journal and balance facts.

Source readers must authorize and retain both inputs before calling this module.
This module neither reconstructs legacy journals using the eRev engine nor treats
an unavailable period as a zero-valued source. The report adapter retains both inputs.
"""

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Any, Final

from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import minor_unit
from erev_api.problems import Problem

CODE: Final = "parallel_run_comparison"
COLUMNS: Final = (
    Column("section_label", "Section", "text"),
    Column("entity_code", "Entity", "code"),
    Column("book_code", "Book", "code"),
    Column("period_key", "Period", "code"),
    Column("period_end", "Period end", "date"),
    Column("account", "Account", "code"),
    Column("contract_external_id", "Contract", "code"),
    Column("currency", "Currency", "code"),
    Column("legacy_debit", "Legacy debit", "money"),
    Column("legacy_credit", "Legacy credit", "money"),
    Column("erev_debit", "eRev debit", "money"),
    Column("erev_credit", "eRev credit", "money"),
    Column("legacy_net_position", "Legacy billed less recognized", "money"),
    Column("contract_liability", "eRev contract liability", "money"),
    Column("contract_asset_and_unbilled", "eRev contract asset and unbilled receivable", "money"),
    Column("difference", "Difference", "money"),
)
MEASURES: Final = {
    1: ("legacy_debit", "legacy_credit", "erev_debit", "erev_credit", "difference"),
    2: ("legacy_net_position", "contract_liability", "contract_asset_and_unbilled", "difference"),
}


@dataclass(frozen=True, order=True)
class Period:
    """One complete entity/book/currency period population, including zero activity."""

    entity_code: str
    book_code: str
    currency: str
    key: str
    start: date
    end: date


@dataclass(frozen=True)
class Journal:
    period: Period
    account: str
    debit: Decimal
    credit: Decimal
    source_rows: tuple[str, ...]


@dataclass(frozen=True)
class Balance:
    period: Period
    contract: str
    # Legacy: billed less recognized. eRev: liability less asset and unbilled.
    net_position: Decimal
    source_rows: tuple[str, ...]
    liability: Decimal | None = None
    asset_and_unbilled: Decimal | None = None


@dataclass(frozen=True)
class Snapshot:
    source_id: str
    sha256: str
    periods: frozenset[Period]
    journals: tuple[Journal, ...]
    balances: tuple[Balance, ...]


@dataclass(frozen=True)
class Comparison:
    data: ReportData
    evidence: Mapping[str, Any]


def _refuse(detail: str) -> Problem:
    return Problem("validation-failed", f"Parallel-run comparison: {detail}")


def _amount(value: Decimal, currency: str) -> Fraction:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise _refuse("a source amount must be a finite decimal.")
    result = Fraction(value)
    if (result * 10 ** minor_unit(currency)).denominator != 1:
        raise _refuse("a source amount is not in currency minor units.")
    return result


def _money(value: Fraction, currency: str) -> dict[str, str]:
    places = minor_unit(currency)
    integer = value * 10**places
    if integer.denominator != 1:
        raise _refuse("a comparison amount requires rounding.")
    digits = str(abs(integer.numerator)).rjust(places + 1, "0")
    rendered = digits if places == 0 else digits[:-places] + "." + digits[-places:]
    return {"amount": ("-" if value < 0 else "") + rendered, "currency": currency}


def _index(snapshot: Snapshot, *, actual: bool) -> tuple[dict[Any, Journal], dict[Any, Balance]]:
    if (
        not snapshot.source_id
        or len(snapshot.sha256) != 64
        or any(char not in "0123456789abcdef" for char in snapshot.sha256)
    ):
        raise _refuse("a retained source identity and SHA-256 are required.")
    identities = set()
    for period in snapshot.periods:
        identity = period.entity_code, period.book_code, period.currency, period.key
        if not all(identity) or identity in identities or period.start > period.end:
            raise _refuse("source period coverage is ambiguous.")
        identities.add(identity)
    journals = {}
    for row in snapshot.journals:
        key = row.period, row.account
        if row.period not in snapshot.periods or not row.account or key in journals:
            raise _refuse("journal account rows are duplicated or outside source coverage.")
        if not row.source_rows or any(not key for key in row.source_rows):
            raise _refuse("journal source-row references are missing.")
        if (
            min(_amount(row.debit, row.period.currency), _amount(row.credit, row.period.currency))
            < 0
        ):
            raise _refuse("debit and credit columns must be nonnegative.")
        journals[key] = row
    balances = {}
    for balance in snapshot.balances:
        key = balance.period, balance.contract
        if balance.period not in snapshot.periods or not balance.contract or key in balances:
            raise _refuse("contract balance rows are duplicated or outside source coverage.")
        if not balance.source_rows or any(not key for key in balance.source_rows):
            raise _refuse("balance source-row references are missing.")
        net = _amount(balance.net_position, balance.period.currency)
        if actual:
            if balance.liability is None or balance.asset_and_unbilled is None:
                raise _refuse("eRev balance components are missing.")
            liability = _amount(balance.liability, balance.period.currency)
            asset = _amount(balance.asset_and_unbilled, balance.period.currency)
            if min(liability, asset) < 0 or liability - asset != net:
                raise _refuse("eRev balance components do not reconcile to its net position.")
        balances[key] = balance
    return journals, balances


def compare(legacy: Snapshot, actual: Snapshot) -> Comparison:
    """Exact signed differences, eRev minus legacy, without any balancing plug.

    A declared complete period permits an absent account/contract to mean zero.
    A period absent from either source is excluded, with coverage retained in evidence.
    Entity/book dimensions remain separate; totals are per section and currency.
    """
    old_journals, old_balances = _index(legacy, actual=False)
    new_journals, new_balances = _index(actual, actual=True)
    # Equal period identifiers must mean the same calendar boundaries on both sides.
    old_dates = {
        (p.entity_code, p.book_code, p.currency, p.key): (p.start, p.end) for p in legacy.periods
    }
    for p in actual.periods:
        prior = old_dates.get((p.entity_code, p.book_code, p.currency, p.key))
        if prior is not None and prior != (p.start, p.end):
            raise _refuse("the sources disagree on period boundaries.")
    periods = legacy.periods & actual.periods
    rows: list[dict[str, Any]] = []
    contributors: dict[str, Any] = {}
    totals: dict[tuple[int, str], dict[str, Fraction]] = defaultdict(lambda: defaultdict(Fraction))
    # Keep the specified simple keys for a single entity/book/currency, qualify otherwise.
    dimensions = {(p.entity_code, p.book_code, p.currency) for p in periods}

    def row_key(prefix: str, period: Period, member: str) -> str:
        # Length prefixes on qualified dimensions avoid delimiter collisions.
        base = (
            f"{prefix}:{period.key}:{member}"
            if prefix == "je"
            else f"{prefix}:{member}:{period.key}"
        )
        if len(dimensions) > 1:
            base += ":" + ":".join(
                f"{len(v)}:{v}"
                for v in (
                    period.entity_code,
                    period.book_code,
                    period.currency,
                )
            )
        return base

    def emit(
        section: int,
        p: Period,
        member: str,
        values: Mapping[str, Fraction],
        before: Journal | Balance | None,
        after: Journal | Balance | None,
    ) -> None:
        key = row_key("je" if section == 1 else "balance", p, member)
        if key in contributors:
            raise _refuse("comparison row identities collide.")
        rows.append(
            {
                "row_key": key,
                "section": section,
                "section_label": "Journal lines by account"
                if section == 1
                else "Contract balances",
                "entity_code": p.entity_code,
                "book_code": p.book_code,
                "period_key": p.key,
                "period_end": p.end,
                "currency": p.currency,
                "account" if section == 1 else "contract_external_id": member,
                **{name: _money(value, p.currency) for name, value in values.items()},
            }
        )
        contributors[key] = {
            "legacy": [] if before is None else list(before.source_rows),
            "erev": [] if after is None else list(after.source_rows),
        }
        for name, value in values.items():
            totals[(section, p.currency)][name] += value

    for p, account in sorted(old_journals.keys() | new_journals.keys()):
        if p not in periods:
            continue
        old, new = old_journals.get((p, account)), new_journals.get((p, account))
        values = {
            f"{side}_{field}": Fraction(0)
            if record is None
            else _amount(getattr(record, field), p.currency)
            for side, record in (("legacy", old), ("erev", new))
            for field in ("debit", "credit")
        }
        values["difference"] = (
            values["erev_debit"]
            - values["erev_credit"]
            - values["legacy_debit"]
            + values["legacy_credit"]
        )
        emit(1, p, account, values, old, new)
    for p, contract in sorted(old_balances.keys() | new_balances.keys()):
        if p not in periods:
            continue
        was, now = old_balances.get((p, contract)), new_balances.get((p, contract))
        old_net = Fraction(0) if was is None else _amount(was.net_position, p.currency)
        liability = Fraction(0) if now is None else _amount(now.liability, p.currency)  # type: ignore[arg-type]
        asset = Fraction(0) if now is None else _amount(now.asset_and_unbilled, p.currency)  # type: ignore[arg-type]
        emit(
            2,
            p,
            contract,
            {
                "legacy_net_position": old_net,
                "contract_liability": liability,
                "contract_asset_and_unbilled": asset,
                "difference": liability - asset - old_net,
            },
            was,
            now,
        )
    controls = {}
    for (section, currency), values in sorted(totals.items()):
        formatted = {key: _money(values[key], currency) for key in MEASURES[section]}
        rows.append(
            {
                "row_key": f"TOTAL:{currency}:{section}",
                "section": section,
                "section_label": "Journal lines by account"
                if section == 1
                else "Contract balances",
                "account" if section == 1 else "contract_external_id": "Total",
                "currency": currency,
                **formatted,
            }
        )
        controls[f"{section}:{currency}"] = {
            key: value["amount"] for key, value in formatted.items()
        }
    for row in rows:
        for column in COLUMNS:
            row.setdefault(column.key, None)

    def coverage(source: Snapshot) -> list[dict[str, str]]:
        return [
            {
                "entity": p.entity_code,
                "book": p.book_code,
                "currency": p.currency,
                "period": p.key,
                "start": p.start.isoformat(),
                "end": p.end.isoformat(),
            }
            for p in sorted(source.periods)
        ]

    return Comparison(
        ReportData(COLUMNS, tuple(rows), controls),
        {
            "version": 1,
            "legacy_source": {
                "id": legacy.source_id,
                "sha256": legacy.sha256,
                "coverage": coverage(legacy),
            },
            "erev_source": {
                "id": actual.source_id,
                "sha256": actual.sha256,
                "coverage": coverage(actual),
            },
            "compared_periods": len(periods),
            "contributors": contributors,
        },
    )
