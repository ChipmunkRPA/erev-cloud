// One report section as a DS-CMP-10 DataGrid (SCREENS_B §5.2 "Sections", RV-09, RV-11, RV-13; §5.6
// RPT-R-02 to RPT-R-04). The section heading is the grid title with its row count; money fields render
// through `<Money>` from API strings; totals rows come from the run and name their currency in the RPT-R-03
// Currency column (DS-CMP-10 item 7). A drillable figure is a grid link:
// click, Enter or `E` asks SB-R-07 for its contributors, and the originating cell receives focus when the
// panel closes (REQ-UX-009).
import { type ReactNode, useId } from "react";

import { DataGrid, testIdKey } from "../../../components/data-grid/DataGrid";
import {
  DEFAULT_WIDTH,
  type GridColumn,
  type GridTotalsRow,
} from "../../../components/data-grid/types";
import { Money } from "../../../components/money/Money";
import { Button } from "../../../components/ui/Button";
import { queryKey } from "../../../lib/api/query-keys";
import type { ReportRow } from "../../../lib/api/queries/reports";
import { formatMoney } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";
import {
  CURRENCY_COLUMN_KEY,
  isMoney,
  type ReportColumn,
  type ReportSection,
  rowLabel,
  rowTestKey,
} from "./specs";

export interface DrillRequest {
  readonly row: ReportRow;
  readonly column: ReportColumn;
  /** The cell that receives focus when the panel closes. */
  readonly element: HTMLElement | null;
}

export interface ReportGridProps {
  readonly runId: string;
  readonly section: ReportSection;
  readonly columns: readonly ReportColumn[];
  readonly totals: readonly GridTotalsRow[];
  readonly onDrill: (request: DrillRequest) => void;
  readonly emptyState?: ReactNode;
  /** The SF id of the host screen: `<SF id>-grid-<name>` and `<SF id>-row-<row>` (SCR-TID-03). */
  readonly testIdPrefix?: string | undefined;
  /** The grid name of the test id; defaults to the section heading normalised. */
  readonly name?: string | undefined;
  /** The grid's accessible name; defaults to the section heading. */
  readonly title?: string | undefined;
  /** The id of the grid's description, for example the SF-06:entries caption (D-88 L7-3-Q-22). */
  readonly describedBy?: string | undefined;
  /** Screen columns after the report's own, for example SF-04 "Flags". */
  readonly extraColumns?: readonly GridColumn<ReportRow>[] | undefined;
}

/** An average `text-body-sm` glyph and the header chrome: cell padding, the column menu and its gap. */
const HEADER_CHAR_PX = 7;
const HEADER_CHROME_PX = 52;
const WIDTH_STEP_PX = 8;

/**
 * A report column holds its header without clipping (DS-AP-10; CLO-26): report headers are data-driven
 * ("Awaiting trigger (USD)", legacy column names), so the width grows from the kind's default with the
 * header's length, in 8 px steps.
 */
export function reportColumnWidth(header: string, kind: ReportColumn["kind"]): number {
  const fit = Math.ceil((header.length * HEADER_CHAR_PX + HEADER_CHROME_PX) / WIDTH_STEP_PX);
  return Math.max(DEFAULT_WIDTH[kind], fit * WIDTH_STEP_PX);
}

function cellOf(element: Element | null): HTMLElement | null {
  const cell = element?.closest<HTMLElement>('[role="gridcell"], [role="rowheader"]') ?? null;
  return cell ?? (element instanceof HTMLElement ? element : null);
}

function textOf(value: unknown): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  return typeof value === "string" ? value : String(value);
}

/** The cell's accessible figure name, for example "Sep 2026 (USD) · SF-ORD-10001". */
export function figureLabel(row: ReportRow, column: ReportColumn): string {
  // The DS-CMP-06 meta separator joins two labels (the context pill's "<code> · <name>").
  return `${column.header} · ${rowLabel(row)}`;
}

