"""Principals and request context KRN-AUTH (docs/dev-guide.md §5.3; 05 TXN-01).

A ``Principal`` is who acts: a user, an API client, an operator or the system. Its ``db_context``
feeds the transaction-local settings that row-level security keys on (DG-KRN-DB-01). A
``RequestContext`` is the principal plus the request facts a command handler needs, with ``now``
captured once at request start.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Final, Literal
from uuid import UUID

from erev_api.db.session import DbContext
from erev_api.enums import PrincipalKind, TenantKind, TenantStatus

SYSTEM_DISPLAY_NAME: Final = "System"


def _no_role_scopes() -> Mapping[str, Literal["*"] | frozenset[UUID]]:
    return MappingProxyType({})


@dataclass(frozen=True, slots=True)
class Principal:
    kind: PrincipalKind  # E-15
    id: UUID | None  # app_user.id or api_client.id; None for SYSTEM
    tenant_id: UUID
    membership_id: UUID | None
    display_name: str
    roles: tuple[str, ...]  # role codes, sorted
    permissions: frozenset[str]
    permission_scopes: Mapping[str, Literal["*"] | frozenset[UUID]]  # permission → entities
    entity_scope: Literal["*"] | tuple[UUID, ...]  # union; feeds app.entity_scope
    auth_method: Literal["password", "oidc", "client_credentials", "system"]
    mfa_verified_at: datetime | None
    session_id: UUID | None
    support_grant_id: UUID | None
    on_behalf_of_id: UUID | None
    # role code → entities (``Grants.role_scopes``): a step's role requirement is met only by an
    # assignment that covers the subject's entities (04 T-PLT-18 rev 1.104; REQ-CLS-011). A
    # principal built without it holds no role for any entity (fail closed).
    role_scopes: Mapping[str, Literal["*"] | frozenset[UUID]] = field(
        default_factory=_no_role_scopes
    )

    @property
    def db_context(self) -> DbContext:
        """Tenant, principal id and the entity scope sorted ascending (DG-KRN-DB-01)."""
        scope: Literal["*"] | tuple[UUID, ...] = (
            "*" if self.entity_scope == "*" else tuple(sorted(self.entity_scope))
        )
        return DbContext(tenant_id=self.tenant_id, user_id=self.id, entity_scope=scope)


def system_principal(tenant_id: UUID, *, on_behalf_of_id: UUID | None = None) -> Principal:
    """The SYSTEM principal of a tenant: no permissions, every entity (jobs, DG-KRN-UOW-04)."""
    return Principal(
        kind=PrincipalKind.SYSTEM,
        id=None,
        tenant_id=tenant_id,
        membership_id=None,
        display_name=SYSTEM_DISPLAY_NAME,
        roles=(),
        permissions=frozenset(),
        permission_scopes=MappingProxyType({}),
        entity_scope="*",
        auth_method="system",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=on_behalf_of_id,
    )


@dataclass(frozen=True, slots=True)
class OperatorContext:
    """An MFA-verified platform operator session outside any tenant (DG-KRN-TEN-05)."""

    operator_user_id: UUID
    session_id: UUID
    request_id: str
    now: datetime


@dataclass(frozen=True, slots=True)
class RequestContext:
    principal: Principal
    tenant_kind: TenantKind  # E-16
    request_id: str
    source_ip: str | None
    user_agent: str | None
    idempotency_key: str | None
    if_match: str | None
    now: datetime  # Clock.now() captured once at request start
    format_locale: str
    # E-101 of the tenant the request runs in (05 SBX-07): only an ACTIVE tenant takes commands.
    # A worker principal's context keeps the default — no job is gated by it.
    tenant_status: TenantStatus = TenantStatus.ACTIVE
