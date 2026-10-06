"""API-R-28 contract schemas (04 §15.3 API-R-28; §16.0; §16.1 API-S-ContractCreate, API-S-Contract,
API-S-ContractVersion, API-S-ContractBalance, API-S-AllocationWalk; §16.2 API-S-Obligation,
API-S-ScheduleLine; §16.14 API-S-ContractHistoryItem; API-C-06; BUILD_SPEC CTR-4).

The request body of ``POST /contracts`` and ``POST /contracts/{id}/replace-draft`` is the
``CONTRACT_BOOKED`` payload (``events.payloads.ContractBookedV1``) plus the command flag
``submit_for_activation``. Its money members refuse a bare JSON number with rule ``API-C-06``
(REQ-PLT-031), as ``MoneyIn`` already does for a numeric ``amount``. Class names drop the
``API-S-`` prefix and append ``Out`` (DG-API-03). Decimals leave as API-C-06 strings.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from pydantic_core import PydanticCustomError

from erev_api.enums import (
    AccountRole,
    BookCode,
    ContractStatus,
    ContractStep,
    ContractStepState,
    Distinctness,
    HistoryItemKind,
    HoldSource,
    HoldType,
    ReasonCode,
    SourceSystem,
    SspRangePosition,
)
from erev_api.events.payloads import (
    ConsiderationPayableV1,
    ContractBookedV1,
    ContractLineV1,
    NonNegativeMoney,
    PaymentPointV1,
    PositiveMoney,
)
from erev_api.money import MONEY_MESSAGE, RULE_ID, MoneyIn, MoneyOut
from erev_api.schemas.common import ActorOut, ContextOut, RefOut

__all__ = [
    "ActivationChecklistItemOut",
    "ActivationChecklistOut",
    "AllocationLineOut",
    "AllocationTotalsOut",
    "AllocationWalkOut",
    "BalanceLinksOut",
    "CauseEventOut",
    "CombinationGroupOut",
    "ContractBalanceFunctionalOut",
    "ContractBalanceOut",
    "ContractCreateIn",
    "ContractDetailKpisOut",
    "ContractHistoryItemOut",
    "ContractKpisOut",
    "ContractLineIn",
    "ContractLinksOut",
    "ContractListItemOut",
    "ContractOut",
    "ContractStepOut",
    "ContractVersionOut",
    "ContractVersionSummaryOut",
    "ContractVoidRequestIn",
    "ContractVoidRequestedOut",
    "DistinctReviewIn",
    "DistinctReviewOut",
    "EntityBalanceKpiOut",
    "HoldOut",
    "KpiRatiosOut",
    "ObligationOut",
    "ScheduleLineOut",
    "SubmitActivationIn",
    "TerminationOut",
    "TransactionPriceBuildupOut",
    "VersionChangeOut",
    "VersionCompareOut",
    "VersionRefOut",
]


def _reject_number(value: object) -> object:
    """API-C-06: a money member sent as a JSON number instead of an API-S-Money object."""
    if isinstance(value, int | float | Decimal) and not isinstance(value, bool):
        raise PydanticCustomError("api_c_06", MONEY_MESSAGE, {"rule_id": RULE_ID})
    return value


_NUMBER_REFUSED = BeforeValidator(_reject_number)
ApiMoney = Annotated[MoneyIn, _NUMBER_REFUSED]
OptionalApiMoney = Annotated[MoneyIn | None, _NUMBER_REFUSED]


# --- requests (04 §16.1) --------------------------------------------------------------------------


class ContractLineIn(ContractLineV1):
    """API-S-ContractLine."""

    total_price: ApiMoney
    out_of_scope_amount: OptionalApiMoney = None


class PaymentPointIn(PaymentPointV1):
    """API-S-PaymentPoint."""

    amount: Annotated[PositiveMoney, _NUMBER_REFUSED]


class ConsiderationPayableIn(ConsiderationPayableV1):
    """API-S-ConsiderationPayable."""

    amount: Annotated[PositiveMoney, _NUMBER_REFUSED]
    distinct_good_fair_value: Annotated[NonNegativeMoney | None, _NUMBER_REFUSED] = None
    committed_purchases: Annotated[NonNegativeMoney | None, _NUMBER_REFUSED] = None


class ContractCreateIn(ContractBookedV1):
    """API-S-ContractCreate: the ``CONTRACT_BOOKED`` members and ``submit_for_activation``."""

    payment_schedule: tuple[PaymentPointIn, ...] = Field(default=(), max_length=500)
    consideration_payable: tuple[ConsiderationPayableIn, ...] = Field(default=(), max_length=50)
    lines: tuple[ContractLineIn, ...] = Field(min_length=1, max_length=500)
    submit_for_activation: bool = False

    def booking(self) -> ContractBookedV1:
        """The ``CONTRACT_BOOKED`` payload of the request (without the command flag)."""
        return ContractBookedV1.model_validate(self.model_dump(exclude={"submit_for_activation"}))


# --- API-S-Contract (04 §16.1) --------------------------------------------------------------------


class TerminationOut(BaseModel):
    party: str
    has_penalty: bool | None
    notice_days: int | None


class CombinationGroupOut(BaseModel):
    id: uuid.UUID
    code: str
    is_singleton: bool
    member_contract_ids: list[uuid.UUID] = Field(
        description="The members the caller reads (REQ-PLT-012)"
    )
    member_count: int = Field(
        description=(
            "How many members the group has in all: greater than the length of "
            "`member_contract_ids` when some are contracts the caller does not read"
        )
    )


class ContractStepOut(BaseModel):
    """One of the five E-112 steps derived by the §16.14 step rule."""

    step: ContractStep
    state: ContractStepState
    status_code: str | None
    detail: dict[str, Any]


class KpiRatiosOut(BaseModel):
    billed: str | None
    recognized: str | None
    pending_trigger_count: int


class ContractKpisOut(BaseModel):
    transaction_price: MoneyOut
    revenue_to_date: MoneyOut
    billed_to_date: MoneyOut
    scheduled: MoneyOut
    awaiting_trigger: MoneyOut
    rpo: MoneyOut


class BalanceLinksOut(BaseModel):
    """The Explain address of a balance entry's figures (04 API-S-Contract ``kpis.balances[]`` and
    API-S-ContractBalance ``links``, rev 1.174): ``/explain/contract_version_balance/<T-CON-09 row
    id>/<measure>`` with the ``period`` of the cut. Null when the cut precedes the first period the
    version measures: the figure is 0 and no node holds it."""

    explain_contract_liability: str | None = None
    explain_contract_asset: str | None = None
    explain_unbilled_receivable: str | None = None


class EntityBalanceKpiOut(BaseModel):
    """Labelled balances of one entity; no signed balance member is returned here (D-12)."""

    entity: RefOut
    contract_liability: MoneyOut
    contract_asset: MoneyOut
    unbilled_receivable: MoneyOut
    refund_liability: MoneyOut
    links: BalanceLinksOut = Field(default_factory=BalanceLinksOut)


class ContractDetailKpisOut(ContractKpisOut):
    balances: list[EntityBalanceKpiOut]


class ContractLinksOut(BaseModel):
    self: str
    obligations: str
    events: str
    versions: str
    allocation: str
    schedule: str
    balances: str
    history: str
    explain_transaction_price: str | None


class ContractListItemOut(BaseModel):
    """API-S-Contract as a list item: without ``kpis.balances`` and ``links``."""

    id: uuid.UUID
    contract_no: str
    external_id: str
    status: ContractStatus
    customer: RefOut
    contracting_entity: RefOut
    transaction_currency: str
    inception_date: date
    combination_group: CombinationGroupOut
    head_stream_version: int
    signature_date: date | None
    document_ref: str | None
    payment_terms: str | None
    termination: TerminationOut | None
    has_commercial_substance: bool
    region: str | None
    channel: str | None
    contract_type: str | None
    memo_1: str | None
    memo_2: str | None
    memo_3: str | None
    custom_attributes: dict[str, Any]
    activation_checklist: Any | None
    activated_at: datetime | None
    completed_at: datetime | None
    terminated_at: datetime | None
    voided_at: datetime | None
    renewal_of_contract_id: uuid.UUID | None
    source_system: SourceSystem
    on_hold: bool
    open_exception_count: int
    status_reason: str | None
    scope_605_35: bool
    payment_schedule: list[dict[str, Any]]
    noncash_consideration: list[dict[str, Any]]
    consideration_payable: list[dict[str, Any]]
    steps: list[ContractStepOut]
    kpis_ratios: KpiRatiosOut
    context: ContextOut | None
    kpis: ContractKpisOut | None
    created_at: datetime
    updated_at: datetime


class HoldOut(BaseModel):
    """One OPEN hold, as API-S-Contract and API-S-Obligation list it under ``holds`` (04 T-CON-20,
    §16.1, §16.2 rev 1.299; item HOLD-RELEASE-READ-1). Until the item the two reads listed no
    hold, so a screen could apply a hold and never release it: ``release-hold`` takes an id no
    read answered. ``id`` is that id — ``hold_id`` of ``POST /contracts/{id}/release-hold``, the
    id of the hold's ``HOLD_APPLIED`` event. ``level``: ``contract`` for a hold of the whole
    contract, listed by API-S-Contract; ``obligation`` for the hold of one obligation, listed by
    that obligation. ``applied_by`` is who recorded the ``HOLD_APPLIED`` event (SYSTEM for the
    hold of a judgement record). ``release_refusal`` is the sentence ``release-hold`` would answer
    for this hold, or null where it would take it — as API-S-Event ``void_refusal`` is for a
    void — so that a screen offers the release only where it can be made, says why where it
    cannot, and keeps no rule of its own; the command's 409 stays the backstop."""

    id: uuid.UUID
    level: Literal["contract", "obligation"]
    hold_type: HoldType
    hold_source: HoldSource
    reason: str
    applied_by: ActorOut
    applied_at: datetime
    release_refusal: str | None


