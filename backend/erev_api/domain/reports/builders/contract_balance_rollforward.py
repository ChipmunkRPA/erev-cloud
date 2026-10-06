"""RPT-03 ``contract_balance_rollforward`` Contract balance rollforward (SCREENS_B §5.6.1 RPT-03;
ENGINE_SPEC_B §15.2.2 S15-R-03 to S15-R-07, EX-15-B; S10-R-08; POLICIES POL-004, POL-126; 03
REQ-RPT-006; CTL-030; BUILD_SPEC RPS-3; supervisor ruling R-72).

Per member contract and contracting entity over the range:

- ``OPENING`` and ``CLOSING`` are the presented balances at the end of the period before the range
  and at the end of the range (``tie_outs.balances_at``);
- the path of S15-R-02 walks the flows of the control role in date order. The flows are the
  ``CONTRACT_LIABILITY`` subledger lines of the range, except the JET-06 netting kinds, and the
  billing that posts no line (R-72 (a)): under ``billing.posting = ERP`` an invoice or a credit
  memo is ingested, never posted, so the role holds no line of it. The billing of a period is the
  delta of the engine's stored node ``billed_unconditional_cum`` of the contract and entity
  (S10-R-08; ``tie_outs.billed_through``) less the ``BILLING`` and ``CREDIT_MEMO`` lines already
  on the role; where that is not zero and the role holds no such line in the period, the period's
  billing documents enter the path at their effective dates — the kept ``BILLING_RECORDED`` lines
  of S10-R-07 (``erev_engine.billing_identity``) and the ``CREDIT_MEMO_RECORDED`` events, without
  voided events and voided contracts. Nothing is plugged: a difference between the documents and
  the delta stays unexplained. On one date a document enters before the lines ([J]: a line carries
  the amount of its computation and is dated by it; the document's date is the invoice's);
- a credit settles the unbilled receivable, then the contract asset, and the rest enters the
  liability as a new layer; a debit consumes the layers first in first out (POL-126
  ``FIFO_WITHIN_CONTRACT``) and the rest is an asset. Each flow is shown under the line of its
  family (SCREENS_B RPT-03 "kind → line"; R-72 (c)): ``BILLINGS`` = billing less credit memos;
  the two revenue lines = revenue relief, the contracting side of an intercompany pair included,
  net of negative revenue — relief of the opening layer is ``REVENUE_FROM_OPENING``, of later
  layers ``REVENUE_FROM_PERIOD_BILLINGS``, and relief beyond the layers is revenue in excess of
  billing, shown on the contract asset row ``REVENUE_FROM_PERIOD_BILLINGS``; every other movement
  of the role (a deposit transfer, noncash consideration, financing interest, the refund
  liability and its release, the receivable contra) is ``RECLASSIFICATIONS``;
- the difference between the path and the presented closing of the unbilled receivable and the
  contract asset is ``RECLASSIFICATIONS`` between the two captions; a difference in their sum, and
  any liability difference, is ``OTHER`` (unexplained; REQ-RPT-006);
- ``FX_REMEASUREMENT`` and ``BUSINESS_COMBINATIONS`` are 0 in the transaction view.

Section 1 "Rollforward" gives one row per line code (``<line>:<ISO>`` when several currencies);
section 2 "By contract" one row per contract for ``balance_role``. Tie-outs:
``TO_ROLLFORWARD_BALANCES`` passes when every ``OTHER`` cell is 0 (opening plus activity equals
closing, S15-R-07); ``TO_BALANCES_EQ_ROLLFORWARD`` compares the contract balances at the range end
with the ``CLOSING`` line; ``TO_ROLLFORWARD_EQ_GL`` is ``NOT_APPLICABLE`` without a trial balance.

R-RC-1 (L6-3-Q-21): the ``CONTRACT_BALANCE_ROLLFORWARD`` reconciliation with
``unexplained_other_amount`` moves with CLO-16.

The two ends (ENGINE_SPEC_B S15-R-20 rev 1.168; ruling R-72 (b); item
RPT-ROLLFWD-LOCKED-CLOSING-1): an end of a period that is locked at the run's cutoff is the
lock's — the opening where the period before the range is, the closing where its last period is
(``reports.locked_ends``) —, so a range of locked months and the period after it foot after a
contract is activated late: its lines are movements of the period they are posted in.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from erev_engine import billing_identity
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import contract_event, subledger_line
from erev_api.domain.reports import locked_ends, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.domain.reports.tie_outs import (
    ROLLFORWARD_BALANCES,
    ZERO,
    BalanceRow,
    EntityRef,
    PeriodRef,
    TracedBalances,
    add,
)
from erev_api.enums import ContractEventType
from erev_api.uow import UnitOfWork

CODE: Final = "contract_balance_rollforward"
LIABILITY: Final = "contract_liability"
ASSET: Final = "contract_asset"
UNBILLED: Final = "unbilled_receivable"
LINES: Final = (
    "OPENING",
    "BILLINGS",
    "REVENUE_FROM_OPENING",
    "REVENUE_FROM_PERIOD_BILLINGS",
    "RECLASSIFICATIONS",
    "FX_REMEASUREMENT",
    "BUSINESS_COMBINATIONS",
    "OTHER",
    "CLOSING",
)
LABELS: Final[Mapping[str, str]] = {
    "OPENING": "Opening balance",
    "BILLINGS": "Billings",
    "REVENUE_FROM_OPENING": "Revenue recognized from the opening balance",
    "REVENUE_FROM_PERIOD_BILLINGS": "Revenue recognized from billings of the period",
    "RECLASSIFICATIONS": "Reclassifications",
    "FX_REMEASUREMENT": "FX remeasurement",
    "BUSINESS_COMBINATIONS": "Business combinations",
    "OTHER": "Other",
    "CLOSING": "Closing balance",
}
BALANCE_ROLES: Final[Mapping[str, str]] = {
    "CONTRACT_LIABILITY": LIABILITY,
    "CONTRACT_ASSET": ASSET,
    "UNBILLED_RECEIVABLE": UNBILLED,
}
NETTING_KINDS: Final = frozenset({"NETTING_RECLASS", "NETTING_RECLASS_REVERSAL"})
REVENUE_KIND: Final = "REVENUE_RECOGNITION"
LIABILITY_ROLE: Final = "CONTRACT_LIABILITY"
# The families of the flows of the role and the line each is shown under (SCREENS_B RPT-03
# "kind → line"; supervisor ruling R-72 (c)). A subledger line's family follows its entry kind
# (04 E-29; ENGINE_SPEC_B Table 14-A): JET-03 invoices and credit memos are billing; revenue
# relief and its reversal — the contracting side of an intercompany pair included (S12-R-03) —
# are revenue; every other movement of the role is a reclassification.
BILLING: Final = "BILLING"
REVENUE: Final = "REVENUE"
RECLASSIFICATION: Final = "RECLASSIFICATION"
FAMILIES: Final[Mapping[str, str]] = {
    "BILLING": BILLING,
    "CREDIT_MEMO": BILLING,
    REVENUE_KIND: REVENUE,
    "INTERCOMPANY": REVENUE,
}
REVENUE_KINDS: Final = frozenset(kind for kind, family in FAMILIES.items() if family == REVENUE)
BILLING_KINDS: Final = frozenset(kind for kind, family in FAMILIES.items() if family == BILLING)
# The line of a family's movement, for the side that has no layer rule of its own.
FAMILY_LINES: Final[Mapping[str, str]] = {
    BILLING: "BILLINGS",
    REVENUE: "REVENUE_FROM_PERIOD_BILLINGS",
    RECLASSIFICATION: "RECLASSIFICATIONS",
}
# A contract's billing stream (04 E-03): the documents and what voids them.
DOCUMENT_TYPES: Final = (
    ContractEventType.BILLING_RECORDED.value,
    ContractEventType.CREDIT_MEMO_RECORDED.value,
)
STREAM_TYPES: Final = (
    *DOCUMENT_TYPES,
    ContractEventType.EVENT_VOIDED.value,
    ContractEventType.CONTRACT_VOIDED.value,
)
FUNCTIONAL_ONLY: Final = (
    "The functional and reporting views show contracts in the entity's functional currency only."
)
type Lines = dict[str, dict[str, Decimal]]


@dataclass(frozen=True, slots=True)
class Flow:
    """One flow of the control role: signed amount (debit positive), whether it is revenue
    relief, and its family (``BILLING``, ``REVENUE``, ``RECLASSIFICATION``). Without a family the
    flow is read by its sign: a credit is billing, a debit revenue relief or another decrease."""

    amount: Decimal
    is_revenue: bool
    kind: str = ""


def family_of(flow: Flow) -> str:
    """The family a flow is shown under (``FAMILY_LINES``)."""
    if flow.kind:
        return flow.kind
    if flow.amount < 0:
        return BILLING
    return REVENUE if flow.is_revenue else RECLASSIFICATION


def line_flow(entry_kind: str, amount: Decimal) -> Flow:
    """The flow of a ``CONTRACT_LIABILITY`` subledger line of ``entry_kind`` (04 E-29)."""
    family = FAMILIES.get(entry_kind, RECLASSIFICATION)
    return Flow(amount, family == REVENUE, family)


def document_flow(signed_billing: Decimal) -> Flow:
    """The flow of a billing document that posts no line: an invoice (positive) credits the role,
    a credit memo (negative) debits it."""
    return Flow(-signed_billing, False, BILLING)


@dataclass(frozen=True, slots=True)
class ContractRollforward:
    contract_id: UUID
    external_id: str
    customer_name: str | None
    entity_id: UUID
    entity_code: str
    currency: str
    lines: Mapping[str, Mapping[str, Decimal]]


def path(
    opening: Mapping[str, Decimal], flows: Sequence[Flow], closing: Mapping[str, Decimal]
) -> Lines:
    """The S15-R-02 lines of one contract and entity (module docstring; ENGINE_SPEC_B EX-15-B)."""
    lines: Lines = {line: dict.fromkeys(ROLLFORWARD_BALANCES, ZERO) for line in LINES}
    for balance in ROLLFORWARD_BALANCES:
        lines["OPENING"][balance] = opening.get(balance, ZERO)
        lines["CLOSING"][balance] = closing.get(balance, ZERO)
    layers: list[list[Any]] = []
    if opening.get(LIABILITY, ZERO) > 0:
        layers.append(["OPENING", opening[LIABILITY]])
    asset = {UNBILLED: opening.get(UNBILLED, ZERO), ASSET: opening.get(ASSET, ZERO)}
    for flow in flows:
        family = family_of(flow)
        label = FAMILY_LINES[family]
        if flow.amount < 0:
            left = -flow.amount
            for role in (UNBILLED, ASSET):
                take = min(asset[role], left)
                asset[role] -= take
                left -= take
                lines[label][role] -= take
            if left > 0:
                layers.append(["NEW", left])
                lines[label][LIABILITY] += left
            continue
        need = flow.amount
        for layer in layers:
            if need <= 0:
                break
            take = min(layer[1], need)
            if take <= 0:
                continue
            layer[1] -= take
            need -= take
            relieved = family == REVENUE and layer[0] == "OPENING"
            lines["REVENUE_FROM_OPENING" if relieved else label][LIABILITY] -= take
        if need > 0:
            asset[ASSET] += need
            lines[label][ASSET] += need
    computed = sum((Decimal(layer[1]) for layer in layers), ZERO)
    lines["OTHER"][LIABILITY] = closing.get(LIABILITY, ZERO) - computed
    unexplained = (closing.get(UNBILLED, ZERO) + closing.get(ASSET, ZERO)) - (
        asset[UNBILLED] + asset[ASSET]
    )
    lines["RECLASSIFICATIONS"][UNBILLED] += closing.get(UNBILLED, ZERO) - asset[UNBILLED]
    lines["RECLASSIFICATIONS"][ASSET] += closing.get(ASSET, ZERO) - asset[ASSET] - unexplained
    lines["OTHER"][ASSET] = unexplained
    return lines


def ranges(
    session: Session, params: ReportParams
) -> tuple[tuple[EntityRef, ...], dict[UUID, tuple[PeriodRef, ...]], dict[UUID, PeriodRef | None]]:
    """The run's entities, each entity's range and the period before its range."""
    found = tie_outs.entities(session, params.entity_ids, params=params)
    found_calendars = tie_outs.calendars(session, found, params=params)
    periods: dict[UUID, tuple[PeriodRef, ...]] = {}
    before: dict[UUID, PeriodRef | None] = {}
    for item in found:
        calendar = found_calendars[item.id]
        periods[item.id] = tie_outs.range_of(params, calendar, item)
        before[item.id] = calendar.before(periods[item.id][0]) if periods[item.id] else None
    return found, periods, before


def rollforwards(
    session: Session,
    *,
    entity_ids: Sequence[UUID],
    book_code: str,
    periods: Mapping[UUID, tuple[PeriodRef, ...]],
    before: Mapping[UUID, PeriodRef | None],
    known_at: datetime,
    cutoff: datetime,
    params: ReportParams,
    contract_id: UUID | None = None,
    documents: bool = True,
    locked: tie_outs.LockedEnds | None = None,
) -> tuple[ContractRollforward, ...]:
    """The rollforward of every member contract and entity with a balance at either end.
    ``documents`` False leaves the billing that posts no line out of the path: a caller that reads
    the ``CLOSING`` line alone (``contract_balances``, CTL-030) needs no flow of it. ``locked``
    are the build's locked period ends (S15-R-20 rev 1.168): both ends are read through them."""
    closing_at: dict[UUID, PeriodRef | None] = {
        entity_id: (items[-1] if items else None) for entity_id, items in periods.items()
    }
    traces: dict[UUID, TracedBalances] = {}
    opening_rows = tie_outs.balances_at(
        session,
        entity_ids=entity_ids,
        book_code=book_code,
        period_keys=before,
        cutoff=cutoff,
        params=params,
        contract_id=contract_id,
        traces=traces,
        locked_ends=locked,
    )
    closing_rows = tie_outs.balances_at(
        session,
        entity_ids=entity_ids,
        book_code=book_code,
        period_keys=closing_at,
        cutoff=cutoff,
        params=params,
        contract_id=contract_id,
        traces=traces,
        locked_ends=locked,
    )
    ends: dict[tuple[UUID, UUID], list[BalanceRow | None]] = {}
    for row in opening_rows:
        ends.setdefault((row.contract_id, row.entity_id), [None, None])[0] = row
    for row in closing_rows:
        ends.setdefault((row.contract_id, row.entity_id), [None, None])[1] = row
    posted = _lines(session, entity_ids, book_code, periods, known_at, contract_id, params=params)
    unposted: dict[tuple[UUID, UUID], list[Entry]] = {}
    if documents:
        described_rows = {
            key: closing if closing is not None else opening
            for key, (opening, closing) in ends.items()
        }
        unposted = _billing(
            session,
            rows={key: row for key, row in described_rows.items() if row is not None},
            posted=posted,
            periods=periods,
            before=before,
            traces=traces,
            cutoff=cutoff,
            params=params,
            locked=locked,
        )
    found: list[ContractRollforward] = []
    for (contract_key, entity_id), (opening, closing) in ends.items():
        described = closing if closing is not None else opening
        assert described is not None
        key = (contract_key, entity_id)
        entries = sorted(
            [*posted.get(key, ()), *unposted.get(key, ())], key=lambda entry: entry.order
        )
        lines = path(_values(opening), [entry.flow for entry in entries], _values(closing))
        found.append(
            ContractRollforward(
                contract_id=contract_key,
                external_id=described.external_id,
                customer_name=described.customer_name,
                entity_id=entity_id,
                entity_code=described.entity_code,
                currency=described.currency,
                lines=lines,
            )
        )
    return tuple(sorted(found, key=lambda item: (item.external_id, item.entity_code)))


