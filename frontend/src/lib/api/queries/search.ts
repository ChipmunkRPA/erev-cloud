// Record search (04 API-R-55 `GET /search`, §16.13 API-S-SearchResult and "Matching and order" rev
// 1.195, E-120; SCREENS §1.4 SF-24 and SF-24:results, §0.4 RT-95; DESIGN_SYSTEM DS-CMP-04; BUILD_SPEC
// CTR-28). Without `scope` the route answers one group a scope, in E-120 order, each with its own
// cursor; with `scope` it answers that group, and a cursor is admitted only then. An item is
// `{id, primary, secondary, status, href}`; `href` is an API link, so the route of a record is built
// here from its scope and id (04 B3-D11).
import { ApiProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { readJson } from "./contracts";
import { OBLIGATIONS_PATH } from "./obligations";

export type SearchScope = components["schemas"]["SearchScope"];
export type SearchItem = components["schemas"]["SearchItemOut"];
export type SearchGroup = components["schemas"]["SearchScopeOut"];

/** 04 E-120, in the order the API answers the scopes. */
export const SEARCH_SCOPES: readonly SearchScope[] = [
  "contracts",
  "customers",
  "invoices",
  "obligations",
  "journals",
];

export const SEARCH_PATH = "/api/v1/search";
/** 04 API-R-55: the permission of the route, and of the single read of every scope. */
export const SEARCH_PERMISSION = "contract.read";
/** SCREENS RT-95 SF-24:results. */
export const SEARCH_ROUTE = "/search";
/** DESIGN_SYSTEM DS-CMP-04: at most 8 results a group in the palette. */
export const PALETTE_LIMIT = 8;
/** SCREENS §1.4: at most 25 rows a table, and 25 more with each "Show more". */
export const RESULTS_LIMIT = 25;

/**
 * The enum of a scope's `status` literal (04 §16.13 "What is answered"; SCREENS §1.4): E-17 of a
 * contract, E-22 of an obligation, E-34 of a journal run; a customer and an invoice have none.
 */
export const SEARCH_STATUS_ENUM: Readonly<Record<SearchScope, string | null>> = {
  contracts: "E-17",
  customers: null,
  invoices: null,
  obligations: "E-22",
  journals: "E-34",
};

const MIN_QUERY = 2;
const MAX_QUERY = 200;

export function isSearchScope(value: string | null | undefined): value is SearchScope {
  return (SEARCH_SCOPES as readonly string[]).includes(value ?? "");
}

/**
 * The `q` a search sends, or null for a text that is not searched: trimmed, at least 2 characters
 * and with a letter or a digit — the route refuses any other with 422 (04 API-R-55 rev 1.195). A
 * longer text is searched by its first 200 characters, the most the route takes.
 */
export function searchable(query: string): string | null {
  const text = query.trim().slice(0, MAX_QUERY).trimEnd();
  return text.length >= MIN_QUERY && /[\p{L}\p{N}]/u.test(text) ? text : null;
}

export function searchKey(q: string, scope: SearchScope | null, limit: number): QueryKey {
  return queryKey("search", "tenant", { q, scope, limit });
}

/**
 * A `q` the route refuses holds no term for the database, which alone says what a letter is (04
 * §16.13 "Matching and order"): such a text finds nothing, and that is what the screens show.
 */
function refusedQuery(error: unknown): boolean {
  return (
    error instanceof ApiProblem &&
    error.status === 422 &&
    error.errors.some((item) => item.field === "q")
  );
}

/** Every scope at once: one group a scope, in E-120 order. */
export async function fetchSearch(q: string, limit: number): Promise<readonly SearchGroup[]> {
  try {
    const { data } = await readJson<components["schemas"]["SearchResultsOut"]>(SEARCH_PATH, {
      q,
      limit,
    });
    return data.results;
  } catch (error) {
    if (refusedQuery(error)) {
      return SEARCH_SCOPES.map((scope) => ({ scope, items: [], next_cursor: null }));
    }
    throw error;
  }
}

/** One scope, from `cursor` on; the cursor belongs to its `q` and its scope. */
export async function fetchSearchScope(
  q: string,
  scope: SearchScope,
  limit: number,
  cursor: string | null,
): Promise<SearchGroup> {
  try {
    const { data } = await readJson<SearchGroup>(SEARCH_PATH, { q, scope, limit, cursor });
    return data;
  } catch (error) {
    if (cursor === null && refusedQuery(error)) {
      return { scope, items: [], next_cursor: null };
    }
    throw error;
  }
}

/**
 * SF-24:results of a query, under a scope chip when one is named. The link is written as the
 * FilterBar of the page writes it (SCREENS §0.5 SCR-URL-08): `q` percent-encoded and one
 * `f.scope=is:<scope>` with a plain colon — the filter codec reads the operator up to the colon of
 * the raw value, so an encoded colon would be a filter the page does not recognise.
 */
export function searchResultsRoute(q: string, scope: SearchScope | null = null): string {
  const chip = scope === null ? "" : `&f.scope=is:${scope}`;
  return `${SEARCH_ROUTE}?q=${encodeURIComponent(q)}${chip}`;
}

/** The route patterns of `src/app/router.tsx` a record of each scope opens (SCREENS §1.4). */
export const RECORD_ROUTE_PATTERNS: Readonly<Record<SearchScope, string>> = {
  contracts: "/contracts/:contractId/obligations",
  customers: "/settings/customers/:customerId",
  invoices: "/contracts/:contractId/billing",
  obligations: "/contracts/:contractId/obligations/:obligationId",
  journals: "/journals/runs/:runId",
};

const CONTRACT_HREF = /^\/api\/v1\/contracts\/([^/?#]+)$/;

/**
 * The route of a record (SCREENS §1.4): a contract opens its Obligations tab, a customer its page, an
 * invoice the Billing tab of its contract — the contract id is the one `href` names — and a journal
 * run its page. An obligation's route needs the id of its contract, which the item does not carry
 * (`obligationRoute`); null for it, and for an invoice whose `href` names no contract.
 */
export function recordRoute(
  scope: SearchScope,
  item: Pick<SearchItem, "id" | "href">,
): string | null {
  switch (scope) {
    case "contracts":
      return `/contracts/${item.id}/obligations`;
    case "customers":
      return `/settings/customers/${item.id}`;
    case "invoices": {
      const contractId = CONTRACT_HREF.exec(item.href)?.[1];
      return contractId === undefined ? null : `/contracts/${contractId}/billing`;
    }
    case "journals":
      return `/journals/runs/${item.id}`;
    case "obligations":
      return null;
  }
}

export function obligationRoute(contractId: string, obligationId: string): string {
  return `/contracts/${contractId}/obligations/${obligationId}`;
}

export function obligationContractKey(obligationId: string): QueryKey {
  return queryKey("obligation-contract", "tenant", { obligationId });
}

/** The contract of an obligation, read from `GET /obligations/{id}` (SCREENS §1.4). */
export async function fetchObligationContract(obligationId: string): Promise<string> {
  const { data } = await readJson<{ readonly contract_id: string }>(
    `${OBLIGATIONS_PATH}/${obligationId}`,
  );
  return data.contract_id;
}

/** The terms of a query as the route splits them: its runs of letters and digits, case-folded. */
export function searchTerms(q: string): readonly string[] {
  return q
    .toLowerCase()
    .split(/[^\p{L}\p{N}]+/u)
    .filter((term) => term !== "");
}

export interface MatchPart {
  readonly text: string;
  readonly match: boolean;
}

/**
 * `text` in parts, with the beginnings of its words that a term matches marked: the route matches a
 * term where it begins a word of `primary` or of `secondary` and never inside one (04 §16.13
 * "Matching and order"). The longest term a word begins with is the one marked. The mark is
 * emphasis alone: what is found is the route's answer.
 */
export function markMatches(text: string, terms: readonly string[]): readonly MatchPart[] {
  const parts: MatchPart[] = [];
  let at = 0;
  for (const word of text.matchAll(/[\p{L}\p{N}]+/gu)) {
    const folded = word[0].toLowerCase();
    const length = terms.reduce(
      (longest, term) => (folded.startsWith(term) && term.length > longest ? term.length : longest),
      0,
    );
    if (length === 0) {
      continue;
    }
    if (word.index > at) {
      parts.push({ text: text.slice(at, word.index), match: false });
    }
    parts.push({ text: text.slice(word.index, word.index + length), match: true });
    at = word.index + length;
  }
  if (at < text.length) {
    parts.push({ text: text.slice(at), match: false });
  }
  return parts;
}
