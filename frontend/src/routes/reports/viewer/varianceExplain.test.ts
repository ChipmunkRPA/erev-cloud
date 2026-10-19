// @vitest-environment jsdom
import { expect, it } from "vitest";
import type { ReportDefinition, ReportRow } from "../../../lib/api/queries/reports";
import { reportColumns, sectionsOf } from "./specs";

it("separates variance sections and explains only the change in either section", () => {
  const definition: ReportDefinition = {
    code: "variance_between_closes", version: 1, name: "Variance between closes", kind: "STANDARD",
    description: "Changes", parameters_schema: {}, output_formats: ["JSON"], tie_outs: [], ipe_logic: null,
  };
  const money = { amount: "58.84", currency: "USD" };
  const rows: ReportRow[] = [1, 2].map(section => ({
    row_key: `row:${section}`, section, measure_label: "Revenue", scope: "Contract 2", currency: "USD",
    earlier_value: money, later_value: money, change: money, driver_label: "Late events",
    measure: "REVENUE", driver: "LATE_EVENT", contract_external_id: "Contract 2",
  }));
  const sections = sectionsOf(definition, rows);
  expect(sections.map(section => [section.heading, section.rows.length])).toEqual([
    ["Change by driver", 1], ["Changes by contract", 1],
  ]);
  for (const section of sections) {
    const columns = reportColumns({ definition, section, periods: [], bands: [] });
    expect(columns.filter(column => column.drillable).map(column => column.key)).toEqual(["change"]);
    expect(columns.map(column => column.key)).not.toContain("measure");
    expect(columns.map(column => column.key)).not.toContain("contract_external_id");
  }
});
