// Reconciliations (04 §15.3 API-R-40, §16.8 API-S-ReconciliationCreate, API-S-Reconciliation,
// API-S-ReconciliationItem and the reconciliation commands; T-CLS-06 to T-CLS-08; SCREENS_B §2.1, §2.2;
// BUILD_SPEC CLO-25, CLO-17). Every generation is a row and `is_current` marks the latest of its kind,
// entity, book and period: the list filter `is_current` reads the period's reconciliations (true) or the
// generations they replaced (false). Money members stay API-C-06 strings (DG-FE-08), and the currencies
// of a read are registered from `GET /currencies` before it renders (DS-FMT-03).
import { send } from "../client";
import { fetchListPage, type ListPage } from "../lists";
import { ApiProblem, readProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { ensureCurrencyCodes } from "./approvals";
import { fetchReportRun } from "./reports";

/** API-S-Reconciliation. */
export type ReconciliationOut = components["schemas"]["ReconciliationOut"];
/**
 * API-S-Reconciliation `summary`: one currency of `totals` with its key figures, summed by the server
 * because a client never sums money (DG-FE-08; SCREENS_B §2.2 "Key figures").
 */
export type ReconciliationSummary = components["schemas"]["ReconciliationSummaryOut"];
/**
 * API-S-Reconciliation `trial_balance`: the latest `attach-trial-balance` request of a
 * subledger-to-GL reconciliation with its job, as every reader of the reconciliation sees it (the job
 * itself is read by its initiator only). `attached_at` is null until the reconciliation has its source.
 */
export type ReconciliationTrialBalance = components["schemas"]["ReconciliationTrialBalanceOut"];
/** `{id, name}` of a general-ledger connection (`gl_connections`) or of a stored file. */
export type ReconciliationNamed = components["schemas"]["ReconciliationNamedOut"];
/** API-S-ReconciliationItem. */
export type ReconciliationItem = components["schemas"]["ReconciliationItemOut"];
/** One T-CLS-06 `totals` row. */
export type ReconciliationTotal = components["schemas"]["ReconciliationTotalOut"];
/** A T-CLS-08 sign-off of a reconciliation. */
export type ReconciliationSignoff = components["schemas"]["ReconciliationSignoffOut"];
/** E-58 `reconciliation_kind`. */
export type ReconciliationKind = components["schemas"]["ReconciliationKind"];
/** E-59 `reconciliation_status`. */
export type ReconciliationStatus = components["schemas"]["ReconciliationStatus"];
/** E-99 `signoff_role`. */
export type SignoffRole = components["schemas"]["SignoffRole"];
/** T-CLS-07 `item_kind`. */
export type ReconciliationItemKind = ReconciliationItem["item_kind"];
/** The request bodies of the API-R-40 commands (04 §16.8). */
export type ReconciliationCreateIn = components["schemas"]["ReconciliationCreateIn"];
/**
 * API-S-ReconciliationAttach (`POST /reconciliations/{id}/attach-trial-balance`): pull through a GL
 * connection (`{source: "ADAPTER", integration_connection_id}`), or compare an uploaded
 * `IMPORT_SOURCE` file (`{file_id}`).
 */
export type ReconciliationAttachIn = components["schemas"]["ReconciliationAttachIn"];
export type ReconciliationItemUpdateIn = components["schemas"]["ReconciliationItemUpdateIn"];
export type ReconciliationSignIn = components["schemas"]["ReconciliationSignIn"];
export type ReconciliationReopenIn = components["schemas"]["ReconciliationReopenIn"];

/** A reconciliation with the number of its report run (SCREENS_B §2.1 "Report run"). */
export interface Reconciliation extends ReconciliationOut {
  /** Null without a run, and for a run the caller cannot read. */
  readonly report_run_no: string | null;
}

export const RECONCILIATIONS_PATH = "/api/v1/reconciliations";
/** The 202 header that names the reconciliation a generation inserts (04 §16.8). */
export const RECONCILIATION_ID_HEADER = "X-Erev-Reconciliation-Id";

/** PRD ACT-33: generate, explain and sign as preparer. */
export const RECON_PREPARE_PERMISSION = "recon.prepare";
/** PRD ACT-34: sign as reviewer and reopen (supervisor ruling R-54 (c)). */
export const RECON_SIGNOFF_PERMISSION = "recon.signoff";
/** PRD ACT-45, SoD-7 function A: its holder is refused the reviewer's sign-off (04 §16.8). */
export const INTEGRATION_MANAGE_PERMISSION = "integration.manage";

/** E-58 in the order the screens list the kinds (SCREENS_B §1.1). */
export const RECONCILIATION_KINDS: readonly ReconciliationKind[] = [
  "BILLING_TO_SUBLEDGER",
  "SUBLEDGER_TO_GL",
  "CONTRACT_BALANCE_ROLLFORWARD",
  "RPO_ROLLFORWARD",
  "MIGRATION_OPENING_BALANCE",
];

/**
 * The kinds `POST /reconciliations` generates (04 §16.8 API-S-ReconciliationCreate): another kind
 * answers 422, so the "Generate reconciliation" menu lists these only (XR-14). The rollforward kinds
 * are report runs and a migration's reconciliation is written by its batch.
 */
export const GENERATED_KINDS: readonly ReconciliationKind[] = [
  "BILLING_TO_SUBLEDGER",
  "SUBLEDGER_TO_GL",
];

/** 04 E-04 states in which a reconciliation is generated, explained and signed (PRD SM-09). */
const WORKABLE_PERIOD_STATES: ReadonlySet<string> = new Set(["open", "closing", "reopened"]);

export function periodIsWorkable(state: string | null | undefined): boolean {
  return state !== null && state !== undefined && WORKABLE_PERIOD_STATES.has(state);
}

/** A page of generations read at most this many times before the read stops (DG-FE-07). */
const MAX_PAGES = 25;

/** Every reconciliation read: the period lists, the records and their differences. */
export const EVERY_RECONCILIATION: QueryKey = queryKey("reconciliations", "tenant");

/** The entity, book and period of SF-05 (SCREENS_B §2.1 data bindings). */
export interface ReconciliationScope {
  readonly entity: string;
  readonly book: string;
  readonly period: string;
}

/** The period's reconciliations (`current`) or the generations they replaced. */
export function reconciliationsKey(scope: ReconciliationScope, current: boolean): QueryKey {
  return queryKey("reconciliations", "tenant", { ...scope, view: current ? "current" : "earlier" });
}

export function reconciliationKey(reconciliationId: string): QueryKey {
  return queryKey("reconciliations", "tenant", { id: reconciliationId });
}

export function reconciliationItemsKey(reconciliationId: string): QueryKey {
  return queryKey("reconciliations", "tenant", { id: reconciliationId, view: "items" });
}

/** SCREENS RT-102 SF-05:reconciliations and RT-103 SF-05:reconciliation. */
export function reconciliationsRoute(scope: ReconciliationScope): string {
  return `/close/${encodeURIComponent(scope.entity)}/${encodeURIComponent(scope.book)}/${encodeURIComponent(scope.period)}/reconciliations`;
}

export function reconciliationRoute(scope: ReconciliationScope, reconciliationId: string): string {
  return `${reconciliationsRoute(scope)}/${reconciliationId}`;
}

/** The scope a reconciliation belongs to, as its route names it. */
export function scopeOf(
  reconciliation: Pick<ReconciliationOut, "entity" | "book" | "period">,
): ReconciliationScope {
  return {
    entity: reconciliation.entity.code,
    book: reconciliation.book,
    period: reconciliation.period.period_key,
  };
}

async function readJson<T>(path: string): Promise<T> {
  const response = await send("GET", path);
  if (!response.ok) {
    throw await readProblem(response);
  }
  return (await response.json()) as T;
}

function moneyCurrencies(reconciliation: ReconciliationOut): readonly string[] {
  return [
    ...reconciliation.totals.map((total) => total.currency),
    ...(reconciliation.unexplained_other_amount === null
      ? []
      : [reconciliation.unexplained_other_amount.currency]),
  ];
}

/** The number of a reconciliation's report run; a run the caller cannot read keeps none. */
async function reportRunNo(reconciliation: ReconciliationOut): Promise<string | null> {
  if (reconciliation.report_run_id === null) {
    return null;
  }
  try {
    return (await fetchReportRun(reconciliation.report_run_id)).report_run_no;
  } catch (error) {
    if (error instanceof ApiProblem && (error.status === 403 || error.status === 404)) {
      return null;
    }
    throw error;
  }
}

async function withRunNumbers(
  reconciliations: readonly ReconciliationOut[],
): Promise<readonly Reconciliation[]> {
  await ensureCurrencyCodes(reconciliations.flatMap(moneyCurrencies));
  const numbers = await Promise.all(reconciliations.map(reportRunNo));
  return reconciliations.map((reconciliation, index) => ({
    ...reconciliation,
    report_run_no: numbers[index] ?? null,
  }));
}

/**
 * The reconciliations of the entity, book and period, newest first (`GET /reconciliations`, sort
 * `-created_at`): with `current` the latest generation of each kind (`is_current=true`), without it the
 * generations a later one replaced (`is_current=false`).
 */
export async function fetchPeriodReconciliations(
  scope: ReconciliationScope,
  current: boolean,
): Promise<readonly Reconciliation[]> {
  const items: ReconciliationOut[] = [];
  let cursor: string | null = null;
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const result: ListPage<ReconciliationOut> = await fetchListPage<ReconciliationOut>(
      RECONCILIATIONS_PATH,
      {
        entity: scope.entity,
        book: scope.book,
        period: scope.period,
        is_current: current ? "true" : "false",
        sort: "-created_at",
      },
      cursor,
      { count: false },
    );
    items.push(...result.items);
    cursor = result.nextCursor;
    if (cursor === null) {
      break;
    }
  }
  return withRunNumbers(items);
}

