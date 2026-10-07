"""Tenant-snapshot dataset pipeline, the pure part (BUILD_SPEC SNP-1 preparation; 05 §10 SBX-03,
SBX-04, SBX-07, SBX-11; 04 T-PLT-34, T-PLT-29, T-PLT-01; 05 PRV-06, PRV-07; dev-guide DG-KRN-CAN-01
to -15; supervisor rulings D-98 candidate 25 on the lane's Q-1 to Q-4).

A tenant snapshot is one JSONL file per copied table plus a JSON manifest (SBX-03; T-PLT-34). This
module holds everything that needs no database:

* the **inventory** — every table of the 04 model carries one explicit :class:`SnapshotClass`
  (COPIED, REGENERATED, EXCLUDED_SECRET, REPLAY_REFERENCE, PENDING; SHARED for the tables without
  ``tenant_id`` that a sandbox reads in place), its SBX-03 reason family (:class:`Category`) and a
  one-line reason; a drift guard fails when a metadata table is unclassified, a rule is stale, or a
  PENDING table (named by the spec, absent on main) appears;
* the **references** — the metadata declares no foreign keys, so every ``*_id`` column of a copied
  table is resolved to its target by name, by ``ALIASES`` or as a declared ``NON_REFERENCE``; the
  resolved references are the load-order oracle: a NOT NULL reference's target precedes its child in
  ``LOAD_ORDER``, a nullable reference to a later table is **deferred** (nulled while loading,
  restored by the ``fixup-deferred-references`` step — an UPDATE, so only where the table's
  immutability class lets the column change), a nullable reference to the same table is never
  deferred (the dataset's rows load **referenced-first**, ``referenced_first``), a reference
  between two tables of one **component** (``COMPONENTS``: tables whose frozen references form a
  cycle no table order breaks) is satisfied by ONE row order over the whole component
  (``component_order``), and a reference to a REGENERATED, PENDING, REPLAY_REFERENCE or
  EXCLUDED_SECRET target is **nulled on export** (recompute or replay produces the sandbox's own
  row, or the target does not exist yet);
* the **JSONL codec** — one canonical JSON object per row (DG-KRN-CAN order and forms through
  ``erev_engine.canonical``), rows in a deterministic order, LF-terminated; binary values are
  refused (PRV-06 ciphertexts never enter a dataset), INET values are normalised with ``str`` as
  ``audit/chain.py`` does, EXCLUDED columns (``EXCLUDED_COLUMNS``, every ``*_token_sha256`` or
  secret-derived column a metadata scan finds; ruling Q-5) are nulled;
* the **content hash and row count** (SHA-256 of the plaintext bytes, T-PLT-29 ``sha256``);
* the **``known_at`` stamp and per-table cutoff** (ruling Q-6): facts and events by their recorded /
  applied / decided / created timestamp; configuration and version tables by their effective state
  as of ``known_at`` (a version created after ``known_at`` but effective on or before it is
  included, one effective after it is not); version children follow their parent; period
  definitions and counters are whole — every rule is data (``CUTOFF_RULES``) with a drift guard;
* the **manifest** (format 2: dataset entries, exclusions with their class and reason, the ruled
  **retention** block — every ``file_object`` id the snapshot carries with its retention state,
  the inherited legal hold and the P8 catalogue families — the **shared** block naming the SHARED
  identities the copy depends on, and the explicit statement that source audit history is not
  carried) with its verifier and the shred checks; the **rebuild steps** of every reference nulled
  on export (``REBUILD_STEPS``); and
* the **load / reset plans** of SBX-04 and SBX-07 as data with the gates each step needs.

Reading rows, writing files (``files.store.put_file`` with purpose ``SNAPSHOT_DATASET``, PRV-06),
the T-PLT-34 row, the job and the routes belong to the integration lane after GATE-RPS / GATE-PLF.
The source is never altered by anything here.

The retention rules (Q-4) are a supervisor ruling recorded as data and pure checks; they require
human confirmation (Ray / Legal) before production use.
"""

from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

import sqlalchemy as sa
from erev_engine.canonical import canonical_bytes
from sqlalchemy import LargeBinary, MetaData

from erev_api.db.tables import metadata as model_metadata

__all__ = [
    "ALIASES",
    "ARRAY_REFERENCES",
    "SCOPE_ARRAYS",
    "SCOPE_UNREPRESENTABLE",
    "ScopeRule",
    "AUDIT_HISTORY_STATEMENT",
    "CLASSIFICATION",
    "CLOSED_INVITATION",
    "CLOSED_INVITATION_AT",
    "COMPONENTS",
    "COPIED_CATEGORIES",
    "CUTOFF_RULES",
    "EMPTY_SANDBOX_PURPOSE",
    "EXCLUDED_COLUMNS",
    "GATE_JOB_LOCK",
    "GATE_PERMISSION",
    "GATE_PROVISIONING_SCOPE",
    "GATE_STEP_UP",
    "LOAD_ORDER",
    "MANIFEST_FORMAT_VERSION",
    "ParentCutoff",
    "SCOPE_COLUMN",
    "NON_REFERENCES",
    "OPEN_INVITATION",
    "REVOKED_WITH_INVITATION",
    "REVOKED_WITH_INVITATION_AT",
    "TOKEN_COLUMNS",
    "PENDING",
    "PENDING_TABLES",
    "POLYMORPHIC_SUBJECTS",
    "POLYMORPHIC_SUBJECT_COLUMNS",
    "PURPOSES",
    "REBUILD_STEPS",
    "RESET_ROUTE",
    "RETENTION_ATTRIBUTE",
    "RETENTION_FAMILIES",
    "RETENTION_LITERALS",
    "RETENTION_PARAMETER",
    "RULES",
    "SHARED_KEYS",
    "Category",
    "CutoffKind",
    "CutoffRule",
    "Dataset",
    "EMPTY_SHA256",
    "Encoded",
    "Exclusion",
    "FileRetention",
    "Inventory",
    "JsonlStream",
    "Manifest",
    "ManifestEntry",
    "apply_parent_cutoff",
    "close_open_invitations",
    "identity_columns",
    "primary_key",
    "row_identity",
    "PendingTable",
    "Reference",
    "Retention",
    "RetentionConfirmation",
    "RetentionPolicy",
    "UnconfirmedRetention",
    "Shared",
    "SharedKey",
    "SharedRef",
    "SnapshotClass",
    "Stamp",
    "Step",
    "TableRule",
    "cutoff",
    "decode_rows",
    "empty_sandbox_plan",
    "encode_rows",
    "encode_stream",
    "export_row",
    "inventory",
    "load_plan",
    "manifest_bytes",
    "manifest_sha256",
    "parents",
    "referenced_first",
    "references",
    "reset_plan",
    "retention_of",
    "retention_confirmation",
    "retention_policy_of",
    "confirmation_source",
    "scan_excluded_columns",
    "shared_dependencies",
    "shred_check",
    "shred_targets",
    "source_untouched",
    "verify_manifest",
    "verify_shared",
]

MANIFEST_FORMAT_VERSION: Final = 2
# T-PLT-34 ``purpose`` literals.
PURPOSES: Final = frozenset({"SANDBOX_COPY", "STORED_BACKUP", "SANDBOX_SEED"})
# An EMPTY sandbox has no T-PLT-34 row and no dataset: SNP-3 reset mode EMPTY and the legacy replay
# target of LMG-4 (SBX-02; T-MIG-01 ``sandbox_tenant_id``; F-LMG interface, record §11.2).
EMPTY_SANDBOX_PURPOSE: Final = "EMPTY"
# 04 API-R-04: the reset route (BUILD_SPEC SNP-3).
RESET_ROUTE: Final = "POST /tenant/reset"
# Gates a load or reset step needs (PRD ACT-50, ACT-51; 05 SBX-02; 04 DB-15; 05 §5.6 row).
GATE_PERMISSION: Final = "permission tenant.snapshot"
GATE_RESET_PERMISSION: Final = "permission sandbox.reset"
GATE_STEP_UP: Final = "fresh TOTP step-up (403 mfa-step-up-required otherwise)"
GATE_PROVISIONING_SCOPE: Final = "app.platform_scope = 'provisioning' (DB-15 tenant INSERT policy)"
GATE_JOB_LOCK: Final = "job lock tenant-copy:<source tenant> (05 §5.6; 1,800 s)"
# Q-4 / P8: the privacy catalogue's table-level attribute is ``retention`` with a ``Retention``
# literal (sprint/l16 ecadc12, not on main); the per-row state stays T-PLT-29 ``retention_until`` /
# ``legal_hold``. The families below repeat P8's reply as strings; every class 04/05 does not name
# is PROPOSED until counsel confirms.
RETENTION_ATTRIBUTE: Final = "retention"
RETENTION_FAMILIES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "file_object": "FILE_RETENTION",
        "import_row": "AUDIT_RETENTION_YEARS",
        "source_record": "AUDIT_RETENTION_YEARS",
        "contract_event": "AUDIT_RETENTION_YEARS",
        "manual_adjustment": "AUDIT_RETENTION_YEARS",
    }
)
RETENTION_FAMILIES_STATUS: Final = (
    "PROPOSED: P8 catalogue (sprint/l16), FILE_RETENTION is SPEC (05 PRV-06, PRV-07); counsel owns "
    "the periods; the ruling requires human confirmation before production use"
)
# Slice I-5: the families become tenant configuration — T-PLT-31 rule 2 (04 rev 1.19). The default
# {} confirms nothing and the exporter refuses; a PUBLISHED TENANT version carrying all five
# families is the human confirmation ruling Q-4 requires.
RETENTION_PARAMETER: Final = "platform.snapshot_retention_families"
RETENTION_LITERALS: Final = (
    "TENANT_LIFETIME",
    "AUDIT_RETENTION_YEARS",
    "EXPIRES_AT_SWEEP",
    "FILE_RETENTION",
)
# Ruling Q-7 addition: the sandbox's audit chain starts fresh (SBX-06).
# 05 SBX-06 rev 1.34: tenant.snapshot_loaded is the load's summary event, not the chain's first —
# the replay and the recompute audit before it.
AUDIT_HISTORY_STATEMENT: Final = (
    "Source audit history is not carried into the sandbox: audit_event, audit_chain_head and "
    "security_event are REGENERATED; the sandbox chain holds only what its load writes — the "
    "period replay, the recompute and the summary event tenant.snapshot_loaded (SBX-06)"
)


class SnapshotClass(StrEnum):
    """The explicit class of a table in the snapshot (ruling D-98 candidate 25 on Q-1)."""

    COPIED = "COPIED"  # facts and configuration the engine or the replay reads
    REGENERATED = "REGENERATED"  # derived or operational state the sandbox produces on its own
    EXCLUDED_SECRET = "EXCLUDED_SECRET"  # secret columns or secret tables, never snapshotted
    REPLAY_REFERENCE = "REPLAY_REFERENCE"  # copied for the replay driver, not loaded as rows
    PENDING = "PENDING"  # the spec names it, main lacks it
    SHARED = "SHARED"  # no tenant_id: read in place by the sandbox (engineering addition)


class Category(StrEnum):
    """The SBX-03 reason family behind a class."""

    FACT = "FACT"
    CONFIGURATION = "CONFIGURATION"
    REPLAY_REFERENCE = "REPLAY_REFERENCE"
    DERIVED = "DERIVED"
    AUDIT = "AUDIT"
    CREDENTIAL_SESSION = "CREDENTIAL_SESSION"
    INTEGRATION = "INTEGRATION"
    SUPPORT = "SUPPORT"
    OPERATIONAL = "OPERATIONAL"
    GLOBAL_REFERENCE = "GLOBAL_REFERENCE"
    SNAPSHOT_BOOKKEEPING = "SNAPSHOT_BOOKKEEPING"


COPIED_CATEGORIES: Final = frozenset({Category.FACT, Category.CONFIGURATION})
_COPIED_CLASSES: Final = frozenset({SnapshotClass.COPIED, SnapshotClass.REPLAY_REFERENCE})
# A reference to one of these target classes is nulled on export (the sandbox produces the row, or
# the table does not exist yet, or the row never travels).
_NULLED_TARGET_CLASSES: Final = frozenset(
    {
        SnapshotClass.REGENERATED,
        SnapshotClass.PENDING,
        SnapshotClass.EXCLUDED_SECRET,
        SnapshotClass.REPLAY_REFERENCE,
    }
)


@dataclass(frozen=True, slots=True)
class TableRule:
    """One table's class, reason family and one-line reason."""

    snapshot_class: SnapshotClass
    category: Category
    reason: str


_C = SnapshotClass
_K = Category


def _copied(category: Category, reason: str) -> TableRule:
    return TableRule(_C.COPIED, category, reason)


def _regenerated(category: Category, reason: str) -> TableRule:
    return TableRule(_C.REGENERATED, category, reason)


def _secret(category: Category, reason: str) -> TableRule:
    return TableRule(_C.EXCLUDED_SECRET, category, reason)


def _shared(reason: str) -> TableRule:
    return TableRule(_C.SHARED, _K.GLOBAL_REFERENCE, reason)


