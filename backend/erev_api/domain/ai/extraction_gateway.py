"""Bounded extraction calls with retained input, current admission and durable recovery."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal
from uuid import UUID

from erev_engine.canonical import sha256_hex

from erev_api.domain.ai.access import AIAccessRefused, authorize_job, require_not_cancelled
from erev_api.domain.ai.attempts import (
    RETRYABLE_PROVIDER_CODES,
    AttemptEvidenceRefused,
    record_intent,
)
from erev_api.domain.ai.budget import AIBudgetRefused, budget_guard
from erev_api.domain.ai.document_retrieval import RetrievedExtraction, retrieve_document
from erev_api.domain.ai.extraction_proposals import (
    record_extraction,
    record_extraction_failure,
    restore_extraction,
    store_document_text,
)
from erev_api.domain.ai.extraction_recovery import RecoveredExtraction, recover_extraction
from erev_api.domain.ai.gateway import AiGateway
from erev_api.domain.ai.ports import AIProvider, DocumentExtractor, ProviderError
from erev_api.domain.ai.preparation import PreparationRefused
from erev_api.domain.ai.proposals import ProposalEvidenceRefused
from erev_api.domain.ai.settings import AISettingsRefused
from erev_api.jobs.context import JobContext, system_unit_of_work
from erev_api.problems import Problem


@dataclass(frozen=True, slots=True)
class ExtractionSource:
    file_id: UUID
    file_sha256: str
    allowed_paths: frozenset[str]

    def fingerprint(self, max_tokens: int) -> str:
        return sha256_hex(
            {
                "operation": "extraction",
                "file_id": str(self.file_id),
                "file_sha256": self.file_sha256,
                "allowed_paths": sorted(self.allowed_paths),
                "max_tokens": max_tokens,
            }
        )


class _RecordedFailure(Exception):
    """A provider failure was committed; re-read it before deciding to retry."""


class ExtractionGateway(AiGateway):
    def __init__(
        self,
        *,
        provider: Literal["fake", "anthropic"],
        provider_factory: Callable[[], AIProvider],
        platform_kill_switch: Callable[[], bool],
        extract_pages: DocumentExtractor,
    ) -> None:
        super().__init__(
            provider=provider,
            provider_factory=provider_factory,
            platform_kill_switch=platform_kill_switch,
        )
        self.extract_pages = extract_pages

    def _recover_extraction(
        self,
        context: JobContext,
        source: ExtractionSource,
        max_tokens: int,
    ) -> RecoveredExtraction | None:
        return recover_extraction(
            context,
            document_id=source.file_id,
            source_sha256=source.file_sha256,
            job_source_sha256=source.fingerprint(max_tokens),
            allowed_paths=source.allowed_paths,
            max_tokens=max_tokens,
            provider=self.provider,
        )

    @staticmethod
    def _terminal(previous: RecoveredExtraction) -> bool:
        failure = previous.failure
        return failure is not None and (
            previous.attempt_no >= 3
            or not failure.retryable
            or failure.code not in RETRYABLE_PROVIDER_CODES
        )

    def _extraction_attempt(
        self,
        context: JobContext,
        source: ExtractionSource,
        max_tokens: int,
    ) -> UUID:
        with context.read_session() as session:
            principal = authorize_job(context, session)
        with budget_guard(principal.db_context) as guard:
            if guard is None:
                raise AIBudgetRefused("AI_BUDGET_BUSY")
            previous = self._recover_extraction(context, source, max_tokens)
            if previous is not None and previous.proposal_id is not None:
                return previous.proposal_id
            if previous is not None and self._terminal(previous):
                assert previous.failure is not None
                with system_unit_of_work(
                    context.runtime,
                    previous.principal,
                    request_id=f"ai-failure-{context.job_id}",
                    clock=context.clock,
                ) as uow:
                    proposal = record_extraction_failure(
                        uow,
                        prepared=previous.prepared,
                        document_text_file_id=previous.text_id,
                        source_sha256=source.file_sha256,
                        log_id=previous.log_id,
                        provider=self.provider,
                        code=previous.failure.code,
                        job_id=context.job_id,
                        job_source_sha256=source.fingerprint(max_tokens),
                    )
                    uow.commit()
                return proposal
            require_not_cancelled(context)
            settings = self._settings(context)
            if not settings.send_contract_text:
                raise PreparationRefused("AI_TEXT_DISABLED")
            guard.require_available(
                now=context.clock.now(), monthly_budget=settings.monthly_token_budget
            )
            retrieved: RetrievedExtraction | RecoveredExtraction
            if previous is None:
                retrieved = retrieve_document(
                    context,
                    file_id=source.file_id,
                    allowed_paths=source.allowed_paths,
                    max_tokens=max_tokens,
                    extract_pages=self.extract_pages,
                    platform_kill_switch=self.platform_kill_switch,
                    expected_file_sha256=source.file_sha256,
                )
            else:
                retrieved = previous
                if (
                    previous.prepared.request.model != settings.model
                    or previous.prepared.request.parameters["redact_contact_details"]
                    != settings.redact_contact_details
                ):
                    raise AISettingsRefused("AI_CONFIGURATION_CHANGED")
            if self._settings(context) != settings:
                raise AISettingsRefused("AI_CONFIGURATION_CHANGED")
            require_not_cancelled(context)
            provider = self.provider_factory()
            with system_unit_of_work(
                context.runtime,
                retrieved.principal,
                request_id=f"ai-intent-{context.job_id}",
                clock=context.clock,
            ) as uow:
                if isinstance(retrieved, RetrievedExtraction):
                    text_id = store_document_text(
                        uow,
                        retrieved,
                        job_id=context.job_id,
                        job_source_sha256=source.fingerprint(max_tokens),
                    )
                else:
                    text_id = retrieved.text_id
                intent_id = record_intent(
                    uow,
                    request=retrieved.prepared.request,
                    provider=self.provider,
                    job_id=context.job_id,
                    source_sha256=source.fingerprint(max_tokens),
                    file_object_id=source.file_id,
                    document_text_file_id=text_id,
                )
                uow.commit()
            guard.bind_intent(intent_id)
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
                    intent_id=intent_id,
                    error=error,
                )
                raise _RecordedFailure() from None
            try:
                if self._settings(context) != settings:
                    raise AISettingsRefused("AI_CONFIGURATION_CHANGED")
                with context.read_session() as session:
                    fresh = authorize_job(context, session)
                guard.require_available(
                    now=context.clock.now(), monthly_budget=settings.monthly_token_budget
                )
                with system_unit_of_work(
                    context.runtime,
                    fresh,
                    request_id=f"ai-proposal-{context.job_id}",
                    clock=context.clock,
                ) as uow:
                    prepared = restore_extraction(
                        uow,
                        document_id=source.file_id,
                        text_id=text_id,
                        source_sha256=source.file_sha256,
                        job_id=context.job_id,
                        job_source_sha256=source.fingerprint(max_tokens),
                        intent_id=intent_id,
                        input_sha256=retrieved.prepared.request.input_sha256,
                        allowed_paths=source.allowed_paths,
                        model=settings.model,
                        max_tokens=max_tokens,
                        redact_contact_details=settings.redact_contact_details,
                        template_version=retrieved.prepared.request.template_version,
                    )
                    proposal = record_extraction(
                        uow,
                        prepared=prepared,
                        document_text_file_id=text_id,
                        source_sha256=source.file_sha256,
                        response=response,
                        provider=self.provider,
                        job_id=context.job_id,
                        job_source_sha256=source.fingerprint(max_tokens),
                        intent_id=intent_id,
                    )
                    uow.commit()
                return proposal
            except (
                AIAccessRefused,
                AISettingsRefused,
                PreparationRefused,
                ProposalEvidenceRefused,
                AIBudgetRefused,
                Problem,
            ):
                self._record_error(
                    context, retrieved, response=response, invalidated=True, intent_id=intent_id
                )
                raise

    def run_extraction(
        self,
        context: JobContext,
        source: ExtractionSource,
        *,
        max_tokens: int,
        wait: Callable[[timedelta], None],
    ) -> UUID:
        """At most three calls, with persisted 5/10-second backoff and no lease across waits."""
        for _ in range(4):  # three calls, then terminal persistence if all failed
            try:
                previous = self._recover_extraction(context, source, max_tokens)
            except AttemptEvidenceRefused:
                # Cancelling the job does not erase an uncertain call or release its budget hold.
                require_not_cancelled(context)
                raise
            if previous is not None and previous.proposal_id is not None:
                return previous.proposal_id
            if previous is not None and not self._terminal(previous):
                require_not_cancelled(context)
                due = previous.outcome_at + timedelta(seconds=5 * 2 ** (previous.attempt_no - 1))
                remaining = due - context.clock.now()
                if remaining > timedelta():
                    wait(remaining)
                require_not_cancelled(context)
            try:
                return self._extraction_attempt(context, source, max_tokens)
            except _RecordedFailure:
                continue
        raise AssertionError("bounded extraction retry loop exhausted without a result")
