// @vitest-environment jsdom
// SF-22 copy and behaviour (BUILD_SPEC WEB-11; SCREENS_B §12.1; SCREENS SCR-URL-30; DESIGN_SYSTEM
// DS-A11Y-17): refused sign-in copy for 401, 423 and 429, the session-expired notice, password manager
// autocomplete, the Show toggle, OIDC buttons from `GET /session` capabilities, and `next` handling.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { SessionState } from "../../app/auth/RequireSession";
import { PUBLIC_ROUTES } from "../../app/router";
import type { components } from "../../lib/api/schema";
import { probeRoute, renderApp, signedInMe, signedInSession } from "../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { destinationAfterSignIn, oidcStartPath, safeNext } from "./sign-in";

installMswServer();

type SessionLoginOut = components["schemas"]["SessionLoginOut"];

const ANONYMOUS: SessionState = {
  authenticated: false,
  capabilities: { identity_providers: [{ code: "mock-idp", name: "Mock IdP" }] },
};

const HOME = probeRoute("SF-01", "/home", "shell.rail.home");
const PROFILE = probeRoute("SF-15:profile", "/settings/profile", "shell.rail.settings");

beforeEach(() => {
  // The page is on /sign-in, so the client's 401 redirect stays on this page (lib/api/client.ts).
  window.history.replaceState(null, "", "/sign-in");
});

afterEach(() => {
  cleanup();
});

function renderSignIn(entry: string) {
  return renderApp(entry, {
    session: ANONYMOUS,
    me: null,
    badge: null,
    publicRoutes: PUBLIC_ROUTES,
    screenRoutes: [HOME, PROFILE],
  });
}