# Every table of the 04 model on main, classified once (SBX-03 read through the ruled classes).
RULES: Final[Mapping[str, TableRule]] = MappingProxyType(
    {
        # --- copied configuration (SBX-03: reference data and all configuration versions) -----
        "fiscal_calendar": _copied(_K.CONFIGURATION, "reference data: calendars (SBX-03)"),
        "period": _copied(_K.CONFIGURATION, "period definitions (SBX-03); loaded open (SBX-04)"),
        "legal_entity": _copied(_K.CONFIGURATION, "reference data: entities (SBX-03)"),
        "book": _copied(_K.CONFIGURATION, "reference data: books (SBX-03)"),
        "entity_book": _copied(_K.CONFIGURATION, "reference data: books kept per entity"),
        "tenant_currency": _copied(_K.CONFIGURATION, "tenant currencies (ruling Q-1: COPIED)"),
        "fx_rate_set": _copied(_K.CONFIGURATION, "reference data: FX rate sets (SBX-03)"),
        "fx_rate_set_version": _copied(_K.CONFIGURATION, "configuration versions (SBX-03)"),
        "fx_rate": _copied(_K.CONFIGURATION, "FX rates of a rate set version"),
        "gl_account": _copied(_K.CONFIGURATION, "reference data: accounts (SBX-03)"),
        "dimension_definition": _copied(_K.CONFIGURATION, "reference data: dimensions"),
        "dimension_value": _copied(_K.CONFIGURATION, "reference data: dimension values"),
        "account_mapping_version": _copied(_K.CONFIGURATION, "configuration versions (SBX-03)"),
        "account_mapping_rule": _copied(_K.CONFIGURATION, "rules of a mapping version"),
        "registry_version": _copied(_K.CONFIGURATION, "policy registry versions (ruling Q-1)"),
        "related_party_group": _copied(_K.CONFIGURATION, "reference data: related parties"),
        "pob_template": _copied(_K.CONFIGURATION, "configuration: POB templates (SBX-03)"),
        "pob_template_version": _copied(_K.CONFIGURATION, "configuration versions (SBX-03)"),
        "product": _copied(_K.CONFIGURATION, "products (SBX-03)"),
        "product_bundle_component": _copied(_K.CONFIGURATION, "bundle components of products"),
        "ssp_book": _copied(_K.CONFIGURATION, "configuration: SSP books"),
        "ssp_book_version": _copied(_K.CONFIGURATION, "configuration versions (SBX-03)"),
        "ssp_entry": _copied(_K.CONFIGURATION, "entries of an SSP book version"),
        "ssp_range": _copied(_K.CONFIGURATION, "ranges of an SSP entry"),
        "ssp_calculator_run": _copied(
            _K.FACT, "SSP calculator evidence referenced by ssp_book_version (ruling Q-1: COPIED)"
        ),
        "ssp_calculator_result": _copied(_K.FACT, "statistics of a calculator run (ruling Q-1)"),
        "ssp_calculator_exclusion": _copied(_K.FACT, "exclusions of a calculator run (ruling Q-1)"),
        "rule_set": _copied(_K.CONFIGURATION, "configuration: rule sets"),
        "rule_set_version": _copied(_K.CONFIGURATION, "configuration versions (SBX-03)"),
        "rule": _copied(_K.CONFIGURATION, "rules of a rule set version"),
        "rule_test_case": _copied(_K.CONFIGURATION, "test cases of a rule set version"),
        "role": _copied(_K.CONFIGURATION, "roles (SBX-03: role assignments need them)"),
        "role_permission": _copied(_K.CONFIGURATION, "permissions of a role"),
        "tenant_membership": _copied(
            _K.CONFIGURATION, "memberships (SBX-03); the invitation token hash is nulled (Q-5)"
        ),
        "role_assignment": _copied(_K.CONFIGURATION, "role assignments (SBX-03)"),
        "sod_rule": _copied(_K.CONFIGURATION, "segregation-of-duties rules"),
        "sod_exception": _copied(_K.CONFIGURATION, "approved SoD exceptions of memberships"),
        "numbering_series": _copied(
            _K.CONFIGURATION, "counters continue from the source so documents never collide (Q-1)"
        ),
        "close_checklist_template": _copied(_K.CONFIGURATION, "close checklist gates"),
        # --- copied facts -----------------------------------------------------------------------
        "file_object": _copied(
            _K.FACT, "file rows sharing storage keys and sidecars (SBX-03); only referenced rows"
        ),
        "file_attachment": _copied(_K.FACT, "attachments of copied subjects"),
        "file_upload": _regenerated(
            _K.OPERATIONAL,
            "the sandbox's own uploads (T-PLT-49); a copied file keeps its first uploader",
        ),
        "import_mapping_profile": _copied(
            _K.CONFIGURATION, "mapping profile versions (IM-P; SBX-03 configuration versions)"
        ),
        "import_upload": _copied(_K.FACT, "import uploads (SBX-03)"),
        "import_row": _copied(_K.FACT, "import lineage (SBX-03)"),
        # landed with main 065e7f65 (wave end): the planned classes of the pending entries apply
        "migration_batch": _copied(_K.FACT, "import lineage (SBX-03); T-MIG-01"),
        "migrated_legacy_row": _copied(_K.FACT, "import lineage (SBX-03); T-MIG-02"),
        # lane F-LMG (04 rev 1.60; revision 0067): the import dry run's durable capture is the
        # batch's evidence; its token columns are declared in TOKEN_COLUMNS (D-98 cand. 106)
        "migration_population_version": _copied(_K.FACT, "import capture (SBX-03); T-MIG-04"),
        "migration_population_obligation": _copied(_K.FACT, "import capture (SBX-03); T-MIG-05"),
        "import_row_lineage": _copied(_K.FACT, "import lineage (SBX-03)"),
        "customer": _copied(_K.FACT, "customers (SBX-03)"),
        "source_record": _copied(_K.FACT, "source records feeding contracts (ruling Q-1: COPIED)"),
        "source_order": _copied(_K.FACT, "source objects (ruling Q-1)"),
        "source_order_line": _copied(_K.FACT, "source objects (ruling Q-1)"),
        "source_invoice": _copied(_K.FACT, "source objects (ruling Q-1)"),
        "source_invoice_line": _copied(_K.FACT, "source objects (ruling Q-1)"),
        "source_usage": _copied(_K.FACT, "source objects (ruling Q-1)"),
        "source_payment": _copied(_K.FACT, "source objects (ruling Q-1)"),
        "source_match": _copied(_K.FACT, "matches of source records (ruling Q-1)"),
        "contract_source_link": _copied(_K.FACT, "links between contracts and source records"),
        "combination_group": _copied(_K.FACT, "accounting units of contracts (SBX-03 contracts)"),
        "contract": _copied(_K.FACT, "contracts (SBX-03)"),
        "modification": _copied(_K.FACT, "modifications (SBX-03; T-CON-06, CTR-17 / D-98 140)"),
        "combination_group_member": _copied(_K.FACT, "group membership of contracts"),
        "obligation": _copied(_K.FACT, "obligation identities of contracts"),
        "event_submission": _copied(_K.FACT, "manual event submissions (ruling Q-1: COPIED)"),
        "contract_event": _copied(_K.FACT, "streams with recorded_at ≤ known_at (SBX-03)"),
        "contract_hold": _copied(_K.FACT, "holds applied to contracts (ruling Q-1: COPIED)"),
        "estimate": _copied(_K.FACT, "estimates (SBX-03)"),
        "estimate_version": _copied(_K.FACT, "estimate versions (SBX-03)"),
        "policy_override": _copied(_K.FACT, "policy overrides (SBX-03)"),
        "judgement_record": _copied(_K.FACT, "judgement records (SBX-03)"),
        "manual_adjustment": _copied(_K.FACT, "manual adjustments (SBX-03)"),
        "approval_request": _copied(_K.FACT, "approvals referenced by copied rows (SBX-03; Q-2)"),
        "approval_step": _copied(_K.FACT, "steps of a copied approval request"),
        "approval_decision": _copied(_K.FACT, "decisions of a copied approval request"),
        # --- replay reference (ruling Q-3) ------------------------------------------------------
        "period_state": TableRule(
            _C.REPLAY_REFERENCE, _K.REPLAY_REFERENCE, "replay source of period states (SBX-04)"
        ),
        "period_state_transition": TableRule(
            _C.REPLAY_REFERENCE, _K.REPLAY_REFERENCE, "replay source of transitions (SBX-04)"
        ),
        "period_lock": TableRule(
            _C.REPLAY_REFERENCE, _K.REPLAY_REFERENCE, "replay source of locks (SBX-04)"
        ),
        # --- regenerated: derived by recompute (SBX-03 never copies derived data) ---------------
        "contract_computation": _regenerated(_K.DERIVED, "recomputed on load (SBX-04 RCP-19)"),
        "contract_version": _regenerated(_K.DERIVED, "recomputed on load (SBX-04)"),
        "contract_version_balance": _regenerated(_K.DERIVED, "recomputed on load (SBX-04)"),
        "fx_layer_movement": _regenerated(_K.DERIVED, "recomputed on load (SBX-04)"),
        "obligation_version": _regenerated(_K.DERIVED, "recomputed on load (SBX-04)"),
        "schedule": _regenerated(_K.DERIVED, "recomputed on load (SBX-04)"),
        "schedule_line": _regenerated(_K.DERIVED, "recomputed on load (SBX-04)"),
        "calc_trace": _regenerated(_K.DERIVED, "recomputed on load (SBX-04)"),
        "subledger_posting": _regenerated(_K.DERIVED, "released postings after replay (SBX-04)"),
        "subledger_posting_seal": _regenerated(_K.DERIVED, "seals of the sandbox's postings"),
        "ledger_chain_head": _regenerated(_K.DERIVED, "the sandbox's own ledger chain"),
        "subledger_line": _regenerated(_K.DERIVED, "released postings after replay (SBX-04)"),
        "subledger_line_event": _regenerated(
            _K.DERIVED, "lineage rows of the sandbox's own postings after replay (SBX-04; T-SL-12)"
        ),
        "journal_run": _regenerated(_K.DERIVED, "journals never copied (SBX-03)"),
        "migration_reconciliation_line": _regenerated(
            _K.DERIVED, "derived by the reconciliation on load; T-MIG-03"
        ),
        "control_execution": _regenerated(_K.OPERATIONAL, "control evidence (T-PLT-39; SOP-1)"),
        "journal_batch": _regenerated(_K.DERIVED, "journals never copied (SBX-03)"),
        "journal_entry": _regenerated(_K.DERIVED, "journals never copied (SBX-03)"),
        "journal_line": _regenerated(_K.DERIVED, "journals never copied (SBX-03)"),
        "posting_ack": _regenerated(_K.DERIVED, "acknowledgements of the source's exports"),
        "report_run": _regenerated(_K.DERIVED, "reports never copied (SBX-03)"),
        "disclosure_snapshot": _regenerated(_K.DERIVED, "snapshots never copied (SBX-03)"),
        "evidence_pack": _regenerated(_K.DERIVED, "reports never copied (SBX-03)"),
        "lock_snapshot": _regenerated(_K.DERIVED, "relock produces the sandbox's own (SBX-04)"),
        "close_run": _regenerated(_K.DERIVED, "the source's close runs; the sandbox runs its own"),
        "close_checklist_item": _regenerated(_K.DERIVED, "items of the source's close runs"),
        "reconciliation": _regenerated(_K.DERIVED, "the source's reconciliations"),
        "reconciliation_item": _regenerated(_K.DERIVED, "the source's reconciliations"),
        "signoff": _regenerated(_K.DERIVED, "the source's sign-offs"),
        "exception_item": _regenerated(_K.DERIVED, "validation derives it on load (ruling Q-1)"),
        # --- regenerated: audit and security logs (SBX-06: the sandbox starts its own chain) ----
        "audit_event": _regenerated(_K.AUDIT, "audit events never copied (SBX-03, SBX-06)"),
        "audit_event_contract": _regenerated(
            _K.AUDIT, "the index of the sandbox's own audit events by contract (T-PLT-48)"
        ),
        "audit_chain_head": _regenerated(_K.AUDIT, "the sandbox starts its own chain (SBX-06)"),
        "audit_chain_verification": _regenerated(_K.AUDIT, "verifications of the source's chain"),
        "security_event": _regenerated(
            _K.AUDIT, "security log with C3 addresses (PRV-01); the sandbox records its own (Q-7)"
        ),
        # --- excluded secrets (SBX-03: not sessions or API clients; PRV-06 ciphertexts) ---------
        "user_session": _secret(_K.CREDENTIAL_SESSION, "sessions never copied (SBX-03)"),
        "api_client": _secret(_K.CREDENTIAL_SESSION, "API clients never copied (SBX-03)"),
        "api_token": _secret(_K.CREDENTIAL_SESSION, "tokens of API clients"),
        "user_mfa_factor": _secret(_K.CREDENTIAL_SESSION, "secret_ciphertext (LargeBinary)"),
        "user_recovery_code": _secret(_K.CREDENTIAL_SESSION, "recovery code hashes"),
        "password_reset_token": _secret(_K.CREDENTIAL_SESSION, "reset token hashes"),
        "identity_provider": _secret(
            _K.CREDENTIAL_SESSION, "client secret reference; global row read in place"
        ),
        "webhook_endpoint": _secret(_K.INTEGRATION, "secret_ciphertext (LargeBinary); SBX-03"),
        # DIN-12 (0072): the planned class of the PENDING entry, moved here when the table landed.
        "integration_connection": _secret(
            _K.INTEGRATION, "adapter credentials by reference (T-INT-01 secret_ref; SBX-03)"
        ),
        "support_grant": _secret(_K.SUPPORT, "access credentials never copied (SBX-03)"),
        # --- regenerated: integration traffic (SBX-08: a sandbox has no outbox) -----------------
        "webhook_delivery": _regenerated(_K.INTEGRATION, "deliveries of the source (SBX-08)"),
        "outbox_message": _regenerated(_K.INTEGRATION, "outbox of the source (SBX-08)"),
        # DIN-12 (0072): the planned classes of the PENDING entries, moved here when the tables
        # landed; a sandbox has no connections, so their runs and id links are its own.
        "sync_run": _regenerated(_K.INTEGRATION, "run ledger of the source (T-INT-02; SBX-08)"),
        "external_id_map": _regenerated(
            _K.INTEGRATION, "per-connection id map (T-INT-04); connections are not copied"
        ),
        # --- regenerated: operational rows the sandbox produces on its own (Q-7) ----------------
        "job": _regenerated(_K.OPERATIONAL, "the load job creates the sandbox's own rows"),
        "notification": _regenerated(_K.OPERATIONAL, "produced by sandbox activity"),
        "notification_preference": _regenerated(_K.OPERATIONAL, "user preferences (Q-7)"),
        "saved_view": _regenerated(_K.OPERATIONAL, "user workspace state (Q-7)"),
        "idempotency_record": _regenerated(_K.OPERATIONAL, "per-command records (IM-E)"),
        "approval_delegation": _regenerated(_K.OPERATIONAL, "time-bound delegations (Q-7)"),
        "access_review_campaign": _regenerated(_K.OPERATIONAL, "the source's reviews (Q-7)"),
        "access_review_item": _regenerated(_K.OPERATIONAL, "the source's reviews (Q-7)"),
        # --- shared: no tenant_id, read in place -------------------------------------------------
        "currency": _shared("global reference (04 §3)"),
        "permission": _shared("global catalogue T-PLT-11"),
        "registry_parameter": _shared("global policy parameters"),
        "registry_parameter_correction": _shared(
            "global catalogue metadata corrections (T-PLT-47)"
        ),
        "import_template": _shared("global templates"),
        "report_definition": _shared("global report catalogue"),
        "engine_release": _shared("global engine releases"),
        "app_user": _shared("global identities; memberships reference them (SBX-03)"),
        "tenant": _shared("the sandbox tenant row is created by provisioning (SBX-02)"),
        # --- the snapshot's own bookkeeping (T-PLT-34, slice I-1) ------------------------------
        "tenant_snapshot": _regenerated(
            _K.SNAPSHOT_BOOKKEEPING,
            "the source's snapshot rows (T-PLT-34); a sandbox's own come from its commands",
        ),
    }
)


@dataclass(frozen=True, slots=True)
class PendingTable:
    """A table the spec defines and main lacks, with the class it takes when it lands."""

    name: str
    planned: SnapshotClass
    category: Category
    lane: str
    reason: str


def _pending(
    name: str, planned: SnapshotClass, category: Category, lane: str, reason: str
) -> tuple[str, PendingTable]:
    return name, PendingTable(name, planned, category, lane, reason)


# 04 tables absent on main 8d76fea (``tenant_snapshot`` landed in slice I-1). A PENDING table that
# appears fails ``inventory()`` until its rule moves into RULES with the planned class (ruling Q-1).
PENDING: Final[Mapping[str, PendingTable]] = MappingProxyType(
    dict(
        (
            _pending("material_right", _C.COPIED, _K.FACT, "CTR", "option terms (T-CON-14)"),
            _pending(
                "contract_cost_asset",
                _C.COPIED,
                _K.FACT,
                "CST",
                "capitalised cost identity (T-CON-15); payee is C3 (PRV-01)",
            ),
            _pending("cost_asset_version", _C.REGENERATED, _K.DERIVED, "CST", "engine state"),
            _pending("loss_provision_version", _C.REGENERATED, _K.DERIVED, "LOS", "engine state"),
            _pending("portfolio", _C.COPIED, _K.CONFIGURATION, "CTR", "portfolios (T-CON-21)"),
            _pending("portfolio_member", _C.COPIED, _K.CONFIGURATION, "CTR", "T-CON-22"),
            _pending(
                "computation_evidence", _C.REGENERATED, _K.DERIVED, "ENG", "computation bytes"
            ),
            _pending(
                "computation_verification", _C.REGENERATED, _K.DERIVED, "SOP", "replay attempts"
            ),
            _pending("posting_attribution", _C.REGENERATED, _K.DERIVED, "REL", "T-SL-11"),
            _pending("release_validation", _C.REGENERATED, _K.DERIVED, "REL", "T-PLT-43"),
            _pending("release_validation_attempt", _C.REGENERATED, _K.DERIVED, "REL", "T-PLT-44"),
            _pending("release_validation_group", _C.REGENERATED, _K.DERIVED, "REL", "T-PLT-45"),
            _pending("release_group_processing", _C.REGENERATED, _K.DERIVED, "REL", "T-PLT-46"),
            _pending(
                "scenario",
                _C.REGENERATED,
                _K.OPERATIONAL,
                "FCS",
                "production-side pointer to a scenario tenant (T-FC-01, SBX-09)",
            ),
            _pending(
                "forecast_event_set", _C.REGENERATED, _K.OPERATIONAL, "FCS", "scenario tenant only"
            ),
            _pending("forecast_run", _C.REGENERATED, _K.DERIVED, "FCS", "scenario tenant only"),
            _pending("deal_preview", _C.REGENERATED, _K.DERIVED, "FCS", "scenario tenant only"),
            _pending(
                "ai_proposal",
                _C.REGENERATED,
                _K.OPERATIONAL,
                "AIX",
                "accepted proposals live on as judgement records, which are copied",
            ),
            _pending("ai_model_log", _C.REGENERATED, _K.AUDIT, "AIX", "AI call evidence"),
        )
    )
)
PENDING_TABLES: Final = frozenset(PENDING)
# Reason families by name, for the tables of RULES and the planned family of PENDING tables.
CLASSIFICATION: Final[Mapping[str, Category]] = MappingProxyType(
    {name: rule.category for name, rule in RULES.items()}
    | {name: item.category for name, item in PENDING.items()}
)

