// Integration connections, sync runs and external ids (04 §15.3 API-R-45; §16.14 API-S-IntegrationConnection,
// API-S-SyncRun, API-S-ExternalIdMap; T-INT-01, T-INT-02, T-INT-04; E-72; API-R-44 `GET /exceptions`;
// SCREENS §14.1 to §14.9; BUILD_SPEC DIN-18). Every route takes `integration.manage`. A connection
// carries `secret_ref`, the name of its credential, and never a secret value (REQ-INT-006); the name is
// one of the workspace's own namespace of the secret store, `tenant-<tenant id>-…` (T-INT-01 rev 1.108),
// and any other is refused at save with 422 on `secret_ref`.
// `POST /integrations/{id}/test` answers 200 with the connection and its `last_test_*`; `POST
// /integrations/{id}/sync` answers 202 with the job in `Location` and the run in `X-Erev-Sync-Run-Id`;
// `PATCH /integrations/{id}` needs `If-Match` with the row version. A sync run's `source_totals` and
// `loaded_totals` are `{count, amount_by_currency, sha256}`; whether they agree is the run's `status`
// (`SUCCEEDED` or `CONTROL_TOTAL_MISMATCH`), which the screens show and never work out again.
// `GET /sync-runs` sorts by `created_at` (default, newest first), `finished_at` or `id`.
import { send } from "../client";
import { fetchListPage, type ListPage } from "../lists";
import { readProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { ensureCurrencyCodes } from "./approvals";
import type { ExceptionItem } from "./exceptions";
import type { MeMembership } from "./me";

export type Connection = components["schemas"]["IntegrationConnectionOut"];
export type ConnectionCreate = components["schemas"]["IntegrationConnectionIn"];
export type ConnectionUpdate = components["schemas"]["IntegrationConnectionUpdateIn"];
export type SyncRun = components["schemas"]["SyncRunOut"];
export type SyncRequest = components["schemas"]["SyncRequestIn"];
export type SyncRunStatus = components["schemas"]["SyncRunStatus"];
export type ExternalId = components["schemas"]["ExternalIdMapOut"];
export type Adapter = Connection["adapter"];
export type Direction = Connection["direction"];
export type SyncRunKind = SyncRun["kind"];

export const INTEGRATIONS_PATH = "/api/v1/integrations";
export const SYNC_RUNS_PATH = "/api/v1/sync-runs";
export const EXTERNAL_IDS_PATH = "/api/v1/external-ids";
const EXCEPTIONS_PATH = "/api/v1/exceptions";
export const INTEGRATION_MANAGE_PERMISSION = "integration.manage";
/** SCREENS RT-48 SF-16, RT-49 SF-16:connection and RT-50 SF-16:sync-run. */
export const INTEGRATIONS_ROUTE = "/data/integrations";
export const CONNECTION_ROUTE = "/data/integrations/:connectionId";
export const SYNC_RUN_ROUTE = "/data/integrations/:connectionId/sync-runs/:syncRunId";
/** SCREENS SCR-IA-07 saved-view code of the sync runs grid. */
export const SYNC_RUNS_SCREEN_CODE = "SF-16#sync-runs";
/** The run a 202 answer of `POST /integrations/{id}/sync` queued. */
export const SYNC_RUN_ID_HEADER = "X-Erev-Sync-Run-Id";
/** SCREENS §14.3: a connection whose `base_url` path starts here talks to an in-process mock adapter. */
export const MOCK_BASE_URL_PREFIX = "/api/v1/__mocks__/";
/**
 * 04 T-INT-01 rev 1.108 (ruling R-48 (f)): the workspace's own namespace of the secret store — what
 * the name of every secret a connection of the workspace references begins with; the workspace's id
 * in its lower-case form.
 */
export function secretNamespace(tenantId: string): string {
  return `tenant-${tenantId.toLowerCase()}-`;
}

/**
 * The namespace of the workspace the session is in — `open` is its membership as the shell names
 * it, by the session's workspace (`app/shell/open-workspace.ts`): a sandbox copy holds its
 * source's membership id and its own namespace — or null without an open workspace.
 */
export function secretNamespaceOf(open: MeMembership | null): string | null {
  return open === null ? null : secretNamespace(open.tenant.id);
}

/** SCREENS §14.3 column 2, in the order of the adapter select. */
export const ADAPTERS: readonly Adapter[] = [
  "SALESFORCE",
  "STRIPE",
  "NETSUITE",
  "QUICKBOOKS_ONLINE",
  "CSV_GL",
];
export const DIRECTIONS: readonly Direction[] = ["INBOUND", "OUTBOUND", "BOTH"];
/** SCREENS §14.4 "Direction": the default of each adapter. */
export const DEFAULT_DIRECTION: Readonly<Record<Adapter, Direction>> = {
  SALESFORCE: "INBOUND",
  STRIPE: "INBOUND",
  NETSUITE: "BOTH",
  QUICKBOOKS_ONLINE: "OUTBOUND",
  CSV_GL: "OUTBOUND",
};
/** 05 SBX-08: a CRM or billing adapter, and an inbound or two-way direction, make a connection inbound. */
const INBOUND_ADAPTERS: ReadonlySet<Adapter> = new Set<Adapter>(["SALESFORCE", "STRIPE"]);
const INBOUND_DIRECTIONS: ReadonlySet<Direction> = new Set<Direction>(["INBOUND", "BOTH"]);
/**
 * SB-R-08 (SCREENS §14.4): what "Add connection" offers in a sandbox workspace. `POST /integrations`
 * answers 403 `sandbox-restricted` there for an inbound connection, so these are the rest.
 */
export const SANDBOX_ADAPTERS: readonly Adapter[] = ADAPTERS.filter(
  (value) => !INBOUND_ADAPTERS.has(value),
);
export const SANDBOX_DIRECTIONS: readonly Direction[] = DIRECTIONS.filter(
  (value) => !INBOUND_DIRECTIONS.has(value),
);
export const SYNC_RUN_STATUSES: readonly SyncRunStatus[] = [
  "QUEUED",
  "RUNNING",
  "SUCCEEDED",
  "CONTROL_TOTAL_MISMATCH",
  "FAILED",
];
export const SYNC_RUN_KINDS: readonly SyncRunKind[] = [
  "INBOUND_POLL",
  "WEBHOOK_BATCH",
  "RECONCILIATION_SWEEP",
  "COA_SYNC",
  "TRIAL_BALANCE_PULL",
  "JOURNAL_EXPORT",
  "TEST_CONNECTION",
];
/** E-72 states of a run that is still to finish. */
const OPEN_STATUSES: ReadonlySet<SyncRunStatus> = new Set<SyncRunStatus>(["QUEUED", "RUNNING"]);
const EXCEPTION_ROWS = 200;

/** Invalidates every connection read and every sync run read. */
export const EVERY_INTEGRATION: QueryKey = queryKey("integrations", "tenant");
export const EVERY_SYNC_RUN: QueryKey = queryKey("sync-runs", "tenant");

export function connectionRoute(connectionId: string): string {
  return `${INTEGRATIONS_ROUTE}/${connectionId}`;
}

export function syncRunRoute(connectionId: string, syncRunId: string): string {
  return `${connectionRoute(connectionId)}/sync-runs/${syncRunId}`;
}

export function connectionPath(connectionId: string): string {
  return `${INTEGRATIONS_PATH}/${connectionId}`;
}

/**
 * SCREENS §14.3 column 2: the path of `base_url` begins with the prefix of the mock routers. In a
 * running stack the value is an address (the API's own origin, then the path: the adapter client
 * connects to an absolute address, 05 ADP-14); the in-process test client takes the bare path.
 */
export function isMock(connection: Pick<Connection, "base_url">): boolean {
  const value = connection.base_url;
  if (value === null) {
    return false;
  }
  let path = value;
  try {
    path = new URL(value).pathname;
  } catch {
    // Not an address: the value is read as the path it is.
  }
  return path.startsWith(MOCK_BASE_URL_PREFIX);
}

export function isOpen(run: Pick<SyncRun, "status">): boolean {
  return OPEN_STATUSES.has(run.status);
}

/**
 * The run kinds "Run sync" offers for a connection (SCREENS §14.4), limited to the kinds API-R-45 queues
 * in 1.0: an inbound poll and a reconciliation sweep of a Salesforce or Stripe connection that reads,
 * and the chart-of-accounts sync of a NetSuite connection. A webhook batch is created by the receiver
 * and a test by "Test connection".
 */
export function requestableKinds(
  connection: Pick<Connection, "adapter" | "direction">,
): readonly SyncRunKind[] {
  if (connection.adapter === "NETSUITE") {
    return ["COA_SYNC"];
  }
  const inbound = connection.adapter === "SALESFORCE" || connection.adapter === "STRIPE";
  return inbound && connection.direction !== "OUTBOUND"
    ? ["INBOUND_POLL", "RECONCILIATION_SWEEP"]
    : [];
}

/** T-INT-02 control totals: the number of records and the amount of each currency. */
export interface ControlTotals {
  readonly count: number;
  readonly amounts: readonly { readonly currency: string; readonly amount: string }[];
}

/** `source_totals` or `loaded_totals` as recorded; null when the run recorded none. */
export function controlTotals(
  value: Readonly<Record<string, unknown>> | null,
): ControlTotals | null {
  if (value === null || typeof value.count !== "number") {
    return null;
  }
  const amounts = value.amount_by_currency;
  return {
    count: value.count,
    amounts:
      typeof amounts === "object" && amounts !== null
        ? Object.entries(amounts as Readonly<Record<string, unknown>>)
            .filter((entry): entry is [string, string] => typeof entry[1] === "string")
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([currency, amount]) => ({ currency, amount }))
        : [],
  };
}

