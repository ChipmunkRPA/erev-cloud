// @vitest-environment jsdom
import { expect, it } from "vitest";
import type { ReportCellContributor, ReportDefinition } from "../../../lib/api/queries/reports";
import { reportColumns } from "./specs";
import { sourceHref } from "./CellContributors";

it("opens source details for modification amounts, including native and analytical currency columns", () => {
  const definition: ReportDefinition = {
    code: "modification_register",
    version: 1,
    name: "Modifications",
    kind: "REGISTER",
    description: "Modifications",
    parameters_schema: {},
    output_formats: ["JSON"],
    tie_outs: [],
    ipe_logic: null,
  };
  const money = { amount: "25.00", currency: "USD" };
  const columns = reportColumns({
    definition,
    periods: [],
    bands: [],
    section: {
      number: 1,
      heading: "Modifications",
      totals: [],
      rows: [
        {
          row_key: "modification:MOD-1:O1",
          modification_no: "MOD-1",
          tp_change: money,
          catch_up_amount: money,
          tp_fixed: money,
          catch_up_functional_calculation: money,
          tp_change_functional_equivalent: money,
          catch_up_reporting: money,
          reporting_basis: "Analytical equivalent",
        },
      ],
    },
  });
  expect(
    columns
      .filter((c) => c.drillable)
      .map((c) => c.key)
      .sort(),
  ).toEqual([
    "catch_up_amount",
    "catch_up_functional_calculation",
    "catch_up_reporting",
    "tp_change",
    "tp_change_functional_equivalent",
    "tp_fixed",
  ]);
});

it("allows retained trace nodes while rejecting other destinations and query parameters", () => {
  const id = "00000000-0000-4000-8000-000000000001";
  const source: ReportCellContributor = {
    object_type: "modification",
    id,
    measure: "tp_change",
    value: { amount: "25.00", currency: "USD" },
    href: `/trace/${id}?node=modification_tp_change%40event%3AC1%3A5`,
  };
  expect(sourceHref(source)).toBe(source.href);
  expect(sourceHref({ ...source, href: `/trace/${id}` })).toBe(`/trace/${id}`);
  for (const href of [
    "https://example.invalid/trace",
    `//example.invalid/trace/${id}`,
    `/trace/${id}?redirect=https://example.invalid`,
    `/trace/${id}?node=x&redirect=y`,
    `/api/v1/calc-traces/${id}`,
    "/trace/invalid",
  ]) {
    expect(sourceHref({ ...source, href })).toBeNull();
  }
});