def _values(row: BalanceRow | None) -> dict[str, Decimal]:
    if row is None:
        return dict.fromkeys(ROLLFORWARD_BALANCES, ZERO)
    return {balance: row.value(balance) for balance in ROLLFORWARD_BALANCES}


# On one date a billing document enters the path before the subledger lines (module docstring).
DOCUMENT_RANK: Final = 0
LINE_RANK: Final = 1


@dataclass(frozen=True, slots=True)
class Entry:
    """A flow in its place on the path: ``order`` = (effective date, rank, the source's own
    order); ``period_id`` and ``entry_kind`` are a subledger line's (None for a document)."""

    order: tuple[Any, ...]
    flow: Flow
    period_id: UUID | None = None
    entry_kind: str | None = None


def _lines(
    session: Session,
    entity_ids: Sequence[UUID],
    book_code: str,
    periods: Mapping[UUID, tuple[PeriodRef, ...]],
    known_at: datetime,
    contract_id: UUID | None,
    *,
    params: ReportParams,
) -> dict[tuple[UUID, UUID], list[Entry]]:
    """The subledger lines of the role over the range, per contract and entity. S15-R-24 /
    frps3c-2: the line ids consumed are recorded as ``members.subledger_line`` on a live build; a
    bound run reads exactly those ids WITHIN today's scope predicates (tenant / book / entity /
    period stay; the ids restrict, never replace) and refuses by name a bound id the read did not
    return (D4)."""
    period_ids = sorted({item.id for items in periods.values() for item in items}, key=str)
    if not entity_ids or not period_ids:
        # R1: an empty range is a CAPTURED empty membership (recorded), never an absent kind
        tie_outs.require_members(params, "subledger_line", ())
        tie_outs.record_members(params, "subledger_line", ())
        return {}
    statement = select(
        subledger_line.c.id,
        subledger_line.c.contract_id,
        subledger_line.c.entity_id,
        subledger_line.c.period_id,
        subledger_line.c.effective_date,
        subledger_line.c.period_end_date,
        subledger_line.c.recorded_at,
        subledger_line.c.entry_no,
        subledger_line.c.amount_txn,
        subledger_line.c.entry_kind,
    ).where(
        subledger_line.c.book_code == book_code,
        subledger_line.c.account_role == LIABILITY_ROLE,
        subledger_line.c.entity_id.in_(list(entity_ids)),
        subledger_line.c.period_id.in_(period_ids),
        subledger_line.c.recorded_at <= known_at,
        subledger_line.c.entry_kind.not_in(sorted(NETTING_KINDS)),
        *tie_outs.bound_member_where(params, "subledger_line", subledger_line.c.id),
    )
    if contract_id is not None:
        statement = statement.where(subledger_line.c.contract_id == contract_id)
    statement = statement.order_by(
        subledger_line.c.effective_date,
        subledger_line.c.period_end_date,
        subledger_line.c.recorded_at,
        subledger_line.c.entry_no,
        subledger_line.c.id,
    )
    found: dict[tuple[UUID, UUID], list[Entry]] = {}
    consumed: list[UUID] = []
    for row in session.execute(statement).mappings():
        if row["contract_id"] is None:
            continue
        consumed.append(UUID(str(row["id"])))
        key = (UUID(str(row["contract_id"])), UUID(str(row["entity_id"])))
        entry_kind = str(getattr(row["entry_kind"], "value", row["entry_kind"]))
        found.setdefault(key, []).append(
            Entry(
                order=(
                    row["effective_date"],
                    LINE_RANK,
                    row["period_end_date"],
                    row["recorded_at"],
                    int(row["entry_no"]),
                    str(row["id"]),
                ),
                flow=line_flow(entry_kind, Decimal(row["amount_txn"])),
                period_id=UUID(str(row["period_id"])),
                entry_kind=entry_kind,
            )
        )
    tie_outs.require_members(params, "subledger_line", consumed)
    tie_outs.record_members(params, "subledger_line", consumed)
    return found


