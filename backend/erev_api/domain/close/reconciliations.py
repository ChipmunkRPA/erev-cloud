"""Reconciliations of the period close (03 REQ-CLS-015 to REQ-CLS-017; 04 §15.3 API-R-40, §16.8
API-S-Reconciliation, T-CLS-06 to T-CLS-08, T-SRC-04, T-SRC-05, §14.1 DB-03, DB-10; PRD §5.2 SM-09,
§5.6 ACT-33, ACT-34, SoD-7; SCREENS_B §2.1, §2.2; research 07 RC-01 to RC-03; dev-guide DG-CMD-01
to DG-CMD-08; BUILD_SPEC CLO-16, CLO-17, BS4-D-09; controls CTL-024, CTL-025, CTL-026).

``request_generation`` accepts ``POST /reconciliations`` and defers the generating job;
``generate`` inserts the reconciliation in ``DRAFT`` with its totals and its itemised differences
and records the control execution (``RECONCILIATION_RUN``, the reconciliation's own id).
``request_trial_balance`` accepts ``attach-trial-balance`` for a subledger-to-GL reconciliation and
defers the job that pulls or reads the trial balance and compares it (``attach``).
``explain_item`` stores the explanation of a difference while the reconciliation is ``DRAFT``;
``prepare`` signs it as preparer (``PREPARED``), ``sign`` as reviewer (``REVIEWED``) and ``reopen``
returns a signed reconciliation to ``REOPENED``. The reads answer API-S-Reconciliation and
API-S-ReconciliationItem inside the caller's ``contract.read`` entity scope (REQ-PLT-012).

Billing to subledger (REQ-CLS-015; research 07 RC-01). For one entity and period the billing
system's documents — the ``source_invoice`` rows of the entity issued in the period, the newest
stored version of each (``source_system``, ``external_invoice_id``) — are matched with the
contract billing events of the entity dated in the period: the kept ``BILLING_RECORDED`` lines of
ENGINE_SPEC_B S10-R-07 (``erev_engine.billing_identity``: a status update of a line adds no
billing) and the ``CREDIT_MEMO_RECORDED`` events, less the events an ``EVENT_VOIDED`` names and the
streams of voided contracts. Documents match by kind, invoice number and currency and by amount.
A document of one side only is ``UNMATCHED_SOURCE`` or ``UNMATCHED_SUBLEDGER``; one of both sides
with different amounts is ``AMOUNT_VARIANCE``, carrying the contract when the document belongs to
one. Tolerance is zero on counts and on amounts (RC-01), so every item counts as a variance and
needs an explanation before the preparer signs.

Subledger to GL (REQ-CLS-016, REQ-INT-009; research 07 RC-02). Generation inserts the ``DRAFT``
reconciliation without a source; ``attach-trial-balance`` gives it one trial balance — pulled
through the entity's GL connection (``GLAdapter.pull_trial_balance``; a ``TRIAL_BALANCE_PULL`` sync
run, ``sync_run_id``) or read from an uploaded file of ``account``, ``currency``, ``amount``
(``source_file_id``) — and compares it with the subledger as the reconciliation was generated
(``trial_balance.compare``: closing balances in the functional currency, by account; the classes
``UNPOSTED_BATCH``, ``TIMING``, ``DIRECT_GL_ENTRY`` with its GL document and ``OTHER``). The source
is written once: another trial balance needs another generation. The subledger side is every line
of the postings sealed up to the chain position the generation read (``ledger_chain_seq``); a
line sealed later refuses the attach.

What a reconciliation read (item REC-GEN-LOCK-1; 04 T-CLS-06 rev 1.259; the supervisor's rulings
of 2026-10-01 21:41 and 22:52 and of 2026-10-02 00:09 and 01:41). A generation records the book's
ledger chain position — read plainly, first — and how many documents it depends on beside the
ledger. For billing to subledger: the source invoices of the period and, of the contracts billed
in it, the billing events dated through the period's last day and the voids. For subledger to
GL: the contract events of the entity dated through the period's last day and their inclusions
in a contract version of the book — what moves the stored closing balances of the role basis,
an event when it is recorded and again when it is computed; a generation counts them up to its
own ``as_of_known_at``, which is what its attach reads. The gate reads a reviewed
reconciliation as out of date by those (``gates.overtaken``): a later seal in scope, or a count
that differs. A time cannot decide it — a line's ``recorded_at`` is the start of its unit of
work, so a posting that began before a generation and committed after it is older than the
reconciliation by every clock stored; the chain sequence is the commit order of the book's
postings. No lock is taken: nothing waits for a generation and a generation waits for nothing
(supervisor ruling R-68 (b)'s lock is replaced).

The role basis (supervisor rulings R-69 (a), R-74; 04 T-CLS-06 "Role basis", rev 1.253). The
three contract balance roles ``CONTRACT_LIABILITY``, ``CONTRACT_ASSET`` and
``UNBILLED_RECEIVABLE`` are compared per role: the subledger side is the stored closing contract
balances of the entity's contracts at the period end (``reports.tie_outs.balances_at``: the
S15-R-07a period nodes of the latest versions recorded by ``as_of_known_at``), the source of the
contract balance rollforward and not a second derivation — so a ledger kept by the ERP, which
posts its own invoices to the contract liability account (``billing.posting = ERP``), ties, and so
does a migrated opening balance. The ledger side is the sum of the role's accounts: the rules of
the mapping in force for the entity and book, and the accounts that carry subledger lines posted
with the role. A balance is stated in the functional currency when the contract's transaction
currency is the functional currency, or when the reconciled period is the latest period of its
version (04 T-CON-09 stores the functional balance of that period only); otherwise the role's row
is "not stated": no subledger amount, the contracts and the reason named, one ``NOT_STATED`` item
the preparer explains. The platform translates no balance (item ENG-FUNC-BALANCE-NODE-1). A
ledger document made in the ERP whose number is an invoice or credit memo number of the entity is
ERP billing and raises no item (R-74 (d)).

Auto-certification (REQ-CLS-017; BS4-D-09; research 07 RC-03). A reconciliation whose comparison
is complete at generation and shows no variance is certified by the published ``AUTO_APPROVAL``
rule that matches its facts (``reconciliation.kind``, ``reconciliation.variance_count``,
``reconciliation.unexplained_other_amount``): the rule's ids are written with the row, the row
moves ``DRAFT → AUTO_CERTIFIED`` and the control execution names the rule. Only rules carrying a
``reconciliation.kind`` condition are read here (supervisor ruling R-38 (v)); any variance leaves
the row ``DRAFT`` for its preparer and reviewer. T-CLS-06 records the certifying rule at insert
only, so a subledger-to-GL reconciliation — compared at the attach — is never auto-certified in
1.0 (known limitation REC-AUTO-GL-1; supervisor ruling R-58 (e)).

[J] Judgements of lane F-CLO-B (none changes a documented figure):

- ``difference`` = ``source_amount`` − ``subledger_amount`` on totals and items (the figures of
  BUILD_SPEC CLO-16 and CLO-17: a source-only amount of 100,000.00 and a GL-only amount of 250.00
  are differences of 100,000.00 and 250.00); amounts are signed, credit memos negative (T-SRC-04).
- Amounts compare net of tax: ``source_invoice.total_amount`` against the events' ``amount``
  (``tax_amount`` is carried beside both).
- A billing reconciliation's ``totals`` rows carry no account: one row per currency.
- An explained item is resolved: ``resolved_at`` and ``resolved_by`` are the explanation's.
- Every generation inserts a new row; the current reconciliation of a kind, entity, book and
  period is the latest generated (``gates.superseded``), and a command on a superseded row is
  refused. SM-09's ``REOPENED`` row is never reused (04 rev 1.37; D-98 79).
- A sign-off needs an MFA-verified session (T-CLS-08 ``mfa_verified_at``; the checklist sign of
  CLO-4), the reviewer's a step-up within BR-PLT-06's window (ACT-34). The SM-09 guard "not an
  Integration Admin" refuses any reviewer holding ``integration.manage`` (SoD-7), beside the route
  permission. Both sign-offs store the hash of the same snapshot: the reviewer's is refused when
  the snapshot no longer hashes to the preparer's.
- Subledger to GL. The accounts compared are the subledger-controlled ones (supervisor ruling
  R-69 (c)): those carrying a subledger line of the entity and book through the period end —
  what the subledger posts to (research 07 RC-02 "deferred revenue, contract assets / unbilled
  AR, and revenue") — and those the account mapping in force gives the ``CONTRACT_LIABILITY`` and
  ``CONTRACT_ASSET`` roles for the entity, controlled before their first line. The rest of the
  mapping is not the scope: it names roles the engine does not post, as ``ACCOUNTS_RECEIVABLE``
  under ``billing.posting = ERP`` (POLICIES §0.8). Other rows of a trial balance are not
  compared. Two limits of this scope: a clearing account (``BILLING_CLEARING``,
  ``CONTRACT_COST_CLEARING``) carries engine lines and, by its definition, the other subledger's
  documents; and under ``billing.posting = ERP`` the contract liability account carries the
  invoices the ERP posts (POLICIES JET-03), which are no subledger lines — which is why the three
  contract balance roles are compared on the role basis above (supervisor rulings R-69, R-74,
  pending the accountant and the ITGC owner) and every other account on its posted lines (T-SL-04).
  An item of a batch carries the batch's ADP-10 external id as its reference (a ``TIMING`` item
  the GL document of its acknowledgement). A subledger-to-GL reconciliation is signed only with a
  trial balance attached.
- Role basis. (a) What another role posted on a role's accounts (T-SL-04 ``account_role``) is
  added to the role's stored balance, so the row compares everything the subledger holds on those
  accounts. (b) An account that two of the three roles reach — by the mapping or by posted lines —
  cannot be split by the ledger: both roles are "not stated", and the account's ledger balance is
  carried once, on the row of the first of them in the order contract liability, contract asset,
  unbilled receivable. (c) Balances the reader refuses (``BalanceUnreadable``, S15-R-07a) make
  all three roles "not stated", naming the contracts: no figure is served in place of a balance.
  (d) A role without an account and without a balance has no row. (e) A ``NOT_STATED`` item
  stores the ledger's balance as ``source_amount`` and as ``difference`` (T-CLS-07 ``difference``
  is NOT NULL) and no subledger amount; the row of ``totals`` shows neither. (f) A not-stated
  role keeps its ``DIRECT_GL_ENTRY`` items — a document made in the ERP is a finding whatever
  the subledger states — and has no batch item and no ``OTHER``.
- The control execution of CTL-026 is ``PASS`` for a certified reconciliation and
  ``NOT_APPLICABLE`` for one the control left to its preparer and reviewer (a variance, or no
  published rule for its facts).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine import billing_identity
from erev_engine import rules as engine_rules
from erev_engine.canonical import sha256_hex
from erev_engine.currencies import ISO_4217
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from sqlalchemy import Select, and_, any_, func, insert, or_, select, tuple_
from sqlalchemy.orm import Session

from erev_api import numbering
from erev_api.audit.writer import record_facts
from erev_api.auth import mfa
from erev_api.auth.dependencies import require_for_entity
from erev_api.auth.principal import Principal, RequestContext
from erev_api.controls.evidence import RunRefType, record_execution
from erev_api.db import new_id, transitions
from erev_api.db.session import tenant_session
from erev_api.db.tables import (
    account_mapping_rule,
    account_mapping_version,
    contract,
    contract_event,
    contract_version_balance,
    control_execution,
    file_object,
    gl_account,
    integration_connection,
    job,
    journal_batch,
    journal_line,
    journal_run,
    ledger_chain_head,
    legal_entity,
    period,
    period_state,
    posting_ack,
    reconciliation,
    reconciliation_item,
    rule,
    rule_set,
    rule_set_version,
    signoff,
    source_invoice,
    source_invoice_line,
    subledger_line,
    subledger_posting_seal,
    sync_run,
    tenant,
)
from erev_api.domain.close import freeze, gates, trial_balance
from erev_api.domain.contracts.queries import primary_book
from erev_api.domain.imports import parse
from erev_api.domain.imports.job_items import failed_item
from erev_api.domain.integrations.ports import ControlTotals
from erev_api.domain.integrations.sync import (
    NOT_APPLIED_DETAIL,
    SYNC_OBJECTS_NOT_APPLIED,
    SYNC_RUN_INSTANCE,
    version_rank,
)
from erev_api.domain.journals import ports as gl_ports
from erev_api.domain.platform import approval_queries, file_access
from erev_api.domain.platform.jobs import job_out_of
from erev_api.domain.reports import tie_outs
from erev_api.enums import (
    AccountRole,
    AccountType,
    BookCode,
    ConfigStatus,
    ContractEventType,
    ControlResult,
    ExceptionSource,
    FilePurpose,
    GlAdapter,
    JobKind,
    JobState,
    JournalState,
    PostingAckKind,
    PrincipalKind,
    ReconciliationKind,
    ReconciliationStatus,
    RuleSetKind,
    SignoffRole,
    SubledgerEntryKind,
    SyncRunStatus,
)
from erev_api.events.outbox import Undeliverable
from erev_api.explain import store as trace_store
from erev_api.files import policy as file_policy
from erev_api.files.store import lock_readable, open_file
from erev_api.jobs.context import JobContext
from erev_api.jobs.registry import FailedSubject, JobOutcome, RetryPolicy, task
from erev_api.money import MoneyOut
from erev_api.periods import period_by_key
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.common import JobOut
from erev_api.schemas.reconciliations import (
    ReconciliationAttachIn,
    ReconciliationCreateIn,
    ReconciliationItemOut,
    ReconciliationItemUpdateIn,
    ReconciliationOut,
    ReconciliationReopenIn,
    ReconciliationSignIn,
)

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

READ_PERMISSION: Final = "contract.read"  # 04 API-R-40
PREPARE_PERMISSION: Final = "recon.prepare"  # PRD ACT-33
SIGNOFF_PERMISSION: Final = "recon.signoff"  # PRD ACT-34
# A reopen discards the reviewer's sign-off, so it takes the reviewer's permission (SM-09;
# supervisor ruling R-54 (c)).
REOPEN_PERMISSION: Final = SIGNOFF_PERMISSION
GENERATE_JOB: Final = JobKind.RECONCILIATION_GENERATE  # 04 E-14 rev 1.121; 05 §5.6 queue close
GENERATE_RETRY: Final = RetryPolicy(max_attempts=2)  # 05 §5.6: 2 attempts
MICROSECOND: Final = timedelta(microseconds=1)
INTEGRATION_PERMISSION: Final = "integration.manage"  # PRD ACT-45; SoD-7 function A
OBJECT_TYPE: Final = "reconciliation"
ITEM_OBJECT: Final = "reconciliation_item"
SERIES: Final = "RECONCILIATION"  # T-PLT-26
HREF: Final = "/api/v1/reconciliations/{reconciliation_id}"
REQUEST_ACTION: Final = "reconciliation.request_generation"
GENERATE_ACTION: Final = "reconciliation.generate"
ITEM_CREATE_ACTION: Final = "reconciliation_item.create"
EXPLAIN_ACTION: Final = "reconciliation_item.explain"
PREPARE_ACTION: Final = "reconciliation.prepare"
SIGN_ACTION: Final = "reconciliation.sign"
REOPEN_ACTION: Final = "reconciliation.reopen"
ATTACH_REQUEST_ACTION: Final = "reconciliation.request_trial_balance"
ATTACH_ACTION: Final = "reconciliation.attach_trial_balance"
AUTO_CERTIFY_ACTION: Final = "reconciliation.auto_certify"
CONTROL_BILLING: Final = "CTL-024"
CONTROL_GL: Final = "CTL-025"
CONTROL_AUTO_CERTIFY: Final = "CTL-026"
RULE_STATES: Final = "SM-09"
RULE_ROW: Final = "T-CLS-06"
RULE_ITEM: Final = "T-CLS-07"
RULE_STATEMENT: Final = "STATEMENT_NOT_ACCEPTED"
RULE_SOD: Final = "SoD-7"
RULE_SOURCE: Final = "REQ-CLS-016"
ATTACH_PARAM: Final = "attach"  # the job parameter of an ``attach-trial-balance`` request
TRIAL_BALANCE_PULL: Final = "TRIAL_BALANCE_PULL"  # 04 T-INT-02 ``kind``
TRIAL_BALANCE_OBJECT: Final = "trial_balance"  # T-INT-02 ``problem.failures[].object_type``
FETCH_STEP: Final = "fetch"  # T-INT-02 ``problem.failures[].step``
# The T-INT-01 adapters that serve a trial balance (03 REQ-INT-009; BUILD_SPEC CLO-15), with their
# E-37 literal; a CSV GL connection exports files and states no balance.
TRIAL_BALANCE_ADAPTERS: Final[Mapping[str, GlAdapter]] = {
    "NETSUITE": GlAdapter.NETSUITE,
    "QUICKBOOKS_ONLINE": GlAdapter.QUICKBOOKS_ONLINE,
}
ACTIVE_CONNECTION: Final = "ACTIVE"
# E-52: the account types whose balance is cumulative; the others are fiscal year to date.
BALANCE_SHEET_TYPES: Final = frozenset(
    {AccountType.ASSET.value, AccountType.LIABILITY.value, AccountType.EQUITY.value}
)
# E-36: the acknowledgements that mean the GL holds the batch.
POSTED_ACKS: Final = (
    PostingAckKind.POSTED.value,
    PostingAckKind.DUPLICATE.value,
    PostingAckKind.MANUAL_CONFIRMATION.value,
)
# E-01: the contract balance roles compared on the role basis (supervisor rulings R-69 (a), R-74
# (b)), in row order, each with the T-CON-09 balance it reads and that balance's sign in a trial
# balance (debit positive: a liability is a credit). Their accounts are controlled before their
# first line (R-69 (c)).
POSITION_ROLES: Final[Mapping[str, tuple[str, int]]] = {
    AccountRole.CONTRACT_LIABILITY.value: ("contract_liability", -1),
    AccountRole.CONTRACT_ASSET.value: ("contract_asset", 1),
    AccountRole.UNBILLED_RECEIVABLE.value: ("unbilled_receivable", 1),
}
CONTROL_ROLES: Final = tuple(POSITION_ROLES)
# SCREENS_B §2.2 "Not stated by the subledger": the reasons of a role row without an amount.
NOT_STATED_FOREIGN: Final = (
    "{count} contract(s) in another currency than {functional} hold no {functional} balance at "
    "{period_key}: the functional balance is stored for a contract version's latest period only."
)
NOT_STATED_UNREADABLE: Final = (
    "The balances of {count} contract(s) at {period_key} cannot be read from their calculation "
    "traces."
)
NOT_STATED_SHARED: Final = (
    "Account(s) {accounts} carry {role} and {others}; the ledger does not tell them apart. Map "
    "each contract balance role to accounts of its own."
)
ACTIVE_JOBS: Final = (JobState.QUEUED.value, JobState.RUNNING.value)
# The facts of an auto-certification rule (BS4-D-09; ``erev_engine.rules.FIELDS``).
KIND_FACT: Final = "reconciliation.kind"
VARIANCE_FACT: Final = "reconciliation.variance_count"
OTHER_AMOUNT_FACT: Final = "reconciliation.unexplained_other_amount"

# 04 T-CLS-07 ``item_kind``.
UNMATCHED_SOURCE: Final = "UNMATCHED_SOURCE"
UNMATCHED_SUBLEDGER: Final = "UNMATCHED_SUBLEDGER"
AMOUNT_VARIANCE: Final = "AMOUNT_VARIANCE"
UNPOSTED_BATCH: Final = "UNPOSTED_BATCH"
TIMING: Final = "TIMING"
DIRECT_GL_ENTRY: Final = "DIRECT_GL_ENTRY"
OTHER: Final = "OTHER"
NOT_STATED: Final = "NOT_STATED"
INVOICE: Final = "INVOICE"
CREDIT_MEMO: Final = "CREDIT_MEMO"

# The kinds ``POST /reconciliations`` generates; the rollforward kinds are report runs of RPS and a
# migration's opening balance reconciliation is written by its batch (fail closed, header XR-12).
ON_DEMAND_KINDS: Final = frozenset(
    {ReconciliationKind.BILLING_TO_SUBLEDGER, ReconciliationKind.SUBLEDGER_TO_GL}
)
# SCREENS_B §2.2: the fixed statements of the sign-offs (T-CLS-08 ``statement``).
PREPARER_STATEMENT: Final = (
    "I prepared this reconciliation and explained every difference above the threshold."
)
REVIEWER_STATEMENT: Final = (
    "I reviewed this reconciliation, its differences and their explanations."
)
# SCREENS_B §2.2 and PRD SM-09 copy.
UNEXPLAINED: Final = "Explain {n} differences above the threshold before signing."
OWN_PREPARATION: Final = "You prepared this reconciliation. Another user must review it."
INTEGRATION_ADMIN: Final = (
    "A user who manages integrations cannot sign a reconciliation as reviewer (SoD-7)."
)
STATEMENT_REQUIRED: Final = "Confirm the statement before signing."
REVIEWER_ONLY: Final = "Sign as reviewer here; the preparer signs with the prepare command."
CERTIFIED: Final = "Certified at lock on {at}. Reopen the period to change it."
NOT_DRAFT: Final = "{no} is {status}. Explanations change only while a reconciliation is a draft."
NOT_PREPARABLE: Final = "{no} is {status}. Only a draft reconciliation is signed as preparer."
NOT_REVIEWABLE: Final = "{no} is {status}. Only a prepared reconciliation is signed as reviewer."
NOT_REOPENABLE: Final = "{no} is {status}. Only a prepared or reviewed reconciliation is reopened."
SUPERSEDED: Final = "{no} was replaced by {later}. Work on the current reconciliation."
SNAPSHOT_CHANGED: Final = (
    "{no} changed after it was prepared. Reopen it and have it prepared again."
)
PERIOD_NOT_OPEN: Final = (
    "{period_key} is {state} for {entity} in book {book}. A reconciliation is generated and "
    "signed while the period is open, in soft close or reopened."
)
KIND_NOT_ON_DEMAND: Final = "{kind} reconciliations are not generated on demand."
# SCREENS_B §2.2 "No source (subledger to GL)" and its attach states; [J] the refusals' copy.
NO_SOURCE: Final = "Attach a trial balance to {no} before signing."
# 04 T-PLT-29 "A document a rule asks for" (rev 1.216): the source is written once (T-CLS-06), so a
# reconciliation whose file was shredded is generated again.
SOURCE_SHREDDED: Final = (
    "The trial balance of {no} was shredded. Generate the reconciliation again and attach a "
    "trial balance before signing."
)
NOT_GL: Final = "{no} is a {kind} reconciliation. Only a subledger-to-GL one takes a trial balance."
NOT_ATTACHABLE: Final = "{no} is {status}. A trial balance is attached while it is a draft."
SOURCE_ATTACHED: Final = (
    "{no} already has a trial balance. Generate the reconciliation again to compare another one."
)
ATTACH_IN_PROGRESS: Final = "A trial balance is already being attached to {no}."
SUBLEDGER_MOVED: Final = (
    "{count} subledger line(s) were recorded after {no} was generated. Generate the "
    "reconciliation again."
)
ONE_SOURCE: Final = "Give either a GL connection to pull from or an uploaded file, not both."
SOURCE_REQUIRED: Final = "Give a GL connection to pull the trial balance from, or an uploaded file."
FILE_REQUIRED: Final = "Upload the file with purpose IMPORT_SOURCE first."
FILE_TYPE: Final = "A trial balance is a .csv or .xlsx file."
FILE_UNREADABLE: Final = "The file cannot be read as a .csv or .xlsx file."
UNKNOWN_CONNECTION: Final = "No GL connection has this id."
CONNECTION_DISABLED: Final = "{name} is disabled. Enable the connection or upload a CSV instead."
CONNECTION_ENTITY: Final = "{name} does not serve {entity}."
NO_TRIAL_BALANCE: Final = "{name} has no trial balance to pull. Upload a CSV instead."
CURRENCY_NOT_FUNCTIONAL: Final = (
    "The trial balance states amounts in {currencies}; {entity} keeps its ledger in {functional}."
)
RUN_NOT_STARTABLE: Final = "The trial balance pull of {no} is {status} and is not run again."
UNKNOWN_ENTITY: Final = "No entity has this code."
UNKNOWN_PERIOD: Final = "The entity's calendar has no period with this key."
BOOK_NOT_KEPT: Final = "{entity} keeps no {book} state for {period_key}."
CERTIFIED_AT_FORMAT: Final = "%d %b %Y %H:%M UTC"  # SCREENS_B §2.2 "<DD MMM YYYY HH:mm UTC>"
# The gate's own lists and conditions (``gates`` "what a reconciliation read"): a generation reads
# its documents under them, and the gate's "overtaken" test counts under the same ones.
BILLING_TYPES: Final = gates.BILLING_EVENT_TYPES
STREAM_TYPES: Final = gates.BILLING_STREAM_TYPES
SIGNED_STATUSES: Final = frozenset(
    {ReconciliationStatus.PREPARED.value, ReconciliationStatus.REVIEWED.value}
)


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))


def amount_text(amount: Decimal, currency: str) -> str:
    """Money text with exactly the currency's minor-unit decimals (API-C-06). An amount a source
    stored finer than the minor unit keeps its digits: a difference is never rounded away."""
    spec = ISO_4217.get(currency.strip())
    places = 2 if spec is None else int(spec.minor_unit)
    value = Decimal(amount)
    exact = value.quantize(Decimal(1).scaleb(-places))
    if exact == value:
        return format(exact.copy_abs() if exact.is_zero() else exact, "f")
    return format(value, "f").rstrip("0")


def _money(amount: Any, currency: str) -> MoneyOut | None:
    if amount is None:
        return None
    return MoneyOut(amount=amount_text(Decimal(str(amount)), currency), currency=currency.strip())


# --- matching (pure) -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Document:
    """One billing document of one side: a source invoice or credit memo, or the billing events
    of one contract carrying the document's number. ``amount`` is signed (a credit memo is
    negative, 04 T-SRC-04)."""

    document_kind: str
    invoice_number: str
    currency: str
    amount: Decimal
    contract_id: UUID | None = None

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.document_kind, self.invoice_number, self.currency)


@dataclass(frozen=True, slots=True)
class Difference:
    """A T-CLS-07 row before it is stored."""

    item_kind: str
    currency: str
    difference: Decimal
    subledger_amount: Decimal | None = None
    source_amount: Decimal | None = None
    account_code: str | None = None
    contract_id: UUID | None = None
    invoice_number: str | None = None
    is_high_risk: bool = False
    gl_document_reference: str | None = None
    account_role: str | None = None


@dataclass(frozen=True, slots=True)
class Total:
    """A T-CLS-06 ``totals`` row. A role row (supervisor ruling R-74) carries ``account_role``,
    ``account_codes`` and, when the subledger states no amount, ``not_stated``; then it has no
    subledger amount and no difference."""

    account_code: str | None
    currency: str
    subledger_amount: Decimal | None
    source_amount: Decimal | None
    account_role: str | None = None
    account_codes: tuple[str, ...] = ()
    not_stated: trial_balance.NotStated | None = None

    @property
    def difference(self) -> Decimal | None:
        if self.not_stated is not None:
            return None
        return (self.source_amount or Decimal(0)) - (self.subledger_amount or Decimal(0))

    def as_json(self) -> dict[str, Any]:
        def shown(amount: Decimal | None) -> str | None:
            return None if amount is None else amount_text(amount, self.currency)

        row: dict[str, Any] = {
            "account_code": self.account_code,
            "currency": self.currency,
            "subledger_amount": shown(self.subledger_amount),
            "source_amount": shown(self.source_amount),
            "difference": shown(self.difference),
        }
        if self.account_role is not None:
            row["account_role"] = self.account_role
            row["account_codes"] = list(self.account_codes)
            row["not_stated"] = (
                None
                if self.not_stated is None
                else {
                    "reason": self.not_stated.reason,
                    "contracts": [
                        {"id": contract_id, "external_id": external_id}
                        for contract_id, external_id in self.not_stated.contracts
                    ],
                }
            )
        return row


@dataclass(frozen=True, slots=True)
class Outcome:
    """What one generation established: totals, differences and the population compared; and
    how many rows it read on each side to establish them (04 T-CLS-06 ``source_documents_read``,
    ``subledger_documents_read``; item REC-GEN-LOCK-1) — None from the pure comparison, which
    reads nothing."""

    totals: tuple[Total, ...]
    differences: tuple[Difference, ...]
    population: int
    source_documents_read: int | None = None
    subledger_documents_read: int | None = None

    @property
    def variance_count(self) -> int:
        return len(self.differences)


def _one_contract(documents: Iterable[Document]) -> UUID | None:
    found = {item.contract_id for item in documents}
    return next(iter(found)) if len(found) == 1 else None


def match_billing(source: Sequence[Document], billed: Sequence[Document]) -> Outcome:
    """Match the billing system's documents with the contract billing events by kind, invoice
    number and currency and by amount (REQ-CLS-015; module docstring)."""
    by_source: dict[tuple[str, str, str], list[Document]] = {}
    by_billed: dict[tuple[str, str, str], list[Document]] = {}
    for item in source:
        by_source.setdefault(item.key, []).append(item)
    for item in billed:
        by_billed.setdefault(item.key, []).append(item)
    sums: dict[str, list[Decimal]] = {}
    differences: list[Difference] = []
    keys = sorted(set(by_source) | set(by_billed))
    for key in keys:
        kind, number, currency = key
        in_source, in_subledger = by_source.get(key), by_billed.get(key)
        source_amount = (
            None if in_source is None else sum((item.amount for item in in_source), Decimal(0))
        )
        subledger_amount = (
            None
            if in_subledger is None
            else sum((item.amount for item in in_subledger), Decimal(0))
        )
        totals = sums.setdefault(currency, [Decimal(0), Decimal(0)])
        totals[0] += subledger_amount or Decimal(0)
        totals[1] += source_amount or Decimal(0)
        if source_amount is not None and subledger_amount is not None:
            if source_amount == subledger_amount:
                continue
            item_kind = AMOUNT_VARIANCE
        else:
            item_kind = UNMATCHED_SOURCE if subledger_amount is None else UNMATCHED_SUBLEDGER
        del kind
        differences.append(
            Difference(
                item_kind=item_kind,
                currency=currency,
                difference=(source_amount or Decimal(0)) - (subledger_amount or Decimal(0)),
                subledger_amount=subledger_amount,
                source_amount=source_amount,
                contract_id=_one_contract(in_subledger or in_source or ()),
                invoice_number=number,
            )
        )
    return Outcome(
        totals=tuple(
            Total(
                account_code=None,
                currency=currency,
                subledger_amount=amounts[0],
                source_amount=amounts[1],
            )
            for currency, amounts in sorted(sums.items())
        ),
        differences=tuple(differences),
        population=len(keys),
    )


# --- populations ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _StoredEvent:
    """A stored contract event read as ``billing_identity.BillingEvent`` (ENG-06 order)."""

    event_id: UUID
    contract_id: UUID
    event_type: str
    effective_date: date
    record_seq: int
    payload: Mapping[str, object]

    @property
    def event_key(self) -> str:
        return str(self.event_id)

    @property
    def contract_key(self) -> str:
        return str(self.contract_id)

    @property
    def order_key(self) -> tuple[date, int, str]:
        return (self.effective_date, self.record_seq, str(self.event_id))


def _payload_money(payload: Mapping[str, object]) -> tuple[Decimal, str]:
    money = payload.get("amount")
    if not isinstance(money, Mapping):
        raise ValueError("a billing event carries no amount")
    return Decimal(str(money["amount"])), str(money["currency"]).strip()


def source_documents(session: Session, scope: gates.PeriodScope) -> tuple[list[Document], int]:
    """The entity's source invoices and credit memos issued in the period: the newest stored
    version of each (``source_system``, ``external_invoice_id``), with the contract its lines name
    when they name one contract of the tenant; and the number of stored rows read — every
    version (``gates.source_invoices_of``)."""
    rows = session.execute(
        select(
            source_invoice.c.id,
            source_invoice.c.source_system,
            source_invoice.c.external_invoice_id,
            source_invoice.c.external_version,
            source_invoice.c.invoice_number,
            source_invoice.c.document_kind,
            source_invoice.c.currency,
            source_invoice.c.total_amount,
        )
        .where(*gates.source_invoices_of(scope))
        .order_by(source_invoice.c.id)
    ).mappings()
    newest: dict[tuple[str, str], dict[str, Any]] = {}
    read = 0
    for stored in rows:
        read += 1
        identity = (_text(stored["source_system"]), str(stored["external_invoice_id"]))
        held = newest.get(identity)
        if held is None or version_rank(str(stored["external_version"])) >= version_rank(
            str(held["external_version"])
        ):
            newest[identity] = dict(stored)
    references: dict[UUID, set[str]] = {}
    if newest:
        for invoice_id, reference in session.execute(
            select(source_invoice_line.c.source_invoice_id, source_invoice_line.c.contract_ref)
            .where(
                source_invoice_line.c.source_invoice_id.in_([row["id"] for row in newest.values()]),
                source_invoice_line.c.contract_ref.is_not(None),
            )
            .distinct()
        ).tuples():
            references.setdefault(UUID(str(invoice_id)), set()).add(str(reference))
    named = sorted({reference for found in references.values() for reference in found})
    contracts: dict[str, UUID] = {}
    if named:
        contracts = {
            str(external_id): UUID(str(contract_id))
            for contract_id, external_id in session.execute(
                select(contract.c.id, contract.c.external_id).where(
                    contract.c.external_id.in_(named),
                    contract.c.contracting_entity_id == scope.entity_id,
                )
            ).tuples()
        }
    documents: list[Document] = []
    for row in newest.values():
        found = {contracts.get(reference) for reference in references.get(row["id"], set())}
        documents.append(
            Document(
                document_kind=str(row["document_kind"]),
                invoice_number=str(row["invoice_number"]),
                currency=str(row["currency"]).strip(),
                amount=Decimal(row["total_amount"]),
                contract_id=next(iter(found)) if len(found) == 1 else None,
            )
        )
    return documents, read


def billed_documents(session: Session, scope: gates.PeriodScope) -> tuple[list[Document], int]:
    """The contract billing events of the entity dated in the period, one document per contract,
    kind, number and currency: kept ``BILLING_RECORDED`` lines (S10-R-07) and
    ``CREDIT_MEMO_RECORDED`` events, without voided events and voided contracts. The identity of
    a line is fixed over the contract's stream in the order of effective date, so the streams
    are read from their beginning through the period's last day, with every void
    (``gates.billing_streams_of``: an event dated later cannot change which events of the period
    are lines); and the number of stream events read."""
    rows = session.execute(
        select(
            contract_event.c.id,
            contract_event.c.contract_id,
            contract_event.c.event_type,
            contract_event.c.effective_date,
            contract_event.c.record_seq,
            contract_event.c.payload,
            contract_event.c.supersedes_event_id,
        )
        .where(*gates.billing_streams_of(scope))
        .order_by(contract_event.c.effective_date, contract_event.c.record_seq, contract_event.c.id)
    ).mappings()
    events: list[_StoredEvent] = []
    voided_events: set[UUID] = set()
    voided_contracts: set[UUID] = set()
    read = 0
    for row in rows:
        read += 1
        event_type = _text(row["event_type"])
        contract_id = UUID(str(row["contract_id"]))
        if event_type == ContractEventType.EVENT_VOIDED.value:
            if row["supersedes_event_id"] is not None:
                voided_events.add(UUID(str(row["supersedes_event_id"])))
            continue
        if event_type == ContractEventType.CONTRACT_VOIDED.value:
            voided_contracts.add(contract_id)
            continue
        events.append(
            _StoredEvent(
                event_id=UUID(str(row["id"])),
                contract_id=contract_id,
                event_type=event_type,
                effective_date=row["effective_date"],
                record_seq=int(row["record_seq"]),
                payload=row["payload"],
            )
        )
    kept = [
        event
        for event in events
        if event.event_id not in voided_events and event.contract_id not in voided_contracts
    ]
    sums: dict[tuple[str, str, str, UUID], Decimal] = {}

    def add(event: _StoredEvent, kind: str, number: object, sign: int) -> None:
        if not scope.start_date <= event.effective_date <= scope.end_date:
            return
        amount, currency = _payload_money(event.payload)
        key = (kind, str(number), currency, event.contract_id)
        sums[key] = sums.get(key, Decimal(0)) + sign * amount

    for line in billing_identity.kept_lines(kept):
        add(line, INVOICE, line.payload.get("invoice_number"), 1)
    for event in kept:
        if event.event_type == ContractEventType.CREDIT_MEMO_RECORDED.value:
            add(event, CREDIT_MEMO, event.payload.get("credit_memo_number"), -1)
    return [
        Document(
            document_kind=kind,
            invoice_number=number,
            currency=currency,
            amount=amount,
            contract_id=contract_id,
        )
        for (kind, number, currency, contract_id), amount in sorted(
            sums.items(), key=lambda item: (item[0][0], item[0][1], item[0][2], str(item[0][3]))
        )
    ], read


def billing_outcome(session: Session, scope: gates.PeriodScope) -> Outcome:
    """The billing-to-subledger comparison of the period (REQ-CLS-015), with the number of rows
    it read on each side."""
    source, source_read = source_documents(session, scope)
    billed, billed_read = billed_documents(session, scope)
    return dataclasses.replace(
        match_billing(source, billed),
        source_documents_read=source_read,
        subledger_documents_read=billed_read,
    )


def ledger_events_read(session: Session, scope: gates.PeriodScope, as_of: datetime) -> int:
    """What a subledger-to-GL reconciliation depends on beside the ledger, as one number: the
    contract events of the entity's contracts dated on or before the period's last day, plus
    the inclusions of those events in a contract version of the book — read in one statement,
    the expression the gate compares with, bounded by the reconciliation's own ``as_of``
    (``gates.ledger_documents``): the attach reads the versions known at or before that
    instant, so a row beyond it is not one the reconciliation holds. On the role basis the
    subledger side of the three contract balance roles is the stored closing balance, and such
    an event moves it when it is computed — under ``billing.posting = ERP`` a billing event
    without writing a subledger line."""
    return int(session.execute(select(gates.ledger_documents(scope, as_of))).scalar_one())


def chain_position(session: Session, scope: gates.PeriodScope) -> int:
    """The book's ledger chain head as this session reads it now — a plain read, no lock (04
    T-SL-03; T-CLS-06 ``ledger_chain_seq``). A seal takes the head's row lock and holds it to
    commit, so the chain sequence is the commit order of the book's postings: every seal up to
    the value read is committed and visible to every later statement of this transaction, and
    a posting that has not committed yet is sealed after it. A book without a head row has
    sealed nothing: position 0, which every seal is later than (``commands._heads`` reads a
    missing row the same way)."""
    head = session.execute(
        select(ledger_chain_head.c.last_chain_seq).where(
            ledger_chain_head.c.book_code == scope.book_code
        )
    ).scalar_one_or_none()
    return 0 if head is None else int(head)


# --- period and row access -----------------------------------------------------------------------


def _refused(message: str, *, rule_id: str = RULE_STATES, field: str = "status") -> Problem:
    error = ProblemError(field=field, rule_id=rule_id, message=message)
    return Problem("invalid-transition", message, errors=[error])


def _invalid(field: str, message: str, *, rule_id: str = RULE_ROW) -> Problem:
    error = ProblemError(field=field, rule_id=rule_id, message=message)
    return Problem("validation-failed", "1 field needs attention.", errors=[error])


def _stamps(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def period_scope_of(
    session: Session, entity_id: UUID, book_code: str, period_id: UUID, *, share: bool = False
) -> gates.PeriodScope:
    """The scope of the entity, book and period; 404 ``not-found`` when the entity keeps no such
    state. ``share`` holds the state row ``FOR SHARE`` to the end of the transaction, so a lock
    decision (which takes it ``FOR UPDATE`` before it reads a gate) waits for the command and then
    evaluates what the command wrote; postings, which read the state without an exclusive lock,
    are not held."""
    statement = gates.scope_select().where(
        period_state.c.entity_id == entity_id,
        period_state.c.book_code == book_code,
        period_state.c.period_id == period_id,
    )
    if share:
        statement = statement.with_for_update(read=True, of=period_state)
    row = session.execute(statement).mappings().first()
    if row is None:
        raise Problem("not-found")
    return gates.scope_of(row)


def require_open(scope: gates.PeriodScope) -> None:
    """409 ``invalid-transition`` unless the period is ``open``, ``closing`` or ``reopened``: a
    future period has nothing to reconcile, and a closed one changes only after its reopen."""
    if scope.state in gates.EVALUATED_STATES:
        return
    message = PERIOD_NOT_OPEN.format(
        period_key=scope.period_key,
        state=scope.state,
        entity=scope.entity_code,
        book=scope.book_code,
    )
    raise _refused(message, field="period_key")


def _serialise(uow: UnitOfWork, scope: gates.PeriodScope, kind: str) -> None:
    """One writer at a time per kind, entity, book and period (generation and the sign-off
    commands), so "the latest generated" is one row."""
    key = (
        f"erev.reconciliation:{uow.principal.tenant_id}:{scope.entity_id}:{scope.book_code}:"
        f"{scope.period_id}:{kind}"
    )
    uow.session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))


def _same_series(row: Mapping[str, Any]) -> Any:
    return and_(
        reconciliation.c.entity_id == row["entity_id"],
        reconciliation.c.book_code == _text(row["book_code"]),
        reconciliation.c.period_id == row["period_id"],
        reconciliation.c.kind == _text(row["kind"]),
    )


@dataclass(frozen=True, slots=True)
class _Held:
    """A reconciliation locked for a command, with its period."""

    row: Mapping[str, Any]
    scope: gates.PeriodScope

    @property
    def id(self) -> UUID:
        return UUID(str(self.row["id"]))

    @property
    def number(self) -> str:
        return str(self.row["reconciliation_no"])

    @property
    def status(self) -> str:
        return _text(self.row["status"])


def _held(uow: UnitOfWork, reconciliation_id: UUID, permission: str | None) -> _Held:
    """The reconciliation under ``FOR UPDATE`` for a holder of ``permission`` for its entity, else
    404 ``not-found`` (REQ-PLT-012); a job, which acts on a request already admitted, passes no
    permission. Locks in one order: the period state (shared), the series, the row."""
    session = uow.session
    seen = (
        session.execute(select(reconciliation).where(reconciliation.c.id == reconciliation_id))
        .mappings()
        .one_or_none()
    )
    if seen is None:
        raise Problem("not-found")
    entity_id = UUID(str(seen["entity_id"]))
    if permission is not None:
        require_for_entity(uow.ctx, permission, entity_id)
    scope = period_scope_of(
        session, entity_id, _text(seen["book_code"]), UUID(str(seen["period_id"])), share=True
    )
    _serialise(uow, scope, _text(seen["kind"]))
    row = (
        session.execute(
            select(reconciliation).where(reconciliation.c.id == reconciliation_id).with_for_update()
        )
        .mappings()
        .one()
    )
    return _Held(row=dict(row), scope=scope)


def _certified(held: _Held) -> Problem:
    at = held.row["certified_at"]
    shown = "" if at is None else at.strftime(CERTIFIED_AT_FORMAT)
    return _refused(CERTIFIED.format(at=shown))


def _require_current(uow: UnitOfWork, held: _Held) -> None:
    """Refuse a command on a reconciliation a later generation replaced."""
    later = uow.session.execute(
        select(reconciliation.c.reconciliation_no)
        .where(_same_series(held.row), gates.later_than(held.row))
        .order_by(reconciliation.c.as_of_known_at.desc(), reconciliation.c.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if later is not None:
        raise _refused(SUPERSEDED.format(no=held.number, later=later))


def _require_mfa(uow: UnitOfWork) -> None:
    """A sign-off needs an MFA-verified session (T-CLS-08 ``mfa_verified_at``)."""
    principal = uow.principal
    if principal.mfa_verified_at is not None:
        return
    enrolled = principal.id is not None and mfa.has_confirmed_factor(
        principal.id, request_id=uow.ctx.request_id
    )
    raise Problem("mfa-required", mfa.VERIFICATION_REQUIRED if enrolled else mfa.ENROLMENT_REQUIRED)


# --- the snapshot a sign-off signs ---------------------------------------------------------------


def _item_rows(session: Session, reconciliation_id: UUID) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in session.execute(
            select(reconciliation_item)
            .where(reconciliation_item.c.reconciliation_id == reconciliation_id)
            .order_by(reconciliation_item.c.id)
        ).mappings()
    ]


def snapshot(held: _Held, items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The content a preparer and a reviewer sign: the reconciliation's identity, its source, its
    totals and every difference with its explanation. Its SHA-256 is the sign-off's
    ``subject_content_sha256`` (T-CLS-08; "the snapshot hash is stored on the sign-off")."""
    row = held.row

    def shown(amount: Any, currency: str) -> str | None:
        return None if amount is None else amount_text(Decimal(amount), currency)

    other = row["unexplained_other_amount"]
    return {
        "reconciliation_no": held.number,
        "kind": _text(row["kind"]),
        "entity_code": held.scope.entity_code,
        "book_code": held.scope.book_code,
        "period_key": held.scope.period_key,
        "as_of_known_at": row["as_of_known_at"],
        "source_file_id": row["source_file_id"],
        "sync_run_id": row["sync_run_id"],
        "totals": row["totals"],
        "variance_count": int(row["variance_count"]),
        "unexplained_other_amount": shown(other, held.scope.functional_currency),
        "items": [
            {
                "id": item["id"],
                "item_kind": str(item["item_kind"]),
                "account_code": item["account_code"],
                "account_role": item["account_role"],
                "contract_id": item["contract_id"],
                "invoice_number": item["invoice_number"],
                "gl_document_reference": item["gl_document_reference"],
                "currency": str(item["currency"]).strip(),
                "subledger_amount": shown(item["subledger_amount"], str(item["currency"])),
                "source_amount": shown(item["source_amount"], str(item["currency"])),
                "difference": shown(item["difference"], str(item["currency"])),
                "is_high_risk": bool(item["is_high_risk"]),
                "explanation": item["explanation"],
            }
            for item in items
        ],
    }


