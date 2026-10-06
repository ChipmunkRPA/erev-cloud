// SF-08:dashboard Dashboards (SCREENS_B §5.5; SCREENS RT-107, SCR-URL-01 to SCR-URL-03, SCR-URL-26,
// SCR-PERM-01, SCR-PERM-02, SCR-ST-07, SCR-ST-12; DESIGN_SYSTEM DS-CMP-14, DS-CH-01 to DS-CH-03, DS-CH-06,
// DS-FMT-02; 04 API-R-41, API-R-44, API-R-17, API-R-18; BUILD_SPEC RPS-19). The revenue dashboard composes
// four report runs into chart panels — revenue by period (RPT-01), the contract liability rollforward
// (RPT-03), remaining performance obligations by time band (RPT-06) and revenue by category (RPT-08) —
// beside the open anomaly flags. Each panel is one JSON run (RV-01) whose id the address keeps as
// `run.<panel>`, so a shared link shows the same four runs; "Refresh" makes four new ones, and so does a
// context that changes.
//
// No report converts an amount in 1.0, and a run that names its period by key reads each entity at that
// key on its own calendar (§5.5 rev 1.82). The panels are therefore drawn for one entity, or for the
// entities in scope where they keep one calendar and one functional currency; otherwise the page makes no
// run and says why. The close dashboard (`close`) follows in its own head.
import { useQuery } from "@tanstack/react-query";
import { type ReactElement, type ReactNode, useCallback, useEffect, useId, useState } from "react";
import { data, Link, type LoaderFunctionArgs, useLocation, useNavigate } from "react-router";