@dataclass(frozen=True, slots=True)
class Document:
    """A billing document of a contract: the invoice line or credit memo the engine keeps
    (S10-R-07), its effective date, its place in the stream and its amount — positive for an
    invoice, negative for a credit memo — and the instant it was recorded at, which decides the
    period it enters the path in where an end is a lock's (``entered``; None: not stated, the
    document is taken as recorded before any lock)."""

    effective_date: date
    record_seq: int
    event_id: UUID
    amount: Decimal
    recorded_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class _StoredEvent:
    """A stored contract event read as ``billing_identity.BillingEvent`` (ENG-06 order)."""

    event_id: UUID
    contract_id: UUID
    event_type: str
    effective_date: date
    record_seq: int
    payload: Mapping[str, object]
    recorded_at: datetime | None = None

    @property
    def event_key(self) -> str:
        return str(self.event_id)

    @property
    def contract_key(self) -> str:
        return str(self.contract_id)

    @property
    def order_key(self) -> tuple[date, int, str]:
        return (self.effective_date, self.record_seq, str(self.event_id))


def kept_documents(events: Iterable[_StoredEvent], voided: Iterable[UUID]) -> list[Document]:
    """The billing documents of one contract's stream, in ENG-06 order: the kept
    ``BILLING_RECORDED`` lines of S10-R-07 (a status update of a line adds no billing) and the
    ``CREDIT_MEMO_RECORDED`` events, less the events ``voided`` names. Pure."""
    dropped = set(voided)
    stream = [event for event in events if event.event_id not in dropped]
    kept = {line.event_id for line in billing_identity.kept_lines(stream)}
    found: list[Document] = []
    for event in stream:
        if event.event_type == ContractEventType.BILLING_RECORDED.value:
            if event.event_id not in kept:
                continue
            sign = 1
        elif event.event_type == ContractEventType.CREDIT_MEMO_RECORDED.value:
            sign = -1
        else:
            continue
        found.append(
            Document(
                effective_date=event.effective_date,
                record_seq=event.record_seq,
                event_id=event.event_id,
                amount=sign * _payload_amount(event.payload),
                recorded_at=event.recorded_at,
            )
        )
    return found


