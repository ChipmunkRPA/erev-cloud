"""Avenmoor key contracts K-01 to K-11 (docs/02-PRD.md §2.7 key contracts, §2.8 WLD-X-01 to
WLD-X-22; BUILD_SPEC CTR-20, XR-09, BS3-D-09).

Every contract is built through the product's commands as the PRD §2.3 personas (WLD-R-02). First
``tomas`` generates the fiscal years the contract terms reach (``LATER_YEARS``), and ``maya``
proposes the principal conclusion of each templated product, which ``marcus`` approves
(``assess_products``). Then, in the order a Revenue Accountant works an order:

1. ``maya`` books the contract as ``POST /contracts`` does: the booking and its provisional
   computation, the combination suggestions (S02-R-14) and the user hold rules;
2. in a contract of two or more obligations, ``maya`` records the distinct review of each obligation
   whose template concludes ``distinct``, and ``priya`` reviews it (table 15.4-I
   ``DISTINCT_REVIEW``);
3. ``maya`` prepares a ``COLLECTIBILITY`` judgement record, ``priya`` reviews it, and ``maya``
   records a probable ``COLLECTIBILITY_ASSESSED`` for every book of the contracting entity (Step 1,
   ``STEP1_RECORD``);
4. ``maya`` submits the activation; ``priya`` approves it, and ``marcus`` decides the Controller
   step of a request from USD 1,000,000.00 (PRD §2.5), so ``CONTRACT_ACTIVATED`` is appended on
   ``maya``'s behalf;
5. ``maya`` records the seeded billing and measure events of PRD §2.7 in one request. Where it
   holds a delivery, progress, milestone, usage, cost or return event — a manual event (PRD
   BR-REC-01; BUILD_SPEC CTR-6) — the request waits whole as an event submission with its evidence
   document, ``priya`` approves it, and the events are appended on ``maya``'s behalf and
   computed; a request without one is appended at once.

All key contracts are booked before any activates: booking K-05 raises the combination suggestion
with K-11 (related-party group HOLLENBRAND, inception within 30 days), which is dismissed with the
PRD rationale before either contract's checklist is evaluated. [J] L5-4-Q-2: the dismissal needs
``contract.create`` (API-R-28; PRD ACT-04), which ``priya`` does not hold, so ``maya`` dismisses it.

Contracts whose activation the rc engine refuses stay drafts with Step 1 recorded (``activates``
False): K-03 and K-08 (L5-4-Q-9), K-04 (D-88 L7-6-Q-1 gate clause: the L8 release gate failed
the screens e2e with its GBP lines in AVM-US) and K-10 (L5-4-Q-12).

R-RC-1 and later capabilities (L5-4-Q-3 to L5-4-Q-6): K-01b is booked directly (modification
``CR-PELLWORTH-2026-07`` waits for the modification commands); estimate versions (K-03 EAC and
bonus, K-05 return rate, K-06 rebate), the K-03 and K-10 variable-consideration elements, the K-07
option, the K-08 minimum commitment, the K-02 and K-09 billing plans and commissions are not seeded.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import contract, customer, exception_item, fiscal_calendar, product
from erev_api.domain.contracts import activation, combination, commands, holds
from erev_api.domain.contracts import events as contract_events
from erev_api.domain.demo.avenmoor import ACCOUNTANT, CONTROLLER, SSP_APPROVER, TENANT_ADMIN
from erev_api.domain.imports.exceptions import OPEN_STATUSES
from erev_api.domain.platform import attachments
from erev_api.domain.policies import judgements
from erev_api.domain.reference import commands as reference_commands
from erev_api.enums import (
    ApprovalSubjectType,
    ContractEventType,
    Distinctness,
    FilePurpose,
    JudgementTopic,
    PrincipalAgent,
)
from erev_api.schemas.calendars import GenerateYearIn
from erev_api.schemas.combinations import SuggestionDismissIn
from erev_api.schemas.contracts import ContractCreateIn, DistinctReviewIn, SubmitActivationIn
from erev_api.schemas.events import EventAppendIn, EventAppendItemIn
from erev_api.schemas.judgements import JudgementCreateIn, JudgementSubmitIn
from erev_api.schemas.products import PrincipalAgentChangeIn

if TYPE_CHECKING:
    from erev_api.domain.demo.builders import BuildContext

PREPARER: Final = ACCOUNTANT  # maya: books, records Step 1 and events, submits activations
REVIEWER: Final = SSP_APPROVER  # priya, Revenue Reviewer: reviews records, approves activations
APPROVERS: Final = (REVIEWER, CONTROLLER)  # step 2 from USD 1,000,000.00 needs a Controller
# The route guards of the commands (04 §15.3 API-R-28, API-R-30, API-R-33).
CREATE: Final = "contract.create"
EVENT_RECORD: Final = "event.record"
JUDGEMENT_CREATE: Final = "judgement.create"
SUBMIT_COMMENT: Final = "Ready for review."
COLLECTIBILITY_CONCLUSION: Final = "Collection of the consideration is probable."
COLLECTIBILITY_RATIONALE: Final = "Credit review of the customer and its payment history."
# 04 T-CON-19 "Step 1 criteria" (supervisor rulings R-113 (f), R-115 (f)): a record that serves
# Step 1 answers the five criteria of 606-10-25-1 when it is sent for review. The seeded
# contracts are contracts: every criterion is met.
STEP1_CRITERIA_MET: Final = dict.fromkeys(("a", "b", "c", "d", "e"), "YES")
DISTINCT_RATIONALE: Final = (
    "The customer can benefit from the promise on its own, and the contract does not integrate it "
    "with the other promises."
)
SUGGESTED: Final = "COMBINATION_SUGGESTED"
DISMISS_RATIONALE: Final = "Separate purchasing entities; negotiated independently."  # WLD-K-11
MASTERDATA_MAINTAIN: Final = "masterdata.maintain"
# The evidence document of a request that holds manual events (04 §16.3 ``evidence_file_ids``;
# 03 REQ-DAT-014): the manual events of the request, one row each.
EVIDENCE_MEDIA_TYPE: Final = "text/csv"
EVIDENCE_COLUMNS: Final = ("contract", "event_type", "effective_date", "obligation_key", "measure")
# The payload member that states what a manual event measures, by event type.
EVIDENCE_MEASURES: Final[Mapping[ContractEventType, str]] = {
    ContractEventType.DELIVERY_RECORDED: "quantity",
    ContractEventType.RETURN_RECORDED: "quantity",
    ContractEventType.PROGRESS_RECORDED: "cumulative_progress_ratio",
    ContractEventType.MILESTONE_ACHIEVED: "cumulative_weight",
    # 04 rev 1.238 (item EVT-USAGE-MANUAL-1): a usage report is a manual event. No contract of the
    # seed records one as ``maya`` — K-08 stays a draft — so the seeded state is unchanged.
    ContractEventType.USAGE_REPORTED: "quantity",
    ContractEventType.COST_INCURRED: "amount",
}
PRINCIPAL_RATIONALE: Final = (
    "Avenmoor controls each good, service and licence before it transfers to the customer, is "
    "primarily responsible for fulfilment and sets the price (606-10-55-37A, 55-39)."
)


@dataclass(frozen=True, slots=True)
class LineSpec:
    """One booked line (API-S-ContractCreate ``lines[]``)."""

    key: str
    product: str
    quantity: str
    price: str
    start: date | None = None
    end: date | None = None
    performing_entity: str | None = None

    def body(self, currency: str) -> dict[str, Any]:
        line: dict[str, Any] = {
            "obligation_key": self.key,
            "product_code": self.product,
            "quantity": self.quantity,
            "total_price": money(self.price, currency),
        }
        if self.start is not None:
            line["start_date"] = self.start.isoformat()
        if self.end is not None:
            line["end_date"] = self.end.isoformat()
        if self.performing_entity is not None:
            line["performing_entity_code"] = self.performing_entity
        return line


@dataclass(frozen=True, slots=True)
class EventSpec:
    """One API-S-EventAppend item."""

    event_type: ContractEventType
    effective: date
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ContractSpec:
    external_id: str
    customer_code: str
    entity: str
    currency: str
    inception: date
    lines: tuple[LineSpec, ...]
    reviews: tuple[str, ...] = ()  # obligation keys that need a distinct review
    events: tuple[EventSpec, ...] = ()
    customer_name: str | None = None  # a customer the booking creates when it does not exist
    activates: bool = True  # False: booked with Step 1 recorded, not submitted

    def body(self, customer_id: UUID | None) -> ContractCreateIn:
        members: dict[str, Any] = {
            "external_id": self.external_id,
            "contracting_entity_code": self.entity,
            "transaction_currency": self.currency,
            "inception_date": self.inception.isoformat(),
            "document_ref": self.external_id,  # IMP-100: the order reference
            # 04 §16.3 rev 1.287 (item ACT-FLAGS-1): the sample contracts hold no acceptance
            # clause and no side letter, and say so.
            "acceptance_clause": False,
            "side_letter": False,
            "lines": [line.body(self.currency) for line in self.lines],
        }
        if customer_id is None:
            members["customer"] = {"code": self.customer_code, "name": self.customer_name}
        else:
            members["customer_id"] = str(customer_id)
        return ContractCreateIn.model_validate(members)


def money(amount: str, currency: str) -> dict[str, str]:
    return {"amount": amount, "currency": currency}


def billing(
    invoice: str, amount: str, currency: str, issued: date, key: str | None = None
) -> EventSpec:
    """``BILLING_RECORDED`` of one invoice line, for the contract or one obligation."""
    payload: dict[str, Any] = {
        "invoice_number": invoice,
        "line_external_id": f"{invoice}-1",
        "amount": money(amount, currency),
        "issue_date": issued.isoformat(),
    }
    if key is not None:
        payload["obligation_key"] = key
    return EventSpec(ContractEventType.BILLING_RECORDED, issued, payload)


def progress(key: str, ratio: str, effective: date) -> EventSpec:
    payload = {
        "obligation_key": key,
        "cumulative_progress_ratio": ratio,
        "measure": "OUTPUT_PERCENT",
    }
    return EventSpec(ContractEventType.PROGRESS_RECORDED, effective, payload)


def delivery(key: str, quantity: str, effective: date) -> EventSpec:
    payload = {"obligation_key": key, "quantity": quantity, "trigger": "DELIVERY"}
    return EventSpec(ContractEventType.DELIVERY_RECORDED, effective, payload)


def cost(key: str, amount: str, currency: str, effective: date) -> EventSpec:
    payload = {
        "purpose": "PROGRESS_INPUT",
        "obligation_key": key,
        "amount": money(amount, currency),
    }
    return EventSpec(ContractEventType.COST_INCURRED, effective, payload)


def usage(key: str, start: date, end: date, calls: str, rated: str, currency: str) -> EventSpec:
    payload = {
        "obligation_key": key,
        "usage_period_start": start.isoformat(),
        "usage_period_end": end.isoformat(),
        "metric": "api_calls",
        "quantity": calls,
        "rated_amount": money(rated, currency),
    }
    return EventSpec(ContractEventType.USAGE_REPORTED, end, payload)


D = date
K01: Final = "SF-ORD-10001"
K05: Final = "NS-SO-DE-5001"
K11: Final = "NS-SO-DE-5004"

# PRD §2.7 key contracts in WLD order. [J] L4-2-Q-8: AVM-SEAT-MO counts seat-months, the unit of
# its SSP entry. [J] Invoices name the obligation they bill when one line of the PRD matches it.
KEY_CONTRACTS: Final[tuple[ContractSpec, ...]] = (
    ContractSpec(
        K01,
        "WLD-C-01",
        "AVM-US",
        "USD",
        D(2026, 1, 1),
        (
            LineSpec("O1", "AVM-PLAT-ENT", "1", "120000.00", D(2026, 1, 1), D(2026, 12, 31)),
            LineSpec("O2", "AVM-IMPL-STD", "1", "15000.00"),
        ),
        reviews=("O2",),
        events=(
            billing("INV-US-1001", "120000.00", "USD", D(2026, 1, 1), "O1"),
            progress("O2", "0.40", D(2026, 1, 31)),
            progress("O2", "1", D(2026, 2, 27)),
            billing("INV-US-1044", "15000.00", "USD", D(2026, 2, 27), "O2"),
        ),
    ),
    ContractSpec(
        "SF-ORD-10388",
        "WLD-C-01",
        "AVM-US",
        "USD",
        D(2026, 7, 1),
        (LineSpec("O1", "AVM-SEAT-MO", "300", "30000.00", D(2026, 7, 1), D(2026, 12, 31)),),
        events=(billing("INV-US-1390", "30000.00", "USD", D(2026, 7, 1), "O1"),),
    ),
    ContractSpec(
        "SF-ORD-10002",
        "WLD-C-02",
        "AVM-US",
        "USD",
        D(2026, 1, 1),
        (LineSpec("O1", "AVM-SEAT-MO", "2400", "240000.00", D(2026, 1, 1), D(2027, 12, 31)),),
        events=(billing("INV-US-1002", "120000.00", "USD", D(2026, 1, 1), "O1"),),
    ),
    ContractSpec(
        "PRJ-CB-2026-01",
        "WLD-C-03",
        "AVM-US",
        "USD",
        D(2026, 2, 1),
        (LineSpec("O1", "AVM-ENG-BUILD", "1", "1000000.00"),),
        # [J] L5-4-Q-9: the activation dry run answers ENGINE_INVARIANT_VIOLATED "the measure of
        # progress is not built" for COST_TO_COST (ENC-5 deferred), so K-03 stays a draft.
        activates=False,
    ),
    ContractSpec(
        "SF-ORD-UK-2001",
        "WLD-C-04",
        "AVM-UK",
        "GBP",
        D(2026, 4, 1),
        (
            LineSpec("O1", "AVM-PLAT-UK", "1", "60000.00", D(2026, 4, 1), D(2027, 3, 31), "AVM-US"),
            LineSpec("O2", "AVM-IMPL-UK", "1", "8000.00", performing_entity="AVM-UK"),
        ),
        reviews=("O2",),
        # [J] D-88 L7-6-Q-1: BookOutput carries PostingState.line_rates and the platform stamps
        # each AVM-US performing line (GBP to USD) with its latest pinned rate (L3-1-Q-30), but
        # the ruling's gate clause keeps K-04 a draft for the rc: the L8 release gate failed the
        # screens e2e with its GBP lines in AVM-US (SF-06:run-lines, SF-06:entries).
        activates=False,
        events=(
            billing("INV-UK-0501", "68000.00", "GBP", D(2026, 4, 1)),
            progress("O2", "0.50", D(2026, 4, 30)),
            progress("O2", "1", D(2026, 5, 31)),
        ),
    ),
    ContractSpec(
        K05,
        "WLD-C-05",
        "AVM-DE",
        "EUR",
        D(2026, 9, 3),
        (LineSpec("O1", "AVM-KIT", "100", "10000.00"),),
        events=(
            delivery("O1", "100", D(2026, 9, 3)),
            billing("INV-DE-4460", "10000.00", "EUR", D(2026, 9, 3), "O1"),
        ),
    ),
    ContractSpec(
        "NS-SO-DE-5002",
        "WLD-C-06",
        "AVM-DE",
        "EUR",
        D(2026, 7, 1),
        # [J] L5-4-Q-4: the framework states a unit price only; the booking names the 575 units of
        # the two shipments at 100.00.
        (LineSpec("O1", "AVM-PART", "575", "57500.00", D(2026, 7, 1), D(2027, 6, 30)),),
        events=(
            delivery("O1", "75", D(2026, 7, 15)),
            billing("INV-DE-4201", "7500.00", "EUR", D(2026, 7, 15), "O1"),
        ),
    ),
    ContractSpec(
        "NS-SO-DE-5003",
        "WLD-C-07",
        "AVM-DE",
        "EUR",
        D(2026, 8, 14),
        (LineSpec("O1", "AVM-FLEET", "1", "100000.00"),),
        events=(delivery("O1", "1", D(2026, 8, 14)),),
    ),
    ContractSpec(
        "SF-ORD-10003",
        "WLD-C-08",
        "AVM-US",
        "USD",
        D(2026, 1, 1),
        # [J] L5-4-Q-5: the usage contract books the four quarterly minimums (800,000 calls at
        # 0.10) as its stated consideration.
        (LineSpec("O1", "AVM-API-CALL", "800000", "80000.00", D(2026, 1, 1), D(2026, 12, 31)),),
        # [J] L5-4-Q-9: the activation dry run answers ENGINE_INVARIANT_VIOLATED "the measure of
        # progress is not built" for USAGE (ENC-5 deferred), so K-08 stays a draft.
        activates=False,
        events=(
            usage("O1", D(2026, 1, 1), D(2026, 3, 31), "250000", "25000.00", "USD"),
            billing("INV-US-1201", "25000.00", "USD", D(2026, 4, 5), "O1"),
            usage("O1", D(2026, 4, 1), D(2026, 6, 30), "220000", "22000.00", "USD"),
            billing("INV-US-1202", "22000.00", "USD", D(2026, 7, 5), "O1"),
            usage("O1", D(2026, 7, 1), D(2026, 7, 31), "60000", "6000.00", "USD"),
            usage("O1", D(2026, 8, 1), D(2026, 8, 31), "50000", "5000.00", "USD"),
        ),
    ),
    ContractSpec(
        "SF-ORD-10417",
        "WLD-C-09",
        "AVM-US",
        "USD",
        D(2026, 9, 1),
        (LineSpec("O1", "AVM-SEAT-MO", "1080", "108000.00", D(2026, 9, 1), D(2029, 8, 31)),),
        events=(billing("INV-US-3101", "36000.00", "USD", D(2026, 9, 1), "O1"),),
    ),
    ContractSpec(
        "JP-LIC-0001",
        "WLD-C-10",
        "AVM-JP",
        "JPY",
        D(2026, 4, 1),
        (LineSpec("O1", "AVM-LIB-LIC", "1", "50000000", D(2026, 4, 1), D(2029, 3, 31)),),
        # [J] L5-4-Q-12: the activation dry run answers ENGINE_INVARIANT_VIOLATED CV-13 "the period
        # carries no state for the book" (stage 14 over FY2026-P01, Apr 2025): the bundle carries
        # the April calendar's periods before AVM-JP's first period, which have no state. K-10
        # stays a draft.
        activates=False,
        events=(billing("INV-JP-0001", "50000000", "JPY", D(2026, 4, 1), "O1"),),
    ),
    ContractSpec(
        K11,
        "WLD-C-11",
        "AVM-DE",
        "EUR",
        D(2026, 9, 1),
        (
            LineSpec("O1", "AVM-GW", "200", "90000.00"),
            LineSpec("O2", "AVM-SUP-12", "1", "18000.00", D(2026, 9, 15), D(2027, 9, 14)),
        ),
        reviews=("O1",),
    ),
)


# --- commands as the personas --------------------------------------------------------------------


def customer_ids(ctx: BuildContext) -> dict[str, UUID]:
    with ctx.read() as session:
        rows = session.execute(select(customer.c.code, customer.c.id)).tuples()
        return {str(code): UUID(str(value)) for code, value in rows}


def head(ctx: BuildContext, contract_id: UUID) -> int:
    """The contract's head stream version, as the persona reads the ETag."""
    with ctx.read() as session:
        value = session.execute(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        ).scalar_one()
    return int(value)


