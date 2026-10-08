"""Platform StrEnums mirroring docs/04-DATA_MODEL.md §3 (DG-ARC-09; BUILD_SPEC FND-7).

One class per enumeration E-01 to E-124 except the withdrawn E-35 and E-48, with the values in
04 order. Enumerations marked API only (E-111 to E-124) have no PostgreSQL type and carry
``API_ONLY = True``. The drift tests compare these classes with 04 and with ``pg_enum``.
"""

from __future__ import annotations

from enum import StrEnum, nonmember


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


class ApprovalRequestStatus(StrEnum):
    """E-05 ``approval_request_status`` (04 §3.4)."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    VOIDED = "VOIDED"
    WITHDRAWN = "WITHDRAWN"


class ApprovalStepStatus(StrEnum):
    """E-06 ``approval_step_status`` (04 §3.4)."""

    WAITING = "WAITING"
    ACTIVE = "ACTIVE"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"
    VOIDED = "VOIDED"


class ApprovalDecisionKind(StrEnum):
    """E-07 ``approval_decision_kind`` (04 §3.4)."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    AUTO_APPROVE = "AUTO_APPROVE"


class ApprovalSubjectType(StrEnum):
    """E-08 ``approval_subject_type`` (04 §3.4)."""

    SSP_BOOK_VERSION = "SSP_BOOK_VERSION"
    SSP_OVERRIDE = "SSP_OVERRIDE"
    CONTRACT_ACTIVATION = "CONTRACT_ACTIVATION"
    MODIFICATION = "MODIFICATION"
    MANUAL_EVENT = "MANUAL_EVENT"
    ESTIMATE_VERSION = "ESTIMATE_VERSION"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"
    REGISTRY_VERSION = "REGISTRY_VERSION"
    RULE_SET_VERSION = "RULE_SET_VERSION"
    POB_TEMPLATE_VERSION = "POB_TEMPLATE_VERSION"
    ACCOUNT_MAPPING_VERSION = "ACCOUNT_MAPPING_VERSION"
    FX_RATE_SET_VERSION = "FX_RATE_SET_VERSION"
    ROLE_CHANGE = "ROLE_CHANGE"
    ROLE_ASSIGNMENT = "ROLE_ASSIGNMENT"
    SOD_EXCEPTION = "SOD_EXCEPTION"
    PERIOD_LOCK = "PERIOD_LOCK"
    PERIOD_REOPEN = "PERIOD_REOPEN"
    IMPORT_COMMIT = "IMPORT_COMMIT"
    CONTRACT_VOID = "CONTRACT_VOID"
    COMBINATION_GROUP = "COMBINATION_GROUP"
    JUDGEMENT_RECORD = "JUDGEMENT_RECORD"
    JOURNAL_RUN = "JOURNAL_RUN"
    SUPPORT_GRANT = "SUPPORT_GRANT"
    AI_PROPOSAL_ACCEPTANCE = "AI_PROPOSAL_ACCEPTANCE"
    PRINCIPAL_AGENT_CHANGE = "PRINCIPAL_AGENT_CHANGE"
    ATTRIBUTE_CHANGE = "ATTRIBUTE_CHANGE"
    EXCEPTION_WAIVER = "EXCEPTION_WAIVER"
    MIGRATION_PROMOTION = "MIGRATION_PROMOTION"
    MAPPING_PROFILE_VERSION = "MAPPING_PROFILE_VERSION"
    POLICY_OVERRIDE = "POLICY_OVERRIDE"
    # 04 rev 1.72 (D-98 133 AMENDMENT 4): the 0071 replay order
    MIGRATION_SSP_REPLAY = "MIGRATION_SSP_REPLAY"
    # 04 rev 1.142 (supervisor rulings R-49 (a), R-86; lane SECFIX-IMP): the last E-08 member
    # — the 0094 replay order
    EVIDENCE_SHRED = "EVIDENCE_SHRED"
    STEP1_EVENT = "STEP1_EVENT"


class EstimateKind(StrEnum):
    """E-09 ``estimate_kind`` (04 §3.4)."""

    VARIABLE_CONSIDERATION = "VARIABLE_CONSIDERATION"
    RETURN_RATE = "RETURN_RATE"
    BREAKAGE = "BREAKAGE"
    EAC = "EAC"
    EXERCISE_LIKELIHOOD = "EXERCISE_LIKELIHOOD"
    IMPLICIT_PRICE_CONCESSION = "IMPLICIT_PRICE_CONCESSION"
    RENEWAL_EXPECTATION = "RENEWAL_EXPECTATION"
    ROYALTY_ACCRUAL = "ROYALTY_ACCRUAL"
    EXPECTED_PURCHASES = "EXPECTED_PURCHASES"
    SHARE_BASED_CONSIDERATION = "SHARE_BASED_CONSIDERATION"


class EstimateMethod(StrEnum):
    """E-10 ``estimate_method`` (04 §3.4)."""

    EXPECTED_VALUE = "EXPECTED_VALUE"
    MOST_LIKELY_AMOUNT = "MOST_LIKELY_AMOUNT"
    ENTERED_AMOUNT = "ENTERED_AMOUNT"
    RATE = "RATE"
    COST_BUILDUP = "COST_BUILDUP"


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