def _payload_amount(payload: Mapping[str, object]) -> Decimal:
    money = payload.get("amount")
    if not isinstance(money, Mapping):
        raise ValueError("a billing event carries no amount")
    return Decimal(str(money["amount"]))


def unposted_periods(
    deltas: Sequence[tuple[PeriodRef, Decimal]], posted: Sequence[Entry]
) -> list[PeriodRef]:
    """The periods of the range whose billing posted no line, for one contract and entity (ruling
    R-72 (a)). ``deltas`` gives, per period, the delta of the engine's ``billed_unconditional_cum``;
    ``posted`` the role's subledger lines of the range. A period is named when that delta less the
    ``BILLING`` and ``CREDIT_MEMO`` lines of the period is not zero and the period holds no such
    line — with such lines the billing is on the role already. Pure."""
    found: list[PeriodRef] = []
    for item, delta in deltas:
        lines = [
            entry
            for entry in posted
            if entry.period_id == item.id and entry.entry_kind in BILLING_KINDS
        ]
        on_role = -sum((entry.flow.amount for entry in lines), ZERO)  # credit positive
        if not lines and delta - on_role != 0:
            found.append(item)
    return found


def document_entries(wanted: Sequence[PeriodRef], documents: Sequence[Document]) -> list[Entry]:
    """The documents dated in the ``wanted`` periods as flows of the path, each at its effective
    date and before the lines of that date. They enter as recorded: a difference from the engine's
    delta is never plugged, it stays unexplained. Pure."""
    return [
        Entry(
            order=(
                document.effective_date,
                DOCUMENT_RANK,
                document.record_seq,
                str(document.event_id),
            ),
            flow=document_flow(document.amount),
        )
        for document in documents
        if any(item.start <= document.effective_date <= item.end for item in wanted)
    ]


