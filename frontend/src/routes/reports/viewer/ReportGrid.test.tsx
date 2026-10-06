// @vitest-environment jsdom
// SCREENS_B RPT-R-03, RPT-R-04 and DESIGN_SYSTEM DS-CMP-10 item 7 (rev 1.4; PR-8.7): a report's `currency`
// column is the DS-FMT-12 Currency column, so the totals rows of a two-currency section name their ISO code
// per row while their figures stay the run's (never a sum across currencies).
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, expect, it } from "vitest";

import { createQueryClient } from "../../../app/providers";
import type { ReportRow } from "../../../lib/api/queries/reports";
import { registerCurrencies } from "../../../lib/format";
import { installGridViewport } from "../../../test/layout";
import { ReportGrid } from "./ReportGrid";
import type { ReportColumn, ReportSection } from "./specs";

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

const RUN_ID = "5b0c7a1e-3d2f-4e6a-9b8c-7d6e5f4a3b2c";

function money(amount: string, currency: string) {
  return { amount, currency };
}

// SF-06:entries "By account" of a run over AVM-UK and AVM-US lines (L8-merge.md run 2 figures).
const ROWS: readonly ReportRow[] = [
  { row_key: "account:5001", account: "5001", currency: "GBP", debit: money("4950.29", "GBP") },
  { row_key: "account:5002", account: "5002", currency: "USD", debit: money("547053.23", "USD") },
];
const COLUMNS: readonly ReportColumn[] = [
  { key: "account", header: "Account", kind: "identifier", drillable: false },
  { key: "currency", header: "Currency", kind: "text", drillable: false },
  { key: "debit", header: "Debit", kind: "money", drillable: false },
];
const SECTION: ReportSection = { number: 1, heading: "By account", rows: ROWS, totals: [] };

it("two-currency totals render the Currency cell per row", async () => {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <ReportGrid
          runId={RUN_ID}
          section={SECTION}
          columns={COLUMNS}
          totals={[
            { key: "TOTAL:GBP", currency: "GBP", values: { debit: "4950.29" } },
            { key: "TOTAL:USD", currency: "USD", values: { debit: "547053.23" } },
          ]}
          onDrill={() => undefined}
          testIdPrefix="SF-06"
          name="by-account"
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const grid = screen.getByRole("grid", { name: "By account" });
  await waitFor(() => {
    expect(within(grid).getAllByRole("rowheader", { name: "Total" })).toHaveLength(2);
  });
  const totals = within(grid)
    .getAllByRole("rowheader", { name: "Total" })
    .map((header) => header.closest<HTMLElement>("[role='row']"))
    .filter((row): row is HTMLElement => row !== null)
    .map((row) => Array.from(row.children).map((cell) => cell.textContent ?? ""));
  expect(totals).toEqual([
    ["Total", "GBP", "4,950.29"],
    ["Total", "USD", "547,053.23"],
  ]);
  expect(grid.textContent).not.toContain("552,003.52");
});
