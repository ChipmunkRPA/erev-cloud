// @vitest-environment jsdom
// DS-CH-06 (DESIGN_SYSTEM §5.3; DS-VIZ-01, DS-VIZ-03): one bar per category, the largest first, in the
// categorical slots in that order; the chart sums nothing, so more than seven categories leave only the
// Table view, which lists every one of them.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { registerCurrencies } from "../../lib/format";
import { CategoryBars, type Category, orderedCategories } from "./CategoryBars";

beforeAll(() => {
  registerCurrencies([{ code: "USD", minor_unit: 2 }]);
});

afterEach(() => {
  cleanup();
});

/** As a `disaggregation` run returns them: in the order of the value codes, not of the amounts. */
const FOUR: readonly Category[] = [
  { key: "LICENCE", label: "Licences", amount: "20000.00" },
  { key: "PRODUCT", label: "Products", amount: "40000.00" },
  { key: "SERVICE", label: "Services", amount: "80000.00" },
  { key: "SUBSCRIPTION", label: "Subscription", amount: "150000.00" },
];

function renderBars(categories: readonly Category[], onSelect = vi.fn(), total?: string) {
  return render(
    <CategoryBars
      title="Revenue by category"
      subtitle="USD · Sep 2026"
      currency="USD"
      categoryHeader="Revenue category"
      categories={categories}
      total={total}
      footnote="Run RPT-000434"
      onSelect={onSelect}
    />,
  );
}

function slots(): (string | null)[][] {
  return Array.from(document.querySelectorAll("rect[data-category]"), (bar) => [
    bar.getAttribute("data-category"),
    bar.getAttribute("fill"),
  ]);
}