type End = tuple[PeriodRef | None, datetime | None]


def entered(documents: Sequence[Document], ends: Sequence[End]) -> list[list[Document]]:
    """Per period of a range, the documents that enter the path in it (ENGINE_SPEC_B S15-R-20 rev
    1.168; the supervisor's ruling of 2026-10-02). ``ends`` are the range's period ends in order,
    the end before the range first (None where the range starts at the first period), each with
    the cutoff of the lock it is read from (None where it is read from the versions).

    An end HOLDS a document dated on or before it — unless the end is a lock's and the document
    was recorded after that lock's cutoff: the lock's balances do not hold it. A document is a
    movement of the first period whose end holds it and whose opening end does not; so a
    document recorded after the lock of the period it is dated in enters in the first period
    whose end is not locked, or was locked after the document was recorded — as a line posted
    with an earlier origin does. Without a lock every document enters in the period it is dated
    in. One list per period of the range, in the documents' order. Pure."""

    def holds(end: End, document: Document) -> bool:
        period, frozen = end
        if period is None or document.effective_date > period.end:
            return False
        return frozen is None or document.recorded_at is None or document.recorded_at <= frozen

    found: list[list[Document]] = [[] for _ in ends[1:]]
    for document in documents:
        if holds(ends[0], document):
            continue  # in the opening already
        for index, end in enumerate(ends[1:]):
            if holds(end, document):
                found[index].append(document)
                break
    return found


