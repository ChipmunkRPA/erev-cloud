// Rollforward bridge (DESIGN_SYSTEM DS-CH-02) in a chart panel (DS-CMP-14): opening, activity and
// closing bars on a category axis in the API's order. Totals start at zero in `--viz-total`; activity
// floats from the running level, increases in `--viz-increase` and decreases in `--viz-decrease`, joined
// by dashed connectors. The chart computes no figure: when the API flags that opening plus activity does
// not equal closing, a negative banner replaces the plot. The running level is geometry only
// (SPEC-Q-244).
import { type ReactNode, useCallback, useMemo, useRef } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Text,
  Tooltip,
  useXAxisScale,
  useYAxisScale,
  XAxis,
  YAxis,
} from "recharts";

import { formatCompact, formatMoney } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { Banner } from "../feedback/Banner";
import { ChartPanel, type ChartPanelState } from "./ChartPanel";
import {
  ActiveLabel,
  type BarBox,
  boxOf,
  ChartPatterns,
  ChartTable,
  compactDelta,
  compactTick,
  compareDecimal,
  paintFor,
  PLOT_HEIGHT,
  PLOT_MARGIN,
  plotNumber,
  rowKey,
  spokenMoney,
  TICK,
  TooltipCard,
  useChartId,
  useElementWidth,
  useEnterToSelect,
  useForcedColors,
} from "./chartKit";

/** `TOTAL`: opening, closing and subtotal bars from zero; `ACTIVITY`: a movement from the running level. */
export type BridgeKind = "TOTAL" | "ACTIVITY";

export interface BridgeCategory {
  readonly key: string;
  readonly label: string;
  readonly kind: BridgeKind;
  readonly amount: string;
}

/** The API's integrity flag: whether opening plus activity equals closing, and the difference. */
export interface BridgeIntegrity {
  readonly balanced: boolean;
  readonly difference: string;
}

export interface RollforwardBridgeProps {
  readonly title: string;
  readonly subtitle?: string | undefined;
  readonly currency: string;
  readonly categories: readonly BridgeCategory[];
  readonly integrity: BridgeIntegrity;
  readonly controls?: ReactNode;
  readonly footnote?: ReactNode;
  readonly state?: ChartPanelState;
  readonly emptyText?: string | undefined;
  readonly errorTitle?: string | undefined;
  readonly onRetry?: (() => void) | undefined;
  /** Opens the rollforward detail filtered to the category. */
  readonly onSelect?: ((key: string) => void) | undefined;
  readonly headingLevel?: 2 | 3;
}

type Tone = "total" | "increase" | "decrease";

const TONE_COLOUR: Readonly<Record<Tone, string>> = {
  total: "var(--viz-total)",
  increase: "var(--viz-increase)",
  decrease: "var(--viz-decrease)",
};

const TONE_SLOT: Readonly<Record<Tone, number>> = { total: 0, increase: 1, decrease: 2 };

