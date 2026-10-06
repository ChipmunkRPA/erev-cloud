// @vitest-environment jsdom
// SF-14:user (BUILD_SPEC WEB-19; SCREENS_B §9.10; SCREENS §0.4 SMAP-14, SB-R-05, SCR-PERM-05; 04 API-R-05
// `GET /users/{id}`, `/suspend`, `/reset-mfa`; API-R-06 `POST /role-assignments`; API-R-07
// `POST /sod-exceptions`; PRD ERR-22): the table "Roles" shows "Setup grant" for AUTO-BOOTSTRAP grants;
// "Suspend" requires a reason and states its consequence; "Reset MFA" needs the step-up and states its
// consequence; a suspended membership shows the warning banner; "Request an exception" opens "Request SoD
// exception" with "Valid to" limited to 366 days.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import type { Role, SodRule } from "../../lib/api/queries/roles";
import type { UserItem } from "../../lib/api/queries/users";
import { installMemoryStorage, renderApp, signedInMe, signedInSession } from "../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { describedBy, REFUSAL_REFERENCE, REFUSAL_TITLE, refusedWith } from "../../test/refusals";
import { assignmentChip } from "./user";

installMswServer();
installMemoryStorage();

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

const TOMAS = signedInMe({ permissions: ["user.manage", "role.manage"] });
const DE_ID = "7e6f5a4b-3c2d-4e1f-8a9b-0c1d2e3f4a5b";
const US_ID = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d";
/** An administrator whose two permissions are held for the named entities alone (04 T-PLT-10). */
function adminOf(...entities: readonly string[]) {
  return signedInMe({
    permissions: ["user.manage", "role.manage"],
    permission_scopes: { "user.manage": [...entities], "role.manage": [...entities] },
  });
}
const MEMBERSHIP = "9b8a7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d";
const ROUTE = `/settings/users/${MEMBERSHIP}`;

const REVIEWER: Role = {
  id: "22222222-2222-4222-8222-222222222222",
  code: "revenue_reviewer",
  name: "Revenue Reviewer",
  description: null,
  is_system: true,
  is_active: true,
  permissions: ["contract.read", "contract.approve"],
  member_count: 1,
  content_sha256: "a".repeat(64),
  pending_approval_request_id: null,
  row_version: 1,
  created_at: "2026-09-01T08:00:00Z",
  updated_at: "2026-09-01T08:00:00Z",
};