def _billing(
    session: Session,
    *,
    rows: Mapping[tuple[UUID, UUID], BalanceRow],
    posted: Mapping[tuple[UUID, UUID], Sequence[Entry]],
    periods: Mapping[UUID, tuple[PeriodRef, ...]],
    before: Mapping[UUID, PeriodRef | None],
    traces: Mapping[UUID, TracedBalances],
    cutoff: datetime,
    params: ReportParams,
    locked: tie_outs.LockedEnds | None = None,
) -> dict[tuple[UUID, UUID], list[Entry]]:
    """The billing that posts no line, per contract and entity (``unposted_periods``,
    ``document_entries``). The engine's billed amount is read from the trace of the version the
    balances came from; the documents are the billing events of the contracts that need them,
    recorded by the cutoff. S15-R-24: the events consumed are recorded as
    ``members.contract_event`` on a live build and a bound run reads exactly those (an empty
    population is a captured empty membership).

    Where an end of an entity's range is a lock's (``locked``; S15-R-20 rev 1.168), a document
    enters in the period ``entered`` gives it, not in the period it is dated in: the engine's
    delta of a period is taken less the documents dated in it that enter elsewhere and plus
    those that enter in it from an earlier date, and a document keeps its own date in the order
    of the path, as a line posted with an earlier origin keeps its. For such an entity the
    streams read
    are those of the contracts with a period whose billing posted no line, as without a lock,
    and of the contracts with a billing event recorded after the earliest of the locks read —
    a document dated before the range can enter in it, and only such an event can move one."""
    wanted: dict[tuple[UUID, UUID], list[PeriodRef]] = {}
    moved: dict[tuple[UUID, UUID], tuple[list[End], list[tuple[PeriodRef, Decimal]]]] = {}
    frozen: dict[UUID, list[End]] = {}
    for entity_id, items in periods.items():
        if locked is None:
            continue
        ends: list[End] = []
        for item in (before.get(entity_id), *items):
            end = None if item is None else locked.at(entity_id, item)
            ends.append((item, None if end is None else end.frozen_at))
        if any(cutoff_of is not None for _, cutoff_of in ends):
            frozen[entity_id] = ends
    for key, row in rows.items():
        entity_id = key[1]
        traced = traces[row.version_id]
        earlier = before.get(entity_id)
        previous = tie_outs.billed_through(
            traced,
            external_id=row.external_id,
            entity_code=row.entity_code,
            period_key=None if earlier is None else earlier.key,
        )
        deltas: list[tuple[PeriodRef, Decimal]] = []
        for item in periods.get(entity_id, ()):
            current = tie_outs.billed_through(
                traced,
                external_id=row.external_id,
                entity_code=row.entity_code,
                period_key=item.key,
            )
            deltas.append((item, current - previous))
            previous = current
        if entity_id in frozen:
            moved[key] = (frozen[entity_id], deltas)
            continue
        found = unposted_periods(deltas, posted.get(key, ()))
        if found:
            wanted[key] = found
    # only the streams of the contracts with such a period are read — and, beside a lock's end,
    # of the contracts with a billing event recorded after the earliest lock read
    read = {key[0] for key in wanted}
    read |= {
        key[0]
        for key, (_, deltas) in moved.items()
        if unposted_periods(deltas, posted.get(key, ()))
    }
    others = sorted({key[0] for key in moved} - read, key=str)
    if others:
        earliest = min(at for ends in frozen.values() for _, at in ends if at is not None)
        read |= {
            UUID(str(found_id))
            for found_id in session.execute(
                select(contract_event.c.contract_id)
                .where(
                    contract_event.c.contract_id.in_(others),
                    contract_event.c.event_type.in_(STREAM_TYPES),
                    contract_event.c.recorded_at > earliest,
                    contract_event.c.recorded_at <= cutoff,
                )
                .distinct()
            ).scalars()
        }
    streams = _streams(session, sorted(read, key=str), cutoff=cutoff, params=params)
    entries = {key: document_entries(found, streams.get(key, ())) for key, found in wanted.items()}
    for key, (ends, deltas) in moved.items():
        if key[0] not in read:
            continue
        documents = streams.get(key, ())
        entering = entered(documents, ends)
        adjusted: list[tuple[PeriodRef, Decimal]] = []
        for (item, delta), here in zip(deltas, entering, strict=True):
            dated = sum(
                (d.amount for d in documents if item.start <= d.effective_date <= item.end), ZERO
            )
            adjusted.append((item, delta - dated + sum((d.amount for d in here), ZERO)))
        named = {item.id for item in unposted_periods(adjusted, posted.get(key, ()))}
        flows = [
            Entry(
                order=(
                    document.effective_date,
                    DOCUMENT_RANK,
                    document.record_seq,
                    str(document.event_id),
                ),
                flow=document_flow(document.amount),
            )
            for (item, _), here in zip(deltas, entering, strict=True)
            if item.id in named
            for document in here
        ]
        if flows:
            entries[key] = flows
    return entries


