// @vitest-environment jsdom
// SF-14:roles and REQ-PLT-008, REQ-PLT-009 (BUILD_SPEC WEB-20; SCREENS_B §9.11; 04 API-R-06 `GET /roles`,
// `GET /roles/{id}`, `GET /permissions`, `POST /roles`; T-PLT-11): the grid "Roles" lists the ten system
// roles and the custom role with Code, System, Permissions, Members and Active; the drawer groups
// permissions by area with the "Approval", "Access admin" and "MFA" chips; "New role" requires a lowercase
// code, notes the forced MFA, warns on a checked SoD pair with "I have reviewed this warning" and
// "Submit for approval" sends `POST /roles`; a system role shows no edit control and the tooltip
// "System roles cannot change."
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import type { Permission, Role, SodRule } from "../../lib/api/queries/roles";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, server } from "../../test/msw";
import { describedBy, REFUSAL_REFERENCE, REFUSAL_TITLE, refusedWith } from "../../test/refusals";
import { areaLabel, rolePairWarning } from "./roles";

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

const TOMAS = signedInMe({ permissions: ["user.manage", "role.manage"] });

const SYSTEM_ROLE_NAMES = [
  "Tenant Admin",
  "Revenue Accountant",
  "Revenue Reviewer",
  "Controller",
  "SSP Analyst",
  "Deal Desk",
  "Auditor",
  "Integration Operator",
  "Report Viewer",
  "Forecast Planner",
];

function role(index: number, name: string, overrides: Partial<Role> = {}): Role {
  const code = name.toLowerCase().replace(/ /g, "_");
  return {
    id: `${String(index + 1).padStart(8, "0")}-0000-4000-8000-000000000000`,
    code,
    name,
    description: null,
    is_system: true,
    is_active: true,
    permissions: ["contract.read"],
    member_count: index,
    content_sha256: "a".repeat(64),
    pending_approval_request_id: null,
    row_version: 1,
    created_at: "2026-09-01T08:00:00Z",
    updated_at: "2026-09-01T08:00:00Z",
    ...overrides,
  };
}

const ROLES: Role[] = [
  ...SYSTEM_ROLE_NAMES.map((name, index) =>
    role(index, name, {
      permissions:
        name === "Revenue Reviewer" ? ["contract.read", "contract.approve"] : ["contract.read"],
    }),
  ),
  role(10, "Deal desk analyst", {
    is_system: false,
    permissions: ["contract.read", "scenario.use"],
    description: "Prepares deal previews.",
  }),
];

const REVIEWER = ROLES[2] as Role;
const CUSTOM = ROLES[10] as Role;

const PERMISSIONS: Permission[] = [
  {
    code: "contract.read",
    area: "CON",
    description: "View contracts, obligations and schedules",
    is_approval: false,
    is_access_admin: false,
    requires_mfa: false,
  },
  {
    code: "contract.create",
    area: "CON",
    description: "Create and edit contracts",
    is_approval: false,
    is_access_admin: false,
    requires_mfa: false,
  },
  {
    code: "contract.approve",
    area: "CON",
    description: "Approve contracts and modifications",
    is_approval: true,
    is_access_admin: false,
    requires_mfa: true,
  },
  {
    code: "user.manage",
    area: "PLT",
    description: "Invite, suspend and remove members",
    is_approval: false,
    is_access_admin: true,
    requires_mfa: true,
  },
  {
    code: "scenario.use",
    area: "FC",
    description: "Use forecast scenarios",
    is_approval: false,
    is_access_admin: false,
    requires_mfa: false,
  },
];

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

