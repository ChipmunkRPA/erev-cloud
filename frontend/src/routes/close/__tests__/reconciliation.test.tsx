// @vitest-environment jsdom
// SF-05:reconciliations and SF-05:reconciliation (BUILD_SPEC CLO-25; SCREENS_B §2.1, §2.2, §0.4 E-59;
// SCREENS SCR-PERM-02, SCR-PERM-05; PRD SM-09, ACT-34, ACT-45, J-13.10 to J-13.12, J-23.9; 04 API-R-40
// §16.8; supervisor rulings R-54 (b), (c)): the period's current reconciliations with their chips and
// sign-offs, generation as a job, the itemised differences with their classification and explanation,
// the preparer's and the reviewer's sign-offs with the step-up resend, the reopen, and the read-only
// states (superseded, certified). API answers are contract fakes of 04 API-S-Reconciliation,
// API-S-ReconciliationItem and API-S-Job.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../../app/router";
import type { PeriodCockpit } from "../../../lib/api/queries/periods";
import type {
  ReconciliationItem,
  ReconciliationOut,
  ReconciliationSignoff,
} from "../../../lib/api/queries/reconciliations";
import type { Me } from "../../../lib/api/queries/me";
import type { Period } from "../../../lib/api/queries/tenant";
import { hasMessage } from "../../../lib/i18n/t";
import messages from "../../../messages/en.json";
import { installMemoryStorage, renderApp, signedInMe, signedInSession } from "../../../test/app";
import { installGridViewport } from "../../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import {
  describedBy,
  RECORD_CHANGED,
  REFUSAL_REFERENCE,
  REFUSAL_TITLE,
  refusedWith,
} from "../../../test/refusals";

installMswServer();
installMemoryStorage();
installGridViewport();
// The cockpit frame reads the periods, then the cockpit, before a tab renders.
configure({ asyncUtilTimeout: 5000 });

const JSDOM_WIDTH = window.innerWidth;

function setViewportWidth(px: number): void {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: px });
}

// The 1440 px wireframes are the default; one case reads the 1280 px column set.
beforeEach(() => {
  setViewportWidth(1440);
});

afterEach(() => {
  cleanup();
  setViewportWidth(JSDOM_WIDTH);
});

const LIST_PATH = "/close/AVM-US/ASC606/FY2026-P09/reconciliations";
const CONTEXT = "?entity=AVM-US&period=FY2026-P09&book=ASC606";
const STATE_ID = "7c1d2e3f-4a5b-4c6d-8e7f-000000000909";
const REC_OLD = "b1a2c3d4-0000-4000-8000-000000000040";
const REC_BILLING = "b1a2c3d4-0000-4000-8000-000000000041";
const REC_GL = "b1a2c3d4-0000-4000-8000-000000000042";
const REC_NEW = "b1a2c3d4-0000-4000-8000-000000000043";
const ITEM_GL = "c1a2c3d4-0000-4000-8000-000000000001";
const ITEM_INVOICE = "c1a2c3d4-0000-4000-8000-000000000002";
const JOB_ID = "5e4d3c2b-1a0f-4e9d-8c7b-6a5f4e3d2c41";
const EXPLANATION =
  "Manual accrual posted in NetSuite by AP; reversed on 01 Oct 2026 by JE-NS-88410.";

const AVM_US = {
  id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000001",
  code: "AVM-US",
  name: "Avenmoor Inc. (Demo)",
};
const MAYA_ACTOR = {
  id: "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a",
  display_name: "Maya Chen",
  kind: "USER" as const,
};
const PRIYA_ACTOR = {
  id: "4d3c2b1a-0f9e-4d8c-9b7a-6f5e4d3c2b1a",
  display_name: "Priya Raman",
  kind: "USER" as const,
};

function persona(
  actor: { readonly id: string; readonly display_name: string },
  email: string,
  permissions: readonly string[],
  overrides: Partial<Me> = {},
): Me {
  return signedInMe({
    user: { id: actor.id, email, display_name: actor.display_name, status: "ACTIVE" },
    permissions: [...permissions],
    ...overrides,
  });
}

/** Revenue Accountant: `recon.prepare` (PRD ACT-33) and, for a trial balance file, `import.upload`. */
const MAYA = persona(MAYA_ACTOR, "maya@example.test", [
  "contract.read",
  "config.read",
  "period.close",
  "recon.prepare",
  "import.upload",
]);
/** Revenue Reviewer: `recon.signoff` (PRD ACT-34). */
const PRIYA = persona(PRIYA_ACTOR, "priya@example.test", [
  "contract.read",
  "config.read",
  "recon.signoff",
]);
/** Integration Admin: `integration.manage` and neither reconciliation permission (SoD-7). */
const NIKHIL = persona(
  { id: "2b3c4d5e-6f70-4a81-9b92-a3b4c5d6e7f8", display_name: "Nikhil Rao" },
  "nikhil@example.test",
  ["contract.read", "config.read", "integration.manage"],
);
/** A viewer without a command permission. */
const ROBERT = persona(
  { id: "1f2e3d4c-5b6a-4978-8a9b-0c1d2e3f4a5b", display_name: "Robert Lang" },
  "robert@example.test",
  ["contract.read", "config.read"],
);

function money(amount: string, currency = "USD") {
  return { amount, currency };
}

function period(overrides: Partial<Period> = {}): Period {
  return {
    id: STATE_ID,
    entity: AVM_US,
    book: "ASC606",
    period: {
      id: "1c2d3e4f-5a6b-4c7d-8e9f-000000000009",
      period_key: "FY2026-P09",
      name: "Sep 2026",
      fiscal_year: 2026,
      period_no: 9,
      quarter_no: 3,
      start_date: "2026-09-01",
      end_date: "2026-09-30",
    },
    state: "open",
    state_changed_at: "2026-09-01T00:00:00Z",
    is_first_open: true,
    current_lock: null,
    blockers: {
      approvals_pending: 0,
      batches_unacknowledged: 0,
      batches_unexported: 0,
      exceptions_open: 0,
      groups_dirty: 0,
      holds_open: 0,
      interface_failures: 0,
      jobs_failed: 0,
      judgements_unreviewed: 0,
      manual_adjustments_pending: 0,
      reconciliations_unsigned: 0,
      unmapped_products: 0,
    },
    close_run: null,
    row_version: 3,
    ...overrides,
  };
}

function cockpit(state: Period): PeriodCockpit {
  return {
    period: state,
    checklist: [],
    journal_preview: {
      debit_functional: money("0.00"),
      credit_functional: money("0.00"),
      difference_functional: money("0.00"),
      balanced: true,
      by_account_role: [],
    },
    kpis: {
      days_to_close_last_three: [],
      reconciliations_reviewed: { reviewed: 0, required: 2 },
    },
    derived_blockers: [],
    pending_requests: [],
  };
}

function signoff(
  role: ReconciliationSignoff["role"],
  signer: ReconciliationSignoff["signer"],
  signedAt: string,
): ReconciliationSignoff {
  return {
    id: `d1a2c3d4-0000-4000-8000-00000000000${role === "PREPARER" ? "1" : "2"}`,
    role,
    signer,
    statement:
      role === "PREPARER"
        ? "I prepared this reconciliation and explained every difference above the threshold."
        : "I reviewed this reconciliation, its differences and their explanations.",
    subject_content_sha256: "9f".repeat(32),
    signed_at: signedAt,
  };
}

function reconciliation(overrides: Partial<ReconciliationOut> = {}): ReconciliationOut {
  return {
    id: REC_BILLING,
    reconciliation_no: "REC-000041",
    kind: "BILLING_TO_SUBLEDGER",
    entity: AVM_US,
    book: "ASC606",
    period: {
      id: "1c2d3e4f-5a6b-4c7d-8e9f-000000000009",
      period_key: "FY2026-P09",
      name: "Sep 2026",
      start_date: "2026-09-01",
      end_date: "2026-09-30",
    },
    status: "DRAFT",
    is_current: true,
    as_of_known_at: "2026-09-12T15:20:00Z",
    period_lock_id: null,
    source_file_id: null,
    sync_run_id: null,
    report_run_id: null,
    totals: [
      {
        account_code: null,
        currency: "USD",
        subledger_amount: money("125000.00"),
        source_amount: money("125000.00"),
        difference: money("0.00"),
      },
    ],
    // API-S-Reconciliation `summary`: the key figures of each currency, summed by the server.
    summary: [
      {
        currency: "USD",
        account_count: 0,
        subledger_amount: money("125000.00"),
        source_amount: money("125000.00"),
        difference: money("0.00"),
        not_stated_count: 0,
      },
    ],
    trial_balance: null,
    gl_connections: [],
    variance_count: 0,
    unexplained_other_amount: null,
    auto_certify_rule: null,
    certified_at: null,
    signoffs: [],
    created_by: MAYA_ACTOR,
    created_at: "2026-09-12T15:20:00Z",
    updated_at: "2026-09-12T15:20:00Z",
    row_version: 1,
    ...overrides,
  };
}

/** The GL connection of the entity (API-S-Reconciliation `gl_connections`). */
const CONNECTION = { id: "a7b8c9d0-0000-4000-8000-000000000011", name: "NetSuite (mock)" };

/** A generated subledger-to-GL draft before its trial balance: no source, nothing compared yet. */
function awaitingTrialBalance(): ReconciliationOut {
  return generalLedger({
    sync_run_id: null,
    totals: [],
    summary: [],
    variance_count: 0,
    trial_balance: null,
    gl_connections: [CONNECTION],
  });
}

/** API-S-Reconciliation `trial_balance`: the latest `attach-trial-balance` request and its job. */
function attachRequest(
  source: "ADAPTER" | "FILE",
  state: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED",
  attachedAt: string | null = null,
  problem: NonNullable<ReconciliationOut["trial_balance"]>["job"]["problem"] = null,
): NonNullable<ReconciliationOut["trial_balance"]> {
  return {
    source,
    integration_connection: source === "ADAPTER" ? CONNECTION : null,
    file: null,
    job: {
      id: JOB_ID,
      state,
      created_by: MAYA_ACTOR,
      created_at: "2026-09-12T15:19:40Z",
      finished_at: state === "QUEUED" || state === "RUNNING" ? null : "2026-09-12T15:20:00Z",
      problem,
    },
    attached_at: attachedAt,
  };
}

