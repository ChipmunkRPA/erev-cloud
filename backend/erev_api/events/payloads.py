"""Versioned contract event payloads KRN-EVT (dev-guide §5.11 DG-KRN-EVT-03, §6.8 DG-ARC-08; 04 §3.3
E-03, §16.1, §16.3; BUILD_SPEC CTR-1).

Each E-03 event type has version 1 of its payload model ``<PascalCase>V1``. Models forbid unknown
members and are frozen; money members are API-S-Money objects (``MoneyIn``, amounts as strings) and
decimal members are strings (``DecimalStr``), so a JSON number fails with rule ``API-C-06``. Amounts
are non-negative unless the §16.3 table marks them signed; its "> 0" and "0-1" bounds are checked
here, and every rule that needs stored data is the command's.

A payload change adds ``<Name>V<n+1>``, raises ``LATEST_SCHEMA_VERSION`` and registers the step in
``UPCASTS``; stored events are never rewritten. ``parse_payload`` upcasts a stored payload to the
latest version before validating it. The first such change is ``OPENING_BALANCE_ESTABLISHED``
version 2 (04 rev 1.61; D-98 candidate 127): the eight money members of an opening obligation are
API-S-ExactMoney (``ExactMoneyIn``, the exact legacy value, ENGINE_SPEC S07-R-03 / S07-R-11) and the
version-1 → 2 step is the identity — every four-place version-1 amount is a valid exact amount, so
stored bodies, hashes and replay are unchanged.

[J] L3-1-Q-15: ``CONTRACT_BOOKED`` carries the API-S-ContractCreate header members and ``lines``,
without the command flag ``submit_for_activation``; ``CONTRACT_ACTIVATED.checklist`` is the item
list of API-S-ActivationChecklist (dev-guide §6.1 example); ``LINE_ATTRIBUTES_CHANGED.diff`` is an
object whose shape 04 does not define.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Annotated, Any, Final, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from pydantic_core import PydanticCustomError

from erev_api.enums import (
    BookCode,
    ContractEventType,
    HoldSource,
    HoldType,
    ModificationTreatment,
    ScopeFlag,
)
from erev_api.money import CurrencyCode, DecimalStr, ExactMoneyIn, MoneyIn

SCHEMA_VERSION_1: Final = 1


def _bound_error(message: str) -> PydanticCustomError:
    return PydanticCustomError("payload_bound", message)


def _positive_money(value: MoneyIn) -> MoneyIn:
    if Decimal(value.amount) <= 0:
        raise _bound_error("Send an amount above 0.")
    return value


def _non_negative_money(value: MoneyIn) -> MoneyIn:
    if Decimal(value.amount) < 0:
        raise _bound_error("Send an amount of at least 0.")
    return value


def _positive_decimal(value: str) -> str:
    if Decimal(value) <= 0:
        raise _bound_error("Send a value above 0.")
    return value


def _non_negative_decimal(value: str) -> str:
    if Decimal(value) < 0:
        raise _bound_error("Send a value of at least 0.")
    return value


def _ratio(value: str) -> str:
    if not Decimal(0) <= Decimal(value) <= Decimal(1):
        raise _bound_error("Send a ratio from 0 to 1.")
    return value


PositiveMoney = Annotated[MoneyIn, AfterValidator(_positive_money)]
NonNegativeMoney = Annotated[MoneyIn, AfterValidator(_non_negative_money)]
PositiveDecimal = Annotated[DecimalStr, AfterValidator(_positive_decimal)]
NonNegativeDecimal = Annotated[DecimalStr, AfterValidator(_non_negative_decimal)]
Ratio = Annotated[DecimalStr, AfterValidator(_ratio)]
Key = Annotated[str, StringConstraints(min_length=1, max_length=255)]
Memo = Annotated[str, StringConstraints(min_length=1, max_length=4000)]
Criterion = Literal["25_9_A", "25_9_B", "25_9_C"]
# 04 table 3.4-R: the E-110 subset of CONTRACT_VOIDED and EVENT_VOIDED.
VoidReason = Literal[
    "DUPLICATE",
    "CREATED_IN_ERROR",
    "CUSTOMER_CANCELLED",
    "DATA_CORRECTION",
    "ESTIMATE_CORRECTION",
    "OTHER",
]


class Payload(BaseModel):
    """Base of every payload model (DG-KRN-EVT-03)."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class EventPayload(Payload):
    """Base of the E-03 payload models: ``effective_at`` keeps the instant of an API-S-EventAppend
    item sent with ``effective_at`` instead of ``effective_date``, as evidence (05 TZ-03; BUILD_SPEC
    CTR-5). ``payload_json`` omits it when absent, so stored payloads without it are unchanged."""

    effective_at: AwareDatetime | None = None


