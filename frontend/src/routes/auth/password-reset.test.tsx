// @vitest-environment jsdom
// SF-22:password-reset and SF-22:password-reset-confirm (BUILD_SPEC WEB-14; SCREENS_B §12.3; 04
// API-R-01 `POST /session/password-reset`, `POST /session/password-reset/confirm`; T-PLT-42; ERR-21):
// the status after a request never reveals account existence; the confirm page reads its token from
// the fragment and sends it only in the body; an invalid token shows the expired-link state with a
// link to request a new one; a mismatch is refused before any request; success links to sign-in.
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { SessionState } from "../../app/auth/RequireSession";
import { PUBLIC_ROUTES } from "../../app/router";
import { probeRoute, renderApp } from "../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";

installMswServer();

const ANONYMOUS: SessionState = { authenticated: false, capabilities: { identity_providers: [] } };
const HOME = probeRoute("SF-01", "/home", "shell.rail.home");
/** A fixture reset token; only its shape matters to the page. */
const RESET_TOKEN = "reset-7f3a";

function renderPublic(entry: string) {
  return renderApp(entry, {
    session: ANONYMOUS,
    me: null,
    badge: null,
    publicRoutes: PUBLIC_ROUTES,
    screenRoutes: [HOME],
  });
}

beforeEach(() => {
  window.history.replaceState(null, "", "/password/reset");
});

afterEach(() => {
  cleanup();
});

describe("SF-22:password-reset and confirm", () => {
  it("after submitting maya@demo.erev the status reads the same for any account", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(apiUrl("/api/v1/session/password-reset"), async ({ request }) => {
        bodies.push(await request.json());
        return new HttpResponse(null, { status: 202 });
      }),
    );
    renderPublic("/password/reset");

    fireEvent.change(await screen.findByRole("textbox", { name: "Email" }), {
      target: { value: "maya@demo.erev" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send reset link" }));

    // The announcer's live region is also role="status", so the page's status is found by its hook.
    const status = await screen.findByTestId("SF-22-banner-reset-sent");
    expect(status.getAttribute("role")).toBe("status");
    expect(status.textContent).toBe(
      "If an account exists for maya@demo.erev, we sent a link to reset the password. The link expires in 60 minutes.",
    );
    expect(bodies).toEqual([{ email: "maya@demo.erev" }]);
    expect(screen.getByRole("link", { name: "Back to sign in" }).getAttribute("href")).toBe(
      "/sign-in",
    );
  });

  it("the confirm page with an invalid token shows This reset link has expired. Request a new link.", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(apiUrl("/api/v1/session/password-reset/confirm"), async ({ request }) => {
        bodies.push(await request.json());
        return problemResponse("not-found", 404, "Not found", { detail: "Unknown token." });
      }),
    );
    const { router } = renderPublic("/password/reset/confirm#token=invalid");

    const newPassword = await screen.findByLabelText("New password");
    expect(newPassword.getAttribute("autocomplete")).toBe("new-password");
    fireEvent.change(newPassword, { target: { value: "Maya!Revenue2026" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "Maya!Revenue2026" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Reset password" }));

    expect(
      await screen.findByText("This reset link has expired. Request a new link."),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "Request a new link" }).getAttribute("href")).toBe(
      "/password/reset",
    );
    expect(bodies).toEqual([{ token: "invalid", new_password: "Maya!Revenue2026" }]);
    expect(router.state.location.search).toBe("");
    // The expired state replaces the form (SCREENS_B §12.3).
    expect(screen.queryByLabelText("New password")).toBeNull();
  });

  it("a mismatch is refused before any request and success reads Password reset. Sign in with your new password.", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(apiUrl("/api/v1/session/password-reset/confirm"), async ({ request }) => {
        bodies.push(await request.json());
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderPublic(`/password/reset/confirm#token=${RESET_TOKEN}`);

    fireEvent.change(await screen.findByLabelText("New password"), {
      target: { value: "Maya!Revenue2026" },
    });
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "Maya!Revenue2027" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Reset password" }));
    expect(await screen.findByText("The passwords do not match.")).toBeTruthy();
    expect(bodies).toEqual([]);

    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "Maya!Revenue2026" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Reset password" }));
    expect(await screen.findByText("Password reset. Sign in with your new password.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Sign in" }).getAttribute("href")).toBe("/sign-in");
    await waitFor(() => {
      expect(bodies).toEqual([{ token: RESET_TOKEN, new_password: "Maya!Revenue2026" }]);
    });
  });

  it("a weak password shows the ERR-21 copy the API answers", async () => {
    server.use(
      http.post(apiUrl("/api/v1/session/password-reset/confirm"), () =>
        problemResponse("password-policy", 422, "Choose another password", {
          detail: "Use at least 12 characters.",
          errors: [
            {
              field: "new_password",
              sheet: null,
              row: null,
              rule_id: null,
              message: "Use at least 12 characters.",
            },
          ],
        }),
      ),
    );
    renderPublic(`/password/reset/confirm#token=${RESET_TOKEN}`);
    fireEvent.change(await screen.findByLabelText("New password"), { target: { value: "short" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "short" } });
    fireEvent.click(screen.getByRole("button", { name: "Reset password" }));
    const policy = await screen.findByTestId("SF-22-banner-password-policy");
    expect(policy.textContent).toContain("Use at least 12 characters.");
  });

  it("a confirm link without a token explains that the link is incomplete", async () => {
    renderPublic("/password/reset/confirm");
    expect(
      await screen.findByText("This reset link is incomplete. Open the link from the email."),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Reset password" })).toBeNull();
  });
});
