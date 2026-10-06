// SF-08:run Report run record (SCREENS_B §5.3; §0.5 RV-03, RV-05, RV-14; SCREENS §0.4 RT-33; §0.6
// SCR-PERM-01; §0.7 SCR-ST-07, SCR-ST-12; DESIGN_SYSTEM DS-CMP-06, DS-CMP-19, DS-CMP-24, DS-CMP-29,
// DS-FMT-16, DS-FMT-17, DS-FMT-23; 04 API-R-41, API-S-ReportRun; REQ-RPT-002; CTL-029; BUILD_SPEC
// RPS-18). One run: the record header with the E-67 chip, "Open report view", "Download <format>" and
// the rerun; the meta row (report and version, entity scope, book, as-of date, source, engine release,
// who ran it, start and finish with seconds); then the static tables "Parameters" (every key the run
// stored, defaults included), "Control totals", the tie-out results, "Output" (format, SHA-256,
// manifest), "Ledger heads" and "Source" (the lock, the cutoff with its basis and what a rerun reads).
// A failed run shows "The run failed: <problem title>. Nothing was exported."; a run that is still
// computing shows its job. The rerun follows RV-03: "Rerun from the same source" where the run's source
// is bound, retained or frozen, "Rerun (new evaluation)" where the builder binds none, and unavailable
// for a run stored before source binding. Its job is followed here; on success the page opens the new
// run's record with "Output identical: <Yes|No>" and "Control totals identical: <Yes|No>". A refused
// rerun says its title, its detail and every sentence of its findings (DS-CMP-29; rev 1.101).
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useEffect, useRef } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { JobProgress, type JobProgressJob } from "../../components/feedback/JobProgress";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { CopySimple, DownloadSimple } from "../../components/icons/registry";
import { NoValue } from "../../components/money/Num";
import { type Crumb, type MetaItem, RecordHeader } from "../../components/record/RecordHeader";
import { Button } from "../../components/ui/Button";
import { cn } from "../../components/ui/cn";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { announce } from "../../lib/a11y/announce";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { isTerminal, JOB_POLL_INTERVAL_MS, useJob } from "../../lib/api/jobs";
import { ApiProblem } from "../../lib/api/problems";
import { currencyRegistered, ensureCurrencyCodes } from "../../lib/api/queries/approvals";
import { type Me, useMe } from "../../lib/api/queries/me";
import {
  EVERY_REPORT_RUN,
  fetchReportRun,
  isRunning,
  mayReadReportRuns,
  mayReadRunJob,
  moneyCurrencies,
  REPORT_EXPORT_PERMISSION,
  REPORT_ROUTE,
  REPORT_RUN_PERMISSION,
  REPORT_RUNS_PATH,
  REPORT_RUNS_ROUTE,
  reportOutputHref,
  REPORTS_ROUTE,
  type ReportRun,
  reportRunKey,
  reportRunRoute,
} from "../../lib/api/queries/reports";
import { formatDate, formatMoney, formatNumber, formatTimestamp, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { useBuiltPaths } from "../settings/index";
import { ReportRunsAccessLimited } from "./access";
import { reportViewHref } from "./run-links";
import { JobReference } from "./viewer/JobReference";
import { valueText } from "./viewer/RunDetailsDrawer";
import { bookLabel, hashPrefix, runAsOf } from "./viewer/RunStamp";
import { isMoney, PACK_CODES } from "./viewer/specs";
import { TieOutStrip } from "./viewer/TieOutStrip";

/** The permission that downloads the output of a pack run (SCREENS_B §5.3). */
const EVIDENCE_EXPORT_PERMISSION = "evidence.export";

/** RV-03: what a rerun of the run reads. */
export type RerunOffer = "same-source" | "new-evaluation" | "unbound";

/**
 * RV-03 (rev 1.19): a run stored before source binding of a builder that binds its source cannot be
 * rerun; an `open` builder's run, and a run that failed before its source was captured, rerun as a new
 * evaluation; every other run reruns from the same source.
 */
export function rerunOffer(run: Pick<ReportRun, "sources">): RerunOffer {
  const { kind, strategy } = run.sources;
  if (kind === "legacy_unbound") {
    return strategy === "open" ? "new-evaluation" : "unbound";
  }
  return kind === "open" || kind === "failed_without_capture" ? "new-evaluation" : "same-source";
}

/** RV-03 "Sources": the sentence of the run's source binding, by `sources.kind`. */
export function sourcesText(run: Pick<ReportRun, "sources">): string {
  const sources = run.sources;
  const count = (value: number) => formatNumber(value, { kind: "count" });
  switch (sources.kind) {
    case "bound":
      return t("reports.run.sources.bound", {
        versions: count(sources.versions),
        labels: count(sources.labels),
        members: count(sources.members),
        rows: count(sources.rows),
        cutoff: sources.cutoff === null ? NO_VALUE : formatTimestamp(sources.cutoff),
      });
    case "retained":
    case "open":
    case "as_locked":
    case "pending":
    case "failed_without_capture":
      return t(`reports.run.sources.${sources.kind}`);
    case "legacy_unbound":
      return t(
        sources.strategy === "open"
          ? "reports.run.sources.legacy_unbound_open"
          : "reports.run.sources.legacy_unbound",
      );
    default:
      return sources.kind;
  }
}

/** RV-03 `known_at` and its basis: the parameter `known_at_basis` the run stored, if any. */
export function knownAtBasis(run: Pick<ReportRun, "parameters">): string {
  const basis = run.parameters.known_at_basis;
  if (basis === "historical") {
    return t("reports.run.knownAt.historical");
  }
  return t(basis === "record" ? "reports.run.knownAt.record" : "reports.run.knownAt.legacy");
}

/** The result of the rerun that created the run on screen, carried by the navigation that opened it. */
export interface RerunResult {
  /** The run that was repeated. */
  readonly ofId: string;
  readonly ofNo: string;
  readonly outputIdentical: boolean;
  readonly totalsIdentical: boolean;
}

function rerunResultOf(state: unknown): RerunResult | null {
  if (typeof state !== "object" || state === null) {
    return null;
  }
  const rerun = (state as Readonly<Record<string, unknown>>).rerun;
  if (typeof rerun !== "object" || rerun === null) {
    return null;
  }
  const { ofId, ofNo, outputIdentical, totalsIdentical } = rerun as Readonly<
    Record<string, unknown>
  >;
  return typeof ofId === "string" &&
    typeof ofNo === "string" &&
    typeof outputIdentical === "boolean" &&
    typeof totalsIdentical === "boolean"
    ? { ofId, ofNo, outputIdentical, totalsIdentical }
    : null;
}

/** A total the run recorded per currency, `{<ISO 4217 code>: <decimal string>}`, or null. */
function currencyTotals(value: unknown): readonly (readonly [string, string])[] | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  const entries = Object.entries(value as Readonly<Record<string, unknown>>);
  return entries.length > 0 &&
    entries.every(([code, amount]) => /^[A-Z]{3}$/.test(code) && typeof amount === "string")
    ? (entries as readonly (readonly [string, string])[])
    : null;
}

