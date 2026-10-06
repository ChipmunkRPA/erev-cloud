// @vitest-environment jsdom
// DS-CH-02 (DESIGN_SYSTEM §5.3): the rollforward bridge draws totals from zero and activity from the
// running level, and when the API flags that opening plus activity does not equal closing, a negative
// banner replaces the plot.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { registerCurrencies } from "../../lib/format";
import { type BridgeCategory, RollforwardBridge } from "./RollforwardBridge";

beforeAll(() => {
  registerCurrencies([{ code: "USD", minor_unit: 2 }]);
});

afterEach(() => {
  cleanup();
});

const CATEGORIES: readonly BridgeCategory[] = [
  { key: "opening", label: "Opening balance", kind: "TOTAL", amount: "40000.00" },
  { key: "billings", label: "Billings", kind: "ACTIVITY", amount: "36000.00" },
  { key: "recognized", label: "Revenue recognized", kind: "ACTIVITY", amount: "-28500.00" },
  { key: "closing", label: "Closing balance", kind: "TOTAL", amount: "47500.00" },
];

function renderBridge(
  integrity = { balanced: true, difference: "0.00" },
  onSelect?: (key: string) => void,
) {
  return render(
    <RollforwardBridge
      title="Contract liability rollforward"
      subtitle="Contract liability · USD · ASC 606"
      currency="USD"
      categories={CATEGORIES}
      integrity={integrity}
      onSelect={onSelect}
    />,
  );
}

describe("DS-CH-02 integrity", () => {
  it("an unbalanced rollforward replaces the plot with the negative banner", () => {
    renderBridge({ balanced: false, difference: "125.00" });
    const title = screen.getByRole("heading", {
      name: "This rollforward does not balance. Difference USD 125.00.",
    });
    expect(title.closest("[data-tone]")?.getAttribute("data-tone")).toBe("negative");
    expect(document.querySelector(".recharts-surface")).toBeNull();
    expect(document.querySelectorAll("rect[data-category]")).toHaveLength(0);
    expect(document.querySelector("[data-chart-legend]")).toBeNull();

    const figure = screen.getByRole("figure", { name: "Contract liability rollforward" });
    expect(
      document.getElementById(figure.getAttribute("aria-describedby") ?? "")?.textContent,
    ).toBe("This rollforward does not balance. Difference USD 125.00.");

    // The Table view still lists the API's figures.
    fireEvent.click(screen.getByRole("radio", { name: "Table" }));
    const table = screen.getByRole("table", { name: "Contract liability rollforward" });
    expect(
      within(table)
        .getAllByRole("row")
        .map((row) => Array.from(row.children, (cell) => cell.textContent)),
    ).toEqual([
      ["Category", "Amount (USD)"],
      ["Opening balance", "40,000.00"],
      ["Billings", "36,000.00"],
      ["Revenue recognized", "(28,500.00)"],
      ["Closing balance", "47,500.00"],
    ]);
  });

  it("a balanced rollforward draws totals, increases, decreases and connectors", () => {
    const onSelect = vi.fn();
    renderBridge(undefined, onSelect);
    expect(screen.queryByRole("heading", { name: /does not balance/ })).toBeNull();
    const bars = Array.from(document.querySelectorAll("rect[data-category]"), (bar) => ({
      key: bar.getAttribute("data-category"),
      fill: bar.getAttribute("fill"),
    }));
    expect(bars).toEqual([
      { key: "opening", fill: "var(--viz-total)" },
      { key: "billings", fill: "var(--viz-increase)" },
      { key: "recognized", fill: "var(--viz-decrease)" },
      { key: "closing", fill: "var(--viz-total)" },
    ]);
    expect(document.querySelectorAll("line[data-connector]")).toHaveLength(3);
    const labels = Array.from(
      document.querySelectorAll(".recharts-label-list text"),
      (text) => text.textContent,
    );
    expect(labels).toEqual(["40K", "+36K", "(28.5K)", "47.5K"]);

    const figure = screen.getByRole("figure", { name: "Contract liability rollforward" });
    expect(
      document.getElementById(figure.getAttribute("aria-describedby") ?? "")?.textContent,
    ).toBe(
      "Contract liability rollforward from Opening balance USD 40,000.00 to Closing balance USD 47,500.00.",
    );

    const billings = document.querySelector('rect[data-category="billings"]');
    if (billings === null) {
      throw new Error("No Billings bar");
    }
    fireEvent.click(billings);
    expect(onSelect).toHaveBeenCalledWith("billings");
  });

  it("totals rows carry the totals rule in the Table view", () => {
    renderBridge();
    fireEvent.click(screen.getByRole("radio", { name: "Table" }));
    const emphasised = Array.from(screen.getByRole("table").querySelectorAll("tbody tr"), (row) =>
      row.className.includes("border-t"),
    );
    expect(emphasised).toEqual([true, false, false, true]);
  });
});
