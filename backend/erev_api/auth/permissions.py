"""Permission catalogue, default role grants and effective grants (dev-guide §5.4 KRN-PERM; 04
T-PLT-09 to T-PLT-12).

``CATALOGUE`` is exactly the seeded T-PLT-11 catalogue; the migration that creates ``permission``
inserts it (DG-KRN-PERM-01). ``DEFAULT_ROLES`` holds the grants of the ten T-PLT-09 role codes as
tabled in docs/02-PRD.md §5.6; tenant provisioning inserts them (04 §14.3). The drift tests compare
both with the documents. Descriptions and role names are copy; codes and flags are identifiers
(D-73). ``effective_grants`` unions the role assignments of a membership that are in force;
``api_client_grants`` gives an access token the client's scopes it carries, never an approval
permission (DG-KRN-PERM-04). ``standing_delegations`` reads the approval delegations that stand at
an instant — or, for a command, every one that has not ended (04 T-PLT-21): what a member holds
beside their own grants, for the rules that ask what a person can do — the second factor
(``auth.mfa``) and the separation of duties (``auth.sod``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Final, Literal
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import (
    api_client,
    approval_delegation,
    role,
    role_assignment,
    role_permission,
)
from erev_api.enums import ApiClientStatus


@dataclass(frozen=True, slots=True)
class PermissionSpec:
    code: str
    area: str
    description: str
    is_approval: bool
    is_access_admin: bool
    requires_mfa: bool


def _permission(
    code: str,
    area: str,
    description: str,
    *,
    approval: bool = False,
    access_admin: bool = False,
    mfa: bool = False,
) -> PermissionSpec:
    return PermissionSpec(
        code=code,
        area=area,
        description=description,
        is_approval=approval,
        is_access_admin=access_admin,
        requires_mfa=mfa,
    )


CATALOGUE: Final[tuple[PermissionSpec, ...]] = (
    _permission("contract.read", "CON", "View contracts, obligations and schedules"),
    _permission(
        "contract.create", "CON", "Create and edit draft contracts and submit them for activation"
    ),
    _permission("contract.approve", "CON", "Approve contract activation", approval=True, mfa=True),
    _permission("contract.void", "CON", "Request the void of a contract"),
    _permission("modification.create", "MOD", "Prepare contract modifications"),
    _permission(
        "modification.approve", "MOD", "Approve contract modifications", approval=True, mfa=True
    ),
    _permission(
        "event.record", "REC", "Record contract events such as deliveries, progress and billing"
    ),
    _permission(
        "event.approve", "REC", "Approve manually entered contract events", approval=True, mfa=True
    ),
    _permission("estimate.create", "TP", "Prepare estimate versions"),
    _permission("estimate.approve", "TP", "Approve estimate versions", approval=True, mfa=True),
    _permission("judgement.create", "POL", "Prepare judgement records"),
    _permission("judgement.review", "POL", "Review judgement records", approval=True, mfa=True),
    _permission("ssp.read", "SSP", "View SSP books and entries"),
    _permission("ssp.create", "SSP", "Prepare SSP book versions and calculator runs"),
    _permission(
        "ssp.approve", "SSP", "Approve SSP book versions and SSP overrides", approval=True, mfa=True
    ),
    _permission("adjustment.create", "JE", "Prepare manual adjustments"),
    _permission("adjustment.approve", "JE", "Approve manual adjustments", approval=True, mfa=True),
    _permission("config.read", "POL", "View revenue policies, rule sets and account mappings"),
    _permission("config.author", "POL", "Author configuration versions"),
    _permission("config.approve", "POL", "Approve configuration versions", approval=True, mfa=True),
    _permission(
        "masterdata.maintain",
        "REF",
        "Maintain master data such as entities, customers, products, accounts and FX rates",
    ),
    _permission("import.upload", "DAT", "Upload and validate import files"),
    _permission("import.approve", "DAT", "Approve import commits", approval=True, mfa=True),
    _permission("journal.run", "JE", "Calculate journal runs"),
    _permission("journal.approve", "JE", "Approve journal runs", approval=True, mfa=True),
    _permission("journal.export", "JE", "Export approved journals to the general ledger"),
    _permission("period.close", "CLS", "Run the close of a period"),
    _permission("period.lock", "CLS", "Lock periods", approval=True, mfa=True),
    _permission("period.reopen_request", "CLS", "Request the reopening of a closed period"),
    _permission(
        "period.reopen_approve",
        "CLS",
        "Approve the reopening of a closed period",
        approval=True,
        mfa=True,
    ),
    _permission("recon.prepare", "CLS", "Prepare reconciliations"),
    _permission("recon.signoff", "CLS", "Sign off reconciliations", approval=True, mfa=True),
    _permission("exception.resolve", "DAT", "Resolve exception queue items"),
    _permission(
        "exception.waive",
        "DAT",
        "Approve waivers of exception queue items",
        approval=True,
        mfa=True,
    ),
    _permission("report.run", "RPT", "Run reports"),
    _permission("report.export", "RPT", "Export report results"),
    _permission("evidence.export", "RPT", "Export audit evidence packs"),
    _permission("audit.read", "PLT", "View the audit log"),
    _permission(
        "user.manage", "PLT", "Invite, suspend and remove users", access_admin=True, mfa=True
    ),
    _permission(
        "role.manage", "PLT", "Maintain roles and role assignments", access_admin=True, mfa=True
    ),
    _permission(
        "access.approve",
        "PLT",
        "Approve role changes, role assignments and SoD exceptions",
        approval=True,
        access_admin=True,
        mfa=True,
    ),
    _permission(
        "support_grant.approve",
        "PLT",
        "Approve provider support access grants",
        approval=True,
        access_admin=True,
        mfa=True,
    ),
    _permission("settings.manage", "PLT", "Manage tenant settings", access_admin=True, mfa=True),
    _permission("integration.manage", "INT", "Manage integration connections", mfa=True),
    _permission(
        "api_client.manage",
        "PLT",
        "Manage API clients and their scopes",
        access_admin=True,
        mfa=True,
    ),
    _permission("webhook.manage", "PLT", "Manage webhook endpoints"),
    _permission("ai.use", "AI", "Use AI assistance"),
    _permission("scenario.use", "FC", "Run scenarios, forecasts and deal previews"),
    _permission(
        "tenant.snapshot",
        "PLT",
        "Create tenant snapshots and restore them into sandboxes",
        mfa=True,
    ),
    _permission("sandbox.reset", "PLT", "Reset sandbox tenants", mfa=True),
    _permission(
        "migration.run", "MIG", "Import legacy databases and run migration reconciliations"
    ),
    _permission(
        "migration.approve", "MIG", "Approve migration promotions", approval=True, mfa=True
    ),
)

_BY_CODE: Final[Mapping[str, PermissionSpec]] = MappingProxyType(
    {permission.code: permission for permission in CATALOGUE}
)

# docs/02-PRD.md §5.6: every default role except service_account holds the three reads.
_READS: Final = frozenset({"contract.read", "ssp.read", "config.read"})

DEFAULT_ROLES: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "revenue_accountant": _READS
        | {
            "contract.create",
            "contract.void",
            "modification.create",
            "event.record",
            "estimate.create",
            "judgement.create",
            "adjustment.create",
            "config.author",
            "masterdata.maintain",
            "import.upload",
            "journal.run",
            "recon.prepare",
            "migration.run",
            "journal.export",
            "period.close",
            "exception.resolve",
            "report.run",
            "report.export",
            "audit.read",
            "ai.use",
            "scenario.use",
        },
        "revenue_reviewer": _READS
        | {
            "contract.approve",
            "modification.approve",
            "event.approve",
            "estimate.approve",
            "judgement.review",
            "adjustment.approve",
            "import.approve",
            "journal.approve",
            "recon.signoff",
            "exception.waive",
            "period.reopen_request",
            "period.reopen_approve",
            "report.run",
            "report.export",
            "audit.read",
            "ai.use",
        },
        "controller": _READS
        | {
            "contract.approve",
            "modification.approve",
            "estimate.approve",
            "judgement.review",
            "adjustment.approve",
            "config.approve",
            "journal.approve",
            "recon.signoff",
            "exception.waive",
            "period.reopen_request",
            "period.reopen_approve",
            "journal.export",
            "period.close",
            "period.lock",
            "migration.approve",
            "tenant.snapshot",
            "sandbox.reset",
            "report.run",
            "report.export",
            "evidence.export",
            "audit.read",
            "ai.use",
            "scenario.use",
        },
        "ssp_analyst": _READS | {"ssp.create", "report.run"},
        "ssp_approver": _READS | {"ssp.approve", "report.run"},
        "integration_admin": _READS
        | {
            "config.author",
            "masterdata.maintain",
            "exception.resolve",
            "report.run",
            "audit.read",
            "integration.manage",
            "webhook.manage",
        },
        "tenant_admin": _READS
        | {
            "audit.read",
            "user.manage",
            "role.manage",
            "access.approve",
            "support_grant.approve",
            "settings.manage",
            "api_client.manage",
        },
        "auditor": _READS | {"report.run", "report.export", "evidence.export", "audit.read"},
        "viewer": _READS | {"report.run", "report.export", "ai.use"},
        "service_account": frozenset(
            {
                "contract.read",
                "contract.create",
                "event.record",
                "masterdata.maintain",
                "import.upload",
            }
        ),
    }
)

# docs/02-PRD.md §5.6 role names (copy), seeded as ``role.name``.
DEFAULT_ROLE_NAMES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "revenue_accountant": "Revenue Accountant",
        "revenue_reviewer": "Revenue Reviewer",
        "controller": "Controller",
        "ssp_analyst": "SSP Analyst",
        "ssp_approver": "SSP Approver",
        "integration_admin": "Integration Admin",
        "tenant_admin": "Tenant Admin",
        "auditor": "Auditor",
        "viewer": "Viewer",
        "service_account": "Service Account",
    }
)


def spec(code: str) -> PermissionSpec:
    """The catalogue entry for ``code``; ``KeyError`` for an unknown code."""
    return _BY_CODE[code]


def role_content_sha256(codes: Iterable[str]) -> str:
    """T-PLT-09 ``content_sha256``: the §5.17 ``sha256_hex`` of the sorted permission codes."""
    return sha256_hex(sorted(codes))


def _no_role_scopes() -> Mapping[str, Literal["*"] | frozenset[UUID]]:
    return MappingProxyType({})


@dataclass(frozen=True, slots=True)
class Grants:
    roles: tuple[str, ...]
    permissions: frozenset[str]
    permission_scopes: Mapping[str, Literal["*"] | frozenset[UUID]]
    entity_scope: Literal["*"] | tuple[UUID, ...]
    # role code → the entities its assignments in force cover (04 T-PLT-18 rev 1.104: a step's
    # role requirement is met only for the subject's entities); empty holds no role anywhere.
    role_scopes: Mapping[str, Literal["*"] | frozenset[UUID]] = field(
        default_factory=_no_role_scopes
    )


def effective_grants(session: Session, membership_id: UUID, *, at: datetime) -> Grants:
    """The union of the membership's role assignments in force at ``at`` (REQ-PLT-008, -012).

    An assignment is in force when it is not revoked, ``valid_from <= at``, ``valid_to`` is null or
    later than ``at``, and its role is active. A permission held through an all-entities assignment
    has scope ``"*"``; otherwise its scope is the union of the entity ids of the assignments that
    grant it. ``entity_scope`` is ``"*"`` when any assignment covers all entities, else the sorted
    union of the assignments' entity ids (empty without assignments). ``role_scopes`` scopes each
    role code the same way: ``"*"`` through an all-entities assignment of the role, else the union
    of the entity ids of its assignments.
    """
    statement = (
        select(
            role.c.code,
            role_assignment.c.is_all_entities,
            role_assignment.c.entity_ids,
            role_permission.c.permission_code,
        )
        .select_from(
            role_assignment.join(
                role,
                and_(
                    role.c.tenant_id == role_assignment.c.tenant_id,
                    role.c.id == role_assignment.c.role_id,
                ),
            ).outerjoin(
                role_permission,
                and_(
                    role_permission.c.tenant_id == role.c.tenant_id,
                    role_permission.c.role_id == role.c.id,
                ),
            )
        )
        .where(
            role_assignment.c.membership_id == membership_id,
            role_assignment.c.revoked_at.is_(None),
            role_assignment.c.valid_from <= at,
            or_(role_assignment.c.valid_to.is_(None), role_assignment.c.valid_to > at),
            role.c.is_active.is_(True),
        )
    )
    roles: set[str] = set()
    all_entities = False
    entities: set[UUID] = set()
    wide: set[str] = set()
    scoped: dict[str, set[UUID]] = {}
    wide_roles: set[str] = set()
    scoped_roles: dict[str, set[UUID]] = {}
    for code, is_all, entity_ids, permission_code in session.execute(statement):
        roles.add(str(code))
        ids = {UUID(str(value)) for value in entity_ids or ()}
        all_entities = all_entities or bool(is_all)
        entities |= ids
        if is_all:
            wide_roles.add(str(code))
        else:
            scoped_roles.setdefault(str(code), set()).update(ids)
        if permission_code is None:
            continue
        if is_all:
            wide.add(str(permission_code))
        else:
            scoped.setdefault(str(permission_code), set()).update(ids)
    scopes: dict[str, Literal["*"] | frozenset[UUID]] = {
        code: frozenset(ids) for code, ids in scoped.items() if code not in wide
    }
    for code in wide:
        scopes[code] = "*"
    role_scopes: dict[str, Literal["*"] | frozenset[UUID]] = {
        code: frozenset(ids) for code, ids in scoped_roles.items() if code not in wide_roles
    }
    for code in wide_roles:
        role_scopes[code] = "*"
    return Grants(
        roles=tuple(sorted(roles)),
        permissions=frozenset(scopes),
        permission_scopes=MappingProxyType(dict(sorted(scopes.items()))),
        entity_scope="*" if all_entities else tuple(sorted(entities)),
        role_scopes=MappingProxyType(dict(sorted(role_scopes.items()))),
    )


@dataclass(frozen=True, slots=True)
class StandingDelegation:
    """An approval delegation that stands at an instant, or that was given and has not ended
    (04 T-PLT-21)."""

    id: UUID
    delegator_membership_id: UUID
    delegate_membership_id: UUID
    permissions: frozenset[str]
    valid_from: datetime
    valid_to: datetime
    created_at: datetime


def standing_delegations(
    session: Session,
    *,
    at: datetime,
    delegate_membership_id: UUID | None = None,
    scheduled: bool = False,
) -> list[StandingDelegation]:
    """The delegations that stand at ``at`` — every one the session sees, or those given to
    ``delegate_membership_id`` — oldest first (04 T-PLT-21; supervisor ruling R-111 (2), (4)).

    A delegation stands when ``valid_from <= at < valid_to`` and it was not revoked by ``at``
    (D-80 rule 2, as for a role assignment: one revoked afterwards still counts at ``at``). That
    is wider than what the approval engine honours at a decision — it also asks that the
    delegator be an ACTIVE member who still holds the permission for the entity
    (``approvals.engine.find_authority``) — and deliberately so: the second factor and the
    separation of duties count what stands, so that neither can fall behind what the engine
    will honour once a delegator's access returns.

    With ``scheduled`` the delegations that have not started count too — every row that has
    not ended at ``at``, whatever its ``valid_from`` and ``created_at``. That is the reading of a
    command: a delegation given for a later start comes into force without a further command,
    and a row committed by a command that ran beside this one is there to be counted, whichever
    of the two clocks read first.
    """
    statement = (
        select(
            approval_delegation.c.id,
            approval_delegation.c.delegator_membership_id,
            approval_delegation.c.delegate_membership_id,
            approval_delegation.c.permissions,
            approval_delegation.c.valid_from,
            approval_delegation.c.valid_to,
            approval_delegation.c.created_at,
        )
        .where(
            approval_delegation.c.valid_to > at,
            or_(approval_delegation.c.revoked_at.is_(None), approval_delegation.c.revoked_at > at),
        )
        .order_by(approval_delegation.c.valid_from, approval_delegation.c.id)
    )
    if not scheduled:
        statement = statement.where(approval_delegation.c.valid_from <= at)
    if delegate_membership_id is not None:
        statement = statement.where(
            approval_delegation.c.delegate_membership_id == delegate_membership_id
        )
    return [
        StandingDelegation(
            id=UUID(str(row.id)),
            delegator_membership_id=UUID(str(row.delegator_membership_id)),
            delegate_membership_id=UUID(str(row.delegate_membership_id)),
            permissions=frozenset(str(code) for code in row.permissions),
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            created_at=row.created_at,
        )
        for row in session.execute(statement)
    ]


def api_client_grants(
    session: Session, api_client_id: UUID, *, token_scopes: Sequence[str], at: datetime
) -> Grants:
    """The grants of an access token: its scopes that the client holds (REQ-PLT-033).

    Approval permissions and codes outside the catalogue are dropped (DG-KRN-PERM-04; DB-12). A
    client that is not ``ACTIVE``, or whose ``expires_at`` is not later than ``at``, holds nothing.
    Every permission has the client's entity scope: ``"*"`` for an all-entities client, else its
    ``entity_ids``.
    """
    client = session.execute(
        select(api_client.c.scopes, api_client.c.is_all_entities, api_client.c.entity_ids).where(
            api_client.c.id == api_client_id,
            api_client.c.status == ApiClientStatus.ACTIVE.value,
            api_client.c.expires_at > at,
        )
    ).one_or_none()
    if client is None:
        return Grants(
            roles=(),
            permissions=frozenset(),
            permission_scopes=MappingProxyType({}),
            entity_scope=(),
        )
    held = {str(code) for code in client.scopes}
    codes = sorted(
        code
        for code in set(token_scopes)
        if code in held and code in _BY_CODE and not _BY_CODE[code].is_approval
    )
    entity_scope: Literal["*"] | tuple[UUID, ...] = (
        "*"
        if client.is_all_entities
        else tuple(sorted(UUID(str(value)) for value in client.entity_ids or ()))
    )
    scope: Literal["*"] | frozenset[UUID] = "*" if entity_scope == "*" else frozenset(entity_scope)
    return Grants(
        roles=(),
        permissions=frozenset(codes),
        permission_scopes=MappingProxyType(dict.fromkeys(codes, scope)),
        entity_scope=entity_scope,
    )
