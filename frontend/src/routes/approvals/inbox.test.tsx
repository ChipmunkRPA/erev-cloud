// @vitest-environment jsdom
// SF-12 master list (BUILD_SPEC WEB-15; SCREENS §15.3, §15.6, §15.10; 04 API-R-09): the Waiting for me,
// Submitted by me and All requests bindings, the two-line rows, the empty views and the member without
// approval permissions.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { listSearch } from "../../lib/api/lists";
import {
  type Approval,
  holdsApprovalPermission,
  requestRoute,
  viewQuery,
} from "../../lib/api/queries/approvals";
import { accessOf } from "../../lib/access";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import { apiUrl, installMswServer, server } from "../../test/msw";
import messages from "../../messages/en.json";
import { CATALOGUED_FLAGS, entitiesLabel, flagLabel, nextRequestId } from "./inbox";

installMswServer();
installMemoryStorage();

afterEach(() => {
  cleanup();
});

const MAYA = {
  id: "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a",
  display_name: "Maya Chen",
  kind: "USER",
} as const;

const APPROVER = signedInMe({ permissions: ["contract.read", "contract.approve"] });

function approval(overrides: Partial<Approval> = {}): Approval {
  return {
    id: "8f0c5a1e-3b2d-4c6e-9a7f-1d2e3f4a5b6c",
    request_no: "APR-000229",
    subject: {
      type: "CONTRACT_ACTIVATION",
      id: "7d1e2f3a-4b5c-4d6e-8f7a-9b0c1d2e3f4a",
      display: "Contract activation BG-AVM-0020",
      href: null,
      content_sha256: "a".repeat(64),
      row_version: 3,
    },
    summary: "Contract activation BG-AVM-0020",
    status: "PENDING",
    entity: { id: "2a3b4c5d-6e7f-4a8b-9c0d-1e2f3a4b5c6d", code: "AVM-US", name: "Avenmoor US" },
    entities: [{ id: "2a3b4c5d-6e7f-4a8b-9c0d-1e2f3a4b5c6d", code: "AVM-US", name: "Avenmoor US" }],
    entity_count: 1,
    all_entities: false,
    amount: { amount: "146000.00", currency: "USD" },
    flags: [],
    routing: { rule_set_version_id: null, rule_key: null },
    preparer: MAYA,
    submitted_at: "2026-09-12T14:05:00Z",
    decided_at: null,
    voided_at: null,
    void_reason: null,
    current_step_no: 1,
    steps: [
      {
        step_no: 1,
        name: "Contract approval",
        required_permission: "contract.approve",
        min_approvers: 1,
        status: "ACTIVE",
        decisions: [],
      },
    ],
    impact_preview: null,
    attachments: [],
    can_decide: true,
    content_withheld: false,
    reason_code: null,
    comment: null,
    ...overrides,
  };
}

const ROLE_CHANGE = approval({
  id: "1b2c3d4e-5f6a-4b7c-8d9e-0f1a2b3c4d5e",
  request_no: "APR-000012",
  subject: {
    type: "ROLE_CHANGE",
    id: "6c5d4e3f-2a1b-4c0d-9e8f-7a6b5c4d3e2f",
    display: "Add the custom role Deal desk analyst",
    href: null,
    content_sha256: "c".repeat(64),
    row_version: null,
  },
  summary: "Add the custom role Deal desk analyst",
  status: "APPROVED",
  entity: null,
  entities: [],
  entity_count: 0,
  amount: null,
  decided_at: "2026-09-01T09:00:00Z",
  submitted_at: "2026-09-01T08:30:00Z",
  can_decide: false,
});

/** `GET /approvals` answering `items`; each search is recorded, and `count=true` answers `total`. */
function listApprovals(items: readonly Approval[], searches: string[], total = items.length): void {
  server.use(
    http.get(apiUrl("/api/v1/approvals"), ({ request }) => {
      const url = new URL(request.url);
      searches.push(url.search);
      const counting = url.searchParams.get("count") === "true";
      return HttpResponse.json(
        { items: counting ? items.slice(0, 1) : items, next_cursor: null },
        { headers: counting ? { "X-Erev-Total-Count": String(total) } : {} },
      );
    }),
  );
}

/** `GET /currencies`: the API currency reference of the amounts (DS-FMT-03). */
function currencies(): void {
  server.use(
    http.get(apiUrl("/api/v1/currencies"), () =>
      HttpResponse.json({
        items: [
          { code: "USD", minor_unit: 2, name: "US Dollar", numeric_code: "840", is_active: true },
        ],
        next_cursor: null,
      }),
    ),
  );
}

/** The recorded searches without the paging parameters `limit` and `count`. */
function bindings(searches: readonly string[]): string[] {
  return searches.map((search) => {
    const params = new URLSearchParams(search);
    params.delete("limit");
    params.delete("count");
    return params.toString();
  });
}

