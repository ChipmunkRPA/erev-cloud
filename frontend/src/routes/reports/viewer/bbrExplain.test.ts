// @vitest-environment jsdom
import { expect, it } from "vitest";
import type { ReportCellContributor, ReportDefinition } from "../../../lib/api/queries/reports";
import { reportColumns } from "./specs";
import { sourceHref } from "./CellContributors";

it("offers contributors for all four BBR measures", () => {
  const definition: ReportDefinition = {
    code: "bookings_billings_revenue", version: 1, name: "BBR", kind: "STANDARD",
    description: "Metrics", parameters_schema: {}, output_formats: ["JSON"],
    tie_outs: [], ipe_logic: null,
  };
  const money = { amount: "25.00", currency: "USD" };
  const columns = reportColumns({ definition, periods: [], bands: [], section: {
    number: 1, heading: "BBR", totals: [], rows: [{ row_key: "period:P01:US",
      period_label: "January", entity_code: "US", currency: "USD",
      booked_new: money, booked_modifications: money, billings: money, revenue: money,
    }],
  }});
  expect(columns.filter(c => c.drillable).map(c => c.key).sort()).toEqual([
    "billings", "booked_modifications", "booked_new", "revenue",
  ]);
});

it("accepts only internal business source routes", () => {
  const id = "00000000-0000-4000-8000-000000000001";
  const source: ReportCellContributor = { object_type: "contract_event", id,
    measure: "billings", value: { amount: "25.00", currency: "USD" },
    href: `/contracts/${id}/billing`,
  };
  expect(sourceHref(source)).toBe(source.href);
  expect(sourceHref({ ...source, href: `/contracts/${id}/modifications/${id}` })).not.toBeNull();
  expect(sourceHref({ ...source, href: "https://example.invalid/contracts" })).toBeNull();
  expect(sourceHref({ ...source, href: `//example.invalid/contracts/${id}/billing` })).toBeNull();
  expect(sourceHref({ ...source, href: `/api/v1/explain/subledger_line/${id}/amount` })).toBeNull();
});
