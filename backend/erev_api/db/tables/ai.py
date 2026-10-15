"""AI evidence tables (04 T-AI-02; AIX-1)."""

from typing import Final

from sqlalchemy import CHAR, Column, Integer, Table, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB

from erev_api.db.tables import metadata
from erev_api.db.tables.platform import _sc_c

ai_model_log: Final = Table(
    "ai_model_log",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
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