class ConfigStatus(StrEnum):
    """E-12 ``config_status`` (04 §3.4)."""

    DRAFT = "DRAFT"
    TESTED = "TESTED"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    VOIDED = "VOIDED"


class JobState(StrEnum):
    """E-13 ``job_state`` (04 §3.4)."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    SUCCEEDED_WITH_EXCEPTIONS = "SUCCEEDED_WITH_EXCEPTIONS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobKind(StrEnum):
    """E-14 ``job_kind`` (04 §3.4)."""

    CONTRACT_COMPUTE = "CONTRACT_COMPUTE"
    IMPORT_VALIDATE = "IMPORT_VALIDATE"
    IMPORT_DIFF = "IMPORT_DIFF"
    IMPORT_COMMIT = "IMPORT_COMMIT"
    CLOSE_RUN = "CLOSE_RUN"
    JOURNAL_RUN_CALCULATE = "JOURNAL_RUN_CALCULATE"
    JOURNAL_EXPORT = "JOURNAL_EXPORT"
    REPORT_RUN = "REPORT_RUN"
    EVIDENCE_PACK = "EVIDENCE_PACK"
    AUDIT_CHAIN_VERIFY = "AUDIT_CHAIN_VERIFY"
    SSP_CALCULATOR = "SSP_CALCULATOR"
    SYNC_RUN = "SYNC_RUN"
    TENANT_SNAPSHOT = "TENANT_SNAPSHOT"
    SANDBOX_RESET = "SANDBOX_RESET"
    MIGRATION_IMPORT = "MIGRATION_IMPORT"
    MIGRATION_RECONCILE = "MIGRATION_RECONCILE"
    REPLAY_VERIFY = "REPLAY_VERIFY"
    POLICY_SIMULATION = "POLICY_SIMULATION"
    FORECAST_RUN = "FORECAST_RUN"
    DEAL_PREVIEW = "DEAL_PREVIEW"
    AI_TASK = "AI_TASK"
    RETENTION_SWEEP = "RETENTION_SWEEP"
    OUTBOX_RELAY = "OUTBOX_RELAY"
    WEBHOOK_DELIVERY = "WEBHOOK_DELIVERY"
    EMAIL_DELIVERY = "EMAIL_DELIVERY"
    RECONCILIATION_GENERATE = "RECONCILIATION_GENERATE"
    PERIOD_OPEN_REDIRTY = "PERIOD_OPEN_REDIRTY"


class PrincipalKind(StrEnum):
    """E-15 ``principal_kind`` (04 §3.4)."""

    USER = "USER"
    API_CLIENT = "API_CLIENT"
    SYSTEM = "SYSTEM"
    OPERATOR = "OPERATOR"


class TenantKind(StrEnum):
    """E-16 ``tenant_kind`` (04 §3.4)."""

    PRODUCTION = "production"
    SANDBOX = "sandbox"


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


class OverTimeCriterion(StrEnum):
    """E-20 ``over_time_criterion`` (04 §3.4)."""

    OT_A = "OT_A"
    OT_B = "OT_B"
    OT_C = "OT_C"
    NOT_APPLICABLE = "NOT_APPLICABLE"


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


class ModificationTemplateMode(StrEnum):
    """E-24 ``modification_template_mode`` (04 §3.4)."""

    PROSPECTIVE = "prospective"
    RETROSPECTIVE = "retrospective"
    POB_PRICE_CHANGE = "pob_price_change"


class ModificationKind(StrEnum):
    """E-25 ``modification_kind`` (04 §3.4)."""

    ADD_OBLIGATION = "ADD_OBLIGATION"
    REMOVE_OBLIGATION = "REMOVE_OBLIGATION"
    QUANTITY_CHANGE = "QUANTITY_CHANGE"
    PRICE_CHANGE = "PRICE_CHANGE"
    TERM_CHANGE = "TERM_CHANGE"
    UPGRADE = "UPGRADE"
    DOWNGRADE = "DOWNGRADE"
    CO_TERM = "CO_TERM"
    RENEWAL = "RENEWAL"
    CANCELLATION = "CANCELLATION"
    TERMINATION = "TERMINATION"
    VC_CHANGE = "VC_CHANGE"
    OTHER = "OTHER"
    EARLY_RENEWAL = "EARLY_RENEWAL"


class ModificationStatus(StrEnum):
    """E-26 ``modification_status`` (04 §3.4)."""

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    VOIDED = "VOIDED"


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


class SubledgerEntryKind(StrEnum):
    """E-29 ``subledger_entry_kind`` (04 §3.4)."""

    REVENUE_RECOGNITION = "REVENUE_RECOGNITION"
    BILLING = "BILLING"
    CREDIT_MEMO = "CREDIT_MEMO"
    NETTING_RECLASS = "NETTING_RECLASS"
    NETTING_RECLASS_REVERSAL = "NETTING_RECLASS_REVERSAL"
    REFUND_LIABILITY = "REFUND_LIABILITY"
    RETURN_ASSET = "RETURN_ASSET"
    DEPOSIT = "DEPOSIT"
    CONSIDERATION_PAYABLE = "CONSIDERATION_PAYABLE"
    CONTRACT_COST_CAPITALIZATION = "CONTRACT_COST_CAPITALIZATION"
    CONTRACT_COST_AMORTIZATION = "CONTRACT_COST_AMORTIZATION"
    CONTRACT_COST_IMPAIRMENT = "CONTRACT_COST_IMPAIRMENT"
    LOSS_PROVISION = "LOSS_PROVISION"
    WARRANTY_ACCRUAL = "WARRANTY_ACCRUAL"
    FINANCING_INTEREST = "FINANCING_INTEREST"
    FX_REMEASUREMENT = "FX_REMEASUREMENT"
    FX_ROUNDING = "FX_ROUNDING"
    INTERCOMPANY = "INTERCOMPANY"
    PRE_STANDARD_REVENUE = "PRE_STANDARD_REVENUE"
    NONCASH_CONSIDERATION = "NONCASH_CONSIDERATION"
    SALES_TAX = "SALES_TAX"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"
    REVERSAL = "REVERSAL"
    RECEIVABLE_CONTRA = "RECEIVABLE_CONTRA"


class JeType(StrEnum):
    """E-30 ``je_type`` (04 §3.4)."""

    AUTOMATED = "automated"
    MANUAL = "manual"
    REVERSAL = "reversal"


class SubledgerPostingKind(StrEnum):
    """E-31 ``subledger_posting_kind`` (04 §3.4)."""

    ENGINE_COMPUTE = "ENGINE_COMPUTE"
    CLOSE_RELEASE = "CLOSE_RELEASE"
    FX_REMEASUREMENT = "FX_REMEASUREMENT"
    NETTING_RECLASS = "NETTING_RECLASS"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"
    VOID_REVERSAL = "VOID_REVERSAL"


class JournalRunMode(StrEnum):
    """E-32 ``journal_run_mode`` (04 §3.4)."""

    GROSS = "GROSS"
    DELTA = "DELTA"


class JournalRunGrain(StrEnum):
    """E-33 ``journal_run_grain`` (04 §3.4)."""

    ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS = (
        "ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS"
    )
    LEGACY_CONTRACT_POB = "LEGACY_CONTRACT_POB"
    CONTRACT_ACCOUNT_DIMENSIONS = "CONTRACT_ACCOUNT_DIMENSIONS"


class JournalState(StrEnum):
    """E-34 ``journal_state`` (04 §3.4)."""

    DRAFT = "draft"
    APPROVED = "approved"
    EXPORTED = "exported"
    ACKNOWLEDGED = "acknowledged"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PostingAckKind(StrEnum):
    """E-36 ``posting_ack_kind`` (04 §3.4)."""

    POSTED = "POSTED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"
    MANUAL_CONFIRMATION = "MANUAL_CONFIRMATION"


class GlAdapter(StrEnum):
    """E-37 ``gl_adapter`` (04 §3.4)."""

    CSV = "CSV"
    NETSUITE = "NETSUITE"
    QUICKBOOKS_ONLINE = "QUICKBOOKS_ONLINE"


class SourceSystem(StrEnum):
    """E-38 ``source_system`` (04 §3.4)."""

    LEGACY_TEMPLATE_V1 = "LEGACY_TEMPLATE_V1"
    CSV_V2 = "CSV_V2"
    API = "API"
    MANUAL_UI = "MANUAL_UI"
    SALESFORCE = "SALESFORCE"
    STRIPE = "STRIPE"
    NETSUITE = "NETSUITE"
    QUICKBOOKS_ONLINE = "QUICKBOOKS_ONLINE"
    LEGACY_DB = "LEGACY_DB"


class SourceObjectType(StrEnum):
    """E-39 ``source_object_type`` (04 §3.4)."""

    ORDER = "ORDER"
    INVOICE = "INVOICE"
    CREDIT_MEMO = "CREDIT_MEMO"
    USAGE = "USAGE"
    PAYMENT = "PAYMENT"
    CUSTOMER = "CUSTOMER"
    PRODUCT = "PRODUCT"
    SSP_ROW = "SSP_ROW"
    CONTRACT_SETUP_ROW = "CONTRACT_SETUP_ROW"
    PROGRESS_ROW = "PROGRESS_ROW"
    MODIFICATION_ROW = "MODIFICATION_ROW"
    GL_ACCOUNT = "GL_ACCOUNT"
    FX_RATE = "FX_RATE"
    LEGACY_CONTRACT_LIVE_ROW = "LEGACY_CONTRACT_LIVE_ROW"


class ImportStatus(StrEnum):
    """E-40 ``import_status`` (04 §3.4)."""

    UPLOADED = "UPLOADED"
    VALIDATING = "VALIDATING"
    INVALID = "INVALID"
    VALIDATED = "VALIDATED"
    DIFFING = "DIFFING"
    DIFF_READY = "DIFF_READY"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    COMMITTING = "COMMITTING"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ImportRowStatus(StrEnum):
    """E-41 ``import_row_status`` (04 §3.4)."""

    VALID = "VALID"
    WARNING = "WARNING"
    ERROR = "ERROR"
    BLANK = "BLANK"
    AGGREGATED = "AGGREGATED"


class ExceptionSource(StrEnum):
    """E-42 ``exception_source`` (04 §3.4)."""

    IMPORT = "IMPORT"
    SYNC = "SYNC"
    ENGINE = "ENGINE"
    CLOSE = "CLOSE"
    RECONCILIATION = "RECONCILIATION"
    JOURNAL = "JOURNAL"
    INTEGRATION = "INTEGRATION"
    DATA_QUALITY = "DATA_QUALITY"
    MIGRATION = "MIGRATION"
    ANOMALY = "ANOMALY"


class ExceptionSeverity(StrEnum):
    """E-43 ``exception_severity`` (04 §3.4)."""

    BLOCKING = "BLOCKING"
    WARNING = "WARNING"
    INFO = "INFO"


class ExceptionStatus(StrEnum):
    """E-44 ``exception_status`` (04 §3.4)."""

    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    WAIVED = "WAIVED"
    DISMISSED = "DISMISSED"


class HoldType(StrEnum):
    """E-45 ``hold_type`` (04 §3.4)."""

    RECOGNITION = "recognition"
    JOURNAL_EXPORT = "journal_export"


class HoldSource(StrEnum):
    """E-46 ``hold_source`` (04 §3.4)."""

    SYSTEM = "SYSTEM"
    USER_RULE = "USER_RULE"
    MANUAL = "MANUAL"


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


class CalendarPattern(StrEnum):
    """E-50 ``calendar_pattern`` (04 §3.4)."""

    MONTHLY = "MONTHLY"
    P445 = "P445"
    P454 = "P454"
    P544 = "P544"
    P13 = "P13"
    W5253 = "W5253"


class RateType(StrEnum):
    """E-51 ``rate_type`` (04 §3.4)."""

    SPOT = "spot"
    CLOSING = "closing"
    AVERAGE = "average"


class AccountType(StrEnum):
    """E-52 ``account_type`` (04 §3.4)."""

    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class RegistryCategory(StrEnum):
    """E-53 ``registry_category`` (04 §3.4)."""

    ACCOUNTING_POLICY = "ACCOUNTING_POLICY"
    PRACTICAL_EXPEDIENT = "PRACTICAL_EXPEDIENT"
    DISCLOSURE_ELECTION = "DISCLOSURE_ELECTION"
    CLOSE = "CLOSE"
    PLATFORM = "PLATFORM"
    SECURITY = "SECURITY"
    AI = "AI"
    INTEGRATION = "INTEGRATION"


class RegistryScope(StrEnum):
    """E-54 ``registry_scope`` (04 §3.4)."""

    TENANT = "TENANT"
    ENTITY = "ENTITY"
    BOOK = "BOOK"
    PRODUCT = "PRODUCT"
    CONTRACT = "CONTRACT"
    OBLIGATION = "OBLIGATION"


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


class JudgementStatus(StrEnum):
    """E-57 ``judgement_status`` (04 §3.4)."""

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    REVIEWED = "REVIEWED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    VOIDED = "VOIDED"  # a discarded draft (04 rev 1.242; revision 0118)


class ReconciliationKind(StrEnum):
    """E-58 ``reconciliation_kind`` (04 §3.4)."""

    BILLING_TO_SUBLEDGER = "BILLING_TO_SUBLEDGER"
    SUBLEDGER_TO_GL = "SUBLEDGER_TO_GL"
    CONTRACT_BALANCE_ROLLFORWARD = "CONTRACT_BALANCE_ROLLFORWARD"
    RPO_ROLLFORWARD = "RPO_ROLLFORWARD"
    MIGRATION_OPENING_BALANCE = "MIGRATION_OPENING_BALANCE"


class ReconciliationStatus(StrEnum):
    """E-59 ``reconciliation_status`` (04 §3.4)."""

    DRAFT = "DRAFT"
    PREPARED = "PREPARED"
    AUTO_CERTIFIED = "AUTO_CERTIFIED"
    REVIEWED = "REVIEWED"
    CERTIFIED = "CERTIFIED"
    REOPENED = "REOPENED"


class ChecklistStatus(StrEnum):
    """E-60 ``checklist_status`` (04 §3.4)."""

    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    PASSED = "PASSED"
    FAILED = "FAILED"
    WAIVED = "WAIVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ChecklistGateKind(StrEnum):
    """E-61 ``checklist_gate_kind`` (04 §3.4)."""

    AUTOMATIC = "AUTOMATIC"
    MANUAL = "MANUAL"


class CloseRunStatus(StrEnum):
    """E-62 ``close_run_status`` (04 §3.4)."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class LockKind(StrEnum):
    """E-63 ``lock_kind`` (04 §3.4)."""

    LOCK = "LOCK"
    REOPEN = "REOPEN"
    PERMANENT_LOCK = "PERMANENT_LOCK"


