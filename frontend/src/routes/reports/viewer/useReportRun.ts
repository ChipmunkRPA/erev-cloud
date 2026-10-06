// RV-01 One run per view (SCREENS_B §0.5; SCREENS SCR-URL-16; BR-RPT-01; 04 API-R-41). The lifecycle every
// report surface shares (SF-08:report, SF-04, SF-06:entries): opening the view with a parameter set creates
// one JSON run and writes `run=<id>` with `history.replace`; a URL with `run` renders that stored run and
// creates none; a context change drops `run`, so the next render starts from the new source; the run is
// polled while it computes, its rows load once it succeeded, and a run longer than 2 seconds announces
// "Report <name> ran." (§5.2). A refused creation (a problem answer to `POST /report-runs`, so no run exists)
// is bound to the parameter set and source it was attempted for: its problem shows only while the view stays
// on that pair and displays no `run`; a stored run opened by a later `run` navigation never inherits it
// (RV-01 rev 1.6; D-90e L9-PLT-Q-6). Every creation answer is bound to the attempt that produced it: an
// answer arriving after a later attempt, a context change or "Run report" is discarded, so a late 202 never
// moves `run` to a superseded creation and a late refusal never shows (late-response ownership guard).
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router";

import { useToast } from "../../../components/feedback/Toast";
import { useCommand } from "../../../lib/api/commands";
import { isTerminal, JOB_POLL_INTERVAL_MS } from "../../../lib/api/jobs";
import type { ApiProblem } from "../../../lib/api/problems";
import {
  EVERY_REPORT_RUN,
  fetchReportRows,
  fetchReportRun,
  isRunning,
  REPORT_RUN_ID_HEADER,
  REPORT_RUNS_PATH,
  type ReportDefinition,
  type ReportRow,
  reportRowsKey,
  type ReportRunColumn,
  reportRunKey,
  type ReportRunRows,
} from "../../../lib/api/queries/reports";
import { formatNumber } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";

/** §5.2: the toast "Report <name> ran." only for runs longer than 2 seconds. */
const SLOW_RUN_MS = 2_000;

function rowsOf(data: ReportRunRows): readonly ReportRow[] {
  return data.rows;
}

function columnsOf(data: ReportRunRows): readonly ReportRunColumn[] {
  return data.columns;
}

/** The problem of a refused creation with the parameter set and source it was attempted for. */
interface Refusal {
  readonly signature: string;
  readonly context: string;
  readonly problem: ApiProblem;
}

export interface ReportRunOptions {
  readonly definition: ReportDefinition;
  /** API-S-ReportRunCreate `parameters` of the view. */
  readonly parameters: Readonly<Record<string, unknown>>;
  /** The source of the view (entity, book, period, snapshot, known_at, …); a change drops `run`. */
  readonly contextSignature: string;
  /** False while the calendar or the As locked default is still settling. */
  readonly ready: boolean;
  /** SCR-URL-16 `run`. */
  readonly runId: string | null;
  /** Writes search parameters with `history.replace` (SCR-URL-20 raw values). */
  readonly replace: (changes: Readonly<Record<string, string | null>>) => void;
  /** Creates no run while false (for example SF-04 `layout=lines`). */
  readonly enabled?: boolean;
  /**
   * False where the view is one of several on a page (SF-08:dashboard, §5.5): the toast of a run longer
   * than 2 seconds is the report view's own (§5.2), and four panels would say it four times.
   */
  readonly announce?: boolean;
}

