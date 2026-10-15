// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  fetchDocumentText,
  fetchProposal,
  type ExtractionProposal,
} from "../../lib/api/queries/ai";
import type { DraftForm } from "../../lib/forms/contract";
import { citedParts, ContractReview } from "./review";

const access = vi.hoisted(() => ({ allowed: true }));
vi.mock("../../lib/access", () => ({ useAccess: () => ({ holdsAnywhere: () => access.allowed }) }));
vi.mock("../../lib/api/queries/ai", async (original) => ({
  ...(await original<typeof import("../../lib/api/queries/ai")>()),
  fetchProposal: vi.fn(),
  fetchDocumentText: vi.fn(),
}));
vi.mock("./draft-form", () => ({
  ReviewedContractDraft: ({
    initial,
    onReview,
  }: {
    initial: DraftForm;
    onReview: (form: DraftForm) => void;
  }) => (
    <div>
      <p>Draft reference: {initial.externalId}</p>
      <p>Draft customer: {initial.customer?.kind === "new" ? initial.customer.name : ""}</p>
      <button onClick={() => onReview({ ...initial, externalId: "HUMAN-REFERENCE" })}>
        Back to field review
      </button>
    </div>
  ),
}));
const ID = "00000000-0000-4000-8000-000000000001";
const actor = { id: ID, display_name: "Reviewer", kind: "USER" as const };
const proposal: ExtractionProposal = {
  id: ID,
  kind: "CONTRACT_EXTRACTION",
  status: "proposed",
  row_version: 1,
  file_object_id: ID,
  document_text_file_id: ID,
  ai_model_log_id: ID,
  job_id: null,
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
  expires_at: "2099-10-01T00:00:00Z",
  created_by: actor,
  updated_by: actor,
  rejected_by: null,
  rejected_at: null,
  rejection_reason: null,
  problem: null,
  accepted_by: null,
  accepted_at: null,
  accepted_command: null,
  accepted_object_type: null,
  accepted_object_id: null,
  field_decisions: null,
  citations: [],
  content: [
    {
      path: "customer_name",
      value: "Original customer",
      confidence: "0.72",
      check: true,
      citation: { ref_type: "document", ref_id: ID, page: 1, char_start: 2, char_end: 10 },
    },
  ],
};
const text = {
  proposal_id: ID,
  file_object_id: ID,
  pages: [{ page_no: 1, text: "\u{1F600} Customer <script>unsafe()</script>" }],
};
function show() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/contracts/review/${ID}`]}>
        <Routes>
          <Route path="/contracts/review/:proposalId" element={<ContractReview />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}
beforeEach(() => {
  access.allowed = true;
  vi.mocked(fetchProposal).mockResolvedValue({ proposal, etag: '"r1"' });
  vi.mocked(fetchDocumentText).mockResolvedValue(text);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("SF-20 retained review", () => {
  it("keeps edits across responsive panes and returns citation focus after resize", async () => {
    const media = new EventTarget();
    let wide = false;
    vi.stubGlobal("matchMedia", () => ({
      get matches() {
        return wide;
      },
      addEventListener: media.addEventListener.bind(media),
      removeEventListener: media.removeEventListener.bind(media),
    }));
    show();
    const fields = await screen.findByRole("tab", { name: "Proposed fields" });
    const documentTab = screen.getByRole("tab", { name: "Document" });
    documentTab.focus();
    fireEvent.keyDown(documentTab, { key: "ArrowRight" });
    expect(document.activeElement).toBe(fields);
    fireEvent.click(screen.getByRole("radio", { name: "Edit" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Edited value for Customer" }), {
      target: { value: "Reviewed customer" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Reason for Customer" }), {
      target: { value: "Confirmed against signed source" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Page 1, characters 2–10" }));
    expect(screen.getByRole("tab", { name: "Document" }).getAttribute("aria-selected")).toBe(
      "true",
    );
    expect(document.activeElement?.tagName).toBe("MARK");
    expect(screen.queryByRole("textbox", { name: "Edited value for Customer" })).toBeNull();
    act(() => {
      wide = true;
      media.dispatchEvent(new Event("change"));
    });
    expect(screen.queryByRole("tab")).toBeNull();
    expect(
      (screen.getByRole("textbox", { name: "Edited value for Customer" }) as HTMLInputElement)
        .value,
    ).toBe("Reviewed customer");
    act(() => {
      wide = false;
      media.dispatchEvent(new Event("change"));
    });
    const mark = document.querySelector("mark");
    if (mark === null) throw new Error("Missing source highlight");
    mark.focus();
    fireEvent.keyDown(mark, { key: "Escape" });
    expect(screen.getByRole("tab", { name: "Proposed fields" }).getAttribute("aria-selected")).toBe(
      "true",
    );
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Page 1, characters 2–10" }),
    );
    expect(
      (screen.getByRole("textbox", { name: "Edited value for Customer" }) as HTMLInputElement)
        .value,
    ).toBe("Reviewed customer");
    expect(
      (screen.getByRole("textbox", { name: "Reason for Customer" }) as HTMLTextAreaElement).value,
    ).toBe("Confirmed against signed source");
  });

  it("requires low-confidence decisions and reasons before leaving source review", async () => {
    show();
    const accept = await screen.findByRole("radio", { name: "Accept" });
    expect((accept as HTMLInputElement).checked).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Continue to draft" }));
    expect(await screen.findByText("Choose a decision for Customer.")).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue to draft" }));
    expect(await screen.findByText(/10.*4,?000/)).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "Edited value for Customer" })).toBeTruthy();
  });

  it("returns to field choices and preserves human draft inputs on continuation", async () => {
    show();
    fireEvent.click(await screen.findByRole("radio", { name: "Accept" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue to draft" }));
    expect(await screen.findByText("Draft customer: Original customer")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Back to field review" }));
    expect((screen.getByRole("radio", { name: "Accept" }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole("radio", { name: "Edit" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Edited value for Customer" }), {
      target: { value: "Corrected customer" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "Reason for Customer" }), {
      target: { value: "Verified against the signed document" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue to draft" }));
    expect(await screen.findByText("Draft reference: HUMAN-REFERENCE")).toBeTruthy();
    expect(screen.getByText("Draft customer: Corrected customer")).toBeTruthy();
  });

  it("highlights Python character offsets, focuses the citation and returns on Escape", async () => {
    show();
    const citation = await screen.findByRole("button", { name: "Page 1, characters 2–10" });
    fireEvent.click(citation);
    const mark = screen.getByLabelText("Cited text for Customer");
    expect(mark.textContent).toBe("Customer");
    expect(document.activeElement).toBe(mark);
    fireEvent.keyDown(mark, { key: "Escape" });
    expect(document.activeElement).toBe(citation);
    expect(document.querySelector("script")).toBeNull();
    expect(screen.getByText("Check", { exact: false })).toBeTruthy();
  });

  it("does not fetch evidence without permission", () => {
    access.allowed = false;
    show();
    expect(screen.getByText("You do not have access to Contract review")).toBeTruthy();
    expect(fetchProposal).not.toHaveBeenCalled();
    expect(fetchDocumentText).not.toHaveBeenCalled();
  });

  it("shows original and edited values separately and links the accepted draft", async () => {
    vi.mocked(fetchProposal).mockResolvedValue({
      proposal: {
        ...proposal,
        status: "accepted",
        accepted_by: actor,
        accepted_at: "2026-10-02T00:00:00Z",
        accepted_object_type: "contract",
        accepted_object_id: ID,
        accepted_command: "contract.create_draft",
        field_decisions: [
          {
            path: "customer_name",
            decision: "EDIT",
            value: "Reviewed customer",
            reason: "Correct account.",
          },
        ],
      },
      etag: '"r2"',
    });
    show();
    expect(await screen.findByText("Original customer")).toBeTruthy();
    expect(screen.getByText("Reviewed customer")).toBeTruthy();
    expect(screen.getByText("Accepted by Reviewer")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open draft contract" }).getAttribute("href")).toBe(
      `/contracts/${ID}/obligations`,
    );
    expect(screen.queryByRole("button", { name: "Reject proposal" })).toBeNull();
  });

  it("requires a reason and sends rejection with the read ETag", async () => {
    const fetch = vi.fn().mockImplementation(async () => {
      const rejected = {
        ...proposal,
        status: "rejected" as const,
        rejected_by: actor,
        rejection_reason: "Wrong customer record.",
      };
      vi.mocked(fetchProposal).mockResolvedValue({ proposal: rejected, etag: '"r2"' });
      return new Response(JSON.stringify(rejected), {
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetch);
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Reject proposal" }));
    const confirm = within(screen.getByRole("alertdialog")).getByRole("button", {
      name: "Reject proposal",
    });
    fireEvent.click(confirm);
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Reason for rejection"), {
      target: { value: "Wrong customer record." },
    });
    fireEvent.click(confirm);
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    const request = fetch.mock.calls[0]?.[0] as Request;
    expect(request.headers.get("If-Match")).toBe('"r1"');
    expect(await request.json()).toEqual({ reason: "Wrong customer record." });
    expect(await screen.findByText("Dismissed by Reviewer: Wrong customer record.")).toBeTruthy();
  });

  it("does not offer commands on expired evidence or missing server ETags", async () => {
    vi.mocked(fetchProposal).mockResolvedValue({
      proposal: { ...proposal, expires_at: "2020-01-01T00:00:00Z" },
      etag: null,
    });
    show();
    expect(await screen.findByText(/This proposal expired/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Reject proposal" })).toBeNull();
  });

  it("withholds rejection when a proposed record has no server ETag", async () => {
    vi.mocked(fetchProposal).mockResolvedValue({ proposal, etag: null });
    show();
    expect(await screen.findByText("Original customer")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Reject proposal" })).toBeNull();
  });

  it("keeps unavailable document text out of the view and offers a retry", async () => {
    vi.mocked(fetchDocumentText).mockRejectedValue(new Error("unavailable"));
    show();
    expect(await screen.findByText("Document text could not be read")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Page 1, characters 2–10" })).toBeNull();
    expect(screen.getByRole("button", { name: "Reload" })).toBeTruthy();
  });

  it("does not highlight out-of-range spans", () => {
    expect(citedParts("\u{1F600} customer", 2, 10)).toEqual(["\u{1F600} ", "customer", ""]);
    expect(citedParts("abc", -1, 2)).toBeNull();
    expect(citedParts("abc", 0, 4)).toBeNull();
    expect(citedParts("abc", 0.5, 2)).toBeNull();
  });
});
