// @vitest-environment jsdom
// SF-05:history (BUILD_SPEC CLO-24; SCREENS_B §1.4, §0.4 E-04; SCREENS SCR-URL-12, SCR-PERM-02, SCR-ST-03;
// 04 API-R-18 `locks` and `transitions`, T-CLS-04, API-R-09; PRD J-14.7, BR-CLS-07; supervisor ruling
// R-94 (d)): the lock, reopen and permanent-lock records of a period with the person who made each, its
// approval by number, the re-lock's difference and the instant the snapshot was frozen at; and the
// period's state changes as an activity list. API answers are contract fakes of 04 §16.8 and §16.10.
import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../../app/router";
import type { Approval } from "../../../lib/api/queries/approvals";
import type { Me } from "../../../lib/api/queries/me";
import type {
  PeriodCockpit,
  PeriodLockRow,
  PeriodTransition,
} from "../../../lib/api/queries/periods";
import type { Period } from "../../../lib/api/queries/tenant";
import { installMemoryStorage, renderApp, signedInMe } from "../../../test/app";
import { narrowColumns } from "../../../test/grid-headers";
import { installGridViewport } from "../../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import { HIDDEN_LOCK_COLUMNS, LOCKS_ROOM_1440, lockColumns } from "../history";

installMswServer();
installMemoryStorage();
installGridViewport();
// The cockpit frame reads the periods, then the cockpit, before a tab renders.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
});

const CONTEXT = "entity=AVM-US&period=FY2026-P09&book=ASC606";
// The canonical URL of the tab, as the cockpit's own links write it (SCR-URL-01 to SCR-URL-03).
const HISTORY_PATH = `/close/AVM-US/ASC606/FY2026-P09/history?${CONTEXT}`;
const STATE_ID = "7c1d2e3f-4a5b-4c6d-8e7f-000000000909";
const FIRST_LOCK = "a1000000-0000-4000-8000-000000000001";
const REOPEN = "a1000000-0000-4000-8000-000000000002";
const RELOCK = "a1000000-0000-4000-8000-000000000003";
const LOCK_REQUEST = "9e8d7c6b-5a4f-4e3d-8c2b-000000000212";
const REOPEN_REQUEST = "9e8d7c6b-5a4f-4e3d-8c2b-000000000539";
const RELOCK_REQUEST = "9e8d7c6b-5a4f-4e3d-8c2b-000000000540";
const DIFF_FILE = "d1ff0000-0000-4000-8000-000000000001";
const MANIFEST = `8b10${"c3".repeat(28)}aa42`;
/** DS-FMT-10: the dash of an absent value, with its text for a screen reader. */
const NO_VALUE = "—No value";
const REOPEN_COMMENT =
  "Costs of 20,500.00 on PRJ-CB-2026-01 incurred on 29 Sep 2026 were omitted from the September cost file.";

const AVM_US = {
  id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000001",
  code: "AVM-US",
  name: "Avenmoor Inc. (Demo)",
};
const MARCUS_ACTOR = {
  id: "6d2e9b8f-3c5a-4d7e-8f9b-8a7c6d5e4f3b",
  display_name: "Marcus Webb",
  kind: "USER" as const,
};
const PRIYA_ACTOR = {
  id: "4d3c2b1a-0f9e-4d8c-9b7a-6f5e4d3c2b1a",
  display_name: "Priya Raman",
  kind: "USER" as const,
};
const MAYA_ACTOR = {
  id: "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a",
  display_name: "Maya Chen",
  kind: "USER" as const,
};
const ELENA_ACTOR = {
  id: "7e3f0c9a-4d6b-4e8f-9a0c-9b8d7e6f5a4c",
  display_name: "Elena Sokolova",
  kind: "USER" as const,
};

/** Controller: reads the requests of the period, runs reports and exports them. */
const MARCUS: Me = signedInMe({
  user: {
    id: MARCUS_ACTOR.id,
    email: "marcus@example.test",
    display_name: MARCUS_ACTOR.display_name,
    status: "ACTIVE",
  },
  permissions: [
    "contract.read",
    "config.read",
    "period.close",
    "period.lock",
    "report.run",
    "report.export",
  ],
});
/** Revenue Accountant: `period.close`; she prepares lock requests and decides none. */
const MAYA: Me = signedInMe({ permissions: ["contract.read", "config.read", "period.close"] });
/** A reader of the close: no request of the period is visible to him and he runs no report. */
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
    state: "closed",
    state_changed_at: "2026-10-02T10:02:11Z",
    is_first_open: false,
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
    row_version: 9,
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

const LEDGER_HEAD = `3fa9${"d2".repeat(28)}19c4`;
const WAIVER_REQUEST = "9e8d7c6b-5a4f-4e3d-8c2b-000000000520";

