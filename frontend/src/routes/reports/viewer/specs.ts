// Report specifications on the client (SCREENS_B §5.1 groups, §5.2 data bindings, §5.6 RPT-R-01 to
// RPT-R-09; D-87 L6-3-Q-26). Parameters come from the context (entity, book, period, snapshot, known_at,
// currency_view) and the `p.<key>` screen parameters (SCREENS SCR-URL-17), restricted to the keys of the
// definition's closed `parameters_schema`, because any other key answers 422. Columns follow the key
// order of the run's rows, which the builders shape in specification order; headers, formats and
// drillable figures come from the specification of each field. Totals rows (`row_key` `total:<ISO>`)
// become DS-CMP-10 totals rows; sections come from the row field `section` (RPT-R-09), so `rpo` section
// 2 rows are the exempt contracts (L6-3-Q-26).
import { rpoBandLabels } from "../../../components/charts/RpoTimeBands";
import { testIdKey } from "../../../components/data-grid/DataGrid";
import type { GridTotalsRow } from "../../../components/data-grid/types";
import type {
  ReportDefinition,
  ReportRow,
  ReportRun,
  ReportRunColumn,
} from "../../../lib/api/queries/reports";
import { type Period, periodLabel } from "../../../lib/api/queries/tenant";
import { formatDate, formatNumber, formatPeriod, formatTimestamp } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";
import { decodeValue, rawParams } from "../../../lib/url/params";

import LOCK_DATASETS from "./lock-datasets.json";

// ---------------------------------------------------------------------------------------------------
// Catalogue (SCREENS_B §5.1).

export interface ReportGroup {
  readonly id: string;
  readonly codes: readonly string[];
}

export const REPORT_GROUPS: readonly ReportGroup[] = [
  {
    id: "revenueAndAnalysis",
    codes: [
      "revenue_waterfall",
      "bookings_billings_revenue",
      "variance_between_closes",
      "book_bridge",
      "adoption_bridge",
      "intercompany_pairs",
    ],
  },
  {
    id: "balancesAndDisclosures",
    codes: [
      "contract_balances",
      "contract_balance_rollforward",
      "revenue_from_opening_liability",
      "revenue_from_prior_period_obligations",
      "rpo",
      "rpo_rollforward",
      "disaggregation",
      "contract_cost_rollforward",
      "loss_provision_register",
      "balance_aging",
    ],
  },
  {
    id: "contractsModificationsJudgements",
    codes: [
      "contract_history",
      "latest_contract_status",
      "modification_register",
      "estimate_change_listing",
      "judgement_register",
      "scope_exclusion_register",
    ],
  },
  {
    id: "journalsAndClose",
    codes: [
      "je_population",
      "out_of_period_register",
      "late_entry_report",
      "manual_adjustment_register",
      "legacy_je_summary",
    ],
  },
  {
    id: "ssp",
    codes: [
      "ssp_change_log",
      "ssp_version_diff",
      "allocations_by_ssp_version",
      "ssp_override_listing",
    ],
  },
  {
    id: "accessConfigurationAudit",
    codes: [
      "config_change_register",
      "user_access_listing",
      "sod_conflict_report",
      "approvals_register",
      "api_client_inventory",
      "audit_log_export",
      "chain_verification_report",
    ],
  },
  {
    id: "forecastsAndMigration",
    codes: [
      "forecast_outputs",
      "actual_vs_forecast",
      "migration_reconciliation",
      "parallel_run_comparison",
    ],
  },
  {
    id: "legacyExports",
    codes: ["legacy_contract_history_export", "legacy_latest_contract_export"],
  },
  {
    id: "dataExtracts",
    codes: [
      "extract_contracts",
      "extract_obligations",
      "extract_contract_versions",
      "extract_schedule_lines",
      "extract_subledger_lines",
      "extract_journal_lines",
      "extract_balances",
      "extract_events",
      "extract_legacy_contract_live",
    ],
  },
  { id: "evidencePacks", codes: ["period_evidence_pack", "contract_sample_pack"] },
];

/**
 * §5.1 visibility: the forecast reports render only in a sandbox holding a scenario (REQ-FC-003, 005)
 * and the migration reports only when `GET /migrations?limit=1` returns an item. Neither read exists
 * in the rc (SF-17 and SF-19 are post-rc), so these codes stay hidden.
 */
export const HIDDEN_CODES: ReadonlySet<string> = new Set([
  "forecast_outputs",
  "actual_vs_forecast",
  "migration_reconciliation",
  "parallel_run_comparison",
]);

/** §5.1: packs link to SF-09 rather than to SF-08:report. */
export const PACK_CODES: ReadonlySet<string> = new Set([
  "period_evidence_pack",
  "contract_sample_pack",
]);

