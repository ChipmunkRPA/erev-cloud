// SF-16:sync-run Sync run (SCREENS §14.5, §14.3, §14.9; §0.4 RT-50; §0.6 SCR-PERM-01; §0.7 SCR-ST-07; §0.8
// E-72, E-43; DESIGN_SYSTEM DS-CMP-19, DS-CMP-29, DS-FMT-17, DS-FMT-21, DS-FMT-24; 04 API-R-45 `GET
// /sync-runs/{id}`, API-R-44 `GET /exceptions?source=SYNC&sync_run_id=<id>`; T-INT-02; REQ-DAT-010;
// BR-INT-03; BUILD_SPEC DIN-18). The Data frame with the `h1` "Sync run · <connection name>" and the
// status chip; the definition list Kind, Started, Finished, Duration and the checkpoints before and
// after (collapsed); the problem banner of a run that recorded one; the static table "Control totals"
// (Records, then one row per currency) with the source and the loaded figure of each measure and the
// run's one result, "Reconciled" or "Difference" — the run's status, which the API decided and the
// screen does not work out again; and the static table "Exceptions" of the items the run raised. A run
// still queued or running is read again every two seconds.
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useId } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { NoValue } from "../../components/money/Num";
import { Button } from "../../components/ui/Button";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { JOB_POLL_INTERVAL_MS } from "../../lib/api/jobs";
import { ApiProblem, REQUEST_INSTANCE_PREFIX } from "../../lib/api/problems";
import { currencyRegistered } from "../../lib/api/queries/approvals";
import { type ExceptionItem, exceptionRoute } from "../../lib/api/queries/exceptions";
import { EXCEPTIONS_ROUTE } from "../../lib/api/queries/imports";
import {
  connectionKey,
  connectionRoute,
  type ControlTotals,
  controlTotals,
  fetchConnection,
  fetchSyncRun,
  fetchSyncRunExceptions,
  INTEGRATION_MANAGE_PERMISSION,
  INTEGRATIONS_ROUTE,
  isOpen,
  type SyncRun,
  syncRunExceptionsKey,
  syncRunKey,
} from "../../lib/api/queries/integrations";
import { useMe } from "../../lib/api/queries/me";
import { formatDuration, formatMoney, formatNumber, formatTimestamp } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { useBuiltPaths } from "../settings/index";
import { DataPageHeader } from "./imports";
import { IntegrationsAccessLimited, kindLabel, SyncStatusChip, TotalsChip } from "./integrations";

const TABLE = "w-full border-separate border-spacing-0 rounded-md border border-default bg-surface";
const HEADER = "px-3 py-2 text-start text-body-sm font-medium text-fg-2";
const CELL = "border-t border-hairline px-3 py-2 text-body-sm text-fg-1";

export function SyncRunPage() {
  const { connectionId = "", syncRunId = "" } = useParams();
  const me = useMe();
  const access = useAccess();
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={t("data.integrations.syncRun.region")} shape="rows" count={6} />;
  } else if (!access.holdsAnywhere(INTEGRATION_MANAGE_PERMISSION)) {
    body = <IntegrationsAccessLimited />;
  } else {
    return <SyncRunLoader key={syncRunId} connectionId={connectionId} syncRunId={syncRunId} />;
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
  readonly syncRunId: string;
}

function notFound(error: unknown): boolean {
  return error instanceof ApiProblem && error.status === 404;
}

