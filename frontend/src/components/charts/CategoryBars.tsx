// Category bars (DESIGN_SYSTEM DS-CH-06; DS-VIZ-00 "plain bars for disaggregation") in a chart panel
// (DS-CMP-14): one horizontal bar per category, the largest first, in the DS-VIZ-01 slots in that order.
// The chart computes no figure: it orders the API's amounts and draws them, and it folds nothing into an
// "Other" bar, which would be a sum of its own. More than seven categories leave only the Table view,
// which lists every one of them with the total the API states.
import { type ReactNode, useCallback, useMemo, useRef } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, Tooltip, XAxis, YAxis } from "recharts";

import { formatCompact, formatList, formatMoney } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { ChartPanel, type ChartPanelState } from "./ChartPanel";
import {
  ActiveLabel,
  type BarBox,
  boxOf,
  ChartPatterns,
  ChartTable,
  compactTick,
  compareDecimal,
  paintFor,
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

export interface Category {
  readonly key: string;
  readonly label: string;
  readonly amount: string;
}

export interface CategoryBarsProps {
  readonly title: string;
  readonly subtitle?: string | undefined;
  readonly currency: string;
  /** The header of the category column, for example "Revenue category". */
  readonly categoryHeader: string;
  /** The categories as the API returns them; the chart orders them by amount, the largest first. */
  readonly categories: readonly Category[];
  /** The total the API states for the categories; the Table view ends with it. */
  readonly total?: string | undefined;
  readonly controls?: ReactNode;
  readonly footnote?: ReactNode;
  readonly state?: ChartPanelState;
  readonly emptyText?: string | undefined;
  readonly errorTitle?: string | undefined;
  readonly onRetry?: (() => void) | undefined;
  /** Opens the report filtered to the category. */
  readonly onSelect?: ((key: string) => void) | undefined;
  readonly headingLevel?: 2 | 3;
}

/** DS-VIZ-03: at most seven named series; the chart folds none into "Other". */
export const MAX_CATEGORIES = 7;

const ROW_HEIGHT = 36;

/** DS-VIZ-01: the categorical slots, assigned in order without skipping. */
function slotColour(index: number): string {
  return `var(--viz-${String(index + 1)})`;
}

/**
 * The categories by descending amount (DS-VIZ-03). The sort is stable, so equal amounts keep the API's
 * order.
 */
export function orderedCategories(categories: readonly Category[]): readonly Category[] {
  return [...categories].sort((left, right) => compareDecimal(right.amount, left.amount));
}

interface PlotRow {
  readonly key: string;
  readonly value: number;
  readonly display: string;
}

interface TooltipArgs {
  readonly active?: boolean | undefined;
  readonly label?: unknown;
}

function CategoryPlot({
  categories,
  currency,
  onSelect,
}: {
  readonly categories: readonly Category[];
  readonly currency: string;
  readonly onSelect: ((key: string) => void) | undefined;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const width = useElementWidth(containerRef);
  const forced = useForcedColors();
  const id = useChartId();
  const byKey = useMemo(
    () => new Map(categories.map((category, index) => [category.key, { category, index }])),
    [categories],
  );
  const rows = useMemo<readonly PlotRow[]>(
    () =>
      categories.map((category) => ({
        key: category.key,
        value: plotNumber(category.amount),
        display: formatCompact(category.amount),
      })),
    [categories],
  );

  const select = useCallback((key: string) => onSelect?.(key), [onSelect]);
  const reportActive = useEnterToSelect(containerRef, onSelect === undefined ? undefined : select);

  const renderTooltip = ({ active, label }: TooltipArgs) => {
    const found = typeof label === "string" ? byKey.get(label) : undefined;
    if (active !== true || found === undefined) {
      return null;
    }
    return (
      <TooltipCard
        heading={found.category.label}
        lines={[
          {
            key: "amount",
            label: t("common.chart.tooltip.amount"),
            value: formatMoney(found.category.amount, currency, { variant: "inline" }),
            colour: slotColour(found.index),
          },
        ]}
      />
    );
  };

  return (
    <div ref={containerRef} className="min-w-0 tabular-nums">
      <BarChart
        layout="vertical"
        width={width}
        height={rows.length * ROW_HEIGHT + 32}
        data={rows}
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
            typeof key === "string" ? (byKey.get(key)?.category.label ?? "") : ""
          }
        />
        <Tooltip
          isAnimationActive={false}
          cursor={{ fill: "var(--bg-hover)" }}
          content={renderTooltip}
        />
        <Bar
          dataKey="value"
          isAnimationActive={false}
          onClick={(item: { readonly payload?: unknown }) => {
            const key = rowKey(item.payload);
            if (key !== undefined) {
              onSelect?.(key);
            }
          }}
          shape={(bar: BarBox) => {
            const key = rowKey(bar.payload);
            const slot = key === undefined ? 0 : (byKey.get(key)?.index ?? 0);
            return (
              <rect
                {...boxOf(bar)}
                {...paintFor({ id, colour: slotColour(slot), slot, forced })}
                data-category={key}
              />
            );
          }}
        >
          <LabelList dataKey="display" position="right" fontSize={12} fill="var(--viz-label)" />
        </Bar>
        <ActiveLabel onChange={reportActive} />
      </BarChart>
    </div>
  );
}

export function CategoryBars({
  title,
  subtitle,
  currency,
  categoryHeader,
  categories,
  total,
  controls,
  footnote,
  state = "ready",
  emptyText,
  errorTitle,
  onRetry,
  onSelect,
  headingLevel,
}: CategoryBarsProps) {
  const ordered = orderedCategories(categories);
  const summary =
    ordered.length === 0
      ? title
      : t("common.chart.categories.summary", {
          title,
          values: formatList(
            ordered.map(
              (category) => `${category.label} ${spokenMoney(category.amount, currency)}`,
            ),
            "unit",
          ),
        });

  const chartDisabledReason =
    ordered.length > MAX_CATEGORIES ? t("common.chart.categories.tooMany") : undefined;

  const table = (
    <ChartTable
      caption={title}
      columns={[
        { key: "category", label: categoryHeader },
        {
          key: "amount",
          label: t("common.chart.categories.column.amount", { currency }),
          numeric: true,
        },
      ]}
      rows={ordered.map((category) => ({
        key: category.key,
        cells: [category.label, formatMoney(category.amount, currency)],
      }))}
      footer={
        total === undefined
          ? undefined
          : { key: "total", cells: [t("common.chart.column.total"), formatMoney(total, currency)] }
      }
    />
  );

  return (
    <ChartPanel
      title={title}
      subtitle={subtitle}
      summary={summary}
      controls={controls}
      footnote={footnote}
      state={state}
      emptyText={emptyText}
      errorTitle={errorTitle}
      onRetry={onRetry}
      chartDisabledReason={chartDisabledReason}
      headingLevel={headingLevel}
      chart={<CategoryPlot categories={ordered} currency={currency} onSelect={onSelect} />}
      table={table}
    />
  );
}
