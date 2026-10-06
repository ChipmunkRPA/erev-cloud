"""Inbound adapter port (05 §5.2 ``InboundAdapter``, ADP-01 to ADP-05, ADP-12, ADP-14 to ADP-16;
04 T-INT-01, T-INT-02, T-SRC-01; 03 REQ-INT-001 to REQ-INT-004; dev-guide DG-LAY-03; BUILD_SPEC
DIN-12; lane F-DIN preparation).

``InboundAdapter`` is the protocol every inbound (CRM / billing) adapter implements: it verifies a
webhook notification, pages the source's changes from a checkpoint (poll and sweep), fetches one
object as the truth before acting, normalises an object purely into canonical records, and answers
the control totals of a page. ``SourceObject``, ``ChangePage``, ``NormalisedRecords`` and
``ControlTotals`` are the typed results; the error classes are those of ADP-12 (``Transient``
is retried on the ADP-12 schedule, ``Permanent`` never). The sync-run ledger, the ``SYNC_RUN`` job
and the ``SYNC_REQUEST`` outbox handler that drive an adapter are the dispatched DIN-12 lane's
(T-INT-02, API-R-45); this module and its adapters are pure over their inputs and a supplied
HTTP client.

Adapters live under ``erev_api.adapters.crm`` / ``erev_api.adapters.billing`` and are wired only
in composition roots and test fixtures (DG-LAY-03): a root registers one factory per adapter code
with ``register_inbound_adapter`` and the sync job builds one with ``inbound_adapter_for``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Final, Literal, Protocol

from pydantic import SecretStr

from erev_api.enums import SourceObjectType, SourceSystem

__all__ = [
    "CHART_ADAPTERS",
    "CHART_SOURCES",
    "INBOUND_ADAPTERS",
    "NOW_HOOK",
    "SWEEP_AFTER",
    "AdapterCode",
    "ChangePage",
    "ChartAccount",
    "ChartSource",
    "ChartValue",
    "Checkpoint",
    "ControlTotals",
    "Duplicate",
    "InboundAdapter",
    "InboundContext",
    "Notification",
    "NormalisedInvoiceDraft",
    "NormalisedInvoiceLine",
    "NormalisedLine",
    "NormalisedOrderDraft",
    "NormalisedRecords",
    "Permanent",
    "SourceObject",
    "Transient",
    "Undeliverable",
    "WebhookNotice",
    "chart_source_for",
    "compare_totals",
    "inbound_adapter_for",
    "register_chart_source",
    "register_inbound_adapter",
    "sweep_due",
    "transient_status",
]

type AdapterCode = Literal["SALESFORCE", "STRIPE"]

# ADP-16: a replay-id checkpoint older than this triggers a RECONCILIATION_SWEEP by last-modified
# time.
SWEEP_AFTER: Final = timedelta(hours=72)
# The ``InboundContext.config`` member through which an adapter reads the time: a callable that
# answers an aware datetime. The sync job and the probe set it to their application clock
# (``sync.adapter_for``), so the 72 hours above are never measured on the wall clock.
NOW_HOOK: Final = "now"


class Undeliverable(Exception):
    """Base of the ADP-12 error classes."""


class Transient(Undeliverable):
    """Timeout, connection error, 408, 429 with ``Retry-After`` or 5xx: retried (ADP-12).
    ``retry_after`` carries the source's ``Retry-After`` seconds when it sent one."""

    def __init__(
        self, message: str, *, status: int | None = None, retry_after: float | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


class Duplicate(Undeliverable):
    """The source reports the object as already delivered (a notification replay)."""


class Permanent(Undeliverable):
    """A 4xx validation failure or an unknown object: never retried (ADP-12)."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def transient_status(status: int) -> bool:
    """ADP-12: 408, 429 and every 5xx are ``Transient`` and retried on the schedule; every other
    non-2xx status is ``Permanent`` (05 rev 1.12 after Codex's DIN-R3 — a whitelist of four 5xx
    codes had made 501 and 507 permanent without a retry)."""
    return status in (408, 429) or 500 <= status < 600


def stated_term(value: object, name: str) -> bool | None:
    """What a source object states of one of the two terms a booking carries (05 ADP-16, ADP-17
    rev 1.204; item ACT-FLAGS-1): a JSON boolean, or the words ``true`` and ``false`` (a metadata
    value is a string); a missing, null or empty value is None — "not stated", which the
    activation's routing flags as such. Any other value is ``Permanent``: nothing is presumed of a
    term the source spelled another way."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise Permanent(f"{name} is neither true nor false")


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """``integration_connection.checkpoint`` (T-INT-01): a replay id for the event feed and the
    last-modified watermark of the last sweep, both optional, plus when the replay id was set and
    when a sweep last ran to completion."""

    replay_id: int | None = None
    replay_at: datetime | None = None
    last_modified_watermark: datetime | None = None
    # 05 rev 1.12 (DIN-R2 residual): the within-source continuation of a budget-stopped sweep —
    # the Salesforce query locator, or Stripe's source index and ``starting_after`` — so the next
    # call resumes where the sweep stopped instead of re-reading the same prefix; None when no
    # sweep is in progress. Adapter-specific and opaque to callers; serialised with the checkpoint.
    sweep_cursor: Mapping[str, Any] | None = None
    # 04 T-INT-01 rev 1.103: when a reconciliation sweep of the connection last ran to completion.
    # The sync job stamps it on its own clock and carries it across the checkpoints the adapters
    # answer — an adapter neither reads nor writes it. The first completed sweep of a connection is
    # its baseline load; after it, a version a sweep stores is one the feed never delivered
    # (REQ-INT-007, ``SOURCE_VERSION_GAP``). Serialised only once set.
    swept_at: datetime | None = None

    def as_json(self) -> dict[str, Any]:
        stated: dict[str, Any] = {
            "replay_id": self.replay_id,
            "replay_at": None if self.replay_at is None else self.replay_at.isoformat(),
            "last_modified_watermark": (
                None
                if self.last_modified_watermark is None
                else self.last_modified_watermark.isoformat()
            ),
            "sweep_cursor": None if self.sweep_cursor is None else dict(self.sweep_cursor),
        }
        if self.swept_at is not None:
            stated["swept_at"] = self.swept_at.isoformat()
        return stated

    @classmethod
    def from_json(cls, values: Mapping[str, Any] | None) -> Checkpoint:
        values = values or {}
        replay_at = values.get("replay_at")
        watermark = values.get("last_modified_watermark")
        cursor = values.get("sweep_cursor")
        swept_at = values.get("swept_at")
        return cls(
            swept_at=None if swept_at is None else datetime.fromisoformat(str(swept_at)),
            sweep_cursor=dict(cursor) if isinstance(cursor, Mapping) and cursor else None,
            replay_id=None if values.get("replay_id") is None else int(values["replay_id"]),
            replay_at=None if replay_at is None else datetime.fromisoformat(str(replay_at)),
            last_modified_watermark=(
                None if watermark is None else datetime.fromisoformat(str(watermark))
            ),
        )


def sweep_due(checkpoint: Checkpoint, now: datetime) -> bool:
    """ADP-16: the next poll runs a ``RECONCILIATION_SWEEP`` when the replay id is older than
    ``SWEEP_AFTER`` (or was never set while a watermark exists)."""
    if checkpoint.replay_id is None:
        return checkpoint.last_modified_watermark is not None
    if checkpoint.replay_at is None:
        return True
    return now - checkpoint.replay_at > SWEEP_AFTER


@dataclass(frozen=True, slots=True)
class Notification:
    """One change notification of the source: which object, which version, in which order."""

    notification_id: str
    object_type: SourceObjectType
    external_id: str
    external_version: str
    replay_id: int


@dataclass(frozen=True, slots=True)
class WebhookNotice:
    """ADP-01: a verified webhook carries notifications and nothing else is acted on."""

    verified: bool
    notifications: tuple[Notification, ...] = ()
    reason: str | None = None  # why verification failed, never the secret


@dataclass(frozen=True, slots=True)
class SourceObject:
    """One fetched source object: the T-SRC-01 identity and its raw payload."""

    source_system: SourceSystem
    object_type: SourceObjectType
    external_id: str
    external_version: str
    version_order: int
    payload: Mapping[str, Any]
    last_modified: datetime | None = None


@dataclass(frozen=True, slots=True)
class ChangePage:
    """One page of ``fetch_changes``: the notifications (or swept objects) and the next
    checkpoint."""

    notifications: tuple[Notification, ...]
    checkpoint: Checkpoint
    has_more: bool = False
    kind: Literal["POLL", "SWEEP"] = "POLL"
    # Source pages consumed to build this page (05 rev 1.12: a sweep pages to exhaustion before its
    # watermark advances; ``has_more`` with a SWEEP means the page budget stopped it first).
    pages: int = 1


@dataclass(frozen=True, slots=True)
class NormalisedLine:
    """A canonical order line before referential validation (T-SRC-03 members)."""

    line_external_id: str
    product_code: str
    quantity: Decimal
    total_price: Decimal
    start_date: date | None = None
    end_date: date | None = None
    performing_entity_code: str | None = None


@dataclass(frozen=True, slots=True)
class NormalisedOrderDraft:
    """A canonical order header before referential validation (T-SRC-02 members without the ids
    the database assigns: ``source_record_id`` and ``customer_id`` are resolved by the sync)."""

    source_system: SourceSystem
    external_order_id: str
    external_version: str
    order_number: str
    order_date: date
    customer_external_id: str
    legal_entity_code: str
    transaction_currency: str
    lines: tuple[NormalisedLine, ...]
    po_number: str | None = None
    parent_order_external_id: str | None = None
    amendment_reason: str | None = None
    payment_terms: str | None = None
    document_ref: str | None = None
    custom_attributes: Mapping[str, Any] = field(default_factory=dict)
    # 05 ADP-16, ADP-17 rev 1.204 (item ACT-FLAGS-1): what the source states of the two terms a
    # booking carries (04 API-S-ContractBooked ``acceptance_clause``, ``side_letter``); None is
    # "the source did not state it" (``stated_term``).
    acceptance_clause: bool | None = None
    side_letter: bool | None = None

    @property
    def is_amendment(self) -> bool:
        """ADP-05: an amended order becomes a DRAFT modification, never a ``CONTRACT_AMENDED``."""
        return self.parent_order_external_id is not None or self.amendment_reason is not None

    @property
    def total(self) -> Decimal:
        return sum((line.total_price for line in self.lines), Decimal(0))


@dataclass(frozen=True, slots=True)
class NormalisedInvoiceLine:
    """A canonical billing line before referential validation (T-SRC-05 members): the service
    period is the ``BILLING_RECORDED`` hint of ADP-17 (REQ-INT-005)."""

    line_external_id: str
    product_code: str
    amount: Decimal
    quantity: Decimal = Decimal(1)
    service_period_start: date | None = None
    service_period_end: date | None = None
    contract_ref: str | None = None  # the source contract (a Stripe subscription id)
    obligation_ref: str | None = None


@dataclass(frozen=True, slots=True)
class NormalisedInvoiceDraft:
    """A canonical invoice or credit memo before referential validation (T-SRC-04 members without
    the ids the database assigns). ``document_kind`` is ``INVOICE`` or ``CREDIT_MEMO``; a credit
    memo names the invoice it credits (``credited_invoice_external_id``)."""

    source_system: SourceSystem
    external_invoice_id: str
    external_version: str
    document_kind: Literal["INVOICE", "CREDIT_MEMO"]
    invoice_number: str
    issue_date: date
    customer_external_id: str
    currency: str
    lines: tuple[NormalisedInvoiceLine, ...]
    due_date: date | None = None
    is_cancellable: bool = False
    legal_entity_code: str | None = None
    credited_invoice_external_id: str | None = None
    document_ref: str | None = None
    custom_attributes: Mapping[str, Any] = field(default_factory=dict)

    @property
    def total(self) -> Decimal:
        """Positive for an invoice, negative for a credit memo (the billing movement)."""
        amount = sum((line.amount for line in self.lines), Decimal(0))
        return -amount if self.document_kind == "CREDIT_MEMO" else amount


@dataclass(frozen=True, slots=True)
class NormalisedRecords:
    """What ``normalise`` answers for one object: the draft records and the mapping version."""

    mapping_version: str
    orders: tuple[NormalisedOrderDraft, ...] = ()
    invoices: tuple[NormalisedInvoiceDraft, ...] = ()


@dataclass(frozen=True, slots=True)
class ControlTotals:
    """T-INT-02 ``source_totals`` / ``loaded_totals``: ``{count, amount_by_currency, sha256}``."""

    count: int
    amount_by_currency: Mapping[str, Decimal]
    sha256: str

    def as_json(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "amount_by_currency": {
                code: format(amount, "f")
                for code, amount in sorted(self.amount_by_currency.items())
            },
            "sha256": self.sha256,
        }

    @classmethod
    def of(cls, items: Sequence[tuple[str, str, str, Decimal]]) -> ControlTotals:
        """Totals over ``(external_id, external_version, currency, amount)`` items; the digest is
        the SHA-256 of the canonical JSON of the sorted identities and amounts."""
        by_currency: dict[str, Decimal] = {}
        rows: list[list[str]] = []
        for external_id, version, currency, amount in sorted(items):
            by_currency[currency] = by_currency.get(currency, Decimal(0)) + amount
            rows.append([external_id, version, currency, format(amount, "f")])
        digest = hashlib.sha256(
            json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode()
        ).hexdigest()
        return cls(count=len(rows), amount_by_currency=by_currency, sha256=digest)


def compare_totals(
    source: ControlTotals, loaded: ControlTotals
) -> Literal["SUCCEEDED", "CONTROL_TOTAL_MISMATCH"]:
    """E-72: a difference in count or in any currency amount sets ``CONTROL_TOTAL_MISMATCH``
    (REQ-DAT-010; PRD BR-INT-03). The digests may differ when the loaded set omits a stale version
    on purpose, so they are recorded but do not decide."""
    if source.count != loaded.count:
        return "CONTROL_TOTAL_MISMATCH"
    if dict(source.amount_by_currency) != dict(loaded.amount_by_currency):
        return "CONTROL_TOTAL_MISMATCH"
    return "SUCCEEDED"


class InboundAdapter(Protocol):
    """05 §5.2: synchronous methods with explicit inputs and typed results."""

    @property
    def code(self) -> AdapterCode: ...

    def verify_webhook(
        self, headers: Mapping[str, str], body: bytes, secret: SecretStr
    ) -> WebhookNotice:
        """ADP-01: verify the signature and read the notification ids; never persist the secret."""
        ...

    def fetch_changes(self, checkpoint: Checkpoint, limit: int) -> ChangePage:
        """Poll the event feed from the replay id (the cursor advances over the complete consumed
        page), or sweep by last-modified time to exhaustion before the watermark advances
        (ADP-16, ADP-17 rev 1.12)."""
        ...

    def fetch_object(self, object_type: SourceObjectType, external_id: str) -> SourceObject:
        """The truth before acting (ADP-01); raises ``Transient`` / ``Permanent`` (ADP-12)."""
        ...

    def normalise(self, obj: SourceObject, mapping_version: str) -> NormalisedRecords:
        """Pure: the canonical records of one object under a mapping version."""
        ...

    def control_totals(self, objects: Sequence[SourceObject]) -> ControlTotals:
        """Count, amount by currency and digest of a fetched set (T-INT-02)."""
        ...


@dataclass(frozen=True, slots=True)
class InboundContext:
    """What a factory builds an adapter from: the connection's non-secret settings and the HTTP
    client a root supplies (the in-process mock in dev / test / e2e, ADP-20)."""

    tenant_code: str
    base_url: str
    config: Mapping[str, Any]
    client: Any  # an ``httpx.Client``-like object; typed loosely so ports stays driver-free


type InboundAdapterFactory = Callable[[InboundContext], InboundAdapter]

# One factory per adapter code, registered by composition roots and test fixtures (DG-LAY-03).
INBOUND_ADAPTERS: Final[dict[str, InboundAdapterFactory]] = {}


def register_inbound_adapter(code: AdapterCode, factory: InboundAdapterFactory) -> None:
    INBOUND_ADAPTERS[code] = factory


def inbound_adapter_for(code: str, context: InboundContext) -> InboundAdapter:
    """A new adapter for ``code``; ``LookupError`` while no root registered one, so a sync run
    fails closed instead of ingesting nothing silently."""
    factory = INBOUND_ADAPTERS.get(code)
    if factory is None:
        raise LookupError(f"no inbound adapter is registered for {code}")
    return factory(context)


# --- the chart of accounts a GL adapter serves ----------------------------------------------------
# 05 §5.2 ``GLAdapter.pull_chart_of_accounts``; 03 REQ-INT-008; BUILD_SPEC DIN-14.


class ChartAccount(Protocol):
    """One account of the ERP's chart as the adapter states it: the ERP's record id (the T-INT-04
    ``external_id``), the account number and name, and the T-REF-13 type and normal balance the
    adapter maps the ERP's account type to."""

    @property
    def external_id(self) -> str: ...
    @property
    def code(self) -> str: ...
    @property
    def name(self) -> str: ...
    @property
    def account_type(self) -> str: ...
    @property
    def normal_balance(self) -> str: ...
    @property
    def is_active(self) -> bool: ...


class ChartValue(Protocol):
    """One value of an ERP dimension (a department) as the adapter states it."""

    @property
    def external_id(self) -> str: ...
    @property
    def code(self) -> str: ...
    @property
    def name(self) -> str: ...
    @property
    def is_active(self) -> bool: ...


class ChartSource(Protocol):
    """What a ``COA_SYNC`` run reads from a GL adapter: the whole chart with the attributes
    ``pull_chart_of_accounts`` leaves out of ``AccountRef`` (type, normal balance, activity, the
    ERP record id), and the values of a dimension. ``journals.ports.Permanent`` when the ERP
    refuses, ``Transient`` when it stays unreachable after the ADP-12 schedule."""

    def pull_erp_accounts(self) -> Sequence[ChartAccount]: ...

    def pull_dimension_values(self, dimension_code: str) -> Sequence[ChartValue]: ...


type ChartSourceFactory = Callable[[InboundContext], ChartSource]

# The GL adapters that serve a chart of accounts (03 REQ-INT-008; BUILD_SPEC DIN-14): NetSuite.
# QuickBooks Online has no chart reading in 1.0 and CSV_GL has no chart. A connection of one of
# these runs ``COA_SYNC`` and is probed by one read of its chart (04 §16.14 rev 1.115).
CHART_ADAPTERS: Final = frozenset({"NETSUITE"})

# One factory per GL adapter code that serves a chart, registered by composition roots and test
# fixtures (DG-LAY-03); the context is the connection's, as for an inbound adapter.
CHART_SOURCES: Final[dict[str, ChartSourceFactory]] = {}


def register_chart_source(code: str, factory: ChartSourceFactory) -> None:
    CHART_SOURCES[code] = factory


def chart_source_for(code: str, context: InboundContext) -> ChartSource:
    """A new chart source for ``code``; ``LookupError`` while no root registered one, so a
    ``COA_SYNC`` fails closed instead of syncing nothing silently."""
    factory = CHART_SOURCES.get(code)
    if factory is None:
        raise LookupError(f"no chart-of-accounts source is registered for {code}")
    return factory(context)
