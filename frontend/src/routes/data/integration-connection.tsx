// SF-16:connection Integration connection (SCREENS §14.1 to §14.9; §0.4 RT-49; §0.5 SCR-URL-13 `pane`; §0.6
// SCR-PERM-01, SCR-PERM-03; §0.7 SCR-ST-07, SCR-ST-09, SCR-ST-12; §0.8 T-INT-01, E-72; SCREENS_B §0.3
// SB-R-06, SB-R-08; DESIGN_SYSTEM DS-CMP-07, DS-CMP-10, DS-CMP-13, DS-CMP-19, DS-CMP-22, DS-CMP-24,
// DS-CMP-29, DS-FMT-17, DS-FMT-24; 04 API-R-45; REQ-INT-006, REQ-DAT-010; BR-INT-01 to BR-INT-03; BUILD_SPEC
// DIN-18). The Data frame with the connection's name as `h1`, its status, adapter and "Mock" chips,
// "Test connection", "Run sync" and "Enable" or "Disable"; the test result in the header ("Connection
// succeeded · <timestamp>" as a status, "Connection failed · <timestamp>: <detail>" as an alert when a
// test has just answered); and the panel tabs Settings · Sync runs · External ids (`pane`). "Run sync"
// offers the kinds API-R-45 queues for the adapter, shows the `SYNC_RUN` job in place and ends with a
// toast that states the run's own result. The grids show what the API answers: "Reconciled" and
// "Difference" are the run's status, never a comparison made here.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";

