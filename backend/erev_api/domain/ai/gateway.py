"""Persisted-job narrative calls with committed starts and bounded recovery.

Public submission, durable admission failures, notifications and reconciliation of
unknown outcomes/usage remain responsibilities of the unfinished job workflow.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import select

from erev_api.db.session import tenant_session
from erev_api.db.tables import ai_call_intent, ai_model_log, ai_proposal, calc_trace
from erev_api.domain.ai.access import AIAccessRefused, authorize_job, visible_narrative_trace
from erev_api.domain.ai.access import AICancelled as AICancelled
from erev_api.domain.ai.access import require_not_cancelled as require_not_cancelled
from erev_api.domain.ai.attempts import (
    PROVIDER_FAILURE_CODES,
    AttemptEvidenceRefused,
    record_attempt,
    record_intent,
)
from erev_api.domain.ai.attempts import RETRYABLE_PROVIDER_CODES as _RETRYABLE_PROVIDER_CODES
from erev_api.domain.ai.budget import AIBudgetRefused, budget_guard
from erev_api.domain.ai.document_retrieval import RetrievedExtraction
from erev_api.domain.ai.extraction_recovery import RecoveredExtraction
from erev_api.domain.ai.ports import AIProvider, AIResponse, AIUsage, ProviderError
from erev_api.domain.ai.preparation import PreparationRefused
from erev_api.domain.ai.proposals import (
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
    expected_trace_id: UUID | None = None


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
            **(
                {"expected_trace_id": str(source.expected_trace_id)}
                if source.expected_trace_id is not None
                else {}
            ),
        }
    )


class _ProviderAttemptFailed(ProviderError):
    """Internal retry evidence; exception text remains a safe provider code."""

    def __init__(
        self, error: ProviderError, log_id: UUID, retrieved: RetrievedNarrative, attempt_no: int
    ) -> None:
        code = error.code if error.code in PROVIDER_FAILURE_CODES else "AI_PROVIDER_ERROR"
        super().__init__(
            code,
            retryable=error.retryable and error.code in _RETRYABLE_PROVIDER_CODES,
            usage=error.usage,
        )
        self.attempt_no = attempt_no
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
        retrieved = retrieve_narrative(
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
        if (
            source.expected_trace_id is not None
            and retrieved.prepared.trace_id != source.expected_trace_id
        ):
            raise PreparationRefused("AI_INPUT_CHANGED")
        return retrieved

    def _record_error(
        self,
        context: JobContext,
        retrieved: RetrievedNarrative | RetrievedExtraction | RecoveredExtraction,
        *,
        response: AIResponse | None,
        timeout: bool = False,
        invalidated: bool = False,
        latency_ms: int = 0,
        intent_id: UUID,
        error: ProviderError | None = None,
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
                intent_id=intent_id,
                usage=error.usage if error else None,
                provider_failure_code=(
                    error.code if error.code in PROVIDER_FAILURE_CODES else "AI_PROVIDER_ERROR"
                )
                if error
                else None,
                provider_retryable=bool(
                    error and error.retryable and error.code in _RETRYABLE_PROVIDER_CODES
                ),
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
            or (
                source.expected_trace_id is not None
                and row["subject_id"] != source.expected_trace_id
            )
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
                    visible_narrative_trace(),
                )
            )
        if visible is None:
            raise AIAccessRefused("AI_TRACE_UNAVAILABLE")
        return UUID(str(row["id"]))

    def _previous(
        self, context: JobContext, source: NarrativeSource, max_tokens: int
    ) -> Mapping[str, Any] | None:
        with context.read_session() as session:
            row = (
                session.execute(
                    select(
                        ai_call_intent,
                        ai_model_log.c.id.label("log_id"),
                        ai_model_log.c.created_at.label("outcome_at"),
                        ai_model_log.c.model_id,
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
        if row is None:
            return None
        if (
            row["source_sha256"] != source_sha256(source, max_tokens)
            or row["provider"] != self.provider
            or row["created_by"] != context.principal.on_behalf_of_id
        ):
            raise PreparationRefused("AI_JOB_INPUT_CHANGED")
        if row["log_id"] is None:
            raise AttemptEvidenceRefused("AI_OUTCOME_UNKNOWN")
        parameters = row["parameters"]
        code = parameters.get("provider_failure_code")
        if (
            code not in PROVIDER_FAILURE_CODES
            or type(parameters.get("provider_retryable")) is not bool
        ):
            raise AttemptEvidenceRefused("AI_RECOVERY_REQUIRED")
        return dict(row)

    def _resume_failure(
        self,
        context: JobContext,
        source: NarrativeSource,
        max_tokens: int,
        previous: Mapping[str, Any],
    ) -> _ProviderAttemptFailed:
        fresh = retrieve_narrative(
            context,
            object_type=source.object_type,
            object_id=source.object_id,
            measure=source.measure,
            period=source.period,
            book_code=source.book_code,
            as_of=source.as_of,
            known_at=source.known_at,
            model=previous["model_id"],
            max_tokens=max_tokens,
            redact_contact_details=previous["parameters"]["redact_contact_details"],
        )
        if fresh.prepared.request.input_sha256 != previous["input_sha256"]:
            raise PreparationRefused("AI_INPUT_CHANGED")
        return _ProviderAttemptFailed(
            ProviderError(
                previous["parameters"]["provider_failure_code"],
                retryable=previous["parameters"]["provider_retryable"],
                usage=AIUsage(previous["input_tokens"], previous["output_tokens"])
                if previous["parameters"].get("usage_evidence") == "REPORTED"
                else None,
            ),
            UUID(str(previous["log_id"])),
            fresh,
            previous["attempt_no"],
        )

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
            require_not_cancelled(context)
            previous = self._previous(context, source, max_tokens)
            if previous is not None and (
                previous["attempt_no"] >= 3
                or not previous["parameters"]["provider_retryable"]
                or previous["parameters"]["provider_failure_code"] not in _RETRYABLE_PROVIDER_CODES
            ):
                raise self._resume_failure(context, source, max_tokens, previous)
            settings = self._settings(context)
            guard.require_available(
                now=context.clock.now(), monthly_budget=settings.monthly_token_budget
            )
            retrieved = self._retrieve(context, source, settings, max_tokens)
            if self._settings(context) != settings:
                raise AISettingsRefused("AI_CONFIGURATION_CHANGED")
            # No provider is constructed until the persisted job, current grants,
            # effective settings, source reads and budget have all been admitted.
            require_not_cancelled(context)
            provider = self.provider_factory()
            with system_unit_of_work(
                context.runtime,
                retrieved.principal,
                request_id=f"ai-intent-{context.job_id}",
                clock=context.clock,
            ) as uow:
                intent_id = record_intent(
                    uow,
                    request=retrieved.prepared.request,
                    provider=self.provider,
                    job_id=context.job_id,
                    source_sha256=source_sha256(source, max_tokens),
                )
                uow.commit()
            guard.bind_intent(intent_id)
            attempt_no = 1 if previous is None else previous["attempt_no"] + 1
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
                    intent_id=intent_id,
                    error=error,
                )
                raise _ProviderAttemptFailed(error, log_id, retrieved, attempt_no) from None
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
                self._record_error(
                    context, retrieved, response=response, invalidated=True, intent_id=intent_id
                )
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
                    intent_id=intent_id,
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
        # A new worker also observes the remaining backoff of a committed failure.
        # No transaction or budget lease survives into the injected wait.
        with context.read_session() as session:
            authorize_job(context, session)
            completed = session.scalar(
                select(ai_proposal.c.id).where(
                    ai_proposal.c.tenant_id == context.tenant_id,
                    ai_proposal.c.job_id == context.job_id,
                )
            )
        if completed is None:
            require_not_cancelled(context)
        resumed_previous = (
            None if completed is not None else self._previous(context, source, max_tokens)
        )
        if (
            resumed_previous is not None
            and resumed_previous["attempt_no"] < 3
            and resumed_previous["parameters"]["provider_retryable"]
            and resumed_previous["parameters"]["provider_failure_code"] in _RETRYABLE_PROVIDER_CODES
        ):
            due = resumed_previous["outcome_at"] + timedelta(
                seconds=5 * 2 ** (resumed_previous["attempt_no"] - 1)
            )
            remaining = due - context.clock.now()
            if remaining > timedelta():
                wait(remaining)
        for _ in range(3):
            try:
                return self.run_narrative_attempt(context, source, max_tokens=max_tokens)
            except _ProviderAttemptFailed as failure:
                if failure.retryable and failure.attempt_no < 3:
                    require_not_cancelled(context)
                    wait(timedelta(seconds=5 * 2 ** (failure.attempt_no - 1)))
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