/** The fourteen gates a lock certifies, in checklist order, with the label the cockpit gives each. */
const GATES: readonly (readonly [string, string])[] = [
  ["INTERFACES_COMPLETE", "Interface batches complete"],
  ["EXCEPTIONS_CLEARED", "Exceptions resolved, waived or dismissed"],
  ["DATA_QUALITY_CLEAR", "Data-quality errors cleared"],
  ["NO_DIRTY_GROUPS", "All contracts computed"],
  ["HOLDS_REVIEWED", "Holds released or waived"],
  ["JUDGEMENTS_REVIEWED", "Judgements reviewed"],
  ["MANUAL_ADJUSTMENTS_CLEARED", "Manual adjustments cleared"],
  ["APPROVALS_CLEARED", "No pending approvals"],
  ["CLOSE_RUN_COMPLETED", "Close run completed"],
  ["JE_COMPLETE", "Journals complete"],
  ["JE_BALANCED", "Journals balance per currency"],
  ["BATCHES_ACKNOWLEDGED", "Batches acknowledged by the GL"],
  ["RECONCILIATIONS_GENERATED", "Reconciliations generated and reviewed"],
  ["CONTROLLER_CERTIFIED", "Controller certification"],
];

/**
 * API-S-PeriodLock `certification` (04 §16.8 rev 1.207): the gate results as the lock stored them.
 * `waived` names a gate that was waived: its waiver request's number and the count at its approval.
 */
function certification(evaluatedAt: string, waived?: string): PeriodLockRow["certification"] {
  return GATES.map(([code]) =>
    code === waived
      ? {
          gate_check_code: code,
          status: "WAIVED",
          // Two counts (R-55 (b)): what the gate computed at the decision, and what its item held
          // when the waiver was approved.
          count: 3,
          evaluated_at: evaluatedAt,
          replayed: false,
          waived_count: 2,
          waiver_approval_request_id: WAIVER_REQUEST,
          waiver_approval_request_no: "APR-000520",
        }
      : {
          gate_check_code: code,
          status: "PASSED",
          // The certification gate counts nothing.
          count: code === "CONTROLLER_CERTIFIED" ? null : 0,
          evaluated_at: evaluatedAt,
          replayed: false,
          waived_count: null,
          waiver_approval_request_id: null,
          waiver_approval_request_no: null,
        },
  );
}

/** The twelve datasets a lock freezes, in E-64 order, with the name of the report each is the run of. */
const DATASETS: readonly (readonly [
  PeriodLockRow["snapshots"][number]["snapshot_kind"],
  string,
])[] = [
  ["WATERFALL", "Revenue waterfall"],
  ["CONTRACT_BALANCES", "Contract balances"],
  ["CONTRACT_BALANCE_ROLLFORWARD", "Contract balance rollforward"],
  ["RPO", "Remaining performance obligations"],
  ["RPO_ROLLFORWARD", "RPO rollforward"],
  ["DISAGGREGATION", "Disaggregation of revenue"],
  ["PRIOR_PERIOD_POB_REVENUE", "Revenue from obligations satisfied in prior periods"],
  ["COST_ROLLFORWARD", "Contract cost rollforward"],
  ["JE_POPULATION", "Journal entry population"],
  ["OUT_OF_PERIOD_REGISTER", "Out-of-period register"],
  ["MODIFICATION_REGISTER", "Modification register"],
  ["MANUAL_ADJUSTMENT_REGISTER", "Manual adjustment register"],
];

/** API-S-PeriodLock `snapshots`: kind, row count and file hash of each dataset. */
function snapshots(firstRows: number): PeriodLockRow["snapshots"] {
  return DATASETS.map(([kind], index) => ({
    snapshot_kind: kind,
    row_count: firstRows + index * 100,
    file_sha256: `${String(index + 10)}aa${"e1".repeat(28)}${String(index + 10)}bb`,
  }));
}

/** J-14.7: the September lock, its reopen and the re-lock, newest first. */
const LOCKS: readonly PeriodLockRow[] = [
  {
    id: RELOCK,
    kind: "LOCK",
    created_at: "2026-10-02T10:02:11Z",
    created_by: MARCUS_ACTOR,
    approval_request_id: RELOCK_REQUEST,
    reason_code: null,
    comment: null,
    ledger_head_chain_seq: 1388,
    audit_head_chain_seq: 9112,
    snapshot_manifest_sha256: MANIFEST,
    cutoff_known_at: "2026-10-02T10:02:09Z",
    previous_lock_id: FIRST_LOCK,
    diff_report_file_id: DIFF_FILE,
    approval_request_no: "APR-000540",
    certification: certification("2026-10-02T10:01:40Z", "HOLDS_REVIEWED"),
    ledger_head_sha256: LEDGER_HEAD,
    snapshots: snapshots(1412),
  },
  {
    id: REOPEN,
    kind: "REOPEN",
    created_at: "2026-10-01T16:40:00Z",
    created_by: PRIYA_ACTOR,
    approval_request_id: REOPEN_REQUEST,
    reason_code: "ERROR_CORRECTION",
    comment: REOPEN_COMMENT,
    ledger_head_chain_seq: 1342,
    audit_head_chain_seq: 9040,
    snapshot_manifest_sha256: null,
    cutoff_known_at: null,
    previous_lock_id: FIRST_LOCK,
    diff_report_file_id: null,
    // A reopen certifies nothing and freezes nothing.
    approval_request_no: "APR-000539",
    certification: [],
    ledger_head_sha256: `77c1${"9a".repeat(28)}0e5d`,
    snapshots: [],
  },
  {
    id: FIRST_LOCK,
    kind: "LOCK",
    created_at: "2026-10-01T09:14:00Z",
    created_by: MARCUS_ACTOR,
    approval_request_id: LOCK_REQUEST,
    reason_code: null,
    comment: null,
    ledger_head_chain_seq: 1342,
    audit_head_chain_seq: 9001,
    snapshot_manifest_sha256: `77aa${"0f".repeat(28)}19c4`,
    cutoff_known_at: "2026-10-01T09:13:58Z",
    previous_lock_id: null,
    diff_report_file_id: null,
    approval_request_no: "APR-000212",
    certification: certification("2026-10-01T09:13:30Z"),
    ledger_head_sha256: `77c1${"9a".repeat(28)}0e5d`,
    snapshots: snapshots(1300),
  },
];

