// @vitest-environment jsdom
// SF-22:mfa-enrol and REQ-PLT-005 (BUILD_SPEC WEB-13; SCREENS_B §12.2; 04 API-R-03 `POST /me/mfa/enroll`,
// `POST /me/mfa/confirm`; PRD ERR-27, J-22.4): the ERR-27 warning banner; step 1's QR image beside the key
// grouped in fours with "Copy key"; the wrong-code copy; step 3's ten codes, "Download codes" saving
// `erev-recovery-codes.txt` and "Continue" gated by the acknowledgement; MfaGate sending every other path
// back to `/mfa/enrol`; "Sign out"; a refused start with "Retry".
import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MFA_ENROL_PATH } from "../../app/auth/MfaGate";
import type { SessionState } from "../../app/auth/RequireSession";
import { PUBLIC_ROUTES, SESSION_ROUTES } from "../../app/router";
import type { MfaEnrolment } from "../../lib/api/queries/mfa";
import type { components } from "../../lib/api/schema";
import { probeRoute, renderApp, signedInMe, signedInSession } from "../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { enrolmentRequired, enrolSteps } from "./mfa-enrol";

installMswServer();

type SessionLoginOut = components["schemas"]["SessionLoginOut"];

const HOME = probeRoute("SF-01", "/home", "shell.rail.home");

/** The sign-in answer of a member who holds a `requires_mfa` permission and has no factor yet. */
const ENROLLING: SessionLoginOut = {
  ...signedInSession({ mfa_verified_at: null }),
  mfa_required: false,
  mfa_enrolment_required: true,
};

const ANONYMOUS: SessionState = { authenticated: false, capabilities: { identity_providers: [] } };

const SEED: MfaEnrolment = {
  otpauth_uri:
    "otpauth://totp/eRev:maya%40example.test?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&issuer=eRev",
  secret_base32: "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
};

const CODES = [
  "4k7p-2m9x",
  "8d3q-7c1v",
  "a1b2-c3d4",
  "e5f6-g7h8",
  "j2k3-m4n5",
  "p6q7-r8s9",
  "t1u2-v3w4",
  "x5y6-z7a8",
  "b9c1-d2e3",
  "f4g5-h6j7",
];

const QR_NAME = "QR code for eRev multi-factor authentication";
const WRONG_CODE = "That code did not match. Check the time on your device and try again.";
const CONTINUE_REASON = "Confirm that you stored the recovery codes.";

