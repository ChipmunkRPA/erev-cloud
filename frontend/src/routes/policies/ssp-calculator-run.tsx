// SF-13:ssp-calculator-run Calculator run (SCREENS §11.5 run page regions, states, sample world and test
// hooks; §0.4 RT-68; DESIGN_SYSTEM DS-CMP-06 figures strip, DS-CMP-10, DS-CMP-11, DS-CMP-14, DS-A11Y-13;
// 04 API-R-27 `GET /ssp-calculator-runs/{id}`, `GET …/results`, `GET …/observations` (§16.14), `POST
// …/exclusions`, `POST …/create-draft-version`; BUILD_SPEC RFD-24). Breadcrumb "Policies / SSP calculator
// / <run name>", the header with the E-67 chip, the parameters and "Create draft version from results";
// per product the figures strip (Observations, Excluded, Median (<currency>), Inside ±<band> with "<n> of
// <m>"), the statistics table and the distribution chart with its Table view; the observations grid with
// "Exclude observation". Figures render the API strings through the format module (DG-FE-08); only the
// integer histogram counts and a plot copy of the bin edges size the marks. The plot is drawn with plain
// bars in this page, without Recharts (L4-5-Q-56).
import { useQuery } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useId, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { PLOT_HEIGHT, plotNumber, spokenMoney } from "../../components/charts/chartKit";
import { ChartPanel } from "../../components/charts/ChartPanel";
import { DataGrid } from "../../components/data-grid/DataGrid";
import type { GridColumn, GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { DateInput } from "../../components/form/DateInput";
import { controlClass, Field } from "../../components/form/Field";
import { ReasonField } from "../../components/form/ReasonField";
import { Num } from "../../components/money/Num";
import { RecordHeader } from "../../components/record/RecordHeader";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { ApiProblem } from "../../lib/api/problems";
import { useMe } from "../../lib/api/queries/me";
import {
  EVERY_SSP_BOOK,
  EVERY_SSP_BOOK_VERSION,
  fetchSspBook,
  SSP_CREATE_PERMISSION,
  SSP_READ_PERMISSION,
  type SspBook,
  sspBookKey,
  type SspBookVersion,
  sspBookVersionRoute,
} from "../../lib/api/queries/ssp-books";
import {
  EVERY_SSP_RUN,
  EXCLUSION_REASON_MIN,
  fetchFileMeta,
  fetchObservationsPage,
  fetchSspResults,
  fetchSspRun,
  fileKey,
  isActiveRun,
  ratioPercentFigures,
  RUN_POLL_INTERVAL_MS,
  type SspCalculatorObservation,
  type SspCalculatorResult,
  type SspCalculatorRun,
  sspObservationsKey,
  sspResultsKey,
  sspRunKey,
  sspRunPath,
  useCurrencyReference,
} from "../../lib/api/queries/ssp-calculator";
import { useFieldRefusals } from "../../lib/api/refusals";
import { formatCompact, formatDate, formatNumber, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { PolicyRecordNav } from "./ssp-book-version";
import { problemText, SspAccessLimited } from "./ssp-books";

export function SspCalculatorRunPage() {
  const { runId = "" } = useParams();
  const me = useMe();
  const access = useAccess();
  const navigate = useNavigate();
  const read = access.holdsAnywhere(SSP_READ_PERMISSION);
  const run = useQuery({
    queryKey: sspRunKey(runId),
    queryFn: () => fetchSspRun(runId),
    enabled: read,
    refetchInterval: (query) =>
      query.state.data !== undefined && isActiveRun(query.state.data.status)
        ? RUN_POLL_INTERVAL_MS
        : false,
  });
  const region = t("policies.sspRun.region");

  if (me.isError) {
    return <Banner tone="negative" title={me.error.message} />;
  }
  if (me.data === undefined) {
    return <Skeleton region={region} shape="rows" count={8} />;
  }
  if (!read) {
    return <SspAccessLimited />;
  }
  if (run.error !== null) {
    if (run.error instanceof ApiProblem && run.error.status === 404) {
      return (
        <EmptyState
          title={t("policies.sspRun.notFound.title")}
          description={t("policies.version.notFound.description")}
          action={{
            label: t("policies.sspRun.notFound.action"),
            onAction: () => void navigate("/policies/ssp-calculator"),
          }}
        />
      );
    }
    return (
      <Banner
        tone="negative"
        title={t("policies.sspRun.loadError")}
        headingLevel={2}
        actions={
          <Button variant="link" onClick={() => void run.refetch()}>
            {t("policies.retry")}
          </Button>
        }
      >
        {problemText(run.error)}
      </Banner>
    );
  }
  if (run.data === undefined) {
    return <Skeleton region={region} shape="rows" count={8} />;
  }
  return (
    <RunView
      key={run.data.id}
      run={run.data}
      create={access.holdsAnywhere(SSP_CREATE_PERMISSION)}
    />
  );
}

interface RunViewProps {
  readonly run: SspCalculatorRun;
  readonly create: boolean;
}

function RunView({ run, create }: RunViewProps) {
  const succeeded = run.status === "SUCCEEDED";
  const results = useQuery({
    queryKey: sspResultsKey(run.id),
    queryFn: () => fetchSspResults(run.id),
    enabled: succeeded,
  });
  const book = useQuery({
    queryKey: sspBookKey(run.parameters.ssp_book_id),
    queryFn: () => fetchSspBook(run.parameters.ssp_book_id),
    retry: false,
  });
  const poolId = run.parameters.pool_file_id;
  const pool = useQuery({
    queryKey: fileKey(poolId ?? ""),
    queryFn: () => fetchFileMeta(poolId ?? ""),
    enabled: poolId !== null,
    retry: false,
  });
  const [excluding, setExcluding] = useState<SspCalculatorObservation | null>(null);
  const [drafting, setDrafting] = useState(false);
  const statusSpec = chipFor("E-67", run.status);
  const items = results.data ?? [];
  // DS-FMT-03: the statistics render once the run's currencies are registered.
  const currencies = useCurrencyReference([
    run.parameters.currency,
    ...items.map((item) => item.currency),
  ]);

  const meta = [
    {
      label: t("policies.sspRun.meta.book"),
      value: <span className="font-mono text-mono-sm">{book.data?.code ?? NO_VALUE}</span>,
    },
    {
      label: t("policies.sspRun.meta.dates"),
      value: t("policies.sspRun.meta.dateRange", {
        from: formatDate(run.parameters.date_from),
        to: formatDate(run.parameters.date_to),
      }),
    },
    {
      label: t("policies.sspRun.meta.band"),
      value: <Num value={run.parameters.band_ratio} kind="share" />,
    },
    {
      label: t("policies.sspRun.meta.source"),
      value: t(`policies.sspCalculator.source.${run.parameters.source}`),
    },
    ...(poolId === null
      ? []
      : [
          {
            label: t("policies.sspRun.meta.pool"),
            value: pool.data?.original_filename ?? NO_VALUE,
          },
        ]),
  ];

  const actions: ReactNode[] = [];
  if (run.draft_ssp_book_version_id !== null) {
    actions.push(
      <Link
        key="draft"
        to={sspBookVersionRoute(run.parameters.ssp_book_id, run.draft_ssp_book_version_id)}
        className="text-body-sm font-medium text-accent-fg hover:underline"
      >
        {t("policies.sspCalculator.runs.openDraft")}
      </Link>,
    );
  }
  if (create && succeeded && items.length > 0) {
    actions.push(
      <Button key="create" variant="primary" onClick={() => setDrafting(true)}>
        {t("policies.sspRun.createDraft")}
      </Button>,
    );
  }

  let body: ReactNode;
  if (isActiveRun(run.status)) {
    body = (
      <div className="flex flex-col gap-3" aria-busy="true">
        <p role="status" className="text-body-sm text-fg-2">
          {t("policies.sspRun.running")}
        </p>
        <Skeleton region={t("policies.sspRun.figures.region")} shape="rows" count={3} />
      </div>
    );
  } else if (run.status === "FAILED") {
    body = <Banner tone="negative" headingLevel={2} title={t("policies.sspRun.failed")} />;
  } else if (results.error !== null || currencies.error !== null) {
    body = (
      <Banner tone="negative" title={t("policies.sspRun.resultsError")} headingLevel={2}>
        {problemText(results.error ?? currencies.error)}
      </Banner>
    );
  } else if (results.data === undefined || currencies.data === undefined) {
    body = <Skeleton region={t("policies.sspRun.figures.region")} shape="rows" count={4} />;
  } else if (items.length === 0) {
    body = (
      <EmptyState
        title={t("policies.sspRun.noObservations.title")}
        description={t("policies.sspRun.noObservations.description")}
      />
    );
  } else {
    body = (
      <>
        {items.map((result) => (
          <ResultSection key={result.id} result={result} />
        ))}
        <ObservationsGrid run={run} create={create} onExclude={setExcluding} />
      </>
    );
  }

  return (
    <div className="flex w-full flex-col gap-6">
      <PolicyRecordNav tabKey="sspCalculator" current={run.name} />
      <RecordHeader
        title={run.name}
        chips={statusSpec === null ? null : <StatusChip status={statusSpec.status} />}
        actions={actions.length === 0 ? undefined : <>{actions}</>}
        meta={meta}
      />
      {body}
      {excluding === null ? null : (
        <ExcludeModal run={run} observation={excluding} onClose={() => setExcluding(null)} />
      )}
      {drafting ? (
        <CreateDraftModal run={run} book={book.data} onClose={() => setDrafting(false)} />
      ) : null}
    </div>
  );
}

function ResultSection({ result }: { readonly result: SspCalculatorResult }) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-4">
      <h2 id={headingId} className="font-mono text-title-sm text-fg-1">
        {result.stratification === ""
          ? result.product_code
          : `${result.product_code} · ${result.stratification}`}
      </h2>
      <FiguresStrip result={result} />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <StatisticsTable result={result} />
        <div className="xl:col-span-2">
          <DistributionPanel result={result} />
        </div>
      </div>
    </section>
  );
}

