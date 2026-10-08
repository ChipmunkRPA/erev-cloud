// @vitest-environment jsdom
// SF-05 close cockpit (BUILD_SPEC CLO-23, CLO-6, CLO-7; SCREENS_B §1.1, §1.3; SCREENS SCR-PERM-02,
// SCR-PERM-03, SCR-PERM-05; XR-14): the guarded "Lock period" control and its reason line, the action
// bar of each period state, the blocker rows whose destinations are not built, the journal preview
// check from API strings, and the lock and reopen commands of lane F-CLO-WEB item 1b: "Submit for lock"
// with the refusal that names the failing gates, "Lock period" with the step-up resend, and "Request
// reopen" with its pending-request banner.
import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../../app/router";
import { contextStorageKey } from "../../../app/shell/ContextPill";
import type {
  ChecklistItem,
  PeriodApproval,
  PeriodCockpit,
} from "../../../lib/api/queries/periods";
import type { Period } from "../../../lib/api/queries/tenant";
import {
  installMemoryStorage,
  renderApp,
  renderWithApp,
  signedInMe,
  signedInSession,
} from "../../../test/app";
import { installGridViewport } from "../../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import {
  RECORD_CHANGED,
  REFUSAL_REFERENCE,
  REFUSAL_TITLE,
  refusedWith,
} from "../../../test/refusals";
import { CloseRedirect } from "../cockpit";

installMswServer();
installMemoryStorage();
installGridViewport();
// The frame reads the periods, then the cockpit, before the tab renders.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
});

const COCKPIT_PATH = "/close/AVM-US/ASC606/FY2026-P09";
const STATE_ID = "7c1d2e3f-4a5b-4c6d-8e7f-000000000909";
const AVM_US = {
  id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000001",
  code: "AVM-US",
  name: "Avenmoor Inc. (Demo)",
};

/** Revenue Accountant: `period.close`, no `period.lock`. */
const MAYA = signedInMe({ permissions: ["contract.read", "period.close"] });
/** Controller: `period.close` and `period.lock`. */
const MARCUS = signedInMe({
  user: {
    id: "6d2e9b8f-3c5a-4d7e-8f9b-8a7c6d5e4f3b",
    email: "marcus@example.test",
    display_name: "Marcus Webb",
    status: "ACTIVE",
  },
  permissions: ["contract.read", "period.close", "period.lock"],
});
/** A Controller who may also request a reopen (`period.reopen_request`). */
const CONTROLLER_REOPEN = signedInMe({
  permissions: ["contract.read", "period.close", "period.lock", "period.reopen_request"],
});

/** Revenue Reviewer: `period.reopen_request` (PRD ACT-28). */
const PRIYA_ACTOR = {
  id: "4d3c2b1a-0f9e-4d8c-9b7a-6f5e4d3c2b1a",
  display_name: "Priya Raman",
  kind: "USER" as const,
};
const PRIYA = signedInMe({
  user: {
    id: PRIYA_ACTOR.id,
    email: "priya@example.test",
    display_name: PRIYA_ACTOR.display_name,
    status: "ACTIVE",
  },
  permissions: ["contract.read", "config.read", "period.reopen_request", "period.reopen_approve"],
});
/** The signed-in default user of `signedInMe`, the requester of a lock. */
const MAYA_ACTOR = {
  id: "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a",
  display_name: "Maya Chen",
  kind: "USER" as const,
};
const MARCUS_ACTOR = {
  id: "6d2e9b8f-3c5a-4d7e-8f9b-8a7c6d5e4f3b",
  display_name: "Marcus Webb",
  kind: "USER" as const,
};
const PERMANENT_COMMENT = "Fiscal year 2026 audit is signed; September is final.";
const LOCK_REQUEST_ID = "9e8d7c6b-5a4f-4e3d-8c2b-000000000212";
const REOPEN_REQUEST_ID = "9e8d7c6b-5a4f-4e3d-8c2b-000000000240";
const SUBJECT_HASH = "ab".repeat(32);
const CERTIFICATION = "September 2026 close is complete and reviewed.";
const LOCK_REASON = "September 2026 close complete";
const REOPEN_COMMENT =
  "Costs of 20,500.00 on PRJ-CB-2026-01 incurred on 29 Sep 2026 were omitted from the September cost file.";

/** A pending API-S-Approval whose subject is the period state (04 §16.10). */
function approval(
  type: "PERIOD_LOCK" | "PERIOD_REOPEN",
  preparer: PeriodApproval["preparer"],
): PeriodApproval {
  const lock = type === "PERIOD_LOCK";
  return {
    id: lock ? LOCK_REQUEST_ID : REOPEN_REQUEST_ID,
    request_no: lock ? "APR-000212" : "APR-000240",
    subject: {
      type,
      id: STATE_ID,
      display: "FY2026-P09",
      href: null,
      content_sha256: SUBJECT_HASH,
      row_version: 4,
    },
    summary: `${lock ? "Lock" : "Reopen"} FY2026-P09 for AVM-US in book ASC606`,
    status: "PENDING",
    entity: AVM_US,
    entities: [AVM_US],
    entity_count: 1,
    all_entities: false,
    amount: null,
    attachments: [],
    can_decide: false,
    content_withheld: false,
    reason_code: null,
    comment: null,
    flags: [],
    impact_preview: null,
    routing: { rule_set_version_id: null, rule_key: null },
    preparer,
    submitted_at: lock ? "2026-10-01T08:30:00Z" : "2026-10-02T09:15:00Z",
    decided_at: null,
    voided_at: null,
    void_reason: null,
    current_step_no: 1,
    steps: [
      {
        step_no: 1,
        name: lock ? "Controller" : "Dual approval",
        required_permission: lock ? "period.lock" : "period.reopen_approve",
        min_approvers: lock ? 1 : 2,
        status: "ACTIVE",
        decisions: [],
      },
    ],
  };
}

const NO_BLOCKERS: Period["blockers"] = {
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
};

const GATES = [
  "INTERFACES_COMPLETE",
  "JE_BALANCED",
  "JE_COMPLETE",
  "APPROVALS_CLEARED",
  "EXCEPTIONS_CLEARED",
  "HOLDS_REVIEWED",
  "BATCHES_ACKNOWLEDGED",
  "RECONCILIATIONS_GENERATED",
  "JUDGEMENTS_REVIEWED",
  "DATA_QUALITY_CLEAR",
  "NO_DIRTY_GROUPS",
  "MANUAL_ADJUSTMENTS_CLEARED",
  "CLOSE_RUN_COMPLETED",
  "CONTROLLER_CERTIFIED",
] as const;
/** 04 §16.8 rev 1.106 (supervisor ruling R-55 (c)): the gates no waiver clears; rev 1.172
 * (supervisor ruling R-114 (b)): nor the close run. */
const NEVER_WAIVABLE: readonly string[] = [
  "JE_BALANCED",
  "JE_COMPLETE",
  "CLOSE_RUN_COMPLETED",
  "CONTROLLER_CERTIFIED",
];

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
    blockers: NO_BLOCKERS,
    close_run: null,
    row_version: 3,
    ...overrides,
  };
}

/** The 14 system gates; CONTROLLER_CERTIFIED is FAILED in every case, as the lock certifies
 * ([J] D-88 L7-2-Q-16). `failing` names the other gates that fail. */
function checklist(failing: readonly string[]): ChecklistItem[] {
  return GATES.map((code, index) => {
    const failed = code === "CONTROLLER_CERTIFIED" || failing.includes(code);
    return {
      id: `9a8b7c6d-5e4f-4a3b-8c2d-${String(index + 1).padStart(12, "0")}`,
      code,
      name: code,
      gate_kind: "AUTOMATIC",
      gate_check_code: code,
      is_blocking: true,
      status: failed ? "FAILED" : "PASSED",
      owner: null,
      due_date: "2026-10-05",
      result: { count: failed ? 1 : 0, detail: null, evaluated_at: "2026-09-12T12:00:00Z" },
      signoff: null,
      waiver_approval_request_id: null,
      // 04 API-S-PeriodCockpit rev 1.106 (R-55 (c)): three gates are never waivable.
      is_waivable: !NEVER_WAIVABLE.includes(code),
      row_version: 1,
    };
  });
}

interface Counts {
  readonly vc: number;
  readonly judgements: number;
  readonly adjustments: number;
}

const NO_COUNTS: Counts = { vc: 0, judgements: 0, adjustments: 0 };

function cockpit(
  state: Period,
  items: readonly ChecklistItem[],
  counts: Counts = NO_COUNTS,
): PeriodCockpit {
  return {
    period: state,
    checklist: [...items],
    journal_preview: {
      debit_functional: money("295.69"),
      credit_functional: money("295.69"),
      difference_functional: money("0.00"),
      balanced: true,
      by_account_role: [
        { account_role: "CONTRACT_LIABILITY", debit: money("295.69"), credit: money("0.00") },
        { account_role: "REVENUE", debit: money("0.00"), credit: money("295.69") },
      ],
    },
    kpis: {
      days_to_close_last_three: [
        { period_key: "FY2026-P07", days: 6 },
        { period_key: "FY2026-P08", days: null },
        { period_key: "FY2026-P09", days: null },
      ],
      reconciliations_reviewed: { reviewed: 0, required: 2 },
    },
    derived_blockers: [
      { code: "JOURNAL_RUN_NOT_CALCULATED", count: 1 },
      { code: "RECONCILIATIONS_NOT_GENERATED", count: 2 },
    ],
    // D-90a QA-L9-7: BLK-06 and BLK-15 subtract these counts, the same for every reader.
    pending_requests: [
      { subject_type: "JUDGEMENT_RECORD", count: counts.judgements },
      { subject_type: "MANUAL_ADJUSTMENT", count: counts.adjustments },
    ],
  };
}

/** Every `GET /approvals` the page sent, by its search parameters. */
type ApprovalReads = URLSearchParams[];

function serve(
  state: Period,
  items: readonly ChecklistItem[],
  counts: Counts = NO_COUNTS,
  approvalReads: ApprovalReads = [],
) {
  const empty = () => HttpResponse.json({ items: [], next_cursor: null });
  const counted = (count: number) =>
    HttpResponse.json(
      { items: [], next_cursor: null },
      { headers: { "X-Erev-Total-Count": String(count) } },
    );
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), empty),
    http.get(apiUrl("/api/v1/entities"), empty),
    http.get(apiUrl("/api/v1/books"), empty),
    http.get(apiUrl("/api/v1/jobs"), empty),
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
    http.get(apiUrl("/api/v1/periods/:periodId/cockpit"), () =>
      HttpResponse.json(cockpit(state, items, counts)),
    ),
    http.get(apiUrl("/api/v1/journal-runs"), empty),
    http.get(apiUrl("/api/v1/exceptions"), () => counted(counts.vc)),
    // A reader without approval visibility lists no requests (04 API-R-09), so the approvals list
    // answers 0 for every query: D-90a QA-L9-7 takes BLK-06 and BLK-15 from the cockpit read.
    http.get(apiUrl("/api/v1/approvals"), ({ request }) => {
      approvalReads.push(new URL(request.url).searchParams);
      return counted(0);
    }),
  );
}