# The dataset order: every NOT NULL reference's target precedes its child (tested against
# ``references``); the three REPLAY_REFERENCE datasets close the list.
LOAD_ORDER: Final[tuple[str, ...]] = (
    "fiscal_calendar",
    "period",
    "legal_entity",
    "book",
    "entity_book",
    "tenant_currency",
    "file_object",
    "file_attachment",
    "gl_account",
    "dimension_definition",
    "dimension_value",
    "related_party_group",
    "customer",
    "pob_template",
    "pob_template_version",
    "product",
    "product_bundle_component",
    "role",
    "role_permission",
    "tenant_membership",
    "sod_rule",
    # FIX-D1 (the frozen-deferral finding of record §14.13; "ordering is the only governed fix"):
    # the approval graphs load BEFORE every row whose ``approval_request_id`` the database freezes
    # at insert — ``sod_exception`` and ``role_assignment`` (IM-S, no UPDATE grant on the column)
    # and the IM-A ``contract_event`` — so that reference is inserted, never fixed up; the rule
    # sets precede them for the same reason (``approval_request.routing_*`` and
    # ``approval_decision.auto_*`` are frozen too). Positions 0 to 20 are unchanged.
    "rule_set",
    "rule_set_version",
    "rule",
    "rule_test_case",
    "approval_request",
    "approval_step",
    "approval_decision",
    "sod_exception",
    "role_assignment",
    "account_mapping_version",
    "account_mapping_rule",
    "registry_version",
    "numbering_series",
    "close_checklist_template",
    "import_mapping_profile",
    "import_upload",
    "import_row",
    "import_row_lineage",
    "fx_rate_set",
    "fx_rate_set_version",
    "fx_rate",
    "ssp_calculator_run",
    "ssp_calculator_result",
    "ssp_calculator_exclusion",
    "ssp_book",
    "ssp_book_version",
    "ssp_entry",
    "ssp_range",
    "source_record",
    "source_order",
    "source_order_line",
    "source_invoice",
    "source_invoice_line",
    "source_usage",
    "source_payment",
    "source_match",
    "combination_group",
    "contract",
    # D-98 140-A3 F1 (F-SNP consent 2026-09-21; CTR-17): judgement_record before modification, so
    # T-CON-06 judgement_record_id (frozen once the row leaves DRAFT) is inserted, never fixed up.
    "judgement_record",
    "modification",
    "event_submission",
    "contract_event",
    "combination_group_member",
    "obligation",
    "contract_source_link",
    "contract_hold",
    "estimate",
    "estimate_version",
    "policy_override",
    "manual_adjustment",
    "migration_batch",
    "migrated_legacy_row",
    "migration_population_version",
    "migration_population_obligation",
    "period_state",
    "period_state_transition",
    "period_lock",
)

# Reference columns whose name does not spell their target table.
ALIASES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "population_version_id": "migration_population_version",  # T-MIG-05 → T-MIG-04 (rev 1.60)
        "payload_migration_batch_id": "migration_batch",  # T-MIG-04: a REAL reference (rev 1.60)
        "calendar_id": "fiscal_calendar",
        "parent_entity_id": "legal_entity",
        "entity_id": "legal_entity",
        "contracting_entity_id": "legal_entity",
        "first_period_id": "period",
        "parent_value_id": "dimension_value",
        "parent_customer_id": "customer",
        "default_pob_template_id": "pob_template",
        "bundle_product_id": "product",
        "component_product_id": "product",
        "revenue_gl_account_id": "gl_account",
        "user_id": "app_user",
        "membership_id": "tenant_membership",
        "owner_role_id": "role",
        "required_role_id": "role",
        "mapping_profile_id": "import_mapping_profile",
        "aggregated_into_row_id": "import_row",
        "latest_computation_id": "contract_computation",
        "head_computation_id": "contract_computation",
        "renewal_of_contract_id": "contract",
        "join_event_id": "contract_event",
        "leave_event_id": "contract_event",
        "created_by_event_id": "contract_event",
        "applied_event_id": "contract_event",
        "sandbox_tenant_id": "tenant",  # T-MIG-01: the source's replay sandbox (SHARED tenant row)
        "reconciliation_report_run_id": "report_run",  # T-MIG-01
        "released_event_id": "contract_event",
        "supersedes_event_id": "contract_event",
        "parent_obligation_id": "obligation",
        "regrouped_from_obligation_id": "obligation",
        "routing_rule_set_version_id": "rule_set_version",
        "auto_rule_set_version_id": "rule_set_version",
        "routing_rule_id": "rule",
        "auto_rule_id": "rule",
        "delegation_id": "approval_delegation",
        "current_lock_id": "period_lock",
        "previous_lock_id": "period_lock",
        "draft_ssp_book_version_id": "ssp_book_version",
    }
)
# ``*_id`` columns that name no row of another table: principals, external identifiers, request
# correlation ids and polymorphic subjects.
# Ruling D-98 candidate 106: every UUID-element array of a copied table declares its element
# target here (or is a NON_REFERENCE); the scanner refuses an undeclared one. Export applies the
# scalar rule per element, in order: kept when the target row is in the copied set, dropped and
# counted (manifest ``array_drops``) when the target is REGENERATED or cut, refused when absent.
ARRAY_REFERENCES: Final[Mapping[tuple[str, str], str]] = MappingProxyType(
    {
        ("gl_account", "entity_ids"): "legal_entity",
        ("role_assignment", "entity_ids"): "legal_entity",
        ("approval_request", "entity_ids"): "legal_entity",  # T-PLT-17 rev 1.104 (R-25)
        ("event_submission", "applied_event_ids"): "contract_event",
        ("estimate_version", "applied_event_ids"): "contract_event",
        ("contract_event", "obligation_ids"): "obligation",
        ("estimate", "target_obligation_ids"): "obligation",
        ("migration_batch", "import_upload_ids"): "import_upload",  # T-MIG-01 REPLAY order
        # T-IMP-02 (04 rev 1.107; R-29): the legal entities an upload's rows name
        ("import_upload", "named_entity_ids"): "legal_entity",
        # T-REF-32 (04 rev 1.277; item SSP-ENTITY-SCOPE-1): the entities a calculator run read
        ("ssp_calculator_run", "entity_ids"): "legal_entity",
    }
)


@dataclass(frozen=True, slots=True)
class ScopeRule:
    """Ruling D-98 candidate 106a: an array reference whose emptiness means *all* targets. A
    partial cut keeps the remaining non-empty scope (the excluded targets do not exist in the
    copy); a complete cut of a non-empty scope is a refusal — the copy never turns a restriction
    into universal applicability — and a paired flag is never flipped.

    ``every_element_required`` (supervisor ruling R-98) is the opposite reading of the same shape:
    a *requirement* array, which a reader covers only with EVERY element (04 T-IMP-02
    ``named_entity_ids``: ``domain.imports.scope.visible``). There a dropped element would remove
    a requirement and widen who reads the copy, so a set that loses any element to the cut is not
    resolved in the copy: the column is exported NULL, which only an all-entities scope reads —
    for a partial and for a complete cut alike, and without a refusal. The cut elements are
    counted like every dropped element."""

    empty_means_all: bool
    paired_flag: str | None = None  # a boolean column the database CHECKs against emptiness
    every_element_required: bool = False  # a cut element makes the set NULL, never a subset


SCOPE_ARRAYS: Final[Mapping[tuple[str, str], ScopeRule]] = MappingProxyType(
    {
        ("gl_account", "entity_ids"): ScopeRule(empty_means_all=True),  # 04 T-REF-13
        ("role_assignment", "entity_ids"): ScopeRule(  # 04 T-PLT-10; 0007_roles CHECK
            empty_means_all=True, paired_flag="is_all_entities"
        ),
        # 04 T-PLT-17 rev 1.104 (R-25): the entities a decision must cover. An emptied set would
        # read as a tenant-level request that any holder decides, so a complete cut refuses and a
        # partial cut keeps the entities that exist in the copy; ``is_all_entities`` is not the
        # emptiness flag of this array (0086 CHECK), so nothing is paired.
        ("approval_request", "entity_ids"): ScopeRule(empty_means_all=True),
        # 04 T-IMP-02: an EMPTY set is a tenant-level upload, readable by every holder of the
        # route permission, and a reader of a named set covers every element of it — so a cut
        # neither empties nor shortens a named set: it leaves it unresolved (ruling R-98)
        ("import_upload", "named_entity_ids"): ScopeRule(
            empty_means_all=True, every_element_required=True
        ),
        # 04 T-REF-32 (rev 1.277; item SSP-ENTITY-SCOPE-1): a run is read by a reader whose
        # scope covers EVERY entity its provider read, and NULL is a run of every entity — a
        # requirement set, as the upload's (ruling R-98): one that lost an element is exported
        # NULL, read by an all-entities scope alone. The set is never empty (its CHECK). None
        # is lost in practice: the set is written at INSERT and the run is cut by
        # ``created_at``, as its entities are.
        ("ssp_calculator_run", "entity_ids"): ScopeRule(
            empty_means_all=False, every_element_required=True
        ),
    }
)
SCOPE_UNREPRESENTABLE: Final = "SNAPSHOT_SCOPE_UNREPRESENTABLE"
NON_REFERENCES: Final = frozenset(
    {
        "regroup_id",  # T-CON-06: the pairing token of a regroup after posting, not a row
        "applied_invoice_external_ids",  # T-SRC: external invoice identifiers (text array)
        "tax_id",
        "external_id",
        "subject_id",
        "target_id",
        "request_id",
        "source_ref_id",
        "reviewer_id",
        "preparer_id",
        "approver_id",
        "on_behalf_of_id",
        "external_order_id",
        "customer_external_id",
        "contract_external_id",  # T-MIG-02 / T-MIG-03: the legacy contract's external id
        "record_unique_id",  # T-MIG-02: the legacy row's own identifier
        "source_rowid",  # T-MIG-02: the legacy rowid (no *_id suffix; listed for clarity)
        "parent_order_external_id",
        "line_external_id",
        "bundle_parent_line_external_id",
        "external_invoice_id",
        "credited_invoice_external_id",
        "order_line_external_id",
        "external_usage_id",
        "external_payment_id",
    }
)
_SELF_REFERENCE_COLUMNS: Final = frozenset({"supersedes_version_id", "supersedes_id"})
# Identity TOKENS (D-98 candidate 106 exclusion; 04 rev 1.60, lane F-LMG): ``*_id`` and ``*_ids``
# columns of a copied table whose values name rows that no longer exist — the opening-balance
# import's dry run rolls its engine rows back and captures their identities as evidence. They are
# copied as opaque values: never resolved to a target, never nulled, never cut element-wise.
# Keyed by (table, column) because the same column NAMES are real references elsewhere.
TOKEN_COLUMNS: Final = frozenset(
    {
        # T-MIG-01: the import's durable operation identity (rev 1.60)
        ("migration_batch", "capture_operation_id"),
        # T-MIG-04: the dry run's version / group / computation / trace / event identities and the
        # expected obligation-version ids; payload_migration_batch_id and engine_release_id are
        # NOT tokens (a real reference to migration_batch; a SHARED engine_release key)
        ("migration_population_version", "contract_version_id"),
        ("migration_population_version", "combination_group_id"),
        ("migration_population_version", "contract_computation_id"),
        ("migration_population_version", "opening_event_id"),
        ("migration_population_version", "obligation_version_ids"),
        ("migration_population_version", "capture_operation_id"),
        ("migration_population_version", "calc_trace_id"),
        # T-MIG-05
        ("migration_population_obligation", "capture_operation_id"),
        ("migration_population_obligation", "contract_version_id"),
        ("migration_population_obligation", "obligation_version_id"),
        ("migration_population_obligation", "contract_id"),
    }
)
_FILE_SUFFIX: Final = "_file_id"
_FILE_OBJECT_COLUMN: Final = "file_object_id"
# EXCLUDED columns of copied tables, nulled on export (ruling Q-5: a production invitation token
# would otherwise be accepted by the sandbox copy of an INVITED membership).
# ``scan_excluded_columns`` finds every ``*_token_sha256`` / secret-derived column by name or
# LargeBinary type; a found column
# that is not declared here fails the inventory (the drift guard forces a decision).
EXCLUDED_COLUMNS: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {"tenant_membership": frozenset({"invitation_token_sha256"})}
)
_EXCLUDED_NAME: Final = re.compile(
    r"(_token_sha256$|_ciphertext$|token|secret|password|recovery_code)"
)
# What a copy carries of an OPEN INVITATION (item SBX-COPY-OPEN-INVITATION-1; 05 SBX-03 rev
# 1.205; 04 T-PLT-07 rev 1.293). The token is nulled above, and the table's two checks tie the
# status, the token and the expiry together — ``(status = 'INVITED') = (token IS NOT NULL)`` and
# ``(token IS NULL) = (expiry IS NULL)`` — so an INVITED row cannot be carried as it is: the load
# of a workspace with one open invitation failed. The copy carries it as the product leaves an
# invitation withdrawn before acceptance (``users.remove_membership``): REMOVED, token and expiry
# null, ``removed_at`` the snapshot's ``known_at``; and its role assignments still in force
# revoked at ``known_at`` by SYSTEM, as a removal leaves them. Nobody becomes a member of a copy
# by an invitation meant for production, every row that names the membership still resolves, and
# the person is invited again in the copy like anyone removed. One rule, the export's
# (``close_open_invitations``): the load does nothing of its own.
OPEN_INVITATION: Final = "INVITED"  # E-78
CLOSED_INVITATION: Final[Mapping[str, Any]] = MappingProxyType(
    {"status": "REMOVED", "invitation_token_sha256": None, "invitation_expires_at": None}
)
CLOSED_INVITATION_AT: Final = "removed_at"
REVOKED_WITH_INVITATION: Final[Mapping[str, Any]] = MappingProxyType(
    {"revoked_by": None, "revoked_by_kind": "SYSTEM"}
)
REVOKED_WITH_INVITATION_AT: Final = "revoked_at"


class CutoffKind(StrEnum):
    """How a dataset is cut at ``known_at`` (ruling Q-6)."""

    TIMESTAMP = "timestamp"  # facts and events: column ≤ known_at
    EFFECTIVE = "effective"  # configuration and versions: effective column ≤ known_at
    PARENT = "parent"  # children of a version or request: follow the parent, no own cutoff
    NONE = "none"  # whole tables: period definitions, counters, period_state


@dataclass(frozen=True, slots=True)
class CutoffRule:
    kind: CutoffKind
    column: str | None = None
    # EFFECTIVE with a NULL effective value (DRAFT, TESTED): the creation timestamp decides.
    fallback: str | None = None


