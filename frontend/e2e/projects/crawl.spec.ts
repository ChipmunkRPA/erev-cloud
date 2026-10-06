// Route crawl (docs/dev-guide.md DG-E2E-02, DG-E2E-13; SCREENS §0.4; supervisor ruling R-67 (b)). Two
// defects reached browser QA because no e2e step opened their routes: five Policies pages crashed on an
// effective instant (Q-9) and two lists asked for a sort their routes refuse (Q-30). This project opens
// every route of `src/app/router.tsx` as a persona that holds the permission SCREENS §0.4 names for it
// and fails when the route error boundary, "Page not found" or the no-access state renders, when an API
// request of the page answers 4xx or 5xx outside `ALLOWED`, or when a script error goes uncaught. On
// each page it clicks every sortable column header once, types a term into each quick search, applies
// every field of each filter bar once and opens every panel tab, under the same checks.
//
// The route list is read from the router, so a new route is crawled without an edit here. A route with
// a path parameter needs its record in `SEEDS`; a route this project cannot open is in `NOT_OPENED` or
// `NOT_SEEDED` with its reason and its test proves the reason still holds. The record of each route
// (persona, URL, what was driven and what was not) is attached to its test and written to
// `e2e/.results/crawl/`. This project does not replace the SCREENS_B §15 audit rows of `screens`.
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import type { APIRequestContext, Page, TestInfo } from "@playwright/test";

import { json } from "../support/api";
import { passwordStep, type Persona, personaEmail, PERSONAS } from "../support/auth";
import {
  type Allowed,
  driveFilters,
  driveGrids,
  type Finding,
  inspect,
  notFound,
  panelTabs,
  Watch,
} from "../support/crawl";
import { expect, type Personas, test } from "../support/fixtures";
import {
  readRouter,
  readScreenRows,
  routeAt,
  type RouterRoute,
  screenRowOf,
} from "../support/routes";
import { normaliseKey, RESULTS_DIR } from "../support/screens";
import { ensureJournalRun, ensurePoolRun, sspBookByCode } from "../support/world";

const ROUTES = readRouter();
const ROWS = readScreenRows();

/** Personas in the order they are tried: the first that holds the permission opens the route. */
const ORDER: readonly Persona[] = [
  "maya",
  "tomas",
  "nikhil",
  ...PERSONAS.filter((persona) => !["maya", "tomas", "nikhil"].includes(persona)),
];

/** Routes whose row names no permission and whose state still depends on who opens them. */
const PERSONA_OF: Readonly<Record<string, Persona>> = {
  // A persona with several workspaces: a single membership opens at once and leaves the page (D-83).
  "SF-23:select": "robert",
  // RT-58 asks for "any approval permission" (T-PLT-11 `is_approval`), which names no code: a Revenue
  // Reviewer holds ten of them, a Revenue Accountant none (SCR-PERM-01 for her).
  "SF-12:delegations": "priya",
};

/** Routes this project does not open, each with its reason. */
const NOT_OPENED: Readonly<Record<string, string>> = {
  "SF-22:mfa-enrol":
    "opening the page starts a factor enrolment for the signed-in user (a command on mount), which " +
    "would change how the persona signs in for the rest of the run; J-20 of project fresh-tenant owns it",
};

/** Routes whose record the demo world does not hold; the test proves the list is still empty. */
const NOT_SEEDED: Readonly<Record<string, string>> = {
  "SF-19:detail": "the demo world holds no migration (GET /migrations lists none)",
  "SF-14:access-review": "the demo world holds no access review (GET /access-reviews lists none)",
};

/**
 * Routes whose record the demo seed does not hold and a row of project `screens` leaves behind. In
 * `make e2e` this project runs after `screens`, so the record is there and its absence fails; a run
 * of this project alone on a fresh world lists the route with the reason instead.
 */