describe("SF-05 close cockpit", () => {
  it("lock period disabled with reason line", async () => {
    serve(period(), checklist(["APPROVALS_CLEARED", "EXCEPTIONS_CLEARED"]));
    const { router } = renderApp(COCKPIT_PATH, { me: MARCUS, screenRoutes: SCREEN_ROUTES });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Close · AVM-US · Sep 2026 · ASC 606" }),
    ).toBeTruthy();
    const lock = await screen.findByRole("button", { name: "Lock period" });
    expect(lock.getAttribute("aria-disabled")).toBe("true");
    const reason = screen.getByTestId("SF-05-banner-lock-unavailable");
    expect((lock.getAttribute("aria-describedby") ?? "").split(/\s+/)).toContain(reason.id);
    // [J] D-88 L7-2-Q-16: APPROVALS_CLEARED, EXCEPTIONS_CLEARED and CONTROLLER_CERTIFIED fail; the
    // certification gate is not counted, because the lock certifies.
    expect(reason.textContent).toContain("Lock is not available: 2 close gates have not passed.");
    // The failing gate labels follow as links to their checklist rows (J-13.1).
    expect(
      within(reason)
        .getAllByRole("button")
        .map((link) => link.textContent),
    ).toEqual(["No pending approvals", "Exceptions resolved, waived or dismissed"]);
    // The page writes its context for the context pill (SCR-URL-01 to SCR-URL-03).
    await waitFor(() => {
      expect(router.state.location.search).toBe("?entity=AVM-US&period=FY2026-P09&book=ASC606");
    });
  });

  it("request waiver only on waivable gates", async () => {
    // SCREENS_B §1.1 rev 1.28 (supervisor ruling R-55 (c)): "Request waiver" is offered on a row
    // that has not passed only when `is_waivable` — never for journal balancing, journal
    // completeness or the controller certification, whose waiver the server refuses; rev 1.50
    // (supervisor ruling R-114 (b)): nor for the close run.
    serve(
      period(),
      checklist(["JE_BALANCED", "JE_COMPLETE", "EXCEPTIONS_CLEARED", "CLOSE_RUN_COMPLETED"]),
    );
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const waivable = await screen.findByTestId("SF-05-row-exceptions-cleared");
    expect(within(waivable).getByRole("button", { name: "Request waiver" })).toBeTruthy();
    for (const key of [
      "je-balanced",
      "je-complete",
      "close-run-completed",
      "controller-certified",
    ]) {
      const row = screen.getByTestId(`SF-05-row-${key}`);
      // The row has not passed, and carries no waiver action.
      expect(row.textContent).toContain("Not passed");
      expect(within(row).queryByRole("button", { name: "Request waiver" })).toBeNull();
    }
    expect(screen.getAllByRole("button", { name: "Request waiver" })).toHaveLength(1);
  });

  it("end soft close says where the period returns", async () => {
    // SCREENS_B §1.1 rev 1.49 (04 §16.8 rev 1.170): the soft close of a period that was never
    // locked returns it to open; a period that has been locked before is under its REOPEN record
    // and returns to reopened, where postings keep needing a second person's approval.
    const dialog = async () => {
      fireEvent.click(await screen.findByRole("button", { name: "More close actions" }));
      fireEvent.click(screen.getByRole("menuitem", { name: "End soft close" }));
      return await screen.findByRole("alertdialog", { name: "End soft close for Sep 2026?" });
    };
    serve(period({ state: "closing", row_version: 4 }), checklist([]));
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    expect((await dialog()).textContent).toContain(
      "The period returns to open. Manual adjustments and imports follow the normal rules again.",
    );
    cleanup();

    const reopen = {
      id: "7c2d3e4f-5a6b-4c7d-8e9f-0000000000a1",
      kind: "REOPEN",
      created_at: "2026-10-09T15:00:00Z",
      created_by: {
        id: "5c2d3e4f-5a6b-4c7d-8e9f-0000000000b2",
        kind: "USER",
        display_name: "Elena",
      },
      ledger_head_chain_seq: null,
      snapshot_manifest_sha256: null,
    } as const;
    serve(period({ state: "closing", row_version: 6, current_lock: reopen }), checklist([]));
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    const reopened = await dialog();
    expect(reopened.textContent).toContain(
      "The period returns to reopened. Postings into it keep needing a second person's approval.",
    );
    expect(reopened.textContent).not.toContain("The period returns to open.");
  });

  it("a soft close after a reopen still says that lines are post-reopen and the re-lock is compared", async () => {
    // SCREENS_B §1.1 rev 1.61 (PRD BR-CLS-06 rev 1.113, BR-CLS-07, REQ-CLS-011 rev 1.99; supervisor
    // rulings R-117 (c), R-118 (c) and R-119 (h)): a soft close does not end what a reopen began.
    // While the period's current lock record is its REOPEN — locked once, not locked now — a line
    // posted is a post-reopen line and the re-lock produces its difference report; the cockpit says
    // so under the soft-close banner. The second approver joins the copy with CLO-REOPEN-APPROVAL-1.
    const reopen = {
      id: "7c2d3e4f-5a6b-4c7d-8e9f-0000000000a1",
      kind: "REOPEN",
      created_at: "2026-10-09T15:00:00Z",
      created_by: {
        id: "5c2d3e4f-5a6b-4c7d-8e9f-0000000000b2",
        kind: "USER",
        display_name: "Elena",
      },
      ledger_head_chain_seq: null,
      snapshot_manifest_sha256: null,
    } as const;
    serve(period({ state: "closing", row_version: 6, current_lock: reopen }), checklist([]));
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    expect((await screen.findByTestId("SF-05-banner-soft-close")).textContent).toContain(
      "Soft close: only users with the lock permission may submit manual adjustments. Imports wait for review.",
    );
    expect(screen.getByTestId("SF-05-banner-reopened-closing").textContent).toContain(
      "Sep 2026 was reopened and is not locked again yet. Lines posted now are flagged post-reopen, and re-lock produces a diff report.",
    );
    // A control the product does not hold for every posting there is not promised.
    expect(screen.getByTestId("SF-05-banner-reopened-closing").textContent).not.toContain(
      "second approver",
    );
    cleanup();

    // The soft close of a period that was never locked: the soft-close banner alone.
    serve(period({ state: "closing", row_version: 4 }), checklist([]));
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    await screen.findByTestId("SF-05-banner-soft-close");
    expect(screen.queryByTestId("SF-05-banner-reopened-closing")).toBeNull();
    expect(screen.queryByText(/was reopened/)).toBeNull();
    cleanup();

    // Reopened and not in soft close: the banner of the state, as before, and no second one.
    serve(period({ state: "reopened", row_version: 5, current_lock: reopen }), checklist([]));
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    expect(
      await screen.findByText(
        "Sep 2026 is reopened. Every posting needs a second approver, and lines are flagged post-reopen. Re-lock produces a diff report.",
      ),
    ).toBeTruthy();
    expect(screen.queryByTestId("SF-05-banner-reopened-closing")).toBeNull();
    expect(screen.queryByTestId("SF-05-banner-soft-close")).toBeNull();
  });

  it("action bar per state", async () => {
    // Every close command is built: "Run close" (CLO-19, CLO-24), "Submit for lock" and "Permanently
    // lock" (CLO-6), "Request reopen" (CLO-7).
    // `open`: primary "Start soft close", secondary "Run close"; no "Lock period" without `period.lock`
    // (SCR-PERM-02).
    serve(period({ state: "open" }), checklist([]));
    const opened = renderApp(`${COCKPIT_PATH}?entity=AVM-US&period=FY2026-P09&book=ASC606`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    const start = await screen.findByRole("button", { name: "Start soft close" });
    expect(start.className).toContain("bg-accent-solid");
    expect(screen.getByRole("button", { name: "Run close" }).className).not.toContain(
      "bg-accent-solid",
    );
    expect(screen.queryByRole("button", { name: "Lock period" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Submit for lock" })).toBeNull();
    // The overflow of an open period: "Close several entities" opens SF-05:multi-entity with the
    // period and the book of this cockpit (CLO-24).
    fireEvent.click(screen.getByRole("button", { name: "More close actions" }));
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      "Close several entities",
    ]);
    fireEvent.click(screen.getByRole("menuitem", { name: "Close several entities" }));
    await waitFor(() => {
      expect(opened.router.state.location.pathname).toBe("/close/multi-entity");
    });
    expect(opened.router.state.location.search).toBe(
      "?entity=AVM-US&period=FY2026-P09&book=ASC606",
    );
    cleanup();

    // `closing` without a pending request: the soft close banner, "Submit for lock" (J-13.13) and
    // "End soft close" in the overflow.
    serve(period({ state: "closing", row_version: 4 }), checklist([]));
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    expect((await screen.findByTestId("SF-05-banner-soft-close")).textContent).toContain(
      "Soft close: only users with the lock permission may submit manual adjustments.",
    );
    fireEvent.click(screen.getByRole("button", { name: "More close actions" }));
    // DS-CMP-28 lists a destructive item last, after the others.
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      "Close several entities",
      "End soft close",
    ]);
    // SCREENS_B §1.1 action bar: in soft close "Run close" is the primary action.
    expect(screen.getByRole("button", { name: "Run close" }).className).toContain(
      "bg-accent-solid",
    );
    expect(screen.getByRole("button", { name: "Submit for lock" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Start soft close" })).toBeNull();
    // A viewer without `period.lock` sees no "Lock period".
    expect(screen.queryByRole("button", { name: "Lock period" })).toBeNull();
    cleanup();

    // The same state for a `period.lock` holder: the guarded control renders, aria-disabled.
    serve(period({ state: "closing", row_version: 4 }), checklist([]));
    renderApp(COCKPIT_PATH, { me: MARCUS, screenRoutes: SCREEN_ROUTES });
    const guarded = await screen.findByRole("button", { name: "Lock period" });
    expect(guarded.getAttribute("aria-disabled")).toBe("true");
    // [J] D-88 L7-2-Q-16: only CONTROLLER_CERTIFIED fails and no lock request is pending
    // (L7-2-Q-15 i).
    expect(screen.getByTestId("SF-05-banner-lock-unavailable").textContent).toBe(
      "Lock is not available: the period has not been submitted for lock.",
    );
    expect(screen.getByRole("button", { name: "Run close" })).toBeTruthy();
    // A Controller holds `period.close` too, so the submission is offered beside the guarded lock.
    expect(screen.getByRole("button", { name: "Submit for lock" })).toBeTruthy();
    cleanup();

    // `closed` for a holder of `period.lock` and `period.reopen_request`: "Request reopen" (J-14.1)
    // and, in the overflow, "Permanently lock".
    serve(period({ state: "closed", row_version: 5 }), checklist([]));
    renderApp(COCKPIT_PATH, { me: CONTROLLER_REOPEN, screenRoutes: SCREEN_ROUTES });
    await screen.findByRole("heading", { level: 1, name: "Close · AVM-US · Sep 2026 · ASC 606" });
    expect(await screen.findByRole("button", { name: "Request reopen" })).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "More close actions" }));
    expect(
      screen.getByRole("menuitem", { name: "Permanently lock" }).getAttribute("aria-disabled"),
    ).toBeNull();
    cleanup();

    // The same period for a Revenue Accountant: neither `period.reopen_request` nor `period.lock`, so
    // no reopen control and no overflow (SCR-PERM-02; PRD ACT-27, ACT-28).
    serve(period({ state: "closed", row_version: 5 }), checklist([]));
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    await screen.findByRole("heading", { level: 1, name: "Close · AVM-US · Sep 2026 · ASC 606" });
    // The blockers table renders once the period and its counts are read.
    await screen.findByRole("table", { name: /^Blockers \(\d+\)$/ });
    expect(screen.queryByRole("button", { name: "Request reopen" })).toBeNull();
    expect(screen.queryByRole("button", { name: "More close actions" })).toBeNull();
  });

  it("blocker rows without unbuilt links", async () => {
    serve(
      period({
        blockers: {
          ...NO_BLOCKERS,
          approvals_pending: 3,
          exceptions_open: 3,
          judgements_unreviewed: 2,
          manual_adjustments_pending: 2,
        },
      }),
      checklist(["APPROVALS_CLEARED"]),
      { vc: 1, judgements: 1, adjustments: 1 },
    );
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    // 3 approvals, 2 exceptions, 1 VC element, 1 judgement, 1 adjustment, 1 run, 2 reconciliations.
    const table = await screen.findByRole("table", { name: "Blockers (11)" });
    const judgements = within(table).getByTestId("SF-05-row-judgements-unreviewed");
    expect(judgements.textContent).toContain("Judgements not reviewed");
    expect(within(judgements).getByRole("cell", { name: "1" })).toBeTruthy();
    // BLK-06 opens SF-08:report `judgement_register` with `p.status=SUBMITTED` (RPS-11).
    expect(
      within(judgements)
        .getByRole("link", { name: "Judgements not reviewed, 1, open Judgement register" })
        .getAttribute("href"),
    ).toBe(
      "/reports/judgement_register?p.status=SUBMITTED&entity=AVM-US&period=FY2026-P09&book=ASC606",
    );
    const adjustments = within(table).getByTestId("SF-05-row-manual-adjustments-pending");
    expect(adjustments.textContent).toContain("Manual adjustments pending");
    expect(within(adjustments).getByRole("cell", { name: "1" })).toBeTruthy();
    // BLK-15 opens SF-08:report `manual_adjustment_register` with `p.status=DRAFT` (RPS-8).
    expect(
      within(adjustments)
        .getByRole("link", {
          name: "Manual adjustments pending, 1, open Manual adjustment register",
        })
        .getAttribute("href"),
    ).toBe(
      "/reports/manual_adjustment_register?p.status=DRAFT&entity=AVM-US&period=FY2026-P09&book=ASC606",
    );
    // BLK-13 opens SF-05:reconciliations in the period's context, now that CLO-25 built the route.
    expect(
      within(within(table).getByTestId("SF-05-row-reconciliations-missing"))
        .getByRole("link", { name: "Reconciliations not generated, 2, open Reconciliations" })
        .getAttribute("href"),
    ).toBe(
      "/close/AVM-US/ASC606/FY2026-P09/reconciliations?entity=AVM-US&period=FY2026-P09&book=ASC606",
    );
    // Built destinations keep their links.
    expect(
      within(table).getByRole("link", { name: "Pending approvals, 3, open Approvals" }),
    ).toBeTruthy();
    expect(
      within(table)
        .getByRole("link", { name: "Journal run not calculated, 1, open Journals" })
        .getAttribute("href"),
    ).toBe("/journals?entity=AVM-US&period=FY2026-P09&book=ASC606");
    expect(
      within(within(table).getByTestId("SF-05-row-exceptions")).getByRole("cell", { name: "2" }),
    ).toBeTruthy();
    // BLK-02 opens the queue on the list its count is made of (§1.1 rev 1.66; 04 §16.14): the items
    // that hold this period's lock, asked by the period's id. The link names no entity, period or
    // status, which left out every item that names no entity or no period.
    expect(
      within(within(table).getByTestId("SF-05-row-exceptions"))
        .getByRole("link", { name: "Exceptions, 2, open Exceptions" })
        .getAttribute("href"),
    ).toBe(`/data/exceptions?blocking=${STATE_ID}`);
    // KPI strip: the sum of the visible rows, reconciliations reviewed and three periods.
    const strip = screen.getByTestId("SF-05-kpi-strip");
    expect(within(strip).getByRole("heading", { name: "Close status" })).toBeTruthy();
    const figures = within(strip).getAllByRole("definition");
    expect(figures[0]?.textContent).toBe("11");
    // The checklist KPI still counts all 14 items, certification included (L7-2-Q-16).
    expect(figures[1]?.textContent).toBe("12 of 14 passed");
    expect(strip.textContent).toContain("0 of 2");
    expect(
      within(screen.getByTestId("SF-05-kpi-days-to-close")).getAllByRole("definition"),
    ).toHaveLength(3);
  });

  it("blocker rows and tabs follow the built routes", async () => {
    // XR-14: the cockpit's row of the SF-16 sync runs names no destination (BLK-07); BLK-08 and BLK-09
    // open SF-05:close-run (CLO-24) and BLK-14 SF-05:reconciliations (CLO-25).
    serve(
      period({
        blockers: {
          ...NO_BLOCKERS,
          interface_failures: 1,
          jobs_failed: 1,
          groups_dirty: 4,
          reconciliations_unsigned: 1,
        },
      }),
      checklist(["RECONCILIATIONS_GENERATED"]),
    );
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    // 1 interface batch, 1 job, 4 contracts, 1 run, 2 reconciliations missing and 1 not signed.
    const table = await screen.findByRole("table", { name: "Blockers (10)" });
    expect(
      within(within(table).getByTestId("SF-05-row-interface-failures")).queryByRole("link"),
    ).toBeNull();
    const closeRun =
      "/close/AVM-US/ASC606/FY2026-P09/close-run?entity=AVM-US&period=FY2026-P09&book=ASC606";
    expect(
      within(table)
        .getByRole("link", { name: "Failed jobs, 1, open Close run" })
        .getAttribute("href"),
    ).toBe(closeRun);
    expect(
      within(table)
        .getByRole("link", {
          name: "Contracts changed since the last close run, 4, open Close run",
        })
        .getAttribute("href"),
    ).toBe(closeRun);
    expect(
      within(table)
        .getByRole("link", { name: "Reconciliations not signed, 1, open Reconciliations" })
        .getAttribute("href"),
    ).toBe(
      "/close/AVM-US/ASC606/FY2026-P09/reconciliations?entity=AVM-US&period=FY2026-P09&book=ASC606",
    );
    // The route tabs list the built tabs only, in the order of SCREENS_B §1.
    const tabs = screen.getByRole("navigation", { name: "Close of Sep 2026" });
    expect(
      within(tabs)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["Checklist", "Close run", "Journal preview", "Reconciliations", "History"]);
  });

  it("BLK-06 and BLK-15 do not depend on the reader", async () => {
    // D-90a QA-L9-7 (L8-C-Q-2; SCREENS_B §1.1 rev 1.3): BLK-06 and BLK-15 subtract API-S-PeriodCockpit
    // `pending_requests`, so an approver and a viewer whose approvals list is empty read the same two
    // rows. BLK-03 still reads the permission-filtered `GET /exceptions` count and is not covered here.
    const reviewer = signedInMe({
      user: {
        id: "4d3c2b1a-0f9e-4d8c-9b7a-6f5e4d3c2b1a",
        email: "priya@example.test",
        display_name: "Priya Raman",
        status: "ACTIVE",
      },
      permissions: ["contract.read", "config.read", "judgement.review", "adjustment.approve"],
    });
    const viewer = signedInMe({
      user: {
        id: "1f2e3d4c-5b6a-4978-8a9b-0c1d2e3f4a5b",
        email: "robert@example.test",
        display_name: "Robert Lang",
        status: "ACTIVE",
      },
      permissions: ["contract.read", "config.read"],
    });
    const state = period({
      blockers: {
        ...NO_BLOCKERS,
        approvals_pending: 2,
        judgements_unreviewed: 1,
        manual_adjustments_pending: 1,
      },
    });
    const captions: (string | null)[] = [];
    for (const me of [reviewer, viewer]) {
      const reads: URLSearchParams[] = [];
      serve(
        state,
        checklist(["APPROVALS_CLEARED"]),
        { vc: 0, judgements: 1, adjustments: 1 },
        reads,
      );
      renderApp(COCKPIT_PATH, { me, screenRoutes: SCREEN_ROUTES });

      // The rows render once the blocker counts are read; no `GET /approvals` read feeds them.
      const table = await screen.findByRole("table", { name: /^Blockers \(\d+\)$/ });
      expect(
        reads
          .filter((params) =>
            params
              .getAll("subject_type")
              .some((type) => type === "JUDGEMENT_RECORD" || type === "MANUAL_ADJUSTMENT"),
          )
          .map((params) => params.toString()),
      ).toEqual([]);
      // 2 approvals, 1 run and 2 reconciliations; the judgement and the adjustment are in review.
      expect(screen.getByRole("table", { name: "Blockers (5)" })).toBe(table);
      captions.push(table.querySelector("caption")?.textContent ?? null);
      expect(within(table).queryByTestId("SF-05-row-judgements-unreviewed")).toBeNull();
      expect(within(table).queryByTestId("SF-05-row-manual-adjustments-pending")).toBeNull();
      cleanup();
    }
    expect(captions[0]).not.toBeNull();
    expect(captions[1]).toBe(captions[0]);
  });

  it("submit for lock names the failing gates, keeps the comment, then shows the request", async () => {
    const sent: { readonly ifMatch: string | null; readonly body: unknown }[] = [];
    let requested = false;
    const state = period({ state: "closing", row_version: 4 });
    serve(state, checklist(["APPROVALS_CLEARED", "EXCEPTIONS_CLEARED"]));
    server.use(
      http.get(apiUrl("/api/v1/approvals"), () =>
        HttpResponse.json({
          items: requested ? [approval("PERIOD_LOCK", MAYA_ACTOR)] : [],
          next_cursor: null,
        }),
      ),
      http.post(apiUrl(`/api/v1/periods/${STATE_ID}/request-lock`), async ({ request }) => {
        sent.push({ ifMatch: request.headers.get("If-Match"), body: await request.json() });
        if (sent.length === 1) {
          // 04 §16.8; BS4-D-08: one errors[] entry per failing gate, `rule_id` = the gate check code.
          return problemResponse("close-gates-failed", 409, "Period cannot be locked", {
            detail:
              "2 close gates have not passed: No pending approvals, Exceptions resolved, waived or dismissed.",
            errors: [
              { field: null, rule_id: "APPROVALS_CLEARED", message: "Pending approvals: 3" },
              { field: null, rule_id: "EXCEPTIONS_CLEARED", message: "Open exceptions: 2" },
            ],
          });
        }
        requested = true;
        return HttpResponse.json({ approval_request_id: LOCK_REQUEST_ID, gate_results: [] });
      }),
    );
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    fireEvent.click(await screen.findByRole("button", { name: "Submit for lock" }));
    const dialog = await screen.findByRole("dialog", { name: "Submit Sep 2026 for lock" });
    // The static "Close gates" table lists every blocking gate with its chip.
    const gates = within(dialog).getByRole("table", { name: "Close gates" });
    expect(within(gates).getAllByRole("row")).toHaveLength(GATES.length + 1);
    const comment = within(dialog).getByRole("textbox", {
      name: /^Certification comment \(required\)/,
    });
    // BR-PLT-08: at least 10 characters, reported on submit; nothing is sent.
    fireEvent.change(comment, { target: { value: "Done" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Submit for lock" }));
    expect(await within(dialog).findByText("Enter at least 10 characters.")).toBeTruthy();
    expect(sent).toHaveLength(0);
    fireEvent.change(comment, { target: { value: CERTIFICATION } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Submit for lock" }));

    // ERR-14: the count and each failing gate as a link; the typed comment stays.
    const refusal = await within(dialog).findByRole("alert");
    expect(refusal.textContent).toContain("2 close gates have not passed:");
    expect(
      within(refusal)
        .getAllByRole("button")
        .map((link) => link.textContent),
    ).toEqual(["No pending approvals", "Exceptions resolved, waived or dismissed"]);
    expect((comment as HTMLTextAreaElement).value).toBe(CERTIFICATION);
    expect(sent).toEqual([{ ifMatch: '"r4"', body: { certification_comment: CERTIFICATION } }]);

    // The gates pass on the second attempt: the toast, then the pending request of the period.
    fireEvent.click(within(dialog).getByRole("button", { name: "Submit for lock" }));
    expect(
      await screen.findByText(
        "Submitted Sep 2026 for lock. A Controller other than you must lock it.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("dialog", { name: "Submit Sep 2026 for lock" })).toBeNull();
    expect(
      await screen.findByText("Submitted for lock by Maya Chen on 01 Oct 2026 08:30 UTC."),
    ).toBeTruthy();
    expect(
      screen.getAllByRole("link", { name: "View lock request" })[0]?.getAttribute("href"),
    ).toBe(`/approvals/requests/${LOCK_REQUEST_ID}`);
    // One request at a time: the submission is not offered again while it is pending.
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Submit for lock" })).toBeNull();
    });
  });

  it("lock period sends the approval again after the step-up, with the same key", async () => {
    const keys: (string | null)[] = [];
    const bodies: unknown[] = [];
    const state = period({ state: "closing", row_version: 4 });
    serve(state, checklist([]));
    server.use(
      http.get(apiUrl("/api/v1/approvals"), () =>
        HttpResponse.json({ items: [approval("PERIOD_LOCK", MAYA_ACTOR)], next_cursor: null }),
      ),
      http.post(apiUrl(`/api/v1/approvals/${LOCK_REQUEST_ID}/approve`), async ({ request }) => {
        keys.push(request.headers.get("Idempotency-Key"));
        bodies.push(await request.json());
        if (keys.length === 1) {
          return problemResponse("mfa-step-up-required", 403, "Confirm with your authenticator", {
            detail: "Enter a code from your authenticator app to continue.",
          });
        }
        return HttpResponse.json({ ...approval("PERIOD_LOCK", MAYA_ACTOR), status: "APPROVED" });
      }),
      http.post(apiUrl("/api/v1/session/mfa"), () =>
        HttpResponse.json({ ...signedInSession(), recovery_codes_remaining: null }),
      ),
    );
    renderApp(COCKPIT_PATH, { me: MARCUS, screenRoutes: SCREEN_ROUTES });

    // A pending request of another user and every gate passed: the decider's primary action.
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Lock period" }).getAttribute("aria-disabled"),
      ).toBeNull();
    });
    fireEvent.click(screen.getByRole("button", { name: "Lock period" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Lock Sep 2026 for AVM-US?" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Reason \(required\)/ }), {
      target: { value: LOCK_REASON },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Lock period" }));

    // SCR-PERM-05 (J-13.14 "a fresh TOTP"): the step-up, then the same approval again.
    const stepUp = await screen.findByRole("dialog", { name: "Confirm with your authenticator" });
    fireEvent.change(within(stepUp).getByRole("textbox", { name: "Authentication code" }), {
      target: { value: "123456" },
    });
    fireEvent.click(within(stepUp).getByRole("button", { name: "Confirm" }));

    expect(await screen.findByText("AVM-US Sep 2026 locked.")).toBeTruthy();
    expect(keys).toHaveLength(2);
    expect(keys[0]).not.toBeNull();
    expect(keys[1]).toBe(keys[0]);
    expect(bodies).toEqual([
      { subject_content_sha256: SUBJECT_HASH, comment: LOCK_REASON },
      { subject_content_sha256: SUBJECT_HASH, comment: LOCK_REASON },
    ]);
  });

  it("lock period shows the refusals of the decision and offers Reload on a stale request", async () => {
    let answer: "self" | "stale" = "self";
    serve(period({ state: "closing", row_version: 4 }), checklist([]));
    server.use(
      http.get(apiUrl("/api/v1/approvals"), () =>
        HttpResponse.json({ items: [approval("PERIOD_LOCK", MAYA_ACTOR)], next_cursor: null }),
      ),
      http.post(apiUrl(`/api/v1/approvals/${LOCK_REQUEST_ID}/approve`), () =>
        answer === "self"
          ? problemResponse("self-approval", 403, "Self-approval not allowed", {
              detail: "You prepared this item, so another user must approve it.",
            })
          : problemResponse("stale-approval", 409, "Approval voided", {
              detail:
                "This item changed after submission, so the approval request was voided. Review the latest version.",
            }),
      ),
    );
    renderApp(COCKPIT_PATH, { me: MARCUS, screenRoutes: SCREEN_ROUTES });

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Lock period" }).getAttribute("aria-disabled"),
      ).toBeNull();
    });
    fireEvent.click(screen.getByRole("button", { name: "Lock period" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Lock Sep 2026 for AVM-US?" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Reason \(required\)/ }), {
      target: { value: LOCK_REASON },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Lock period" }));
    // ERR-02.
    expect(
      await within(dialog).findByText("You prepared this item, so another user must approve it."),
    ).toBeTruthy();

    answer = "stale";
    fireEvent.click(within(dialog).getByRole("button", { name: "Lock period" }));
    // ERR-04 with "Reload", which reads the period again and closes the dialog.
    expect(
      await within(dialog).findByText(
        "This item changed after submission, so the approval request was voided. Review the latest version.",
      ),
    ).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Reload" }));
    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).toBeNull();
    });
  });

  it("lock period treats a lock conflict as busy: the warning of ERR-52, then a new key locks", async () => {
    const keys: (string | null)[] = [];
    serve(period({ state: "closing", row_version: 4 }), checklist([]));
    server.use(
      http.get(apiUrl("/api/v1/approvals"), () =>
        HttpResponse.json({ items: [approval("PERIOD_LOCK", MAYA_ACTOR)], next_cursor: null }),
      ),
      http.post(apiUrl(`/api/v1/approvals/${LOCK_REQUEST_ID}/approve`), ({ request }) => {
        keys.push(request.headers.get("Idempotency-Key"));
        // 04 DB-07 (rev 1.113): the decision does not wait for the next period's row.
        return keys.length === 1
          ? problemResponse("lock-conflict", 409, "Another change was in progress", {
              detail:
                "Another change to the same records was being saved at the same moment, so nothing was saved. Resubmit the request.",
            })
          : HttpResponse.json({ ...approval("PERIOD_LOCK", MAYA_ACTOR), status: "APPROVED" });
      }),
    );
    renderApp(COCKPIT_PATH, { me: MARCUS, screenRoutes: SCREEN_ROUTES });

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Lock period" }).getAttribute("aria-disabled"),
      ).toBeNull();
    });
    fireEvent.click(screen.getByRole("button", { name: "Lock period" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Lock Sep 2026 for AVM-US?" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Reason \(required\)/ }), {
      target: { value: LOCK_REASON },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Lock period" }));

    // Busy, not failed: a warning that is a status, with the copy of ERR-52, and no alert.
    const busy = await within(dialog).findByRole("status");
    expect(busy.getAttribute("data-tone")).toBe("warning");
    expect(
      within(busy).getByRole("heading", { name: "Another change was in progress" }),
    ).toBeTruthy();
    expect(busy.textContent).toContain(
      "Another change to the same records was being saved at the same moment, so nothing was saved. Resubmit the request.",
    );
    expect(within(dialog).queryByRole("alert")).toBeNull();
    // The reason stays. The API keeps the 409 as the answer of its key (dev-guide DG-KRN-IDEM-03;
    // supervisor ruling R-97 (6)), so the next press is decided only under a new key.
    expect(
      within(dialog).getByRole<HTMLTextAreaElement>("textbox", { name: /^Reason \(required\)/ })
        .value,
    ).toBe(LOCK_REASON);
    fireEvent.click(within(dialog).getByRole("button", { name: "Lock period" }));
    expect(await screen.findByText("AVM-US Sep 2026 locked.")).toBeTruthy();
    expect(keys).toHaveLength(2);
    expect(keys[0]).not.toBeNull();
    expect(keys[1]).not.toBeNull();
    expect(keys[1]).not.toBe(keys[0]);
  });

  it("the order of periods: an earlier postable period blocks the lock and its request; periods open in order", async () => {
    const august = period({
      id: "7c1d2e3f-4a5b-4c6d-8e7f-000000000908",
      state: "open",
      row_version: 2,
      is_first_open: false,
      period: {
        id: "1c2d3e4f-5a6b-4c7d-8e9f-000000000008",
        period_key: "FY2026-P08",
        name: "Aug 2026",
        fiscal_year: 2026,
        period_no: 8,
        quarter_no: 3,
        start_date: "2026-08-01",
        end_date: "2026-08-31",
      },
    });
    const withAugust = (september: Period) =>
      server.use(
        http.get(apiUrl("/api/v1/periods"), () =>
          HttpResponse.json({ items: [august, september], next_cursor: null }),
        ),
      );
    const ORDER = "Lock Aug 2026 first. An earlier period of AVM-US in book ASC 606 is not closed.";

    // BR-CLS-08 (ERR-65) at the request: the preparer reads the reason and is led to the earlier period.
    const closing = period({ state: "closing", row_version: 4 });
    serve(closing, checklist([]));
    withAugust(closing);
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    const submit = await screen.findByRole("button", { name: "Submit for lock" });
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Submit for lock" }).getAttribute("aria-disabled"),
      ).toBe("true");
    });
    const reason = screen.getByTestId("SF-05-banner-lock-unavailable");
    expect(reason.textContent).toContain(ORDER);
    expect(
      screen.getByRole("button", { name: "Submit for lock" }).getAttribute("aria-describedby"),
    ).toContain(reason.id);
    expect(within(reason).getByRole("link", { name: "Go to Aug 2026" }).getAttribute("href")).toBe(
      "/close/AVM-US/ASC606/FY2026-P08?entity=AVM-US&period=FY2026-P08&book=ASC606",
    );
    fireEvent.click(submit);
    expect(screen.queryByRole("dialog", { name: "Submit Sep 2026 for lock" })).toBeNull();
    cleanup();

    // And at the decision: every gate has passed and a request waits, yet the lock is not offered.
    serve(closing, checklist([]));
    withAugust(closing);
    server.use(
      http.get(apiUrl("/api/v1/approvals"), () =>
        HttpResponse.json({ items: [approval("PERIOD_LOCK", MAYA_ACTOR)], next_cursor: null }),
      ),
    );
    renderApp(COCKPIT_PATH, { me: MARCUS, screenRoutes: SCREEN_ROUTES });
    await waitFor(() => {
      expect(screen.getByTestId("SF-05-banner-lock-unavailable").textContent).toContain(ORDER);
    });
    const lock = screen.getByRole("button", { name: "Lock period" });
    expect(lock.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(lock);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    cleanup();

    // An earlier period that is closed, or still future, blocks nothing.
    const lockedAugust = { ...august, state: "closed" as const };
    serve(closing, checklist([]));
    server.use(
      http.get(apiUrl("/api/v1/periods"), () =>
        HttpResponse.json({ items: [lockedAugust, closing], next_cursor: null }),
      ),
    );
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    const free = await screen.findByRole("button", { name: "Submit for lock" });
    expect(free.getAttribute("aria-disabled")).toBeNull();
    expect(screen.queryByTestId("SF-05-banner-lock-unavailable")).toBeNull();
    cleanup();

    // SM-07: a period does not open before the one before it.
    const futureAugust = { ...august, state: "future" as const };
    const futureSeptember = period({ state: "future", row_version: 1, is_first_open: false });
    serve(futureSeptember, checklist([]));
    server.use(
      http.get(apiUrl("/api/v1/periods"), () =>
        HttpResponse.json({ items: [futureAugust, futureSeptember], next_cursor: null }),
      ),
    );
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    const open = await screen.findByRole("button", { name: "Open period" });
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Open period" }).getAttribute("aria-disabled"),
      ).toBe("true");
    });
    const order = screen.getByTestId("SF-05-banner-open-unavailable");
    expect(order.textContent).toContain("Open Aug 2026 first.");
    expect(within(order).getByRole("link", { name: "Go to Aug 2026" }).getAttribute("href")).toBe(
      "/close/AVM-US/ASC606/FY2026-P08?entity=AVM-US&period=FY2026-P08&book=ASC606",
    );
    fireEvent.click(open);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("request reopen sends the reason and the comment, then shows the pending request", async () => {
    const sent: { readonly ifMatch: string | null; readonly body: unknown }[] = [];
    const withdrawn: unknown[] = [];
    const reviewedJudgementId = "3c4d5e6f-7081-4b92-8ca3-000000000502";
    let pending: PeriodApproval | null = null;
    serve(period({ state: "closed", row_version: 5 }), checklist([]));
    server.use(
      http.get(apiUrl("/api/v1/judgements"), ({ request }) => {
        const query = new URL(request.url).searchParams;
        expect(query.get("entity_id")).toBe(period().entity.id);
        expect(query.get("book")).toBe("ASC606");
        expect(query.get("topic")).toBe("ESTIMATE_VS_ERROR");
        expect(query.get("status")).toBe("REVIEWED");
        return HttpResponse.json({
          items: [
            {
              id: reviewedJudgementId,
              judgement_no: "JDG-000042",
              conclusion: "Correct omitted September costs.",
              rationale: "Reviewed source cost file.",
              contract_id: null,
              reviewer: { display_name: "Marcus" },
            },
          ],
          next_cursor: null,
        });
      }),
      http.get(apiUrl("/api/v1/approvals"), () =>
        HttpResponse.json({ items: pending === null ? [] : [pending], next_cursor: null }),
      ),
      http.get(apiUrl(`/api/v1/approvals/${REOPEN_REQUEST_ID}`), () =>
        HttpResponse.json(approval("PERIOD_REOPEN", PRIYA_ACTOR)),
      ),
      http.post(apiUrl(`/api/v1/periods/${STATE_ID}/request-reopen`), async ({ request }) => {
        sent.push({ ifMatch: request.headers.get("If-Match"), body: await request.json() });
        pending = approval("PERIOD_REOPEN", PRIYA_ACTOR);
        return HttpResponse.json({ approval_request_id: REOPEN_REQUEST_ID });
      }),
      http.post(apiUrl(`/api/v1/approvals/${REOPEN_REQUEST_ID}/withdraw`), async ({ request }) => {
        withdrawn.push(await request.json());
        pending = null;
        return HttpResponse.json({
          ...approval("PERIOD_REOPEN", PRIYA_ACTOR),
          status: "WITHDRAWN",
        });
      }),
    );
    renderApp(COCKPIT_PATH, { me: PRIYA, screenRoutes: SCREEN_ROUTES });

    fireEvent.click(await screen.findByRole("button", { name: "Request reopen" }));
    const drawer = await screen.findByRole("dialog", { name: "Request reopen of Sep 2026" });
    // REQ-CLS-011 rev 1.99 (supervisor ruling R-117 (c)): the flag covers every line posted from the
    // reopen until the period is locked again, the soft close that follows the reopen included.
    expect(drawer.textContent).toContain(
      "Lines posted until it is locked again are flagged post-reopen, and re-lock produces a diff report.",
    );
    // SCR-PERM-02: the attachments field is for a holder of an attachment permission and the judgement
    // fields for a holder of `judgement.create`; a Revenue Reviewer holds neither (PRD §5.6).
    expect(within(drawer).queryByLabelText(/^Attachments/)).toBeNull();
    expect(
      within(drawer).queryByRole("checkbox", {
        name: "Record an estimate-versus-error judgement",
      }),
    ).toBeNull();
    // Not a dead end (supervisor ruling R-100 (a)): who records the judgement, and where it is listed.
    expect(
      within(drawer).getByText(
        "A Revenue Accountant records the estimate-versus-error judgement. Name it in the comment.",
      ),
    ).toBeTruthy();
    expect(
      within(drawer).getByRole("link", { name: "Judgement register" }).getAttribute("href"),
    ).toBe("/reports/judgement_register?entity=AVM-US&period=FY2026-P09&book=ASC606");
    // A reason and a comment of at least 10 characters are required.
    fireEvent.click(within(drawer).getByRole("button", { name: "Submit reopen request" }));
    expect(await within(drawer).findByText("Choose a reason.")).toBeTruthy();
    expect(sent).toHaveLength(0);
    fireEvent.click(within(drawer).getByRole("combobox", { name: /^Reason/ }));
    fireEvent.mouseDown(await screen.findByRole("option", { name: "Error correction" }));
    fireEvent.change(within(drawer).getByRole("textbox", { name: /^Comment \(required\)/ }), {
      target: { value: REOPEN_COMMENT },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Submit reopen request" }));
    expect(sent).toHaveLength(0);
    fireEvent.click(await within(drawer).findByRole("combobox", { name: /^Reviewed judgement/ }));
    fireEvent.mouseDown(await screen.findByRole("option", { name: "JDG-000042" }));
    expect(within(drawer).getByText("Reviewed by Marcus")).toBeTruthy();
    expect(
      within(drawer).queryByRole("checkbox", { name: "Record an estimate-versus-error judgement" }),
    ).toBeNull();
    fireEvent.click(within(drawer).getByRole("button", { name: "Submit reopen request" }));

    expect(
      await screen.findByText("Reopen requested for AVM-US Sep 2026. Two approvers must approve."),
    ).toBeTruthy();
    expect(sent).toEqual([
      {
        ifMatch: '"r5"',
        body: {
          reason_code: "ERROR_CORRECTION",
          comment: REOPEN_COMMENT,
          judgement_record_id: reviewedJudgementId,
        },
      },
    ]);

    // The pending request: the dual-approval status, the requester's line and "Withdraw request";
    // a second request is not offered.
    const banner = await screen.findByTestId("SF-05-banner-reopen-request");
    expect(banner.textContent).toContain(
      "Reopen requested by Priya Raman on 02 Oct 2026. Dual approval · 0 of 2 recorded.",
    );
    expect(banner.textContent).toContain(
      "You submitted this request. Two other approvers must review it.",
    );
    expect(
      within(banner).getByRole("link", { name: "Review in Approvals" }).getAttribute("href"),
    ).toBe(`/approvals/requests/${REOPEN_REQUEST_ID}`);
    expect(screen.queryByRole("button", { name: "Request reopen" })).toBeNull();

    fireEvent.click(within(banner).getByRole("button", { name: "Withdraw request" }));
    const confirm = await screen.findByRole("alertdialog", {
      name: "Withdraw the reopen request?",
    });
    fireEvent.click(within(confirm).getByRole("button", { name: "Withdraw request" }));
    expect(await screen.findByText("Reopen request withdrawn.")).toBeTruthy();
    expect(withdrawn).toEqual([{ comment: null }]);
    await waitFor(() => {
      expect(screen.queryByTestId("SF-05-banner-reopen-request")).toBeNull();
    });
    expect(await screen.findByRole("button", { name: "Request reopen" })).toBeTruthy();
  });

  it("late-source reopen attaches files and optionally submits a new judgement for review", async () => {
    // A role that requests a reopen, prepares reconciliations (an attachment permission, 04 API-R-12)
    // and records judgements (PRD ACT-12).
    const requester = signedInMe({
      user: PRIYA.user,
      permissions: [
        "contract.read",
        "config.read",
        "period.reopen_request",
        "recon.prepare",
        "judgement.create",
      ],
    });
    const CONTRACT_ID = "2b3c4d5e-6f70-4a81-9b92-000000000301";
    const FILE_ID = "f1f1f1f1-f1f1-4f1f-8f1f-000000000401";
    const JUDGEMENT_ID = "3c4d5e6f-7081-4b92-8ca3-000000000501";
    const calls: string[] = [];
    const requests: unknown[] = [];
    const attached: unknown[] = [];
    const judged: unknown[] = [];
    const uploads: string[] = [];
    serve(period({ state: "closed", row_version: 5 }), checklist([]));
    server.use(
      http.get(apiUrl("/api/v1/approvals"), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get(apiUrl("/api/v1/contracts"), () =>
        HttpResponse.json({
          items: [
            {
              id: CONTRACT_ID,
              external_id: "PRJ-CB-2026-01",
              customer: { id: "c0", code: "CASTELLAN", name: "Castellan Builders" },
            },
          ],
          next_cursor: null,
        }),
      ),
      http.post(apiUrl(`/api/v1/periods/${STATE_ID}/request-reopen`), async ({ request }) => {
        calls.push("request-reopen");
        requests.push(await request.json());
        return HttpResponse.json({ approval_request_id: REOPEN_REQUEST_ID });
      }),
      http.post(apiUrl("/api/v1/files"), async ({ request }) => {
        calls.push("files");
        // The multipart body as text: the DOM `File` of this environment is not the parser's.
        uploads.push(await request.text());
        return HttpResponse.json({ id: FILE_ID }, { status: 201 });
      }),
      http.post(apiUrl("/api/v1/attachments"), async ({ request }) => {
        calls.push("attachments");
        attached.push(await request.json());
        return HttpResponse.json({ id: "a1" }, { status: 201 });
      }),
      http.post(apiUrl("/api/v1/judgements"), async ({ request }) => {
        calls.push("judgements");
        judged.push(await request.json());
        return HttpResponse.json({ id: JUDGEMENT_ID }, { status: 201 });
      }),
      http.post(apiUrl(`/api/v1/judgements/${JUDGEMENT_ID}/submit`), () => {
        calls.push("judgement-submit");
        return HttpResponse.json({ id: JUDGEMENT_ID });
      }),
    );
    renderApp(COCKPIT_PATH, { me: requester, screenRoutes: SCREEN_ROUTES });

    fireEvent.click(await screen.findByRole("button", { name: "Request reopen" }));
    const drawer = await screen.findByRole("dialog", { name: "Request reopen of Sep 2026" });
    fireEvent.click(within(drawer).getByRole("combobox", { name: /^Reason/ }));
    fireEvent.mouseDown(await screen.findByRole("option", { name: "Late source data" }));
    fireEvent.change(within(drawer).getByRole("textbox", { name: /^Comment \(required\)/ }), {
      target: { value: REOPEN_COMMENT },
    });
    // J-14.1: the job-cost report as an attachment of the request.
    const report = new File(["cost code,amount\n4100,20500.00\n"], "job-cost-report-sep-2026.csv", {
      type: "text/csv",
    });
    fireEvent.change(within(drawer).getByLabelText(/^Attachments/), {
      target: { files: [report] },
    });
    expect(within(drawer).getByText("job-cost-report-sep-2026.csv")).toBeTruthy();
    // A holder of `judgement.create` records the judgement here and is not sent elsewhere.
    expect(within(drawer).queryByRole("link", { name: "Judgement register" })).toBeNull();
    fireEvent.click(
      within(drawer).getByRole("checkbox", { name: "Record an estimate-versus-error judgement" }),
    );
    // DS-CMP-21: typing opens the list of the entity's contracts.
    fireEvent.change(await within(drawer).findByRole("combobox", { name: /^Contract/ }), {
      target: { value: "PRJ" },
    });
    fireEvent.mouseDown(
      await screen.findByRole("option", { name: "PRJ-CB-2026-01 · Castellan Builders" }),
    );
    fireEvent.change(within(drawer).getByRole("textbox", { name: /^Conclusion/ }), {
      target: { value: "Estimate: late September cost data needs review." },
    });
    fireEvent.change(within(drawer).getByRole("textbox", { name: /^Rationale/ }), {
      target: {
        value: "The source arrived after close; the accounting conclusion requires review.",
      },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Submit reopen request" }));

    expect(
      await screen.findByText("Reopen requested for AVM-US Sep 2026. Two approvers must approve."),
    ).toBeTruthy();
    // The request first; then the file, attached to the request; then the judgement and its submit.
    expect(requests).toEqual([
      { reason_code: "LATE_SOURCE_DATA", comment: REOPEN_COMMENT, judgement_record_id: null },
    ]);
    expect(calls).toEqual([
      "request-reopen",
      "files",
      "attachments",
      "judgements",
      "judgement-submit",
    ]);
    // One upload of purpose ATTACHMENT with the file part (this environment's multipart writer keeps
    // the media type and neither the DOM file's name nor its bytes, so those are not asserted).
    expect(uploads).toHaveLength(1);
    expect(uploads[0]).toMatch(/name="purpose"\r\n\r\nATTACHMENT\r\n/);
    expect(uploads[0]).toMatch(/name="file"; filename="[^"]+"\r\nContent-Type: text\/csv\r\n/);
    expect(attached).toEqual([
      {
        file_object_id: FILE_ID,
        subject_type: "approval_request",
        subject_id: REOPEN_REQUEST_ID,
        description: null,
      },
    ]);
    expect(judged).toEqual([
      {
        topic: "ESTIMATE_VS_ERROR",
        subject_type: "contract",
        subject_id: CONTRACT_ID,
        conclusion: "Estimate: late September cost data needs review.",
        rationale: "The source arrived after close; the accounting conclusion requires review.",
      },
    ]);
  });

  it("a locked period offers the estimate-versus-error judgement to a holder of judgement.create", async () => {
    // PRD J-14.1 (rev 1.59; supervisor ruling R-100 (a)): the judgement is the Revenue Accountant's,
    // who requests no reopen; she records it on its own (item CLO-JDG-ESTERR-UI-1).
    const accountant = signedInMe({
      permissions: ["contract.read", "config.read", "period.close", "judgement.create"],
    });
    const CONTRACT_ID = "2b3c4d5e-6f70-4a81-9b92-000000000301";
    const JUDGEMENT_ID = "3c4d5e6f-7081-4b92-8ca3-000000000541";
    const calls: string[] = [];
    const judged: unknown[] = [];
    let refused = true;
    serve(period({ state: "closed", row_version: 5 }), checklist([]));
    server.use(
      http.get(apiUrl("/api/v1/contracts"), () =>
        HttpResponse.json({
          items: [
            {
              id: CONTRACT_ID,
              external_id: "PRJ-CB-2026-01",
              customer: { id: "c0", code: "CASTELLAN", name: "Castellan Builders" },
            },
          ],
          next_cursor: null,
        }),
      ),
      http.post(apiUrl("/api/v1/judgements"), async ({ request }) => {
        calls.push("judgements");
        judged.push(await request.json());
        return HttpResponse.json({ id: JUDGEMENT_ID, judgement_no: "JDG-000041" }, { status: 201 });
      }),
      http.post(apiUrl(`/api/v1/judgements/${JUDGEMENT_ID}/submit`), () => {
        calls.push("judgement-submit");
        if (refused) {
          refused = false;
          return problemResponse("validation-failed", 422, "Check the fields", {
            detail: "A judgement record needs a reviewer other than its preparer.",
          });
        }
        return HttpResponse.json({ id: JUDGEMENT_ID, judgement_no: "JDG-000041" });
      }),
    );
    renderApp(COCKPIT_PATH, { me: accountant, screenRoutes: SCREEN_ROUTES });

    fireEvent.click(
      await screen.findByRole("button", { name: "Record estimate-versus-error judgement" }),
    );
    const drawer = await screen.findByRole("dialog", {
      name: "Estimate-versus-error judgement for Sep 2026",
    });
    expect(drawer.textContent).toContain(
      "The record goes to a Revenue Reviewer for review. A reopen request names it in its comment.",
    );
    // The three fields are required: nothing is sent without them.
    fireEvent.click(within(drawer).getByRole("button", { name: "Record judgement" }));
    expect(await within(drawer).findByText("Choose a contract.")).toBeTruthy();
    expect(within(drawer).getByText("Enter a conclusion.")).toBeTruthy();
    expect(within(drawer).getByText("Enter a rationale.")).toBeTruthy();
    expect(calls).toEqual([]);

    fireEvent.change(await within(drawer).findByRole("combobox", { name: /^Contract/ }), {
      target: { value: "PRJ" },
    });
    fireEvent.mouseDown(
      await screen.findByRole("option", { name: "PRJ-CB-2026-01 · Castellan Builders" }),
    );
    fireEvent.change(within(drawer).getByRole("textbox", { name: /^Conclusion/ }), {
      target: { value: "Error: costs incurred in September were omitted from the cost file." },
    });
    fireEvent.change(within(drawer).getByRole("textbox", { name: /^Rationale/ }), {
      target: { value: "The costs were known at the close and are not a change in estimate." },
    });
    // The record is created; its submission is refused, by name, and the drawer stays.
    fireEvent.click(within(drawer).getByRole("button", { name: "Record judgement" }));
    expect(
      await within(drawer).findByText(
        "A judgement record needs a reviewer other than its preparer.",
      ),
    ).toBeTruthy();
    expect(calls).toEqual(["judgements", "judgement-submit"]);
    // The next press submits the record that exists; it is not created a second time.
    fireEvent.click(within(drawer).getByRole("button", { name: "Record judgement" }));
    expect(await screen.findByText("Judgement JDG-000041 was submitted for review.")).toBeTruthy();
    expect(calls).toEqual(["judgements", "judgement-submit", "judgement-submit"]);
    // 04 T-CON-19: the subject of the record is the contract.
    expect(judged).toEqual([
      {
        topic: "ESTIMATE_VS_ERROR",
        subject_type: "contract",
        subject_id: CONTRACT_ID,
        conclusion: "Error: costs incurred in September were omitted from the cost file.",
        rationale: "The costs were known at the close and are not a change in estimate.",
      },
    ]);
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    cleanup();

    // Not offered while the period is not locked, nor to a reader without `judgement.create`.
    serve(period({ state: "open" }), checklist([]));
    renderApp(COCKPIT_PATH, { me: accountant, screenRoutes: SCREEN_ROUTES });
    await screen.findByRole("button", { name: "Start soft close" });
    expect(
      screen.queryByRole("button", { name: "Record estimate-versus-error judgement" }),
    ).toBeNull();
    cleanup();
    serve(period({ state: "closed", row_version: 5 }), checklist([]));
    renderApp(COCKPIT_PATH, { me: CONTROLLER_REOPEN, screenRoutes: SCREEN_ROUTES });
    await screen.findByRole("button", { name: "Request reopen" });
    expect(
      screen.queryByRole("button", { name: "Record estimate-versus-error judgement" }),
    ).toBeNull();
  });

  it("a pending reopen request lists its decisions for an approver; a later closed period blocks the request", async () => {
    // J-14.2: `marcus` has approved; `elena`, another Controller, reads the cockpit.
    const decided: PeriodApproval = {
      ...approval("PERIOD_REOPEN", PRIYA_ACTOR),
      steps: [
        {
          step_no: 1,
          name: "Dual approval",
          required_permission: "period.reopen_approve",
          min_approvers: 2,
          status: "ACTIVE",
          decisions: [
            {
              id: "5e6f7a8b-9c0d-4e1f-8a2b-000000000001",
              decision: "APPROVE",
              approver: {
                id: "6d2e9b8f-3c5a-4d7e-8f9b-8a7c6d5e4f3b",
                display_name: "Marcus Webb",
                kind: "USER",
              },
              on_behalf_of: { id: null, display_name: "Elena Sokolova", kind: "USER" },
              decided_at: "2026-10-02T10:00:00Z",
              comment: "Costs omitted from the September file.",
              reason_code: null,
              auto_rule_key: null,
            },
          ],
        },
      ],
    };
    serve(period({ state: "closed", row_version: 5 }), checklist([]));
    server.use(
      http.get(apiUrl("/api/v1/approvals"), () =>
        HttpResponse.json({ items: [decided], next_cursor: null }),
      ),
    );
    renderApp(COCKPIT_PATH, { me: CONTROLLER_REOPEN, screenRoutes: SCREEN_ROUTES });

    const banner = await screen.findByTestId("SF-05-banner-reopen-request");
    expect(banner.textContent).toContain("Dual approval · 1 of 2 recorded.");
    expect(banner.textContent).toContain("Marcus Webb");
    expect(banner.textContent).toContain("on behalf of Elena Sokolova");
    expect(banner.textContent).toContain("02 Oct 2026 10:00 UTC");
    // Not the requester: no withdrawal and no requester line (the decision is made in Approvals).
    expect(within(banner).queryByRole("button", { name: "Withdraw request" })).toBeNull();
    expect(banner.textContent).not.toContain("You submitted this request.");
    cleanup();

    // BR-CLS-05 (ERR-16): a later closed period leaves the control aria-disabled with its reason.
    const october = period({
      id: "7c1d2e3f-4a5b-4c6d-8e7f-000000000910",
      state: "closed",
      row_version: 2,
      is_first_open: false,
      period: {
        id: "1c2d3e4f-5a6b-4c7d-8e9f-000000000010",
        period_key: "FY2026-P10",
        name: "Oct 2026",
        fiscal_year: 2026,
        period_no: 10,
        quarter_no: 4,
        start_date: "2026-10-01",
        end_date: "2026-10-31",
      },
    });
    const september = period({ state: "closed", row_version: 5 });
    serve(september, checklist([]));
    server.use(
      http.get(apiUrl("/api/v1/periods"), () =>
        HttpResponse.json({ items: [september, october], next_cursor: null }),
      ),
    );
    renderApp(COCKPIT_PATH, { me: CONTROLLER_REOPEN, screenRoutes: SCREEN_ROUTES });
    const reopen = await screen.findByRole("button", { name: "Request reopen" });
    expect(reopen.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(reopen);
    expect(screen.queryByRole("dialog", { name: "Request reopen of Sep 2026" })).toBeNull();
  });

  it("a pending reopen request names its reason; without one the sentence stands without it", async () => {
    // SCREENS_B §1.1 rev 1.93: API-S-Approval states the reason code a request was submitted with
    // (04 §16.10 rev 1.252; item APR-REQUEST-REASON-1), so the banner reads as it was first specified,
    // with the label the reopen drawer offers. A reader the API withholds the code from (null) and a
    // code this build has no label for read the sentence of rev 1.32, never the code itself.
    const NO_REASON =
      "Reopen requested by Priya Raman on 02 Oct 2026. Dual approval · 0 of 2 recorded.";
    const cases: readonly (readonly [string | null, string])[] = [
      [
        "ERROR_CORRECTION",
        "Reopen requested by Priya Raman on 02 Oct 2026: Error correction. Dual approval · 0 of 2 recorded.",
      ],
      [
        "LATE_SOURCE_DATA",
        "Reopen requested by Priya Raman on 02 Oct 2026: Late source data. Dual approval · 0 of 2 recorded.",
      ],
      [
        "AUDIT_ADJUSTMENT",
        "Reopen requested by Priya Raman on 02 Oct 2026: Audit adjustment. Dual approval · 0 of 2 recorded.",
      ],
      [
        "OTHER",
        "Reopen requested by Priya Raman on 02 Oct 2026: Other. Dual approval · 0 of 2 recorded.",
      ],
      [null, NO_REASON],
      ["RESTATEMENT", NO_REASON],
    ];
    for (const [code, sentence] of cases) {
      serve(period({ state: "closed", row_version: 5 }), checklist([]));
      server.use(
        http.get(apiUrl("/api/v1/approvals"), () =>
          HttpResponse.json({
            items: [{ ...approval("PERIOD_REOPEN", PRIYA_ACTOR), reason_code: code }],
            next_cursor: null,
          }),
        ),
      );
      renderApp(COCKPIT_PATH, { me: CONTROLLER_REOPEN, screenRoutes: SCREEN_ROUTES });
      const banner = await screen.findByTestId("SF-05-banner-reopen-request");
      expect(within(banner).getByRole("heading").textContent).toBe(sentence);
      cleanup();
    }
  });

  it("permanently lock is a Controller's request, disabled with its reason behind an earlier period", async () => {
    const sent: { readonly ifMatch: string | null; readonly body: unknown }[] = [];
    let pending = false;
    const august = period({
      id: "7c1d2e3f-4a5b-4c6d-8e7f-000000000908",
      state: "permanently_locked",
      row_version: 7,
      is_first_open: false,
      period: {
        id: "1c2d3e4f-5a6b-4c7d-8e9f-000000000008",
        period_key: "FY2026-P08",
        name: "Aug 2026",
        fiscal_year: 2026,
        period_no: 8,
        quarter_no: 3,
        start_date: "2026-08-01",
        end_date: "2026-08-31",
      },
    });
    const september = period({ state: "closed", row_version: 5 });
    serve(september, checklist([]));
    server.use(
      http.get(apiUrl("/api/v1/periods"), () =>
        HttpResponse.json({ items: [august, september], next_cursor: null }),
      ),
      http.get(apiUrl("/api/v1/approvals"), () =>
        HttpResponse.json({
          items: pending ? [approval("PERIOD_LOCK", MARCUS_ACTOR)] : [],
          next_cursor: null,
        }),
      ),
      http.post(
        apiUrl(`/api/v1/periods/${STATE_ID}/request-permanent-lock`),
        async ({ request }) => {
          sent.push({ ifMatch: request.headers.get("If-Match"), body: await request.json() });
          pending = true;
          return HttpResponse.json({ approval_request_id: LOCK_REQUEST_ID });
        },
      ),
    );
    renderApp(COCKPIT_PATH, { me: MARCUS, screenRoutes: SCREEN_ROUTES });

    // Every earlier period is permanently locked: the item is enabled for a holder of `period.lock`.
    fireEvent.click(await screen.findByRole("button", { name: "More close actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Permanently lock" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Permanently lock Sep 2026 for AVM-US?",
    });
    expect(dialog.textContent).toContain("A permanently locked period can never be reopened.");
    // SB-R-05: a comment of at least 10 characters, and the Danger command.
    fireEvent.click(within(dialog).getByRole("button", { name: "Request permanent lock" }));
    expect(await within(dialog).findByText("Enter at least 10 characters.")).toBeTruthy();
    expect(sent).toHaveLength(0);
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Comment \(required\)/ }), {
      target: { value: PERMANENT_COMMENT },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Request permanent lock" }));

    // The pending request: its banner with "View request"; the item is not rendered meanwhile.
    const banner = await screen.findByTestId("SF-05-banner-permanent-lock-request");
    expect(banner.textContent).toContain(
      "Permanent lock requested by Marcus Webb on 01 Oct 2026 08:30 UTC.",
    );
    expect(within(banner).getByRole("link", { name: "View request" }).getAttribute("href")).toBe(
      `/approvals/requests/${LOCK_REQUEST_ID}`,
    );
    expect(sent).toEqual([{ ifMatch: '"r5"', body: { comment: PERMANENT_COMMENT } }]);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "More close actions" })).toBeNull();
    });
    cleanup();

    // SM-07: an earlier period that is not permanently locked leaves the item disabled with the
    // reason of SCREENS_B §1.1; it opens no dialog.
    const lockedAugust = { ...august, state: "closed" as const };
    serve(september, checklist([]));
    server.use(
      http.get(apiUrl("/api/v1/periods"), () =>
        HttpResponse.json({ items: [lockedAugust, september], next_cursor: null }),
      ),
    );
    renderApp(COCKPIT_PATH, { me: MARCUS, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(await screen.findByRole("button", { name: "More close actions" }));
    const item = screen.getByRole("menuitem", { name: "Permanently lock" });
    expect(item.getAttribute("aria-disabled")).toBe("true");
    expect(document.getElementById(item.getAttribute("aria-describedby") ?? "")?.textContent).toBe(
      "Permanently lock Aug 2026 first.",
    );
    fireEvent.click(item);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("/close starts from the workspace's own stored context: a sandbox copy of one membership id does not start from its source's", async () => {
    // A sandbox copy keeps the ids of the rows it copies (SCREENS_B §9.7 "The open workspace").
    const source = MAYA.memberships[0];
    if (source === undefined) {
      throw new Error("no membership");
    }
    const COPY_ID = "1c1c1c1c-1c1c-4c1c-8c1c-1c1c1c1c1c1c";
    const me = {
      ...MAYA,
      memberships: [
        source,
        {
          ...source,
          tenant: {
            ...source.tenant,
            id: COPY_ID,
            code: "sbx-avenmoor-rehearsal",
            display_name: "Avenmoor rehearsal",
            kind: "sandbox" as const,
            source_tenant_id: source.tenant.id,
            source_known_at: "2026-09-12T18:10:00Z",
          },
        },
      ],
    };
    const inCopy = signedInSession({
      active_tenant: {
        id: COPY_ID,
        code: "sbx-avenmoor-rehearsal",
        display_name: "Avenmoor rehearsal",
        kind: "sandbox",
      },
    });
    const entity = (code: string, books: readonly string[]) => ({
      id: `id-${code}`,
      code,
      name: code,
      is_active: true,
      books: books.map((book_code) => ({ book_code, is_enabled: true })),
    });
    const month = (code: string, two: string, state: string, isFirstOpen: boolean) => ({
      id: `${code}-${two}`,
      entity: { id: `id-${code}`, code, name: code },
      state,
      is_first_open: isFirstOpen,
      period: {
        period_key: `FY2026-P${two}`,
        fiscal_year: 2026,
        start_date: `2026-${two}-01`,
        end_date: `2026-${two}-28`,
      },
    });
    server.use(
      http.get(apiUrl("/api/v1/entities"), () =>
        HttpResponse.json({
          items: [entity("AVM-DE", ["ASC606"]), entity("AVM-UK", ["ASC606", "IFRS15"])],
          next_cursor: null,
        }),
      ),
      http.get(apiUrl("/api/v1/books"), () =>
        HttpResponse.json({
          items: [
            { code: "IFRS15", is_primary: false, is_enabled: true },
            { code: "ASC606", is_primary: true, is_enabled: true },
          ],
          next_cursor: null,
        }),
      ),
      http.get(apiUrl("/api/v1/periods"), ({ request }) => {
        const code = new URL(request.url).searchParams.get("entity") ?? "";
        return HttpResponse.json({
          items: [month(code, "01", "open", true), month(code, "02", "open", false)],
          next_cursor: null,
        });
      }),
    );
    // What the member last chose in the SOURCE workspace; the copy holds no choice.
    window.localStorage.setItem(
      contextStorageKey({ userId: MAYA.user.id, tenantId: source.tenant.id }),
      JSON.stringify({ entity: "AVM-UK", period: "FY2026-P02", book: "IFRS15" }),
    );

    const inSource = renderWithApp(<CloseRedirect />, { entry: "/close", me });
    await waitFor(() => {
      expect(inSource.router.state.location.pathname).toBe("/close/AVM-UK/IFRS15/FY2026-P02");
    });
    cleanup();

    const { router } = renderWithApp(<CloseRedirect />, { entry: "/close", me, session: inCopy });
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/close/AVM-DE/ASC606/FY2026-P01");
    });
    window.localStorage.clear();
  });

  it("a period of the legacy book names the book it follows and offers no close command", async () => {
    // SCREENS_B §1.1 rev 1.42 (04 §16.8 rev 1.155, API-S-Period `follows`; PRD ERR-76; supervisor
    // rulings R-112 (e), R-113 (h) and R-114 (d)): the LEGACY book has no close of its own. Its
    // period shows one line — the book whose close it follows, that book's state for the period and
    // the way there — in place of the close status, the blockers and the checklist, and of the
    // commands only the two the API keeps for such a row: `open` and `cancel-close`.
    const LEGACY_PATH = "/close/AVM-US/LEGACY/FY2026-P09";
    const legacy = (overrides: Partial<Period> = {}) =>
      period({ book: "LEGACY", follows: { book_code: "ASC606", state: "closing" }, ...overrides });
    const approvalReads: ApprovalReads = [];
    const exceptionReads: string[] = [];
    serve(legacy(), checklist(["EXCEPTIONS_CLEARED"]), NO_COUNTS, approvalReads);
    server.use(
      http.get(apiUrl("/api/v1/exceptions"), ({ request }) => {
        exceptionReads.push(new URL(request.url).searchParams.toString());
        return HttpResponse.json(
          { items: [], next_cursor: null },
          { headers: { "X-Erev-Total-Count": "0" } },
        );
      }),
    );
    renderApp(LEGACY_PATH, { me: CONTROLLER_REOPEN, screenRoutes: SCREEN_ROUTES });

    await screen.findByRole("heading", { level: 1, name: "Close · AVM-US · Sep 2026 · Legacy" });
    const line = await screen.findByTestId("SF-05-follows");
    expect(line.textContent).toContain("The legacy book follows the close of ASC 606.");
    // The followed book's state for the period comes with the row: no second request.
    expect(line.textContent).toContain("Sep 2026 in ASC 606:");
    expect(within(line).getByText("Soft close")).toBeTruthy();
    expect(
      within(line).getByRole("link", { name: "Go to Sep 2026 in ASC 606" }).getAttribute("href"),
    ).toBe("/close/AVM-US/ASC606/FY2026-P09?entity=AVM-US&period=FY2026-P09&book=ASC606");
    // The header keeps the row's own state, and names no close run or lock of the book.
    expect(screen.getByText("Period open")).toBeTruthy();
    expect(screen.queryByText("Current lock")).toBeNull();
    expect(screen.queryByText("Close run")).toBeNull();
    // No close status, blockers or checklist, and none of the commands of an open period.
    expect(screen.queryByTestId("SF-05-kpi-strip")).toBeNull();
    expect(screen.queryByTestId("SF-05-grid-blockers")).toBeNull();
    expect(screen.queryByRole("grid")).toBeNull();
    for (const name of ["Start soft close", "Run close", "Lock period", "Submit for lock"]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
    expect(screen.queryByRole("button", { name: "More close actions" })).toBeNull();
    // The tabs of a book without a close run, a journal run or reconciliations of its own.
    const tabs = screen.getByRole("navigation", { name: "Close of Sep 2026" });
    expect(
      within(tabs)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["Checklist", "History"]);
    // Neither the requests of the period nor its blocker counts are read.
    expect(
      approvalReads.filter((params) =>
        params.getAll("subject_type").some((type) => type.startsWith("PERIOD_")),
      ),
    ).toHaveLength(0);
    expect(exceptionReads).toEqual([]);
    cleanup();

    // A row an earlier release left in soft close: "End soft close" alone returns it to open.
    serve(legacy({ state: "closing", row_version: 4 }), checklist([]));
    renderApp(LEGACY_PATH, { me: CONTROLLER_REOPEN, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(await screen.findByRole("button", { name: "More close actions" }));
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      "End soft close",
    ]);
    for (const name of ["Run close", "Submit for lock", "Lock period"]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
    expect(screen.getByTestId("SF-05-follows")).toBeTruthy();
    cleanup();

    // The states no command of this release gives such a row: nothing of a reopen, a judgement, a
    // permanent lock or a close run.
    for (const state of ["closed", "reopened"] as const) {
      serve(legacy({ state, row_version: 5 }), checklist([]));
      renderApp(LEGACY_PATH, {
        me: signedInMe({
          permissions: [
            "contract.read",
            "period.close",
            "period.lock",
            "period.reopen_request",
            "judgement.create",
          ],
        }),
        screenRoutes: SCREEN_ROUTES,
      });
      await screen.findByTestId("SF-05-follows");
      for (const name of [
        "Request reopen",
        "Record estimate-versus-error judgement",
        "Run close",
        "Start soft close",
      ]) {
        expect(screen.queryByRole("button", { name })).toBeNull();
      }
      expect(screen.queryByRole("button", { name: "More close actions" })).toBeNull();
      cleanup();
    }

    // A future period is opened like any other; where the entity keeps no period of the followed
    // book the line says so and leads nowhere.
    serve(
      legacy({
        state: "future",
        is_first_open: false,
        follows: { book_code: "ASC606", state: null },
      }),
      checklist([]),
    );
    renderApp(LEGACY_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    expect(await screen.findByRole("button", { name: "Open period" })).toBeTruthy();
    const alone = screen.getByTestId("SF-05-follows");
    expect(alone.textContent).toBe(
      "The legacy book follows the close of ASC 606.ASC 606 has no period Sep 2026 for AVM-US.",
    );
    expect(within(alone).queryByRole("link")).toBeNull();
    cleanup();

    // The addresses of the tabs that are not offered show the same line, and none of their commands.
    for (const segment of ["close-run", "journal-preview", "reconciliations"]) {
      serve(legacy(), checklist([]));
      renderApp(`${LEGACY_PATH}/${segment}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
      expect((await screen.findByTestId("SF-05-follows")).textContent).toContain(
        "The legacy book follows the close of ASC 606.",
      );
      expect(screen.queryByRole("button", { name: "Run close" })).toBeNull();
      expect(screen.queryByRole("link", { name: "Run journals" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Generate reconciliation" })).toBeNull();
      cleanup();
    }
  });

  it("journal preview balanced from api strings", async () => {
    serve(period(), checklist([]));
    renderApp(`${COCKPIT_PATH}/journal-preview`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const region = await screen.findByRole("region", { name: /^Journal preview \(USD\)/ });
    expect(region.textContent).toContain("295.69");
    expect(within(region).getByText("Pass")).toBeTruthy();
    expect(within(region).getByText("Balanced")).toBeTruthy();
    const table = screen.getByRole("table", { name: "Journal preview by account role, USD" });
    expect(within(table).getAllByRole("row")).toHaveLength(4);
    expect(table.textContent).toContain("Contract liability");
    // No run yet: the run link is replaced by the not calculated text (§1.3 states).
    expect(region.textContent).toContain("Journal run not calculated");
  });
});

// docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): the commands of the cockpit show no
// message at a field, so the banner of each says every sentence of a refusal — one that names a member
// was shown nowhere — and after a 412 it says that the record changed, in place of the problem (SCREENS
// SCR-ST-09), where the dialogs showed both.
describe("SF-05 close cockpit, a refused command", () => {
  const SENTENCE = "A close run of this period has not ended.";
  const WHOLE = REFUSAL_TITLE + SENTENCE + REFUSAL_REFERENCE;

  function refuse(command: string, status = 422) {
    server.use(
      http.post(apiUrl(`/api/v1/periods/${STATE_ID}/${command}`), () =>
        refusedWith({ status: SENTENCE }, { status }),
      ),
    );
  }

  async function bannerOf(dialog: HTMLElement): Promise<string | null> {
    return (await within(dialog).findByRole("alert")).textContent;
  }

  it("Start soft close says every sentence, and after a 412 that the record changed", async () => {
    serve(period({ state: "open" }), checklist([]));
    let status = 422;
    server.use(
      http.post(apiUrl(`/api/v1/periods/${STATE_ID}/start-close`), () =>
        refusedWith({ status: SENTENCE }, { status }),
      ),
    );
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(await screen.findByRole("button", { name: "Start soft close" }));
    const dialog = await screen.findByRole("dialog", { name: "Start soft close for Sep 2026?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Start soft close" }));
    expect(await bannerOf(dialog)).toBe(WHOLE);

    status = 412;
    fireEvent.click(within(dialog).getByRole("button", { name: "Start soft close" }));
    expect(await within(dialog).findByRole("heading", { name: RECORD_CHANGED })).toBeTruthy();
    expect(within(dialog).queryByRole("heading", { name: REFUSAL_TITLE })).toBeNull();
  });

  it("End soft close says every sentence", async () => {
    serve(period({ state: "closing", row_version: 4 }), checklist([]));
    refuse("cancel-close");
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(await screen.findByRole("button", { name: "More close actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "End soft close" }));
    const dialog = await screen.findByRole("alertdialog", { name: "End soft close for Sep 2026?" });
    const reason = within(dialog).getByRole("combobox", { name: /^Reason/ });
    fireEvent.click(reason);
    fireEvent.mouseDown(
      within(
        document.getElementById(reason.getAttribute("aria-controls") ?? "") as HTMLElement,
      ).getByRole("option", { name: "Close restarted" }),
    );
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Comment \(required\)/ }), {
      target: { value: "The usage import of September is run again." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "End soft close" }));
    expect(await bannerOf(dialog)).toBe(WHOLE);
  });

  it("Submit for lock says every sentence of a refusal that names no gate", async () => {
    serve(period({ state: "closing", row_version: 4 }), checklist([]));
    refuse("request-lock");
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(await screen.findByRole("button", { name: "Submit for lock" }));
    const dialog = await screen.findByRole("dialog", { name: "Submit Sep 2026 for lock" });
    fireEvent.change(
      within(dialog).getByRole("textbox", { name: /^Certification comment \(required\)/ }),
      { target: { value: "September is reconciled and reviewed." } },
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Submit for lock" }));
    expect(await bannerOf(dialog)).toBe(WHOLE);
  });

  it("Request waiver says every sentence", async () => {
    const gates = checklist(["EXCEPTIONS_CLEARED"]);
    const gate = gates.find((item) => item.code === "EXCEPTIONS_CLEARED");
    serve(period(), gates);
    refuse(`checklist/${gate?.id ?? ""}/waive`);
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    const row = await screen.findByTestId("SF-05-row-exceptions-cleared");
    fireEvent.click(within(row).getByRole("button", { name: "Request waiver" }));
    const dialog = await screen.findByRole("alertdialog", { name: /^Request a waiver of / });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Reason \(required\)/ }), {
      target: { value: "Two exceptions wait for the customer's reply." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Request waiver" }));
    expect(await bannerOf(dialog)).toBe(WHOLE);
  });

  it("Sign task says every sentence", async () => {
    const task = {
      ...(checklist([])[0] as ChecklistItem),
      id: "9a8b7c6d-5e4f-4a3b-8c2d-0000000000aa",
      code: "FLUX_REVIEW",
      name: "Flux review",
      gate_kind: "MANUAL" as const,
      gate_check_code: null,
      status: "NOT_STARTED" as const,
      result: null,
    };
    serve(period(), [...checklist([]), task]);
    refuse(`checklist/${task.id}/sign`);
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(await screen.findByRole("button", { name: "Sign task" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Sign Flux review?" });
    fireEvent.click(within(dialog).getByRole("checkbox", { name: "I confirm this statement" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Sign task" }));
    expect(await bannerOf(dialog)).toBe(WHOLE);
  });

  it("Permanently lock says every sentence", async () => {
    const august = period({
      id: "7c1d2e3f-4a5b-4c6d-8e7f-000000000908",
      state: "permanently_locked",
      row_version: 7,
      is_first_open: false,
      period: {
        id: "1c2d3e4f-5a6b-4c7d-8e9f-000000000008",
        period_key: "FY2026-P08",
        name: "Aug 2026",
        fiscal_year: 2026,
        period_no: 8,
        quarter_no: 3,
        start_date: "2026-08-01",
        end_date: "2026-08-31",
      },
    });
    const september = period({ state: "closed", row_version: 5 });
    serve(september, checklist([]));
    server.use(
      http.get(apiUrl("/api/v1/periods"), () =>
        HttpResponse.json({ items: [august, september], next_cursor: null }),
      ),
    );
    refuse("request-permanent-lock");
    renderApp(COCKPIT_PATH, { me: MARCUS, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(await screen.findByRole("button", { name: "More close actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Permanently lock" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Permanently lock Sep 2026 for AVM-US?",
    });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Comment \(required\)/ }), {
      target: { value: PERMANENT_COMMENT },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Request permanent lock" }));
    expect(await bannerOf(dialog)).toBe(WHOLE);
  });

  it("Withdraw request says every sentence in its confirmation", async () => {
    serve(period({ state: "closed", row_version: 5 }), checklist([]));
    server.use(
      http.get(apiUrl("/api/v1/approvals"), () =>
        HttpResponse.json({ items: [approval("PERIOD_REOPEN", PRIYA_ACTOR)], next_cursor: null }),
      ),
      http.get(apiUrl(`/api/v1/approvals/${REOPEN_REQUEST_ID}`), () =>
        HttpResponse.json(approval("PERIOD_REOPEN", PRIYA_ACTOR)),
      ),
      http.post(apiUrl(`/api/v1/approvals/${REOPEN_REQUEST_ID}/withdraw`), () =>
        refusedWith({ status: SENTENCE }),
      ),
    );
    renderApp(COCKPIT_PATH, { me: PRIYA, screenRoutes: SCREEN_ROUTES });
    const banner = await screen.findByTestId("SF-05-banner-reopen-request");
    fireEvent.click(await within(banner).findByRole("button", { name: "Withdraw request" }));
    const confirm = await screen.findByRole("alertdialog", {
      name: "Withdraw the reopen request?",
    });
    fireEvent.click(within(confirm).getByRole("button", { name: "Withdraw request" }));
    expect(await bannerOf(confirm)).toBe(WHOLE);
  });

  it("Run close says every sentence on the page", async () => {
    serve(period({ state: "open" }), checklist([]));
    server.use(
      http.post(apiUrl("/api/v1/close-runs"), () => refusedWith({ period_key: SENTENCE })),
    );
    renderApp(COCKPIT_PATH, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(await screen.findByRole("button", { name: "Run close" }));
    const heading = await screen.findByRole("heading", { name: REFUSAL_TITLE });
    expect(heading.closest('[role="alert"]')?.textContent).toBe(WHOLE);
  });
});
