// SF-04 Schedules: revenue waterfall (SCREENS_B §4.1; §0.5 RV-01 to RV-14; §5.6 RPT-01; SCREENS RT-25,
// SCR-URL-06, SCR-URL-16, SCR-URL-18, SCR-URL-24; DESIGN_SYSTEM DS-CMP-10, DS-CMP-14, DS-CMP-19, DS-CMP-31,
// DS-CH-01, DS-FMT-03, DS-FMT-19; 04 API-R-18, API-R-35, API-R-41, API-R-44; BUILD_SPEC RPS-7). The
// `h1` "Schedules" with "Run details" and "Export"; the parameters toolbar (Rows, Granularity, From, To,
// Measure, then the Layout switch); for `layout=waterfall` one `revenue_waterfall` report run per
// parameter set with the run stamp, the As locked banners, the tie-out strip, the DS-CH-01 chart and the
// grid "Revenue waterfall" whose figures drill through SB-R-07, plus the "Flags" column of open anomaly
// flags; for `layout=lines` the grid "Schedule lines" of `GET /schedule-lines`, which has no run stamp
// because it reads current schedule lines. The screen parameters `rows`, `granularity` and `measure`
// reach the run in uppercase, and `f.period=between:<from>,<to>` names the range (SCR-URL-24).
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router";