def book(ctx: BuildContext, spec: ContractSpec, customer_id: UUID | None) -> UUID:
    """``POST /contracts`` as ``maya`` (REQ-CON-001; S02-R-14; REQ-POL-010)."""
    body = spec.body(customer_id)
    with ctx.command(PREPARER, CREATE) as uow:
        created = commands.create_contract(uow, body=body)
        combination.raise_suggestions(uow, created.id)
        holds.apply_rule_holds(uow, created.id)
    return created.id


def review_distinct(ctx: BuildContext, contract_id: UUID, obligation_key: str) -> None:
    """``POST /contracts/{id}/obligations/{key}/distinct-review`` as ``maya``; ``priya`` reviews."""
    with ctx.command(PREPARER, JUDGEMENT_CREATE) as uow:
        reviewed = activation.record_distinct_review(
            uow,
            contract_id=contract_id,
            obligation_key=obligation_key,
            body=DistinctReviewIn(distinctness=Distinctness.DISTINCT, rationale=DISTINCT_RATIONALE),
        )
    ctx.approve(ApprovalSubjectType.JUDGEMENT_RECORD, reviewed.judgement_record_id, [REVIEWER])


def manual_events(specs: Sequence[EventSpec]) -> list[EventSpec]:
    """The events of a request that a signed-in person's entry routes through ``MANUAL_EVENT``."""
    return [spec for spec in specs if spec.event_type in contract_events.MANUAL_TYPES]


