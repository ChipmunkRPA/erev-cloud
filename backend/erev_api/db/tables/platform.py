"""Platform tables (04 §4)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Final

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    SmallInteger,
    Table,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, INET, JSONB

from erev_api.db.tables import metadata
from erev_api.db.types import MoneyType
from erev_api.enums import (
    AccessReviewDecision,
    AccessReviewStatus,
    ApiClientStatus,
    ApprovalDecisionKind,
    ApprovalRequestStatus,
    ApprovalStepStatus,
    ApprovalSubjectType,
    AuditOutcome,
    BookCode,
    ConfigStatus,
    ControlResult,
    FilePurpose,
    GrantStatus,
    IdentityProviderKind,
    JobKind,
    JobState,
    MembershipStatus,
    NotificationKind,
    PrincipalKind,
    RegistryCategory,
    RegistryScope,
    RunStatus,
    SecurityEventKind,
    SessionEndReason,
    TenantKind,
    TenantStatus,
    UserStatus,
    WebhookDeliveryStatus,
)


def _enum(values: type[StrEnum], name: str) -> ENUM:
    """An existing PostgreSQL enum type of schema erev; revisions create the types (DG-MIG-06)."""
    return ENUM(*(member.value for member in values), name=name, schema="erev", create_type=False)


# Created by revision 0004 (PLF-1): E-15, E-16, E-78 to E-81, E-101, E-102.
principal_kind: Final = _enum(PrincipalKind, "principal_kind")
tenant_kind: Final = _enum(TenantKind, "tenant_kind")
membership_status: Final = _enum(MembershipStatus, "membership_status")
security_event_kind: Final = _enum(SecurityEventKind, "security_event_kind")
identity_provider_kind: Final = _enum(IdentityProviderKind, "identity_provider_kind")
audit_outcome: Final = _enum(AuditOutcome, "audit_outcome")
tenant_status: Final = _enum(TenantStatus, "tenant_status")
user_status: Final = _enum(UserStatus, "user_status")
# Created by revision 0005 (PLF-2): E-104.
session_end_reason: Final = _enum(SessionEndReason, "session_end_reason")


def _timestamp(name: str, *, nullable: bool = True, now_default: bool = False) -> Column[Any]:
    default = text("now()") if now_default else None
    return Column(name, DateTime(timezone=True), nullable=nullable, server_default=default)


def _sc_c_sc_m() -> tuple[Column[Any], ...]:
    """SC-C then SC-M (04 §1.3); a new tuple per table, because a Column belongs to one table."""
    return (
        _timestamp("created_at", nullable=False, now_default=True),
        Column("created_by", Uuid(), nullable=True),
        Column("created_by_kind", principal_kind, nullable=False),
        _timestamp("updated_at", nullable=False, now_default=True),
        Column("updated_by", Uuid(), nullable=True),
        Column("updated_by_kind", principal_kind, nullable=False),
        Column("row_version", Integer(), nullable=False, server_default=text("1")),
    )


# E-53 and E-54, created by revision 0003.
registry_category: Final = ENUM(
    *(category.value for category in RegistryCategory),
    name="registry_category",
    schema="erev",
    create_type=False,
)
registry_scope: Final = ENUM(
    *(scope.value for scope in RegistryScope),
    name="registry_scope",
    schema="erev",
    create_type=False,
)

# T-PLT-11: global permission catalogue (IM-A, RLS-NONE-G), seeded from auth.permissions.CATALOGUE.
permission: Final = Table(
    "permission",
    metadata,
    Column("code", Text(), primary_key=True),
    Column("area", Text(), nullable=False),
    Column("description", Text(), nullable=False),
    Column("is_approval", Boolean(), nullable=False),
    Column("is_access_admin", Boolean(), nullable=False),
    Column("requires_mfa", Boolean(), nullable=False),
)

# T-PLT-31: global registry catalogue (IM-A, RLS-NONE-G), seeded from registry.policies and
# registry.platform.
registry_parameter: Final = Table(
    "registry_parameter",
    metadata,
    Column("code", Text(), primary_key=True),
    Column("pol_id", Text(), nullable=True),
    Column("category", registry_category, nullable=False),
    Column("value_schema", JSONB(), nullable=False),
    Column("default_asc606", JSONB(), nullable=False),
    Column("default_ifrs15", JSONB(), nullable=True),
    Column("is_forced_asc606", Boolean(), nullable=False, server_default=text("false")),
    Column("is_forced_ifrs15", Boolean(), nullable=False, server_default=text("false")),
    Column("legacy_parity_value", JSONB(), nullable=True),
    Column("allowed_levels", ARRAY(registry_scope), nullable=False),
    Column("pin", CHAR(1), nullable=False),
    Column("approval_code", Text(), nullable=False),
    Column("description", Text(), nullable=False),
    Column("source_ref", Text(), nullable=False),
    Column("section", Text(), nullable=False),
)

# T-PLT-03: login methods (IM-M, RLS-NONE-U); erev_app reads only (04 §14.2).
identity_provider: Final = Table(
    "identity_provider",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("kind", identity_provider_kind, nullable=False),
    Column("display_name", Text(), nullable=False),
    Column("issuer_url", Text(), nullable=True),
    Column("client_id", Text(), nullable=True),
    Column("client_secret_ref", Text(), nullable=True),
    Column("config", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    # The email domains the provider is authoritative for (REQ-PLT-006; revision 0092).
    Column("email_domains", ARRAY(Text()), nullable=False, server_default=text("'{}'")),
    Column("is_enabled", Boolean(), nullable=False, server_default=text("true")),
    *_sc_c_sc_m(),
)

# T-PLT-02: global human identity (IM-M, RLS-NONE-U). DB-19 ``tg_app_user__erasure_guard``
# (revision 0073): ``email`` and ``external_id`` change only in the erased form of
# ``user.anonymise`` (05 PRV-07 a), else EREV-PRV-001.
app_user: Final = Table(
    "app_user",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("email", Text(), nullable=False),
    Column("display_name", Text(), nullable=False),
    Column("password_hash", Text(), nullable=True),
    _timestamp("password_changed_at"),
    Column("status", user_status, nullable=False, server_default=text("'ACTIVE'")),
    Column("failed_login_count", Integer(), nullable=False, server_default=text("0")),
    _timestamp("locked_until"),
    Column("identity_provider_id", Uuid(), nullable=True),
    # The subject the provider names the identity by, recorded at its first sign-in through the
    # provider (REQ-PLT-006; revision 0092).
    Column("identity_provider_subject", Text(), nullable=True),
    Column("external_id", Text(), nullable=True),
    Column("is_operator", Boolean(), nullable=False, server_default=text("false")),
    Column("preferences", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    _timestamp("last_login_at"),
    *_sc_c_sc_m(),
)

# T-PLT-04: TOTP factor per user (IM-M, RLS-NONE-U).
user_mfa_factor: Final = Table(
    "user_mfa_factor",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("user_id", Uuid(), nullable=False),
    Column("factor_kind", Text(), nullable=False, server_default=text("'TOTP'")),
    Column("secret_ciphertext", LargeBinary(), nullable=False),
    Column("secret_key_id", Text(), nullable=False),
    _timestamp("confirmed_at"),
    Column("last_used_step", BigInteger(), nullable=True),
    _timestamp("disabled_at"),
    *_sc_c_sc_m(),
)

# T-PLT-05: single-use recovery codes per batch (IM-S on used_at, RLS-NONE-U); DB-03 trigger.
user_recovery_code: Final = Table(
    "user_recovery_code",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("user_id", Uuid(), nullable=False),
    Column("batch_id", Uuid(), nullable=False),
    Column("code_hash", Text(), nullable=False),
    _timestamp("used_at"),
    _timestamp("created_at", nullable=False, now_default=True),
)

# T-PLT-01: a customer organisation's data space (IM-M, RLS-TN).
tenant: Final = Table(
    "tenant",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("kind", tenant_kind, nullable=False),
    Column("status", tenant_status, nullable=False, server_default=text("'ACTIVE'")),
    Column("display_name", Text(), nullable=False),
    Column("reporting_currency", CHAR(3), nullable=False),
    Column("source_tenant_id", Uuid(), nullable=True),
    _timestamp("source_known_at"),
    Column("is_demo", Boolean(), nullable=False, server_default=text("false")),
    Column("industry_cluster", Text(), nullable=True),
    Column("audit_hmac_key_id", Text(), nullable=False),
    Column("default_locale", Text(), nullable=False, server_default=text("'en-US'")),
    _timestamp("setup_completed_at"),
    _timestamp("ai_disabled_at"),
    Column("ai_disabled_by", Uuid(), nullable=True),
    Column("ai_disabled_by_kind", principal_kind, nullable=True),
    *_sc_c_sc_m(),
)

# T-PLT-07: a user's membership of a tenant (IM-M, RLS-TM).
tenant_membership: Final = Table(
    "tenant_membership",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("user_id", Uuid(), nullable=False),
    Column("status", membership_status, nullable=False, server_default=text("'INVITED'")),
    _timestamp("invited_at", nullable=False, now_default=True),
    Column("invitation_token_sha256", CHAR(64), nullable=True),
    _timestamp("invitation_expires_at"),
    _timestamp("activated_at"),
    _timestamp("removed_at"),
    _timestamp("last_opened_at"),
    *_sc_c_sc_m(),
)

# T-PLT-06: pre-tenant security log, hash-chained globally (IM-A, RLS-NONE-U).
security_event: Final = Table(
    "security_event",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("chain_seq", BigInteger(), nullable=False),
    _timestamp("occurred_at", nullable=False, now_default=True),
    Column("kind", security_event_kind, nullable=False),
    Column("outcome", audit_outcome, nullable=False),
    Column("user_id", Uuid(), nullable=True),
    Column("email_sha256", CHAR(64), nullable=True),
    Column("session_id", Uuid(), nullable=True),
    Column("tenant_id", Uuid(), nullable=True),
    Column("ip_address", INET(), nullable=True),
    Column("user_agent", Text(), nullable=True),
    Column("request_id", Text(), nullable=False),
    Column("detail", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    Column("prev_hmac", CHAR(64), nullable=True),
    Column("hmac", CHAR(64), nullable=False),
    # Rev 1.42 (SPEC-Q-116 ruling, migration 0061): the key the row was signed with and the form
    # of its HMAC preimage; rows before 0061 carry NULL / 1 and are attributed to security-hmac:1.
    Column("hmac_key_id", Text(), nullable=True),
    Column("canonical_version", SmallInteger(), nullable=False, server_default=text("1")),
)

# T-PLT-08: server-side browser session (IM-E, RLS-NONE-U).
user_session: Final = Table(
    "user_session",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("user_id", Uuid(), nullable=False),
    Column("token_sha256", CHAR(64), nullable=False),
    Column("csrf_token_sha256", CHAR(64), nullable=False),
    Column("auth_method", identity_provider_kind, nullable=False),
    _timestamp("mfa_verified_at"),
    Column("active_tenant_id", Uuid(), nullable=True),
    _timestamp("created_at", nullable=False, now_default=True),
    _timestamp("last_seen_at", nullable=False, now_default=True),
    _timestamp("idle_expires_at", nullable=False),
    _timestamp("absolute_expires_at", nullable=False),
    _timestamp("ended_at"),
    Column("end_reason", session_end_reason, nullable=True),
    Column("operator_support_grant_id", Uuid(), nullable=True),
    Column("ip_address", INET(), nullable=True),
    Column("user_agent", Text(), nullable=True),
    _timestamp("expires_at"),
)

# T-PLT-42: single-use password reset token (IM-E, RLS-NONE-U); revision 0017 (PLF-15).
password_reset_token: Final = Table(
    "password_reset_token",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("user_id", Uuid(), nullable=False),
    Column("token_sha256", CHAR(64), nullable=False),
    _timestamp("created_at", nullable=False, now_default=True),
    _timestamp("token_expires_at", nullable=False),
    _timestamp("used_at"),
    _timestamp("superseded_at"),
    Column("request_id", Text(), nullable=False),
    Column("ip_address", INET(), nullable=True),
    _timestamp("expires_at", nullable=False),
)

# T-PLT-38: the release stamped on computations and runs (IM-A, RLS-NONE-G); revision 0018 (PLF-20).
engine_release: Final = Table(
    "engine_release",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("engine_version", Text(), nullable=False),
    Column("build_sha", Text(), nullable=False),
    Column("schema_revision", Text(), nullable=False),
    _timestamp("deployed_at", nullable=False, now_default=True),
    Column("release_notes", Text(), nullable=True),
    Column("control_impact_tags", ARRAY(Text()), nullable=False, server_default=text("'{}'")),
    Column("gate_results", JSONB(none_as_null=True), nullable=False, server_default=text("'{}'")),
    # 04 rev 1.29 (D-96 (3)): the REL-01 declaration; CHECK ck_engine_release__validation_level in
    # the DDL (revision 0055, assigned at slice 1c; not applied to any database before the merge).
    Column("validation_level", Text(), nullable=False, server_default=text("'PATCH'")),
)

# T-PLT-22: per-tenant audit chain pointer (IM-X, RLS-T); DB-09 advances it.
audit_chain_head: Final = Table(
    "audit_chain_head",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("last_chain_seq", BigInteger(), nullable=False, server_default=text("0")),
    Column("last_hmac", CHAR(64), nullable=True),
    _timestamp("last_occurred_at"),
    _timestamp("updated_at", nullable=False, now_default=True),
)

# T-PLT-19: tenant audit log, HMAC-chained per tenant (IM-A, RLS-T, PT-MOC).
audit_event: Final = Table(
    "audit_event",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    # PRIMARY KEY (tenant_id, occurred_at, id): the partition key is part of the key (04 T-… Keys;
    # revision 0006; DG-ARC-15 finding F2, D-98 candidate 136 amendment 1).
    Column(
        "occurred_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        primary_key=True,
    ),
    Column("id", Uuid(), primary_key=True),
    Column("chain_seq", BigInteger(), nullable=False),
    Column("actor_id", Uuid(), nullable=True),
    Column("actor_kind", principal_kind, nullable=False),
    Column("actor_roles", ARRAY(Text()), nullable=False, server_default=text("'{}'")),
    Column("auth_method", Text(), nullable=True),
    Column("mfa_verified", Boolean(), nullable=True),
    Column("on_behalf_of_id", Uuid(), nullable=True),
    Column("api_client_id", Uuid(), nullable=True),
    Column("support_grant_id", Uuid(), nullable=True),
    Column("source_ip", INET(), nullable=True),
    Column("request_id", Text(), nullable=False),
    Column("action", Text(), nullable=False),
    Column("object_type", Text(), nullable=False),
    Column("object_id", Uuid(), nullable=True),
    Column("object_version", Text(), nullable=True),
    # SQL NULL, never JSON null, when absent (ck_audit_event__diff).
    Column("before", JSONB(none_as_null=True), nullable=True),
    Column("after", JSONB(none_as_null=True), nullable=True),
    Column("diff", JSONB(none_as_null=True), nullable=True),
    Column("reason_code", Text(), nullable=True),
    Column("comment", Text(), nullable=True),
    Column("approval_request_id", Uuid(), nullable=True),
    Column("outcome", audit_outcome, nullable=False),
    Column("detail", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    Column("prev_hmac", CHAR(64), nullable=True),
    Column("hmac", CHAR(64), nullable=False),
    Column("hmac_key_id", Text(), nullable=False),
)

# T-PLT-48: the contracts an audit event names, one row a contract (IM-A, RLS-T, PT-N); revision
# 0101. It is the index of the contract key of T-PLT-19, written by ``audit.chain.append_events``
# from ``audit_event.detail`` in the event's transaction: a read by contract compares plain
# columns, which is what an index condition under a row-level-security policy must do (the
# ``jsonb`` operators are not leakproof). The event is the evidence; this is derived from it.
audit_event_contract: Final = Table(
    "audit_event_contract",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("contract_id", Uuid(), primary_key=True),
    Column("chain_seq", BigInteger(), primary_key=True),
    _timestamp("occurred_at", nullable=False),
    Column("audit_event_id", Uuid(), nullable=False),
)


def _sc_c() -> tuple[Column[Any], ...]:
    """SC-C (04 §1.3) of a table without SC-M."""
    return (
        _timestamp("created_at", nullable=False, now_default=True),
        Column("created_by", Uuid(), nullable=True),
        Column("created_by_kind", principal_kind, nullable=False),
    )


# T-PLT-47 (04 rev 1.59; D-98 candidate 125): append-only metadata corrections of seeded T-PLT-31
# rows — complete snapshots of the four metadata columns, appended only by governed Alembic
# revisions (IM-A global reference, RLS-NONE-G; erev_app reads only). The catalogue's effective
# relation (erev_api.registry.effective) reads the latest correction per code over the seed.
registry_parameter_correction: Final = Table(
    "registry_parameter_correction",
    metadata,
    Column("code", Text(), ForeignKey("erev.registry_parameter.code"), primary_key=True),
    Column("correction_no", Integer(), primary_key=True),
    Column("value_schema", JSONB(), nullable=False),
    Column("description", Text(), nullable=False),
    Column("source_ref", Text(), nullable=False),
    Column("section", Text(), nullable=False),
    Column("applied_by_revision", Text(), nullable=False),
    *_sc_c(),
    CheckConstraint("correction_no >= 1", name="ck_registry_parameter_correction__correction_no"),
)

# T-PLT-09: named permission set (IM-M, RLS-T).
role: Final = Table(
    "role",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("description", Text(), nullable=True),
    Column("is_system", Boolean(), nullable=False, server_default=text("false")),
    Column("is_active", Boolean(), nullable=False, server_default=text("true")),
    Column("content_sha256", CHAR(64), nullable=False),
    *_sc_c_sc_m(),
)

# T-PLT-10: a role granted to a membership (IM-S, RLS-T); DB-03 and DB-12 triggers.
role_assignment: Final = Table(
    "role_assignment",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("membership_id", Uuid(), nullable=False),
    Column("role_id", Uuid(), nullable=False),
    Column("is_all_entities", Boolean(), nullable=False, server_default=text("true")),
    Column("entity_ids", ARRAY(Uuid()), nullable=False, server_default=text("'{}'::uuid[]")),
    _timestamp("valid_from", nullable=False, now_default=True),
    _timestamp("valid_to"),
    Column("approval_request_id", Uuid(), nullable=True),
    Column("sod_exception_id", Uuid(), nullable=True),
    _timestamp("revoked_at"),
    Column("revoked_by", Uuid(), nullable=True),
    Column("revoked_by_kind", principal_kind, nullable=True),
    *_sc_c(),
)

# T-PLT-12: permission membership of a role (IM-M with DELETE; DB-01 blocks UPDATE; RLS-T).
role_permission: Final = Table(
    "role_permission",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("role_id", Uuid(), primary_key=True),
    Column("permission_code", Text(), primary_key=True),
    *_sc_c(),
)

# Created by revision 0009 (PLF-6): E-12, E-96.
config_status: Final = _enum(ConfigStatus, "config_status")
grant_status: Final = _enum(GrantStatus, "grant_status")


def _sc_v() -> tuple[Column[Any], ...]:
    """SC-V (04 §1.3): versioned configuration columns."""
    return (
        Column("version_no", Integer(), nullable=False),
        Column("status", config_status, nullable=False, server_default=text("'DRAFT'")),
        _timestamp("effective_from"),
        _timestamp("effective_to"),
        Column("content_sha256", CHAR(64), nullable=True),
        Column("approval_request_id", Uuid(), nullable=True),
        _timestamp("published_at"),
        Column("published_by", Uuid(), nullable=True),
        Column("supersedes_version_id", Uuid(), nullable=True),
    )


# T-PLT-13: conflicting permission pairs (IM-P, SC-V, RLS-T); DB-04 and DB-12 triggers.
sod_rule: Final = Table(
    "sod_rule",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("function_a_permissions", ARRAY(Text()), nullable=False),
    Column("function_b_permissions", ARRAY(Text()), nullable=False),
    Column("rationale", Text(), nullable=False),
    *_sc_c_sc_m(),
    *_sc_v(),
)

# T-PLT-14: approved exception for a conflicting combination (IM-S, RLS-T); DB-03 trigger.
sod_exception: Final = Table(
    "sod_exception",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("sod_rule_code", Text(), nullable=False),
    Column("membership_id", Uuid(), nullable=False),
    Column("compensating_control", Text(), nullable=False),
    Column("status", grant_status, nullable=False, server_default=text("'REQUESTED'")),
    _timestamp("valid_from", nullable=False),
    _timestamp("valid_to", nullable=False),
    Column("approval_request_id", Uuid(), nullable=True),
    _timestamp("approved_at"),
    _timestamp("revoked_at"),
    Column("revoked_by", Uuid(), nullable=True),
    Column("revoked_by_kind", principal_kind, nullable=True),
    *_sc_c(),
)

# E-02, created by revision 0015 (PLF-13).
book_code: Final = _enum(BookCode, "book_code")

# T-PLT-32: tenant values of one registry category at one scope (IM-P, SC-V; RLS-TE with a NULL
# entity visible to every scope); DB-04 trigger. Read the values column as ``c["values"]``, because
# ``ColumnCollection.values`` is a method.
registry_version: Final = Table(
    "registry_version",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("category", registry_category, nullable=False),
    Column("scope", registry_scope, nullable=False),
    Column("book_code", book_code, nullable=True),
    Column("entity_id", Uuid(), nullable=True),
    Column("values", JSONB(none_as_null=True), nullable=False, server_default=text("'{}'::jsonb")),
    Column("preset_code", Text(), nullable=True),
    Column("test_evidence", JSONB(none_as_null=True), nullable=True),
    Column("impact_simulation_file_id", Uuid(), nullable=True),
    *_sc_c_sc_m(),
    *_sc_v(),
)

# T-PLT-28: stored first response per Idempotency-Key (IM-E, RLS-T); revision 0010 (PLF-7).
idempotency_record: Final = Table(
    "idempotency_record",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("principal_id", Uuid(), primary_key=True),
    Column("idempotency_key", Text(), primary_key=True),
    Column("principal_kind", principal_kind, nullable=False),
    Column("method", Text(), nullable=False),
    Column("path", Text(), nullable=False),
    Column("request_sha256", CHAR(64), nullable=False),
    Column("state", Text(), nullable=False, server_default=text("'IN_PROGRESS'")),
    Column("response_status", Integer(), nullable=True),
    Column("response_headers", JSONB(none_as_null=True), nullable=True),
    Column("response_body", JSONB(none_as_null=True), nullable=True),
    Column("response_file_id", Uuid(), nullable=True),
    _timestamp("created_at", nullable=False, now_default=True),
    _timestamp("completed_at"),
    _timestamp("expires_at", nullable=False),
)

# Created by revision 0011 (PLF-8): E-68.
file_purpose: Final = _enum(FilePurpose, "file_purpose")

# T-PLT-29: content-addressed file metadata (IM-A with the DB-03 update allow-list, RLS-T).
file_object: Final = Table(
    "file_object",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("sha256", CHAR(64), nullable=False),
    Column("size_bytes", BigInteger(), nullable=False),
    Column("media_type", Text(), nullable=False),
    Column("original_filename", Text(), nullable=True),
    Column("purpose", file_purpose, nullable=False),
    Column("storage_backend", Text(), nullable=False),
    Column("storage_key", Text(), nullable=False),
    Column("retention_until", Date(), nullable=True),
    Column("legal_hold", Boolean(), nullable=False, server_default=text("false")),
    _timestamp("shredded_at"),
    Column("shredded_by", Uuid(), nullable=True),
    Column("shredded_by_kind", principal_kind, nullable=True),
    Column("shred_reason", Text(), nullable=True),
    _timestamp("shred_completed_at"),
    *_sc_c(),
)

# E-67 (RPS-1), read here for T-PLT-34.
run_status_platform: Final = _enum(RunStatus, "run_status")

# T-PLT-34: a stored copy of a tenant as of known_at (IM-S, RLS-T); DB-03 and DB-15 triggers.
tenant_snapshot: Final = Table(
    "tenant_snapshot",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    _timestamp("known_at", nullable=False),
    Column("purpose", Text(), nullable=False),
    Column("status", run_status_platform, nullable=False, server_default=text("'QUEUED'")),
    Column("target_tenant_id", Uuid(), nullable=True),
    Column("manifest_file_id", Uuid(), nullable=True),
    Column("manifest_sha256", CHAR(64), nullable=True),
    Column("row_counts", JSONB(none_as_null=True), nullable=True),
    Column("job_id", Uuid(), nullable=True),
    _timestamp("started_at"),
    _timestamp("finished_at"),
    *_sc_c(),
)

# T-PLT-30: a file linked to a subject record (IM-S: void columns, RLS-T); DB-03 and DB-11 triggers.
file_attachment: Final = Table(
    "file_attachment",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("file_object_id", Uuid(), nullable=False),
    Column("subject_type", Text(), nullable=False),
    Column("subject_id", Uuid(), nullable=False),
    Column("description", Text(), nullable=True),
    _timestamp("voided_at"),
    Column("voided_by", Uuid(), nullable=True),
    Column("voided_by_kind", principal_kind, nullable=True),
    Column("void_reason", Text(), nullable=True),
    *_sc_c(),
)
# T-PLT-49: the uploads of a stored file, one row per file and uploader with the uploader's own
# file name and time (IM-A, RLS-T, PT-N); revision 0103. Identical content of one purpose is one
# ``file_object`` row; ``attachments.upload_file`` writes a row here for the principal that stores
# a file and for each other principal that uploads the same bytes, so that every uploader reads
# and uses the upload (``file_access.uploaded_by``) and is shown their own facts, not the first
# uploader's (04 T-PLT-29 "Uploads of the same bytes"; ruling R-111 (5)).
file_upload: Final = Table(
    "file_upload",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("file_object_id", Uuid(), primary_key=True),
    Column("uploaded_by", Uuid(), primary_key=True),
    Column("uploaded_by_kind", principal_kind, primary_key=True),
    Column("original_filename", Text(), nullable=True),
    _timestamp("uploaded_at", nullable=False),
)


def _sc_m() -> tuple[Column[Any], ...]:
    """SC-M (04 §1.3) of a table without SC-C, or placed after SC-C."""
    return (
        _timestamp("updated_at", nullable=False, now_default=True),
        Column("updated_by", Uuid(), nullable=True),
        Column("updated_by_kind", principal_kind, nullable=False),
        Column("row_version", Integer(), nullable=False, server_default=text("1")),
    )


# Created by revision 0012 (PLF-9): E-13, E-14.
job_state: Final = _enum(JobState, "job_state")
job_kind: Final = _enum(JobKind, "job_kind")

# T-PLT-26: human-facing sequential numbers (IM-X, RLS-T).
numbering_series: Final = Table(
    "numbering_series",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("series_code", Text(), nullable=False),
    Column("scope_key", Text(), nullable=False, server_default=text("''")),
    Column("prefix", Text(), nullable=False),
    Column("next_value", BigInteger(), nullable=False, server_default=text("1")),
    Column("padding", Integer(), nullable=False, server_default=text("6")),
    Column("is_gapless", Boolean(), nullable=False),
    *_sc_m(),
)

# T-PLT-27: API-visible job wrapping a Procrastinate task (IM-S, RLS-T); DB-03 trigger.
job: Final = Table(
    "job",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("kind", job_kind, nullable=False),
    Column("state", job_state, nullable=False, server_default=text("'QUEUED'")),
    Column("params", JSONB(none_as_null=True), nullable=False),
    Column("queue", Text(), nullable=False, server_default=text("'default'")),
    Column("priority", Integer(), nullable=False, server_default=text("0")),
    Column("progress_done", BigInteger(), nullable=False, server_default=text("0")),
    Column("progress_total", BigInteger(), nullable=True),
    Column("result", JSONB(none_as_null=True), nullable=True),
    Column("problem", JSONB(none_as_null=True), nullable=True),
    Column("procrastinate_job_id", BigInteger(), nullable=True),
    Column("parent_job_id", Uuid(), nullable=True),
    _timestamp("started_at"),
    _timestamp("finished_at"),
    _timestamp("cancel_requested_at"),
    Column("subject_type", Text(), nullable=True),
    Column("subject_id", Uuid(), nullable=True),
    *_sc_c(),
    *_sc_m(),
)

# Created by revision 0013 (PLF-10): E-05 to E-08.
approval_request_status: Final = _enum(ApprovalRequestStatus, "approval_request_status")
approval_step_status: Final = _enum(ApprovalStepStatus, "approval_step_status")
approval_decision_kind: Final = _enum(ApprovalDecisionKind, "approval_decision_kind")
approval_subject_type: Final = _enum(ApprovalSubjectType, "approval_subject_type")

# T-PLT-17: one approval routing instance for one subject (IM-S, RLS-TE on a nullable entity_id).
# Rev 1.104 (revision 0086; R-25): entity_ids / is_all_entities state the entities of a subject
# that spans several, frozen at submission; ck_approval_request__entity_scope keeps the three
# columns exclusive.
approval_request: Final = Table(
    "approval_request",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("request_no", Text(), nullable=False),
    Column("subject_type", approval_subject_type, nullable=False),
    Column("subject_id", Uuid(), nullable=False),
    Column("subject_row_version", Integer(), nullable=True),
    Column("subject_content_sha256", CHAR(64), nullable=False),
    Column("summary", Text(), nullable=False),
    Column("entity_id", Uuid(), nullable=True),
    Column("entity_ids", ARRAY(Uuid()), nullable=False, server_default=text("'{}'::uuid[]")),
    Column("is_all_entities", Boolean(), nullable=False, server_default=text("false")),
    Column("amount_functional", MoneyType(), nullable=True),
    Column("amount_currency", CHAR(3), nullable=True),
    Column("flags", ARRAY(Text()), nullable=False, server_default=text("'{}'")),
    Column("routing_rule_set_version_id", Uuid(), nullable=True),
    Column("routing_rule_id", Uuid(), nullable=True),
    Column("status", approval_request_status, nullable=False, server_default=text("'PENDING'")),
    Column("current_step_no", Integer(), nullable=False, server_default=text("1")),
    Column("preparer_id", Uuid(), nullable=True),
    Column("preparer_kind", principal_kind, nullable=False),
    _timestamp("submitted_at", nullable=False, now_default=True),
    _timestamp("decided_at"),
    _timestamp("voided_at"),
    Column("void_reason", Text(), nullable=True),
    Column("impact_preview_file_id", Uuid(), nullable=True),
    Column("impact_preview_sha256", CHAR(64), nullable=True),
    Column("reason_code", Text(), nullable=True),
    Column("comment", Text(), nullable=True),
    *_sc_c(),
)

# T-PLT-18: a level of a multi-level approval (IM-S, RLS-T); DB-03 trigger.
approval_step: Final = Table(
    "approval_step",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("approval_request_id", Uuid(), nullable=False),
    Column("step_no", Integer(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("required_permission", Text(), nullable=False),
    Column("required_role_id", Uuid(), nullable=True),
    Column("min_approvers", Integer(), nullable=False, server_default=text("1")),
    Column("status", approval_step_status, nullable=False, server_default=text("'WAITING'")),
    _timestamp("activated_at"),
    _timestamp("completed_at"),
)

# T-PLT-20: an approve, reject or auto-approve decision (IM-A, RLS-T); DB-10 trigger.
approval_decision: Final = Table(
    "approval_decision",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("approval_request_id", Uuid(), nullable=False),
    Column("approval_step_id", Uuid(), nullable=False),
    Column("decision", approval_decision_kind, nullable=False),
    Column("approver_id", Uuid(), nullable=True),
    Column("approver_kind", principal_kind, nullable=False),
    Column("delegation_id", Uuid(), nullable=True),
    Column("on_behalf_of_id", Uuid(), nullable=True),
    Column("auto_rule_set_version_id", Uuid(), nullable=True),
    Column("auto_rule_id", Uuid(), nullable=True),
    Column("subject_content_sha256", CHAR(64), nullable=False),
    Column("impact_preview_sha256", CHAR(64), nullable=True),
    _timestamp("mfa_verified_at"),
    Column("reason_code", Text(), nullable=True),
    Column("comment", Text(), nullable=True),
    _timestamp("decided_at", nullable=False, now_default=True),
)

# Created by revision 0016 (PLF-14): E-69.
notification_kind: Final = _enum(NotificationKind, "notification_kind")

# T-PLT-24: in-app notification (IM-S: read_at, email_sent_at; RLS-T); DB-03 trigger.
notification: Final = Table(
    "notification",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("recipient_membership_id", Uuid(), nullable=False),
    Column("kind", notification_kind, nullable=False),
    Column("subject_type", Text(), nullable=True),
    Column("subject_id", Uuid(), nullable=True),
    Column("title", Text(), nullable=False),
    Column("body", Text(), nullable=True),
    Column("link_path", Text(), nullable=True),
    _timestamp("read_at"),
    _timestamp("email_sent_at"),
    *_sc_c(),
)

# T-PLT-25: per-membership subscription preferences (IM-M, RLS-T).
notification_preference: Final = Table(
    "notification_preference",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("membership_id", Uuid(), nullable=False),
    Column("kind", notification_kind, nullable=False),
    Column("in_app", Boolean(), nullable=False, server_default=text("true")),
    Column("email", Boolean(), nullable=False, server_default=text("false")),
    *_sc_m(),
)

# T-PLT-37: saved grid views and favourites per membership (IM-M with DELETE, RLS-T).
saved_view: Final = Table(
    "saved_view",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("membership_id", Uuid(), nullable=False),
    Column("screen_code", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("config", JSONB(), nullable=False),
    Column("is_shared", Boolean(), nullable=False, server_default=text("false")),
    Column("is_favourite", Boolean(), nullable=False, server_default=text("false")),
    *_sc_c_sc_m(),
)

# Created by revision 0020 (PLF-23): E-98.
control_result: Final = _enum(ControlResult, "control_result")

# T-PLT-23: result and digest of one audit chain verification run (IM-A, RLS-T).
audit_chain_verification: Final = Table(
    "audit_chain_verification",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("trigger", Text(), nullable=False),
    Column("from_chain_seq", BigInteger(), nullable=False),
    Column("to_chain_seq", BigInteger(), nullable=False),
    Column("events_checked", BigInteger(), nullable=False),
    Column("result", control_result, nullable=False),
    Column("first_failure_seq", BigInteger(), nullable=True),
    Column("failure_detail", JSONB(none_as_null=True), nullable=True),
    Column("digest_last_hmac", CHAR(64), nullable=True),
    Column("digest_file_id", Uuid(), nullable=True),
    Column("job_id", Uuid(), nullable=True),
    _timestamp("started_at", nullable=False),
    _timestamp("finished_at", nullable=False),
    *_sc_c(),
)

# T-PLT-39: control evidence registry (IM-A; RLS-T, RLS-TE when entity_id is not null; AUD-FACT);
# revision 0057 (SOP-1). ``run_ref_type`` is text with the T-PLT-39 check (mirror:
# ``erev_api.controls.evidence.RunRefType``); ``book_code`` is the E-02 type of revision 0004.
book_code_type: Final = _enum(BookCode, "book_code")
control_execution: Final = Table(
    "control_execution",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("control_id", Text(), nullable=False),
    Column("run_ref_type", Text(), nullable=False),
    Column("run_ref_id", Uuid(), nullable=False),
    Column("entity_id", Uuid(), nullable=True),
    Column("book_code", book_code_type, nullable=True),
    Column("period_id", Uuid(), nullable=True),
    Column("population_count", BigInteger(), nullable=False),
    Column("exception_count", BigInteger(), nullable=False),
    Column("result", control_result, nullable=False),
    Column("detail", JSONB(), nullable=False, server_default=text("'{}'")),
    Column("exceptions_file_id", Uuid(), nullable=True),
    Column("engine_release_id", Uuid(), nullable=False),
    _timestamp("executed_at", nullable=False, now_default=True),
)

# Created by revision 0021 (PLF-24): E-97.
webhook_delivery_status: Final = _enum(WebhookDeliveryStatus, "webhook_delivery_status")

# T-PLT-35: outbound webhook subscription (IM-M, RLS-T). DB-15 ``tg_webhook_endpoint__sandbox``
# (revision 0091, SNP-4): in a sandbox tenant a row cannot become active.
webhook_endpoint: Final = Table(
    "webhook_endpoint",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("url", Text(), nullable=False),
    Column("description", Text(), nullable=True),
    Column("event_kinds", ARRAY(Text()), nullable=False),
    Column("secret_ciphertext", LargeBinary(), nullable=False),
    Column("secret_key_id", Text(), nullable=False),
    Column("is_active", Boolean(), nullable=False, server_default=text("true")),
    *_sc_c_sc_m(),
)

# T-PLT-36: delivery log with retries for 24 hours (IM-S, RLS-T); DB-03 trigger.
webhook_delivery: Final = Table(
    "webhook_delivery",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("webhook_endpoint_id", Uuid(), nullable=False),
    Column("event_kind", Text(), nullable=False),
    Column("payload", JSONB(), nullable=False),
    Column("payload_sha256", CHAR(64), nullable=False),
    Column("status", webhook_delivery_status, nullable=False, server_default=text("'PENDING'")),
    Column("attempt_count", Integer(), nullable=False, server_default=text("0")),
    _timestamp("next_attempt_at"),
    _timestamp("abandon_at", nullable=False),
    Column("last_response_status", Integer(), nullable=True),
    Column("last_error", Text(), nullable=True),
    _timestamp("succeeded_at"),
    *_sc_c(),
)

# Created by revision 0022 (PLF-25): E-103.
api_client_status: Final = _enum(ApiClientStatus, "api_client_status")

# T-PLT-15: OAuth2 client-credentials integration principal (IM-M, RLS-T); DB-12 triggers.
api_client: Final = Table(
    "api_client",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("name", Text(), nullable=False),
    Column("client_id", Text(), nullable=False),
    Column("secret_hash", Text(), nullable=False),
    _timestamp("secret_rotated_at"),
    Column("scopes", ARRAY(Text()), nullable=False),
    Column("is_all_entities", Boolean(), nullable=False, server_default=text("true")),
    Column("entity_ids", ARRAY(Uuid()), nullable=False, server_default=text("'{}'::uuid[]")),
    Column("status", api_client_status, nullable=False, server_default=text("'ACTIVE'")),
    _timestamp("expires_at", nullable=False),
    Column("rate_limit_per_minute", Integer(), nullable=False, server_default=text("600")),
    _timestamp("last_used_at"),
    *_sc_c_sc_m(),
)

# T-PLT-16: issued access tokens, deleted 7 days after expiry (IM-E, RLS-T).
api_token: Final = Table(
    "api_token",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("api_client_id", Uuid(), nullable=False),
    Column("token_sha256", CHAR(64), nullable=False),
    Column("scopes", ARRAY(Text()), nullable=False),
    _timestamp("issued_at", nullable=False, now_default=True),
    _timestamp("expires_at", nullable=False),
    _timestamp("revoked_at"),
)

# T-PLT-33: tenant-approved, time-boxed operator access (IM-S, RLS-T); DB-03 trigger. Created by
# revision 0023 (PLF-26).
support_grant: Final = Table(
    "support_grant",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("operator_user_id", Uuid(), nullable=False),
    Column("scope", Text(), nullable=False, server_default=text("'READ_ONLY'")),
    Column("reason", Text(), nullable=False),
    Column("ticket_ref", Text(), nullable=True),
    Column("status", grant_status, nullable=False, server_default=text("'REQUESTED'")),
    _timestamp("valid_from", nullable=False),
    _timestamp("valid_to", nullable=False),
    Column("approval_request_id", Uuid(), nullable=True),
    _timestamp("approved_at"),
    _timestamp("revoked_at"),
    Column("revoked_by", Uuid(), nullable=True),
    Column("revoked_by_kind", principal_kind, nullable=True),
    *_sc_c(),
)

# T-PLT-21: time-boxed delegation of approval permissions (IM-S, RLS-T); DB-03 trigger.
approval_delegation: Final = Table(
    "approval_delegation",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("delegator_membership_id", Uuid(), nullable=False),
    Column("delegate_membership_id", Uuid(), nullable=False),
    Column("permissions", ARRAY(Text()), nullable=False),
    _timestamp("valid_from", nullable=False),
    _timestamp("valid_to", nullable=False),
    Column("reason", Text(), nullable=False),
    _timestamp("revoked_at"),
    Column("revoked_by", Uuid(), nullable=True),
    Column("revoked_by_kind", principal_kind, nullable=True),
    *_sc_c(),
)

# Created by revision 0024 (PLF-28): E-107, E-108.
access_review_status: Final = _enum(AccessReviewStatus, "access_review_status")
access_review_decision: Final = _enum(AccessReviewDecision, "access_review_decision")

# T-PLT-40: access review campaign (IM-S, RLS-T); DB-03 trigger.
access_review_campaign: Final = Table(
    "access_review_campaign",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("name", Text(), nullable=False),
    Column("status", access_review_status, nullable=False, server_default=text("'DRAFT'")),
    _timestamp("as_of", nullable=False),
    Column("reviewer_membership_ids", ARRAY(Uuid()), nullable=False),
    Column("snapshot_file_id", Uuid(), nullable=True),
    _timestamp("started_at"),
    _timestamp("completed_at"),
    *_sc_c_sc_m(),
)

# T-PLT-41: one membership under review (IM-S, RLS-T); DB-03 and DB-10 triggers.
access_review_item: Final = Table(
    "access_review_item",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("access_review_campaign_id", Uuid(), nullable=False),
    Column("membership_id", Uuid(), nullable=False),
    Column("user_email_snapshot", Text(), nullable=False),
    Column("roles_snapshot", JSONB(), nullable=False),
    _timestamp("last_login_at"),
    Column("decision", access_review_decision, nullable=False, server_default=text("'PENDING'")),
    Column("reviewer_id", Uuid(), nullable=True),
    _timestamp("decided_at"),
    Column("comment", Text(), nullable=True),
    _timestamp("revocation_completed_at"),
    *_sc_c_sc_m(),
)
