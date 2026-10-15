"""Atomic narrative proposal evidence; no acceptance or accounting commands."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Literal
from uuid import UUID

from erev_engine.canonical import sha256_hex
from erev_engine.currencies import ISO_4217
from erev_engine.money import EXACT_PLACES
from sqlalchemy import insert, null, select

from erev_api.audit.writer import record
from erev_api.db import new_id
from erev_api.db.tables import ai_proposal, calc_trace, obligation_version
from erev_api.domain.ai.attempts import record_attempt
from erev_api.domain.ai.narratives import PreparedNarrative, prepare_narrative
from erev_api.domain.ai.ports import AIResponse
from erev_api.enums import PrincipalKind
from erev_api.explain import service, store
from erev_api.uow import UnitOfWork


class ProposalEvidenceRefused(ValueError):
    """Fixed evidence error without source text."""


def record_narrative(
    uow: UnitOfWork,
    *,
    prepared: PreparedNarrative,
    response: AIResponse,
    provider: Literal["fake", "anthropic"],
) -> UUID:
    """Revalidate the immutable trace, then buffer log/proposal/audit atomically.

    Caller owns fresh authorization, the scoped USER unit of work and its commit
    before releasing the budget lease. The proposal's subject is the retained trace;
    citations identify its nodes. A failure stores no rejected provider narrative.
    """
    principal = uow.principal
    if (
        principal.kind is not PrincipalKind.USER
        or principal.id is None
        or not {"ai.use", "contract.read"}.issubset(principal.permissions)
    ):
        raise ProposalEvidenceRefused("AI_PROPOSAL_USER_REQUIRED")
    # A broad principal must not reopen source records beyond either required grant.
    for permission in ("ai.use", "contract.read"):
        held = principal.permission_scopes.get(permission, frozenset())
        if not held or (
            held != "*"
            and (principal.entity_scope == "*" or not set(principal.entity_scope).issubset(held))
        ):
            raise ProposalEvidenceRefused("AI_PROPOSAL_SCOPE_REQUIRED")
    row = (
        uow.session.execute(
            select(calc_trace).where(
                calc_trace.c.tenant_id == principal.tenant_id,
                calc_trace.c.id == prepared.trace_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise ProposalEvidenceRefused("AI_TRACE_UNAVAILABLE")
    trace = store.trace_from_row(dict(row))
    # Root identity is part of the hashed request, not an independently supplied id.
    try:
        root = json.loads(prepared.request.messages[0]["content"])["facts"]["root_node_id"]
        if not isinstance(root, str):
            raise ValueError("root")
        explanation = service.build_explain(trace, root)
        precision = (
            ISO_4217[explanation.currency].minor_unit
            if explanation.currency is not None
            else EXACT_PLACES
        )
        rebuilt = prepare_narrative(
            explanation=explanation,
            trace_id=prepared.trace_id,
            minor_unit=precision,
            model=prepared.request.model,
            max_tokens=prepared.request.max_tokens,
            redact_contact_details=prepared.request.parameters["redact_contact_details"],
        )
    except (ValueError, KeyError, IndexError, TypeError):
        raise ProposalEvidenceRefused("AI_TRACE_EVIDENCE_MISMATCH") from None
    if rebuilt.request != prepared.request:
        raise ProposalEvidenceRefused("AI_TRACE_EVIDENCE_MISMATCH")
    # Use the rebuilt immutable evidence, never the caller's mutable/forged values.
    selected = rebuilt.select(response)
    contracts = tuple(
        uow.session.scalars(
            select(obligation_version.c.contract_id)
            .where(
                obligation_version.c.tenant_id == principal.tenant_id,
                obligation_version.c.contract_version_id == row["contract_version_id"],
            )
            .distinct()
        )
    )
    if not contracts:
        raise ProposalEvidenceRefused("AI_TRACE_CONTRACTS_UNAVAILABLE")
    log_id = record_attempt(
        uow,
        request=rebuilt.request,
        response=response,
        provider=provider,
        outcome="SUCCESS" if selected.proposed else "ERROR",
        failure=None
        if selected.proposed
        else ("refusal" if selected.problem_code == "AI_REFUSAL" else "invalid_output"),
    )
    proposal_id = new_id()
    status = "proposed" if selected.proposed else "failed"
    content = {"narrative": list(selected.narrative)} if selected.proposed else {}
    citations = [
        {"ref_type": "record", "ref_id": str(prepared.trace_id), "node_id": node}
        for node in selected.node_ids
    ]
    uow.session.execute(
        insert(ai_proposal).values(
            tenant_id=principal.tenant_id,
            id=proposal_id,
            kind="NUMBER_EXPLANATION",
            status=status,
            subject_type="calc_trace",
            subject_id=prepared.trace_id,
            content=content,
            citations=citations,
            ai_model_log_id=log_id,
            expires_at=uow.now + timedelta(days=30),
            problem=null() if selected.proposed else {"code": selected.problem_code},
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind="USER",
            updated_at=uow.now,
            updated_by=principal.id,
            updated_by_kind="USER",
        )
    )
    record(
        uow,
        action="ai_proposal.create",
        object_type="ai_proposal",
        object_id=proposal_id,
        after={"kind": "NUMBER_EXPLANATION", "status": status},
        detail={
            "ai_model_log_id": str(log_id),
            "trace_id": str(prepared.trace_id),
            "content_sha256": sha256_hex(content),
            "citations_sha256": sha256_hex(citations),
        },
        contract_ids=contracts,
    )
    return proposal_id
