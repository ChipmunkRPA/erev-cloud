// RV-10 Chart and table (SCREENS_B §0.5, §5.6 RPT-01 and RPT-06; DESIGN_SYSTEM DS-CMP-14, DS-CH-01,
// DS-CH-03). The chart panel sits above the grid, which is always present. `revenue_waterfall` draws
// DS-CH-01 from the totals row: with measure Total by month a period's figure is recognized when the
// period ends on or before the run's as-of date and scheduled after it (RPT-01 definitions), so the chart
// adds nothing; other granularities, By state or mixed currencies leave the grid only (L7-3-Q-4). `rpo`
// draws DS-CH-03 from the bands of the run's control totals (L6-3-Q-26): the total row, then the first
// eleven rows.
import type { ReactElement, ReactNode } from "react";

import {
  RevenueWaterfall,
  type WaterfallPeriod,
} from "../../../components/charts/RevenueWaterfall";
import { RpoTimeBands, type RpoRow } from "../../../components/charts/RpoTimeBands";
import type { ReportDefinition, ReportRun } from "../../../lib/api/queries/reports";
import type { Period } from "../../../lib/api/queries/tenant";
import { t } from "../../../lib/i18n/t";
import { bookLabel } from "./RunStamp";
import {
  bandBoundaries,
  bucketLabel,
  isMoney,
  PERIOD_COLUMN_PREFIX,
  type ReportSection,
  rowLabel,
  rpoBands,
} from "./specs";

const OPEN_STATES: ReadonlySet<string> = new Set(["open", "closing", "reopened"]);
const NONZERO = /[1-9]/;

function zeroOf(amount: string): string {
  return amount.replace("-", "").replace(/\d/g, "0");
}

function totalOf(
  controlTotals: Readonly<Record<string, unknown>> | null,
  key: string,
  currency: string,
) {
  const value = controlTotals?.[key];
  if (typeof value === "object" && value !== null) {
    const amount = (value as Readonly<Record<string, unknown>>)[currency];
    return typeof amount === "string" ? amount : null;
  }
  return null;
}

function scopeOf(run: ReportRun): string {
  return run.entity_scope.length === 0
    ? t("reports.chart.allEntities")
    : run.entity_scope.map((item) => item.code).join(", ");
}

export interface ReportChartProps {
  readonly definition: ReportDefinition;
  readonly run: ReportRun;
  readonly section: ReportSection;
  readonly periods: readonly Period[];
  /** The panel's test id; SF-08:report `SF-08-chart-<code>`, SF-04 `SF-04-chart-waterfall`. */
  readonly testId?: string | undefined;
  /** The panel's footnote: on SF-08:dashboard the run the panel shows, with its report (§5.5). */
  readonly footnote?: ReactNode;
  /** A mark of DS-CH-01 or DS-CH-03 was chosen: the period, or the row, it stands for. */
  readonly onSelectPeriod?: ((periodKey: string | null) => void) | undefined;
  readonly onSelectRow?: ((rowKey: string) => void) | undefined;
}

export function ReportChart(props: ReportChartProps) {
  return reportChart(props);
}

/**
 * The chart of a run's first section, or null where its figures cannot be drawn as one. A screen that
 * must say so — a dashboard panel has no grid under it — asks here before it renders.
 */
