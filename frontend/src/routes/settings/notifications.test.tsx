// @vitest-environment jsdom
// SF-15:notifications and REQ-PLT-021 (BUILD_SPEC WEB-17; SCREENS_B §9.8; SCREENS SCR-IA-03; PRD §5.4
// NTF-R2, NTF-R3; 04 API-R-03 `GET, PUT /me/notification-preferences`, T-PLT-25): the thirteen kinds with
// their names, descriptions and switches; the full-list PUT; "Preferences saved." at most once per 5
// seconds; the revert on failure; the mandatory audit chain switches; and a sandbox, which sends no
// email (05 SBX-08 rev 1.116; SCREENS_B §9.8 rev 1.54).
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { renderApp, signedInSession } from "../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import {
  type NotificationPreference,
  preferencesBody,
  SAVED_TOAST_INTERVAL_MS,
} from "./notifications";

installMswServer();

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

/** 04 E-69 order with the T-PLT-25 email defaults (PRD §5.4 "Email default"). */
const STORED: readonly NotificationPreference[] = [
  { kind: "APPROVAL_ASSIGNED", in_app: true, email: true },
  { kind: "APPROVAL_UNASSIGNED", in_app: true, email: true },
  { kind: "ITEM_REJECTED", in_app: true, email: true },
  { kind: "APPROVAL_VOIDED", in_app: true, email: true },
  { kind: "JOB_FAILED", in_app: true, email: true },
  { kind: "CLOSE_BLOCKER_RAISED", in_app: true, email: false },
  { kind: "CHAIN_VERIFICATION_FAILED", in_app: true, email: true },
  { kind: "EXPORT_FAILED", in_app: true, email: true },
  { kind: "EXCEPTION_ASSIGNED", in_app: true, email: false },
  { kind: "SUPPORT_GRANT_REQUESTED", in_app: true, email: true },
  { kind: "ITEM_APPROVED", in_app: true, email: false },
  { kind: "PERIOD_LOCKED", in_app: true, email: false },
  { kind: "PERIOD_REOPENED", in_app: true, email: true },
];

/** SCREENS_B §9.8 grid rows: notification and "When it is sent". */
const ROWS: readonly (readonly [string, string])[] = [
  ["Approval assigned to you", "A step becomes active for an item you can approve"],
  [
    "Approval needs an independent approver",
    "An approval has no independent eligible person for its active step",
  ],
  ["Your item was approved", "An item you prepared is approved"],
  ["Your item was rejected", "An item you prepared is rejected"],
  ["An approval request was voided", "An item changed after submission or was withdrawn"],
  ["A job failed", "A job you started fails; for close runs, Controllers of the entity"],
  ["A period was locked", "A period of an entity in your scope is locked"],
  ["A period was reopened", "A period of an entity in your scope is reopened"],
  ["A close blocker was raised", "A new blocker appears for a period in soft close"],
  ["Audit chain verification failed", "The audit chain verification fails"],
  ["A journal export failed", "A journal batch or run fails to export"],
  ["An exception was assigned to you", "An exception is created for you or assigned to you"],
  ["Support access was requested", "A platform operator requests support access"],
];

interface PreferencesBody {
  readonly items: readonly NotificationPreference[];
}

interface ServeOptions {
  /** The PUT answers 500. */
  readonly failure?: boolean;
  /** The PUT answers only after this promise settles. */
  readonly gate?: Promise<void>;
}

/** GET answers the stored list; PUT records the body and stores it, unless it fails. */
function servePreferences(options: ServeOptions = {}): { readonly bodies: PreferencesBody[] } {
  let stored: readonly NotificationPreference[] = STORED;
  const bodies: PreferencesBody[] = [];
  server.use(
    // A successful command refreshes the shell's notifications badge (lib/api/commands.ts).
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/me/notification-preferences"), () =>
      HttpResponse.json({ items: stored }),
    ),
    http.put(apiUrl("/api/v1/me/notification-preferences"), async ({ request }) => {
      const body = (await request.json()) as PreferencesBody;
      bodies.push(body);
      if (options.gate !== undefined) {
        await options.gate;
      }
      if (options.failure === true) {
        return problemResponse(null, 500, "Internal Server Error");
      }
      stored = body.items;
      return HttpResponse.json({ items: stored });
    }),
  );
  return { bodies };
}

function renderPreferences() {
  return renderApp("/settings/notifications", { screenRoutes: SCREEN_ROUTES });
}

function switchNamed(name: string): HTMLElement {
  return screen.getByRole("switch", { name });
}