/** The currencies of the control totals a run recorded per currency. */
function totalCurrencies(totals: ReportRun["control_totals"]): readonly string[] {
  return Object.values(totals ?? {}).flatMap((value) =>
    (currencyTotals(value) ?? []).map(([code]) => code),
  );
}

/** A currency the caller cannot read shows no value (DS-FMT-03). */
function amount(value: string, currency: string): string {
  return currencyRegistered(currency)
    ? formatMoney(value, currency, { variant: "inline" })
    : NO_VALUE;
}

/**
 * A recorded control total as text: an amount per currency, API-S-Money and lists of it as amounts;
 * anything else as stored, and no value for a map or a list the run recorded nothing in. The browser
 * formats and adds nothing (DG-FE-08).
 */
export function recorded(value: unknown): string {
  if (typeof value === "object" && value !== null && Object.keys(value).length === 0) {
    return NO_VALUE;
  }
  const totals = currencyTotals(value);
  if (totals !== null) {
    return totals.map(([code, total]) => amount(total, code)).join(", ");
  }
  const money = isMoney(value) ? [value] : Array.isArray(value) ? value.filter(isMoney) : [];
  if (money.length > 0 && (!Array.isArray(value) || money.length === value.length)) {
    return money.map((item) => amount(item.amount, item.currency)).join(", ");
  }
  return valueText(value);
}

const INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;
const SYSTEM_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * A stored parameter as recorded. An instant and a system id differ from one world to the next and
 * are masked in captures (SCR-TID-05).
 */
function parameterValue(name: string, value: unknown): ReactNode {
  const text = valueText(value);
  return INSTANT.test(text) || SYSTEM_ID.test(text) ? (
    <span key={name} data-volatile="">
      {text}
    </span>
  ) : (
    text
  );
}

/** When the run was recorded: masked in captures (SCR-TID-05). */
function Instant({ value }: { readonly value: string | null }) {
  return value === null ? (
    <NoValue />
  ) : (
    <time dateTime={value} data-volatile="" className="num">
      {formatTimestamp(value, { seconds: true })}
    </time>
  );
}

/** DS-FMT-23: a hash or a system id as its first 8 and last 4 characters, with the full value and copy. */
function SystemValue({ value, copyLabel }: { readonly value: string; readonly copyLabel: string }) {
  return (
    <span className="inline-flex items-center gap-1" data-volatile="">
      <span aria-hidden="true" className="font-mono text-mono-sm text-fg-1">
        {hashPrefix(value)}
      </span>
      <span className="sr-only">{value}</span>
      <Button
        variant="ghost"
        size="sm"
        icon={CopySimple}
        aria-label={copyLabel}
        onClick={() => {
          void navigator.clipboard
            .writeText(value)
            .then(() => announce(t("reports.stamp.copied"), "polite"));
        }}
      />
    </span>
  );
}

// The two columns are fixed, so a long recorded value wraps inside the table instead of widening it.
const TABLE =
  "w-full table-fixed border-separate border-spacing-0 rounded-md border border-default bg-surface";
const CELL = "border-t border-hairline px-3 py-2 text-body-sm text-fg-1";
/** A recorded key (mono) and a catalogue word, as the row header of a name and value table. */
const KEY =
  "w-2/5 break-words border-t border-hairline px-3 py-2 text-start align-top font-mono text-mono-sm font-normal text-fg-2";
const WORD =
  "w-2/5 break-words border-t border-hairline px-3 py-2 text-start align-top text-body-sm font-normal text-fg-2";
const LINK_BUTTON =
  "inline-flex h-[var(--control-h)] shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-md border border-control bg-surface px-3 text-body-sm font-medium text-fg-1 hover:bg-hover active:bg-active";

interface RecordTableProps {
  readonly title: string;
  readonly testId: string;
  readonly rows: readonly (readonly [string, ReactNode])[];
  /** What the table says when the run recorded none. */
  readonly empty: string;
  /** Names that are words of the catalogue rather than recorded keys. */
  readonly words?: boolean;
}

/**
 * A static table of names and values with its title as the caption (SCREENS_B §5.3 "static tables";
 * "parameters table `caption`"). A table the run recorded nothing for says so in one row.
 */
