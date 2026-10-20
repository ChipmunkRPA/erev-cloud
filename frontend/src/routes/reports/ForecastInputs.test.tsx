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
        effective_from: "2026-01-01T01:00:00.123456+01:00",
        effective_to: null,
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
  expect(screen.queryByRole("button", { name: "Save assumptions" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Publish assumptions" })).toBeNull();
});

it("edits and clears UTC boundaries with the row version, and requires saving before publication", async () => {
  state.submit.mockResolvedValue({ kind: "network-error" });
  open();
  await screen.findByText(/BUDGET — Budget/);
  const start = screen.getAllByLabelText("Effective from (UTC)").at(-1) as HTMLInputElement;
  const end = screen.getAllByLabelText("Effective to (UTC)").at(-1) as HTMLInputElement;
  expect(start.value).toBe("2026-01-01T00:00:00.123");
  fireEvent.change(end, { target: { value: "2026-02-01T00:00" } });
  fireEvent.click(screen.getByRole("button", { name: "Publish assumptions" }));
  expect(screen.queryByRole("button", { name: "Confirm publication" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Save assumptions" }));
  await waitFor(() =>
    expect(state.submit).toHaveBeenCalledWith(
      expect.objectContaining({ method: "PATCH" }),
      { name: "Budget", effective_to: "2026-02-01T00:00Z" },
      { ifMatch: '"r7"' },
    ),
  );
  // Unedited microsecond source timestamp is omitted, rather than rounded and rewritten.
  fireEvent.change(start, { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "Save assumptions" }));
  await waitFor(() =>
    expect(state.submit).toHaveBeenLastCalledWith(
      expect.objectContaining({ method: "PATCH" }),
      { name: "Budget", effective_from: null, effective_to: "2026-02-01T00:00Z" },
      { ifMatch: '"r7"' },
    ),
  );
});
it("rejects equal or reversed effective boundaries before submission", async () => {
  open();
  await screen.findByText(/BUDGET — Budget/);
  fireEvent.change(screen.getAllByLabelText("Effective to (UTC)").at(-1) as HTMLInputElement, {
    target: { value: "2025-12-31T00:00" },
  });
  expect(screen.getByRole("alert").textContent).toContain("must be later");
  fireEvent.click(screen.getByRole("button", { name: "Save assumptions" }));
  expect(state.submit).not.toHaveBeenCalled();
});
