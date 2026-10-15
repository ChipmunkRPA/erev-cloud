"""Atomic, hashes-only attempt evidence and its AUD-FACT summary (T-AI-02)."""

from __future__ import annotations

import re
from hashlib import sha256
from typing import Literal
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import insert

from erev_api.audit.writer import record_facts
from erev_api.db import new_id
from erev_api.db.tables import ai_model_log
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


class AttemptEvidenceRefused(ValueError):
    """Fixed failure code; never contains request/response text or provider errors."""


def record_attempt(
    uow: UnitOfWork,
    *,
    request: AIRequest,
    provider: Literal["fake", "anthropic"],
    outcome: Outcome,
    response: AIResponse | None = None,
    failure: Failure | None = None,
    latency_ms: int = 0,
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
    log_id = new_id()
    uow.session.execute(
        insert(ai_model_log).values(
            tenant_id=principal.tenant_id,
            id=log_id,
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
