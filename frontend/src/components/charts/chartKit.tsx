// Shared parts of the chart module (DESIGN_SYSTEM §5.2, DS-VIZ-08, DS-VIZ-09; DS-CMP-14). Recharts is
// imported only under this directory (DS-LINT-08). Figures on screen are the API's decimal strings
// through the format module; `plotNumber` converts a copy to a JavaScript number for pixel geometry
// only, and nothing plotted is summed into a displayed figure (DG-FE-08; SPEC-Q-244).
import { Fragment, type RefObject, useCallback, useEffect, useId, useRef, useState } from "react";
import { useActiveTooltipLabel } from "recharts";

import { formatCompact, formatMoney, NBSP } from "../../lib/format";
import { cn } from "../ui/cn";

/** Plot height of the Recharts charts in comfortable density. */
export const PLOT_HEIGHT = 280;

/** DS-VIZ-09 plot margins; the inline-start side fits the widest tick label (`width="auto"`). */
export const PLOT_MARGIN = { top: 8, right: 12, bottom: 0, left: 0 } as const;

/** DS-VIZ-09 tick labels: caption size in `--viz-tick`; the plot wrapper sets tabular numerals. */
export const TICK = { fill: "var(--viz-tick)", fontSize: 12 } as const;

/** The plot width before the panel is measured, and wherever no ResizeObserver exists. */
export const FALLBACK_WIDTH = 640;

// Copy and size defects throw in development and tests; a production build still renders.
export const STRICT = import.meta.env.DEV || import.meta.env.MODE === "test";

const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/;

interface Digits {
  readonly negative: boolean;
  readonly integer: string;
  readonly fraction: string;
}

function digitsOf(value: string): Digits {
  const match = DECIMAL.exec(value);
  if (match === null) {
    throw new Error(`Not a decimal string: ${value}`);
  }
  const integer = (match[2] ?? "0").replace(/^0+(?=\d)/, "");
  const fraction = (match[3] ?? "").replace(/0+$/, "");
  const zero = integer === "0" && fraction === "";
  return { negative: match[1] === "-" && !zero, integer, fraction };
}

/** Orders two decimal strings on their digits, without converting either to a number. */
export function compareDecimal(a: string, b: string): -1 | 0 | 1 {
  const x = digitsOf(a);
  const y = digitsOf(b);
  if (x.negative !== y.negative) {
    return x.negative ? -1 : 1;
  }
  let magnitude: -1 | 0 | 1;
  if (x.integer.length !== y.integer.length) {
    magnitude = x.integer.length < y.integer.length ? -1 : 1;
  } else {
    const width = Math.max(x.fraction.length, y.fraction.length);
    const left = x.integer + x.fraction.padEnd(width, "0");
    const right = y.integer + y.fraction.padEnd(width, "0");
    magnitude = left === right ? 0 : left < right ? -1 : 1;
  }
  if (magnitude === 0 || !x.negative) {
    return magnitude;
  }
  return magnitude === 1 ? -1 : 1;
}

/** A decimal string as a number for pixel geometry only; never displayed or summed into a figure. */
export function plotNumber(amount: string): number {
  if (!DECIMAL.test(amount)) {
    throw new Error(`Not a decimal string: ${amount}`);
  }
  return Number(amount);
}

/** Money with its code for accessible names and summaries, with an ordinary space after the code. */
export function spokenMoney(value: string, currency: string): string {
  return formatMoney(value, currency, { variant: "inline" }).replace(NBSP, " ");
}

const PLAIN_NUMBER = /^-?\d+(?:\.\d+)?$/;

/** DS-FMT-15 compact tick labels over Recharts' tick values. */
export function compactTick(value: unknown): string {
  const text = typeof value === "number" || typeof value === "string" ? String(value) : "";
  return PLAIN_NUMBER.test(text) ? formatCompact(text) : "";
}

