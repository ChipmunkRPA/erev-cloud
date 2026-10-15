import { describe, expect, it } from "vitest";
import type { ExtractionProposal } from "../../lib/api/queries/ai";
import { fieldChoice, prepareReview, resumeDraft } from "./review-decisions";
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

describe("returning to field review", () => {
  const fields = [
    { path: "payment_terms", value: "Net 30", confidence: "0.9" },
    { path: "lines.0", value: { product_code: "A", amount: "100.00" }, confidence: "0.9" },
    { path: "lines.1", value: { product_code: "B", amount: "200.00" }, confidence: "0.9" },
  ];
  function prepared(choices = fields.map((field) => fieldChoice(field, true))) {
    const result = prepareReview({ ...proposal, content: fields }, choices, null);
    if (!result.ok) throw new Error("Expected prepared review");
    return result.review;
  }
  it("preserves human inputs and rebinds renamed rows across an unchanged review", () => {
    const previous = prepared();
    const current = {
      ...previous.initial,
      externalId: "HUMAN-1",
      entity: "US",
      currency: "USD",
      paymentTerms: "Human correction",
      lines: previous.initial.lines.map((line) => ({
        ...line,
        obligationKey: `H-${line.obligationKey}`,
        quantity: "12",
        startDate: "2026-10-01",
      })),
    };
    const next = resumeDraft(previous, current, prepared());
    expect(next.initial).toEqual(current);
    expect(next.lines).toEqual({ "lines.0": "H-O1", "lines.1": "H-O2" });
  });
  it("applies changed reviewed values, removes rejected rows and keeps quantities and human rows", () => {
    const previous = prepared();
    const current = {
      ...previous.initial,
      externalId: "HUMAN-1",
      lines: previous.initial.lines.map((line) => ({ ...line, quantity: "12" })),
    };
    const first = current.lines[0];
    if (first === undefined) throw new Error("Missing fixture row");
    current.lines.push({ ...first, id: "l3", obligationKey: "O3", productCode: "HUMAN" });
    const choices = fields.map((field) => fieldChoice(field, true));
    choices[0] = {
      ...fieldChoice(fields[0] ?? {}, true),
      decision: "REJECT",
      reason: "Not an agreed payment term",
    };
    choices[1] = {
      ...fieldChoice(fields[1] ?? {}, true),
      decision: "REJECT",
      reason: "Duplicated source line item",
    };
    choices[2] = {
      ...fieldChoice(fields[2] ?? {}, true),
      decision: "EDIT",
      product: "CORRECTED",
      value: "150.25",
      reason: "Verified amount against signed source",
    };
    const result = resumeDraft(previous, current, prepared(choices));
    expect(result.initial.externalId).toBe("HUMAN-1");
    expect(result.initial.paymentTerms).toBe("");
    expect(result.initial.lines).toHaveLength(2);
    expect(result.initial.lines[0]).toMatchObject({
      id: "l2",
      productCode: "CORRECTED",
      totalPrice: "150.25",
      quantity: "12",
    });
    expect(result.initial.lines[1]).toMatchObject({ id: "l3", productCode: "HUMAN" });
    expect(result.lines).toEqual({ "lines.1": "O2" });
    expect(current.lines).toHaveLength(3);
  });
  it("moves an explicitly remapped effective date without changing unrelated inputs", () => {
    const content = [{ path: "effective_date", value: "2026-10-01", confidence: "0.9" }];
    const choices = content.map((field) => fieldChoice(field, true));
    const first = prepareReview({ ...proposal, content }, choices, "inception_date");
    const next = prepareReview({ ...proposal, content }, choices, "signature_date");
    if (!first.ok || !next.ok) throw new Error("Expected prepared dates");
    const result = resumeDraft(
      first.review,
      { ...first.review.initial, paymentTerms: "Net 60" },
      next.review,
    );
    expect(result.initial).toMatchObject({
      inceptionDate: "",
      signatureDate: "2026-10-01",
      paymentTerms: "Net 60",
    });
    expect(result.headers.effective_date).toBe("signature_date");
  });
  it("restores retained deleted rows without colliding with new human rows", () => {
    const previous = prepared();
    const row = previous.initial.lines[0];
    if (row === undefined) throw new Error("Missing fixture row");
    const result = resumeDraft(
      previous,
      {
        ...previous.initial,
        lines: [{ ...row, id: "l9", obligationKey: "O1", productCode: "HUMAN" }],
      },
      prepared(),
    );
    expect(result.initial.lines).toHaveLength(3);
    expect(new Set(result.initial.lines.map((line) => line.id)).size).toBe(3);
    expect(new Set(result.initial.lines.map((line) => line.obligationKey)).size).toBe(3);
    expect(result.initial.lines[0]?.productCode).toBe("HUMAN");
  });
});
