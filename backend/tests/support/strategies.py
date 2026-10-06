"""Hypothesis strategies for the engine properties (dev-guide §9.7 DG-PROP-03; BUILD_SPEC EKC-7).

Every strategy builds exact values: ``int``, ``Fraction`` and ``Decimal``. ``floats()`` is
forbidden (DG-PROP-03); ``tests/engine/support/test_bundle_builders.py`` walks 200 draws of each
strategy through ``guards.no_floats``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from itertools import accumulate

from hypothesis import strategies as st
from support import prop_worlds

# Currencies of every ISO 4217 minor unit the engine meets: 0, 2, 3 and 4.
MINOR_UNITS = {"BHD": 3, "CLF": 4, "JPY": 0, "USD": 2}
MAX_TOTAL_MINOR = 10**12
# Positive weights range from 1 to 10^12, so weight ratios reach 1:10^12.
MAX_WEIGHT = 10**12
MAX_OBLIGATIONS = 200


@dataclass(frozen=True, slots=True)
class AllocationCase:
    """One apportionment: a total in minor units over SSP weights keyed by obligation."""

    currency: str
    minor_unit: int
    total_minor: int
    weights: tuple[Fraction, ...]
    keys: tuple[str, ...]


def obligation_keys(count: int) -> tuple[str, ...]:
    return tuple(f"POB-{index:03d}" for index in range(1, count + 1))


def currencies() -> st.SearchStrategy[str]:
    return st.sampled_from(sorted(MINOR_UNITS))


def _with_positive(others: list[int], positive: int, position: int) -> tuple[Fraction, ...]:
    weights = list(others)
    weights.insert(position % (len(weights) + 1), positive)
    return tuple(Fraction(weight) for weight in weights)


def ssp_weights(max_size: int = MAX_OBLIGATIONS) -> st.SearchStrategy[tuple[Fraction, ...]]:
    """1 to ``max_size`` weights, zeros included, with at least one positive weight."""
    weight = st.one_of(st.just(0), st.integers(1, MAX_WEIGHT))
    return st.builds(
        _with_positive,
        st.lists(weight, max_size=max_size - 1),
        st.integers(1, MAX_WEIGHT),
        st.integers(0, max_size),
    )


def transaction_totals() -> st.SearchStrategy[int]:
    """Positive and negative transaction prices in minor units."""
    return st.integers(-MAX_TOTAL_MINOR, MAX_TOTAL_MINOR)


@st.composite
def allocation_cases(draw: st.DrawFn, max_size: int = MAX_OBLIGATIONS) -> AllocationCase:
    currency = draw(currencies())
    weights = draw(ssp_weights(max_size))
    total = draw(transaction_totals())
    return AllocationCase(
        currency, MINOR_UNITS[currency], total, weights, obligation_keys(len(weights))
    )


@st.composite
def progress_paths(draw: st.DrawFn, max_periods: int = 36) -> tuple[Fraction, ...]:
    """Monotone cumulative progress in [0, 1] that ends exactly at 1."""
    steps = draw(st.lists(st.integers(0, 1000), max_size=max_periods - 1))
    final = draw(st.integers(1, 1000))
    cumulative = list(accumulate([*steps, final]))
    return tuple(Fraction(value, cumulative[-1]) for value in cumulative)


@st.composite
def progress_paths_with_returns(draw: st.DrawFn, max_events: int = 36) -> tuple[Fraction, ...]:
    """Delivered over contracted quantity, where returns lower delivery but never below 0."""
    quantity = draw(st.integers(1, 10_000))
    moves = draw(st.lists(st.integers(-quantity, quantity), max_size=max_events))
    delivered, path = 0, []
    for move in moves:
        delivered = min(max(delivered + move, 0), quantity)
        path.append(Fraction(delivered, quantity))
    path.append(Fraction(1))
    return tuple(path)


@st.composite
def billing_paths(draw: st.DrawFn, max_documents: int = 24) -> tuple[Decimal, ...]:
    """Cumulative billed amounts with two decimals; credit memos lower them, never below 0."""
    movements = draw(st.lists(st.integers(-(10**8), 10**9), min_size=1, max_size=max_documents))
    cumulative, path = 0, []
    for movement in movements:
        cumulative = max(cumulative + movement, 0)
        path.append(Decimal(cumulative).scaleb(-2))
    return tuple(path)


@st.composite
def fx_rate_paths(draw: st.DrawFn, max_periods: int = 24) -> tuple[Decimal, ...]:
    """Positive rates with 12 decimal places (NUMERIC(28,12), D-11), one per period."""
    raw = draw(st.lists(st.integers(1, 10**16), min_size=1, max_size=max_periods))
    return tuple(Decimal(value).scaleb(-12) for value in raw)


def arrival_orders[T](items: Sequence[T]) -> st.SearchStrategy[list[T]]:
    """Permutations of the arrival order of commuting events (research 06 §18.3)."""
    return st.permutations(items)


# --- Compute-level worlds (END-13, END-14) --------------------------------------------------------

MAX_LINE_PRICE = 10**7
MAX_SSP_POINT = 10**6
MAX_MEASURE_DAY = 700
MAX_START_OFFSET = 6
MAX_TERM_MONTHS = 18


@st.composite
def world_specs(
    draw: st.DrawFn,
    *,
    max_contracts: int = 2,
    max_lines: int = 3,
    kinds: Sequence[str] = prop_worlds.KINDS,
) -> prop_worlds.WorldSpec:
    """One or two contracts of 1 to ``max_lines`` lines each, in JPY, USD, BHD or CLF: point-in-time
    goods (1 to 4 units) and ratable ``DAILY`` or ``MONTHLY_EVEN`` services (1 to 18 months,
    starting 0 to 6 months after inception); 0 to 2 deliveries per good within its quantity and
    0 to 2 billings per line within its price, dated on one of 1 to 4 anchor days 0 to 700 days
    after inception, in a drawn arrival order (research 06 §18.3, §18.5)."""
    currency = draw(currencies())
    # a few anchor days per world, so that measure events of different contracts share dates and
    # an interleaving of the contract streams moves commuting arrivals (P8)
    days = st.sampled_from(
        draw(st.lists(st.integers(0, MAX_MEASURE_DAY), min_size=1, max_size=4, unique=True))
    )
    contracts: list[tuple[str, tuple[prop_worlds.LineSpec, ...]]] = []
    pool: list[prop_worlds.MeasureSpec] = []
    for number in range(1, draw(st.integers(1, max_contracts)) + 1):
        contract = f"K-{number}"
        lines: list[prop_worlds.LineSpec] = []
        for index in range(1, draw(st.integers(1, max_lines)) + 1):
            kind = draw(st.sampled_from(sorted(kinds)))
            point_in_time = kind == "PIT"
            line = prop_worlds.LineSpec(
                key=f"POB-{index:02d}",
                kind=kind,
                price=draw(st.integers(1, MAX_LINE_PRICE)),
                ssp=draw(st.integers(1, MAX_SSP_POINT)),
                quantity=draw(st.integers(1, 4)) if point_in_time else 1,
                start_offset=draw(st.integers(0, MAX_START_OFFSET)),
                term_months=0 if point_in_time else draw(st.integers(1, MAX_TERM_MONTHS)),
            )
            lines.append(line)
            if point_in_time:
                remaining_units = line.quantity
                for _ in range(draw(st.integers(0, 2))):
                    if remaining_units == 0:
                        break
                    units = draw(st.integers(1, remaining_units))
                    remaining_units -= units
                    day = draw(days)
                    pool.append(
                        prop_worlds.MeasureSpec(
                            contract, line.key, prop_worlds.DELIVERY, day, units
                        )
                    )
            remaining_amount = line.price
            for _ in range(draw(st.integers(0, 2))):
                if remaining_amount == 0:
                    break
                amount = draw(st.integers(1, remaining_amount))
                remaining_amount -= amount
                day = draw(days)
                pool.append(
                    prop_worlds.MeasureSpec(contract, line.key, prop_worlds.BILLING, day, amount)
                )
        contracts.append((contract, tuple(lines)))
    arrivals = draw(st.permutations(pool))
    return prop_worlds.WorldSpec(currency, tuple(contracts), tuple(arrivals))
