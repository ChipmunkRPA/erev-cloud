// SF-05:close-run Close run (SCREENS_B §1.2; §0.3 SB-R-05, SB-R-06; §0.4 E-62; SCREENS RT-99, SCR-PERM-02,
// SCR-PERM-03, SCR-ST-03, SCR-ST-05, SCR-ST-12; DESIGN_SYSTEM DS-CMP-10, DS-CMP-11, DS-CMP-19, DS-CMP-24,
// DS-A11Y-08, DS-FMT-17, DS-FMT-24; 04 API-R-39 §16.8 API-S-CloseRun, T-CLS-01; PRD SM-14, NFR-14, IMP-132;
// supervisor ruling R-79; BUILD_SPEC CLO-24, CLO-19). The Close run tab of the cockpit: the period's
// newest run with its fourteen steps, what stopped it — a failed step with its problem, or contracts
// the recalculation quarantined — and the commands that move it on: run, resume, cancel. The run is read
// as itself and read again every 2 s while it is queued or running, so every reader follows it, not only
// the one who started it. The rows keep the order of the API's array; the run executes "FX remeasurement"
// before "Release schedules", so the row after the running one may already have ended.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";

import { DataGrid, testIdKey } from "../../components/data-grid/DataGrid";
import type { GridColumn, GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { JobProgress } from "../../components/feedback/JobProgress";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { NoValue } from "../../components/money/Num";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import {
  chipFor,
  statusMessageKey,
  StatusChip,
  type StatusWord,
} from "../../components/ui/StatusChip";
import { announce } from "../../lib/a11y/announce";
import { useCommand } from "../../lib/api/commands";
import type { ApiProblem } from "../../lib/api/problems";
import { currencyRegistered } from "../../lib/api/queries/approvals";
import {
  CLOSE_RUN_POLL_MS,
  type CloseRun,
  type CloseRunCancelIn,
  type CloseRunCreateIn,
  closeRunKey,
  type CloseRunScope,
  closeRunsKey,
  type CloseRunStep,
  countOf,
  EARLIER_RUNS,
  EVERY_CLOSE_RUN,
  fetchCloseRun,
  fetchCloseRuns,
  isActiveRun,
  isMovingRun,
  isResumableRun,
  lockedByOf,
  stepNumber,
  tieOutOf,
} from "../../lib/api/queries/close-runs";
import {
  EVERY_EXCEPTION,
  EXCEPTION_QUEUE_ROUTE,
  type ExceptionItem,
  exceptionRoute,
  fetchExceptions,
} from "../../lib/api/queries/exceptions";
import { runRoute } from "../../lib/api/queries/journal-runs";
import {
  CLOSE_RUNS_PATH,
  EVERY_PERIOD,
  PERIOD_CLOSE_PERMISSION,
} from "../../lib/api/queries/periods";
import { periodIsWorkable } from "../../lib/api/queries/reconciliations";
import { periodLabel } from "../../lib/api/queries/tenant";
import { queryKey, type QueryKey } from "../../lib/api/query-keys";
import {
  formatDuration,
  formatMoney,
  formatNumber,
  formatTimestamp,
  instantMs,
} from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { useBuiltPaths } from "../settings/index";
import { type CockpitContext, CockpitFrame, Mono, RetryBanner } from "./cockpit";

/**
 * SCREENS RT-10, RT-29 and RT-47: the targets of a quarantined contract, of "Open journal run" and of
 * the contract's exception item.
 */
const CONTRACT_ROUTE = "/contracts/:contractId";
const JOURNAL_RUN_ROUTE = "/journals/runs/:runId";
const EXCEPTION_ITEM_ROUTE = `${EXCEPTION_QUEUE_ROUTE}/:exceptionId`;
/** The reads a close-run command changes: the runs, the cockpit and the quarantined contracts. */
const COMMAND_KEYS: readonly QueryKey[] = [EVERY_CLOSE_RUN, EVERY_PERIOD, EVERY_EXCEPTION];
const CELL = "px-3 py-2 text-body-sm";

export function CloseRunPage() {
  return <CockpitFrame tab="close-run">{(context) => <CloseRunTab {...context} />}</CockpitFrame>;
}

function stepLabel(stepCode: string | null): string {
  return stepCode === null ? "" : t(`close.run.step.${stepCode}`);
}

/** The E-62 word of a run or a step. */
function statusWord(status: CloseRun["status"]): StatusWord {
  const chip = chipFor("E-62", status);
  if (chip === null) {
    throw new Error(`No status chip for E-62 ${status}`);
  }
  return chip.status;
}

function durationOf(startedAt: string | null, finishedAt: string | null): string | null {
  if (startedAt === null || finishedAt === null) {
    return null;
  }
  return formatDuration(Math.max(0, instantMs(finishedAt) - instantMs(startedAt)));
}

/** A count with its plural message: "3 interface runs complete". */
function counted(key: string, count: number, extra: Readonly<Record<string, string>> = {}): string {
  return t(key, { count, formatted: formatNumber(count, { kind: "count" }), ...extra });
}

/**
 * SCREENS_B §1.2 "Summary when finished", from `steps[].counts` as 04 T-CLS-01 serves them (BUILD_SPEC
 * CLO-19, CLO-20). A step whose counts the run does not state reads nothing; a failed step reads its
 * problem's title, except "Invariant checks", which states how many invariants failed.
 */
function stepSummary(run: CloseRun, step: CloseRunStep): string | null {
  const count = (name: string) => countOf(step.counts, name);
  if (step.status === "FAILED") {
    const failures = step.step_code === "INVARIANTS" ? count("invariant_failures") : null;
    return failures !== null && failures > 0
      ? counted("close.run.summary.invariantFailures", failures)
      : (step.problem?.title ?? null);
  }
  if (step.status === "RUNNING") {
    const progress = run.job?.progress;
    return step.step_code === "RECOMPUTE_DIRTY" &&
      progress !== undefined &&
      progress.total !== null &&
      progress.total > 0
      ? t("close.run.progress", {
          done: formatNumber(progress.done, { kind: "count" }),
          total: formatNumber(progress.total, { kind: "count" }),
        })
      : null;
  }
  if (step.status !== "SUCCEEDED" && step.status !== "BLOCKED") {
    return null;
  }
  switch (step.step_code) {
    case "CUTOFF":
      return formatTimestamp(run.cutoff_known_at);
    case "INTERFACE_COMPLETENESS": {
      const runs = count("interface_runs_complete");
      return runs === null ? null : counted("close.run.summary.interfaceRuns", runs);
    }
    case "EXCEPTION_CHECK": {
      const open = count("blocking_exceptions");
      return open === null ? null : counted("close.run.summary.blockingExceptions", open);
    }
    case "RECOMPUTE_DIRTY": {
      const recomputed = count("groups_recomputed");
      const quarantined = count("groups_quarantined");
      return recomputed === null || quarantined === null
        ? null
        : counted("close.run.groups", recomputed, {
            quarantined: formatNumber(quarantined, { kind: "count" }),
          });
    }
    case "RELEASE_SCHEDULES": {
      const postings = count("postings");
      const lines = count("lines");
      return postings === null || lines === null
        ? null
        : counted("close.run.summary.release", postings, {
            lines: counted("close.run.summary.lines", lines),
          });
    }
    case "FX_REMEASUREMENT":
    case "NETTING_RECLASS": {
      const lines = count("lines");
      return lines === null ? null : counted("close.run.summary.lines", lines);
    }
    case "INVARIANTS": {
      const failures = count("invariant_failures");
      if (failures === null) {
        return null;
      }
      return failures === 0
        ? t("close.run.summary.invariantsPass")
        : counted("close.run.summary.invariantFailures", failures);
    }
    case "JOURNAL_SUMMARIZATION": {
      const batches = count("batches");
      return batches === null ? null : counted("close.run.summary.batches", batches);
    }
    case "EXPORT": {
      const exported = count("batches_exported");
      return exported === null ? null : counted("close.run.summary.exported", exported);
    }
    case "ACKNOWLEDGEMENT_WAIT": {
      const batches = count("batches");
      const acknowledged = count("batches_acknowledged");
      return batches === null || acknowledged === null
        ? null
        : counted("close.run.summary.acknowledged", batches, {
            acknowledged: formatNumber(acknowledged, { kind: "count" }),
          });
    }
    case "GL_TIE_OUT": {
      // The difference of the period's current subledger-to-GL reconciliation, where it has a
      // trial balance; the step attaches none (BS4-D-03).
      const tieOut = tieOutOf(step.counts);
      if (tieOut === null) {
        return null;
      }
      if (!tieOut.attached) {
        return t("close.run.summary.noTrialBalance");
      }
      return tieOut.difference === null || !currencyRegistered(tieOut.currency)
        ? null
        : t("close.run.summary.difference", {
            amount: formatMoney(tieOut.difference, tieOut.currency, { variant: "inline" }),
          });
    }
    case "DATASET_FREEZE": {
      const frozen = count("datasets_frozen");
      return frozen === null ? null : counted("close.run.summary.datasets", frozen);
    }
    case "LOCK": {
      const name = lockedByOf(step.counts);
      return name === null ? null : t("close.run.summary.lockedBy", { name });
    }
    default:
      return null;
  }
}

function CloseRunTab({ cockpit, permissions, ctxSearch }: CockpitContext) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const built = useBuiltPaths();
  const period = cockpit.period;
  const entity = period.entity.code;
  const book = period.book;
  const periodKey = period.period.period_key;
  const label = periodLabel(period.period);
  const scope = useMemo<CloseRunScope>(
    () => ({ entity, book, period: periodKey }),
    [entity, book, periodKey],
  );
  // SCR-PERM-02 and SCR-PERM-03: a command renders for a holder of `period.close`, and a run starts
  // only in a period that is open, in soft close or reopened (the API answers 409 otherwise).
  const canClose = permissions.includes(PERIOD_CLOSE_PERMISSION);
  const mayStart = canClose && periodIsWorkable(period.state);

  const runs = useQuery({ queryKey: closeRunsKey(scope), queryFn: () => fetchCloseRuns(scope) });
  const newest = runs.data?.[0];
  const newestId = newest?.id ?? null;
  // The newest run is followed on its own read: every reader sees it move, not only its initiator.
  const followed = useQuery({
    queryKey: closeRunKey(newestId ?? "none"),
    queryFn: () => fetchCloseRun(newestId ?? ""),
    enabled: newestId !== null,
    refetchInterval: (query) =>
      isMovingRun(query.state.data ?? newest) ? CLOSE_RUN_POLL_MS : false,
  });
  const run = followed.data ?? newest ?? null;
  const earlier = (runs.data ?? []).slice(1, EARLIER_RUNS + 1);

  const [cancelling, setCancelling] = useState(false);
  // A command that did not reach the server: nothing started, and the reader is told so.
  const [unsent, setUnsent] = useState(false);
  const start = useCommand<CloseRun>({
    method: "POST",
    path: CLOSE_RUNS_PATH,
    invalidates: COMMAND_KEYS,
  });
  const resume = useCommand({
    method: "POST",
    path: `${CLOSE_RUNS_PATH}/${newestId ?? "none"}/resume`,
    invalidates: COMMAND_KEYS,
  });
  const refresh = () =>
    Promise.all(COMMAND_KEYS.map((key) => queryClient.invalidateQueries({ queryKey: key })));
  // A resume or a cancel the API refused because this page's read of the runs was out of date (§1.2
  // rev 1.81). The tab holds it: the resume's own refusal leaves with its path when the newest run
  // changes (DG-FE-05), which is the moment the reader needs the sentence, and the cancel's leaves
  // with its dialog.
  const [stale, setStale] = useState<ApiProblem | null>(null);

  const runClose = async () => {
    setUnsent(false);
    setStale(null);
    const outcome = await start.submit({
      entity_code: entity,
      book,
      period_key: periodKey,
    } satisfies CloseRunCreateIn);
    if (outcome.kind === "network-error") {
      setUnsent(true);
    } else if (outcome.kind === "accepted") {
      await refresh();
    } else if (outcome.kind === "succeeded") {
      if (outcome.data !== null) {
        // 200: the entity, book and period already have a run that has not ended (04 §16.8).
        toast.show({
          tone: "neutral",
          message: t("close.run.alreadyRunning", { number: outcome.data.close_run_no }),
        });
      }
    } else if (outcome.problem.status === 409) {
      // A run starts in an open period, in soft close or in a reopened one (04 §16.8). The command is
      // offered by the state this page has read, so the refusal means that read is out of date: its
      // sentence stays, and the period and the runs are read again.
      await refresh();
    }
  };
  const resumeRun = async () => {
    setUnsent(false);
    setStale(null);
    const outcome = await resume.submit();
    if (outcome.kind === "network-error") {
      setUnsent(true);
    } else if (outcome.kind === "accepted" || outcome.kind === "succeeded") {
      await refresh();
    } else if (outcome.problem.status === 409) {
      // The command is offered on the newest run this page has read. A run the API will not resume —
      // a newer one has superseded it, another has not ended, or it is no longer failed or blocked
      // (04 §16.8 rev 1.228) — means that read is out of date: the refusal stays in its banner and
      // the runs are read again, so that the page shows the run the period has.
      setStale(outcome.problem);
      await refresh();
    }
  };
  // A run that ended since this page read it is not cancelled (04 §16.8): the dialog closes, the
  // API's sentence stands above the run, and the runs are read again.
  const cancelRefused = (problem: ApiProblem) => {
    setCancelling(false);
    setStale(problem);
    void refresh();
  };
  const notSent = unsent ? <Banner tone="negative" title={t("close.run.network")} /> : null;

  // The end of a run is announced (DS-A11Y-08) and the reads it changed are made again.
  const status = run?.status ?? null;
  const lastStatus = useRef<{ readonly id: string | null; readonly status: string | null }>({
    id: newestId,
    status,
  });
  useEffect(() => {
    const before = lastStatus.current;
    lastStatus.current = { id: newestId, status };
    if (run === null || before.id !== newestId || before.status === status) {
      return;
    }
    if (before.status !== "PENDING" && before.status !== "RUNNING") {
      return;
    }
    if (status === "PENDING" || status === "RUNNING") {
      return;
    }
    void Promise.all(
      [EVERY_PERIOD, EVERY_EXCEPTION, closeRunsKey(scope)].map((key) =>
        queryClient.invalidateQueries({ queryKey: key }),
      ),
    );
    const number = run.close_run_no;
    if (status === "SUCCEEDED") {
      announce(t("close.run.succeeded", { number }), "polite");
      const journalRunId = run.journal_run_id;
      toast.show({
        tone: "positive",
        message: t("close.run.succeeded", { number }),
        action:
          journalRunId !== null && built.has(JOURNAL_RUN_ROUTE)
            ? {
                label: t("close.run.openJournalRun"),
                onAction: () => void navigate(`${runRoute(journalRunId)}${ctxSearch}`),
              }
            : undefined,
      });
    } else if (status === "FAILED") {
      announce(
        t("close.run.failed", {
          entity,
          period: label,
          step: stepLabel(run.current_step_code),
        }),
        "assertive",
      );
    } else if (status === "BLOCKED") {
      announce(t("close.run.blockedAnnounce", { number }), "assertive");
    } else {
      announce(t("close.run.cancelled", { number }), "polite");
    }
  }, [run, newestId, status, scope, queryClient, toast, built, navigate, ctxSearch, entity, label]);

  if (runs.isError) {
    return (
      <RetryBanner
        title={t("close.run.loadError")}
        problem={runs.error}
        onRetry={() => void runs.refetch()}
      />
    );
  }
  if (runs.isPending) {
    return <Skeleton region={t("close.run.region")} shape="rows" count={8} />;
  }
  if (run === null) {
    return (
      <div className="flex flex-col gap-3">
        {notSent}
        <RefusalBanner problem={start.problem ?? stale} />
        <div className="rounded-md border border-hairline bg-surface px-4 pb-4">
          <EmptyState
            title={t("close.run.emptyTitle", { period: label })}
            description={t("close.run.emptyDescription", { entity })}
            headingLevel={2}
            action={
              mayStart
                ? { label: t("close.action.runClose"), onAction: () => void runClose() }
                : undefined
            }
          />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {notSent}
      <RefusalBanner problem={start.problem ?? resume.problem ?? stale} />
      <RunHeader
        run={run}
        entity={entity}
        periodId={period.id}
        periodLabel={label}
        canClose={canClose}
        resuming={resume.pending}
        journalRunHref={
          run.journal_run_id !== null && built.has(JOURNAL_RUN_ROUTE)
            ? `${runRoute(run.journal_run_id)}${ctxSearch}`
            : null
        }
        onResume={() => void resumeRun()}
        onCancel={() => setCancelling(true)}
      />
      <Steps run={run} />
      <Quarantined run={run} periodId={period.id} ctxSearch={ctxSearch} />
      {earlier.length === 0 ? null : <EarlierRuns runs={earlier} />}
      {cancelling ? (
        <CancelDialog
          run={run}
          onClose={() => setCancelling(false)}
          onCancelled={() => void refresh()}
          onRefused={cancelRefused}
        />
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// The run: its number, state and what stopped it.

interface RunHeaderProps {
  readonly run: CloseRun;
  readonly entity: string;
  /** API-S-Period `id` of the run's entity, book and period: what the quarantine read asks by. */
  readonly periodId: string;
  readonly periodLabel: string;
  readonly canClose: boolean;
  readonly resuming: boolean;
  /** SF-06:run of the journal run the close run calculated, or null. */
  readonly journalRunHref: string | null;
  readonly onResume: () => void;
  readonly onCancel: () => void;
}

function RunHeader({
  run,
  entity,
  periodId,
  periodLabel: label,
  canClose,
  resuming,
  journalRunHref,
  onResume,
  onCancel,
}: RunHeaderProps) {
  const position = stepNumber(run, run.current_step_code);
  const moving = isMovingRun(run);
  const caption =
    position === null || run.status === "SUCCEEDED" || run.status === "CANCELLED"
      ? null
      : t("close.run.stepCaption", {
          step: formatNumber(position, { kind: "count" }),
          total: formatNumber(run.steps.length, { kind: "count" }),
          label: stepLabel(run.current_step_code),
        });
  const stopped = stoppedStep(run);
  const resumeButton =
    canClose && isResumableRun(run) ? (
      <Button variant="link" loading={resuming} onClick={onResume}>
        {t("close.run.resume")}
      </Button>
    ) : undefined;

  return (
    <section
      aria-label={t("close.run.title", { number: run.close_run_no })}
      className="flex flex-col gap-3 rounded-md border border-hairline bg-surface p-4"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h2 className="text-title-sm text-fg-1">
          {t("close.run.title", { number: run.close_run_no })}
        </h2>
        <StatusChip status={statusWord(run.status)} caption={caption} />
        <span className="flex-1" />
        {journalRunHref === null ? null : (
          // The toast of a run that ends names the journal run once; the link stays for every reader.
          <Link
            to={journalRunHref}
            className="inline-flex min-h-6 items-center text-body-sm text-accent-fg hover:underline"
          >
            {t("close.run.openJournalRun")}
          </Link>
        )}
        {canClose && isActiveRun(run) ? (
          <Button onClick={onCancel}>{t("close.run.cancel")}</Button>
        ) : null}
      </div>
      {moving && run.job !== null ? (
        <div data-testid="SF-05-job-close-run">
          <JobProgress
            label={t("close.cockpit.runClose.job", { entity, period: label })}
            job={{
              id: run.job.id,
              state: run.job.state === "QUEUED" ? "QUEUED" : "RUNNING",
              progress: run.job.progress,
              started_at: run.started_at,
              problem: null,
            }}
            unit={t("close.run.unit")}
          />
        </div>
      ) : null}
      {run.status === "BLOCKED" && stopped === null ? (
        <div data-testid="SF-05-banner-close-run-blocked">
          <BlockedBanner run={run} periodId={periodId} actions={resumeButton} />
        </div>
      ) : null}
      {run.status === "FAILED" || (run.status === "BLOCKED" && stopped !== null) ? (
        // SCR-ST-12. A run blocked by a failed invariant shows the same copy for its "Invariant
        // checks" step, with that step's problem (SCREENS_B §1.2 rev 1.47; PRD SM-14).
        <div data-testid="SF-05-banner-close-run-failed">
          <Banner
            tone="negative"
            announce="static"
            title={t("close.run.failed", {
              entity,
              period: label,
              step: stepLabel(stopped?.step_code ?? run.current_step_code),
            })}
            actions={resumeButton}
          >
            {stopped === null ? null : <StepProblem step={stopped} />}
          </Banner>
        </div>
      ) : null}
    </section>
  );
}

/** The problem a step recorded: its title, and the sentence that names what to fix. */
function StepProblem({ step }: { readonly step: CloseRunStep }) {
  if (step.problem === null) {
    return null;
  }
  return (
    <>
      <p>{step.problem.title}</p>
      {step.problem.detail === null ? null : <p>{step.problem.detail}</p>}
    </>
  );
}

/**
 * The quarantined contracts of a period (SCREENS_B §1.2 rev 1.66; 04 §16.14 rev 1.206): the blocking
 * items of the engine that the period's close gates count, asked by the API-S-Period id — `GET
 * /exceptions?blocking=<period id>&source=ENGINE&severity=BLOCKING`. Such an item carries the code of
 * its own refusal and no period, and the item of a group of several contracts no entity and no
 * contract (05 RCP-20), so the read names no `code`, `period` or `entity`; the list holds open items
 * only, so it names no `status`. It is the list of the period, not of the run: an item raised before
 * the run and still open is in it.
 */
function quarantineQuery(periodId: string) {
  return {
    q: null,
    status: [],
    severity: ["BLOCKING"],
    source: ["ENGINE"],
    code: [],
    entity: [],
    owner: null,
    contract: [],
    period: [],
    importUploadId: [],
    blocking: periodId,
    sort: "newest",
  } as const;
}

function quarantineKey(periodId: string): QueryKey {
  return queryKey("exceptions", "tenant", { view: "quarantined", period: periodId });
}

/**
 * The step that stopped a run and states why: of a failed run the step it names, and of a blocked run
 * the step that failed — "Invariant checks" found the period's ledger out of balance (PRD SM-14; 04
 * T-CLS-01 "Ends of a run"). A run blocked by quarantined contracts has no such step.
 */
function stoppedStep(run: CloseRun): CloseRunStep | null {
  if (run.status === "FAILED") {
    return run.steps.find((step) => step.step_code === run.current_step_code) ?? null;
  }
  if (run.status === "BLOCKED") {
    return run.steps.find((step) => step.status === "FAILED" && step.problem !== null) ?? null;
  }
  return null;
}

/** The groups the run's recalculation quarantined (`steps[RECOMPUTE_DIRTY].counts`), or null. */
function quarantinedGroups(run: CloseRun): number | null {
  const recompute = run.steps.find((step) => step.step_code === "RECOMPUTE_DIRTY");
  return recompute === undefined ? null : countOf(recompute.counts, "groups_quarantined");
}

/**
 * SCREENS_B §1.2 `BLOCKED`: the count is the run's own — what its recalculation quarantined — and the
 * open items of the grid below stand in only for a run that states none.
 */
function BlockedBanner({
  run,
  periodId,
  actions,
}: {
  readonly run: CloseRun;
  readonly periodId: string;
  readonly actions: ReactNode;
}) {
  const stated = quarantinedGroups(run);
  const quarantined = useQuery({
    queryKey: quarantineKey(periodId),
    queryFn: () => fetchExceptions(quarantineQuery(periodId)),
    enabled: stated === null,
  });
  const count = stated ?? quarantined.data?.total?.count ?? quarantined.data?.items.length ?? 0;
  return (
    <Banner
      tone="warning"
      announce="static"
      title={t("close.run.blocked", {
        number: run.close_run_no,
        contracts: formatNumber(count, { kind: "count" }),
      })}
      actions={actions}
    />
  );
}

// ---------------------------------------------------------------------------------------------------
// The fourteen steps.

function Steps({ run }: { readonly run: CloseRun }) {
  const total = formatNumber(run.steps.length, { kind: "count" });
  return (
    <ol
      aria-label={t("close.run.steps")}
      data-testid="SF-05-close-run-steps"
      className="flex flex-col divide-y divide-hairline rounded-md border border-hairline bg-surface"
    >
      {run.steps.map((step, index) => {
        const word = statusWord(step.status);
        const name = stepLabel(step.step_code);
        const summary = stepSummary(run, step);
        const duration = durationOf(step.started_at, step.finished_at);
        const timing = step.status === "RUNNING" ? t("close.run.running") : duration;
        return (
          <li
            key={step.step_code}
            aria-label={t("close.run.stepName", {
              step: formatNumber(index + 1, { kind: "count" }),
              total,
              label: name,
              status: t(statusMessageKey(word)),
            })}
            data-testid={`SF-05-row-${testIdKey(step.step_code)}`}
            className="grid min-h-[var(--row-h)] grid-cols-[7.5rem_2rem_minmax(0,16rem)_minmax(0,1fr)] items-center gap-3 px-4 py-1.5 text-body-sm min-[1440px]:grid-cols-[7.5rem_2rem_minmax(0,16rem)_minmax(0,1fr)_6rem]"
          >
            <span>
              <StatusChip status={word} />
            </span>
            <span className="num text-fg-3">{formatNumber(index + 1, { kind: "count" })}</span>
            <span className="truncate text-fg-1">{name}</span>
            <span className="flex min-w-0 items-baseline gap-1.5">
              <span
                className={`truncate ${step.status === "FAILED" ? "text-negative-fg" : "text-fg-2"}`}
                title={summary ?? undefined}
              >
                {summary}
              </span>
              {/* SCREENS_B §1.2 "1280 px": below 1440 px the duration follows the summary. */}
              {timing === null ? null : (
                <span data-volatile="" className="num shrink-0 text-fg-3 min-[1440px]:hidden">
                  {summary === null ? timing : `· ${timing}`}
                </span>
              )}
            </span>
            <span data-volatile="" className="num hidden text-end text-fg-3 min-[1440px]:block">
              {timing}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

// ---------------------------------------------------------------------------------------------------
// Quarantined contracts.

function Quarantined({
  run,
  periodId,
  ctxSearch,
}: {
  readonly run: CloseRun;
  /** API-S-Period `id` of the run's entity, book and period. */
  readonly periodId: string;
  readonly ctxSearch: string;
}) {
  const queryClient = useQueryClient();
  const built = useBuiltPaths();
  // SCREENS_B §1.2: only while the run is blocked by quarantined contracts or it quarantined some.
  const shown =
    (run.status === "BLOCKED" && stoppedStep(run) === null) || (quarantinedGroups(run) ?? 0) > 0;
  const source: GridSource<ExceptionItem> = useMemo(
    () => ({
      queryKey: queryKey("exceptions", "tenant", { view: "quarantined-grid", period: periodId }),
      fetchPage: () =>
        queryClient.fetchQuery({
          queryKey: quarantineKey(periodId),
          queryFn: () => fetchExceptions(quarantineQuery(periodId)),
        }),
    }),
    [queryClient, periodId],
  );
  const contractsBuilt = built.has(CONTRACT_ROUTE);
  const itemsBuilt = built.has(EXCEPTION_ITEM_ROUTE);
  const columns = useMemo(
    () => quarantineColumns({ contractsBuilt, itemsBuilt, ctxSearch }),
    [contractsBuilt, itemsBuilt, ctxSearch],
  );
  if (!shown) {
    return null;
  }
  return (
    <div className="flex min-h-48 flex-col">
      <DataGrid<ExceptionItem>
        name="quarantined"
        title={t("close.run.quarantined.title")}
        errorTitle={t("close.run.quarantined.loadError")}
        countLabel={(count, formatted) => t("close.run.quarantined.count", { count, formatted })}
        columns={columns}
        source={source}
        rowKey={(item) => item.id}
        rowLabel={(item) => item.contract_external_id ?? item.exception_no}
        testIdPrefix="SF-05"
        emptyState={
          <EmptyState
            title={t("close.run.quarantined.emptyTitle")}
            description={t("close.run.quarantined.emptyDescription")}
            headingLevel={3}
          />
        }
      />
    </div>
  );
}

/**
 * SCREENS_B §1.2 "Grid columns: quarantined contracts". A link is rendered where its route is built
 * (XR-14); the message is the last text to be cut and keeps its whole text in its title. Rev 1.66:
 * the item of a group of several contracts names no contract, so "Contract" shows the group's code —
 * text, a group having no page — and the item's message names the member contracts.
 */
export function quarantineColumns({
  contractsBuilt,
  itemsBuilt,
  ctxSearch,
}: {
  readonly contractsBuilt: boolean;
  readonly itemsBuilt: boolean;
  readonly ctxSearch: string;
}): readonly GridColumn<ExceptionItem>[] {
  return [
    {
      id: "contract",
      header: t("close.run.quarantined.contract"),
      kind: "identifier",
      value: (item) => item.contract_external_id ?? item.combination_group_code,
      render: (item) => {
        if (item.contract_external_id === null) {
          return item.combination_group_code === null ? (
            <NoValue />
          ) : (
            <Mono>{item.combination_group_code}</Mono>
          );
        }
        return contractsBuilt && item.contract_id !== null ? (
          <Link
            to={`/contracts/${item.contract_id}${ctxSearch}`}
            tabIndex={-1}
            className="truncate font-mono text-mono-sm text-accent-fg hover:underline"
          >
            {item.contract_external_id}
          </Link>
        ) : (
          <Mono>{item.contract_external_id}</Mono>
        );
      },
      width: 200,
    },
    {
      id: "code",
      header: t("close.run.quarantined.code"),
      kind: "text",
      value: (item) => item.code,
      render: (item) => <Mono>{item.code}</Mono>,
      width: 264,
    },
    {
      id: "message",
      header: t("close.run.quarantined.message"),
      kind: "text",
      value: (item) => item.message,
      render: (item) => (
        <span className="truncate" title={item.message}>
          {item.message}
        </span>
      ),
      width: 456,
    },
    {
      id: "exception",
      header: t("close.run.quarantined.exception"),
      kind: "text",
      value: (item) => item.exception_no,
      render: (item) =>
        itemsBuilt ? (
          <Link
            to={exceptionRoute(item.id, ctxSearch)}
            tabIndex={-1}
            className="font-mono text-mono-sm text-accent-fg hover:underline"
          >
            {item.exception_no}
          </Link>
        ) : (
          <Mono>{item.exception_no}</Mono>
        ),
      width: 160,
    },
  ];
}

// ---------------------------------------------------------------------------------------------------
// Earlier close runs.

function EarlierRuns({ runs }: { readonly runs: readonly CloseRun[] }) {
  const headers = ["number", "status", "started", "by", "duration"] as const;
  return (
    <section
      data-testid="SF-05-grid-close-runs"
      className="rounded-md border border-hairline bg-surface"
    >
      <table className="w-full border-collapse" aria-label={t("close.run.earlier.title")}>
        <caption className="px-4 py-3 text-start text-title-sm text-fg-1">
          {t("close.run.earlier.title")}
        </caption>
        <thead>
          <tr className="border-y border-default bg-subtle">
            {headers.map((id) => (
              <th
                key={id}
                scope="col"
                className={`${CELL} text-start font-medium text-fg-2 first:ps-4`}
              >
                {t(`close.run.earlier.column.${id}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {runs.map((item) => (
            <tr key={item.id} className="border-b border-hairline last:border-b-0">
              <th scope="row" className={`${CELL} ps-4 text-start font-normal`}>
                <Mono>{item.close_run_no}</Mono>
              </th>
              <td className={CELL}>
                <StatusChip status={statusWord(item.status)} />
              </td>
              <td className={`${CELL} num`}>
                <span data-volatile="">{formatTimestamp(item.created_at)}</span>
              </td>
              <td className={CELL}>{item.created_by.display_name}</td>
              <td className={`${CELL} num`}>
                <span data-volatile="">
                  {durationOf(item.started_at, item.finished_at) ?? <NoValue />}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

// ---------------------------------------------------------------------------------------------------
// Cancel close run (SB-R-05).

function CancelDialog({
  run,
  onClose,
  onCancelled,
  onRefused,
}: {
  readonly run: CloseRun;
  readonly onClose: () => void;
  readonly onCancelled: () => void;
  /** The run is no longer one that is cancelled (409): the page's read of it is out of date. */
  readonly onRefused: (problem: ApiProblem) => void;
}) {
  const toast = useToast();
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [unsent, setUnsent] = useState(false);
  const command = useCommand<CloseRun>({
    method: "POST",
    path: `${CLOSE_RUNS_PATH}/${run.id}/cancel`,
    invalidates: COMMAND_KEYS,
  });
  const submit = async () => {
    setAttempted(true);
    if (reasonError(reason) !== null) {
      return;
    }
    setUnsent(false);
    const outcome = await command.submit({ reason: reason.trim() } satisfies CloseRunCancelIn);
    if (outcome.kind === "network-error") {
      setUnsent(true);
    } else if (outcome.kind === "succeeded" || outcome.kind === "accepted") {
      // 04 §16.8: a run whose job is running ends after its current step; a queued or a blocked
      // run is cancelled at once, and the answer says which.
      const ended = outcome.kind === "succeeded" && outcome.data?.status === "CANCELLED";
      toast.show({
        tone: "positive",
        message: t(ended ? "close.run.cancelled" : "close.run.cancelRequested", {
          number: run.close_run_no,
        }),
      });
      onCancelled();
      onClose();
    } else if (outcome.problem.status === 409) {
      onRefused(outcome.problem);
    }
  };
  return (
    <Modal
      open
      variant="confirmation"
      title={t("close.run.cancelTitle", { number: run.close_run_no })}
      description={t("close.run.cancelDescription")}
      primaryAction={{
        label: t("close.run.cancel"),
        destructive: true,
        onAction: () => void submit(),
      }}
      submitting={command.pending}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        {unsent ? <Banner tone="negative" title={t("close.run.network")} /> : null}
        <RefusalBanner problem={command.problem} />
        <ReasonField
          name="close-run-cancel-reason"
          label={t("close.run.cancelReason")}
          value={reason}
          onChange={setReason}
          showError={attempted}
        />
      </div>
    </Modal>
  );
}
