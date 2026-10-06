"""Report run framework and stamped outputs (BUILD_SPEC RPS-2; 04 §16.9 API-R-41, T-RPT-01 rule 1,
T-RPT-02; SCREENS_B §0.5 RV-01 to RV-14, RPT-R-01 to RPT-R-06; 03 REQ-RPT-002, REQ-RPT-024,
REQ-RPT-027, REQ-SEC-011, REQ-PLT-019; 05 §5.6 ``REPORT_RUN``; CTL-029).

``create_run`` serves ``POST /report-runs``: the current definition (or ``report_version``), an
output format of the definition, ``report.export`` for a file format (RV-06), the parameters against
the closed ``parameters_schema`` (unknown keys, types, formats, start after end; T-RPT-01 rule 1,
REQ-RPT-012), entity codes within the caller's ``report.run`` scope, a lock of the workspace and a
``known_at`` not later than now. Entities of more than one fiscal calendar are refused a period
named by key — and any run of a definition whose columns are period keys — here and at the rerun
(T-RPT-01 rule 6; PRD ERR-97; ``_calendar_errors``). The run stores every parameter including
the defaults
(``entity_codes``: every entity in scope; ``known_at``: now; flags: false unless
``PARAMETER_DEFAULTS`` names another default, D-87 L6-3-Q-29; a parameter of
``SETTING_DEFAULTS``: the registry setting in force at the run's ``known_at``), its resolved
``entity_ids``, the engine release, a number of series ``REPORT_RUN`` and its ``REPORT_RUN`` job.

``run_report`` is the job handler: QUEUED → RUNNING, the definition's builder of ``BUILDERS``, the
output of the run's format stored as a ``REPORT_OUTPUT`` file, the CSV manifest, ``row_count``,
``control_totals``, ``tie_out_results``, ``ledger_heads`` (book → ``{chain_seq, seal_sha256}``) and
SUCCEEDED in one transaction. A failed attempt leaves the run RUNNING for the retry (05 §5.6: 2
attempts); after the last attempt the job's failure hook ends the run FAILED with the job's problem
(RV-14). A rerun is a new run with identical parameters; its job result adds
``output_sha256_equal`` and ``control_totals_equal`` against the run it repeats (REQ-RPT-002).
The SOP-1 CTL-029 fact is derived from that same comparison BEFORE it is recorded
(``ctl029_fact``; D-98 candidate 100): a first run PASSes with its reproducibility stamp; a rerun
PASSes when hash and totals both equal the original's, FAILs with one exception on a hash-only or
totals-only mismatch — the run and the job stay SUCCEEDED, the mismatch is a control exception —
and is NOT_APPLICABLE (``ORIGINAL_WITHOUT_OUTPUT``) when the original has no output to compare.

Reads: a run is visible when each of its entities is in the caller's scope of the permission
its report is run under (``run_permission``: ``report.run``, or ``audit.read`` for the three
access registers) and, for an output, also in the caller's scope of ``report.export``.
``GET /report-runs/{id}/output`` streams the file and appends one ``report.export`` audit event
with the run id (REQ-PLT-019).

Permissions by report (04 API-R-41 rev 1.128; supervisor rulings R-13, R-28, R-63 (a)): a report
run must not reveal data whose own API route the caller's permissions refuse, and a register that
holds no accounting data is not tied to ``report.run``. ``RUN_PERMISSIONS`` names the reports run
and read under another permission than ``report.run`` — the user access listing, the SoD conflict
report and the API client inventory answer to ``audit.read``, so a Tenant Admin runs them and a
holder of ``report.run`` alone does not. ``REQUIRED_PERMISSIONS`` declares, per report, what it
needs beside its run permission — ``audit.read`` (API-R-10) for the audit log export (for every
entity), the chain verification report, the configuration change register and the approvals
register. Both are enforced in one place, ``require_report``: creating a run, reading it (detail,
data, cell explanation), exporting it and re-running it answer 403 ``forbidden`` after one
``DENIED`` audit event; a run of a report the caller does not hold the run permission for is not
visible at all (404, and no list names it), and ``runs_statement`` leaves out the runs whose
declared permission the caller lacks. ``admitted`` is the test of the routes themselves: a
principal that may run no report is refused before anything is read.

[J] L5-2-Q-11: ``output_sha256`` is the SHA-256 of the output bytes of the unstamped formats
(JSON, CSV). XLSX and PDF outputs print the run number, user and time (RV-07), so their bytes differ
between runs and cannot contain their own hash: their ``output_sha256`` is the SHA-256 of the run's
JSON dataset, printed in the header block, and ``file_object.sha256`` keeps the file's own hash.
[J] L5-2-Q-14: a definition without a builder answers 422 at ``POST /report-runs``; run data is
served for SUCCEEDED JSON runs (04 API-R-41 names no data of file runs).
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, BinaryIO, Final
from uuid import UUID

from erev_engine import ENGINE_VERSION
from sqlalchemy import (
    ColumnElement,
    Select,
    Text,
    Uuid,
    and_,
    cast,
    false,
    func,
    insert,
    literal,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import array as pg_array
from sqlalchemy.orm import Session

from erev_api.audit import writer as audit_writer
from erev_api.auth.dependencies import DENIED_OBJECT_TYPE
from erev_api.controls.evidence import RunRefType, record_execution
from erev_api.controls.release import current_environment, current_release, release_identity
from erev_api.controls.stamping import process_release_id
from erev_api.db import new_id
from erev_api.db.session import every_entity_scope, tenant_session
from erev_api.db.tables import (
    contract,
    engine_release,
    job,
    ledger_chain_head,
    legal_entity,
    obligation_version,
    period,
    period_lock,
    report_definition,
    report_run,
    schedule_line,
    subledger_line,
)
from erev_api.db.transitions import apply
from erev_api.domain.platform import approval_queries
from erev_api.domain.platform.jobs import job_outs
from erev_api.domain.reports import catalogue, locked, tie_outs
from erev_api.domain.reports.builders import (
    ADAPTER,
    OPEN,
    RETAINED,
    Builder,
    ReportParams,
    SourceBinding,
    SourceCollector,
    filter_problem,
)
from erev_api.domain.reports.builders import adoption_bridge as adoption_bridge_builder
from erev_api.domain.reports.builders import (
    allocations_by_ssp_version as allocations_by_ssp_version_builder,
)
from erev_api.domain.reports.builders import api_client_inventory as api_client_inventory_builder
from erev_api.domain.reports.builders import approvals_register as approvals_register_builder
from erev_api.domain.reports.builders import audit_log_export as audit_log_export_builder
from erev_api.domain.reports.builders import book_bridge as book_bridge_builder
from erev_api.domain.reports.builders import (
    chain_verification_report as chain_verification_report_builder,
)
from erev_api.domain.reports.builders import (
    config_change_register as config_change_register_builder,
)
from erev_api.domain.reports.builders import (
    contract_balance_rollforward as contract_balance_rollforward_builder,
)
from erev_api.domain.reports.builders import contract_balances as contract_balances_builder
from erev_api.domain.reports.builders import (
    contract_cost_rollforward as contract_cost_rollforward_builder,
)
from erev_api.domain.reports.builders import contract_history as contract_history_builder
from erev_api.domain.reports.builders import disaggregation as disaggregation_builder
from erev_api.domain.reports.builders import (
    estimate_change_listing as estimate_change_listing_builder,
)
from erev_api.domain.reports.builders import intercompany_pairs as intercompany_pairs_builder
from erev_api.domain.reports.builders import je_population as je_population_builder
from erev_api.domain.reports.builders import judgement_register as judgement_register_builder
from erev_api.domain.reports.builders import late_entry_report as late_entry_report_builder
from erev_api.domain.reports.builders import (
    latest_contract_status as latest_contract_status_builder,
)
from erev_api.domain.reports.builders import (
    legacy_contract_history_export as legacy_contract_history_export_builder,
)
from erev_api.domain.reports.builders import legacy_je_summary as legacy_je_summary_builder
from erev_api.domain.reports.builders import (
    legacy_latest_contract_export as legacy_latest_contract_export_builder,
)
from erev_api.domain.reports.builders import (
    manual_adjustment_register as manual_adjustment_register_builder,
)
from erev_api.domain.reports.builders import (
    migration_reconciliation as migration_reconciliation_builder,
)
from erev_api.domain.reports.builders import modification_register as modification_register_builder
from erev_api.domain.reports.builders import (
    out_of_period_register as out_of_period_register_builder,
)
from erev_api.domain.reports.builders import (
    revenue_from_opening_liability as revenue_from_opening_liability_builder,
)
from erev_api.domain.reports.builders import (
    revenue_from_prior_period_obligations as revenue_from_prior_period_obligations_builder,
)
from erev_api.domain.reports.builders import revenue_waterfall as revenue_waterfall_builder
from erev_api.domain.reports.builders import rpo as rpo_builder
from erev_api.domain.reports.builders import rpo_rollforward as rpo_rollforward_builder
from erev_api.domain.reports.builders import (
    scope_exclusion_register as scope_exclusion_register_builder,
)
from erev_api.domain.reports.builders import sod_conflict_report as sod_conflict_report_builder
from erev_api.domain.reports.builders import ssp_change_log as ssp_change_log_builder
from erev_api.domain.reports.builders import ssp_override_listing as ssp_override_listing_builder
from erev_api.domain.reports.builders import ssp_version_diff as ssp_version_diff_builder
from erev_api.domain.reports.builders import user_access_listing as user_access_listing_builder
from erev_api.domain.reports.outputs import ReportData, RunStamp, display_timestamp, utc_text
from erev_api.domain.reports.outputs import csv as csv_output
from erev_api.domain.reports.outputs import manifest as manifest_output
from erev_api.domain.reports.outputs import pdf as pdf_output
from erev_api.domain.reports.outputs import xlsx as xlsx_output
from erev_api.enums import ControlResult, FilePurpose, JobKind, RunStatus
from erev_api.files.store import FileStore, open_file, store_file
from erev_api.jobs.context import JobContext
from erev_api.jobs.registry import JobOutcome, RetryPolicy, task
from erev_api.numbering import next_number
from erev_api.problems import Problem, ProblemError
from erev_api.registry.resolve import setting
from erev_api.schemas.common import ActorOut, JobOut, MoneyOut, ProblemOut, RefOut
from erev_api.schemas.explain import (
    ExplainCellContributorOut,
    ExplainCellContributorsOut,
    ExplainCellEntityPartOut,
    ExplainCellOut,
)
from erev_api.schemas.reports import (
    EngineReleaseRefOut,
    IpeLogicOut,
    ReportDefinitionOut,
    ReportOutputOut,
    ReportRefOut,
    ReportRunCreateIn,
    ReportRunOut,
    ReportRunSourcesOut,
    TieOutResultOut,
)

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.auth.principal import Principal, RequestContext
    from erev_api.uow import UnitOfWork

__all__ = [
    "BUILDERS",
    "Builder",
    "ReportData",
    "ReportParams",
    "create_run",
    "rerun",
    "run_report",
]

RUN_PERMISSION: Final = "report.run"
EXPORT_PERMISSION: Final = "report.export"
TABLE: Final = "report_run"
OBJECT_TYPE: Final = "report_run"
SERIES: Final = "REPORT_RUN"
ACTION_CREATE: Final = "report_run.create"
ACTION_START: Final = "report_run.start"
ACTION_SUCCEED: Final = "report_run.succeed"
ACTION_FAIL: Final = "report_run.fail"
ACTION_EXPORT: Final = "report.export"
RUN_HREF: Final = "/api/v1/report-runs/{run_id}"
OUTPUT_HREF: Final = "/api/v1/report-runs/{run_id}/output"
MANIFEST_HREF: Final = "/api/v1/report-runs/{run_id}/output?part=manifest"
JSON_FORMAT: Final = "JSON"
NEGATIVE_NUMBER_STYLE: Final = "ui.negative_number_style"
REPORT_RUN_RETRY: Final = RetryPolicy(max_attempts=2)  # 05 §5.6 execution profile
QUEUED: Final = RunStatus.QUEUED.value
RUNNING: Final = RunStatus.RUNNING.value
SUCCEEDED: Final = RunStatus.SUCCEEDED.value
FAILED: Final = RunStatus.FAILED.value
ENTITY_CODES: Final = catalogue.ENTITY_SCOPE_KEY
KNOWN_AT: Final = catalogue.KNOWN_AT_KEY
KNOWN_AT_BASIS: Final = catalogue.KNOWN_AT_BASIS_KEY
HISTORICAL_BASIS: Final = catalogue.HISTORICAL_BASIS
RECORD_BASIS: Final = catalogue.RECORD_BASIS
BASIS_NEEDS_KNOWN_AT: Final = "known_at_basis 'historical' needs a known_at to hold."
PART_OUTPUT: Final = "output"
PART_MANIFEST: Final = "manifest"

# Rule ids of the parameter findings.
RULE_PARAMETERS: Final = "T-RPT-01"
RULE_START_END: Final = "REQ-RPT-012"
RULE_FORMATS: Final = "RPT-R-05"
RULE_SCOPE: Final = "REQ-PLT-012"
RULE_REPORT: Final = "API-R-41"
# 04 T-RPT-01 rule 6 (rev 1.264; PRD ERR-97): entities of more than one fiscal calendar.
RULE_CALENDARS: Final = "CALENDARS_DIFFER"
# [J] L5-2-Q-10: copy the documents leave open; SCREENS_B RV-08 and RPT-11 give the range copy.
UNKNOWN_REPORT: Final = "Choose a report of the standard catalogue."
UNKNOWN_VERSION: Final = "Choose a version of this report."
FORMAT_NOT_OFFERED: Final = "Choose one of this report's formats: {formats}."
NOT_AVAILABLE: Final = "This report is not available yet."
UNKNOWN_PARAMETER: Final = "{key} is not a parameter of this report."
START_PERIOD_AFTER_END: Final = "Start period must be on or before end period."
START_DATE_AFTER_END: Final = "Start date must be on or before end date."
START_AFTER_END: Final = "Start must be on or before end."
ENTITY_UNKNOWN: Final = "Choose entities that exist in this workspace."
LOCK_UNKNOWN: Final = "Choose a period lock of this workspace."
KNOWN_AT_FUTURE: Final = "known_at must not be later than now."
# PRD ERR-97, word for word (the copy-catalogue pin compares the two).
CALENDARS_DIFFER: Final = (
    "The entities of this run keep different fiscal calendars, so a period key can name "
    "different months for them. Run the report for entities of one calendar."
)
# frps3b (04 T-RPT-02 rev 1.55; S15-R-24): a live run without a binding was created before source
# binding; its consumed sources are not recorded and are never reconstructed from today's rows.
RERUN_UNBOUND: Final = (
    "Report run {run_no} was created before source binding: its consumed sources are not "
    "recorded and cannot be rerun from the same source. Run the report current instead."
)
EXPLAIN_UNBOUND: Final = (
    "Cell explanation resolves against a run's bound sources; report run {run_no} was created "
    "before source binding and has none. Run the report current to explain a cell."
)
ROW_NOT_IN_RUN: Final = "The run's saved output holds no row {row_key} (S15-R-24)."
BINDING_INCOMPATIBLE: Final = (
    "Report run {run_no} carries a source binding this release cannot read ({reason}); its saved "
    "output stays as it was. Run the report current instead."
)
# Codex 2154 (4): the lifecycle classes of a run's sources (API-S-ReportRun ``sources.kind``).
KIND_BOUND: Final = "bound"
KIND_RETAINED: Final = RETAINED
KIND_AS_LOCKED: Final = "as_locked"
KIND_PENDING: Final = "pending"
KIND_FAILED: Final = "failed_without_capture"
KIND_LEGACY: Final = "legacy_unbound"
KIND_OPEN: Final = OPEN  # no same-source support: a rerun is a new live evaluation
NOT_FINISHED: Final = "This run has not finished."
DATA_OF_JSON_RUNS: Final = (
    "Run data is available for JSON runs. Download this run's output instead."
)
NO_MANIFEST: Final = "This run has no manifest."
SOURCE_CURRENT: Final = "Current, known at {at}"
SOURCE_LOCKED: Final = "As locked on {at}"

_RANGES: Final = (
    ("from_period_key", "to_period_key", START_PERIOD_AFTER_END),
    ("from_date", "to_date", START_DATE_AFTER_END),
    ("from", "to", START_AFTER_END),
)
_INSTANT: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$"
)
_DATE: Final = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")

BUILDERS: Final[Mapping[str, Builder]] = MappingProxyType(
    {
        api_client_inventory_builder.CODE: api_client_inventory_builder.build,
        revenue_waterfall_builder.CODE: revenue_waterfall_builder.build,
        contract_balances_builder.CODE: contract_balances_builder.build,
        contract_balance_rollforward_builder.CODE: contract_balance_rollforward_builder.build,
        contract_cost_rollforward_builder.CODE: contract_cost_rollforward_builder.build,
        revenue_from_opening_liability_builder.CODE: revenue_from_opening_liability_builder.build,
        revenue_from_prior_period_obligations_builder.CODE: (
            revenue_from_prior_period_obligations_builder.build
        ),
        rpo_builder.CODE: rpo_builder.build,
        rpo_rollforward_builder.CODE: rpo_rollforward_builder.build,
        disaggregation_builder.CODE: disaggregation_builder.build,
        contract_history_builder.CODE: contract_history_builder.build,
        legacy_contract_history_export_builder.CODE: legacy_contract_history_export_builder.build,
        latest_contract_status_builder.CODE: latest_contract_status_builder.build,
        legacy_latest_contract_export_builder.CODE: legacy_latest_contract_export_builder.build,
        legacy_je_summary_builder.CODE: legacy_je_summary_builder.build,
        # D-98 candidate 85: the two E-64 kinds whose producers were absent (lane ENG-C6).
        je_population_builder.CODE: je_population_builder.build,
        out_of_period_register_builder.CODE: out_of_period_register_builder.build,
        # LMG-3 (SCREENS_B RPT-41 "Reader and registration"; lane F-LMG, 2026-09-20).
        migration_reconciliation_builder.CODE: migration_reconciliation_builder.build,
        # CTR-17 slice 1 (D-98 140-A1; ENGINE_SPEC_B S15-R-20c; SCREENS_B RPT-14 rev 1.23; lane
        # F-CTR): the MODIFICATION_REGISTER producer over T-CON-06 (18 → 19).
        modification_register_builder.CODE: modification_register_builder.build,
        # F-CLO (BUILD_SPEC RPS-8 RPT-18; ENGINE_SPEC_B S15-R-20d rev 1.39): the
        # MANUAL_ADJUSTMENT_REGISTER producer over T-SL-05 (19 → 20).
        manual_adjustment_register_builder.CODE: manual_adjustment_register_builder.build,
        # BUILD_SPEC RPS-9 (SCREENS_B §5.6.4 RPT-19 to RPT-22; lane F-RPS-REG): the SSP reports
        # (20 → 24).
        ssp_change_log_builder.CODE: ssp_change_log_builder.build,
        ssp_version_diff_builder.CODE: ssp_version_diff_builder.build,
        allocations_by_ssp_version_builder.CODE: allocations_by_ssp_version_builder.build,
        ssp_override_listing_builder.CODE: ssp_override_listing_builder.build,
        # BUILD_SPEC RPS-10 (SCREENS_B §5.6.5 RPT-23 to RPT-26, RPT-43, RPT-44; lane F-RPS-REG):
        # the access, configuration, approvals and audit registers (24 → 30).
        config_change_register_builder.CODE: config_change_register_builder.build,
        user_access_listing_builder.CODE: user_access_listing_builder.build,
        sod_conflict_report_builder.CODE: sod_conflict_report_builder.build,
        approvals_register_builder.CODE: approvals_register_builder.build,
        audit_log_export_builder.CODE: audit_log_export_builder.build,
        chain_verification_report_builder.CODE: chain_verification_report_builder.build,
        # BUILD_SPEC RPS-11 (SCREENS_B §5.6.2 RPT-28 to RPT-30; lane F-RPS-REG): the judgement,
        # estimate-change and scope-exclusion registers (30 → 33). RPT-31 loss_provision_register
        # stays unregistered: its source T-CON-17 is not persisted before CTR-14.
        judgement_register_builder.CODE: judgement_register_builder.build,
        estimate_change_listing_builder.CODE: estimate_change_listing_builder.build,
        scope_exclusion_register_builder.CODE: scope_exclusion_register_builder.build,
        # BUILD_SPEC RPS-12 (SCREENS_B §5.6.6 RPT-33 to RPT-35; lane F-RPS-REG): the book bridge,
        # the adoption bridge and the intercompany pairs (33 → 36). RPT-36 balance_aging stays
        # unregistered: its interim subledger source holds no JET-06 line before the close run
        # posts the netting reclass (CLO-19) and no T-CON-18 layer before CTR-14 (ruling Q-2).
        book_bridge_builder.CODE: book_bridge_builder.build,
        adoption_bridge_builder.CODE: adoption_bridge_builder.build,
        intercompany_pairs_builder.CODE: intercompany_pairs_builder.build,
        # BUILD_SPEC RPS-8 (SCREENS_B §5.6.3 RPT-17 rev 1.25; lane F-RPS-REG): the late-entry
        # report over T-CON-05 and T-CLS-04 (36 → 37).
        late_entry_report_builder.CODE: late_entry_report_builder.build,
    }
)


@dataclass(frozen=True, slots=True)
class SourceContract:
    """How a registered live builder is source-bound (S15-R-24; Codex 2154 / 2202): its strategy,
    the source dimensions its adapter binds, and the dimensions its contract leaves OPEN — stated
    in the binding of every run it produces (``SourceBinding.open``) and in API-S-ReportRun
    ``sources.open``; never silently narrowed."""

    strategy: str
    bound: tuple[str, ...]
    open: tuple[str, ...] = ()


_VERSIONS: Final = "contract versions (ids per book, at the bound cutoff)"
_CUTOFF: Final = "effective record cutoff (the exact instant the build applied)"
_POLICIES: Final = (
    "policies / elections (resolved at the bound cutoff through the historical resolver)"
)
# frps3c-1: the entity calendar assignment, the period definitions, the entity attributes and the
# default book are retained as configuration EVIDENCE by the live build and read back — never from
# today's rows — by a bound run (Codex 2245 (d) closed; design §2.1 / §10.1).
_CONFIGURATION: Final = (
    "consumed configuration retained as evidence (entities: code / calendar / functional "
    "currency / time zone; the period definitions of each consumed calendar; the default book) "
    "— read back bound, never from today's rows"
)
_CUSTOMERS: Final = (
    "customer association and names as consumed (contract → customer id, customer id → name; "
    "NULL retained as null, an absent key refused by name; no live customer value under a binding)"
)
_SCHEDULE: Final = "schedule lines (children of the bound versions)"
_LINES: Final = (
    "subledger-line membership (the consumed line ids as members; a bound read re-reads "
    "exactly those rows within today's scope and refuses a missing id by name)"
)
# Ruling R-72 (a): the billing that posts no line enters the rollforward's path from the
# contracts' billing events; the engine's billed amount is a node of the bound versions' traces.
_BILLING_EVENTS: Final = (
    "billing-event membership (the billing streams consumed as members.contract_event — "
    "BILLING_RECORDED, CREDIT_MEMO_RECORDED and what voids them; a bound read re-reads exactly "
    "those events and refuses a missing id by name) and the billed_unconditional_cum nodes of "
    "the bound versions' traces"
)
# Codex 2301 (b): the open declarations name each builder's ACTUAL input families (the frps3c
# baseline map) — a rebuild is from those, never from substituted journal lines.
_LEGACY_JE_OPEN: Final = (
    "subledger-line population (GROSS / DELTA applicability; enabled LEGACY books) "
    "read live; frps3c"
)
_OOP_OPEN: Final = (
    "subledger-line population and postings, ordered T-SL-12 event sets, computation / approval "
    "references and whole-group per-book cause proof (missing evidence distinct from a proved "
    "zero) read live; frps3c"
)
_JE_POPULATION_OPEN: Final = (
    "journal population: the independent total side and the history side read live; frps3c"
)
_LEGACY_EXPORT_OPEN: Final = (
    "contract / obligation rows incl. predecessor obligation rows of legacy conversions read live; "
    "frps3c"
)
_MIGRATION_OPEN: Final = (
    "migration reconciliation, profile and exception mappings read live; frps3c"
)
_MODIFICATION_REGISTER_OPEN: Final = (
    "modification rows with their contracts, approvals, judgement numbers, applied events, the "
    "run book's contract / obligation versions and the stored impact previews read live "
    "(CTR-17 slice 1; S15-R-20c)"
)
_MANUAL_ADJUSTMENT_REGISTER_OPEN: Final = (
    "manual adjustment rows (T-SL-05) with their contracts, obligations, posting periods, "
    "approvals and attachment counts read live (F-CLO RPS-8 RPT-18; S15-R-20d)"
)
# BUILD_SPEC RPS-9 to RPS-12 (lane F-RPS-REG): the registers and listings read live; no source
# adapter yet — each names its actual input families.
_SSP_CHANGE_LOG_OPEN: Final = (
    "SSP book versions with their books, entry counts, study attachments and approval requests / "
    "decisions read live (RPS-9 RPT-19)"
)
_SSP_VERSION_DIFF_OPEN: Final = (
    "the entries and ranges of both SSP book versions read live (RPS-9 RPT-20)"
)
_ALLOCATIONS_BY_SSP_VERSION_OPEN: Final = (
    "obligation versions (the allocation lineage) of the run's book with their contract versions, "
    "cause events, contracts and SSP book versions read live (RPS-9 RPT-21)"
)
_SSP_OVERRIDE_LISTING_OPEN: Final = (
    "obligation versions carrying an SSP override with their contracts, SSP book versions and "
    "approval requests / decisions read live (RPS-9 RPT-22)"
)
_CONFIG_CHANGE_REGISTER_OPEN: Final = (
    "decided configuration approval requests with their decisions, subject versions, audit "
    "events (the recorded field diffs) and example cases read live (RPS-10 RPT-23)"
)
_USER_ACCESS_LISTING_OPEN: Final = (
    "memberships with their people, role assignments, roles, granting approval decisions, MFA "
    "factors, entity codes and the audit events of invitations read live (RPS-10 RPT-24)"
)
_SOD_CONFLICT_REPORT_OPEN: Final = (
    "SoD rule versions, role assignments, role permissions, memberships and SoD exceptions read "
    "live (RPS-10 RPT-25)"
)
_APPROVALS_REGISTER_OPEN: Final = (
    "approval requests with their steps, decisions, auto-approval rules, entity codes and "
    "display names read live (RPS-10 RPT-26)"
)
_AUDIT_LOG_EXPORT_OPEN: Final = "audit events of the workspace read live (RPS-10 RPT-43)"
_CHAIN_VERIFICATION_REPORT_OPEN: Final = "audit chain verification rows read live (RPS-10 RPT-44)"
_JUDGEMENT_REGISTER_OPEN: Final = (
    "judgement records with their contracts, subjects and display names read live (RPS-11 RPT-28)"
)
_ESTIMATE_CHANGE_LISTING_OPEN: Final = (
    "approved estimate versions with their elements, contracts, predecessors, approval requests / "
    "decisions, attachments and the catch-up of the contract versions their events caused read "
    "live (RPS-11 RPT-29)"
)
_SCOPE_EXCLUSION_REGISTER_OPEN: Final = (
    "routed-out obligation versions of each group's latest contract version at the period end "
    "with their contract versions and judgement records read live (RPS-11 RPT-30)"
)
_BOOK_BRIDGE_OPEN: Final = (
    "the entity's kept books, the REVENUE subledger lines of both books over the range, the "
    "presented balances of each book's latest contract versions at the range end, the contract "
    "versions' status history and the IFRS 15 impairment-reversal lines read live (RPS-12 RPT-33)"
)
_ADOPTION_BRIDGE_OPEN: Final = (
    "the entity's kept books, the PRE_STANDARD_REVENUE subledger lines of the LEGACY book by "
    "origin period, and the revenue, billed and balance nodes of the latest ASC 606 contract "
    "versions at the period end before the date of initial application read live (RPS-12 RPT-34)"
)
_INTERCOMPANY_PAIRS_OPEN: Final = (
    "the intercompany due-from and due-to subledger lines of the run's entities with their "
    "counterparties, contracts, obligations and periods read live (RPS-12 RPT-35)"
)
_LATE_ENTRY_REPORT_OPEN: Final = (
    "contract events of the run's entities with their contracts, approval requests and "
    "recording principals, and the first lock record of each entity's period read live "
    "(RPS-8 RPT-17)"
)
_OPEN_ONLY: Final = (
    "effective record cutoff (the basis; nothing else is bound — a rerun is a NEW live evaluation, "
    "labelled open, never a reproduction)",
)
SOURCE_CONTRACTS: Final[Mapping[str, SourceContract]] = MappingProxyType(
    {
        rpo_builder.CODE: SourceContract(
            ADAPTER,
            (
                _CUTOFF,
                "contract-version history (every version consumed)",
                _SCHEDULE,
                "labels: customer_segment / customer_name per customer, "
                "product_family / product_name per product",
                _POLICIES,
                _CONFIGURATION,
            ),
        ),
        rpo_rollforward_builder.CODE: SourceContract(
            ADAPTER,
            (
                _CUTOFF,
                "contract-version history (every version consumed)",
                _SCHEDULE,
                "labels: customer_segment / customer_name / product_family / product_name",
                _POLICIES,
                _CONFIGURATION,
            ),
        ),
        revenue_waterfall_builder.CODE: SourceContract(
            ADAPTER,
            (
                _CUTOFF,
                _VERSIONS,
                _SCHEDULE,
                "subledger-line membership (recognized lines consumed; the cell contributors)",
                "journal-run membership of the revenue tie-out",
                "labels: customer_name per customer, product_revenue_category per product",
                _POLICIES,
                _CONFIGURATION,
            ),
        ),
        contract_history_builder.CODE: SourceContract(
            ADAPTER,
            (
                _CUTOFF,
                "contract versions consumed (the history population)",
                "cause events (children of the bound versions)",
                _CONFIGURATION,
            ),
        ),
        contract_balances_builder.CODE: SourceContract(
            ADAPTER,
            (
                _CUTOFF,
                _VERSIONS,
                "contract-version balances (children of the bound versions)",
                _CONFIGURATION,
                _CUSTOMERS,
                _LINES,
            ),
            (),
        ),
        contract_balance_rollforward_builder.CODE: SourceContract(
            ADAPTER,
            (
                _CUTOFF,
                _VERSIONS,
                "contract-version balances at both ends",
                _CONFIGURATION,
                _CUSTOMERS,
                _LINES,
                _BILLING_EVENTS,
            ),
            (),
        ),
        contract_cost_rollforward_builder.CODE: SourceContract(
            ADAPTER,
            (
                _CUTOFF,
                _VERSIONS,
                "cost balances (children of the bound versions)",
                _CONFIGURATION,
                _LINES,
            ),
            (),
        ),
        revenue_from_opening_liability_builder.CODE: SourceContract(
            ADAPTER,
            (
                _CUTOFF,
                _VERSIONS,
                "opening balances (children of the bound versions)",
                _CONFIGURATION,
                _CUSTOMERS,
                _LINES,
            ),
            (),
        ),
        disaggregation_builder.CODE: SourceContract(
            ADAPTER,
            (
                _CUTOFF,
                "journal-run membership of the revenue tie-out",
                _POLICIES,
                _CONFIGURATION,
                _LINES,
                "product grouping labels (product_family / product_revenue_category per "
                "product id) retained as consumed",
            ),
            (),
        ),
        # ENG-C4 (D-98 candidate 85; main after 71d81d51): the eighteenth registered builder — an
        # ADAPTER: its per-(group, period) selection is restricted to / recorded as the consumed
        # versions, its historical membership candidates recorded as members; traces, obligation
        # rows and contract events are children of the bound versions; the sum-node identity
        # checks run on the rebuilt read (Codex 2301 (c): composed at integration, never a count).
        revenue_from_prior_period_obligations_builder.CODE: SourceContract(
            ADAPTER,
            (
                _CUTOFF,
                "contract versions selected per (group, period) — the consumed ids",
                "stored traces, obligation rows and contract events (children of the bound "
                "versions)",
                "combination-group membership as of the bound cutoff (historical identities; the "
                "candidate contract ids recorded and re-applied)",
                "sum-node identity checks re-run on the rebuilt read (S15-R-13)",
                _CONFIGURATION,
            ),
            (
                "subledger-line REFERENCE population (read live by recorded_at <= known_at; the "
                "bound version ids fix the selection; frps3c)",
            ),
        ),
        # Codex 2202 / 2225: no contract version binds the inventory; its live build records the
        # consumed client rows — each with the grant of its scopes (ruling R-38 (iii)) — entity
        # codes and display names as evidence, and a bound run REBUILDS from that evidence
        # through the same logic — never a replay of saved output.
        api_client_inventory_builder.CODE: SourceContract(
            RETAINED,
            (
                _CUTOFF,
                "api-client membership consumed",
                "retained INPUT evidence: the consumed client rows with their grant, entity "
                "codes and display names, fed to the real builder logic on a same-source rebuild",
            ),
        ),
        # No source adapter yet (frps3c): the cutoff is recorded, nothing else is bound; a rerun
        # is a NEW live evaluation labelled `open` — never a reproduction claim (Codex 2202 / 2225).
        legacy_contract_history_export_builder.CODE: SourceContract(
            OPEN, _OPEN_ONLY, (_LEGACY_EXPORT_OPEN,)
        ),
        latest_contract_status_builder.CODE: SourceContract(
            OPEN,
            _OPEN_ONLY,
            ("latest contract-status rows (contract / version / status reads) read live; frps3c",),
        ),
        legacy_latest_contract_export_builder.CODE: SourceContract(
            OPEN, _OPEN_ONLY, (_LEGACY_EXPORT_OPEN,)
        ),
        legacy_je_summary_builder.CODE: SourceContract(OPEN, _OPEN_ONLY, (_LEGACY_JE_OPEN,)),
        migration_reconciliation_builder.CODE: SourceContract(OPEN, _OPEN_ONLY, (_MIGRATION_OPEN,)),
        # ENG-C6 (D-98 candidate 85; main 7bf044a5): the two E-64 producers registered after this
        # slice's design — journal / subledger population readers without a source adapter yet.
        je_population_builder.CODE: SourceContract(OPEN, _OPEN_ONLY, (_JE_POPULATION_OPEN,)),
        out_of_period_register_builder.CODE: SourceContract(OPEN, _OPEN_ONLY, (_OOP_OPEN,)),
        # F-CTR CTR-17 slice 1 (D-98 140-A1): the register reads live; no source adapter yet.
        modification_register_builder.CODE: SourceContract(
            OPEN, _OPEN_ONLY, (_MODIFICATION_REGISTER_OPEN,)
        ),
        # F-CLO RPS-8 RPT-18: the register reads live; no source adapter yet.
        manual_adjustment_register_builder.CODE: SourceContract(
            OPEN, _OPEN_ONLY, (_MANUAL_ADJUSTMENT_REGISTER_OPEN,)
        ),
        # RPS-9 (RPT-19 to RPT-22): the SSP reports read live; no source adapter yet.
        ssp_change_log_builder.CODE: SourceContract(OPEN, _OPEN_ONLY, (_SSP_CHANGE_LOG_OPEN,)),
        ssp_version_diff_builder.CODE: SourceContract(OPEN, _OPEN_ONLY, (_SSP_VERSION_DIFF_OPEN,)),
        allocations_by_ssp_version_builder.CODE: SourceContract(
            OPEN, _OPEN_ONLY, (_ALLOCATIONS_BY_SSP_VERSION_OPEN,)
        ),
        ssp_override_listing_builder.CODE: SourceContract(
            OPEN, _OPEN_ONLY, (_SSP_OVERRIDE_LISTING_OPEN,)
        ),
        # RPS-10 (RPT-23 to RPT-26, RPT-43, RPT-44): the registers read live; no source adapter yet.
        config_change_register_builder.CODE: SourceContract(
            OPEN, _OPEN_ONLY, (_CONFIG_CHANGE_REGISTER_OPEN,)
        ),
        user_access_listing_builder.CODE: SourceContract(
            OPEN, _OPEN_ONLY, (_USER_ACCESS_LISTING_OPEN,)
        ),
        sod_conflict_report_builder.CODE: SourceContract(
            OPEN, _OPEN_ONLY, (_SOD_CONFLICT_REPORT_OPEN,)
        ),
        approvals_register_builder.CODE: SourceContract(
            OPEN, _OPEN_ONLY, (_APPROVALS_REGISTER_OPEN,)
        ),
        audit_log_export_builder.CODE: SourceContract(OPEN, _OPEN_ONLY, (_AUDIT_LOG_EXPORT_OPEN,)),
        chain_verification_report_builder.CODE: SourceContract(
            OPEN, _OPEN_ONLY, (_CHAIN_VERIFICATION_REPORT_OPEN,)
        ),
        # RPS-11 (RPT-28 to RPT-30): the registers read live; no source adapter yet.
        judgement_register_builder.CODE: SourceContract(
            OPEN, _OPEN_ONLY, (_JUDGEMENT_REGISTER_OPEN,)
        ),
        estimate_change_listing_builder.CODE: SourceContract(
            OPEN, _OPEN_ONLY, (_ESTIMATE_CHANGE_LISTING_OPEN,)
        ),
        scope_exclusion_register_builder.CODE: SourceContract(
            OPEN, _OPEN_ONLY, (_SCOPE_EXCLUSION_REGISTER_OPEN,)
        ),
        # RPS-12 (RPT-33 to RPT-35): the analysis reports read live; no source adapter yet.
        book_bridge_builder.CODE: SourceContract(OPEN, _OPEN_ONLY, (_BOOK_BRIDGE_OPEN,)),
        adoption_bridge_builder.CODE: SourceContract(OPEN, _OPEN_ONLY, (_ADOPTION_BRIDGE_OPEN,)),
        intercompany_pairs_builder.CODE: SourceContract(
            OPEN, _OPEN_ONLY, (_INTERCOMPANY_PAIRS_OPEN,)
        ),
        late_entry_report_builder.CODE: SourceContract(
            OPEN, _OPEN_ONLY, (_LATE_ENTRY_REPORT_OPEN,)
        ),
    }
)
assert set(SOURCE_CONTRACTS) == set(BUILDERS), (
    "every registered live builder states its source contract"
)


# D-87 L6-3-Q-29: a run stores every parameter including its defaults. A flag is false unless the
# report specification names another default here (SCREENS_B RPT-08 ``include_timing`` true;
# RPT-13 ``mode`` GROSS).
PARAMETER_DEFAULTS: Final[Mapping[str, Mapping[str, Any]]] = MappingProxyType(
    {
        disaggregation_builder.CODE: MappingProxyType({"include_timing": True}),
        # SCREENS_B RPT-32 "Currency view: default functional" (D-98 85 / 97; RPS-12).
        contract_cost_rollforward_builder.CODE: MappingProxyType({"currency_view": "functional"}),
        legacy_je_summary_builder.CODE: MappingProxyType({"mode": "GROSS"}),
        # SCREENS_B RPT-14: status default "Applied", "Approved"; rev 1.23 the transaction view is
        # the served currency view (CTR-17 slice 1; D-98 140-A1).
        modification_register_builder.CODE: MappingProxyType(
            {"status": ["APPLIED", "APPROVED"], "currency_view": "transaction"}
        ),
        # SCREENS_B RPT-18 "Currency view: default functional" (F-CLO; S15-R-20d).
        manual_adjustment_register_builder.CODE: MappingProxyType({"currency_view": "functional"}),
        # SCREENS_B RPT-20 "Only changed entries: default true" (RPS-9).
        ssp_version_diff_builder.CODE: MappingProxyType(
            {"only_changes": ssp_version_diff_builder.ONLY_CHANGES_DEFAULT}
        ),
        # SCREENS_B RPT-26 "Currency view: yes (functional amounts of requests)" (RPS-10).
        approvals_register_builder.CODE: MappingProxyType(
            {"currency_view": approvals_register_builder.DEFAULT_CURRENCY_VIEW}
        ),
        # SCREENS_B RPT-29, RPT-30 "Currency view: yes": the transaction view is served (RPS-11).
        estimate_change_listing_builder.CODE: MappingProxyType(
            {"currency_view": estimate_change_listing_builder.DEFAULT_CURRENCY_VIEW}
        ),
        scope_exclusion_register_builder.CODE: MappingProxyType(
            {"currency_view": scope_exclusion_register_builder.DEFAULT_CURRENCY_VIEW}
        ),
        # SCREENS_B RPT-33 "Currency view: default functional"; RPT-35 "default transaction"
        # (RPS-12).
        book_bridge_builder.CODE: MappingProxyType(
            {"currency_view": book_bridge_builder.DEFAULT_CURRENCY_VIEW}
        ),
        intercompany_pairs_builder.CODE: MappingProxyType(
            {"currency_view": intercompany_pairs_builder.DEFAULT_CURRENCY_VIEW}
        ),
    }
)


# A parameter whose default is a registry setting (T-PLT-31): resolved at the run's ``known_at``
# when the caller leaves it out and stored with the run like every other default (D-87
# L6-3-Q-29). SCREENS_B RPT-17 ``window_days``: ``close.late_entry_window_days``.
SETTING_DEFAULTS: Final[Mapping[str, Mapping[str, str]]] = MappingProxyType(
    {
        late_entry_report_builder.CODE: MappingProxyType(
            {late_entry_report_builder.WINDOW_DAYS: late_entry_report_builder.WINDOW_SETTING}
        ),
    }
)
# The SCREENS_B validation copy of an integer parameter, answered for any value its schema
# refuses (RPT-17 ``window_days``).
INTEGER_COPY: Final[Mapping[str, str]] = MappingProxyType(
    {late_entry_report_builder.WINDOW_DAYS: late_entry_report_builder.WINDOW_COPY}
)
# 04 T-RPT-01 rule 6: the definitions whose columns are period keys — a builder that names them
# with its ``PERIOD_PREFIX`` (the waterfall, the disaggregation). Over entities of more than one
# calendar a run of theirs states one series of period keys per calendar, side by side, whether
# or not its parameters name a key. Read from the builders, so that a definition registered with
# period columns is in the set.
PERIOD_KEY_COLUMNS: Final = frozenset(
    code
    for code, builder in BUILDERS.items()
    if hasattr(sys.modules[builder.__module__], "PERIOD_PREFIX")
)


@dataclass(frozen=True, slots=True)
class RequiredPermission:
    """A permission a report needs — its run permission, or one it declares beside it (04
    API-R-41 rev 1.99; ruling R-13).
    ``all_entities``: it must be held for every entity — the report's rows carry no entity
    attribution and may hold entity financial data, so a holder restricted to named entities is
    refused rather than shown a filtered-looking register (ruling R-28; REQ-PLT-012)."""

    code: str
    all_entities: bool = False

    def held_by(self, principal: Principal) -> bool:
        scope = principal.permission_scopes.get(self.code)
        if self.code not in principal.permissions or scope is None:
            return False
        return scope == "*" or not self.all_entities


AUDIT_READ: Final = "audit.read"  # 04 API-R-10: the audit log and the chain verifications
# Ruling R-63 (a): the permission a report is run, read and listed under where it is not
# ``report.run``. The three access registers hold no accounting data, and ``audit.read`` already
# opens the audit log, which carries every grant: a Tenant Admin and an Auditor run them (PRD
# J-22.8, J-17.6); a viewer and the two SSP roles do not.
RUN_PERMISSIONS: Final[Mapping[str, str]] = MappingProxyType(
    {
        user_access_listing_builder.CODE: AUDIT_READ,  # RPT-24
        sod_conflict_report_builder.CODE: AUDIT_READ,  # RPT-25
        api_client_inventory_builder.CODE: AUDIT_READ,  # RPT-27
    }
)
# The permissions one of which opens the routes of API-R-41: ``report.run`` first.
ADMITTING_PERMISSIONS: Final = (RUN_PERMISSION, *sorted(set(RUN_PERMISSIONS.values())))
# Ruling R-13: a report run must not reveal data whose own API route the caller's permissions
# refuse. The report's code names every permission it needs beside its run permission (and
# ``report.export`` for a file); ``require_report`` and ``runs_statement`` are the only readers.
REQUIRED_PERMISSIONS: Final[Mapping[str, tuple[RequiredPermission, ...]]] = MappingProxyType(
    {
        # RPT-43: every T-PLT-19 column of the audit events, which name no entity (R-28)
        audit_log_export_builder.CODE: (RequiredPermission(AUDIT_READ, all_entities=True),),
        # RPT-44: the chain verifications — counts and chain values, no entity data, so at
        # any scope, where RPT-43 states the events themselves and asks for all entities (the
        # supervisor's ruling of 2026-10-01 on item SCOPE-WORKSPACE-LISTS-1)
        chain_verification_report_builder.CODE: (RequiredPermission(AUDIT_READ),),
        # RPT-23 (R-63 (a)): the field changes of every configuration version, from audit events
        config_change_register_builder.CODE: (RequiredPermission(AUDIT_READ),),
        # RPT-26 (R-63 (a)): every request with its decisions, comments and amounts
        approvals_register_builder.CODE: (RequiredPermission(AUDIT_READ),),
    }
)
assert set(REQUIRED_PERMISSIONS) <= set(BUILDERS), "a declared report is a registered report"
assert set(RUN_PERMISSIONS) <= set(BUILDERS), "a report with its own run permission is registered"
type CellExplainer = Callable[
    [Session, ReportParams, str, str], tuple[Mapping[str, str], list[dict[str, Any]]]
]
# API-R-49 ``GET /explain/report-runs/{id}/cell``: the reports whose cells name contributors.
CELL_EXPLAINERS: Final[Mapping[str, CellExplainer]] = MappingProxyType(
    {
        revenue_waterfall_builder.CODE: revenue_waterfall_builder.cell,
        rpo_builder.CODE: rpo_builder.cell,
    }
)
NO_CELL_EXPLAINER: Final = "The cells of this report name no contributors."


@dataclass(frozen=True, slots=True)
class _Rendered:
    content: bytes
    sha256: str
    media_type: str
    extension: str
    manifest: bytes | None = None


@dataclass(frozen=True, slots=True)
class Download:
    """A run output: the plaintext stream, its media type and the attachment file name."""

    stream: BinaryIO
    media_type: str
    file_name: str


# --- definitions -------------------------------------------------------------------------------

_ORDER: Final[Mapping[str, int]] = MappingProxyType(
    {definition.code: index for index, definition in enumerate(catalogue.DEFINITIONS)}
)


def definition_rows(session: Session) -> list[Mapping[str, Any]]:
    """The current definitions in catalogue order (04 T-RPT-01 seeded list)."""
    rows = session.execute(
        select(report_definition).where(report_definition.c.is_current)
    ).mappings()
    return sorted(
        (MappingProxyType(dict(row)) for row in rows),
        key=lambda row: (_ORDER.get(str(row["code"]), len(_ORDER)), str(row["code"])),
    )


def definition_row(
    session: Session, code: str, version: int | None = None
) -> Mapping[str, Any] | None:
    statement = select(report_definition).where(report_definition.c.code == code)
    statement = statement.where(
        report_definition.c.is_current
        if version is None
        else report_definition.c.version == version
    )
    row = session.execute(statement).mappings().one_or_none()
    return None if row is None else MappingProxyType(dict(row))


def definition_listed(principal: Principal, code: str) -> bool:
    """Whether the catalogue names ``code`` to ``principal`` (04 API-R-41): a holder of
    ``report.run`` reads every definition — catalogue text, never rows (rev 1.99); a caller
    without it reads the definitions of the reports it holds the run permission for (ruling
    R-63 (a): the three access registers for a Tenant Admin)."""
    held = principal.permissions
    return RUN_PERMISSION in held or run_permission(code) in held


def definition_out(row: Mapping[str, Any], principal: Principal) -> ReportDefinitionOut:
    """API-S-ReportDefinition; ``ipe_logic`` only with ``report.export`` (REQ-RPT-027)."""
    values: dict[str, Any] = {
        "code": row["code"],
        "version": row["version"],
        "name": row["name"],
        "kind": row["kind"],
        "description": row["description"],
        "parameters_schema": dict(row["parameters_schema"]),
        "output_formats": list(row["output_formats"]),
        "tie_outs": list(row["tie_outs"]),
    }
    if EXPORT_PERMISSION in principal.permissions:
        values["ipe_logic"] = IpeLogicOut.model_validate(row["ipe_logic"])
    return ReportDefinitionOut(**values)


def get_definition(session: Session, principal: Principal, code: str) -> ReportDefinitionOut:
    row = definition_row(session, code)
    if row is None or not definition_listed(principal, str(row["code"])):
        raise Problem("not-found")  # a definition outside the caller's catalogue is not named
    return definition_out(row, principal)


# --- parameters --------------------------------------------------------------------------------


def _finding(field: str, message: str, rule_id: str = RULE_PARAMETERS) -> ProblemError:
    return ProblemError(field=field, rule_id=rule_id, message=message)


def _invalid(errors: Sequence[ProblemError]) -> Problem:
    """422 ``validation-failed`` with the findings. The refusal of PRD ERR-97 is the ``detail`` as
    well: the run record prints the detail of a refused rerun, and no screen has a field for the
    entity scope to read the message on."""
    named = next((error.message for error in errors if error.rule_id == RULE_CALENDARS), None)
    counted = (
        "1 field needs attention." if len(errors) == 1 else f"{len(errors)} fields need attention."
    )
    return Problem("validation-failed", named or counted, errors=list(errors))


def parse_instant(value: Any) -> datetime | None:
    """An RFC 3339 timestamp with a zone, else None."""
    if not isinstance(value, str) or not _INSTANT.fullmatch(value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _is_uuid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def schema_message(key: str, schema: Mapping[str, Any], value: Any) -> str | None:
    """The first violation of ``value`` against the JSON Schema subset of the catalogue, or None
    (``type``, ``enum``, ``pattern``, ``format`` uuid, date and date-time, ``minLength``,
    ``items``, ``minItems``, ``maxItems``, ``uniqueItems``, ``minimum``, ``maximum`` and
    ``additionalProperties``)."""
    kind = schema.get("type")
    if kind == "boolean":
        return None if isinstance(value, bool) else f"{key} must be true or false."
    if kind == "integer":
        copy = INTEGER_COPY.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            return copy or f"{key} must be a whole number."
        if "minimum" in schema and value < schema["minimum"]:
            return copy or f"{key} must be at least {schema['minimum']}."
        if "maximum" in schema and value > schema["maximum"]:
            return copy or f"{key} must be at most {schema['maximum']}."
        return None
    if kind == "array":
        if not isinstance(value, list):
            return f"{key} must be a list."
        if len(value) < schema.get("minItems", 0):
            return f"{key} needs at least {schema['minItems']} values."
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            return f"{key} takes at most {schema['maxItems']} values."
        if schema.get("uniqueItems") and len(
            {json.dumps(item, sort_keys=True) for item in value}
        ) != len(value):
            return f"{key} lists a value twice."
        items = schema.get("items")
        if isinstance(items, Mapping):
            for item in value:
                message = schema_message(key, items, item)
                if message is not None:
                    return message
        return None
    if kind == "object":
        if not isinstance(value, dict) or not all(isinstance(name, str) for name in value):
            return f"{key} must be an object."
        extra = schema.get("additionalProperties", True)
        for name, item in value.items():
            if extra is False:
                return f"{key}.{name} is not accepted."
            if isinstance(extra, Mapping):
                message = schema_message(f"{key}.{name}", extra, item)
                if message is not None:
                    return message
        return None
    if kind == "string":
        return _string_message(key, schema, value)
    return None


def _string_message(key: str, schema: Mapping[str, Any], value: Any) -> str | None:
    if not isinstance(value, str):
        return f"{key} must be text."
    if "enum" in schema and value not in schema["enum"]:
        return f"{key} must be one of {', '.join(str(item) for item in schema['enum'])}."
    if len(value) < schema.get("minLength", 0):
        return f"{key} must not be empty."
    pattern = schema.get("pattern")
    if pattern is not None and not re.search(str(pattern), value):
        if key.endswith("period_key"):
            return f"{key} must be a period key such as FY2026-P09."
        return f"{key} is not in the expected form."
    match schema.get("format"):
        case "uuid" if not _is_uuid(value):
            return f"{key} must be an id."
        case "date" if _parse_date(value) is None:
            return f"{key} must be a date YYYY-MM-DD."
        case "date-time" if parse_instant(value) is None:
            return f"{key} must be a timestamp such as 2026-09-30T23:59:59Z."
    return None


def parameter_errors(
    schema: Mapping[str, Any], parameters: Mapping[str, Any]
) -> list[ProblemError]:
    """Findings of ``parameters`` under a closed ``parameters_schema``: unknown keys, schema
    violations and a start after its end (T-RPT-01 rule 1; REQ-RPT-012)."""
    properties: Mapping[str, Any] = schema.get("properties", {})
    errors: list[ProblemError] = []
    for key in sorted(parameters):
        field = f"parameters.{key}"
        if key not in properties:
            errors.append(_finding(field, UNKNOWN_PARAMETER.format(key=key)))
            continue
        message = schema_message(key, properties[key], parameters[key])
        if message is not None:
            errors.append(_finding(field, message))
    if errors:
        return errors
    for start, end, copy in _RANGES:
        low, high = parameters.get(start), parameters.get(end)
        if low is None or high is None:
            continue
        if start == "from":
            low, high = parse_instant(low), parse_instant(high)
        if low is not None and high is not None and low > high:
            errors.append(_finding(f"parameters.{start}", copy, RULE_START_END))
    return errors


@dataclass(frozen=True, slots=True)
class _Resolved:
    parameters: dict[str, Any]
    entity_ids: tuple[UUID, ...]
    known_at: datetime
    book_code: str | None
    as_of_date: date | None
    period_lock_id: UUID | None
    # F-RPS-CUTOFF-R1 (record §43): the run was created with an explicit ``known_at`` — an as-of
    # read whose builders keep that cutoff (READ-1) instead of L6-3-Q-19's record basis.
    historical: bool = False
    # frps3b (S15-R-24): a rerun carries the original's stored binding into the new run.
    source_binding: Mapping[str, Any] | None = None


def _scope_ids(principal: Principal, permission: str) -> frozenset[UUID] | None:
    """The entities of ``permission``; None for every entity."""
    scope = principal.permission_scopes.get(permission)
    return None if scope is None or scope == "*" else frozenset(scope)


def _permissions_of(report_code: str) -> tuple[str, ...]:
    """The permission ``report_code`` is run under and the permissions it declares beside it."""
    return (
        run_permission(report_code),
        *(required.code for required in REQUIRED_PERMISSIONS.get(report_code, ())),
    )


def _in_scope_entities(session: Session, principal: Principal, report_code: str) -> dict[str, UUID]:
    """The entities a run of ``report_code`` may name: those inside the caller's scope of its run
    permission AND of every permission it declares (rulings R-13 and R-28; item
    SCOPE-WORKSPACE-LISTS-1) — a run reveals nothing whose own route the caller's permissions
    refuse, entity by entity. Before, the run permission alone decided: a Viewer of two entities
    who audits one of them ran the approvals register over both."""
    rows = session.execute(select(legal_entity.c.id, legal_entity.c.code)).tuples()
    scopes = [
        scope
        for scope in (_scope_ids(principal, code) for code in _permissions_of(report_code))
        if scope is not None
    ]
    return {
        str(code): UUID(str(entity_id))
        for entity_id, code in rows
        if all(UUID(str(entity_id)) in scope for scope in scopes)
    }


def resolve_basis(
    given: Mapping[str, Any], *, known_at_given: bool
) -> tuple[str, list[ProblemError]]:
    """The read basis of a run from the CALLER-SUPPLIED parameters (F-RPS-CUTOFF-R1; D-98
    candidate 112): a supplied ``known_at_basis`` is honoured — ``historical`` without a
    ``known_at`` is refused (no cutoff to hold); ``record`` with a ``known_at`` is an explicit
    compatibility read and is stored as such — otherwise ``historical`` when the caller supplied
    ``known_at`` and ``record`` when it defaulted to the application clock."""
    supplied = given.get(KNOWN_AT_BASIS)
    if supplied is not None:
        basis = str(supplied)
        if basis == HISTORICAL_BASIS and not known_at_given:
            return basis, [_finding(f"parameters.{KNOWN_AT_BASIS}", BASIS_NEEDS_KNOWN_AT)]
        return basis, []
    return (HISTORICAL_BASIS if known_at_given else RECORD_BASIS), []


def _calendar_errors(
    session: Session, code: str, parameters: Mapping[str, Any], entity_ids: Sequence[UUID]
) -> list[ProblemError]:
    """04 T-RPT-01 rule 6 (rev 1.264; PRD ERR-97; item RPT-PERIOD-KEY-CALENDARS-1): a period key
    belongs to a fiscal calendar, and a builder reads it in each entity's own. A run over entities
    of more than one calendar that names a period by key can state different months under one
    key — measured: the RPO of an April-year entity's December beside a January-year entity's
    September, as one total. A definition of ``PERIOD_KEY_COLUMNS`` states its figures in one
    column per period key, so with no key in its parameters, too, it sets one month into a column
    per calendar. Such a run is refused before it exists; any other run that names no period by
    key reads each entity at its own period holding the run's date and is not."""
    if len(set(entity_ids)) < 2:
        return []
    by_key = any(
        key.endswith("period_key") and value is not None for key, value in parameters.items()
    )
    if not by_key and code not in PERIOD_KEY_COLUMNS:
        return []
    calendars = session.execute(
        select(func.count(func.distinct(legal_entity.c.calendar_id))).where(
            legal_entity.c.id.in_(entity_ids)
        )
    ).scalar_one()
    if calendars < 2:
        return []
    return [_finding(f"parameters.{ENTITY_CODES}", CALENDARS_DIFFER, RULE_CALENDARS)]