import {
  type ContextChoice,
  contextOwner,
  readStoredContext,
  resolveEntityBook,
  resolvePeriod,
} from "../../app/shell/ContextPill";
import { useShellSession } from "../../app/shell/SandboxIndicator";
import { CategoryBars, type Category } from "../../components/charts/CategoryBars";
import { ChartPanel } from "../../components/charts/ChartPanel";
import { type BridgeCategory, RollforwardBridge } from "../../components/charts/RollforwardBridge";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { refusalLines } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { ArrowsClockwise } from "../../components/icons/registry";
import { RecordHeader } from "../../components/record/RecordHeader";
import { Button } from "../../components/ui/Button";
import { chipFor, OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { type Access, useAccess } from "../../lib/access";
import { fetchListPage } from "../../lib/api/lists";
import { ApiProblem } from "../../lib/api/problems";
import {
  DEFAULT_STATUSES,
  EXCEPTION_QUEUE_ROUTE,
  EXCEPTION_READ_PERMISSION,
  type ExceptionItem,
  exceptionRoute,
  EXCEPTIONS_PATH,
} from "../../lib/api/queries/exceptions";
import { type Me, useMe } from "../../lib/api/queries/me";
import {
  fetchReportDefinitions,
  REPORT_ROUTE,
  REPORT_RUN_PERMISSION,
  type ReportDefinition,
  reportDefinitionsKey,
  type ReportRow,
  type ReportRun,
} from "../../lib/api/queries/reports";
import {
  booksKey,
  entitiesKey,
  fetchActiveEntities,
  fetchBooks,
  fetchPeriods,
  periodLabel,
  periodsKey,
  STRUCTURE_READ_PERMISSION,
} from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import { formatNumber, formatPeriod, formatTimestamp } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { useLiveSearch } from "../../lib/url/live-search";
import { withParams } from "../../lib/url/params";
import { useBuiltPaths } from "../settings/index";
import { DASHBOARDS } from "./dashboards";
import { JobReference } from "./viewer/JobReference";
import { reportChart } from "./viewer/ReportChart";
import { bookLabel } from "./viewer/RunStamp";
import {
  isMoney,
  type ReportContext,
  type ReportSection,
  rowTestKey,
  runParameters,
  sectionsOf,
} from "./viewer/specs";
import { useReportRun } from "./viewer/useReportRun";
import { ALL_ENTITIES, ENTITIES_PARAM, useViewContext } from "./viewer/useViewContext";

/** RT-107: a code this build has no dashboard for is X:not-found (SCR-ST-07). */
export function dashboardLoader({ params }: LoaderFunctionArgs): null {
  if (!DASHBOARDS.some((dashboard) => dashboard.code === params.dashboardCode)) {
    throw data(null, { status: 404 });
  }
  return null;
}

const SCHEDULES_ROUTE = "/schedules";
const EXCEPTION_ITEM_ROUTE = `${EXCEPTION_QUEUE_ROUTE}/:exceptionId`;
/** §5.5 rev 1.82: the view the four runs are asked in; no report converts an amount in 1.0. */
const CURRENCY_VIEW = "functional";
/** §5.5: the flags panel lists at most eight items beside their count. */
const FLAGS_LIMIT = 8;
const NONZERO = /[1-9]/;
const PANEL = "flex min-w-0 flex-col gap-3 rounded-md border border-hairline bg-surface p-4";

type PanelName = "revenue" | "rollforward" | "rpo" | "disaggregation";

/** The report of each panel (§5.5 "Regions and components"). */
const PANEL_REPORT: Readonly<Record<PanelName, string>> = {
  revenue: "revenue_waterfall",
  rollforward: "contract_balance_rollforward",
  rpo: "rpo",
  disaggregation: "disaggregation",
};

/**
 * The parameters a panel sends beside the context's (§5.5 rev 1.82): the time bands by entity, as the
 * wireframe draws them, and the categories without the timing of transfer. "Open report" carries them
 * as `p.<key>`, so the report's toolbar shows what the run was asked.
 */
const PANEL_VALUES: Readonly<Record<PanelName, Readonly<Record<string, string>>>> = {
  revenue: {},
  rollforward: {},
  rpo: { row_dimension: "ENTITY" },
  disaggregation: { dimension_code: "revenue_category", include_timing: "false" },
};

function panelTestId(panel: PanelName): string {
  return `SF-08-chart-dashboard-${panel}`;
}

/** The runs the address names, by panel (SCR-URL-26 `run.<panel>`). */
function runsIn(search: string): Readonly<Record<PanelName, string | null>> {
  const params = new URLSearchParams(search);
  return {
    revenue: params.get("run.revenue"),
    rollforward: params.get("run.rollforward"),
    rpo: params.get("run.rpo"),
    disaggregation: params.get("run.disaggregation"),
  };
}

/** The context the page has shown, and the runs it has left: another context's, refreshed or retried. */
interface Shown {
  readonly context: string | null;
  readonly left: ReadonlySet<string>;
}

const NO_RUNS: ReadonlySet<string> = new Set();

function withRuns(left: ReadonlySet<string>, ids: readonly (string | null)[]): ReadonlySet<string> {
  const more = ids.filter((id): id is string => id !== null && !left.has(id));
  return more.length === 0 ? left : new Set([...left, ...more]);
}

function unlessLeft(id: string | null, left: ReadonlySet<string>): string | null {
  return id !== null && left.has(id) ? null : id;
}

export function DashboardPage() {
  const me = useMe();
  const access = useAccess();
  // §0.5 "The context of a view" (rev 1.92): the page is mounted once the address holds its context —
  // the entity it names, the pill's where it names none, or `entities=all`.
  const viewContext = useViewContext();
  let body;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={t("reports.dashboard.revenue.name")} shape="rows" count={8} />;
  } else if (!access.holdsAnywhere(REPORT_RUN_PERMISSION)) {
    // SCR-PERM-01 (RT-107: `report.run`).
    body = (
      <EmptyState
        title={t("settings.access.title", { area: t("reports.dashboard.access.area") })}
        description={t("settings.access.description", {
          permission: t("reports.dashboard.access.permission"),
        })}
      />
    );
  } else if (viewContext.failure !== null) {
    body = (
      <div className="px-[var(--gutter)] py-[var(--panel-pad)]">
        <RetryBanner
          title={t("reports.dashboard.loadError")}
          problem={viewContext.failure}
          onRetry={viewContext.retry}
        />
      </div>
    );
  } else if (!viewContext.settled) {
    body = <Skeleton region={t("reports.dashboard.revenue.name")} shape="rows" count={8} />;
  } else {
    // One dashboard in this build (the loader admits no other code).
    body = <RevenueDashboard me={me.data} access={access} />;
  }
  return (
    <div data-testid="SF-08-page" className="flex min-w-0 flex-col">
      {body}
    </div>
  );
}

/**
 * Writes search parameters with `history.replace`, each write starting from the search the router
 * holds when it is made (`useLiveSearch`, docs/dev-guide.md DG-FE-03) and not from the search the page
 * last rendered. Four panels write their run close together, and a navigation is committed later
 * than it is asked for: a write takes up the one still on its way, so none replaces another; a write
 * made from an effect, in the render of a new address, is made on that address; and what the
 * reader's own navigation overtook does not come back with the next write.
 */
export function useSearchWriter() {
  const navigate = useNavigate();
  const liveSearch = useLiveSearch();
  return useCallback(
    (changes: Readonly<Record<string, string | null>>) => {
      void navigate({ search: withParams(liveSearch(), changes) }, { replace: true });
    },
    [liveSearch, navigate],
  );
}

function RetryBanner({
  title,
  problem,
  onRetry,
  headingLevel = 2,
}: {
  readonly title: string;
  readonly problem: unknown;
  readonly onRetry: () => void;
  readonly headingLevel?: 2 | 3;
}) {
  const detail = problem instanceof ApiProblem ? (problem.detail ?? problem.title) : null;
  return (
    <Banner
      tone="negative"
      title={title}
      headingLevel={headingLevel}
      actions={
        <Button variant="link" onClick={onRetry}>
          {t("reports.report.retry")}
        </Button>
      }
    >
      {detail === null ? null : <p>{detail}</p>}
      {problem instanceof ApiProblem && problem.requestId !== null ? (
        <p>{t("common.refusal.reference", { reference: problem.requestId })}</p>
      ) : null}
    </Banner>
  );
}