/** DS-FMT-31 compact delta: `+36K` for an increase; a decrease keeps the tenant negative style. */
export function compactDelta(value: string): string {
  const text = formatCompact(value);
  return compareDecimal(value, "0") > 0 && /[1-9]/.test(text) ? `+${text}` : text;
}

/** The measured content width of the plot wrapper. */
export function useElementWidth(ref: RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(FALLBACK_WIDTH);
  useEffect(() => {
    const element = ref.current;
    if (element === null || typeof ResizeObserver === "undefined") {
      return undefined;
    }
    const observer = new ResizeObserver((entries) => {
      const next = Math.floor(entries[0]?.contentRect.width ?? 0);
      if (next > 0) {
        setWidth(next);
      }
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, [ref]);
  return width;
}

const FORCED_COLORS = "(forced-colors: active)";

function forcedColorsActive(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia(FORCED_COLORS).matches
    : false;
}

/** Whether `forced-colors: active` applies, so series switch to CanvasText textures (DS-VIZ-08). */
export function useForcedColors(): boolean {
  const [forced, setForced] = useState(forcedColorsActive);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      return undefined;
    }
    const query = window.matchMedia(FORCED_COLORS);
    const onChange = () => {
      setForced(query.matches);
    };
    query.addEventListener("change", onChange);
    return () => {
      query.removeEventListener("change", onChange);
    };
  }, []);
  return forced;
}

/** An id usable inside `url(#…)` references. */
export function useChartId(): string {
  return `chart${useId().replace(/[^A-Za-z0-9]/g, "")}`;
}

function Hatch({
  id,
  angle,
  colour,
}: {
  readonly id: string;
  readonly angle: number;
  readonly colour: string;
}) {
  return (
    <pattern
      id={id}
      width={6}
      height={6}
      patternUnits="userSpaceOnUse"
      patternTransform={`rotate(${String(angle)})`}
    >
      <line x1={0} y1={0} x2={0} y2={6} stroke={colour} strokeWidth={1.5} />
    </pattern>
  );
}

/** DS-VIZ-08 textures: the Awaiting trigger hatch and the forced-colours fills. */
export function ChartPatterns({ id }: { readonly id: string }) {
  return (
    <defs>
      <Hatch id={`${id}-awaiting`} angle={45} colour="var(--viz-awaiting)" />
      <Hatch id={`${id}-hatch`} angle={45} colour="CanvasText" />
      <Hatch id={`${id}-hatch-reverse`} angle={135} colour="CanvasText" />
      <pattern id={`${id}-dots`} width={6} height={6} patternUnits="userSpaceOnUse">
        <circle cx={3} cy={3} r={1.25} fill="CanvasText" />
      </pattern>
    </defs>
  );
}

type ForcedTexture = "solid" | "hatch" | "hatch-reverse" | "dots" | "none";

// DS-VIZ-08: under forced colours every series is a CanvasText stroke with fills in slot order.
const FORCED_TEXTURES: readonly ForcedTexture[] = [
  "solid",
  "hatch",
  "hatch-reverse",
  "dots",
  "none",
];

export interface Paint {
  readonly fill: string;
  readonly stroke: string;
  readonly strokeWidth: number;
  readonly strokeDasharray?: string | undefined;
}

export interface PaintOptions {
  /** The chart's `useChartId`, which names its patterns. */
  readonly id: string;
  readonly colour: string;
  /** The series slot, from 0. */
  readonly slot: number;
  readonly forced: boolean;
  readonly awaiting?: boolean;
}

/** Fill and stroke of one series (DS-VIZ-08, DS-VIZ-09: 1 px `--bg-surface` between segments). */
export function paintFor({ id, colour, slot, forced, awaiting = false }: PaintOptions): Paint {
  if (forced) {
    const texture = FORCED_TEXTURES[Math.min(slot, FORCED_TEXTURES.length - 1)] ?? "none";
    const fill =
      texture === "solid" ? "CanvasText" : texture === "none" ? "none" : `url(#${id}-${texture})`;
    return { fill, stroke: "CanvasText", strokeWidth: 1 };
  }
  if (awaiting) {
    return {
      fill: `url(#${id}-awaiting)`,
      stroke: "var(--viz-awaiting)",
      strokeWidth: 1.5,
      strokeDasharray: "4 3",
    };
  }
  return { fill: colour, stroke: "var(--bg-surface)", strokeWidth: 1 };
}

