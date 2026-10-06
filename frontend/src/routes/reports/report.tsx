// SF-08:report Report view (SCREENS_B §5.2; §0.5 RV-01 to RV-14; §0.3 SB-R-07, SB-R-09; §5.6 RPT-R-01 to
// RPT-R-09; SCREENS RT-32, SCR-URL-06, SCR-URL-12, SCR-URL-16, SCR-URL-17, SCR-ST-07, SCR-ST-10,
// SCR-ST-12; BUILD_SPEC RPS-6; D-87 L6-3-Q-20, L6-3-Q-26). Opening a report with a parameter set creates a
// JSON report run and renders its rows; a URL with `run` renders that stored run and creates none. A
// locked context period defaults to the lock snapshot. The header carries "IPE documentation", "Run
// details" and "Export"; below the `h1` sit the description, the parameters toolbar, the run stamp, the
// source banners, the tie-out strip, the chart panel and one grid per section. Report figures drill
// through SB-R-07 into the docked Explain panel.
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { Navigate, useLocation, useNavigate, useParams } from "react-router";

import { contextSearch } from "../../app/shell/IconRail";
import {
  ExplainPanel,
  type Explanation,
  ExplainProvider,
} from "../../components/explain/ExplainPanel";
import type { FigureRef } from "../../components/explain/ExplainTrigger";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { JobProgress } from "../../components/feedback/JobProgress";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { RecordHeader } from "../../components/record/RecordHeader";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { Tooltip } from "../../components/ui/Tooltip";
import { type Access, useAccess } from "../../lib/access";
import { ApiProblem } from "../../lib/api/problems";
import { fetchExplanation } from "../../lib/api/queries/explain";
import { useMe } from "../../lib/api/queries/me";
import {
  fetchReportDefinition,
  fetchReportRun,
  REPORT_EXPORT_PERMISSION,
  type ReportDefinition,
  reportDefinitionKey,
  type ReportRun,
  reportRunKey,
} from "../../lib/api/queries/reports";
import {
  fetchPeriods,
  periodLabel,
  periodsKey,
  STRUCTURE_READ_PERMISSION,
} from "../../lib/api/queries/tenant";
import { formatDate, formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { withParams } from "../../lib/url/params";
import { AsLockedBanner, LOCKED_STATES } from "./viewer/AsLockedBanner";
import { CellContributors, type CellRequest } from "./viewer/CellContributors";
import { ExportMenu } from "./viewer/ExportMenu";
import { ParametersToolbar, toolbarKeys } from "./viewer/ParametersToolbar";
import { ReportChart } from "./viewer/ReportChart";
import { type DrillRequest, figureLabel, ReportGrid } from "./viewer/ReportGrid";
import { RunDetailsDrawer, valueText } from "./viewer/RunDetailsDrawer";
import { runAsOf, RunStamp } from "./viewer/RunStamp";
import {
  bandBoundaries,
  bucketLabel,
  contextPeriod,
  datasetLock,
  hasLockDataset,
  isAsLocked,
  LEGACY_JE_SUMMARY,
  legacyJeSummarySearch,
  namesAnotherLock,
  parameterDefaults,
  registerEmptyCopy,
  type ReportContext,
  reportColumns,
  rpoBands,
  runParameters,
  sectionEmptyCopy,
  sectionsOf,
  totalsRows,
  validateParameters,
} from "./viewer/specs";
import { TieOutStrip } from "./viewer/TieOutStrip";
import { JobReference } from "./viewer/JobReference";
import { useReportRun } from "./viewer/useReportRun";
import { useViewContext } from "./viewer/useViewContext";

/** SCREENS SCR-URL-01 to SCR-URL-03: the context a reports link keeps. */
const CONTEXT = ["entity", "period", "book"] as const;
const PARAMETER_PREFIX = "p.";
const RUN_DETAILS = "run-details";
const IPE = "ipe";
const PARAMETERS_FIELD = "parameters.";

export function ReportView() {
  const { reportCode = "" } = useParams();
  const location = useLocation();
  // Report figures open Explain (DS-CMP-15), so the page hosts the provider and docks the panel.
  const loadExplanation = useCallback(
    async (figure: FigureRef) => (await fetchExplanation(figure)) as Explanation,
    [],
  );
  // SCREENS_B RPT-13: `/reports/legacy_je_summary` redirects to SF-06:entries with the same parameters.
  if (reportCode === LEGACY_JE_SUMMARY) {
    return <Navigate replace to={`/journals/entries${legacyJeSummarySearch(location.search)}`} />;
  }
  return (
    <ExplainProvider load={loadExplanation}>
      <ReportScreen />
    </ExplainProvider>
  );
}

function ReportScreen() {
  const { reportCode = "" } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const me = useMe();
  const access = useAccess();
  // §0.5 "The context of a view" (rev 1.92): the view is mounted once the address holds its context.
  const viewContext = useViewContext();
  const definition = useQuery({
    queryKey: reportDefinitionKey(reportCode),
    queryFn: () => fetchReportDefinition(reportCode),
    retry: (count, error) => !(error instanceof ApiProblem && error.status === 404) && count < 1,
  });

  if (me.isError) {
    return <Banner tone="negative" title={me.error.message} />;
  }
  if (definition.error !== null) {
    if (definition.error instanceof ApiProblem && definition.error.status === 404) {
      return (
        <div data-testid="SF-08-page" className="px-[var(--gutter)]">
          <EmptyState
            title={t("reports.report.notFound.title")}
            description={t("reports.report.notFound.description")}
            headingLevel={2}
            action={{
              label: t("reports.report.notFound.action"),
              onAction: () => void navigate(`/reports${contextSearch(location.search, CONTEXT)}`),
            }}
          />
        </div>
      );
    }
    return (
      <div className="px-[var(--gutter)] py-[var(--panel-pad)]">
        <Banner
          tone="negative"
          title={t("reports.report.loadError")}
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
      <div className="px-[var(--gutter)] py-[var(--panel-pad)]">
        <Banner
          tone="negative"
          title={t("reports.report.loadError")}
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
    return <Skeleton region={t("reports.report.region")} shape="rows" count={8} />;
  }
  return <ReportBody key={definition.data.code} definition={definition.data} access={access} />;
}

interface SectionNote {
  readonly section: number;
  readonly note: string;
  readonly registryKey: string | null;
}

/** RV-12 notes and section footnotes of a run's control totals (`rpo` `notes`). */
function notesOf(run: ReportRun | undefined): readonly SectionNote[] {
  const notes = run?.control_totals?.notes;
  if (!Array.isArray(notes)) {
    return [];
  }
  return notes.flatMap((item: unknown) => {
    if (typeof item !== "object" || item === null) {
      return [];
    }
    const { section, note, registry_key: registryKey } = item as Readonly<Record<string, unknown>>;
    return typeof section === "number" && typeof note === "string"
      ? [{ section, note, registryKey: typeof registryKey === "string" ? registryKey : null }]
      : [];
  });
}

function emptyCopy(definition: ReportDefinition, run: ReportRun, context: ReportContext) {
  const parameter = (key: string) => {
    const value = run.parameters[key];
    return typeof value === "string" ? value : null;
  };
  switch (definition.code) {
    case "revenue_waterfall": {
      const from = parameter("from_period_key");
      const to = parameter("to_period_key");
      return {
        title: t("reports.empty.revenue_waterfall.title", {
          from: from === null ? "" : bucketLabel(from, context.periods),
          to: to === null ? "" : bucketLabel(to, context.periods),
        }),
        description: t("reports.empty.revenue_waterfall.description"),
      };
    }
    case "rpo": {
      const asOf = runAsOf(run);
      return {
        title: t("reports.empty.rpo.title", { date: asOf === null ? "" : formatDate(asOf) }),
        description: t("reports.empty.rpo.description"),
      };
    }
    case "legacy_contract_history_export": {
      const from = parameter("from_date");
      const to = parameter("to_date");
      return {
        title: t("reports.empty.legacy_contract_history_export.title", {
          from: from === null ? "" : formatDate(from),
          to: to === null ? "" : formatDate(to),
        }),
        description: t("reports.empty.legacy_contract_history_export.description"),
      };
    }
    default:
      // The registers and analysis reports state their own copy (SCREENS_B §5.6 "Empty copy").
      return (
        registerEmptyCopy(definition.code, run, context) ?? {
          title: t("reports.empty.generic.title"),
          description: t("reports.empty.generic.description"),
        }
      );
  }
}

interface ReportBodyProps {
  readonly definition: ReportDefinition;
  readonly access: Access;
}

function ReportBody({ definition, access }: ReportBodyProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const toast = useToast();
  const search = location.search;
  const params = new URLSearchParams(search);
  const entity = params.get("entity");
  const period = params.get("period");
  const book = params.get("book");
  const snapshot = params.get("snapshot");
  const knownAt = params.get("known_at");
  const currencyView = params.get("currency_view");
  const runId = params.get("run");
  const drawer = params.get("drawer");
  const pValues: Record<string, string> = {};
  for (const [name, value] of params) {
    if (name.startsWith(PARAMETER_PREFIX)) {
      pValues[name.slice(PARAMETER_PREFIX.length)] = value;
    }
  }
  const canExport = access.holdsAnywhere(REPORT_EXPORT_PERMISSION);

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
  const context: ReportContext = {
    entity,
    book,
    periodKey: period,
    periods: periods.data ?? [],
    snapshot,
    knownAt,
    currencyView,
  };
  const current = contextPeriod(context);
  // The record that locked the period, and the lock whose datasets stand for it (API-S-Period
  // `dataset_lock`): one record while the period is `closed`; on a `permanently_locked` period the
  // LOCK the permanent lock sealed.
  const lock = current?.current_lock ?? null;
  const standingLock = datasetLock(context);
  const locked = current !== null && LOCKED_STATES.has(current.state) && lock !== null;
  const contextKey = [entity, book, period].join("|");
  const [currentChosen, setCurrentChosen] = useState<string | null>(null);
  const calendarReady =
    !periodsEnabled || period === null || periods.data !== undefined || periods.isError;

  // RV-04 rev 1.98: a locked context period defaults to its lock snapshot until the user shows current
  // figures — for a report the lock freezes. Any other report runs current figures there and says so:
  // a lock sent to a report without a dataset is refused by name, and a `snapshot` beside a report
  // that takes no lock is sent nowhere, so the page must not call its figures locked.
  // D-88 L7-3-Q-2: a report run, an export and a rerun read the source `period_lock_id` names and change
  // no business state, so they are not SCR-ST-10 command controls and stay while `snapshot` is shown.
  // The sentences of RV-04 name the context period and its lock's time: they are said of that lock
  // and of no other. An address that names another lock — the link of a stored as-locked run of a
  // report without `period_key`, once the context is filled around it — is kept as written, and
  // the run stamp alone states the source of what is shown.
  // Rev 1.101: that lock is `dataset_lock`, the one whose datasets stand. On a `permanently_locked`
  // period it is the LOCK the permanent lock sealed, so a frozen report opens as locked there too,
  // on the time its figures were frozen at; where a locked period has no such lock nothing defaults
  // to one and nothing offers one, and the banner is the current sentence.
  const frozen = hasLockDataset(definition.code);
  const standing = standingLock !== null;
  const asLocked = isAsLocked(definition, context);
  const anotherLock = namesAnotherLock(definition, context);
  const needsSnapshot =
    frozen &&
    standing &&
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

  const defaults = parameterDefaults(definition, context);
  const urlValues: Record<string, string> = {
    ...defaults,
    ...pValues,
    ...(currencyView === null ? {} : { currency_view: currencyView }),
  };
  const [draft, setDraft] = useState<Readonly<Record<string, string>> | null>(null);
  const values = draft ?? urlValues;
  const parameters = runParameters(definition, context, pValues);
  const [clientErrors, setClientErrors] = useState<Readonly<Record<string, string>>>({});
  // RV-01: one run per parameter set; a context change drops the stored run.
  const { problem, run, rows, columns, pendingJob, computing, createdJobId, restart } =
    useReportRun({
      definition,
      parameters,
      contextSignature: [entity, book, period, snapshot, knownAt, currencyView].join("|"),
      ready: calendarReady && !needsSnapshot,
      runId,
      replace,
    });
  const succeeded = run.data?.status === "SUCCEEDED";

  const runReport = () => {
    if (computing) {
      toast.show({
        tone: "neutral",
        message: t("reports.report.alreadyRunning", { name: definition.name }),
      });
      return;
    }
    const chosen: Record<string, string> = {};
    for (const key of toolbarKeys(definition)) {
      const value = values[key];
      if (key !== "currency_view" && key !== "time_bands" && value !== undefined) {
        chosen[key] = value;
      }
    }
    const view = values.currency_view ?? currencyView;
    const next = runParameters(definition, { ...context, currencyView: view }, chosen);
    const errors = validateParameters(context, next);
    setClientErrors(errors);
    if (Object.keys(errors).length > 0) {
      return;
    }
    const changes: Record<string, string | null> = { run: null };
    for (const key of toolbarKeys(definition)) {
      if (key === "time_bands") {
        continue;
      }
      const value = values[key];
      if (key === "currency_view") {
        changes.currency_view =
          value === undefined || value === "" ? null : encodeURIComponent(value);
        continue;
      }
      changes[`${PARAMETER_PREFIX}${key}`] =
        value === undefined || value === "" || value === defaults[key]
          ? null
          : encodeURIComponent(value);
    }
    setDraft(null);
    restart();
    replace(changes);
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
  const onExportDetails = useCallback((id: string) => openDetails(id), [openDetails]);

  // L6-3-Q-20: a refused parameter shows on its field; other findings in the problem banner. The problem is
  // the refused creation's, bound to this parameter set and source (RV-01 rev 1.6; D-90e L9-PLT-Q-6).
  const fieldKeys = new Set(toolbarKeys(definition));
  const serverErrors: Record<string, string> = {};
  const otherMessages: string[] = [];
  for (const error of problem?.errors ?? []) {
    const key = error.field?.startsWith(PARAMETERS_FIELD)
      ? error.field.slice(PARAMETERS_FIELD.length)
      : null;
    if (key !== null && fieldKeys.has(key)) {
      serverErrors[key] = error.message;
    } else {
      otherMessages.push(error.message);
    }
  }
  const errors = { ...serverErrors, ...clientErrors };

  const data = run.data;
  const bands = rpoBands(data?.control_totals ?? null);
  const timeBands =
    bands.length === 0
      ? null
      : t("reports.parameters.timeBandsValue", {
          bands: bandBoundaries(bands)
            .map((item) => formatNumber(item, { kind: "count" }))
            .join(", "),
        });
  const periodText = current === null ? (period ?? "") : periodLabel(current.period);
  const runningLabel = t("reports.report.running", { name: definition.name });
  const notes = notesOf(data);

  let body = null;
  if (computing && data?.status !== "FAILED") {
    body =
      pendingJob !== null ? (
        <JobProgress label={runningLabel} job={pendingJob} unit={t("reports.export.unit")} />
      ) : (
        <Skeleton region={runningLabel} shape="rows" count={6} />
      );
  } else if (data?.status === "FAILED") {
    body = (
      <Banner
        tone="negative"
        title={t("common.job.failed", { label: runningLabel })}
        actions={
          <Button variant="link" onClick={runReport}>
            {t("reports.report.retry")}
          </Button>
        }
      >
        {data.problem === null ? null : <p>{data.problem.title}</p>}
        {/* SCR-ST-12 "Reference <job id prefix>": the run's own job, else the creation this view started (RV-14 rev 1.7). */}
        <JobReference run={data} createdJobId={createdJobId} />
      </Banner>
    );
  } else if (run.isError) {
    body = (
      <Banner
        tone="negative"
        title={t("reports.report.loadError")}
        actions={
          <Button variant="link" onClick={() => void run.refetch()}>
            {t("reports.report.retry")}
          </Button>
        }
      />
    );
  } else if (succeeded && data !== undefined) {
    if (rows.isError) {
      body = (
        <Banner
          tone="negative"
          title={t("reports.report.dataLoadError")}
          actions={
            <Button variant="link" onClick={() => void rows.refetch()}>
              {t("reports.report.retry")}
            </Button>
          }
        />
      );
    } else if (rows.data === undefined) {
      body = <Skeleton region={definition.name} shape="rows" count={8} />;
    } else if (rows.data.length === 0) {
      const copy = emptyCopy(definition, data, context);
      body = <EmptyState title={copy.title} description={copy.description} headingLevel={2} />;
    } else {
      const sections = sectionsOf(definition, rows.data);
      const first = sections[0];
      body = (
        <div className="flex flex-col gap-6">
          {/* An as-locked run draws no chart: its rows are the frozen dataset, every cell text (RV-04
              rev 1.17), and `reportChart` draws from a totals row of money alone. */}
          {first === undefined ? null : (
            <ReportChart
              definition={definition}
              run={data}
              section={first}
              periods={context.periods}
            />
          )}
          {sections.map((section) => {
            const sectionNotes = notes.filter((item) => item.section === section.number);
            return (
              <section key={section.number} className="flex flex-col gap-2">
                <ReportGrid
                  runId={data.id}
                  section={section}
                  columns={reportColumns({
                    definition,
                    section,
                    periods: context.periods,
                    bands,
                    columns,
                  })}
                  totals={totalsRows(section)}
                  onDrill={drill}
                  emptyState={
                    <p className="p-4 text-body-sm text-fg-2">
                      {sectionEmptyCopy(definition.code, section.number, data, context) ??
                        t("reports.report.section.empty")}
                    </p>
                  }
                />
                {sectionNotes.map((item) =>
                  item.registryKey === null ? (
                    <p key={item.note} className="text-body-sm text-fg-2">
                      {item.note}
                    </p>
                  ) : (
                    <Tooltip
                      key={item.note}
                      content={t("reports.report.registryKey", { key: item.registryKey })}
                    >
                      {(trigger) => (
                        <p
                          {...trigger}
                          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- DS-CMP-27: a tooltip trigger is focusable
                          tabIndex={0}
                          className="text-body-sm text-fg-2"
                        >
                          {item.note}
                        </p>
                      )}
                    </Tooltip>
                  ),
                )}
              </section>
            );
          })}
          <p className="text-caption text-fg-3">
            {t("reports.report.footer", {
              count: data.row_count ?? 0,
              rows: formatNumber(data.row_count ?? 0, { kind: "count" }),
            })}
          </p>
        </div>
      );
    }
  }

  const headerActions = (
    <>
      {definition.ipe_logic === null || definition.ipe_logic === undefined ? null : (
        <Button variant="secondary" onClick={() => replace({ drawer: IPE })}>
          {t("reports.report.ipe")}
        </Button>
      )}
      {data === undefined ? null : (
        <Button variant="secondary" onClick={() => openDetails(null)}>
          {t("reports.report.runDetails")}
        </Button>
      )}
      {canExport && definition.output_formats.length > 0 ? (
        <ExportMenu
          definition={definition}
          parameters={data?.parameters ?? parameters}
          onDetails={onExportDetails}
        />
      ) : null}
    </>
  );

  return (
    <div className="flex min-h-full gap-4">
      <div data-testid="SF-08-page" className="flex min-w-0 flex-1 flex-col gap-4">
        <RecordHeader
          title={definition.name}
          breadcrumb={[
            {
              label: t("reports.report.breadcrumb"),
              to: `/reports${contextSearch(search, CONTEXT)}`,
            },
          ]}
          actions={headerActions}
          banner={
            <div className="flex flex-col gap-3">
              <p className="max-w-160 text-body-sm text-fg-2">{definition.description}</p>
              <ParametersToolbar
                key={contextKey}
                definition={definition}
                context={context}
                values={values}
                errors={errors}
                timeBands={timeBands}
                unavailable={asLocked ? t("reports.asLocked.noParameters") : undefined}
                onChange={(key, value) => setDraft({ ...values, [key]: value })}
                onRun={runReport}
              />
              {data === undefined ? null : (
                <RunStamp
                  run={data}
                  lockCreatedAt={
                    standingLock !== null && data.period_lock_id === standingLock.id
                      ? standingLock.created_at
                      : null
                  }
                />
              )}
              {locked && lock !== null && !anotherLock ? (
                <AsLockedBanner
                  periodLabel={periodText}
                  // The time the period's figures were frozen at; where no dataset stands, the
                  // time of the record that locked it.
                  lockedAt={(standingLock ?? lock).created_at}
                  asLocked={asLocked}
                  frozen={frozen}
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
              {data === undefined ? null : <TieOutStrip results={data.tie_out_results} />}
            </div>
          }
        />
        <div className="px-[var(--gutter)] pb-[var(--panel-pad)]">{body}</div>
      </div>
      {cellRequest === null ? null : (
        <CellContributors
          key={`${cellRequest.rowKey}:${cellRequest.columnKey}`}
          request={cellRequest}
          onClose={closeCell}
        />
      )}
      <ExplainPanel />
      {drawer === RUN_DETAILS && details.data !== undefined ? (
        <RunDetailsDrawer
          run={details.data}
          onClose={() => {
            setDetailsRunId(null);
            replace({ drawer: null });
          }}
        />
      ) : null}
      {drawer === IPE && definition.ipe_logic !== null && definition.ipe_logic !== undefined ? (
        <div data-testid="SF-08-drawer-ipe" className="flex h-full">
          <Drawer
            open
            variant="docked"
            title={t("reports.report.ipe")}
            onClose={() => replace({ drawer: null })}
          >
            <IpeDocumentation definition={definition} />
          </Drawer>
        </div>
      ) : null}
    </div>
  );
}

/** §5.2 "IPE documentation": the definition, its parameters schema and `ipe_logic` (REQ-RPT-027). */
function IpeDocumentation({ definition }: { readonly definition: ReportDefinition }) {
  const logic = definition.ipe_logic;
  const download = () => {
    const blob = new Blob([JSON.stringify(definition, null, 2)], { type: "application/json" });
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = `${definition.code}-v${String(definition.version)}.json`;
    anchor.click();
    URL.revokeObjectURL(href);
  };
  const entries: readonly (readonly [string, string])[] = [
    ["code", definition.code],
    ["version", String(definition.version)],
    ["kind", definition.kind],
    ["description", definition.description],
    ["parameters_schema", valueText(definition.parameters_schema.properties)],
    ["source_tables", valueText(logic?.source_tables)],
    ["joins", valueText(logic?.joins)],
    ["filters", valueText(logic?.filters)],
    ["parameters", valueText(logic?.parameters)],
    ["tie_outs", valueText(definition.tie_outs)],
  ];
  return (
    <div className="flex flex-col gap-3">
      <dl className="flex flex-col gap-2">
        {entries.map(([name, value]) => (
          <div key={name} className="flex flex-col gap-0.5">
            <dt className="font-mono text-mono-sm text-fg-3">{name}</dt>
            <dd className="break-words text-body-sm text-fg-1">{value}</dd>
          </div>
        ))}
      </dl>
      <Button variant="secondary" onClick={download}>
        {t("reports.report.downloadDefinition")}
      </Button>
    </div>
  );
}
