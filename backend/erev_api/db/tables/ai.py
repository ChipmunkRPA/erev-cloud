"""AI evidence tables (04 T-AI-02; AIX-1)."""

from typing import Final

from sqlalchemy import CHAR, Column, DateTime, Integer, Table, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB

from erev_api.db.tables import metadata
from erev_api.db.tables.platform import _enum, _sc_c, _sc_c_sc_m, _timestamp
from erev_api.enums import AiProposalKind, AiProposalStatus

ai_model_log: Final = Table(
    "ai_model_log",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("intent_id", Uuid(), nullable=True),
    Column("provider", Text(), nullable=False),
    Column("model_id", Text(), nullable=False),
    Column("prompt_template_id", Text(), nullable=False),
    Column("prompt_template_version", Text(), nullable=False),
    Column("parameters", JSONB(), nullable=False),
    Column("input_sha256", CHAR(64), nullable=False),
    Column("response_sha256", CHAR(64), nullable=True),
    Column("input_tokens", Integer(), nullable=False, server_default=text("0")),
    Column("output_tokens", Integer(), nullable=False, server_default=text("0")),
    Column("latency_ms", Integer(), nullable=False),
    Column("outcome", Text(), nullable=False),
    Column("error_detail", Text(), nullable=True),
    *_sc_c(),
)


ai_proposal: Final = Table(
    "ai_proposal",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("kind", _enum(AiProposalKind, "ai_proposal_kind"), nullable=False),
    Column(
        "status",
        _enum(AiProposalStatus, "ai_proposal_status"),
        nullable=False,
        server_default=text("'proposed'"),
    ),
    Column("job_id", Uuid(), nullable=True),
    Column("job_source_sha256", CHAR(64), nullable=True),
    Column("subject_type", Text(), nullable=True),
    Column("subject_id", Uuid(), nullable=True),
    Column("file_object_id", Uuid(), nullable=True),
    Column("document_text_file_id", Uuid(), nullable=True),
    Column("content", JSONB(), nullable=False),
    Column("citations", JSONB(), nullable=False, server_default=text("'[]'::jsonb")),
    Column("ai_model_log_id", Uuid(), nullable=False),
    Column("accepted_command", Text(), nullable=True),
    Column("field_decisions", JSONB(), nullable=True),
    Column("accepted_object_type", Text(), nullable=True),
    Column("accepted_object_id", Uuid(), nullable=True),
    Column("accepted_by", Uuid(), nullable=True),
    _timestamp("accepted_at", nullable=True),
    Column("rejected_by", Uuid(), nullable=True),
    _timestamp("rejected_at", nullable=True),
    Column("rejection_reason", Text(), nullable=True),
    Column(
        "expires_at",
        DateTime(timezone=True),
        nullable=False,
    ),
    Column("problem", JSONB(), nullable=True),
    *_sc_c_sc_m(),
)


ai_call_intent: Final = Table(
    "ai_call_intent",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("job_id", Uuid(), nullable=False),
    Column("attempt_no", Integer(), nullable=False),
    Column("provider", Text(), nullable=False),
    Column("input_sha256", CHAR(64), nullable=False),
    Column("source_sha256", CHAR(64), nullable=False),
    *_sc_c(),
)