interface BridgeRow {
  readonly key: string;
  readonly range: readonly [number, number];
  readonly end: number;
  readonly tone: Tone;
  readonly display: string;
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

function CategoryTick({ tick, label }: { readonly tick: TickArgs; readonly label: string }) {
  const xScale = useXAxisScale();
  const key = typeof tick.payload?.value === "string" ? tick.payload.value : "";
  const start = xScale?.(key, { position: "start" });
  const end = xScale?.(key, { position: "end" });
  const width = start === undefined || end === undefined ? undefined : end - start;
  return (
    <Text
      x={tick.x}
      y={tick.y}
      {...(width === undefined ? {} : { width })}
      maxLines={2}
      textAnchor="middle"
      verticalAnchor="start"
      fontSize={12}
      fill="var(--viz-tick)"
    >
      {label}
    </Text>
  );
}

function BridgeConnectors({ rows }: { readonly rows: readonly BridgeRow[] }) {
  const xScale = useXAxisScale();
  const yScale = useYAxisScale();
  if (xScale === undefined || yScale === undefined) {
    return null;
  }
  return (
    <g data-bridge-connectors="">
      {rows.slice(0, -1).map((row, index) => {
        const next = rows[index + 1];
        const x1 = xScale(row.key, { position: "end" });
        const x2 = next === undefined ? undefined : xScale(next.key, { position: "start" });
        const y = yScale(row.end);
        if (x1 === undefined || x2 === undefined || y === undefined) {
          return null;
        }
        return (
          <line
            key={row.key}
            data-connector=""
            x1={x1}
            x2={x2}
            y1={y}
            y2={y}
            stroke="var(--viz-baseline)"
            strokeWidth={1}
            strokeDasharray="3 3"
          />
        );
      })}
    </g>
  );
}

function BridgePlot({
  categories,
  currency,
  onSelect,
}: {
  readonly categories: readonly BridgeCategory[];
  readonly currency: string;
  readonly onSelect: ((key: string) => void) | undefined;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const width = useElementWidth(containerRef);
  const forced = useForcedColors();
  const id = useChartId();
  const byKey = useMemo(
    () => new Map(categories.map((category) => [category.key, category])),
    [categories],
  );

  const rows = useMemo<readonly BridgeRow[]>(() => {
    let level = 0;
    return categories.map((category) => {
      const amount = plotNumber(category.amount);
      if (category.kind === "TOTAL") {
        level = amount;
        return {
          key: category.key,
          range: [Math.min(0, amount), Math.max(0, amount)],
          end: amount,
          tone: "total",
          display: formatCompact(category.amount),
        };
      }
      const start = level;
      level += amount;
      return {
        key: category.key,
        range: [Math.min(start, level), Math.max(start, level)],
        end: level,
        tone: compareDecimal(category.amount, "0") < 0 ? "decrease" : "increase",
        display: compactDelta(category.amount),
      };
    });
  }, [categories]);

  const select = useCallback((key: string) => onSelect?.(key), [onSelect]);
  const reportActive = useEnterToSelect(containerRef, onSelect === undefined ? undefined : select);

  const renderTooltip = ({ active, label }: TooltipArgs) => {
    const category = typeof label === "string" ? byKey.get(label) : undefined;
    if (active !== true || category === undefined) {
      return null;
    }
    return (
      <TooltipCard
        heading={category.label}
        lines={[
          {
            key: "amount",
            label: t("common.chart.tooltip.amount"),
            value: formatMoney(category.amount, currency, {
              variant: "inline",
              delta: category.kind === "ACTIVITY",
            }),
          },
        ]}
      />
    );
  };

  return (
    <div ref={containerRef} className="min-w-0 tabular-nums">
      <BarChart
        width={width}
        height={PLOT_HEIGHT}
        data={rows}
        margin={{ ...PLOT_MARGIN, top: 20 }}
        barCategoryGap="25%"
      >
        <ChartPatterns id={id} />
        <CartesianGrid vertical={false} stroke="var(--viz-grid)" />
        <XAxis
          dataKey="key"
          height={36}
          interval={0}
          tickLine={false}
          axisLine={{ stroke: "var(--viz-baseline)" }}
          tick={(tick: TickArgs) => (
            <CategoryTick
              tick={tick}
              label={
                typeof tick.payload?.value === "string"
                  ? (byKey.get(tick.payload.value)?.label ?? "")
                  : ""
              }
            />
          )}
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
        <Bar
          dataKey="range"
          isAnimationActive={false}
          onClick={(item: { readonly payload?: unknown }) => {
            const key = rowKey(item.payload);
            if (key !== undefined) {
              onSelect?.(key);
            }
          }}
          shape={(bar: BarBox) => {
            const row = rows.find((candidate) => candidate.key === rowKey(bar.payload));
            const tone = row?.tone ?? "total";
            return (
              <rect
                {...boxOf(bar)}
                {...paintFor({ id, colour: TONE_COLOUR[tone], slot: TONE_SLOT[tone], forced })}
                data-category={row?.key}
                data-tone={tone}
              />
            );
          }}
        >
          <LabelList dataKey="display" position="top" fontSize={12} fill="var(--viz-label)" />
        </Bar>
        <BridgeConnectors rows={rows} />
        <ActiveLabel onChange={reportActive} />
      </BarChart>
    </div>
  );
}

export function RollforwardBridge({
  title,
  subtitle,
  currency,
  categories,
  integrity,
  controls,
  footnote,
  state = "ready",
  emptyText,
  errorTitle,
  onRetry,
  onSelect,
  headingLevel,
}: RollforwardBridgeProps) {
  const unbalanced = t("common.chart.bridge.unbalanced", {
    difference: spokenMoney(integrity.difference, currency),
  });
  const totals = categories.filter((category) => category.kind === "TOTAL");
  const opening = totals[0];
  const closing = totals[totals.length - 1];
  const summary = !integrity.balanced
    ? unbalanced
    : opening === undefined || closing === undefined
      ? title
      : t("common.chart.bridge.summary", {
          title,
          from: opening.label,
          opening: spokenMoney(opening.amount, currency),
          to: closing.label,
          closing: spokenMoney(closing.amount, currency),
        });

  const legend = [
    { key: "total", label: t("common.chart.bridge.legend.total"), colour: TONE_COLOUR.total },
    {
      key: "increase",
      label: t("common.chart.bridge.legend.increase"),
      colour: TONE_COLOUR.increase,
    },
    {
      key: "decrease",
      label: t("common.chart.bridge.legend.decrease"),
      colour: TONE_COLOUR.decrease,
    },
  ];

  const chart = integrity.balanced ? (
    <BridgePlot categories={categories} currency={currency} onSelect={onSelect} />
  ) : (
    <Banner tone="negative" announce="static" title={unbalanced} headingLevel={4} />
  );

  const table = (
    <ChartTable
      caption={title}
      columns={[
        { key: "category", label: t("common.chart.bridge.column.category") },
        {
          key: "amount",
          label: t("common.chart.bridge.column.amount", { currency }),
          numeric: true,
        },
      ]}
      rows={categories.map((category) => ({
        key: category.key,
        cells: [category.label, formatMoney(category.amount, currency)],
        emphasis: category.kind === "TOTAL",
      }))}
    />
  );

  return (
    <ChartPanel
      title={title}
      subtitle={subtitle}
      summary={summary}
      legend={integrity.balanced ? legend : undefined}
      controls={controls}
      footnote={footnote}
      state={state}
      emptyText={emptyText}
      errorTitle={errorTitle}
      onRetry={onRetry}
      headingLevel={headingLevel}
      chart={chart}
      table={table}
    />
  );
}