class ContractOut(ContractListItemOut):
    """API-S-Contract (``GET /contracts/{id}``)."""

    kpis: ContractDetailKpisOut | None
    # 04 §16.1 rev 1.299 (item HOLD-RELEASE-READ-1): the contract's open CONTRACT-LEVEL holds,
    # oldest first; the hold of one obligation is listed by API-S-Obligation ``holds``.
    # ``on_hold`` stays true for either. Every answer carries the member; the default keeps it
    # optional in the generated type, as a member a read gained is.
    holds: list[HoldOut] = Field(default_factory=list)
    links: ContractLinksOut


# --- API-S-Obligation (04 §16.2) ------------------------------------------------------------------


class TemplateVersionRefOut(BaseModel):
    id: uuid.UUID
    template_code: str
    version_no: int


class ObligationOriginalOut(BaseModel):
    quantity: str
    ssp_low: str | None
    ssp_mid: str | None
    ssp_high: str | None
    ssp_selected: str
    total_contract_ssp: str
    unit_ssp: str | None
    unit_revenue_rate: str | None
    stated_price: MoneyOut
    allocated_amount: MoneyOut
    total_contract_price: MoneyOut
    ssp_in_range: bool | None


class ObligationCurrentOut(BaseModel):
    quantity: str
    allocation_weight: str
    unit_ssp: str | None
    remaining_unit_revenue_rate: str | None
    stated_price: MoneyOut
    allocated_amount: MoneyOut
    allocation_adjustment: MoneyOut