import { openMembership } from "../../app/shell/open-workspace";
import { useShellSession } from "../../app/shell/SandboxIndicator";
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
import { JobProgress, type JobProgressJob } from "../../components/feedback/JobProgress";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import { type FilterField, parseFilters } from "../../components/filter-bar/filters";
import { NoValue } from "../../components/money/Num";
import { PanelTabs } from "../../components/record/Tabs";
import { Button } from "../../components/ui/Button";
import { Menu } from "../../components/ui/Menu";
import { chipFor, OutlineChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { isTerminal } from "../../lib/api/jobs";
import { ApiProblem } from "../../lib/api/problems";
import { currencyRegistered } from "../../lib/api/queries/approvals";
import { useAllEntities } from "../../lib/api/queries/entities";
import { EXCEPTIONS_ROUTE } from "../../lib/api/queries/imports";
import {
  type Connection,
  connectionKey,
  connectionPath,
  type ConnectionUpdate,
  controlTotals,
  type ControlTotals,
  EVERY_INTEGRATION,
  EVERY_SYNC_RUN,
  type ExternalId,
  externalIdsKey,
  fetchConnection,
  fetchExternalIdsPage,
  fetchSyncRun,
  fetchSyncRunsPage,
  INTEGRATION_MANAGE_PERMISSION,
  INTEGRATIONS_ROUTE,
  isMock,
  requestableKinds,
  secretNamespaceOf,
  SYNC_RUN_ID_HEADER,
  SYNC_RUN_KINDS,
  SYNC_RUN_STATUSES,
  SYNC_RUNS_SCREEN_CODE,
  type SyncRequest,
  type SyncRun,
  type SyncRunKind,
  syncRunRoute,
  syncRunsKey,
} from "../../lib/api/queries/integrations";
import { type Me, useMe } from "../../lib/api/queries/me";
import { rowIfMatch } from "../../lib/api/queries/tenant";
import { formatDuration, formatMoney, formatNumber, formatTimestamp } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { withParams } from "../../lib/url/params";
import { useBuiltPaths } from "../settings/index";
import { DataPageHeader } from "./imports";
import {
  adapterLabel,
  ConnectionDrawer,
  ConnectionStatusChip,
  directionLabel,
  entitiesText,
  IntegrationsAccessLimited,
  kindLabel,
  SyncStatusChip,
  TotalsChip,
  totalsStatus,
} from "./integrations";

/** SCREENS §14.7 panel tabs; the sync runs are what the page opens on. */
export const CONNECTION_PANES = ["settings", "sync-runs", "external-ids"] as const;
export type ConnectionPane = (typeof CONNECTION_PANES)[number];
const DEFAULT_PANE: ConnectionPane = "sync-runs";
const PANE_PARAM = "pane";
const PARTS_SEPARATOR = " · ";
/** SB-R-08, DB-15: GL adapters a sandbox workspace cannot enable outbound. */
const SANDBOX_REFUSED_ADAPTERS: ReadonlySet<string> = new Set(["NETSUITE", "QUICKBOOKS_ONLINE"]);
/**
 * SB-R-08, 05 SBX-08 (rev 1.116): the adapters whose test calls nothing, so a sandbox workspace may
 * test them. An adapter not named here calls out and its test is refused there.
 */
const SANDBOX_TESTED_ADAPTERS: ReadonlySet<string> = new Set(["CSV_GL"]);
/** T-INT-04 `object_type` values whose record has a screen that opens from the id. */
const EXTERNAL_ID_ROUTES: Readonly<
  Record<string, { readonly pattern: string; readonly to: (id: string) => string }>
> = {
  contract: { pattern: "/contracts/:contractId", to: (id) => `/contracts/${id}` },
  customer: {
    pattern: "/settings/customers/:customerId",
    to: (id) => `/settings/customers/${id}`,
  },
  product: { pattern: "/settings/products/:productId", to: (id) => `/settings/products/${id}` },
};

export function connectionPaneOf(value: string | null): ConnectionPane {
  return (CONNECTION_PANES as readonly string[]).includes(value ?? "")
    ? (value as ConnectionPane)
    : DEFAULT_PANE;
}

/**
 * SCREENS §14.3 "Source totals" and "Loaded totals": the record count and the amount of each currency,
 * for example "3 records · USD 120,000.00"; null when the run recorded no totals.
 */
export function totalsText(totals: ControlTotals | null): string | null {
  if (totals === null) {
    return null;
  }
  return [
    t("data.integrations.records", {
      count: totals.count,
      formatted: formatNumber(totals.count, { kind: "count" }),
    }),
    ...totals.amounts.map(({ currency, amount }) =>
      // A currency the viewer's reads did not register keeps its recorded digits (DS-FMT-03).
      currencyRegistered(currency)
        ? formatMoney(amount, currency, { variant: "inline" })
        : `${currency} ${amount}`,
    ),
  ].join(PARTS_SEPARATOR);
}

function mono(text: string): ReactNode {
  return <span className="truncate font-mono text-mono-sm text-fg-1">{text}</span>;
}

/** SCREENS §14.3 sync runs grid. */
export function syncRunColumns(
  connectionId: string,
  exceptionsBuilt: boolean,
): readonly GridColumn<SyncRun>[] {
  const totals = (value: SyncRun["source_totals"]) => totalsText(controlTotals(value));
  return [
    {
      id: "started_at",
      header: t("data.integrations.runs.column.started"),
      kind: "identifier",
      value: (run) => run.started_at,
      href: (run) => syncRunRoute(connectionId, run.id),
      render: (run) => (
        <Link
          to={syncRunRoute(connectionId, run.id)}
          tabIndex={-1}
          data-volatile=""
          className="num truncate text-accent-fg hover:text-accent-fg-hover hover:underline"
        >
          {run.started_at === null ? (
            t("data.integrations.runs.notStarted")
          ) : (
            <time dateTime={run.started_at}>{formatTimestamp(run.started_at)}</time>
          )}
        </Link>
      ),
      width: 192,
    },
    {
      id: "kind",
      header: t("data.integrations.runs.column.kind"),
      kind: "text",
      value: (run) => kindLabel(run.kind),
      width: 192,
    },
    {
      id: "status",
      header: t("data.integrations.runs.column.status"),
      kind: "status",
      value: (run) => run.status,
      render: (run) => <SyncStatusChip status={run.status} />,
      width: 128,
    },
    {
      id: "record_count",
      header: t("data.integrations.runs.column.records"),
      kind: "number",
      numberKind: "count",
      value: (run) => String(run.record_count),
      width: 104,
    },
    {
      id: "source_totals",
      header: t("data.integrations.runs.column.sourceTotals"),
      kind: "text",
      value: (run) => totals(run.source_totals),
      width: 256,
    },
    {
      id: "loaded_totals",
      header: t("data.integrations.runs.column.loadedTotals"),
      kind: "text",
      value: (run) => totals(run.loaded_totals),
      width: 256,
    },
    {
      id: "result",
      header: t("data.integrations.runs.column.result"),
      kind: "status",
      value: (run) => totalsStatus(run),
      render: (run) => <TotalsChip status={totalsStatus(run)} />,
      width: 128,
    },
    {
      id: "exception_count",
      header: t("data.integrations.runs.column.exceptions"),
      kind: "number",
      numberKind: "count",
      value: (run) => String(run.exception_count),
      render: (run) =>
        run.exception_count > 0 && exceptionsBuilt ? (
          <Link
            to={`${EXCEPTIONS_ROUTE}?f.source=is:SYNC`}
            tabIndex={-1}
            className="num text-accent-fg hover:text-accent-fg-hover hover:underline"
          >
            {formatNumber(run.exception_count, { kind: "count" })}
          </Link>
        ) : (
          <span className="num">{formatNumber(run.exception_count, { kind: "count" })}</span>
        ),
      width: 120,
    },
    {
      id: "duration",
      header: t("data.integrations.runs.column.duration"),
      kind: "number",
      value: (run) => (run.duration_seconds === null ? null : String(run.duration_seconds)),
      render: (run) =>
        run.duration_seconds === null ? (
          <NoValue />
        ) : (
          <span className="num">{formatDuration(run.duration_seconds * 1_000)}</span>
        ),
      width: 112,
    },
  ];
}

const RUN_COLUMNS_DEFAULT: GridColumnState = initialColumnState(syncRunColumns("", false));

/** T-INT-04 object type in words: `gl_account` reads "Gl account". */
function objectTypeWords(objectType: string): string {
  const key = `data.integrations.externalIds.objectType.${objectType}`;
  return t(key);
}

export function externalIdColumns(built: ReadonlySet<string>): readonly GridColumn<ExternalId>[] {
  const route = (item: ExternalId): string | null => {
    const target = EXTERNAL_ID_ROUTES[item.object_type];
    return target !== undefined && built.has(target.pattern) ? target.to(item.internal_id) : null;
  };
  // API-C-09 sort keys: GET /api/v1/external-ids
  return [
    {
      id: "external_id",
      header: t("data.integrations.externalIds.column.externalId"),
      kind: "text",
      value: (item) => item.external_id,
      render: (item) => mono(item.external_id),
      sortKey: "external_id",
      width: 256,
    },
    {
      id: "object",
      header: t("data.integrations.externalIds.column.record"),
      kind: "text",
      value: (item) => objectTypeWords(item.object_type),
      render: (item) => {
        const to = route(item);
        return to === null ? (
          <span className="truncate">{objectTypeWords(item.object_type)}</span>
        ) : (
          <Link
            to={to}
            tabIndex={-1}
            className="truncate text-accent-fg hover:text-accent-fg-hover hover:underline"
          >
            {objectTypeWords(item.object_type)}
          </Link>
        );
      },
      width: 176,
    },
    {
      id: "external_version",
      header: t("data.integrations.externalIds.column.version"),
      kind: "text",
      value: (item) => item.external_version,
      render: (item) =>
        item.external_version === null ? <NoValue /> : mono(item.external_version),
      width: 152,
    },
    {
      id: "valid_from",
      header: t("data.integrations.externalIds.column.validFrom"),
      kind: "timestamp",
      value: (item) => item.valid_from,
      // An instant with the cell padding is 186 px; the kit's default is 176.
      width: 192,
    },
    {
      id: "valid_to",
      header: t("data.integrations.externalIds.column.validTo"),
      kind: "timestamp",
      value: (item) => item.valid_to,
      width: 192,
    },
    {
      id: "created_at",
      header: t("data.integrations.externalIds.column.linked"),
      kind: "timestamp",
      value: (item) => item.created_at,
      sortKey: "created_at",
      width: 192,
    },
  ];
}

export function IntegrationConnection() {
  const { connectionId = "" } = useParams();
  const me = useMe();
  const access = useAccess();
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={t("data.integrations.title")} shape="rows" count={6} />;
  } else if (!access.holdsAnywhere(INTEGRATION_MANAGE_PERMISSION)) {
    body = <IntegrationsAccessLimited />;
  } else {
    return <ConnectionLoader key={connectionId} connectionId={connectionId} me={me.data} />;
  }
  return (
    <div data-testid="SF-16-page" className="flex flex-col gap-4">
      <DataPageHeader title={t("data.integrations.title")} />
      {body}
    </div>
  );
}

