// SF-08:runs Report run register (SCREENS_B §5.3; SCREENS §0.3 SCR-IA-02, SCR-IA-07; §0.4 RT-106; §0.5
// SCR-URL-10; §0.6 SCR-PERM-01; DESIGN_SYSTEM DS-CMP-10, DS-CMP-13, DS-CMP-19, DS-CMP-23, DS-FMT-16,
// DS-FMT-17, DS-FMT-23; 04 API-R-41, API-S-ReportRun, T-RPT-02; REQ-RPT-002; CTL-029; BUILD_SPEC RPS-18).
// The Reports frame with the tab "Report runs" and the DataGrid "Report runs": every report and export
// run the viewer may see, with its IPE fields — report and version, status, entity scope, book, as-of
// date, source, output format, row count, output hash, who ran it and when. The API decides which runs
// are listed (a run is listed under its report's run permission, 04 API-R-41 rev 1.128); the screen
// filters nothing itself. The chips are the route's filters: Report, Status, Created from and Created
// to. The list keeps the API's order, newest first: API-R-41 sorts by `id` or `created_at`, and the run
// carries neither as a column, so no column sorts.
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import { SavedViewSelector } from "../../components/data-grid/SavedViewSelector";
import {
  type GridColumn,
  type GridColumnState,
  type GridSource,
  initialColumnState,
} from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import { type FilterField, parseFilters, withFilters } from "../../components/filter-bar/filters";
import { CopySimple } from "../../components/icons/registry";
import { NoValue } from "../../components/money/Num";
import { Button } from "../../components/ui/Button";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { announce } from "../../lib/a11y/announce";
import { useAccess } from "../../lib/access";
import { type Me, useMe } from "../../lib/api/queries/me";
import {
  fetchReportDefinitions,
  fetchReportRunsPage,
  mayReadReportRuns,
  REPORT_ROUTE,
  type ReportDefinition,
  reportDefinitionsKey,
  type ReportRun,
  type ReportRunQuery,
  reportRunRoute,
  reportRunsKey,
} from "../../lib/api/queries/reports";
import { addDays, dayStartInstant, formatTimestamp, parseDateInput } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { urlChipValues } from "../contracts/list";
import { useBuiltPaths } from "../settings/index";
import { ReportRunsAccessLimited } from "./access";
import { ReportsHeader } from "./frame";
import { reportViewHref } from "./run-links";
import { bookLabel, hashPrefix, runAsOf } from "./viewer/RunStamp";

/** SCREENS SCR-IA-07 saved-view code. */
export const REPORT_RUNS_SCREEN_CODE = "SF-08:runs";
/** E-67 `run_status`, in the order a run passes through. */
const RUN_STATUSES = ["QUEUED", "RUNNING", "SUCCEEDED", "FAILED"] as const;

function statusWord(status: string): string {
  return chipFor("E-67", status)?.status ?? status;
}

/** SCREENS_B §5.3 filters, in route order: `f.report_code`, `f.status`, `f.created_from`, `f.created_to`. */
export function reportRunFilterFields(
  search: string,
  definitions: readonly ReportDefinition[] | undefined,
): readonly FilterField[] {
  return [
    {
      name: "report_code",
      label: t("reports.runs.filter.report"),
      kind: "enum",
      operators: ["is", "in"],
      options:
        definitions === undefined
          ? urlChipValues(search, "report_code").map((value) => ({ value, label: value }))
          : definitions.map((definition) => ({ value: definition.code, label: definition.name })),
      optionsLoading: definitions === undefined,
    },
    {
      name: "status",
      label: t("reports.runs.filter.status"),
      kind: "enum",
      operators: ["is", "in"],
      options: RUN_STATUSES.map((status) => ({ value: status, label: statusWord(status) })),
    },
    {
      name: "created_from",
      label: t("reports.runs.filter.createdFrom"),
      kind: "date",
      operators: ["gte"],
    },
    {
      name: "created_to",
      label: t("reports.runs.filter.createdTo"),
      kind: "date",
      operators: ["lte"],
    },
  ];
}

/** A `YYYY-MM-DD` chip operand as a business date, or null. */
function chipDate(value: string | undefined): string | null {
  const parsed = parseDateInput(value ?? "");
  return parsed.ok ? parsed.value : null;
}

/**
 * The API query of the URL chips. The two dates are whole days of platform time: `created_from` is
 * the first instant of its day and `created_to`, which the API reads as exclusive, the first instant
 * of the day after.
 */
export function reportRunQuery(search: string, fields: readonly FilterField[]): ReportRunQuery {
  const parsed = parseFilters(search, fields);
  const chip = (name: string) => parsed.filters.find((filter) => filter.field === name);
  const from = chipDate(chip("created_from")?.values[0]);
  const to = chipDate(chip("created_to")?.values[0]);
  return {
    reportCodes: chip("report_code")?.values ?? [],
    statuses: chip("status")?.values ?? [],
    createdFrom: from === null ? null : dayStartInstant(from),
    createdTo: to === null ? null : dayStartInstant(addDays(to, 1)),
  };
}

