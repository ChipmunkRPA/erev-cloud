// Schedule lines (04 API-R-35 `GET /schedule-lines`, API-S-ScheduleLine, E-27, E-28; SCREENS §4.3;
// BUILD_SPEC CTR-23). The SF-03:schedules revenue schedule reads the REVENUE lines of the contract's
// latest version in the context book recorded by `known_at`, 200 lines a page, sorted by the period end
// date unless the URL names another sort. [J] L5-4-Q-47: `as_of` is not sent, because API-C-10 would cut
// the schedule at the context period, while SCREENS §4.3 shows inception to the last scheduled period.
import { fetchListPage, type ListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type ScheduleLine = components["schemas"]["ScheduleLineOut"];
export type ScheduleLineType = components["schemas"]["ScheduleLineType"];

export const SCHEDULE_LINES_PATH = "/api/v1/schedule-lines";
/** SCREENS SCR-IA-07 screen code of the revenue schedule grid's saved views. */
export const REVENUE_SCHEDULE_SCREEN_CODE = "SF-03:schedules#revenue";
/** E-27: the revenue schedule panel lists revenue lines only (the billing plan is another kind). */
export const REVENUE_SCHEDULE_KIND = "REVENUE";

/** E-28 literals in the SCREENS §4.3 column 3 order. */
export const SCHEDULE_LINE_TYPES: readonly ScheduleLineType[] = [
  "NORMAL",
  "CATCH_UP",
  "TP_CHANGE",
  "BREAKAGE",
  "ROYALTY",
  "RETURN",
  "MODIFICATION",
  "OPENING_BALANCE",
];

/** The API parameters of one revenue schedule grid state (SCREENS §4.3 filters and context). */
export interface ScheduleLineQuery {
  readonly contractId: string;
  readonly book: string | null;
  readonly knownAt: string | null;
  readonly fromPeriod: string | null;
  readonly toPeriod: string | null;
  readonly obligation: string | null;
  readonly lineType: string | null;
}

export function scheduleLinesKey(query: ScheduleLineQuery): QueryKey {
  return queryKey("schedule-lines", "tenant", {
    contract: query.contractId,
    book: query.book,
    known_at: query.knownAt,
    from_period: query.fromPeriod,
    to_period: query.toPeriod,
    obligation: query.obligation,
    line_type: query.lineType,
  });
}

/** The API parameters of SF-04 `layout=lines` (SCREENS_B §4.1 data bindings; BUILD_SPEC RPS-7). */
export interface ScheduleRangeQuery {
  readonly entity: string | null;
  readonly book: string | null;
  readonly fromPeriod: string | null;
  readonly toPeriod: string | null;
  /** An obligation key or id (API-R-35). */
  readonly obligation: string | null;
  readonly knownAt: string | null;
}

export function scheduleRangeKey(query: ScheduleRangeQuery): QueryKey {
  return queryKey("schedule-lines", "tenant", {
    view: "range",
    entity: query.entity,
    book: query.book,
    from_period: query.fromPeriod,
    to_period: query.toPeriod,
    obligation: query.obligation,
    known_at: query.knownAt,
  });
}

/** One page of the context's revenue schedule lines with the total count (`count=true`). */
export function fetchScheduleRangePage(
  query: ScheduleRangeQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<ScheduleLine>> {
  return fetchListPage<ScheduleLine>(
    SCHEDULE_LINES_PATH,
    {
      entity: query.entity,
      book: query.book,
      from_period: query.fromPeriod,
      to_period: query.toPeriod,
      obligation: query.obligation,
      schedule_kind: REVENUE_SCHEDULE_KIND,
      known_at: query.knownAt,
      sort,
    },
    cursor,
    { count: true },
  );
}

/** One page of the contract's revenue schedule lines; no URL sort keeps `period_end_date`. */
export function fetchScheduleLinesPage(
  query: ScheduleLineQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<ScheduleLine>> {
  return fetchListPage<ScheduleLine>(
    SCHEDULE_LINES_PATH,
    {
      contract: query.contractId,
      schedule_kind: REVENUE_SCHEDULE_KIND,
      book: query.book,
      known_at: query.knownAt,
      from_period: query.fromPeriod,
      to_period: query.toPeriod,
      obligation: query.obligation,
      line_type: query.lineType,
      sort,
    },
    cursor,
  );
}
