// Close cockpit reads (04 API-R-18 §16.8: API-S-Period, API-S-PeriodCockpit, the period commands and
// the `locks` and `transitions` of SF-05:history; API-R-09 approval counts; API-R-38 `GET /journal-runs`;
// SCREENS_B §1.1, §1.3 and §1.4 data bindings; BUILD_SPEC CLO-23, CLO-24). The cockpit resolves its period from the context pill's read of
// `GET /periods?entity=&book=` (the same query key), because the route takes no `period` filter
// ([J] L7-2-Q-13). Money members stay API-C-06 strings (DG-FE-08), and the functional currency is
// registered from `GET /currencies` before the cockpit renders (DS-FMT-03).
import { send } from "../client";
import { fetchListPage, type ListPage, type ListQuery } from "../lists";
import { ApiProblem, readProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { APPROVALS_PATH } from "./approvals";
import { ensureCurrencyCodes, JOURNAL_RUNS_PATH, type JournalRun } from "./journal-runs";
import { PERIODS_PATH } from "./tenant";

export type PeriodCockpit = components["schemas"]["PeriodCockpitOut"];
export type ChecklistItem = components["schemas"]["ChecklistItemOut"];
export type ChecklistStatus = components["schemas"]["ChecklistStatus"];
export type PeriodBlockers = components["schemas"]["PeriodBlockersOut"];
export type JournalPreview = components["schemas"]["JournalPreviewOut"];
export type PeriodApproval = components["schemas"]["ApprovalOut"];
/** The request bodies of `request-lock`, `request-permanent-lock` and `request-reopen` (04 §16.8). */
export type PeriodLockRequestIn = components["schemas"]["PeriodLockRequestIn"];
export type PeriodPermanentLockRequestIn = components["schemas"]["PeriodPermanentLockRequestIn"];
export type PeriodReopenRequestIn = components["schemas"]["PeriodReopenRequestIn"];

export const EXCEPTIONS_PATH = "/api/v1/exceptions";
/** API-R-39; its routes belong to CLO-19 (R-RC-1, post-rc; L7-2-Q-14). */
export const CLOSE_RUNS_PATH = "/api/v1/close-runs";
export const JUDGEMENTS_PATH = "/api/v1/judgements";

/** 04 API-R-18 command permissions (SCREENS_B §1.1 "Roles and permissions"). */
export const PERIOD_CLOSE_PERMISSION = "period.close";
export const PERIOD_LOCK_PERMISSION = "period.lock";
export const PERIOD_REOPEN_PERMISSION = "period.reopen_request";

/** Every period read: the context pill's lists, the cockpit, its counts and its requests. */
export const EVERY_PERIOD: QueryKey = queryKey("periods", "tenant");

export function periodCommandPath(periodId: string, command: string): string {
  return `${PERIODS_PATH}/${periodId}/${command}`;
}

async function readJson<T>(path: string): Promise<T> {
  const response = await send("GET", path);
  if (!response.ok) {
    throw await readProblem(response);
  }
  return (await response.json()) as T;
}

export function cockpitKey(periodId: string): QueryKey {
  return queryKey("periods", "tenant", { id: periodId, view: "cockpit" });
}

/** `GET /periods/{id}/cockpit` with its functional currency registered. */
export async function fetchCockpit(periodId: string): Promise<PeriodCockpit> {
  const cockpit = await readJson<PeriodCockpit>(`${PERIODS_PATH}/${periodId}/cockpit`);
  await ensureCurrencyCodes([cockpit.journal_preview.debit_functional.currency]);
  return cockpit;
}

/** The SCREENS_B §1.1 blocker counts read beside API-S-Period (counts only, `X-Erev-Total-Count`). */
export interface BlockerCounts {
  readonly vcReassessmentMissing: number;
}

export function blockerCountsKey(periodId: string): QueryKey {
  return queryKey("periods", "tenant", { id: periodId, view: "blocker-counts" });
}

async function countOf(path: string, query: ListQuery): Promise<number> {
  try {
    const page = await fetchListPage<unknown>(path, query, null, { limit: 1, count: true });
    return page.total?.count ?? page.items.length;
  } catch (error) {
    // A reader without the list's permission reads no such items; the API stays the enforcer.
    if (error instanceof ApiProblem && error.status === 403) {
      return 0;
    }
    throw error;
  }
}

/**
 * BLK-03 `VC_REASSESSMENT_MISSING` items, read through the permission-filtered `GET /exceptions` (a
 * 403 reads as 0). BLK-06 and BLK-15 no longer read `GET /approvals`: they subtract API-S-PeriodCockpit
 * `pending_requests`, which API-R-09 request visibility does not filter, so those two rows do not
 * depend on the reader (SCREENS_B §1.1 rev 1.3; D-90a QA-L9-7, L8-C-Q-2).
 */
export async function fetchBlockerCounts(
  entity: { readonly id: string; readonly code: string },
  periodKey: string,
): Promise<BlockerCounts> {
  const vc = await countOf(EXCEPTIONS_PATH, {
    code: "VC_REASSESSMENT_MISSING",
    entity: entity.code,
    period: periodKey,
    status: ["OPEN", "IN_PROGRESS"],
  });
  return { vcReassessmentMissing: vc };
}

export function openExceptionCountKey(entity: string, periodKey: string): QueryKey {
  return queryKey("exceptions", "tenant", { view: "open-count", entity, period: periodKey });
}

/**
 * SCREENS_B §1.5 "Exceptions": the open and in-progress items of an entity and period, as a count
 * (`GET /exceptions?entity&period&status&count=true`); a 403 reads as 0.
 */
export function fetchOpenExceptionCount(entity: string, periodKey: string): Promise<number> {
  return countOf(EXCEPTIONS_PATH, {
    entity,
    period: periodKey,
    status: ["OPEN", "IN_PROGRESS"],
  });
}

/** The pending `PERIOD_LOCK` and `PERIOD_REOPEN` requests whose subject is the period state. */
export interface PeriodRequests {
  readonly lock: PeriodApproval | null;
  readonly reopen: PeriodApproval | null;
}

export function periodRequestsKey(periodId: string): QueryKey {
  return queryKey("periods", "tenant", { id: periodId, view: "requests" });
}

export async function fetchPeriodRequests(periodId: string): Promise<PeriodRequests> {
  const page = await fetchListPage<PeriodApproval>(
    APPROVALS_PATH,
    { status: "PENDING", subject_type: ["PERIOD_LOCK", "PERIOD_REOPEN"] },
    null,
    { limit: 200, count: false },
  );
  const of = (type: string) =>
    page.items.find((item) => item.subject.type === type && item.subject.id === periodId) ?? null;
  return { lock: of("PERIOD_LOCK"), reopen: of("PERIOD_REOPEN") };
}

/** One T-CLS-04 record of `GET /periods/{id}/locks`: a lock, a reopen or a permanent lock (E-63). */
export type PeriodLockRow = components["schemas"]["PeriodLockRowOut"];
export type LockKind = components["schemas"]["LockKind"];
/** One row of `GET /periods/{id}/transitions`: a change of the period's state (E-04). */
export type PeriodTransition = components["schemas"]["PeriodTransitionOut"];

/** SCREENS_B §1.4: the state history is read a page at a time; "Load older activity" reads the next. */
export const TRANSITIONS_PAGE = 50;

export function locksKey(periodId: string): QueryKey {
  return queryKey("periods", "tenant", { id: periodId, view: "locks" });
}

export function transitionsKey(periodId: string): QueryKey {
  return queryKey("periods", "tenant", { id: periodId, view: "transitions" });
}

/** The lock, reopen and permanent-lock records of the period, newest first (one answer, no pages). */
export async function fetchPeriodLocks(periodId: string): Promise<readonly PeriodLockRow[]> {
  const body = await readJson<{ readonly items: readonly PeriodLockRow[] }>(
    `${PERIODS_PATH}/${periodId}/locks`,
  );
  return body.items;
}

/** One page of the period's state history, newest first (the route's default sort `-id`). */
export function fetchPeriodTransitions(
  periodId: string,
  cursor: string | null,
): Promise<ListPage<PeriodTransition>> {
  return fetchListPage<PeriodTransition>(`${PERIODS_PATH}/${periodId}/transitions`, {}, cursor, {
    limit: TRANSITIONS_PAGE,
    count: false,
  });
}

export function latestRunKey(entity: string, book: string, period: string): QueryKey {
  return queryKey("journal-runs", "tenant", { entity, book, period, view: "latest" });
}

/** SCREENS_B §1.3 "Open journal run": the newest run of the entity, book and period not cancelled. */
export async function fetchLatestJournalRun(
  entity: string,
  book: string,
  period: string,
): Promise<JournalRun | null> {
  const page = await fetchListPage<JournalRun>(JOURNAL_RUNS_PATH, { entity, book, period }, null, {
    limit: 50,
    count: false,
  });
  const live = page.items.filter((run) => run.state !== "cancelled");
  return [...live].sort((a, b) => (a.created_at < b.created_at ? 1 : -1))[0] ?? null;
}
