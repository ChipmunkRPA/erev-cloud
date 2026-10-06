"""API-R-10 Audit: the audit log, chain verifications and on-demand verification.

04 §15.3 API-R-10, §16.14 "Audit events" (rev 1.154), API-C-12, T-PLT-19, T-PLT-23; SCREENS_B
§6.3, §6.4; BUILD_SPEC PLF-23. Every route requires ``audit.read``. The audit events, the actors
of a range and the command that starts a verification ask it for all entities: an audit event
carries no entity, so a holder of named entities is refused, never shown a list that looks
filtered, and a verification of the chain is a tenant-wide act (supervisor rulings R-28 and
R-115 (c); item SCOPE-WORKSPACE-LISTS-1). The verifications are read at any scope: they state
counts and chain values, no entity's data.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Final, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import ColumnElement, Select
from sqlalchemy.orm import Session

from erev_api.api.deps import (
    API_PREFIX,
    CommandContext,
    GuardedRoute,
    KernelDeps,
    command,
    kernel_deps,
    problem_responses,
    run_command,
)
from erev_api.api.lists import (
    TOTAL_COUNT_HEADER,
    FilterSpec,
    ListParams,
    ListResult,
    ListSpec,
    list_params,
    paginate,
)
from erev_api.auth.dependencies import require, require_all_entities
from erev_api.auth.principal import RequestContext
from erev_api.db.tables import audit_chain_verification, audit_event
from erev_api.domain.platform import audit_log
from erev_api.enums import AuditOutcome, ControlResult
from erev_api.schemas.audit import AuditActorsOut, AuditChainVerificationOut, AuditEventOut
from erev_api.schemas.common import JobOut, ListOut

TAG: Final = "API-R-10 Audit"
AUDIT_READ: Final = "audit.read"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden")
_COMMAND_PROBLEMS: Final = (
    *_READ_PROBLEMS,
    "validation-failed",
    "idempotency-key-reused",
    "idempotency-in-progress",
)
EVENT_LIST: Final = ListSpec(
    resource="audit-events",
    sort_keys={
        "id": audit_event.c.id,
        "chain_seq": audit_event.c.chain_seq,
        "occurred_at": audit_event.c.occurred_at,
    },
    default_sort="-chain_seq",
    filters={
        "object_type": FilterSpec(
            name="object_type", column=audit_event.c.object_type, kind="exact"
        ),
        "object_id": FilterSpec(name="object_id", column=audit_event.c.object_id, kind="exact"),
        "actor_id": FilterSpec(name="actor_id", column=audit_event.c.actor_id, kind="exact"),
        "action": FilterSpec(name="action", column=audit_event.c.action, kind="exact"),
        "outcome": FilterSpec(
            name="outcome",
            column=audit_event.c.outcome,
            kind="exact",
            choices=frozenset(outcome.value for outcome in AuditOutcome),
        ),
        "chain_seq": FilterSpec(name="chain_seq", column=audit_event.c.chain_seq, kind="exact"),
        "from": FilterSpec(name="from", column=audit_event.c.occurred_at, kind="from"),
        "to": FilterSpec(name="to", column=audit_event.c.occurred_at, kind="to"),
    },
    # Applied by ``audit_log.event_source``: the contract key of T-PLT-19 is no column.
    custom_filters=frozenset({"contract_id"}),
)


def _event_list(columns: Mapping[str, ColumnElement[Any]]) -> ListSpec:
    """``EVENT_LIST`` bound to the columns a read takes its keys from: the table's for the log as
    a whole (the specification as it stands), the link's and the looked-up event's for the trail
    of a contract (``audit_log.EventSource``)."""
    return dataclasses.replace(
        EVENT_LIST,
        sort_keys={key: columns[column.name] for key, column in EVENT_LIST.sort_keys.items()},
        filters={
            name: dataclasses.replace(spec, column=columns[spec.column.name])
            for name, spec in EVENT_LIST.filters.items()
        },
    )


VERIFICATION_LIST: Final = ListSpec(
    resource="audit-events/verifications",
    sort_keys={
        "id": audit_chain_verification.c.id,
        "finished_at": audit_chain_verification.c.finished_at,
    },
    default_sort="-finished_at",
    filters={
        "trigger": FilterSpec(
            name="trigger",
            column=audit_chain_verification.c.trigger,
            kind="exact",
            choices=frozenset({"SCHEDULED", "ON_DEMAND"}),
        ),
        "result": FilterSpec(
            name="result",
            column=audit_chain_verification.c.result,
            kind="exact",
            choices=frozenset(result.value for result in ControlResult),
        ),
        "from": FilterSpec(name="from", column=audit_chain_verification.c.finished_at, kind="from"),
        "to": FilterSpec(name="to", column=audit_chain_verification.c.finished_at, kind="to"),
    },
)

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


@router.get(
    "/audit-events",
    operation_id="audit_events_list",
    response_model=ListOut[AuditEventOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def audit_events_list(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require_all_entities(AUDIT_READ))],
    params: Annotated[ListParams, Depends(list_params)],
    object_type: Annotated[str | None, Query()] = None,
    object_id: Annotated[uuid.UUID | None, Query()] = None,
    actor_id: Annotated[uuid.UUID | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    outcome: Annotated[
        list[AuditOutcome] | None, Query(description="Repeatable: any of the outcomes sent")
    ] = None,
    contract_id: Annotated[
        uuid.UUID | None,
        Query(
            description=(
                "Every event that names the contract, whatever its object type "
                "(detail.contract_id or a member of detail.contract_ids); read without a default "
                "range"
            )
        ),
    ] = None,
    chain_seq: Annotated[
        int | None,
        Query(ge=1, description="The event of this chain sequence; read without a default range"),
    ] = None,
    from_: Annotated[
        datetime | None,
        Query(
            alias="from",
            description=(
                "Inclusive. Without it a read starts 30 days before `to`, or before the request "
                "when `to` is not sent either — except a read by `contract_id` or `chain_seq`"
            ),
        ),
    ] = None,
    to: Annotated[
        datetime | None,
        Query(
            description=(
                "Exclusive. Without it a read ends one day after the request — except a read by "
                "`contract_id` or `chain_seq`"
            )
        ),
    ] = None,
) -> ListOut[AuditEventOut]:
    """The workspace's audit events; sort ``chain_seq`` (default ``-chain_seq``, newest first),
    ``occurred_at`` or ``id``. An event is addressed by its chain sequence: ``id`` is no filter."""

    source = audit_log.event_source(
        ctx.now, contract_id=contract_id, since=from_, until=to, by_sequence=chain_seq is not None
    )
    spec = _event_list(source.columns)

    def page(session: Session, statement: Select[Any]) -> tuple[ListResult, list[AuditEventOut]]:
        result = paginate(session, statement, spec, params)
        return result, audit_log.event_outs(result.items)

    result, items = audit_log.list_events(ctx, source, page=page)
    if result.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = result.total_count
    return ListOut[AuditEventOut](items=items, next_cursor=result.next_cursor)


@router.get(
    "/audit-events/actors",
    operation_id="audit_events_actors",
    response_model=AuditActorsOut,
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def audit_events_actors(
    ctx: Annotated[RequestContext, Depends(require_all_entities(AUDIT_READ))],
    from_: Annotated[
        datetime | None,
        Query(
            alias="from",
            description=(
                "Inclusive. Without it the range starts 30 days before `to`, or before the "
                "request when `to` is not sent either"
            ),
        ),
    ] = None,
    to: Annotated[
        datetime | None,
        Query(description="Exclusive. Without it the range ends one day after the request"),
    ] = None,
    q: Annotated[
        str | None, Query(max_length=200, description="Part of the name, any case")
    ] = None,
) -> AuditActorsOut:
    """Who acted in a range of the log — the users, operators and API clients its events name — by
    name, at most 100 (``is_truncated`` says the range holds more): the options of the log's actor
    filter. Never the workspace's user list: a person who did nothing in the range is not
    answered."""
    return audit_log.actors_in_range(ctx, since=from_, until=to, q=q)


@router.get(
    "/audit-events/verifications",
    operation_id="audit_events_verifications",
    response_model=ListOut[AuditChainVerificationOut],
    responses=problem_responses(*_READ_PROBLEMS, "validation-failed"),
)
def audit_events_verifications(
    response: Response,
    ctx: Annotated[RequestContext, Depends(require(AUDIT_READ))],
    params: Annotated[ListParams, Depends(list_params)],
    trigger: Annotated[Literal["SCHEDULED", "ON_DEMAND"] | None, Query()] = None,
    result: Annotated[ControlResult | None, Query()] = None,
    from_: Annotated[datetime | None, Query(alias="from", description="Inclusive")] = None,
    to: Annotated[datetime | None, Query(description="Exclusive")] = None,
) -> ListOut[AuditChainVerificationOut]:
    """The workspace's chain verifications; sort ``finished_at`` (default ``-finished_at``) or
    ``id``."""

    def page(
        session: Session, statement: Select[Any]
    ) -> tuple[ListResult, list[AuditChainVerificationOut]]:
        listed = paginate(session, statement, VERIFICATION_LIST, params)
        return listed, audit_log.verification_outs(listed.items)

    listed, items = audit_log.list_verifications(ctx, page=page)
    if listed.total_count is not None:
        response.headers[TOTAL_COUNT_HEADER] = listed.total_count
    return ListOut[AuditChainVerificationOut](items=items, next_cursor=listed.next_cursor)


@router.get(
    "/audit-events/verifications/{verification_id}",
    operation_id="audit_events_verification",
    response_model=AuditChainVerificationOut,
    responses=problem_responses(*_READ_PROBLEMS, "not-found", "validation-failed"),
)
def audit_events_verification(
    verification_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(require(AUDIT_READ))],
) -> AuditChainVerificationOut:
    """One chain verification of the workspace."""
    return audit_log.get_verification(ctx, verification_id)


@router.post(
    "/audit-events/verify",
    status_code=202,
    operation_id="audit_events_verify",
    response_model=JobOut,
    responses=problem_responses(*_COMMAND_PROBLEMS),
)
def audit_events_verify(
    cmd: Annotated[CommandContext, Depends(command(AUDIT_READ, all_entities=True))],
    deps: Annotated[KernelDeps, Depends(kernel_deps)],
) -> Response:
    """Verify the audit chain now: 202 with the job and ``Location: /api/v1/jobs/{id}``."""
    return run_command(
        cmd,
        deps,
        audit_log.request_verification,
        status_code=202,
        location=lambda job: f"{API_PREFIX}/jobs/{job.id}",
    )