/** `GET /reconciliations/{id}` with its sign-offs. */
export async function fetchReconciliation(reconciliationId: string): Promise<Reconciliation> {
  const reconciliation = await readJson<ReconciliationOut>(
    `${RECONCILIATIONS_PATH}/${reconciliationId}`,
  );
  const [row] = await withRunNumbers([reconciliation]);
  return row ?? { ...reconciliation, report_run_no: null };
}

/** The differences of a reconciliation, with whether the read stopped before the last page. */
export interface ReconciliationItems {
  readonly items: readonly ReconciliationItem[];
  /** True when more differences exist than the read holds. */
  readonly truncated: boolean;
}

/**
 * Every difference of a reconciliation in the order it was itemised (`GET /reconciliations/{id}/items`,
 * default sort), so the screen can count the differences without an explanation before the preparer
 * signs (SCREENS_B §2.2).
 */
export async function fetchReconciliationItems(
  reconciliationId: string,
): Promise<ReconciliationItems> {
  const items: ReconciliationItem[] = [];
  let cursor: string | null = null;
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const result: ListPage<ReconciliationItem> = await fetchListPage<ReconciliationItem>(
      `${RECONCILIATIONS_PATH}/${reconciliationId}/items`,
      {},
      cursor,
      { count: false },
    );
    items.push(...result.items);
    cursor = result.nextCursor;
    if (cursor === null) {
      break;
    }
  }
  await ensureCurrencyCodes(items.map((item) => item.currency));
  return { items, truncated: cursor !== null };
}