export function groupLabel(group: ReportGroup, count: number): string {
  // §5.1 caption "<group label> (<n>)"; RPT-R-03 money headers join the same way.
  return `${t(`reports.catalogue.group.${group.id}`)} (${formatNumber(count, { kind: "count" })})`;
}

/** `SF-08-grid-<group label normalised>`, for example `SF-08-grid-balances-and-disclosures`. */
export function groupTestId(group: ReportGroup): string {
  return `SF-08-grid-${testIdKey(t(`reports.catalogue.group.${group.id}`))}`;
}

const KINDS: ReadonlySet<string> = new Set([
  "STANDARD",
  "REGISTER",
  "DISCLOSURE",
  "EXTRACT",
  "PACK",
  "LEGACY_EXPORT",
]);

/** RPT-R-07 kind literals as outline chip words. */
export function kindLabel(kind: string): string {
  return KINDS.has(kind) ? t(`reports.kind.${kind}`) : kind;
}

const FORMATS: ReadonlySet<string> = new Set(["XLSX", "CSV", "PDF", "JSON", "ZIP"]);

/** RV-06 menu labels of the output formats. */
export function formatLabel(format: string): string {
  return FORMATS.has(format) ? t(`reports.export.format.${format}`) : format;
}

const TIE_OUTS: ReadonlySet<string> = new Set([
  "TO_WATERFALL_EQ_JE_REVENUE",
  "TO_ROLLFORWARD_EQ_GL",
  "TO_RPO_ROLLFORWARD_EQ_RPO",
  "TO_DISAGGREGATION_EQ_JE_REVENUE",
  "TO_ROLLFORWARD_BALANCES",
  "TO_BALANCES_EQ_ROLLFORWARD",
  "TO_JE_POPULATION_EQ_RUNS",
  "TO_AGING_EQ_BALANCES",
  "TO_COST_ROLLFORWARD_BALANCES",
  "TO_BBR_EQ_JE_REVENUE",
  "TO_IC_UNMATCHED_ZERO",
  "TO_MIGRATION_UNEXPLAINED_ZERO",
  "TO_BRIDGE_DRIVERS_EQ_DIFFERENCE",
]);

/** RPT-R-08 tie-out names; an unknown code keeps its literal. */
export function tieOutName(code: string): string {
  return TIE_OUTS.has(code) ? t(`reports.tieOut.${code}`) : code;
}

/** RPT-13, whose primary view is SF-06:entries (SCREENS_B §3.5). */
export const LEGACY_JE_SUMMARY = "legacy_je_summary";

/** SCREENS_B §3.5 `format` literals of the RPT-13 `mode`. */
export const JOURNAL_VIEW_FORMATS: Readonly<Record<string, "GROSS" | "DELTA">> = {
  gross: "GROSS",
  adjustment: "DELTA",
};

/**
 * The SF-06:entries search of a `/reports/legacy_je_summary` link: the context, `snapshot` and `run`
 * stay; `p.from_date`, `p.to_date` and `p.mode` become `from`, `to` and `format` (RPT-13).
 */
export function legacyJeSummarySearch(search: string): string {
  const parts: string[] = [];
  for (const param of rawParams(search)) {
    switch (param.name) {
      case "p.from_date":
        parts.push(`from=${param.value}`);
        break;
      case "p.to_date":
        parts.push(`to=${param.value}`);
        break;
      case "p.mode": {
        const format = Object.entries(JOURNAL_VIEW_FORMATS).find(
          ([, mode]) => mode === decodeValue(param.value),
        )?.[0];
        if (format !== undefined) {
          parts.push(`format=${format}`);
        }
        break;
      }
      default:
        if (!param.name.startsWith("p.")) {
          parts.push(`${param.name}=${param.value}`);
        }
    }
  }
  return parts.length === 0 ? "" : `?${parts.join("&")}`;
}

// ---------------------------------------------------------------------------------------------------
// Parameters (RPT-R-01; §5.2 data bindings; §5.6 parameter tables).

export interface ReportContext {
  readonly entity: string | null;
  readonly book: string | null;
  readonly periodKey: string | null;
  /** The periods of the context entity and book, in period order; empty while unknown. */
  readonly periods: readonly Period[];
  readonly snapshot: string | null;
  readonly knownAt: string | null;
  readonly currencyView: string | null;
}

type Schema = Readonly<Record<string, unknown>>;

function properties(definition: ReportDefinition): Readonly<Record<string, Schema>> {
  const found = definition.parameters_schema.properties;
  return typeof found === "object" && found !== null
    ? (found as Readonly<Record<string, Schema>>)
    : {};
}

/** The parameter keys of the definition in schema order. */
export function parameterKeys(definition: ReportDefinition): readonly string[] {
  return Object.keys(properties(definition));
}

function fixedValue(schema: Schema | undefined): string | null {
  const values = schema?.enum;
  return Array.isArray(values) && values.length === 1 && typeof values[0] === "string"
    ? values[0]
    : null;
}

