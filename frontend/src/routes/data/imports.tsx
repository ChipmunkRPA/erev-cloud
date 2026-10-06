// SF-10 Imports list (SCREENS §12.1; §0.3 SCR-IA-02; §0.4 RT-42; §0.7 SCR-PERM-01, SCR-ST-04, SCR-ST-05;
// §0.8 E-40, E-05; DESIGN_SYSTEM DS-CMP-07, DS-CMP-10, DS-CMP-13, DS-CMP-19, DS-CMP-23, DS-FMT-17,
// DS-FMT-21, DS-FMT-23; 04 API-R-43 `GET /imports`, API-R-09 `GET /approvals/{id}`; BUILD_SPEC DIN-15).
// The Data frame (breadcrumb, the route tabs of built Data pages, SCR-IA-02) and the `h1` "Imports" with
// "<n> imports" from `X-Erev-Total-Count`, "Download templates" and, once SF-10:new is built, "New import"
// (XR-14); then the DataGrid "Imports" with the saved-view selector and the Template, Status and Uploaded
// from chips. An `INVALID` import shows "Error" with its caption (PRD SM-05). [J] L6-4-Q-8: the `h1` names
// the page, as §12.1 and the §12.2 and §13.2 wireframes do, and the breadcrumb carries the area "Data"
// that SCR-IA-02 names. L6-4-Q-9: `GET /imports` answers `q` with 422, so the bar holds chips only, and no
// binding tells a legacy preset tenant (SCR-LTH-O3), so the native empty state renders.
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useMemo, useState } from "react";
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
import {
  FILTER_PREFIX,
  type FilterField,
  parseFilters,
  withFilters,
} from "../../components/filter-bar/filters";
import { type RouteTab, RouteTabs } from "../../components/record/Tabs";
import { Button } from "../../components/ui/Button";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { approvalKey, fetchApproval } from "../../lib/api/queries/approvals";
import {
  fetchImportTemplates,
  type ImportTemplate,
  importTemplatesKey,
  templateName,
} from "../../lib/api/queries/import-templates";
import {
  EXCEPTIONS_ROUTE,
  fetchImportsPage,
  IMPORT_DETAIL_ROUTE,
  IMPORT_READ_PERMISSION,
  IMPORT_STATUSES,
  IMPORT_UPLOAD_PERMISSION,
  type ImportItem,
  type ImportListQuery,
  importName,
  importRoute,
  IMPORTS_ROUTE,
  IMPORTS_SCREEN_CODE,
  importsKey,
  type ImportStatus,
  NEW_IMPORT_ROUTE,
  TEMPLATES_ROUTE,
} from "../../lib/api/queries/imports";
import { type Me, useMe } from "../../lib/api/queries/me";
import { dayStartInstant, formatNumber, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { decodeValue, rawParams } from "../../lib/url/params";
import { useBuiltPaths } from "../settings/index";

export interface DataTab {
  readonly screen: string;
  readonly path: string;
  /** The message key under `data.tabs`. */
  readonly key: string;
  /** Any-of read permissions (SCREENS §0.4). */
  readonly permissions: readonly string[];
}

/** SCREENS §0.3 SCR-IA-02 Data route tabs, in order, with the RT-42 to RT-53 read permissions. */
export const DATA_TABS: readonly DataTab[] = [
  { screen: "SF-10", path: IMPORTS_ROUTE, key: "imports", permissions: ["contract.read"] },
  {
    screen: "SF-11",
    path: EXCEPTIONS_ROUTE,
    key: "exceptions",
    permissions: ["contract.read"],
  },
  {
    screen: "SF-16",
    path: "/data/integrations",
    key: "integrations",
    permissions: ["integration.manage"],
  },
  {
    screen: "SF-19",
    path: "/data/migrations",
    key: "migrations",
    permissions: ["migration.run"],
  },
  {
    screen: "SF-10:templates",
    path: TEMPLATES_ROUTE,
    key: "templates",
    permissions: ["contract.read"],
  },
];

/** Data tabs whose pages have child routes: the tab stays the current page on them. */
const NESTED_TABS: ReadonlySet<string> = new Set([
  IMPORTS_ROUTE,
  EXCEPTIONS_ROUTE,
  "/data/integrations",
]);

/** SCREENS §12.1 columns hidden by default. */
export const HIDDEN_BY_DEFAULT: readonly string[] = ["import_no", "sha256", "aggregated"];

/** Status options whose chip word several E-40 literals share name their step (the rest use the chip). */
const RUNNING_LABELS: Readonly<Partial<Record<ImportStatus, string>>> = {
  VALIDATING: "data.imports.status.VALIDATING",
  VALIDATED: "data.imports.status.VALIDATED",
  DIFFING: "data.imports.status.DIFFING",
  COMMITTING: "data.imports.status.COMMITTING",
};

export interface DataCrumb {
  readonly label: string;
  readonly to: string;
}

export interface DataPageHeaderProps {
  readonly title: string;
  readonly count?: string | undefined;
  /** Status and outline chips beside the `h1` of a record page (SCREENS §14.2 connection header). */
  readonly chips?: ReactNode;
  readonly actions?: ReactNode;
  /** Crumbs between "Data" and the current page, for example "Imports" on SF-10:detail. */
  readonly crumbs?: readonly DataCrumb[];
  /** The current crumb when it differs from the `h1`, for example the file name (SCREENS §12.2). */
  readonly current?: string | undefined;
  /** The meta row under the `h1`. */
  readonly meta?: ReactNode;
}

/** SCR-IA-02 Data frame: breadcrumb, the route tabs of built pages the user may read (XR-14), `h1`. */
export function DataPageHeader({
  title,
  count,
  chips,
  actions,
  crumbs = [],
  current,
  meta,
}: DataPageHeaderProps) {
  const built = useBuiltPaths();
  const access = useAccess();
  const tabs: RouteTab[] = DATA_TABS.filter(
    (tab) =>
      built.has(tab.path) && tab.permissions.some((permission) => access.holdsAnywhere(permission)),
  ).map((tab) => ({
    id: tab.screen,
    label: t(`data.tabs.${tab.key}`),
    to: tab.path,
    // The Imports tab stays current on SF-10:new and SF-10:detail (SCREENS §12.2 wireframe), the
    // Exceptions tab on SF-11:item (§13.2 wireframe) and the Integrations tab on SF-16:connection and
    // SF-16:sync-run (§14.2 wireframe).
    end: !NESTED_TABS.has(tab.path),
  }));
  return (
    <header className="flex flex-col gap-3">
      <nav aria-label={t("common.record.breadcrumb")}>
        <ol className="flex flex-wrap items-center gap-1.5 text-body-sm text-fg-3">
          {[{ label: t("data.title"), to: IMPORTS_ROUTE }, ...crumbs].map((crumb) => (
            <li key={`${crumb.label}:${crumb.to}`} className="flex items-center gap-1.5">
              <Link to={crumb.to} className="hover:text-fg-1 hover:underline">
                {crumb.label}
              </Link>
              <span aria-hidden="true">/</span>
            </li>
          ))}
          <li aria-current="page" className="min-w-0 truncate">
            {current ?? title}
          </li>
        </ol>
      </nav>
      {tabs.length === 0 ? null : <RouteTabs label={t("data.tabs.label")} tabs={tabs} />}
      <div className="flex flex-wrap items-center gap-3">
        <h1 tabIndex={-1} className="text-title-lg text-fg-1">
          {title}
        </h1>
        {count === undefined ? null : <span className="num text-body text-fg-3">{count}</span>}
        {chips === undefined ? null : <span className="flex items-center gap-1.5">{chips}</span>}
        <span className="flex-1" />
        {actions}
      </div>
      {meta}
    </header>
  );
}

/** SCR-PERM-01 for `contract.read`. */
export function DataAccessLimited({ area }: { readonly area: string }) {
  return (
    <EmptyState
      title={t("settings.access.title", { area })}
      description={t("settings.access.description", {
        permission: t("contracts.access.permission"),
      })}
    />
  );
}

/** DS-FMT-23 middle ellipsis of a digest. */
export function digestText(value: string): string {
  return value.length <= 20 ? value : `${value.slice(0, 8)}…${value.slice(-8)}`;
}

function mono(text: string) {
  return <span className="font-mono text-mono text-fg-2">{text}</span>;
}

/** The values of the URL chip `f.<field>`, read before the field's options have loaded. */
function urlChipValues(search: string, field: string): readonly string[] {
  const param = rawParams(search).find((item) => item.name === `${FILTER_PREFIX}${field}`);
  const colon = param?.value.indexOf(":") ?? -1;
  if (param === undefined || colon < 0) {
    return [];
  }
  return param.value
    .slice(colon + 1)
    .split(",")
    .map((value) => decodeValue(value));
}

function statusLabel(status: ImportStatus): string {
  const key = RUNNING_LABELS[status];
  return key === undefined ? (chipFor("E-40", status)?.status ?? status) : t(key);
}

/** SCREENS §12.1 filters: Template → `template_code`, Status → `status`, Uploaded from → `created_from`. */
export function importFilterFields(
  search: string,
  templates: readonly ImportTemplate[] | undefined,
): readonly FilterField[] {
  return [
    {
      name: "template",
      label: t("data.imports.filter.template"),
      kind: "enum",
      operators: ["is"],
      options:
        templates === undefined
          ? urlChipValues(search, "template").map((value) => ({ value, label: value }))
          : templates.map((template) => ({ value: template.code, label: templateName(template) })),
      optionsLoading: templates === undefined,
    },
    {
      name: "status",
      label: t("data.imports.filter.status"),
      kind: "enum",
      operators: ["is", "in"],
      options: IMPORT_STATUSES.map((status) => ({ value: status, label: statusLabel(status) })),
    },
    {
      name: "uploaded_from",
      label: t("data.imports.filter.uploadedFrom"),
      kind: "date",
      operators: ["gte"],
    },
  ];
}

/** The API query of the URL chips. */
export function importQuery(search: string, fields: readonly FilterField[]): ImportListQuery {
  const parsed = parseFilters(search, fields);
  const chip = (name: string) => parsed.filters.find((filter) => filter.field === name);
  const from = chip("uploaded_from")?.values[0] ?? null;
  return {
    status: chip("status")?.values ?? [],
    templateCode: chip("template")?.values[0] ?? null,
    createdFrom: from === null ? null : dayStartInstant(from),
  };
}

/** SCREENS §12.1 column 3: the E-40 chip, with the caption of an `INVALID` import (SM-05). */
export function ImportStatusCell({ status }: { readonly status: ImportStatus }) {
  const chip = chipFor("E-40", status);
  return chip === null ? null : <StatusChip status={chip.status} caption={chip.caption} />;
}

/** SCREENS §12.1 column 9: the E-05 chip of the import's approval request. */
function ApprovalCell({ requestId }: { readonly requestId: string | null }) {
  const approval = useQuery({
    queryKey: approvalKey(requestId ?? ""),
    queryFn: () => fetchApproval(requestId ?? ""),
    enabled: requestId !== null,
    retry: false,
  });
  if (requestId === null || approval.isError) {
    return NO_VALUE;
  }
  const chip = approval.data === undefined ? null : chipFor("E-05", approval.data.status);
  return chip === null ? null : <StatusChip status={chip.status} />;
}

function count(value: number | null): string | null {
  return value === null ? null : String(value);
}

/** SCREENS §12.1 columns. */
export function importColumns(built: ReadonlySet<string>): readonly GridColumn<ImportItem>[] {
  const detail = built.has(IMPORT_DETAIL_ROUTE);
  return [
    {
      id: "file",
      header: t("data.imports.column.import"),
      kind: "identifier",
      value: (item) => importName(item),
      href: detail ? (item) => importRoute(item.id) : undefined,
      width: 304,
    },
    {
      id: "template",
      header: t("data.imports.column.template"),
      kind: "text",
      value: (item) => templateName(item.template),
      width: 224,
    },
    {
      id: "status",
      header: t("data.imports.column.status"),
      kind: "status",
      value: (item) => item.status,
      render: (item) => <ImportStatusCell status={item.status} />,
      width: 304,
    },
    {
      id: "rows",
      header: t("data.imports.column.rows"),
      kind: "number",
      numberKind: "count",
      value: (item) => count(item.counts.rows),
      width: 96,
    },
    {
      id: "errors",
      header: t("data.imports.column.errors"),
      kind: "number",
      numberKind: "count",
      value: (item) => count(item.counts.errors),
      width: 96,
    },
    {
      id: "warnings",
      header: t("data.imports.column.warnings"),
      kind: "number",
      numberKind: "count",
      value: (item) => count(item.counts.warnings),
      width: 104,
    },
    {
      id: "uploaded_by",
      header: t("data.imports.column.uploadedBy"),
      kind: "user",
      value: (item) => item.created_by.display_name,
    },
    {
      id: "created_at",
      header: t("data.imports.column.uploadedAt"),
      kind: "timestamp",
      value: (item) => item.created_at,
      sortKey: "created_at",
    },
    {
      id: "approval",
      header: t("data.imports.column.approval"),
      kind: "status",
      value: (item) => item.approval_request_id,
      render: (item) => <ApprovalCell requestId={item.approval_request_id} />,
      width: 160,
    },
    {
      id: "committed_at",
      header: t("data.imports.column.committedAt"),
      kind: "timestamp",
      value: (item) => item.committed_at,
    },
    {
      id: "import_no",
      header: t("data.imports.column.importNo"),
      kind: "text",
      value: (item) => item.import_no,
      render: (item) => mono(item.import_no),
      sortKey: "import_no",
      width: 144,
    },
    {
      id: "sha256",
      header: t("data.imports.column.sha256"),
      kind: "text",
      value: (item) => item.file.sha256,
      render: (item) => mono(digestText(item.file.sha256)),
      width: 200,
    },
    {
      id: "aggregated",
      header: t("data.imports.column.aggregated"),
      kind: "number",
      numberKind: "count",
      value: (item) => String(item.counts.aggregated),
      width: 136,
    },
  ];
}

export function ImportsList() {
  const me = useMe();
  const access = useAccess();
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={t("data.imports.title")} shape="rows" count={10} />;
  } else if (!access.holdsAnywhere(IMPORT_READ_PERMISSION)) {
    body = <DataAccessLimited area={t("data.access.imports")} />;
  } else {
    return <ImportsPage me={me.data} />;
  }
  return (
    <div data-testid="SF-10-page" className="flex flex-col gap-4">
      <DataPageHeader title={t("data.imports.title")} />
      {body}
    </div>
  );
}

