"""Stage 10 billing classification: documents, status updates and unconditional dates (ENC-11).

ENGINE_SPEC_B §10.2.1 and §10.2.2 (S10-R-01, S10-R-02, S10-R-04, S10-R-06 to S10-R-08). Each
``BILLING_RECORDED`` or ``CREDIT_MEMO_RECORDED`` event is one line of a billing document, and the
lines of one contract with the same document number and effective date form one document
(L2-4-Q-8). A ``BILLING_RECORDED`` with the ``invoice_number`` and ``line_external_id`` of an
earlier line of the same contract and ``is_cancellable`` not true is a status update: it adds no
billing, never changes the first line's attribution and, with the same amount, dates the line's
noncancellable right; a different amount, or a non-null ``obligation_key`` different from the first
line's non-null key, raises ``INVOICE_STATUS_UPDATE_MISMATCH`` (``ERROR``, S10-R-07; D-91). The
identity decision is the kernel helper ``erev_engine.billing_identity`` (D-91 "One identity rule,
one home"). Payload amounts exclude tax (S10-R-02; 04 §16.3 rev 1.2). The billing mode of a line is
``state.billing_mode_at``: the resolved POL-123 basis at the line's period of the contracting
entity, derived from POL-004 when the bundle holds no POL-123 value for that period (POLICIES §1;
S10-R-06 rev 1.162). In ``ERP`` mode a line counts on its effective date; in ``ENGINE`` mode a
cancellable line is memo-only until the earlier of a payment applied to its invoice and a
same-amount status update (S10-R-06), and the event that sets the date is the line's
``unconditional_source`` (D-89 L7-6-Q-9). A line recorded while the contract is
``NOT_A_CONTRACT`` in the book counts for billing only and enters no position (S10-R-04).
Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
from typing import Final

from erev_engine import billing_identity, money
from erev_engine.errors import EngineError
from erev_engine.stages.state import (
    BILLING_BASIS_POLICY,
    BILLING_MODE_ENGINE,
    BILLING_MODE_ERP,
    BILLING_POSTING_POLICY,
    AllocatedState,
    BookContext,
    ContractView,
    EventView,
    Finding,
    billing_mode_at,
)

__all__ = [
    "CREDIT_MEMO",
    "ENGINE",
    "ERP",
    "INVOICE",
    "MISMATCH",
    "Classified",
    "Document",
    "Line",
    "Receipt",
    "amount_of",
    "classify",
    "contract_status",
    "minor_unit",
    "mode_at",
]

INVOICE: Final = "INVOICE"
CREDIT_MEMO: Final = "CREDIT_MEMO"
ERP: Final = BILLING_MODE_ERP
ENGINE: Final = BILLING_MODE_ENGINE
MISMATCH: Final = "INVOICE_STATUS_UPDATE_MISMATCH"  # 04 table 15.4-B, rev 1.2 and 1.11
TAX_MISMATCH: Final = "INVOICE_STATUS_UPDATE_TAX_MISMATCH"  # 04 table 15.4-B rev 1.24; D-97 (27)
POSTING_POLICY: Final = BILLING_POSTING_POLICY  # POL-004
BASIS_POLICY: Final = BILLING_BASIS_POLICY  # POL-123
_STAGE: Final = 10


@dataclass(frozen=True, slots=True)
class Line:
    """One billing document line with its mode and unconditional date (§10.1 ``billing``)."""

    event: EventView
    kind: str  # INVOICE | CREDIT_MEMO
    number: str  # invoice_number | credit_memo_number
    line_external_id: str | None
    obligation_key: str | None
    amount: int  # minor units, excluding tax (S10-R-02)
    tax_amount: int  # minor units; never attributed
    is_cancellable: bool
    credited_invoice_number: str | None
    mode: str  # ERP | ENGINE
    unconditional_date: date | None  # None while memo-only (S10-R-06)
    in_position: bool  # False while the contract is NOT_A_CONTRACT in the book (S10-R-04)
    # D-89 L7-6-Q-9: the line's own event when the unconditional date is its effective date (and
    # for a credit memo), else the payment or status update that sets the date; None while
    # memo-only.
    unconditional_source: EventView | None


@dataclass(frozen=True, slots=True)
class Document:
    """The lines of one invoice or credit memo of a contract on one date (S10-R-01)."""

    contract_key: str
    kind: str
    number: str
    effective_date: date
    lines: tuple[Line, ...]  # ENG-06 order

    @property
    def key(self) -> str:
        """The natural key of the document: the event key of its first line."""
        return self.lines[0].event.event_key

    @property
    def credited_invoice_number(self) -> str | None:
        """The invoice a credit memo names, from its first line naming one."""
        return next(
            (line.credited_invoice_number for line in self.lines if line.credited_invoice_number),
            None,
        )


@dataclass(frozen=True, slots=True)
class Receipt:
    """A ``PAYMENT_RECEIVED`` on the contract subject key (REQ-BIL-012; S01-R-16)."""

    event: EventView
    contract_key: str
    entity: str  # the header's contracting entity
    receipt_reference: str
    amount: int  # minor units
    receipt_date: date
    applied_invoice_numbers: tuple[str, ...]
    form: str  # CASH | NONCASH (04 §16.3 rev 1.2)


@dataclass(frozen=True, slots=True)
class Classified:
    """Billing documents, receipts and findings of one book, ENG-06 order."""

    documents: tuple[Document, ...]
    receipts: tuple[Receipt, ...]
    findings: tuple[Finding, ...]


def _invariant(message: str, subject_key: str | None, **detail: str) -> EngineError:
    return EngineError("ENGINE_INVARIANT_VIOLATED", message, subject_key=subject_key, detail=detail)


def minor_unit(ctx: BookContext) -> int:
    """μ of the group's transaction currency (C-01)."""
    spec = ctx.currencies.get(ctx.txn_currency)
    if spec is None:
        raise _invariant(
            "the transaction currency is absent from the currency table",
            None,
            rule="CV-30",
            currency=ctx.txn_currency,
        )
    return spec.minor_unit


