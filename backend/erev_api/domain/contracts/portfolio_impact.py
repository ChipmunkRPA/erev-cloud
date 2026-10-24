"""Read-only shared return/breakage impact, once per affected group."""

from dataclasses import replace
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.approvals import subjects
from erev_api.auth.dependencies import require_for_entity
from erev_api.auth.principal import RequestContext
from erev_api.db.session import system_entity_scope
from erev_api.db.tables import combination_group, contract, estimate, estimate_version
from erev_api.domain.contracts import (
    bundles,
    computation,
    estimates,
    portfolio_binding,
    portfolio_estimate_versions,
    portfolios,
    queries,
)
from erev_api.domain.contracts.activation import engine_problem
from erev_api.domain.contracts.events import impact_summary
from erev_api.problems import Problem
from erev_api.schemas.estimates import SharedEstimateApplicationBasis
from erev_api.schemas.portfolios import (
    PortfolioImpactGroupOut,
    PortfolioImpactMemberOut,
    PortfolioImpactOut,
)
from erev_api.uow import UnitOfWork
from erev_engine.currencies import ISO_4217
from erev_engine.errors import EngineError


def preview(
    session: Session,
    ctx: RequestContext,
    portfolio_id: UUID,
    estimate_id: UUID,
    version_id: UUID,
    now: datetime,
    *,
    uow: UnitOfWork | None = None,
) -> PortfolioImpactOut:
    shown = portfolio_estimate_versions.get(session, ctx, portfolio_id, estimate_id, version_id)
    if shown.status not in {"DRAFT", "SUBMITTED"}:
        raise Problem("validation-failed", "Preview an open shared estimate version.")
    with system_entity_scope(session):
        scope = subjects.estimate_version_entities(session, version_id)
    if scope.all_entities or not scope.ids:
        raise Problem("validation-failed", "A complete member population is required for preview.")
    for entity_id in scope.ids:
        require_for_entity(ctx, "contract.read", entity_id)
    element = dict(
        session.execute(select(estimate).where(estimate.c.id == estimate_id)).mappings().one()
    )
    row = dict(
        session.execute(select(estimate_version).where(estimate_version.c.id == version_id))
        .mappings()
        .one()
    )
    if str(element["estimate_kind"]) not in {"RETURN_RATE", "BREAKAGE"}:
        raise Problem("validation-failed", "This shared estimate kind cannot be applied yet.")
    is_breakage = str(element["estimate_kind"]) == "BREAKAGE"
    if is_breakage:
        from .portfolio_breakage_application import require_fresh

        if uow is None:
            raise Problem(
                "validation-failed", "Shared breakage preview needs original file sources."
            )
        require_fresh(uow, element, row)
    if not is_breakage and row.get("portfolio_application_basis") is not None:
        if SharedEstimateApplicationBasis.model_validate(
            row["portfolio_application_basis"]
        ) != SharedEstimateApplicationBasis.model_validate(
            portfolio_binding.capture(session, portfolio_id, element, values=row)
        ):
            raise Problem(
                "validation-failed",
                "Member bindings or cost-conversion rates changed. "
                "Save the draft again before preview.",
            )
    member_ids = (
        portfolio_binding.recipients(row["portfolio_application_basis"])
        if row.get("portfolio_application_basis") is not None
        else [
            m["contract_id"] for m in session.execute(portfolios.members(portfolio_id)).mappings()
        ]
    )
    if not member_ids:
        raise Problem("validation-failed", "Add members before previewing shared estimates.")
    currents = [
        dict(c)
        for c in session.execute(select(contract).where(contract.c.id.in_(member_ids))).mappings()
    ]
    groups = sorted({c["combination_group_id"] for c in currents})
    results = []
    book = queries.primary_book(session)
    for group_id in groups:
        group = (
            session.execute(select(combination_group).where(combination_group.c.id == group_id))
            .mappings()
            .one()
        )
        if group["dirty_since"] is not None or group["head_computation_id"] is None:
            raise Problem("validation-failed", "Recompute affected groups before impact preview.")
        representative = min(
            (c for c in currents if c["combination_group_id"] == group_id),
            key=lambda c: c["external_id"],
        )
        prior = queries.version_at(session, representative, book_code=book, known_at=None)
        if prior is None or prior["contract_computation_id"] != group["head_computation_id"]:
            raise Problem("validation-failed", "A current primary-book computation is required.")
        pending = [estimates._changed_event(row, row["supersedes_version_id"], None)]
        try:
            bundle = bundles.build(
                session, group_id, now, pending, "DRY_RUN", pending_contract_id=representative["id"]
            )
            if is_breakage:
                saved_books = set(
                    (row.get("portfolio_application_basis") or {}).get("breakage_allocations", {})
                )
                missing = {b.book_code for b in bundle.books} - saved_books
                if missing:
                    raise Problem(
                        "validation-failed",
                        "Save shared breakage allocations for books: " + ", ".join(sorted(missing)),
                    )
            estimate_key = bundles._estimate_key(element, representative["external_id"])
            key = f"{estimate_key}@v{row['version_no']}"
            bundle = replace(
                bundle,
                estimate_versions=tuple(
                    replace(v, status="APPROVED") if v.version_key == key else v
                    for v in bundle.estimate_versions
                ),
            )
            output = computation.default_engine()(bundle)
        except EngineError as error:
            raise engine_problem(error) from error
        affected = (
            session.execute(select(contract).where(contract.c.combination_group_id == group_id))
            .mappings()
            .all()
        )
        members = []
        for current in sorted(affected, key=lambda c: c["external_id"]):
            before, after = estimates._balances(session, dict(current), bundle, output)
            summary = impact_summary(
                session, dict(current), bundle, output, pending, computed_at=now
            )
            members.append(
                PortfolioImpactMemberOut(
                    contract_id=current["id"],
                    contract_external_id=current["external_id"],
                    balances_before=before,
                    balances_after=after,
                    revenue_by_period=summary.revenue_by_period,
                )
            )
        currency = str(representative["transaction_currency"]).strip()
        catch_up = estimates.group_catch_up(output.books, ISO_4217[currency].minor_unit, book)
        if catch_up is None:
            raise Problem("validation-failed", "The shared preview produced no calculation book.")
        results.append(
            PortfolioImpactGroupOut(
                source_computation_id=group["head_computation_id"],
                source_contract_version_id=prior["id"],
                input_sha256=bundle.sha256(),
                combination_group_id=group_id,
                book_code=book,
                currency=currency,
                catch_up_amount=str(catch_up),
                members=members,
            )
        )
    return PortfolioImpactOut(
        basis="SHARED_BREAKAGE_DRY_RUN" if is_breakage else "SHARED_RETURN_DRY_RUN",
        portfolio_id=portfolio_id,
        version_id=version_id,
        computed_at=now,
        groups=results,
    )