def _streams(
    session: Session, contract_ids: Sequence[UUID], *, cutoff: datetime, params: ReportParams
) -> dict[tuple[UUID, UUID], list[Document]]:
    """The billing documents of ``contract_ids``, per contract and contracting entity."""
    if not contract_ids:
        tie_outs.require_members(params, "contract_event", ())
        tie_outs.record_members(params, "contract_event", ())
        return {}
    rows = session.execute(
        select(
            contract_event.c.id,
            contract_event.c.contract_id,
            contract_event.c.contracting_entity_id,
            contract_event.c.event_type,
            contract_event.c.effective_date,
            contract_event.c.record_seq,
            contract_event.c.payload,
            contract_event.c.supersedes_event_id,
            contract_event.c.recorded_at,
        )
        .where(
            contract_event.c.contract_id.in_(list(contract_ids)),
            contract_event.c.event_type.in_(STREAM_TYPES),
            contract_event.c.recorded_at <= cutoff,
            *tie_outs.bound_member_where(params, "contract_event", contract_event.c.id),
        )
        .order_by(contract_event.c.effective_date, contract_event.c.record_seq, contract_event.c.id)
    ).mappings()
    consumed: list[UUID] = []
    events: dict[tuple[UUID, UUID], list[_StoredEvent]] = {}
    voided: dict[UUID, set[UUID]] = {}
    void_contracts: set[UUID] = set()
    for row in rows:
        consumed.append(UUID(str(row["id"])))
        contract_key = UUID(str(row["contract_id"]))
        event_type = str(getattr(row["event_type"], "value", row["event_type"]))
        if event_type == ContractEventType.EVENT_VOIDED.value:
            if row["supersedes_event_id"] is not None:
                voided.setdefault(contract_key, set()).add(UUID(str(row["supersedes_event_id"])))
            continue
        if event_type == ContractEventType.CONTRACT_VOIDED.value:
            void_contracts.add(contract_key)
            continue
        key = (contract_key, UUID(str(row["contracting_entity_id"])))
        events.setdefault(key, []).append(
            _StoredEvent(
                event_id=UUID(str(row["id"])),
                contract_id=contract_key,
                event_type=event_type,
                effective_date=row["effective_date"],
                record_seq=int(row["record_seq"]),
                payload=row["payload"],
                recorded_at=row["recorded_at"],
            )
        )
    tie_outs.require_members(params, "contract_event", consumed)
    tie_outs.record_members(params, "contract_event", consumed)
    return {
        key: kept_documents(found, voided.get(key[0], ()))
        for key, found in events.items()
        if key[0] not in void_contracts
    }


def _check_view(params: ReportParams, found: Sequence[EntityRef], items: Sequence[Any]) -> None:
    view = str(params.parameters.get("currency_view") or "transaction")
    functional = {entity.id: entity.functional_currency for entity in found}
    if view != "transaction" and any(item.currency != functional[item.entity_id] for item in items):
        raise tie_outs.invalid("currency_view", FUNCTIONAL_ONLY)