def _resolve(
    uow: UnitOfWork, schema: Mapping[str, Any], given: Mapping[str, Any], *, code: str = ""
) -> tuple[_Resolved, list[ProblemError]]:
    session = uow.session
    properties: Mapping[str, Any] = schema.get("properties", {})
    parameters = dict(given)
    errors: list[ProblemError] = []
    defaults = PARAMETER_DEFAULTS.get(code, {})
    for key, spec in properties.items():
        if key in parameters:
            continue
        if key in defaults:
            parameters[key] = defaults[key]
        elif spec.get("type") == "boolean":
            parameters[key] = False
    entities = _in_scope_entities(session, uow.principal, code)
    if ENTITY_CODES in parameters:
        codes = [str(code) for code in parameters[ENTITY_CODES]]
        if any(code not in entities for code in codes):
            errors.append(_finding(f"parameters.{ENTITY_CODES}", ENTITY_UNKNOWN, RULE_SCOPE))
        entity_ids = tuple(entities[code] for code in codes if code in entities)
    elif ENTITY_CODES in properties and entities:
        parameters[ENTITY_CODES] = sorted(entities)
        entity_ids = tuple(entities[code] for code in sorted(entities))
    else:
        entity_ids = ()
    known_at = uow.now
    known_at_given = False
    if KNOWN_AT in parameters:
        parsed = parse_instant(parameters[KNOWN_AT])
        if parsed is not None and parsed > uow.now:
            errors.append(_finding(f"parameters.{KNOWN_AT}", KNOWN_AT_FUTURE))
        known_at = parsed or uow.now
        known_at_given = parsed is not None  # the caller supplied a cutoff (before normalisation)
    if KNOWN_AT in properties:
        parameters[KNOWN_AT] = utc_text(known_at)
    for key, setting_code in SETTING_DEFAULTS.get(code, {}).items():
        if key in properties and key not in parameters:
            parameters[key] = setting(session, setting_code, known_at=known_at)
    # F-RPS-CUTOFF-R1 (D-98 candidate 112): the read basis, from what the caller supplied — never
    # from the normalised parameters or the timestamp value — and stored as a schema key (D-87) so
    # the run, its reruns and the explain route resolve identically.
    basis, basis_errors = resolve_basis(given, known_at_given=known_at_given)
    errors += basis_errors
    if KNOWN_AT_BASIS in properties:
        parameters[KNOWN_AT_BASIS] = basis
    historical = basis == HISTORICAL_BASIS
    lock_id: UUID | None = None
    if parameters.get("period_lock_id") is not None:
        lock_id = UUID(str(parameters["period_lock_id"]))
        scope = locked.lock_scope(session, lock_id)
        kind = locked.snapshot_kind_of(code)
        if scope is None or scope.entity_id not in entities.values():
            errors.append(_finding("parameters.period_lock_id", LOCK_UNKNOWN, RULE_SCOPE))
        elif kind is None:
            # S15-R-19: a report without a lock dataset refuses the lock at creation, by name.
            errors.append(
                _finding(
                    "parameters.period_lock_id", locked.NO_DATASET.format(code=code), locked.RULE
                )
            )
        elif (refused := locked.froze_nothing(session, scope)) is not None:
            # S15-R-19 rev 1.167: a REOPEN or a PERMANENT_LOCK record froze nothing — refused
            # here, naming the LOCK whose datasets stand, never queued to fail on its dataset.
            errors.append(_finding("parameters.period_lock_id", refused, locked.RULE))
        else:
            # CLO8-SCOPE-R1: the run's scope IS the lock's — explicit selectors must equal it,
            # omitted ones are derived, nothing else is admitted; the run persists that scope.
            normalized, lock_errors = locked.reconcile_selectors(
                given, scope, properties, kind=kind
            )
            errors.extend(lock_errors)
            if KNOWN_AT in properties:
                normalized[KNOWN_AT] = parameters[KNOWN_AT]
            if KNOWN_AT_BASIS in properties:
                # F-RPS-CUTOFF-R1 × CLO-8 (record §43 addendum): the stored basis survives the
                # lock normalisation — an admitted key, not a selector; the scope stays the lock's.
                normalized[KNOWN_AT_BASIS] = basis
            parameters = normalized
            entity_ids = (scope.entity_id,)
    errors += _calendar_errors(session, code, parameters, entity_ids)
    as_of = _parse_date(parameters.get("as_of"))
    book = parameters.get("book")
    return (
        _Resolved(
            parameters=parameters,
            entity_ids=tuple(sorted(set(entity_ids))),
            known_at=known_at,
            historical=historical,
            book_code=None if book is None else str(book),
            as_of_date=as_of,
            period_lock_id=lock_id,
        ),
        errors,
    )


