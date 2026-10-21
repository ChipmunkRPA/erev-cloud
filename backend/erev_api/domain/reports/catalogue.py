"""Standard report catalogue (04 T-RPT-01 and table 10-T; SCREENS_B §5.6; BUILD_SPEC RPS-1).

``DEFINITIONS`` holds one version-1 definition per seeded code of 04 T-RPT-01, in that list's order:
the 55 RPS codes, the 2 LMG codes and the 2 FCS codes of PHASES §5.4. Tenants cannot modify a
definition (REQ-RPT-001). A changed definition is a new version, seeded by a later revision.

``parameters_schema`` is a closed JSON Schema (``additionalProperties: false``, T-RPT-01 rule 1). It
declares the parameter keys of the report's SCREENS_B §5.6 table, the ``currency_view`` key where
the specification says "Currency view: yes" (RPT-R-03), and ``known_at`` and the entity scope
``entity_codes`` for accounting reports (T-RPT-01 rule 1, RPT-R-01). The live actor-scoped
``ai_call_log_export`` instead accepts no caller-selected parameters. ``ipe_logic`` documents
the source tables, joins, filters, parameters and definition version (REQ-RPT-027).
``tie_outs`` lists codes of ``TIE_OUT_CODES`` only (REQ-RPT-003).

The RPS-1 revision seeds ``report_definition`` with the statement ``seed_statement`` renders, as a
literal. A revision may not import this domain module (DG-LAY-03), so the literal is compared with a
fresh rendering by ``tests/unit/reports/test_catalogue.py`` (the DG-ARC-07 pattern) and with the
stored rows by ``tests/pg/test_report_tables.py`` (L4-2-Q-27).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final, Literal

from erev_api.db.migration_ops import insert_rows_sql
from erev_api.enums import (
    ApprovalRequestStatus,
    ApprovalSubjectType,
    AuditOutcome,
    BookCode,
    EstimateKind,
    JudgementStatus,
    JudgementTopic,
    ManualAdjustmentKind,
    ManualAdjustmentStatus,
    ModificationStatus,
)

type ReportKind = Literal["STANDARD", "REGISTER", "DISCLOSURE", "EXTRACT", "PACK", "LEGACY_EXPORT"]
type OutputFormat = Literal["XLSX", "CSV", "PDF", "JSON", "ZIP"]

# 04 T-RPT-01 ``kind`` CHECK and ``output_formats`` subset (RPT-R-05, RPT-R-07).
REPORT_KINDS: Final = ("STANDARD", "REGISTER", "DISCLOSURE", "EXTRACT", "PACK", "LEGACY_EXPORT")
OUTPUT_FORMATS: Final = ("XLSX", "CSV", "PDF", "JSON", "ZIP")
ENTITY_SCOPE_KEY: Final = "entity_codes"
KNOWN_AT_KEY: Final = "known_at"
# F-RPS-CUTOFF-R1 (D-98 candidate 112): the read basis stored with every run — ``record``
# (L6-3-Q-19: versions recorded by the later of known_at and the job's transaction time; the
# default when known_at defaulted to the application clock) or ``historical`` (READ-1: an explicit
# as-of read keeps the supplied known_at exactly; the default when the caller supplied known_at).
KNOWN_AT_BASIS_KEY: Final = "known_at_basis"
RECORD_BASIS: Final = "record"
HISTORICAL_BASIS: Final = "historical"
JSON_SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"

# 04 table 10-T (rev 1.2; SCREENS_B RPT-R-08): code → name (copy). Results are E-98 literals.
TIE_OUT_NAMES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "TO_WATERFALL_EQ_JE_REVENUE": "Waterfall revenue equals revenue journal total",
        "TO_ROLLFORWARD_EQ_GL": "Rollforward closing equals GL balance",
        "TO_RPO_ROLLFORWARD_EQ_RPO": "RPO rollforward closing equals RPO report total",
        "TO_DISAGGREGATION_EQ_JE_REVENUE": "Disaggregation total equals revenue journal total",
        "TO_ROLLFORWARD_BALANCES": "Opening plus activity equals closing",
        "TO_BALANCES_EQ_ROLLFORWARD": "Contract balances equal rollforward closing",
        "TO_JE_POPULATION_EQ_RUNS": "Population totals equal journal run totals",
        "TO_AGING_EQ_BALANCES": "Aging totals equal contract balances",
        "TO_COST_ROLLFORWARD_BALANCES": "Cost opening plus activity equals closing",
        "TO_BBR_EQ_JE_REVENUE": "Revenue equals revenue journal total",
        "TO_IC_UNMATCHED_ZERO": "Unmatched intercompany balance is zero",
        "TO_MIGRATION_UNEXPLAINED_ZERO": "Unexplained differences are zero",
        "TO_BRIDGE_DRIVERS_EQ_DIFFERENCE": "Driver effects equal the book difference",
    }
)
TIE_OUT_CODES: Final[tuple[str, ...]] = tuple(TIE_OUT_NAMES)


@dataclass(frozen=True, slots=True)
class ReportDefinition:
    """One T-RPT-01 row."""

    code: str
    version: int
    name: str
    kind: ReportKind
    description: str
    parameters_schema: Mapping[str, Any]
    output_formats: tuple[OutputFormat, ...]
    ipe_logic: Mapping[str, Any]
    tie_outs: tuple[str, ...] = ()
    is_current: bool = True

    def __post_init__(self) -> None:
        if self.version < 1 or not self.output_formats:
            raise ValueError(f"{self.code}: version from 1 and at least one output format")
        unknown = [code for code in self.tie_outs if code not in TIE_OUT_NAMES]
        if unknown:
            raise ValueError(f"{self.code}: tie-out codes outside table 10-T: {unknown}")
        if self.code == "ai_call_log_export":
            if self.parameters_schema != {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            }:
                raise ValueError("live call exports accept no caller-selected filters")
            return
        properties = self.parameters_schema.get("properties", {})
        if self.parameters_schema.get("additionalProperties") is not False or not {
            ENTITY_SCOPE_KEY,
            KNOWN_AT_KEY,
        } <= set(properties):
            raise ValueError(
                f"{self.code}: parameters_schema must be closed with known_at and scope"
            )


# --- parameter schemas ----------------------------------------------------------------------

_UUID: Final = {"type": "string", "format": "uuid"}
_DATE: Final = {"type": "string", "format": "date"}
_INSTANT: Final = {"type": "string", "format": "date-time"}
_TEXT: Final = {"type": "string", "minLength": 1}
_FLAG: Final = {"type": "boolean"}
# 04 T-REF-06 ``period_key``: FY<fiscal year>-P<two-digit period number>.
_PERIOD_KEY: Final = {"type": "string", "pattern": "^FY[0-9]{4}-P[0-9]{2}$"}


def _one_of(*values: str) -> dict[str, Any]:
    return {"type": "string", "enum": list(values)}


def _any_of(values: Sequence[str]) -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string", "enum": list(values)}, "uniqueItems": True}


def _codes(*, max_items: int | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": _TEXT, "minItems": 1, "uniqueItems": True}
    if max_items is not None:
        schema["maxItems"] = max_items
    return schema


# The API-S-ReportRunCreate keys of 04 §16.9 and the report-specific keys of SCREENS_B §5.6 whose
# meaning does not differ between reports; a report whose key means something else overrides it.
PARAMETER_SCHEMAS: Final[Mapping[str, Mapping[str, Any]]] = MappingProxyType(
    {
        "action": _TEXT,
        "actor_id": _UUID,
        "against_version_id": _UUID,
        "as_of": _DATE,
        "book": _one_of(*BookCode),
        "contract_external_id": _TEXT,
        "contract_external_ids": {**_codes(max_items=50)},
        "contract_id": _UUID,
        "currency_view": _one_of("transaction", "functional", "reporting"),
        "date_of_initial_application": _DATE,
        "dimension_code": _TEXT,
        "entity_codes": _codes(),
        "estimate_kind": _any_of(list(EstimateKind)),
        "filters": {"type": "object", "additionalProperties": {"type": "string"}},
        "forecast_run_id": _UUID,
        "from": _INSTANT,
        "from_date": _DATE,
        "from_period_key": _PERIOD_KEY,
        "from_period_lock_id": _UUID,
        "granularity": _one_of("MONTH", "QUARTER", "YEAR"),
        "include_cancelled": _FLAG,
        "include_removed": _FLAG,
        "include_revoked": _FLAG,
        "include_timing": _FLAG,
        "include_zero": _FLAG,
        "known_at": _INSTANT,
        "known_at_basis": _one_of(RECORD_BASIS, HISTORICAL_BASIS),
        "known_since": _INSTANT,
        "measure": _one_of("TOTAL", "BY_STATE"),
        "migration_id": _UUID,
        "object_id": _UUID,
        "object_type": _TEXT,
        "only_changes": _FLAG,
        "only_differences": _FLAG,
        "only_with_provision": _FLAG,
        "origin_period_key": _PERIOD_KEY,
        "outcome": _any_of(list(AuditOutcome)),
        "period_key": _PERIOD_KEY,
        "period_lock_id": _UUID,
        "quarter": _FLAG,
        "ssp_book_code": _TEXT,
        "ssp_book_version_id": _UUID,
        "time_bands": {
            "type": "array",
            "items": {"type": "integer", "minimum": 1},
            "minItems": 1,
            "uniqueItems": True,
        },
        "to": _INSTANT,
        "to_date": _DATE,
        "to_period_key": _PERIOD_KEY,
        "to_period_lock_id": _UUID,
        "topic": _any_of(list(JudgementTopic)),
        "window_days": {"type": "integer", "minimum": 0, "maximum": 31},
    }
)
_ONE_ENTITY: Final = {"entity_codes": _codes(max_items=1)}
_LEGACY_BOOK: Final = {"book": _one_of(BookCode.ASC606)}
_TIMESTAMP_AS_OF: Final = {"as_of": _INSTANT}
_EXTRACT_MODE: Final = {"mode": _one_of("FULL", "INCREMENTAL")}
# SCREENS_B RPT-23 ``subject_types``: the configuration subjects of E-08.
CONFIGURATION_SUBJECTS: Final = (
    ApprovalSubjectType.REGISTRY_VERSION,
    ApprovalSubjectType.AI_SETTINGS_VERSION,
    ApprovalSubjectType.RULE_SET_VERSION,
    ApprovalSubjectType.POB_TEMPLATE_VERSION,
    ApprovalSubjectType.ACCOUNT_MAPPING_VERSION,
    ApprovalSubjectType.FX_RATE_SET_VERSION,
    ApprovalSubjectType.SSP_BOOK_VERSION,
    ApprovalSubjectType.MAPPING_PROFILE_VERSION,
    ApprovalSubjectType.ROLE_CHANGE,
    ApprovalSubjectType.PRINCIPAL_AGENT_CHANGE,
)


def parameters_schema(
    keys: Sequence[str], overrides: Mapping[str, Mapping[str, Any]] | None = None
) -> dict[str, Any]:
    """The closed schema of ``keys``, with ``entity_codes`` first and ``known_at`` last when the
    specification's table does not list them (T-RPT-01 rule 1)."""
    ordered = list(keys)
    if ENTITY_SCOPE_KEY not in ordered:
        ordered.insert(0, ENTITY_SCOPE_KEY)
    if KNOWN_AT_KEY not in ordered:
        ordered.append(KNOWN_AT_KEY)
    if KNOWN_AT_BASIS_KEY not in ordered:
        ordered.append(KNOWN_AT_BASIS_KEY)  # stored with known_at (D-98 candidate 112)
    if len(set(ordered)) != len(ordered):
        raise ValueError(f"duplicate parameter keys in {ordered}")
    chosen = overrides or {}
    properties = {key: dict(chosen.get(key) or PARAMETER_SCHEMAS[key]) for key in ordered}
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
    }