_TS: Final = CutoffKind.TIMESTAMP
_EF: Final = CutoffKind.EFFECTIVE
_CREATED: Final = CutoffRule(_TS, "created_at")
_VERSION: Final = CutoffRule(_EF, "effective_from", "created_at")
_PARENT: Final = CutoffRule(CutoffKind.PARENT)
_WHOLE: Final = CutoffRule(CutoffKind.NONE)
# The per-table cutoff (ruling Q-6), one entry per dataset of LOAD_ORDER.
CUTOFF_RULES: Final[Mapping[str, CutoffRule]] = MappingProxyType(
    {
        # configuration: master data by existence at known_at (Q-8a), versions by effectivity
        "fiscal_calendar": _CREATED,
        "period": _WHOLE,  # a calendar is copied whole (DB-05 contiguity)
        "legal_entity": _CREATED,
        "book": _CREATED,
        "entity_book": _CREATED,
        "tenant_currency": _CREATED,
        "gl_account": _CREATED,
        "dimension_definition": _CREATED,
        "dimension_value": _CREATED,
        "related_party_group": _CREATED,
        "pob_template": _CREATED,
        "pob_template_version": _VERSION,
        "product": _CREATED,
        "product_bundle_component": CutoffRule(_EF, "valid_from"),
        "role": _CREATED,
        "role_permission": _PARENT,
        "tenant_membership": _CREATED,
        "sod_rule": _VERSION,
        "sod_exception": CutoffRule(_EF, "valid_from"),
        "role_assignment": CutoffRule(_EF, "valid_from"),
        "rule_set": _CREATED,
        "rule_set_version": _VERSION,
        "rule": _PARENT,
        "rule_test_case": _PARENT,
        "account_mapping_version": _VERSION,
        "account_mapping_rule": _PARENT,
        "registry_version": _VERSION,
        "numbering_series": _WHOLE,  # counters continue from the source (ruling Q-1)
        "close_checklist_template": _CREATED,
        "import_mapping_profile": _VERSION,
        "fx_rate_set": _CREATED,
        "fx_rate_set_version": _VERSION,
        "fx_rate": CutoffRule(_EF, "effective_date"),
        "ssp_book": _CREATED,
        "ssp_book_version": _VERSION,
        "ssp_entry": _PARENT,
        "ssp_range": _PARENT,
        # facts and events by their timestamp (SBX-03 names contract_event.recorded_at)
        "file_object": _CREATED,
        "file_attachment": _CREATED,
        "import_upload": _CREATED,
        "import_row": _CREATED,
        "import_row_lineage": _CREATED,
        "migration_batch": _CREATED,
        "migrated_legacy_row": _CREATED,
        "migration_population_version": _CREATED,
        "migration_population_obligation": _CREATED,
        "customer": _CREATED,
        "ssp_calculator_run": _CREATED,
        "ssp_calculator_result": _PARENT,
        "ssp_calculator_exclusion": _CREATED,
        "source_record": _CREATED,
        "source_order": _CREATED,
        "source_order_line": _CREATED,
        "source_invoice": _CREATED,
        "source_invoice_line": _CREATED,
        "source_usage": _CREATED,
        "source_payment": _CREATED,
        "source_match": _CREATED,
        "combination_group": _CREATED,
        "contract": _CREATED,
        "modification": _CREATED,
        "event_submission": _CREATED,
        "contract_event": CutoffRule(_TS, "recorded_at"),
        "combination_group_member": _CREATED,
        "obligation": _CREATED,
        "contract_source_link": _CREATED,
        "contract_hold": CutoffRule(_TS, "applied_at"),
        "estimate": _CREATED,
        "estimate_version": _CREATED,
        "judgement_record": _CREATED,
        "policy_override": _CREATED,
        "manual_adjustment": _CREATED,
        "approval_request": _CREATED,
        "approval_step": _PARENT,
        "approval_decision": CutoffRule(_TS, "decided_at"),
        # replay reference: the events by their timestamp, the state rows whole
        "period_state": _WHOLE,
        "period_state_transition": _CREATED,
        "period_lock": _CREATED,
    }
)
# Effectivity columns a configuration table may carry; such a table needs an EFFECTIVE rule.
_EFFECTIVITY_COLUMNS: Final = frozenset({"effective_from", "valid_from"})


# The step of ``load_plan`` that rebuilds a reference nulled on export; None: it stays NULL in the
# sandbox, for the recorded reason (ruling on finding 2).
@dataclass(frozen=True, slots=True)
class Finalization:
    """SBX-04 governed restoration of a finalized row whose dependants a LIVE insertion guard admits
    only while the row is in an initial status (DB-10, 0013: an ``approval_decision`` inserts only
    while its request is PENDING and its step ACTIVE). The loader inserts such a row in ``initial``
    with its exported ``held`` set-once columns NULL, loads the guarded dependants under the guard,
    and then applies the exported status and the held columns through the DB-03 kernel
    (``transitions.apply``, the pair ``initial → exported`` validated) once the dataset ``after``
    has loaded — the final evidence and every identity preserved, no approval fabricated, no
    decision omitted, no guard weakened (Codex production-20260921-1713 §3 R3; D-98 137
    amendment 4). ``when`` names a column that must be non-NULL for the hold to apply (a step
    that was never ACTIVE has no decisions and is inserted as exported). ``kernel`` is False for
    a table the DB-03 registry does not govern (``tenant_membership``: an SC-M status the platform
    domain writes with a plain UPDATE, ``users._set_status``); its finalization is that UPDATE of
    the status and the held columns — an IM-M row, so DB-02 ``tg_touch`` stamps the sandbox's own
    ``updated_at`` (the finalization instant) and ``row_version`` (source + 1): a restored
    membership equals the source on every column except ``tenant_id``, ``updated_at`` and
    ``row_version``, never a bypassed trigger (Codex production-20260921-1757 §1 MEMBERSHIP-1 and
    1824 §1 MEMBERSHIP-STAMPS-1; D-98 137 amendments 6 and 7; 05 SBX-04 rev 1.20 in place)."""

    status_column: str
    initial: str
    final: frozenset[str]
    held: tuple[str, ...]
    after: str
    when: str | None = None
    kernel: bool = True


FINALIZATIONS: Final[Mapping[str, Finalization]] = MappingProxyType(
    {
        "approval_step": Finalization(
            "status",
            "ACTIVE",
            frozenset({"APPROVED", "REJECTED", "VOIDED"}),
            ("completed_at",),
            "approval_decision",
            when="activated_at",
        ),
        "approval_request": Finalization(
            "status",
            "PENDING",
            frozenset({"APPROVED", "REJECTED", "VOIDED", "WITHDRAWN"}),
            ("decided_at", "voided_at", "void_reason"),
            "approval_decision",
        ),
        # MEMBERSHIP-1: the 0013 decision guard requires the approver's CURRENT membership ACTIVE,
        # so a copied membership that ended SUSPENDED / REMOVED loads in its activation state,
        # the approval graphs load under the live guards, and its later status is applied after —
        # final state, ids, hashes, MFA and times preserved (updated_at / row_version carry the
        # sandbox's DB-02 stamps); never a permanent reactivation, not even behind a refusal.
        "tenant_membership": Finalization(
            "status",
            "ACTIVE",
            frozenset({"SUSPENDED", "REMOVED"}),
            ("removed_at",),
            "approval_decision",
            when="activated_at",
            kernel=False,
        ),
    }
)
# Steps finalize before their request (the engine's order); memberships after every graph.
FINALIZATION_ORDER: Final = ("approval_step", "approval_request", "tenant_membership")


@dataclass(frozen=True, slots=True)
class Graph:
    """SBX-04 restoration of WHOLE historical graphs, root row by root row (Codex
    production-20260921-1739 §1 APPROVAL-UNIQUE-1; D-98 137 amendment 5). The root dataset and its
    dependants load one root at a time in ``order`` — chronological, so two completed requests of
    one subject are never PENDING together (``ux_approval_request__pending_subject``) — each
    graph finalized (``FINALIZATIONS``) before the next root inserts; a legitimately current
    PENDING request, if one exists, is last by that order. Original ids, hashes, subjects,
    timestamps and final states are preserved; the live guards apply to every insert."""

    root: str
    dependants: tuple[tuple[str, str], ...]  # (dataset, the column naming the root)
    order: tuple[str, ...]  # the finalized roots' chronological order, then their id
    dependant_order: Mapping[str, tuple[str, ...]]
    # The explicit partition (Codex 1757 §2): every finalized root of a subject in ``order``, then
    # the one legitimately current root in this (column, value) LAST — regardless of its
    # ``submitted_at``; equal ``submitted_at`` values fall back to the id.
    current: tuple[str, str] | None = ("status", "PENDING")


GRAPHS: Final[Mapping[str, Graph]] = MappingProxyType(
    {
        "approval_request": Graph(
            "approval_request",
            (
                ("approval_step", "approval_request_id"),
                ("approval_decision", "approval_request_id"),
            ),
            ("submitted_at", "id"),
            MappingProxyType(
                {"approval_step": ("step_no", "id"), "approval_decision": ("decided_at", "id")}
            ),
        ),
    }
)


@dataclass(frozen=True, slots=True)
class Component:
    """SBX-04 restoration of tables whose references form a cycle that no table order breaks
    (05 SBX-04 rev 1.50; supervisor ruling R-43 (b)). Every edge of the cycle is frozen at insert
    or NOT NULL — an IM-A event names an estimate version, whose estimate names an obligation,
    which names the event that created it — so neither LOAD_ORDER nor the fixup step can restore
    it; but no cycle exists between ROWS (an event names only what existed when it was appended).
    The component's tables therefore load as ONE unit at the position of its first table, their
    rows in one order in which every row follows the rows it names (``component_order``), in one
    copy-phase transaction. ``ordered`` is the table whose given row order is kept exactly (the
    stream, in source ``record_seq`` order — DB-08 re-stamps in insertion order). ``deferred``
    names the references that stay with the fixup step: the updatable back-edge of a two-row
    cycle (an adjustment names the event that applied it, and that event names the adjustment).
    Ordering only: no guard, grant or trigger changes."""

    name: str  # the copy-phase transaction is ``load-<name>``
    tables: tuple[str, ...]  # in LOAD_ORDER; the component loads at the first one
    ordered: str
    deferred: frozenset[tuple[str, str]] = frozenset()  # (table, column)


COMPONENTS: Final[Mapping[str, Component]] = MappingProxyType(
    {
        "contract_event": Component(
            "stream",
            ("contract_event", "obligation", "estimate", "estimate_version", "manual_adjustment"),
            "contract_event",
            frozenset({("manual_adjustment", "applied_event_id")}),
        ),
    }
)
_COMPONENT_OF: Final[Mapping[str, Component]] = MappingProxyType(
    {table: component for component in COMPONENTS.values() for table in component.tables}
)


REBUILD_STEPS: Final[Mapping[tuple[str, str], str | None]] = MappingProxyType(
    {
        ("contract", "latest_computation_id"): "recompute",
        ("combination_group", "head_computation_id"): "recompute",
        ("manual_adjustment", "subledger_posting_id"): "recompute",
        # delegations are REGENERATED; approver_id and on_behalf_of_id stay on the row (Q-8c)
        ("approval_decision", "delegation_id"): None,
        # replayed transitions carry no close run; the sandbox's own runs create new ones
        ("period_state_transition", "close_run_id"): None,
        # T-MIG-01: the source's replay sandbox is not the copy's; a new legacy replay creates its
        # own (05 SBX-10) — the SHARED tenant identity is nulled, not listed as a dependency
        ("migration_batch", "sandbox_tenant_id"): None,
        # T-MIG-01: the reconciliation, its report run and the job are the source's REGENERATED
        # artefacts; a later replay in the copy produces its own (05 SBX-10)
        ("migration_batch", "reconciliation_id"): None,
        ("migration_batch", "reconciliation_report_run_id"): None,
        ("migration_batch", "job_id"): None,
        # PENDING targets: sync_run (F-DIN) and portfolio (F-CTR); modification landed with CTR-17
        # (D-98 140), so contract_event.modification_id resolves to the copied row of a NATIVE
        # event; a legacy-template CONTRACT_AMENDED stores NULL there from 04 rev 1.80 on (its
        # synthetic id is in the payload; MAIN DEFECT 2, (c)-QUALIFIED) and exports null
        ("source_record", "sync_run_id"): None,
        ("contract_event", "sync_run_id"): None,
        ("contract", "portfolio_id"): None,
        ("estimate", "portfolio_id"): None,
        # operational job rows of the source are not rebuilt
        ("import_upload", "job_id"): None,
        ("ssp_calculator_run", "job_id"): None,
        # polymorphic subjects of a REGENERATED class (ruling D-98 candidate 34): the row travels,
        # its subject_id stays NULL
        ("judgement_record", "subject_id"): None,
        ("rule_test_case", "subject_id"): None,
    }
)
# Polymorphic ``subject_type`` / ``subject_id`` columns of copied datasets (ruling D-98 candidate
# 34; the 04 CHECK literals of T-PLT-30, judgement_record and rule_test_case, literal = table). A
# PENDING or unsupported subject type refuses the export; a REGENERATED subject's attachment is
# excluded and a REGENERATED subject's judgement record or test case travels with ``subject_id``
# nulled (REBUILD_STEPS: stays NULL); a copied subject is kept as is.
POLYMORPHIC_SUBJECTS: Final[Mapping[str, Mapping[str, str]]] = MappingProxyType(
    {
        "file_attachment": MappingProxyType(
            {
                literal: literal
                for literal in (
                    "contract",
                    "modification",
                    "estimate_version",
                    "ssp_book_version",
                    "judgement_record",
                    "manual_adjustment",
                    "reconciliation",
                    "sod_exception",
                    "approval_request",
                    "exception_item",
                    "contract_event",
                    "event_submission",
                )
            }
        ),
        "judgement_record": MappingProxyType(
            {
                literal: literal
                for literal in (
                    "contract",
                    "obligation",
                    "combination_group",
                    "modification",
                    "estimate_version",
                    "product",
                    "registry_version",
                    "migration_batch",
                )
            }
        ),
        "rule_test_case": MappingProxyType(
            {
                literal: literal
                for literal in (
                    "rule_set_version",
                    "pob_template_version",
                    "account_mapping_version",
                    "registry_version",
                )
            }
        ),
    }
)
# The polymorphic columns nulled row by row (a REGENERATED subject) rather than per column.
POLYMORPHIC_SUBJECT_COLUMNS: Final = frozenset(
    {("judgement_record", "subject_id"), ("rule_test_case", "subject_id")}
)


@dataclass(frozen=True, slots=True)
class SharedKey:
    """Columns of a copied table whose values are identities of a SHARED table (ruling Q-7: the
    manifest records the shared identities the copy depends on). ARRAY values are flattened;
    several columns form one composite value joined by ``|``."""

    shared_table: str
    table: str
    columns: tuple[str, ...]


def _key(shared: str, table: str, *columns: str) -> SharedKey:
    return SharedKey(shared, table, columns)


SHARED_KEYS: Final[tuple[SharedKey, ...]] = (
    _key("app_user", "tenant_membership", "user_id"),
    # T-MIG-04 (rev 1.60): the producing computation's engine release (nullable)
    _key("engine_release", "migration_population_version", "engine_release_id"),
    _key("currency", "legal_entity", "functional_currency"),
    _key("currency", "tenant_currency", "currency_code"),
    _key("currency", "fx_rate", "base_currency"),
    _key("currency", "fx_rate", "quote_currency"),
    _key("currency", "ssp_calculator_result", "currency"),
    _key("currency", "ssp_book", "currency"),
    _key("currency", "ssp_entry", "currency"),
    _key("currency", "source_order", "transaction_currency"),
    _key("currency", "source_invoice", "currency"),
    _key("currency", "source_usage", "currency"),
    _key("currency", "source_payment", "currency"),
    _key("currency", "combination_group", "transaction_currency"),
    _key("currency", "contract", "transaction_currency"),
    _key("currency", "modification", "currency"),
    _key("currency", "estimate_version", "currency"),
    _key("currency", "manual_adjustment", "currency"),
    _key("currency", "approval_request", "amount_currency"),
    _key("permission", "role_permission", "permission_code"),
    _key("permission", "approval_step", "required_permission"),
    _key("permission", "sod_rule", "function_a_permissions"),
    _key("permission", "sod_rule", "function_b_permissions"),
    _key("import_template", "import_mapping_profile", "template_code"),
    _key("import_template", "import_upload", "template_code", "template_version"),
    _key("registry_parameter", "policy_override", "policy_key"),
)
# Row order of copied tables that do not sort by their primary key (streams by record_seq, SBX-04).
_ORDER_OVERRIDES: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {"contract_event": ("record_seq", "id")}
)
_TENANT_ID: Final = "tenant_id"
_CREATED_AT: Final = "created_at"
_ID: Final = "id"
_IP_TYPES: Final = (
    ipaddress.IPv4Address,
    ipaddress.IPv6Address,
    ipaddress.IPv4Network,
    ipaddress.IPv6Network,
    ipaddress.IPv4Interface,
    ipaddress.IPv6Interface,
)


@dataclass(frozen=True, slots=True)
class Reference:
    """One ``*_id`` column of a copied table and the table it names; ``array`` marks a UUID-array
    column whose elements name the target (ruling D-98 candidate 106): filtered per element,
    never nulled, never a parent-first constraint (the database declares no FK on arrays)."""

    table: str
    column: str
    target: str
    nullable: bool
    array: bool = False

    @property
    def self_reference(self) -> bool:
        return self.table == self.target


