// @vitest-environment jsdom
// SF-12 inbox toolbar (BUILD_SPEC WEB-16; SCREENS §15.3 FilterBar, §0.5 SCR-URL-10, SCR-URL-18,
// SCR-URL-21; 04 API-R-09): the chips Type, Entity and Status reach `GET /approvals` as the filters the
// route admits; Status is a chip of All requests only; the context pill's entity is not applied; a
// request opened from a filtered list keeps the chips; a filtered list without rows says so.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import type { Approval } from "../../lib/api/queries/approvals";
import { installMemoryStorage, preloadScreens, renderApp, signedInMe } from "../../test/app";
import { apiUrl, installMswServer, server } from "../../test/msw";
import { approvalFilterFields, approvalListFilters, isBulkLayout, withChips } from "./toolbar";

installMswServer();
installMemoryStorage();

beforeAll(async () => {
  await preloadScreens(SCREEN_ROUTES, ["SF-12", "SF-12:all", "SF-12:request"]);
});

afterEach(() => {
  cleanup();
});

const APPROVER = signedInMe({
  permissions: ["contract.read", "config.read", "contract.approve", "access.approve"],
});
const REQUEST = "1b2c3d4e-5f6a-4b7c-8d9e-0f1a2b3c4d5e";

function roleChange(): Approval {
  return {
    id: REQUEST,
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
    all_entities: false,
    amount: null,
    flags: [],
    routing: { rule_set_version_id: null, rule_key: null },
    preparer: {
      id: "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a",
      display_name: "Tomás Rivera",
      kind: "USER",
    },
    submitted_at: "2026-09-01T08:30:00Z",
    decided_at: "2026-09-01T09:00:00Z",
    voided_at: null,
    void_reason: null,
    current_step_no: 1,
    steps: [],
    impact_preview: null,
    attachments: [],
    can_decide: false,
    content_withheld: false,
    reason_code: null,
    comment: null,
  };
}

/** API-S-Entity as the shell and the Entity chip read it. */
function entity(id: string, code: string, name: string) {
  return {
    id,
    code,
    name,
    country_code: null,
    functional_currency: "USD",
    time_zone: "UTC",
    calendar_id: "0a1b2c3d-4e5f-4a6b-8c7d-0000000000c1",
    parent_entity_id: null,
    tax_id: null,
    is_active: true,
    books: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    row_version: 1,
  };
}

function list(items: readonly unknown[]) {
  return HttpResponse.json({ items, next_cursor: null });
}

/**
 * The list reads of `GET /approvals` without paging parameters, in the order they arrive. `read`
 * resolves when the list has been read with a search, and `opened` when the request page has read
 * its request: the read itself is the event a case waits for, so a slow host delays the case and
 * does not fail it.
 */
interface ListReads {
  readonly bindings: readonly string[];
  readonly read: (search: string) => Promise<void>;
  readonly opened: Promise<void>;
}

function serve(items: readonly Approval[]): ListReads {
  const bindings: string[] = [];
  const awaited = new Map<string, (() => void)[]>();
  let requestRead = (): void => undefined;
  const opened = new Promise<void>((arrived) => {
    requestRead = arrived;
  });
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () => list([])),
    http.get(apiUrl("/api/v1/books"), () => list([])),
    http.get(apiUrl("/api/v1/periods"), () => list([])),
    http.get(apiUrl("/api/v1/entities"), () =>
      list([
        entity("0a1b2c3d-4e5f-4a6b-8c7d-000000000001", "AVM-US", "Avenmoor US Inc."),
        entity("0a1b2c3d-4e5f-4a6b-8c7d-000000000002", "AVM-UK", "Avenmoor UK Ltd"),
      ]),
    ),
    http.get(apiUrl("/api/v1/approvals"), ({ request }) => {
      const params = new URL(request.url).searchParams;
      const counting = params.get("count") === "true";
      params.delete("limit");
      params.delete("count");
      if (!counting) {
        const search = params.toString();
        bindings.push(search);
        for (const arrived of awaited.get(search) ?? []) {
          arrived();
        }
        awaited.delete(search);
      }
      return HttpResponse.json(
        { items: counting ? items.slice(0, 1) : items, next_cursor: null },
        { headers: counting ? { "X-Erev-Total-Count": String(items.length) } : {} },
      );
    }),
    http.get(apiUrl(`/api/v1/approvals/${REQUEST}`), () => {
      requestRead();
      return HttpResponse.json(roleChange());
    }),
  );
  return {
    bindings,
    opened,
    read: (search) =>
      bindings.includes(search)
        ? Promise.resolve()
        : new Promise<void>((arrived) => {
            awaited.set(search, [...(awaited.get(search) ?? []), arrived]);
          }),
  };
}