function SyncRunLoader({ connectionId, syncRunId }: LoaderProps) {
  const navigate = useNavigate();
  const connection = useQuery({
    queryKey: connectionKey(connectionId),
    queryFn: () => fetchConnection(connectionId),
    retry: (count, error) => !notFound(error) && count < 1,
  });
  const run = useQuery({
    queryKey: syncRunKey(syncRunId),
    queryFn: () => fetchSyncRun(syncRunId),
    retry: (count, error) => !notFound(error) && count < 1,
    // A run that is still to finish is read again until it has ended.
    refetchInterval: (query) =>
      query.state.data !== undefined && isOpen(query.state.data) ? JOB_POLL_INTERVAL_MS : false,
  });
  const crumbs = [
    { label: t("data.integrations.title"), to: INTEGRATIONS_ROUTE },
    ...(connection.data === undefined
      ? []
      : [{ label: connection.data.name, to: connectionRoute(connection.data.id) }]),
  ];
  // SCR-ST-07: an unknown run, an unknown connection, or a run of another connection.
  const missing =
    notFound(run.error) ||
    notFound(connection.error) ||
    (run.data !== undefined && run.data.integration_connection_id !== connectionId);
  let body: ReactNode = null;
  if (missing) {
    body = (
      <EmptyState
        title={t("data.integrations.syncRun.notFound.title")}
        description={t("data.integrations.syncRun.notFound.description")}
        action={{
          label: t("data.integrations.connection.notFound.action"),
          onAction: () => void navigate(INTEGRATIONS_ROUTE),
        }}
      />
    );
  } else if (run.isError || connection.isError) {
    const error = run.error ?? connection.error;
    body = (
      <Banner
        tone="negative"
        title={t("data.integrations.syncRun.loadError")}
        actions={
          <Button
            variant="link"
            onClick={() => {
              void run.refetch();
              void connection.refetch();
            }}
          >
            {t("data.integrations.retry")}
          </Button>
        }
      >
        {error instanceof ApiProblem ? error.title : (error?.message ?? null)}
      </Banner>
    );
  } else if (run.data === undefined || connection.data === undefined) {
    body = <Skeleton region={t("data.integrations.syncRun.region")} shape="rows" count={6} />;
  }
  if (body !== null || run.data === undefined || connection.data === undefined) {
    return (
      <div data-testid="SF-16-page" className="flex flex-col gap-4">
        <DataPageHeader title={t("data.integrations.syncRun.region")} crumbs={crumbs} />
        {body}
      </div>
    );
  }
  return (
    <div data-testid="SF-16-page" className="flex flex-col gap-6">
      <DataPageHeader
        title={t("data.integrations.syncRun.title", { name: connection.data.name })}
        crumbs={crumbs}
        current={t("data.integrations.syncRun.region")}
        chips={<SyncStatusChip status={run.data.status} />}
      />
      <RunSummary run={run.data} />
      <RunProblem run={run.data} />
      <ControlTotalsTable run={run.data} />
      <RunExceptions run={run.data} />
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

function Instant({ value }: { readonly value: string | null }) {
  return value === null ? (
    <NoValue />
  ) : (
    <time dateTime={value} className="num" data-volatile="">
      {formatTimestamp(value, { seconds: true })}
    </time>
  );
}

function Checkpoint({ value }: { readonly value: Readonly<Record<string, unknown>> | null }) {
  if (value === null || Object.keys(value).length === 0) {
    return <NoValue />;
  }
  return (
    <details>
      <summary className="cursor-default text-body-sm text-accent-fg">
        {t("data.integrations.syncRun.showCheckpoint")}
      </summary>
      <pre
        data-volatile=""
        className="mt-1 whitespace-pre-wrap break-all rounded-md bg-subtle px-3 py-2 font-mono text-mono-sm text-fg-1"
      >
        {JSON.stringify(value, null, 2)}
      </pre>
    </details>
  );
}

/** SCREENS §14.5 definition list. */
function RunSummary({ run }: { readonly run: SyncRun }) {
  return (
    <dl className="grid max-w-160 grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-2 text-body-sm">
      <Definition term={t("data.integrations.runs.column.kind")}>{kindLabel(run.kind)}</Definition>
      <Definition term={t("data.integrations.runs.column.started")}>
        <Instant value={run.started_at} />
      </Definition>
      <Definition term={t("data.integrations.syncRun.finished")}>
        <Instant value={run.finished_at} />
      </Definition>
      <Definition term={t("data.integrations.runs.column.duration")}>
        {run.duration_seconds === null ? (
          <NoValue />
        ) : (
          <span className="num" data-volatile="">
            {formatDuration(run.duration_seconds * 1_000)}
          </span>
        )}
      </Definition>
      <Definition term={t("data.integrations.syncRun.checkpointBefore")}>
        <Checkpoint value={run.checkpoint_before} />
      </Definition>
      <Definition term={t("data.integrations.syncRun.checkpointAfter")}>
        <Checkpoint value={run.checkpoint_after} />
      </Definition>
    </dl>
  );
}

/** SCREENS §14.5 problem banner: the problem's title, its detail and "Reference <request id>". */
function RunProblem({ run }: { readonly run: SyncRun }) {
  const problem = run.problem;
  if (problem === null) {
    return null;
  }
  const text = (name: string): string | null => {
    const value = problem[name];
    return typeof value === "string" && value !== "" ? value : null;
  };
  const instance = text("instance");
  const reference =
    instance !== null && instance.startsWith(REQUEST_INSTANCE_PREFIX)
      ? instance.slice(REQUEST_INSTANCE_PREFIX.length)
      : null;
  return (
    <div data-testid="SF-16-banner-problem">
      <Banner
        tone="negative"
        announce="static"
        title={text("title") ?? t("data.integrations.syncRun.problem")}
      >
        {text("detail") === null ? null : <p>{text("detail")}</p>}
        {reference === null ? null : (
          <p>{t("data.integrations.syncRun.reference", { reference })}</p>
        )}
      </Banner>
    </div>
  );
}

interface Measure {
  readonly key: string;
  readonly label: string;
  readonly source: string | null;
  readonly loaded: string | null;
}

function amountText(currency: string, amount: string | undefined): string | null {
  if (amount === undefined) {
    return null;
  }
  // A currency the viewer's reads did not register keeps its recorded digits (DS-FMT-03).
  return currencyRegistered(currency) ? formatMoney(amount, currency) : amount;
}

/** The rows of "Control totals": Records, then each currency either side recorded. */
export function totalsMeasures(
  source: ControlTotals | null,
  loaded: ControlTotals | null,
): readonly Measure[] {
  const count = (totals: ControlTotals | null) =>
    totals === null ? null : formatNumber(totals.count, { kind: "count" });
  const amounts = (totals: ControlTotals | null) =>
    new Map((totals?.amounts ?? []).map((item) => [item.currency, item.amount]));
  const sourceAmounts = amounts(source);
  const loadedAmounts = amounts(loaded);
  const currencies = [...new Set([...sourceAmounts.keys(), ...loadedAmounts.keys()])].sort();
  return [
    {
      key: "records",
      label: t("data.integrations.syncRun.totals.records"),
      source: count(source),
      loaded: count(loaded),
    },
    ...currencies.map((currency) => ({
      key: currency,
      label: t("data.integrations.syncRun.totals.amount", { currency }),
      source: amountText(currency, sourceAmounts.get(currency)),
      loaded: amountText(currency, loadedAmounts.get(currency)),
    })),
  ];
}

/** SCREENS §14.5 "Control totals": Measure, Source, Loaded and the run's result. */
function ControlTotalsTable({ run }: { readonly run: SyncRun }) {
  const headingId = useId();
  const source = controlTotals(run.source_totals);
  const loaded = controlTotals(run.loaded_totals);
  const measures = totalsMeasures(source, loaded);
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <h2 id={headingId} className="text-title-sm text-fg-1">
        {t("data.integrations.syncRun.totals.title")}
      </h2>
      {source === null && loaded === null ? (
        <p className="text-body-sm text-fg-2">{t("data.integrations.syncRun.totals.none")}</p>
      ) : (
        <table
          data-testid="SF-16-grid-control-totals"
          aria-labelledby={headingId}
          className={`${TABLE} max-w-200`}
        >
          <thead className="bg-subtle">
            <tr>
              <th scope="col" className={HEADER}>
                {t("data.integrations.syncRun.totals.measure")}
              </th>
              <th scope="col" className={`${HEADER} text-end`}>
                {t("data.integrations.syncRun.totals.source")}
              </th>
              <th scope="col" className={`${HEADER} text-end`}>
                {t("data.integrations.syncRun.totals.loaded")}
              </th>
              <th scope="col" className={HEADER}>
                {t("data.integrations.runs.column.result")}
              </th>
            </tr>
          </thead>
          <tbody>
            {measures.map((measure, index) => (
              <tr key={measure.key}>
                <th scope="row" className={`${CELL} text-start font-medium`}>
                  {measure.label}
                </th>
                <td className={`${CELL} num text-end`}>{measure.source ?? <NoValue />}</td>
                <td className={`${CELL} num text-end`}>{measure.loaded ?? <NoValue />}</td>
                {index === 0 ? (
                  // One result for the run: its status, which the API decided over every measure.
                  <td rowSpan={measures.length} className={`${CELL} align-top`}>
                    <TotalsChip status={run.status} />
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function severityChip(item: ExceptionItem): ReactNode {
  const chip = chipFor("E-43", item.severity);
  return chip === null ? null : <StatusChip status={chip.status} />;
}

/** SCREENS §14.5 "Exceptions": Title, Code, Severity and the link to the item. */
function RunExceptions({ run }: { readonly run: SyncRun }) {
  const headingId = useId();
  const built = useBuiltPaths();
  const linked = built.has(`${EXCEPTIONS_ROUTE}/:exceptionId`);
  const exceptions = useQuery({
    queryKey: syncRunExceptionsKey(run.id),
    queryFn: () => fetchSyncRunExceptions(run.id),
    // A run that raised none has nothing to read.
    enabled: run.exception_count > 0,
  });
  let content: ReactNode;
  if (run.exception_count === 0) {
    content = (
      <p className="text-body-sm text-fg-2">{t("data.integrations.syncRun.noExceptions")}</p>
    );
  } else if (exceptions.isError) {
    content = (
      <Banner
        tone="negative"
        headingLevel={3}
        title={t("data.integrations.syncRun.exceptionsLoadError")}
        actions={
          <Button variant="link" onClick={() => void exceptions.refetch()}>
            {t("data.integrations.retry")}
          </Button>
        }
      />
    );
  } else if (exceptions.data === undefined) {
    content = (
      <Skeleton region={t("data.integrations.syncRun.exceptions")} shape="rows" count={3} />
    );
  } else {
    content = (
      <table data-testid="SF-16-grid-exceptions" aria-labelledby={headingId} className={TABLE}>
        <thead className="bg-subtle">
          <tr>
            <th scope="col" className={HEADER}>
              {t("data.integrations.syncRun.exception.title")}
            </th>
            <th scope="col" className={HEADER}>
              {t("data.integrations.syncRun.exception.code")}
            </th>
            <th scope="col" className={HEADER}>
              {t("data.integrations.syncRun.exception.severity")}
            </th>
          </tr>
        </thead>
        <tbody>
          {exceptions.data.map((item) => (
            <tr key={item.id}>
              <th scope="row" className={`${CELL} text-start font-normal`}>
                {linked ? (
                  <Link
                    to={exceptionRoute(item.id)}
                    className="text-accent-fg hover:text-accent-fg-hover hover:underline"
                  >
                    {item.title}
                  </Link>
                ) : (
                  item.title
                )}
              </th>
              <td className={`${CELL} font-mono text-mono-sm`}>{item.code}</td>
              <td className={CELL}>{severityChip(item)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <h2 id={headingId} className="text-title-sm text-fg-1">
        {t("data.integrations.syncRun.exceptions")}
      </h2>
      {content}
    </section>
  );
}