def _minor(ev: EventView, member: str, mu: int, *, required: bool = True) -> int:
    value = ev.payload.get(member)
    if value is None and not required:
        return 0
    if isinstance(value, bool) or not isinstance(value, str | int | Decimal | Fraction):
        raise _invariant(
            "a billing amount is malformed", ev.contract_key, rule="CV-45", event_key=ev.event_key
        )
    scale: int = 10**mu
    scaled = money.to_fraction(value) * scale
    if scaled.denominator != 1:
        raise _invariant(
            "a billing amount has more places than the currency",
            ev.contract_key,
            rule="CV-45",
            event_key=ev.event_key,
        )
    return scaled.numerator


def amount_of(ev: EventView, member: str, mu: int, *, required: bool = True) -> int:
    """A payload money member in minor units, with the CV-45 checks of the billing members."""
    return _minor(ev, member, mu, required=required)


def _text(ev: EventView, member: str, *, required: bool = True) -> str | None:
    value = ev.payload.get(member)
    if value is None or value == "":
        if required:
            raise _invariant(
                f"a billing event carries no {member}",
                ev.contract_key,
                rule="CV-45",
                event_key=ev.event_key,
            )
        return None
    if not isinstance(value, str):
        raise _invariant(
            f"a billing event {member} is malformed",
            ev.contract_key,
            rule="CV-45",
            event_key=ev.event_key,
        )
    return value


def _date(ev: EventView, member: str) -> date:
    value = ev.payload.get(member)
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise _invariant(
        f"a payment {member} is malformed", ev.contract_key, rule="CV-45", event_key=ev.event_key
    )


