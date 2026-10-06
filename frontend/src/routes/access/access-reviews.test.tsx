// @vitest-environment jsdom
// SF-14:access-reviews (BUILD_SPEC WEB-21; SCREENS_B §9.13; 04 API-R-51 `GET, POST /access-reviews`): the
// grid "Campaigns" shows Name, Status, As of, Reviewers, Members, Decided "<n> of <m>", Revocations
// completed, Started and Completed; the empty state reads "No access reviews yet" with the primary "New
// campaign"; "New campaign" offers only members holding `access.approve` as reviewers.
import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import type { AccessReview } from "../../lib/api/queries/access-reviews";
import type { UserItem } from "../../lib/api/queries/users";
import { accessDescription } from "../../test/access";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, server } from "../../test/msw";
import { describedBy, REFUSAL_REFERENCE, REFUSAL_TITLE, refusedWith } from "../../test/refusals";
import { reviewerCandidates } from "./access-reviews";

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

const GRACE = signedInMe({
  permissions: ["access.approve", "user.manage"],
  user: {
    id: "7a7b7c7d-7e7f-4a7b-8c7d-7e7f7a7b7c7d",
    email: "grace@demo.erev",
    display_name: "Grace Okafor",
    status: "ACTIVE",
  },
});

const ADMIN_ROLE = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  code: "tenant_admin",
  name: "Tenant Admin",
  permissions: ["user.manage", "access.approve"],
};
const ACCOUNTANT_ROLE = {
  id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  code: "revenue_accountant",
  name: "Revenue Accountant",
  permissions: ["contract.read", "contract.create"],
};

function member(id: string, name: string, email: string, roleId: string): UserItem {
  return {
    id,
    user_id: `${id.slice(0, 8)}-1111-4111-8111-111111111111`,
    email,
    display_name: name,
    status: "ACTIVE",
    roles: [
      {
        assignment_id: `${id.slice(0, 8)}-2222-4222-8222-222222222222`,
        role: { id: roleId, code: roleId, name: roleId },
        is_all_entities: true,
        entities: [],
        entity_count: 0,
        status: "ACTIVE",
        granted_at: "2026-09-01T08:00:00Z",
        granted_by: null,
        setup_grant: true,
        approval_request_id: null,
        sod_exception_id: null,
        revoked_at: null,
        revoked_by: null,
      },
    ],
    mfa_enrolled: true,
    sign_in_withheld: false,
    last_login_at: "2026-09-12T09:30:00Z",
    invited_at: "2026-08-30T08:00:00Z",
    invitation_expires_at: null,
    activated_at: "2026-08-30T09:00:00Z",
    removed_at: null,
    row_version: 1,
    created_at: "2026-08-30T08:00:00Z",
    updated_at: "2026-09-12T09:30:00Z",
  };
}

// Distinct from test/app MEMBERSHIP_ID: the signed-in member is preselected as a reviewer.
const TOMAS = member(
  "4b5c6d7e-8f9a-4b2c-8d3e-4f5a6b7c8d9e",
  "Tomás Rivera",
  "tomas@demo.erev",
  ADMIN_ROLE.id,
);
const MAYA = member(
  "9b8a7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d",
  "Maya Chen",
  "maya@demo.erev",
  ACCOUNTANT_ROLE.id,
);

const CAMPAIGN: AccessReview = {
  id: "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1",
  name: "Q3 2026 access review",
  status: "IN_REVIEW",
  as_of: "2026-09-12T20:00:00Z",
  reviewers: [
    {
      membership_id: GRACE.active_membership_id ?? "",
      user_id: GRACE.user.id,
      display_name: "Grace Okafor",
    },
  ],
  counts: { members: 13, certified: 9, revoke_requested: 1, revoked: 1, pending: 2 },
  snapshot_file_id: "f1f1f1f1-f1f1-4f1f-8f1f-f1f1f1f1f1f1",
  started_at: "2026-09-12T20:05:00Z",
  completed_at: null,
  created_by: { id: GRACE.user.id, kind: "USER", display_name: "Grace Okafor" },
  created_at: "2026-09-12T19:55:00Z",
  updated_at: "2026-09-13T10:00:00Z",
  row_version: 3,
};