/** J-13.11: subledger to GL with the 250.00 direct GL entry on account 2100. */
function generalLedger(overrides: Partial<ReconciliationOut> = {}): ReconciliationOut {
  return reconciliation({
    id: REC_GL,
    reconciliation_no: "REC-000042",
    kind: "SUBLEDGER_TO_GL",
    sync_run_id: "e1a2c3d4-0000-4000-8000-000000000001",
    totals: [
      {
        account_code: "2100",
        currency: "USD",
        subledger_amount: money("-103430.14"),
        source_amount: money("-103180.14"),
        difference: money("250.00"),
      },
    ],
    summary: [
      {
        currency: "USD",
        account_count: 1,
        subledger_amount: money("-103430.14"),
        source_amount: money("-103180.14"),
        difference: money("250.00"),
        not_stated_count: 0,
      },
    ],
    // The trial balance was pulled through the entity's GL connection (J-13.11).
    trial_balance: attachRequest("ADAPTER", "SUCCEEDED", "2026-09-12T15:20:00Z"),
    variance_count: 1,
    ...overrides,
  });
}

function directEntry(overrides: Partial<ReconciliationItem> = {}): ReconciliationItem {
  return {
    id: ITEM_GL,
    reconciliation_id: REC_GL,
    item_kind: "DIRECT_GL_ENTRY",
    account_code: "2100",
    contract: null,
    invoice_number: null,
    gl_document_reference: "JE-NS-88121",
    currency: "USD",
    subledger_amount: money("0.00"),
    source_amount: money("250.00"),
    difference: money("250.00"),
    is_high_risk: true,
    explanation: null,
    resolved_at: null,
    resolved_by: null,
    row_version: 1,
    ...overrides,
  };
}

function unmatchedInvoice(overrides: Partial<ReconciliationItem> = {}): ReconciliationItem {
  return {
    id: ITEM_INVOICE,
    reconciliation_id: REC_BILLING,
    item_kind: "UNMATCHED_SOURCE",
    account_code: null,
    contract: { id: "f1a2c3d4-0000-4000-8000-000000000001", external_id: "NS-SO-US-1001" },
    invoice_number: "INV-US-9001",
    gl_document_reference: null,
    currency: "USD",
    subledger_amount: null,
    source_amount: money("100000.00"),
    difference: money("100000.00"),
    is_high_risk: false,
    explanation: null,
    resolved_at: null,
    resolved_by: null,
    row_version: 1,
    ...overrides,
  };
}

interface World {
  readonly state?: Period;
  /** Every generation of the period, as `GET /reconciliations` lists them. */
  readonly generations?: readonly ReconciliationOut[];
  readonly items?: Readonly<Record<string, readonly ReconciliationItem[]>>;
}

/** Every `GET /reconciliations` the screens sent, by its search parameters. */
type ListReads = URLSearchParams[];