const LEFT_BY_SCREENS: Readonly<Record<string, string>> = {
  "SF-09:verification":
    "the world holds no chain verification until the row SF-09:audit-log of project screens starts one",
  "SF-16:connection":
    "the world holds no connection until the rows SF-16 of project screens add one",
  "SF-16:sync-run":
    "the world holds no sync run until the rows SF-16 of project screens test their connection",
  "SF-08:run":
    "the world holds no report run until a row of project screens opens a report view (SF-08:report)",
  "SF-05:reconciliation":
    "the world holds no reconciliation until the row SF-05:reconciliations of project screens " +
    "generates billing to subledger for AVM-DE Sep 2026",
  "SF-07:detail":
    "the world holds no modification until the rows SF-07 of project screens leave one on K-02",
  "SF-03:estimate":
    "the world holds no estimate until the rows SF-03:estimates of project screens add one to K-03",
};
/** `make e2e` without a restriction: every project ran before this one (scripts/e2e.sh). */
const WHOLE_GATE = process.env.EREV_E2E_COMMAND === "make e2e";

/** Routes that render no screen of their own, and the screen they land on. */
const LANDS_ON: Readonly<Record<string, string>> = {
  "X:landing": "SF-01",
  "X:contract-redirect": "SF-03",
  "X:close-redirect": "SF-05",
  "X:import-redirect": "SF-10:detail",
  "SF-13": "SF-13:revenue",
  "SF-13:ssp-book": "SF-13:ssp-book-version",
};

const ACTION_MS = 20_000;

/**
 * API answers of 400 and above that are correct, or a known defect with the item that owns it. Empty
 * since item W-19 closed crawl finding F1 (SF-06:run-lines sent typed text to two uuid filters).
 */
const ALLOWED: readonly Allowed[] = [];

/** The context of the SCREENS_B §15 audit rows. */
const AUDIT_CONTEXT = { entity: "AVM-US", book: "ASC606", period: "FY2026-P09" } as const;

/**
 * Routes opened in that context, written into the address in SCR-URL-20 order. SF-04 reads the
 * address alone: without an entity it asks the revenue waterfall for every entity in scope, and the
 * entities of the demo world keep two fiscal calendars, so the API refuses that run (04 T-RPT-01
 * rule 6; PRD ERR-97; item RPT-PERIOD-KEY-CALENDARS-1). The refusal is the true answer to that
 * request and leaves no grid to drive, so the screen is crawled for one entity, as the routes that
 * name `:entity`, `:book` and `:period` are.
 */
const IN_CONTEXT: ReadonlySet<string> = new Set(["SF-04"]);
const CONTEXT_SEARCH = `entity=${AUDIT_CONTEXT.entity}&period=${AUDIT_CONTEXT.period}&book=${AUDIT_CONTEXT.book}`;

type Found = Readonly<Record<string, string>>;

interface Seed {
  /** The path parameters this entry supplies. */
  readonly params: readonly string[];
  /** Only for routes under this path, where one parameter name serves several records. */
  readonly under?: string;
  /** The record by its business key (DG-E2E-09); null when the world holds none. */
  readonly find: (api: APIRequestContext, found: Found) => Promise<Found | null>;
}

interface Listed<Item> {
  readonly items: readonly Item[];
}

async function list<Item>(
  api: APIRequestContext,
  path: string,
  params: Readonly<Record<string, string | number | boolean>> = {},
): Promise<readonly Item[]> {
  return (await json<Listed<Item>>(await api.get(path, { params: { limit: 200, ...params } })))
    .items;
}

/** PRD §2.5 K-01, the contract of the SCREENS §4 sample world. */
const K01 = "SF-ORD-10001";
/** PRD §2.5 K-02, the contract of the SCREENS §7 sample world. */
const K02 = "SF-ORD-10002";
const K03 = "PRJ-CB-2026-01";

interface Versioned {
  readonly id: string;
  readonly code: string;
  readonly current_version: { readonly id: string } | null;
}