beforeEach(() => {
  window.history.replaceState(null, "", MFA_ENROL_PATH);
  server.use(http.post(apiUrl("/api/v1/me/mfa/enroll"), () => HttpResponse.json(SEED)));
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function renderEnrol(session: SessionState = ENROLLING, entry = MFA_ENROL_PATH) {
  return renderApp(entry, {
    session,
    me: signedInMe({ mfa: { enrolled: false, verified_at: null } }),
    publicRoutes: PUBLIC_ROUTES,
    sessionRoutes: SESSION_ROUTES,
    screenRoutes: [HOME],
  });
}

/** The reads of the shell and the re-read session after enrolment. */
function afterEnrolment(): void {
  server.use(
    http.get(apiUrl("/api/v1/session"), () => HttpResponse.json(signedInSession())),
    http.get(apiUrl("/api/v1/me"), () => HttpResponse.json(signedInMe())),
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
  );
}

async function reachCodes(): Promise<void> {
  server.use(
    http.post(apiUrl("/api/v1/me/mfa/confirm"), () => HttpResponse.json({ recovery_codes: CODES })),
  );
  fireEvent.click(await screen.findByRole("button", { name: "Next" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Authentication code" }), {
    target: { value: "123456" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Verify code" }));
  await screen.findByRole("list", { name: "Recovery codes" });
}

describe("SF-22:mfa-enrol and REQ-PLT-005", () => {
  it("shows the ERR-27 warning banner, the QR image beside the key grouped in fours, and Copy key", async () => {
    const headers: Array<string | null> = [];
    server.use(
      http.post(apiUrl("/api/v1/me/mfa/enroll"), ({ request }) => {
        headers.push(request.headers.get("Idempotency-Key"));
        return HttpResponse.json(SEED);
      }),
    );
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    renderEnrol();

    const qr = await screen.findByRole("img", { name: QR_NAME });
    expect(qr.getAttribute("src")?.startsWith("data:image/png;base64,")).toBe(true);
    expect(qr.getAttribute("width")).toBe(qr.getAttribute("height"));
    expect(
      screen.getByRole("heading", { level: 1, name: "Set up multi-factor authentication" }),
    ).toBeTruthy();
    // The title is set in a passive effect after the commit (F-ADM latent-race sweep).
    await waitFor(() => {
      expect(document.title).toBe("Set up multi-factor authentication · eRev Cloud");
    });
    expect(
      screen.getByText(
        "Set up multi-factor authentication to continue. Your roles include approval or administration permissions.",
      ),
    ).toBeTruthy();
    expect(screen.getByTestId("SF-22-mfa-key").textContent).toBe(
      "JBSW Y3DP EHPK 3PXP JBSW Y3DP EHPK 3PXP",
    );
    expect(
      screen.getByText("Scan the QR code with your authenticator app, or enter the key manually."),
    ).toBeTruthy();
    const steps = screen.getByRole("navigation", { name: "Steps" });
    expect(within(steps).getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy();
    expect(headers).toHaveLength(1);
    expect(headers[0]).toMatch(/^[0-9a-f-]{36}$/);

    fireEvent.click(screen.getByRole("button", { name: "Copy key" }));
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith(SEED.secret_base32);
    });
    expect(await screen.findByText("Key copied.")).toBeTruthy();
  });

  it("a wrong code shows That code did not match. Check the time on your device and try again.", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(apiUrl("/api/v1/me/mfa/confirm"), async ({ request }) => {
        bodies.push(await request.json());
        return problemResponse("validation-failed", 422, "Validation failed", {
          detail: WRONG_CODE,
          errors: [{ field: "code", sheet: null, row: null, rule_id: null, message: WRONG_CODE }],
        });
      }),
    );
    renderEnrol();

    fireEvent.click(await screen.findByRole("button", { name: "Next" }));
    expect(screen.getByText("Enter the 6-digit code from your authenticator app.")).toBeTruthy();
    const field = screen.getByRole("textbox", { name: "Authentication code" });
    expect(field.getAttribute("autocomplete")).toBe("one-time-code");
    fireEvent.change(field, { target: { value: " 000000 " } });
    fireEvent.click(screen.getByRole("button", { name: "Verify code" }));

    const banner = await screen.findByTestId("SF-22-banner-error");
    expect(within(banner).getByRole("alert").textContent).toBe(WRONG_CODE);
    expect(field.getAttribute("aria-invalid")).toBe("true");
    expect(field.getAttribute("aria-describedby")).toContain(banner.id);
    expect(bodies).toEqual([{ code: "000000" }]);

    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByRole("img", { name: QR_NAME })).toBeTruthy();
  });

  it("step 3 lists ten codes, Download codes saves erev-recovery-codes.txt and Continue waits for the checkbox", async () => {
    const downloads: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      downloads.push(this.download);
    });
    const createObjectURL = vi.fn(() => "blob:recovery-codes");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: createObjectURL,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: revokeObjectURL,
    });
    afterEnrolment();
    const { router } = renderEnrol();
    await reachCodes();

    const list = screen.getByRole("list", { name: "Recovery codes" });
    expect(
      within(list)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(CODES);
    expect(screen.getByText("Store these recovery codes. Each code works once.")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Download codes" }));
    expect(downloads).toEqual(["erev-recovery-codes.txt"]);
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:recovery-codes");

    const proceed = screen.getByRole("button", { name: "Continue" });
    expect(proceed.getAttribute("aria-disabled")).toBe("true");
    expect(screen.getAllByText(CONTINUE_REASON).length).toBeGreaterThan(0);
    fireEvent.click(proceed);
    expect(router.state.location.pathname).toBe(MFA_ENROL_PATH);

    fireEvent.click(screen.getByRole("checkbox", { name: "I have stored these recovery codes" }));
    // Without a reason the button renders without its tooltip wrapper, so it is queried again.
    const enabled = screen.getByRole("button", { name: "Continue" });
    expect(enabled.getAttribute("aria-disabled")).toBeNull();
    expect(screen.queryByText(CONTINUE_REASON)).toBeNull();
    fireEvent.click(enabled);

    expect(await screen.findByRole("heading", { level: 1, name: "Home" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/home");
  });

  it("navigating elsewhere redirects back to /mfa/enrol while enrolment is required", async () => {
    const { router } = renderEnrol();
    await screen.findByRole("img", { name: QR_NAME });

    for (const path of ["/home", "/", "/settings/profile?tab=a"]) {
      await act(() => router.navigate(path));
      await waitFor(() => {
        expect(router.state.location.pathname).toBe(MFA_ENROL_PATH);
      });
    }
    expect(screen.queryByRole("heading", { name: "Home" })).toBeNull();
    expect(screen.getByRole("navigation", { name: "Steps" })).toBeTruthy();
  });

  it("Sign out ends the session and opens sign-in", async () => {
    let logouts = 0;
    server.use(
      http.post(apiUrl("/api/v1/session/logout"), () => {
        logouts += 1;
        return new HttpResponse(null, { status: 204 });
      }),
      http.get(apiUrl("/api/v1/session"), () => HttpResponse.json(ANONYMOUS)),
    );
    const { router } = renderEnrol();

    fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/sign-in");
    expect(logouts).toBe(1);
  });

  it("without the enrolment step the page renders without the warning banner", async () => {
    renderEnrol(signedInSession());
    await screen.findByRole("img", { name: QR_NAME });
    expect(screen.queryByTestId("SF-22-banner-mfa-required")).toBeNull();
    expect(enrolmentRequired(signedInSession())).toBe(false);
    expect(enrolmentRequired(ENROLLING)).toBe(true);
    expect(enrolmentRequired(ANONYMOUS)).toBe(false);
    expect(enrolmentRequired(undefined)).toBe(false);
  });

  it("a refused start shows Multi-factor enrolment could not start. with the problem and Retry", async () => {
    let attempts = 0;
    server.use(
      http.post(apiUrl("/api/v1/me/mfa/enroll"), () => {
        attempts += 1;
        return attempts === 1
          ? problemResponse("invalid-transition", 409, "Action not available in this state", {
              detail: "Multi-factor authentication is already set up.",
            })
          : HttpResponse.json(SEED);
      }),
    );
    renderEnrol();

    const banner = await screen.findByTestId("SF-22-banner-error");
    const alert = within(banner).getByRole("alert");
    expect(within(alert).getByText("Multi-factor enrolment could not start.")).toBeTruthy();
    expect(within(alert).getByText("Multi-factor authentication is already set up.")).toBeTruthy();
    expect(screen.queryByRole("img", { name: QR_NAME })).toBeNull();

    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("img", { name: QR_NAME })).toBeTruthy();
    expect(attempts).toBe(2);
  });

  it("enrolSteps marks earlier steps complete and later steps pending", () => {
    expect(enrolSteps("scan").map((step) => step.state)).toEqual(["current", "pending", "pending"]);
    expect(enrolSteps("verify").map((step) => step.state)).toEqual([
      "complete",
      "current",
      "pending",
    ]);
    expect(enrolSteps("recovery").map((step) => [step.id, step.label, step.state])).toEqual([
      ["scan", "Scan", "complete"],
      ["verify", "Verify", "complete"],
      ["recovery", "Recovery codes", "current"],
    ]);
  });
});

// F-ADM-R1: exact retained independent synthetic fixtures, not live credentials. The admitted
// long email produces a 454-byte URI; the 93-byte positive remains QR-capable. Manual setup
// stays behind the same first-code confirmation even when an image cannot be generated.
describe("F-ADM-R1 admitted provisioning URI", () => {
  it("short_positive", async () => {
    const seed: MfaEnrolment = {
      otpauth_uri:
        "otpauth://totp/eRev:review%40example.test?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&issuer=eRev",
      secret_base32: SEED.secret_base32,
    };
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const confirmation = vi.fn();
    server.use(
      http.post(apiUrl("/api/v1/me/mfa/enroll"), () => HttpResponse.json(seed)),
      http.post(apiUrl("/api/v1/me/mfa/confirm"), () => {
        confirmation();
        return HttpResponse.json({ recovery_codes: CODES });
      }),
    );
    const { router } = renderEnrol();
    expect((await screen.findByTestId("SF-22-mfa-key")).textContent).toBe(
      "JBSW Y3DP EHPK 3PXP JBSW Y3DP EHPK 3PXP",
    );
    const qr = screen.getByRole("img", { name: QR_NAME });
    expect(qr.getAttribute("src")?.startsWith("data:image/png;base64,")).toBe(true);
    expect(qr.getAttribute("width")).toBe("196");
    expect(qr.getAttribute("height")).toBe("196");
    fireEvent.click(screen.getByRole("button", { name: "Copy key" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(seed.secret_base32));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByRole("textbox", { name: "Authentication code" })).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Recovery codes" })).toBeNull();
    expect(confirmation).not.toHaveBeenCalled();
    expect(router.state.location.pathname).toBe(MFA_ENROL_PATH);
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByTestId("SF-22-mfa-key")).toBeTruthy();
  });
  it("long_admitted_email", async () => {
    const seed: MfaEnrolment = {
      otpauth_uri:
        "otpauth://totp/eRev:a%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%40aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.ccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc.com?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&issuer=eRev",
      secret_base32: SEED.secret_base32,
    };
    const writeText = vi.fn<(text: string) => Promise<void>>().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const confirmation = vi.fn();
    server.use(
      http.post(apiUrl("/api/v1/me/mfa/enroll"), () => HttpResponse.json(seed)),
      http.post(apiUrl("/api/v1/me/mfa/confirm"), () => {
        confirmation();
        return HttpResponse.json({ recovery_codes: CODES });
      }),
    );
    const { router } = renderEnrol();
    expect((await screen.findByTestId("SF-22-mfa-key")).textContent).toBe(
      "JBSW Y3DP EHPK 3PXP JBSW Y3DP EHPK 3PXP",
    );
    expect(screen.queryByRole("img", { name: QR_NAME })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Copy key" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(seed.secret_base32));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByRole("textbox", { name: "Authentication code" })).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Recovery codes" })).toBeNull();
    expect(confirmation).not.toHaveBeenCalled();
    expect(router.state.location.pathname).toBe(MFA_ENROL_PATH);
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByTestId("SF-22-mfa-key")).toBeTruthy();
  });
});