class SnapshotKind(StrEnum):
    """E-64 ``snapshot_kind`` (04 §3.4)."""

    WATERFALL = "WATERFALL"
    CONTRACT_BALANCES = "CONTRACT_BALANCES"
    CONTRACT_BALANCE_ROLLFORWARD = "CONTRACT_BALANCE_ROLLFORWARD"
    RPO = "RPO"
    RPO_ROLLFORWARD = "RPO_ROLLFORWARD"
    DISAGGREGATION = "DISAGGREGATION"
    PRIOR_PERIOD_POB_REVENUE = "PRIOR_PERIOD_POB_REVENUE"
    COST_ROLLFORWARD = "COST_ROLLFORWARD"
    JE_POPULATION = "JE_POPULATION"
    OUT_OF_PERIOD_REGISTER = "OUT_OF_PERIOD_REGISTER"
    MODIFICATION_REGISTER = "MODIFICATION_REGISTER"
    MANUAL_ADJUSTMENT_REGISTER = "MANUAL_ADJUSTMENT_REGISTER"


class DisclosureKind(StrEnum):
    """E-65 ``disclosure_kind`` (04 §3.4)."""

    RPO = "RPO"
    CONTRACT_BALANCE_ROLLFORWARD = "CONTRACT_BALANCE_ROLLFORWARD"
    REVENUE_FROM_OPENING_LIABILITY = "REVENUE_FROM_OPENING_LIABILITY"
    PRIOR_PERIOD_POB_REVENUE = "PRIOR_PERIOD_POB_REVENUE"
    DISAGGREGATION = "DISAGGREGATION"
    COST_ROLLFORWARD = "COST_ROLLFORWARD"
    EXPEDIENTS_USED = "EXPEDIENTS_USED"


