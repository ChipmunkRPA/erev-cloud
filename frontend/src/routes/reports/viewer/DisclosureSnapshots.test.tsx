// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { fetchDisclosureSnapshot, fetchDisclosureSnapshots, type DisclosureSnapshot } from "../../../lib/api/queries/disclosures";
import { DisclosureSnapshots } from "./DisclosureSnapshots";
vi.mock("../../../lib/api/queries/disclosures", () => ({ fetchDisclosureSnapshot: vi.fn(), fetchDisclosureSnapshots: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const snapshot: DisclosureSnapshot = {
  id: "snapshot", disclosure_kind: "DISAGGREGATION", entity_id: "entity", entity_code: "US",
  book: "ASC606", period_id: "period", period_key: "2026-10", period_lock_id: null,
  report_run_id: "parent", source: "DRAFT", data_sha256: "a".repeat(64), created_at: "2026-10-19T00:00:00Z",
};
function expand(label: string) {
  const details = screen.getByText(label).closest("details");
  if (details === null) throw new Error("Missing details");
  details.open = true;
  fireEvent(details, new Event("toggle"));
}
function mount() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><DisclosureSnapshots runId="parent" /></QueryClientProvider>);
}
it("loads on demand, verifies selected content and keeps suppressed inputs hidden", async () => {
  vi.mocked(fetchDisclosureSnapshots).mockResolvedValue([snapshot]);
  vi.mocked(fetchDisclosureSnapshot).mockResolvedValue({ ...snapshot, data: { known_at: "2026-10-18T00:00:00Z", quarter: true, children: [{ suppressed: "hidden-amount" }] } });
  mount();
  expect(fetchDisclosureSnapshots).not.toHaveBeenCalled();
  expand("Saved disclosure snapshots");
  await screen.findByText("Revenue disaggregation — Draft");
  expect(fetchDisclosureSnapshots).toHaveBeenCalledWith("parent");
  expect(fetchDisclosureSnapshot).not.toHaveBeenCalled();
  expect(screen.queryByText("Saved content verified by the server")).toBeNull();
  expand("Revenue disaggregation — Draft");
  await screen.findByText("Saved content verified by the server");
  expect(fetchDisclosureSnapshot).toHaveBeenCalledWith("snapshot");
  expect(screen.getByText("2026-10-18T00:00:00Z")).toBeTruthy();
  expect(screen.queryByText("hidden-amount")).toBeNull();
});
it("shows failed verification and supports retry", async () => {
  vi.mocked(fetchDisclosureSnapshots).mockResolvedValue([snapshot]);
  vi.mocked(fetchDisclosureSnapshot).mockRejectedValueOnce(new Error("Digest mismatch")).mockResolvedValueOnce({ ...snapshot, data: { known_at: "cutoff", quarter: false } });
  mount();
  expand("Saved disclosure snapshots");
  await screen.findByText("Revenue disaggregation — Draft");
  expand("Revenue disaggregation — Draft");
  await screen.findByText("The saved snapshot could not be verified or loaded.");
  expect(screen.queryByText("Saved content verified by the server")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await screen.findByText("Saved content verified by the server");
});
