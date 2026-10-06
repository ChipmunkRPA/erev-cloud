// @vitest-environment jsdom
// SF-22:accept-invitation (BUILD_SPEC WEB-13; SCREENS_B §12.3 rev 1.8; SCREENS RT-05; 04 API-R-01
// `POST /session/invitations/lookup`, `POST /session/accept-invitation`, §16.12 rev 1.38; PRD J-22.3,
// ERR-21): the token is read from `#token=` and sent only in request bodies; the heading from the lookup;
// the 404 expired-link copy; a link without a token; `password1234` shows the ERR-21 copy; mismatched
// passwords; the `has_password` variant "Your eRev password"; an accepted invitation opens the MFA
// enrolment when the roles require it.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { MFA_ENROL_PATH } from "../../app/auth/MfaGate";
import type { SessionState } from "../../app/auth/RequireSession";
import { PUBLIC_ROUTES, SESSION_ROUTES } from "../../app/router";
import { type InvitationLookup, tokenFromFragment } from "../../lib/api/queries/credentials";
import type { components } from "../../lib/api/schema";
import { probeRoute, renderApp, signedInMe, signedInSession } from "../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { invitationHeading } from "./accept-invitation";

installMswServer();

type SessionLoginOut = components["schemas"]["SessionLoginOut"];

const ANONYMOUS: SessionState = { authenticated: false, capabilities: { identity_providers: [] } };
const HOME = probeRoute("SF-01", "/home", "shell.rail.home");
const INVITATION_TOKEN = "inv-7f3a9c2e5b1d4e6f8a0b1c2d3e4f5a6b";
const ENTRY = `/accept-invitation#token=${INVITATION_TOKEN}`;
/** Fixture values of the demo invitee (PRD J-22.3, J-22.4). */
const CHOSEN_PASSWORD = "Lena!Revenue2026";
const EXISTING_PASSWORD = "existing-password-1";

const INVITATION: InvitationLookup = {
  workspace_display_name: "Avenmoor Holdings (Demo)",
  inviter_display_name: "Tomás Rivera",
  email: "lena@demo.erev",
  expires_at: "2026-09-26T08:00:00Z",
  has_password: false,
};

const HEADING = "Tomás Rivera invited lena@demo.erev to Avenmoor Holdings (Demo).";
const EXPIRED =
  "This invitation link has expired or was already used. Ask a workspace administrator to resend it.";
const MISSING = "This invitation link is incomplete. Open the link from the invitation email.";

interface Seen {
  readonly url: string;
  readonly body: unknown;
}

beforeEach(() => {
  window.history.replaceState(null, "", "/accept-invitation");
});

afterEach(() => {
  cleanup();
});

function renderAccept(entry = ENTRY) {
  return renderApp(entry, {
    session: ANONYMOUS,
    me: null,
    badge: null,
    publicRoutes: PUBLIC_ROUTES,
    sessionRoutes: SESSION_ROUTES,
    screenRoutes: [HOME],
  });
}

/** Answers the lookup with the invitation and records every request. */
function lookupFound(seen: Seen[], invitation: InvitationLookup = INVITATION): void {
  server.use(
    http.post(apiUrl("/api/v1/session/invitations/lookup"), async ({ request }) => {
      seen.push({ url: request.url, body: await request.json() });
      return HttpResponse.json(invitation);
    }),
  );
}

async function fillPasswords(password: string, confirmation = password): Promise<void> {
  fireEvent.change(await screen.findByLabelText("Choose a password"), {
    target: { value: password },
  });
  fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: confirmation } });
  fireEvent.click(screen.getByRole("button", { name: "Accept invitation" }));
}

