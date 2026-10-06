// Stand-in of record search for vitest (04 API-R-55 `GET /search`, §16.13 API-S-SearchResult and
// "Matching and order" rev 1.195; BUILD_SPEC CTR-28). `serveSearch` answers as the API does: an item
// matches when every term of `q` begins a word of its `primary` or of its `secondary`; without
// `scope` one group a scope in E-120 order, each with at most `limit` items and its own
// `next_cursor`; with `scope` that group from `cursor` on; a `q` shorter than two characters or
// without a letter or digit, and a cursor without a scope, are refused with 422. The world keeps the
// order it is given (the API's order by tier and instant is not a matter of a screen). It also
// answers `GET /obligations/{id}` with the contract of an obligation — the read a screen needs to
// build an obligation's route (SCREENS §1.4) — and the reads of the shell.
import { http, HttpResponse } from "msw";

import type { SearchItem, SearchScope } from "../lib/api/queries/search";
import { SEARCH_SCOPES } from "../lib/api/queries/search";
import { apiUrl, problemResponse, server } from "./msw";

export const K01_ID = "11111111-1111-4111-8111-111111111111";
export const K02_ID = "22222222-2222-4222-8222-222222222222";
export const PELLWORTH_ID = "33333333-3333-4333-8333-333333333333";
export const INVOICE_ID = "44444444-4444-4444-8444-444444444444";
export const OBLIGATION_ID = "55555555-5555-4555-8555-555555555555";
export const OTHER_OBLIGATION_ID = "56565656-5656-4565-8565-565656565656";
export const RUN_ID = "66666666-6666-4666-8666-666666666666";

export type SearchItems = Readonly<Record<SearchScope, readonly SearchItem[]>>;

/** The K-01 and K-02 records of PRD §2.5 as the search answers them for "SF-ORD". */
export const SF_ORD: SearchItems = {
  contracts: [
    {
      id: K01_ID,
      primary: "SF-ORD-10001",
      secondary: "Pellworth Logistics Inc. (Demo)",
      status: "ACTIVE",
      href: `/api/v1/contracts/${K01_ID}`,
    },
    {
      id: K02_ID,
      primary: "SF-ORD-10002",
      secondary: "Marrowby Health Partners LLC (Demo)",
      status: "PENDING_REVIEW",
      href: `/api/v1/contracts/${K02_ID}`,
    },
  ],
  customers: [
    {
      id: PELLWORTH_ID,
      primary: "SF-ORD-HOLDINGS",
      secondary: "Pellworth Logistics Inc. (Demo)",
      status: null,
      href: `/api/v1/customers/${PELLWORTH_ID}`,
    },
  ],
  invoices: [
    {
      id: INVOICE_ID,
      primary: "INV-2026-0042",
      secondary: "SF-ORD-10001",
      status: null,
      href: `/api/v1/contracts/${K01_ID}`,
    },
  ],
  obligations: [
    {
      id: OBLIGATION_ID,
      primary: "SF-ORD-10001 · O1",
      secondary: "Platform subscription",
      status: "SATISFIED",
      href: `/api/v1/obligations/${OBLIGATION_ID}`,
    },
    {
      id: OTHER_OBLIGATION_ID,
      primary: "SF-ORD-10002 · O1",
      secondary: "Platform seat, per seat",
      status: "PARTIALLY_SATISFIED",
      href: `/api/v1/obligations/${OTHER_OBLIGATION_ID}`,
    },
  ],
  journals: [
    {
      id: RUN_ID,
      primary: "JR-000118",
      secondary: "FY2026-P09 · AVM-US",
      status: "draft",
      href: `/api/v1/journal-runs/${RUN_ID}`,
    },
  ],
};

const NOTHING: SearchItems = {
  contracts: [],
  customers: [],
  invoices: [],
  obligations: [],
  journals: [],
};

/** `count` contracts `BG-AVM-0001` … of one customer, for a scope that pages. */
export function manyContracts(count: number): readonly SearchItem[] {
  return Array.from({ length: count }, (_, index) => {
    const number = String(index + 1).padStart(4, "0");
    const id = `7a7a7a7a-7a7a-4a7a-8a7a-7a7a7a7a${number}`;
    return {
      id,
      primary: `BG-AVM-${number}`,
      secondary: "Bracken Group Ltd (Demo)",
      status: "ACTIVE",
      href: `/api/v1/contracts/${id}`,
    };
  });
}