# --- shared members (04 §16.1) ----------------------------------------------------------------


class ContractLineV1(Payload):
    """API-S-ContractLine: a booking line."""

    obligation_key: Key
    product_code: Key
    stratification: str | None = None
    quantity: DecimalStr
    total_price: MoneyIn  # signed: negative VC rows under the parity preset (POL-213)
    unit_price: DecimalStr | None = None
    start_date: date | None = None
    end_date: date | None = None
    performing_entity_code: str | None = None
    ssp_version_label: str | None = None
    ssp_override_justification: str | None = None
    account_overrides: dict[str, str] | None = None
    scope_flag: ScopeFlag = ScopeFlag.IN_SCOPE_606
    out_of_scope_amount: MoneyIn | None = None
    bundle_parent_obligation_key: str | None = None
    memo_1: str | None = None
    memo_2: str | None = None
    memo_3: str | None = None
    custom_attributes: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _line_rules(self) -> Self:
        if Decimal(self.quantity) == 0:
            raise ValueError("quantity must not be 0 (REQ-DAT-005)")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if self.scope_flag is not ScopeFlag.IN_SCOPE_606 and self.out_of_scope_amount is None:
            raise ValueError("out_of_scope_amount is required outside IN_SCOPE_606")
        return self


class CustomerRefV1(Payload):
    code: Key
    name: Key


class TerminationV1(Payload):
    party: Literal["NONE", "CUSTOMER", "ENTITY", "BOTH"]
    has_penalty: bool | None = None
    notice_days: int | None = Field(default=None, ge=0)


class PaymentPointV1(Payload):
    """API-S-PaymentPoint."""

    date: date
    amount: PositiveMoney


class NoncashConsiderationV1(Payload):
    """API-S-NoncashConsideration."""

    units: PositiveDecimal
    fair_value_per_unit: NonNegativeDecimal
    measurement_date: date
    variability: Literal["FORM", "PERFORMANCE"]
    asset_type: str | None = None


class ConsiderationPayableV1(Payload):
    """API-S-ConsiderationPayable."""

    amount: PositiveMoney
    promise_date: date
    related_obligation_keys: tuple[Key, ...] = ()
    distinct_good_fair_value: NonNegativeMoney | None = None
    committed_purchases: NonNegativeMoney | None = None
    share_based: bool = False


