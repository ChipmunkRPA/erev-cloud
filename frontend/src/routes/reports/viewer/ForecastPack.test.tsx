// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { fetchForecastSections, fetchReportRows } from "../../../lib/api/queries/reports";
import { ForecastPack } from "./ForecastPack";

vi.mock("../../../lib/api/queries/reports", () => ({ fetchForecastSections: vi.fn(), fetchReportRows: vi.fn() }));
vi.mock("./ReportGrid", () => ({ ReportGrid: ({ section }: { section: { rows: readonly { row_key: string }[] } }) => <div>{section.rows.map(row => <span key={row.row_key}>{row.row_key}</span>)}</div> }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("shows the saved publication and reads only the opened forecast table", async () => {
  vi.mocked(fetchForecastSections).mockResolvedValue({
    items: [], columns: [], next_cursor: null,
    forecast: { scenario_name: "Q4 outlook", event_set_name: "Base", event_set_version: 2, horizon_periods: ["FY2026-P10", "FY2026-P11"], known_at: "2026-10-19T12:00:00Z" },
    sections: [{ number: 1, title: "Forecast revenue by period", interim_required: false,
      tables: [{ key: "revenue", title: "Forecast revenue by period", basis: "FORECAST", omitted: false, notes: [], source_run_id: null, source_sha256: "a".repeat(64), row_count: 1 }] }],
  });
  vi.mocked(fetchReportRows).mockResolvedValue({ rows: [{ row_key: "contract:C1:O1" }], columns: [] });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ForecastPack runId="forecast-one" /></QueryClientProvider>);
  await screen.findByText("Scenario Q4 outlook");
  expect(screen.getByText("Event set Base v2")).toBeTruthy();
  expect(screen.getByText("Horizon FY2026-P10 – FY2026-P11")).toBeTruthy();
  expect(fetchReportRows).not.toHaveBeenCalled();
  expect(screen.queryByText(/Draft disclosure/)).toBeNull();
  const table = screen.getByText("Forecast revenue by period — Forecast (1)").closest("details");
  if (table === null) throw new Error("Forecast table missing");
  table.open = true;
  fireEvent(table, new Event("toggle"));
  await screen.findByText("contract:C1:O1");
  expect(fetchReportRows).toHaveBeenCalledWith("forecast-one", "revenue");
});