COLUMNS: Final = (
    Column("section", "Section", "integer"),
    # D-98 85 (CLO-7c): the stable line code is the row's identity in the frozen dataset; the label
    # is a display attribute.
    Column("line_code", "Line code", "code"),
    Column("line_label", "Line", "text"),
    Column(LIABILITY, "Contract liability", "money"),
    Column(ASSET, "Contract asset", "money"),
    Column(UNBILLED, "Unbilled receivable", "money"),
    Column("contract_external_id", "Contract", "code"),
    Column("customer_name", "Customer", "text"),
    Column("currency", "Currency", "code"),
    Column("opening", "Opening", "money"),
    Column("billings", "Billings", "money"),
    Column("revenue_from_opening", "Revenue from opening", "money"),
    Column("revenue_from_period_billings", "Revenue from period billings", "money"),
    Column("reclassifications", "Reclassifications", "money"),
    Column("fx_remeasurement", "FX remeasurement", "money"),
    Column("business_combinations", "Business combinations", "money"),
    Column("other", "Other", "money"),
    Column("closing", "Closing", "money"),
)


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    session = uow.session
    book_code = tie_outs.book_of(session, params)
    found, periods, before = ranges(session, params)
    contract_id = tie_outs.contract_named(session, params)
    cutoff = tie_outs.cutoff_for(session, params)
    ends = locked_ends.Reader(
        uow,
        params,
        book_code=book_code,
        cutoff=cutoff,
        entity_codes={item.id: item.code for item in found},
    )
    items = rollforwards(
        session,
        entity_ids=params.entity_ids,
        book_code=book_code,
        periods=periods,
        before=before,
        known_at=params.known_at,
        cutoff=cutoff,
        params=params,
        contract_id=contract_id,
        locked=ends,
    )
    _check_view(params, found, items)
    role = BALANCE_ROLES[str(params.parameters.get("balance_role") or "CONTRACT_LIABILITY")]
    totals: dict[str, Lines] = {}
    for item in items:
        into = totals.setdefault(
            item.currency, {line: dict.fromkeys(ROLLFORWARD_BALANCES, ZERO) for line in LINES}
        )
        for line in LINES:
            for balance in ROLLFORWARD_BALANCES:
                into[line][balance] += item.lines[line][balance]
    rows: list[dict[str, Any]] = []
    mixed = len(totals) > 1
    for currency, lines in sorted(totals.items()):
        for line in LINES:
            rows.append(
                {
                    "row_key": f"{line}:{currency}" if mixed else line,
                    "section": 1,
                    "line_code": line,
                    "line_label": LABELS[line],
                    # 04 T-CLS-05 dataset identity (D-98 85): a line row is identified by its
                    # line code and currency; the contract column is stated EMPTY, never left
                    # out — the lock freeze reads every key column by name (S15-R-18).
                    "contract_external_id": None,
                    "currency": currency,
                    **{
                        balance: tie_outs.money(lines[line][balance], currency)
                        for balance in ROLLFORWARD_BALANCES
                    },
                }
            )
    for item in items:
        rows.append(
            {
                "row_key": f"contract:{item.external_id}:{item.entity_code}",
                "section": 2,
                # a by-contract row is identified by its contract and currency: no line code
                "line_code": None,
                "contract_external_id": item.external_id,
                "customer_name": item.customer_name,
                "currency": item.currency,
                **{
                    line.lower(): tie_outs.money(item.lines[line][role], item.currency)
                    for line in LINES
                },
            }
        )
    control: dict[str, Any] = {}
    for balance in ROLLFORWARD_BALANCES:
        control[f"opening_{balance}"] = tie_outs.by_currency(
            {code: lines["OPENING"][balance] for code, lines in totals.items()}
        )
        control[f"closing_{balance}"] = tie_outs.by_currency(
            {code: lines["CLOSING"][balance] for code, lines in totals.items()}
        )
    closing_balances = tie_outs.balances_at(
        session,
        entity_ids=params.entity_ids,
        book_code=book_code,
        period_keys={key: (value[-1] if value else None) for key, value in periods.items()},
        cutoff=cutoff,
        params=params,
        contract_id=contract_id,
        locked_ends=ends,
    )
    return ReportData(
        columns=COLUMNS,
        rows=tuple(rows),
        control_totals=control,
        tie_out_results=(
            balances_tie(totals),
            balances_equal_tie(closing_balances, items),
            tie_outs.not_applicable(tie_outs.TO_ROLLFORWARD_EQ_GL),
        ),
    )


def balances_tie(totals: Mapping[str, Lines]) -> dict[str, Any]:
    """``TO_ROLLFORWARD_BALANCES``: opening plus explained activity equals closing, per currency
    over the three balances; any non-zero ``OTHER`` fails (S15-R-07)."""
    expected: dict[str, Decimal] = {}
    actual: dict[str, Decimal] = {}
    unexplained = False
    for currency, lines in totals.items():
        for balance in ROLLFORWARD_BALANCES:
            add(expected, currency, lines["CLOSING"][balance])
            explained = sum(
                (lines[line][balance] for line in LINES if line not in ("OTHER", "CLOSING")), ZERO
            )
            add(actual, currency, explained)
            unexplained = unexplained or lines["OTHER"][balance] != 0
    result = tie_outs.compared(tie_outs.TO_ROLLFORWARD_BALANCES, expected, actual)
    if unexplained:
        result["result"] = tie_outs.FAIL
    return result


def balances_equal_tie(
    closing: Sequence[BalanceRow], items: Sequence[ContractRollforward]
) -> dict[str, Any]:
    """``TO_BALANCES_EQ_ROLLFORWARD``: Σ contract liability, contract asset and unbilled receivable
    at the range end equals Σ the ``CLOSING`` line (CTL-030)."""
    expected: dict[str, Decimal] = {}
    for row in closing:
        add(expected, row.currency, sum((row.value(b) for b in ROLLFORWARD_BALANCES), ZERO))
    actual: dict[str, Decimal] = {}
    for item in items:
        add(
            actual,
            item.currency,
            sum((item.lines["CLOSING"][b] for b in ROLLFORWARD_BALANCES), ZERO),
        )
    return tie_outs.compared(tie_outs.TO_BALANCES_EQ_ROLLFORWARD, expected, actual)