/** The `p.<key>` value typed by the key's schema: arrays split on commas, booleans and integers. */
function typed(schema: Schema | undefined, raw: string): unknown {
  switch (schema?.type) {
    case "array": {
      const items = raw.split(",").filter((item) => item !== "");
      const itemType = (schema.items as Schema | undefined)?.type;
      return itemType === "integer" ? items.map((item) => Number.parseInt(item, 10)) : items;
    }
    case "boolean":
      return raw === "true";
    case "integer":
      return Number.parseInt(raw, 10);
    default:
      return raw;
  }
}

export function contextPeriod(context: ReportContext): Period | null {
  return context.periods.find((item) => item.period.period_key === context.periodKey) ?? null;
}

// ---------------------------------------------------------------------------------------------------
// As locked (SCREENS_B §0.5 RV-04 rev 1.98; SCREENS SCR-URL-06; ENGINE_SPEC_B S15-R-19, §15.2.7).

const LOCK_KEY = "period_lock_id";
/** The selectors of a run that name its period, each the lock's own period on an as-locked run. */
const PERIOD_KEYS: readonly string[] = ["period_key", "from_period_key", "to_period_key"];

/**
 * True for a report a period lock freezes: one of the E-64 dataset kinds. `lock-datasets.json` is the
 * API's own table (`locked.SNAPSHOT_KIND_BY_REPORT`), written by `scripts/as_locked_fixture.py` and
 * held to it by `backend/tests/unit/test_as_locked_fixture.py` — API-S-ReportDefinition does not
 * state it, and this is the one place that reads the table instead. A closed context period defaults
 * such a report to "As locked"; every other report shows current figures and says so.
 */
export function hasLockDataset(code: string): boolean {
  return Object.hasOwn(LOCK_DATASETS, code);
}

/** True for a report whose runs can name a lock at all: its schema has `period_lock_id`. */
export function takesLock(definition: ReportDefinition): boolean {
  return Object.hasOwn(properties(definition), LOCK_KEY);
}

/**
 * The lock whose datasets stand for the context period (04 API-S-Period `dataset_lock`; RV-04 rev
 * 1.101): the record of the close that froze the period's figures. While the period is `closed` that
 * is its current lock; on a `permanently_locked` period it is the LOCK the permanent lock sealed —
 * the permanent lock's own record freezes nothing, and a run that names it is refused with the LOCK
 * to pass. Null where no dataset stands: a period that is not locked, and a locked one without a
 * LOCK record. "As locked" is this lock's and no other's — the default names it, the banner says its
 * time, the run stamp is compared with it.
 */
export function datasetLock(context: ReportContext): NonNullable<Period["current_lock"]> | null {
  return contextPeriod(context)?.dataset_lock ?? null;
}

/**
 * The source of the view is the lock whose datasets stand for the context period: the address names
 * that lock and the report's runs take one. Only then does the view say "as locked", ask the lock's
 * own selectors and make its fields unavailable — the sentence names the context period and the
 * time its figures were frozen at, so it is true of no other lock. A `snapshot` beside a report that
 * takes no lock is sent nowhere, and the view does not call its figures locked.
 */
export function isAsLocked(definition: ReportDefinition, context: ReportContext): boolean {
  const lock = datasetLock(context);
  return lock !== null && context.snapshot === lock.id && takesLock(definition);
}

/**
 * The address names a lock that is not the one whose datasets stand for the context period: another
 * period's, as the link of a stored as-locked run whose parameters name no `period_key` can be once
 * the context is filled around it; the record of a permanent lock; or one the calendar does not
 * list. It is sent as written with the view's parameters, the API answers, and the view says nothing
 * of the context period's lock: the run stamp states the source.
 */
export function namesAnotherLock(definition: ReportDefinition, context: ReportContext): boolean {
  return context.snapshot !== null && takesLock(definition) && !isAsLocked(definition, context);
}

/** The context period's fiscal year periods, in period order. */
function fiscalYear(context: ReportContext): readonly Period[] {
  const current = contextPeriod(context);
  return current === null
    ? []
    : context.periods.filter((item) => item.period.fiscal_year === current.period.fiscal_year);
}

