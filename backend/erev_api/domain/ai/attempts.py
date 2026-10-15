"""Atomic, hashes-only attempt evidence and its AUD-FACT summary (T-AI-02)."""

from __future__ import annotations

import re
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import insert, select

from erev_api.audit.writer import record_facts
from erev_api.db import new_id
from erev_api.db.tables import ai_call_intent, ai_model_log, job
from erev_api.domain.ai.ports import AIRequest, AIResponse
from erev_api.enums import PrincipalKind
from erev_api.uow import UnitOfWork

Outcome = Literal["SUCCESS", "ERROR", "TIMEOUT", "BUDGET_EXCEEDED", "DISABLED"]
Failure = Literal[
    "provider_error", "invalid_output", "refusal", "timeout", "budget_exhausted", "disabled"
]
_DETAILS = {
    "SUCCESS": frozenset({None}),
    "ERROR": frozenset({"provider_error", "invalid_output", "refusal"}),
    "TIMEOUT": frozenset({"timeout"}),
    "BUDGET_EXCEEDED": frozenset({"budget_exhausted"}),
    "DISABLED": frozenset({"disabled"}),
}
_PARAMETERS = frozenset(
    {"template_sha256", "send_contract_text", "redact_contact_details", "max_tokens"}
)


PROVIDER_FAILURE_CODES = frozenset(
    {
        "AI_MODEL_NOT_FOUND",
        "AI_TIMEOUT",
        "AI_RATE_LIMIT",
        "AI_PROVIDER_UNAVAILABLE",
        "AI_CONNECTION",
        "AI_BAD_REQUEST",
        "AI_AUTHENTICATION",
        "AI_PERMISSION",
        "AI_PROVIDER_ERROR",
        "AI_INVALID_RESPONSE",
    }
)


RETRYABLE_PROVIDER_CODES = frozenset(
    {
        "AI_TIMEOUT",
        "AI_RATE_LIMIT",
        "AI_PROVIDER_UNAVAILABLE",
        "AI_CONNECTION",
    }
)


class AttemptEvidenceRefused(ValueError):
    """Fixed failure code; never contains request/response text or provider errors."""


