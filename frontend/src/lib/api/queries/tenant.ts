// The workspace and its structure (04 API-R-17 `GET, PATCH /tenant`, `GET /entities`, `GET /books`;
// API-R-18 `GET /periods`; §16.4 API-S-Entity, §16.8 API-S-Period; BUILD_SPEC RFD-19). The shell's
// context pill (DS-CMP-03) and the workspace setup and settings screens read these; entity, book and
// period lists come in one page of at most 200 rows, which covers a workspace's context choices.
import { useQuery } from "@tanstack/react-query";

import { dateParts, daysInMonth, formatPeriod } from "../../format";
import { api, unwrap } from "../client";
import { fetchListPage, type ListPage, type ListQuery } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type Tenant = components["schemas"]["TenantOut"];
export type TenantUpdate = components["schemas"]["TenantUpdateIn"];
export type Entity = components["schemas"]["EntityOut"];
export type Book = components["schemas"]["BookOut"];
export type BookCode = components["schemas"]["BookCode"];
export type Period = components["schemas"]["PeriodOut"];
export type PeriodState = components["schemas"]["PeriodState"];
export type CalendarPeriod = components["schemas"]["CalendarPeriodOut"];

export const TENANT_PATH = "/api/v1/tenant";
export const ENTITIES_PATH = "/api/v1/entities";
export const BOOKS_PATH = "/api/v1/books";
export const PERIODS_PATH = "/api/v1/periods";
/** One page of context choices (04 API-C-09 limit maximum). */
export const STRUCTURE_LIMIT = 200;
/** 04 API-R-17 and API-R-18: the structure reads need `config.read`. */
export const STRUCTURE_READ_PERMISSION = "config.read";

export function tenantKey(): QueryKey {
  return queryKey("tenant", "tenant");
}

export function fetchTenant(): Promise<Tenant> {
  return unwrap(api.GET("/api/v1/tenant"));
}

/** `GET /tenant` (`settings.manage`). */
export function useTenant(enabled = true) {
  return useQuery({ queryKey: tenantKey(), queryFn: fetchTenant, enabled });
}

/** The 04 API-C-05 `If-Match` value of a row version. */
export function rowIfMatch(rowVersion: number): string {
  return `"r${String(rowVersion)}"`;
}

export function entitiesKey(): QueryKey {
  return queryKey("entities", "tenant", { is_active: true });
}

/** The active entities in the principal's scope, in code order (API-R-17 default sort). */
export async function fetchActiveEntities(): Promise<readonly Entity[]> {
  const page = await fetchListPage<Entity>(ENTITIES_PATH, { is_active: true }, null, {
    limit: STRUCTURE_LIMIT,
    count: false,
  });
  return page.items;
}

export function booksKey(): QueryKey {
  return queryKey("books", "tenant");
}

/** The tenant's three books (E-02). */
export async function fetchBooks(): Promise<readonly Book[]> {
  const page = await fetchListPage<Book>(BOOKS_PATH, {}, null, {
    limit: STRUCTURE_LIMIT,
    count: false,
  });
  return page.items;
}

export function periodsKey(query: Readonly<Record<string, string>>): QueryKey {
  return queryKey("periods", "tenant", query);
}

/** API-S-Period rows under `query` in period order (`period_end_date`, the default sort). */
export async function fetchPeriods(
  query: ListQuery,
  limit: number = STRUCTURE_LIMIT,
): Promise<readonly Period[]> {
  const page = await fetchListPage<Period>(PERIODS_PATH, query, null, { limit, count: false });
  return page.items;
}

/** One page of a structure list with its `X-Erev-Total-Count`, for counts such as "2 entities". */
export function fetchCounted<T>(path: string, query: ListQuery): Promise<ListPage<T>> {
  return fetchListPage<T>(path, query, null, { limit: 1, count: true });
}

/** Whether the period is one Gregorian month: it starts on the 1st and ends on that month's last day. */
export function isCalendarMonth(period: Pick<CalendarPeriod, "start_date" | "end_date">): boolean {
  const start = dateParts(period.start_date);
  const end = dateParts(period.end_date);
  return (
    start.day === 1 &&
    start.year === end.year &&
    start.month === end.month &&
    end.day === daysInMonth(end.year, end.month)
  );
}

/** DS-FMT-19: "Sep 2026" for a Gregorian month, else the fiscal label such as "FY2026 P09". */
export function periodLabel(
  period: Pick<CalendarPeriod, "period_key" | "start_date" | "end_date">,
): string {
  return isCalendarMonth(period)
    ? formatPeriod(period.period_key, { startDate: period.start_date })
    : formatPeriod(period.period_key);
}
