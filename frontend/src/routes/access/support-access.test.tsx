// @vitest-environment jsdom
// SF-14:support-access and REQ-PLT-036 (BUILD_SPEC WEB-22; SCREENS_B §9.14; 04 API-R-14): the grid
// "Support grants" shows Operator, Scope "Read-only", Reason, Ticket, Valid from, Valid to, Status,
// Approval, Approved and Revoked; a pending request shows the info banner "Support access requested by
// operator <name>: read-only from <start> to <end>." with the link "Review in Approvals"; "Revoke"
// requires a reason and states "The operator's sessions end immediately."; the empty state reads "No
// support access"; "View operator activity" is not rendered (BS1-D-14).
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { isRevocable, type SupportGrant } from "../../lib/api/queries/support-grants";
import { accessDescription } from "../../test/access";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, server } from "../../test/msw";
import { REFUSAL_REFERENCE, REFUSAL_TITLE, refusedWith } from "../../test/refusals";
import { grantFilterFields, grantQuery, pendingRequestText } from "./support-access";

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

const GRACE = signedInMe({ permissions: ["support_grant.approve", "user.manage"] });

function grant(overrides: Partial<SupportGrant> & Pick<SupportGrant, "id">): SupportGrant {
  return {
    approval_request_id: null,
    approved_at: null,
    created_at: "2026-09-12T18:00:00Z",
    created_by: {
      id: "0p0p0p0p-0p0p-4p0p-8p0p-0p0p0p0p0p0p",
      kind: "OPERATOR",
      display_name: "Ari Lang",
    },
    operator: {
      id: "0p0p0p0p-0p0p-4p0p-8p0p-0p0p0p0p0p0p",
      kind: "OPERATOR",
      display_name: "Ari Lang",
    },
    reason: "Investigate export failure",
    revoked_at: null,
    revoked_by: null,
    scope: "READ_ONLY",
    status: "REQUESTED",
    ticket_ref: "SUP-2291",
    valid_from: "2026-09-13T09:00:00Z",
    valid_to: "2026-09-13T17:00:00Z",
    ...overrides,
  };
}

const ARI = grant({
  id: "a1a1a1a1-a1a1-4a1a-8a1a-a1a1a1a1a1a1",
  approval_request_id: "e5e5e5e5-e5e5-4e5e-8e5e-e5e5e5e5e5e5",
});
/** Approved for a window that has not expired: "Revoke" shows (SCREENS_B §9.14). */
const BEA = grant({
  id: "b2b2b2b2-b2b2-4b2b-8b2b-b2b2b2b2b2b2",
  operator: {
    id: "1q1q1q1q-1q1q-4q1q-8q1q-1q1q1q1q1q1q",
    kind: "OPERATOR",
    display_name: "Bea Novak",
  },
  reason: "Reproduce a schedule regeneration defect",
  ticket_ref: "SUP-2304",
  status: "APPROVED",
  approval_request_id: "f6f6f6f6-f6f6-4f6f-8f6f-f6f6f6f6f6f6",
  approved_at: "2029-12-31T20:00:00Z",
  valid_from: "2030-01-01T08:00:00Z",
  valid_to: "2030-01-02T08:00:00Z",
});
const CAI = grant({
  id: "c3c3c3c3-c3c3-4c3c-8c3c-c3c3c3c3c3c3",
  operator: {
    id: "2r2r2r2r-2r2r-4r2r-8r2r-2r2r2r2r2r2r",
    kind: "OPERATOR",
    display_name: "Cai Wen",
  },
  reason: "Check a webhook delivery backlog",
  ticket_ref: null,
  status: "EXPIRED",
  approval_request_id: "07070707-0707-4707-8707-070707070707",
  approved_at: "2026-09-01T07:30:00Z",
  valid_from: "2026-09-01T08:00:00Z",
  valid_to: "2026-09-01T12:00:00Z",
});

function serve(grants: readonly SupportGrant[]) {
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/books"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/periods"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/saved-views"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/support-grants"), ({ request }) => {
      const url = new URL(request.url);
      const statuses = url.searchParams.getAll("status").flatMap((value) => value.split(","));
      const items =
        statuses.length === 0 ? grants : grants.filter((item) => statuses.includes(item.status));
      return HttpResponse.json(
        { items, next_cursor: null },
        {
          headers:
            url.searchParams.get("count") === "true"
              ? { "X-Erev-Total-Count": String(items.length) }
              : {},
        },
      );
    }),
  );
}