function RecordTable({ title, testId, rows, empty, words = false }: RecordTableProps) {
  return (
    <table data-testid={testId} className={TABLE}>
      <caption className="mb-2 text-start text-title-sm text-fg-1">{title}</caption>
      <tbody>
        {rows.length === 0 ? (
          <tr>
            <td colSpan={2} className="px-3 py-2 text-body-sm text-fg-2">
              {empty}
            </td>
          </tr>
        ) : (
          rows.map(([name, value], index) => (
            <tr key={name}>
              <th scope="row" className={cn(words ? WORD : KEY, index === 0 && "border-t-0")}>
                {name}
              </th>
              <td className={cn(CELL, "break-words", index === 0 && "border-t-0")}>{value}</td>
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}

export function ReportRunPage() {
  const { runId = "" } = useParams();
  const me = useMe();
  const access = useAccess();
  if (me.isError) {
    return <Banner tone="negative" title={me.error.message} />;
  }
  if (me.data === undefined) {
    return <Skeleton region={t("reports.run.region")} shape="rows" count={8} />;
  }
  if (!mayReadReportRuns(access)) {
    return (
      <div data-testid="SF-08-page" className="px-[var(--gutter)]">
        <ReportRunsAccessLimited />
      </div>
    );
  }
  return <RunRecord key={runId} runId={runId} me={me.data} />;
}

interface RunRecordProps {
  readonly runId: string;
  readonly me: Me;
}

function RunRecord({ runId, me }: RunRecordProps) {
  const navigate = useNavigate();
  const run = useQuery({
    queryKey: reportRunKey(runId),
    queryFn: async () => {
      const data = await fetchReportRun(runId);
      await ensureCurrencyCodes([
        ...moneyCurrencies(data.control_totals),
        ...totalCurrencies(data.control_totals),
      ]);
      return data;
    },
    retry: (count, error) => !(error instanceof ApiProblem && error.status === 404) && count < 1,
    // A run that is still computing is read again until it ends.
    refetchInterval: (query) => (isRunning(query.state.data) ? JOB_POLL_INTERVAL_MS : false),
  });

  if (run.isError) {
    if (run.error instanceof ApiProblem && run.error.status === 404) {
      // SCR-ST-07: no run with this id, or one the viewer may not see (API-R-41 answers both alike).
      return (
        <div data-testid="SF-08-page" className="px-[var(--gutter)]">
          <EmptyState
            title={t("reports.run.notFound.title")}
            description={t("reports.run.notFound.description")}
            action={{
              label: t("reports.run.notFound.action"),
              onAction: () => void navigate(REPORT_RUNS_ROUTE),
            }}
          />
        </div>
      );
    }
    return (
      <div data-testid="SF-08-page" className="px-[var(--gutter)] py-[var(--panel-pad)]">
        <Banner
          tone="negative"
          title={t("reports.run.loadError")}
          actions={
            <Button variant="link" onClick={() => void run.refetch()}>
              {t("reports.report.retry")}
            </Button>
          }
        >
          <p>{run.error instanceof ApiProblem ? run.error.title : run.error.message}</p>
        </Banner>
      </div>
    );
  }
  if (run.data === undefined) {
    return (
      <div data-testid="SF-08-page" className="px-[var(--gutter)] py-[var(--panel-pad)]">
        <Skeleton region={t("reports.run.region")} shape="rows" count={8} />
      </div>
    );
  }
  return <RunBody run={run.data} me={me} />;
}

interface RunBodyProps {
  readonly run: ReportRun;
  readonly me: Me;
}

function RunBody({ run, me }: RunBodyProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const built = useBuiltPaths();
  const access = useAccess();
  const computing = isRunning(run);
  const result = rerunResultOf(location.state);

  // The job of a run that is still computing (DS-CMP-24), for who may read it (04 API-R-11); another
  // reader sees the run computing without its progress, and the run is read again until it ends.
  const ownJob = useJob(computing && mayReadRunJob(run, me.user.id, access) ? run.job_id : null);

  // RV-03: the rerun is a command that answers 202 with a job; its result names the new run.
  const rerun = useCommand({
    method: "POST",
    path: `${REPORT_RUNS_PATH}/${run.id}/rerun`,
    invalidates: [EVERY_REPORT_RUN],
  });
  const job = rerun.job;
  // The job shows from the 202 answer on, before its first read answers.
  const rerunJob: JobProgressJob | null =
    rerun.jobId === null
      ? null
      : (job ?? {
          id: rerun.jobId,
          state: "QUEUED",
          progress: { done: 0, total: null },
          started_at: null,
          problem: null,
        });
  const ended = job !== undefined && isTerminal(job) ? job : null;
  const rerunning = rerunJob !== null && ended === null;
  const opened = useRef<string | null>(null);
  useEffect(() => {
    if (ended === null || ended.state !== "SUCCEEDED" || opened.current === ended.id) {
      return;
    }
    const next = ended.result?.report_run_id;
    if (typeof next !== "string") {
      return;
    }
    opened.current = ended.id;
    const state: { readonly rerun: RerunResult } = {
      rerun: {
        ofId: run.id,
        ofNo: run.report_run_no,
        outputIdentical: ended.result?.output_sha256_equal === true,
        totalsIdentical: ended.result?.control_totals_equal === true,
      },
    };
    void navigate(reportRunRoute(next), { state });
  }, [ended, navigate, run.id, run.report_run_no]);

  const status = chipFor("E-67", run.status);
  const label = t("reports.report.running", { name: run.report.name });
  const offer = rerunOffer(run);
  const view = built.has(REPORT_ROUTE) ? reportViewHref(run) : null;
  const output = run.output;
  const mayDownload = access.holdsAnywhere(
    PACK_CODES.has(run.report.code) ? EVIDENCE_EXPORT_PERMISSION : REPORT_EXPORT_PERMISSION,
  );
  const asOf = runAsOf(run);

  const breadcrumb: Crumb[] = [
    ...(access.holdsAnywhere(REPORT_RUN_PERMISSION) && built.has(REPORTS_ROUTE)
      ? [{ label: t("reports.report.breadcrumb"), to: REPORTS_ROUTE }]
      : []),
    { label: t("reports.tabs.runs"), to: REPORT_RUNS_ROUTE },
  ];
  const meta: MetaItem[] = [
    {
      label: t("reports.stamp.report"),
      value: t("reports.stamp.reportValue", {
        name: run.report.name,
        version: run.report.version,
      }),
    },
    {
      label: t("reports.stamp.entity"),
      value:
        run.entity_scope.length === 0 ? (
          <NoValue />
        ) : (
          <span className="font-mono text-mono-sm">
            {run.entity_scope.map((item) => item.code).join(", ")}
          </span>
        ),
    },
    {
      label: t("reports.stamp.book"),
      value: run.book === null ? <NoValue /> : bookLabel(run.book),
    },
    { label: t("reports.stamp.asOf"), value: asOf === null ? <NoValue /> : formatDate(asOf) },
    {
      label: t("reports.stamp.source"),
      value:
        run.period_lock_id === null ? (
          <span data-volatile="">
            {t("reports.stamp.current", { at: formatTimestamp(run.known_at) })}
          </span>
        ) : (
          <span data-volatile="">
            {t("reports.run.source.locked", { lock: hashPrefix(run.period_lock_id) })}
          </span>
        ),
    },
    {
      label: t("reports.stamp.engine"),
      value: (
        <span data-volatile="">
          {t("reports.run.engine", {
            version: run.engine_release.engine_version,
            build: run.engine_release.build_sha.slice(0, 8),
          })}
        </span>
      ),
    },
    { label: t("reports.stamp.runBy"), value: run.run_by.display_name },
    { label: t("reports.run.meta.started"), value: <Instant value={run.started_at} /> },
    { label: t("reports.run.meta.finished"), value: <Instant value={run.finished_at} /> },
  ];

  const showsBanner =
    result !== null ||
    run.status === "FAILED" ||
    computing ||
    rerunning ||
    (ended !== null && ended.state !== "SUCCEEDED") ||
    rerun.problem !== null;
  const banners = !showsBanner ? undefined : (
    <div className="flex flex-col gap-2">
      {result === null ? null : (
        <div data-testid="SF-08-banner-rerun-result">
          <Banner
            tone={result.outputIdentical && result.totalsIdentical ? "positive" : "warning"}
            title={t("reports.run.rerunOf", { run: result.ofNo })}
            actions={
              <Link
                to={reportRunRoute(result.ofId)}
                className="text-body-sm text-accent-fg hover:text-accent-fg-hover hover:underline"
              >
                {t("reports.run.openOriginal", { run: result.ofNo })}
              </Link>
            }
          >
            <p>
              {t("reports.runDetails.outputIdentical", {
                answer: t(
                  result.outputIdentical ? "reports.runDetails.yes" : "reports.runDetails.no",
                ),
              })}
            </p>
            <p>
              {t("reports.runDetails.totalsIdentical", {
                answer: t(
                  result.totalsIdentical ? "reports.runDetails.yes" : "reports.runDetails.no",
                ),
              })}
            </p>
          </Banner>
        </div>
      )}
      {run.status === "FAILED" ? (
        <div data-testid="SF-08-banner-run-failed">
          {/* DS-CMP-29: the banner is present on load, so it is a static element with a heading. */}
          <Banner
            tone="negative"
            announce="static"
            title={t("reports.run.failed", {
              problem: run.problem?.title ?? t("reports.run.failedUnnamed"),
            })}
          >
            {run.problem?.detail === undefined || run.problem.detail === null ? null : (
              <p>{run.problem.detail}</p>
            )}
            <JobReference run={run} createdJobId={null} />
          </Banner>
        </div>
      ) : null}
      {computing ? (
        ownJob.data === undefined ? (
          <p role="status" className="text-body-sm text-fg-2">
            {label}
          </p>
        ) : (
          <JobProgress label={label} job={ownJob.data} unit={t("reports.export.unit")} />
        )
      ) : null}
      {rerunning ? (
        <JobProgress label={label} job={rerunJob} unit={t("reports.export.unit")} />
      ) : null}
      {ended !== null && ended.state !== "SUCCEEDED" ? (
        <Banner tone="negative" title={t("common.job.failed", { label })}>
          {ended.problem === null ? null : <p>{ended.problem.title}</p>}
        </Banner>
      ) : null}
      {/* DS-CMP-29 (rev 1.101): the title, the detail and every sentence of a refused rerun — the lock
          to pass stands in a finding alone where the run names a record that froze no dataset. */}
      <RefusalBanner problem={rerun.problem} />
    </div>
  );

  const heads = Object.entries(run.ledger_heads).map(
    ([book, head]): readonly [string, ReactNode] => {
      const record =
        typeof head === "object" && head !== null
          ? (head as Readonly<Record<string, unknown>>)
          : {};
      const sequence = typeof record.chain_seq === "number" ? record.chain_seq : null;
      const seal = typeof record.seal_sha256 === "string" ? record.seal_sha256 : null;
      return [
        bookLabel(book),
        <span key={book} className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="num" data-volatile="">
            {t("reports.run.head.chain", {
              sequence: sequence === null ? NO_VALUE : formatNumber(sequence, { kind: "count" }),
            })}
          </span>
          {seal === null ? null : (
            <span className="inline-flex items-center gap-1.5">
              {t("reports.run.head.seal")}
              <SystemValue value={seal} copyLabel={t("reports.run.head.copySeal")} />
            </span>
          )}
        </span>,
      ];
    },
  );

  return (
    <div data-testid="SF-08-page" className="flex flex-col gap-4">
      <RecordHeader
        title={t("reports.run.title", { run: run.report_run_no })}
        breadcrumb={breadcrumb}
        chips={
          status === null ? undefined : (
            <StatusChip status={status.status} caption={status.caption} />
          )
        }
        actions={
          <>
            {view === null ? null : (
              <Link to={view} className={LINK_BUTTON}>
                {t("reports.run.openView")}
              </Link>
            )}
            {output === null || !mayDownload ? null : (
              <a href={reportOutputHref(run.id)} download className={LINK_BUTTON}>
                <DownloadSimple aria-hidden="true" className="shrink-0" />
                {t("reports.run.download", { format: output.format })}
              </a>
            )}
            {computing ? null : (
              <Button
                variant="primary"
                loading={rerun.pending || rerunning}
                disabledReason={
                  offer === "unbound" ? t("reports.run.sources.legacy_unbound") : undefined
                }
                onClick={() => void rerun.submit()}
              >
                {t(
                  offer === "new-evaluation"
                    ? "reports.run.rerun.newEvaluation"
                    : "reports.runDetails.rerun",
                )}
              </Button>
            )}
          </>
        }
        meta={meta}
        banner={banners}
      />
      {/* SCREENS_B §5.3, 1440 px: the parameters and what the run read on the left, the figures on
          the right, in the wireframe's proportions; one column below. */}
      <div className="grid grid-cols-1 items-start gap-6 px-[var(--gutter)] pb-[var(--panel-pad)] xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="flex min-w-0 flex-col gap-6">
          <RecordTable
            title={t("reports.runDetails.parameters")}
            testId="SF-08-grid-run-parameters"
            rows={Object.entries(run.parameters).map(([key, value]) => [
              key,
              parameterValue(key, value),
            ])}
            empty={t("reports.run.table.noParameters")}
          />
          <RecordTable
            title={t("reports.runDetails.source")}
            testId="SF-08-grid-run-source"
            words
            rows={[
              [
                t("reports.run.sourceTable.lock"),
                run.period_lock_id === null ? (
                  t("reports.runs.source.current")
                ) : (
                  <SystemValue
                    key="lock"
                    value={run.period_lock_id}
                    copyLabel={t("reports.run.sourceTable.copyLock")}
                  />
                ),
              ],
              [
                t("reports.run.sourceTable.knownAt"),
                <span key="known" className="flex flex-col">
                  <Instant value={run.known_at} />
                  <span className="text-fg-2">{knownAtBasis(run)}</span>
                </span>,
              ],
              [
                t("reports.run.sourceTable.sources"),
                <span key="sources" className="flex flex-col" data-volatile="">
                  <span>{sourcesText(run)}</span>
                  {run.sources.open.length === 0 ? null : (
                    <span className="text-fg-2">
                      {t("reports.run.sources.notBound", { items: run.sources.open.join(", ") })}
                    </span>
                  )}
                </span>,
              ],
            ]}
            empty={t("reports.run.table.noOutput")}
          />
        </div>
        <div className="flex min-w-0 flex-col gap-6">
          <RecordTable
            title={t("reports.runDetails.controlTotals")}
            testId="SF-08-grid-run-control-totals"
            rows={Object.entries(run.control_totals ?? {}).map(([key, value]) => {
              const text = recorded(value);
              return [
                key,
                text === NO_VALUE ? (
                  <NoValue key={key} />
                ) : (
                  <span key={key} className="num">
                    {text}
                  </span>
                ),
              ];
            })}
            empty={t("reports.run.table.noTotals")}
          />
          <TieOutStrip results={run.tie_out_results} />
          <RecordTable
            title={t("reports.runDetails.output")}
            testId="SF-08-grid-run-output"
            words
            rows={
              output === null
                ? []
                : [
                    [
                      t("reports.run.output.format"),
                      <span key="format" className="font-mono text-mono-sm">
                        {output.format}
                      </span>,
                    ],
                    [
                      t("reports.stamp.sha"),
                      <SystemValue
                        key="sha"
                        value={output.sha256}
                        copyLabel={t("reports.stamp.copySha")}
                      />,
                    ],
                    [
                      t("reports.run.output.manifest"),
                      output.manifest_href === null || !mayDownload ? (
                        <NoValue key="manifest" />
                      ) : (
                        <a
                          key="manifest"
                          href={output.manifest_href}
                          download
                          className="text-accent-fg hover:text-accent-fg-hover hover:underline"
                        >
                          {t("reports.runDetails.manifest")}
                        </a>
                      ),
                    ],
                    [
                      t("reports.stamp.rows"),
                      run.row_count === null ? (
                        <NoValue key="rows" />
                      ) : (
                        <span key="rows" className="num">
                          {formatNumber(run.row_count, { kind: "count" })}
                        </span>
                      ),
                    ],
                  ]
            }
            empty={t("reports.run.table.noOutput")}
          />
          <RecordTable
            title={t("reports.runDetails.ledgerHeads")}
            testId="SF-08-grid-run-ledger-heads"
            words
            rows={heads}
            empty={t("reports.run.table.noHeads")}
          />
        </div>
      </div>
    </div>
  );
}
