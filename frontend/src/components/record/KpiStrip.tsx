// KPI strip of the record header (DESIGN_SYSTEM DS-CMP-06; SCREENS §4.1.4): a caption heading, then a
// `dl` of at most six cells (four in the compact obligation header). Values are neutral ink in DS-FMT-04
// digits without the code, which the heading carries. Every computed value is an Explain trigger named
// "Explain <label>, <currency> <value>" that opens on Enter or `E`. A proportion bar is aria-hidden
// because the secondary line states the same proportion; above 100% the bar is full and the warning
// chip is shown. Ratios come from the API and are compared on their digits (DG-FE-08). A standalone
// strip (SCREENS §2.6 SF-01) may drill instead: the value is a link named "<label>, <currency> <value>"
// (or "<label>, <count>"), with an optional DS-CH-04 sparkline beside it.
import { type ReactNode, useId } from "react";
import { Link } from "react-router";

import { formatList, formatMoney, formatNumber, NBSP, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { ProportionBar } from "../charts/ProportionBar";
import { ExplainTrigger, type FigureRef } from "../explain/ExplainTrigger";
import { Function as FunctionIcon } from "../icons/registry";
import { cn } from "../ui/cn";

export { ratioAboveOne } from "../charts/ProportionBar";

export interface KpiBar {
  /** The API ratio of the value to its reference, a non-negative decimal string such as "0.462". */
  readonly ratio: string;
  /** The warning chip above 100%, for example "Over transaction price". */
  readonly overLabel: string;
}

/**
 * What the value explains: the value renders inside `<ExplainTrigger>` (DG-FE-15), with the figure it
 * names, or with the id of a list level of the host where the trace holds no node for the value
 * (SCREENS §6.3 list level, rev 1.21).
 */
export type KpiExplain =
  | {
      readonly figureRef: FigureRef;
      /** The context line of the panel: contract, obligation, book and entity. */
      readonly context?: string | undefined;
    }
  | { readonly list: string };

export interface Kpi {
  readonly id: string;
  readonly label: string;
  readonly value: string | null;
  readonly currency: string;
  /** Opens the Explain panel (DS-CMP-15); every computed figure has one. */
  readonly onExplain?: (() => void) | undefined;
  /** The Explain figure; takes precedence over `onExplain`. */
  readonly explain?: KpiExplain | undefined;
  /** SCREENS SCR-TID-04 `kpi-<measure>` of the value. */
  readonly testId?: string | undefined;
  readonly bar?: KpiBar | undefined;
  /** The secondary line, for example "46.2% of transaction price"; required with a bar. */
  readonly secondary?: ReactNode;
  /**
   * `count`: a DS-FMT-21 count without a currency; `text`: the value as given, in mono, for an identifier
   * or a hash (DS-FMT-23; SCREENS_B §6.4 "Last chain value"); `figure`: a percentage, a date or a
   * quantity the caller has formatted (SCREENS §8.4 "Progress", "Rate"), shown as given in tabular
   * figures; the default is money.
   */
  readonly kind?: "money" | "count" | "text" | "figure" | undefined;
  /** A drill target: the value renders as a link to it (SCREENS §2.6). */
  readonly to?: string | undefined;
  /** A DS-CH-04 sparkline beside the value. */
  readonly trend?: ReactNode;
}

export interface KpiStripProps {
  readonly heading: string;
  readonly kpis: readonly Kpi[];
  readonly loading?: boolean;
  /** The obligation variant inside a master-detail pane: at most four cells. */
  readonly compact?: boolean;
  readonly headingLevel?: 2 | 3;
  /** A `section` named by the heading (the record header's "Key figures" region). */
  readonly region?: boolean;
  /** SCREENS SCR-TID-04 `kpi-strip`. */
  readonly testId?: string | undefined;
}

// Copy defects throw in development and tests; a production build still renders.
const STRICT = import.meta.env.DEV || import.meta.env.MODE === "test";

function KpiValue({ kpi, loading }: { readonly kpi: Kpi; readonly loading: boolean }) {
  if (loading) {
    return (
      <span aria-hidden="true" data-skeleton="" className="block h-6 w-24 rounded-sm bg-subtle" />
    );
  }
  if (kpi.value === null) {
    return <span className="num text-kpi text-fg-3">{NO_VALUE}</span>;
  }
  if (kpi.kind === "text") {
    // An identifier or a hash differs from one world to the next: captures mask it (SCR-TID-05).
    return (
      <span data-testid={kpi.testId} data-volatile="" className="font-mono text-kpi text-fg-1">
        {kpi.value}
      </span>
    );
  }
  if (kpi.kind === "figure") {
    return (
      <span data-testid={kpi.testId} className="num text-kpi text-fg-1">
        {kpi.value}
      </span>
    );
  }
  const count = kpi.kind === "count";
  const figures = count
    ? formatNumber(kpi.value, { kind: "count" })
    : formatMoney(kpi.value, kpi.currency);
  const withCode = count
    ? figures
    : formatMoney(kpi.value, kpi.currency, { variant: "inline" }).replace(NBSP, " ");
  if (kpi.to !== undefined) {
    return (
      <Link
        to={kpi.to}
        data-testid={kpi.testId}
        aria-label={formatList([kpi.label, withCode], "unit")}
        className="num rounded-sm text-kpi text-fg-1 decoration-control decoration-dotted underline-offset-4 hover:underline focus-visible:underline"
      >
        {figures}
      </Link>
    );
  }
  if (count) {
    return (
      <span data-testid={kpi.testId} className="num text-kpi text-fg-1">
        {figures}
      </span>
    );
  }
  if (kpi.explain !== undefined) {
    return (
      <span data-testid={kpi.testId} className="inline-flex text-kpi text-fg-1">
        {"list" in kpi.explain ? (
          <ExplainTrigger list={kpi.explain.list} label={kpi.label} valueText={withCode}>
            <span className="num">{figures}</span>
          </ExplainTrigger>
        ) : (
          <ExplainTrigger
            figureRef={kpi.explain.figureRef}
            label={kpi.label}
            context={kpi.explain.context}
            valueText={withCode}
          >
            <span className="num">{figures}</span>
          </ExplainTrigger>
        )}
      </span>
    );
  }
  const explain = kpi.onExplain;
  if (explain === undefined) {
    return (
      <span data-testid={kpi.testId} className="num text-kpi text-fg-1">
        {figures}
      </span>
    );
  }
  return (
    <button
      type="button"
      data-testid={kpi.testId}
      aria-label={t("common.record.kpi.explain", { label: kpi.label, value: withCode })}
      onClick={explain}
      onKeyDown={(event) => {
        if (event.key === "e" || event.key === "E") {
          event.preventDefault();
          explain();
        }
      }}
      className="group inline-flex items-center gap-1 rounded-sm text-kpi text-fg-1 decoration-control decoration-dotted underline-offset-4 hover:underline focus-visible:underline"
    >
      <span className="num">{figures}</span>
      <FunctionIcon
        aria-hidden="true"
        className="invisible shrink-0 text-fg-3 group-hover:visible group-focus-visible:visible"
      />
    </button>
  );
}

function KpiCell({ kpi, loading }: { readonly kpi: Kpi; readonly loading: boolean }) {
  const bar = kpi.bar;
  if (STRICT && bar !== undefined && kpi.secondary === undefined) {
    throw new Error(
      "A KPI proportion bar needs a secondary line stating the proportion (DS-CMP-06)",
    );
  }
  return (
    <div className="relative flex min-w-0 flex-col gap-1 px-4 before:absolute before:inset-y-0 before:start-0 before:w-px before:bg-hairline before:content-['']">
      <dt className="text-caption text-fg-3">{kpi.label}</dt>
      <dd className="flex flex-col items-start gap-1.5">
        {kpi.trend === undefined || loading ? (
          <KpiValue kpi={kpi} loading={loading} />
        ) : (
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <KpiValue kpi={kpi} loading={loading} />
            {kpi.trend}
          </span>
        )}
        {bar === undefined || loading ? null : (
          <ProportionBar ratio={bar.ratio} overLabel={bar.overLabel} />
        )}
        {kpi.secondary === undefined || loading ? null : (
          <span className="text-body-sm text-fg-3">{kpi.secondary}</span>
        )}
      </dd>
    </div>
  );
}

export function KpiStrip({
  heading,
  kpis,
  loading = false,
  compact = false,
  headingLevel = 2,
  region = false,
  testId,
}: KpiStripProps) {
  const headingId = useId();
  const limit = compact ? 4 : 6;
  if (STRICT && kpis.length > limit) {
    throw new Error(`A KPI strip holds at most ${String(limit)} cells (DS-CMP-06)`);
  }
  const Heading = `h${String(headingLevel)}` as "h2" | "h3";
  const Root = region ? "section" : "div";
  return (
    <Root
      aria-busy={loading ? true : undefined}
      aria-labelledby={region ? headingId : undefined}
      data-testid={testId}
      className="flex flex-col gap-2"
    >
      <Heading id={headingId} className="text-caption text-fg-3">
        {heading}
      </Heading>
      {/* D-87 L6-4-Q-7: cells wrap onto further rows when the strip is narrow (for example beside the
          docked Explain panel), so figures never clip. Each cell draws its start rule as a 1 px
          pseudo-element; the strip is pulled back by one cell's start padding, and the clipping box
          hides the rule at the start of every row; its 4 px margin keeps focus rings visible. */}
      <div className="-m-1 overflow-hidden p-1">
        <dl
          className={cn(
            "-ms-4 grid grid-cols-[repeat(auto-fit,minmax(min(100%,11rem),1fr))]",
            compact ? "gap-y-2" : "gap-y-3",
          )}
        >
          {kpis.map((kpi) => (
            <KpiCell key={kpi.id} kpi={kpi} loading={loading} />
          ))}
        </dl>
      </div>
    </Root>
  );
}
