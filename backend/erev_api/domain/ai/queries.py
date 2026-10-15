"""Retained AI evidence reads with current source authorization."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from erev_api.auth.principal import Principal
from erev_api.db.session import tenant_session
from erev_api.db.tables import ai_proposal, calc_trace
from erev_api.domain.ai.access import AIAccessRefused, narrative_reader, visible_narrative_trace
from erev_api.domain.platform import actors
from erev_api.problems import Problem
from erev_api.schemas.ai import AIProposalOut


def proposal(principal: Principal, proposal_id: UUID) -> AIProposalOut:
    """Read only supported evidence; AI switches do not revoke retained source access."""
    try:
        reader = narrative_reader(principal)
    except AIAccessRefused as exc:
        raise Problem("forbidden", "AI source read permission is required.") from exc
    with tenant_session(reader.db_context, read_only=True) as session:
        row = (
            session.execute(
                select(
                    ai_proposal,
                    actors.named(ai_proposal.c.created_by, tenant_id=ai_proposal.c.tenant_id).label(
                        "creator"
                    ),
                    actors.named(ai_proposal.c.updated_by, tenant_id=ai_proposal.c.tenant_id).label(
                        "updater"
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
                    visible_narrative_trace(),
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise Problem("not-found", "AI proposal not found.")
        data = dict(row)
        for name, lookup in (("created_by", "creator"), ("updated_by", "updater")):
            data[name] = actors.actor(row[name], row[f"{name}_kind"], row[lookup])
        return AIProposalOut.model_validate(data)
