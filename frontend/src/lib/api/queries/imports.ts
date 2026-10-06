// Imports (04 API-R-43 `GET /imports`, `GET /imports/{id}`, `/rows`, `/diff`, `/error-report`,
// `POST /imports`, `/submit`, `/cancel`; API-R-11 `GET /jobs`; API-S-Import, API-S-ImportRow,
// API-S-ImportDiff; E-40, E-41; SCREENS §12.1 to §12.3, §0.4 RT-42 to RT-45; BUILD_SPEC DIN-15, DIN-16).
// Counts stay the API's integers and digests and amounts its strings (DG-FE-08).
import { api, send, unwrap } from "../client";
import type { Job } from "../jobs";
import { fetchListPage, type ListPage } from "../lists";
import { isRefused, readProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type ImportItem = components["schemas"]["ImportOut"];
export type ImportStatus = components["schemas"]["ImportStatus"];
export type ImportRow = components["schemas"]["ImportRowOut"];
export type ImportRowStatus = components["schemas"]["ImportRowStatus"];
export type ImportDiff = components["schemas"]["ImportDiffOut"];
export type ImportDiffItem = components["schemas"]["ImportDiffItemOut"];
export type ImportFinding = components["schemas"]["FindingCountOut"];
export type HeaderMatch = components["schemas"]["HeaderMatchOut"];
export type ImportCreateBody = components["schemas"]["ImportCreateIn"];

export const IMPORTS_PATH = "/api/v1/imports";
export const JOBS_PATH = "/api/v1/jobs";
/** SCREENS RT-42 SF-10, the "Data" rail destination (SCR-IA-01). */
export const IMPORTS_ROUTE = "/data/imports";
/** SCREENS RT-43 SF-10:new. */
export const NEW_IMPORT_ROUTE = "/data/imports/new";
/** SCREENS RT-44: `/data/imports/:importId` redirects to the step of the import's status. */
export const IMPORT_DETAIL_ROUTE = "/data/imports/:importId";
/** SCREENS RT-44 SF-10:detail. */
export const IMPORT_STEP_ROUTE = "/data/imports/:importId/:step";
/** SCREENS RT-45 SF-10:templates. */
export const TEMPLATES_ROUTE = "/data/templates";
/** SCREENS RT-46 SF-11 (built by DIN-17; linked only once built, XR-14). */
export const EXCEPTIONS_ROUTE = "/data/exceptions";
/** 04 API-R-43: reads need `contract.read`; uploads need `import.upload` (SCREENS §12.1). */
export const IMPORT_READ_PERMISSION = "contract.read";
export const IMPORT_UPLOAD_PERMISSION = "import.upload";
/** SCREENS SCR-IA-07 screen code of the imports grid. */
export const IMPORTS_SCREEN_CODE = "SF-10";
/** SCREENS §12.1 column 8 "Uploaded at": the default sort, descending. */
export const DEFAULT_IMPORT_SORT = "-created_at";
/** 04 E-51 purpose of an uploaded import file (API-R-12). */
export const IMPORT_FILE_PURPOSE = "IMPORT_SOURCE";
/** The `job.subject_type` of the import jobs (05 IPL-01, IPL-07; API-R-11 filter). */
export const IMPORT_SUBJECT_TYPE = "import_upload";
/** While a job of the import runs, the screen reads the import again at the job poll interval. */
export const IMPORT_POLL_INTERVAL_MS = 2_000;

/** E-40 literals in 04 order, the options of the Status chip. */
export const IMPORT_STATUSES: readonly ImportStatus[] = [
  "UPLOADED",
  "VALIDATING",
  "INVALID",
  "VALIDATED",
  "DIFFING",
  "DIFF_READY",
  "SUBMITTED",
  "APPROVED",
  "REJECTED",
  "COMMITTING",
  "COMMITTED",
  "FAILED",
  "CANCELLED",
];

/** SCREENS SCR-URL-15: the step slugs of RT-44, in wizard order. */
export type ImportStep = "map" | "validate" | "review" | "approval" | "committed";
export const IMPORT_STEPS: readonly ImportStep[] = [
  "map",
  "validate",
  "review",
  "approval",
  "committed",
];

export function isImportStep(value: string | undefined): value is ImportStep {
  return value !== undefined && (IMPORT_STEPS as readonly string[]).includes(value);
}

/** SCREENS §12.2 "Step redirect by status". */
export function stepOfStatus(status: ImportStatus): ImportStep {
  switch (status) {
    case "DIFFING":
    case "DIFF_READY":
      return "review";
    case "SUBMITTED":
    case "APPROVED":
    case "REJECTED":
    case "COMMITTING":
      return "approval";
    case "COMMITTED":
    case "FAILED":
      return "committed";
    default:
      // UPLOADED, VALIDATING, INVALID, VALIDATED and CANCELLED.
      return "validate";
  }
}

/** Statuses a job moves on by itself; the screen polls the import while one holds. */
export const RUNNING_STATUSES: ReadonlySet<ImportStatus> = new Set<ImportStatus>([
  "UPLOADED",
  "VALIDATING",
  "VALIDATED",
  "DIFFING",
  "APPROVED",
  "COMMITTING",
]);

/** An import still before approval, which its uploader can cancel (PRD SM-05). */
export const CANCELLABLE_STATUSES: ReadonlySet<ImportStatus> = new Set<ImportStatus>([
  "UPLOADED",
  "VALIDATING",
  "VALIDATED",
  "DIFFING",
  "DIFF_READY",
]);

export interface ImportListQuery {
  /** Repeatable `status`: several values mean IN (04 API-C-09). */
  readonly status: readonly string[];
  readonly templateCode: string | null;
  /** `created_from`: the start of the chosen day, UTC. */
  readonly createdFrom: string | null;
}

export function importsKey(query: ImportListQuery): QueryKey {
  return queryKey("imports", "tenant", {
    view: "list",
    status: query.status.join(","),
    template_code: query.templateCode,
    created_from: query.createdFrom,
  });
}

/** Every import read, for invalidation after a command. */
export const EVERY_IMPORT: QueryKey = queryKey("imports", "tenant");

/** One DataGrid page of `GET /imports` (DG-FE-07); without a URL sort, newest upload first. */
export function fetchImportsPage(
  query: ImportListQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<ImportItem>> {
  return fetchListPage<ImportItem>(
    IMPORTS_PATH,
    {
      status: query.status,
      template_code: query.templateCode,
      created_from: query.createdFrom,
      sort: sort ?? DEFAULT_IMPORT_SORT,
    },
    cursor,
  );
}

/** The SF-10:detail link of a row (RT-44 redirects to the step). */
export function importRoute(importId: string): string {
  return `/data/imports/${importId}`;
}

/** The SF-10:detail route of one step. */
export function importStepRoute(importId: string, step: ImportStep): string {
  return `/data/imports/${importId}/${step}`;
}

/** The row's business identifier: the uploaded file name, else the import number. */
export function importName(item: Pick<ImportItem, "file" | "import_no">): string {
  return item.file.original_filename ?? item.import_no;
}

export function importKey(importId: string): QueryKey {
  return queryKey("imports", "tenant", { id: importId });
}

/** `GET /imports/{id}` (API-S-Import). */
export function fetchImport(importId: string): Promise<ImportItem> {
  return unwrap(
    api.GET("/api/v1/imports/{import_id}", { params: { path: { import_id: importId } } }),
  );
}

export interface ImportRowQuery {
  /** E-41 `status`. */
  readonly status: string | null;
  /** 04 §15.4 codes of a row message (repeatable). */
  readonly codes: readonly string[];
}

export function importRowsKey(importId: string, query: ImportRowQuery): QueryKey {
  return queryKey("imports", "tenant", {
    id: importId,
    view: "rows",
    status: query.status,
    code: query.codes.join(","),
  });
}

/**
 * SCREENS §12.2 rows grid, "Errors first", as D-87 rules L6-4-Q-14: `sort=severity` lists `ERROR`,
 * `WARNING`, `VALID`, `AGGREGATED`, then `BLANK` rows, and rows of one status by row number.
 */
export const DEFAULT_ROW_SORT = "severity";

/** One DataGrid page of `GET /imports/{id}/rows` (04 API-R-43 row filters). */
export function fetchImportRowsPage(
  importId: string,
  query: ImportRowQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<ImportRow>> {
  return fetchListPage<ImportRow>(
    `${IMPORTS_PATH}/${importId}/rows`,
    { status: query.status, code: query.codes, sort: sort ?? DEFAULT_ROW_SORT },
    cursor,
  );
}

/** SCREENS §12.3: the row of the drawer, `GET /imports/{id}/rows?row_number&sheet_name`. */
export async function fetchImportRow(
  importId: string,
  rowNumber: number,
  sheetName: string | null,
): Promise<ImportRow | null> {
  const page = await fetchListPage<ImportRow>(
    `${IMPORTS_PATH}/${importId}/rows`,
    { row_number: String(rowNumber), sheet_name: sheetName },
    null,
    { limit: 1, count: false },
  );
  return page.items[0] ?? null;
}

/** The row an aggregated row was combined into: the first pages sorted by row number (L6-4-Q-15). */
export async function findImportRow(importId: string, rowId: string): Promise<ImportRow | null> {
  let cursor: string | null = null;
  for (let page = 0; page < 5; page += 1) {
    const result: ListPage<ImportRow> = await fetchListPage<ImportRow>(
      `${IMPORTS_PATH}/${importId}/rows`,
      { sort: "row_number" },
      cursor,
      { limit: 200, count: false },
    );
    const found = result.items.find((row) => row.id === rowId);
    if (found !== undefined) {
      return found;
    }
    cursor = result.nextCursor;
    if (cursor === null) {
      break;
    }
  }
  return null;
}

export function importDiffKey(importId: string): QueryKey {
  return queryKey("imports", "tenant", { id: importId, view: "diff" });
}

/** `GET /imports/{id}/diff` (API-S-ImportDiff; available from DIFF_READY). */
export function fetchImportDiff(importId: string): Promise<ImportDiff> {
  return unwrap(
    api.GET("/api/v1/imports/{import_id}/diff", { params: { path: { import_id: importId } } }),
  );
}

export function importJobsKey(importId: string): QueryKey {
  return queryKey("jobs", "tenant", { subject_type: IMPORT_SUBJECT_TYPE, subject_id: importId });
}

/**
 * The jobs of an import, newest first (API-R-11 `GET /jobs?subject_type&subject_id`): validation,
 * the dry run and the commit. The screen shows the newest one while the import moves on by itself.
 * Null when the API refuses the read of the jobs (SCREENS §0.6 SCR-PERM-02): the screen shows its
 * stand-in and does not ask again.
 */
export async function fetchImportJobs(importId: string): Promise<readonly Job[] | null> {
  try {
    const page = await fetchListPage<Job>(
      JOBS_PATH,
      { subject_type: IMPORT_SUBJECT_TYPE, subject_id: importId, sort: "-created_at" },
      null,
      { limit: 10, count: false },
    );
    return page.items;
  } catch (error) {
    if (isRefused(error)) {
      return null;
    }
    throw error;
  }
}

/**
 * `GET /imports/{id}/error-report` saved as `<import number>-error-report.csv` (04 §16.6: `row, column,
 * rule_id, message`). Throws the `ApiProblem` of a refused download.
 */
export async function downloadErrorReport(
  item: Pick<ImportItem, "id" | "import_no">,
): Promise<void> {
  const response = await send("GET", `${IMPORTS_PATH}/${item.id}/error-report`);
  if (!response.ok) {
    throw await readProblem(response);
  }
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${item.import_no}-error-report.csv`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** One line of the error report (04 §16.6). */
export interface ReportedFinding {
  readonly row: string;
  readonly column: string;
  readonly ruleId: string;
  readonly message: string;
}

/** RFC 4180 records of a CSV text. */
export function parseCsv(text: string): string[][] {
  const records: string[][] = [];
  let field = "";
  let fields: string[] = [];
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text.charAt(index);
    if (quoted) {
      if (char === '"' && text.charAt(index + 1) === '"') {
        field += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      fields.push(field);
      field = "";
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && text.charAt(index + 1) === "\n") {
        index += 1;
      }
      fields.push(field);
      records.push(fields);
      fields = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (field !== "" || fields.length > 0) {
    fields.push(field);
    records.push(fields);
  }
  return records;
}

export function fileFindingsKey(importId: string): QueryKey {
  return queryKey("imports", "tenant", { id: importId, view: "file-findings" });
}

/**
 * The file-level findings of an import (a blank row), read from the error report: 04 API-S-Import
 * names only the codes (`finding_counts`), and `GET /imports/{id}/rows` holds row messages only
 * (L6-4-Q-17). The report lists them first.
 */
export async function fetchFileFindings(importId: string): Promise<readonly ReportedFinding[]> {
  const response = await send("GET", `${IMPORTS_PATH}/${importId}/error-report`);
  if (!response.ok) {
    throw await readProblem(response);
  }
  const [, ...lines] = parseCsv(await response.text());
  return lines
    .map(([row = "", column = "", ruleId = "", message = ""]) => ({ row, column, ruleId, message }))
    .filter((finding) => finding.row === "" && finding.ruleId !== "");
}

/** 04 API-S-Import `diff_summary` (REQ-DAT-015). */
export interface DiffSummary {
  readonly contractsAffected: number;
  readonly contractsCreated: number;
  readonly allocationChanges: readonly {
    readonly contract: string;
    readonly before: string | null;
    readonly after: string | null;
  }[];
  readonly revenueByPeriod: readonly { readonly periodKey: string; readonly amount: string }[];
  readonly journalPreview: readonly {
    readonly accountRole: string;
    readonly debit: string | null;
    readonly credit: string | null;
  }[];
}

function record(value: unknown): Readonly<Record<string, unknown>> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Readonly<Record<string, unknown>>)
    : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function count(value: unknown): number {
  return typeof value === "number" && Number.isSafeInteger(value) ? value : 0;
}

function entries(value: unknown): readonly Readonly<Record<string, unknown>>[] {
  return Array.isArray(value)
    ? value.map(record).filter((item): item is Readonly<Record<string, unknown>> => item !== null)
    : [];
}

/** The typed `diff_summary`, or null before the dry run. */
export function diffSummaryOf(item: Pick<ImportItem, "diff_summary">): DiffSummary | null {
  const summary = record(item.diff_summary);
  if (summary === null) {
    return null;
  }
  return {
    contractsAffected: count(summary.contracts_affected),
    contractsCreated: count(summary.contracts_created),
    allocationChanges: entries(summary.allocation_changes).map((entry) => ({
      contract: text(entry.contract_external_id) ?? "",
      before: text(entry.before),
      after: text(entry.after),
    })),
    revenueByPeriod: entries(summary.revenue_by_period_delta).map((entry) => ({
      periodKey: text(entry.period_key) ?? "",
      amount: text(entry.amount) ?? "0",
    })),
    journalPreview: entries(summary.journal_preview).map((entry) => ({
      accountRole: text(entry.account_role) ?? "",
      debit: text(entry.debit),
      credit: text(entry.credit),
    })),
  };
}

/** 05 IPL-06 `control_totals.source` or `.loaded`. */
export interface ControlTotalsSide {
  readonly rows: number;
  readonly amountSums: Readonly<Record<string, string>>;
}

export interface ControlTotals {
  readonly source: ControlTotalsSide | null;
  readonly loaded: ControlTotalsSide | null;
}

function side(value: unknown): ControlTotalsSide | null {
  const found = record(value);
  if (found === null) {
    return null;
  }
  const sums = record(found.amount_sums) ?? {};
  return {
    rows: count(found.rows),
    amountSums: Object.fromEntries(
      Object.entries(sums).flatMap(([name, amount]) =>
        typeof amount === "string" ? [[name, amount]] : [],
      ),
    ),
  };
}

export function controlTotalsOf(item: Pick<ImportItem, "control_totals">): ControlTotals | null {
  const totals = record(item.control_totals);
  return totals === null ? null : { source: side(totals.source), loaded: side(totals.loaded) };
}

/** True when the loaded totals differ from the source totals (PRD IMP-43). */
export function totalsMismatch(totals: ControlTotals | null): boolean {
  if (totals?.source == null || totals.loaded === null) {
    return false;
  }
  const { source, loaded } = totals;
  const names = new Set([...Object.keys(source.amountSums), ...Object.keys(loaded.amountSums)]);
  return (
    source.rows !== loaded.rows ||
    [...names].some((name) => source.amountSums[name] !== loaded.amountSums[name])
  );
}
