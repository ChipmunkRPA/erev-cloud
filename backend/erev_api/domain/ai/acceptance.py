"""Human extraction acceptance through the normal draft command in one transaction."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.audit.writer import record
from erev_api.auth.dependencies import require_for_entity
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import customer, legal_entity
from erev_api.db.transitions import apply
from erev_api.domain.ai.draft_review import review_draft
from erev_api.domain.ai.field_review import FieldReviewRefused
from erev_api.domain.ai.queries import proposal_detail_in
from erev_api.domain.contracts import combination, holds
from erev_api.domain.contracts import commands as contracts
from erev_api.domain.platform import attachments
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.ai import AIExtractionDraftIn, AIExtractionProposalOut, AIProposalAcceptedOut
from erev_api.uow import UnitOfWork


def access(
    session: Session,
    ctx: RequestContext,
    proposal_id: UUID,
    body: AIExtractionDraftIn,
    *,
    lock: bool = False,
) -> AIExtractionProposalOut:
    """Recheck both permissions and source/entity access even before idempotent replay."""
    if "contract.create" not in ctx.principal.permissions:
        raise Problem("forbidden")
    proposal = proposal_detail_in(session, ctx, proposal_id, lock=lock)
    if not isinstance(proposal, AIExtractionProposalOut):
        raise Problem("not-found")
    entity_id = session.scalar(
        select(legal_entity.c.id).where(legal_entity.c.code == body.entity_code)
    )
    if entity_id is None:
        raise Problem("not-found")
    require_for_entity(ctx, "ai.use", entity_id)
    require_for_entity(ctx, "contract.create", entity_id)
    return proposal


def accept_draft(
    uow: UnitOfWork,
    proposal_id: UUID,
    body: AIExtractionDraftIn,
    *,
    check_version: Callable[[int], None],
) -> AIProposalAcceptedOut:
    current = access(uow.session, uow.ctx, proposal_id, body, lock=True)
    check_version(current.row_version)
    if current.status != "proposed" or current.expires_at <= uow.now:
        raise Problem("invalid-transition", "Only an unexpired proposed item can be accepted.")
    resolved = None
    if body.draft.customer_id is not None:
        row = uow.session.execute(
            select(customer.c.id, customer.c.name).where(customer.c.id == body.draft.customer_id)
        ).one_or_none()
        if row is not None:
            resolved = (row.id, row.name)
    try:
        reviewed = review_draft(current.content, body, resolved_customer=resolved)
        if not reviewed.values:
            raise FieldReviewRefused("AI_REVIEW_EMPTY_ACCEPTANCE")
    except FieldReviewRefused as error:
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(
                    field="field_decisions",
                    rule_id=str(error),
                    message="Decide every field and match the draft to its reviewed values.",
                )
            ],
        ) from None
    created = contracts.create_contract(uow, body=body.draft)
    attachments.attach(
        uow,
        file_object_id=current.file_object_id,
        subject_type="contract",
        subject_id=created.id,
        description="Source document for accepted AI extraction",
    )
    combination.raise_suggestions(uow, created.id)
    holds.apply_rule_holds(uow, created.id)
    apply(
        uow.session,
        "ai_proposal",
        proposal_id,
        to_status="accepted",
        expected_status="proposed",
        expected_row_version=current.row_version,
        set_values={
            "accepted_command": "contract.create_draft",
            "field_decisions": list(reviewed.decisions),
            "accepted_object_type": "contract",
            "accepted_object_id": created.id,
            "accepted_by": uow.principal.id,
            "accepted_at": uow.now,
            "updated_by": uow.principal.id,
            "updated_by_kind": "USER",
            "updated_at": uow.now,
            "row_version": current.row_version + 1,
        },
    )
    record(
        uow,
        action="ai_proposal.accept",
        object_type="ai_proposal",
        object_id=proposal_id,
        before={"status": "proposed"},
        after={"status": "accepted"},
        contract_id=created.id,
        detail={
            "command": "contract.create_draft",
            "field_decisions_sha256": sha256_hex(list(reviewed.decisions)),
        },
    )
    return AIProposalAcceptedOut(contract_id=created.id)
