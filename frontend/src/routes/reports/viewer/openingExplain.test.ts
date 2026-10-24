// @vitest-environment jsdom
import { expect, it } from "vitest";
import type { ReportDefinition } from "../../../lib/api/queries/reports";
import { reportColumns } from "./specs";

it.each([1, 2])("offers all opening-liability money cells in section %s", (number) => {
  const definition: ReportDefinition = {
    code: "revenue_from_opening_liability", version: 1, name: "Opening liability", kind: "STANDARD",
    description: "Disclosure", parameters_schema: {}, output_formats: ["JSON"],
    tie_outs: [], ipe_logic: null,
  };
  const money = { amount: "26.67", currency: "GBP" };
  const columns = reportColumns({ definition, periods: [], bands: [], section: {
    number, heading: "Opening", totals: [], rows: [{ row_key: number === 1 ? "summary:GBP" : "combined:group",
      currency: "GBP", opening_contract_liability: money, revenue_recognized: money, revenue_from_opening: money,
    }],
  }});
  expect(columns.filter(c => c.drillable).map(c => c.key).sort()).toEqual([
    "opening_contract_liability", "revenue_from_opening", "revenue_recognized",
  ]);
});

it("offers acquisition explanations only on their rollforward cells", () => {
  const definition: ReportDefinition = {
    code: "contract_balance_rollforward", version: 1, name: "Rollforward", kind: "STANDARD",
    description: "Disclosure", parameters_schema: {}, output_formats: ["JSON"],
    tie_outs: [], ipe_logic: null,
  };
  const money = { amount: "10000.00", currency: "EUR" };
  const acquired = { row_key: "BUSINESS_COMBINATIONS", line_code: "BUSINESS_COMBINATIONS", contract_liability: money };
  const opening = { row_key: "OPENING", line_code: "OPENING", contract_liability: money };
  const columns = reportColumns({ definition, periods: [], bands: [], section: {
    number: 1, heading: "Rollforward", totals: [], rows: [acquired, opening],
  }});
  const column = columns.find(c => c.key === "contract_liability")!;
  expect(column.drillable).toBe(true);
  expect(column.drillableWhen?.(acquired)).toBe(true);
  expect(column.drillableWhen?.(opening)).toBe(false);
});


it("offers acquisition balance explanations only with retained source periods", () => {
  const definition: ReportDefinition = {
    code: "contract_balances", version: 1, name: "Balances", kind: "STANDARD",
    description: "Balances", parameters_schema: {}, output_formats: ["JSON"],
    tie_outs: [], ipe_logic: null,
  };
  const money = { amount: "80000.00", currency: "USD" };
  const acquired = { row_key: "contract:ACQUIRED:US", acquisition_source_period: "FY2026-P08", contract_asset_noncurrent: money, refund_liability: money };
  const ordinary = { row_key: "contract:ORDINARY:US", contract_asset_noncurrent: money, refund_liability: money };
  const columns = reportColumns({ definition, periods: [], bands: [], section: {
    number: 1, heading: "Balances", totals: [], rows: [acquired, ordinary],
  }});
  const column = columns.find(c => c.key === "contract_asset_noncurrent")!;
  expect(column.drillable).toBe(true);
  expect(column.drillableWhen?.(acquired)).toBe(true);
  expect(column.drillableWhen?.(ordinary)).toBe(false);
  expect(columns.find(c => c.key === "refund_liability")?.drillable).toBe(false);
});
