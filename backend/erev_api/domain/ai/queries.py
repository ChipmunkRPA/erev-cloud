"""Retained AI evidence reads with current source authorization."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from erev_api.auth.principal import Principal, RequestContext
from erev_api.db.session import tenant_session
from erev_api.db.tables import ai_proposal, calc_trace
from erev_api.domain.ai.access import AIAccessRefused, narrative_reader, visible_narrative_trace
from erev_api.domain.platform import actors, file_access
from erev_api.domain.platform.approval_queries import Page
from erev_api.enums import PrincipalKind
from erev_api.problems import Problem
from erev_api.schemas.ai import AIExtractionProposalOut, AIProposalOut


def proposal(principal: Principal, proposal_id: UUID) -> AIProposalOut:
    """Read only supported evidence; AI switches do not revoke retained source access."""
    with tenant_session(principal.db_context, read_only=True) as session:
        return proposal_in(session, principal, proposal_id)


def proposal_in(
    session: Session, principal: Principal, proposal_id: UUID, *, lock: bool = False
) -> AIProposalOut:
    """Apply both grants in SQL, including inside a command's existing transaction."""
    statement = proposal_statement(principal).where(ai_proposal.c.id == proposal_id)
    if lock:
        statement = statement.with_for_update(of=ai_proposal)
    row = session.execute(statement).mappings().one_or_none()
    if row is None:
        raise Problem("not-found", "AI proposal not found.")
    return proposal_out(dict(row))


def _actor_data(row: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(row)
    for name, lookup in (("created_by", "creator"), ("updated_by", "updater")):
        data[name] = actors.actor(row[name], row[f"{name}_kind"], row[lookup])
    data["rejected_by"] = (
        None
        if row["rejected_by"] is None
        else actors.actor(row["rejected_by"], "USER", row["rejector"])
    )
    return data


def proposal_out(row: Mapping[str, Any]) -> AIProposalOut:
    return AIProposalOut.model_validate(_actor_data(row))


def proposal_statement(principal: Principal) -> Select[Any]:
    """Authorize before paging or counting, using the same source predicate as detail reads."""
    try:
        reader = narrative_reader(principal)
    except AIAccessRefused as exc:
        raise Problem("forbidden", "AI source read permission is required.") from exc
    return (
        select(
            ai_proposal,
            actors.named(ai_proposal.c.created_by, tenant_id=ai_proposal.c.tenant_id).label(
                "creator"
            ),
            actors.named(ai_proposal.c.updated_by, tenant_id=ai_proposal.c.tenant_id).label(
                "updater"
            ),
            actors.named(ai_proposal.c.rejected_by, tenant_id=ai_proposal.c.tenant_id).label(
                "rejector"
            ),
        )
        .select_from(
            ai_proposal.join(
                calc_trace,
                (calc_trace.c.tenant_id == ai_proposal.c.tenant_id)
                & (calc_trace.c.id == ai_proposal.c.subject_id),
            )
        )
        .where(
            ai_proposal.c.tenant_id == reader.tenant_id,
            ai_proposal.c.kind == "NUMBER_EXPLANATION",
            ai_proposal.c.subject_type == "calc_trace",
            visible_narrative_trace(reader.entity_scope),
        )
    )


def list_proposals[P: Page](
    principal: Principal, *, page: Callable[[Session, Select[Any]], P]
) -> tuple[P, list[AIProposalOut]]:
    statement = proposal_statement(principal)
    with tenant_session(principal.db_context, read_only=True) as session:
        result = page(session, statement)
        return result, [proposal_out(row) for row in result.items]


def proposal_detail(
    ctx: RequestContext, proposal_id: UUID
) -> AIProposalOut | AIExtractionProposalOut:
    """Authorize extraction source metadata before selecting any suggestions or citations."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return proposal_detail_in(session, ctx, proposal_id)


def proposal_detail_in(
    session: Session, ctx: RequestContext, proposal_id: UUID, *, lock: bool = False
) -> AIProposalOut | AIExtractionProposalOut:
    """Authorize retained evidence inside the reader or review command transaction."""
    principal = ctx.principal
    held = principal.permission_scopes.get("ai.use", frozenset())
    if (
        principal.kind is not PrincipalKind.USER
        or principal.id is None
        or "ai.use" not in principal.permissions
        or not held
        or (
            held != "*"
            and (principal.entity_scope == "*" or not set(principal.entity_scope).issubset(held))
        )
    ):
        raise Problem("forbidden")
    binding = (
        session.execute(
            select(ai_proposal.c.kind, ai_proposal.c.file_object_id).where(
                ai_proposal.c.tenant_id == principal.tenant_id,
                ai_proposal.c.id == proposal_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if binding is None:
        raise Problem("not-found", "AI proposal not found.")
    if binding["kind"] != "CONTRACT_EXTRACTION":
        return proposal_in(session, principal, proposal_id, lock=lock)
    source = file_access.bound(session, ctx, binding["file_object_id"])
    if (
        source is None
        or source["shredded_at"] is not None
        or source["purpose"] != "ATTACHMENT"
        or source["media_type"] != "application/pdf"
    ):
        raise Problem("not-found", "AI proposal not found.")
    statement = select(
        ai_proposal,
        actors.named(ai_proposal.c.created_by, tenant_id=ai_proposal.c.tenant_id).label("creator"),
        actors.named(ai_proposal.c.updated_by, tenant_id=ai_proposal.c.tenant_id).label("updater"),
        actors.named(ai_proposal.c.rejected_by, tenant_id=ai_proposal.c.tenant_id).label(
            "rejector"
        ),
    ).where(ai_proposal.c.tenant_id == principal.tenant_id, ai_proposal.c.id == proposal_id)
    if lock:
        statement = statement.with_for_update(of=ai_proposal)
    row = session.execute(statement).mappings().one()
    return AIExtractionProposalOut.model_validate(_actor_data(dict(row)))