/** The seeded records the parameter routes open, each found by its business key. */
const SEEDS: readonly Seed[] = [
  {
    params: ["contractId"],
    find: async (api) => {
      const contracts = await list<{ readonly id: string; readonly external_id: string }>(
        api,
        "/api/v1/contracts",
        { q: K01 },
      );
      const contract = contracts.find((item) => item.external_id === K01);
      return contract === undefined ? null : { contractId: contract.id };
    },
  },
  {
    params: ["obligationId"],
    find: async (api, found) => {
      const obligations = await list<{ readonly id: string; readonly obligation_key: string }>(
        api,
        `/api/v1/contracts/${found.contractId ?? ""}/obligations`,
        { book: "ASC606" },
      );
      const obligation = obligations.find((item) => item.obligation_key === "O1");
      return obligation === undefined ? null : { obligationId: obligation.id };
    },
  },
  {
    // The modification the rows SF-07 of project screens leave on K-02 (BUILD_SPEC CTR-27) — a draft
    // they discard, so it reads Void; it belongs to K-02, so the entry answers the contract of the
    // route as well.
    params: ["modificationId"],
    find: async (api) => {
      const contracts = await list<{ readonly id: string; readonly external_id: string }>(
        api,
        "/api/v1/contracts",
        { q: K02 },
      );
      const contract = contracts.find((item) => item.external_id === K02);
      if (contract === undefined) {
        return null;
      }
      const modifications = await list<{
        readonly id: string;
        readonly reference: string | null;
      }>(api, `/api/v1/contracts/${contract.id}/modifications`);
      const left = modifications.find((item) => item.reference?.startsWith("CR-E2E-") === true);
      return left === undefined ? null : { contractId: contract.id, modificationId: left.id };
    },
  },
  {
    // The `EAC` element the rows SF-03:estimates of project screens add to K-03 (BUILD_SPEC CTR-25);
    // the element belongs to K-03, so the entry answers the contract of the route as well.
    params: ["estimateId"],
    find: async (api) => {
      const contracts = await list<{ readonly id: string; readonly external_id: string }>(
        api,
        "/api/v1/contracts",
        { q: K03 },
      );
      const contract = contracts.find((item) => item.external_id === K03);
      if (contract === undefined) {
        return null;
      }
      const estimates = await list<{ readonly id: string; readonly element_code: string }>(
        api,
        `/api/v1/contracts/${contract.id}/estimates`,
      );
      const element = estimates.find((item) => item.element_code === "EAC");
      return element === undefined ? null : { contractId: contract.id, estimateId: element.id };
    },
  },
  {
    // SF-05:reconciliation (RT-103): the path names the reconciliation's own entity, book and period —
    // another context answers "Reconciliation not found" — so this entry supplies all four, ahead of
    // the context entry below, for the one route under this path. The record is the current billing
    // to subledger reconciliation of AVM-DE Sep 2026, which the `screens` rows generate (BUILD_SPEC
    // CLO-25; the demo world seeds none).
    params: ["entity", "book", "period", "reconciliationId"],
    under: "/close/:entity/:book/:period/reconciliations/",
    find: async (api) => {
      const context = { entity: "AVM-DE", book: "ASC606", period: "FY2026-P09" };
      const reconciliations = await list<{ readonly id: string; readonly is_current: boolean }>(
        api,
        "/api/v1/reconciliations",
        { ...context, kind: "BILLING_TO_SUBLEDGER" },
      );
      const current = reconciliations.find((item) => item.is_current);
      return current === undefined ? null : { ...context, reconciliationId: current.id };
    },
  },
  {
    params: ["entity", "book", "period"],
    find: () => Promise.resolve({ ...AUDIT_CONTEXT }),
  },
  {
    params: ["runId"],
    under: "/journals/",
    find: async (api) => ({ runId: await ensureJournalRun(api) }),
  },
  {
    params: ["runId"],
    under: "/policies/ssp-calculator/",
    find: async (api) => ({ runId: await ensurePoolRun(api) }),
  },
  {
    // The report run that started last among those the persona may see (04 API-R-41).
    params: ["runId"],
    under: "/reports/runs/",
    find: async (api) => {
      const [run] = await list<{ readonly id: string }>(api, "/api/v1/report-runs");
      return run === undefined ? null : { runId: run.id };
    },
  },
  {
    // 04 T-RPT-01 RPT-03, a report of two sections.
    params: ["reportCode"],
    find: () => Promise.resolve({ reportCode: "contract_balance_rollforward" }),
  },
  {
    params: ["importId", "step"],
    find: async (api) => {
      const imports = await list<{ readonly id: string; readonly status: string }>(
        api,
        "/api/v1/imports",
        { status: "COMMITTED" },
      );
      const [committed] = imports;
      return committed === undefined ? null : { importId: committed.id, step: "committed" };
    },
  },
  {
    params: ["exceptionId"],
    find: async (api) => {
      const [exception] = await list<{ readonly id: string }>(api, "/api/v1/exceptions", {
        code: "PROGRESS_OVER_DELIVERY",
      });
      return exception === undefined ? null : { exceptionId: exception.id };
    },
  },
  {
    params: ["migrationId"],
    find: async (api) => {
      const [migration] = await list<{ readonly id: string }>(api, "/api/v1/migrations");
      return migration === undefined ? null : { migrationId: migration.id };
    },
  },
  {
    params: ["requestId"],
    find: async (api) => {
      const [request] = await list<{ readonly id: string }>(api, "/api/v1/approvals", {
        sort: "submitted_at",
      });
      return request === undefined ? null : { requestId: request.id };
    },
  },
  {
    params: ["templateId", "versionId"],
    under: "/policies/templates/",
    find: async (api) => {
      const templates = await list<Versioned>(api, "/api/v1/pob-templates", { sort: "code" });
      const template = templates.find((item) => item.code === "TPL-SUB-DAILY");
      const version = template?.current_version ?? null;
      return template === undefined || version === null
        ? null
        : { templateId: template.id, versionId: version.id };
    },
  },
  {
    params: ["ruleSetId", "versionId"],
    under: "/policies/rule-sets/",
    find: async (api) => {
      const sets = await list<Versioned>(api, "/api/v1/rule-sets", { q: "APPROVAL_ROUTING" });
      const set = sets.find((item) => item.code === "APPROVAL_ROUTING");
      const version = set?.current_version ?? null;
      return set === undefined || version === null
        ? null
        : { ruleSetId: set.id, versionId: version.id };
    },
  },
  {
    params: ["policyId"],
    find: async (api) => {
      const [policy] = await list<{ readonly id: string }>(api, "/api/v1/policies", {
        category: "ACCOUNTING_POLICY",
        scope: "TENANT",
        status: "PUBLISHED",
      });
      return policy === undefined ? null : { policyId: policy.id };
    },
  },
  {
    params: ["bookId", "versionId"],
    under: "/policies/ssp-books/",
    find: async (api) => {
      const book = await sspBookByCode(api, "US-LIST");
      return book.current_version === null
        ? null
        : { bookId: book.id, versionId: book.current_version.id };
    },
  },
  {
    params: ["mappingVersionId"],
    find: async (api) => {
      const [mapping] = await list<{ readonly id: string }>(api, "/api/v1/account-mappings", {
        status: "PUBLISHED",
        sort: "-version_no",
      });
      return mapping === undefined ? null : { mappingVersionId: mapping.id };
    },
  },
  {
    params: ["customerId"],
    find: async (api) => {
      const contracts = await list<{
        readonly external_id: string;
        readonly customer: { readonly id: string };
      }>(api, "/api/v1/contracts", { q: K01 });
      const contract = contracts.find((item) => item.external_id === K01);
      return contract === undefined ? null : { customerId: contract.customer.id };
    },
  },
  {
    params: ["productId"],
    find: async (api) => {
      const products = await list<{ readonly id: string; readonly code: string }>(
        api,
        "/api/v1/products",
        { q: "AVM-PLAT-100" },
      );
      const product = products.find((item) => item.code === "AVM-PLAT-100");
      return product === undefined ? null : { productId: product.id };
    },
  },
  {
    // The trace of the K-01 O1 revenue line of Sep 2026 (SCREENS §6.5 sample world).
    params: ["calcTraceId"],
    find: async (api) => {
      const contracts = await list<{ readonly id: string; readonly external_id: string }>(
        api,
        "/api/v1/contracts",
        { q: K01 },
      );
      const contract = contracts.find((item) => item.external_id === K01);
      if (contract === undefined) {
        return null;
      }
      const lines = await list<{
        readonly id: string;
        readonly obligation_key: string | null;
        readonly line_type: string;
      }>(api, "/api/v1/schedule-lines", {
        contract: contract.id,
        schedule_kind: "REVENUE",
        book: "ASC606",
        from_period: "FY2026-P09",
        to_period: "FY2026-P09",
      });
      const line = lines.find(
        (item) => item.obligation_key === "O1" && item.line_type === "NORMAL",
      );
      if (line === undefined) {
        return null;
      }
      const explained = await json<{ readonly calc_trace_id: string }>(
        await api.get(`/api/v1/explain/schedule_line/${line.id}/amount`, {
          params: { period: "FY2026-P09", book: "ASC606" },
        }),
      );
      return { calcTraceId: explained.calc_trace_id };
    },
  },
  {
    params: ["membershipId"],
    find: async (api) => {
      // API-S-User: `id` is the membership.
      const users = await list<{ readonly id: string; readonly email: string }>(
        api,
        "/api/v1/users",
        { q: personaEmail("maya") },
      );
      const user = users.find((item) => item.email === personaEmail("maya"));
      return user === undefined ? null : { membershipId: user.id };
    },
  },
  {
    params: ["reviewId"],
    find: async (api) => {
      const [review] = await list<{ readonly id: string }>(api, "/api/v1/access-reviews");
      return review === undefined ? null : { reviewId: review.id };
    },
  },
  {
    // The verification that finished last (SCREENS_B §6.4).
    params: ["verificationId"],
    find: async (api) => {
      const [verification] = await list<{ readonly id: string }>(
        api,
        "/api/v1/audit-events/verifications",
      );
      return verification === undefined ? null : { verificationId: verification.id };
    },
  },
  {
    params: ["connectionId"],
    find: async (api) => {
      const [connection] = await list<{ readonly id: string }>(api, "/api/v1/integrations");
      return connection === undefined ? null : { connectionId: connection.id };
    },
  },
  {
    // A run of that connection (04 API-R-45 `GET /sync-runs?connection=<id>`).
    params: ["syncRunId"],
    find: async (api, found) => {
      const [run] = await list<{ readonly id: string }>(api, "/api/v1/sync-runs", {
        connection: found.connectionId ?? "",
      });
      return run === undefined ? null : { syncRunId: run.id };
    },
  },
  {
    // SCREENS_B §5.5 (RT-107): the dashboards are a closed set of codes, not records of the world.
    params: ["dashboardCode"],
    find: () => Promise.resolve({ dashboardCode: "revenue" }),
  },
];

