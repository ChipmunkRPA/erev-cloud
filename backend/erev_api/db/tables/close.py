"""Close tables (04 §9 T-CLS-01 to T-CLS-08; BUILD_SPEC CLO-2).

The CLO-2 revision creates close runs, the checklist templates and items, period locks with their
snapshots, reconciliations with their items, and sign-offs. Close runs and reconciliations are
IM-S (DB-03, generated from ``TRANSITIONS``); checklist templates and items are IM-M; locks,
snapshots and sign-offs are IM-A (DB-01), and sign-offs carry the DB-10 separation trigger.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import CHAR, BigInteger, Boolean, Column, Date, Integer, Table, Text, Uuid
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB

from erev_api.db.tables import metadata
from erev_api.db.tables.platform import _enum, _sc_c, _sc_c_sc_m, _timestamp, principal_kind
from erev_api.db.types import MoneyType
from erev_api.enums import (
    BookCode,
    ChecklistGateKind,
    ChecklistStatus,
    CloseRunStatus,
    LockKind,
    ReasonCode,
    ReconciliationKind,
    ReconciliationStatus,
    SignoffRole,
    SnapshotKind,
)

# E-02 and E-110 of earlier revisions, bound here again so that this module does not depend on
# ``tables.reference`` while ``tables/__init__`` is importing.
book_code_type: Final = _enum(BookCode, "book_code")
reason_code_type: Final = _enum(ReasonCode, "reason_code")
# Created by the CLO-2 revision: E-58 to E-64 and E-99.
reconciliation_kind: Final = _enum(ReconciliationKind, "reconciliation_kind")
reconciliation_status: Final = _enum(ReconciliationStatus, "reconciliation_status")
checklist_status: Final = _enum(ChecklistStatus, "checklist_status")
checklist_gate_kind: Final = _enum(ChecklistGateKind, "checklist_gate_kind")
close_run_status: Final = _enum(CloseRunStatus, "close_run_status")
lock_kind: Final = _enum(LockKind, "lock_kind")
snapshot_kind: Final = _enum(SnapshotKind, "snapshot_kind")
signoff_role: Final = _enum(SignoffRole, "signoff_role")

# T-CLS-01: resumable close state machine per entity, book and period (IM-S, RLS-TE on entity_id);
# DB-03 with the LOCK element of ``steps`` updatable while SUCCEEDED (BS4-D-03).
close_run: Final = Table(
    "close_run",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("close_run_no", Text(), nullable=False),
    Column("entity_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("period_id", Uuid(), nullable=False),
    Column("status", close_run_status, nullable=False, server_default=sql_text("'PENDING'")),
    _timestamp("cutoff_known_at", nullable=False),
    Column("current_step_code", Text(), nullable=True),
    Column("steps", JSONB(), nullable=False),
    Column("counts", JSONB(), nullable=False, server_default=sql_text("'{}'::jsonb")),
    Column("job_id", Uuid(), nullable=True),
    _timestamp("started_at"),
    _timestamp("finished_at"),
    *_sc_c_sc_m(),
    # 04 rev 1.291 (revision 0127; item CLO-RATE-AFTER-RUN-1): what the run's first period-end
    # step read beside its contracts, as two digests, added after the standard columns of 0047 and
    # written once. NULL in a run started before the revision.
    Column("rates_read", Text(), nullable=True),
    Column("registry_read", Text(), nullable=True),
)

# T-CLS-02: system gates and tenant-defined close tasks (IM-M, RLS-T); system rows change only in
# ``owner_role_id`` and ``due_offset_days``.
close_checklist_template: Final = Table(
    "close_checklist_template",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("description", Text(), nullable=True),
    Column("gate_kind", checklist_gate_kind, nullable=False),
    Column("gate_check_code", Text(), nullable=True),
    Column("is_blocking", Boolean(), nullable=False, server_default=sql_text("true")),
    Column("is_system", Boolean(), nullable=False, server_default=sql_text("false")),
    Column("owner_role_id", Uuid(), nullable=True),
    Column("due_offset_days", Integer(), nullable=True),
    Column("sequence", Integer(), nullable=False),
    Column("is_active", Boolean(), nullable=False, server_default=sql_text("true")),
    *_sc_c_sc_m(),
)

# T-CLS-03: checklist instance per entity, book and period (IM-M without DELETE, RLS-TE on
# entity_id); DB-03 status pairs.
close_checklist_item: Final = Table(
    "close_checklist_item",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("close_checklist_template_id", Uuid(), nullable=False),
    Column("entity_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("period_id", Uuid(), nullable=False),
    Column("status", checklist_status, nullable=False, server_default=sql_text("'NOT_STARTED'")),
    Column("owner_membership_id", Uuid(), nullable=True),
    Column("due_date", Date(), nullable=True),
    Column("result", JSONB(), nullable=True),
    Column("control_execution_id", Uuid(), nullable=True),
    Column("signoff_id", Uuid(), nullable=True),
    Column("waiver_approval_request_id", Uuid(), nullable=True),
    Column("comment", Text(), nullable=True),
    *_sc_c_sc_m(),
)

# T-CLS-04: lock, reopen or permanent-lock record (IM-A, RLS-TE on entity_id); DB-01.
period_lock: Final = Table(
    "period_lock",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("kind", lock_kind, nullable=False),
    Column("entity_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("period_id", Uuid(), nullable=False),
    Column("period_state_transition_id", Uuid(), nullable=False),
    Column("approval_request_id", Uuid(), nullable=False),
    Column("reason_code", reason_code_type, nullable=True),
    Column("comment", Text(), nullable=True),
    Column("certification", JSONB(), nullable=False),
    Column("ledger_head_chain_seq", BigInteger(), nullable=False),
    Column("ledger_head_sha256", CHAR(64), nullable=True),
    Column("audit_head_chain_seq", BigInteger(), nullable=False),
    Column("audit_head_hmac", CHAR(64), nullable=True),
    Column("snapshot_manifest_sha256", CHAR(64), nullable=True),
    Column("previous_lock_id", Uuid(), nullable=True),
    Column("diff_report_file_id", Uuid(), nullable=True),
    # rev 1.113 (revision 0084): the instant a LOCK row's datasets are frozen at (S15-R-18c)
    _timestamp("cutoff_known_at"),
    *_sc_c(),
)

# T-CLS-05: immutable dataset frozen at lock (IM-A, RLS-T); DB-01.
lock_snapshot: Final = Table(
    "lock_snapshot",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("period_lock_id", Uuid(), nullable=False),
    Column("snapshot_kind", snapshot_kind, nullable=False),
    Column("report_run_id", Uuid(), nullable=True),
    Column("file_id", Uuid(), nullable=False),
    Column("file_sha256", CHAR(64), nullable=False),
    Column("row_count", BigInteger(), nullable=False),
    Column("control_totals", JSONB(), nullable=False),
    *_sc_c(),
)

# T-CLS-06: reconciliation with certification (IM-S, RLS-TE on entity_id); DB-03, frozen after
# CERTIFIED except the move to REOPENED.
reconciliation: Final = Table(
    "reconciliation",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("reconciliation_no", Text(), nullable=False),
    Column("kind", reconciliation_kind, nullable=False),
    Column("entity_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("period_id", Uuid(), nullable=False),
    Column("status", reconciliation_status, nullable=False, server_default=sql_text("'DRAFT'")),
    _timestamp("as_of_known_at", nullable=False),
    Column("period_lock_id", Uuid(), nullable=True),
    Column("source_file_id", Uuid(), nullable=True),
    Column("sync_run_id", Uuid(), nullable=True),
    Column("totals", JSONB(), nullable=False, server_default=sql_text("'{}'::jsonb")),
    Column("variance_count", Integer(), nullable=False, server_default=sql_text("0")),
    Column("unexplained_other_amount", MoneyType(), nullable=True),
    Column("auto_certify_rule_set_version_id", Uuid(), nullable=True),
    Column("auto_certify_rule_id", Uuid(), nullable=True),
    Column("report_run_id", Uuid(), nullable=True),
    _timestamp("certified_at"),
    *_sc_c_sc_m(),
    # 04 rev 1.259 (revision 0121; item REC-GEN-LOCK-1): what the generation read, added after the
    # standard columns of 0047. NULL in a row generated before the revision.
    Column("ledger_chain_seq", BigInteger(), nullable=True),
    Column("source_documents_read", Integer(), nullable=True),
    Column("subledger_documents_read", Integer(), nullable=True),
)

# T-CLS-07: itemised difference (IM-S, RLS-T); DB-03 while the parent is not CERTIFIED.
reconciliation_item: Final = Table(
    "reconciliation_item",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("reconciliation_id", Uuid(), nullable=False),
    Column("item_kind", Text(), nullable=False),
    Column("account_code", Text(), nullable=True),
    Column("contract_id", Uuid(), nullable=True),
    Column("invoice_number", Text(), nullable=True),
    Column("subledger_amount", MoneyType(), nullable=True),
    Column("source_amount", MoneyType(), nullable=True),
    Column("difference", MoneyType(), nullable=False),
    Column("currency", CHAR(3), nullable=False),
    Column("is_high_risk", Boolean(), nullable=False, server_default=sql_text("false")),
    Column("gl_document_reference", Text(), nullable=True),
    Column("explanation", Text(), nullable=True),
    _timestamp("resolved_at"),
    Column("resolved_by", Uuid(), nullable=True),
    Column("resolved_by_kind", principal_kind, nullable=True),
    *_sc_c_sc_m(),
    # 04 rev 1.253 (revision 0119; supervisor rulings R-68 (a), R-74): added after the standard
    # columns of 0047.
    Column("origin_period_id", Uuid(), nullable=True),
    Column("account_role", Text(), nullable=True),
)

# T-CLS-08: preparer, reviewer or controller sign-off (IM-A, RLS-T); DB-01, DB-10 separation.
signoff: Final = Table(
    "signoff",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("subject_type", Text(), nullable=False),
    Column("subject_id", Uuid(), nullable=False),
    Column("role", signoff_role, nullable=False),
    Column("signer_id", Uuid(), nullable=False),
    Column("statement", Text(), nullable=False),
    Column("subject_content_sha256", CHAR(64), nullable=False),
    _timestamp("mfa_verified_at", nullable=False),
    _timestamp("signed_at", nullable=False, now_default=True),
)