# --- commands ----------------------------------------------------------------------------------


def run_permission(report_code: str) -> str:
    """The permission ``report_code`` is run, read and listed under: ``report.run`` unless
    ``RUN_PERMISSIONS`` names another (ruling R-63 (a))."""
    return RUN_PERMISSIONS.get(report_code, RUN_PERMISSION)


def admitted(principal: Principal) -> bool:
    """Whether ``principal`` may run any report: the test of the API-R-41 routes themselves."""
    return any(code in principal.permissions for code in ADMITTING_PERMISSIONS)


def require_admitted(
    ctx: RequestContext, *, method: str, path: str, keyring: KeyRing | None = None
) -> None:
    """The guard of the API-R-41 routes and of the cell route of API-R-49 (ruling R-63 (a)): a
    principal that may run no report — neither ``report.run`` nor another run permission — gets
    403 ``forbidden`` after one ``DENIED`` audit event naming ``report.run`` and the route, as the
    ``require("report.run")`` guard of these routes wrote it (DG-KRN-AUTH-05). Which report an
    admitted principal reaches is ``require_report``'s and the visibility's to decide."""
    if admitted(ctx.principal):
        return
    audit_writer.record_denied(
        ctx,
        action=RUN_PERMISSION,
        object_type=DENIED_OBJECT_TYPE,
        object_id=None,
        permission=RUN_PERMISSION,
        detail={"method": method, "path": path},
        keyring=keyring,
    )
    raise Problem("forbidden")


