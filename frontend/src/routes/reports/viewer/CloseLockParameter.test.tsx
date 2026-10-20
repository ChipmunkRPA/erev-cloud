// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CloseLockParameter } from "./CloseLockParameter";
import type { ReportContext } from "./specs";
const state = vi.hoisted(() => ({ fetch: vi.fn(), allowed: true }));
vi.mock("../../../lib/access", () => ({ useAccess: () => ({ holds: () => state.allowed }) }));
vi.mock("../../../lib/api/queries/periods", () => ({
  locksKey: (id: string) => ["locks", id],
  fetchPeriodLocks: state.fetch,
}));
afterEach(() => {
  cleanup();
  state.fetch.mockReset();
  state.allowed = true;
});
const context = {
  entity: "US",
  book: "ASC606",
  periodKey: "2026-01",
  periods: [
    {
      id: "period-us",
      entity: { code: "US", id: "us" },
      book: "ASC606",
      period: { period_key: "2026-01" },
    },
  ],
} as unknown as ReportContext;
function open(value = "", ctx = context) {
  const change = vi.fn();
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <CloseLockParameter
        name="from_period_lock_id"
        context={ctx}
        value={value}
        error={undefined}
        disabled={false}
        onChange={change}
      />
    </QueryClientProvider>,
  );
  return change;
}
it("offers only freezing locks from the selected entity/book/period", async () => {
  const row = { created_at: "2026-02-01T12:00:00Z", created_by: { display_name: "Maya" } };
  state.fetch.mockResolvedValue([
    { ...row, id: "lock", kind: "LOCK", approval_request_no: "APR-01" },
    { ...row, id: "reopen", kind: "REOPEN", approval_request_no: "APR-02" },
    { ...row, id: "permanent", kind: "PERMANENT_LOCK", approval_request_no: "APR-03" },
  ]);
  const change = open();
  const input = screen.getByRole("combobox", { name: "Earlier close" });
  fireEvent.keyDown(input, { key: "ArrowDown" });
  const option = await screen.findByRole("option", { name: /APR-01/ });
  expect(screen.queryByRole("option", { name: /APR-02|APR-03/ })).toBeNull();
  fireEvent.mouseDown(option);
  expect(change).toHaveBeenCalledWith("lock");
  expect(state.fetch).toHaveBeenCalledWith("period-us");
});
it("keeps explicit references without reading another entity's history", () => {
  open("saved-lock", { ...context, entity: "OTHER" });
  expect((screen.getByRole("textbox", { name: "Earlier close" }) as HTMLInputElement).value).toBe(
    "saved-lock",
  );
  expect(state.fetch).not.toHaveBeenCalled();
});