function safePeriod(key: string): string {
  try {
    return formatPeriod(key);
  } catch {
    return key;
  }
}

function RevenueDashboard({ me, access }: { readonly me: Me; readonly access: Access }) {
  const location = useLocation();
  const search = location.search;
  const session = useShellSession();
  const structure = access.holdsAnywhere(STRUCTURE_READ_PERMISSION);
  const entities = useQuery({
    queryKey: entitiesKey(),
    queryFn: fetchActiveEntities,
    enabled: structure,
  });
  const books = useQuery({ queryKey: booksKey(), queryFn: fetchBooks, enabled: structure });
  // The period and book are the context pill's (BR-UX-01): the URL, else the stored choice, else the
  // defaults. The entity is the URL's alone: the page is mounted on a settled address (`DashboardPage`),
  // which names the entity — its own or the pill's, written there — unless it says `entities=all` or
  // nothing could fill it; without an entity the page reads All entities (SCR-URL-01 rev 1.61).
  const params = new URLSearchParams(search);
  const url: ContextChoice = {
    entity: params.get("entity"),
    period: params.get("period"),
    book: params.get("book"),
  };
  const owner = contextOwner(me, session);
  const stored = owner === null ? null : readStoredContext(owner);
  const choices = stored === null ? [url] : [url, stored];
  const head =
    entities.data === undefined || books.data === undefined
      ? null
      : resolveEntityBook(entities.data, books.data, choices);
  const periodQuery = { entity: head?.entity.code ?? "", book: head?.book.code ?? "" };
  const periods = useQuery({
    queryKey: periodsKey(periodQuery),
    queryFn: () => fetchPeriods(periodQuery),
    enabled: head !== null,
  });
  const reference =
    head === null || periods.data === undefined ? null : resolvePeriod(periods.data, choices);

  const named = params.get("entity");
  const one = named === null ? null : (head?.entity.code ?? named);
  const book = head?.book.code ?? params.get("book");
  const periodKey = reference?.period.period_key ?? params.get("period");
  const periodText =
    reference !== null
      ? periodLabel(reference.period)
      : periodKey === null
        ? null
        : safePeriod(periodKey);
  const name = t("reports.dashboard.revenue.name");
  const title = [
    name,
    one ?? t("reports.chart.allEntities"),
    periodText,
    book === null ? null : bookLabel(book),
  ]
    .filter((part): part is string => part !== null)
    .join(" · ");
  // The context the page shows, for every link it makes (SCR-URL-01 to SCR-URL-03).
  const contextQuery = withParams("", {
    entity: one === null ? null : encodeURIComponent(one),
    period: periodKey === null ? null : encodeURIComponent(periodKey),
    book: book === null ? null : encodeURIComponent(book),
  });
  // The same for the links to the report views and to Schedules. Those screens take the pill's
  // context where an address names no entity (SCR-URL-01 rev 1.61), so a page of all entities says
  // so: without it "Open report" would open the pill's entity around a run of all entities.
  const viewQuery =
    one === null ? withParams(contextQuery, { [ENTITIES_PARAM]: ALL_ENTITIES }) : contextQuery;

  // §5.5 rev 1.82: a run without an entity reads the entities of the member's `report.run` scope
  // (04 API-R-41); those of them that keep the book give its figures, which make one chart where
  // they keep one calendar and one functional currency. The calendar is also the one the context
  // period was chosen on, the pill's entity's: a run reads its period by key, and on another
  // calendar that key is another month.
  const scope =
    one !== null || book === null
      ? []
      : (entities.data ?? []).filter(
          (entity) =>
            access.holds(REPORT_RUN_PERMISSION, entity) &&
            entity.books.some((kept) => kept.book_code === book && kept.is_enabled),
        );
  const calendars =
    new Set([
      ...scope.map((entity) => entity.calendar_id),
      ...(scope.length === 0 || head === null ? [] : [head.entity.calendar_id]),
    ]).size > 1;
  const currencies = new Set(scope.map((entity) => entity.functional_currency)).size > 1;
  const apart = calendars || currencies;

  // The runs in the address are those of the context they were made in (RV-01). Once the page has
  // shown one context, the runs it finds in the address under another are that other context's:
  // they are left — shown no more, and taken out of the address — and the panels start from none.
  // A panel cannot see this itself: an entity or a book that changes takes the calendar away for a
  // moment and the panels with it, and a panel mounted again would read the old runs as a link's.
  const resolved = head !== null && reference !== null && book !== null;
  const contextKey = resolved ? [one ?? "", book, periodKey].join("|") : null;
  const inAddress = runsIn(search);
  const [shown, setShown] = useState<Shown>({ context: null, left: NO_RUNS });
  if (contextKey !== null && contextKey !== shown.context) {
    // State from the render before, set before the panels render: none of them sees a left run.
    setShown({
      context: contextKey,
      left: shown.context === null ? shown.left : withRuns(shown.left, Object.values(inAddress)),
    });
  }
  const leave = useCallback((ids: readonly (string | null)[]) => {
    setShown((before) => ({ ...before, left: withRuns(before.left, ids) }));
  }, []);
  const write = useSearchWriter();
  const left = shown.left;
  useEffect(() => {
    const gone: Record<string, null> = {};
    for (const [panel, id] of Object.entries(runsIn(search))) {
      if (id !== null && left.has(id)) {
        gone[`run.${panel}`] = null;
      }
    }
    if (Object.keys(gone).length > 0) {
      write(gone);
    }
  }, [left, search, write]);
  const runs: Readonly<Record<PanelName, string | null>> = {
    revenue: unlessLeft(inAddress.revenue, left),
    rollforward: unlessLeft(inAddress.rollforward, left),
    rpo: unlessLeft(inAddress.rpo, left),
    disaggregation: unlessLeft(inAddress.disaggregation, left),
  };

  // "Refresh" (§5.5): new runs for every panel. The runs shown are left, and a panel that is mounted
  // again starts from no run.
  const [round, setRound] = useState(0);
  const refresh = () => {
    leave(Object.values(inAddress));
    setRound((count) => count + 1);
  };

  // SCR-PERM-02: the flags are the exception queue's read (`contract.read`, 04 API-R-44) and the
  // chart panels are report runs (`report.run`, 04 API-R-41), each asked for the context entity: a
  // run that names an entity outside the member's scope is refused. The chart panels also need the
  // calendar (`config.read`): without it no context is resolved and none renders.
  const readsFlags =
    one === null
      ? access.holdsAnywhere(EXCEPTION_READ_PERMISSION)
      : access.holds(EXCEPTION_READ_PERMISSION, { code: one });
  const runsReports = one === null || access.holds(REPORT_RUN_PERMISSION, { code: one });

  const failure = entities.error ?? books.error ?? periods.error;
  const settling =
    structure &&
    failure === null &&
    (entities.data === undefined ||
      books.data === undefined ||
      (head !== null && periods.data === undefined));
  const charts = runsReports && resolved;
  const drawn = charts && !apart;

  let body: ReactNode;
  if (failure !== null) {
    body = (
      <RetryBanner
        title={t("reports.dashboard.loadError")}
        problem={failure}
        onRetry={() => {
          void entities.refetch();
          void books.refetch();
          void periods.refetch();
        }}
      />
    );
  } else if (settling) {
    body = <Skeleton region={name} shape="rows" count={8} />;
  } else if (structure && reference === null) {
    // No entity keeps a book, or the one in context has no period.
    body = (
      <EmptyState
        title={t("reports.dashboard.noPeriod.title")}
        description={t("reports.dashboard.noPeriod.description")}
      />
    );
  } else if (!charts && !readsFlags) {
    // SCR-PERM-02: no panel may be read, so none renders; the page names what the charts lack —
    // the calendar, or a report run of this entity.
    body = (
      <EmptyState
        title={t("settings.access.title", { area: t("reports.dashboard.access.area") })}
        description={t("settings.access.description", {
          permission: t(
            structure
              ? "reports.dashboard.access.permission"
              : "settings.access.permission.configRead",
          ),
        })}
      />
    );
  } else {
    const context: ReportContext = {
      entity: one,
      book,
      periodKey,
      periods: periods.data ?? [],
      snapshot: null,
      knownAt: null,
      currencyView: CURRENCY_VIEW,
    };
    // Keyed: the panel keeps its place among the chart panels' states and is not mounted again when
    // the charts arrive.
    const flags = readsFlags ? (
      <FlagsPanel key="flags" entity={one} contextQuery={contextQuery} />
    ) : null;
    body = (
      <div className="grid min-w-0 grid-cols-1 items-start gap-[var(--stack-gap)] xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        {!charts ? (
          flags
        ) : apart ? (
          <>
            <div data-testid="SF-08-dashboard-banner-scope" className="min-w-0 xl:col-span-2">
              <Banner
                tone="info"
                announce="static"
                title={t(
                  calendars && currencies
                    ? "reports.dashboard.apart.both"
                    : calendars
                      ? "reports.dashboard.apart.calendars"
                      : "reports.dashboard.apart.currencies",
                )}
              />
            </div>
            {flags}
          </>
        ) : (
          <ChartPanels
            key={round}
            context={context}
            periodText={periodText ?? ""}
            runs={runs}
            viewQuery={viewQuery}
            write={write}
            onLeave={leave}
            flags={flags}
          />
        )}
      </div>
    );
  }

  return (
    <>
      <RecordHeader
        title={title}
        breadcrumb={[{ label: t("reports.report.breadcrumb"), to: `/reports${contextQuery}` }]}
        meta={
          drawn
            ? [
                {
                  label: t("reports.dashboard.currency"),
                  value: <OutlineChip label={t("reports.parameters.currencyView.functional")} />,
                },
              ]
            : []
        }
        actions={
          drawn ? (
            <Button variant="ghost" icon={ArrowsClockwise} onClick={refresh}>
              {t("reports.dashboard.refresh")}
            </Button>
          ) : null
        }
      />
      <div className="px-[var(--gutter)] py-[var(--panel-pad)]">{body}</div>
    </>
  );
}