class ObligationSspOut(BaseModel):
    book_version_id: uuid.UUID | None
    version_label: str | None
    entry_id: uuid.UUID | None
    method: str | None
    unit_list_price: str | None
    midpoint_discount_ratio: str | None
    range_ratio: str | None
    override_approval_request_id: uuid.UUID | None
    range_position: SspRangePosition | None
    outside_range_point: str | None


class ObligationToDateOut(BaseModel):
    delivered_quantity: str
    returned_quantity: str
    progress_ratio: str
    ssp_delivered: str
    revenue: MoneyOut
    billed: MoneyOut
    catch_up: MoneyOut
    catch_up_modification: MoneyOut
    catch_up_tp_change: MoneyOut
    catch_up_estimate: MoneyOut
    pre_standard_revenue: MoneyOut


class ObligationRemainingOut(BaseModel):
    quantity: str
    ssp: str
    allocation: MoneyOut
    billing: MoneyOut


class ObligationRatiosOut(BaseModel):
    recognized: str | None
    scheduled: str | None
    awaiting_trigger: str | None


class PositionOut(BaseModel):
    """D-12 labelled display of ``position_obligation``."""

    label: str
    amount: MoneyOut


class NettingReclassOut(BaseModel):
    amount: MoneyOut
    role: AccountRole | None


class ObligationLinksOut(BaseModel):
    self: str
    versions: str
    schedule: str
    events: str
    explain_revenue_to_date: str
    # 04 rev 1.132: the node that holds ``to_date.billed``; its period is one of the contracting
    # entity's, which the item's ``measured_period`` (the performing entity's) does not name.
    explain_billed_to_date: str | None = None
    explain_allocated_amount: str


