"""API-R-36 subledger schemas (04 §15.3 API-R-36, §16 API-S-SubledgerLine, T-SL-01, T-SL-02;
BUILD_SPEC CTR-3)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from erev_api.enums import AccountRole, BookCode, SubledgerEntryKind, SubledgerPostingKind
from erev_api.schemas.common import MoneyOut, RefOut


class SubledgerFxRateOut(BaseModel):
    """The rate a foreign-currency line was converted at (REQ-FX-006)."""

    id: uuid.UUID
    rate: str
    rate_set_version_id: uuid.UUID


class SubledgerLineLinksOut(BaseModel):
    explain: str
    event: str | None
    schedule_line: str | None
    source_row: str | None


class SubledgerLineOut(BaseModel):
    """API-S-SubledgerLine: amounts signed debit positive (research 06 §4.2)."""

    id: uuid.UUID
    posting_id: uuid.UUID
    posting_kind: SubledgerPostingKind
    entity: RefOut
    book: BookCode
    period_key: str
    origin_period_key: str | None
    is_post_reopen: bool
    effective_date: date
    recorded_at: datetime
    entry_no: int
    entry_kind: SubledgerEntryKind
    account_role: AccountRole
    account: RefOut
    dr_cr: str
    amount_txn: MoneyOut
    amount_functional: MoneyOut
    fx_rate: SubledgerFxRateOut | None
    # rev 1.204: never null — every subledger line has a contract (04 T-SL-04)
    contract_id: uuid.UUID
    # rev 1.159: null only when the line's contract is outside the caller's entity scope
    contract_external_id: str | None
    obligation_id: uuid.UUID | None
    # rev 1.245: null without an obligation, and wherever ``contract_external_id`` is null
    obligation_key: str | None
    contract_version_id: uuid.UUID | None
    contract_event_id: uuid.UUID | None
    schedule_line_id: uuid.UUID | None
    journal_run_id: uuid.UUID | None
    reason_code: str | None
    links: SubledgerLineLinksOut


class ControlTotalOut(BaseModel):
    """One T-SL-02 control total: debits and credits of an entity, period and transaction currency,
    as the seal trigger stores them (``erev.money`` text)."""

    entity_id: uuid.UUID
    period_id: uuid.UUID
    currency: str
    debit_txn: str
    credit_txn: str
    debit_functional: str
    credit_functional: str


class SubledgerSealOut(BaseModel):
    """T-SL-02: the seal of a posting."""

    chain_seq: int
    line_count: int
    control_totals: list[ControlTotalOut]
    prev_seal_sha256: str | None
    seal_sha256: str
    sealed_at: datetime


class SubledgerPostingOut(BaseModel):
    """T-SL-01 columns with the seal (L3-1-Q-31)."""

    id: uuid.UUID
    book: BookCode
    posting_kind: SubledgerPostingKind
    combination_group_id: uuid.UUID | None
    contract_computation_id: uuid.UUID | None
    close_run_id: uuid.UUID | None
    manual_adjustment_id: uuid.UUID | None
    reverses_posting_id: uuid.UUID | None
    idempotency_key: str
    description: str
    created_at: datetime
    seal: SubledgerSealOut
