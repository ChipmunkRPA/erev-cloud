"""Audit writer KRN-AUD (dev-guide §5.5 DG-KRN-AUD-01, DG-KRN-AUD-04, DG-KRN-AUD-05,
DG-KRN-AUD-09; DG-KRN-AUTH-05; 04 §1.7 AUD-CMD, AUD-FACT; REQ-PLT-018, REQ-PLT-019).

``record`` and ``record_facts`` buffer one event on the unit of work; ``UnitOfWork.commit()``
appends the buffer to the tenant chain as its last database work. ``record_denied`` appends in its
own transaction, so the evidence of a refused command survives the command's rollback.

An event of an object that belongs to a contract names the contract: every function here takes
``contract_id=`` (one contract) or ``contract_ids=`` (several) and states it in ``detail`` as
``audit.contract_key`` says (04 T-PLT-19, rev 1.154).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.canonical import sha256_hex

from erev_api.audit import contract_key
from erev_api.audit.chain import append_events
from erev_api.audit.redact import REDACT, json_value, redact
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, RequestContext
from erev_api.db import new_id
from erev_api.db.session import process_keyring, tenant_session
from erev_api.enums import AuditOutcome, PrincipalKind

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = [
    "REDACT",
    "AuditActor",
    "actor_of",
    "build_event",
    "principal_actor",
    "record",
    "record_denied",
    "record_facts",
    "record_now",
]

ACTION: Final = re.compile(r"^[a-z_]+\.[a-z_]+$")
# 04 §1.7 AUD-FACT: above this many ids the event keeps a digest instead of the list.
FACT_ID_LIMIT: Final = 100
_MISSING: Final = object()


@dataclass(frozen=True, slots=True)
class AuditActor:
    kind: PrincipalKind
    id: UUID | None
    roles: tuple[str, ...]
    auth_method: str | None
    mfa_verified: bool | None
    on_behalf_of_id: UUID | None
    api_client_id: UUID | None
    support_grant_id: UUID | None
    source_ip: str | None
    request_id: str


def actor_of(ctx: RequestContext) -> AuditActor:
    """The actor fields of T-PLT-19 from the request's principal (DG-KRN-AUD-01)."""
    return principal_actor(ctx.principal, request_id=ctx.request_id, source_ip=ctx.source_ip)


def principal_actor(
    principal: Principal, *, request_id: str, source_ip: str | None = None
) -> AuditActor:
    """The actor fields of T-PLT-19 for ``principal`` under ``request_id``: what ``actor_of`` reads
    from a request, for an event appended outside a unit of work (the jobs registry's ``job.start``
    of a scheduler deferral and its ``job.finish``; 04 T-PLT-27)."""
    return AuditActor(
        kind=principal.kind,
        id=principal.id,
        roles=principal.roles,
        auth_method=principal.auth_method,
        mfa_verified=principal.mfa_verified_at is not None,
        on_behalf_of_id=principal.on_behalf_of_id,
        api_client_id=principal.id if principal.kind is PrincipalKind.API_CLIENT else None,
        support_grant_id=principal.support_grant_id,
        source_ip=source_ip,
        request_id=request_id,
    )


def _diff(before: Any, after: Any, path: str) -> list[dict[str, Any]]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        entries: list[dict[str, Any]] = []
        for key in sorted(set(before) | set(after)):
            child = f"{path}.{key}" if path else key
            entries += _diff(before.get(key, _MISSING), after.get(key, _MISSING), child)
        return entries
    if before == after:
        return []
    return [
        {
            "path": path,
            "before": None if before is _MISSING else before,
            "after": None if after is _MISSING else after,
        }
    ]


def build_event(
    *,
    tenant_id: UUID,
    actor: AuditActor,
    occurred_at: datetime,
    action: str,
    object_type: str,
    object_id: UUID | None,
    object_version: str | None = None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    reason_code: str | None = None,
    comment: str | None = None,
    approval_request_id: UUID | None = None,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    detail: Mapping[str, Any] | None = None,
    contract_id: UUID | None = None,
    contract_ids: Sequence[UUID] | None = None,
) -> dict[str, Any]:
    """One T-PLT-19 row without its chain columns; payloads JSON-native and redacted. The
    contract the event concerns is stated in ``detail`` (``contract_key.keyed``)."""
    if not ACTION.fullmatch(action):
        raise ValueError(f"audit action {action!r} must match ^[a-z_]+\\.[a-z_]+$")
    detail = contract_key.keyed(
        object_type,
        detail,
        contract_id=contract_id,
        contract_ids=contract_ids,
        # A refusal is recorded whatever its writer holds of the object (DG-KRN-AUTH-05).
        required=outcome is not AuditOutcome.DENIED,
    )
    before_value = None if before is None else redact(json_value(before))
    after_value = None if after is None else redact(json_value(after))
    diff = (
        None
        if before_value is None or after_value is None
        else _diff(before_value, after_value, "")
    )
    return {
        "tenant_id": tenant_id,
        "occurred_at": occurred_at,
        "id": new_id(),
        "actor_id": actor.id,
        "actor_kind": actor.kind.value,
        "actor_roles": list(actor.roles),
        "auth_method": actor.auth_method,
        "mfa_verified": actor.mfa_verified,
        "on_behalf_of_id": actor.on_behalf_of_id,
        "api_client_id": actor.api_client_id,
        "support_grant_id": actor.support_grant_id,
        "source_ip": actor.source_ip,
        "request_id": actor.request_id,
        "action": action,
        "object_type": object_type,
        "object_id": object_id,
        "object_version": object_version,
        "before": before_value,
        "after": after_value,
        "diff": diff,
        "reason_code": reason_code,
        "comment": comment,
        "approval_request_id": approval_request_id,
        "outcome": outcome.value,
        "detail": redact(json_value(detail)),
    }


