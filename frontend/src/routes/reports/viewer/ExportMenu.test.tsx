// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { Job } from "../../../lib/api/jobs";
import type { ReportDefinition } from "../../../lib/api/queries/reports";
import { ExportMenu } from "./ExportMenu";

const state = vi.hoisted(() => ({
  submit: vi.fn(),
  fetch: vi.fn(),
  toast: { show: vi.fn() },
  pending: false,
  job: undefined as Job | undefined,
}));
vi.mock("../../../lib/api/commands", () => ({ useCommand: () => state }));
vi.mock("../../../components/feedback/Toast", () => ({ useToast: () => state.toast }));
vi.mock("../../../components/feedback/JobProgress", () => ({ JobProgress: () => null }));
vi.mock("../../../components/ui/Menu", () => ({
  Menu: ({ items }: { items: { id: string; onSelect: () => void; disabledReason?: string }[] }) => (
    <div>
      {items.map((item) => (
        <button key={item.id} disabled={!!item.disabledReason} onClick={item.onSelect}>
          {item.id}
        </button>
      ))}
    </div>
  ),
}));
vi.mock("../../../lib/api/queries/reports", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../lib/api/queries/reports")>()),
  fetchReportRun: (id: string) => state.fetch(id),
}));
const definition = {
  code: "rpo",
  name: "RPO",
  output_formats: ["CSV", "XLSX"],
} as ReportDefinition;
const props = { definition, parameters: {}, onDetails: vi.fn() };
function accepted() {
  return {
    kind: "accepted",
    response: new Response(null, { headers: { "X-Erev-Report-Run-Id": "saved-report" } }),
  };
}
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  state.job = undefined;
  state.pending = false;
});

it("prevents duplicate submission before the request resolves and while a job is running", async () => {
  let finish!: (value: unknown) => void;
  state.submit.mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const view = render(<ExportMenu {...props} />);
  fireEvent.click(screen.getByText("CSV"));
  fireEvent.click(screen.getByText("XLSX"));
  expect(state.submit).toHaveBeenCalledTimes(1);
  await act(async () => {
    finish(accepted());
  });
  fireEvent.click(screen.getByText("XLSX"));
  expect(state.submit).toHaveBeenCalledTimes(1);
  state.job = { id: "job", state: "RUNNING" } as Job;
  view.rerender(<ExportMenu {...props} />);
  expect((screen.getByText("CSV") as HTMLButtonElement).disabled).toBe(true);
});

it("retries download preparation against the completed report without submitting another export", async () => {
  state.submit.mockResolvedValue(accepted());
  state.fetch.mockRejectedValue(new Error("temporarily unavailable"));
  const view = render(<ExportMenu {...props} />);
  await act(async () => {
    fireEvent.click(screen.getByText("CSV"));
  });
  state.job = { id: "job", state: "SUCCEEDED" } as Job;
  view.rerender(<ExportMenu {...props} />);
  await waitFor(() =>
    expect(state.toast.show).toHaveBeenCalledWith(
      expect.objectContaining({ tone: "negative", action: expect.any(Object) }),
    ),
  );
  const failure = state.toast.show.mock.calls.at(-1)?.[0];
  await act(async () => {
    failure.action.onAction();
  });
  expect(state.fetch).toHaveBeenCalledTimes(2);
  expect(state.fetch).toHaveBeenLastCalledWith("saved-report");
  expect(state.submit).toHaveBeenCalledTimes(1);
  expect(state.toast.show.mock.calls.some(([toast]) => toast.tone === "positive")).toBe(false);
});

it("shows a lost-response message instead of silently ignoring a network error", async () => {
  state.submit.mockResolvedValue({ kind: "network-error" });
  render(<ExportMenu {...props} />);
  await act(async () => {
    fireEvent.click(screen.getByText("CSV"));
  });
  expect(state.toast.show).toHaveBeenCalledWith(expect.objectContaining({ tone: "negative" }));
});
