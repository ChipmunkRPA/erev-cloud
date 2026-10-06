// @vitest-environment jsdom
// SF-22:mfa-challenge (BUILD_SPEC WEB-12; SCREENS_B §12.1; 04 API-R-01 `POST /session/mfa`,
// `POST /session/logout`; BS1-D-30): the wrong-code copy, the swap to a recovery code, the recovery
// code toast, "Sign in as someone else" and the one-time-code autocomplete.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { SessionState } from "../../app/auth/RequireSession";
import { PUBLIC_ROUTES } from "../../app/router";
import type { components } from "../../lib/api/schema";
import { probeRoute, renderApp, signedInMe, signedInSession } from "../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { challengePending } from "./mfa-challenge";

installMswServer();

type SessionLoginOut = components["schemas"]["SessionLoginOut"];
type SessionMfaOut = components["schemas"]["SessionMfaOut"];

const PENDING: SessionLoginOut = {
  ...signedInSession({ mfa_verified_at: null }),
  mfa_required: true,
  mfa_enrolment_required: false,
};

const ANONYMOUS: SessionState = { authenticated: false, capabilities: { identity_providers: [] } };

const HOME = probeRoute("SF-01", "/home", "shell.rail.home");

beforeEach(() => {
  // A 401 redirect of the client stays on the page under test (lib/api/client.ts).
  window.history.replaceState(null, "", "/sign-in");
});

afterEach(() => {
  cleanup();
});

function renderChallenge(session: SessionState = PENDING, entry = "/sign-in/mfa") {
  return renderApp(entry, {
    session,
    me: null,
    badge: null,
    publicRoutes: PUBLIC_ROUTES,
    screenRoutes: [HOME],
  });
}

function shellReads(): void {
  server.use(
    http.get(apiUrl("/api/v1/me"), () => HttpResponse.json(signedInMe())),
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
  );
}

function verified(remaining: number | null): SessionMfaOut {
  return { ...signedInSession(), recovery_codes_remaining: remaining };
}

describe("SF-22:mfa-challenge", () => {
  it("a wrong code shows That code did not match. Check your authenticator app and try again.", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(apiUrl("/api/v1/session/mfa"), async ({ request }) => {
        bodies.push(await request.json());
        return problemResponse("validation-failed", 422, "Validation failed", {
          detail: "That code did not match. Check your authenticator app and try again.",
          errors: [
            {
              field: "code",
              sheet: null,
              row: null,
              rule_id: null,
              message: "That code did not match. Check your authenticator app and try again.",
            },
          ],
        });
      }),
    );
    renderChallenge();

    fireEvent.change(await screen.findByRole("textbox", { name: "Authentication code" }), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify" }));

    const banner = await screen.findByTestId("SF-22-banner-error");
    expect(within(banner).getByRole("alert").textContent).toBe(
      "That code did not match. Check your authenticator app and try again.",
    );
    const field = screen.getByRole("textbox", { name: "Authentication code" });
    expect(field.getAttribute("aria-invalid")).toBe("true");
    expect(field.getAttribute("aria-describedby")).toContain(banner.id);
    expect(bodies).toEqual([{ code: "123456" }]);
  });

  it("Use a recovery code instead swaps the field to Recovery code", async () => {
    renderChallenge();
    expect(
      await screen.findByText("Enter the 6-digit code from your authenticator app."),
    ).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Use a recovery code instead" }));

    const recovery = screen.getByRole("textbox", { name: "Recovery code" });
    expect(recovery.getAttribute("autocomplete")).toBe("off");
    expect(document.activeElement).toBe(recovery);
    expect(screen.queryByRole("textbox", { name: "Authentication code" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Use an authentication code instead" }));
    expect(screen.getByRole("textbox", { name: "Authentication code" })).toBeTruthy();
  });

  it("after a recovery-code sign-in the toast reads You used a recovery code. <n> codes remain.", async () => {
    const bodies: unknown[] = [];
    shellReads();
    server.use(
      http.post(apiUrl("/api/v1/session/mfa"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(verified(7));
      }),
    );
    const { router } = renderChallenge();

    fireEvent.click(await screen.findByRole("button", { name: "Use a recovery code instead" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Recovery code" }), {
      target: { value: " k7q2-9xm4 " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify" }));

    expect(await screen.findByText("You used a recovery code. 7 codes remain.")).toBeTruthy();
    expect(await screen.findByRole("heading", { level: 1, name: "Home" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/home");
    expect(bodies).toEqual([{ recovery_code: "k7q2-9xm4" }]);
  });

  it("a TOTP sign-in shows no toast and opens the safe next path", async () => {
    shellReads();
    server.use(http.post(apiUrl("/api/v1/session/mfa"), () => HttpResponse.json(verified(null))));
    const { router } = renderChallenge(PENDING, "/sign-in/mfa?next=%2Fhome%3Ftab%3Da");

    fireEvent.change(await screen.findByRole("textbox", { name: "Authentication code" }), {
      target: { value: "654321" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/home");
    });
    expect(router.state.location.search).toBe("?tab=a");
    expect(screen.queryByText(/You used a recovery code/)).toBeNull();
  });

  it("Sign in as someone else ends the pending session", async () => {
    let logouts = 0;
    server.use(
      http.post(apiUrl("/api/v1/session/logout"), () => {
        logouts += 1;
        return new HttpResponse(null, { status: 204 });
      }),
      http.get(apiUrl("/api/v1/session"), () => HttpResponse.json(ANONYMOUS)),
    );
    const { router } = renderChallenge();

    fireEvent.click(await screen.findByRole("button", { name: "Sign in as someone else" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/sign-in");
    expect(logouts).toBe(1);
  });

  it("the code field uses autocomplete one-time-code", async () => {
    renderChallenge();
    const code = await screen.findByRole("textbox", { name: "Authentication code" });
    expect(code.getAttribute("autocomplete")).toBe("one-time-code");
    expect(code.getAttribute("inputmode")).toBe("numeric");
    expect(screen.getByRole("heading", { level: 1, name: "Verify your sign-in" })).toBeTruthy();
    // The title is set in a passive effect after the lazily loaded route's first commit (F-ADM Q21).
    await waitFor(() => {
      expect(document.title).toBe("Verify your sign-in · eRev Cloud");
    });
  });

  it("no session opens sign-in; a verified session leaves for its destination", async () => {
    const { router } = renderChallenge(ANONYMOUS, "/sign-in/mfa?next=%2Fhome");
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeTruthy();
    expect(router.state.location.search).toBe("?next=%2Fhome");
    cleanup();

    expect(challengePending(PENDING)).toBe(true);
    expect(challengePending(signedInSession())).toBe(false);
    const passwordOnly: SessionLoginOut = { ...PENDING, mfa_required: false };
    expect(challengePending(passwordOnly)).toBe(false);
    expect(challengePending(ANONYMOUS)).toBe(false);
  });
});
