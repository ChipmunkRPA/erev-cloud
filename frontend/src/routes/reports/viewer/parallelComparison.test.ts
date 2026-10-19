// @vitest-environment jsdom
import { expect, it } from "vitest";
import type { ReportDefinition, ReportRow } from "../../../lib/api/queries/reports";
import { reportColumns, sectionsOf } from "./specs";

it("keeps journal and balance measures in their own comparison sections", () => {
  const definition: ReportDefinition = {
    code: "parallel_run_comparison", version: 1, name: "Parallel-run comparison", kind: "STANDARD",
    description: "Comparison", parameters_schema: {}, output_formats: ["JSON"], tie_outs: [], ipe_logic: null,
  };
  const rows: ReportRow[] = [1, 2].map(section => ({
    row_key: `row:${section}`, section, account: section === 1 ? "21001" : null,
    legacy_debit: section === 1 ? { amount: "295.69", currency: "USD" } : null,
    legacy_net_position: section === 2 ? { amount: "-58.85", currency: "USD" } : null,
  }));
  const sections = sectionsOf(definition, rows);
  expect(sections.map(section => section.heading)).toEqual(["Journal lines by account", "Contract balances"]);
  const [journalSection, balanceSection] = sections;
  if (!journalSection || !balanceSection) throw new Error("Both comparison sections are required");
  const journal = reportColumns({ definition, section: journalSection, periods: [], bands: [] });
  const balance = reportColumns({ definition, section: balanceSection, periods: [], bands: [] });
  expect(journal.map(column => column.key)).not.toContain("legacy_net_position");
  expect(balance.map(column => column.key)).not.toContain("legacy_debit");
  expect(balance.find(column => column.key === "legacy_net_position")?.header).toContain("Legacy billed less recognized");
  expect([...journal, ...balance].some(column => column.drillable)).toBe(false);
});