describe("DS-CH-06 category bars", () => {
  it("orders the categories by amount, the largest first, without converting a figure", () => {
    expect(orderedCategories(FOUR).map((category) => category.key)).toEqual([
      "SUBSCRIPTION",
      "SERVICE",
      "PRODUCT",
      "LICENCE",
    ]);
    // Decimal strings are compared on their digits: 9.5 is less than 10, and a reversal comes last.
    const mixed: readonly Category[] = [
      { key: "a", label: "A", amount: "9.50" },
      { key: "b", label: "B", amount: "-3.00" },
      { key: "c", label: "C", amount: "10.00" },
      { key: "d", label: "D", amount: "9.50" },
    ];
    // Equal amounts keep the order the API gave them.
    expect(orderedCategories(mixed).map((category) => category.key)).toEqual(["c", "a", "d", "b"]);
  });

  it("draws one bar per category in the categorical slots, in the order of the amounts", () => {
    const onSelect = vi.fn();
    renderBars(FOUR, onSelect, "290000.00");
    expect(slots()).toEqual([
      ["SUBSCRIPTION", "var(--viz-1)"],
      ["SERVICE", "var(--viz-2)"],
      ["PRODUCT", "var(--viz-3)"],
      ["LICENCE", "var(--viz-4)"],
    ]);
    // The amount follows each bar, compact (DS-FMT-15).
    expect(
      Array.from(
        document.querySelectorAll(".recharts-label-list text"),
        (text) => text.textContent,
      ),
    ).toEqual(["150K", "80K", "40K", "20K"]);
    expect(screen.getByText("Run RPT-000434")).toBeTruthy();
    // No legend: each bar is named on its axis (DS-A11Y-04).
    expect(document.querySelector("[data-chart-legend]")).toBeNull();

    const figure = screen.getByRole("figure", { name: "Revenue by category" });
    expect(
      document.getElementById(figure.getAttribute("aria-describedby") ?? "")?.textContent,
    ).toBe(
      "Revenue by category, largest first: Subscription USD 150,000.00, Services USD 80,000.00, Products USD 40,000.00, Licences USD 20,000.00.",
    );

    const services = document.querySelector('rect[data-category="SERVICE"]');
    if (services === null) {
      throw new Error("No bar for Services");
    }
    fireEvent.click(services);
    expect(onSelect).toHaveBeenCalledWith("SERVICE");

    // Enter on the category made active from the keyboard drills into it.
    onSelect.mockClear();
    const surface = document.querySelector(".recharts-surface");
    if (surface === null) {
      throw new Error("No chart surface");
    }
    fireEvent.keyDown(surface, { key: "ArrowRight" });
    fireEvent.keyDown(surface, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("the Table view lists every category with the API's total", () => {
    renderBars(FOUR, vi.fn(), "290000.00");
    fireEvent.click(screen.getByRole("radio", { name: "Table" }));
    const table = screen.getByRole("table", { name: "Revenue by category" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["Revenue category", "Amount (USD)"]);
    expect(
      within(table)
        .getAllByRole("row")
        .slice(1)
        .map((row) => Array.from(row.children, (cell) => cell.textContent)),
    ).toEqual([
      ["Subscription", "150,000.00"],
      ["Services", "80,000.00"],
      ["Products", "40,000.00"],
      ["Licences", "20,000.00"],
      ["Total", "290,000.00"],
    ]);
    cleanup();

    // Without a total from the API the table ends with its last category: the chart adds none up.
    renderBars(FOUR);
    fireEvent.click(screen.getByRole("radio", { name: "Table" }));
    expect(
      within(screen.getByRole("table", { name: "Revenue by category" })).queryByRole("rowheader", {
        name: "Total",
      }),
    ).toBeNull();
  });

  it("eight categories leave only the Table view, with the Chart option disabled", () => {
    const eight: readonly Category[] = Array.from({ length: 8 }, (_, index) => ({
      key: `C${String(index + 1)}`,
      label: `Category ${String(index + 1)}`,
      amount: `${String((index + 1) * 1000)}.00`,
    }));
    renderBars(eight.slice(0, 7));
    expect(slots().map(([, fill]) => fill)).toEqual([
      "var(--viz-1)",
      "var(--viz-2)",
      "var(--viz-3)",
      "var(--viz-4)",
      "var(--viz-5)",
      "var(--viz-6)",
      "var(--viz-7)",
    ]);
    cleanup();

    renderBars(eight);
    const chart = screen.getByRole("radio", { name: "Chart" });
    expect(chart.getAttribute("aria-disabled")).toBe("true");
    expect(document.getElementById(chart.getAttribute("aria-describedby") ?? "")?.textContent).toBe(
      "The chart shows at most seven categories.",
    );
    expect(screen.getByRole("radio", { name: "Table" }).getAttribute("aria-checked")).toBe("true");
    expect(document.querySelector(".recharts-surface")).toBeNull();
    // Nothing is folded into "Other": the table holds all eight.
    const table = screen.getByRole("table", { name: "Revenue by category" });
    expect(
      within(table)
        .getAllByRole("rowheader")
        .map((cell) => cell.textContent),
    ).toEqual([
      "Category 8",
      "Category 7",
      "Category 6",
      "Category 5",
      "Category 4",
      "Category 3",
      "Category 2",
      "Category 1",
    ]);
  });

  it("an empty run shows the empty text in place of the plot", () => {
    render(
      <CategoryBars
        title="Revenue by category"
        currency="USD"
        categoryHeader="Revenue category"
        categories={[]}
        state="empty"
        emptyText="No revenue to disaggregate in Sep 2026"
      />,
    );
    expect(screen.getByText("No revenue to disaggregate in Sep 2026")).toBeTruthy();
    expect(document.querySelector(".recharts-surface")).toBeNull();
    // With nothing to list, the figure is described by its title alone.
    const figure = screen.getByRole("figure", { name: "Revenue by category" });
    expect(
      document.getElementById(figure.getAttribute("aria-describedby") ?? "")?.textContent,
    ).toBe("Revenue by category");
  });
});
