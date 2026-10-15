// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { fetchProposal, proposalKey, type AIProposal } from "../../lib/api/queries/ai";
import { RetainedNarrative } from "./RetainedNarrative";
const access = vi.hoisted(() => ({ allowed: true }));
vi.mock("../../lib/access", () => ({ useAccess: () => ({ holdsAnywhere: () => access.allowed }) }));
vi.mock("../../lib/api/queries/ai", async (original) => ({
  ...(await original<typeof import("../../lib/api/queries/ai")>()),
  fetchProposal: vi.fn(),
}));
const traceId = "00000000-0000-4000-8000-000000000001";
const proposalId = "00000000-0000-4000-8000-000000000002";
const actor = { id: proposalId, kind: "USER" as const, display_name: "Maya" };
const proposal: AIProposal = {
  id: proposalId,
  kind: "NUMBER_EXPLANATION",
  subject_type: "calc_trace",
  subject_id: traceId,
  status: "proposed",
  content: { narrative: ["<script>unsafe()</script>"] },
  citations: [
    { ref_type: "record", ref_id: traceId, node_id: "n1" },
    { ref_type: "record", ref_id: "other", node_id: "hidden" },
  ],
  ai_model_log_id: proposalId,
  job_id: null,
  expires_at: "2026-10-31T00:00:00Z",
  problem: null,
  created_at: "2026-10-15T00:00:00Z",
  updated_at: "2026-10-15T00:00:00Z",
  created_by: actor,
  updated_by: actor,
  row_version: 1,
  rejected_by: null,
  rejected_at: null,
  rejection_reason: null,
};
afterEach(cleanup);
beforeEach(() => {
  access.allowed = true;
  vi.mocked(fetchProposal).mockReset();
  vi.mocked(fetchProposal).mockResolvedValue({ proposal, etag: '"1"' });
});
function show(cached = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (cached) client.setQueryData(proposalKey(proposalId), { proposal, etag: '"1"' });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <RetainedNarrative traceId={traceId} proposalId={proposalId} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

it("renders text safely and links only citations of the bound trace", async () => {
  show();
  expect(await screen.findByText("<script>unsafe()</script>")).toBeTruthy();
  expect(document.querySelector("script")).toBeNull();
  expect(screen.getByRole("link", { name: "Trace node n1" }).getAttribute("href")).toBe(
    `/trace/${traceId}?proposal=${proposalId}&node=n1`,
  );
  expect(screen.queryByRole("link", { name: /hidden/ })).toBeNull();
  expect(fetchProposal).toHaveBeenCalledWith(proposalId);
});
it("refuses a proposal bound to a different trace", async () => {
  vi.mocked(fetchProposal).mockResolvedValue({
    proposal: { ...proposal, subject_id: "other" },
    etag: null,
  });
  show();
  expect(
    await screen.findByText("This proposed explanation is not available for this trace."),
  ).toBeTruthy();
  expect(screen.queryByText("<script>unsafe()</script>")).toBeNull();
});
it("does not fetch without AI permission", async () => {
  access.allowed = false;
  show();
  expect(
    screen.getByText("This proposed explanation is not available for this trace."),
  ).toBeTruthy();
  expect(fetchProposal).not.toHaveBeenCalled();
});
it("does not show cached content when the fresh read is refused", async () => {
  vi.mocked(fetchProposal).mockRejectedValue(new Error("Not found"));
  show(true);
  expect(screen.queryByText("<script>unsafe()</script>")).toBeNull();
  expect(
    await screen.findByText("This proposed explanation is not available for this trace."),
  ).toBeTruthy();
  expect(screen.queryByText("<script>unsafe()</script>")).toBeNull();
});
it("does not render narrative content for a failed proposal", async () => {
  vi.mocked(fetchProposal).mockResolvedValue({
    proposal: { ...proposal, status: "failed" },
    etag: null,
  });
  show();
  expect(
    await screen.findByText(
      "No proposed narrative was retained. The calculation trace remains authoritative.",
    ),
  ).toBeTruthy();
  expect(screen.queryByText("<script>unsafe()</script>")).toBeNull();
});
