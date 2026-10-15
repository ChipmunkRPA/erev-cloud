"""Recover extraction evidence under current source access without invoking a provider."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select

from erev_api.auth.principal import Principal
from erev_api.db.tables import ai_call_intent, ai_model_log, ai_proposal
from erev_api.domain.ai.access import authorize_job
from erev_api.domain.ai.attempts import PROVIDER_FAILURE_CODES, AttemptEvidenceRefused
from erev_api.domain.ai.document_preparation import PreparedExtraction
from erev_api.domain.ai.extraction_proposals import restore_extraction
from erev_api.domain.ai.ports import AIUsage, ProviderError
from erev_api.domain.ai.preparation import PreparationRefused
from erev_api.domain.ai.proposals import require_failure_binding
from erev_api.jobs.context import JobContext, system_unit_of_work


@dataclass(frozen=True, slots=True)
class RecoveredExtraction:
    principal: Principal
    prepared: PreparedExtraction
    text_id: UUID
    intent_id: UUID
    log_id: UUID
    attempt_no: int
    outcome_at: datetime
    proposal_id: UUID | None
    failure: ProviderError | None


def recover_extraction(
    context: JobContext,
    *,
    document_id: UUID,
    source_sha256: str,
    job_source_sha256: str,
    allowed_paths: frozenset[str],
    max_tokens: int,
    provider: Literal["fake", "anthropic"],
) -> RecoveredExtraction | None:
    """Find the last durable outcome and restore its exact request, never reparse or resend.

    Completed results and failure evidence can be read while AI is disabled, but only by
    the currently authorized initiating human with source access. The gateway must separately
    admit any new attempt, enforce remaining backoff and budget, and settle cancellation.
    """
    with context.read_session() as session:
        principal = authorize_job(context, session)
        intent = (
            session.execute(
                select(
                    ai_call_intent,
                    ai_model_log.c.id.label("log_id"),
                    ai_model_log.c.created_at.label("outcome_at"),
                    ai_model_log.c.model_id,
                    ai_model_log.c.prompt_template_id,
                    ai_model_log.c.prompt_template_version,
                    ai_model_log.c.parameters,
                    ai_model_log.c.input_tokens,
                    ai_model_log.c.output_tokens,
                )
                .outerjoin(
                    ai_model_log,
                    (ai_model_log.c.tenant_id == ai_call_intent.c.tenant_id)
                    & (ai_model_log.c.intent_id == ai_call_intent.c.id),
                )
                .where(
                    ai_call_intent.c.tenant_id == context.tenant_id,
                    ai_call_intent.c.job_id == context.job_id,
                )
                .order_by(ai_call_intent.c.attempt_no.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        proposal = (
            session.execute(
                select(
                    ai_proposal.c.id,
                    ai_proposal.c.kind,
                    ai_proposal.c.job_source_sha256,
                    ai_proposal.c.file_object_id,
                    ai_proposal.c.document_text_file_id,
                    ai_proposal.c.ai_model_log_id,
                    ai_proposal.c.created_by,
                    ai_proposal.c.created_by_kind,
                ).where(
                    ai_proposal.c.tenant_id == context.tenant_id,
                    ai_proposal.c.job_id == context.job_id,
                )
            )
            .mappings()
            .one_or_none()
        )
    if intent is None:
        if proposal is not None:
            raise AttemptEvidenceRefused("AI_RECOVERY_REQUIRED")
        return None
    if (
        intent["source_sha256"] != job_source_sha256
        or intent["file_object_id"] != document_id
        or intent["document_text_file_id"] is None
        or intent["provider"] != provider
        or intent["created_by"] != principal.id
        or intent["created_by_kind"] != "USER"
    ):
        raise PreparationRefused("AI_JOB_INPUT_CHANGED")
    if intent["log_id"] is None:
        raise AttemptEvidenceRefused("AI_OUTCOME_UNKNOWN")
    if intent["prompt_template_id"] != "contract-review":
        raise AttemptEvidenceRefused("AI_RECOVERY_REQUIRED")
    parameters = intent["parameters"]
    try:
        version = int(intent["prompt_template_version"])
        if (
            str(version) != intent["prompt_template_version"]
            or type(parameters["redact_contact_details"]) is not bool
            or parameters["send_contract_text"] is not True
            or type(parameters["max_tokens"]) is not int
            or parameters["max_tokens"] != max_tokens
        ):
            raise ValueError("invalid extraction parameters")
    except (KeyError, TypeError, ValueError):
        raise AttemptEvidenceRefused("AI_RECOVERY_REQUIRED") from None
    text_id, intent_id, log_id = (
        UUID(str(intent[name])) for name in ("document_text_file_id", "id", "log_id")
    )
    if proposal is not None and (
        proposal["kind"] != "CONTRACT_EXTRACTION"
        or proposal["job_source_sha256"] != job_source_sha256
        or proposal["file_object_id"] != document_id
        or proposal["document_text_file_id"] != text_id
        or proposal["ai_model_log_id"] != log_id
        or proposal["created_by"] != principal.id
        or proposal["created_by_kind"] != "USER"
    ):
        raise PreparationRefused("AI_JOB_INPUT_CHANGED")
    failure = None
    with system_unit_of_work(
        context.runtime,
        principal,
        request_id=f"ai-extraction-recovery-{context.job_id}",
        clock=context.clock,
    ) as uow:
        prepared = restore_extraction(
            uow,
            document_id=document_id,
            text_id=text_id,
            source_sha256=source_sha256,
            job_id=context.job_id,
            job_source_sha256=job_source_sha256,
            intent_id=intent_id,
            input_sha256=intent["input_sha256"],
            allowed_paths=allowed_paths,
            model=intent["model_id"],
            max_tokens=max_tokens,
            redact_contact_details=parameters["redact_contact_details"],
            template_version=version,
        )
        if proposal is None:
            code = parameters.get("provider_failure_code")
            if (
                code not in PROVIDER_FAILURE_CODES
                or type(parameters.get("provider_retryable")) is not bool
            ):
                raise AttemptEvidenceRefused("AI_RECOVERY_REQUIRED")
            require_failure_binding(
                uow,
                request=prepared.request,
                log_id=log_id,
                provider=provider,
                code=code,
                job_id=context.job_id,
                job_source_sha256=job_source_sha256,
                file_object_id=document_id,
                document_text_file_id=text_id,
            )
            failure = ProviderError(
                code,
                retryable=parameters["provider_retryable"],
                usage=AIUsage(intent["input_tokens"], intent["output_tokens"])
                if parameters.get("usage_evidence") == "REPORTED"
                else None,
            )
    return RecoveredExtraction(
        principal,
        prepared,
        text_id,
        intent_id,
        log_id,
        intent["attempt_no"],
        intent["outcome_at"],
        None if proposal is None else UUID(str(proposal["id"])),
        failure,
    )
