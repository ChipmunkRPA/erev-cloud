"""Worker entry point for persisted narrative and extraction AI tasks.

Submission and human review remain separate workflows. The gateway owns provider
retries and durable recovery; the job runner must not multiply those attempts.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    TypeAdapter,
    ValidationError,
)

from erev_api.domain.ai.extraction_gateway import ExtractionGateway, ExtractionSource
from erev_api.domain.ai.gateway import (
    AICancelled,
    AiGateway,
    NarrativeSource,
    require_not_cancelled,
)
from erev_api.enums import JobKind
from erev_api.jobs.context import JobContext
from erev_api.jobs.registry import JobOutcome, RetryPolicy, task
from erev_api.schemas.explain import ExplainObjectType


class NarrativeTask(BaseModel):
    """Only source selectors enter the queue; prompts and provider settings do not."""

    model_config = ConfigDict(extra="forbid")
    operation: Literal["narrative"]
    object_type: ExplainObjectType
    object_id: UUID
    measure: str = Field(min_length=1, max_length=128)
    period: str | None = None
    book_code: str | None = None
    as_of: date | None = None
    known_at: AwareDatetime | None = None
    expected_trace_id: UUID | None = None
    max_tokens: StrictInt = Field(gt=0)

    def source(self) -> NarrativeSource:
        return NarrativeSource(
            object_type=self.object_type,
            object_id=self.object_id,
            measure=self.measure,
            period=self.period,
            book_code=self.book_code,
            as_of=self.as_of,
            known_at=self.known_at,
            expected_trace_id=self.expected_trace_id,
        )


class ExtractionTask(BaseModel):
    """Server-selected source/hash and field paths; no prompt, model or document text."""

    model_config = ConfigDict(extra="forbid")
    operation: Literal["extraction"]
    file_id: UUID
    file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    allowed_paths: frozenset[Annotated[str, Field(min_length=1, max_length=128)]] = Field(
        min_length=1, max_length=128
    )
    max_tokens: StrictInt = Field(gt=0)

    def source(self) -> ExtractionSource:
        return ExtractionSource(self.file_id, self.file_sha256, self.allowed_paths)


_TASK: TypeAdapter[NarrativeTask | ExtractionTask] = TypeAdapter(
    Annotated[NarrativeTask | ExtractionTask, Field(discriminator="operation")]
)


_gateway: AiGateway | None = None
_wait: Callable[[timedelta], None] | None = None


def configure(gateway: AiGateway, wait: Callable[[timedelta], None]) -> None:
    """Bind worker-owned services without importing adapters into the domain."""
    global _gateway, _wait
    _gateway, _wait = gateway, wait


def retry_wait(context: JobContext, delay: timedelta, wait: Callable[[timedelta], None]) -> None:
    """Wait without a transaction, noticing cancellation at one-second boundaries."""
    remaining = delay
    while remaining > timedelta():
        context.heartbeat()
        require_not_cancelled(context)
        chunk = min(remaining, timedelta(seconds=1))
        wait(chunk)
        remaining -= chunk
    context.heartbeat()
    require_not_cancelled(context)


@task(JobKind.AI_TASK, retry=RetryPolicy(max_attempts=1))
def run(context: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    try:
        request = _TASK.validate_python(params)
    except ValidationError:
        # Pydantic errors include input values; never persist them in job diagnostics.
        raise ValueError("AI_INVALID_TASK") from None
    gateway, wait = _gateway, _wait
    if gateway is None or wait is None:
        raise RuntimeError("AI_WORKER_NOT_CONFIGURED")
    try:
        if isinstance(request, ExtractionTask):
            if not isinstance(gateway, ExtractionGateway):
                raise RuntimeError("AI_EXTRACTION_WORKER_NOT_CONFIGURED")
            proposal_id = gateway.run_extraction(
                context,
                request.source(),
                max_tokens=request.max_tokens,
                wait=lambda delay: retry_wait(context, delay, wait),
            )
        else:
            proposal_id = gateway.run_narrative(
                context,
                request.source(),
                max_tokens=request.max_tokens,
                wait=lambda delay: retry_wait(context, delay, wait),
            )
    except AICancelled:
        # The registry reads the durable cancellation flag and settles CANCELLED.
        # No synthetic proposal or successful model result is created here.
        return JobOutcome(state="SUCCEEDED", result={"cancelled": True})
    # A failed provider result may itself be a durably completed proposal. Job
    # completion reports persistence, never acceptance or accounting approval.
    return JobOutcome(state="SUCCEEDED", result={"proposal_id": str(proposal_id)})