interface ChartPanelsProps {
  readonly context: ReportContext;
  readonly periodText: string;
  /** The run each panel shows: the address's, unless the page has left it. */
  readonly runs: Readonly<Record<PanelName, string | null>>;
  /** The page's context as its links to the report views and to Schedules say it. */
  readonly viewQuery: string;
  readonly write: (changes: Readonly<Record<string, string | null>>) => void;
  readonly onLeave: (ids: readonly (string | null)[]) => void;
  /** The flags panel, which stands after the third chart panel (§5.5 wireframes). */
  readonly flags: ReactNode;
}

/** The four chart panels and the flags panel in §5.5 order; the last chart spans both columns. */
function ChartPanels({
  context,
  periodText,
  runs,
  viewQuery,
  write,
  onLeave,
  flags,
}: ChartPanelsProps) {
  const navigate = useNavigate();
  const built = useBuiltPaths();
  const definitions = useQuery({
    queryKey: reportDefinitionsKey(),
    queryFn: fetchReportDefinitions,
  });
  if (definitions.isError) {
    return (
      <>
        <div className="min-w-0 xl:col-span-2">
          <RetryBanner
            title={t("reports.dashboard.loadError")}
            problem={definitions.error}
            onRetry={() => void definitions.refetch()}
          />
        </div>
        {flags}
      </>
    );
  }
  if (definitions.data === undefined) {
    return (
      <>
        <div className="min-w-0 xl:col-span-2">
          <Skeleton region={t("reports.dashboard.revenue.name")} shape="rows" count={8} />
        </div>
        {flags}
      </>
    );
  }
  const byCode = new Map(definitions.data.map((definition) => [definition.code, definition]));
  // The address of a report in the page's context and view; a panel adds its parameters and its run.
  const reportSearch = withParams(viewQuery, { currency_view: CURRENCY_VIEW });
  const panel = (name: PanelName, title: string, chart: PanelRunProps["chart"], wide = false) => {
    const definition = byCode.get(PANEL_REPORT[name]);
    // A report the catalogue does not hold has no panel (SCR-PERM-02).
    return definition === undefined ? null : (
      <div key={name} className={wide ? "min-w-0 xl:col-span-2" : "min-w-0"}>
        <Panel
          panel={name}
          title={title}
          definition={definition}
          context={context}
          runId={runs[name]}
          write={write}
          onLeave={onLeave}
          reportSearch={reportSearch}
          reportBuilt={built.has(REPORT_ROUTE)}
          chart={chart}
        />
      </div>
    );
  };
  // §5.5: a mark of "Revenue by period" opens SF-04 on the mark's period, as the Home's chart does.
  const openSchedules = (key: string | null) => {
    const period = key ?? context.periodKey;
    void navigate(
      `${SCHEDULES_ROUTE}${withParams(viewQuery, {
        period: period === null ? null : encodeURIComponent(period),
      })}`,
    );
  };
  return (
    <>
      {panel("revenue", t("reports.chart.waterfall"), (ready) =>
        reportChart({
          definition: ready.definition,
          run: ready.run,
          section: ready.section,
          periods: context.periods,
          testId: panelTestId("revenue"),
          footnote: ready.footnote,
          onSelectPeriod: built.has(SCHEDULES_ROUTE) ? openSchedules : undefined,
        }),
      )}
      {panel("rollforward", t("reports.dashboard.rollforward"), rollforwardChart)}
      {panel("rpo", t("reports.chart.rpo"), (ready) =>
        reportChart({
          definition: ready.definition,
          run: ready.run,
          section: ready.section,
          periods: context.periods,
          testId: panelTestId("rpo"),
          footnote: ready.footnote,
          onSelectRow: ready.openReport,
        }),
      )}
      {flags}
      {panel(
        "disaggregation",
        t("reports.dashboard.category"),
        (ready) => categoryChart(ready, periodText),
        true,
      )}
    </>
  );
}