def _signers(session: Session, reconciliation_id: UUID, role: SignoffRole) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in session.execute(
            select(signoff.c.signer_id, signoff.c.subject_content_sha256)
            .where(
                signoff.c.subject_type == OBJECT_TYPE,
                signoff.c.subject_id == reconciliation_id,
                signoff.c.role == role.value,
            )
            .order_by(signoff.c.signed_at, signoff.c.id)
        ).mappings()
    ]


def _sign(
    uow: UnitOfWork, held: _Held, *, role: SignoffRole, statement: str, content_sha256: str
) -> UUID:
    principal = uow.principal
    if principal.id is None or principal.mfa_verified_at is None:
        raise Problem("mfa-required", mfa.VERIFICATION_REQUIRED)
    signoff_id = new_id()
    uow.session.execute(
        insert(signoff).values(
            tenant_id=principal.tenant_id,
            id=signoff_id,
            subject_type=OBJECT_TYPE,
            subject_id=held.id,
            role=role.value,
            signer_id=principal.id,
            statement=statement,
            subject_content_sha256=content_sha256,
            mfa_verified_at=principal.mfa_verified_at,
            signed_at=uow.now,
        )
    )
    return signoff_id


# --- generation ----------------------------------------------------------------------------------

type Generator = Callable[[Session, gates.PeriodScope], Outcome]

