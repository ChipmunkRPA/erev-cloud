// SF-01 Home reads (04 API-R-50 §16.13 API-S-DashboardHome; API-R-09 approvals; API-R-44 exceptions;
// API-R-10 audit events; API-R-28 contracts; API-R-16 saved views; API-R-26 policies; SCREENS §2.4,
// §2.5; BUILD_SPEC RPS-22). Money members stay API-C-06 strings (DG-FE-08); their currencies are
// registered from `GET /currencies` before the page formats them (DS-FMT-03). The query keys use each
// resource's name, so the commands that invalidate a resource refresh Home as well.
import { send } from "../client";
import { fetchListPage, type ListPage, listSearch } from "../lists";
import { ApiProblem, isRefused, readProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { APPROVALS_PATH, type Approval } from "./approvals";
import { CONTRACTS_PATH, type ContractListItem } from "./contracts";
import type { ExceptionItem } from "./exceptions";
import { AUDIT_EVENTS_PATH, ensureCurrencyCodes } from "./journal-runs";
import { EXCEPTIONS_PATH } from "./periods";
import { SAVED_VIEWS_PATH, type SavedView } from "./saved-views";

export type DashboardHome = components["schemas"]["DashboardHomeOut"];
export type DashboardBlockers = components["schemas"]["PeriodBlockersOut"];
export type AuditEvent = components["schemas"]["AuditEventOut"];
export type Policy = components["schemas"]["PolicyOut"];

export const DASHBOARD_HOME_PATH = "/api/v1/dashboard/home";
export const POLICIES_PATH = "/api/v1/policies";

/** SCREENS §2.3: up to 8 rows in each queue and 10 activity items. */
export const QUEUE_LIMIT = 8;
export const ACTIVITY_LIMIT = 10;
const FAVOURITES_LIMIT = 200;

/** SCREENS §2.4 (SCR-LTH-O1): the preset of the published TENANT accounting policy version. */
export const LEGACY_PRESET = "LEGACY_PARITY";

/** The context parameters of `GET /dashboard/home`; null leaves the API default (API-C-11). */
export interface HomeContext {
  readonly entity: string | null;
  readonly period: string | null;
  readonly book: string | null;
}

export function dashboardHomeKey(context: HomeContext): QueryKey {
  return queryKey("dashboard", "tenant", {
    view: "home",
    entity: context.entity,
    period: context.period,
    book: context.book,
  });
}

/** `GET /dashboard/home` with its currency registered. */
export async function fetchDashboardHome(context: HomeContext): Promise<DashboardHome> {
  const search = listSearch({
    entity: context.entity,
    period: context.period,
    book: context.book,
  });
  const response = await send("GET", `${DASHBOARD_HOME_PATH}${search}`);
  if (!response.ok) {
    throw await readProblem(response);
  }
  const home = (await response.json()) as DashboardHome;
  await ensureCurrencyCodes([home.context.currency]);
  return home;
}

export function waitingForYouKey(): QueryKey {
  return queryKey("approvals", "tenant", { view: "home-waiting" });
}

/**
 * SCREENS §2.5 "Waiting for you": pending requests the caller can decide, oldest first, with the count.
 * [J] L7-2-Q-22: no `entity` parameter, because API-R-09 filters on the request's own entity and most
 * requests name none (L7-2-Q-2, Q-13).
 */
export async function fetchWaitingForYou(): Promise<ListPage<Approval>> {
  const page = await fetchListPage<Approval>(
    APPROVALS_PATH,
    { assigned_to_me: true, status: "PENDING", sort: "submitted_at" },
    null,
    { limit: QUEUE_LIMIT, count: true },
  );
  await ensureCurrencyCodes(
    page.items.flatMap((item) => (item.amount === null ? [] : [item.amount.currency])),
  );
  return page;
}

export function openExceptionsKey(entity: string | null): QueryKey {
  return queryKey("exceptions", "tenant", { view: "home-open", entity });
}

/** SCREENS §2.5 "Open exceptions": blocking first, then newest (04 API-R-44 `sort=severity`). */
export function fetchOpenExceptions(entity: string | null): Promise<ListPage<ExceptionItem>> {
  return fetchListPage<ExceptionItem>(
    EXCEPTIONS_PATH,
    { status: ["OPEN", "IN_PROGRESS"], entity, sort: "severity" },
    null,
    { limit: QUEUE_LIMIT, count: true },
  );
}

export function recentActivityKey(from: string | null): QueryKey {
  return queryKey("audit-events", "tenant", { view: "home-recent", from });
}

/**
 * SCREENS §2.5 "Recent activity": the 10 latest audit events from the context period start; null
 * when the API refuses the read (ruling R-28: the list is read with `audit.read` for all entities).
 */
export async function fetchRecentActivity(
  from: string | null,
): Promise<readonly AuditEvent[] | null> {
  try {
    const page = await fetchListPage<AuditEvent>(AUDIT_EVENTS_PATH, { from }, null, {
      limit: ACTIVITY_LIMIT,
      count: false,
    });
    return page.items;
  } catch (error) {
    if (isRefused(error)) {
      return null;
    }
    throw error;
  }
}

export function recentlyViewedKey(): QueryKey {
  return queryKey("contracts", "tenant", { view: "home-recently-viewed" });
}

/** SCREENS §2.5 "Recently viewed" variant: `GET /contracts?quick_list=RECENTLY_VIEWED` (E-111). */
export async function fetchRecentlyViewed(): Promise<readonly ContractListItem[]> {
  const page = await fetchListPage<ContractListItem>(
    CONTRACTS_PATH,
    { quick_list: "RECENTLY_VIEWED" },
    null,
    { limit: ACTIVITY_LIMIT, count: false },
  );
  return page.items;
}

export function contractCountKey(): QueryKey {
  return queryKey("contracts", "tenant", { view: "home-count" });
}

/** [J] L7-2-Q-23: the SCREENS §2.7 empty tenant is a workspace without contracts. */
export async function fetchContractCount(): Promise<number> {
  const page = await fetchListPage<unknown>(CONTRACTS_PATH, {}, null, { limit: 1, count: true });
  return page.total?.count ?? page.items.length;
}

export function favouritesKey(): QueryKey {
  return queryKey("saved-views", "tenant", { view: "home-favourites", is_favourite: true });
}

/** SCREENS §2.5 "Favourites" (SCR-IA-08): the caller's saved views with `is_favourite = true`. */
export async function fetchFavourites(): Promise<readonly SavedView[]> {
  const page = await fetchListPage<SavedView>(SAVED_VIEWS_PATH, { is_favourite: true }, null, {
    limit: FAVOURITES_LIMIT,
    count: false,
  });
  return page.items.filter((view) => view.is_favourite);
}

/** The favourite's target: `config.path` when it is an app path, and `config.label` or the name. */
export function favouriteTarget(view: SavedView): {
  readonly path: string | null;
  readonly label: string;
} {
  const { path, label } = view.config;
  return {
    path: typeof path === "string" && path.startsWith("/") && !path.startsWith("//") ? path : null,
    label: typeof label === "string" && label !== "" ? label : view.name,
  };
}

export function legacyPresetKey(): QueryKey {
  return queryKey("policies", "tenant", { view: "home-legacy-preset" });
}

/**
 * SCREENS §2.4: whether the published TENANT accounting policy version is the legacy-parity preset.
 * A reader without `config.read` reads no policy, so the panel does not render.
 */
export async function fetchLegacyPreset(): Promise<boolean> {
  try {
    const page = await fetchListPage<Policy>(
      POLICIES_PATH,
      { category: "ACCOUNTING_POLICY", scope: "TENANT", status: "PUBLISHED" },
      null,
      { limit: 1, count: false },
    );
    return page.items[0]?.preset_code === LEGACY_PRESET;
  } catch (error) {
    if (error instanceof ApiProblem && error.status === 403) {
      return false;
    }
    throw error;
  }
}
