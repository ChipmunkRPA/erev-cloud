"""Money kernel: quantisation, apportionment and formatting (dev-guide §5.9; POLICIES ALG-01).

Exact amounts and ratios are ``Fraction``; posted amounts are ``int`` minor units (DG-ENG-03).
This module is the only place that rounds (ENGINE_SPEC CV-31; DG-ARC-06). Minor units come from
the currency table (DG-KRN-MONEY-04); no code here assumes two decimals. Standard library only.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import (
    ROUND_HALF_UP,
    Context,
    Decimal,
    DivisionByZero,
    FloatOperation,
    InvalidOperation,
    Overflow,
)
from fractions import Fraction
from typing import Final

from erev_engine.errors import EngineError

__all__ = [
    "DECIMAL_CONTEXT",
    "EXACT_PLACES",
    "Money",
    "cumulative_posted",
    "decimal_to_minor",
    "format_exact",
    "format_money",
    "largest_remainder",
    "minor_to_decimal",
    "period_amounts",
    "round_half_up",
    "to_fraction",
]

# Used through decimal.localcontext(DECIMAL_CONTEXT), which copies it (CV-30).
DECIMAL_CONTEXT: Final[Context] = Context(
    prec=38,
    rounding=ROUND_HALF_UP,
    traps=[FloatOperation, InvalidOperation, DivisionByZero, Overflow],
)
EXACT_PLACES: Final = 18  # TY-02 scale

_DECIMAL_STRING: Final = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")
_CURRENCY_CODE: Final = re.compile(r"[A-Z]{3}")


@dataclass(frozen=True, slots=True)
class Money:
    """An amount in integer minor units of ``currency``."""

    minor: int
    currency: str

    def __post_init__(self) -> None:
        _require_int(self.minor, "minor")
        if not _CURRENCY_CODE.fullmatch(self.currency):
            raise ValueError("currency must be an ISO 4217 alphabetic code")


def _require_int(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int, not {type(value).__qualname__}")


def _require_places(places: int, name: str) -> None:
    _require_int(places, name)
    if not 0 <= places <= EXACT_PLACES:
        raise ValueError(f"{name} must lie between 0 and {EXACT_PLACES}")


def to_fraction(value: str | int | Decimal | Fraction) -> Fraction:
    """Exact rational value of a bundle number (DG-KRN-MONEY-05).

    ``float`` and ``bool`` raise ``TypeError``; strings must be plain decimals (``-12.30``), so an
    exponent raises ``ValueError``; non-finite ``Decimal`` values raise ``ValueError``.
    """
    if isinstance(value, bool) or not isinstance(value, str | int | Decimal | Fraction):
        raise TypeError(f"to_fraction rejects {type(value).__qualname__}")
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("to_fraction rejects NaN and infinite Decimal values")
        return Fraction(value)
    if not _DECIMAL_STRING.fullmatch(value):
        raise ValueError("to_fraction accepts plain decimal strings only, without exponent")
    return Fraction(value)


def round_half_up(x: Fraction | Decimal | int, minor_unit: int) -> int:
    """ALG-01 §2.1.1: sign(x) × ⌊|x| × 10^e + 1/2⌋, returned in minor units (DG-KRN-MONEY-01)."""
    exact = to_fraction(x)
    _require_places(minor_unit, "minor_unit")
    scale: int = 10**minor_unit
    scaled = abs(exact) * scale
    magnitude = (2 * scaled.numerator + scaled.denominator) // (2 * scaled.denominator)
    return -magnitude if exact < 0 else magnitude


def minor_to_decimal(n: int, minor_unit: int) -> Decimal:
    """``n`` minor units as a Decimal with exactly ``minor_unit`` places; never negative zero."""
    _require_int(n, "n")
    _require_places(minor_unit, "minor_unit")
    digits = tuple(int(digit) for digit in str(abs(n)))
    return Decimal((1 if n < 0 else 0, digits, -minor_unit))


def decimal_to_minor(d: Decimal, minor_unit: int) -> int:
    """Minor units of ``d``; ``ValueError`` when ``d`` is not a whole number of minor units."""
    if not isinstance(d, Decimal):
        raise TypeError(f"decimal_to_minor requires Decimal, not {type(d).__qualname__}")
    _require_places(minor_unit, "minor_unit")
    scale: int = 10**minor_unit
    scaled = to_fraction(d) * scale
    if scaled.denominator != 1:
        raise ValueError(f"amount has more than {minor_unit} decimal places")
    return scaled.numerator


def largest_remainder(
    total_minor: int, weights: Sequence[Fraction], keys: Sequence[str]
) -> list[int]:
    """ALG-01 §2.1.2: apportion ``total_minor`` over ``weights`` (DG-KRN-MONEY-02; CV-36).

    Ties order by larger fractional remainder, then larger weight, then ascending key by Unicode
    code point, so the amount per key does not depend on input order.
    """
    _require_int(total_minor, "total_minor")
    if len(weights) != len(keys):
        raise ValueError("weights and keys must have the same length")
    if len(set(keys)) != len(keys):
        raise ValueError("keys must be unique")
    exact_weights = [to_fraction(weight) for weight in weights]
    for key, weight in zip(keys, exact_weights, strict=True):
        if weight < 0:
            raise EngineError(
                "NEGATIVE_WEIGHT", "an allocation weight is negative", subject_key=key
            )
    total_weight = sum(exact_weights, Fraction(0))
    if total_weight == 0:
        raise EngineError("TOTAL_WEIGHT_ZERO", "the allocation weights sum to 0")
    sign = -1 if total_minor < 0 else 1
    magnitude = abs(total_minor)
    exact = [magnitude * weight / total_weight for weight in exact_weights]
    base = [share.numerator // share.denominator for share in exact]
    remainder = magnitude - sum(base)
    order = sorted(
        range(len(keys)),
        key=lambda i: (-(exact[i] - base[i]), -exact_weights[i], keys[i]),
    )
    for i in order[:remainder]:
        base[i] += 1
    return [sign * share for share in base]


def cumulative_posted(
    exact_allocation: Fraction, posted_allocation_minor: int, progress: Fraction, minor_unit: int
) -> int:
    """ALG-01 §2.1.3 as confirmed by D-11a: posted cumulative C_t (DG-KRN-MONEY-03; CV-35).

    C_t = round_half_up(X × f_t), bounded to [0, A] when A ≥ 0 and to [A, 0] when A < 0, and
    C_t = A when f_t = 1. Rounding A × f_t is forbidden (CHK-007). A progress outside [0, 1]
    raises ``ValueError``; stages validate progress first and raise their own codes.
    """
    exact = to_fraction(exact_allocation)
    fraction = to_fraction(progress)
    _require_int(posted_allocation_minor, "posted_allocation_minor")
    _require_places(minor_unit, "minor_unit")
    if not 0 <= fraction <= 1:
        raise ValueError("progress must lie between 0 and 1")
    if fraction == 1:
        return posted_allocation_minor
    rounded = round_half_up(exact * fraction, minor_unit)
    if posted_allocation_minor >= 0:
        return min(max(rounded, 0), posted_allocation_minor)
    return max(min(rounded, 0), posted_allocation_minor)


def period_amounts(
    exact_allocation: Fraction,
    posted_allocation_minor: int,
    cumulative_progress: Sequence[Fraction],
    minor_unit: int,
    opening_posted_minor: int = 0,
) -> list[int]:
    """Period amounts C_t − C_(t−1) with C_0 = ``opening_posted_minor`` (ALG-01 §2.1.3; POL-210).

    There is no plug to the last period (D-11): completion aligns C_t to A.
    """
    _require_int(opening_posted_minor, "opening_posted_minor")
    amounts: list[int] = []
    previous = opening_posted_minor
    for progress in cumulative_progress:
        current = cumulative_posted(exact_allocation, posted_allocation_minor, progress, minor_unit)
        amounts.append(current - previous)
        previous = current
    return amounts


def format_money(n_minor: int, minor_unit: int) -> str:
    """API money string with exactly ``minor_unit`` decimals (DG-KRN-MONEY-06)."""
    return format(minor_to_decimal(n_minor, minor_unit), "f")


def format_exact(x: Fraction | Decimal | int, places: int = EXACT_PLACES) -> str:
    """``erev.exact`` string: half up at ``places``, trailing zeros trimmed, no exponent."""
    scaled = round_half_up(x, places)
    if scaled == 0:
        return "0"
    sign = "-" if scaled < 0 else ""
    whole, fraction = divmod(abs(scaled), 10**places)
    digits = f"{fraction:0{places}d}".rstrip("0") if places else ""
    return f"{sign}{whole}.{digits}" if digits else f"{sign}{whole}"
