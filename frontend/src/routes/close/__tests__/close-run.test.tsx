// @vitest-environment jsdom
// SF-05:close-run (BUILD_SPEC CLO-24; SCREENS_B §1.2, §0.4 E-62; SCREENS SCR-PERM-02, SCR-ST-03, SCR-ST-12;
// PRD SM-14, NFR-14; 04 API-R-39 §16.8, T-CLS-01; supervisor ruling R-79): the period's newest close run
// with its fourteen steps in the order of the API's array, the states a run reaches — queued, running,
// blocked on quarantined contracts, failed at a step with its problem, succeeded, cancelled — and the
// commands run, resume and cancel. The run is read as itself, so a reader who did not start it follows it
// too. API answers are contract fakes of 04 API-S-CloseRun.
import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../../app/router";
import type { CloseRun, CloseRunStatus } from "../../../lib/api/queries/close-runs";
import { CLOSE_RUN_STEP_CODES } from "../../../lib/api/queries/close-runs";
import type { Me } from "../../../lib/api/queries/me";
import type { PeriodCockpit } from "../../../lib/api/queries/periods";
import type { Period } from "../../../lib/api/queries/tenant";
import { NBSP } from "../../../lib/format";
import { installMemoryStorage, renderApp, signedInMe } from "../../../test/app";
import { narrowColumns } from "../../../test/grid-headers";
import { installGridViewport } from "../../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import { REFUSAL_REFERENCE, REFUSAL_TITLE, refusedWith } from "../../../test/refusals";
import { quarantineColumns } from "../close-run";

installMswServer();
installMemoryStorage();
installGridViewport();
// The cockpit frame reads the periods, then the cockpit, before a tab renders; a run is read again
// every 2 s while it moves.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
});

const RUN_PATH = "/close/AVM-US/ASC606/FY2026-P09/close-run";
const STATE_ID = "7c1d2e3f-4a5b-4c6d-8e7f-000000000909";
const RUN_ID = "e2a1b3c4-0000-4000-8000-000000000031";
const EARLIER_ID = "e2a1b3c4-0000-4000-8000-000000000030";
const JOB_ID = "5e4d3c2b-1a0f-4e9d-8c7b-6a5f4e3d2c51";
const JOURNAL_RUN_ID = "f3a1b3c4-0000-4000-8000-000000000007";
/** The sentence of a period-end step refused over an earlier period (supervisor ruling R-112). */
const EARLIER_UNPOSTED =
  "Aug 2026 has period-end amounts no close run has posted; run its close first.";
const UNBALANCED =
  "1 of 2 ledger invariants failed for FY2026-P09 of AVM-US in book ASC606: the USD lines sum to 12.00 USD, not to zero";

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

/** Revenue Accountant: `period.close` (PRD ACT-25). */
const MAYA = signedInMe({
  permissions: ["contract.read", "config.read", "period.close"],
});
/** A reader of the close without a command permission. */
const ROBERT: Me = signedInMe({
  user: {
    id: "1f2e3d4c-5b6a-4978-8a9b-0c1d2e3f4a5b",
    email: "robert@example.test",
    display_name: "Robert Lang",
    status: "ACTIVE",
  },
  permissions: ["contract.read", "config.read"],
});

