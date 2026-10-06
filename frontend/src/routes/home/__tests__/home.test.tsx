// @vitest-environment jsdom
// SF-01 Home (BUILD_SPEC RPS-22; SCREENS §2.4 to §2.7, SCR-PERM-01; XR-14): the key figures drill to the
// screens that own them with the context, a Viewer sees the no-permission approvals copy and the
// "Recently viewed" variant, and a legacy-parity workspace shows "Coming from eRev desktop".
import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../../app/router";
import type { Approval } from "../../../lib/api/queries/approvals";
import type { ContractListItem } from "../../../lib/api/queries/contracts";
import type { DashboardHome, Policy } from "../../../lib/api/queries/dashboard";
import type { Period } from "../../../lib/api/queries/tenant";
import { installMemoryStorage, renderApp, signedInMe, signedInSession } from "../../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";

installMswServer();
installMemoryStorage();
// The page resolves the context, then reads the dashboard, before the figures render.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
});

const HOME_ENTRY = "/home?entity=AVM-US&period=FY2026-P09&book=ASC606";
const CONTEXT = "entity=AVM-US&period=FY2026-P09&book=ASC606";
const TENANT_ID = "0b6f3e2d-1c4a-4b8e-9d7f-6a5c4b3e2d1f";
const STAMP = "2026-09-01T00:00:00Z";
const AVM_US = {
  id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000001",
  code: "AVM-US",
  name: "Avenmoor Inc.",
};

/** Revenue Reviewer: decides activations, adjustments and judgements. */
const PRIYA = signedInMe({
  permissions: [
    "contract.read",
    "config.read",
    "contract.approve",
    "adjustment.approve",
    "judgement.review",
  ],
});
/** Viewer (backend DEFAULT_ROLES `viewer`): reads, reports, no approval permission, no `audit.read`. */
const ROBERT = signedInMe({
  permissions: [
    "contract.read",
    "ssp.read",
    "config.read",
    "report.run",
    "report.export",
    "ai.use",
  ],
});

const ENTITY = {
  ...AVM_US,
  books: [
    {
      id: "5e6f7a8b-9c0d-4e1f-8a2b-000000000001",
      entity_id: AVM_US.id,
      book_code: "ASC606",
      is_enabled: true,
      first_period_id: "1c2d3e4f-5a6b-4c7d-8e9f-000000000001",
      first_period_key: "FY2026-P01",
      created_at: STAMP,
      updated_at: STAMP,
      row_version: 1,
    },
  ],
  calendar_id: "6f7a8b9c-0d1e-4f2a-8b3c-000000000001",
  country_code: "US",
  functional_currency: "USD",
  is_active: true,
  parent_entity_id: null,
  tax_id: null,
  time_zone: "America/New_York",
  created_at: STAMP,
  updated_at: STAMP,
  row_version: 1,
};

const BOOK = {
  id: "7a8b9c0d-1e2f-4a3b-8c4d-000000000001",
  code: "ASC606",
  name: "ASC 606",
  is_enabled: true,
  is_primary: true,
  posting_target: "GL_PRIMARY",
  created_at: STAMP,
  updated_at: STAMP,
  row_version: 1,
};

