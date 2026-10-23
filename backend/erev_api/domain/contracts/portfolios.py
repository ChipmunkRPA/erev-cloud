"""Portfolio metadata and audited membership, serialized by the portfolio row."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, insert, select, update
from sqlalchemy.orm import Session

from erev_api.audit.writer import record_facts
from erev_api.auth.dependencies import require_for_entity
from erev_api.auth.principal import RequestContext
from erev_api.db import new_id
from erev_api.db.tables import contract, estimate, portfolio, portfolio_member
from erev_api.domain.contracts import estimates, repo
from erev_api.problems import Problem
from erev_api.schemas.estimates import EstimateOut
from erev_api.schemas.portfolios import (
    PortfolioEstimateIn,
    PortfolioIn,
    PortfolioMemberOut,
    PortfolioOut,
)
from erev_api.uow import UnitOfWork

WRITE = "estimate.create"


def get(session: Session, portfolio_id: UUID, *, lock: bool = False) -> PortfolioOut:
    statement = select(portfolio).where(portfolio.c.id == portfolio_id)
    if lock:
        statement = statement.with_for_update()
    row = session.execute(statement).mappings().one_or_none()
    if row is None:
        raise Problem("not-found")
    return PortfolioOut.model_validate({key: row[key] for key in PortfolioOut.model_fields})


def members(portfolio_id: UUID, *, history: bool = False) -> Select[Any]:
    statement = (
        select(
            portfolio_member,
            contract.c.contracting_entity_id,
            contract.c.external_id.label("contract_external_id"),
            portfolio.c.row_version.label("portfolio_row_version"),
        )
        .select_from(
            portfolio_member.join(
                contract,
                (portfolio_member.c.tenant_id == contract.c.tenant_id)
                & (portfolio_member.c.contract_id == contract.c.id),
            ).join(
                portfolio,
                (portfolio_member.c.tenant_id == portfolio.c.tenant_id)
                & (portfolio_member.c.portfolio_id == portfolio.c.id),
            )
        )
        .where(portfolio_member.c.portfolio_id == portfolio_id)
    )
    return statement if history else statement.where(portfolio_member.c.valid_to_known_at.is_(None))


def touch(uow: UnitOfWork, portfolio_id: UUID) -> None:
    uow.session.execute(
        update(portfolio)
        .where(portfolio.c.id == portfolio_id)
        .values(
            updated_at=uow.now,
            updated_by=uow.principal.id,
            updated_by_kind=uow.principal.kind.value,
        )
    )


def save(
    uow: UnitOfWork,
    body: PortfolioIn,
    *,
    portfolio_id: UUID | None = None,
    check_version: Callable[[int], None] | None = None,
) -> PortfolioOut:
    require_for_entity(uow.ctx, WRITE, None)
    creating = portfolio_id is None
    if portfolio_id is not None:
        before = get(uow.session, portfolio_id, lock=True)
        if check_version is None:
            raise ValueError("Portfolio updates require a version check")
        check_version(before.row_version)
    duplicate = uow.session.scalar(select(portfolio.c.id).where(portfolio.c.code == body.code))
    if duplicate is not None and duplicate != portfolio_id:
        raise Problem("validation-failed", "This portfolio code is already used.")
    values = body.model_dump()
    if creating:
        portfolio_id = new_id()
        uow.session.execute(
            insert(portfolio).values(
                tenant_id=uow.principal.tenant_id,
                id=portfolio_id,
                **values,
                created_at=uow.now,
                created_by=uow.principal.id,
                created_by_kind=uow.principal.kind.value,
                updated_at=uow.now,
                updated_by=uow.principal.id,
                updated_by_kind=uow.principal.kind.value,
            )
        )
    else:
        uow.session.execute(
            update(portfolio)
            .where(portfolio.c.id == portfolio_id)
            .values(
                **values,
                updated_at=uow.now,
                updated_by=uow.principal.id,
                updated_by_kind=uow.principal.kind.value,
            )
        )
    assert portfolio_id is not None
    record_facts(
        uow,
        action="portfolio.create" if creating else "portfolio.update",
        object_type="portfolio",
        ids=[portfolio_id],
        detail=values,
    )
    return get(uow.session, portfolio_id)


def change_member(
    uow: UnitOfWork,
    portfolio_id: UUID,
    *,
    contract_id: UUID | None = None,
    member_id: UUID | None = None,
    remove: bool = False,
    rationale: str,
    check_version: Callable[[int], None],
) -> PortfolioMemberOut:
    current = get(uow.session, portfolio_id, lock=True)
    check_version(current.row_version)
    if remove:
        active = (
            uow.session.execute(
                members(portfolio_id).where(portfolio_member.c.contract_id == contract_id)
            )
            .mappings()
            .one_or_none()
        )
        if active is None:
            raise Problem("not-found", "This contract has no current membership here.")
        member_id = active["id"]
    if member_id is not None:
        row = (
            uow.session.execute(
                members(portfolio_id, history=True).where(portfolio_member.c.id == member_id)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise Problem("not-found")
        contract_id = row["contract_id"]
        if row["valid_to_known_at"] is not None:
            raise Problem("invalid-transition", "This membership has already ended.")
        if uow.now <= row["valid_from_known_at"]:
            raise Problem("invalid-transition", "Membership must end after its start.")
    if contract_id is None:
        raise ValueError("A member command must identify its contract")
    header = repo.get_contract(uow.session, contract_id)
    require_for_entity(uow.ctx, WRITE, header["contracting_entity_id"])
    joining = member_id is None
    if joining:
        if (
            uow.session.execute(
                members(portfolio_id).where(portfolio_member.c.contract_id == contract_id)
            ).first()
            is not None
        ):
            raise Problem("invalid-transition", "This contract is already a current member.")
        member_id = new_id()
        uow.session.execute(
            insert(portfolio_member).values(
                tenant_id=uow.principal.tenant_id,
                id=member_id,
                portfolio_id=portfolio_id,
                contract_id=contract_id,
                valid_from_known_at=uow.now,
                created_at=uow.now,
                created_by=uow.principal.id,
                created_by_kind=uow.principal.kind.value,
            )
        )
    else:
        uow.session.execute(
            update(portfolio_member)
            .where(portfolio_member.c.id == member_id)
            .values(valid_to_known_at=uow.now)
        )
    assert member_id is not None
    touch(uow, portfolio_id)
    record_facts(
        uow,
        action="portfolio.member_join" if joining else "portfolio.member_leave",
        object_type="portfolio_member",
        ids=[member_id],
        contract_ids=[contract_id],
        detail={"portfolio_id": str(portfolio_id), "rationale": rationale},
    )
    row = (
        uow.session.execute(
            members(portfolio_id, history=True).where(portfolio_member.c.id == member_id)
        )
        .mappings()
        .one()
    )
    return PortfolioMemberOut.model_validate(row)


def require_estimate_scope(
    session: Session, ctx: RequestContext, portfolio_id: UUID, permission: str
) -> None:
    """Shared estimate evidence requires every historical member's permission.

    Comparing the retained population with the contract join detects RLS-hidden members.
    Keeping former members in scope prevents removing one to reveal its shared evidence.
    No population count or hidden contract identity is returned in a refusal.
    """
    get(session, portfolio_id)
    expected = session.scalar(
        select(func.count())
        .select_from(portfolio_member)
        .where(portfolio_member.c.portfolio_id == portfolio_id)
    )
    visible = session.execute(members(portfolio_id, history=True)).mappings().all()
    if len(visible) != expected:
        raise Problem("not-found")
    require_for_entity(ctx, permission, None)
    for entity_id in {row["contracting_entity_id"] for row in visible}:
        require_for_entity(ctx, permission, entity_id)


def get_estimate_definition(
    session: Session, ctx: RequestContext, portfolio_id: UUID, estimate_id: UUID
) -> EstimateOut:
    require_estimate_scope(session, ctx, portfolio_id, "contract.read")
    row = (
        session.execute(
            select(estimate).where(
                estimate.c.id == estimate_id, estimate.c.portfolio_id == portfolio_id
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return estimates.estimate_outs(session, [dict(row)])[0]


def create_estimate_definition(
    uow: UnitOfWork,
    portfolio_id: UUID,
    body: PortfolioEstimateIn,
    *,
    check_version: Callable[[int], None],
) -> EstimateOut:
    current = get(uow.session, portfolio_id, lock=True)
    check_version(current.row_version)
    require_estimate_scope(uow.session, uow.ctx, portfolio_id, WRITE)
    # The response contains shared evidence too, including any existing version summaries.
    require_estimate_scope(uow.session, uow.ctx, portfolio_id, "contract.read")
    if (
        uow.session.execute(
            select(estimate.c.id).where(
                estimate.c.portfolio_id == portfolio_id,
                estimate.c.element_code == body.element_code,
            )
        ).first()
        is not None
    ):
        raise Problem("validation-failed", "This portfolio already has that estimate code.")
    estimate_id = new_id()
    uow.session.execute(
        insert(estimate).values(
            tenant_id=uow.principal.tenant_id,
            id=estimate_id,
            portfolio_id=portfolio_id,
            contract_id=None,
            obligation_id=None,
            estimate_kind=body.estimate_kind,
            element_code=body.element_code,
            method=body.method.value,
            direction="INCREASE",
            allocation_target="CONTRACT",
            target_obligation_ids=[],
            created_at=uow.now,
            created_by=uow.principal.id,
            created_by_kind=uow.principal.kind.value,
        )
    )
    touch(uow, portfolio_id)
    record_facts(
        uow,
        action="estimate.create",
        object_type="estimate",
        ids=[estimate_id],
        detail={"portfolio_id": str(portfolio_id), **body.model_dump(mode="json")},
    )
    return get_estimate_definition(uow.session, uow.ctx, portfolio_id, estimate_id)
