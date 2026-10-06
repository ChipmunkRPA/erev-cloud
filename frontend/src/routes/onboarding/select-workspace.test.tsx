// @vitest-environment jsdom
// SF-23:select (BUILD_SPEC WEB-12; SCREENS_B §11.3; 04 API-R-01 `POST /session/tenant`, §16.12
// API-S-Me memberships): the Production, Demo workspaces, and Sandboxes and scenarios sections ordered
// by `last_opened_at`; "Open <workspace name>" sends `POST /session/tenant` and opens the landing
// route; one membership opens at once; none shows the empty state with "Sign out".
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SESSION_ROUTES } from "../../app/router";
import { announce } from "../../lib/a11y/announce";
import type { Me, MeMembership } from "../../lib/api/queries/me";
import { probeRoute, renderApp, signedInMe, signedInSession } from "../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { openableMemberships, sectionOf, testIdKey } from "./select-workspace";

vi.mock("../../lib/a11y/announce", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/a11y/announce")>();
  return { ...actual, announce: vi.fn() };
});

installMswServer();

afterEach(() => {
  cleanup();
  vi.mocked(announce).mockClear();
});

const HOME = probeRoute("SF-01", "/home", "shell.rail.home");

let counter = 0;

function membership(
  code: string,
  displayName: string,
  options: {
    readonly kind?: "production" | "sandbox";
    readonly isDemo?: boolean;
    readonly lastOpenedAt?: string | null;
    readonly status?: MeMembership["status"];
    readonly tenantStatus?: MeMembership["tenant"]["status"];
  } = {},
): MeMembership {
  counter += 1;
  const suffix = String(counter).padStart(12, "0");
  return {
    membership_id: `3a4b5c6d-7e8f-4a1b-9c2d-${suffix}`,
    tenant: {
      id: `0b6f3e2d-1c4a-4b8e-9d7f-${suffix}`,
      code,
      display_name: displayName,
      kind: options.kind ?? "production",
      is_demo: options.isDemo ?? false,
      status: options.tenantStatus ?? "ACTIVE",
      source_tenant_id: null,
      source_known_at: null,
    },
    status: options.status ?? "ACTIVE",
    last_opened_at: options.lastOpenedAt === undefined ? null : options.lastOpenedAt,
  };
}

const NORTHWIND = membership("northwind", "Northwind Analytics", {
  lastOpenedAt: "2026-09-10T09:30:00Z",
});
const HARBOUR = membership("harbour", "Harbour Components", {
  lastOpenedAt: "2026-09-13T08:00:00Z",
});
const FERNHILL = membership("fernhill", "Fernhill Software, Inc. (Demo)", { isDemo: true });
const BRACKEN = membership("bracken", "Bracken Robotics Corp. (Demo)", {
  isDemo: true,
  lastOpenedAt: "2026-09-01T12:00:00Z",
});
const OUTLOOK = membership("q4-outlook", "Q4 2026 outlook (Scenario)", {
  kind: "sandbox",
  lastOpenedAt: "2026-09-12T17:02:00Z",
});
const SUSPENDED = membership("granitefield", "Granitefield Engineering Group (Demo)", {
  isDemo: true,
  status: "SUSPENDED",
  lastOpenedAt: "2026-09-13T10:00:00Z",
});

function withMemberships(memberships: readonly MeMembership[]): Me {
  return { ...signedInMe(), memberships: [...memberships] };
}

function renderSelect(me: Me | null, session = signedInSession()) {
  return renderApp("/select-workspace", {
    session,
    me,
    badge: null,
    sessionRoutes: SESSION_ROUTES,
    screenRoutes: [HOME],
  });
}

function acceptTenant(bodies: unknown[]): void {
  server.use(
    http.post(apiUrl("/api/v1/session/tenant"), async ({ request }) => {
      bodies.push(await request.json());
      return HttpResponse.json({
        ...signedInSession(),
        mfa_required: false,
        mfa_enrolment_required: false,
      });
    }),
    http.get(apiUrl("/api/v1/me"), () => HttpResponse.json(signedInMe())),
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
  );
}

