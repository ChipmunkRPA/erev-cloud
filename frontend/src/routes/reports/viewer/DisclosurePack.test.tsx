// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { fetchDisclosureSections, fetchReportRows } from "../../../lib/api/queries/reports";
import { DisclosurePack } from "./DisclosurePack";

vi.mock("../../../lib/api/queries/reports", () => ({ fetchDisclosureSections: vi.fn(), fetchReportRows: vi.fn() }));
vi.mock("./ReportGrid", () => ({ ReportGrid: ({ section }: { section: { rows: readonly { row_key: string }[] } }) => <div>{section.rows.map(row => <span key={row.row_key}>{row.row_key}</span>)}</div> }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("loads expanded tables separately and never requests omitted amounts", async () => {
  vi.mocked(fetchDisclosureSections).mockResolvedValue([
    { number: 1, title: "Disaggregation", interim_required: true, tables: [
      { key: "revenue", title: "Revenue", basis: "PERIOD", omitted: false, notes: [], source_run_id: "child-one", source_sha256: "a".repeat(64), row_count: 1 },
    ] },
    { number: 2, title: "Balances", interim_required: false, tables: [
      { key: "omitted", title: "Rollforward", basis: "PERIOD", omitted: true, notes: ["Omitted under the elected relief."], source_run_id: "child-two", source_sha256: "b".repeat(64), row_count: 0 },
    ] },
  ]);
  vi.mocked(fetchReportRows).mockResolvedValue({ rows: [{ row_key: "retained-revenue-row" }], columns: [] });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><DisclosurePack runId="parent" /></QueryClientProvider>);
  await screen.findByRole("heading", { name: "1. Disaggregation" });
  expect(fetchReportRows).not.toHaveBeenCalled();
  const revenue = screen.getByText("Revenue — Period (1)").closest("details");
  if (revenue === null) throw new Error("Revenue details missing");
  revenue.open = true;
  fireEvent(revenue, new Event("toggle"));
  await screen.findByText("retained-revenue-row");
  expect(fetchReportRows).toHaveBeenCalledWith("parent", "revenue");
  const omitted = screen.getByText("Rollforward — Period (0)").closest("details");
  if (omitted === null) throw new Error("Omitted details missing");
  omitted.open = true;
  fireEvent(omitted, new Event("toggle"));
  expect(screen.getByText("Omitted under the elected relief.")).toBeTruthy();
  expect(fetchReportRows).toHaveBeenCalledTimes(1);
});