function seedOf(route: RouterRoute, param: string): Seed | undefined {
  return SEEDS.find(
    (seed) =>
      seed.params.includes(param) &&
      (seed.under === undefined || route.path.startsWith(seed.under)),
  );
}

// The tables name routes of the router, and every redirect and parameter is accounted for: a stale or
// missing entry stops the project before any page opens.
const IDS = new Set(ROUTES.map((route) => route.id));
for (const id of [
  ...Object.keys(PERSONA_OF),
  ...Object.keys(NOT_OPENED),
  ...Object.keys(NOT_SEEDED),
  ...Object.keys(LEFT_BY_SCREENS),
  ...Object.keys(LANDS_ON),
  ...Object.values(LANDS_ON),
]) {
  if (!IDS.has(id)) {
    throw new Error(`crawl.spec.ts names the route ${id}, which the router does not hold`);
  }
}
for (const route of ROUTES) {
  if (screenRowOf(route, ROWS) === undefined) {
    throw new Error(`${route.id} ${route.path} has no row in SCREENS §0.4`);
  }
  if (route.loader && LANDS_ON[route.id] === undefined) {
    throw new Error(`${route.id} redirects in its loader; name its target in LANDS_ON`);
  }
  const unseeded = route.params.filter((param) => seedOf(route, param) === undefined);
  if (unseeded.length > 0 && NOT_OPENED[route.id] === undefined) {
    throw new Error(
      `${route.id} ${route.path}: SEEDS holds no record for :${unseeded.join(", :")}`,
    );
  }
}

