"""GL adapter port (05 §5.2 ``GLAdapter``, ADP-10 to ADP-15, ADP-31; 03 REQ-JE-012; dev-guide
DG-LAY-03; BUILD_SPEC CLO-13, CLO-15).

``GLAdapter`` is the protocol every general ledger adapter implements: it validates accounts and
dimensions, posts one chunk idempotently by its external id, finds a posting after a timeout, and
pulls the chart of accounts and a trial balance. ``JournalChunk`` is what a batch sends and
``PostingResult`` what the adapter answers. The error classes are those of ADP-12: ``Transient`` is
retried on the ADP-12 schedule, ``Duplicate`` names the document the ERP already holds, and
``Permanent`` is never retried.

Adapters live under ``erev_api.adapters.gl`` and are wired only in composition roots and test
fixtures (DG-LAY-03). A root registers one factory per E-37 literal with ``register_gl_adapter``,
and the export relay builds an adapter per dispatch with ``gl_adapter_for``. An adapter that
reaches an ERP is built for one ``integration_connection``: ``GLContext`` carries the connection's
``base_url`` and non-secret ``config`` (CLO-15), and ``DEFAULT_MAX_LINES`` holds the ADP-11 chunk
sizes a connection's ``config.max_lines_per_chunk`` overrides.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Final, Literal, Protocol

from erev_api.enums import GlAdapter
from erev_api.events.outbox import Undeliverable

type AdapterCode = Literal["CSV_GL", "NETSUITE", "QUICKBOOKS_ONLINE"]
type PostingStatus = Literal["EXPORTED", "POSTED", "DUPLICATE"]


@dataclass(frozen=True, slots=True)
class AccountRef:
    """An account by its code. ``account_type`` is the E-52 literal when the caller knows it (the
    relay's chart of the batch's entity): an ERP adapter states it with a line's account, so a
    ledger that opens the account knows whether its balance is cumulative or fiscal year to date
    (CLO-15)."""

    code: str
    name: str
    account_type: str | None = None


@dataclass(frozen=True, slots=True)
class DimensionRef:
    code: str
    value: str


@dataclass(frozen=True, slots=True)
class EntityRef:
    code: str


@dataclass(frozen=True, slots=True)
class PeriodRef:
    period_key: str
    start_date: date
    end_date: date


@dataclass(frozen=True, slots=True)
class TrialBalanceLine:
    """One account of a trial balance (03 REQ-INT-009; supervisor ruling R-54 (e)): the closing
    balance at the period end in ``currency`` — the entity's functional currency — debit positive
    and credit negative. A balance sheet account is cumulative; an income statement account
    (E-52 ``REVENUE``, ``EXPENSE``) is stated for the fiscal year to date."""

    account_code: str
    currency: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class TrialBalanceDetail:
    """One GL document on one account with a posting date inside the period, in the sign and
    currency of ``TrialBalanceLine``. ``external_id`` is the ADP-10 external id of the chunk when
    the document was posted by this subledger, None for a document made in the ERP (03
    REQ-CLS-016: a direct GL entry to a subledger-controlled account)."""

    account_code: str
    currency: str
    amount: Decimal
    document_reference: str
    external_id: str | None = None
    posted_date: date | None = None


@dataclass(frozen=True, slots=True)
class TrialBalance:
    """``lines`` and ``details`` are additive (supervisor ruling R-54 (e)): an adapter that fills
    only ``balances`` states them in the entity's functional currency and supplies no document."""

    entity_code: str
    period_key: str
    balances: Mapping[str, Decimal]  # account code → signed balance
    lines: tuple[TrialBalanceLine, ...] = ()
    details: tuple[TrialBalanceDetail, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationResult:
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class ChunkLine:
    """One journal line of a chunk (04 T-SL-09; the REQ-JE-011 columns)."""

    je_no: str
    line_no: int
    account_code: str
    account_name: str
    account_role: str
    debit: Decimal  # transaction currency
    credit: Decimal
    debit_functional: Decimal
    credit_functional: Decimal
    dimensions: Mapping[str, str]
    memo: str | None
    source_references: str


@dataclass(frozen=True, slots=True)
class JournalChunk:
    """One chunk of a batch with its deterministic external id (ADP-10, ADP-11)."""

    external_id: str
    run_no: str
    batch_no: int
    chunk_no: int
    entity_code: str
    posting_period: str  # period key
    period_end_date: date
    txn_currency: str
    functional_currency: str
    lines: tuple[ChunkLine, ...]

    @property
    def accounts(self) -> tuple[AccountRef, ...]:
        names = {line.account_code: line.account_name for line in self.lines}
        return tuple(AccountRef(code=code, name=names[code]) for code in sorted(names))

    @property
    def dimensions(self) -> tuple[DimensionRef, ...]:
        pairs = {(code, value) for line in self.lines for code, value in line.dimensions.items()}
        return tuple(DimensionRef(code=code, value=value) for code, value in sorted(pairs))


@dataclass(frozen=True, slots=True)
class PostingResult:
    """What an adapter answers for a chunk (ADP-31): ``EXPORTED`` for a file export that waits for a
    manual confirmation (ADP-33); ``POSTED`` or ``DUPLICATE`` with the ERP document id."""

    external_id: str
    status: PostingStatus
    gl_document_id: str | None = None
    gl_posted_date: date | None = None
    response_sha256: str | None = None
    message: str | None = None
    artifact: bytes | None = field(default=None, repr=False)  # CSV_GL: the REQ-JE-011 ZIP
    artifact_name: str | None = None


class Transient(Exception):
    """A timeout, connection error, 408, 429 or 5xx: the relay retries on the ADP-12 schedule.
    ``retry_after`` is the ``Retry-After`` of a 429 or 503 in seconds, when the ERP states one: the
    next attempt is not made earlier (CLO-15)."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class Accepted(Transient):
    """The ERP took the chunk and did not show the posting when the adapter read it back (05
    ADP-12 rev 1.175; item JRN-EXIT-SETTLE-1). For the relay it is a ``Transient``: the schedule
    retries it, and each retry asks ``get_posting`` first. It is a class of its own for what it
    says — the ledger said yes: its name is what the relay keeps as the message's ``last_error``
    (``outbox.error_name``), and the cancel of a failed run and the hand-over of a failed batch
    refuse a batch whose message died of it at any age (04 §16.7 rev 1.247), because the ledger's
    "not found" is then no evidence that it holds nothing."""


class Duplicate(Exception):
    """The ERP already holds the external id: the relay records ``DUPLICATE`` (ADP-12)."""

    def __init__(self, external_id: str, gl_document_id: str) -> None:
        super().__init__(f"{external_id} is already posted as {gl_document_id}.")
        self.external_id = external_id
        self.gl_document_id = gl_document_id


class Permanent(Undeliverable):
    """A 4xx validation failure or an unknown account: never retried (ADP-12)."""


class GLAdapter(Protocol):
    """05 §5.2: every method is synchronous, takes explicit inputs and returns typed results."""

    @property
    def code(self) -> AdapterCode: ...

    def validate_accounts(
        self, accounts: Sequence[AccountRef], dimensions: Sequence[DimensionRef]
    ) -> ValidationResult: ...

    def post_chunk(self, chunk: JournalChunk) -> PostingResult:
        """Post ``chunk``; idempotent by ``chunk.external_id`` (ADP-10)."""
        ...

    def get_posting(self, external_id: str) -> PostingResult | None:
        """The posting of ``external_id``, for recovery after a timeout (ADP-12)."""
        ...

    def pull_chart_of_accounts(self) -> Sequence[AccountRef]:
        """REQ-INT-008."""
        ...

    def pull_trial_balance(
        self, entity: EntityRef, period: PeriodRef, accounts: Sequence[str]
    ) -> TrialBalance:
        """REQ-INT-009."""
        ...


@dataclass(frozen=True, slots=True)
class GLContext:
    """What a factory builds an adapter from: the workspace code and its chart of accounts, and —
    for an adapter that reaches an ERP — the ``base_url`` and the non-secret ``config`` of the
    ``integration_connection`` the batch or the pull names (04 T-INT-01; CLO-15). ``CSV_GL`` needs
    neither."""

    tenant_code: str
    accounts: tuple[AccountRef, ...]
    base_url: str | None = None
    config: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


type GLAdapterFactory = Callable[[GLContext], GLAdapter]

# 05 ADP-11: the lines one chunk may hold, by E-37 literal; None = no limit. A connection's
# ``config.max_lines_per_chunk`` overrides its adapter's default.
DEFAULT_MAX_LINES: Final[Mapping[GlAdapter, int | None]] = MappingProxyType(
    {GlAdapter.CSV: None, GlAdapter.NETSUITE: 500, GlAdapter.QUICKBOOKS_ONLINE: 250}
)
MAX_LINES_KEY: Final = "max_lines_per_chunk"

# One factory per E-37 literal, registered by composition roots and test fixtures (DG-LAY-03).
GL_ADAPTERS: Final[dict[GlAdapter, GLAdapterFactory]] = {}


def register_gl_adapter(code: GlAdapter, factory: GLAdapterFactory) -> None:
    """Register the factory of the adapter ``code`` names (E-37)."""
    GL_ADAPTERS[GlAdapter(code)] = factory


def gl_adapter_for(code: GlAdapter, context: GLContext) -> GLAdapter:
    """A new adapter for ``code``; ``LookupError`` while no root registered one, so the relay
    retries the message instead of exporting nothing (XR-12)."""
    factory = GL_ADAPTERS.get(GlAdapter(code))
    if factory is None:
        raise LookupError(f"no GL adapter is registered for {GlAdapter(code).value}")
    return factory(context)