def missing_permission(principal: Principal, report_code: str) -> RequiredPermission | None:
    """The first permission ``report_code`` needs that ``principal`` does not hold (at the
    declared scope) — its run permission, then what ``REQUIRED_PERMISSIONS`` declares; None when
    it holds them all."""
    needed = (
        RequiredPermission(run_permission(report_code)),
        *REQUIRED_PERMISSIONS.get(report_code, ()),
    )
    for required in needed:
        if not required.held_by(principal):
            return required
    return None


def withheld_reports(principal: Principal) -> tuple[str, ...]:
    """The reports with a declared permission whose runs ``principal`` may not see, in code order
    (04 API-R-41 rev 1.99); the run permission itself is the list's visibility (``_scoped``)."""
    return tuple(
        sorted(
            code for code in REQUIRED_PERMISSIONS if missing_permission(principal, code) is not None
        )
    )


def require_report(
    ctx: RequestContext, report_code: str, *, run_id: UUID | None, keyring: KeyRing | None = None
) -> None:
    """Rulings R-13 and R-63 (a): 403 ``forbidden`` after one ``DENIED`` audit event
    (DG-KRN-AUTH-05) when the caller lacks the run permission of ``report_code`` or a permission
    it declares. ``run_id`` names the run read, exported or re-run; None on creation."""
    required = missing_permission(ctx.principal, report_code)
    if required is None:
        return
    detail: dict[str, Any] = {"report_code": report_code}
    if required.all_entities:
        detail["scope"] = "*"
    audit_writer.record_denied(
        ctx,
        action=required.code,
        object_type=OBJECT_TYPE,
        object_id=run_id,
        permission=required.code,
        detail=detail,
        keyring=keyring,
    )
    raise Problem("forbidden")