def _unique(values: list[str], member: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{member} repeat")


def _ascending_dates(points: tuple[PaymentPointV1, ...]) -> None:
    dates = [point.date for point in points]
    if any(later <= earlier for earlier, later in zip(dates, dates[1:], strict=False)):
        raise ValueError("payment_schedule dates must be unique and ascending")


# --- E-03 payloads (04 §16.3) -----------------------------------------------------------------


class ContractBookedV1(EventPayload):
    external_id: Key
    customer_id: UUID | None = None
    customer: CustomerRefV1 | None = None
    contracting_entity_code: Key
    transaction_currency: CurrencyCode
    inception_date: date
    signature_date: date | None = None
    document_ref: str | None = None
    payment_terms: str | None = None
    termination: TerminationV1 | None = None
    # 04 §16.3 rev 1.287 (item ACT-FLAGS-1): whether the contract holds a customer acceptance
    # clause, and whether a side letter exists beside it. Three states each — true, false, and
    # absent: "not stated", which ``payload_json`` leaves out of the stored payload.
    acceptance_clause: bool | None = None
    side_letter: bool | None = None
    has_commercial_substance: bool = True
    region: str | None = None
    channel: str | None = None
    contract_type: str | None = None
    memo_1: str | None = None
    memo_2: str | None = None
    memo_3: str | None = None
    custom_attributes: dict[str, Any] | None = None
    scope_605_35: bool = False
    renewal_of_contract_id: UUID | None = None
    payment_schedule: tuple[PaymentPointV1, ...] = Field(default=(), max_length=500)
    noncash_consideration: tuple[NoncashConsiderationV1, ...] = Field(default=(), max_length=50)
    consideration_payable: tuple[ConsiderationPayableV1, ...] = Field(default=(), max_length=50)
    lines: tuple[ContractLineV1, ...] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _booking_rules(self) -> Self:
        if self.customer_id is None and self.customer is None:
            raise ValueError("one of customer_id or customer is required")
        keys = [line.obligation_key for line in self.lines]
        _unique(keys, "obligation keys")
        parents = {line.bundle_parent_obligation_key for line in self.lines}
        if not parents <= {None, *keys}:
            raise ValueError("bundle_parent_obligation_key must name a line of the booking")
        _ascending_dates(self.payment_schedule)
        return self


class ChecklistItemV1(Payload):
    code: Key
    passed: bool
    detail: str | None = None


class ContractActivatedV1(EventPayload):
    checklist: tuple[ChecklistItemV1, ...] = Field(min_length=1)


class CollectibilityAssessedV1(EventPayload):
    book: BookCode
    is_probable: bool
    credit_grade: str | None = None
    mitigation: Literal["ADVANCE_PAYMENT", "STOP_SERVICE"] | None = None
    expected_collectible_amount: NonNegativeMoney | None = None
    judgement_record_id: UUID


class ContractCriteriaMetV1(EventPayload):
    book: BookCode
    judgement_record_id: UUID


class SignificantChangeFlaggedV1(EventPayload):
    description: Memo


class SspBasisV1(Payload):
    """One obligation of T-CON-06 ``ssp_basis``."""

    ssp_book_version_id: UUID | None = None
    is_override: bool = False
    justification: str | None = None


class ModificationLineV1(Payload):
    """One T-CON-06 ``lines`` item, which ``CONTRACT_AMENDED`` copies from the modification (04
    §16.3; §17.4 LM-TPL-MOD: legacy ``Mod Billing`` = ``consideration_delta``, ``Mod Qty`` =
    ``quantity_delta``, both signed). [J] L5-1-Q-27 (BUILD_SPEC DIN-6): the lines are modification
    lines, not booking lines."""

    obligation_key: Key
    action: Literal["ADD", "REMOVE", "CHANGE"]
    product_code: Key | None = None
    quantity_delta: DecimalStr = "0"
    consideration_delta: MoneyIn | None = None
    start_date: date | None = None
    end_date: date | None = None
    stratification: str | None = None
    selling_entity_code: str | None = None
    account_codes: dict[str, str] | None = None
    ssp_version_label: str | None = None
    memo_1: str | None = None
    memo_2: str | None = None
    memo_3: str | None = None

    @model_validator(mode="after")
    def _line_rules(self) -> Self:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class ContractAmendedV1(EventPayload):
    modification_id: UUID
    treatments: dict[str, ModificationTreatment]
    lines: tuple[ModificationLineV1, ...] = Field(max_length=500)
    ssp_basis: dict[str, SspBasisV1]
    price_change_settlement: Literal["FUTURE_PRICING", "CREDIT_OR_REFUND"] | None = None
    noncash_consideration: tuple[NoncashConsiderationV1, ...] | None = Field(
        default=None, max_length=50
    )
    consideration_payable: tuple[ConsiderationPayableV1, ...] | None = Field(
        default=None, max_length=50
    )
    scope_605_35: bool | None = None

    @model_validator(mode="after")
    def _amendment_rules(self) -> Self:
        _unique([line.obligation_key for line in self.lines], "obligation keys")
        return self


class ContractTerminatedV1(EventPayload):
    modification_id: UUID
    termination_kind: Literal["FULL", "PARTIAL"]
    obligation_keys: tuple[Key, ...] | None = None
    refund_amount: NonNegativeMoney | None = None


class DeliveryRecordedV1(EventPayload):
    obligation_key: Key
    quantity: PositiveDecimal
    trigger: Literal["DELIVERY", "ACCEPTANCE", "SELL_THROUGH", "BILL_AND_HOLD", "CONTROL_TRANSFER"]
    source_ref: str | None = None


class ProgressRecordedV1(EventPayload):
    obligation_key: Key
    cumulative_progress_ratio: Ratio
    measure: Literal["OUTPUT_PERCENT", "LABOUR_HOURS"]
    hours_to_date: NonNegativeDecimal | None = None


class MilestoneAchievedV1(EventPayload):
    obligation_key: Key
    milestone_code: Key
    cumulative_weight: Ratio


class UsageReportedV1(EventPayload):
    obligation_key: Key
    usage_period_start: date
    usage_period_end: date
    metric: Key
    quantity: DecimalStr
    rated_amount: NonNegativeMoney | None = None
    is_royalty_statement: bool | None = None

    @model_validator(mode="after")
    def _period(self) -> Self:
        if self.usage_period_end < self.usage_period_start:
            raise ValueError("usage_period_end must not be before usage_period_start")
        return self


class CostIncurredV1(EventPayload):
    purpose: Literal["PROGRESS_INPUT", "COST_TO_OBTAIN", "COST_TO_FULFILL", "WARRANTY_CLAIM"]
    obligation_key: Key | None = None
    amount: NonNegativeMoney
    is_wasted: bool | None = None
    is_uninstalled_material: bool | None = None
    payee: str | None = None
    plan_code: str | None = None
    is_incremental: bool | None = None
    has_clawback: bool | None = None
    cost_adjustment: Literal["CLAWBACK"] | None = None

    @model_validator(mode="after")
    def _cost_rules(self) -> Self:
        if self.purpose == "WARRANTY_CLAIM" and self.obligation_key is None:
            raise ValueError("obligation_key is required for WARRANTY_CLAIM")
        if self.cost_adjustment == "CLAWBACK":
            if self.purpose != "COST_TO_OBTAIN":
                raise ValueError("cost_adjustment CLAWBACK needs purpose COST_TO_OBTAIN")
            if not self.payee or not self.plan_code:
                raise ValueError("a CLAWBACK names payee and plan_code")
        return self


class TaxLineV1(Payload):
    tax_type: Key
    amount: NonNegativeMoney
    principal_or_agent: Literal["PRINCIPAL", "AGENT"]


class BillingRecordedV1(EventPayload):
    invoice_number: Key
    line_external_id: Key
    obligation_key: Key | None = None
    amount: PositiveMoney
    issue_date: date
    due_date: date | None = None
    is_cancellable: bool | None = None
    tax_amount: NonNegativeMoney | None = None
    tax_lines: tuple[TaxLineV1, ...] | None = None
    service_period_start: date | None = None
    service_period_end: date | None = None
    source_invoice_id: str | None = None

    @model_validator(mode="after")
    def _billing_rules(self) -> Self:
        if self.tax_lines is not None:
            if self.tax_amount is None:
                raise ValueError("tax_lines need tax_amount")
            total = sum((Decimal(line.amount.amount) for line in self.tax_lines), Decimal(0))
            currencies = {line.amount.currency for line in self.tax_lines}
            if total != Decimal(self.tax_amount.amount) or not currencies <= {
                self.tax_amount.currency
            }:
                raise ValueError("tax_lines amounts must sum to tax_amount")
        start, end = self.service_period_start, self.service_period_end
        if start and end and end < start:
            raise ValueError("service_period_end must not be before service_period_start")
        return self


class CreditMemoRecordedV1(EventPayload):
    credit_memo_number: Key
    credited_invoice_number: str | None = None
    obligation_key: Key | None = None
    amount: PositiveMoney
    issue_date: date
    reason: str | None = None


class PaymentReceivedV1(EventPayload):
    receipt_reference: Key
    amount: PositiveMoney
    receipt_date: date
    applied_invoice_numbers: tuple[Key, ...] | None = None
    form: Literal["CASH", "NONCASH"] = "CASH"
    units_received: PositiveDecimal | None = None
    asset_type: str | None = None

    @model_validator(mode="after")
    def _form_rules(self) -> Self:
        if (self.form == "NONCASH") != (self.units_received is not None):
            raise ValueError("units_received is required with form NONCASH and absent otherwise")
        return self


class ReturnRecordedV1(EventPayload):
    obligation_key: Key
    quantity: PositiveDecimal
    refund_amount: NonNegativeMoney | None = None
    reason: str | None = None


class EstimateChangedV1(EventPayload):
    estimate_version_id: UUID
    previous_estimate_version_id: UUID | None = None


class MaterialRightExercisedV1(EventPayload):
    obligation_key: Key
    exercised_quantity: PositiveDecimal | None = None
    additional_consideration: NonNegativeMoney | None = None
    new_lines: tuple[ContractLineV1, ...] | None = Field(default=None, max_length=500)


class MaterialRightExpiredV1(EventPayload):
    obligation_key: Key


class HoldAppliedV1(EventPayload):
    hold_type: HoldType
    hold_source: HoldSource
    obligation_key: Key | None = None
    reason: Memo
    rule_id: UUID | None = None


class HoldReleasedV1(EventPayload):
    hold_id: UUID
    comment: Memo


class PreStandardRevenueRecordedV1(EventPayload):
    obligation_key: Key
    amount: MoneyIn  # signed (POL-008)


class ManualAdjustmentAppliedV1(EventPayload):
    manual_adjustment_id: UUID


class CombinationChangedV1(EventPayload):
    combination_group_id: UUID
    action: Literal["JOIN", "LEAVE"]
    criterion: Criterion | None = None


class OpeningObligationV1(Payload):
    """One member of ``OPENING_BALANCE_ESTABLISHED.obligations``."""

    obligation_key: Key
    delivered_quantity_cum: DecimalStr
    ssp_delivered_cum: DecimalStr
    remaining_quantity: DecimalStr
    remaining_ssp: DecimalStr
    revenue_cum: MoneyIn
    billed_cum: MoneyIn
    catch_up_cum: MoneyIn
    pre_standard_revenue_cum: MoneyIn
    remaining_allocation: MoneyIn
    remaining_billing: MoneyIn
    position_obligation: MoneyIn
    netting_reclass_amount: MoneyIn


class OpeningObligationV2(Payload):
    """One member of ``OPENING_BALANCE_ESTABLISHED.obligations`` at payload version 2 (04 §16.3 rev
    1.61; D-98 candidate 127): the eight money members are API-S-ExactMoney — the exact legacy
    value with at most 20 integer and 18 fractional digits, never quantized (ENGINE_SPEC S07-R-03,
    S07-R-11); the four quantity / SSP members stay ``DecimalStr``."""

    obligation_key: Key
    delivered_quantity_cum: DecimalStr
    ssp_delivered_cum: DecimalStr
    remaining_quantity: DecimalStr
    remaining_ssp: DecimalStr
    revenue_cum: ExactMoneyIn
    billed_cum: ExactMoneyIn
    catch_up_cum: ExactMoneyIn
    pre_standard_revenue_cum: ExactMoneyIn
    remaining_allocation: ExactMoneyIn
    remaining_billing: ExactMoneyIn
    position_obligation: ExactMoneyIn
    netting_reclass_amount: ExactMoneyIn


OpeningReason = Literal["LEGACY_MIGRATION", "SYSTEM_ONBOARDING", "BUSINESS_COMBINATION"]


def _opening_rules(
    reason: str,
    fair_value: MoneyIn | None,
    obligations: tuple[OpeningObligationV1, ...] | tuple[OpeningObligationV2, ...],
) -> None:
    if fair_value is not None and reason != "BUSINESS_COMBINATION":
        raise ValueError("fair_value_contract_liability needs reason BUSINESS_COMBINATION")
    _unique([item.obligation_key for item in obligations], "obligation keys")


class OpeningBalanceEstablishedV1(EventPayload):
    """Payload version 1: the eight money members of a row are API-S-Money (four fractional
    digits). Kept for stored events; new appends use version 2, to which version 1 upcasts
    unchanged (``UPCASTS``)."""

    reason: OpeningReason
    cutover_date: date
    migration_batch_id: UUID | None = None
    fair_value_contract_liability: NonNegativeMoney | None = None
    obligations: tuple[OpeningObligationV1, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _rules(self) -> Self:
        _opening_rules(self.reason, self.fair_value_contract_liability, self.obligations)
        return self


class OpeningBalanceEstablishedV2(EventPayload):
    """Payload version 2 (04 §16.3 rev 1.61; D-98 candidate 127): as version 1 with
    ``OpeningObligationV2`` rows (exact money members); ``fair_value_contract_liability`` stays
    API-S-Money."""

    reason: OpeningReason
    cutover_date: date
    migration_batch_id: UUID | None = None
    fair_value_contract_liability: NonNegativeMoney | None = None
    obligations: tuple[OpeningObligationV2, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _rules(self) -> Self:
        _opening_rules(self.reason, self.fair_value_contract_liability, self.obligations)
        return self


class EventVoidedV1(EventPayload):
    reason_code: VoidReason
    comment: Memo


class ContractVoidedV1(EventPayload):
    reason_code: VoidReason
    comment: Memo
    # D-98 99a: the approved posted-state cutoff the SYSTEM append carries from the CONTRACT_VOID
    # request (04 §16.3); the engine reads none of these.
    approval_request_id: UUID | None = None
    posted_line_count: int | None = None
    posted_through: AwareDatetime | None = None
    posted_through_seq: dict[str, int] | None = None  # D-98 99b: per book, T-SL-02 chain_seq


class LineAttributeChangesV1(Payload):
    account_overrides: dict[str, str] | None = None
    performing_entity_code: str | None = None
    ssp_version_label: str | None = None
    ssp_book_version_id: UUID | None = None
    justification: str | None = None

    @model_validator(mode="after")
    def _changes(self) -> Self:
        members = (
            self.account_overrides,
            self.performing_entity_code,
            self.ssp_version_label,
            self.ssp_book_version_id,
        )
        if all(member is None for member in members):
            raise ValueError("changes names at least one attribute")
        if self.ssp_book_version_id is not None and not self.justification:
            raise ValueError("ssp_book_version_id needs a justification")
        return self


class LineAttributesChangedV1(EventPayload):
    obligation_key: Key
    changes: LineAttributeChangesV1
    diff: dict[str, Any]


MemoMember = Literal["memo_1", "memo_2", "memo_3", "custom_attributes", "dimensions"]
# The members an ``update-memos`` writer can supply (04 §16.1, §16.3): the presence set ``named``
# admits every one of them (ENGINE_SPEC CV-47 (a)); ``locks.MEMO_MEMBERS`` and the record-events
# derivation read this tuple so the three never drift.
MEMO_UPDATED_MEMBERS: Final[tuple[MemoMember, ...]] = (
    "memo_1",
    "memo_2",
    "memo_3",
    "custom_attributes",
    "dimensions",
)


class MemoUpdatedV1(EventPayload):
    """04 §16.3 ``MEMO_UPDATED``. ``named`` is the presence set of the members this event sets —
    any of ``MEMO_UPDATED_MEMBERS`` (ENGINE_SPEC CV-47 (a); Codex T1F2-MEMO-R1): the stored form
    writes every member, so an omitted sibling appears as null and only ``named`` tells a supplied
    null (a memo clear; an empty attribute set) from an omission. Every producer writes it; an
    event without it (persisted earlier) keeps its earlier readings — the engine's obligation fold
    reads strings replace / nulls are omissions, the header projection its ``model_fields_set``."""

    obligation_key: Key | None = None
    memo_1: str | None = None
    memo_2: str | None = None
    memo_3: str | None = None
    custom_attributes: dict[str, Any] | None = None
    dimensions: dict[str, str] | None = None
    named: tuple[MemoMember, ...] | None = None


class RegroupedV1(EventPayload):
    regroup_id: UUID
    direction: Literal["OUT", "IN"]
    obligation_keys: tuple[Key, ...] = Field(min_length=1)
    counterpart_contract_id: UUID
    modification_id: UUID
    # D-98 140-A6 REGROUP-R1 (04 §16.3 rev 1.70): an IN event carries the moved obligations' booked
    # lines so the target group's bundle reconstructs the move without the source group.
    lines: tuple[ContractLineV1, ...] = Field(default=(), max_length=500)


_V1: Final[tuple[tuple[ContractEventType, type[Payload]], ...]] = (
    (ContractEventType.CONTRACT_BOOKED, ContractBookedV1),
    (ContractEventType.CONTRACT_ACTIVATED, ContractActivatedV1),
    (ContractEventType.COLLECTIBILITY_ASSESSED, CollectibilityAssessedV1),
    (ContractEventType.CONTRACT_CRITERIA_MET, ContractCriteriaMetV1),
    (ContractEventType.CONTRACT_AMENDED, ContractAmendedV1),
    (ContractEventType.DELIVERY_RECORDED, DeliveryRecordedV1),
    (ContractEventType.PROGRESS_RECORDED, ProgressRecordedV1),
    (ContractEventType.MILESTONE_ACHIEVED, MilestoneAchievedV1),
    (ContractEventType.USAGE_REPORTED, UsageReportedV1),
    (ContractEventType.COST_INCURRED, CostIncurredV1),
    (ContractEventType.BILLING_RECORDED, BillingRecordedV1),
    (ContractEventType.CREDIT_MEMO_RECORDED, CreditMemoRecordedV1),
    (ContractEventType.PAYMENT_RECEIVED, PaymentReceivedV1),
    (ContractEventType.RETURN_RECORDED, ReturnRecordedV1),
    (ContractEventType.ESTIMATE_CHANGED, EstimateChangedV1),
    (ContractEventType.MATERIAL_RIGHT_EXERCISED, MaterialRightExercisedV1),
    (ContractEventType.MATERIAL_RIGHT_EXPIRED, MaterialRightExpiredV1),
    (ContractEventType.HOLD_APPLIED, HoldAppliedV1),
    (ContractEventType.HOLD_RELEASED, HoldReleasedV1),
    (ContractEventType.PRE_STANDARD_REVENUE_RECORDED, PreStandardRevenueRecordedV1),
    (ContractEventType.MANUAL_ADJUSTMENT_APPLIED, ManualAdjustmentAppliedV1),
    (ContractEventType.CONTRACT_TERMINATED, ContractTerminatedV1),
    (ContractEventType.COMBINATION_CHANGED, CombinationChangedV1),
    (ContractEventType.OPENING_BALANCE_ESTABLISHED, OpeningBalanceEstablishedV1),
    (ContractEventType.EVENT_VOIDED, EventVoidedV1),
    (ContractEventType.CONTRACT_VOIDED, ContractVoidedV1),
    (ContractEventType.SIGNIFICANT_CHANGE_FLAGGED, SignificantChangeFlaggedV1),
    (ContractEventType.LINE_ATTRIBUTES_CHANGED, LineAttributesChangedV1),
    (ContractEventType.MEMO_UPDATED, MemoUpdatedV1),
    (ContractEventType.REGROUPED, RegroupedV1),
)

# Later versions (DG-KRN-EVT-03): OPENING_BALANCE_ESTABLISHED V2 (04 rev 1.61; D-98 candidate 127).
_LATER: Final[tuple[tuple[ContractEventType, int, type[BaseModel]], ...]] = (
    (ContractEventType.OPENING_BALANCE_ESTABLISHED, 2, OpeningBalanceEstablishedV2),
)
PAYLOADS: Final[Mapping[tuple[ContractEventType, int], type[BaseModel]]] = MappingProxyType(
    {
        **{(event_type, SCHEMA_VERSION_1): model for event_type, model in _V1},
        **{(event_type, version): model for event_type, version, model in _LATER},
    }
)
LATEST_SCHEMA_VERSION: Final[Mapping[ContractEventType, int]] = MappingProxyType(
    {event_type: max(v for t, v in PAYLOADS if t is event_type) for event_type, _ in _V1}
)


def _unchanged(data: Mapping[str, Any]) -> Mapping[str, Any]:
    """The identity upcast: every version-1 body is a valid version-2 body (a four-place API-S-Money
    amount is an exact amount), so stored bytes and hashes stay as written."""
    return data


# (event type, version n) → the step producing version n + 1 of the payload.
UPCASTS: Final[
    Mapping[tuple[ContractEventType, int], Callable[[Mapping[str, Any]], Mapping[str, Any]]]
] = MappingProxyType({(ContractEventType.OPENING_BALANCE_ESTABLISHED, 1): _unchanged})


def model_name(event_type: ContractEventType, schema_version: int) -> str:
    """``<PascalCase>V<schema_version>`` of an E-03 literal (04 §3.3)."""
    pascal = "".join(part.capitalize() for part in event_type.value.split("_"))
    return f"{pascal}V{schema_version}"


def upcast(
    event_type: ContractEventType, schema_version: int, data: Mapping[str, Any]
) -> tuple[int, Mapping[str, Any]]:
    """Apply the registered steps from ``schema_version`` up to the latest version."""
    latest = LATEST_SCHEMA_VERSION[event_type]
    if not 1 <= schema_version <= latest:
        raise ValueError(f"{event_type.value} has no payload version {schema_version}")
    version, current = schema_version, data
    while version < latest:
        step = UPCASTS.get((event_type, version))
        if step is None:
            raise LookupError(f"no upcast of {event_type.value} from version {version}")
        current = step(current)
        version += 1
    return version, current


def parse_payload(
    event_type: ContractEventType, schema_version: int, data: Mapping[str, Any]
) -> BaseModel:
    """Validate a stored or submitted payload as the latest model of its event type."""
    version, current = upcast(event_type, schema_version, data)
    return PAYLOADS[(event_type, version)].model_validate(current)


# Members a payload gained after events of its type were stored, each absent from the stored JSON
# while it is not stated: a payload that does not state them is stored — and hashed — as it was
# before the member existed (04 §16.3 rev 1.287; item ACT-FLAGS-1).
STATED_ONLY: Final[Mapping[type[BaseModel], tuple[str, ...]]] = MappingProxyType(
    {ContractBookedV1: ("acceptance_clause", "side_letter")}
)


def payload_json(payload: BaseModel) -> dict[str, Any]:
    """The stored JSON form of a payload: every member, dates and ids as strings; ``effective_at``
    only when it is set (TZ-03), and the members of ``STATED_ONLY`` only when they are stated."""
    body = payload.model_dump(mode="json")
    if isinstance(payload, EventPayload) and payload.effective_at is None:
        body.pop("effective_at", None)
    for model, members in STATED_ONLY.items():
        if isinstance(payload, model):
            for member in members:
                if body.get(member) is None:
                    body.pop(member, None)
    return body
