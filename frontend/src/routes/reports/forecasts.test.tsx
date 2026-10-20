// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { ForecastRunsPage } from "./forecasts";

const state = vi.hoisted(() => ({
  sandbox: true,
  exportAllowed: true,
  showOutput: false,
  submit: vi.fn(),
}));
vi.mock("./ForecastComparisonForm", () => ({ ForecastComparisonForm: () => null }));
vi.mock("./frame", () => ({ ReportsHeader: () => null }));
vi.mock("../../lib/api/queries/me", () => ({
  useMe: () => ({
    data: {
      active_membership_id: "member",
      memberships: [
        { membership_id: "member", tenant: { kind: state.sandbox ? "sandbox" : "production" } },
      ],
    },
  }),
}));
vi.mock("../../lib/access", () => ({
  useAccess: () => ({
    holdsForAll: () => true,
    holds: () => true,
    holdsForEvery: () => state.exportAllowed,
  }),
}));
vi.mock("../../lib/api/commands", () => ({
  useCommand: () => ({ submit: state.submit, pending: false, job: null, problem: null }),
}));
vi.mock("../../lib/api/queries/forecasts", () => ({
  forecastInputsKey: ["inputs"],
  forecastRunsKey: ["runs"],
  fetchForecastInputs: async () => [{ id: "input", name: "Base", version_no: 2 }],
  fetchForecastRuns: async () => ({
    items: state.showOutput
      ? [
          {
            id: "forecast",
            status: "SUCCEEDED",
            created_at: "2026-10-19",
            problem: null,
            parameters: { horizon_periods: ["2026-01"] },
            report_run_ids: ["xlsx-output"],
          },
        ]
      : [],
    nextCursor: null,
  }),
}));
vi.mock("../../lib/api/queries/tenant", () => ({
  entitiesKey: () => ["entities"],
  fetchActiveEntities: async () => [{ id: "entity", code: "US" }],
  fetchPeriods: async () =>
    ["01", "02"].map((n) => ({ period: { period_key: `2026-${n}`, name: `Period ${n}` } })),
}));

vi.mock("./viewer/ForecastPack", () => ({ ForecastPack: () => <p>Saved forecast sections</p> }));
vi.mock("../../lib/api/queries/reports", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../lib/api/queries/reports")>()),
  fetchReportRun: async () => ({
    id: "xlsx-output",
    report_run_no: "RPT-1",
    status: "SUCCEEDED",
    output: { format: "XLSX" },
    entity_scope: [{ id: "entity", code: "US" }],
  }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  state.showOutput = false;
  state.sandbox = true;
  state.exportAllowed = true;
});
function page() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <ForecastRunsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
it("submits the selected publication, consecutive horizon and formats", async () => {
  state.submit.mockResolvedValue({ kind: "accepted" });
  page();
  await screen.findByText("Base v2");
  fireEvent.change(screen.getByLabelText("Published input set"), { target: { value: "input" } });
  fireEvent.click(screen.getByLabelText("US"));
  await waitFor(() =>
    expect(screen.getByLabelText("From period").querySelectorAll("option")).toHaveLength(3),
  );
  fireEvent.change(screen.getByLabelText("From period"), { target: { value: "2026-01" } });
  fireEvent.change(screen.getByLabelText("To period"), { target: { value: "2026-02" } });
  fireEvent.click(screen.getByLabelText("XLSX"));
  fireEvent.click(screen.getByRole("button", { name: "Run forecast" }));
  await waitFor(() =>
    expect(state.submit).toHaveBeenCalledWith({
      forecast_event_set_id: "input",
      parameters: {
        entity_ids: ["entity"],
        horizon_periods: ["2026-01", "2026-02"],
        book_code: "ASC606",
        currency_view: "transaction",
        output_formats: ["JSON", "XLSX"],
      },
    }),
  );
});
it("does not offer forecast creation in production", () => {
  state.sandbox = false;
  page();
  expect(screen.queryByRole("button", { name: "Run forecast" })).toBeNull();
  expect(screen.getByText(/Open a scenario workspace/)).toBeTruthy();
});
it("keeps file export unavailable without export permission", async () => {
  state.exportAllowed = false;
  page();
  fireEvent.click(await screen.findByLabelText("US"));
  expect((screen.getByLabelText("XLSX") as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByLabelText("JSON") as HTMLInputElement).disabled).toBe(false);
});

it("opens saved file-format sections only with export access", async () => {
  state.showOutput = true;
  page();
  fireEvent.click(await screen.findByRole("button", { name: "View forecast figures" }));
  expect(screen.getByText("Saved forecast sections")).toBeTruthy();
  cleanup();
  state.exportAllowed = false;
  page();
  await screen.findByText("XLSX — RPT-1");
  expect(screen.queryByRole("button", { name: "View forecast figures" })).toBeNull();
});