const held = new Map<Persona, readonly string[]>();

/** `GET /me` permissions of a persona, read once per worker. */
async function permissionsOf(personas: Personas, persona: Persona): Promise<readonly string[]> {
  let known = held.get(persona);
  if (known === undefined) {
    const page = await personas.page(persona);
    known = (
      await json<{ readonly permissions: readonly string[] }>(await page.request.get("/api/v1/me"))
    ).permissions;
    held.set(persona, known);
    await page.close();
  }
  return known;
}

/**
 * The personas that open a route: the one named for it, else the first that holds every permission
 * of its SCREENS §0.4 row, else the first holder of each permission in turn (a screen whose panes
 * take different permissions, as SF-16:developer).
 */
async function personasFor(
  personas: Personas,
  route: RouterRoute,
  permissions: readonly string[],
): Promise<readonly Persona[]> {
  const named = PERSONA_OF[route.id];
  if (named !== undefined) {
    return [named];
  }
  if (permissions.length === 0) {
    return [ORDER[0] ?? "maya"];
  }
  for (const persona of ORDER) {
    const has = await permissionsOf(personas, persona);
    if (permissions.every((permission) => has.includes(permission))) {
      return [persona];
    }
  }
  const chosen: Persona[] = [];
  for (const permission of permissions) {
    let holder: Persona | undefined;
    for (const persona of ORDER) {
      if ((await permissionsOf(personas, persona)).includes(permission)) {
        holder = persona;
        break;
      }
    }
    if (holder === undefined) {
      throw new Error(`${route.id}: no persona holds ${permission}`);
    }
    if (!chosen.includes(holder)) {
      chosen.push(holder);
    }
  }
  return chosen;
}