describe("SF-22:accept-invitation", () => {
  it("reads the token from #token= and sends it only in request bodies; the heading names inviter, email and workspace", async () => {
    const seen: Seen[] = [];
    lookupFound(seen);
    server.use(
      http.post(apiUrl("/api/v1/session/accept-invitation"), async ({ request }) => {
        seen.push({ url: request.url, body: await request.json() });
        return problemResponse("not-found", 404, "Not found");
      }),
    );
    const { router } = renderAccept();

    expect((await screen.findByTestId("SF-22-invitation-heading")).textContent).toBe(HEADING);
    expect(screen.getByRole("heading", { level: 1, name: "Accept invitation" })).toBeTruthy();
    // The title is set in a passive effect after the commit (F-ADM latent-race sweep).
    await waitFor(() => {
      expect(document.title).toBe("Accept invitation · eRev Cloud");
    });
    expect(router.state.location.hash).toBe(`#token=${INVITATION_TOKEN}`);
    expect(router.state.location.search).toBe("");
    const password = screen.getByLabelText("Choose a password");
    expect(password.getAttribute("autocomplete")).toBe("new-password");
    expect(password.getAttribute("type")).toBe("password");
    expect(
      screen.getByText(
        "Use at least 12 characters. Do not use your email address or a common password.",
      ),
    ).toBeTruthy();

    await fillPasswords(CHOSEN_PASSWORD);
    expect(await screen.findByText(EXPIRED)).toBeTruthy();

    expect(seen).toHaveLength(2);
    for (const request of seen) {
      expect(request.url).not.toContain(INVITATION_TOKEN);
      expect(new URL(request.url).hash).toBe("");
    }
    expect(seen[0]?.body).toEqual({ token: INVITATION_TOKEN });
    expect(seen[1]?.body).toEqual({ token: INVITATION_TOKEN, password: CHOSEN_PASSWORD });
  });

  it("a 404 from the lookup shows the expired-link copy and no form", async () => {
    server.use(
      http.post(apiUrl("/api/v1/session/invitations/lookup"), () =>
        problemResponse("not-found", 404, "Not found"),
      ),
    );
    renderAccept();

    const banner = await screen.findByTestId("SF-22-banner-invitation-expired");
    expect(within(banner).getByText(EXPIRED)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Accept invitation" })).toBeNull();
  });

  it("a link without a token fragment explains that the link is incomplete, without a request", async () => {
    let lookups = 0;
    server.use(
      http.post(apiUrl("/api/v1/session/invitations/lookup"), () => {
        lookups += 1;
        return HttpResponse.json(INVITATION);
      }),
    );
    renderAccept("/accept-invitation");
    expect(await screen.findByText(MISSING)).toBeTruthy();
    expect(lookups).toBe(0);
    cleanup();

    renderAccept("/accept-invitation?token=in-the-query");
    expect(await screen.findByText(MISSING)).toBeTruthy();
    expect(lookups).toBe(0);

    expect(tokenFromFragment("#token=abc")).toBe("abc");
    expect(tokenFromFragment("token=abc&x=1")).toBe("abc");
    expect(tokenFromFragment("#token=")).toBeNull();
    expect(tokenFromFragment("")).toBeNull();
  });

  it("password1234 shows Choose a less common password. under the field, before the help text", async () => {
    lookupFound([]);
    server.use(
      http.post(apiUrl("/api/v1/session/accept-invitation"), () =>
        problemResponse("password-policy", 422, "Choose another password", {
          detail: "Choose a less common password.",
          errors: [
            {
              field: "password",
              sheet: null,
              row: null,
              rule_id: null,
              message: "Choose a less common password.",
            },
          ],
        }),
      ),
    );
    renderAccept();

    await fillPasswords("password1234");

    const policy = await screen.findByTestId("SF-22-banner-password-policy");
    expect(within(policy).getByText("Choose a less common password.")).toBeTruthy();
    const password = screen.getByLabelText("Choose a password");
    expect(password.getAttribute("aria-invalid")).toBe("true");
    const described = (password.getAttribute("aria-describedby") ?? "").split(" ");
    expect(described).toHaveLength(2);
    expect(document.getElementById(described[0] ?? "")?.textContent).toContain(
      "Choose a less common password.",
    );
    expect(document.getElementById(described[1] ?? "")?.textContent).toBe(
      "Use at least 12 characters. Do not use your email address or a common password.",
    );
  });

  it("mismatched passwords show The passwords do not match. without a request", async () => {
    const seen: Seen[] = [];
    lookupFound(seen);
    server.use(
      http.post(apiUrl("/api/v1/session/accept-invitation"), async ({ request }) => {
        seen.push({ url: request.url, body: await request.json() });
        return HttpResponse.json(signedInSession());
      }),
    );
    renderAccept();

    await fillPasswords(CHOSEN_PASSWORD, "Lena!Revenue2025");

    expect(await screen.findByText("The passwords do not match.")).toBeTruthy();
    expect(screen.getByLabelText("Confirm password").getAttribute("aria-invalid")).toBe("true");
    expect(seen.map((request) => new URL(request.url).pathname)).toEqual([
      "/api/v1/session/invitations/lookup",
    ]);
  });

  it("an existing user enters Your eRev password once; a wrong one is the field error and a lock the sign-in copy", async () => {
    const seen: Seen[] = [];
    lookupFound(seen, { ...INVITATION, has_password: true });
    server.use(
      http.post(apiUrl("/api/v1/session/accept-invitation"), async ({ request }) => {
        seen.push({ url: request.url, body: await request.json() });
        return problemResponse("validation-failed", 422, "Check the highlighted fields", {
          detail: "The password is incorrect.",
          errors: [
            {
              field: "password",
              sheet: null,
              row: null,
              rule_id: null,
              message: "The password is incorrect.",
            },
          ],
        });
      }),
    );
    renderAccept();

    const existing = await screen.findByLabelText("Your eRev password");
    expect(existing.getAttribute("autocomplete")).toBe("current-password");
    expect(screen.queryByLabelText("Confirm password")).toBeNull();
    expect(screen.queryByLabelText("Choose a password")).toBeNull();
    expect(
      screen.queryByText(
        "Use at least 12 characters. Do not use your email address or a common password.",
      ),
    ).toBeNull();

    fireEvent.change(existing, { target: { value: EXISTING_PASSWORD } });
    fireEvent.click(screen.getByRole("button", { name: "Accept invitation" }));
    expect(await screen.findByText("The password is incorrect.")).toBeTruthy();
    expect(existing.getAttribute("aria-invalid")).toBe("true");
    expect(screen.queryByTestId("SF-22-banner-password-policy")).toBeNull();
    expect(seen[1]?.body).toEqual({ token: INVITATION_TOKEN, password: EXISTING_PASSWORD });

    server.use(
      http.post(apiUrl("/api/v1/session/accept-invitation"), () =>
        problemResponse("account-locked", 423, "Account locked"),
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "Accept invitation" }));
    const banner = await screen.findByTestId("SF-22-banner-error");
    expect(within(banner).getByRole("alert").textContent).toBe(
      "Too many failed sign-in attempts. Try again in 15 minutes or ask a workspace administrator.",
    );
  });

  // SCREENS §0.7 SCR-ST-13, DG-FE-06 rev 1.228 (item KIT-UNPLACED-ERRORS-1): the page showed its
  // banner only while the 422 carried no field errors at all, and only the password has a field, so
  // an acceptance refused for its token was refused without a word.
  it("a refusal that names the token is said in the banner; one the password field shows whole has no banner", async () => {
    const seen: Seen[] = [];
    lookupFound(seen, { ...INVITATION, has_password: true });
    const error = (field: string, message: string) => ({
      field,
      sheet: null,
      row: null,
      rule_id: null,
      message,
    });
    let errors = [error("token", "This invitation was sent for another workspace.")];
    server.use(
      http.post(apiUrl("/api/v1/session/accept-invitation"), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", { errors }),
      ),
    );
    renderAccept();

    const existing = await screen.findByLabelText("Your eRev password");
    fireEvent.change(existing, { target: { value: EXISTING_PASSWORD } });
    fireEvent.click(screen.getByRole("button", { name: "Accept invitation" }));
    const banner = await screen.findByTestId("SF-22-banner-error");
    expect(
      within(banner).getByText("This invitation was sent for another workspace."),
    ).toBeTruthy();
    expect(existing.getAttribute("aria-invalid")).not.toBe("true");

    // Both at once: the password's sentence at its field, the token's in the banner.
    errors = [
      error("password", "The password is incorrect."),
      error("token", "This invitation was sent for another workspace."),
    ];
    fireEvent.click(screen.getByRole("button", { name: "Accept invitation" }));
    await waitFor(() => expect(existing.getAttribute("aria-invalid")).toBe("true"));
    expect(screen.getAllByText("The password is incorrect.")).toHaveLength(1);
    expect(
      within(screen.getByTestId("SF-22-banner-error")).queryByText("The password is incorrect."),
    ).toBeNull();
    expect(
      within(screen.getByTestId("SF-22-banner-error")).getByText(
        "This invitation was sent for another workspace.",
      ),
    ).toBeTruthy();

    // SCREENS_B §12.3: a wrong password is the field's error and nothing else.
    errors = [error("password", "The password is incorrect.")];
    fireEvent.click(screen.getByRole("button", { name: "Accept invitation" }));
    await waitFor(() => expect(screen.queryByTestId("SF-22-banner-error")).toBeNull());
    expect(await screen.findByText("The password is incorrect.")).toBeTruthy();
    expect(existing.getAttribute("aria-invalid")).toBe("true");
  });

  it("an accepted invitation opens the MFA enrolment when the roles require it", async () => {
    lookupFound([]);
    const answered: SessionLoginOut = {
      ...signedInSession({ mfa_verified_at: null }),
      mfa_required: false,
      mfa_enrolment_required: true,
    };
    server.use(
      http.post(apiUrl("/api/v1/session/accept-invitation"), () => HttpResponse.json(answered)),
      http.post(apiUrl("/api/v1/me/mfa/enroll"), () =>
        HttpResponse.json({
          otpauth_uri: "otpauth://totp/eRev:lena%40demo.erev?secret=JBSWY3DPEHPK3PXP&issuer=eRev",
          secret_base32: "JBSWY3DPEHPK3PXP",
        }),
      ),
      http.get(apiUrl("/api/v1/me"), () => HttpResponse.json(signedInMe())),
    );
    const { router, queryClient } = renderAccept();

    await fillPasswords(CHOSEN_PASSWORD);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(MFA_ENROL_PATH);
    });
    expect(
      await screen.findByRole("heading", { level: 1, name: "Set up multi-factor authentication" }),
    ).toBeTruthy();
    expect(queryClient.getQueryData(["session", "public", {}])).toEqual(answered);
  });

  it("an invitation without an inviter reads You were invited as <email> to <workspace>.", () => {
    expect(invitationHeading(INVITATION)).toBe(HEADING);
    expect(invitationHeading({ ...INVITATION, inviter_display_name: null })).toBe(
      "You were invited as lena@demo.erev to Avenmoor Holdings (Demo).",
    );
  });
});
