"""API-R-47 AI submission and retained evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from erev_api.enums import AiFieldDecision, AiProposalStatus
from erev_api.schemas.common import ActorOut
from erev_api.schemas.contracts import ContractCreateIn
from erev_api.schemas.explain import ExplainObjectType


class AIExplanationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_type: ExplainObjectType
    id: UUID
    measure: str = Field(min_length=1, max_length=128)
    period: str | None = Field(default=None, min_length=1, max_length=100)


class AIContractExtractionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: UUID


class AIProposalEvidenceOut(BaseModel):
    """Common retained proposal metadata."""

    id: UUID
    status: AiProposalStatus
    job_id: UUID | None
    citations: list[dict[str, Any]]
    ai_model_log_id: UUID
    expires_at: datetime
    problem: dict[str, Any] | None
    created_at: datetime
    created_by: ActorOut
    updated_at: datetime
    updated_by: ActorOut
    row_version: int
    rejected_by: ActorOut | None
    rejected_at: datetime | None
    rejection_reason: str | None


class AIProposalOut(AIProposalEvidenceOut):
    """Retained number-explanation evidence authorized through its source trace."""

    kind: Literal["NUMBER_EXPLANATION"]
    subject_type: Literal["calc_trace"]
    subject_id: UUID
    content: dict[str, Any]


class AIExtractionProposalOut(AIProposalEvidenceOut):
    """Extraction suggestions remain review evidence, never accepted contract values."""

    kind: Literal["CONTRACT_EXTRACTION"]
    file_object_id: UUID
    document_text_file_id: UUID
    content: list[dict[str, Any]]
    accepted_command: str | None
    field_decisions: list[dict[str, Any]] | None
    accepted_object_type: str | None
    accepted_object_id: UUID | None
    accepted_by: ActorOut | None
    accepted_at: datetime | None


class AIProposalRejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(min_length=1, max_length=4000)


class AIDocumentPageOut(BaseModel):
    page_no: int
    text: str


class AIDocumentTextOut(BaseModel):
    proposal_id: UUID
    file_object_id: UUID
    pages: list[AIDocumentPageOut]


class AIFieldDecisionIn(BaseModel):
    """An explicit human decision; values remain uncoerced JSON for typed field checks."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=128)
    decision: AiFieldDecision
    value: Any = None
    reason: str | None = Field(default=None, max_length=4000)

    @field_validator("reason")
    @classmethod
    def reason_text(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not value or "\x00" in value:
                raise ValueError("Provide a nonblank review reason.")
        return value

    @model_validator(mode="after")
    def explicit_decision(self) -> Self:
        if self.decision is AiFieldDecision.EDIT:
            if "value" not in self.model_fields_set:
                raise ValueError("An edit requires an explicit value.")
        elif "value" in self.model_fields_set:
            raise ValueError("Only an edit may supply a replacement value.")
        if self.decision in (AiFieldDecision.EDIT, AiFieldDecision.REJECT) and self.reason is None:
            raise ValueError("Edits and rejections require a reason.")
        return self


class AIExtractionDraftIn(BaseModel):
    """Explicit draft inputs for review; this model does not enable acceptance."""

    model_config = ConfigDict(extra="forbid")

    command: Literal["contract.create_draft"]
    entity_code: str = Field(min_length=1, max_length=255)
    field_decisions: tuple[AIFieldDecisionIn, ...] = Field(min_length=1, max_length=507)
    draft: ContractCreateIn
    line_bindings: dict[str, str] = Field(default_factory=dict, max_length=500)
    header_bindings: dict[
        Literal["customer_name", "effective_date", "payment_terms"],
        Literal["customer", "inception_date", "signature_date", "payment_terms"],
    ] = Field(default_factory=dict, max_length=3)

    @model_validator(mode="after")
    def explicit_draft(self) -> Self:
        if self.draft.submit_for_activation:
            raise ValueError("AI review may create only a draft.")
        if self.entity_code != self.draft.contracting_entity_code:
            raise ValueError("The review entity must match the draft entity.")
        keys = {line.obligation_key for line in self.draft.lines}
        targets = list(self.line_bindings.values())
        if len(set(targets)) != len(targets) or not set(targets).issubset(keys):
            raise ValueError("Each line binding must name a different draft obligation key.")
        return self


class AIProposalAcceptedOut(BaseModel):
    contract_id: UUID


class AIModelLogOut(BaseModel):
    """Immutable call configuration evidence; never prompt or response content."""

    id: UUID
    provider: Literal["fake", "anthropic"]
    model_id: str
    prompt_template_id: str
    prompt_template_version: str
    parameters: dict[str, Any]
    input_sha256: str
    response_sha256: str | None
    usage_known: bool
    input_tokens: int
    output_tokens: int
    latency_ms: int
    outcome: Literal["SUCCESS", "ERROR", "TIMEOUT", "BUDGET_EXCEEDED", "DISABLED"]
    error_detail: str | None
    created_at: datetime
    created_by: ActorOut
