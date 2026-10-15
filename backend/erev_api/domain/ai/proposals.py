"""Atomic narrative proposal evidence; no acceptance or accounting commands."""

from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Literal
from uuid import UUID

from erev_engine.canonical import sha256_hex
from erev_engine.currencies import ISO_4217
from erev_engine.money import EXACT_PLACES
from sqlalchemy import insert, null, select

from erev_api.audit.writer import record
from erev_api.db import new_id
from erev_api.db.tables import (
    ai_call_intent,
    ai_model_log,
    ai_proposal,
    calc_trace,
    job,
    obligation_version,
)
from erev_api.domain.ai.attempts import PROVIDER_FAILURE_CODES, record_attempt
from erev_api.domain.ai.narratives import NarrativeSelection, PreparedNarrative, prepare_narrative
from erev_api.domain.ai.ports import AIRequest, AIResponse
from erev_api.enums import PrincipalKind
from erev_api.explain import service, store
from erev_api.uow import UnitOfWork


class ProposalEvidenceRefused(ValueError):
    """Fixed evidence error without source text."""


def _evidence(
    uow: UnitOfWork, prepared: PreparedNarrative
) -> tuple[PreparedNarrative, tuple[UUID, ...]]:
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
    return rebuilt, contracts


def require_intent_binding(
    uow: UnitOfWork,
    intent_id: UUID | None,
    job_id: UUID | None,
    source_sha256: str | None,
    input_sha256: str,
) -> None:
    if intent_id is None:
        return
    if (
        job_id is None
        or source_sha256 is None
        or uow.session.scalar(
            select(ai_call_intent.c.id).where(
                ai_call_intent.c.tenant_id == uow.principal.tenant_id,
                ai_call_intent.c.id == intent_id,
                ai_call_intent.c.job_id == job_id,
                ai_call_intent.c.source_sha256 == source_sha256,
                ai_call_intent.c.input_sha256 == input_sha256,
                ai_call_intent.c.created_by == uow.principal.id,
            )
        )
        is None
    ):
        raise ProposalEvidenceRefused("AI_INVALID_INTENT_BINDING")


def require_job_binding(
    uow: UnitOfWork, job_id: UUID | None, job_source_sha256: str | None
) -> None:
    """A proposal is bound to the initiating human's running AI job."""
    principal = uow.principal
    if (job_id is None) != (job_source_sha256 is None) or (
        job_source_sha256 is not None and re.fullmatch(r"[0-9a-f]{64}", job_source_sha256) is None
    ):
        raise ProposalEvidenceRefused("AI_INVALID_JOB_BINDING")
    if job_id is not None:
        owned = uow.session.scalar(
            select(job.c.id).where(
                job.c.tenant_id == principal.tenant_id,
                job.c.id == job_id,
                job.c.kind == "AI_TASK",
                job.c.created_by == principal.id,
                job.c.created_by_kind == "USER",
                job.c.state == "RUNNING",
            )
        )
        if owned is None:
            raise ProposalEvidenceRefused("AI_INVALID_JOB_BINDING")


def record_narrative(
    uow: UnitOfWork,
    *,
    prepared: PreparedNarrative,
    response: AIResponse,
    provider: Literal["fake", "anthropic"],
    job_id: UUID | None = None,
    job_source_sha256: str | None = None,
    intent_id: UUID | None = None,
) -> UUID:
    """Revalidate the immutable trace, then buffer log/proposal/audit atomically.

    Caller owns fresh authorization, the scoped USER unit of work and its commit
    before releasing the budget lease. The proposal's subject is the retained trace;
    citations identify its nodes. A failure stores no rejected provider narrative.
    """
    rebuilt, contracts = _evidence(uow, prepared)
    require_intent_binding(uow, intent_id, job_id, job_source_sha256, rebuilt.request.input_sha256)
    selected = rebuilt.select(response)
    log_id = record_attempt(
        uow,
        request=rebuilt.request,
        intent_id=intent_id,
        response=response,
        provider=provider,
        outcome="SUCCESS" if selected.proposed else "ERROR",
        failure=None
        if selected.proposed
        else ("refusal" if selected.problem_code == "AI_REFUSAL" else "invalid_output"),
    )
    return _insert_narrative(uow, rebuilt, log_id, selected, contracts, job_id, job_source_sha256)