async function submitCredentials(): Promise<void> {
  fireEvent.change(await screen.findByLabelText("Email"), {
    target: { value: "maya@example.test" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "correct horse battery staple" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

function refuseLogin(response: () => Response): void {
  server.use(http.post(apiUrl("/api/v1/session/login"), response));
}

function acceptLogin(bodies: unknown[] = []): void {
  const answered: SessionLoginOut = {
    ...signedInSession(),
    mfa_verified_at: null,
    mfa_required: false,
    mfa_enrolment_required: false,
  };
  server.use(
    http.post(apiUrl("/api/v1/session/login"), async ({ request }) => {
      bodies.push(await request.json());
      return HttpResponse.json(answered);
    }),
    http.get(apiUrl("/api/v1/me"), () => HttpResponse.json(signedInMe())),
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
  );
}

describe("SF-22 copy and behaviour", () => {
  it("a 401 shows The email or password is incorrect. and marks both fields", async () => {
    refuseLogin(() => problemResponse("unauthenticated", 401, "Authentication required"));
    renderSignIn("/sign-in");
    await submitCredentials();

    const banner = await screen.findByTestId("SF-22-banner-error");
    expect(within(banner).getByRole("alert").textContent).toBe(
      "The email or password is incorrect.",
    );
    expect(screen.getByLabelText("Email").getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByLabelText("Password").getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByLabelText("Email").getAttribute("aria-describedby")).toBe(banner.id);
  });

  it("a 423 shows the lockout copy", async () => {
    refuseLogin(() => problemResponse("account-locked", 423, "Account locked"));
    renderSignIn("/sign-in");
    await submitCredentials();

    expect((await screen.findByTestId("SF-22-banner-error")).textContent).toBe(
      "Too many failed sign-in attempts. Try again in 15 minutes or ask a workspace administrator.",
    );
  });

  it("?reason=session-expired with idle 30 minutes shows the session-ended notice", async () => {
    renderSignIn("/sign-in?reason=session-expired");
    expect(
      await screen.findByText(
        "Your session ended after 30 minutes without activity. Sign in again.",
      ),
    ).toBeTruthy();
    cleanup();

    renderSignIn("/sign-in?reason=other");
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeTruthy();
    expect(screen.queryByText(/Your session ended/)).toBeNull();
  });

  it("a 429 with Retry-After: 42 shows Too many sign-in attempts. Try again in 42 seconds.", async () => {
    refuseLogin(() =>
      HttpResponse.json(
        {
          type: "https://erev.dev/problems/rate-limited",
          title: "Too many requests",
          status: 429,
          instance: "urn:erev:request:0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d",
          errors: [],
        },
        {
          status: 429,
          headers: { "Content-Type": "application/problem+json", "Retry-After": "42" },
        },
      ),
    );
    renderSignIn("/sign-in");
    await submitCredentials();

    expect((await screen.findByTestId("SF-22-banner-error")).textContent).toBe(
      "Too many sign-in attempts. Try again in 42 seconds.",
    );
  });

  it("Email uses autocomplete username and Password current-password; Show toggles aria-pressed", async () => {
    renderSignIn("/sign-in");
    const email = await screen.findByLabelText("Email");
    const password = screen.getByLabelText("Password");
    expect(email.getAttribute("autocomplete")).toBe("username");
    expect(password.getAttribute("autocomplete")).toBe("current-password");
    expect(password.getAttribute("type")).toBe("password");
    // The title is set in a passive effect after the commit (F-ADM latent-race sweep).
    await waitFor(() => {
      expect(document.title).toBe("Sign in · eRev Cloud");
    });

    const show = screen.getByRole("button", { name: "Show" });
    expect(show.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(show);
    expect(show.getAttribute("aria-pressed")).toBe("true");
    expect(password.getAttribute("type")).toBe("text");
    fireEvent.click(show);
    expect(show.getAttribute("aria-pressed")).toBe("false");
    expect(password.getAttribute("type")).toBe("password");
  });

  it("each identity provider of GET /session capabilities renders Sign in with <provider name>", async () => {
    const session: SessionState = {
      authenticated: false,
      capabilities: {
        identity_providers: [
          { code: "mock-idp", name: "Mock IdP" },
          { code: "okta", name: "Okta" },
        ],
      },
    };
    renderApp("/sign-in", { session, me: null, badge: null, publicRoutes: PUBLIC_ROUTES });

    const mock = await screen.findByRole("link", { name: "Sign in with Mock IdP" });
    expect(mock.getAttribute("href")).toBe("/api/v1/session/oidc/mock-idp/start");
    expect(screen.getByRole("link", { name: "Sign in with Okta" }).getAttribute("href")).toBe(
      "/api/v1/session/oidc/okta/start",
    );
    expect(oidcStartPath("a b")).toBe("/api/v1/session/oidc/a%20b/start");
  });

  it("next=//evil.test/x is dropped; sign-in opens the landing route", async () => {
    const bodies: unknown[] = [];
    acceptLogin(bodies);
    const { router } = renderSignIn("/sign-in?next=%2F%2Fevil.test%2Fx");
    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
    await submitCredentials();

    expect(await screen.findByRole("heading", { level: 1, name: "Home" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/home");
    expect(bodies).toEqual([
      { email: "maya@example.test", password: "correct horse battery staple" },
    ]);
  });

  it("next=/settings/profile is used after sign-in", async () => {
    acceptLogin();
    const { router } = renderSignIn("/sign-in?next=%2Fsettings%2Fprofile");
    await submitCredentials();

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/settings/profile");
    });
    expect(await screen.findByRole("heading", { level: 1, name: "Settings" })).toBeTruthy();
  });

  it("a session that is live when the page opens leaves for next at once, without the form", async () => {
    // 05 SAR-09 rev 1.178: of two requests that present one session — two tabs that choose a
    // workspace — the second is answered 401 and the client sends its tab here with `next`
    // (lib/api/client.ts). The cookie the browser holds is by then the first request's successor,
    // so `GET /session` answers a live session and the tab goes back to where it was.
    server.use(
      http.get(apiUrl("/api/v1/session"), () => HttpResponse.json(signedInSession())),
      http.get(apiUrl("/api/v1/me"), () => HttpResponse.json(signedInMe())),
      http.get(apiUrl("/api/v1/me/notifications"), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
    const { router } = renderApp("/sign-in?next=%2Fsettings%2Fprofile", {
      session: null,
      me: null,
      badge: null,
      publicRoutes: PUBLIC_ROUTES,
      screenRoutes: [HOME, PROFILE],
    });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/settings/profile");
    });
    expect(await screen.findByRole("heading", { level: 1, name: "Settings" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Sign in" })).toBeNull();
    expect(screen.queryByText(/Your session ended/)).toBeNull();
  });

  it("Forgot password? opens SF-22:password-reset (WEB-14)", async () => {
    const { router } = renderSignIn("/sign-in");
    fireEvent.click(await screen.findByRole("link", { name: "Forgot password?" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Reset password" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/password/reset");
  });

  it("SCR-URL-30 next values and the MFA step", () => {
    expect(safeNext("/settings/profile?tab=a")).toBe("/settings/profile?tab=a");
    expect(safeNext("//evil.test/x")).toBeNull();
    expect(safeNext("/\\evil.test/x")).toBeNull();
    expect(safeNext("https://evil.test/x")).toBeNull();
    expect(safeNext("settings")).toBeNull();
    expect(safeNext(null)).toBeNull();

    const pending: SessionLoginOut = {
      ...signedInSession(),
      mfa_required: true,
      mfa_enrolment_required: false,
    };
    expect(destinationAfterSignIn(pending, "/settings/profile")).toBe(
      "/sign-in/mfa?next=%2Fsettings%2Fprofile",
    );
    expect(destinationAfterSignIn(pending, null)).toBe("/sign-in/mfa");
    expect(destinationAfterSignIn(signedInSession(), null)).toBe("/");

    // WEB-12: a session without a workspace goes to SF-23:select before `next` (L3-3-Q-10).
    const noWorkspace = signedInSession({ active_tenant: null });
    expect(destinationAfterSignIn(noWorkspace, null)).toBe("/select-workspace");
    expect(destinationAfterSignIn(noWorkspace, "/settings/profile")).toBe("/select-workspace");
    const pendingNoWorkspace: SessionLoginOut = { ...pending, active_tenant: null };
    expect(destinationAfterSignIn(pendingNoWorkspace, null)).toBe("/sign-in/mfa");
  });
});
