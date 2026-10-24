"""Server-captured shared return targets retained on a draft version and frozen on submission."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import obligation, estimate_version
from erev_api.domain.contracts import portfolios
from erev_api.problems import Problem
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from erev_api.schemas.estimates import SharedEstimateApplicationBasis, SharedEstimateMemberBinding


def capture(
    session: Session,
    portfolio_id: UUID,
    element: Mapping[str, Any],
    *,
    values: Mapping[str, Any],
    target_keys: list[str] | None = None,
) -> dict[str, Any] | None:
    if str(element["estimate_kind"]) != "RETURN_RATE":
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
    # Definitions retain their original IDs as the source of the common target keys.
    # A new member has different original IDs; resolve those only into the new version.
    keys = set(
        session.scalars(
            select(obligation.c.obligation_key).where(
                obligation.c.id.in_(element["target_obligation_ids"])
            )
        )
    )
    selected_keys = target_keys
    if selected_keys is None:
        selected_keys = (values.get("portfolio_application_basis") or previous or {}).get(
            "target_obligation_keys"
        )
    if selected_keys is not None:
        if not selected_keys or len(set(selected_keys)) != len(selected_keys):
            raise Problem("validation-failed", "Select each shared target key exactly once.")
        keys = set(selected_keys)
    if not keys:
        return None
    if not population and not retired:
        raise Problem("validation-failed", "Add members or retire a previously applied population.")
    rows = session.execute(
        select(obligation.c.id, obligation.c.contract_id, obligation.c.obligation_key).where(
            obligation.c.contract_id.in_([m["contract_id"] for m in population]),
            obligation.c.obligation_key.in_(keys),
        )
    ).all()
    members = []
    for member in sorted(population, key=lambda m: str(m["contract_id"])):
        targets = sorted(
            (row for row in rows if row.contract_id == member["contract_id"]),
            key=lambda r: str(r.id),
        )
        if {row.obligation_key for row in targets} != keys:
            raise Problem(
                "validation-failed",
                "Every current member must contain every shared target obligation key.",
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
    current_targets = {m.contract_id: set(m.obligation_ids) for m in members}
    retired_targets = []
    for old in (previous or {}).get("members", []):
        original = SharedEstimateMemberBinding.model_validate(old)
        if original.contract_id not in current_targets:
            continue
        removed = set(original.obligation_ids) - current_targets[original.contract_id]
        if removed:
            removed_rows = session.execute(
                select(obligation.c.id, obligation.c.obligation_key).where(
                    obligation.c.id.in_(sorted(removed))
                )
            ).all()
            retired_targets.append(
                SharedEstimateMemberBinding(
                    contract_id=original.contract_id,
                    contract_key=original.contract_key,
                    obligation_ids=sorted(removed),
                    obligation_keys=sorted({r.obligation_key for r in removed_rows}),
                )
            )
    from erev_api.domain.contracts import portfolio_cost_fx

    conversion = portfolio_cost_fx.capture(
        session, values, sorted({m.contract_id for m in (*members, *retired)})
    )
    return SharedEstimateApplicationBasis(
        portfolio_id=portfolio_id,
        members=members,
        retired_members=retired,
        cost_conversions=conversion,
        target_obligation_keys=None
        if (
            values.get("portfolio_application_basis")
            and values["portfolio_application_basis"].get("target_obligation_keys") is None
            and target_keys is None
        )
        else sorted(keys),
        retired_targets=retired_targets,
    ).model_dump(mode="json")


def for_group(
    basis: Mapping[str, Any],
    element: Mapping[str, Any],
    contracts: Mapping[UUID, Mapping[str, Any]],
    *,
    obligation_keys: Mapping[UUID, str],
    obligation_owners: Mapping[UUID, UUID],
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...], tuple[str, ...] | None]:
    frozen = SharedEstimateApplicationBasis.model_validate(basis)
    if str(frozen.portfolio_id) != str(element["portfolio_id"]):
        raise Problem("validation-failed", "The retained application names a different portfolio.")
    members = [member for member in frozen.members if member.contract_id in contracts]
    recipients = [
        member
        for member in (*frozen.members, *frozen.retired_members, *frozen.retired_targets)
        if member.contract_id in contracts
    ]
    targets = {target for member in recipients for target in member.obligation_ids}
    for member in recipients:
        if (
            not member.obligation_ids
            or any(
                obligation_owners.get(target) != member.contract_id
                for target in member.obligation_ids
            )
            or {obligation_keys.get(target) for target in member.obligation_ids}
            != set(member.obligation_keys)
        ):
            raise Problem(
                "validation-failed", "Retained targets no longer match their member and keys."
            )
    if any(
        str(contracts[member.contract_id]["external_id"]) != member.contract_key
        for member in recipients
    ):
        raise Problem(
            "validation-failed", "A retained member identity no longer matches its contract."
        )
    selected = dict(element)
    selected["target_obligation_ids"] = sorted(targets)
    selected["allocation_target"] = "OBLIGATIONS"
    return (
        selected,
        tuple(sorted({member.contract_key for member in members})),
        tuple(sorted({member.contract_key for member in recipients})),
        None
        if frozen.target_obligation_keys is None
        else tuple(
            sorted(
                {
                    obligation_subject_key(m.contract_key, key)
                    for m in members
                    for key in m.obligation_keys
                }
            )
        ),
    )


def recipients(basis: Mapping[str, Any]) -> list[UUID]:
    """Apply a new scope to both retained members and members leaving its predecessor."""
    frozen = SharedEstimateApplicationBasis.model_validate(basis)
    return sorted(
        {m.contract_id for m in (*frozen.members, *frozen.retired_members, *frozen.retired_targets)}
    )
