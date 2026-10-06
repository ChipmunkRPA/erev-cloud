"""API-R-38 journal run schemas (04 §16.7 API-S-JournalRunCreate, API-S-JournalRun,
API-S-JournalLine, API-S-PostingAck, API-S-JournalRunSummary, "Journal commands"; T-SL-06 to
T-SL-10; BUILD_SPEC CLO-8, CLO-11, CLO-13, CLO-14).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from erev_api.enums import (
    AccountRole,
    BookCode,
    GlAdapter,
    JeType,
    JournalRunGrain,
    JournalRunMode,
    JournalState,
    PostingAckKind,
    SubledgerEntryKind,
)
from erev_api.money import MoneyOut
from erev_api.schemas.common import ActorOut, RefOut

CODE_LENGTH: Final = 64
PERIOD_KEY_LENGTH: Final = 16
DOCUMENT_ID_LENGTH: Final = 200
Memo = Annotated[str, StringConstraints(min_length=1, max_length=4000)]
DocumentId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=DOCUMENT_ID_LENGTH)
]


class JournalRunCreateIn(BaseModel):
    """API-S-JournalRunCreate: ``POST /journal-runs`` answers 202 API-S-Job."""

    model_config = ConfigDict(extra="forbid")

    entity_code: str = Field(min_length=1, max_length=CODE_LENGTH)
    book: BookCode | None = Field(default=None, description="Default the primary book; not LEGACY")
    period_key: str = Field(min_length=1, max_length=PERIOD_KEY_LENGTH)
    mode: JournalRunMode | None = Field(default=None, description="Default the POL-005 value")
    grain: JournalRunGrain | None = Field(default=None, description="Default the POL-006 value")
    cutoff_known_at: AwareDatetime | None = Field(default=None, description="Default now")
    close_run_id: uuid.UUID | None = None


class JournalRunSubmitIn(BaseModel):
    """``POST /journal-runs/{id}/submit`` (04 §16.7 "Journal commands")."""

    model_config = ConfigDict(extra="forbid")

    comment: Memo | None = None


class JournalRunCancelIn(BaseModel):
    """``POST /journal-runs/{id}/cancel``: the reason is required (04 §16.7; BR-PLT-08)."""

    model_config = ConfigDict(extra="forbid")

    reason: Memo


class JournalRunExportIn(BaseModel):
    """``POST /journal-runs/{id}/export``: 202 API-S-Job ``JOURNAL_EXPORT`` (04 §16.7)."""

    model_config = ConfigDict(extra="forbid")

    adapter: GlAdapter | None = Field(
        default=None, description="Default the adapter the batches were calculated for"
    )


class PostingAckCreateIn(BaseModel):
    """``POST /journal-batches/{id}/acknowledge`` (04 §16.7 "Journal commands"; PRD BR-JE-03): the
    ERP document reference of the imported batch is required; 201 API-S-PostingAck."""

    model_config = ConfigDict(extra="forbid")

    gl_document_id: DocumentId
    gl_posted_date: date | None = None
    message: Memo | None = None


class JournalRunPeriodOut(BaseModel):
    id: uuid.UUID
    period_key: str
    name: str
    start_date: date
    end_date: date


class JournalRunCoverageOut(BaseModel):
    """The seal ranges ``(from, to]`` the run covers (T-SL-06; DB-16)."""

    from_chain_seq: int
    to_chain_seq: int
    delta_from_chain_seq: int | None
    delta_to_chain_seq: int | None


class JournalRunTotalsOut(BaseModel):
    line_count: int
    debit_functional: MoneyOut
    credit_functional: MoneyOut
    balanced: bool


class PostingAckOut(BaseModel):
    """API-S-PostingAck (T-SL-10)."""

    id: uuid.UUID
    ack_kind: PostingAckKind
    gl_document_id: str | None
    gl_posted_date: date | None
    message: str | None
    response_sha256: str | None
    received_at: datetime
    recorded_by: ActorOut


class JournalBatchOut(BaseModel):
    """A T-SL-07 batch: the API-S-JournalRun ``batches`` members, plus the run, the functional
    totals, the retained detail file, and the export attempts and last error of
    ``GET /journal-batches/{id}`` (SCREENS_B SF-06:run-batches "Attempts", "Last error"; D-87
    L6-5-Q-1)."""

    id: uuid.UUID
    journal_run_id: uuid.UUID
    batch_no: int
    chunk_no: int
    txn_currency: str
    functional_currency: str
    state: JournalState
    line_count: int
    total_debit_txn: MoneyOut
    total_credit_txn: MoneyOut
    total_debit_functional: MoneyOut
    total_credit_functional: MoneyOut
    external_id: str
    adapter: GlAdapter
    detail_file_id: uuid.UUID | None
    detail_sha256: str | None
    attempt_count: int
    last_error: str | None
    exported_at: datetime | None
    acknowledged_at: datetime | None
    # 04 §16.7 rev 1.221: the instant a failed batch of an ERP adapter was handed over for manual
    # posting; null for every other batch
    handed_over_at: datetime | None
    acknowledgements: list[PostingAckOut]
    row_version: int


class JeRangeOut(BaseModel):
    first_je_no: str | None
    last_je_no: str | None
    count: int


class JournalRunOut(BaseModel):
    """API-S-JournalRun (T-SL-06)."""

    id: uuid.UUID
    run_no: str
    entity: RefOut
    book: BookCode
    period: JournalRunPeriodOut
    mode: JournalRunMode
    delta_book: BookCode | None
    grain: JournalRunGrain
    state: JournalState
    cutoff_known_at: datetime
    coverage: JournalRunCoverageOut
    totals: JournalRunTotalsOut
    batches: list[JournalBatchOut]
    je_range: JeRangeOut
    approval_request_id: uuid.UUID | None
    approved_at: datetime | None
    exported_at: datetime | None
    acknowledged_at: datetime | None
    cancelled_at: datetime | None
    created_by: ActorOut
    created_at: datetime
    updated_at: datetime
    row_version: int


class JournalEntryOut(BaseModel):
    """A T-SL-08 journal entry of ``GET /journal-runs/{id}/entries``."""

    id: uuid.UUID
    journal_batch_id: uuid.UUID
    je_seq: int
    je_no: str
    je_type: JeType
    entry_kind: SubledgerEntryKind | None
    description: str
    is_post_close: bool
    source_event_ids: list[uuid.UUID]
    manual_adjustment_id: uuid.UUID | None
    reverses_journal_entry_id: uuid.UUID | None
    line_count: int
    created_at: datetime


class JournalLineContractOut(BaseModel):
    id: uuid.UUID
    # rev 1.245: null only when the contract is outside the caller's entity scope (T-CON-01 is
    # RLS-TE); the id is the line's own and stays, as on API-S-SubledgerLine
    external_id: str | None


class JournalLineLinksOut(BaseModel):
    drill: str


class JournalLineOut(BaseModel):
    """API-S-JournalLine (T-SL-09)."""

    id: uuid.UUID
    journal_batch_id: uuid.UUID
    je_no: str
    je_type: JeType
    line_no: int
    account: RefOut
    account_role: AccountRole
    dimensions: dict[str, str]
    txn_currency: str
    debit_txn: MoneyOut
    credit_txn: MoneyOut
    debit_functional: MoneyOut
    credit_functional: MoneyOut
    contract: JournalLineContractOut | None
    obligation_key: str | None
    legacy_key: str | None
    counterparty_entity: RefOut | None
    origin_period_key: str | None
    is_post_close: bool
    fx_rate_ids: list[uuid.UUID]
    memo: str | None
    source_line_count: int
    source_grouping_sha256: str
    links: JournalLineLinksOut


class JournalSummaryLineOut(BaseModel):
    account_code: str
    account_name: str
    currency: str
    debit: MoneyOut
    credit: MoneyOut


class JournalBalanceCheckOut(BaseModel):
    entity_code: str
    currency: str
    basis: Literal["TRANSACTION", "FUNCTIONAL"]
    debit: MoneyOut
    credit: MoneyOut
    difference: MoneyOut


class JournalRunSummaryOut(BaseModel):
    """API-S-JournalRunSummary (rev 1.2; SCREENS_B OQ-B-07), computed from the run's lines."""

    lines: list[JournalSummaryLineOut]
    balance_checks: list[JournalBalanceCheckOut]
