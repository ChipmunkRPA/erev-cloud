// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { SaveDealPreview } from "./SaveDealPreview";
const state = vi.hoisted(() => ({ submit: vi.fn() }));
vi.mock("../../lib/api/commands", () => ({
  useCommand: () => ({ submit: state.submit, pending: false, problem: null }),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
function page(allowed = true, saved: string | null = null) {
  const busy = vi.fn();
  render(
    <MemoryRouter>
      <SaveDealPreview
        preview={{ id: "preview", saved_contract_id: saved, save_allowed: allowed }}
        onBusy={busy}
      />
    </MemoryRouter>,
  );
  return busy;
}
it("does not offer saving when the server refuses eligibility, and links already saved drafts", () => {
  page(false);
  expect(screen.queryByRole("button")).toBeNull();
  cleanup();
  page(false, "draft");
  expect(screen.getByRole("link", { name: "Open draft contract" }).getAttribute("href")).toBe(
    "/contracts/draft/obligations",
  );
});
it("retains the external ID through network failure and links the recovered draft", async () => {
  state.submit
    .mockResolvedValueOnce({ kind: "network-error" })
    .mockResolvedValueOnce({ kind: "succeeded", data: { id: "draft" } });
  const busy = page();
  fireEvent.change(screen.getByLabelText("Contract external ID"), {
    target: { value: " DEAL-1 " },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save as scenario draft" }));
  await screen.findByText(/Could not confirm the save/);
  expect((screen.getByLabelText("Contract external ID") as HTMLInputElement).value).toBe(
    " DEAL-1 ",
  );
  fireEvent.click(screen.getByRole("button", { name: "Save as scenario draft" }));
  await screen.findByRole("link", { name: "Open draft contract" });
  expect(state.submit).toHaveBeenNthCalledWith(1, { contract_external_id: "DEAL-1" });
  expect(state.submit).toHaveBeenNthCalledWith(2, { contract_external_id: "DEAL-1" });
  await waitFor(() => expect(busy).toHaveBeenLastCalledWith(false));
  expect(screen.queryByRole("button")).toBeNull();
});
