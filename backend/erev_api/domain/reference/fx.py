"""Currencies and FX rates (04 T-REF-08 to T-REF-12, E-51, §15.2 ``missing-fx-rate``; PRD ERR-36;
03 REQ-REF-004 to REQ-REF-006; BUILD_SPEC RFD-3).

A rate for a date resolves from the highest APPROVED version of its set whose coverage contains the
date (T-REF-11): a version chosen by coverage answers for the date whether or not it holds the pair.
When sets of one rate type each answer, the most recently approved version wins (L1-1-Q-29). DRAFT,
SUBMITTED, REJECTED and WITHDRAWN versions are never used (REQ-REF-006, CTL-031). Approving a
version supersedes nothing, because a later version may cover only part of an earlier one.

Entered rates are validated before any write: currencies, the period of a closing or average rate
(its end date is the effective date), the version's coverage and one rate per pair and date. At
submission the inverse of every entered pair without an entered inverse is added with
``is_derived = true``, while the version is still DRAFT, because DB-04 freezes child rows once it
leaves DRAFT (L1-1-Q-30). Inverses are exact fractions rounded half up at twelve places.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Any, Final
from uuid import UUID

from erev_engine.money import round_half_up
from sqlalchemy import Select, and_, exists, func, select
from sqlalchemy.orm import Session

from erev_api.db.tables import currency, fx_rate, fx_rate_set, fx_rate_set_version, period
from erev_api.enums import ConfigStatus, RateType
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.currencies import FxRateIn

RULE_TENANT_CURRENCY: Final = "T-REF-09"
RULE_SET: Final = "T-REF-10"
RULE_VERSION: Final = "T-REF-11"
RULE_RATE: Final = "T-REF-12"
RULE_PERIOD: Final = "T-REF-05"
RULE_LIFECYCLE: Final = "E-12"
RULE_FROZEN: Final = "DB-04"
RULE_MISSING: Final = "FX_RATE_MISSING"  # 04 Table 15.4-E; PRD IMP-81
RATE_PLACES: Final = 12  # TY-03 erev.fx_rate_value NUMERIC(28,12)
SOURCE_MANUAL: Final = "MANUAL"
SOURCE_CSV_IMPORT: Final = "CSV_IMPORT"

TENANT_CURRENCY_OBJECT: Final = "tenant_currency"
TENANT_CURRENCY_CREATE: Final = "tenant_currency.create"
TENANT_CURRENCY_UPDATE: Final = "tenant_currency.update"
SET_OBJECT: Final = "fx_rate_set"
SET_CREATE: Final = "fx_rate_set.create"
VERSION_OBJECT: Final = "fx_rate_set_version"
VERSION_CREATE: Final = "fx_rate_set_version.create"
VERSION_UPDATE: Final = "fx_rate_set_version.update"
VERSION_SUBMIT: Final = "fx_rate_set_version.submit"
VERSION_WITHDRAW: Final = "fx_rate_set_version.withdraw"
RATE_OBJECT: Final = "fx_rate"
RATE_CREATE: Final = "fx_rate.create"
RATE_DELETE: Final = "fx_rate.delete"

# Copy (D-73): errors[].message and problem details.
CURRENCY_UNKNOWN: Final = "Choose an active ISO 4217 currency."
CURRENCY_TWICE: Final = "List each currency once."
REPORTING_KEPT: Final = "The reporting currency {code} stays enabled."
SET_CODE_TAKEN: Final = "Another FX rate set already uses this code."
SOURCE_FORMAT: Final = "Use MANUAL, CSV_IMPORT or a provider code of capital letters and digits."
COVERAGE_ORDER: Final = "The coverage ends on or after the day it starts."
SAME_CURRENCY: Final = "Choose a quote currency other than the base currency."
SPOT_DATE_REQUIRED: Final = "A spot rate needs its effective date."
SPOT_PERIOD: Final = "A spot rate names a day, not a period."
PERIOD_REQUIRED: Final = "A {rate_type} rate needs the key of its period."
PERIOD_UNKNOWN: Final = "No period has the key {key}. Generate its fiscal year first."
PERIOD_AMBIGUOUS: Final = "Periods {key} of several calendars end on different days."
NOT_PERIOD_END: Final = "A {rate_type} rate takes the end date of its period, {end}."
OUTSIDE_COVERAGE: Final = "The effective date lies outside the version's coverage."
RATE_TWICE: Final = "The version already holds a {base} to {quote} rate for {date}."
RATES_REQUIRED: Final = "Add at least one rate before submitting the version."
INVERSE_ZERO: Final = "The inverse of this rate rounds to zero at twelve decimals."
NOT_DRAFT: Final = "Only a draft version changes. This version is {status}."
NOT_SUBMITTABLE: Final = "Only a draft version can be submitted. This version is {status}."
NOT_PENDING: Final = "This version has no pending approval request to withdraw."
# PRD ERR-36 with the rerun target named generically: no contract is known here (L1-1-Q-31).
MISSING_RATE: Final = (
    "No {rate_type} rate from {base} to {quote} for {date}. "
    "Publish the rate, then rerun the affected contracts."
)
PROVIDER_CODE: Final = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def format_rate(value: Decimal) -> str:
    """The stored ``NUMERIC(28,12)`` string: twelve places, no exponent (L1-1-Q-27)."""
    return format(Decimal(value).quantize(Decimal(1).scaleb(-RATE_PLACES)), "f")


def inverse(value: Decimal) -> Decimal:
    """1 / ``value`` rounded half up at twelve places from the exact fraction."""
    return Decimal(round_half_up(1 / Fraction(value), RATE_PLACES)).scaleb(-RATE_PLACES)


def source_errors(source: str) -> list[ProblemError]:
    """T-REF-10 ``source``: ``MANUAL``, ``CSV_IMPORT`` or a provider code."""
    if source and len(source) <= 64 and set(source) <= PROVIDER_CODE and source[0] != "_":
        return []
    return [ProblemError(field="source", rule_id=RULE_SET, message=SOURCE_FORMAT)]


@dataclass(frozen=True, slots=True)
class RateRow:
    """A validated rate of a version."""

    base_currency: str
    quote_currency: str
    effective_date: date
    period_id: UUID | None
    rate: Decimal
    is_derived: bool = False


def active_currencies(session: Session, codes: Sequence[str]) -> set[str]:
    statement = select(currency.c.code).where(
        currency.c.code.in_(sorted(set(codes))), currency.c.is_active.is_(True)
    )
    return {str(code).strip() for code in session.scalars(statement)}


def _period_ends(session: Session, keys: Sequence[str]) -> dict[str, list[tuple[UUID, date]]]:
    found: dict[str, list[tuple[UUID, date]]] = {}
    if not keys:
        return found
    statement = (
        select(period.c.period_key, period.c.id, period.c.end_date)
        .where(period.c.period_key.in_(sorted(set(keys))))
        .order_by(period.c.period_key, period.c.id)
    )
    for key, period_id, end_date in session.execute(statement).tuples():
        found.setdefault(str(key), []).append((UUID(str(period_id)), end_date))
    return found


def rate_rows(
    session: Session,
    *,
    rate_type: RateType,
    coverage_from: date,
    coverage_to: date,
    rates: Sequence[FxRateIn],
    field: str = "rates",
) -> tuple[list[RateRow], list[ProblemError]]:
    """Validate entered rates; every finding is returned with its ``rates.<i>.<member>`` path."""
    errors: list[ProblemError] = []
    active = active_currencies(
        session, [code for item in rates for code in (item.base_currency, item.quote_currency)]
    )
    ends = _period_ends(session, [item.period_key for item in rates if item.period_key])
    rows: list[RateRow] = []
    seen: set[tuple[str, str, date]] = set()
    for index, item in enumerate(rates):
        prefix = f"{field}.{index}"
        found: list[ProblemError] = []

        def finding(
            member: str, message: str, found: list[ProblemError] = found, prefix: str = prefix
        ) -> None:
            found.append(
                ProblemError(field=f"{prefix}.{member}", rule_id=RULE_RATE, message=message)
            )

        for member in ("base_currency", "quote_currency"):
            if getattr(item, member) not in active:
                finding(member, CURRENCY_UNKNOWN)
        if item.base_currency == item.quote_currency:
            finding("quote_currency", SAME_CURRENCY)
        effective = item.effective_date
        period_id: UUID | None = None
        if rate_type is RateType.SPOT:
            if item.period_key is not None:
                finding("period_key", SPOT_PERIOD)
            if effective is None:
                finding("effective_date", SPOT_DATE_REQUIRED)
        elif item.period_key is None:
            finding("period_key", PERIOD_REQUIRED.format(rate_type=rate_type.value))
        else:
            candidates = ends.get(item.period_key, [])
            if not candidates:
                finding("period_key", PERIOD_UNKNOWN.format(key=item.period_key))
            elif len({end for _, end in candidates}) > 1:
                finding("period_key", PERIOD_AMBIGUOUS.format(key=item.period_key))
            else:
                period_id, end = candidates[0]
                if effective is not None and effective != end:
                    message = NOT_PERIOD_END.format(rate_type=rate_type.value, end=end.isoformat())
                    finding("effective_date", message)
                effective = end
        if effective is not None and not coverage_from <= effective <= coverage_to:
            finding("effective_date", OUTSIDE_COVERAGE)
        if not found and effective is not None:
            pair = (item.base_currency, item.quote_currency, effective)
            if pair in seen:
                message = RATE_TWICE.format(base=pair[0], quote=pair[1], date=effective.isoformat())
                finding("effective_date", message)
            seen.add(pair)
        errors += found
        if not found and effective is not None:
            rows.append(
                RateRow(
                    base_currency=item.base_currency,
                    quote_currency=item.quote_currency,
                    effective_date=effective,
                    period_id=period_id,
                    rate=Decimal(item.rate),
                )
            )
    return rows, errors


def derived_inverses(rows: Sequence[RateRow]) -> tuple[list[RateRow], list[int]]:
    """The inverse of each entered pair whose inverse is not entered, and the indexes of the rates
    whose inverse rounds to zero (T-REF-12 ``is_derived``)."""
    entered = {(row.base_currency, row.quote_currency, row.effective_date) for row in rows}
    derived: list[RateRow] = []
    zero: list[int] = []
    for index, row in enumerate(rows):
        if (row.quote_currency, row.base_currency, row.effective_date) in entered:
            continue
        value = inverse(row.rate)
        if value == 0:
            zero.append(index)
            continue
        derived.append(
            RateRow(
                base_currency=row.quote_currency,
                quote_currency=row.base_currency,
                effective_date=row.effective_date,
                period_id=row.period_id,
                rate=value,
                is_derived=True,
            )
        )
    return derived, zero


def _effective_rates() -> Any:
    """Rates of APPROVED versions that no higher APPROVED version of the same set covers, ranked
    across sets by publication (``resolution_rank = 1`` is in force)."""
    version = fx_rate_set_version
    later = fx_rate_set_version.alias("later_version")
    covered_later = exists().where(
        later.c.tenant_id == version.c.tenant_id,
        later.c.fx_rate_set_id == version.c.fx_rate_set_id,
        later.c.status == ConfigStatus.APPROVED.value,
        later.c.version_no > version.c.version_no,
        later.c.coverage_from <= fx_rate.c.effective_date,
        later.c.coverage_to >= fx_rate.c.effective_date,
    )
    rank = func.row_number().over(
        partition_by=(
            fx_rate.c.rate_type,
            fx_rate.c.base_currency,
            fx_rate.c.quote_currency,
            fx_rate.c.effective_date,
        ),
        order_by=(version.c.published_at.desc(), version.c.id.desc()),
    )
    joined = (
        fx_rate.join(
            version,
            and_(
                version.c.tenant_id == fx_rate.c.tenant_id,
                version.c.id == fx_rate.c.fx_rate_set_version_id,
            ),
        )
        .join(
            fx_rate_set,
            and_(
                fx_rate_set.c.tenant_id == version.c.tenant_id,
                fx_rate_set.c.id == version.c.fx_rate_set_id,
            ),
        )
        .outerjoin(
            period,
            and_(period.c.tenant_id == fx_rate.c.tenant_id, period.c.id == fx_rate.c.period_id),
        )
    )
    return (
        select(
            fx_rate.c.id,
            fx_rate.c.rate_type,
            fx_rate.c.base_currency,
            fx_rate.c.quote_currency,
            fx_rate.c.effective_date,
            fx_rate.c.period_id,
            period.c.period_key,
            fx_rate.c.rate,
            fx_rate.c.is_derived,
            fx_rate_set.c.id.label("fx_rate_set_id"),
            fx_rate_set.c.code.label("fx_rate_set_code"),
            version.c.id.label("fx_rate_set_version_id"),
            version.c.version_no,
            version.c.published_at,
            rank.label("resolution_rank"),
        )
        .select_from(joined)
        .where(
            version.c.status == ConfigStatus.APPROVED.value,
            version.c.coverage_from <= fx_rate.c.effective_date,
            version.c.coverage_to >= fx_rate.c.effective_date,
            ~covered_later,
        )
        .subquery("effective_fx_rate")
    )


EFFECTIVE_RATES: Final = _effective_rates()


def effective_rates_select() -> Select[Any]:
    """The rates in force, one per rate type, pair and date (``GET /fx-rates``)."""
    columns = [column for column in EFFECTIVE_RATES.c if column.name != "resolution_rank"]
    return select(*columns).where(EFFECTIVE_RATES.c.resolution_rank == 1)


def period_end_date(session: Session, period_key: str) -> date:
    """The end date of the periods named ``period_key``; 422 when none or several differ."""
    ends = sorted(
        {
            end
            for end in session.scalars(
                select(period.c.end_date).where(period.c.period_key == period_key)
            )
        }
    )
    if len(ends) == 1:
        end: date = ends[0]
        return end
    message = (PERIOD_UNKNOWN if not ends else PERIOD_AMBIGUOUS).format(key=period_key)
    error = ProblemError(field="period_key", rule_id=RULE_PERIOD, message=message)
    raise Problem("validation-failed", errors=[error])


def missing_rate(rate_type: RateType, base: str, quote: str, on: date) -> Problem:
    """422 ``missing-fx-rate`` naming the rate type, the pair and the date (ERR-36)."""
    message = MISSING_RATE.format(
        rate_type=rate_type.value, base=base, quote=quote, date=on.isoformat()
    )
    error = ProblemError(field="rate", rule_id=RULE_MISSING, message=message)
    return Problem("missing-fx-rate", message, errors=[error])


def rate(
    session: Session,
    *,
    rate_type: RateType | str,
    base: str,
    quote: str,
    period_key: str | None = None,
    on: date | None = None,
) -> Decimal:
    """The rate in force for ``base`` → ``quote``: spot rates by day (``on``), closing and average
    rates by period (``period_key``, resolved to its end date) or by that end date. A pair of equal
    currencies is 1. Raises 422 ``missing-fx-rate`` when no APPROVED version answers."""
    kind = RateType(rate_type)
    if (period_key is None) == (on is None):
        raise ValueError("rate needs exactly one of period_key and on")
    effective = on if on is not None else period_end_date(session, str(period_key))
    if base == quote:
        return Decimal(10**RATE_PLACES).scaleb(-RATE_PLACES)
    statement = select(EFFECTIVE_RATES.c.rate).where(
        EFFECTIVE_RATES.c.resolution_rank == 1,
        EFFECTIVE_RATES.c.rate_type == kind.value,
        EFFECTIVE_RATES.c.base_currency == base,
        EFFECTIVE_RATES.c.quote_currency == quote,
        EFFECTIVE_RATES.c.effective_date == effective,
    )
    found = session.execute(statement).scalar_one_or_none()
    if found is None:
        raise missing_rate(kind, base, quote, effective)
    return Decimal(found)