interface LoaderProps {
  readonly connectionId: string;
  readonly me: Me;
}

const crumbs = () => [{ label: t("data.integrations.title"), to: INTEGRATIONS_ROUTE }];

function ConnectionLoader({ connectionId, me }: LoaderProps) {
  const navigate = useNavigate();
  const connection = useQuery({
    queryKey: connectionKey(connectionId),
    queryFn: () => fetchConnection(connectionId),
    retry: (count, error) => !(error instanceof ApiProblem && error.status === 404) && count < 1,
  });
  if (connection.data !== undefined) {
    return <ConnectionPage connection={connection.data} me={me} />;
  }
  let body: ReactNode;
  if (connection.error instanceof ApiProblem && connection.error.status === 404) {
    // SCR-ST-07: an unknown id, or a connection outside the viewer's access.
    body = (
      <EmptyState
        title={t("data.integrations.connection.notFound.title")}
        description={t("data.integrations.connection.notFound.description")}
        action={{
          label: t("data.integrations.connection.notFound.action"),
          onAction: () => void navigate(INTEGRATIONS_ROUTE),
        }}
      />
    );
  } else if (connection.isError) {
    body = (
      <Banner
        tone="negative"
        title={t("data.integrations.loadError")}
        actions={
          <Button variant="link" onClick={() => void connection.refetch()}>
            {t("data.integrations.retry")}
          </Button>
        }
      >
        {connection.error instanceof ApiProblem ? connection.error.title : connection.error.message}
      </Banner>
    );
  } else {
    body = <Skeleton region={t("data.integrations.connection.region")} shape="rows" count={6} />;
  }
  return (
    <div data-testid="SF-16-page" className="flex flex-col gap-4">
      <DataPageHeader title={t("data.integrations.connection.region")} crumbs={crumbs()} />
      {body}
    </div>
  );
}

