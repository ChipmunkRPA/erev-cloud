"""Royalty-bearing obligations and their realised royalties (ENGINE_SPEC S04-R-06; ENGINE_SPEC_B
S09-R-01, S09-R-02, §9.2.9 S09-R-32, S09-R-33; POL-056, POL-057; ENC-8).

A stage-neutral kernel helper, like ``billing_identity``: stage 04 prices realised royalties into
the transaction price, stage 05 opens the ``ROYALTY`` recognition component and stage 09 recognises
it, and all three read one predicate and one realisation here, so that the transaction price and
the recognition target carry the same amounts at every date (S09-R-02; 04 DB-17 V1).

An obligation bears royalties when its recognition method is ``ROYALTY`` (E-11), when a
``USAGE_REPORTED`` event with ``is_royalty_statement = true`` names it, or when a
``ROYALTY_ACCRUAL`` estimate element of its contract targets it (ARCHITECTURE §3.6.6; the royalty
rows of POLICIES table 1.4-A). Realised royalties at a date and ENG-06 position are the latest
statement per usage period whose period ended by the date, plus, under POL-056 ``ACCRUE_ESTIMATE``,
the ``ROYALTY_ACCRUAL`` version in force for every ended usage period that no statement covers
(S09-R-32: a statement replaces every accrual whose usage period lies within it). Amounts are
exact ``Fraction`` currency units (CV-30). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from erev_engine.bundle import EstimateVersionInput
from erev_engine.money import to_fraction

if TYPE_CHECKING:  # the kernel reads stage state by attribute only (DG-ARC-02 layering)
    from erev_engine.stages.state import EstimatePins, EventView, OrderKey

__all__ = [
    "ACCRUAL_KIND",
    "ACCRUE_ESTIMATE",
    "FIXED_ON_LICENCE_PATTERN",
    "GUARANTEE_POLICY",
    "ROYALTY_METHOD",
    "STATEMENT_MEMBER",
    "UNREPORTED_SALES_POLICY",
    "Accrual",
    "Realisation",
    "Statement",
    "accruals",
    "bearing",
    "contract_wide_accrual",
    "covers",
    "is_statement",
    "names_obligation",
    "realised",
    "statements",
]

ROYALTY_METHOD: Final = "ROYALTY"  # E-11
ACCRUAL_KIND: Final = "ROYALTY_ACCRUAL"  # E-09
STATEMENT_MEMBER: Final = "is_royalty_statement"  # 04 §16.3 USAGE_REPORTED
UNREPORTED_SALES_POLICY: Final = "royalty.unreported_sales"  # POL-056
GUARANTEE_POLICY: Final = "royalty.minimum_guarantee"  # POL-057
ACCRUE_ESTIMATE: Final = "ACCRUE_ESTIMATE"
FIXED_ON_LICENCE_PATTERN: Final = "FIXED_ON_LICENCE_PATTERN"
_KEY_ESCAPES: Final[Mapping[str, str]] = MappingProxyType(
    {"%": "%25", "/": "%2F", "@": "%40", "#": "%23", ":": "%3A"}
)  # CV-21


@dataclass(frozen=True, slots=True)
class Statement:
    """One royalty statement counted at a date: the latest for its usage period (S09-R-32)."""

    event: EventView
    start: date  # usage_period_start
    end: date  # usage_period_end
    amount: Fraction  # rated_amount, currency units


@dataclass(frozen=True, slots=True)
class Accrual:
    """The ``ROYALTY_ACCRUAL`` version in force for a usage period no statement covers."""

    version: EstimateVersionInput
    start: date  # parameters.usage_period_start_date
    end: date  # parameters.usage_period_end_date
    member: str  # the version member that gives the amount
    amount: Fraction  # currency units


@dataclass(frozen=True, slots=True)
class Realisation:
    """Realised royalties of one obligation at a date and position (S04-R-06; §9.2.9 ``CR``)."""

    statements: tuple[Statement, ...]  # by (start, end)
    accruals: tuple[Accrual, ...]  # uncovered usage periods, by (start, end)

    @property
    def total(self) -> Fraction:
        """CR: Σ statements + Σ uncovered accruals, currency units."""
        amounts = [item.amount for item in self.statements]
        amounts.extend(item.amount for item in self.accruals)
        return sum(amounts, Fraction(0))


def _encode(component: str) -> str:
    return "".join(_KEY_ESCAPES.get(character, character) for character in component)


def _date(value: object) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _amount(value: object) -> Fraction | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str | int | Decimal | Fraction):
        return to_fraction(value)
    return None


def _admits(order_key: OrderKey, cutoff: OrderKey | None, inclusive: bool) -> bool:
    if cutoff is None:
        return True
    return order_key <= cutoff if inclusive else order_key < cutoff


def is_statement(event: EventView) -> bool:
    """A ``USAGE_REPORTED`` with ``is_royalty_statement = true`` (04 §16.3)."""
    return event.event_type == "USAGE_REPORTED" and event.payload.get(STATEMENT_MEMBER) in (
        True,
        "true",
    )


def names_obligation(
    event: EventView, contract_key: str, obligation_key: str, subject_key: str
) -> bool:
    """The event names the obligation by subject key or payload ``obligation_key``."""
    if subject_key in event.obligation_subject_keys:
        return True
    return event.contract_key == contract_key and event.payload.get("obligation_key") == (
        obligation_key
    )


def _targets(version: EstimateVersionInput, contract_key: str, obligation_key: str) -> bool:
    """A ``ROYALTY_ACCRUAL`` element of the contract naming the obligation (T-CON-12)."""
    if version.estimate_kind != ACCRUAL_KIND:
        return False
    if not version.estimate_key.startswith(f"{_encode(contract_key)}/"):
        return False
    return version.obligation_key == obligation_key or (
        obligation_key in version.target_obligation_keys
    )


def bearing(
    method: str,
    contract_key: str,
    obligation_key: str,
    subject_key: str,
    measure_events: Iterable[EventView],
    pins: EstimatePins,
) -> bool:
    """Whether the obligation carries the ``ROYALTY`` recognition component (S09-R-01).

    Method ``ROYALTY``; or any royalty statement of the stream naming the obligation; or any
    ``ROYALTY_ACCRUAL`` element of the contract targeting it. The whole stream is read, so the
    component exists from inception and its trace nodes are stable across positions (S09-INV-12).
    """
    if method == ROYALTY_METHOD:
        return True
    if contract_wide_accrual(pins, contract_key):
        # D-88 L7-5-Q-8: the contract's royalties are variable consideration of the contract
        # (32-40(b) fails; EX-05-D), priced and reallocated by the contract-wide element, not a
        # component of the obligation a statement happens to name.
        return False
    if any(
        is_statement(event) and names_obligation(event, contract_key, obligation_key, subject_key)
        for event in measure_events
    ):
        return True
    return any(
        _targets(pin.version, contract_key, obligation_key)
        for versions in pins.pins.values()
        for pin in versions
    )


def contract_wide_accrual(pins: EstimatePins, contract_key: str) -> bool:
    """A ``ROYALTY_ACCRUAL`` element of the contract with ``allocation_target = CONTRACT`` and no
    obligation target: the D-88 L7-5-Q-8 variable-consideration route (S04-R-06 extension)."""
    prefix = f"{_encode(contract_key)}/"
    return any(
        pin.version.estimate_kind == ACCRUAL_KIND
        and pin.version.estimate_key.startswith(prefix)
        and pin.version.allocation_target == "CONTRACT"
        and pin.version.obligation_key is None
        and not pin.version.target_obligation_keys
        for versions in pins.pins.values()
        for pin in versions
    )


def statements(
    measure_events: Iterable[EventView],
    contract_key: str,
    obligation_key: str,
    subject_key: str,
    *,
    at: date,
    cutoff: OrderKey | None = None,
    inclusive: bool = True,
) -> tuple[Statement, ...]:
    """The latest statement per usage period, admitted at ``at`` and before ``cutoff``, whose
    ``usage_period_end`` is on or before ``at`` (S04-R-06; S09-R-32). A statement without its
    period dates or amount is malformed (``ValueError``, CV-45)."""
    latest: dict[tuple[date, date], Statement] = {}
    for event in measure_events:
        if not is_statement(event):
            continue
        if not names_obligation(event, contract_key, obligation_key, subject_key):
            continue
        if event.effective_date > at or not _admits(event.order_key, cutoff, inclusive):
            continue
        start = _date(event.payload.get("usage_period_start"))
        end = _date(event.payload.get("usage_period_end"))
        amount = _amount(event.payload.get("rated_amount"))
        if start is None or end is None or amount is None:
            raise ValueError(
                f"{event.event_key}: a royalty statement carries usage_period_start, "
                "usage_period_end and rated_amount (CV-45)"
            )
        if end > at:
            continue
        found = latest.get((start, end))
        if found is None or event.order_key > found.event.order_key:
            latest[(start, end)] = Statement(event, start, end, amount)
    return tuple(latest[key] for key in sorted(latest))


def covers(start: date, end: date, found: Sequence[Statement]) -> bool:
    """A statement whose usage period contains [``start``, ``end``] (S09-R-32)."""
    return any(item.start <= start and end <= item.end for item in found)


def accruals(
    pins: EstimatePins,
    contract_key: str,
    obligation_key: str,
    *,
    at: date,
    cutoff: OrderKey | None = None,
    inclusive: bool = True,
    covered_by: Sequence[Statement] = (),
) -> tuple[Accrual, ...]:
    """The ``ROYALTY_ACCRUAL`` version in force per usage period ended by ``at``, no statement of
    ``covered_by`` covering it (S04-R-06; S09-R-32).

    A version is in force when its effective date is on or before ``at`` and the event that
    applied it precedes ``cutoff`` (S01-R-18); the greatest (effective date, version number) per
    usage period wins. The amount is ``constrained_amount`` when present, else
    ``expected_total_amount`` (the estimated royalties on occurred sales; ARCHITECTURE §3.6.6).
    """
    in_force: dict[tuple[date, date], Accrual] = {}
    for versions in pins.pins.values():
        for pin in versions:
            version = pin.version
            if not _targets(version, contract_key, obligation_key):
                continue
            if version.effective_date > at or not _admits(pin.event_order_key, cutoff, inclusive):
                continue
            start = _date(version.parameters.get("usage_period_start_date"))
            end = _date(version.parameters.get("usage_period_end_date"))
            if start is None or end is None:
                raise ValueError(
                    f"{version.version_key}: a ROYALTY_ACCRUAL version carries "
                    "usage_period_start_date and usage_period_end_date (T-CON-13)"
                )
            if end > at or covers(start, end, covered_by):
                continue
            if version.constrained_amount is not None:
                member, raw = "constrained_amount", to_fraction(version.constrained_amount)
            elif version.expected_total_amount is not None:
                member, raw = "expected_total_amount", to_fraction(version.expected_total_amount)
            else:
                continue
            found = in_force.get((start, end))
            if found is None or (version.effective_date, version.version_no) > (
                found.version.effective_date,
                found.version.version_no,
            ):
                in_force[(start, end)] = Accrual(version, start, end, member, raw)
    return tuple(in_force[key] for key in sorted(in_force))


def realised(
    measure_events: Iterable[EventView],
    pins: EstimatePins,
    contract_key: str,
    obligation_key: str,
    subject_key: str,
    *,
    at: date,
    cutoff: OrderKey | None = None,
    inclusive: bool = True,
    accrue: bool,
) -> Realisation:
    """Statements and, under POL-056 ``ACCRUE_ESTIMATE`` (``accrue``), the uncovered accruals."""
    found = statements(
        measure_events,
        contract_key,
        obligation_key,
        subject_key,
        at=at,
        cutoff=cutoff,
        inclusive=inclusive,
    )
    if not accrue:
        return Realisation(found, ())
    accrued = accruals(
        pins,
        contract_key,
        obligation_key,
        at=at,
        cutoff=cutoff,
        inclusive=inclusive,
        covered_by=found,
    )
    return Realisation(found, accrued)
