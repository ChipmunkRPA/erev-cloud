// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { RefreshScenario } from "./RefreshScenario";
const state = vi.hoisted(() => ({
  fetch: vi.fn(),
  submit: vi.fn(),
  status: "",
  jobId: "job-old",
  finished: false,
}));
vi.mock("../../lib/api/lists", () => ({ fetchListPage: state.fetch }));
vi.mock("../../lib/api/jobs", () => ({
  useJob: (id: string | null) => ({
    data:
      state.finished && id === "new-job"
        ? { id, state: "SUCCEEDED", finished_at: "2026-10-18T23:00:00Z" }
        : undefined,
  }),
  isTerminal: (job: { state: string } | undefined) => job?.state === "SUCCEEDED",
}));
vi.mock("../../components/feedback/JobProgress", () => ({ JobProgress: () => null }));
vi.mock("../../lib/api/commands", () => ({
  useCommand: () => ({ submit: state.submit, pending: false, problem: null, banner: null }),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  state.status = "";
  state.jobId = "job-old";
  state.finished = false;
});
function open() {
  state.fetch.mockImplementation((path: string) =>
    Promise.resolve({
      items: path.endsWith("/refreshes")
        ? state.status
          ? [
              {
                id: "refresh",
                job_id: state.jobId,
                status: state.status,
                created_at: "2026-10-19T00:00:00Z",
                started_at: null,
                finished_at: null,
              },
            ]
          : []
        : [{ id: "input", code: "BUDGET", name: "Budget", version_no: 2 }],
      nextCursor: null,
      total: null,
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RefreshScenario id="scenario" version={7} />
    </QueryClientProvider>,
  );
  return client;
}
it("loads choices only when opened and keeps an accepted refresh blocked until its durable outcome", async () => {
  const client = open();
  expect(state.fetch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Refresh scenario" }));
  await waitFor(() => expect(state.fetch).toHaveBeenCalledTimes(2));
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "Budget" } });
  fireEvent.mouseDown(await screen.findByRole("option", { name: "BUDGET — Budget (v2)" }));
  state.submit.mockResolvedValue({ kind: "accepted", jobId: "new-job" });
  fireEvent.click(screen.getByRole("button", { name: "Refresh with selected assumptions" }));
  await waitFor(() =>
    expect(state.submit).toHaveBeenCalledWith(
      { forecast_event_set_id: "input" },
      { ifMatch: '"r7"' },
    ),
  );
  expect(
    await screen.findByText("Waiting for the complete refresh outcome…", { selector: "p" }),
  ).toBeTruthy();
  expect(screen.queryByText(/Refresh completed/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Refresh with selected assumptions" }));
  expect(state.submit).toHaveBeenCalledTimes(1);
  state.jobId = "new-job";
  state.status = "SUCCEEDED";
  await client.invalidateQueries({ queryKey: ["scenario-refreshes"] });
  expect(await screen.findByText(/Refresh completed/)).toBeTruthy();
  state.jobId = "later-job";
  state.status = "RUNNING";
  await client.invalidateQueries({ queryKey: ["scenario-refreshes"] });
  expect(await screen.findByText(/Refresh in progress/)).toBeTruthy();
  expect(
    screen.queryByText("Waiting for the complete refresh outcome…", { selector: "p" }),
  ).toBeNull();
  state.status = "SUCCEEDED";
  await client.invalidateQueries({ queryKey: ["scenario-refreshes"] });
  expect(await screen.findByText(/Refresh completed/)).toBeTruthy();
  await waitFor(() =>
    expect(
      screen
        .getByRole("button", { name: "Refresh with selected assumptions" })
        .getAttribute("aria-disabled"),
    ).not.toBe("true"),
  );
});
it("recovers an in-flight refresh after reopening without requesting a second copy", async () => {
  state.status = "RUNNING";
  open();
  fireEvent.click(screen.getByRole("button", { name: "Refresh scenario" }));
  expect(await screen.findByText(/Refresh in progress/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Refresh with selected assumptions" }));
  expect(state.submit).not.toHaveBeenCalled();
});

it("follows a newer durable refresh when the accepted terminal outcome was skipped between polls", async () => {
  open();
  fireEvent.click(screen.getByRole("button", { name: "Refresh scenario" }));
  await waitFor(() => expect(state.fetch).toHaveBeenCalledTimes(2));
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "Budget" } });
  fireEvent.mouseDown(await screen.findByRole("option", { name: "BUDGET — Budget (v2)" }));
  state.submit.mockImplementation(async () => {
    state.finished = true;
    state.jobId = "newer-job";
    state.status = "RUNNING";
    return { kind: "accepted", jobId: "new-job" };
  });
  fireEvent.click(screen.getByRole("button", { name: "Refresh with selected assumptions" }));
  expect(await screen.findByText(/Refresh in progress/)).toBeTruthy();
  await waitFor(() =>
    expect(
      screen.queryByText("Waiting for the complete refresh outcome…", { selector: "p" }),
    ).toBeNull(),
  );
});