# The kinds compared at generation. A subledger-to-GL reconciliation is generated without a source
# and compared when its trial balance is attached (``attach``).
GENERATORS: Final[Mapping[ReconciliationKind, Generator]] = {
    ReconciliationKind.BILLING_TO_SUBLEDGER: billing_outcome,
}
CONTROLS: Final[Mapping[ReconciliationKind, str]] = {
    ReconciliationKind.BILLING_TO_SUBLEDGER: CONTROL_BILLING,
    ReconciliationKind.SUBLEDGER_TO_GL: CONTROL_GL,
}


@dataclass(frozen=True, slots=True)
class CertifyingRule:
    """The published rule a reconciliation is auto-certified under (T-CLS-06
    ``auto_certify_rule_set_version_id``, ``auto_certify_rule_id``)."""

    rule_set_version_id: UUID
    rule_id: UUID
    rule_set_code: str
    version_no: int
    rule_key: str


@dataclass(frozen=True, slots=True)
class _Rule:
    rule_key: str
    priority: int
    specificity: int
    conditions: Sequence[Mapping[str, object]]
    outputs: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _RuleSet:
    kind: str
    rules: Sequence[_Rule]


def _names_a_kind(conditions: object) -> bool:
    """Whether a rule is an auto-certification rule: it carries a ``reconciliation.kind``
    condition (supervisor ruling R-38 (v)). Every other ``AUTO_APPROVAL`` rule is the approval
    engine's and is never read for a reconciliation."""
    return isinstance(conditions, Sequence) and any(
        isinstance(item, Mapping) and item.get("field") == KIND_FACT for item in conditions
    )


def certifying_rule(
    session: Session,
    *,
    kind: ReconciliationKind,
    variance_count: int,
    unexplained_other_amount: Decimal | None,
    at: datetime,
) -> CertifyingRule | None:
    """The published ``AUTO_APPROVAL`` rule that certifies a reconciliation with these facts, or
    None (REQ-CLS-017; BS4-D-09). Only a reconciliation without a variance is certified (research
    07 RC-03), whatever a rule's conditions say. Across the versions in force the most specific
    rule wins, then the highest priority, the ascending rule key and the ascending rule set code
    (the order of ``approvals.routing``); a malformed rule raises, so nothing is certified under a
    rule nobody can explain (XR-12)."""
    if variance_count != 0:
        return None
    facts: dict[str, object] = {
        KIND_FACT: kind.value,
        VARIANCE_FACT: variance_count,
        OTHER_AMOUNT_FACT: unexplained_other_amount,
    }
    versions = session.execute(
        select(rule_set_version.c.id, rule_set_version.c.version_no, rule_set.c.code)
        .select_from(
            rule_set_version.join(
                rule_set,
                and_(
                    rule_set.c.tenant_id == rule_set_version.c.tenant_id,
                    rule_set.c.id == rule_set_version.c.rule_set_id,
                ),
            )
        )
        .where(
            rule_set_version.c.kind == RuleSetKind.AUTO_APPROVAL.value,
            rule_set_version.c.status == ConfigStatus.PUBLISHED.value,
            or_(
                rule_set_version.c.effective_from.is_(None), rule_set_version.c.effective_from <= at
            ),
            or_(rule_set_version.c.effective_to.is_(None), rule_set_version.c.effective_to > at),
        )
        .order_by(rule_set.c.code, rule_set_version.c.id)
    ).all()
    best: tuple[tuple[int, int, str, str], CertifyingRule] | None = None
    for version_id, version_no, code in versions:
        rows = [
            row
            for row in session.execute(
                select(
                    rule.c.id,
                    rule.c.rule_key,
                    rule.c.priority,
                    rule.c.specificity,
                    rule.c.conditions,
                    rule.c.outputs,
                )
                .where(rule.c.rule_set_version_id == version_id)
                .order_by(rule.c.rule_key)
            ).all()
            if _names_a_kind(row.conditions)
        ]
        if not rows:
            continue
        found = engine_rules.match(
            _RuleSet(
                kind=RuleSetKind.AUTO_APPROVAL.value,
                rules=tuple(
                    _Rule(
                        rule_key=str(row.rule_key),
                        priority=int(row.priority),
                        specificity=int(row.specificity),
                        conditions=row.conditions,
                        outputs=row.outputs,
                    )
                    for row in rows
                ),
            ),
            facts,
        )
        if found is None or found.outputs.get("auto_approve") is not True:
            continue
        rank = (-found.specificity, -found.priority, found.rule_key, str(code))
        if best is None or rank < best[0]:
            ids = {str(row.rule_key): UUID(str(row.id)) for row in rows}
            best = (
                rank,
                CertifyingRule(
                    rule_set_version_id=UUID(str(version_id)),
                    rule_id=ids[found.rule_key],
                    rule_set_code=str(code),
                    version_no=int(version_no),
                    rule_key=found.rule_key,
                ),
            )
    return None if best is None else best[1]


