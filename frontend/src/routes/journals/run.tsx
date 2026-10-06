// SF-06:run Journal run: summary (SCREENS_B §3.2; §0.3 SB-R-05, SB-R-06, SB-R-08; §0.4 E-34 SMAP-05 to
// SMAP-08; SCREENS RT-29; DESIGN_SYSTEM DS-CMP-06, DS-CMP-07, DS-CMP-09 to DS-CMP-12, DS-CMP-19, DS-CMP-24,
// DS-CMP-29, DS-FMT-04 to DS-FMT-06; 04 API-R-38 §16.7; BUILD_SPEC CLO-26). The record frame shared by the
// Summary, Lines and Batches route tabs: header with the E-34 chip and the action bar of §3.2, the totals
// strip, the partially acknowledged, failed and sandbox banners, the export progress and the History drawer.
// The Summary tab renders the API's totals by account and its balance checks; every figure is an API
// string rendered through the format module, never a converted number (DG-FE-08, DS-FMT-02).
//
// The exits of a failed run (§3.2 and §3.4 rev 1.71; 04 §16.7 rev 1.159; item JRN-FAILED-EXITS-UI-1): the
// cancel of a run with a failed batch and the hand-over of a failed batch are accepted as a job, and a
// job decides them after it asked the ledger. The frame follows that job by its id — the one a command of
// this frame was accepted as, or the run's active one that `GET /jobs` lists — shows its progress in the
// header with the actions hidden, and says what it decided: a toast when it is done, a banner with the
// job's sentence when it is not.
//
// The jobs without a mode (§3.2 and §3.4 rev 1.77; 04 §16.7 rows `retry` and `export`, rev 1.221; item
// JRN-RETRY-FOLLOW-1): the retry of a failed batch and the run's export are followed the same way. Such
// a job ends SUCCEEDED whether or not it sent a batch, so its ending is read from the run after it: of a
// retry, the batch as it then is and the job's `result.waiting`; of an export, the run's state. An
// ending that needs more than the two lines of a toast (DS-CMP-22) is a banner of the frame.
import { useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { type ReactNode, useCallback, useEffect, useId, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";

import { contextSearch } from "../../app/shell/IconRail";
import { sandboxTenantName, useShellSession } from "../../app/shell/SandboxIndicator";
import { DataGrid } from "../../components/data-grid/DataGrid";
import type { GridColumn, GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { JobProgress, type JobProgressJob } from "../../components/feedback/JobProgress";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useNoAnswer, useToast } from "../../components/feedback/Toast";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { ClockCounterClockwise, DotsThree, DownloadSimple } from "../../components/icons/registry";
import { Money } from "../../components/money/Money";
import { NoValue } from "../../components/money/Num";
import { type MetaItem, RecordHeader } from "../../components/record/RecordHeader";
import { type RouteTab, RouteTabs } from "../../components/record/Tabs";
import { Timeline, type TimelineEvent } from "../../components/record/Timeline";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { Menu, type MenuItem } from "../../components/ui/Menu";
import { Modal } from "../../components/ui/Modal";
import { chipFor, type ChipSpec, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { type CommandState, useCommand } from "../../lib/api/commands";
import { isTerminal, JOB_POLL_INTERVAL_MS, useJob } from "../../lib/api/jobs";
import { ApiProblem } from "../../lib/api/problems";
import { approvalKey, currencyRegistered, fetchApproval } from "../../lib/api/queries/approvals";
import {
  acknowledgedBatches,
  AUDIT_READ_PERMISSION,
  type AuditEvent,
  type BalanceCheck,
  downloadBatch,
  EVERY_JOURNAL_BATCH,
  EVERY_JOURNAL_RUN,
  exitEnding,
  type ExitMode,
  exitModeOf,
  exportEnding,
  exportJobKey,
  fetchActiveExportJobs,
  fetchJournalRun,
  fetchJournalRunSummary,
  fetchRunHistory,
  type GlAdapter,
  JOURNAL_EXPORT_PERMISSION,
  JOURNAL_RUN_CANCEL_ACTION,
  JOURNAL_RUN_PERMISSION,
  JOURNAL_RUNS_PATH,
  type JournalBatch,
  type JournalRunGrain,
  type JournalRunMode,
  type JournalRunRow,
  type JournalRunSummary,
  journalRunKey,
  journalRunSummaryKey,
  REPORT_EXPORT_PERMISSION,
  retryEnding,
  runHistoryKey,
  runRoute,
  type SummaryLine,
} from "../../lib/api/queries/journal-runs";
import { useMe } from "../../lib/api/queries/me";
import { queryKey } from "../../lib/api/query-keys";
import { formatMoney, formatNumber, formatTimestamp, NO_VALUE } from "../../lib/format";
import { hasMessage, t } from "../../lib/i18n/t";
import { withParams } from "../../lib/url/params";
import { type Choice, SelectField, TextField } from "../contracts/drawers/common";
import { useBuiltPaths } from "../settings/index";

/** SCREENS SCR-URL-01 to SCR-URL-03: the context a journal link keeps. */
export const CONTEXT = ["entity", "period", "book"] as const;
/** SCREENS RT-57 SF-12:request, the target of "View approval request". */
export const APPROVAL_REQUEST_ROUTE = "/approvals/requests/:requestId";

export type RunTab = "summary" | "lines" | "batches";

// ---------------------------------------------------------------------------------------------------
// Labels and chips shared by the SF-06 screens.

export function bookText(code: string): string {
  return code === "ASC606" || code === "IFRS15" || code === "LEGACY"
    ? t(`journals.book.${code}`)
    : code;
}

export function modeText(mode: JournalRunMode): string {
  return t(`journals.mode.${mode}`);
}

export function grainText(grain: JournalRunGrain): string {
  return t(`journals.grain.${grain}`);
}

export function adapterText(adapter: GlAdapter | null): string {
  return adapter === null ? NO_VALUE : t(`journals.adapter.${adapter}`);
}

/** SCREENS_B §0.4 E-34 with SMAP-05 to SMAP-08: the run's chip from its state, request and export job. */
export function runChip(
  run: Pick<JournalRunRow, "state" | "batches" | "request_status">,
  exportJobState: string | null = null,
): ChipSpec | null {
  return chipFor("E-34", run.state, {
    job_state: run.state === "approved" ? exportJobState : null,
    request_status: run.request_status,
    acknowledged_batches: run.state === "exported" ? acknowledgedBatches(run.batches) : null,
    batch_count: run.batches.length,
  });
}

export function RunStateChip({
  run,
  exportJobState = null,
}: {
  readonly run: Pick<JournalRunRow, "state" | "batches" | "request_status">;
  readonly exportJobState?: string | null;
}) {
  const chip = runChip(run, exportJobState);
  return chip === null ? null : <StatusChip status={chip.status} caption={chip.caption} />;
}

/** A money cell; an amount whose currency is not registered shows no value (DS-FMT-03). */
export function MoneyCell({
  value,
  currency,
}: {
  readonly value: string | null;
  readonly currency: string;
}) {
  return value === null || !currencyRegistered(currency) ? (
    <NoValue />
  ) : (
    <Money value={value} currency={currency} variant="cell" />
  );
}

export function moneyText(value: string, currency: string, variant: "cell" | "inline"): string {
  return currencyRegistered(currency) ? formatMoney(value, currency, { variant }) : NO_VALUE;
}

export function Mono({ children }: { readonly children: ReactNode }) {
  return <span className="font-mono text-mono-sm text-fg-1">{children}</span>;
}

/** SCREENS SCR-ST-05: the negative region banner with the problem title and Retry. */
export function RetryBanner({
  title,
  problem,
  onRetry,
}: {
  readonly title: string;
  readonly problem: unknown;
  readonly onRetry: () => void;
}) {
  return (
    <Banner
      tone="negative"
      title={title}
      actions={
        <Button variant="link" onClick={onRetry}>
          {t("journals.retry")}
        </Button>
      }
    >
      {problem instanceof ApiProblem ? <p>{problem.title}</p> : null}
      {problem instanceof ApiProblem && problem.requestId !== null ? (
        <p>{t("journals.reference", { reference: problem.requestId })}</p>
      ) : null}
    </Banner>
  );
}

// ---------------------------------------------------------------------------------------------------
// The action state of §3.2 "Action bar".

export type ActionState =
  | "calculated"
  | "pending"
  | "approved"
  | "exporting"
  | "exported"
  | "failed"
  | "posted"
  | "cancelled";

export function actionState(run: JournalRunRow, exportJobState: string | null): ActionState {
  switch (run.state) {
    case "draft":
      return run.request_status === "PENDING" ? "pending" : "calculated";
    case "approved":
      return exportJobState === "QUEUED" || exportJobState === "RUNNING" ? "exporting" : "approved";
    case "exported":
      return "exported";
    case "failed":
      return "failed";
    case "acknowledged":
      return "posted";
    case "cancelled":
      return "cancelled";
  }
}

const EXPORTABLE: ReadonlySet<ActionState> = new Set(["approved", "exported", "failed", "posted"]);

// ---------------------------------------------------------------------------------------------------
// The record frame.

/**
 * A job of the run the frame follows to its end (§3.2 States): a cancel or a hand-over (rev 1.71), the
 * retry of a batch, or a job without a mode the frame names no batch for (rev 1.77).
 */
export type FollowedJob =
  | {
      readonly jobId: string;
      readonly mode: ExitMode;
      /**
       * "<batch> · <chunk>" of the hand-over this frame sent; null for a job it found under way,
       * because API-S-Job names no batch.
       */
      readonly batch: string | null;
    }
  | {
      readonly jobId: string;
      /** The row's "Retry export" of §3.4, sent by this frame: its ending is said of the batch. */
      readonly mode: "RETRY";
      readonly batch: string;
      readonly batchId: string;
    }
  | {
      readonly jobId: string;
      /**
       * A job without a mode and without a batch the frame can name: the run's export, or a retry
       * another frame sent.
       */
      readonly mode: "EXPORT";
      readonly batch: null;
      /** What this frame sent it as: "Export", "Export again", or nothing — it found the job under way. */
      readonly sent: "export" | "again" | null;
      /** The run was `exported` or `acknowledged` when the frame began to follow the job. */
      readonly exported: boolean;
    };

/** A job that did not do what was asked, as its banner says it. */
interface NotDone {
  readonly title: string;
  readonly sentence: string | null;
  /** The reference of a job that did not decide: it failed, or it was cancelled. */
  readonly reference: string | null;
}

/** A retry that did not send its batch (§3.2 States "Sending again"): the batch waits, or the job failed. */
interface RetryNotSent extends NotDone {
  readonly jobId: string;
  readonly tone: "warning" | "negative";
}

/**
 * A job of the run's own export that failed or was cancelled (§3.2 States "Exporting", rev 1.85): over a
 * run that is not exported it exported nothing, over an Exported run it repeated nothing.
 */
interface ExportNotDone extends NotDone {
  readonly jobId: string;
}

/** A download the API refused (§3.2 "Download batch files", rev 1.77). */
interface RefusedDownload {
  /** "<batch> · <chunk>". */
  readonly batch: string;
  readonly lines: readonly string[];
}

/** The run was exported: SMAP-08's `exported`, or `acknowledged` once every batch is. */
function isExported(run: Pick<JournalRunRow, "state">): boolean {
  return run.state === "exported" || run.state === "acknowledged";
}

/** "<batch> · <chunk>" (SCREENS_B §3.4 "Batch"), a number pair rather than prose. */
export function batchLabel(batch: Pick<JournalBatch, "batch_no" | "chunk_no">): string {
  return `${formatNumber(batch.batch_no, { kind: "count" })} · ${formatNumber(batch.chunk_no, {
    kind: "count",
  })}`;
}

/** The texts of a followed exit: its progress label, its toast and the title of its banner. */
const EXIT_TEXT = {
  cancel: {
    progress: "journals.run.exit.cancelling",
    done: "journals.run.exit.cancelled",
    refused: "journals.run.exit.notCancelled",
  },
  handOver: {
    progress: "journals.run.exit.handingOver",
    done: "journals.run.exit.handedOver",
    refused: "journals.run.exit.notHandedOver",
  },
  // A hand-over this frame did not send, told by its run.
  handOverOfRun: {
    progress: "journals.run.exit.handingOverRun",
    done: "journals.run.exit.handedOverRun",
    refused: "journals.run.exit.notHandedOverRun",
  },
} as const;

type FollowedExit = Extract<FollowedJob, { readonly mode: ExitMode }>;

function isExit(job: FollowedJob): job is FollowedExit {
  return job.mode === "CANCEL" || job.mode === "HAND_OVER";
}

function exitText(
  exit: FollowedExit,
  runNo: string,
  text: "progress" | "done" | "refused",
): string {
  if (exit.mode === "HAND_OVER" && exit.batch !== null) {
    return t(EXIT_TEXT.handOver[text], { batch: exit.batch });
  }
  return t(EXIT_TEXT[exit.mode === "CANCEL" ? "cancel" : "handOverOfRun"][text], { run: runNo });
}

/** A job the frame follows before its first read arrives: shown from the accepted command on. */
function queued(jobId: string): JobProgressJob {
  return {
    id: jobId,
    state: "QUEUED",
    progress: { done: 0, total: null },
    started_at: null,
    problem: null,
  };
}

/** A batch outside eRev: a ledger holds it, or its file was handed out (04 §16.7, PRD ERR-74). */
function outside(batch: JournalBatch): boolean {
  return batch.state === "exported" || batch.state === "acknowledged";
}

/** A failed batch a ledger was sent: the only kind that is handed over, and that a cancel asks about. */
export function failedInLedger(batch: JournalBatch): boolean {
  return batch.state === "failed" && batch.adapter !== "CSV";
}

/** What a refused download says: the problem's sentence, else its title and reference (PRD ERR-79). */
function refusalLines(problem: ApiProblem): readonly string[] {
  if (problem.detail !== null) {
    return [problem.detail];
  }
  return problem.requestId === null
    ? [problem.title]
    : [problem.title, t("journals.reference", { reference: problem.requestId })];
}

/** The lines under the title of a job that did not do what was asked: its sentence, its reference. */
function notDoneLines(notDone: NotDone): ReactNode {
  const lines = [
    notDone.sentence,
    notDone.reference === null ? null : t("common.job.reference", { reference: notDone.reference }),
  ].filter((line): line is string => line !== null);
  return lines.length === 0 ? undefined : lines.map((line) => <p key={line}>{line}</p>);
}

export interface RunContext {
  readonly run: JournalRunRow;
  readonly summary: UseQueryResult<JournalRunSummary>;
  readonly ctxSearch: string;
  /**
   * The frame follows a job of the run that has not ended — a cancel, a hand-over, a retry or an
   * export: the commands of its failed batches wait.
   */
  readonly jobUnderWay: boolean;
  /** Follows the job that a command of a tab was accepted as (§3.4 "Hand over", "Retry export"). */
  readonly followJob: (job: FollowedJob) => void;
  /**
   * §3.2 "Download batch files" and §3.4 "Download": the file is fetched and then saved; a refused
   * download saves nothing and is said in the frame's banner (rev 1.77).
   */
  readonly download: (batch: JournalBatch) => void;
}

export interface RunFrameProps {
  readonly tab: RunTab;
  readonly children: (context: RunContext) => ReactNode;
}

export function RunFrame({ tab, children }: RunFrameProps) {
  const { runId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const me = useMe();
  const run = useQuery({ queryKey: journalRunKey(runId), queryFn: () => fetchJournalRun(runId) });
  const region = t("journals.run.region");

  if (me.isError) {
    return <Banner tone="negative" title={me.error.message} />;
  }
  if (run.error !== null) {
    if (run.error instanceof ApiProblem && run.error.status === 404) {
      return (
        <div data-testid="SF-06-page">
          <EmptyState
            title={t("journals.run.notFound.title")}
            description={t("journals.run.notFound.description")}
            headingLevel={2}
            action={{
              label: t("journals.run.notFound.action"),
              onAction: () => void navigate(`/journals${contextSearch(location.search, CONTEXT)}`),
            }}
          />
        </div>
      );
    }
    return (
      <RetryBanner
        title={t("journals.run.loadError")}
        problem={run.error}
        onRetry={() => void run.refetch()}
      />
    );
  }
  if (me.data === undefined || run.data === undefined) {
    return <Skeleton region={region} shape="rows" count={8} />;
  }
  return (
    <RunView key={run.data.id} run={run.data} tab={tab}>
      {children}
    </RunView>
  );
}

/** "exportAgain" is the export of an Exported run: the same command, which posts nothing again. */
type Dialog = "submit" | "export" | "exportAgain" | "cancel" | null;

interface RunViewProps {
  readonly run: JournalRunRow;
  readonly tab: RunTab;
  readonly children: (context: RunContext) => ReactNode;
}

function RunView({ run, tab, children }: RunViewProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const built = useBuiltPaths();
  const sandbox = sandboxTenantName(useShellSession()) !== null;
  const ctxSearch = contextSearch(location.search, CONTEXT);
  const drawer = new URLSearchParams(location.search).get("drawer");
  // SCREENS SCR-PERM-02 (a): a journal run is a record of one legal entity (DG-FE-16).
  const access = useAccess();
  const canRun = access.holds(JOURNAL_RUN_PERMISSION, run.entity);
  const canExport = access.holds(JOURNAL_EXPORT_PERMISSION, run.entity);
  const canDownload = canExport || access.holds(REPORT_EXPORT_PERMISSION, run.entity);
  const [dialog, setDialog] = useState<Dialog>(null);
  // A download the API refused is said in a banner, whole (rev 1.77): PRD ERR-79's sentence names the
  // differences, and a toast holds two lines. The banner goes when another download is asked.
  const [refusedDownload, setRefusedDownload] = useState<RefusedDownload | null>(null);
  const download = useCallback(
    (batch: JournalBatch) => {
      setRefusedDownload(null);
      void downloadBatch(batch).catch((error: unknown) => {
        if (error instanceof ApiProblem) {
          setRefusedDownload({ batch: batchLabel(batch), lines: refusalLines(error) });
        } else {
          toast.show({ tone: "negative", message: t("common.command.noAnswer") });
        }
      });
    },
    [toast],
  );

  const summary = useQuery({
    queryKey: journalRunSummaryKey(run.id),
    queryFn: () => fetchJournalRunSummary(run.id),
  });
  // D-87 L6-5-Q-6: the Cancelled banner reads the `journal_run.cancel` audit event, and "History"
  // the events of the run. SCREENS_B §3.2 (SCREENS §0.6 SCR-PERM-02; ruling R-28): the audit events
  // are a list of the whole workspace, read with `audit.read` for all entities. One read serves both;
  // a read the API refuses (null) leaves the screen of a member without the permission.
  const readsAudit = access.holdsForAll(AUDIT_READ_PERMISSION);
  const history = useQuery({
    queryKey: runHistoryKey(run.id),
    queryFn: () => fetchRunHistory(run.id),
    enabled: readsAudit && (run.state === "cancelled" || drawer === "history"),
  });
  const historyOffered = readsAudit && history.data !== null;
  // `drawer=history` without it opens nothing and leaves the address (SCR-URL-20).
  const historyUnavailable = drawer === "history" && !historyOffered;
  const { search } = location;
  useEffect(() => {
    if (historyUnavailable) {
      void navigate({ search: withParams(search, { drawer: null }) }, { replace: true });
    }
  }, [historyUnavailable, search, navigate]);
  // D-87 L6-5-Q-6: the Approval meta shows the request's `request_no`; a request the caller cannot
  // read shows no meta.
  const approvalRequestId = run.approval_request_id;
  const approval = useQuery({
    queryKey: approvalKey(approvalRequestId ?? ""),
    queryFn: () => fetchApproval(approvalRequestId ?? ""),
    enabled: approvalRequestId !== null,
    retry: false,
  });
  const exportCommand = useCommand({
    method: "POST",
    path: `${JOURNAL_RUNS_PATH}/${run.id}/export`,
    invalidates: [EVERY_JOURNAL_RUN],
  });
  const failed = run.batches.filter((batch) => batch.state === "failed");
  // The run's active jobs: the export of an approved run (SMAP-07) and, for a run with a failed batch,
  // a retry, its cancel or the hand-over of a batch (rev 1.71).
  const activeJobs = useQuery({
    queryKey: exportJobKey(run.id),
    queryFn: () => fetchActiveExportJobs(run.id),
    enabled: run.state === "approved" || failed.length > 0,
    refetchInterval: (query) =>
      (query.state.data?.length ?? 0) > 0 ? JOB_POLL_INTERVAL_MS : false,
  });
  // The job the frame follows: the one a command of this frame was accepted as, else the active one
  // the API lists, so that a tab opened meanwhile, and a holder of `audit.read`, see it end too.
  const [followed, setFollowed] = useState<FollowedJob | null>(null);
  const followedRead = useJob(followed?.jobId ?? null).data;
  const job = followed !== null && followedRead?.id === followed.jobId ? followedRead : undefined;
  const ended = isTerminal(job);
  // An exit before a job without a mode: a retry of one batch can run beside the hand-over of another.
  const listedExit = activeJobs.data?.find((item) => exitModeOf(item) !== null);
  const listedExport = activeJobs.data?.find((item) => exitModeOf(item) === null);
  const listed = listedExit ?? listedExport;
  const listedId = listed?.id ?? null;
  const listedMode = listed === undefined ? null : exitModeOf(listed);
  const exported = isExported(run);
  useEffect(() => {
    if (listedId === null) {
      return;
    }
    if (followed === null || (followed.jobId !== listedId && ended)) {
      setFollowed(
        listedMode === null
          ? { jobId: listedId, mode: "EXPORT", batch: null, sent: null, exported }
          : { jobId: listedId, mode: listedMode, batch: null },
      );
    }
  }, [listedId, listedMode, followed, ended, exported]);
  const followJob = useCallback(
    (next: FollowedJob) => {
      setFollowed(next);
      // Read at once: cached as "no job" it would hide this one from the frame of the next tab.
      void queryClient.invalidateQueries({ queryKey: exportJobKey(run.id) });
    },
    [queryClient, run.id],
  );
  const underWay = followed !== null && !ended ? followed : null;
  // SMAP-07: the state of the job without a mode — of the one followed from its accepted command on,
  // its first read still on its way, else of one the list holds and the frame is about to follow. An
  // exit job is no export: it leaves the chip and the Exporting state alone.
  let exportJobState: string | null = null;
  if (underWay !== null && !isExit(underWay)) {
    exportJobState = job?.state ?? "QUEUED";
  } else if (listedExport !== undefined && listedExport.id !== followed?.jobId) {
    exportJobState = listedExport.state;
  }
  const state = actionState(run, exportJobState);

  // An exit its job did not carry out (§3.2 States "Cancelling", "Handing over").
  let refusedExit: NotDone | null = null;
  if (followed !== null && isExit(followed) && job !== undefined && ended) {
    const ending = exitEnding(job);
    if (!ending.done) {
      refusedExit = {
        title: exitText(followed, run.run_no, "refused"),
        sentence: ending.sentence,
        reference: ending.decided ? null : job.id.slice(0, 8),
      };
    }
  }

  // A finished job: what it changed is read again whatever it did — a batch the ledger holds is
  // acknowledged also when an exit is refused. An exit says what its job decided. A job without a mode
  // ends SUCCEEDED whether or not it sent a batch (04 §16.7), so its ending is said of the run as it is
  // read after it (§3.2 States "Sending again" and "Exporting", rev 1.77).
  const [retryNotSent, setRetryNotSent] = useState<RetryNotSent | null>(null);
  const [exportNotDone, setExportNotDone] = useState<ExportNotDone | null>(null);
  const announced = useRef<string | null>(null);
  useEffect(() => {
    if (followed === null || job === undefined || !isTerminal(job)) {
      return;
    }
    if (announced.current === job.id) {
      return;
    }
    announced.current = job.id;
    for (const queryKey of [
      EVERY_JOURNAL_RUN,
      EVERY_JOURNAL_BATCH,
      exportJobKey(run.id),
      runHistoryKey(run.id),
    ]) {
      void queryClient.invalidateQueries({ queryKey });
    }
    if (isExit(followed)) {
      if (exitEnding(job).done) {
        toast.show({ tone: "positive", message: exitText(followed, run.run_no, "done") });
      }
      return;
    }
    const say = (after: JournalRunRow) => {
      if (followed.mode === "RETRY") {
        const ending = retryEnding(job, followed.batchId, after);
        if (ending.kind === "sent") {
          toast.show({
            tone: "positive",
            message: t("journals.run.retry.sent", { batch: followed.batch }),
          });
        } else if (ending.kind !== "refused") {
          const title = t("journals.run.retry.notSent", { batch: followed.batch });
          setRetryNotSent(
            ending.kind === "waiting"
              ? {
                  jobId: job.id,
                  tone: "warning",
                  title,
                  sentence: t("journals.run.retry.waiting", { at: formatTimestamp(ending.at) }),
                  reference: null,
                }
              : {
                  jobId: job.id,
                  tone: "negative",
                  title,
                  sentence: ending.sentence,
                  reference: job.id.slice(0, 8),
                },
          );
        }
        return;
      }
      // "Exported" is said of a run the job exported, never of a job that merely ended: on a Failed
      // run `export` writes no message for a batch that has one (04 T-SL-07). The export of an
      // Exported run posts nothing again (BR-JE-02). A job that failed or was cancelled says what it
      // did not do — of an Exported run, that the export was not repeated (rev 1.85).
      const ending = exportEnding(
        job,
        { exported: followed.exported, again: followed.sent === "again" },
        after,
      );
      if (ending.kind === "repeated") {
        toast.show({ tone: "positive", message: t("journals.run.export.repeated") });
      } else if (ending.kind === "exported") {
        toast.show({
          tone: "positive",
          message: t("journals.run.export.done", {
            run: after.run_no,
            acknowledged: acknowledgedBatches(after.batches),
            total: after.batches.length,
          }),
        });
      } else if (ending.kind !== "none") {
        setExportNotDone({
          jobId: job.id,
          title: t(
            ending.kind === "notRepeated"
              ? "journals.run.export.notRepeated"
              : "journals.run.export.notDone",
            { run: after.run_no },
          ),
          sentence: ending.sentence,
          reference: job.id.slice(0, 8),
        });
      }
    };
    // A run that cannot be read again shows its own error, and nothing is said of what the job did.
    // The read alone is excused: a fault in what is said of its answer is not caught here.
    void queryClient
      .fetchQuery({ queryKey: journalRunKey(run.id), queryFn: () => fetchJournalRun(run.id) })
      .then(say, () => undefined);
  }, [followed, job, queryClient, run.id, run.run_no, toast]);

  // Search updates keep raw values, so `f.*` operator colons stay unencoded (SCR-URL-20).
  const setDrawer = (next: string | null) => {
    void navigate({ search: withParams(location.search, { drawer: next }) }, { replace: true });
  };

  // The adapter the run's batches were calculated for — the entity's GL connection, or CSV (04 T-SL-07).
  const adapter = run.batches.find((batch) => batch.adapter !== null)?.adapter ?? "CSV";
  // §3.2 action bar, Approved: "Export to <adapter label>", and "Export journals" for a CSV run.
  const exportLabel =
    adapter === "CSV"
      ? t("journals.run.action.export")
      : t("journals.run.action.exportTo", { adapter: adapterText(adapter) });
  const sandboxReason = t("journals.sandboxReason");

  // While the frame follows a job that has not ended — a cancel or a hand-over (rev 1.71), a retry or
  // an export (rev 1.77) — the action bar offers "History" alone (§3.2).
  const idle = underWay === null;
  let primary: ReactNode = null;
  if (idle && state === "calculated" && canRun) {
    primary = (
      <Button variant="primary" onClick={() => setDialog("submit")}>
        {t("journals.run.action.submit")}
      </Button>
    );
  } else if (idle && state === "approved" && canExport) {
    // A Failed run has no primary action (§3.2, rev 1.77; the supervisor's ruling of 2026-10-01):
    // `export` writes no message for a batch that has one, so on a run with a failed batch it sends
    // nothing (04 T-SL-07). The rows' "Retry export" of §3.4 are the way until `export` writes each
    // failed batch's retry message (item JRN-RUN-RETRY-1, lane F-CLO-A); the header's action then
    // returns as one command.
    primary = (
      <Button
        variant="primary"
        disabledReason={sandbox ? sandboxReason : undefined}
        onClick={() => setDialog("export")}
      >
        {exportLabel}
      </Button>
    );
  }

  const secondary: ReactNode[] = [];
  if (
    idle &&
    state === "pending" &&
    run.approval_request_id !== null &&
    built.has(APPROVAL_REQUEST_ROUTE)
  ) {
    secondary.push(
      <Link
        key="request"
        to={`/approvals/requests/${run.approval_request_id}`}
        className="inline-flex h-[var(--control-h)] items-center rounded-md border border-control bg-surface px-3 text-body-sm font-medium text-fg-1 hover:bg-hover"
      >
        {t("journals.run.action.viewRequest")}
      </Link>,
    );
  }
  if (idle && EXPORTABLE.has(state) && canDownload && run.batches.length > 0) {
    secondary.push(<DownloadMenu key="download" batches={run.batches} onDownload={download} />);
  }

  // A batch of the run that is outside eRev, the first in batch and chunk order as the API names it
  // (PRD ERR-74): the run cannot be cancelled, because a new run would send its lines again.
  const held = [...run.batches]
    .sort((left, right) => left.batch_no - right.batch_no || left.chunk_no - right.chunk_no)
    .find(outside);
  const overflow: MenuItem[] = [];
  if (idle && state === "exported" && canExport && !sandbox) {
    overflow.push({
      id: "export-again",
      label: t("journals.run.action.exportAgain"),
      onSelect: () => setDialog("exportAgain"),
    });
  }
  if (historyOffered) {
    overflow.push({
      id: "history",
      label: t("journals.run.action.history"),
      icon: ClockCounterClockwise,
      onSelect: () => setDrawer("history"),
    });
  }
  const cancellable =
    state === "calculated" || state === "pending" || state === "approved" || state === "failed";
  if (idle && cancellable && canRun) {
    overflow.push({
      id: "cancel",
      label: t("journals.run.action.cancel"),
      destructive: true,
      // SCREENS SCR-PERM-03: the record says that the command would be refused, and why.
      disabledReason:
        state === "failed" && held !== undefined
          ? t("journals.run.cancel.partlyOutside", {
              run: run.run_no,
              externalId: held.external_id,
            })
          : undefined,
      onSelect: () => setDialog("cancel"),
    });
  }

  const acknowledged = acknowledgedBatches(run.batches);
  const banners: ReactNode[] = [];
  if (
    run.state === "cancelled" &&
    (!historyOffered || history.data !== undefined || history.isError)
  ) {
    // A job cancels a failed run as System on behalf of the person who asked, and may have refused
    // before: its DENIED events carry the same action, so the banner takes the SUCCESS one (04 §16.7).
    const cancel = history.data?.find(
      (event) => event.action === JOURNAL_RUN_CANCEL_ACTION && event.outcome === "SUCCESS",
    );
    // The copy ends the sentence, so a reason's own closing punctuation is not repeated.
    const reason = cancel?.comment?.trim().replace(/[.!?]+$/, "") ?? "";
    banners.push(
      <div key="cancelled" data-testid="SF-06-banner-cancelled">
        <Banner
          tone="info"
          announce="static"
          title={
            cancel === undefined
              ? t("journals.run.banner.cancelledAt", {
                  run: run.run_no,
                  at: formatTimestamp(run.cancelled_at),
                })
              : t("journals.run.banner.cancelled", {
                  run: run.run_no,
                  name: (cancel.on_behalf_of ?? cancel.actor).display_name,
                  at: formatTimestamp(cancel.occurred_at),
                  reason: reason === "" ? NO_VALUE : reason,
                })
          }
        />
      </div>,
    );
  }
  if (underWay !== null) {
    // One line for the job followed (§3.2 States): an exit by what it does; the retry this frame sent
    // by its batch; a job without a mode it names no batch for by the run, "Exporting journal run".
    let label = t("journals.run.exporting", { run: run.run_no, adapter: adapterText(adapter) });
    if (isExit(underWay)) {
      label = exitText(underWay, run.run_no, "progress");
    } else if (underWay.mode === "RETRY") {
      label = t("journals.run.retry.sending", { batch: underWay.batch });
    }
    banners.push(
      <JobProgress
        key="job"
        label={label}
        // Shown from the accepted command on: the job's first read may still be on its way.
        job={job ?? queued(underWay.jobId)}
        unit={t(isExit(underWay) ? "journals.run.exit.unit" : "journals.run.chunks")}
      />,
    );
  }
  if (refusedExit !== null) {
    banners.push(
      <div key="exit-refused" data-testid="SF-06-banner-exit-refused">
        <Banner tone="negative" title={refusedExit.title}>
          {notDoneLines(refusedExit)}
        </Banner>
      </div>,
    );
  }
  // Said until the frame follows another job: of the retry it sent, not of one before it.
  if (retryNotSent !== null && retryNotSent.jobId === followed?.jobId) {
    banners.push(
      <div key="retry-not-sent" data-testid="SF-06-banner-retry-not-sent">
        <Banner tone={retryNotSent.tone} title={retryNotSent.title}>
          {notDoneLines(retryNotSent)}
        </Banner>
      </div>,
    );
  }
  // Said in every frame that followed the job, until it follows another (§3.2 "Exporting", rev 1.85).
  if (exportNotDone !== null && exportNotDone.jobId === followed?.jobId) {
    banners.push(
      <div key="export-not-done" data-testid="SF-06-banner-export-not-done">
        <Banner tone="negative" title={exportNotDone.title}>
          {notDoneLines(exportNotDone)}
        </Banner>
      </div>,
    );
  }
  if (refusedDownload !== null) {
    banners.push(
      <div key="download-refused" data-testid="SF-06-banner-download-refused">
        <Banner
          tone="negative"
          title={t("journals.run.download.refused", { batch: refusedDownload.batch })}
        >
          {refusedDownload.lines.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </Banner>
      </div>,
    );
  }
  if (run.state === "exported" && acknowledged > 0) {
    banners.push(
      <Banner
        key="partial"
        tone="info"
        announce="static"
        title={t("journals.run.banner.partial", { acknowledged, total: run.batches.length })}
      />,
    );
  }
  if (failed.length > 0) {
    const last = failed.at(-1);
    // The exits this reader is offered on this run, and none that is not (§3.2 Banners, rev 1.71): the
    // cancel of a Failed run with nothing outside eRev, the hand-over of a failed batch a ledger was sent.
    const cancelExit = idle && state === "failed" && canRun && held === undefined;
    const handOverExit = idle && canExport && !sandbox && failed.some(failedInLedger);
    const exits =
      cancelExit && handOverExit
        ? "both"
        : cancelExit
          ? "cancel"
          : handOverExit
            ? "handOver"
            : null;
    // The banner carries no "Retry export" (rev 1.77): its link sent the run's `export`, which sends
    // nothing for a batch that has a message. A failed batch is retried on its row (§3.4), so on the
    // other two tabs the banner leads there (rev 1.85); on Batches the rows are in view.
    banners.push(
      <div key="failed" data-testid="SF-06-banner-export-failed">
        <Banner
          tone="negative"
          announce="static"
          title={t("journals.run.banner.failed", {
            adapter: adapterText(last?.adapter ?? adapter),
            count: failed.length,
            error: last?.last_error ?? NO_VALUE,
          })}
          actions={
            tab === "batches" ? undefined : (
              <Link
                to={`${runRoute(run.id, "batches")}${ctxSearch}`}
                className="text-body-sm text-accent-fg hover:underline"
              >
                {t("journals.run.banner.openBatches")}
              </Link>
            )
          }
        >
          {exits === null ? undefined : <p>{t(`journals.run.banner.exits.${exits}`)}</p>}
        </Banner>
      </div>,
    );
  }
  if (sandbox && canExport && EXPORTABLE.has(state)) {
    banners.push(
      <p key="sandbox" data-testid="SF-06-sandbox-reason" className="text-body-sm text-fg-2">
        {sandboxReason}
      </p>,
    );
  }

  const meta: MetaItem[] = [
    { label: t("journals.run.meta.entity"), value: <Mono>{run.entity.code}</Mono> },
    { label: t("journals.run.meta.book"), value: bookText(run.book) },
    { label: t("journals.run.meta.period"), value: run.period.name },
    { label: t("journals.run.meta.mode"), value: modeText(run.mode) },
    { label: t("journals.run.meta.summarization"), value: grainText(run.grain) },
    {
      label: t("journals.run.meta.cutoff"),
      value: <span data-volatile="">{formatTimestamp(run.cutoff_known_at)}</span>,
    },
    {
      label: t("journals.run.meta.entries"),
      value:
        run.je_range.first_je_no === null || run.je_range.last_je_no === null ? (
          NO_VALUE
        ) : (
          <Mono>
            {`${run.je_range.first_je_no} – ${run.je_range.last_je_no} (${formatNumber(
              run.je_range.count,
              { kind: "count" },
            )})`}
          </Mono>
        ),
    },
  ];
  if (approvalRequestId !== null && approval.data !== undefined) {
    const requestNo = approval.data.request_no;
    meta.push({
      label: t("journals.run.meta.approval"),
      value: built.has(APPROVAL_REQUEST_ROUTE) ? (
        <Link
          to={`/approvals/requests/${approvalRequestId}`}
          className="font-mono text-mono-sm text-accent-fg hover:underline"
        >
          {requestNo}
        </Link>
      ) : (
        <Mono>{requestNo}</Mono>
      ),
    });
  }

  const tabs: readonly RouteTab[] = [
    {
      id: "summary",
      label: t("journals.run.tabs.summary"),
      to: `${runRoute(run.id)}${ctxSearch}`,
      end: true,
    },
    {
      id: "lines",
      label: t("journals.run.tabs.lines"),
      to: `${runRoute(run.id, "lines")}${ctxSearch}`,
    },
    {
      id: "batches",
      label: t("journals.run.tabs.batches"),
      to: `${runRoute(run.id, "batches")}${ctxSearch}`,
    },
  ];

  return (
    <div data-testid="SF-06-page" className="flex flex-col gap-4">
      <RecordHeader
        title={t("journals.run.title", { run: run.run_no })}
        breadcrumb={[{ label: t("journals.title"), to: `/journals${ctxSearch}` }]}
        chips={<RunStateChip run={run} exportJobState={exportJobState} />}
        actions={
          <>
            {secondary}
            {/* RecordHeader shows `primaryAction` only in its condensed bar; the page row carries it here. */}
            {primary}
            {overflow.length === 0 ? null : (
              <Menu
                label={t("journals.run.action.more")}
                icon={DotsThree}
                iconOnly
                variant="ghost"
                align="end"
                items={overflow}
              />
            )}
          </>
        }
        primaryAction={primary ?? undefined}
        meta={meta}
        banner={
          banners.length === 0 ? undefined : <div className="flex flex-col gap-2">{banners}</div>
        }
        kpis={<TotalsStrip run={run} summary={summary.data} />}
      />
      <RouteTabs label={t("journals.run.tabs.label", { run: run.run_no })} tabs={tabs} />
      {children({ run, summary, ctxSearch, jobUnderWay: !idle, followJob, download })}
      {dialog === "submit" ? <SubmitDialog run={run} onClose={() => setDialog(null)} /> : null}
      {dialog === "export" || dialog === "exportAgain" ? (
        <ExportDialog
          run={run}
          adapter={adapter}
          command={exportCommand}
          onAccepted={(jobId) =>
            followJob({
              jobId,
              mode: "EXPORT",
              batch: null,
              sent: dialog === "exportAgain" ? "again" : "export",
              exported,
            })
          }
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === "cancel" ? (
        <CancelDialog
          run={run}
          onAccepted={(jobId) => followJob({ jobId, mode: "CANCEL", batch: null })}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {drawer === "history" && historyOffered ? (
        <HistoryDrawer history={history} onClose={() => setDrawer(null)} />
      ) : null}
    </div>
  );
}

/** §3.2 "Download batch files": one ZIP of CSV and manifest per batch chunk. */
function DownloadMenu({
  batches,
  onDownload,
}: {
  readonly batches: readonly JournalBatch[];
  readonly onDownload: (batch: JournalBatch) => void;
}) {
  const items: MenuItem[] = batches.map((batch) => ({
    id: batch.id,
    label: t("journals.run.download.item", {
      batch: batch.batch_no,
      chunk: batch.chunk_no,
      currency: batch.txn_currency,
    }),
    onSelect: () => onDownload(batch),
  }));
  return <Menu label={t("journals.run.action.download")} icon={DownloadSimple} items={items} />;
}

/** DS-CMP-06 KPI strip "Totals (<functional currency>)" of API-S-JournalRun and the FUNCTIONAL check. */
function TotalsStrip({
  run,
  summary,
}: {
  readonly run: JournalRunRow;
  readonly summary: JournalRunSummary | undefined;
}) {
  const headingId = useId();
  const currency = run.totals.debit_functional.currency;
  const functional = summary?.balance_checks.find(
    (check) => check.basis === "FUNCTIONAL" && check.currency === currency,
  );
  const difference = functional === undefined ? null : functional.difference.amount;
  const balanced = run.totals.balanced;
  const figure = (value: string) => (
    <span className="num text-kpi text-fg-1">{moneyText(value, currency, "cell")}</span>
  );
  const items: readonly {
    readonly id: string;
    readonly label: string;
    readonly value: ReactNode;
  }[] = [
    {
      id: "debits",
      label: t("journals.run.kpi.debits"),
      value: figure(run.totals.debit_functional.amount),
    },
    {
      id: "credits",
      label: t("journals.run.kpi.credits"),
      value: figure(run.totals.credit_functional.amount),
    },
    {
      id: "difference",
      label: t("journals.run.kpi.difference"),
      value: (
        <span data-testid="SF-06-kpi-difference" className="inline-flex items-center gap-2">
          <span
            className="num text-kpi text-fg-1"
            aria-label={t(
              balanced ? "journals.run.kpi.differenceBalanced" : "journals.run.kpi.differenceOpen",
              {
                value: difference === null ? NO_VALUE : moneyText(difference, currency, "inline"),
              },
            )}
          >
            {difference === null ? NO_VALUE : moneyText(difference, currency, "cell")}
          </span>
          <StatusChip status={balanced ? "Balanced" : "Difference"} />
        </span>
      ),
    },
    {
      id: "lines",
      label: t("journals.run.kpi.lines"),
      value: (
        <span className="num text-kpi text-fg-1">
          {formatNumber(run.totals.line_count, { kind: "count" })}
        </span>
      ),
    },
    {
      id: "acknowledged",
      label: t("journals.run.kpi.acknowledged"),
      value: (
        <span className="text-kpi text-fg-1">
          {t("journals.run.kpi.acknowledgedValue", {
            acknowledged: formatNumber(acknowledgedBatches(run.batches), { kind: "count" }),
            total: formatNumber(run.batches.length, { kind: "count" }),
          })}
        </span>
      ),
    },
  ];
  return (
    <section
      aria-labelledby={headingId}
      data-testid="SF-06-kpi-strip"
      className="flex flex-col gap-2 border-t border-hairline pt-3"
    >
      <h2 id={headingId} className="text-caption text-fg-3">
        {t("journals.run.kpi.heading", { currency })}
      </h2>
      {/* DS "content reflows": with a docked drawer the figures wrap into rows instead of clipping. */}
      <dl className="flex flex-wrap gap-y-3">
        {items.map((item) => (
          // Every figure carries its rule, so wrapped rows keep one alignment.
          <div
            key={item.id}
            className="flex min-w-44 flex-1 flex-col gap-1 border-s border-hairline px-4"
          >
            <dt className="text-caption text-fg-3">{item.label}</dt>
            <dd className="flex flex-col items-start gap-1.5">{item.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** §3.2 "Submit for approval" (DS-CMP-11 form modal). */
function SubmitDialog({
  run,
  onClose,
}: {
  readonly run: JournalRunRow;
  readonly onClose: () => void;
}) {
  const formId = useId();
  const toast = useToast();
  const noAnswer = useNoAnswer();
  const [comment, setComment] = useState("");
  const command = useCommand({
    method: "POST",
    path: `${JOURNAL_RUNS_PATH}/${run.id}/submit`,
    invalidates: [EVERY_JOURNAL_RUN],
  });
  const submit = async () => {
    const text = comment.trim();
    const outcome = await command.submit({ comment: text === "" ? null : text });
    if (outcome.kind === "succeeded" || outcome.kind === "accepted") {
      toast.show({ tone: "positive", message: t("journals.run.submit.done", { run: run.run_no }) });
      onClose();
    } else if (outcome.kind === "network-error") {
      noAnswer();
    }
  };
  return (
    <Modal
      open
      variant="form"
      title={t("journals.run.submit.title", { run: run.run_no })}
      description={t("journals.run.submit.description")}
      primaryAction={{ label: t("journals.run.action.submit"), form: formId }}
      submitting={command.pending}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <RefusalBanner problem={command.problem} />
        <TextField
          name="journal-run-comment"
          label={t("journals.run.submit.comment")}
          optional
          multiline
          value={comment}
          onChange={setComment}
        />
      </form>
    </Modal>
  );
}

/**
 * §3.2 "Export" (DS-CMP-11 confirmation with the Target select). A run's batches are calculated for one
 * adapter — the entity's GL connection, or CSV — and `export` answers 422 for any other (04 §16.7 rev
 * 1.145; BUILD_SPEC CLO-15): "Target" lists that one target and the command sends it (rev 1.77). The
 * dialog closes on the accepted command and the frame follows the job.
 */
function ExportDialog({
  run,
  adapter,
  command,
  onAccepted,
  onClose,
}: {
  readonly run: JournalRunRow;
  /** The adapter the run's batches were calculated for. */
  readonly adapter: GlAdapter;
  readonly command: CommandState<unknown>;
  readonly onAccepted: (jobId: string) => void;
  readonly onClose: () => void;
}) {
  const noAnswer = useNoAnswer();
  // One target, so the select has nothing to change: it states where the run goes.
  const targets: readonly Choice<GlAdapter>[] = [
    {
      value: adapter,
      label: adapter === "CSV" ? t("journals.run.export.csvTarget") : adapterText(adapter),
    },
  ];
  const submit = async () => {
    const outcome = await command.submit({ adapter });
    if (outcome.kind === "accepted") {
      onAccepted(outcome.jobId);
    }
    if (outcome.kind === "accepted" || outcome.kind === "succeeded") {
      onClose();
    } else if (outcome.kind === "network-error") {
      noAnswer();
    }
  };
  return (
    <Modal
      open
      variant="confirmation"
      title={t("journals.run.export.title", { run: run.run_no, adapter: adapterText(adapter) })}
      description={t("journals.run.export.consequence")}
      primaryAction={{ label: t("journals.run.export.confirm"), onAction: () => void submit() }}
      submitting={command.pending}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        <RefusalBanner problem={command.problem} />
        <div data-testid="SF-06-export-target">
          <SelectField
            name="journal-export-target"
            label={t("journals.run.export.target")}
            options={targets}
            value={adapter}
            onChange={() => undefined}
          />
        </div>
      </div>
    </Modal>
  );
}

/**
 * §3.2 "Cancel journal run" (SB-R-05: confirmation with a reason of at least 10 characters). A run
 * without a failed batch is cancelled by the command (200). A run with one is cancelled by the job the
 * command is accepted as (202; 04 §16.7 rev 1.159), which asks the ledger first: the dialog closes and
 * the frame follows that job. A refusal of the command itself stays here, as sent.
 */
function CancelDialog({
  run,
  onAccepted,
  onClose,
}: {
  readonly run: JournalRunRow;
  readonly onAccepted: (jobId: string) => void;
  readonly onClose: () => void;
}) {
  const noAnswer = useNoAnswer();
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const command = useCommand({
    method: "POST",
    path: `${JOURNAL_RUNS_PATH}/${run.id}/cancel`,
    invalidates: [EVERY_JOURNAL_RUN],
  });
  const submit = async () => {
    setAttempted(true);
    if (reasonError(reason) !== null) {
      return;
    }
    const outcome = await command.submit({ reason: reason.trim() });
    if (outcome.kind === "accepted") {
      onAccepted(outcome.jobId);
    }
    if (outcome.kind === "succeeded" || outcome.kind === "accepted") {
      onClose();
    } else if (outcome.kind === "network-error") {
      noAnswer();
    }
  };
  return (
    <Modal
      open
      variant="confirmation"
      title={t("journals.run.cancel.title", { run: run.run_no })}
      // A CSV batch fails before a file exists, so only a failed batch of an ERP adapter is asked about.
      description={t(
        run.batches.some(failedInLedger)
          ? "journals.run.cancel.consequenceFailed"
          : "journals.run.cancel.consequence",
      )}
      primaryAction={{
        label: t("journals.run.action.cancel"),
        destructive: true,
        onAction: () => void submit(),
      }}
      submitting={command.pending}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        <RefusalBanner problem={command.problem} />
        <ReasonField
          name="journal-run-cancel-reason"
          label={t("journals.run.cancel.reason")}
          value={reason}
          onChange={setReason}
          showError={attempted}
        />
      </div>
    </Modal>
  );
}

/**
 * The message an event recorded in its `detail`: for the DENIED event of a job, the sentence of the
 * refusal it decided (04 §16.7).
 */
function messageOf(event: AuditEvent): string | null {
  const message = event.detail.message;
  return typeof message === "string" && message !== "" ? message : null;
}

/**
 * The verb phrase of an audit event of the run (§3.2 History, rev 1.85): the catalogue's words for its
 * action — the seven the journals domain records for a run — else the action literal. An event that
 * did not succeed says so before the phrase, as the contract trail does (DS-CMP-12).
 */
function runHistoryVerb(event: Pick<AuditEvent, "action" | "outcome">): string {
  const key = `journals.run.history.action.${event.action}`;
  const action = hasMessage(key) ? t(key) : event.action;
  return event.outcome === "SUCCESS"
    ? action
    : t(`journals.run.history.outcome.${event.outcome}`, { action });
}

/**
 * An audit event of the run as the History drawer tells it (§3.2 rev 1.71). An entry a job wrote for a
 * person reads "System on behalf of <name>". An event that did not succeed says so before its action.
 * The message an event recorded — the refusal of a job — is quoted in the Timeline's slot between the
 * time and the comment, the comment being the reason the person gave.
 */
function historyEntry(event: AuditEvent): TimelineEvent {
  const message = messageOf(event);
  return {
    id: event.id,
    at: event.occurred_at,
    icon: ClockCounterClockwise,
    actor:
      event.on_behalf_of === null
        ? event.actor.display_name
        : t("journals.run.history.onBehalfOf", {
            actor: event.actor.display_name,
            name: event.on_behalf_of.display_name,
          }),
    actorIsPerson: event.actor.kind === "USER",
    verb: runHistoryVerb(event),
    diff: message === null ? undefined : <p className="text-body-sm text-fg-1">{message}</p>,
    comment: event.comment ?? undefined,
  };
}

/** §3.2 History drawer: the DS-CMP-12 audit timeline of the run (`drawer=history`). */
function HistoryDrawer({
  history,
  onClose,
}: {
  readonly history: UseQueryResult<readonly AuditEvent[] | null>;
  readonly onClose: () => void;
}) {
  const events: readonly TimelineEvent[] = (history.data ?? []).map(historyEntry);
  return (
    <Drawer
      open
      variant="docked"
      title={t("journals.run.history.title")}
      initialFocus="title"
      onClose={onClose}
    >
      <Timeline
        events={events}
        status={history.isPending ? "loading" : history.isError ? "error" : "ready"}
        errorState={
          <RetryBanner
            title={t("journals.run.history.loadError")}
            problem={history.error}
            onRetry={() => void history.refetch()}
          />
        }
      />
    </Drawer>
  );
}

// ---------------------------------------------------------------------------------------------------
// The Summary tab.

export function JournalRunSummaryPage() {
  return <RunFrame tab="summary">{(context) => <SummaryTab {...context} />}</RunFrame>;
}

function summaryColumns(run: JournalRunRow, ctxSearch: string): readonly GridColumn<SummaryLine>[] {
  const linesPath = runRoute(run.id, "lines");
  const join = ctxSearch === "" ? "?" : `${ctxSearch}&`;
  return [
    {
      id: "account_code",
      header: t("journals.run.summary.column.account"),
      kind: "text",
      value: (line) => line.account_code,
      render: (line) => (
        <Link
          to={`${linesPath}${join}f.account_code=is:${encodeURIComponent(line.account_code)}`}
          tabIndex={-1}
          className="font-mono text-mono-sm text-accent-fg hover:underline"
        >
          {line.account_code}
        </Link>
      ),
      width: 112,
    },
    {
      id: "account_name",
      header: t("journals.run.summary.column.name"),
      kind: "text",
      value: (line) => line.account_name,
      render: (line) => (
        <span className="truncate" title={line.account_name}>
          {line.account_name}
        </span>
      ),
      width: 320,
    },
    {
      id: "currency",
      header: t("journals.run.summary.column.currency"),
      kind: "text",
      value: (line) => line.currency,
      render: (line) => <Mono>{line.currency}</Mono>,
      width: 104,
    },
    {
      id: "debit",
      header: t("journals.run.summary.column.debit"),
      kind: "money",
      value: (line) => line.debit.amount,
      currency: (line) => line.currency,
      render: (line) => <MoneyCell value={line.debit.amount} currency={line.currency} />,
      width: 176,
    },
    {
      id: "credit",
      header: t("journals.run.summary.column.credit"),
      kind: "money",
      value: (line) => line.credit.amount,
      currency: (line) => line.currency,
      render: (line) => <MoneyCell value={line.credit.amount} currency={line.currency} />,
      width: 176,
    },
  ];
}

function SummaryTab({ run, summary, ctxSearch }: RunContext) {
  const queryClient = useQueryClient();
  // The API answers the summary in one document (OQ-B-07); the grid reads it as one page, in API order.
  const source: GridSource<SummaryLine> = {
    queryKey: queryKey("journal-runs", "tenant", { id: run.id, view: "summary-grid" }),
    fetchPage: async () => {
      const data = await queryClient.fetchQuery({
        queryKey: journalRunSummaryKey(run.id),
        queryFn: () => fetchJournalRunSummary(run.id),
      });
      return {
        items: data.lines,
        nextCursor: null,
        total: { count: data.lines.length, capped: false },
      };
    },
  };
  return (
    <div className="flex flex-col gap-4">
      <div className="flex min-h-80 flex-col">
        <DataGrid<SummaryLine>
          name="summary"
          title={t("journals.run.summary.title")}
          errorTitle={t("journals.run.summary.loadError")}
          countLabel={(count, formatted) => t("journals.run.summary.count", { count, formatted })}
          columns={summaryColumns(run, ctxSearch)}
          source={source}
          rowKey={(line) => `${line.account_code}|${line.currency}`}
          rowLabel={(line) => `${line.account_code} ${line.currency}`}
          testIdPrefix="SF-06"
          emptyState={
            <EmptyState
              title={t("journals.run.summary.empty")}
              description={t("journals.run.summary.emptyDescription")}
              headingLevel={3}
            />
          }
        />
      </div>
      {summary.error !== null ? (
        <RetryBanner
          title={t("journals.run.checks.loadError")}
          problem={summary.error}
          onRetry={() => void summary.refetch()}
        />
      ) : summary.data === undefined ? (
        <Skeleton region={t("journals.run.checks.caption")} shape="rows" count={2} />
      ) : (
        <BalanceChecks checks={summary.data.balance_checks} />
      )}
    </div>
  );
}

const CELL = "px-3 py-2 text-body-sm";

/** §3.2 "Balance checks": one row per entity and transaction currency, and per functional currency. */
export function BalanceChecks({ checks }: { readonly checks: readonly BalanceCheck[] }) {
  return (
    <div
      data-testid="SF-06-grid-balance-checks"
      className="overflow-x-auto rounded-md border border-hairline bg-surface"
    >
      <table className="w-full border-collapse">
        <caption className="px-3 py-2 text-start text-title-sm text-fg-1">
          {t("journals.run.checks.caption")}
        </caption>
        <thead>
          <tr className="border-b border-hairline">
            {(["entity", "basis", "currency"] as const).map((id) => (
              <th key={id} scope="col" className={`${CELL} text-start text-caption text-fg-3`}>
                {t(`journals.run.checks.column.${id}`)}
              </th>
            ))}
            {(["debit", "credit", "difference"] as const).map((id) => (
              <th key={id} scope="col" className={`${CELL} text-end text-caption text-fg-3`}>
                {t(`journals.run.checks.column.${id}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {checks.map((check) => {
            const difference = check.difference.amount;
            const zero = /^-?0+(\.0+)?$/.test(difference);
            return (
              <tr
                key={`${check.entity_code}|${check.basis}|${check.currency}`}
                className="border-b border-hairline last:border-b-0"
              >
                <td className={CELL}>
                  <Mono>{check.entity_code}</Mono>
                </td>
                <td className={CELL}>{t(`journals.run.checks.basis.${check.basis}`)}</td>
                <td className={CELL}>
                  <Mono>{check.currency}</Mono>
                </td>
                <td className={`${CELL} text-end`}>
                  <MoneyCell value={check.debit.amount} currency={check.currency} />
                </td>
                <td className={`${CELL} text-end`}>
                  <MoneyCell value={check.credit.amount} currency={check.currency} />
                </td>
                <td className={`${CELL} text-end`}>
                  <span className="inline-flex items-center justify-end gap-2">
                    <MoneyCell value={difference} currency={check.currency} />
                    <StatusChip status={zero ? "Balanced" : "Difference"} />
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
