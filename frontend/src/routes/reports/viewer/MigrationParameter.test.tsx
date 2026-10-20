// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MigrationParameter } from "./MigrationParameter";
const state = vi.hoisted(() => ({ allowed: true, fetch: vi.fn() }));
vi.mock("../../../lib/access", () => ({ useAccess: () => ({ holdsForAll: () => state.allowed }) }));
vi.mock("../../../lib/api/lists", () => ({ fetchListPage: state.fetch }));
afterEach(() => {
  cleanup();
  state.allowed = true;
  state.fetch.mockReset();
});
function open(value = "") {
  const onChange = vi.fn();
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MigrationParameter value={value} error={undefined} disabled={false} onChange={onChange} />
    </QueryClientProvider>,
  );
  return onChange;
}
const item = (id: string, number: string) => ({
  id,
  migration_no: number,
  mode: "OPENING_BALANCES",
  status: "RECONCILED",
  cutover_date: "2026-01-31",
});
it("loads older batches and selects the exact migration ID", async () => {
  state.fetch
    .mockResolvedValueOnce({ items: [item("first", "MIG-002")], nextCursor: "older", total: null })
    .mockResolvedValueOnce({ items: [item("second", "MIG-001")], nextCursor: null, total: null });
  const change = open();
  fireEvent.click(await screen.findByRole("button", { name: "Load older migrations" }));
  await waitFor(() => expect(state.fetch).toHaveBeenCalledTimes(2));
  expect(state.fetch.mock.calls[1]?.[2]).toBe("older");
  const input = screen.getByRole("combobox", { name: "Migration" });
  fireEvent.change(input, { target: { value: "MIG-001" } });
  fireEvent.keyDown(input, { key: "ArrowDown" });
  fireEvent.mouseDown(await screen.findByRole("option", { name: /MIG-001/ }));
  expect(change).toHaveBeenCalledWith("second");
});
it("preserves an older selected ID outside the loaded page", async () => {
  state.fetch.mockResolvedValue({ items: [], nextCursor: null, total: null });
  const change = open("saved-batch");
  await waitFor(() => expect(state.fetch).toHaveBeenCalledOnce());
  expect((screen.getByRole("combobox", { name: "Migration" }) as HTMLInputElement).value).toBe(
    "saved-batch",
  );
  expect(change).not.toHaveBeenCalled();
});
it("does not request migration metadata without its read permission", () => {
  state.allowed = false;
  open("saved-batch");
  expect(screen.getByRole("textbox", { name: "Migration" })).toBeTruthy();
  expect(state.fetch).not.toHaveBeenCalled();
});
