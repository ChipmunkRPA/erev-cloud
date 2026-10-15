// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { submitExtraction } from "../../lib/api/queries/ai";
import { uploadFile } from "../../lib/api/queries/ssp-books";
import { NewContractReview } from "./review-new";

const state = vi.hoisted(() => ({
  allowed: true,
  enabled: true,
  job: {} as Record<string, unknown>,
}));
vi.mock("../../lib/access", () => ({ useAccess: () => ({ holdsAnywhere: () => state.allowed }) }));
vi.mock("../../lib/api/queries/me", () => ({
  useMe: () => ({
    isPending: false,
    data: { user: { id: "reviewer" }, tenant_settings: { ai_enabled: state.enabled } },
  }),
}));
vi.mock("../../lib/api/jobs", async (original) => ({
  ...(await original<typeof import("../../lib/api/jobs")>()),
  useJob: (id: string | null) => ({
    data: id === null ? undefined : state.job,
    isError: false,
    refetch: vi.fn(),
  }),
}));
vi.mock("../../lib/api/queries/ai", async (original) => ({
  ...(await original<typeof import("../../lib/api/queries/ai")>()),
  submitExtraction: vi.fn(),
}));
vi.mock("../../lib/api/queries/ssp-books", () => ({ uploadFile: vi.fn() }));
const ID = "00000000-0000-4000-8000-000000000001";
const PROPOSAL = "00000000-0000-4000-8000-000000000002";
function show(search = "") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/contracts/review/new${search}`]}>
        <Routes>
          <Route path="/contracts/review/new" element={<NewContractReview />} />
          <Route path={`/contracts/review/${PROPOSAL}`} element={<h1>Retained review</h1>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
function choose(name = "contract.pdf", type = "application/pdf") {
  fireEvent.change(screen.getByLabelText("Choose file"), {
    target: { files: [new File(["%PDF fixture"], name, { type })] },
  });
}
beforeEach(() => {
  state.allowed = true;
  state.enabled = true;
  state.job = {
    id: ID,
    kind: "AI_TASK",
    state: "SUCCEEDED",
    result: { proposal_id: PROPOSAL },
    created_by: { id: "reviewer" },
  };
  vi.mocked(uploadFile).mockResolvedValue({ id: ID } as Awaited<ReturnType<typeof uploadFile>>);
  vi.mocked(submitExtraction).mockResolvedValue({
    ok: true,
    data: { id: ID, kind: "AI_TASK" },
    response: new Response(),
  } as Awaited<ReturnType<typeof submitExtraction>>);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("SF-20 document upload", () => {
  it("uploads a source attachment and navigates from the completed job", async () => {
    show();
    choose();
    fireEvent.click(screen.getByRole("button", { name: "Start review" }));
    expect(await screen.findByRole("heading", { name: "Retained review" })).toBeTruthy();
    expect(uploadFile).toHaveBeenCalledTimes(1);
    expect(vi.mocked(uploadFile).mock.calls[0]?.[1]).toBe("ATTACHMENT");
    expect(vi.mocked(submitExtraction).mock.calls[0]?.[1]).toBe(ID);
  });
  it("retains the successful upload and command keys after a lost submission response", async () => {
    vi.mocked(submitExtraction).mockRejectedValueOnce(new TypeError("offline"));
    show();
    choose();
    fireEvent.click(screen.getByRole("button", { name: "Start review" }));
    expect(
      await screen.findByText("No response received. Try again to confirm the result."),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Start review" }));
    expect(await screen.findByRole("heading", { name: "Retained review" })).toBeTruthy();
    expect(uploadFile).toHaveBeenCalledTimes(1);
    expect(vi.mocked(submitExtraction).mock.calls[0]?.[0]).toBe(
      vi.mocked(submitExtraction).mock.calls[1]?.[0],
    );
  });
  it("rejects absent or unsupported files before any upload", () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: "Start review" }));
    expect(screen.getByText("Choose a contract document.")).toBeTruthy();
    choose(
      "contract.docx",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    );
    fireEvent.click(screen.getByRole("button", { name: "Start review" }));
    expect(uploadFile).not.toHaveBeenCalled();
    expect(submitExtraction).not.toHaveBeenCalled();
  });
  it("does not offer upload without permission or while AI is off", () => {
    state.enabled = false;
    show();
    expect(screen.getByText("AI assistance is turned off for this workspace")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Choose file" })).toBeNull();
    expect(uploadFile).not.toHaveBeenCalled();
  });
  it("withholds source upload from a user without AI permission", () => {
    state.allowed = false;
    show();
    expect(screen.getByText("You do not have access to Review a contract document")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Choose file" })).toBeNull();
    expect(uploadFile).not.toHaveBeenCalled();
  });

  it("resumes a retained successful job after AI is disabled", async () => {
    state.enabled = false;
    show(`?job=${ID}`);
    expect(await screen.findByRole("heading", { name: "Retained review" })).toBeTruthy();
    expect(uploadFile).not.toHaveBeenCalled();
    expect(submitExtraction).not.toHaveBeenCalled();
  });
  it("never navigates from an unrelated job or malformed proposal result", () => {
    state.job = { ...state.job, kind: "IMPORT", result: { proposal_id: "https://example.test" } };
    show(`?job=${ID}`);
    expect(screen.getByRole("button", { name: "Start another review" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Retained review" })).toBeNull();
  });
  it("offers cancellation only on the initiator's active extraction job", async () => {
    state.job = { ...state.job, state: "RUNNING", result: null };
    const fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ...state.job, state: "CANCELLED" }), {
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetch);
    show(`?job=${ID}`);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    const request = fetch.mock.calls[0]?.[0] as Request;
    expect(new URL(request.url).pathname).toBe(`/api/v1/jobs/${ID}/cancel`);
    expect(request.headers.get("Idempotency-Key")).toBeTruthy();
  });
});