import { contextSearch } from "../../app/shell/IconRail";
import { DataGrid } from "../../components/data-grid/DataGrid";
import type { GridColumn, GridSource } from "../../components/data-grid/types";
import {
  type Explanation,
  ExplainPanel,
  ExplainProvider,
} from "../../components/explain/ExplainPanel";
import { ExplainTrigger, type FigureRef } from "../../components/explain/ExplainTrigger";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { JobProgress } from "../../components/feedback/JobProgress";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { Money } from "../../components/money/Money";
import { NoValue } from "../../components/money/Num";
import { Button } from "../../components/ui/Button";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { StatusChip } from "../../components/ui/StatusChip";
import { type Access, useAccess } from "../../lib/access";
import { fetchListPage } from "../../lib/api/lists";
import { ApiProblem } from "../../lib/api/problems";
import { EXCEPTIONS_PATH, type ExceptionItem } from "../../lib/api/queries/exceptions";
import { fetchExplanation } from "../../lib/api/queries/explain";
import { ensureCurrencyCodes } from "../../lib/api/queries/journal-runs";
import { useMe } from "../../lib/api/queries/me";
import {
  fetchReportDefinition,
  fetchReportRun,
  REPORT_EXPORT_PERMISSION,
  type ReportDefinition,
  reportDefinitionKey,
  type ReportRow,
  reportRunKey,
} from "../../lib/api/queries/reports";
import {
  fetchScheduleRangePage,
  type ScheduleLine,
  type ScheduleRangeQuery,
  scheduleRangeKey,
} from "../../lib/api/queries/schedule-lines";
import {
  fetchPeriods,
  type Period,
  periodLabel,
  periodsKey,
  STRUCTURE_READ_PERMISSION,
} from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import { formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { decodeValue, rawParams, withParams } from "../../lib/url/params";
import { figureFromLink, moneyText } from "../contracts/obligation-pane";
import { AsLockedBanner, LOCKED_STATES } from "../reports/viewer/AsLockedBanner";
import { CellContributors, type CellRequest } from "../reports/viewer/CellContributors";
import { ExportMenu } from "../reports/viewer/ExportMenu";
import { ParametersToolbar } from "../reports/viewer/ParametersToolbar";
import { ReportChart } from "../reports/viewer/ReportChart";
import { type DrillRequest, figureLabel, ReportGrid } from "../reports/viewer/ReportGrid";
import { RunDetailsDrawer } from "../reports/viewer/RunDetailsDrawer";
import { RunStamp } from "../reports/viewer/RunStamp";
import {
  datasetLock,
  hasLockDataset,
  isAsLocked,
  namesAnotherLock,
  isMoney,
  type ReportContext,
  reportColumns,
  runParameters,
  sectionsOf,
  totalsRows,
  validateParameters,
} from "../reports/viewer/specs";
import { TieOutStrip } from "../reports/viewer/TieOutStrip";
import { JobReference } from "../reports/viewer/JobReference";
import { useReportRun } from "../reports/viewer/useReportRun";
import { useViewContext } from "../reports/viewer/useViewContext";

/** SCREENS SCR-URL-01 to SCR-URL-03: the context a schedules link keeps. */
const CONTEXT = ["entity", "period", "book"] as const;
export const WATERFALL_REPORT = "revenue_waterfall";
const RUN_DETAILS = "run-details";
/** SCREENS_B §4.1 wireframe order of the toolbar fields. */
const TOOLBAR_KEYS = [
  "row_dimension",
  "granularity",
  "from_period_key",
  "to_period_key",
  "measure",
] as const;
export const LAYOUTS = ["waterfall", "lines"] as const;
export type Layout = (typeof LAYOUTS)[number];
/** SCREENS_B RPT-01: above 36 months the default granularity is Quarter. */
const MAX_MONTH_COLUMNS = 36;
const PERIOD_FILTER = "f.period";
const CONTRACT_FILTER = "f.contract";
/** SCR-URL-24 screen parameter of SF-04 `layout=lines`: an obligation key or id (API-R-35). */
const OBLIGATION_PARAM = "obligation";
/** SCREENS_B §4.1 anomaly flags: `GET /exceptions?source=ANOMALY&status=OPEN,IN_PROGRESS`. */
const OPEN_FLAG_STATUSES = ["OPEN", "IN_PROGRESS"] as const;
const FLAGS_LIMIT = 200;

export function Schedules() {
  // Waterfall figures and schedule lines open Explain (DS-CMP-15), so the page docks the panel.
  const loadExplanation = useCallback(
    async (figure: FigureRef) => (await fetchExplanation(figure)) as Explanation,
    [],
  );
  return (
    <ExplainProvider load={loadExplanation}>
      <SchedulesScreen />
    </ExplainProvider>
  );
}

function SchedulesScreen() {
  const me = useMe();
  const access = useAccess();
  // §0.5 "The context of a view" (rev 1.92): the screen is mounted once the address holds its context.
  const viewContext = useViewContext();
  const definition = useQuery({
    queryKey: reportDefinitionKey(WATERFALL_REPORT),
    queryFn: () => fetchReportDefinition(WATERFALL_REPORT),
    retry: (count, error) => !(error instanceof ApiProblem && error.status === 404) && count < 1,
  });
  if (me.isError) {
    return <Banner tone="negative" title={me.error.message} />;
  }
  if (definition.error !== null) {
    return (
      <div data-testid="SF-04-page" className="flex flex-col gap-4">
        <h1 tabIndex={-1} className="text-title-lg text-fg-1">
          {t("schedules.title")}
        </h1>
        <Banner
          tone="negative"
          title={t("schedules.loadError")}
          actions={
            <Button variant="link" onClick={() => void definition.refetch()}>
              {t("reports.report.retry")}
            </Button>
          }
        >
          <p>{definition.error.message}</p>
        </Banner>
      </div>
    );
  }
  if (viewContext.failure !== null) {
    // The entities, the books or the calendar that fill the address could not be read: no run is
    // asked on half a context (§0.5 "The context of a view").
    return (
      <div data-testid="SF-04-page" className="flex flex-col gap-4">
        <h1 tabIndex={-1} className="text-title-lg text-fg-1">
          {t("schedules.title")}
        </h1>
        <Banner
          tone="negative"
          title={t("schedules.loadError")}
          actions={
            <Button variant="link" onClick={viewContext.retry}>
              {t("reports.report.retry")}
            </Button>
          }
        >
          <p>{viewContext.failure.message}</p>
        </Banner>
      </div>
    );
  }
  if (me.data === undefined || definition.data === undefined || !viewContext.settled) {
    return <Skeleton region={t("schedules.region")} shape="rows" count={8} />;
  }
  return <SchedulesBody definition={definition.data} access={access} />;
}

/** `between:<from>,<to>` of `f.period` (SCREENS SCR-URL-10). */
function periodRange(search: string): { readonly from: string; readonly to: string } | null {
  const raw = rawParams(search).find((param) => param.name === PERIOD_FILTER)?.value ?? null;
  const match = raw === null ? null : /^between:([^,]+),([^,]+)$/.exec(raw);
  return match === null
    ? null
    : { from: decodeValue(match[1] ?? ""), to: decodeValue(match[2] ?? "") };
}

/** The `is:<value>` of a single-value `f.<field>` parameter. */
function isFilter(search: string, name: string): string | null {
  const raw = rawParams(search).find((param) => param.name === name)?.value ?? null;
  return raw?.startsWith("is:") === true ? decodeValue(raw.slice(3)) : null;
}

function screenParam<T extends string>(value: string | null, allowed: readonly T[]): T | null {
  const lower = value?.toLowerCase() ?? null;
  return allowed.find((item) => item === lower) ?? null;
}

/** The context period: the URL period, else the first open period of the calendar (SCREENS §1.3). */
function resolvedPeriod(periods: readonly Period[], key: string | null): Period | null {
  return (
    periods.find((item) => item.period.period_key === key) ??
    periods.find((item) => item.is_first_open) ??
    null
  );
}

interface SchedulesBodyProps {
  readonly definition: ReportDefinition;
  readonly access: Access;
}

function SchedulesBody({ definition, access }: SchedulesBodyProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const toast = useToast();
  const search = location.search;
  const params = new URLSearchParams(search);
  const entity = params.get("entity");
  const book = params.get("book");
  const snapshot = params.get("snapshot");
  const knownAt = params.get("known_at");
  const currencyView = params.get("currency_view");
  const runId = params.get("run");
  const drawer = params.get("drawer");
  const layout = screenParam(params.get("layout"), LAYOUTS) ?? "waterfall";
  const obligation = params.get(OBLIGATION_PARAM);
  const contract = isFilter(search, CONTRACT_FILTER);
  const range = periodRange(search);
  const ctxSearch = contextSearch(search, CONTEXT);

  // SCR-URL-20: search updates keep raw values; the latest search survives an awaited command.
  const latestSearch = useRef(search);
  useEffect(() => {
    latestSearch.current = search;
  });
  const replace = useCallback(
    (changes: Readonly<Record<string, string | null>>) => {
      void navigate({ search: withParams(latestSearch.current, changes) }, { replace: true });
    },
    [navigate],
  );

  const periodQuery = { entity: entity ?? "", book: book ?? "" };
  // The periods of one entity: `config.read` is asked for that entity (SCR-PERM-02 (a)).
  const periodsEnabled =
    entity !== null && book !== null && access.holds(STRUCTURE_READ_PERMISSION, { code: entity });
  const periods = useQuery({
    queryKey: periodsKey(periodQuery),
    queryFn: () => fetchPeriods(periodQuery),
    enabled: periodsEnabled,
  });
  const calendar = periods.data ?? [];
  const current = resolvedPeriod(calendar, params.get("period"));
  const period = current?.period.period_key ?? params.get("period");
  const context: ReportContext = {
    entity,
    book,
    periodKey: period,
    periods: calendar,
    snapshot,
    knownAt,
    currencyView,
  };
  // The record that locked the period, and the lock whose datasets stand for it (`dataset_lock`).
  const lock = current?.current_lock ?? null;
  const standingLock = datasetLock(context);
  const locked = current !== null && LOCKED_STATES.has(current.state) && lock !== null;
  const contextKey = [entity, book, period].join("|");
  const [currentChosen, setCurrentChosen] = useState<string | null>(null);
  const calendarReady = !periodsEnabled || periods.data !== undefined || periods.isError;

  // RV-04: a locked context period defaults to its lock snapshot until the user shows current figures.
  // Rev 1.98: the waterfall is one of the reports a lock freezes (`hasLockDataset`), and while the
  // lock is the source the run is the lock's period alone and the bar's fields are unavailable.
  // The banner's sentences are the context period's lock's: an address that names another lock is
  // kept as written and the page says neither (report.tsx).
  const asLocked = layout === "waterfall" && isAsLocked(definition, context);
  const anotherLock = namesAnotherLock(definition, context);
  // Rev 1.101: the lock is the one whose datasets stand — on a permanently locked period the LOCK
  // the permanent lock sealed. A locked period without one has no default and no offer.
  const standing = standingLock !== null;
  const needsSnapshot =
    hasLockDataset(definition.code) &&
    standing &&
    layout === "waterfall" &&
    locked &&
    snapshot === null &&
    runId === null &&
    currentChosen !== contextKey;
  const lockId = standingLock?.id ?? null;
  useEffect(() => {
    if (needsSnapshot && lockId !== null) {
      replace({ snapshot: encodeURIComponent(lockId) });
    }
  }, [needsSnapshot, lockId, replace]);

  // The range: `f.period`, else the context fiscal year (RPT-01 defaults). A lock holds one period,
  // so while it is the source both ends are the context period, whatever the address's range says.
  const year =
    current === null
      ? []
      : calendar.filter((item) => item.period.fiscal_year === current.period.fiscal_year);
  const fromKey = asLocked
    ? (period ?? "")
    : (range?.from ?? year[0]?.period.period_key ?? period ?? "");
  const toKey = asLocked
    ? (period ?? "")
    : (range?.to ?? year.at(-1)?.period.period_key ?? period ?? "");
  const index = (key: string) => calendar.findIndex((item) => item.period.period_key === key);
  const months = index(fromKey) >= 0 && index(toKey) >= 0 ? index(toKey) - index(fromKey) + 1 : 0;
  const defaultGranularity = months > MAX_MONTH_COLUMNS ? "QUARTER" : "MONTH";
  const urlValues: Readonly<Record<string, string>> = {
    from_period_key: fromKey,
    to_period_key: toKey,
    row_dimension: (params.get("rows") ?? "contract").toUpperCase(),
    granularity: (params.get("granularity") ?? defaultGranularity).toUpperCase(),
    measure: (params.get("measure") ?? "total").toUpperCase(),
    ...(contract === null ? {} : { contract_external_id: contract }),
  };
  const [draft, setDraft] = useState<Readonly<Record<string, string>> | null>(null);
  const values = draft ?? urlValues;
  const parameters = runParameters(definition, context, urlValues);
  const [clientErrors, setClientErrors] = useState<Readonly<Record<string, string>>>({});

  const { problem, run, rows, pendingJob, computing, createdJobId, restart } = useReportRun({
    definition,
    parameters,
    contextSignature: [entity, book, period, snapshot, knownAt, currencyView].join("|"),
    ready: calendarReady && !needsSnapshot,
    runId,
    replace,
    enabled: layout === "waterfall",
  });

  const runReport = () => {
    const next = runParameters(definition, context, values);
    const errors = validateParameters(context, next);
    setClientErrors(errors);
    if (Object.keys(errors).length > 0) {
      return;
    }
    if (layout === "waterfall" && computing) {
      toast.show({
        tone: "neutral",
        message: t("reports.report.alreadyRunning", { name: definition.name }),
      });
      return;
    }
    if (asLocked) {
      // The fields take no input while the lock is the source, so there is nothing to write: the
      // range the bar shows is the lock's month, not a choice, and written as `f.period` it
      // would still be there when current figures are shown.
      setDraft(null);
      restart();
      replace({ run: null });
      return;
    }
    const lower = (key: string, fallback: string) => {
      const value = values[key]?.toLowerCase() ?? fallback;
      return value === fallback ? null : encodeURIComponent(value);
    };
    const defaultFrom = year[0]?.period.period_key ?? null;
    const defaultTo = year.at(-1)?.period.period_key ?? null;
    const from = values.from_period_key ?? "";
    const to = values.to_period_key ?? "";
    setDraft(null);
    restart();
    replace({
      run: null,
      rows: lower("row_dimension", "contract"),
      granularity: lower("granularity", defaultGranularity.toLowerCase()),
      measure: lower("measure", "total"),
      // Raw `f.*` values keep the operator colon and the comma (SCR-URL-20).
      [PERIOD_FILTER]:
        from === defaultFrom && to === defaultTo
          ? null
          : `between:${encodeURIComponent(from)},${encodeURIComponent(to)}`,
    });
  };

  const showCurrent = () => {
    setCurrentChosen(contextKey);
    replace({ snapshot: null, run: null });
  };
  const showLocked = () => {
    setCurrentChosen(null);
    if (lockId !== null) {
      replace({ snapshot: encodeURIComponent(lockId), run: null });
    }
  };

  const [cellRequest, setCellRequest] = useState<CellRequest | null>(null);
  const drill = ({ row, column, element }: DrillRequest) => {
    if (runId === null) {
      return;
    }
    setCellRequest({
      runId,
      rowKey: row.row_key,
      columnKey: column.key,
      label: figureLabel(row, column),
      element,
    });
  };
  const closeCell = useCallback((restoreFocus: boolean) => {
    setCellRequest((previous) => {
      if (restoreFocus && previous?.element?.isConnected === true) {
        previous.element.focus();
      }
      return null;
    });
  }, []);

  const [detailsRunId, setDetailsRunId] = useState<string | null>(null);
  const details = useQuery({
    queryKey: reportRunKey(detailsRunId ?? runId ?? ""),
    queryFn: () => fetchReportRun(detailsRunId ?? runId ?? ""),
    enabled: drawer === RUN_DETAILS && (detailsRunId ?? runId) !== null,
  });
  const openDetails = useCallback(
    (id: string | null) => {
      setDetailsRunId(id);
      replace({ drawer: RUN_DETAILS });
    },
    [replace],
  );

  // The refused creation's problem, bound to this parameter set and source (RV-01 rev 1.6; D-90e L9-PLT-Q-6).
  const serverErrors: Record<string, string> = {};
  const otherMessages: string[] = [];
  for (const error of problem?.errors ?? []) {
    const key = error.field?.startsWith("parameters.")
      ? error.field.slice("parameters.".length)
      : null;
    if (key !== null && (TOOLBAR_KEYS as readonly string[]).includes(key)) {
      serverErrors[key] = error.message;
    } else {
      otherMessages.push(error.message);
    }
  }

  const data = layout === "waterfall" ? run.data : undefined;
  const periodText = current === null ? (period ?? "") : periodLabel(current.period);
  const canExport = access.holdsAnywhere(REPORT_EXPORT_PERMISSION);
  const layoutControl = (
    <SegmentedControl<Layout>
      label={t("schedules.layout")}
      options={LAYOUTS.map((value) => ({ value, label: t(`schedules.layout.${value}`) }))}
      value={layout}
      onChange={(next) => {
        closeCell(false);
        replace({ layout: next === "waterfall" ? null : next, drawer: null });
      }}
    />
  );

  let body: ReactNode = null;
  if (layout === "lines" && !calendarReady) {
    // The range defaults to the context fiscal year, so the lines wait for the calendar.
    body = <Skeleton region={t("schedules.lines.title")} shape="rows" count={8} />;
  } else if (layout === "lines") {
    body = (
      <ScheduleLinesGrid
        query={{
          entity,
          book,
          fromPeriod: fromKey === "" ? null : fromKey,
          toPeriod: toKey === "" ? null : toKey,
          obligation,
          knownAt,
        }}
        periodText={periodText}
        onGoToContracts={() => void navigate(`/contracts${ctxSearch}`)}
      />
    );
  } else if (computing && data?.status !== "FAILED") {
    const label = t("reports.report.running", { name: definition.name });
    body =
      pendingJob !== null ? (
        <JobProgress label={label} job={pendingJob} unit={t("reports.export.unit")} />
      ) : (
        <Skeleton region={label} shape="rows" count={6} />
      );
  } else if (data?.status === "FAILED") {
    const label = t("reports.report.running", { name: definition.name });
    body = (
      <Banner
        tone="negative"
        title={t("common.job.failed", { label })}
        actions={
          <Button variant="link" onClick={runReport}>
            {t("reports.report.retry")}
          </Button>
        }
      >
        {data.problem === null ? null : <p>{data.problem.title}</p>}
        {/* SCR-ST-12 "Reference <job id prefix>" (RV-14 rev 1.7; D-91 SF-04 addition). */}
        <JobReference run={data} createdJobId={createdJobId} />
      </Banner>
    );
  } else if (run.isError || rows.isError) {
    body = (
      <Banner
        tone="negative"
        title={t("schedules.loadError")}
        actions={
          <Button
            variant="link"
            onClick={() => void (run.isError ? run.refetch() : rows.refetch())}
          >
            {t("reports.report.retry")}
          </Button>
        }
      />
    );
  } else if (data?.status === "SUCCEEDED") {
    body =
      rows.data === undefined ? (
        <Skeleton region={definition.name} shape="rows" count={8} />
      ) : (
        <WaterfallBody
          definition={definition}
          rows={rows.data}
          runId={data.id}
          entity={entity}
          period={period}
          periods={calendar}
          filtered={contract !== null}
          periodText={periodText}
          access={access}
          // An as-locked run draws no chart: its rows are the frozen dataset — one row an obligation
          // of the lock's period, every cell text (RV-04 rev 1.17) — and `reportChart` draws from a
          // totals row of money alone.
          chart={(section) => (
            <ReportChart
              definition={definition}
              run={data}
              section={section}
              periods={calendar}
              testId="SF-04-chart-waterfall"
            />
          )}
          onDrill={drill}
          onGoToContracts={() => void navigate(`/contracts${ctxSearch}`)}
        />
      );
  }

  return (
    <div className="flex min-h-full gap-4">
      <div data-testid="SF-04-page" className="flex min-w-0 flex-1 flex-col gap-4">
        <header className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <h1 tabIndex={-1} className="text-title-lg text-fg-1">
              {t("schedules.title")}
            </h1>
            {layout === "waterfall" ? (
              <span className="ms-auto inline-flex items-center gap-3">
                {data === undefined ? null : (
                  <Button variant="secondary" onClick={() => openDetails(null)}>
                    {t("reports.report.runDetails")}
                  </Button>
                )}
                {canExport && definition.output_formats.length > 0 ? (
                  <ExportMenu
                    definition={definition}
                    parameters={data?.parameters ?? parameters}
                    onDetails={openDetails}
                  />
                ) : null}
              </span>
            ) : null}
          </div>
          <ParametersToolbar
            key={contextKey}
            definition={definition}
            context={context}
            values={values}
            errors={{ ...serverErrors, ...clientErrors }}
            timeBands={null}
            keys={TOOLBAR_KEYS}
            testIdPrefix="SF-04"
            unavailable={asLocked ? t("reports.asLocked.noParameters") : undefined}
            onChange={(key, value) => setDraft({ ...values, [key]: value })}
            onRun={runReport}
          >
            {layoutControl}
          </ParametersToolbar>
          {data === undefined ? null : (
            <RunStamp
              run={data}
              testIdPrefix="SF-04"
              lockCreatedAt={
                standingLock !== null && data.period_lock_id === standingLock.id
                  ? standingLock.created_at
                  : null
              }
            />
          )}
          {layout === "waterfall" && locked && lock !== null && !anotherLock ? (
            <AsLockedBanner
              periodLabel={periodText}
              lockedAt={(standingLock ?? lock).created_at}
              asLocked={asLocked}
              frozen={hasLockDataset(definition.code)}
              standing={standing}
              onShowCurrent={showCurrent}
              onShowLocked={showLocked}
            />
          ) : null}
          {problem === null || otherMessages.length === 0 ? null : (
            <Banner tone="negative" title={problem.title}>
              {otherMessages.map((message) => (
                <p key={message}>{message}</p>
              ))}
            </Banner>
          )}
          {data === undefined ? null : (
            <TieOutStrip results={data.tie_out_results} testIdPrefix="SF-04" />
          )}
        </header>
        <div className="pb-[var(--panel-pad)]">{body}</div>
      </div>
      {cellRequest === null ? null : (
        <CellContributors
          key={`${cellRequest.rowKey}:${cellRequest.columnKey}`}
          request={cellRequest}
          onClose={closeCell}
          testIdPrefix="SF-04"
        />
      )}
      <ExplainPanel />
      {drawer === RUN_DETAILS && details.data !== undefined ? (
        <RunDetailsDrawer
          run={details.data}
          testIdPrefix="SF-04"
          onClose={() => {
            setDetailsRunId(null);
            replace({ drawer: null });
          }}
        />
      ) : null}
    </div>
  );
}

/** Open anomaly flags of the context entity and period, counted per contract external id (§8.4). */
async function fetchAnomalyCounts(
  entity: string,
  period: string | null,
): Promise<ReadonlyMap<string, number>> {
  const page = await fetchListPage<ExceptionItem>(
    EXCEPTIONS_PATH,
    { source: ["ANOMALY"], status: [...OPEN_FLAG_STATUSES], entity, period },
    null,
    { limit: FLAGS_LIMIT, count: false },
  );
  const counts = new Map<string, number>();
  for (const item of page.items) {
    if (item.source === "ANOMALY" && item.contract_external_id !== null) {
      counts.set(item.contract_external_id, (counts.get(item.contract_external_id) ?? 0) + 1);
    }
  }
  return counts;
}

interface WaterfallBodyProps {
  readonly definition: ReportDefinition;
  readonly rows: readonly ReportRow[];
  readonly runId: string;
  readonly entity: string | null;
  readonly period: string | null;
  readonly periods: readonly Period[];
  readonly filtered: boolean;
  readonly periodText: string;
  readonly access: Access;
  readonly chart: (section: ReturnType<typeof sectionsOf>[number]) => ReactNode;
  readonly onDrill: (request: DrillRequest) => void;
  readonly onGoToContracts: () => void;
}

function WaterfallBody({
  definition,
  rows,
  runId,
  entity,
  period,
  periods,
  filtered,
  periodText,
  access,
  chart,
  onDrill,
  onGoToContracts,
}: WaterfallBodyProps) {
  const flags = useQuery({
    queryKey: queryKey("exceptions", "tenant", { view: "anomaly-counts", entity, period }),
    queryFn: () => fetchAnomalyCounts(entity ?? "", period),
    // The anomalies of one entity: `contract.read` is asked for that entity.
    enabled: entity !== null && access.holds("contract.read", { code: entity }),
  });
  const counts = flags.data;
  const flagColumns = useMemo((): readonly GridColumn<ReportRow>[] => {
    const countOf = (row: ReportRow) => {
      const contract = row.contract_external_id;
      return typeof contract === "string" ? (counts?.get(contract) ?? 0) : 0;
    };
    return [
      {
        id: "flags",
        header: t("schedules.column.flags"),
        kind: "text",
        value: (row) => {
          const count = countOf(row);
          return count === 0 ? null : t("schedules.flags", { count, formatted: String(count) });
        },
        render: (row) => {
          const count = countOf(row);
          if (count === 0) {
            return null;
          }
          const formatted = formatNumber(count, { kind: "count" });
          return (
            <span className="inline-flex items-center">
              <span aria-hidden="true">
                <StatusChip status="Warning" caption={t("schedules.flags", { count, formatted })} />
              </span>
              <span className="sr-only">{t("schedules.flagsName", { count, formatted })}</span>
            </span>
          );
        },
        width: 152,
      },
    ];
  }, [counts]);

  if (rows.length === 0) {
    return filtered ? (
      <EmptyState title={t("schedules.noResults")} description="" headingLevel={2} />
    ) : (
      <EmptyState
        title={t("schedules.empty.title", { period: periodText })}
        description={t("schedules.empty.description")}
        headingLevel={2}
        action={{ label: t("schedules.empty.action"), onAction: onGoToContracts }}
      />
    );
  }
  const section = sectionsOf(definition, rows)[0];
  if (section === undefined) {
    return null;
  }
  const currencies = new Set(
    [...section.rows, ...section.totals].flatMap((row) =>
      Object.values(row).flatMap((value) => (isMoney(value) ? [value.currency] : [])),
    ),
  );
  return (
    <div className="flex flex-col gap-6">
      {entity === null && currencies.size > 1 ? (
        <Banner tone="info" announce="static" title={t("schedules.mixedCurrencies")} />
      ) : null}
      {chart(section)}
      <ReportGrid
        runId={runId}
        section={section}
        columns={reportColumns({ definition, section, periods, bands: [] })}
        totals={totalsRows(section)}
        onDrill={onDrill}
        testIdPrefix="SF-04"
        name="waterfall"
        title={t("schedules.grid.waterfall")}
        extraColumns={flagColumns}
      />
    </div>
  );
}

interface ScheduleLinesGridProps {
  readonly query: ScheduleRangeQuery;
  readonly periodText: string;
  readonly onGoToContracts: () => void;
}

/** SCREENS_B §4.1 "Grid columns: schedule lines" of the fields API-S-ScheduleLine carries (L7-3-Q-17). */
function lineColumns(book: string | null): readonly GridColumn<ScheduleLine>[] {
  const figure = (line: ScheduleLine): FigureRef =>
    figureFromLink(line.links.explain, book) ?? {
      objectType: "schedule_line",
      id: line.id,
      measure: "amount",
      book: book ?? undefined,
    };
  const label = (line: ScheduleLine) =>
    line.obligation_key === null
      ? t("contracts.obligation.schedule.explainLabel", { period: line.period.name })
      : t("contracts.schedules.explainLabel", {
          period: line.period.name,
          obligation: line.obligation_key,
        });
  return [
    {
      id: "obligation",
      header: t("schedules.lines.column.obligation"),
      kind: "text",
      value: (line) => line.obligation_key,
      render: (line) =>
        line.obligation_key === null ? (
          <NoValue />
        ) : (
          <span className="font-mono text-mono-sm text-fg-1">{line.obligation_key}</span>
        ),
      width: 120,
    },
    {
      id: "entity",
      header: t("schedules.lines.column.entity"),
      kind: "text",
      value: (line) => line.entity.code,
      render: (line) => (
        <span className="font-mono text-mono-sm text-fg-1">{line.entity.code}</span>
      ),
      width: 104,
    },
    {
      id: "period",
      header: t("schedules.lines.column.period"),
      kind: "text",
      value: (line) => line.period.name,
      width: 112,
    },
    {
      id: "line_type",
      header: t("schedules.lines.column.lineType"),
      kind: "text",
      value: (line) => t(`contracts.schedule.lineType.${line.line_type}`),
      width: 200,
    },
    {
      id: "currency",
      header: t("schedules.lines.column.currency"),
      kind: "text",
      value: (line) => line.amount.currency,
      render: (line) => (
        <span className="font-mono text-mono-sm text-fg-1">{line.amount.currency}</span>
      ),
      width: 104,
    },
    {
      id: "amount",
      header: t("schedules.lines.column.amount"),
      kind: "money",
      value: (line) => line.amount.amount,
      currency: (line) => line.amount.currency,
      render: (line) => (
        <ExplainTrigger
          tabIndex={-1}
          figureRef={figure(line)}
          label={label(line)}
          valueText={moneyText(line.amount.amount, line.amount.currency)}
        >
          <Money value={line.amount.amount} currency={line.amount.currency} variant="cell" />
        </ExplainTrigger>
      ),
      width: 168,
    },
    {
      id: "cumulative",
      header: t("schedules.lines.column.cumulative"),
      kind: "money",
      value: (line) => line.cumulative_amount.amount,
      currency: (line) => line.cumulative_amount.currency,
      width: 168,
    },
    {
      id: "quantity",
      header: t("schedules.lines.column.quantity"),
      kind: "number",
      numberKind: "quantity",
      value: (line) => line.quantity,
      width: 120,
    },
  ];
}

function ScheduleLinesGrid({ query, periodText, onGoToContracts }: ScheduleLinesGridProps) {
  const [total, setTotal] = useState<number | undefined>(undefined);
  const columns = useMemo(() => lineColumns(query.book), [query.book]);
  const source: GridSource<ScheduleLine> = {
    queryKey: scheduleRangeKey(query),
    fetchPage: async (cursor, sort) => {
      const page = await fetchScheduleRangePage(query, cursor, sort);
      await ensureCurrencyCodes(page.items.map((line) => line.amount.currency));
      return page;
    },
  };
  return (
    <div className="flex min-h-120 flex-col">
      <DataGrid<ScheduleLine>
        name="lines"
        title={t("schedules.lines.title")}
        errorTitle={t("schedules.lines.loadError")}
        countLabel={(count, formatted) => t("schedules.lines.count", { count, formatted })}
        columns={columns}
        source={source}
        rowKey={(line) => line.id}
        rowLabel={(line) =>
          line.obligation_key === null
            ? line.period.name
            : `${line.obligation_key} ${line.period.name}`
        }
        testIdPrefix="SF-04"
        onTotalChange={(next) => setTotal(next?.count)}
        footer={total !== undefined}
        emptyState={
          <EmptyState
            title={t("schedules.empty.title", { period: periodText })}
            description={t("schedules.empty.description")}
            headingLevel={3}
            action={{ label: t("schedules.empty.action"), onAction: onGoToContracts }}
          />
        }
        noResults={<EmptyState title={t("schedules.noResults")} description="" headingLevel={3} />}
      />
    </div>
  );
}