/** A panel's run with its rows: what a chart is drawn from. */
interface PanelReady {
  readonly definition: ReportDefinition;
  readonly run: ReportRun;
  readonly section: ReportSection;
  /** "Run <no> · <instant>" and "Open report" (§5.5). */
  readonly footnote: ReactNode;
  /** Opens the report with the panel's run; undefined where the report view is not built. */
  readonly openReport: (() => void) | undefined;
}

interface PanelRunProps {
  readonly panel: PanelName;
  /** The panel's name without its currency, for the states that have no figure yet. */
  readonly title: string;
  readonly definition: ReportDefinition;
  readonly context: ReportContext;
  readonly runId: string | null;
  readonly write: (changes: Readonly<Record<string, string | null>>) => void;
  /** The page shows these runs no more and takes them out of the address. */
  readonly onLeave: (ids: readonly (string | null)[]) => void;
  readonly reportSearch: string;
  readonly reportBuilt: boolean;
  /** The chart of a run with rows, or null where its figures cannot be drawn as one chart. */
  readonly chart: (ready: PanelReady) => ReactElement | null;
  /** "Retry": the panel is mounted again and asks for a new run. */
  readonly onRetry: () => void;
}

/**
 * A panel and its "Retry". A panel that is mounted again starts from no run: a refused creation
 * leaves nothing in the address whose change would start another, so the retry is a new mount, not a
 * new parameter.
 */