def contract_status(ctx: BookContext, contract: ContractView, d: date) -> str | None:
    """The E-17 status of ``contract`` in the book at ``d`` (stage 02 ``status_in_book``)."""
    history = contract.status_in_book.get(str(ctx.book_code))
    if history is None:
        raise _invariant(
            "the contract carries no status for the book",
            contract.header.external_id,
            rule="S02-R-03",
            book_code=str(ctx.book_code),
        )
    current: str | None = None
    for when, status in history:
        if when > d:
            break
        current = status
    return current


def _mode(ctx: BookContext, contract: ContractView, d: date) -> str:
    """ERP or ENGINE at ``d`` for the contracting entity: ``state.billing_mode_at`` (D-91)."""
    entity_code = contract.header.contracting_entity_code
    entity = ctx.entities.get(entity_code)
    if entity is None:
        raise _invariant(
            "the contracting entity has no calendar", contract.header.external_id, rule="CV-12"
        )
    return billing_mode_at(ctx.policies, entity, d)


def mode_at(ctx: BookContext, contract: ContractView, d: date) -> str:
    """The billing mode of ``contract`` at ``d``, ``ERP`` or ``ENGINE`` (POL-123, else POL-004)."""
    return _mode(ctx, contract, d)


@dataclass(frozen=True, slots=True)
class _Raw:
    event: EventView
    kind: str
    number: str
    line_external_id: str | None
    obligation_key: str | None
    amount: int
    tax_amount: int
    is_cancellable: bool
    credited_invoice_number: str | None


