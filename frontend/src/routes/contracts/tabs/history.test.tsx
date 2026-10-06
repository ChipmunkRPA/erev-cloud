// @vitest-environment jsdom
// SF-03:history History tab (BUILD_SPEC CTR-24; SCREENS §4.7; DESIGN_SYSTEM DS-CMP-12, DS-CMP-16,
// DS-CMP-31, DS-FMT-31; D-12; 04 API-R-28 history, versions and compare, API-R-10 audit events): the
// view switch in the URL; the activity timeline with its filters and paging; the versions grid, whose
// two selected rows compare as a field diff grouped by obligation, without signed positions and without
// a difference the API does not answer (ruling R-93 (c)); the audit trail, offered only with `audit.read`.
import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../../app/router";
import type { ContractHistoryItem } from "../../../lib/api/queries/contracts";
import { installMemoryStorage, preloadScreens, renderApp, signedInMe } from "../../../test/app";
import {
  CONTEXT,
  CONTRACT_ID,
  MAYA_USER,
  money,
  PRIYA_USER,
  serveWorkbench,
  SYSTEM_ACTOR,
} from "../../../test/workbench";
import { installGridViewport } from "../../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import { activityVerb, auditVerb, compareGroups, historyViewOf } from "./history";

installMswServer();
installMemoryStorage();
installGridViewport();
configure({ asyncUtilTimeout: 5000 });

beforeAll(async () => {
  await preloadScreens(SCREEN_ROUTES, ["SF-03:history"]);
});

afterEach(() => {
  cleanup();
});

const READER = ["contract.read", "config.read"];
const MAYA = signedInMe({ permissions: [...READER, "contract.create", "audit.read"] });
const ROBERT = signedInMe({ permissions: READER });
const REQUEST_ID = "01a0f3bd-1bc7-7531-946f-dcee7ce93462";
const BASE = `/api/v1/contracts/${CONTRACT_ID}`;

function historyItem(
  kind: ContractHistoryItem["kind"],
  occurredAt: string,
  actor: ContractHistoryItem["actor"],
  summaryKey: string,
  params: ContractHistoryItem["params"],
  links: ContractHistoryItem["links"] = {},
): ContractHistoryItem {
  return { kind, occurred_at: occurredAt, actor, summary_key: summaryKey, params, links };
}

// 04 API-S-ContractHistoryItem rev 1.143: a computation is SYSTEM's whether a person's command or a
// job ran it, so the route answers it with `include_system=true` only.
const COMPUTATION = historyItem(
  "CALCULATION",
  "2026-09-16T11:00:03Z",
  SYSTEM_ACTOR,
  "contract_computation.SUCCEEDED",
  { status: "SUCCEEDED", trigger: "COMMAND", engine_version: "1.0.0" },
  { versions: `${BASE}/versions` },
);
const ACTIVITY = [
  historyItem(
    "EVENT",
    "2026-09-16T11:00:02Z",
    MAYA_USER,
    "contract_event.RETURN_RECORDED",
    {
      event_type: "RETURN_RECORDED",
      stream_version: 6,
      effective_date: "2026-09-15",
      origin: "UI",
    },
    { event: `${BASE}/events/0e0e0e0e-0e0e-4e0e-8e0e-0e0e0e0e0e0e` },
  ),
  historyItem(
    "APPROVAL",
    "2026-01-02T10:00:00Z",
    PRIYA_USER,
    "approval_decision.APPROVE",
    { decision: "APPROVE", subject_type: "CONTRACT_ACTIVATION", request_no: "APR-000065" },
    { approval: `/api/v1/approvals/${REQUEST_ID}` },
  ),
];
const OLDER = [
  historyItem("EVENT", "2026-01-01T09:00:00Z", MAYA_USER, "contract_event.CONTRACT_BOOKED", {
    event_type: "CONTRACT_BOOKED",
    stream_version: 1,
    effective_date: "2026-01-01",
    origin: "UI",
  }),
];
const SYSTEM_EVENT = historyItem(
  "EVENT",
  "2026-01-02T10:00:01Z",
  SYSTEM_ACTOR,
  "contract_event.CONTRACT_ACTIVATED",
  { event_type: "CONTRACT_ACTIVATED", stream_version: 4, effective_date: "2026-01-01" },
);

