"""05 PRV-01 data-classification catalogue: every column of docs/04-DATA_MODEL.md with its class.

``CLASSIFICATION`` maps ``(table, column)`` to a :class:`ColumnClassification` carrying the data
class (C0 public, C1 internal, C2 confidential financial, C3 personal data), the processing purpose,
the retention rule, the erasure handling, the recipients beyond the hosted database and the basis of
the class. The catalogue is a literal, hand-maintained registry: ``TABLES`` lists every column of
every 04 table explicitly, so ``backend/tests/unit/test_privacy_classification.py`` fails when a
column of ``erev_api.db.tables`` has no entry, when an entry names a column that does not exist, and
when a ``PENDING`` entry's column lands in the code (the reconciliation gate for lanes P2, C1b and
P5; BUILD_SPEC SOP-5).

Classes are taken from the specification where it names them (05 PRV-01 C3 list, PRV-03 memos,
PRV-04 audit payloads, PRV-05 tokenised containers, §6.1 asset table; ``Basis.SPEC``). Every other
class is a lane P8 proposal awaiting the accountant's and the privacy owner's confirmation
(``Basis.PROPOSED``); the rule that produced it is recorded on every entry (``R01`` to ``R08``).
Nothing here decides erasure or legal-hold policy: the erasure values restate 05 PRV-07 and PRV-09,
and ``Erasure.NO_PATH`` marks a C3 column for which 1.0 names no erasure (returned as a question in
``docs/reviews/loop/prod/P8-privacy-catalogue.md``).

Retention values restate 04 §1.5 IM-E (``EXPIRES_AT_SWEEP``), 05 PRV-09 (``AUDIT_RETENTION_YEARS``,
``platform.audit_retention_years``, default 7; no delete path in 1.0), 05 PRV-06 and PRV-07 b
(``FILE_RETENTION``) and 05 PRV-11 deletion or return at contract end (``TENANT_LIFETIME``).
Recipients name the sub-processors and controller-directed transfers of 05 PRV-10 and PRV-11 beyond
the hosted database (Google Cloud, which processes every column of a hosted deployment and is not
repeated per column): the SMTP relay, the AI provider when a tenant enables AI (D-46) and the
tenant's own systems (ERP connectors, webhook endpoints).

The column lists are space-separated strings parsed at import into the frozen registry; a duplicate
column or table raises at import.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

__all__ = [
    "CLASSIFICATION",
    "PERSONAL_COLUMN_PATTERN",
    "TABLES",
    "TABLE_CLASSIFICATION",
    "Basis",
    "ColumnClassification",
    "ColumnNote",
    "CoverageReport",
    "DataClass",
    "Erasure",
    "PendingSource",
    "Recipient",
    "Retention",
    "Rule",
    "Status",
    "TableClassification",
    "check_coverage",
    "columns_of",
    "data_class",
]


class DataClass(StrEnum):
    """05 PRV-01 classes."""

    C0 = "C0"  # public
    C1 = "C1"  # internal
    C2 = "C2"  # confidential financial
    C3 = "C3"  # personal data


class Basis(StrEnum):
    """Where a class comes from."""

    SPEC = "SPEC"  # named in 05 PRV-01, PRV-03, PRV-04, PRV-05 or §6.1
    PROPOSED = "PROPOSED"  # lane P8 proposal; accountant / privacy owner confirmation pending


class Status(StrEnum):
    """Whether the column exists in ``erev_api.db.tables`` at this revision."""

    ACTIVE = "ACTIVE"
    PENDING = "PENDING"  # ruled in 04 or on a lane branch; no code column yet


class PendingSource(StrEnum):
    DOC_04 = "DOC_04"  # ruled in docs/04-DATA_MODEL.md on main
    LANE_BRANCH = "LANE_BRANCH"  # ruled on a lane branch; the 04 revision is not on main yet


class Retention(StrEnum):
    TENANT_LIFETIME = "TENANT_LIFETIME"  # deletion or return at contract end (05 PRV-11)
    AUDIT_RETENTION_YEARS = "AUDIT_RETENTION_YEARS"  # platform.audit_retention_years (05 PRV-09)
    EXPIRES_AT_SWEEP = "EXPIRES_AT_SWEEP"  # 04 §1.5 IM-E: deleted by the retention job
    FILE_RETENTION = "FILE_RETENTION"  # legal_hold / retention_until, then file.shred (05 PRV-07 b)


class Erasure(StrEnum):
    NONE = "NONE"  # not personal data; no erasure handling
    ANONYMISE = "ANONYMISE"  # rewritten or cleared by user.anonymise (05 PRV-07 a)
    PSEUDONYMISED = "PSEUDONYMISED"  # stored only as a hash; never the clear value
    TOKENISED = "TOKENISED"  # C3 paths replaced by PRV-05 tokens before the write
    AUDIT_HMAC = "AUDIT_HMAC"  # C3 values appear only in the PRV-04 {hmac, length} form
    SECURITY_LOG = "SECURITY_LOG"  # retained with the security log; PRV-09 truncation later
    RETENTION_SWEEP = "RETENTION_SWEEP"  # erased with the IM-E row by the retention job
    CLEARED_ON_USE = "CLEARED_ON_USE"  # single-use token hash set to NULL when consumed
    NO_PATH = "NO_PATH"  # C3 with no erasure named in 1.0; returned as a question


class Recipient(StrEnum):
    """Recipients beyond the hosted database (05 PRV-10, PRV-11)."""

    SMTP_RELAY = "SMTP_RELAY"  # the configured relay (invitations, notifications, resets)
    AI_PROVIDER = "AI_PROVIDER"  # Anthropic, only for tenants that enable AI (D-46; PRV-08)
    TENANT_SYSTEMS = "TENANT_SYSTEMS"  # the tenant's ERP or webhook endpoints (controller-directed)


@dataclass(frozen=True, slots=True)
class Rule:
    """A classification rule; the class and its basis follow from the rule."""

    id: str
    data_class: DataClass
    basis: Basis
    text: str


@dataclass(frozen=True, slots=True)
class ColumnNote:
    """Column-level departures from the table defaults."""

    purpose: str | None = None
    erasure: Erasure | None = None
    recipients: frozenset[Recipient] | None = None
    pending: PendingSource | None = None
    note: str = ""


_NO_NOTES: Final[Mapping[str, ColumnNote]] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class TableClassification:
    """One 04 table: purpose, retention and every column grouped by the rule that classifies it."""

    name: str
    ref: str  # 04 table id, for example "T-PLT-02"
    purpose: str
    retention: Retention
    retention_basis: Basis
    groups: Mapping[Rule, tuple[str, ...]]
    status: Status = Status.ACTIVE
    recipients: frozenset[Recipient] = frozenset()
    notes: Mapping[str, ColumnNote] = _NO_NOTES

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(column for columns in self.groups.values() for column in columns)


@dataclass(frozen=True, slots=True)
class ColumnClassification:
    """The catalogue entry of one column."""

    table: str
    ref: str
    column: str
    data_class: DataClass
    basis: Basis
    rule: str
    purpose: str
    retention: Retention
    retention_basis: Basis
    erasure: Erasure
    recipients: frozenset[Recipient]
    status: Status
    pending: PendingSource | None
    note: str


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Result of :func:`check_coverage`; every tuple empty means the catalogue matches the code."""

    missing: tuple[tuple[str, str], ...]  # code columns without an ACTIVE entry
    unknown: tuple[tuple[str, str], ...]  # ACTIVE entries naming no code column
    landed: tuple[tuple[str, str], ...]  # PENDING entries whose column now exists in the code

    @property
    def ok(self) -> bool:
        return not (self.missing or self.unknown or self.landed)


# 05 PRV-01: a column whose name matches this pattern must have a classification.
PERSONAL_COLUMN_PATTERN: Final = re.compile(r"(email|name|phone|address|ip_|user_agent|payee)")

# Rules. SPEC_* restate the specification; R01 to R08 are lane P8 proposals.
SPEC_C3: Final = Rule("SPEC-C3", DataClass.C3, Basis.SPEC, "Named C3 in 05 PRV-01.")
SPEC_C2_AUDIT: Final = Rule(
    "SPEC-C2-AUDIT",
    DataClass.C2,
    Basis.SPEC,
    "Audit and security event content is C2 (05 §6.1); C3 values inside appear only in the PRV-04 "
    "HMAC form.",
)
SPEC_C2_MEMO: Final = Rule(
    "SPEC-C2-MEMO",
    DataClass.C2,
    Basis.SPEC,
    "memo_1..3 are C2 free text; the user guide instructs tenants not to put personal data in "
    "memos (05 PRV-03).",
)
SPEC_C2_PAYLOAD: Final = Rule(
    "SPEC-C2-PAYLOAD",
    DataClass.C2,
    Basis.SPEC,
    "Contract events, source records, import rows and files are C2 and may contain C3, tokenised "
    "at ingestion (05 §6.1, PRV-05).",
)
SPEC_C2_LEDGER: Final = Rule(
    "SPEC-C2-LEDGER",
    DataClass.C2,
    Basis.SPEC,
    "Subledger, journals, contract versions and calc traces are C2 confidential financial "
    "(05 §6.1).",
)
SPEC_C2_CONFIG: Final = Rule(
    "SPEC-C2-CONFIG", DataClass.C2, Basis.SPEC, "Configuration and policies are C2 (05 §6.1)."
)
R01: Final = Rule(
    "R01",
    DataClass.C1,
    Basis.PROPOSED,
    "Structural column: identifiers, foreign keys, record-keeping and as-of timestamps, statuses "
    "and outcomes, hashes and HMACs, versions, counters and sequence numbers. Internal, never "
    "public; person references are pseudonymous UUIDs (05 PRV-03).",
)
R02: Final = Rule(
    "R02",
    DataClass.C2,
    Basis.PROPOSED,
    "Business content of an accounting, reference, import, integration, forecast, AI or migration "
    "table: amounts, rates, quantities, commercial terms and dates, names, codes, free text and "
    "JSON payloads.",
)
R03: Final = Rule(
    "R03",
    DataClass.C1,
    Basis.PROPOSED,
    "Internal platform configuration and operational state: roles, permissions, jobs, "
    "notification metadata, chain heads, catalogues.",
)
R04: Final = Rule(
    "R04",
    DataClass.C2,
    Basis.PROPOSED,
    "Platform column carrying tenant business content: approval summaries and comments, "
    "notification text, saved views, job parameters and results, cached responses, webhook "
    "payloads, control detail.",
)
R05: Final = Rule(
    "R05",
    DataClass.C3,
    Basis.PROPOSED,
    "Credential bound to a natural person: password hash, MFA seed, recovery-code hashes, "
    "session, invitation and reset token hashes (05 §6.1 'users, sessions, MFA seeds ... C3 and "
    "credentials'); redacted in audit payloads by erev_api.audit.redact.REDACT.",
)
R06: Final = Rule(
    "R06",
    DataClass.C2,
    Basis.PROPOSED,
    "Tenant-bound secret material or secret reference: API client secret hash and tokens, webhook "
    "signing secret, identity-provider and integration secret references (05 ARC-11, SAR-07); "
    "redacted in audit payloads.",
)
R07: Final = Rule(
    "R07",
    DataClass.C3,
    Basis.PROPOSED,
    "Personal data of a PRV-01 kind (an IP address) on a table added to 04 after PRV-01 was "
    "written; not in the PRV-01 list.",
)
R08: Final = Rule(
    "R08",
    DataClass.C0,
    Basis.PROPOSED,
    "Public reference facts: ISO 4217 currencies and the seeded permission catalogue published "
    "through the API schema.",
)
RULES: Final[tuple[Rule, ...]] = (
    SPEC_C3,
    SPEC_C2_AUDIT,
    SPEC_C2_MEMO,
    SPEC_C2_PAYLOAD,
    SPEC_C2_LEDGER,
    SPEC_C2_CONFIG,
    R01,
    R02,
    R03,
    R04,
    R05,
    R06,
    R07,
    R08,
)


def _cols(text: str) -> tuple[str, ...]:
    return tuple(text.split())


def _table(
    name: str,
    ref: str,
    purpose: str,
    retention: Retention,
    groups: Mapping[Rule, tuple[str, ...]],
    *,
    retention_basis: Basis = Basis.PROPOSED,
    status: Status = Status.ACTIVE,
    recipients: frozenset[Recipient] = frozenset(),
    notes: Mapping[str, ColumnNote] | None = None,
) -> TableClassification:
    return TableClassification(
        name=name,
        ref=ref,
        purpose=purpose,
        retention=retention,
        retention_basis=retention_basis,
        groups=MappingProxyType(dict(groups)),
        status=status,
        recipients=recipients,
        notes=MappingProxyType(dict(notes)) if notes else _NO_NOTES,
    )