function transition(
  id: string,
  from: PeriodTransition["from_state"],
  to: PeriodTransition["to_state"],
  at: string,
  by: PeriodTransition["created_by"],
  extra: Partial<PeriodTransition> = {},
): PeriodTransition {
  return {
    id,
    period_state_id: STATE_ID,
    from_state: from,
    to_state: to,
    reason_code: null,
    comment: null,
    approval_request_id: null,
    approval_request_no: null,
    close_run_id: null,
    period_lock_id: null,
    created_at: at,
    created_by: by,
    ...extra,
  };
}

const TRANSITIONS: readonly PeriodTransition[] = [
  transition(
    "b2000000-0000-4000-8000-000000000006",
    "reopened",
    "closed",
    "2026-10-02T10:02:11Z",
    MARCUS_ACTOR,
    {
      approval_request_id: RELOCK_REQUEST,
      approval_request_no: "APR-000540",
      period_lock_id: RELOCK,
    },
  ),
  transition(
    "b2000000-0000-4000-8000-000000000005",
    "closed",
    "reopened",
    "2026-10-01T16:40:00Z",
    PRIYA_ACTOR,
    {
      approval_request_id: REOPEN_REQUEST,
      approval_request_no: "APR-000539",
      period_lock_id: REOPEN,
      reason_code: "ERROR_CORRECTION",
      comment: REOPEN_COMMENT,
    },
  ),
  transition(
    "b2000000-0000-4000-8000-000000000004",
    "closing",
    "closed",
    "2026-10-01T09:14:00Z",
    MARCUS_ACTOR,
    {
      approval_request_id: LOCK_REQUEST,
      approval_request_no: "APR-000212",
      period_lock_id: FIRST_LOCK,
    },
  ),
  transition(
    "b2000000-0000-4000-8000-000000000003",
    "open",
    "closing",
    "2026-09-30T17:05:00Z",
    MAYA_ACTOR,
  ),
  transition("b2000000-0000-4000-8000-000000000002", "future", "open", "2026-09-01T00:00:00Z", {
    id: null,
    display_name: "System",
    kind: "SYSTEM",
  }),
];

function approval(
  id: string,
  number: string,
  type: "PERIOD_LOCK" | "PERIOD_REOPEN",
  preparer: Approval["preparer"],
  decisions: Approval["steps"][number]["decisions"],
): Approval {
  const lock = type === "PERIOD_LOCK";
  return {
    id,
    request_no: number,
    subject: {
      type,
      id: STATE_ID,
      display: "FY2026-P09",
      href: null,
      content_sha256: "ab".repeat(32),
      row_version: 4,
    },
    summary: `${lock ? "Lock" : "Reopen"} FY2026-P09 for AVM-US in book ASC606`,
    status: "APPROVED",
    entity: AVM_US,
    // One entity names the request (04 API-S-Approval since revision 0086; ruling R-25).
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
    submitted_at: "2026-10-01T08:30:00Z",
    decided_at: "2026-10-01T09:14:00Z",
    voided_at: null,
    void_reason: null,
    current_step_no: 1,
    steps: [
      {
        step_no: 1,
        name: lock ? "Controller" : "Dual approval",
        required_permission: lock ? "period.lock" : "period.reopen_approve",
        min_approvers: lock ? 1 : 2,
        status: "APPROVED",
        decisions,
      },
    ],
  };
}

function decision(
  id: string,
  approver: Approval["preparer"],
  at: string,
  onBehalfOf: Approval["preparer"] | null = null,
): Approval["steps"][number]["decisions"][number] {
  return {
    id,
    decision: "APPROVE",
    approver,
    on_behalf_of: onBehalfOf,
    decided_at: at,
    comment: null,
    reason_code: null,
    auto_rule_key: null,
  };
}

const APPROVALS: Readonly<Record<string, Approval>> = {
  [LOCK_REQUEST]: approval(LOCK_REQUEST, "APR-000212", "PERIOD_LOCK", MAYA_ACTOR, [
    decision("c3000000-0000-4000-8000-000000000001", MARCUS_ACTOR, "2026-10-01T09:14:00Z"),
  ]),
  [REOPEN_REQUEST]: approval(REOPEN_REQUEST, "APR-000539", "PERIOD_REOPEN", PRIYA_ACTOR, [
    decision("c3000000-0000-4000-8000-000000000002", MARCUS_ACTOR, "2026-10-01T15:10:00Z"),
    decision(
      "c3000000-0000-4000-8000-000000000003",
      ELENA_ACTOR,
      "2026-10-01T16:40:00Z",
      MAYA_ACTOR,
    ),
  ]),
  [RELOCK_REQUEST]: approval(RELOCK_REQUEST, "APR-000540", "PERIOD_LOCK", MAYA_ACTOR, [
    decision("c3000000-0000-4000-8000-000000000004", MARCUS_ACTOR, "2026-10-02T10:02:11Z"),
  ]),
};

