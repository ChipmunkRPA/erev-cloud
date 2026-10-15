// Human review state is local until the atomic acceptance command succeeds.
import type { ExtractionDraft, ExtractionProposal } from "../../lib/api/queries/ai";
import { emptyDraft, emptyLine, type DraftForm, type DraftLine } from "../../lib/forms/contract";

export type Decision = "ACCEPT" | "EDIT" | "REJECT";
export interface FieldChoice {
  readonly decision: Decision | null;
  readonly value: string;
  readonly product: string;
  readonly reason: string;
}
export interface PreparedReview {
  readonly decisions: ExtractionDraft["field_decisions"];
  readonly headers: ExtractionDraft["header_bindings"];
  readonly lines: ExtractionDraft["line_bindings"];
  readonly initial: DraftForm;
}
export type ReviewError =
  "incomplete" | "reason" | "empty" | "unsupported" | "invalid" | "dateTarget";
export type ReviewPreparation =
  | { readonly ok: true; readonly review: PreparedReview }
  | { readonly ok: false; readonly error: ReviewError; readonly path: string };

export function fieldChoice(field: Record<string, unknown>, cited: boolean): FieldChoice {
  const line =
    typeof field.value === "object" && field.value !== null
      ? (field.value as Record<string, unknown>)
      : null;
  const confidence = typeof field.confidence === "string" ? Number(field.confidence) : NaN;
  return {
    decision:
      cited && Number.isFinite(confidence) && confidence >= 0.75 && confidence <= 1
        ? "ACCEPT"
        : null,
    value: line !== null ? String(line.amount ?? "") : String(field.value ?? ""),
    product: line === null ? "" : String(line.product_code ?? ""),
    reason: "",
  };
}

/** Never invent currency, quantity, identity, dates or accounting terms from a suggestion. */
export function prepareReview(
  proposal: ExtractionProposal,
  choices: readonly FieldChoice[],
  dateTarget: "inception_date" | "signature_date" | null,
): ReviewPreparation {
  const initial = emptyDraft("l1");
  const decisions: ExtractionDraft["field_decisions"] = [];
  const headers: ExtractionDraft["header_bindings"] = {};
  const lines: ExtractionDraft["line_bindings"] = {};
  let draft: DraftForm = { ...initial, documentRef: `AI proposal ${proposal.id}` };
  const retainedLines: DraftLine[] = [];
  const paths = new Set<string>();
  let retained = 0;
  for (const [index, field] of proposal.content.entries()) {
    const path = typeof field.path === "string" ? field.path : "";
    const choice = choices[index];
    if (!path || paths.has(path)) return { ok: false, error: "invalid", path };
    paths.add(path);
    if (choice?.decision == null) return { ok: false, error: "incomplete", path };
    const reason = choice.reason.trim();
    if (
      choice.decision !== "ACCEPT" &&
      (Array.from(reason).length < 10 || reason.length > 4000 || reason.includes("\0"))
    )
      return { ok: false, error: "reason", path };
    if (choice.decision === "REJECT") {
      decisions.push({ path, decision: "REJECT", reason });
      continue;
    }
    const isLine = /^lines\.(?:0|[1-9]\d{0,2})$/.test(path) && Number(path.slice(6)) < 500;
    const value: unknown =
      choice.decision === "ACCEPT"
        ? field.value
        : isLine
          ? { product_code: choice.product, amount: choice.value }
          : choice.value;
    if (isLine) {
      if (typeof value !== "object" || value === null) return { ok: false, error: "invalid", path };
      const line = value as Record<string, unknown>;
      if (
        typeof line.product_code !== "string" ||
        !line.product_code.trim() ||
        typeof line.amount !== "string" ||
        !/^-?\d{1,20}(?:\.\d{1,4})?$/.test(line.amount)
      )
        return { ok: false, error: "invalid", path };
      const key = `O${String(retainedLines.length + 1)}`;
      lines[path] = key;
      retainedLines.push({
        ...emptyLine(`l${String(retainedLines.length + 1)}`, key),
        productCode: line.product_code,
        totalPrice: line.amount,
      });
    } else if (path === "customer_name" || path === "effective_date" || path === "payment_terms") {
      if (typeof value !== "string" || !value.trim()) return { ok: false, error: "invalid", path };
      if (path === "customer_name") {
        headers.customer_name = "customer";
        draft = { ...draft, customer: { kind: "new", name: value } };
      } else if (path === "payment_terms") {
        headers.payment_terms = "payment_terms";
        draft = { ...draft, paymentTerms: value };
      } else {
        if (dateTarget === null) return { ok: false, error: "dateTarget", path };
        headers.effective_date = dateTarget;
        draft =
          dateTarget === "inception_date"
            ? { ...draft, inceptionDate: value }
            : { ...draft, signatureDate: value };
      }
    } else return { ok: false, error: "unsupported", path };
    retained += 1;
    decisions.push(
      choice.decision === "EDIT"
        ? { path, decision: "EDIT", value, reason }
        : { path, decision: "ACCEPT" },
    );
  }
  if (retained === 0) return { ok: false, error: "empty", path: "" };
  if (retainedLines.length) draft = { ...draft, lines: retainedLines };
  return { ok: true, review: { decisions, headers, lines, initial: draft } };
}