@dataclass(frozen=True, slots=True)
class Dataset:
    """One copied table: its JSONL file in the snapshot."""

    name: str
    snapshot_class: SnapshotClass
    category: Category
    columns: tuple[str, ...]  # the 04 columns, in table order
    cutoff: CutoffRule  # the per-table known_at rule (ruling Q-6)
    order_by: tuple[str, ...]  # the deterministic row order (primary key without tenant_id)
    load_position: int  # index in LOAD_ORDER
    deferred: tuple[str, ...]  # nullable references to a LATER table (NULL, then the fixup step)
    nulled_on_export: tuple[str, ...]  # references to regenerated/pending/secret targets, excluded
    # nullable references to the SAME table: never deferred — the rows load referenced-first
    # (``referenced_first``), so the value is inserted with its row
    self_references: tuple[str, ...] = ()
    # references to ANOTHER table of the dataset's component (``COMPONENTS``): never deferred —
    # the component's rows load in one order in which the referenced row comes first
    row_references: tuple[str, ...] = ()

    @property
    def cutoff_column(self) -> str | None:
        return self.cutoff.column


@dataclass(frozen=True, slots=True)
class Exclusion:
    """One table the snapshot never carries, with its class and SBX-03 reason."""

    name: str
    category: Category
    snapshot_class: SnapshotClass = SnapshotClass.REGENERATED
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Inventory:
    """Every table of the model, classified once."""

    datasets: tuple[Dataset, ...]  # LOAD_ORDER
    exclusions: tuple[Exclusion, ...]  # by name
    references: tuple[Reference, ...]  # of the datasets, in LOAD_ORDER then column order
    pending: tuple[PendingTable, ...]  # by name

    def dataset(self, name: str) -> Dataset:
        for dataset in self.datasets:
            if dataset.name == name:
                return dataset
        raise KeyError(name)

    @property
    def names(self) -> frozenset[str]:
        return frozenset(dataset.name for dataset in self.datasets)

    @property
    def classes(self) -> Mapping[str, SnapshotClass]:
        classes = {dataset.name: dataset.snapshot_class for dataset in self.datasets}
        classes.update({item.name: item.snapshot_class for item in self.exclusions})
        return MappingProxyType(classes)


@dataclass(frozen=True, slots=True)
class Encoded:
    """The JSONL bytes of one dataset with their T-PLT-29 hash and row count."""

    name: str
    content: bytes
    sha256: str
    row_count: int


@dataclass(frozen=True, slots=True)
class Stamp:
    """The ``known_at`` stamp of a snapshot (T-PLT-34 ``known_at``, ``purpose``; T-PLT-01
    ``source_tenant_id``, ``source_known_at``)."""

    source_tenant_id: UUID
    known_at: datetime
    purpose: str

    def __post_init__(self) -> None:
        if self.purpose not in PURPOSES:
            raise ValueError(f"unknown snapshot purpose {self.purpose!r} (T-PLT-34)")
        if self.known_at.tzinfo is None or self.known_at.utcoffset() is None:
            raise ValueError("known_at is timezone-aware (DG-KRN-CAN-08)")


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    name: str
    sha256: str
    row_count: int


@dataclass(frozen=True, slots=True)
class FileRetention:
    """The retention state of one copied ``file_object`` row at snapshot time (T-PLT-29)."""

    id: UUID
    sha256: str
    purpose: str
    retention_until: date | None
    legal_hold: bool


@dataclass(frozen=True, slots=True)
class Retention:
    """Ruling Q-4 (supervisor; requires human confirmation before production use): the snapshot
    inherits the source's retention state; every file it carries is listed so a source shred can
    locate every copy."""

    files: tuple[FileRetention, ...]  # by id
    source_legal_hold: bool  # any listed file under legal hold at snapshot time
    families: Mapping[str, str] = RETENTION_FAMILIES  # P8 catalogue literal per copied family
    families_status: str = RETENTION_FAMILIES_STATUS  # PROPOSED, or the confirming version (I-5)


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """The tenant's confirmed retention families (slice I-5): the value of
    ``platform.snapshot_retention_families`` and the registry version that confirmed it."""

    families: Mapping[str, str]
    source: str  # "registry version <id> (TENANT)"


class UnconfirmedRetention(ValueError):
    """The in-force retention version carries no named human approval (D-98 candidate 86)."""


@dataclass(frozen=True, slots=True)
class RetentionConfirmation:
    """The human approval that confirms a retention version: the approver (an ``app_user`` id, never
    a name or e-mail — PRV-01) and the instant of the latest human APPROVE decision."""

    approver_id: UUID
    decided_at: datetime


def retention_confirmation(
    version: Mapping[str, Any], decisions: Iterable[Mapping[str, Any]]
) -> RetentionConfirmation:
    """Ruling D-98 candidate 86: the confirming registry version is PUBLISHED by someone
    (``published_by`` non-null), references its approval request, and that request holds at least
    one ``APPROVE`` decision by a ``USER`` with an approver id and no auto-approval rule — an
    ``AUTO_APPROVE`` decision never counts. Anything else raises :class:`UnconfirmedRetention`
    with the reason."""
    if version.get("published_by") is None:
        raise UnconfirmedRetention("published_by is NULL: no auto-publish path confirms retention")
    request_id = version.get("approval_request_id")
    if request_id is None:
        raise UnconfirmedRetention("approval_request_id is NULL: the version was never approved")
    human: list[Mapping[str, Any]] = []
    seen_auto = False
    for decision in decisions:
        if decision.get("approval_request_id") not in (None, request_id):
            continue
        if decision.get("decision") == "AUTO_APPROVE" or decision.get("auto_rule_id") is not None:
            seen_auto = True
            continue
        if decision.get("decision") != "APPROVE":
            continue
        if decision.get("approver_kind") != "USER" or decision.get("approver_id") is None:
            raise UnconfirmedRetention(
                "an APPROVE decision without a USER approver does not confirm retention"
            )
        human.append(decision)
    if not human:
        if seen_auto:
            raise UnconfirmedRetention(
                "the version was AUTO_APPROVE-d: AUTO_APPROVAL is disallowed for "
                f"{RETENTION_PARAMETER}"
            )
        raise UnconfirmedRetention("no APPROVE decision by a named human approver")
    latest = max(human, key=lambda d: d["decided_at"])
    return RetentionConfirmation(UUID(str(latest["approver_id"])), latest["decided_at"])


def confirmation_source(
    version: Mapping[str, Any],
    confirmed: RetentionConfirmation,
    *,
    in_force: Mapping[str, Any] | None = None,
) -> str:
    """The manifest wording ruled by D-98 candidate 86: the version that confirmed the retention
    families and its approver. ``in_force`` is the version in force that holds them: when a
    later version of the key carries the families forward (04 T-PLT-32 "Whole value set", rev
    1.183), the manifest names it beside the confirming one."""
    source = (
        f"registry version {version['id']} approved by {confirmed.approver_id} "
        f"at {confirmed.decided_at.isoformat()}"
    )
    if in_force is None or in_force["id"] == version["id"]:
        return source
    return f"{source}; in force as registry version {in_force['id']}"


def retention_policy_of(value: Any, source: str) -> RetentionPolicy | None:
    """The policy a resolved parameter value denotes: ``None`` for the refusing default (``{}`` or
    no value); a full mapping of the five families to P8 literals is a policy; anything else
    refuses (``ValueError``) — never a silent fallback to the PROPOSED families."""
    if value is None or value == {}:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"{RETENTION_PARAMETER}: the value is an object of family → literal")
    unknown = sorted(set(value) - set(RETENTION_FAMILIES))
    missing = sorted(set(RETENTION_FAMILIES) - set(value))
    if unknown or missing:
        raise ValueError(
            f"{RETENTION_PARAMETER}: unknown family {unknown}, missing family {missing}; the "
            f"copied families are {sorted(RETENTION_FAMILIES)}"
        )
    bad = sorted(family for family, literal in value.items() if literal not in RETENTION_LITERALS)
    if bad:
        raise ValueError(
            f"{RETENTION_PARAMETER}: retention literal outside {list(RETENTION_LITERALS)} for {bad}"
        )
    return RetentionPolicy(
        MappingProxyType({family: str(value[family]) for family in RETENTION_FAMILIES}), source
    )


@dataclass(frozen=True, slots=True)
class SharedRef:
    """The identities of one SHARED table the snapshot depends on (ruling Q-7)."""

    table: str
    values: tuple[str, ...]  # sorted, distinct


@dataclass(frozen=True, slots=True)
class Shared:
    refs: tuple[SharedRef, ...]  # by table
    engine_release: str  # the source's stamped engine release (05 REL-03), supplied by the exporter

    def __post_init__(self) -> None:
        # F-SNP-I2-R2: a shared block without the source's release is refused, never formatted.
        if not self.engine_release:
            raise ValueError("the shared block requires the source's engine release")


@dataclass(frozen=True, slots=True)
class Manifest:
    """The JSON manifest of T-PLT-34: one entry per dataset file, the stamp, the exclusions and
    the retention block."""

    stamp: Stamp
    entries: tuple[ManifestEntry, ...]  # LOAD_ORDER
    exclusions: tuple[Exclusion, ...]
    retention: Retention | None = None
    shared: Shared | None = None
    format_version: int = MANIFEST_FORMAT_VERSION
    audit_history_carried: bool = False  # ruling Q-7 addition; always false (SBX-06)
    # D-98 candidate 106: array elements dropped on export, per "table.column" (always present)
    array_drops: Mapping[str, int] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class Step:
    """One step of a load or reset plan with the gates it needs and the tables it writes."""

    name: str
    description: str
    gates: tuple[str, ...]
    writes: tuple[str, ...]


def _tables(metadata: MetaData | None) -> Mapping[str, Any]:
    return {table.name: table for table in (metadata or model_metadata).tables.values()}


def references(metadata: MetaData | None = None) -> tuple[Reference, ...]:
    """Every ``*_id`` column of a copied table resolved to its target (by name, ``ALIASES`` or the
    file suffix) or declared in ``NON_REFERENCES``; an unresolved column or an unknown target is
    refused, so a new reference column forces a decision."""
    tables = _tables(metadata)
    known = set(tables) | set(PENDING)
    found: list[Reference] = []
    for name in LOAD_ORDER:
        table = tables.get(name)
        if table is None:
            continue
        for column in table.columns:
            label = str(column.name)
            if (name, label) in TOKEN_COLUMNS:
                continue  # an identity token, not a reference (D-98 candidate 106 exclusion)
            if isinstance(column.type, sa.ARRAY):
                is_uuid_array = isinstance(column.type.item_type, sa.Uuid)
                if not is_uuid_array and not label.endswith("_ids"):
                    continue  # text arrays (permission codes, dimension names, flags)
                if label in NON_REFERENCES:
                    continue
                array_target = ARRAY_REFERENCES.get((name, label))
                if array_target is None:
                    raise ValueError(
                        f"{name}.{label}: undeclared array reference; declare its element target "
                        "in ARRAY_REFERENCES or list it in NON_REFERENCES (D-98 candidate 106)"
                    )
                if array_target not in known:
                    raise ValueError(f"{name}.{label}: unknown target table {array_target!r}")
                found.append(Reference(name, label, array_target, bool(column.nullable), True))
                continue
            if not label.endswith("_id") or label in (_ID, _TENANT_ID):
                continue
            if label in NON_REFERENCES:
                continue
            if label in _SELF_REFERENCE_COLUMNS:
                target = name
            elif label == _FILE_OBJECT_COLUMN or label.endswith(_FILE_SUFFIX):
                target = "file_object"
            elif label in ALIASES:
                target = ALIASES[label]
            elif label[:-3] in known:
                target = label[:-3]
            else:
                raise ValueError(
                    f"{name}.{label}: unresolved reference column; add it to ALIASES or "
                    "NON_REFERENCES"
                )
            if target not in known:
                raise ValueError(f"{name}.{label}: unknown target table {target!r}")
            found.append(Reference(name, label, target, bool(column.nullable)))
    return tuple(found)


def scan_excluded_columns(metadata: MetaData | None = None) -> tuple[tuple[str, str], ...]:
    """Every column of a copied table that looks credential-derived (``*_token_sha256``,
    ``*_ciphertext``, ``token``, ``secret``, ``password``, ``recovery_code``) or is binary
    (ruling Q-5); ``inventory`` refuses any of them that ``EXCLUDED_COLUMNS`` does not declare."""
    tables = _tables(metadata)
    found: list[tuple[str, str]] = []
    for name in LOAD_ORDER:
        table = tables.get(name)
        if table is None:
            continue
        for column in table.columns:
            label = str(column.name)
            if _EXCLUDED_NAME.search(label) or isinstance(column.type, LargeBinary):
                found.append((name, label))
    return tuple(found)


def _class_of(name: str) -> SnapshotClass:
    if name in RULES:
        return RULES[name].snapshot_class
    if name in PENDING:
        return SnapshotClass.PENDING
    raise KeyError(name)


def parents(metadata: MetaData | None = None) -> Mapping[str, tuple[str, ...]]:
    """Per copied table, the copied tables that must load before it: the targets of its
    non-deferred references to other copied tables."""
    position = {name: index for index, name in enumerate(LOAD_ORDER)}
    result: dict[str, list[str]] = {}
    for reference in references(metadata):
        if reference.target not in position or reference.self_reference or reference.array:
            continue
        if position[reference.target] < position[reference.table]:
            targets = result.setdefault(reference.table, [])
            if reference.target not in targets:
                targets.append(reference.target)
    return MappingProxyType({name: tuple(targets) for name, targets in sorted(result.items())})


