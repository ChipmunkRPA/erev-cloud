"""Verified effective-date SSP preview; approval must still freeze the shown basis."""

from decimal import Decimal
from fractions import Fraction
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.auth.principal import RequestContext
from erev_api.db.tables import combination_group, contract, material_right, obligation_version
from erev_api.domain.contracts import (
    bundles,
    portfolio_allocation,
    portfolio_effective_basis,
    portfolio_estimate_versions,
    portfolio_ssp_fx,
    portfolios,
    queries,
)
from erev_api.domain.reports import computation_sources
from erev_api.problems import Problem
from erev_api.schemas.portfolios import PortfolioBreakagePreviewOut, PortfolioBreakageShareOut
from erev_api.uow import UnitOfWork
from erev_engine.errors import EngineError
from erev_engine.stages.s01_canonicalize import obligation_subject_key


def preview(
    session: Session,
    ctx: RequestContext,
    portfolio_id: UUID,
    estimate_id: UUID,
    version_id: UUID,
    book_code: str | None = None,
    *,
    uow: UnitOfWork,
) -> PortfolioBreakagePreviewOut:
    definition = portfolios.get_estimate_definition(session, ctx, portfolio_id, estimate_id)
    version = portfolio_estimate_versions.get(session, ctx, portfolio_id, estimate_id, version_id)
    if str(definition.estimate_kind) != "BREAKAGE":
        raise Problem("validation-failed", "SSP quantity allocation applies to shared breakage.")
    if version.currency is None:
        raise Problem("validation-failed", "The shared estimate needs an explicit currency.")
    binding = version.portfolio_application_basis
    target_keys = set(
        binding.target_obligation_keys
        if binding is not None and binding.target_obligation_keys is not None
        else definition.target_obligation_keys
    )
    if str(definition.allocation_target) == "OBLIGATIONS" and not target_keys:
        raise Problem("validation-failed", "The shared breakage target keys are unavailable.")
    total = version.parameters.get("portfolio_total_breakage_quantity")
    if total is None:
        raise Problem("validation-failed", "Enter the portfolio total breakage quantity first.")
    members = session.execute(portfolios.members(portfolio_id)).mappings().all()
    if not members:
        raise Problem("validation-failed", "Add portfolio members before previewing allocation.")
    bound_members = {} if binding is None else {m.contract_id: m for m in binding.members}
    if binding is not None and (
        binding.portfolio_id != portfolio_id
        or len(bound_members) != len(binding.members)
        or set(bound_members) != {m["contract_id"] for m in members}
    ):
        raise Problem(
            "validation-failed",
            "The saved breakage population differs. Save the draft again before previewing.",
        )
    book = book_code or queries.primary_book(session)
    sources = []
    weights = []
    conversions = {}
    rate_sets = {}
    verified = {}
    provenance = {}
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
        if target_keys:
            eligible = [row for row in eligible if row["obligation_key"] in target_keys]
            if {row["obligation_key"] for row in eligible} != target_keys:
                raise Problem(
                    "validation-failed",
                    "Every member must retain every selected breakage target as an "
                    "in-scope redemption or loyalty obligation. Recompute or revise the targets.",
                )
        if not eligible:
            raise Problem(
                "validation-failed",
                "Every member must have a retained redemption or loyalty obligation.",
            )
        bound = bound_members.get(current["id"])
        if bound is not None and (
            bound.contract_key != current["external_id"]
            or set(bound.obligation_keys) != {row["obligation_key"] for row in eligible}
            or set(bound.obligation_ids) != {row["obligation_id"] for row in eligible}
        ):
            raise Problem(
                "validation-failed",
                "The saved breakage targets differ. Save the draft again before previewing.",
            )
        computation_id = computed["contract_computation_id"]
        if computation_id not in verified:
            verified[computation_id] = computation_sources.read_for_report(
                uow, computation_id, permission="contract.read"
            )
        original = verified[computation_id]
        try:
            historical = portfolio_effective_basis.from_bundle(
                original.bundle,
                book,
                version.effective_date,
                [
                    obligation_subject_key(current["external_id"], row["obligation_key"])
                    for row in eligible
                ],
            )
        except EngineError as error:
            raise Problem(
                "validation-failed",
                f"The retained contract cannot supply the dated allocation basis ({error.code}).",
            ) from error
        for row in eligible:
            key = obligation_subject_key(current["external_id"], row["obligation_key"])
            dated = historical[key]
            if not dated.redemption_eligible:
                raise Problem(
                    "validation-failed",
                    "A target was not a redemption or loyalty obligation "
                    "on the estimate effective date.",
                )
            ssp = dated.ssp
            currency = dated.currency
            provenance[key] = original
            if currency != version.currency:
                if currency not in rate_sets:
                    rate_sets[currency] = bundles.fx_rate_inputs(
                        session, {currency, version.currency}, None
                    )
                conversion = portfolio_ssp_fx.convert(
                    ssp, currency, version.currency, version.effective_date, rate_sets[currency]
                )
                conversions[key] = conversion
                ssp = Fraction(conversion.converted_ssp)
            try:
                quantity = Decimal(
                    portfolio_allocation.text_of_units(
                        portfolio_allocation.units(dated.entitlement)
                    )
                )
            except ValueError as error:
                raise Problem("validation-failed", str(error)) from error
            weights.append(portfolio_allocation.Basis(key, ssp, quantity))
            sources.append((key, current, row, ssp, quantity))
    try:
        shares = portfolio_allocation.allocate(Decimal(str(total)), weights)
    except ValueError as error:
        raise Problem("validation-failed", str(error)) from error
    return PortfolioBreakagePreviewOut(
        effective_date=version.effective_date,
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
                computation_id=provenance[key].computation_id,
                computation_output_sha256=provenance[key].output_sha256,
                ssp_conversion=conversions.get(key),
                entitlement_quantity=str(quantity),
                breakage_quantity=shares[key],
            )
            for key, current, row, ssp, quantity in sorted(sources, key=lambda item: item[0])
        ],
    )