interface TestResultProps {
  readonly connection: Connection;
  /** The result answered a test made on this page, so it is announced (DS-CMP-29). */
  readonly live: boolean;
}

/** SCREENS §14.4 "Test connection" result and §14.6 "Never tested". */
function TestResult({ connection, live }: TestResultProps) {
  if (connection.last_test_result === null || connection.last_test_at === null) {
    // SCREENS §14.6 "Never tested": the header's primary action is "Test connection".
    return <p className="text-body-sm text-fg-2">{t("data.integrations.test.never")}</p>;
  }
  const timestamp = formatTimestamp(connection.last_test_at);
  const succeeded = connection.last_test_result === "SUCCESS";
  let title: string;
  if (succeeded) {
    title = t("data.integrations.test.succeeded", { timestamp });
  } else if (connection.last_test_detail === null || connection.last_test_detail === "") {
    title = t("data.integrations.test.failedNoDetail", { timestamp });
  } else {
    title = t("data.integrations.test.failed", {
      timestamp,
      detail: connection.last_test_detail,
    });
  }
  return (
    <div data-testid="SF-16-banner-test">
      <Banner
        tone={succeeded ? "positive" : "negative"}
        announce={live ? "live" : "static"}
        title={title}
      />
    </div>
  );
}

interface PageProps {
  readonly connection: Connection;
  readonly me: Me;
}