interface Figure {
  readonly id: string;
  readonly label: string;
  readonly value: ReactNode;
  readonly secondary?: string;
}

/**
 * SCREENS §11.5 figures per product (DS-CMP-06 strip): Observations; Excluded; Median (<currency>);
 * Inside ±<band> (`compliance_ratio`, DS-FMT-09 one decimal) with "<inside count> of <observation
 * count>". Every figure is the API's value through `<Num>`; nothing is converted to a number.
 */
export function FiguresStrip({ result }: { readonly result: SspCalculatorResult }) {
  const headingId = useId();
  const figures: readonly Figure[] = [
    {
      id: "observations",
      label: t("policies.sspRun.figures.observations"),
      value: <Num value={result.observation_count} kind="count" />,
    },
    {
      id: "excluded",
      label: t("policies.sspRun.figures.excluded"),
      value: <Num value={result.excluded_count} kind="count" />,
    },
    {
      id: "median",
      label: t("policies.sspRun.figures.median", { currency: result.currency }),
      value: <Num value={result.median_unit_price} kind="rate" currency={result.currency} />,
    },
    {
      id: "inside",
      label: t("policies.sspRun.figures.inside", {
        percent: ratioPercentFigures(result.band_ratio),
      }),
      value: <Num value={result.compliance_ratio} kind="percent" />,
      secondary: t("policies.sspRun.figures.insideCount", {
        inside: formatNumber(result.inside_count, { kind: "count" }),
        total: formatNumber(result.observation_count, { kind: "count" }),
      }),
    },
  ];
  return (
    <div
      data-testid="SF-13-kpi-strip"
      className="flex flex-col gap-2 border-y border-hairline py-3"
    >
      <h3 id={headingId} className="text-caption text-fg-3">
        {t("policies.sspRun.figures.heading", { product: result.product_code })}
      </h3>
      <dl aria-labelledby={headingId} className="grid auto-cols-fr grid-flow-col gap-y-3">
        {figures.map((figure) => (
          <div
            key={figure.id}
            className="flex min-w-0 flex-col gap-1 border-s border-hairline px-4 first:border-s-0 first:ps-0"
          >
            <dt className="text-caption text-fg-3">{figure.label}</dt>
            <dd className="flex flex-col items-start gap-1.5">
              <span className="text-kpi text-fg-1">{figure.value}</span>
              {figure.secondary === undefined ? null : (
                <span className="text-body-sm text-fg-3">{figure.secondary}</span>
              )}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

const STATISTICS = [
  ["p10", "p10_unit_price"],
  ["p25", "p25_unit_price"],
  ["median", "median_unit_price"],
  ["p75", "p75_unit_price"],
  ["p90", "p90_unit_price"],
  ["mean", "mean_unit_price"],
  ["proposedLow", "proposed_low"],
  ["proposedMid", "proposed_mid"],
  ["proposedHigh", "proposed_high"],
] as const;

/** SCREENS §11.5 statistics: P10, P25, Median, P75, P90, Mean, Proposed low, mid and high (DS-FMT-13). */
function StatisticsTable({ result }: { readonly result: SspCalculatorResult }) {
  return (
    <table className="w-full border-collapse text-body-sm">
      <caption className="pb-2 text-start text-title-sm text-fg-1">
        {t("policies.sspRun.statistics.title")}
      </caption>
      <thead>
        <tr className="border-b border-default bg-subtle">
          <th scope="col" className="px-3 py-2 text-start font-medium text-fg-2">
            {t("policies.sspRun.statistics.column.statistic")}
          </th>
          <th scope="col" className="px-3 py-2 text-end font-medium text-fg-2">
            {t("policies.sspRun.statistics.column.value", { currency: result.currency })}
          </th>
        </tr>
      </thead>
      <tbody>
        {STATISTICS.map(([key, member]) => (
          <tr key={key} className="border-b border-hairline">
            <th scope="row" className="px-3 py-2 text-start font-normal text-fg-1">
              {t(`policies.sspRun.statistics.row.${key}`)}
            </th>
            <td className="px-3 py-2 text-end">
              <Num value={result[member]} kind="rate" currency={result.currency} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** SCREENS §11.5 distribution: DS-CMP-14 plain bars with the Table view From, To, Count. */
function DistributionPanel({ result }: { readonly result: SspCalculatorResult }) {
  const bins = result.histogram;
  const percent = ratioPercentFigures(result.band_ratio);
  const summary = t("policies.sspRun.chart.summary", {
    product: result.product_code,
    observations: formatNumber(result.observation_count, { kind: "count" }),
    median: spokenMoney(result.median_unit_price, result.currency),
    percent,
    low: spokenMoney(result.proposed_low, result.currency),
    high: spokenMoney(result.proposed_high, result.currency),
  });
  const table = (
    <table className="w-full border-collapse text-body-sm">
      <caption className="sr-only">{t("policies.sspRun.chart.title")}</caption>
      <thead>
        <tr className="border-b border-default bg-subtle">
          {(["from", "to", "count"] as const).map((key) => (
            <th key={key} scope="col" className="px-3 py-2 text-end font-medium text-fg-2">
              {t(`policies.sspRun.chart.column.${key}`, { currency: result.currency })}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {bins.map((bin, index) => (
          <tr key={String(index)} className="border-b border-hairline">
            <td className="px-3 py-2 text-end">
              <Num value={bin.from} kind="rate" currency={result.currency} />
            </td>
            <td className="px-3 py-2 text-end">
              <Num value={bin.to} kind="rate" currency={result.currency} />
            </td>
            <td className="px-3 py-2 text-end">
              <Num value={bin.count} kind="count" />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
  return (
    <div data-testid="SF-13-chart-distribution">
      <ChartPanel
        title={t("policies.sspRun.chart.title")}
        subtitle={t("policies.sspRun.chart.subtitle", {
          product: result.product_code,
          currency: result.currency,
        })}
        summary={summary}
        state={bins.length === 0 ? "empty" : "ready"}
        emptyText={t("policies.sspRun.chart.empty")}
        chart={<HistogramPlot result={result} percent={percent} />}
        table={table}
      />
    </div>
  );
}

/** One bar per `histogram` bin in `--viz-1`, with 1 px rules at the median and the band edges. */
function HistogramPlot({
  result,
  percent,
}: {
  readonly result: SspCalculatorResult;
  readonly percent: string;
}) {
  const bins = result.histogram;
  const first = bins[0];
  const last = bins.at(-1);
  if (first === undefined || last === undefined) {
    return null;
  }
  const low = plotNumber(first.from);
  const span = plotNumber(last.to) - low;
  const position = (value: string): number =>
    span <= 0 ? 50 : Math.min(100, Math.max(0, ((plotNumber(value) - low) / span) * 100));
  const peak = Math.max(1, ...bins.map((bin) => bin.count));
  const rules = [
    { id: "low", label: t("policies.sspRun.chart.lower", { percent }), value: result.proposed_low },
    { id: "median", label: t("policies.sspRun.chart.median"), value: result.median_unit_price },
    {
      id: "high",
      label: t("policies.sspRun.chart.upper", { percent }),
      value: result.proposed_high,
    },
  ];
  return (
    <div aria-hidden="true" className="flex flex-col gap-2">
      <div className="relative" style={{ blockSize: PLOT_HEIGHT }}>
        <div className="absolute inset-0 flex items-end gap-px border-b border-control pt-6">
          {bins.map((bin, index) => (
            <div
              key={String(index)}
              className="flex-1 bg-viz-1"
              style={{ blockSize: `${String((bin.count / peak) * 100)}%` }}
            />
          ))}
        </div>
        {rules.map((rule) => (
          <div
            key={rule.id}
            className="absolute inset-y-0 border-s border-control"
            style={{ insetInlineStart: `${String(position(rule.value))}%` }}
          >
            <span className="absolute top-0 ms-1 whitespace-nowrap text-caption text-fg-2">
              {rule.label}
            </span>
          </div>
        ))}
      </div>
      <div className="num flex justify-between text-caption text-fg-3">
        <span>{formatCompact(first.from)}</span>
        <span>{formatCompact(result.median_unit_price)}</span>
        <span>{formatCompact(last.to)}</span>
      </div>
    </div>
  );
}

interface ObservationsGridProps {
  readonly run: SspCalculatorRun;
  readonly create: boolean;
  readonly onExclude: (observation: SspCalculatorObservation) => void;
}

/** SCREENS §11.5 observations (`GET /ssp-calculator-runs/{id}/observations`, 04 §16.14). */
function ObservationsGrid({ run, create, onExclude }: ObservationsGridProps) {
  const currency = run.parameters.currency;
  const columns: GridColumn<SspCalculatorObservation>[] = [
    {
      id: "date",
      header: t("policies.sspRun.observations.column.date"),
      kind: "date",
      value: (item) => item.date,
      width: 128,
    },
    {
      id: "source",
      header: t("policies.sspRun.observations.column.source"),
      kind: "identifier",
      value: (item) => item.source_reference,
      width: 176,
    },
    {
      id: "product",
      header: t("policies.sspRun.observations.column.product"),
      kind: "text",
      value: (item) => item.product_code,
      render: (item) => <span className="font-mono text-mono-sm">{item.product_code}</span>,
      width: 144,
    },
    {
      id: "customer",
      header: t("policies.sspRun.observations.column.customer"),
      kind: "text",
      value: (item) => item.customer?.name ?? null,
      width: 208,
    },
    {
      id: "quantity",
      header: t("policies.sspRun.observations.column.quantity"),
      kind: "number",
      numberKind: "quantity",
      value: (item) => item.quantity,
      width: 104,
    },
    {
      id: "unitPrice",
      header: t("policies.sspRun.observations.column.unitPrice", { currency }),
      kind: "number",
      value: (item) => item.unit_price,
      render: (item) => <Num value={item.unit_price} kind="rate" currency={currency} />,
      width: 152,
    },
    {
      id: "inBand",
      header: t("policies.sspRun.observations.column.inBand"),
      kind: "text",
      value: (item) => t(item.in_band ? "common.grid.yes" : "common.grid.no"),
      width: 96,
    },
    {
      id: "excluded",
      header: t("policies.sspRun.observations.column.excluded"),
      kind: "text",
      value: (item) => item.exclusion_reason,
      width: 280,
    },
  ];
  if (create && run.status === "SUCCEEDED") {
    columns.push({
      id: "actions",
      header: t("policies.sspRun.observations.column.actions"),
      kind: "actions",
      value: () => null,
      render: (item) =>
        item.exclusion_reason === null ? (
          <Button
            variant="ghost"
            size="sm"
            aria-label={t("policies.sspRun.exclude.rowAction", {
              reference: item.source_reference,
            })}
            onClick={() => onExclude(item)}
          >
            {t("policies.sspRun.exclude.action")}
          </Button>
        ) : null,
      width: 184,
    });
  }
  const source: GridSource<SspCalculatorObservation> = {
    queryKey: sspObservationsKey(run.id),
    fetchPage: (cursor) => fetchObservationsPage(run.id, cursor),
  };
  return (
    <div className="flex h-120 min-h-0 flex-col">
      <DataGrid<SspCalculatorObservation>
        name="observations"
        title={t("policies.sspRun.observations.title")}
        countLabel={(count, formatted) =>
          t("policies.sspRun.observations.count", { count, formatted })
        }
        columns={columns}
        source={source}
        rowKey={(item) => `${item.product_code}:${item.source_reference}`}
        rowLabel={(item) => item.source_reference}
        testIdPrefix="SF-13"
        rowTestKey={(item) => `observation-${item.source_reference}`}
        emptyState={
          <EmptyState
            title={t("policies.sspRun.noObservations.title")}
            description={t("policies.sspRun.noObservations.description")}
          />
        }
      />
    </div>
  );
}

interface ExcludeModalProps {
  readonly run: SspCalculatorRun;
  readonly observation: SspCalculatorObservation;
  readonly onClose: () => void;
}

/** The API members the fields of the two modals send (DG-FE-06 rev 1.228). */
const EXCLUSION_MEMBERS = { reason: ["reason"] } as const;
const DRAFT_MEMBERS = {
  version_label: ["version_label"],
  effective_from_date: ["effective_from_date"],
} as const;

/** SCREENS §11.5 exclude modal: Reason (at least 10 characters); "Exclude" recomputes the figures. */
function ExcludeModal({ run, observation, onClose }: ExcludeModalProps) {
  const toast = useToast();
  const formId = useId();
  const [reason, setReason] = useState("");
  const [tried, setTried] = useState(false);
  const command = useCommand<unknown>({
    method: "POST",
    path: `${sspRunPath(run.id)}/exclusions`,
    invalidates: [EVERY_SSP_RUN],
  });
  const refusals = useFieldRefusals(command.problem, EXCLUSION_MEMBERS);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setTried(true);
    if (command.pending || reason.trim().length < EXCLUSION_REASON_MIN) {
      return;
    }
    const outcome = await command.submit({
      source_reference: observation.source_reference,
      reason: reason.trim(),
    });
    if (outcome.kind === "succeeded") {
      toast.show({
        tone: "positive",
        message: t("policies.sspRun.exclude.done", { reference: observation.source_reference }),
      });
      onClose();
    }
  };
  return (
    <Modal
      open
      variant="form"
      title={t("policies.sspRun.exclude.title", { reference: observation.source_reference })}
      description={t("policies.sspRun.exclude.description")}
      primaryAction={{ label: t("policies.sspRun.exclude.confirm"), form: formId }}
      submitting={command.pending}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        onSubmit={(event) => void submit(event)}
        className="flex flex-col gap-3"
      >
        <RefusalBanner problem={refusals.banner} placed={refusals.placed} headingLevel={3} />
        <ReasonField
          label={t("policies.sspRun.exclude.reason")}
          value={reason}
          onChange={(value) => {
            setReason(value);
            refusals.edited("reason");
          }}
          minimum={EXCLUSION_REASON_MIN}
          showError={tried}
          error={refusals.fields.reason}
        />
      </form>
    </Modal>
  );
}

interface CreateDraftModalProps {
  readonly run: SspCalculatorRun;
  readonly book: SspBook | undefined;
  readonly onClose: () => void;
}

/** SCREENS §11.5 create draft modal: Version label, Effective from, the book read-only. */
function CreateDraftModal({ run, book, onClose }: CreateDraftModalProps) {
  const toast = useToast();
  const navigate = useNavigate();
  const formId = useId();
  const [label, setLabel] = useState("");
  const [typed, setTyped] = useState("");
  const [date, setDate] = useState<string | null>(null);
  const [formatError, setFormatError] = useState<string | null>(null);
  const [local, setLocal] = useState<string | null>(null);
  const command = useCommand<SspBookVersion>({
    method: "POST",
    path: `${sspRunPath(run.id)}/create-draft-version`,
    invalidates: [EVERY_SSP_RUN, EVERY_SSP_BOOK, EVERY_SSP_BOOK_VERSION],
  });
  const refusals = useFieldRefusals(command.problem, DRAFT_MEMBERS);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (command.pending || formatError !== null) {
      return;
    }
    if (label.trim() === "") {
      setLocal(t("policies.sspRun.draft.labelRequired"));
      return;
    }
    setLocal(null);
    const outcome = await command.submit({
      version_label: label.trim(),
      ...(date === null ? {} : { effective_from_date: date }),
    });
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      toast.show({
        tone: "positive",
        message: t("policies.sspRun.draft.created", { label: label.trim() }),
      });
      onClose();
      void navigate(sspBookVersionRoute(run.parameters.ssp_book_id, outcome.data.id));
    }
  };
  return (
    <Modal
      open
      variant="form"
      title={t("policies.sspRun.draft.title")}
      primaryAction={{ label: t("policies.sspRun.draft.confirm"), form: formId }}
      submitting={command.pending}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        onSubmit={(event) => void submit(event)}
        className="flex flex-col gap-4"
      >
        <RefusalBanner problem={refusals.banner} placed={refusals.placed} headingLevel={3} />
        <Field
          name="draft_version_label"
          label={t("policies.sspVersion.meta.label")}
          required
          error={local ?? refusals.fields.version_label}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              value={label}
              onChange={(event) => {
                setLabel(event.target.value);
                refusals.edited("version_label");
              }}
              className={controlClass(local !== null)}
            />
          )}
        </Field>
        <Field
          name="draft_effective_from"
          label={t("policies.sspVersion.meta.effectiveFrom")}
          optional
          error={formatError ?? refusals.fields.effective_from_date}
          width="date"
        >
          {(control) => (
            <DateInput
              control={control}
              value={typed}
              onChange={(value) => {
                setTyped(value);
                refusals.edited("effective_from_date");
              }}
              onValue={setDate}
              onFormatError={setFormatError}
              invalid={formatError !== null}
            />
          )}
        </Field>
        <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1 text-body-sm">
          <dt className="text-fg-3">{t("policies.sspRun.meta.book")}</dt>
          <dd className="text-fg-1">
            {book === undefined ? NO_VALUE : `${book.code} · ${book.name}`}
          </dd>
        </dl>
      </form>
    </Modal>
  );
}
