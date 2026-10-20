import { send } from "../client";
import { fetchListPage, type ListPage, type ListQuery } from "../lists";
import { readProblem } from "../problems";
import type { components } from "../schema";

export type DisclosureSnapshot = components["schemas"]["DisclosureSnapshotSummaryOut"];
export type DisclosureSnapshotDetail = components["schemas"]["DisclosureSnapshotOut"];
const PATH = "/api/v1/disclosure-snapshots";

export async function fetchDisclosureSnapshots(
  runId: string,
): Promise<readonly DisclosureSnapshot[]> {
  const items: DisclosureSnapshot[] = [];
  let cursor: string | null = null;
  do {
    const page: ListPage<DisclosureSnapshot> = await fetchListPage<DisclosureSnapshot>(
      PATH,
      { report_run_id: runId },
      cursor,
    );
    items.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor !== null);
  return items.sort((a, b) => a.disclosure_kind.localeCompare(b.disclosure_kind));
}

/** Detail is returned only after the server verifies the saved payload's digest and scope. */
export async function fetchDisclosureSnapshot(id: string): Promise<DisclosureSnapshotDetail> {
  const response = await send("GET", `${PATH}/${encodeURIComponent(id)}`);
  if (!response.ok) throw await readProblem(response);
  return (await response.json()) as DisclosureSnapshotDetail;
}

export function fetchDisclosureSnapshotPage(query: ListQuery, cursor: string | null) {
  return fetchListPage<DisclosureSnapshot>(PATH, query, cursor, { limit: 50, count: false });
}