/** The reconciliation id of a finished `RECONCILIATION_GENERATE` job (`result.href`), if it names one. */
export function reconciliationIdOf(href: string | null | undefined): string | null {
  const match = /\/reconciliations\/([0-9a-f-]{36})(?:$|[/?#])/.exec(href ?? "");
  return match?.[1] ?? null;
}

/** The sign-offs of one role, earliest first as the API lists them. */
export function signoffsOf(
  reconciliation: Pick<ReconciliationOut, "signoffs">,
  role: SignoffRole,
): readonly ReconciliationSignoff[] {
  return reconciliation.signoffs.filter((signoff) => signoff.role === role);
}

/**
 * Where a reconciliation stands with its trial balance (SCREENS_B §2.2 "States"): only a
 * subledger-to-GL reconciliation has one. `attaching` and `failed` come from API-S-Reconciliation
 * `trial_balance`, so every reader of the record sees them, not only the job's initiator.
 */
export type TrialBalanceState = "none" | "missing" | "attaching" | "failed" | "attached";

export function trialBalanceState(
  reconciliation:
    | Pick<ReconciliationOut, "kind" | "source_file_id" | "sync_run_id" | "trial_balance">
    | undefined,
): TrialBalanceState {
  if (reconciliation === undefined || reconciliation.kind !== "SUBLEDGER_TO_GL") {
    return "none";
  }
  const request = reconciliation.trial_balance ?? null;
  if (
    reconciliation.source_file_id !== null ||
    reconciliation.sync_run_id !== null ||
    (request !== null && request.attached_at !== null)
  ) {
    return "attached";
  }
  if (request === null) {
    return "missing";
  }
  switch (request.job.state) {
    case "QUEUED":
    case "RUNNING":
      return "attaching";
    case "FAILED":
    case "CANCELLED":
      return "failed";
    default:
      // A finished attach has written the source; a read that does not show it yet shows none.
      return "missing";
  }
}

/** True for an amount string whose every digit is zero (no numeric conversion, DG-FE-08). */
export function isZeroAmount(amount: string): boolean {
  return /^-?0+(?:\.0+)?$/.test(amount);
}

/** SM-09: a difference counts until it carries an explanation (04 §16.8 `prepare`). */
export function needsExplanation(
  item: Pick<ReconciliationItem, "difference" | "explanation">,
): boolean {
  return (
    !isZeroAmount(item.difference.amount) &&
    (item.explanation === null || item.explanation.trim() === "")
  );
}