function ConnectionPage({ connection, me }: PageProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const built = useBuiltPaths();
  const search = location.search;
  const pane = connectionPaneOf(new URLSearchParams(search).get(PANE_PARAM));
  // The workspace is the session's: a sandbox copy holds its source's membership id.
  const open = openMembership(me, useShellSession());
  const namespace = secretNamespaceOf(open);
  const [editing, setEditing] = useState(false);
  const store = (next: Connection) => {
    queryClient.setQueryData(connectionKey(connection.id), next);
  };

  // "Test connection": 200 with the connection and its `last_test_*`.
  const test = useCommand<Connection>({
    method: "POST",
    path: `${connectionPath(connection.id)}/test`,
    invalidates: [EVERY_INTEGRATION, EVERY_SYNC_RUN],
  });
  const [testedAt, setTestedAt] = useState<string | null>(null);
  const runTest = async () => {
    const outcome = await test.submit();
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      setTestedAt(outcome.data.last_test_at);
      store(outcome.data);
    } else if (outcome.kind === "failed") {
      toast.show({ tone: "negative", message: outcome.problem.title });
    } else if (outcome.kind === "network-error") {
      toast.show({ tone: "negative", message: t("data.integrations.notSent") });
    }
  };

  // "Run sync": 202 with the `SYNC_RUN` job and the queued run.
  const sync = useCommand({
    method: "POST",
    path: `${connectionPath(connection.id)}/sync`,
    invalidates: [EVERY_INTEGRATION, EVERY_SYNC_RUN],
  });
  // The run the last 202 queued, and the kind asked for: "Retry" asks for the same kind again.
  const queuedRun = useRef<string | null>(null);
  const reported = useRef<string | null>(null);
  const [requestedKind, setRequestedKind] = useState<SyncRunKind | null>(null);
  const runSync = async (kind: SyncRunKind) => {
    setRequestedKind(kind);
    const outcome = await sync.submit({ kind } satisfies SyncRequest);
    if (outcome.kind === "accepted") {
      queuedRun.current = outcome.response.headers.get(SYNC_RUN_ID_HEADER);
    } else if (outcome.kind === "failed") {
      // The API's own reason where it gives one ("The connection is disabled."), else the title.
      const reason = outcome.problem.errors.find((error) => error.message !== "")?.message;
      toast.show({ tone: "negative", message: reason ?? outcome.problem.title });
    } else if (outcome.kind === "network-error") {
      toast.show({ tone: "negative", message: t("data.integrations.notSent") });
    }
  };
  const syncJob = sync.job;
  const syncing: JobProgressJob | null =
    sync.jobId === null
      ? null
      : (syncJob ?? {
          id: sync.jobId,
          state: "QUEUED",
          progress: { done: 0, total: null },
          started_at: null,
          problem: null,
        });
  useEffect(() => {
    if (syncJob === undefined || !isTerminal(syncJob) || reported.current === syncJob.id) {
      return;
    }
    reported.current = syncJob.id;
    const runId = queuedRun.current;
    if (runId === null || syncJob.state === "CANCELLED") {
      return;
    }
    // The toast states the run's own result (E-72), whatever state the job ended in.
    void fetchSyncRun(runId).then((finished) => {
      const view = {
        label: t("data.integrations.sync.view"),
        onAction: () => void navigate(syncRunRoute(connection.id, runId)),
      };
      if (finished.status === "SUCCEEDED") {
        toast.show({
          tone: "positive",
          message: t("data.integrations.sync.done", {
            count: finished.record_count,
            formatted: formatNumber(finished.record_count, { kind: "count" }),
          }),
          action: view,
        });
      } else if (finished.status === "CONTROL_TOTAL_MISMATCH") {
        toast.show({
          tone: "warning",
          message: t("data.integrations.sync.difference"),
          action: view,
        });
      } else if (finished.status === "FAILED") {
        toast.show({ tone: "negative", message: t("data.integrations.sync.failed"), action: view });
      }
    });
  }, [syncJob, toast, navigate, connection.id]);
  const syncRunning = sync.pending || (sync.jobId !== null && !isTerminal(syncJob));
  const jobShown =
    syncing !== null &&
    syncing.state !== "SUCCEEDED" &&
    syncing.state !== "SUCCEEDED_WITH_EXCEPTIONS";

  // "Enable" and "Disable": PATCH `status` with the row version.
  const status = useCommand<Connection>({
    method: "PATCH",
    path: connectionPath(connection.id),
    invalidates: [EVERY_INTEGRATION],
  });
  const active = connection.status === "ACTIVE";
  const setStatus = async () => {
    const next = active ? "DISABLED" : "ACTIVE";
    const outcome = await status.submit({ status: next } satisfies ConnectionUpdate, {
      ifMatch: rowIfMatch(connection.row_version),
    });
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      store(outcome.data);
      toast.show({
        tone: "positive",
        message: t(active ? "data.integrations.disabled" : "data.integrations.enabled", {
          name: connection.name,
        }),
      });
    } else if (outcome.kind === "failed" && outcome.problem.status !== 412) {
      toast.show({
        tone: "negative",
        message: outcome.problem.detail ?? outcome.problem.title,
      });
    } else if (outcome.kind === "network-error") {
      toast.show({ tone: "negative", message: t("data.integrations.notSent") });
    }
  };
  const tenantKind = open?.tenant.kind;
  // SB-R-08 (DB-15): a sandbox workspace cannot enable an outbound GL adapter other than CSV GL export.
  const sandboxRefused =
    !active &&
    tenantKind === "sandbox" &&
    SANDBOX_REFUSED_ADAPTERS.has(connection.adapter) &&
    connection.direction !== "INBOUND";
  // SB-R-08 (05 SBX-08 rev 1.116): a sandbox reaches no external system, a probe included; the API
  // answers 403 `sandbox-restricted` to the test of every adapter that calls out.
  const sandboxUntested =
    tenantKind === "sandbox" && !SANDBOX_TESTED_ADAPTERS.has(connection.adapter);

  const kinds = requestableKinds(connection);
  const setPane = (next: string) => {
    void navigate(
      { search: withParams(search, { [PANE_PARAM]: next === DEFAULT_PANE ? null : next }) },
      { replace: true },
    );
  };

  const actions = (
    <>
      <Button
        variant="primary"
        loading={test.pending}
        disabledReason={sandboxUntested ? t("data.integrations.test.sandboxReason") : undefined}
        onClick={() => void runTest()}
      >
        {t("data.integrations.test")}
      </Button>
      {kinds.length === 0 ? null : active ? (
        <Menu
          label={t("data.integrations.runSync")}
          align="end"
          items={kinds.map((kind) => ({
            id: kind,
            label: kindLabel(kind),
            onSelect: () => void runSync(kind),
          }))}
        />
      ) : (
        // SCR-PERM-03: the state, not a permission, holds the command back.
        <Button variant="secondary" disabledReason={t("data.integrations.sync.disabledReason")}>
          {t("data.integrations.runSync")}
        </Button>
      )}
      <Button
        variant="secondary"
        loading={status.pending}
        disabledReason={sandboxRefused ? t("data.integrations.sandboxReason") : undefined}
        onClick={() => void setStatus()}
      >
        {t(active ? "data.integrations.disable" : "data.integrations.enable")}
      </Button>
    </>
  );

  return (
    <div data-testid="SF-16-page" className="flex flex-col gap-4">
      <DataPageHeader
        title={connection.name}
        crumbs={crumbs()}
        chips={
          <>
            <ConnectionStatusChip status={connection.status} />
            <OutlineChip label={adapterLabel(connection.adapter)} />
            {isMock(connection) ? <OutlineChip label={t("data.integrations.mock")} /> : null}
          </>
        }
        actions={actions}
        meta={
          <div className="flex flex-col gap-2">
            {status.banner === null ? null : (
              <Banner tone="warning" announce="live" title={status.banner} />
            )}
            <TestResult
              connection={connection}
              live={testedAt !== null && testedAt === connection.last_test_at}
            />
            {jobShown && syncing !== null ? (
              <JobProgress
                label={t("data.integrations.syncing", { name: connection.name })}
                job={syncing}
                unit={t("data.integrations.recordsUnit")}
                onRetry={requestedKind === null ? undefined : () => void runSync(requestedKind)}
              />
            ) : null}
            {syncRunning && !jobShown ? (
              <p role="status" className="text-body-sm text-fg-2">
                {t("data.integrations.syncing", { name: connection.name })}
              </p>
            ) : null}
          </div>
        }
      />
      <PanelTabs
        label={t("data.integrations.connection.panes")}
        tabs={CONNECTION_PANES.map((id) => ({ id, label: t(`data.integrations.pane.${id}`) }))}
        selectedId={pane}
        onChange={setPane}
      >
        {pane === "settings" ? (
          <SettingsPane connection={connection} onEdit={() => setEditing(true)} />
        ) : pane === "external-ids" ? (
          <ExternalIdsPane connectionId={connection.id} built={built} />
        ) : (
          <SyncRunsPane connection={connection} me={me} built={built} />
        )}
      </PanelTabs>
      {editing && namespace !== null ? (
        <ConnectionDrawer
          connection={connection}
          namespace={namespace}
          onClose={() => setEditing(false)}
          onSaved={(saved) => {
            setEditing(false);
            store(saved);
            toast.show({
              tone: "positive",
              message: t("data.integrations.saved", { name: saved.name }),
            });
          }}
        />
      ) : null}
    </div>
  );
}

