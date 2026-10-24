"""Conserving shared breakage allocation against explicit, retained SSP inputs."""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from collections.abc import Sequence

from erev_engine.money import largest_remainder

SCALE = 10**18


@dataclass(frozen=True)
class Basis:
    key: str
    ssp: Decimal
    quantity: Decimal


def units(value: Decimal) -> int:
    """Database quantities use erev.exact's 18 decimal places, without float rounding."""
    if not value.is_finite() or value < 0:
        raise ValueError("Quantities must be finite and nonnegative")
    exact = Fraction(value) * SCALE
    if exact.denominator != 1:
        raise ValueError("Shared quantities support at most 18 decimal places")
    return exact.numerator


def text_of_units(value: int) -> str:
    whole, remainder = divmod(value, SCALE)
    return str(whole) if not remainder else f"{whole}.{remainder:018d}".rstrip("0")


def allocate(total: Decimal, basis: Sequence[Basis]) -> dict[str, str]:
    """SSP weights, then largest remainder at the retained quantity precision.

    Excess over an entitlement is refused, not redistributed onto other members: such a
    redistribution would change the owner's chosen SSP basis.
    """
    amount = units(total)
    ordered = sorted(basis, key=lambda item: item.key)
    if not ordered or len({item.key for item in ordered}) != len(ordered):
        raise ValueError("A complete, unique allocation population is required")
    for item in ordered:
        units(item.quantity)
        if not item.ssp.is_finite() or item.ssp < 0:
            raise ValueError("SSP weights must be finite and nonnegative")
    weights = [Fraction(item.ssp) for item in ordered]
    if sum(weights) <= 0:
        raise ValueError("A positive total SSP is required")
    shares = largest_remainder(amount, weights, [item.key for item in ordered])
    for item, share in zip(ordered, shares, strict=True):
        if share > units(item.quantity):
            raise ValueError(f"Allocated breakage exceeds the entitlement for {item.key}")
    return {item.key: text_of_units(share) for item, share in zip(ordered, shares, strict=True)}
