// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { ForecastComparisonForm } from "./ForecastComparisonForm";

const state = vi.hoisted(() => ({ submit: vi.fn(), exportAllowed: true }));
vi.mock("../../lib/access", () => ({
  useAccess: () => ({
    holdsForEvery: (permission: string) => permission !== "report.export" || state.exportAllowed,
  }),
}));
vi.mock("../../lib/api/commands", () => ({
  useCommand: () => ({ submit: state.submit, pending: false, job: null, problem: null }),
}));
vi.mock("../../lib/api/queries/forecasts", () => ({
  fetchComparisonForecasts: async () => ({
    items: [
      {
        id: "archived-run",
        created_at: "2026-10-18",
        parameters: {
          book_code: "ASC606",
          currency_view: "functional",
          entity_ids: ["entity"],
          horizon_periods: ["FY2026-P10", "FY2026-P11"],
        },
      },
    ],
    nextCursor: null,
  }),
}));
vi.mock("../../lib/api/queries/tenant", () => ({
  entitiesKey: () => ["entities"],
  fetchActiveEntities: async () => [{ id: "entity", code: "US" }],
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  state.exportAllowed = true;
});
function page() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <ForecastComparisonForm />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
it("submits an archived forecast with its fixed entity and currency scope", async () => {
  state.submit.mockResolvedValue({ kind: "accepted" });
  page();
  await screen.findByText(/2026-10-18 · ASC606/);
  fireEvent.change(screen.getByLabelText("Saved forecast"), { target: { value: "archived-run" } });
  fireEvent.change(screen.getByLabelText("Compare by"), { target: { value: "REVENUE_CATEGORY" } });
  fireEvent.click(screen.getByRole("button", { name: "Run comparison" }));
  await waitFor(() =>
    expect(state.submit).toHaveBeenCalledWith({
      report_code: "actual_vs_forecast",
      output_format: "JSON",
      parameters: {
        forecast_run_id: "archived-run",
        entity_codes: ["US"],
        currency_view: "functional",
        row_dimension: "REVENUE_CATEGORY",
        from_period_key: "FY2026-P10",
        to_period_key: "FY2026-P11",
      },
    }),
  );
});
it("does not offer file formats without export permission", async () => {
  state.exportAllowed = false;
  page();
  await screen.findByText(/2026-10-18 · ASC606/);
  fireEvent.change(screen.getByLabelText("Saved forecast"), { target: { value: "archived-run" } });
  expect((screen.getByRole("option", { name: "XLSX" }) as HTMLOptionElement).disabled).toBe(true);
});