function mono(text: string) {
  return <span className="truncate font-mono text-mono-sm text-fg-1">{text}</span>;
}

/** When the run was recorded: masked in captures (SCR-TID-05). */
function Instant({ value }: { readonly value: string | null }) {
  return value === null ? (
    <NoValue />
  ) : (
    <time dateTime={value} data-volatile="" className="num whitespace-nowrap">
      {formatTimestamp(value)}
    </time>
  );
}

/** DS-FMT-23: the hash as its first 8 and last 4 characters, the full value for assistive technology. */
function OutputHash({ sha }: { readonly sha: string }) {
  return (
    <span className="inline-flex items-center gap-1" data-volatile="">
      <span aria-hidden="true" className="font-mono text-mono-sm text-fg-1">
        {hashPrefix(sha)}
      </span>
      <span className="sr-only">{sha}</span>
      <Button
        variant="ghost"
        size="sm"
        icon={CopySimple}
        tabIndex={-1}
        aria-label={t("reports.stamp.copySha")}
        onClick={() => {
          void navigator.clipboard
            .writeText(sha)
            .then(() => announce(t("reports.stamp.copied"), "polite"));
        }}
      />
    </span>
  );
}

export interface ReportRunColumnOptions {
  /** The built routes: "Report" links to SF-08:report where that screen is built. */
  readonly built: ReadonlySet<string>;
  /** Opens a route: Enter on the Report cell drills as a click on its link does. */
  readonly open: (to: string) => void;
}

/** SCREENS_B §5.3 "Grid columns: SF-08:runs", the REQ-RPT-002 fields of a run. */
export function reportRunColumns({
  built,
  open,
}: ReportRunColumnOptions): readonly GridColumn<ReportRun>[] {
  const view = (run: ReportRun) => (built.has(REPORT_ROUTE) ? reportViewHref(run) : null);
  const reportName = (run: ReportRun) =>
    t("reports.stamp.reportValue", { name: run.report.name, version: run.report.version });
  return [
    {
      id: "report_run_no",
      header: t("reports.runs.column.run"),
      kind: "identifier",
      value: (run) => run.report_run_no,
      href: (run) => reportRunRoute(run.id),
      width: 136,
    },
    {
      id: "report",
      header: t("reports.runs.column.report"),
      kind: "text",
      value: reportName,
      render: (run) => {
        const to = view(run);
        return to === null ? (
          <span className="truncate" title={reportName(run)}>
            {reportName(run)}
          </span>
        ) : (
          <Link
            to={to}
            tabIndex={-1}
            title={reportName(run)}
            className="truncate text-accent-fg hover:text-accent-fg-hover hover:underline"
          >
            {reportName(run)}
          </Link>
        );
      },
      activate: (run) => {
        const to = view(run);
        if (to !== null) {
          open(to);
        }
      },
      // Most report names fit on the line; a longer one is cut and keeps its full text in the title.
      width: 288,
    },
    {
      id: "status",
      header: t("reports.runs.column.status"),
      kind: "status",
      value: (run) => statusWord(run.status),
      render: (run) => {
        const chip = chipFor("E-67", run.status);
        return chip === null ? null : <StatusChip status={chip.status} caption={chip.caption} />;
      },
      width: 128,
    },
    {
      id: "entity",
      header: t("reports.runs.column.entity"),
      kind: "text",
      value: (run) =>
        run.entity_scope.length === 0 ? null : run.entity_scope.map((item) => item.code).join(", "),
      render: (run) =>
        run.entity_scope.length === 0 ? (
          <NoValue />
        ) : (
          mono(run.entity_scope.map((item) => item.code).join(", "))
        ),
      width: 144,
    },
    {
      id: "book",
      header: t("reports.runs.column.book"),
      kind: "text",
      value: (run) => (run.book === null ? null : bookLabel(run.book)),
      width: 104,
    },
    {
      id: "as_of",
      header: t("reports.runs.column.asOf"),
      kind: "date",
      value: (run) => runAsOf(run),
    },
    {
      id: "source",
      header: t("reports.runs.column.source"),
      kind: "text",
      value: (run) =>
        t(
          run.period_lock_id === null
            ? "reports.runs.source.current"
            : "reports.runs.source.locked",
        ),
      width: 112,
    },
    {
      id: "format",
      header: t("reports.runs.column.format"),
      kind: "text",
      value: (run) => run.output?.format ?? null,
      render: (run) => (run.output === null ? <NoValue /> : mono(run.output.format)),
      width: 96,
    },
    {
      id: "row_count",
      header: t("reports.runs.column.rows"),
      kind: "number",
      numberKind: "count",
      value: (run) => (run.row_count === null ? null : String(run.row_count)),
      width: 96,
    },
    {
      id: "output_sha256",
      header: t("reports.runs.column.sha"),
      kind: "text",
      value: (run) => run.output?.sha256 ?? null,
      render: (run) => (run.output === null ? <NoValue /> : <OutputHash sha={run.output.sha256} />),
      width: 184,
    },
    {
      id: "run_by",
      header: t("reports.runs.column.runBy"),
      kind: "user",
      value: (run) => run.run_by.display_name,
    },
    {
      id: "started_at",
      header: t("reports.runs.column.started"),
      kind: "timestamp",
      value: (run) => run.started_at,
      render: (run) => <Instant value={run.started_at} />,
      // "01 Oct 2026 06:42 UTC" with the cell padding is 186 px; the kit's default is 176.
      width: 192,
    },
    {
      id: "finished_at",
      header: t("reports.runs.column.finished"),
      kind: "timestamp",
      value: (run) => run.finished_at,
      render: (run) => <Instant value={run.finished_at} />,
      width: 192,
    },
  ];
}

