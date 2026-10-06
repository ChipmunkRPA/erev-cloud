// @vitest-environment jsdom
// SF-14 (BUILD_SPEC WEB-19; SCREENS_B §9.10; 04 API-R-05 `GET /users`, `POST /users`; PRD ERR-22,
// BR-PLT-02; BS1-D-14): the grid "Members" binds `GET /users?status&q&count=true` with the §9.10 columns;
// "Invite user" opens the drawer with Email, Display name and repeatable Role and Scope rows; the live
// SoD check shows the ERR-22 alert with focus on "Request an exception"; the toast names the outcome
// (AUTO-BOOTSTRAP while setup is incomplete, else waiting for approval); "Download access listing" is
// not rendered.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import type { Role, SodRule } from "../../lib/api/queries/roles";
import type { UserItem } from "../../lib/api/queries/users";
import { installMemoryStorage, renderApp, signedInMe, signedInSession } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { describedBy, REFUSAL_REFERENCE, REFUSAL_TITLE, refusedWith } from "../../test/refusals";
import { memberScope, userQuery, userFilterFields } from "./users";

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

/** An API-S-Entity as the shell's context pill and the scope multi-select read it. */
function entity(id: string, code: string, name: string): Record<string, unknown> {
  return {
    id,
    code,
    name,
    functional_currency: "EUR",
    time_zone: "Europe/Berlin",
    calendar_id: "0c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e4f",
    parent_entity_id: null,
    country_code: "DE",
    tax_id: null,
    is_active: true,
    books: [],
    row_version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

const TOMAS = signedInMe({ permissions: ["user.manage", "role.manage", "config.read"] });
const DE_ID = "7e6f5a4b-3c2d-4e1f-8a9b-0c1d2e3f4a5b";
/** An administrator of AVM-DE alone (04 T-PLT-10: nobody grants beyond their own access). */
const ADMIN_OF_DE = signedInMe({
  permissions: ["user.manage", "role.manage", "config.read"],
  permission_scopes: { "user.manage": [DE_ID], "role.manage": [DE_ID], "config.read": "*" },
});

const ACCOUNTANT: Role = {
  id: "11111111-1111-4111-8111-111111111111",
  code: "revenue_accountant",
  name: "Revenue Accountant",
  description: null,
  is_system: true,
  is_active: true,
  permissions: ["contract.read", "contract.create"],
  member_count: 3,
  content_sha256: "a".repeat(64),
  pending_approval_request_id: null,
  row_version: 1,
  created_at: "2026-09-01T08:00:00Z",
  updated_at: "2026-09-01T08:00:00Z",
};

const REVIEWER: Role = {
  ...ACCOUNTANT,
  id: "22222222-2222-4222-8222-222222222222",
  code: "revenue_reviewer",
  name: "Revenue Reviewer",
  permissions: ["contract.read", "contract.approve"],
  member_count: 1,
};

const SOD_3: SodRule = {
  id: "33333333-3333-4333-8333-333333333333",
  code: "SoD-3",
  name: "Revenue Accountant with Revenue Reviewer lets one person create and approve the same contract or modification",
  rationale: "Maker and checker of the same contract.",
  function_a_permissions: ["contract.create"],
  function_b_permissions: ["contract.approve"],
  version_no: 1,
  status: "PUBLISHED",
  published_at: "2026-09-01T08:00:00Z",
  published_by: null,
  effective_from: null,
  effective_to: null,
  supersedes_version_id: null,
  approval_request_id: null,
  pending_approval_request_id: null,
  content_sha256: null,
  row_version: 1,
  created_at: "2026-09-01T08:00:00Z",
  updated_at: "2026-09-01T08:00:00Z",
};

const SOD_COPY =
  "Separation of duties conflict SoD-3: Revenue Accountant with Revenue Reviewer lets one person create and approve the same contract or modification.";

function member(overrides: Partial<UserItem> = {}): UserItem {
  return {
    id: "3a4b5c6d-7e8f-4a1b-9c2d-3e4f5a6b7c8d",
    user_id: "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a",
    email: "maya@demo.erev",
    display_name: "Maya Chen",
    status: "ACTIVE",
    roles: [
      {
        assignment_id: "44444444-4444-4444-8444-444444444444",
        role: { id: ACCOUNTANT.id, code: ACCOUNTANT.code, name: ACCOUNTANT.name },
        is_all_entities: true,
        entities: [],
        entity_count: 0,
        status: "ACTIVE",
        granted_at: "2026-09-01T08:00:00Z",
        granted_by: { id: null, kind: "SYSTEM", display_name: "System" },
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
    row_version: 3,
    created_at: "2026-08-30T08:00:00Z",
    updated_at: "2026-09-12T09:30:00Z",
    ...overrides,
  };
}

const LENA = member({
  id: "9b8a7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d",
  user_id: "6d2e9b8f-3c5a-4d7e-8f9a-0b1c2d3e4f5a",
  email: "lena@demo.erev",
  display_name: "Lena Fischer",
  status: "INVITED",
  roles: [
    {
      assignment_id: null,
      role: { id: REVIEWER.id, code: REVIEWER.code, name: REVIEWER.name },
      is_all_entities: false,
      entities: [
        { id: "7e6f5a4b-3c2d-4e1f-8a9b-0c1d2e3f4a5b", code: "AVM-DE", name: "Avenmoor GmbH" },
      ],
      entity_count: 1,
      status: "REQUESTED",
      granted_at: null,
      granted_by: null,
      setup_grant: false,
      approval_request_id: "8f7e6d5c-4b3a-4c2d-9e1f-0a9b8c7d6e5f",
      sod_exception_id: null,
      revoked_at: null,
      revoked_by: null,
    },
  ],
  // An invited member: the two facts of the person are not shown (04 T-PLT-02 rev 1.316).
  mfa_enrolled: null,
  sign_in_withheld: true,
  last_login_at: null,
  activated_at: null,
});

/** The shell's reads and the screen's reads; each `GET /users` search is recorded. */
function serve(searches: string[], users: readonly UserItem[] = [member(), LENA]) {
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), () =>
      HttpResponse.json({
        items: [
          entity(DE_ID, "AVM-DE", "Avenmoor GmbH"),
          entity("1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d", "AVM-US", "Avenmoor Inc"),
        ],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/books"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/periods"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/saved-views"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/roles"), () =>
      HttpResponse.json({ items: [ACCOUNTANT, REVIEWER], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/sod-rules"), () =>
      HttpResponse.json({ items: [SOD_3], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/users"), ({ request }) => {
      const url = new URL(request.url);
      searches.push(url.search);
      const counting = url.searchParams.get("count") === "true";
      return HttpResponse.json(
        { items: users, next_cursor: null },
        { headers: counting ? { "X-Erev-Total-Count": String(users.length) } : {} },
      );
    }),
  );
}

function bindings(searches: readonly string[]): string[] {
  return searches.map((search) => {
    const params = new URLSearchParams(search);
    params.delete("limit");
    params.delete("cursor");
    params.delete("count");
    return params.toString();
  });
}

async function openInvite(): Promise<HTMLElement> {
  fireEvent.click(await screen.findByRole("button", { name: "Invite user" }));
  return screen.findByRole("dialog", { name: "Invite user" });
}

function chooseRole(dialog: HTMLElement, position: number, roleName: string): void {
  const row = within(dialog).getByRole("group", { name: `Role ${String(position)}` });
  fireEvent.click(within(row).getByRole("combobox", { name: "Role" }));
  // Listbox options are picked on mousedown (components/form/Listbox.tsx).
  fireEvent.mouseDown(screen.getByRole("option", { name: roleName }));
}

describe("SF-14", () => {
  it("the grid Members binds GET /users?status&q&count=true with the §9.10 columns", async () => {
    const searches: string[] = [];
    serve(searches);
    renderApp("/settings/users?f.status=is:INVITED&q=lena", {
      me: TOMAS,
      screenRoutes: SCREEN_ROUTES,
    });

    const grid = await within(await screen.findByTestId("SF-14-grid-members")).findByRole("grid", {
      name: "Members",
    });
    expect(await within(grid).findByRole("rowheader", { name: "Lena Fischer" })).toBeTruthy();
    expect(screen.getByTestId("SF-14-row-lena-demo-erev")).toBeTruthy();
    const headers = within(grid)
      .getAllByRole("columnheader")
      .map((header) => header.textContent?.trim());
    for (const name of [
      "Name",
      "Email",
      "Status",
      "Roles",
      "Scope",
      "MFA",
      "Last login",
      "Invited",
    ]) {
      expect(headers.some((header) => header?.startsWith(name))).toBe(true);
    }
    await waitFor(() => {
      expect(searches.length).toBeGreaterThan(0);
    });
    expect(new URLSearchParams(searches[0] ?? "").get("count")).toBe("true");
    expect(bindings(searches)[0]).toBe("status=INVITED&q=lena&sort=display_name");
    expect(within(grid).getByText("Pending approval")).toBeTruthy();
    // Lena is invited: her MFA state and last sign-in are not shown (SCREENS_B §9.10 rev 1.105),
    // where the cell read "Never"; "Never" is a member's cell, in the next test.
    expect(within(grid).getAllByText("Not shown")).toHaveLength(2);
    expect(within(grid).queryByText("Never")).toBeNull();
    expect(screen.getByRole("heading", { level: 1, name: "Users" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Download access listing" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Download access listing" })).toBeNull();
  });

  it("MFA and Last login say what the API answers of a member, and Not shown of an invited or a removed one", async () => {
    // SCREENS_B §9.10 rev 1.105 (04 T-PLT-02 rev 1.316): for an invited or a removed member
    // API-S-User answers `sign_in_withheld` and null in both members — the cells read "Not shown",
    // never "No" or "Never", which say of a member that there is no factor and no sign-in.
    const other = (name: string, overrides: Partial<UserItem>): UserItem =>
      member({
        id: `${name === "otto" ? "1" : "2"}a4b5c6d-7e8f-4a1b-9c2d-3e4f5a6b7c8d`,
        user_id: `${name === "otto" ? "1" : "2"}c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a`,
        email: `${name}@demo.erev`,
        ...overrides,
      });
    serve(
      [],
      [
        member(),
        other("otto", { display_name: "Otto Brandt", mfa_enrolled: false, last_login_at: null }),
        LENA,
        other("nikhil", {
          display_name: "nikhil@demo.erev",
          status: "REMOVED",
          removed_at: "2026-09-13T08:00:00Z",
          mfa_enrolled: null,
          sign_in_withheld: true,
          last_login_at: null,
        }),
      ],
    );
    renderApp("/settings/users", { me: TOMAS, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-14-grid-members")).findByRole("grid", {
      name: "Members",
    });
    await within(grid).findByRole("rowheader", { name: "Maya Chen" });
    const cells = (email: string) => {
      const row = screen.getByTestId(`SF-14-row-${email}-demo-erev`);
      return ["mfa", "last_login_at"].map((column) =>
        row.querySelector(`[data-column="${column}"]`)?.textContent.trim(),
      );
    };
    expect(cells("maya")).toEqual(["Yes", "12 Sep 2026 09:30 UTC"]);
    expect(cells("otto")).toEqual(["No", "Never"]);
    expect(cells("lena")).toEqual(["Not shown", "Not shown"]);
    expect(cells("nikhil")).toEqual(["Not shown", "Not shown"]);
  });

  it("Invite user opens the drawer with Email, Display name and repeatable Role and Scope rows", async () => {
    serve([]);
    renderApp("/settings/users", { me: TOMAS, screenRoutes: SCREEN_ROUTES });

    const dialog = await openInvite();
    expect(within(dialog).getByTestId("SF-14-drawer-invite")).toBeTruthy();
    expect(within(dialog).getByLabelText("Email")).toBeTruthy();
    expect(within(dialog).getByLabelText("Display name")).toBeTruthy();
    expect(within(dialog).getAllByRole("combobox", { name: "Role" })).toHaveLength(1);
    expect(within(dialog).getByRole("radio", { name: "All entities" })).toBeTruthy();
    expect(within(dialog).getByRole("radio", { name: "Selected entities" })).toBeTruthy();

    fireEvent.click(within(dialog).getByRole("button", { name: "Add another role" }));
    expect(within(dialog).getAllByRole("combobox", { name: "Role" })).toHaveLength(2);
    expect(within(dialog).getByRole("button", { name: "Remove role 2" })).toBeTruthy();

    fireEvent.click(within(dialog).getByRole("button", { name: "Send invitation" }));
    expect(await within(dialog).findByText("Enter the email address.")).toBeTruthy();
    expect(within(dialog).getAllByText("Choose a role.")).toHaveLength(2);
  });

  it("Invite user names the workspace the session is in, among a workspace and its copy of one membership id", async () => {
    // A sandbox copy keeps the ids of the rows it copies (SCREENS_B §9.7 "The open workspace"):
    // GET /me lists the source first, with the same membership id as the copy.
    const source = TOMAS.memberships[0];
    if (source === undefined) {
      throw new Error("no membership");
    }
    const COPY_ID = "1c1c1c1c-1c1c-4c1c-8c1c-1c1c1c1c1c1c";
    const me = {
      ...TOMAS,
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
    serve([]);
    renderApp("/settings/users", { me, screenRoutes: SCREEN_ROUTES });
    let dialog = await openInvite();
    expect(within(dialog).getByText(source.tenant.display_name)).toBeTruthy();
    expect(within(dialog).queryByText("Avenmoor rehearsal")).toBeNull();
    cleanup();

    serve([]);
    renderApp("/settings/users", {
      me,
      session: signedInSession({
        active_tenant: {
          id: COPY_ID,
          code: "sbx-avenmoor-rehearsal",
          display_name: "Avenmoor rehearsal",
          kind: "sandbox",
        },
      }),
      screenRoutes: SCREEN_ROUTES,
    });
    dialog = await openInvite();
    expect(within(dialog).getByText("Avenmoor rehearsal")).toBeTruthy();
    expect(within(dialog).queryByText(source.tenant.display_name)).toBeNull();
  });

  it("a live SoD check shows the SoD-3 alert with focus on Request an exception", async () => {
    serve([]);
    renderApp("/settings/users", { me: TOMAS, screenRoutes: SCREEN_ROUTES });

    const dialog = await openInvite();
    await within(dialog).findByRole("combobox", { name: "Role" });
    chooseRole(dialog, 1, "Revenue Accountant");
    expect(screen.queryByTestId("SF-14-banner-sod-conflict")).toBeNull();
    fireEvent.click(within(dialog).getByRole("button", { name: "Add another role" }));
    chooseRole(dialog, 2, "Revenue Reviewer");

    const banner = await screen.findByTestId("SF-14-banner-sod-conflict");
    const alert = within(banner).getByRole("alert");
    expect(within(alert).getByRole("heading").textContent).toBe(SOD_COPY);
    const action = within(alert).getByRole("button", { name: "Request an exception" });
    await waitFor(() => {
      expect(document.activeElement).toBe(action);
    });
    fireEvent.click(action);
    expect(
      await screen.findByText(
        "Send the invitation without the conflicting role, then request the exception from the member's page.",
      ),
    ).toBeTruthy();
  });

  it("the toast reads the AUTO-BOOTSTRAP copy while setup is incomplete, else waiting for approval", async () => {
    const bodies: unknown[] = [];
    serve([]);
    let answer: UserItem = member({
      id: "9b8a7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d",
      email: "lena@demo.erev",
      display_name: "Lena Fischer",
      status: "INVITED",
    });
    server.use(
      http.post(apiUrl("/api/v1/users"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(answer, { status: 201 });
      }),
    );
    renderApp("/settings/users", { me: TOMAS, screenRoutes: SCREEN_ROUTES });

    let dialog = await openInvite();
    await within(dialog).findByRole("combobox", { name: "Role" });
    fireEvent.change(within(dialog).getByLabelText("Email"), {
      target: { value: "lena@demo.erev" },
    });
    fireEvent.change(within(dialog).getByLabelText("Display name"), {
      target: { value: "Lena Fischer" },
    });
    chooseRole(dialog, 1, "Revenue Reviewer");
    fireEvent.click(within(dialog).getByRole("radio", { name: "Selected entities" }));
    // The multi-select lists the matches of the typed text (DS-CMP-21).
    fireEvent.change(within(dialog).getByRole("combobox", { name: "Entities" }), {
      target: { value: "AVM-DE" },
    });
    fireEvent.mouseDown(screen.getByRole("option", { name: "AVM-DE · Avenmoor GmbH" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Send invitation" }));

    expect(
      await screen.findByText("Invitation sent. Setup grants are approved by rule AUTO-BOOTSTRAP."),
    ).toBeTruthy();
    expect(bodies).toEqual([
      {
        email: "lena@demo.erev",
        display_name: "Lena Fischer",
        roles: [{ role_id: REVIEWER.id, is_all_entities: false, entity_codes: ["AVM-DE"] }],
      },
    ]);

    answer = LENA;
    dialog = await openInvite();
    await within(dialog).findByRole("combobox", { name: "Role" });
    fireEvent.change(within(dialog).getByLabelText("Email"), {
      target: { value: "lena@demo.erev" },
    });
    fireEvent.change(within(dialog).getByLabelText("Display name"), {
      target: { value: "Lena Fischer" },
    });
    chooseRole(dialog, 1, "Revenue Reviewer");
    fireEvent.click(within(dialog).getByRole("button", { name: "Send invitation" }));
    expect(
      await screen.findByText("Invitation for lena@demo.erev is waiting for approval."),
    ).toBeTruthy();
  });

  it("a grantor of named entities is offered those entities and not all entities", async () => {
    // SCREENS_B §9.10 rev 1.60: the scope field offers what the grantor's own user.manage covers.
    // Before, it offered every entity and "All entities", and the API refused the grant (422).
    const bodies: unknown[] = [];
    serve([]);
    server.use(
      http.post(apiUrl("/api/v1/users"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(LENA, { status: 201 });
      }),
    );
    renderApp("/settings/users", { me: ADMIN_OF_DE, screenRoutes: SCREEN_ROUTES });

    const dialog = await openInvite();
    await within(dialog).findByRole("combobox", { name: "Role" });
    expect(within(dialog).queryByRole("radio", { name: "All entities" })).toBeNull();
    expect(
      within(dialog).getByRole<HTMLInputElement>("radio", { name: "Selected entities" }).checked,
    ).toBe(true);
    expect(
      within(dialog).getByText(
        "Your own access covers named entities only. Choose from those entities, not all entities.",
      ),
    ).toBeTruthy();
    // The multi-select holds the grantor's entity alone.
    const entities = within(dialog).getByRole("combobox", { name: "Entities" });
    fireEvent.change(entities, { target: { value: "AVM" } });
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual([
      "AVM-DE · Avenmoor GmbH",
    ]);
    fireEvent.mouseDown(screen.getByRole("option", { name: "AVM-DE · Avenmoor GmbH" }));

    fireEvent.change(within(dialog).getByLabelText("Email"), {
      target: { value: "lena@demo.erev" },
    });
    fireEvent.change(within(dialog).getByLabelText("Display name"), {
      target: { value: "Lena Fischer" },
    });
    chooseRole(dialog, 1, "Revenue Reviewer");
    fireEvent.click(within(dialog).getByRole("button", { name: "Send invitation" }));
    await waitFor(() => {
      expect(bodies).toEqual([
        {
          email: "lena@demo.erev",
          display_name: "Lena Fischer",
          roles: [{ role_id: REVIEWER.id, is_all_entities: false, entity_codes: ["AVM-DE"] }],
        },
      ]);
    });
  });

  it("a finding of the API on a scope is shown under the scope field of its row", async () => {
    // 04 T-PLT-10: `roles[<n>].entity_codes` and `roles[<n>].is_all_entities` (422).
    serve([]);
    server.use(
      http.post(apiUrl("/api/v1/users"), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            {
              field: "roles[1].entity_codes",
              sheet: null,
              row: null,
              rule_id: "EREV-REF-002",
              message: "Choose entities that exist in this workspace.",
            },
            {
              field: "roles[0].is_all_entities",
              sheet: null,
              row: null,
              rule_id: "T-PLT-10",
              message:
                "Your own access covers named entities only. Choose from those entities, not all entities.",
            },
          ],
        }),
      ),
    );
    renderApp("/settings/users", { me: TOMAS, screenRoutes: SCREEN_ROUTES });

    const dialog = await openInvite();
    await within(dialog).findByRole("combobox", { name: "Role" });
    fireEvent.change(within(dialog).getByLabelText("Email"), {
      target: { value: "lena@demo.erev" },
    });
    fireEvent.change(within(dialog).getByLabelText("Display name"), {
      target: { value: "Lena Fischer" },
    });
    chooseRole(dialog, 1, "Revenue Accountant");
    fireEvent.click(within(dialog).getByRole("button", { name: "Add another role" }));
    chooseRole(dialog, 2, "Revenue Reviewer");
    const second = within(dialog).getByRole("group", { name: "Role 2" });
    fireEvent.click(within(second).getByRole("radio", { name: "Selected entities" }));
    fireEvent.change(within(second).getByRole("combobox", { name: "Entities" }), {
      target: { value: "AVM-DE" },
    });
    fireEvent.mouseDown(screen.getByRole("option", { name: "AVM-DE · Avenmoor GmbH" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Send invitation" }));

    expect(
      await within(second).findByText("Choose entities that exist in this workspace."),
    ).toBeTruthy();
    const first = within(dialog).getByRole("group", { name: "Role 1" });
    expect(
      within(first).getByText(
        "Your own access covers named entities only. Choose from those entities, not all entities.",
      ),
    ).toBeTruthy();
    expect(within(first).queryByText("Choose entities that exist in this workspace.")).toBeNull();
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): a message that names a member the
  // drawer shows no message of was shown nowhere. The banner lists it, and what a field or a row shows
  // is not said again. The validation of the request writes a row as `roles.<n>.`.
  it("Invite user under a refused command: the banner lists what no field and no row shows", async () => {
    const noField = "This role is waiting for approval and cannot be granted yet.";
    const atEmail = "A member with this email exists in this workspace.";
    const finding = "Choose entities that exist in this workspace.";
    serve([]);
    server.use(
      http.post(apiUrl("/api/v1/users"), () =>
        refusedWith({
          "roles.0.role_id": noField,
          email: atEmail,
          "roles.0.entity_codes": finding,
        }),
      ),
    );
    renderApp("/settings/users", { me: TOMAS, screenRoutes: SCREEN_ROUTES });

    const dialog = await openInvite();
    await within(dialog).findByRole("combobox", { name: "Role" });
    const email = within(dialog).getByLabelText("Email");
    fireEvent.change(email, { target: { value: "lena@demo.erev" } });
    fireEvent.change(within(dialog).getByLabelText("Display name"), {
      target: { value: "Lena Fischer" },
    });
    chooseRole(dialog, 1, "Revenue Accountant");
    fireEvent.click(within(dialog).getByRole("button", { name: "Send invitation" }));

    // The row is for all entities, so its entities are not on screen: that finding is the banner's.
    const heading = await within(dialog).findByRole("heading", { name: REFUSAL_TITLE });
    expect(heading.closest("div")?.textContent).toBe(
      REFUSAL_TITLE + noField + finding + REFUSAL_REFERENCE,
    );
    expect(describedBy(email)).toContain(atEmail);
  });

  it("a member without user.manage sees the access-limited state", async () => {
    serve([]);
    renderApp("/settings/users", {
      me: signedInMe({ permissions: ["contract.read"] }),
      screenRoutes: SCREEN_ROUTES,
    });
    expect(
      await screen.findByRole("heading", { name: "You do not have access to Users" }),
    ).toBeTruthy();
  });

  it("filter helpers: the URL chips and the member scope", () => {
    const fields = userFilterFields();
    expect(userQuery("?f.status=in:INVITED,ACTIVE&q=maya", fields)).toEqual({
      status: ["INVITED", "ACTIVE"],
      q: "maya",
    });
    expect(userQuery("", fields)).toEqual({ status: [], q: null });
    expect(memberScope(member())).toBe("All entities");
    expect(memberScope(LENA)).toBe("AVM-DE");
    expect(memberScope(member({ roles: [] }))).toBe("—");
  });
});