function Panel(props: Omit<PanelRunProps, "onRetry">) {
  const [attempt, setAttempt] = useState(0);
  return <PanelRun key={attempt} {...props} onRetry={() => setAttempt((count) => count + 1)} />;
}

function PanelFrame({
  panel,
  title,
  footnote,
  children,
}: {
  readonly panel: PanelName;
  readonly title: string;
  readonly footnote?: ReactNode;
  readonly children: ReactNode;
}) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} data-testid={panelTestId(panel)} className={PANEL}>
      <h2 id={headingId} className="text-title-sm text-fg-1">
        {title}
      </h2>
      {children}
      {footnote === undefined ? null : <p className="text-caption text-fg-3">{footnote}</p>}
    </section>
  );
}

/**
 * One chart panel: its run (RV-01, `run.<panel>`), the states before a chart exists, and the chart the
 * caller draws from the run's rows. A refused or failed run is the panel's own banner; the other panels
 * render (§5.5 "States").
 */
function PanelRun({
  panel,
  title,
  definition,
  context,
  runId,
  write,
  onLeave,
  reportSearch,
  reportBuilt,
  chart,
  onRetry,
}: PanelRunProps) {
  const navigate = useNavigate();
  const values = PANEL_VALUES[panel];
  // SCR-URL-26: the hook's `run` is this panel's `run.<panel>`.
  const replace = useCallback(
    (changes: Readonly<Record<string, string | null>>) => {
      const renamed: Record<string, string | null> = {};
      for (const [name, value] of Object.entries(changes)) {
        renamed[name === "run" ? `run.${panel}` : name] = value;
      }
      write(renamed);
    },
    [panel, write],
  );
  const { problem, run, rows, createdJobId } = useReportRun({
    definition,
    parameters: runParameters(definition, context, values),
    // One source as far as the view goes: the page leaves the runs of another context before a
    // panel renders in it (RevenueDashboard), so no panel ever holds a run whose source has changed.
    contextSignature: "",
    ready: true,
    runId,
    replace,
    announce: false,
  });
  const again = () => {
    // The run that failed is left; a refused creation left none.
    onLeave([runId]);
    onRetry();
  };
  const retry = (
    <Button variant="link" onClick={again}>
      {t("reports.report.retry")}
    </Button>
  );
  const found = run.data;

  const notRun = t("common.job.failed", {
    label: t("reports.report.running", { name: definition.name }),
  });
  if (problem !== null) {
    // A refused creation, said as SCREENS SCR-ST-13 says a refused command: the problem's detail and
    // every sentence of its findings, each once, and the request. The title is the panel's own — it
    // has no field, and the API's "Check the highlighted fields" would point at nothing — and "Retry"
    // stands in the banner, which the kit's RefusalBanner has no place for. A refusal that states
    // neither a detail nor a finding says its title under the panel's.
    const { detail, sentences } = refusalLines(problem);
    const said = [...(detail === null ? [] : [detail]), ...sentences];
    return (
      <PanelFrame panel={panel} title={title}>
        <Banner tone="negative" title={notRun} headingLevel={3} actions={retry}>
          {(said.length === 0 ? [problem.title] : said).map((sentence) => (
            <p key={sentence}>{sentence}</p>
          ))}
          {problem.requestId === null ? null : (
            <p>{t("common.refusal.reference", { reference: problem.requestId })}</p>
          )}
        </Banner>
      </PanelFrame>
    );
  }
  if (found?.status === "FAILED") {
    // SCR-ST-12: the run's job failed; nothing of it is drawn.
    return (
      <PanelFrame panel={panel} title={title}>
        <Banner tone="negative" title={notRun} headingLevel={3} actions={retry}>
          {found.problem === null ? null : <p>{found.problem.title}</p>}
          <JobReference run={found} createdJobId={createdJobId} />
        </Banner>
      </PanelFrame>
    );
  }
  if (run.isError || rows.isError) {
    const failed = run.isError ? run : rows;
    return (
      <PanelFrame panel={panel} title={title}>
        <RetryBanner
          title={t(run.isError ? "reports.report.loadError" : "reports.report.dataLoadError")}
          problem={failed.error}
          onRetry={() => void failed.refetch()}
          headingLevel={3}
        />
      </PanelFrame>
    );
  }
  if (found?.status !== "SUCCEEDED" || rows.data === undefined) {
    // No run yet, a run that is still computing (it is polled), or its rows on their way.
    return (
      <div data-testid={panelTestId(panel)}>
        <ChartPanel
          title={title}
          summary={title}
          state="loading"
          headingLevel={2}
          chart={null}
          table={null}
        />
      </div>
    );
  }

  const changes: Record<string, string | null> = { run: encodeURIComponent(found.id) };
  for (const [key, value] of Object.entries(values)) {
    changes[`p.${key}`] = encodeURIComponent(value);
  }
  const href = `/reports/${definition.code}${withParams(reportSearch, changes)}`;
  const footnote = (
    <span className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
      <span data-volatile="">
        {t("reports.dashboard.panel.run", {
          run: found.report_run_no,
          at: formatTimestamp(found.finished_at ?? found.started_at),
        })}
      </span>
      {reportBuilt ? (
        <Link
          to={href}
          aria-label={t("reports.dashboard.panel.openReportOf", { name: definition.name })}
          className="text-accent-fg hover:underline"
        >
          {t("reports.dashboard.panel.openReport")}
        </Link>
      ) : null}
    </span>
  );
  if (rows.data.length === 0) {
    const empty = t("reports.dashboard.panel.empty");
    return (
      <div data-testid={panelTestId(panel)}>
        <ChartPanel
          title={title}
          summary={empty}
          state="empty"
          emptyText={empty}
          footnote={footnote}
          headingLevel={2}
          chart={null}
          table={null}
        />
      </div>
    );
  }
  const section = sectionsOf(definition, rows.data)[0];
  const drawn =
    section === undefined
      ? null
      : chart({
          definition,
          run: found,
          section,
          footnote,
          openReport: reportBuilt ? () => void navigate(href) : undefined,
        });
  return (
    drawn ?? (
      <PanelFrame panel={panel} title={title} footnote={footnote}>
        <p className="text-body-sm text-fg-2">{t("reports.dashboard.panel.notDrawn")}</p>
      </PanelFrame>
    )
  );
}

