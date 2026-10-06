// Journal runs (04 API-R-38 and §16.7: API-S-JournalRun, API-S-JournalLine, API-S-PostingAck,
// API-S-JournalRunSummary and the journal commands; API-R-36 API-S-SubledgerLine for the drill; API-C-12
// jobs; SCREENS_B §3.1 to §3.4; BUILD_SPEC CLO-26). The row types are the generated schemas (D-87
// L6-5-Q-1): summary amounts are API-S-Money, and a batch carries `attempt_count` and `last_error`
// (T-SL-07; SF-06:run-batches). Money members stay API-C-06 strings (DG-FE-08), and the currencies of
// a page are registered from `GET /currencies` before it renders (DS-FMT-03).
import { send } from "../client";
import { fetchListPage, type ListPage, type ListQuery } from "../lists";
import { ApiProblem, isRefused, readProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { APPROVALS_PATH, ensureCurrencyCodes } from "./approvals";
import type { SubledgerLine } from "./subledger-lines";

export type Money = components["schemas"]["MoneyOut"];
export type ApprovalStatus = components["schemas"]["ApprovalRequestStatus"];
export type AccountRole = components["schemas"]["AccountRole"];
export type Job = components["schemas"]["JobOut"];
export type AuditEvent = components["schemas"]["AuditEventOut"];

/** E-34 `journal_state` (04 §3.4); batches carry the same literals. */
export type JournalState = components["schemas"]["JournalState"];
/** E-32 `journal_run_mode`. */
export type JournalRunMode = components["schemas"]["JournalRunMode"];
/** E-33 `journal_run_grain`. */
export type JournalRunGrain = components["schemas"]["JournalRunGrain"];
/** E-37 `gl_adapter`. */
export type GlAdapter = components["schemas"]["GlAdapter"];
/** E-36 `posting_ack_kind`. */
export type PostingAckKind = components["schemas"]["PostingAckKind"];
/** E-30 `je_type`. */
export type JeType = components["schemas"]["JeType"];

/** API-S-PostingAck. */
export type PostingAck = components["schemas"]["PostingAckOut"];

/**
 * A T-SL-07 batch: the `batches[]` member of API-S-JournalRun, `GET /journal-runs/{id}/batches` and
 * `GET /journal-batches/{id}`, with the export attempts and the last error (SF-06:run-batches).
 */
export type JournalBatch = components["schemas"]["JournalBatchOut"];

export type JournalRunPeriod = components["schemas"]["JournalRunPeriodOut"];

/** API-S-JournalRun. */
export type JournalRun = components["schemas"]["JournalRunOut"];

/** A list row: the run and the status of its approval request while it is `draft` (SMAP-06). */
export interface JournalRunRow extends JournalRun {
  readonly request_status: ApprovalStatus | null;
}

/** API-S-JournalLine. */
export type JournalLine = components["schemas"]["JournalLineOut"];

/** A summary row: sums per GL account and transaction currency, as API-S-Money. */
export type SummaryLine = components["schemas"]["JournalSummaryLineOut"];

/** A balance check per entity, basis and currency, as API-S-Money. */
export type BalanceCheck = components["schemas"]["JournalBalanceCheckOut"];

export type BalanceBasis = BalanceCheck["basis"];

/** API-S-JournalRunSummary (04 B3-D20; OQ-B-07). */
export type JournalRunSummary = components["schemas"]["JournalRunSummaryOut"];

export const JOURNAL_RUNS_PATH = "/api/v1/journal-runs";
export const JOURNAL_BATCHES_PATH = "/api/v1/journal-batches";
export const JOURNAL_LINES_PATH = "/api/v1/journal-lines";
export const JOBS_PATH = "/api/v1/jobs";
export const AUDIT_EVENTS_PATH = "/api/v1/audit-events";
/** The audit events are a list of the whole workspace: read with this permission for all entities. */
export const AUDIT_READ_PERMISSION = "audit.read";
/** [J] The `subject_type` of the journal run's jobs and audit events (04 T-PLT jobs; L6-5-Q-1). */
export const JOURNAL_RUN_OBJECT = "journal_run";
/** D-87 L6-5-Q-6: the audit action whose actor, time and comment name a run's cancellation. */
export const JOURNAL_RUN_CANCEL_ACTION = "journal_run.cancel";
/** A drill reads at most this many 200-line pages before it stops (DG-FE-07). */
const DRILL_MAX_PAGES = 50;
/** SCREENS_B §3.1 saved-view codes. */
export const RUNS_SCREEN_CODE = "SF-06";
export const LINES_SCREEN_CODE = "SF-06:run-lines";

export const JOURNAL_RUN_PERMISSION = "journal.run";
export const JOURNAL_EXPORT_PERMISSION = "journal.export";
export const REPORT_EXPORT_PERMISSION = "report.export";

export const EVERY_JOURNAL_RUN: QueryKey = queryKey("journal-runs", "tenant");
export const EVERY_JOURNAL_BATCH: QueryKey = queryKey("journal-batches", "tenant");

export function runRoute(runId: string, tab: "summary" | "lines" | "batches" = "summary"): string {
  return tab === "summary" ? `/journals/runs/${runId}` : `/journals/runs/${runId}/${tab}`;
}

/** The list filters of SF-06 (SCREENS_B §3.1 data bindings). */
export interface JournalRunQuery {
  readonly entity: string | null;
  readonly book: string | null;
  readonly period: string | null;
  readonly state: string | null;
  readonly mode: string | null;
}

export function journalRunsKey(query: JournalRunQuery): QueryKey {
  return queryKey("journal-runs", "tenant", { ...query, view: "list" });
}

export function journalRunKey(runId: string): QueryKey {
  return queryKey("journal-runs", "tenant", { id: runId });
}

export function journalRunSummaryKey(runId: string): QueryKey {
  return queryKey("journal-runs", "tenant", { id: runId, view: "summary" });
}

export function journalRunBatchesKey(runId: string): QueryKey {
  return queryKey("journal-runs", "tenant", { id: runId, view: "batches" });
}

/** The API filters of SF-06:run-lines (SCREENS_B §3.3). */
export interface JournalLineQuery {
  readonly accountCode: string | null;
  readonly accountRole: string | null;
  readonly contract: string | null;
  readonly batchId: string | null;
}

export function journalLinesKey(runId: string, query: JournalLineQuery): QueryKey {
  return queryKey("journal-runs", "tenant", {
    id: runId,
    view: "lines",
    account_code: query.accountCode,
    account_role: query.accountRole,
    contract: query.contract,
    batch_id: query.batchId,
  });
}

export function lineDrillKey(lineId: string, contract: string | null): QueryKey {
  return queryKey("journal-lines", "tenant", { id: lineId, view: "drill", contract });
}

export function journalBatchKey(batchId: string): QueryKey {
  return queryKey("journal-batches", "tenant", { id: batchId });
}

export function exportJobKey(runId: string): QueryKey {
  return queryKey("jobs", "tenant", { subject_id: runId, kind: "JOURNAL_EXPORT" });
}

export function runHistoryKey(runId: string): QueryKey {
  return queryKey("audit-events", "tenant", { object_type: JOURNAL_RUN_OBJECT, object_id: runId });
}

async function readJson<T>(path: string): Promise<T> {
  const response = await send("GET", path);
  if (!response.ok) {
    throw await readProblem(response);
  }
  return (await response.json()) as T;
}

/** Registers the minor units of `codes` (DS-FMT-03); the one helper lives in ./approvals (D-90a QA-L9-5a). */
export { ensureCurrencyCodes };

function runCurrencies(run: JournalRun): readonly string[] {
  return [
    run.totals.debit_functional.currency,
    run.totals.credit_functional.currency,
    ...run.batches.map((batch) => batch.txn_currency),
  ];
}

/** SMAP-06: the status of a draft run's approval request; a request the caller cannot read is null. */
async function requestStatus(run: JournalRun): Promise<ApprovalStatus | null> {
  if (run.state !== "draft" || run.approval_request_id === null) {
    return null;
  }
  try {
    const approval = await readJson<{ readonly status: ApprovalStatus }>(
      `${APPROVALS_PATH}/${run.approval_request_id}`,
    );
    return approval.status;
  } catch (error) {
    if (error instanceof ApiProblem && (error.status === 403 || error.status === 404)) {
      return null;
    }
    throw error;
  }
}

/** One page of `GET /journal-runs` (API-R-38), default sort `-period` (SCREENS_B §3.1). */
export async function fetchJournalRunsPage(
  query: JournalRunQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<JournalRunRow>> {
  const params: ListQuery = {
    entity: query.entity,
    book: query.book,
    period: query.period,
    state: query.state,
    mode: query.mode,
    sort: sort ?? "-period",
  };
  const page = await fetchListPage<JournalRun>(JOURNAL_RUNS_PATH, params, cursor);
  await ensureCurrencyCodes(page.items.flatMap(runCurrencies));
  const statuses = await Promise.all(page.items.map(requestStatus));
  return {
    ...page,
    items: page.items.map((run, index) => ({ ...run, request_status: statuses[index] ?? null })),
  };
}

/** `GET /journal-runs/{id}` with the request status of a draft run. */
export async function fetchJournalRun(runId: string): Promise<JournalRunRow> {
  const run = await readJson<JournalRun>(`${JOURNAL_RUNS_PATH}/${runId}`);
  await ensureCurrencyCodes(runCurrencies(run));
  return { ...run, request_status: await requestStatus(run) };
}

/** `GET /journal-runs/{id}/summary`, computed server-side (DS-FMT-02). */
export async function fetchJournalRunSummary(runId: string): Promise<JournalRunSummary> {
  const summary = await readJson<JournalRunSummary>(`${JOURNAL_RUNS_PATH}/${runId}/summary`);
  await ensureCurrencyCodes([
    ...summary.lines.map((line) => line.currency),
    ...summary.balance_checks.map((check) => check.currency),
  ]);
  return summary;
}

/** One page of `GET /journal-runs/{id}/batches`. */
export async function fetchRunBatchesPage(
  runId: string,
  cursor: string | null,
): Promise<ListPage<JournalBatch>> {
  const page = await fetchListPage<JournalBatch>(
    `${JOURNAL_RUNS_PATH}/${runId}/batches`,
    {},
    cursor,
  );
  await ensureCurrencyCodes(page.items.map((batch) => batch.txn_currency));
  return page;
}

/** One page of `GET /journal-runs/{id}/lines` (filters `account_code`, `account_role`, `contract`, `batch_id`). */
export async function fetchJournalLinesPage(
  runId: string,
  query: JournalLineQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<JournalLine>> {
  const page = await fetchListPage<JournalLine>(
    `${JOURNAL_RUNS_PATH}/${runId}/lines`,
    {
      account_code: query.accountCode,
      account_role: query.accountRole,
      contract: query.contract,
      batch_id: query.batchId,
      sort,
    },
    cursor,
  );
  await ensureCurrencyCodes(
    page.items.flatMap((line) => [line.debit_txn.currency, line.debit_functional.currency]),
  );
  return page;
}

/**
 * One page of `GET /journal-lines/{id}/drill`: the contributing subledger lines (T-SL-06). The route
 * takes no filter; the drawer's Contract filter applies client-side (D-87 L6-5-Q-9).
 */
export async function fetchLineDrillPage(
  lineId: string,
  cursor: string | null,
): Promise<ListPage<SubledgerLine>> {
  const page = await fetchListPage<SubledgerLine>(
    `${JOURNAL_LINES_PATH}/${lineId}/drill`,
    {},
    cursor,
  );
  await ensureCurrencyCodes(
    page.items.flatMap((line) => [line.amount_txn.currency, line.amount_functional.currency]),
  );
  return page;
}

/**
 * Every contributing subledger line of a journal line, as the drill answers them. A row names its
 * contract itself — API-S-SubledgerLine `contract_external_id` (04 §16.7; item
 * JRN-DRILL-CONTRACT-NAME-1), null for a line without a contract and for a contract outside the
 * reader's entity scope — so no contract is read: one read per distinct contract stood before the
 * first row (91 reads, 18.8 s together, for one line of the seeded tenant). D-87 L6-5-Q-9: the drawer's
 * Contract filter applies client-side by external id, so the drawer reads every page.
 */
export async function fetchLineDrill(lineId: string): Promise<readonly SubledgerLine[]> {
  const items: SubledgerLine[] = [];
  let cursor: string | null = null;
  for (let page = 0; page < DRILL_MAX_PAGES; page += 1) {
    const result: ListPage<SubledgerLine> = await fetchLineDrillPage(lineId, cursor);
    items.push(...result.items);
    cursor = result.nextCursor;
    if (cursor === null) {
      break;
    }
  }
  return items;
}

/** `GET /journal-batches/{id}`: attempts, last error and acknowledgements. */
export async function fetchJournalBatch(batchId: string): Promise<JournalBatch> {
  const batch = await readJson<JournalBatch>(`${JOURNAL_BATCHES_PATH}/${batchId}`);
  await ensureCurrencyCodes([batch.txn_currency]);
  return batch;
}

/** More active jobs than one run has at a time: an export or the retries of its batches, and an exit. */
const ACTIVE_JOBS_LIMIT = 10;

/**
 * SMAP-07: the queued and running `JOURNAL_EXPORT` jobs of a run. An export and a retry carry no
 * `mode`; the cancel of a failed run and the hand-over of a failed batch are such jobs with one
 * (`exitModeOf`), and a retry of one batch can run beside the hand-over of another. The API lists a job
 * to the member who started it and to a holder of `audit.read` (04 API-C-12). A read of the jobs the
 * API refuses answers the empty list — no job to show (SCREENS §0.6 SCR-PERM-02) — so the query
 * settles and is not sent again.
 */
export async function fetchActiveExportJobs(runId: string): Promise<readonly Job[]> {
  try {
    const page = await fetchListPage<Job>(
      JOBS_PATH,
      {
        kind: ["JOURNAL_EXPORT"],
        state: ["QUEUED", "RUNNING"],
        subject_type: JOURNAL_RUN_OBJECT,
        subject_id: runId,
      },
      null,
      { limit: ACTIVE_JOBS_LIMIT, count: false },
    );
    return page.items;
  } catch (error) {
    if (isRefused(error)) {
      return [];
    }
    throw error;
  }
}

/**
 * DS-CMP-12 history of a run: `GET /audit-events?object_type=journal_run&object_id=<id>`; null when
 * the API refuses the read (ruling R-28: the audit events are read with `audit.read` for all entities).
 */
export async function fetchRunHistory(runId: string): Promise<readonly AuditEvent[] | null> {
  try {
    const page = await fetchListPage<AuditEvent>(
      AUDIT_EVENTS_PATH,
      { object_type: JOURNAL_RUN_OBJECT, object_id: runId, sort: "-occurred_at" },
      null,
      { limit: 200, count: false },
    );
    return page.items;
  } catch (error) {
    if (isRefused(error)) {
      return null;
    }
    throw error;
  }
}

/** `GET /journal-batches/{id}/download`: the ZIP of the batch CSV and its JSON manifest (REQ-JE-011). */
export function batchDownloadHref(batchId: string): string {
  return `${JOURNAL_BATCHES_PATH}/${batchId}/download`;
}

/** The file name of `Content-Disposition: attachment; filename="…"`, else null. */
function attachmentName(response: Response): string | null {
  const match = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") ?? "");
  return match?.[1] ?? null;
}

/**
 * The batch's ZIP saved under the name the API gives it — its external id with the colons replaced
 * (04 §16.7 `download`). The file is fetched first: a refused download (409 `invalid-transition`, PRD
 * ERR-79, for a batch whose lines differ from what was calculated and approved) throws its `ApiProblem`
 * and saves nothing, where a plain link saved the problem under the batch's name.
 */
export async function downloadBatch(
  batch: Pick<JournalBatch, "id" | "external_id">,
): Promise<void> {
  const response = await send("GET", batchDownloadHref(batch.id));
  if (!response.ok) {
    throw await readProblem(response);
  }
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = attachmentName(response) ?? `${batch.external_id.replace(/:/g, "_")}.zip`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

/**
 * The two exits of a failed run that a job decides (04 §16.7 rev 1.159; T-SL-07 "The ways out of
 * `failed`"): `mode` of the `JOURNAL_EXPORT` job that `POST /journal-runs/{id}/cancel` answers for a run
 * with a failed batch, and of the job of `POST /journal-batches/{id}/hand-over`.
 */
export type ExitMode = "CANCEL" | "HAND_OVER";

/** The exit a job decides; null for an export and for a retry, which carry no mode. */
export function exitModeOf(job: Pick<Job, "mode">): ExitMode | null {
  return job.mode === "CANCEL" || job.mode === "HAND_OVER" ? job.mode : null;
}

/** How an exit job ended (04 §16.7 "What a screen reads"). */
export interface ExitEnding {
  /** `result.outcome` is `CANCELLED` or `HANDED_OVER`. */
  readonly done: boolean;
  /**
   * Why not: `result.refusal.detail` of a job that decided against it (PRD ERR-73 and the sentences of
   * 04 §16.7), else the problem of a job that did not decide — a ledger that could not be reached.
   */
  readonly sentence: string | null;
  /** The job decided: it ended with an outcome, not `FAILED` or `CANCELLED`. */
  readonly decided: boolean;
}

function detailOf(problem: unknown): string | null {
  if (typeof problem !== "object" || problem === null) {
    return null;
  }
  const detail = (problem as { readonly detail?: unknown }).detail;
  return typeof detail === "string" && detail !== "" ? detail : null;
}

/** `result.outcome` alone tells "done" from "not done, and why". */
export function exitEnding(job: Pick<Job, "result" | "problem">): ExitEnding {
  const outcome = job.result?.outcome;
  if (outcome === "CANCELLED" || outcome === "HANDED_OVER") {
    return { done: true, sentence: null, decided: true };
  }
  if (outcome === "NOT_CANCELLED" || outcome === "NOT_HANDED_OVER") {
    return { done: false, sentence: detailOf(job.result?.refusal), decided: true };
  }
  return {
    done: false,
    sentence: detailOf(job.problem) ?? job.problem?.title ?? null,
    decided: false,
  };
}

/**
 * An item of `result.waiting` of a `JOURNAL_EXPORT` job without a mode (04 §16.7, rows `retry` and
 * `export`, rev 1.221): a batch of the run whose export message is due again when the job ends, and the
 * instant from which it is sent. The message keeps its schedule, so the job sent nothing for it, or
 * tried and the ledger did not answer.
 */
export interface WaitingBatch {
  readonly journal_batch_id: string;
  readonly next_attempt_at: string;
}

/** An RFC 3339 instant in UTC, as 04 §16.7 states `next_attempt_at`. */
const UTC_INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/;

/**
 * `result.waiting` as far as it is well formed; none for a job of an API that states no `waiting`. A
 * job's `result` is a free object in the OpenAPI document, so an item is read by its shape: a batch id
 * and an instant in UTC, the only kind the page formats (DG-FE-20).
 */
export function waitingBatches(job: Pick<Job, "result">): readonly WaitingBatch[] {
  const waiting: unknown = job.result?.waiting;
  if (!Array.isArray(waiting)) {
    return [];
  }
  return waiting.flatMap((item: unknown) => {
    if (typeof item !== "object" || item === null) {
      return [];
    }
    const { journal_batch_id: id, next_attempt_at: at } = item as Readonly<Record<string, unknown>>;
    return typeof id === "string" && typeof at === "string" && UTC_INSTANT.test(at)
      ? [{ journal_batch_id: id, next_attempt_at: at }]
      : [];
  });
}

/**
 * How the retry of a batch ended (SCREENS_B §3.2 States "Sending again", rev 1.77). The job of a retry
 * ends `SUCCEEDED` whether or not it sent the batch (04 §16.7), so the ending is read from the batch as
 * the run states it after the job, and only then from the job.
 */
export type RetryEnding =
  /** The batch left `failed`: the adapter took it. */
  | { readonly kind: "sent" }
  /** `result.waiting` names it: it is sent again from `at`, and no earlier for the retry. */
  | { readonly kind: "waiting"; readonly at: string }
  /** The job failed or was cancelled over a batch that is still `failed`. */
  | { readonly kind: "failed"; readonly sentence: string | null }
  /** Still `failed`, and the job says no more: the ledger refused it again, as the batch's error says. */
  | { readonly kind: "refused" };

const SENT: ReadonlySet<JournalBatch["state"]> = new Set<JournalBatch["state"]>([
  "exported",
  "acknowledged",
]);

export function retryEnding(
  job: Pick<Job, "state" | "result" | "problem">,
  batchId: string,
  after: Pick<JournalRun, "batches">,
): RetryEnding {
  const batch = after.batches.find((item) => item.id === batchId);
  if (batch !== undefined && SENT.has(batch.state)) {
    return { kind: "sent" };
  }
  const waiting = waitingBatches(job).find((item) => item.journal_batch_id === batchId);
  if (waiting !== undefined) {
    return { kind: "waiting", at: waiting.next_attempt_at };
  }
  if (job.state === "FAILED" || job.state === "CANCELLED") {
    return { kind: "failed", sentence: detailOf(job.problem) ?? job.problem?.title ?? null };
  }
  return { kind: "refused" };
}

/**
 * How a followed job of the run's own export ended (SCREENS_B §3.2 States "Exporting", rev 1.85). As for
 * a retry the run decides before the job: a job that ended `FAILED` over a run it exported all the same
 * is the export it made. A job that failed or was cancelled over a run that was exported before it
 * began repeated nothing; over a run that is still not exported it exported nothing.
 */
export type ExportEnding =
  /** The run was not exported when the job began, and is now. */
  | { readonly kind: "exported" }
  /** "Export again" of an exported run, taken: nothing is posted twice (PRD BR-JE-02). */
  | { readonly kind: "repeated" }
  /** The job failed or was cancelled over a run that is not exported. */
  | { readonly kind: "notExported"; readonly sentence: string | null }
  /** The job failed or was cancelled over a run that was exported before it began. */
  | { readonly kind: "notRepeated"; readonly sentence: string | null }
  /** Nothing to say: a job that ended well and exported nothing new, sent by another frame. */
  | { readonly kind: "none" };

export function exportEnding(
  job: Pick<Job, "state" | "problem">,
  before: {
    /** The run was exported when the frame began to follow the job. */
    readonly exported: boolean;
    /** This frame sent the job as "Export again". */
    readonly again: boolean;
  },
  after: Pick<JournalRun, "state">,
): ExportEnding {
  const failed = job.state === "FAILED" || job.state === "CANCELLED";
  const sentence = detailOf(job.problem) ?? job.problem?.title ?? null;
  // "Export again" is offered on an Exported run alone, so `again` is never without `exported`.
  if (before.exported) {
    if (failed) {
      return { kind: "notRepeated", sentence };
    }
    return before.again ? { kind: "repeated" } : { kind: "none" };
  }
  if (after.state === "exported" || after.state === "acknowledged") {
    return { kind: "exported" };
  }
  return failed ? { kind: "notExported", sentence } : { kind: "none" };
}

/** SMAP-08: batches `acknowledged` of all batches. */
export function acknowledgedBatches(batches: readonly JournalBatch[]): number {
  return batches.filter((batch) => batch.state === "acknowledged").length;
}