class EvidencePackKind(StrEnum):
    """E-66 ``evidence_pack_kind`` (04 §3.4)."""

    CLOSE = "CLOSE"
    CONTRACT_SAMPLE = "CONTRACT_SAMPLE"
    CHANGE = "CHANGE"
    ACCESS = "ACCESS"


class RunStatus(StrEnum):
    """E-67 ``run_status`` (04 §3.4)."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class FilePurpose(StrEnum):
    """E-68 ``file_purpose`` (04 §3.4)."""

    IMPORT_SOURCE = "IMPORT_SOURCE"
    ATTACHMENT = "ATTACHMENT"
    SSP_STUDY = "SSP_STUDY"
    REPORT_OUTPUT = "REPORT_OUTPUT"
    EVIDENCE_PACK = "EVIDENCE_PACK"
    JOURNAL_EXPORT = "JOURNAL_EXPORT"
    LEGACY_DATABASE = "LEGACY_DATABASE"
    SNAPSHOT_DATASET = "SNAPSHOT_DATASET"
    IMPACT_PREVIEW = "IMPACT_PREVIEW"
    AI_PROMPT_LOG = "AI_PROMPT_LOG"
    AUDIT_DIGEST = "AUDIT_DIGEST"
    POSTING_RESPONSE = "POSTING_RESPONSE"
    AI_DOCUMENT_TEXT = "AI_DOCUMENT_TEXT"


class NotificationKind(StrEnum):
    """E-69 ``notification_kind`` (04 §3.4)."""

    APPROVAL_ASSIGNED = "APPROVAL_ASSIGNED"
    ITEM_REJECTED = "ITEM_REJECTED"
    APPROVAL_VOIDED = "APPROVAL_VOIDED"
    JOB_FAILED = "JOB_FAILED"
    CLOSE_BLOCKER_RAISED = "CLOSE_BLOCKER_RAISED"
    CHAIN_VERIFICATION_FAILED = "CHAIN_VERIFICATION_FAILED"
    EXPORT_FAILED = "EXPORT_FAILED"
    EXCEPTION_ASSIGNED = "EXCEPTION_ASSIGNED"
    SUPPORT_GRANT_REQUESTED = "SUPPORT_GRANT_REQUESTED"
    ITEM_APPROVED = "ITEM_APPROVED"
    PERIOD_LOCKED = "PERIOD_LOCKED"
    PERIOD_REOPENED = "PERIOD_REOPENED"
    APPROVAL_UNASSIGNED = "APPROVAL_UNASSIGNED"


class OutboxTopic(StrEnum):
    """E-70 ``outbox_topic`` (04 §3.4)."""

    JOURNAL_EXPORT = "JOURNAL_EXPORT"
    WEBHOOK = "WEBHOOK"
    EMAIL = "EMAIL"
    SYNC_REQUEST = "SYNC_REQUEST"


class OutboxStatus(StrEnum):
    """E-71 ``outbox_status`` (04 §3.4)."""

    PENDING = "PENDING"
    DISPATCHING = "DISPATCHING"
    DISPATCHED = "DISPATCHED"
    FAILED = "FAILED"
    DEAD = "DEAD"


class SyncRunStatus(StrEnum):
    """E-72 ``sync_run_status`` (04 §3.4)."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    CONTROL_TOTAL_MISMATCH = "CONTROL_TOTAL_MISMATCH"
    FAILED = "FAILED"


