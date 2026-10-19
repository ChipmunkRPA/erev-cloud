// CLOSE evidence reads use the ordinary authenticated API pipeline. The server applies
// the intersection of source permissions before pagination and verifies each download.
import type { Access } from "../../access";
import { send } from "../client";
import { fetchListPage, type ListPage } from "../lists";
import { readProblem } from "../problems";
import { queryKey } from "../query-keys";
import type { components } from "../schema";

export type EvidencePack =
  components["schemas"]["ClosePackOut"] | components["schemas"]["ContractSamplePackOut"];
export type EvidencePackSummary = components["schemas"]["ClosePackSummaryOut"];
export const EVIDENCE_PACKS_PATH = "/api/v1/evidence-packs";
export const EVIDENCE_PACKS_ROUTE = "/reports/evidence";
const READ = ["report.run", "audit.read", "contract.read"] as const;
const EXPORT = [...READ, "report.export", "evidence.export"] as const;

export function mayReadEvidence(access: Access): boolean {
  return READ.every((permission) => access.holdsAnywhere(permission));
}

export function mayDownloadEvidence(
  access: Access,
  pack: EvidencePackSummary | EvidencePack,
): boolean {
  if (pack.kind === "CONTRACT_SAMPLE")
    return EXPORT.every((permission) =>
      pack.all_entities
        ? access.holdsForAll(permission)
        : pack.source_entity_ids.every((id) => access.holds(permission, { id })),
    );
  return EXPORT.every((permission) => access.holds(permission, { id: pack.entity_id }));
}

type PackScope = Pick<EvidencePackSummary, "entity_code" | "book" | "period_key">;

export function evidencePackContext(pack: PackScope): string {
  return `?${new URLSearchParams({
    entity: pack.entity_code,
    book: pack.book,
    period: pack.period_key,
  }).toString()}`;
}

export function evidencePackRoute(id: string, pack: PackScope): string {
  return `${EVIDENCE_PACKS_ROUTE}/${encodeURIComponent(id)}${evidencePackContext(pack)}`;
}

export interface EvidencePackQuery {
  readonly entities: readonly string[];
  readonly book: string | null;
  readonly period: string | null;
  readonly statuses: readonly string[];
}

export function evidencePacksKey(query: EvidencePackQuery) {
  return queryKey("evidence-packs", "tenant", {
    entities: query.entities.join(","),
    book: query.book,
    period: query.period,
    statuses: query.statuses.join(","),
  });
}

export function evidencePackKey(id: string) {
  return queryKey("evidence-pack", "tenant", { id });
}

export function fetchEvidencePacksPage(
  query: EvidencePackQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<EvidencePackSummary>> {
  return fetchListPage(
    EVIDENCE_PACKS_PATH,
    {
      entity: query.entities,
      book: query.book,
      period: query.period,
      status: query.statuses,
      kind: "CLOSE",
      sort,
    },
    cursor,
  );
}

export async function fetchEvidencePack(id: string): Promise<EvidencePack> {
  const response = await send("GET", `${EVIDENCE_PACKS_PATH}/${encodeURIComponent(id)}`);
  if (!response.ok) throw await readProblem(response);
  return (await response.json()) as EvidencePack;
}

export async function downloadEvidencePack(
  id: string,
  artifact: "download" | "manifest" = "download",
): Promise<Blob> {
  const response = await send(
    "GET",
    `${EVIDENCE_PACKS_PATH}/${encodeURIComponent(id)}/${artifact}`,
  );
  if (!response.ok) throw await readProblem(response);
  return response.blob();
}

export function mayCreateEvidence(access: Access, entityId: string): boolean {
  return EXPORT.every((permission) => access.holds(permission, { id: entityId }));
}

export function mayChooseEvidenceSources(access: Access): boolean {
  return [...EXPORT, "config.read"].every((permission) => access.holdsAnywhere(permission));
}