def _request_parameters(request: AIRequest) -> dict[str, Any]:
    parameters = dict(request.parameters)
    if (
        set(parameters) != _PARAMETERS
        or any(
            type(parameters[name]) is not bool
            for name in ("send_contract_text", "redact_contact_details")
        )
        or type(request.max_tokens) is not int
        or request.max_tokens < 1
        or type(parameters["max_tokens"]) is not int
        or parameters["max_tokens"] != request.max_tokens
        or not isinstance(parameters["template_sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", parameters["template_sha256"]) is None
        or type(request.template_version) is not int
        or request.template_version < 1
        or re.fullmatch(r"[a-z][a-z0-9-]*", request.template_id) is None
        or not request.model.strip()
    ):
        raise AttemptEvidenceRefused("AI_INVALID_ATTEMPT_CONFIGURATION")
    try:
        expected = sha256_hex(
            {
                "template_id": request.template_id,
                "template_version": request.template_version,
                "model": request.model,
                "parameters": parameters,
                "system": request.system,
                "messages": request.messages,
                "max_tokens": request.max_tokens,
            }
        )
    except (ValueError, TypeError, RecursionError):
        raise AttemptEvidenceRefused("AI_INVALID_ATTEMPT_CONFIGURATION") from None
    if expected != request.input_sha256:
        raise AttemptEvidenceRefused("AI_REQUEST_HASH_MISMATCH")
    return parameters


def record_attempt(
    uow: UnitOfWork,
    *,
    request: AIRequest,
    provider: Literal["fake", "anthropic"],
    outcome: Outcome,
    response: AIResponse | None = None,
    failure: Failure | None = None,
    latency_ms: int = 0,
    intent_id: UUID | None = None,
    provider_failure_code: str | None = None,
    provider_retryable: bool = False,
) -> UUID:
    """Insert evidence and buffer its audit event in the caller's transaction.

    The gateway supplies its freshly authorized USER unit of work and owns commit
    before releasing the budget lease. This function neither calls a provider nor
    accepts a proposal. Metadata fields are allow-listed; arbitrary parameters and
    free-form failure messages cannot become retained prompt/response back doors.
    """
    principal = uow.principal
    if (
        principal.kind is not PrincipalKind.USER
        or principal.id is None
        or "ai.use" not in principal.permissions
    ):
        raise AttemptEvidenceRefused("AI_ATTEMPT_USER_REQUIRED")
    if (
        provider not in {"fake", "anthropic"}
        or outcome not in _DETAILS
        or failure not in _DETAILS[outcome]
    ):
        raise AttemptEvidenceRefused("AI_INVALID_ATTEMPT_OUTCOME")
    if (outcome == "SUCCESS" and response is None) or (
        outcome in {"BUDGET_EXCEEDED", "DISABLED"} and response is not None
    ):
        raise AttemptEvidenceRefused("AI_INVALID_ATTEMPT_RESPONSE")
    parameters = _request_parameters(request)
    if provider_failure_code is not None:
        if (
            provider_failure_code not in PROVIDER_FAILURE_CODES
            or (provider_retryable and provider_failure_code not in RETRYABLE_PROVIDER_CODES)
            or response is not None
            or type(provider_retryable) is not bool
            or outcome != ("TIMEOUT" if provider_failure_code == "AI_TIMEOUT" else "ERROR")
            or failure != ("timeout" if provider_failure_code == "AI_TIMEOUT" else "provider_error")
        ):
            raise AttemptEvidenceRefused("AI_INVALID_PROVIDER_FAILURE")
        parameters["provider_failure_code"] = provider_failure_code
        parameters["provider_retryable"] = provider_retryable
    elif provider_retryable:
        raise AttemptEvidenceRefused("AI_INVALID_PROVIDER_FAILURE")
    input_tokens = output_tokens = 0
    response_hash = None
    if response is not None:
        if re.fullmatch(r"[A-Za-z0-9._:-]{1,256}", response.model) is None:
            raise AttemptEvidenceRefused("AI_INVALID_RESPONSE_MODEL")
        try:
            response_hash = sha256(response.text.encode("utf-8")).hexdigest()
        except UnicodeEncodeError:
            raise AttemptEvidenceRefused("AI_INVALID_RESPONSE_ENCODING") from None
        if response_hash != response.response_sha256:
            raise AttemptEvidenceRefused("AI_RESPONSE_HASH_MISMATCH")
        parameters["response_model"] = response.model
        input_tokens, output_tokens = response.input_tokens, response.output_tokens
        latency_ms = response.latency_ms
    if any(
        type(value) is not int or not 0 <= value <= 2147483647
        for value in (input_tokens, output_tokens, latency_ms)
    ):
        raise AttemptEvidenceRefused("AI_INVALID_ATTEMPT_COUNTERS")
    if intent_id is not None:
        intent = (
            uow.session.execute(
                select(ai_call_intent).where(
                    ai_call_intent.c.tenant_id == principal.tenant_id,
                    ai_call_intent.c.id == intent_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if (
            intent is None
            or intent["provider"] != provider
            or intent["input_sha256"] != request.input_sha256
            or intent["created_by"] != principal.id
            or intent["created_by_kind"] != "USER"
            or outcome in {"BUDGET_EXCEEDED", "DISABLED"}
        ):
            raise AttemptEvidenceRefused("AI_INTENT_MISMATCH")
        if (
            uow.session.scalar(
                select(ai_model_log.c.id).where(
                    ai_model_log.c.tenant_id == principal.tenant_id,
                    ai_model_log.c.intent_id == intent_id,
                )
            )
            is not None
        ):
            raise AttemptEvidenceRefused("AI_INTENT_ALREADY_RECORDED")
    # Zero-valued compatibility counters alone never prove zero provider usage.
    # Derive this evidence here, after validating the response, rather than trust
    # caller-supplied request parameters or infer it from a retryable error code.
    parameters["usage_evidence"] = (
        "REPORTED"
        if response is not None
        else "NOT_SENT"
        if outcome in {"BUDGET_EXCEEDED", "DISABLED"}
        else "UNKNOWN"
    )
    log_id = new_id()
    uow.session.execute(
        insert(ai_model_log).values(
            tenant_id=principal.tenant_id,
            id=log_id,
            intent_id=intent_id,
            provider=provider,
            model_id=request.model,
            prompt_template_id=request.template_id,
            prompt_template_version=str(request.template_version),
            parameters=parameters,
            input_sha256=request.input_sha256,
            response_sha256=response_hash,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            outcome=outcome,
            error_detail=failure,
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
        )
    )
    record_facts(
        uow,
        action="ai_model_log.record",
        object_type="ai_model_log",
        ids=[log_id],
        detail={"outcome": outcome, "input_tokens": input_tokens, "output_tokens": output_tokens},
    )
    return log_id


def record_intent(
    uow: UnitOfWork,
    *,
    request: AIRequest,
    provider: Literal["fake", "anthropic"],
    job_id: UUID,
    source_sha256: str,
) -> UUID:
    """Reserve the next immutable call start; the caller commits before calling the provider.

    Lock the persisted job to serialize starts. An unresolved prior start is uncertain,
    never a zero-usage failure. This writer does not decide whether a known error is retryable;
    the gateway must retain and enforce that classification before requesting another start.
    """
    principal = uow.principal
    if (
        principal.kind is not PrincipalKind.USER
        or principal.id is None
        or "ai.use" not in principal.permissions
    ):
        raise AttemptEvidenceRefused("AI_ATTEMPT_USER_REQUIRED")
    _request_parameters(request)
    if (
        provider not in {"fake", "anthropic"}
        or re.fullmatch(r"[0-9a-f]{64}", source_sha256) is None
    ):
        raise AttemptEvidenceRefused("AI_INVALID_INTENT_CONFIGURATION")
    owned = uow.session.scalar(
        select(job.c.id)
        .where(
            job.c.tenant_id == principal.tenant_id,
            job.c.id == job_id,
            job.c.kind == "AI_TASK",
            job.c.state == "RUNNING",
            job.c.created_by_kind == "USER",
            job.c.created_by == principal.id,
        )
        .with_for_update()
    )
    if owned is None:
        raise AttemptEvidenceRefused("AI_INVALID_JOB_BINDING")
    previous = (
        uow.session.execute(
            select(
                ai_call_intent,
                ai_model_log.c.id.label("log_id"),
            )
            .outerjoin(
                ai_model_log,
                (ai_model_log.c.tenant_id == ai_call_intent.c.tenant_id)
                & (ai_model_log.c.intent_id == ai_call_intent.c.id),
            )
            .where(
                ai_call_intent.c.tenant_id == principal.tenant_id,
                ai_call_intent.c.job_id == job_id,
            )
            .order_by(ai_call_intent.c.attempt_no)
        )
        .mappings()
        .all()
    )
    for number, row in enumerate(previous, start=1):
        if (
            row["attempt_no"] != number
            or row["provider"] != provider
            or row["input_sha256"] != request.input_sha256
            or row["source_sha256"] != source_sha256
            or row["created_by"] != principal.id
        ):
            raise AttemptEvidenceRefused("AI_JOB_INPUT_CHANGED")
        if row["log_id"] is None:
            raise AttemptEvidenceRefused("AI_OUTCOME_UNKNOWN")
    if len(previous) >= 3:
        raise AttemptEvidenceRefused("AI_ATTEMPTS_EXHAUSTED")
    intent_id = new_id()
    uow.session.execute(
        insert(ai_call_intent).values(
            tenant_id=principal.tenant_id,
            id=intent_id,
            job_id=job_id,
            attempt_no=len(previous) + 1,
            provider=provider,
            input_sha256=request.input_sha256,
            source_sha256=source_sha256,
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind="USER",
        )
    )
    record_facts(
        uow,
        action="ai_call_intent.record",
        object_type="ai_call_intent",
        ids=[intent_id],
        detail={"job_id": str(job_id), "attempt_no": len(previous) + 1},
    )
    return intent_id