def inventory(metadata: MetaData | None = None) -> Inventory:
    """Classify every table of ``metadata`` (the 04 model by default) and resolve the references.

    Refuses: an unclassified table, a stale rule, a PENDING table that is present, a copied table
    whose class and reason family disagree, a NOT NULL reference whose target loads after its
    child or never loads, a binary column or an undeclared credential-like column in a copied
    table (ruling Q-1; SBX-03; PRV-06)."""
    tables = _tables(metadata)
    unclassified = sorted(set(tables) - set(RULES) - set(PENDING))
    stale = sorted(set(RULES) - set(tables))
    present = sorted(set(PENDING) & set(tables))
    if unclassified or stale or present:
        raise ValueError(
            f"snapshot inventory: unclassified tables {unclassified}; stale entries {stale}; "
            f"pending tables present {present}"
        )
    for name, rule in RULES.items():
        copied = rule.snapshot_class is SnapshotClass.COPIED
        if copied != (rule.category in COPIED_CATEGORIES):
            raise ValueError(f"snapshot inventory: {name} class and reason family disagree")
        replay = rule.snapshot_class is SnapshotClass.REPLAY_REFERENCE
        if replay != (rule.category is Category.REPLAY_REFERENCE):
            raise ValueError(f"snapshot inventory: {name} class and reason family disagree")
        if not rule.reason:
            raise ValueError(f"snapshot inventory: {name} has no reason")
    copied_names = [n for n, r in RULES.items() if r.snapshot_class in _COPIED_CLASSES]
    misplaced = sorted(set(copied_names) ^ set(LOAD_ORDER))
    if misplaced:
        raise ValueError(f"snapshot inventory: LOAD_ORDER and the copied tables differ {misplaced}")
    unruled = sorted(set(LOAD_ORDER) ^ set(CUTOFF_RULES))
    if unruled:
        raise ValueError(f"snapshot inventory: CUTOFF_RULES and LOAD_ORDER differ {unruled}")
    for (table, column), scope in SCOPE_ARRAYS.items():
        if (table, column) not in ARRAY_REFERENCES:
            raise ValueError(f"snapshot inventory: SCOPE_ARRAYS names {table}.{column}, no array")
        if scope.every_element_required and not tables[table].c[column].nullable:
            raise ValueError(
                f"snapshot inventory: {table}.{column} is a requirement array and cannot be NULL"
            )
    undeclared = sorted(
        (table, column)
        for table, column in scan_excluded_columns(metadata)
        if column not in EXCLUDED_COLUMNS.get(table, frozenset())
    )
    if undeclared:
        raise ValueError(
            f"snapshot inventory: credential-like or binary columns {undeclared}; list them in "
            "EXCLUDED_COLUMNS (nulled on export) or move the table out of the copy"
        )
    for key in SHARED_KEYS:
        if key.table not in tables or key.shared_table not in RULES:
            raise ValueError(f"snapshot inventory: SHARED_KEYS names unknown table {key}")
        if RULES[key.shared_table].snapshot_class is not SnapshotClass.SHARED:
            raise ValueError(f"snapshot inventory: {key.shared_table} is not SHARED")
        missing_columns = [c for c in key.columns if c not in tables[key.table].c]
        if missing_columns:
            raise ValueError(f"snapshot inventory: {key.table} has no columns {missing_columns}")
    position = {name: index for index, name in enumerate(LOAD_ORDER)}
    resolved = references(metadata)
    by_table: dict[str, list[Reference]] = {}
    for reference in resolved:
        by_table.setdefault(reference.table, []).append(reference)
    datasets: list[Dataset] = []
    for name in LOAD_ORDER:
        table = tables[name]
        rule = RULES[name]
        columns = tuple(str(column.name) for column in table.columns)
        missing_excluded = sorted(EXCLUDED_COLUMNS.get(name, frozenset()) - set(columns))
        if missing_excluded:
            raise ValueError(f"snapshot inventory: {name} has no columns {missing_excluded}")
        cutoff_rule = CUTOFF_RULES[name]
        for column_name in (cutoff_rule.column, cutoff_rule.fallback):
            if column_name is not None and column_name not in columns:
                raise ValueError(f"snapshot inventory: {name} has no cutoff column {column_name}")
        if cutoff_rule.kind in (_TS, _EF) and not cutoff_rule.column:
            raise ValueError(f"snapshot inventory: {name} cutoff rule names no column")
        effectivity = sorted(_EFFECTIVITY_COLUMNS & set(columns))
        if effectivity and rule.category is Category.CONFIGURATION and cutoff_rule.kind is not _EF:
            raise ValueError(
                f"snapshot inventory: {name} carries {effectivity}; a configuration table with an "
                "effectivity column is cut by its effective state (ruling Q-6)"
            )
        if rule.category is Category.FACT and cutoff_rule.kind is CutoffKind.NONE:
            raise ValueError(f"snapshot inventory: fact table {name} needs a timestamp cutoff")
        if rule.category is Category.FACT and cutoff_rule.kind is CutoffKind.PARENT:
            if _CREATED_AT in columns:
                raise ValueError(f"snapshot inventory: {name} has created_at; cut by it")
        primary = tuple(str(c.name) for c in table.primary_key.columns if c.name != _TENANT_ID)
        order_by = _ORDER_OVERRIDES.get(name, primary)
        if not order_by:
            raise ValueError(f"snapshot inventory: {name} has no row order")
        missing = [column for column in order_by if column not in columns]
        if missing:
            raise ValueError(f"snapshot inventory: {name} has no order columns {missing}")
        deferred: list[str] = []
        self_references: list[str] = []
        row_references: list[str] = []
        component = _COMPONENT_OF.get(name)
        nulled: list[str] = list(sorted(EXCLUDED_COLUMNS.get(name, frozenset())))
        for reference in by_table.get(name, ()):
            target_class = _class_of(reference.target)
            if reference.array:
                # D-98 candidate 106: filtered per element by apply_parent_cutoff; never nulled,
                # never deferred, never a shared dependency
                continue
            if rule.snapshot_class is SnapshotClass.REPLAY_REFERENCE:
                # Consumed by the replay driver, never inserted: only regenerated targets are
                # nulled (their rows do not exist in the sandbox yet).
                if target_class in (SnapshotClass.REGENERATED, SnapshotClass.PENDING):
                    nulled.append(reference.column)
                continue
            if target_class is SnapshotClass.COPIED and reference.self_reference:
                # The referenced row is a row of this dataset: ordering inside the dataset puts
                # it first, so the value is inserted and never waits for an UPDATE the table's
                # immutability class would refuse (IM-A, IM-S past its editable states, IM-P past
                # TESTED).
                if not reference.nullable:
                    raise ValueError(
                        f"snapshot inventory: {name}.{reference.column} is a NOT NULL "
                        "self-reference; no row of the dataset could load first"
                    )
                self_references.append(reference.column)
            elif (
                target_class is SnapshotClass.COPIED
                and component is not None
                and reference.target in component.tables
            ):
                # Both rows belong to one component: its single row order puts the referenced
                # row first, whichever table loads first — unless the reference is the
                # component's declared updatable back-edge, which the fixup step restores.
                if (name, reference.column) in component.deferred:
                    if not reference.nullable:
                        raise ValueError(
                            f"snapshot inventory: {name}.{reference.column} is NOT NULL and "
                            f"cannot be the deferred edge of the {component.name} component"
                        )
                    deferred.append(reference.column)
                else:
                    row_references.append(reference.column)
            elif target_class is SnapshotClass.COPIED:
                later = position[reference.target] > position[name]
                if later and not reference.nullable:
                    raise ValueError(
                        f"snapshot inventory: {name}.{reference.column} is NOT NULL but "
                        f"{reference.target} loads after {name}"
                    )
                if later:
                    deferred.append(reference.column)
            elif target_class in _NULLED_TARGET_CLASSES:
                if not reference.nullable:
                    raise ValueError(
                        f"snapshot inventory: {name}.{reference.column} is NOT NULL but names "
                        f"{reference.target} ({target_class.value}), which the sandbox never loads"
                    )
                nulled.append(reference.column)
                if (name, reference.column) not in REBUILD_STEPS:
                    raise ValueError(
                        f"snapshot inventory: {name}.{reference.column} is nulled on export but "
                        "REBUILD_STEPS names no rebuild step (or None with a reason)"
                    )
            elif target_class is SnapshotClass.SHARED and (name, reference.column) in REBUILD_STEPS:
                # an explicit rebuild step wins: the identity is the source's own (its replay
                # sandbox), not a dependency of the copy — nulled on export, rebuilt by a later
                # replay (T-MIG-01 sandbox_tenant_id; 05 SBX-10)
                nulled.append(reference.column)
            elif target_class is SnapshotClass.SHARED:
                # kept as is: the identities travel and the manifest lists them (SHARED_KEYS)
                if not any(k.table == name and reference.column in k.columns for k in SHARED_KEYS):
                    raise ValueError(
                        f"snapshot inventory: {name}.{reference.column} names SHARED "
                        f"{reference.target} but SHARED_KEYS does not list it"
                    )
        datasets.append(
            Dataset(
                name,
                rule.snapshot_class,
                rule.category,
                columns,
                cutoff_rule,
                order_by,
                position[name],
                tuple(deferred),
                tuple(sorted(set(nulled))),
                tuple(self_references),
                tuple(row_references),
            )
        )
    for table, literals in POLYMORPHIC_SUBJECTS.items():
        if table not in tables or not {"subject_type", "subject_id"} <= set(tables[table].c.keys()):
            raise ValueError(f"snapshot inventory: {table} has no polymorphic subject columns")
        unknown = sorted(t for t in literals.values() if t not in RULES and t not in PENDING)
        if unknown:
            raise ValueError(f"snapshot inventory: {table} names unknown subject tables {unknown}")
    self_referencing = {d.name for d in datasets if d.self_references}
    for graph in GRAPHS.values():
        in_graph = sorted({graph.root, *(n for n, _ in graph.dependants)} & self_referencing)
        if in_graph:  # a graph loads root by root, not referenced-first within one dataset
            raise ValueError(f"snapshot inventory: graph datasets {in_graph} carry self-references")
    _check_components(datasets, resolved, position)
    nulled_by_table = {d.name: set(d.nulled_on_export) for d in datasets}
    stale_steps = sorted(
        f"{t}.{c}"
        for t, c in REBUILD_STEPS
        if c not in nulled_by_table.get(t, set()) and (t, c) not in POLYMORPHIC_SUBJECT_COLUMNS
    )
    if stale_steps:
        raise ValueError(
            f"snapshot inventory: REBUILD_STEPS names columns not nulled {stale_steps}"
        )
    exclusions = tuple(
        Exclusion(name, rule.category, rule.snapshot_class, rule.reason)
        for name, rule in sorted(RULES.items())
        if rule.snapshot_class not in _COPIED_CLASSES and name in tables
    )
    return Inventory(
        tuple(datasets), exclusions, resolved, tuple(PENDING[name] for name in sorted(PENDING))
    )


def _refuse_binary(name: str, row: Mapping[str, Any]) -> None:
    """A binary column never enters a dataset: ciphertexts and sidecars stay out (PRV-06)."""
    for column, value in row.items():
        if isinstance(value, bytes | bytearray | memoryview):
            raise TypeError(f"{name}.{column}: binary values are refused from a snapshot dataset")


def _normalise(value: Any) -> Any:
    """INET values as text, the way ``audit.chain.canonical_event`` writes ``source_ip``."""
    return str(value) if isinstance(value, _IP_TYPES) else value


def export_row(dataset: Dataset, row: Mapping[str, Any]) -> Mapping[str, Any]:
    """The row as the snapshot carries it: secret columns and references to regenerated, pending
    or secret targets nulled; INET values normalised; binary values refused."""
    _refuse_binary(dataset.name, row)
    prepared = {column: _normalise(value) for column, value in row.items()}
    for column in dataset.nulled_on_export:
        if column in prepared:
            prepared[column] = None
    return prepared


def _sort_key(dataset: Dataset, row: Mapping[str, Any]) -> bytes:
    parts = []
    for column in dataset.order_by:
        if column not in row:
            raise ValueError(f"{dataset.name}: row lacks the order column {column!r}")
        value = row[column]
        if isinstance(value, int) and not isinstance(value, bool):
            parts.append(f"{value:032d}".encode())  # integers sort numerically
        else:
            parts.append(canonical_bytes(value))
    return b"\x00".join(parts)


EMPTY_SHA256: Final = hashlib.sha256(b"").hexdigest()  # the entry of a dataset with no rows (I-3)


class JsonlStream(io.RawIOBase):
    """The JSONL bytes of one dataset, produced as they are read (slice I-3: no whole-dataset
    buffer). The exported rows are sorted once by ``dataset.order_by`` — the reader's rows are in
    memory already — then each canonical line (DG-KRN-CAN-01 to -15, LF-terminated) is encoded
    only when the consumer reads it; the SHA-256 (T-PLT-29) and the row count follow the bytes
    handed out, so ``sha256`` is the digest of exactly what the store received once ``exhausted``.
    """

    def __init__(self, dataset: Dataset, rows: Iterable[Mapping[str, Any]]) -> None:
        super().__init__()
        prepared: list[tuple[bytes, Mapping[str, Any]]] = []
        for row in rows:
            exported = export_row(dataset, row)
            prepared.append((_sort_key(dataset, exported), exported))
        prepared.sort(key=lambda item: item[0])
        self.name = dataset.name
        self._lines = (canonical_bytes(dict(exported)) + b"\n" for _, exported in prepared)
        self._pending = b""
        self._hash = hashlib.sha256()
        self.row_count = 0
        self.size = 0
        self.exhausted = False

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        view = memoryview(buffer).cast("B")
        want, out = len(view), 0
        while out < want:
            if not self._pending:
                line = next(self._lines, None)
                if line is None:
                    self.exhausted = True
                    break
                self._pending = line
                self.row_count += 1
            take = min(want - out, len(self._pending))
            view[out : out + take] = self._pending[:take]
            self._pending = self._pending[take:]
            out += take
        self._hash.update(view[:out])
        self.size += out
        return out

    @property
    def sha256(self) -> str:
        """The digest of the bytes handed out so far — the file's digest once ``exhausted``."""
        return self._hash.hexdigest()


def encode_stream(dataset: Dataset, rows: Iterable[Mapping[str, Any]]) -> JsonlStream:
    """The streaming form of :func:`encode_rows` (slice I-3)."""
    return JsonlStream(dataset, rows)


def encode_rows(dataset: Dataset, rows: Iterable[Mapping[str, Any]]) -> Encoded:
    """One canonical JSON object per exported row (DG-KRN-CAN-01 to -15), rows in
    ``dataset.order_by`` order, each line LF-terminated; the hash is the SHA-256 of the plaintext
    bytes (T-PLT-29). The in-memory form of :class:`JsonlStream`, read to the end."""
    stream = encode_stream(dataset, rows)
    content = stream.readall()
    return Encoded(dataset.name, content, stream.sha256, stream.row_count)