export function ReportGrid({
  runId,
  section,
  columns,
  totals,
  onDrill,
  emptyState,
  testIdPrefix = "SF-08",
  name: gridName,
  title,
  describedBy,
  extraColumns = [],
}: ReportGridProps) {
  const headingId = useId();
  const reportColumns: GridColumn<ReportRow>[] = columns.map((column) => {
    const base = {
      id: column.key,
      header: column.header,
      width: reportColumnWidth(column.header, column.kind),
    };
    if (column.kind === "money") {
      const money = (row: ReportRow) => {
        const value = row[column.key];
        return isMoney(value) ? value : null;
      };
      const drill = (row: ReportRow, element: Element | null) => {
        onDrill({ row, column, element: cellOf(element) });
      };
      return {
        ...base,
        kind: "money",
        value: (row) => money(row)?.amount ?? null,
        currency: (row) => money(row)?.currency ?? "",
        render: (row) => {
          const value = money(row);
          if (value === null) {
            return null;
          }
          const figure = <Money value={value.amount} currency={value.currency} variant="cell" />;
          return column.drillable ? (
            <Button
              variant="link"
              tabIndex={-1}
              aria-label={t("common.explain.trigger", {
                label: figureLabel(row, column),
                value: formatMoney(value.amount, value.currency, { variant: "inline" }),
              })}
              onClick={(event) => drill(row, event.currentTarget)}
            >
              {figure}
            </Button>
          ) : (
            figure
          );
        },
        ...(column.drillable
          ? {
              activate: (row: ReportRow) => drill(row, document.activeElement),
              explain: (row: ReportRow) => drill(row, document.activeElement),
            }
          : {}),
      } satisfies GridColumn<ReportRow>;
    }
    if (column.kind === "number") {
      return {
        ...base,
        kind: "number",
        numberKind: "count",
        value: (row) => textOf(row[column.key]),
      } satisfies GridColumn<ReportRow>;
    }
    return {
      ...base,
      kind: column.kind,
      value: (row) => textOf(row[column.key]),
      // RPT-R-03: the Currency column of a mixed-currency result; its totals cells name the row currency.
      ...(column.key === CURRENCY_COLUMN_KEY ? { currencyColumn: true } : {}),
    } satisfies GridColumn<ReportRow>;
  });
  const gridColumns = [...reportColumns, ...extraColumns];
  const name = gridName ?? testIdKey(section.heading);
  const heading = title ?? section.heading;
  const rows = section.rows;
  if (rows.length === 0 && totals.length === 0) {
    // A section without rows is a static region: a grid with no focusable cell would be a scrollable
    // region without keyboard access (axe `scrollable-region-focusable`; DG-E2E-07).
    return (
      <section
        aria-labelledby={headingId}
        data-testid={`${testIdPrefix}-grid-${name}`}
        className="flex flex-col gap-2 rounded-md border border-hairline bg-surface p-4"
      >
        <h2 id={headingId} className="flex items-baseline gap-2 text-title-sm text-fg-1">
          {heading}
          <span className="text-body-sm font-normal text-fg-3">
            {t("reports.report.section.count", { count: 0, formatted: "0" })}
          </span>
        </h2>
        {emptyState}
      </section>
    );
  }
  return (
    <DataGrid<ReportRow>
      name={name}
      title={heading}
      describedBy={describedBy}
      headingLevel={2}
      countLabel={(count, formatted) => t("reports.report.section.count", { count, formatted })}
      errorTitle={t("reports.report.dataLoadError")}
      columns={gridColumns}
      source={{
        queryKey: queryKey("report-run-section", "tenant", {
          runId,
          section: section.number,
          grid: name,
        }),
        fetchPage: () =>
          Promise.resolve({
            items: rows,
            nextCursor: null,
            total: { count: rows.length, capped: false },
          }),
      }}
      rowKey={(row) => row.row_key}
      rowLabel={rowLabel}
      totals={totals}
      emptyState={emptyState}
      testIdPrefix={testIdPrefix}
      rowTestKey={rowTestKey}
    />
  );
}
