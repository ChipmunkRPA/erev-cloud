// Close runs (04 §15.3 API-R-39, §16.8 API-S-CloseRunCreate and API-S-CloseRun, T-CLS-01, E-62; PRD
// SM-14, NFR-14; SCREENS_B §1.2, §1.5; BUILD_SPEC CLO-24, CLO-19). A run is read as itself — its status,
// its fourteen steps with their counts and problem, and the progress of its newest job — because the job
// answers only its initiator and an auditor. The rows of `steps` are in the order of the array (T-CLS-01);
// the run executes "FX remeasurement" before "Release schedules" (supervisor ruling R-79 (b)).
import { send } from "../client";
import { fetchListPage } from "../lists";
import { readProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { ensureCurrencyCodes } from "./approvals";
import { CLOSE_RUNS_PATH } from "./periods";

/** API-S-CloseRun. */
export type CloseRun = components["schemas"]["CloseRunOut"];
/** One T-CLS-01 `steps` element. */
export type CloseRunStep = components["schemas"]["CloseRunStepOut"];
/** E-62 `close_run_status`, of a run and of each step. */
export type CloseRunStatus = components["schemas"]["CloseRunStatus"];
/** The request bodies of `POST /close-runs` and `POST /close-runs/{id}/cancel`. */
export type CloseRunCreateIn = components["schemas"]["CloseRunCreateIn"];
export type CloseRunCancelIn = components["schemas"]["CloseRunCancelIn"];

/** The 202 header that names the run a start inserted (04 §16.8). */
export const CLOSE_RUN_ID_HEADER = "X-Erev-Close-Run-Id";
/** A run is read again this often while it is queued or running (SCREENS_B §1.2). */
export const CLOSE_RUN_POLL_MS = 2_000;
/** SCREENS_B §1.2 "Earlier close runs": at most ten, newest first. */
export const EARLIER_RUNS = 10;

/** T-CLS-01 `step_code` in the order of the array, for the labels the screens give them. */
export const CLOSE_RUN_STEP_CODES = [
  "CUTOFF",
  "INTERFACE_COMPLETENESS",
  "EXCEPTION_CHECK",
  "RECOMPUTE_DIRTY",
  "RELEASE_SCHEDULES",
  "FX_REMEASUREMENT",
  "NETTING_RECLASS",
  "INVARIANTS",
  "JOURNAL_SUMMARIZATION",
  "EXPORT",
  "ACKNOWLEDGEMENT_WAIT",
  "GL_TIE_OUT",
  "DATASET_FREEZE",
  "LOCK",
] as const;
export type CloseRunStepCode = (typeof CLOSE_RUN_STEP_CODES)[number];

const ACTIVE: ReadonlySet<CloseRunStatus> = new Set<CloseRunStatus>([
  "PENDING",
  "RUNNING",
  "BLOCKED",
]);
const MOVING: ReadonlySet<CloseRunStatus> = new Set<CloseRunStatus>(["PENDING", "RUNNING"]);
const RESUMABLE: ReadonlySet<CloseRunStatus> = new Set<CloseRunStatus>(["FAILED", "BLOCKED"]);

/** A run that has not ended: no second run of its entity, book and period starts, and it is cancelled. */
export function isActiveRun(run: Pick<CloseRun, "status">): boolean {
  return ACTIVE.has(run.status);
}

/** A run whose job is queued or working, so its read is repeated. */
export function isMovingRun(run: Pick<CloseRun, "status"> | undefined): boolean {
  return run !== undefined && MOVING.has(run.status);
}

/** `POST /close-runs/{id}/resume` takes a failed or a blocked run (NFR-14). */
export function isResumableRun(run: Pick<CloseRun, "status">): boolean {
  return RESUMABLE.has(run.status);
}

/** Every close-run read: the lists of a period and each run. */
export const EVERY_CLOSE_RUN: QueryKey = queryKey("close-runs", "tenant");

/** The entity, book and period of SF-05 (SCREENS_B §1.2 data bindings). */
export interface CloseRunScope {
  readonly entity: string;
  readonly book: string;
  readonly period: string;
}

export function closeRunsKey(scope: CloseRunScope): QueryKey {
  return queryKey("close-runs", "tenant", { ...scope, view: "period" });
}

export function closeRunKey(closeRunId: string): QueryKey {
  return queryKey("close-runs", "tenant", { id: closeRunId });
}

/** SCREENS RT-99 SF-05:close-run. */
export function closeRunRoute(scope: CloseRunScope): string {
  return `/close/${encodeURIComponent(scope.entity)}/${encodeURIComponent(scope.book)}/${encodeURIComponent(scope.period)}/close-run`;
}

/**
 * The close runs of the entity, book and period, newest first (`GET /close-runs`, default sort
 * `-id`): the first is the period's run, the others the "Earlier close runs".
 */
export async function fetchCloseRuns(scope: CloseRunScope): Promise<readonly CloseRun[]> {
  const page = await fetchListPage<CloseRun>(
    CLOSE_RUNS_PATH,
    { entity: scope.entity, book: scope.book, period: scope.period },
    null,
    { limit: EARLIER_RUNS + 1, count: false },
  );
  return withCurrencies(page.items);
}

/** One page of context choices covers the runs of a book that have not ended (04 API-C-09). */
const ACTIVE_RUNS_LIMIT = 200;

/**
 * The close runs of a book that have not ended, in every entity of the reader's scope (SCREENS_B §1.5):
 * the entities SF-05:multi-entity shows when it opens.
 */
export async function fetchActiveCloseRuns(book: string): Promise<readonly CloseRun[]> {
  const page = await fetchListPage<CloseRun>(
    CLOSE_RUNS_PATH,
    { book, status: ["PENDING", "RUNNING", "BLOCKED"] },
    null,
    { limit: ACTIVE_RUNS_LIMIT, count: false },
  );
  return page.items;
}

/** The currencies a run's steps state amounts in, registered before the run renders (DS-FMT-03). */
async function withCurrencies<T extends CloseRun | readonly CloseRun[]>(found: T): Promise<T> {
  const runs: readonly CloseRun[] = Array.isArray(found) ? found : [found as CloseRun];
  await ensureCurrencyCodes(
    runs.flatMap((run) => run.steps.map((step) => tieOutOf(step.counts)?.currency ?? "")),
  );
  return found;
}

/** `GET /close-runs/{id}` with its steps, counts and newest job. */
export async function fetchCloseRun(closeRunId: string): Promise<CloseRun> {
  const response = await send("GET", `${CLOSE_RUNS_PATH}/${closeRunId}`);
  if (!response.ok) {
    throw await readProblem(response);
  }
  return withCurrencies((await response.json()) as CloseRun);
}

/** The position of a step in the array, from 1, or null for a code the run does not hold. */
export function stepNumber(run: Pick<CloseRun, "steps">, stepCode: string | null): number | null {
  const index = run.steps.findIndex((step) => step.step_code === stepCode);
  return index < 0 ? null : index + 1;
}

/** A non-negative integer count of a step's `counts`, or null when the step does not state it. */
export function countOf(counts: CloseRunStep["counts"], name: string): number | null {
  const value = counts[name];
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;
}

/** What `GL_TIE_OUT` observed (04 T-CLS-01 `counts`; BUILD_SPEC CLO-20). */
export interface TieOut {
  readonly attached: boolean;
  /** The functional currency of the difference; "" where no trial balance is attached. */
  readonly currency: string;
  /** The difference as an API-C-06 decimal string, or null where the step states none. */
  readonly difference: string | null;
}

/** `GL_TIE_OUT` `counts`: `{trial_balance_attached}`, and with a trial balance `{currency, difference}`. */
export function tieOutOf(counts: CloseRunStep["counts"]): TieOut | null {
  const attached = counts.trial_balance_attached;
  if (typeof attached !== "boolean") {
    return null;
  }
  const currency = counts.currency;
  const difference = counts.difference;
  return {
    attached,
    currency: typeof currency === "string" ? currency : "",
    difference: typeof difference === "string" ? difference : null,
  };
}

/** `LOCK` `counts.locked_by`: the name of the person whose decision locked the period, or null. */
export function lockedByOf(counts: CloseRunStep["counts"]): string | null {
  const actor = counts.locked_by;
  if (typeof actor !== "object" || actor === null || !("display_name" in actor)) {
    return null;
  }
  const name = (actor as { readonly display_name: unknown }).display_name;
  return typeof name === "string" && name !== "" ? name : null;
}
