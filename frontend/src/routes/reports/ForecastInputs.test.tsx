// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { ForecastInputs } from "./ForecastInputs";
const state = vi.hoisted(() => ({ fetch: vi.fn(), submit: vi.fn(), status: "DRAFT" }));
vi.mock("../../lib/access", () => ({ useAccess: () => ({ holdsAnywhere: () => true }) }));
vi.mock("../../lib/api/lists", () => ({ fetchListPage: state.fetch }));
vi.mock("../../lib/api/commands", () => ({
  useCommand: (options: { path: string; method: string }) => ({
    submit: (body: unknown, headers: unknown) => state.submit(options, body, headers),
    pending: false,
    problem: null,
    banner: null,
  }),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  state.status = "DRAFT";
});
function open() {
  state.fetch.mockResolvedValue({
    items: [
      {
        id: "input",
        code: "BUDGET",
        name: "Budget",
        status: state.status,
        version_no: 2,
        row_version: 7,
        api_commands: [],
        import_upload_ids: [],
      },
    ],
    nextCursor: null,
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ForecastInputs />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Manage forecast assumptions" }));
}
it("creates a trimmed draft and clears fields only after success", async () => {
  state.submit.mockResolvedValue({ kind: "succeeded" });
  open();
  fireEvent.change(screen.getByRole("textbox", { name: "Assumption set code" }), {
    target: { value: " NEXT " },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "Assumption set name" }), {
    target: { value: " Next year " },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create assumption draft" }));
  await waitFor(() =>
    expect(state.submit).toHaveBeenCalledWith(
      expect.objectContaining({ path: "/api/v1/forecast-event-sets", method: "POST" }),
      { code: "NEXT", name: "Next year" },
      undefined,
    ),
  );
  await waitFor(() =>
    expect(
      (screen.getByRole("textbox", { name: "Assumption set code" }) as HTMLInputElement).value,
    ).toBe(""),
  );
});
it("requires publication confirmation and sends the saved row version", async () => {
  state.submit.mockResolvedValue({ kind: "network-error" });
  open();
  fireEvent.click(await screen.findByRole("button", { name: "Publish assumptions" }));
  expect(state.submit).not.toHaveBeenCalled();
  expect(
    screen.getByRole("link", { name: "Import changes into this draft" }).getAttribute("href"),
  ).toBe("/data/imports/new?event_set=input");
  expect(screen.getByText(/contains no captured changes/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Confirm publication" }));
  await waitFor(() =>
    expect(state.submit).toHaveBeenCalledWith(
      expect.objectContaining({
        path: "/api/v1/forecast-event-sets/input/publish",
        method: "POST",
      }),
      undefined,
      { ifMatch: '"r7"' },
    ),
  );
  expect(await screen.findByText(/Could not save assumptions/)).toBeTruthy();
});
it("keeps published versions read-only", async () => {
  state.status = "PUBLISHED";
  open();
  await screen.findByText(/BUDGET — Budget/);
  expect(screen.queryByRole("button", { name: "Save name" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Publish assumptions" })).toBeNull();
});
