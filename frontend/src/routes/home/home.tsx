// SF-01 Home (SCREENS §2.1 to §2.11, §0.3 SCR-IA-01, SCR-IA-08; DESIGN_SYSTEM DS-CMP-06, DS-CMP-10,
// DS-CMP-12, DS-CMP-14, DS-CMP-29, DS-CH-01, DS-CH-04; 04 API-R-50 API-S-DashboardHome, API-R-09, API-R-10,
// API-R-16, API-R-28, API-R-44; BUILD_SPEC RPS-22). For the context entity, period and book, resolved as
// the context pill resolves them (BR-UX-01) and written into the URL: the key figures, each drilling to
// the screen that owns it; the user's queues; recent activity, or "Recently viewed" without `audit.read`
// for all entities (SCREENS §0.6 SCR-PERM-02; a permission is held for entities, and a region asks for which);
// close status; revenue by period; favourites; and the legacy-parity panel. Figures and counts come from
// the API (DG-FE-08), and links go only to built routes (XR-14). Home is a reading surface without a
// primary action.
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useEffect, useId, useState } from "react";
import { Link, matchPath, useLocation, useNavigate, useNavigation } from "react-router";

import {
  type ContextChoice,
  contextOwner,
  readStoredContext,
  resolveEntityBook,
  resolvePeriod,
} from "../../app/shell/ContextPill";
import { openMembership } from "../../app/shell/open-workspace";
import { useShellSession } from "../../app/shell/SandboxIndicator";
import { compareDecimal } from "../../components/charts/chartKit";
import {
  RevenueWaterfall,
  type WaterfallPeriod,
  type WaterfallTarget,
} from "../../components/charts/RevenueWaterfall";
import { Sparkline } from "../../components/charts/Sparkline";
import { Banner } from "../../components/feedback/Banner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { ClockCounterClockwise, Minus } from "../../components/icons/registry";
import { type Kpi, KpiStrip } from "../../components/record/KpiStrip";
import { Timeline, type TimelineEvent } from "../../components/record/Timeline";
import { Button } from "../../components/ui/Button";
import { cn } from "../../components/ui/cn";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { announce } from "../../lib/a11y/announce";
import { ApiProblem } from "../../lib/api/problems";
import { holdsApprovalPermission, requestRoute } from "../../lib/api/queries/approvals";
import {
  type AuditEvent,
  contractCountKey,
  type DashboardBlockers,
  type DashboardHome,
  dashboardHomeKey,
  favouritesKey,
  favouriteTarget,
  fetchContractCount,
  fetchDashboardHome,
  fetchFavourites,
  fetchLegacyPreset,
  fetchOpenExceptions,
  fetchRecentActivity,
  fetchRecentlyViewed,
  fetchWaitingForYou,
  type HomeContext,
  legacyPresetKey,
  openExceptionsKey,
  recentActivityKey,
  recentlyViewedKey,
  waitingForYouKey,
} from "../../lib/api/queries/dashboard";
import { useMe } from "../../lib/api/queries/me";
import { type SavedView, useUpdateSavedView } from "../../lib/api/queries/saved-views";
import {
  booksKey,
  entitiesKey,
  fetchActiveEntities,
  fetchBooks,
  fetchPeriods,
  type Period,
  periodLabel,
  periodsKey,
  STRUCTURE_READ_PERMISSION,
} from "../../lib/api/queries/tenant";
import {
  dayStartInstant,
  formatDate,
  formatList,
  formatMoney,
  formatNumber,
  formatPercent,
  formatPeriod,
  NO_VALUE,
  timestampDate,
} from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { usePageStays } from "../../lib/url/live-search";
import { withParams } from "../../lib/url/params";
import { useBuiltPaths } from "../settings/index";

/** SCREENS RT-07. */
export const HOME_PATH = "/home";
const SCHEDULES_ROUTE = "/schedules";
const APPROVALS_ROUTE = "/approvals";
const EXCEPTIONS_ROUTE = "/data/exceptions";
const IMPORTS_ROUTE = "/data/imports";
const TEMPLATES_ROUTE = "/data/templates";
/** SCREENS §2.6: the SF-11 filter of the Open exceptions drill. */
const OPEN_STATUS_FILTER = "in:OPEN,IN_PROGRESS";
const CONTRACT_READ = "contract.read";
const EXCEPTION_RESOLVE = "exception.resolve";
const AUDIT_READ = "audit.read";
/** SCREENS §2.4: the per-device dismissal of the legacy panel. */
export const LEGACY_PANEL_STORAGE_PREFIX = "erev.dismissed.legacy-panel.";

/** SCREENS §2.6 close status rows, in this order. */
export const BLOCKER_ORDER: readonly (keyof DashboardBlockers)[] = [
  "approvals_pending",
  "exceptions_open",
  "holds_open",
  "judgements_unreviewed",
  "unmapped_products",
  "interface_failures",
  "jobs_failed",
  "groups_dirty",
  "batches_unexported",
  "batches_unacknowledged",
  "reconciliations_unsigned",
  "manual_adjustments_pending",
];

/** SCREENS §2.6 "Recent activity": the catalogue verbs of known audit actions. */
const AUDIT_VERBS: Readonly<Record<string, string>> = {
  "contract.book": "audit.action.contract.book",
  "import_upload.submit": "audit.action.import_upload.submit",
  "approval_request.approve": "audit.action.approval_request.approve",
};