/** The drawn box of a Recharts bar, normalised to a non-negative height and width. */
export interface BarBox {
  readonly x?: number | undefined;
  readonly y?: number | undefined;
  readonly width?: number | undefined;
  readonly height?: number | undefined;
  readonly payload?: unknown;
}

export function boxOf(bar: BarBox): {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
} {
  const x = bar.x ?? 0;
  const y = bar.y ?? 0;
  const width = bar.width ?? 0;
  const height = bar.height ?? 0;
  return {
    x: width < 0 ? x + width : x,
    y: height < 0 ? y + height : y,
    width: Math.abs(width),
    height: Math.abs(height),
  };
}

/** The `key` member of a plotted row, which the charts use as the category value. */
export function rowKey(payload: unknown): string | undefined {
  if (typeof payload === "object" && payload !== null && "key" in payload) {
    const key = (payload as { readonly key: unknown }).key;
    return typeof key === "string" ? key : undefined;
  }
  return undefined;
}

/** Reports the category that Recharts' keyboard or pointer navigation made active. */
export function ActiveLabel({
  onChange,
}: {
  readonly onChange: (label: string | undefined) => void;
}) {
  const label = useActiveTooltipLabel();
  useEffect(() => {
    onChange(label === undefined ? undefined : String(label));
  }, [label, onChange]);
  return null;
}

/**
 * DS-CMP-14 keyboard: Enter inside the plot drills down on the active category. Returns the callback
 * that `ActiveLabel` reports to.
 */
export function useEnterToSelect(
  ref: RefObject<HTMLElement | null>,
  select: ((key: string) => void) | undefined,
): (label: string | undefined) => void {
  const active = useRef<string | undefined>(undefined);
  useEffect(() => {
    const element = ref.current;
    if (element === null || select === undefined) {
      return undefined;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Enter" && active.current !== undefined) {
        event.preventDefault();
        select(active.current);
      }
    };
    element.addEventListener("keydown", onKeyDown);
    return () => {
      element.removeEventListener("keydown", onKeyDown);
    };
  }, [ref, select]);
  return useCallback((label: string | undefined) => {
    active.current = label;
  }, []);
}

export type SwatchTexture = "solid" | "hatch";

export function Swatch({
  colour,
  texture = "solid",
}: {
  readonly colour: string;
  readonly texture?: SwatchTexture | undefined;
}) {
  const id = useChartId();
  return (
    <svg
      aria-hidden="true"
      width={10}
      height={10}
      viewBox="0 0 10 10"
      data-swatch={colour}
      className="shrink-0"
    >
      {texture === "hatch" ? (
        <>
          <defs>
            <Hatch id={`${id}-swatch`} angle={45} colour={colour} />
          </defs>
          <rect
            x={0.75}
            y={0.75}
            width={8.5}
            height={8.5}
            fill={`url(#${id}-swatch)`}
            stroke={colour}
            strokeWidth={1.5}
            strokeDasharray="2 1.5"
          />
        </>
      ) : (
        <rect width={10} height={10} fill={colour} />
      )}
    </svg>
  );
}

export interface LegendEntry {
  readonly key: string;
  readonly label: string;
  readonly colour: string;
  readonly texture?: SwatchTexture | undefined;
}