// F-ADM-R1 Q20 (team-lead ruling): when the encoder refuses the URI the screen says so beside the
// manual key; a QR-capable URI shows the image and no notice. The retained fixtures again.
describe("F-ADM-R1 Q20 QR-unavailable notice", () => {
  const NOTICE = "QR unavailable — enter the key manually";
  const LONG_URI =
    "otpauth://totp/eRev:a%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%2B%40aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.ccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc.com?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&issuer=eRev";
  const SHORT_URI =
    "otpauth://totp/eRev:review%40example.test?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&issuer=eRev";

  it("long_admitted_email shows the notice beside the manual key and no image", async () => {
    expect(new TextEncoder().encode(LONG_URI).length).toBe(454);
    server.use(
      http.post(apiUrl("/api/v1/me/mfa/enroll"), () =>
        HttpResponse.json({ otpauth_uri: LONG_URI, secret_base32: SEED.secret_base32 }),
      ),
    );
    renderEnrol();
    expect(await screen.findByTestId("SF-22-mfa-key")).toBeTruthy();
    const notice = screen.getByRole("note");
    expect(notice.textContent).toBe(NOTICE);
    expect(notice.getAttribute("data-testid")).toBe("SF-22-mfa-qr-unavailable");
    expect(screen.queryByRole("img", { name: QR_NAME })).toBeNull();
    expect(screen.getByRole("button", { name: "Copy key" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Next" })).toBeTruthy();
  });

  it("short_positive shows the image and no notice", async () => {
    expect(new TextEncoder().encode(SHORT_URI).length).toBe(93);
    server.use(
      http.post(apiUrl("/api/v1/me/mfa/enroll"), () =>
        HttpResponse.json({ otpauth_uri: SHORT_URI, secret_base32: SEED.secret_base32 }),
      ),
    );
    renderEnrol();
    expect(await screen.findByRole("img", { name: QR_NAME })).toBeTruthy();
    expect(screen.queryByRole("note")).toBeNull();
    expect(screen.queryByText(NOTICE)).toBeNull();
    expect(screen.queryByTestId("SF-22-mfa-qr-unavailable")).toBeNull();
  });
});