/** The §5.6 defaults of the report-specific keys that the screen supplies. */
export function parameterDefaults(
  definition: ReportDefinition,
  context: ReportContext,
): Readonly<Record<string, string>> {
  const keys = new Set(parameterKeys(definition));
  const current = contextPeriod(context);
  const year = fiscalYear(context);
  const defaults: Record<string, string> = {};
  if (current === null) {
    return defaults;
  }
  if (isAsLocked(definition, context)) {
    // RV-04 rev 1.98: a lock holds one period, and its figures take no date and no other choice.
    for (const key of PERIOD_KEYS.filter((item) => item !== "period_key" && keys.has(item))) {
      defaults[key] = current.period.period_key;
    }
    return defaults;
  }
  // RPT-01: the first and last period of the context fiscal year; RPT-03 and others: the context period.
  const wholeYear = definition.code === "revenue_waterfall";
  if (keys.has("from_period_key")) {
    defaults.from_period_key = wholeYear
      ? (year[0]?.period.period_key ?? current.period.period_key)
      : current.period.period_key;
  }
  if (keys.has("to_period_key")) {
    defaults.to_period_key = wholeYear
      ? (year.at(-1)?.period.period_key ?? current.period.period_key)
      : current.period.period_key;
  }
  // RPT-09 and RPT-10: the first day of the context fiscal year to the end of the context period.
  if (keys.has("from_date")) {
    defaults.from_date = year[0]?.period.start_date ?? current.period.start_date;
  }
  if (keys.has("to_date")) {
    defaults.to_date = current.period.end_date;
  }
  return defaults;
}

/**
 * API-S-ReportRunCreate `parameters` of the view: `entity` → `entity_codes` (absent: every entity in
 * scope), `book`, `period` → `period_key` and `as_of` (its end date), `snapshot` → `period_lock_id`,
 * `known_at`, `currency_view`, then the `p.<key>` values over the §5.6 defaults.
 *
 * An as-locked run (RV-04 rev 1.98; ENGINE_SPEC_B S15-R-19) is the lock's entity, book and period and
 * nothing else: the lock, the context's entity and book, each period key of the schema as the context
 * period, and a cutoff the address names. No `as_of`, no date, no `currency_view` and no `p.<key>` —
 * the frozen dataset carries no such selector, and the API refuses each by name.
 */
export function runParameters(
  definition: ReportDefinition,
  context: ReportContext,
  values: Readonly<Record<string, string>>,
): Record<string, unknown> {
  const schema = properties(definition);
  const has = (key: string) => Object.hasOwn(schema, key);
  const current = contextPeriod(context);
  const parameters: Record<string, unknown> = {};
  if (has("entity_codes") && context.entity !== null) {
    parameters.entity_codes = [context.entity];
  }
  if (has("book")) {
    const fixed = fixedValue(schema.book);
    if (fixed !== null) {
      parameters.book = fixed;
    } else if (context.book !== null) {
      parameters.book = context.book;
    }
  }
  if (isAsLocked(definition, context)) {
    if (context.periodKey !== null) {
      for (const key of PERIOD_KEYS.filter(has)) {
        parameters[key] = context.periodKey;
      }
    }
    parameters[LOCK_KEY] = context.snapshot;
    if (has("known_at") && context.knownAt !== null) {
      parameters.known_at = context.knownAt;
    }
    return parameters;
  }
  if (has("period_key") && context.periodKey !== null) {
    parameters.period_key = context.periodKey;
  }
  if (has("as_of") && schema.as_of?.format === "date" && current !== null) {
    parameters.as_of = current.period.end_date;
  }
  if (has("known_at") && context.knownAt !== null) {
    parameters.known_at = context.knownAt;
  }
  if (has("currency_view") && context.currencyView !== null) {
    parameters.currency_view = context.currencyView;
  }
  if (has(LOCK_KEY) && context.snapshot !== null) {
    // A lock that is not the context period's (`namesAnotherLock`): sent as the address says.
    parameters[LOCK_KEY] = context.snapshot;
  }
  const merged = { ...parameterDefaults(definition, context), ...values };
  for (const [key, raw] of Object.entries(merged)) {
    if (has(key) && raw !== "") {
      parameters[key] = typed(schema[key], raw);
    }
  }
  return parameters;
}

/** RV-08 submit validation: field key → message. */
export function validateParameters(
  context: ReportContext,
  parameters: Readonly<Record<string, unknown>>,
): Readonly<Record<string, string>> {
  const errors: Record<string, string> = {};
  const from = parameters.from_period_key;
  const to = parameters.to_period_key;
  if (typeof from === "string" && typeof to === "string") {
    const index = (key: string) =>
      context.periods.findIndex((item) => item.period.period_key === key);
    if (index(from) >= 0 && index(to) >= 0 && index(from) > index(to)) {
      errors.from_period_key = t("reports.parameters.periodOrder");
    }
  }
  const fromDate = parameters.from_date;
  const toDate = parameters.to_date;
  // DG-FE-20: business dates compare as strings.
  if (typeof fromDate === "string" && typeof toDate === "string" && fromDate > toDate) {
    errors.from_date = t("reports.parameters.dateOrder");
  }
  return errors;
}

// ---------------------------------------------------------------------------------------------------
// Rows, sections and columns (RPT-R-02 to RPT-R-04, RPT-R-09).

export interface Money {
  readonly amount: string;
  readonly currency: string;
}

export function isMoney(value: unknown): value is Money {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as { amount?: unknown }).amount === "string" &&
    typeof (value as { currency?: unknown }).currency === "string"
  );
}

