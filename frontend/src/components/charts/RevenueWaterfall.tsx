// Revenue waterfall (DESIGN_SYSTEM DS-CH-01) in a chart panel (DS-CMP-14): recognized and scheduled
// revenue as stacked columns by period, then one trailing "Awaiting trigger" column, which has no period
// because its timing depends on an event. The first open period's label is bold under an "Open"
// caption, with a rule at the boundary after the last closed period. Figures, totals and the summary
// are the API's strings; the plot converts copies to numbers for geometry only (SPEC-Q-244).
import { type ReactNode, useCallback, useMemo, useRef } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Tooltip,
  usePlotArea,
  useXAxisScale,
  XAxis,
  YAxis,
} from "recharts";

import { formatMoney, formatNumber, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { ChartPanel, type ChartPanelState } from "./ChartPanel";
import {
  ActiveLabel,
  type BarBox,
  boxOf,
  ChartPatterns,
  ChartTable,
  compactTick,
  type LegendEntry,
  paintFor,
  PLOT_HEIGHT,
  PLOT_MARGIN,
  plotNumber,
  rowKey,
  spokenMoney,
  STRICT,
  TICK,
  TooltipCard,
  useChartId,
  useElementWidth,
  useEnterToSelect,
  useForcedColors,
} from "./chartKit";

export type WaterfallSeries = "recognized" | "scheduled" | "awaiting";

export interface WaterfallPeriod {
  /** The period key, for example "FY2026-P07". */
  readonly key: string;
  /** DS-FMT-19 label, for example "Jul 2026". */
  readonly label: string;
  readonly recognized: string;
  readonly scheduled: string;
  readonly total: string;
  /** The period is open; the first open period carries the open marker. */
  readonly open?: boolean | undefined;
}

export interface WaterfallAwaiting {
  readonly amount: string;
  /** Pending triggers behind the amount. */
  readonly count: number;
}

export interface WaterfallTotals {
  readonly recognized: string;
  readonly scheduled: string;
  readonly awaiting: string;
  /** Recognized, scheduled and awaiting trigger together. */
  readonly total: string;
}

/** A drill-down target: `period` null is the Awaiting trigger column; `series` null is every state. */
export interface WaterfallTarget {
  readonly period: string | null;
  readonly series: WaterfallSeries | null;
}

export interface RevenueWaterfallProps {
  readonly title: string;
  readonly subtitle?: string | undefined;
  /** The contract, obligation, customer or portfolio named in the summary. */
  readonly scope: string;
  readonly currency: string;
  readonly periods: readonly WaterfallPeriod[];
  readonly awaiting: WaterfallAwaiting | null;
  readonly totals: WaterfallTotals;
  /** Granularity segmented control and range paging, supplied by the screen. */
  readonly controls?: ReactNode;
  readonly footnote?: ReactNode;
  readonly state?: ChartPanelState;
  readonly emptyText?: string | undefined;
  readonly errorTitle?: string | undefined;
  readonly onRetry?: (() => void) | undefined;
  readonly onSelect?: ((target: WaterfallTarget) => void) | undefined;
  readonly headingLevel?: 2 | 3;
}

/** DS-CH-01: at most 36 columns are drawn; the screen pages longer ranges. */
export const MAX_COLUMNS = 36;

const AWAITING_KEY = "awaiting-trigger";

const SERIES: readonly {
  readonly series: WaterfallSeries;
  readonly colour: string;
  readonly labelKey: string;
}[] = [
  {
    series: "recognized",
    colour: "var(--viz-recognized)",
    labelKey: "common.chart.waterfall.recognized",
  },
  {
    series: "scheduled",
    colour: "var(--viz-scheduled)",
    labelKey: "common.chart.waterfall.scheduled",
  },
  {
    series: "awaiting",
    colour: "var(--viz-awaiting)",
    labelKey: "common.chart.waterfall.awaiting",
  },
];

interface PlotRow {
  readonly key: string;
  readonly label: string;
  readonly recognized: number;
  readonly scheduled: number;
  readonly awaiting: number;
}

interface TickArgs {
  readonly x?: number | string | undefined;
  readonly y?: number | string | undefined;
  readonly payload?: { readonly value?: unknown } | undefined;
}

interface TooltipArgs {
  readonly active?: boolean | undefined;
  readonly label?: unknown;
}

function PeriodMarkers({
  openKey,
  closedKey,
  lastPeriodKey,
  hasAwaiting,
}: {
  readonly openKey: string | undefined;
  readonly closedKey: string | undefined;
  readonly lastPeriodKey: string | undefined;
  readonly hasAwaiting: boolean;
}) {
  const xScale = useXAxisScale();
  const plot = usePlotArea();
  if (xScale === undefined || plot === undefined) {
    return null;
  }
  const between = (left: string, right: string): number | undefined => {
    const end = xScale(left, { position: "end" });
    const start = xScale(right, { position: "start" });
    return end === undefined || start === undefined ? undefined : (end + start) / 2;
  };
  const top = plot.y;
  const bottom = plot.y + plot.height;
  const captionX = openKey === undefined ? undefined : xScale(openKey, { position: "middle" });
  const openRule =
    openKey === undefined || closedKey === undefined ? undefined : between(closedKey, openKey);
  const awaitingRule =
    hasAwaiting && lastPeriodKey !== undefined ? between(lastPeriodKey, AWAITING_KEY) : undefined;
  return (
    <g data-period-markers="">
      {captionX === undefined ? null : (
        <text
          data-open-caption=""
          x={captionX}
          y={top - 6}
          textAnchor="middle"
          fontSize={12}
          fill="var(--viz-label)"
        >
          {t("common.chart.waterfall.open")}
        </text>
      )}
      {openRule === undefined ? null : (
        <line
          data-open-rule=""
          x1={openRule}
          x2={openRule}
          y1={top}
          y2={bottom}
          stroke="var(--fg-2)"
          strokeWidth={1}
        />
      )}
      {awaitingRule === undefined ? null : (
        <line
          data-awaiting-rule=""
          x1={awaitingRule}
          x2={awaitingRule}
          y1={top}
          y2={bottom}
          stroke="var(--viz-baseline)"
          strokeWidth={1}
          strokeDasharray="4 4"
        />
      )}
    </g>
  );
}

function WaterfallPlot({
  periods,
  awaiting,
  currency,
  onSelect,
}: {
  readonly periods: readonly WaterfallPeriod[];
  readonly awaiting: WaterfallAwaiting | null;
  readonly currency: string;
  readonly onSelect: ((target: WaterfallTarget) => void) | undefined;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const width = useElementWidth(containerRef);
  const forced = useForcedColors();
  const id = useChartId();
  const awaitingLabel = t("common.chart.waterfall.awaiting");

  const rows = useMemo<readonly PlotRow[]>(
    () => [
      ...periods.map((period) => ({
        key: period.key,
        label: period.label,
        recognized: plotNumber(period.recognized),
        scheduled: plotNumber(period.scheduled),
        awaiting: 0,
      })),
      ...(awaiting === null
        ? []
        : [
            {
              key: AWAITING_KEY,
              label: awaitingLabel,
              recognized: 0,
              scheduled: 0,
              awaiting: plotNumber(awaiting.amount),
            },
          ]),
    ],
    [periods, awaiting, awaitingLabel],
  );
  const byKey = useMemo(() => new Map(periods.map((period) => [period.key, period])), [periods]);

  const firstOpen = periods.findIndex((period) => period.open === true);
  const openKey = firstOpen >= 0 ? periods[firstOpen]?.key : undefined;
  const closedKey = firstOpen > 0 ? periods[firstOpen - 1]?.key : undefined;
  const lastPeriodKey = periods[periods.length - 1]?.key;

  const select = useCallback(
    (key: string) => {
      onSelect?.(
        key === AWAITING_KEY ? { period: null, series: "awaiting" } : { period: key, series: null },
      );
    },
    [onSelect],
  );
  const reportActive = useEnterToSelect(containerRef, onSelect === undefined ? undefined : select);

  const amountOf = (series: WaterfallSeries, key: string | undefined): string | undefined => {
    if (key === undefined) {
      return undefined;
    }
    if (key === AWAITING_KEY) {
      return series === "awaiting" ? awaiting?.amount : undefined;
    }
    const period = byKey.get(key);
    return series === "recognized"
      ? period?.recognized
      : series === "scheduled"
        ? period?.scheduled
        : undefined;
  };

  const money = (value: string) => formatMoney(value, currency, { variant: "inline" });
  const renderTooltip = ({ active, label }: TooltipArgs) => {
    if (active !== true || typeof label !== "string") {
      return null;
    }
    if (label === AWAITING_KEY) {
      return awaiting === null ? null : (
        <TooltipCard
          heading={awaitingLabel}
          lines={[
            {
              key: "amount",
              label: t("common.chart.tooltip.amount"),
              value: money(awaiting.amount),
            },
            {
              key: "count",
              label: t("common.chart.waterfall.pendingTriggers"),
              value: formatNumber(awaiting.count, { kind: "count" }),
            },
          ]}
        />
      );
    }
    const period = byKey.get(label);
    if (period === undefined) {
      return null;
    }
    return (
      <TooltipCard
        heading={period.label}
        lines={SERIES.slice(0, 2).map((entry) => ({
          key: entry.series,
          label: t(entry.labelKey),
          value: money(entry.series === "recognized" ? period.recognized : period.scheduled),
          colour: entry.colour,
        }))}
        total={{ key: "total", label: t("common.chart.column.total"), value: money(period.total) }}
      />
    );
  };

  return (
    <div ref={containerRef} className="min-w-0 tabular-nums">
      <BarChart
        width={width}
        height={PLOT_HEIGHT}
        data={rows}
        margin={{ ...PLOT_MARGIN, top: openKey === undefined ? PLOT_MARGIN.top : 24 }}
        barCategoryGap="20%"
      >
        <ChartPatterns id={id} />
        <CartesianGrid vertical={false} stroke="var(--viz-grid)" />
        <XAxis
          dataKey="key"
          height={24}
          tickLine={false}
          axisLine={{ stroke: "var(--viz-baseline)" }}
          tick={({ x, y, payload }: TickArgs) => {
            const key = typeof payload?.value === "string" ? payload.value : "";
            return (
              <text
                x={x}
                y={y}
                dy={14}
                textAnchor="middle"
                fontSize={12}
                fill="var(--viz-tick)"
                fontWeight={key === openKey ? 600 : 400}
              >
                {key === AWAITING_KEY ? awaitingLabel : (byKey.get(key)?.label ?? key)}
              </text>
            );
          }}
        />
        <YAxis
          width="auto"
          tickCount={5}
          tick={TICK}
          tickLine={false}
          axisLine={false}
          tickFormatter={compactTick}
        />
        <Tooltip
          isAnimationActive={false}
          cursor={{ fill: "var(--bg-hover)" }}
          content={renderTooltip}
        />
        {SERIES.map((entry, slot) => {
          const paint = paintFor({
            id,
            colour: entry.colour,
            slot,
            forced,
            awaiting: entry.series === "awaiting",
          });
          return (
            <Bar
              key={entry.series}
              dataKey={entry.series}
              name={t(entry.labelKey)}
              stackId="revenue"
              isAnimationActive={false}
              onClick={(item: { readonly payload?: unknown }) => {
                const key = rowKey(item.payload);
                if (key === undefined || onSelect === undefined) {
                  return;
                }
                onSelect({
                  period: key === AWAITING_KEY ? null : key,
                  series: entry.series,
                });
              }}
              shape={(bar: BarBox) => {
                const box = boxOf(bar);
                const key = rowKey(bar.payload);
                return (
                  <rect
                    {...box}
                    {...paint}
                    data-series={entry.series}
                    data-period={key}
                    data-amount={amountOf(entry.series, key)}
                  />
                );
              }}
            />
          );
        })}
        <PeriodMarkers
          openKey={openKey}
          closedKey={closedKey}
          lastPeriodKey={lastPeriodKey}
          hasAwaiting={awaiting !== null}
        />
        <ActiveLabel onChange={reportActive} />
      </BarChart>
    </div>
  );
}

export function RevenueWaterfall({
  title,
  subtitle,
  scope,
  currency,
  periods,
  awaiting,
  totals,
  controls,
  footnote,
  state = "ready",
  emptyText,
  errorTitle,
  onRetry,
  onSelect,
  headingLevel,
}: RevenueWaterfallProps) {
  if (STRICT && periods.length > MAX_COLUMNS) {
    throw new Error(`A revenue waterfall draws at most ${String(MAX_COLUMNS)} columns (DS-CH-01)`);
  }
  const first = periods[0];
  const last = periods[periods.length - 1];
  const summary =
    first === undefined || last === undefined
      ? t("common.chart.waterfall.summaryEmpty", { scope })
      : t("common.chart.waterfall.summary", {
          scope,
          from: first.label,
          to: last.label,
          recognized: spokenMoney(totals.recognized, currency),
          scheduled: spokenMoney(totals.scheduled, currency),
          awaiting: spokenMoney(totals.awaiting, currency),
        });

  const legend: LegendEntry[] = SERIES.filter(
    (entry) => entry.series !== "awaiting" || awaiting !== null,
  ).map((entry) => ({
    key: entry.series,
    label: t(entry.labelKey),
    colour: entry.colour,
    texture: entry.series === "awaiting" ? "hatch" : "solid",
  }));

  const money = (value: string) => formatMoney(value, currency);
  const table = (
    <ChartTable
      caption={title}
      columns={[
        { key: "period", label: t("common.chart.column.period") },
        {
          key: "recognized",
          label: t("common.chart.waterfall.column.recognized", { currency }),
          numeric: true,
        },
        {
          key: "scheduled",
          label: t("common.chart.waterfall.column.scheduled", { currency }),
          numeric: true,
        },
        {
          key: "total",
          label: t("common.chart.waterfall.column.total", { currency }),
          numeric: true,
        },
      ]}
      rows={[
        ...periods.map((period) => ({
          key: period.key,
          cells: [
            period.label,
            money(period.recognized),
            money(period.scheduled),
            money(period.total),
          ],
        })),
        ...(awaiting === null
          ? []
          : [
              {
                key: AWAITING_KEY,
                cells: [
                  t("common.chart.waterfall.awaiting"),
                  NO_VALUE,
                  NO_VALUE,
                  money(awaiting.amount),
                ],
              },
            ]),
      ]}
      footer={{
        key: "total",
        cells: [
          t("common.chart.column.total"),
          money(totals.recognized),
          money(totals.scheduled),
          money(totals.total),
        ],
      }}
    />
  );

  return (
    <ChartPanel
      title={title}
      subtitle={subtitle}
      summary={summary}
      legend={legend}
      controls={controls}
      footnote={footnote}
      state={state}
      emptyText={emptyText}
      errorTitle={errorTitle}
      onRetry={onRetry}
      headingLevel={headingLevel}
      chart={
        <WaterfallPlot
          periods={periods}
          awaiting={awaiting}
          currency={currency}
          onSelect={onSelect}
        />
      }
      table={table}
    />
  );
}
