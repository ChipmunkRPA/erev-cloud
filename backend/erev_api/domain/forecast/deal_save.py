"""Save a verified preview once as a draft in its active registered scenario."""

from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from erev_api.db.session import DbContext, set_tenant_context
from erev_api.db.tables import deal_preview, scenario, tenant
from erev_api.domain.contracts import combination, commands, holds, queries
from erev_api.domain.forecast import deal_bundle
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.contracts import ContractCreateIn, ContractOut
from erev_api.schemas.deal_previews import DealInputIn
from erev_api.uow import UnitOfWork


def active_scenario(session: Session, context: DbContext, *, lock: bool = False) -> bool:
    parent = session.execute(
        select(tenant.c.source_tenant_id).where(
            tenant.c.id == context.tenant_id,
            tenant.c.kind == "sandbox",
            tenant.c.status == "ACTIVE",
        )
    ).scalar_one_or_none()
    found = None
    if parent is not None:
        set_tenant_context(
            session, DbContext(tenant_id=parent, user_id=context.user_id, entity_scope="*")
        )
        try:
            statement = select(scenario.c.id).where(
                scenario.c.tenant_id == parent,
                scenario.c.scenario_tenant_id == context.tenant_id,
                scenario.c.status == "ACTIVE",
            )
            # Save holds the pointer through commit; a read only advertises current eligibility.
            if lock:
                statement = statement.with_for_update(read=True)
            found = session.scalar(statement)
        finally:
            set_tenant_context(session, context)
    return found is not None


def _active_scenario(uow: UnitOfWork) -> None:
    if not active_scenario(uow.session, uow.principal.db_context, lock=True):
        raise Problem(
            "invalid-transition",
            "A preview can only be saved in its active registered scenario.",
            errors=[ProblemError(rule_id="DEAL_PREVIEW_SAVE_NOT_ALLOWED")],
        )


def save(uow: UnitOfWork, preview_id: UUID, external_id: str) -> ContractOut:
    _active_scenario(uow)
    row = (
        uow.session.execute(
            select(deal_preview)
            .where(
                deal_preview.c.tenant_id == uow.principal.tenant_id, deal_preview.c.id == preview_id
            )
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    proposal = DealInputIn.model_validate(row["input"]["proposal"])
    deal_bundle.authorize(uow, proposal)
    if row["saved_contract_id"] is not None:
        raise Problem("invalid-transition", "This preview has already been saved as a contract.")
    if (
        sha256_hex(row["input"]) != row["input_sha256"]
        or sha256_hex(row["result"]) != row["result_sha256"]
    ):
        raise Problem("precondition-failed", "The retained preview evidence failed verification.")
    booking = deal_bundle.booking(proposal, preview_id).model_copy(
        update={"external_id": external_id}
    )
    # Ordinary creation validates contract.create for the contracting entity and current reference
    # data. Its new provisional computation is not represented as the original preview result.
    created = commands.create_contract(
        uow, body=ContractCreateIn.model_validate(booking.model_dump())
    )
    combination.raise_suggestions(uow, created.id)
    if holds.apply_rule_holds(uow, created.id):
        created = queries.contract_out(uow.session, created.id, now=uow.now)
    uow.session.execute(
        update(deal_preview)
        .where(deal_preview.c.id == preview_id)
        .values(saved_contract_id=created.id)
    )
    uow.audit(
        action="deal_preview.save",
        object_type="deal_preview",
        object_id=preview_id,
        before={"saved_contract_id": None},
        after={"saved_contract_id": str(created.id)},
        contract_id=created.id,
    )
    return created
