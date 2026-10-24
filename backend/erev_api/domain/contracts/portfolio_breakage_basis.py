"""Canonical breakage allocation snapshots for later submission and freshness checks.

Freezing an allocation does not approve it or determine expected redemptions. The caller
must capture the authorized effective-date preview while holding the workflow source locks.
"""

from collections.abc import Mapping
from decimal import Decimal
from fractions import Fraction
from typing import Any

from pydantic import ValidationError

from erev_api.domain.contracts import portfolio_allocation
from erev_api.problems import Problem
from erev_api.schemas.portfolios import PortfolioBreakagePreviewOut
from erev_engine.canonical import sha256_hex
from erev_engine.stages.s01_canonicalize import obligation_subject_key


def freeze(preview: PortfolioBreakagePreviewOut) -> dict[str, Any]:
    """Retain exact SSP fractions, FX provenance and original computation identities."""
    weights = []
    actual = {}
    identities = set()
    for share in preview.shares:
        key = obligation_subject_key(share.contract_external_id, share.obligation_key)
        identity = (share.contract_id, share.obligation_id)
        if key in actual or identity in identities:
            raise Problem("validation-failed", "Breakage allocation contains duplicate targets.")
        if len(share.computation_output_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in share.computation_output_sha256
        ):
            raise Problem("validation-failed", "Breakage allocation lacks its original digest.")
        identities.add(identity)
        try:
            weights.append(
                portfolio_allocation.Basis(
                    key, Fraction(share.ssp), Decimal(share.entitlement_quantity)
                )
            )
            actual[key] = portfolio_allocation.units(Decimal(share.breakage_quantity))
        except (ValueError, ArithmeticError) as error:
            raise Problem(
                "validation-failed", "Invalid retained breakage allocation quantities."
            ) from error
    try:
        expected = portfolio_allocation.allocate(Decimal(preview.total_breakage_quantity), weights)
        total = portfolio_allocation.units(Decimal(preview.allocated_total))
    except (ValueError, ArithmeticError) as error:
        raise Problem("validation-failed", "Invalid retained breakage allocation basis.") from error
    if total != sum(actual.values()) or any(
        actual[key] != portfolio_allocation.units(Decimal(amount))
        for key, amount in expected.items()
    ):
        raise Problem(
            "validation-failed", "Retained breakage shares differ from exact SSP allocation."
        )
    # Stable target ordering makes request/list ordering irrelevant, without rounding or
    # normalizing away original source values, identities, rates, book or effective date.
    payload = preview.model_dump(mode="json")
    payload["shares"] = sorted(
        payload["shares"],
        key=lambda item: (
            item["contract_external_id"],
            item["obligation_key"],
            item["obligation_id"],
        ),
    )
    return {"schema_version": 1, "allocation": payload, "sha256": sha256_hex(payload)}


def read(snapshot: Mapping[str, Any]) -> PortfolioBreakagePreviewOut:
    """Validate a persisted snapshot without substituting current member calculations."""
    if snapshot.get("schema_version") != 1:
        raise Problem("validation-failed", "Unsupported frozen breakage allocation schema.")
    payload = snapshot.get("allocation")
    if not isinstance(payload, Mapping) or sha256_hex(payload) != snapshot.get("sha256"):
        raise Problem("validation-failed", "Frozen breakage allocation digest differs.")
    try:
        result = PortfolioBreakagePreviewOut.model_validate(payload)
    except ValidationError as error:
        raise Problem("validation-failed", "Frozen breakage allocation is incomplete.") from error
    if freeze(result) != dict(snapshot):
        raise Problem("validation-failed", "Frozen breakage allocation is not canonical.")
    return result


def require_fresh(snapshot: Mapping[str, Any], preview: PortfolioBreakagePreviewOut) -> None:
    """A changed source, book, population or amount requires a new submission basis."""
    read(snapshot)
    if freeze(preview) != dict(snapshot):
        raise Problem(
            "invalid-transition", "Breakage allocation sources changed; submit a fresh basis."
        )
