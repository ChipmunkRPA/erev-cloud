// @vitest-environment jsdom
import { expect, it } from "vitest";
import type { ReportDefinition } from "../../../lib/api/queries/reports";
import { EXPLAIN_OBJECT_TYPES } from "../../../lib/api/queries/explain";
import { reportColumns } from "./specs";

it("offers Explain only for the loss register's provision balance", () => {
  const definition: ReportDefinition = {
    code: "loss_provision_register",
    version: 1,
    name: "Loss provision register",
    kind: "REGISTER",
    description: "Loss tests",
    parameters_schema: {},
    output_formats: ["JSON"],
    tie_outs: [],
    ipe_logic: null,
  };
  const amount = { amount: "25.00", currency: "USD" };
  const columns = reportColumns({
    definition,
    periods: [],
    bands: [],
    section: {
      number: 1,
      heading: "Loss provision register",
      totals: [],
      rows: [
        {
          row_key: "contract:C1",
          provision_balance: amount,
          expected_margin: amount,
          provision_movement: amount,
        },
      ],
    },
  });
  expect(columns.filter((column) => column.drillable).map((column) => column.key)).toEqual([
    "provision_balance",
  ]);
  expect(EXPLAIN_OBJECT_TYPES).toContain("loss_provision_version");
});
