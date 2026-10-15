"""AI explanation inputs read as the current human in a read-only transaction."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from uuid import UUID

from erev_engine.currencies import ISO_4217
from erev_engine.money import EXACT_PLACES

from erev_api.auth.principal import Principal
from erev_api.db.session import tenant_session
from erev_api.domain.ai.access import AIAccessRefused, authorize_job
from erev_api.domain.ai.narratives import PreparedNarrative, prepare_narrative
from erev_api.domain.contracts import obligations, queries, to_date
from erev_api.enums import PrincipalKind
from erev_api.explain import service
from erev_api.jobs.context import JobAttempt, JobContext
from erev_api.problems import Problem
from erev_api.schemas.explain import ExplainObjectType


@dataclass(frozen=True, slots=True)
class RetrievedNarrative:
    principal: Principal
    prepared: PreparedNarrative


def retrieve_narrative(
    context: JobContext,
    *,
    object_type: ExplainObjectType,
    object_id: UUID,
    measure: str,
    model: str,
    max_tokens: int,
    period: str | None = None,
    book_code: str | None = None,
    as_of: date | None = None,
    known_at: datetime | None = None,
    redact_contact_details: bool = True,
) -> RetrievedNarrative:
    """Reauthorize every attempt; intersect AI and contract-read entity grants.

    The gateway owns settings, budget admission and durable attempt evidence.
    No system-scoped session may read the trace. Returned data is detached before
    provider work; submission uses the same read path without invoking a provider.
    """
    with context.read_session() as session:
        principal = authorize_job(context, session)
    attempt = context.runtime.attempt
    if attempt is None:
        raise AIAccessRefused("AI_JOB_CONTEXT_REQUIRED")
    return retrieve_for_user(
        principal,
        now=context.clock.now(),
        object_type=object_type,
        object_id=object_id,
        measure=measure,
        model=model,
        max_tokens=max_tokens,
        period=period,
        book_code=book_code,
        as_of=as_of,
        known_at=known_at,
        redact_contact_details=redact_contact_details,
        attempt=attempt,
    )


def retrieve_for_user(
    principal: Principal,
    *,
    now: datetime,
    object_type: ExplainObjectType,
    object_id: UUID,
    measure: str,
    model: str,
    max_tokens: int,
    period: str | None = None,
    book_code: str | None = None,
    as_of: date | None = None,
    known_at: datetime | None = None,
    redact_contact_details: bool = True,
    attempt: JobAttempt | None = None,
) -> RetrievedNarrative:
    """Shared submission/worker read admission; never constructs or calls a provider."""
    if (
        principal.kind is not PrincipalKind.USER
        or principal.id is None
        or "ai.use" not in principal.permissions
    ):
        raise AIAccessRefused("AI_HUMAN_INITIATOR_REQUIRED")
    if known_at is not None and known_at.utcoffset() is None:
        raise AIAccessRefused("AI_INVALID_READ_CUTOFF")
    read_scope = principal.permission_scopes.get("contract.read", frozenset())
    ai_scope = principal.permission_scopes.get("ai.use", frozenset())
    if "contract.read" not in principal.permissions or not read_scope:
        raise AIAccessRefused("AI_READ_PERMISSION_DENIED")
    if ai_scope == "*":
        scope = read_scope
    elif read_scope == "*":
        scope = ai_scope
    else:
        scope = ai_scope & read_scope
    if not scope:
        raise AIAccessRefused("AI_READ_PERMISSION_DENIED")
    principal = replace(principal, entity_scope="*" if scope == "*" else tuple(sorted(scope)))
    with tenant_session(principal.db_context, read_only=True) as session:
        if attempt is not None:
            attempt.require(session)
        # Match the public Explain route's to-date period selection.
        name = service.MEASURE_ALIASES.get(measure, measure)
        if (
            object_type == "obligation"
            and period is None
            and name
            in {
                to_date.REVENUE,
                to_date.BILLED,
                to_date.PROGRESS,
            }
        ):
            measured = obligations.measured_period(
                session,
                object_id,
                name,
                params=queries.ReadParams(book=book_code, as_of=as_of, known_at=known_at),
                now=now,
            )
            if measured is None:
                raise Problem("not-found", service.NOT_TRACED)
            period = measured.period_key
        trace_id, explanation = service.explanation_snapshot(
            session,
            object_type=object_type,
            object_id=object_id,
            measure=measure,
            book_code=book_code,
            known_at=known_at,
            period_key=period,
        )
    minor_unit = (
        ISO_4217[explanation.currency].minor_unit
        if explanation.currency is not None
        else EXACT_PLACES
    )
    prepared = prepare_narrative(
        explanation=explanation,
        trace_id=trace_id,
        minor_unit=minor_unit,
        model=model,
        max_tokens=max_tokens,
        redact_contact_details=redact_contact_details,
    )
    return RetrievedNarrative(principal, prepared)