class AiProposalKind(StrEnum):
    """E-73 ``ai_proposal_kind`` (04 §3.4)."""

    CONTRACT_EXTRACTION = "CONTRACT_EXTRACTION"
    NUMBER_EXPLANATION = "NUMBER_EXPLANATION"
    ANOMALY_FLAG = "ANOMALY_FLAG"
    QA_ANSWER = "QA_ANSWER"


class AiProposalStatus(StrEnum):
    """E-74 ``ai_proposal_status`` (04 §3.4)."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    FAILED = "failed"


class MigrationMode(StrEnum):
    """E-75 ``migration_mode`` (04 §3.4)."""

    OPENING_BALANCES = "OPENING_BALANCES"
    REPLAY = "REPLAY"


class MigrationStatus(StrEnum):
    """E-76 ``migration_status`` (04 §3.4)."""

    UPLOADED = "UPLOADED"
    PROFILING = "PROFILING"
    PROFILED = "PROFILED"
    IMPORTING = "IMPORTING"
    IMPORTED = "IMPORTED"
    RECONCILED = "RECONCILED"
    SUBMITTED = "SUBMITTED"
    PROMOTED = "PROMOTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


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


class MembershipStatus(StrEnum):
    """E-78 ``membership_status`` (04 §3.4)."""

    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REMOVED = "REMOVED"


class SecurityEventKind(StrEnum):
    """E-79 ``security_event_kind`` (04 §3.4)."""

    LOGIN_SUCCEEDED = "LOGIN_SUCCEEDED"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    MFA_ENROLLED = "MFA_ENROLLED"
    MFA_RESET = "MFA_RESET"
    MFA_CHALLENGE_FAILED = "MFA_CHALLENGE_FAILED"
    RECOVERY_CODE_USED = "RECOVERY_CODE_USED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    TENANT_SELECTED = "TENANT_SELECTED"
    OIDC_LINKED = "OIDC_LINKED"
    PLATFORM_SCOPE_USED = "PLATFORM_SCOPE_USED"
    PASSWORD_RESET_REQUESTED = "PASSWORD_RESET_REQUESTED"
    PASSWORD_RESET_COMPLETED = "PASSWORD_RESET_COMPLETED"
    INVITATION_LOOKUP_FAILED = "INVITATION_LOOKUP_FAILED"
    MFA_ENROLMENT_STARTED = "MFA_ENROLMENT_STARTED"
    RECOVERY_CODES_REGENERATED = "RECOVERY_CODES_REGENERATED"
    MFA_CHALLENGE_PASSED = "MFA_CHALLENGE_PASSED"
    MFA_PENDING_DENIED = "MFA_PENDING_DENIED"


class IdentityProviderKind(StrEnum):
    """E-80 ``identity_provider_kind`` (04 §3.4)."""

    PASSWORD = "password"
    OIDC = "oidc"
    SAML = "saml"


class AuditOutcome(StrEnum):
    """E-81 ``audit_outcome`` (04 §3.4)."""

    SUCCESS = "SUCCESS"
    DENIED = "DENIED"
    FAILED = "FAILED"


class ReportingEntityType(StrEnum):
    """E-82 ``reporting_entity_type`` (04 §3.4)."""

    PBE = "PBE"
    NFP_CONDUIT = "NFP_CONDUIT"
    EBP_SEC = "EBP_SEC"
    NONPUBLIC = "NONPUBLIC"


class CostKind(StrEnum):
    """E-83 ``cost_kind`` (04 §3.4)."""

    OBTAIN = "OBTAIN"
    FULFILL = "FULFILL"


class AmortizationPattern(StrEnum):
    """E-84 ``amortization_pattern`` (04 §3.4)."""

    STRAIGHT_LINE = "STRAIGHT_LINE"
    PROPORTIONAL_TO_RELATED_REVENUE = "PROPORTIONAL_TO_RELATED_REVENUE"


class LossUnit(StrEnum):
    """E-85 ``loss_unit`` (04 §3.4)."""

    CONTRACT = "CONTRACT"
    POB = "POB"


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


class ComputationStatus(StrEnum):
    """E-88 ``computation_status`` (04 §3.4)."""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"


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


class OptionType(StrEnum):
    """E-92 ``option_type`` (04 §3.4)."""

    DISCOUNT_VOUCHER = "DISCOUNT_VOUCHER"
    LOYALTY_POINTS = "LOYALTY_POINTS"
    RENEWAL_OPTION = "RENEWAL_OPTION"
    TIERED_DISCOUNT = "TIERED_DISCOUNT"
    OTHER = "OTHER"


class ManualAdjustmentKind(StrEnum):
    """E-93 ``manual_adjustment_kind`` (04 §3.4)."""

    SCHEDULE_OVERRIDE = "SCHEDULE_OVERRIDE"
    MANUAL_RELEASE = "MANUAL_RELEASE"
    MANUAL_DEFER = "MANUAL_DEFER"
    MANUAL_JOURNAL = "MANUAL_JOURNAL"
    ACCOUNT_RECLASS = "ACCOUNT_RECLASS"


class ManualAdjustmentStatus(StrEnum):
    """E-94 ``manual_adjustment_status`` (04 §3.4)."""

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    POSTED = "POSTED"
    REJECTED = "REJECTED"
    VOIDED = "VOIDED"


class CombinationStatus(StrEnum):
    """E-95 ``combination_status`` (04 §3.4)."""

    PROPOSED = "PROPOSED"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    VOIDED = "VOIDED"


class GrantStatus(StrEnum):
    """E-96 ``grant_status`` (04 §3.4)."""

    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class WebhookDeliveryStatus(StrEnum):
    """E-97 ``webhook_delivery_status`` (04 §3.4)."""

    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ABANDONED = "ABANDONED"


class ControlResult(StrEnum):
    """E-98 ``control_result`` (04 §3.4)."""

    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SignoffRole(StrEnum):
    """E-99 ``signoff_role`` (04 §3.4)."""

    PREPARER = "PREPARER"
    REVIEWER = "REVIEWER"
    CONTROLLER = "CONTROLLER"


class ScenarioStatus(StrEnum):
    """E-100 ``scenario_status`` (04 §3.4)."""

    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class TenantStatus(StrEnum):
    """E-101 ``tenant_status`` (04 §3.4)."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"


