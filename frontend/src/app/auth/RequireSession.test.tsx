// @vitest-environment jsdom
// DG-FE-02 guards (docs/dev-guide.md §8.2; 03 REQ-PLT-005; SCREENS SCR-URL-30, RT-02, RT-03): without a
// session the router redirects to /sign-in?next=<path>; a user who must enrol reaches only /mfa/enrol,
// and a session that owes the challenge only /sign-in/mfa. The step is read from API-S-Session, so a
// reload keeps it (security review 2026-09-29 S21), and a call the API refuses because the session
// owes a step makes the guard read the session again.
import { act, cleanup, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { send } from "../../lib/api/client";
import { probeRoute, renderApp, signedInSession } from "../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { MFA_ENROL_PATH } from "./MfaGate";
import { MFA_CHALLENGE_PATH } from "./RequireSession";

installMswServer();

afterEach(() => {
  cleanup();
});

const TABLES = {
  publicRoutes: [
    probeRoute("SF-22", "/sign-in", "shell.productName"),
    probeRoute("SF-22:mfa-challenge", "/sign-in/mfa", "auth.mfa-challenge.title"),
  ],
  sessionRoutes: [probeRoute("SF-22:mfa-enrol", "/mfa/enrol", "shell.productName")],
  screenRoutes: [
    probeRoute("SF-12", "/approvals", "shell.rail.approvals"),
    probeRoute("SF-15:profile", "/settings/profile", "shell.rail.settings"),
  ],
};

describe("DG-FE-02 guards", () => {
  it("without a session the router redirects to /sign-in?next=<path>", async () => {
    let calls = 0;
    server.use(
      http.get(apiUrl("/api/v1/session"), () => {
        calls += 1;
        return HttpResponse.json({
          authenticated: false,
          capabilities: { identity_providers: [] },
        });
      }),
    );
    const { router } = renderApp("/approvals?view=mine", { ...TABLES, session: null });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/sign-in");
    });
    expect(new URLSearchParams(router.state.location.search).get("next")).toBe(
      "/approvals?view=mine",
    );
    expect(await screen.findByRole("heading", { level: 1, name: "eRev Cloud" })).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: "Primary" })).toBeNull();
    expect(calls).toBe(1);
  });

  it("a signed-in session is read once and the route renders in the shell", async () => {
    let calls = 0;
    server.use(
      http.get(apiUrl("/api/v1/session"), () => {
        calls += 1;
        return HttpResponse.json(signedInSession());
      }),
    );
    const { router } = renderApp("/approvals", { ...TABLES, session: null });

    expect(await screen.findByRole("heading", { level: 1, name: "Approvals" })).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeTruthy();
    await act(() => router.navigate("/settings/profile"));
    expect(await screen.findByRole("heading", { level: 1, name: "Settings" })).toBeTruthy();
    expect(calls).toBe(1);
  });

  it("with mfa_enrolment_required true, MfaGate makes /mfa/enrol the only reachable route", async () => {
    const { router } = renderApp("/approvals", {
      ...TABLES,
      session: signedInSession({ mfa_enrolment_required: true }),
    });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(MFA_ENROL_PATH);
    });
    expect(screen.queryByRole("navigation", { name: "Primary" })).toBeNull();
    for (const path of ["/settings/profile", "/some/unknown/path", "/", "/approvals?view=mine"]) {
      await act(() => router.navigate(path));
      await waitFor(() => {
        expect(router.state.location.pathname).toBe(MFA_ENROL_PATH);
      });
    }
    expect(screen.queryByRole("heading", { name: "Approvals" })).toBeNull();
  });

  it("after a reload GET /session still carries the enrolment step, so MfaGate holds", async () => {
    let reads = 0;
    server.use(
      http.get(apiUrl("/api/v1/session"), () => {
        reads += 1;
        return HttpResponse.json(
          signedInSession({ mfa_verified_at: null, mfa_enrolment_required: true }),
        );
      }),
    );
    // An empty cache is what a page reload leaves: the loader reads the session from the API.
    const { router } = renderApp("/approvals", { ...TABLES, session: null });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(MFA_ENROL_PATH);
    });
    expect(screen.queryByRole("heading", { name: "Approvals" })).toBeNull();
    expect(screen.queryByRole("navigation", { name: "Primary" })).toBeNull();
    expect(reads).toBe(1);
  });

  it("with mfa_required true every authenticated path opens the challenge with next", async () => {
    const { router } = renderApp("/approvals?view=mine", {
      ...TABLES,
      session: signedInSession({ mfa_verified_at: null, mfa_required: true }),
    });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(MFA_CHALLENGE_PATH);
    });
    expect(new URLSearchParams(router.state.location.search).get("next")).toBe(
      "/approvals?view=mine",
    );
    expect(
      await screen.findByRole("heading", { level: 1, name: "Verify your sign-in" }),
    ).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: "Primary" })).toBeNull();
    await act(() => router.navigate("/mfa/enrol"));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(MFA_CHALLENGE_PATH);
    });
    expect(new URLSearchParams(router.state.location.search).get("next")).toBe("/mfa/enrol");
  });

  it("a call refused because the session owes enrolment re-reads the session and opens /mfa/enrol", async () => {
    let reads = 0;
    server.use(
      http.get(apiUrl("/api/v1/session"), () => {
        reads += 1;
        return HttpResponse.json(
          signedInSession({ mfa_verified_at: null, mfa_enrolment_required: true }),
        );
      }),
      http.get(apiUrl("/api/v1/contracts"), () =>
        problemResponse("mfa-required", 403, "Multi-factor authentication required"),
      ),
    );
    // The cached session owes nothing: the role that makes MFA mandatory was granted afterwards.
    const { router } = renderApp("/approvals", { ...TABLES, session: signedInSession() });
    expect(await screen.findByRole("heading", { level: 1, name: "Approvals" })).toBeTruthy();
    expect(reads).toBe(0);

    await act(async () => {
      await send("GET", "/api/v1/contracts");
    });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(MFA_ENROL_PATH);
    });
    expect(screen.queryByRole("heading", { name: "Approvals" })).toBeNull();
    expect(reads).toBe(1);
  });

  it("a forbidden call that names no second-factor step leaves the session alone", async () => {
    let reads = 0;
    server.use(
      http.get(apiUrl("/api/v1/session"), () => {
        reads += 1;
        return HttpResponse.json(signedInSession());
      }),
      http.get(apiUrl("/api/v1/contracts"), () =>
        problemResponse("forbidden", 403, "Permission denied"),
      ),
    );
    const { router } = renderApp("/approvals", { ...TABLES, session: signedInSession() });
    expect(await screen.findByRole("heading", { level: 1, name: "Approvals" })).toBeTruthy();

    await act(async () => {
      await send("GET", "/api/v1/contracts");
    });

    expect(router.state.location.pathname).toBe("/approvals");
    expect(reads).toBe(0);
  });

  it("without the enrolment step the authenticated routes are reachable", async () => {
    const { router } = renderApp("/approvals", {
      ...TABLES,
      session: signedInSession({ mfa_enrolment_required: false }),
    });

    expect(await screen.findByRole("heading", { level: 1, name: "Approvals" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/approvals");
  });

  it("sign-in without its public route is not found and never redirects to itself", async () => {
    let calls = 0;
    server.use(
      http.get(apiUrl("/api/v1/session"), () => {
        calls += 1;
        return HttpResponse.json({
          authenticated: false,
          capabilities: { identity_providers: [] },
        });
      }),
    );
    const { router } = renderApp("/sign-in", { session: null });

    expect(await screen.findByRole("heading", { level: 1, name: "Page not found" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/sign-in");
    expect(router.state.location.search).toBe("");
    expect(calls).toBe(1);
  });
});
