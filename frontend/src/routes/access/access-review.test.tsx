// @vitest-environment jsdom
// SF-14:access-review and REQ-CTL-006 (BUILD_SPEC WEB-21; SCREENS_B §9.13; 04 API-R-51, API-R-12): the
// header shows the status chip and the KPI strip Members, Certified, Revocations requested, Revocations
// completed, Pending; the grid "Items" shows the roles at snapshot joined with "; "; decision buttons are
// named "Certify <member>" and "Request revocation for <member>"; the reviewer's own row shows "You cannot
// review your own access."; "Complete campaign" with pending items shows "Decide <n> pending items before
// completing the campaign."; "Download snapshot" downloads `GET /files/{snapshot_file_id}/content`.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import type { AccessReview, AccessReviewItem } from "../../lib/api/queries/access-reviews";
import { accessDescription } from "../../test/access";
import { installMemoryStorage, MEMBERSHIP_ID, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, server } from "../../test/msw";
import { REFUSAL_REFERENCE, REFUSAL_TITLE, refusedWith } from "../../test/refusals";
import { decisionChip } from "./access-review";

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

const GRACE = signedInMe({ permissions: ["access.approve", "user.manage"] });
const REVIEW_ID = "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1";
const ROUTE = `/settings/access-reviews/${REVIEW_ID}`;

const CAMPAIGN: AccessReview = {
  id: REVIEW_ID,
  name: "Q3 2026 access review",
  status: "IN_REVIEW",
  as_of: "2026-09-12T20:00:00Z",
  reviewers: [
    { membership_id: MEMBERSHIP_ID, user_id: GRACE.user.id, display_name: "Grace Okafor" },
  ],
  counts: { members: 3, certified: 0, revoke_requested: 1, revoked: 0, pending: 2 },
  snapshot_file_id: "f1f1f1f1-f1f1-4f1f-8f1f-f1f1f1f1f1f1",
  started_at: "2026-09-12T20:05:00Z",
  completed_at: null,
  created_by: { id: GRACE.user.id, kind: "USER", display_name: "Grace Okafor" },
  created_at: "2026-09-12T19:55:00Z",
  updated_at: "2026-09-13T10:00:00Z",
  row_version: 3,
};

function item(
  id: string,
  membershipId: string,
  name: string,
  email: string,
  decision: AccessReviewItem["decision"],
): AccessReviewItem {
  return {
    id,
    access_review_campaign_id: REVIEW_ID,
    membership_id: membershipId,
    display_name: name,
    user_email_snapshot: email,
    roles_snapshot: [
      {
        role_code: "Revenue Reviewer",
        is_all_entities: false,
        entity_codes: ["AVM-DE"],
        granted_at: "2026-09-12T19:02:00Z",
        granted_by: "Grace Okafor",
      },
      {
        role_code: "Revenue Accountant",
        is_all_entities: true,
        entity_codes: [],
        granted_at: "2026-09-01T08:00:00Z",
        granted_by: "seed",
      },
    ],
    last_login_at: "2026-09-12T09:30:00Z",
    decision,
    decided_at: decision === "PENDING" ? null : "2026-09-13T10:00:00Z",
    reviewer: null,
    comment: null,
    revocation_completed_at: null,
    row_version: 1,
  };
}

const LENA = item(
  "11111111-1111-4111-8111-111111111111",
  "9b8a7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d",
  "Lena Fischer",
  "lena@demo.erev",
  "PENDING",
);
const OWN = item(
  "22222222-2222-4222-8222-222222222222",
  MEMBERSHIP_ID,
  "Grace Okafor",
  "grace@demo.erev",
  "PENDING",
);
const MAYA = item(
  "33333333-3333-4333-8333-333333333333",
  "3a4b5c6d-7e8f-4a1b-9c2d-3e4f5a6b7c8e",
  "Maya Chen",
  "maya@demo.erev",
  "REVOKE_REQUESTED",
);

function serve(
  review: AccessReview = CAMPAIGN,
  items: readonly AccessReviewItem[] = [LENA, OWN, MAYA],
) {
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
    http.get(apiUrl(`/api/v1/access-reviews/${REVIEW_ID}`), () => HttpResponse.json(review)),
    http.get(apiUrl(`/api/v1/access-reviews/${REVIEW_ID}/items`), ({ request }) =>
      HttpResponse.json(
        { items, next_cursor: null },
        {
          headers:
            new URL(request.url).searchParams.get("count") === "true"
              ? { "X-Erev-Total-Count": String(items.length) }
              : {},
        },
      ),
    ),
  );
}