interface Visit {
  readonly persona: string;
  readonly url: string;
  readonly landed: string;
  readonly apiRequests: number;
  readonly sorted: readonly string[];
  readonly filtered: readonly string[];
  readonly panes: readonly string[];
  readonly notDriven: readonly string[];
  readonly ms: number;
}

interface RouteRecord {
  readonly route: string;
  readonly path: string;
  readonly row: string;
  readonly notOpened: string | null;
  readonly visits: readonly Visit[];
  readonly findings: readonly Finding[];
}

function save(testInfo: TestInfo, record: RouteRecord): Promise<void> {
  const directory = join(RESULTS_DIR, "crawl");
  mkdirSync(directory, { recursive: true });
  const body = `${JSON.stringify(record, null, 2)}\n`;
  writeFileSync(join(directory, `${normaliseKey(record.route)}.json`), body);
  return testInfo.attach("crawl", { body, contentType: "application/json" });
}

/** Opens one URL on a signed-in or signed-out page and drives what the shared components offer. */
async function visit(
  page: Page,
  route: RouterRoute,
  url: string,
  persona: string,
  findings: Finding[],
  arrive: () => Promise<unknown>,
): Promise<Visit> {
  const started = Date.now();
  const watch = new Watch(page);
  const notDriven: string[] = [];
  const after = async (step: string): Promise<void> => {
    await watch.settle();
    // A failed query is asked again by its retry: one finding for the same answer of a step.
    const seen = new Set([...watch.drain(ALLOWED).found, ...(await inspect(page))]);
    findings.push(...[...seen].map((what) => ({ step: `${persona}: ${step}`, what })));
  };
  const step = { after, note: (text: string) => notDriven.push(text) };

  // An action that cannot complete fails by name instead of using up the time of the test.
  page.setDefaultTimeout(ACTION_MS);
  await arrive();
  await after("open");
  const landed = routeAt(new URL(page.url()).pathname, ROUTES)?.id ?? "";
  const expected = LANDS_ON[route.id] ?? route.id;
  if (landed !== expected) {
    findings.push({
      step: `${persona}: open`,
      what: `landed on ${landed} ${new URL(page.url()).pathname}, not on ${expected}`,
    });
  }
  const sorted: string[] = [];
  const filtered: string[] = [];
  const panes: string[] = [];
  if (route.path === "*") {
    await expect(notFound(page)).toBeVisible();
  } else if (LANDS_ON[route.id] !== undefined) {
    // The screen it lands on is driven by its own route.
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  } else {
    if ((await notFound(page).count()) > 0) {
      findings.push({ step: `${persona}: open`, what: '"Page not found" rendered' });
    }
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
    const driven = new Set<string>();
    sorted.push(...(await driveGrids(page, step, driven)));
    filtered.push(...(await driveFilters(page, step, driven)));
    // DS-CMP-07 panel tabs of the first level; a tab list a pane brings with it is not opened.
    for (const tab of await panelTabs(page)) {
      await page.locator(`[id="${tab.id}"]`).click();
      await after(`pane "${tab.name}"`);
      panes.push(tab.name);
      sorted.push(...(await driveGrids(page, step, driven)));
      filtered.push(...(await driveFilters(page, step, driven)));
    }
  }
  return {
    persona,
    url,
    landed,
    apiRequests: watch.requests,
    sorted,
    filtered,
    panes,
    notDriven,
    ms: Date.now() - started,
  };
}

