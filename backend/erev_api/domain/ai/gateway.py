"""One persisted-job narrative attempt: admission, provider work and durable evidence.

Public submission, durable admission failures, notifications, idempotent completion
and crash recovery remain responsibilities of the unfinished job handler.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import select

from erev_api.db.session import tenant_session
from erev_api.db.tables import ai_model_log, ai_proposal, calc_trace
from erev_api.domain.ai.access import AIAccessRefused, authorize_job
from erev_api.domain.ai.attempts import record_attempt
from erev_api.domain.ai.budget import AIBudgetRefused, budget_guard
from erev_api.domain.ai.ports import AIProvider, AIResponse, ProviderError
from erev_api.domain.ai.preparation import PreparationRefused
from erev_api.domain.ai.proposals import (
    PROVIDER_FAILURE_CODES,
    record_narrative,
    record_provider_failure,
)
from erev_api.domain.ai.retrieval import RetrievedNarrative, retrieve_narrative
from erev_api.domain.ai.settings import AISettings, AISettingsRefused, load_settings
from erev_api.jobs.context import JobContext, system_unit_of_work
from erev_api.problems import Problem
from erev_api.schemas.explain import ExplainObjectType


@dataclass(frozen=True, slots=True)
class NarrativeSource:
    object_type: ExplainObjectType
    object_id: UUID
    measure: str
    period: str | None = None
    book_code: str | None = None
    as_of: date | None = None
    known_at: datetime | None = None


def source_sha256(source: NarrativeSource, max_tokens: int) -> str:
    return sha256_hex(
        {
            "object_type": source.object_type,
            "object_id": str(source.object_id),
            "measure": source.measure,
            "period": source.period,
            "book_code": source.book_code,
            "as_of": source.as_of.isoformat() if source.as_of is not None else None,
            "known_at": source.known_at.isoformat() if source.known_at is not None else None,
            "max_tokens": max_tokens,
        }
    )


_RETRYABLE_PROVIDER_CODES = frozenset(
    {
        "AI_TIMEOUT",
        "AI_RATE_LIMIT",
        "AI_PROVIDER_UNAVAILABLE",
        "AI_CONNECTION",
    }
)


class _ProviderAttemptFailed(ProviderError):
    """Internal retry evidence; exception text remains a safe provider code."""

    def __init__(self, error: ProviderError, log_id: UUID, retrieved: RetrievedNarrative) -> None:
        code = error.code if error.code in PROVIDER_FAILURE_CODES else "AI_PROVIDER_ERROR"
        super().__init__(
            code, retryable=error.retryable and error.code in _RETRYABLE_PROVIDER_CODES
        )
        self.log_id = log_id
        self.retrieved = retrieved


class AiGateway:
    """Composition roots supply a lazy provider factory and the platform switch."""

    def __init__(
        self,
        *,
        provider: Literal["fake", "anthropic"],
        provider_factory: Callable[[], AIProvider],
        platform_kill_switch: Callable[[], bool],
    ) -> None:
        if provider not in {"fake", "anthropic"}:
            raise ValueError("AI_INVALID_PROVIDER")
        self.provider = provider
        self.provider_factory = provider_factory
        self.platform_kill_switch = platform_kill_switch

    def _settings(self, context: JobContext) -> AISettings:
        with context.read_session() as session:
            settings = load_settings(
                session,
                tenant_id=context.tenant_id,
                now=context.clock.now(),
                platform_kill_switch=self.platform_kill_switch(),
            )
        settings.require_available()
        return settings

    def _retrieve(
        self, context: JobContext, source: NarrativeSource, settings: AISettings, max_tokens: int
    ) -> RetrievedNarrative:
        return retrieve_narrative(
            context,
            object_type=source.object_type,
            object_id=source.object_id,
            measure=source.measure,
            period=source.period,
            book_code=source.book_code,
            as_of=source.as_of,
            known_at=source.known_at,
            model=settings.model,
            max_tokens=max_tokens,
            redact_contact_details=settings.redact_contact_details,
        )

    def _record_error(
        self,
        context: JobContext,
        retrieved: RetrievedNarrative,
        *,
        response: AIResponse | None,
        timeout: bool = False,
        invalidated: bool = False,
        latency_ms: int = 0,
    ) -> UUID:
        # This is accounting for a call already authorized/made, not permission to
        # retain its narrative. Keep known usage even if a switch changed mid-call.
        with system_unit_of_work(
            context.runtime,
            retrieved.principal,
            request_id=f"ai-attempt-{context.job_id}",
            clock=context.clock,
        ) as uow:
            log_id = record_attempt(
                uow,
                request=retrieved.prepared.request,
                provider=self.provider,
                response=response,
                outcome="TIMEOUT" if timeout else "ERROR",
                failure="timeout"
                if timeout
                else ("invalid_output" if invalidated else "provider_error"),
                latency_ms=latency_ms,
            )
            uow.commit()
            return log_id

    def _completed(
        self, context: JobContext, source: NarrativeSource, max_tokens: int
    ) -> UUID | None:
        with context.read_session() as session:
            row = (
                session.execute(
                    select(ai_proposal, ai_model_log.c.model_id, ai_model_log.c.parameters)
                    .join(
                        ai_model_log,
                        (ai_model_log.c.tenant_id == ai_proposal.c.tenant_id)
                        & (ai_model_log.c.id == ai_proposal.c.ai_model_log_id),
                    )
                    .where(
                        ai_proposal.c.tenant_id == context.tenant_id,
                        ai_proposal.c.job_id == context.job_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        if (
            row["job_source_sha256"] != source_sha256(source, max_tokens)
            or row["created_by"] != context.principal.on_behalf_of_id
            or row["kind"] != "NUMBER_EXPLANATION"
            or row["subject_type"] != "calc_trace"
        ):
            raise PreparationRefused("AI_JOB_INPUT_CHANGED")
        # A completed result bypasses new-call admission, never current read permissions.
        fresh = retrieve_narrative(
            context,
            object_type=source.object_type,
            object_id=source.object_id,
            measure=source.measure,
            period=source.period,
            book_code=source.book_code,
            as_of=source.as_of,
            known_at=source.known_at,
            model=row["model_id"],
            max_tokens=max_tokens,
            redact_contact_details=row["parameters"]["redact_contact_details"],
        )
        with tenant_session(fresh.principal.db_context, read_only=True) as session:
            visible = session.scalar(
                select(calc_trace.c.id).where(
                    calc_trace.c.tenant_id == context.tenant_id,
                    calc_trace.c.id == row["subject_id"],
                )
            )
        if visible is None:
            raise AIAccessRefused("AI_TRACE_UNAVAILABLE")
        return UUID(str(row["id"]))

    def run_narrative_attempt(
        self, context: JobContext, source: NarrativeSource, *, max_tokens: int
    ) -> UUID:
        """Run one attempt, keeping the tenant budget lease through committed usage.

        No DB transaction spans provider execution. ProviderError remains typed for
        the retry policy; a busy budget lease is a deferral, not a model call.
        No retries or model fallback happen in this method.
        """
        with context.read_session() as session:
            principal = authorize_job(context, session)
        with budget_guard(principal.db_context) as guard:
            if guard is None:
                raise AIBudgetRefused("AI_BUDGET_BUSY")
            completed = self._completed(context, source, max_tokens)
            if completed is not None:
                return completed
            settings = self._settings(context)
            guard.require_available(
                now=context.clock.now(), monthly_budget=settings.monthly_token_budget
            )
            retrieved = self._retrieve(context, source, settings, max_tokens)
            if self._settings(context) != settings:
                raise AISettingsRefused("AI_CONFIGURATION_CHANGED")
            # No provider is constructed until the persisted job, current grants,
            # effective settings, source reads and budget have all been admitted.
            provider = self.provider_factory()
            started = context.clock.now()
            try:
                response = provider.complete(retrieved.prepared.request)
            except ProviderError as error:
                elapsed = max(0, (context.clock.now() - started) // timedelta(milliseconds=1))
                log_id = self._record_error(
                    context,
                    retrieved,
                    response=None,
                    timeout=error.code == "AI_TIMEOUT",
                    latency_ms=elapsed,
                )
                raise _ProviderAttemptFailed(error, log_id, retrieved) from None
            try:
                if self._settings(context) != settings:
                    raise AISettingsRefused("AI_CONFIGURATION_CHANGED")
                fresh = self._retrieve(context, source, settings, max_tokens)
                if fresh.prepared.request != retrieved.prepared.request:
                    raise PreparationRefused("AI_INPUT_CHANGED")
                guard.require_available(
                    now=context.clock.now(), monthly_budget=settings.monthly_token_budget
                )
            except (
                AIAccessRefused,
                AISettingsRefused,
                PreparationRefused,
                AIBudgetRefused,
                Problem,
            ):
                self._record_error(context, retrieved, response=response, invalidated=True)
                raise
            with system_unit_of_work(
                context.runtime,
                fresh.principal,
                request_id=f"ai-proposal-{context.job_id}",
                clock=context.clock,
            ) as uow:
                proposal = record_narrative(
                    uow,
                    prepared=fresh.prepared,
                    response=response,
                    provider=self.provider,
                    job_id=context.job_id,
                    job_source_sha256=source_sha256(source, max_tokens),
                )
                uow.commit()
            return proposal

    def run_narrative(
        self,
        context: JobContext,
        source: NarrativeSource,
        *,
        max_tokens: int,
        wait: Callable[[timedelta], None],
    ) -> UUID:
        """At most three provider attempts, with 5/10-second waits (AIA-06).

        The worker supplies the wait implementation. No transaction or budget lease
        spans a wait. Every retry goes through fresh admission; a refused admission
        is propagated immediately. Permanent/exhausted provider errors yield a failed
        proposal linked to the last committed log, without duplicating usage.
        """
        for index in range(3):
            try:
                return self.run_narrative_attempt(context, source, max_tokens=max_tokens)
            except _ProviderAttemptFailed as failure:
                if failure.retryable and index < 2:
                    wait(timedelta(seconds=5 * 2**index))
                    continue
                # Reauthorize the source before persisting terminal evidence. Retain
                # the failed attempt's model/configuration, not a newer request hash.
                previous = failure.retrieved.prepared
                fresh = retrieve_narrative(
                    context,
                    object_type=source.object_type,
                    object_id=source.object_id,
                    measure=source.measure,
                    period=source.period,
                    book_code=source.book_code,
                    as_of=source.as_of,
                    known_at=source.known_at,
                    model=previous.request.model,
                    max_tokens=previous.request.max_tokens,
                    redact_contact_details=previous.request.parameters["redact_contact_details"],
                )
                if fresh.prepared.request != previous.request:
                    raise PreparationRefused("AI_INPUT_CHANGED") from None
                with system_unit_of_work(
                    context.runtime,
                    fresh.principal,
                    request_id=f"ai-failure-{context.job_id}",
                    clock=context.clock,
                ) as uow:
                    proposal = record_provider_failure(
                        uow,
                        prepared=fresh.prepared,
                        log_id=failure.log_id,
                        provider=self.provider,
                        code=failure.code,
                        job_id=context.job_id,
                        job_source_sha256=source_sha256(source, max_tokens),
                    )
                    uow.commit()
                return proposal
        raise AssertionError("bounded AI retry loop exhausted without a result")
