// @vitest-environment jsdom
// SF-15:profile and REQ-UX-022 (BUILD_SPEC WEB-12; SCREENS_B §9.9; DESIGN_SYSTEM DS-DEN-01,
// DS-I18N-02, DS-I18N-03; 04 API-R-03 `PATCH /me/preferences`, `POST /me/recovery-codes`; SCREENS
// SCR-PERM-05): the number format and its example, theme and density applied at once and persisted,
// the recovery codes confirmation and dialog, the step-up resend and the not-enrolled state.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SCREEN_ROUTES, SESSION_ROUTES } from "../../app/router";
import type { Me, Preferences } from "../../lib/api/queries/me";
import { configureFormat, formatNumber } from "../../lib/format";
import { installMemoryStorage, renderApp, signedInMe, signedInSession } from "../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { formatLocaleChoices, localeLabel } from "./profile";

installMswServer();
installMemoryStorage();

afterEach(() => {
  cleanup();
  configureFormat({ locale: "en-US" });
});

const CODES = [
  "k7q2-9xm4",
  "p3vd-8hn2",
  "c6rt-2ws9",
  "m4ze-7yb3",
  "t9fa-5ku6",
  "h2lp-4qc8",
  "w8nj-3ro5",
  "b5gx-6de1",
  "s1vy-9mt7",
  "e6ck-2pa4",
];

function renderProfile(me: Me = signedInMe()) {
  // A successful command refreshes the shell's notifications badge (lib/api/commands.ts).
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
  );
  return renderApp("/settings/profile", { me, screenRoutes: SCREEN_ROUTES });
}

/** `PATCH /me/preferences` merging each body into the answered preferences. */
function acceptPreferences(bodies: unknown[], start: Preferences = signedInMe().preferences): void {
  let current = start;
  server.use(
    http.patch(apiUrl("/api/v1/me/preferences"), async ({ request }) => {
      const body = (await request.json()) as Partial<Preferences>;
      bodies.push(body);
      current = { ...current, ...body };
      return HttpResponse.json({ preferences: current });
    }),
  );
}

