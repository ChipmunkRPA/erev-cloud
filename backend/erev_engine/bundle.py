"""Engine input and output bundles (dev-guide §7; ENGINE_SPEC §0.4, §0.5, CV-25, CV-26; EKC-6).

Every class is a frozen dataclass with slots. Money and exact values arrive as ``Decimal`` and are
converted once by ``money.to_fraction`` in stage 01; dates are ``date`` and timestamps are
timezone-aware ``datetime``. Input tuples are sorted by the key noted beside them and stage 01
asserts the order (S01-R-02), so these classes do not validate. Output tuples follow CV-23.

The types §0.4 names without expanding carry the 04 columns or payload members of their source
(T-CON-06, T-CON-14, T-CON-21 and T-CON-22, API-S-PaymentPoint, API-S-NoncashConsideration,
API-S-ConsiderationPayable), with natural keys in place of surrogate ids (DG-ENG-02). The version
rows of the output (T-CON-08, T-CON-09, T-CON-11, T-CON-16 to T-CON-18) carry their 04 columns as
a mapping by column name. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from erev_engine.canonical import sha256_hex
from erev_engine.currencies import CurrencyTable
from erev_engine.trace import Trace

if TYPE_CHECKING:
    from erev_engine.stages.state import ScheduleLineOut

__all__ = [
    "DECREASE",
    "DIRECTIONS",
    "INCREASE",
    "VC_DECREASE_TYPES",
    "AccountMappingInput",
    "BalanceOut",
    "BookInput",
    "BookOutput",
    "BundleComponentInput",
    "ContractInput",
    "ContractVersionOut",
    "CostAssetVersionOut",
    "Diagnostic",
    "EntityInput",
    "EstimateVersionInput",
    "EventInput",
    "FxLayerMovementOut",
    "FxRateInput",
    "GroupInput",
    "InputBundle",
    "IntentLine",
    "JudgementInput",
    "LossProvisionOut",
    "MappingRuleInput",
    "MaterialRightInput",
    "ModificationInput",
    "NoncashInput",
    "ObligationVersionOut",
    "OutputBundle",
    "PayableInput",
    "PaymentPointInput",
    "PeriodInput",
    "PortfolioInput",
    "PostedAmountInput",
    "PostingIntent",
    "ProductInput",
    "ProposalOut",
    "ResolvedPolicyInput",
    "RuleInput",
    "RuleSetInput",
    "SspEntryInput",
    "SspRangeInput",
    "SspVersionInput",
    "TemplateInput",
    "TimeTrigger",
]

# Alias for members named ``date`` (API-S-PaymentPoint, RCP-10 time triggers).
_Date = date


# --- Input bundle (ENGINE_SPEC §0.4) -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResolvedPolicyInput:
    """A policy value resolved by the orchestrator (DG-KRN-REG-03); stages read it (CV-17)."""

    code: str  # POLICIES §1 key, for example "mod.ssp_basis"
    scope: str  # "GROUP" | "CONTRACT" | "OBLIGATION" | "ENTITY" | "PERIOD"
    # "" for GROUP; contract external_id; obligation subject key; entity code;
    # "<entity code>@<period_key>" for PERIOD
    subject_key: str
    value: str | tuple[str, ...] | Mapping[str, str]  # POLICIES §1 literals; decimals as strings
    level: str  # "O" | "C" | "P" | "B" | "E" | "T" | "DEFAULT" (DG-KRN-REG-01)
    source_ref: str  # registry version, template version, product or override key
    pin: str  # "K" | "P"


@dataclass(frozen=True, slots=True)
class MappingRuleInput:
    """T-REF-15 rule of the pinned account mapping version."""

    account_role: str  # E-01
    clearing_purpose: str | None
    entity_code: str | None
    book_code: str | None
    product_code: str | None
    revenue_category: str | None
    account_code: str
    default_dimensions: Mapping[str, str]
    priority: int
    specificity: int


@dataclass(frozen=True, slots=True)
class AccountMappingInput:
    """PUBLISHED account mapping version pinned for the computation (T-REF-14, T-REF-15)."""

    version_key: str
    content_sha256: str
    # (account_role, clearing_purpose, -specificity, -priority, account_code)
    rules: tuple[MappingRuleInput, ...]


@dataclass(frozen=True, slots=True)
class BookInput:
    book_code: str  # E-02
    is_primary: bool
    entity_codes: tuple[str, ...]  # entities keeping the book (T-REF-03), sorted
    policies: tuple[ResolvedPolicyInput, ...]  # (code, scope, subject_key)
    account_mapping: AccountMappingInput


@dataclass(frozen=True, slots=True)
class PeriodInput:
    period_key: str  # FY<year>-P<nn> (T-REF-05)
    fiscal_year: int
    period_no: int
    start_date: date
    end_date: date
    states: tuple[tuple[str, str], ...]  # (book_code, E-04 state) at known_at, sorted by book_code


@dataclass(frozen=True, slots=True)
class EntityInput:
    code: str
    functional_currency: str
    time_zone: str
    calendar_pattern: str  # E-50
    # start_date; group inception through the horizon plus the future periods containing every
    # subject end date (CV-12, CV-13)
    periods: tuple[PeriodInput, ...]


@dataclass(frozen=True, slots=True)
class BundleComponentInput:
    """T-REF-21 bundle component."""

    component_product_code: str
    quantity_per_bundle: Decimal
    split_basis: str  # "relative_ssp" | "fixed_percentage"
    split_ratio: Decimal | None
    sequence: int
    valid_from: date
    valid_to: date | None


@dataclass(frozen=True, slots=True)
class ProductInput:
    """T-REF-20 product with its components."""

    code: str
    sku_number: str | None
    product_family: str | None
    revenue_category: str | None
    default_template_code: str | None
    principal_agent: str  # E-89
    distinctness_default: str  # E-105
    unit_of_measure: str
    is_bundle: bool
    policy_values: Mapping[str, str]
    assurance_cost_per_unit: Decimal | None  # None = no accrual (S03-R-08)
    components: tuple[BundleComponentInput, ...]  # (sequence, component_product_code)
    # T-REF-20 column (04 rev 1.2, B3-D21): 952-606-25-2 pre-opening service (POL-202; S03-R-15)
    is_franchisor_preopening_service: bool = False


@dataclass(frozen=True, slots=True)
class PortfolioInput:
    """T-CON-21 portfolio with its member contracts at known_at (T-CON-22)."""

    code: str
    member_contract_keys: tuple[str, ...]  # sorted


@dataclass(frozen=True, slots=True)
class GroupInput:
    group_key: str  # combination_group.code (T-CON-03)
    transaction_currency: str
    inception_date: date  # earliest member inception (T-CON-03)
    member_contract_keys: tuple[str, ...]  # members at known_at (T-CON-04), sorted
    criterion: str | None  # "25_9_A" | "25_9_B" | "25_9_C"; None for singletons
    # (contract key, stream_version) included in the previous computation; () for the first
    previous_stream_heads: tuple[tuple[str, int], ...]
    products: tuple[ProductInput, ...]  # every product referenced by a member line or event; code
    portfolios: tuple[PortfolioInput, ...]  # code


@dataclass(frozen=True, slots=True)
class JudgementInput:
    """T-CON-19 REVIEWED record; the engine reads the Table 0.4-A outcome members only."""

    judgement_key: str
    topic: str  # E-56
    subject_key: str
    book_code: str | None  # None = every book
    outcome: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class MaterialRightInput:
    """T-CON-14 option terms of a material-right obligation (D-21, D-21a)."""

    obligation_key: str
    option_type: str  # E-92
    incremental_discount_ratio: Decimal | None
    is_discount_available_without_contract: bool
    expected_purchase_amount: Decimal | None
    currency: str
    ssp_method: str  # "DISCOUNT_X_LIKELIHOOD" | "RENEWAL_ALTERNATIVE" | "ENTERED_AMOUNT" (POL-026)
    expiry_date: date | None
    likelihood_estimate_key: str | None  # EXERCISE_LIKELIHOOD element (T-CON-12)
    is_legacy_quantity_ssp_dollars: bool


@dataclass(frozen=True, slots=True)
class NoncashInput:
    """API-S-NoncashConsideration item (POL-048)."""

    units: Decimal
    fair_value_per_unit: Decimal
    measurement_date: date
    variability: str  # "FORM" | "PERFORMANCE" (606-10-32-23)
    asset_type: str | None


@dataclass(frozen=True, slots=True)
class PayableInput:
    """API-S-ConsiderationPayable item (POL-049)."""

    amount: Decimal
    promise_date: date
    related_obligation_keys: tuple[str, ...]  # empty = every obligation
    distinct_good_fair_value: Decimal | None
    committed_purchases: Decimal | None
    share_based: bool


@dataclass(frozen=True, slots=True)
class PaymentPointInput:
    """API-S-PaymentPoint: expected payment for the POL-046 financing gap test (S04-R-10)."""

    date: _Date  # ascending, unique within the schedule
    amount: Decimal


@dataclass(frozen=True, slots=True)
class ModificationInput:
    """T-CON-06 modification object (APPROVED or APPLIED) referenced by an event."""

    modification_key: str  # modification_no
    effective_date: date
    kind: str  # E-25
    template_mode: str | None  # E-24
    status: str  # E-26
    reference: str | None
    questionnaire: Mapping[str, object]
    lines: tuple[Mapping[str, object], ...]
    price_change_amount: Decimal | None
    noncash_consideration: tuple[NoncashInput, ...] | None  # None = unchanged
    consideration_payable: tuple[PayableInput, ...] | None  # None = unchanged
    scope_605_35: bool | None  # None = unchanged
    currency: str
    proposed_treatments: Mapping[str, str]  # obligation key -> E-23
    chosen_treatments: Mapping[str, str]  # obligation key -> E-23
    treatment_summary: str | None  # E-23
    # obligation key -> {ssp_version_key, is_override, justification} (D-18)
    ssp_basis: Mapping[str, Mapping[str, str]]
    judgement_key: str | None
    content_sha256: str | None


@dataclass(frozen=True, slots=True)
class ContractInput:
    """T-CON-01 header projection at known_at; the booking payload is authoritative (S01-R-20)."""

    external_id: str
    customer_code: str
    related_party_group: str | None
    contracting_entity_code: str
    transaction_currency: str
    inception_date: date
    signature_date: date | None
    document_ref: str | None
    termination_party: str | None
    termination_has_penalty: bool | None
    termination_notice_days: int | None
    has_commercial_substance: bool
    region: str | None
    channel: str | None
    contract_type: str | None
    renewal_of_contract_key: str | None
    judgements: tuple[JudgementInput, ...]  # REVIEWED records only; judgement_key
    material_rights: tuple[MaterialRightInput, ...]  # obligation_key
    modifications: tuple[ModificationInput, ...]  # modification_key
    noncash_consideration: tuple[NoncashInput, ...]
    consideration_payable: tuple[PayableInput, ...]
    payment_schedule: tuple[PaymentPointInput, ...]
    scope_605_35: bool


@dataclass(frozen=True, slots=True)
class EventInput:
    """T-CON-05 event with handles resolved to natural keys."""

    event_key: str  # "<contract external_id>/EV-<stream_version, 6 digits>" (CV-22)
    contract_key: str
    stream_version: int
    event_type: str  # E-03
    schema_version: int
    effective_date: date
    recorded_at: datetime
    record_seq: int
    origin: str
    is_manual: bool
    obligation_keys: tuple[str, ...]
    payload: Mapping[str, object]  # 04 §16.3 payload
    payload_sha256: str
    idempotency_key: str | None
    supersedes_event_key: str | None  # EVENT_VOIDED target
    modification_key: str | None
    estimate_version_key: str | None
    manual_adjustment_key: str | None


@dataclass(frozen=True, slots=True)
class SspRangeInput:
    band_dimension: str
    band_from: Decimal | None
    band_to: Decimal | None
    point_value: Decimal | None
    low_value: Decimal | None
    mid_value: Decimal | None
    high_value: Decimal | None


@dataclass(frozen=True, slots=True)
class SspEntryInput:
    entry_key: str  # "<version_key>/<product_code>/<stratification>/<dims>/<currency>"
    product_code: str
    stratification: str
    region: str | None
    channel: str | None
    segment: str | None
    deal_size_band: str | None
    term_band: str | None
    currency: str
    method: str  # E-47
    value_basis: str  # E-49
    unit_list_price: Decimal | None
    midpoint_discount_ratio: Decimal | None
    range_ratio: Decimal | None
    cost_basis: Decimal | None
    margin_ratio: Decimal | None
    distinctness: str
    revenue_account_code: str | None
    observable_point: Decimal | None  # None = absent (S05-R-07)
    ranges: tuple[SspRangeInput, ...]  # (band_dimension, band_from)
    # E-125 (D-97 (3)): what a series line's quantity counts under PER_INCREMENT; required then
    # (CV-45), never inferred, no default, meaningful for PER_INCREMENT only.
    quantity_unit: str | None = None

    def hash_view(self) -> dict[str, object]:
        """The entry's members for ``InputBundle.sha256`` (CV-25): ``quantity_unit`` is written
        only when declared (D-97 (3)). This canonicalises bundles assembled before the member
        existed: an entry without a declaration hashes identically to the form hashed before it —
        the D-93 (5) ``direction`` treatment. Only this CV-25 view normalises; the dataclass
        encoding keeps the field (DG-KRN-CAN-13). Replay stays version-pinned to the stored engine
        release (RCP-28 to RCP-30); no byte-identical cross-version claim is made."""
        view: dict[str, object] = {item.name: getattr(self, item.name) for item in fields(self)}
        if self.quantity_unit is None:
            del view["quantity_unit"]
        return view


@dataclass(frozen=True, slots=True)
class SspVersionInput:
    """T-REF-28 to T-REF-31 SSP book version (pinned or effective only)."""

    ssp_book_code: str
    version_key: str  # "<ssp book code>@v<version_no>"
    version_no: int
    resolution_mode: str  # "EFFECTIVE_DATE" | "BY_LABEL"
    legacy_version_label: str | None
    effective_from_date: date | None
    effective_to_date: date | None
    status: str  # "APPROVED" | "SUPERSEDED"
    approved_at: datetime
    content_sha256: str
    scope_entity_code: str | None
    scope_currency: str | None
    scope_channel: str | None
    scope_segment: str | None
    # (product_code, stratification, region, channel, segment, deal_size_band, term_band, currency)
    entries: tuple[SspEntryInput, ...]

    def hash_view(self) -> dict[str, object]:
        """The version's members for ``InputBundle.sha256`` (CV-25) with each entry through
        ``SspEntryInput.hash_view`` (D-97 (3): ``quantity_unit`` only when declared)."""
        view: dict[str, object] = {item.name: getattr(self, item.name) for item in fields(self)}
        view["entries"] = tuple(entry.hash_view() for entry in self.entries)
        return view


@dataclass(frozen=True, slots=True)
class TemplateInput:
    """T-REF-23 POB template version columns plus identity."""

    template_code: str
    version_key: str
    version_no: int
    content_sha256: str
    obligation_kind: str  # E-18
    distinctness: str  # E-105
    series_increment_unit: str | None
    satisfaction_pattern: str  # E-19
    over_time_criterion: str  # E-20
    recognition_method: str  # E-11
    ratable_convention: str | None  # E-21
    start_date_rule: str
    end_date_rule: str
    term_months: int | None
    principal_agent: str  # E-89
    warranty_type: str  # E-91
    licence_nature: str  # E-90
    sfc_assessment_required: bool
    revenue_category: str | None
    disaggregation: Mapping[str, str]
    account_role_overrides: Mapping[str, str]
    stratification_label: str | None
    is_excluded_from_netting_attribution: bool
    policy_values: Mapping[str, str]
    effective_from: date  # SC-V effective range
    effective_to: date | None


@dataclass(frozen=True, slots=True)
class RuleInput:
    """T-REF-26 rule; ``erev_engine.rules.match`` evaluates it."""

    rule_key: str
    priority: int
    specificity: int
    conditions: tuple[Mapping[str, object], ...]
    outputs: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class RuleSetInput:
    """T-REF-25 rule set version."""

    rule_set_code: str
    kind: str  # E-55
    version_key: str
    version_no: int
    content_sha256: str
    effective_from: date
    effective_to: date | None
    rules: tuple[RuleInput, ...]  # (-specificity, -priority, rule_key)


# 04 T-CON-12 ``direction`` (B3-D16): the sign belongs to the element; version amounts are
# magnitudes.
INCREASE: Final = "INCREASE"
DECREASE: Final = "DECREASE"
DIRECTIONS: Final = frozenset({INCREASE, DECREASE})
# dev-guide §9.5.4 B3-DG-17 (topics convention T-03): the VARIABLE_CONSIDERATION element types that
# reduce the transaction price when the element carries no direction.
VC_DECREASE_TYPES: Final = frozenset(
    {
        "IMPLICIT_PRICE_CONCESSION",
        "REBATE",
        "VOLUME_TIER",
        "PRICE_PROTECTION",
        "SLA_CREDIT",
        "DISCOUNT",
        "RETURN",
        "REFUND",
        "PENALTY",
    }
)
_DIRECTED_KINDS: Final = frozenset({"VARIABLE_CONSIDERATION", "IMPLICIT_PRICE_CONCESSION"})


@dataclass(frozen=True, slots=True)
class EstimateVersionInput:
    """T-CON-12 and T-CON-13; APPROVED versions referenced by included events.

    ``direction`` is the element's T-CON-12 column (B3-D16), carried by every producer that holds
    it (the platform bundle from the stored element, the answer-key runner from the key); ``None``
    means the producer carried none and ``resolved_direction`` applies the documented B3-DG-17
    default. ``hash_view`` writes the member into ``input_sha256`` only when it differs from that
    default (CV-25; ENC-VC-direction).
    """

    # "<contract external_id>/<element_code>" or "PORTFOLIO:<code>/<element_code>"
    estimate_key: str
    estimate_kind: str  # E-09
    element_code: str
    method: str  # E-10
    vc_element_type: str | None
    allocation_target: str
    target_obligation_keys: tuple[str, ...]
    obligation_key: str | None
    version_key: str  # "<estimate_key>@v<version_no>"
    version_no: int
    status: str
    effective_date: date
    scenarios: tuple[Mapping[str, Decimal], ...]  # {outcome, amount, probability}
    parameters: Mapping[str, object]  # T-CON-13 parameter schema by kind
    unconstrained_amount: Decimal | None
    most_conservative_amount: Decimal | None
    constrained_amount: Decimal | None
    rate: Decimal | None
    expected_total_amount: Decimal | None
    expected_quantity: Decimal | None
    amortization_months: int | None
    currency: str | None
    supersedes_version_key: str | None
    judgement_key: str | None
    content_sha256: str
    direction: str | None = None  # T-CON-12 INCREASE | DECREASE; None: resolved_direction derives

    def resolved_direction(self) -> str:
        """The element's direction (B3-D16), or the B3-DG-17 default when the producer carried
        none: ``DECREASE`` for kind ``IMPLICIT_PRICE_CONCESSION`` and for a
        ``VARIABLE_CONSIDERATION`` element whose type is in ``VC_DECREASE_TYPES``, else
        ``INCREASE``. An explicit value outside ``DIRECTIONS``, an ``IMPLICIT_PRICE_CONCESSION``
        element that is not ``DECREASE`` or a ``DECREASE`` on a kind without a direction violates
        the T-CON-12 checks (04 §16.14) and is malformed input (CV-45)."""
        kind = self.estimate_kind
        if self.direction is None:
            if kind == "IMPLICIT_PRICE_CONCESSION":
                return DECREASE
            if kind == "VARIABLE_CONSIDERATION" and self.vc_element_type in VC_DECREASE_TYPES:
                return DECREASE
            return INCREASE
        if self.direction not in DIRECTIONS:
            raise ValueError(
                f"{self.version_key}: direction {self.direction!r} is not INCREASE or DECREASE "
                "(T-CON-12; CV-45)"
            )
        if kind == "IMPLICIT_PRICE_CONCESSION" and self.direction != DECREASE:
            raise ValueError(
                f"{self.version_key}: an IMPLICIT_PRICE_CONCESSION element is DECREASE "
                "(T-CON-12; CV-45)"
            )
        if kind not in _DIRECTED_KINDS and self.direction != INCREASE:
            raise ValueError(f"{self.version_key}: a {kind} element is INCREASE (T-CON-12; CV-45)")
        return self.direction

    def hash_view(self) -> dict[str, object]:
        """The version's members for ``InputBundle.sha256`` (CV-25): ``direction`` is written only
        when it differs from the B3-DG-17 default the engine would derive without it (D-93 (5);
        ENC-VC-direction). This canonicalises pre-0.3.0 bundles: an absent member and an explicit
        member equal to that default hash identically, and identically to the form hashed before
        the member existed. Limits: the view depends on the B3-DG-17 default list; an explicit
        default-equal direction is indistinguishable in the hash from an absent one; only this
        CV-25 view normalises, the dataclass encoding keeps the field (DG-KRN-CAN-13); and the hash
        still carries ``engine_version``, so every 0.3.0 input hash differs from its 0.2.0 one.
        Replay is version-pinned to the stored engine release (RCP-28 to RCP-30); no silent
        rewriting or reposting of history; historical-integrity replay (RCP-28/29) and
        candidate-upgrade validation (REL-06) remain mandatory; new computations use 0.3.0."""
        view: dict[str, object] = {item.name: getattr(self, item.name) for item in fields(self)}
        if (
            self.direction is None
            or self.direction == replace(self, direction=None).resolved_direction()
        ):
            del view["direction"]
        return view


@dataclass(frozen=True, slots=True)
class FxRateInput:
    """T-REF-11, T-REF-12 rate."""

    rate_key: str
    version_key: str
    rate_type: str  # E-51
    base_currency: str
    quote_currency: str
    effective_date: date
    period_key: str | None
    rate: Decimal


@dataclass(frozen=True, slots=True)
class PostedAmountInput:
    """RCP-05 posted cumulative amounts, grouped also by origin period, posting class and the
    line's ``reason_code`` (S14-R-27; D-98 candidate 19), with the rate references stamped on the
    summed lines (S14-R-28)."""

    book_code: str
    entity_code: str
    subject_key: str
    entry_kind: str  # E-29
    account_role: str  # E-01
    clearing_purpose: str | None
    counterparty_entity_code: str | None
    period_key: str  # posting period
    origin_period_key: str | None  # None when posted in its own period
    posting_class: str  # "EVENT" | "TIME"
    txn_currency: str
    functional_currency: str
    amount_txn: int  # signed minor units, debit positive
    amount_functional: int
    # subledger_line.reason_code of the summed lines; None when they carry none (S14-R-27).
    reason_code: str | None = None
    # The distinct (rate_key, version_key) of the rates stamped on the summed lines, sorted: what a
    # delta that only reverses this amount names as its rates (S14-R-28; 05 RCP-05 rev 1.41). Not a
    # grouping member. Empty when transaction and functional currency are the same.
    rate_refs: tuple[tuple[str, str], ...] = ()

    def hash_view(self) -> dict[str, object]:
        """The members for ``InputBundle.sha256`` (CV-25): ``reason_code`` is written only when
        set, so a bundle whose posted lines carry no reason hashes as it did before the member
        existed, apart from the ``engine_version`` stamp (the D-93 (5) ``direction`` precedent;
        ENGINE_SPEC §0.4 rev 1.16), and ``rate_refs`` only when the lines carry a rate (rev 1.43),
        so a single-currency bundle hashes as before. Only this view normalises; the dataclass
        encoding keeps the fields (DG-KRN-CAN-13)."""
        view: dict[str, object] = {item.name: getattr(self, item.name) for item in fields(self)}
        if self.reason_code is None:
            del view["reason_code"]
        if not self.rate_refs:
            del view["rate_refs"]
        return view


@dataclass(frozen=True, slots=True)
class InputBundle:
    """Everything one computation reads (DG §7 field list; ENGINE_SPEC §0.4)."""

    format_version: int  # 1
    engine_version: str  # == ENGINE_VERSION
    trigger: str  # E-87 literal, or "DRY_RUN"
    known_at: datetime  # record-time cutoff; excluded from sha256 (CV-25)
    tenant_preset: str  # "DEFAULT" | "LEGACY_PARITY" (informational, DG-ENG-09)
    currencies: CurrencyTable  # every code the group uses
    books: tuple[BookInput, ...]  # RCP-11 order ASC606, IFRS15, LEGACY
    entities: tuple[EntityInput, ...]  # code
    group: GroupInput
    contracts: tuple[ContractInput, ...]  # external_id
    events: tuple[EventInput, ...]  # (effective_date, record_seq, event_key) = ENG-06
    ssp_versions: tuple[SspVersionInput, ...]  # (ssp_book_code, version_no)
    pob_template_versions: tuple[TemplateInput, ...]  # (template_code, version_no)
    rule_set_versions: tuple[RuleSetInput, ...]  # (rule_set_code, version_no)
    estimate_versions: tuple[EstimateVersionInput, ...]  # (estimate_key, version_no)
    fx_rates: tuple[FxRateInput, ...]  # (rate_type, base, quote, effective_date, version_key)
    # (book_code, entity_code, subject_key, entry_kind, account_role, clearing_purpose or "",
    #  period_key, origin_period_key or "", posting_class)
    posted: tuple[PostedAmountInput, ...]

    def sha256(self) -> str:
        """CV-25: SHA-256 of the canonical bundle without ``known_at``; each estimate version
        enters through ``EstimateVersionInput.hash_view`` (its ``direction`` only when it differs
        from the B3-DG-17 default; ENC-VC-direction), each SSP version through
        ``SspVersionInput.hash_view`` (an entry's ``quantity_unit`` only when declared;
        D-97 (3)) and each posted amount through ``PostedAmountInput.hash_view`` (its
        ``reason_code`` only when set, S14-R-27; its ``rate_refs`` only when present, S14-R-28)."""
        view = {item.name: getattr(self, item.name) for item in fields(self)}
        del view["known_at"]
        view["estimate_versions"] = tuple(item.hash_view() for item in self.estimate_versions)
        # D-97 (3): an entry's quantity_unit enters only when declared (SspEntryInput.hash_view).
        view["ssp_versions"] = tuple(item.hash_view() for item in self.ssp_versions)
        view["posted"] = tuple(item.hash_view() for item in self.posted)
        return sha256_hex(view)


# --- Output bundle (ENGINE_SPEC §0.5) ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ContractVersionOut:
    """T-CON-08 columns without surrogate ids; the orchestrator assigns ``version_no``."""

    subject_key: str
    columns: Mapping[str, object]  # 04 column name -> value
    trace_nodes: Mapping[str, str]  # measure -> trace node id


@dataclass(frozen=True, slots=True)
class ObligationVersionOut:
    """T-CON-11 columns of one obligation version."""

    subject_key: str  # obligation subject key
    columns: Mapping[str, object]
    trace_nodes: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class BalanceOut:
    """T-CON-09 labelled balances of a contract and entity at a period end (stage 10)."""

    subject_key: str  # "<contract external_id>@<entity code>"
    period_key: str
    columns: Mapping[str, object]
    trace_nodes: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class CostAssetVersionOut:
    """T-CON-16 columns of a contract cost asset version (stage 11)."""

    subject_key: str  # "<contract external_id>/COST/<local event key>"
    columns: Mapping[str, object]
    trace_nodes: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class LossProvisionOut:
    """T-CON-17 columns of a loss provision version (stage 11)."""

    subject_key: str  # loss unit
    period_key: str
    columns: Mapping[str, object]
    trace_nodes: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class FxLayerMovementOut:
    """T-CON-18 columns of one FX layer movement (stage 12)."""

    subject_key: str  # "<group code>@<entity code>/<layer_key>"
    columns: Mapping[str, object]
    trace_nodes: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class IntentLine:
    """One line of a posting intent (S14-R-13, S14-R-15)."""

    line_key: str
    side: str  # "D" | "C"
    account_role: str  # E-01; never RETAINED_EARNINGS or FINANCING_OBLIGATION (D-14a)
    clearing_purpose: str | None  # BILLING_CLEARING lines only (E-109)
    counterparty_entity: str | None  # intercompany roles only
    account_code: str
    amount_txn: int  # minor units, positive
    amount_functional: int  # minor units, positive
    txn_currency: str
    functional_currency: str
    dimensions: Mapping[str, str]  # JET rule R3
    source_event_key: str | None  # None for a cumulative delta (L2-5-Q-36)
    trace_node_id: str
    # S14-R-13a (rev 1.25; D-98 95): the ENG-06-ordered keys of the events of the delta's subject
    # first included in the computation; the lineage of a cumulative amount, not an apportionment.
    source_event_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PostingIntent:
    """A balanced journal entry of one book (S14-R-12, S14-R-15; D-16)."""

    entry_key: str
    book_code: str
    entity: str
    posting_period_key: str
    origin_period_key: str | None
    entry_kind: str  # E-29
    posting_class: str  # "EVENT" | "TIME"
    subject_key: str
    reason_code: str | None
    lines: tuple[IntentLine, ...]


@dataclass(frozen=True, slots=True)
class ProposalOut:
    """An engine-proposed treatment (CV-16): modification treatments or discount exceptions."""

    kind: str  # "MODIFICATION_TREATMENT" | "DISCOUNT_EXCEPTION"
    subject_key: str
    summary: str | None  # E-23 summary of a modification proposal
    treatments: Mapping[str, str]  # obligation key -> E-23 literal
    detail: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class TimeTrigger:
    """RCP-10 time trigger (CV-27); 1.0 emits only ``MATERIAL_RIGHT_EXPIRY``."""

    kind: str
    date: _Date
    subject_key: str


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A non-blocking finding (CV-41); no personal data (DG-ENG-06)."""

    code: str  # 04 §15.4
    severity: str  # "WARNING" | "INFO"
    book_code: str | None
    subject_key: str | None
    event_key: str | None
    detail: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class BookOutput:
    book_code: str
    # None for the LEGACY book, which carries only posting intents and trace
    contract_version: ContractVersionOut | None
    status_in_book: tuple[tuple[str, str], ...]  # (contract key, E-17) per member
    obligation_versions: tuple[ObligationVersionOut, ...]  # subject key
    balances: tuple[BalanceOut, ...]  # subject key
    schedules: tuple[ScheduleLineOut, ...]  # (schedule_kind, subject_key, line_type, period start)
    cost_asset_versions: tuple[CostAssetVersionOut, ...]
    loss_provision_versions: tuple[LossProvisionOut, ...]
    fx_layer_movements: tuple[FxLayerMovementOut, ...]
    posting_intents: tuple[PostingIntent, ...]  # balanced per entry
    proposals: tuple[ProposalOut, ...]  # (kind, subject key)
    time_triggers: tuple[TimeTrigger, ...]  # (date, kind, subject key)
    trace: Trace  # one per book
    # (line key, ((rate key, version key), ...)) of every foreign-currency posting line, sorted by
    # line key: PostingState.line_rates (REQ-FX-006; D-88 L7-6-Q-1); () for the LEGACY book
    line_rates: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = ()


@dataclass(frozen=True, slots=True)
class OutputBundle:
    """The result of one computation (DG §7 field list; ENGINE_SPEC §0.5)."""

    engine_version: str
    input_sha256: str
    books: tuple[BookOutput, ...]  # RCP-11 order
    diagnostics: tuple[Diagnostic, ...]  # CV-43 order

    def sha256(self) -> str:
        """CV-26: SHA-256 of the canonical output, ``input_sha256`` included."""
        return sha256_hex(self)