function Definition({ term, children }: { readonly term: string; readonly children: ReactNode }) {
  return (
    <>
      <dt className="text-fg-3">{term}</dt>
      <dd className="min-w-0 break-words text-fg-1">{children}</dd>
    </>
  );
}

interface SettingsPaneProps {
  readonly connection: Connection;
  readonly onEdit: () => void;
}

/** SCREENS §14.3 "Header and settings": the connection's settings and "Edit connection". */
function SettingsPane({ connection, onEdit }: SettingsPaneProps) {
  const entities = useAllEntities();
  const settings = Object.keys(connection.config).sort();
  const scope = entitiesText(connection.entity_ids, entities.data);
  return (
    <div className="flex flex-col gap-4" data-testid="SF-16-pane-settings">
      {connection.owner_membership_id === null ? (
        <Banner tone="warning" title={t("data.integrations.owner.missing")} />
      ) : null}
      <Button variant="secondary" className="self-start" onClick={onEdit}>
        {t("data.integrations.drawer.editTitle")}
      </Button>
      <dl className="grid max-w-160 grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-2 text-body-sm">
        <Definition term={t("data.integrations.drawer.adapter")}>
          {adapterLabel(connection.adapter)}
        </Definition>
        <Definition term={t("data.integrations.drawer.code")}>{mono(connection.code)}</Definition>
        <Definition term={t("data.integrations.drawer.direction")}>
          {directionLabel(connection.direction)}
        </Definition>
        <Definition term={t("data.integrations.drawer.entities")}>
          {scope === null ? <NoValue /> : scope}
        </Definition>
        <Definition term={t("data.integrations.drawer.baseUrl")}>
          {connection.base_url === null ? <NoValue /> : mono(connection.base_url)}
        </Definition>
        <Definition term={t("data.integrations.drawer.secretRef")}>
          {connection.secret_ref === null ? <NoValue /> : mono(connection.secret_ref)}
        </Definition>
        <Definition term={t("data.integrations.drawer.settings")}>
          {settings.length === 0 ? (
            <NoValue />
          ) : (
            <ul className="flex flex-col gap-1">
              {settings.map((key) => {
                const value: unknown = connection.config[key];
                return (
                  <li key={key} className="font-mono text-mono-sm">
                    {`${key} = ${typeof value === "string" ? value : JSON.stringify(value)}`}
                  </li>
                );
              })}
            </ul>
          )}
        </Definition>
        <Definition term={t("data.integrations.connection.updated")}>
          <time dateTime={connection.updated_at} className="num" data-volatile="">
            {formatTimestamp(connection.updated_at)}
          </time>
        </Definition>
      </dl>
    </div>
  );
}

