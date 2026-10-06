// Exception queue (04 API-R-44 `GET /exceptions`, `GET /exceptions/{id}`, `POST /exceptions/{id}/assign`,
// `/resolve`, `/reprocess`, `/request-waiver`, `/dismiss`; T-IMP-05; §16.14 exception item additions;
// E-42 to E-44, E-106, E-117; SCREENS §13.1 to §13.9, §0.4 RT-46, RT-47; BUILD_SPEC DIN-17). Integration
// after merge (D-81): DIN-11 builds these routes in the same level, so the types below follow its
// contract (ExceptionItemOut, ExceptionAssignIn, ExceptionResolveIn, ExceptionCommentIn,
// WaiverRequestedOut on `sprint/l1`) until `make openapi` regenerates `schema.d.ts` at the merge.
import { send } from "../client";
import { fetchListPage, type ListPage } from "../lists";
import { readProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { EXCEPTIONS_ROUTE } from "./imports";

export type ExceptionStatus = components["schemas"]["ExceptionStatus"];
/** E-43 `exception_severity`. */
export type ExceptionSeverity = "BLOCKING" | "WARNING" | "INFO";
/** E-42 `exception_source`. */
export type ExceptionSource =
  | "IMPORT"
  | "SYNC"
  | "ENGINE"
  | "CLOSE"
  | "RECONCILIATION"
  | "JOURNAL"
  | "INTEGRATION"
  | "DATA_QUALITY"
  | "MIGRATION"
  | "ANOMALY";
/** E-106 `exception_disposition`. */
export type ExceptionDisposition = "remediable" | "discarded";
/** E-117 `exception_action` (API only). */
export type ExceptionAction = "ASSIGN" | "REPROCESS" | "RESOLVE" | "REQUEST_WAIVER" | "DISMISS";
/** 04 §16.14 `dismiss_blocked_reason`. */
export type DismissBlockedReason = "INPUT_COMMITTED";

/** T-IMP-05 `exception_item` with the 04 §16.14 actions (DIN-11 ExceptionItemOut). */
export interface ExceptionItem {
  readonly id: string;
  readonly exception_no: string;
  readonly source: ExceptionSource;
  readonly code: string;
  readonly severity: ExceptionSeverity;
  readonly disposition: ExceptionDisposition;
  readonly status: ExceptionStatus;
  readonly priority: number;
  readonly title: string;
  readonly message: string;
  readonly suggestion: string | null;
  readonly field: string | null;
  readonly business_key: string | null;
  readonly source_payload: Readonly<Record<string, unknown>> | null;
  readonly import_upload_id: string | null;
  readonly import_row_id: string | null;
  readonly sync_run_id: string | null;
  readonly source_record_id: string | null;
  readonly contract_id: string | null;
  readonly contract_external_id: string | null;
  readonly obligation_id: string | null;
  readonly combination_group_id: string | null;
  /**
   * The code of the item's combination group (04 §16.14 rev 1.206): what names the item of a group of
   * several contracts, which carries no contract of its own.
   */
  readonly combination_group_code: string | null;
  readonly entity_id: string | null;
  readonly period_id: string | null;
  readonly close_run_id: string | null;
  readonly journal_run_id: string | null;
  readonly owner_membership_id: string | null;
  readonly owner: components["schemas"]["ActorOut"] | null;
  readonly dedupe_key: string;
  readonly occurrence_count: number;
  readonly last_seen_at: string;
  readonly resolution: string | null;
  readonly resolved_at: string | null;
  readonly resolved_by: components["schemas"]["ActorOut"] | null;
  readonly waiver_approval_request_id: string | null;
  readonly reprocessed_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
  readonly row_version: number;
  readonly available_actions: readonly ExceptionAction[];
  readonly dismiss_blocked_reason: DismissBlockedReason | null;
}

/** DIN-11 WaiverRequestedOut: the `EXCEPTION_WAIVER` request a waiver request opened. */
export interface WaiverRequested {
  readonly approval_request_id: string;
  readonly request_no: string;
}

export const EXCEPTIONS_PATH = "/api/v1/exceptions";
export const USERS_PATH = "/api/v1/users";
/** SCREENS RT-46 SF-11. */
export const EXCEPTION_QUEUE_ROUTE = EXCEPTIONS_ROUTE;
/** SCREENS §13.1: reads need `contract.read`; the commands need `exception.resolve` (ACT-17). */
export const EXCEPTION_READ_PERMISSION = "contract.read";
export const EXCEPTION_RESOLVE_PERMISSION = "exception.resolve";
/** 04 API-R-05: the member directory of the Owner combobox needs `user.manage`. */
export const USER_MANAGE_PERMISSION = "user.manage";
/** SCREENS §13.4 `limit=200`. */
export const QUEUE_PAGE_SIZE = 200;
/** The Owner filter value of the signed-in member (04 API-R-44 `owner=me`). */
export const OWNER_ME = "me";

/** E-44 literals in 04 order; SCREENS §13.3 Status defaults to `in:OPEN,IN_PROGRESS`. */
export const EXCEPTION_STATUSES: readonly ExceptionStatus[] = [
  "OPEN",
  "IN_PROGRESS",
  "RESOLVED",
  "WAIVED",
  "DISMISSED",
];
export const DEFAULT_STATUSES: readonly ExceptionStatus[] = ["OPEN", "IN_PROGRESS"];
/** E-43 literals in 04 order (the severity sort). */
export const EXCEPTION_SEVERITIES: readonly ExceptionSeverity[] = ["BLOCKING", "WARNING", "INFO"];
/** E-42 literals in 04 order (SCREENS §13.4 source labels). */
export const EXCEPTION_SOURCES: readonly ExceptionSource[] = [
  "IMPORT",
  "SYNC",
  "ENGINE",
  "CLOSE",
  "RECONCILIATION",
  "JOURNAL",
  "INTEGRATION",
  "DATA_QUALITY",
  "MIGRATION",
  "ANOMALY",
];

/** SCREENS §13.3 sort menu: "Severity" (the API default), "Newest", "Oldest" (04 API-R-44 keys). */
export type ExceptionSort = "severity" | "newest" | "oldest";
export const EXCEPTION_SORTS: readonly ExceptionSort[] = ["severity", "newest", "oldest"];
const SORT_KEYS: Readonly<Record<ExceptionSort, string>> = {
  severity: "severity",
  newest: "-created_at",
  oldest: "created_at",
};

/** The menu entry of a URL `sort` value; absent or unknown reads the default "Severity". */
export function sortOf(value: string | null): ExceptionSort {
  return EXCEPTION_SORTS.find((sort) => SORT_KEYS[sort] === value) ?? "severity";
}

/** The URL `sort` value of a menu entry; the default is omitted (SCR-URL-09). */
export function sortParam(sort: ExceptionSort): string | null {
  return sort === "severity" ? null : SORT_KEYS[sort];
}

/** The API query of the FilterBar chips (SCREENS §13.4). Repeated values mean IN (04 API-C-09). */
export interface ExceptionListQuery {
  readonly q: string | null;
  readonly status: readonly string[];
  readonly severity: readonly string[];
  readonly source: readonly string[];
  readonly code: readonly string[];
  readonly entity: readonly string[];
  readonly owner: string | null;
  readonly contract: readonly string[];
  readonly period: readonly string[];
  readonly importUploadId: readonly string[];
  /**
   * The id of one period (API-S-Period `id`): the items that hold its lock, by the close gates' own
   * predicate (04 §16.14 rev 1.206). Null for a list that is not cut down to them.
   */
  readonly blocking: string | null;
  readonly sort: ExceptionSort;
}

export function exceptionListParams(
  query: ExceptionListQuery,
): Readonly<Record<string, string | readonly string[] | null>> {
  return {
    q: query.q,
    status: query.status,
    severity: query.severity,
    source: query.source,
    code: query.code,
    entity: query.entity,
    owner: query.owner,
    contract: query.contract,
    period: query.period,
    import_upload_id: query.importUploadId,
    blocking: query.blocking,
    sort: SORT_KEYS[query.sort],
  };
}

export function exceptionsKey(query: ExceptionListQuery): QueryKey {
  return queryKey("exceptions", "tenant", {
    view: "list",
    q: query.q,
    status: query.status.join(","),
    severity: query.severity.join(","),
    source: query.source.join(","),
    code: query.code.join(","),
    entity: query.entity.join(","),
    owner: query.owner,
    contract: query.contract.join(","),
    period: query.period.join(","),
    import_upload_id: query.importUploadId.join(","),
    blocking: query.blocking,
    sort: query.sort,
  });
}

/** Every exception read, for invalidation after a command. */
export const EVERY_EXCEPTION: QueryKey = queryKey("exceptions", "tenant");

/** The master list: the first 200 items of the filters with the total count (SCREENS §13.4). */
export function fetchExceptions(query: ExceptionListQuery): Promise<ListPage<ExceptionItem>> {
  return fetchListPage<ExceptionItem>(EXCEPTIONS_PATH, exceptionListParams(query), null, {
    limit: QUEUE_PAGE_SIZE,
    count: true,
  });
}

export function openCountKey(): QueryKey {
  return queryKey("exceptions", "tenant", { view: "open-count" });
}

/** SCREENS §13.3 page header "<n> open": the OPEN and IN_PROGRESS items the viewer can read. */
export async function fetchOpenCount(): Promise<number | null> {
  const page = await fetchListPage<ExceptionItem>(
    EXCEPTIONS_PATH,
    { status: DEFAULT_STATUSES },
    null,
    { limit: 1, count: true },
  );
  return page.total?.count ?? null;
}

export function exceptionKey(exceptionId: string): QueryKey {
  return queryKey("exceptions", "tenant", { id: exceptionId });
}

/** `GET /exceptions/{id}`: every T-IMP-05 column with `available_actions` and the blocked reason. */
export async function fetchException(exceptionId: string): Promise<ExceptionItem> {
  const response = await send("GET", `${EXCEPTIONS_PATH}/${exceptionId}`);
  if (!response.ok) {
    throw await readProblem(response);
  }
  return (await response.json()) as ExceptionItem;
}

/** The SF-11:item route of an item, keeping the queue's search string (filters, sort, context). */
export function exceptionRoute(exceptionId: string, search = ""): string {
  return `${EXCEPTION_QUEUE_ROUTE}/${exceptionId}${search}`;
}

export type ExceptionCommand = "assign" | "resolve" | "reprocess" | "request-waiver" | "dismiss";

export function exceptionCommandPath(exceptionId: string, command: ExceptionCommand): string {
  return `${EXCEPTIONS_PATH}/${exceptionId}/${command}`;
}

/** SCR-TID-03 key of a code: `PROGRESS_OVER_DELIVERY` → `progress-over-delivery`. */
export function testKey(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** SCREENS §13.5: the item's input can be dismissed; otherwise the blocked-dismissal line shows. */
export function dismissBlocked(item: Pick<ExceptionItem, "dismiss_blocked_reason">): boolean {
  return item.dismiss_blocked_reason === "INPUT_COMMITTED";
}

export type Member = components["schemas"]["UserOut"];

export function membersKey(): QueryKey {
  return queryKey("users", "tenant", { status: "ACTIVE", view: "owners" });
}

/** The active members of the workspace (04 API-R-05 `GET /users?status=ACTIVE`; `user.manage`). */
export async function fetchActiveMembers(): Promise<readonly Member[]> {
  const page = await fetchListPage<Member>(
    USERS_PATH,
    { status: "ACTIVE", sort: "display_name" },
    null,
    { limit: QUEUE_PAGE_SIZE, count: false },
  );
  return page.items;
}
