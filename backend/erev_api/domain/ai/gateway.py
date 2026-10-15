"""One persisted-job narrative attempt: admission, provider work and durable evidence.

Retry scheduling, terminal failed proposals for admission/provider errors, public
submission and crash recovery remain responsibilities of the unfinished job handler.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID

from erev_api.domain.ai.access import AIAccessRefused, authorize_job
from erev_api.domain.ai.attempts import record_attempt
from erev_api.domain.ai.budget import AIBudgetRefused, budget_guard
from erev_api.domain.ai.ports import AIProvider, AIResponse, ProviderError
from erev_api.domain.ai.preparation import PreparationRefused
from erev_api.domain.ai.proposals import record_narrative
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
    ) -> None:
        # This is accounting for a call already authorized/made, not permission to
        # retain its narrative. Keep known usage even if a switch changed mid-call.
        with system_unit_of_work(
            context.runtime,
            retrieved.principal,
            request_id=f"ai-attempt-{context.job_id}",
            clock=context.clock,
        ) as uow:
            record_attempt(
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

    def run_narrative_attempt(
        self, context: JobContext, source: NarrativeSource, *, max_tokens: int
    ) -> UUID:
        """Run one attempt, keeping the tenant budget lease through committed usage.

        No DB transaction spans provider execution. ProviderError remains typed for
        the future retry policy; a busy budget lease is a deferral, not a model call.
        No retries or model fallback happen in this method.
        """
        with context.read_session() as session:
            principal = authorize_job(context, session)
        settings = self._settings(context)
        with budget_guard(principal.db_context) as guard:
            if guard is None:
                raise AIBudgetRefused("AI_BUDGET_BUSY")
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
                self._record_error(
                    context,
                    retrieved,
                    response=None,
                    timeout=error.code == "AI_TIMEOUT",
                    latency_ms=elapsed,
                )
                raise
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
                    uow, prepared=fresh.prepared, response=response, provider=self.provider
                )
                uow.commit()
            return proposal