/** [J] L7-2-Q-24: the object labels of the audit object types Home names; others show the literal. */
const AUDIT_OBJECTS: ReadonlySet<string> = new Set([
  "approval_request",
  "contract",
  "import_upload",
  "journal_run",
  "period_state",
  "saved_view",
]);

const PANEL =
  "flex min-w-0 flex-col gap-3 rounded-md border border-default bg-surface p-[var(--panel-pad)]";
const CELL = "px-2 py-2 align-top text-body-sm";
const HEAD = "px-2 py-1.5 text-start text-caption font-normal text-fg-3";
const MONO = "font-mono text-mono-sm text-fg-1 [overflow-wrap:anywhere]";
const TEXT_LINK = "text-accent-fg hover:text-accent-fg-hover hover:underline";

function enc(value: string): string {
  return encodeURIComponent(value);
}

/** Whether a target path matches a built route pattern (XR-14). */
export function isBuilt(built: ReadonlySet<string>, target: string): boolean {
  const pathname = target.split(/[?#]/, 1)[0] ?? target;
  for (const pattern of built) {
    if (matchPath({ path: pattern, end: true }, pathname) !== null) {
      return true;
    }
  }
  return false;
}

function bookText(code: string | null): string {
  if (code === null) {
    return NO_VALUE;
  }
  return code === "ASC606" || code === "IFRS15" || code === "LEGACY"
    ? t(`shell.context.books.${code}`)
    : code;
}

function dateOf(timestamp: string): string {
  return formatDate(timestampDate(timestamp));
}

function readDismissed(key: string): boolean {
  try {
    return window.localStorage.getItem(key) !== null;
  } catch {
    return false;
  }
}

function storeDismissed(key: string): void {
  try {
    window.localStorage.setItem(key, "1");
  } catch {
    // Storage may be unavailable; the panel stays hidden for this page only.
  }
}

/** SCREENS SCR-ST-05: the negative region banner with the problem and Retry. */
function RetryBanner({
  title,
  problem,
  onRetry,
}: {
  readonly title: string;
  readonly problem: unknown;
  readonly onRetry: () => void;
}) {
  const detail =
    problem instanceof ApiProblem ? (problem.errors[0]?.message ?? problem.detail) : null;
  return (
    <Banner
      tone="negative"
      title={title}
      headingLevel={3}
      actions={
        <Button variant="link" onClick={onRetry}>
          {t("home.retry")}
        </Button>
      }
    >
      {problem instanceof ApiProblem ? <p>{detail ?? problem.title}</p> : null}
      {problem instanceof ApiProblem && problem.requestId !== null ? (
        <p>{t("home.reference", { reference: problem.requestId })}</p>
      ) : null}
    </Banner>
  );
}

function Panel({
  title,
  testId,
  className,
  action,
  children,
}: {
  readonly title: string;
  readonly testId?: string | undefined;
  readonly className?: string | undefined;
  readonly action?: ReactNode;
  readonly children: ReactNode;
}) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} data-testid={testId} className={cn(PANEL, className)}>
      <h2 id={headingId} className="text-title-sm text-fg-1">
        {title}
      </h2>
      {children}
      {action === undefined || action === null ? null : (
        <div className="text-body-sm">{action}</div>
      )}
    </section>
  );
}