# Every 04 table in document order (§4 to §13), every column listed once under its rule.
TABLES: Final[tuple[TableClassification, ...]] = (
    # ---- PLT tables (04 T-PLT-nn)
    _table(
        "tenant",
        "T-PLT-01",
        "A customer organisation's isolated data space: production or sandbox (REQ-PLT-003).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "id kind status source_tenant_id source_known_at is_demo audit_hmac_key_id "
                "setup_completed_at ai_disabled_at ai_disabled_by ai_disabled_by_kind "
                "created_at created_by created_by_kind updated_at updated_by updated_by_kind "
                "row_version"
            ),
            R03: _cols("code reporting_currency industry_cluster default_locale"),
            R04: _cols("display_name"),
        },
        notes={
            "display_name": ColumnNote(
                note="The tenant's workspace name (its company name).",
            ),
        },
    ),
    _table(
        "app_user",
        "T-PLT-02",
        "Global human identity.",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "id password_changed_at status failed_login_count locked_until "
                "identity_provider_id is_operator last_login_at created_at created_by "
                "created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            R03: _cols("preferences"),
            R05: _cols("password_hash"),
            SPEC_C3: _cols("email display_name external_id identity_provider_subject"),
        },
        notes={
            "email": ColumnNote(
                purpose="Login identifier; invitation, notification and password-reset delivery.",
                erasure=Erasure.ANONYMISE,
                recipients=frozenset({Recipient.SMTP_RELAY}),
                note="05 PRV-07 a rewrites it to `erased+<user id>@invalid.erev`.",
            ),
            "display_name": ColumnNote(
                erasure=Erasure.ANONYMISE,
                note="05 PRV-07 a rewrites it to `Erased user <first 8 hex of SHA-256(user id)>`.",
            ),
            "password_hash": ColumnNote(
                erasure=Erasure.ANONYMISE,
                note="argon2id PHC string; cleared by 05 PRV-07 a.",
            ),
            "external_id": ColumnNote(
                erasure=Erasure.ANONYMISE,
                note="SCIM identifier reserved for REQ-PLT-007; cleared by 05 PRV-07 a.",
            ),
            "identity_provider_subject": ColumnNote(
                purpose="Binds the identity to one subject of its OIDC provider (REQ-PLT-006).",
                erasure=Erasure.ANONYMISE,
                note="The provider's `sub` of the first sign-in; cleared by 05 PRV-07 a.",
            ),
        },
    ),
    _table(
        "identity_provider",
        "T-PLT-03",
        "Login methods: password, OIDC (tested against a mock IdP), SAML reserved.",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "id kind client_id is_enabled created_at created_by created_by_kind updated_at "
                "updated_by updated_by_kind row_version"
            ),
            R03: _cols("code display_name issuer_url config email_domains"),
            R06: _cols("client_secret_ref"),
        },
        notes={
            "client_secret_ref": ColumnNote(
                note="Secret reference only (05 ARC-11).",
            ),
        },
    ),
    _table(
        "user_mfa_factor",
        "T-PLT-04",
        "TOTP factor per user (REQ-PLT-005).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "id user_id factor_kind secret_key_id confirmed_at last_used_step disabled_at "
                "created_at created_by created_by_kind updated_at updated_by updated_by_kind "
                "row_version"
            ),
            R05: _cols("secret_ciphertext"),
        },
        notes={
            "secret_ciphertext": ColumnNote(
                erasure=Erasure.NO_PATH,
                note=(
                    "TOTP seed under SAR-07 envelope encryption; 05 PRV-07 a does not name MFA "
                    "factors (question for the privacy owner)."
                ),
            ),
        },
    ),
    _table(
        "user_recovery_code",
        "T-PLT-05",
        "Ten single-use recovery codes per enrolment batch (REQ-PLT-005).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols("id user_id batch_id used_at created_at"),
            R05: _cols("code_hash"),
        },
        notes={
            "code_hash": ColumnNote(
                erasure=Erasure.NO_PATH,
                note="05 PRV-07 a does not name recovery codes (question for the privacy owner).",
            ),
        },
    ),
    _table(
        "security_event",
        "T-PLT-06",
        (
            "Pre-tenant security log (login, lockout, MFA, platform scope use), hash-chained "
            "globally."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "id chain_seq occurred_at kind outcome user_id session_id tenant_id request_id "
                "prev_hmac hmac hmac_key_id canonical_version"
            ),
            SPEC_C2_AUDIT: _cols("detail"),
            SPEC_C3: _cols("email_sha256 ip_address user_agent"),
        },
        retention_basis=Basis.SPEC,
        notes={
            "email_sha256": ColumnNote(
                erasure=Erasure.PSEUDONYMISED,
                note=(
                    "Pseudonymous (05 PRV-01): SHA-256 of an attempted email that matched no "
                    "user; retained with the security log (05 PRV-09)."
                ),
            ),
            "ip_address": ColumnNote(
                erasure=Erasure.SECURITY_LOG,
                note=(
                    "Retained with the security log under legitimate interest; truncated to "
                    "/24 (IPv4) and /48 (IPv6) after 400 days when retention is built (05 "
                    "PRV-09)."
                ),
            ),
            "user_agent": ColumnNote(
                erasure=Erasure.SECURITY_LOG,
                note="Truncated to 512 characters; retained with the security log (05 PRV-09).",
            ),
            "hmac_key_id": ColumnNote(
                note=(
                    "04 rev 1.42 (SPEC-Q-116 ruling), landed with lane P2 (migration 0061). Key "
                    "id of the row's HMAC (05 KEY-03); no personal data."
                ),
            ),
            "canonical_version": ColumnNote(
                note=(
                    "04 rev 1.42 (SPEC-Q-116 ruling), landed with lane P2 (migration 0061). Form "
                    "of the HMAC preimage; no personal data."
                ),
            ),
        },
    ),
    _table(
        "tenant_membership",
        "T-PLT-07",
        "A user's membership of a tenant.",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id user_id status invited_at invitation_expires_at activated_at "
                "removed_at last_opened_at created_at created_by created_by_kind updated_at "
                "updated_by updated_by_kind row_version"
            ),
            R05: _cols("invitation_token_sha256"),
        },
        notes={
            "invitation_token_sha256": ColumnNote(
                erasure=Erasure.CLEARED_ON_USE,
                note=(
                    "Hash of the invitation token e-mailed to the invited person; set to NULL "
                    "on acceptance (04 T-PLT-07)."
                ),
            ),
        },
    ),
    _table(
        "user_session",
        "T-PLT-08",
        "Server-side session for browser users (REQ-PLT-004).",
        Retention.EXPIRES_AT_SWEEP,
        {
            R01: _cols(
                "id user_id auth_method mfa_verified_at active_tenant_id created_at "
                "last_seen_at idle_expires_at absolute_expires_at ended_at "
                "operator_support_grant_id expires_at"
            ),
            R03: _cols("end_reason"),
            R05: _cols("token_sha256 csrf_token_sha256"),
            SPEC_C3: _cols("ip_address user_agent"),
        },
        retention_basis=Basis.SPEC,
        notes={
            "token_sha256": ColumnNote(
                erasure=Erasure.RETENTION_SWEEP,
            ),
            "csrf_token_sha256": ColumnNote(
                erasure=Erasure.RETENTION_SWEEP,
            ),
            "ip_address": ColumnNote(
                erasure=Erasure.RETENTION_SWEEP,
                note=(
                    "Rows are deleted 30 days after `ended_at` (04 T-PLT-08 IM-E); 05 PRV-07 a "
                    "ends every session of an anonymised user."
                ),
            ),
            "user_agent": ColumnNote(
                erasure=Erasure.RETENTION_SWEEP,
                note="As `ip_address`.",
            ),
        },
    ),
    _table(
        "role",
        "T-PLT-09",
        "Named permission set.",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id is_active content_sha256 created_at created_by created_by_kind "
                "updated_at updated_by updated_by_kind row_version"
            ),
            R03: _cols("code name description is_system"),
        },
    ),
    _table(
        "role_assignment",
        "T-PLT-10",
        "Grants a role to a membership, for all entities or a named subset (REQ-PLT-012).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id membership_id role_id entity_ids valid_from valid_to "
                "approval_request_id sod_exception_id revoked_at revoked_by revoked_by_kind "
                "created_at created_by created_by_kind"
            ),
            R03: _cols("is_all_entities"),
        },
    ),
    _table(
        "permission",
        "T-PLT-11",
        (
            "Global permission catalogue, seeded by migration from "
            "`erev_api.auth.permissions.CATALOGUE`."
        ),
        Retention.TENANT_LIFETIME,
        {
            R08: _cols("code area description is_approval is_access_admin requires_mfa"),
        },
    ),
    _table(
        "role_permission",
        "T-PLT-12",
        "Permission membership of a role.",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols("tenant_id role_id created_at created_by created_by_kind"),
            R03: _cols("permission_code"),
        },
    ),
    _table(
        "sod_rule",
        "T-PLT-13",
        (
            "Conflicting permission pairs SoD-1 to SoD-7 (research 07 §5.8), seeded per "
            "tenant, versioned under the configuration lifecycle (REQ-POL-003)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id created_at created_by created_by_kind updated_at updated_by "
                "updated_by_kind row_version version_no status content_sha256 "
                "approval_request_id published_at published_by supersedes_version_id"
            ),
            R03: _cols(
                "code name function_a_permissions function_b_permissions effective_from "
                "effective_to"
            ),
            R04: _cols("rationale"),
        },
    ),
    _table(
        "sod_exception",
        "T-PLT-14",
        (
            "Approved exception allowing a conflicting role combination, with a compensating "
            "control and an expiry (REQ-PLT-010)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id membership_id status valid_from valid_to approval_request_id "
                "approved_at revoked_at revoked_by revoked_by_kind created_at created_by "
                "created_by_kind"
            ),
            R03: _cols("sod_rule_code"),
            R04: _cols("compensating_control"),
        },
    ),
    _table(
        "api_client",
        "T-PLT-15",
        "OAuth2 client-credentials integration principal (REQ-PLT-033).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id client_id secret_rotated_at entity_ids status expires_at "
                "last_used_at created_at created_by created_by_kind updated_at updated_by "
                "updated_by_kind row_version"
            ),
            R03: _cols("name scopes is_all_entities rate_limit_per_minute"),
            R06: _cols("secret_hash"),
        },
    ),
    _table(
        "api_token",
        "T-PLT-16",
        "Issued access tokens (60 minutes, REQ-PLT-033).",
        Retention.EXPIRES_AT_SWEEP,
        {
            R01: _cols("tenant_id id api_client_id issued_at expires_at revoked_at"),
            R03: _cols("scopes"),
            R06: _cols("token_sha256"),
        },
        retention_basis=Basis.SPEC,
    ),
    _table(
        "approval_request",
        "T-PLT-17",
        "One approval routing instance for one subject (REQ-PLT-013 to -017).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id request_no subject_type subject_id subject_row_version "
                "subject_content_sha256 entity_id entity_ids is_all_entities "
                "routing_rule_set_version_id routing_rule_id "
                "status current_step_no preparer_id preparer_kind submitted_at decided_at "
                "voided_at impact_preview_file_id impact_preview_sha256 created_at created_by "
                "created_by_kind"
            ),
            R03: _cols("amount_currency flags reason_code"),
            R04: _cols("summary amount_functional void_reason comment"),
        },
    ),
    _table(
        "approval_step",
        "T-PLT-18",
        "A level in a multi-level approval.",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id approval_request_id step_no required_role_id status activated_at "
                "completed_at"
            ),
            R03: _cols("name required_permission min_approvers"),
        },
    ),
    _table(
        "audit_event",
        "T-PLT-19",
        "Tenant audit log, append-only and HMAC-chained per tenant (D-43, REQ-PLT-018).",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id occurred_at id chain_seq actor_id actor_kind actor_roles auth_method "
                "mfa_verified on_behalf_of_id api_client_id support_grant_id request_id action "
                "object_type object_id object_version approval_request_id outcome prev_hmac "
                "hmac hmac_key_id"
            ),
            R03: _cols("reason_code"),
            SPEC_C2_AUDIT: _cols("before after diff comment detail"),
            SPEC_C3: _cols("source_ip"),
        },
        retention_basis=Basis.SPEC,
        notes={
            "source_ip": ColumnNote(
                erasure=Erasure.SECURITY_LOG,
                note=(
                    "Retained with the audit log for `platform.audit_retention_years`; the "
                    "PRV-09 /24 and /48 truncation is PROPOSED for audit events too (question "
                    "for the privacy owner)."
                ),
            ),
            "before": ColumnNote(
                erasure=Erasure.AUDIT_HMAC,
                note=(
                    'C3 values stored as `{"hmac", "length"}` with KEY-05 (05 PRV-04); '
                    "credential keys as `[REDACTED]`."
                ),
            ),
            "after": ColumnNote(
                erasure=Erasure.AUDIT_HMAC,
                note=(
                    'C3 values stored as `{"hmac", "length"}` with KEY-05 (05 PRV-04); '
                    "credential keys as `[REDACTED]`."
                ),
            ),
            "diff": ColumnNote(
                erasure=Erasure.AUDIT_HMAC,
                note=(
                    'C3 values stored as `{"hmac", "length"}` with KEY-05 (05 PRV-04); '
                    "credential keys as `[REDACTED]`."
                ),
            ),
            "detail": ColumnNote(
                erasure=Erasure.AUDIT_HMAC,
                note=(
                    'C3 values stored as `{"hmac", "length"}` with KEY-05 (05 PRV-04); '
                    "credential keys as `[REDACTED]`."
                ),
            ),
        },
    ),
    _table(
        "approval_decision",
        "T-PLT-20",
        "An individual approve, reject or rule-based auto-approve decision.",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id approval_request_id approval_step_id approver_id approver_kind "
                "delegation_id on_behalf_of_id auto_rule_set_version_id auto_rule_id "
                "subject_content_sha256 impact_preview_sha256 mfa_verified_at decided_at"
            ),
            R03: _cols("decision reason_code"),
            R04: _cols("comment"),
        },
    ),
    _table(
        "approval_delegation",
        "T-PLT-21",
        "Time-boxed delegation of approval permissions (REQ-PLT-013).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id delegator_membership_id delegate_membership_id valid_from "
                "valid_to revoked_at revoked_by revoked_by_kind created_at created_by "
                "created_by_kind"
            ),
            R03: _cols("permissions"),
            R04: _cols("reason"),
        },
    ),
    _table(
        "audit_chain_head",
        "T-PLT-22",
        "Per-tenant chain pointer; its row lock serialises audit appends (DB-09).",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols("tenant_id last_chain_seq last_hmac last_occurred_at updated_at"),
        },
    ),
    _table(
        "audit_chain_verification",
        "T-PLT-23",
        "Result of a chain verification run and its digest (REQ-PLT-020).",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id trigger from_chain_seq to_chain_seq events_checked result "
                "first_failure_seq digest_last_hmac digest_file_id job_id started_at "
                "finished_at created_at created_by created_by_kind"
            ),
            R03: _cols("failure_detail"),
        },
    ),
    _table(
        "notification",
        "T-PLT-24",
        "In-app notification (REQ-PLT-021).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id recipient_membership_id kind subject_type subject_id read_at "
                "email_sent_at created_at created_by created_by_kind"
            ),
            R03: _cols("link_path"),
            R04: _cols("title body"),
        },
        notes={
            "title": ColumnNote(
                recipients=frozenset({Recipient.SMTP_RELAY}),
                note=(
                    "E-mailed through the configured relay when the recipient's preference is "
                    "on (04 T-PLT-25)."
                ),
            ),
            "body": ColumnNote(
                recipients=frozenset({Recipient.SMTP_RELAY}),
                note="As `title`.",
            ),
        },
    ),
    _table(
        "notification_preference",
        "T-PLT-25",
        "Per-user subscription preferences (REQ-PLT-021).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id membership_id kind updated_at updated_by updated_by_kind row_version"
            ),
            R03: _cols("in_app email"),
        },
        notes={
            "email": ColumnNote(
                note="Boolean e-mail subscription flag, not an address (04 T-PLT-25).",
            ),
        },
    ),
    _table(
        "numbering_series",
        "T-PLT-26",
        (
            "Human-facing sequential numbers; gapless series allocate inside the business "
            "transaction under a row lock."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols("tenant_id id next_value updated_at updated_by updated_by_kind row_version"),
            R03: _cols("series_code scope_key prefix padding is_gapless"),
        },
    ),
    _table(
        "job",
        "T-PLT-27",
        ("API-visible job resource for long operations (REQ-PLT-029); wraps a Procrastinate task."),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id kind state queue priority progress_done progress_total "
                "procrastinate_job_id parent_job_id started_at finished_at cancel_requested_at "
                "subject_type subject_id created_at created_by created_by_kind updated_at "
                "updated_by updated_by_kind row_version"
            ),
            R04: _cols("params result problem"),
        },
    ),
    _table(
        "idempotency_record",
        "T-PLT-28",
        "Stored first response per `Idempotency-Key` (REQ-PLT-026).",
        Retention.EXPIRES_AT_SWEEP,
        {
            R01: _cols(
                "tenant_id principal_id idempotency_key principal_kind method path "
                "request_sha256 state response_status response_file_id created_at completed_at "
                "expires_at"
            ),
            R04: _cols("response_headers response_body"),
        },
        retention_basis=Basis.SPEC,
        notes={
            "response_body": ColumnNote(
                note="Cached API response; holds whatever the route returned (04 T-PLT-28).",
            ),
        },
    ),
    _table(
        "file_object",
        "T-PLT-29",
        (
            "Immutable, content-addressed file store metadata (imports, attachments, outputs, "
            "evidence)."
        ),
        Retention.FILE_RETENTION,
        {
            R01: _cols(
                "tenant_id id sha256 size_bytes media_type storage_backend storage_key "
                "shredded_at shredded_by shredded_by_kind shred_completed_at created_at "
                "created_by created_by_kind"
            ),
            R03: _cols("purpose retention_until legal_hold shred_reason"),
            SPEC_C3: _cols("original_filename"),
        },
        retention_basis=Basis.SPEC,
        notes={
            "original_filename": ColumnNote(
                erasure=Erasure.NO_PATH,
                note=(
                    "Kept on the immutable row; `file.shred` destroys the bytes, not the "
                    "filename (05 PRV-06, PRV-07 b; question for the privacy owner)."
                ),
            ),
        },
    ),
    _table(
        "file_attachment",
        "T-PLT-30",
        "Links a file to a subject record (REQ-PLT-035).",
        Retention.FILE_RETENTION,
        {
            R01: _cols(
                "tenant_id id file_object_id subject_type subject_id voided_at voided_by "
                "voided_by_kind created_at created_by created_by_kind"
            ),
            R03: _cols("description void_reason"),
        },
    ),
    _table(
        "registry_parameter",
        "T-PLT-31",
        (
            "Global catalogue of tenant settings and accounting policy parameters with "
            "defaults and legacy-parity values."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols("pol_id category"),
            R03: _cols(
                "code value_schema default_asc606 default_ifrs15 is_forced_asc606 "
                "is_forced_ifrs15 legacy_parity_value allowed_levels pin approval_code "
                "description source_ref section"
            ),
        },
    ),
    _table(
        "registry_version",
        "T-PLT-32",
        (
            "Versioned tenant values for one registry category at one scope: the tenant "
            "accounting policy set (REQ-POL-004), expedient flags, elections and platform "
            "settings."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id category scope entity_id impact_simulation_file_id created_at "
                "created_by created_by_kind updated_at updated_by updated_by_kind row_version "
                "version_no status content_sha256 approval_request_id published_at published_by "
                "supersedes_version_id"
            ),
            R03: _cols("book_code preset_code effective_from effective_to"),
            SPEC_C2_CONFIG: _cols("values test_evidence"),
        },
    ),
    _table(
        "support_grant",
        "T-PLT-33",
        "Tenant-approved, time-boxed operator access (REQ-PLT-036; research 07 AC-05).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id operator_user_id scope status valid_from valid_to "
                "approval_request_id approved_at revoked_at revoked_by revoked_by_kind "
                "created_at created_by created_by_kind"
            ),
            R04: _cols("reason ticket_ref"),
        },
    ),
    _table(
        "tenant_snapshot",
        "T-PLT-34",
        (
            "A stored copy of a tenant as of `known_at`, used to create sandbox tenants and "
            'for "restore into sandbox" (REQ-PLT-023 to -025; D-01).'
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id known_at status target_tenant_id manifest_file_id manifest_sha256 "
                "job_id started_at finished_at created_at created_by created_by_kind"
            ),
            R03: _cols("purpose row_counts"),
        },
        # landed with SNP-1 slice I-1 (lane F-SNP, T-PLT-34): ACTIVE at merge prep
    ),
    _table(
        "webhook_endpoint",
        "T-PLT-35",
        "Outbound webhook subscription (REQ-PLT-034).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id secret_key_id is_active created_at created_by created_by_kind "
                "updated_at updated_by updated_by_kind row_version"
            ),
            R03: _cols("event_kinds"),
            R04: _cols("url description"),
            R06: _cols("secret_ciphertext"),
        },
        notes={
            "secret_ciphertext": ColumnNote(
                note="Signing secret under SAR-07 envelope encryption.",
            ),
        },
    ),
    _table(
        "webhook_delivery",
        "T-PLT-36",
        "Delivery log with retries for 24 hours (REQ-PLT-034).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id webhook_endpoint_id event_kind payload_sha256 status "
                "attempt_count next_attempt_at abandon_at last_response_status succeeded_at "
                "created_at created_by created_by_kind"
            ),
            R04: _cols("payload last_error"),
        },
        notes={
            "payload": ColumnNote(
                recipients=frozenset({Recipient.TENANT_SYSTEMS}),
                note=(
                    "Delivered to the tenant-configured endpoint (controller-directed "
                    "transfer, not a sub-processor)."
                ),
            ),
        },
    ),
    _table(
        "saved_view",
        "T-PLT-37",
        (
            "Saved grid filters, columns and favourites per user (UX; research 01b §4 "
            "favourites, M-PM-07)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id membership_id screen_code is_shared is_favourite created_at "
                "created_by created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            R04: _cols("name config"),
        },
    ),
    _table(
        "engine_release",
        "T-PLT-38",
        "Release manifest stamped on every computation and run (research 07 CH-03, F-15).",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols("id engine_version build_sha schema_revision deployed_at"),
            R03: _cols("release_notes control_impact_tags gate_results validation_level"),
        },
        notes={
            "validation_level": ColumnNote(
                note=(
                    "04 T-PLT-38 rev 1.29 (D-96 (3); lane P5 integration slice 1; revision "
                    "0055): the author's REL-01 validation level declaration "
                    "(PATCH / MINOR / MAJOR), persisted at REL-03 stamping; a release literal, "
                    "no personal data. Reconciled from the rev 1.13 DOC_04 pending entry."
                ),
            ),
        },
    ),
    _table(
        "control_execution",
        "T-PLT-39",
        (
            "Control evidence registry: one row per automated control execution (research 07 "
            "EVD-02). Reconciled from the DOC_04 pending entry when lane P4's SOP-1 table landed "
            "in the code (revision 0057 on 0056; the fifteen columns are unchanged)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id control_id run_ref_type run_ref_id entity_id period_id "
                "population_count exception_count result exceptions_file_id engine_release_id "
                "executed_at"
            ),
            R03: _cols("book_code"),
            R04: _cols("detail"),
        },
    ),
    _table(
        "access_review_campaign",
        "T-PLT-40",
        (
            "User access review campaign snapshotting users, roles, entity scopes, last login, "
            "grant date and grantor (REQ-CTL-006; research 07 AC-04)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id status as_of reviewer_membership_ids snapshot_file_id started_at "
                "completed_at created_at created_by created_by_kind updated_at updated_by "
                "updated_by_kind row_version"
            ),
            R03: _cols("name"),
        },
    ),
    _table(
        "access_review_item",
        "T-PLT-41",
        (
            "One membership under review with the reviewer's decision and revocation tracking "
            "(REQ-CTL-006)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id access_review_campaign_id membership_id last_login_at reviewer_id "
                "decided_at revocation_completed_at created_at created_by created_by_kind "
                "updated_at updated_by updated_by_kind row_version"
            ),
            R03: _cols("roles_snapshot decision"),
            R04: _cols("comment"),
            SPEC_C3: _cols("user_email_snapshot"),
        },
        notes={
            "user_email_snapshot": ColumnNote(
                erasure=Erasure.NO_PATH,
                note=(
                    "Point-in-time evidence of an access review (REQ-CTL-006); 05 PRV-07 names "
                    "no erasure for it (question for the privacy owner)."
                ),
            ),
        },
    ),
    _table(
        "password_reset_token",
        "T-PLT-42",
        "Single-use password reset token (rev 1.2; SCREENS_B OQ-B-28; B3-D10).",
        Retention.EXPIRES_AT_SWEEP,
        {
            R01: _cols(
                "id user_id created_at token_expires_at used_at superseded_at request_id expires_at"
            ),
            R05: _cols("token_sha256"),
            R07: _cols("ip_address"),
        },
        retention_basis=Basis.SPEC,
        notes={
            "token_sha256": ColumnNote(
                erasure=Erasure.RETENTION_SWEEP,
            ),
            "ip_address": ColumnNote(
                erasure=Erasure.RETENTION_SWEEP,
                note=(
                    "Requester IP of a password reset (04 T-PLT-42, rev 1.2); the row is "
                    "deleted 30 days after `token_expires_at`. PROPOSED C3: same kind as the "
                    "PRV-01 IP columns."
                ),
            ),
        },
    ),
    _table(
        "release_validation",
        "T-PLT-43",
        (
            "Per-tenant validation of a candidate engine release before its processes may "
            "persist (05 REL-06, RCP-28a; D-96 (4))."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id engine_release_id source_engine_release_id effective_level status "
                "accepted_attempt_id enabled_at created_at created_by created_by_kind "
                "updated_at updated_by updated_by_kind row_version"
            ),
        },
        status=Status.PENDING,
    ),
    _table(
        "release_validation_attempt",
        "T-PLT-44",
        (
            "The frozen snapshot of one validation attempt: population, required entity set, "
            "dataset and approval (D-96 (4); R4/R7)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id release_validation_id attempt_no seed required_entity_ids status "
                "dataset_file_id dataset_sha256 report_run_id approval_request_id created_at "
                "created_by created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            R03: _cols("population"),
        },
        status=Status.PENDING,
    ),
    _table(
        "release_validation_group",
        "T-PLT-45",
        (
            "One row per (attempt, combination group): frozen selection, the group job's "
            "orchestration state and the pointer to the accepted verification (D-96 (4); B)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id release_validation_attempt_id combination_group_id "
                "source_computation_id selection rank_sha256 orchestration_state "
                "accepted_verification_id child_job_id created_at created_by created_by_kind "
                "updated_at updated_by updated_by_kind row_version"
            ),
            R03: _cols("strata"),
        },
        status=Status.PENDING,
    ),
    _table(
        "release_group_processing",
        "T-PLT-46",
        (
            "Append-only event log of each group's upgrade processing after a MINOR or MAJOR "
            "release is enabled, kept per portion (group × entity × enabled book): pending "
            "until an explicit outcome per portion..."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id release_validation_id release_validation_attempt_id "
                "combination_group_id entity_id seq upgrade_state contract_computation_id "
                "subledger_posting_ids created_at created_by created_by_kind"
            ),
            R03: _cols("book_code unresolved_origin_period_keys reason"),
        },
        status=Status.PENDING,
    ),
    # ---- REF tables (04 T-REF-nn)
    _table(
        "registry_parameter_correction",
        "T-PLT-47",
        (
            "Append-only metadata corrections of seeded T-PLT-31 registry_parameter rows "
            "(D-98 candidate 125): complete snapshots read through the effective relation."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols("correction_no applied_by_revision created_at created_by created_by_kind"),
            R03: _cols("code value_schema description source_ref section"),
        },
    ),
    _table(
        "audit_event_contract",
        "T-PLT-48",
        (
            "The contracts an audit event names, one row a contract: the index of the contract "
            "key of T-PLT-19, derived from the event (04 rev 1.154)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols("tenant_id contract_id chain_seq occurred_at audit_event_id"),
        },
    ),
    _table(
        "file_upload",
        "T-PLT-49",
        (
            "The uploads of a stored file: one row per file and uploader with the uploader's "
            "own file name and time (04 rev 1.189)."
        ),
        Retention.FILE_RETENTION,
        {
            R01: _cols("tenant_id file_object_id uploaded_by uploaded_by_kind uploaded_at"),
            SPEC_C3: _cols("original_filename"),
        },
        retention_basis=Basis.SPEC,
        notes={
            "original_filename": ColumnNote(
                erasure=Erasure.NO_PATH,
                note=(
                    "Kept on the immutable row, as `file_object.original_filename` is (05 "
                    "PRV-06, PRV-07 b; question for the privacy owner)."
                ),
            ),
        },
    ),
    _table(
        "legal_entity",
        "T-REF-01",
        (
            "Legal entity with functional currency, time zone and calendar (REQ-REF-001; "
            "research 06 §10.1)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id calendar_id parent_entity_id is_active created_at created_by "
                "created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            SPEC_C2_CONFIG: _cols("code name functional_currency time_zone country_code"),
            R02: _cols("tax_id"),
        },
    ),
    _table(
        "book",
        "T-REF-02",
        "Accounting books enabled for the tenant (D-24).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id is_enabled created_at created_by created_by_kind updated_at "
                "updated_by updated_by_kind row_version"
            ),
            SPEC_C2_CONFIG: _cols("code name is_primary posting_target"),
        },
    ),
    _table(
        "entity_book",
        "T-REF-03",
        "Which books an entity keeps, from which first period.",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id entity_id first_period_id is_enabled created_at created_by "
                "created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            SPEC_C2_CONFIG: _cols("book_code"),
        },
    ),
    _table(
        "fiscal_calendar",
        "T-REF-04",
        "Fiscal calendar definition (REQ-REF-002, -003).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id created_at created_by created_by_kind updated_at updated_by "
                "updated_by_kind row_version"
            ),
            SPEC_C2_CONFIG: _cols(
                "code name pattern fiscal_year_start_month week_end_day year_end_anchor"
            ),
        },
    ),
    _table(
        "period",
        "T-REF-05",
        "Accounting period of a calendar; generated by the command `calendar.generate_year`.",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id calendar_id period_no quarter_no created_at created_by "
                "created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            SPEC_C2_CONFIG: _cols("fiscal_year period_key name start_date end_date"),
        },
    ),
    _table(
        "period_state",
        "T-REF-06",
        "Current state of a period per entity and book (D-19; research 06 §6.1).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id entity_id period_id state current_lock_id state_changed_at "
                "updated_at updated_by updated_by_kind row_version"
            ),
            SPEC_C2_CONFIG: _cols("book_code period_end_date"),
        },
    ),
    _table(
        "period_state_transition",
        "T-REF-07",
        "Append-only history of period state changes with reasons and approvals.",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id period_state_id entity_id period_id from_state to_state "
                "approval_request_id period_lock_id close_run_id created_txid created_at "
                "created_by created_by_kind"
            ),
            SPEC_C2_CONFIG: _cols("book_code reason_code comment"),
        },
    ),
    _table(
        "currency",
        "T-REF-08",
        "ISO 4217 currency table with minor units 0-4 (D-11; REQ-REF-004; research 06 §8.1).",
        Retention.TENANT_LIFETIME,
        {
            R08: _cols("code numeric_code name minor_unit is_active"),
        },
    ),
    _table(
        "tenant_currency",
        "T-REF-09",
        "Currencies enabled for the tenant (REQ-REF-004).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id is_enabled created_at created_by created_by_kind updated_at "
                "updated_by updated_by_kind row_version"
            ),
            SPEC_C2_CONFIG: _cols("currency_code"),
        },
    ),
    _table(
        "fx_rate_set",
        "T-REF-10",
        "Identity of a rate series by rate type and source (research 06 §9.5).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id created_at created_by created_by_kind updated_at updated_by "
                "updated_by_kind row_version"
            ),
            SPEC_C2_CONFIG: _cols("code name rate_type source"),
        },
    ),
    _table(
        "fx_rate_set_version",
        "T-REF-11",
        "Immutable published batch of rates covering a date range (REQ-REF-005).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id fx_rate_set_id rate_count import_upload_id created_at created_by "
                "created_by_kind updated_at updated_by updated_by_kind row_version version_no "
                "status content_sha256 approval_request_id published_at published_by "
                "supersedes_version_id"
            ),
            SPEC_C2_CONFIG: _cols("coverage_from coverage_to effective_from effective_to"),
        },
    ),
    _table(
        "fx_rate",
        "T-REF-12",
        "One rate: 1 unit of `base_currency` = `rate` units of `quote_currency`.",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols("tenant_id id fx_rate_set_version_id period_id"),
            SPEC_C2_CONFIG: _cols(
                "rate_type base_currency quote_currency effective_date rate is_derived"
            ),
        },
    ),
    _table(
        "gl_account",
        "T-REF-13",
        "Chart of accounts (REQ-REF-007).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id entity_ids source_system is_active created_at created_by "
                "created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            SPEC_C2_CONFIG: _cols("code name account_type normal_balance required_dimensions"),
        },
    ),
    _table(
        "account_mapping_version",
        "T-REF-14",
        "Versioned, effective-dated account-role mapping (D-14; REQ-REF-008).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id impact_simulation_file_id created_at created_by created_by_kind "
                "updated_at updated_by updated_by_kind row_version version_no status "
                "content_sha256 approval_request_id published_at published_by "
                "supersedes_version_id"
            ),
            SPEC_C2_CONFIG: _cols("name notes effective_from effective_to"),
        },
    ),
    _table(
        "account_mapping_rule",
        "T-REF-15",
        (
            "Resolves an account role (× entity × optional book, product or revenue category) "
            "to a GL account."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id account_mapping_version_id entity_id product_id gl_account_id "
                "priority"
            ),
            SPEC_C2_CONFIG: _cols(
                "account_role clearing_purpose book_code revenue_category default_dimensions "
                "specificity"
            ),
        },
    ),
    _table(
        "dimension_definition",
        "T-REF-16",
        (
            "Built-in (department, class, location, product, customer) and up to five "
            "tenant-defined dimensions (REQ-REF-009)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id position is_active created_at created_by created_by_kind "
                "updated_at updated_by updated_by_kind row_version"
            ),
            SPEC_C2_CONFIG: _cols("code name is_builtin"),
        },
    ),
    _table(
        "dimension_value",
        "T-REF-17",
        "Allowed values of a dimension.",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id dimension_definition_id parent_value_id is_active created_at "
                "created_by created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            R02: _cols("code name"),
        },
    ),
    _table(
        "related_party_group",
        "T-REF-18",
        "Group of related customers for combination detection and disclosure (REQ-REF-011).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id created_at created_by created_by_kind updated_at updated_by "
                "updated_by_kind row_version"
            ),
            R02: _cols("code name description"),
        },
    ),
    _table(
        "customer",
        "T-REF-19",
        "Customer master (REQ-REF-010).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id related_party_group_id parent_customer_id source_system is_active "
                "created_at created_by created_by_kind updated_at updated_by updated_by_kind "
                "row_version"
            ),
            R02: _cols("code name credit_grade segment country_code external_id"),
        },
        notes={
            "name": ColumnNote(
                note=(
                    "Customer legal name; may name a natural person for a sole-trader customer "
                    "(question for the privacy owner: C2 or C3). The customer master holds no "
                    "contact details (04 T-REF-19)."
                ),
            ),
        },
    ),
    _table(
        "product",
        "T-REF-20",
        "Product or SKU master (REQ-REF-012).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id sku_number default_pob_template_id is_active created_at "
                "created_by created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            R02: _cols(
                "code name product_family revenue_category disaggregation principal_agent "
                "distinctness_default unit_of_measure is_bundle assurance_cost_per_unit "
                "is_franchisor_preopening_service policy_values"
            ),
        },
    ),
    _table(
        "product_bundle_component",
        "T-REF-21",
        "Bundle explosion map (REQ-REF-013).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id bundle_product_id component_product_id created_at created_by "
                "created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            R02: _cols("quantity_per_bundle split_basis split_ratio sequence valid_from valid_to"),
        },
    ),
    _table(
        "pob_template",
        "T-REF-22",
        "Identity of a performance obligation template (REQ-POL-001).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id created_at created_by created_by_kind updated_at updated_by "
                "updated_by_kind row_version"
            ),
            SPEC_C2_CONFIG: _cols("code name description"),
        },
    ),
    _table(
        "pob_template_version",
        "T-REF-23",
        "Versioned outputs of a POB template (REQ-POL-001).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id pob_template_id obligation_kind created_at created_by "
                "created_by_kind updated_at updated_by updated_by_kind row_version version_no "
                "status content_sha256 approval_request_id published_at published_by "
                "supersedes_version_id"
            ),
            SPEC_C2_CONFIG: _cols(
                "distinctness series_increment_unit satisfaction_pattern over_time_criterion "
                "recognition_method ratable_convention start_date_rule end_date_rule "
                "term_months principal_agent warranty_type licence_nature "
                "sfc_assessment_required revenue_category disaggregation account_role_overrides "
                "stratification_label is_excluded_from_netting_attribution policy_values "
                "effective_from effective_to"
            ),
        },
    ),
    _table(
        "rule_set",
        "T-REF-24",
        (
            "Identity of a decision table (research 06 D13): POB assignment, SSP assignment, "
            "approval routing, auto-approval, combination detection, holds, data-quality "
            "monitors."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id kind created_at created_by created_by_kind updated_at updated_by "
                "updated_by_kind row_version"
            ),
            SPEC_C2_CONFIG: _cols("code name description"),
        },
    ),
    _table(
        "rule_set_version",
        "T-REF-25",
        "Immutable published version of a decision table.",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id rule_set_id kind impact_simulation_file_id created_at created_by "
                "created_by_kind updated_at updated_by updated_by_kind row_version version_no "
                "status content_sha256 approval_request_id published_at published_by "
                "supersedes_version_id"
            ),
            SPEC_C2_CONFIG: _cols("lint_result effective_from effective_to"),
        },
    ),
    _table(
        "rule",
        "T-REF-26",
        "One row of a decision table.",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols("tenant_id id rule_set_version_id priority"),
            SPEC_C2_CONFIG: _cols("rule_key conditions outputs specificity description"),
        },
    ),
    _table(
        "rule_test_case",
        "T-REF-27",
        (
            "Example cases that must pass before a configuration version becomes TESTED "
            "(REQ-POL-003)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id subject_type subject_id last_run_at created_at created_by "
                "created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            SPEC_C2_CONFIG: _cols("name input expected_output last_result"),
        },
    ),
    _table(
        "ssp_book",
        "T-REF-28",
        "SSP book identity and scope (REQ-SSP-001).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id entity_id created_at created_by created_by_kind updated_at "
                "updated_by updated_by_kind row_version"
            ),
            SPEC_C2_CONFIG: _cols("code name description currency channel segment resolution_mode"),
        },
    ),
    _table(
        "ssp_book_version",
        "T-REF-29",
        "Immutable approved set of SSP values (REQ-SSP-001, -007, -008, -013).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id ssp_book_id entry_count ssp_calculator_run_id import_upload_id "
                "created_at created_by created_by_kind updated_at updated_by updated_by_kind "
                "row_version version_no status content_sha256 approval_request_id published_at "
                "published_by supersedes_version_id"
            ),
            SPEC_C2_CONFIG: _cols(
                "legacy_version_label effective_from_date effective_to_date methodology_label "
                "is_methodology_change diff_summary effective_from effective_to"
            ),
        },
    ),
    _table(
        "ssp_entry",
        "T-REF-30",
        (
            "SSP value for a product, stratification and dimension key within a version "
            "(REQ-SSP-002, -003)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id ssp_book_version_id product_id revenue_gl_account_id created_at "
                "created_by created_by_kind"
            ),
            SPEC_C2_CONFIG: _cols(
                "stratification region channel segment deal_size_band term_band currency method "
                "value_basis quantity_unit unit_list_price midpoint_discount_ratio range_ratio "
                "cost_basis margin_ratio observable_point distinctness"
            ),
        },
    ),
    _table(
        "ssp_range",
        "T-REF-31",
        (
            "Per-unit point or low/mid/high values of an entry, optionally banded by quantity, "
            "deal size or term (REQ-SSP-003, -004)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols("tenant_id id ssp_entry_id created_at created_by created_by_kind"),
            SPEC_C2_CONFIG: _cols(
                "band_dimension band_from band_to point_value low_value mid_value high_value"
            ),
        },
    ),
    _table(
        "ssp_calculator_run",
        "T-REF-32",
        (
            "Historical SSP calculator run producing statistics and a Draft SSP version "
            "(REQ-SSP-009)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id status observation_count result_file_id draft_ssp_book_version_id "
                "job_id started_at finished_at entity_ids created_at created_by created_by_kind"
            ),
            SPEC_C2_CONFIG: _cols("name parameters"),
        },
    ),
    _table(
        "ssp_calculator_result",
        "T-REF-33",
        "Statistics per product and key for a calculator run (REQ-SSP-009).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id ssp_calculator_run_id product_id observation_count excluded_count "
                "inside_count"
            ),
            SPEC_C2_CONFIG: _cols(
                "stratification dimension_key currency median_unit_price mean_unit_price "
                "p10_unit_price p25_unit_price p75_unit_price p90_unit_price band_ratio "
                "compliance_ratio proposed_low proposed_mid proposed_high histogram"
            ),
        },
    ),
    _table(
        "ssp_calculator_exclusion",
        "T-REF-34",
        "Observations excluded as outliers, with a reason (REQ-SSP-009).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id ssp_calculator_run_id source_ref_id created_at created_by "
                "created_by_kind"
            ),
            SPEC_C2_CONFIG: _cols("source_ref_type reason"),
        },
    ),
    # ---- SRC tables (04 T-SRC-nn)
    _table(
        "source_record",
        "T-SRC-01",
        (
            "Immutable raw payload received from any channel, keyed by source identity and "
            "version (research 06 D14; REQ-INT-001, REQ-DAT-011)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id source_system object_type external_id external_version "
                "version_order payload_sha256 received_at import_upload_id import_row_id "
                "sync_run_id request_id idempotency_key created_at created_by created_by_kind"
            ),
            SPEC_C2_PAYLOAD: _cols("payload"),
        },
        notes={
            "payload": ColumnNote(
                erasure=Erasure.TOKENISED,
                note=(
                    'C3 paths declared by the adapter mapping are replaced by `{"$pii": '
                    '"hmac:<hex>"}` before the write (05 PRV-05, ADP-04).'
                ),
            ),
        },
    ),
    _table(
        "source_order",
        "T-SRC-02",
        (
            "Normalized order or contract header (CRM, CPQ, Stripe subscription, legacy "
            "Contract Setup file grouped by `Contract Unique Name`)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id source_record_id source_system external_order_id external_version "
                "order_number customer_external_id customer_id po_number "
                "parent_order_external_id created_at created_by created_by_kind"
            ),
            SPEC_C2_PAYLOAD: _cols(
                "order_date legal_entity_code transaction_currency amendment_reason "
                "grouping_values payment_terms signature_date document_ref termination_rights "
                "custom_attributes"
            ),
        },
    ),
    _table(
        "source_order_line",
        "T-SRC-03",
        "Normalized order line; one legacy Contract Setup row.",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id source_order_id line_external_id line_no product_id "
                "bundle_parent_line_external_id created_at created_by created_by_kind"
            ),
            SPEC_C2_PAYLOAD: _cols(
                "product_code stratification quantity unit_list_price unit_price total_price "
                "start_date end_date selling_entity_code performing_entity_code "
                "ssp_version_label account_codes effective_date is_usage_line scope_flag "
                "out_of_scope_amount custom_attributes"
            ),
            SPEC_C2_MEMO: _cols("memo_1 memo_2 memo_3"),
        },
    ),
    _table(
        "source_invoice",
        "T-SRC-04",
        "Normalized invoice or credit memo header (REQ-BIL-001).",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id source_record_id source_system external_invoice_id "
                "external_version invoice_number document_kind customer_external_id customer_id "
                "credited_invoice_external_id created_at created_by created_by_kind"
            ),
            SPEC_C2_PAYLOAD: _cols(
                "issue_date due_date is_cancellable legal_entity_code currency total_amount "
                "tax_amount custom_attributes"
            ),
        },
    ),
    _table(
        "source_invoice_line",
        "T-SRC-05",
        "Invoice or credit memo line with its contract and obligation reference.",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id source_invoice_id line_external_id order_line_external_id "
                "created_at created_by created_by_kind"
            ),
            SPEC_C2_PAYLOAD: _cols(
                "contract_ref obligation_ref product_code quantity amount tax_lines "
                "service_period_start service_period_end custom_attributes"
            ),
        },
    ),
    _table(
        "source_usage",
        "T-SRC-06",
        "Normalized usage record or royalty statement line (REQ-REC-010, -011).",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id source_record_id source_system external_usage_id external_version "
                "order_line_external_id created_at created_by created_by_kind"
            ),
            SPEC_C2_PAYLOAD: _cols(
                "usage_date usage_period_start usage_period_end contract_ref obligation_ref "
                "product_code metric quantity rated_amount currency is_royalty_statement "
                "custom_attributes"
            ),
        },
    ),
    _table(
        "source_payment",
        "T-SRC-07",
        (
            "Normalized cash receipt for FX layering and deposit accounting (REQ-BIL-012, "
            "REQ-CON-003)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id source_record_id source_system external_payment_id "
                "external_version customer_external_id applied_invoice_external_ids created_at "
                "created_by created_by_kind"
            ),
            SPEC_C2_PAYLOAD: _cols(
                "receipt_date legal_entity_code currency amount contract_ref custom_attributes"
            ),
        },
    ),
    _table(
        "source_match",
        "T-SRC-08",
        (
            "Result of matching a source record to internal objects (grouping, explicit "
            "reference, legacy key, manual)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id source_record_id target_id created_at created_by created_by_kind"
            ),
            SPEC_C2_PAYLOAD: _cols("target_type match_method match_detail"),
        },
    ),
    # ---- CON tables (04 T-CON-nn)
    _table(
        "contract",
        "T-CON-01",
        "Commercial contract identity and header projection (REQ-CON-001, -002, -005).",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id contract_no external_id customer_id contracting_entity_id status "
                "combination_group_id head_stream_version latest_computation_id activated_at "
                "completed_at terminated_at voided_at renewal_of_contract_id portfolio_id "
                "source_system created_at created_by created_by_kind updated_at updated_by "
                "updated_by_kind row_version"
            ),
            R02: _cols(
                "transaction_currency inception_date signature_date document_ref payment_terms "
                "termination_party termination_has_penalty termination_notice_days "
                "has_commercial_substance region channel contract_type custom_attributes "
                "activation_checklist scope_605_35 acceptance_clause side_letter"
            ),
            SPEC_C2_MEMO: _cols("memo_1 memo_2 memo_3"),
        },
    ),
    _table(
        "contract_source_link",
        "T-CON-02",
        "Links a contract to the source records that established or changed it.",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id contract_id source_record_id contract_event_id created_at "
                "created_by created_by_kind"
            ),
            R02: _cols("link_role"),
        },
    ),
    _table(
        "combination_group",
        "T-CON-03",
        (
            "Accounting unit for Steps 2-5, netting and loss provisions (REQ-CON-009, -019; "
            "research 04 §1.3)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id status judgement_record_id approval_request_id "
                "head_computation_id dirty_since dirty_trigger period_ends_open created_at "
                "created_by created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            R02: _cols("code is_singleton transaction_currency criterion rationale inception_date"),
        },
    ),
    _table(
        "combination_group_member",
        "T-CON-04",
        "Membership of contracts in groups over record time.",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id combination_group_id contract_id valid_from_known_at "
                "valid_to_known_at join_event_id leave_event_id created_at created_by "
                "created_by_kind"
            ),
        },
    ),
    _table(
        "contract_event",
        "T-CON-05",
        (
            "The bitemporal, append-only event stream of a contract (D-10, D-19; research 06 "
            "§3.3-3.4)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id contract_id contracting_entity_id stream_version schema_version "
                "recorded_at record_seq obligation_ids payload_sha256 idempotency_key "
                "supersedes_event_id approval_request_id modification_id estimate_version_id "
                "manual_adjustment_id import_upload_id source_record_id sync_run_id request_id "
                "created_at created_by created_by_kind"
            ),
            SPEC_C2_PAYLOAD: _cols("event_type effective_date origin is_manual payload"),
        },
    ),
    _table(
        "modification",
        "T-CON-06",
        (
            "Modification object with questionnaire, proposed and chosen treatments, impact "
            "preview and approval (REQ-MOD-001, -002, -013, -014)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id modification_no contract_id contracting_entity_id kind status "
                "judgement_record_id impact_preview_file_id impact_preview_sha256 "
                "content_sha256 approval_request_id applied_event_id regroup_id "
                "import_upload_id created_at created_by created_by_kind updated_at updated_by "
                "updated_by_kind row_version"
            ),
            R02: _cols(
                "effective_date template_mode reference questionnaire lines price_change_amount "
                "noncash_consideration consideration_payable scope_605_35 currency "
                "proposed_treatments chosen_treatments treatment_summary ssp_basis rationale "
                "classification"
            ),
        },
        # Reconciled from the DOC_04 pending entry when the CTR-17 revision 0068 landed the table
        # (D-98 140; 04 rev 1.70 adds ``regroup_id``, an identity token: R01).
    ),
    _table(
        "contract_computation",
        "T-CON-07",
        (
            "One engine invocation over a combination group: pinned inputs, input hash, engine "
            "release, outcome (D-10; research 06 §5; REQ-REF-015)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id combination_group_id known_at trigger engine_release_id "
                "engine_version input_sha256 status duration_ms job_id close_run_id created_at "
                "created_by created_by_kind cutoff_at"
            ),
            SPEC_C2_LEDGER: _cols("stream_heads pinned_refs problem"),
        },
    ),
    _table(
        "contract_version",
        "T-CON-08",
        (
            "Immutable computed version of a combination group for one book (REQ-CON-014, "
            "REQ-MOD-022)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id combination_group_id contract_computation_id version_no "
                "previous_version_id known_at cause_event_ids output_sha256 calc_trace_id "
                "status_in_book modification_boundary_no created_at created_by created_by_kind"
            ),
            SPEC_C2_LEDGER: _cols(
                "book_code transaction_currency status_reason_in_book transaction_price "
                "fixed_consideration vc_constrained_amount vc_excluded_amount "
                "expected_returns_amount consideration_payable_amount "
                "financing_adjustment_amount noncash_consideration_amount "
                "sales_tax_excluded_amount out_of_scope_amount total_ssp revenue_cum billed_cum "
                "net_position rpo_amount scheduled_amount awaiting_trigger_amount "
                "pinned_policies"
            ),
        },
    ),
    _table(
        "contract_version_balance",
        "T-CON-09",
        (
            "Labelled balances per member contract and legal entity at a version (D-12, D-15, "
            "D-23; REQ-BIL-003, -004, -007, -010; REQ-ENT-002)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id contract_version_id contract_id entity_id created_at created_by "
                "created_by_kind"
            ),
            SPEC_C2_LEDGER: _cols(
                "book_code txn_currency functional_currency revenue_cum_txn billed_cum_txn "
                "net_position_txn contract_liability_txn contract_liability_functional "
                "contract_liability_current_txn contract_asset_txn contract_asset_functional "
                "contract_asset_current_txn unbilled_receivable_txn "
                "unbilled_receivable_functional accounts_receivable_txn "
                "accounts_receivable_functional refund_liability_txn "
                "refund_liability_functional return_asset_txn return_asset_functional "
                "deposit_liability_txn deposit_liability_functional "
                "customer_incentive_asset_txn consideration_payable_txn cost_asset_carrying_txn "
                "loss_provision_txn consideration_payable_functional "
                "customer_incentive_asset_functional"
            ),
        },
    ),
    _table(
        "obligation",
        "T-CON-10",
        "Continuous identity of a performance obligation across versions (REQ-POB-004).",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id contract_id product_id created_by_event_id parent_obligation_id "
                "regrouped_from_obligation_id created_at created_by created_by_kind"
            ),
            R02: _cols("obligation_key legacy_record_key line_sequence"),
        },
    ),
    _table(
        "obligation_version",
        "T-CON-11",
        (
            "Full state of one obligation at one contract version and book: terms, SSP "
            "snapshot, allocation, cumulative, activity, remaining, position and lineage."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id contract_version_id obligation_id contract_id "
                "combination_group_id version_no previous_obligation_version_id product_id "
                "sku_number obligation_kind pob_template_version_id contracting_entity_id "
                "performing_entity_id ssp_book_version_id ssp_entry_id ssp_range_id "
                "ssp_override_approval_request_id satisfaction_status modification_boundary_no "
                "last_modification_id created_at created_by created_by_kind"
            ),
            SPEC_C2_LEDGER: _cols(
                "book_code obligation_key legacy_record_key product_code stratification "
                "distinctness series_increment_unit scope_flag satisfaction_pattern "
                "over_time_criterion recognition_method ratable_convention principal_agent "
                "licence_nature warranty_type start_date end_date txn_currency "
                "account_overrides legacy_deferred_revenue_account legacy_unbilled_ar_account "
                "legacy_revenue_account original_quantity original_stated_price quantity "
                "stated_price ssp_method ssp_version_label ssp_unit_list_price "
                "ssp_midpoint_discount_ratio ssp_range_ratio original_ssp_mid original_ssp_high "
                "original_ssp_low original_ssp_selected original_ssp_in_range "
                "original_total_contract_price original_total_contract_ssp "
                "original_allocated_amount original_allocated_exact original_unit_ssp "
                "original_unit_revenue_rate allocation_weight allocated_amount allocated_exact "
                "allocation_adjustment unit_ssp remaining_unit_revenue_rate "
                "delivered_quantity_cum returned_quantity_cum progress_ratio revenue_cum "
                "billed_cum ssp_delivered_cum catch_up_cum catch_up_modification_cum "
                "catch_up_tp_change_cum catch_up_estimate_cum pre_standard_revenue_cum "
                "delivered_quantity revenue_amount billed_amount ssp_delivered catch_up_amount "
                "pre_standard_revenue_amount remaining_quantity remaining_ssp "
                "remaining_allocation remaining_billing scheduled_amount "
                "awaiting_trigger_amount position_obligation position_contract_entity "
                "netting_reclass_amount netting_reclass_role satisfied_date hold_types "
                "gross_amount_memo effective_date previous_effective_date trace_nodes"
            ),
            SPEC_C2_MEMO: _cols("memo_1 memo_2 memo_3"),
        },
    ),
    _table(
        "estimate",
        "T-CON-12",
        (
            "Identity of an estimated element: VC element, return rate, breakage, EAC, "
            "exercise likelihood and the other E-09 kinds (D-20; REQ-TP-002, -004, -017)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id contract_id portfolio_id obligation_id estimate_kind "
                "target_obligation_ids created_at created_by created_by_kind"
            ),
            R02: _cols(
                "element_code vc_element_type direction method allocation_target "
                "allocation_criteria_evidence"
            ),
        },
    ),
    _table(
        "estimate_version",
        "T-CON-13",
        (
            "Immutable approved estimate with preparer, approver, rationale and evidence; a "
            "reassessment is a new version (D-20; REQ-TP-004, -005)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id estimate_id version_no status judgement_record_id content_sha256 "
                "approval_request_id applied_event_ids supersedes_version_id modification_id "
                "created_at created_by created_by_kind updated_at updated_by updated_by_kind "
                "row_version"
            ),
            SPEC_C2_LEDGER: _cols(
                "effective_date scenarios parameters unconstrained_amount "
                "most_conservative_amount constrained_amount rate expected_total_amount "
                "expected_quantity amortization_months currency constraint_checklist rationale"
            ),
        },
    ),
    _table(
        "material_right",
        "T-CON-14",
        "Option terms of a material-right obligation (D-21; REQ-POB-006, -007).",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id obligation_id contract_id likelihood_estimate_id created_at "
                "created_by created_by_kind"
            ),
            R02: _cols(
                "option_type incremental_discount_ratio is_discount_available_without_contract "
                "expected_purchase_amount currency ssp_method expiry_date "
                "is_legacy_quantity_ssp_dollars"
            ),
        },
        status=Status.PENDING,
    ),
    _table(
        "contract_cost_asset",
        "T-CON-15",
        (
            "Identity and terms of a capitalised cost to obtain or fulfil a contract "
            "(REQ-CST-001 to -003)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id contract_id entity_id cost_kind capitalized_by_event_id "
                "related_obligation_ids created_at created_by created_by_kind"
            ),
            R02: _cols(
                "plan_code capitalization_date amount_capitalized currency amortization_pattern "
                "amortization_start_date amortization_months has_clawback"
            ),
            SPEC_C3: _cols("payee"),
        },
        status=Status.PENDING,
        notes={
            "payee": ColumnNote(
                erasure=Erasure.NO_PATH,
                note=(
                    "Identifier of a cost payee (05 PRV-01 'identifier'); no erasure path in "
                    "1.0 (question for the privacy owner)."
                ),
            ),
        },
    ),
    _table(
        "cost_asset_version",
        "T-CON-16",
        (
            "Engine-computed state of a cost asset at a contract version and book (REQ-CST-003 "
            "to -006)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id contract_version_id contract_cost_asset_id "
                "renewal_estimate_version_id created_at created_by created_by_kind"
            ),
            SPEC_C2_LEDGER: _cols(
                "book_code capitalized_cum amortized_cum impaired_cum impairment_reversed_cum "
                "clawback_cum carrying_amount remaining_months"
            ),
        },
        status=Status.PENDING,
    ),
    _table(
        "loss_provision_version",
        "T-CON-17",
        "Loss provision test result at a contract version (REQ-LOS-001 to -003).",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id contract_version_id obligation_id eac_estimate_version_id "
                "created_at created_by created_by_kind"
            ),
            SPEC_C2_LEDGER: _cols(
                "book_code unit measurement_basis currency expected_consideration "
                "expected_total_costs costs_to_date revenue_to_date expected_margin "
                "provision_balance provision_movement"
            ),
        },
        status=Status.PENDING,
    ),
    _table(
        "fx_layer_movement",
        "T-CON-18",
        (
            "Contract liability layers at historical rates, remeasured contract asset layers "
            "and, from rev 1.2, the monetary liability layers of D-25b, as computed by a "
            "version (D-25, D-25a, D-25b; REQ-FX-002 t..."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id contract_version_id contract_id entity_id movement_kind "
                "fx_rate_id source_event_id trace_node_id created_at created_by created_by_kind"
            ),
            SPEC_C2_LEDGER: _cols(
                "book_code layer_key balance_role effective_date txn_currency amount_txn "
                "functional_currency amount_functional rate"
            ),
        },
    ),
    _table(
        "judgement_record",
        "T-CON-19",
        (
            "Documented accounting judgement with preparer and reviewer (REQ-POL-008; research "
            "04 §14.1, V11)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id judgement_no topic subject_type subject_id contract_id status "
                "reviewer_id reviewed_at approval_request_id content_sha256 supersedes_id "
                "created_at created_by created_by_kind updated_at updated_by updated_by_kind "
                "row_version"
            ),
            R02: _cols(
                "book_code conclusion rationale alternatives_considered codification_refs "
                "questionnaire"
            ),
        },
    ),
    _table(
        "contract_hold",
        "T-CON-20",
        (
            "Current and historical holds (REQ-POL-010, REQ-REC-022, REQ-JE-017); projection "
            "of `HOLD_APPLIED` and `HOLD_RELEASED` events."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id contract_id obligation_id rule_set_version_id rule_id "
                "applied_event_id applied_at released_event_id released_at"
            ),
            R02: _cols("hold_type hold_source reason"),
        },
    ),
    _table(
        "portfolio",
        "T-CON-21",
        "Named set of similar contracts for portfolio-scoped estimates (REQ-TP-017).",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id created_at created_by created_by_kind updated_at updated_by "
                "updated_by_kind row_version"
            ),
            R02: _cols("code name product_group description"),
        },
        status=Status.PENDING,
    ),
    _table(
        "portfolio_member",
        "T-CON-22",
        "Contracts in a portfolio over record time.",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id portfolio_id contract_id valid_from_known_at valid_to_known_at "
                "created_at created_by created_by_kind"
            ),
        },
        status=Status.PENDING,
    ),
    _table(
        "policy_override",
        "T-CON-23",
        (
            "Contract-level (C) or obligation-level (O) policy value with OVR approval "
            "(POLICIES.md §0.5, §0.6)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id contract_id obligation_id judgement_record_id status "
                "content_sha256 approval_request_id approved_at supersedes_id created_at "
                "created_by created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            R02: _cols("level policy_key value rationale"),
        },
    ),
    _table(
        "event_submission",
        "T-CON-24",
        (
            "Holds events that need approval (manual progress, acceptance and cost events; "
            "voids) until an approver other than the preparer approves them; the SYSTEM "
            "principal then appends them on the preparer'..."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id contract_id contracting_entity_id status content_sha256 "
                "approval_request_id applied_event_ids created_at created_by created_by_kind "
                "updated_at updated_by updated_by_kind row_version"
            ),
            SPEC_C2_PAYLOAD: _cols("events comment"),
        },
    ),
    # ---- ENG tables (04 T-ENG-nn)
    _table(
        "schedule",
        "T-ENG-01",
        (
            "Header of a versioned schedule produced by a contract version (research 06 D6; "
            "REQ-REC-020)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id contract_version_id combination_group_id schedule_kind line_count "
                "created_at created_by created_by_kind"
            ),
            SPEC_C2_LEDGER: _cols("book_code currency total_amount"),
        },
    ),
    _table(
        "schedule_line",
        "T-ENG-02",
        (
            "Planned amount per subject, period and line type, cumulative-rounded (D-11; "
            "REQ-REC-019, -020, -021)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id schedule_id contract_version_id contract_id subject_type "
                "subject_id entity_id period_id trace_node_id created_at"
            ),
            SPEC_C2_LEDGER: _cols(
                "period_end_date book_code line_type amount cumulative_amount cumulative_exact "
                "quantity currency is_released_at_close"
            ),
        },
    ),
    _table(
        "calc_trace",
        "T-ENG-03",
        (
            "Calculation DAG behind every computed number of a contract version (D-10, D-45; "
            "research 06 §19; REQ-RPT-018)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id contract_version_id combination_group_id format_version "
                "engine_version trace_sha256 node_count created_at created_by created_by_kind"
            ),
            SPEC_C2_LEDGER: _cols("book_code root_measures trace"),
        },
    ),
    # ---- CON tables (04 T-CON-nn)
    _table(
        "computation_evidence",
        "T-CON-25",
        (
            "The full canonical input and output bytes of a computation, their raw-file "
            "digests, the logical hashes, the per-book ledger cutoff and the predecessor, "
            "captured in the persisting transaction so tha..."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id contract_computation_id input_file_id input_file_sha256 input_sha256 "
                "output_file_id output_file_sha256 output_sha256 codec previous_computation_id "
                "captured backfill_verification_id created_at created_by created_by_kind"
            ),
            SPEC_C2_LEDGER: _cols("book_codes ledger_cutoff"),
        },
        status=Status.PENDING,
    ),
    _table(
        "computation_verification",
        "T-CON-26",
        (
            "One immutable row per verification execution attempt of a stored computation, for "
            "the integrity replay (`REPLAY_VERIFY`) and the candidate validation "
            "(`UPGRADE_VALIDATE`) (05 RCP-28, RCP-28a; D-96..."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id source_computation_id combination_group_id trigger "
                "source_engine_release_id source_engine_version source_codec "
                "process_engine_release_id process_engine_version engine_executed "
                "executed_engine_release_id executed_engine_version input_transform_id "
                "candidate_input_sha256 input_sha256 input_file_sha256_expected "
                "input_file_sha256_observed expected_output_sha256 evidence_output_sha256 "
                "actual_output_sha256 normalised_expected_sha256 normalised_actual_sha256 "
                "normalised_input_match outcome difference_file_id "
                "release_validation_attempt_id job_id task_id attempt duration_ms created_at "
                "created_by created_by_kind"
            ),
            SPEC_C2_LEDGER: _cols("expected_book_codes reason difference_summary problem"),
        },
        status=Status.PENDING,
    ),
    # ---- SL tables (04 T-SL-nn)
    _table(
        "subledger_posting",
        "T-SL-01",
        (
            "Atomic container of detail lines written by one engine commit, close release, FX "
            "remeasurement, netting reclass, manual adjustment or void reversal."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id posting_kind combination_group_id contract_computation_id "
                "close_run_id manual_adjustment_id reverses_posting_id idempotency_key "
                "created_txid created_at created_by created_by_kind"
            ),
            SPEC_C2_LEDGER: _cols("book_code description"),
        },
    ),
    _table(
        "subledger_posting_seal",
        "T-SL-02",
        (
            "Seals a posting: validates balance, quantization and period guard, assigns the "
            "chain sequence and stores control totals and the hash chain (D-16, D-43; research "
            "06 §4.3)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id subledger_posting_id chain_seq line_count prev_seal_sha256 "
                "seal_sha256 sealed_at created_at created_by created_by_kind"
            ),
            SPEC_C2_LEDGER: _cols("book_code control_totals"),
        },
    ),
    _table(
        "ledger_chain_head",
        "T-SL-03",
        "Per tenant and book ledger chain pointer; its row lock serialises seals.",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols("tenant_id last_chain_seq last_seal_sha256 updated_at"),
            SPEC_C2_LEDGER: _cols("book_code"),
        },
    ),
    _table(
        "subledger_line",
        "T-SL-04",
        ("Detail accounting line: the revenue subledger of record (research 06 §4.2; D-16, D-19)."),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id subledger_posting_id entity_id period_id origin_period_id "
                "recorded_at entry_no entry_kind gl_account_id dimension_set_sha256 "
                "fx_rate_set_version_id fx_rate_id contract_id obligation_id "
                "contract_version_id contract_event_id schedule_line_id contract_cost_asset_id "
                "counterparty_entity_id reverses_line_id calc_trace_id trace_node_id created_at "
                "created_by created_by_kind"
            ),
            SPEC_C2_LEDGER: _cols(
                "period_end_date book_code is_post_reopen effective_date account_role "
                "clearing_purpose dimensions txn_currency amount_txn functional_currency "
                "amount_functional dr_cr fx_rate fx_layer_key schedule_period_end_date "
                "reverses_period_end_date reason_code legacy_key description subject_key"
            ),
        },
    ),
    _table(
        "manual_adjustment",
        "T-SL-05",
        (
            "Maker-checker manual adjustment: schedule override, manual release or defer, "
            "account reclass, manual journal tied to a contract (REQ-JE-019, REQ-REC-023; "
            "research 07 MA-01)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id adjustment_no kind status contract_id obligation_id entity_id "
                "period_id impact_preview_file_id content_sha256 approval_request_id "
                "applied_event_id subledger_posting_id created_at created_by created_by_kind "
                "updated_at updated_by updated_by_kind row_version"
            ),
            SPEC_C2_LEDGER: _cols(
                "book_code effective_date payload amount_functional_abs currency reason_code "
                "memo is_deferred_past_lock"
            ),
        },
    ),
    _table(
        "journal_run",
        "T-SL-06",
        (
            "Summarisation of detail lines for an entity, book and period into GL batches "
            "(REQ-JE-001, -004, -007, -008, -010; D-34)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id run_no entity_id period_id state cutoff_known_at from_chain_seq "
                "to_chain_seq delta_from_chain_seq delta_to_chain_seq line_count close_run_id "
                "job_id approval_request_id approved_at exported_at acknowledged_at "
                "cancelled_at created_at created_by created_by_kind updated_at updated_by "
                "updated_by_kind row_version"
            ),
            SPEC_C2_LEDGER: _cols(
                "book_code mode delta_book_code grain functional_currency "
                "total_debit_functional total_credit_functional"
            ),
        },
    ),
    _table(
        "journal_batch",
        "T-SL-07",
        (
            "Balanced GL document for one currency of a run, chunked for ERP limits, with a "
            "deterministic external id (REQ-JE-001, -011 to -016)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id journal_run_id batch_no chunk_no entity_id period_id state "
                "line_count engine_release_id adapter integration_connection_id external_id "
                "export_file_id export_sha256 detail_file_id detail_sha256 outbox_message_id "
                "attempt_count exported_at acknowledged_at created_at created_by "
                "created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            SPEC_C2_LEDGER: _cols(
                "book_code txn_currency functional_currency total_debit_txn total_credit_txn "
                "total_debit_functional total_credit_functional last_error"
            ),
        },
        recipients=frozenset({Recipient.TENANT_SYSTEMS}),
    ),
    _table(
        "journal_entry",
        "T-SL-08",
        "JE header with a gapless number per tenant and entity (REQ-JE-003, -005, -018).",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id journal_batch_id entity_id je_seq je_no entry_kind "
                "source_event_ids manual_adjustment_id reverses_journal_entry_id created_at "
                "created_by created_by_kind"
            ),
            SPEC_C2_LEDGER: _cols("je_type description is_post_close"),
        },
        recipients=frozenset({Recipient.TENANT_SYSTEMS}),
    ),
    _table(
        "journal_line",
        "T-SL-09",
        (
            "Summarised GL line with debit and credit in transaction and functional currency "
            "(REQ-JE-003, -011)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id journal_entry_id journal_batch_id line_no entity_id period_id "
                "gl_account_id dimension_set_sha256 contract_id obligation_id "
                "counterparty_entity_id origin_period_id fx_rate_set_version_ids fx_rate_ids "
                "source_line_count source_grouping_sha256 created_at created_by created_by_kind"
            ),
            SPEC_C2_LEDGER: _cols(
                "book_code account_role gl_account_code dimensions txn_currency debit_txn "
                "credit_txn functional_currency debit_functional credit_functional legacy_key "
                "memo"
            ),
        },
        recipients=frozenset({Recipient.TENANT_SYSTEMS}),
    ),
    _table(
        "posting_ack",
        "T-SL-10",
        "ERP acknowledgement or manual confirmation of a batch (REQ-JE-012, -016).",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id journal_batch_id ack_kind gl_document_id response_sha256 "
                "response_file_id received_at created_at created_by created_by_kind"
            ),
            SPEC_C2_LEDGER: _cols("gl_posted_date message"),
        },
        recipients=frozenset({Recipient.TENANT_SYSTEMS}),
    ),
    _table(
        "posting_attribution",
        "T-SL-11",
        (
            "Attribution metadata for every posting a group produces under an enabled release "
            "while its upgrade processing is pending: which validation, which computation, and "
            "a conservative cause label (D-96 (..."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id subledger_posting_id release_validation_attempt_id "
                "combination_group_id contract_computation_id previous_computation_id cause "
                "sampled created_at created_by created_by_kind"
            ),
            SPEC_C2_LEDGER: _cols("origin_periods input_comparison"),
        },
        status=Status.PENDING,
    ),
    _table(
        "subledger_line_event",
        "T-SL-12",
        (
            "The contract events a cumulative posting line attributes to, in ENG-06 order "
            "(ENGINE_SPEC_B S14-R-13a; D-98 candidate 95; 04 rev 1.48)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id subledger_line_id contract_event_id ordinal created_at created_by "
                "created_by_kind"
            ),
            SPEC_C2_LEDGER: _cols("subledger_line_period_end_date"),
        },
    ),
    # ---- CLS tables (04 T-CLS-nn)
    _table(
        "close_run",
        "T-CLS-01",
        (
            "Persisted, resumable close state machine per entity, book and period "
            "(REQ-CLS-012, -013; research 06 §6.4, §12.4)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id close_run_no entity_id period_id status cutoff_known_at job_id "
                "started_at finished_at created_at created_by created_by_kind updated_at "
                "updated_by updated_by_kind row_version rates_read registry_read"
            ),
            R02: _cols("book_code current_step_code steps counts"),
        },
    ),
    _table(
        "close_checklist_template",
        "T-CLS-02",
        "System gates and tenant-defined close tasks (REQ-CLS-008, -009, -021).",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id gate_kind owner_role_id is_active created_at created_by "
                "created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            R02: _cols(
                "code name description gate_check_code is_blocking is_system due_offset_days "
                "sequence"
            ),
        },
    ),
    _table(
        "close_checklist_item",
        "T-CLS-03",
        "Checklist instance per entity, book and period with gate result, sign-off or waiver.",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id close_checklist_template_id entity_id period_id status "
                "owner_membership_id control_execution_id signoff_id waiver_approval_request_id "
                "created_at created_by created_by_kind updated_at updated_by updated_by_kind "
                "row_version"
            ),
            R02: _cols("book_code due_date result comment"),
        },
    ),
    _table(
        "period_lock",
        "T-CLS-04",
        (
            "Lock, reopen or permanent-lock record with certification, head hashes and "
            "snapshot manifest (REQ-CLS-009 to -011)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id kind entity_id period_id period_state_transition_id "
                "approval_request_id ledger_head_chain_seq ledger_head_sha256 "
                "audit_head_chain_seq audit_head_hmac snapshot_manifest_sha256 previous_lock_id "
                "diff_report_file_id cutoff_known_at created_at created_by created_by_kind"
            ),
            R02: _cols("book_code reason_code comment certification"),
        },
    ),
    _table(
        "lock_snapshot",
        "T-CLS-05",
        'Immutable dataset frozen at lock; "as locked" reports reference it (REQ-CLS-010).',
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id period_lock_id snapshot_kind report_run_id file_id file_sha256 "
                "row_count created_at created_by created_by_kind"
            ),
            R02: _cols("control_totals"),
        },
    ),
    _table(
        "reconciliation",
        "T-CLS-06",
        (
            "Billing-to-subledger, subledger-to-GL, rollforward and migration reconciliations "
            "with certification (REQ-CLS-015 to -017, REQ-MIG-003)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id reconciliation_no kind entity_id period_id status as_of_known_at "
                "period_lock_id source_file_id sync_run_id variance_count "
                "auto_certify_rule_set_version_id auto_certify_rule_id report_run_id "
                "certified_at created_at created_by created_by_kind updated_at updated_by "
                "updated_by_kind row_version ledger_chain_seq source_documents_read "
                "subledger_documents_read"
            ),
            R02: _cols("book_code totals unexplained_other_amount"),
        },
    ),
    _table(
        "reconciliation_item",
        "T-CLS-07",
        "Itemised difference with classification and explanation.",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id reconciliation_id item_kind contract_id invoice_number "
                "resolved_at resolved_by resolved_by_kind created_at created_by created_by_kind "
                "updated_at updated_by updated_by_kind row_version origin_period_id"
            ),
            R02: _cols(
                "account_code subledger_amount source_amount difference currency is_high_risk "
                "gl_document_reference explanation account_role"
            ),
        },
    ),
    _table(
        "signoff",
        "T-CLS-08",
        "Preparer, reviewer or controller sign-off on a close object (research 07 §5.6).",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id subject_type subject_id signer_id subject_content_sha256 "
                "mfa_verified_at signed_at"
            ),
            R02: _cols("role statement"),
        },
    ),
    # ---- RPT tables (04 T-RPT-nn)
    _table(
        "report_definition",
        "T-RPT-01",
        (
            "Global, versioned standard report catalogue that tenants cannot modify "
            "(REQ-RPT-001, -027)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols("kind"),
            R02: _cols(
                "code version name description parameters_schema output_formats ipe_logic "
                "tie_outs is_current"
            ),
        },
    ),
    _table(
        "report_run",
        "T-RPT-02",
        (
            "IPE-grade report and export run record (REQ-RPT-002, CTL-029; research 07 §5.10 "
            'RPT-01 and feature F-13 "standard report catalogue with run records"; the design '
            "brief's reference to F-14 denotes th..."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id report_run_no report_version status entity_ids known_at "
                "period_lock_id engine_release_id output_file_id output_sha256 manifest_file_id "
                "row_count child_report_run_ids disclosure_snapshot_ids job_id started_at "
                "finished_at created_at created_by created_by_kind updated_at updated_by "
                "updated_by_kind row_version"
            ),
            R02: _cols(
                "report_code parameters book_code as_of_date output_format control_totals "
                "tie_out_results ledger_heads source_binding problem"
            ),
        },
    ),
    _table(
        "disclosure_snapshot",
        "T-RPT-03",
        (
            "Frozen disclosure dataset per entity, book and period (research 04 §14.1; "
            "REQ-CLS-010; REQ-RPT-007 to -011)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id disclosure_kind entity_id period_id period_lock_id report_run_id "
                "data_sha256 created_at created_by created_by_kind"
            ),
            R02: _cols("book_code data"),
        },
    ),
    _table(
        "evidence_pack",
        "T-RPT-04",
        (
            "Period and contract sample evidence packs with manifest and per-file hashes "
            "(REQ-RPT-014, -015)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id pack_no kind entity_id period_id period_lock_id contract_ids "
                "status manifest_sha256 file_id report_run_ids job_id created_at created_by "
                "created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            R02: _cols("book_code as_of_date from_date to_date manifest"),
        },
    ),
    # ---- IMP tables (04 T-IMP-nn)
    _table(
        "import_template",
        "T-IMP-01",
        (
            "Global template registry: the four legacy templates as v1 and the modern CSV "
            "templates (D-30; REQ-DAT-002, -004, -016)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R02: _cols(
                "code version name family target_object file_format sheet_rule header_match "
                "headers required_parameters row_model aggregation_rule is_current"
            ),
        },
    ),
    _table(
        "import_upload",
        "T-IMP-02",
        (
            "One uploaded file through upload → validate → dry-run diff → approval → atomic "
            "commit (D-30; REQ-DAT-001, -008, -010, -015)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id import_no template_version file_object_id file_sha256 "
                "mapping_profile_id status row_count valid_row_count warning_count error_count "
                "diff_file_id approval_request_id committed_at job_id named_entity_ids created_at "
                "created_by created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            # 04 rev 1.147 (revision 0102): permission codes, as T-PLT-15 / T-PLT-16 ``scopes``
            R03: _cols("uploader_scopes"),
            SPEC_C2_PAYLOAD: _cols(
                "template_code parameters is_quarantine_mode control_totals diff_summary"
            ),
        },
    ),
    _table(
        "import_row",
        "T-IMP-03",
        (
            "Each data row as read, normalized and validated, with its row number "
            "(REQ-DAT-006, -007)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id import_upload_id row_number row_sha256 status "
                "aggregated_into_row_id created_at created_by created_by_kind"
            ),
            SPEC_C2_PAYLOAD: _cols("raw normalized business_key"),
            R02: _cols("sheet_name"),
        },
        notes={
            "raw": ColumnNote(
                erasure=Erasure.TOKENISED,
                note=(
                    "C3 paths declared by the template are tokenised before the write (05 "
                    "PRV-05, IPL-04)."
                ),
            ),
            "normalized": ColumnNote(
                erasure=Erasure.TOKENISED,
                note="Derived from `raw` after tokenisation (05 IPL-04).",
            ),
        },
    ),
    _table(
        "import_row_lineage",
        "T-IMP-04",
        "Row-level lineage from a row to every object it emitted (D-30, D-43; REQ-RPT-017).",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id import_row_id import_upload_id target_id created_at created_by "
                "created_by_kind"
            ),
            SPEC_C2_PAYLOAD: _cols("target_type"),
        },
    ),
    _table(
        "exception_item",
        "T-IMP-05",
        (
            "Shared exception queue for imports, adapters, engine quarantines, close blockers, "
            "data-quality monitors, anomaly action items and migration (REQ-DAT-009; "
            "REQ-CLS-013, -019; REQ-AI-007)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id exception_no status priority import_upload_id import_row_id "
                "sync_run_id source_record_id contract_id obligation_id combination_group_id "
                "entity_id period_id close_run_id journal_run_id owner_membership_id dedupe_key "
                "occurrence_count last_seen_at resolved_at resolved_by resolved_by_kind "
                "waiver_approval_request_id reprocessed_at created_at created_by "
                "created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            R02: _cols(
                "source code severity disposition title message suggestion field business_key "
                "source_payload resolution"
            ),
        },
    ),
    _table(
        "import_mapping_profile",
        "T-IMP-06",
        (
            "Versioned column mapping for modern CSV imports: aliases, constants and custom "
            "attribute columns (REQ-DAT-013)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id created_at created_by created_by_kind updated_at updated_by "
                "updated_by_kind row_version version_no status content_sha256 "
                "approval_request_id published_at published_by supersedes_version_id"
            ),
            R02: _cols("code name template_code mappings effective_from effective_to"),
        },
    ),
    # ---- INT tables (04 T-INT-nn); T-INT-01 / 02 / 04 reconciled with DIN-12 (revision 0072)
    _table(
        "integration_connection",
        "T-INT-01",
        "Configured adapter instance (REQ-INT-002 to -009, REQ-JE-012 to -015).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id adapter entity_ids status last_test_at created_at created_by "
                "created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            R02: _cols(
                "code name direction base_url config checkpoint last_test_result last_test_detail"
            ),
            R06: _cols("secret_ref"),
        },
        notes={
            "secret_ref": ColumnNote(
                note="Secret reference only (05 ARC-11).",
            ),
        },
    ),
    _table(
        "sync_run",
        "T-INT-02",
        "Interface run ledger with control totals (REQ-DAT-010; research 07 IN-02).",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id integration_connection_id kind status record_count "
                "exception_count job_id started_at finished_at created_at created_by "
                "created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            R02: _cols("checkpoint_before checkpoint_after source_totals loaded_totals problem"),
        },
        recipients=frozenset({Recipient.TENANT_SYSTEMS}),
    ),
    _table(
        "outbox_message",
        "T-INT-03",
        (
            "Transactional outbox for journal export, webhooks, email and sync requests "
            "(research 06 §14.5; REQ-JE-013)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id topic aggregate_type aggregate_id dedupe_key status attempt_count "
                "next_attempt_at dispatched_at created_at created_by created_by_kind updated_at "
                "updated_by updated_by_kind row_version"
            ),
            R02: _cols("payload last_error"),
        },
        recipients=frozenset({Recipient.TENANT_SYSTEMS}),
    ),
    _table(
        "external_id_map",
        "T-INT-04",
        (
            "Mapping between internal ids and external system ids per connection (research 06 "
            "§14.4; REQ-INT-008)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id integration_connection_id object_type internal_id external_id "
                "external_version valid_from valid_to sync_run_id created_at created_by "
                "created_by_kind"
            ),
        },
        recipients=frozenset({Recipient.TENANT_SYSTEMS}),
    ),
    # ---- FC tables (04 T-FC-nn)
    _table(
        "scenario",
        "T-FC-01",
        (
            "Registers a scenario (sandbox) tenant created from a production snapshot "
            "(REQ-FC-001, -004)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id scenario_tenant_id tenant_snapshot_id base_known_at status "
                "last_refreshed_at created_at created_by created_by_kind updated_at updated_by "
                "updated_by_kind row_version"
            ),
            R02: _cols("name purpose"),
        },
        status=Status.PENDING,
    ),
    _table(
        "forecast_event_set",
        "T-FC-02",
        (
            "Named, versioned set of forecast inputs re-applied in order on refresh "
            "(REQ-FC-002, -004)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id production_scenario_id import_upload_ids created_at created_by "
                "created_by_kind updated_at updated_by updated_by_kind row_version version_no "
                "status content_sha256 approval_request_id published_at published_by "
                "supersedes_version_id"
            ),
            R02: _cols("code name api_commands effective_from effective_to"),
        },
        status=Status.PENDING,
    ),
    _table(
        "forecast_run",
        "T-FC-03",
        (
            "Forecast computation over a scenario producing revenue, billing, balances, RPO "
            "and journal preview reports (REQ-FC-003, -005)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id forecast_event_set_id status report_run_ids job_id started_at "
                "finished_at created_at created_by created_by_kind updated_at updated_by "
                "updated_by_kind row_version"
            ),
            R02: _cols("parameters problem"),
        },
        status=Status.PENDING,
    ),
    _table(
        "deal_preview",
        "T-FC-04",
        "Audited deal-desk allocation preview (REQ-FC-006).",
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id input_sha256 result_sha256 engine_release_id saved_contract_id "
                "created_at created_by created_by_kind"
            ),
            R02: _cols("input result pinned_refs"),
        },
        status=Status.PENDING,
    ),
    # ---- AI tables (04 T-AI-nn)
    _table(
        "ai_proposal",
        "T-AI-01",
        (
            "AI output as a proposal with citations; acceptance is an audited human command "
            "(D-46; REQ-AI-003, -005 to -008)."
        ),
        Retention.TENANT_LIFETIME,
        {
            R01: _cols(
                "tenant_id id kind status subject_type subject_id file_object_id "
                "document_text_file_id ai_model_log_id accepted_object_id accepted_by "
                "accepted_at rejected_by rejected_at expires_at created_at created_by "
                "created_by_kind updated_at updated_by updated_by_kind row_version"
            ),
            R02: _cols(
                "content citations accepted_command field_decisions accepted_object_type "
                "rejection_reason problem"
            ),
        },
        status=Status.PENDING,
        notes={
            "content": ColumnNote(
                recipients=frozenset({Recipient.AI_PROVIDER}),
                note=(
                    "Model output received from the provider when AI is enabled (D-46); "
                    "prompts are redacted first (05 PRV-08)."
                ),
            ),
            "citations": ColumnNote(
                recipients=frozenset({Recipient.AI_PROVIDER}),
            ),
        },
    ),
    _table(
        "ai_model_log",
        "T-AI-02",
        "Configuration evidence per AI call (REQ-AI-004).",
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id provider model_id prompt_template_id prompt_template_version "
                "input_sha256 response_sha256 input_tokens output_tokens latency_ms outcome "
                "created_at created_by created_by_kind"
            ),
            R02: _cols("parameters error_detail"),
        },
        status=Status.PENDING,
    ),
    # ---- MIG tables (04 T-MIG-nn; landed by revision 0056, lane F-LMG, 2026-09-20)
    _table(
        "migration_batch",
        "T-MIG-01",
        (
            "Legacy `ASC606.db` import in opening-balance or replay mode, with profiling, "
            "reconciliation and promotion (D-31; REQ-MIG-001 to -006)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id migration_no status source_file_id source_sha256 "
                "sandbox_tenant_id import_upload_ids registry_version_id reconciliation_id "
                "reconciliation_report_run_id approval_request_id job_id started_at finished_at "
                "capture_operation_id created_at created_by created_by_kind updated_at updated_by "
                "updated_by_kind row_version"
            ),
            R02: _cols("mode cutover_date profile problem"),
        },
    ),
    _table(
        "migrated_legacy_row",
        "T-MIG-02",
        (
            'Read-only migrated `Contract_Live` history labelled "migrated, unattributed" '
            "(D-31 mode a; REQ-MIG-001; research 07 K4)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id migration_batch_id source_rowid contract_external_id "
                "processing_time_log record_unique_id legacy_row_sha256 contract_id "
                "obligation_id created_at created_by created_by_kind"
            ),
            R02: _cols("obligation_key product_code current_period legacy_row label"),
        },
    ),
    _table(
        "migration_reconciliation_line",
        "T-MIG-03",
        (
            "Per contract and obligation comparison of eRev values with the source database "
            "(REQ-MIG-003)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id migration_batch_id contract_external_id exception_item_id "
                "created_at created_by created_by_kind"
            ),
            R02: _cols(
                "obligation_key measure source_value erev_value difference tolerance "
                "is_within_tolerance deviation_ref"
            ),
        },
    ),
    # T-MIG-04 / T-MIG-05 (04 rev 1.60; revision 0067, lane F-LMG, 2026-09-20): the durable capture
    # of the import's dry run. The ``*_id`` columns other than the batch / population-version keys
    # are identity tokens of rolled-back engine rows (D-98 candidate 106 exclusion).
    _table(
        "migration_population_version",
        "T-MIG-04",
        (
            "One contract version the opening-balance import's dry run computed for a migration: "
            "identities (tokens), provenance, authoritative membership, expected obligation "
            "output and the calc-trace mirror the reconcile binds and hash-checks (D-98 "
            "candidates 122 and 126)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id migration_batch_id contract_version_id version_no book_code "
                "combination_group_id status_in_book contract_computation_id input_sha256 "
                "output_sha256 engine_version engine_release_id known_at bundle_known_at "
                "payload_migration_batch_id opening_event_id opening_event_key "
                "opening_event_binding_sha256 expected_output_captured "
                "obligation_version_ids capture_operation_id calc_trace_id format_version "
                "node_count trace_sha256 input_evidence_sha256 created_at created_by "
                "created_by_kind"
            ),
            R02: _cols("cutover_date members root_measures trace input_evidence"),
        },
    ),
    _table(
        "migration_population_obligation",
        "T-MIG-05",
        (
            "One captured obligation version of a T-MIG-04 row: the nine T-MIG-03 measure sources "
            "as obligation_version stores them, the trace-node binding and the full row as "
            "evidence (rev 1.60)."
        ),
        Retention.AUDIT_RETENTION_YEARS,
        {
            R01: _cols(
                "tenant_id id migration_batch_id population_version_id capture_operation_id "
                "contract_version_id obligation_version_id contract_id contract_external_id "
                "row_sha256 created_at created_by created_by_kind"
            ),
            R02: _cols(
                "obligation_key obligation_kind original_allocated_exact remaining_quantity "
                "billed_cum revenue_cum remaining_allocation position_obligation "
                "netting_reclass_amount trace_nodes row"
            ),
        },
    ),
)


