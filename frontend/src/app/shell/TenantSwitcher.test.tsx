// @vitest-environment jsdom
// SF-23 switcher (SCREENS §1.3; 04 API-R-01 `POST /session/tenant`, API-S-Me memberships): "Switch
// tenant" only with more than one membership; the listbox marks the current tenant "Current" and sandbox
// tenants "Sandbox"; selecting sends POST /session/tenant, clears the query cache, opens the landing route
// and announces "Switched to <tenant name>"; the popover ends with "All workspaces". The current tenant
// is the session's (SCREENS_B §9.7 "The open workspace"): a workspace and its copies share one
// membership id.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { announce } from "../../lib/a11y/announce";
import type { Me } from "../../lib/api/queries/me";
import { queryKey, queryKeys } from "../../lib/api/query-keys";
import type { Session } from "../auth/RequireSession";
import { installMemoryStorage, renderWithApp, signedInMe, signedInSession } from "../../test/app";
import { apiUrl, installMswServer, server } from "../../test/msw";
import { switchableMemberships } from "./TenantSwitcher";
import { UserMenu } from "./UserMenu";

vi.mock("../../lib/a11y/announce", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/a11y/announce")>();
  return { ...actual, announce: vi.fn() };
});

installMswServer();
installMemoryStorage();

afterEach(() => {
  cleanup();
  vi.mocked(announce).mockClear();
});

const SANDBOX_MEMBERSHIP = "9e8d7c6b-5a4f-4e3d-8c2b-1a0f9e8d7c6b";
/** The workspace of `signedInSession` and of the membership of `signedInMe`. */
const PRODUCTION_TENANT_ID = "0b6f3e2d-1c4a-4b8e-9d7f-6a5c4b3e2d1f";
const SANDBOX_TENANT = {
  id: "7d6c5b4a-3f2e-4d1c-9b0a-8f7e6d5c4b3a",
  code: "avenmoor-sbx",
  display_name: "Avenmoor Sandbox",
  kind: "sandbox" as const,
  status: "ACTIVE" as const,
  source_tenant_id: "0b6f3e2d-1c4a-4b8e-9d7f-6a5c4b3e2d1f",
  source_known_at: "2026-09-12T18:10:00Z",
};

function twoWorkspaces(overrides: Partial<Me> = {}): Me {
  const me = signedInMe();
  return {
    ...me,
    memberships: [
      ...me.memberships,
      {
        membership_id: SANDBOX_MEMBERSHIP,
        tenant: { ...SANDBOX_TENANT, is_demo: false },
        status: "ACTIVE",
        last_opened_at: null,
      },
    ],
    ...overrides,
  };
}

function nth(elements: readonly HTMLElement[], index: number): HTMLElement {
  const element = elements[index];
  if (element === undefined) {
    throw new Error(`no element ${String(index)}`);
  }
  return element;
}

function openUserMenu(): void {
  fireEvent.click(screen.getByRole("button", { name: "User menu for Maya Chen" }));
}