class ObligationOut(BaseModel):
    """API-S-Obligation at a contract version."""

    id: uuid.UUID
    obligation_version_id: uuid.UUID
    contract_id: uuid.UUID
    obligation_key: str
    legacy_record_key: str
    product: RefOut
    stratification: str
    obligation_kind: str
    distinctness: str
    series_increment_unit: str | None
    pob_template_version: TemplateVersionRefOut
    scope_flag: str
    satisfaction_pattern: str
    over_time_criterion: str
    recognition_method: str
    ratable_convention: str | None
    principal_agent: str
    licence_nature: str
    warranty_type: str
    start_date: date | None
    end_date: date | None
    contracting_entity: RefOut
    performing_entity: RefOut
    currency: str
    memo_1: str | None
    memo_2: str | None
    memo_3: str | None
    account_overrides: dict[str, RefOut]
    original: ObligationOriginalOut
    current: ObligationCurrentOut
    ssp: ObligationSspOut
    to_date: ObligationToDateOut
    remaining: ObligationRemainingOut
    scheduled: MoneyOut
    awaiting_trigger: MoneyOut
    ratios: ObligationRatiosOut
    position: PositionOut
    netting_reclass: NettingReclassOut
    satisfaction_status: str
    satisfied_date: date | None
    # 04 §16.2 rev 1.299 (item HOLD-RELEASE-READ-1): the obligation's own open holds, oldest
    # first — open NOW, whatever ``as_of`` and ``known_at`` the answer is read at: a hold is
    # released against the stream's head. The version reads list none (a hold is no fact of a
    # version). A contract-level hold is listed by API-S-Contract ``holds``.
    holds: list[HoldOut]
    material_right: dict[str, Any] | None
    context: ContextOut
    links: ObligationLinksOut


# --- API-S-ContractBalance, API-S-ContractVersion, API-S-AllocationWalk (04 §16.1) --------------


class ContractBalanceFunctionalOut(BaseModel):
    """The balance names in functional currency; null where T-CON-09 keeps no functional figure."""

    net_position: MoneyOut | None
    contract_liability: MoneyOut | None
    contract_liability_current: MoneyOut | None
    contract_asset: MoneyOut | None
    contract_asset_current: MoneyOut | None
    unbilled_receivable: MoneyOut | None
    accounts_receivable: MoneyOut | None
    refund_liability: MoneyOut | None
    return_asset: MoneyOut | None
    deposit_liability: MoneyOut | None
    customer_incentive_asset: MoneyOut | None
    consideration_payable: MoneyOut | None
    cost_asset_carrying: MoneyOut | None
    loss_provision: MoneyOut | None


class ContractBalanceOut(BaseModel):
    """API-S-ContractBalance: labelled balances of a member contract and entity at a version."""

    contract_id: uuid.UUID
    entity: RefOut
    book: BookCode
    net_position: MoneyOut
    contract_liability: MoneyOut
    contract_liability_current: MoneyOut
    contract_asset: MoneyOut
    contract_asset_current: MoneyOut
    unbilled_receivable: MoneyOut
    accounts_receivable: MoneyOut
    refund_liability: MoneyOut
    return_asset: MoneyOut
    deposit_liability: MoneyOut
    customer_incentive_asset: MoneyOut
    consideration_payable: MoneyOut
    cost_asset_carrying: MoneyOut
    loss_provision: MoneyOut
    functional: ContractBalanceFunctionalOut
    links: BalanceLinksOut = Field(default_factory=BalanceLinksOut)
    context: ContextOut


class CauseEventOut(BaseModel):
    id: uuid.UUID
    event_type: str
    effective_date: date
    recorded_at: datetime


class TransactionPriceBuildupOut(BaseModel):
    """REQ-TP-001 build-up of a contract version."""

    fixed: MoneyOut
    vc_constrained: MoneyOut
    vc_excluded: MoneyOut
    expected_returns: MoneyOut
    consideration_payable: MoneyOut
    financing_adjustment: MoneyOut
    noncash: MoneyOut
    sales_tax_excluded: MoneyOut
    out_of_scope: MoneyOut
    total: MoneyOut


class ContractVersionSummaryOut(BaseModel):
    """API-S-ContractVersion as a list item: without ``obligations`` and ``balances``."""

    id: uuid.UUID
    version_no: int
    book: BookCode
    known_at: datetime
    cause_events: list[CauseEventOut]
    engine_version: str
    input_sha256: str
    output_sha256: str
    status_in_book: ContractStatus
    status_reason_in_book: str | None
    transaction_price_buildup: TransactionPriceBuildupOut
    total_ssp: str
    revenue_to_date: MoneyOut
    billed_to_date: MoneyOut
    rpo: MoneyOut
    scheduled: MoneyOut
    awaiting_trigger: MoneyOut
    modification_boundary_no: int
    pinned_refs: dict[str, Any]
    pinned_policies: dict[str, Any]


class ContractVersionOut(ContractVersionSummaryOut):
    """API-S-ContractVersion (``GET /contracts/{id}/versions/{version_no}``)."""

    obligations: list[ObligationOut]
    balances: list[ContractBalanceOut]


class VersionRefOut(BaseModel):
    id: uuid.UUID
    version_no: int
    known_at: datetime