export function reportChart({
  definition,
  run,
  section,
  periods,
  testId,
  footnote,
  onSelectPeriod,
  onSelectRow,
}: ReportChartProps): ReactElement | null {
  const totals = section.totals;
  const totalRow = totals.length === 1 ? totals[0] : undefined;
  const totalMoney = totalRow?.total;
  if (totalRow === undefined || !isMoney(totalMoney)) {
    return null;
  }
  const currency = totalMoney.currency;
  // SCREENS_B §5.2 wireframe title "<chart> · <ISO> · <book>".
  const title = [
    definition.code === "rpo" ? t("reports.chart.rpo") : t("reports.chart.waterfall"),
    currency,
    bookLabel(run.book),
  ].join(" · ");

  if (definition.code === "revenue_waterfall") {
    const granularity = run.parameters.granularity ?? "MONTH";
    const measure = run.parameters.measure ?? "TOTAL";
    const asOf = run.as_of;
    if (granularity !== "MONTH" || measure !== "TOTAL" || asOf === null) {
      return null;
    }
    const chartPeriods: WaterfallPeriod[] = [];
    for (const [key, value] of Object.entries(totalRow)) {
      if (!key.startsWith(PERIOD_COLUMN_PREFIX) || !isMoney(value)) {
        continue;
      }
      const bucket = key.slice(PERIOD_COLUMN_PREFIX.length);
      const found = periods.find((item) => item.period.period_key === bucket);
      if (found === undefined) {
        return null;
      }
      // DG-FE-20: business dates compare as strings.
      const posted = found.period.end_date <= asOf;
      chartPeriods.push({
        key: bucket,
        label: bucketLabel(bucket, periods),
        recognized: posted ? value.amount : zeroOf(value.amount),
        scheduled: posted ? zeroOf(value.amount) : value.amount,
        total: value.amount,
        open: OPEN_STATES.has(found.state),
      });
    }
    const awaiting = totalRow.awaiting_trigger;
    const recognized = totalOf(run.control_totals, "recognized_total", currency);
    const scheduled = totalOf(run.control_totals, "scheduled_total", currency);
    const awaitingTotal = totalOf(run.control_totals, "awaiting_trigger_total", currency);
    if (
      recognized === null ||
      scheduled === null ||
      awaitingTotal === null ||
      chartPeriods.length > 36
    ) {
      return null;
    }
    // A count of rows, not money (SCREENS_B §1.1 permits count arithmetic).
    const pending = section.rows.filter((row) => {
      const amount = row.awaiting_trigger;
      return isMoney(amount) && NONZERO.test(amount.amount);
    }).length;
    return (
      <div data-testid={testId ?? "SF-08-chart-revenue-waterfall"}>
        <RevenueWaterfall
          title={title}
          scope={scopeOf(run)}
          currency={currency}
          periods={chartPeriods}
          awaiting={isMoney(awaiting) ? { amount: awaiting.amount, count: pending } : null}
          totals={{ recognized, scheduled, awaiting: awaitingTotal, total: totalMoney.amount }}
          footnote={footnote}
          onSelect={
            onSelectPeriod === undefined ? undefined : (target) => onSelectPeriod(target.period)
          }
          headingLevel={2}
        />
      </div>
    );
  }

  if (definition.code === "rpo") {
    const bands = rpoBands(run.control_totals);
    if (bands.length === 0) {
      return null;
    }
    const rowOf = (
      key: string,
      label: string,
      row: Readonly<Record<string, unknown>>,
    ): RpoRow | null => {
      const total = row.total;
      const amounts = bands.map((band) => {
        const amount = row[band.key];
        return isMoney(amount) ? amount.amount : null;
      });
      return isMoney(total) && amounts.every((item) => item !== null)
        ? { key, label, total: total.amount, amounts: amounts as string[] }
        : null;
    };
    const rows = [
      rowOf(totalRow.row_key, t("common.grid.total"), totalRow),
      ...section.rows.slice(0, 11).map((row) => rowOf(row.row_key, rowLabel(row), row)),
    ].filter((row): row is RpoRow => row !== null);
    const dimension =
      typeof run.parameters.row_dimension === "string" ? run.parameters.row_dimension : "CONTRACT";
    return (
      <div data-testid={testId ?? "SF-08-chart-rpo"}>
        <RpoTimeBands
          title={title}
          currency={currency}
          boundaries={bandBoundaries(bands)}
          rows={rows}
          rowHeader={t(`reports.parameters.row_dimension.${dimension}`)}
          footnote={footnote}
          onSelect={onSelectRow === undefined ? undefined : (target) => onSelectRow(target.row)}
          headingLevel={2}
        />
      </div>
    );
  }
  return null;
}