/** The default layout: every column in definition order, the run number pinned to the start. */
const DEFAULT_COLUMNS: GridColumnState = initialColumnState(
  reportRunColumns({ built: new Set(), open: () => undefined }),
);

function ReportRunsPage({ me }: { readonly me: Me }) {
  const location = useLocation();
  const navigate = useNavigate();
  const built = useBuiltPaths();
  const search = location.search;
  // The report names of the Report chip; a caller reads the definitions of the reports it may run.
  const definitions = useQuery({
    queryKey: reportDefinitionsKey(),
    queryFn: fetchReportDefinitions,
  });
  const fields = useMemo(
    () => reportRunFilterFields(search, definitions.data),
    [search, definitions.data],
  );
  const query = reportRunQuery(search, fields);
  const source: GridSource<ReportRun> = {
    queryKey: reportRunsKey(query),
    fetchPage: (cursor, sort) => fetchReportRunsPage(query, cursor, sort),
  };
  const columns = useMemo(
    () => reportRunColumns({ built, open: (to) => void navigate(to) }),
    [built, navigate],
  );
  const [columnState, setColumnState] = useState<GridColumnState>(DEFAULT_COLUMNS);
  const [total, setTotal] = useState<number | undefined>(undefined);
  const countLabel = (count: number, formatted: string) =>
    t("reports.runs.count", { count, formatted });

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <DataGrid<ReportRun>
        name="runs"
        title={t("reports.tabs.runs")}
        errorTitle={t("reports.runs.loadError")}
        countLabel={countLabel}
        columns={columns}
        source={source}
        rowKey={(run) => run.id}
        rowLabel={(run) => run.report_run_no}
        rowHref={(run) => reportRunRoute(run.id)}
        testIdPrefix="SF-08"
        rowTestKey={(run) => run.report_run_no}
        columnState={columnState}
        defaultColumnState={DEFAULT_COLUMNS}
        onColumnStateChange={setColumnState}
        onTotalChange={(next) => setTotal(next?.count)}
        viewSelector={
          <SavedViewSelector
            screenCode={REPORT_RUNS_SCREEN_CODE}
            membershipId={me.active_membership_id}
            defaultLabel={t("reports.runs.view.default")}
            columnState={columnState}
            defaultColumnState={DEFAULT_COLUMNS}
            onApplyColumns={setColumnState}
            testId="SF-08-saved-view"
          />
        }
        filterBar={
          <FilterBar
            fields={fields}
            resultCount={total}
            resultLabel={(count) => countLabel(count, String(count))}
            testId="SF-08-filter-bar"
          />
        }
        emptyState={
          <div data-testid="SF-08-empty-runs">
            <EmptyState
              title={t("reports.runs.empty.title")}
              description={t("reports.runs.empty.description")}
            />
          </div>
        }
        noResults={
          <EmptyState
            title={t("reports.runs.noResults")}
            description=""
            action={{
              label: t("reports.runs.clearFilters"),
              onAction: () =>
                void navigate({ search: withFilters(search, "", []) }, { replace: true }),
            }}
          />
        }
      />
    </div>
  );
}

export function ReportRuns() {
  const me = useMe();
  const access = useAccess();
  let body;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={t("reports.tabs.runs")} shape="rows" count={10} />;
  } else if (!mayReadReportRuns(access)) {
    body = <ReportRunsAccessLimited />;
  } else {
    body = <ReportRunsPage me={me.data} />;
  }
  return (
    <div data-testid="SF-08-page" className="flex h-full min-h-0 flex-col">
      <ReportsHeader />
      <div className="flex min-h-0 flex-1 flex-col gap-4 px-[var(--gutter)] py-[var(--panel-pad)]">
        {body}
      </div>
    </div>
  );
}
