// Sparkline (DESIGN_SYSTEM DS-CH-04): a compact trend inside KPI cells, list rows and grid cells. A small
// SVG, not Recharts, because many can render in one grid. A 1.5 px `--viz-sparkline` line and a 3 px
// end dot in `--fg-1`, with a 1 px `--viz-grid` zero line when the series crosses zero. It has no
// interaction (the parent cell drills down) and is named with the measure, the range, the first and
// last values and the low and high, which are chosen on their digits.
import { formatMoney, NBSP } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { compareDecimal, plotNumber } from "./chartKit";

export interface SparkPoint {
  /** The period label, for example "Oct 2025". */
  readonly label: string;
  readonly value: string;
}

export interface SparklineProps {
  /** The measure named first, for example "Recognized revenue". */
  readonly measure: string;
  readonly currency: string;
  readonly points: readonly SparkPoint[];
  /** `kpi`: 80 × 24 px in KPI cells; `cell`: 64 × 20 px in grid cells. */
  readonly size?: "kpi" | "cell";
}

const SIZES = { kpi: { width: 80, height: 24 }, cell: { width: 64, height: 20 } } as const;

// The end dot's radius, so the dot is not clipped at the edges.
const INSET = 3;

function spoken(value: string, currency: string): string {
  return formatMoney(value, currency, { variant: "inline" }).replace(NBSP, " ");
}

export function Sparkline({ measure, currency, points, size = "kpi" }: SparklineProps) {
  const first = points[0];
  const last = points[points.length - 1];
  if (first === undefined || last === undefined) {
    return null;
  }
  let low = first.value;
  let high = first.value;
  for (const point of points) {
    if (compareDecimal(point.value, low) < 0) {
      low = point.value;
    }
    if (compareDecimal(point.value, high) > 0) {
      high = point.value;
    }
  }
  const name = t("common.chart.sparkline.name", {
    measure,
    from: first.label,
    to: last.label,
    first: spoken(first.value, currency),
    last: spoken(last.value, currency),
    low: spoken(low, currency),
    high: spoken(high, currency),
  });

  const { width, height } = SIZES[size];
  // Geometry only: the plotted numbers are never displayed (SPEC-Q-244).
  const minimum = plotNumber(low);
  const span = plotNumber(high) - minimum;
  const xOf = (index: number) =>
    points.length === 1 ? width / 2 : INSET + (index * (width - 2 * INSET)) / (points.length - 1);
  const yOf = (value: number) =>
    span === 0 ? height / 2 : INSET + ((plotNumber(high) - value) * (height - 2 * INSET)) / span;
  const coordinates = points.map((point, index) => ({
    x: xOf(index),
    y: yOf(plotNumber(point.value)),
  }));
  const end = coordinates[coordinates.length - 1] ?? { x: width / 2, y: height / 2 };
  const crossesZero = compareDecimal(low, "0") < 0 && compareDecimal(high, "0") > 0;

  return (
    <svg
      role="img"
      aria-label={name}
      width={width}
      height={height}
      viewBox={`0 0 ${String(width)} ${String(height)}`}
      className="shrink-0"
    >
      {crossesZero ? (
        <line
          data-zero-line=""
          x1={0}
          x2={width}
          y1={yOf(0)}
          y2={yOf(0)}
          stroke="var(--viz-grid)"
          strokeWidth={1}
        />
      ) : null}
      {coordinates.length > 1 ? (
        <polyline
          points={coordinates.map(({ x, y }) => `${String(x)},${String(y)}`).join(" ")}
          fill="none"
          stroke="var(--viz-sparkline)"
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      ) : null}
      <circle data-end-dot="" cx={end.x} cy={end.y} r={INSET} fill="var(--fg-1)" />
    </svg>
  );
}