describe("SF-15:notifications and REQ-PLT-021", () => {
  it("the table Notification preferences lists the 13 kinds with the SCREENS_B §9.8 names, descriptions and named switches; the footnote states NTF-R3", async () => {
    servePreferences();
    renderPreferences();

    const table = await screen.findByRole("table", { name: "Notification preferences" });
    expect(table.getAttribute("data-testid")).toBe("SF-15-grid-notification-preferences");
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((cell) => cell.textContent),
    ).toEqual(["Notification", "When it is sent", "In app", "Email"]);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(
      rows.map((row) => [
        within(row).getByRole("rowheader").textContent,
        within(row).getAllByRole("cell")[0]?.textContent,
      ]),
    ).toEqual(ROWS.map(([name, description]) => [name, description]));
    expect(screen.getByTestId("SF-15-row-approval-assigned")).toBe(rows[0]);

    for (const [name] of ROWS) {
      expect(switchNamed(`${name}, in app`).getAttribute("aria-checked")).toBe("true");
      expect(switchNamed(`${name}, email`)).toBeTruthy();
    }
    expect(switchNamed("Your item was approved, email").getAttribute("aria-checked")).toBe("false");
    expect(switchNamed("Approval assigned to you, email").getAttribute("aria-checked")).toBe(
      "true",
    );
    expect(
      screen.getByText(
        "Emails contain the object reference and a link, never amounts or customer data.",
      ),
    ).toBeTruthy();

    // SCR-IA-03: breadcrumb and the Your preferences route tabs.
    expect(
      screen.getByRole("heading", { level: 1, name: "Notification preferences" }),
    ).toBeTruthy();
    const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(breadcrumb).getByRole("link", { name: "Settings" }).getAttribute("href")).toBe(
      "/settings",
    );
    const tabs = screen.getByRole("navigation", { name: "Your preferences" });
    expect(
      within(tabs).getByRole("link", { name: "Notifications" }).getAttribute("aria-current"),
    ).toBe("page");
    expect(within(tabs).getByRole("link", { name: "Profile" }).getAttribute("href")).toBe(
      "/settings/profile",
    );
    await waitFor(() => {
      expect(document.title).toBe("Notification preferences · eRev Cloud");
    });
  });

  it("a change sends PUT /me/notification-preferences with the full list and shows Preferences saved. at most once per 5 seconds", async () => {
    const start = 1_800_000_000_000;
    const clock = vi.spyOn(Date, "now").mockReturnValue(start);
    const served = servePreferences();
    renderPreferences();

    fireEvent.click(await screen.findByRole("switch", { name: "Your item was approved, email" }));
    expect(await screen.findByText("Preferences saved.")).toBeTruthy();
    expect(switchNamed("Your item was approved, email").getAttribute("aria-checked")).toBe("true");
    expect(served.bodies).toEqual([
      {
        items: STORED.map((item) =>
          item.kind === "ITEM_APPROVED" ? { ...item, email: true } : item,
        ),
      },
    ]);

    fireEvent.click(switchNamed("A period was locked, email"));
    await waitFor(() => {
      expect(served.bodies).toHaveLength(2);
    });
    await waitFor(() => {
      expect(switchNamed("A period was locked, email").getAttribute("aria-busy")).toBeNull();
    });
    expect(switchNamed("A period was locked, email").getAttribute("aria-checked")).toBe("true");
    expect(screen.getAllByText("Preferences saved.")).toHaveLength(1);
    const second = served.bodies[1]?.items ?? [];
    expect(second).toHaveLength(13);
    expect(second.find((item) => item.kind === "PERIOD_LOCKED")).toEqual({
      kind: "PERIOD_LOCKED",
      in_app: true,
      email: true,
    });
    expect(second.find((item) => item.kind === "ITEM_APPROVED")?.email).toBe(true);

    clock.mockReturnValue(start + SAVED_TOAST_INTERVAL_MS);
    fireEvent.click(switchNamed("A job failed, in app"));
    await waitFor(() => {
      expect(screen.getAllByText("Preferences saved.")).toHaveLength(2);
    });
    expect(served.bodies).toHaveLength(3);
    expect(switchNamed("A job failed, in app").getAttribute("aria-checked")).toBe("false");
  });

  it("a failure reverts the switch with Could not save the preference. Try again.", async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const served = servePreferences({ failure: true, gate });
    renderPreferences();

    fireEvent.click(
      await screen.findByRole("switch", { name: "Approval assigned to you, in app" }),
    );
    const saving = switchNamed("Approval assigned to you, in app");
    expect(saving.getAttribute("aria-checked")).toBe("false");
    expect(saving.getAttribute("aria-busy")).toBe("true");
    await waitFor(() => {
      expect(served.bodies).toHaveLength(1);
    });
    release();

    expect(await screen.findByText("Could not save the preference. Try again.")).toBeTruthy();
    const reverted = switchNamed("Approval assigned to you, in app");
    expect(reverted.getAttribute("aria-checked")).toBe("true");
    expect(reverted.getAttribute("aria-busy")).toBeNull();
    expect(screen.queryByText("Preferences saved.")).toBeNull();
  });

  it("the CHAIN_VERIFICATION_FAILED switches have aria-disabled with the tooltip Audit chain failures are always sent in the app and by email.", async () => {
    const served = servePreferences();
    renderPreferences();

    for (const channel of ["in app", "email"]) {
      const locked = await screen.findByRole("switch", {
        name: `Audit chain verification failed, ${channel}`,
      });
      expect(locked.getAttribute("aria-disabled")).toBe("true");
      expect(locked.getAttribute("aria-checked")).toBe("true");
      const tooltipId = locked.getAttribute("aria-describedby");
      expect(tooltipId === null ? null : document.getElementById(tooltipId)?.textContent).toBe(
        "Audit chain failures are always sent in the app and by email.",
      );
      fireEvent.click(locked);
      expect(locked.getAttribute("aria-checked")).toBe("true");
    }
    expect(switchNamed("Approval assigned to you, email").getAttribute("aria-disabled")).toBeNull();
    expect(served.bodies).toEqual([]);

    // Another change still sends the audit chain kind on in both channels (NTF-R2).
    fireEvent.click(switchNamed("A close blocker was raised, email"));
    await waitFor(() => {
      expect(served.bodies).toHaveLength(1);
    });
    expect(
      served.bodies[0]?.items.find((item) => item.kind === "CHAIN_VERIFICATION_FAILED"),
    ).toEqual({ kind: "CHAIN_VERIFICATION_FAILED", in_app: true, email: true });
  });

  it("in a sandbox the email switches are off and unavailable and the footnote says that a sandbox sends no email", async () => {
    const served = servePreferences();
    renderApp("/settings/notifications", {
      session: signedInSession({
        active_tenant: {
          id: "1c1c1c1c-1c1c-4c1c-8c1c-1c1c1c1c1c1c",
          code: "sbx-avenmoor-rehearsal",
          display_name: "Avenmoor rehearsal",
          kind: "sandbox",
        },
      }),
      screenRoutes: SCREEN_ROUTES,
    });
    const described = (element: HTMLElement) =>
      document.getElementById(element.getAttribute("aria-describedby") ?? "")?.textContent;

    // Every "Email" switch is off and unavailable, whatever is stored, and says why.
    await screen.findByRole("table", { name: "Notification preferences" });
    const emails = ROWS.map(([name]) => switchNamed(`${name}, email`));
    expect(emails).toHaveLength(13);
    expect(STORED.filter((item) => item.email)).toHaveLength(9);
    for (const email of emails) {
      expect(email.getAttribute("aria-checked")).toBe("false");
      expect(email.getAttribute("aria-disabled")).toBe("true");
      expect(described(email)).toBe("No email is sent from a sandbox workspace.");
      fireEvent.click(email);
      expect(email.getAttribute("aria-checked")).toBe("false");
    }
    expect(served.bodies).toEqual([]);
    // The kind that cannot be turned off is sent in the app, and the tooltip says no more.
    const locked = switchNamed("Audit chain verification failed, in app");
    expect(locked.getAttribute("aria-checked")).toBe("true");
    expect(locked.getAttribute("aria-disabled")).toBe("true");
    expect(described(locked)).toBe("Audit chain failures are always sent in the app.");
    expect(
      screen.getByText(
        "A sandbox sends no email. Notifications raised in this workspace are delivered in the app only.",
      ),
    ).toBeTruthy();
    expect(
      screen.queryByText(
        "Emails contain the object reference and a link, never amounts or customer data.",
      ),
    ).toBeNull();

    // "In app" still applies at once, and the stored email preferences travel unchanged.
    fireEvent.click(switchNamed("A close blocker was raised, in app"));
    await waitFor(() => {
      expect(served.bodies).toHaveLength(1);
    });
    expect(served.bodies[0]?.items).toEqual(
      STORED.map((item) =>
        item.kind === "CLOSE_BLOCKER_RAISED" ? { ...item, in_app: false } : item,
      ),
    );
    expect(switchNamed("A close blocker was raised, in app").getAttribute("aria-checked")).toBe(
      "false",
    );
  });

  it("preferencesBody sends every kind and keeps the audit chain kind on", () => {
    const tampered = STORED.map((item) =>
      item.kind === "CHAIN_VERIFICATION_FAILED" ? { ...item, in_app: false, email: false } : item,
    );
    const body = preferencesBody(tampered);
    expect(body.items).toHaveLength(13);
    expect(body.items.find((item) => item.kind === "CHAIN_VERIFICATION_FAILED")).toEqual({
      kind: "CHAIN_VERIFICATION_FAILED",
      in_app: true,
      email: true,
    });
    expect(body.items.find((item) => item.kind === "ITEM_APPROVED")).toEqual({
      kind: "ITEM_APPROVED",
      in_app: true,
      email: false,
    });
  });
});