describe("SF-15:profile and REQ-UX-022", () => {
  it("Number format German (Germany) sends PATCH /me/preferences {format_locale: de-DE}; the example updates to 1.234.567,89", async () => {
    const bodies: unknown[] = [];
    acceptPreferences(bodies);
    renderProfile();

    expect(await screen.findByRole("heading", { level: 1, name: "Profile" })).toBeTruthy();
    // The title is set in a passive effect after the commit (F-ADM latent-race sweep).
    await waitFor(() => {
      expect(document.title).toBe("Profile · eRev Cloud");
    });
    const identity = screen.getByTestId("SF-15-profile-identity");
    expect(within(identity).getByText("Maya Chen")).toBeTruthy();
    expect(within(identity).getByText("maya@example.test")).toBeTruthy();
    // SCR-IA-03: breadcrumb "Settings /" and the Your preferences route tabs.
    const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(breadcrumb).getByRole("link", { name: "Settings" }).getAttribute("href")).toBe(
      "/settings",
    );
    const tabs = screen.getByRole("navigation", { name: "Your preferences" });
    expect(within(tabs).getByRole("link", { name: "Profile" }).getAttribute("aria-current")).toBe(
      "page",
    );
    expect(within(tabs).getByRole("link", { name: "Notifications" }).getAttribute("href")).toBe(
      "/settings/notifications",
    );
    expect(screen.getByText("Example 1,234,567.89")).toBeTruthy();

    fireEvent.click(screen.getByRole("combobox", { name: "Number format" }));
    fireEvent.mouseDown(screen.getByRole("option", { name: "German (Germany)" }));

    expect(await screen.findByText("Example 1.234.567,89")).toBeTruthy();
    expect(bodies).toEqual([{ format_locale: "de-DE" }]);
    expect(screen.getByRole("combobox", { name: "Number format" }).textContent).toContain(
      "German (Germany)",
    );
    // REQ-UX-022: the stored locale reaches the format module for every screen.
    await waitFor(() => {
      expect(formatNumber("1234567.89")).toBe("1.234.567,89");
    });
  });

  it("Theme and Density segmented controls apply at once and persist erev.theme and erev.density", async () => {
    const bodies: unknown[] = [];
    acceptPreferences(bodies);
    renderProfile();

    const theme = await screen.findByRole("radiogroup", { name: "Theme" });
    fireEvent.click(within(theme).getByRole("radio", { name: "Dark" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(window.localStorage.getItem("erev.theme")).toBe("dark");
    expect(within(theme).getByRole("radio", { name: "Dark" }).getAttribute("aria-checked")).toBe(
      "true",
    );

    const density = screen.getByRole("radiogroup", { name: "Density" });
    fireEvent.click(within(density).getByRole("radio", { name: "Compact" }));
    expect(document.documentElement.getAttribute("data-density")).toBe("compact");
    expect(window.localStorage.getItem("erev.density")).toBe("compact");

    fireEvent.click(screen.getByRole("switch", { name: "Single-key shortcuts" }));

    await waitFor(() => {
      expect(bodies).toEqual([
        { theme: "DARK" },
        { density: "COMPACT" },
        { shortcuts_enabled: false },
      ]);
    });
    await waitFor(() => {
      expect(
        screen.getByRole("switch", { name: "Single-key shortcuts" }).getAttribute("aria-checked"),
      ).toBe("false");
    });
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("Regenerate recovery codes confirms, then Recovery codes reports Confirm that you stored the codes. until the checkbox is checked", async () => {
    let posts = 0;
    server.use(
      http.post(apiUrl("/api/v1/me/recovery-codes"), () => {
        posts += 1;
        return HttpResponse.json({ recovery_codes: CODES });
      }),
    );
    renderProfile();

    const security = await screen.findByRole("region", { name: "Sign-in and security" });
    expect(security.getAttribute("data-testid")).toBe("SF-15-profile-security");
    expect(within(security).getByText("Enrolled")).toBeTruthy();
    fireEvent.click(within(security).getByRole("button", { name: "Regenerate recovery codes" }));

    const confirmation = screen.getByRole("alertdialog", { name: "Regenerate recovery codes?" });
    expect(
      within(confirmation).getByText("Your current recovery codes stop working."),
    ).toBeTruthy();
    expect(document.activeElement?.textContent).toBe("Cancel");
    fireEvent.click(
      within(confirmation).getByRole("button", { name: "Regenerate recovery codes" }),
    );

    const dialog = await screen.findByRole("dialog", { name: "Recovery codes" });
    expect(dialog.getAttribute("data-testid")).toBe("SF-15-drawer-recovery-codes");
    expect(
      within(dialog)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(CODES);
    expect(within(dialog).getByRole("button", { name: "Copy codes" })).toBeTruthy();
    expect(within(dialog).getByRole("button", { name: "Download codes (TXT)" })).toBeTruthy();
    expect(screen.queryByRole("alertdialog")).toBeNull();

    const done = within(dialog).getByRole("button", { name: "Done" });
    expect(
      within(dialog).getByText("Confirm that you stored the codes.", { selector: "p" }),
    ).toBeTruthy();
    expect(done.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(done);
    expect(screen.getByRole("dialog", { name: "Recovery codes" })).toBeTruthy();

    fireEvent.click(
      within(dialog).getByRole("checkbox", { name: "I have stored these recovery codes" }),
    );
    expect(
      within(dialog).queryByText("Confirm that you stored the codes.", { selector: "p" }),
    ).toBeNull();
    const enabled = within(dialog).getByRole("button", { name: "Done" });
    expect(enabled.getAttribute("aria-disabled")).toBeNull();
    fireEvent.click(enabled);

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Recovery codes" })).toBeNull();
    });
    expect(posts).toBe(1);
  });

  it("SCR-PERM-05: mfa-step-up-required opens Confirm with your authenticator and resends with the same Idempotency-Key", async () => {
    const keys: (string | null)[] = [];
    const verifications: unknown[] = [];
    server.use(
      http.post(apiUrl("/api/v1/me/recovery-codes"), ({ request }) => {
        keys.push(request.headers.get("Idempotency-Key"));
        return keys.length === 1
          ? problemResponse("mfa-step-up-required", 403, "Step-up required")
          : HttpResponse.json({ recovery_codes: CODES });
      }),
      http.post(apiUrl("/api/v1/session/mfa"), async ({ request }) => {
        verifications.push(await request.json());
        return HttpResponse.json({
          authenticated: true,
          user: signedInMe().user,
          active_tenant: null,
          mfa_verified_at: "2026-09-13T08:10:00Z",
          idle_expires_at: "2026-09-13T09:10:00Z",
          absolute_expires_at: "2026-09-13T20:00:00Z",
          capabilities: { identity_providers: [] },
          csrf_token: "csrf-rotated",
          recovery_codes_remaining: null,
        });
      }),
    );
    renderProfile();

    fireEvent.click(await screen.findByRole("button", { name: "Regenerate recovery codes" }));
    fireEvent.click(
      within(screen.getByRole("alertdialog")).getByRole("button", {
        name: "Regenerate recovery codes",
      }),
    );

    const stepUp = await screen.findByRole("dialog", { name: "Confirm with your authenticator" });
    const code = within(stepUp).getByRole("textbox", { name: "Authentication code" });
    expect(code.getAttribute("autocomplete")).toBe("one-time-code");
    fireEvent.change(code, { target: { value: "246810" } });
    fireEvent.click(within(stepUp).getByRole("button", { name: "Confirm" }));

    expect(await screen.findByRole("dialog", { name: "Recovery codes" })).toBeTruthy();
    expect(verifications).toEqual([{ code: "246810" }]);
    expect(keys).toHaveLength(2);
    expect(keys[0]).not.toBeNull();
    expect(keys[1]).toBe(keys[0]);
  });

  it("a user without a factor sees Not enrolled and Set up multi-factor authentication", async () => {
    renderProfile({ ...signedInMe(), mfa: { enrolled: false, verified_at: null } });

    const security = await screen.findByRole("region", { name: "Sign-in and security" });
    expect(within(security).getByText("Not enrolled")).toBeTruthy();
    const setUp = within(security).getByRole("link", {
      name: "Set up multi-factor authentication",
    });
    expect(setUp.getAttribute("href")).toBe("/mfa/enrol");
    expect(
      within(security).queryByRole("button", { name: "Regenerate recovery codes" }),
    ).toBeNull();
  });

  it("Change password in Sign-in and security opens SF-22:password-change (SCREENS_B rev 1.8)", async () => {
    server.use(
      http.get(apiUrl("/api/v1/me/notifications"), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
    const { router } = renderApp("/settings/profile", {
      sessionRoutes: SESSION_ROUTES,
      screenRoutes: SCREEN_ROUTES,
    });
    const security = await screen.findByRole("region", { name: "Sign-in and security" });
    expect(within(security).getByText("Password")).toBeTruthy();
    expect(within(security).queryByText(/Last changed/)).toBeNull();

    fireEvent.click(within(security).getByRole("link", { name: "Change password" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Change password" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/password/change");
  });

  it("Workspaces marks the session's workspace Current, and it alone, among a workspace and its copies of one membership id", async () => {
    // A sandbox copy keeps the ids of the rows it copies (SCREENS_B §9.7 "The open workspace").
    const base = signedInMe();
    const source = base.memberships[0];
    if (source === undefined) {
      throw new Error("no membership");
    }
    const COPY_ID = "1c1c1c1c-1c1c-4c1c-8c1c-1c1c1c1c1c1c";
    const me: Me = {
      ...base,
      memberships: [
        source,
        {
          ...source,
          tenant: {
            ...source.tenant,
            id: COPY_ID,
            code: "sbx-avenmoor-rehearsal",
            display_name: "Avenmoor rehearsal",
            kind: "sandbox",
            source_tenant_id: source.tenant.id,
            source_known_at: "2026-09-12T18:10:00Z",
          },
        },
      ],
    };
    expect(me.memberships.map((membership) => membership.membership_id)).toEqual([
      source.membership_id,
      source.membership_id,
    ]);
    const errors = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const rows = async () => {
      const list = within(await screen.findByRole("region", { name: "Workspaces" })).getAllByRole(
        "listitem",
      );
      return list.map((item) => item.textContent);
    };

    renderProfile(me);
    expect(await rows()).toEqual(["AvenmoorCurrent", "Avenmoor rehearsalSandbox"]);
    cleanup();

    renderApp("/settings/profile", {
      me,
      session: signedInSession({
        active_tenant: {
          id: COPY_ID,
          code: "sbx-avenmoor-rehearsal",
          display_name: "Avenmoor rehearsal",
          kind: "sandbox",
        },
      }),
      screenRoutes: SCREEN_ROUTES,
    });
    expect(await rows()).toEqual(["Avenmoor", "Avenmoor rehearsalSandboxCurrent"]);
    expect(errors.mock.calls.filter(([message]) => String(message).includes("same key"))).toEqual(
      [],
    );
    errors.mockRestore();
  });

  it("locale names and choices", () => {
    expect(localeLabel("en-US")).toBe("English (United States)");
    expect(localeLabel("de-DE")).toBe("German (Germany)");
    expect(formatLocaleChoices("de-DE")[0]).toBe("en-US");
    expect(formatLocaleChoices("pt-BR")[0]).toBe("pt-BR");
  });
});