def request_generation(uow: UnitOfWork, body: ReconciliationCreateIn) -> tuple[UUID, JobOut]:
    """``POST /reconciliations``: (reconciliation id, API-S-Job of the deferred generation). The id
    is chosen here, so the job is idempotent and the command answers it beside the job."""
    session = uow.session
    if body.kind not in ON_DEMAND_KINDS:
        raise _invalid("kind", KIND_NOT_ON_DEMAND.format(kind=body.kind.value))
    found = session.execute(
        select(legal_entity.c.id, legal_entity.c.calendar_id).where(
            legal_entity.c.code == body.entity_code
        )
    ).one_or_none()
    if found is None:
        raise _invalid("entity_code", UNKNOWN_ENTITY)
    entity_id, calendar_id = UUID(str(found[0])), UUID(str(found[1]))
    require_for_entity(uow.ctx, PREPARE_PERMISSION, entity_id)
    book = body.book if body.book is not None else BookCode(primary_book(session))
    try:
        at = period_by_key(session, calendar_id=calendar_id, period_key=body.period_key)
    except LookupError:
        raise _invalid("period_key", UNKNOWN_PERIOD) from None
    try:
        scope = period_scope_of(session, entity_id, book.value, at.id)
    except Problem:
        message = BOOK_NOT_KEPT.format(
            entity=body.entity_code, book=book.value, period_key=body.period_key
        )
        raise _invalid("book", message) from None
    require_open(scope)
    reconciliation_id = new_id()
    params = {
        "reconciliation_id": str(reconciliation_id),
        "kind": body.kind.value,
        "entity_id": str(entity_id),
        "book_code": book.value,
        "period_id": str(at.id),
    }
    job_row = uow.defer(
        GENERATE_JOB, params, subject_type=OBJECT_TYPE, subject_id=reconciliation_id
    )
    uow.audit(
        action=REQUEST_ACTION,
        object_type=OBJECT_TYPE,
        object_id=reconciliation_id,
        after={**params, "job_id": str(job_row["id"]), "period_key": body.period_key},
    )
    return reconciliation_id, job_out_of(session, UUID(str(job_row["id"])))


def _as_of(uow: UnitOfWork, params: Mapping[str, Any]) -> datetime:
    """The knowledge cutoff of a generation: the later of the application instant and the
    transaction timestamp (the rule of a lock's freeze cutoff, S15-R-18c), and after every earlier
    generation of the same series, so the latest generated is one row."""
    session = uow.session
    cutoff = freeze.freeze_cutoff(session, uow.now)
    latest = session.execute(
        select(func.max(reconciliation.c.as_of_known_at)).where(
            reconciliation.c.entity_id == UUID(str(params["entity_id"])),
            reconciliation.c.book_code == str(params["book_code"]),
            reconciliation.c.period_id == UUID(str(params["period_id"])),
            reconciliation.c.kind == str(params["kind"]),
        )
    ).scalar_one_or_none()
    if latest is not None and cutoff <= latest:
        cutoff = latest + MICROSECOND
    return cutoff


def generate(uow: UnitOfWork, params: Mapping[str, Any], *, job_id: UUID | None) -> dict[str, int]:
    """Insert the reconciliation ``params`` names in ``DRAFT`` with its totals and differences,
    and record the control execution (module docstring). A repeated attempt whose row exists
    writes nothing (DG-KRN-JOB-03)."""
    session = uow.session
    principal = uow.principal
    reconciliation_id = UUID(str(params["reconciliation_id"]))
    kind = ReconciliationKind(str(params["kind"]))
    scope = period_scope_of(
        session,
        UUID(str(params["entity_id"])),
        str(params["book_code"]),
        UUID(str(params["period_id"])),
        share=True,
    )
    _serialise(uow, scope, kind.value)
    stored = session.execute(
        select(reconciliation.c.variance_count).where(reconciliation.c.id == reconciliation_id)
    ).scalar_one_or_none()
    if stored is not None:
        return {"variances": int(stored)}
    require_open(scope)
    # What the generation reads is recorded as a position and as counts, not as a time (item
    # REC-GEN-LOCK-1; ``gates.overtaken``). The chain position is read FIRST: a posting that
    # commits while the documents are read is sealed after it, and so counts as later.
    position = chain_position(session, scope)
    # The instant is fixed before the documents are counted: what the attach reads later is
    # what is known at or before it, and the ledger kind counts under that bound.
    as_of = _as_of(uow, params)
    generator = GENERATORS.get(kind)
    # Compared at generation, or generated without a source and compared at the attach.
    outcome = None if generator is None else generator(session, scope)
    source_read = None if outcome is None else outcome.source_documents_read
    if kind is ReconciliationKind.SUBLEDGER_TO_GL:
        subledger_read: int | None = ledger_events_read(session, scope, as_of)
    else:
        subledger_read = None if outcome is None else outcome.subledger_documents_read
    number = numbering.next_number(uow, SERIES)
    created = {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
        **_stamps(uow),
    }
    totals = [] if outcome is None else [total.as_json() for total in outcome.totals]
    variances = 0 if outcome is None else outcome.variance_count
    certifying = (
        None
        if outcome is None
        else certifying_rule(
            session, kind=kind, variance_count=variances, unexplained_other_amount=None, at=uow.now
        )
    )
    session.execute(
        insert(reconciliation).values(
            tenant_id=principal.tenant_id,
            id=reconciliation_id,
            reconciliation_no=number,
            kind=kind.value,
            entity_id=scope.entity_id,
            book_code=scope.book_code,
            period_id=scope.period_id,
            status=ReconciliationStatus.DRAFT.value,
            as_of_known_at=as_of,
            totals=totals,
            variance_count=variances,
            # T-CLS-06 records the certifying rule at insert (IM-S: not updatable).
            auto_certify_rule_set_version_id=(
                None if certifying is None else certifying.rule_set_version_id
            ),
            auto_certify_rule_id=None if certifying is None else certifying.rule_id,
            ledger_chain_seq=position,
            source_documents_read=source_read,
            subledger_documents_read=subledger_read,
            **created,
        )
    )
    identity = {
        "reconciliation_id": str(reconciliation_id),
        "reconciliation_no": number,
        "kind": kind.value,
    }
    uow.audit(
        action=GENERATE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=reconciliation_id,
        object_version="1",
        after={
            "reconciliation_no": number,
            "kind": kind.value,
            "entity_id": str(scope.entity_id),
            "book_code": scope.book_code,
            "period_id": str(scope.period_id),
            "status": ReconciliationStatus.DRAFT.value,
            "as_of_known_at": as_of,
            "totals": totals,
            "variance_count": variances,
            "population": None if outcome is None else outcome.population,
            "job_id": None if job_id is None else str(job_id),
        },
    )
    if outcome is None:
        return {"variances": 0}
    item_ids = _insert_items(uow, reconciliation_id, outcome.differences, created)
    record_execution(
        uow,
        control_id=CONTROLS[kind],
        run_ref_type=RunRefType.RECONCILIATION_RUN,
        run_ref_id=reconciliation_id,
        population_count=outcome.population,
        exception_count=variances,
        result=ControlResult.FAIL if variances else ControlResult.PASS,
        detail={**identity, "variance_count": variances, "auto_certified": certifying is not None},
        entity_id=scope.entity_id,
        book_code=scope.book_code,
        period_id=scope.period_id,
    )
    if item_ids:
        record_facts(
            uow,
            action=ITEM_CREATE_ACTION,
            object_type=ITEM_OBJECT,
            ids=item_ids,
            detail={"reconciliation_id": str(reconciliation_id)},
        )
    _auto_certify(uow, scope, identity, variances=variances, certifying=certifying)
    return {"variances": variances, "documents": outcome.population}


def _auto_certify(
    uow: UnitOfWork,
    scope: gates.PeriodScope,
    identity: Mapping[str, str],
    *,
    variances: int,
    certifying: CertifyingRule | None,
) -> None:
    """REQ-CLS-017 for a reconciliation just inserted with its certifying rule, if any: the move
    ``DRAFT → AUTO_CERTIFIED`` and the CTL-026 execution — ``PASS`` with the rule for a certified
    reconciliation, ``NOT_APPLICABLE`` for one left to its preparer and reviewer."""
    reconciliation_id = UUID(identity["reconciliation_id"])
    rule_detail = (
        None
        if certifying is None
        else {
            "rule_set_version_id": str(certifying.rule_set_version_id),
            "rule_id": str(certifying.rule_id),
            "rule_set_code": certifying.rule_set_code,
            "version_no": certifying.version_no,
            "rule_key": certifying.rule_key,
        }
    )
    record_execution(
        uow,
        control_id=CONTROL_AUTO_CERTIFY,
        run_ref_type=RunRefType.RECONCILIATION_RUN,
        run_ref_id=reconciliation_id,
        population_count=0 if certifying is None else 1,
        exception_count=0,
        result=ControlResult.NOT_APPLICABLE if certifying is None else ControlResult.PASS,
        detail={
            **identity,
            "variance_count": variances,
            "auto_certified": certifying is not None,
            "rule": rule_detail,
        },
        entity_id=scope.entity_id,
        book_code=scope.book_code,
        period_id=scope.period_id,
    )
    if certifying is None:
        return
    transitions.apply(
        uow.session,
        OBJECT_TYPE,
        reconciliation_id,
        to_status=ReconciliationStatus.AUTO_CERTIFIED.value,
        expected_status=ReconciliationStatus.DRAFT.value,
        set_values={"row_version": 2, **_stamps(uow)},
    )
    uow.audit(
        action=AUTO_CERTIFY_ACTION,
        object_type=OBJECT_TYPE,
        object_id=reconciliation_id,
        object_version="2",
        before={"status": ReconciliationStatus.DRAFT.value},
        after={"status": ReconciliationStatus.AUTO_CERTIFIED.value, "rule": rule_detail},
    )


def _insert_items(
    uow: UnitOfWork,
    reconciliation_id: UUID,
    differences: Sequence[Difference],
    created: Mapping[str, Any],
) -> list[UUID]:
    rows = [
        {
            "tenant_id": uow.principal.tenant_id,
            "id": new_id(),
            "reconciliation_id": reconciliation_id,
            "item_kind": item.item_kind,
            "account_code": item.account_code,
            "account_role": item.account_role,
            "contract_id": item.contract_id,
            "invoice_number": item.invoice_number,
            "subledger_amount": item.subledger_amount,
            "source_amount": item.source_amount,
            "difference": item.difference,
            "currency": item.currency,
            "is_high_risk": item.is_high_risk,
            "gl_document_reference": item.gl_document_reference,
            **created,
        }
        for item in differences
    ]
    if rows:
        uow.session.execute(insert(reconciliation_item), rows)
    return [row["id"] for row in rows]


# --- subledger to GL: what the comparison reads ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Windows:
    """What an account's closing balance covers at the period end (``trial_balance``): every
    period through the end for a balance sheet account, the periods of the period's fiscal year
    through the end for an income statement account."""

    fiscal_year: int
    year_start: date
    period_end: date

    def holds_period(self, account_type: str, fiscal_year: int, end_date: date) -> bool:
        if end_date > self.period_end:
            return False
        return account_type in BALANCE_SHEET_TYPES or fiscal_year == self.fiscal_year

    def holds_date(self, account_type: str, day: date) -> bool:
        if day > self.period_end:
            return False
        return account_type in BALANCE_SHEET_TYPES or day >= self.year_start


def _windows(session: Session, scope: gates.PeriodScope) -> _Windows:
    calendar_id, fiscal_year = session.execute(
        select(period.c.calendar_id, period.c.fiscal_year).where(period.c.id == scope.period_id)
    ).one()
    year_start = session.execute(
        select(func.min(period.c.start_date)).where(
            period.c.calendar_id == calendar_id, period.c.fiscal_year == fiscal_year
        )
    ).scalar_one()
    return _Windows(fiscal_year=int(fiscal_year), year_start=year_start, period_end=scope.end_date)


@dataclass(frozen=True, slots=True)
class _Subledger:
    """The subledger side at a knowledge cutoff: the balance of every account inside its window,
    the accounts that carry a line through the period end, the same two by the account role the
    lines were posted with (T-SL-04 ``account_role``), and the lines recorded after the cutoff,
    which the reconciliation does not hold."""

    balances: tuple[trial_balance.AccountBalance, ...]
    accounts: frozenset[str]
    later_lines: int
    by_role: Mapping[tuple[str, str], Decimal]  # (account code, account role) → balance
    role_accounts: Mapping[str, frozenset[str]]  # account role → the accounts its lines reached


def _subledger_side(
    session: Session,
    scope: gates.PeriodScope,
    windows: _Windows,
    as_of: datetime,
    chain_seq: int | None = None,
) -> _Subledger:
    """The subledger side of the entity and book through the period end. With ``chain_seq`` —
    the reconciliation's chain position (T-CLS-06 ``ledger_chain_seq``) — the reconciliation
    holds the lines of the postings sealed up to it, and a line of a later seal is one it does
    not hold: the chain sequence is the commit order of the book's postings, so "later" is
    "committed later" whenever the posting's unit of work began. Without one (a row generated
    before revision 0121) it holds the lines recorded at or before ``as_of``."""
    posting_period = period.alias("posting_period")
    lines = subledger_line.join(
        gl_account,
        and_(
            gl_account.c.tenant_id == subledger_line.c.tenant_id,
            gl_account.c.id == subledger_line.c.gl_account_id,
        ),
    ).join(
        posting_period,
        and_(
            posting_period.c.tenant_id == subledger_line.c.tenant_id,
            posting_period.c.id == subledger_line.c.period_id,
        ),
    )
    if chain_seq is None:
        within = subledger_line.c.recorded_at <= as_of
    else:
        sealed = subledger_posting_seal
        lines = lines.join(
            sealed,
            and_(
                sealed.c.tenant_id == subledger_line.c.tenant_id,
                sealed.c.subledger_posting_id == subledger_line.c.subledger_posting_id,
            ),
        )
        within = sealed.c.chain_seq <= chain_seq
    rows = session.execute(
        select(
            gl_account.c.code,
            gl_account.c.account_type,
            subledger_line.c.account_role,
            posting_period.c.fiscal_year,
            subledger_line.c.functional_currency,
            func.coalesce(
                func.sum(subledger_line.c.amount_functional).filter(within), Decimal(0)
            ).label("amount"),
            func.count().filter(within).label("held"),
            func.count().filter(~within).label("later"),
        )
        .select_from(lines)
        .where(
            subledger_line.c.entity_id == scope.entity_id,
            subledger_line.c.book_code == scope.book_code,
            subledger_line.c.period_end_date <= scope.end_date,
        )
        .group_by(
            gl_account.c.code,
            gl_account.c.account_type,
            subledger_line.c.account_role,
            posting_period.c.fiscal_year,
            subledger_line.c.functional_currency,
        )
    ).all()
    functional = scope.functional_currency.strip()
    balances: dict[str, Decimal] = {}
    by_role: dict[tuple[str, str], Decimal] = {}
    role_accounts: dict[str, set[str]] = {}
    accounts: set[str] = set()
    later = 0
    for row in rows:
        later += int(row.later)
        if not int(row.held):
            continue
        if str(row.functional_currency).strip() != functional:
            raise ValueError(
                f"subledger lines of {scope.entity_code} are stated in "
                f"{row.functional_currency}, not in its functional currency {functional}"
            )
        code = str(row.code)
        role = _text(row.account_role)
        accounts.add(code)
        role_accounts.setdefault(role, set()).add(code)
        if _text(row.account_type) in BALANCE_SHEET_TYPES or int(row.fiscal_year) == (
            windows.fiscal_year
        ):
            balances[code] = balances.get(code, Decimal(0)) + Decimal(row.amount)
            by_role[(code, role)] = by_role.get((code, role), Decimal(0)) + Decimal(row.amount)
    return _Subledger(
        balances=tuple(
            trial_balance.AccountBalance(account_code=code, amount=amount)
            for code, amount in sorted(balances.items())
        ),
        accounts=frozenset(accounts),
        later_lines=later,
        by_role=by_role,
        role_accounts={role: frozenset(codes) for role, codes in role_accounts.items()},
    )


def _control_role_accounts(
    session: Session, scope: gates.PeriodScope, as_of: datetime
) -> dict[str, frozenset[str]]:
    """Per contract balance role, the GL accounts the published account mapping in force at
    ``as_of`` gives it for the entity and book (T-REF-14, T-REF-15): subledger-controlled before
    the subledger's first line on them (supervisor rulings R-69 (c), R-74 (c))."""
    version = account_mapping_version
    mapped = account_mapping_rule
    found: dict[str, set[str]] = {}
    for role, code in session.execute(
        select(mapped.c.account_role, gl_account.c.code)
        .select_from(
            mapped.join(
                version,
                and_(
                    version.c.tenant_id == mapped.c.tenant_id,
                    version.c.id == mapped.c.account_mapping_version_id,
                ),
            ).join(
                gl_account,
                and_(
                    gl_account.c.tenant_id == mapped.c.tenant_id,
                    gl_account.c.id == mapped.c.gl_account_id,
                ),
            )
        )
        .where(
            mapped.c.account_role.in_(CONTROL_ROLES),
            version.c.status == ConfigStatus.PUBLISHED.value,
            or_(version.c.effective_from.is_(None), version.c.effective_from <= as_of),
            or_(version.c.effective_to.is_(None), version.c.effective_to > as_of),
            or_(mapped.c.entity_id.is_(None), mapped.c.entity_id == scope.entity_id),
            or_(mapped.c.book_code.is_(None), mapped.c.book_code == scope.book_code),
        )
        .distinct()
    ):
        found.setdefault(_text(role), set()).add(str(code))
    return {role: frozenset(codes) for role, codes in found.items()}


def _mapped_accounts(mapped: Mapping[str, frozenset[str]]) -> frozenset[str]:
    return frozenset(code for codes in mapped.values() for code in codes)


def _period_ref(session: Session, scope: gates.PeriodScope) -> tie_outs.PeriodRef:
    """The reconciled period as the balance reader names one."""
    fiscal_year, period_no, quarter_no = session.execute(
        select(period.c.fiscal_year, period.c.period_no, period.c.quarter_no).where(
            period.c.id == scope.period_id
        )
    ).one()
    return tie_outs.PeriodRef(
        id=scope.period_id,
        key=scope.period_key,
        name=scope.period_name,
        fiscal_year=int(fiscal_year),
        period_no=int(period_no),
        quarter_no=None if quarter_no is None else int(quarter_no),
        start=scope.start_date,
        end=scope.end_date,
    )