function rowHeaders(section: HTMLElement): string[] {
  return within(section)
    .getAllByRole("rowheader")
    .map((header) => header.textContent);
}

describe("SF-23:select", () => {
  it("sections Production, Demo workspaces and Sandboxes and scenarios list memberships ordered by last_opened_at", async () => {
    renderSelect(withMemberships([NORTHWIND, FERNHILL, OUTLOOK, BRACKEN, HARBOUR, SUSPENDED]));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Choose a workspace" }),
    ).toBeTruthy();
    // The shell sets the document title in an effect after the page renders.
    await waitFor(() => {
      expect(document.title).toBe("Choose a workspace · eRev Cloud");
    });
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual(["Production", "Demo workspaces", "Sandboxes and scenarios"]);

    const [production, demo, sandboxes] = screen
      .getAllByRole("region")
      .filter((region) => region.tagName === "SECTION");
    if (production === undefined || demo === undefined || sandboxes === undefined) {
      throw new Error("three sections expected");
    }
    expect(rowHeaders(production)).toEqual(["Harbour Components", "Northwind Analytics"]);
    // Never opened sorts last; a SUSPENDED membership cannot be opened and is not listed.
    expect(rowHeaders(demo)).toEqual([
      "Bracken Robotics Corp. (Demo)",
      "Fernhill Software, Inc. (Demo)",
    ]);
    expect(rowHeaders(sandboxes)).toEqual(["Q4 2026 outlook (Scenario)Sandbox"]);

    const fernhill = screen.getByTestId("SF-23-row-fernhill");
    expect(within(fernhill).getByText("fernhill")).toBeTruthy();
    expect(within(fernhill).getByText("Last opened —")).toBeTruthy();
    expect(
      within(screen.getByTestId("SF-23-row-bracken")).getByText("Last opened 01 Sep 2026"),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open Q4 2026 outlook (Scenario)" })).toBeTruthy();
    expect(screen.queryByText("Granitefield Engineering Group (Demo)")).toBeNull();
  });

  it("Open <workspace name> sends POST /session/tenant and navigates to the landing route", async () => {
    const bodies: unknown[] = [];
    acceptTenant(bodies);
    const { router } = renderSelect(withMemberships([HARBOUR, FERNHILL]));

    fireEvent.click(
      await screen.findByRole("button", { name: "Open Fernhill Software, Inc. (Demo)" }),
    );

    expect(await screen.findByRole("heading", { level: 1, name: "Home" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/home");
    expect(bodies).toEqual([{ tenant_id: FERNHILL.tenant.id }]);
    expect(announce).toHaveBeenCalledWith("Switched to Fernhill Software, Inc. (Demo)", "polite");
  });

  it("a workspace and its copies share one membership id: each is a row of its own and only the one opened is busy", async () => {
    // A sandbox copy keeps the ids of the rows it copies (SCREENS_B §9.7 "The open workspace").
    const source = membership("avenmoor", "Avenmoor Holdings (Demo)", { isDemo: true });
    const copyOf = (code: string, name: string): MeMembership => {
      const copy = membership(code, name, { kind: "sandbox" });
      return { ...copy, membership_id: source.membership_id };
    };
    const rehearsal = copyOf("sbx-rehearsal", "Close rehearsal");
    const outlook = copyOf("sbx-outlook", "Q4 outlook");
    const errors = vi.spyOn(console, "error").mockImplementation(() => undefined);
    let answer: (() => void) | undefined;
    const bodies: unknown[] = [];
    server.use(
      http.post(apiUrl("/api/v1/session/tenant"), async ({ request }) => {
        bodies.push(await request.json());
        await new Promise<void>((resolve) => {
          answer = resolve;
        });
        return HttpResponse.json({
          ...signedInSession(),
          mfa_required: false,
          mfa_enrolment_required: false,
        });
      }),
      http.get(apiUrl("/api/v1/me"), () => HttpResponse.json(signedInMe())),
      http.get(apiUrl("/api/v1/me/notifications"), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
    renderSelect(withMemberships([source, rehearsal, outlook]));

    const open = (name: string) => screen.getByRole("button", { name: `Open ${name}` });
    fireEvent.click(await screen.findByRole("button", { name: "Open Q4 outlook" }));
    await waitFor(() => {
      expect(bodies).toEqual([{ tenant_id: outlook.tenant.id }]);
    });
    expect(
      ["Avenmoor Holdings (Demo)", "Close rehearsal", "Q4 outlook"].map(
        (name) => open(name).getAttribute("aria-busy") === "true",
      ),
    ).toEqual([false, false, true]);
    // React names two children of one key on the console; three workspaces are three keys.
    expect(errors.mock.calls.filter(([message]) => String(message).includes("same key"))).toEqual(
      [],
    );
    answer?.();
    expect(await screen.findByRole("heading", { level: 1, name: "Home" })).toBeTruthy();
    errors.mockRestore();
  });

  it("with one membership the page opens it automatically", async () => {
    const bodies: unknown[] = [];
    acceptTenant(bodies);
    const { router } = renderSelect(
      withMemberships([HARBOUR, SUSPENDED]),
      signedInSession({ active_tenant: null }),
    );

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/home");
    });
    expect(bodies).toEqual([{ tenant_id: HARBOUR.tenant.id }]);
  });

  it("with none it shows You are not a member of any workspace and Sign out", async () => {
    let logouts = 0;
    server.use(
      http.post(apiUrl("/api/v1/session/logout"), () => {
        logouts += 1;
        return new HttpResponse(null, { status: 204 });
      }),
      // Sign-out clears the cache, and this page reads `GET /me` again before it leaves.
      http.get(apiUrl("/api/v1/me"), () =>
        problemResponse("unauthenticated", 401, "Authentication required"),
      ),
    );
    renderSelect(withMemberships([SUSPENDED]));

    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: "You are not a member of any workspace",
      }),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Ask a workspace administrator to invite you, or use the link in your invitation email.",
      ),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await waitFor(() => {
      expect(logouts).toBe(1);
    });
  });

  it("a refused GET /me stays on the page with the refusal, Retry and Sign out (L3-3-Q-10)", async () => {
    let reads = 0;
    server.use(
      http.get(apiUrl("/api/v1/me"), () => {
        reads += 1;
        return problemResponse("unauthenticated", 401, "Authentication required", {
          detail: "Sign in to continue.",
        });
      }),
    );
    const { router } = renderSelect(null, signedInSession({ active_tenant: null }));

    expect(await screen.findByText("Sign in to continue.")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/select-workspace");
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy();
    expect(reads).toBe(1);
  });

  it("sections and order helpers", () => {
    expect(sectionOf(OUTLOOK)).toBe("sandbox");
    expect(sectionOf(FERNHILL)).toBe("demo");
    expect(sectionOf(HARBOUR)).toBe("production");
    expect(
      openableMemberships([FERNHILL, NORTHWIND, SUSPENDED, HARBOUR]).map((m) => m.tenant.code),
    ).toEqual(["harbour", "northwind", "fernhill"]);
    // 05 SBX-07: an ACTIVE membership of a workspace that is not ACTIVE is not a workspace to open
    const archived = membership("old-copy", "Old copy (Sandbox)", {
      kind: "sandbox",
      tenantStatus: "ARCHIVED",
    });
    const copying = membership("new-copy", "New copy (Sandbox)", {
      kind: "sandbox",
      tenantStatus: "SUSPENDED",
    });
    expect(openableMemberships([archived, HARBOUR, copying]).map((m) => m.tenant.code)).toEqual([
      "harbour",
    ]);
    expect(testIdKey("Juniper Street_Coffee")).toBe("juniper-street-coffee");
  });
});