def _build(
    tables: Iterable[TableClassification],
) -> tuple[Mapping[str, TableClassification], Mapping[tuple[str, str], ColumnClassification]]:
    by_table: dict[str, TableClassification] = {}
    by_column: dict[tuple[str, str], ColumnClassification] = {}
    for table in tables:
        if table.name in by_table:
            raise ValueError(f"privacy catalogue lists table {table.name} twice")
        by_table[table.name] = table
        for rule, columns in table.groups.items():
            for column in columns:
                key = (table.name, column)
                if key in by_column:
                    raise ValueError(f"privacy catalogue lists {table.name}.{column} twice")
                note = table.notes.get(column, ColumnNote())
                by_column[key] = ColumnClassification(
                    table=table.name,
                    ref=table.ref,
                    column=column,
                    data_class=rule.data_class,
                    basis=rule.basis,
                    rule=rule.id,
                    purpose=note.purpose or table.purpose,
                    retention=table.retention,
                    retention_basis=table.retention_basis,
                    erasure=note.erasure or Erasure.NONE,
                    recipients=(
                        note.recipients if note.recipients is not None else table.recipients
                    ),
                    status=Status.PENDING if note.pending is not None else table.status,
                    pending=note.pending
                    or (PendingSource.DOC_04 if table.status is Status.PENDING else None),
                    note=note.note,
                )
        for column in table.notes:
            if (table.name, column) not in by_column:
                raise ValueError(f"privacy catalogue notes unknown column {table.name}.{column}")
    return MappingProxyType(by_table), MappingProxyType(by_column)