interface SyncRunsPaneProps {
  readonly connection: Connection;
  readonly me: Me;
  readonly built: ReadonlySet<string>;
}

/** SCREENS §14.3 "Sync runs": `GET /sync-runs?connection=<id>&status&kind`, newest first. */
function SyncRunsPane({ connection, me, built }: SyncRunsPaneProps) {
  const location = useLocation();
  const fields: readonly FilterField[] = useMemo(
    () => [
      {
        name: "status",
        label: t("data.integrations.runs.column.status"),
        kind: "enum",
        operators: ["is", "in"],
        options: SYNC_RUN_STATUSES.map((value) => ({
          value,
          label: chipFor("E-72", value)?.status ?? value,
        })),
      },
      {
        name: "kind",
        label: t("data.integrations.runs.column.kind"),
        kind: "enum",
        operators: ["is"],
        options: SYNC_RUN_KINDS.map((value) => ({ value, label: kindLabel(value) })),
      },
    ],
    [],
  );
  const parsed = parseFilters(location.search, fields);
  const query = {
    connectionId: connection.id,
    status: parsed.filters.find((filter) => filter.field === "status")?.values ?? [],
    kind: parsed.filters.find((filter) => filter.field === "kind")?.values[0] ?? null,
  };
  const source: GridSource<SyncRun> = {
    queryKey: syncRunsKey(query),
    fetchPage: (cursor, sort) => fetchSyncRunsPage(query, cursor, sort),
  };
  const columns = useMemo(
    () => syncRunColumns(connection.id, built.has(EXCEPTIONS_ROUTE)),
    [connection.id, built],
  );
  const [columnState, setColumnState] = useState<GridColumnState>(RUN_COLUMNS_DEFAULT);
  const [total, setTotal] = useState<number | undefined>(undefined);
  const countLabel = (value: number) =>
    t("data.integrations.runs.count", {
      count: value,
      formatted: formatNumber(value, { kind: "count" }),
    });
  return (
    <div className="flex min-h-0 flex-col" data-testid="SF-16-pane-sync-runs">
      <DataGrid<SyncRun>
        name="sync-runs"
        title={t("data.integrations.runs.title")}
        errorTitle={t("data.integrations.runs.loadError")}
        countLabel={(value, formatted) =>
          t("data.integrations.runs.count", { count: value, formatted })
        }
        columns={columns}
        source={source}
        rowKey={(run) => run.id}
        rowHref={(run) => syncRunRoute(connection.id, run.id)}
        testIdPrefix="SF-16"
        rowTestKey={(run) => run.id}
        columnState={columnState}
        defaultColumnState={RUN_COLUMNS_DEFAULT}
        onColumnStateChange={setColumnState}
        onTotalChange={(next) => setTotal(next?.count)}
        viewSelector={
          <SavedViewSelector
            screenCode={SYNC_RUNS_SCREEN_CODE}
            membershipId={me.active_membership_id}
            defaultLabel={t("data.integrations.runs.view.default")}
            columnState={columnState}
            defaultColumnState={RUN_COLUMNS_DEFAULT}
            onApplyColumns={setColumnState}
            testId="SF-16-saved-view"
          />
        }
        filterBar={
          <FilterBar
            fields={fields}
            resultCount={total}
            resultLabel={countLabel}
            testId="SF-16-filter-bar"
          />
        }
        emptyState={
          <EmptyState
            title={t("data.integrations.runs.empty.title")}
            description={t("data.integrations.runs.empty.description")}
          />
        }
        noResults={<EmptyState title={t("data.integrations.runs.noResults")} description="" />}
      />
    </div>
  );
}