def evidence_document(external_id: str, specs: Sequence[EventSpec]) -> bytes:
    """The evidence of the manual events of a request as CSV (UTF-8, LF line ends), one row per
    event; the same bytes on every call."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(EVIDENCE_COLUMNS)
    for spec in manual_events(specs):
        measure = spec.payload.get(EVIDENCE_MEASURES[spec.event_type])
        if isinstance(measure, Mapping):
            measure = f"{measure['amount']} {measure['currency']}"
        writer.writerow(
            (
                external_id,
                spec.event_type.value,
                spec.effective.isoformat(),
                spec.payload.get("obligation_key") or "",
                measure,
            )
        )
    return buffer.getvalue().encode("utf-8")


def evidence_filename(external_id: str) -> str:
    return f"{external_id.lower()}-event-evidence.csv"


def record_events(ctx: BuildContext, contract_id: UUID, specs: Sequence[EventSpec]) -> None:
    """``POST /contracts/{id}/events`` as ``maya`` with ``If-Match`` of the current head. A
    request that holds a manual event carries its evidence document and waits as an event
    submission, which ``priya`` approves (BUILD_SPEC CTR-6; 04 §16.3 "Manual events")."""
    if not specs:
        return
    evidence: list[UUID] = []
    if manual_events(specs):
        with ctx.read() as session:
            external_id = str(
                session.execute(
                    select(contract.c.external_id).where(contract.c.id == contract_id)
                ).scalar_one()
            )
        with ctx.command(PREPARER) as uow:
            stored = attachments.upload_file(
                uow,
                purpose=FilePurpose.ATTACHMENT.value,
                stream=io.BytesIO(evidence_document(external_id, specs)),
                original_filename=evidence_filename(external_id),
                media_type=EVIDENCE_MEDIA_TYPE,
            )
        evidence.append(UUID(str(stored["id"])))
    body = EventAppendIn(
        events=[
            EventAppendItemIn(
                event_type=spec.event_type,
                effective_date=spec.effective,
                payload=dict(spec.payload),
            )
            for spec in specs
        ],
        evidence_file_ids=evidence,
    )
    current = head(ctx, contract_id)
    with ctx.command(PREPARER, EVENT_RECORD) as uow:
        recorded = contract_events.record_events(
            uow, contract_id=contract_id, expected_stream_version=current, body=body
        )
    if recorded.submission is not None:
        ctx.approve(
            ApprovalSubjectType.MANUAL_EVENT, recorded.submission.event_submission_id, [REVIEWER]
        )


def record_step1(ctx: BuildContext, contract_id: UUID, effective: date) -> None:
    """Step 1: a reviewed ``COLLECTIBILITY`` record and a probable assessment per enabled book."""
    with ctx.command(PREPARER, JUDGEMENT_CREATE) as uow:
        record = judgements.create_judgement(
            uow,
            body=JudgementCreateIn(
                topic=JudgementTopic.COLLECTIBILITY,
                subject_type="contract",
                subject_id=contract_id,
                conclusion=COLLECTIBILITY_CONCLUSION,
                rationale=COLLECTIBILITY_RATIONALE,
                questionnaire={"criteria": dict(STEP1_CRITERIA_MET)},
            ),
        )
    with ctx.command(PREPARER, JUDGEMENT_CREATE) as uow:
        judgements.submit_judgement(
            uow, judgement_id=record.id, body=JudgementSubmitIn(comment=SUBMIT_COMMENT)
        )
    ctx.approve(ApprovalSubjectType.JUDGEMENT_RECORD, record.id, [REVIEWER])
    with ctx.read() as session:
        entity_id = session.execute(
            select(contract.c.contracting_entity_id).where(contract.c.id == contract_id)
        ).scalar_one()
        books = activation.enabled_books(session, UUID(str(entity_id)))
    assessed = [
        EventSpec(
            ContractEventType.COLLECTIBILITY_ASSESSED,
            effective,
            {"book": code, "is_probable": True, "judgement_record_id": str(record.id)},
        )
        for code in books
    ]
    record_events(ctx, contract_id, assessed)


def submit(ctx: BuildContext, contract_id: UUID) -> None:
    """``POST /contracts/{id}/submit-activation`` as ``maya``."""
    current = head(ctx, contract_id)
    with ctx.command(PREPARER, CREATE) as uow:
        activation.submit_activation(
            uow,
            contract_id=contract_id,
            expected_stream_version=current,
            body=SubmitActivationIn(comment=SUBMIT_COMMENT),
        )


def activate(ctx: BuildContext, contract_id: UUID) -> None:
    """Submit the activation and approve every routed step (``priya``, then ``marcus``)."""
    submit(ctx, contract_id)
    ctx.approve(ApprovalSubjectType.CONTRACT_ACTIVATION, contract_id, APPROVERS)


def dismiss_suggestions(ctx: BuildContext, contract_id: UUID, rationale: str) -> None:
    """``POST /combination-suggestions/{id}/dismiss`` as ``maya`` for each open suggestion naming
    the contract (L5-4-Q-2)."""
    with ctx.read() as session:
        items = (
            session.execute(
                select(exception_item.c.id)
                .where(
                    exception_item.c.code == SUGGESTED,
                    exception_item.c.status.in_(OPEN_STATUSES),
                    exception_item.c.source_payload["contract_ids"].contains([str(contract_id)]),
                )
                .order_by(exception_item.c.exception_no)
            )
            .scalars()
            .all()
        )
    for item_id in items:
        with ctx.command(PREPARER, CREATE) as uow:
            combination.dismiss_suggestion(
                uow, item_id=UUID(str(item_id)), body=SuggestionDismissIn(rationale=rationale)
            )


# [J] L5-4-Q-11: the engine needs a period for every date of an obligation's term, and RFD-16 builds
# the January calendar to FY2027 and the April calendar to FY2028. The contract terms reach 31 Aug
# 2029 (K-09) and the background licences 31 Aug 2029 (AVM-JP FY2030), so ``tomas`` generates the
# later fiscal years; their periods stay ``future``.
LATER_YEARS: Final = (("AVM-JAN", (2028, 2029)), ("AVM-APR", (2029, 2030)))


def extend_calendars(ctx: BuildContext) -> None:
    """``POST /calendars/{id}/generate-year`` as ``tomas`` for ``LATER_YEARS``."""
    with ctx.read() as session:
        rows = session.execute(select(fiscal_calendar.c.code, fiscal_calendar.c.id)).tuples()
        calendars = {str(code): UUID(str(value)) for code, value in rows}
    for code, years in LATER_YEARS:
        for year in years:
            with ctx.command(TENANT_ADMIN) as uow:
                reference_commands.generate_year(
                    uow, calendar_id=calendars[code], body=GenerateYearIn(fiscal_year=year)
                )


def assess_products(ctx: BuildContext) -> None:
    """``POST /products/{id}/propose-principal-agent-change`` ``PRINCIPAL`` as ``maya`` for each
    product with a revenue policy template that is not yet assessed, approved by ``marcus``
    (``PRINCIPAL_AGENT_CHANGE``, PRD §2.5).

    [J] L5-4-Q-8: S03-R-09 refuses an activation while a line's product is ``NOT_ASSESSED`` (the
    T-REF-20 default kept by D-83), and PRD §2.6 states no conclusion; every Avenmoor good, service
    and licence is sold as principal, as the answer keys assume.
    """
    with ctx.read() as session:
        pending = session.execute(
            select(product.c.id)
            .where(
                product.c.default_pob_template_id.is_not(None),
                product.c.principal_agent == PrincipalAgent.NOT_ASSESSED.value,
            )
            .order_by(product.c.code)
        ).scalars()
        product_ids = [UUID(str(value)) for value in pending]
    for product_id in product_ids:
        with ctx.command(PREPARER, MASTERDATA_MAINTAIN) as uow:
            reference_commands.propose_principal_agent_change(
                uow,
                product_id=product_id,
                body=PrincipalAgentChangeIn(
                    principal_agent=PrincipalAgent.PRINCIPAL, rationale=PRINCIPAL_RATIONALE
                ),
            )
        ctx.approve(ApprovalSubjectType.PRINCIPAL_AGENT_CHANGE, product_id, [CONTROLLER])


def build(ctx: BuildContext) -> None:
    """PRD §2.7 key contracts of WLD-T-01 (module docstring order)."""
    extend_calendars(ctx)
    assess_products(ctx)
    customers = customer_ids(ctx)
    booked = {
        spec.external_id: book(ctx, spec, customers[spec.customer_code]) for spec in KEY_CONTRACTS
    }
    dismiss_suggestions(ctx, booked[K11], DISMISS_RATIONALE)
    for spec in KEY_CONTRACTS:
        contract_id = booked[spec.external_id]
        for key in spec.reviews:
            review_distinct(ctx, contract_id, key)
        record_step1(ctx, contract_id, spec.inception)
        if not spec.activates:
            continue
        activate(ctx, contract_id)
        record_events(ctx, contract_id, spec.events)


def external_ids() -> tuple[str, ...]:
    return tuple(spec.external_id for spec in KEY_CONTRACTS)