export interface SearchWorld {
  /** What the world holds, a scope each; `GET /search` answers the items the query matches. */
  items: SearchItems;
  /** Obligation id → the contract `GET /obligations/{id}` answers. */
  contractOf: Record<string, string>;
  /** Every `GET /search` the screen sent, as its query parameters. */
  readonly searches: Readonly<Record<string, string>>[];
  /** Every obligation `GET /obligations/{id}` was asked for. */
  readonly obligationReads: string[];
  /** A status every search answers with instead (a problem), until it is null again. */
  failWith: number | null;
  /** Searches wait for this before they answer. */
  hold: Promise<void> | null;
  /** Obligation reads wait for this before they answer. */
  holdObligations: Promise<void> | null;
}

function terms(q: string): readonly string[] {
  return q
    .toLowerCase()
    .split(/[^\p{L}\p{N}]+/u)
    .filter((term) => term !== "");
}

function beginsWord(text: string, term: string): boolean {
  return text
    .toLowerCase()
    .split(/[^\p{L}\p{N}]+/u)
    .some((word) => word.startsWith(term));
}

/** 04 §16.13 "Matching and order": every term begins a word of `primary` or of `secondary`. */
export function matches(item: SearchItem, q: string): boolean {
  return terms(q).every(
    (term) => beginsWord(item.primary, term) || beginsWord(item.secondary, term),
  );
}

function invalid(field: string, message: string) {
  return problemResponse("validation-failed", 422, "1 field needs attention.", {
    errors: [{ field, rule_id: "API-R-55", message }],
  });
}

/** Serves `GET /search`, `GET /obligations/{id}` and the reads of the shell. */
export function serveSearch(items: Partial<SearchItems> = SF_ORD): SearchWorld {
  const world: SearchWorld = {
    items: { ...NOTHING, ...items },
    contractOf: { [OBLIGATION_ID]: K01_ID, [OTHER_OBLIGATION_ID]: K02_ID },
    searches: [],
    obligationReads: [],
    failWith: null,
    hold: null,
    holdObligations: null,
  };
  const page = (scope: SearchScope, q: string, limit: number, cursor: string | null) => {
    const found = world.items[scope].filter((item) => matches(item, q));
    const from = cursor === null ? 0 : Number(cursor.replace(`${scope}:`, ""));
    const next = from + limit;
    return {
      scope,
      items: found.slice(from, next),
      next_cursor: next < found.length ? `${scope}:${String(next)}` : null,
    };
  };
  const empty = () => HttpResponse.json({ items: [], next_cursor: null });
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), empty),
    http.get(apiUrl("/api/v1/entities"), empty),
    http.get(apiUrl("/api/v1/books"), empty),
    http.get(apiUrl("/api/v1/periods"), empty),
    http.get(apiUrl("/api/v1/search"), async ({ request }) => {
      const params = new URL(request.url).searchParams;
      world.searches.push(Object.fromEntries(params));
      if (world.hold !== null) {
        await world.hold;
      }
      if (world.failWith !== null) {
        return problemResponse(
          world.failWith === 403 ? "forbidden" : "internal-error",
          world.failWith,
          world.failWith === 403 ? "Forbidden" : "The search could not be read",
        );
      }
      const q = (params.get("q") ?? "").trim();
      if (q.length < 2) {
        return invalid("q", "Type at least 2 characters to search.");
      }
      if (terms(q).length === 0) {
        return invalid("q", "Type a letter or a digit to search.");
      }
      const scope = params.get("scope");
      const cursor = params.get("cursor");
      const limit = Number(params.get("limit") ?? "8");
      if (scope === null) {
        if (cursor !== null) {
          return invalid("cursor", "Send cursor together with scope.");
        }
        return HttpResponse.json({
          results: SEARCH_SCOPES.map((name) => page(name, q, limit, null)),
        });
      }
      const named = SEARCH_SCOPES.find((name) => name === scope);
      if (named === undefined) {
        return invalid("scope", "Not a scope.");
      }
      return HttpResponse.json(page(named, q, limit, cursor));
    }),
    http.get(apiUrl("/api/v1/obligations/:obligationId"), async ({ params }) => {
      const id = String(params.obligationId);
      world.obligationReads.push(id);
      if (world.holdObligations !== null) {
        await world.holdObligations;
      }
      const contractId = world.contractOf[id];
      return contractId === undefined
        ? problemResponse("not-found", 404, "Obligation not found")
        : HttpResponse.json({ id, contract_id: contractId });
    }),
  );
  return world;
}

/** A gate a test opens: `[promise, release]`. */
export function gate(): readonly [Promise<void>, () => void] {
  let release: () => void = () => undefined;
  const promise = new Promise<void>((resolve) => {
    release = resolve;
  });
  return [promise, release];
}