function totalsCurrencies(run: Pick<SyncRun, "source_totals" | "loaded_totals">): string[] {
  return [run.source_totals, run.loaded_totals].flatMap((totals) =>
    (controlTotals(totals)?.amounts ?? []).map((item) => item.currency),
  );
}

async function readJson<T>(path: string): Promise<T> {
  const response = await send("GET", path);
  if (!response.ok) {
    throw await readProblem(response);
  }
  return (await response.json()) as T;
}

export function connectionsKey(): QueryKey {
  return queryKey("integrations", "tenant", { view: "list" });
}

/** One page of `GET /integrations`; without a URL sort the API's `code` order applies. */
export function fetchConnectionsPage(
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<Connection>> {
  return fetchListPage<Connection>(INTEGRATIONS_PATH, { sort }, cursor);
}

export function connectionKey(connectionId: string): QueryKey {
  return queryKey("integrations", "tenant", { id: connectionId });
}

/** `GET /integrations/{id}`; an unknown id answers 404 (SCR-ST-07). */
export function fetchConnection(connectionId: string): Promise<Connection> {
  return readJson<Connection>(connectionPath(connectionId));
}

export interface SyncRunQuery {
  readonly connectionId: string;
  readonly status: readonly string[];
  readonly kind: string | null;
}

export function syncRunsKey(query: SyncRunQuery): QueryKey {
  return queryKey("sync-runs", "tenant", {
    connection: query.connectionId,
    status: query.status.join(","),
    kind: query.kind,
  });
}

/** One page of `GET /sync-runs?connection=<id>`, newest first, with the currencies of its totals. */
export async function fetchSyncRunsPage(
  query: SyncRunQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<SyncRun>> {
  const page = await fetchListPage<SyncRun>(
    SYNC_RUNS_PATH,
    {
      connection: query.connectionId,
      status: query.status.length === 0 ? null : query.status,
      kind: query.kind,
      sort,
    },
    cursor,
  );
  await ensureCurrencyCodes(page.items.flatMap(totalsCurrencies));
  return page;
}

export function syncRunKey(syncRunId: string): QueryKey {
  return queryKey("sync-runs", "tenant", { id: syncRunId });
}

/** `GET /sync-runs/{id}` with the currencies of its totals registered (DS-FMT-03). */
export async function fetchSyncRun(syncRunId: string): Promise<SyncRun> {
  const run = await readJson<SyncRun>(`${SYNC_RUNS_PATH}/${syncRunId}`);
  await ensureCurrencyCodes(totalsCurrencies(run));
  return run;
}

export function externalIdsKey(connectionId: string): QueryKey {
  return queryKey("external-ids", "tenant", { connection: connectionId });
}

/** One page of `GET /external-ids?connection=<id>`, newest first. */
export function fetchExternalIdsPage(
  connectionId: string,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<ExternalId>> {
  return fetchListPage<ExternalId>(EXTERNAL_IDS_PATH, { connection: connectionId, sort }, cursor);
}

export function syncRunExceptionsKey(syncRunId: string): QueryKey {
  return queryKey("exceptions", "tenant", { view: "sync-run", sync_run_id: syncRunId });
}

/** SCREENS §14.5 "Exceptions": `GET /exceptions?source=SYNC&sync_run_id=<id>` (04 API-R-44). */
export async function fetchSyncRunExceptions(syncRunId: string): Promise<readonly ExceptionItem[]> {
  const page = await fetchListPage<ExceptionItem>(
    EXCEPTIONS_PATH,
    { source: "SYNC", sync_run_id: syncRunId },
    null,
    { limit: EXCEPTION_ROWS, count: false },
  );
  return page.items;
}
