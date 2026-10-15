"""Retained AI evidence reads with current source authorization."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.auth.principal import Principal
from erev_api.db.session import tenant_session
from erev_api.db.tables import ai_proposal, calc_trace
from erev_api.domain.ai.access import AIAccessRefused, narrative_reader, visible_narrative_trace
from erev_api.domain.platform import actors
from erev_api.problems import Problem
from erev_api.schemas.ai import AIProposalOut


def proposal(principal: Principal, proposal_id: UUID) -> AIProposalOut:
    """Read only supported evidence; AI switches do not revoke retained source access."""
    with tenant_session(principal.db_context, read_only=True) as session:
        return proposal_in(session, principal, proposal_id)


def proposal_in(
    session: Session, principal: Principal, proposal_id: UUID, *, lock: bool = False
) -> AIProposalOut:
    """Apply both grants in SQL, including inside a command's existing transaction."""
    try:
        reader = narrative_reader(principal)
    except AIAccessRefused as exc:
        raise Problem("forbidden", "AI source read permission is required.") from exc
    statement = (
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
            ai_proposal.c.id == proposal_id,
            ai_proposal.c.kind == "NUMBER_EXPLANATION",
            ai_proposal.c.subject_type == "calc_trace",
            visible_narrative_trace(reader.entity_scope),
        )
    )
    if lock:
        statement = statement.with_for_update(of=ai_proposal)
    row = session.execute(statement).mappings().one_or_none()
    if row is None:
        raise Problem("not-found", "AI proposal not found.")
    data = dict(row)
    for name, lookup in (("created_by", "creator"), ("updated_by", "updater")):
        data[name] = actors.actor(row[name], row[f"{name}_kind"], row[lookup])
    data["rejected_by"] = (
        None
        if row["rejected_by"] is None
        else actors.actor(row["rejected_by"], "USER", row["rejector"])
    )
    return AIProposalOut.model_validate(data)
