// @vitest-environment jsdom
import { expect, it } from "vitest";
import type { ReportDefinition, ReportRow } from "../../../lib/api/queries/reports";
import { reportColumns, sectionsOf, totalsRows, registerEmptyCopy } from "./specs";

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
    expect(columns.map(column => column.key)).toEqual([
      "measure_label", "scope", "currency", "earlier_value", "later_value", "change", "driver_label",
    ]);
    expect(columns.map(column => column.key)).not.toContain("contract_external_id");
  }
});


it("labels each measure total separately and states identical frozen figures", () => {
  const section = { number: 2, heading: "Changes by contract", rows: [], totals: [
    { row_key: "TOTAL:USD:REVENUE:2", measure_label: "Revenue", change: { amount: "117.68", currency: "USD" } },
    { row_key: "TOTAL:USD:RPO:2", measure_label: "Remaining performance obligations", change: { amount: "-117.68", currency: "USD" } },
  ] };
  expect(totalsRows(section).map(row => [row.label, row.values.change])).toEqual([
    ["Total · Revenue (USD)", "117.68"], ["Total · Remaining performance obligations (USD)", "-117.68"],
  ]);
  expect(registerEmptyCopy("variance_between_closes", { parameters: {}, control_totals: {} }, {
    entity: null, book: null, periodKey: null, periods: [], snapshot: null, knownAt: null, currencyView: null,
  })).toEqual({ title: "No changes between the two locks", description: "The figures frozen at both locks are identical." });
});