function serve() {
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
    http.get(apiUrl("/api/v1/roles"), ({ request }) =>
      HttpResponse.json(
        { items: ROLES, next_cursor: null },
        {
          headers:
            new URL(request.url).searchParams.get("count") === "true"
              ? { "X-Erev-Total-Count": String(ROLES.length) }
              : {},
        },
      ),
    ),
    http.get(apiUrl(`/api/v1/roles/${REVIEWER.id}`), () => HttpResponse.json(REVIEWER)),
    http.get(apiUrl(`/api/v1/roles/${CUSTOM.id}`), () => HttpResponse.json(CUSTOM)),
    http.get(apiUrl("/api/v1/permissions"), () =>
      HttpResponse.json({ items: PERMISSIONS, next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/sod-rules"), () =>
      HttpResponse.json({ items: [SOD_3], next_cursor: null }),
    ),
  );
}

async function findGrid(): Promise<HTMLElement> {
  return within(await screen.findByTestId("SF-14-grid-roles")).findByRole("grid", {
    name: "Roles",
  });
}

describe("SF-14:roles and REQ-PLT-008, REQ-PLT-009", () => {
  it("the grid Roles lists the ten system roles and the custom role with Code, System, Permissions, Members and Active", async () => {
    serve();
    renderApp("/settings/roles", { me: TOMAS, screenRoutes: SCREEN_ROUTES });

    const grid = await findGrid();
    expect(await within(grid).findByRole("rowheader", { name: "Deal desk analyst" })).toBeTruthy();
    for (const name of SYSTEM_ROLE_NAMES) {
      expect(within(grid).getByRole("rowheader", { name })).toBeTruthy();
    }
    const headers = within(grid)
      .getAllByRole("columnheader")
      .map((header) => header.textContent?.trim() ?? "");
    for (const name of ["Role", "Code", "System", "Permissions", "Members", "Active"]) {
      expect(headers.some((header) => header.startsWith(name))).toBe(true);
    }
    const custom = screen.getByTestId("SF-14-row-deal-desk-analyst");
    expect(within(custom).getByText("deal_desk_analyst")).toBeTruthy();
    expect(within(custom).getAllByText("No").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { level: 1, name: "Roles" })).toBeTruthy();
    expect(screen.queryByText("Download role matrix")).toBeNull();
  });

  // SCREENS_B §9.11 Grid columns: "System" (Yes/No) and "Active" (Yes/No). The two columns handed
  // the copy "Yes" to the grid's boolean cell, which prints "Yes" for the raw value "true" alone:
  // every role read "No" in both.
  it("System and Active read Yes for a system role that is active, and No for the flag a role does not have", async () => {
    serve();
    renderApp("/settings/roles", { me: TOMAS, screenRoutes: SCREEN_ROUTES });

    const grid = await findGrid();
    await within(grid).findByRole("rowheader", { name: "Deal desk analyst" });
    const flags = (row: string) =>
      ["is_system", "is_active"].map(
        (column) =>
          screen.getByTestId(`SF-14-row-${row}`).querySelector(`[data-column="${column}"]`)
            ?.textContent,
      );
    expect(flags("revenue-reviewer")).toEqual(["Yes", "Yes"]);
    expect(flags("deal-desk-analyst")).toEqual(["No", "Yes"]);
  });

  it("the drawer groups permissions by area with the chips Approval, Access admin and MFA; a system role cannot change", async () => {
    serve();
    const { router } = renderApp("/settings/roles", { me: TOMAS, screenRoutes: SCREEN_ROUTES });
    const grid = await findGrid();
    const cell = await within(grid).findByRole("rowheader", { name: "Revenue Reviewer" });
    fireEvent.click(within(cell).getByRole("link", { name: "Revenue Reviewer" }));

    const drawer = await screen.findByRole("complementary", { name: "Revenue Reviewer" });
    await waitFor(() => {
      expect(router.state.location.search).toBe(`?drawer=role&role=${REVIEWER.id}`);
    });
    expect(within(drawer).getByTestId("SF-14-drawer-role")).toBeTruthy();
    const contracts = await within(drawer).findByRole("region", { name: "Contracts" });
    expect(within(contracts).getByText("contract.approve")).toBeTruthy();
    expect(within(contracts).getByText("Approval")).toBeTruthy();
    expect(within(contracts).getByText("MFA")).toBeTruthy();
    expect(within(contracts).queryByText("Access admin")).toBeNull();
    expect(within(drawer).getByText("Code revenue_reviewer · System role")).toBeTruthy();

    const change = within(drawer).getByRole("button", { name: "Propose change" });
    expect(change.getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByText("System roles cannot change.")).toBeTruthy();
    expect(areaLabel("CON")).toBe("Contracts");
    expect(areaLabel("ZZZ")).toBe("ZZZ");
  });

  it("a custom role's Propose change opens the change drawer", async () => {
    serve();
    renderApp(`/settings/roles?drawer=role&role=${CUSTOM.id}`, {
      me: TOMAS,
      screenRoutes: SCREEN_ROUTES,
    });
    const drawer = await screen.findByRole("complementary", { name: "Deal desk analyst" });
    expect(await within(drawer).findByText("Prepares deal previews.")).toBeTruthy();
    const change = within(drawer).getByRole("button", { name: "Propose change" });
    expect(change.getAttribute("aria-disabled")).toBeNull();
    fireEvent.click(change);
    const dialog = await screen.findByRole("dialog", { name: "Propose change" });
    expect(
      (within(dialog).getByRole("checkbox", { name: /scenario\.use/ }) as HTMLInputElement).checked,
    ).toBe(true);
  });

  it("a role's definition needs role.manage for all entities: a holder for named entities reads the roles and is offered neither command", async () => {
    // SCREENS_B §9.11 rev 1.60 (04 T-PLT-10): POST /roles and /propose-change are tenant-wide acts.
    serve();
    renderApp(`/settings/roles?drawer=role&role=${CUSTOM.id}`, {
      me: signedInMe({
        permissions: ["role.manage"],
        permission_scopes: { "role.manage": ["7e6f5a4b-3c2d-4e1f-8a9b-0c1d2e3f4a5b"] },
      }),
      screenRoutes: SCREEN_ROUTES,
    });
    const drawer = await screen.findByRole("complementary", { name: "Deal desk analyst" });
    expect(await within(drawer).findByText("Prepares deal previews.")).toBeTruthy();
    expect(within(drawer).queryByRole("button", { name: "Propose change" })).toBeNull();
    expect(await screen.findByRole("grid", { name: "Roles" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "New role" })).toBeNull();
  });

  it("New role requires a lowercase code, notes the forced MFA, warns on a checked SoD pair and submits for approval", async () => {
    serve();
    const bodies: unknown[] = [];
    server.use(
      http.post(apiUrl("/api/v1/roles"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(
          role(11, "Contract clerk", {
            is_system: false,
            code: "contract_clerk",
            permissions: ["contract.create", "contract.approve"],
            pending_approval_request_id: "8f7e6d5c-4b3a-4c2d-9e1f-0a9b8c7d6e5f",
          }),
          { status: 201 },
        );
      }),
    );
    renderApp("/settings/roles", { me: TOMAS, screenRoutes: SCREEN_ROUTES });
    await findGrid();

    fireEvent.click(screen.getByRole("button", { name: "New role" }));
    const dialog = await screen.findByRole("dialog", { name: "New role" });
    const contracts = await within(dialog).findByRole("group", { name: "Contracts" });
    expect(within(dialog).getByRole("group", { name: "Platform" })).toBeTruthy();

    fireEvent.change(within(dialog).getByLabelText("Name"), {
      target: { value: "Contract clerk" },
    });
    fireEvent.change(within(dialog).getByLabelText("Code"), {
      target: { value: "Contract Clerk" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Submit for approval" }));
    expect(within(dialog).getAllByText("Use lowercase letters and underscores.").length).toBe(2);
    expect(bodies).toEqual([]);

    fireEvent.change(within(dialog).getByLabelText("Code"), {
      target: { value: "contract_clerk" },
    });
    fireEvent.click(within(contracts).getByRole("checkbox", { name: /contract\.approve/ }));
    expect(
      within(dialog).getByText(
        "Holding an approval permission forces multi-factor authentication.",
      ),
    ).toBeTruthy();
    expect(within(dialog).queryByTestId("SF-14-banner-role-sod")).toBeNull();

    fireEvent.click(within(contracts).getByRole("checkbox", { name: /contract\.create/ }));
    const warning = await within(dialog).findByTestId("SF-14-banner-role-sod");
    expect(within(warning).getByRole("status").textContent).toBe(
      "This role combines contract.create with contract.approve (SoD 3). Members will need an exception.",
    );
    const reviewed = within(warning).getByRole("checkbox", {
      name: "I have reviewed this warning",
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Submit for approval" }));
    expect(
      await within(dialog).findByText(
        "Confirm that you reviewed the separation-of-duties warning.",
      ),
    ).toBeTruthy();
    expect(bodies).toEqual([]);

    fireEvent.click(reviewed);
    fireEvent.click(within(dialog).getByRole("button", { name: "Submit for approval" }));
    expect(await screen.findByText("Role Contract clerk is waiting for approval.")).toBeTruthy();
    expect(bodies).toEqual([
      {
        code: "contract_clerk",
        name: "Contract clerk",
        description: null,
        permissions: ["contract.approve", "contract.create"],
      },
    ]);
    expect(rolePairWarning(SOD_3)).toBe(
      "This role combines contract.create with contract.approve (SoD 3). Members will need an exception.",
    );
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): a message for a member the form
  // shows no message of was shown nowhere; one for a field stands there and is not said by the banner.
  it("New role under a refused command: the banner lists what no field shows", async () => {
    const noField = "A role may hold at most one approval permission of an area.";
    const atCode = "A role with this code exists.";
    serve();
    server.use(
      http.post(apiUrl("/api/v1/roles"), () =>
        refusedWith({ "permissions.1": noField, code: atCode }),
      ),
    );
    renderApp("/settings/roles", { me: TOMAS, screenRoutes: SCREEN_ROUTES });
    await findGrid();
    fireEvent.click(screen.getByRole("button", { name: "New role" }));
    const dialog = await screen.findByRole("dialog", { name: "New role" });
    const contracts = await within(dialog).findByRole("group", { name: "Contracts" });
    fireEvent.change(within(dialog).getByLabelText("Name"), {
      target: { value: "Contract clerk" },
    });
    const code = within(dialog).getByLabelText("Code");
    fireEvent.change(code, { target: { value: "contract_clerk" } });
    fireEvent.click(within(contracts).getByRole("checkbox", { name: /contract\.approve/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Submit for approval" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + noField + REFUSAL_REFERENCE);
    expect(describedBy(code)).toContain(atCode);
  });

  it("Propose change under a refused command: the drawer has no field for a message, so the banner says every sentence", async () => {
    const first = "A role in use keeps its approval permissions.";
    const second = "Say why the role changes.";
    serve();
    server.use(
      http.post(apiUrl(`/api/v1/roles/${CUSTOM.id}/propose-change`), () =>
        refusedWith({ permissions: first, comment: second }),
      ),
    );
    renderApp(`/settings/roles?drawer=role&role=${CUSTOM.id}`, {
      me: TOMAS,
      screenRoutes: SCREEN_ROUTES,
    });
    const drawer = await screen.findByRole("complementary", { name: "Deal desk analyst" });
    await within(drawer).findByText("Prepares deal previews.");
    fireEvent.click(within(drawer).getByRole("button", { name: "Propose change" }));
    const dialog = await screen.findByRole("dialog", { name: "Propose change" });
    fireEvent.click(await within(dialog).findByRole("checkbox", { name: /contract\.create/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Submit for approval" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + first + second + REFUSAL_REFERENCE);
  });
});
