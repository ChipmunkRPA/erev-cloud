// @vitest-environment jsdom
// X:session-expiring (SCREENS_B §12.4; SCREENS §1.1; 04 API-S-Session `idle_expires_at`): two minutes
// before the idle expiry a modal reads "Your session ends in 2 minutes." with the primary "Stay signed
// in", which calls GET /session, and "Sign out", which ends the session and opens sign-in.
import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { instantMs } from "../../lib/format";
import { renderWithApp, signedInSession } from "../../test/app";
import { apiUrl, installMswServer, server } from "../../test/msw";
import { SessionExpiringModal } from "./SessionExpiringModal";

installMswServer();

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const IDLE_EXPIRES_AT = "2026-09-13T09:30:00Z";

function fakeClock(at: string): void {
  vi.useFakeTimers({
    now: instantMs(at),
    shouldAdvanceTime: true,
    toFake: ["setTimeout", "clearTimeout", "Date"],
  });
}

describe("X:session-expiring", () => {
  it("two minutes before idle_expires_at the modal offers Stay signed in, which calls GET /session", async () => {
    fakeClock("2026-09-13T09:27:55Z");
    let reads = 0;
    server.use(
      http.get(apiUrl("/api/v1/session"), () => {
        reads += 1;
        return HttpResponse.json(signedInSession({ idle_expires_at: "2026-09-13T10:00:00Z" }));
      }),
    );
    renderWithApp(<SessionExpiringModal />, {
      session: signedInSession({ idle_expires_at: IDLE_EXPIRES_AT }),
    });
    expect(screen.queryByRole("alertdialog")).toBeNull();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    const modal = screen.getByRole("alertdialog", { name: "Your session ends in 2 minutes." });
    expect(modal.getAttribute("aria-modal")).toBe("true");
    expect(within(modal).getByRole("button", { name: "Sign out" })).toBeTruthy();
    const stay = within(modal).getByRole("button", { name: "Stay signed in" });
    expect(document.activeElement).toBe(stay);

    fireEvent.click(stay);
    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).toBeNull();
    });
    expect(reads).toBe(1);
  });

  it("Sign out sends POST /session/logout and opens sign-in", async () => {
    fakeClock("2026-09-13T09:28:30Z");
    let logouts = 0;
    server.use(
      http.post(apiUrl("/api/v1/session/logout"), () => {
        logouts += 1;
        return new HttpResponse(null, { status: 204 });
      }),
      http.get(apiUrl("/api/v1/session"), () =>
        HttpResponse.json({ authenticated: false, capabilities: { identity_providers: [] } }),
      ),
    );
    const { router } = renderWithApp(<SessionExpiringModal />, {
      session: signedInSession({ idle_expires_at: IDLE_EXPIRES_AT }),
    });
    const modal = await screen.findByRole("alertdialog", {
      name: "Your session ends in 2 minutes.",
    });
    fireEvent.click(within(modal).getByRole("button", { name: "Sign out" }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/sign-in");
    });
    expect(logouts).toBe(1);
  });

  it("a session already past its idle expiry shows no modal", async () => {
    fakeClock("2026-09-13T09:31:00Z");
    renderWithApp(<SessionExpiringModal />, {
      session: signedInSession({ idle_expires_at: IDLE_EXPIRES_AT }),
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });
});
