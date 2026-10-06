// @vitest-environment jsdom
// SF-14:security (BUILD_SPEC WEB-22; SCREENS_B §9.14; 04 §16.12 API-S-Session; BS1-D-15): the region
// "Sign-in methods" lists "Email and password" with the chip "Active" and the identity providers of the
// `GET /session` capabilities, or "OIDC none configured"; the region "Password rules" lists the four rules
// as a list; the "Multi-factor authentication" text; no "Sessions" form renders.
import { cleanup, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { accessDescription } from "../../test/access";
import { installMemoryStorage, renderApp, signedInMe, signedInSession } from "../../test/app";
import { apiUrl, installMswServer, server } from "../../test/msw";
import { passwordRuleKeys } from "./security";

installMswServer();
installMemoryStorage();

afterEach(() => {
  cleanup();
});

const TOMAS = signedInMe({ permissions: ["settings.manage", "user.manage"] });

function serveShell() {
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
  );
}

describe("SF-14:security", () => {
  it("the region Sign-in methods lists Email and password with the chip Active and the identity providers of GET /session", async () => {
    serveShell();
    renderApp("/settings/security", {
      me: TOMAS,
      session: signedInSession({
        capabilities: { identity_providers: [{ code: "okta", name: "Okta" }] },
      }),
      screenRoutes: SCREEN_ROUTES,
    });

    const signIn = await screen.findByRole("region", { name: "Sign-in methods" });
    const rows = within(signIn)
      .getAllByRole("listitem")
      .map((item) => item.textContent ?? "");
    expect(rows).toEqual(["Email and passwordActive", "OktaActive"]);
    expect(within(signIn).queryByText("none configured")).toBeNull();
    expect(screen.getByRole("heading", { level: 1, name: "Security" })).toBeTruthy();
  });

  it("without an identity provider the region reads OIDC none configured", async () => {
    serveShell();
    renderApp("/settings/security", { me: TOMAS, screenRoutes: SCREEN_ROUTES });

    const signIn = await screen.findByRole("region", { name: "Sign-in methods" });
    const rows = within(signIn)
      .getAllByRole("listitem")
      .map((item) => item.textContent ?? "");
    expect(rows).toEqual(["Email and passwordActive", "OIDCnone configured"]);
  });

  it("the region Password rules is a list of the four rules, the MFA text reads as specified and no Sessions form renders", async () => {
    serveShell();
    renderApp("/settings/security", { me: TOMAS, screenRoutes: SCREEN_ROUTES });

    const rules = await screen.findByRole("region", { name: "Password rules" });
    expect(rules.getAttribute("data-testid")).toBe("SF-14-security-password-rules");
    const list = within(rules).getByRole("list");
    expect(
      within(list)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual([
      "At least 12 characters",
      "not your email address",
      "not a common password",
      "five failed attempts lock for 15 minutes",
    ]);
    expect(passwordRuleKeys()).toHaveLength(4);

    const mfa = screen.getByRole("region", { name: "Multi-factor authentication" });
    expect(
      within(mfa).getByText(
        "Required for members holding approval, lock, access administration, integration or sandbox permissions.",
      ),
    ).toBeTruthy();

    // BS1-D-15: the "Sessions" form (API-R-13) is not part of WEB-22.
    expect(screen.queryByRole("form", { name: "Sessions" })).toBeNull();
    expect(screen.queryByTestId("SF-14-security-form")).toBeNull();
    expect(screen.queryByText("Idle timeout")).toBeNull();
    expect(screen.queryByText("Role assignments need approval")).toBeNull();
    expect(screen.queryByRole("button", { name: "Submit for approval" })).toBeNull();
  });

  it("without settings.manage the page shows the access empty state (SCR-PERM-01)", async () => {
    serveShell();
    renderApp("/settings/security", {
      me: signedInMe({ permissions: ["contract.read"] }),
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("heading", { name: "You do not have access to Security" }),
    ).toBeTruthy();
    expect(screen.getByText(/managing workspace settings/)).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Sign-in methods" })).toBeNull();
  });
});

// W-12e, the supervisor's ruling of 2026-10-02 02:43 (Q2; SCREENS §0.6 SCR-PERM-02 (c)): the sign-in
// rules are the workspace's, so the page is read by a holder of settings.manage for all entities.
describe("SF-14:security, a holder for named entities", () => {
  it("settings.manage for one entity alone: the page says that security covers every entity", async () => {
    serveShell();
    renderApp("/settings/security", {
      me: signedInMe({
        permissions: ["settings.manage"],
        permission_scopes: { "settings.manage": ["0a1b2c3d-4e5f-4a6b-8c7d-0000000000de"] },
      }),
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("heading", { name: "You do not have access to Security" }),
    ).toBeTruthy();
    expect(accessDescription()).toBe(
      "Security covers every entity of the workspace. Ask a workspace administrator for a role that includes managing workspace settings (settings.manage) for all entities.",
    );
    expect(screen.queryByRole("region", { name: "Sign-in methods" })).toBeNull();
  });
});