/** The builders' totals rows: `row_key` `TOTAL:<ISO>` (RPT-R-04). */
export const TOTAL_ROW_PREFIX = "TOTAL:";

/** The reports whose section 1 figures name contributors (API-R-49 cell explainers). */
export const DRILLABLE_REPORTS: ReadonlySet<string> = new Set(["revenue_waterfall", "rpo"]);

export interface ReportSection {
  readonly number: number;
  readonly heading: string;
  readonly rows: readonly ReportRow[];
  readonly totals: readonly ReportRow[];
}

const SECTION_HEADINGS: Readonly<Record<string, readonly string[]>> = {
  rpo: ["reports.section.rpo.1", "reports.section.rpo.2"],
};

/**
 * The section a row states. A live run states a number. A frozen row states it as text, as every cell
 * of a lock dataset is text (RV-04 rev 1.17): read as a number only, an as-locked `rpo` listed its
 * exempt obligations under the first heading and said "Exempt contracts (0)" below them.
 */
function sectionNumber(row: ReportRow): number | null {
  const value: unknown = row.section;
  if (typeof value === "number") {
    return value;
  }
  return typeof value === "string" && /^[1-9]\d*$/.test(value) ? Number(value) : null;
}

/** RPT-R-09: one section per `section` number in order; a report without the field has one section. */
export function sectionsOf(
  definition: ReportDefinition,
  rows: readonly ReportRow[],
): ReportSection[] {
  const numbers = new Set<number>([1]);
  const headings = SECTION_HEADINGS[definition.code];
  for (let index = 2; index <= (headings?.length ?? 0); index += 1) {
    numbers.add(index);
  }
  for (const row of rows) {
    const stated = sectionNumber(row);
    if (stated !== null) {
      numbers.add(stated);
    }
  }
  return [...numbers]
    .sort((left, right) => left - right)
    .map((number) => {
      const members = rows.filter((row) => (sectionNumber(row) ?? 1) === number);
      const key = headings?.[number - 1];
      return {
        number,
        heading: key === undefined ? definition.name : t(key),
        rows: members.filter((row) => !row.row_key.startsWith(TOTAL_ROW_PREFIX)),
        totals: members.filter((row) => row.row_key.startsWith(TOTAL_ROW_PREFIX)),
      };
    });
}

export interface RpoBand {
  readonly index: number;
  readonly key: string;
  readonly from_month: number;
  readonly to_month: number | null;
}

/** L6-3-Q-26: the ordered bands of an `rpo` run are the control total `bands`. */
export function rpoBands(
  controlTotals: Readonly<Record<string, unknown>> | null,
): readonly RpoBand[] {
  const bands = controlTotals?.bands;
  if (!Array.isArray(bands)) {
    return [];
  }
  return bands.filter(
    (band): band is RpoBand =>
      typeof band === "object" &&
      band !== null &&
      typeof (band as { key?: unknown }).key === "string" &&
      typeof (band as { index?: unknown }).index === "number",
  );
}

/** The month boundaries of the bands, for DS-CH-03 labels: every band's upper month but the last. */
export function bandBoundaries(bands: readonly RpoBand[]): readonly number[] {
  return bands.flatMap((band) => (band.to_month === null ? [] : [band.to_month]));
}

export type ReportColumnKind = "identifier" | "text" | "money" | "number";

export interface ReportColumn {
  /** The row field and the explain `column_key`. */
  readonly key: string;
  readonly header: string;
  readonly kind: ReportColumnKind;
  readonly drillable: boolean;
}

/** Fields that carry structure, not figures. */
const STRUCTURAL: ReadonlySet<string> = new Set(["row_key", "section", "expedient"]);

/** RPT-R-03: the field of a mixed-currency result shown by the DS-FMT-12 Currency column (DS-CMP-10 item 7). */
export const CURRENCY_COLUMN_KEY = "currency";

const HEADERS: ReadonlySet<string> = new Set([
  "contract_external_id",
  "customer_name",
  "obligation_key",
  "product_code",
  "revenue_category",
  "entity_code",
  CURRENCY_COLUMN_KEY,
  "awaiting_trigger",
  "total",
  "current",
  "noncurrent",
  "expedient_label",
  "nature",
  "remaining_duration_months",
  "excluded_amount",
  "excluded_descriptor",
]);

export const PERIOD_COLUMN_PREFIX = "period:";

const QUARTER_KEY = /^FY(\d{4})-Q([1-4])$/;

/**
 * DS-FMT-19 label of a period or bucket key from the context calendar, else the fiscal label. RPT-01
 * quarter buckets `FY<year>-Q<n>` read "Q3 2026" when the fiscal year starts in January of that year, and
 * "FY2027 Q2" otherwise (WLD-P-05; SCREENS_B §5.6 RPT-01).
 */