def _functional_balances(
    session: Session, scope: gates.PeriodScope, rows: Sequence[tie_outs.BalanceRow]
) -> dict[tuple[UUID, UUID], dict[str, Decimal]]:
    """The stored functional balances (04 T-CON-09) of the member contracts in ``rows`` whose
    version's latest period is the reconciled one — the only period a functional balance is
    stored for — by (contract version, contract): the three role balances by their measure. The
    latest period of a member is the last one a balance node of its subject carries
    (``tie_outs.traced_balances``); a member whose stored transaction balances are not the
    period's is left out."""
    if not rows:
        return {}
    latest: dict[UUID, Mapping[str, str]] = {}
    for version_id in sorted({row.version_id for row in rows}, key=str):
        trace = trace_store.load_trace(session, version_id)
        nodes = () if trace is None else ((node.id, node.value) for node in trace.nodes)
        latest[version_id] = tie_outs.traced_balances(nodes).latest
    by_key = {
        (row.version_id, row.contract_id): row
        for row in rows
        if latest[row.version_id].get(contract_entity_subject_key(row.external_id, row.entity_code))
        == scope.period_key
    }
    if not by_key:
        return {}
    balance = contract_version_balance
    measures = [measure for measure, _ in POSITION_ROLES.values()]
    found: dict[tuple[UUID, UUID], dict[str, Decimal]] = {}
    for stored in session.execute(
        select(
            balance.c.contract_version_id,
            balance.c.contract_id,
            *(balance.c[f"{measure}_txn"] for measure in measures),
            *(balance.c[f"{measure}_functional"] for measure in measures),
        ).where(
            balance.c.entity_id == scope.entity_id,
            tuple_(balance.c.contract_version_id, balance.c.contract_id).in_(
                sorted(by_key, key=str)
            ),
        )
    ).mappings():
        key = (UUID(str(stored["contract_version_id"])), UUID(str(stored["contract_id"])))
        row = by_key[key]
        if all(Decimal(stored[f"{measure}_txn"]) == row.value(measure) for measure in measures):
            found[key] = {measure: Decimal(stored[f"{measure}_functional"]) for measure in measures}
    return found


def _role_balances(
    session: Session,
    scope: gates.PeriodScope,
    as_of: datetime,
    side: _Subledger,
    mapped: Mapping[str, frozenset[str]],
) -> tuple[trial_balance.RoleBalance, ...]:
    """The subledger side of the three contract balance roles on the role basis (module
    docstring; supervisor rulings R-69 (a), R-74): per role its accounts, and the stored closing
    balances of the entity's contracts in the functional currency with what other roles posted
    on those accounts — or why the role is not stated."""
    functional = scope.functional_currency.strip()
    reached = {
        role: mapped.get(role, frozenset()) | side.role_accounts.get(role, frozenset())
        for role in POSITION_ROLES
    }
    unreadable: tuple[tuple[str, str], ...] | None = None
    try:
        rows: tuple[tie_outs.BalanceRow, ...] = tie_outs.balances_at(
            session,
            entity_ids=[scope.entity_id],
            book_code=scope.book_code,
            period_keys={scope.entity_id: _period_ref(session, scope)},
            cutoff=as_of,
        )
    except tie_outs.BalanceUnreadable as refused:
        rows = ()
        unreadable = _contracts_named(session, scope, refused)
    measures = [measure for measure, _ in POSITION_ROLES.values()]
    foreign = [
        row
        for row in rows
        if row.currency != functional and any(row.value(measure) != 0 for measure in measures)
    ]
    stored = _functional_balances(session, scope, foreign)
    balances: list[trial_balance.RoleBalance] = []
    taken: set[str] = set()
    for role, (measure, sign) in POSITION_ROLES.items():
        codes = tuple(sorted(reached[role] - taken))
        taken |= reached[role]
        others = {
            other: reached[role] & reached[other]
            for other in POSITION_ROLES
            if other != role and reached[role] & reached[other]
        }
        amount = Decimal(0)
        missing: list[tie_outs.BalanceRow] = []
        for row in rows:
            value = row.value(measure)
            if value == 0:
                continue
            if row.currency == functional:
                amount += sign * value
                continue
            held = stored.get((row.version_id, row.contract_id))
            if held is None:
                missing.append(row)
            else:
                amount += sign * held[measure]
        # What other roles posted on the role's accounts is part of what the ledger holds there.
        amount += sum(
            (
                posted
                for (code, posted_role), posted in side.by_role.items()
                if code in codes and posted_role not in POSITION_ROLES
            ),
            Decimal(0),
        )
        not_stated: trial_balance.NotStated | None = None
        if unreadable is not None:
            reason = NOT_STATED_UNREADABLE.format(
                count=len(unreadable), period_key=scope.period_key
            )
            not_stated = trial_balance.NotStated(reason, unreadable)
        elif others:
            reason = NOT_STATED_SHARED.format(
                accounts=", ".join(sorted({code for found in others.values() for code in found})),
                role=role,
                others=" and ".join(others),
            )
            not_stated = trial_balance.NotStated(reason)
        elif missing:
            named = tuple(
                sorted({(str(row.contract_id), row.external_id) for row in missing}, key=_second)
            )
            reason = NOT_STATED_FOREIGN.format(
                count=len(named), functional=functional, period_key=scope.period_key
            )
            not_stated = trial_balance.NotStated(reason, named)
        if not_stated is None and not codes and amount == 0:
            continue  # a role without an account and without a balance has no row
        balances.append(
            trial_balance.RoleBalance(
                account_role=role,
                account_codes=codes,
                amount=None if not_stated is not None else amount,
                not_stated=not_stated,
            )
        )
    return tuple(balances)


def _second(pair: tuple[str, str]) -> tuple[str, str]:
    return (pair[1], pair[0])


def _contracts_named(
    session: Session, scope: gates.PeriodScope, refused: tie_outs.BalanceUnreadable
) -> tuple[tuple[str, str], ...]:
    """(contract id, external id) of the member contracts a ``BalanceUnreadable`` names — its
    errors carry ``balances[<external id>@<entity code>]`` — in external id order."""
    suffix = f"@{scope.entity_code}]"
    prefix = "balances["
    fields = [error.field for error in refused.errors if error.field is not None]
    named = sorted(
        {
            field[len(prefix) : -len(suffix)]
            for field in fields
            if field.startswith(prefix) and field.endswith(suffix)
        }
    )
    if not named:
        return ()
    found = {
        str(external_id): str(contract_id)
        for contract_id, external_id in session.execute(
            select(contract.c.id, contract.c.external_id).where(contract.c.external_id.in_(named))
        )
    }
    return tuple((found[name], name) for name in named if name in found)


def _billing_references(
    session: Session,
    scope: gates.PeriodScope,
    details: Sequence[gl_ports.TrialBalanceDetail],
) -> frozenset[str]:
    """The numbers among the documents made in the ERP (no ADP-10 external id) that are an
    invoice or credit memo number of the entity (supervisor ruling R-74 (d)): of a stored source
    invoice (T-SRC-04), or of a billing event of one of the entity's contracts that no
    ``EVENT_VOIDED`` names and whose contract is not voided."""
    candidates = sorted({item.document_reference for item in details if item.external_id is None})
    if not candidates:
        return frozenset()
    found = {
        str(number)
        for number in session.execute(
            select(source_invoice.c.invoice_number)
            .where(
                source_invoice.c.legal_entity_code == scope.entity_code,
                source_invoice.c.invoice_number.in_(candidates),
            )
            .distinct()
        ).scalars()
    }
    invoice_number = contract_event.c.payload["invoice_number"].astext
    memo_number = contract_event.c.payload["credit_memo_number"].astext
    events = session.execute(
        select(
            contract_event.c.id,
            contract_event.c.contract_id,
            func.coalesce(invoice_number, memo_number).label("number"),
        ).where(
            contract_event.c.contracting_entity_id == scope.entity_id,
            contract_event.c.event_type.in_(BILLING_TYPES),
            or_(invoice_number.in_(candidates), memo_number.in_(candidates)),
        )
    ).all()
    if events:
        event_ids = [row.id for row in events]
        contract_ids = sorted({row.contract_id for row in events}, key=str)
        voided_events = set(
            session.execute(
                select(contract_event.c.supersedes_event_id).where(
                    contract_event.c.event_type == ContractEventType.EVENT_VOIDED.value,
                    contract_event.c.supersedes_event_id.in_(event_ids),
                )
            ).scalars()
        )
        voided_contracts = set(
            session.execute(
                select(contract_event.c.contract_id).where(
                    contract_event.c.event_type == ContractEventType.CONTRACT_VOIDED.value,
                    contract_event.c.contract_id.in_(contract_ids),
                )
            ).scalars()
        )
        found |= {
            str(row.number)
            for row in events
            if row.id not in voided_events and row.contract_id not in voided_contracts
        }
    return frozenset(found)


def _batch_portions(
    session: Session, scope: gates.PeriodScope, windows: _Windows
) -> list[trial_balance.BatchPortion]:
    """What the entity's journal batches of the book carry per account, for the batches that can
    explain a difference: one the GL has not acknowledged whose period the subledger balance
    holds, and an acknowledged one whose GL posting date lies in another window than its
    period."""
    batch_period = period.alias("batch_period")
    accepted = (
        select(
            posting_ack.c.journal_batch_id,
            posting_ack.c.gl_posted_date,
            posting_ack.c.gl_document_id,
            func.row_number()
            .over(
                partition_by=posting_ack.c.journal_batch_id,
                order_by=(posting_ack.c.received_at.desc(), posting_ack.c.id.desc()),
            )
            .label("rank"),
        )
        .where(posting_ack.c.ack_kind.in_(POSTED_ACKS))
        .subquery("accepted")
    )
    cancelled = JournalState.CANCELLED.value
    batches = session.execute(
        select(
            journal_batch.c.id,
            journal_batch.c.external_id,
            journal_batch.c.state,
            batch_period.c.fiscal_year,
            batch_period.c.end_date,
            accepted.c.gl_posted_date,
            accepted.c.gl_document_id,
        )
        .select_from(
            journal_batch.join(
                journal_run,
                and_(
                    journal_run.c.tenant_id == journal_batch.c.tenant_id,
                    journal_run.c.id == journal_batch.c.journal_run_id,
                ),
            )
            .join(
                batch_period,
                and_(
                    batch_period.c.tenant_id == journal_batch.c.tenant_id,
                    batch_period.c.id == journal_batch.c.period_id,
                ),
            )
            .outerjoin(
                accepted,
                and_(accepted.c.journal_batch_id == journal_batch.c.id, accepted.c.rank == 1),
            )
        )
        .where(
            journal_batch.c.entity_id == scope.entity_id,
            journal_batch.c.book_code == scope.book_code,
            journal_batch.c.state != cancelled,
            journal_run.c.state != cancelled,
        )
    ).all()
    # (in the subledger's window, posted, in the GL's window) per account class of every batch
    standing: dict[UUID, dict[bool, tuple[bool, bool, bool]]] = {}
    references: dict[UUID, tuple[str, str | None]] = {}
    for batch in batches:
        posted = _text(batch.state) == JournalState.ACKNOWLEDGED.value
        by_class: dict[bool, tuple[bool, bool, bool]] = {}
        for balance_sheet in (True, False):
            kind = AccountType.ASSET.value if balance_sheet else AccountType.REVENUE.value
            in_subledger = windows.holds_period(kind, int(batch.fiscal_year), batch.end_date)
            in_ledger = (
                in_subledger
                if batch.gl_posted_date is None
                else windows.holds_date(kind, batch.gl_posted_date)
            )
            by_class[balance_sheet] = (in_subledger, posted, in_ledger)
        if any(
            (in_subledger and not posted) or (posted and in_subledger != in_ledger)
            for in_subledger, posted, in_ledger in by_class.values()
        ):
            batch_id = UUID(str(batch.id))
            standing[batch_id] = by_class
            references[batch_id] = (
                str(batch.external_id),
                None if batch.gl_document_id is None else str(batch.gl_document_id),
            )
    if not standing:
        return []
    amount = func.sum(journal_line.c.debit_functional - journal_line.c.credit_functional)
    rows = session.execute(
        select(
            journal_line.c.journal_batch_id,
            gl_account.c.code,
            gl_account.c.account_type,
            amount.label("amount"),
        )
        .select_from(
            journal_line.join(
                gl_account,
                and_(
                    gl_account.c.tenant_id == journal_line.c.tenant_id,
                    gl_account.c.id == journal_line.c.gl_account_id,
                ),
            )
        )
        .where(journal_line.c.journal_batch_id.in_(sorted(standing, key=str)))
        .group_by(journal_line.c.journal_batch_id, gl_account.c.code, gl_account.c.account_type)
        .order_by(gl_account.c.code, journal_line.c.journal_batch_id)
    ).all()
    portions: list[trial_balance.BatchPortion] = []
    for row in rows:
        batch_id = UUID(str(row.journal_batch_id))
        in_subledger, posted, in_ledger = standing[batch_id][
            _text(row.account_type) in BALANCE_SHEET_TYPES
        ]
        reference, document = references[batch_id]
        portions.append(
            trial_balance.BatchPortion(
                reference=reference,
                account_code=str(row.code),
                amount=Decimal(row.amount),
                in_subledger=in_subledger,
                posted=posted,
                in_ledger=in_ledger,
                gl_document_reference=document,
            )
        )
    return portions


def _own_references(
    session: Session, scope: gates.PeriodScope, details: Sequence[gl_ports.TrialBalanceDetail]
) -> frozenset[str]:
    """The ADP-10 external ids among ``details`` that name a journal batch of the entity."""
    named = sorted({item.external_id for item in details if item.external_id})
    if not named:
        return frozenset()
    return frozenset(
        str(found)
        for found in session.execute(
            select(journal_batch.c.external_id).where(
                journal_batch.c.entity_id == scope.entity_id,
                journal_batch.c.external_id.in_(named),
            )
        ).scalars()
    )


def controlled_accounts(
    session: Session, scope: gates.PeriodScope, as_of: datetime, chain_seq: int | None = None
) -> tuple[str, ...]:
    """The subledger-controlled account codes of the entity and book at the period end (module
    docstring [J]): what a trial balance is pulled for (REQ-INT-009) and compared on. ``as_of``
    and ``chain_seq`` are the reconciliation's (``_subledger_side``)."""
    side = _subledger_side(session, scope, _windows(session, scope), as_of, chain_seq)
    mapped = _mapped_accounts(_control_role_accounts(session, scope, as_of))
    return tuple(sorted(side.accounts | mapped))


# 04 E-29: the entry kinds of an invoice and a credit memo the SUBLEDGER posts (POLICIES JET-03,
# ``billing.posting = ENGINE``).
POSTED_BILLING_KINDS: Final = (
    SubledgerEntryKind.BILLING.value,
    SubledgerEntryKind.CREDIT_MEMO.value,
)


def erp_posted_billing(
    session: Session, scope: gates.PeriodScope, as_of: datetime
) -> dict[str, Decimal]:
    """What the ERP itself posts to the contract liability under ``billing.posting = ERP``
    (POLICIES POL-004; supervisor ruling R-74 (e)), through the period end: by account code and
    debit positive, in the functional currency — the billing a credit.

    Under that policy an invoice or a credit memo is ingested and never posted by the subledger,
    which holds it in the stored contract balance (module docstring, "The role basis"); a ledger
    the ERP keeps holds the document itself, Dr receivable / Cr contract liability. Whoever
    states such a ledger from the subledger's lines — a seed that writes the trial balance of a
    period it closes (``domain.demo.closing.closing_balances``) — adds this.

    The amount is the billing the engine counts in the position of the entity's contracts at
    the period end (ENGINE_SPEC_B S10-R-08, node ``billed_unconditional_cum`` of the contract
    versions read at ``as_of``; ``tie_outs.billed_through``) less the invoice and credit memo
    lines the subledger posted on the role itself: nothing under ``billing.posting = ENGINE``,
    the whole billing under ``ERP`` — the measure of the roll-forward report (supervisor ruling
    R-72 (a)). A contract in another currency than the functional one is left out: the ERP
    states its documents at a rate of its own ([J]; the role's row is stated for such a contract
    only in its version's latest period).

    The account is the one the published mapping gives ``CONTRACT_LIABILITY``; where it gives
    several, the lowest code — the role is one row of the reconciliation, so which of its
    accounts takes the credit does not change what is compared. Empty when the role has no
    account or the ERP posted nothing.

    What a file written with it proves, and what it does not. The amount is the engine's own
    figure, and the stored contract balance the reconciliation compares with is the engine's
    too: a trial balance written from the subledger's lines and this billing ties by
    construction. Its tie shows that the two sides of the reconciliation are computed
    consistently — not that an independent ledger agrees."""
    role = AccountRole.CONTRACT_LIABILITY.value
    accounts = _control_role_accounts(session, scope, as_of).get(role, frozenset())
    if not accounts:
        return {}
    functional = scope.functional_currency.strip()
    traces: dict[UUID, tie_outs.TracedBalances] = {}
    rows = tie_outs.balances_at(
        session,
        entity_ids=[scope.entity_id],
        book_code=scope.book_code,
        period_keys={scope.entity_id: _period_ref(session, scope)},
        cutoff=as_of,
        traces=traces,
    )
    counted = sum(
        (
            tie_outs.billed_through(
                traces[row.version_id],
                external_id=row.external_id,
                entity_code=row.entity_code,
                period_key=scope.period_key,
            )
            for row in rows
            if row.currency == functional
        ),
        Decimal(0),
    )
    # The lines are signed debit positive: what the subledger posted of the billing is a credit.
    posted = Decimal(
        session.execute(
            select(func.coalesce(func.sum(subledger_line.c.amount_functional), 0)).where(
                subledger_line.c.entity_id == scope.entity_id,
                subledger_line.c.book_code == scope.book_code,
                subledger_line.c.period_end_date <= scope.end_date,
                subledger_line.c.recorded_at <= as_of,
                subledger_line.c.account_role == role,
                subledger_line.c.entry_kind.in_(POSTED_BILLING_KINDS),
                subledger_line.c.txn_currency == functional,
            )
        ).scalar_one()
    )
    by_the_erp = counted + posted
    return {min(accounts): -by_the_erp} if by_the_erp else {}


