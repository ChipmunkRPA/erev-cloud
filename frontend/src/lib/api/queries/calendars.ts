// Fiscal calendars (04 API-R-18 `GET, POST /calendars`, `POST /calendars/{id}/generate-year`; T-REF-02;
// E-50 `calendar_pattern`; REQ-REF-002, REQ-REF-003; SCREENS_B §9.3; BUILD_SPEC RFD-18). A calendar
// defines fiscal years and periods; entities use one calendar each. The workspace has a handful of
// calendars, read in one page.
import { useQuery } from "@tanstack/react-query";

import { fetchListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { DateParts } from "../../format";
import type { components } from "../schema";
import { type BookCode, type CalendarPeriod, type Period, STRUCTURE_LIMIT } from "./tenant";

export type Calendar = components["schemas"]["CalendarOut"];
export type CalendarCreate = components["schemas"]["CalendarIn"];
export type CalendarPattern = components["schemas"]["CalendarPattern"];
export type GenerateYear = components["schemas"]["GenerateYearIn"];
export type GenerateYearResult = components["schemas"]["GenerateYearOut"];
export type YearEndAnchor = NonNullable<Calendar["year_end_anchor"]>;

export const CALENDARS_PATH = "/api/v1/calendars";
/** SCREENS RT-76 SF-15:calendars; the screen parameter `calendar=<code>` selects one (SCR-URL-27). */
export const CALENDARS_ROUTE = "/settings/calendars";
/** 04 API-R-18: calendars and `generate-year` need any of these. */
export const CALENDAR_MAINTAIN_PERMISSIONS: readonly string[] = [
  "masterdata.maintain",
  "settings.manage",
];
/** E-50 literals in 04 order. */
export const CALENDAR_PATTERNS: readonly CalendarPattern[] = [
  "MONTHLY",
  "P445",
  "P454",
  "P544",
  "P13",
  "W5253",
];
/** Week-based patterns take "Week ends on" and "Year-end anchor" (BUILD_SPEC BS3-D-16). */
export const WEEK_BASED_PATTERNS: ReadonlySet<CalendarPattern> = new Set([
  "P445",
  "P454",
  "P544",
  "P13",
  "W5253",
]);
export const YEAR_END_ANCHORS: readonly YearEndAnchor[] = [
  "LAST_WEEKDAY_OF_MONTH",
  "NEAREST_WEEKDAY_TO_MONTH_END",
];
/** SCREENS_B §9.3 "Code": letters, digits and hyphens. */
export const CALENDAR_CODE_PATTERN = /^[A-Za-z0-9-]+$/;

/** Every calendar read, for invalidation after a command. */
export const EVERY_CALENDAR: QueryKey = queryKey("calendars", "tenant");

export function calendarsKey(): QueryKey {
  return queryKey("calendars", "tenant", { view: "all" });
}

/** All calendars in code order (the API default sort). */
export async function fetchAllCalendars(): Promise<readonly Calendar[]> {
  const page = await fetchListPage<Calendar>(CALENDARS_PATH, {}, null, {
    limit: STRUCTURE_LIMIT,
    count: false,
  });
  return page.items;
}

export function useCalendars(enabled = true) {
  return useQuery({ queryKey: calendarsKey(), queryFn: fetchAllCalendars, enabled });
}

export function generateYearPath(calendarId: string): string {
  return `${CALENDARS_PATH}/${calendarId}/generate-year`;
}

export function calendarRoute(code: string): string {
  return `${CALENDARS_ROUTE}?calendar=${encodeURIComponent(code)}`;
}

/** The calendar whose code matches, else the first one (the screen's default selection). */
export function selectCalendar(
  calendars: readonly Calendar[],
  code: string | null,
): Calendar | null {
  return calendars.find((calendar) => calendar.code === code) ?? calendars[0] ?? null;
}

/** DS-FMT-19 fiscal year label. */
export function fiscalYearLabel(fiscalYear: number): string {
  return `FY${String(fiscalYear)}`;
}

/** The fiscal year that contains a business date under the calendar's start month (SCREENS_B §9.3
 *  "the year in which the fiscal year ends": AVM-JP's April 2026 to March 2027 year is FY2027). */
export function fiscalYearOf(
  calendar: Pick<Calendar, "fiscal_year_start_month">,
  date: DateParts,
): number {
  const start = calendar.fiscal_year_start_month;
  return start === 1 || date.month < start ? date.year : date.year + 1;
}

/** The fiscal years offered by the "Fiscal year" select: two back, two ahead and the selected one. */
export function fiscalYearOptions(current: number, selected: number | null): readonly number[] {
  const years = new Set<number>();
  for (let year = current - 2; year <= current + 2; year += 1) {
    years.add(year);
  }
  if (selected !== null) {
    years.add(selected);
  }
  return [...years].sort((a, b) => a - b);
}

/** SCREENS_B §9.3 `f.fiscal_year=is:<n>`: the selected year, else null. */
export function fiscalYearParam(search: string): number | null {
  const raw = new URLSearchParams(search).get("f.fiscal_year");
  const match = raw === null ? null : /^is:(\d{4})$/.exec(raw);
  return match === null ? null : Number(match[1]);
}

export function calendarSearch(code: string | null, fiscalYear: number | null): string {
  const params = new URLSearchParams();
  if (code !== null) {
    params.set("calendar", code);
  }
  if (fiscalYear !== null) {
    params.set("f.fiscal_year", `is:${String(fiscalYear)}`);
  }
  const text = params.toString();
  return text === "" ? "" : `?${text}`;
}

/** One periods-grid row: the calendar period and the API-S-Period row per "<entity code>|<book>". */
export interface PeriodMatrixRow {
  readonly key: string;
  readonly period: CalendarPeriod;
  readonly cells: ReadonlyMap<string, Period>;
}

export function matrixColumnKey(entityCode: string, book: BookCode): string {
  return `${entityCode}|${book}`;
}

/** Groups API-S-Period rows by period key in period order (SCREENS_B §9.3 periods grid). */
export function buildPeriodRows(periods: readonly Period[]): readonly PeriodMatrixRow[] {
  const rows = new Map<string, { period: CalendarPeriod; cells: Map<string, Period> }>();
  for (const row of periods) {
    const key = row.period.period_key;
    const existing = rows.get(key) ?? { period: row.period, cells: new Map<string, Period>() };
    existing.cells.set(matrixColumnKey(row.entity.code, row.book), row);
    rows.set(key, existing);
  }
  return [...rows.values()]
    .sort(
      (a, b) =>
        a.period.fiscal_year - b.period.fiscal_year || a.period.period_no - b.period.period_no,
    )
    .map((entry) => ({ key: entry.period.period_key, period: entry.period, cells: entry.cells }));
}

/** SCREENS_B §9.3: "Open" shows in `future` cells whose previous period is not `future` (the first
 *  fetched period of the year counts as openable when nothing earlier is in view). */
export function canOpenCell(
  rows: readonly PeriodMatrixRow[],
  index: number,
  columnKey: string,
): boolean {
  const cell = rows[index]?.cells.get(columnKey);
  if (cell === undefined || cell.state !== "future") {
    return false;
  }
  const previous = rows[index - 1]?.cells.get(columnKey);
  return previous === undefined ? index === 0 : previous.state !== "future";
}