class UserStatus(StrEnum):
    """E-102 ``user_status`` (04 §3.4)."""

    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"
    DISABLED = "DISABLED"


class ApiClientStatus(StrEnum):
    """E-103 ``api_client_status`` (04 §3.4). ``PENDING_APPROVAL`` and ``REJECTED`` (rev 1.168;
    supervisor ruling R-38 (iii)): a client whose scopes wait for their approval, and one whose
    request was rejected, withdrawn or voided. Only ``ACTIVE`` authenticates."""

    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    REJECTED = "REJECTED"


class SessionEndReason(StrEnum):
    """E-104 ``session_end_reason`` (04 §3.4)."""

    LOGOUT = "LOGOUT"
    IDLE_TIMEOUT = "IDLE_TIMEOUT"
    ABSOLUTE_TIMEOUT = "ABSOLUTE_TIMEOUT"
    REVOKED = "REVOKED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"


class Distinctness(StrEnum):
    """E-105 ``distinctness`` (04 §3.4)."""

    DISTINCT = "distinct"
    NONDISTINCT = "nondistinct"
    SERIES = "series"


class ExceptionDisposition(StrEnum):
    """E-106 ``exception_disposition`` (04 §3.4)."""

    REMEDIABLE = "remediable"
    DISCARDED = "discarded"