def decode_rows(content: bytes) -> tuple[Mapping[str, Any], ...]:
    """The rows of a JSONL dataset as JSON values (strings for Decimal, UUID, date, datetime)."""
    if content and not content.endswith(b"\n"):
        raise ValueError("a JSONL dataset ends with a line feed")
    rows: list[Mapping[str, Any]] = []
    for number, line in enumerate(content.split(b"\n")[:-1], start=1):
        parsed = json.loads(line.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError(f"line {number}: a dataset row is a JSON object")
        rows.append(MappingProxyType(parsed))
    return tuple(rows)


def _at_or_before(value: Any, known_at: datetime, what: str) -> bool:
    """``value ≤ known_at`` for a timezone-aware datetime, or for a DATE against the UTC calendar
    date of ``known_at`` (Q-8b; business dates are entity-local, API-C-07)."""
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{what}: a timezone-aware datetime is required")
        return value <= known_at
    if isinstance(value, date):
        return value <= known_at.astimezone(UTC).date()
    raise ValueError(f"{what}: a timezone-aware datetime or a date is required")


def cutoff(
    dataset: Dataset, rows: Iterable[Mapping[str, Any]], known_at: datetime
) -> tuple[Mapping[str, Any], ...]:
    """The rows the snapshot keeps as of ``known_at`` under the dataset's ``CutoffRule`` (ruling
    Q-6): TIMESTAMP keeps ``column ≤ known_at``; EFFECTIVE keeps rows effective on or before
    ``known_at`` (a NULL effective value falls back to the creation timestamp; Q-8b); PARENT and
    NONE keep every row."""
    if known_at.tzinfo is None or known_at.utcoffset() is None:
        raise ValueError("known_at is timezone-aware (DG-KRN-CAN-08)")
    rule = dataset.cutoff
    if rule.kind in (CutoffKind.PARENT, CutoffKind.NONE) or rule.column is None:
        return tuple(rows)
    kept: list[Mapping[str, Any]] = []
    for row in rows:
        value = row.get(rule.column)
        what = f"{dataset.name}.{rule.column}"
        if rule.kind is CutoffKind.TIMESTAMP:
            if not isinstance(value, datetime):
                raise ValueError(f"{what}: a timezone-aware datetime is required")
            if _at_or_before(value, known_at, what):
                kept.append(row)
            continue
        if value is None:
            if rule.fallback is None:
                kept.append(row)
            elif _at_or_before(row.get(rule.fallback), known_at, f"{dataset.name}.{rule.fallback}"):
                kept.append(row)
            continue
        if _at_or_before(value, known_at, what):
            kept.append(row)
    return tuple(kept)


def close_open_invitations(
    rows: Mapping[str, Sequence[Mapping[str, Any]]], known_at: datetime
) -> Mapping[str, Sequence[Mapping[str, Any]]]:
    """``rows`` — the kept rows of every dataset — as the snapshot carries them where a
    membership is INVITED at the cut (``CLOSED_INVITATION``): that row REMOVED, its token and
    expiry null and ``removed_at = known_at``; each of its role assignments still in force
    revoked at ``known_at`` by SYSTEM. An invitation that has run past its expiry and was not
    removed is INVITED too. Every other row is the object it was, and with no open invitation
    ``rows`` itself is returned."""
    if known_at.tzinfo is None or known_at.utcoffset() is None:
        raise ValueError("known_at is timezone-aware (DG-KRN-CAN-08)")
    memberships = rows.get("tenant_membership", ())
    invited = {row["id"] for row in memberships if row["status"] == OPEN_INVITATION}
    if not invited:
        return rows
    carried = dict(rows)
    carried["tenant_membership"] = tuple(
        {**row, **CLOSED_INVITATION, CLOSED_INVITATION_AT: known_at}
        if row["id"] in invited
        else row
        for row in memberships
    )
    if "role_assignment" in rows:
        carried["role_assignment"] = tuple(
            {**row, **REVOKED_WITH_INVITATION, REVOKED_WITH_INVITATION_AT: known_at}
            if row["membership_id"] in invited and row[REVOKED_WITH_INVITATION_AT] is None
            else row
            for row in rows["role_assignment"]
        )
    return MappingProxyType(carried)


def shared_dependencies(
    rows_by_table: Mapping[str, Iterable[Mapping[str, Any]]], engine_release: str
) -> Shared:
    """The SHARED identities the exported rows name, through ``SHARED_KEYS`` (ruling Q-7), with
    the source's stamped engine release (required; F-SNP-I2-R2)."""
    values: dict[str, set[str]] = {}
    for key in SHARED_KEYS:
        for row in rows_by_table.get(key.table, ()):
            parts: list[list[str]] = []
            for column in key.columns:
                value = row.get(column)
                if value is None:
                    parts = []
                    break
                items = value if isinstance(value, list | tuple | set | frozenset) else [value]
                parts.append([str(item) for item in items])
            if not parts:
                continue
            if len(parts) == 1:
                values.setdefault(key.shared_table, set()).update(parts[0])
            else:
                values.setdefault(key.shared_table, set()).add("|".join(p[0] for p in parts))
    refs = tuple(SharedRef(table, tuple(sorted(items))) for table, items in sorted(values.items()))
    return Shared(refs, engine_release)


def verify_shared(manifest: Manifest, present: Mapping[str, Iterable[str]]) -> tuple[str, ...]:
    """The shared identities the manifest depends on that ``present`` (per SHARED table, the
    identities of the target deployment) lacks — the drift check of ruling Q-7."""
    if manifest.shared is None:
        return ("manifest carries no shared block",)
    findings: list[str] = []
    if not manifest.shared.engine_release:
        findings.append("shared block carries no engine release")
    for ref in manifest.shared.refs:
        have = set(present.get(ref.table, ()))
        missing = sorted(v for v in ref.values if v not in have)
        if missing:
            findings.append(f"{ref.table}: missing {missing}")
    return tuple(findings)


SCOPE_COLUMN: Final = (
    "tenant_id"  # the first key column of every copied table: the snapshot's scope
)


def primary_key(table: str) -> tuple[str, ...]:
    """The canonical primary key of a copied table, in column order, from the table metadata."""
    return tuple(c.name for c in model_metadata.tables[f"erev.{table}"].primary_key.columns)


def identity_columns(table: str) -> tuple[str, ...]:
    """The primary key minus the tenant scope a snapshot carries once (Codex I2-R3): ``("id",)``
    for the id-keyed tables, ``("role_id", "permission_code")`` for role_permission."""
    columns = tuple(column for column in primary_key(table) if column != SCOPE_COLUMN)
    if not columns:
        raise ValueError(f"{table}: no primary key column beside {SCOPE_COLUMN}")
    return columns


def row_identity(table: str, row: Mapping[str, Any]) -> str:
    """A row's identity as text — its key values in primary-key order joined with ``|``, a single
    key column kept as its single value; never None, never invented: a missing or NULL key column
    refuses (Codex I2-R3; ruling D-98 71 refinement)."""
    parts: list[str] = []
    for column in identity_columns(table):
        value = row.get(column)
        if value is None:
            raise ValueError(
                f"{table}: row lacks the primary key column {column!r}; the excluded identity "
                "is never None or invented"
            )
        parts.append(str(value))
    return "|".join(parts)


def _check_components(
    datasets: Sequence[Dataset], resolved: Sequence[Reference], position: Mapping[str, int]
) -> None:
    """Every ``COMPONENTS`` entry against the catalogue: keyed by its first table, its tables
    COPIED and in LOAD_ORDER, outside every graph, its deferred edges real, nullable references
    inside it — and every copied parent OUTSIDE the component loads before the component does,
    because the whole component loads at its first table's position."""
    by_name = {d.name: d for d in datasets}
    in_graphs = {name for g in GRAPHS.values() for name in (g.root, *(n for n, _ in g.dependants))}
    seen: set[str] = set()
    for key, component in COMPONENTS.items():
        label = f"snapshot inventory: component {component.name}"
        absent = [t for t in component.tables if t not in by_name]
        if absent:
            raise ValueError(f"{label} names tables the snapshot does not carry: {absent}")
        if len(component.tables) < 2 or len(set(component.tables)) != len(component.tables):
            raise ValueError(f"{label} needs at least two distinct tables")
        if list(component.tables) != sorted(component.tables, key=position.__getitem__):
            raise ValueError(f"{label} lists its tables out of LOAD_ORDER")
        if key != component.tables[0] or component.ordered not in component.tables:
            raise ValueError(f"{label} is keyed by its first table and orders one of its own")
        if seen & set(component.tables) or in_graphs & set(component.tables):
            raise ValueError(f"{label} shares a table with another component or a graph")
        seen.update(component.tables)
        not_copied = [
            t for t in component.tables if by_name[t].snapshot_class is not SnapshotClass.COPIED
        ]
        if not_copied:
            raise ValueError(f"{label} holds tables that are not COPIED: {not_copied}")
        inside = {
            (r.table, r.column)
            for r in resolved
            if r.table in component.tables and r.target in component.tables and not r.array
        }
        unknown = sorted(component.deferred - inside)
        if unknown:
            raise ValueError(f"{label} defers references it does not carry: {unknown}")
        anchor = position[component.tables[0]]
        for reference in resolved:
            if reference.table not in component.tables or reference.array:
                continue
            target = reference.target
            if target in component.tables or target not in by_name:
                continue
            if by_name[target].snapshot_class is not SnapshotClass.COPIED:
                continue
            if (
                position[target] > anchor
                and reference.column not in by_name[reference.table].deferred
            ):
                raise ValueError(
                    f"{label}: {reference.table}.{reference.column} names {target}, which loads "
                    "after the component does"
                )


def component_references(
    inv: Inventory, component: Component
) -> Mapping[str, tuple[tuple[str, str], ...]]:
    """Per table of ``component``: the (column, referenced table) pairs its row order satisfies —
    the table's self-references and its references to the component's other tables, without the
    component's deferred edges and without arrays (the database declares no key on them)."""
    ordered: dict[str, tuple[tuple[str, str], ...]] = {}
    for table in component.tables:
        dataset = inv.dataset(table)
        kept = {*dataset.self_references, *dataset.row_references}
        ordered[table] = tuple(
            (reference.column, reference.target)
            for reference in inv.references
            if reference.table == table and not reference.array and reference.column in kept
        )
    return MappingProxyType(ordered)


def component_order(
    component: Component,
    rows: Mapping[str, Sequence[Mapping[str, Any]]],
    references: Mapping[str, Sequence[tuple[str, str]]],
) -> tuple[tuple[str, Mapping[str, Any]], ...]:
    """The rows of a component's tables as ONE insertion order of (table, row): every row comes
    AFTER the rows its ``references`` name — an estimate version before the event that names it,
    its estimate before the version, that estimate's obligation before the estimate, the event
    that created the obligation before the obligation. The base order is the component's tables
    in LOAD_ORDER, each in its given row order, and it is kept wherever it already satisfies
    that: a row moves only behind a row it names (``referenced_first``, over several tables).

    The ``ordered`` table's rows must come out in exactly their given order — the stream stays in
    source ``record_seq`` order, which DB-08 turns into the sandbox's own. A result that would
    reorder them (an event naming, through its rows, an event recorded later), a value naming no
    row of the component and a cycle are an inconsistent export (``ValueError``)."""
    nodes: list[tuple[str, Mapping[str, Any]]] = [
        (table, row) for table in component.tables for row in rows.get(table, ())
    ]
    index: dict[tuple[str, str], int] = {}
    for position, (table, row) in enumerate(nodes):
        key = (table, str(row["id"]))
        if key in index:
            raise ValueError(f"{table}: two rows carry the id {row['id']}")
        index[key] = position
    placed, open_ = 2, 1
    state = [0] * len(nodes)
    ordered: list[tuple[str, Mapping[str, Any]]] = []
    for start in range(len(nodes)):
        if state[start]:
            continue
        stack = [start]
        while stack:
            current = stack[-1]
            if state[current] == placed:
                stack.pop()
                continue
            state[current] = open_
            table, row = nodes[current]
            waiting: list[int] = []
            for column, referenced in references.get(table, ()):
                value = row.get(column)
                if value is None:
                    continue
                target = index.get((referenced, str(value)))
                if target is None:
                    raise ValueError(
                        f"{table}.{column}: row {row['id']} names {referenced} {value}, which "
                        f"the {component.name} component does not carry"
                    )
                if state[target] == open_:  # itself, or a row already waiting on this one
                    raise ValueError(
                        f"{table}.{column}: row {row['id']} is part of a reference cycle"
                    )
                if state[target] != placed and target not in waiting:
                    waiting.append(target)
            if waiting:
                stack.extend(reversed(waiting))
                continue
            state[current] = placed
            ordered.append(nodes[current])
            stack.pop()
    kept = [str(row["id"]) for table, row in ordered if table == component.ordered]
    given = [str(row["id"]) for row in rows.get(component.ordered, ())]
    if kept != given:
        moved = next(a for a, b in zip(kept, given, strict=True) if a != b)
        raise ValueError(
            f"{component.ordered}: row {moved} would load out of its source order — a row it "
            "names, directly or through other rows, was recorded later"
        )
    return tuple(ordered)


def referenced_first(
    name: str, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]
) -> tuple[Mapping[str, Any], ...]:
    """The rows of one dataset ordered so that every row comes AFTER the rows its self-reference
    ``columns`` name — a version after the version it supersedes, a child entity after its parent,
    an event after the event it supersedes — so the loader inserts each reference with its row
    (``Dataset.self_references``). The given order is kept wherever it already satisfies that: a
    row moves only behind a row it names, so a stream stays in ``record_seq`` order. A value
    naming no row of the dataset, a row naming itself and a cycle are an inconsistent export
    (``ValueError``): the exporter excludes a row whose referenced row was cut
    (``apply_parent_cutoff``), so a consistent dataset never carries one."""
    if not columns or not rows:
        return tuple(rows)
    index: dict[str, int] = {}
    for position, row in enumerate(rows):
        key = str(row["id"])
        if key in index:
            raise ValueError(f"{name}: two rows carry the id {key}")
        index[key] = position
    placed, open_ = 2, 1
    state = [0] * len(rows)
    ordered: list[Mapping[str, Any]] = []
    for start in range(len(rows)):
        if state[start]:
            continue
        stack = [start]
        while stack:
            current = stack[-1]
            if state[current] == placed:
                stack.pop()
                continue
            state[current] = open_
            waiting: list[int] = []
            for column in columns:
                value = rows[current].get(column)
                if value is None:
                    continue
                target = index.get(str(value))
                if target is None:
                    raise ValueError(
                        f"{name}.{column}: row {rows[current]['id']} names {value}, which the "
                        "dataset does not carry"
                    )
                if state[target] == open_:  # itself, or a row already waiting on this one
                    raise ValueError(
                        f"{name}.{column}: row {rows[current]['id']} is part of a reference cycle"
                    )
                if state[target] != placed and target not in waiting:
                    waiting.append(target)
            if waiting:
                stack.extend(reversed(waiting))
                continue
            state[current] = placed
            ordered.append(rows[current])
            stack.pop()
    return tuple(ordered)


@dataclass(frozen=True, slots=True)
class ParentCutoff:
    """The kept rows after the parent dependencies were applied transitively (rulings D-98 62 and
    D-98 71)."""

    kept: Mapping[str, tuple[Mapping[str, Any], ...]]
    excluded_descendants: Mapping[str, int]  # rows dropped because a referenced row was cut
    excluded_ids: Mapping[str, tuple[str, ...]]  # their identities (row_identity), in row order
    broken: tuple[str, ...]  # references naming no source row at all: a refusal, never nulled
    # D-98 candidate 106: array elements dropped (cut or regenerated target), per "table.column"
    dropped_elements: Mapping[str, int] = MappingProxyType({})
    # D-98 candidate 106a: scope arrays whose every target was cut — a refusal, the row left as read
    unrepresentable: tuple[str, ...] = ()


def apply_parent_cutoff(
    inv: Inventory,
    source: Mapping[str, Sequence[Mapping[str, Any]]],
    cut: Mapping[str, Sequence[Mapping[str, Any]]],
) -> ParentCutoff:
    """Apply the declared parent dependencies after each table's own cutoff (F-SNP-I2-R1 / R2;
    rulings D-98 62 and D-98 71). For every reference of a dataset whose target is another
    dataset: a non-NULL value naming a row the target's cutoff kept passes; a value naming a row
    present in ``source`` but cut excludes the row — nullable or not, parent-following table or
    not; no column is ever cleared (a later-set optional link is a post-rc question); a value
    naming no source row is a broken reference finding. A judgement record's or rule test case's
    polymorphic subject (``POLYMORPHIC_SUBJECT_COLUMNS``) naming a COPIED table is a parent in the
    same sense (REGENERATED and PENDING subjects are left to the polymorphic filter). Processed to
    a fixed point across ``LOAD_ORDER`` so exclusions cascade through later parents and
    self-references."""
    dataset_names = {d.name for d in inv.datasets}
    refs_by_table: dict[str, list[Reference]] = {}
    for reference in inv.references:
        if reference.target in dataset_names:
            refs_by_table.setdefault(reference.table, []).append(reference)
    polymorphic = {table for table, _ in POLYMORPHIC_SUBJECT_COLUMNS}
    source_ids = {name: {row["id"] for row in rows if "id" in row} for name, rows in source.items()}
    kept: dict[str, list[Mapping[str, Any]]] = {name: list(rows) for name, rows in cut.items()}
    excluded: dict[str, list[str]] = {}
    dropped: dict[str, int] = {}
    broken: list[str] = []
    unrepresentable: list[str] = []
    changed = True
    while changed:
        changed = False
        kept_ids = {name: {row["id"] for row in rows if "id" in row} for name, rows in kept.items()}
        for dataset in inv.datasets:
            rows = kept.get(dataset.name)
            references: list[Reference] = list(refs_by_table.get(dataset.name, ()))
            subjects = dataset.name in polymorphic
            if not rows or not (references or subjects):
                continue
            survivors: list[Mapping[str, Any]] = []
            for row in rows:
                drop = False
                row_references = references
                if subjects:
                    target = POLYMORPHIC_SUBJECTS[dataset.name].get(str(row.get("subject_type")))
                    if (
                        target in dataset_names
                        and target is not None
                        and RULES[target].snapshot_class is SnapshotClass.COPIED
                    ):
                        row_references = [
                            *references,
                            Reference(dataset.name, "subject_id", target, nullable=False),
                        ]
                for reference in row_references:
                    if reference.array:
                        elements = row.get(reference.column) or ()
                        kept_elements: list[Any] = []
                        target_copied = RULES[reference.target].snapshot_class in (
                            SnapshotClass.COPIED,
                            SnapshotClass.REPLAY_REFERENCE,
                        )
                        for index, element in enumerate(elements):
                            if target_copied and element in kept_ids.get(reference.target, set()):
                                kept_elements.append(element)
                            elif element in source_ids.get(reference.target, set()):
                                key = f"{dataset.name}.{reference.column}"
                                dropped[key] = dropped.get(key, 0) + 1  # cut or regenerated
                            else:
                                finding = (
                                    f"{dataset.name}.{reference.column}[{index}]: "
                                    f"{row_identity(dataset.name, row)} names {element}, "
                                    "absent from the source"
                                )
                                if finding not in broken:
                                    broken.append(finding)
                        scope = SCOPE_ARRAYS.get((dataset.name, reference.column))
                        if (
                            scope is not None
                            and scope.every_element_required
                            and list(elements) != kept_elements
                        ):
                            # ruling R-98: a requirement set that lost an element is unresolved
                            # in the copy — NULL, never the remaining subset and never a refusal
                            changed = True
                            row = {**row, reference.column: None}
                            continue
                        if scope is not None and elements and not kept_elements:
                            # D-98 candidate 106a: every scoped target cut — never rewrite to []
                            # (that would mean all targets) and never flip the paired flag
                            finding = (
                                f"{dataset.name}.{reference.column}: "
                                f"{row_identity(dataset.name, row)} — every scoped target cut "
                                f"({', '.join(str(e) for e in elements)}); [] would mean all "
                                "entities"
                            )
                            if finding not in unrepresentable:
                                unrepresentable.append(finding)
                            key = f"{dataset.name}.{reference.column}"
                            dropped[key] = dropped.get(key, 0) - len(elements)  # not a drop
                            if dropped[key] == 0:
                                del dropped[key]
                            continue
                        if list(elements) != kept_elements:
                            changed = True
                            row = {**row, reference.column: kept_elements}
                        continue
                    value = row.get(reference.column)
                    if value is None or value in kept_ids.get(reference.target, set()):
                        continue
                    if value in source_ids.get(reference.target, set()):
                        drop = True  # D-98 71: excluded whatever the column's nullability
                        break
                    finding = (
                        f"{dataset.name}.{reference.column}: "
                        f"{row_identity(dataset.name, row)} names {value}, absent from the source"
                    )
                    if finding not in broken:
                        broken.append(finding)
                if drop:
                    changed = True
                    excluded.setdefault(dataset.name, []).append(row_identity(dataset.name, row))
                    continue
                survivors.append(row)
            kept[dataset.name] = survivors
    return ParentCutoff(
        MappingProxyType({name: tuple(rows) for name, rows in kept.items()}),
        MappingProxyType({name: len(ids) for name, ids in excluded.items()}),
        MappingProxyType({name: tuple(ids) for name, ids in excluded.items()}),
        tuple(broken),
        MappingProxyType(dict(sorted(dropped.items()))),
        tuple(unrepresentable),
    )


