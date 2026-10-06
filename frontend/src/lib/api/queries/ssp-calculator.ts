// Historical SSP calculator (04 API-R-27 `GET, POST /ssp-calculator-runs`, `GET
// /ssp-calculator-runs/{id}`, `GET …/results`, `GET …/observations` (§16.14), `POST …/exclusions`,
// `POST …/create-draft-version`; API-R-12 `POST /files` purpose `IMPORT_SOURCE`, `GET /files/{id}`;
// T-REF-32 to T-REF-34; SCREENS §11.5; BUILD_SPEC RFD-24). Statistics stay API-C-06 strings; only
// histogram counts, which are integers, size the bars (DG-FE-08).
import { useQuery } from "@tanstack/react-query";

import { formatNumber, NO_VALUE, registerCurrencies } from "../../format";
import { api, unwrap } from "../client";
import { fetchListPage, type ListPage } from "../lists";
import { ApiProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { CURRENCIES_PATH, currencyRegistered } from "./approvals";

export type SspCalculatorRun = components["schemas"]["SspCalculatorRunOut"];
export type SspCalculatorResult = components["schemas"]["SspCalculatorResultOut"];
export type SspCalculatorObservation = components["schemas"]["SspCalculatorObservationOut"];
export type HistogramBin = components["schemas"]["SspCalculatorHistogramBinOut"];
export type RunStatus = components["schemas"]["RunStatus"];
export type CalculatorSource = SspCalculatorRun["parameters"]["source"];
export type Product = components["schemas"]["ProductOut"];
export type TenantCurrency = components["schemas"]["TenantCurrencyOut"];
export type StoredFileMeta = components["schemas"]["FileOut"];
export type Currency = components["schemas"]["CurrencyOut"];

export const SSP_CALCULATOR_RUNS_PATH = "/api/v1/ssp-calculator-runs";
export const PRODUCTS_PATH = "/api/v1/products";
export const TENANT_CURRENCIES_PATH = "/api/v1/tenant-currencies";
/** L2-1-Q-52: the 202 answer of `POST /ssp-calculator-runs` names the run in this header. */
export const RUN_ID_HEADER = "X-Erev-Ssp-Calculator-Run-Id";
/** API-R-12: the pool file of an uploaded source is an `IMPORT_SOURCE` CSV (L2-1-Q-53). */
export const POOL_FILE_PURPOSE = "IMPORT_SOURCE";
export const POOL_UPLOAD_PERMISSION = "import.upload";
/** SCREENS §11.5 "New run": 50 MiB pool files (04 T-PLT-29). */
export const POOL_MAX_BYTES = 50 * 1024 * 1024;
export const SOURCES: readonly CalculatorSource[] = ["source_order_lines", "committed_obligations"];
/** SCREENS §11.5: the run page polls a queued or running run. */
export const RUN_POLL_INTERVAL_MS = 2_000;
/** SCREENS §11.5 "Runs" panel: the newest runs. */
export const RUNS_PANEL_LIMIT = 50;
/** SCREENS §11.5 exclude modal: a reason of at least 10 characters. */
export const EXCLUSION_REASON_MIN = 10;

export const EVERY_SSP_RUN: QueryKey = queryKey("ssp-calculator-runs", "tenant");

export function sspRunsKey(): QueryKey {
  return queryKey("ssp-calculator-runs", "tenant", { view: "panel" });
}

export function sspRunKey(runId: string): QueryKey {
  return queryKey("ssp-calculator-runs", "tenant", { id: runId });
}

export function sspResultsKey(runId: string): QueryKey {
  return queryKey("ssp-calculator-runs", "tenant", { id: runId, view: "results" });
}

export function sspObservationsKey(runId: string): QueryKey {
  return queryKey("ssp-calculator-runs", "tenant", { id: runId, view: "observations" });
}

export function productsKey(): QueryKey {
  return queryKey("products", "tenant", { is_active: true });
}

export function tenantCurrenciesKey(): QueryKey {
  return queryKey("tenant-currencies", "tenant", { is_enabled: true });
}

export function fileKey(fileId: string): QueryKey {
  return queryKey("files", "tenant", { id: fileId });
}

/** RT-68 SF-13:ssp-calculator-run. */
export function sspRunRoute(runId: string): string {
  return `/policies/ssp-calculator/runs/${runId}`;
}

export function sspRunPath(runId: string): string {
  return `${SSP_CALCULATOR_RUNS_PATH}/${runId}`;
}

export function isActiveRun(status: RunStatus): boolean {
  return status === "QUEUED" || status === "RUNNING";
}

/** The newest runs of the "Runs" panel. */
export async function fetchSspRuns(): Promise<readonly SspCalculatorRun[]> {
  const page = await fetchListPage<SspCalculatorRun>(
    SSP_CALCULATOR_RUNS_PATH,
    { sort: "-created_at" },
    null,
    { limit: RUNS_PANEL_LIMIT, count: false },
  );
  return page.items;
}

export function fetchSspRun(runId: string): Promise<SspCalculatorRun> {
  return unwrap(
    api.GET("/api/v1/ssp-calculator-runs/{run_id}", { params: { path: { run_id: runId } } }),
  );
}

async function fetchAll<T>(path: string, query: Readonly<Record<string, string | boolean>>) {
  const items: T[] = [];
  let cursor: string | null = null;
  do {
    const page: ListPage<T> = await fetchListPage<T>(path, query, cursor, { count: false });
    items.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor !== null);
  return items;
}

/** Every result of a run in product order. */
export function fetchSspResults(runId: string): Promise<readonly SspCalculatorResult[]> {
  return fetchAll<SspCalculatorResult>(`${sspRunPath(runId)}/results`, { sort: "product_code" });
}

/** One DataGrid page of observations; their order is fixed by date (04 §16.14). */
export function fetchObservationsPage(
  runId: string,
  cursor: string | null,
): Promise<ListPage<SspCalculatorObservation>> {
  return fetchListPage<SspCalculatorObservation>(`${sspRunPath(runId)}/observations`, {}, cursor);
}

/** The active products in code order (the "Products" multi-select). */
export function fetchActiveProducts(): Promise<readonly Product[]> {
  return fetchAll<Product>(PRODUCTS_PATH, { is_active: true, sort: "code" });
}

/** The enabled currencies of the workspace (the "Currency" select). */
export async function fetchTenantCurrencies(): Promise<readonly TenantCurrency[]> {
  const items = await fetchAll<TenantCurrency>(TENANT_CURRENCIES_PATH, {});
  return items.filter((item) => item.is_enabled);
}

export function fetchFileMeta(fileId: string): Promise<StoredFileMeta> {
  return unwrap(api.GET("/api/v1/files/{file_id}", { params: { path: { file_id: fileId } } }));
}

/** A ratio such as "0.150000" as percent figures with trailing zeros trimmed: "15", "12.5". */
export function ratioPercentFigures(ratio: string): string {
  const match = /^(\d+)(?:\.(\d+))?$/.exec(ratio);
  if (match === null) {
    return NO_VALUE;
  }
  const fraction = (match[2] ?? "").padEnd(2, "0");
  const integer = `${match[1] ?? "0"}${fraction.slice(0, 2)}`.replace(/^0+(?=\d)/, "");
  const rest = fraction.slice(2).replace(/0+$/, "");
  return formatNumber(rest === "" ? integer : `${integer}.${rest}`, { kind: "quantity" });
}

/**
 * Registers the minor units of `codes` from `GET /currencies` (DS-FMT-03, DS-I18N-09): figures in a
 * currency render only once the API currency reference holds it. True when every code is registered.
 */
export async function registerCurrencyCodes(codes: readonly string[]): Promise<boolean> {
  const missing = [...new Set(codes)].filter((code) => !currencyRegistered(code));
  if (missing.length > 0) {
    try {
      const page = await fetchListPage<Currency>(CURRENCIES_PATH, { code: missing }, null, {
        limit: 200,
        count: false,
      });
      registerCurrencies(page.items);
    } catch (error) {
      if (!(error instanceof ApiProblem && error.status === 403)) {
        throw error;
      }
    }
  }
  return missing.every(currencyRegistered);
}

/** The currency reference of `codes`; `data` is defined once the read has run. */
export function useCurrencyReference(codes: readonly string[]) {
  const sorted = [...new Set(codes)].sort();
  return useQuery({
    queryKey: queryKey("currencies", "tenant", { codes: sorted.join(",") }),
    queryFn: () => registerCurrencyCodes(sorted),
    staleTime: Number.POSITIVE_INFINITY,
  });
}
