"""Reference data tables (04 §5)."""

from __future__ import annotations

from typing import Final

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    Column,
    Computed,
    Date,
    Integer,
    SmallInteger,
    Table,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from erev_api.db.tables import metadata
from erev_api.db.tables.platform import (
    _enum,
    _sc_c,
    _sc_c_sc_m,
    _sc_m,
    _sc_v,
    _timestamp,
)
from erev_api.db.types import ExactType, FxRateType
from erev_api.enums import (
    AccountRole,
    AccountType,
    BookCode,
    CalendarPattern,
    ClearingPurpose,
    Distinctness,
    LicenceNature,
    ObligationKind,
    OverTimeCriterion,
    PrincipalAgent,
    RatableConvention,
    RateType,
    ReasonCode,
    RecognitionMethod,
    RuleSetKind,
    RunStatus,
    SatisfactionPattern,
    SourceSystem,
    SspMethod,
    SspQuantityUnit,
    SspValueBasis,
    WarrantyType,
)

# Created by revision 0027 (RFD-1): E-50.
calendar_pattern: Final = _enum(CalendarPattern, "calendar_pattern")

# T-REF-04: fiscal calendar definition (IM-M, RLS-T).
fiscal_calendar: Final = Table(
    "fiscal_calendar",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("pattern", calendar_pattern, nullable=False, server_default=text("'MONTHLY'")),
    Column("fiscal_year_start_month", SmallInteger(), nullable=False, server_default=text("1")),
    Column("week_end_day", SmallInteger(), nullable=True),
    Column("year_end_anchor", Text(), nullable=True),
    *_sc_c_sc_m(),
)

