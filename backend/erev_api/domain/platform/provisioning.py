"""Tenant provisioning KRN-TEN (dev-guide §5.20; 04 §14.3; REQ-PLT-038).

``provision_tenant`` runs ``tenant.provision`` in one ``platform_session("provisioning")``: the
tenant row with its audit key id (DG-KRN-KEY-06), then, under the new tenant context, the admin
``app_user``, the ``INVITED`` membership, the ten system roles with their permissions
(DG-KRN-PERM-01), the SoD rules SoD-1 to SoD-7 as PUBLISHED version 1 (BS1-D-26), the
``numbering_series`` rows of every T-PLT-26 code except ``JE`` (PLF-9), rule set
``AUTO-BOOTSTRAP`` with its PUBLISHED version 1 and rule, and the admin's ``tenant_admin``
assignment for all entities, whose ``ROLE_ASSIGNMENT`` request that rule approves at submission
(PLF-12), one DEFAULT ``registry_version`` per E-53 category, approved by SYSTEM (PLF-13), the
built-in ``dimension_definition`` rows (RFD-6), the three ``book`` rows (RFD-2), the fourteen system
``close_checklist_template`` gates (CLO-2; CLO-GATE-RUN-1), and the invitation
``outbox_message`` carrying the
acceptance link (PLF-14). The session records
``PLATFORM_SCOPE_USED`` naming the tenant (DG-KRN-DB-03).
Later items extend the same transaction with the rest of the 04 §14.3 seed (BUILD_SPEC BS-D-12).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final, Literal
from uuid import UUID

from erev_engine.canonical import sha256_hex
from erev_engine.currencies import ISO_4217
from erev_engine.rules import validate_conditions
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from erev_api.approvals import engine as approvals
from erev_api.approvals import routing
from erev_api.approvals.subjects import ALL_ENTITIES
from erev_api.audit.chain import append_events
from erev_api.audit.writer import AuditActor, build_event
from erev_api.auth.keyring import (
    DerivedTenantKeyProvisioner,
    KeyRing,
    ProvisioningReadbackError,
    TenantKeyProvisioner,
)
from erev_api.auth.permissions import DEFAULT_ROLE_NAMES, DEFAULT_ROLES, role_content_sha256
from erev_api.clock import Clock
from erev_api.db import new_id
from erev_api.db.session import (
    DbContext,
    name_platform_tenant,
    of_session_tenant,
    platform_session,
    set_tenant_context,
)
from erev_api.db.tables.close import close_checklist_template
from erev_api.db.tables.platform import (
    app_user,
    audit_chain_head,
    numbering_series,
    registry_version,
    role,
    role_assignment,
    role_permission,
    sod_rule,
    tenant,
    tenant_membership,
)
from erev_api.db.tables.reference import (
    book,
    dimension_definition,
    rule,
    rule_set,
    rule_set_version,
    tenant_currency,
)
from erev_api.db.tables.subledger import ledger_chain_head
from erev_api.domain.close import monitor_rules
from erev_api.domain.journals.subledger import ledger_chain_head_rows
from erev_api.domain.platform.sod_seed import sod_rule_rows
from erev_api.domain.reference.books import book_rows
from erev_api.domain.reference.dimensions import builtin_dimension_rows
from erev_api.enums import (
    ApprovalSubjectType,
    ChecklistGateKind,
    ConfigStatus,
    MembershipStatus,
    OutboxTopic,
    PrincipalKind,
    RegistryCategory,
    RegistryScope,
    RuleSetKind,
    TenantKind,
    TenantStatus,
)
from erev_api.events import outbox
from erev_api.files.store import FileStore
from erev_api.numbering import allocate, tenant_series_rows
from erev_api.problems import Problem, ProblemError
from erev_api.registry import versions as registry_versions

# [J] DG-KRN-TEN-03: a URL-safe subset of erev.code (TY-06), 3 to 40 characters.
TENANT_CODE: Final = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# T-PLT-01 industry_cluster: free text within TY-07 (D-98 148 A5 Q7); 05 PERF-11: a perf: value
# names the generator manifest the volume tenant was built from.
PERF_CLUSTER_PREFIX: Final = "perf:"
PERF_CLUSTER: Final = re.compile(r"^perf:[0-9a-f]{16}$")
TENANT_CODE_LENGTH: Final = range(3, 41)
EMAIL: Final = re.compile(r"^[^@\s]+@[^@\s]+$")  # TY-09 after lower-casing
LABEL_LENGTH: Final = range(1, 401)  # TY-07
INVITATION_LIFETIME: Final = timedelta(days=7)  # T-PLT-07
TENANT_CODE_INDEX: Final = "ux_tenant__code"
# 04 §14.3 item 2: the bootstrap auto-approval rule set and the role it grants.
# The engine admits the bootstrap grants only through this rule set and this role (R-26 (b)), so
# the two literals live with the rule that enforces them.
AUTO_BOOTSTRAP: Final = routing.AUTO_BOOTSTRAP
DQ_SYSTEM: Final = "DQ-SYSTEM"  # 04 §14.3 rev 1.21; BUILD_SPEC CLO-5; supervisor ruling Q-4
BOOTSTRAP_ROLE: Final = routing.BOOTSTRAP_ROLE
# PRD §2.5 routing row ROLE_ASSIGNMENT: one access.approve step.
BOOTSTRAP_STEP: Final = routing.StepPlan(
    name=routing.FALLBACK_STEP_NAME, permission="access.approve", min_approvers=1
)
ROLE_ASSIGNMENT_CREATE: Final = "role_assignment.create"
REGISTRY_SEED_ACTION: Final = "registry_version.seed"  # 04 §14.3
# SCREENS_B §12.3 RT-05: the token travels in the fragment, never in a query parameter. The
# place is filled when the email is sent (05 NTR-04).
INVITATION_LINK: Final = "/accept-invitation#token={token}"
# ``KeyRing.link_token`` purpose of an invitation link; each invitation email has a reference of
# its own, so that a re-sent invitation has another token.
INVITATION_PURPOSE: Final = "invitation"
# 04 T-CLS-02: the gate check codes in their order, with the SCREENS_B §1.1 gate labels (CLO-2).
# ``CLOSE_RUN_COMPLETED`` is the thirteenth and the certification stays the last line of every
# checklist (item CLO-GATE-RUN-1; supervisor rulings R-114 (b) and R-116 (e)).
SYSTEM_CLOSE_GATES: Final = (
    ("INTERFACES_COMPLETE", "Interface batches complete"),
    ("JE_BALANCED", "Journals balance per currency"),
    ("JE_COMPLETE", "Journals complete"),
    ("APPROVALS_CLEARED", "No pending approvals"),
    ("EXCEPTIONS_CLEARED", "Exceptions resolved, waived or dismissed"),
    ("HOLDS_REVIEWED", "Holds released or waived"),
    ("BATCHES_ACKNOWLEDGED", "Batches acknowledged by the GL"),
    ("RECONCILIATIONS_GENERATED", "Reconciliations generated and reviewed"),
    ("JUDGEMENTS_REVIEWED", "Judgements reviewed"),
    ("DATA_QUALITY_CLEAR", "Data-quality errors cleared"),
    ("NO_DIRTY_GROUPS", "All contracts computed"),
    ("MANUAL_ADJUSTMENTS_CLEARED", "Manual adjustments cleared"),
    ("CLOSE_RUN_COMPLETED", "Close run completed"),
    ("CONTROLLER_CERTIFIED", "Controller certification"),
)


@dataclass(frozen=True, slots=True)
class TenantProvisionRequest:
    code: str
    display_name: str
    reporting_currency: str
    is_demo: bool
    admin_email: str
    # T-PLT-01 ``industry_cluster``: free text, or ``perf:<first 16 hex of the manifest SHA-256>``
    # for the PRF-2 volume tenant (05 PERF-11); set only here, never by ``TenantUpdateIn``.
    industry_cluster: str | None = None


@dataclass(frozen=True, slots=True)
class OperatorActor:
    channel: Literal["CLI", "API"]
    operator_user_id: UUID | None  # app_user.id with is_operator = true; None for the CLI
    os_user: str | None  # getpass.getuser() for the CLI; None for the API
    request_id: str


@dataclass(frozen=True, slots=True)
class TenantProvisionResult:
    tenant: Mapping[str, Any]  # {id, code, kind, display_name, reporting_currency, is_demo}
    admin_membership_id: UUID
    invitation_expires_at: datetime


@dataclass(frozen=True, slots=True)
class InvitationReissue:
    """What ``reissue_admin_invitation`` did: the tenant, the membership and the new expiry."""

    tenant_id: UUID
    tenant_code: str
    admin_membership_id: UUID
    invitation_expires_at: datetime


# 04 §14.3 step 5 (rev 1.114; ruling R-37 (d)): the refusals of ``reissue_admin_invitation``. The
# slugs and rule ids are existing ones; the messages name what the operator enters.
RULE_PROVISIONING: Final = "BR-PLT-01"
RULE_MEMBERSHIP: Final = "T-PLT-07"
REISSUE_TENANT_UNKNOWN: Final = "Choose an existing production workspace."
REISSUE_NO_MEMBERSHIP: Final = "Enter the email address the invitation was sent to."
REISSUE_WORKSPACE_INVITATION: Final = (
    "This invitation was sent from the workspace. A Tenant Admin sends it again."
)
OPERATOR_DISPLAY_NAME: Final = "Platform operator"
OPERATOR_LOCALE: Final = "en-US"


def validation_errors(request: TenantProvisionRequest) -> list[ProblemError]:
    """One error per failing field, in request field order (DG-KRN-TEN-03; SPEC-Q-117)."""
    errors: list[ProblemError] = []
    if not (TENANT_CODE.fullmatch(request.code) and len(request.code) in TENANT_CODE_LENGTH):
        errors.append(
            ProblemError(
                field="code",
                rule_id="TENANT_CODE_FORMAT",
                message="Use 3 to 40 lowercase letters, digits and single hyphens.",
            )
        )
    if len(request.display_name) not in LABEL_LENGTH:
        errors.append(
            ProblemError(
                field="display_name",
                rule_id="LABEL_LENGTH",
                message="Use 1 to 400 characters.",
            )
        )
    if request.reporting_currency not in ISO_4217:
        errors.append(
            ProblemError(
                field="reporting_currency",
                rule_id="CURRENCY_UNKNOWN",
                message="Use an ISO 4217 currency code.",
            )
        )
    if not EMAIL.fullmatch(request.admin_email.lower()):
        errors.append(
            ProblemError(
                field="admin_email", rule_id="EMAIL_FORMAT", message="Enter an email address."
            )
        )
    cluster = request.industry_cluster
    if cluster is not None and (
        len(cluster) not in LABEL_LENGTH
        or (cluster.startswith(PERF_CLUSTER_PREFIX) and not PERF_CLUSTER.fullmatch(cluster))
    ):
        errors.append(
            ProblemError(
                field="industry_cluster",
                rule_id="INDUSTRY_CLUSTER_FORMAT",
                message="Use 1 to 400 characters; a perf: cluster is perf: and 16 hex digits.",
            )
        )
    return errors


def _code_exists() -> Problem:
    """DG-KRN-TEN-02: an existing code refuses the whole command and creates nothing."""
    return Problem(
        "validation-failed",
        errors=[
            ProblemError(
                field="code",
                rule_id="TENANT_CODE_EXISTS",
                message="A workspace with this code already exists.",
            )
        ],
    )


def _constraint_name(error: IntegrityError) -> str | None:
    name = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    return name if isinstance(name, str) else None


def _admin_user_id(session: Session, *, email: str, stamp: Mapping[str, Any]) -> UUID:
    """The user of ``email``, or a new one with ``password_hash`` NULL (04 §14.3 item 2)."""
    existing = session.execute(
        select(app_user.c.id).where(app_user.c.email == email)
    ).scalar_one_or_none()
    if existing is not None:
        return UUID(str(existing))
    user_id = new_id()
    # [J] display_name is NOT NULL and the request has no admin name: the email until the user
    # sets one (SPEC-Q-118).
    session.execute(
        insert(app_user).values(
            id=user_id, email=email, display_name=email, password_hash=None, **stamp
        )
    )
    return user_id


def default_role_rows(
    tenant_id: UUID, *, stamp: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The ten T-PLT-09 system roles and their T-PLT-12 rows, from ``DEFAULT_ROLES`` (04 §14.3)."""
    created = {key: stamp[key] for key in ("created_at", "created_by", "created_by_kind")}
    roles: list[dict[str, Any]] = []
    grants: list[dict[str, Any]] = []
    for code, permissions in DEFAULT_ROLES.items():
        role_id = new_id()
        roles.append(
            {
                "tenant_id": tenant_id,
                "id": role_id,
                "code": code,
                "name": DEFAULT_ROLE_NAMES[code],
                "description": None,
                "is_system": True,
                "is_active": True,
                "content_sha256": role_content_sha256(permissions),
                **stamp,
            }
        )
        grants += [
            {"tenant_id": tenant_id, "role_id": role_id, "permission_code": permission, **created}
            for permission in sorted(permissions)
        ]
    return roles, grants