export function bucketLabel(key: string, periods: readonly Period[]): string {
  const found = periods.find((item) => item.period.period_key === key);
  if (found !== undefined) {
    return periodLabel(found.period);
  }
  const quarter = QUARTER_KEY.exec(key);
  if (quarter !== null) {
    const [, year = "", number = ""] = quarter;
    const first = periods.find((item) => String(item.period.fiscal_year) === year);
    // DG-FE-20: business dates compare as strings.
    if (first?.period.start_date.startsWith(`${year}-01-`) === true) {
      return t("reports.column.quarterCalendar", { quarter: number, year });
    }
  }
  try {
    return formatPeriod(key);
  } catch {
    return key;
  }
}

function currenciesOf(rows: readonly ReportRow[]): ReadonlySet<string> {
  const found = new Set<string>();
  for (const row of rows) {
    for (const value of Object.values(row)) {
      if (isMoney(value)) {
        found.add(value.currency);
      }
    }
  }
  return found;
}

/** The §5.6 columns of a section whose run returned no rows for it. */
const EMPTY_SECTION_COLUMNS: Readonly<
  Record<string, Readonly<Record<number, readonly (readonly [string, ReportColumnKind])[]>>>
> = {
  rpo: {
    1: [
      ["contract_external_id", "text"],
      ["customer_name", "text"],
      ["entity_code", "text"],
      ["currency", "text"],
      ["total", "money"],
    ],
    2: [
      ["contract_external_id", "text"],
      ["obligation_key", "text"],
      ["expedient_label", "text"],
      ["nature", "text"],
      ["remaining_duration_months", "number"],
      ["excluded_amount", "money"],
      ["excluded_descriptor", "text"],
    ],
  },
};

export interface ColumnContext {
  readonly definition: ReportDefinition;
  readonly section: ReportSection;
  readonly periods: readonly Period[];
  readonly bands: readonly RpoBand[];
  /** The run's `columns` in builder order (D-88 L7-1-Q-5); a legacy export orders its grid by them. */
  readonly columns?: readonly ReportRunColumn[] | undefined;
}

function headerOf(key: string, context: ColumnContext): string {
  if (key.startsWith(PERIOD_COLUMN_PREFIX)) {
    const [bucket = "", state] = key.slice(PERIOD_COLUMN_PREFIX.length).split(":");
    const label = bucketLabel(bucket, context.periods);
    return state === "recognized" || state === "scheduled"
      ? t(`reports.column.period.${state}`, { period: label })
      : label;
  }
  const band = context.bands.find((item) => item.key === key);
  if (band !== undefined) {
    return rpoBandLabels(bandBoundaries(context.bands))[band.index] ?? key;
  }
  if (context.definition.kind !== "LEGACY_EXPORT" && HEADERS.has(key)) {
    return t(`reports.column.${key}`);
  }
  // Legacy exports keep the 71 legacy names as headers and row keys (D-33, DS-LINT-19).
  return key;
}

/**
 * §5.6 column order of the known fields. A stored run serialises each row with sorted keys, so the key
 * order of `GET /report-runs/{id}/data` is not the specification order (L7-3-Q-6): identity fields
 * first, then periods in key order, bands in API order and the figures of each specification; unknown
 * fields keep their row order after them. A legacy export instead follows the run's `columns`, the builder's
 * legacy output order (D-88 L7-1-Q-5 over L7-3-Q-6; SCREENS_B RPT-10, RPT-12); moving the other reports to
 * the column metadata is post-rc.
 */
const IDENTITY_RANKS: Readonly<Record<string, number>> = {
  contract_external_id: 0,
  customer_name: 1,
  obligation_key: 2,
  product_code: 3,
  revenue_category: 4,
  entity_code: 5,
  currency: 6,
};

const FIGURE_RANKS: Readonly<Record<string, Readonly<Record<string, number>>>> = {
  revenue_waterfall: { awaiting_trigger: 800, total: 900 },
  rpo: {
    total: 7,
    current: 500,
    noncurrent: 501,
    expedient_label: 600,
    nature: 601,
    remaining_duration_months: 602,
    excluded_amount: 603,
    excluded_descriptor: 604,
  },
};

const PERIODS_RANK = 100;
const BANDS_RANK = 10;
const UNKNOWN_RANK = 1_000;