function serve(campaigns: readonly AccessReview[]) {
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
    http.get(apiUrl("/api/v1/access-reviews"), ({ request }) =>
      HttpResponse.json(
        { items: campaigns, next_cursor: null },
        {
          headers:
            new URL(request.url).searchParams.get("count") === "true"
              ? { "X-Erev-Total-Count": String(campaigns.length) }
              : {},
        },
      ),
    ),
    http.get(apiUrl("/api/v1/users"), () =>
      HttpResponse.json({ items: [TOMAS, MAYA], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/roles"), () =>
      HttpResponse.json({
        items: [ADMIN_ROLE, ACCOUNTANT_ROLE].map((role) => ({
          ...role,
          description: null,
          is_system: true,
          is_active: true,
          member_count: 1,
          content_sha256: "a".repeat(64),
          pending_approval_request_id: null,
          row_version: 1,
          created_at: "2026-09-01T08:00:00Z",
          updated_at: "2026-09-01T08:00:00Z",
        })),
        next_cursor: null,
      }),
    ),
  );
}

describe("SF-14:access-reviews", () => {
  it("the grid Campaigns shows Name, Status, As of, Reviewers, Members, Decided, Revocations completed, Started and Completed", async () => {
    serve([CAMPAIGN]);
    renderApp("/settings/access-reviews", { me: GRACE, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-14-grid-access-reviews")).findByRole(
      "grid",
      { name: "Campaigns" },
    );
    const row = await within(grid).findByRole("row", { name: /Q3 2026 access review/ });
    const headers = within(grid)
      .getAllByRole("columnheader")
      .map((header) => header.textContent?.trim() ?? "");
    for (const name of [
      "Name",
      "Status",
      "As of",
      "Reviewers",
      "Members",
      "Decided",
      "Revocations completed",
      "Started",
      "Completed",
    ]) {
      expect(headers.some((header) => header.startsWith(name))).toBe(true);
    }
    expect(within(row).getByText("In review")).toBeTruthy();
    expect(within(row).getByText("Grace Okafor")).toBeTruthy();
    expect(within(row).getByText("11 of 13")).toBeTruthy();
    expect(
      within(row).getByRole("link", { name: "Q3 2026 access review" }).getAttribute("href"),
    ).toBe(`/settings/access-reviews/${CAMPAIGN.id}`);
  });

  it("reads the campaigns by the sort keys API-R-51 admits: id by default, then as_of and name", async () => {
    // 04 API-C-09: a key the route does not list answers 422 and the page cannot load (Q-30).
    const sorts: (string | null)[] = [];
    serve([CAMPAIGN]);
    server.use(
      http.get(apiUrl("/api/v1/access-reviews"), ({ request }) => {
        const search = new URL(request.url).searchParams;
        sorts.push(search.get("sort"));
        return ["-id", "as_of", "-as_of", "name"].includes(search.get("sort") ?? "")
          ? HttpResponse.json(
              { items: [CAMPAIGN], next_cursor: null },
              { headers: { "X-Erev-Total-Count": "1" } },
            )
          : HttpResponse.json(
              {
                type: "https://erev.dev/problems/validation-failed",
                title: "Validation failed",
                status: 422,
                errors: [
                  {
                    field: "sort",
                    rule_id: "API-C-09",
                    message: "Sort by one of as_of, id, name.",
                  },
                ],
              },
              { status: 422, headers: { "Content-Type": "application/problem+json" } },
            );
      }),
    );
    renderApp("/settings/access-reviews", { me: GRACE, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-14-grid-access-reviews")).findByRole(
      "grid",
      { name: "Campaigns" },
    );
    await within(grid).findByRole("row", { name: /Q3 2026 access review/ });
    expect(sorts).toEqual(["-id"]);

    const press = (header: HTMLElement) => {
      // DS-CMP-10: Enter on a focused header cycles the server-side sort.
      fireEvent.mouseDown(header);
      act(() => header.focus());
      fireEvent.keyDown(header, { key: "Enter" });
    };
    const asOf = within(grid).getByRole("columnheader", { name: /^As of/ });
    press(asOf);
    await waitFor(() => expect(sorts).toEqual(["-id", "as_of"]));
    press(asOf);
    await waitFor(() => expect(sorts).toEqual(["-id", "as_of", "-as_of"]));
    press(within(grid).getByRole("columnheader", { name: /^Name/ }));
    await waitFor(() => expect(sorts).toEqual(["-id", "as_of", "-as_of", "name"]));
    // No other header sorts: the route lists no other key.
    expect(
      within(grid)
        .getAllByRole("columnheader")
        .filter((header) => header.hasAttribute("aria-sort"))
        .map((header) => header.textContent?.trim()),
    ).toEqual(["Name", "As of"]);
    expect(await within(grid).findByRole("row", { name: /Q3 2026 access review/ })).toBeTruthy();
    expect(screen.queryByText("Could not load the campaigns")).toBeNull();
  });

  it("the empty state reads No access reviews yet with the primary New campaign", async () => {
    serve([]);
    renderApp("/settings/access-reviews", { me: GRACE, screenRoutes: SCREEN_ROUTES });
    const empty = await screen.findByTestId("SF-14-empty-access-reviews");
    expect(within(empty).getByRole("heading", { name: "No access reviews yet" })).toBeTruthy();
    expect(
      within(empty).getByText(
        "A campaign snapshots every membership and its roles so reviewers can certify or revoke access.",
      ),
    ).toBeTruthy();
    expect(within(empty).getByRole("button", { name: "New campaign" })).toBeTruthy();
  });

  it("New campaign offers only members holding access.approve as reviewers and posts the campaign", async () => {
    const bodies: unknown[] = [];
    serve([]);
    server.use(
      http.post(apiUrl("/api/v1/access-reviews"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(
          { ...CAMPAIGN, status: "DRAFT", started_at: null },
          { status: 201 },
        );
      }),
      http.get(apiUrl(`/api/v1/access-reviews/${CAMPAIGN.id}`), () =>
        HttpResponse.json({ ...CAMPAIGN, status: "DRAFT", started_at: null }),
      ),
      http.get(apiUrl(`/api/v1/access-reviews/${CAMPAIGN.id}/items`), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
    const { router } = renderApp("/settings/access-reviews", {
      me: GRACE,
      screenRoutes: SCREEN_ROUTES,
    });
    await screen.findByTestId("SF-14-empty-access-reviews");
    fireEvent.click(screen.getAllByRole("button", { name: "New campaign" })[0] as HTMLElement);

    const dialog = await screen.findByRole("dialog", { name: "New campaign" });
    fireEvent.change(within(dialog).getByLabelText("Name"), {
      target: { value: "Q3 2026 access review" },
    });
    const asOf = within(dialog).getByLabelText("As of");
    fireEvent.change(asOf, { target: { value: "2026-09-12" } });
    fireEvent.blur(asOf);
    fireEvent.change(within(dialog).getByLabelText("Time (UTC)"), { target: { value: "20:00" } });
    const reviewers = within(dialog).getByRole("combobox", { name: "Reviewers" });
    // The multi-select lists the matches of the typed text (DS-CMP-21).
    fireEvent.change(reviewers, { target: { value: "Tom" } });
    expect(
      await screen.findByRole("option", { name: "Tomás Rivera · tomas@demo.erev" }),
    ).toBeTruthy();
    fireEvent.change(reviewers, { target: { value: "Maya" } });
    expect(screen.queryByRole("option", { name: "Maya Chen · maya@demo.erev" })).toBeNull();
    fireEvent.change(reviewers, { target: { value: "Tom" } });
    fireEvent.mouseDown(screen.getByRole("option", { name: "Tomás Rivera · tomas@demo.erev" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Create campaign" }));
    expect(await screen.findByText(/Campaign Q3 2026 access review created/)).toBeTruthy();
    expect(bodies).toEqual([
      {
        name: "Q3 2026 access review",
        as_of: "2026-09-12T20:00:00Z",
        reviewer_membership_ids: [GRACE.active_membership_id, TOMAS.id],
      },
    ]);
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/settings/access-reviews/${CAMPAIGN.id}`),
    );
    expect(
      reviewerCandidates([TOMAS, MAYA], [ADMIN_ROLE, ACCOUNTANT_ROLE]).map((u) => u.id),
    ).toEqual([TOMAS.id]);
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): a message for a member the form
  // has no field for was shown nowhere; one for a field stands there and is not said by the banner.
  it("New campaign under a refused command: the banner lists what no field shows", async () => {
    const noField = "A campaign of this workspace is still in progress.";
    const atName = "Use a name no other campaign has.";
    serve([]);
    server.use(
      http.post(apiUrl("/api/v1/access-reviews"), () =>
        refusedWith({ status: noField, name: atName }),
      ),
    );
    renderApp("/settings/access-reviews", { me: GRACE, screenRoutes: SCREEN_ROUTES });
    await screen.findByTestId("SF-14-empty-access-reviews");
    fireEvent.click(screen.getAllByRole("button", { name: "New campaign" })[0] as HTMLElement);

    const dialog = await screen.findByRole("dialog", { name: "New campaign" });
    const name = within(dialog).getByLabelText("Name");
    fireEvent.change(name, { target: { value: "Q3 2026 access review" } });
    const asOf = within(dialog).getByLabelText("As of");
    fireEvent.change(asOf, { target: { value: "2026-09-12" } });
    fireEvent.blur(asOf);
    fireEvent.click(within(dialog).getByRole("button", { name: "Create campaign" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + noField + REFUSAL_REFERENCE);
    expect(describedBy(name)).toContain(atName);
  });
});

// W-12e (SCREENS §0.6 SCR-PERM-02 (c); 04 T-PLT-40, API-R-51 as of c028101f): a campaign reviews the
// members of the whole workspace, so every route of it asks access.approve for all entities. A holder
// for one entity was shown the grid and "New campaign" while the API refused the list and the command.
describe("SF-14:access-reviews, a holder for named entities", () => {
  it("access.approve for one entity alone: the page says that access reviews cover every entity, and asks for no campaign", async () => {
    const asked: string[] = [];
    serve([CAMPAIGN]);
    server.use(
      http.get(apiUrl("/api/v1/*"), ({ request }) => {
        asked.push(new URL(request.url).pathname);
      }),
    );
    renderApp("/settings/access-reviews", {
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
    expect(screen.queryByRole("button", { name: "New campaign" })).toBeNull();
    // The access module has read the entities of the workspace by now (src/lib/access.ts); a read
    // of the campaigns would have been sent before that one was answered.
    await waitFor(() => {
      expect(asked).toContain("/api/v1/entities");
    });
    expect(asked.filter((path) => path.startsWith("/api/v1/access-reviews"))).toEqual([]);
  });

  it("a member without access.approve reads the sentence of a missing permission", async () => {
    serve([CAMPAIGN]);
    renderApp("/settings/access-reviews", {
      me: signedInMe({ permissions: ["contract.read"] }),
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("heading", { name: "You do not have access to Access reviews" }),
    ).toBeTruthy();
    expect(accessDescription()).toBe(
      "Ask a workspace administrator for a role that includes approving access (access.approve).",
    );
  });

  // The API takes as a reviewer a holder of access.approve for all entities by a role of their own
  // and answers 422 on another (04 T-PLT-40): the list offers no member it would refuse.
  it("New campaign offers no reviewer whose role holds access.approve for named entities only", async () => {
    const base = member(
      "6c7d8e9f-0a1b-4c2d-8e3f-5a6b7c8d9e0f",
      "Lena Fischer",
      "lena@demo.erev",
      ADMIN_ROLE.id,
    );
    const lena: UserItem = {
      ...base,
      roles: base.roles.map((role) => ({
        ...role,
        is_all_entities: false,
        entities: [
          { id: "0a1b2c3d-4e5f-4a6b-8c7d-0000000000de", code: "AVM-DE", name: "Avenmoor GmbH" },
        ],
        entity_count: 1,
      })),
    };
    serve([]);
    server.use(
      http.get(apiUrl("/api/v1/users"), () =>
        HttpResponse.json({ items: [TOMAS, lena, MAYA], next_cursor: null }),
      ),
    );
    renderApp("/settings/access-reviews", { me: GRACE, screenRoutes: SCREEN_ROUTES });
    await screen.findByText("No access reviews yet");
    fireEvent.click(screen.getAllByRole("button", { name: "New campaign" })[0] as HTMLElement);

    const dialog = await screen.findByRole("dialog", { name: "New campaign" });
    const reviewers = within(dialog).getByRole("combobox", { name: "Reviewers" });
    fireEvent.change(reviewers, { target: { value: "Tom" } });
    expect(
      await screen.findByRole("option", { name: "Tomás Rivera · tomas@demo.erev" }),
    ).toBeTruthy();
    fireEvent.change(reviewers, { target: { value: "Lena" } });
    expect(screen.queryByRole("option", { name: "Lena Fischer · lena@demo.erev" })).toBeNull();
    expect(
      reviewerCandidates([TOMAS, lena, MAYA], [ADMIN_ROLE, ACCOUNTANT_ROLE]).map((u) => u.id),
    ).toEqual([TOMAS.id]);
  });
});