/** DS-CMP-14 legend: inline at the top start, 10 px swatches with labels. */
export function ChartLegend({ entries }: { readonly entries: readonly LegendEntry[] }) {
  return (
    <ul data-chart-legend="" className="flex flex-wrap gap-x-4 gap-y-1">
      {entries.map((entry) => (
        <li key={entry.key} className="inline-flex items-center gap-1.5 text-caption text-fg-2">
          <Swatch colour={entry.colour} texture={entry.texture} />
          {entry.label}
        </li>
      ))}
    </ul>
  );
}

export interface TooltipLine {
  readonly key: string;
  readonly label: string;
  readonly value: string;
  readonly colour?: string | undefined;
  readonly texture?: SwatchTexture | undefined;
}

/** DS-CMP-14 tooltip (E2): heading, one row per series with full values, and a total row. */
export function TooltipCard({
  heading,
  lines,
  total,
}: {
  readonly heading: string;
  readonly lines: readonly TooltipLine[];
  readonly total?: TooltipLine | undefined;
}) {
  return (
    <div
      data-chart-tooltip=""
      className="flex flex-col gap-1 rounded-sm border border-hairline bg-raised px-2.5 py-2 text-caption text-fg-1 shadow-popover"
    >
      <p className="font-semibold">{heading}</p>
      <dl className="grid grid-cols-[auto_auto] items-center gap-x-4 gap-y-0.5">
        {lines.map((line) => (
          <Fragment key={line.key}>
            <dt className="inline-flex items-center gap-1.5 text-fg-2">
              {line.colour === undefined ? null : (
                <Swatch colour={line.colour} texture={line.texture} />
              )}
              {line.label}
            </dt>
            <dd className="num text-end">{line.value}</dd>
          </Fragment>
        ))}
        {total === undefined ? null : (
          <>
            <dt className="border-t border-hairline pt-0.5 font-medium">{total.label}</dt>
            <dd className="num border-t border-hairline pt-0.5 text-end font-medium">
              {total.value}
            </dd>
          </>
        )}
      </dl>
    </div>
  );
}

export interface TableColumn {
  readonly key: string;
  readonly label: string;
  readonly numeric?: boolean;
}

export interface TableRow {
  readonly key: string;
  /** The row header, then one formatted figure per numeric column. */
  readonly cells: readonly string[];
  /** A totals row with its rule (DS-ELV-02). */
  readonly emphasis?: boolean;
}

function ChartTableRow({
  row,
  columns,
}: {
  readonly row: TableRow;
  readonly columns: readonly TableColumn[];
}) {
  const emphasis = row.emphasis === true;
  return (
    <tr className={cn(emphasis && "border-t border-control")}>
      {row.cells.map((cell, index) => {
        const key = columns[index]?.key ?? String(index);
        return index === 0 ? (
          <th
            key={key}
            scope="row"
            className={cn(
              "px-3 py-1.5 text-start text-fg-1",
              emphasis ? "font-semibold" : "font-normal",
            )}
          >
            {cell}
          </th>
        ) : (
          <td
            key={key}
            className={cn("num px-3 py-1.5 text-end text-fg-1", emphasis && "font-semibold")}
          >
            {cell}
          </td>
        );
      })}
    </tr>
  );
}

/** The complete non-visual equivalent of a chart (DS-VIZ-00, DS-A11Y-13). */
export function ChartTable({
  caption,
  columns,
  rows,
  footer,
}: {
  readonly caption: string;
  readonly columns: readonly TableColumn[];
  readonly rows: readonly TableRow[];
  readonly footer?: TableRow | undefined;
}) {
  return (
    <div className="overflow-x-auto">
      <table data-chart-table="" className="w-full border-collapse text-body-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={cn(
                  "border-b border-hairline px-3 py-2 text-caption font-medium text-fg-3",
                  column.numeric === true ? "text-end" : "text-start",
                )}
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <ChartTableRow key={row.key} row={row} columns={columns} />
          ))}
        </tbody>
        {footer === undefined ? null : (
          <tfoot>
            <ChartTableRow row={{ ...footer, emphasis: true }} columns={columns} />
          </tfoot>
        )}
      </table>
    </div>
  );
}
