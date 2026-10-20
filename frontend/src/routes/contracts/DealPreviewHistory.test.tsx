// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { DealPreviewHistory } from "./DealPreviewHistory";
const fetch = vi.hoisted(() => vi.fn());
vi.mock("../../lib/api/queries/deal-previews", () => ({
  fetchDealPreviews: fetch,
  dealHistoryKey: ["deal-previews", "tenant"],
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
function page() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <DealPreviewHistory />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
function row(id: string, saved: string | null) {
  return {
    id,
    created_at: "2026-10-19T12:00:00Z",
    saved_contract_id: saved,
    proposal: {
      customer_name: id,
      entity_code: "US",
      start_date: "2026-11-01",
      lines: [{ product_code: "PLATFORM" }],
    },
  };
}
it("loads lazily, pages older previews, and opens retained results/drafts without discarding current input", async () => {
  fetch
    .mockResolvedValueOnce({ items: [row("new", null)], nextCursor: "older" })
    .mockResolvedValueOnce({ items: [row("old", "draft")], nextCursor: null });
  page();
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Show previous deal previews" }));
  const first = await screen.findByRole("link", { name: "Open preview (new tab)" });
  expect(first.getAttribute("href")).toBe("/contracts/deal-preview?preview=new");
  expect(first.getAttribute("target")).toBe("_blank");
  fireEvent.click(screen.getByRole("button", { name: "Load older previews" }));
  expect(await screen.findByRole("link", { name: "Open draft (new tab)" })).toHaveProperty(
    "href",
    expect.stringContaining("/contracts/draft/obligations"),
  );
  expect(fetch).toHaveBeenNthCalledWith(2, "older");
  expect(screen.getAllByRole("link", { name: "Open preview (new tab)" })).toHaveLength(2);
});
it("retries a failed later page without losing already loaded rows", async () => {
  fetch
    .mockResolvedValueOnce({ items: [row("first", null)], nextCursor: "older" })
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ items: [], nextCursor: null });
  page();
  fireEvent.click(screen.getByRole("button", { name: "Show previous deal previews" }));
  fireEvent.click(await screen.findByRole("button", { name: "Load older previews" }));
  fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
  expect(fetch).toHaveBeenLastCalledWith("older");
  expect(screen.getByRole("link", { name: "Open preview (new tab)" })).toBeTruthy();
});
