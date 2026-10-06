"""The stand-in personas of the lane's DB-bound adapter tests (record §31, slice PLAT-ACT-1; rule
ACT-1).

The DB-bound tests do not run the PROVISION and PERSONAS plan steps: ``support.principals`` members
stand in for ``ak-preparer`` (maya) and ``ak-approver`` (marcus), with roles assigned through
``support.reference.assign``. ACT-1 needs a proven principal for every actor a plan step names, so
the map handed to ``WorkspaceAdapter.for_database`` is built here from those members and the roles
they actually hold in the database — never defaulted to the workspace's own principal. Role codes
are the T-PLT-09 system roles a provisioned tenant has (``DEFAULT_ROLES``, 04 §14.3); any other
code cannot be assigned (``insert_role_assignment`` selects the tenant's ``role`` row) and is
refused here by name rather than claimed on the principal.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Final, Literal, Protocol
from uuid import UUID

from erev_api.auth.permissions import DEFAULT_ROLES
from erev_api.auth.principal import Principal
from erev_api.enums import PrincipalKind
from support.answer_keys.platform_plan import (
    APPROVER,
    INTEGRATION,
    INTEGRATION_SCOPES,
    OPERATOR,
    PREPARER,
    SSP_ANALYST,
    SSP_APPROVER,
    H,
    Step,
)

# The role codes the stand-ins hold in the database (T-PLT-09 codes only; DG-AK-41 rev 1.38, D-98
# candidate 107): maya is the revenue accountant; marcus holds the controller role (the approver —
# no ``approver`` platform role exists) and the ``tenant_admin`` grant, so he also stands in for the
# provisioning operator, who applies tenant settings (``settings.manage``).
PERSONA_ROLES: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        PREPARER: ("revenue_accountant",),
        APPROVER: ("controller", "tenant_admin"),
        OPERATOR: ("tenant_admin",),
        SSP_ANALYST: ("ssp_analyst",),  # D-98 candidate 107a
        SSP_APPROVER: ("ssp_approver",),
    }
)

# The plan steps ``test_ledger_resolver_ids_equal_rows`` runs: world configuration only.
LEDGER_RESOLVER_HANDLERS: Final[frozenset[str]] = frozenset(
    {H["currencies"], H["calendar"], H["fiscal_year"], H["entity"], H["customer"]}
)


class MemberLike(Protocol):
    """What a stand-in contributes to its principal: ``support.principals.Member`` or a fake."""

    @property
    def user_id(self) -> UUID: ...

    @property
    def tenant_id(self) -> UUID: ...

    @property
    def membership_id(self) -> UUID: ...


def persona_principal(persona: str, someone: MemberLike, *, verified_at: datetime) -> Principal:
    """The ACT-1 principal of the stand-in ``someone`` acting as ``persona``: the member's ids, the
    roles of ``PERSONA_ROLES`` and their ``DEFAULT_ROLES`` permissions over every entity."""
    if persona not in PERSONA_ROLES:
        raise ValueError(
            f"no stand-in persona {persona!r}; known: {', '.join(sorted(PERSONA_ROLES))}"
        )
    roles = PERSONA_ROLES[persona]
    unknown = [code for code in roles if code not in DEFAULT_ROLES]
    if unknown:
        raise ValueError(
            f"persona {persona!r}: role codes {unknown} are not T-PLT-09 system roles; "
            "a provisioned tenant cannot assign them"
        )
    permissions = frozenset[str]().union(*(DEFAULT_ROLES[code] for code in roles))
    scopes: dict[str, Literal["*"] | frozenset[UUID]] = {code: "*" for code in permissions}
    return Principal(
        kind=PrincipalKind.USER,
        id=someone.user_id,
        tenant_id=someone.tenant_id,
        membership_id=someone.membership_id,
        display_name=persona,
        roles=tuple(sorted(roles)),
        permissions=permissions,
        permission_scopes=MappingProxyType(scopes),
        entity_scope="*",
        auth_method="password",
        # The verified session the API presents after `POST /me/mfa/confirm` (`support.principals.
        # enrolled`): approvals refuse an unverified principal (approvals/engine.py `mfa-required`),
        # a control the witnesses keep — batch #6 returned POS-117 on exactly this stamp.
        mfa_verified_at=verified_at,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


def integration_principal(tenant_id: UUID, client_id: UUID) -> Principal:
    """The ACT-1 principal of the world's API client ``ak-integration`` (BUILD_SPEC CTR-6; PRD
    ACT-10): the stand-in for the client the plan's PERSONAS step creates — a test inserts the
    ``api_client`` row (``support.rows.api_client_values``, as the imports tests build theirs)
    and hands in its id. Its permissions are its scopes, ``INTEGRATION_SCOPES``, over every
    entity; it has no role and no verified session."""
    permissions = frozenset(INTEGRATION_SCOPES)
    scopes: dict[str, Literal["*"] | frozenset[UUID]] = {code: "*" for code in permissions}
    return Principal(
        kind=PrincipalKind.API_CLIENT,
        id=client_id,
        tenant_id=tenant_id,
        membership_id=None,
        display_name=INTEGRATION,
        roles=(),
        permissions=permissions,
        permission_scopes=MappingProxyType(scopes),
        entity_scope="*",
        auth_method="client_credentials",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


def principal_map(
    preparer: MemberLike,
    approver: MemberLike,
    operator: MemberLike | None = None,
    *,
    ssp_analyst: MemberLike | None = None,
    ssp_approver: MemberLike | None = None,
    integration: UUID | None = None,
    verified_at: datetime,
) -> dict[str, Principal]:
    """The map for ``WorkspaceAdapter.for_database`` (ACT-1): the personas and the operator, proven
    by name; the operator stand-in defaults to the approver's member (marcus holds the
    ``tenant_admin`` grant the operator is checked for); the SSP personas are mapped only when a
    test hands in members holding their roles (a step by an unmapped persona is refused), and
    the world's API client only when a test hands in the id of its ``api_client`` row
    (``integration``; CTR-6)."""
    principals = {
        PREPARER: persona_principal(PREPARER, preparer, verified_at=verified_at),
        APPROVER: persona_principal(APPROVER, approver, verified_at=verified_at),
        OPERATOR: persona_principal(
            OPERATOR, approver if operator is None else operator, verified_at=verified_at
        ),
    }
    if ssp_analyst is not None:
        principals[SSP_ANALYST] = persona_principal(
            SSP_ANALYST, ssp_analyst, verified_at=verified_at
        )
    if ssp_approver is not None:
        principals[SSP_APPROVER] = persona_principal(
            SSP_APPROVER, ssp_approver, verified_at=verified_at
        )
    if integration is not None:
        principals[INTEGRATION] = integration_principal(preparer.tenant_id, integration)
    return principals


def actors_of(steps: Iterable[Step]) -> frozenset[str]:
    """The actors the given plan steps name — what the principal map must cover."""
    return frozenset(step.actor for step in steps)
