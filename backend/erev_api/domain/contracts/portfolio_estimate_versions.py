"""Shared estimate draft values; no approval or financial application occurs here."""

from collections.abc import Callable
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from erev_api.auth.principal import RequestContext
from erev_api.db import new_id, transitions
from erev_api.db.locking import hold_fx_publication
from erev_api.db.tables import estimate, estimate_version
from erev_api.domain.contracts import estimates, portfolio_allocation, portfolio_binding, portfolios
from erev_api.problems import Problem
from erev_api.schemas.estimates import EstimateVersionOut
from erev_api.schemas.portfolios import PortfolioEstimateVersionIn
from erev_api.uow import UnitOfWork


def _element(
    session: Session, ctx: RequestContext, portfolio_id: UUID, estimate_id: UUID
) -> dict[str, Any]:
    portfolios.get_estimate_definition(session, ctx, portfolio_id, estimate_id)
    return dict(
        session.execute(select(estimate).where(estimate.c.id == estimate_id)).mappings().one()
    )


def get(
    session: Session, ctx: RequestContext, portfolio_id: UUID, estimate_id: UUID, version_id: UUID
) -> EstimateVersionOut:
    _element(session, ctx, portfolio_id, estimate_id)
    row = (
        session.execute(
            select(estimate_version).where(
                estimate_version.c.id == version_id, estimate_version.c.estimate_id == estimate_id
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return estimates.version_outs(session, [dict(row)])[0]


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    return {
        "updated_at": uow.now,
        "updated_by": uow.principal.id,
        "updated_by_kind": uow.principal.kind.value,
    }


def save(
    uow: UnitOfWork,
    portfolio_id: UUID,
    estimate_id: UUID,
    body: PortfolioEstimateVersionIn | None,
    *,
    check_version: Callable[[int], None],
    version_id: UUID | None = None,
    discard: bool = False,
) -> EstimateVersionOut:
    # Match submission/approval lock order before freezing rate and population sources.
    hold_fx_publication(uow.session, uow.principal.tenant_id)
    parent = portfolios.get(uow.session, portfolio_id, lock=True)
    portfolios.require_estimate_scope(uow.session, uow.ctx, portfolio_id, "estimate.create")
    element = _element(uow.session, uow.ctx, portfolio_id, estimate_id)
    creating = version_id is None
    before = None
    version_row_version = 0
    if creating:
        check_version(parent.row_version)
        if discard:
            raise ValueError("Discard requires an existing version")
        open_version = uow.session.scalar(
            select(estimate_version.c.id)
            .where(
                estimate_version.c.estimate_id == estimate_id,
                estimate_version.c.status.in_(["DRAFT", "SUBMITTED"]),
            )
            .limit(1)
        )
        if open_version is not None:
            raise Problem(
                "invalid-transition", "Finish or discard the existing open version first."
            )
    else:
        row = (
            uow.session.execute(
                select(estimate_version)
                .where(
                    estimate_version.c.id == version_id,
                    estimate_version.c.estimate_id == estimate_id,
                )
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise Problem("not-found")
        before = estimates.version_outs(uow.session, [dict(row)])[0].model_dump(mode="json")
        version_row_version = int(row["row_version"])
        check_version(version_row_version)
        if row["status"] != "DRAFT":
            raise Problem("invalid-transition", "Only a draft version can be edited or discarded.")
    values: dict[str, Any] = {}
    if not discard:
        if body is None:
            raise ValueError("Saving requires version values")
        values = estimates.validated_version_values(
            uow.session, element, body, default_currency=body.currency
        )
        if body.target_obligation_keys is not None and str(element["estimate_kind"]) not in {
            "RETURN_RATE",
            "BREAKAGE",
        }:
            raise Problem(
                "validation-failed", "Version target keys apply only to shared returns or breakage."
            )
        if str(element["estimate_kind"]) == "BREAKAGE":
            if values["parameters"].get("portfolio_total_breakage_quantity") is None:
                raise Problem(
                    "validation-failed",
                    "Enter the portfolio total breakage quantity for SSP allocation.",
                )
            try:
                portfolio_allocation.units(
                    Decimal(values["parameters"]["portfolio_total_breakage_quantity"])
                )
            except ValueError as error:
                raise Problem("validation-failed", str(error)) from error
            if values["rate"] is not None or values["expected_quantity"] is not None:
                raise Problem(
                    "validation-failed",
                    "Shared breakage uses a total quantity; do not also enter a rate "
                    "or expected redemption quantity.",
                )
        values["portfolio_application_basis"] = portfolio_binding.capture(
            uow.session,
            portfolio_id,
            element,
            values={
                **values,
                "portfolio_application_basis": (before or {}).get("portfolio_application_basis"),
            },
            target_keys=body.target_obligation_keys,
        )
        if body.rate is not None and not 0 <= values["rate"] <= 1:
            raise Problem(
                "validation-failed", "A shared estimate rate must be between zero and one."
            )
    if creating:
        version_id = new_id()
        number = uow.session.scalar(
            select(func.coalesce(func.max(estimate_version.c.version_no), 0)).where(
                estimate_version.c.estimate_id == estimate_id
            )
        )
        previous = uow.session.scalar(
            select(estimate_version.c.id)
            .where(
                estimate_version.c.estimate_id == estimate_id,
                estimate_version.c.status == "APPROVED",
            )
            .order_by(estimate_version.c.version_no.desc())
            .limit(1)
        )
        uow.session.execute(
            insert(estimate_version).values(
                tenant_id=uow.principal.tenant_id,
                id=version_id,
                estimate_id=estimate_id,
                version_no=int(number or 0) + 1,
                status="DRAFT",
                supersedes_version_id=previous,
                created_at=uow.now,
                created_by=uow.principal.id,
                created_by_kind=uow.principal.kind.value,
                **values,
                **_stamps(uow),
            )
        )
    else:
        assert version_id is not None
        transitions.apply(
            uow.session,
            "estimate_version",
            version_id,
            to_status="VOIDED" if discard else None,
            expected_status="DRAFT",
            expected_row_version=version_row_version,
            set_values={**values, **_stamps(uow), "row_version": version_row_version + 1},
        )
    assert version_id is not None
    portfolios.touch(uow, portfolio_id)
    result = get(uow.session, uow.ctx, portfolio_id, estimate_id, version_id)
    uow.audit(
        action="estimate_version." + ("create" if creating else "discard" if discard else "update"),
        object_type="estimate_version",
        object_id=version_id,
        object_version=str(result.row_version),
        before=before,
        after=result.model_dump(mode="json"),
        contract_ids=portfolios.audit_contract_ids(uow.session, portfolio_id),
        detail={
            "portfolio_id": str(portfolio_id),
            "estimate_id": str(estimate_id),
        },
    )
    return result