class VersionChangeOut(BaseModel):
    """One field whose value differs between two versions; ``obligation_key`` is null for a
    contract version field. Money values are amount strings at the currency's minor unit."""

    field: str
    obligation_key: str | None
    before: Any
    after: Any


class VersionCompareOut(BaseModel):
    """``GET /contracts/{id}/versions/compare`` (REQ-CON-014; L3-1-Q-39)."""

    book: BookCode
    from_version: VersionRefOut
    to_version: VersionRefOut
    changes: list[VersionChangeOut]


class SspVersionRefOut(BaseModel):
    id: uuid.UUID
    label: str | None


class AllocationLineOut(BaseModel):
    obligation_key: str
    product: RefOut
    ssp_book_version: SspVersionRefOut | None
    ssp_entry_id: uuid.UUID | None
    ssp_method: str | None
    low: str | None
    mid: str | None
    high: str | None
    stated_price: MoneyOut
    in_range: bool | None
    range_position: SspRangePosition | None
    outside_range_point: str | None
    selected_ssp: str
    weight: str
    exact_quota: str
    rounding_residue: str
    allocated: MoneyOut
    allocation_adjustment: MoneyOut


class AllocationTotalsOut(BaseModel):
    allocated: MoneyOut
    allocation_adjustment: MoneyOut


class AllocationWalkOut(BaseModel):
    """API-S-AllocationWalk (REQ-ALC-009)."""

    context: ContextOut
    transaction_price: MoneyOut
    total_ssp: str
    lines: list[AllocationLineOut]
    totals: AllocationTotalsOut


# --- API-S-ScheduleLine (04 §16.2) and API-S-ContractHistoryItem (§16.14) ------------------------


class SchedulePeriodOut(BaseModel):
    id: uuid.UUID
    period_key: str
    name: str
    end_date: date


class ScheduleLineLinksOut(BaseModel):
    explain: str


class ScheduleLineOut(BaseModel):
    """API-S-ScheduleLine."""

    id: uuid.UUID
    period: SchedulePeriodOut
    obligation_key: str | None
    schedule_kind: str
    line_type: str
    amount: MoneyOut
    cumulative_amount: MoneyOut
    quantity: str | None
    state: str
    entity: RefOut
    contract_version_id: uuid.UUID
    links: ScheduleLineLinksOut


class ContractHistoryItemOut(BaseModel):
    """API-S-ContractHistoryItem."""

    occurred_at: datetime
    kind: HistoryItemKind
    actor: ActorOut
    summary_key: str
    params: dict[str, Any]
    links: dict[str, str]


# --- activation (04 §16.1, §16.14 API-S-ActivationChecklist; BUILD_SPEC CTR-9) --------------------


class SubmitActivationIn(BaseModel):
    """``POST /contracts/{id}/submit-activation`` (04 §16.1)."""

    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=4000)


class ContractVoidRequestIn(BaseModel):
    """``POST /contracts/{id}/request-void`` (04 §16.1): a reason of the table 3.4-R subset and the
    preparer's comment (PRD J-26; REQ-CON-015)."""

    model_config = ConfigDict(extra="forbid")

    reason_code: ReasonCode
    comment: str = Field(min_length=1, max_length=4000)


class ContractVoidRequestedOut(BaseModel):
    """The 200 body of ``request-void``: the ``CONTRACT_VOID`` approval request (04 §16.1)."""

    approval_request_id: uuid.UUID


class ActivationChecklistItemOut(BaseModel):
    """One item of table 15.4-I."""

    code: str
    passed: bool
    detail: str | None


class ActivationChecklistOut(BaseModel):
    """API-S-ActivationChecklist, evaluated without storing."""

    items: list[ActivationChecklistItemOut]
    evaluated_at: datetime


def _default_codification() -> list[str]:
    return ["606-10-25-19", "606-10-25-21"]


class DistinctReviewIn(BaseModel):
    """``POST /contracts/{id}/obligations/{obligation_key}/distinct-review`` (04 §16.1; SCREENS
    R-17)."""

    model_config = ConfigDict(extra="forbid")

    distinctness: Distinctness
    rationale: str = Field(min_length=1, max_length=4000)
    codification_refs: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=_default_codification, max_length=50
    )
    integrates_into_obligation_key: str | None = Field(
        default=None, min_length=1, max_length=255, description="Required for nondistinct"
    )


class DistinctReviewOut(BaseModel):
    """The submitted ``POB_DISTINCT_OVERRIDE`` judgement record and its review request."""

    judgement_record_id: uuid.UUID
    approval_request_id: uuid.UUID | None