interface ExternalIdsPaneProps {
  readonly connectionId: string;
  readonly built: ReadonlySet<string>;
}

/** SCREENS §14.3 "External ids": `GET /external-ids?connection=<id>` (T-INT-04), newest first. */
function ExternalIdsPane({ connectionId, built }: ExternalIdsPaneProps) {
  const columns = useMemo(() => externalIdColumns(built), [built]);
  const source: GridSource<ExternalId> = {
    queryKey: externalIdsKey(connectionId),
    fetchPage: (cursor, sort) => fetchExternalIdsPage(connectionId, cursor, sort),
  };
  return (
    <div className="flex min-h-0 flex-col" data-testid="SF-16-pane-external-ids">
      <DataGrid<ExternalId>
        name="external-ids"
        title={t("data.integrations.externalIds.title")}
        errorTitle={t("data.integrations.externalIds.loadError")}
        countLabel={(value, formatted) =>
          t("data.integrations.externalIds.count", { count: value, formatted })
        }
        columns={columns}
        source={source}
        rowKey={(item) => item.id}
        testIdPrefix="SF-16"
        emptyState={
          <EmptyState
            title={t("data.integrations.externalIds.empty.title")}
            description={t("data.integrations.externalIds.empty.description")}
          />
        }
      />
    </div>
  );
}
