// SF-20 review API boundary: retained reads, explicit human commands and server ETags.
// Source authorization is enforced by the API on every read and replay. No AI setting gates
// retained reads, and this module never retries a command or infers draft inputs.
import { send } from "../client";
import type { CommandKeys } from "../commands";
import { fetchListPage, type ListQuery } from "../lists";
import { readProblem } from "../problems";
import { queryKey } from "../query-keys";
import type { components } from "../schema";
import { sendCommand } from "./contracts";

export type ExtractionProposal = components["schemas"]["AIExtractionProposalOut"];
export type AIProposal = ExtractionProposal | components["schemas"]["AIProposalOut"];
export type DocumentText = components["schemas"]["AIDocumentTextOut"];
export type ExtractionDraft = components["schemas"]["AIExtractionDraftIn"];
export type AcceptedDraft = components["schemas"]["AIProposalAcceptedOut"];

export const AI_PROPOSALS_PATH = "/api/v1/ai/proposals";
export const AI_EXTRACTIONS_PATH = "/api/v1/ai/contract-extractions";
export const AI_REVIEW_ROUTE = "/contracts/review";
export const AI_USE_PERMISSION = "ai.use";

export function proposalPath(id: string): string {
  return `${AI_PROPOSALS_PATH}/${encodeURIComponent(id)}`;
}

export function proposalKey(id: string) {
  return queryKey("ai-proposals", "tenant", { id });
}

export function documentTextKey(id: string) {
  return queryKey("ai-document-text", "tenant", { id });
}

/** Null ETag permits display but must never be replaced with an invented version for review. */
export async function fetchProposal(id: string): Promise<{
  readonly proposal: AIProposal;
  readonly etag: string | null;
}> {
  const response = await send("GET", proposalPath(id));
  if (!response.ok) throw await readProblem(response);
  return { proposal: (await response.json()) as AIProposal, etag: response.headers.get("ETag") };
}

export async function fetchDocumentText(id: string): Promise<DocumentText> {
  const response = await send("GET", `${proposalPath(id)}/document-text`);
  if (!response.ok) throw await readProblem(response);
  return (await response.json()) as DocumentText;
}

export function fetchProposals(query: ListQuery, cursor: string | null = null) {
  return fetchListPage<AIProposal>(AI_PROPOSALS_PATH, query, cursor);
}

export function submitExtraction(keys: CommandKeys, fileId: string) {
  return sendCommand<components["schemas"]["JobOut"]>(keys, "POST", AI_EXTRACTIONS_PATH, {
    file_id: fileId,
  } satisfies components["schemas"]["AIContractExtractionIn"]);
}

export function rejectProposal(keys: CommandKeys, id: string, etag: string, reason: string) {
  return sendCommand<AIProposal>(keys, "POST", `${proposalPath(id)}/reject`, { reason }, etag);
}

export function acceptExtraction(
  keys: CommandKeys,
  id: string,
  etag: string,
  body: ExtractionDraft,
) {
  return sendCommand<AcceptedDraft>(keys, "POST", `${proposalPath(id)}/accept`, body, etag);
}
