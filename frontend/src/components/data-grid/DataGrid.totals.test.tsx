// @vitest-environment jsdom
// DS-CMP-10 item 7 and DS-FMT-12 (DESIGN_SYSTEM rev 1.4; PR-8.7; L8-merge.md run 2): a mixed-currency grid
// shows one totals row per currency with the API figures and never a sum across currencies; each totals row
// names its ISO code in the Currency column wherever that column sits; while the column is hidden the label
// carries the code ("Total (GBP)"); a single totals row keeps the label "Total".
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { createQueryClient } from "../../app/providers";
import { queryKey } from "../../lib/api/query-keys";
import { registerCurrencies } from "../../lib/format";
import { installGridViewport } from "../../test/layout";
import { DataGrid } from "./DataGrid";
import {
  type GridColumn,
  type GridColumnState,
  type GridSource,
  type GridTotalsRow,
  initialColumnState,
} from "./types";

installGridViewport();

beforeAll(() => {
  registerCurrencies([
    { code: "GBP", minor_unit: 2 },
    { code: "USD", minor_unit: 2 },
  ]);
});

afterEach(() => {
  cleanup();
});

interface Line {
  readonly id: string;
  readonly account: string;
  readonly currency: string;
  readonly amount: string;
}

const LINES: readonly Line[] = [
  { id: "line-1", account: "5001", currency: "GBP", amount: "4950.29" },
  { id: "line-2", account: "5002", currency: "USD", amount: "547053.23" },
];

const ACCOUNT: GridColumn<Line> = {
  id: "account",
  header: "Account",
  kind: "identifier",
  value: (row) => row.account,
};
/** The DS-FMT-12 Currency column: text, immediately before the first amount column. */
const CURRENCY: GridColumn<Line> = {
  id: "currency",
  header: "Currency",
  kind: "text",
  value: (row) => row.currency,
  currencyColumn: true,
};
const AMOUNT: GridColumn<Line> = {
  id: "amount",
  header: "Amount",
  kind: "money",
  value: (row) => row.amount,
  currency: (row) => row.currency,
};
const COLUMNS: readonly GridColumn<Line>[] = [ACCOUNT, CURRENCY, AMOUNT];

const SOURCE: GridSource<Line> = {
  queryKey: queryKey("totals-test", "tenant"),
  fetchPage: () =>
    Promise.resolve({
      items: LINES,
      nextCursor: null,
      total: { count: LINES.length, capped: false },
    }),
};

// The figures observed on the SF-06:entries by-account grid (L8-merge.md run 2): GBP 4,950.29 and USD
// 547,053.23 on one grid. Their arithmetic sum, 552,003.52, is a figure of no currency and appears nowhere.
const GBP_TOTAL: GridTotalsRow = {
  key: "TOTAL:GBP",
  currency: "GBP",
  values: { amount: "4950.29" },
};
const USD_TOTAL: GridTotalsRow = {
  key: "TOTAL:USD",
  currency: "USD",
  values: { amount: "547053.23" },
};
const CROSS_CURRENCY_SUM = "552,003.52";

function renderGrid(
  totals: readonly GridTotalsRow[],
  columns: readonly GridColumn<Line>[] = COLUMNS,
  state?: GridColumnState,
): HTMLElement {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <DataGrid<Line>
          name="lines"
          title="Lines"
          countLabel={(_, formatted) => `${formatted} lines`}
          columns={columns}
          source={SOURCE}
          rowKey={(row) => row.id}
          totals={totals}
          defaultColumnState={state}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return screen.getByRole("grid", { name: "Lines" });
}

/** The cell texts of every totals row (a row whose row header starts with "Total"), in document order. */
async function totalsCells(grid: HTMLElement): Promise<string[][]> {
  await waitFor(() => {
    expect(within(grid).getAllByRole("rowheader", { name: /^Total/ }).length).toBeGreaterThan(0);
  });
  return within(grid)
    .getAllByRole("rowheader", { name: /^Total/ })
    .map((header) => header.closest<HTMLElement>("[role='row']"))
    .filter((row): row is HTMLElement => row !== null)
    .map((row) => Array.from(row.children).map((cell) => cell.textContent ?? ""));
}

describe("DS-CMP-10 item 7: per-currency totals rows name their currency", () => {
  it("two-currency totals render the Currency cell per row and no sum across currencies", async () => {
    const grid = renderGrid([GBP_TOTAL, USD_TOTAL]);
    expect(await totalsCells(grid)).toEqual([
      ["Total", "GBP", "4,950.29"],
      ["Total", "USD", "547,053.23"],
    ]);
    expect(grid.textContent).not.toContain(CROSS_CURRENCY_SUM);
    // The header row, two body rows and two totals rows.
    expect(grid.getAttribute("aria-rowcount")).toBe("5");
  });

  it("the Currency cell follows its column when the columns are reordered", async () => {
    const grid = renderGrid([GBP_TOTAL, USD_TOTAL], COLUMNS, {
      ...initialColumnState(COLUMNS),
      order: ["account", "amount", "currency"],
    });
    expect(await totalsCells(grid)).toEqual([
      ["Total", "4,950.29", "GBP"],
      ["Total", "547,053.23", "USD"],
    ]);
  });

  it("a hidden Currency column moves the code into the label of each totals row", async () => {
    const grid = renderGrid([GBP_TOTAL, USD_TOTAL], COLUMNS, {
      ...initialColumnState(COLUMNS),
      hidden: ["currency"],
    });
    expect(await totalsCells(grid)).toEqual([
      ["Total (GBP)", "4,950.29"],
      ["Total (USD)", "547,053.23"],
    ]);
    expect(grid.textContent).not.toContain(CROSS_CURRENCY_SUM);
  });

  it("a single totals row keeps the label Total and still names its code in the Currency cell", async () => {
    const grid = renderGrid([USD_TOTAL]);
    expect(await totalsCells(grid)).toEqual([["Total", "USD", "547,053.23"]]);
    expect(within(grid).getByRole("rowheader", { name: "Total" })).toBeTruthy();
  });

  it("a single-currency grid without a Currency column keeps the label Total", async () => {
    const grid = renderGrid([USD_TOTAL], [ACCOUNT, AMOUNT], {
      ...initialColumnState([ACCOUNT, AMOUNT]),
    });
    expect(await totalsCells(grid)).toEqual([["Total", "547,053.23"]]);
  });
});