function orderedKeys(
  definition: ReportDefinition,
  keys: readonly string[],
  bands: readonly RpoBand[],
  columns: readonly ReportRunColumn[] | undefined,
): string[] {
  if (definition.kind === "LEGACY_EXPORT") {
    // The keys in `columns[].key` order; `row_key` and `section` stay hidden (STRUCTURAL), and a row field
    // that names no column keeps its row order after them.
    const listed = (columns ?? [])
      .map((column) => column.key)
      .filter((key) => !STRUCTURAL.has(key));
    const named = new Set(listed);
    return [...listed, ...keys.filter((key) => !named.has(key))];
  }
  const figures = FIGURE_RANKS[definition.code] ?? {};
  const rank = (key: string, index: number): number => {
    const known = IDENTITY_RANKS[key] ?? figures[key];
    if (known !== undefined) {
      return known;
    }
    if (key.startsWith(PERIOD_COLUMN_PREFIX)) {
      return PERIODS_RANK;
    }
    const band = bands.find((item) => item.key === key);
    return band === undefined ? UNKNOWN_RANK + index : BANDS_RANK + band.index;
  };
  return keys
    .map((key, index) => ({ key, rank: rank(key, index) }))
    .sort((left, right) => {
      if (left.rank !== right.rank) {
        return left.rank - right.rank;
      }
      // Period keys are zero-padded (`FY2026-P09`), and `:recognized` sorts before `:scheduled`.
      return left.key < right.key ? -1 : left.key > right.key ? 1 : 0;
    })
    .map((item) => item.key);
}

/** The columns of a section in §5.6 order, with money headers `<header> (<ISO>)` (RPT-R-03). */
export function reportColumns(context: ColumnContext): ReportColumn[] {
  const { definition, section } = context;
  const rows = [...section.rows, ...section.totals];
  const keys: string[] = [];
  const kinds = new Map<string, ReportColumnKind>();
  for (const row of rows) {
    for (const [key, value] of Object.entries(row)) {
      if (STRUCTURAL.has(key)) {
        continue;
      }
      if (!keys.includes(key)) {
        keys.push(key);
      }
      if (value !== null && value !== undefined && !kinds.has(key)) {
        kinds.set(key, isMoney(value) ? "money" : typeof value === "number" ? "number" : "text");
      }
    }
  }
  if (keys.length === 0) {
    // A section without rows still shows its columns (RPT-06 section 2 "Exempt contracts (0)").
    const fallback = [
      ...(EMPTY_SECTION_COLUMNS[definition.code]?.[section.number] ?? []),
      ...(definition.code === "rpo" && section.number === 1
        ? [
            ...context.bands.map((band) => [band.key, "money"] as const),
            ["current", "money"] as const,
            ["noncurrent", "money"] as const,
          ]
        : []),
    ];
    for (const [key, kind] of fallback) {
      keys.push(key);
      kinds.set(key, kind);
    }
  }
  const currencies = currenciesOf(rows);
  const single = currencies.size === 1 ? [...currencies][0] : undefined;
  const drillable = DRILLABLE_REPORTS.has(definition.code) && section.number === 1;
  return orderedKeys(definition, keys, context.bands, context.columns).map((key) => {
    const kind: ReportColumnKind =
      key === "contract_external_id" && definition.kind !== "LEGACY_EXPORT"
        ? "identifier"
        : (kinds.get(key) ?? "text");
    const header = headerOf(key, context);
    return {
      key,
      header: kind === "money" && single !== undefined ? `${header} (${single})` : header,
      kind,
      drillable:
        (drillable ||
          (definition.code === "loss_provision_register" && key === "provision_balance")) &&
        kind === "money",
    };
  });
}

/** DS-CMP-10 totals rows of a section: one per currency, figures from the run (RPT-R-04). */
export function totalsRows(section: ReportSection): GridTotalsRow[] {
  return section.totals.map((row) => {
    const values: Record<string, string> = {};
    let currency = row.row_key.slice(TOTAL_ROW_PREFIX.length);
    for (const [key, value] of Object.entries(row)) {
      if (isMoney(value)) {
        values[key] = value.amount;
        currency = value.currency;
      }
    }
    return { key: row.row_key, currency, values };
  });
}

/** `SF-08-row-<row key normalised>`: the row key without its kind prefix (`contract:SF-ORD-10002`). */
export function rowTestKey(row: ReportRow): string {
  const colon = row.row_key.indexOf(":");
  return colon < 0 ? row.row_key : row.row_key.slice(colon + 1);
}

/** The row's business label for figure names: the contract, else the row key without its prefix. */
export function rowLabel(row: ReportRow): string {
  const contract = row.contract_external_id;
  const obligation = row.obligation_key;
  if (typeof contract === "string") {
    return typeof obligation === "string" ? `${contract} ${obligation}` : contract;
  }
  return row.row_key.startsWith(TOTAL_ROW_PREFIX) ? t("common.grid.total") : rowTestKey(row);
}

// ---------------------------------------------------------------------------------------------------
// Empty runs (SCREENS_B §5.6 "Empty copy" of each report; DESIGN_SYSTEM DS-CMP-23).

export interface EmptyCopy {
  readonly title: string;
  readonly description: string;
}

type RunFacts = Pick<ReportRun, "parameters" | "control_totals">;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const UTC_INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/;

/** A parameter of the run, else the value its builder resolved and echoed in the control totals. */
function factOf(run: RunFacts, key: string): unknown {
  return run.parameters[key] ?? run.control_totals?.[key] ?? null;
}