def _insert_narrative(
    uow: UnitOfWork,
    prepared: PreparedNarrative,
    log_id: UUID,
    selected: NarrativeSelection,
    contracts: tuple[UUID, ...],
    job_id: UUID | None,
    job_source_sha256: str | None,
) -> UUID:
    principal = uow.principal
    require_job_binding(uow, job_id, job_source_sha256)
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
            job_id=job_id,
            job_source_sha256=job_source_sha256,
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


def require_failure_binding(
    uow: UnitOfWork,
    *,
    request: AIRequest,
    log_id: UUID,
    provider: Literal["fake", "anthropic"],
    code: str,
    job_id: UUID | None,
    job_source_sha256: str | None,
) -> UUID | None:
    """Validate a retained provider failure against its request, human and job intent."""
    if code not in PROVIDER_FAILURE_CODES:
        raise ProposalEvidenceRefused("AI_INVALID_PROVIDER_FAILURE")
    log = (
        uow.session.execute(
            select(ai_model_log).where(
                ai_model_log.c.tenant_id == uow.principal.tenant_id,
                ai_model_log.c.id == log_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    expected_parameters = dict(request.parameters)
    expected = {
        "created_by": uow.principal.id,
        "created_by_kind": "USER",
        "provider": provider,
        "input_sha256": request.input_sha256,
        "response_sha256": None,
        "model_id": request.model,
        "prompt_template_id": request.template_id,
        "prompt_template_version": str(request.template_version),
        "parameters": expected_parameters,
        "input_tokens": 0,
        "output_tokens": 0,
        "outcome": "TIMEOUT" if code == "AI_TIMEOUT" else "ERROR",
        "error_detail": "timeout" if code == "AI_TIMEOUT" else "provider_error",
    }
    if log is not None and "provider_failure_code" in log["parameters"]:
        if type(log["parameters"].get("provider_retryable")) is not bool:
            raise ProposalEvidenceRefused("AI_ATTEMPT_EVIDENCE_MISMATCH")
        expected_parameters.update(
            provider_failure_code=code,
            provider_retryable=log["parameters"].get("provider_retryable"),
        )
    if log is not None and "usage_evidence" in log["parameters"]:
        # Failure counters can be reported without retaining a response body.
        reported = log["parameters"]["usage_evidence"] == "REPORTED"
        expected_parameters["usage_evidence"] = "REPORTED" if reported else "UNKNOWN"
        if reported:
            expected["input_tokens"] = log["input_tokens"]
            expected["output_tokens"] = log["output_tokens"]
    if log is None or any(log[key] != value for key, value in expected.items()):
        raise ProposalEvidenceRefused("AI_ATTEMPT_EVIDENCE_MISMATCH")
    require_intent_binding(uow, log["intent_id"], job_id, job_source_sha256, request.input_sha256)
    return None if log["intent_id"] is None else UUID(str(log["intent_id"]))


def record_provider_failure(
    uow: UnitOfWork,
    *,
    prepared: PreparedNarrative,
    log_id: UUID,
    provider: Literal["fake", "anthropic"],
    code: str,
    job_id: UUID | None = None,
    job_source_sha256: str | None = None,
) -> UUID:
    """Finalize a provider failure using its already committed attempt, without relogging it."""
    rebuilt, contracts = _evidence(uow, prepared)
    require_failure_binding(
        uow,
        request=rebuilt.request,
        log_id=log_id,
        provider=provider,
        code=code,
        job_id=job_id,
        job_source_sha256=job_source_sha256,
    )
    return _insert_narrative(
        uow,
        rebuilt,
        log_id,
        NarrativeSelection(False, (), (), code),
        contracts,
        job_id,
        job_source_sha256,
    )
