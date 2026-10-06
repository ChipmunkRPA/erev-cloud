// @vitest-environment jsdom
// SF-15 index (BUILD_SPEC WEB-17; SCREENS_B §9.1; SCREENS §0.3 SCR-IA-03, §0.4 RT-71 to RT-93 and
// RT-110; 04 API-R-17 `GET /tenant`): one section and h2 per group and never a card grid; a link only
// for a readable, built page; the setup banner for settings.manage holders, with "Finish setup" once
// SF-15:setup is built.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { RouteObject } from "react-router";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { accessOf } from "../../lib/access";
import { renderApp, signedInMe } from "../../test/app";
import { apiUrl, installMswServer, server } from "../../test/msw";
import { mayRead, SETTINGS_GROUPS, tenantKey, visibleGroups } from "./index";

installMswServer();

afterEach(() => {
  cleanup();
});

/** `GET /tenant` answering `setup_completed_at`; `count` reports the requests served. */
function serveTenant(setupCompletedAt: string | null): { readonly count: () => number } {
  let requests = 0;
  server.use(
    http.get(apiUrl("/api/v1/tenant"), () => {
      requests += 1;
      return HttpResponse.json({
        id: "0b6f3e2d-1c4a-4b8e-9d7f-6a5c4b3e2d1f",
        code: "avenmoor",
        display_name: "Avenmoor",
        kind: "production",
        setup_completed_at: setupCompletedAt,
      });
    }),
  );
  return { count: () => requests };
}

const ONE_ENTITY = "0a1b2c3d-4e5f-4a6b-8c7d-0000000000de";

/** The entities of the workspace, which the access module reads for a member of named entities. */
function serveEntities(): void {
  server.use(
    http.get(apiUrl("/api/v1/entities"), () => HttpResponse.json({ items: [], next_cursor: null })),
  );
}

function renderIndex(permissions: readonly string[], extraRoutes: readonly RouteObject[] = []) {
  return renderApp("/settings", {
    me: signedInMe({ permissions: [...permissions] }),
    screenRoutes: [...SCREEN_ROUTES, ...extraRoutes],
  });
}

function groupHeadings(): (string | null)[] {
  return within(screen.getByTestId("SF-15-page"))
    .getAllByRole("heading", { level: 2 })
    .map((heading) => heading.textContent);
}