function version(no: number, overrides: Readonly<Record<string, unknown>> = {}) {
  return {
    id: `0000000${String(no)}-aaaa-4aaa-8aaa-aaaaaaaaaaaa`,
    version_no: no,
    book: "ASC606",
    known_at: `2026-09-1${String(no)}T12:00:00Z`,
    engine_version: "1.0.0",
    input_sha256: "a".repeat(64),
    output_sha256: "b".repeat(64),
    modification_boundary_no: 0,
    pinned_policies: {},
    pinned_refs: {},
    status_in_book: "ACTIVE",
    status_reason_in_book: null,
    total_ssp: "240000",
    cause_events: [
      {
        id: `1111111${String(no)}-bbbb-4bbb-8bbb-bbbbbbbbbbbb`,
        event_type: "BILLING_RECORDED",
        effective_date: "2026-01-01",
        recorded_at: "2026-09-12T11:00:00Z",
      },
    ],
    transaction_price_buildup: Object.fromEntries(
      [
        "fixed",
        "vc_constrained",
        "vc_excluded",
        "expected_returns",
        "consideration_payable",
        "financing_adjustment",
        "noncash",
        "sales_tax_excluded",
        "out_of_scope",
        "total",
      ].map((name) => [name, money(name === "fixed" || name === "total" ? "240000.00" : "0.00")]),
    ),
    revenue_to_date: money("89753.42"),
    billed_to_date: money("120000.00"),
    scheduled: money("150246.58"),
    awaiting_trigger: money("0.00"),
    rpo: money("150246.58"),
    ...overrides,
  };
}

const VERSIONS = [
  version(5, {
    transaction_price_buildup: {
      ...version(5).transaction_price_buildup,
      total: money("300000.00"),
    },
  }),
  version(4, { cause_events: [] }),
  version(3, { status_in_book: "DRAFT" }),
];

/** SCREENS §4.7 sample world: K-02 before and after J-05 (PRD rev 1.21). */
const COMPARE = {
  book: "ASC606",
  from_version: { id: VERSIONS[2]?.id, version_no: 3, known_at: "2026-09-13T12:00:00Z" },
  to_version: { id: VERSIONS[0]?.id, version_no: 5, known_at: "2026-09-15T12:00:00Z" },
  changes: [
    { field: "status_in_book", obligation_key: null, before: "DRAFT", after: "ACTIVE" },
    { field: "transaction_price", obligation_key: null, before: "240000.00", after: "300000.00" },
    { field: "net_position", obligation_key: null, before: "0.00", after: "119671.23" },
    { field: "obligation", obligation_key: "O2", before: null, after: "O2" },
    {
      field: "remaining_allocation",
      obligation_key: "O1",
      before: "155178.08",
      after: "148451.55",
    },
    { field: "end_date", obligation_key: "O1", before: "2027-12-31", after: "2028-06-30" },
    { field: "progress_ratio", obligation_key: "O1", before: "0", after: "0.3125" },
    {
      field: "satisfaction_status",
      obligation_key: "O1",
      before: "UNSATISFIED",
      after: "PARTIALLY_SATISFIED",
    },
    { field: "position_obligation", obligation_key: "O1", before: "0.00", after: "119671.23" },
    { field: "product_id", obligation_key: "O1", before: "x", after: "y" },
  ],
};