interface World {
  readonly state?: Period;
  readonly locks?: readonly PeriodLockRow[];
  /** The pages of the state history, newest first; a page names the next by its index. */
  readonly pages?: readonly (readonly PeriodTransition[])[];
  /** Whether the reader may read the period's approval requests (API-R-09 visibility). */
  readonly requestsVisible?: boolean;
}

interface Traffic {
  readonly transitionReads: string[];
  readonly approvalReads: string[];
}

function serve(world: World = {}): Traffic {
  const state = world.state ?? period();
  const pages = world.pages ?? [TRANSITIONS];
  const traffic: Traffic = { transitionReads: [], approvalReads: [] };
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
        ],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/periods"), () =>
      HttpResponse.json({ items: [state], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/periods/:periodId/cockpit"), () => HttpResponse.json(cockpit(state))),
    http.get(apiUrl("/api/v1/periods/:periodId/locks"), () =>
      HttpResponse.json({ items: world.locks ?? LOCKS, next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/periods/:periodId/transitions"), ({ request }) => {
      const params = new URL(request.url).searchParams;
      traffic.transitionReads.push(params.toString());
      const index = Number(params.get("cursor") ?? "0");
      return HttpResponse.json({
        items: pages[index] ?? [],
        next_cursor: index + 1 < pages.length ? String(index + 1) : null,
      });
    }),
    http.get(apiUrl("/api/v1/approvals/:requestId"), ({ params }) => {
      const id = String(params.requestId);
      traffic.approvalReads.push(id);
      const found = world.requestsVisible === false ? undefined : APPROVALS[id];
      return found === undefined
        ? problemResponse("not-found", 404, "Not found")
        : HttpResponse.json(found);
    }),
  );
  return traffic;
}

function open(me: Me, path = HISTORY_PATH) {
  return renderApp(path, { me, screenRoutes: SCREEN_ROUTES });
}

function cellTexts(grid: HTMLElement, column: string): (string | null)[] {
  return [...grid.querySelectorAll(`[role="row"] [data-column="${column}"]`)]
    .filter((cell) => cell.getAttribute("role") !== "columnheader")
    .map((cell) => cell.textContent);
}

describe("SF-05:history", () => {
  it("every column of the locks grid holds its header and its instant; the shown ones fit at 1440 px", () => {
    // DS-CMP-10, DS-AP-10: jsdom has no layout, so the widths are held to what a header and a
    // DS-FMT-17 instant need (src/test/grid-headers.ts: an instant with the cell padding measured
    // 186 px in the browser), and the shown columns to the grid's room beside the activity.
    const columns = lockColumns({
      locks: [],
      approvals: new Map(),
      permissions: [],
      ctxSearch: "",
      requestsBuilt: false,
      reportsBuilt: false,
      onOpen: () => undefined,
      navigate: () => undefined,
    });
    expect(narrowColumns(columns)).toEqual([]);
    const shown = columns.filter((column) => !HIDDEN_LOCK_COLUMNS.includes(column.id));
    expect(shown.map((column) => column.header)).toEqual([
      "Kind",
      "Recorded",
      "By",
      "Approval",
      "Diff report",
    ]);
    expect(shown.reduce((sum, column) => sum + (column.width ?? 0), 0)).toBeLessThanOrEqual(
      LOCKS_ROOM_1440,
    );
    // "Frozen as known at" is to the second: three characters more than the instant of the kit.
    expect(columns.find((column) => column.id === "cutoff")?.width).toBeGreaterThanOrEqual(216);
    // "Previous lock" names a record by kind and instant: "Reopen, recorded 01 Oct 2026 16:40 UTC".
    expect(columns.find((column) => column.id === "previous")?.width).toBeGreaterThanOrEqual(296);
  });

  it("lock records with their approvals and the re-lock's difference; state changes as activity", async () => {
    const traffic = serve();
    open(MARCUS);

    const grid = await screen.findByRole("grid", { name: "Locks" });
    expect(grid.closest('[data-testid="SF-05-grid-locks"]')).not.toBeNull();
    await within(grid).findByRole("link", { name: "APR-000540" });
    // The columns of the wireframe; the reason, the head sequences, the manifest, the frozen instant
    // and the previous lock are in the column chooser and in the record's drawer.
    expect(
      within(grid)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["Kind", "Recorded", "By", "Approval", "Diff report"]);
    expect(cellTexts(grid, "kind")).toEqual(["Lock", "Reopen", "Lock"]);
    expect(cellTexts(grid, "recorded")).toEqual([
      "02 Oct 2026 10:02 UTC",
      "01 Oct 2026 16:40 UTC",
      "01 Oct 2026 09:14 UTC",
    ]);
    // The person, not an id (04 API-S-Actor).
    expect(cellTexts(grid, "by")).toEqual(["Marcus Webb", "Priya Raman", "Marcus Webb"]);
    expect(cellTexts(grid, "approval")).toEqual(["APR-000540", "APR-000539", "APR-000212"]);
    expect(within(grid).getByRole("link", { name: "APR-000539" }).getAttribute("href")).toBe(
      `/approvals/requests/${REOPEN_REQUEST}`,
    );
    // The re-lock opens RPT-38 between the two locks and downloads the stored file; a reopen changes
    // no figure; a first lock has nothing before it.
    const diff = within(grid).getByRole("link", { name: "Open diff report" });
    expect(diff.getAttribute("data-testid")).toBe("SF-05-row-diff-report");
    expect(diff.getAttribute("href")).toBe(
      `/reports/variance_between_closes?${CONTEXT}&p.from_period_lock_id=${FIRST_LOCK}&p.to_period_lock_id=${RELOCK}`,
    );
    expect(within(grid).getByRole("link", { name: "Download file" }).getAttribute("href")).toBe(
      `/api/v1/files/${DIFF_FILE}/content`,
    );
    expect(cellTexts(grid, "diff")).toEqual([
      "Open diff reportDownload file",
      NO_VALUE,
      "No previous lock",
    ]);
    // Each request is read once, by its id.
    expect([...traffic.approvalReads].sort()).toEqual(
      [LOCK_REQUEST, REOPEN_REQUEST, RELOCK_REQUEST].sort(),
    );

    // The newest lock's heads and manifest, under the grid.
    const current = screen.getByRole("group", { name: "Lock, recorded 02 Oct 2026 10:02 UTC" });
    expect(current.textContent).toContain("Snapshot manifest8b10c3c3…aa42");
    expect(current.textContent).toContain("Ledger head1,388");
    expect(current.textContent).toContain("Audit head9,112");
    expect(within(current).getByRole("button", { name: "Copy Snapshot manifest" })).toBeTruthy();

    // The state changes, newest first, under their dates.
    const region = screen.getByRole("region", { name: "State transitions" });
    expect(region.getAttribute("data-testid")).toBe("SF-05-timeline-transitions");
    const events = within(within(region).getByRole("list", { name: "Activity" })).getAllByRole(
      "listitem",
    );
    expect(events).toHaveLength(5);
    expect(events[0]?.textContent).toContain(
      "Marcus Webb changed the period from Reopened to Locked with approval APR-000540",
    );
    expect(events[0]?.textContent).toContain("02 Oct 2026 10:02:11 UTC");
    expect(events[1]?.textContent).toContain(
      "Priya Raman changed the period from Locked to Reopened with approval APR-000539",
    );
    expect(events[1]?.textContent).toContain(`Reason: Error correction. ${REOPEN_COMMENT}`);
    expect(
      within(events[1] as HTMLElement)
        .getByRole("link", { name: "APR-000539" })
        .getAttribute("href"),
    ).toBe(`/approvals/requests/${REOPEN_REQUEST}`);
    expect(events[3]?.textContent).toContain(
      "Maya Chen changed the period from Period open to Soft close",
    );
    expect(events[4]?.textContent).toContain(
      "System changed the period from Future to Period open",
    );
    // The tab is the cockpit's.
    expect(
      within(screen.getByRole("navigation", { name: "Close of Sep 2026" }))
        .getByRole("link", { name: "History" })
        .getAttribute("aria-current"),
    ).toBe("page");
  });

  it("a record opens in its drawer: the frozen instant, the decisions and the lock before it", async () => {
    serve();
    const { router } = open(MARCUS);
    const grid = await screen.findByRole("grid", { name: "Locks" });
    await within(grid).findByRole("link", { name: "APR-000539" });

    fireEvent.click(
      within(grid).getByRole("button", { name: "Reopen, recorded 01 Oct 2026 16:40 UTC" }),
    );
    const reopen = await screen.findByRole("dialog", {
      name: "Reopen, recorded 01 Oct 2026 16:40 UTC",
    });
    // SCR-URL-12: the URL names the drawer.
    expect(router.state.location.search).toContain("drawer=lock");
    expect(reopen.textContent).toContain("ByPriya Raman");
    expect(reopen.textContent).toContain("ReasonError correction");
    expect(reopen.textContent).toContain(REOPEN_COMMENT);
    expect(within(reopen).getByRole("link", { name: "APR-000539" })).toBeTruthy();
    // The reopen's two decisions (SCREENS_B §1.1 "Dual-approval status").
    const decisions = within(reopen).getAllByRole("listitem");
    expect(decisions.map((item) => item.textContent)).toEqual([
      "Marcus Webb approved01 Oct 2026 15:10 UTC",
      "Elena Sokolova approvedon behalf of Maya Chen01 Oct 2026 16:40 UTC",
    ]);
    // A reopen record froze no snapshot.
    expect(reopen.textContent).not.toContain("Frozen as known at");

    // The lock it reopened opens from "Previous lock".
    fireEvent.click(
      within(reopen).getByRole("button", { name: "Lock, recorded 01 Oct 2026 09:14 UTC" }),
    );
    const first = await screen.findByRole("dialog", {
      name: "Lock, recorded 01 Oct 2026 09:14 UTC",
    });
    // Supervisor ruling R-94 (d): the instant the lock's snapshot was frozen at, to the second.
    expect(first.textContent).toContain("SnapshotFrozen as known at 01 Oct 2026 09:13:58 UTC");
    expect(first.textContent).toContain("Ledger head1,342");
    expect(first.textContent).toContain("Audit head9,001");
    expect(first.textContent).toContain("Diff reportNo previous lock");
    expect(within(first).getByRole("button", { name: "Copy Snapshot manifest" })).toBeTruthy();

    fireEvent.click(within(first).getByRole("button", { name: "Close" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(router.state.location.search).not.toContain("drawer=");
  });

  it("a link with drawer=lock opens the newest record", async () => {
    serve();
    open(MARCUS, `${HISTORY_PATH}&drawer=lock`);
    const newest = await screen.findByRole("dialog", {
      name: "Lock, recorded 02 Oct 2026 10:02 UTC",
    });
    expect(newest.textContent).toContain("SnapshotFrozen as known at 02 Oct 2026 10:02:09 UTC");
    expect(
      within(newest).getByRole("link", { name: "Open diff report" }).getAttribute("href"),
    ).toContain(`p.from_period_lock_id=${FIRST_LOCK}&p.to_period_lock_id=${RELOCK}`);
  });

  it("a reader who may not read the requests or run reports sees the records without links", async () => {
    // A reader of the close holds no permission that makes a period's request visible (API-R-09):
    // none is asked for, so the API has no 404 to answer. The record states the number of its request
    // (§1.4 rev 1.67), so he reads the number and cannot open the request.
    const traffic = serve({ requestsVisible: false });
    open(ROBERT);
    const grid = await screen.findByRole("grid", { name: "Locks" });
    await waitFor(() => {
      expect(cellTexts(grid, "approval")).toEqual(["APR-000540", "APR-000539", "APR-000212"]);
    });
    expect(within(grid).queryByRole("link", { name: /^APR-/ })).toBeNull();
    expect(cellTexts(grid, "by")).toEqual(["Marcus Webb", "Priya Raman", "Marcus Webb"]);
    // SCR-PERM-02: no report and no file without `report.run`, `report.export` or `evidence.export`.
    expect(within(grid).queryByRole("link", { name: "Open diff report" })).toBeNull();
    expect(within(grid).queryByRole("link", { name: "Download file" })).toBeNull();
    expect(cellTexts(grid, "diff")).toEqual([NO_VALUE, NO_VALUE, "No previous lock"]);
    // The activity names the change, the person and the request by its number, without a link.
    const events = within(screen.getByRole("list", { name: "Activity" })).getAllByRole("listitem");
    expect(events[0]?.textContent).toContain(
      "Marcus Webb changed the period from Reopened to Locked with approval APR-000540",
    );
    expect(within(events[0] as HTMLElement).queryByRole("link")).toBeNull();
    expect(traffic.approvalReads).toEqual([]);
    cleanup();

    // A Revenue Accountant may have prepared a request, so each is asked for; the ones she neither
    // prepared nor decides answer 404, and their numbers stay text.
    const asked = serve({ requestsVisible: false });
    open(MAYA);
    const hers = await screen.findByRole("grid", { name: "Locks" });
    await waitFor(() => {
      expect([...asked.approvalReads].sort()).toEqual(
        [LOCK_REQUEST, REOPEN_REQUEST, RELOCK_REQUEST].sort(),
      );
    });
    expect(cellTexts(hers, "approval")).toEqual(["APR-000540", "APR-000539", "APR-000212"]);
    expect(within(hers).queryByRole("link", { name: /^APR-/ })).toBeNull();
    cleanup();

    // A request outside the reader's row scope: the record states no number (04 rev 1.207), and the
    // cell and the activity name none.
    serve({
      requestsVisible: false,
      locks: LOCKS.map((lock) => ({ ...lock, approval_request_no: null })),
      pages: [TRANSITIONS.map((move) => ({ ...move, approval_request_no: null }))],
    });
    open(ROBERT);
    const unnamed = await screen.findByRole("grid", { name: "Locks" });
    await waitFor(() => {
      expect(cellTexts(unnamed, "approval")).toEqual([NO_VALUE, NO_VALUE, NO_VALUE]);
    });
    const plain = within(screen.getByRole("list", { name: "Activity" })).getAllByRole("listitem");
    expect(plain[0]?.textContent).toContain(
      "Marcus Webb changed the period from Reopened to Locked",
    );
    expect(plain[0]?.textContent).not.toContain("with approval");
    cleanup();

    // A first state reads without a "from"; its request is named by the number in the same way.
    serve({
      requestsVisible: false,
      locks: [],
      pages: [
        [
          transition(
            "b2000000-0000-4000-8000-000000000001",
            null,
            "closed",
            "2026-10-01T09:14:00Z",
            MARCUS_ACTOR,
            { approval_request_id: LOCK_REQUEST, approval_request_no: "APR-000212" },
          ),
        ],
      ],
    });
    open(ROBERT);
    const first = await screen.findByRole("list", { name: "Activity" });
    expect((await within(first).findAllByRole("listitem"))[0]?.textContent).toContain(
      "Marcus Webb set the period to Locked with approval APR-000212",
    );
    expect(within(first).queryByRole("link")).toBeNull();
  });

  it("a lock's drawer lists what it certified and what it froze; a reopen has neither", async () => {
    serve();
    open(MARCUS, `${HISTORY_PATH}&drawer=lock`);
    const relock = await screen.findByRole("dialog", {
      name: "Lock, recorded 02 Oct 2026 10:02 UTC",
    });
    // §1.4 rev 1.81: the wide drawer — the four columns of "Certification" do not fit the narrow one.
    // jsdom lays nothing out, so the variant is read from the panel's width class.
    expect(relock.className).toContain("w-[var(--drawer-w-wide)]");

    // §1.4 rev 1.67: the static table "Certification" — the fourteen gate results as the lock stored
    // them, in the API's order, with the labels and the chip of the checklist.
    const certified = within(relock).getByRole("table", { name: "Certification" });
    const [head, ...gates] = within(certified).getAllByRole("row");
    expect(
      within(head as HTMLElement)
        .getAllByRole("columnheader")
        .map((cell) => cell.textContent),
    ).toEqual(["Gate", "Status", "Count", "Evaluated"]);
    expect(gates.map((row) => within(row).getByRole("rowheader").textContent)).toEqual(
      GATES.map(([, label]) => label),
    );
    expect(gates[0]?.textContent).toBe("Interface batches completePassed002 Oct 2026 10:01 UTC");
    // A waived gate names its waiver's request and the count when the waiver was approved (2), beside
    // the count the gate computed at the decision (3).
    expect(gates[4]?.textContent).toBe(
      "Holds released or waivedWaivedWaiver APR-000520, 2 at approval302 Oct 2026 10:01 UTC",
    );
    // The certification itself counts nothing.
    expect(gates[13]?.textContent).toBe(
      `Controller certificationPassed${NO_VALUE}02 Oct 2026 10:01 UTC`,
    );

    // The datasets the lock froze, in E-64 order, each with its rows and its file's hash.
    const frozen = within(relock).getByRole("table", { name: "Frozen datasets" });
    const [columns, ...datasets] = within(frozen).getAllByRole("row");
    expect(
      within(columns as HTMLElement)
        .getAllByRole("columnheader")
        .map((cell) => cell.textContent),
    ).toEqual(["Dataset", "Rows", "File hash"]);
    expect(datasets.map((row) => within(row).getByRole("rowheader").textContent)).toEqual(
      DATASETS.map(([, name]) => name),
    );
    expect(datasets[0]?.textContent).toContain("Revenue waterfall1,41210aae1e1…10bb");
    expect(datasets[11]?.textContent).toContain("Manual adjustment register2,51221aae1e1…21bb");
    expect(
      within(frozen).getByRole("button", { name: "Copy file hash of Revenue waterfall" }),
    ).toBeTruthy();
    expect(within(frozen).getAllByRole("button", { name: /^Copy file hash of / })).toHaveLength(12);

    // "Ledger head": the sequence, and the hash the record states — its prefix, the value and copy.
    expect(relock.textContent).toContain("Ledger head1,3883fa9d2d2…19c4");
    expect(within(relock).getByRole("button", { name: "Copy Ledger head" })).toBeTruthy();

    // The reopen before it certified nothing and froze nothing.
    fireEvent.click(within(relock).getByRole("button", { name: "Close" }));
    const grid = await screen.findByRole("grid", { name: "Locks" });
    fireEvent.click(
      await within(grid).findByRole("button", { name: "Reopen, recorded 01 Oct 2026 16:40 UTC" }),
    );
    const reopen = await screen.findByRole("dialog", {
      name: "Reopen, recorded 01 Oct 2026 16:40 UTC",
    });
    expect(within(reopen).queryByRole("table", { name: "Certification" })).toBeNull();
    expect(within(reopen).queryByRole("table", { name: "Frozen datasets" })).toBeNull();
  });

  it("the ledger head shows the prefix of its hash where the record states one", async () => {
    // A record of a book without a seal states no hash (04 rev 1.207): the sequence stands alone.
    const unsealed = LOCKS.map((lock) =>
      lock.id === FIRST_LOCK ? { ...lock, ledger_head_sha256: null } : lock,
    );
    serve({ locks: unsealed });
    open(MARCUS);
    await screen.findByRole("grid", { name: "Locks" });

    // Under the grid: the newest lock's head, described by the prefix of its hash.
    const current = await screen.findByRole("group", {
      name: "Lock, recorded 02 Oct 2026 10:02 UTC",
    });
    const head = within(current).getByText("1,388");
    const described = (head.getAttribute("aria-describedby") ?? "").split(" ").filter(Boolean);
    expect(described.map((id) => document.getElementById(id)?.textContent)).toEqual([
      "3fa9d2d2…19c4",
    ]);
    cleanup();

    serve({ locks: unsealed.filter((lock) => lock.id === FIRST_LOCK) });
    open(MARCUS);
    const alone = await screen.findByRole("group", {
      name: "Lock, recorded 01 Oct 2026 09:14 UTC",
    });
    expect(within(alone).getByText("1,342").getAttribute("aria-describedby")).toBeNull();
    const grid = await screen.findByRole("grid", { name: "Locks" });
    fireEvent.click(
      await within(grid).findByRole("button", { name: "Lock, recorded 01 Oct 2026 09:14 UTC" }),
    );
    const first = await screen.findByRole("dialog", {
      name: "Lock, recorded 01 Oct 2026 09:14 UTC",
    });
    expect(first.textContent).toContain("Ledger head1,342Audit head");
    expect(within(first).queryByRole("button", { name: "Copy Ledger head" })).toBeNull();
  });

  it("a permanent lock's drawer shows its certification alone, as it was stored", async () => {
    // 04 API-S-PeriodLock: a permanent lock holds the fourteen results and freezes no dataset.
    const permanent: PeriodLockRow = {
      id: "a1000000-0000-4000-8000-000000000004",
      kind: "PERMANENT_LOCK",
      created_at: "2026-11-02T08:00:05Z",
      created_by: MARCUS_ACTOR,
      approval_request_id: "9e8d7c6b-5a4f-4e3d-8c2b-000000000541",
      approval_request_no: "APR-000541",
      reason_code: null,
      comment: null,
      ledger_head_chain_seq: 1388,
      ledger_head_sha256: LEDGER_HEAD,
      audit_head_chain_seq: 9240,
      snapshot_manifest_sha256: null,
      cutoff_known_at: null,
      previous_lock_id: RELOCK,
      diff_report_file_id: null,
      certification: certification("2026-11-02T07:59:40Z", "HOLDS_REVIEWED").map((gate) => {
        // The result the replay of a source lock laid over a sandbox's own evaluation (R-116 (e)).
        if (gate.gate_check_code === "CLOSE_RUN_COMPLETED") {
          return { ...gate, replayed: true };
        }
        // A waiver whose request lies outside the reader's row scope: the API states no number.
        if (gate.gate_check_code === "HOLDS_REVIEWED") {
          return { ...gate, waiver_approval_request_no: null };
        }
        return gate;
      }),
      snapshots: [],
    };
    serve({ locks: [permanent, ...LOCKS] });
    open(MARCUS, `${HISTORY_PATH}&drawer=lock`);
    const drawer = await screen.findByRole("dialog", {
      name: "Permanent lock, recorded 02 Nov 2026 08:00 UTC",
    });
    const certified = within(drawer).getByRole("table", { name: "Certification" });
    const [, ...gates] = within(certified).getAllByRole("row");
    expect(gates.map((row) => within(row).getByRole("rowheader").textContent)).toEqual(
      GATES.map(([, label]) => label),
    );
    // §1.4 rev 1.81: a replayed result is not marked — it reads as the result beside it does.
    expect(gates[8]?.textContent).toBe("Close run completedPassed002 Nov 2026 07:59 UTC");
    expect(gates[9]?.textContent).toBe("Journals completePassed002 Nov 2026 07:59 UTC");
    // A waiver without a number names no request: the chip stands alone, and the count stays.
    expect(gates[4]?.textContent).toBe("Holds released or waivedWaived302 Nov 2026 07:59 UTC");
    expect(within(drawer).queryByRole("table", { name: "Frozen datasets" })).toBeNull();
  });

  it("a period without locks says so; older activity loads a page at a time", async () => {
    const older = [TRANSITIONS[3], TRANSITIONS[4]].filter(
      (item): item is PeriodTransition => item !== undefined,
    );
    const newer = [
      transition(
        "b2000000-0000-4000-8000-000000000009",
        "closing",
        "open",
        "2026-10-01T08:00:00Z",
        MAYA_ACTOR,
        { reason_code: "CLOSE_RESTARTED", comment: null },
      ),
    ];
    const traffic = serve({
      state: period({ state: "open", row_version: 6 }),
      locks: [],
      pages: [newer, older],
    });
    open(MARCUS);

    // SCR-ST-03.
    expect(await screen.findByRole("heading", { name: "No locks yet" })).toBeTruthy();
    expect(
      screen.getByText(
        "Locks, reopens and permanent locks of Sep 2026 appear here with their head hashes and snapshots.",
      ),
    ).toBeTruthy();
    expect(screen.queryByTestId("SF-05-current-lock")).toBeNull();

    const list = await screen.findByRole("list", { name: "Activity" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(list.textContent).toContain(
      "Maya Chen changed the period from Soft close to Period open",
    );
    expect(list.textContent).toContain("Reason: Close restarted.");
    fireEvent.click(screen.getByRole("button", { name: "Load older activity" }));
    await waitFor(() => {
      expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    });
    expect(screen.queryByRole("button", { name: "Load older activity" })).toBeNull();
    // The second page was read with the cursor of the first; the route's default order is not named.
    expect(traffic.transitionReads).toHaveLength(2);
    expect(traffic.transitionReads[1]).toContain("cursor=1");
    expect(traffic.transitionReads[0]).not.toContain("sort=");
  });

  it("a period of the legacy book has no locks of its own; its state changes stay its history", async () => {
    // SCREENS_B §1.4 rev 1.42 (04 §16.8 rev 1.155, API-S-Period `follows`; supervisor rulings
    // R-112 (e) and R-114 (d)): the LEGACY book follows the close of the primary book, so the empty
    // grid promises no lock, and the tabs are the two such a period has.
    serve({
      state: period({
        book: "LEGACY",
        state: "open",
        row_version: 2,
        follows: { book_code: "ASC606", state: "closed" },
      }),
      locks: [],
      pages: [[TRANSITIONS[4]].filter((item): item is PeriodTransition => item !== undefined)],
    });
    open(
      MARCUS,
      "/close/AVM-US/LEGACY/FY2026-P09/history?entity=AVM-US&period=FY2026-P09&book=LEGACY",
    );

    expect(await screen.findByRole("heading", { name: "No locks" })).toBeTruthy();
    expect(
      screen.getByText("The legacy book has no locks of its own. It follows the close of ASC 606."),
    ).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "No locks yet" })).toBeNull();
    const list = await screen.findByRole("list", { name: "Activity" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(list.textContent).toContain("System changed the period from Future to Period open");
    const tabs = screen.getByRole("navigation", { name: "Close of Sep 2026" });
    expect(
      within(tabs)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["Checklist", "History"]);
  });
});