const ACCOUNTANT: Role = {
  ...REVIEWER,
  id: "11111111-1111-4111-8111-111111111111",
  code: "revenue_accountant",
  name: "Revenue Accountant",
  permissions: ["contract.read", "contract.create"],
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

function lena(overrides: Partial<UserItem> = {}): UserItem {
  return {
    id: MEMBERSHIP,
    user_id: "6d2e9b8f-3c5a-4d7e-8f9a-0b1c2d3e4f5a",
    email: "lena@demo.erev",
    display_name: "Lena Fischer",
    status: "ACTIVE",
    roles: [
      {
        assignment_id: "44444444-4444-4444-8444-444444444444",
        role: { id: REVIEWER.id, code: REVIEWER.code, name: REVIEWER.name },
        is_all_entities: false,
        entities: [
          { id: "7e6f5a4b-3c2d-4e1f-8a9b-0c1d2e3f4a5b", code: "AVM-DE", name: "Avenmoor GmbH" },
        ],
        entity_count: 1,
        status: "ACTIVE",
        granted_at: "2026-09-12T19:02:00Z",
        granted_by: { id: null, kind: "SYSTEM", display_name: "AUTO-BOOTSTRAP" },
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
    invited_at: "2026-09-12T08:00:00Z",
    invitation_expires_at: null,
    activated_at: "2026-09-12T09:00:00Z",
    removed_at: null,
    row_version: 4,
    created_at: "2026-09-12T08:00:00Z",
    updated_at: "2026-09-13T10:15:00Z",
    ...overrides,
  };
}

function serve(user: UserItem) {
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), () =>
      HttpResponse.json({
        items: [entity("7e6f5a4b-3c2d-4e1f-8a9b-0c1d2e3f4a5b", "AVM-DE", "Avenmoor GmbH")],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/roles"), () =>
      HttpResponse.json({ items: [ACCOUNTANT, REVIEWER], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/sod-rules"), () =>
      HttpResponse.json({ items: [SOD_3], next_cursor: null }),
    ),
    http.get(apiUrl(`/api/v1/users/${MEMBERSHIP}`), () => HttpResponse.json(user)),
  );
}

function renderUser(me = TOMAS) {
  return renderApp(ROUTE, { me, screenRoutes: SCREEN_ROUTES });
}

describe("SF-14:user", () => {
  it("the roles table named Roles shows the outline chip Setup grant for AUTO-BOOTSTRAP grants", async () => {
    serve(lena());
    renderUser();

    expect(await screen.findByRole("heading", { level: 1, name: "Lena Fischer" })).toBeTruthy();
    const table = screen.getByRole("table", { name: "Roles" });
    expect(table.getAttribute("data-testid")).toBe("SF-14-grid-user-roles");
    const row = within(table).getByRole("row", { name: /Revenue Reviewer/ });
    expect(within(row).getByText("Setup grant")).toBeTruthy();
    expect(within(row).getByText("AVM-DE")).toBeTruthy();
    expect(within(row).getByText("Active")).toBeTruthy();
    expect(within(row).getByRole("button", { name: "Revoke role" })).toBeTruthy();
    expect(screen.getByText("MFA enrolled")).toBeTruthy();
    expect(assignmentChip("REQUESTED")).toBe("Pending approval");
    expect(assignmentChip("REVOKED")).toBe("Revoked");
  });

  // SCREENS_B §9.10 rev 1.60 (04 T-PLT-10): Lena's one role is for AVM-DE. Before, every holder of
  // user.manage and role.manage was offered the commands, and the API refused the others (403).
  it("a command on a member and on a role is offered to an administrator whose permission covers the entities granted", async () => {
    serve(lena());
    renderUser(adminOf(DE_ID));
    expect(await screen.findByRole("heading", { level: 1, name: "Lena Fischer" })).toBeTruthy();
    for (const name of ["Reset MFA", "Suspend", "Remove", "Add role", "Revoke role"]) {
      expect(screen.getByRole("button", { name }), name).toBeTruthy();
    }
  });

  it("an administrator of another entity is offered no command on the member or her role", async () => {
    serve(lena());
    renderUser(adminOf(US_ID));
    expect(await screen.findByRole("heading", { level: 1, name: "Lena Fischer" })).toBeTruthy();
    for (const name of ["Reset MFA", "Suspend", "Remove", "Revoke role"]) {
      expect(screen.queryByRole("button", { name }), name).toBeNull();
    }
    // "Add role" stays: its scope field offers what the administrator's own role.manage covers.
    expect(screen.getByRole("button", { name: "Add role" })).toBeTruthy();
  });

  it("a role for all entities is beyond an administrator of named entities", async () => {
    const everywhere = lena();
    const [role] = everywhere.roles;
    serve({
      ...everywhere,
      roles: role === undefined ? [] : [{ ...role, is_all_entities: true, entities: [] }],
    });
    renderUser(adminOf(DE_ID, US_ID));
    expect(await screen.findByRole("heading", { level: 1, name: "Lena Fischer" })).toBeTruthy();
    for (const name of ["Reset MFA", "Suspend", "Remove", "Revoke role"]) {
      expect(screen.queryByRole("button", { name }), name).toBeNull();
    }
  });

  it("Add role offers a grantor of named entities those entities and shows the API's finding on the scope", async () => {
    serve(lena());
    server.use(
      http.post(apiUrl("/api/v1/role-assignments"), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            {
              field: "entity_codes",
              sheet: null,
              row: null,
              rule_id: "EREV-REF-002",
              message: "Choose entities that exist in this workspace.",
            },
          ],
        }),
      ),
    );
    renderUser(adminOf(DE_ID));
    fireEvent.click(await screen.findByRole("button", { name: "Add role" }));
    const dialog = await screen.findByRole("dialog", { name: "Add role" });
    await within(dialog).findByRole("combobox", { name: "Role" });
    expect(within(dialog).queryByRole("radio", { name: "All entities" })).toBeNull();
    expect(
      within(dialog).getByText(
        "Your own access covers named entities only. Choose from those entities, not all entities.",
      ),
    ).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("combobox", { name: "Role" }));
    fireEvent.mouseDown(screen.getByRole("option", { name: "Revenue Accountant" }));
    fireEvent.change(within(dialog).getByRole("combobox", { name: "Entities" }), {
      target: { value: "AVM-DE" },
    });
    fireEvent.mouseDown(screen.getByRole("option", { name: "AVM-DE · Avenmoor GmbH" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Add role" }));
    expect(
      await within(dialog).findByText("Choose entities that exist in this workspace."),
    ).toBeTruthy();
  });

  it("Suspend requires a reason and states its consequence", async () => {
    const bodies: unknown[] = [];
    serve(lena());
    server.use(
      http.post(apiUrl(`/api/v1/users/${MEMBERSHIP}/suspend`), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(lena({ status: "SUSPENDED" }));
      }),
    );
    renderUser();

    fireEvent.click(await screen.findByRole("button", { name: "Suspend" }));
    const dialog = await screen.findByRole("dialog", { name: "Suspend Lena Fischer?" });
    expect(
      within(dialog).getByText(
        "Suspending Lena Fischer ends every session immediately. The membership and its history remain.",
      ),
    ).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Suspend member" }));
    expect(await within(dialog).findByText(/at least 10 characters/i)).toBeTruthy();
    expect(bodies).toEqual([]);

    fireEvent.change(within(dialog).getByRole("textbox", { name: "Reason (required)" }), {
      target: { value: "Left the finance team on 12 September." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Suspend member" }));
    expect(await screen.findByText("Lena Fischer is suspended.")).toBeTruthy();
    expect(bodies).toEqual([{ reason: "Left the finance team on 12 September." }]);
  });

  it("Reset MFA needs the step-up, states its consequence and resends with the same Idempotency-Key", async () => {
    const keys: Array<string | null> = [];
    let attempts = 0;
    serve(lena());
    server.use(
      http.post(apiUrl(`/api/v1/users/${MEMBERSHIP}/reset-mfa`), ({ request }) => {
        attempts += 1;
        keys.push(request.headers.get("Idempotency-Key"));
        return attempts === 1
          ? problemResponse("mfa-step-up-required", 403, "Verify with your authenticator")
          : HttpResponse.json(lena({ mfa_enrolled: false }));
      }),
      http.post(apiUrl("/api/v1/session/mfa"), () =>
        HttpResponse.json({ ...signedInSession(), recovery_codes_remaining: null }),
      ),
    );
    renderUser();

    fireEvent.click(await screen.findByRole("button", { name: "Reset MFA" }));
    const dialog = await screen.findByRole("dialog", { name: "Reset MFA for Lena Fischer?" });
    expect(
      within(dialog).getByText(
        "Lena Fischer must enrol again at the next sign-in. Every session of the user ends.",
      ),
    ).toBeTruthy();
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Reason (required)" }), {
      target: { value: "Phone lost, confirmed by the member." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Reset MFA" }));

    const stepUp = await screen.findByRole("dialog", { name: "Confirm with your authenticator" });
    fireEvent.change(within(stepUp).getByRole("textbox", { name: "Authentication code" }), {
      target: { value: "123456" },
    });
    fireEvent.click(within(stepUp).getByRole("button", { name: "Confirm" }));

    expect(await screen.findByText("MFA reset for Lena Fischer.")).toBeTruthy();
    expect(attempts).toBe(2);
    expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/);
    expect(keys[1]).toBe(keys[0]);
  });

  // SCREENS_B §9.10 rev 1.105 (04 T-PLT-02 rev 1.316): the null of `mfa_enrolled` of an invited or
  // a removed member means "not shown" — API-S-User says so with `sign_in_withheld` — and the
  // section read "MFA not enrolled" for it, which says of the person that there is no factor.
  it.each([
    ["an invited", lena({ status: "INVITED", activated_at: null })],
    ["a removed", lena({ status: "REMOVED", removed_at: "2026-09-13T10:15:00Z" })],
  ])(
    "the Security section of %s member says that MFA and last sign-in are not shown",
    async (_, member) => {
      serve({ ...member, mfa_enrolled: null, sign_in_withheld: true, last_login_at: null });
      renderUser();

      const section = await screen.findByRole("region", { name: "Security" });
      expect(section.textContent).toBe(
        "SecurityMFA and last sign-in are not shown while a membership is invited or removed.",
      );
    },
  );

  it("the Security section of a member without a factor says MFA not enrolled", async () => {
    serve(lena({ mfa_enrolled: false }));
    renderUser();

    const section = await screen.findByRole("region", { name: "Security" });
    expect(section.textContent).toBe("SecurityMFA not enrolled");
  });

  it("a suspended membership shows This membership is suspended. The user's sessions ended on <timestamp>.", async () => {
    serve(lena({ status: "SUSPENDED", updated_at: "2026-09-13T10:15:00Z" }));
    renderUser();

    const banner = await screen.findByTestId("SF-14-banner-suspended");
    expect(banner.textContent).toMatch(
      /^This membership is suspended\. The user's sessions ended on .+2026.+\.$/,
    );
    expect(screen.getByRole("button", { name: "Reactivate" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Suspend" })).toBeNull();
  });

  it("Request an exception opens Request SoD exception with Valid to limited to 366 days", async () => {
    const bodies: unknown[] = [];
    serve(lena());
    server.use(
      http.post(apiUrl("/api/v1/sod-exceptions"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(
          {
            id: "55555555-5555-4555-8555-555555555555",
            membership_id: MEMBERSHIP,
            member_name: "Lena Fischer",
            sod_rule_code: "SoD-3",
            compensating_control: "Controller reviews every approval by Lena Fischer monthly.",
            valid_from: "2026-09-19T00:00:00Z",
            valid_to: "2027-09-19T23:59:59Z",
            status: "REQUESTED",
            approval_request_id: "8f7e6d5c-4b3a-4c2d-9e1f-0a9b8c7d6e5f",
            approved_at: null,
            created_by: { id: TOMAS.user.id, kind: "USER", display_name: "Tomás Rivera" },
            created_at: "2026-09-19T12:00:00Z",
            revoked_at: null,
            revoked_by: null,
          },
          { status: 201 },
        );
      }),
    );
    renderUser();

    fireEvent.click(await screen.findByRole("button", { name: "Add role" }));
    const add = await screen.findByRole("dialog", { name: "Add role" });
    await within(add).findByRole("combobox", { name: "Role" });
    fireEvent.click(within(add).getByRole("combobox", { name: "Role" }));
    fireEvent.mouseDown(screen.getByRole("option", { name: "Revenue Accountant" }));
    const alert = within(await screen.findByTestId("SF-14-banner-sod-conflict")).getByRole("alert");
    expect(within(alert).getByRole("heading").textContent).toBe(
      "Separation of duties conflict SoD-3: Revenue Accountant with Revenue Reviewer lets one person create and approve the same contract or modification.",
    );
    fireEvent.click(within(alert).getByRole("button", { name: "Request an exception" }));

    const exception = await screen.findByRole("dialog", { name: "Request SoD exception" });
    expect(within(exception).getByTestId("SF-14-drawer-sod-exception")).toBeTruthy();
    expect((within(exception).getByLabelText("Rule") as HTMLInputElement).value).toContain("SoD-3");
    const from = within(exception).getByLabelText("Valid from");
    const to = within(exception).getByLabelText("Valid to");
    fireEvent.change(from, { target: { value: "2026-09-19" } });
    fireEvent.blur(from);
    fireEvent.change(to, { target: { value: "2027-09-21" } });
    fireEvent.blur(to);
    expect(
      await within(exception).findByText("Choose a validity of at most 366 days."),
    ).toBeTruthy();

    // The last day counts (DS-I18N-08; SCREENS_B §9.10 rev 1.30): 366 days after "Valid from" would be a
    // window of 367 days, which 04 T-PLT-14 refuses.
    fireEvent.change(to, { target: { value: "2027-09-20" } });
    fireEvent.blur(to);
    expect(within(exception).getByText("Choose a validity of at most 366 days.")).toBeTruthy();

    fireEvent.change(to, { target: { value: "2027-09-19" } });
    fireEvent.blur(to);
    await waitFor(() => {
      expect(within(exception).queryByText("Choose a validity of at most 366 days.")).toBeNull();
    });
    fireEvent.change(
      within(exception).getByRole("textbox", { name: "Compensating control (required)" }),
      {
        target: { value: "Controller reviews every approval by Lena Fischer monthly." },
      },
    );
    fireEvent.change(within(exception).getByRole("textbox", { name: "Comment (required)" }), {
      target: { value: "Temporary cover during the audit." },
    });
    fireEvent.click(within(exception).getByRole("button", { name: "Request exception" }));

    expect(await screen.findByText("Exception for SoD-3 is waiting for approval.")).toBeTruthy();
    expect(bodies).toEqual([
      {
        membership_id: MEMBERSHIP,
        sod_rule_code: "SoD-3",
        compensating_control: "Controller reviews every approval by Lena Fischer monthly.",
        // SodExceptionIn `valid_from` and `valid_to` are date-time: the window in platform time.
        valid_from: "2026-09-19T00:00:00Z",
        valid_to: "2027-09-19T23:59:59Z",
        comment: "Temporary cover during the audit.",
      },
    ]);
    expect(
      await screen.findByText("Exception 55555555 is attached to this assignment."),
    ).toBeTruthy();
  });
});

// docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): a message of `errors[]` that names a
// member the form shows no message of was shown nowhere. The banner lists it; a message a field or a
// row shows stands there and is not said again.
describe("SF-14:user, a refused command", () => {
  it("Add role: the finding stays under the scope and the banner lists what the row does not show", async () => {
    const finding = "Choose entities that exist in this workspace.";
    const noField = "The exception attached to this assignment has expired.";
    serve(lena());
    server.use(
      http.post(apiUrl("/api/v1/role-assignments"), () =>
        refusedWith({ entity_codes: finding, sod_exception_id: noField }),
      ),
    );
    renderUser(adminOf(DE_ID));
    fireEvent.click(await screen.findByRole("button", { name: "Add role" }));
    const dialog = await screen.findByRole("dialog", { name: "Add role" });
    fireEvent.click(await within(dialog).findByRole("combobox", { name: "Role" }));
    fireEvent.mouseDown(screen.getByRole("option", { name: "Revenue Accountant" }));
    fireEvent.change(within(dialog).getByRole("combobox", { name: "Entities" }), {
      target: { value: "AVM-DE" },
    });
    fireEvent.mouseDown(screen.getByRole("option", { name: "AVM-DE · Avenmoor GmbH" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Add role" }));

    expect(await within(dialog).findByText(finding)).toBeTruthy();
    const banner = within(dialog).getByRole("heading", { name: REFUSAL_TITLE }).closest("div");
    expect(banner?.textContent).toBe(REFUSAL_TITLE + noField + REFUSAL_REFERENCE);
  });

  it("Suspend: the dialog shows no message at its reason, so the banner says every sentence", async () => {
    const sentence = "A member who holds the last Tenant Admin role cannot be suspended.";
    serve(lena());
    server.use(
      http.post(apiUrl(`/api/v1/users/${MEMBERSHIP}/suspend`), () =>
        refusedWith({ reason: sentence }),
      ),
    );
    renderUser();
    fireEvent.click(await screen.findByRole("button", { name: "Suspend" }));
    const dialog = await screen.findByRole("dialog", { name: "Suspend Lena Fischer?" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Reason (required)" }), {
      target: { value: "Left the finance team on 12 September." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Suspend member" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + sentence + REFUSAL_REFERENCE);
  });

  it("Revoke role: the dialog shows no message at its reason, so the banner says every sentence", async () => {
    const sentence = "A setup grant is revoked once the workspace's setup is complete.";
    serve(lena());
    server.use(
      http.post(
        apiUrl("/api/v1/role-assignments/44444444-4444-4444-8444-444444444444/revoke"),
        () => refusedWith({ status: sentence }),
      ),
    );
    renderUser();
    fireEvent.click(await screen.findByRole("button", { name: "Revoke role" }));
    const dialog = await screen.findByRole("dialog", { name: "Revoke Revenue Reviewer?" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Reason (required)" }), {
      target: { value: "The review duty moved to Priya Raman." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Revoke role" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + sentence + REFUSAL_REFERENCE);
  });

  it("Request SoD exception: the banner lists what no field shows and leaves the comment's message at its field", async () => {
    const noField = "An exception of this rule is already waiting for approval.";
    const atComment = "Say who asked for the exception.";
    serve(lena());
    server.use(
      http.post(apiUrl("/api/v1/sod-exceptions"), () =>
        refusedWith({ valid_to: noField, comment: atComment }),
      ),
    );
    renderUser();
    fireEvent.click(await screen.findByRole("button", { name: "Add role" }));
    const add = await screen.findByRole("dialog", { name: "Add role" });
    fireEvent.click(await within(add).findByRole("combobox", { name: "Role" }));
    fireEvent.mouseDown(screen.getByRole("option", { name: "Revenue Accountant" }));
    const alert = within(await screen.findByTestId("SF-14-banner-sod-conflict")).getByRole("alert");
    fireEvent.click(within(alert).getByRole("button", { name: "Request an exception" }));
    const exception = await screen.findByRole("dialog", { name: "Request SoD exception" });
    const from = within(exception).getByLabelText("Valid from");
    fireEvent.change(from, { target: { value: "2026-09-19" } });
    fireEvent.blur(from);
    const to = within(exception).getByLabelText("Valid to");
    fireEvent.change(to, { target: { value: "2027-09-19" } });
    fireEvent.blur(to);
    fireEvent.change(
      within(exception).getByRole("textbox", { name: "Compensating control (required)" }),
      { target: { value: "Controller reviews every approval by Lena Fischer monthly." } },
    );
    const comment = within(exception).getByRole("textbox", { name: "Comment (required)" });
    fireEvent.change(comment, { target: { value: "Temporary cover during the audit." } });
    fireEvent.click(within(exception).getByRole("button", { name: "Request exception" }));

    const banner = await within(exception).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + noField + REFUSAL_REFERENCE);
    expect(describedBy(comment)).toContain(atComment);
  });
});