def auto_bootstrap_rows(
    tenant_id: UUID, *, stamp: Mapping[str, Any], published_at: datetime
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Rule set ``AUTO-BOOTSTRAP``, its PUBLISHED version 1 and its one rule (04 §14.3 item 2).

    The rule approves role assignments prepared by a Tenant Admin while setup is incomplete. The
    version has no effective dates, so it is in force from provisioning on; its content hash covers
    the kind and the rule (DB-04).
    """
    kind = RuleSetKind.AUTO_APPROVAL.value
    conditions: list[Mapping[str, object]] = [
        {"field": "subject.type", "op": "eq", "value": ApprovalSubjectType.ROLE_ASSIGNMENT.value},
        {"field": "preparer.role_codes", "op": "in", "value": [BOOTSTRAP_ROLE]},
        {"field": "tenant.setup_completed", "op": "eq", "value": False},
    ]
    set_id, version_id = new_id(), new_id()
    rule_row = {
        "tenant_id": tenant_id,
        "id": new_id(),
        "rule_set_version_id": version_id,
        "rule_key": AUTO_BOOTSTRAP,
        "priority": 0,
        "conditions": conditions,
        "outputs": {"auto_approve": True},
        "specificity": validate_conditions(kind, conditions),
        "description": "Role assignments by the bootstrap Tenant Admin until setup completes.",
    }
    content = {
        "kind": kind,
        "rules": [
            {key: rule_row[key] for key in ("rule_key", "priority", "specificity", "conditions")}
            | {"outputs": rule_row["outputs"]}
        ],
    }
    set_row = {
        "tenant_id": tenant_id,
        "id": set_id,
        "code": AUTO_BOOTSTRAP,
        "name": "Setup grants",
        "kind": kind,
        "description": "Approves the bootstrap Tenant Admin's role assignments during setup.",
        **stamp,
    }
    version_row = {
        "tenant_id": tenant_id,
        "id": version_id,
        "rule_set_id": set_id,
        "kind": kind,
        "lint_result": None,
        "impact_simulation_file_id": None,
        **stamp,
        "version_no": 1,
        "status": ConfigStatus.PUBLISHED.value,
        "effective_from": None,
        "effective_to": None,
        "content_sha256": sha256_hex(content),
        "approval_request_id": None,
        "published_at": published_at,
        "published_by": stamp["created_by"],
        "supersedes_version_id": None,
    }
    return set_row, version_row, rule_row


# 04 §14.3 rev 1.72; 02-PRD §2.5 rev 1.15 (D-98 133 AMENDMENT 4). The engine reads this rule set
# alone for a MIGRATION_SSP_REPLAY (R-41 (7)), so the literal lives with the rule that enforces it.
AUTO_MIGRATION: Final = routing.AUTO_MIGRATION


def auto_migration_rows(
    tenant_id: UUID, *, stamp: Mapping[str, Any], published_at: datetime
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Rule set ``AUTO-MIG-01``, its PUBLISHED version 1 and its one rule (04 §14.3 item 2 rev
    1.72):
    the mode-(a) legacy SSP replay request (``MIGRATION_SSP_REPLAY``) submitted by a user at
    ``POST /migrations/{id}/import`` is approved at submission — the ``AUTO-IMP-01`` precedent. The
    two
    ruling conditions that are not rule facts (zero LM-SSP-01..09 ERROR findings; the content bound
    to
    the source digest) are enforced by ``/import`` before submission. Removed if the CONTROL FLAG is
    decided as a human approval before the job (A1)."""
    kind = RuleSetKind.AUTO_APPROVAL.value
    conditions: list[Mapping[str, object]] = [
        {
            "field": "subject.type",
            "op": "eq",
            "value": ApprovalSubjectType.MIGRATION_SSP_REPLAY.value,
        },
        {"field": "source.channel", "op": "eq", "value": "USER"},
    ]
    set_id, version_id = new_id(), new_id()
    rule_row = {
        "tenant_id": tenant_id,
        "id": new_id(),
        "rule_set_version_id": version_id,
        "rule_key": AUTO_MIGRATION,
        "priority": 0,
        "conditions": conditions,
        "outputs": {"auto_approve": True},
        "specificity": validate_conditions(kind, conditions),
        "description": (
            "Legacy SSP replay requests of a mode-(a) migration, submitted by a user at import."
        ),
    }
    content = {
        "kind": kind,
        "rules": [
            {key: rule_row[key] for key in ("rule_key", "priority", "specificity", "conditions")}
            | {"outputs": rule_row["outputs"]}
        ],
    }
    set_row = {
        "tenant_id": tenant_id,
        "id": set_id,
        "code": AUTO_MIGRATION,
        "name": "Legacy SSP replay",
        "kind": kind,
        "description": (
            "Approves the legacy SSP replay request of a mode-(a) migration at submission."
        ),
        **stamp,
    }
    version_row = {
        "tenant_id": tenant_id,
        "id": version_id,
        "rule_set_id": set_id,
        "kind": kind,
        "lint_result": None,
        "impact_simulation_file_id": None,
        **stamp,
        "version_no": 1,
        "status": ConfigStatus.PUBLISHED.value,
        "effective_from": None,
        "effective_to": None,
        "content_sha256": sha256_hex(content),
        "approval_request_id": None,
        "published_at": published_at,
        "published_by": stamp["created_by"],
        "supersedes_version_id": None,
    }
    return set_row, version_row, rule_row


def data_quality_rows(
    tenant_id: UUID, *, stamp: Mapping[str, Any], published_at: datetime
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Rule set ``DQ-SYSTEM``, its PUBLISHED version 1 and one rule per 04 table 15.4-E monitor
    (04 §14.3 rev 1.21; BUILD_SPEC CLO-5; supervisor ruling Q-4).

    Each rule is keyed by the monitor code (``FIELDS[DATA_QUALITY]`` is empty, so it has no
    conditions) and carries the table's default severity and description as its outputs; the CLO-5
    monitors bind severity by ``rule_key``, and a tenant's own published set overrides this seed.
    The version has no effective dates; its content hash covers the kind and the rules (DB-04).
    """
    kind = RuleSetKind.DATA_QUALITY.value
    set_id, version_id = new_id(), new_id()
    rule_rows = [
        {
            "tenant_id": tenant_id,
            "id": new_id(),
            "rule_set_version_id": version_id,
            "rule_key": spec.code,
            "priority": 0,
            "conditions": [],
            "outputs": {"severity": spec.default_severity, "message": spec.description},
            "specificity": validate_conditions(kind, []),
            "description": spec.description,
        }
        for spec in monitor_rules.MONITORS
    ]
    content = {
        "kind": kind,
        "rules": [
            {key: row[key] for key in ("rule_key", "priority", "specificity", "conditions")}
            | {"outputs": row["outputs"]}
            for row in rule_rows
        ],
    }
    set_row = {
        "tenant_id": tenant_id,
        "id": set_id,
        "code": DQ_SYSTEM,
        "name": "Data-quality monitors",
        "kind": kind,
        "description": "Severity of each 04 table 15.4-E data-quality monitor (REQ-CLS-019).",
        **stamp,
    }
    version_row = {
        "tenant_id": tenant_id,
        "id": version_id,
        "rule_set_id": set_id,
        "kind": kind,
        "lint_result": None,
        "impact_simulation_file_id": None,
        **stamp,
        "version_no": 1,
        "status": ConfigStatus.PUBLISHED.value,
        "effective_from": None,
        "effective_to": None,
        "content_sha256": sha256_hex(content),
        "approval_request_id": None,
        "published_at": published_at,
        "published_by": stamp["created_by"],
        "supersedes_version_id": None,
    }
    return set_row, version_row, rule_rows


def system_checklist_template_rows(
    tenant_id: UUID, *, stamp: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """One system ``close_checklist_template`` per gate check code (04 §14.3; T-CLS-02; BS-D-12).

    Each gate is automatic, blocking and active, takes its gate check code as its code and its
    position in the gate list as its sequence, and has no owner role or due offset until a tenant
    sets them (the two columns a system row may change).
    """
    return [
        {
            "tenant_id": tenant_id,
            "id": new_id(),
            "code": code,
            "name": label,
            "description": None,
            "gate_kind": ChecklistGateKind.AUTOMATIC.value,
            "gate_check_code": code,
            "is_blocking": True,
            "is_system": True,
            "owner_role_id": None,
            "due_offset_days": None,
            "sequence": sequence,
            "is_active": True,
            **stamp,
        }
        for sequence, (code, label) in enumerate(SYSTEM_CLOSE_GATES, start=1)
    ]


def registry_default_rows(tenant_id: UUID, *, published_at: datetime) -> list[dict[str, Any]]:
    """One PUBLISHED TENANT ``registry_version`` per E-53 category, with ``preset_code`` DEFAULT
    and no values, approved by the SYSTEM principal (04 §14.3).

    Without effective dates each version is in force from provisioning until a later version
    supersedes it; while it holds no values, resolution falls through to the framework defaults
    (DG-KRN-REG-01).
    """
    system = {
        "created_at": published_at,
        "created_by": None,
        "created_by_kind": PrincipalKind.SYSTEM.value,
        "updated_at": published_at,
        "updated_by": None,
        "updated_by_kind": PrincipalKind.SYSTEM.value,
    }
    scope = RegistryScope.TENANT
    return [
        {
            "tenant_id": tenant_id,
            "id": new_id(),
            "category": category.value,
            "scope": scope.value,
            "book_code": None,
            "entity_id": None,
            "values": {},
            "preset_code": registry_versions.DEFAULT_PRESET,
            "test_evidence": None,
            "impact_simulation_file_id": None,
            **system,
            "version_no": 1,
            "status": ConfigStatus.PUBLISHED.value,
            "effective_from": None,
            "effective_to": None,
            "content_sha256": registry_versions.content_sha256(
                category=category, scope=scope, book_code=None, entity_id=None, values={}
            ),
            "approval_request_id": None,
            "published_at": published_at,
            "published_by": None,
            "supersedes_version_id": None,
        }
        for category in RegistryCategory
    ]


def _registry_seed_events(
    rows: list[dict[str, Any]], *, actor: OperatorActor, now: datetime
) -> list[dict[str, Any]]:
    """``registry_version.seed`` per DEFAULT version, by the SYSTEM principal in the operator's
    request (04 §14.3)."""
    return registry_seed_events(rows, request_id=actor.request_id, now=now)


def registry_seed_events(
    rows: list[dict[str, Any]], *, request_id: str, now: datetime
) -> list[dict[str, Any]]:
    """``registry_version.seed`` per DEFAULT version, by the SYSTEM principal under
    ``request_id`` (04 §14.3)."""
    system = AuditActor(
        kind=PrincipalKind.SYSTEM,
        id=None,
        roles=(),
        auth_method=None,
        mfa_verified=None,
        on_behalf_of_id=None,
        api_client_id=None,
        support_grant_id=None,
        source_ip=None,
        request_id=request_id,
    )
    seeded = (
        "category",
        "scope",
        "preset_code",
        "version_no",
        "status",
        "values",
        "content_sha256",
    )
    return [
        build_event(
            tenant_id=row["tenant_id"],
            actor=system,
            occurred_at=now,
            action=REGISTRY_SEED_ACTION,
            object_type=registry_versions.OBJECT_TYPE,
            object_id=row["id"],
            after={key: row[key] for key in seeded},
        )
        for row in rows
    ]


def reissue_admin_invitation(
    *,
    code: str,
    admin_email: str,
    actor: OperatorActor,
    clock: Clock,
    keyring: KeyRing,
    files: FileStore,
) -> InvitationReissue:
    """Issue the first Tenant Admin's invitation again while it is open (04 §14.3 step 5, rev
    1.114; PRD BR-PLT-01; ruling R-37 (d)).

    Until that invitation is accepted nobody in the tenant can send it again (API-R-05 needs a
    Tenant Admin) and an operator has no session there, so a lost or expired link left a workspace
    nobody could enter. The tenant is read through the ``tenant_directory`` scope (a
    ``PLATFORM_SCOPE_USED`` security event); the membership command then runs in the tenant under
    principal kind ``OPERATOR`` and its audit event names the channel and the OS user.

    422 ``validation-failed`` on ``code`` unless it names a production tenant, and on ``admin``
    when the email has no membership there; 409 ``invalid-transition`` unless that membership is
    ``INVITED`` and an operator created it. Nothing is written on a refusal.
    """
    # Imported here: users imports this module for the invitation message, and the unit of work
    # and the principal belong to the command's composition, not to provisioning's own rows.
    from erev_api.auth.principal import Principal, RequestContext
    from erev_api.domain.platform import users
    from erev_api.uow import unit_of_work

    with platform_session(
        "tenant_directory",
        actor_user_id=actor.operator_user_id,
        request_id=actor.request_id,
        keyring=keyring,
    ) as directory:
        found = directory.execute(
            select(tenant.c.id, tenant.c.kind).where(tenant.c.code == code)
        ).one_or_none()
    if found is None or found.kind != TenantKind.PRODUCTION.value:
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(
                    field="code", rule_id=RULE_PROVISIONING, message=REISSUE_TENANT_UNKNOWN
                )
            ],
        )
    tenant_id = UUID(str(found.id))
    principal = Principal(
        kind=PrincipalKind.OPERATOR,
        id=actor.operator_user_id,
        tenant_id=tenant_id,
        membership_id=None,
        display_name=OPERATOR_DISPLAY_NAME,
        roles=(),
        permissions=frozenset(),
        permission_scopes=MappingProxyType({}),
        entity_scope="*",
        auth_method="system",
        mfa_verified_at=None,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )
    ctx = RequestContext(
        principal=principal,
        tenant_kind=TenantKind(found.kind),
        request_id=actor.request_id,
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale=OPERATOR_LOCALE,
    )
    detail: dict[str, Any] = {"channel": actor.channel}
    if actor.channel == "CLI":
        detail["os_user"] = actor.os_user
    else:
        detail["operator_user_id"] = str(actor.operator_user_id)
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        membership = uow.session.execute(
            select(
                tenant_membership.c.id,
                tenant_membership.c.status,
                tenant_membership.c.created_by_kind,
            )
            .join(app_user, app_user.c.id == tenant_membership.c.user_id)
            .where(
                of_session_tenant(tenant_membership),
                app_user.c.email == admin_email.strip().lower(),
            )
        ).one_or_none()
        if membership is None:
            raise Problem(
                "validation-failed",
                errors=[
                    ProblemError(
                        field="admin", rule_id=RULE_MEMBERSHIP, message=REISSUE_NO_MEMBERSHIP
                    )
                ],
            )
        if (
            membership.status == MembershipStatus.INVITED.value
            and membership.created_by_kind != PrincipalKind.OPERATOR.value
        ):
            # The workspace's own invitations are its Tenant Admin's to send again (API-R-05).
            raise Problem(
                "invalid-transition",
                errors=[
                    ProblemError(
                        field="status",
                        rule_id=users.RULE_LIFECYCLE,
                        message=REISSUE_WORKSPACE_INVITATION,
                    )
                ],
            )
        membership_id = UUID(str(membership.id))
        # 409 invalid-transition unless the membership is INVITED (accepted, suspended, removed).
        users.issue_invitation_again(uow, membership_id, detail=detail)
        expires_at = uow.session.execute(
            select(tenant_membership.c.invitation_expires_at).where(
                of_session_tenant(tenant_membership), tenant_membership.c.id == membership_id
            )
        ).scalar_one()
        uow.commit()
    return InvitationReissue(
        tenant_id=tenant_id,
        tenant_code=code,
        admin_membership_id=membership_id,
        invitation_expires_at=expires_at,
    )


@dataclass(frozen=True, slots=True)
class InvitationToken:
    """The token of one invitation email: ``token`` goes into ``tenant_membership`` as its
    SHA-256 only; the email names it by ``reference`` and ``key_id``."""

    token: str
    reference: UUID
    key_id: str

    def __repr__(self) -> str:
        return f"InvitationToken(reference={self.reference!r}, key_id={self.key_id!r})"


def invitation_token(keyring: KeyRing) -> InvitationToken:
    """A new invitation token (T-PLT-07): derived from the platform security key and a fresh
    reference, so that the token is stored nowhere and every invitation email has its own."""
    reference = new_id()
    issued = keyring.link_token(INVITATION_PURPOSE, reference)
    return InvitationToken(issued.token, reference, issued.key_id)


def invitation_message(
    *,
    tenant_id: UUID,
    membership_id: UUID,
    email: str,
    workspace_name: str,
    link_reference: UUID,
    key_id: str,
    expires_at: datetime,
    created_by: UUID | None,
    created_by_kind: PrincipalKind,
    now: datetime,
    dedupe_key: str | None = None,
) -> dict[str, Any]:
    """The invitation ``outbox_message`` of topic ``EMAIL``. The row holds neither the token nor
    its hash: it names the token by the reference and the key ``invitation_token`` derived it
    with, and the link is composed when the email is sent (04 T-INT-03 ``payload`` rev 1.151;
    §14.3 item 2). The text holds no amounts (PRD NTF-R3). A re-sent invitation names its own
    ``dedupe_key``."""
    text = (
        f"Hello,\n\nYou are invited to join the workspace {workspace_name} in eRev. "
        f"The invitation expires on {expires_at:%d %b %Y at %H:%M} UTC.\n\nAccept the invitation:"
    )
    return outbox.message_values(
        tenant_id=tenant_id,
        topic=OutboxTopic.EMAIL,
        aggregate_type="tenant_membership",
        aggregate_id=membership_id,
        dedupe_key=dedupe_key or f"invitation:{membership_id}",
        payload={
            "to": email,
            "subject": f"You are invited to {workspace_name} on eRev",
            "text": text,
            "link_path": INVITATION_LINK,
            outbox.LINK_TOKEN: outbox.link_token_reference(
                INVITATION_PURPOSE, link_reference, key_id
            ),
            "reference": str(membership_id),
            "notification_id": None,
        },
        now=now,
        created_by=created_by,
        created_by_kind=created_by_kind,
    )


def _operator(actor: OperatorActor) -> AuditActor:
    return AuditActor(
        kind=PrincipalKind.OPERATOR,
        id=actor.operator_user_id,
        roles=(),
        auth_method=None,
        mfa_verified=None,
        on_behalf_of_id=None,
        api_client_id=None,
        support_grant_id=None,
        source_ip=None,
        request_id=actor.request_id,
    )


def _provision_event(
    request: TenantProvisionRequest, *, actor: OperatorActor, tenant_id: UUID, now: datetime
) -> dict[str, Any]:
    """Event 1 of the tenant chain: ``tenant.provision`` by the operator (PLF-3; SPEC-Q-135).

    ``detail`` names the channel and the OS user of the CLI or the operator of the API
    (DG-KRN-TEN-01).
    """
    detail: dict[str, Any] = {"channel": actor.channel}
    if actor.channel == "CLI":
        detail["os_user"] = actor.os_user
    else:
        detail["operator_user_id"] = str(actor.operator_user_id)
    return build_event(
        tenant_id=tenant_id,
        actor=_operator(actor),
        occurred_at=now,
        action="tenant.provision",
        object_type="tenant",
        object_id=tenant_id,
        after={
            "code": request.code,
            "display_name": request.display_name,
            "is_demo": request.is_demo,
            "kind": TenantKind.PRODUCTION.value,
            "reporting_currency": request.reporting_currency,
        },
        detail=detail,
    )


@dataclass(frozen=True, slots=True)
class SeedActor:
    """Who the seed grant is stamped, audited and channelled by: the operator of
    ``tenant.provision``, or the SYSTEM principal of the job that creates an empty sandbox on
    behalf of its requester (05 SBX-07 rev 1.64)."""

    created_by: UUID | None
    created_by_kind: PrincipalKind
    audit: AuditActor
    source_channel: str


def _grant_bootstrap_admin(
    session: Session,
    *,
    tenant_id: UUID,
    membership_id: UUID,
    role_id: UUID,
    actor: OperatorActor,
    now: datetime,
) -> list[dict[str, Any]]:
    """``grant_bootstrap_admin`` by the operator of ``tenant.provision``."""
    return grant_bootstrap_admin(
        session,
        tenant_id=tenant_id,
        membership_id=membership_id,
        role_id=role_id,
        grantor=SeedActor(
            created_by=actor.operator_user_id,
            created_by_kind=PrincipalKind.OPERATOR,
            audit=_operator(actor),
            source_channel=PrincipalKind.OPERATOR.value,
        ),
        now=now,
    )


def grant_bootstrap_admin(
    session: Session,
    *,
    tenant_id: UUID,
    membership_id: UUID,
    role_id: UUID,
    grantor: SeedActor,
    now: datetime,
) -> list[dict[str, Any]]:
    """The admin's ``tenant_admin`` assignment for all entities, approved at submission by rule
    ``AUTO-BOOTSTRAP``; returns the audit events of the request and the assignment.

    [J] SPEC-Q-174: provisioning prepares the grant as SYSTEM on behalf of the bootstrap admin, so
    the preparer role codes are the role it confers and the channel is the grantor's
    (``OPERATOR`` for ``tenant.provision``). A missing match fails closed and rolls the
    transaction back (XR-12).

    The pair written here — a request prepared by SYSTEM with no preparer that the rule
    approved, and the assignment that is its subject and names it — is how the approvals engine
    knows THE bootstrap Tenant Admin, whoever the grantor is (``routing.is_bootstrap_admin``;
    04 §14.3 item 2 rev 1.254). Only the seed of a workspace writes it:
    ``tests/architecture/test_bootstrap_grant_writers.py`` lists the callers.
    """
    assignment_id = new_id()
    subject_type = ApprovalSubjectType.ROLE_ASSIGNMENT
    proposal = {
        "membership_id": str(membership_id),
        "role_id": str(role_id),
        "role_code": BOOTSTRAP_ROLE,
        "is_all_entities": True,
        "entity_ids": [],
    }
    content_sha256 = sha256_hex(proposal)
    auto_rule = routing.auto_approval(
        session,
        routing.auto_approval_facts(
            subject_type=subject_type,
            preparer_role_codes=(BOOTSTRAP_ROLE,),
            setup_completed=routing.setup_completed(session, tenant_id),
            source_channel=grantor.source_channel,
        ),
        at=now,
        rule_set_code=AUTO_BOOTSTRAP,
    )
    if auto_rule is None:
        raise LookupError(f"rule {AUTO_BOOTSTRAP} did not approve the bootstrap admin grant")
    routed = routing.resolve_steps(
        session,
        routing.routing_facts(
            subject_type=subject_type, entity_codes=(), amount_functional=None, flags=()
        ),
        fallback=BOOTSTRAP_STEP,
        at=now,
    )
    request_no = allocate(session, tenant_id, approvals.SERIES, 1)[0]
    created = {
        "created_by": grantor.created_by,
        "created_by_kind": grantor.created_by_kind.value,
    }
    request_id = approvals.insert_request(
        session,
        values={
            "tenant_id": tenant_id,
            "id": new_id(),
            "request_no": request_no,
            "subject_type": subject_type.value,
            "subject_id": assignment_id,
            "subject_content_sha256": content_sha256,
            "summary": "Grant the bootstrap Tenant Admin role",
            # The grant is for all entities, and the request says so (04 §16.10 rev 1.104: a role
            # assignment states the entities of the grant it proposes).
            **approvals.entity_columns(ALL_ENTITIES),
            "amount_functional": None,
            "amount_currency": None,
            "flags": [],
            "preparer_id": None,
            "preparer_kind": PrincipalKind.SYSTEM.value,
            "impact_preview_file_id": None,
            "impact_preview_sha256": None,
            "reason_code": None,
            "comment": None,
            **created,
        },
        routed=routed,
        now=now,
    )
    approvals.record_auto_approval(
        session,
        tenant_id=tenant_id,
        approval_request_id=request_id,
        subject_content_sha256=content_sha256,
        rule=auto_rule,
        now=now,
    )
    session.execute(
        insert(role_assignment).values(
            tenant_id=tenant_id,
            id=assignment_id,
            membership_id=membership_id,
            role_id=role_id,
            is_all_entities=True,
            entity_ids=[],
            valid_from=now,
            approval_request_id=request_id,
            created_at=now,
            **created,
        )
    )
    operator = grantor.audit
    return [
        build_event(
            tenant_id=tenant_id,
            actor=operator,
            occurred_at=now,
            action=approvals.SUBMIT_ACTION,
            object_type=approvals.OBJECT_TYPE,
            object_id=request_id,
            after=approvals.submit_audit_after(
                request_no=request_no,
                subject_type=subject_type,
                subject_id=assignment_id,
                subject_content_sha256=content_sha256,
                impact_preview_sha256=None,
                routed=routed,
                entities=ALL_ENTITIES,
            ),
            approval_request_id=request_id,
        ),
        build_event(
            tenant_id=tenant_id,
            actor=operator,
            occurred_at=now,
            action=approvals.AUTO_APPROVE_ACTION,
            object_type=approvals.OBJECT_TYPE,
            object_id=request_id,
            before={"status": "PENDING"},
            after=approvals.auto_approve_audit_after(auto_rule),
            approval_request_id=request_id,
        ),
        build_event(
            tenant_id=tenant_id,
            actor=operator,
            occurred_at=now,
            action=ROLE_ASSIGNMENT_CREATE,
            object_type="role_assignment",
            object_id=assignment_id,
            after=proposal,
            approval_request_id=request_id,
        ),
    ]


@dataclass(frozen=True, slots=True)
class SeededWorkspace:
    """What :func:`seed_workspace` hands its caller for the rows that follow the seed."""

    admin_role_id: UUID  # the ``tenant_admin`` role the bootstrap grant confers
    registry_defaults: list[dict[str, Any]]  # for the ``registry_version.seed`` events


def seed_workspace(
    session: Session,
    *,
    tenant_id: UUID,
    reporting_currency: str,
    stamp: Mapping[str, Any],
    published_by: UUID | None,
    now: datetime,
) -> SeededWorkspace:
    """The 04 §14.3 seed of a workspace whose ``tenant`` row exists, under the provisioning scope
    with the tenant's context set: the ten system roles and their permissions, the SoD rules, the
    three books and their ledger chain heads, the numbering series, the DEFAULT registry versions,
    the built-in dimensions, the reporting currency, the system close checklist and the rule sets
    ``AUTO-BOOTSTRAP``, ``DQ-SYSTEM`` and ``AUTO-MIG-01``.

    One function, so that ``tenant.provision`` and the empty sandbox of a reset (05 SBX-07 rev
    1.64) hold the same seed by construction. The caller writes the tenant row and its key before
    it, and the membership, its bootstrap grant, the ``audit_chain_head`` and the audit events
    around it."""
    roles, grants = default_role_rows(tenant_id, stamp=stamp)
    bootstrap_set, bootstrap_version, bootstrap_rule = auto_bootstrap_rows(
        tenant_id, stamp=stamp, published_at=now
    )
    dq_set, dq_version, dq_rules = data_quality_rows(tenant_id, stamp=stamp, published_at=now)
    mig_set, mig_version, mig_rule = auto_migration_rows(tenant_id, stamp=stamp, published_at=now)
    registry_defaults = registry_default_rows(tenant_id, published_at=now)
    session.execute(insert(role), roles)
    session.execute(insert(role_permission), grants)
    session.execute(
        insert(sod_rule),
        sod_rule_rows(tenant_id, stamp=stamp, published_by=published_by, published_at=now),
    )
    # 04 §14.3: the three books, before the numbering series.
    session.execute(insert(book), book_rows(tenant_id, stamp=stamp))
    # 04 §14.3: a ledger chain head per book (CTR-3; BS-D-12).
    session.execute(insert(ledger_chain_head), ledger_chain_head_rows(tenant_id, now=now))
    session.execute(insert(numbering_series), tenant_series_rows(tenant_id, stamp=stamp))
    session.execute(insert(registry_version), registry_defaults)
    session.execute(insert(dimension_definition), builtin_dimension_rows(tenant_id, stamp=stamp))
    # 04 §14.3: the reporting currency, enabled (T-REF-09; RFD-3).
    session.execute(
        insert(tenant_currency).values(
            tenant_id=tenant_id,
            currency_code=reporting_currency,
            is_enabled=True,
            **stamp,
        )
    )
    # 04 §14.3: the system close checklist, one template per gate check code (CLO-2).
    session.execute(
        insert(close_checklist_template),
        system_checklist_template_rows(tenant_id, stamp=stamp),
    )
    session.execute(insert(rule_set).values(**bootstrap_set))
    session.execute(insert(rule_set_version).values(**bootstrap_version))
    session.execute(insert(rule).values(**bootstrap_rule))
    # 04 §14.3 rev 1.21: the DQ-SYSTEM data-quality rule set (CLO-5; ruling Q-4).
    session.execute(insert(rule_set).values(**dq_set))
    session.execute(insert(rule_set_version).values(**dq_version))
    session.execute(insert(rule), dq_rules)
    # 04 §14.3 rev 1.72: the AUTO-MIG-01 legacy SSP replay auto-approval (D-98 133 AMENDMENT 4).
    session.execute(insert(rule_set).values(**mig_set))
    session.execute(insert(rule_set_version).values(**mig_version))
    session.execute(insert(rule).values(**mig_rule))
    return SeededWorkspace(
        admin_role_id=next(row["id"] for row in roles if row["code"] == BOOTSTRAP_ROLE),
        registry_defaults=registry_defaults,
    )


def provision_tenant(
    request: TenantProvisionRequest,
    *,
    actor: OperatorActor,
    clock: Clock,
    keyring: KeyRing,
    key_provisioner: TenantKeyProvisioner | None = None,
) -> TenantProvisionResult:
    """Provision a workspace (docstring of the module). ``key_provisioner`` is the KEY-05
    provisioning authority (DG-KRN-KEY-06 as extended by the hosted runtime contract): inside the
    provisioning transaction the tenant row is inserted first under its deterministic key id, so
    the unique code index refuses a duplicate before the provisioner ever runs (DG-KRN-TEN-02
    "creates nothing"; a directory read is not possible here, because RLS-TN hides other tenants'
    rows from the provisioning scope), then the key is created and read back; any failure rolls
    the row back, so a tenant commits only when its key can be read. ``None`` derives the key
    locally."""
    errors = validation_errors(request)
    if errors:
        raise Problem("validation-failed", errors=errors)
    now = clock.now()
    tenant_id, membership_id = new_id(), new_id()
    provisioner = key_provisioner or DerivedTenantKeyProvisioner(keyring)
    # The 256-bit token travels only in the invitation email; the row keeps its SHA-256 and the
    # outbox message a reference to it (T-PLT-07; T-INT-03 ``payload``).
    invitation = invitation_token(keyring)
    stamp = {
        "created_at": now,
        "created_by": actor.operator_user_id,
        "created_by_kind": PrincipalKind.OPERATOR.value,
        "updated_at": now,
        "updated_by": actor.operator_user_id,
        "updated_by_kind": PrincipalKind.OPERATOR.value,
    }
    expires_at = now + INVITATION_LIFETIME
    try:
        with platform_session(
            "provisioning",
            actor_user_id=actor.operator_user_id,
            request_id=actor.request_id,
            keyring=keyring,
        ) as session:
            # The row goes in first under its deterministic key id (DG-KRN-KEY-06): a duplicate
            # code fails on ux_tenant__code here, before the provisioner runs, so a repeated
            # request creates nothing anywhere (DG-KRN-TEN-02). The key is provisioned right
            # after, inside this transaction; a failure rolls the row back.
            audit_hmac_key_id = keyring.new_tenant_audit_key_id(tenant_id)
            session.execute(
                insert(tenant).values(
                    id=tenant_id,
                    code=request.code,
                    kind=TenantKind.PRODUCTION.value,
                    status=TenantStatus.ACTIVE.value,
                    display_name=request.display_name,
                    reporting_currency=request.reporting_currency,
                    is_demo=request.is_demo,
                    industry_cluster=request.industry_cluster,
                    audit_hmac_key_id=audit_hmac_key_id,
                    setup_completed_at=None,
                    **stamp,
                )
            )
            # Hosted, this creates the tenant secret and reads its first version back; the row
            # above is committed only if this returns (hosted runtime contract).
            provisioned_key_id = provisioner.provision_audit_key(tenant_id)
            if provisioned_key_id != audit_hmac_key_id:
                raise ProvisioningReadbackError(provisioned_key_id)
            name_platform_tenant(session, tenant_id)
            set_tenant_context(
                session, DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
            )
            user_id = _admin_user_id(session, email=request.admin_email.lower(), stamp=stamp)
            session.execute(
                insert(tenant_membership).values(
                    tenant_id=tenant_id,
                    id=membership_id,
                    user_id=user_id,
                    status=MembershipStatus.INVITED.value,
                    invited_at=now,
                    invitation_token_sha256=hashlib.sha256(
                        invitation.token.encode("ascii")
                    ).hexdigest(),
                    invitation_expires_at=expires_at,
                    **stamp,
                )
            )
            # The minute outbox sweeper relays it once provisioning commits (SCH-03; SPEC-Q-179).
            outbox.insert_message(
                session,
                invitation_message(
                    tenant_id=tenant_id,
                    membership_id=membership_id,
                    email=request.admin_email.lower(),
                    workspace_name=request.display_name,
                    link_reference=invitation.reference,
                    key_id=invitation.key_id,
                    expires_at=expires_at,
                    created_by=actor.operator_user_id,
                    created_by_kind=PrincipalKind.OPERATOR,
                    now=now,
                ),
            )
            seeded = seed_workspace(
                session,
                tenant_id=tenant_id,
                reporting_currency=request.reporting_currency,
                stamp=stamp,
                published_by=actor.operator_user_id,
                now=now,
            )
            registry_defaults = seeded.registry_defaults
            grant_events = _grant_bootstrap_admin(
                session,
                tenant_id=tenant_id,
                membership_id=membership_id,
                role_id=seeded.admin_role_id,
                actor=actor,
                now=now,
            )
            # 04 §14.3: the chain head, then the audit events, as the last tenant writes.
            session.execute(
                insert(audit_chain_head).values(
                    tenant_id=tenant_id, last_chain_seq=0, updated_at=now
                )
            )
            append_events(
                session,
                tenant_id=tenant_id,
                keyring=keyring,
                events=[
                    _provision_event(request, actor=actor, tenant_id=tenant_id, now=now),
                    *_registry_seed_events(registry_defaults, actor=actor, now=now),
                    *grant_events,
                ],
            )
    except IntegrityError as error:
        if _constraint_name(error) != TENANT_CODE_INDEX:
            raise
        raise _code_exists() from error
    return TenantProvisionResult(
        tenant=MappingProxyType(
            {
                "id": tenant_id,
                "code": request.code,
                "kind": TenantKind.PRODUCTION.value,
                "display_name": request.display_name,
                "reporting_currency": request.reporting_currency,
                "is_demo": request.is_demo,
            }
        ),
        admin_membership_id=membership_id,
        invitation_expires_at=expires_at,
    )
