import { describe, expect, it } from "vitest";
import type { ExtractionProposal } from "../../lib/api/queries/ai";
import { fieldChoice, prepareReview } from "./review-decisions";
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

describe("extraction field decisions", () => {
  it("requires explicit low-confidence and uncited decisions", () => {
    expect(fieldChoice({ confidence: "0.74", value: "Name" }, true).decision).toBeNull();
    expect(fieldChoice({ confidence: "0.95", value: "Name" }, false).decision).toBeNull();
    expect(fieldChoice({ confidence: "0.75", value: "Name" }, true).decision).toBe("ACCEPT");
    expect(
      prepareReview(proposal, [fieldChoice(proposal.content[0] ?? {}, true)], null),
    ).toMatchObject({ ok: false, error: "incomplete" });
  });
  it("preserves decimal strings and requires explicit date meaning without inventing inputs", () => {
    const fields = [
      {
        path: "lines.7",
        value: { product_code: "PRODUCT", amount: "9007199254740993.1200" },
        confidence: "0.9",
      },
      { path: "effective_date", value: "2026-10-01", confidence: "0.9" },
      { path: "customer_name", value: "Customer", confidence: "0.9" },
    ];
    const choices = fields.map((field) => fieldChoice(field, true));
    expect(prepareReview({ ...proposal, content: fields }, choices, null)).toMatchObject({
      ok: false,
      error: "dateTarget",
    });
    const result = prepareReview({ ...proposal, content: fields }, choices, "signature_date");
    expect(result.ok).toBe(true);
    if (!result.ok) throw new Error("Expected prepared review");
    expect(result.review.lines).toEqual({ "lines.7": "O1" });
    expect(result.review.initial).toMatchObject({
      currency: null,
      entity: null,
      customerCode: "",
      inceptionDate: "",
      signatureDate: "2026-10-01",
    });
    expect(result.review.initial.lines[0]).toMatchObject({
      quantity: "",
      totalPrice: "9007199254740993.1200",
      productCode: "PRODUCT",
    });
    expect(result.review.decisions).toEqual(
      fields.map(({ path }) => ({ path, decision: "ACCEPT" })),
    );
  });
  it("requires reasons and omits rejected terms without interpreting them", () => {
    const fields = [
      { path: "payment_terms", value: "Net 30", confidence: "0.9" },
      { path: "variable_consideration_terms", value: "Bonus", confidence: "0.9" },
    ];
    const choices = fields.map((field) => fieldChoice(field, true));
    expect(prepareReview({ ...proposal, content: fields }, choices, null)).toMatchObject({
      ok: false,
      error: "unsupported",
    });
    choices[1] = { ...fieldChoice(fields[1] ?? {}, true), decision: "REJECT", reason: "short" };
    expect(prepareReview({ ...proposal, content: fields }, choices, null)).toMatchObject({
      ok: false,
      error: "reason",
    });
    choices[1] = { ...choices[1], reason: "Requires separate accounting review" };
    const result = prepareReview({ ...proposal, content: fields }, choices, null);
    expect(result.ok).toBe(true);
    if (!result.ok) throw new Error("Expected prepared review");
    expect(result.review.headers).toEqual({ payment_terms: "payment_terms" });
    expect(result.review.decisions[1]).toEqual({
      path: "variable_consideration_terms",
      decision: "REJECT",
      reason: "Requires separate accounting review",
    });
  });
  it("records edited strings separately and refuses an entirely rejected proposal", () => {
    const choice = {
      ...fieldChoice(proposal.content[0] ?? {}, true),
      decision: "EDIT" as const,
      value: "Corrected customer",
      reason: "Verified against original signed document",
    };
    const result = prepareReview(proposal, [choice], null);
    expect(result.ok).toBe(true);
    if (!result.ok) throw new Error("Expected prepared review");
    expect(result.review.decisions[0]).toMatchObject({
      decision: "EDIT",
      value: "Corrected customer",
    });
    expect(proposal.content[0]?.value).toBe("Original customer");
    expect(prepareReview(proposal, [{ ...choice, decision: "REJECT" }], null)).toMatchObject({
      ok: false,
      error: "empty",
    });
  });
});