// `blockers` is null in a row of `GET /periods` alone (04 §16.8 rev 1.199); the counts are an object
const NO_BLOCKERS: NonNullable<Period["blockers"]> = {
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

function period(no: number, state: Period["state"]): Period {
  const month = String(no).padStart(2, "0");
  const last = no === 8 ? "31" : "30";
  return {
    id: `7c1d2e3f-4a5b-4c6d-8e7f-0000000009${month}`,
    entity: AVM_US,
    book: "ASC606",
    period: {
      id: `1c2d3e4f-5a6b-4c7d-8e9f-0000000000${month}`,
      period_key: `FY2026-P${month}`,
      name: no === 8 ? "Aug 2026" : "Sep 2026",
      fiscal_year: 2026,
      period_no: no,
      quarter_no: 3,
      start_date: `2026-${month}-01`,
      end_date: `2026-${month}-${last}`,
    },
    state,
    state_changed_at: STAMP,
    is_first_open: no === 8,
    current_lock: null,
    blockers: NO_BLOCKERS,
    close_run: null,
    row_version: 1,
  };
}

function money(amount: string) {
  return { amount, currency: "USD" };
}

function home(): DashboardHome {
  return {
    context: {
      entity: AVM_US,
      book: "ASC606",
      period: { period_key: "FY2026-P09", name: "Sep 2026", end_date: "2026-09-30" },
      currency: "USD",
      known_at: "2026-09-12T12:00:00Z",
    },
    revenue: {
      current: money("19627.39"),
      prior: money("18000.00"),
      change_ratio: "0.0904",
      trend: [
        { period_key: "FY2026-P08", recognized: money("18000.00") },
        { period_key: "FY2026-P09", recognized: money("19627.39") },
      ],
    },
    contract_liability: { closing: money("60190.69"), opening: money("79818.08") },
    rpo: { total: money("180190.69"), within_12_months: money("149944.11") },
    pending_approvals: { count: 3, oldest_submitted_at: "2026-09-10T09:00:00Z" },
    open_exceptions: { total: 4, blocking: 2, warning: 1, info: 1 },
    close: {
      id: "b3000000-0000-4000-8000-000000000009",
      state: "open",
      blockers: { ...NO_BLOCKERS, approvals_pending: 3, exceptions_open: 2, holds_open: 1 },
      close_run: null,
    },
    revenue_chart: {
      periods: [
        {
          period_key: "FY2026-P08",
          recognized: money("18000.00"),
          scheduled: money("0.00"),
          total: money("18000.00"),
        },
        {
          period_key: "FY2026-P09",
          recognized: money("19627.39"),
          scheduled: money("100.00"),
          total: money("19727.39"),
        },
      ],
      awaiting_trigger: money("0.00"),
      pending_trigger_count: 0,
      totals: {
        recognized: money("37627.39"),
        scheduled: money("100.00"),
        awaiting_trigger: money("0.00"),
        total: money("37727.39"),
      },
    },
  };
}

const ACTIVATION = {
  id: "8b9c0d1e-2f3a-4b4c-8d5e-000000000001",
  request_no: "AR-000020",
  summary: "Contract activation BG-AVM-0020",
  subject: {
    id: "9c0d1e2f-3a4b-4c5d-8e6f-000000000001",
    type: "CONTRACT_ACTIVATION",
    display: "BG-AVM-0020",
    href: null,
    content_sha256: "a".repeat(64),
    row_version: 1,
  },
  amount: money("146000.00"),
  preparer: { id: "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a", kind: "USER", display_name: "Maya Chen" },
  submitted_at: "2026-09-10T09:00:00Z",
  status: "PENDING",
  can_decide: true,
  current_step_no: 1,
  steps: [],
} as unknown as Approval;

const RECENT = {
  id: "0d1e2f3a-4b5c-4d6e-8f7a-000000000001",
  external_id: "SF-ORD-10001",
  customer: {
    id: "1e2f3a4b-5c6d-4e7f-8a8b-000000000001",
    code: "C-01",
    name: "Pellworth Logistics",
  },
  status: "ACTIVE",
} as unknown as ContractListItem;

function legacyPolicy(): Policy {
  return {
    id: "2f3a4b5c-6d7e-4f8a-8b9c-000000000001",
    category: "ACCOUNTING_POLICY",
    scope: "TENANT",
    status: "PUBLISHED",
    preset_code: "LEGACY_PARITY",
  } as unknown as Policy;
}

interface Served {
  readonly dashboardSearches: string[];
  readonly approvalSearches: string[];
}

function serve(
  options: {
    readonly approvals?: readonly Approval[];
    readonly recent?: readonly ContractListItem[];
    readonly legacy?: boolean;
  } = {},
): Served {
  const served: Served = { dashboardSearches: [], approvalSearches: [] };
  const list = (items: readonly unknown[], count?: number) =>
    HttpResponse.json(
      { items, next_cursor: null },
      count === undefined ? {} : { headers: { "X-Erev-Total-Count": String(count) } },
    );
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () => list([])),
    http.get(apiUrl("/api/v1/jobs"), () => list([])),
    http.get(apiUrl("/api/v1/entities"), () => list([ENTITY])),
    http.get(apiUrl("/api/v1/books"), () => list([BOOK])),
    http.get(apiUrl("/api/v1/periods"), () => list([period(8, "open"), period(9, "open")])),
    http.get(apiUrl("/api/v1/currencies"), () =>
      list([
        { code: "USD", name: "US dollar", minor_unit: 2, numeric_code: "840", is_active: true },
      ]),
    ),
    http.get(apiUrl("/api/v1/dashboard/home"), ({ request }) => {
      served.dashboardSearches.push(new URL(request.url).search);
      return HttpResponse.json(home());
    }),
    http.get(apiUrl("/api/v1/approvals"), ({ request }) => {
      served.approvalSearches.push(new URL(request.url).search);
      const items = options.approvals ?? [];
      return list(items, items.length);
    }),
    http.get(apiUrl("/api/v1/exceptions"), () => list([], 0)),
    http.get(apiUrl("/api/v1/audit-events"), () => list([])),
    http.get(apiUrl("/api/v1/contracts"), ({ request }) =>
      new URL(request.url).searchParams.get("quick_list") === "RECENTLY_VIEWED"
        ? list(options.recent ?? [])
        : list([], 12),
    ),
    http.get(apiUrl("/api/v1/saved-views"), () => list([])),
    http.get(apiUrl("/api/v1/policies"), () =>
      list(options.legacy === true ? [legacyPolicy()] : []),
    ),
  );
  return served;
}