function serve(world: World = {}, listReads: ListReads = []) {
  const state = world.state ?? period();
  const generations = world.generations ?? [];
  const empty = () => HttpResponse.json({ items: [], next_cursor: null });
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), empty),
    http.get(apiUrl("/api/v1/entities"), empty),
    http.get(apiUrl("/api/v1/books"), empty),
    http.get(apiUrl("/api/v1/jobs"), empty),
    http.get(apiUrl("/api/v1/journal-runs"), empty),
    http.get(apiUrl("/api/v1/approvals"), empty),
    http.get(apiUrl("/api/v1/exceptions"), () =>
      HttpResponse.json(
        { items: [], next_cursor: null },
        { headers: { "X-Erev-Total-Count": "0" } },
      ),
    ),
    http.get(apiUrl("/api/v1/currencies"), () =>
      HttpResponse.json({
        items: [
          { code: "USD", name: "US dollar", minor_unit: 2, numeric_code: "840", is_active: true },
          { code: "EUR", name: "Euro", minor_unit: 2, numeric_code: "978", is_active: true },
        ],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/periods"), () =>
      HttpResponse.json({ items: [state], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/periods/:periodId/cockpit"), () => HttpResponse.json(cockpit(state))),
    http.get(apiUrl("/api/v1/reconciliations"), ({ request }) => {
      const params = new URL(request.url).searchParams;
      listReads.push(params);
      // API-R-40: the bool filter `is_current`; without it every generation.
      const wanted = params.get("is_current");
      return HttpResponse.json({
        items: generations.filter(
          (item) => wanted === null || item.is_current === (wanted === "true"),
        ),
        next_cursor: null,
      });
    }),
    http.get(apiUrl("/api/v1/reconciliations/:reconciliationId"), ({ params }) => {
      const found = generations.find((item) => item.id === String(params.reconciliationId));
      return found === undefined
        ? problemResponse("not-found", 404, "Not found")
        : HttpResponse.json(found, { headers: { ETag: `"r${String(found.row_version)}"` } });
    }),
    http.get(apiUrl("/api/v1/reconciliations/:reconciliationId/items"), ({ params }) =>
      HttpResponse.json({
        items: world.items?.[String(params.reconciliationId)] ?? [],
        next_cursor: null,
      }),
    ),
  );
}

function detailPath(reconciliationId: string): string {
  return `${LIST_PATH}/${reconciliationId}`;
}

function open(path: string, me: Me) {
  return renderApp(path, { me, screenRoutes: SCREEN_ROUTES });
}

async function differences(): Promise<HTMLElement> {
  return screen.findByRole("grid", { name: "Differences" });
}

/**
 * The `href` of a link once the page has written its context for the context pill (SCR-URL-01 to
 * SCR-URL-03): the write follows the first render, so a link read at once may still lack it.
 */
async function hrefOf(container: HTMLElement, name: string): Promise<string | null> {
  // Read again on every try: a breadcrumb item is keyed by its target, so the write replaces it.
  const link = () => within(container).getByRole("link", { name });
  await waitFor(() => {
    expect(link().getAttribute("href")).toContain("?entity=");
  });
  return link().getAttribute("href");
}

/** The DS-CMP-19 chip words of the record header whose `h1` reads `title`, in order. */
function headerChips(title: string): (string | null)[] {
  const header = screen.getByRole("region", { name: title });
  return Array.from(header.querySelectorAll("span[data-tone]"), (chip) => chip.textContent);
}

const HERE = dirname(fileURLToPath(import.meta.url));

/** 04 T-CLS-07 `item_kind` as the API document states it (`docs/api/openapi.json`), in its order. */
function apiItemKinds(): readonly ReconciliationItem["item_kind"][] {
  const file = resolve(HERE, "../../../../../docs/api/openapi.json");
  const document = JSON.parse(readFileSync(file, "utf8")) as {
    readonly components: {
      readonly schemas: Readonly<
        Record<
          string,
          {
            readonly properties?: Readonly<
              Record<string, { readonly enum?: readonly ReconciliationItem["item_kind"][] }>
            >;
          }
        >
      >;
    };
  };
  return document.components.schemas.ReconciliationItemOut?.properties?.item_kind?.enum ?? [];
}

describe("SF-05:reconciliations", () => {
  it("lists the current reconciliation of each kind with chips, variances and sign-offs", async () => {
    const reads: ListReads = [];
    serve(
      {
        generations: [
          generalLedger({
            status: "PREPARED",
            signoffs: [signoff("PREPARER", MAYA_ACTOR, "2026-09-12T16:05:00Z")],
          }),
          reconciliation({
            status: "AUTO_CERTIFIED",
            auto_certify_rule: {
              rule_id: "a1a2c3d4-0000-4000-8000-000000000001",
              rule_key: "AUTO-REC-01",
              rule_set_code: "CLOSE-CONTROLS",
              rule_set_version_id: "a1a2c3d4-0000-4000-8000-000000000002",
              version_no: 1,
            },
          }),
          reconciliation({
            id: REC_OLD,
            reconciliation_no: "REC-000040",
            is_current: false,
            variance_count: 2,
            created_at: "2026-09-11T09:00:00Z",
          }),
        ],
      },
      reads,
    );
    open(LIST_PATH, MAYA);

    // The cockpit frame and its route tabs are shared by the tab (SCREENS_B §1).
    expect(
      await screen.findByRole("heading", { level: 1, name: "Close · AVM-US · Sep 2026 · ASC 606" }),
    ).toBeTruthy();
    const tabs = screen.getByRole("navigation", { name: "Close of Sep 2026" });
    expect(
      within(tabs).getByRole("link", { name: "Reconciliations" }).getAttribute("aria-current"),
    ).toBe("page");

    const grid = await screen.findByRole("grid", { name: "Reconciliations" });
    // The 1440 px wireframe's columns; the others stay in the column chooser.
    expect(
      within(grid)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["Number", "Kind", "Status", "Variances", "Preparer", "Reviewer"]);
    // One row per kind, the current generation only, billing first (E-58 order).
    const billing = await within(grid).findByTestId("SF-05-row-billing-to-subledger");
    const ledger = within(grid).getByTestId("SF-05-row-subledger-to-gl");
    expect(within(grid).getAllByRole("row")).toHaveLength(3);
    expect(billing.compareDocumentPosition(ledger) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // J-13.10: zero variance, auto-certified under the rule, prepared by the system.
    expect(await hrefOf(billing, "REC-000041")).toBe(`${LIST_PATH}/${REC_BILLING}${CONTEXT}`);
    expect(billing.textContent).toContain("Billing to subledger");
    expect(billing.textContent).toContain("Auto-certified");
    expect(billing.textContent).toContain("under AUTO-REC-01 v1");
    expect(billing.textContent).not.toContain("Difference");
    expect(billing.querySelector('[data-column="preparer"]')?.textContent).toBe("System");

    // J-13.11: prepared with one variance, so the second chip reads Difference.
    expect(ledger.textContent).toContain("Subledger to GL");
    expect(ledger.textContent).toContain("Prepared");
    expect(ledger.textContent).toContain("Difference");
    expect(ledger.querySelector('[data-column="variances"]')?.textContent).toBe("1");
    expect(ledger.querySelector('[data-column="preparer"]')?.textContent).toBe("Maya Chen");
    expect(ledger.querySelector('[data-column="reviewer"]')?.textContent).toContain("No value");

    // The superseded generation is not a row of the grid; it is listed as history.
    expect(within(grid).queryByText("REC-000040")).toBeNull();
    const toggle = screen.getByRole("button", { name: "Earlier generations (1)" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggle);
    const history = screen.getByRole("table", { name: "Earlier generations (1)" });
    expect(await hrefOf(history, "REC-000040")).toBe(`${LIST_PATH}/${REC_OLD}${CONTEXT}`);
    expect(history.textContent).toContain("Draft");

    // The route's ListSpec admits the filters and the sort the screen sends (API-R-40): the current
    // reconciliations for the grid, the replaced ones for the history.
    const sent = reads.map((params) => Object.fromEntries(params));
    for (const current of ["true", "false"]) {
      expect(sent).toContainEqual({
        entity: "AVM-US",
        book: "ASC606",
        period: "FY2026-P09",
        is_current: current,
        sort: "-created_at",
        limit: "200",
      });
    }
    expect(sent.every((params) => params.is_current !== undefined)).toBe(true);
  });

  it("merges Preparer and Reviewer into Sign-offs below 1440 px", async () => {
    setViewportWidth(1280);
    serve({
      generations: [
        generalLedger({
          status: "PREPARED",
          signoffs: [signoff("PREPARER", MAYA_ACTOR, "2026-09-12T16:05:00Z")],
        }),
      ],
    });
    open(LIST_PATH, MAYA);

    const grid = await screen.findByRole("grid", { name: "Reconciliations" });
    const ledger = await within(grid).findByTestId("SF-05-row-subledger-to-gl");
    // SCREENS_B §2.1, 1280 px wireframe: "Maya Chen · —" in one column.
    expect(
      within(grid)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["Number", "Kind", "Status", "Variances", "Sign-offs"]);
    const cell = ledger.querySelector('[data-column="signoffs"]');
    expect(cell?.textContent).toContain("Maya Chen");
    expect(cell?.textContent).toContain("No value");
  });

  it("generates a reconciliation as a job, then names it in a toast", async () => {
    const posted: { readonly key: string | null; readonly body: unknown }[] = [];
    const generations: ReconciliationOut[] = [];
    serve({ generations });
    server.use(
      http.post(apiUrl("/api/v1/reconciliations"), async ({ request }) => {
        posted.push({ key: request.headers.get("Idempotency-Key"), body: await request.json() });
        return HttpResponse.json(
          { id: JOB_ID, kind: "RECONCILIATION_GENERATE", state: "QUEUED" },
          {
            status: 202,
            headers: {
              Location: `/api/v1/jobs/${JOB_ID}`,
              "X-Erev-Reconciliation-Id": REC_NEW,
            },
          },
        );
      }),
      http.get(apiUrl("/api/v1/jobs/:jobId"), () => {
        // The job inserts the reconciliation before it succeeds.
        if (generations.length === 0) {
          generations.push(reconciliation({ id: REC_NEW, reconciliation_no: "REC-000043" }));
        }
        return HttpResponse.json({
          id: JOB_ID,
          kind: "RECONCILIATION_GENERATE",
          state: "SUCCEEDED",
          progress: { done: 0, total: null },
          created_at: "2026-09-12T15:20:00Z",
          created_by: MAYA_ACTOR,
          started_at: "2026-09-12T15:20:01Z",
          finished_at: "2026-09-12T15:20:02Z",
          problem: null,
          result: { href: `/api/v1/reconciliations/${REC_NEW}`, counts: { variances: 0 } },
        });
      }),
    );
    open(LIST_PATH, MAYA);

    // SCR-ST-03 with the generate control, for a holder of `recon.prepare`.
    expect(
      await screen.findByRole("heading", { name: "No reconciliations for Sep 2026" }),
    ).toBeTruthy();
    const triggers = screen.getAllByRole("button", { name: "Generate reconciliation" });
    const trigger = triggers[0];
    if (trigger === undefined) {
      throw new Error("no Generate reconciliation control");
    }
    fireEvent.click(trigger);
    // XR-14: the menu lists the kinds `POST /reconciliations` generates.
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      "Billing to subledger",
      "Subledger to GL",
    ]);
    fireEvent.click(screen.getByRole("menuitem", { name: "Billing to subledger" }));

    expect(await screen.findByText("Generated REC-000043 (Billing to subledger).")).toBeTruthy();
    expect(posted).toHaveLength(1);
    expect(posted[0]?.key).not.toBeNull();
    expect(posted[0]?.body).toEqual({
      kind: "BILLING_TO_SUBLEDGER",
      entity_code: "AVM-US",
      book: "ASC606",
      period_key: "FY2026-P09",
    });
    // The list is read again and shows the new reconciliation.
    const grid = screen.getByRole("grid", { name: "Reconciliations" });
    expect(await within(grid).findByRole("link", { name: "REC-000043" })).toBeTruthy();
  });

  it("a generated subledger-to-GL reconciliation opens in its attach state", async () => {
    const posted: unknown[] = [];
    const generations: ReconciliationOut[] = [];
    serve({ generations });
    server.use(
      http.post(apiUrl("/api/v1/reconciliations"), async ({ request }) => {
        posted.push(await request.json());
        return HttpResponse.json(
          { id: JOB_ID, kind: "RECONCILIATION_GENERATE", state: "QUEUED" },
          {
            status: 202,
            headers: {
              Location: `/api/v1/jobs/${JOB_ID}`,
              "X-Erev-Reconciliation-Id": REC_GL,
            },
          },
        );
      }),
      http.get(apiUrl("/api/v1/jobs/:jobId"), () => {
        // The job inserts the draft without a source (04 §16.8).
        if (generations.length === 0) {
          generations.push(awaitingTrialBalance());
        }
        return HttpResponse.json({
          id: JOB_ID,
          kind: "RECONCILIATION_GENERATE",
          state: "SUCCEEDED",
          progress: { done: 0, total: null },
          created_at: "2026-09-12T15:20:00Z",
          created_by: MAYA_ACTOR,
          started_at: "2026-09-12T15:20:01Z",
          finished_at: "2026-09-12T15:20:02Z",
          problem: null,
          result: { href: `/api/v1/reconciliations/${REC_GL}`, counts: { variances: 0 } },
        });
      }),
    );
    open(LIST_PATH, MAYA);

    expect(
      await screen.findByRole("heading", { name: "No reconciliations for Sep 2026" }),
    ).toBeTruthy();
    const trigger = screen.getAllByRole("button", { name: "Generate reconciliation" })[0];
    if (trigger === undefined) {
      throw new Error("no Generate reconciliation control");
    }
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("menuitem", { name: "Subledger to GL" }));

    // SCREENS_B §2.1: the new reconciliation opens where its trial balance is attached; no toast.
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "REC-000042 · Subledger to GL · Sep 2026",
      }),
    ).toBeTruthy();
    expect(await screen.findByRole("heading", { name: "Attach a trial balance" })).toBeTruthy();
    expect(screen.queryByText(/^Generated REC-/)).toBeNull();
    expect(posted).toEqual([
      { kind: "SUBLEDGER_TO_GL", entity_code: "AVM-US", book: "ASC606", period_key: "FY2026-P09" },
    ]);
  });

  it("shows the generating job in place and a refused generation by name", async () => {
    let refuse = false;
    serve({ generations: [reconciliation()] });
    server.use(
      http.post(apiUrl("/api/v1/reconciliations"), () =>
        refuse
          ? problemResponse("invalid-transition", 409, "Invalid transition", {
              detail:
                "FY2026-P09 is closed for AVM-US in book ASC606. A reconciliation is generated and signed while the period is open, in soft close or reopened.",
            })
          : HttpResponse.json(
              { id: JOB_ID, kind: "RECONCILIATION_GENERATE", state: "QUEUED" },
              {
                status: 202,
                headers: {
                  Location: `/api/v1/jobs/${JOB_ID}`,
                  "X-Erev-Reconciliation-Id": REC_NEW,
                },
              },
            ),
      ),
      http.get(apiUrl("/api/v1/jobs/:jobId"), () =>
        HttpResponse.json({
          id: JOB_ID,
          kind: "RECONCILIATION_GENERATE",
          state: "RUNNING",
          progress: { done: 0, total: null },
          created_at: "2026-09-12T15:20:00Z",
          created_by: MAYA_ACTOR,
          started_at: "2026-09-12T15:20:01Z",
          finished_at: null,
          problem: null,
          result: null,
        }),
      ),
    );
    open(LIST_PATH, MAYA);

    await screen.findByTestId("SF-05-row-billing-to-subledger");
    fireEvent.click(screen.getByRole("button", { name: "Generate reconciliation" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Billing to subledger" }));
    // SB-R-06: "Generating <kind label>" with the job indicator (DS-CMP-24).
    const job = await screen.findByTestId("SF-05-job-reconciliations");
    expect(
      within(job).getByRole("progressbar", { name: "Generating Billing to subledger" }),
    ).toBeTruthy();

    refuse = true;
    fireEvent.click(screen.getByRole("button", { name: "Generate reconciliation" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Billing to subledger" }));
    expect(
      await screen.findByText(/^FY2026-P09 is closed for AVM-US in book ASC606\./),
    ).toBeTruthy();
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): the list has no field for a
  // message, so the banner says every sentence of a refused generation; one that names a member was
  // shown nowhere.
  it("a refused generation says every sentence of its refusal", async () => {
    const sentence = "The billing interface of this period is not complete.";
    serve({ generations: [reconciliation()] });
    server.use(http.post(apiUrl("/api/v1/reconciliations"), () => refusedWith({ kind: sentence })));
    open(LIST_PATH, MAYA);
    await screen.findByTestId("SF-05-row-billing-to-subledger");
    fireEvent.click(screen.getByRole("button", { name: "Generate reconciliation" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Billing to subledger" }));

    expect((await screen.findByText(sentence)).closest('[role="alert"]')?.textContent).toBe(
      REFUSAL_TITLE + sentence + REFUSAL_REFERENCE,
    );
  });

  it("offers no generation without recon.prepare or outside a workable period", async () => {
    serve();
    open(LIST_PATH, ROBERT);
    expect(
      await screen.findByRole("heading", { name: "No reconciliations for Sep 2026" }),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Generate reconciliation" })).toBeNull();
    cleanup();

    // A locked period generates nothing (PRD SM-09): the control is not rendered (SCR-PERM-03).
    serve({ state: period({ state: "closed", row_version: 9 }) });
    open(LIST_PATH, MAYA);
    expect(
      await screen.findByRole("heading", { name: "No reconciliations for Sep 2026" }),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Generate reconciliation" })).toBeNull();
  });
});

describe("SF-05:reconciliation", () => {
  it("high risk item", async () => {
    serve({
      generations: [generalLedger()],
      items: { [REC_GL]: [directEntry()] },
    });
    open(detailPath(REC_GL), MAYA);

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "REC-000042 · Subledger to GL · Sep 2026",
      }),
    ).toBeTruthy();
    const grid = await differences();
    const row = await within(grid).findByTestId("SF-05-row-je-ns-88121");
    // J-13.11 (asserted): kind, reference, the 250.00 difference and the high-risk classification.
    expect(
      within(row).getByRole("rowheader", {
        name: "Direct GL entry to a subledger-controlled account",
      }),
    ).toBeTruthy();
    expect(row.querySelector('[data-column="reference"]')?.textContent).toBe("JE-NS-88121");
    expect(row.querySelector('[data-column="difference"]')?.textContent).toBe("250.00");
    expect(row.querySelector('[data-column="account"]')?.textContent).toBe("2100");
    const risk = row.querySelector('[data-column="risk"]');
    expect(risk?.textContent).toBe("High risk");
    // The outline (classification) variant, not a status chip: no tone and no icon (§0.4).
    const chip = within(row).getByText("High risk");
    expect(chip.getAttribute("data-tone")).toBeNull();
    expect(chip.querySelector("svg")).toBeNull();
    expect(chip.className).toContain("bg-transparent");

    // The header carries the E-59 chip and the second chip Difference; the totals name the account.
    expect(headerChips("REC-000042 · Subledger to GL · Sep 2026")).toEqual(["Draft", "Difference"]);
    const totals = screen.getByRole("grid", { name: "Totals by account" });
    expect(totals.textContent).toContain("2100");
    expect(within(totals).getByRole("columnheader", { name: "GL (USD)" })).toBeTruthy();
    const figures = screen.getByRole("region", { name: "Key figures (USD)" });
    expect(figures.textContent).toContain("250.00");
  });

  it("every item kind the API states has its words, and a difference of each kind is listed", async () => {
    // The API hands the grid, the row's name and the drawer an `item_kind`, and `t()` throws on a key
    // the catalogue lacks (a production build prints the key): the role basis added `NOT_STATED` to
    // the API (04 §16.8 rev 1.253) and the page of every reconciliation with a role "not stated"
    // stood on the route's error page. The kinds are read from the API document, so a kind the server
    // gains fails here until the catalogue holds its words (SCREENS_B §2.2 "Kind").
    const kinds = apiItemKinds();
    expect(kinds).toContain("NOT_STATED");
    const key = (kind: string) => `close.reconciliation.itemKind.${kind}`;
    expect(kinds.filter((kind) => !hasMessage(key(kind)))).toEqual([]);
    const words: Readonly<Record<string, string>> = messages;
    expect(words[key("NOT_STATED")]).toBe("Not stated by the subledger");

    serve({
      generations: [generalLedger({ variance_count: kinds.length })],
      items: {
        [REC_GL]: kinds.map((kind, index) =>
          directEntry({
            id: `c1a2c3d4-0000-4000-8000-0000000001${String(index).padStart(2, "0")}`,
            item_kind: kind,
            gl_document_reference: `JE-KIND-${String(index + 1)}`,
          }),
        ),
      },
    });
    open(detailPath(REC_GL), MAYA);

    const grid = await differences();
    await within(grid).findByTestId("SF-05-row-je-kind-1");
    // One row a kind, in the order served, each named by its words and none by a catalogue key.
    const named = within(grid)
      .getAllByRole("rowheader")
      .map((cell) => cell.textContent);
    expect(named).toEqual(kinds.map((kind) => words[key(kind)]));
    expect(named[kinds.indexOf("NOT_STATED")]).toBe("Not stated by the subledger");
  });

  it("no sign-off for integration admin", async () => {
    const prepared = reconciliation({
      status: "PREPARED",
      signoffs: [signoff("PREPARER", MAYA_ACTOR, "2026-09-12T16:05:00Z")],
      row_version: 2,
    });
    // The reviewer sees the control on this reconciliation, so its absence below is not vacuous.
    serve({ generations: [prepared] });
    open(detailPath(REC_BILLING), PRIYA);
    expect(await screen.findByRole("button", { name: "Sign as reviewer" })).toBeTruthy();
    cleanup();

    // J-23.9: `nikhil` holds `integration.manage` and no `recon.signoff`.
    serve({ generations: [prepared] });
    open(detailPath(REC_BILLING), NIKHIL);
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "REC-000041 · Billing to subledger · Sep 2026",
      }),
    ).toBeTruthy();
    // The record and its sign-off history are readable; no sign-off control is rendered (SCR-PERM-02).
    const signoffs = await screen.findByRole("region", { name: "Sign-offs" });
    expect(signoffs.textContent).toContain("Maya Chen");
    expect(screen.queryByRole("button", { name: "Sign as reviewer" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Sign as preparer" })).toBeNull();
    expect(screen.queryByRole("button", { name: "More reconciliation actions" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Reopen/ })).toBeNull();
  });

  it("hides the reviewer sign-off from every holder of integration.manage (SoD-7)", async () => {
    // A custom role with both SoD-7 functions: the command answers 403 (04 §16.8), so the control
    // is not rendered; the reopen, which the command admits, stays.
    const both = persona(
      { id: "3c4d5e6f-7081-4b92-8ca3-b4c5d6e7f809", display_name: "Dana Okafor" },
      "dana@example.test",
      ["contract.read", "config.read", "integration.manage", "recon.signoff"],
    );
    serve({
      generations: [
        reconciliation({
          status: "PREPARED",
          signoffs: [signoff("PREPARER", MAYA_ACTOR, "2026-09-12T16:05:00Z")],
        }),
      ],
    });
    open(detailPath(REC_BILLING), both);
    fireEvent.click(await screen.findByRole("button", { name: "More reconciliation actions" }));
    expect(screen.getByRole("menuitem", { name: "Reopen reconciliation" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Sign as reviewer" })).toBeNull();
  });

  it("explains a difference with the item's If-Match, then signs as preparer", async () => {
    const patches: { readonly ifMatch: string | null; readonly body: unknown }[] = [];
    let item = directEntry();
    let current = generalLedger();
    const world = { generations: [current], items: { [REC_GL]: [item] } };
    serve(world);
    server.use(
      http.get(apiUrl("/api/v1/reconciliations/:reconciliationId"), () =>
        HttpResponse.json(current),
      ),
      http.get(apiUrl("/api/v1/reconciliations/:reconciliationId/items"), () =>
        HttpResponse.json({ items: [item], next_cursor: null }),
      ),
      http.patch(
        apiUrl(`/api/v1/reconciliations/${REC_GL}/items/${ITEM_GL}`),
        async ({ request }) => {
          const body = (await request.json()) as { readonly explanation: string };
          patches.push({ ifMatch: request.headers.get("If-Match"), body });
          item = directEntry({
            explanation: body.explanation,
            resolved_at: "2026-09-12T16:00:00Z",
            resolved_by: MAYA_ACTOR,
            row_version: 2,
          });
          return HttpResponse.json(item);
        },
      ),
      http.post(apiUrl(`/api/v1/reconciliations/${REC_GL}/prepare`), () => {
        current = generalLedger({
          status: "PREPARED",
          signoffs: [signoff("PREPARER", MAYA_ACTOR, "2026-09-12T16:05:00Z")],
          row_version: 2,
        });
        return HttpResponse.json(current);
      }),
    );
    open(detailPath(REC_GL), MAYA);

    const grid = await differences();
    const row = await within(grid).findByTestId("SF-05-row-je-ns-88121");
    // SM-09: signing reports the differences without an explanation; no dialog opens.
    fireEvent.click(screen.getByRole("button", { name: "Sign as preparer" }));
    expect((await screen.findByTestId("SF-05-banner-unexplained")).textContent).toContain(
      "Explain 1 difference above the threshold before signing.",
    );
    expect(screen.queryByRole("alertdialog")).toBeNull();

    fireEvent.click(within(row).getByRole("button", { name: "Add explanation" }));
    const drawer = await screen.findByRole("dialog", { name: "Explain difference" });
    expect(within(drawer).getByTestId("SF-05-drawer-explain-difference").textContent).toContain(
      "JE-NS-88121",
    );
    const field = within(drawer).getByRole("textbox", { name: /^Explanation \(required\)/ });
    // SB-R-05 minimum: a short explanation is reported on submit and nothing is sent.
    fireEvent.change(field, { target: { value: "Too short" } });
    fireEvent.click(within(drawer).getByRole("button", { name: "Save explanation" }));
    expect(await within(drawer).findByText("Enter at least 10 characters.")).toBeTruthy();
    expect(patches).toHaveLength(0);
    fireEvent.change(field, { target: { value: EXPLANATION } });
    fireEvent.click(within(drawer).getByRole("button", { name: "Save explanation" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Explain difference" })).toBeNull();
    });
    expect(patches).toEqual([{ ifMatch: '"r1"', body: { explanation: EXPLANATION } }]);
    await waitFor(() => {
      expect(
        screen.getByTestId("SF-05-row-je-ns-88121").querySelector('[data-column="explanation"]')
          ?.textContent,
      ).toContain(EXPLANATION);
    });

    // The statement is confirmed before the command is sent (OQ-B-05).
    fireEvent.click(screen.getByRole("button", { name: "Sign as preparer" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Sign REC-000042 as preparer?",
    });
    const confirm = within(dialog).getByRole("checkbox", { name: /I confirm this statement/ });
    expect(confirm.getAttribute("aria-labelledby")).not.toBeNull();
    expect(dialog.textContent).toContain(
      "I prepared this reconciliation and explained every difference above the threshold.",
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Sign as preparer" }));
    expect(await within(dialog).findByText("Confirm the statement before signing.")).toBeTruthy();
    fireEvent.click(confirm);
    fireEvent.click(within(dialog).getByRole("button", { name: "Sign as preparer" }));

    // Success: chip Prepared and the frozen-snapshot banner; the edit controls are gone.
    expect(await screen.findByText("Snapshot frozen for review.")).toBeTruthy();
    expect(headerChips("REC-000042 · Subledger to GL · Sep 2026")).toEqual([
      "Prepared",
      "Difference",
    ]);
    expect(screen.queryByRole("button", { name: "Sign as preparer" })).toBeNull();
    // DB-10: the preparer reads why no reviewer control is offered.
    expect(
      screen.getByText("You prepared this reconciliation. Another user must review it."),
    ).toBeTruthy();
    const signoffs = screen.getByTestId("SF-05-signoffs");
    expect(signoffs.textContent).toContain("Maya Chen");
    expect(signoffs.textContent).toContain("12 Sep 2026 16:05 UTC");
  });

  it("signs as reviewer after the step-up with the same Idempotency-Key", async () => {
    const keys: (string | null)[] = [];
    const bodies: unknown[] = [];
    let current = reconciliation({
      status: "PREPARED",
      signoffs: [signoff("PREPARER", MAYA_ACTOR, "2026-09-12T16:05:00Z")],
      row_version: 2,
    });
    serve({ generations: [current] });
    server.use(
      http.get(apiUrl("/api/v1/reconciliations/:reconciliationId"), () =>
        HttpResponse.json(current),
      ),
      http.post(apiUrl(`/api/v1/reconciliations/${REC_BILLING}/sign`), async ({ request }) => {
        keys.push(request.headers.get("Idempotency-Key"));
        bodies.push(await request.json());
        if (keys.length === 1) {
          return problemResponse("mfa-step-up-required", 403, "Confirm with your authenticator", {
            detail: "Enter a code from your authenticator app to continue.",
          });
        }
        current = reconciliation({
          status: "REVIEWED",
          signoffs: [
            signoff("PREPARER", MAYA_ACTOR, "2026-09-12T16:05:00Z"),
            signoff("REVIEWER", PRIYA_ACTOR, "2026-09-13T09:10:00Z"),
          ],
          row_version: 3,
        });
        return HttpResponse.json(current);
      }),
      http.post(apiUrl("/api/v1/session/mfa"), () =>
        HttpResponse.json({ ...signedInSession(), recovery_codes_remaining: null }),
      ),
    );
    open(detailPath(REC_BILLING), PRIYA);

    fireEvent.click(await screen.findByRole("button", { name: "Sign as reviewer" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Sign REC-000041 as reviewer?",
    });
    expect(dialog.textContent).toContain(
      "I reviewed this reconciliation, its differences and their explanations.",
    );
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /I confirm this statement/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Sign as reviewer" }));

    // SCR-PERM-05: the step-up modal, then the command again with the same key and body.
    const stepUp = await screen.findByRole("dialog", { name: "Confirm with your authenticator" });
    fireEvent.change(within(stepUp).getByRole("textbox", { name: "Authentication code" }), {
      target: { value: "123456" },
    });
    fireEvent.click(within(stepUp).getByRole("button", { name: "Confirm" }));

    expect(await screen.findByText("Signed REC-000041 as reviewer.")).toBeTruthy();
    expect(keys).toHaveLength(2);
    expect(keys[0]).not.toBeNull();
    expect(keys[1]).toBe(keys[0]);
    expect(bodies).toEqual([
      { role: "REVIEWER", statement_accepted: true },
      { role: "REVIEWER", statement_accepted: true },
    ]);
    await waitFor(() => {
      expect(headerChips("REC-000041 · Billing to subledger · Sep 2026")).toEqual(["Reviewed"]);
    });
    expect(screen.getByTestId("SF-05-signoffs").textContent).toContain("Priya Raman");
    expect(screen.queryByRole("button", { name: "Sign as reviewer" })).toBeNull();
  });

  it("a superseded reconciliation is read-only and leads to the current one", async () => {
    const old = reconciliation({
      id: REC_OLD,
      reconciliation_no: "REC-000040",
      is_current: false,
      variance_count: 1,
      created_at: "2026-09-11T09:00:00Z",
    });
    serve({
      generations: [reconciliation(), old],
      items: {
        [REC_OLD]: [unmatchedInvoice({ reconciliation_id: REC_OLD })],
      },
    });
    open(detailPath(REC_OLD), MAYA);

    const banner = await screen.findByTestId("SF-05-banner-superseded");
    expect(banner.textContent).toContain(
      "REC-000040 was replaced by REC-000041. Work on the current reconciliation.",
    );
    expect(await hrefOf(banner, "Open REC-000041")).toBe(`${LIST_PATH}/${REC_BILLING}${CONTEXT}`);
    expect(headerChips("REC-000040 · Billing to subledger · Sep 2026")).toEqual([
      "Draft",
      "Difference",
      "Superseded",
    ]);
    // Plainly not current: no sign-off and no explanation control on the draft.
    const row = await within(await differences()).findByTestId("SF-05-row-inv-us-9001");
    expect(within(row).queryByRole("button", { name: "Add explanation" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Sign as preparer" })).toBeNull();
  });

  it("a 409 on a reconciliation replaced meanwhile says so and refreshes the record", async () => {
    // R-54 (b): another user generated again after this screen read the draft.
    let replaced = false;
    const item = unmatchedInvoice({ explanation: "Invoice booked in October by billing." });
    serve({ generations: [reconciliation({ variance_count: 1 })] });
    server.use(
      http.get(apiUrl("/api/v1/reconciliations"), () =>
        HttpResponse.json({
          items: replaced
            ? [
                reconciliation({ id: REC_NEW, reconciliation_no: "REC-000043" }),
                reconciliation({ variance_count: 1, is_current: false }),
              ]
            : [reconciliation({ variance_count: 1 })],
          next_cursor: null,
        }),
      ),
      http.get(apiUrl("/api/v1/reconciliations/:reconciliationId"), () =>
        HttpResponse.json(reconciliation({ variance_count: 1, is_current: !replaced })),
      ),
      http.get(apiUrl("/api/v1/reconciliations/:reconciliationId/items"), () =>
        HttpResponse.json({ items: [item], next_cursor: null }),
      ),
      http.post(apiUrl(`/api/v1/reconciliations/${REC_BILLING}/prepare`), () => {
        replaced = true;
        return problemResponse("invalid-transition", 409, "Invalid transition", {
          detail: "REC-000041 was replaced by REC-000043. Work on the current reconciliation.",
        });
      }),
    );
    open(detailPath(REC_BILLING), MAYA);

    await within(await differences()).findByTestId("SF-05-row-inv-us-9001");
    fireEvent.click(screen.getByRole("button", { name: "Sign as preparer" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Sign REC-000041 as preparer?",
    });
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /I confirm this statement/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Sign as preparer" }));

    // The refusal is shown on the page and the record is read again: it now leads to REC-000043.
    const banner = await screen.findByTestId("SF-05-banner-superseded");
    expect(await hrefOf(banner, "Open REC-000043")).toBe(`${LIST_PATH}/${REC_NEW}${CONTEXT}`);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(screen.getByTestId("SF-05-banner-refused").textContent).toContain(
      "REC-000041 was replaced by REC-000043. Work on the current reconciliation.",
    );
    expect(screen.queryByRole("button", { name: "Sign as preparer" })).toBeNull();
  });

  it("a signature the API forbids is said on the record, whole", async () => {
    // §2.2 (rev 1.85): the 403 was a toast, and PRD ERR-01's two sentences take three lines of the
    // two a toast shows (DS-CMP-22). The refusal goes where the screen shows its other refusals.
    const ERR_01 =
      "You do not have permission to sign this reconciliation. Ask a workspace administrator if you need it.";
    const item = unmatchedInvoice({ explanation: "Invoice booked in October by billing." });
    const sign = async () => {
      await within(await differences()).findByTestId("SF-05-row-inv-us-9001");
      fireEvent.click(screen.getByRole("button", { name: "Sign as preparer" }));
      const dialog = await screen.findByRole("alertdialog", {
        name: "Sign REC-000041 as preparer?",
      });
      fireEvent.click(within(dialog).getByRole("checkbox", { name: /I confirm this statement/ }));
      fireEvent.click(within(dialog).getByRole("button", { name: "Sign as preparer" }));
    };
    const serveForbidden = (extra: Readonly<Record<string, string>>) => {
      serve({ generations: [reconciliation({ variance_count: 1 })] });
      server.use(
        http.get(apiUrl("/api/v1/reconciliations/:reconciliationId/items"), () =>
          HttpResponse.json({ items: [item], next_cursor: null }),
        ),
        http.post(apiUrl(`/api/v1/reconciliations/${REC_BILLING}/prepare`), () =>
          problemResponse("forbidden", 403, "Permission denied", extra),
        ),
      );
    };

    // The API's 403 without a sentence of its own: the catalogue's, in the banner.
    serveForbidden({});
    open(detailPath(REC_BILLING), MAYA);
    await sign();
    const banner = await screen.findByTestId("SF-05-banner-refused");
    expect(within(banner).getByRole("heading", { name: "Permission denied" })).toBeTruthy();
    expect(within(banner).getByText(ERR_01)).toBeTruthy();
    expect(screen.queryByRole("alertdialog")).toBeNull();
    // No toast: the messages region holds nothing.
    expect(
      within(screen.getByRole("region", { name: "Messages" })).queryByText(/permission/),
    ).toBeNull();
    cleanup();

    // With a sentence of its own the banner holds that one, and not the catalogue's beside it.
    serveForbidden({ detail: "recon.prepare is required for AVM-US." });
    open(detailPath(REC_BILLING), MAYA);
    await sign();
    const named = await screen.findByTestId("SF-05-banner-refused");
    expect(within(named).getByText("recon.prepare is required for AVM-US.")).toBeTruthy();
    expect(within(named).queryByText(ERR_01)).toBeNull();
    expect(
      within(screen.getByRole("region", { name: "Messages" })).queryByText(/required/),
    ).toBeNull();
    cleanup();

    // ERR-01 is the sentence of a 403 alone: another refusal without a sentence keeps its title.
    serve({ generations: [reconciliation({ variance_count: 1 })] });
    server.use(
      http.get(apiUrl("/api/v1/reconciliations/:reconciliationId/items"), () =>
        HttpResponse.json({ items: [item], next_cursor: null }),
      ),
      http.post(apiUrl(`/api/v1/reconciliations/${REC_BILLING}/prepare`), () =>
        problemResponse("invalid-transition", 409, "Invalid transition"),
      ),
    );
    open(detailPath(REC_BILLING), MAYA);
    await sign();
    const plain = await screen.findByTestId("SF-05-banner-refused");
    expect(within(plain).getByRole("heading", { name: "Invalid transition" })).toBeTruthy();
    expect(within(plain).queryByText(ERR_01)).toBeNull();
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): a sentence of `errors[]` that
  // names a member was shown nowhere — on the page, in the sign dialog, in "Reopen" and in "Explain
  // difference". The banner lists what no field shows, and what a field shows is not said twice.
  describe("a refused command", () => {
    const NO_FIELD = "The period of this reconciliation is locked.";

    function world(prepare: () => Response) {
      const item = unmatchedInvoice({ explanation: "Invoice booked in October by billing." });
      serve({ generations: [reconciliation({ variance_count: 1 })] });
      server.use(
        http.get(apiUrl("/api/v1/reconciliations/:reconciliationId/items"), () =>
          HttpResponse.json({ items: [item], next_cursor: null }),
        ),
        http.post(apiUrl(`/api/v1/reconciliations/${REC_BILLING}/prepare`), prepare),
      );
    }

    async function sign(): Promise<HTMLElement> {
      open(detailPath(REC_BILLING), MAYA);
      await within(await differences()).findByTestId("SF-05-row-inv-us-9001");
      fireEvent.click(screen.getByRole("button", { name: "Sign as preparer" }));
      const dialog = await screen.findByRole("alertdialog", {
        name: "Sign REC-000041 as preparer?",
      });
      fireEvent.click(within(dialog).getByRole("checkbox", { name: /I confirm this statement/ }));
      fireEvent.click(within(dialog).getByRole("button", { name: "Sign as preparer" }));
      return dialog;
    }

    it("a refusal about the record says every sentence on the page", async () => {
      world(() =>
        refusedWith(
          { status: NO_FIELD },
          { slug: "invalid-transition", status: 409, title: "Invalid transition" },
        ),
      );
      await sign();

      const banner = await screen.findByTestId("SF-05-banner-refused");
      expect(banner.textContent).toBe("Invalid transition" + NO_FIELD + REFUSAL_REFERENCE);
    });

    it("a 422 of a signature says every sentence in the dialog", async () => {
      world(() => refusedWith({ statement: NO_FIELD }));
      const dialog = await sign();

      const banner = await within(dialog).findByRole("alert");
      expect(banner.textContent).toBe(REFUSAL_TITLE + NO_FIELD + REFUSAL_REFERENCE);
    });

    it("Reopen: the banner lists what the reason does not show", async () => {
      const atReason = "Say what was found after the review.";
      serve({
        generations: [
          reconciliation({
            status: "REVIEWED",
            signoffs: [
              signoff("PREPARER", MAYA_ACTOR, "2026-09-12T16:05:00Z"),
              signoff("REVIEWER", PRIYA_ACTOR, "2026-09-13T09:10:00Z"),
            ],
            row_version: 3,
          }),
        ],
      });
      server.use(
        http.post(apiUrl(`/api/v1/reconciliations/${REC_BILLING}/reopen`), () =>
          refusedWith({ status: NO_FIELD, reason: atReason }),
        ),
      );
      open(detailPath(REC_BILLING), PRIYA);
      fireEvent.click(await screen.findByRole("button", { name: "More reconciliation actions" }));
      fireEvent.click(screen.getByRole("menuitem", { name: "Reopen reconciliation" }));
      const dialog = await screen.findByRole("alertdialog", { name: "Reopen REC-000041?" });
      const reason = within(dialog).getByRole("textbox", { name: /^Reason/ });
      fireEvent.change(reason, { target: { value: "A late credit memo changes the balance." } });
      fireEvent.click(within(dialog).getByRole("button", { name: "Reopen reconciliation" }));

      const banner = await within(dialog).findByRole("alert");
      expect(banner.textContent).toBe(REFUSAL_TITLE + NO_FIELD + REFUSAL_REFERENCE);
      expect(describedBy(reason)).toContain(atReason);
    });

    it("Explain difference: the banner lists what the explanation does not show, and after a 412 that the record changed", async () => {
      const atExplanation = "Name the journal entry that corrects the difference.";
      let status = 422;
      serve({ generations: [generalLedger()], items: { [REC_GL]: [directEntry()] } });
      server.use(
        http.patch(apiUrl(`/api/v1/reconciliations/${REC_GL}/items/${ITEM_GL}`), () =>
          refusedWith({ resolved_by: NO_FIELD, explanation: atExplanation }, { status }),
        ),
      );
      open(detailPath(REC_GL), MAYA);
      const row = await within(await differences()).findByTestId("SF-05-row-je-ns-88121");
      fireEvent.click(within(row).getByRole("button", { name: "Add explanation" }));
      const drawer = await screen.findByRole("dialog", { name: "Explain difference" });
      const field = within(drawer).getByRole("textbox", { name: /^Explanation \(required\)/ });
      fireEvent.change(field, { target: { value: "Posted directly in the ledger by treasury." } });
      fireEvent.click(within(drawer).getByRole("button", { name: "Save explanation" }));

      const banner = await within(drawer).findByRole("alert");
      expect(banner.textContent).toBe(REFUSAL_TITLE + NO_FIELD + REFUSAL_REFERENCE);
      expect(describedBy(field)).toContain(atExplanation);

      status = 412;
      fireEvent.click(within(drawer).getByRole("button", { name: "Save explanation" }));
      expect(await within(drawer).findByRole("heading", { name: RECORD_CHANGED })).toBeTruthy();
      expect(within(drawer).queryByRole("heading", { name: REFUSAL_TITLE })).toBeNull();
    });
  });

  it("a certified reconciliation shows when it was certified and no edit control", async () => {
    serve({
      state: period({ state: "closed", row_version: 9 }),
      generations: [
        reconciliation({
          status: "CERTIFIED",
          variance_count: 1,
          certified_at: "2026-10-01T09:14:00Z",
          period_lock_id: "a9a2c3d4-0000-4000-8000-000000000001",
          signoffs: [
            signoff("PREPARER", MAYA_ACTOR, "2026-09-12T16:05:00Z"),
            signoff("REVIEWER", PRIYA_ACTOR, "2026-09-13T09:10:00Z"),
          ],
        }),
      ],
      items: {
        [REC_BILLING]: [
          unmatchedInvoice({
            explanation: "Invoice booked in October by billing.",
            resolved_at: "2026-09-12T16:00:00Z",
            resolved_by: MAYA_ACTOR,
            row_version: 2,
          }),
        ],
      },
    });
    // A holder of both reconciliation permissions still gets no control (04 T-CLS-06).
    open(
      detailPath(REC_BILLING),
      persona(PRIYA_ACTOR, "priya@example.test", [
        "contract.read",
        "config.read",
        "recon.prepare",
        "recon.signoff",
      ]),
    );

    const banner = await screen.findByTestId("SF-05-banner-certified");
    expect(banner.textContent).toContain(
      "Certified at lock on 01 Oct 2026 09:14 UTC. Reopen the period to change it.",
    );
    // E-59 CERTIFIED reads Reconciled, and a certified reconciliation shows no Difference chip.
    expect(headerChips("REC-000041 · Billing to subledger · Sep 2026")).toEqual(["Reconciled"]);
    const row = await within(await differences()).findByTestId("SF-05-row-inv-us-9001");
    expect(row.textContent).toContain("Invoice booked in October by billing.");
    expect(screen.queryByRole("button", { name: "More reconciliation actions" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Sign as/ })).toBeNull();
    expect(within(row).queryByRole("button", { name: "Add explanation" })).toBeNull();
  });

  it("reopens a reviewed reconciliation with a reason", async () => {
    const reopens: unknown[] = [];
    let current = reconciliation({
      status: "REVIEWED",
      signoffs: [
        signoff("PREPARER", MAYA_ACTOR, "2026-09-12T16:05:00Z"),
        signoff("REVIEWER", PRIYA_ACTOR, "2026-09-13T09:10:00Z"),
      ],
      row_version: 3,
    });
    serve({ generations: [current] });
    server.use(
      http.get(apiUrl("/api/v1/reconciliations/:reconciliationId"), () =>
        HttpResponse.json(current),
      ),
      http.post(apiUrl(`/api/v1/reconciliations/${REC_BILLING}/reopen`), async ({ request }) => {
        reopens.push(await request.json());
        current = { ...current, status: "REOPENED", row_version: 4 };
        return HttpResponse.json(current);
      }),
    );
    // The preparer's permission does not reopen (supervisor ruling R-54 (c)).
    open(detailPath(REC_BILLING), MAYA);
    await screen.findByRole("region", { name: "Sign-offs" });
    expect(screen.queryByRole("button", { name: "More reconciliation actions" })).toBeNull();
    cleanup();

    open(detailPath(REC_BILLING), PRIYA);
    fireEvent.click(await screen.findByRole("button", { name: "More reconciliation actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Reopen reconciliation" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Reopen REC-000041?" });
    expect(dialog.textContent).toContain(
      "The reconciliation is reopened. Its sign-offs stay in the history; generate it again and repeat them.",
    );
    // SB-R-05: a reason of at least 10 characters, and the Danger command.
    fireEvent.click(within(dialog).getByRole("button", { name: "Reopen reconciliation" }));
    expect(await within(dialog).findByText("Enter at least 10 characters.")).toBeTruthy();
    expect(reopens).toHaveLength(0);
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Reason \(required\)/ }), {
      target: { value: "Late credit memo received from billing." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Reopen reconciliation" }));

    expect(await screen.findByText("Reopened REC-000041.")).toBeTruthy();
    expect(reopens).toEqual([{ reason: "Late credit memo received from billing." }]);
    await waitFor(() => {
      expect(headerChips("REC-000041 · Billing to subledger · Sep 2026")).toEqual(["Reopened"]);
    });
    // The sign-offs stay as history; the next step is a new generation.
    expect(screen.getByTestId("SF-05-signoffs").textContent).toContain("Priya Raman");
    expect(screen.getByTestId("SF-05-banner-reopened").textContent).toContain(
      "REC-000041 is reopened. Generate it again and repeat the sign-offs.",
    );
    expect(screen.queryByRole("button", { name: "More reconciliation actions" })).toBeNull();
  });

  it("shows no differences, the key figures of the currency and not found", async () => {
    serve({ generations: [reconciliation()] });
    open(detailPath(REC_BILLING), ROBERT);

    expect(await screen.findByRole("heading", { name: "No differences" })).toBeTruthy();
    expect(screen.getByText("Subledger and source totals agree for every account.")).toBeTruthy();
    // One totals row per currency for billing, so the strip reads that row (no client arithmetic).
    const figures = screen.getByRole("region", { name: "Key figures (USD)" });
    expect(figures.textContent).toContain("Billing total");
    expect(figures.textContent).toContain("125,000.00");
    expect(
      within(screen.getByRole("grid", { name: "Totals by account" })).getByRole("columnheader", {
        name: "Billing (USD)",
      }),
    ).toBeTruthy();
    // The breadcrumb leads back to the period's reconciliations, with the context the page wrote.
    const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(await hrefOf(breadcrumb, "Reconciliations")).toBe(`${LIST_PATH}${CONTEXT}`);
    expect(
      within(breadcrumb)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["Close", "AVM-US · ASC 606", "Reconciliations"]);
    cleanup();

    // SCR-ST-07: an id the caller cannot read, and a reconciliation of another period than the path's.
    serve({ generations: [reconciliation()] });
    open(detailPath(REC_NEW), ROBERT);
    expect(
      await screen.findByRole("heading", { level: 2, name: "Reconciliation not found" }),
    ).toBeTruthy();
    cleanup();

    serve({ generations: [reconciliation()] });
    open(`/close/AVM-US/ASC606/FY2026-P08/reconciliations/${REC_BILLING}`, ROBERT);
    expect(
      await screen.findByRole("heading", { level: 2, name: "Reconciliation not found" }),
    ).toBeTruthy();
  });

  it("attaches a trial balance by a pull that is followed on the record", async () => {
    const awaiting = awaitingTrialBalance();
    const rows: ReconciliationOut[] = [awaiting];
    const items: Record<string, readonly ReconciliationItem[]> = {};
    const sent: { readonly key: string | null; readonly body: unknown }[] = [];
    serve({ generations: rows, items });
    server.use(
      http.post(
        apiUrl(`/api/v1/reconciliations/${REC_GL}/attach-trial-balance`),
        async ({ request }) => {
          sent.push({ key: request.headers.get("Idempotency-Key"), body: await request.json() });
          // From now on the record states the request, for every reader.
          rows[0] = { ...awaiting, trial_balance: attachRequest("ADAPTER", "RUNNING") };
          return HttpResponse.json(
            { id: JOB_ID, kind: "RECONCILIATION_GENERATE", state: "QUEUED" },
            { status: 202, headers: { Location: `/api/v1/jobs/${JOB_ID}` } },
          );
        },
      ),
      http.get(apiUrl("/api/v1/jobs/:jobId"), () =>
        HttpResponse.json({
          id: JOB_ID,
          kind: "RECONCILIATION_GENERATE",
          state: "RUNNING",
          progress: { done: 0, total: null },
          created_at: "2026-09-12T15:19:40Z",
          created_by: MAYA_ACTOR,
          started_at: "2026-09-12T15:19:41Z",
          finished_at: null,
          problem: null,
          result: null,
        }),
      ),
    );
    open(detailPath(REC_GL), MAYA);

    // SCREENS_B §2.2 "No source": the state, and for the preparer the two ways to attach.
    expect(await screen.findByRole("heading", { name: "Attach a trial balance" })).toBeTruthy();
    expect(
      screen.getByText(
        "Pull the trial balance for AVM-US Sep 2026 from the GL connection, or upload a CSV of account balances.",
      ),
    ).toBeTruthy();
    // The controls follow the read of the period's state.
    const choice = await screen.findByRole("radiogroup", { name: "Trial balance source" });
    expect(
      within(choice)
        .getAllByRole("radio")
        .map((radio) => [radio.textContent, radio.getAttribute("aria-checked")]),
    ).toEqual([
      ["Pull from NetSuite (mock)", "true"],
      ["Upload CSV", "false"],
    ]);
    // Nothing is compared yet: no grid, no sign-off control.
    expect(screen.queryByRole("grid", { name: "Totals by account" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Sign as preparer" })).toBeNull();

    fireEvent.click(
      screen.getByRole("button", { name: "Pull trial balance from NetSuite (mock)" }),
    );
    // SB-R-06: the pull shows in place, read from the record.
    expect(
      await screen.findByRole("progressbar", { name: "Generating Subledger to GL" }),
    ).toBeTruthy();
    expect(sent).toHaveLength(1);
    expect(sent[0]?.key).not.toBeNull();
    expect(sent[0]?.body).toEqual({ source: "ADAPTER", integration_connection_id: CONNECTION.id });
    expect(screen.queryByRole("radiogroup", { name: "Trial balance source" })).toBeNull();

    // The job ends: the record has its source, its totals and its difference.
    items[REC_GL] = [directEntry()];
    rows[0] = generalLedger({
      gl_connections: [CONNECTION],
      trial_balance: attachRequest("ADAPTER", "SUCCEEDED", "2026-09-12T15:20:00Z"),
    });
    expect(await screen.findByRole("grid", { name: "Totals by account" })).toBeTruthy();
    // The differences are read again when the attach ends.
    expect(await within(await differences()).findByText("JE-NS-88121")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Attach a trial balance" })).toBeNull();
    // The wireframe's source line, and the preparer's control on a compared draft.
    expect(
      screen.getByText("NetSuite (mock) trial balance · pulled 12 Sep 2026 15:20 UTC"),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sign as preparer" })).toBeTruthy();
  });

  it("more than four GL connections are chosen from a list, behind one segment", async () => {
    // DS-CMP-31 holds two to five options: five connections and the upload would be six.
    const connections = [
      "NetSuite (mock)",
      "NetSuite EMEA",
      "SAP S/4HANA UK",
      "Sage Intacct",
      "Oracle Fusion",
    ].map((name, index) => ({ id: `a7b8c9d0-0000-4000-8000-00000000002${String(index)}`, name }));
    const awaiting: ReconciliationOut = { ...awaitingTrialBalance(), gl_connections: connections };
    const sent: unknown[] = [];
    serve({ generations: [awaiting], items: {} });
    server.use(
      http.post(
        apiUrl(`/api/v1/reconciliations/${REC_GL}/attach-trial-balance`),
        async ({ request }) => {
          sent.push(await request.json());
          return HttpResponse.json(
            { id: JOB_ID, kind: "RECONCILIATION_GENERATE", state: "QUEUED" },
            { status: 202, headers: { Location: `/api/v1/jobs/${JOB_ID}` } },
          );
        },
      ),
      http.get(apiUrl("/api/v1/jobs/:jobId"), () =>
        HttpResponse.json({
          id: JOB_ID,
          kind: "RECONCILIATION_GENERATE",
          state: "QUEUED",
          progress: { done: 0, total: null },
          created_at: "2026-09-12T15:19:40Z",
          created_by: MAYA_ACTOR,
          started_at: null,
          finished_at: null,
          problem: null,
          result: null,
        }),
      ),
    );
    open(detailPath(REC_GL), MAYA);

    const choice = await screen.findByRole("radiogroup", { name: "Trial balance source" });
    expect(
      within(choice)
        .getAllByRole("radio")
        .map((radio) => [radio.textContent, radio.getAttribute("aria-checked")]),
    ).toEqual([
      ["Pull from a GL connection", "true"],
      ["Upload CSV", "false"],
    ]);
    // The connections are a list; the first is chosen.
    const list = screen.getByRole("combobox", { name: "GL connection" });
    expect(list.textContent).toContain("NetSuite (mock)");
    expect(
      screen.getByRole("button", { name: "Pull trial balance from NetSuite (mock)" }),
    ).toBeTruthy();
    fireEvent.click(list);
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual(
      connections.map((connection) => connection.name),
    );
    fireEvent.mouseDown(screen.getByRole("option", { name: "Sage Intacct" }));
    // The command names the connection chosen.
    fireEvent.click(
      await screen.findByRole("button", { name: "Pull trial balance from Sage Intacct" }),
    );
    await waitFor(() => {
      expect(sent).toEqual([{ source: "ADAPTER", integration_connection_id: connections[3]?.id }]);
    });
  });

  it("a failed pull names the connection and the problem; the upload attaches a file", async () => {
    const FILE_ID = "f1f1f1f1-f1f1-4f1f-8f1f-000000000402";
    const failed: ReconciliationOut = {
      ...awaitingTrialBalance(),
      trial_balance: attachRequest("ADAPTER", "FAILED", null, {
        type: "https://erev.dev/problems/adapter-unavailable",
        title: "GL connection unavailable",
        status: 503,
        detail: "NetSuite (mock) did not answer.",
      }),
    };
    const rows: ReconciliationOut[] = [failed];
    const calls: string[] = [];
    const attached: unknown[] = [];
    const uploads: string[] = [];
    let refuse = true;
    serve({ generations: rows });
    server.use(
      http.post(apiUrl("/api/v1/files"), async ({ request }) => {
        calls.push("files");
        uploads.push(await request.text());
        return HttpResponse.json({ id: FILE_ID }, { status: 201 });
      }),
      http.post(
        apiUrl(`/api/v1/reconciliations/${REC_GL}/attach-trial-balance`),
        async ({ request }) => {
          calls.push("attach");
          attached.push(await request.json());
          if (refuse) {
            // 04 §16.8: a file that cannot be compared is refused with its findings by row and column.
            return problemResponse("validation-failed", 422, "Check the highlighted fields", {
              detail: "1 field needs attention.",
              errors: [
                {
                  field: "amount",
                  sheet: null,
                  row: 3,
                  rule_id: "REQ-INT-009",
                  message: "Enter the closing balance as a number.",
                },
              ],
            });
          }
          rows[0] = { ...failed, trial_balance: attachRequest("FILE", "RUNNING") };
          return HttpResponse.json(
            { id: JOB_ID, kind: "RECONCILIATION_GENERATE", state: "QUEUED" },
            { status: 202, headers: { Location: `/api/v1/jobs/${JOB_ID}` } },
          );
        },
      ),
      http.get(apiUrl("/api/v1/jobs/:jobId"), () =>
        HttpResponse.json({
          id: JOB_ID,
          kind: "RECONCILIATION_GENERATE",
          state: "RUNNING",
          progress: { done: 0, total: null },
          created_at: "2026-09-12T15:19:40Z",
          created_by: MAYA_ACTOR,
          started_at: "2026-09-12T15:19:41Z",
          finished_at: null,
          problem: null,
          result: null,
        }),
      ),
    );
    open(detailPath(REC_GL), MAYA);

    // SCREENS_B §2.2 "Pull failed", read from the record.
    const banner = await screen.findByTestId("SF-05-banner-attach-failed");
    expect(banner.textContent).toContain(
      "The trial balance could not be pulled from NetSuite (mock): GL connection unavailable. Upload a CSV instead.",
    );
    // "Upload a CSV instead": the section opens on the upload (the controls follow the period read).
    const choice = await screen.findByRole("radiogroup", { name: "Trial balance source" });
    expect(
      within(choice).getByRole("radio", { name: "Upload CSV" }).getAttribute("aria-checked"),
    ).toBe("true");
    expect(screen.getByText("Import files must be .xlsx or .csv and at most 50 MiB.")).toBeTruthy();

    // DS-CMP-21: the button stays enabled and says what is missing.
    fireEvent.click(screen.getByRole("button", { name: "Upload and compare" }));
    expect(await screen.findByText("Choose a CSV or XLSX file.")).toBeTruthy();
    expect(calls).toEqual([]);

    const balances = new File(
      ["account,currency,amount\n2100,USD,-103180.14\n"],
      "tb-sep-2026.csv",
      {
        type: "text/csv",
      },
    );
    fireEvent.change(screen.getByTestId("SF-05-trial-balance-file"), {
      target: { files: [balances] },
    });
    expect(screen.getByTestId("SF-05-trial-balance-selected").textContent).toContain(
      "tb-sep-2026.csv",
    );
    // A file that cannot be compared is refused with its rows; the section stays.
    fireEvent.click(screen.getByRole("button", { name: "Upload and compare" }));
    expect(await screen.findByText("1 field needs attention.")).toBeTruthy();
    expect(screen.getByText("Row 3, amount: Enter the closing balance as a number.")).toBeTruthy();
    // docs/dev-guide.md DG-FE-06: a message that names a column is said in the findings, and the
    // banner does not say it a second time.
    expect(
      screen.getByRole("heading", { name: REFUSAL_TITLE }).closest('[role="alert"]')?.textContent,
    ).toBe(REFUSAL_TITLE + "1 field needs attention." + REFUSAL_REFERENCE);
    expect(calls).toEqual(["files", "attach"]);
    expect(uploads[0]).toMatch(/name="purpose"\r\n\r\nIMPORT_SOURCE\r\n/);
    expect(attached[0]).toEqual({ file_id: FILE_ID });

    // The next file is accepted: the comparison shows in place.
    refuse = false;
    fireEvent.click(screen.getByRole("button", { name: "Upload and compare" }));
    expect(
      await screen.findByRole("progressbar", { name: "Generating Subledger to GL" }),
    ).toBeTruthy();
    expect(calls).toEqual(["files", "attach", "files", "attach"]);
  });

  it("the trial balance of a reader: the state without controls; a record that names no connection offers none", async () => {
    // A reviewer follows a pull in progress and a failed upload, and attaches nothing.
    const rows: ReconciliationOut[] = [
      { ...awaitingTrialBalance(), trial_balance: attachRequest("ADAPTER", "RUNNING") },
    ];
    serve({ generations: rows });
    open(detailPath(REC_GL), PRIYA);
    expect(
      await screen.findByRole("progressbar", { name: "Generating Subledger to GL" }),
    ).toBeTruthy();
    expect(screen.queryByRole("radiogroup", { name: "Trial balance source" })).toBeNull();
    cleanup();

    serve({
      generations: [
        {
          ...awaitingTrialBalance(),
          trial_balance: {
            ...attachRequest("FILE", "FAILED", null, {
              type: "https://erev.dev/problems/validation-failed",
              title: "Validation failed",
              status: 422,
              detail:
                "The trial balance names account 9999, which the chart of accounts does not hold.",
            }),
            file: { id: "f1f1f1f1-f1f1-4f1f-8f1f-000000000403", name: "tb-sep-2026.csv" },
          },
        },
      ],
    });
    open(detailPath(REC_GL), PRIYA);
    const banner = await screen.findByTestId("SF-05-banner-attach-failed");
    expect(banner.textContent).toContain(
      "The trial balance file could not be compared: Validation failed.",
    );
    expect(banner.textContent).toContain(
      "The trial balance names account 9999, which the chart of accounts does not hold.",
    );
    expect(screen.queryByRole("button", { name: "Upload and compare" })).toBeNull();
    cleanup();

    // A preparer whose entity has no GL connection uploads (`gl_connections` is empty).
    serve({ generations: [{ ...awaitingTrialBalance(), gl_connections: [] }] });
    open(detailPath(REC_GL), MAYA);
    expect(
      await screen.findByText(
        "No GL connection is set up for AVM-US. Upload a CSV of account balances.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("No source attached")).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Upload and compare" })).toBeTruthy();
    expect(screen.queryByRole("radiogroup", { name: "Trial balance source" })).toBeNull();
    cleanup();

    // SCR-PERM-02: the upload is `POST /files` purpose `IMPORT_SOURCE`, which takes `import.upload`.
    // A preparer without it pulls, and with no connection is offered nothing.
    const preparerOnly = persona(MAYA_ACTOR, "maya@example.test", [
      "contract.read",
      "config.read",
      "recon.prepare",
    ]);
    serve({ generations: [awaitingTrialBalance()] });
    open(detailPath(REC_GL), preparerOnly);
    expect(
      await screen.findByRole("button", { name: "Pull trial balance from NetSuite (mock)" }),
    ).toBeTruthy();
    expect(screen.queryByRole("radiogroup", { name: "Trial balance source" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Upload and compare" })).toBeNull();
    cleanup();

    serve({ generations: [{ ...awaitingTrialBalance(), gl_connections: [] }] });
    open(detailPath(REC_GL), preparerOnly);
    expect(await screen.findByText("No GL connection is set up for AVM-US.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Upload and compare" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Pull trial balance/ })).toBeNull();
  });

  it("key figures are the API's summary, one line per currency", async () => {
    const lines = (figure: string) =>
      Array.from(screen.getByTestId(`SF-05-kpi-${figure}`).querySelectorAll("dd"), (line) =>
        (line.textContent ?? "").replace(/\u00a0/g, " "),
      );
    // Two accounts in USD and one in EUR: three totals rows. The strip reads the server's sums; a
    // client that added the rows it holds would show other figures than these.
    serve({
      generations: [
        generalLedger({
          totals: [
            {
              account_code: "2100",
              currency: "USD",
              subledger_amount: money("-103430.14"),
              source_amount: money("-103180.14"),
              difference: money("250.00"),
            },
            {
              account_code: "2100",
              currency: "EUR",
              subledger_amount: money("-9000.00", "EUR"),
              source_amount: money("-9000.00", "EUR"),
              difference: money("0.00", "EUR"),
            },
          ],
          summary: [
            {
              currency: "USD",
              account_count: 2,
              subledger_amount: money("-55430.14"),
              source_amount: money("-55180.14"),
              difference: money("250.00"),
              not_stated_count: 0,
            },
            {
              currency: "EUR",
              account_count: 1,
              subledger_amount: money("-9000.00", "EUR"),
              source_amount: money("-9000.00", "EUR"),
              difference: money("0.00", "EUR"),
              not_stated_count: 0,
            },
          ],
        }),
      ],
    });
    open(detailPath(REC_GL), ROBERT);
    expect(await screen.findByRole("region", { name: "Key figures" })).toBeTruthy();
    expect(lines("accounts")).toEqual(["USD 2", "EUR 1"]);
    expect(lines("subledger-total")).toEqual(["USD (55,430.14)", "EUR (9,000.00)"]);
    expect(lines("source-total")).toEqual(["USD (55,180.14)", "EUR (9,000.00)"]);
    expect(lines("difference")).toEqual(["USD 250.00", "EUR 0.00"]);
    expect(lines("variances")).toEqual(["1"]);
    cleanup();

    // One currency: the heading names it and the figures carry no code; a billing summary counts no
    // account, so "Accounts" is left out.
    serve({ generations: [reconciliation()] });
    open(detailPath(REC_BILLING), ROBERT);
    expect(await screen.findByRole("region", { name: "Key figures (USD)" })).toBeTruthy();
    expect(screen.queryByTestId("SF-05-kpi-accounts")).toBeNull();
    expect(lines("subledger-total")).toEqual(["125,000.00"]);
    expect(lines("difference")).toEqual(["0.00"]);
    cleanup();

    // A draft before its trial balance holds no totals: the API's summary is empty and no figure is
    // made up.
    serve({ generations: [awaitingTrialBalance()] });
    open(detailPath(REC_GL), ROBERT);
    expect(await screen.findByRole("region", { name: "Key figures" })).toBeTruthy();
    expect(lines("subledger-total")).toEqual(["—No value"]);
    expect(lines("variances")).toEqual(["0"]);
  });
});
