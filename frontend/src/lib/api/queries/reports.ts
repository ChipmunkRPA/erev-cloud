// Report definitions, report runs, run data and report cell explanations (04 §15.3 API-R-41, API-R-49,
// §16.9 API-S-ReportDefinition, API-S-ReportRun; SCREENS_B §0.5 RV-01 to RV-14, §5.1, §5.2, SB-R-07;
// BUILD_SPEC RPS-6). `POST /report-runs` answers 202 with the job in `Location` and the run id in
// `X-Erev-Report-Run-Id` ([J] L5-2-Q-12). `GET /report-runs/{id}/data` takes no filter, sort or search
// and keeps the response order; the viewer reads every 200-row page, because sections and totals
// rows are row fields (RPT-R-09) that 04 defines no parameter for. Every page also carries the run's
// `columns` in builder order (D-88 L7-1-Q-5). `GET /report-runs` admits the filters `report_code`,
// `status`, `created_from` (inclusive) and `created_to` (exclusive) and sorts by `id` (default, newest
// first) or `created_at`; it has no search (SCREENS_B §5.3; BUILD_SPEC RPS-18). The report routes admit a
// holder of `report.run` or `audit.read` and list the runs that caller may see (04 API-R-41 rev 1.128).
import type { Access } from "../../access";
import { send } from "../client";
import { fetchListPage, GRID_PAGE_SIZE, type ListPage, listSearch } from "../lists";
import { readProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { ensureCurrencyCodes } from "./journal-runs";

export type ReportDefinition = components["schemas"]["ReportDefinitionOut"];
export type ReportRun = components["schemas"]["ReportRunOut"];
export type ReportRow = components["schemas"]["ReportRowOut"];
export type ReportRunData = components["schemas"]["ReportRunDataOut"];
export type ReportRunColumn = components["schemas"]["ReportColumnOut"];
export type TieOutResult = components["schemas"]["TieOutResultOut"];
export type ReportCell = components["schemas"]["ExplainCellOut"];
export type ReportCellContributor = components["schemas"]["ExplainCellContributorOut"];
export type ReportOutputFormat = components["schemas"]["OutputFormat"];

export const REPORT_DEFINITIONS_PATH = "/api/v1/report-definitions";
export const REPORT_RUNS_PATH = "/api/v1/report-runs";
export const REPORT_CELL_PATH = "/api/v1/explain/report-runs";
/** [J] L5-2-Q-12: the run a 202 answer created. */
export const REPORT_RUN_ID_HEADER = "X-Erev-Report-Run-Id";
export const REPORT_RUN_PERMISSION = "report.run";
export const REPORT_EXPORT_PERMISSION = "report.export";
/** SCREENS RT-31 SF-08 and RT-32 SF-08:report. */
export const REPORTS_ROUTE = "/reports";
export const REPORT_ROUTE = "/reports/:reportCode";
/** SCREENS RT-106 SF-08:runs and RT-33 SF-08:run. */
export const REPORT_RUNS_ROUTE = "/reports/runs";
export const REPORT_RUN_ROUTE = "/reports/runs/:runId";
/** 04 API-R-41 (rev 1.128): a report is run, read and listed under `report.run` or `audit.read`. */
const AUDIT_READ_PERMISSION = "audit.read";

export function reportRunRoute(runId: string): string {
  return `${REPORT_RUNS_ROUTE}/${runId}`;
}

/** Who the report routes admit; which runs that caller sees is the API's decision per report. */
export function mayReadReportRuns(access: Access): boolean {
  return access.holdsAnywhere(REPORT_RUN_PERMISSION) || access.holdsAnywhere(AUDIT_READ_PERMISSION);
}

/**
 * Who reads the job of a run (04 API-R-11: a job's owner or a holder of `audit.read`). The jobs of
 * other members are a list of the whole workspace, read with `audit.read` for all entities (ruling
 * R-28; SCREENS §0.6 SCR-PERM-02 (c)). Another reader of the run is answered 404 for its job, so a
 * screen does not ask for it.
 */
export function mayReadRunJob(
  run: Pick<ReportRun, "run_by">,
  userId: string,
  access: Access,
): boolean {
  return run.run_by.id === userId || access.holdsForAll(AUDIT_READ_PERMISSION);
}

/** E-67 run states that are still computing. */
const RUNNING_STATES: ReadonlySet<string> = new Set(["QUEUED", "RUNNING"]);

export function isRunning(run: Pick<ReportRun, "status"> | undefined): boolean {
  return run !== undefined && RUNNING_STATES.has(run.status);
}

/** Invalidates every report run read. */
export const EVERY_REPORT_RUN: QueryKey = queryKey("report-runs", "tenant");

export function reportDefinitionsKey(): QueryKey {
  return queryKey("report-definitions", "tenant");
}

export function reportDefinitionKey(code: string): QueryKey {
  return queryKey("report-definitions", "tenant", { code });
}

export function reportRunKey(runId: string): QueryKey {
  return queryKey("report-runs", "tenant", { id: runId });
}

export function reportRowsKey(runId: string): QueryKey {
  return queryKey("report-run-data", "tenant", { id: runId });
}

export function recentReportRunsKey(createdFrom: string): QueryKey {
  return queryKey("report-runs", "tenant", { createdFrom, recent: true });
}

export function reportCellKey(runId: string, rowKey: string, columnKey: string): QueryKey {
  return queryKey("report-cell", "tenant", { runId, rowKey, columnKey });
}

async function read<T>(path: string): Promise<T> {
  const response = await send("GET", path);
  if (!response.ok) {
    throw await readProblem(response);
  }
  return (await response.json()) as T;
}

/** `GET /report-definitions`: the current definitions in catalogue order (REQ-RPT-001). */
export async function fetchReportDefinitions(): Promise<readonly ReportDefinition[]> {
  const body = await read<{ readonly items: readonly ReportDefinition[] }>(REPORT_DEFINITIONS_PATH);
  return body.items;
}

/** `GET /report-definitions/{code}`; an unknown code answers 404 (SCR-ST-07). */
export function fetchReportDefinition(code: string): Promise<ReportDefinition> {
  return read<ReportDefinition>(`${REPORT_DEFINITIONS_PATH}/${encodeURIComponent(code)}`);
}

/** The currencies of every API-S-Money inside `value`, so amounts can be formatted (DS-FMT-03). */
export function moneyCurrencies(value: unknown, found: Set<string> = new Set()): Set<string> {
  if (Array.isArray(value)) {
    for (const item of value) {
      moneyCurrencies(item, found);
    }
  } else if (typeof value === "object" && value !== null) {
    const record = value as Readonly<Record<string, unknown>>;
    if (typeof record.amount === "string" && typeof record.currency === "string") {
      found.add(record.currency);
    } else {
      for (const item of Object.values(record)) {
        moneyCurrencies(item, found);
      }
    }
  }
  return found;
}

export async function fetchReportRun(runId: string): Promise<ReportRun> {
  const run = await read<ReportRun>(`${REPORT_RUNS_PATH}/${runId}`);
  await ensureCurrencyCodes(moneyCurrencies(run.tie_out_results));
  return run;
}

/** The rows of a run and the columns of its stored dataset document (D-88 L7-1-Q-5). */
export interface ReportRunRows {
  readonly rows: readonly ReportRow[];
  /** The definition's columns in builder order, which is the output order, from the first page. */
  readonly columns: readonly ReportRunColumn[];
}

/**
 * Every row of a SUCCEEDED JSON run, read in 200-row pages in response order (RV-11), with the first page's
 * `columns`. The data response is API-S-List plus `columns` (04 §16.9; D-88 L7-1-Q-5), so it has its own
 * page reader rather than `fetchListPage`.
 */
export async function fetchReportRows(runId: string): Promise<ReportRunRows> {
  const rows: ReportRow[] = [];
  let columns: readonly ReportRunColumn[] | null = null;
  let cursor: string | null = null;
  do {
    const page: ReportRunData = await read<ReportRunData>(
      `${REPORT_RUNS_PATH}/${runId}/data${listSearch({ limit: GRID_PAGE_SIZE, cursor })}`,
    );
    rows.push(...page.items);
    columns ??= page.columns;
    cursor = page.next_cursor;
  } while (cursor !== null);
  await ensureCurrencyCodes(moneyCurrencies(rows));
  return { rows, columns: columns ?? [] };
}

/**
 * SF-08 "Recent runs": runs created since `createdFrom`, newest first (API-C-09 default order). 04
 * defines no creator filter, so the screen keeps the viewer's runs (SCREENS_B §5.1 data bindings).
 */
export async function fetchRecentReportRuns(createdFrom: string): Promise<readonly ReportRun[]> {
  const page = await fetchListPage<ReportRun>(
    REPORT_RUNS_PATH,
    { created_from: createdFrom },
    null,
    { limit: 50, count: false },
  );
  return page.items;
}

/** SF-08:runs: the filters of the register as API-R-41 takes them. */
export interface ReportRunQuery {
  readonly reportCodes: readonly string[];
  readonly statuses: readonly string[];
  /** The first instant of the range, inclusive. */
  readonly createdFrom: string | null;
  /** The first instant after the range: the API's `created_to` is exclusive. */
  readonly createdTo: string | null;
}

export function reportRunsKey(query: ReportRunQuery): QueryKey {
  return queryKey("report-runs", "tenant", {
    register: true,
    report: query.reportCodes.join(","),
    status: query.statuses.join(","),
    createdFrom: query.createdFrom,
    createdTo: query.createdTo,
  });
}

/** One page of `GET /report-runs`, newest first, with the currencies of the runs' tie-outs. */
export async function fetchReportRunsPage(
  query: ReportRunQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<ReportRun>> {
  const page = await fetchListPage<ReportRun>(
    REPORT_RUNS_PATH,
    {
      report_code: query.reportCodes.length === 0 ? null : query.reportCodes,
      status: query.statuses.length === 0 ? null : query.statuses,
      created_from: query.createdFrom,
      created_to: query.createdTo,
      sort,
    },
    cursor,
  );
  await ensureCurrencyCodes(moneyCurrencies(page.items.map((run) => run.tie_out_results)));
  return page;
}

/** SB-R-07: `GET /explain/report-runs/{id}/cell` lists the records behind one report figure. */
export async function fetchReportCell(
  runId: string,
  rowKey: string,
  columnKey: string,
): Promise<ReportCell> {
  const search = listSearch({ row_key: rowKey, column_key: columnKey });
  const cell = await read<ReportCell>(`${REPORT_CELL_PATH}/${runId}/cell${search}`);
  await ensureCurrencyCodes(moneyCurrencies(cell));
  return cell;
}

/** RV-06: the output of a file run, downloaded as an attachment (`report.export`). */
export function reportOutputHref(runId: string): string {
  return `${REPORT_RUNS_PATH}/${runId}/output`;
}