const BRIDGE_TOTALS: ReadonlySet<string> = new Set(["OPENING", "CLOSING"]);

/**
 * The contract liability column of section 1 of RPT-03 as DS-CH-02 categories: "Opening balance" and
 * "Closing balance" as totals and the lines between as activity, in the API's order. A line without
 * movement draws nothing and is left out; the report lists all nine. Null where the section holds
 * several currencies.
 */
export function bridgeOf(
  rows: readonly ReportRow[],
): { readonly currency: string; readonly categories: readonly BridgeCategory[] } | null {
  const first = rows[0]?.contract_liability;
  if (!isMoney(first)) {
    return null;
  }
  const categories: BridgeCategory[] = [];
  for (const row of rows) {
    const amount = row.contract_liability;
    const code = row.line_code;
    const label = row.line_label;
    if (
      !isMoney(amount) ||
      amount.currency !== first.currency ||
      typeof code !== "string" ||
      typeof label !== "string"
    ) {
      return null;
    }
    const total = BRIDGE_TOTALS.has(code);
    if (total || NONZERO.test(amount.amount)) {
      categories.push({
        key: code,
        label,
        kind: total ? "TOTAL" : "ACTIVITY",
        amount: amount.amount,
      });
    }
  }
  return { currency: first.currency, categories };
}

/** DS-CH-02 of the run; its integrity is the run's tie-out `TO_ROLLFORWARD_BALANCES`. */
function rollforwardChart(ready: PanelReady): ReactElement | null {
  const lines = bridgeOf(ready.section.rows);
  if (lines === null) {
    return null;
  }
  const tieOut = ready.run.tie_out_results.find((item) => item.code === "TO_ROLLFORWARD_BALANCES");
  const difference = tieOut?.difference?.find((item) => item.currency === lines.currency);
  return (
    <div data-testid={panelTestId("rollforward")}>
      <RollforwardBridge
        title={[t("reports.dashboard.rollforward"), lines.currency].join(" · ")}
        currency={lines.currency}
        categories={lines.categories}
        integrity={{ balanced: tieOut?.result !== "FAIL", difference: difference?.amount ?? "0" }}
        footnote={ready.footnote}
        onSelect={ready.openReport}
        headingLevel={2}
      />
    </div>
  );
}

