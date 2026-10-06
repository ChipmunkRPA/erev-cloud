// Chart panel (DESIGN_SYSTEM DS-CMP-14, DS-A11Y-13). A `figure` named by its title and described by a
// generated text summary, with a Chart / Table view switch (DS-CMP-31) whose Table view is the complete
// non-visual equivalent. Loading, empty and error states replace the plot area, and Esc inside the plot
// returns focus to the panel. The panel draws no figure itself: each chart passes its plot, its table
// and its summary, all built from the API's figures.
import { type ReactNode, useEffect, useId, useRef, useState } from "react";

import { t } from "../../lib/i18n/t";
import { Banner } from "../feedback/Banner";
import { ChartBar, Table } from "../icons/registry";
import { Button } from "../ui/Button";
import { SegmentedControl } from "../ui/SegmentedControl";
import { ChartLegend, type LegendEntry, PLOT_HEIGHT } from "./chartKit";

export type ChartView = "chart" | "table";
export type ChartPanelState = "ready" | "loading" | "empty" | "error";

export interface ChartPanelProps {
  readonly title: string;
  /** Measure, currency and book, for example "Revenue by period · USD · ASC 606". */
  readonly subtitle?: string | undefined;
  /** The generated summary the figure is described by. */
  readonly summary: string;
  readonly legend?: readonly LegendEntry[] | undefined;
  /** Screen controls placed before the view switch, for example a granularity segmented control. */
  readonly controls?: ReactNode;
  /** For example "As of 07 Sep 2026 14:05 UTC". */
  readonly footnote?: ReactNode;
  readonly state?: ChartPanelState;
  readonly emptyText?: string | undefined;
  /** The problem title of a failed load. */
  readonly errorTitle?: string | undefined;
  readonly onRetry?: (() => void) | undefined;
  /** Set when the chart cannot draw these figures: the panel shows only the Table view. */
  readonly chartDisabledReason?: string | undefined;
  readonly defaultView?: ChartView;
  readonly headingLevel?: 2 | 3 | undefined;
  readonly chart: ReactNode;
  readonly table: ReactNode;
}

export function ChartPanel({
  title,
  subtitle,
  summary,
  legend,
  controls,
  footnote,
  state = "ready",
  emptyText,
  errorTitle,
  onRetry,
  chartDisabledReason,
  defaultView = "chart",
  headingLevel = 3,
  chart,
  table,
}: ChartPanelProps) {
  const titleId = useId();
  const summaryId = useId();
  const figureRef = useRef<HTMLElement>(null);
  const plotRef = useRef<HTMLDivElement>(null);
  const [chosen, setChosen] = useState<ChartView>(defaultView);
  const view: ChartView = chartDisabledReason === undefined ? chosen : "table";

  useEffect(() => {
    const plot = plotRef.current;
    if (plot === null) {
      return undefined;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        figureRef.current?.focus();
      }
    };
    plot.addEventListener("keydown", onKeyDown);
    return () => {
      plot.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  const Heading = `h${String(headingLevel)}` as "h2" | "h3";
  let body: ReactNode;
  if (state === "loading") {
    body = (
      <div
        aria-hidden="true"
        data-skeleton=""
        className="w-full rounded-sm bg-subtle"
        style={{ blockSize: PLOT_HEIGHT }}
      />
    );
  } else if (state === "error") {
    body = (
      <Banner
        tone="negative"
        title={errorTitle ?? t("common.chart.loadError")}
        headingLevel={headingLevel === 2 ? 3 : 4}
        actions={
          onRetry === undefined ? undefined : (
            <Button variant="link" onClick={onRetry}>
              {t("common.chart.retry")}
            </Button>
          )
        }
      />
    );
  } else if (state === "empty") {
    body = (
      <p
        className="flex items-center justify-center text-body-sm text-fg-3"
        style={{ blockSize: PLOT_HEIGHT }}
      >
        {emptyText ?? t("common.chart.empty")}
      </p>
    );
  } else {
    body = view === "chart" ? chart : table;
  }

  return (
    <figure
      ref={figureRef}
      tabIndex={-1}
      aria-labelledby={titleId}
      aria-describedby={summaryId}
      aria-busy={state === "loading" ? true : undefined}
      className="flex min-w-0 flex-col gap-3 rounded-md border border-hairline bg-surface p-4"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-0.5">
          <Heading id={titleId} className="text-title-sm text-fg-1">
            {title}
          </Heading>
          {subtitle === undefined ? null : <p className="text-body-sm text-fg-3">{subtitle}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {controls}
          <SegmentedControl<ChartView>
            label={t("common.chart.viewSwitch")}
            options={[
              {
                value: "chart",
                label: t("common.chart.view.chart"),
                icon: ChartBar,
                disabledReason: chartDisabledReason,
              },
              { value: "table", label: t("common.chart.view.table"), icon: Table },
            ]}
            value={view}
            onChange={setChosen}
          />
        </div>
      </div>
      <p id={summaryId} className="sr-only">
        {summary}
      </p>
      {view === "chart" && state === "ready" && legend !== undefined && legend.length > 0 ? (
        <ChartLegend entries={legend} />
      ) : null}
      <div ref={plotRef} data-chart-view={view} className="min-w-0">
        {body}
      </div>
      {footnote === undefined ? null : <p className="text-caption text-fg-3">{footnote}</p>}
    </figure>
  );
}