# T-REF-05: accounting period of a calendar (IM-M, RLS-T); DB-05 contiguity trigger.
period: Final = Table(
    "period",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("calendar_id", Uuid(), nullable=False),
    Column("fiscal_year", Integer(), nullable=False),
    Column("period_no", SmallInteger(), nullable=False),
    Column("quarter_no", SmallInteger(), nullable=False),
    Column("period_key", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("start_date", Date(), nullable=False),
    Column("end_date", Date(), nullable=False),
    *_sc_c_sc_m(),
)

# E-02, created by revision 0015; E-110, created by revision 0029 (RFD-2). The E-04 columns are text
# with a CHECK of its literals: table period_state owns the row type erev.period_state (L1-1-Q-20).
book_code_type: Final = _enum(BookCode, "book_code")
reason_code: Final = _enum(ReasonCode, "reason_code")

# T-REF-01: legal entity (IM-M, RLS-TE on id).
legal_entity: Final = Table(
    "legal_entity",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("functional_currency", CHAR(3), nullable=False),
    Column("time_zone", Text(), nullable=False),
    Column("calendar_id", Uuid(), nullable=False),
    Column("parent_entity_id", Uuid(), nullable=True),
    Column("country_code", CHAR(2), nullable=True),
    Column("tax_id", Text(), nullable=True),
    Column("is_active", Boolean(), nullable=False, server_default=text("true")),
    *_sc_c_sc_m(),
)

# T-REF-02: accounting books of the tenant (IM-M with ``code`` immutable, RLS-T).
book: Final = Table(
    "book",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("code", book_code_type, nullable=False),
    Column("name", Text(), nullable=False),
    Column("is_primary", Boolean(), nullable=False, server_default=text("false")),
    Column("is_enabled", Boolean(), nullable=False, server_default=text("true")),
    Column("posting_target", Text(), nullable=False),
    *_sc_c_sc_m(),
)

# T-REF-03: the books an entity keeps, from which first period (IM-M, RLS-TE on entity_id).
entity_book: Final = Table(
    "entity_book",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("entity_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("first_period_id", Uuid(), nullable=False),
    Column("is_enabled", Boolean(), nullable=False, server_default=text("true")),
    *_sc_c_sc_m(),
)

# T-REF-06: state of a period per entity and book (IM-X, RLS-TE on entity_id); DB-07 trigger.
period_state: Final = Table(
    "period_state",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("entity_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("period_id", Uuid(), nullable=False),
    Column("period_end_date", Date(), nullable=False),
    Column("state", Text(), nullable=False, server_default=text("'future'")),
    Column("current_lock_id", Uuid(), nullable=True),
    _timestamp("state_changed_at", nullable=False, now_default=True),
    *_sc_m(),
)

# T-REF-07: append-only history of period state changes (IM-A, RLS-TE on entity_id).
period_state_transition: Final = Table(
    "period_state_transition",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("period_state_id", Uuid(), nullable=False),
    Column("entity_id", Uuid(), nullable=False),
    Column("book_code", book_code_type, nullable=False),
    Column("period_id", Uuid(), nullable=False),
    Column("from_state", Text(), nullable=True),
    Column("to_state", Text(), nullable=False),
    Column("reason_code", reason_code, nullable=True),
    Column("comment", Text(), nullable=True),
    Column("approval_request_id", Uuid(), nullable=True),
    Column("period_lock_id", Uuid(), nullable=True),
    Column("close_run_id", Uuid(), nullable=True),
    Column("created_txid", BigInteger(), nullable=False, server_default=text("txid_current()")),
    *_sc_c(),
)

# Created by revision 0028 (RFD-6): E-52 and E-38.
account_type: Final = _enum(AccountType, "account_type")
source_system: Final = _enum(SourceSystem, "source_system")

# T-REF-13: chart of accounts (IM-M, RLS-T).
gl_account: Final = Table(
    "gl_account",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("account_type", account_type, nullable=False),
    Column("normal_balance", CHAR(1), nullable=False),
    Column("entity_ids", ARRAY(Uuid()), nullable=False, server_default=text("'{}'::uuid[]")),
    Column(
        "required_dimensions", ARRAY(Text()), nullable=False, server_default=text("'{}'::text[]")
    ),
    Column("source_system", source_system, nullable=False, server_default=text("'MANUAL_UI'")),
    Column("is_active", Boolean(), nullable=False, server_default=text("true")),
    *_sc_c_sc_m(),
)

# T-REF-16: built-in and tenant-defined dimensions (IM-M, RLS-T); DB-12 custom limit trigger.
dimension_definition: Final = Table(
    "dimension_definition",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("is_builtin", Boolean(), nullable=False),
    Column("position", SmallInteger(), nullable=False),
    Column("is_active", Boolean(), nullable=False, server_default=text("true")),
    *_sc_c_sc_m(),
)

# T-REF-17: allowed values of a dimension other than product and customer (IM-M, RLS-T).
dimension_value: Final = Table(
    "dimension_value",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("dimension_definition_id", Uuid(), nullable=False),
    Column("code", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("parent_value_id", Uuid(), nullable=True),
    Column("is_active", Boolean(), nullable=False, server_default=text("true")),
    *_sc_c_sc_m(),
)

# Created by revision 0032 (RFD-7): E-01 and E-109.
account_role: Final = _enum(AccountRole, "account_role")
clearing_purpose: Final = _enum(ClearingPurpose, "clearing_purpose")

# T-REF-14: versioned, effective-dated account-role mapping (IM-P, SC-V, RLS-T); DB-04 trigger.
account_mapping_version: Final = Table(
    "account_mapping_version",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("name", Text(), nullable=False),
    Column("notes", Text(), nullable=True),
    Column("impact_simulation_file_id", Uuid(), nullable=True),
    *_sc_c_sc_m(),
    *_sc_v(),
)

# T-REF-15: one mapping rule of a version (IM-P child, RLS-T); DB-04 child trigger. ``specificity``
# is generated by the database.
account_mapping_rule: Final = Table(
    "account_mapping_rule",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("account_mapping_version_id", Uuid(), nullable=False),
    Column("account_role", account_role, nullable=False),
    Column("clearing_purpose", clearing_purpose, nullable=True),
    Column("entity_id", Uuid(), nullable=True),
    Column("book_code", book_code_type, nullable=True),
    Column("product_id", Uuid(), nullable=True),
    Column("revenue_category", Text(), nullable=True),
    Column("gl_account_id", Uuid(), nullable=False),
    Column("default_dimensions", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    Column("priority", Integer(), nullable=False, server_default=text("0")),
    Column(
        "specificity",
        SmallInteger(),
        Computed(
            "(CASE WHEN entity_id IS NOT NULL THEN 8 ELSE 0 END) "
            "+ (CASE WHEN book_code IS NOT NULL THEN 4 ELSE 0 END) "
            "+ (CASE WHEN product_id IS NOT NULL OR revenue_category IS NOT NULL "
            "THEN 2 ELSE 0 END)",
            persisted=True,
        ),
        nullable=False,
    ),
)

# Created by revision 0031 (RFD-8).
# T-REF-18: group of related customers (IM-M, RLS-T).
related_party_group: Final = Table(
    "related_party_group",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("description", Text(), nullable=True),
    *_sc_c_sc_m(),
)

# T-REF-19: customer master (IM-M, RLS-T); external id unique per source system when set.
customer: Final = Table(
    "customer",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("related_party_group_id", Uuid(), nullable=True),
    Column("parent_customer_id", Uuid(), nullable=True),
    Column("credit_grade", Text(), nullable=True),
    Column("segment", Text(), nullable=True),
    Column("country_code", CHAR(2), nullable=True),
    Column("source_system", source_system, nullable=False, server_default=text("'MANUAL_UI'")),
    Column("external_id", Text(), nullable=True),
    Column("is_active", Boolean(), nullable=False, server_default=text("true")),
    *_sc_c_sc_m(),
)

# Created by revision 0033 (RFD-9): E-89, E-105.
principal_agent: Final = _enum(PrincipalAgent, "principal_agent")
distinctness: Final = _enum(Distinctness, "distinctness")

# T-REF-20: product or SKU master (IM-M, RLS-T); ``principal_agent`` changes through an approved
# ``PRINCIPAL_AGENT_CHANGE`` request.
product: Final = Table(
    "product",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("sku_number", Text(), nullable=True),
    Column("name", Text(), nullable=False),
    Column("product_family", Text(), nullable=True),
    Column("revenue_category", Text(), nullable=True),
    Column("default_pob_template_id", Uuid(), nullable=True),
    Column("disaggregation", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    Column(
        "principal_agent", principal_agent, nullable=False, server_default=text("'NOT_ASSESSED'")
    ),
    Column("distinctness_default", distinctness, nullable=False, server_default=text("'distinct'")),
    Column("unit_of_measure", Text(), nullable=False, server_default=text("'EA'")),
    Column("is_bundle", Boolean(), nullable=False, server_default=text("false")),
    Column("assurance_cost_per_unit", ExactType(), nullable=True),
    Column(
        "is_franchisor_preopening_service", Boolean(), nullable=False, server_default=text("false")
    ),
    Column("policy_values", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    Column("is_active", Boolean(), nullable=False, server_default=text("true")),
    *_sc_c_sc_m(),
)

# T-REF-21: bundle explosion map (IM-M with DELETE, 04 §14.2; RLS-T).
product_bundle_component: Final = Table(
    "product_bundle_component",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("bundle_product_id", Uuid(), nullable=False),
    Column("component_product_id", Uuid(), nullable=False),
    Column("quantity_per_bundle", ExactType(), nullable=False, server_default=text("1")),
    Column("split_basis", Text(), nullable=False, server_default=text("'relative_ssp'")),
    Column("split_ratio", ExactType(), nullable=True),
    Column("sequence", Integer(), nullable=False),
    Column("valid_from", Date(), nullable=False),
    Column("valid_to", Date(), nullable=True),
    *_sc_c_sc_m(),
)

# Created by revision 0036 (RFD-10): E-11, E-18 to E-21, E-90, E-91.
recognition_method: Final = _enum(RecognitionMethod, "recognition_method")
obligation_kind: Final = _enum(ObligationKind, "obligation_kind")
satisfaction_pattern: Final = _enum(SatisfactionPattern, "satisfaction_pattern")
over_time_criterion: Final = _enum(OverTimeCriterion, "over_time_criterion")
ratable_convention: Final = _enum(RatableConvention, "ratable_convention")
licence_nature: Final = _enum(LicenceNature, "licence_nature")
warranty_type: Final = _enum(WarrantyType, "warranty_type")

# T-REF-22: identity of a performance obligation template (IM-M, RLS-T).
pob_template: Final = Table(
    "pob_template",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("description", Text(), nullable=True),
    *_sc_c_sc_m(),
)

# T-REF-23: versioned outputs of a POB template (IM-P, SC-V, RLS-T); DB-04 trigger.
pob_template_version: Final = Table(
    "pob_template_version",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("pob_template_id", Uuid(), nullable=False),
    Column("obligation_kind", obligation_kind, nullable=False, server_default=text("'STANDARD'")),
    Column("distinctness", distinctness, nullable=False, server_default=text("'distinct'")),
    Column("series_increment_unit", Text(), nullable=True),
    Column("satisfaction_pattern", satisfaction_pattern, nullable=False),
    Column(
        "over_time_criterion",
        over_time_criterion,
        nullable=False,
        server_default=text("'NOT_APPLICABLE'"),
    ),
    Column("recognition_method", recognition_method, nullable=False),
    Column("ratable_convention", ratable_convention, nullable=True),
    Column("start_date_rule", Text(), nullable=False, server_default=text("'LINE_START'")),
    Column("end_date_rule", Text(), nullable=False, server_default=text("'LINE_END'")),
    Column("term_months", Integer(), nullable=True),
    Column("principal_agent", principal_agent, nullable=False, server_default=text("'PRINCIPAL'")),
    Column("warranty_type", warranty_type, nullable=False, server_default=text("'NONE'")),
    Column(
        "licence_nature", licence_nature, nullable=False, server_default=text("'NOT_APPLICABLE'")
    ),
    Column("sfc_assessment_required", Boolean(), nullable=False, server_default=text("false")),
    Column("revenue_category", Text(), nullable=True),
    Column("disaggregation", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    Column("account_role_overrides", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    Column("stratification_label", Text(), nullable=True),
    Column(
        "is_excluded_from_netting_attribution",
        Boolean(),
        nullable=False,
        server_default=text("false"),
    ),
    Column("policy_values", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    *_sc_c_sc_m(),
    *_sc_v(),
)

# Created by revision 0034 (RFD-12): E-47, E-49. E-125 by revision 0056 (D-97 (3)).
ssp_method: Final = _enum(SspMethod, "ssp_method")
ssp_value_basis: Final = _enum(SspValueBasis, "ssp_value_basis")
ssp_quantity_unit: Final = _enum(SspQuantityUnit, "ssp_quantity_unit")

# T-REF-28: SSP book identity and scope (IM-M, RLS-T).
ssp_book: Final = Table(
    "ssp_book",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("description", Text(), nullable=True),
    Column("entity_id", Uuid(), nullable=True),
    Column("currency", CHAR(3), nullable=True),
    Column("channel", Text(), nullable=True),
    Column("segment", Text(), nullable=True),
    Column("resolution_mode", Text(), nullable=False, server_default=text("'EFFECTIVE_DATE'")),
    *_sc_c_sc_m(),
)

# T-REF-29: an approved set of SSP values (IM-P, SC-V, RLS-T); DB-04 trigger. SC-V effective_from
# and effective_to stay null; the business dates are effective_from_date and effective_to_date.
ssp_book_version: Final = Table(
    "ssp_book_version",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("ssp_book_id", Uuid(), nullable=False),
    Column("legacy_version_label", Text(), nullable=True),
    Column("effective_from_date", Date(), nullable=True),
    Column("effective_to_date", Date(), nullable=True),
    Column("methodology_label", Text(), nullable=False),
    Column("is_methodology_change", Boolean(), nullable=False, server_default=text("false")),
    Column("entry_count", Integer(), nullable=False, server_default=text("0")),
    Column("diff_summary", JSONB(none_as_null=True), nullable=True),
    Column("ssp_calculator_run_id", Uuid(), nullable=True),
    Column("import_upload_id", Uuid(), nullable=True),
    *_sc_c_sc_m(),
    *_sc_v(),
)

# T-REF-30: the SSP value of a product, stratification and dimension key (IM-P child, RLS-T);
# DB-04 child trigger.
ssp_entry: Final = Table(
    "ssp_entry",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("ssp_book_version_id", Uuid(), nullable=False),
    Column("product_id", Uuid(), nullable=False),
    Column("stratification", Text(), nullable=False, server_default=text("''")),
    Column("region", Text(), nullable=True),
    Column("channel", Text(), nullable=True),
    Column("segment", Text(), nullable=True),
    Column("deal_size_band", Text(), nullable=True),
    Column("term_band", Text(), nullable=True),
    Column("currency", CHAR(3), nullable=False),
    Column("method", ssp_method, nullable=False),
    Column("value_basis", ssp_value_basis, nullable=False, server_default=text("'AMOUNT'")),
    # D-97 (3): what a series line's quantity counts under PER_INCREMENT; no default, never
    # inferred, meaningful for PER_INCREMENT only:
    # CHECK ((value_basis::text = 'PER_INCREMENT') = (quantity_unit IS NOT NULL)) (revision 0056;
    # the text comparison lets the check reference the label the same revision adds).
    Column("quantity_unit", ssp_quantity_unit, nullable=True),
    Column("unit_list_price", ExactType(), nullable=True),
    Column("midpoint_discount_ratio", ExactType(), nullable=True),
    Column("range_ratio", ExactType(), nullable=True),
    Column("cost_basis", ExactType(), nullable=True),
    Column("margin_ratio", ExactType(), nullable=True),
    Column("observable_point", ExactType(), nullable=True),
    Column("revenue_gl_account_id", Uuid(), nullable=True),
    Column("distinctness", distinctness, nullable=False),
    *_sc_c(),
)

# T-REF-31: per-unit point or low, mid and high values of an entry, optionally banded (IM-P child,
# RLS-T); DB-04 child trigger over the entry's version.
ssp_range: Final = Table(
    "ssp_range",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("ssp_entry_id", Uuid(), nullable=False),
    Column("band_dimension", Text(), nullable=False, server_default=text("'NONE'")),
    Column("band_from", ExactType(), nullable=True),
    Column("band_to", ExactType(), nullable=True),
    Column("point_value", ExactType(), nullable=True),
    Column("low_value", ExactType(), nullable=True),
    Column("mid_value", ExactType(), nullable=True),
    Column("high_value", ExactType(), nullable=True),
    *_sc_c(),
)

# Created by revision 0037 (RFD-15): E-67.
run_status: Final = _enum(RunStatus, "run_status")

# T-REF-32: a historical SSP calculator run (IM-S, RLS-T); DB-03 transition trigger.
ssp_calculator_run: Final = Table(
    "ssp_calculator_run",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("name", Text(), nullable=False),
    Column("parameters", JSONB(), nullable=False),
    Column("status", run_status, nullable=False, server_default=text("'QUEUED'")),
    Column("observation_count", Integer(), nullable=True),
    Column("result_file_id", Uuid(), nullable=True),
    Column("draft_ssp_book_version_id", Uuid(), nullable=True),
    Column("job_id", Uuid(), nullable=True),
    _timestamp("started_at"),
    _timestamp("finished_at"),
    # The entities the run's provider may read (rev 1.277; revision 0123): written at INSERT;
    # NULL = every entity, never empty.
    Column("entity_ids", ARRAY(Uuid()), nullable=True),
    *_sc_c(),
)

# T-REF-33: statistics per product and key of a calculator run (IM-A, RLS-T).
ssp_calculator_result: Final = Table(
    "ssp_calculator_result",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("ssp_calculator_run_id", Uuid(), nullable=False),
    Column("product_id", Uuid(), nullable=False),
    Column("stratification", Text(), nullable=False, server_default=text("''")),
    Column("dimension_key", JSONB(), nullable=False, server_default=text("'{}'::jsonb")),
    Column("currency", CHAR(3), nullable=False),
    Column("observation_count", Integer(), nullable=False),
    Column("excluded_count", Integer(), nullable=False),
    Column("median_unit_price", ExactType(), nullable=False),
    Column("mean_unit_price", ExactType(), nullable=False),
    Column("p10_unit_price", ExactType(), nullable=False),
    Column("p25_unit_price", ExactType(), nullable=False),
    Column("p75_unit_price", ExactType(), nullable=False),
    Column("p90_unit_price", ExactType(), nullable=False),
    Column("band_ratio", ExactType(), nullable=False),
    Column("compliance_ratio", ExactType(), nullable=False),
    Column("inside_count", Integer(), nullable=False),
    Column("proposed_low", ExactType(), nullable=False),
    Column("proposed_mid", ExactType(), nullable=False),
    Column("proposed_high", ExactType(), nullable=False),
    Column("histogram", JSONB(), nullable=False),
)

# T-REF-34: an observation excluded from a calculator run, with its reason (IM-A, RLS-T).
ssp_calculator_exclusion: Final = Table(
    "ssp_calculator_exclusion",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("ssp_calculator_run_id", Uuid(), nullable=False),
    Column("source_ref_type", Text(), nullable=False),
    Column("source_ref_id", Uuid(), nullable=False),
    Column("reason", Text(), nullable=False),
    *_sc_c(),
)

# T-REF-08: ISO 4217 currencies (IM-A, RLS-NONE-G), seeded from erev_engine.currencies.ISO_4217.
currency: Final = Table(
    "currency",
    metadata,
    Column("code", CHAR(3), primary_key=True),
    Column("numeric_code", CHAR(3), nullable=False),
    Column("name", Text(), nullable=False),
    Column("minor_unit", SmallInteger(), nullable=False),
    Column("is_active", Boolean(), nullable=False, server_default=text("true")),
)

# Created by revision 0030 (RFD-3): E-51.
rate_type: Final = _enum(RateType, "rate_type")

# T-REF-09: currencies enabled for the tenant (IM-M, RLS-T); key (tenant_id, currency_code).
tenant_currency: Final = Table(
    "tenant_currency",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("currency_code", CHAR(3), primary_key=True),
    Column("is_enabled", Boolean(), nullable=False, server_default=text("true")),
    *_sc_c_sc_m(),
)

# T-REF-10: identity of a rate series by rate type and source (IM-M, RLS-T).
fx_rate_set: Final = Table(
    "fx_rate_set",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("rate_type", rate_type, nullable=False),
    Column("source", Text(), nullable=False),
    *_sc_c_sc_m(),
)

# T-REF-11: a batch of rates covering a date range (IM-P, SC-V, RLS-T); DB-04 trigger.
fx_rate_set_version: Final = Table(
    "fx_rate_set_version",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("fx_rate_set_id", Uuid(), nullable=False),
    Column("coverage_from", Date(), nullable=False),
    Column("coverage_to", Date(), nullable=False),
    Column("rate_count", Integer(), nullable=False, server_default=text("0")),
    Column("import_upload_id", Uuid(), nullable=True),
    *_sc_c_sc_m(),
    *_sc_v(),
)

# T-REF-12: one rate, 1 base = rate quote (IM-P child, RLS-T); DB-04 child trigger.
fx_rate: Final = Table(
    "fx_rate",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("fx_rate_set_version_id", Uuid(), nullable=False),
    Column("rate_type", rate_type, nullable=False),
    Column("base_currency", CHAR(3), nullable=False),
    Column("quote_currency", CHAR(3), nullable=False),
    Column("effective_date", Date(), nullable=False),
    Column("period_id", Uuid(), nullable=True),
    Column("rate", FxRateType(), nullable=False),
    Column("is_derived", Boolean(), nullable=False, server_default=text("false")),
)

# Created by revision 0014 (PLF-12): E-55.
rule_set_kind: Final = _enum(RuleSetKind, "rule_set_kind")

# T-REF-24: identity of a decision table (IM-M, RLS-T).
rule_set: Final = Table(
    "rule_set",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("kind", rule_set_kind, nullable=False),
    Column("description", Text(), nullable=True),
    *_sc_c_sc_m(),
)

# T-REF-25: a version of a decision table (IM-P, SC-V, RLS-T); DB-04 trigger.
rule_set_version: Final = Table(
    "rule_set_version",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("rule_set_id", Uuid(), nullable=False),
    Column("kind", rule_set_kind, nullable=False),
    Column("lint_result", JSONB(none_as_null=True), nullable=True),
    Column("impact_simulation_file_id", Uuid(), nullable=True),
    *_sc_c_sc_m(),
    *_sc_v(),
)

# T-REF-26: one row of a decision table (IM-P child, RLS-T); DB-04 child trigger.
rule: Final = Table(
    "rule",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("rule_set_version_id", Uuid(), nullable=False),
    Column("rule_key", Text(), nullable=False),
    Column("priority", Integer(), nullable=False, server_default=text("0")),
    Column("conditions", JSONB(), nullable=False),
    Column("outputs", JSONB(), nullable=False),
    Column("specificity", SmallInteger(), nullable=False),
    Column("description", Text(), nullable=True),
)

# T-REF-27: example cases of a configuration version (IM-P child, RLS-T); DB-04 child trigger.
rule_test_case: Final = Table(
    "rule_test_case",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("subject_type", Text(), nullable=False),
    Column("subject_id", Uuid(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("input", JSONB(), nullable=False),
    Column("expected_output", JSONB(), nullable=False),
    Column("last_result", Text(), nullable=True),
    _timestamp("last_run_at"),
    *_sc_c_sc_m(),
)
