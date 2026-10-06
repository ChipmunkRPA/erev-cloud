// @vitest-environment jsdom
// DS-CMP-14 (DESIGN_SYSTEM §7.3, §5.3 DS-CH-01; DS-A11Y-13): the chart panel is a figure described by a
// generated summary, every Recharts series is static, the Chart / Table view switch is a segmented
// control and the Table view shows the figures the chart plots.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { createElement, type ComponentProps } from "react";
import type * as Recharts from "recharts";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { formatMoney, formatPeriod, registerCurrencies } from "../../lib/format";
import {
  RevenueWaterfall,
  type RevenueWaterfallProps,
  type WaterfallPeriod,
} from "./RevenueWaterfall";

const recorded = vi.hoisted(() => ({
  series: [] as { readonly name: string; readonly animation: unknown }[],
}));

vi.mock("recharts", async (importOriginal) => {
  const actual = await importOriginal<typeof Recharts>();
  return {
    ...actual,
    Bar: (props: ComponentProps<typeof actual.Bar>) => {
      recorded.series.push({
        name: `Bar ${String(props.dataKey)}`,
        animation: props.isAnimationActive,
      });
      return createElement(actual.Bar, props);
    },
    Tooltip: (props: ComponentProps<typeof actual.Tooltip>) => {
      recorded.series.push({ name: "Tooltip", animation: props.isAnimationActive });
      return createElement(actual.Tooltip, props);
    },
  };
});

beforeAll(() => {
  registerCurrencies([{ code: "USD", minor_unit: 2 }]);
});

beforeEach(() => {
  recorded.series.length = 0;
});

afterEach(() => {
  cleanup();
});

const MONTHS = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"];

// Jan to Jun 2026 are closed and recognized; Jul to Dec are open and scheduled.
function periods(): readonly WaterfallPeriod[] {
  return MONTHS.map((month, index) => {
    const closed = index < 6;
    const key = `FY2026-P${month}`;
    return {
      key,
      label: formatPeriod(key, { startDate: `2026-${month}-01` }),
      recognized: closed ? "9240.00" : "0.00",
      scheduled: closed ? "0.00" : "10760.00",
      total: closed ? "9240.00" : "10760.00",
      open: !closed,
    };
  });
}

const TOTALS = {
  recognized: "55440.00",
  scheduled: "64560.00",
  awaiting: "8000.00",
  total: "128000.00",
};

function renderWaterfall(overrides: Partial<RevenueWaterfallProps> = {}) {
  return render(
    <RevenueWaterfall
      title="Revenue by period"
      subtitle="Revenue by period · USD · ASC 606"
      scope="Northwind Health master agreement"
      currency="USD"
      periods={periods()}
      awaiting={{ amount: "8000.00", count: 2 }}
      totals={TOTALS}
      {...overrides}
    />,
  );
}

function plotted(): readonly { series: string; period: string; amount: string }[] {
  return Array.from(document.querySelectorAll("rect[data-series]"), (rect) => ({
    series: rect.getAttribute("data-series") ?? "",
    period: rect.getAttribute("data-period") ?? "",
    amount: rect.getAttribute("data-amount") ?? "",
  }));
}

function viewSwitch() {
  return within(screen.getByRole("radiogroup", { name: "View" }));
}