/** The screen routes less SF-04 and SF-08:report (RPS-7 and RPS-6), for the XR-14 unlinked case. */
const WITHOUT_REPORT_ROUTES = SCREEN_ROUTES.filter(
  (route) => route.id !== "SF-04" && route.id !== "SF-08:report",
);

describe("SF-01 home", () => {
  it("kpi drill targets", async () => {
    const served = serve({ approvals: [ACTIVATION] });
    renderApp(HOME_ENTRY, { me: PRIYA, screenRoutes: SCREEN_ROUTES });

    expect(await screen.findByRole("heading", { level: 1, name: "Home" })).toBeTruthy();
    const revenue = await screen.findByRole("link", { name: /^Revenue, USD 19,627\.39$/ });
    expect(revenue.getAttribute("href")).toBe(`/schedules?${CONTEXT}`);
    expect(
      screen.getByRole("link", { name: "Contract liability, USD 60,190.69" }).getAttribute("href"),
    ).toBe(`/reports/contract_balance_rollforward?${CONTEXT}`);
    expect(screen.getByRole("link", { name: "RPO, USD 180,190.69" }).getAttribute("href")).toBe(
      `/reports/rpo?${CONTEXT}`,
    );
    expect(screen.getByRole("link", { name: "Pending approvals, 3" }).getAttribute("href")).toBe(
      "/approvals?entity=AVM-US",
    );
    expect(screen.getByRole("link", { name: "Open exceptions, 4" }).getAttribute("href")).toBe(
      "/data/exceptions?entity=AVM-US&f.status=in:OPEN,IN_PROGRESS",
    );
    // SCREENS §2.6 heading, secondary lines and the DS-CH-04 sparkline name.
    const strip = screen.getByRole("region", { name: /^Key figures/ });
    expect(
      within(strip).getByRole("heading", { name: "Key figures (USD, ASC 606, Sep 2026)" }),
    ).toBeTruthy();
    expect(strip.textContent).toContain("Aug 2026: 18,000.00 · change +9.0%");
    expect(strip.textContent).toContain("Opening 79,818.08");
    expect(strip.textContent).toContain("Within 12 months 149,944.11");
    expect(strip.textContent).toContain("Oldest submitted 10 Sep 2026");
    expect(strip.textContent).toContain("2 blocking");
    expect(
      within(screen.getByTestId("SF-01-chart-revenue-trend")).getByRole("img", {
        name: /^Recognized revenue, Aug 2026 to Sep 2026/,
      }),
    ).toBeTruthy();
    expect(served.dashboardSearches).toContain(`?${CONTEXT}`);
    // Waiting for you: oldest first, no entity filter (L7-2-Q-22).
    const approvals = await screen.findByRole("table", { name: "Waiting for you" });
    expect(
      within(approvals).getByRole("link", { name: "Contract activation BG-AVM-0020" }),
    ).toBeTruthy();
    expect(approvals.textContent).toContain("146,000.00");
    expect(
      served.approvalSearches.some(
        (search) =>
          search.includes("assigned_to_me=true") &&
          search.includes("sort=submitted_at") &&
          search.includes("limit=8") &&
          !search.includes("entity="),
      ),
    ).toBe(true);
    // Close status: the non-zero blocker rows and the cockpit link.
    const close = screen.getByRole("region", { name: "Close status" });
    expect(close.textContent).toContain("Period open");
    expect(close.textContent).toContain("Pending approvals3");
    expect(close.textContent).toContain("Open holds1");
    // SCREENS §2.6 rev 1.37 (04 §16.13 rev 1.206; ruling R-121 (i)): the close row counts the items
    // that hold the lock of the context period — not every open exception, which is the key figure
    // above — so it says so, and it alone of the rows opens the list it counts: the queue under
    // `blocking` with `close.id`.
    expect(close.textContent).toContain("Exceptions holding the lock2");
    expect(close.textContent).not.toContain("Open exceptions");
    expect(
      within(close).getByRole("link", { name: "Exceptions holding the lock" }).getAttribute("href"),
    ).toBe("/data/exceptions?blocking=b3000000-0000-4000-8000-000000000009");
    expect(
      within(close).queryByRole("link", { name: /^(Pending approvals|Open holds)/ }),
    ).toBeNull();
    expect(
      within(close).getByRole("link", { name: "Open close cockpit" }).getAttribute("href"),
    ).toBe("/close/AVM-US/ASC606/FY2026-P09");
    expect(screen.getByRole("figure", { name: "Revenue by period" })).toBeTruthy();
    cleanup();

    // Without the SF-04 and SF-08:report routes the three money figures do not link (XR-14).
    serve({ approvals: [ACTIVATION] });
    renderApp(HOME_ENTRY, { me: PRIYA, screenRoutes: WITHOUT_REPORT_ROUTES });
    expect(await screen.findByRole("link", { name: "Pending approvals, 3" })).toBeTruthy();
    expect(screen.getByTestId("SF-01-kpi-revenue").tagName).toBe("SPAN");
    expect(screen.queryByRole("link", { name: /^Revenue, USD/ })).toBeNull();
    expect(screen.queryByRole("link", { name: /^RPO, USD/ })).toBeNull();
  });

  it("viewer empty approvals", async () => {
    const served = serve({ recent: [RECENT] });
    renderApp(HOME_ENTRY, { me: ROBERT, screenRoutes: SCREEN_ROUTES });

    expect(
      await screen.findByRole("heading", { name: "You have no approval permissions" }),
    ).toBeTruthy();
    expect(screen.getByText("Items you can view appear in reports and registers.")).toBeTruthy();
    const viewed = screen.getByTestId("SF-01-pane-recently-viewed");
    expect(within(viewed).getByRole("heading", { level: 2, name: "Recently viewed" })).toBeTruthy();
    const contract = await within(viewed).findByRole("link", { name: "SF-ORD-10001" });
    expect(contract.getAttribute("href")).toBe(
      "/contracts/0d1e2f3a-4b5c-4d6e-8f7a-000000000001/obligations",
    );
    expect(viewed.textContent).toContain("Pellworth Logistics");
    expect(screen.queryByTestId("SF-01-pane-activity")).toBeNull();
    expect(screen.queryByRole("table", { name: "Waiting for you" })).toBeNull();
    expect(served.approvalSearches.filter((search) => search.includes("limit=8"))).toEqual([]);
  });

  it("the legacy panel's dismissal is the workspace's: a sandbox copy of one membership id keeps its own", async () => {
    // A sandbox copy keeps the ids of the rows it copies (SCREENS_B §9.7 "The open workspace"):
    // the source's dismissal is not the copy's, and the copy's is stored under the copy.
    const source = PRIYA.memberships[0];
    if (source === undefined) {
      throw new Error("no membership");
    }
    const COPY_ID = "1c1c1c1c-1c1c-4c1c-8c1c-1c1c1c1c1c1c";
    const me = {
      ...PRIYA,
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
            source_tenant_id: TENANT_ID,
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
    window.localStorage.setItem(`erev.dismissed.legacy-panel.${TENANT_ID}`, "1");
    serve({ legacy: true });
    renderApp(HOME_ENTRY, { me, session: inCopy, screenRoutes: SCREEN_ROUTES });

    const banner = await screen.findByTestId("SF-01-banner-legacy");
    fireEvent.click(within(banner).getByRole("button", { name: /^Dismiss/ }));
    await waitFor(() => {
      expect(screen.queryByTestId("SF-01-banner-legacy")).toBeNull();
    });
    expect(window.localStorage.getItem(`erev.dismissed.legacy-panel.${COPY_ID}`)).toBe("1");
    window.localStorage.clear();
  });

  it("legacy panel in preset tenant", async () => {
    serve({ legacy: true });
    renderApp(HOME_ENTRY, { me: PRIYA, screenRoutes: SCREEN_ROUTES });

    expect(await screen.findByRole("heading", { name: "Coming from eRev desktop" })).toBeTruthy();
    const banner = screen.getByTestId("SF-01-banner-legacy");
    expect(banner.textContent).toContain(
      "Your workspace uses the legacy-parity preset. See where each desktop button lives now, or download the four legacy templates.",
    );
    expect(
      within(banner).getByRole("link", { name: "Download legacy templates" }).getAttribute("href"),
    ).toBe("/data/templates?f.family=is:LEGACY_V1");
    // SF-26 is not built, so the transition map action is absent (XR-14; L7-2-Q-25).
    expect(within(banner).queryByRole("link", { name: "Open the transition map" })).toBeNull();

    fireEvent.click(within(banner).getByRole("button", { name: /^Dismiss/ }));
    await waitFor(() => {
      expect(screen.queryByTestId("SF-01-banner-legacy")).toBeNull();
    });
    expect(window.localStorage.getItem(`erev.dismissed.legacy-panel.${TENANT_ID}`)).not.toBeNull();
    cleanup();

    // A workspace without the preset shows no panel.
    serve({ legacy: false });
    renderApp(HOME_ENTRY, { me: PRIYA, screenRoutes: SCREEN_ROUTES });
    expect(await screen.findByRole("link", { name: "Pending approvals, 3" })).toBeTruthy();
    expect(screen.queryByTestId("SF-01-banner-legacy")).toBeNull();
  });
});

// SCREENS §0.6 SCR-PERM-02 and §2.1 (rev 1.34; item W-12, slice b; supervisor ruling R-28): a permission
// is held for entities. The figures and the exceptions queue ask for the context entity; "Recent
// activity" reads a list of the whole workspace and asks for all entities; and a read the API refuses
// gives the variant of a member without the permission, not an error with "Retry".
describe("SF-01 home: for which entities a permission is held", () => {
  const AVM_DE_ID = "0a1b2c3d-4e5f-4a6b-8c7d-000000000003";
  const REVIEWER = ["contract.read", "config.read", "contract.approve", "audit.read"];

  /** Records the reads of the audit events and of the exceptions queue; `refuse` answers the first with 403. */
  function watch(refuse = false): { readonly audit: string[]; readonly exceptions: string[] } {
    const reads = { audit: [] as string[], exceptions: [] as string[] };
    server.use(
      http.get(apiUrl("/api/v1/audit-events"), ({ request }) => {
        reads.audit.push(new URL(request.url).search);
        return refuse
          ? problemResponse("forbidden", 403, "Permission denied")
          : HttpResponse.json({
              items: [
                {
                  id: "4b3a2c1d-0e9f-4a8b-9c7d-000000000001",
                  action: "contract.book",
                  object_type: "contract",
                  object_id: "0d1e2f3a-4b5c-4d6e-8f7a-000000000001",
                  actor: { id: "a1", display_name: "Maya Chen", kind: "USER" },
                  occurred_at: "2026-09-10T08:30:00Z",
                  outcome: "SUCCESS",
                },
              ],
              next_cursor: null,
            });
      }),
      http.get(apiUrl("/api/v1/exceptions"), ({ request }) => {
        reads.exceptions.push(new URL(request.url).search);
        return HttpResponse.json(
          { items: [], next_cursor: null },
          { headers: { "X-Erev-Total-Count": "0" } },
        );
      }),
    );
    return reads;
  }

  it("a reviewer of all entities reads recent activity", async () => {
    serve();
    const reads = watch();
    renderApp(HOME_ENTRY, {
      me: signedInMe({ permissions: REVIEWER }),
      screenRoutes: SCREEN_ROUTES,
    });

    const activity = await screen.findByTestId("SF-01-pane-activity");
    expect(await within(activity).findByText(/Maya Chen/)).toBeTruthy();
    expect(reads.audit).toHaveLength(1);
    expect(screen.queryByTestId("SF-01-pane-recently-viewed")).toBeNull();
  });

  it("a reviewer of the context entity alone reads its figures and the Recently viewed variant, and no audit event", async () => {
    const served = serve({ recent: [RECENT] });
    const reads = watch();
    renderApp(HOME_ENTRY, {
      me: signedInMe({
        permissions: REVIEWER,
        permission_scopes: Object.fromEntries(REVIEWER.map((code) => [code, [AVM_US.id]])),
      }),
      screenRoutes: SCREEN_ROUTES,
    });

    // The context entity is hers: the figures and the exceptions queue are read.
    expect(await screen.findByRole("link", { name: /^Revenue, USD 19,627\.39$/ })).toBeTruthy();
    expect(served.dashboardSearches).toHaveLength(1);
    expect(await screen.findByRole("heading", { name: /^Open exceptions/ })).toBeTruthy();
    await waitFor(() => {
      expect(reads.exceptions).toHaveLength(1);
    });
    // `audit.read` for one entity does not read the audit events of the workspace.
    const viewed = await screen.findByTestId("SF-01-pane-recently-viewed");
    expect(await within(viewed).findByRole("link", { name: "SF-ORD-10001" })).toBeTruthy();
    expect(screen.queryByTestId("SF-01-pane-activity")).toBeNull();
    expect(reads.audit).toEqual([]);
  });

  it("a reviewer of another entity reads no figures and no exceptions of the context entity", async () => {
    const served = serve({ recent: [RECENT] });
    const reads = watch();
    renderApp(HOME_ENTRY, {
      me: signedInMe({
        permissions: REVIEWER,
        permission_scopes: {
          "contract.read": [AVM_DE_ID],
          "contract.approve": [AVM_DE_ID],
          "audit.read": [AVM_DE_ID],
          "config.read": "*",
        },
      }),
      screenRoutes: SCREEN_ROUTES,
    });

    // Her approvals queue and the variant render at once. Until the context is resolved the figures
    // and the exceptions queue are regions of "some entity"; once it is AVM-US they are not hers.
    expect(await screen.findByTestId("SF-01-pane-recently-viewed")).toBeTruthy();
    expect(await screen.findByRole("heading", { name: "Waiting for you" })).toBeTruthy();
    await waitFor(() => {
      expect(screen.queryByRole("region", { name: /^Key figures/ })).toBeNull();
      expect(screen.queryByRole("heading", { name: /^Open exceptions/ })).toBeNull();
    });
    expect(screen.queryByTestId("SF-01-pane-close")).toBeNull();
    // Neither was read: each read waits for the context, and the context took the region away.
    expect(served.dashboardSearches).toEqual([]);
    expect(reads.exceptions).toEqual([]);
  });

  it("a read of the audit events that is refused gives the Recently viewed variant: no error, no second request", async () => {
    serve({ recent: [RECENT] });
    const reads = watch(true);
    const { queryClient } = renderApp(HOME_ENTRY, {
      me: signedInMe({ permissions: REVIEWER }),
      screenRoutes: SCREEN_ROUTES,
    });

    const viewed = await screen.findByTestId("SF-01-pane-recently-viewed");
    expect(await within(viewed).findByRole("link", { name: "SF-ORD-10001" })).toBeTruthy();
    expect(screen.queryByTestId("SF-01-pane-activity")).toBeNull();
    expect(screen.queryByText("Could not load recent activity")).toBeNull();
    expect(screen.queryByText("Permission denied")).toBeNull();
    // A refusal is not repaired by asking again: the read has settled as answered, so the query's
    // retry never sends it a second time.
    const settled = queryClient
      .getQueryCache()
      .findAll({ predicate: (query) => JSON.stringify(query.queryKey).includes('"home-recent"') })
      .filter((query) => query.state.dataUpdateCount > 0 || query.state.errorUpdateCount > 0)
      .map((query) => [query.state.status, query.state.data, query.state.fetchFailureCount]);
    expect(settled).toEqual([["success", null, 0]]);
    expect(reads.audit).toHaveLength(1);
  });
});

// KIT-FILTER-LEAVING-2 (dev-guide DG-FE-03 rule (3), rev 1.230): Home writes its resolved context with
// its own path. When the read that resolves it answered while the member was on the way to another
// page, the write took them back to Home.
describe("SF-01 home: the context written for a page that is leaving", () => {
  it("is not written while a navigation to another page is on its way, and the member arrives", async () => {
    serve();
    let answer: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      answer = resolve;
    });
    let asked = 0;
    let answered = false;
    server.use(
      http.get(apiUrl("/api/v1/periods"), async () => {
        asked += 1;
        await held;
        answered = true;
        return HttpResponse.json({
          items: [period(8, "open"), period(9, "open")],
          next_cursor: null,
        });
      }),
    );
    let arrive: () => void = () => undefined;
    const fetched = new Promise<void>((resolve) => {
      arrive = resolve;
    });
    const slow = {
      id: "X:slow",
      path: "/slow",
      handle: { sf: "X", screen: "X:slow", titleKey: "contracts.list.title" },
      lazy: async () => {
        await fetched;
        return { Component: () => <h1 tabIndex={-1}>The next page</h1> };
      },
    };
    const { router } = renderApp("/home", { me: PRIYA, screenRoutes: [...SCREEN_ROUTES, slow] });
    await waitFor(() => expect(asked).toBeGreaterThan(0));
    void router.navigate("/slow");
    await waitFor(() => expect(router.state.navigation.state).toBe("loading"));

    answer();
    await waitFor(() => expect(answered).toBe(true));
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(router.state.navigation.location?.pathname).toBe("/slow");
    expect(router.state.location.search).toBe("");

    arrive();
    expect(await screen.findByRole("heading", { level: 1, name: "The next page" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/slow");
  });

  it("is written once Home is the page that stays", async () => {
    serve();
    const { router } = renderApp("/home", { me: PRIYA, screenRoutes: SCREEN_ROUTES });
    await waitFor(() =>
      expect(router.state.location.search).toBe("?entity=AVM-US&period=FY2026-P08&book=ASC606"),
    );
  });
});
