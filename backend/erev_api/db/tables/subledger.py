"""Subledger and journal tables (04 §8 T-SL-01 to T-SL-10; BUILD_SPEC CTR-3, CLO-1).

T-SL-01 to T-SL-04 are created by the CTR-3 revision. ``domain.journals.subledger.post`` is the
writer of postings, lines and seals (DG-CMD-10); postings, seals and lines are IM-A, and the ledger
chain head (IM-X) changes only through the DB-06 seal trigger. T-SL-05 to T-SL-10 (manual
adjustments, journal runs, batches, entries, lines and posting acknowledgements) are created by the
CLO-1 revision.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import CHAR, BigInteger, Boolean, Column, Computed, Date, Integer, Table, Text, Uuid
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from erev_api.db.tables import metadata
from erev_api.db.tables.platform import _enum, _sc_c, _sc_c_sc_m, _timestamp
from erev_api.db.types import FxRateType, MoneyType
from erev_api.enums import (
    AccountRole,
    BookCode,
    ClearingPurpose,
    GlAdapter,
    JeType,
    JournalRunGrain,
    JournalRunMode,
    JournalState,
    ManualAdjustmentKind,
    ManualAdjustmentStatus,
    PostingAckKind,
    SubledgerEntryKind,
    SubledgerPostingKind,
)

# E-01, E-02 and E-109 of earlier revisions, bound here again so that this module does not depend
# on ``tables.reference`` while ``tables/__init__`` is importing.
book_code_type: Final = _enum(BookCode, "book_code")
account_role: Final = _enum(AccountRole, "account_role")
clearing_purpose: Final = _enum(ClearingPurpose, "clearing_purpose")
# Created by the CTR-3 revision: E-29, E-31.
subledger_entry_kind: Final = _enum(SubledgerEntryKind, "subledger_entry_kind")
subledger_posting_kind: Final = _enum(SubledgerPostingKind, "subledger_posting_kind")
# Created by the CLO-1 revision: E-30, E-32 to E-34, E-36, E-37, E-93, E-94.
je_type: Final = _enum(JeType, "je_type")
journal_run_mode: Final = _enum(JournalRunMode, "journal_run_mode")
journal_run_grain: Final = _enum(JournalRunGrain, "journal_run_grain")
journal_state: Final = _enum(JournalState, "journal_state")
posting_ack_kind: Final = _enum(PostingAckKind, "posting_ack_kind")
gl_adapter: Final = _enum(GlAdapter, "gl_adapter")
manual_adjustment_kind: Final = _enum(ManualAdjustmentKind, "manual_adjustment_kind")
manual_adjustment_status: Final = _enum(ManualAdjustmentStatus, "manual_adjustment_status")
# T-SL-04 ``dr_cr``.
DR_CR: Final = (
    "CASE WHEN amount_functional > 0 OR (amount_functional = 0 AND amount_txn > 0) "
    "THEN 'D' ELSE 'C' END"
)


# T-SL-01: the atomic container of the lines one commit writes (IM-A, RLS-T); DB-06 (3).
subledger_posting: Final = Table(
    "subledger_posting",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("book_code", book_code_type, nullable=False),
    Column("posting_kind", subledger_posting_kind, nullable=False),
    Column("combination_group_id", Uuid(), nullable=True),
    Column("contract_computation_id", Uuid(), nullable=True),
    Column("close_run_id", Uuid(), nullable=True),
    Column("manual_adjustment_id", Uuid(), nullable=True),
    Column("reverses_posting_id", Uuid(), nullable=True),
    Column("idempotency_key", Text(), nullable=False),
    Column("created_txid", BigInteger(), nullable=False, server_default=sql_text("txid_current()")),
    Column("description", Text(), nullable=False),
    *_sc_c(),
)

# T-SL-02: the seal of a posting with its control totals and hash chain (IM-A, RLS-T); DB-06 (2).
subledger_posting_seal: Final = Table(
    "subledger_posting_seal",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("subledger_posting_id", Uuid(), primary_key=True),
    Column("book_code", book_code_type, nullable=False),
    Column("chain_seq", BigInteger(), nullable=False),
    Column("line_count", Integer(), nullable=False),
    Column("control_totals", JSONB(), nullable=False),
    Column("prev_seal_sha256", CHAR(64), nullable=True),
    Column("seal_sha256", CHAR(64), nullable=False),
    _timestamp("sealed_at", nullable=False, now_default=True),
    *_sc_c(),
)

# T-SL-03: the ledger chain pointer of a book; its row lock serialises seals (IM-X, RLS-T).
ledger_chain_head: Final = Table(
    "ledger_chain_head",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("book_code", book_code_type, primary_key=True),
    Column("last_chain_seq", BigInteger(), nullable=False, server_default=sql_text("0")),
    Column("last_seal_sha256", CHAR(64), nullable=True),
    _timestamp("updated_at", nullable=False, now_default=True),
)

# T-SL-04: the detail accounting line (IM-A, RLS-TE on entity_id, PT-MPE); DB-06 (1), DB-07.
subledger_line: Final = Table(
    "subledger_line",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("period_end_date", Date(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("subledger_posting_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("entity_id", Uuid(), nullable=False),
    Column("period_id", Uuid(), nullable=False),
    Column("origin_period_id", Uuid(), nullable=True),
    Column("is_post_reopen", Boolean(), nullable=False, server_default=sql_text("false")),
    Column("effective_date", Date(), nullable=False),
    _timestamp("recorded_at", nullable=False, now_default=True),
    Column("entry_no", Integer(), nullable=False),
    Column("entry_kind", subledger_entry_kind, nullable=False),
    Column("account_role", account_role, nullable=False),
    Column("clearing_purpose", clearing_purpose, nullable=True),
    Column("gl_account_id", Uuid(), nullable=False),
    Column("dimensions", JSONB(), nullable=False, server_default=sql_text("'{}'::jsonb")),
    Column("dimension_set_sha256", CHAR(64), nullable=False),
    Column("txn_currency", CHAR(3), nullable=False),
    Column("amount_txn", MoneyType(), nullable=False),
    Column("functional_currency", CHAR(3), nullable=False),
    Column("amount_functional", MoneyType(), nullable=False),
    Column("dr_cr", CHAR(1), Computed(DR_CR, persisted=True), nullable=False),
    Column("fx_rate_set_version_id", Uuid(), nullable=True),
    Column("fx_rate_id", Uuid(), nullable=True),
    Column("fx_rate", FxRateType(), nullable=True),
    Column("fx_layer_key", Text(), nullable=True),
    Column("contract_id", Uuid(), nullable=False),
    Column("obligation_id", Uuid(), nullable=True),
    Column("contract_version_id", Uuid(), nullable=True),
    Column("contract_event_id", Uuid(), nullable=True),
    Column("schedule_line_id", Uuid(), nullable=True),
    Column("schedule_period_end_date", Date(), nullable=True),
    Column("contract_cost_asset_id", Uuid(), nullable=True),
    Column("counterparty_entity_id", Uuid(), nullable=True),
    Column("reverses_line_id", Uuid(), nullable=True),
    Column("reverses_period_end_date", Date(), nullable=True),
    Column("reason_code", Text(), nullable=True),
    Column("legacy_key", Text(), nullable=True),
    Column("calc_trace_id", Uuid(), nullable=True),
    Column("trace_node_id", Text(), nullable=True),
    Column("description", Text(), nullable=True),
    *_sc_c(),
    # Supervisor ruling R-11 as amended (04 rev 1.282; revision 0124): the subject of the
    # entry the line belongs to, as the engine keys it; added after the standard columns of 0040.
    # NULL only on a line no product command wrote — ``subledger.post`` requires it of every
    # product caller — and such a line reads back in the spelling of decision L3-1-Q-32.
    Column("subject_key", Text(), nullable=True),
)

# T-SL-12: the first-included events a cumulative posting line attributes to, in ENG-06 order
# (IM-A, RLS-T); ENGINE_SPEC_B S14-R-13a; 04 rev 1.48 (D-98 candidate 95). Created by the
# revision ``0064_subledger_line_event`` on 0063 (assigned at merge prep; landed at the merge of
# main f84770d4).
subledger_line_event: Final = Table(
    "subledger_line_event",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("subledger_line_id", Uuid(), primary_key=True),
    Column("subledger_line_period_end_date", Date(), nullable=False),
    Column("contract_event_id", Uuid(), primary_key=True),
    Column("ordinal", Integer(), nullable=False),
    *_sc_c(),
)

# T-SL-05: maker-checker manual adjustment (IM-S, RLS-TE on entity_id); DB-03.
manual_adjustment: Final = Table(
    "manual_adjustment",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("adjustment_no", Text(), nullable=False),
    Column("kind", manual_adjustment_kind, nullable=False),
    Column("status", manual_adjustment_status, nullable=False, server_default=sql_text("'DRAFT'")),
    Column("contract_id", Uuid(), nullable=False),
    Column("obligation_id", Uuid(), nullable=True),
    Column("entity_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("period_id", Uuid(), nullable=False),
    Column("effective_date", Date(), nullable=False),
    Column("payload", JSONB(), nullable=False),
    Column("amount_functional_abs", MoneyType(), nullable=False),
    Column("currency", CHAR(3), nullable=False),
    Column("reason_code", Text(), nullable=False),
    Column("memo", Text(), nullable=False),
    Column("impact_preview_file_id", Uuid(), nullable=True),
    Column("content_sha256", CHAR(64), nullable=True),
    Column("approval_request_id", Uuid(), nullable=True),
    Column("applied_event_id", Uuid(), nullable=True),
    Column("subledger_posting_id", Uuid(), nullable=True),
    Column("is_deferred_past_lock", Boolean(), nullable=False, server_default=sql_text("false")),
    *_sc_c_sc_m(),
)

# T-SL-06: summarisation of detail lines into GL batches (IM-S, RLS-TE on entity_id); DB-03,
# DB-16 coverage and JE sequence.
journal_run: Final = Table(
    "journal_run",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("run_no", Text(), nullable=False),
    Column("entity_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("period_id", Uuid(), nullable=False),
    Column("mode", journal_run_mode, nullable=False),
    Column("delta_book_code", book_code_type, nullable=True),
    Column("grain", journal_run_grain, nullable=False),
    Column("state", journal_state, nullable=False, server_default=sql_text("'draft'")),
    _timestamp("cutoff_known_at", nullable=False),
    Column("from_chain_seq", BigInteger(), nullable=False),
    Column("to_chain_seq", BigInteger(), nullable=False),
    Column("delta_from_chain_seq", BigInteger(), nullable=True),
    Column("delta_to_chain_seq", BigInteger(), nullable=True),
    Column("functional_currency", CHAR(3), nullable=False),
    Column("line_count", Integer(), nullable=False),
    Column("total_debit_functional", MoneyType(), nullable=False),
    Column("total_credit_functional", MoneyType(), nullable=False),
    Column("close_run_id", Uuid(), nullable=True),
    Column("job_id", Uuid(), nullable=True),
    Column("approval_request_id", Uuid(), nullable=True),
    _timestamp("approved_at"),
    _timestamp("exported_at"),
    _timestamp("acknowledged_at"),
    _timestamp("cancelled_at"),
    *_sc_c_sc_m(),
)

# T-SL-07: balanced GL document of one currency of a run (IM-S, RLS-TE on entity_id); DB-03, DB-15,
# DB-16 approval.
journal_batch: Final = Table(
    "journal_batch",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("journal_run_id", Uuid(), nullable=False),
    Column("batch_no", Integer(), nullable=False),
    Column("chunk_no", Integer(), nullable=False, server_default=sql_text("1")),
    Column("entity_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("period_id", Uuid(), nullable=False),
    Column("txn_currency", CHAR(3), nullable=False),
    Column("functional_currency", CHAR(3), nullable=False),
    Column("state", journal_state, nullable=False, server_default=sql_text("'draft'")),
    Column("line_count", Integer(), nullable=False),
    Column("total_debit_txn", MoneyType(), nullable=False),
    Column("total_credit_txn", MoneyType(), nullable=False),
    Column("total_debit_functional", MoneyType(), nullable=False),
    Column("total_credit_functional", MoneyType(), nullable=False),
    Column("engine_release_id", Uuid(), nullable=False),
    Column("adapter", gl_adapter, nullable=False),
    Column("integration_connection_id", Uuid(), nullable=True),
    Column("external_id", Text(), nullable=False),
    Column("export_file_id", Uuid(), nullable=True),
    Column("export_sha256", CHAR(64), nullable=True),
    Column("detail_file_id", Uuid(), nullable=True),
    Column("detail_sha256", CHAR(64), nullable=True),
    Column("outbox_message_id", Uuid(), nullable=True),
    Column("attempt_count", Integer(), nullable=False, server_default=sql_text("0")),
    Column("last_error", Text(), nullable=True),
    _timestamp("exported_at"),
    _timestamp("acknowledged_at"),
    *_sc_c_sc_m(),
)

# T-SL-08: JE header with a gapless number per tenant and entity (IM-A, RLS-TE on entity_id); DB-01.
journal_entry: Final = Table(
    "journal_entry",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("journal_batch_id", Uuid(), nullable=False),
    Column("entity_id", Uuid(), nullable=False),
    Column("je_seq", BigInteger(), nullable=False),
    Column("je_no", Text(), nullable=False),
    Column("je_type", je_type, nullable=False),
    Column("entry_kind", subledger_entry_kind, nullable=True),
    Column("description", Text(), nullable=False),
    Column(
        "source_event_ids", ARRAY(Uuid()), nullable=False, server_default=sql_text("'{}'::uuid[]")
    ),
    Column("manual_adjustment_id", Uuid(), nullable=True),
    Column("reverses_journal_entry_id", Uuid(), nullable=True),
    Column("is_post_close", Boolean(), nullable=False, server_default=sql_text("false")),
    *_sc_c(),
)

# T-SL-09: summarised GL line (IM-A, RLS-TE on entity_id); DB-01, DB-07 period guard (BS4-D-02).
journal_line: Final = Table(
    "journal_line",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("journal_entry_id", Uuid(), nullable=False),
    Column("journal_batch_id", Uuid(), nullable=False),
    Column("line_no", Integer(), nullable=False),
    Column("entity_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("period_id", Uuid(), nullable=False),
    Column("account_role", account_role, nullable=False),
    Column("gl_account_id", Uuid(), nullable=False),
    Column("gl_account_code", Text(), nullable=False),
    Column("dimensions", JSONB(), nullable=False, server_default=sql_text("'{}'::jsonb")),
    Column("dimension_set_sha256", CHAR(64), nullable=False),
    Column("txn_currency", CHAR(3), nullable=False),
    Column("debit_txn", MoneyType(), nullable=False, server_default=sql_text("0")),
    Column("credit_txn", MoneyType(), nullable=False, server_default=sql_text("0")),
    Column("functional_currency", CHAR(3), nullable=False),
    Column("debit_functional", MoneyType(), nullable=False, server_default=sql_text("0")),
    Column("credit_functional", MoneyType(), nullable=False, server_default=sql_text("0")),
    Column("contract_id", Uuid(), nullable=True),
    Column("obligation_id", Uuid(), nullable=True),
    Column("legacy_key", Text(), nullable=True),
    Column("counterparty_entity_id", Uuid(), nullable=True),
    Column("origin_period_id", Uuid(), nullable=True),
    Column(
        "fx_rate_set_version_ids",
        ARRAY(Uuid()),
        nullable=False,
        server_default=sql_text("'{}'::uuid[]"),
    ),
    Column("fx_rate_ids", ARRAY(Uuid()), nullable=False, server_default=sql_text("'{}'::uuid[]")),
    Column("memo", Text(), nullable=True),
    Column("source_line_count", Integer(), nullable=False),
    Column("source_grouping_sha256", CHAR(64), nullable=False),
    *_sc_c(),
)

# T-SL-10: ERP acknowledgement or manual confirmation of a batch (IM-A, RLS-T); DB-01.
posting_ack: Final = Table(
    "posting_ack",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("journal_batch_id", Uuid(), nullable=False),
    Column("ack_kind", posting_ack_kind, nullable=False),
    Column("gl_document_id", Text(), nullable=True),
    Column("gl_posted_date", Date(), nullable=True),
    Column("response_sha256", CHAR(64), nullable=True),
    Column("response_file_id", Uuid(), nullable=True),
    Column("message", Text(), nullable=True),
    _timestamp("received_at", nullable=False, now_default=True),
    *_sc_c(),
)