def record(
    uow: UnitOfWork,
    *,
    action: str,
    object_type: str,
    object_id: UUID | None,
    object_version: str | None = None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    reason_code: str | None = None,
    comment: str | None = None,
    approval_request_id: UUID | None = None,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    detail: Mapping[str, Any] | None = None,
    contract_id: UUID | None = None,
    contract_ids: Sequence[UUID] | None = None,
) -> None:
    """Buffer one AUD-CMD event with ``occurred_at = uow.now`` (DG-KRN-AUD-01)."""
    uow.buffer_audit_event(
        build_event(
            tenant_id=uow.principal.tenant_id,
            actor=actor_of(uow.ctx),
            occurred_at=uow.now,
            action=action,
            object_type=object_type,
            object_id=object_id,
            object_version=object_version,
            before=before,
            after=after,
            reason_code=reason_code,
            comment=comment,
            approval_request_id=approval_request_id,
            outcome=outcome,
            detail=detail,
            contract_id=contract_id,
            contract_ids=contract_ids,
        )
    )


def record_facts(
    uow: UnitOfWork,
    *,
    action: str,
    object_type: str,
    ids: Sequence[UUID],
    detail: Mapping[str, Any] | None = None,
    contract_id: UUID | None = None,
    contract_ids: Sequence[UUID] | None = None,
) -> None:
    """Buffer one AUD-FACT summary: the ids, or above 100 the count, first and last id of the
    sorted list and its SHA-256 (04 §1.7; SPEC-Q-132)."""
    ordered = sorted(str(value) for value in ids)
    if len(ordered) > FACT_ID_LIMIT:
        facts: dict[str, Any] = {
            "count": len(ordered),
            "first_id": ordered[0],
            "last_id": ordered[-1],
            "ids_sha256": sha256_hex(ordered),
        }
    else:
        facts = {"ids": ordered}
    record(
        uow,
        action=action,
        object_type=object_type,
        object_id=None,
        detail={**(detail or {}), **facts},
        contract_id=contract_id,
        contract_ids=contract_ids,
    )


def record_now(
    ctx: RequestContext,
    *,
    action: str,
    object_type: str,
    object_id: UUID | None,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    detail: Mapping[str, Any] | None = None,
    keyring: KeyRing | None = None,
    contract_id: UUID | None = None,
    contract_ids: Sequence[UUID] | None = None,
) -> None:
    """Append one event in a transaction of its own: denials (DG-KRN-AUTH-05) and the requests of
    an operator under a support grant (05 SAR-29)."""
    event = build_event(
        tenant_id=ctx.principal.tenant_id,
        actor=actor_of(ctx),
        occurred_at=ctx.now,
        action=action,
        object_type=object_type,
        object_id=object_id,
        outcome=outcome,
        detail=detail,
        contract_id=contract_id,
        contract_ids=contract_ids,
    )
    with tenant_session(ctx.principal.db_context) as session:
        append_events(
            session,
            tenant_id=ctx.principal.tenant_id,
            keyring=process_keyring() if keyring is None else keyring,
            events=[event],
        )


def record_denied(
    ctx: RequestContext,
    *,
    action: str,
    object_type: str,
    object_id: UUID | None,
    permission: str,
    detail: Mapping[str, Any] | None = None,
    keyring: KeyRing | None = None,
    contract_id: UUID | None = None,
    contract_ids: Sequence[UUID] | None = None,
) -> None:
    """Append one ``DENIED`` event in a transaction of its own (DG-KRN-AUTH-05)."""
    record_now(
        ctx,
        action=action,
        object_type=object_type,
        object_id=object_id,
        outcome=AuditOutcome.DENIED,
        detail={**(detail or {}), "permission": permission},
        keyring=keyring,
        contract_id=contract_id,
        contract_ids=contract_ids,
    )
