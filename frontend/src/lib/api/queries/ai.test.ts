// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import { createCommandKeys } from "../commands";
import {
  acceptExtraction,
  type ExtractionDraft,
  fetchDocumentText,
  fetchProposal,
  fetchProposals,
  rejectProposal,
  submitExtraction,
} from "./ai";

const ID = "00000000-0000-4000-8000-000000000001";
const BODY: ExtractionDraft = {
  command: "contract.create_draft",
  entity_code: "US",
  field_decisions: [
    { path: "customer_name", decision: "EDIT", value: "Reviewed name", reason: "Verified" },
  ],
  header_bindings: { customer_name: "customer" },
  line_bindings: {},
  draft: {
    external_id: "ORDER-1",
    consideration_payable: [],
    noncash_consideration: [],
    payment_schedule: [],
    has_commercial_substance: true,
    scope_605_35: false,
    submit_for_activation: false,
    customer: { code: "C1", name: "Reviewed name" },
    contracting_entity_code: "US",
    transaction_currency: "USD",
    inception_date: "2026-01-01",
    lines: [
      {
        obligation_key: "O1",
        scope_flag: "IN_SCOPE_606",
        product_code: "SUB",
        quantity: "1",
        total_price: { amount: "120.0000", currency: "USD" },
      },
    ],
  },
};
const json = (value: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(value), {
    headers: { "Content-Type": "application/json", ...headers },
  });

afterEach(() => vi.unstubAllGlobals());

describe("retained AI review API", () => {
  it("preserves evidence and server ETag without a settings request", async () => {
    const proposal = {
      kind: "CONTRACT_EXTRACTION",
      content: [{ path: "lines.0", value: { amount: "120.0000" } }],
      accepted_object_id: ID,
      field_decisions: BODY.field_decisions,
    };
    const fetch = vi.fn().mockResolvedValueOnce(json(proposal, { ETag: '"r7"' }));
    vi.stubGlobal("fetch", fetch);
    expect(await fetchProposal(ID)).toEqual({ proposal, etag: '"r7"' });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("keeps missing versions null and reads original text without interpretation", async () => {
    const pages = {
      proposal_id: ID,
      file_object_id: ID,
      pages: [{ page_no: 1, text: "<script>document text</script>" }],
    };
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(json({ id: ID }))
        .mockResolvedValueOnce(json(pages)),
    );
    expect((await fetchProposal(ID)).etag).toBeNull();
    expect(await fetchDocumentText(ID)).toEqual(pages);
  });

  it("propagates inaccessible-source reads without a fallback request", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          type: "https://erev.dev/problems/not-found",
          title: "Not found",
          status: 404,
          instance: "urn:erev:request:review-read",
        }),
        { status: 404, headers: { "Content-Type": "application/problem+json" } },
      ),
    );
    vi.stubGlobal("fetch", fetch);
    await expect(fetchDocumentText(ID)).rejects.toMatchObject({
      slug: "not-found",
      requestId: "review-read",
    });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("passes list filters and opaque cursors to authorized pagination", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        json({ items: [], next_cursor: "next" }, { "X-Erev-Total-Count": "0" }),
      );
    vi.stubGlobal("fetch", fetch);
    const page = await fetchProposals(
      { kind: "CONTRACT_EXTRACTION", status: "accepted" },
      "opaque+token",
    );
    const request = fetch.mock.calls[0]?.[0] as Request;
    const url = new URL(request.url);
    expect(url.searchParams.get("cursor")).toBe("opaque+token");
    expect(url.searchParams.get("status")).toBe("accepted");
    expect(page.nextCursor).toBe("next");
    expect(page.items).toEqual([]);
  });

  it("retains a lost-response acceptance key, exact reviewed values and If-Match", async () => {
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValueOnce(json({ contract_id: ID }));
    vi.stubGlobal("fetch", fetch);
    const keys = createCommandKeys();
    await expect(acceptExtraction(keys, ID, '"r1"', BODY)).rejects.toThrow("offline");
    const result = await acceptExtraction(keys, ID, '"r1"', BODY);
    expect(result.ok).toBe(true);
    const first = fetch.mock.calls[0]?.[0] as Request;
    const second = fetch.mock.calls[1]?.[0] as Request;
    expect(first.headers.get("Idempotency-Key")).toBeTruthy();
    expect(second.headers.get("Idempotency-Key")).toBe(first.headers.get("Idempotency-Key"));
    expect(second.headers.get("If-Match")).toBe('"r1"');
    expect(await second.json()).toEqual(BODY);
  });

  it("submits only the source ID and propagates review refusal without retry", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(json({ id: ID }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            type: "https://erev.dev/problems/precondition-failed",
            title: "Changed",
            status: 412,
          }),
          { status: 412, headers: { "Content-Type": "application/problem+json" } },
        ),
      );
    vi.stubGlobal("fetch", fetch);
    const keys = createCommandKeys();
    await submitExtraction(keys, ID);
    const sent = fetch.mock.calls[0]?.[0] as Request;
    expect(await sent.json()).toEqual({ file_id: ID });
    const rejected = await rejectProposal(keys, ID, '"r1"', "Incorrect customer");
    expect(rejected.ok).toBe(false);
    if (!rejected.ok) expect(rejected.problem.slug).toBe("precondition-failed");
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