/**
 * The rows of RPT-08 by revenue category as DS-CH-06 categories, with the run's own total. A row of
 * the nonpublic election names its timing. Null where the run holds several currencies.
 */
export function categoriesOf(section: ReportSection): {
  readonly currency: string;
  readonly total: string;
  readonly categories: readonly Category[];
} | null {
  const total = section.totals.length === 1 ? section.totals[0]?.total : undefined;
  if (!isMoney(total)) {
    return null;
  }
  const categories: Category[] = [];
  for (const row of section.rows) {
    const amount = row.total;
    if (!isMoney(amount) || amount.currency !== total.currency) {
      return null;
    }
    const label =
      typeof row.dimension_value_label === "string"
        ? row.dimension_value_label
        : typeof row.timing === "string"
          ? row.timing
          : rowTestKey(row);
    categories.push({ key: row.row_key, label, amount: amount.amount });
  }
  return { currency: total.currency, total: total.amount, categories };
}

function categoryChart(ready: PanelReady, periodText: string): ReactElement | null {
  const bars = categoriesOf(ready.section);
  if (bars === null) {
    return null;
  }
  return (
    <div data-testid={panelTestId("disaggregation")}>
      <CategoryBars
        title={[t("reports.dashboard.category"), bars.currency, periodText].join(" · ")}
        currency={bars.currency}
        categoryHeader={t("reports.column.revenue_category")}
        categories={bars.categories}
        total={bars.total}
        footnote={ready.footnote}
        onSelect={ready.openReport}
        headingLevel={2}
      />
    </div>
  );
}

/**
 * §5.5 flags panel: the open anomaly flags of the context (§8.4), at most eight beside their count,
 * each opening its item in the exception queue. Nothing raises such a flag in this release.
 */
function FlagsPanel({
  entity,
  contextQuery,
}: {
  readonly entity: string | null;
  readonly contextQuery: string;
}) {
  const headingId = useId();
  const built = useBuiltPaths();
  const flags = useQuery({
    queryKey: queryKey("exceptions", "tenant", { view: "dashboard-flags", entity }),
    queryFn: () =>
      fetchListPage<ExceptionItem>(
        EXCEPTIONS_PATH,
        { source: ["ANOMALY"], status: DEFAULT_STATUSES, entity },
        null,
        { limit: FLAGS_LIMIT },
      ),
  });
  const count = flags.data?.total?.count ?? null;
  const heading =
    count === null
      ? t("reports.dashboard.flags.heading")
      : t("reports.dashboard.flags.title", { count: formatNumber(count, { kind: "count" }) });
  // The list the count counts: the queue adds its default Status chip itself (SCREENS §13.3).
  const queue = `${EXCEPTION_QUEUE_ROUTE}${withParams(contextQuery, {
    "f.source": "is:ANOMALY",
    "f.entity": entity === null ? null : `is:${encodeURIComponent(entity)}`,
  })}`;
  const linked = built.has(EXCEPTION_ITEM_ROUTE);
  let body;
  if (flags.isError) {
    body = (
      <RetryBanner
        title={t("reports.dashboard.flags.loadError")}
        problem={flags.error}
        onRetry={() => void flags.refetch()}
        headingLevel={3}
      />
    );
  } else if (flags.data === undefined) {
    body = <Skeleton region={heading} shape="rows" count={3} />;
  } else if (flags.data.items.length === 0) {
    body = <p className="text-body-sm text-fg-2">{t("reports.dashboard.flags.empty")}</p>;
  } else {
    body = (
      <ul className="flex flex-col">
        {flags.data.items.map((item) => {
          const chip = chipFor("E-43", item.severity);
          const record = item.contract_external_id ?? item.business_key;
          return (
            <li
              key={item.id}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-hairline py-2 last:border-b-0"
            >
              {chip === null ? null : <StatusChip status={chip.status} />}
              {/* §8.4: the code, then the record it is about; together they name the item's link. */}
              {linked ? (
                <Link
                  to={exceptionRoute(item.id, contextQuery)}
                  className="font-mono text-mono-sm text-accent-fg hover:underline"
                >
                  {record === null ? item.code : `${item.code} ${record}`}
                </Link>
              ) : (
                <span className="font-mono text-mono-sm text-fg-1">
                  {record === null ? item.code : `${item.code} ${record}`}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    );
  }
  return (
    <section aria-labelledby={headingId} data-testid="SF-08-dashboard-flags" className={PANEL}>
      <h2 id={headingId} className="text-title-sm text-fg-1">
        {heading}
      </h2>
      {body}
      {built.has(EXCEPTION_QUEUE_ROUTE) && count !== null && count > 0 ? (
        <p className="text-body-sm">
          <Link to={queue} className="text-accent-fg hover:underline">
            {t("reports.dashboard.flags.viewAll")}
          </Link>
        </p>
      ) : null}
    </section>
  );
}
