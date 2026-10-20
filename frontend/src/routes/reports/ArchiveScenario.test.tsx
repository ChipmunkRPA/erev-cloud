// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ArchiveScenario } from "./ArchiveScenario";
const state = vi.hoisted(() => ({ submit: vi.fn(), options: null as unknown }));
vi.mock("../../lib/api/commands", () => ({
  useCommand: (options: unknown) => {
    state.options = options;
    return { submit: state.submit, pending: false, problem: null, banner: null };
  },
}));
afterEach(() => {
  cleanup();
  state.submit.mockReset();
});
it("requires confirmation and sends the current row version without an invented body", async () => {
  state.submit.mockResolvedValue({ kind: "succeeded" });
  render(<ArchiveScenario id="scenario-1" name="Budget" version={7} />);
  fireEvent.click(screen.getByRole("button", { name: "Archive scenario" }));
  expect(state.submit).not.toHaveBeenCalled();
  expect(screen.getByText("Archive Budget?")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Confirm archive" }));
  await screen.findByText("Scenario archived.");
  expect(state.submit).toHaveBeenCalledWith(undefined, { ifMatch: '"r7"' });
  expect(state.options).toMatchObject({
    method: "POST",
    path: "/api/v1/scenarios/scenario-1/archive",
  });
});
it("keeps confirmation available after a lost response and cancels without sending", async () => {
  state.submit.mockResolvedValue({ kind: "network-error" });
  render(<ArchiveScenario id="scenario-1" name="Budget" version={7} />);
  fireEvent.click(screen.getByRole("button", { name: "Archive scenario" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm archive" }));
  await screen.findByText("Could not archive scenario");
  expect(screen.getByRole("button", { name: "Confirm archive" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(screen.queryByText("Archive Budget?")).toBeNull());
  expect(state.submit).toHaveBeenCalledTimes(1);
});
