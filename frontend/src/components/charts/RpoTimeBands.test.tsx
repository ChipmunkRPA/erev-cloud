// @vitest-environment jsdom
// DS-CH-03 (DESIGN_SYSTEM §5.3, DS-VIZ-06): RPO bands are the returned boundaries, labelled from them and
// coloured with the ordinal ramp; more than five bands leave only the Table view.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { registerCurrencies } from "../../lib/format";
import { rpoBandLabels, type RpoRow, RpoTimeBands } from "./RpoTimeBands";

beforeAll(() => {
  registerCurrencies([{ code: "USD", minor_unit: 2 }]);
});

afterEach(() => {
  cleanup();
});

const THREE_BANDS: readonly RpoRow[] = [
  {
    key: "total",
    label: "Total",
    total: "250000.00",
    amounts: ["120000.00", "80000.00", "50000.00"],
  },
  {
    key: "us",
    label: "Avenmoor US",
    total: "150000.00",
    amounts: ["70000.00", "50000.00", "30000.00"],
  },
  {
    key: "uk",
    label: "Avenmoor UK",
    total: "100000.00",
    amounts: ["50000.00", "30000.00", "20000.00"],
  },
];

function renderBands(boundaries: readonly number[], rows: readonly RpoRow[], onSelect = vi.fn()) {
  return render(
    <RpoTimeBands
      title="Remaining performance obligations"
      subtitle="RPO by expected timing · USD · ASC 606"
      currency="USD"
      boundaries={boundaries}
      rows={rows}
      rowHeader="Entity"
      footnote="Excludes contracts with an original expected duration of one year or less."
      onSelect={onSelect}
    />,
  );
}

describe("DS-CH-03 bands", () => {
  it("labels the bands from the returned boundaries", () => {
    expect(rpoBandLabels([12, 24])).toEqual([
      "Within 12 months",
      "13 to 24 months",
      "After 24 months",
    ]);
    expect(rpoBandLabels([6])).toEqual(["Within 6 months", "After 6 months"]);
    expect(rpoBandLabels([])).toEqual(["All remaining periods"]);
  });

  it("boundaries [12, 24] draw three bands in --viz-rpo-1 to --viz-rpo-3", () => {
    const onSelect = vi.fn();
    renderBands([12, 24], THREE_BANDS, onSelect);
    const legend = document.querySelector("[data-chart-legend]");
    expect(
      Array.from(legend?.querySelectorAll("li") ?? [], (item) => ({
        label: item.textContent,
        swatch: item.querySelector("[data-swatch]")?.getAttribute("data-swatch"),
      })),
    ).toEqual([
      { label: "Within 12 months", swatch: "var(--viz-rpo-1)" },
      { label: "13 to 24 months", swatch: "var(--viz-rpo-2)" },
      { label: "After 24 months", swatch: "var(--viz-rpo-3)" },
    ]);
    for (const band of [0, 1, 2]) {
      const segments = document.querySelectorAll(`rect[data-band="${String(band)}"]`);
      expect(segments).toHaveLength(3);
      for (const segment of segments) {
        expect(segment.getAttribute("fill")).toBe(`var(--viz-rpo-${String(band + 1)})`);
      }
    }
    // The row total follows each bar.
    expect(
      Array.from(
        document.querySelectorAll(".recharts-label-list text"),
        (text) => text.textContent,
      ),
    ).toEqual(["250K", "150K", "100K"]);
    expect(
      screen.getByText(
        "Excludes contracts with an original expected duration of one year or less.",
      ),
    ).toBeTruthy();

    const figure = screen.getByRole("figure", { name: "Remaining performance obligations" });
    expect(
      document.getElementById(figure.getAttribute("aria-describedby") ?? "")?.textContent,
    ).toBe(
      "Remaining performance obligations for Total: Within 12 months USD 120,000.00, 13 to 24 months USD 80,000.00, After 24 months USD 50,000.00; total USD 250,000.00.",
    );

    const segment = document.querySelector('rect[data-band="1"][data-row="uk"]');
    if (segment === null) {
      throw new Error("No 13 to 24 months segment for Avenmoor UK");
    }
    fireEvent.click(segment);
    expect(onSelect).toHaveBeenCalledWith({ row: "uk", band: 1 });

    // Enter on the row made active from the keyboard drills into every band of that row.
    onSelect.mockClear();
    const surface = document.querySelector(".recharts-surface");
    if (surface === null) {
      throw new Error("No chart surface");
    }
    fireEvent.keyDown(surface, { key: "ArrowRight" });
    fireEvent.keyDown(surface, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0]?.[0]).toMatchObject({ band: null });
  });

  it("six bands leave only the Table view, with the Chart option disabled", () => {
    const rows: readonly RpoRow[] = [
      {
        key: "total",
        label: "Total",
        total: "210000.00",
        amounts: ["60000.00", "50000.00", "40000.00", "30000.00", "20000.00", "10000.00"],
      },
    ];
    renderBands([12, 24, 36, 48, 60], rows);
    const chart = screen.getByRole("radio", { name: "Chart" });
    expect(chart.getAttribute("aria-disabled")).toBe("true");
    expect(document.getElementById(chart.getAttribute("aria-describedby") ?? "")?.textContent).toBe(
      "The chart shows at most five time bands.",
    );
    expect(screen.getByRole("radio", { name: "Table" }).getAttribute("aria-checked")).toBe("true");
    expect(document.querySelector(".recharts-surface")).toBeNull();
    expect(document.querySelector("[data-chart-legend]")).toBeNull();

    fireEvent.click(chart);
    expect(document.querySelector(".recharts-surface")).toBeNull();

    const table = screen.getByRole("table", { name: "Remaining performance obligations" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual([
      "Entity",
      "Within 12 months (USD)",
      "13 to 24 months (USD)",
      "25 to 36 months (USD)",
      "37 to 48 months (USD)",
      "49 to 60 months (USD)",
      "After 60 months (USD)",
      "Total (USD)",
    ]);
    expect(
      Array.from(
        within(table).getByRole("rowheader", { name: "Total" }).closest("tr")?.children ?? [],
        (cell) => cell.textContent,
      ),
    ).toEqual([
      "Total",
      "60,000.00",
      "50,000.00",
      "40,000.00",
      "30,000.00",
      "20,000.00",
      "10,000.00",
      "210,000.00",
    ]);
  });

  it("refuses a row whose amounts do not match the returned bands", () => {
    expect(() =>
      renderBands([12, 24], [{ key: "total", label: "Total", total: "1.00", amounts: ["1.00"] }]),
    ).toThrow("one amount per returned band");
  });
});