function dateOf(run: RunFacts, key: string): string {
  const value = factOf(run, key);
  return typeof value === "string" && ISO_DATE.test(value) ? formatDate(value) : "";
}

function instantOf(run: RunFacts, key: string): string {
  const value = factOf(run, key);
  return typeof value === "string" && UTC_INSTANT.test(value) ? formatTimestamp(value) : "";
}

/** "<range label>": one period's label, or "<from label> to <to label>". */
function rangeOf(run: RunFacts, context: ReportContext): string {
  const from = factOf(run, "from_period_key");
  const to = factOf(run, "to_period_key");
  const first = typeof from === "string" ? bucketLabel(from, context.periods) : null;
  const last = typeof to === "string" ? bucketLabel(to, context.periods) : null;
  if (first === null || last === null || first === last) {
    return first ?? last ?? "";
  }
  return t("reports.empty.range", { from: first, to: last });
}

/** The interpolations of the SCREENS_B empty copy, by report code. */
const EMPTY_PARAMS: Readonly<
  Record<string, (run: RunFacts, context: ReportContext) => Readonly<Record<string, string>>>
> = {
  ssp_change_log: dates,
  allocations_by_ssp_version: dates,
  ssp_override_listing: dates,
  config_change_register: dates,
  approvals_register: dates,
  judgement_register: dates,
  estimate_change_listing: dates,
  chain_verification_report: (run) => ({ from: instantOf(run, "from"), to: instantOf(run, "to") }),
  sod_conflict_report: (run) => ({ instant: instantOf(run, "as_of") }),
  scope_exclusion_register: (run) => ({ date: dateOf(run, "as_of") }),
  contract_cost_rollforward: range,
  intercompany_pairs: range,
  book_bridge: (run, context) => {
    const codes = run.parameters.entity_codes;
    const entity = Array.isArray(codes) && typeof codes[0] === "string" ? codes[0] : "";
    return {
      range: rangeOf(run, context),
      entity: entity === "" ? (context.entity ?? "") : entity,
    };
  },
  adoption_bridge: (run) => ({ date: dateOf(run, "date_of_initial_application") }),
};

function dates(run: RunFacts): Readonly<Record<string, string>> {
  return { from: dateOf(run, "from_date"), to: dateOf(run, "to_date") };
}

function range(run: RunFacts, context: ReportContext): Readonly<Record<string, string>> {
  return { range: rangeOf(run, context) };
}

const LATE_ENTRY_REPORT = "late_entry_report";
const AUDIT_LOG_EXPORT = "audit_log_export";

/**
 * RPT-17 "Empty copy per section": "No events entered after the lock of <period label>." and "No events
 * within <n> days of <period end date>."; null for another report or section.
 */
export function sectionEmptyCopy(
  code: string,
  section: number,
  run: RunFacts,
  context: ReportContext,
): string | null {
  if (code !== LATE_ENTRY_REPORT) {
    return null;
  }
  const key = factOf(run, "period_key");
  const period =
    typeof key === "string"
      ? context.periods.find((item) => item.period.period_key === key)
      : undefined;
  if (section === 1) {
    return t("reports.empty.late_entry_report.section1", {
      period: typeof key === "string" ? bucketLabel(key, context.periods) : "",
    });
  }
  if (section === 2) {
    const days = factOf(run, "window_days");
    return t("reports.empty.late_entry_report.section2", {
      count: typeof days === "number" ? days : 0,
      date: period === undefined ? "" : formatDate(period.period.end_date),
    });
  }
  return null;
}

/**
 * The SCREENS_B empty copy of a register or analysis report; null for a report whose copy the view states
 * itself (`revenue_waterfall`, `rpo`, `legacy_contract_history_export`) or that keeps the generic copy:
 * `user_access_listing` ("not reachable": every tenant has a Tenant Admin) and `ssp_version_diff`, whose
 * copy names two version labels that a run does not carry.
 */
export function registerEmptyCopy(
  code: string,
  run: RunFacts,
  context: ReportContext,
): EmptyCopy | null {
  if (code === LATE_ENTRY_REPORT) {
    return {
      title: sectionEmptyCopy(code, 1, run, context) ?? "",
      description: sectionEmptyCopy(code, 2, run, context) ?? "",
    };
  }
  if (code === AUDIT_LOG_EXPORT) {
    // RPT-43 states one sentence; the description is the generic one of an empty run.
    return {
      title: t("reports.empty.audit_log_export.title"),
      description: t("reports.empty.generic.description"),
    };
  }
  const params = EMPTY_PARAMS[code];
  if (params === undefined) {
    return null;
  }
  const values = params(run, context);
  return {
    title: t(`reports.empty.${code}.title`, values),
    description: t(`reports.empty.${code}.description`, values),
  };
}