def trial_balance_totals(lines: Sequence[gl_ports.TrialBalanceLine]) -> ControlTotals:
    """T-INT-02 ``source_totals`` / ``loaded_totals`` of a pulled trial balance (REQ-DAT-010): the
    count of its accounts, the sum by currency and the digest of its rows."""
    return ControlTotals.of([(line.account_code, "", line.currency, line.amount) for line in lines])


# --- subledger to GL: the attach -----------------------------------------------------------------


def _require_attachable(uow: UnitOfWork, held: _Held) -> None:
    """A trial balance is attached to the current ``DRAFT`` subledger-to-GL reconciliation of an
    open period that has none yet (T-CLS-06: the source is written once)."""
    kind = _text(held.row["kind"])
    if kind != ReconciliationKind.SUBLEDGER_TO_GL.value:
        label = gates.RECONCILIATION_LABELS.get(kind, kind)
        raise _refused(NOT_GL.format(no=held.number, kind=label), rule_id=RULE_SOURCE, field="kind")
    if held.status == ReconciliationStatus.CERTIFIED.value:
        raise _certified(held)
    if held.status != ReconciliationStatus.DRAFT.value:
        raise _refused(NOT_ATTACHABLE.format(no=held.number, status=held.status))
    require_open(held.scope)
    _require_current(uow, held)
    if _has_source(held.row):
        raise _refused(SOURCE_ATTACHED.format(no=held.number), rule_id=RULE_ROW, field="source")


def _has_source(row: Mapping[str, Any]) -> bool:
    return row["source_file_id"] is not None or row["sync_run_id"] is not None


def attach(
    uow: UnitOfWork,
    held: _Held,
    *,
    lines: Sequence[gl_ports.TrialBalanceLine],
    details: Sequence[gl_ports.TrialBalanceDetail] = (),
    source_file_id: UUID | None = None,
    sync_run_id: UUID | None = None,
    job_id: UUID | None = None,
) -> dict[str, int]:
    """Compare ``held`` — an attachable subledger-to-GL reconciliation — with a trial balance and
    store the result: the source (written once), the totals by account, the itemised differences
    and the CTL-025 execution (module docstring). The subledger side is the lines of the postings
    sealed up to the reconciliation's chain position; a line sealed later refuses the attach
    (a row generated before revision 0121: recorded at or before, and after, its
    ``as_of_known_at``)."""
    if (source_file_id is None) == (sync_run_id is None):
        raise ValueError("a trial balance comes from one file or from one sync run")
    session = uow.session
    scope = held.scope
    functional = scope.functional_currency.strip()
    stated = {line.currency.strip() for line in lines} | {item.currency.strip() for item in details}
    foreign = sorted(stated - {functional})
    if foreign:
        message = CURRENCY_NOT_FUNCTIONAL.format(
            currencies=", ".join(foreign), entity=scope.entity_code, functional=functional
        )
        raise _invalid("currency", message, rule_id=RULE_SOURCE)
    as_of = held.row["as_of_known_at"]
    windows = _windows(session, scope)
    # The lines of the postings sealed up to the reconciliation's chain position; a line sealed
    # later is one it does not hold, and refuses the attach (item REC-GEN-LOCK-1).
    side = _subledger_side(session, scope, windows, as_of, held.row["ledger_chain_seq"])
    if side.later_lines:
        message = SUBLEDGER_MOVED.format(count=side.later_lines, no=held.number)
        raise _refused(message, rule_id=RULE_SOURCE, field="as_of_known_at")
    mapped = _control_role_accounts(session, scope, as_of)
    compared = trial_balance.compare(
        currency=functional,
        accounts=side.accounts | _mapped_accounts(mapped),
        subledger=side.balances,
        portions=_batch_portions(session, scope, windows),
        lines=lines,
        details=details,
        own_references=_own_references(session, scope, details),
        roles=_role_balances(session, scope, as_of, side, mapped),
        billing_references=_billing_references(session, scope, details),
    )
    totals = [
        Total(
            account_code=row.account_code,
            currency=row.currency,
            subledger_amount=row.subledger_amount,
            source_amount=row.source_amount,
            account_role=row.account_role,
            account_codes=row.account_codes,
            not_stated=row.not_stated,
        ).as_json()
        for row in compared.totals
    ]
    differences = [
        Difference(
            item_kind=item.item_kind,
            currency=item.currency,
            difference=item.difference,
            subledger_amount=item.subledger_amount,
            source_amount=item.source_amount,
            account_code=item.account_code,
            is_high_risk=item.is_high_risk,
            gl_document_reference=item.gl_document_reference,
            account_role=item.account_role,
        )
        for item in compared.items
    ]
    row_version = int(held.row["row_version"])
    source = (
        {"source_file_id": source_file_id}
        if source_file_id is not None
        else {"sync_run_id": sync_run_id}
    )
    transitions.apply(
        session,
        OBJECT_TYPE,
        held.id,
        to_status=None,
        set_values={
            **source,
            "totals": totals,
            "variance_count": len(differences),
            "row_version": row_version + 1,
            **_stamps(uow),
        },
        expected_row_version=row_version,
    )
    principal = uow.principal
    created = {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
        **_stamps(uow),
    }
    item_ids = _insert_items(uow, held.id, differences, created)
    record_execution(
        uow,
        control_id=CONTROL_GL,
        run_ref_type=RunRefType.RECONCILIATION_RUN,
        run_ref_id=held.id,
        population_count=len(compared.totals),
        exception_count=len(differences),
        result=ControlResult.FAIL if differences else ControlResult.PASS,
        detail={
            "reconciliation_id": str(held.id),
            "reconciliation_no": held.number,
            "kind": _text(held.row["kind"]),
            "variance_count": len(differences),
            "direct_gl_entries": compared.direct_entries,
            "erp_billing_documents": compared.erp_billing_documents,
            "roles_not_stated": compared.not_stated,
            "trial_balance_rows": len(lines),
            "rows_not_compared": compared.ignored_lines,
            "auto_certified": False,
        },
        entity_id=scope.entity_id,
        book_code=scope.book_code,
        period_id=scope.period_id,
    )
    uow.audit(
        action=ATTACH_ACTION,
        object_type=OBJECT_TYPE,
        object_id=held.id,
        object_version=str(row_version + 1),
        before={"source_file_id": None, "sync_run_id": None, "totals": held.row["totals"]},
        after={
            "source_file_id": None if source_file_id is None else str(source_file_id),
            "sync_run_id": None if sync_run_id is None else str(sync_run_id),
            "totals": totals,
            "variance_count": len(differences),
            "direct_gl_entries": compared.direct_entries,
            "erp_billing_documents": compared.erp_billing_documents,
            "roles_not_stated": compared.not_stated,
            "rows_not_compared": compared.ignored_lines,
            "job_id": None if job_id is None else str(job_id),
        },
    )
    if item_ids:
        record_facts(
            uow,
            action=ITEM_CREATE_ACTION,
            object_type=ITEM_OBJECT,
            ids=item_ids,
            detail={"reconciliation_id": str(held.id)},
        )
    return {"variances": len(differences), "accounts": len(compared.totals)}


def _file_lines(
    uow: UnitOfWork, file_id: UUID, *, functional_currency: str
) -> tuple[gl_ports.TrialBalanceLine, ...]:
    """The closing balances of an uploaded trial balance (``IMPORT_SOURCE``; .csv or .xlsx); 422
    ``validation-failed`` naming the file or every row that cannot be read."""
    session = uow.session
    stored = (
        session.execute(select(file_object).where(file_object.c.id == file_id))
        .mappings()
        .one_or_none()
    )
    if (
        stored is None
        or _text(stored["purpose"]) != FilePurpose.IMPORT_SOURCE.value
        or stored["shredded_at"] is not None
    ):
        raise _invalid("file_id", FILE_REQUIRED, rule_id=RULE_SOURCE)
    media_type = str(stored["media_type"])
    if media_type not in (file_policy.CSV, file_policy.XLSX):
        raise _invalid("file_id", FILE_TYPE, rule_id=RULE_SOURCE)
    _, stream = open_file(session, file_id, files=uow.files, keyring=uow.keyring)
    try:
        with stream:
            sheet = (
                parse.read_csv(stream) if media_type == file_policy.CSV else parse.read_xlsx(stream)
            )
        return trial_balance.lines_of_sheet(sheet, functional_currency=functional_currency)
    except parse.ParseError:
        raise _invalid("file_id", FILE_UNREADABLE, rule_id=RULE_SOURCE) from None
    except trial_balance.SheetError as error:
        errors = [
            ProblemError(
                field=name, sheet=sheet.sheet_name, row=number, rule_id=RULE_SOURCE, message=text
            )
            for number, name, text in error.findings
        ]
        count = len(errors)
        detail = "1 field needs attention." if count == 1 else f"{count} fields need attention."
        raise Problem("validation-failed", detail, errors=errors) from None


def _gl_connection(uow: UnitOfWork, held: _Held, connection_id: UUID) -> Mapping[str, Any]:
    """The GL connection a trial balance is pulled through: ``ACTIVE``, of an adapter that serves
    one, and serving the reconciliation's entity (T-INT-01 ``entity_ids``: empty = every entity);
    else 422 ``validation-failed`` on ``integration_connection_id``."""
    found = (
        uow.session.execute(
            select(integration_connection).where(integration_connection.c.id == connection_id)
        )
        .mappings()
        .one_or_none()
    )
    field = "integration_connection_id"
    if found is None:
        raise _invalid(field, UNKNOWN_CONNECTION, rule_id=RULE_SOURCE)
    name = str(found["name"])
    if str(found["adapter"]) not in TRIAL_BALANCE_ADAPTERS:
        raise _invalid(field, NO_TRIAL_BALANCE.format(name=name), rule_id=RULE_SOURCE)
    if str(found["status"]) != ACTIVE_CONNECTION:
        raise _invalid(field, CONNECTION_DISABLED.format(name=name), rule_id=RULE_SOURCE)
    entities = [UUID(str(value)) for value in found["entity_ids"] or ()]
    if entities and held.scope.entity_id not in entities:
        message = CONNECTION_ENTITY.format(name=name, entity=held.scope.entity_code)
        raise _invalid(field, message, rule_id=RULE_SOURCE)
    return dict(found)


def request_trial_balance(
    uow: UnitOfWork, reconciliation_id: UUID, body: ReconciliationAttachIn
) -> JobOut:
    """``POST /reconciliations/{id}/attach-trial-balance``: API-S-Job of the deferred attach. An
    uploaded file is read here, so a file that cannot be compared is refused at once (422 with its
    rows); a pull is refused here for a connection that cannot serve it, and its
    ``TRIAL_BALANCE_PULL`` sync run is queued with the job."""
    session = uow.session
    held = _held(uow, reconciliation_id, PREPARE_PERMISSION)
    _require_attachable(uow, held)
    running = session.execute(
        select(func.count())
        .select_from(job)
        .where(
            job.c.kind == GENERATE_JOB.value,
            job.c.subject_type == OBJECT_TYPE,
            job.c.subject_id == held.id,
            job.c.state.in_(ACTIVE_JOBS),
            job.c.params.has_key(ATTACH_PARAM),
        )
    ).scalar_one()
    if running:
        raise _refused(ATTACH_IN_PROGRESS.format(no=held.number), rule_id=RULE_SOURCE)
    scope = held.scope
    attached: dict[str, str]
    run_id: UUID | None = None
    connection: Mapping[str, Any] | None = None
    if body.file_id is not None:
        if body.integration_connection_id is not None or body.source is not None:
            raise _invalid("file_id", ONE_SOURCE, rule_id=RULE_SOURCE)
        # 04 T-PLT-29 Binding (ruling R-111 (1)): the file is the caller's to name only when the
        # caller may read it; otherwise it is answered as a missing file, before anything of it
        # is read. The job reads the bound file as SYSTEM.
        if file_access.bound(session, uow.ctx, body.file_id) is None:
            raise _invalid("file_id", FILE_REQUIRED, rule_id=RULE_SOURCE)
        _file_lines(uow, body.file_id, functional_currency=scope.functional_currency)
        attached = {"file_id": str(body.file_id)}
    else:
        if body.integration_connection_id is None:
            raise _invalid("integration_connection_id", SOURCE_REQUIRED, rule_id=RULE_SOURCE)
        connection = _gl_connection(uow, held, body.integration_connection_id)
        run_id = new_id()
        attached = {
            "integration_connection_id": str(connection["id"]),
            "sync_run_id": str(run_id),
        }
    params = {
        "reconciliation_id": str(held.id),
        "kind": _text(held.row["kind"]),
        "entity_id": str(scope.entity_id),
        "book_code": scope.book_code,
        "period_id": str(scope.period_id),
        ATTACH_PARAM: attached,
    }
    job_row = uow.defer(GENERATE_JOB, params, subject_type=OBJECT_TYPE, subject_id=held.id)
    if run_id is not None and connection is not None:
        principal = uow.principal
        session.execute(
            insert(sync_run).values(
                tenant_id=principal.tenant_id,
                id=run_id,
                integration_connection_id=connection["id"],
                kind=TRIAL_BALANCE_PULL,
                status=SyncRunStatus.QUEUED.value,
                checkpoint_before=dict(connection["checkpoint"] or {}),
                job_id=job_row["id"],
                created_at=uow.now,
                created_by=principal.id,
                created_by_kind=principal.kind.value,
                row_version=1,
                **_stamps(uow),
            )
        )
    uow.audit(
        action=ATTACH_REQUEST_ACTION,
        object_type=OBJECT_TYPE,
        object_id=held.id,
        object_version=str(int(held.row["row_version"])),
        after={**attached, "job_id": str(job_row["id"])},
    )
    return job_out_of(session, UUID(str(job_row["id"])))


def _already_attached(held: _Held, attached: Mapping[str, Any]) -> bool:
    """Whether an earlier attempt of this job attached its trial balance (DG-KRN-JOB-03)."""
    row = held.row
    if "file_id" in attached:
        return row["source_file_id"] is not None and str(row["source_file_id"]) == str(
            attached["file_id"]
        )
    return row["sync_run_id"] is not None and str(row["sync_run_id"]) == str(
        attached["sync_run_id"]
    )


def _moved_run(uow: UnitOfWork) -> dict[str, Any]:
    """SC-M of one move of a ``sync_run`` (an IM-S row raises ``row_version`` itself)."""
    return {**_stamps(uow), "row_version": sync_run.c.row_version + 1}


@dataclass(frozen=True, slots=True)
class _Pull:
    """What a trial balance pull needs, read when its sync run starts. ``base_url`` and ``config``
    are the connection's (04 T-INT-01): an adapter that reaches an ERP is built for the connection
    the pull names (``GLContext``; BUILD_SPEC CLO-15)."""

    adapter: GlAdapter
    tenant_code: str
    chart: tuple[gl_ports.AccountRef, ...]
    entity: gl_ports.EntityRef
    period: gl_ports.PeriodRef
    accounts: tuple[str, ...]
    base_url: str | None
    config: Mapping[str, Any]


def _start_pull(uow: UnitOfWork, held: _Held, connection_id: UUID, run_id: UUID) -> _Pull:
    """Start the ``TRIAL_BALANCE_PULL`` run (``QUEUED → RUNNING``; a retried attempt finds it
    running) and read what the adapter is asked for."""
    session = uow.session
    scope = held.scope
    connection = _gl_connection(uow, held, connection_id)
    status = _text(
        session.execute(
            select(sync_run.c.status).where(sync_run.c.id == run_id).with_for_update()
        ).scalar_one()
    )
    if status == SyncRunStatus.QUEUED.value:
        transitions.apply(
            session,
            "sync_run",
            run_id,
            to_status=SyncRunStatus.RUNNING.value,
            expected_status=status,
            set_values={"started_at": uow.now, **_moved_run(uow)},
        )
    elif status != SyncRunStatus.RUNNING.value:
        raise _refused(RUN_NOT_STARTABLE.format(no=held.number, status=status))
    tenant_code = str(
        session.execute(
            select(tenant.c.code).where(tenant.c.id == uow.principal.tenant_id)
        ).scalar_one()
    )
    # The chart of the entity: active accounts for all entities or this one (T-REF-13).
    chart = tuple(
        gl_ports.AccountRef(code=str(code), name=str(name))
        for code, name in session.execute(
            select(gl_account.c.code, gl_account.c.name)
            .where(
                gl_account.c.is_active.is_(True),
                or_(
                    func.cardinality(gl_account.c.entity_ids) == 0,
                    any_(gl_account.c.entity_ids) == scope.entity_id,
                ),
            )
            .order_by(gl_account.c.code)
        )
    )
    return _Pull(
        adapter=TRIAL_BALANCE_ADAPTERS[str(connection["adapter"])],
        tenant_code=tenant_code,
        chart=chart,
        entity=gl_ports.EntityRef(code=scope.entity_code),
        period=gl_ports.PeriodRef(
            period_key=scope.period_key, start_date=scope.start_date, end_date=scope.end_date
        ),
        accounts=controlled_accounts(
            session, scope, held.row["as_of_known_at"], held.row["ledger_chain_seq"]
        ),
        base_url=None if connection["base_url"] is None else str(connection["base_url"]),
        config=dict(connection["config"] or {}),
    )