describe("SF-15 index", () => {
  it("renders h1 Settings with one section and h2 per group, never a card grid; a member without settings permissions sees Your preferences only", async () => {
    const tenantReads = serveTenant(null);
    renderIndex(["contract.read", "contract.create"]);

    expect(await screen.findByRole("heading", { level: 1, name: "Settings" })).toBeTruthy();
    await waitFor(() => {
      expect(document.title).toBe("Settings · eRev Cloud");
    });
    const page = screen.getByTestId("SF-15-page");
    expect(page.querySelectorAll("section")).toHaveLength(2);
    expect(page.querySelectorAll("article")).toHaveLength(0);
    expect(groupHeadings()).toEqual(["Your preferences", "Reference data"]);

    const preferences = within(page).getByRole("region", { name: "Your preferences" });
    const table = within(preferences).getByRole("table", { name: "Your preferences" });
    expect(within(table).queryAllByRole("columnheader")).toHaveLength(0);
    expect(
      within(preferences).getByRole("link", { name: "Notifications" }).getAttribute("href"),
    ).toBe("/settings/notifications");
    expect(within(preferences).getByRole("link", { name: "Profile" }).getAttribute("href")).toBe(
      "/settings/profile",
    );
    expect(
      within(screen.getByTestId("SF-15-row-notifications")).getByText(
        "Choose which notifications you receive in the app and by email",
      ),
    ).toBeTruthy();
    expect(
      within(screen.getByTestId("SF-15-row-profile")).getByText(
        "Multi-factor authentication, formats, theme and density",
      ),
    ).toBeTruthy();

    // contract.read admits Customers (RFD-20) and Products (RFD-21), both built.
    const reference = within(page).getByRole("region", { name: "Reference data" });
    expect(within(reference).getByRole("link", { name: "Customers" }).getAttribute("href")).toBe(
      "/settings/customers",
    );
    expect(
      within(reference).getByRole("link", { name: "Related-party groups" }).getAttribute("href"),
    ).toBe("/settings/related-party-groups");
    expect(within(reference).getByRole("link", { name: "Products" }).getAttribute("href")).toBe(
      "/settings/products",
    );
    expect(screen.queryByTestId("SF-15-banner-setup")).toBeNull();
    expect(tenantReads.count()).toBe(0);
  });

  it("each link renders only when the user holds its page's read permission and the page is built", async () => {
    // Every settings page is built; this render leaves SF-16:developer (WEB-23) out of the route table
    // so it stands for "readable but not built" (XR-14).
    const extra: RouteObject[] = [];
    renderApp("/settings", {
      me: signedInMe({ permissions: ["config.read", "api_client.manage"] }),
      screenRoutes: SCREEN_ROUTES.filter((route) => route.id !== "SF-16:developer"),
    });

    const workspace = await screen.findByRole("region", { name: "Workspace" });
    expect(within(workspace).getByRole("link", { name: "Entities" }).getAttribute("href")).toBe(
      "/settings/entities",
    );
    expect(screen.getByTestId("SF-15-row-entities")).toBeTruthy();
    expect(within(workspace).getByRole("link", { name: "Calendars" }).getAttribute("href")).toBe(
      "/settings/calendars",
    );
    // Readable with api_client.manage, but not built (WEB-23).
    expect(screen.queryByRole("link", { name: "API clients and webhooks" })).toBeNull();
    // Built, but role.manage is not held.
    expect(screen.queryByRole("link", { name: "Roles" })).toBeNull();
    expect(groupHeadings()).toEqual(["Your preferences", "Workspace"]);
    cleanup();

    renderIndex(["config.read", "role.manage"], extra);
    const access = await screen.findByRole("region", { name: "Access" });
    expect(within(access).getByRole("link", { name: "Roles" }).getAttribute("href")).toBe(
      "/settings/roles",
    );
    expect(
      within(access).getByRole("link", { name: "Separation of duties" }).getAttribute("href"),
    ).toBe("/settings/separation-of-duties");
    // Built, but user.manage and access.approve are not held.
    expect(within(access).queryByRole("link", { name: "Users" })).toBeNull();
    expect(groupHeadings()).toEqual(["Your preferences", "Workspace", "Access"]);
  });

  it("a settings.manage holder with setup_completed_at null sees Workspace setup is not complete. with Finish setup only once SF-15:setup is built", async () => {
    serveTenant(null);
    // RFD-19 built SF-15:setup; this render leaves it out of the route table.
    renderApp("/settings", {
      me: signedInMe({ permissions: ["settings.manage"] }),
      screenRoutes: SCREEN_ROUTES.filter((route) => route.id !== "SF-15:setup"),
    });

    const banner = await screen.findByTestId("SF-15-banner-setup");
    expect(within(banner).getByRole("status")).toBeTruthy();
    expect(within(banner).getByText("Workspace setup is not complete.")).toBeTruthy();
    expect(within(banner).queryByRole("link", { name: "Finish setup" })).toBeNull();
    cleanup();

    serveTenant(null);
    renderIndex(["settings.manage"]);
    const withSetup = await screen.findByTestId("SF-15-banner-setup");
    expect(within(withSetup).getByRole("link", { name: "Finish setup" }).getAttribute("href")).toBe(
      "/settings/setup",
    );
    expect(
      within(screen.getByRole("region", { name: "Workspace" })).getByRole("link", {
        name: "Setup",
      }),
    ).toBeTruthy();
    cleanup();

    const reads = serveTenant("2026-09-02T10:00:00Z");
    const { queryClient } = renderIndex(["settings.manage"]);
    await waitFor(() => {
      expect(queryClient.getQueryData(tenantKey())).toBeDefined();
    });
    expect(reads.count()).toBe(1);
    expect(screen.queryByTestId("SF-15-banner-setup")).toBeNull();
  });

  // W-12e: `GET /tenant` answers a holder of settings.manage for all entities alone. A holder for one
  // entity sent the read from the index and was refused.
  it("settings.manage for one entity alone: the index does not ask for the tenant and shows no setup banner", async () => {
    const reads = serveTenant(null);
    serveEntities();
    renderApp("/settings", {
      me: signedInMe({
        permissions: ["settings.manage"],
        permission_scopes: { "settings.manage": [ONE_ENTITY] },
      }),
      screenRoutes: SCREEN_ROUTES,
    });

    expect(await screen.findByRole("heading", { level: 1, name: "Settings" })).toBeTruthy();
    await screen.findByRole("region", { name: "Your preferences" });
    expect(screen.queryByTestId("SF-15-banner-setup")).toBeNull();
    expect(reads.count()).toBe(0);
  });

  // W-12e, the supervisor's ruling of 2026-10-02 02:43 (Q3): a link asks what its page asks. Setup,
  // Workspace settings, Access reviews, Security, Support access and Sandbox copies are pages of the
  // whole workspace, read by a holder for all entities alone (SCREENS §0.6 SCR-PERM-02 (c)); so are
  // the webhooks of the developer page, whose API clients are a tenant-wide object. A holder for one
  // entity was shown seven links to pages that answered "You do not have access".
  it("a holder for one entity alone is shown no link to a page of the whole workspace; held for all entities each link is listed", async () => {
    const workspaceWide = [
      "settings.manage",
      "access.approve",
      "support_grant.approve",
      "tenant.snapshot",
      "webhook.manage",
    ];
    const linksOf = (region: string) =>
      within(screen.getByRole("region", { name: region }))
        .getAllByRole("link")
        .map((link) => link.textContent);
    serveEntities();
    renderApp("/settings", {
      me: signedInMe({
        permissions: ["config.read", "role.manage", "user.manage", ...workspaceWide],
        permission_scopes: {
          "config.read": "*",
          "role.manage": "*",
          "user.manage": [ONE_ENTITY],
          ...Object.fromEntries(workspaceWide.map((code) => [code, [ONE_ENTITY]])),
        },
      }),
      screenRoutes: SCREEN_ROUTES,
    });

    await screen.findByRole("region", { name: "Workspace" });
    expect(linksOf("Workspace")).toEqual([
      "Entities",
      "Calendars",
      "Currencies and rates",
      "Chart of accounts",
    ]);
    // The users are read with user.manage for any entity (question (b)): held for one, the link stays.
    expect(linksOf("Access")).toEqual(["Users", "Roles", "Separation of duties"]);
    expect(groupHeadings()).toEqual(["Your preferences", "Workspace", "Access"]);
    cleanup();

    serveTenant("2026-09-02T10:00:00Z");
    renderIndex(["config.read", "role.manage", "user.manage", ...workspaceWide]);
    await screen.findByRole("region", { name: "Workspace" });
    expect(linksOf("Workspace")).toEqual([
      "Setup",
      "Entities",
      "Calendars",
      "Currencies and rates",
      "Chart of accounts",
      "Workspace settings",
    ]);
    expect(linksOf("Access")).toEqual([
      "Users",
      "Roles",
      "Separation of duties",
      "Access reviews",
      "Security",
      "Support access",
    ]);
    expect(linksOf("Developer")).toEqual(["API clients and webhooks"]);
    expect(linksOf("Sandbox")).toEqual(["Sandbox copies"]);
    cleanup();

    // The developer page keeps its link for the API clients alone.
    serveEntities();
    renderApp("/settings", {
      me: signedInMe({
        permissions: ["api_client.manage", "webhook.manage"],
        permission_scopes: { "api_client.manage": [ONE_ENTITY], "webhook.manage": [ONE_ENTITY] },
      }),
      screenRoutes: SCREEN_ROUTES,
    });
    await screen.findByRole("region", { name: "Developer" });
    expect(linksOf("Developer")).toEqual(["API clients and webhooks"]);
  });

  // The links of the index and the tabs of every settings page ask one function, `mayRead`.
  it("a page of the whole workspace is read with its permission held for all entities, by the index and by the tabs of a settings page alike", () => {
    const pages = SETTINGS_GROUPS.flatMap((group) => group.pages);
    expect(
      pages
        .filter((candidate) => candidate.workspaceWide.length > 0)
        .map((candidate) => [candidate.screen, candidate.workspaceWide]),
    ).toEqual([
      ["SF-15:setup", ["settings.manage"]],
      ["SF-15:workspace", ["settings.manage"]],
      ["SF-14:access-reviews", ["access.approve"]],
      ["SF-14:security", ["settings.manage"]],
      ["SF-14:support-access", ["support_grant.approve"]],
      ["SF-16:developer", ["webhook.manage"]],
      ["SF-15:sandbox", ["tenant.snapshot"]],
    ]);
    for (const candidate of pages) {
      for (const code of candidate.workspaceWide) {
        const forOne = accessOf(
          signedInMe({ permissions: [code], permission_scopes: { [code]: [ONE_ENTITY] } }),
        );
        const forAll = accessOf(signedInMe({ permissions: [code] }));
        expect([candidate.screen, mayRead(candidate, forOne), mayRead(candidate, forAll)]).toEqual([
          candidate.screen,
          false,
          true,
        ]);
      }
    }
  });

  it("read permissions are any-of, and a group without a readable built page is not listed", () => {
    const pages = SETTINGS_GROUPS.flatMap((group) => group.pages);
    const callLog = pages.find((candidate) => candidate.screen === "SF-15:ai-call-log");
    const profile = pages.find((candidate) => candidate.screen === "SF-15:profile");
    const holding = (permissions: string[]) => accessOf(signedInMe({ permissions }));
    expect(callLog === undefined ? null : mayRead(callLog, holding(["ai.use"]))).toBe(true);
    expect(callLog === undefined ? null : mayRead(callLog, holding(["contract.read"]))).toBe(false);
    expect(profile === undefined ? null : mayRead(profile, holding([]))).toBe(true);

    expect(SETTINGS_GROUPS.map((group) => group.id)).toEqual([
      "preferences",
      "workspace",
      "reference",
      "access",
      "developer",
      "ai",
      "sandbox",
    ]);
    expect(
      visibleGroups(holding([]), new Set(["/settings/profile", "/settings/users"])).map((group) => [
        group.id,
        group.pages.map((candidate) => candidate.screen),
      ]),
    ).toEqual([["preferences", ["SF-15:profile"]]]);
  });
});