const AUDIT = [
  {
    id: "2a2a2a2a-2a2a-4a2a-8a2a-2a2a2a2a2a2a",
    chain_seq: 412,
    occurred_at: "2026-09-16T11:00:02Z",
    action: "contract.record_events",
    outcome: "SUCCESS",
    object_type: "contract",
    object_id: CONTRACT_ID,
    object_version: "6",
    actor: MAYA_USER,
    actor_roles: ["revenue_accountant"],
    comment: "Return of 2 units on O1",
    reason_code: null,
    detail: {},
    diff: null,
    before: null,
    after: null,
    hmac: "c".repeat(64),
    hmac_key_id: "k1",
    prev_hmac: "d".repeat(64),
    request_id: "0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d",
    source_ip: null,
    auth_method: "password",
    mfa_verified: true,
    api_client_id: null,
    approval_request_id: null,
    on_behalf_of_id: null,
    on_behalf_of: null,
    support_grant_id: null,
  },
];
const VERIFICATION = {
  id: "3b3b3b3b-3b3b-4b3b-8b3b-3b3b3b3b3b3b",
  trigger: "SCHEDULED",
  result: "PASS",
  started_at: "2026-09-07T14:04:00Z",
  finished_at: "2026-09-07T14:05:00Z",
  from_chain_seq: 1,
  to_chain_seq: 400,
  events_checked: 400,
  first_failure_seq: null,
  failure_detail: null,
  digest_file_id: null,
  digest_last_hmac: null,
  job_id: null,
};

interface Reads {
  readonly history: string[];
  readonly compare: string[];
  readonly audit: string[];
}