_BUILT: Final = _build(TABLES)
TABLE_CLASSIFICATION: Final[Mapping[str, TableClassification]] = _BUILT[0]
CLASSIFICATION: Final[Mapping[tuple[str, str], ColumnClassification]] = _BUILT[1]


def data_class(table: str, column: str) -> DataClass:
    """The class of ``table.column``; ``KeyError`` when the column is not catalogued."""
    return CLASSIFICATION[(table, column)].data_class


def columns_of(
    data_class: DataClass, *, status: Status | None = None
) -> tuple[ColumnClassification, ...]:
    """Every catalogued column of ``data_class``, optionally limited to one status."""
    return tuple(
        entry
        for entry in CLASSIFICATION.values()
        if entry.data_class is data_class and (status is None or entry.status is status)
    )


def check_coverage(code_columns: Iterable[tuple[str, str]]) -> CoverageReport:
    """Compare the catalogue with the ``(table, column)`` pairs of ``erev_api.db.tables``.

    ``missing`` are code columns without an ``ACTIVE`` entry; ``unknown`` are ``ACTIVE`` entries
    that name no code column; ``landed`` are ``PENDING`` entries whose column now exists and must
    be reconciled (status flipped and class confirmed) before the test passes again.
    """
    code = frozenset(code_columns)
    active = {key for key, entry in CLASSIFICATION.items() if entry.status is Status.ACTIVE}
    pending = {key for key, entry in CLASSIFICATION.items() if entry.status is Status.PENDING}
    return CoverageReport(
        missing=tuple(sorted(code - active)),
        unknown=tuple(sorted(active - code)),
        landed=tuple(sorted(pending & code)),
    )
