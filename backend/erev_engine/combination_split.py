"""Dated remaining-SSP allocation for a prospective contract-combination split.

This prepares the source-backed allocation, not a membership change. Application must
preserve the original revenue and groups before the boundary and install the planned
remaining allocations prospectively. DATA_CORRECTION is not an application substitute.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from fractions import Fraction

from erev_engine import money
from erev_engine.boundary_basis import FixedBoundaryBasis, fixed_boundary_basis
from erev_engine.bundle import InputBundle


@dataclass(frozen=True, slots=True)
class SplitMember:
    contract_key: str
    destination: str
    original: tuple[FixedBoundaryBasis, ...]
    remaining_ssp: Fraction
    recognized_minor: int
    remaining_before_minor: int
    remaining_after_minor: int
    # Original obligation keys and their prospective remainder, in key order.
    obligation_shares: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class SplitBasis:
    input_sha256: str
    book_code: str
    currency: str
    effective_date: date
    boundary_event_key: str | None
    boundary_position: str
    recognized_minor: int
    unrecognized_minor: int
    members: tuple[SplitMember, ...]


def prepare(
    bundle: InputBundle,
    *,
    book_code: str,
    destinations: Mapping[str, str],
    effective_date: date | None = None,
    event_key: str | None = None,
) -> SplitBasis:
    """Partition every original member and allocate the posted remainder by dated SSP.

    Native boundary measurement preserves prior posted revenue, including its rounding.
    First apportion the group remainder to original contracts by remaining SSP; then
    apportion each member's amount to its obligations. Both use native largest remainder
    and stable original identities. No latest remaining-balance column is used.
    """
    if book_code not in {"ASC606", "IFRS15"}:
        raise ValueError("Prospective split allocation requires ASC606 or IFRS15")
    population = {contract.external_id for contract in bundle.contracts}
    if len(population) < 2 or set(destinations) != population:
        raise ValueError("A split must partition every original combined contract exactly once")
    if (
        any(not target.strip() for target in destinations.values())
        or len(set(destinations.values())) < 2
    ):
        raise ValueError("A split requires at least two named destinations")
    dated = {}
    for key in sorted(population):
        dated[key] = fixed_boundary_basis(
            bundle,
            book_code=book_code,
            event_key=event_key,
            effective_date=effective_date,
            contract_key=key,
            obligation_keys=None,
            require_fixed_transfer=True,
            require_remaining_service=False,
            resolve_remaining_ssp=True,
        )
    first = next(iter(dated.values()))[0]
    if any(c.inception_date > first.effective_date for c in bundle.contracts):
        raise ValueError("A split cannot include contracts created after its effective date")
    ssp = {
        key: sum((row.remaining_ssp or Fraction(0) for row in rows), Fraction(0))
        for key, rows in dated.items()
    }
    if any(weight < 0 for weight in ssp.values()):
        raise ValueError("Remaining split SSP must be nonnegative")
    unrecognized = sum(row.remaining_minor for rows in dated.values() for row in rows)
    recognized = sum(row.recognized_minor for rows in dated.values() for row in rows)
    keys = sorted(dated)
    shares = (
        money.largest_remainder(unrecognized, [ssp[key] for key in keys], keys)
        if unrecognized
        else [0] * len(keys)
    )
    members = []
    for key, share in zip(keys, shares, strict=True):
        rows = dated[key]
        child_keys = [row.obligation_key for row in rows]
        child_shares = (
            money.largest_remainder(
                share, [row.remaining_ssp or Fraction(0) for row in rows], child_keys
            )
            if share
            else [0] * len(rows)
        )
        members.append(
            SplitMember(
                contract_key=key,
                destination=destinations[key],
                original=rows,
                remaining_ssp=ssp[key],
                recognized_minor=sum(row.recognized_minor for row in rows),
                remaining_before_minor=sum(row.remaining_minor for row in rows),
                remaining_after_minor=share,
                obligation_shares=tuple(zip(child_keys, child_shares, strict=True)),
            )
        )
    return SplitBasis(
        input_sha256=first.input_sha256,
        book_code=book_code,
        currency=first.currency,
        effective_date=first.effective_date,
        boundary_event_key=event_key,
        boundary_position=first.boundary_position,
        recognized_minor=recognized,
        unrecognized_minor=unrecognized,
        members=tuple(members),
    )