function serve(): Reads {
  const reads: Reads = { history: [], compare: [], audit: [] };
  serveWorkbench();
  server.use(
    http.get(apiUrl(`${BASE}/history`), ({ request }) => {
      const url = new URL(request.url);
      reads.history.push(url.search);
      const kinds = url.searchParams.getAll("kind");
      if (url.searchParams.get("cursor") === "older") {
        return HttpResponse.json({ items: OLDER, next_cursor: null });
      }
      const system = url.searchParams.get("include_system") === "true";
      const items = [
        ...(system ? [COMPUTATION] : []),
        ...ACTIVITY,
        ...(system ? [SYSTEM_EVENT] : []),
      ].filter((item) => kinds.length === 0 || kinds.includes(item.kind));
      return HttpResponse.json({ items, next_cursor: kinds.length === 0 ? "older" : null });
    }),
    http.get(apiUrl(`${BASE}/versions/compare`), ({ request }) => {
      reads.compare.push(new URL(request.url).search);
      return HttpResponse.json(COMPARE);
    }),
    http.get(apiUrl(`${BASE}/versions`), () =>
      HttpResponse.json(
        { items: VERSIONS, next_cursor: null },
        { headers: { "X-Erev-Total-Count": "3" } },
      ),
    ),
    http.get(apiUrl("/api/v1/audit-events/verifications"), () =>
      HttpResponse.json({ items: [VERIFICATION], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/audit-events"), ({ request }) => {
      reads.audit.push(new URL(request.url).search);
      return HttpResponse.json({ items: AUDIT, next_cursor: null });
    }),
  );
  return reads;
}

function open(view: string | null, me = MAYA) {
  const search = view === null ? CONTEXT : `${CONTEXT}&view=${view}`;
  return renderApp(`/contracts/${CONTRACT_ID}/history?${search}`, {
    me,
    screenRoutes: SCREEN_ROUTES,
  });
}

/** The text of `element` without the parts matching `selector`. */
function textWithout(element: Element | null, selector: string): string {
  const shown = element?.cloneNode(true) as HTMLElement | undefined;
  for (const hidden of shown?.querySelectorAll(selector) ?? []) {
    hidden.remove();
  }
  return (shown?.textContent ?? "").replace(/\s+/g, " ").trim();
}

/** The text of each timeline item as read: actor, phrase and the linked object (not the avatar). */
function activityTexts(): string[] {
  return within(screen.getByRole("list", { name: "Activity" }))
    .getAllByRole("listitem")
    .map((item) => textWithout(item.querySelector("p"), "[aria-hidden='true']"));
}

describe("SF-03:history activity", () => {
  it("shows events, calculations and approvals with their filters and older pages", async () => {
    const reads = serve();
    const { router } = open(null);

    const group = await screen.findByRole("radiogroup", { name: "History view" });
    expect(
      within(group)
        .getAllByRole("radio")
        .map((radio) => `${radio.textContent ?? ""}:${radio.getAttribute("aria-checked") ?? ""}`),
    ).toEqual(["Activity:true", "Versions:false", "Audit trail:false"]);
    expect(screen.getByRole("heading", { level: 2, name: "History" })).toBeTruthy();
    await screen.findByRole("list", { name: "Activity" });
    // What people did: a computation is the system's and is not among it.
    expect(activityTexts()).toEqual([
      "Maya Chen recorded a return, effective 15 Sep 2026",
      "Priya Raman approved the Contract activation request APR-000065",
    ]);
    // The decision links to its request (SF-12:request), not to a raw id.
    expect(screen.getByRole("link", { name: "APR-000065" }).getAttribute("href")).toBe(
      `/approvals/requests/${REQUEST_ID}`,
    );
    // Each item carries its instant in UTC with seconds (DS-FMT-17).
    expect(screen.getByText("16 Sep 2026 11:00:02 UTC")).toBeTruthy();
    expect(reads.history[0]).not.toContain("include_system");

    fireEvent.click(screen.getByRole("button", { name: "Load older activity" }));
    await waitFor(() => expect(activityTexts()).toHaveLength(3));
    expect(activityTexts()[2]).toBe("Maya Chen booked the contract, effective 01 Jan 2026");
    expect(screen.queryByRole("button", { name: "Load older activity" })).toBeNull();

    // No chip "Imports" until the history route answers IMPORT items (ruling R-93 (b)).
    expect(
      within(screen.getByRole("radiogroup", { name: "Activity type" }))
        .getAllByRole("radio")
        .map((radio) => radio.textContent),
    ).toEqual(["All", "Changes", "Approvals", "Calculations"]);
    // "Approvals" reads kind=APPROVAL; "Show system events" reads include_system=true.
    fireEvent.click(
      within(screen.getByRole("radiogroup", { name: "Activity type" })).getByRole("radio", {
        name: "Approvals",
      }),
    );
    await waitFor(() => expect(activityTexts()).toHaveLength(1));
    expect(reads.history.at(-1)).toContain("kind=APPROVAL");
    fireEvent.click(
      within(screen.getByRole("radiogroup", { name: "Activity type" })).getByRole("radio", {
        name: "All",
      }),
    );
    fireEvent.click(screen.getByRole("switch", { name: "Show system events" }));
    await waitFor(() =>
      expect(activityTexts()).toContain("System activated the contract, effective 01 Jan 2026"),
    );
    expect(activityTexts()).toContain("System computed the contract (engine 1.0.0)");
    expect(reads.history.at(-1)).toContain("include_system=true");

    // The view switch writes `view` and keeps the context parameters.
    fireEvent.click(within(group).getByRole("radio", { name: "Versions" }));
    await waitFor(() => expect(router.state.location.search).toBe(`?${CONTEXT}&view=versions`));
  });

  // SCREENS §4.7 rev 1.39 (item HIST-CALC-CHIP-1): every computation is the system's (04 rev 1.143),
  // so a chip that read `kind=CALCULATION` alone listed nothing until the switch was on.
  it("the chip Calculations lists the computations, which are the system's, whatever the switch says", async () => {
    const reads = serve();
    open(null);

    await screen.findByRole("list", { name: "Activity" });
    const chips = within(screen.getByRole("radiogroup", { name: "Activity type" }));
    const toggle = screen.getByRole("switch", { name: "Show system events" });
    expect(toggle.getAttribute("aria-checked")).toBe("false");

    fireEvent.click(chips.getByRole("radio", { name: "Calculations" }));
    await waitFor(() =>
      expect(activityTexts()).toEqual(["System computed the contract (engine 1.0.0)"]),
    );
    const read = new URLSearchParams(reads.history.at(-1));
    expect(read.getAll("kind")).toEqual(["CALCULATION"]);
    expect(read.get("include_system")).toBe("true");
    // The switch is the member's own choice: the chip does not move it.
    expect(toggle.getAttribute("aria-checked")).toBe("false");

    // Another chip reads as the switch says again.
    fireEvent.click(chips.getByRole("radio", { name: "Changes" }));
    await waitFor(() =>
      expect(activityTexts()).toEqual(["Maya Chen recorded a return, effective 15 Sep 2026"]),
    );
    expect(reads.history.at(-1)).toContain("kind=EVENT");
    expect(reads.history.at(-1)).not.toContain("include_system");
  });

  it("names an event type the catalogue does not know as a change", () => {
    expect(
      activityVerb(
        historyItem("EVENT", "2026-09-16T11:00:02Z", MAYA_USER, "contract_event.SOMETHING_NEW", {
          event_type: "SOMETHING_NEW",
          effective_date: "not a date",
        }),
      ),
    ).toBe("recorded a change");
    expect(
      activityVerb(
        historyItem("APPROVAL", "2026-09-16T11:00:02Z", PRIYA_USER, "approval_decision.REJECT", {
          decision: "REJECT",
          subject_type: "MODIFICATION",
          request_no: "APR-000070",
        }),
      ),
    ).toBe("rejected the Modification request APR-000070");
  });
});

describe("SF-03:history versions", () => {
  it("compares two selected versions as a field diff grouped by obligation", async () => {
    const reads = serve();
    open("versions");

    const section = await screen.findByTestId("SF-03-grid-versions");
    const grid = await within(section).findByRole("grid", { name: "Contract versions" });
    await within(grid).findByRole("checkbox", { name: "Select version 5" });
    const rows = within(grid)
      .getAllByRole("row")
      .slice(1)
      .map((row) =>
        Array.from(row.querySelectorAll("[role='gridcell']"), (cell) =>
          textWithout(cell, ".sr-only"),
        ).slice(1),
      );
    expect(rows).toEqual([
      [
        "5",
        "15 Sep 2026 12:00 UTC",
        "Invoice recorded, effective 01 Jan 2026",
        "1.0.0",
        "300,000.00",
        "89,753.42",
        "Active",
      ],
      ["4", "14 Sep 2026 12:00 UTC", "—", "1.0.0", "240,000.00", "89,753.42", "Active"],
      [
        "3",
        "13 Sep 2026 12:00 UTC",
        "Invoice recorded, effective 01 Jan 2026",
        "1.0.0",
        "240,000.00",
        "89,753.42",
        "Draft",
      ],
    ]);

    // Fewer than two selected: the button is unavailable and states why (SCR-PERM-03).
    const compare = within(section).getByRole("button", { name: "Compare versions" });
    expect(compare.getAttribute("aria-disabled")).toBe("true");
    // The reason is a visible line that also describes the grid.
    const reason = document.getElementById(grid.getAttribute("aria-describedby") ?? "");
    expect(reason?.textContent).toBe("Select two versions to compare.");
    expect(reason?.classList.contains("sr-only")).toBe(false);
    fireEvent.click(within(grid).getByRole("checkbox", { name: "Select version 5" }));
    expect(
      within(section)
        .getByRole("button", { name: "Compare versions" })
        .getAttribute("aria-disabled"),
    ).toBe("true");
    fireEvent.click(within(grid).getByRole("checkbox", { name: "Select version 3" }));
    const ready = within(section).getByRole("button", { name: "Compare versions" });
    expect(ready.hasAttribute("aria-disabled")).toBe(false);
    fireEvent.click(ready);

    const table = await screen.findByRole("table", { name: "Changes from version 3 to version 5" });
    expect(table.getAttribute("data-testid")).toBe("SF-03-diff");
    // The earlier version is `from`, whatever the order of selection.
    expect(new URLSearchParams(reads.compare[0]).get("from")).toBe("3");
    expect(new URLSearchParams(reads.compare[0]).get("to")).toBe("5");
    expect(new URLSearchParams(reads.compare[0]).get("book")).toBe("ASC606");
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["Change", "Field", "Version 3", "Version 5"]);
    const lines = within(table)
      .getAllByRole("row")
      .slice(1)
      .map((row) =>
        Array.from(row.querySelectorAll("th, td"), (cell) => textWithout(cell, ".sr-only")),
      );
    expect(lines).toEqual([
      ["Contract"],
      ["~", "Status in book", "Draft", "Active"],
      ["~", "Transaction price", "240,000.00", "300,000.00"],
      ["Obligation O1"],
      // SCREENS §4.7: O1 remaining allocation 155,178.08 → 148,451.55. No Delta column: the compare
      // route answers no difference and the browser computes none (DG-FE-08; ruling R-93 (c)).
      ["~", "Remaining allocation", "155,178.08", "148,451.55"],
      ["~", "End date", "31 Dec 2027", "30 Jun 2028"],
      ["~", "Progress", "0.0%", "31.3%"],
      ["~", "Satisfaction status", "Not satisfied", "Partially satisfied"],
      ["Obligation O2"],
      ["+", "Obligation", "—", "O2"],
    ]);
    expect(table.textContent).not.toContain("6,726.53");
    expect(table.textContent).not.toContain("60,000.00");
    // Markers carry a spoken prefix, so the tint is never the only signal (DS-CMP-16).
    expect(within(table).getAllByText("Changed:").length).toBe(6);
    expect(within(table).getByText("Added:")).toBeTruthy();
    // D-12: signed positions never render; internal fields are counted, not listed.
    expect(table.textContent).not.toContain("119,671.23");
    expect(screen.getByText("3 changes in internal fields are not listed.")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Close comparison" }));
    expect(screen.queryByTestId("SF-03-diff")).toBeNull();
  });

  it("compareGroups lists the contract first and leaves unknown columns out", () => {
    const compared = compareGroups(
      [
        { field: "allocated_amount", obligation_key: "O2", before: "10.00", after: "12.50" },
        { field: "contract_computation_id", obligation_key: null, before: "a", after: "b" },
        { field: "scope_flag", obligation_key: "O1", before: "IN_SCOPE_606", after: "LEASE_842" },
        { field: "hold_types", obligation_key: "O1", before: [], after: ["recognition"] },
        { field: "revenue_cum", obligation_key: null, before: "0.00", after: "328.77" },
      ],
      "USD",
    );
    expect(compared.omitted).toBe(1);
    expect(compared.groups.map((group) => group.obligationKey)).toEqual([null, "O1", "O2"]);
    expect(compared.groups[1]?.rows).toEqual([
      {
        id: "O1:scope_flag",
        label: "Scope",
        change: "changed",
        before: "In scope (ASC 606)",
        after: "Lease (ASC 842)",
      },
      {
        id: "O1:hold_types",
        label: "Holds",
        change: "added",
        before: null,
        after: "Recognition hold",
      },
    ]);
    expect(compared.groups[2]?.rows).toEqual([
      {
        id: "O2:allocated_amount",
        label: "Allocated amount",
        change: "changed",
        before: "10.00",
        after: "12.50",
      },
    ]);
  });
});

describe("SF-03:history audit trail", () => {
  it("shows the audit events of the contract under the latest chain verification", async () => {
    const reads = serve();
    open("audit");

    expect(await screen.findByText("Audit chain verified 07 Sep 2026 14:05 UTC")).toBeTruthy();
    await screen.findByRole("list", { name: "Activity" });
    expect(activityTexts()).toEqual(["Maya Chen recorded events"]);
    expect(screen.getByText("Return of 2 units on O1")).toBeTruthy();
    const params = new URLSearchParams(reads.audit[0]);
    expect(params.get("object_type")).toBe("contract");
    expect(params.get("object_id")).toBe(CONTRACT_ID);
  });

  // SCREENS §4.7 rev 1.39 (item HIST-CALC-CHIP-1): what the system wrote for a principal names both
  // (04 API-S-AuditEvent `on_behalf_of`; the computation of a person's command, 05 TXN-10).
  it("names the principal an event was written for", async () => {
    serve();
    server.use(
      http.get(apiUrl("/api/v1/audit-events"), () =>
        HttpResponse.json({
          items: [
            {
              ...AUDIT[0],
              id: "4c4c4c4c-4c4c-4c4c-8c4c-4c4c4c4c4c4c",
              chain_seq: 413,
              occurred_at: "2026-09-16T11:00:03Z",
              action: "contract.active",
              actor: SYSTEM_ACTOR,
              comment: null,
              on_behalf_of: MAYA_USER,
            },
            AUDIT[0],
          ],
          next_cursor: null,
        }),
      ),
    );
    open("audit");

    await screen.findByRole("list", { name: "Activity" });
    expect(activityTexts()).toEqual([
      "System on behalf of Maya Chen activated the contract",
      "Maya Chen recorded events",
    ]);
  });

  it("is not offered without audit.read", async () => {
    const reads = serve();
    open("audit", ROBERT);

    const group = await screen.findByRole("radiogroup", { name: "History view" });
    expect(
      within(group)
        .getAllByRole("radio")
        .map((radio) => radio.textContent),
    ).toEqual(["Activity", "Versions"]);
    // `view=audit` without the permission falls back to Activity and reads no audit event.
    await screen.findByRole("list", { name: "Activity" });
    expect(reads.audit).toEqual([]);
    expect(historyViewOf("audit", false)).toBe("activity");
    expect(historyViewOf("versions", false)).toBe("versions");
    expect(historyViewOf("nonsense", true)).toBe("activity");
  });

  // SCREENS §4.7 and §0.6 SCR-PERM-02 (rev 1.34; item W-12, slice b; supervisor ruling R-28): the audit
  // events are a list of the whole workspace, read with `audit.read` for all entities.
  it("is not offered to a holder of audit.read for named entities", async () => {
    const reads = serve();
    const held = [...READER, "audit.read"];
    open(
      "audit",
      signedInMe({
        permissions: held,
        permission_scopes: Object.fromEntries(
          held.map((code) => [code, ["0a1b2c3d-4e5f-4a6b-8c7d-000000000001"]]),
        ),
      }),
    );

    const group = await screen.findByRole("radiogroup", { name: "History view" });
    expect(
      within(group)
        .getAllByRole("radio")
        .map((radio) => radio.textContent),
    ).toEqual(["Activity", "Versions"]);
    await screen.findByRole("list", { name: "Activity" });
    expect(reads.audit).toEqual([]);
  });

  it("a read of the audit events that is refused removes the option and shows Activity, without an error", async () => {
    const reads = serve();
    const refused: string[] = [];
    server.use(
      http.get(apiUrl("/api/v1/audit-events/verifications"), () =>
        problemResponse("forbidden", 403, "Permission denied"),
      ),
      http.get(apiUrl("/api/v1/audit-events"), ({ request }) => {
        refused.push(new URL(request.url).search);
        return problemResponse("forbidden", 403, "Permission denied");
      }),
    );
    open("audit");

    // The Activity view of a member without the permission: its own read, its own list.
    await waitFor(() => {
      expect(reads.history.length).toBeGreaterThan(0);
    });
    await screen.findByRole("list", { name: "Activity" });
    expect(screen.getByTestId("SF-03-pane-activity")).toBeTruthy();
    expect(screen.queryByTestId("SF-03-pane-audit")).toBeNull();
    expect(
      within(screen.getByRole("radiogroup", { name: "History view" }))
        .getAllByRole("radio")
        .map((radio) => `${radio.textContent}:${radio.getAttribute("aria-checked") ?? ""}`),
    ).toEqual(["Activity:true", "Versions:false"]);
    expect(screen.queryByText("Could not load the audit trail")).toBeNull();
    expect(screen.queryByText("Permission denied")).toBeNull();
    // The refused read is not sent again.
    expect(refused).toHaveLength(1);
  });

  it("names a refused or unknown action without losing it", () => {
    expect(auditVerb({ action: "contract.replace_draft", outcome: "SUCCESS" })).toBe(
      "replaced the draft",
    );
    expect(auditVerb({ action: "contract.replace_draft", outcome: "DENIED" })).toBe(
      "was refused: replaced the draft",
    );
    expect(auditVerb({ action: "contract.something_new", outcome: "SUCCESS" })).toBe(
      "contract.something_new",
    );
  });
});
