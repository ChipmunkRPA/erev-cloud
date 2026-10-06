// @vitest-environment jsdom
// SF-22:password-change (BUILD_SPEC WEB-14; SCREENS_B §12.3; 04 API-R-03 `POST /me/password`; SAR-10):
// a 422 on current_password shows the wrong-password copy; success shows the toast and the request
// carries both passwords; the route is authenticated and outside the shell.
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { PUBLIC_ROUTES, SESSION_ROUTES } from "../../app/router";
import { probeRoute, renderApp, signedInMe, signedInSession } from "../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";

installMswServer();

const HOME = probeRoute("SF-01", "/home", "shell.rail.home");

function renderChange() {
  return renderApp("/password/change", {
    session: signedInSession(),
    me: signedInMe(),
    badge: null,
    publicRoutes: PUBLIC_ROUTES,
    sessionRoutes: SESSION_ROUTES,
    screenRoutes: [HOME],
  });
}

function fill(current: string, next: string, confirm = next): void {
  fireEvent.change(screen.getByLabelText("Current password"), { target: { value: current } });
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: next } });
  fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: confirm } });
  fireEvent.click(screen.getByRole("button", { name: "Change password" }));
}

beforeEach(() => {
  window.history.replaceState(null, "", "/password/change");
  server.use(
    http.get(apiUrl("/api/v1/session"), () => HttpResponse.json(signedInSession())),
    http.get(apiUrl("/api/v1/me"), () => HttpResponse.json(signedInMe())),
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
  );
});

afterEach(() => {
  cleanup();
});

describe("SF-22:password-change", () => {
  it("a 422 on current_password shows The current password is incorrect.", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(apiUrl("/api/v1/me/password"), async ({ request }) => {
        bodies.push(await request.json());
        return problemResponse("validation-failed", 422, "Validation failed", {
          detail: "The current password is incorrect.",
          errors: [
            {
              field: "current_password",
              sheet: null,
              row: null,
              rule_id: null,
              message: "The current password is incorrect.",
            },
          ],
        });
      }),
    );
    renderChange();
    expect(await screen.findByRole("heading", { level: 1, name: "Change password" })).toBeTruthy();
    expect(screen.getByLabelText("Current password").getAttribute("autocomplete")).toBe(
      "current-password",
    );

    fill("wrong-old", "Maya!Revenue2026");
    expect(
      (await screen.findAllByText("The current password is incorrect.")).length,
    ).toBeGreaterThan(0);
    expect(screen.getByLabelText("Current password").getAttribute("aria-invalid")).toBe("true");
    expect(bodies).toEqual([{ current_password: "wrong-old", new_password: "Maya!Revenue2026" }]);
  });

  it("success shows the toast Password changed. Your other sessions were signed out.", async () => {
    server.use(
      http.post(apiUrl("/api/v1/me/password"), () => new HttpResponse(null, { status: 204 })),
    );
    const { router } = renderChange();
    await screen.findByRole("heading", { level: 1, name: "Change password" });

    fill("Maya!Revenue2025", "Maya!Revenue2026");
    await waitFor(() => {
      expect(
        screen.getByText("Password changed. Your other sessions were signed out."),
      ).toBeTruthy();
    });
    // SCREENS_B rev 1.8 (Q5): after the toast the page opens the landing route.
    expect(await screen.findByRole("heading", { level: 1, name: "Home" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/home");
  });
});