test.describe("crawl: the watch", () => {
  test("does not wait for a request of a document that a navigation replaced", async ({ page }) => {
    // While a route of the context intercepts requests (support/network.ts), Chromium reports no end
    // for a request that is in flight when its document is replaced: no `requestfailed`, no
    // `requestfinished`, no response. A persona that signs in within its test lands on Home, and a
    // read Home started just before the route under test opened kept the watch waiting for 45 s
    // (main 303f2f47, SF-12:delegations; the trace of SF-22:password-change, 2026-10-01).
    let release: () => void = () => undefined;
    const answered = new Promise<void>((resolve) => {
      release = resolve;
    });
    const left = "**/api/v1/session?left=in-flight";
    // Held at the route until the next document has loaded, so that it cannot end before then.
    await page.route(left, async (route) => {
      await answered;
      await route.continue().catch(() => undefined);
    });
    await page.goto("/sign-in");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const watch = new Watch(page);
    await page.evaluate(() => {
      void fetch("/api/v1/session?left=in-flight").catch(() => undefined);
    });
    await expect.poll(() => watch.requests, "the watch saw the request start").toBe(1);

    await page.goto("/sign-in");
    release();
    await watch.settle();
    await page.unroute(left);
  });
});

test.describe("crawl: every route of the router opens, sorts and filters without an error", () => {
  test.describe.configure({ timeout: 300_000 });

  for (const route of ROUTES) {
    const row = screenRowOf(route, ROWS);
    if (row === undefined) {
      continue;
    }
    test(`${route.id} ${route.path}`, async ({ personas, page: signedOut }, testInfo) => {
      const findings: Finding[] = [];
      const visits: Visit[] = [];
      let notOpened: string | null = NOT_OPENED[route.id] ?? null;

      if (notOpened !== null) {
        // Listed, never silently skipped: the reason is the record of this route.
      } else if (row.access === "public") {
        visits.push(
          await visit(signedOut, route, route.path, "signed out", findings, () =>
            signedOut.goto(route.path),
          ),
        );
      } else if (row.access.startsWith("password step completed")) {
        // RT-02: reached between the two steps of a sign-in, as the SF-22:mfa-challenge row does.
        visits.push(
          await visit(signedOut, route, route.path, "marcus, password step", findings, () =>
            passwordStep(signedOut, "marcus"),
          ),
        );
      } else {
        for (const persona of await personasFor(personas, route, row.permissions)) {
          const page = await personas.page(persona);
          let found: Found = {};
          let missing: string | null = null;
          for (const param of route.params) {
            if (found[param] === undefined && missing === null) {
              const record = await seedOf(route, param)?.find(page.request, found);
              if (record === undefined || record === null) {
                missing = param;
              } else {
                expect(record[param], `the seed of :${param} names a record`).toMatch(/\S/);
                found = { ...found, ...record };
              }
            }
          }
          const reason = NOT_SEEDED[route.id];
          const left = LEFT_BY_SCREENS[route.id];
          if (missing !== null && left !== undefined) {
            // The record of an earlier project: it must be there when that project ran.
            expect(WHOLE_GATE, `${route.id}: no record for :${missing}, although ${left}`).toBe(
              false,
            );
            notOpened = left;
            continue;
          }
          if (missing !== null) {
            // The world holds no record: allowed only for the routes that say so.
            expect(reason, `${route.id}: no record for :${missing} as ${persona}`).toBeDefined();
            notOpened = reason ?? null;
            continue;
          }
          expect(reason, `${route.id} is in NOT_SEEDED and the world now holds its record`).toBe(
            undefined,
          );
          const path =
            route.path === "*"
              ? "/crawl/no-such-page"
              : route.path.replace(/:([A-Za-z]+)/g, (_, name: string) =>
                  encodeURIComponent(found[name] ?? ""),
                );
          const url = IN_CONTEXT.has(route.id) ? `${path}?${CONTEXT_SEARCH}` : path;
          visits.push(await visit(page, route, url, persona, findings, () => page.goto(url)));
        }
      }

      const record = {
        route: route.id,
        path: route.path,
        row: `${row.rt} ${row.access}`,
        notOpened,
        visits,
        findings,
      };
      await save(testInfo, record);
      expect(
        findings.map((finding) => `${finding.step}: ${finding.what}`),
        `${route.id} ${route.path}`,
      ).toEqual([]);
      expect(visits.length > 0 || notOpened !== null, `${route.id} was opened or is listed`).toBe(
        true,
      );
    });
  }
});
