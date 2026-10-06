// SF-08 Report catalogue (SCREENS_B §5.1; SCREENS RT-31; DESIGN_SYSTEM DS-CMP-06, DS-CMP-10, DS-CMP-13,
// DS-CMP-23; 04 API-R-41; BUILD_SPEC RPS-6). `h1` "Reports", quick search and the Group and Kind filters
// over `GET /report-definitions`, the viewer's recent runs and one static table per report group in
// §5.6 index order. The forecast and migration reports stay hidden without a scenario sandbox or a
// migration (§5.1 visibility); packs link to SF-09 once it is built. The `h1` and the route tabs of the
// built Reports pages come from the area frame (`./frame`, SCR-IA-02); the "Dashboards" list links to
// the dashboards that are built (SF-08:dashboard, BUILD_SPEC RPS-19) and stands beside "Recent runs" at
// 1440 px; the pin column waits for a DS-ICO-07 pin icon (L7-3-Q-5).
import { useQuery } from "@tanstack/react-query";
import { useId, useMemo } from "react";
import { Link, useLocation } from "react-router";

import { contextSearch } from "../../app/shell/IconRail";
import { testIdKey } from "../../components/data-grid/DataGrid";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import { type FilterField, parseFilters } from "../../components/filter-bar/filters";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { Button } from "../../components/ui/Button";
import { chipFor, OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { Tooltip } from "../../components/ui/Tooltip";
import { useMe } from "../../lib/api/queries/me";
import {
  fetchRecentReportRuns,
  fetchReportDefinitions,
  recentReportRunsKey,
  type ReportDefinition,
  reportDefinitionsKey,
  type ReportRun,
} from "../../lib/api/queries/reports";
import { addDays, formatDate, timestampDate, utcDateOf } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { useBuiltPaths } from "../settings/index";
import { DASHBOARD_ROUTE, dashboardRoute, DASHBOARDS } from "./dashboards";
import { ReportsHeader } from "./frame";
import {
  groupLabel,
  groupTestId,
  HIDDEN_CODES,
  kindLabel,
  PACK_CODES,
  REPORT_GROUPS,
  type ReportGroup,
} from "./viewer/specs";

const CONTEXT = ["entity", "period", "book"] as const;
/** SCREENS SCR-URL-01 to SCR-URL-06 context a report link keeps. */
const REPORT_CONTEXT = ["entity", "period", "book", "currency_view", "known_at"] as const;
const RECENT_DAYS = 30;
const RECENT_ROWS = 10;
const EVIDENCE_ROUTE = "/evidence";
const KINDS = ["STANDARD", "REGISTER", "DISCLOSURE", "EXTRACT", "PACK", "LEGACY_EXPORT"] as const;

/** The context parameters of `names` that a report link keeps, in that order. */
function keptSearch(search: string, names: readonly string[]): string {
  const current = new URLSearchParams(search);
  const kept = new URLSearchParams();
  for (const name of names) {
    const value = current.get(name);
    if (value !== null && value !== "") {
      kept.set(name, value);
    }
  }
  const text = kept.toString();
  return text === "" ? "" : `?${text}`;
}

function matches(
  definition: ReportDefinition,
  group: ReportGroup,
  query: string,
  groups: readonly string[] | null,
  kinds: readonly string[] | null,
): boolean {
  const text = query.trim().toLocaleLowerCase();
  if (
    text !== "" &&
    !definition.name.toLocaleLowerCase().includes(text) &&
    !definition.description.toLocaleLowerCase().includes(text)
  ) {
    return false;
  }
  if (groups !== null && !groups.includes(group.id)) {
    return false;
  }
  return kinds === null || kinds.includes(definition.kind);
}

export function ReportCatalogue() {
  const location = useLocation();
  const me = useMe();
  const built = useBuiltPaths();
  const definitions = useQuery({
    queryKey: reportDefinitionsKey(),
    queryFn: fetchReportDefinitions,
  });
  const createdFrom = useMemo(() => addDays(utcDateOf(Date.now()), -RECENT_DAYS), []);
  const recent = useQuery({
    queryKey: recentReportRunsKey(createdFrom),
    queryFn: () => fetchRecentReportRuns(createdFrom),
  });
  const fields: readonly FilterField[] = useMemo(
    () => [
      {
        name: "group",
        label: t("reports.catalogue.filter.group"),
        kind: "enum",
        operators: ["is", "in"],
        options: REPORT_GROUPS.map((group) => ({
          value: group.id,
          label: t(`reports.catalogue.group.${group.id}`),
        })),
      },
      {
        name: "kind",
        label: t("reports.catalogue.filter.kind"),
        kind: "enum",
        operators: ["is", "in"],
        options: KINDS.map((kind) => ({ value: kind, label: kindLabel(kind) })),
      },
    ],
    [],
  );
  const parsed = parseFilters(location.search, fields);
  const groupFilter = parsed.filters.find((item) => item.field === "group")?.values ?? null;
  const kindFilter = parsed.filters.find((item) => item.field === "kind")?.values ?? null;
  const reportSearch = keptSearch(location.search, REPORT_CONTEXT);

  const byCode = new Map((definitions.data ?? []).map((item) => [item.code, item]));
  const tables = REPORT_GROUPS.map((group) => ({
    group,
    items: group.codes.flatMap((code) => {
      const found = byCode.get(code);
      return found === undefined ||
        HIDDEN_CODES.has(code) ||
        !matches(found, group, parsed.query, groupFilter, kindFilter)
        ? []
        : [found];
    }),
  })).filter((table) => table.items.length > 0);
  const shown = tables.reduce((count, table) => count + table.items.length, 0);

  let catalogue;
  if (definitions.isError) {
    catalogue = (
      <Banner
        tone="negative"
        title={t("reports.catalogue.loadError")}
        actions={
          <Button variant="link" onClick={() => void definitions.refetch()}>
            {t("reports.catalogue.retry")}
          </Button>
        }
      />
    );
  } else if (definitions.data === undefined) {
    catalogue = <Skeleton region={t("reports.catalogue.title")} shape="rows" count={10} />;
  } else if (tables.length === 0) {
    catalogue = (
      <p className="text-body-sm text-fg-2" role="status">
        {t("reports.catalogue.noResults")}
      </p>
    );
  } else {
    catalogue = tables.map(({ group, items }) => (
      <GroupTable
        key={group.id}
        group={group}
        items={items}
        search={reportSearch}
        packsBuilt={built.has(EVIDENCE_ROUTE)}
      />
    ));
  }

  return (
    <div data-testid="SF-08-page" className="flex flex-col">
      <ReportsHeader />
      <div className="flex flex-col gap-6 px-[var(--gutter)] py-[var(--panel-pad)]">
        <FilterBar
          fields={fields}
          searchLabel={t("reports.catalogue.search")}
          resultCount={definitions.data === undefined ? undefined : shown}
          resultLabel={(count) => t("reports.catalogue.count", { count, formatted: String(count) })}
        />
        {/* §5.1: "Dashboards" beside "Recent runs" at 1440 px, above it below that width. */}
        <div
          className={
            built.has(DASHBOARD_ROUTE)
              ? "grid min-w-0 grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]"
              : "flex min-w-0 flex-col"
          }
        >
          {built.has(DASHBOARD_ROUTE) ? (
            <Dashboards search={contextSearch(location.search, CONTEXT)} />
          ) : null}
          <RecentRuns
            runs={recent.data}
            failed={recent.isError}
            userId={me.data?.user.id ?? null}
            search={contextSearch(location.search, CONTEXT)}
            onRetry={() => void recent.refetch()}
          />
        </div>
        {catalogue}
      </div>
    </div>
  );
}

/** §5.1 "Dashboards": a flat list of links, each with its one-line description. */
function Dashboards({ search }: { readonly search: string }) {
  const headingId = useId();
  return (
    <section
      aria-labelledby={headingId}
      data-testid="SF-08-dashboards"
      className="flex min-w-0 flex-col gap-2"
    >
      <h2 id={headingId} className="text-title-sm text-fg-1">
        {t("reports.catalogue.dashboards")}
      </h2>
      <ul className="flex flex-col rounded-md border border-default bg-surface">
        {DASHBOARDS.map((dashboard) => (
          <li
            key={dashboard.code}
            className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-hairline px-3 py-2 text-body-sm first:border-t-0"
          >
            <Link
              to={`${dashboardRoute(dashboard.code)}${search}`}
              className="font-medium text-accent-fg hover:underline"
            >
              {t(dashboard.nameKey)}
            </Link>
            <span className="text-fg-2">{t(dashboard.descriptionKey)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function GroupTable({
  group,
  items,
  search,
  packsBuilt,
}: {
  readonly group: ReportGroup;
  readonly items: readonly ReportDefinition[];
  readonly search: string;
  readonly packsBuilt: boolean;
}) {
  const header = "px-3 py-2 text-start text-body-sm font-medium text-fg-2";
  const cell = "px-3 py-2 align-top text-body-sm text-fg-1";
  return (
    <table
      data-testid={groupTestId(group)}
      className="w-full table-fixed border-separate border-spacing-0 overflow-hidden rounded-md border border-default bg-surface"
    >
      <caption className="mb-2 text-start text-title-sm text-fg-1">
        {groupLabel(group, items.length)}
      </caption>
      {/* Fixed columns: a description truncates to one line with its tooltip (§5.1 1280 px). */}
      <colgroup>
        <col className="w-80" />
        <col />
        <col className="w-32" />
        <col className="w-40" />
        <col className="w-20" />
      </colgroup>
      <thead className="bg-subtle">
        <tr>
          <th scope="col" className={header}>
            {t("reports.catalogue.column.report")}
          </th>
          <th scope="col" className={header}>
            {t("reports.catalogue.column.description")}
          </th>
          <th scope="col" className={header}>
            {t("reports.catalogue.column.kind")}
          </th>
          <th scope="col" className={header}>
            {t("reports.catalogue.column.outputs")}
          </th>
          <th scope="col" className={header}>
            {t("reports.catalogue.column.version")}
          </th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => {
          const pack = PACK_CODES.has(item.code);
          return (
            <tr key={item.code} data-testid={`SF-08-row-${testIdKey(item.code)}`}>
              <th scope="row" className={`${cell} border-t border-hairline text-start font-medium`}>
                {pack && !packsBuilt ? (
                  item.name
                ) : (
                  <Link
                    to={pack ? EVIDENCE_ROUTE : `/reports/${item.code}${search}`}
                    className="text-accent-fg hover:underline"
                  >
                    {item.name}
                  </Link>
                )}
              </th>
              <td className={`${cell} max-w-110 border-t border-hairline`}>
                {/* A one-column grid bounds the tooltip wrapper to the cell, so the line truncates. */}
                <div className="grid grid-cols-1">
                  <Tooltip content={item.description}>
                    {(trigger) => (
                      <span
                        {...trigger}
                        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- DS-CMP-27: a tooltip trigger is focusable
                        tabIndex={0}
                        className="block min-w-0 truncate text-fg-2"
                      >
                        {item.description}
                      </span>
                    )}
                  </Tooltip>
                </div>
              </td>
              <td className={`${cell} border-t border-hairline`}>
                <OutlineChip label={kindLabel(item.kind)} />
              </td>
              <td className={`${cell} border-t border-hairline font-mono text-mono-sm`}>
                {item.output_formats.filter((format) => format !== "JSON").join(" ")}
              </td>
              <td className={`${cell} border-t border-hairline`}>
                {t("reports.catalogue.version", { version: item.version })}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function RecentRuns({
  runs,
  failed,
  userId,
  search,
  onRetry,
}: {
  readonly runs: readonly ReportRun[] | undefined;
  readonly failed: boolean;
  readonly userId: string | null;
  readonly search: string;
  readonly onRetry: () => void;
}) {
  const headingId = useId();
  const mine =
    runs === undefined || userId === null
      ? undefined
      : runs.filter((run) => run.run_by.id === userId).slice(0, RECENT_ROWS);
  let content;
  if (failed) {
    content = (
      <Banner
        tone="negative"
        headingLevel={3}
        title={t("reports.catalogue.recent.loadError")}
        actions={
          <Button variant="link" onClick={onRetry}>
            {t("reports.catalogue.retry")}
          </Button>
        }
      />
    );
  } else if (mine === undefined) {
    content = <Skeleton region={t("reports.catalogue.recent.title")} shape="rows" count={3} />;
  } else if (mine.length === 0) {
    content = (
      <EmptyState
        headingLevel={3}
        title={t("reports.catalogue.recent.empty.title")}
        description={t("reports.catalogue.recent.empty.description")}
      />
    );
  } else {
    const header = "px-3 py-2 text-start text-body-sm font-medium text-fg-2";
    const cell = "border-t border-hairline px-3 py-2 text-body-sm text-fg-1";
    const join = (base: string, run: ReportRun) =>
      `${base}${search === "" ? "?" : `${search}&`}run=${encodeURIComponent(run.id)}`;
    content = (
      <table
        data-testid="SF-08-grid-recent-runs"
        aria-labelledby={headingId}
        className="w-full border-separate border-spacing-0 rounded-md border border-default bg-surface"
      >
        <thead className="bg-subtle">
          <tr>
            <th scope="col" className={header}>
              {t("reports.catalogue.recent.column.run")}
            </th>
            <th scope="col" className={header}>
              {t("reports.catalogue.recent.column.report")}
            </th>
            <th scope="col" className={header}>
              {t("reports.catalogue.recent.column.status")}
            </th>
            <th scope="col" className={header}>
              {t("reports.catalogue.recent.column.runAt")}
            </th>
          </tr>
        </thead>
        <tbody>
          {mine.map((run) => {
            const chip = chipFor("E-67", run.status);
            const at = run.started_at ?? run.finished_at;
            return (
              <tr key={run.id}>
                <td className={cell}>
                  <Link
                    to={
                      run.output === null || run.output.format === "JSON"
                        ? join(`/reports/${run.report.code}`, run)
                        : `/reports/${run.report.code}${search}`
                    }
                    className="font-mono text-mono-sm text-accent-fg hover:underline"
                  >
                    {run.report_run_no}
                  </Link>
                </td>
                <td className={cell}>{run.report.name}</td>
                <td className={cell}>
                  {chip === null ? null : (
                    <StatusChip status={chip.status} caption={chip.caption} />
                  )}
                </td>
                <td className={`${cell} num`} data-volatile="">
                  {at === null ? null : formatDate(timestampDate(at))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  }
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <h2 id={headingId} className="text-title-sm text-fg-1">
        {t("reports.catalogue.recent.title")}
      </h2>
      {content}
    </section>
  );
}
