"""Engine StrEnums mirroring docs/04-DATA_MODEL.md §3 (DG-ARC-09; BUILD_SPEC EKC-5).

One class per enumeration the engine reads, with the 04 values in 04 order and the class names of
``erev_api.enums``. The engine may not import ``erev_api`` (DG-LAY-03), so these classes are a
second mirror; ``tests/architecture/test_data_model_drift.py`` compares both with 04. Standard
library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from erev_engine.errors import EngineError

__all__ = [
    "AccountRole",
    "BookCode",
    "ComputationTrigger",
    "ContractEventType",
    "ContractStatus",
    "Distinctness",
    "FxLayerMovementKind",
    "JudgementTopic",
    "LicenceNature",
    "ModificationTreatment",
    "ObligationKind",
    "PeriodState",
    "PrincipalAgent",
    "RatableConvention",
    "RecognitionMethod",
    "RuleSetKind",
    "SatisfactionPattern",
    "SatisfactionStatus",
    "ScheduleKind",
    "ScheduleLineType",
    "ScopeFlag",
    "SspMethod",
    "SspQuantityUnit",
    "SspValueBasis",
    "SubledgerPostingKind",
    "WarrantyType",
]


class AccountRole(StrEnum):
    """E-01 ``account_role`` (04 §3.1)."""

    REVENUE = "REVENUE"
    CONTRACT_LIABILITY = "CONTRACT_LIABILITY"
    CONTRACT_ASSET = "CONTRACT_ASSET"
    UNBILLED_RECEIVABLE = "UNBILLED_RECEIVABLE"
    ACCOUNTS_RECEIVABLE = "ACCOUNTS_RECEIVABLE"
    BILLING_CLEARING = "BILLING_CLEARING"
    REFUND_LIABILITY = "REFUND_LIABILITY"
    RETURN_ASSET = "RETURN_ASSET"
    DEPOSIT_LIABILITY = "DEPOSIT_LIABILITY"
    CONSIDERATION_PAYABLE = "CONSIDERATION_PAYABLE"
    CUSTOMER_INCENTIVE_ASSET = "CUSTOMER_INCENTIVE_ASSET"
    COST_TO_OBTAIN_ASSET = "COST_TO_OBTAIN_ASSET"
    COST_TO_FULFILL_ASSET = "COST_TO_FULFILL_ASSET"
    CONTRACT_COST_AMORTIZATION = "CONTRACT_COST_AMORTIZATION"
    CONTRACT_COST_IMPAIRMENT = "CONTRACT_COST_IMPAIRMENT"
    LOSS_PROVISION = "LOSS_PROVISION"
    LOSS_EXPENSE = "LOSS_EXPENSE"
    WARRANTY_PROVISION = "WARRANTY_PROVISION"
    WARRANTY_EXPENSE = "WARRANTY_EXPENSE"
    INTEREST_INCOME = "INTEREST_INCOME"
    INTEREST_EXPENSE = "INTEREST_EXPENSE"
    FX_GAIN_LOSS = "FX_GAIN_LOSS"
    INTERCOMPANY_DUE_TO = "INTERCOMPANY_DUE_TO"
    INTERCOMPANY_DUE_FROM = "INTERCOMPANY_DUE_FROM"
    NONCASH_CONSIDERATION_ASSET = "NONCASH_CONSIDERATION_ASSET"
    SALES_TAX_PAYABLE = "SALES_TAX_PAYABLE"
    PRE_STANDARD_REVENUE = "PRE_STANDARD_REVENUE"
    ROUNDING = "ROUNDING"
    COST_OF_REVENUE = "COST_OF_REVENUE"
    CONTRACT_COST_CLEARING = "CONTRACT_COST_CLEARING"
    RECEIVABLE_CONTRA = "RECEIVABLE_CONTRA"
    RETAINED_EARNINGS = "RETAINED_EARNINGS"
    FINANCING_OBLIGATION = "FINANCING_OBLIGATION"


class BookCode(StrEnum):
    """E-02 ``book_code`` (04 §3.2)."""

    ASC606 = "ASC606"
    IFRS15 = "IFRS15"
    LEGACY = "LEGACY"


class ContractEventType(StrEnum):
    """E-03 ``contract_event_type`` (04 §3.3)."""

    CONTRACT_BOOKED = "CONTRACT_BOOKED"
    CONTRACT_ACTIVATED = "CONTRACT_ACTIVATED"
    COLLECTIBILITY_ASSESSED = "COLLECTIBILITY_ASSESSED"
    CONTRACT_CRITERIA_MET = "CONTRACT_CRITERIA_MET"
    CONTRACT_AMENDED = "CONTRACT_AMENDED"
    DELIVERY_RECORDED = "DELIVERY_RECORDED"
    PROGRESS_RECORDED = "PROGRESS_RECORDED"
    MILESTONE_ACHIEVED = "MILESTONE_ACHIEVED"
    USAGE_REPORTED = "USAGE_REPORTED"
    COST_INCURRED = "COST_INCURRED"
    BILLING_RECORDED = "BILLING_RECORDED"
    CREDIT_MEMO_RECORDED = "CREDIT_MEMO_RECORDED"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    RETURN_RECORDED = "RETURN_RECORDED"
    ESTIMATE_CHANGED = "ESTIMATE_CHANGED"
    MATERIAL_RIGHT_EXERCISED = "MATERIAL_RIGHT_EXERCISED"
    MATERIAL_RIGHT_EXPIRED = "MATERIAL_RIGHT_EXPIRED"
    HOLD_APPLIED = "HOLD_APPLIED"
    HOLD_RELEASED = "HOLD_RELEASED"
    PRE_STANDARD_REVENUE_RECORDED = "PRE_STANDARD_REVENUE_RECORDED"
    MANUAL_ADJUSTMENT_APPLIED = "MANUAL_ADJUSTMENT_APPLIED"
    CONTRACT_TERMINATED = "CONTRACT_TERMINATED"
    COMBINATION_CHANGED = "COMBINATION_CHANGED"
    OPENING_BALANCE_ESTABLISHED = "OPENING_BALANCE_ESTABLISHED"
    EVENT_VOIDED = "EVENT_VOIDED"
    CONTRACT_VOIDED = "CONTRACT_VOIDED"
    SIGNIFICANT_CHANGE_FLAGGED = "SIGNIFICANT_CHANGE_FLAGGED"
    LINE_ATTRIBUTES_CHANGED = "LINE_ATTRIBUTES_CHANGED"
    MEMO_UPDATED = "MEMO_UPDATED"
    REGROUPED = "REGROUPED"


class PeriodState(StrEnum):
    """E-04 ``period_state`` (04 §3.4)."""

    FUTURE = "future"
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"
    REOPENED = "reopened"
    PERMANENTLY_LOCKED = "permanently_locked"


class RecognitionMethod(StrEnum):
    """E-11 ``recognition_method`` (04 §3.4)."""

    POINT_IN_TIME = "POINT_IN_TIME"
    TIME_ELAPSED = "TIME_ELAPSED"
    UNITS_DELIVERED = "UNITS_DELIVERED"
    OUTPUT_PERCENT = "OUTPUT_PERCENT"
    MILESTONE = "MILESTONE"
    COST_TO_COST = "COST_TO_COST"
    LABOUR_HOURS = "LABOUR_HOURS"
    RIGHT_TO_INVOICE = "RIGHT_TO_INVOICE"
    COST_RECOVERY = "COST_RECOVERY"
    USAGE = "USAGE"
    ROYALTY = "ROYALTY"
    REDEMPTION_PATTERN = "REDEMPTION_PATTERN"
    MANUAL = "MANUAL"


class ContractStatus(StrEnum):
    """E-17 ``contract_status`` (04 §3.4)."""

    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    NOT_A_CONTRACT = "NOT_A_CONTRACT"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    TERMINATED = "TERMINATED"
    VOIDED = "VOIDED"


class ObligationKind(StrEnum):
    """E-18 ``obligation_kind`` (04 §3.4)."""

    STANDARD = "STANDARD"
    VC_LINE = "VC_LINE"
    MATERIAL_RIGHT = "MATERIAL_RIGHT"
    SERVICE_WARRANTY = "SERVICE_WARRANTY"
    CUSTODIAL = "CUSTODIAL"
    LICENCE = "LICENCE"
    SHIPPING = "SHIPPING"


class SatisfactionPattern(StrEnum):
    """E-19 ``satisfaction_pattern`` (04 §3.4)."""

    POINT_IN_TIME = "POINT_IN_TIME"
    OVER_TIME = "OVER_TIME"


class RatableConvention(StrEnum):
    """E-21 ``ratable_convention`` (04 §3.4)."""

    DAILY = "DAILY"
    MONTHLY_EVEN = "MONTHLY_EVEN"
    MID_MONTH = "MID_MONTH"


class SatisfactionStatus(StrEnum):
    """E-22 ``satisfaction_status`` (04 §3.4)."""

    UNSATISFIED = "UNSATISFIED"
    PARTIALLY_SATISFIED = "PARTIALLY_SATISFIED"
    SATISFIED = "SATISFIED"
    CANCELLED = "CANCELLED"


class ModificationTreatment(StrEnum):
    """E-23 ``modification_treatment`` (04 §3.4)."""

    SEPARATE_CONTRACT = "SEPARATE_CONTRACT"
    PROSPECTIVE = "PROSPECTIVE"
    CUMULATIVE_CATCH_UP = "CUMULATIVE_CATCH_UP"
    MIXED = "MIXED"
    LEGACY_PROSPECTIVE = "LEGACY_PROSPECTIVE"
    LEGACY_RETROSPECTIVE = "LEGACY_RETROSPECTIVE"
    LEGACY_POB_VC = "LEGACY_POB_VC"


class ScheduleKind(StrEnum):
    """E-27 ``schedule_kind`` (04 §3.4)."""

    REVENUE = "REVENUE"
    COST_AMORTIZATION = "COST_AMORTIZATION"
    FINANCING_INTEREST = "FINANCING_INTEREST"
    BILLING_PLAN = "BILLING_PLAN"
    LOSS_PROVISION_RELEASE = "LOSS_PROVISION_RELEASE"


class ScheduleLineType(StrEnum):
    """E-28 ``schedule_line_type`` (04 §3.4)."""

    NORMAL = "NORMAL"
    CATCH_UP = "CATCH_UP"
    TP_CHANGE = "TP_CHANGE"
    BREAKAGE = "BREAKAGE"
    ROYALTY = "ROYALTY"
    RETURN = "RETURN"
    MODIFICATION = "MODIFICATION"
    OPENING_BALANCE = "OPENING_BALANCE"


class SubledgerPostingKind(StrEnum):
    """E-31 ``subledger_posting_kind`` (04 §3.4)."""

    ENGINE_COMPUTE = "ENGINE_COMPUTE"
    CLOSE_RELEASE = "CLOSE_RELEASE"
    FX_REMEASUREMENT = "FX_REMEASUREMENT"
    NETTING_RECLASS = "NETTING_RECLASS"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"
    VOID_REVERSAL = "VOID_REVERSAL"


class SspMethod(StrEnum):
    """E-47 ``ssp_method`` (04 §3.4)."""

    OBSERVABLE = "observable"
    ADJUSTED_MARKET = "adjusted_market"
    COST_PLUS_MARGIN = "cost_plus_margin"
    RESIDUAL = "residual"
    LEGACY_RANGE = "legacy_range"
    FORMULA = "formula"


class SspValueBasis(StrEnum):
    """E-49 ``ssp_value_basis`` (04 §3.4; D-93 (4): the pricing basis a series product's SSP entry
    declares, T-REF-30 ``value_basis``)."""

    AMOUNT = "AMOUNT"
    PERCENT_OF_LIST = "PERCENT_OF_LIST"
    PER_INCREMENT = "PER_INCREMENT"
    PER_BOOKED_TERM = "PER_BOOKED_TERM"


class SspQuantityUnit(StrEnum):
    """E-131 ``ssp_quantity_unit`` (04 §3.4; D-97 (3): what a series line's ``quantity`` counts when
    its SSP entry is priced ``PER_INCREMENT``, T-REF-30 ``quantity_unit``; required on such an
    entry, never inferred from a quantity)."""

    SERVICE_UNITS = "SERVICE_UNITS"
    INCREMENTS = "INCREMENTS"


class RuleSetKind(StrEnum):
    """E-55 ``rule_set_kind`` (04 §3.4)."""

    POB_ASSIGNMENT = "POB_ASSIGNMENT"
    SSP_ASSIGNMENT = "SSP_ASSIGNMENT"
    APPROVAL_ROUTING = "APPROVAL_ROUTING"
    AUTO_APPROVAL = "AUTO_APPROVAL"
    COMBINATION_DETECTION = "COMBINATION_DETECTION"
    HOLD = "HOLD"
    DATA_QUALITY = "DATA_QUALITY"


class JudgementTopic(StrEnum):
    """E-56 ``judgement_topic`` (04 §3.4)."""

    NOT_A_CONTRACT = "NOT_A_CONTRACT"
    COLLECTIBILITY = "COLLECTIBILITY"
    CONTRACT_TERM = "CONTRACT_TERM"
    COMBINATION = "COMBINATION"
    POB_DISTINCT_OVERRIDE = "POB_DISTINCT_OVERRIDE"
    SERIES_CLASSIFICATION = "SERIES_CLASSIFICATION"
    PRINCIPAL_AGENT = "PRINCIPAL_AGENT"
    LICENCE_NATURE = "LICENCE_NATURE"
    WARRANTY_TYPE = "WARRANTY_TYPE"
    CONSTRAINT = "CONSTRAINT"
    SFC_ASSESSMENT = "SFC_ASSESSMENT"
    MODIFICATION_TREATMENT_OVERRIDE = "MODIFICATION_TREATMENT_OVERRIDE"
    SSP_OVERRIDE = "SSP_OVERRIDE"
    REPURCHASE_CLASSIFICATION = "REPURCHASE_CLASSIFICATION"
    ESTIMATE_VS_ERROR = "ESTIMATE_VS_ERROR"
    OTHER = "OTHER"
    BILL_AND_HOLD = "BILL_AND_HOLD"


class ScopeFlag(StrEnum):
    """E-77 ``scope_flag`` (04 §3.4)."""

    IN_SCOPE_606 = "IN_SCOPE_606"
    LEASE_842 = "LEASE_842"
    INSURANCE_944 = "INSURANCE_944"
    FINANCIAL_INSTRUMENT = "FINANCIAL_INSTRUMENT"
    GUARANTEE_460 = "GUARANTEE_460"
    CONTRIBUTION_958_605 = "CONTRIBUTION_958_605"
    NONFINANCIAL_ASSET_610_20 = "NONFINANCIAL_ASSET_610_20"
    ALTERNATIVE_REVENUE_980_605 = "ALTERNATIVE_REVENUE_980_605"
    COLLABORATION_808 = "COLLABORATION_808"


class FxLayerMovementKind(StrEnum):
    """E-86 ``fx_layer_movement_kind`` (04 §3.4)."""

    LIABILITY_LAYER_CREATED = "LIABILITY_LAYER_CREATED"
    LIABILITY_LAYER_CONSUMED = "LIABILITY_LAYER_CONSUMED"
    ASSET_LAYER_CREATED = "ASSET_LAYER_CREATED"
    ASSET_LAYER_SETTLED = "ASSET_LAYER_SETTLED"
    ASSET_LAYER_REMEASURED = "ASSET_LAYER_REMEASURED"
    LIABILITY_LAYER_REMEASURED = "LIABILITY_LAYER_REMEASURED"


class ComputationTrigger(StrEnum):
    """E-87 ``computation_trigger`` (04 §3.4)."""

    COMMAND = "COMMAND"
    REPLAY_VERIFY = "REPLAY_VERIFY"
    RESTATE = "RESTATE"
    UPGRADE_VALIDATE = "UPGRADE_VALIDATE"
    FX_REPUBLISH = "FX_REPUBLISH"
    POLICY_RERUN = "POLICY_RERUN"
    CLOSE_RELEASE = "CLOSE_RELEASE"
    MIGRATION = "MIGRATION"


class PrincipalAgent(StrEnum):
    """E-89 ``principal_agent`` (04 §3.4)."""

    PRINCIPAL = "PRINCIPAL"
    AGENT = "AGENT"
    NOT_ASSESSED = "NOT_ASSESSED"


class LicenceNature(StrEnum):
    """E-90 ``licence_nature`` (04 §3.4)."""

    FUNCTIONAL = "FUNCTIONAL"
    SYMBOLIC = "SYMBOLIC"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class WarrantyType(StrEnum):
    """E-91 ``warranty_type`` (04 §3.4)."""

    ASSURANCE = "ASSURANCE"
    SERVICE = "SERVICE"
    NONE = "NONE"


class Distinctness(StrEnum):
    """E-105 ``distinctness`` (04 §3.4)."""

    DISTINCT = "distinct"
    NONDISTINCT = "nondistinct"
    SERIES = "series"


# Legacy `Distinct or Nondistinct` flags (legacy 01 LM-SSP-03), exact strings only (REQ-POB-003).
_LEGACY_DISTINCTNESS: Final[Mapping[str, Distinctness]] = MappingProxyType(
    {"Distinct": Distinctness.DISTINCT, "Nondistinct": Distinctness.NONDISTINCT}
)


def legacy_distinctness(flag: object) -> Distinctness:
    """The E-105 literal of a legacy ``Distinct or Nondistinct`` flag (REQ-POB-003; TC-13).

    Only the exact strings ``Distinct`` and ``Nondistinct`` map. Any other value raises
    ``EngineError("SSP_DISTINCT_FLAG_INVALID")`` (04 table 15.4-A; DEVIATIONS DEV-025), so a row is
    refused and never dropped. The function is not in ``__all__``, which lists the StrEnum mirrors
    that ``tests/architecture/test_data_model_drift.py`` compares with 04.
    """
    found = _LEGACY_DISTINCTNESS.get(flag) if isinstance(flag, str) else None
    if found is None:
        raise EngineError(
            "SSP_DISTINCT_FLAG_INVALID",
            "the distinct flag is not exactly Distinct or Nondistinct",
            detail={"flag": flag if isinstance(flag, str) else type(flag).__qualname__},
        )
    return found