describe("SF-23 switcher", () => {
  it("the user menu shows Switch tenant only with more than one membership", () => {
    renderWithApp(<UserMenu built={new Set()} homePath="/home" />);
    openUserMenu();
    expect(screen.getByRole("menu")).toBeTruthy();
    expect(screen.queryByRole("menuitem", { name: "Switch tenant" })).toBeNull();
    cleanup();

    renderWithApp(<UserMenu built={new Set()} homePath="/home" />, { me: twoWorkspaces() });
    openUserMenu();
    expect(screen.getByRole("menuitem", { name: "Switch tenant" })).toBeTruthy();
  });

  it("offers ACTIVE workspaces only: an archived sandbox is not a choice (05 SBX-07)", () => {
    const me = twoWorkspaces();
    const archived = me.memberships.map((membership) =>
      membership.membership_id === SANDBOX_MEMBERSHIP
        ? { ...membership, tenant: { ...membership.tenant, status: "ARCHIVED" as const } }
        : membership,
    );
    // the membership is still ACTIVE: it is the workspace that can no longer be opened
    expect(archived.map((membership) => membership.status)).toEqual(["ACTIVE", "ACTIVE"]);
    expect(switchableMemberships(archived, PRODUCTION_TENANT_ID).map((m) => m.tenant.code)).toEqual(
      ["avenmoor"],
    );
    expect(
      switchableMemberships(me.memberships, PRODUCTION_TENANT_ID).map((m) => m.tenant.code),
    ).toEqual(["avenmoor", "avenmoor-sbx"]);
    // a session still inside the archived sandbox sees it as its current workspace
    expect(switchableMemberships(archived, SANDBOX_TENANT.id).map((m) => m.tenant.code)).toEqual([
      "avenmoor",
      "avenmoor-sbx",
    ]);
    // with one workspace left to open there is nothing to switch to
    renderWithApp(<UserMenu built={new Set()} homePath="/home" />, {
      me: { ...me, memberships: archived },
    });
    openUserMenu();
    expect(screen.queryByRole("menuitem", { name: "Switch tenant" })).toBeNull();
  });

  it("marks Current and Sandbox; selecting switches, clears the cache, opens the landing route and announces", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(apiUrl("/api/v1/session/tenant"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({
          ...signedInSession({ active_tenant: SANDBOX_TENANT }),
          mfa_required: false,
          mfa_enrolment_required: false,
        });
      }),
      http.get(apiUrl("/api/v1/me"), () =>
        HttpResponse.json(twoWorkspaces({ active_membership_id: SANDBOX_MEMBERSHIP })),
      ),
    );
    const { router, queryClient } = renderWithApp(
      <UserMenu built={new Set(["/select-workspace"])} homePath="/home" />,
      { entry: "/contracts?view=mine", me: twoWorkspaces() },
    );
    const previousWorkspace = queryKey("probe", "tenant");
    queryClient.setQueryData(previousWorkspace, "a read of the previous workspace");

    openUserMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "Switch tenant" }));
    const listbox = screen.getByRole("listbox", { name: "Workspaces" });
    expect(document.activeElement).toBe(listbox);
    const options = within(listbox).getAllByRole("option");
    expect(options).toHaveLength(2);
    const current = nth(options, 0);
    const sandbox = nth(options, 1);
    expect(within(current).getByText("Avenmoor")).toBeTruthy();
    expect(within(current).getByText("Current")).toBeTruthy();
    expect(current.getAttribute("aria-selected")).toBe("true");
    expect(within(sandbox).getByText("Avenmoor Sandbox")).toBeTruthy();
    expect(within(sandbox).getByText("Sandbox")).toBeTruthy();
    expect(within(sandbox).queryByText("Current")).toBeNull();
    const popover = listbox.parentElement;
    if (popover === null) {
      throw new Error("the listbox has no popover");
    }
    const allWorkspaces = within(popover).getByRole("link", { name: "All workspaces" });
    expect(allWorkspaces.getAttribute("href")).toBe("/select-workspace");
    expect(popover.lastElementChild?.contains(allWorkspaces)).toBe(true);

    fireEvent.keyDown(listbox, { key: "ArrowDown" });
    fireEvent.keyDown(listbox, { key: "Enter" });
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/home");
    });
    expect(bodies).toEqual([{ tenant_id: SANDBOX_TENANT.id }]);
    expect(queryClient.getQueryData(previousWorkspace)).toBeUndefined();
    expect(
      queryClient.getQueryData<Session>(queryKeys.session())?.active_tenant?.display_name,
    ).toBe("Avenmoor Sandbox");
    expect(announce).toHaveBeenCalledWith("Switched to Avenmoor Sandbox", "polite");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("between a workspace and its copies one workspace reads Current and a choice opens the workspace chosen", async () => {
    // A copy keeps the ids of the rows it copies: the member of a workspace holds ONE membership id
    // in the workspace, in its copy and in the copy a reset archived.
    const base = signedInMe();
    const production = base.memberships[0];
    if (production === undefined) {
      throw new Error("no membership");
    }
    const copy = (id: string, code: string, status: "ACTIVE" | "ARCHIVED") => ({
      membership_id: production.membership_id,
      tenant: {
        ...SANDBOX_TENANT,
        id,
        code,
        display_name: "Avenmoor rehearsal",
        status,
        is_demo: false,
      },
      status: "ACTIVE" as const,
      last_opened_at: null,
    });
    const ACTIVE_COPY = "1c1c1c1c-1c1c-4c1c-8c1c-1c1c1c1c1c1c";
    const ARCHIVED_COPY = "2d2d2d2d-2d2d-4d2d-8d2d-2d2d2d2d2d2d";
    const me: Me = {
      ...base,
      memberships: [
        production,
        copy(ACTIVE_COPY, "sbx-avenmoor-rehearsal-r1", "ACTIVE"),
        copy(ARCHIVED_COPY, "sbx-avenmoor-rehearsal", "ARCHIVED"),
      ],
    };
    expect(new Set(me.memberships.map((membership) => membership.membership_id)).size).toBe(1);
    const inside = (id: string, code: string) =>
      signedInSession({
        active_tenant: { id, code, display_name: "Avenmoor rehearsal", kind: "sandbox" },
      });
    const bodies: unknown[] = [];
    server.use(
      http.post(apiUrl("/api/v1/session/tenant"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({
          ...signedInSession(),
          mfa_required: false,
          mfa_enrolment_required: false,
        });
      }),
      http.get(apiUrl("/api/v1/me"), () => HttpResponse.json(me)),
    );
    /** The options of the switcher: [name, chips …] of each. */
    const listed = () => {
      openUserMenu();
      fireEvent.click(screen.getByRole("menuitem", { name: "Switch tenant" }));
      const options = within(screen.getByRole("listbox", { name: "Workspaces" })).getAllByRole(
        "option",
      );
      return {
        options,
        rows: options.map((option) => [
          option.getAttribute("aria-selected") === "true" ? "selected" : "",
          ...(option.textContent.match(/Avenmoor rehearsal|Avenmoor|Sandbox|Current/g) ?? []),
        ]),
      };
    };

    // In the workspace: it alone is current, the archived copy is not listed, the copy opens.
    renderWithApp(<UserMenu built={new Set()} homePath="/home" />, { me });
    let shown = listed();
    expect(shown.rows).toEqual([
      ["selected", "Avenmoor", "Current"],
      ["", "Avenmoor rehearsal", "Sandbox"],
    ]);
    fireEvent.mouseDown(nth(shown.options, 1));
    await waitFor(() => {
      expect(bodies).toEqual([{ tenant_id: ACTIVE_COPY }]);
    });
    cleanup();

    // In the copy: the copy alone is current, and the source opens.
    renderWithApp(<UserMenu built={new Set()} homePath="/home" />, {
      me,
      session: inside(ACTIVE_COPY, "sbx-avenmoor-rehearsal-r1"),
    });
    shown = listed();
    expect(shown.rows).toEqual([
      ["", "Avenmoor"],
      ["selected", "Avenmoor rehearsal", "Sandbox", "Current"],
    ]);
    fireEvent.mouseDown(nth(shown.options, 0));
    await waitFor(() => {
      expect(bodies).toEqual([{ tenant_id: ACTIVE_COPY }, { tenant_id: PRODUCTION_TENANT_ID }]);
    });
    cleanup();

    // A session still inside the archived copy: it is listed for that session, and it alone is
    // current.
    renderWithApp(<UserMenu built={new Set()} homePath="/home" />, {
      me,
      session: inside(ARCHIVED_COPY, "sbx-avenmoor-rehearsal"),
    });
    shown = listed();
    expect(shown.rows).toEqual([
      ["", "Avenmoor"],
      ["", "Avenmoor rehearsal", "Sandbox"],
      ["selected", "Avenmoor rehearsal", "Sandbox", "Current"],
    ]);
  });

  it("without SF-23:select built the popover has no All workspaces link", () => {
    renderWithApp(<UserMenu built={new Set()} homePath="/home" />, { me: twoWorkspaces() });
    openUserMenu();
    fireEvent.click(screen.getByRole("menuitem", { name: "Switch tenant" }));
    expect(screen.getByRole("listbox", { name: "Workspaces" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "All workspaces" })).toBeNull();
  });
});
