// RPO time-band stacked bars (DESIGN_SYSTEM DS-CH-03; ASC 606-10-50-13) in a chart panel (DS-CMP-14):
// one horizontal bar per row (the total, then the chosen disaggregation), stacked by the bands the `rpo`
// report run returns, nearest first in `--viz-rpo-1` onward. Band labels are built from the returned
// month boundaries (POL-201 `rpo.time_bands`); the chart never computes, merges or re-orders bands, and
// more than five bands leave only the Table view.
import { type ReactNode, useCallback, useMemo, useRef } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, Tooltip, XAxis, YAxis } from "recharts";

import { formatCompact, formatList, formatMoney, formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { ChartPanel, type ChartPanelState } from "./ChartPanel";
import {
  ActiveLabel,
  type BarBox,
  boxOf,
  ChartPatterns,
  ChartTable,
  compactTick,
  paintFor,
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

export interface RpoRow {
  readonly key: string;
  readonly label: string;
  readonly total: string;
  /** One amount per band, nearest band first. */
  readonly amounts: readonly string[];
}

export interface RpoTarget {
  readonly row: string;
  /** The band index, nearest first; null for every band of the row (Enter on the active row). */
  readonly band: number | null;
}

export interface RpoTimeBandsProps {
  readonly title: string;
  readonly subtitle?: string | undefined;
  readonly currency: string;
  /** The month boundaries of the run's bands, for example `[12, 24]`. */
  readonly boundaries: readonly number[];
  /** The total row first, then at most eleven disaggregation rows, folded into "Other" by the API. */
  readonly rows: readonly RpoRow[];
  /** The header of the row column, for example "Entity". */
  readonly rowHeader: string;
  /** The disaggregation toolbar, supplied by the screen. */
  readonly controls?: ReactNode;
  /** The practical expedients applied and what they exclude (606-10-50-14). */
  readonly footnote?: ReactNode;
  readonly state?: ChartPanelState;
  readonly emptyText?: string | undefined;
  readonly errorTitle?: string | undefined;
  readonly onRetry?: (() => void) | undefined;
  readonly onSelect?: ((target: RpoTarget) => void) | undefined;
  readonly headingLevel?: 2 | 3;
}

/** DS-CH-03: the chart draws one to five bands. */
export const MAX_CHART_BANDS = 5;

/** DS-CH-03: at most 12 rows. */
export const MAX_ROWS = 12;

const ROW_HEIGHT = 36;

/** DS-CH-03 band labels from the returned month boundaries. */
export function rpoBandLabels(boundaries: readonly number[]): readonly string[] {
  if (boundaries.length === 0) {
    return [t("common.chart.rpo.band.all")];
  }
  const months = (value: number) => formatNumber(value, { kind: "count" });
  const labels = boundaries.map((boundary, index) =>
    index === 0
      ? t("common.chart.rpo.band.within", { months: months(boundary) })
      : t("common.chart.rpo.band.between", {
          from: months((boundaries[index - 1] ?? 0) + 1),
          to: months(boundary),
        }),
  );
  labels.push(
    t("common.chart.rpo.band.after", { months: months(boundaries[boundaries.length - 1] ?? 0) }),
  );
  return labels;
}

function bandColour(index: number): string {
  return `var(--viz-rpo-${String(index + 1)})`;
}

interface PlotRow {
  readonly key: string;
  readonly values: readonly number[];
  readonly totalLabel: string;
}

interface TooltipArgs {
  readonly active?: boolean | undefined;
  readonly label?: unknown;
}

function RpoPlot({
  rows,
  labels,
  currency,
  onSelect,
}: {
  readonly rows: readonly RpoRow[];
  readonly labels: readonly string[];
  readonly currency: string;
  readonly onSelect: ((target: RpoTarget) => void) | undefined;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const width = useElementWidth(containerRef);
  const forced = useForcedColors();
  const id = useChartId();
  const byKey = useMemo(() => new Map(rows.map((row) => [row.key, row])), [rows]);
  const plotRows = useMemo<readonly PlotRow[]>(
    () =>
      rows.map((row) => ({
        key: row.key,
        values: row.amounts.map(plotNumber),
        totalLabel: formatCompact(row.total),
      })),
    [rows],
  );

  const select = useCallback((key: string) => onSelect?.({ row: key, band: null }), [onSelect]);
  const reportActive = useEnterToSelect(containerRef, onSelect === undefined ? undefined : select);

  const renderTooltip = ({ active, label }: TooltipArgs) => {
    const row = typeof label === "string" ? byKey.get(label) : undefined;
    if (active !== true || row === undefined) {
      return null;
    }
    const money = (value: string) => formatMoney(value, currency, { variant: "inline" });
    return (
      <TooltipCard
        heading={row.label}
        lines={labels.map((band, index) => ({
          key: String(index),
          label: band,
          value: money(row.amounts[index] ?? "0"),
          colour: bandColour(index),
        }))}
        total={{ key: "total", label: t("common.chart.column.total"), value: money(row.total) }}
      />
    );
  };

  return (
    <div ref={containerRef} className="min-w-0 tabular-nums">
      <BarChart
        layout="vertical"
        width={width}
        height={rows.length * ROW_HEIGHT + 32}
        data={plotRows}
        margin={{ ...PLOT_MARGIN, right: 64 }}
        barCategoryGap="25%"
      >
        <ChartPatterns id={id} />
        <CartesianGrid horizontal={false} stroke="var(--viz-grid)" />
        <XAxis
          type="number"
          height={24}
          tickCount={5}
          tick={TICK}
          tickLine={false}
          axisLine={{ stroke: "var(--viz-baseline)" }}
          tickFormatter={compactTick}
        />
        <YAxis
          type="category"
          dataKey="key"
          width="auto"
          tick={TICK}
          tickLine={false}
          axisLine={false}
          tickFormatter={(key: unknown) =>
            typeof key === "string" ? (byKey.get(key)?.label ?? "") : ""
          }
        />
        <Tooltip
          isAnimationActive={false}
          cursor={{ fill: "var(--bg-hover)" }}
          content={renderTooltip}
        />
        {labels.map((label, index) => {
          const paint = paintFor({ id, colour: bandColour(index), slot: index, forced });
          return (
            <Bar
              key={label}
              dataKey={(row: PlotRow) => row.values[index] ?? 0}
              name={label}
              stackId="rpo"
              isAnimationActive={false}
              onClick={(item: { readonly payload?: unknown }) => {
                const key = rowKey(item.payload);
                if (key !== undefined) {
                  onSelect?.({ row: key, band: index });
                }
              }}
              shape={(bar: BarBox) => (
                <rect {...boxOf(bar)} {...paint} data-band={index} data-row={rowKey(bar.payload)} />
              )}
            >
              {index === labels.length - 1 ? (
                <LabelList
                  dataKey="totalLabel"
                  position="right"
                  fontSize={12}
                  fill="var(--viz-label)"
                />
              ) : null}
            </Bar>
          );
        })}
        <ActiveLabel onChange={reportActive} />
      </BarChart>
    </div>
  );
}

export function RpoTimeBands({
  title,
  subtitle,
  currency,
  boundaries,
  rows,
  rowHeader,
  controls,
  footnote,
  state = "ready",
  emptyText,
  errorTitle,
  onRetry,
  onSelect,
  headingLevel,
}: RpoTimeBandsProps) {
  const labels = rpoBandLabels(boundaries);
  if (STRICT && rows.length > MAX_ROWS) {
    throw new Error(`An RPO chart holds at most ${String(MAX_ROWS)} rows (DS-CH-03)`);
  }
  if (STRICT && rows.some((row) => row.amounts.length !== labels.length)) {
    throw new Error("Every RPO row needs one amount per returned band (DS-CH-03)");
  }
  const total = rows[0];
  const summary =
    total === undefined
      ? title
      : t("common.chart.rpo.summary", {
          row: total.label,
          bands: formatList(
            labels.map(
              (label, index) => `${label} ${spokenMoney(total.amounts[index] ?? "0", currency)}`,
            ),
            "unit",
          ),
          total: spokenMoney(total.total, currency),
        });

  const chartDisabledReason =
    labels.length > MAX_CHART_BANDS ? t("common.chart.rpo.tooManyBands") : undefined;

  const table = (
    <ChartTable
      caption={title}
      columns={[
        { key: "row", label: rowHeader },
        // The band label and the code are joined in code: a message of placeholders alone fails
        // the DS-I18N-06 pseudo-localisation test.
        ...labels.map((label, index) => ({
          key: `band-${String(index)}`,
          label: `${label} (${currency})`,
          numeric: true,
        })),
        { key: "total", label: t("common.chart.rpo.column.total", { currency }), numeric: true },
      ]}
      rows={rows.map((row) => ({
        key: row.key,
        cells: [
          row.label,
          ...row.amounts.map((amount) => formatMoney(amount, currency)),
          formatMoney(row.total, currency),
        ],
      }))}
    />
  );

  return (
    <ChartPanel
      title={title}
      subtitle={subtitle}
      summary={summary}
      legend={labels.map((label, index) => ({
        key: String(index),
        label,
        colour: bandColour(index),
      }))}
      controls={controls}
      footnote={footnote}
      state={state}
      emptyText={emptyText}
      errorTitle={errorTitle}
      onRetry={onRetry}
      chartDisabledReason={chartDisabledReason}
      headingLevel={headingLevel}
      chart={<RpoPlot rows={rows} labels={labels} currency={currency} onSelect={onSelect} />}
      table={table}
    />
  );
}
