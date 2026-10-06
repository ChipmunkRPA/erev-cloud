"""API-R-40 reconciliation schemas (04 §15.3 API-R-40, §16.8 API-S-ReconciliationCreate,
API-S-ReconciliationAttach, API-S-Reconciliation, API-S-ReconciliationItem, "Reconciliation
commands"; T-CLS-06 to T-CLS-08; E-58, E-59, E-99; SCREENS_B §2.1, §2.2; BUILD_SPEC CLO-16, CLO-17).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import (
    BookCode,
    JobState,
    ReconciliationKind,
    ReconciliationStatus,
    SignoffRole,
)
from erev_api.money import MoneyOut
from erev_api.schemas.common import ActorOut, RefOut
from erev_api.schemas.periods import MEMO_LENGTH

CODE_LENGTH: Final = 64
PERIOD_KEY_LENGTH: Final = 16
# SCREENS_B §2.2 "Explain difference": "Explanation (required)", minimum 10 characters.
EXPLANATION_MIN_LENGTH: Final = 10
# PRD BR-PLT-08: a reopen carries a comment of at least 10 characters.
REASON_MIN_LENGTH: Final = 10

# 04 T-CLS-07 ``item_kind`` (``ck_reconciliation_item__item_kind``).
ReconciliationItemKind = Literal[
    "UNMATCHED_SOURCE",
    "UNMATCHED_SUBLEDGER",
    "AMOUNT_VARIANCE",
    "UNPOSTED_BATCH",
    "TIMING",
    "DIRECT_GL_ENTRY",
    "OTHER",
    "NOT_STATED",
]
# The contract balance roles a subledger-to-GL reconciliation compares per role (04 T-CLS-06 "Role
# basis", rev 1.253; supervisor rulings R-69 (a), R-74 (b)).
ReconciliationAccountRole = Literal["CONTRACT_LIABILITY", "CONTRACT_ASSET", "UNBILLED_RECEIVABLE"]


class ReconciliationCreateIn(BaseModel):
    """API-S-ReconciliationCreate: ``POST /reconciliations`` answers 202 API-S-Job."""

    model_config = ConfigDict(extra="forbid")

    kind: ReconciliationKind
    entity_code: str = Field(min_length=1, max_length=CODE_LENGTH)
    book: BookCode | None = Field(default=None, description="Default the primary book")
    period_key: str = Field(min_length=1, max_length=PERIOD_KEY_LENGTH)


class ReconciliationAttachIn(BaseModel):
    """API-S-ReconciliationAttach: ``POST /reconciliations/{id}/attach-trial-balance`` answers 202
    API-S-Job. Either ``{source: "ADAPTER", integration_connection_id}`` — pull the trial balance
    through the GL connection — or ``{file_id}`` of an uploaded ``IMPORT_SOURCE`` file (SCREENS_B
    §2.2 data bindings)."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["ADAPTER"] | None = None
    integration_connection_id: uuid.UUID | None = None
    file_id: uuid.UUID | None = None


class ReconciliationPeriodOut(BaseModel):
    id: uuid.UUID
    period_key: str
    name: str
    start_date: date
    end_date: date


class ReconciliationContractOut(BaseModel):
    id: uuid.UUID
    external_id: str


class ReconciliationNotStatedOut(BaseModel):
    """Why a role row states no subledger amount, and the contracts concerned (supervisor ruling
    R-74 (a); SCREENS_B §2.2 "Not stated by the subledger"). ``contracts`` names those the reader
    reads and ``contract_count`` counts all of them (04 §16.8 rev 1.253). The two differ only
    where a contract named lies outside the reader's entity scope, which no posting of the
    engine produces today: a contract's balances are held with its own contracting entity (04
    T-CLS-06 "Role basis", the correction of rev 1.259)."""

    reason: str
    contracts: list[ReconciliationContractOut]
    contract_count: int


class ReconciliationTotalOut(BaseModel):
    """One T-CLS-06 ``totals`` row: an account (null for a billing reconciliation, whose documents
    carry none) and currency with the subledger amount, the source amount and
    ``difference`` = source − subledger. A subledger-to-GL row of a contract balance role (rev
    1.253) carries ``account_role`` and ``account_codes`` — ``account_code`` too when the role
    has one account — and, when the subledger states no amount for the role, ``not_stated``:
    then ``subledger_amount`` and ``difference`` are null."""

    account_code: str | None
    account_role: ReconciliationAccountRole | None = None
    account_codes: list[str] = Field(default_factory=list)
    currency: str
    subledger_amount: MoneyOut | None
    source_amount: MoneyOut | None
    difference: MoneyOut | None
    not_stated: ReconciliationNotStatedOut | None = None


class ReconciliationSummaryOut(BaseModel):
    """One currency of ``totals``: the key figures of SCREENS_B §2.2, summed by the server because
    a client never sums money (dev-guide DG-FE-08). ``account_count`` counts the distinct accounts
    the currency's rows name (0 for a billing reconciliation); ``not_stated_count`` the rows that
    state no subledger amount (supervisor ruling R-74)."""

    currency: str
    account_count: int
    subledger_amount: MoneyOut
    source_amount: MoneyOut
    difference: MoneyOut
    not_stated_count: int