class AccessReviewStatus(StrEnum):
    """E-107 ``access_review_status`` (04 §3.4)."""

    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class AccessReviewDecision(StrEnum):
    """E-108 ``access_review_decision`` (04 §3.4)."""

    PENDING = "PENDING"
    CERTIFIED = "CERTIFIED"
    REVOKE_REQUESTED = "REVOKE_REQUESTED"
    REVOKED = "REVOKED"


class ClearingPurpose(StrEnum):
    """E-109 ``clearing_purpose`` (04 §3.4)."""

    BILLING = "BILLING"
    UNAPPLIED_CASH = "UNAPPLIED_CASH"
    AP_SUPPLIER = "AP_SUPPLIER"
    INVENTORY = "INVENTORY"
    EQUITY = "EQUITY"
    INVESTMENTS = "INVESTMENTS"


class ReasonCode(StrEnum):
    """E-110 ``reason_code`` (04 §3.4)."""

    DUPLICATE = "DUPLICATE"
    CREATED_IN_ERROR = "CREATED_IN_ERROR"
    CUSTOMER_CANCELLED = "CUSTOMER_CANCELLED"
    DATA_CORRECTION = "DATA_CORRECTION"
    ESTIMATE_CORRECTION = "ESTIMATE_CORRECTION"
    OTHER = "OTHER"
    ERROR_CORRECTION = "ERROR_CORRECTION"
    LATE_SOURCE_DATA = "LATE_SOURCE_DATA"
    AUDIT_ADJUSTMENT = "AUDIT_ADJUSTMENT"
    CLOSE_RESTARTED = "CLOSE_RESTARTED"
    DATA_CORRECTION_PENDING = "DATA_CORRECTION_PENDING"


class ContractQuickList(StrEnum):
    """E-111 ``contract_quick_list`` (04 §3.4; API only)."""

    API_ONLY = nonmember(True)

    RECENTLY_VIEWED = "RECENTLY_VIEWED"
    ON_HOLD = "ON_HOLD"
    LARGEST_VALUE = "LARGEST_VALUE"
    MODIFIED_THIS_PERIOD = "MODIFIED_THIS_PERIOD"
    CREATED_MANUALLY = "CREATED_MANUALLY"
    CREATED_FROM_INTEGRATIONS_THIS_PERIOD = "CREATED_FROM_INTEGRATIONS_THIS_PERIOD"


class ContractStep(StrEnum):
    """E-112 ``contract_step`` (04 §3.4; API only)."""

    API_ONLY = nonmember(True)

    CONTRACT = "CONTRACT"
    OBLIGATIONS = "OBLIGATIONS"
    TRANSACTION_PRICE = "TRANSACTION_PRICE"
    ALLOCATION = "ALLOCATION"
    RECOGNITION = "RECOGNITION"


class ContractStepState(StrEnum):
    """E-113 ``contract_step_state`` (04 §3.4; API only)."""

    API_ONLY = nonmember(True)

    COMPLETE = "COMPLETE"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    BLOCKED = "BLOCKED"
    IN_REVIEW = "IN_REVIEW"
    NOT_STARTED = "NOT_STARTED"


class SspRangePosition(StrEnum):
    """E-114 ``ssp_range_position`` (04 §3.4; API only)."""

    API_ONLY = nonmember(True)

    INSIDE = "INSIDE"
    BELOW = "BELOW"
    ABOVE = "ABOVE"


class MaterialRightStatus(StrEnum):
    """E-115 ``material_right_status`` (04 §3.4; API only)."""

    API_ONLY = nonmember(True)

    OPEN = "OPEN"
    EXERCISED = "EXERCISED"
    EXPIRED = "EXPIRED"


