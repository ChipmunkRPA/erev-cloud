// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { DisclosureRegister } from "./disclosures";
const state = vi.hoisted(() => ({ allowed: true, fetch: vi.fn() }));
vi.mock("../../lib/access", () => ({ useAccess: () => ({ holdsAnywhere: () => state.allowed }) }));
vi.mock("../../lib/api/queries/disclosures", () => ({ fetchDisclosureSnapshotPage: state.fetch }));
vi.mock("./frame", () => ({ ReportsHeader: () => <h1>Reports</h1> }));
vi.mock("./viewer/DisclosureSnapshots", () => ({
  Snapshot: ({ snapshot }: { snapshot: { id: string } }) => <p>{snapshot.id}</p>,
}));
afterEach(() => {
  cleanup();
  state.fetch.mockReset();
  state.allowed = true;
});
function open() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter
        initialEntries={[
          "/reports/disclosures?entity=US&book=ASC606&period=2026-01&disclosure_kind=RPO",
        ]}
      >
        <DisclosureRegister />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
it("uses context and disclosure filters, pages metadata, and links the original report", async () => {
  state.fetch
    .mockResolvedValueOnce({
      items: [{ id: "draft-one", report_run_id: "source-run" }],
      nextCursor: "older",
    })
    .mockResolvedValueOnce({
      items: [{ id: "draft-two", report_run_id: "source-run-2" }],
      nextCursor: null,
    });
  open();
  expect(await screen.findByText("draft-one")).toBeTruthy();
  expect(state.fetch).toHaveBeenCalledWith(
    {
      entity: "US",
      book: "ASC606",
      period: "2026-01",
      disclosure_kind: "RPO",
      sort: "-created_at",
    },
    null,
  );
  expect(screen.getByRole("link", { name: "Open source report" }).getAttribute("href")).toBe(
    "/reports/runs/source-run",
  );
  fireEvent.click(screen.getByRole("button", { name: "Load older snapshots" }));
  expect(await screen.findByText("draft-two")).toBeTruthy();
  expect(state.fetch.mock.calls[1]?.[1]).toBe("older");
});
it("does not read snapshot metadata without report permission", async () => {
  state.allowed = false;
  open();
  await waitFor(() => expect(screen.queryByRole("combobox")).toBeNull());
  expect(state.fetch).not.toHaveBeenCalled();
});