def unknown_parameter_keys(
    definition: ReportDefinition, parameters: Mapping[str, Any]
) -> tuple[str, ...]:
    """The keys of ``parameters`` that the closed ``parameters_schema`` rejects (T-RPT-01 rule 1;
    API-S-ReportRunCreate answers them with 422 ``validation-failed``)."""
    properties = definition.parameters_schema["properties"]
    return tuple(sorted(key for key in parameters if key not in properties))


def _definition(
    code: str,
    name: str,
    kind: ReportKind,
    formats: tuple[OutputFormat, ...],
    description: str,
    keys: Sequence[str],
    *,
    sources: Sequence[str],
    joins: Sequence[str],
    filters: Sequence[str],
    tie_outs: Sequence[str] = (),
    overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> ReportDefinition:
    schema = parameters_schema(keys, overrides)
    return ReportDefinition(
        code=code,
        version=1,
        name=name,
        kind=kind,
        description=description,
        parameters_schema=schema,
        output_formats=formats,
        ipe_logic={
            "version": 1,
            "source_tables": list(sources),
            "joins": list(joins),
            "filters": list(filters),
            "parameters": list(schema["properties"]),
        },
        tie_outs=tuple(tie_outs),
    )


# --- shared IPE phrases -----------------------------------------------------------------------

_ALL: Final[tuple[OutputFormat, ...]] = ("XLSX", "CSV", "PDF", "JSON")
_NO_PDF: Final[tuple[OutputFormat, ...]] = ("XLSX", "CSV", "JSON")
_DATASET: Final[tuple[OutputFormat, ...]] = ("CSV", "JSON")
_SCOPE: Final = "entity code in entity_codes and within the caller's entity scope"
_BOOK: Final = "book_code = book"
_KNOWN: Final = "rows recorded at or before known_at"
# 04 T-CON-04 reading rule (rev 1.175, rev 1.187; items RPT-FORMER-GROUP-VERSIONS-1 and
# RPT-FORMER-GROUP-READERS-1): a version counts for a member contract only while that contract
# is a member of the version's group, and a contract is read from the last version along its
# chain.
_LATEST: Final = (
    "per contract, the last contract_version of the book known at known_at along the contract's "
    "chain of combination groups, of the versions computed with the contract among their "
    "members (combination_group_member, contract_computation)"
)
_CHAIN: Final = (
    "per contract, the contract_version at the date along the contract's chain of combination "
    "groups: the versions recorded while the contract was a member of their group "
    "(combination_group_member)"
)
# Supervisor ruling R-117 (a) (item RPT-FORMER-GROUP-READERS-1): the number of a version in the
# contract history counts along the contract's chain, not within one combination group.
_NUMBERED: Final = (
    "the version number counts the versions computed with the contract among their members "
    "while it was a member of their combination group, along the contract's chain of groups in "
    "record order (combination_group_member, contract_computation)"
)
_PERIODS: Final = "period_key from from_period_key to to_period_key"
_DATES: Final = "dates from from_date to to_date inclusive"
_CONTRACT: Final = "contract.external_id = contract_external_id when given"


def _as_locked(kind: str) -> str:
    return f"with period_lock_id, the values frozen at that lock (lock_snapshot kind {kind})"


# Supervisor ruling R-63 (c): an event an import commit wrote as SYSTEM is shown with its upload's
# uploader and approval (RPT-16, RPT-17; ``builders.event_provenance``).
_IMPORTED_EVENT: Final = (
    "contract_event.import_upload_id = import_upload.id (an event written by SYSTEM for an "
    "import: recorded by = the upload's creator)"
)
_IMPORT_APPROVAL: Final = (
    "import_upload.approval_request_id = approval_request.id (the approval of such an event)"
)
_INCREMENTAL: Final = (
    "mode INCREMENTAL: rows created (recorded for events and subledger lines) after known_since "
    "and at or before the source time"
)
_SOURCE_TIME: Final = "source time: the lock of period_lock_id when given, else known_at"

DEFINITIONS: Final[tuple[ReportDefinition, ...]] = (
    _definition(
        "revenue_waterfall",
        "Revenue waterfall",
        "STANDARD",
        _ALL,
        "Recognized, scheduled and awaiting-trigger revenue by contract, obligation, product or "
        "revenue category and period over a range (REQ-RPT-004).",
        (
            "entity_codes",
            "book",
            "from_period_key",
            "to_period_key",
            "as_of",
            "known_at",
            "period_lock_id",
            "row_dimension",
            "granularity",
            "measure",
            "contract_external_id",
            "currency_view",
            "filters",
        ),
        overrides={
            "row_dimension": _one_of("CONTRACT", "OBLIGATION", "PRODUCT", "REVENUE_CATEGORY")
        },
        sources=(
            "schedule_line",
            "subledger_line",
            "tenant",
            "fx_rate",
            "fx_rate_set",
            "fx_rate_set_version",
            "contract_version",
            "obligation_version",
            "contract",
            "customer",
            "legal_entity",
            "product",
            "period",
            "journal_line",
            "lock_snapshot",
            "combination_group_member",
            "contract_computation",
            "calc_trace",
            "contract_event",
        ),
        joins=(
            "schedule_line.contract_version_id = contract_version.id",
            "schedule_line.subject_id = obligation_version.obligation_id and "
            "schedule_line.contract_version_id = obligation_version.contract_version_id",
            "schedule_line.contract_id = contract.id",
            "contract.customer_id = customer.id",
            "schedule_line.entity_id = legal_entity.id",
            "schedule_line.period_id = period.id",
            "obligation_version.product_id = product.id",
            "combination_group_member.combination_group_id = contract_version.combination_group_id",
            "contract_version.contract_computation_id = contract_computation.id",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            "schedule_line.subject_type = 'obligation'",
            _LATEST,
            _PERIODS,
            _CONTRACT,
            _as_locked("WATERFALL"),
            "historical time-based schedules freeze the original allocation segment at the "
            "reporting cut; dated projections reconcile to the remainder and retain cut-specific "
            "drill-through",
            "original period projections survive removed current schedule lines; source evidence "
            "is the contract version trace for the exact reporting cut and future period",
            "scheduled and awaiting remainders use original period-level recognition-hold and "
            "pattern evidence reconciled to the version state; future holds do not alter earlier "
            "time-based projections",
            "fixed-only manual releases, deferrals and schedule overrides replay only events "
            "effective at the reporting cut; unsupported component mixtures or unreproducible "
            "snapshots retain explicit projection errors",
            "manual projection freezes realized usage at the reporting cut and replays fixed "
            "plus PERIOD_VC targets without proportional allocation; schedule overrides retain "
            "anchor-period realized consideration and recognize subsequent usage immediately; "
            "royalty and netted projections remain unavailable",
            "royalty manual projections freeze original statements and effective estimate pins "
            "at the reporting cut; minimum guarantees and recognized royalty sources must remain "
            "stable over the frozen horizon; schedule overrides retain anchor royalties and "
            "subsequent signed royalty changes separately",
            "Step-1 netted forecasts freeze original deposit recognitions and cite their "
            "attributed shares; a separate dated reporting remainder excludes already-recognized "
            "deposit revenue while preserving contract measurement balances; projected future "
            "periods must reconcile to that net remainder",
            "Waterfall entry dates come from the first included contract version on its "
            "membership chain and its book-specific entry event; contracts entering after "
            "the performing entity as-of period are excluded; retained entry bindings and "
            "legacy populations remain unchanged on rerun",
        ),
        tie_outs=("TO_WATERFALL_EQ_JE_REVENUE",),
    ),
    _definition(
        "contract_balances",
        "Contract balances",
        "STANDARD",
        _ALL,
        "Contract liability, contract asset, unbilled receivable, refund liability and the other "
        "contract balances per contract and contracting entity at a period end (REQ-RPT-005).",
        (
            "entity_codes",
            "book",
            "period_key",
            "period_lock_id",
            "include_zero",
            "contract_external_id",
            "currency_view",
        ),
        sources=(
            "contract_version_balance",
            "contract_version",
            "contract",
            "customer",
            "legal_entity",
            "period",
            "lock_snapshot",
            "combination_group_member",
            "contract_computation",
            "tenant",
            "fx_rate",
            "fx_rate_set",
            "fx_rate_set_version",
        ),
        joins=(
            "contract_version_balance.contract_version_id = contract_version.id",
            "contract_version_balance.contract_id = contract.id",
            "contract.customer_id = customer.id",
            "contract_version_balance.entity_id = legal_entity.id",
            "combination_group_member.combination_group_id = contract_version.combination_group_id",
            "contract_version.contract_computation_id = contract_computation.id",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            "per contract, the last contract_version known at known_at along the contract's chain "
            "of combination groups, of the versions computed with the contract among their "
            "members (combination_group_member, contract_computation), read at the end of "
            "period_key",
            "include_zero false: contracts with a non-zero balance only",
            _CONTRACT,
            _as_locked("CONTRACT_BALANCES"),
            "GL bridge v2 compares report, retained reconciliation subledger and GL per "
            "entity and role in functional currency; either nonzero leg fails even when net "
            "differences cancel; missing subledger evidence is unavailable and v1 bindings "
            "retain two-way semantics",
            "GL bridge v3 requires the latest retained reconciliation to be reviewed or "
            "certified; draft, prepared, reopened or missing status is unavailable; "
            "historical v1 and v2 bindings preserve their original arithmetic controls",
            "GL bridge v4 selects the latest source identity before checking mutable state; "
            "a source changed after the report cutoff is unavailable and never replaced "
            "by an older reviewed source; retained v1-v3 bindings remain unchanged",
        ),
        tie_outs=("TO_BALANCES_EQ_ROLLFORWARD", "TO_ROLLFORWARD_EQ_GL"),
    ),
    _definition(
        "contract_balance_rollforward",
        "Contract balance rollforward",
        "DISCLOSURE",
        _ALL,
        "Opening balance, billings, revenue, reclassifications, FX remeasurement, business "
        "combinations, other movements and closing balance of contract liabilities, contract "
        "assets and unbilled receivables over a range (REQ-RPT-006; ASC 606-10-50-8 to 50-10).",
        (
            "entity_codes",
            "book",
            "from_period_key",
            "to_period_key",
            "balance_role",
            "period_lock_id",
            "currency_view",
        ),
        overrides={
            "balance_role": _one_of("CONTRACT_LIABILITY", "CONTRACT_ASSET", "UNBILLED_RECEIVABLE")
        },
        sources=(
            "subledger_line",
            "subledger_posting",
            "close_pass_evidence",
            "computation_evidence",
            "contract_version",
            "subledger_posting_seal",
            "file_object",
            "contract_version_balance",
            "calc_trace",
            "fx_layer_movement",
            "contract_event",
            "contract",
            "customer",
            "period",
            "lock_snapshot",
            "reconciliation",
            "tenant",
            "fx_rate",
            "fx_rate_set",
            "fx_rate_set_version",
        ),
        joins=(
            "subledger_line.subledger_posting_id = subledger_posting.id",
            "close_pass_evidence.subledger_posting_id = subledger_posting.id; "
            "retained entry index identifies the source group",
            "close_pass_evidence.file_id = file_object.id; "
            "authenticated pass input/output and paid-line history",
            "subledger_line.contract_version_id = contract_version.id; "
            "contract_version.contract_computation_id = "
            "computation_evidence.contract_computation_id",
            "computation_evidence retains original input/output files and per-book seal cutoff",
            "subledger_line.contract_id = contract.id",
            "subledger_line.period_id = period.id",
            "contract_version_balance.contract_id = contract.id",
            "calc_trace.contract_version_id = contract_version_balance.contract_version_id",
            "contract_event.contract_id = contract.id (billing documents)",
            "contract.customer_id = customer.id",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            _PERIODS,
            "subledger_line.account_role is a contract balance role",
            "opening: balance at the end of the period before from_period_key; closing: balance at "
            "the end of to_period_key",
            "billing that posts no line (billing.posting = ERP): per period the delta of the "
            "calc_trace node billed_unconditional_cum less the BILLING and CREDIT_MEMO lines of "
            "the role; where not zero and the role holds no such line, the period's kept "
            "BILLING_RECORDED lines and CREDIT_MEMO_RECORDED events, not voided, at their "
            "effective dates",
            "functional/reporting close FX uses signed asset/liability source layers, "
            "prior targets and recursively retained paid lines",
            "source binding retains posted-history dependencies and evidence hashes; "
            "unavailable source attribution refuses",
            "EVENT FX nets actual retained deltas by dated source before billing or revenue; "
            "source-backed reports replace synthetic settlement offsets",
            "combined memo billing reads authorized same-version member layers; credit-memo "
            "spot portions follow retained relief order with cumulative rounding",
            "combined liability reclassifications bridge original layer carrying and retained "
            "member presentation at each endpoint, plus cross-member memo source transfers; "
            "each original computation group conserves zero and evidence is bound",
            "new member presentation bridges include all foreign contract/entity endpoints, "
            "even without a memo or FX journal; legacy v1 bindings retain memo-triggered scope",
            "cross-member revenue reconciles the entire posted delta to original signed sources; "
            "liability consumption separately reproduces retained owner/layer relief while "
            "own-member asset creation remains asset revenue; original layer dates classify "
            "opening consumption and v4 presentation binds the liability relief amounts",
            "new source-backed revenue runs recursively reconcile original functional targets, "
            "prior targets and sealed paid-line history; reversals must reproduce the same "
            "owner/layer relief population and preserve evidence on rerun",
            "v5 presentation includes own-member asset settlements and newly created liabilities "
            "from original signed revenue sources, including returns whose source consumption "
            "predates the selected range; new liabilities are not opening relief",
            "cross-member revenue asset settlements retain their original layer owner and "
            "signed member transfers; an asset bridge reconciles original carrying to presented "
            "contract-asset/unbilled endpoints and conserves the full group at each endpoint",
            "cross-member billing asset settlements retain original asset amounts and owner "
            "transfers; asset bridge v2 separates settled assets from any excess billing that "
            "creates a liability, with independently reconciled per-period billing roles",
            "contracting intercompany relief uses the same-entity INTERCOMPANY_DUE_TO counterpart "
            "and its original paid population; bridge v6 includes source-backed same-currency "
            "groups and return-month-only presentation, while earlier bindings retain their scope",
            "unexplained OTHER on any individual contract fails even when currency totals cancel",
            _as_locked("CONTRACT_BALANCE_ROLLFORWARD"),
            "mixed revenue inputs use retained per-input TIME amounts in both currencies only "
            "when original sources have one contract, layer, movement kind, date and source "
            "identity; ambiguous ownership is not proportionally assigned",
            "GL bridge v2 compares report, retained reconciliation subledger and GL per "
            "entity and role in functional currency; either nonzero leg fails even when net "
            "differences cancel; missing subledger evidence is unavailable and v1 bindings "
            "retain two-way semantics",
            "mixed revenue inputs spanning original sources use retained recognition-period "
            "classes only when every source period is uniform TIME or EVENT and both currency "
            "TIME totals reconcile; mixed periods and unmatched functional allocation remain "
            "unavailable",
            "agent gross control relief is reconciled to separately retained net revenue "
            "and AP_SUPPLIER components in both currencies; split targets require unique "
            "original source ownership and supplier history capability, otherwise "
            "attribution is unavailable",
            "zero-net agent control relief uses its sole retained AP_SUPPLIER counterpart, with "
            "no synthetic revenue line; supplier amounts and original signed sources must "
            "reconcile in both currencies",
            "mixed recognition periods may use retained transaction and functional TIME target "
            "deltas only with one original provenance per mixed period; totals must reconcile "
            "in both currencies and ambiguous within-period owners remain unavailable",
            "multi-source agent relief uses original gross control target and paid history for "
            "ownership; net revenue and supplier components separately verify split formulas "
            "and paid amounts in both currencies without allocating component amounts across "
            "owners",
            "combined-member refunds classify billing from retained asset and liability sources "
            "even when asset consumption is zero; full-return recipients replay original negative "
            "postings when latest targets no longer retain prior consumed layers",
            "GL bridge v3 requires the latest retained reconciliation to be reviewed or "
            "certified; draft, prepared, reopened or missing status is unavailable; "
            "historical v1 and v2 bindings preserve their original arithmetic controls",
            "GL bridge v4 selects the latest source identity before checking mutable state; "
            "a source changed after the report cutoff is unavailable and never replaced "
            "by an older reviewed source; retained v1-v3 bindings remain unchanged",
        ),
        tie_outs=("TO_ROLLFORWARD_BALANCES", "TO_BALANCES_EQ_ROLLFORWARD", "TO_ROLLFORWARD_EQ_GL"),
    ),
    _definition(
        "revenue_from_opening_liability",
        "Revenue from the opening contract liability",
        "DISCLOSURE",
        _ALL,
        "Revenue recognized in a range that was included in the contract liability at the "
        "beginning of the range (REQ-RPT-007; ASC 606-10-50-8(b)).",
        (
            "entity_codes",
            "book",
            "period_lock_id",
            "from_period_key",
            "to_period_key",
            "currency_view",
        ),
        sources=(
            "contract_version_balance",
            "subledger_line",
            "contract",
            "customer",
            "legal_entity",
            "period",
            "lock_snapshot",
            "period_lock",
            "subledger_posting",
            "close_pass_evidence",
            "computation_evidence",
            "contract_version",
            "subledger_posting_seal",
            "file_object",
            "calc_trace",
            "fx_layer_movement",
            "contract_event",
            "tenant",
            "fx_rate",
            "fx_rate_set",
            "fx_rate_set_version",
        ),
        joins=(
            "contract_version_balance.contract_id = contract.id",
            "subledger_line.contract_id = contract.id",
            "subledger_line.period_id = period.id",
            "contract.customer_id = customer.id",
            "contract_version_balance.entity_id = legal_entity.id",
            "functional/reporting sources share the retained contract balance rollforward "
            "version, movement, posting-delta and reporting-rate joins",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            "opening contract liability at the end of the period before from_period_key",
            "subledger_line.account_role = 'REVENUE' in the range",
            "relief: the CONTRACT_LIABILITY lines of entry kinds REVENUE_RECOGNITION and "
            "INTERCOMPANY in the range, net; the INTERCOMPANY relief is counted as revenue "
            "recognized",
            "consumption per accounting.rollforward.opening_liability_consumption (POL-126)",
            "new functional/reporting runs use reconciled original liability-layer relief; "
            "combined opening holders and recognizing members are both included, without a "
            "same-member opening cap; original bindings retain their prior path",
            "reporting openings use preceding closing rates and recognized flows use their "
            "period averages; translation rates and source method are bound for rerun",
            "new positive transaction runs pool control flows by retained computation version, "
            "entity and currency; actual opening-layer consumption is assigned to each recognizing "
            "member after prior non-revenue debits; source groups and lines are bound",
            "functional/reporting mixed liability consumption and own-member asset creation "
            "use original source amounts; only consumed opening liabilities enter opening relief",
            "own-member return sources distinguish asset settlement from new-liability creation; "
            "both complete-range and return-month-only views retain prior-period dependencies",
            "returns settling another member's asset retain signed settlement transfers and "
            "the original asset carrying bridge; asset settlement never becomes opening relief",
            "cross-member invoices likewise distinguish original asset settlement from newly "
            "created liability before subsequent opening-liability consumption",
            "functional/reporting cross-member liability relief includes source-proven revenue "
            "reversals using original functional targets and recursive paid-line attribution",
            "transaction revenue reversals use original signed sources, layer creation dates "
            "and recursively verified paid lines, including contracting intercompany due-to "
            "counterparts; asset settlement and new liabilities are not opening relief; earlier "
            "legacy bindings retain their original builder",
            _as_locked("CONTRACT_BALANCE_ROLLFORWARD"),
            "mixed revenue inputs use retained per-input TIME amounts in both currencies only "
            "when original sources have one contract, layer, movement kind, date and source "
            "identity; ambiguous ownership is not proportionally assigned",
            "mixed revenue inputs spanning original sources use retained recognition-period "
            "classes only when every source period is uniform TIME or EVENT and both currency "
            "TIME totals reconcile; mixed periods and unmatched functional allocation remain "
            "unavailable",
            "agent gross control relief is reconciled to separately retained net revenue "
            "and AP_SUPPLIER components in both currencies; split targets require unique "
            "original source ownership and supplier history capability, otherwise "
            "attribution is unavailable",
            "zero-net agent control relief uses its sole retained AP_SUPPLIER counterpart, with "
            "no synthetic revenue line; supplier amounts and original signed sources must "
            "reconcile in both currencies",
            "mixed recognition periods may use retained transaction and functional TIME target "
            "deltas only with one original provenance per mixed period; totals must reconcile "
            "in both currencies and ambiguous within-period owners remain unavailable",
            "multi-source agent relief uses original gross control target and paid history for "
            "ownership; net revenue and supplier components separately verify split formulas "
            "and paid amounts in both currencies without allocating component amounts across "
            "owners",
        ),
    ),
    _definition(
        "revenue_from_prior_period_obligations",
        "Revenue from obligations satisfied in prior periods",
        "DISCLOSURE",
        _ALL,
        "Revenue recognized in a range from performance obligations satisfied before the range, by "
        "cause (REQ-RPT-008; ASC 606-10-50-12A).",
        (
            "entity_codes",
            "book",
            "period_lock_id",
            "from_period_key",
            "to_period_key",
            "currency_view",
        ),
        sources=(
            "schedule_line",
            "obligation_version",
            "contract",
            "product",
            "legal_entity",
            "period",
            "lock_snapshot",
        ),
        joins=(
            "schedule_line.subject_id = obligation_version.obligation_id and "
            "schedule_line.contract_version_id = obligation_version.contract_version_id",
            "schedule_line.contract_id = contract.id",
            "obligation_version.product_id = product.id",
            "schedule_line.entity_id = legal_entity.id",
            "schedule_line.period_id = period.id",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            _PERIODS,
            "catch-up schedule lines of obligations satisfied before from_period_key",
            "cause: transaction price change, estimate change or modification (POL-204)",
            _as_locked("PRIOR_PERIOD_POB_REVENUE"),
        ),
    ),
    _definition(
        "rpo",
        "Remaining performance obligations",
        "DISCLOSURE",
        _ALL,
        "Transaction price allocated to unsatisfied and partially satisfied obligations at a "
        "period end, by time band, with the contracts excluded under practical expedients "
        "(REQ-RPT-009; ASC 606-10-50-13 to 50-15).",
        (
            "entity_codes",
            "book",
            "period_key",
            "period_lock_id",
            "time_bands",
            "row_dimension",
            "currency_view",
        ),
        overrides={
            "row_dimension": _one_of("CONTRACT", "ENTITY", "PRODUCT_FAMILY", "CUSTOMER_SEGMENT")
        },
        sources=(
            "tenant",
            "fx_rate",
            "fx_rate_set",
            "fx_rate_set_version",
            "obligation_version",
            "schedule_line",
            "contract_version",
            "contract_computation",
            "computation_evidence",
            "contract",
            "customer",
            "product",
            "legal_entity",
            "period",
            "registry_version",
            "lock_snapshot",
            "combination_group_member",
            "calc_trace",
        ),
        joins=(
            "obligation_version.contract_version_id = contract_version.id",
            "obligation_version.contract_id = contract.id",
            "schedule_line.subject_id = obligation_version.obligation_id and "
            "schedule_line.contract_version_id = obligation_version.contract_version_id",
            "contract.customer_id = customer.id",
            "obligation_version.product_id = product.id",
            "obligation_version.contracting_entity_id = legal_entity.id",
            "combination_group_member.contract_id = contract.id",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            _CHAIN,
            "unsatisfied and partially satisfied obligations at the end of period_key",
            "remaining amounts by expected period of recognition, banded by time_bands (POL-201)",
            "section 2: contracts exempt under POL-197 to POL-200 set to APPLY",
            _as_locked("RPO"),
            "historical time-based schedules freeze the original allocation segment at the "
            "reporting cut; dated projections reconcile to the remainder and retain cut-specific "
            "drill-through",
            "original period projections survive removed current schedule lines; source evidence "
            "is the contract version trace for the exact reporting cut and future period",
            "scheduled and awaiting remainders use original period-level recognition-hold and "
            "pattern evidence reconciled to the version state; future holds do not alter earlier "
            "time-based projections",
            "fixed-only manual releases, deferrals and schedule overrides replay only events "
            "effective at the reporting cut; unsupported component mixtures or unreproducible "
            "snapshots retain explicit projection errors",
            "manual projection freezes realized usage at the reporting cut and replays fixed "
            "plus PERIOD_VC targets without proportional allocation; schedule overrides retain "
            "anchor-period realized consideration and recognize subsequent usage immediately; "
            "royalty and netted projections remain unavailable",
            "royalty manual projections freeze original statements and effective estimate pins "
            "at the reporting cut; minimum guarantees and recognized royalty sources must remain "
            "stable over the frozen horizon; schedule overrides retain anchor royalties and "
            "subsequent signed royalty changes separately",
            "Step-1 netted forecasts freeze original deposit recognitions and cite their "
            "attributed shares; a separate dated reporting remainder excludes already-recognized "
            "deposit revenue while preserving contract measurement balances; projected future "
            "periods must reconcile to that net remainder",
        ),
        tie_outs=("TO_RPO_ROLLFORWARD_EQ_RPO",),
    ),
    _definition(
        "rpo_rollforward",
        "RPO rollforward",
        "DISCLOSURE",
        _ALL,
        "Opening remaining performance obligations, new contracts, modifications, variable "
        "consideration estimate changes, revenue, cancellations, FX, unexplained difference and "
        "closing over a range (REQ-RPT-010).",
        (
            "entity_codes",
            "book",
            "period_lock_id",
            "from_period_key",
            "to_period_key",
            "currency_view",
        ),
        sources=(
            "tenant",
            "fx_rate",
            "fx_rate_set",
            "fx_rate_set_version",
            "calc_trace",
            "obligation_version",
            "contract_version",
            "contract_computation",
            "computation_evidence",
            "contract_event",
            "contract",
            "period",
            "lock_snapshot",
            "combination_group_member",
        ),
        joins=(
            "obligation_version.contract_version_id = contract_version.id",
            "obligation_version.contract_id = contract.id",
            "contract_event.contract_id = contract.id",
            "combination_group_member.contract_id = contract.id",
            "calc_trace.contract_version_id = contract_version.id; "
            "estimate-event shares reconcile to original tp_delta nodes",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            "opening: RPO at the end of the period before from_period_key; closing: RPO at the end "
            "of to_period_key",
            _CHAIN,
            "movements classified by the contract_event that caused each contract version",
            "full RPO exemption eligibility is evaluated per retained version; "
            "opening and closing exclusions are separate, with eligibility changes in EXEMPTIONS",
            "terminal cancellations remove only unrecognized allocation; "
            "retained cancelled-version revenue separates period recognition and late restatement",
            "cancellation and re-entry histories use separate disclosure segments; "
            "re-entry admits remaining RPO and revenue excludes changes while outside disclosure",
            "mixed modification and estimate changes use original event-specific estimate shares "
            "reconciled to each price delta; unsupported or incomplete evidence stays unexplained",
            _as_locked("RPO_ROLLFORWARD"),
            "measurement-only estimate pins prove no allocation movement; inception estimates "
            "and legacy pins without an explicit effect are not assumed to have zero impact",
            "first-entry batches separate later original estimate shares and dated "
            "fixed-boundary modification deltas from new contracts; modification "
            "decomposition requires complete event evidence and cancellations retain "
            "existing limits",
            "dated fixed-allocation evidence reconciles to version remainders and "
            "excludes future changes from earlier RPO; same-version estimate and "
            "modification movements require original shares and boundary deltas matching "
            "the dated allocation difference",
            "historical time-based schedules freeze the original allocation segment at the "
            "reporting cut; dated projections reconcile to the remainder and retain cut-specific "
            "drill-through",
            "original period projections survive removed current schedule lines; source evidence "
            "is the contract version trace for the exact reporting cut and future period",
            "scheduled and awaiting remainders use original period-level recognition-hold and "
            "pattern evidence reconciled to the version state; future holds do not alter earlier "
            "time-based projections",
            "fixed-only manual releases, deferrals and schedule overrides replay only events "
            "effective at the reporting cut; unsupported component mixtures or unreproducible "
            "snapshots retain explicit projection errors",
            "exemption details retain obligation-level opening and closing exclusions, "
            "policy codes and transaction-currency movement; translated views label this "
            "original basis and legacy bindings retain their existing output shape",
            "manual projection freezes realized usage at the reporting cut and replays fixed "
            "plus PERIOD_VC targets without proportional allocation; schedule overrides retain "
            "anchor-period realized consideration and recognize subsequent usage immediately; "
            "royalty and netted projections remain unavailable",
            "royalty manual projections freeze original statements and effective estimate pins "
            "at the reporting cut; minimum guarantees and recognized royalty sources must remain "
            "stable over the frozen horizon; schedule overrides retain anchor royalties and "
            "subsequent signed royalty changes separately",
            "Step-1 netted forecasts freeze original deposit recognitions and cite their "
            "attributed shares; a separate dated reporting remainder excludes already-recognized "
            "deposit revenue while preserving contract measurement balances; projected future "
            "periods must reconcile to that net remainder",
            "new obligations added to an already disclosed contract follow modification and "
            "estimate causes instead of new contracts; first admission and re-entry keep "
            "admission rules; bindings without rpo_added_obligations_v1 retain their original "
            "classification",
            "translated RPO exemption details retain each contract-period original movement "
            "and its monthly-average translated amount; details sum by report currency to "
            "EXEMPTIONS even when original range endpoints cancel; older bindings keep their "
            "existing controls",
            "first-batch added obligations may omit pre-creation boundaries only with "
            "original absent-before creation evidence and independently retained earlier "
            "event order; zero allocation alone never proves absence and missing post-"
            "creation evidence remains unsupported",
        ),
        tie_outs=("TO_ROLLFORWARD_BALANCES", "TO_RPO_ROLLFORWARD_EQ_RPO"),
    ),
    _definition(
        "disaggregation",
        "Disaggregation of revenue",
        "DISCLOSURE",
        _ALL,
        "Revenue by a disaggregation dimension and timing of transfer over a range, tied to the "
        "revenue journal total (REQ-RPT-011; ASC 606-10-50-5 to 50-7).",
        (
            "entity_codes",
            "book",
            "period_lock_id",
            "from_period_key",
            "to_period_key",
            "dimension_code",
            "include_timing",
            "currency_view",
        ),
        sources=(
            "subledger_line",
            "tenant",
            "fx_rate",
            "fx_rate_set",
            "fx_rate_set_version",
            "journal_line",
            "journal_batch",
            "journal_run",
            "obligation_version",
            "product",
            "dimension_value",
            "period",
            "lock_snapshot",
        ),
        joins=(
            "subledger_line.obligation_id = obligation_version.obligation_id and "
            "subledger_line.contract_version_id = obligation_version.contract_version_id",
            "obligation_version.product_id = product.id",
            "subledger_line.period_id = period.id",
            "journal_line.journal_batch_id = journal_batch.id for the independent journal tie-out",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            _PERIODS,
            "subledger_line.account_role = 'REVENUE'; independent tie-out uses "
            "journal runs not cancelled",
            "functional reads posted amounts; reporting translates posted functional lines at "
            "their period average rates, retained for reruns",
            "grouped by dimension_code and, with include_timing, the timing of transfer",
            _as_locked("DISAGGREGATION"),
        ),
        tie_outs=("TO_DISAGGREGATION_EQ_JE_REVENUE",),
    ),
    _definition(
        "contract_history",
        "Contract history",
        "STANDARD",
        _NO_PDF,
        "One row per obligation version effective in a date range, with allocation, revenue, "
        "billing and catch-up figures (REQ-RPT-012).",
        ("entity_codes", "book", "from_date", "to_date", "contract_external_id", "known_at"),
        sources=(
            "obligation_version",
            "contract_version",
            "contract",
            "contract_event",
            "product",
            "combination_group_member",
            "contract_computation",
        ),
        joins=(
            "obligation_version.contract_version_id = contract_version.id",
            "obligation_version.contract_id = contract.id",
            "obligation_version.product_id = product.id",
            "contract_event.contract_id = contract.id",
            "combination_group_member.contract_id = contract.id",
            "contract_version.contract_computation_id = contract_computation.id",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            "obligation_version.effective_date from from_date to to_date inclusive "
            "(04 §17.1 rule 1)",
            _KNOWN,
            _CONTRACT,
            _NUMBERED,
        ),
    ),
    _definition(
        "legacy_contract_history_export",
        "Legacy contract history export",
        "LEGACY_EXPORT",
        _NO_PDF,
        "The contract history with the 71 legacy Contract_Live column names in legacy order "
        "(REQ-RPT-012; D-33; 04 §17.1, §17.2).",
        ("entity_codes", "book", "from_date", "to_date", "contract_external_id"),
        overrides=_LEGACY_BOOK,
        sources=(
            "obligation_version",
            "contract_version",
            "contract",
            "migrated_legacy_row",
            "combination_group_member",
            "contract_computation",
        ),
        joins=(
            "obligation_version.contract_version_id = contract_version.id",
            "obligation_version.contract_id = contract.id",
            "migrated_legacy_row.contract_id = contract.id",
            "combination_group_member.contract_id = contract.id",
            "contract_version.contract_computation_id = contract_computation.id",
        ),
        filters=(
            _SCOPE,
            "book fixed to ASC606",
            "04 §17.1 rules 1 to 6 over obligation versions effective from from_date to to_date",
            "rows before a cutover from migrated_legacy_row.legacy_row unchanged",
            _CONTRACT,
            _NUMBERED,
        ),
    ),
    _definition(
        "latest_contract_status",
        "Latest contract status",
        "STANDARD",
        _NO_PDF,
        "The obligation versions of each contract's latest version effective on or before a date, "
        "with balances and status (REQ-RPT-013).",
        ("entity_codes", "book", "as_of", "contract_external_id"),
        sources=(
            "obligation_version",
            "contract_version",
            "contract_version_balance",
            "contract",
            "product",
            "legal_entity",
            "combination_group_member",
            "contract_computation",
        ),
        joins=(
            "obligation_version.contract_version_id = contract_version.id",
            "obligation_version.contract_id = contract.id",
            "contract_version_balance.contract_version_id = contract_version.id",
            "obligation_version.product_id = product.id",
            "obligation_version.contracting_entity_id = legal_entity.id",
            "combination_group_member.contract_id = contract.id",
            "contract_version.contract_computation_id = contract_computation.id",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            "per contract, the latest contract version with effective_date on or before as_of "
            "among the versions recorded while the contract was a member of their group "
            "(combination_group_member), tie-broken by record_seq (04 §17.1 rule 1)",
            _KNOWN,
            _CONTRACT,
            _NUMBERED,
        ),
    ),
    _definition(
        "legacy_latest_contract_export",
        "Legacy latest contract export",
        "LEGACY_EXPORT",
        _NO_PDF,
        "The latest contract status with the 71 legacy Contract_Live column names in legacy order "
        "(REQ-RPT-013; D-33; 04 §17.1, §17.2).",
        ("entity_codes", "book", "as_of", "contract_external_id"),
        overrides=_LEGACY_BOOK,
        sources=("obligation_version", "contract_version", "contract", "migrated_legacy_row"),
        joins=(
            "obligation_version.contract_version_id = contract_version.id",
            "obligation_version.contract_id = contract.id",
            "migrated_legacy_row.contract_id = contract.id",
        ),
        filters=(
            _SCOPE,
            "book fixed to ASC606",
            "the RPT-11 row rule at as_of",
            _CONTRACT,
        ),
    ),
    _definition(
        "legacy_je_summary",
        "Legacy journal summary",
        "LEGACY_EXPORT",
        _NO_PDF,
        "Journal activity by account, by entity and by legacy line item over a date range, gross "
        "or as adjustments (REQ-JE-007, REQ-JE-008).",
        ("entity_codes", "book", "from_date", "to_date", "mode"),
        overrides={**_LEGACY_BOOK, "mode": _one_of("GROSS", "DELTA")},
        sources=("subledger_line", "subledger_posting", "gl_account", "legal_entity", "contract"),
        joins=(
            "subledger_line.subledger_posting_id = subledger_posting.id",
            "subledger_line.gl_account_id = gl_account.id",
            "subledger_line.entity_id = legal_entity.id",
            "subledger_line.contract_id = contract.id",
        ),
        filters=(
            _SCOPE,
            "book fixed to ASC606",
            "subledger_line.effective_date from from_date to to_date inclusive",
            "mode GROSS: gross lines; mode DELTA: adjustment lines against the Legacy book",
            _KNOWN,
        ),
    ),
    _definition(
        "modification_register",
        "Modification register",
        "REGISTER",
        _ALL,
        "Contract modifications with questionnaire answers, treatment, approvals, transaction "
        "price change and catch-up per obligation line (REQ-MOD-014).",
        (
            "entity_codes",
            "book",
            "from_date",
            "to_date",
            "status",
            "contract_external_id",
            "period_lock_id",
            "currency_view",
        ),
        overrides={"status": _any_of(list(ModificationStatus))},
        sources=(
            "modification",
            "contract",
            "approval_request",
            "approval_decision",
            "judgement_record",
            "contract_version",
            "lock_snapshot",
        ),
        joins=(
            "modification.contract_id = contract.id",
            "modification.approval_request_id = approval_request.id",
            "approval_decision.approval_request_id = approval_request.id",
            "modification.judgement_record_id = judgement_record.id",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            "modification.effective_date from from_date to to_date inclusive",
            "modification.status in status",
            _CONTRACT,
            _as_locked("MODIFICATION_REGISTER"),
        ),
    ),
    _definition(
        "je_population",
        "Journal entry population",
        "REGISTER",
        _NO_PDF,
        "Every journal line of the selected journal runs with preparer, approver and UTC "
        "timestamps, for population testing (REQ-JE-018).",
        (
            "entity_codes",
            "book",
            "from_period_key",
            "to_period_key",
            "period_lock_id",
            "include_cancelled",
        ),
        sources=(
            "journal_line",
            "journal_entry",
            "journal_batch",
            "journal_run",
            "posting_ack",
            "gl_account",
            "legal_entity",
            "period",
            "contract",
            "obligation",
            "lock_snapshot",
        ),
        joins=(
            "journal_line.journal_entry_id = journal_entry.id",
            "journal_line.journal_batch_id = journal_batch.id",
            "journal_batch.journal_run_id = journal_run.id",
            "posting_ack.journal_batch_id = journal_batch.id",
            "journal_line.gl_account_id = gl_account.id",
            "journal_line.period_id = period.id",
            "journal_line.contract_id = contract.id",
            "journal_line.obligation_id = obligation.id",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            _PERIODS,
            "include_cancelled false: runs not cancelled",
            _as_locked("JE_POPULATION"),
        ),
        tie_outs=("TO_JE_POPULATION_EQ_RUNS",),
    ),
    _definition(
        "out_of_period_register",
        "Out-of-period register",
        "REGISTER",
        _ALL,
        "Contract events whose effect posted in a period other than the period of their effective "
        "date, plus computed late events with zero postings. Event amounts are separate from "
        "posted effects (REQ-CLS-006; REG-LATE-NOLINE-1).",
        (
            "entity_codes",
            "book",
            "from_period_key",
            "to_period_key",
            "origin_period_key",
            "period_lock_id",
            "currency_view",
        ),
        sources=(
            "exception_item",
            "subledger_line",
            "contract_event",
            "contract",
            "approval_request",
            "import_upload",
            "period",
            "lock_snapshot",
        ),
        joins=(
            "ENGINE LATE_EVENT exception dedupe key binds contract_event.id",
            "subledger_line.contract_event_id = contract_event.id",
            "subledger_line.contract_id = contract.id",
            "subledger_line.period_id = period.id (posting period)",
            "subledger_line.origin_period_id = period.id (origin period)",
            "contract_event.approval_request_id = approval_request.id",
            _IMPORTED_EVENT,
            _IMPORT_APPROVAL,
        ),
        filters=(
            "stored LATE_EVENT period/book evidence; known_at excludes later findings",
            _SCOPE,
            _BOOK,
            "posting period_key from from_period_key to to_period_key",
            "subledger_line.origin_period_id is not null and differs from subledger_line.period_id",
            "origin period = origin_period_key when given",
            _as_locked("OUT_OF_PERIOD_REGISTER"),
        ),
    ),
    _definition(
        "late_entry_report",
        "Late-entry report",
        "REGISTER",
        _ALL,
        "Events entered after a period's first lock, and events effective near the period end "
        "(REQ-CLS-007).",
        ("entity_codes", "book", "period_key", "window_days"),
        sources=(
            "contract_event",
            "contract",
            "period",
            "period_lock",
            "approval_request",
            "import_upload",
        ),
        joins=(
            "contract_event.contract_id = contract.id",
            "period_lock.period_id = period.id",
            "contract_event.approval_request_id = approval_request.id",
            _IMPORTED_EVENT,
            _IMPORT_APPROVAL,
        ),
        filters=(
            _SCOPE,
            _BOOK,
            "section 1: contract_event.recorded_at after the first period_lock of period_key, with "
            "effective_date in the period",
            "section 2: effective_date within window_days of the period end "
            "(close.late_entry_window_days)",
        ),
    ),
    _definition(
        "manual_adjustment_register",
        "Manual adjustment register",
        "REGISTER",
        _ALL,
        "Schedule overrides, manual releases and deferrals, manual journals and account "
        "reclassifications with their approvals and attachments (REQ-JE-019; REQ-RPT-022).",
        (
            "entity_codes",
            "book",
            "from_period_key",
            "to_period_key",
            "status",
            "kind",
            "period_lock_id",
            "currency_view",
        ),
        overrides={
            "status": _any_of(list(ManualAdjustmentStatus)),
            "kind": _any_of(list(ManualAdjustmentKind)),
        },
        sources=(
            "manual_adjustment",
            "contract",
            "obligation",
            "legal_entity",
            "period",
            "approval_request",
            "approval_decision",
            "file_attachment",
            "lock_snapshot",
        ),
        joins=(
            "manual_adjustment.contract_id = contract.id",
            "manual_adjustment.obligation_id = obligation.id",
            "manual_adjustment.entity_id = legal_entity.id",
            "manual_adjustment.period_id = period.id",
            "manual_adjustment.approval_request_id = approval_request.id",
            "approval_decision.approval_request_id = approval_request.id",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            _PERIODS,
            "status and kind when given",
            _as_locked("MANUAL_ADJUSTMENT_REGISTER"),
        ),
    ),
    _definition(
        "ssp_change_log",
        "SSP change log",
        "REGISTER",
        _ALL,
        "SSP book versions with a lifecycle transition in a date range, with methodology, entry "
        "counts, diff summary and approvals (REQ-SSP-012).",
        ("from_date", "to_date", "ssp_book_code"),
        sources=(
            "ssp_book_version",
            "ssp_book",
            "ssp_entry",
            "approval_request",
            "approval_decision",
            "file_object",
        ),
        joins=(
            "ssp_book_version.ssp_book_id = ssp_book.id",
            "ssp_entry.ssp_book_version_id = ssp_book_version.id",
            "ssp_book_version.approval_request_id = approval_request.id",
            "approval_decision.approval_request_id = approval_request.id",
        ),
        filters=(
            "a lifecycle transition of the version from from_date to to_date inclusive",
            "ssp_book.code = ssp_book_code when given",
            "books of the entities in entity_codes and tenant-wide books",
        ),
    ),
    _definition(
        "ssp_version_diff",
        "SSP version diff",
        "STANDARD",
        _ALL,
        "Entries added, removed and changed between two versions of one SSP book (REQ-SSP-012).",
        ("ssp_book_version_id", "against_version_id", "only_changes"),
        sources=("ssp_entry", "ssp_range", "ssp_book_version", "product"),
        joins=(
            "ssp_entry.ssp_book_version_id = ssp_book_version.id",
            "ssp_entry.product_id = product.id",
            "ssp_range of each ssp_entry (T-REF-31)",
        ),
        filters=(
            "entry keys present in either version",
            "against_version_id: a version of the same book, by default the prior approved version",
            "only_changes true: added, removed and changed entries only",
        ),
    ),
    _definition(
        "allocations_by_ssp_version",
        "Allocations by SSP version",
        "STANDARD",
        _NO_PDF,
        "Obligation allocations at inception and 25-13(a) reallocations with the SSP book version, "
        "range check and selected SSP used (REQ-SSP-011, REQ-SSP-012).",
        ("entity_codes", "book", "ssp_book_version_id", "from_date", "to_date"),
        sources=(
            "obligation_version",
            "contract_version",
            "contract",
            "product",
            "ssp_book_version",
            "ssp_entry",
            "ssp_range",
        ),
        joins=(
            "obligation_version.contract_version_id = contract_version.id",
            "obligation_version.contract_id = contract.id",
            "obligation_version.product_id = product.id",
            "obligation_version.ssp_book_version_id = ssp_book_version.id",
            "obligation_version.ssp_entry_id = ssp_entry.id",
            "obligation_version.ssp_range_id = ssp_range.id",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            "obligation versions of an allocation event effective from from_date to to_date",
            "obligation_version.ssp_book_version_id = ssp_book_version_id when given",
        ),
    ),
    _definition(
        "ssp_override_listing",
        "SSP override listing",
        "REGISTER",
        _ALL,
        "Obligations allocated with an approved SSP version other than the effective one, with "
        "justification and approval (REQ-SSP-006, REQ-SSP-012).",
        ("entity_codes", "from_date", "to_date"),
        sources=(
            "obligation_version",
            "contract",
            "product",
            "ssp_book_version",
            "approval_request",
            "approval_decision",
        ),
        joins=(
            "obligation_version.ssp_override_approval_request_id = approval_request.id",
            "approval_decision.approval_request_id = approval_request.id",
            "obligation_version.ssp_book_version_id = ssp_book_version.id",
            "obligation_version.contract_id = contract.id",
            "obligation_version.product_id = product.id",
        ),
        filters=(
            _SCOPE,
            "obligation_version.ssp_override_approval_request_id is not null",
            "approval decided from from_date to to_date inclusive",
        ),
    ),
    _definition(
        "config_change_register",
        "Configuration change register",
        "REGISTER",
        _ALL,
        "Decided configuration approval requests with author, approvers, effective date and diff "
        "counts (REQ-RPT-022).",
        ("from_date", "to_date", "subject_types"),
        overrides={"subject_types": _any_of(CONFIGURATION_SUBJECTS)},
        sources=(
            "approval_request",
            "approval_step",
            "approval_decision",
            "audit_event",
            "file_attachment",
        ),
        joins=(
            "approval_step.approval_request_id = approval_request.id",
            "approval_decision.approval_request_id = approval_request.id",
            "audit_event.approval_request_id = approval_request.id",
        ),
        filters=(
            "approval_request.subject_type in subject_types (configuration subjects of E-08)",
            "decided from from_date to to_date inclusive",
            "requests whose every entity is in entity_codes, and tenant-level requests; a request "
            "of all entities when entity_codes names every entity",
        ),
    ),
    _definition(
        "user_access_listing",
        "User access listing",
        "REGISTER",
        _ALL,
        "Memberships and role assignments active at an instant, with entity scope, grantor, SoD "
        "exception, MFA enrolment and last login (REQ-RPT-022; REQ-CTL-006).",
        ("as_of", "include_removed"),
        overrides=_TIMESTAMP_AS_OF,
        sources=(
            "tenant_membership",
            "app_user",
            "role_assignment",
            "role",
            "sod_exception",
            "user_mfa_factor",
            "approval_request",
            "audit_event",
        ),
        joins=(
            "role_assignment.membership_id = tenant_membership.id",
            "role_assignment.role_id = role.id",
            "tenant_membership.user_id = app_user.id",
            "role_assignment.sod_exception_id = sod_exception.id",
            "role_assignment.approval_request_id = approval_request.id",
            "audit_event.object_id = tenant_membership.id (action tenant_membership.invite)",
        ),
        filters=(
            "role assignments active at as_of",
            "memberships removed at as_of are left out: REMOVED with removed_at by then, or "
            "as_of inside a removal that a later invitation ended (the invitation's audit event "
            "states the removal's instant)",
            "include_removed: removed memberships too",
            "assignments whose entity scope includes an entity of entity_codes",
        ),
    ),
    _definition(
        "sod_conflict_report",
        "SoD conflict report",
        "REGISTER",
        _ALL,
        "Members holding conflicting permissions at an instant, with the covering exception and "
        "compensating control (REQ-PLT-010; REQ-RPT-022).",
        ("as_of",),
        overrides=_TIMESTAMP_AS_OF,
        sources=(
            "sod_rule",
            "role_assignment",
            "role_permission",
            "tenant_membership",
            "app_user",
            "sod_exception",
            "approval_delegation",
        ),
        joins=(
            "role_assignment.membership_id = tenant_membership.id",
            "role_permission.role_id = role_assignment.role_id",
            "tenant_membership.user_id = app_user.id",
            "sod_exception.membership_id = tenant_membership.id",
            "approval_delegation.delegate_membership_id = tenant_membership.id",
            "approval_delegation.delegator_membership_id = tenant_membership.id",
        ),
        filters=(
            "memberships holding permissions of both functions of a published sod_rule at as_of",
            "exception status at as_of",
            "assignments whose entity scope includes an entity of entity_codes",
            "approval delegations standing at as_of and given by then, for the permissions their "
            "delegator holds at as_of through the assignments in scope",
        ),
    ),
    _definition(
        "approvals_register",
        "Approvals register",
        "REGISTER",
        _ALL,
        "Every approval request, decision and auto-approval with preparer and approver "
        "(REQ-RPT-022).",
        ("entity_codes", "from_date", "to_date", "subject_types", "status", "currency_view"),
        overrides={
            "subject_types": _any_of(list(ApprovalSubjectType)),
            "status": _any_of(list(ApprovalRequestStatus)),
        },
        sources=(
            "approval_request",
            "approval_step",
            "approval_decision",
            "app_user",
            "legal_entity",
        ),
        joins=(
            "approval_step.approval_request_id = approval_request.id",
            "approval_decision.approval_step_id = approval_step.id",
            "approval_decision.approver_id = app_user.id",
            "approval_request.entity_id = legal_entity.id",
        ),
        filters=(
            "requests whose every entity is in entity_codes, and tenant-level requests; a request "
            "of all entities when entity_codes names every entity",
            "submitted from from_date to to_date inclusive",
            "subject_types and status when given",
        ),
    ),
    _definition(
        "api_client_inventory",
        "API client inventory",
        "REGISTER",
        _ALL,
        "OAuth2 client-credentials clients with scopes, entity scope, rate limit, expiry, last "
        "use and the approval of their scopes; secrets are never shown (REQ-PLT-033).",
        ("include_revoked",),
        sources=("api_client", "app_user", "approval_request", "approval_decision", "rule"),
        joins=(
            "api_client.created_by = app_user.id",
            "approval_request.subject_type = ROLE_ASSIGNMENT and approval_request.subject_id = "
            "api_client.id",
            "approval_decision.approval_request_id = approval_request.id",
            "approval_decision.approver_id = app_user.id",
            "approval_decision.auto_rule_id = rule.id",
        ),
        filters=(
            "include_revoked false: clients not revoked",
            "clients whose entity scope includes an entity of entity_codes",
            "secret hashes are never selected",
            "the latest approval request of each client submitted by the record cutoff, with its "
            "approving decisions by the cutoff",
        ),
    ),
    _definition(
        "judgement_register",
        "Judgement register",
        "REGISTER",
        _ALL,
        "Documented accounting judgements with topic, subject, conclusion, codification "
        "references, preparer and reviewer (REQ-RPT-023).",
        ("entity_codes", "book", "from_date", "to_date", "topic", "status"),
        overrides={"status": _any_of(list(JudgementStatus))},
        sources=("judgement_record", "contract", "app_user"),
        joins=(
            "judgement_record.contract_id = contract.id",
            "judgement_record.reviewer_id = app_user.id",
            "judgement_record.supersedes_id = judgement_record.id",
        ),
        filters=(
            _SCOPE,
            "recorded from from_date to to_date inclusive",
            "topic and status when given",
        ),
    ),
    _definition(
        "estimate_change_listing",
        "Estimate change listing",
        "REGISTER",
        _ALL,
        "Approved estimate versions effective in a date range with their predecessor, method and "
        "profit or loss effect (REQ-RPT-023).",
        ("entity_codes", "book", "from_date", "to_date", "estimate_kind", "currency_view"),
        sources=(
            "estimate_version",
            "estimate",
            "contract",
            "obligation",
            "approval_request",
            "approval_decision",
            "file_attachment",
        ),
        joins=(
            "estimate_version.estimate_id = estimate.id",
            "estimate.contract_id = contract.id",
            "estimate.obligation_id = obligation.id",
            "estimate_version.supersedes_version_id = estimate_version.id (predecessor)",
            "estimate_version.approval_request_id = approval_request.id",
            "approval_decision.approval_request_id = approval_request.id",
        ),
        filters=(
            _SCOPE,
            "approved versions with effective_date from from_date to to_date inclusive",
            "estimate kind in estimate_kind when given",
        ),
    ),
    _definition(
        "scope_exclusion_register",
        "Scope exclusion register",
        "REGISTER",
        _ALL,
        "Lines routed out of Topic 606 at a period end with their measured amounts and judgement "
        "(REQ-RPT-023; REQ-CON-016).",
        ("entity_codes", "book", "period_lock_id", "period_key", "currency_view"),
        sources=(
            "obligation_version",
            "contract_version",
            "contract",
            "product",
            "judgement_record",
            "combination_group_member",
        ),
        joins=(
            "obligation_version.contract_version_id = contract_version.id",
            "obligation_version.contract_id = contract.id",
            "obligation_version.product_id = product.id",
            "judgement_record.contract_id = contract.id",
            "combination_group_member.contract_id = contract.id",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            _CHAIN,
            "obligation versions at the end of period_key with scope_flag other than IN_SCOPE_606",
        ),
    ),
    _definition(
        "loss_provision_register",
        "Loss provision register",
        "REGISTER",
        _ALL,
        "Contracts or obligations tested for anticipated losses with the estimate at completion, "
        "provision balance and movement (REQ-LOS-003).",
        (
            "entity_codes",
            "book",
            "period_lock_id",
            "period_key",
            "only_with_provision",
            "currency_view",
        ),
        sources=(
            "loss_provision_version",
            "loss_provision_eac",
            "calc_trace",
            "contract_version_balance",
            "estimate",
            "legal_entity",
            "period",
            "contract_version",
            "contract",
            "obligation",
            "estimate_version",
        ),
        joins=(
            "loss_provision_version.contract_version_id = contract_version.id",
            "contract_version.id = the report-bound version read for each contract",
            "loss_provision_version.period_key and as_of = the selected entity period",
            "loss_provision_version.obligation_id = obligation.id",
            "loss_provision_eac.loss_provision_version_id = loss_provision_version.id",
            "loss_provision_eac.estimate_version_id = estimate_version.id",
            "estimate_version.estimate_id = estimate.id",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            "contracts in the loss-test scope of the book (POL-151) at the end of period_key",
            "only_with_provision true: a non-zero provision balance",
        ),
    ),
    _definition(
        "contract_cost_rollforward",
        "Contract cost rollforward",
        "DISCLOSURE",
        _ALL,
        "Opening, additions, amortization, impairment, impairment reversal, clawbacks and closing "
        "of capitalized contract costs by category over a range (REQ-CST-006; ASC 340-40-50-3).",
        (
            "entity_codes",
            "book",
            "period_lock_id",
            "from_period_key",
            "to_period_key",
            "currency_view",
        ),
        sources=(
            "contract_cost_asset",
            "cost_asset_version",
            "schedule_line",
            "subledger_line",
            "contract",
            "period",
            "lock_snapshot",
        ),
        joins=(
            "cost_asset_version.contract_cost_asset_id = contract_cost_asset.id",
            "contract_cost_asset.contract_id = contract.id",
            "subledger_line.contract_cost_asset_id = contract_cost_asset.id",
            "schedule_line.subject_id = contract_cost_asset.id",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            _PERIODS,
            "schedule_line.subject_type = 'contract_cost_asset'",
            _as_locked("COST_ROLLFORWARD"),
        ),
        tie_outs=("TO_COST_ROLLFORWARD_BALANCES",),
    ),
    _definition(
        "book_bridge",
        "Book-to-book bridge",
        "STANDARD",
        _ALL,
        "Differences between the ASC 606 and IFRS 15 books of one entity by measure and driver "
        "over a range (REQ-BK-006).",
        ("entity_codes", "from_period_key", "to_period_key", "period_lock_id", "currency_view"),
        overrides=_ONE_ENTITY,
        sources=(
            "contract_version",
            "contract_version_balance",
            "schedule_line",
            "subledger_line",
            "contract",
            "legal_entity",
            "period",
        ),
        joins=(
            "contract_version_balance.contract_version_id = contract_version.id",
            "schedule_line.contract_version_id = contract_version.id",
            "subledger_line.contract_id = contract.id",
            "subledger_line.period_id = period.id",
        ),
        filters=(
            "one entity of entity_codes keeping both ASC606 and IFRS15",
            _PERIODS,
            "the same contracts compared in both books, differences attributed to drivers",
        ),
        tie_outs=("TO_BRIDGE_DRIVERS_EQ_DIFFERENCE",),
    ),
    _definition(
        "adoption_bridge",
        "Adoption bridge",
        "STANDARD",
        _ALL,
        "Cumulative effect of adopting Topic 606 per contract and the line-item comparison at the "
        "date of initial application (REQ-BK-007; ASC 606-10-65-1(h), (i)).",
        ("entity_codes", "date_of_initial_application", "contract_external_id"),
        overrides=_ONE_ENTITY,
        sources=(
            "contract_version",
            "contract_version_balance",
            "obligation_version",
            "contract",
            "customer",
        ),
        joins=(
            "contract_version_balance.contract_version_id = contract_version.id",
            "obligation_version.contract_version_id = contract_version.id",
            "contract_version_balance.contract_id = contract.id",
            "contract.customer_id = customer.id",
        ),
        filters=(
            "one entity of entity_codes keeping the LEGACY book",
            "ASC606 and LEGACY figures at date_of_initial_application",
            _CONTRACT,
        ),
    ),
    _definition(
        "intercompany_pairs",
        "Intercompany pairs",
        "STANDARD",
        _ALL,
        "Due-from and due-to balances between contracting and performing entities, with the "
        "unmatched amount (REQ-ENT-005).",
        (
            "entity_codes",
            "book",
            "period_lock_id",
            "from_period_key",
            "to_period_key",
            "currency_view",
        ),
        sources=("subledger_line", "obligation_version", "contract", "legal_entity", "period"),
        joins=(
            "subledger_line.counterparty_entity_id = legal_entity.id",
            "subledger_line.obligation_id = obligation_version.obligation_id",
            "subledger_line.contract_id = contract.id",
            "subledger_line.period_id = period.id",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            _PERIODS,
            "subledger_line.counterparty_entity_id is not null: an obligation performed by an "
            "entity other than the contracting entity",
        ),
        tie_outs=("TO_IC_UNMATCHED_ZERO",),
    ),
    _definition(
        "balance_aging",
        "Balance aging",
        "STANDARD",
        _ALL,
        "Contract assets, unbilled receivables and contract liabilities at a period end by age "
        "bucket (REQ-BIL-013).",
        ("entity_codes", "book", "period_lock_id", "period_key", "balance_role", "currency_view"),
        overrides={
            "balance_role": _one_of(
                "ALL", "CONTRACT_ASSET", "UNBILLED_RECEIVABLE", "CONTRACT_LIABILITY"
            )
        },
        sources=(
            "fx_layer_movement",
            "calc_trace",
            "contract_version_balance",
            "contract",
            "customer",
            "legal_entity",
            "tenant",
            "period",
            "fx_rate",
            "fx_rate_set",
            "fx_rate_set_version",
            "contract_version",
            "contract_computation",
            "combination_group_member",
            "lock_snapshot",
        ),
        joins=(
            "fx_layer_movement.contract_version_id = contract_version_balance.contract_version_id",
            "fx_layer_movement.contract_id = contract.id",
            "contract.customer_id = customer.id",
            "fx_layer_movement.entity_id = legal_entity.id",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            "non-zero balances at the end of period_key",
            "liability age: layer creation date to period end",
            "asset/unbilled age: engine attribution revenue date to period end",
            "balance_role when not ALL",
            "Functional aging uses retained original reclass shares for assets and unbilled "
            "receivables and signed functional liability-layer movements with original "
            "dates; each member and role must reconcile to dated functional balances; "
            "reporting view uses retained closing rates and cumulative bucket rounding; "
            "legacy bindings retain original behavior",
            _as_locked("BALANCE_AGING"),
        ),
        tie_outs=("TO_AGING_EQ_BALANCES",),
    ),
    _definition(
        "bookings_billings_revenue",
        "Bookings, billings and revenue",
        "STANDARD",
        _ALL,
        "Booked new contracts and modifications, billings and revenue by period bucket and entity "
        "(REQ-RPT-020).",
        (
            "entity_codes",
            "book",
            "period_lock_id",
            "from_period_key",
            "to_period_key",
            "granularity",
            "currency_view",
        ),
        sources=(
            "contract_event",
            "modification",
            "combination_group_member",
            "contract_version",
            "subledger_line",
            "subledger_posting_seal",
            "journal_line",
            "journal_entry",
            "journal_batch",
            "journal_run",
            "audit_event",
            "legal_entity",
            "period",
            "fx_rate",
            "fx_rate_set",
            "fx_rate_set_version",
        ),
        joins=(
            "modification applied_event_id binds its original application group and "
            "contract_version; predecessor supplies price delta",
            "subledger_line joins its posting seal; journal lines join entries, batches and "
            "runs with lifecycle evidence",
            "entity fiscal calendars bucket contributions; historical approved spot rates "
            "value non-functional contract and billing amounts",
        ),
        filters=(
            "entity code in entity_codes and within the caller's entity scope",
            "book_code = book",
            "period_key from from_period_key to to_period_key",
            "source-time event/version creation and sealed posting cutoffs; retained inputs "
            "supply reruns",
            "activated contract stated line values exclude bookings linked to "
            "separate-contract modifications",
            "applied modification counted once; missing or shared valuation basis refuses",
            "billing identity, credit and void rules; revenue uses posting period",
            "journal revenue excludes runs cancelled as of source time; unknown historical "
            "state refuses",
            "functional contract/billing amounts use unique approved effective-day spot "
            "rate; reporting currency and lock datasets unsupported",
        ),
        tie_outs=("TO_BBR_EQ_JE_REVENUE",),
    ),
    _definition(
        "variance_between_closes",
        "Variance between closes",
        "STANDARD",
        _ALL,
        "Changes in revenue, balances and remaining performance obligations between two locks of "
        "one period, by driver and contract (REQ-RPT-019; REQ-CLS-011).",
        ("from_period_lock_id", "to_period_lock_id", "currency_view"),
        overrides={"currency_view": _one_of("transaction", "functional", "reporting")},
        sources=("period_lock", "lock_snapshot", "disclosure_snapshot", "contract"),
        joins=(
            "lock_snapshot.period_lock_id = period_lock.id",
            "disclosure_snapshot.period_lock_id = period_lock.id",
        ),
        filters=(
            "two locks of one entity, book and period; the later recorded after the earlier",
            "locks of an entity in entity_codes",
            "changes attributed to drivers",
        ),
    ),
    _definition(
        "forecast_outputs",
        "Forecast outputs",
        "STANDARD",
        _NO_PDF,
        "Forecast revenue, billing, projected balances, projected remaining performance "
        "obligations and journal preview of a forecast run over its horizon (REQ-FC-003).",
        ("forecast_run_id", "entity_codes", "book", "currency_view"),
        sources=("forecast_run", "forecast_event_set", "scenario"),
        joins=("forecast_run.forecast_event_set_id = forecast_event_set.id",),
        filters=(
            "a succeeded forecast_run of forecast_run_id",
            "horizon periods of the run",
            _SCOPE,
            _BOOK,
        ),
    ),
    _definition(
        "actual_vs_forecast",
        "Actual vs forecast",
        "STANDARD",
        _ALL,
        "Forecast revenue against actual revenue per contract or revenue category and period "
        "within a forecast horizon (REQ-FC-005).",
        ("forecast_run_id", "row_dimension", "from_period_key", "to_period_key", "currency_view"),
        overrides={"row_dimension": _one_of("CONTRACT", "REVENUE_CATEGORY")},
        sources=(
            "forecast_run",
            "report_run",
            "scenario",
            "tenant_snapshot",
            "forecast_actuals_capture",
            "file_object",
        ),
        joins=(
            "scenario.tenant_snapshot_id binds the current production actuals capture",
            "successful refresh lineage binds archived forecast reports to the logical scenario",
        ),
        filters=(
            "periods inside the saved forecast horizon",
            "current scenario and report entity permissions; exact forecast currency basis",
            "acknowledged production revenue at snapshot cutoff; "
            "retained inputs only for same-source rebuild",
        ),
    ),
    _definition(
        "migration_reconciliation",
        "Migration reconciliation",
        "STANDARD",
        _ALL,
        "Legacy against eRev Cloud values per contract, obligation and measure of a migration, "
        "with tolerance and deviation references (REQ-MIG-003).",
        ("migration_id", "only_differences"),
        sources=("migration_reconciliation_line", "migration_batch", "exception_item"),
        joins=(
            "migration_reconciliation_line.migration_batch_id = migration_batch.id",
            "migration_reconciliation_line.exception_item_id = exception_item.id",
        ),
        filters=(
            "migration_batch.id = migration_id",
            "only_differences true: lines outside tolerance",
            "every line of the batch in the tenant; migration lines carry no entity, so "
            "entity_codes names no filter (SCREENS_B RPT-41 rev 1.13)",
        ),
        tie_outs=("TO_MIGRATION_UNEXPLAINED_ZERO",),
    ),
    _definition(
        "parallel_run_comparison",
        "Parallel-run comparison",
        "STANDARD",
        _ALL,
        "Legacy and eRev Cloud journal lines and contract balances per period after a migration "
        "cutover (REQ-MIG-007).",
        ("migration_id", "from_period_key", "to_period_key"),
        sources=(
            "migration_batch",
            "migrated_legacy_row",
            "journal_line",
            "contract_version_balance",
            "period",
        ),
        joins=(
            "migrated_legacy_row.migration_batch_id = migration_batch.id",
            "journal_line.period_id = period.id",
        ),
        filters=(
            "migration_batch.id = migration_id",
            "periods after the cutover from from_period_key to to_period_key",
            "entities in entity_codes",
        ),
    ),
    _definition(
        "audit_log_export",
        "Audit log export",
        "EXTRACT",
        _DATASET,
        "Audit events in chain order with every T-PLT-19 column, redacted JSON values and a "
        "manifest (REQ-PLT-018).",
        ("from", "to", "object_type", "object_id", "contract_id", "actor_id", "action", "outcome"),
        sources=("audit_event", "audit_event_contract"),
        joins=("audit_event_contract.audit_event_id = audit_event.id",),
        filters=(
            "audit_event.occurred_at from from to to",
            "object_type, object_id, actor_id and action when given",
            "outcome among the literals given",
            "with contract_id the events that name the contract (audit_event_contract)",
            "chain_seq order; JSON columns redacted per erev_api.audit.REDACT",
        ),
    ),
    _definition(
        "chain_verification_report",
        "Audit chain verification report",
        "REGISTER",
        ("CSV", "PDF", "JSON"),
        "Audit chain verifications finished in a time range with events checked, result, first "
        "failure and digest (REQ-PLT-020).",
        ("from", "to"),
        sources=("audit_chain_verification", "file_object"),
        joins=("audit_chain_verification.digest_file_id = file_object.id",),
        filters=("audit_chain_verification.finished_at from from to to",),
    ),
    _definition(
        "extract_contracts",
        "Extract: contracts",
        "EXTRACT",
        _DATASET,
        "Contract rows in scope as a CSV dataset with a JSON manifest (REQ-RPT-028).",
        ("mode", "entity_codes", "period_lock_id", "known_at", "known_since"),
        overrides=_EXTRACT_MODE,
        sources=("report_source_revision",),
        joins=(
            "captured contract customer_id and contracting_entity_id to latest captured "
            "code labels at known_at",
        ),
        filters=(
            _SCOPE,
            "latest database-captured revision at known_at; "
            "uncovered migration-era history refuses",
            "mode INCREMENTAL: contract created_at after known_since; "
            "not an update or deletion feed",
            "lock datasets unsupported",
        ),
    ),
    _definition(
        "extract_obligations",
        "Extract: obligations",
        "EXTRACT",
        _DATASET,
        "Obligation versions of the latest contract version per book as a CSV dataset with a JSON "
        "manifest (REQ-RPT-028).",
        ("mode", "entity_codes", "book", "period_lock_id", "known_at", "known_since"),
        overrides=_EXTRACT_MODE,
        sources=("obligation_version", "contract_version", "contract"),
        joins=(
            "obligation_version.contract_version_id = contract_version.id",
            "obligation_version.contract_id = contract.id",
        ),
        filters=(_SCOPE, _BOOK, _LATEST, _SOURCE_TIME, _INCREMENTAL),
    ),
    _definition(
        "extract_contract_versions",
        "Extract: contract versions",
        "EXTRACT",
        _DATASET,
        "Contract versions known at the source time as a CSV dataset with a JSON manifest "
        "(REQ-RPT-028).",
        ("mode", "entity_codes", "book", "period_lock_id", "known_at", "known_since"),
        overrides=_EXTRACT_MODE,
        sources=("contract_version", "contract_computation", "contract"),
        joins=(
            "contract_version.contract_computation_id = contract_computation.id",
            "contract_computation.stream_heads keys = contract.id (original members)",
        ),
        filters=(
            "Every original member contracting entity must be in the report scope",
            _BOOK,
            "version known_at and created_at at or before known_at source time; lock unsupported",
            _INCREMENTAL,
        ),
    ),
    _definition(
        "extract_schedule_lines",
        "Extract: schedule lines",
        "EXTRACT",
        _DATASET,
        "Schedule lines of the latest contract versions as a CSV dataset with a JSON manifest "
        "(REQ-RPT-028).",
        ("mode", "entity_codes", "book", "period_lock_id", "known_at", "known_since"),
        overrides=_EXTRACT_MODE,
        sources=("schedule_line", "contract_version", "contract", "period"),
        joins=(
            "schedule_line.contract_version_id = contract_version.id",
            "schedule_line.contract_id = contract.id",
            "schedule_line.period_id = period.id",
        ),
        filters=(_SCOPE, _BOOK, _LATEST, _SOURCE_TIME, _INCREMENTAL),
    ),
    _definition(
        "extract_subledger_lines",
        "Extract: subledger lines",
        "EXTRACT",
        _DATASET,
        "Subledger lines recorded at or before the source time as a CSV dataset with a JSON "
        "manifest (REQ-RPT-028).",
        ("mode", "entity_codes", "book", "period_lock_id", "known_at", "known_since"),
        overrides=_EXTRACT_MODE,
        sources=("subledger_line", "subledger_posting_seal", "contract", "period", "gl_account"),
        joins=(
            "subledger_line.contract_id = contract.id",
            "subledger_line.subledger_posting_id = subledger_posting_seal.subledger_posting_id "
            "(same tenant/book)",
            "subledger_line.period_id = period.id",
            "subledger_line.origin_period_id = period.id (origin period)",
            "subledger_line.gl_account_id = gl_account.id",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            "subledger_line.recorded_at at or before the source time",
            "source time is known_at; lock datasets unsupported",
            "line recorded_server_at and posting sealed_server_at at or before source time",
            _INCREMENTAL,
        ),
    ),
    _definition(
        "extract_journal_lines",
        "Extract: journal lines",
        "EXTRACT",
        _DATASET,
        "Journal lines of runs not cancelled as a CSV dataset with a JSON manifest (REQ-RPT-028).",
        ("mode", "entity_codes", "book", "period_lock_id", "known_at", "known_since"),
        overrides=_EXTRACT_MODE,
        sources=(
            "journal_line",
            "journal_entry",
            "journal_batch",
            "journal_run",
            "period",
            "audit_event",
        ),
        joins=(
            "journal_line.journal_entry_id = journal_entry.id",
            "journal_line.journal_batch_id = journal_batch.id",
            "journal_batch.journal_run_id = journal_run.id",
            "journal_line.period_id = period.id",
            "audit_event run and batch lifecycle transitions resolve run state at source time",
        ),
        filters=(
            _SCOPE,
            _BOOK,
            "runs not cancelled as of known_at; unknown historical state refuses",
            "line/entry/batch/run created by known_at; lock datasets unsupported",
            _INCREMENTAL,
        ),
    ),
    _definition(
        "extract_balances",
        "Extract: balances",
        "EXTRACT",
        _DATASET,
        "Contract balances of the latest contract versions as a CSV dataset with a JSON manifest "
        "(REQ-RPT-028).",
        ("mode", "entity_codes", "book", "period_lock_id", "known_at", "known_since"),
        overrides=_EXTRACT_MODE,
        sources=("contract_version_balance", "contract_version", "contract", "legal_entity"),
        joins=(
            "contract_version_balance.contract_version_id = contract_version.id",
            "contract_version_balance.contract_id = contract.id",
            "contract_version_balance.entity_id = legal_entity.id",
        ),
        filters=(_SCOPE, _BOOK, _LATEST, _SOURCE_TIME, _INCREMENTAL),
    ),
    _definition(
        "extract_events",
        "Extract: events",
        "EXTRACT",
        _DATASET,
        "Contract events recorded at or before the source time as a CSV dataset with a JSON "
        "manifest (REQ-RPT-028).",
        ("mode", "entity_codes", "period_lock_id", "known_at", "known_since"),
        overrides=_EXTRACT_MODE,
        sources=("contract_event", "contract"),
        joins=("contract_event.contract_id = contract.id",),
        filters=(
            _SCOPE,
            "contract_event.recorded_at at or before the source time",
            _SOURCE_TIME,
            _INCREMENTAL,
        ),
    ),
    _definition(
        "extract_legacy_contract_live",
        "Extract: legacy Contract_Live dataset",
        "EXTRACT",
        _DATASET,
        "The history rows of 04 §17.1 rule 1 over all dates with the 71 legacy column names as a "
        "CSV dataset with a JSON manifest (REQ-RPT-028; D-33).",
        ("mode", "entity_codes", "book", "period_lock_id", "known_at", "known_since"),
        overrides=_EXTRACT_MODE,
        sources=(
            "obligation_version",
            "contract_version",
            "contract",
            "contract_computation",
            "obligation",
            "legal_entity",
            "combination_group_member",
            "calc_trace",
        ),
        joins=(
            "obligation_version.contract_version_id = contract_version.id",
            "obligation_version.contract_id = contract.id",
            "contract_version.contract_computation_id = contract_computation.id",
            "previous_obligation_version_id identifies predecessor input",
            "calc_trace.contract_version_id supplies exact source texts",
        ),
        filters=(
            _SCOPE,
            "ASC606 only",
            "04 §17.1 rule 1 over all effective dates",
            "known_at source cutoff and row/version created_at cutoff; lock unsupported",
            _INCREMENTAL,
        ),
    ),
    _definition(
        "period_evidence_pack",
        "Period evidence pack",
        "PACK",
        ("ZIP",),
        "The close evidence of one entity, book and locked period in a ZIP with a manifest of "
        "per-file hashes (REQ-RPT-014).",
        ("entity_codes", "book", "period_key", "period_lock_id"),
        overrides=_ONE_ENTITY,
        sources=(
            "evidence_pack",
            "period_lock",
            "lock_snapshot",
            "journal_batch",
            "reconciliation",
            "signoff",
            "report_run",
            "audit_chain_verification",
        ),
        joins=(
            "evidence_pack.period_lock_id = period_lock.id",
            "lock_snapshot.period_lock_id = period_lock.id",
            "reconciliation.period_lock_id = period_lock.id",
            "signoff.subject_id = reconciliation.id (subject_type reconciliation)",
            "evidence_pack.report_run_ids holds the report runs of the pack",
        ),
        filters=(
            "one entity of entity_codes, book and period_key locked by period_lock_id",
            "files per the manifest layout of 04 T-RPT-04",
        ),
    ),
    _definition(
        "contract_sample_pack",
        "Contract sample pack",
        "PACK",
        ("ZIP", "PDF", "XLSX"),
        "Contract-to-schedule tie-out evidence for a sample of contracts as of a date "
        "(REQ-RPT-015).",
        ("entity_codes", "contract_external_ids", "as_of"),
        sources=(
            "evidence_pack",
            "contract",
            "contract_event",
            "contract_version",
            "obligation_version",
            "schedule_line",
            "subledger_line",
            "calc_trace",
        ),
        joins=(
            "evidence_pack.contract_ids holds the sampled contracts",
            "contract_event.contract_id = contract.id",
            "obligation_version.contract_id = contract.id",
            "schedule_line.contract_id = contract.id",
            "subledger_line.contract_id = contract.id",
            "calc_trace.contract_version_id = contract_version.id",
        ),
        filters=(
            "contract.external_id in contract_external_ids (1 to 50)",
            "figures as of as_of and known at known_at",
            _SCOPE,
        ),
    ),
    _definition(
        "disclosure_pack",
        "Disclosure pack",
        "DISCLOSURE",
        ("XLSX", "PDF", "JSON"),
        "The revenue disclosures of one entity, book and period with every tie-out printed, from "
        "the lock snapshots when the period is locked (REQ-RPT-003).",
        ("entity_codes", "book", "period_key", "period_lock_id", "quarter"),
        overrides=_ONE_ENTITY,
        sources=("report_run", "disclosure_snapshot", "registry_version", "period_lock"),
        joins=(
            "report_run.child_report_run_ids holds the section runs",
            "report_run.disclosure_snapshot_ids holds the snapshots read",
            "disclosure_snapshot.period_lock_id = period_lock.id",
        ),
        filters=(
            "one entity of entity_codes, book and period_key",
            "section runs of revenue_waterfall, contract_balances, contract_balance_rollforward, "
            "revenue_from_opening_liability, revenue_from_prior_period_obligations, rpo, "
            "rpo_rollforward and disaggregation (T-RPT-01 rule 2)",
            "a locked period reads the disclosure_snapshot rows frozen at lock",
            "quarter true: the fiscal quarter-to-date column",
        ),
    ),
    ReportDefinition(
        code="ai_call_log_export",
        version=1,
        name="AI call log export",
        kind="EXTRACT",
        description="Current authorized call evidence; reruns are new live evaluations.",
        parameters_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_formats=("CSV", "XLSX"),
        ipe_logic={
            "version": 1,
            "source_tables": ["ai_model_log"],
            "joins": [],
            "filters": ["Original requester scope and current source/export permissions"],
            "parameters": [],
        },
    ),
    ReportDefinition(
        code="engine_trueup_register",
        version=1,
        name="Engine true-up register",
        kind="REGISTER",
        description="Upgrade processing states and attributed ledger amounts at the record cutoff.",
        parameters_schema={
            **parameters_schema(("release_validation_id",), {"release_validation_id": _UUID}),
            "required": ["release_validation_id"],
        },
        output_formats=("XLSX", "CSV", "JSON"),
        ipe_logic={
            "version": 1,
            "source_tables": [
                "release_group_processing",
                "posting_attribution",
                "subledger_posting",
                "subledger_posting_seal",
                "subledger_line",
                "release_validation_group",
                "legal_entity",
                "period",
            ],
            "joins": ["Processing portion to attributed sealed posting lines by entity and book"],
            "filters": [
                "Exact known_at; authorized entities; whole-group terminal hidden for partial scope"
            ],
            "parameters": ["entity_codes", "release_validation_id", "known_at", "known_at_basis"],
        },
    ),
    ReportDefinition(
        code="upgrade_validation",
        version=1,
        name="Upgrade validation",
        kind="REGISTER",
        description="Frozen release validation outcomes and detailed comparison evidence.",
        parameters_schema={
            **parameters_schema(
                ("release_validation_attempt_id",), {"release_validation_attempt_id": _UUID}
            ),
            "required": ["release_validation_attempt_id"],
        },
        output_formats=("XLSX", "CSV", "JSON"),
        ipe_logic={
            "version": 1,
            "source_tables": ["release_validation_attempt", "file_object"],
            "joins": ["Immutable attempt dataset file and digest"],
            "filters": ["Current report permission for every frozen entity; no partial population"],
            "parameters": [
                "entity_codes",
                "release_validation_attempt_id",
                "known_at",
                "known_at_basis",
            ],
        },
    ),
)

DEFINITIONS_BY_CODE: Final[Mapping[str, ReportDefinition]] = MappingProxyType(
    {definition.code: definition for definition in DEFINITIONS}
)
if len(DEFINITIONS_BY_CODE) != len(DEFINITIONS):
    raise ValueError("report codes must be unique")

# --- the revision seed (DG-MIG-07) ------------------------------------------------------------

SEED_COLUMNS: Final = (
    "code",
    "version",
    "name",
    "kind",
    "description",
    "parameters_schema",
    "output_formats",
    "ipe_logic",
    "tie_outs",
    "is_current",
)


def canonical_json(value: Mapping[str, Any]) -> str:
    """Sorted, compact UTF-8 JSON: the seed literal of a jsonb value. Characters are not escaped,
    so the revision's Python literal holds no backslash sequence."""
    rendered = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if "\\" in rendered:
        raise ValueError("a seeded JSON value holds no backslash")
    return rendered


def _text_array(values: Sequence[str]) -> str:
    if any(not value.isidentifier() or not value.isupper() for value in values):
        raise ValueError(f"array literal of upper-case codes only: {values}")
    return "{" + ",".join(values) + "}"


def seed_statement() -> str:
    """The multi-row INSERT that seeds ``report_definition`` from ``DEFINITIONS``."""
    rows = [
        (
            definition.code,
            definition.version,
            definition.name,
            definition.kind,
            definition.description,
            canonical_json(definition.parameters_schema),
            _text_array(definition.output_formats),
            canonical_json(definition.ipe_logic),
            _text_array(definition.tie_outs),
            definition.is_current,
        )
        for definition in DEFINITIONS
    ]
    return insert_rows_sql("report_definition", SEED_COLUMNS, rows)