describe("DS-CMP-14", () => {
  it("every Recharts series renders with isAnimationActive={false}", () => {
    renderWaterfall();
    expect(plotted().length).toBeGreaterThanOrEqual(13);
    const names = new Set(recorded.series.map((entry) => entry.name));
    expect(names).toEqual(new Set(["Bar recognized", "Bar scheduled", "Bar awaiting", "Tooltip"]));
    expect(recorded.series.every((entry) => entry.animation === false)).toBe(true);
  });

  it("the view switch Chart / Table is a segmented control", () => {
    renderWaterfall();
    const radios = viewSwitch().getAllByRole("radio");
    expect(radios.map((radio) => radio.textContent)).toEqual(["Chart", "Table"]);
    expect(radios[0]?.getAttribute("aria-checked")).toBe("true");
    expect(document.querySelector(".recharts-surface")).not.toBeNull();

    fireEvent.click(viewSwitch().getByRole("radio", { name: "Table" }));
    expect(viewSwitch().getByRole("radio", { name: "Table" }).getAttribute("aria-checked")).toBe(
      "true",
    );
    expect(document.querySelector(".recharts-surface")).toBeNull();
    expect(screen.getByRole("table", { name: "Revenue by period" })).toBeTruthy();

    fireEvent.click(viewSwitch().getByRole("radio", { name: "Chart" }));
    expect(document.querySelector(".recharts-surface")).not.toBeNull();
  });

  it("the Table view shows the same figures as the chart", () => {
    renderWaterfall();
    const marks = plotted().filter((mark) => /[1-9]/.test(mark.amount));
    // Six recognized, six scheduled and the Awaiting trigger column.
    expect(marks).toHaveLength(13);
    const labels = new Map(periods().map((period) => [period.key, period.label]));

    fireEvent.click(viewSwitch().getByRole("radio", { name: "Table" }));
    const table = screen.getByRole("table", { name: "Revenue by period" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["Period", "Recognized (USD)", "Scheduled (USD)", "Total (USD)"]);
    const rowOf = (header: string) => {
      const row = within(table).getByRole("rowheader", { name: header }).closest("tr");
      if (row === null) {
        throw new Error(`No table row for ${header}`);
      }
      return Array.from(row.children, (cell) => cell.textContent);
    };
    const column = { recognized: 1, scheduled: 2, awaiting: 3 } as const;
    for (const mark of marks) {
      const header =
        mark.series === "awaiting" ? "Awaiting trigger" : (labels.get(mark.period) ?? "");
      const cells = rowOf(header);
      expect(cells[column[mark.series as keyof typeof column]]).toBe(
        formatMoney(mark.amount, "USD"),
      );
    }
    expect(rowOf("Total")).toEqual(["Total", "55,440.00", "64,560.00", "128,000.00"]);
  });

  it("the panel is a figure whose aria-describedby summary states range and totals", () => {
    renderWaterfall();
    const figure = screen.getByRole("figure", { name: "Revenue by period" });
    const summary = document.getElementById(figure.getAttribute("aria-describedby") ?? "");
    expect(summary?.textContent).toBe(
      "Revenue for Northwind Health master agreement from Jan 2026 to Dec 2026: recognized USD 55,440.00, scheduled USD 64,560.00, awaiting trigger USD 8,000.00.",
    );
    expect(within(figure).getByText("Revenue by period · USD · ASC 606")).toBeTruthy();
    expect(
      Array.from(figure.querySelectorAll("[data-chart-legend] li"), (item) => item.textContent),
    ).toEqual(["Recognized", "Scheduled", "Awaiting trigger"]);
  });

  it("marks the first open period and separates the Awaiting trigger column", () => {
    renderWaterfall();
    expect(document.querySelector("[data-open-caption]")?.textContent).toBe("Open");
    expect(document.querySelector("[data-open-rule]")).not.toBeNull();
    expect(document.querySelector("[data-awaiting-rule]")).not.toBeNull();
    const awaiting = document.querySelector('rect[data-series="awaiting"][data-amount="8000.00"]');
    expect(awaiting?.getAttribute("fill")).toMatch(/^url\(#chart\w+-awaiting\)$/);
    expect(awaiting?.getAttribute("stroke-dasharray")).toBe("4 3");
    const recognized = document.querySelector('rect[data-series="recognized"]');
    expect(recognized?.getAttribute("fill")).toBe("var(--viz-recognized)");
  });

  it("selecting a bar drills down to its period and state", () => {
    const onSelect = vi.fn();
    renderWaterfall({ onSelect });
    const july = document.querySelector('rect[data-series="scheduled"][data-period="FY2026-P07"]');
    if (july === null) {
      throw new Error("No scheduled bar for Jul 2026");
    }
    fireEvent.click(july);
    const awaiting = document.querySelector('rect[data-series="awaiting"][data-amount="8000.00"]');
    if (awaiting === null) {
      throw new Error("No Awaiting trigger bar");
    }
    fireEvent.click(awaiting);
    expect(onSelect.mock.calls).toEqual([
      [{ period: "FY2026-P07", series: "scheduled" }],
      [{ period: null, series: "awaiting" }],
    ]);
  });

  it("Enter drills down on the column made active from the keyboard; Esc returns to the panel", () => {
    const onSelect = vi.fn();
    renderWaterfall({ onSelect });
    const surface = document.querySelector<SVGElement>(".recharts-surface");
    if (surface === null) {
      throw new Error("No chart surface");
    }
    act(() => {
      surface.focus();
    });
    fireEvent.keyDown(surface, { key: "ArrowRight" });
    fireEvent.keyDown(surface, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0]?.[0]).toMatchObject({ series: null });

    fireEvent.keyDown(surface, { key: "Escape" });
    expect(document.activeElement).toBe(screen.getByRole("figure", { name: "Revenue by period" }));
  });

  it("loading, empty and error states replace the plot area", () => {
    const { rerender } = renderWaterfall({ state: "loading" });
    const figure = screen.getByRole("figure", { name: "Revenue by period" });
    expect(figure.getAttribute("aria-busy")).toBe("true");
    expect(figure.querySelector("[data-skeleton]")).not.toBeNull();
    expect(document.querySelector(".recharts-surface")).toBeNull();

    const props = {
      title: "Revenue by period",
      scope: "Northwind Health master agreement",
      currency: "USD",
      periods: [],
      awaiting: null,
      totals: TOTALS,
    };
    rerender(
      <RevenueWaterfall
        {...props}
        state="empty"
        emptyText="No revenue scheduled for this range."
      />,
    );
    expect(screen.getByText("No revenue scheduled for this range.")).toBeTruthy();

    const onRetry = vi.fn();
    rerender(<RevenueWaterfall {...props} state="error" onRetry={onRetry} />);
    const alert = screen.getByRole("alert");
    expect(within(alert).getByText("The chart could not be loaded.")).toBeTruthy();
    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("refuses more than 36 columns", () => {
    const many = Array.from({ length: 37 }, (_, index) => ({
      key: `P${String(index)}`,
      label: `Period ${String(index)}`,
      recognized: "1.00",
      scheduled: "0.00",
      total: "1.00",
    }));
    expect(() => renderWaterfall({ periods: many })).toThrow("at most 36 columns");
  });
});
