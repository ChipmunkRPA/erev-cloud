"""Read-only current computed SSP preview; application must freeze an effective-date basis."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.auth.principal import RequestContext
from erev_api.db.tables import combination_group, contract, material_right, obligation_version
from erev_api.domain.contracts import (
    portfolio_allocation,
    portfolio_estimate_versions,
    portfolios,
    queries,
)
from erev_api.problems import Problem
from erev_api.schemas.portfolios import PortfolioBreakagePreviewOut, PortfolioBreakageShareOut


def preview(
    session: Session,
    ctx: RequestContext,
    portfolio_id: UUID,
    estimate_id: UUID,
    version_id: UUID,
    book_code: str | None = None,
) -> PortfolioBreakagePreviewOut:
    definition = portfolios.get_estimate_definition(session, ctx, portfolio_id, estimate_id)
    version = portfolio_estimate_versions.get(session, ctx, portfolio_id, estimate_id, version_id)
    if str(definition.estimate_kind) != "BREAKAGE":
        raise Problem("validation-failed", "SSP quantity allocation applies to shared breakage.")
    if version.currency is None:
        raise Problem("validation-failed", "The shared estimate needs an explicit currency.")
    total = version.parameters.get("portfolio_total_breakage_quantity")
    if total is None:
        raise Problem("validation-failed", "Enter the portfolio total breakage quantity first.")
    members = session.execute(portfolios.members(portfolio_id)).mappings().all()
    if not members:
        raise Problem("validation-failed", "Add portfolio members before previewing allocation.")
    book = book_code or queries.primary_book(session)
    sources = []
    weights = []
    for member in members:
        current = (
            session.execute(select(contract).where(contract.c.id == member["contract_id"]))
            .mappings()
            .one()
        )
        group = (
            session.execute(
                select(combination_group).where(
                    combination_group.c.id == current["combination_group_id"]
                )
            )
            .mappings()
            .one_or_none()
        )
        if group is None or group["dirty_since"] is not None:
            raise Problem(
                "validation-failed", "Recompute every portfolio member before allocation preview."
            )
        computed = queries.version_at(session, dict(current), book_code=book, known_at=None)
        if computed is None or computed["contract_computation_id"] != group["head_computation_id"]:
            raise Problem(
                "validation-failed",
                "A current computation is required for every portfolio member and book.",
            )
        loyalty = set(
            session.scalars(
                select(material_right.c.obligation_id).where(
                    material_right.c.contract_id == current["id"],
                    material_right.c.option_type == "LOYALTY_POINTS",
                )
            )
        )
        rows = (
            session.execute(
                select(obligation_version).where(
                    obligation_version.c.contract_version_id == computed["id"],
                    obligation_version.c.contract_id == current["id"],
                    obligation_version.c.scope_flag == "IN_SCOPE_606",
                )
            )
            .mappings()
            .all()
        )
        eligible = [
            row
            for row in rows
            if str(row["recognition_method"]) == "REDEMPTION_PATTERN"
            or row["obligation_id"] in loyalty
        ]
        if not eligible:
            raise Problem(
                "validation-failed",
                "Every member must have a retained redemption or loyalty obligation.",
            )
        for row in eligible:
            if str(row["txn_currency"]).strip() != version.currency:
                raise Problem(
                    "validation-failed",
                    "SSP preview needs weights in the shared estimate currency; "
                    "cross-currency weight conversion is not yet available.",
                )
            key = f"{current['external_id']}/{row['obligation_key']}"
            ssp = Decimal(
                row["original_ssp_selected"]
                if row["modification_boundary_no"] == 0
                else row["remaining_ssp"]
            )
            quantity = Decimal(row["quantity"])
            weights.append(portfolio_allocation.Basis(key, ssp, quantity))
            sources.append((key, current, row, ssp, quantity))
    try:
        shares = portfolio_allocation.allocate(Decimal(str(total)), weights)
    except ValueError as error:
        raise Problem("validation-failed", str(error)) from error
    return PortfolioBreakagePreviewOut(
        portfolio_id=portfolio_id,
        version_id=version_id,
        book_code=book,
        currency=version.currency,
        total_breakage_quantity=str(total),
        allocated_total=portfolio_allocation.text_of_units(
            sum(portfolio_allocation.units(Decimal(v)) for v in shares.values())
        ),
        shares=[
            PortfolioBreakageShareOut(
                contract_id=current["id"],
                contract_external_id=current["external_id"],
                contract_version_id=row["contract_version_id"],
                obligation_id=row["obligation_id"],
                obligation_key=row["obligation_key"],
                ssp=str(ssp),
                entitlement_quantity=str(quantity),
                breakage_quantity=shares[key],
            )
            for key, current, row, ssp, quantity in sorted(sources, key=lambda item: item[0])
        ],
    )