def _lines_of(
    pulled: gl_ports.TrialBalance, functional: str
) -> tuple[gl_ports.TrialBalanceLine, ...]:
    """The closing balances of a pull: its ``lines``, or its ``balances`` in the entity's
    functional currency for an adapter that fills only those (``TrialBalance`` docstring)."""
    if pulled.lines:
        return tuple(pulled.lines)
    return tuple(
        gl_ports.TrialBalanceLine(account_code=str(code), currency=functional, amount=amount)
        for code, amount in sorted(pulled.balances.items())
    )


def _pull_and_attach(jc: JobContext, params: Mapping[str, Any]) -> dict[str, int]:
    """The adapter path of ``attach-trial-balance``: start the sync run, pull with no transaction
    open while the adapter retries on the ADP-12 schedule, then attach and finish the run in one
    transaction. A pull that fails raises ``sync-objects-not-applied`` naming the trial balance;
    the run ends ``FAILED`` with the job (``generation_failed``)."""
    attached = params[ATTACH_PARAM]
    reconciliation_id = UUID(str(params["reconciliation_id"]))
    run_id = UUID(str(attached["sync_run_id"]))
    with jc.unit_of_work() as uow:
        held = _held(uow, reconciliation_id, None)
        if _already_attached(held, attached):
            return {"variances": int(held.row["variance_count"])}
        _require_attachable(uow, held)
        pull = _start_pull(uow, held, UUID(str(attached["integration_connection_id"])), run_id)
        uow.commit()
    try:
        adapter = gl_ports.gl_adapter_for(
            pull.adapter,
            gl_ports.GLContext(
                tenant_code=pull.tenant_code,
                accounts=pull.chart,
                base_url=pull.base_url,
                config=pull.config,
            ),
        )
        pulled = adapter.pull_trial_balance(pull.entity, pull.period, pull.accounts)
    except (gl_ports.Transient, Undeliverable, LookupError) as error:
        failure = {
            "step": FETCH_STEP,
            "object_type": TRIAL_BALANCE_OBJECT,
            "external_id": f"{pull.entity.code}:{pull.period.period_key}",
            "external_versions": [],
            "error": f"{type(error).__name__}: {error}",
        }
        raise Problem(
            SYNC_OBJECTS_NOT_APPLIED,
            NOT_APPLIED_DETAIL.format(failed=1, total=1),
            failures=[failure],
        ) from error
    jc.heartbeat()
    with jc.unit_of_work() as uow:
        held = _held(uow, reconciliation_id, None)
        _require_attachable(uow, held)
        lines = _lines_of(pulled, held.scope.functional_currency.strip())
        counts = attach(
            uow,
            held,
            lines=lines,
            details=tuple(pulled.details),
            sync_run_id=run_id,
            job_id=jc.job_id,
        )
        totals = trial_balance_totals(lines).as_json()
        transitions.apply(
            uow.session,
            "sync_run",
            run_id,
            to_status=SyncRunStatus.SUCCEEDED.value,
            expected_status=SyncRunStatus.RUNNING.value,
            set_values={
                "source_totals": totals,
                "loaded_totals": totals,
                "record_count": len(lines),
                "exception_count": 0,
                "finished_at": uow.now,
                **_moved_run(uow),
            },
        )
        uow.commit()
    return counts


def _read_and_attach(jc: JobContext, params: Mapping[str, Any]) -> dict[str, int]:
    """The upload path of ``attach-trial-balance``: the file the request already read."""
    attached = params[ATTACH_PARAM]
    file_id = UUID(str(attached["file_id"]))
    with jc.unit_of_work() as uow:
        held = _held(uow, UUID(str(params["reconciliation_id"])), None)
        if _already_attached(held, attached):
            return {"variances": int(held.row["variance_count"])}
        _require_attachable(uow, held)
        lines = _file_lines(uow, file_id, functional_currency=held.scope.functional_currency)
        counts = attach(uow, held, lines=lines, source_file_id=file_id, job_id=jc.job_id)
        uow.commit()
    return counts


def generation_failed(
    uow: UnitOfWork, params: Mapping[str, Any], problem: Mapping[str, Any]
) -> None:
    """The job's last attempt failed (BUILD_SPEC RPS-2 hook): the ``TRIAL_BALANCE_PULL`` run of an
    attach ends ``FAILED`` with the job's problem as its own (04 T-INT-02 ``problem``); a run
    already finished is left alone."""
    attached = params.get(ATTACH_PARAM) or {}
    if "sync_run_id" not in attached:
        return
    run_id = UUID(str(attached["sync_run_id"]))
    status = uow.session.execute(
        select(sync_run.c.status).where(sync_run.c.id == run_id).with_for_update()
    ).scalar_one_or_none()
    if status is None or _text(status) not in (
        SyncRunStatus.QUEUED.value,
        SyncRunStatus.RUNNING.value,
    ):
        return
    transitions.apply(
        uow.session,
        "sync_run",
        run_id,
        to_status=SyncRunStatus.FAILED.value,
        expected_status=_text(status),
        set_values={
            "problem": {**problem, "instance": SYNC_RUN_INSTANCE.format(run_id=run_id)},
            "finished_at": uow.now,
            **_moved_run(uow),
        },
    )


def failed_generation(
    session: Session, subject_type: str | None, subject_id: UUID, params: Mapping[str, Any]
) -> FailedSubject | None:
    """05 JOB-07 rev 1.165: what the exception item of a failed generation names. A generation
    on demand creates the reconciliation under the id its command chose, so a failed job may
    leave no row to read: the kind, the entity, the book and the period are the job's params,
    and together they are the record — a later generation of the same reconciliation settles
    the item, whatever its id."""
    entity_id, period_id = params.get("entity_id"), params.get("period_id")
    if entity_id is None or period_id is None:
        return None
    return FailedSubject(
        entity_id=UUID(str(entity_id)),
        period_id=UUID(str(period_id)),
        key=f"{params.get('kind')}:{entity_id}:{params.get('book_code')}:{period_id}",
    )