class HistoryItemKind(StrEnum):
    """E-116 ``history_item_kind`` (04 §3.4; API only)."""

    API_ONLY = nonmember(True)

    EVENT = "EVENT"
    CALCULATION = "CALCULATION"
    APPROVAL = "APPROVAL"
    IMPORT = "IMPORT"


class ExceptionAction(StrEnum):
    """E-117 ``exception_action`` (04 §3.4; API only)."""

    API_ONLY = nonmember(True)

    ASSIGN = "ASSIGN"
    REPROCESS = "REPROCESS"
    RESOLVE = "RESOLVE"
    REQUEST_WAIVER = "REQUEST_WAIVER"
    DISMISS = "DISMISS"


class ImportDiffChange(StrEnum):
    """E-118 ``import_diff_change`` (04 §3.4; API only)."""

    API_ONLY = nonmember(True)

    ADDED = "ADDED"
    CHANGED = "CHANGED"


class HeaderMatchKind(StrEnum):
    """E-119 ``header_match_kind`` (04 §3.4; API only)."""

    API_ONLY = nonmember(True)

    EXACT = "EXACT"
    ALIAS = "ALIAS"
    NOT_MAPPED = "NOT_MAPPED"
    MISSING = "MISSING"


class SearchScope(StrEnum):
    """E-120 ``search_scope`` (04 §3.4; API only)."""

    API_ONLY = nonmember(True)

    CONTRACTS = "contracts"
    CUSTOMERS = "customers"
    INVOICES = "invoices"
    OBLIGATIONS = "obligations"
    JOURNALS = "journals"


class AiFieldDecision(StrEnum):
    """E-121 ``ai_field_decision`` (04 §3.4; API only)."""

    API_ONLY = nonmember(True)

    ACCEPT = "ACCEPT"
    EDIT = "EDIT"
    REJECT = "REJECT"


class DerivedBlockerCode(StrEnum):
    """E-122 ``derived_blocker_code`` (04 §3.4; API only)."""

    API_ONLY = nonmember(True)

    JOURNAL_RUN_NOT_CALCULATED = "JOURNAL_RUN_NOT_CALCULATED"
    RECONCILIATIONS_NOT_GENERATED = "RECONCILIATIONS_NOT_GENERATED"


class UiTheme(StrEnum):
    """E-123 ``ui_theme`` (04 §3.4; API only)."""

    API_ONLY = nonmember(True)

    SYSTEM = "SYSTEM"
    LIGHT = "LIGHT"
    DARK = "DARK"


class UiDensity(StrEnum):
    """E-124 ``ui_density`` (04 §3.4; API only)."""

    API_ONLY = nonmember(True)

    COMFORTABLE = "COMFORTABLE"
    COMPACT = "COMPACT"


class VerificationOutcome(StrEnum):
    """E-125 ``verification_outcome`` (04 §3.4; T-CON-26; D-96)."""

    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    DIFFERENCES = "DIFFERENCES"
    UNVERIFIABLE = "UNVERIFIABLE"
    NO_SOURCE = "NO_SOURCE"
    ERROR = "ERROR"


class ReleaseValidationStatus(StrEnum):
    """E-126 ``release_validation_status`` (04 §3.4; T-PLT-43; D-96)."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    INCOMPLETE = "INCOMPLETE"
    PASSED = "PASSED"
    FAILED = "FAILED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ValidationAttemptStatus(StrEnum):
    """E-127 ``validation_attempt_status`` (04 §3.4; T-PLT-44; D-96)."""

    SELECTED = "SELECTED"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    SUPERSEDED = "SUPERSEDED"


class PostingAttributionCause(StrEnum):
    """E-128 ``posting_attribution_cause`` (04 §3.4; T-SL-11; D-96 (F))."""

    UPGRADE_CONTEXT = "UPGRADE_CONTEXT"
    UPGRADE_ONLY = "UPGRADE_ONLY"
    UPGRADE_AND_OTHER_INPUTS = "UPGRADE_AND_OTHER_INPUTS"


class ValidationGroupOrchestrationState(StrEnum):
    """E-129 ``validation_group_orchestration_state`` (04 §3.4; T-PLT-45; D-96 (B))."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRYABLE = "RETRYABLE"
    COMPLETE = "COMPLETE"
    FAILED_EXHAUSTED = "FAILED_EXHAUSTED"
    CANCELLED = "CANCELLED"


class UpgradeProcessingState(StrEnum):
    """E-130 ``upgrade_processing_state`` (04 §3.4; T-PLT-46; D-96 (E))."""

    PENDING = "PENDING"
    DEFERRED_NO_OPEN_PERIOD = "DEFERRED_NO_OPEN_PERIOD"
    SETTLED_NO_POSTING = "SETTLED_NO_POSTING"
    POSTED = "POSTED"


class Step1GateReason(StrEnum):
    """E-132 ``step1_gate_reason`` (04 §3.4; API only): why the not-a-contract gate did not follow
    a not-probable assessment of a DRAFT contract (supervisor rulings R-77 (6), R-84 (b))."""

    API_ONLY = nonmember(True)

    BOOK_NOT_ASSESSED = "BOOK_NOT_ASSESSED"
    GROUP_TOO_LARGE = "GROUP_TOO_LARGE"
    ENGINE_REFUSED = "ENGINE_REFUSED"
    BOOK_NOT_CONFIRMED = "BOOK_NOT_CONFIRMED"
