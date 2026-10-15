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
from erev_api.explain import service
from erev_api.jobs.context import JobContext
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

    This does not enable AI or invoke a provider. The gateway still owes settings,
    budget admission, per-attempt logging and durable proposals. No system-scoped
    session may read the trace. Returned data is detached before provider work.
    """
    if known_at is not None and known_at.utcoffset() is None:
        raise AIAccessRefused("AI_INVALID_READ_CUTOFF")
    with context.read_session() as session:
        principal = authorize_job(context, session)
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
        attempt = context.runtime.attempt
        if attempt is None:
            raise AIAccessRefused("AI_JOB_CONTEXT_REQUIRED")
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
                now=context.clock.now(),
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