function money(amount: string) {
  return { amount, currency: "USD" };
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

/** The fourteen steps of T-CLS-01 in the order of the array, each with the status of `statuses`. */
function steps(
  statuses: Partial<Record<(typeof CLOSE_RUN_STEP_CODES)[number], CloseRunStatus>>,
  extra: Partial<
    Record<(typeof CLOSE_RUN_STEP_CODES)[number], Partial<CloseRun["steps"][number]>>
  > = {},
): CloseRun["steps"] {
  return CLOSE_RUN_STEP_CODES.map((code, index) => {
    const status = statuses[code] ?? "PENDING";
    const ended = status === "SUCCEEDED" || status === "FAILED" || status === "BLOCKED";
    return {
      step_code: code,
      status,
      counts: {},
      started_at:
        status === "PENDING" ? null : `2026-09-12T14:05:${String(index * 2).padStart(2, "0")}Z`,
      finished_at: ended ? `2026-09-12T14:05:${String(index * 2 + 1).padStart(2, "0")}Z` : null,
      problem: null,
      ...extra[code],
    };
  });
}

const FIRST_FOUR = {
  CUTOFF: "SUCCEEDED",
  INTERFACE_COMPLETENESS: "SUCCEEDED",
  EXCEPTION_CHECK: "SUCCEEDED",
  RECOMPUTE_DIRTY: "SUCCEEDED",
} as const;
const FIRST_FOUR_COUNTS = {
  INTERFACE_COMPLETENESS: { counts: { interface_runs_complete: 3, interface_failures: 0 } },
  EXCEPTION_CHECK: { counts: { blocking_exceptions: 0 } },
  RECOMPUTE_DIRTY: { counts: { groups_recomputed: 14, groups_quarantined: 0, groups_waived: 0 } },
} as const;

function closeRun(overrides: Partial<CloseRun> = {}): CloseRun {
  return {
    id: RUN_ID,
    close_run_no: "CLS-000031",
    entity: AVM_US,
    book: "ASC606",
    period: {
      id: "1c2d3e4f-5a6b-4c7d-8e9f-000000000009",
      period_key: "FY2026-P09",
      name: "Sep 2026",
      start_date: "2026-09-01",
      end_date: "2026-09-30",
    },
    status: "PENDING",
    current_step_code: null,
    cutoff_known_at: "2026-09-12T14:05:00Z",
    steps: steps({}),
    counts: {},
    job: { id: JOB_ID, state: "QUEUED", progress: { done: 0, total: null } },
    journal_run_id: null,
    created_by: MAYA_ACTOR,
    created_at: "2026-09-12T14:05:00Z",
    started_at: null,
    finished_at: null,
    updated_at: "2026-09-12T14:05:00Z",
    row_version: 1,
    ...overrides,
  };
}

/** 04 T-CLS-01 `steps[].counts` of the period-end steps, as BUILD_SPEC CLO-20 serves them. */
const PERIOD_END_COUNTS = {
  RELEASE_SCHEDULES: { counts: { postings: 1204, lines: 2408, groups: 14, groups_skipped: 0 } },
  FX_REMEASUREMENT: { counts: { postings: 18, lines: 36, groups: 14, groups_skipped: 0 } },
  NETTING_RECLASS: { counts: { postings: 1, lines: 1, groups: 14, groups_skipped: 0 } },
  INVARIANTS: { counts: { invariants_checked: 2, invariant_failures: 0, lines_checked: 2445 } },
  JOURNAL_SUMMARIZATION: { counts: { batches: 2, journal_lines: 48 } },
  EXPORT: { counts: { batches: 2, batches_exported: 0 } },
  ACKNOWLEDGEMENT_WAIT: { counts: { batches: 2, batches_acknowledged: 0 } },
  GL_TIE_OUT: {
    counts: {
      trial_balance_attached: true,
      reconciliation_id: "b1a2c3d4-0000-4000-8000-000000000041",
      currency: "USD",
      difference: "250.00",
      variance_count: 1,
    },
  },
  DATASET_FREEZE: {
    counts: {
      datasets: { ROLLFORWARD: "ab".repeat(32) },
      datasets_frozen: 12,
      frozen_known_at: "2026-09-12T14:09:00Z",
      ledger_chain_seq: 1388,
    },
  },
} as const;

/** Steps 1 to 13 succeeded; "Lock" stays queued for the lock decision (BS4-D-03). */
function succeeded(overrides: Partial<CloseRun> = {}): CloseRun {
  return closeRun({
    status: "SUCCEEDED",
    current_step_code: null,
    started_at: "2026-09-12T14:05:00Z",
    finished_at: "2026-09-12T14:09:02Z",
    journal_run_id: JOURNAL_RUN_ID,
    job: { id: JOB_ID, state: "SUCCEEDED", progress: { done: 14, total: 14 } },
    steps: steps(
      Object.fromEntries(
        CLOSE_RUN_STEP_CODES.map((code) => [code, code === "LOCK" ? "PENDING" : "SUCCEEDED"]),
      ),
      { ...FIRST_FOUR_COUNTS, ...PERIOD_END_COUNTS },
    ),
    row_version: 16,
    ...overrides,
  });
}

/**
 * A run refused over an earlier period (supervisor ruling R-112; BUILD_SPEC CLO-20): `FAILED` at "FX
 * remeasurement", the first period-end step the run executes, with the sentence that names the period.
 */
function failedAtRemeasurement(): CloseRun {
  return closeRun({
    status: "FAILED",
    current_step_code: "FX_REMEASUREMENT",
    started_at: "2026-09-12T14:05:00Z",
    finished_at: "2026-09-12T14:05:40Z",
    job: { id: JOB_ID, state: "FAILED", progress: { done: 14, total: 14 } },
    steps: steps(
      { ...FIRST_FOUR, FX_REMEASUREMENT: "FAILED" },
      {
        ...FIRST_FOUR_COUNTS,
        FX_REMEASUREMENT: {
          problem: {
            type: "https://erev.dev/problems/invalid-transition",
            title: "Action not available",
            status: 409,
            detail: EARLIER_UNPOSTED,
          },
        },
      },
    ),
    row_version: 7,
  });
}

interface World {
  readonly state?: Period;
  /** The close runs of the period, newest first, as `GET /close-runs` lists them. */
  readonly runs?: CloseRun[];
  /** The blocking items of the engine that the period's close gates count (04 §16.14). */
  readonly quarantined?: readonly Record<string, unknown>[];
  /** Receives the query of every read of the engine's items. */
  readonly asked?: URLSearchParams[];
}

function serve(world: World = {}) {
  const state = world.state ?? period();
  const runs = world.runs ?? [];
  const empty = () => HttpResponse.json({ items: [], next_cursor: null });
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), empty),
    http.get(apiUrl("/api/v1/entities"), empty),
    http.get(apiUrl("/api/v1/books"), empty),
    http.get(apiUrl("/api/v1/jobs"), empty),
    http.get(apiUrl("/api/v1/journal-runs"), empty),
    http.get(apiUrl("/api/v1/approvals"), empty),
    http.get(apiUrl("/api/v1/currencies"), () =>
      HttpResponse.json({
        items: [
          { code: "USD", name: "US dollar", minor_unit: 2, numeric_code: "840", is_active: true },
        ],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/periods"), () =>
      HttpResponse.json({ items: [state], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/periods/:periodId/cockpit"), () => HttpResponse.json(cockpit(state))),
    http.get(apiUrl("/api/v1/exceptions"), ({ request }) => {
      const params = new URL(request.url).searchParams;
      if (params.get("source") === "ENGINE") {
        world.asked?.push(params);
      }
      // The quarantine read (SCREENS_B §1.2 rev 1.66): the blocking items of the engine that the gates
      // of this period count, asked by the period's id. Such an item names no period, the code of its
      // own refusal and — for a group of several contracts — no entity, and the list holds open items
      // only: a read that names an entity, a period, a code or a status is another list.
      const quarantine =
        params.get("source") === "ENGINE" &&
        params.get("severity") === "BLOCKING" &&
        params.get("blocking") === STATE_ID &&
        !["entity", "period", "code", "status"].some((name) => params.has(name));
      const items = quarantine ? (world.quarantined ?? []) : [];
      return HttpResponse.json(
        { items, next_cursor: null },
        { headers: { "X-Erev-Total-Count": String(items.length) } },
      );
    }),
    http.get(apiUrl("/api/v1/close-runs"), () =>
      HttpResponse.json({ items: runs, next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/close-runs/:closeRunId"), ({ params }) => {
      const found = runs.find((item) => item.id === String(params.closeRunId));
      return found === undefined
        ? problemResponse("not-found", 404, "Not found")
        : HttpResponse.json(found);
    }),
  );
}

function open(me: Me) {
  return renderApp(RUN_PATH, { me, screenRoutes: SCREEN_ROUTES });
}

describe("SF-05:close-run", () => {
  it("step labels", async () => {
    serve({ runs: [succeeded()] });
    open(MAYA);

    // SCREENS_B §1.2: an ordered list named "Close run steps", one row per step of the API's array.
    const list = await screen.findByRole("list", { name: "Close run steps" });
    expect(list.tagName).toBe("OL");
    const rows = within(list).getAllByRole("listitem");
    expect(rows.map((row) => row.getAttribute("aria-label"))).toEqual([
      "Step 1 of 14, Cut-off known at, Succeeded",
      "Step 2 of 14, Interface completeness, Succeeded",
      "Step 3 of 14, Exception check, Succeeded",
      "Step 4 of 14, Recompute changed contracts, Succeeded",
      "Step 5 of 14, Release schedules, Succeeded",
      "Step 6 of 14, FX remeasurement, Succeeded",
      "Step 7 of 14, Contract balance reclassification, Succeeded",
      "Step 8 of 14, Invariant checks, Succeeded",
      "Step 9 of 14, Journal summarization, Succeeded",
      "Step 10 of 14, Export, Succeeded",
      "Step 11 of 14, Acknowledgement wait, Succeeded",
      "Step 12 of 14, Subledger to GL tie-out, Succeeded",
      "Step 13 of 14, Dataset freeze, Succeeded",
      "Step 14 of 14, Lock, Queued",
    ]);
    // "Summary when finished": what each step's counts state (04 T-CLS-01), and the run's own
    // cut-off for the first step. The summary is the text of the row's tooltip too.
    expect(
      Object.fromEntries(
        rows.map((row) => [
          row.getAttribute("data-testid"),
          row.querySelector("span[title]")?.getAttribute("title") ?? null,
        ]),
      ),
    ).toEqual({
      "SF-05-row-cutoff": "12 Sep 2026 14:05 UTC",
      "SF-05-row-interface-completeness": "3 interface runs complete",
      "SF-05-row-exception-check": "0 blocking exceptions",
      "SF-05-row-recompute-dirty": "14 groups recomputed, 0 quarantined",
      "SF-05-row-release-schedules": "1,204 postings, 2,408 lines",
      "SF-05-row-fx-remeasurement": "36 lines",
      "SF-05-row-netting-reclass": "1 line",
      "SF-05-row-invariants": "All invariants pass",
      "SF-05-row-journal-summarization": "2 batches",
      "SF-05-row-export": "0 batches exported",
      "SF-05-row-acknowledgement-wait": "0 of 2 batches acknowledged",
      // DS-FMT-05: the ISO code, a no-break space, the amount.
      "SF-05-row-gl-tie-out": `Difference USD${NBSP}250.00`,
      "SF-05-row-dataset-freeze": "12 datasets frozen",
      "SF-05-row-lock": null,
    });
    // A run that ended has no step caption and no command; its journal run stays one link away.
    const header = screen.getByRole("region", { name: "Close run CLS-000031" });
    expect(header.textContent).toContain("Succeeded");
    expect(header.textContent).not.toContain("Step ");
    expect(
      within(header).getByRole("link", { name: "Open journal run" }).getAttribute("href"),
    ).toContain(`/journals/runs/${JOURNAL_RUN_ID}`);
    expect(screen.queryByRole("button", { name: "Cancel close run" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Resume close run" })).toBeNull();
    // The tab sits in the cockpit's route tabs.
    expect(
      within(screen.getByRole("navigation", { name: "Close of Sep 2026" }))
        .getByRole("link", { name: "Close run" })
        .getAttribute("aria-current"),
    ).toBe("page");
  });

  it("blocked banner", async () => {
    const blocked = closeRun({
      status: "BLOCKED",
      current_step_code: "RECOMPUTE_DIRTY",
      started_at: "2026-09-12T14:05:00Z",
      job: { id: JOB_ID, state: "SUCCEEDED", progress: { done: 14, total: 14 } },
      steps: steps(
        {
          CUTOFF: "SUCCEEDED",
          INTERFACE_COMPLETENESS: "SUCCEEDED",
          EXCEPTION_CHECK: "SUCCEEDED",
          RECOMPUTE_DIRTY: "BLOCKED",
        },
        {
          ...FIRST_FOUR_COUNTS,
          RECOMPUTE_DIRTY: {
            counts: { groups_recomputed: 13, groups_quarantined: 1, groups_waived: 0 },
          },
        },
      ),
    });
    const resumed: (string | null)[] = [];
    const asked: URLSearchParams[] = [];
    const members =
      "Combination group CG-000017 (NS-SO-US-1002, NS-SO-US-1003): no EUR to USD rate for 30 Sep 2026.";
    serve({
      runs: [blocked],
      asked,
      quarantined: [
        {
          id: "9a8b7c6d-0000-4000-8000-000000000101",
          exception_no: "EXC-000412",
          source: "ENGINE",
          code: "ENGINE_INVARIANT_VIOLATION",
          severity: "BLOCKING",
          status: "OPEN",
          title: "Engine invariant violated",
          message: "Allocated transaction price does not equal the contract's transaction price.",
          contract_id: "f1a2c3d4-0000-4000-8000-000000000001",
          contract_external_id: "NS-SO-US-1001",
          combination_group_code: null,
        },
        // The item of a group of several contracts names no contract and no entity (05 RCP-20), and
        // carries the code of its own refusal: raised before this run and still open, it is in the
        // period's list and not in the run's count.
        {
          id: "9a8b7c6d-0000-4000-8000-000000000102",
          exception_no: "EXC-000398",
          source: "ENGINE",
          code: "FX_RATE_MISSING",
          severity: "BLOCKING",
          status: "OPEN",
          title: "FX rate missing",
          message: members,
          contract_id: null,
          contract_external_id: null,
          combination_group_code: "CG-000017",
        },
      ],
    });
    server.use(
      http.post(apiUrl(`/api/v1/close-runs/${RUN_ID}/resume`), ({ request }) => {
        resumed.push(request.headers.get("Idempotency-Key"));
        return HttpResponse.json(
          { id: JOB_ID, kind: "CLOSE_RUN", state: "QUEUED" },
          { status: 202, headers: { Location: `/api/v1/jobs/${JOB_ID}` } },
        );
      }),
      http.get(apiUrl("/api/v1/jobs/:jobId"), () =>
        HttpResponse.json({
          id: JOB_ID,
          kind: "CLOSE_RUN",
          state: "QUEUED",
          progress: { done: 0, total: null },
          created_at: "2026-09-12T14:20:00Z",
          created_by: MAYA_ACTOR,
          started_at: null,
          finished_at: null,
          problem: null,
          result: null,
        }),
      ),
    );
    open(MAYA);

    // SCREENS_B §1.2 `BLOCKED`, with the copy of the build spec's acceptance.
    const banner = await screen.findByTestId("SF-05-banner-close-run-blocked");
    await waitFor(() => {
      expect(banner.textContent).toContain(
        "Close run CLS-000031 is blocked: 1 contracts were quarantined. Resolve or waive them, then resume.",
      );
    });
    // The quarantined contract with its exception, for the one who resolves it.
    const grid = await screen.findByRole("grid", { name: "Quarantined contracts" });
    expect(await within(grid).findByRole("link", { name: "NS-SO-US-1001" })).toBeTruthy();
    expect(within(grid).getByText("ENGINE_INVARIANT_VIOLATION")).toBeTruthy();
    expect(within(grid).getByRole("link", { name: "EXC-000412" }).getAttribute("href")).toContain(
      "/data/exceptions/9a8b7c6d-0000-4000-8000-000000000101",
    );
    // SCREENS_B §1.2 rev 1.66: the item of a group of several contracts shows the group's code under
    // "Contract" — text, a group having no page — and its message names the member contracts.
    const group = within(grid).getByText("CG-000017");
    expect(group.closest("a")).toBeNull();
    expect(group.closest('[role="row"]')?.textContent).toContain(members);
    expect(group.closest('[role="row"]')?.textContent).toContain("FX_RATE_MISSING");
    expect(within(grid).getByRole("link", { name: "EXC-000398" }).getAttribute("href")).toContain(
      "/data/exceptions/9a8b7c6d-0000-4000-8000-000000000102",
    );
    // The read is the list the period's gates count, by the period's id (04 §16.14 rev 1.206): no
    // entity, period, code or status of the screen's own.
    expect(asked.length).toBeGreaterThan(0);
    for (const query of asked) {
      expect([...query.keys()].sort()).toEqual([
        "blocking",
        "count",
        "limit",
        "severity",
        "sort",
        "source",
      ]);
      expect([query.get("blocking"), query.get("source"), query.get("severity")]).toEqual([
        STATE_ID,
        "ENGINE",
        "BLOCKING",
      ]);
    }
    // The header names where the run stopped.
    expect(screen.getByRole("region", { name: "Close run CLS-000031" }).textContent).toContain(
      "Step 4 of 14: Recompute changed contracts",
    );

    fireEvent.click(within(banner).getByRole("button", { name: "Resume close run" }));
    await waitFor(() => {
      expect(resumed).toHaveLength(1);
    });
    expect(resumed[0]).not.toBeNull();
  });

  it("a blocked run that states no count takes the count of the period's list", async () => {
    // A run that states no `groups_quarantined` (04 T-CLS-01 "Step counts"): the banner's count stands
    // in from the list the grid shows — the same read, by the period's id.
    const blocked = closeRun({
      status: "BLOCKED",
      current_step_code: "RECOMPUTE_DIRTY",
      started_at: "2026-09-12T14:05:00Z",
      job: { id: JOB_ID, state: "SUCCEEDED", progress: { done: 14, total: 14 } },
      steps: steps({
        CUTOFF: "SUCCEEDED",
        INTERFACE_COMPLETENESS: "SUCCEEDED",
        EXCEPTION_CHECK: "SUCCEEDED",
        RECOMPUTE_DIRTY: "BLOCKED",
      }),
    });
    const asked: URLSearchParams[] = [];
    const item = (number: number) => ({
      id: `9a8b7c6d-0000-4000-8000-00000000020${String(number)}`,
      exception_no: `EXC-00050${String(number)}`,
      source: "ENGINE",
      code: "ENGINE_INVARIANT_VIOLATION",
      severity: "BLOCKING",
      status: "OPEN",
      title: "Engine invariant violated",
      message: "Allocated transaction price does not equal the contract's transaction price.",
      contract_id: `f1a2c3d4-0000-4000-8000-00000000020${String(number)}`,
      contract_external_id: `NS-SO-US-200${String(number)}`,
      combination_group_code: null,
    });
    serve({ runs: [blocked], asked, quarantined: [item(1), item(2), item(3)] });
    open(MAYA);

    const banner = await screen.findByTestId("SF-05-banner-close-run-blocked");
    await waitFor(() => {
      expect(banner.textContent).toContain(
        "Close run CLS-000031 is blocked: 3 contracts were quarantined. Resolve or waive them, then resume.",
      );
    });
    const grid = await screen.findByRole("grid", { name: "Quarantined contracts" });
    expect(await within(grid).findByRole("link", { name: "NS-SO-US-2003" })).toBeTruthy();
    expect(asked.length).toBeGreaterThan(0);
    expect(asked.map((query) => query.get("blocking"))).toEqual(asked.map(() => STATE_ID));
    expect(asked.some((query) => query.has("entity") || query.has("status"))).toBe(false);
  });

  it("a failed invariant blocks the run: the step's problem, and no quarantine", async () => {
    const blocked = closeRun({
      status: "BLOCKED",
      current_step_code: "INVARIANTS",
      started_at: "2026-09-12T14:05:00Z",
      job: { id: JOB_ID, state: "SUCCEEDED", progress: { done: 14, total: 14 } },
      steps: steps(
        {
          ...FIRST_FOUR,
          RELEASE_SCHEDULES: "SUCCEEDED",
          FX_REMEASUREMENT: "SUCCEEDED",
          NETTING_RECLASS: "SUCCEEDED",
          INVARIANTS: "FAILED",
        },
        {
          ...FIRST_FOUR_COUNTS,
          ...PERIOD_END_COUNTS,
          INVARIANTS: {
            counts: { invariants_checked: 2, invariant_failures: 1, lines_checked: 2445 },
            problem: {
              type: "https://erev.dev/problems/ledger-unbalanced",
              title: "Entries do not balance",
              status: 422,
              detail: UNBALANCED,
            },
          },
        },
      ),
    });
    serve({ runs: [blocked] });
    open(MAYA);

    // PRD SM-14: a failed invariant blocks the run. SCREENS_B §1.2 (rev 1.47): the banner is the
    // copy of a failed step, for "Invariant checks", and the step says what does not balance.
    const banner = await screen.findByTestId("SF-05-banner-close-run-failed");
    expect(banner.textContent).toContain(
      "Close run for AVM-US Sep 2026 failed at Invariant checks. Nothing was committed for that step.",
    );
    expect(screen.queryByTestId("SF-05-banner-close-run-blocked")).toBeNull();
    expect(banner.textContent).toContain("Entries do not balance");
    expect(banner.textContent).toContain(UNBALANCED);
    expect(banner.textContent).not.toContain("quarantined");
    expect(within(banner).getByRole("button", { name: "Resume close run" })).toBeTruthy();
    const list = screen.getByRole("list", { name: "Close run steps" });
    const row = within(list).getByTestId("SF-05-row-invariants");
    expect(row.getAttribute("aria-label")).toBe("Step 8 of 14, Invariant checks, Failed");
    expect(row.textContent).toContain("1 invariant failure");
    // Nothing was quarantined: no grid of contracts to resolve.
    expect(screen.queryByRole("grid", { name: "Quarantined contracts" })).toBeNull();
    // A blocked run has not ended: it is cancelled or resumed.
    expect(screen.getByRole("button", { name: "Cancel close run" })).toBeTruthy();
    const header = screen.getByRole("region", { name: "Close run CLS-000031" });
    expect(header.textContent).toContain("Blocked");
    expect(header.textContent).toContain("Step 8 of 14: Invariant checks");
  });

  it("a run that failed at a step shows the step's problem and is resumed", async () => {
    const runs: CloseRun[] = [failedAtRemeasurement()];
    let resumes = 0;
    serve({ runs });
    server.use(
      http.post(apiUrl(`/api/v1/close-runs/${RUN_ID}/resume`), () => {
        resumes += 1;
        // The job continues at the first step that has not succeeded (NFR-14).
        runs[0] = closeRun({
          status: "RUNNING",
          current_step_code: "FX_REMEASUREMENT",
          started_at: "2026-09-12T14:05:00Z",
          job: { id: JOB_ID, state: "RUNNING", progress: { done: 0, total: null } },
          steps: steps({ ...FIRST_FOUR, FX_REMEASUREMENT: "RUNNING" }, FIRST_FOUR_COUNTS),
          row_version: 8,
        });
        return HttpResponse.json(
          { id: JOB_ID, kind: "CLOSE_RUN", state: "QUEUED" },
          { status: 202, headers: { Location: `/api/v1/jobs/${JOB_ID}` } },
        );
      }),
      http.get(apiUrl("/api/v1/jobs/:jobId"), () =>
        HttpResponse.json({
          id: JOB_ID,
          kind: "CLOSE_RUN",
          state: "RUNNING",
          progress: { done: 0, total: null },
          created_at: "2026-09-12T14:20:00Z",
          created_by: MAYA_ACTOR,
          started_at: "2026-09-12T14:20:01Z",
          finished_at: null,
          problem: null,
          result: null,
        }),
      ),
    );
    open(MAYA);

    // SCR-ST-12 with the step by its label, and the step's own problem (04 §16.8 `steps[].problem`).
    const banner = await screen.findByTestId("SF-05-banner-close-run-failed");
    expect(banner.textContent).toContain(
      "Close run for AVM-US Sep 2026 failed at FX remeasurement. Nothing was committed for that step.",
    );
    expect(banner.textContent).toContain(EARLIER_UNPOSTED);
    const header = screen.getByRole("region", { name: "Close run CLS-000031" });
    expect(header.textContent).toContain("Failed");
    expect(header.textContent).toContain("Step 6 of 14: FX remeasurement");
    // The run executes "FX remeasurement" before "Release schedules" (R-79 (b)): row 6 has failed
    // while row 5 is still queued, and the rows keep the order of the array.
    const list = screen.getByRole("list", { name: "Close run steps" });
    expect(
      within(list)
        .getAllByRole("listitem")
        .slice(4, 6)
        .map((row) => row.getAttribute("aria-label")),
    ).toEqual([
      "Step 5 of 14, Release schedules, Queued",
      "Step 6 of 14, FX remeasurement, Failed",
    ]);
    expect(within(list).getByTestId("SF-05-row-fx-remeasurement").textContent).toContain(
      "Action not available",
    );
    // A failed run has ended: nothing to cancel.
    expect(screen.queryByRole("button", { name: "Cancel close run" })).toBeNull();
    expect(screen.queryByRole("grid", { name: "Quarantined contracts" })).toBeNull();

    fireEvent.click(within(banner).getByRole("button", { name: "Resume close run" }));
    // The resumed run is followed on the run itself.
    expect(
      await screen.findByRole("progressbar", { name: "Close run for AVM-US Sep 2026" }),
    ).toBeTruthy();
    expect(resumes).toBe(1);
    expect(screen.queryByTestId("SF-05-banner-close-run-failed")).toBeNull();
    expect(screen.getByRole("region", { name: "Close run CLS-000031" }).textContent).toContain(
      "Running",
    );
    expect(screen.getByRole("button", { name: "Cancel close run" })).toBeTruthy();
  });

  it("a resume the API refuses says why, and the runs are read again", async () => {
    // SCREENS_B §1.2 rev 1.81 (04 §16.8 rev 1.228, item CLO-GATE-RUN-2): a run that a newer one has
    // superseded is not resumed. The page offers "Resume close run" on the newest run it has read, so
    // the refusal means that read is out of date — here another member's run, started and ended since.
    // The sentence is the API's as it ends since 04 §16.8 rev 1.259 (SCREENS_B §1.2 rev 1.97).
    const SUPERSEDED = "CLS-000031 is not the latest close run of this period. Run close again.";
    const NEWER_ID = "e2a1b3c4-0000-4000-8000-000000000032";
    const runs: CloseRun[] = [failedAtRemeasurement()];
    let resumes = 0;
    serve({ runs });
    server.use(
      http.post(apiUrl(`/api/v1/close-runs/${RUN_ID}/resume`), () => {
        resumes += 1;
        runs.unshift(
          succeeded({
            id: NEWER_ID,
            close_run_no: "CLS-000032",
            created_at: "2026-09-12T15:00:00Z",
            started_at: "2026-09-12T15:00:01Z",
            finished_at: "2026-09-12T15:04:10Z",
          }),
        );
        return problemResponse("invalid-transition", 409, "Action not available", {
          detail: SUPERSEDED,
        });
      }),
    );
    open(MAYA);

    const failed = await screen.findByTestId("SF-05-banner-close-run-failed");
    expect(screen.getByRole("region", { name: "Close run CLS-000031" })).toBeTruthy();
    fireEvent.click(within(failed).getByRole("button", { name: "Resume close run" }));

    // The API's sentence, whole, in the banner above the run.
    const refusal = await screen.findByText(SUPERSEDED);
    expect(refusal.closest('[role="alert"]')?.textContent).toContain("Action not available");
    expect(resumes).toBe(1);
    // The page shows the run the period has: the newer run in the header, the refused one below it.
    const header = await screen.findByRole("region", { name: "Close run CLS-000032" });
    expect(header.textContent).toContain("Succeeded");
    expect(screen.queryByRole("region", { name: "Close run CLS-000031" })).toBeNull();
    expect(screen.queryByTestId("SF-05-banner-close-run-failed")).toBeNull();
    expect(screen.queryByRole("button", { name: "Resume close run" })).toBeNull();
    const earlier = await screen.findByRole("table", { name: "Earlier close runs" });
    expect(await within(earlier).findByText("CLS-000031")).toBeTruthy();
    // The refusal stays while the page changes under it.
    expect(screen.getByText(SUPERSEDED)).toBeTruthy();
    cleanup();

    // The refusal leaves with the next command: here the other run is gone, and the resume is taken.
    const OTHER_ACTIVE =
      "CLS-000032 is already running for this period. CLS-000031 cannot be resumed.";
    const again: CloseRun[] = [failedAtRemeasurement()];
    let attempts = 0;
    serve({ runs: again });
    server.use(
      http.post(apiUrl(`/api/v1/close-runs/${RUN_ID}/resume`), () => {
        attempts += 1;
        if (attempts === 1) {
          return problemResponse("invalid-transition", 409, "Action not available", {
            detail: OTHER_ACTIVE,
          });
        }
        again[0] = closeRun({
          status: "RUNNING",
          current_step_code: "FX_REMEASUREMENT",
          started_at: "2026-09-12T14:05:00Z",
          job: { id: JOB_ID, state: "RUNNING", progress: { done: 0, total: null } },
          steps: steps({ ...FIRST_FOUR, FX_REMEASUREMENT: "RUNNING" }, FIRST_FOUR_COUNTS),
          row_version: 8,
        });
        return HttpResponse.json(
          { id: JOB_ID, kind: "CLOSE_RUN", state: "QUEUED" },
          { status: 202, headers: { Location: `/api/v1/jobs/${JOB_ID}` } },
        );
      }),
      http.get(apiUrl("/api/v1/jobs/:jobId"), () =>
        HttpResponse.json({
          id: JOB_ID,
          kind: "CLOSE_RUN",
          state: "RUNNING",
          progress: { done: 0, total: null },
          created_at: "2026-09-12T14:20:00Z",
          created_by: MAYA_ACTOR,
          started_at: "2026-09-12T14:20:01Z",
          finished_at: null,
          problem: null,
          result: null,
        }),
      ),
    );
    open(MAYA);
    fireEvent.click(
      within(await screen.findByTestId("SF-05-banner-close-run-failed")).getByRole("button", {
        name: "Resume close run",
      }),
    );
    expect(await screen.findByText(OTHER_ACTIVE)).toBeTruthy();
    // The run is still the newest and still failed: the command is offered again.
    fireEvent.click(
      within(await screen.findByTestId("SF-05-banner-close-run-failed")).getByRole("button", {
        name: "Resume close run",
      }),
    );
    expect(
      await screen.findByRole("progressbar", { name: "Close run for AVM-US Sep 2026" }),
    ).toBeTruthy();
    expect(attempts).toBe(2);
    expect(screen.queryByText(OTHER_ACTIVE)).toBeNull();
    cleanup();

    // A refusal that is no conflict says nothing about the page's read: the runs are not read again.
    let listReads = 0;
    serve({ runs: [failedAtRemeasurement()] });
    server.use(
      http.get(apiUrl("/api/v1/close-runs"), () => {
        listReads += 1;
        return HttpResponse.json({ items: [failedAtRemeasurement()], next_cursor: null });
      }),
      http.post(apiUrl(`/api/v1/close-runs/${RUN_ID}/resume`), () =>
        problemResponse("forbidden", 403, "You do not have permission to do that", {
          detail: "period.close is required for AVM-US.",
        }),
      ),
    );
    open(MAYA);
    const resumeIt = within(await screen.findByTestId("SF-05-banner-close-run-failed")).getByRole(
      "button",
      { name: "Resume close run" },
    );
    // A failed run does not move, so nothing reads the list between the page's first read and the press.
    const before = listReads;
    expect(before).toBeGreaterThan(0);
    fireEvent.click(resumeIt);
    expect(await screen.findByText("period.close is required for AVM-US.")).toBeTruthy();
    await new Promise((resolve) => setTimeout(resolve, 250));
    expect(listReads).toBe(before);
  });

  it("a run the API refuses to start says why, and the period is read again", async () => {
    // "Run close" is offered by the state the page has read (SCREENS_B §1.1, §1.2). Another member
    // locked the period since: the API refuses the run (04 §16.8), and that read is out of date.
    const NOT_OPEN =
      "FY2026-P09 of AVM-US in book ASC606 is closed. A close run needs an open period, a period in soft close or a reopened one.";
    const refusal = () =>
      problemResponse("invalid-transition", 409, "Action not available", {
        detail: NOT_OPEN,
        errors: [{ field: "period_key", rule_id: "SM-07", message: NOT_OPEN }],
      });
    const places = [
      // The tab's own command, on a period without a run.
      { runs: [] as CloseRun[], within: "No close run for Sep 2026" },
      // The action bar's, beside a run that has ended.
      { runs: [succeeded()], within: null },
    ];
    for (const place of places) {
      let state = period();
      let starts = 0;
      serve({ runs: place.runs });
      server.use(
        http.get(apiUrl("/api/v1/periods"), () =>
          HttpResponse.json({ items: [state], next_cursor: null }),
        ),
        http.get(apiUrl("/api/v1/periods/:periodId/cockpit"), () =>
          HttpResponse.json(cockpit(state)),
        ),
        http.post(apiUrl("/api/v1/close-runs"), () => {
          starts += 1;
          state = period({ state: "closed", row_version: 9 });
          return refusal();
        }),
      );
      open(MAYA);
      if (place.within === null) {
        await screen.findByRole("region", { name: "Close run CLS-000031" });
        fireEvent.click(screen.getByRole("button", { name: "Run close" }));
      } else {
        const tab = (await screen.findByRole("heading", { name: place.within })).parentElement
          ?.parentElement;
        if (tab === null || tab === undefined) {
          throw new Error("the empty state has no container");
        }
        fireEvent.click(within(tab).getByRole("button", { name: "Run close" }));
      }

      // The API's sentence, whole, and once.
      const said = await screen.findByText(NOT_OPEN);
      expect(said.closest('[role="alert"]')?.textContent).toContain("Action not available");
      expect(screen.getAllByText(NOT_OPEN)).toHaveLength(1);
      expect(starts).toBe(1);
      // The page shows the period as it is: locked, and no run is offered any more.
      await waitFor(() => {
        expect(screen.queryByRole("button", { name: "Run close" })).toBeNull();
      });
      expect(screen.getByText(NOT_OPEN)).toBeTruthy();
      cleanup();
    }

    // A refusal that is no conflict says nothing about the page's read: the period is not read again.
    let periodReads = 0;
    serve({ runs: [] });
    server.use(
      http.get(apiUrl("/api/v1/periods"), () => {
        periodReads += 1;
        return HttpResponse.json({ items: [period()], next_cursor: null });
      }),
      http.post(apiUrl("/api/v1/close-runs"), () =>
        problemResponse("forbidden", 403, "You do not have permission to do that", {
          detail: "period.close is required for AVM-US.",
        }),
      ),
    );
    open(MAYA);
    const empty = (await screen.findByRole("heading", { name: "No close run for Sep 2026" }))
      .parentElement?.parentElement;
    if (empty === null || empty === undefined) {
      throw new Error("the empty state has no container");
    }
    const before = periodReads;
    expect(before).toBeGreaterThan(0);
    fireEvent.click(within(empty).getByRole("button", { name: "Run close" }));
    expect(await screen.findByText("period.close is required for AVM-US.")).toBeTruthy();
    await new Promise((resolve) => setTimeout(resolve, 250));
    expect(periodReads).toBe(before);
  });

  it("a cancel the API refuses closes its dialog, says why above the run, and the run is read again", async () => {
    // Another member cancelled the run while the dialog was open (04 §16.8): nothing is left to
    // cancel, and the page's read of the run is out of date. A blocked run is not read again on an
    // interval, so the page shows what it is only if the refusal makes it read.
    const NOT_CANCELLABLE =
      "CLS-000031 is CANCELLED. Only a close run that has not ended is cancelled.";
    const blocked = closeRun({
      status: "BLOCKED",
      current_step_code: "RECOMPUTE_DIRTY",
      started_at: "2026-09-12T14:05:00Z",
      job: { id: JOB_ID, state: "SUCCEEDED", progress: { done: 14, total: 14 } },
      steps: steps({ ...FIRST_FOUR, RECOMPUTE_DIRTY: "BLOCKED" }, FIRST_FOUR_COUNTS),
    });
    const cancelIt = async () => {
      fireEvent.click(await screen.findByRole("button", { name: "Cancel close run" }));
      const dialog = await screen.findByRole("alertdialog", {
        name: "Cancel close run CLS-000031?",
      });
      fireEvent.change(within(dialog).getByRole("textbox", { name: /^Reason \(required\)/ }), {
        target: { value: "The SSP of the licences is corrected first." },
      });
      fireEvent.click(within(dialog).getByRole("button", { name: "Cancel close run" }));
    };
    const runs: CloseRun[] = [blocked];
    let cancels = 0;
    serve({ runs });
    server.use(
      http.post(apiUrl(`/api/v1/close-runs/${RUN_ID}/cancel`), () => {
        cancels += 1;
        runs[0] = { ...blocked, status: "CANCELLED", finished_at: "2026-09-12T14:20:00Z" };
        return problemResponse("invalid-transition", 409, "Action not available", {
          detail: NOT_CANCELLABLE,
          errors: [{ field: "status", rule_id: "SM-07", message: NOT_CANCELLABLE }],
        });
      }),
    );
    open(MAYA);
    await cancelIt();

    // The dialog is gone; the sentence stands on the page, above the run it is about.
    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).toBeNull();
    });
    const said = await screen.findByText(NOT_CANCELLABLE);
    expect(said.closest('[role="alert"]')?.textContent).toContain("Action not available");
    expect(cancels).toBe(1);
    // The run as it is: ended, with no command to cancel or resume it.
    await waitFor(() => {
      expect(screen.getByRole("region", { name: "Close run CLS-000031" }).textContent).toContain(
        "Cancelled",
      );
    });
    expect(screen.queryByRole("button", { name: "Cancel close run" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Resume close run" })).toBeNull();
    expect(screen.getByText(NOT_CANCELLABLE)).toBeTruthy();
    cleanup();

    // A refusal that is no conflict says nothing about the page's read: it stays in the dialog, with
    // the command, and the runs are not read again.
    let listReads = 0;
    serve({ runs: [blocked] });
    server.use(
      http.get(apiUrl("/api/v1/close-runs"), () => {
        listReads += 1;
        return HttpResponse.json({ items: [blocked], next_cursor: null });
      }),
      http.post(apiUrl(`/api/v1/close-runs/${RUN_ID}/cancel`), () =>
        problemResponse("forbidden", 403, "You do not have permission to do that", {
          detail: "period.close is required for AVM-US.",
        }),
      ),
    );
    open(MAYA);
    await screen.findByTestId("SF-05-banner-close-run-blocked");
    const before = listReads;
    expect(before).toBeGreaterThan(0);
    await cancelIt();
    const kept = await screen.findByRole("alertdialog", { name: "Cancel close run CLS-000031?" });
    expect(await within(kept).findByText("period.close is required for AVM-US.")).toBeTruthy();
    expect(within(kept).getByRole("button", { name: "Cancel close run" })).toBeTruthy();
    await new Promise((resolve) => setTimeout(resolve, 250));
    expect(listReads).toBe(before);
  });

  it("a running run shows its job's progress and is followed to its end by any reader", async () => {
    const running = closeRun({
      status: "RUNNING",
      current_step_code: "RECOMPUTE_DIRTY",
      started_at: "2026-09-12T14:05:00Z",
      job: { id: JOB_ID, state: "RUNNING", progress: { done: 412, total: 1204 } },
      steps: steps(
        {
          CUTOFF: "SUCCEEDED",
          INTERFACE_COMPLETENESS: "SUCCEEDED",
          EXCEPTION_CHECK: "SUCCEEDED",
          RECOMPUTE_DIRTY: "RUNNING",
        },
        FIRST_FOUR_COUNTS,
      ),
    });
    const runs: CloseRun[] = [running];
    serve({ runs });
    // ROBERT did not start the run and may not read its job: he follows the run.
    open(ROBERT);

    const bar = await screen.findByRole("progressbar", { name: "Close run for AVM-US Sep 2026" });
    expect(bar.getAttribute("aria-valuetext")).toBe("412 of 1,204 contracts");
    const header = screen.getByRole("region", { name: "Close run CLS-000031" });
    expect(header.textContent).toContain("Step 4 of 14: Recompute changed contracts");
    expect(
      within(screen.getByRole("list", { name: "Close run steps" })).getByTestId(
        "SF-05-row-recompute-dirty",
      ).textContent,
    ).toContain("412 of 1,204 contracts");
    // SCR-PERM-02: no command without `period.close`.
    expect(screen.queryByRole("button", { name: "Cancel close run" })).toBeNull();

    // The run ends: read again on its 2 s interval, without a command of this reader.
    runs[0] = closeRun({
      status: "SUCCEEDED",
      current_step_code: null,
      started_at: "2026-09-12T14:05:00Z",
      finished_at: "2026-09-12T14:09:02Z",
      journal_run_id: JOURNAL_RUN_ID,
      job: { id: JOB_ID, state: "SUCCEEDED", progress: { done: 1204, total: 1204 } },
      steps: steps(
        Object.fromEntries(
          CLOSE_RUN_STEP_CODES.map((code) => [code, code === "LOCK" ? "PENDING" : "SUCCEEDED"]),
        ),
        FIRST_FOUR_COUNTS,
      ),
    });
    expect(await screen.findByText("Close run CLS-000031 succeeded.")).toBeTruthy();
    expect(screen.queryByRole("progressbar", { name: "Close run for AVM-US Sep 2026" })).toBeNull();
    expect(screen.getByRole("button", { name: "Open journal run" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Close run CLS-000031" }).textContent).toContain(
      "Succeeded",
    );
  });

  it("run close starts a run from the empty state; an active run is named instead", async () => {
    const runs: CloseRun[] = [];
    const sent: unknown[] = [];
    let active = false;
    serve({ runs });
    server.use(
      http.post(apiUrl("/api/v1/close-runs"), async ({ request }) => {
        sent.push(await request.json());
        if (active) {
          // 04 §16.8: 200 with the run of the entity, book and period that has not ended.
          return HttpResponse.json(runs[0]);
        }
        runs.unshift(closeRun());
        return HttpResponse.json(
          { id: JOB_ID, kind: "CLOSE_RUN", state: "QUEUED" },
          {
            status: 202,
            headers: { Location: `/api/v1/jobs/${JOB_ID}`, "X-Erev-Close-Run-Id": RUN_ID },
          },
        );
      }),
      http.get(apiUrl("/api/v1/jobs/:jobId"), () =>
        HttpResponse.json({
          id: JOB_ID,
          kind: "CLOSE_RUN",
          state: "QUEUED",
          progress: { done: 0, total: null },
          created_at: "2026-09-12T14:05:00Z",
          created_by: MAYA_ACTOR,
          started_at: null,
          finished_at: null,
          problem: null,
          result: null,
        }),
      ),
    );
    open(MAYA);

    // SCR-ST-03.
    expect(await screen.findByRole("heading", { name: "No close run for Sep 2026" })).toBeTruthy();
    expect(
      screen.getByText(
        "A close run recomputes changed contracts, releases schedules and prepares journals for AVM-US.",
      ),
    ).toBeTruthy();
    const tab = screen.getByRole("heading", { name: "No close run for Sep 2026" }).parentElement
      ?.parentElement;
    if (tab === null || tab === undefined) {
      throw new Error("the empty state has no container");
    }
    fireEvent.click(within(tab).getByRole("button", { name: "Run close" }));
    expect(await screen.findByRole("region", { name: "Close run CLS-000031" })).toBeTruthy();
    expect(sent).toEqual([{ entity_code: "AVM-US", book: "ASC606", period_key: "FY2026-P09" }]);
    expect(screen.getByRole("region", { name: "Close run CLS-000031" }).textContent).toContain(
      "Queued",
    );

    // The action bar's "Run close" while that run has not ended: the API answers the run itself.
    active = true;
    fireEvent.click(screen.getByRole("button", { name: "Run close" }));
    expect(await screen.findByText("Close run CLS-000031 is already running.")).toBeTruthy();
    expect(sent).toHaveLength(2);
  });

  it("cancel close run asks for a reason and sends it", async () => {
    const runs: CloseRun[] = [
      closeRun({
        status: "RUNNING",
        current_step_code: "RECOMPUTE_DIRTY",
        started_at: "2026-09-12T14:05:00Z",
        job: { id: JOB_ID, state: "RUNNING", progress: { done: 3, total: 14 } },
        steps: steps(
          {
            CUTOFF: "SUCCEEDED",
            INTERFACE_COMPLETENESS: "SUCCEEDED",
            EXCEPTION_CHECK: "SUCCEEDED",
            RECOMPUTE_DIRTY: "RUNNING",
          },
          FIRST_FOUR_COUNTS,
        ),
      }),
      closeRun({
        id: EARLIER_ID,
        close_run_no: "CLS-000030",
        status: "CANCELLED",
        started_at: "2026-09-11T09:12:00Z",
        finished_at: "2026-09-11T09:16:02Z",
        created_at: "2026-09-11T09:12:00Z",
        job: null,
      }),
    ];
    const cancelled: unknown[] = [];
    serve({ runs });
    server.use(
      http.post(apiUrl(`/api/v1/close-runs/${RUN_ID}/cancel`), async ({ request }) => {
        cancelled.push(await request.json());
        return HttpResponse.json(runs[0]);
      }),
    );
    open(MAYA);

    // The earlier runs of the period, newest first.
    const earlier = await screen.findByRole("table", { name: "Earlier close runs" });
    expect(within(earlier).getByRole("rowheader", { name: "CLS-000030" })).toBeTruthy();
    expect(earlier.textContent).toContain("Cancelled");
    expect(earlier.textContent).toContain("Maya Chen");
    // DS-FMT-24.
    expect(earlier.textContent).toContain("4 min 02 s");

    fireEvent.click(screen.getByRole("button", { name: "Cancel close run" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Cancel close run CLS-000031?" });
    expect(dialog.textContent).toContain(
      "Cancelling stops the run after the current step. Steps already completed stay recorded.",
    );
    // SB-R-05: a reason of at least 10 characters.
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel close run" }));
    expect(cancelled).toHaveLength(0);
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Reason \(required\)/ }), {
      target: { value: "Cost file for September is being corrected." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel close run" }));
    expect(await screen.findByText("Close run CLS-000031 is being cancelled.")).toBeTruthy();
    expect(cancelled).toEqual([{ reason: "Cost file for September is being corrected." }]);
    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).toBeNull();
    });
  });

  it("a blocked run is cancelled at once and says so", async () => {
    const blocked = closeRun({
      status: "BLOCKED",
      current_step_code: "RECOMPUTE_DIRTY",
      started_at: "2026-09-12T14:05:00Z",
      job: { id: JOB_ID, state: "SUCCEEDED", progress: { done: 14, total: 14 } },
      steps: steps(
        {
          CUTOFF: "SUCCEEDED",
          INTERFACE_COMPLETENESS: "SUCCEEDED",
          EXCEPTION_CHECK: "SUCCEEDED",
          RECOMPUTE_DIRTY: "BLOCKED",
        },
        {
          ...FIRST_FOUR_COUNTS,
          RECOMPUTE_DIRTY: {
            counts: { groups_recomputed: 0, groups_quarantined: 3, groups_waived: 0 },
          },
        },
      ),
    });
    const runs: CloseRun[] = [blocked];
    serve({ runs });
    server.use(
      http.post(apiUrl(`/api/v1/close-runs/${RUN_ID}/cancel`), () => {
        // 04 §16.8: a run whose job is not running is `CANCELLED` at once.
        runs[0] = { ...blocked, status: "CANCELLED", finished_at: "2026-09-12T14:20:00Z" };
        return HttpResponse.json(runs[0]);
      }),
    );
    open(MAYA);

    expect((await screen.findByTestId("SF-05-banner-close-run-blocked")).textContent).toContain(
      "Close run CLS-000031 is blocked: 3 contracts were quarantined.",
    );
    fireEvent.click(screen.getByRole("button", { name: "Cancel close run" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Cancel close run CLS-000031?" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Reason \(required\)/ }), {
      target: { value: "The SSP of the licences is corrected first." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel close run" }));
    // The answer is the cancelled run: the page says it was cancelled, not that it is being cancelled.
    expect(await screen.findByText("Close run CLS-000031 was cancelled.")).toBeTruthy();
    await waitFor(() => {
      expect(screen.queryByTestId("SF-05-banner-close-run-blocked")).toBeNull();
    });
    expect(screen.getByRole("region", { name: "Close run CLS-000031" }).textContent).toContain(
      "Cancelled",
    );
    expect(screen.queryByRole("button", { name: "Cancel close run" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Resume close run" })).toBeNull();
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): the commands of a close run show
  // no message at a field, so the banner says every sentence of a refusal; a sentence of `errors[]`
  // that names a member was shown nowhere.
  describe("a refused command", () => {
    const SENTENCE = "The period's cut-off has not been reached.";
    const WHOLE = REFUSAL_TITLE + SENTENCE + REFUSAL_REFERENCE;

    it("Run close from the empty state says every sentence", async () => {
      serve({ runs: [] });
      server.use(
        http.post(apiUrl("/api/v1/close-runs"), () => refusedWith({ period_key: SENTENCE })),
      );
      open(MAYA);
      const empty = (await screen.findByRole("heading", { name: "No close run for Sep 2026" }))
        .parentElement?.parentElement;
      if (empty === null || empty === undefined) {
        throw new Error("the empty state has no container");
      }
      fireEvent.click(within(empty).getByRole("button", { name: "Run close" }));

      expect((await screen.findByText(SENTENCE)).closest('[role="alert"]')?.textContent).toBe(
        WHOLE,
      );
    });

    it("Resume close run says every sentence above the run", async () => {
      serve({ runs: [failedAtRemeasurement()] });
      server.use(
        http.post(apiUrl(`/api/v1/close-runs/${RUN_ID}/resume`), () =>
          refusedWith({ status: SENTENCE }),
        ),
      );
      open(MAYA);
      const failed = await screen.findByTestId("SF-05-banner-close-run-failed");
      fireEvent.click(within(failed).getByRole("button", { name: "Resume close run" }));

      expect((await screen.findByText(SENTENCE)).closest('[role="alert"]')?.textContent).toBe(
        WHOLE,
      );
    });

    it("Cancel close run says every sentence in the dialog", async () => {
      serve({
        runs: [
          closeRun({
            status: "RUNNING",
            current_step_code: "RECOMPUTE_DIRTY",
            started_at: "2026-09-12T14:05:00Z",
            job: { id: JOB_ID, state: "RUNNING", progress: { done: 3, total: 14 } },
            steps: steps({ ...FIRST_FOUR, RECOMPUTE_DIRTY: "RUNNING" }, FIRST_FOUR_COUNTS),
          }),
        ],
      });
      server.use(
        http.post(apiUrl(`/api/v1/close-runs/${RUN_ID}/cancel`), () =>
          refusedWith({ reason: SENTENCE }),
        ),
      );
      open(MAYA);
      fireEvent.click(await screen.findByRole("button", { name: "Cancel close run" }));
      const dialog = await screen.findByRole("alertdialog", {
        name: "Cancel close run CLS-000031?",
      });
      fireEvent.change(within(dialog).getByRole("textbox", { name: /^Reason \(required\)/ }), {
        target: { value: "Cost file for September is being corrected." },
      });
      fireEvent.click(within(dialog).getByRole("button", { name: "Cancel close run" }));

      expect((await within(dialog).findByRole("alert")).textContent).toBe(WHOLE);
    });
  });

  it("a command that does not reach the server says so and changes nothing", async () => {
    serve({ runs: [failedAtRemeasurement()] });
    server.use(
      http.post(apiUrl(`/api/v1/close-runs/${RUN_ID}/resume`), () => HttpResponse.error()),
    );
    open(MAYA);
    const banner = await screen.findByTestId("SF-05-banner-close-run-failed");
    fireEvent.click(within(banner).getByRole("button", { name: "Resume close run" }));
    expect(
      await screen.findByText(
        "The request did not reach the server. Nothing was started or changed. Try again.",
      ),
    ).toBeTruthy();
    // The failed run stands as it was, with its command.
    expect(
      within(screen.getByTestId("SF-05-banner-close-run-failed")).getByRole("button", {
        name: "Resume close run",
      }),
    ).toBeTruthy();
  });

  it("a period that is not open offers no run; a reader sees a failed run without commands", async () => {
    serve({ state: period({ state: "closed", row_version: 9 }), runs: [] });
    open(MAYA);
    expect(await screen.findByRole("heading", { name: "No close run for Sep 2026" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Run close" })).toBeNull();
    cleanup();

    serve({ runs: [failedAtRemeasurement()] });
    open(ROBERT);
    const banner = await screen.findByTestId("SF-05-banner-close-run-failed");
    expect(banner.textContent).toContain(EARLIER_UNPOSTED);
    expect(within(banner).queryByRole("button", { name: "Resume close run" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Run close" })).toBeNull();
    cleanup();

    // The lock decision marks step 14 of the period's succeeded run with the person who decided it.
    const locked = succeeded();
    serve({
      state: period({ state: "closed", row_version: 9 }),
      runs: [
        {
          ...locked,
          steps: locked.steps.map((step) =>
            step.step_code === "LOCK"
              ? {
                  ...step,
                  status: "SUCCEEDED" as const,
                  started_at: "2026-10-01T09:14:00Z",
                  finished_at: "2026-10-01T09:14:00Z",
                  counts: {
                    period_lock_id: "a1000000-0000-4000-8000-000000000001",
                    locked_by: {
                      id: "6d2e9b8f-3c5a-4d7e-8f9b-8a7c6d5e4f3b",
                      kind: "USER",
                      display_name: "Marcus Webb",
                    },
                  },
                }
              : step,
          ),
        },
      ],
    });
    open(ROBERT);
    const lockRow = await screen.findByTestId("SF-05-row-lock");
    expect(lockRow.getAttribute("aria-label")).toBe("Step 14 of 14, Lock, Succeeded");
    expect(lockRow.textContent).toContain("Locked by Marcus Webb");
  });

  it("every column of the quarantined grid holds its header; the four fit at 1440 px", () => {
    // DS-CMP-10, DS-AP-10 (src/test/grid-headers.ts). At 1440 px a grid as wide as the page has
    // 1,158 px beside the open rail; the columns leave a scrollbar's width of it.
    const columns = quarantineColumns({ contractsBuilt: false, itemsBuilt: false, ctxSearch: "" });
    expect(narrowColumns(columns)).toEqual([]);
    expect(columns.map((column) => column.header)).toEqual([
      "Contract",
      "Code",
      "Message",
      "Exception",
    ]);
    expect(columns.reduce((sum, column) => sum + (column.width ?? 0), 0)).toBeLessThanOrEqual(
      1158 - 14,
    );
  });
});
