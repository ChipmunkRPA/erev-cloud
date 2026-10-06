// Modifications (04 API-R-31 `GET, POST /contracts/{id}/modifications`, `GET, PATCH /modifications/{id}`,
// `POST /modifications/{id}/classify`, `/preview`, `/submit`, `/withdraw`; §16.14 API-S-Modification; E-23
// to E-26; SCREENS §4.6, §7; BUILD_SPEC CTR-24, CTR-27). The SF-03:modifications grid reads pages of the
// contract's modifications; list items carry the catch-up total of the stored preview. SF-07 reads one
// modification with its stored preview and sends its commands. No modification command takes
// `If-Match` (D-98 140-A4): the row answers `ETag "r<row_version>"` and the last write stands.
import { fetchListPage, type ListPage } from "../lists";
import { ApiProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { ensureCurrencyCodes } from "./approvals";
import {
  type ContractEvent,
  contractPathOf,
  type Judgement,
  JUDGEMENTS_PATH,
  readJson,
} from "./contracts";
import {
  fetchAllSspBooks,
  fetchSspBookVersions,
  type SspBook,
  type SspBookVersion,
  versionLabel,
} from "./ssp-books";

export type ModificationListItem = components["schemas"]["ModificationListItemOut"];
export type ModificationKind = components["schemas"]["ModificationKind"];
export type ModificationStatus = components["schemas"]["ModificationStatus"];
export type ModificationTreatment = components["schemas"]["ModificationTreatment"];
/** API-S-Modification: the list item with the authored members and the stored preview. */
export type Modification = components["schemas"]["ModificationOut"];
export type ModificationCreateBody = components["schemas"]["ModificationCreateIn"];
export type ModificationUpdateBody = components["schemas"]["ModificationUpdateIn"];
export type ModificationLineBody = components["schemas"]["ModificationLineV1"];
export type ModificationSubmitBody = components["schemas"]["ModificationSubmitIn"];
export type ModificationWithdrawBody = components["schemas"]["ModificationWithdrawIn"];
export type SspBasisBody = components["schemas"]["SspBasisV1"];
/** API-S-ImpactSummary of a stored preview. */
export type ImpactSummary = components["schemas"]["ImpactSummaryOut"];

/**
 * Whether the row HOLDS a stored preview (04 §16.10 rev 1.300 "Who reads a stored preview"; SCREENS
 * §7.7 rev 1.77): one the read answers (`impact_preview`), or one this reader is not shown
 * (`impact_preview_withheld`, with `impact_preview` null). Whatever asks whether the row is
 * previewed asks this; the tables of the preview alone ask `impact_preview`.
 */
export function holdsStoredPreview(
  row: Pick<Modification, "impact_preview" | "impact_preview_withheld">,
): boolean {
  return row.impact_preview !== null || row.impact_preview_withheld;
}

/**
 * The catch-up of the row's stored preview, or null without one: the preview's own where the read
 * answers it, else `impact_summary.catch_up_total` — the same figure of the same document, the
 * catch-up of the contract's own obligations, which the API answers to every reader of the row and
 * so for a preview this reader is not shown (04 §16.10 rev 1.300).
 */
export function storedCatchUp(
  row: Pick<Modification, "impact_preview" | "impact_summary">,
): Modification["impact_summary"]["catch_up_total"] {
  return row.impact_preview?.catch_up_total ?? row.impact_summary.catch_up_total;
}
export type JudgementCreateBody = components["schemas"]["JudgementCreateIn"];
export type JudgementTopic = components["schemas"]["JudgementTopic"];

/** T-PLT-11: preparing a modification (SCREENS §4.6, §7.1; ACT-07). */
export const MODIFICATION_CREATE_PERMISSION = "modification.create";
/** SCREENS RT-20 SF-07 and RT-21 SF-07:detail. */
export const MODIFICATION_NEW_ROUTE = "/contracts/:contractId/modifications/new";
export const MODIFICATION_ROUTE = "/contracts/:contractId/modifications/:modificationId";
/** API-R-31 default sort: newest first. */
export const DEFAULT_MODIFICATION_SORT = "-id";
/** E-26 literals in the Status filter order. */
export const MODIFICATION_STATUSES: readonly ModificationStatus[] = [
  "DRAFT",
  "SUBMITTED",
  "APPROVED",
  "APPLIED",
  "REJECTED",
  "VOIDED",
];
/** T-CON-06 `template_mode` literals with a SCREENS §4.6 label. */
export const TEMPLATE_MODES = ["prospective", "retrospective", "pob_price_change"] as const;

export function contractModificationsPath(contractId: string): string {
  return `${contractPathOf(contractId)}/modifications`;
}

export function modificationRoute(contractId: string, modificationId: string): string {
  return `/contracts/${contractId}/modifications/${modificationId}`;
}

/** The API parameters of one grid state (SCREENS §4.6 binding). */
export interface ModificationListQuery {
  readonly contractId: string;
  readonly status: readonly string[];
  readonly effectiveFrom: string | null;
  readonly effectiveTo: string | null;
}

export function contractModificationsKey(query: ModificationListQuery): QueryKey {
  return queryKey("contract-modifications", "tenant", {
    contractId: query.contractId,
    status: query.status.join(","),
    effective_from: query.effectiveFrom,
    effective_to: query.effectiveTo,
  });
}

/** One page of the contract's modifications, with the currencies of their figures registered. */
export async function fetchContractModificationsPage(
  query: ModificationListQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<ModificationListItem>> {
  const page = await fetchListPage<ModificationListItem>(
    contractModificationsPath(query.contractId),
    {
      status: query.status.length === 0 ? undefined : query.status,
      effective_from: query.effectiveFrom,
      effective_to: query.effectiveTo,
      sort: sort ?? DEFAULT_MODIFICATION_SORT,
    },
    cursor,
  );
  await ensureCurrencyCodes(page.items.map((item) => item.currency));
  return page;
}

export function modificationCountKey(contractId: string): QueryKey {
  return queryKey("contract-modifications", "tenant", { contractId, view: "count" });
}

/** The "Modifications <n>" tab count (SCREENS §4.1.7: `count=true&limit=1`). */
export async function fetchModificationCount(contractId: string): Promise<number | null> {
  const page = await fetchListPage<ModificationListItem>(
    contractModificationsPath(contractId),
    {},
    null,
    { limit: 1, count: true },
  );
  return page.total?.count ?? null;
}

// --- SF-07 and SF-07:detail (SCREENS §7; BUILD_SPEC CTR-27).

export const MODIFICATIONS_PATH = "/api/v1/modifications";
/** POL-100 `mod.route_selection` (04 E-23): the `LEGACY_*` treatments route only under this value. */
export const ROUTE_SELECTION_POLICY = "mod.route_selection";
export const USER_SELECTED_TEMPLATE = "USER_SELECTED_TEMPLATE";

/** E-25 literals in the order of the SF-07 "Kind" select: scope and price first, subscriptions last. */
export const MODIFICATION_KINDS: readonly ModificationKind[] = [
  "ADD_OBLIGATION",
  "REMOVE_OBLIGATION",
  "QUANTITY_CHANGE",
  "PRICE_CHANGE",
  "TERM_CHANGE",
  "VC_CHANGE",
  "UPGRADE",
  "DOWNGRADE",
  "CO_TERM",
  "RENEWAL",
  "EARLY_RENEWAL",
  "CANCELLATION",
  "TERMINATION",
  "OTHER",
];
/** T-CON-06 `questionnaire` members per obligation key, in the order of SCREENS §7.5. */
export const QUESTIONS = [
  "added_goods_distinct",
  "priced_at_ssp",
  "remaining_goods_distinct_from_transferred",
] as const;
export type Question = (typeof QUESTIONS)[number];
/** E-56 topics the screen can author without a topic schema of its own (04 T-CON-19). */
export const OVERRIDE_TOPIC: JudgementTopic = "MODIFICATION_TREATMENT_OVERRIDE";
export const LINKED_TOPICS: readonly JudgementTopic[] = [
  "MODIFICATION_TREATMENT_OVERRIDE",
  "SSP_OVERRIDE",
  "ESTIMATE_VS_ERROR",
  "OTHER",
];
/** The judgement `subject_type` of a modification (04 T-CON-19). */
export const MODIFICATION_SUBJECT = "modification";

export function modificationPath(modificationId: string): string {
  return `${MODIFICATIONS_PATH}/${modificationId}`;
}

export function modificationKey(modificationId: string): QueryKey {
  return queryKey("modification", "tenant", { modificationId });
}

/** Every modification row (`GET /modifications/{id}`), whatever its id. */
export const EVERY_MODIFICATION: QueryKey = queryKey("modification", "tenant");

/** The keys a modification command refreshes: the row, the contract's list and the tab count. */
export const MODIFICATION_RECORD_KEYS: readonly QueryKey[] = [
  EVERY_MODIFICATION,
  queryKey("contract-modifications", "tenant"),
  queryKey("modification-judgements", "tenant"),
];

/** The reads beside the row itself, for a command that sets the row from its answer. */
export const MODIFICATION_LIST_KEYS: readonly QueryKey[] = MODIFICATION_RECORD_KEYS.filter(
  (key) => key[0] !== "modification",
);

/** API-S-Modification with its stored preview; the currency of its figures is registered. */
export async function fetchModification(modificationId: string): Promise<Modification> {
  const { data } = await readJson<Modification>(modificationPath(modificationId));
  await ensureCurrencyCodes([data.currency]);
  return data;
}

export function modificationJudgementsKey(modificationId: string): QueryKey {
  return queryKey("modification-judgements", "tenant", { modificationId });
}

/** The judgement records whose subject is the modification, newest first (BR-MOD-02). */
export async function fetchModificationJudgements(
  modificationId: string,
): Promise<readonly Judgement[]> {
  const page = await fetchListPage<Judgement>(
    JUDGEMENTS_PATH,
    { subject_type: MODIFICATION_SUBJECT, subject_id: modificationId },
    null,
    { limit: 200, count: false },
  );
  return page.items;
}

export function routeSelectionKey(entityCode: string): QueryKey {
  return queryKey("policy-resolution", "tenant", { key: ROUTE_SELECTION_POLICY, entityCode });
}

/**
 * Whether POL-100 selects the legacy presets for the entity. Without `config.read` (403) the guided
 * route stands: the `LEGACY_*` literals are then not offered.
 */
export async function fetchLegacyRoute(entityCode: string): Promise<boolean> {
  try {
    const { data } = await readJson<components["schemas"]["PolicyResolutionOut"]>(
      "/api/v1/policies/resolve",
      { key: ROUTE_SELECTION_POLICY, entity: entityCode },
    );
    return data.value === USER_SELECTED_TEMPLATE;
  } catch (error) {
    if (error instanceof ApiProblem && error.status === 403) {
      return false;
    }
    throw error;
  }
}

/** One approved SSP book version the preparer may name instead of the classification default. */
export interface SspVersionChoice {
  readonly id: string;
  /** `<book code> <version label>`, for example "US-LIST 2026-H1". */
  readonly label: string;
}

export function approvedSspVersionsKey(currency: string): QueryKey {
  return queryKey("ssp-book-versions", "tenant", { view: "approved", currency });
}

function offered(book: SspBook, currency: string): boolean {
  return book.currency === null || book.currency === currency;
}

/**
 * The approved versions of the SSP books of the contract currency (REQ-SSP-006), in book and
 * version order. Empty without `ssp.read`: the override is then not offered.
 */
export async function fetchApprovedSspVersions(
  currency: string,
): Promise<readonly SspVersionChoice[]> {
  try {
    const books = (await fetchAllSspBooks()).filter((book) => offered(book, currency));
    const versions = await Promise.all(
      books.map(async (book) => ({ book, versions: await fetchSspBookVersions(book.id) })),
    );
    return versions.flatMap(({ book, versions: listed }) =>
      listed
        .filter((version: SspBookVersion) => version.status === "APPROVED")
        .map((version) => ({ id: version.id, label: `${book.code} ${versionLabel(version)}` })),
    );
  } catch (error) {
    if (error instanceof ApiProblem && error.status === 403) {
      return [];
    }
    throw error;
  }
}

export function latestEventKey(contractId: string): QueryKey {
  return queryKey("contract-latest-event", "tenant", { contractId });
}

/** The event of the contract with the latest effective date, for the BR-MOD-04 note; null without events. */
export async function fetchLatestEvent(contractId: string): Promise<ContractEvent | null> {
  const page = await fetchListPage<ContractEvent>(
    `${contractPathOf(contractId)}/events`,
    { sort: "-effective_date" },
    null,
    { limit: 1, count: false },
  );
  return page.items[0] ?? null;
}