def _require_export(uow: UnitOfWork, output_format: str, object_id: UUID | None) -> None:
    """RV-06: a file output needs ``report.export``; the denial is audited (DG-KRN-AUTH-05)."""
    if output_format == JSON_FORMAT or EXPORT_PERMISSION in uow.principal.permissions:
        return
    audit_writer.record_denied(
        uow.ctx,
        action=EXPORT_PERMISSION,
        object_type=OBJECT_TYPE,
        object_id=object_id,
        permission=EXPORT_PERMISSION,
        detail={"output_format": output_format},
        keyring=uow.keyring,
    )
    raise Problem("forbidden")


def _release_id(session: Session) -> UUID:
    """The process's own release row (05 REL-03 consumers, rev 1.15; ``controls.stamping``), else
    503; the latest row of the running engine version is only the dev / test fallback (D-98 60)."""

    def latest_for_version() -> UUID | None:
        found = session.execute(
            select(engine_release.c.id)
            .where(engine_release.c.engine_version == ENGINE_VERSION)
            .order_by(engine_release.c.deployed_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        return None if found is None else UUID(str(found))

    return process_release_id(
        current_release(),
        env=current_environment(),
        engine_version=ENGINE_VERSION,
        latest_for_version=latest_for_version,
    )


def _stamp(uow: UnitOfWork) -> dict[str, Any]:
    principal = uow.principal
    return {
        "created_at": uow.now,
        "created_by": principal.id,
        "created_by_kind": principal.kind.value,
        "updated_at": uow.now,
        "updated_by": principal.id,
        "updated_by_kind": principal.kind.value,
    }


def _job_out(session: Session, job_id: Any) -> JobOut:
    row = session.execute(select(job).where(job.c.id == job_id)).mappings().one()
    (item,) = job_outs(session, [dict(row)])
    return item


def _insert_run(
    uow: UnitOfWork,
    *,
    definition: Mapping[str, Any],
    resolved: _Resolved,
    output_format: str,
    rerun_of: UUID | None,
) -> tuple[UUID, JobOut]:
    session = uow.session
    release_id = _release_id(session)
    run_id = new_id()
    run_no = next_number(uow, SERIES)
    params: dict[str, Any] = {"report_run_id": str(run_id)}
    if rerun_of is not None:
        params["rerun_of"] = str(rerun_of)
    deferred = uow.defer(JobKind.REPORT_RUN, params, subject_type=OBJECT_TYPE, subject_id=run_id)
    values: dict[str, Any] = {
        "report_run_no": run_no,
        "report_code": definition["code"],
        "report_version": definition["version"],
        "status": QUEUED,
        "parameters": resolved.parameters,
        "entity_ids": list(resolved.entity_ids),
        "book_code": resolved.book_code,
        "as_of_date": resolved.as_of_date,
        "known_at": resolved.known_at,
        "period_lock_id": resolved.period_lock_id,
        "engine_release_id": release_id,
        "output_format": output_format,
        "job_id": deferred["id"],
        "source_binding": None
        if resolved.source_binding is None
        else dict(resolved.source_binding),
    }
    session.execute(
        insert(report_run).values(
            tenant_id=uow.principal.tenant_id, id=run_id, **values, **_stamp(uow)
        )
    )
    uow.audit(
        action=ACTION_CREATE,
        object_type=OBJECT_TYPE,
        object_id=run_id,
        after={
            **{key: value for key, value in values.items() if key != "known_at"},
            "known_at": utc_text(resolved.known_at),
        },
        detail={} if rerun_of is None else {"rerun_of": str(rerun_of)},
    )
    return run_id, _job_out(session, deferred["id"])


def create_run(uow: UnitOfWork, body: ReportRunCreateIn) -> tuple[UUID, JobOut]:
    """``POST /report-runs``: the QUEUED run and its job (202 API-S-Job)."""
    session = uow.session
    definition = definition_row(session, body.report_code, body.report_version)
    if definition is None:
        if body.report_version is not None and definition_row(session, body.report_code):
            raise _invalid([_finding("report_version", UNKNOWN_VERSION, RULE_REPORT)])
        raise _invalid([_finding("report_code", UNKNOWN_REPORT, RULE_REPORT)])
    require_report(uow.ctx, str(definition["code"]), run_id=None, keyring=uow.keyring)  # R-13
    formats = [str(value) for value in definition["output_formats"]]
    if body.output_format not in formats:
        message = FORMAT_NOT_OFFERED.format(formats=", ".join(formats))
        raise _invalid([_finding("output_format", message, RULE_FORMATS)])
    _require_export(uow, body.output_format, None)
    schema = definition["parameters_schema"]
    errors = parameter_errors(schema, body.parameters)
    resolved, findings = _resolve(
        uow, schema, body.parameters if not errors else {}, code=str(definition["code"])
    )
    errors += [] if errors else findings
    if errors:
        raise _invalid(errors)
    if str(definition["code"]) not in BUILDERS:
        raise _invalid([_finding("report_code", NOT_AVAILABLE, RULE_REPORT)])
    return _insert_run(
        uow,
        definition=definition,
        resolved=resolved,
        output_format=body.output_format,
        rerun_of=None,
    )


def rerun(uow: UnitOfWork, run_id: UUID) -> tuple[UUID, JobOut]:
    """``POST /report-runs/{id}/rerun``: a new run with the stored parameters, entity scope,
    ``known_at``, lock, definition version and format (REQ-RPT-002)."""
    session = uow.session
    original = run_row(session, uow.principal, run_id, RUN_PERMISSION, lock=True)
    require_report(uow.ctx, str(original["report_code"]), run_id=run_id, keyring=uow.keyring)
    if original["status"] not in (SUCCEEDED, FAILED):
        raise Problem("invalid-transition", NOT_FINISHED)
    _require_export(uow, str(original["output_format"]), run_id)
    definition = definition_row(
        session, str(original["report_code"]), int(original["report_version"])
    )
    if definition is None or str(definition["code"]) not in BUILDERS:
        raise _invalid([_finding("report_code", NOT_AVAILABLE, RULE_REPORT)])
    # S15-R-24: a live run reruns from ITS bound sources — never from today's rows; without a
    # binding it is refused by name. An as-locked run reruns from its frozen dataset (S15-R-19).
    require_bound(original, RERUN_UNBOUND, "invalid-transition")
    if original["period_lock_id"] is not None:
        # S15-R-19 rev 1.167: a run stored before the revision may name a REOPEN or a
        # PERMANENT_LOCK record, which froze nothing; its rerun is refused as its creation is.
        frozen = locked.lock_scope(session, UUID(str(original["period_lock_id"])))
        refused = None if frozen is None else locked.froze_nothing(session, frozen)
        if refused is not None:
            raise _invalid([_finding("parameters.period_lock_id", refused, locked.RULE)])
    # An OPEN-strategy builder has no same-source support: its rerun is a NEW live evaluation
    # (labelled so; the new run captures its own record), never a reproduction claim.
    contract = SOURCE_CONTRACTS[str(original["report_code"])]
    copied = None if contract.strategy == OPEN else original["source_binding"]
    resolved = _Resolved(
        parameters=dict(original["parameters"]),
        entity_ids=tuple(UUID(str(value)) for value in original["entity_ids"]),
        known_at=original["known_at"],
        book_code=original["book_code"],
        as_of_date=original["as_of_date"],
        period_lock_id=original["period_lock_id"],
        source_binding=copied,
    )
    # T-RPT-01 rule 6: a rerun copies its run and resolves nothing, so the rule is asked here as
    # well. An entity's calendar does not change: only a run stored before the rule meets it.
    findings = _calendar_errors(
        session, str(original["report_code"]), resolved.parameters, resolved.entity_ids
    )
    if findings:
        raise _invalid(findings)
    return _insert_run(
        uow,
        definition=definition,
        resolved=resolved,
        output_format=str(original["output_format"]),
        rerun_of=run_id,
    )


# --- the REPORT_RUN job ------------------------------------------------------------------------


def _lock_run(session: Session, run_id: UUID) -> Mapping[str, Any]:
    row = (
        session.execute(select(report_run).where(report_run.c.id == run_id).with_for_update())
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return MappingProxyType(dict(row))


def report_params(run: Mapping[str, Any]) -> ReportParams:
    """The builder parameters of a stored run."""
    parameters = dict(run["parameters"])
    filters = parameters.get("filters")
    return ReportParams(
        report_code=str(run["report_code"]),
        report_version=int(run["report_version"]),
        parameters=MappingProxyType(parameters),
        entity_ids=tuple(UUID(str(value)) for value in run["entity_ids"]),
        known_at=run["known_at"],
        book_code=run["book_code"],
        as_of_date=run["as_of_date"],
        period_lock_id=run["period_lock_id"],
        filters=MappingProxyType(dict(filters) if isinstance(filters, dict) else {}),
        output_format=str(run["output_format"]),
        # F-RPS-CUTOFF-R1: the stored basis decides the version cutoff for run, rerun and explain.
        historical=parameters.get(KNOWN_AT_BASIS) == HISTORICAL_BASIS,
        # frps3b (S15-R-24): a bound run's build, rerun and explanation resolve against its binding.
        binding=SourceBinding.from_stored(run.get("source_binding")),
    )


def run_kind(run: Mapping[str, Any]) -> str:
    """The lifecycle class of a run's sources (Codex 2154 (4); API-S-ReportRun ``sources.kind``):
    ``as_locked`` (its frozen dataset is its source); ``bound`` / ``retained`` (a SUCCEEDED live
    run with a binding, by its builder's strategy); ``pending`` (QUEUED / RUNNING — nothing
    captured yet); ``failed_without_capture`` (FAILED before capture — a rerun is a NEW evaluation,
    never a reproduction); ``legacy_unbound`` (SUCCEEDED before source binding)."""
    if run.get("period_lock_id") is not None:
        return KIND_AS_LOCKED
    status = str(run.get("status"))
    if run.get("source_binding") is not None:
        strategy = run["source_binding"].get("strategy")
        if strategy == RETAINED:
            return KIND_RETAINED
        return KIND_OPEN if strategy == OPEN else KIND_BOUND
    if status in (QUEUED, RUNNING):
        return KIND_PENDING
    if status == FAILED:
        return KIND_FAILED
    return KIND_LEGACY


def require_bound(run: Mapping[str, Any], message: str, slug: str) -> None:
    """S15-R-24: a SUCCEEDED live run without a ``source_binding`` was created before source
    binding — its sources are never reconstructed from today's rows; refuse by name with
    ``message`` as ``slug``. A binding this release cannot read refuses likewise. As-locked runs
    carry no binding by design (S15-R-19); pending and failed runs are governed by the status
    rules (a failed original reruns as a new evaluation)."""
    kind = run_kind(run)
    contract = SOURCE_CONTRACTS.get(str(run.get("report_code")))
    if kind == KIND_LEGACY and (contract is None or contract.strategy != OPEN):
        raise Problem(slug, message.format(run_no=run.get("report_run_no")))
    if kind in (KIND_BOUND, KIND_RETAINED, KIND_OPEN):
        try:
            SourceBinding.from_stored(run["source_binding"])
        except (ValueError, KeyError, TypeError) as exc:
            raise Problem(
                slug, BINDING_INCOMPATIBLE.format(run_no=run.get("report_run_no"), reason=exc)
            ) from exc


def require_original_row(binding: SourceBinding, row_key: str) -> None:
    """S15-R-24: a cell explanation names a row the saved output holds; a row key the original did
    not hold — a row a later label change would create — is refused by name."""
    if row_key not in binding.row_keys:
        raise filter_problem("row_key", ROW_NOT_IN_RUN.format(row_key=row_key))


def sources_out(run: Mapping[str, Any]) -> ReportRunSourcesOut:
    """API-S-ReportRun ``sources`` (04 §16.9 rev 1.55): the binding summarised with its lifecycle
    ``kind``; ``bound: false`` with the kind for an as-locked, pending, failed or legacy run."""
    kind = run_kind(run)
    if kind in (KIND_BOUND, KIND_RETAINED):
        try:
            binding = SourceBinding.from_stored(run["source_binding"])
        except (ValueError, KeyError, TypeError):
            binding = None
        if binding is not None:
            return ReportRunSourcesOut.model_validate(binding.summary())
    contract = SOURCE_CONTRACTS.get(str(run.get("report_code")))
    return ReportRunSourcesOut(
        bound=False,
        kind=kind,
        strategy=None if contract is None else contract.strategy,
        cutoff=None,
        versions=0,
        labels=0,
        members=0,
        rows=0,
        open=[] if contract is None else list(contract.open),
    )


def _source(session: Session, run: Mapping[str, Any]) -> str:
    lock_id = run["period_lock_id"]
    if lock_id is not None:
        locked_at = session.execute(
            select(period_lock.c.created_at).where(period_lock.c.id == lock_id)
        ).scalar_one_or_none()
        if locked_at is not None:
            return SOURCE_LOCKED.format(at=display_timestamp(locked_at))
    return SOURCE_CURRENT.format(at=display_timestamp(run["known_at"]))


def _run_stamp(
    session: Session,
    run: Mapping[str, Any],
    definition: Mapping[str, Any],
    *,
    output_sha256: str,
    style: str,
) -> RunStamp:
    release = session.execute(
        select(engine_release.c.engine_version, engine_release.c.build_sha).where(
            engine_release.c.id == run["engine_release_id"]
        )
    ).one()
    identity = release_identity(release.engine_version, release.build_sha)  # REL-03: never swapped
    names = approval_queries.display_names(session, [run["created_by"]])
    run_by = approval_queries.actor(run["created_by"], str(run["created_by_kind"]), names)
    codes = _entity_codes(session, run["entity_ids"])
    as_of = run["as_of_date"]
    return RunStamp(
        report_code=str(definition["code"]),
        report_name=str(definition["name"]),
        report_version=int(definition["version"]),
        report_run_no=str(run["report_run_no"]),
        parameters=dict(run["parameters"]),
        entity_codes=codes,
        book=run["book_code"],
        as_of=None if as_of is None else as_of.isoformat(),
        source=_source(session, run),
        engine_version=identity[0],
        build_sha=identity[1],
        run_by=str(run_by["display_name"]),
        run_at=run["started_at"] or run["created_at"],
        output_sha256=output_sha256,
        negative_number_style=style,
    )


def _entity_codes(session: Session, entity_ids: Sequence[Any]) -> tuple[str, ...]:
    ids = [UUID(str(value)) for value in entity_ids]
    if not ids:
        return ()
    rows = session.execute(
        select(legal_entity.c.id, legal_entity.c.code).where(legal_entity.c.id.in_(ids))
    ).tuples()
    codes = {UUID(str(entity_id)): str(code) for entity_id, code in rows}
    return tuple(codes.get(entity_id, str(entity_id)) for entity_id in ids)


def _render(
    session: Session,
    run: Mapping[str, Any],
    definition: Mapping[str, Any],
    data: ReportData,
    style: str,
) -> _Rendered:
    report = manifest_output.report_reference(
        str(definition["code"]), str(definition["name"]), int(definition["version"])
    )
    dataset = manifest_output.dataset_bytes(report, run["parameters"], data)
    output_format = str(run["output_format"])
    if output_format == JSON_FORMAT:
        return _Rendered(
            dataset,
            hashlib.sha256(dataset).hexdigest(),
            manifest_output.MEDIA_TYPE,
            manifest_output.EXTENSION,
        )
    if output_format == "CSV":
        content = csv_output.render_csv(data)
        sha256 = hashlib.sha256(content).hexdigest()
        stamp = _run_stamp(session, run, definition, output_sha256=sha256, style=style)
        manifest = manifest_output.manifest_bytes(
            stamp=stamp,
            data=data,
            file_name=_file_name(run, csv_output.EXTENSION),
            media_type=csv_output.MEDIA_TYPE,
            content=content,
        )
        return _Rendered(content, sha256, csv_output.MEDIA_TYPE, csv_output.EXTENSION, manifest)
    sha256 = hashlib.sha256(dataset).hexdigest()
    stamp = _run_stamp(session, run, definition, output_sha256=sha256, style=style)
    if output_format == "XLSX":
        content = xlsx_output.render_xlsx(data, stamp)
        return _Rendered(content, sha256, xlsx_output.MEDIA_TYPE, xlsx_output.EXTENSION)
    if output_format == "PDF":
        content = pdf_output.render_pdf(data, stamp)
        return _Rendered(content, sha256, pdf_output.MEDIA_TYPE, pdf_output.EXTENSION)
    raise Problem("validation-failed", NOT_AVAILABLE)


def _render_locked(
    session: Session,
    run: Mapping[str, Any],
    definition: Mapping[str, Any],
    frozen: locked.LockedDataset,
    data: ReportData,
    style: str,
) -> _Rendered:
    """The outputs of an as-locked run (S15-R-19 rev 1.31; RPS-SNAP A4 13.1): CSV is the frozen
    file rendered through the export formula guard (``locked.export_csv`` by each column's DECLARED
    kind — byte-identical to the frozen file, hash = ``file_sha256``, whenever no text cell begins
    with a trigger; otherwise the served bytes' own hash, the frozen ``file_sha256`` staying the
    dataset's identity) with the RV-02 manifest of the DELIVERED bytes; JSON, XLSX and PDF render
    the frozen rows (text-kind columns) exactly as a live run renders its builder's rows."""
    output_format = str(run["output_format"])
    if output_format == "CSV":
        # A4 13.1 (b) / Codex 1739 §3 (c): the guard follows each column's DECLARED kind, which the
        # registry declares (function-level import: framework <-> snapshots would otherwise cycle).
        from erev_api.domain.reports import snapshots as registry

        kinds = registry.declared_kinds(
            frozen.kind, locked.headers_of(frozen), frozen.control_totals
        )
        content, sha256 = locked.export_csv(frozen, kinds)
        stamp = _run_stamp(session, run, definition, output_sha256=sha256, style=style)
        manifest = manifest_output.manifest_bytes(
            stamp=stamp,
            data=data,
            file_name=_file_name(run, csv_output.EXTENSION),
            media_type=csv_output.MEDIA_TYPE,
            content=content,
        )
        return _Rendered(content, sha256, csv_output.MEDIA_TYPE, csv_output.EXTENSION, manifest)
    return _render(session, run, definition, data, style)


def _file_name(run: Mapping[str, Any], extension: str) -> str:
    return f"{run['report_code']}-{run['report_run_no']}.{extension}"


def _ledger_heads(session: Session) -> dict[str, Any]:
    rows = session.execute(
        select(
            ledger_chain_head.c.book_code,
            ledger_chain_head.c.last_chain_seq,
            ledger_chain_head.c.last_seal_sha256,
        ).order_by(ledger_chain_head.c.book_code)
    ).tuples()
    return {
        str(book): {"chain_seq": int(seq), "seal_sha256": None if seal is None else str(seal)}
        for book, seq, seal in rows
    }


ORIGINAL_WITHOUT_OUTPUT: Final = "ORIGINAL_WITHOUT_OUTPUT"


@dataclass(frozen=True, slots=True)
class Ctl029Fact:
    """The CTL-029 fact of one run (SOP-1 T-PLT-39) and the equality flags its job result carries,
    derived once from the rerun comparison before anything is recorded (D-98 candidate 100)."""

    result: ControlResult
    population_count: int
    exception_count: int
    detail: Mapping[str, Any]
    flags: Mapping[str, bool]  # empty for a first run; both REQ-RPT-002 flags for a rerun


def _output_of(row: Mapping[str, Any]) -> dict[str, Any]:
    totals = row.get("control_totals")
    sha = row.get("output_sha256")
    return {
        "output_sha256": None if sha is None else str(sha),
        "control_totals": None if totals is None else dict(totals),
    }


def ctl029_fact(
    run: Mapping[str, Any], original: Mapping[str, Any] | None, *, rerun_of: UUID | None
) -> Ctl029Fact:
    """REQ-RPT-002 reproducibility as the CTL-029 control fact (pure; D-98 candidate 100).

    ``run`` is the finished run (``output_sha256``, ``control_totals``, ``row_count``);
    ``original`` the run it repeats (``status``, ``output_sha256``, ``control_totals``) when
    ``rerun_of`` names one. First run: PASS, population 1, detail ``first_run`` with the run's hash,
    totals and row count as the reproducibility stamp. Rerun of a SUCCEEDED original with output:
    PASS when hash and totals both equal, else FAIL with one exception; ``detail`` keeps both flags
    and both sides' hash and totals (evidence retained, never overwritten). Rerun of an original
    without output (not SUCCEEDED, or hash / totals null): NOT_APPLICABLE, population 0, reason
    ``ORIGINAL_WITHOUT_OUTPUT``; the flags then read False, as the job result always has."""
    rerun_output = {
        **_output_of(run),
        "row_count": None if run.get("row_count") is None else int(run["row_count"]),
    }
    if rerun_of is None:
        return Ctl029Fact(ControlResult.PASS, 1, 0, {"first_run": True, **rerun_output}, {})
    original_output = _output_of(original or {})
    has_output = (
        original is not None
        and str(original.get("status")) == SUCCEEDED
        and original_output["output_sha256"] is not None
        and original_output["control_totals"] is not None
    )
    flags = {
        "output_sha256_equal": has_output
        and original_output["output_sha256"] == rerun_output["output_sha256"],
        "control_totals_equal": has_output
        and original_output["control_totals"] == rerun_output["control_totals"],
    }
    detail: dict[str, Any] = {"first_run": False, "rerun_of": str(rerun_of), **flags}
    if not has_output:
        detail["reason"] = ORIGINAL_WITHOUT_OUTPUT
        status = None if original is None else original.get("status")
        detail["original"] = {
            "status": None if status is None else str(status),
            **original_output,
        }
        detail["rerun"] = rerun_output
        return Ctl029Fact(ControlResult.NOT_APPLICABLE, 0, 0, detail, flags)
    detail["original"] = original_output
    detail["rerun"] = rerun_output
    if flags["output_sha256_equal"] and flags["control_totals_equal"]:
        return Ctl029Fact(ControlResult.PASS, 1, 0, detail, flags)
    return Ctl029Fact(ControlResult.FAIL, 1, 1, detail, flags)


def _original_of(
    session: Session, params: Mapping[str, Any]
) -> tuple[UUID | None, Mapping[str, Any] | None]:
    """The run a rerun repeats (``params["rerun_of"]``): its status, hash and totals; ``(None,
    None)`` for a first run."""
    if params.get("rerun_of") is None:
        return None, None
    rerun_of = UUID(str(params["rerun_of"]))
    original = (
        session.execute(
            select(
                report_run.c.status, report_run.c.output_sha256, report_run.c.control_totals
            ).where(report_run.c.id == rerun_of)
        )
        .mappings()
        .one()
    )
    return rerun_of, MappingProxyType(dict(original))


def _outcome(run: Mapping[str, Any], params: Mapping[str, Any], fact: Ctl029Fact) -> JobOutcome:
    """The job result; a rerun's equality flags come from the recorded fact, never recomputed."""
    run_id = UUID(str(run["id"]))
    result: dict[str, Any] = {
        "href": RUN_HREF.format(run_id=run_id),
        "counts": {"rows": int(run["row_count"] or 0)},
        "report_run_id": str(run_id),
    }
    if params.get("rerun_of") is not None:
        result["rerun_of"] = str(params["rerun_of"])
        result.update(fact.flags)
    return JobOutcome(state="SUCCEEDED", result=result)


def _store(uow: UnitOfWork, content: bytes, *, name: str, media_type: str) -> UUID:
    row = store_file(
        uow,
        purpose=FilePurpose.REPORT_OUTPUT,
        stream=io.BytesIO(content),
        original_filename=name,
        media_type=media_type,
    )
    return UUID(str(row["id"]))


def run_failed(uow: UnitOfWork, params: Mapping[str, Any], problem: Mapping[str, Any]) -> None:
    """The ``REPORT_RUN`` failure hook: a QUEUED or RUNNING run ends FAILED with the job's problem
    (SCREENS_B RV-14)."""
    if params.get("report_run_id") is None:
        return
    run_id = UUID(str(params["report_run_id"]))
    run = _lock_run(uow.session, run_id)
    if run["status"] not in (QUEUED, RUNNING):
        return
    apply(
        uow.session,
        TABLE,
        run_id,
        to_status=FAILED,
        set_values={"finished_at": uow.now, "problem": dict(problem)},
        expected_status=str(run["status"]),
    )
    uow.audit(
        action=ACTION_FAIL,
        object_type=OBJECT_TYPE,
        object_id=run_id,
        before={"status": run["status"]},
        after={"status": FAILED, "finished_at": utc_text(uow.now)},
        detail={"problem_type": str(problem.get("type")), "status": problem.get("status")},
    )


@task(JobKind.REPORT_RUN, retry=REPORT_RUN_RETRY, on_failure=run_failed)
def run_report(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``REPORT_RUN``: build, render, store and stamp the run named by ``params.report_run_id``."""
    run_id = UUID(str(params["report_run_id"]))
    with jc.unit_of_work() as uow:
        run = _lock_run(uow.session, run_id)
        if run["period_lock_id"] is not None:
            # CLO8-SCOPE-R1 (Codex 1622 residual): reconcile before ANY path, the SUCCEEDED fast
            # path included — an inconsistent as-locked run yields no outcome from the worker.
            locked.assert_run_matches(uow.session, run)
        if run["status"] == SUCCEEDED:
            rerun_of, original = _original_of(uow.session, params)
            return _outcome(run, params, ctl029_fact(run, original, rerun_of=rerun_of))
        if run["status"] == FAILED:
            raise Problem("invalid-transition", NOT_FINISHED)
        if run["status"] == QUEUED:
            apply(
                uow.session,
                TABLE,
                run_id,
                to_status=RUNNING,
                set_values={"started_at": uow.now},
                expected_status=QUEUED,
            )
            uow.audit(
                action=ACTION_START,
                object_type=OBJECT_TYPE,
                object_id=run_id,
                before={"status": QUEUED},
                after={"status": RUNNING, "started_at": utc_text(uow.now)},
                detail={"job_id": str(jc.job_id)},
            )
            uow.commit()
    with jc.unit_of_work() as uow:
        session = uow.session
        run = _lock_run(session, run_id)
        definition = definition_row(session, str(run["report_code"]), int(run["report_version"]))
        builder = BUILDERS.get(str(run["report_code"]))
        if definition is None:
            raise Problem("validation-failed", NOT_AVAILABLE)
        heads = _ledger_heads(session)
        style = str(setting(session, NEGATIVE_NUMBER_STYLE, known_at=uow.now))
        if run["period_lock_id"] is not None:
            # S15-R-19 (rev 1.31; D-98 candidate 96): an as-locked run reads the lock's frozen
            # dataset of the report's kind and no live table; refusals by name, never a live label.
            locked.assert_run_matches(session, run)  # CLO8-SCOPE-R1: the run's scope is the lock's
            frozen = locked.locked_dataset(
                uow, report_code=str(run["report_code"]), lock_id=UUID(str(run["period_lock_id"]))
            )
            data = locked.report_data(frozen)
            jc.heartbeat()
            rendered = _render_locked(session, run, definition, frozen, data, style)
        else:
            if builder is None:
                raise Problem("validation-failed", NOT_AVAILABLE)
            # S15-R-24: a live build consumes bound sources (a rerun) or records what it consumes
            # (an original run) so the framework binds them with the run below. A bound run
            # REBUILDS through the builder (Codex 2225): an adapter reads the bound sources, a
            # retained-inputs builder feeds its retained evidence to the same logic — never a
            # replay of saved output, so a calculation change still shows as a CTL-029 mismatch.
            build_params = report_params(run)
            contract = SOURCE_CONTRACTS[str(run["report_code"])]
            collector = SourceCollector() if build_params.binding is None else None
            data = builder(uow, replace(build_params, sources=collector))
            jc.heartbeat()
            rendered = _render(session, run, definition, data, style)
            if collector is not None:
                if collector.cutoff is None:  # a builder that selects no versions: the basis cutoff
                    collector.record_cutoff(
                        tie_outs.version_cutoff(
                            session, build_params.known_at, historical=build_params.historical
                        )
                    )
                source_binding = collector.binding(
                    row_keys=[str(row["row_key"]) for row in data.rows],
                    strategy=contract.strategy,
                    open=contract.open,
                    report_version=int(run["report_version"]),
                    dataset={"output_sha256": rendered.sha256, "format": str(run["output_format"])},
                ).to_stored()
            else:
                source_binding = dict(run["source_binding"])
        output_file_id = _store(
            uow,
            rendered.content,
            name=_file_name(run, rendered.extension),
            media_type=rendered.media_type,
        )
        manifest_file_id = (
            None
            if rendered.manifest is None
            else _store(
                uow,
                rendered.manifest,
                name=_file_name(run, rendered.extension) + manifest_output.MANIFEST_SUFFIX,
                media_type=manifest_output.MEDIA_TYPE,
            )
        )
        values = {
            "output_file_id": output_file_id,
            "output_sha256": rendered.sha256,
            "manifest_file_id": manifest_file_id,
            "row_count": data.row_count,
            "control_totals": dict(data.control_totals),
            "tie_out_results": [dict(item) for item in data.tie_out_results],
            "ledger_heads": heads,
            "finished_at": uow.now,
        }
        if run["period_lock_id"] is None:
            values["source_binding"] = source_binding  # S15-R-24; NULL stays for as-locked runs
        finished = apply(
            session, TABLE, run_id, to_status=SUCCEEDED, set_values=values, expected_status=RUNNING
        )
        uow.audit(
            action=ACTION_SUCCEED,
            object_type=OBJECT_TYPE,
            object_id=run_id,
            before={"status": RUNNING},
            after={
                "status": SUCCEEDED,
                "output_file_id": str(output_file_id),
                "output_sha256": rendered.sha256,
                "row_count": data.row_count,
                "finished_at": utc_text(uow.now),
            },
        )
        # SOP-1 CTL-029: the rerun comparison is computed first and the fact derived from it
        # (D-98 candidate 100) — PASS, FAIL on a mismatch (a control exception; the run and the
        # job stay SUCCEEDED) or NOT_APPLICABLE for an original without output; CTL-030 (the
        # built-in tie-outs: each FAIL is one exception; no tie-outs is NOT_APPLICABLE).
        rerun_of, original = _original_of(session, params)
        fact = ctl029_fact({**run, **values}, original, rerun_of=rerun_of)
        record_execution(
            uow,
            control_id="CTL-029",
            run_ref_type=RunRefType.REPORT_RUN,
            run_ref_id=run_id,
            population_count=fact.population_count,
            exception_count=fact.exception_count,
            result=fact.result,
            detail=fact.detail,
        )
        failed_tie_outs = sum(1 for item in data.tie_out_results if item["result"] == tie_outs.FAIL)
        if not data.tie_out_results:
            tie_out_result = ControlResult.NOT_APPLICABLE
        elif failed_tie_outs:
            tie_out_result = ControlResult.FAIL
        else:
            tie_out_result = ControlResult.PASS
        record_execution(
            uow,
            control_id="CTL-030",
            run_ref_type=RunRefType.REPORT_RUN,
            run_ref_id=run_id,
            population_count=len(data.tie_out_results),
            exception_count=failed_tie_outs,
            result=tie_out_result,
            detail={
                "tie_outs": [
                    {"code": item["code"], "result": item["result"]}
                    for item in data.tie_out_results
                ]
            },
        )
        outcome = _outcome({**run, **finished, **values}, params, fact)
        uow.commit()
    return outcome


# --- reads -------------------------------------------------------------------------------------


def _within(scope: object) -> ColumnElement[bool] | None:
    """``report_run.entity_ids`` within a permission scope; None for every entity."""
    if scope == "*" or not isinstance(scope, frozenset):
        return None
    return report_run.c.entity_ids.op("<@")(literal(sorted(scope), type_=ARRAY(Uuid())))


def _under_run_permission(principal: Principal) -> ColumnElement[bool]:
    """A run is visible within the caller's scope of the permission ITS REPORT is run under
    (``run_permission``; ruling R-63 (a)): ``report.run`` for every report ``RUN_PERMISSIONS``
    does not name, the named permission for the others. A permission the caller does not hold
    shows none of its reports' runs."""
    named = sorted(RUN_PERMISSIONS)
    families: list[tuple[str, ColumnElement[bool]]] = [
        (RUN_PERMISSION, report_run.c.report_code.not_in(named))
    ]
    for permission in sorted(set(RUN_PERMISSIONS.values())):
        codes = sorted(code for code, held in RUN_PERMISSIONS.items() if held == permission)
        families.append((permission, report_run.c.report_code.in_(codes)))
    clauses: list[ColumnElement[bool]] = []
    for permission, of_reports in families:
        scope = principal.permission_scopes.get(permission)
        if scope is None:
            continue
        within = _within(scope)
        clauses.append(of_reports if within is None else and_(of_reports, within))
    return or_(*clauses) if clauses else false()


def _within_declared(principal: Principal) -> list[ColumnElement[bool]]:
    """Per report that declares a permission the caller holds for named entities: its runs lie
    within that scope too — the read's side of ``_in_scope_entities`` (rulings R-13 and R-28)."""
    clauses: list[ColumnElement[bool]] = []
    for code in sorted(REQUIRED_PERMISSIONS):
        for required in REQUIRED_PERMISSIONS[code]:
            within = _within(principal.permission_scopes.get(required.code))
            if within is not None:
                clauses.append(or_(report_run.c.report_code != code, within))
    return clauses


def _scoped(statement: Select[Any], principal: Principal, permission: str) -> Select[Any]:
    """Runs the caller reads under ``permission``: each within the scope of its report's run
    permission (``_under_run_permission``) and of every permission its report declares
    (``_within_declared``) and, for ``report.export``, also within the caller's scope of that
    permission."""
    statement = statement.where(_under_run_permission(principal), *_within_declared(principal))
    if permission == RUN_PERMISSION:
        return statement
    scope = principal.permission_scopes.get(permission)
    if scope is None:
        return statement.where(false())
    within = _within(scope)
    return statement if within is None else statement.where(within)


def _consistent_with_lock() -> Any:
    """S15-R-19 (rev 1.31, CLO8-SCOPE-R1 and its Codex 1622 residual): an as-locked run is visible
    only while its persisted FULL scope is its lock's — ``entity_ids`` exactly the lock's entity,
    ``book_code`` the lock's book, every persisted period selector the lock's period key, no
    parameter outside ``locked.ADMITTED_KEYS`` and ``entity_codes`` the lock's entity code — so
    readers are authorized against what the dataset holds, never against the request alone, in
    any status and however long ago the run completed. The SQL twin of ``locked.run_mismatch``."""
    parameters = report_run.c.parameters
    admitted = pg_array([literal(key) for key in sorted(locked.ADMITTED_KEYS)])
    period_selectors = [
        or_(parameters[key].astext.is_(None), parameters[key].astext == period.c.period_key)
        for key in locked.PERIOD_KEYS
    ]
    matching_lock = (
        select(literal(1))
        .select_from(period_lock)
        .join(legal_entity, legal_entity.c.id == period_lock.c.entity_id)
        .join(period, period.c.id == period_lock.c.period_id)
        .where(
            period_lock.c.id == report_run.c.period_lock_id,
            report_run.c.entity_ids == pg_array([period_lock.c.entity_id]),
            report_run.c.book_code == period_lock.c.book_code,
            parameters.op("-")(admitted) == cast(literal("{}"), JSONB),
            or_(
                parameters["entity_codes"].is_(None),
                parameters["entity_codes"] == func.jsonb_build_array(legal_entity.c.code),
            ),
            or_(
                parameters["book"].astext.is_(None),
                parameters["book"].astext == cast(period_lock.c.book_code, Text),  # Codex 1649 (a)
            ),
            *period_selectors,
        )
        .exists()
    )
    return or_(report_run.c.period_lock_id.is_(None), matching_lock)


def visible(statement: Select[Any], principal: Principal, permission: str) -> Select[Any]:
    """Runs whose entities are all in the caller's scope of ``permission`` and, for an as-locked
    run, whose entity scope is the lock's (``_consistent_with_lock``)."""
    return _scoped(statement, principal, permission).where(_consistent_with_lock())


def _refuse_inconsistent_lock_run(
    session: Session, principal: Principal, run_id: UUID, permission: str
) -> None:
    """An as-locked run within the caller's scope that ``visible`` hid because its persisted scope
    differs from its lock's is refused by name (S15-R-19), not reported absent."""
    hidden = (
        session.execute(
            _scoped(
                select(report_run.c.report_run_no, report_run.c.period_lock_id).where(
                    report_run.c.id == run_id
                ),
                principal,
                permission,
            )
        )
        .mappings()
        .one_or_none()
    )
    if hidden is not None and hidden["period_lock_id"] is not None:
        raise Problem(
            "not-found", locked.RUN_SCOPE_INCONSISTENT.format(run_no=hidden["report_run_no"])
        )


def runs_statement(principal: Principal) -> Select[Any]:
    """The runs ``GET /report-runs`` lists: each visible in the caller's scope of its report's run
    permission, and none of a report whose declared permission the caller lacks (04 API-R-41;
    rulings R-13, R-63 (a))."""
    statement = visible(select(report_run), principal, RUN_PERMISSION)
    withheld = withheld_reports(principal)
    return statement.where(report_run.c.report_code.not_in(withheld)) if withheld else statement


def run_row(
    session: Session, principal: Principal, run_id: UUID, permission: str, *, lock: bool = False
) -> Mapping[str, Any]:
    statement = visible(select(report_run).where(report_run.c.id == run_id), principal, permission)
    if lock:
        statement = statement.with_for_update()
    row = session.execute(statement).mappings().one_or_none()
    if row is None:
        _refuse_inconsistent_lock_run(session, principal, run_id, permission)
        raise Problem("not-found")
    if row["period_lock_id"] is not None:
        # CLO8-SCOPE-R1 (Codex 1622 residual): the authoritative reconciliation on EVERY addressed
        # read — detail, rows, output, manifest, rerun, cell explanation — whatever the row's status
        # and even when the database predicate admitted it; never deferred to a worker execution.
        lock_id = UUID(str(row["period_lock_id"]))
        scope = locked.lock_scope(session, lock_id)
        if scope is None:
            raise Problem(
                "not-found",
                locked.RUN_LOCK_MISSING.format(lock=lock_id, run_no=row["report_run_no"]),
            )
        if locked.run_mismatch(dict(row), scope) is not None:
            raise Problem(
                "not-found", locked.RUN_SCOPE_INCONSISTENT.format(run_no=row["report_run_no"])
            )
    return MappingProxyType(dict(row))


def _release_ref(engine_version: object, build_sha: object) -> EngineReleaseRefOut:
    """API-S-ReportRun ``engine_release``: the run's release identity, semver and sha distinct
    (05 REL-03; ``controls.release.release_identity`` refuses a swapped pair)."""
    version, sha = release_identity(engine_version, build_sha)
    return EngineReleaseRefOut(engine_version=version, build_sha=sha)


def run_outs(session: Session, rows: Sequence[Mapping[str, Any]]) -> list[ReportRunOut]:
    """API-S-ReportRun of each row, read in ``session``."""
    if not rows:
        return []
    definitions = {
        (str(found["code"]), int(found["version"])): str(found["name"])
        for found in session.execute(
            select(report_definition.c.code, report_definition.c.version, report_definition.c.name)
        ).mappings()
    }
    releases = {
        UUID(str(found["id"])): _release_ref(found["engine_version"], found["build_sha"])
        for found in session.execute(
            select(
                engine_release.c.id, engine_release.c.engine_version, engine_release.c.build_sha
            ).where(engine_release.c.id.in_({row["engine_release_id"] for row in rows}))
        ).mappings()
    }
    entity_ids = sorted({UUID(str(value)) for row in rows for value in row["entity_ids"]})
    refs = {
        UUID(str(found["id"])): RefOut(id=found["id"], code=found["code"], name=found["name"])
        for found in (
            session.execute(
                select(legal_entity.c.id, legal_entity.c.code, legal_entity.c.name).where(
                    legal_entity.c.id.in_(entity_ids)
                )
            ).mappings()
            if entity_ids
            else ()
        )
    }
    names = approval_queries.display_names(session, (row["created_by"] for row in rows))
    items: list[ReportRunOut] = []
    for row in rows:
        run_id = UUID(str(row["id"]))
        output = (
            None
            if row["output_file_id"] is None
            else ReportOutputOut(
                file_id=row["output_file_id"],
                format=str(row["output_format"]),
                sha256=str(row["output_sha256"]),
                href=OUTPUT_HREF.format(run_id=run_id),
                manifest_href=None
                if row["manifest_file_id"] is None
                else MANIFEST_HREF.format(run_id=run_id),
            )
        )
        code, version = str(row["report_code"]), int(row["report_version"])
        items.append(
            ReportRunOut(
                id=run_id,
                report_run_no=str(row["report_run_no"]),
                report=ReportRefOut(
                    code=code, version=version, name=definitions.get((code, version), code)
                ),
                status=row["status"],
                parameters=dict(row["parameters"]),
                entity_scope=[
                    refs[UUID(str(value))]
                    for value in row["entity_ids"]
                    if UUID(str(value)) in refs
                ],
                book=row["book_code"],
                as_of=row["as_of_date"],
                known_at=row["known_at"],
                period_lock_id=row["period_lock_id"],
                engine_release=releases[UUID(str(row["engine_release_id"]))],
                row_count=row["row_count"],
                control_totals=None
                if row["control_totals"] is None
                else dict(row["control_totals"]),
                # [J] D-88 L7-3-Q-3: `difference` is filled here, when the run is serialised; the
                # stored T-RPT-02 results, datasets, manifests and file outputs stay unchanged.
                tie_out_results=[
                    TieOutResultOut.model_validate(
                        {**item, "difference": tie_outs.difference(item)}
                    )
                    for item in row["tie_out_results"] or ()
                ],
                ledger_heads=dict(row["ledger_heads"] or {}),
                sources=sources_out(row),
                output=output,
                problem=None
                if row["problem"] is None
                else ProblemOut.model_validate(row["problem"]),
                job_id=row["job_id"],
                run_by=ActorOut.model_validate(
                    approval_queries.actor(row["created_by"], str(row["created_by_kind"]), names)
                ),
                started_at=row["started_at"],
                finished_at=row["finished_at"],
            )
        )
    return items


def get_run(
    ctx: RequestContext, session: Session, run_id: UUID, *, keyring: KeyRing | None = None
) -> ReportRunOut:
    row = run_row(session, ctx.principal, run_id, RUN_PERMISSION)
    require_report(ctx, str(row["report_code"]), run_id=run_id, keyring=keyring)  # R-13
    return run_outs(session, [row])[0]


def explain_cell(
    ctx: RequestContext,
    session: Session,
    run_id: UUID,
    *,
    row_key: str,
    column_key: str,
    keyring: KeyRing | None = None,
) -> ExplainCellOut:
    """``GET /explain/report-runs/{id}/cell``: the value and contributors of one cell of a
    SUCCEEDED run, read with the run's parameters (04 §16.11; SCREENS_B SB-R-07; REQ-RPT-017).

    The cell is explained as the run's job read it, and the caller is named the contributors
    her entity scope reaches; the rest is stated as one sum per entity (04 §16.11 rev 1.239;
    dev-guide DG-KRN-DB-05 rev 1.227; the supervisor's ruling of 2026-10-01; item
    RPT-EXPLAIN-READER-SCOPE-1).

    [J] L6-3-Q-24: dev-guide §5.16 names ``explain_report_cell`` in the kernel module
    ``erev_api/explain/service.py``, which may not import the report builders (DG-LAY-03), so the
    report domain serves it."""
    row = run_row(session, ctx.principal, run_id, RUN_PERMISSION)
    require_report(ctx, str(row["report_code"]), run_id=run_id, keyring=keyring)  # R-13
    if row["status"] != SUCCEEDED:
        raise Problem("invalid-transition", NOT_FINISHED)
    if row["period_lock_id"] is not None:
        raise Problem("not-found", locked.EXPLAIN_LOCKED)  # S15-R-19 rev 1.31
    explainer = CELL_EXPLAINERS.get(str(row["report_code"]))
    if explainer is None:
        raise Problem("not-found", NO_CELL_EXPLAINER)
    # S15-R-24: the explanation resolves against the run's bound sources — never today's rows —
    # and names only rows the saved output holds; an unbound live run is refused by name.
    require_bound(row, EXPLAIN_UNBOUND, "not-found")
    params = report_params(row)
    assert params.binding is not None  # require_bound: a live run here is bound
    require_original_row(params.binding, row_key)
    # The caller is authorised for the run and its report above. The explainer then reads what
    # the run's job read — every row the figure needs, whoever owns the row. Under the caller's
    # own scope it found "no such cell" for a row the run holds (the contract row of another
    # contracting entity) or was refused by S15-R-01 (the schedule lines another entity performs).
    with every_entity_scope(session, ctx.principal.db_context):
        value, contributors = explainer(session, params, row_key, column_key)
        owners = _contributor_entities(session, contributors)
        entities = _entity_refs_of(session, set(owners.values()))
    # A record is named only where the caller's scope reaches it; the rest is one sum per entity.
    # ``legal_entity`` is RLS-TE and the block has given the caller's scope back: her entities.
    reached = {UUID(str(found)) for found in session.execute(select(legal_entity.c.id)).scalars()}
    currency = str(value["currency"])
    named: list[Mapping[str, Any]] = []
    elsewhere: dict[UUID, Decimal] = {}
    for item in contributors:
        owner = owners[UUID(str(item["id"]))]
        if owner in reached:
            named.append(item)
        else:
            amount = Decimal(str(item["value"]["amount"]))
            elsewhere[owner] = elsewhere.get(owner, Decimal(0)) + amount
    return ExplainCellOut(
        value=MoneyOut(amount=str(value["amount"]), currency=currency),
        contributors=ExplainCellContributorsOut(
            items=[ExplainCellContributorOut.model_validate(item) for item in named]
        ),
        other_entities=[
            ExplainCellEntityPartOut(
                entity=entities[owner],
                value=MoneyOut(**tie_outs.money(amount, currency)),
            )
            for owner, amount in sorted(elsewhere.items(), key=lambda part: entities[part[0]].code)
        ],
    )


def _reach_statement(kind: str, ids: Sequence[UUID]) -> Select[tuple[UUID, UUID]]:
    """Contributor id and the entity whose scope reaches it, for the contributors of one kind —
    as the kind's own address ``GET /explain/{object_type}/{id}/{measure}`` judges reach
    (``explain.service``): a schedule line and a subledger line by the line's entity, an
    obligation version by its contract's row, the contracting entity. A kind without a rule is
    refused, so that a new contributor kind is never named before its reach is stated."""
    if kind == "schedule_line":
        return select(schedule_line.c.id, schedule_line.c.entity_id).where(
            schedule_line.c.id.in_(ids)
        )
    if kind == "subledger_line":
        return select(subledger_line.c.id, subledger_line.c.entity_id).where(
            subledger_line.c.id.in_(ids)
        )
    if kind == "obligation_version":
        return (
            select(obligation_version.c.id, contract.c.contracting_entity_id)
            .select_from(
                obligation_version.join(
                    contract,
                    and_(
                        contract.c.tenant_id == obligation_version.c.tenant_id,
                        contract.c.id == obligation_version.c.contract_id,
                    ),
                )
            )
            .where(obligation_version.c.id.in_(ids))
        )
    raise LookupError(f"no reach rule for a cell contributor of kind {kind}")


def _contributor_entities(
    session: Session, contributors: Sequence[Mapping[str, Any]]
) -> dict[UUID, UUID]:
    """Contributor id → the entity whose scope reaches the record (``_reach_statement``); read
    inside the caller's ``every_entity_scope`` block."""
    by_kind: dict[str, list[UUID]] = {}
    for item in contributors:
        by_kind.setdefault(str(item["object_type"]), []).append(UUID(str(item["id"])))
    owners: dict[UUID, UUID] = {}
    for kind, ids in sorted(by_kind.items()):
        owners.update(
            (UUID(str(found[0])), UUID(str(found[1])))
            for found in session.execute(_reach_statement(kind, sorted(set(ids))))
        )
    return owners


def _entity_refs_of(session: Session, entity_ids: set[UUID]) -> dict[UUID, RefOut]:
    """id, code and name of ``entity_ids`` — what a reader outside an entity is told of it and
    nothing else (supervisor ruling R-85 (d)); read inside the ``every_entity_scope`` block."""
    if not entity_ids:
        return {}
    return {
        UUID(str(found.id)): RefOut(id=found.id, code=str(found.code), name=str(found.name))
        for found in session.execute(
            select(legal_entity.c.id, legal_entity.c.code, legal_entity.c.name).where(
                legal_entity.c.id.in_(sorted(entity_ids))
            )
        )
    }


def run_rows(
    ctx: RequestContext, run_id: UUID, *, files: FileStore, keyring: KeyRing
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The rows of a SUCCEEDED JSON run and its columns ``{key, header, kind}`` in builder order,
    both from its stored dataset document (04 §16.9; D-88 L7-1-Q-5)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        row = run_row(session, ctx.principal, run_id, RUN_PERMISSION)
        require_report(ctx, str(row["report_code"]), run_id=run_id, keyring=keyring)  # R-13
        if row["status"] != SUCCEEDED or row["output_file_id"] is None:
            raise Problem("invalid-transition", NOT_FINISHED)
        if row["output_format"] != JSON_FORMAT:
            raise Problem("invalid-transition", DATA_OF_JSON_RUNS)
        _, stream = open_file(
            session, UUID(str(row["output_file_id"])), files=files, keyring=keyring
        )
    with stream:
        document = json.loads(stream.read())
    return (
        [dict(item) for item in document["rows"]],
        [dict(column) for column in document["columns"]],
    )


def open_output(
    ctx: RequestContext, run_id: UUID, *, part: str, files: FileStore, keyring: KeyRing
) -> Download:
    """``GET /report-runs/{id}/output``: the output or manifest stream of a SUCCEEDED run, after one
    ``report.export`` audit event naming the run (REQ-PLT-019)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        row = run_row(session, ctx.principal, run_id, EXPORT_PERMISSION)
        require_report(ctx, str(row["report_code"]), run_id=run_id, keyring=keyring)  # R-13
        if row["status"] != SUCCEEDED or row["output_file_id"] is None:
            raise Problem("invalid-transition", NOT_FINISHED)
        file_id = row["output_file_id"] if part == PART_OUTPUT else row["manifest_file_id"]
        if file_id is None:
            raise Problem("not-found", NO_MANIFEST)
        stored, stream = open_file(session, UUID(str(file_id)), files=files, keyring=keyring)
    # The stored name belongs to the first run of identical content; the download names this run.
    name = _file_name(row, _extension_of(row))
    if part == PART_MANIFEST:
        name += manifest_output.MANIFEST_SUFFIX
    audit_writer.record_now(
        ctx,
        action=ACTION_EXPORT,
        object_type=OBJECT_TYPE,
        object_id=run_id,
        detail={
            "report_code": str(row["report_code"]),
            "report_run_no": str(row["report_run_no"]),
            "output_format": str(row["output_format"]),
            "part": part,
            "file_id": str(file_id),
        },
        keyring=keyring,
    )
    return Download(stream=stream, media_type=str(stored["media_type"]), file_name=name)


_EXTENSIONS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "JSON": manifest_output.EXTENSION,
        "CSV": csv_output.EXTENSION,
        "XLSX": xlsx_output.EXTENSION,
        "PDF": pdf_output.EXTENSION,
        "ZIP": "zip",
    }
)


def _extension_of(row: Mapping[str, Any]) -> str:
    return _EXTENSIONS.get(str(row["output_format"]), "bin")


def chunks(stream: BinaryIO, size: int = 1024 * 1024) -> Iterator[bytes]:
    """Read ``stream`` in chunks and close it (REQ-RPT-024: outputs stream)."""
    with stream:
        while chunk := stream.read(size):
            yield chunk