function options(): HTMLElement[] {
  return within(screen.getByRole("listbox", { name: "Approval requests" })).getAllByRole("option");
}

function renderInbox(entry: string, me = APPROVER) {
  return renderApp(entry, { me, screenRoutes: SCREEN_ROUTES });
}

describe("SF-12 entities of a request (04 §16.10 API-S-Approval entities)", () => {
  const US = { id: "2a3b4c5d-6e7f-4a8b-9c0d-1e2f3a4b5c6d", code: "AVM-US", name: "Avenmoor US" };
  const DE = { id: "9f8e7d6c-5b4a-4c3d-8e2f-1a0b9c8d7e6f", code: "AVM-DE", name: "Avenmoor DE" };

  it("names every entity the reader may read, the ones outside its entities by count, and a request of every entity", () => {
    expect(entitiesLabel({ entities: [US], entity_count: 1, all_entities: false })).toBe("AVM-US");
    expect(entitiesLabel({ entities: [DE, US], entity_count: 2, all_entities: false })).toBe(
      "AVM-DE, AVM-US",
    );
    expect(entitiesLabel({ entities: [US], entity_count: 2, all_entities: false })).toBe(
      "AVM-US and 1 more entity",
    );
    expect(entitiesLabel({ entities: [], entity_count: 3, all_entities: false })).toBe(
      "3 entities outside your access",
    );
    expect(entitiesLabel({ entities: [], entity_count: 0, all_entities: true })).toBe(
      "All entities",
    );
    expect(entitiesLabel({ entities: [], entity_count: 0, all_entities: false })).toBeNull();
  });

  it("a request of two entities lists both codes in its row; a request of every entity reads All entities", async () => {
    currencies();
    listApprovals(
      [
        approval({
          summary: "Combine BG-AVM-0020 and BG-AVD-0007",
          entity: null,
          entities: [DE, US],
          entity_count: 2,
        }),
        approval({
          id: "3c4d5e6f-7a8b-4c9d-8e0f-1a2b3c4d5e6f",
          request_no: "APR-000230",
          summary: "Commit import IMP-000031",
          entity: null,
          entities: [],
          entity_count: 0,
          all_entities: true,
        }),
      ],
      [],
    );
    renderInbox("/approvals");

    await screen.findByRole("listbox", { name: "Approval requests" });
    const [first, second] = options();
    if (first === undefined || second === undefined) {
      throw new Error("two options expected");
    }
    expect(within(first).getByText("AVM-DE, AVM-US")).toBeTruthy();
    expect(within(second).getByText("All entities")).toBeTruthy();
  });
});

