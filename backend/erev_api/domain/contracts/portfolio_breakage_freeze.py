"""Retain a reviewed draft allocation; this does not approve or apply an estimate."""

from collections.abc import Callable
from uuid import UUID

from sqlalchemy import select

from erev_api.db import transitions
from erev_api.db.locking import hold_fx_publication
from erev_api.db.tables import contract
from erev_api.problems import Problem
from erev_api.schemas.estimates import (
    EstimateVersionOut,
    SharedEstimateApplicationBasis,
    SharedEstimateMemberBinding,
)
from erev_api.schemas.portfolios import PortfolioBreakagePreviewOut
from erev_api.uow import UnitOfWork

from . import (
    estimates,
    portfolio_breakage_basis,
    portfolio_estimate_versions,
    portfolio_preview,
    portfolios,
    repo,
)


def retain(
    uow: UnitOfWork,
    portfolio_id: UUID,
    estimate_id: UUID,
    version_id: UUID,
    shown: PortfolioBreakagePreviewOut,
    *,
    check_version: Callable[[int], None],
) -> EstimateVersionOut:
    hold_fx_publication(uow.session, uow.principal.tenant_id)
    portfolios.get(uow.session, portfolio_id, lock=True)
    portfolios.require_estimate_scope(uow.session, uow.ctx, portfolio_id, "estimate.create")
    definition = portfolios.get_estimate_definition(uow.session, uow.ctx, portfolio_id, estimate_id)
    if str(definition.estimate_kind) != "BREAKAGE":
        raise Problem("validation-failed", "Allocation retention applies to shared breakage.")
    row = estimates._version_row(uow.session, version_id, lock=True)
    if row["estimate_id"] != estimate_id:
        raise Problem("not-found")
    check_version(int(row["row_version"]))
    if str(row["status"]) != "DRAFT":
        raise Problem("invalid-transition", "Only a draft allocation can be retained.")
    if shown.portfolio_id != portfolio_id or shown.version_id != version_id:
        raise Problem("validation-failed", "The preview names a different estimate version.")
    population = uow.session.execute(portfolios.members(portfolio_id)).mappings().all()
    ids = [member["contract_id"] for member in population]
    heads = uow.session.execute(
        select(contract.c.id, contract.c.combination_group_id).where(contract.c.id.in_(ids))
    ).all()
    if len(heads) != len(ids):
        raise Problem("not-found")
    for head in sorted(heads, key=lambda item: (str(item.combination_group_id), str(item.id))):
        repo.lock_group_then_contract(uow.session, head.id)
    current = portfolio_preview.preview(
        uow.session,
        uow.ctx,
        portfolio_id,
        estimate_id,
        version_id,
        shown.book_code,
        uow=uow,
    )
    snapshot = portfolio_breakage_basis.freeze(shown)
    portfolio_breakage_basis.require_fresh(snapshot, current)
    if row.get("portfolio_application_basis") is None:
        members = []
        for cid in sorted(ids, key=str):
            shares = [share for share in current.shares if share.contract_id == cid]
            if not shares:
                raise Problem("validation-failed", "The allocation omits a member.")
            members.append(
                SharedEstimateMemberBinding(
                    contract_id=cid,
                    contract_key=shares[0].contract_external_id,
                    obligation_ids=sorted(share.obligation_id for share in shares),
                    obligation_keys=sorted(share.obligation_key for share in shares),
                )
            )
        basis = SharedEstimateApplicationBasis(portfolio_id=portfolio_id, members=members)
    else:
        basis = SharedEstimateApplicationBasis.model_validate(row["portfolio_application_basis"])
    basis.breakage_allocations[current.book_code] = snapshot
    before = estimates.version_outs(uow.session, [dict(row)])[0].model_dump(mode="json")
    transitions.apply(
        uow.session,
        "estimate_version",
        version_id,
        to_status=None,
        expected_status="DRAFT",
        expected_row_version=int(row["row_version"]),
        set_values={
            "portfolio_application_basis": basis.model_dump(mode="json"),
            "row_version": int(row["row_version"]) + 1,
            **portfolio_estimate_versions._stamps(uow),
        },
    )
    portfolios.touch(uow, portfolio_id)
    result = portfolio_estimate_versions.get(
        uow.session, uow.ctx, portfolio_id, estimate_id, version_id
    )
    uow.audit(
        action="estimate_version.retain_allocation",
        object_type="estimate_version",
        object_id=version_id,
        object_version=str(result.row_version),
        before=before,
        after=result.model_dump(mode="json"),
        contract_ids=portfolios.audit_contract_ids(uow.session, portfolio_id),
        detail={
            "portfolio_id": str(portfolio_id),
            "book_code": current.book_code,
            "allocation_sha256": snapshot["sha256"],
        },
    )
    return result