class ReconciliationNamedOut(BaseModel):
    """``{id, name}`` of a general-ledger connection or of a stored file."""

    id: uuid.UUID
    name: str


class ReconciliationProblemOut(BaseModel):
    """The four base members of the problem a failed attach ended with. The other members — the
    ``failures`` of a pull with the adapter's message — stay with ``GET /jobs/{id}`` and
    ``GET /sync-runs/{id}`` and their readers (04 API-R-11)."""

    type: str
    title: str
    status: int
    detail: str | None


class ReconciliationAttachJobOut(BaseModel):
    """The job of an ``attach-trial-balance`` request as every reader of the reconciliation sees
    it; API-S-Job itself is read by the job's initiator and holders of ``audit.read`` only."""

    id: uuid.UUID
    state: JobState
    created_by: ActorOut
    created_at: datetime
    finished_at: datetime | None
    problem: ReconciliationProblemOut | None


class ReconciliationTrialBalanceOut(BaseModel):
    """API-S-Reconciliation ``trial_balance``: the latest ``attach-trial-balance`` request of a
    subledger-to-GL reconciliation. ``attached_at`` is null until the reconciliation has its
    source: the time the trial balance was pulled, or the uploaded file compared."""

    source: Literal["ADAPTER", "FILE"]
    integration_connection: ReconciliationNamedOut | None
    file: ReconciliationNamedOut | None
    job: ReconciliationAttachJobOut
    attached_at: datetime | None


class ReconciliationSignoffOut(BaseModel):
    """A T-CLS-08 sign-off of the reconciliation; ``subject_content_sha256`` is the hash of the
    snapshot the signer signed."""

    id: uuid.UUID
    role: SignoffRole
    signer: ActorOut
    statement: str
    subject_content_sha256: str
    signed_at: datetime


class ReconciliationRuleOut(BaseModel):
    """The published rule a reconciliation was auto-certified under (REQ-CLS-017): SCREENS_B §2.1
    caption "under <rule key> v<n>"."""

    rule_set_version_id: uuid.UUID
    rule_id: uuid.UUID
    rule_set_code: str
    version_no: int
    rule_key: str


class ReconciliationOut(BaseModel):
    """API-S-Reconciliation: a T-CLS-06 row with its entity, period and sign-offs. ``is_current`` is
    false once a later reconciliation of the same kind, entity, book and period was generated.
    ``gl_connections`` names the connections a trial balance can be pulled through, for a caller
    whose ``recon.prepare`` covers the entity (supervisor ruling R-68 (c))."""

    id: uuid.UUID
    reconciliation_no: str
    kind: ReconciliationKind
    entity: RefOut
    book: BookCode
    period: ReconciliationPeriodOut
    status: ReconciliationStatus
    is_current: bool
    as_of_known_at: datetime
    period_lock_id: uuid.UUID | None
    source_file_id: uuid.UUID | None
    sync_run_id: uuid.UUID | None
    totals: list[ReconciliationTotalOut]
    summary: list[ReconciliationSummaryOut]
    trial_balance: ReconciliationTrialBalanceOut | None
    gl_connections: list[ReconciliationNamedOut]
    variance_count: int
    unexplained_other_amount: MoneyOut | None
    auto_certify_rule: ReconciliationRuleOut | None
    report_run_id: uuid.UUID | None
    certified_at: datetime | None
    signoffs: list[ReconciliationSignoffOut]
    created_by: ActorOut
    created_at: datetime
    updated_at: datetime
    row_version: int


class ReconciliationItemOut(BaseModel):
    """API-S-ReconciliationItem: a T-CLS-07 difference with its classification and explanation.
    ``account_role`` names the role row of ``totals`` the item belongs to (rev 1.253)."""

    id: uuid.UUID
    reconciliation_id: uuid.UUID
    item_kind: ReconciliationItemKind
    account_code: str | None
    account_role: ReconciliationAccountRole | None = None
    contract: ReconciliationContractOut | None
    invoice_number: str | None
    gl_document_reference: str | None
    currency: str
    subledger_amount: MoneyOut | None
    source_amount: MoneyOut | None
    difference: MoneyOut
    is_high_risk: bool
    explanation: str | None
    resolved_at: datetime | None
    resolved_by: ActorOut | None
    row_version: int


class ReconciliationItemUpdateIn(BaseModel):
    """``PATCH /reconciliations/{id}/items/{item_id}`` (``If-Match`` of the item)."""

    model_config = ConfigDict(extra="forbid")

    explanation: str = Field(min_length=EXPLANATION_MIN_LENGTH, max_length=MEMO_LENGTH)


class ReconciliationSignIn(BaseModel):
    """``POST /reconciliations/{id}/sign``: the reviewer's sign-off (SCREENS_B §2.2)."""

    model_config = ConfigDict(extra="forbid")

    role: SignoffRole
    statement_accepted: bool


class ReconciliationReopenIn(BaseModel):
    """``POST /reconciliations/{id}/reopen``."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=REASON_MIN_LENGTH, max_length=MEMO_LENGTH)
