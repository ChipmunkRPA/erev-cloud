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
function page(initialForecast?: import("../../lib/api/queries/forecasts").ForecastRun) {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <ForecastComparisonForm {...(initialForecast ? { initialForecast } : {})} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
it("defaults to the latest authorized forecast and its complete horizon", async () => {
  state.submit.mockResolvedValue({ kind: "accepted" });
  page();
  await screen.findByText(/2026-10-18 · ASC606/);
  expect((screen.getByLabelText("Saved forecast") as HTMLSelectElement).value).toBe("archived-run");
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

it("keeps an explicit history forecast selected even when it is absent from the choice page", async () => {
  state.submit.mockResolvedValue({ kind: "accepted" });
  const run = {
    id: "chosen-history",
    created_at: "2026-09-01",
    parameters: {
      entity_ids: ["entity"],
      book_code: "ASC606",
      currency_view: "transaction",
      horizon_periods: ["FY2026-P08", "FY2026-P09"],
    },
  } as import("../../lib/api/queries/forecasts").ForecastRun;
  page(run);
  await screen.findByText(/2026-10-18 · ASC606/);
  expect((screen.getByLabelText("Saved forecast") as HTMLSelectElement).value).toBe(run.id);
  fireEvent.click(screen.getByRole("button", { name: "Run comparison" }));
  await waitFor(() =>
    expect(state.submit).toHaveBeenCalledWith(
      expect.objectContaining({
        parameters: expect.objectContaining({
          forecast_run_id: run.id,
          from_period_key: "FY2026-P08",
          to_period_key: "FY2026-P09",
          currency_view: "transaction",
        }),
      }),
    ),
  );
});