function open(entry: string) {
  return renderApp(entry, { me: APPROVER, screenRoutes: SCREEN_ROUTES });
}

describe("SF-12 FilterBar", () => {
  it("the chips of All requests reach the list read as subject_type, entity and status", async () => {
    const reads = serve([roleChange()]);
    const { router } = open(
      "/approvals/all?f.type=is:ROLE_CHANGE&f.entity=in:AVM-US,AVM-UK&f.status=is:APPROVED",
    );
    await screen.findByRole("listbox", { name: "Approval requests" });
    const bar = screen.getByTestId("SF-12-filter-bar");
    for (const chip of ["Type is Role change, edit filter", "Status is Approved, edit filter"]) {
      expect(await within(bar).findByRole("button", { name: chip })).toBeTruthy();
    }
    expect(
      await within(bar).findByRole("button", { name: /^Entity .*AVM-US.*AVM-UK, edit filter$/ }),
    ).toBeTruthy();
    // API-R-09: one subject_type, one status, the entity codes repeated; newest first.
    await reads.read(
      "status=APPROVED&subject_type=ROLE_CHANGE&entity=AVM-US&entity=AVM-UK&sort=-submitted_at",
    );
    // The route has no search: the bar holds chips only.
    expect(within(bar).queryByRole("searchbox")).toBeNull();

    // A request opened from the filtered list keeps the chips, and so does the list beside it.
    // DS-CMP-08: a pointer press selects at once.
    fireEvent.mouseDown(
      screen.getByRole("option", { name: /Add the custom role Deal desk analyst/ }),
    );
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/approvals/requests/${REQUEST}`),
    );
    expect(router.state.location.search).toBe(
      "?view=all&f.type=is:ROLE_CHANGE&f.entity=in:AVM-US,AVM-UK&f.status=is:APPROVED",
    );
    // The address moves before the page does: the list's own bar stays on screen until the request
    // page has rendered. Its read of the request says that it has, and the bar found after it is the
    // request page's.
    await reads.opened;
    expect(
      await within(await screen.findByTestId("SF-12-filter-bar")).findByRole("button", {
        name: "Type is Role change, edit filter",
      }),
    ).toBeTruthy();

    // Removing a chip reads the list again without its filter.
    fireEvent.click(
      within(screen.getByTestId("SF-12-filter-bar")).getByRole("button", {
        name: "Remove filter: Status",
      }),
    );
    await reads.read("subject_type=ROLE_CHANGE&entity=AVM-US&entity=AVM-UK&sort=-submitted_at");
  });

  // KIT-FILTER-LEAVING-1 (docs/dev-guide.md DG-FE-03 rev 1.215): the whole chain, from a chip of the
  // list to the router's guard, which reads the route id `useNavigate` passes with the write.
  it("a chip pressed on the list while the request page is being rendered does not rewrite the request's address", async () => {
    const reads = serve([roleChange()]);
    const { router } = open("/approvals/all?f.type=is:ROLE_CHANGE&f.status=is:APPROVED");
    await screen.findByRole("listbox", { name: "Approval requests" });
    await reads.read("status=APPROVED&subject_type=ROLE_CHANGE&sort=-submitted_at");
    const remove = await within(screen.getByTestId("SF-12-filter-bar")).findByRole("button", {
      name: "Remove filter: Status",
    });
    // The router takes the new address at once; React renders the page for it a task later.
    await router.navigate(
      `/approvals/requests/${REQUEST}?view=all&f.type=is:ROLE_CHANGE&f.status=is:APPROVED`,
    );
    expect(router.state.location.pathname).toBe(`/approvals/requests/${REQUEST}`);
    expect(document.body.contains(remove)).toBe(true);
    fireEvent.click(remove);
    await reads.opened;
    await waitFor(() => expect(router.state.navigation.state).toBe("idle"));
    expect(`${router.state.location.pathname}${router.state.location.search}`).toBe(
      `/approvals/requests/${REQUEST}?view=all&f.type=is:ROLE_CHANGE&f.status=is:APPROVED`,
    );
  });

  it("Status is no chip of Waiting for me, and the context pill's entity is not a filter", async () => {
    const reads = serve([]);
    open("/approvals?entity=AVM-US&f.status=is:APPROVED&f.type=is:IMPORT_COMMIT");
    const bar = await screen.findByTestId("SF-12-filter-bar");
    expect(
      await within(bar).findByRole("button", { name: "Type is Import commit, edit filter" }),
    ).toBeTruthy();
    // SCR-URL-21: a chip the view does not offer is dropped, and said.
    expect(
      await screen.findByText("Some filters in the link were not recognised and were removed."),
    ).toBeTruthy();
    expect(within(bar).queryByRole("button", { name: /^Status/ })).toBeNull();
    await reads.read(
      "assigned_to_me=true&status=PENDING&subject_type=IMPORT_COMMIT&sort=submitted_at",
    );
    expect(reads.bindings.some((binding) => binding.includes("entity="))).toBe(false);
    // SCR-ST-04: a filtered list without rows.
    expect(
      await screen.findByRole("heading", { name: "No approval requests match these filters" }),
    ).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "No requests waiting for you" })).toBeNull();
  });
});

describe("the chips as the list reads them", () => {
  const entities = [{ code: "AVM-US" }, { code: "AVM-UK" }] as never;

  it("Type and Entity on every view, Status on All requests; no Entity chip without the structure", () => {
    expect(approvalFilterFields("waiting", "", entities).map((field) => field.name)).toEqual([
      "type",
      "entity",
    ]);
    expect(approvalFilterFields("submitted", "", entities).map((field) => field.name)).toEqual([
      "type",
      "entity",
    ]);
    expect(approvalFilterFields("all", "", entities).map((field) => field.name)).toEqual([
      "type",
      "entity",
      "status",
    ]);
    expect(approvalFilterFields("all", "", null).map((field) => field.name)).toEqual([
      "type",
      "status",
    ]);
    const status = approvalFilterFields("all", "", entities)[2];
    expect(status?.options?.map((option) => option.label)).toEqual([
      "Pending approval",
      "Approved",
      "Rejected",
      "Stale or void",
      "Withdrawn",
    ]);
    // While the entities load, a link's own values stand in, so its chip is kept.
    expect(
      approvalFilterFields("all", "?f.entity=is:AVM-DE", undefined)[1]?.options?.map(
        (option) => option.value,
      ),
    ).toEqual(["AVM-DE"]);
  });

  it("the filters are the API's literals", () => {
    const fields = approvalFilterFields("all", "", entities);
    expect(
      approvalListFilters("?f.type=is:CONTRACT_VOID&f.entity=is:AVM-UK&f.status=is:VOIDED", fields),
    ).toEqual({ subjectType: "CONTRACT_VOID", entity: ["AVM-UK"], status: "VOIDED" });
    expect(approvalListFilters("", fields)).toEqual({
      subjectType: null,
      entity: [],
      status: null,
    });
    // A value outside the route's choices is no filter.
    expect(approvalListFilters("?f.type=is:INVOICE", fields).subjectType).toBeNull();
  });

  it("a link keeps the chips and nothing else; the bulk layout is Waiting for me's", () => {
    expect(
      withChips("/approvals/requests/x?view=all", "?entity=AVM-US&f.type=is:ROLE_CHANGE"),
    ).toBe("/approvals/requests/x?view=all&f.type=is:ROLE_CHANGE");
    expect(withChips("/approvals", "?layout=bulk&f.entity=in:AVM-US,AVM-UK")).toBe(
      "/approvals?f.entity=in:AVM-US,AVM-UK",
    );
    expect(withChips("/approvals/all", "?layout=bulk")).toBe("/approvals/all");
    expect(isBulkLayout("waiting", "?layout=bulk")).toBe(true);
    expect(isBulkLayout("waiting", "?layout=lines")).toBe(false);
    expect(isBulkLayout("all", "?layout=bulk")).toBe(false);
  });
});
