"""Pydantic models of the answer-key YAML schema (docs/dev-guide.md §9.5.2 to §9.5.6; EKC-8).

Every model forbids members that its §9.5 table does not name (``extra="forbid"``). The loader
keeps every scalar except null and bool as a string (DG-AK-31), so decimals, dates and money stay
exact strings here and integer fields are converted from digit strings.

Members whose member set another document owns are typed mappings: timeline ``payload`` (04 §16.3),
obligation value columns (T-CON-11), policy values (POLICIES §1), questionnaires (T-CON-06,
T-CON-19), estimate ``parameters`` (T-CON-13), rule ``conditions`` and ``outputs`` (T-REF-26) and
report ``parameters``. Enumeration literals owned by 04 §3 are strings. The cross-validation of
DG-AK-32 checks those against their owners (EKC-9).
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    JsonValue,
    StrictBool,
    StrictStr,
    Tag,
    model_validator,
)

SCHEMA_ID = "erev-answer-key/1"
FAMILY_CODES = (
    "RND", "SSP", "ALC", "STP1", "POB", "VC", "RET", "MR", "BRK", "SFC", "NCC", "CPC", "TAX",
    "IFRS", "REC", "ROY", "MOD", "POS", "JE", "DLT", "FX", "ENT", "COST", "LOSS", "LATE", "DISC",
    "ONB", "PAR",
)  # fmt: skip
KEY_ID_PATTERN = (
    r"^(RND|SSP|ALC|STP1|POB|VC|RET|MR|BRK|SFC|NCC|CPC|TAX|IFRS|REC|ROY|MOD|POS|JE|DLT|FX|ENT|COST"
    r"|LOSS|LATE|DISC|ONB|PAR)-[A-Z0-9][A-Z0-9-]{0,78}[A-Z0-9]$"
)
# B3-DG-17: estimate kinds and VC element types whose absent `direction` derives DECREASE.
DECREASE_ESTIMATE_KINDS = frozenset({"IMPLICIT_PRICE_CONCESSION"})
DECREASE_VC_ELEMENT_TYPES = frozenset({
    "IMPLICIT_PRICE_CONCESSION", "REBATE", "VOLUME_TIER", "PRICE_PROTECTION", "SLA_CREDIT",
    "DISCOUNT", "RETURN", "REFUND", "PENALTY",
})  # fmt: skip

_DIGITS = re.compile(r"[0-9]+")


def _digits(value: object) -> object:
    """Integer fields arrive as digit strings (DG-AK-31); anything else fails validation."""
    if isinstance(value, str) and _DIGITS.fullmatch(value):
        return int(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise ValueError("expected a digit string")


Text = StrictStr
Flag = StrictBool
DigitInt = Annotated[int, BeforeValidator(_digits)]
RecordedAt = Annotated[
    StrictStr, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
]
FamilyCode = Literal[
    "RND", "SSP", "ALC", "STP1", "POB", "VC", "RET", "MR", "BRK", "SFC", "NCC", "CPC", "TAX",
    "IFRS", "REC", "ROY", "MOD", "POS", "JE", "DLT", "FX", "ENT", "COST", "LOSS", "LATE", "DISC",
    "ONB", "PAR",
]  # fmt: skip
Scalar = StrictStr | StrictBool
# §9.5.3 value shapes: an option literal, a list of literals, or an object of string members.
PolicyValue = StrictStr | tuple[StrictStr, ...] | dict[str, StrictStr]
PolicyValues = dict[str, PolicyValue]
AccountCodes = dict[str, StrictStr]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MoneyAmount(Model):
    """§9.5.4: a money field written as ``{amount, currency}``; a bare string uses the context."""

    amount: Text
    currency: Text


Money = StrictStr | MoneyAmount


def _exactly_one(values: dict[str, Any], names: tuple[str, str], context: str) -> None:
    present = [name for name in names if values.get(name) is not None]
    if len(present) != 1:
        raise ValueError(f"{context} carries exactly one of {' and '.join(names)}")


# §9.5.2 top-level members


class Authority(Model):
    codification: tuple[Text, ...]
    ifrs: tuple[Text, ...]
    practice: tuple[Text, ...]
    urls: tuple[Text, ...]


class DerivedFrom(Model):
    research04: tuple[Text, ...] = ()
    research05: tuple[Text, ...] = ()
    chk: tuple[Text, ...] = ()
    golden: tuple[Text, ...] = ()
    dev: tuple[Text, ...] = ()


class Review(Model):
    author: Text
    authored_on: Text
    reviewer: Text | None
    reviewed_on: Text | None
    status: Literal["pending", "approved", "changes_requested"]


# §9.5.3 world


class Tenant(Model):
    reporting_currency: Text
    preset: Literal["DEFAULT", "LEGACY_PARITY"]


class Calendar(Model):
    pattern: Text
    fiscal_year_start_month: DigitInt
    week_end_day: Text | None = None
    year_end_anchor: Text | None = None


class Entity(Model):
    code: Text
    name: Text
    functional_currency: Text
    time_zone: Text
    calendar: Calendar
    books: tuple[Text, ...] = Field(min_length=1)
    parent_code: Text | None = None


class Periods(Model):
    model_config = ConfigDict(populate_by_name=True)

    from_: Text = Field(alias="from", pattern=r"^[0-9]{4}-[0-9]{2}$")
    to: Text = Field(pattern=r"^[0-9]{4}-[0-9]{2}$")


class PeriodState(Model):
    entity: Text
    book: Text
    period_key: Text
    state: Text


class GlAccount(Model):
    code: Text
    name: Text
    account_type: Text


class AccountMappingRow(Model):
    account_role: Text
    clearing_purpose: Text | None = None
    account: Text
    entity: Text | None = None
    book_code: Text | None = None
    product: Text | None = None
    revenue_category: Text | None = None
    priority: DigitInt | None = None


class Customer(Model):
    code: Text
    name: Text
    related_party_group: Text | None = None


class PobTemplate(Model):
    code: Text
    obligation_kind: Text
    distinctness: Text
    series_increment_unit: Text | None = None
    satisfaction_pattern: Text
    over_time_criterion: Text
    recognition_method: Text
    ratable_convention: Literal["DAILY", "MONTHLY_EVEN", "MID_MONTH"] | None = None
    start_date_rule: Text | None = None
    end_date_rule: Text | None = None
    term_months: DigitInt | None = None
    principal_agent: Text | None = None
    warranty_type: Text | None = None
    licence_nature: Text | None = None
    sfc_assessment_required: Flag | None = None
    is_excluded_from_netting_attribution: Flag | None = None
    revenue_category: Text | None = None
    account_role_overrides: AccountCodes | None = None
    policy_values: PolicyValues | None = None


class BundleComponent(Model):
    product: Text
    quantity_per_bundle: Text
    split_basis: Literal["relative_ssp", "fixed_percentage"]
    split_ratio: Text | None = None


class Product(Model):
    code: Text
    name: Text
    pob_template: Text
    sku_number: Text | None = None
    product_family: Text | None = None
    revenue_category: Text | None = None
    principal_agent: Text | None = None
    distinctness_default: Text | None = None
    is_bundle: Flag | None = None
    assurance_cost_per_unit: Text | None = None
    is_franchisor_preopening_service: Flag = False
    policy_values: PolicyValues | None = None
    components: tuple[BundleComponent, ...] | None = None


class SspRange(Model):
    band_dimension: Text | None = None
    band_from: Text | None = None
    band_to: Text | None = None
    point_value: Text | None = None
    low_value: Text | None = None
    mid_value: Text | None = None
    high_value: Text | None = None


class Population(Model):
    observation_count: DigitInt = Field(ge=1)
    inside_count: DigitInt

    @model_validator(mode="after")
    def _inside_within_observations(self) -> Population:
        if self.inside_count > self.observation_count:
            raise ValueError("inside_count exceeds observation_count")
        return self


class SspEntry(Model):
    product: Text
    stratification: Text | None = None
    region: Text | None = None
    channel: Text | None = None
    segment: Text | None = None
    deal_size_band: Text | None = None
    term_band: Text | None = None
    currency: Text
    method: Text
    value_basis: Text | None = None
    quantity_unit: Text | None = None  # E-125 (D-97 (3)); required with PER_INCREMENT
    unit_list_price: Text | None = None
    midpoint_discount_ratio: Text | None = None
    range_ratio: Text | None = None
    cost_basis: Text | None = None
    margin_ratio: Text | None = None
    distinctness: Text
    revenue_account: Text | None = None
    observable_point: Text | None = None
    population: Population | None = None
    ranges: tuple[SspRange, ...]


class SspBookVersion(Model):
    legacy_version_label: Text | None = None
    effective_from_date: Text | None = None
    effective_to_date: Text | None = None
    methodology_label: Text
    entries: tuple[SspEntry, ...]


class SspBook(Model):
    code: Text
    resolution_mode: Text
    entity: Text | None = None
    currency: Text | None = None
    versions: tuple[SspBookVersion, ...] = Field(min_length=1)


class FxRate(Model):
    base_currency: Text
    quote_currency: Text
    effective_date: Text
    period_key: Text | None = None
    rate: Text


class FxRateSet(Model):
    code: Text
    name: Text | None = None  # rev 1.26 (D-98 54): the T-REF-10 label; the platform runner's
    rate_type: Text
    rates: tuple[FxRate, ...]


class Rule(Model):
    rule_key: Text
    priority: DigitInt
    conditions: JsonValue
    outputs: JsonValue


class RuleExampleCase(Model):
    """Rev 1.26 (D-98 54): a T-REF-27 example case the platform runner runs before submission."""

    name: Text
    input: JsonValue
    expected_output: JsonValue


class RuleSet(Model):
    code: Text
    kind: Text
    rules: tuple[Rule, ...]
    example_cases: tuple[RuleExampleCase, ...] | None = None  # rev 1.26 (D-98 54)


class Scenario(Model):
    outcome: Text
    probability: Text
    amount: Text


class EstimateVersion(Model):
    version_no: DigitInt
    effective_date: Text
    scenarios: tuple[Scenario, ...] | None = None
    parameters: dict[str, Scalar] | None = None
    unconstrained_amount: Text | None = None
    most_conservative_amount: Text | None = None
    constrained_amount: Text | None = None
    rate: Text | None = None
    expected_total_amount: Text | None = None
    expected_quantity: Text | None = None
    amortization_months: DigitInt | None = None
    currency: Text | None = None
    rationale: Text


class Estimate(Model):
    element_code: Text
    estimate_kind: Text
    method: Text
    obligation_key: Text | None = None
    vc_element_type: Text | None = None
    allocation_target: Text | None = None
    target_obligation_keys: tuple[Text, ...] | None = None
    # T-CON-12 `allocation_criteria_evidence` (erev.memo): the 606-10-32-40(a) and (b) attestation
    # of a targeted element, carried to every version's parameters (S05-R-14, S08-R-04; D-91).
    allocation_criteria_evidence: Text | None = None
    direction: Literal["INCREASE", "DECREASE"]
    versions: tuple[EstimateVersion, ...] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _derive_direction(cls, data: Any) -> Any:
        """§9.5.4 (B3-DG-17): an absent `direction` derives from the kind and element type."""
        if isinstance(data, dict) and data.get("direction") is None:
            decrease = (
                data.get("estimate_kind") in DECREASE_ESTIMATE_KINDS
                or data.get("vc_element_type") in DECREASE_VC_ELEMENT_TYPES
            )
            return {**data, "direction": "DECREASE" if decrease else "INCREASE"}
        return data


class Portfolio(Model):
    code: Text
    name: Text
    product_group: Text | None = None
    description: Text | None = None
    members: tuple[Text, ...]
    estimates: tuple[Estimate, ...] | None = None


class Policies(Model):
    tenant: PolicyValues = Field(default_factory=dict)
    entities: dict[str, PolicyValues] = Field(default_factory=dict)
    books: dict[str, PolicyValues] = Field(default_factory=dict)


class World(Model):
    tenant: Tenant
    currencies: tuple[Text, ...]
    entities: tuple[Entity, ...] = Field(min_length=1)
    periods: Periods
    period_states: tuple[PeriodState, ...] = ()
    gl_accounts: tuple[GlAccount, ...] = ()
    account_mapping: tuple[AccountMappingRow, ...] = ()
    customers: tuple[Customer, ...] = ()
    pob_templates: tuple[PobTemplate, ...] = ()
    products: tuple[Product, ...] = ()
    ssp_books: tuple[SspBook, ...] = ()
    fx_rate_sets: tuple[FxRateSet, ...] = ()
    rule_sets: tuple[RuleSet, ...] = ()
    portfolios: tuple[Portfolio, ...] = ()
    policies: Policies = Field(default_factory=Policies)


# §9.5.4 contracts


class Termination(Model):
    party: Text
    has_penalty: Flag
    notice_days: DigitInt


class PaymentPoint(Model):
    date: Text
    amount: Money


class NoncashConsideration(Model):
    units: Text
    fair_value_per_unit: Text
    measurement_date: Text
    variability: Literal["FORM", "PERFORMANCE"]
    asset_type: Text


class ConsiderationPayable(Model):
    amount: Money
    promise_date: Text
    related_obligation_keys: tuple[Text, ...]
    distinct_good_fair_value: Money | None = None
    committed_purchases: Money | None = None
    share_based: Flag


class ContractLine(Model):
    """API-S-ContractLine fields; also the terms form of modification lines."""

    obligation_key: Text
    product_code: Text
    stratification: Text | None = None
    quantity: Text
    total_price: Money
    unit_price: Money | None = None
    start_date: Text | None = None
    end_date: Text | None = None
    performing_entity_code: Text | None = None
    ssp_version_label: Text | None = None
    ssp_override_justification: Text | None = None
    account_overrides: AccountCodes | None = None
    scope_flag: Text | None = None
    out_of_scope_amount: Money | None = None
    bundle_parent_obligation_key: Text | None = None
    memo_1: Text | None = None
    memo_2: Text | None = None
    memo_3: Text | None = None


class DeltaLine(Model):
    """The delta form of modification lines, marked by `action` (B3-DG-15)."""

    obligation_key: Text
    action: Literal["ADD", "REMOVE", "CHANGE"]
    product_code: Text | None = None
    quantity_delta: Text | None = None
    consideration_delta: Money | None = None
    start_date: Text | None = None
    end_date: Text | None = None
    stratification: Text | None = None
    selling_entity_code: Text | None = None
    account_codes: AccountCodes | None = None
    ssp_version_label: Text | None = None
    memo_1: Text | None = None
    memo_2: Text | None = None
    memo_3: Text | None = None


def _line_form(value: Any) -> str:
    return "delta" if isinstance(value, dict) and "action" in value else "terms"


ModificationLine = Annotated[
    Annotated[DeltaLine, Tag("delta")] | Annotated[ContractLine, Tag("terms")],
    Discriminator(_line_form),
]


class PolicyOverride(Model):
    policy_key: Text
    value: PolicyValue
    obligation_key: Text | None = None
    rationale: Text


class Judgement(Model):
    handle: Text
    topic: Text
    subject_obligation_key: Text | None = None
    book_code: Text | None = None
    conclusion: Text
    rationale: Text | None = None  # rev 1.26 (D-98 54): T-CON-19 rationale; the platform runner's
    questionnaire: dict[str, Scalar] | None = None


class MaterialRight(Model):
    obligation_key: Text
    option_type: Text
    incremental_discount_ratio: Text | None = None
    is_discount_available_without_contract: Flag | None = None
    expected_purchase_amount: Money | None = None
    ssp_method: Text
    expiry_date: Text | None = None
    likelihood_estimate: Text | None = None
    is_legacy_quantity_ssp_dollars: Flag | None = None


class Modification(Model):
    reference: Text
    effective_date: Text
    kind: Text
    template_mode: Text | None = None
    questionnaire: dict[str, dict[str, Scalar]] | None = None
    lines: tuple[ModificationLine, ...]
    price_change_amount: Money | None = None
    chosen_treatments: dict[str, Text] | None = None
    ssp_basis: Text | None = None


class Contract(Model):
    external_id: Text
    customer: Text
    contracting_entity: Text
    transaction_currency: Text
    inception_date: Text
    signature_date: Text | None = None
    payment_terms: Text | None = None
    termination: Termination | None = None
    has_commercial_substance: Flag | None = None
    region: Text | None = None
    channel: Text | None = None
    contract_type: Text | None = None
    renewal_of: Text | None = None
    scope_605_35: Flag = False
    payment_schedule: tuple[PaymentPoint, ...] | None = None
    noncash_consideration: tuple[NoncashConsideration, ...] | None = None
    consideration_payable: tuple[ConsiderationPayable, ...] | None = None
    combination_group: Text | None = None
    combination_criterion: Text | None = None
    lines: tuple[ContractLine, ...] = Field(min_length=1)
    policy_overrides: tuple[PolicyOverride, ...] | None = None
    judgements: tuple[Judgement, ...] | None = None
    estimates: tuple[Estimate, ...] | None = None
    material_rights: tuple[MaterialRight, ...] | None = None
    modifications: tuple[Modification, ...] | None = None


# §9.5.5 timeline


class ExpectProblem(Model):
    code: Text
    rule_id: Text | None = None
    status: DigitInt | None = None


class EventItem(Model):
    seq: DigitInt
    kind: Literal["event"]
    contract: Text
    event_type: Text
    effective_date: Text
    recorded_at: RecordedAt | None = None
    payload: dict[str, JsonValue]
    is_manual: Flag = False
    expect_problem: ExpectProblem | None = None


class PeriodStateItem(Model):
    seq: DigitInt
    kind: Literal["period_state"]
    entity: Text
    book: Text
    period_key: Text
    state: Text
    recorded_at: RecordedAt | None = None
    expect_problem: ExpectProblem | None = None


class Command(Model):
    name: Literal[
        "close_run", "journal_run", "lock_period", "reopen_period", "publish_fx_rate_set",
        "import_upload",
    ]  # fmt: skip
    params: dict[str, JsonValue] = Field(default_factory=dict)


class CommandItem(Model):
    seq: DigitInt
    kind: Literal["command"]
    command: Command
    recorded_at: RecordedAt | None = None
    expect_problem: ExpectProblem | None = None


def _item_kind(value: Any) -> str | None:
    kind = value.get("kind") if isinstance(value, dict) else getattr(value, "kind", None)
    return kind if kind in ("event", "period_state", "command") else None


TimelineItem = Annotated[
    Annotated[EventItem, Tag("event")]
    | Annotated[PeriodStateItem, Tag("period_state")]
    | Annotated[CommandItem, Tag("command")],
    Discriminator(
        _item_kind,
        custom_error_type="timeline_kind",
        custom_error_message="kind must be event, period_state or command",
    ),
]


# §9.5.6 checkpoints


class BalanceAmounts(Model):
    """API-S-ContractBalance labelled balances (04 §16)."""

    contract_liability: Money | None = None
    contract_liability_current: Money | None = None
    contract_asset: Money | None = None
    contract_asset_current: Money | None = None
    unbilled_receivable: Money | None = None
    accounts_receivable: Money | None = None
    refund_liability: Money | None = None
    return_asset: Money | None = None
    deposit_liability: Money | None = None
    customer_incentive_asset: Money | None = None
    consideration_payable: Money | None = None
    cost_asset_carrying: Money | None = None
    loss_provision: Money | None = None


class BalanceRow(BalanceAmounts):
    entity: Text
    functional: BalanceAmounts | None = None


class VersionBlock(Model):
    transaction_price: Money | None = None
    fixed_consideration: Money | None = None
    vc_constrained_amount: Money | None = None
    vc_excluded_amount: Money | None = None
    expected_returns_amount: Money | None = None
    consideration_payable_amount: Money | None = None
    financing_adjustment_amount: Money | None = None
    noncash_consideration_amount: Money | None = None
    sales_tax_excluded_amount: Money | None = None
    out_of_scope_amount: Money | None = None
    total_ssp: Text | None = None
    revenue_cum: Money | None = None
    billed_cum: Money | None = None
    rpo_amount: Money | None = None
    scheduled_amount: Money | None = None
    awaiting_trigger_amount: Money | None = None
    modification_boundary_no: DigitInt | None = None


def _obligation_row(value: object) -> object:
    if isinstance(value, dict) and not isinstance(value.get("obligation_key"), str):
        raise ValueError("an obligation row names its obligation_key")
    return value


ObligationRow = Annotated[dict[str, Scalar | None], BeforeValidator(_obligation_row)]


class ScheduleRow(Model):
    obligation_key: Text | None = None
    cost_asset: Text | None = None
    schedule_kind: Text
    line_type: Text = "NORMAL"
    amounts: dict[str, Money] | None = None
    period_key: Text | None = None
    amount: Money | None = None
    cumulative_amount: Money | None = None
    quantity: Text | None = None

    @model_validator(mode="after")
    def _one_subject_and_one_form(self) -> ScheduleRow:
        _exactly_one(self.__dict__, ("obligation_key", "cost_asset"), "a schedule row")
        partial = (self.period_key is None) != (self.amount is None)
        per_period = self.period_key is not None and self.amount is not None
        if partial or (self.amounts is not None) == per_period:
            raise ValueError("a schedule row carries amounts, or period_key with amount")
        return self


class ModificationBlock(Model):
    reference: Text
    proposed_treatments: dict[str, Text]
    treatment_summary: Text | None = None


class TraceAssertion(Model):
    measure: Text
    subject_key: Text
    period_key: Text | None = None
    value: Text
    formula_id: Text | None = None


class ContractBlock(Model):
    contract: Text
    status_in_book: Text | None = None
    version: VersionBlock | None = None
    obligations: tuple[ObligationRow, ...] | None = None
    balances: tuple[BalanceRow, ...] | None = None
    schedule: tuple[ScheduleRow, ...] | None = None
    modifications: tuple[ModificationBlock, ...] | None = None
    trace: tuple[TraceAssertion, ...] | None = None


class SubledgerLine(Model):
    account_role: Text
    clearing_purpose: Text | None = None
    account: Text | None = None
    obligation_key: Text | None = None
    entry_kind: Text | None = None
    origin_period_key: Text | None = None
    counterparty_entity: Text | None = None
    dr: Money | None = None
    cr: Money | None = None
    functional_dr: Money | None = None
    functional_cr: Money | None = None

    @model_validator(mode="after")
    def _one_side(self) -> SubledgerLine:
        _exactly_one(self.__dict__, ("dr", "cr"), "a subledger line")
        return self


class SubledgerBlock(Model):
    period_key: Text
    entity: Text
    match: Literal["exact", "subset"]
    contract: Text | None = None
    grain: Literal["role", "role_account", "role_account_obligation"] = "role_account"
    lines: tuple[SubledgerLine, ...]


class JournalRun(Model):
    entity: Text
    period_key: Text
    mode: Text
    grain: Text


class JournalLine(Model):
    account: Text
    dr: Money | None = None
    cr: Money | None = None
    contract: Text | None = None
    legacy_key: Text | None = None

    @model_validator(mode="after")
    def _one_side(self) -> JournalLine:
        _exactly_one(self.__dict__, ("dr", "cr"), "a journal line")
        return self


class JournalBlock(Model):
    run: JournalRun
    match: Literal["exact", "subset"]
    lines: tuple[JournalLine, ...]


class ReportCell(Model):
    row_key: Text
    column_key: Text
    value: Text


class ReportBlock(Model):
    report_code: Text
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    cells: tuple[ReportCell, ...]


class GroupBlock(Model):
    group: Text
    balances: tuple[BalanceRow, ...]


class ExceptionRow(Model):
    code: Text
    severity: Literal["ERROR", "WARNING"]
    contract: Text | None = None
    obligation_key: Text | None = None
    subject: Text | None = None


class Checkpoint(Model):
    name: Text = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    after_seq: DigitInt
    as_of: Text
    book: Text
    contracts: tuple[ContractBlock, ...] | None = None
    subledger: tuple[SubledgerBlock, ...] | None = None
    journals: tuple[JournalBlock, ...] | None = None
    reports: tuple[ReportBlock, ...] | None = None
    period_states: tuple[PeriodState, ...] | None = None
    groups: tuple[GroupBlock, ...] | None = None
    exceptions: tuple[ExceptionRow, ...] | None = None


class AnswerKey(Model):
    schema_id: Literal["erev-answer-key/1"] = Field(alias="schema")
    id: Text = Field(pattern=KEY_ID_PATTERN)
    title: Text = Field(max_length=200)
    status: Literal["active", "withdrawn"]
    families: tuple[FamilyCode, ...] = Field(min_length=1)
    tags: tuple[Annotated[Text, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")], ...] = ()
    summary: Text
    authority: Authority
    derived_from: DerivedFrom = Field(default_factory=DerivedFrom)
    requirements: tuple[Annotated[Text, Field(pattern=r"^REQ-[A-Z]+-[0-9]{3}$")], ...] = Field(
        min_length=1
    )
    policy_refs: tuple[Annotated[Text, Field(pattern=r"^POL-[0-9]{3}$")], ...] = ()
    review: Review
    runner: Literal["engine", "platform"]
    books: tuple[Text, ...] = Field(min_length=1)
    world: World
    contracts: tuple[Contract, ...] = Field(min_length=1)
    timeline: tuple[TimelineItem, ...] = Field(min_length=1)
    checkpoints: tuple[Checkpoint, ...] = Field(min_length=1)
    # DG-AK-59 (D-97 (2)): documentary; the loader and the runner read nothing from it.
    notes: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def _field_rules(self) -> AnswerKey:
        if len(set(self.families)) != len(self.families):
            raise ValueError("families are unique (DG-AK-14)")
        if not self.authority.codification and self.families[0] not in ("RND", "PAR"):
            raise ValueError("authority.codification is empty only for RND and PAR (DG-AK-17)")
        names = [checkpoint.name for checkpoint in self.checkpoints]
        if len(set(names)) != len(names):
            raise ValueError("checkpoint names are unique in the key (§9.5.6)")
        return self
