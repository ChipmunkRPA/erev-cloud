"""Immutable accepted-proposal provenance used by contract activation controls."""

from __future__ import annotations

from typing import Any, Final
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import ai_proposal, contract

AI_ASSISTED: Final = "AI_ASSISTED"


def accepted_draft_proposals(session: Session, contract_id: UUID) -> list[dict[str, Any]]:
    """Bind provenance to the visible contract's tenant; retain hashes, not quoted field text.

    Approval routing must not depend on the current draft author or current AI enablement.
    Replacing a draft never erases the accepted proposal's immutable target link.
    """
    rows = session.execute(
        select(
            ai_proposal.c.id,
            ai_proposal.c.ai_model_log_id,
            ai_proposal.c.field_decisions,
            ai_proposal.c.accepted_by,
            ai_proposal.c.accepted_at,
        )
        .join(
            contract,
            (contract.c.tenant_id == ai_proposal.c.tenant_id)
            & (contract.c.id == ai_proposal.c.accepted_object_id),
        )
        .where(
            contract.c.id == contract_id,
            ai_proposal.c.kind == "CONTRACT_EXTRACTION",
            ai_proposal.c.status == "accepted",
            ai_proposal.c.accepted_command == "contract.create_draft",
            ai_proposal.c.accepted_object_type == "contract",
        )
        .order_by(ai_proposal.c.id)
    ).mappings()
    return [
        {
            "proposal_id": str(row["id"]),
            "model_log_id": str(row["ai_model_log_id"]),
            "accepted_by": str(row["accepted_by"]),
            "accepted_at": row["accepted_at"].isoformat(),
            "field_decisions_sha256": sha256_hex(row["field_decisions"]),
        }
        for row in rows
    ]
