// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { ScenarioPage } from "./scenarios";
const state = vi.hoisted(() => ({
  source: true,
  allowed: true,
  fetch: vi.fn(),
  submit: vi.fn(),
  open: vi.fn(),
  jobId: null as string | null,
}));
vi.mock("./frame", () => ({ ReportsHeader: () => null }));
vi.mock("../../lib/access", () => ({ useAccess: () => ({ holdsForAll: () => state.allowed }) }));
vi.mock("../../lib/api/queries/me", () => ({
  useMe: () => ({
    data: {
      active_membership_id: "m",
      memberships: [
        { membership_id: "m", tenant: { kind: state.source ? "production" : "sandbox" } },
      ],
    },
  }),
}));
vi.mock("../../lib/api/lists", () => ({ fetchListPage: state.fetch }));
vi.mock("../../lib/api/commands", () => ({
  useCommand: () => ({
    submit: state.submit,
    pending: false,
    fieldErrors: {},
    jobId: state.jobId,
    job: undefined,
    problem: null,
  }),
}));
vi.mock("../settings/sandbox", () => ({
  useOpenWorkspace: () => ({ open: state.open, pending: false, problem: null }),
}));
afterEach(() => {
  cleanup();
  state.fetch.mockReset();
  state.submit.mockReset();
  state.open.mockReset();
  state.source = true;
  state.allowed = true;
  state.jobId = null;
});
function open() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ScenarioPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
it("creates a named source scenario and opens an existing scenario workspace", async () => {
  state.fetch.mockResolvedValue({
    items: [
      {
        id: "s",
        name: "Budget",
        purpose: "Next year",
        status: "ACTIVE",
        base_known_at: "2026-10-01T00:00:00Z",
        last_refreshed_at: null,
        scenario_tenant_id: "sandbox",
      },
    ],
    nextCursor: null,
  });
  state.submit.mockResolvedValue({ kind: "accepted" });
  open();
  expect(await screen.findByText("Budget")).toBeTruthy();
  fireEvent.change(screen.getByRole("textbox", { name: "Scenario name" }), {
    target: { value: "  Revised forecast  " },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "Purpose" }), {
    target: { value: "Planning" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create scenario" }));
  await waitFor(() =>
    expect(state.submit).toHaveBeenCalledWith({ name: "Revised forecast", purpose: "Planning" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Open scenario workspace" }));
  expect(state.open).toHaveBeenCalledWith("sandbox", "Budget");
});
it("withholds source requests inside a sandbox", () => {
  state.source = false;
  open();
  expect(state.fetch).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Create scenario" })).toBeNull();
});
it("prevents a second create while an accepted job is still loading", () => {
  state.fetch.mockResolvedValue({ items: [], nextCursor: null });
  state.jobId = "job";
  open();
  fireEvent.submit(
    screen.getByRole("textbox", { name: "Scenario name" }).closest("form") as HTMLFormElement,
  );
  expect(state.submit).not.toHaveBeenCalled();
});

it("applies status filtering on the server before paging", async () => {
  state.fetch.mockResolvedValue({ items: [], nextCursor: null });
  open();
  fireEvent.click(screen.getByRole("combobox", { name: "Scenario status" }));
  fireEvent.mouseDown(await screen.findByRole("option", { name: "Archived" }));
  await waitFor(() =>
    expect(state.fetch).toHaveBeenLastCalledWith(
      "/api/v1/scenarios",
      { sort: "-created_at", status: "ARCHIVED" },
      null,
      { limit: 50, count: false },
    ),
  );
});