describe("SF-14:access-review and REQ-CTL-006", () => {
  it("shows the status chip, the KPI strip and the items grid with roles at snapshot; decisions are named per member", async () => {
    serve();
    renderApp(ROUTE, { me: GRACE, screenRoutes: SCREEN_ROUTES });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Q3 2026 access review" }),
    ).toBeTruthy();
    expect(screen.getByText("In review")).toBeTruthy();
    const kpis = screen.getByTestId("SF-14-kpi-strip");
    for (const label of [
      "Members",
      "Certified",
      "Revocations requested",
      "Revocations completed",
      "Pending",
    ]) {
      expect(within(kpis).getByText(label)).toBeTruthy();
    }
    const grid = await within(
      await screen.findByTestId("SF-14-grid-access-review-items"),
    ).findByRole("grid", { name: "Items" });
    const lena = await within(grid).findByTestId("SF-14-row-lena-demo-erev");
    expect(
      within(lena).getByText("Revenue Reviewer (AVM-DE); Revenue Accountant (All entities)"),
    ).toBeTruthy();
    expect(within(lena).getByText("Grace Okafor, seed")).toBeTruthy();
    expect(within(lena).getByRole("button", { name: "Certify Lena Fischer" })).toBeTruthy();
    expect(
      within(lena).getByRole("button", { name: "Request revocation for Lena Fischer" }),
    ).toBeTruthy();

    const own = within(grid).getByTestId("SF-14-row-grace-demo-erev");
    expect(within(own).getByText("You cannot review your own access.")).toBeTruthy();
    expect(within(own).queryByRole("button", { name: /Certify/ })).toBeNull();

    const maya = within(grid).getByTestId("SF-14-row-maya-demo-erev");
    expect(within(maya).getByText("Revocation requested")).toBeTruthy();
    expect(within(maya).getByRole("button", { name: "Confirm revocation" })).toBeTruthy();
    expect(decisionChip("CERTIFIED")).toBe("Certified");
    expect(decisionChip("REVOKED")).toBe("Revoked");

    const snapshot = screen.getByRole("link", { name: "Download snapshot" });
    expect(snapshot.getAttribute("href")).toBe(
      "/api/v1/files/f1f1f1f1-f1f1-4f1f-8f1f-f1f1f1f1f1f1/content",
    );
    expect(snapshot.hasAttribute("download")).toBe(true);
  });

  // SCREENS_B §9.13 Items: "Last login" is the item's `last_login_at`, "Never" when null. The
  // cell's `render` answered "Never" for null and nothing otherwise, and the grid prints what
  // `render` answers: an item with a sign-in read empty — the datum a reviewer decides keep or
  // revoke by (REQ-CTL-006).
  it("Last login reads the instant of an item's last sign-in, and Never of an item without one", async () => {
    serve(CAMPAIGN, [LENA, { ...MAYA, last_login_at: null }]);
    renderApp(ROUTE, { me: GRACE, screenRoutes: SCREEN_ROUTES });

    const grid = await within(
      await screen.findByTestId("SF-14-grid-access-review-items"),
    ).findByRole("grid", { name: "Items" });
    const lastLogin = async (member: string) =>
      (await within(grid).findByTestId(`SF-14-row-${member}-demo-erev`)).querySelector(
        '[data-column="last_login_at"]',
      )?.textContent;
    expect(await lastLogin("lena")).toBe("12 Sep 2026 09:30 UTC");
    expect(await lastLogin("maya")).toBe("Never");
  });

  it("Complete campaign with pending items shows Decide 2 pending items before completing the campaign.", async () => {
    let completes = 0;
    serve();
    server.use(
      http.post(apiUrl(`/api/v1/access-reviews/${REVIEW_ID}/complete`), () => {
        completes += 1;
        return HttpResponse.json({ ...CAMPAIGN, status: "COMPLETED" });
      }),
    );
    renderApp(ROUTE, { me: GRACE, screenRoutes: SCREEN_ROUTES });
    await screen.findByRole("heading", { level: 1, name: "Q3 2026 access review" });

    fireEvent.click(screen.getAllByRole("button", { name: "Complete campaign" })[0] as HTMLElement);
    const banner = await screen.findByTestId("SF-14-banner-pending-items");
    expect(banner.textContent).toContain("Decide 2 pending items before completing the campaign.");
    expect(screen.queryByRole("dialog", { name: "Complete Q3 2026 access review?" })).toBeNull();
    expect(completes).toBe(0);
  });

  it("Certify and Request revocation send the decisions; Complete campaign confirms when nothing is pending", async () => {
    const decisions: Array<{ readonly url: string; readonly body: unknown }> = [];
    let completes = 0;
    const review = { ...CAMPAIGN, counts: { ...CAMPAIGN.counts, pending: 0 } };
    serve(review, [LENA, MAYA]);
    server.use(
      http.post(
        apiUrl(`/api/v1/access-reviews/${REVIEW_ID}/items/${LENA.id}/decide`),
        async ({ request }) => {
          decisions.push({ url: request.url, body: await request.json() });
          return HttpResponse.json({ ...LENA, decision: "CERTIFIED" });
        },
      ),
      http.post(
        apiUrl(`/api/v1/access-reviews/${REVIEW_ID}/items/${MAYA.id}/confirm-revocation`),
        () => HttpResponse.json({ ...MAYA, decision: "REVOKED" }),
      ),
      http.post(apiUrl(`/api/v1/access-reviews/${REVIEW_ID}/complete`), () => {
        completes += 1;
        return HttpResponse.json({ ...review, status: "COMPLETED" });
      }),
    );
    renderApp(ROUTE, { me: GRACE, screenRoutes: SCREEN_ROUTES });
    const grid = await within(
      await screen.findByTestId("SF-14-grid-access-review-items"),
    ).findByRole("grid", { name: "Items" });
    const lena = await within(grid).findByTestId("SF-14-row-lena-demo-erev");

    fireEvent.click(
      within(lena).getByRole("button", { name: "Request revocation for Lena Fischer" }),
    );
    const revoke = await screen.findByRole("dialog", {
      name: "Request revocation for Lena Fischer?",
    });
    fireEvent.click(within(revoke).getByRole("button", { name: "Request revocation" }));
    expect(await within(revoke).findByText(/at least 10 characters/i)).toBeTruthy();
    fireEvent.change(within(revoke).getByRole("textbox", { name: "Comment (required)" }), {
      target: { value: "Role no longer needed after the team change." },
    });
    fireEvent.click(within(revoke).getByRole("button", { name: "Request revocation" }));
    expect(await screen.findByText("Revocation requested for Lena Fischer.")).toBeTruthy();

    const lenaAgain = await within(grid).findByTestId("SF-14-row-lena-demo-erev");
    fireEvent.click(await within(lenaAgain).findByRole("button", { name: "Certify Lena Fischer" }));
    expect(await screen.findByText("Lena Fischer certified.")).toBeTruthy();
    expect(decisions.map((d) => d.body)).toEqual([
      { decision: "REVOKE_REQUESTED", comment: "Role no longer needed after the team change." },
      { decision: "CERTIFIED" },
    ]);

    // The grid re-renders after each decision, so the row is queried again.
    const maya = await within(grid).findByTestId("SF-14-row-maya-demo-erev");
    fireEvent.click(await within(maya).findByRole("button", { name: "Confirm revocation" }));
    // Confirmations are alertdialogs (components/ui/Modal.tsx, variant "confirmation").
    const confirm = await screen.findByRole("alertdialog", {
      name: "Confirm the revocation for Maya Chen?",
    });
    fireEvent.click(within(confirm).getByRole("button", { name: "Confirm revocation" }));
    expect(await screen.findByText("Revocation for Maya Chen recorded as completed.")).toBeTruthy();

    fireEvent.click(screen.getAllByRole("button", { name: "Complete campaign" })[0] as HTMLElement);
    const complete = await screen.findByRole("alertdialog", {
      name: "Complete Q3 2026 access review?",
    });
    fireEvent.click(within(complete).getByRole("button", { name: "Complete campaign" }));
    expect(await screen.findByText("Q3 2026 access review completed.")).toBeTruthy();
    expect(completes).toBe(1);
  });
});

// docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): the three dialogs of a campaign show
// no message at a field, so the banner says every sentence of a refusal; a sentence of `errors[]` that
// names a member was shown nowhere.
describe("SF-14:access-review, a refused command", () => {
  const SENTENCE = "The campaign changed since this page was read.";
  const review = { ...CAMPAIGN, counts: { ...CAMPAIGN.counts, pending: 0 } };

  async function grid(): Promise<HTMLElement> {
    renderApp(ROUTE, { me: GRACE, screenRoutes: SCREEN_ROUTES });
    return within(await screen.findByTestId("SF-14-grid-access-review-items")).findByRole("grid", {
      name: "Items",
    });
  }

  it("Complete campaign says every sentence of its refusal", async () => {
    serve(review, [LENA, MAYA]);
    server.use(
      http.post(apiUrl(`/api/v1/access-reviews/${REVIEW_ID}/complete`), () =>
        refusedWith({ status: SENTENCE }),
      ),
    );
    await grid();
    fireEvent.click(screen.getAllByRole("button", { name: "Complete campaign" })[0] as HTMLElement);
    const dialog = await screen.findByRole("alertdialog", {
      name: "Complete Q3 2026 access review?",
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Complete campaign" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + SENTENCE + REFUSAL_REFERENCE);
  });

  it("Request revocation says every sentence of its refusal", async () => {
    serve(review, [LENA, MAYA]);
    server.use(
      http.post(apiUrl(`/api/v1/access-reviews/${REVIEW_ID}/items/${LENA.id}/decide`), () =>
        refusedWith({ comment: SENTENCE }),
      ),
    );
    const lena = await within(await grid()).findByTestId("SF-14-row-lena-demo-erev");
    fireEvent.click(
      within(lena).getByRole("button", { name: "Request revocation for Lena Fischer" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Request revocation for Lena Fischer?",
    });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Comment (required)" }), {
      target: { value: "Role no longer needed after the team change." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Request revocation" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + SENTENCE + REFUSAL_REFERENCE);
  });

  it("Confirm revocation says every sentence of its refusal", async () => {
    serve(review, [LENA, MAYA]);
    server.use(
      http.post(
        apiUrl(`/api/v1/access-reviews/${REVIEW_ID}/items/${MAYA.id}/confirm-revocation`),
        () => refusedWith({ decision: SENTENCE }),
      ),
    );
    const maya = await within(await grid()).findByTestId("SF-14-row-maya-demo-erev");
    fireEvent.click(await within(maya).findByRole("button", { name: "Confirm revocation" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Confirm the revocation for Maya Chen?",
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm revocation" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + SENTENCE + REFUSAL_REFERENCE);
  });
});

// W-12e (SCREENS §0.6 SCR-PERM-02 (c); 04 T-PLT-40 as of c028101f): a campaign is read, and acted on,
// by a holder of access.approve for all entities. The page read the campaign before it asked what the
// member holds, and a holder for one entity was shown "Could not load the campaign".
describe("SF-14:access-review, a holder for named entities", () => {
  it("access.approve for one entity alone: the page says that access reviews cover every entity, and no read of the campaign is sent", async () => {
    const asked: string[] = [];
    serve();
    server.use(
      http.get(apiUrl("/api/v1/*"), ({ request }) => {
        asked.push(new URL(request.url).pathname);
      }),
    );
    renderApp(ROUTE, {
      me: signedInMe({
        permissions: ["access.approve"],
        permission_scopes: { "access.approve": ["0a1b2c3d-4e5f-4a6b-8c7d-0000000000de"] },
      }),
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("heading", { name: "You do not have access to Access reviews" }),
    ).toBeTruthy();
    expect(accessDescription()).toBe(
      "Access reviews cover every entity of the workspace. Ask a workspace administrator for a role that includes approving access (access.approve) for all entities.",
    );
    expect(screen.queryByTestId("SF-14-grid-access-review-items")).toBeNull();
    // The access module has read the entities of the workspace by now; a read of the campaign is
    // sent at the first render, before that one is asked.
    await waitFor(() => {
      expect(asked).toContain("/api/v1/entities");
    });
    expect(asked.filter((path) => path.startsWith("/api/v1/access-reviews"))).toEqual([]);
  });

  it("a member without access.approve reads the sentence of a missing permission", async () => {
    serve();
    renderApp(ROUTE, {
      me: signedInMe({ permissions: ["contract.read"] }),
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("heading", { name: "You do not have access to Access reviews" }),
    ).toBeTruthy();
    expect(accessDescription()).toBe(
      "Ask a workspace administrator for a role that includes approving access (access.approve).",
    );
    expect(screen.queryByTestId("SF-14-grid-access-review-items")).toBeNull();
  });
});
