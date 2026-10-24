"""Server-captured shared return targets retained on a draft version and frozen on submission."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import obligation, estimate_version
from erev_api.domain.contracts import portfolios
from erev_api.problems import Problem
from erev_api.schemas.estimates import SharedEstimateApplicationBasis, SharedEstimateMemberBinding


def capture(
    session: Session, portfolio_id: UUID, element: Mapping[str, Any]
) -> dict[str, Any] | None:
    if str(element["estimate_kind"]) != "RETURN_RATE" or not element["target_obligation_ids"]:
        return None
    population = session.execute(portfolios.members(portfolio_id)).mappings().all()
    previous = session.scalar(
        select(estimate_version.c.portfolio_application_basis)
        .where(
            estimate_version.c.estimate_id == element["id"], estimate_version.c.status == "APPROVED"
        )
        .order_by(estimate_version.c.version_no.desc())
        .limit(1)
    )
    active_ids = {str(m["contract_id"]) for m in population}
    retired = [
        SharedEstimateMemberBinding.model_validate(m)
        for m in (previous or {}).get("members", [])
        if str(m["contract_id"]) not in active_ids
    ]
    if not population and not retired:
        raise Problem("validation-failed", "Add members or retire a previously applied population.")
    rows = session.execute(
        select(obligation.c.id, obligation.c.contract_id, obligation.c.obligation_key).where(
            obligation.c.id.in_(element["target_obligation_ids"])
        )
    ).all()
    members = []
    for member in sorted(population, key=lambda m: str(m["contract_id"])):
        targets = sorted(
            (row for row in rows if row.contract_id == member["contract_id"]),
            key=lambda r: str(r.id),
        )
        if not targets:
            raise Problem(
                "validation-failed", "A current member has no retained targets in this definition."
            )
        members.append(
            SharedEstimateMemberBinding(
                contract_id=member["contract_id"],
                contract_key=member["contract_external_id"],
                obligation_ids=[row.id for row in targets],
                obligation_keys=sorted({row.obligation_key for row in targets}),
            )
        )
    if members and len({tuple(member.obligation_keys) for member in members}) != 1:
        raise Problem("validation-failed", "Shared return member targets must have matching keys.")
    return SharedEstimateApplicationBasis(
        portfolio_id=portfolio_id, members=members, retired_members=retired
    ).model_dump(mode="json")


def for_group(
    basis: Mapping[str, Any],
    element: Mapping[str, Any],
    contracts: Mapping[UUID, Mapping[str, Any]],
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]]:
    frozen = SharedEstimateApplicationBasis.model_validate(basis)
    if str(frozen.portfolio_id) != str(element["portfolio_id"]):
        raise Problem("validation-failed", "The retained application names a different portfolio.")
    members = [member for member in frozen.members if member.contract_id in contracts]
    recipients = [
        member
        for member in (*frozen.members, *frozen.retired_members)
        if member.contract_id in contracts
    ]
    targets = {target for member in recipients for target in member.obligation_ids}
    declared = {UUID(str(target)) for target in element["target_obligation_ids"]}
    if not targets <= declared:
        raise Problem("validation-failed", "The retained application names undeclared targets.")
    if any(
        str(contracts[member.contract_id]["external_id"]) != member.contract_key
        for member in recipients
    ):
        raise Problem(
            "validation-failed", "A retained member identity no longer matches its contract."
        )
    selected = dict(element)
    selected["target_obligation_ids"] = sorted(targets)
    return (
        selected,
        tuple(sorted({member.contract_key for member in members})),
        tuple(sorted({member.contract_key for member in recipients})),
    )


def recipients(basis: Mapping[str, Any]) -> list[UUID]:
    """Apply a new scope to both retained members and members leaving its predecessor."""
    frozen = SharedEstimateApplicationBasis.model_validate(basis)
    return sorted({m.contract_id for m in (*frozen.members, *frozen.retired_members)})