@task(
    GENERATE_JOB,
    retry=GENERATE_RETRY,
    on_failure=generation_failed,
    failed_item=failed_item(ExceptionSource.RECONCILIATION, failed_generation),
)
def run_generation(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``RECONCILIATION_GENERATE`` (05 §5.6 queue ``close``): the generation of a reconciliation,
    one transaction per reconciliation, or — with ``attach`` — the trial balance of a
    subledger-to-GL one. A retried attempt whose work is stored answers with it (DG-KRN-JOB-03).
    """
    attached = params.get(ATTACH_PARAM)
    if attached is None:
        with jc.unit_of_work() as uow:
            counts = generate(uow, params, job_id=jc.job_id)
            uow.commit()
    elif "file_id" in attached:
        counts = _read_and_attach(jc, params)
    else:
        counts = _pull_and_attach(jc, params)
    return JobOutcome(
        state="SUCCEEDED",
        result={
            "href": HREF.format(reconciliation_id=params["reconciliation_id"]),
            "counts": counts,
        },
    )


# --- commands ------------------------------------------------------------------------------------


def explain_item(
    uow: UnitOfWork,
    *,
    reconciliation_id: UUID,
    item_id: UUID,
    body: ReconciliationItemUpdateIn,
    check_version: Callable[[int], None],
) -> ReconciliationItemOut:
    """``PATCH /reconciliations/{id}/items/{item_id}`` (``If-Match`` of the item): the explanation
    of a difference while the reconciliation is ``DRAFT``; the explainer resolves the item. 409
    ``invalid-transition`` afterwards — a certified reconciliation changes only after the reopen of
    its period (T-CLS-07)."""
    session = uow.session
    held = _held(uow, reconciliation_id, PREPARE_PERMISSION)
    item = (
        session.execute(
            select(reconciliation_item)
            .where(
                reconciliation_item.c.id == item_id,
                reconciliation_item.c.reconciliation_id == reconciliation_id,
            )
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if item is None:
        raise Problem("not-found")
    check_version(int(item["row_version"]))
    if held.status == ReconciliationStatus.CERTIFIED.value:
        raise _certified(held)
    if held.status != ReconciliationStatus.DRAFT.value:
        raise _refused(NOT_DRAFT.format(no=held.number, status=held.status))
    require_open(held.scope)
    _require_current(uow, held)
    principal = uow.principal
    transitions.apply(
        session,
        ITEM_OBJECT,
        item_id,
        to_status=None,
        set_values={
            "explanation": body.explanation,
            "resolved_at": uow.now,
            "resolved_by": principal.id,
            "resolved_by_kind": principal.kind.value,
            "row_version": int(item["row_version"]) + 1,
            **_stamps(uow),
        },
        expected_row_version=int(item["row_version"]),
    )
    uow.audit(
        action=EXPLAIN_ACTION,
        object_type=ITEM_OBJECT,
        object_id=item_id,
        object_version=str(int(item["row_version"]) + 1),
        before={"explanation": item["explanation"]},
        after={
            "explanation": body.explanation,
            "reconciliation_id": str(reconciliation_id),
            "item_kind": str(item["item_kind"]),
        },
    )
    return get_item(session, item_id)


def prepare(uow: UnitOfWork, reconciliation_id: UUID) -> ReconciliationOut:
    """``POST /reconciliations/{id}/prepare`` (SM-09 ``DRAFT → PREPARED``): the preparer's sign-off
    of the fixed statement with the hash of the snapshot, which is frozen for review from here.
    403 ``mfa-required`` without an MFA-verified session; 409 ``invalid-transition`` while a
    difference has no explanation, outside ``DRAFT``, and for a reconciliation without its
    trial balance — none attached, or a file that was shredded since."""
    session = uow.session
    held = _held(uow, reconciliation_id, PREPARE_PERMISSION)
    _require_mfa(uow)
    if held.status == ReconciliationStatus.CERTIFIED.value:
        raise _certified(held)
    if held.status != ReconciliationStatus.DRAFT.value:
        raise _refused(NOT_PREPARABLE.format(no=held.number, status=held.status))
    require_open(held.scope)
    _require_current(uow, held)
    if _text(held.row["kind"]) == ReconciliationKind.SUBLEDGER_TO_GL.value and not _has_source(
        held.row
    ):
        raise _refused(NO_SOURCE.format(no=held.number), rule_id=RULE_SOURCE, field="source")
    # The file the statement was compared with is one that can still be read (04 T-PLT-29 "A
    # document a rule asks for"; rulings R-119 (g), R-120 (g)): read under the file row's lock,
    # which this sign-off holds to its commit — from then on the reconciliation holds the file.
    source_file_id = held.row["source_file_id"]
    if source_file_id is not None and not lock_readable(session, [source_file_id]):
        raise _refused(SOURCE_SHREDDED.format(no=held.number), rule_id=RULE_SOURCE, field="source")
    items = _item_rows(session, held.id)
    unexplained = sum(
        1 for item in items if Decimal(item["difference"]) != 0 and not item["explanation"]
    )
    if unexplained:
        raise _refused(UNEXPLAINED.format(n=unexplained), field="items")
    content_sha256 = sha256_hex(snapshot(held, items))
    signoff_id = _sign(
        uow,
        held,
        role=SignoffRole.PREPARER,
        statement=PREPARER_STATEMENT,
        content_sha256=content_sha256,
    )
    _move(uow, held, ReconciliationStatus.PREPARED)
    uow.audit(
        action=PREPARE_ACTION,
        object_type=OBJECT_TYPE,
        object_id=held.id,
        object_version=str(int(held.row["row_version"]) + 1),
        before={"status": held.status},
        after={
            "status": ReconciliationStatus.PREPARED.value,
            "signoff_id": str(signoff_id),
            "role": SignoffRole.PREPARER.value,
            "statement": PREPARER_STATEMENT,
            "subject_content_sha256": content_sha256,
        },
    )
    return get(session, uow.principal, held.id)


def sign(uow: UnitOfWork, reconciliation_id: UUID, body: ReconciliationSignIn) -> ReconciliationOut:
    """``POST /reconciliations/{id}/sign`` (SM-09 ``PREPARED → REVIEWED``): the reviewer's sign-off
    with a step-up verification (ACT-34). 403 ``self-approval`` for a preparer of the
    reconciliation (DB-10), 403 ``forbidden`` for a user who manages integrations (SoD-7), 409
    ``invalid-transition`` outside ``PREPARED`` or when the snapshot no longer hashes to the one the
    preparer signed."""
    if body.role is not SignoffRole.REVIEWER:
        raise _invalid("role", REVIEWER_ONLY, rule_id=RULE_STATES)
    if not body.statement_accepted:
        raise _invalid("statement_accepted", STATEMENT_REQUIRED, rule_id=RULE_STATEMENT)
    session = uow.session
    held = _held(uow, reconciliation_id, SIGNOFF_PERMISSION)
    principal = uow.principal
    if principal.permission_scopes.get(INTEGRATION_PERMISSION) is not None:
        error = ProblemError(rule_id=RULE_SOD, message=INTEGRATION_ADMIN)
        raise Problem("forbidden", INTEGRATION_ADMIN, errors=[error])
    if not mfa.step_up_fresh_at(principal.mfa_verified_at, uow.now):
        raise Problem("mfa-step-up-required", mfa.STEP_UP_REQUIRED)
    if held.status == ReconciliationStatus.CERTIFIED.value:
        raise _certified(held)
    if held.status != ReconciliationStatus.PREPARED.value:
        raise _refused(NOT_REVIEWABLE.format(no=held.number, status=held.status))
    require_open(held.scope)
    _require_current(uow, held)
    prepared = _signers(session, held.id, SignoffRole.PREPARER)
    if any(row["signer_id"] == principal.id for row in prepared):
        raise Problem("self-approval", OWN_PREPARATION)
    content_sha256 = sha256_hex(snapshot(held, _item_rows(session, held.id)))
    signed = {str(row["subject_content_sha256"]) for row in prepared}
    if signed != {content_sha256}:
        raise _refused(SNAPSHOT_CHANGED.format(no=held.number))
    signoff_id = _sign(
        uow,
        held,
        role=SignoffRole.REVIEWER,
        statement=REVIEWER_STATEMENT,
        content_sha256=content_sha256,
    )
    _move(uow, held, ReconciliationStatus.REVIEWED)
    uow.audit(
        action=SIGN_ACTION,
        object_type=OBJECT_TYPE,
        object_id=held.id,
        object_version=str(int(held.row["row_version"]) + 1),
        before={"status": held.status},
        after={
            "status": ReconciliationStatus.REVIEWED.value,
            "signoff_id": str(signoff_id),
            "role": SignoffRole.REVIEWER.value,
            "statement": REVIEWER_STATEMENT,
            "subject_content_sha256": content_sha256,
        },
    )
    return get(session, principal, held.id)


def reopen(
    uow: UnitOfWork, reconciliation_id: UUID, body: ReconciliationReopenIn
) -> ReconciliationOut:
    """``POST /reconciliations/{id}/reopen`` (SM-09 ``PREPARED``, ``REVIEWED`` → ``REOPENED``): the
    sign-offs stay as history and the reconciliation is generated again before the lock (04
    T-CLS-06: a ``REOPENED`` row is never reused). A certified reconciliation is reopened only by
    the reopen of its period."""
    held = _held(uow, reconciliation_id, REOPEN_PERMISSION)
    if held.status == ReconciliationStatus.CERTIFIED.value:
        raise _certified(held)
    if held.status not in SIGNED_STATUSES:
        raise _refused(NOT_REOPENABLE.format(no=held.number, status=held.status))
    require_open(held.scope)
    _move(uow, held, ReconciliationStatus.REOPENED)
    uow.audit(
        action=REOPEN_ACTION,
        object_type=OBJECT_TYPE,
        object_id=held.id,
        object_version=str(int(held.row["row_version"]) + 1),
        before={"status": held.status},
        after={"status": ReconciliationStatus.REOPENED.value},
        comment=body.reason,
    )
    return get(uow.session, uow.principal, held.id)


def _move(uow: UnitOfWork, held: _Held, to_status: ReconciliationStatus) -> None:
    transitions.apply(
        uow.session,
        OBJECT_TYPE,
        held.id,
        to_status=to_status.value,
        expected_status=held.status,
        set_values={"row_version": int(held.row["row_version"]) + 1, **_stamps(uow)},
    )


# --- reads ---------------------------------------------------------------------------------------

ROW_COLUMNS: Final = (
    *reconciliation.c,
    legal_entity.c.code.label("entity_code"),
    legal_entity.c.name.label("entity_name"),
    legal_entity.c.functional_currency,
    period.c.period_key,
    period.c.name.label("period_name"),
    period.c.start_date,
    period.c.end_date,
    (~gates.superseded()).label("is_current"),
)


def read[T](ctx: RequestContext, fn: Callable[[Session], T]) -> T:
    """Run ``fn`` in a read-only tenant session of the caller (DG-CMD-13)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return fn(session)


def read_scope(principal: Principal) -> frozenset[UUID] | None:
    """The entities the principal reads reconciliations of (``contract.read``); None for every
    entity (REQ-PLT-012: a holder restricted to named entities reads theirs only)."""
    scope = principal.permission_scopes.get(READ_PERMISSION)
    return None if scope is None or scope == "*" else frozenset(scope)


def statement(principal: Principal) -> Select[Any]:
    """API-S-Reconciliation rows inside the principal's ``contract.read`` scope."""
    row = reconciliation.c
    joined = reconciliation.join(
        legal_entity,
        and_(legal_entity.c.tenant_id == row.tenant_id, legal_entity.c.id == row.entity_id),
    ).join(period, and_(period.c.tenant_id == row.tenant_id, period.c.id == row.period_id))
    found = select(*ROW_COLUMNS).select_from(joined)
    entities = read_scope(principal)
    if entities is not None:
        found = found.where(reconciliation.c.entity_id.in_(sorted(entities, key=str)))
    return found


def _signoffs(session: Session, ids: Sequence[UUID]) -> dict[UUID, list[dict[str, Any]]]:
    found: dict[UUID, list[dict[str, Any]]] = {}
    if not ids:
        return found
    for row in session.execute(
        select(signoff)
        .where(signoff.c.subject_type == OBJECT_TYPE, signoff.c.subject_id.in_(ids))
        .order_by(signoff.c.signed_at, signoff.c.id)
    ).mappings():
        found.setdefault(UUID(str(row["subject_id"])), []).append(dict(row))
    return found


def _rules(session: Session, ids: Sequence[UUID]) -> dict[UUID, dict[str, Any]]:
    if not ids:
        return {}
    rows = session.execute(
        select(
            rule.c.id.label("rule_id"),
            rule.c.rule_key,
            rule_set_version.c.id.label("rule_set_version_id"),
            rule_set_version.c.version_no,
            rule_set.c.code.label("rule_set_code"),
        )
        .select_from(
            rule.join(
                rule_set_version,
                and_(
                    rule_set_version.c.tenant_id == rule.c.tenant_id,
                    rule_set_version.c.id == rule.c.rule_set_version_id,
                ),
            ).join(
                rule_set,
                and_(
                    rule_set.c.tenant_id == rule_set_version.c.tenant_id,
                    rule_set.c.id == rule_set_version.c.rule_set_id,
                ),
            )
        )
        .where(rule.c.id.in_(ids))
    ).mappings()
    return {UUID(str(row["rule_id"])): dict(row) for row in rows}


def summary_of(totals: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """API-S-Reconciliation ``summary``: per currency of ``totals``, in currency order, the number
    of distinct accounts its rows name, the sums of the two sides and of the differences (an
    absent amount counts as zero) and the number of rows that state no subledger amount (supervisor
    ruling R-74: a row marked ``not_stated``)."""
    found: dict[str, dict[str, Any]] = {}
    for total in totals:
        currency = str(total["currency"]).strip()
        row = found.setdefault(
            currency,
            {
                "accounts": set(),
                "subledger": Decimal(0),
                "source": Decimal(0),
                "difference": Decimal(0),
                "not_stated": 0,
            },
        )
        if total.get("account_code") is not None:
            row["accounts"].add(str(total["account_code"]))
        row["accounts"].update(str(code) for code in total.get("account_codes") or ())
        row["subledger"] += Decimal(str(total.get("subledger_amount") or 0))
        row["source"] += Decimal(str(total.get("source_amount") or 0))
        row["difference"] += Decimal(str(total.get("difference") or 0))
        row["not_stated"] += 1 if total.get("not_stated") else 0
    return [
        {
            "currency": currency,
            "account_count": len(row["accounts"]),
            "subledger_amount": _money(row["subledger"], currency),
            "source_amount": _money(row["source"], currency),
            "difference": _money(row["difference"], currency),
            "not_stated_count": row["not_stated"],
        }
        for currency, row in sorted(found.items())
    ]


ATTACH_JOB_COLUMNS: Final = (
    job.c.id,
    job.c.state,
    job.c.params,
    job.c.problem,
    job.c.subject_id,
    job.c.created_by,
    job.c.created_by_kind,
    job.c.created_at,
    job.c.finished_at,
)
# RFC 9457 base members a reader of the reconciliation sees of a failed attach (04 §16.8).
PROBLEM_MEMBERS: Final = ("type", "title", "status", "detail")


def _attach_requests(
    session: Session, rows: Sequence[Mapping[str, Any]]
) -> dict[UUID, dict[str, Any]]:
    """API-S-Reconciliation ``trial_balance`` by reconciliation id: the latest
    ``attach-trial-balance`` request of each subledger-to-GL row, without its ``job.created_by``
    actor (``outs`` reads the names once). ``attached_at`` is the instant of the CTL-025 execution
    the attach recorded, present once the row has its source."""
    ids = [
        UUID(str(row["id"]))
        for row in rows
        if _text(row["kind"]) == ReconciliationKind.SUBLEDGER_TO_GL.value
    ]
    if not ids:
        return {}
    latest: dict[UUID, dict[str, Any]] = {}
    for requested in session.execute(
        select(*ATTACH_JOB_COLUMNS)
        .where(
            job.c.kind == GENERATE_JOB.value,
            job.c.subject_type == OBJECT_TYPE,
            job.c.subject_id.in_(ids),
            job.c.params.has_key(ATTACH_PARAM),
        )
        .order_by(job.c.created_at, job.c.id)
    ).mappings():
        latest[UUID(str(requested["subject_id"]))] = dict(requested)
    if not latest:
        return {}
    requests = {key: dict(found["params"][ATTACH_PARAM]) for key, found in latest.items()}
    connection_ids = sorted(
        {
            UUID(str(item["integration_connection_id"]))
            for item in requests.values()
            if "integration_connection_id" in item
        },
        key=str,
    )
    file_ids = sorted(
        {UUID(str(item["file_id"])) for item in requests.values() if "file_id" in item}, key=str
    )
    connections = (
        {
            UUID(str(found_id)): str(name)
            for found_id, name in session.execute(
                select(integration_connection.c.id, integration_connection.c.name).where(
                    integration_connection.c.id.in_(connection_ids)
                )
            )
        }
        if connection_ids
        else {}
    )
    files = (
        {
            UUID(str(found_id)): str(name)
            for found_id, name in session.execute(
                select(file_object.c.id, file_object.c.original_filename).where(
                    file_object.c.id.in_(file_ids)
                )
            )
        }
        if file_ids
        else {}
    )
    compared = {
        UUID(str(found_id)): at
        for found_id, at in session.execute(
            select(control_execution.c.run_ref_id, func.max(control_execution.c.executed_at))
            .where(
                control_execution.c.control_id == CONTROL_GL,
                control_execution.c.run_ref_type == RunRefType.RECONCILIATION_RUN.value,
                control_execution.c.run_ref_id.in_(sorted(latest, key=str)),
            )
            .group_by(control_execution.c.run_ref_id)
        )
    }
    sourced = {UUID(str(row["id"])) for row in rows if _has_source(row)}
    out: dict[UUID, dict[str, Any]] = {}
    for key, found in latest.items():
        request = requests[key]
        file_id = UUID(str(request["file_id"])) if "file_id" in request else None
        connection_id = (
            None if file_id is not None else UUID(str(request["integration_connection_id"]))
        )
        problem = found["problem"]
        out[key] = {
            "source": "FILE" if file_id is not None else "ADAPTER",
            "integration_connection": None
            if connection_id is None
            else {"id": connection_id, "name": connections.get(connection_id, "")},
            "file": None if file_id is None else {"id": file_id, "name": files.get(file_id, "")},
            "job": {
                "id": found["id"],
                "state": _text(found["state"]),
                "created_by": (found["created_by"], _text(found["created_by_kind"])),
                "created_at": found["created_at"],
                "finished_at": found["finished_at"],
                "problem": None
                if problem is None
                else {name: problem.get(name) for name in PROBLEM_MEMBERS},
            },
            "attached_at": compared.get(key) if key in sourced else None,
        }
    return out


def _pull_connections(
    session: Session, rows: Sequence[Mapping[str, Any]], principal: Principal | None
) -> dict[UUID, list[dict[str, Any]]]:
    """API-S-Reconciliation ``gl_connections`` by entity id (supervisor ruling R-68 (c)): for the
    entities of the subledger-to-GL rows that the caller's ``recon.prepare`` covers, the ``ACTIVE``
    connections of an adapter that states a trial balance and that serve the entity (T-INT-01
    ``entity_ids``: empty = every entity), in name order — those ``_gl_connection`` admits."""
    scope = None if principal is None else principal.permission_scopes.get(PREPARE_PERMISSION)
    if scope is None:
        return {}
    entities = {
        UUID(str(row["entity_id"]))
        for row in rows
        if _text(row["kind"]) == ReconciliationKind.SUBLEDGER_TO_GL.value
    }
    if isinstance(scope, frozenset):
        entities &= scope
    if not entities:
        return {}
    found = session.execute(
        select(
            integration_connection.c.id,
            integration_connection.c.name,
            integration_connection.c.entity_ids,
        )
        .where(
            integration_connection.c.adapter.in_(sorted(TRIAL_BALANCE_ADAPTERS)),
            integration_connection.c.status == ACTIVE_CONNECTION,
        )
        .order_by(integration_connection.c.name, integration_connection.c.id)
    ).all()
    out: dict[UUID, list[dict[str, Any]]] = {}
    for entity_id in entities:
        out[entity_id] = [
            {"id": connection_id, "name": str(name)}
            for connection_id, name, served in found
            if not served or entity_id in {UUID(str(value)) for value in served}
        ]
    return out


def outs(
    session: Session, rows: Sequence[Mapping[str, Any]], principal: Principal | None = None
) -> list[ReconciliationOut]:
    """API-S-Reconciliation of each ``statement`` row with its sign-offs, its rule, its key figures
    and its latest attach request; ``principal`` is the reader, whose ``recon.prepare`` decides
    ``gl_connections`` (none without a reader)."""
    ids = [UUID(str(row["id"])) for row in rows]
    signed = _signoffs(session, ids)
    attaches = _attach_requests(session, rows)
    pullable = _pull_connections(session, rows, principal)
    rules = _rules(
        session,
        [UUID(str(row["auto_certify_rule_id"])) for row in rows if row["auto_certify_rule_id"]],
    )
    names = approval_queries.display_names(
        session,
        [row["created_by"] for row in rows]
        + [item["signer_id"] for items in signed.values() for item in items]
        + [item["job"]["created_by"][0] for item in attaches.values()],
    )
    for item in attaches.values():
        requester, requester_kind = item["job"]["created_by"]
        item["job"]["created_by"] = approval_queries.actor(requester, requester_kind, names)
    user = PrincipalKind.USER.value
    readable = _readable_contracts(session, rows)
    found: list[ReconciliationOut] = []
    for row in rows:
        functional = str(row["functional_currency"]).strip()
        rule_id = row["auto_certify_rule_id"]
        found.append(
            ReconciliationOut.model_validate(
                {
                    "id": row["id"],
                    "reconciliation_no": row["reconciliation_no"],
                    "kind": _text(row["kind"]),
                    "entity": {
                        "id": row["entity_id"],
                        "code": row["entity_code"],
                        "name": row["entity_name"],
                    },
                    "book": _text(row["book_code"]),
                    "period": {
                        "id": row["period_id"],
                        "period_key": row["period_key"],
                        "name": row["period_name"],
                        "start_date": row["start_date"],
                        "end_date": row["end_date"],
                    },
                    "status": _text(row["status"]),
                    "is_current": bool(row["is_current"]),
                    "as_of_known_at": row["as_of_known_at"],
                    "period_lock_id": row["period_lock_id"],
                    "source_file_id": row["source_file_id"],
                    "sync_run_id": row["sync_run_id"],
                    "totals": [_total_out(total, readable) for total in row["totals"] or []],
                    "summary": summary_of(row["totals"] or []),
                    "trial_balance": attaches.get(UUID(str(row["id"]))),
                    "gl_connections": pullable.get(UUID(str(row["entity_id"])), [])
                    if _text(row["kind"]) == ReconciliationKind.SUBLEDGER_TO_GL.value
                    else [],
                    "variance_count": row["variance_count"],
                    "unexplained_other_amount": _money(row["unexplained_other_amount"], functional),
                    "auto_certify_rule": None if rule_id is None else rules.get(UUID(str(rule_id))),
                    "report_run_id": row["report_run_id"],
                    "certified_at": row["certified_at"],
                    "signoffs": [
                        {
                            "id": item["id"],
                            "role": _text(item["role"]),
                            "signer": approval_queries.actor(item["signer_id"], user, names),
                            "statement": item["statement"],
                            "subject_content_sha256": str(item["subject_content_sha256"]),
                            "signed_at": item["signed_at"],
                        }
                        for item in signed.get(UUID(str(row["id"])), [])
                    ],
                    "created_by": approval_queries.actor(
                        row["created_by"], _text(row["created_by_kind"]), names
                    ),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "row_version": row["row_version"],
                }
            )
        )
    return found


def _named_contracts(total: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The contracts a stored ``totals`` row names in ``not_stated``; none on any other row."""
    return list((total.get("not_stated") or {}).get("contracts") or [])


def _readable_contracts(session: Session, rows: Sequence[Mapping[str, Any]]) -> frozenset[str]:
    """Of the contracts the not-stated role rows of ``rows`` name, the ids the reader reads.

    ``totals`` is stored once for every reader and names each contract concerned, and
    ``contract`` is RLS-TE on the contracting entity. The join is this one statement under the
    reader's own session (supervisor ruling of 2026-10-01 21:23, point 4): what it returns is
    named, the rest is counted (``not_stated.contract_count``).

    As the engine stands the rest is empty: a contract's balances are held with the contract's
    own contracting entity (stage 10; T-CON-09 rows are written for no other), so every contract
    a role of an entity names is that entity's, and whoever reads the reconciliation reads it
    (04 T-CLS-06 "Role basis", the correction of rev 1.259). T-CON-09's key (contract, entity)
    allows a balance of one entity under another entity's contract; the rule is what the read
    does should a later revision write one."""
    named = sorted(
        {
            UUID(str(item["id"]))
            for row in rows
            for total in row["totals"] or []
            for item in _named_contracts(total)
        },
        key=str,
    )
    if not named:
        return frozenset()
    return frozenset(
        str(found)
        for found in session.execute(
            select(contract.c.id).where(contract.c.id.in_(named))
        ).scalars()
    )


def _total_out(total: Mapping[str, Any], readable: frozenset[str]) -> dict[str, Any]:
    currency = str(total["currency"])
    stated = total.get("not_stated")
    named = _named_contracts(total)
    return {
        "account_code": total.get("account_code"),
        "account_role": total.get("account_role"),
        "account_codes": list(total.get("account_codes") or ()),
        "currency": currency,
        "subledger_amount": _money(total.get("subledger_amount"), currency),
        "source_amount": _money(total.get("source_amount"), currency),
        "difference": _money(total.get("difference"), currency),
        "not_stated": None
        if stated is None
        else {
            "reason": stated["reason"],
            "contracts": [item for item in named if str(item["id"]) in readable],
            "contract_count": len(named),
        },
    }


def row_of(session: Session, principal: Principal, reconciliation_id: UUID) -> dict[str, Any]:
    """The ``statement`` row of a reconciliation the principal reads, else 404 ``not-found``."""
    row = (
        session.execute(statement(principal).where(reconciliation.c.id == reconciliation_id))
        .mappings()
        .first()
    )
    if row is None:
        raise Problem("not-found")
    return dict(row)


def get(session: Session, principal: Principal, reconciliation_id: UUID) -> ReconciliationOut:
    """``GET /reconciliations/{id}``."""
    return outs(session, [row_of(session, principal, reconciliation_id)], principal)[0]


ITEM_COLUMNS: Final = (*reconciliation_item.c, contract.c.external_id.label("contract_external_id"))


def items_statement(reconciliation_id: UUID) -> Select[Any]:
    """The T-CLS-07 rows of a reconciliation with their contracts' external ids."""
    joined = reconciliation_item.outerjoin(
        contract,
        and_(
            contract.c.tenant_id == reconciliation_item.c.tenant_id,
            contract.c.id == reconciliation_item.c.contract_id,
        ),
    )
    return (
        select(*ITEM_COLUMNS)
        .select_from(joined)
        .where(reconciliation_item.c.reconciliation_id == reconciliation_id)
    )


def item_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[ReconciliationItemOut]:
    names = approval_queries.display_names(session, (row["resolved_by"] for row in rows))
    found: list[ReconciliationItemOut] = []
    for row in rows:
        currency = str(row["currency"]).strip()
        resolved_kind = row["resolved_by_kind"]
        found.append(
            ReconciliationItemOut.model_validate(
                {
                    "id": row["id"],
                    "reconciliation_id": row["reconciliation_id"],
                    "item_kind": row["item_kind"],
                    "account_code": row["account_code"],
                    "account_role": row["account_role"],
                    "contract": None
                    if row["contract_id"] is None or row["contract_external_id"] is None
                    else {"id": row["contract_id"], "external_id": row["contract_external_id"]},
                    "invoice_number": row["invoice_number"],
                    "gl_document_reference": row["gl_document_reference"],
                    "currency": currency,
                    "subledger_amount": _money(row["subledger_amount"], currency),
                    "source_amount": _money(row["source_amount"], currency),
                    "difference": _money(row["difference"], currency),
                    "is_high_risk": bool(row["is_high_risk"]),
                    "explanation": row["explanation"],
                    "resolved_at": row["resolved_at"],
                    "resolved_by": None
                    if row["resolved_at"] is None
                    else approval_queries.actor(row["resolved_by"], _text(resolved_kind), names),
                    "row_version": row["row_version"],
                }
            )
        )
    return found


def get_item(session: Session, item_id: UUID) -> ReconciliationItemOut:
    row = (
        session.execute(
            select(*ITEM_COLUMNS)
            .select_from(
                reconciliation_item.outerjoin(
                    contract,
                    and_(
                        contract.c.tenant_id == reconciliation_item.c.tenant_id,
                        contract.c.id == reconciliation_item.c.contract_id,
                    ),
                )
            )
            .where(reconciliation_item.c.id == item_id)
        )
        .mappings()
        .one()
    )
    return item_outs(session, [dict(row)])[0]