function ImportsPage({ me }: { readonly me: Me }) {
  const access = useAccess();
  const location = useLocation();
  const navigate = useNavigate();
  const built = useBuiltPaths();
  const search = location.search;
  const templates = useQuery({ queryKey: importTemplatesKey(), queryFn: fetchImportTemplates });
  const fields = useMemo(
    () => importFilterFields(search, templates.data),
    [search, templates.data],
  );
  const query = importQuery(search, fields);
  const source: GridSource<ImportItem> = {
    queryKey: importsKey(query),
    fetchPage: (cursor, sort) => fetchImportsPage(query, cursor, sort),
  };
  const [total, setTotal] = useState<number | undefined>(undefined);
  const columns = useMemo(() => importColumns(built), [built]);
  const defaultColumns = useMemo(() => initialColumnState(columns, HIDDEN_BY_DEFAULT), [columns]);
  const [columnState, setColumnState] = useState<GridColumnState>(defaultColumns);

  const newImport =
    built.has(NEW_IMPORT_ROUTE) && access.holdsAnywhere(IMPORT_UPLOAD_PERMISSION)
      ? { label: t("data.imports.new"), onAction: () => void navigate(NEW_IMPORT_ROUTE) }
      : undefined;
  const actions: ReactNode[] = [];
  if (built.has(TEMPLATES_ROUTE)) {
    actions.push(
      <Button key="templates" variant="secondary" onClick={() => void navigate(TEMPLATES_ROUTE)}>
        {t("data.imports.downloadTemplates")}
      </Button>,
    );
  }
  if (newImport !== undefined) {
    actions.push(
      <Button key="new" variant="primary" onClick={newImport.onAction}>
        {newImport.label}
      </Button>,
    );
  }
  const countLabel = (value: number) =>
    t("data.imports.count", { count: value, formatted: formatNumber(value, { kind: "count" }) });
  const clearFilters = () => {
    void navigate({ search: withFilters(search, "", []) }, { replace: true });
  };

  return (
    <div data-testid="SF-10-page" className="flex h-full min-h-0 flex-col gap-4">
      <DataPageHeader
        title={t("data.imports.title")}
        count={total === undefined ? undefined : countLabel(total)}
        actions={actions}
      />
      <div className="flex min-h-0 flex-1 flex-col">
        <DataGrid<ImportItem>
          name="imports"
          title={t("data.imports.title")}
          titleVisible={false}
          errorTitle={t("data.imports.loadError")}
          countLabel={(value, formatted) => t("data.imports.count", { count: value, formatted })}
          columns={columns}
          source={source}
          rowKey={(item) => item.id}
          rowLabel={importName}
          rowHref={built.has(IMPORT_DETAIL_ROUTE) ? (item) => importRoute(item.id) : undefined}
          testIdPrefix="SF-10"
          rowTestKey={importName}
          columnState={columnState}
          defaultColumnState={defaultColumns}
          onColumnStateChange={setColumnState}
          onTotalChange={(next) => setTotal(next?.count)}
          viewSelector={
            <SavedViewSelector
              screenCode={IMPORTS_SCREEN_CODE}
              membershipId={me.active_membership_id}
              defaultLabel={t("data.imports.view.default")}
              columnState={columnState}
              defaultColumnState={defaultColumns}
              onApplyColumns={setColumnState}
              testId="SF-10-saved-view"
            />
          }
          filterBar={
            <FilterBar
              fields={fields}
              resultCount={total}
              resultLabel={countLabel}
              testId="SF-10-filter-bar"
            />
          }
          emptyState={
            <div data-testid="SF-10-empty-imports">
              <EmptyState
                title={t("data.imports.empty.title")}
                description={t("data.imports.empty.description")}
                action={newImport}
              />
            </div>
          }
          noResults={
            <EmptyState
              title={t("data.imports.noResults")}
              description=""
              action={{ label: t("data.imports.clearFilters"), onAction: clearFilters }}
            />
          }
        />
      </div>
    </div>
  );
}
