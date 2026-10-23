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