function PanelEmpty({
  title,
  description,
}: {
  readonly title: string;
  readonly description: string;
}) {
  return (
    <div className="flex flex-col gap-1 py-2">
      <h3 className="text-body font-medium text-fg-1">{title}</h3>
      <p className="text-body-sm text-fg-2">{description}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// The page.

export function HomePage() {
  const me = useMe();
  const built = useBuiltPaths();
  const location = useLocation();
  const navigate = useNavigate();
  const stays = usePageStays();
  // A navigation that was on its way and did not arrive leaves Home on screen: its context is
  // written then.
  const moving = useNavigation().state !== "idle";
  const access = useAccess();
  const data = me.data;
  // The workspace is the session's: a workspace and its sandbox copies hold one membership id.
  const session = useShellSession();
  const tenantId = openMembership(data, session)?.tenant.id ?? null;
  const structure = access.holdsAnywhere(STRUCTURE_READ_PERMISSION);

  const entities = useQuery({
    queryKey: entitiesKey(),
    queryFn: fetchActiveEntities,
    enabled: structure,
  });
  const books = useQuery({ queryKey: booksKey(), queryFn: fetchBooks, enabled: structure });
  const params = new URLSearchParams(location.search);
  const url: ContextChoice = {
    entity: params.get("entity"),
    period: params.get("period"),
    book: params.get("book"),
  };
  const owner = contextOwner(data, session);
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
  const period = periods.data === undefined ? null : resolvePeriod(periods.data, choices);

  const resolvedEntity = head?.entity.code ?? null;
  const resolvedBook = head?.book.code ?? null;
  const resolvedPeriod = period?.period.period_key ?? null;
  const structureSettled =
    !structure ||
    entities.error !== null ||
    books.error !== null ||
    (entities.data !== undefined && books.data !== undefined && head === null) ||
    periods.error !== null ||
    periods.data !== undefined;
  const ready = data !== undefined && structureSettled;
  const context: HomeContext =
    resolvedEntity !== null && resolvedBook !== null && resolvedPeriod !== null
      ? { entity: resolvedEntity, period: resolvedPeriod, book: resolvedBook }
      : { entity: url.entity ?? null, period: url.period ?? null, book: url.book ?? null };

  // SCREENS SCR-URL-01 to SCR-URL-03: the page writes its resolved context for the context pill.
  const { pathname, search, hash } = location;
  useEffect(() => {
    if (resolvedEntity === null || resolvedBook === null || resolvedPeriod === null) {
      return;
    }
    const current = new URLSearchParams(search);
    if (
      current.get("entity") === resolvedEntity &&
      current.get("period") === resolvedPeriod &&
      current.get("book") === resolvedBook
    ) {
      return;
    }
    // The write names Home's own path: while the member is on the way to another page it would
    // take them back (DG-FE-03 rule (3), rev 1.230). It is made once Home is the page that stays.
    if (!stays()) {
      return;
    }
    void navigate(
      {
        pathname,
        search: withParams(search, {
          entity: enc(resolvedEntity),
          period: enc(resolvedPeriod),
          book: enc(resolvedBook),
        }),
        hash,
      },
      { replace: true },
    );
  }, [
    resolvedEntity,
    resolvedBook,
    resolvedPeriod,
    pathname,
    search,
    hash,
    navigate,
    stays,
    moving,
  ]);

  // SCREENS §2.1: the figures and the exceptions queue are those of the context entity, so their
  // permission is asked for that entity; until the context is resolved, for any entity.
  const holdsForContext = (permission: string): boolean =>
    resolvedEntity === null
      ? access.holdsAnywhere(permission)
      : access.holds(permission, { code: resolvedEntity });
  const canReadFigures = holdsForContext(CONTRACT_READ);
  const dashboard = useQuery({
    queryKey: dashboardHomeKey(context),
    queryFn: () => fetchDashboardHome(context),
    enabled: ready && canReadFigures,
  });
  const byKey = new Map((periods.data ?? []).map((row) => [row.period.period_key, row]));
  const labelOf = (key: string): string => {
    const row = byKey.get(key);
    return row === undefined ? formatPeriod(key) : periodLabel(row.period);
  };
  const canReadExceptions = holdsForContext(EXCEPTION_RESOLVE) || holdsForContext(CONTRACT_READ);
  // The queue of requests the member may decide: any approval permission, for any entity.
  const canApprove = holdsApprovalPermission(access);
  // The audit events are a list of the whole workspace (ruling R-28): `audit.read` for all entities.
  const readsActivity = access.holdsForAll(AUDIT_READ);
  // [J] L7-2-Q-24: the start of the context period at 00:00 UTC.
  const activityFrom = period === null ? null : dayStartInstant(period.period.start_date);

  return (
    <div data-testid="SF-01-page" className="flex min-w-0 flex-col gap-[var(--stack-gap)]">
      <h1 tabIndex={-1} className="text-title-lg text-fg-1">
        {t("home.page.title")}
      </h1>
      {tenantId === null || !structure ? null : <LegacyPanel tenantId={tenantId} built={built} />}
      {canReadFigures ? (
        <KeyFigures
          dashboard={dashboard}
          context={context}
          built={built}
          labelOf={labelOf}
          ready={ready}
        />
      ) : null}
      {/* SCREENS §2.2: at 1280 px and wider two independent columns, 7 : 5, so a tall panel never
          leaves a gap beside a short one; Recent activity and Favourites follow, one under each column
          at 1440 px and at full width below that. */}
      <div className="grid min-w-0 grid-cols-1 items-start gap-[var(--stack-gap)] lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className="flex min-w-0 flex-col gap-[var(--stack-gap)]">
          <WaitingForYou allowed={canApprove} built={built} entity={context.entity} className="" />
          {canReadExceptions ? (
            <OpenExceptions built={built} entity={context.entity} ready={ready} className="" />
          ) : null}
        </div>
        {canReadFigures ? (
          <div className="flex min-w-0 flex-col gap-[var(--stack-gap)]">
            <CloseStatus dashboard={dashboard} built={built} labelOf={labelOf} className="" />
            <RevenueByPeriod
              dashboard={dashboard}
              periods={periods.data ?? []}
              built={built}
              labelOf={labelOf}
              className=""
            />
          </div>
        ) : null}
        {readsActivity ? (
          <RecentActivity
            from={activityFrom}
            ready={ready}
            built={built}
            className="lg:col-span-2 xl:col-span-1 xl:col-start-1"
          />
        ) : (
          <RecentlyViewed built={built} className="lg:col-span-2 xl:col-span-1 xl:col-start-1" />
        )}
        <Favourites built={built} className="lg:col-span-2 xl:col-span-1" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// Key figures.

interface DashboardQuery {
  readonly data: DashboardHome | undefined;
  readonly isPending: boolean;
  readonly error: unknown;
  readonly refetch: () => unknown;
}

function KeyFigures({
  dashboard,
  context,
  built,
  labelOf,
  ready,
}: {
  readonly dashboard: DashboardQuery;
  readonly context: HomeContext;
  readonly built: ReadonlySet<string>;
  readonly labelOf: (key: string) => string;
  readonly ready: boolean;
}) {
  const counted = useQuery({
    queryKey: contractCountKey(),
    queryFn: fetchContractCount,
    enabled: ready,
  });
  const home = dashboard.data;
  const labels = {
    revenue: t("home.kpi.revenue"),
    contractLiability: t("home.kpi.contractLiability"),
    rpo: t("home.kpi.rpo"),
    pendingApprovals: t("home.kpi.pendingApprovals"),
    openExceptions: t("home.kpi.openExceptions"),
  };
  if (dashboard.error !== null && dashboard.error !== undefined) {
    return (
      <div data-testid="SF-01-kpi-strip">
        <RetryBanner
          title={t("home.kpi.loadError")}
          problem={dashboard.error}
          onRetry={() => void dashboard.refetch()}
        />
      </div>
    );
  }
  if (home === undefined) {
    return (
      <KpiStrip
        region
        testId="SF-01-kpi-strip"
        heading={t("home.kpi.headingLoading")}
        loading
        kpis={[
          { id: "revenue", label: labels.revenue, value: null, currency: "" },
          { id: "contract-liability", label: labels.contractLiability, value: null, currency: "" },
          { id: "rpo", label: labels.rpo, value: null, currency: "" },
          { id: "pending-approvals", label: labels.pendingApprovals, value: null, currency: "" },
          { id: "open-exceptions", label: labels.openExceptions, value: null, currency: "" },
        ]}
      />
    );
  }
  const currency = home.context.currency;
  const entity = home.context.entity?.code ?? context.entity;
  const book = home.context.book;
  const periodKey = home.context.period.period_key;
  const pill = `?${[
    ...(entity === null ? [] : [`entity=${enc(entity)}`]),
    `period=${enc(periodKey)}`,
    `book=${enc(book)}`,
  ].join("&")}`;
  const entitySearch = entity === null ? "" : `?entity=${enc(entity)}`;
  const drill = (path: string, query: string): string | undefined =>
    isBuilt(built, path) ? `${path}${query}` : undefined;
  const money = (value: string) => formatMoney(value, currency);
  const { revenue } = home;
  const priorKey = revenue.trend.at(-2)?.period_key ?? null;
  const priorLine =
    revenue.prior === null || priorKey === null
      ? t("home.kpi.noPrior")
      : t("home.kpi.priorLine", {
          period: labelOf(priorKey),
          amount: money(revenue.prior.amount),
          change:
            revenue.change_ratio === null
              ? NO_VALUE
              : formatPercent(revenue.change_ratio, { delta: true }),
        });
  const approvals = home.pending_approvals;
  const exceptions = home.open_exceptions;
  const kpis: Kpi[] = [
    {
      id: "revenue",
      label: labels.revenue,
      value: revenue.current.amount,
      currency,
      testId: "SF-01-kpi-revenue",
      to: drill(SCHEDULES_ROUTE, pill),
      trend: (
        <span data-testid="SF-01-chart-revenue-trend" className="inline-flex">
          <Sparkline
            measure={t("home.kpi.trendMeasure")}
            currency={currency}
            points={revenue.trend.map((point) => ({
              label: labelOf(point.period_key),
              value: point.recognized.amount,
            }))}
          />
        </span>
      ),
      secondary: priorLine,
    },
    {
      id: "contract-liability",
      label: labels.contractLiability,
      value: home.contract_liability.closing.amount,
      currency,
      testId: "SF-01-kpi-contract-liability",
      to: drill("/reports/contract_balance_rollforward", pill),
      secondary: t("home.kpi.opening", { amount: money(home.contract_liability.opening.amount) }),
    },
    {
      id: "rpo",
      label: labels.rpo,
      value: home.rpo.total.amount,
      currency,
      testId: "SF-01-kpi-rpo",
      to: drill("/reports/rpo", pill),
      secondary: t("home.kpi.within12Months", { amount: money(home.rpo.within_12_months.amount) }),
    },
    {
      id: "pending-approvals",
      label: labels.pendingApprovals,
      kind: "count",
      value: String(approvals.count),
      currency: "",
      testId: "SF-01-kpi-pending-approvals",
      to: drill(APPROVALS_ROUTE, entitySearch),
      secondary:
        approvals.count === 0 || approvals.oldest_submitted_at === null
          ? t("home.kpi.noneWaiting")
          : t("home.kpi.oldest", { date: dateOf(approvals.oldest_submitted_at) }),
    },
    {
      id: "open-exceptions",
      label: labels.openExceptions,
      kind: "count",
      value: String(exceptions.total),
      currency: "",
      testId: "SF-01-kpi-open-exceptions",
      to: drill(
        EXCEPTIONS_ROUTE,
        `${entitySearch === "" ? "?" : `${entitySearch}&`}f.status=${OPEN_STATUS_FILTER}`,
      ),
      secondary: t("home.kpi.blocking", {
        count: formatNumber(exceptions.blocking, { kind: "count" }),
      }),
    },
  ];
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className={PANEL}>
        <KpiStrip
          region
          testId="SF-01-kpi-strip"
          heading={t("home.kpi.heading", {
            currency,
            book: bookText(book),
            period: labelOf(periodKey),
          })}
          kpis={kpis}
        />
      </div>
      {counted.data === 0 ? (
        <p data-testid="SF-01-empty-no-contracts" className="text-body-sm text-fg-2">
          {t("home.empty.noContracts")}{" "}
          {isBuilt(built, IMPORTS_ROUTE) ? (
            <Link to={IMPORTS_ROUTE} className={TEXT_LINK}>
              {t("home.empty.goToData")}
            </Link>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// Queues.

function WaitingForYou({
  allowed,
  built,
  entity,
  className,
}: {
  /** The member holds an approval permission for some entity. */
  readonly allowed: boolean;
  readonly built: ReadonlySet<string>;
  readonly entity: string | null;
  readonly className: string;
}) {
  const listed = useQuery({
    queryKey: waitingForYouKey(),
    queryFn: fetchWaitingForYou,
    enabled: allowed,
  });
  const title = t("home.queue.approvals.title");
  const countKey = "home.queue.approvals.titleCount";
  const count = listed.data?.total?.count ?? null;
  const viewAll =
    allowed && isBuilt(built, APPROVALS_ROUTE) ? (
      <Link
        to={`${APPROVALS_ROUTE}${entity === null ? "" : `?entity=${enc(entity)}`}`}
        className={TEXT_LINK}
      >
        {t("home.queue.approvals.viewAll")}
      </Link>
    ) : null;
  let body: ReactNode;
  if (!allowed) {
    body = (
      <PanelEmpty
        title={t("home.queue.approvals.noPermissionTitle")}
        description={t("home.queue.approvals.noPermissionDescription")}
      />
    );
  } else if (listed.isPending) {
    body = <Skeleton region={title} shape="rows" count={3} />;
  } else if (listed.isError) {
    body = (
      <RetryBanner
        title={t("home.queue.approvals.loadError")}
        problem={listed.error}
        onRetry={() => void listed.refetch()}
      />
    );
  } else if (listed.data.items.length === 0) {
    body = (
      <PanelEmpty
        title={t("home.queue.approvals.emptyTitle")}
        description={t("home.queue.approvals.emptyDescription")}
      />
    );
  } else {
    const linked = isBuilt(built, "/approvals/requests/:requestId");
    body = (
      <div data-testid="SF-01-grid-approvals" className="min-w-0 overflow-x-auto">
        <table className="w-full border-collapse">
          <caption className="sr-only">{title}</caption>
          <thead>
            <tr className="border-b border-hairline">
              <th scope="col" className={HEAD}>
                {t("home.queue.approvals.column.request")}
              </th>
              <th scope="col" className={HEAD}>
                {t("home.queue.approvals.column.type")}
              </th>
              <th scope="col" className={HEAD}>
                {t("home.queue.approvals.column.currency")}
              </th>
              <th scope="col" className={`${HEAD} text-end`}>
                {t("home.queue.approvals.column.amount")}
              </th>
              <th scope="col" className={HEAD}>
                {t("home.queue.approvals.column.preparer")}
              </th>
              <th scope="col" className={HEAD}>
                {t("home.queue.approvals.column.submitted")}
              </th>
            </tr>
          </thead>
          <tbody>
            {listed.data.items.map((item) => (
              <tr
                key={item.id}
                data-testid={`SF-01-row-approval-${item.request_no.toLowerCase()}`}
                className="border-b border-hairline last:border-b-0"
              >
                <th scope="row" className={`${CELL} text-start font-normal text-fg-1`}>
                  {linked ? (
                    <Link to={requestRoute(item.id)} className={TEXT_LINK}>
                      {item.summary}
                    </Link>
                  ) : (
                    item.summary
                  )}
                </th>
                <td className={`${CELL} text-fg-2`}>
                  {t(`approvals.subjectType.${item.subject.type}`)}
                </td>
                <td className={`${CELL} font-mono text-mono-sm text-fg-2`}>
                  {item.amount?.currency ?? NO_VALUE}
                </td>
                <td className={`${CELL} num whitespace-nowrap text-end text-fg-1`}>
                  {item.amount === null
                    ? NO_VALUE
                    : formatMoney(item.amount.amount, item.amount.currency)}
                </td>
                <td className={`${CELL} text-fg-2`}>{item.preparer.display_name}</td>
                <td className={`${CELL} whitespace-nowrap text-fg-2`}>
                  {dateOf(item.submitted_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return (
    <Panel
      title={
        count === null ? title : t(countKey, { count: formatNumber(count, { kind: "count" }) })
      }
      className={className}
      action={viewAll}
    >
      {body}
    </Panel>
  );
}

function OpenExceptions({
  built,
  entity,
  ready,
  className,
}: {
  readonly built: ReadonlySet<string>;
  readonly entity: string | null;
  readonly ready: boolean;
  readonly className: string;
}) {
  const listed = useQuery({
    queryKey: openExceptionsKey(entity),
    queryFn: () => fetchOpenExceptions(entity),
    enabled: ready,
  });
  const title = t("home.queue.exceptions.title");
  const countKey = "home.queue.exceptions.titleCount";
  const count = listed.data?.total?.count ?? null;
  const queueSearch = `?${entity === null ? "" : `entity=${enc(entity)}&`}f.status=${OPEN_STATUS_FILTER}`;
  const viewAll = isBuilt(built, EXCEPTIONS_ROUTE) ? (
    <Link to={`${EXCEPTIONS_ROUTE}${queueSearch}`} className={TEXT_LINK}>
      {t("home.queue.exceptions.viewAll")}
    </Link>
  ) : null;
  let body: ReactNode;
  if (listed.isPending) {
    body = <Skeleton region={title} shape="rows" count={3} />;
  } else if (listed.isError) {
    body = (
      <RetryBanner
        title={t("home.queue.exceptions.loadError")}
        problem={listed.error}
        onRetry={() => void listed.refetch()}
      />
    );
  } else if (listed.data.items.length === 0) {
    body = (
      <PanelEmpty
        title={t("home.queue.exceptions.emptyTitle")}
        description={t("home.queue.exceptions.emptyDescription")}
      />
    );
  } else {
    const linked = isBuilt(built, `${EXCEPTIONS_ROUTE}/:exceptionId`);
    body = (
      <div data-testid="SF-01-grid-exceptions" className="min-w-0 overflow-x-auto">
        <table className="w-full border-collapse">
          <caption className="sr-only">{title}</caption>
          <thead>
            <tr className="border-b border-hairline">
              <th scope="col" className={HEAD}>
                {t("home.queue.exceptions.column.severity")}
              </th>
              <th scope="col" className={HEAD}>
                {t("home.queue.exceptions.column.exception")}
              </th>
              <th scope="col" className={HEAD}>
                {t("home.queue.exceptions.column.code")}
              </th>
              <th scope="col" className={HEAD}>
                {t("home.queue.exceptions.column.record")}
              </th>
              <th scope="col" className={HEAD}>
                {t("home.queue.exceptions.column.created")}
              </th>
            </tr>
          </thead>
          <tbody>
            {listed.data.items.map((item) => {
              const chip = chipFor("E-43", item.severity);
              const record = item.business_key ?? item.contract_external_id;
              return (
                <tr key={item.id} className="border-b border-hairline last:border-b-0">
                  <td className={CELL}>
                    {chip === null ? item.severity : <StatusChip status={chip.status} />}
                  </td>
                  <th scope="row" className={`${CELL} text-start font-normal text-fg-1`}>
                    {linked ? (
                      <Link
                        to={`${EXCEPTIONS_ROUTE}/${item.id}${queueSearch}`}
                        className={TEXT_LINK}
                      >
                        {item.title}
                      </Link>
                    ) : (
                      item.title
                    )}
                  </th>
                  <td className={`${CELL} ${MONO}`}>{item.code}</td>
                  <td className={`${CELL} ${MONO}`}>{record ?? NO_VALUE}</td>
                  <td className={`${CELL} whitespace-nowrap text-fg-2`}>
                    {dateOf(item.created_at)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }
  return (
    <Panel
      title={
        count === null ? title : t(countKey, { count: formatNumber(count, { kind: "count" }) })
      }
      className={className}
      action={viewAll}
    >
      {body}
    </Panel>
  );
}

// ---------------------------------------------------------------------------------------------------
// Activity.

function activityVerb(event: AuditEvent): string {
  const key = AUDIT_VERBS[event.action];
  const verb = key === undefined ? event.action : t(key);
  const object = AUDIT_OBJECTS.has(event.object_type)
    ? t(`home.activity.object.${event.object_type}`)
    : event.object_type;
  return t("home.activity.verb", { verb, object });
}

function RecentActivity({
  from,
  ready,
  built,
  className,
}: {
  readonly from: string | null;
  readonly ready: boolean;
  readonly built: ReadonlySet<string>;
  readonly className: string;
}) {
  const listed = useQuery({
    queryKey: recentActivityKey(from),
    queryFn: () => fetchRecentActivity(from),
    enabled: ready,
  });
  // SCREENS §2.7 (SCR-PERM-02): a refused read gives the variant of a member without the permission.
  if (listed.data === null) {
    return <RecentlyViewed built={built} className={className} />;
  }
  const events: readonly TimelineEvent[] = (listed.data ?? []).map((event) => ({
    id: event.id,
    at: event.occurred_at,
    icon: ClockCounterClockwise,
    actor: event.actor.display_name,
    actorIsPerson: event.actor.kind === "USER",
    verb: activityVerb(event),
  }));
  return (
    <Panel title={t("home.activity.title")} testId="SF-01-pane-activity" className={className}>
      {listed.data !== undefined && listed.data.length === 0 ? (
        <p className="text-body-sm text-fg-2">{t("home.activity.empty")}</p>
      ) : (
        <Timeline
          events={events}
          headingLevel={3}
          status={listed.isPending ? "loading" : listed.isError ? "error" : "ready"}
          errorState={
            <RetryBanner
              title={t("home.activity.loadError")}
              problem={listed.error}
              onRetry={() => void listed.refetch()}
            />
          }
        />
      )}
    </Panel>
  );
}

function RecentlyViewed({
  built,
  className,
}: {
  readonly built: ReadonlySet<string>;
  readonly className: string;
}) {
  const listed = useQuery({ queryKey: recentlyViewedKey(), queryFn: fetchRecentlyViewed });
  const title = t("home.activity.recentlyViewed");
  const linked = isBuilt(built, "/contracts/:contractId/obligations");
  let body: ReactNode;
  if (listed.isPending) {
    body = <Skeleton region={title} shape="rows" count={3} />;
  } else if (listed.isError) {
    body = (
      <RetryBanner
        title={t("home.activity.recentlyViewedLoadError")}
        problem={listed.error}
        onRetry={() => void listed.refetch()}
      />
    );
  } else if (listed.data.length === 0) {
    body = <p className="text-body-sm text-fg-2">{t("home.activity.recentlyViewedEmpty")}</p>;
  } else {
    body = (
      <ul className="flex flex-col">
        {listed.data.map((contract) => {
          const chip = chipFor("E-17", contract.status);
          return (
            <li
              key={contract.id}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-hairline py-2 last:border-b-0"
            >
              {linked ? (
                <Link
                  to={`/contracts/${contract.id}/obligations`}
                  className={cn("font-mono text-mono-sm", TEXT_LINK)}
                >
                  {contract.external_id}
                </Link>
              ) : (
                <span className="font-mono text-mono-sm text-fg-1">{contract.external_id}</span>
              )}
              <span className="min-w-0 flex-1 text-body-sm text-fg-2">
                {contract.customer.name}
              </span>
              {chip === null ? null : <StatusChip status={chip.status} caption={chip.caption} />}
            </li>
          );
        })}
      </ul>
    );
  }
  return (
    <Panel title={title} testId="SF-01-pane-recently-viewed" className={className}>
      {body}
    </Panel>
  );
}

// ---------------------------------------------------------------------------------------------------
// Close status and revenue by period.

function CloseStatus({
  dashboard,
  built,
  labelOf,
  className,
}: {
  readonly dashboard: DashboardQuery;
  readonly built: ReadonlySet<string>;
  readonly labelOf: (key: string) => string;
  readonly className: string;
}) {
  const title = t("home.close.title");
  const home = dashboard.data;
  let body: ReactNode;
  let action: ReactNode = null;
  if (dashboard.error !== null && dashboard.error !== undefined) {
    body = (
      <RetryBanner
        title={t("home.close.loadError")}
        problem={dashboard.error}
        onRetry={() => void dashboard.refetch()}
      />
    );
  } else if (home === undefined) {
    body = <Skeleton region={title} shape="rows" count={4} />;
  } else if (home.context.entity === null) {
    body = <p className="text-body-sm text-fg-2">{t("home.close.selectEntity")}</p>;
  } else if (home.close === null) {
    body = <p className="text-body-sm text-fg-2">{t("home.close.none")}</p>;
  } else {
    const { close } = home;
    const entity = home.context.entity.code;
    const periodKey = home.context.period.period_key;
    const chip = chipFor("E-04", close.state);
    const rows = BLOCKER_ORDER.filter((key) => close.blockers[key] > 0);
    // SCREENS §2.6 rev 1.37 (04 §16.13 rev 1.206; ruling R-121 (i)): the row of `exceptions_open` counts
    // the items that hold the lock of the context period — not every open exception, which is the key
    // figure — and it alone of the rows links, to the list it counts: the queue under `blocking` with
    // `close.id`, the period's id.
    const holdingLock = isBuilt(built, EXCEPTIONS_ROUTE)
      ? `${EXCEPTIONS_ROUTE}?blocking=${enc(close.id)}`
      : null;
    body = (
      <div className="flex flex-col gap-3">
        <p className="flex flex-wrap items-center gap-2 text-body-sm text-fg-2">
          {chip === null ? null : <StatusChip status={chip.status} caption={chip.caption} />}
          <span>{formatList([labelOf(periodKey), entity], "unit")}</span>
        </p>
        {rows.length === 0 ? (
          <p className="text-body-sm text-fg-2">{t("home.close.noBlockers")}</p>
        ) : (
          <dl className="flex flex-col">
            {rows.map((key) => (
              <div
                key={key}
                className="flex items-baseline justify-between gap-3 border-b border-hairline py-1.5 last:border-b-0"
              >
                <dt className="min-w-0 text-body-sm text-fg-2">
                  {key === "exceptions_open" && holdingLock !== null ? (
                    <Link to={holdingLock} className={TEXT_LINK}>
                      {t(`home.close.blocker.${key}`)}
                    </Link>
                  ) : (
                    t(`home.close.blocker.${key}`)
                  )}
                </dt>
                <dd className="num text-body-sm text-fg-1">
                  {formatNumber(close.blockers[key], { kind: "count" })}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    );
    const cockpit = `/close/${enc(entity)}/${enc(home.context.book)}/${enc(periodKey)}`;
    if (isBuilt(built, cockpit)) {
      action = (
        <Link to={cockpit} className={TEXT_LINK}>
          {t("home.close.open")}
        </Link>
      );
    }
  }
  return (
    <Panel title={title} testId="SF-01-pane-close" className={className} action={action}>
      {body}
    </Panel>
  );
}

const OPEN_STATES: ReadonlySet<string> = new Set(["open", "closing", "reopened"]);

function RevenueByPeriod({
  dashboard,
  periods,
  built,
  labelOf,
  className,
}: {
  readonly dashboard: DashboardQuery;
  readonly periods: readonly Period[];
  readonly built: ReadonlySet<string>;
  readonly labelOf: (key: string) => string;
  readonly className: string;
}) {
  const navigate = useNavigate();
  const title = t("home.chart.title");
  const home = dashboard.data;
  if (home === undefined) {
    const failed = dashboard.error !== null && dashboard.error !== undefined;
    return (
      <Panel title={title} testId="SF-01-chart-revenue" className={className}>
        {failed ? (
          <RetryBanner
            title={t("home.chart.loadError")}
            problem={dashboard.error}
            onRetry={() => void dashboard.refetch()}
          />
        ) : (
          <Skeleton region={title} shape="rows" count={4} />
        )}
      </Panel>
    );
  }
  const chart = home.revenue_chart;
  const currency = home.context.currency;
  const states = new Map(periods.map((row) => [row.period.period_key, row.state]));
  const columns: WaterfallPeriod[] = chart.periods.map((row) => ({
    key: row.period_key,
    label: labelOf(row.period_key),
    recognized: row.recognized.amount,
    scheduled: row.scheduled.amount,
    total: row.total.amount,
    open: OPEN_STATES.has(states.get(row.period_key) ?? ""),
  }));
  const empty =
    compareDecimal(chart.totals.total.amount, "0") === 0 &&
    chart.periods.every(
      (row) =>
        compareDecimal(row.recognized.amount, "0") === 0 &&
        compareDecimal(row.scheduled.amount, "0") === 0,
    );
  const entity = home.context.entity?.code ?? null;
  const schedules = isBuilt(built, SCHEDULES_ROUTE);
  const select = (target: WaterfallTarget) => {
    const changes: string[] = [];
    if (entity !== null) {
      changes.push(`entity=${enc(entity)}`);
    }
    changes.push(`period=${enc(target.period ?? home.context.period.period_key)}`);
    changes.push(`book=${enc(home.context.book)}`);
    if (target.series !== null) {
      changes.push(`f.state=is:${target.series}`);
    }
    void navigate(`${SCHEDULES_ROUTE}?${changes.join("&")}`);
  };
  return (
    <div data-testid="SF-01-chart-revenue" className={cn("min-w-0", className)}>
      <RevenueWaterfall
        title={title}
        subtitle={t("home.chart.subtitle", { currency, book: bookText(home.context.book) })}
        scope={entity ?? t("home.chart.allEntities")}
        currency={currency}
        periods={columns}
        awaiting={{ amount: chart.awaiting_trigger.amount, count: chart.pending_trigger_count }}
        totals={{
          recognized: chart.totals.recognized.amount,
          scheduled: chart.totals.scheduled.amount,
          awaiting: chart.totals.awaiting_trigger.amount,
          total: chart.totals.total.amount,
        }}
        state={empty ? "empty" : "ready"}
        emptyText={t("home.chart.empty")}
        onSelect={schedules ? select : undefined}
        headingLevel={2}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// Favourites and the legacy panel.

function FavouriteRow({
  view,
  built,
}: {
  readonly view: SavedView;
  readonly built: ReadonlySet<string>;
}) {
  const unpin = useUpdateSavedView(view.id);
  const { path, label } = favouriteTarget(view);
  return (
    <li className="flex items-center justify-between gap-2 border-b border-hairline py-1 last:border-b-0">
      {path !== null && isBuilt(built, path) ? (
        <Link to={path} className={cn("min-w-0 text-body-sm [overflow-wrap:anywhere]", TEXT_LINK)}>
          {label}
        </Link>
      ) : (
        <span className="min-w-0 text-body-sm text-fg-1 [overflow-wrap:anywhere]">{label}</span>
      )}
      <Button
        variant="ghost"
        size="sm"
        icon={Minus}
        aria-label={t("home.favourites.unpin", { label })}
        loading={unpin.pending}
        onClick={() => void unpin.submit({ is_favourite: false })}
      />
    </li>
  );
}

function Favourites({
  built,
  className,
}: {
  readonly built: ReadonlySet<string>;
  readonly className: string;
}) {
  const listed = useQuery({ queryKey: favouritesKey(), queryFn: fetchFavourites });
  const title = t("home.favourites.title");
  let body: ReactNode;
  if (listed.isPending) {
    body = <Skeleton region={title} shape="rows" count={3} />;
  } else if (listed.isError) {
    body = (
      <RetryBanner
        title={t("home.favourites.loadError")}
        problem={listed.error}
        onRetry={() => void listed.refetch()}
      />
    );
  } else if (listed.data.length === 0) {
    body = (
      <PanelEmpty
        title={t("home.favourites.emptyTitle")}
        description={t("home.favourites.emptyDescription")}
      />
    );
  } else {
    body = (
      <ul className="flex flex-col">
        {listed.data.map((view) => (
          <FavouriteRow key={view.id} view={view} built={built} />
        ))}
      </ul>
    );
  }
  return (
    <Panel title={title} testId="SF-01-pane-favourites" className={className}>
      {body}
    </Panel>
  );
}

function LegacyPanel({
  tenantId,
  built,
}: {
  readonly tenantId: string;
  readonly built: ReadonlySet<string>;
}) {
  const storageKey = `${LEGACY_PANEL_STORAGE_PREFIX}${tenantId}`;
  const [dismissed, setDismissed] = useState(() => readDismissed(storageKey));
  const preset = useQuery({
    queryKey: legacyPresetKey(),
    queryFn: fetchLegacyPreset,
    enabled: !dismissed,
  });
  if (dismissed || preset.data !== true) {
    return null;
  }
  // SF-26 (the transition map) is not built, so only the templates action renders (XR-14; L7-2-Q-25).
  const templates = `${TEMPLATES_ROUTE}?f.family=is:LEGACY_V1`;
  return (
    <div data-testid="SF-01-banner-legacy">
      <Banner
        tone="info"
        announce="static"
        title={t("home.legacy.title")}
        actions={
          isBuilt(built, TEMPLATES_ROUTE) ? (
            <Link to={templates} className={cn("text-body-sm font-medium", TEXT_LINK)}>
              {t("home.legacy.templates")}
            </Link>
          ) : undefined
        }
        onDismiss={() => {
          storeDismissed(storageKey);
          setDismissed(true);
          announce(t("home.legacy.dismissed"), "polite");
        }}
      >
        <p>{t("home.legacy.message")}</p>
      </Banner>
    </div>
  );
}