def retention_of(
    file_rows: Iterable[Mapping[str, Any]], policy: RetentionPolicy | None = None
) -> Retention:
    """The Q-4 retention block from the copied ``file_object`` rows (T-PLT-29 columns); with a
    ``policy`` the confirmed families and ``"CONFIRMED: <source>"`` replace the PROPOSED defaults
    (the exporter always passes one — it refuses without)."""
    files: list[FileRetention] = []
    for row in file_rows:
        until = row.get("retention_until")
        if until is not None and not isinstance(until, date):
            raise ValueError("file_object.retention_until is a date")
        files.append(
            FileRetention(
                row["id"], str(row["sha256"]), str(row["purpose"]), until, bool(row["legal_hold"])
            )
        )
    files.sort(key=lambda item: str(item.id))
    hold = any(item.legal_hold for item in files)
    if policy is None:
        return Retention(tuple(files), hold)
    return Retention(tuple(files), hold, policy.families, f"CONFIRMED: {policy.source}")


def manifest_bytes(manifest: Manifest) -> bytes:
    """Canonical JSON of the manifest (the T-PLT-34 ``manifest_file_id`` content)."""
    document: dict[str, Any] = {
        "format_version": manifest.format_version,
        "source_tenant_id": manifest.stamp.source_tenant_id,
        "known_at": manifest.stamp.known_at,
        "purpose": manifest.stamp.purpose,
        "datasets": [
            {"name": entry.name, "sha256": entry.sha256, "row_count": entry.row_count}
            for entry in manifest.entries
        ],
        "exclusions": [
            {"name": item.name, "class": item.snapshot_class.value, "reason": item.category.value}
            for item in manifest.exclusions
        ],
    }
    document["audit_history_carried"] = manifest.audit_history_carried
    document["audit_statement"] = AUDIT_HISTORY_STATEMENT
    document["array_drops"] = dict(sorted(manifest.array_drops.items()))
    if manifest.shared is not None:
        document["shared"] = {
            "engine_release": manifest.shared.engine_release,
            "refs": [
                {"table": ref.table, "values": list(ref.values)} for ref in manifest.shared.refs
            ],
        }
    if manifest.retention is not None:
        document["retention"] = {
            "attribute": RETENTION_ATTRIBUTE,
            "families": dict(manifest.retention.families),
            "families_status": manifest.retention.families_status,
            "source_legal_hold": manifest.retention.source_legal_hold,
            "files": [
                {
                    "id": item.id,
                    "sha256": item.sha256,
                    "purpose": item.purpose,
                    "retention_until": item.retention_until,
                    "legal_hold": item.legal_hold,
                }
                for item in manifest.retention.files
            ],
        }
    return canonical_bytes(document)


def manifest_sha256(manifest: Manifest) -> str:
    """T-PLT-34 ``manifest_sha256``: the SHA-256 of the manifest bytes."""
    return hashlib.sha256(manifest_bytes(manifest)).hexdigest()


def verify_manifest(manifest: Manifest, files: Mapping[str, bytes]) -> tuple[str, ...]:
    """Recompute each file's SHA-256 and row count against the manifest (SNP-1
    ``test_manifest_hashes_and_counts``); returns the findings, empty when everything ties."""
    findings: list[str] = []
    named = {entry.name for entry in manifest.entries}
    for entry in manifest.entries:
        content = files.get(entry.name)
        if content is None:
            # I-3: a dataset with no rows is not stored (T-PLT-29 stores at least one byte); its
            # entry carries the empty digest with row count 0 and needs no file.
            if entry.row_count == 0 and entry.sha256 == EMPTY_SHA256:
                continue
            findings.append(f"{entry.name}: file missing")
            continue
        digest = hashlib.sha256(content).hexdigest()
        if digest != entry.sha256:
            findings.append(f"{entry.name}: sha256 {digest} differs from the manifest")
        count = content.count(b"\n")
        if count != entry.row_count:
            findings.append(
                f"{entry.name}: {count} rows differ from the manifest {entry.row_count}"
            )
    for extra in sorted(set(files) - named):
        findings.append(f"{extra}: file not in the manifest")
    return tuple(findings)


def shred_targets(manifest: Manifest, file_id: UUID) -> tuple[str, ...]:
    """Where a source file's copy lives inside the snapshot (Q-4): the ``file_object`` dataset row
    and the manifest's retention entry; empty when the snapshot does not carry the file."""
    if manifest.retention is None or all(item.id != file_id for item in manifest.retention.files):
        return ()
    return ("file_object", "manifest.retention")


def shred_check(manifest: Manifest, file_id: UUID, today: date) -> tuple[str, ...]:
    """Whether the snapshot copy of ``file_id`` may be shredded today: mirrors 04 §15.4
    ``FILE_RETENTION_ACTIVE`` (legal hold or future retention) and adds the ruled inheritance — a
    legal hold anywhere in the source at snapshot time blocks shredding of the snapshot copy too.
    Returns the findings; empty means the shred may proceed."""
    if manifest.retention is None:
        return ("manifest carries no retention block (format < 2)",)
    match = [item for item in manifest.retention.files if item.id == file_id]
    if not match:
        return (f"file {file_id} is not in the snapshot",)
    item = match[0]
    findings: list[str] = []
    if item.legal_hold:
        findings.append("FILE_RETENTION_ACTIVE: legal hold on the file")
    if item.retention_until is not None and item.retention_until > today:
        findings.append(f"FILE_RETENTION_ACTIVE: retention until {item.retention_until}")
    if manifest.retention.source_legal_hold and not item.legal_hold:
        findings.append(
            "inherited legal hold: the source held files at snapshot time (ruling Q-4; requires "
            "human confirmation before production use)"
        )
    return tuple(findings)


def source_untouched(before: Mapping[str, int], after: Mapping[str, int]) -> tuple[str, ...]:
    """SBX-11: the source's row counts before and after a snapshot; findings name every table
    whose count changed or that appears on one side only."""
    findings: list[str] = []
    for name in sorted(set(before) | set(after)):
        if name not in before or name not in after:
            findings.append(f"{name}: counted on one side only")
        elif before[name] != after[name]:
            findings.append(f"{name}: {before[name]} rows before, {after[name]} after")
    return tuple(findings)


def _load_steps(inv: Inventory) -> tuple[Step, ...]:
    """One ``load:<table>`` step per COPIED dataset, in LOAD_ORDER (F-SNP-R1: the executed
    sequence is the sequence the deferral was derived from; no family reordering) — except the
    tables of a component (``COMPONENTS``), which load as ONE step ``load:<component>`` at the
    position of the component's first table. Deferred reference columns are inserted NULL and
    restored by the fixup step; self-references are inserted with their row, the rows
    referenced-first; streams go in record_seq order with DB-08 assigning new recorded_at /
    record_seq; every period loads open."""
    steps: list[Step] = []
    for dataset in inv.datasets:
        if dataset.snapshot_class is not SnapshotClass.COPIED:
            continue
        component = _COMPONENT_OF.get(dataset.name)
        if component is not None:
            if dataset.name == component.tables[0]:
                steps.append(_component_step(inv, component))
            continue  # the other tables load with the component, at its first table
        deferred = (
            f"; deferred (inserted NULL): {', '.join(dataset.deferred)}" if dataset.deferred else ""
        )
        referenced = (
            f"; rows referenced-first (inserted with the row): {', '.join(dataset.self_references)}"
            if dataset.self_references
            else ""
        )
        periods = "; every period loaded open (SBX-04)" if dataset.name == "period" else ""
        steps.append(
            Step(
                f"load:{dataset.name}",
                f"insert the {dataset.name} dataset, one transaction per batch (TXN-08), the "
                f"source read in repeatable-read batches{deferred}{referenced}{periods}",
                (GATE_PROVISIONING_SCOPE,),
                (dataset.name,),
            )
        )
    return tuple(steps)


def _component_step(inv: Inventory, component: Component) -> Step:
    """The one load step of a component: its tables in one row order, one transaction."""
    members = [inv.dataset(name) for name in component.tables]
    ordered = "; ".join(
        f"{d.name}: {', '.join((*d.self_references, *d.row_references))}"
        for d in members
        if d.self_references or d.row_references
    )
    deferred = "; ".join(f"{d.name}: {', '.join(d.deferred)}" for d in members if d.deferred)
    return Step(
        f"load:{component.name}",
        f"insert the {', '.join(component.tables)} datasets as one unit in one transaction, "
        f"their rows in ONE order in which every row follows the rows it names ({ordered}); "
        f"{component.ordered} rows keep their source record_seq order (DB-08)"
        + (f"; deferred (inserted NULL): {deferred}" if deferred else ""),
        (GATE_PROVISIONING_SCOPE,),
        component.tables,
    )


def load_plan(purpose: str, inv: Inventory | None = None) -> tuple[Step, ...]:
    """SBX-04 as data: the steps of a sandbox load from a snapshot of ``purpose`` with the gates
    each needs; no step is executed here."""
    if purpose not in PURPOSES:
        raise ValueError(f"unknown snapshot purpose {purpose!r} (T-PLT-34)")
    inv = inv or inventory()
    deferred_tables = tuple(d.name for d in inv.datasets if d.deferred)
    return (
        Step(
            "authorise",
            "POST /tenant/sandboxes (or /tenant/snapshots with purpose SANDBOX_COPY) by a "
            "principal holding the permission with a fresh step-up (PRD ACT-50)",
            (GATE_PERMISSION, GATE_STEP_UP),
            (),
        ),
        Step(
            "queue",
            "TENANT_SNAPSHOT job on the maintenance queue under the source tenant's copy lock",
            (GATE_JOB_LOCK,),
            ("job",),
        ),
        Step(
            "provision",
            "tenant row of kind sandbox with source_tenant_id and source_known_at (T-PLT-01); "
            "DB-15 admits the INSERT only in provisioning scope",
            (GATE_PROVISIONING_SCOPE,),
            ("tenant",),
        ),
        *_load_steps(inv),
        Step(
            "fixup-deferred-references",
            "restore the deferred reference columns (nullable references to a table that loads "
            "later) from the exported values, one UPDATE per table; references nulled on export "
            "stay NULL until recompute or replay sets them",
            (GATE_PROVISIONING_SCOPE,),
            deferred_tables,
        ),
        Step(
            "recompute",
            "every combination group recomputed with trigger MIGRATION (RCP-19); derived "
            "tables are produced, never copied",
            (),
            ("contract_computation", "contract_version", "schedule_line", "subledger_line"),
        ),
        Step(
            "replay-period-states",
            "period states and locks replayed through the normal transitions from the "
            "REPLAY_REFERENCE datasets in snapshot_replay.replay_plan order; closed periods "
            "receive their released postings first",
            (),
            ("period_state", "period_state_transition", "period_lock"),
        ),
        Step(
            "verify-determinism",
            "per book and group, the MONETARY STATE of the sandbox's recomputed version against "
            "the source's latest version as of known_at — contract version, balances, "
            "obligation versions and schedule lines without the per-version activity columns — "
            "and, for a group's first computation, the recomputed output hashed with the source "
            "computation's input_sha256 against the source's output_sha256 (SBX-05 rev 1.50); "
            "derived_mismatches recorded in the load report, each naming its first differing "
            "member; a non-zero count raises SANDBOX_DETERMINISM_MISMATCH (WARNING) and "
            "notifies the requester",
            (),
            ("tenant_snapshot", "exception_item"),
        ),
        Step(
            "audit",
            "tenant.snapshot_loaded as the load's single summary event in the sandbox, after "
            "the verification (source tenant id, known_at, manifest SHA-256, row counts, source "
            "audit chain head at known_at, load report id and SHA-256, derived_mismatches, "
            "blocked_periods); tenant.snapshot_created in the source (SBX-06 rev 1.34)",
            (),
            ("audit_event",),
        ),
    )


def empty_sandbox_plan(permission: str) -> tuple[Step, ...]:
    """An EMPTY sandbox as data (SBX-02 creation paths "reset to empty" and "legacy replay target";
    SNP-3 mode EMPTY; LMG-4): a ``tenant`` row of kind ``sandbox`` under provisioning scope with
    ``source_tenant_id`` = the production tenant and ``source_known_at`` NULL, holding only the
    04 §14.3 provisioning seed; no dataset, no ``tenant_snapshot`` row; the kind is immutable
    (DB-05 ``tenant-kind-immutable``; SBX-10: never converted). ``permission`` is the caller's
    (``sandbox.reset`` for a reset; the migration permission for LMG-4)."""
    if not permission or " " in permission:
        raise ValueError("empty_sandbox_plan needs the caller's permission code")
    return (
        Step(
            "authorise",
            f"the caller holds {permission} with a fresh step-up; the display name is the "
            "caller's (LMG-4: '<tenant display name> replay (Sandbox)')",
            (f"permission {permission}", GATE_STEP_UP),
            (),
        ),
        Step(
            "provision",
            "tenant row of kind sandbox, source_tenant_id = the production tenant, "
            "source_known_at NULL (nothing is copied); DB-15 admits the INSERT only in "
            "provisioning scope; the kind never changes (DB-05)",
            (GATE_PROVISIONING_SCOPE,),
            ("tenant",),
        ),
        Step(
            "seed",
            "the 04 §14.3 provisioning seed only: audit_chain_head, the three books, "
            "ledger_chain_head per book, numbering_series, the ten default roles and their "
            "permissions, SoD rules, built-in dimension definitions, system checklist "
            "templates, tenant_currency, DEFAULT registry versions",
            (GATE_PROVISIONING_SCOPE,),
            (
                "audit_chain_head",
                "book",
                "ledger_chain_head",
                "numbering_series",
                "role",
                "role_permission",
                "sod_rule",
                "dimension_definition",
                "close_checklist_template",
                "tenant_currency",
                "registry_version",
            ),
        ),
        Step(
            "audit",
            "tenant.sandbox_created in the production tenant and as the sandbox's first audit "
            "event (SBX-02: audit events in both tenants)",
            (),
            ("audit_event",),
        ),
    )


def reset_plan() -> tuple[Step, ...]:
    """SBX-07 as data: a reset is a supersession — nothing is deleted. Mode SNAPSHOT supersedes
    through ``load_plan``; mode EMPTY through ``empty_sandbox_plan(GATE_RESET_PERMISSION)``."""
    return (
        Step(
            "authorise",
            f"{RESET_ROUTE} (04 API-R-04) by a principal holding the permission with a fresh "
            "step-up; 409 production-reset-forbidden for a production tenant (REQ-PLT-025)",
            (GATE_RESET_PERMISSION, GATE_STEP_UP),
            (),
        ),
        Step(
            "supersede",
            "a new sandbox tenant: mode SNAPSHOT from the chosen snapshot through load_plan; "
            f"mode {EMPTY_SANDBOX_PURPOSE} through empty_sandbox_plan (the provisioning seed only)",
            (GATE_PROVISIONING_SCOPE, GATE_JOB_LOCK),
            ("tenant",),
        ),
        Step(
            "archive",
            "the old sandbox status = ARCHIVED; scenario.scenario_tenant_id repointed where "
            "applicable (IM-M); no row deleted (DB-01)",
            (),
            ("tenant", "scenario"),
        ),
        Step(
            "move-session",
            "the requesting user's session moved to the new tenant",
            (),
            ("user_session",),
        ),
        Step(
            "audit",
            "tenant.sandbox_reset in the old and the new tenant",
            (),
            ("audit_event",),
        ),
    )


def datasets_of(inv: Inventory, category: Category) -> Sequence[Dataset]:
    """The datasets of one reason family, in load order."""
    return tuple(dataset for dataset in inv.datasets if dataset.category is category)
