// Obligations (04 API-R-29 `GET /contracts/{id}/obligations`, `GET /obligations/{id}`,
// `GET /obligations/{id}/schedule`, `GET /obligations/{id}/events`; API-R-06 `GET /ssp-book-versions/{id}`
// and `GET /ssp-books/{id}` for the SSP book version label; SCREENS §4.2, §5.4, §5.6; BUILD_SPEC CTR-22).
// Every read passes the context `book`, `as_of` and `known_at` (BR-UX-02, SCR-URL-23).
import { fetchListPage, type ListQuery } from "../lists";
import { ApiProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { readJson, type RecordContext, recordParams } from "./contracts";

export type Obligation = components["schemas"]["ObligationOut"];
export type ScheduleLine = components["schemas"]["ScheduleLineOut"];
// API-S-Event is one schema (04 rev 1.273): the obligation's route answers what the events
// resource answers.
export type ObligationEvent = components["schemas"]["EventOut"];
export type SspRangePosition = components["schemas"]["SspRangePosition"];
type SspBookVersion = components["schemas"]["SspBookVersionOut"];
type SspBook = components["schemas"]["SspBookOut"];

/** An open hold as API-S-Contract and API-S-Obligation list it (04 §16.1, §16.2 rev 1.299; T-CON-20). */
export type Hold = components["schemas"]["HoldOut"];

/** An open hold of a contract with the obligation it holds; null for a hold of the whole contract. */
export interface OpenHold {
  readonly hold: Hold;
  readonly obligationKey: string | null;
}

/**
 * Every open hold of a contract (04 §16.1 rev 1.299): API-S-Contract lists the holds of the whole
 * contract and each obligation its own, and a screen that wants them all reads both. The contract's
 * first, then each obligation's in the order of `obligations`; each list oldest first, as the API
 * answers it.
 */
export function openHolds(
  contract: { readonly holds?: readonly Hold[] | undefined },
  obligations: readonly Pick<Obligation, "obligation_key" | "holds">[],
): readonly OpenHold[] {
  return [
    ...(contract.holds ?? []).map((hold) => ({ hold, obligationKey: null })),
    ...obligations.flatMap((item) =>
      item.holds.map((hold) => ({ hold, obligationKey: item.obligation_key })),
    ),
  ];
}

export const OBLIGATIONS_PATH = "/api/v1/obligations";
/** SCREENS §5.6: more than 100 schedule lines switch to the DataGrid; the pane reads one page. */
export const PANE_PAGE_LIMIT = 100;

function contextParams(context: RecordContext): Readonly<Record<string, string | null>> {
  return { book: context.book, as_of: context.asOf, known_at: context.knownAt };
}

export function contractObligationsKey(contractId: string, context: RecordContext): QueryKey {
  return queryKey("contract-obligations", "tenant", { contractId, ...contextParams(context) });
}

/** API-S-Obligation of every obligation of the contract; one page (a contract holds at most 500). */
export async function fetchContractObligations(
  contractId: string,
  context: RecordContext,
): Promise<readonly Obligation[]> {
  const page = await fetchListPage<Obligation>(
    `/api/v1/contracts/${contractId}/obligations`,
    recordParams(context),
    null,
    { limit: 500, count: false },
  );
  return page.items;
}

export function obligationKey(obligationId: string, context: RecordContext): QueryKey {
  return queryKey("obligation", "tenant", { obligationId, ...contextParams(context) });
}

export async function fetchObligation(
  obligationId: string,
  context: RecordContext,
): Promise<Obligation> {
  return (await readJson<Obligation>(`${OBLIGATIONS_PATH}/${obligationId}`, recordParams(context)))
    .data;
}

export function obligationScheduleKey(obligationId: string, context: RecordContext): QueryKey {
  return queryKey("obligation-schedule", "tenant", { obligationId, ...contextParams(context) });
}

/** The obligation's schedule lines at the version in context, in period order. */
export async function fetchObligationSchedule(
  obligationId: string,
  context: RecordContext,
): Promise<readonly ScheduleLine[]> {
  const page = await fetchListPage<ScheduleLine>(
    `${OBLIGATIONS_PATH}/${obligationId}/schedule`,
    recordParams(context),
    null,
    { limit: PANE_PAGE_LIMIT, count: false },
  );
  return page.items;
}

export function obligationEventsKey(obligationId: string, knownAt: string | null): QueryKey {
  return queryKey("obligation-events", "tenant", { obligationId, known_at: knownAt });
}

/** API-S-Event of the stream events naming the obligation, recorded by `known_at`. */
export async function fetchObligationEvents(
  obligationId: string,
  knownAt: string | null,
): Promise<readonly ObligationEvent[]> {
  const query: ListQuery = { known_at: knownAt };
  const page = await fetchListPage<ObligationEvent>(
    `${OBLIGATIONS_PATH}/${obligationId}/events`,
    query,
    null,
    { limit: PANE_PAGE_LIMIT, count: false },
  );
  return page.items;
}

export function sspVersionLabelKey(versionId: string): QueryKey {
  return queryKey("ssp-version-label", "tenant", { versionId });
}

export interface SspVersionLabel {
  readonly label: string;
  /** The book of the version, for the SF-13:ssp-book-version link; null when it cannot be read. */
  readonly bookId: string | null;
  /**
   * The key the engine names the version by, `<book code>@v<version no>` (04 §16.14 `prefill_reasons`
   * and `price_tests`, `params.ssp_version_key`); null when the version cannot be read.
   */
  readonly key: string | null;
}

/**
 * SCREENS §5.6 "SSP book version": `<book code> <version label>`, for example "DE-LIST 2026". The
 * obligation carries only the version label, so the version and its book are read; without
 * `ssp.read` (403) the stored label stands alone.
 */
export async function fetchSspVersionLabel(
  versionId: string,
  stored: string | null,
): Promise<SspVersionLabel> {
  try {
    const version = (await readJson<SspBookVersion>(`/api/v1/ssp-book-versions/${versionId}`)).data;
    const book = (await readJson<SspBook>(`/api/v1/ssp-books/${version.ssp_book_id}`)).data;
    const label = stored ?? version.legacy_version_label;
    return {
      label: label === null ? book.code : `${book.code} ${label}`,
      bookId: book.id,
      key: `${book.code}@v${String(version.version_no)}`,
    };
  } catch (error) {
    if (error instanceof ApiProblem && (error.status === 403 || error.status === 404)) {
      return { label: stored ?? "", bookId: null, key: null };
    }
    throw error;
  }
}

/** SCREENS §4.2 sort menu: key (numeric collation), start date, product. */
export type ObligationSort = "key" | "start" | "product";

const COLLATOR = new Intl.Collator("en", { numeric: true, sensitivity: "base" });

export function sortObligations(
  items: readonly Obligation[],
  sort: ObligationSort,
): readonly Obligation[] {
  const byKey = (left: Obligation, right: Obligation) =>
    COLLATOR.compare(left.obligation_key, right.obligation_key);
  return [...items].sort((left, right) => {
    if (sort === "start") {
      const a = left.start_date ?? "";
      const b = right.start_date ?? "";
      return a === b ? byKey(left, right) : a < b ? -1 : 1;
    }
    if (sort === "product") {
      const order = COLLATOR.compare(left.product.name, right.product.name);
      return order === 0 ? byKey(left, right) : order;
    }
    return byKey(left, right);
  });
}

/** SCREENS §4.2: client-side match on key, product code and product name. */
export function matchesObligation(item: Obligation, text: string): boolean {
  const query = text.trim().toLocaleLowerCase();
  return (
    query === "" ||
    [item.obligation_key, item.product.code, item.product.name].some((value) =>
      value.toLocaleLowerCase().includes(query),
    )
  );
}