export function useReportRun({
  definition,
  parameters,
  contextSignature,
  ready,
  runId,
  replace,
  enabled = true,
  announce = true,
}: ReportRunOptions) {
  const toast = useToast();
  // The address as last committed: a navigation gives its location a key of its own.
  const { key: written } = useLocation();
  const signature = JSON.stringify(parameters);
  const create = useCommand({
    method: "POST",
    path: REPORT_RUNS_PATH,
    invalidates: [EVERY_REPORT_RUN],
  });
  const { submit, reset } = create;
  const startedFor = useRef<string | null>(null);
  // The key of the address "Run report" was pressed on, until the write that follows it is committed.
  const awaited = useRef<string | null>(null);
  const startedAt = useRef<number | null>(null);
  // The (run, job) pair this view created, from the 202 (`X-Erev-Report-Run-Id`, `Location`). SCR-ST-12
  // names the job of a command started on the screen, so the job is exposed only while the displayed run
  // is the created one; a stored run opened by a later `run` navigation in the same mounted view was not
  // started here and shows no reference (L9-PLT plt-job-reference).
  const [created, setCreated] = useState<{
    readonly runId: string;
    readonly jobId: string;
  } | null>(null);
  // The refused creation of this mounted view, if any (D-90e L9-PLT-Q-6): read against the current
  // parameter set and source below, so a stored run or another parameter set never shows it.
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const previousContext = useRef(contextSignature);
  // The identity of the latest creation attempt: a new start, "Run report" and a context change supersede
  // the attempts before them, whose answers are then discarded.
  const attempts = useRef(0);
  // The view is on screen. A view is keyed by its report, so the view of a report that gave way to
  // another under the same route is gone while its creation may still be unanswered: that answer is
  // discarded too, or it would write its run onto the address of the report now shown
  // (RPT-VIEWER-LATE-RUN-1).
  const shown = useRef(false);
  useEffect(() => {
    shown.current = true;
    return () => {
      shown.current = false;
    };
  }, []);

  const start = useCallback(
    async (parameterSignature: string) => {
      // The pair the attempt belongs to, captured before the answer: the view may move on meanwhile.
      const context = previousContext.current;
      const attempt = (attempts.current += 1);
      startedAt.current = Date.now();
      const outcome = await submit({
        report_code: definition.code,
        parameters: JSON.parse(parameterSignature) as Readonly<Record<string, unknown>>,
        output_format: "JSON",
      });
      if (attempts.current !== attempt || !shown.current) {
        return;
      }
      if (outcome.kind === "accepted") {
        const id = outcome.response.headers.get(REPORT_RUN_ID_HEADER);
        setCreated(id === null ? null : { runId: id, jobId: outcome.jobId });
        if (id !== null) {
          replace({ run: encodeURIComponent(id) });
        }
      } else if (outcome.kind === "failed") {
        setRefusal({ signature: parameterSignature, context, problem: outcome.problem });
      }
    },
    [definition.code, replace, submit],
  );

  // A context change starts from the new source: the stored run no longer describes the view.
  useEffect(() => {
    if (previousContext.current === contextSignature) {
      return;
    }
    previousContext.current = contextSignature;
    startedFor.current = null;
    attempts.current += 1;
    setCreated(null);
    setRefusal(null);
    if (runId !== null) {
      replace({ run: null });
    }
  }, [contextSignature, replace, runId]);

  // RV-01: opening the view with a parameter set creates one run. "Run report" asks (rev 1.92;
  // REPORT-RERUN-AFTER-REFUSAL-1): `restart` leaves the set unstarted and the screen writes the address,
  // and that write is what this effect answers to — every navigation commits a location of its own key,
  // also one that leaves the address as it was, which is the case of "Run report" pressed again on a
  // refused set. Until that write is committed nothing is started: a navigation is committed after
  // the state updates of the handler that asked for it, so the set rendered in between is one the
  // address is about to leave — the refused set once more, or the screen's new entities beside the
  // address's old dates (SF-06:entries) — and a creation for it is one nobody asked for.
  useEffect(() => {
    if (awaited.current === written) {
      return;
    }
    awaited.current = null;
    if (!enabled || !ready || runId !== null || startedFor.current === signature) {
      return;
    }
    startedFor.current = signature;
    void start(signature);
  }, [enabled, ready, runId, signature, start, written]);

  const run = useQuery({
    queryKey: reportRunKey(runId ?? ""),
    queryFn: () => fetchReportRun(runId ?? ""),
    enabled: enabled && runId !== null,
    refetchInterval: (query) => (isRunning(query.state.data) ? JOB_POLL_INTERVAL_MS : false),
  });
  const succeeded = run.data?.status === "SUCCEEDED";
  const rowsEnabled = enabled && runId !== null && succeeded;
  // Two observers of one query: the rows, and the run's `columns` for ColumnContext (D-88 L7-1-Q-5).
  const rows = useQuery({
    queryKey: reportRowsKey(runId ?? ""),
    queryFn: () => fetchReportRows(runId ?? ""),
    enabled: rowsEnabled,
    select: rowsOf,
  });
  const columns = useQuery({
    queryKey: reportRowsKey(runId ?? ""),
    queryFn: () => fetchReportRows(runId ?? ""),
    enabled: rowsEnabled,
    select: columnsOf,
  });

  const announced = useRef<string | null>(null);
  useEffect(() => {
    const data = run.data;
    if (
      data?.status !== "SUCCEEDED" ||
      announced.current === data.id ||
      startedAt.current === null
    ) {
      return;
    }
    announced.current = data.id;
    const elapsed = Date.now() - startedAt.current;
    startedAt.current = null;
    if (announce && elapsed > SLOW_RUN_MS) {
      const count = data.row_count ?? 0;
      toast.show({
        tone: "positive",
        message: t("reports.report.ran", {
          name: definition.name,
          count,
          rows: formatNumber(count, { kind: "count" }),
        }),
      });
    }
  }, [announce, definition.name, run.data, toast]);

  const job = create.job;
  const pendingJob = runId === null && job !== undefined && !isTerminal(job) ? job : null;
  const computing = create.pending || pendingJob !== null || isRunning(run.data);
  /** SCR-ST-12 "Reference <job id prefix>": the created job, only while its run is the displayed run. */
  const createdJobId = created !== null && created.runId === runId ? created.jobId : null;
  /**
   * The problem of a refused creation, only while the view still shows the parameter set and source it was
   * attempted for and displays no `run` (RV-01 rev 1.6; D-90e L9-PLT-Q-6).
   */
  const problem =
    refusal !== null &&
    runId === null &&
    refusal.signature === signature &&
    refusal.context === contextSignature
      ? refusal.problem
      : null;

  /**
   * "Run report": a run is created from the parameters the screen writes next — the caller writes the
   * address after this call, also when nothing in it changes, and the creation answers to that write.
   */
  const restart = useCallback(() => {
    startedFor.current = null;
    awaited.current = written;
    attempts.current += 1;
    setCreated(null);
    setRefusal(null);
    reset();
  }, [reset, written]);

  return {
    problem,
    run,
    rows,
    columns: columns.data,
    pendingJob,
    computing,
    createdJobId,
    restart,
  };
}
