"""Policy registry parameters: POLICIES.md §1 and §5.0 rows as 04 T-PLT-31 specs (dev-guide §5.15).

Generated from ``docs/accounting/POLICIES.md`` by ``erev registry-seed`` (``registry.seed``).
Never edit by hand: ``make registry-seed CHECK=1`` fails when this file is stale
(DG-KRN-REG-04, DG-LAY-07). ``None`` in ``default_asc606`` means there is no single framework
default and the engine applies the rule the §1 cell states; ``None`` in ``default_ifrs15`` or
``legacy_parity_value`` means the ASC606 default applies.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Literal

from erev_api.enums import RegistryCategory, RegistryScope


@dataclass(frozen=True, slots=True)
class RegistryParameterSpec:
    """One ``registry_parameter`` row (04 T-PLT-31)."""

    code: str
    pol_id: str | None
    category: RegistryCategory
    value_schema: Mapping[str, Any]
    default_asc606: Any
    default_ifrs15: Any | None
    is_forced_asc606: bool
    is_forced_ifrs15: bool
    legacy_parity_value: Any | None
    allowed_levels: frozenset[RegistryScope]
    pin: Literal["K", "P"]
    approval_code: Literal["CFG", "OVR", "EST", "JDG", "FIX"]
    description: str
    source_ref: str
    section: str


_SPECS: Final[tuple[RegistryParameterSpec, ...]] = (
    RegistryParameterSpec(
        code="rounding.posting_mode",
        pol_id="POL-001",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "HALF_UP",
            ],
        },
        default_asc606="HALF_UP",
        default_ifrs15="HALF_UP",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="HALF_UP",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="FIX",
        description="How are posted amounts quantised?",
        source_ref="POL-001",
        section="Platform, books, posting and rounding",
    ),
    RegistryParameterSpec(
        code="rounding.apportionment",
        pol_id="POL-002",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "LARGEST_REMAINDER",
            ],
        },
        default_asc606="LARGEST_REMAINDER",
        default_ifrs15="LARGEST_REMAINDER",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="LARGEST_REMAINDER",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="FIX",
        description="How is an amount split across POBs, entities, periods or layers?",
        source_ref="POL-002",
        section="Platform, books, posting and rounding",
    ),
    RegistryParameterSpec(
        code="rounding.schedule",
        pol_id="POL-003",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "CUMULATIVE",
            ],
        },
        default_asc606="CUMULATIVE",
        default_ifrs15="CUMULATIVE",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="CUMULATIVE",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="FIX",
        description="How are period amounts derived from progress?",
        source_ref="POL-003",
        section="Platform, books, posting and rounding",
    ),
    RegistryParameterSpec(
        code="billing.posting",
        pol_id="POL-004",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "ERP",
                "ENGINE",
            ],
        },
        default_asc606="ERP",
        default_ifrs15="ERP",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="ERP",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Who posts invoices and credit memos (Dr AR / Cr contract liability)?",
        source_ref="POL-004",
        section="Platform, books, posting and rounding",
    ),
    RegistryParameterSpec(
        code="je.posting_mode",
        pol_id="POL-005",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "GROSS",
                "DELTA",
            ],
        },
        default_asc606="GROSS",
        default_ifrs15="GROSS",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="GROSS",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Does the GL receive full entries or only the difference from pre-standard revenue already booked by the ERP?",
        source_ref="POL-005",
        section="Platform, books, posting and rounding",
    ),
    RegistryParameterSpec(
        code="je.summarization",
        pol_id="POL-006",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS",
                "LEGACY_CONTRACT_POB",
                "CONTRACT_ACCOUNT_DIMENSIONS",
            ],
        },
        default_asc606="ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS",
        default_ifrs15="ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="LEGACY_CONTRACT_POB",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="At what grain are journal lines summarised for GL export?",
        source_ref="POL-006",
        section="Platform, books, posting and rounding",
    ),
    RegistryParameterSpec(
        code="books.enabled",
        pol_id="POL-007",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "object",
            "properties": {
                "set": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "ASC606",
                            "IFRS15",
                            "LEGACY",
                        ],
                    },
                    "minItems": 1,
                    "uniqueItems": True,
                },
                "primary": {
                    "type": "string",
                    "enum": [
                        "ASC606",
                        "IFRS15",
                        "LEGACY",
                    ],
                },
            },
            "required": [
                "set",
                "primary",
            ],
            "additionalProperties": False,
        },
        default_asc606={
            "set": [
                "ASC606",
            ],
            "primary": "ASC606",
        },
        default_ifrs15={
            "set": [
                "IFRS15",
            ],
            "primary": "IFRS15",
        },
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value={
            "set": [
                "ASC606",
                "LEGACY",
            ],
            "primary": "ASC606",
        },
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Which books run for an entity, and which is primary?",
        source_ref="POL-007",
        section="Platform, books, posting and rounding",
    ),
    RegistryParameterSpec(
        code="legacy_book.source",
        pol_id="POL-008",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "PRE_STANDARD_EVENTS",
                "ERP_REVENUE_FEED",
            ],
        },
        default_asc606="PRE_STANDARD_EVENTS",
        default_ifrs15="PRE_STANDARD_EVENTS",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="PRE_STANDARD_EVENTS",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Where does pre-standard revenue for the `LEGACY` book come from?",
        source_ref="POL-008",
        section="Platform, books, posting and rounding",
    ),
    RegistryParameterSpec(
        code="step1.collectibility_threshold",
        pol_id="POL-011",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "US_PROBABLE",
                "IFRS_PROBABLE",
            ],
        },
        default_asc606="US_PROBABLE",
        default_ifrs15="IFRS_PROBABLE",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.BOOK,
            }
        ),
        pin="K",
        approval_code="JDG",
        description="Which collectibility threshold applies, and does the engine compute it?",
        source_ref="POL-011",
        section="Step 1: contract existence, term and combination",
    ),
    RegistryParameterSpec(
        code="step1.event_c_enabled",
        pol_id="POL-012",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "ENABLED",
                "DISABLED",
            ],
        },
        default_asc606="ENABLED",
        default_ifrs15="DISABLED",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.BOOK,
            }
        ),
        pin="K",
        approval_code="FIX",
        description="May nonrefundable consideration be recognised when the entity has stopped transferring and has no obligation to transfer more (25-7(c))?",
        source_ref="POL-012",
        section="Step 1: contract existence, term and combination",
    ),
    RegistryParameterSpec(
        code="step1.criteria_met_transition",
        pol_id="POL-013",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "CATCH_UP_AT_TRANSITION",
                "PROSPECTIVE_FROM_TRANSITION",
            ],
        },
        default_asc606="CATCH_UP_AT_TRANSITION",
        default_ifrs15="CATCH_UP_AT_TRANSITION",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="When a contract moves from `NOT_A_CONTRACT` to `ACTIVE`, how is performance already rendered treated?",
        source_ref="POL-013",
        section="Step 1: contract existence, term and combination",
    ),
    RegistryParameterSpec(
        code="step1.term_with_termination_rights",
        pol_id="POL-014",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "TO_EARLIEST_TERMINATION_WITHOUT_SUBSTANTIVE_PENALTY",
                "STATED_TERM",
            ],
        },
        default_asc606="TO_EARLIEST_TERMINATION_WITHOUT_SUBSTANTIVE_PENALTY",
        default_ifrs15="TO_EARLIEST_TERMINATION_WITHOUT_SUBSTANTIVE_PENALTY",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="STATED_TERM",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
                RegistryScope.CONTRACT,
            }
        ),
        pin="K",
        approval_code="OVR",
        description="What is the accounting term when the customer can terminate for convenience?",
        source_ref="POL-014",
        section="Step 1: contract existence, term and combination",
    ),
    RegistryParameterSpec(
        code="step1.portfolio_approach",
        pol_id="POL-015",
        category=RegistryCategory.PRACTICAL_EXPEDIENT,
        value_schema={
            "type": "string",
            "enum": [
                "DISABLED",
                "ENABLED",
            ],
        },
        default_asc606="DISABLED",
        default_ifrs15="DISABLED",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="DISABLED",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
                RegistryScope.PRODUCT,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="May the guidance be applied to a portfolio of similar contracts or POBs?",
        source_ref="POL-015",
        section="Step 1: contract existence, term and combination",
    ),
    RegistryParameterSpec(
        code="combination.detection_window_days",
        pol_id="POL-016",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "integer",
            "minimum": 0,
            "maximum": 365,
        },
        default_asc606=30,
        default_ifrs15=30,
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=0,
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Within how many days must contracts with the same customer group be signed to be suggested for combination?",
        source_ref="POL-016",
        section="Step 1: contract existence, term and combination",
    ),
    RegistryParameterSpec(
        code="pob.immaterial_promise_relief",
        pol_id="POL-020",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "anyOf": [
                {
                    "type": "string",
                    "enum": [
                        "ASSESS_ALL",
                        "APPLY_RELIEF",
                    ],
                },
                {
                    "type": "object",
                    "properties": {
                        "option": {
                            "const": "APPLY_RELIEF",
                        },
                        "immaterial_threshold_pct": {
                            "type": "string",
                            "format": "decimal",
                            "default": "0.01",
                            "x-maximum": "0.05",
                        },
                    },
                    "required": [
                        "option",
                    ],
                    "additionalProperties": False,
                },
            ],
        },
        default_asc606="ASSESS_ALL",
        default_ifrs15="ASSESS_ALL",
        is_forced_asc606=False,
        is_forced_ifrs15=True,
        legacy_parity_value="ASSESS_ALL",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
                RegistryScope.ENTITY,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="May promises that are immaterial in the context of the contract be left unassessed?",
        source_ref="POL-020",
        section="Step 2: performance obligations",
    ),
    RegistryParameterSpec(
        code="pob.shipping_as_fulfilment",
        pol_id="POL-021",
        category=RegistryCategory.PRACTICAL_EXPEDIENT,
        value_schema={
            "type": "string",
            "enum": [
                "TRUE",
                "FALSE",
            ],
        },
        default_asc606="TRUE",
        default_ifrs15="FALSE",
        is_forced_asc606=False,
        is_forced_ifrs15=True,
        legacy_parity_value="FALSE",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
                RegistryScope.ENTITY,
                RegistryScope.PRODUCT,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="Are shipping and handling activities after control transfers treated as fulfilment costs?",
        source_ref="POL-021",
        section="Step 2: performance obligations",
    ),
    RegistryParameterSpec(
        code="pob.assurance_warranty_accrual",
        pol_id="POL-022",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "ENGINE",
                "EXTERNAL",
            ],
        },
        default_asc606="ENGINE",
        default_ifrs15="ENGINE",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="EXTERNAL",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Does the engine post the Subtopic 460-10 cost accrual for assurance-type warranties?",
        source_ref="POL-022",
        section="Step 2: performance obligations",
    ),
    RegistryParameterSpec(
        code="licence.nature_model",
        pol_id="POL-024",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "FUNCTIONAL_SYMBOLIC",
                "ACTIVITIES_SIGNIFICANTLY_AFFECT_IP",
            ],
        },
        default_asc606="FUNCTIONAL_SYMBOLIC",
        default_ifrs15="ACTIVITIES_SIGNIFICANTLY_AFFECT_IP",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.BOOK,
            }
        ),
        pin="K",
        approval_code="JDG",
        description="Which licence-nature assessment applies?",
        source_ref="POL-024",
        section="Step 2: performance obligations",
    ),
    RegistryParameterSpec(
        code="licence.renewal_start",
        pol_id="POL-025",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "RENEWAL_PERIOD_START",
                "LATER_OF_AGREEMENT_AND_AVAILABILITY",
            ],
        },
        default_asc606="RENEWAL_PERIOD_START",
        default_ifrs15="LATER_OF_AGREEMENT_AND_AVAILABILITY",
        is_forced_asc606=True,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.BOOK,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="When may revenue for a licence renewal begin?",
        source_ref="POL-025",
        section="Step 2: performance obligations",
    ),
    RegistryParameterSpec(
        code="material_right.ssp_method",
        pol_id="POL-026",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "DISCOUNT_X_LIKELIHOOD",
                "RENEWAL_ALTERNATIVE",
                "ENTERED_AMOUNT",
            ],
        },
        default_asc606="DISCOUNT_X_LIKELIHOOD",
        default_ifrs15="DISCOUNT_X_LIKELIHOOD",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="ENTERED_AMOUNT",
        allowed_levels=frozenset(
            {
                RegistryScope.PRODUCT,
                RegistryScope.CONTRACT,
                RegistryScope.OBLIGATION,
            }
        ),
        pin="K",
        approval_code="EST",
        description="How is the SSP of an option that provides a material right estimated?",
        source_ref="POL-026",
        section="Step 2: performance obligations",
    ),
    RegistryParameterSpec(
        code="material_right.exercise",
        pol_id="POL-028",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "CONTINUATION",
                "MODIFICATION",
            ],
        },
        default_asc606="CONTINUATION",
        default_ifrs15="CONTINUATION",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="MODIFICATION",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="How is the exercise of a material right accounted for?",
        source_ref="POL-028",
        section="Step 2: performance obligations",
    ),
    RegistryParameterSpec(
        code="upfront_fee.recognition_period",
        pol_id="POL-029",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "CONTRACT_TERM",
                "EXPECTED_BENEFIT_PERIOD",
            ],
        },
        default_asc606="EXPECTED_BENEFIT_PERIOD",
        default_ifrs15="EXPECTED_BENEFIT_PERIOD",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.PRODUCT,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="Over what period is a nonrefundable upfront fee recognised when renewal options give the customer a material right?",
        source_ref="POL-029",
        section="Step 2: performance obligations",
    ),
    RegistryParameterSpec(
        code="pob.principal_or_agent",
        pol_id="POL-030",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "PRINCIPAL",
                "AGENT",
            ],
        },
        default_asc606=None,
        default_ifrs15=None,
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="PRINCIPAL",
        allowed_levels=frozenset(
            {
                RegistryScope.PRODUCT,
                RegistryScope.OBLIGATION,
            }
        ),
        pin="K",
        approval_code="JDG",
        description="Is the entity principal or agent for each specified good or service?",
        source_ref="POL-030",
        section="Step 2: performance obligations",
    ),
    RegistryParameterSpec(
        code="vc.estimation_method",
        pol_id="POL-040",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "EXPECTED_VALUE",
                "MOST_LIKELY_AMOUNT",
                "ENTERED_AMOUNT",
            ],
        },
        default_asc606=None,
        default_ifrs15=None,
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="ENTERED_AMOUNT",
        allowed_levels=frozenset(
            {
                RegistryScope.CONTRACT,
            }
        ),
        pin="K",
        approval_code="EST",
        description="Which method estimates each VC element?",
        source_ref="POL-040",
        section="Step 3: transaction price",
    ),
    RegistryParameterSpec(
        code="vc.constraint",
        pol_id="POL-041",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "PREPARER_CONSTRAINED_AMOUNT",
                "NOT_APPLIED",
            ],
        },
        default_asc606="PREPARER_CONSTRAINED_AMOUNT",
        default_ifrs15="PREPARER_CONSTRAINED_AMOUNT",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="NOT_APPLIED",
        allowed_levels=frozenset(
            {
                RegistryScope.CONTRACT,
            }
        ),
        pin="P",
        approval_code="EST",
        description="How is the constraint applied?",
        source_ref="POL-041",
        section="Step 3: transaction price",
    ),
    RegistryParameterSpec(
        code="vc.reassessment_gate",
        pol_id="POL-042",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "REQUIRE_VERSION_OR_ATTESTATION",
                "NOT_ENFORCED",
            ],
        },
        default_asc606="REQUIRE_VERSION_OR_ATTESTATION",
        default_ifrs15="REQUIRE_VERSION_OR_ATTESTATION",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="NOT_ENFORCED",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Must every open VC element have an estimate version for each period end?",
        source_ref="POL-042",
        section="Step 3: transaction price",
    ),
    RegistryParameterSpec(
        code="vc.estimate_import_semantics",
        pol_id="POL-043",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "FULL_ESTIMATE",
                "DELTA",
            ],
        },
        default_asc606="FULL_ESTIMATE",
        default_ifrs15="FULL_ESTIMATE",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="DELTA",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Do imported VC rows carry the full estimate or a change?",
        source_ref="POL-043",
        section="Step 3: transaction price",
    ),
    RegistryParameterSpec(
        code="vc.targeted_allocation_tolerance",
        pol_id="POL-044",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "anyOf": [
                {
                    "type": "string",
                    "format": "decimal",
                    "x-minimum": "0",
                    "x-maximum": "1",
                },
                {
                    "type": "string",
                    "enum": [
                        "NOT_ENFORCED",
                    ],
                },
            ],
        },
        default_asc606="0.20",
        default_ifrs15="0.20",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="NOT_ENFORCED",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="OVR",
        description="When VC is allocated entirely to some POBs (32-40), how far may the result depart from relative SSP before review is required?",
        source_ref="POL-044",
        section="Step 3: transaction price",
    ),
    RegistryParameterSpec(
        code="tp.sales_tax_exclusion",
        pol_id="POL-045",
        category=RegistryCategory.PRACTICAL_EXPEDIENT,
        value_schema={
            "type": "string",
            "enum": [
                "EXCLUDE_ALL_IN_SCOPE",
                "ASSESS_EACH_TAX",
            ],
        },
        default_asc606="EXCLUDE_ALL_IN_SCOPE",
        default_ifrs15="ASSESS_EACH_TAX",
        is_forced_asc606=False,
        is_forced_ifrs15=True,
        legacy_parity_value="EXCLUDE_ALL_IN_SCOPE",
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Are taxes collected from customers excluded from the transaction price?",
        source_ref="POL-045",
        section="Step 3: transaction price",
    ),
    RegistryParameterSpec(
        code="sfc.one_year_expedient",
        pol_id="POL-046",
        category=RegistryCategory.PRACTICAL_EXPEDIENT,
        value_schema={
            "type": "string",
            "enum": [
                "APPLY",
                "DO_NOT_APPLY",
            ],
        },
        default_asc606="APPLY",
        default_ifrs15="APPLY",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="APPLY",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
                RegistryScope.ENTITY,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="Is the financing adjustment skipped when the gap between transfer and payment is one year or less at inception?",
        source_ref="POL-046",
        section="Step 3: transaction price",
    ),
    RegistryParameterSpec(
        code="sfc.discount_rate_basis",
        pol_id="POL-047",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "object",
            "properties": {
                "basis": {
                    "type": "string",
                    "enum": [
                        "CUSTOMER_CREDIT_RATE",
                        "ENTITY_BORROWING_RATE",
                    ],
                },
                "annual_rate": {
                    "type": "string",
                    "format": "decimal",
                },
                "compounding": {
                    "type": "string",
                    "enum": [
                        "MONTHLY",
                        "ANNUAL",
                    ],
                    "default": "MONTHLY",
                },
            },
            "required": [
                "basis",
                "annual_rate",
            ],
            "additionalProperties": False,
        },
        default_asc606={
            "basis": "CUSTOMER_CREDIT_RATE",
            "compounding": "MONTHLY",
        },
        default_ifrs15={
            "basis": "CUSTOMER_CREDIT_RATE",
            "compounding": "MONTHLY",
        },
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.CONTRACT,
            }
        ),
        pin="K",
        approval_code="EST",
        description="Which rate discounts a significant financing component, and how does it compound?",
        source_ref="POL-047",
        section="Step 3: transaction price",
    ),
    RegistryParameterSpec(
        code="noncash.measurement_date",
        pol_id="POL-048",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "CONTRACT_INCEPTION",
                "RECEIPT_DATE",
                "SATISFACTION_DATE",
            ],
        },
        default_asc606="CONTRACT_INCEPTION",
        default_ifrs15="CONTRACT_INCEPTION",
        is_forced_asc606=True,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.BOOK,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="At what date is noncash consideration measured?",
        source_ref="POL-048",
        section="Step 3: transaction price",
    ),
    RegistryParameterSpec(
        code="cpc.incentive_asset_release_basis",
        pol_id="POL-049",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "EXPECTED_PURCHASES",
                "COMMITTED_PURCHASES",
            ],
        },
        default_asc606="EXPECTED_PURCHASES",
        default_ifrs15="EXPECTED_PURCHASES",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.CONTRACT,
            }
        ),
        pin="K",
        approval_code="EST",
        description="How is an upfront payment to a customer that precedes revenue released against revenue?",
        source_ref="POL-049",
        section="Step 3: transaction price",
    ),
    RegistryParameterSpec(
        code="returns.model",
        pol_id="POL-051",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "EXPECTED_RETURNS",
                "ACTUAL_RETURNS_ONLY",
            ],
        },
        default_asc606="EXPECTED_RETURNS",
        default_ifrs15="EXPECTED_RETURNS",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="ACTUAL_RETURNS_ONLY",
        allowed_levels=frozenset(
            {
                RegistryScope.PRODUCT,
                RegistryScope.CONTRACT,
                RegistryScope.OBLIGATION,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="Is revenue reduced for expected returns at transfer?",
        source_ref="POL-051",
        section="Step 3: transaction price",
    ),
    RegistryParameterSpec(
        code="returns.reversal_rate",
        pol_id="POL-052",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "AVERAGE_CARRYING_RATE",
                "CURRENT_REMAINING_RATE",
            ],
        },
        default_asc606="AVERAGE_CARRYING_RATE",
        default_ifrs15="AVERAGE_CARRYING_RATE",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="CURRENT_REMAINING_RATE",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="At what rate is revenue reversed for returned units in excess of the refund liability?",
        source_ref="POL-052",
        section="Step 3: transaction price",
    ),
    RegistryParameterSpec(
        code="returns.returned_units_scope",
        pol_id="POL-053",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "REDUCE_CONTRACT_QUANTITY",
                "RESTORE_REMAINING_QUANTITY",
            ],
        },
        default_asc606="REDUCE_CONTRACT_QUANTITY",
        default_ifrs15="REDUCE_CONTRACT_QUANTITY",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="RESTORE_REMAINING_QUANTITY",
        allowed_levels=frozenset(
            {
                RegistryScope.PRODUCT,
                RegistryScope.CONTRACT,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="Does a returned unit leave the contract or become deliverable again?",
        source_ref="POL-053",
        section="Step 3: transaction price",
    ),
    RegistryParameterSpec(
        code="breakage.method",
        pol_id="POL-055",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "PROPORTIONAL_TO_EXERCISE",
                "WHEN_REMOTE",
            ],
        },
        default_asc606="PROPORTIONAL_TO_EXERCISE",
        default_ifrs15="PROPORTIONAL_TO_EXERCISE",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.PRODUCT,
            }
        ),
        pin="K",
        approval_code="EST",
        description="How is expected breakage on nonrefundable prepayments recognised?",
        source_ref="POL-055",
        section="Step 3: transaction price",
    ),
    RegistryParameterSpec(
        code="royalty.unreported_sales",
        pol_id="POL-056",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "ACCRUE_ESTIMATE",
                "AS_REPORTED",
            ],
        },
        default_asc606="ACCRUE_ESTIMATE",
        default_ifrs15="ACCRUE_ESTIMATE",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.CONTRACT,
            }
        ),
        pin="P",
        approval_code="EST",
        description="Are royalties on sales or usage that have occurred but are not yet reported accrued?",
        source_ref="POL-056",
        section="Step 3: transaction price",
    ),
    RegistryParameterSpec(
        code="royalty.minimum_guarantee",
        pol_id="POL-057",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "FIXED_ON_LICENCE_PATTERN",
                "ROYALTY_WITH_FLOOR_TRUE_UP",
            ],
        },
        default_asc606="FIXED_ON_LICENCE_PATTERN",
        default_ifrs15="FIXED_ON_LICENCE_PATTERN",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.CONTRACT,
            }
        ),
        pin="K",
        approval_code="JDG",
        description="How is a fixed minimum guarantee in a royalty-bearing licence recognised?",
        source_ref="POL-057",
        section="Step 3: transaction price",
    ),
    RegistryParameterSpec(
        code="ssp.version_basis",
        pol_id="POL-070",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "LATEST_APPROVED_EFFECTIVE_AT_INCEPTION",
                "NAMED_VERSION",
            ],
        },
        default_asc606="LATEST_APPROVED_EFFECTIVE_AT_INCEPTION",
        default_ifrs15="LATEST_APPROVED_EFFECTIVE_AT_INCEPTION",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="NAMED_VERSION",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
                RegistryScope.OBLIGATION,
            }
        ),
        pin="K",
        approval_code="OVR",
        description="Which SSP book version prices a contract at inception?",
        source_ref="POL-070",
        section="Step 4: allocation and SSP",
    ),
    RegistryParameterSpec(
        code="ssp.inside_range_point",
        pol_id="POL-071",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "CONTRACT_PRICE",
                "MIDPOINT",
            ],
        },
        default_asc606="CONTRACT_PRICE",
        default_ifrs15="CONTRACT_PRICE",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="CONTRACT_PRICE",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
                RegistryScope.ENTITY,
                RegistryScope.PRODUCT,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="Which point is the SSP when the stated price is inside the SSP range?",
        source_ref="POL-071",
        section="Step 4: allocation and SSP",
    ),
    RegistryParameterSpec(
        code="ssp.outside_range_point",
        pol_id="POL-072",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "NEAREST_BOUND",
                "MIDPOINT",
                "LOW_POINT",
                "HIGH_POINT",
                "OBSERVABLE_POINT",
            ],
        },
        default_asc606="NEAREST_BOUND",
        default_ifrs15="NEAREST_BOUND",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="NEAREST_BOUND",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
                RegistryScope.ENTITY,
                RegistryScope.PRODUCT,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="Which point is the SSP when the stated price is outside the range?",
        source_ref="POL-072",
        section="Step 4: allocation and SSP",
    ),
    RegistryParameterSpec(
        code="ssp.range_validation",
        pol_id="POL-073",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "anyOf": [
                {
                    "type": "object",
                    "properties": {
                        "max_half_width_pct": {
                            "type": "string",
                            "format": "decimal",
                        },
                        "min_coverage_pct": {
                            "type": "string",
                            "format": "decimal",
                        },
                        "mode": {
                            "type": "string",
                            "enum": [
                                "WARN",
                                "BLOCK",
                            ],
                        },
                    },
                    "required": [
                        "max_half_width_pct",
                        "min_coverage_pct",
                        "mode",
                    ],
                    "additionalProperties": False,
                },
                {
                    "type": "string",
                    "enum": [
                        "NOT_ENFORCED",
                    ],
                },
            ],
        },
        default_asc606={
            "max_half_width_pct": "0.20",
            "min_coverage_pct": "0.50",
            "mode": "WARN",
        },
        default_ifrs15={
            "max_half_width_pct": "0.20",
            "min_coverage_pct": "0.50",
            "mode": "WARN",
        },
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="NOT_ENFORCED",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Which range statistics are checked when an SSP version is published?",
        source_ref="POL-073",
        section="Step 4: allocation and SSP",
    ),
    RegistryParameterSpec(
        code="ssp.method_hierarchy",
        pol_id="POL-074",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "anyOf": [
                {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "observable",
                            "adjusted_market",
                            "cost_plus_margin",
                            "residual",
                        ],
                    },
                    "uniqueItems": True,
                },
                {
                    "type": "string",
                    "enum": [
                        "legacy_range",
                    ],
                },
            ],
        },
        default_asc606=[
            "observable",
            "adjusted_market",
            "cost_plus_margin",
            "residual",
        ],
        default_ifrs15=[
            "observable",
            "adjusted_market",
            "cost_plus_margin",
            "residual",
        ],
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="legacy_range",
        allowed_levels=frozenset(
            {
                RegistryScope.PRODUCT,
            }
        ),
        pin="K",
        approval_code="FIX",
        description="Which estimation methods may an SSP row use, in what order of preference?",
        source_ref="POL-074",
        section="Step 4: allocation and SSP",
    ),
    RegistryParameterSpec(
        code="ssp.residual_failure",
        pol_id="POL-075",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "REQUIRE_ESTIMATED_SSP",
                "BLOCK",
            ],
        },
        default_asc606="REQUIRE_ESTIMATED_SSP",
        default_ifrs15="REQUIRE_ESTIMATED_SSP",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="OVR",
        description="What happens when a residual SSP is not permitted or fails its checks?",
        source_ref="POL-075",
        section="Step 4: allocation and SSP",
    ),
    RegistryParameterSpec(
        code="alloc.discount_exception",
        pol_id="POL-076",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "anyOf": [
                {
                    "type": "string",
                    "enum": [
                        "DISABLED",
                        "PROPOSE_WITH_APPROVAL",
                    ],
                },
                {
                    "type": "object",
                    "properties": {
                        "option": {
                            "const": "PROPOSE_WITH_APPROVAL",
                        },
                        "bundle_discount_tolerance_pp": {
                            "type": "string",
                            "format": "decimal",
                            "default": "0.02",
                        },
                    },
                    "required": [
                        "option",
                    ],
                    "additionalProperties": False,
                },
            ],
        },
        default_asc606="PROPOSE_WITH_APPROVAL",
        default_ifrs15="PROPOSE_WITH_APPROVAL",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="DISABLED",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="OVR",
        description="May a discount be allocated entirely to some POBs?",
        source_ref="POL-076",
        section="Step 4: allocation and SSP",
    ),
    RegistryParameterSpec(
        code="alloc.zero_total_ssp",
        pol_id="POL-077",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "REJECT",
            ],
        },
        default_asc606="REJECT",
        default_ifrs15="REJECT",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="REJECT",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="FIX",
        description="What if every POB of a contract has SSP 0?",
        source_ref="POL-077",
        section="Step 4: allocation and SSP",
    ),
    RegistryParameterSpec(
        code="alloc.negative_booking_lines",
        pol_id="POL-078",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "REJECT_ROUTE_TO_RETURNS_OR_VC",
            ],
        },
        default_asc606="REJECT_ROUTE_TO_RETURNS_OR_VC",
        default_ifrs15="REJECT_ROUTE_TO_RETURNS_OR_VC",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="REJECT_ROUTE_TO_RETURNS_OR_VC",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="FIX",
        description="May a booking line carry a negative quantity or price?",
        source_ref="POL-078",
        section="Step 4: allocation and SSP",
    ),
    RegistryParameterSpec(
        code="ssp.currency_conversion",
        pol_id="POL-079",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "CONVERT_AT_INCEPTION_SPOT",
                "CURRENCY_SPECIFIC_BOOK_REQUIRED",
            ],
        },
        default_asc606="CONVERT_AT_INCEPTION_SPOT",
        default_ifrs15="CONVERT_AT_INCEPTION_SPOT",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="How is an SSP expressed in another currency converted to the contract currency?",
        source_ref="POL-079",
        section="Step 4: allocation and SSP",
    ),
    RegistryParameterSpec(
        code="mod.ssp_basis",
        pol_id="POL-080",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "D18_DEFAULT",
                "INCEPTION_ALL",
                "LEGACY_CARRIED_PLUS_FILE_VERSION",
            ],
        },
        default_asc606="D18_DEFAULT",
        default_ifrs15="D18_DEFAULT",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="LEGACY_CARRIED_PLUS_FILE_VERSION",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
                RegistryScope.OBLIGATION,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="Which SSPs weight a modification's reallocation?",
        source_ref="POL-080",
        section="Step 4: allocation and SSP",
    ),
    RegistryParameterSpec(
        code="mod.reduction_ssp",
        pol_id="POL-081",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "CARRIED_UNIT_SSP",
                "CLAMPED_MOD_PRICE",
            ],
        },
        default_asc606="CARRIED_UNIT_SSP",
        default_ifrs15="CARRIED_UNIT_SSP",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="CLAMPED_MOD_PRICE",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="At what SSP are removed units taken out of the weights?",
        source_ref="POL-081",
        section="Step 4: allocation and SSP",
    ),
    RegistryParameterSpec(
        code="recognition.time_convention",
        pol_id="POL-090",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "DAILY",
                "MONTHLY_EVEN",
                "MID_MONTH",
            ],
        },
        default_asc606="DAILY",
        default_ifrs15="DAILY",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
                RegistryScope.PRODUCT,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="How is time-elapsed progress measured?",
        source_ref="POL-090",
        section="Step 5: recognition",
    ),
    RegistryParameterSpec(
        code="recognition.measure_of_progress",
        pol_id="POL-091",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "TIME_ELAPSED",
                "UNITS_DELIVERED",
                "MILESTONE",
                "COST_TO_COST",
                "LABOUR_HOURS",
                "RIGHT_TO_INVOICE",
                "COST_RECOVERY",
            ],
        },
        default_asc606=None,
        default_ifrs15=None,
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="UNITS_DELIVERED",
        allowed_levels=frozenset(
            {
                RegistryScope.PRODUCT,
                RegistryScope.OBLIGATION,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="Which measure applies to an over-time POB?",
        source_ref="POL-091",
        section="Step 5: recognition",
    ),
    RegistryParameterSpec(
        code="recognition.right_to_invoice_guard",
        pol_id="POL-092",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "BLOCK_IF_NONLINEAR_OR_FIXED_COMPONENT",
                "ALLOW",
            ],
        },
        default_asc606="BLOCK_IF_NONLINEAR_OR_FIXED_COMPONENT",
        default_ifrs15="BLOCK_IF_NONLINEAR_OR_FIXED_COMPONENT",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="OVR",
        description="When is the right-to-invoice expedient blocked?",
        source_ref="POL-092",
        section="Step 5: recognition",
    ),
    RegistryParameterSpec(
        code="bill_and_hold.custodial_pob",
        pol_id="POL-094",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "CREATE_WHEN_SSP_PROVIDED",
                "NEVER",
            ],
        },
        default_asc606="CREATE_WHEN_SSP_PROVIDED",
        default_ifrs15="CREATE_WHEN_SSP_PROVIDED",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="JDG",
        description="Does an approved bill-and-hold create a custodial POB?",
        source_ref="POL-094",
        section="Step 5: recognition",
    ),
    RegistryParameterSpec(
        code="recognition.control_trigger",
        pol_id="POL-095",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "ANY_TRANSFER",
                "ACCEPTANCE_ONLY",
                "SELL_THROUGH_ONLY",
            ],
        },
        default_asc606="ANY_TRANSFER",
        default_ifrs15="ANY_TRANSFER",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.PRODUCT,
                RegistryScope.OBLIGATION,
            }
        ),
        pin="K",
        approval_code="JDG",
        description="Which recorded triggers may transfer control of a POB whose terms include a customer-acceptance clause or a consignment arrangement?",
        source_ref="POL-095",
        section="Step 5: recognition",
    ),
    RegistryParameterSpec(
        code="mod.route_selection",
        pol_id="POL-100",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "ENGINE_PROPOSES_PREPARER_CONFIRMS",
                "USER_SELECTED_TEMPLATE",
            ],
        },
        default_asc606="ENGINE_PROPOSES_PREPARER_CONFIRMS",
        default_ifrs15="ENGINE_PROPOSES_PREPARER_CONFIRMS",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="USER_SELECTED_TEMPLATE",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="OVR",
        description="Who selects the 25-12 or 25-13 route?",
        source_ref="POL-100",
        section="Contract modifications",
    ),
    RegistryParameterSpec(
        code="mod.separate_contract_price_test",
        pol_id="POL-101",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "anyOf": [
                {
                    "type": "string",
                    "enum": [
                        "WITHIN_MOD_DATE_RANGE",
                    ],
                },
                {
                    "type": "object",
                    "properties": {
                        "option": {
                            "const": "WITHIN_MOD_DATE_RANGE",
                        },
                        "point_tolerance_pct": {
                            "type": "string",
                            "format": "decimal",
                            "default": "0.00",
                        },
                    },
                    "required": [
                        "option",
                    ],
                    "additionalProperties": False,
                },
            ],
        },
        default_asc606="WITHIN_MOD_DATE_RANGE",
        default_ifrs15="WITHIN_MOD_DATE_RANGE",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="OVR",
        description='When does the price of added distinct goods "reflect SSP" (25-12(b))?',
        source_ref="POL-101",
        section="Contract modifications",
    ),
    RegistryParameterSpec(
        code="mod.catch_up_scope",
        pol_id="POL-102",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "PARTIALLY_SATISFIED_NONDISTINCT_ONLY",
                "ALL_POBS_FULL_REALLOCATION",
            ],
        },
        default_asc606="PARTIALLY_SATISFIED_NONDISTINCT_ONLY",
        default_ifrs15="PARTIALLY_SATISFIED_NONDISTINCT_ONLY",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="ALL_POBS_FULL_REALLOCATION",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="Which POBs may receive a cumulative catch-up in a modification that is not a separate contract?",
        source_ref="POL-102",
        section="Contract modifications",
    ),
    RegistryParameterSpec(
        code="mod.mixed_allocation",
        pol_id="POL-103",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "REMAINING_TP",
                "TOTAL_TP",
                "ATTRIBUTE_BY_LINE",
            ],
        },
        default_asc606="REMAINING_TP",
        default_ifrs15="REMAINING_TP",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="TOTAL_TP",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="In a 25-13(c) modification, which consideration is reallocated?",
        source_ref="POL-103",
        section="Contract modifications",
    ),
    RegistryParameterSpec(
        code="mod.price_change_on_satisfied_performance",
        pol_id="POL-104",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "RECOGNISE_IN_PERIOD_ON_INCEPTION_BASIS",
                "POOL_WITH_REMAINING",
            ],
        },
        default_asc606="RECOGNISE_IN_PERIOD_ON_INCEPTION_BASIS",
        default_ifrs15="RECOGNISE_IN_PERIOD_ON_INCEPTION_BASIS",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="POOL_WITH_REMAINING",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="OVR",
        description="How is modification consideration that relates to goods already transferred accounted for?",
        source_ref="POL-104",
        section="Contract modifications",
    ),
    RegistryParameterSpec(
        code="mod.unpriced_change_orders",
        pol_id="POL-105",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "ESTIMATE_WITH_CONSTRAINT",
            ],
        },
        default_asc606="ESTIMATE_WITH_CONSTRAINT",
        default_ifrs15="ESTIMATE_WITH_CONSTRAINT",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="ESTIMATE_WITH_CONSTRAINT",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="EST",
        description="How is an approved change in scope with an undetermined price accounted for?",
        source_ref="POL-105",
        section="Contract modifications",
    ),
    RegistryParameterSpec(
        code="mod.post_modification_vc_routing",
        pol_id="POL-106",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "ASC_606_10_32_45",
            ],
        },
        default_asc606="ASC_606_10_32_45",
        default_ifrs15="ASC_606_10_32_45",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="FIX",
        description="To which POBs is a later change in VC promised before a modification allocated?",
        source_ref="POL-106",
        section="Contract modifications",
    ),
    RegistryParameterSpec(
        code="mod.catch_up_progress_basis",
        pol_id="POL-107",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "POB_MEASURE",
                "LEGACY_BY_TEMPLATE",
            ],
        },
        default_asc606="POB_MEASURE",
        default_ifrs15="POB_MEASURE",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="LEGACY_BY_TEMPLATE",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="FIX",
        description="Which progress measure drives catch-ups?",
        source_ref="POL-107",
        section="Contract modifications",
    ),
    RegistryParameterSpec(
        code="position.netting_unit",
        pol_id="POL-120",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "CONTRACT_ENTITY_BOOK",
            ],
        },
        default_asc606="CONTRACT_ENTITY_BOOK",
        default_ifrs15="CONTRACT_ENTITY_BOOK",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="CONTRACT_ENTITY_BOOK",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="FIX",
        description="At what unit are contract assets and contract liabilities netted?",
        source_ref="POL-120",
        section="Contract balances and presentation",
    ),
    RegistryParameterSpec(
        code="position.reclass_attribution_key",
        pol_id="POL-121",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "POB_DEBIT_POSITIONS",
                "CUMULATIVE_SSP_DELIVERED",
            ],
        },
        default_asc606="POB_DEBIT_POSITIONS",
        default_ifrs15="POB_DEBIT_POSITIONS",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="CUMULATIVE_SSP_DELIVERED",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="How is the period-end reclass attributed to POB-level account strings?",
        source_ref="POL-121",
        section="Contract balances and presentation",
    ),
    RegistryParameterSpec(
        code="balance.right_to_consideration",
        pol_id="POL-122",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "CONDITIONAL",
                "UNCONDITIONAL",
            ],
        },
        default_asc606=None,
        default_ifrs15=None,
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.PRODUCT,
                RegistryScope.OBLIGATION,
            }
        ),
        pin="K",
        approval_code="OVR",
        description="Is an earned but uninvoiced amount a conditional right (contract asset) or an unconditional right (unbilled receivable)?",
        source_ref="POL-122",
        section="Contract balances and presentation",
    ),
    RegistryParameterSpec(
        code="balance.position_invoice_basis",
        pol_id="POL-123",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "ERP_POSTED_INVOICES",
                "UNCONDITIONAL_INVOICES_ONLY",
            ],
        },
        default_asc606=None,
        default_ifrs15=None,
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="ERP_POSTED_INVOICES",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="FIX",
        description='Which invoices count as "billed or unconditionally due" in the position?',
        source_ref="POL-123",
        section="Contract balances and presentation",
    ),
    RegistryParameterSpec(
        code="balance.current_noncurrent",
        pol_id="POL-124",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "EXPECTED_TIMING_12_MONTHS",
                "NONE",
            ],
        },
        default_asc606="EXPECTED_TIMING_12_MONTHS",
        default_ifrs15="EXPECTED_TIMING_12_MONTHS",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="NONE",
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Are contract balances classified as current or noncurrent?",
        source_ref="POL-124",
        section="Contract balances and presentation",
    ),
    RegistryParameterSpec(
        code="balance.credit_losses",
        pol_id="POL-125",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "EXTERNAL_MODEL",
            ],
        },
        default_asc606="EXTERNAL_MODEL",
        default_ifrs15="EXTERNAL_MODEL",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="EXTERNAL_MODEL",
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="FIX",
        description="Does the engine measure expected credit losses on receivables and contract assets?",
        source_ref="POL-125",
        section="Contract balances and presentation",
    ),
    RegistryParameterSpec(
        code="rollforward.opening_liability_consumption",
        pol_id="POL-126",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "FIFO_WITHIN_CONTRACT",
                "FIFO_WITHIN_POB",
            ],
        },
        default_asc606="FIFO_WITHIN_CONTRACT",
        default_ifrs15="FIFO_WITHIN_CONTRACT",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="FIFO_WITHIN_CONTRACT",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="CFG",
        description='How is "revenue recognised from the opening contract liability" measured?',
        source_ref="POL-126",
        section="Contract balances and presentation",
    ),
    RegistryParameterSpec(
        code="balance.refund_liability_presentation",
        pol_id="POL-127",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "SEPARATE",
            ],
        },
        default_asc606="SEPARATE",
        default_ifrs15="SEPARATE",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="SEPARATE",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="FIX",
        description="Are refund liabilities netted into the contract position?",
        source_ref="POL-127",
        section="Contract balances and presentation",
    ),
    RegistryParameterSpec(
        code="balance.deposit_liability",
        pol_id="POL-128",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "DEPOSIT_LIABILITY",
            ],
        },
        default_asc606="DEPOSIT_LIABILITY",
        default_ifrs15="DEPOSIT_LIABILITY",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="FIX",
        description="Where do receipts go while a contract fails Step 1?",
        source_ref="POL-128",
        section="Contract balances and presentation",
    ),
    RegistryParameterSpec(
        code="costs.obtain_expedient",
        pol_id="POL-140",
        category=RegistryCategory.PRACTICAL_EXPEDIENT,
        value_schema={
            "type": "string",
            "enum": [
                "APPLY",
                "DO_NOT_APPLY",
            ],
        },
        default_asc606="APPLY",
        default_ifrs15="APPLY",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="APPLY",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
                RegistryScope.ENTITY,
                RegistryScope.PRODUCT,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="Are incremental costs of obtaining a contract expensed when the amortisation period would be one year or less?",
        source_ref="POL-140",
        section="Contract costs and loss contracts",
    ),
    RegistryParameterSpec(
        code="costs.amortisation_period",
        pol_id="POL-141",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "TERM_PLUS_EXPECTED_RENEWALS_UNLESS_COMMENSURATE",
                "CONTRACT_TERM",
                "EXPECTED_CUSTOMER_LIFE",
            ],
        },
        default_asc606="TERM_PLUS_EXPECTED_RENEWALS_UNLESS_COMMENSURATE",
        default_ifrs15="TERM_PLUS_EXPECTED_RENEWALS_UNLESS_COMMENSURATE",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.PRODUCT,
            }
        ),
        pin="K",
        approval_code="EST",
        description="Over what period is a cost asset amortised?",
        source_ref="POL-141",
        section="Contract costs and loss contracts",
    ),
    RegistryParameterSpec(
        code="costs.commensurate_ratio",
        pol_id="POL-142",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "format": "decimal",
            "x-minimum": "0",
        },
        default_asc606="1.00",
        default_ifrs15="1.00",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
                RegistryScope.PRODUCT,
            }
        ),
        pin="K",
        approval_code="OVR",
        description='When is a renewal commission "commensurate" with the initial commission?',
        source_ref="POL-142",
        section="Contract costs and loss contracts",
    ),
    RegistryParameterSpec(
        code="costs.amortisation_pattern",
        pol_id="POL-143",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "STRAIGHT_LINE",
                "PROPORTIONAL_TO_RELATED_REVENUE",
            ],
        },
        default_asc606="STRAIGHT_LINE",
        default_ifrs15="STRAIGHT_LINE",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.PRODUCT,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="Which systematic pattern applies?",
        source_ref="POL-143",
        section="Contract costs and loss contracts",
    ),
    RegistryParameterSpec(
        code="costs.impairment_reversal",
        pol_id="POL-144",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "PROHIBITED",
                "REQUIRED_CAPPED",
            ],
        },
        default_asc606="PROHIBITED",
        default_ifrs15="REQUIRED_CAPPED",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="PROHIBITED",
        allowed_levels=frozenset(
            {
                RegistryScope.BOOK,
            }
        ),
        pin="P",
        approval_code="FIX",
        description="Is a contract-cost impairment reversed when conditions improve?",
        source_ref="POL-144",
        section="Contract costs and loss contracts",
    ),
    RegistryParameterSpec(
        code="costs.termination_acceleration",
        pol_id="POL-145",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "ACCELERATE_TO_REMAINING_BENEFIT",
                "CONTINUE",
            ],
        },
        default_asc606="ACCELERATE_TO_REMAINING_BENEFIT",
        default_ifrs15="ACCELERATE_TO_REMAINING_BENEFIT",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="On termination for convenience or churn, is the remaining cost asset expensed?",
        source_ref="POL-145",
        section="Contract costs and loss contracts",
    ),
    RegistryParameterSpec(
        code="costs.fulfilment_capitalisation",
        pol_id="POL-146",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "WHEN_25_5_ATTESTED",
            ],
        },
        default_asc606="WHEN_25_5_ATTESTED",
        default_ifrs15="WHEN_25_5_ATTESTED",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.PRODUCT,
            }
        ),
        pin="K",
        approval_code="JDG",
        description="When are costs to fulfil a contract capitalised?",
        source_ref="POL-146",
        section="Contract costs and loss contracts",
    ),
    RegistryParameterSpec(
        code="loss.unit",
        pol_id="POL-150",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "CONTRACT",
                "POB",
            ],
        },
        default_asc606="CONTRACT",
        default_ifrs15="CONTRACT",
        is_forced_asc606=False,
        is_forced_ifrs15=True,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="At what level is an anticipated loss determined?",
        source_ref="POL-150",
        section="Contract costs and loss contracts",
    ),
    RegistryParameterSpec(
        code="loss.scope",
        pol_id="POL-151",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "SCOPED_605_35_ONLY",
                "ALL_CONTRACTS_WITH_EAC",
            ],
        },
        default_asc606="SCOPED_605_35_ONLY",
        default_ifrs15="ALL_CONTRACTS_WITH_EAC",
        is_forced_asc606=False,
        is_forced_ifrs15=True,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.BOOK,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="Which contracts are tested for anticipated losses?",
        source_ref="POL-151",
        section="Contract costs and loss contracts",
    ),
    RegistryParameterSpec(
        code="loss.cost_basis",
        pol_id="POL-152",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "SUBTOPIC_605_35_COSTS",
                "IAS37_68A_COSTS",
            ],
        },
        default_asc606="SUBTOPIC_605_35_COSTS",
        default_ifrs15="IAS37_68A_COSTS",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.BOOK,
            }
        ),
        pin="K",
        approval_code="FIX",
        description="Which costs enter the loss test?",
        source_ref="POL-152",
        section="Contract costs and loss contracts",
    ),
    RegistryParameterSpec(
        code="loss.consideration_basis",
        pol_id="POL-153",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "UNCONSTRAINED_CREDIT_ADJUSTED_TP",
            ],
        },
        default_asc606="UNCONSTRAINED_CREDIT_ADJUSTED_TP",
        default_ifrs15="UNCONSTRAINED_CREDIT_ADJUSTED_TP",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="FIX",
        description="Which consideration enters the loss test?",
        source_ref="POL-153",
        section="Contract costs and loss contracts",
    ),
    RegistryParameterSpec(
        code="fx.cl_layer_date",
        pol_id="POL-160",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "EARLIER_OF_RECEIPT_AND_UNCONDITIONAL_DUE",
                "INVOICE_ISSUE_DATE",
            ],
        },
        default_asc606="EARLIER_OF_RECEIPT_AND_UNCONDITIONAL_DUE",
        default_ifrs15="EARLIER_OF_RECEIPT_AND_UNCONDITIONAL_DUE",
        is_forced_asc606=False,
        is_forced_ifrs15=True,
        legacy_parity_value="EARLIER_OF_RECEIPT_AND_UNCONDITIONAL_DUE",
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Which date sets the historical rate of a contract-liability layer?",
        source_ref="POL-160",
        section="Foreign currency and legal entities",
    ),
    RegistryParameterSpec(
        code="fx.cl_layer_consumption",
        pol_id="POL-161",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "FIFO",
                "PRO_RATA",
            ],
        },
        default_asc606="FIFO",
        default_ifrs15="FIFO",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="FIFO",
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="In what order are contract-liability layers derecognised?",
        source_ref="POL-161",
        section="Foreign currency and legal entities",
    ),
    RegistryParameterSpec(
        code="fx.unbilled_revenue_rate",
        pol_id="POL-162",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "PERIOD_AVERAGE",
                "TRANSACTION_DATE_SPOT",
            ],
        },
        default_asc606="PERIOD_AVERAGE",
        default_ifrs15="PERIOD_AVERAGE",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Which rate measures revenue recognised in excess of the available contract liability?",
        source_ref="POL-162",
        section="Foreign currency and legal entities",
    ),
    RegistryParameterSpec(
        code="fx.cl_historical_layering",
        pol_id="POL-163",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "ENABLED",
                "DISABLED_REMEASURE_AS_MONETARY",
            ],
        },
        default_asc606="ENABLED",
        default_ifrs15="ENABLED",
        is_forced_asc606=False,
        is_forced_ifrs15=True,
        legacy_parity_value="ENABLED",
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
                RegistryScope.CONTRACT,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Are contract liabilities measured at historical rates (nonmonetary) rather than remeasured?",
        source_ref="POL-163",
        section="Foreign currency and legal entities",
    ),
    RegistryParameterSpec(
        code="fx.monetary_remeasurement",
        pol_id="POL-164",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "ASSET_POSITIONS_ENGINE_AR_AND_MONETARY_LIABILITIES",
            ],
        },
        default_asc606="ASSET_POSITIONS_ENGINE_AR_AND_MONETARY_LIABILITIES",
        default_ifrs15="ASSET_POSITIONS_ENGINE_AR_AND_MONETARY_LIABILITIES",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="ASSET_POSITIONS_ENGINE_AR_AND_MONETARY_LIABILITIES",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="FIX",
        description="Which balances are remeasured at the closing rate?",
        source_ref="POL-164",
        section="Foreign currency and legal entities",
    ),
    RegistryParameterSpec(
        code="ic.revenue_entity",
        pol_id="POL-170",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "PERFORMING_ENTITY",
                "CONTRACTING_ENTITY",
            ],
        },
        default_asc606="PERFORMING_ENTITY",
        default_ifrs15="PERFORMING_ENTITY",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="PERFORMING_ENTITY",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
                RegistryScope.ENTITY,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="Which legal entity recognises revenue when the performing entity differs from the contracting entity?",
        source_ref="POL-170",
        section="Foreign currency and legal entities",
    ),
    RegistryParameterSpec(
        code="ic.pair_amount",
        pol_id="POL-171",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "REVENUE_AMOUNT",
            ],
        },
        default_asc606="REVENUE_AMOUNT",
        default_ifrs15="REVENUE_AMOUNT",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="REVENUE_AMOUNT",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="FIX",
        description="What amount does an intercompany pair carry?",
        source_ref="POL-171",
        section="Foreign currency and legal entities",
    ),
    RegistryParameterSpec(
        code="late_events.posting",
        pol_id="POL-180",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "FIRST_OPEN_PERIOD_WITH_ORIGIN",
            ],
        },
        default_asc606="FIRST_OPEN_PERIOD_WITH_ORIGIN",
        default_ifrs15="FIRST_OPEN_PERIOD_WITH_ORIGIN",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="FIRST_OPEN_PERIOD_WITH_ORIGIN",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="FIX",
        description="Where does the effect of an event dated in a closed period post?",
        source_ref="POL-180",
        section="Close, late events and estimates",
    ),
    RegistryParameterSpec(
        code="late_events.fx_rates",
        pol_id="POL-181",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "EFFECTIVE_DATE_RATES_CUMULATIVE_DIFFERENCE",
            ],
        },
        default_asc606="EFFECTIVE_DATE_RATES_CUMULATIVE_DIFFERENCE",
        default_ifrs15="EFFECTIVE_DATE_RATES_CUMULATIVE_DIFFERENCE",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="EFFECTIVE_DATE_RATES_CUMULATIVE_DIFFERENCE",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="FIX",
        description="Which rates apply to a late event?",
        source_ref="POL-181",
        section="Close, late events and estimates",
    ),
    RegistryParameterSpec(
        code="estimates.versioning",
        pol_id="POL-182",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "IMMUTABLE_VERSIONS",
            ],
        },
        default_asc606="IMMUTABLE_VERSIONS",
        default_ifrs15="IMMUTABLE_VERSIONS",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="IMMUTABLE_VERSIONS",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="EST",
        description="How are VC, constraint, return, breakage, EAC and exercise-likelihood estimates stored?",
        source_ref="POL-182",
        section="Close, late events and estimates",
    ),
    RegistryParameterSpec(
        code="estimates.change_classification",
        pol_id="POL-183",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "PREPARER_CLASSIFIES",
            ],
        },
        default_asc606="PREPARER_CLASSIFIES",
        default_ifrs15="PREPARER_CLASSIFIES",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="PREPARER_CLASSIFIES",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="JDG",
        description="Is a change a change in estimate or an error correction?",
        source_ref="POL-183",
        section="Close, late events and estimates",
    ),
    RegistryParameterSpec(
        code="entity.reporting_type",
        pol_id="POL-190",
        category=RegistryCategory.DISCLOSURE_ELECTION,
        value_schema={
            "type": "string",
            "enum": [
                "PBE",
                "NFP_CONDUIT",
                "EBP_SEC",
                "NONPUBLIC",
            ],
        },
        default_asc606="PBE",
        default_ifrs15=None,
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="PBE",
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Which reporting-entity category applies?",
        source_ref="POL-190",
        section="Disclosures, nonpublic-entity reliefs and interim packs",
    ),
    RegistryParameterSpec(
        code="disclosure.nonpublic_disaggregation_relief",
        pol_id="POL-191",
        category=RegistryCategory.DISCLOSURE_ELECTION,
        value_schema={
            "type": "string",
            "enum": [
                "ELECT",
                "DO_NOT_ELECT",
            ],
        },
        default_asc606="DO_NOT_ELECT",
        default_ifrs15="DO_NOT_ELECT",
        is_forced_asc606=False,
        is_forced_ifrs15=True,
        legacy_parity_value="DO_NOT_ELECT",
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="May the quantitative disaggregation (50-5, 50-6, 55-89 to 55-91) be omitted?",
        source_ref="POL-191",
        section="Disclosures, nonpublic-entity reliefs and interim packs",
    ),
    RegistryParameterSpec(
        code="disclosure.nonpublic_contract_balances_relief",
        pol_id="POL-192",
        category=RegistryCategory.DISCLOSURE_ELECTION,
        value_schema={
            "type": "string",
            "enum": [
                "ELECT",
                "DO_NOT_ELECT",
            ],
        },
        default_asc606="DO_NOT_ELECT",
        default_ifrs15="DO_NOT_ELECT",
        is_forced_asc606=False,
        is_forced_ifrs15=True,
        legacy_parity_value="DO_NOT_ELECT",
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="May 50-8 to 50-10 and 50-12A be omitted?",
        source_ref="POL-192",
        section="Disclosures, nonpublic-entity reliefs and interim packs",
    ),
    RegistryParameterSpec(
        code="disclosure.nonpublic_rpo_relief",
        pol_id="POL-193",
        category=RegistryCategory.DISCLOSURE_ELECTION,
        value_schema={
            "type": "string",
            "enum": [
                "ELECT",
                "DO_NOT_ELECT",
            ],
        },
        default_asc606="DO_NOT_ELECT",
        default_ifrs15="DO_NOT_ELECT",
        is_forced_asc606=False,
        is_forced_ifrs15=True,
        legacy_parity_value="DO_NOT_ELECT",
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="May the RPO disclosures (50-13 to 50-15) be omitted?",
        source_ref="POL-193",
        section="Disclosures, nonpublic-entity reliefs and interim packs",
    ),
    RegistryParameterSpec(
        code="disclosure.nonpublic_judgements_relief",
        pol_id="POL-194",
        category=RegistryCategory.DISCLOSURE_ELECTION,
        value_schema={
            "type": "string",
            "enum": [
                "ELECT",
                "DO_NOT_ELECT",
            ],
        },
        default_asc606="DO_NOT_ELECT",
        default_ifrs15="DO_NOT_ELECT",
        is_forced_asc606=False,
        is_forced_ifrs15=True,
        legacy_parity_value="DO_NOT_ELECT",
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="May 50-18(b), 50-19 and 50-20 be omitted?",
        source_ref="POL-194",
        section="Disclosures, nonpublic-entity reliefs and interim packs",
    ),
    RegistryParameterSpec(
        code="disclosure.nonpublic_expedient_relief",
        pol_id="POL-195",
        category=RegistryCategory.DISCLOSURE_ELECTION,
        value_schema={
            "type": "string",
            "enum": [
                "ELECT",
                "DO_NOT_ELECT",
            ],
        },
        default_asc606="DO_NOT_ELECT",
        default_ifrs15="DO_NOT_ELECT",
        is_forced_asc606=False,
        is_forced_ifrs15=True,
        legacy_parity_value="DO_NOT_ELECT",
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="May the practical-expedient disclosures (50-22) be omitted?",
        source_ref="POL-195",
        section="Disclosures, nonpublic-entity reliefs and interim packs",
    ),
    RegistryParameterSpec(
        code="disclosure.nonpublic_cost_relief",
        pol_id="POL-196",
        category=RegistryCategory.DISCLOSURE_ELECTION,
        value_schema={
            "type": "string",
            "enum": [
                "ELECT",
                "DO_NOT_ELECT",
            ],
        },
        default_asc606="DO_NOT_ELECT",
        default_ifrs15="DO_NOT_ELECT",
        is_forced_asc606=False,
        is_forced_ifrs15=True,
        legacy_parity_value="DO_NOT_ELECT",
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="May the contract-cost disclosures (340-40-50-2, 50-3, 50-5) be omitted?",
        source_ref="POL-196",
        section="Disclosures, nonpublic-entity reliefs and interim packs",
    ),
    RegistryParameterSpec(
        code="rpo.exemption_original_duration_one_year",
        pol_id="POL-197",
        category=RegistryCategory.PRACTICAL_EXPEDIENT,
        value_schema={
            "type": "string",
            "enum": [
                "APPLY",
                "DO_NOT_APPLY",
            ],
        },
        default_asc606="DO_NOT_APPLY",
        default_ifrs15="DO_NOT_APPLY",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="DO_NOT_APPLY",
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Is RPO omitted for POBs in contracts with an original expected duration of one year or less?",
        source_ref="POL-197",
        section="Disclosures, nonpublic-entity reliefs and interim packs",
    ),
    RegistryParameterSpec(
        code="rpo.exemption_right_to_invoice",
        pol_id="POL-198",
        category=RegistryCategory.PRACTICAL_EXPEDIENT,
        value_schema={
            "type": "string",
            "enum": [
                "APPLY",
                "DO_NOT_APPLY",
            ],
        },
        default_asc606="DO_NOT_APPLY",
        default_ifrs15="DO_NOT_APPLY",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="DO_NOT_APPLY",
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Is RPO omitted for POBs recognised under the right-to-invoice expedient?",
        source_ref="POL-198",
        section="Disclosures, nonpublic-entity reliefs and interim packs",
    ),
    RegistryParameterSpec(
        code="rpo.exemption_royalty_vc",
        pol_id="POL-199",
        category=RegistryCategory.PRACTICAL_EXPEDIENT,
        value_schema={
            "type": "string",
            "enum": [
                "APPLY",
                "DO_NOT_APPLY",
            ],
        },
        default_asc606="DO_NOT_APPLY",
        default_ifrs15="DO_NOT_APPLY",
        is_forced_asc606=False,
        is_forced_ifrs15=True,
        legacy_parity_value="DO_NOT_APPLY",
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Is sales- or usage-based royalty VC on licences omitted from RPO?",
        source_ref="POL-199",
        section="Disclosures, nonpublic-entity reliefs and interim packs",
    ),
    RegistryParameterSpec(
        code="rpo.exemption_vc_wholly_unsatisfied",
        pol_id="POL-200",
        category=RegistryCategory.PRACTICAL_EXPEDIENT,
        value_schema={
            "type": "string",
            "enum": [
                "APPLY",
                "DO_NOT_APPLY",
            ],
        },
        default_asc606="DO_NOT_APPLY",
        default_ifrs15="DO_NOT_APPLY",
        is_forced_asc606=False,
        is_forced_ifrs15=True,
        legacy_parity_value="DO_NOT_APPLY",
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Is VC allocated entirely to a wholly unsatisfied POB or series increment (32-40) omitted from RPO?",
        source_ref="POL-200",
        section="Disclosures, nonpublic-entity reliefs and interim packs",
    ),
    RegistryParameterSpec(
        code="rpo.time_bands",
        pol_id="POL-201",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "array",
            "items": {
                "type": "integer",
                "minimum": 1,
            },
            "minItems": 1,
            "uniqueItems": True,
            "x-ordered": "ascending",
        },
        default_asc606=[
            12,
            24,
        ],
        default_ifrs15=[
            12,
            24,
        ],
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=[
            12,
            24,
        ],
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="CFG",
        description="Which time bands present RPO?",
        source_ref="POL-201",
        section="Disclosures, nonpublic-entity reliefs and interim packs",
    ),
    RegistryParameterSpec(
        code="franchisor.preopening_expedient",
        pol_id="POL-202",
        category=RegistryCategory.PRACTICAL_EXPEDIENT,
        value_schema={
            "type": "string",
            "enum": [
                "NOT_ELECTED",
                "ELECT_DISTINCT_SERVICES",
                "ELECT_SINGLE_SERVICES_POB",
            ],
        },
        default_asc606="NOT_ELECTED",
        default_ifrs15="NOT_ELECTED",
        is_forced_asc606=False,
        is_forced_ifrs15=True,
        legacy_parity_value="NOT_ELECTED",
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="Does a nonpublic franchisor apply the pre-opening services expedient?",
        source_ref="POL-202",
        section="Disclosures, nonpublic-entity reliefs and interim packs",
    ),
    RegistryParameterSpec(
        code="disclosure.interim_revenue_pack",
        pol_id="POL-203",
        category=RegistryCategory.DISCLOSURE_ELECTION,
        value_schema={
            "anyOf": [
                {
                    "type": "string",
                    "enum": [
                        "TOPIC_270_LIST",
                    ],
                },
                {
                    "type": "string",
                    "enum": [
                        "IAS34_16A_L",
                    ],
                },
            ],
        },
        default_asc606=None,
        default_ifrs15="IAS34_16A_L",
        is_forced_asc606=False,
        is_forced_ifrs15=True,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="P",
        approval_code="FIX",
        description="Which revenue disclosures does an interim pack contain?",
        source_ref="POL-203",
        section="Disclosures, nonpublic-entity reliefs and interim packs",
    ),
    RegistryParameterSpec(
        code="disclosure.prior_period_pob_revenue_basis",
        pol_id="POL-204",
        category=RegistryCategory.DISCLOSURE_ELECTION,
        value_schema={
            "type": "string",
            "enum": [
                "ALG10_DECOMPOSITION",
            ],
        },
        default_asc606="ALG10_DECOMPOSITION",
        default_ifrs15="ALG10_DECOMPOSITION",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="ALG10_DECOMPOSITION",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="FIX",
        description='How is "revenue from POBs satisfied (or partially satisfied) in previous periods" measured?',
        source_ref="POL-204",
        section="Disclosures, nonpublic-entity reliefs and interim packs",
    ),
    RegistryParameterSpec(
        code="onboarding.method",
        pol_id="POL-210",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "RECOMPUTE_FROM_INCEPTION",
                "OPENING_BALANCES_AT_CUTOVER",
            ],
        },
        default_asc606="RECOMPUTE_FROM_INCEPTION",
        default_ifrs15="RECOMPUTE_FROM_INCEPTION",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(),
        pin="K",
        approval_code="CFG",
        description="How are in-flight contracts onboarded?",
        source_ref="POL-210",
        section="Onboarding, migration and business combinations",
    ),
    RegistryParameterSpec(
        code="migration.nondistinct_mapping",
        pol_id="POL-211",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "SINGLE_POB",
                "SERIES",
                "REVIEW_QUEUE",
            ],
        },
        default_asc606="REVIEW_QUEUE",
        default_ifrs15="REVIEW_QUEUE",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="SINGLE_POB",
        allowed_levels=frozenset(),
        pin="K",
        approval_code="OVR",
        description='How is a legacy "Nondistinct" SKU flag mapped?',
        source_ref="POL-211",
        section="Onboarding, migration and business combinations",
    ),
    RegistryParameterSpec(
        code="migration.material_right_convention",
        pol_id="POL-212",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "CONVERT_TO_OPTION_RECORD",
                "KEEP_QUANTITY_CONVENTION",
            ],
        },
        default_asc606="CONVERT_TO_OPTION_RECORD",
        default_ifrs15="CONVERT_TO_OPTION_RECORD",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="KEEP_QUANTITY_CONVENTION",
        allowed_levels=frozenset(),
        pin="K",
        approval_code="CFG",
        description="How are legacy material-right rows (L = 1, d = 0, r = 0, quantity = SSP in dollars) imported?",
        source_ref="POL-212",
        section="Onboarding, migration and business combinations",
    ),
    RegistryParameterSpec(
        code="migration.legacy_vc_rows",
        pol_id="POL-213",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "VC_ELEMENT_PLUS_CREDIT_EVENTS",
            ],
        },
        default_asc606="VC_ELEMENT_PLUS_CREDIT_EVENTS",
        default_ifrs15="VC_ELEMENT_PLUS_CREDIT_EVENTS",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="VC_ELEMENT_PLUS_CREDIT_EVENTS",
        allowed_levels=frozenset(),
        pin="K",
        approval_code="FIX",
        description="How are legacy `VC` stratification rows imported?",
        source_ref="POL-213",
        section="Onboarding, migration and business combinations",
    ),
    RegistryParameterSpec(
        code="migration.split_upload_allocation",
        pol_id="POL-214",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "ALLOCATE_ACROSS_ALL_POBS",
            ],
        },
        default_asc606="ALLOCATE_ACROSS_ALL_POBS",
        default_ifrs15="ALLOCATE_ACROSS_ALL_POBS",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="ALLOCATE_ACROSS_ALL_POBS",
        allowed_levels=frozenset(),
        pin="K",
        approval_code="FIX",
        description="How are contracts split across legacy uploads allocated?",
        source_ref="POL-214",
        section="Onboarding, migration and business combinations",
    ),
    RegistryParameterSpec(
        code="bc.acquired_contract_measurement",
        pol_id="POL-215",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "ASC606_AS_IF_ORIGINATED",
                "FAIR_VALUE_IFRS3",
            ],
        },
        default_asc606="ASC606_AS_IF_ORIGINATED",
        default_ifrs15="FAIR_VALUE_IFRS3",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.BOOK,
            }
        ),
        pin="K",
        approval_code="JDG",
        description="How are contract assets and contract liabilities acquired in a business combination measured?",
        source_ref="POL-215",
        section="Onboarding, migration and business combinations",
    ),
    RegistryParameterSpec(
        code="bc.expedient_modification_aggregation",
        pol_id="POL-216",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "APPLY",
                "DO_NOT_APPLY",
            ],
        },
        default_asc606="APPLY",
        default_ifrs15=None,
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(),
        pin="K",
        approval_code="CFG",
        description="Does the acquirer reflect the aggregate effect of all pre-acquisition modifications?",
        source_ref="POL-216",
        section="Onboarding, migration and business combinations",
    ),
    RegistryParameterSpec(
        code="bc.expedient_ssp_at_acquisition",
        pol_id="POL-217",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "APPLY",
                "DO_NOT_APPLY",
            ],
        },
        default_asc606="APPLY",
        default_ifrs15=None,
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(),
        pin="K",
        approval_code="CFG",
        description="Does the acquirer determine SSP at the acquisition date instead of contract inception?",
        source_ref="POL-217",
        section="Onboarding, migration and business combinations",
    ),
    RegistryParameterSpec(
        code="transition.first_time_application",
        pol_id="POL-218",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "MODIFIED_RETROSPECTIVE",
                "FULL_RETROSPECTIVE",
            ],
        },
        default_asc606="MODIFIED_RETROSPECTIVE",
        default_ifrs15="MODIFIED_RETROSPECTIVE",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="For an entity first applying Topic 606 or IFRS 15 on the platform, which transition method's reports are produced?",
        source_ref="POL-218",
        section="Onboarding, migration and business combinations",
    ),
    RegistryParameterSpec(
        code="scope.nonfinancial_asset_sale_610_20",
        pol_id="POL-230",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "ROUTE_OUT",
            ],
        },
        default_asc606="ROUTE_OUT",
        default_ifrs15="ROUTE_OUT",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value="ROUTE_OUT",
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="FIX",
        description="How are transfers of nonfinancial assets to noncustomers treated?",
        source_ref="POL-230",
        section="Scope routing and informational switches",
    ),
    RegistryParameterSpec(
        code="scope.lessor_combination_expedient",
        pol_id="POL-231",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "NOT_ELECTED",
                "ELECTED",
            ],
        },
        default_asc606="NOT_ELECTED",
        default_ifrs15="NOT_ELECTED",
        is_forced_asc606=False,
        is_forced_ifrs15=True,
        legacy_parity_value="NOT_ELECTED",
        allowed_levels=frozenset(
            {
                RegistryScope.ENTITY,
                RegistryScope.PRODUCT,
            }
        ),
        pin="K",
        approval_code="CFG",
        description="Does a lessor combine nonlease components with the associated lease component?",
        source_ref="POL-231",
        section="Scope routing and informational switches",
    ),
    RegistryParameterSpec(
        code="licence.combined_pob_nature",
        pol_id="POL-232",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "CONSIDER_NATURE",
            ],
        },
        default_asc606="CONSIDER_NATURE",
        default_ifrs15="CONSIDER_NATURE",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.BOOK,
            }
        ),
        pin="K",
        approval_code="FIX",
        description="Is the nature of a licence considered when it is part of a combined POB?",
        source_ref="POL-232",
        section="Scope routing and informational switches",
    ),
    RegistryParameterSpec(
        code="scope.repurchase_classification",
        pol_id="POL-233",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "DECISION_TABLE_55_66_TO_55_78",
            ],
        },
        default_asc606="DECISION_TABLE_55_66_TO_55_78",
        default_ifrs15="DECISION_TABLE_55_66_TO_55_78",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.CONTRACT,
            }
        ),
        pin="K",
        approval_code="JDG",
        description="How are repurchase agreements classified?",
        source_ref="POL-233",
        section="Scope routing and informational switches",
    ),
    RegistryParameterSpec(
        code="scope.collaboration_808",
        pol_id="POL-234",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "UNIT_OF_ACCOUNT_CUSTOMER_TEST",
            ],
        },
        default_asc606="UNIT_OF_ACCOUNT_CUSTOMER_TEST",
        default_ifrs15=None,
        is_forced_asc606=True,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.CONTRACT,
            }
        ),
        pin="K",
        approval_code="JDG",
        description="When are transactions with a collaborative-arrangement participant revenue under Topic 606?",
        source_ref="POL-234",
        section="Scope routing and informational switches",
    ),
    RegistryParameterSpec(
        code="usage.tier_minimum_method",
        pol_id="POL-240",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "DERIVED",
                "ESTIMATE_MEASUREMENT_PERIOD_TP",
            ],
        },
        default_asc606="DERIVED",
        default_ifrs15="DERIVED",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.PRODUCT,
                RegistryScope.CONTRACT,
            }
        ),
        pin="K",
        approval_code="OVR",
        description="Is usage-based VC allocated to the period of usage, or estimated for the whole measurement period?",
        source_ref="POL-240",
        section="Additional register entries for the topics",
    ),
    RegistryParameterSpec(
        code="credits.rollover_treatment",
        pol_id="POL-241",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "BREAKAGE_INCLUDING_EXPECTED_ROLLOVER_USE",
                "FORFEIT_AT_TERM_END",
            ],
        },
        default_asc606="BREAKAGE_INCLUDING_EXPECTED_ROLLOVER_USE",
        default_ifrs15="BREAKAGE_INCLUDING_EXPECTED_ROLLOVER_USE",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.PRODUCT,
            }
        ),
        pin="K",
        approval_code="EST",
        description="How are unused prepaid credits that roll into a renewal accounted for?",
        source_ref="POL-241",
        section="Additional register entries for the topics",
    ),
    RegistryParameterSpec(
        code="termination.refund_settlement",
        pol_id="POL-242",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "REFUND_LIABILITY_UNTIL_CREDIT_MEMO",
            ],
        },
        default_asc606="REFUND_LIABILITY_UNTIL_CREDIT_MEMO",
        default_ifrs15="REFUND_LIABILITY_UNTIL_CREDIT_MEMO",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="P",
        approval_code="FIX",
        description="How is a refund agreed on termination settled in the ledger?",
        source_ref="POL-242",
        section="Additional register entries for the topics",
    ),
    RegistryParameterSpec(
        code="concession.allocation_basis",
        pol_id="POL-243",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "INCEPTION_BASIS",
                "TARGETED_WHEN_32_40_ATTESTED",
            ],
        },
        default_asc606="INCEPTION_BASIS",
        default_ifrs15="INCEPTION_BASIS",
        is_forced_asc606=False,
        is_forced_ifrs15=False,
        legacy_parity_value="TARGETED_WHEN_32_40_ATTESTED",
        allowed_levels=frozenset(
            {
                RegistryScope.CONTRACT,
            }
        ),
        pin="K",
        approval_code="OVR",
        description="How is a price concession on transferred goods allocated?",
        source_ref="POL-243",
        section="Additional register entries for the topics",
    ),
    RegistryParameterSpec(
        code="claims.recognition_gate",
        pol_id="POL-244",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "ENFORCEABLE_ATTESTED_AND_CONSTRAINED",
            ],
        },
        default_asc606="ENFORCEABLE_ATTESTED_AND_CONSTRAINED",
        default_ifrs15="ENFORCEABLE_ATTESTED_AND_CONSTRAINED",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.CONTRACT,
            }
        ),
        pin="K",
        approval_code="JDG",
        description="When is a claim included in the transaction price?",
        source_ref="POL-244",
        section="Additional register entries for the topics",
    ),
    RegistryParameterSpec(
        code="portfolio.results_attribution",
        pol_id="POL-245",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "PORTFOLIO_RATE_PER_CONTRACT",
            ],
        },
        default_asc606="PORTFOLIO_RATE_PER_CONTRACT",
        default_ifrs15="PORTFOLIO_RATE_PER_CONTRACT",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.TENANT,
            }
        ),
        pin="K",
        approval_code="FIX",
        description="How are portfolio estimates applied to contracts?",
        source_ref="POL-245",
        section="Additional register entries for the topics",
    ),
    RegistryParameterSpec(
        code="cpc.share_based_timing",
        pol_id="POL-246",
        category=RegistryCategory.ACCOUNTING_POLICY,
        value_schema={
            "type": "string",
            "enum": [
                "LATER_OF_RELATED_REVENUE_AND_GRANT",
            ],
        },
        default_asc606="LATER_OF_RELATED_REVENUE_AND_GRANT",
        default_ifrs15="LATER_OF_RELATED_REVENUE_AND_GRANT",
        is_forced_asc606=True,
        is_forced_ifrs15=True,
        legacy_parity_value=None,
        allowed_levels=frozenset(
            {
                RegistryScope.CONTRACT,
            }
        ),
        pin="K",
        approval_code="EST",
        description="When does share-based consideration payable to a customer reduce revenue?",
        source_ref="POL-246",
        section="Additional register entries for the topics",
    ),
)
# POLICIES.md §1 and §5.0, one spec per non-retired POL row, keyed by code.
POLICY_PARAMETERS: Final[Mapping[str, RegistryParameterSpec]] = MappingProxyType(
    {spec.code: spec for spec in _SPECS}
)