def classify(ctx: BookContext, st: AllocatedState) -> Classified:
    """Documents with modes and unconditional dates, receipts and S10-R-07 findings."""
    mu = minor_unit(ctx)
    contracts = {view.header.external_id: view for view in st.contracts}
    raw: list[_Raw] = []
    receipts: list[Receipt] = []
    findings: list[Finding] = []
    # S10-R-07 identity at contract scope over the whole ENG-06 stream (D-91): the kernel helper
    # decides line against status update; this stage owns the mismatch finding.
    identities = {
        item.event.event_key: item
        for item in billing_identity.iter_billing_lines(st.measure_events)
    }
    # The first valid status update of each identity, keyed by the identity's FIRST-SEEN line
    # (the ``line`` the kernel records the update with): it dates that line alone; a repeat
    # flagged cancellable is another line and stays memo-only until its own receipt (S10-R-07
    # "never changes the first line's attribution"; D-91 C606-01 (2); supervisor ruling, ENG-B4).
    # The map and the date are the kernel's (``first_updates`` / ``unconditional_source``; one
    # home for stages 04, 09 and 10; D-91 05g, lane ENG-C6); this stage owns the findings.
    noncancellable_on = billing_identity.first_updates(st.measure_events)
    for ev in st.measure_events:  # ENG-06 order
        contract = contracts.get(ev.contract_key)
        if ev.event_type not in ("BILLING_RECORDED", "CREDIT_MEMO_RECORDED", "PAYMENT_RECEIVED"):
            continue
        if contract is None:
            raise _invariant(
                "a billing event names a contract absent from the state",
                ev.contract_key,
                rule="CV-45",
                event_key=ev.event_key,
            )
        if ev.event_type == "PAYMENT_RECEIVED":
            applied = ev.payload.get("applied_invoice_numbers") or ()
            if not isinstance(applied, list | tuple) or not all(
                isinstance(n, str) for n in applied
            ):
                raise _invariant(
                    "a payment names malformed invoices",
                    ev.contract_key,
                    rule="CV-45",
                    event_key=ev.event_key,
                )
            form = ev.payload.get("form") or "CASH"
            receipts.append(
                Receipt(
                    event=ev,
                    contract_key=ev.contract_key,
                    entity=contract.header.contracting_entity_code,
                    receipt_reference=_text(ev, "receipt_reference") or "",
                    amount=_minor(ev, "amount", mu),
                    receipt_date=_date(ev, "receipt_date"),
                    applied_invoice_numbers=tuple(str(number) for number in applied),
                    form=str(form),
                )
            )
            continue
        obligation_key = _text(ev, "obligation_key", required=False)
        amount = _minor(ev, "amount", mu)
        if ev.event_type == "CREDIT_MEMO_RECORDED":
            raw.append(
                _Raw(
                    ev,
                    CREDIT_MEMO,
                    _text(ev, "credit_memo_number") or "",
                    None,
                    obligation_key,
                    amount,
                    0,
                    False,
                    _text(ev, "credited_invoice_number", required=False),
                )
            )
            continue
        number = _text(ev, "invoice_number") or ""
        line_id = _text(ev, "line_external_id") or ""
        identity = identities[ev.event_key]
        cancellable = billing_identity.is_cancellable(ev)
        if identity.is_status_update:  # S10-R-07: no billing; a same-amount update dates the line
            detail = {"invoice_number": number, "line_external_id": line_id, "rule": "S10-R-07"}
            if identity.amount_mismatch:
                findings.append(
                    Finding(MISMATCH, "ERROR", ev.contract_key, detail, _STAGE, ev.event_key)
                )
            if identity.obligation_mismatch:  # D-91 C606-01 (3): a re-attribution is refused
                findings.append(
                    Finding(
                        MISMATCH,
                        "ERROR",
                        ev.contract_key,
                        {**detail, "member": "obligation_key"},
                        _STAGE,
                        ev.event_key,
                    )
                )
            if identity.tax_mismatch:  # D-97 (27): the update's tax is dropped; no value effect
                findings.append(
                    Finding(
                        TAX_MISMATCH,
                        "WARNING",
                        ev.contract_key,
                        {**detail, "member": "tax_amount"},
                        _STAGE,
                        ev.event_key,
                    )
                )
            continue
        raw.append(
            _Raw(
                ev,
                INVOICE,
                number,
                line_id,
                obligation_key,
                amount,
                _minor(ev, "tax_amount", mu, required=False),
                cancellable,
                None,
            )
        )
    paid_on: dict[tuple[str, str], list[EventView]] = {}
    for receipt in receipts:
        for number in receipt.applied_invoice_numbers:
            paid_on.setdefault((receipt.contract_key, number), []).append(receipt.event)
    grouped: dict[tuple[str, str, str, date], list[Line]] = {}
    for item in raw:
        ev = item.event
        contract = contracts[ev.contract_key]
        mode = _mode(ctx, contract, ev.effective_date)
        unconditional: date | None = ev.effective_date
        source: EventView | None = ev
        if item.kind == INVOICE and mode == ENGINE and item.is_cancellable:
            # S10-R-06: the earliest of the applied receipts and the first valid update, floored
            # at the line's date; None while memo-only (the kernel's rule, D-91 05g).
            source = billing_identity.unconditional_source(
                ev,
                update=noncancellable_on.get(ev.event_key),
                receipts=paid_on.get((ev.contract_key, item.number), ()),
            )
            unconditional = None if source is None else source.effective_date
        line = Line(
            event=ev,
            kind=item.kind,
            number=item.number,
            line_external_id=item.line_external_id,
            obligation_key=item.obligation_key,
            amount=item.amount,
            tax_amount=item.tax_amount,
            is_cancellable=item.is_cancellable,
            credited_invoice_number=item.credited_invoice_number,
            mode=mode,
            unconditional_date=unconditional,
            in_position=contract_status(ctx, contract, ev.effective_date) != "NOT_A_CONTRACT",
            unconditional_source=source,
        )
        key4 = (ev.contract_key, item.kind, item.number, ev.effective_date)
        grouped.setdefault(key4, []).append(line)
    documents = tuple(
        Document(contract_key, kind, number, effective_date, tuple(lines))
        for (contract_key, kind, number, effective_date), lines in grouped.items()
    )
    return Classified(
        documents=tuple(sorted(documents, key=lambda doc: doc.lines[0].event.order_key)),
        receipts=tuple(receipts),
        findings=tuple(sorted(findings, key=lambda finding: finding.sort_key())),
    )