describe("SF-14:support-access and REQ-PLT-036", () => {
  it("the grid Support grants shows Operator, Scope Read-only, Reason, Ticket, Valid from, Valid to, Status, Approval, Approved and Revoked; a pending request shows the info banner with Review in Approvals", async () => {
    serve([ARI, BEA, CAI]);
    renderApp("/settings/support-access", { me: GRACE, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-14-grid-support-grants")).findByRole(
      "grid",
      { name: "Support grants" },
    );
    const headers = within(grid)
      .getAllByRole("columnheader")
      .map((header) => header.textContent?.trim() ?? "");
    for (const name of [
      "Operator",
      "Scope",
      "Reason",
      "Ticket",
      "Valid from",
      "Valid to",
      "Status",
      "Approval",
      "Approved",
      "Revoked",
    ]) {
      expect(headers.some((header) => header.startsWith(name))).toBe(true);
    }
    const ari = await within(grid).findByTestId(`SF-14-row-${ARI.id}`);
    expect(within(ari).getByText("Ari Lang")).toBeTruthy();
    expect(within(ari).getByText("Read-only")).toBeTruthy();
    expect(within(ari).getByText("Investigate export failure")).toBeTruthy();
    expect(within(ari).getByText("SUP-2291")).toBeTruthy();
    expect(within(ari).getByText("13 Sep 2026 09:00 UTC")).toBeTruthy();
    expect(within(ari).getByText("13 Sep 2026 17:00 UTC")).toBeTruthy();
    expect(within(ari).getByText("Pending approval")).toBeTruthy();
    expect(within(ari).getByRole("link", { name: "Request" }).getAttribute("href")).toBe(
      `/approvals/requests/${String(ARI.approval_request_id)}`,
    );
    const cai = within(grid).getByTestId(`SF-14-row-${CAI.id}`);
    expect(within(cai).getByText("Expired")).toBeTruthy();
    expect(within(cai).getByText("01 Sep 2026 07:30 UTC")).toBeTruthy();

    const banner = await screen.findByTestId("SF-14-banner-support-request");
    // The info banner is a live status region (DS-CMP-29); its heading carries the request copy.
    const status = within(banner).getByRole("status");
    expect(
      within(status).getByRole("heading", {
        name: "Support access requested by operator Ari Lang: read-only from 13 Sep 2026 09:00 UTC to 13 Sep 2026 17:00 UTC.",
      }),
    ).toBeTruthy();
    expect(pendingRequestText(ARI)).toBe(
      "Support access requested by operator Ari Lang: read-only from 13 Sep 2026 09:00 UTC to 13 Sep 2026 17:00 UTC.",
    );
    expect(
      within(banner).getByRole("link", { name: "Review in Approvals" }).getAttribute("href"),
    ).toBe(`/approvals/requests/${String(ARI.approval_request_id)}`);
    expect(screen.getAllByTestId("SF-14-banner-support-request")).toHaveLength(1);

    // BS1-D-14: the audit-log link arrives with the RPS item that builds SF-09:audit-log.
    expect(screen.queryByText("View operator activity")).toBeNull();
    expect(grantQuery("?f.status=in:APPROVED,EXPIRED", grantFilterFields())).toEqual({
      status: ["APPROVED", "EXPIRED"],
    });
  });

  it("Revoke shows on approved, unexpired grants only, requires a reason, states the consequence and posts the revocation", async () => {
    const bodies: unknown[] = [];
    serve([BEA, CAI]);
    server.use(
      http.post(apiUrl(`/api/v1/support-grants/${BEA.id}/revoke`), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({
          ...BEA,
          status: "REVOKED",
          revoked_at: "2026-09-19T10:00:00Z",
          revoked_by: { id: GRACE.user.id, kind: "USER", display_name: "Maya Chen" },
        });
      }),
    );
    renderApp("/settings/support-access", { me: GRACE, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-14-grid-support-grants")).findByRole(
      "grid",
      { name: "Support grants" },
    );
    const bea = await within(grid).findByTestId(`SF-14-row-${BEA.id}`);
    const cai = within(grid).getByTestId(`SF-14-row-${CAI.id}`);
    expect(within(cai).queryByRole("button", { name: "Revoke" })).toBeNull();
    expect(isRevocable(BEA, Date.now())).toBe(true);
    expect(isRevocable(CAI, Date.now())).toBe(false);
    expect(isRevocable({ ...BEA, valid_to: "2026-09-01T12:00:00Z" }, Date.now())).toBe(false);

    fireEvent.click(within(bea).getByRole("button", { name: "Revoke" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Revoke support access for Bea Novak?",
    });
    expect(within(dialog).getByText("The operator's sessions end immediately.")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Revoke support access" }));
    expect(await within(dialog).findByText(/at least 10 characters/i)).toBeTruthy();
    expect(bodies).toEqual([]);

    fireEvent.change(within(dialog).getByRole("textbox", { name: "Reason (required)" }), {
      target: { value: "Investigation finished; access no longer needed." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Revoke support access" }));
    expect(await screen.findByText("Support access for Bea Novak revoked.")).toBeTruthy();
    expect(bodies).toEqual([{ reason: "Investigation finished; access no longer needed." }]);
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): the dialog shows no message at its
  // reason, so the banner says every sentence of a refusal; one that names a member was shown nowhere.
  it("Revoke under a refused command says every sentence", async () => {
    const sentence = "This grant expired before it was revoked.";
    serve([BEA, CAI]);
    server.use(
      http.post(apiUrl(`/api/v1/support-grants/${BEA.id}/revoke`), () =>
        refusedWith({ valid_to: sentence }),
      ),
    );
    renderApp("/settings/support-access", { me: GRACE, screenRoutes: SCREEN_ROUTES });
    const grid = await within(await screen.findByTestId("SF-14-grid-support-grants")).findByRole(
      "grid",
      { name: "Support grants" },
    );
    const bea = await within(grid).findByTestId(`SF-14-row-${BEA.id}`);
    fireEvent.click(within(bea).getByRole("button", { name: "Revoke" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Revoke support access for Bea Novak?",
    });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Reason (required)" }), {
      target: { value: "Investigation finished; access no longer needed." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Revoke support access" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + sentence + REFUSAL_REFERENCE);
  });

  it("the empty state reads No support access", async () => {
    serve([]);
    renderApp("/settings/support-access", { me: GRACE, screenRoutes: SCREEN_ROUTES });

    const empty = await screen.findByTestId("SF-14-empty-support-grants");
    expect(within(empty).getByRole("heading", { name: "No support access" })).toBeTruthy();
    expect(
      within(empty).getByText(
        "A platform operator can read this workspace only under a grant that a workspace administrator approves, for at most 72 hours. Every operator action is logged here and in the audit log.",
      ),
    ).toBeTruthy();
    expect(screen.queryByTestId("SF-14-banner-support-request")).toBeNull();
  });

  it("without support_grant.approve the page shows the access empty state (SCR-PERM-01)", async () => {
    serve([ARI]);
    renderApp("/settings/support-access", {
      me: signedInMe({ permissions: ["contract.read"] }),
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("heading", { name: "You do not have access to Support access" }),
    ).toBeTruthy();
    expect(screen.getByText(/approving support access/)).toBeTruthy();
    expect(screen.queryByTestId("SF-14-grid-support-grants")).toBeNull();
  });

  // W-12e (SCREENS §0.6 SCR-PERM-02 (c); 04 API-C-03 `require_all_entities`): the grants of the
  // workspace are listed to a holder of support_grant.approve for all entities alone. A holder for
  // one entity was shown the grid and its reads were refused.
  it("support_grant.approve for one entity alone: the page says that support access covers every entity, and asks for no grant", async () => {
    const asked: string[] = [];
    serve([ARI]);
    server.use(
      http.get(apiUrl("/api/v1/*"), ({ request }) => {
        asked.push(new URL(request.url).pathname);
      }),
    );
    renderApp("/settings/support-access", {
      me: signedInMe({
        permissions: ["support_grant.approve"],
        permission_scopes: { "support_grant.approve": ["0a1b2c3d-4e5f-4a6b-8c7d-0000000000de"] },
      }),
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("heading", { name: "You do not have access to Support access" }),
    ).toBeTruthy();
    expect(accessDescription()).toBe(
      "Support access covers every entity of the workspace. Ask a workspace administrator for a role that includes approving support access (support_grant.approve) for all entities.",
    );
    expect(screen.queryByTestId("SF-14-grid-support-grants")).toBeNull();
    expect(asked.filter((path) => path === "/api/v1/support-grants")).toEqual([]);
  });
});