describe("SF-12 master list", () => {
  it("Waiting for me binds GET /approvals?assigned_to_me=true&status=PENDING&sort=submitted_at; line 1 holds summary and USD 146,000.00, line 2 the label, entity code, preparer and date", async () => {
    const searches: string[] = [];
    currencies();
    listApprovals(
      [
        approval(),
        approval({
          id: "3c4d5e6f-7a8b-4c9d-8e0f-1a2b3c4d5e6f",
          request_no: "APR-000230",
          summary: "Manual adjustment BG-AVM-0022",
          amount: { amount: "2400.00", currency: "USD" },
        }),
      ],
      searches,
      3,
    );
    renderInbox("/approvals");

    expect(await screen.findByRole("heading", { level: 1, name: "Approvals" })).toBeTruthy();
    await screen.findByRole("listbox", { name: "Approval requests" });
    const [first, second] = options();
    if (first === undefined || second === undefined) {
      throw new Error("two options expected");
    }
    expect(within(first).getByText("Contract activation BG-AVM-0020")).toBeTruthy();
    expect(within(first).getByText("USD 146,000.00")).toBeTruthy();
    for (const text of ["Contract activation", "AVM-US", "Maya Chen", "12 Sep 2026"]) {
      expect(within(first).getByText(text)).toBeTruthy();
    }
    expect(within(first).queryByText("Pending approval")).toBeNull();
    expect(within(second).getByText("USD 2,400.00")).toBeTruthy();

    expect(bindings(searches)).toContain("assigned_to_me=true&status=PENDING&sort=submitted_at");
    expect(await screen.findByRole("link", { name: "Waiting for me 3" })).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Waiting for me 3" }).getAttribute("aria-current"),
    ).toBe("page");
    // The count follows the loaded items in a later commit (F-ADM latent-race sweep).
    expect(await screen.findByText("2 requests")).toBeTruthy();
    expect(screen.getByText("oldest first")).toBeTruthy();
    expect(
      screen.getByText("Select a request to review its changes, impact and routing."),
    ).toBeTruthy();
    // The title is set in a passive effect after the commit (F-ADM latent-race sweep).
    await waitFor(() => {
      expect(document.title).toBe("Approvals · eRev Cloud");
    });
  });

  it("Submitted by me binds preparer=me&sort=-submitted_at; a decided row shows Role change and its status chip", async () => {
    const searches: string[] = [];
    listApprovals([ROLE_CHANGE], searches);
    renderInbox("/approvals/submitted");

    await screen.findByRole("listbox", { name: "Approval requests" });
    const [row] = options();
    if (row === undefined) {
      throw new Error("one option expected");
    }
    expect(within(row).getByText("Add the custom role Deal desk analyst")).toBeTruthy();
    expect(within(row).getByText("Role change")).toBeTruthy();
    expect(within(row).getByText("Approved")).toBeTruthy();
    expect(within(row).getByText("01 Sep 2026")).toBeTruthy();
    expect(within(row).queryByText(/USD/)).toBeNull();

    expect(bindings(searches)).toContain("preparer=me&sort=-submitted_at");
    expect(screen.getByText("newest first")).toBeTruthy();
    // The title is set in a passive effect after the commit (F-ADM latent-race sweep).
    await waitFor(() => {
      expect(document.title).toBe("Submitted by me · eRev Cloud");
    });
  });

  it("All requests binds sort=-submitted_at; rows show Stale, the catalogued flag and a routing flag verbatim", async () => {
    const searches: string[] = [];
    currencies();
    listApprovals(
      [
        approval({
          status: "VOIDED",
          void_reason: "STALE_SUBJECT",
          flags: ["TREATMENT_OVERRIDE", "TP at or above USD 100,000.00"],
          can_decide: false,
        }),
      ],
      searches,
    );
    renderInbox("/approvals/all");

    await screen.findByRole("listbox", { name: "Approval requests" });
    const [row] = options();
    if (row === undefined) {
      throw new Error("one option expected");
    }
    expect(within(row).getByText("Stale")).toBeTruthy();
    expect(within(row).getByText("Treatment override")).toBeTruthy();
    expect(within(row).getByText("TP at or above USD 100,000.00")).toBeTruthy();
    expect(bindings(searches)).toContain("sort=-submitted_at");
    expect(bindings(searches).filter((search) => search.includes("preparer"))).toEqual([]);
  });

  // SCREENS §15.3 rev 1.70 (item ACT-FLAGS-1; 04 T-PLT-17 rev 1.287): the six flags an activation
  // gained read their labels in the row; before, each showed as sent ("TERMS_NOT_STATED"). A flag the
  // catalogue does not hold still shows verbatim — the fallback stays for a seventh.
  it("a contract activation's row reads the labels of the flags of rev 1.70", async () => {
    currencies();
    listApprovals(
      [
        approval({
          flags: [
            "MATERIAL_RIGHT",
            "NEW_SKU",
            "RATE_NOT_PUBLISHED",
            "SIDE_LETTER",
            "TERMS_NOT_STATED",
            "VARIABLE_CONSIDERATION",
            "SEVENTH_FLAG",
          ],
        }),
      ],
      [],
    );
    renderInbox("/approvals/all");

    await screen.findByRole("listbox", { name: "Approval requests" });
    const [row] = options();
    if (row === undefined) {
      throw new Error("one option expected");
    }
    for (const label of [
      "Material right",
      "New product",
      "Rate not published",
      "Side letter",
      "Terms not stated",
      "Variable consideration",
      "SEVENTH_FLAG",
    ]) {
      expect(within(row).getByText(label)).toBeTruthy();
    }
    for (const literal of ["MATERIAL_RIGHT", "NEW_SKU", "TERMS_NOT_STATED"]) {
      expect(within(row).queryByText(literal)).toBeNull();
    }
  });

  it.each([
    [
      "/approvals",
      "No requests waiting for you",
      "Requests you can approve appear here, oldest first.",
    ],
    ["/approvals/submitted", "You have not submitted any requests.", null],
    ["/approvals/all", "No approval requests yet.", null],
  ])("the empty view %s reads %s", async (entry, title, description) => {
    listApprovals([], []);
    renderInbox(entry);

    expect(await screen.findByRole("heading", { level: 2, name: title })).toBeTruthy();
    if (description !== null) {
      expect(screen.getByText(description)).toBeTruthy();
    }
    expect(screen.queryByRole("listbox", { name: "Approval requests" })).toBeNull();
  });

  // SCREENS §15.4 "Content withheld" (rev 1.32; item W-12d): the row of a request whose content the
  // reader is not shown carries the summary the API sends and "—" where the amount stands; a request
  // without an amount shows nothing there, as before.
  it("a withheld request's row shows — for its amount, and a request without an amount shows nothing", async () => {
    currencies();
    listApprovals(
      [
        approval({
          id: "7f8a9b0c-1d2e-4f3a-8b4c-5d6e7f8a9b0c",
          request_no: "APR-000021",
          summary: "Contract activation APR-000021",
          amount: null,
          content_withheld: true,
        }),
        approval({
          id: "8a9b0c1d-2e3f-4a4b-9c5d-6e7f8a9b0c1d",
          request_no: "APR-000022",
          summary: "Role change for the close team",
          amount: null,
        }),
      ],
      [],
    );
    renderInbox("/approvals/all");

    await screen.findByRole("listbox", { name: "Approval requests" });
    await waitFor(() => expect(options()).toHaveLength(2));
    const [withheld, plain] = options();
    expect(withheld?.textContent).toContain("Contract activation APR-000021");
    expect(withheld?.textContent).toContain("—");
    expect(plain?.textContent).toContain("Role change for the close team");
    expect(plain?.textContent).not.toContain("—");
  });

  it("a user without approval permissions sees You have no approval permissions", async () => {
    const searches: string[] = [];
    listApprovals([approval()], searches);
    renderInbox("/approvals", signedInMe({ permissions: ["contract.read", "audit.read"] }));

    expect(
      await screen.findByRole("heading", { level: 2, name: "You have no approval permissions" }),
    ).toBeTruthy();
    expect(screen.getByText("Items you can view appear in reports and registers.")).toBeTruthy();
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(searches).toEqual([]);
    expect(screen.getByRole("link", { name: "Submitted by me" })).toBeTruthy();
  });

  it("view bindings, approval permissions, next request and flag labels", () => {
    expect(listSearch(viewQuery("waiting"))).toBe(
      "?assigned_to_me=true&status=PENDING&sort=submitted_at",
    );
    expect(listSearch(viewQuery("submitted"))).toBe("?preparer=me&sort=-submitted_at");
    expect(listSearch(viewQuery("all"))).toBe("?sort=-submitted_at");
    const holding = (permissions: string[]) => accessOf(signedInMe({ permissions }));
    expect(holdsApprovalPermission(holding(["contract.read", "scenario.use"]))).toBe(false);
    expect(holdsApprovalPermission(holding(["access.approve"]))).toBe(true);
    expect(nextRequestId(["a", "b", "c"], "b")).toBe("c");
    expect(nextRequestId(["a", "b", "c"], "c")).toBe("b");
    expect(nextRequestId(["a"], "a")).toBeNull();
    expect(nextRequestId(["a", "b"], "z")).toBe("a");
    expect(requestRoute("x", "all")).toBe("/approvals/requests/x?view=all");
    expect(flagLabel("AI_ASSISTED")).toBe("AI assisted");
    // SCREENS §15.3 rev 1.18 (R-104 (a)): the routing flags the API sets read their labels; before,
    // every flag but two showed as sent ("METHODOLOGY_CHANGE").
    expect(
      [
        "ABOVE_THRESHOLD",
        "ABOVE_CONTROLLER_THRESHOLD",
        "MANUAL_ENTRY",
        "NON_STANDARD_TERMS",
        "METHODOLOGY_CHANGE",
        "CATCH_UP_GE_50K",
        "TP_CHANGE_GE_250K",
        "POSTED_LINES",
        "PERIOD_IN_CLOSE",
      ].map(flagLabel),
    ).toEqual([
      "Above threshold",
      "Above Controller threshold",
      "Manual entry",
      "Non-standard terms",
      "Methodology change",
      "Catch-up of USD 50,000.00 or more",
      "Price change of USD 250,000.00 or more",
      "Posted lines",
      "Period in close",
    ]);
    // A routing string of a rule output has no catalogue entry and shows verbatim.
    expect(flagLabel("TP at or above USD 100,000.00")).toBe("TP at or above USD 100,000.00");
    // The set of catalogued flags and the catalogue's `approvals.flag.*` keys are the same list.
    expect(
      Object.keys(messages)
        .filter((key) => key.startsWith("approvals.flag."))
        .map((key) => key.slice("approvals.flag.".length))
        .sort(),
    ).toEqual([...CATALOGUED_FLAGS].sort());
  });
});

it.each([true, false, null])("queue marks current assignment blockage (%s)", async (blocked) => {
  const searches: string[] = [];
  currencies();
  listApprovals([approval({ assignment_blocked: blocked, can_decide: false })], searches);
  renderInbox("/approvals/submitted");
  await screen.findByRole("listbox", { name: "Approval requests" });
  const [row] = options();
  if (row === undefined) throw new Error("one option expected");
  expect(within(row).queryByText("Needs an independent approver") !== null).toBe(blocked === true);
});
