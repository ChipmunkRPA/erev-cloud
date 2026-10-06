// @vitest-environment jsdom
// SF-14:sod and REQ-PLT-010 (BUILD_SPEC WEB-20; SCREENS_B §9.12; 04 API-R-07 `GET /sod-rules`,
// `GET /sod-exceptions?status`, `POST /sod-exceptions/{id}/revoke`; BS1-D-14): the panel tabs Rules and
// Exceptions (`pane=rules|exceptions`); the rules grid "SoD rules" shows SoD-1 to SoD-7 with their function
// permissions, version and status; the exceptions grid "SoD exceptions" shows the compensating control,
// validity and status; "Revoke exception" requires a reason and states its consequence; the empty
// exceptions state reads "No SoD exceptions"; the "SoD conflict report" link is not rendered.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import type { SodException, SodRule } from "../../lib/api/queries/roles";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, server } from "../../test/msw";
import { REFUSAL_REFERENCE, REFUSAL_TITLE, refusedWith } from "../../test/refusals";
import { exceptionQuery, exceptionFilterFields, sodPaneOf } from "./sod";

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

const TOMAS = signedInMe({ permissions: ["user.manage", "role.manage"] });

const RULE_NAMES: Record<number, string> = {
  1: "User administration with transaction or approval permissions",
  2: "Configuration authoring with configuration approval",
  3: "Revenue Accountant with Revenue Reviewer lets one person create and approve the same contract or modification",
  4: "Journal run with journal approval",
  5: "Estimate creation with estimate approval",
  6: "Import upload with import approval",
  7: "Period close with period lock",
};

function rule(n: number): SodRule {
  return {
    id: `${String(n).padStart(8, "0")}-3333-4333-8333-333333333333`,
    code: `SoD-${String(n)}`,
    name: RULE_NAMES[n] ?? `Rule ${String(n)}`,
    rationale: `Rationale ${String(n)}.`,
    function_a_permissions: [`function_a.${String(n)}`],
    function_b_permissions: [`function_b.${String(n)}`],
    version_no: n === 3 ? 2 : 1,
    status: "PUBLISHED",
    published_at: "2026-09-01T08:00:00Z",
    published_by: null,
    effective_from: null,
    effective_to: null,
    supersedes_version_id: null,
    approval_request_id: null,
    pending_approval_request_id: null,
    content_sha256: null,
    row_version: 1,
    created_at: "2026-09-01T08:00:00Z",
    updated_at: "2026-09-01T08:00:00Z",
  };
}

const RULES = [1, 2, 3, 4, 5, 6, 7].map(rule);

const EXCEPTION: SodException = {
  id: "55555555-5555-4555-8555-555555555555",
  membership_id: "9b8a7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d",
  member_name: "Lena Fischer",
  sod_rule_code: "SoD-3",
  compensating_control:
    "Controller reviews every approval by Lena Fischer monthly using the approvals register.",
  valid_from: "2026-09-12T19:30:00Z",
  valid_to: "2026-12-11T19:30:00Z",
  status: "APPROVED",
  approval_request_id: "8f7e6d5c-4b3a-4c2d-9e1f-0a9b8c7d6e5f",
  approved_at: "2026-09-12T19:30:00Z",
  created_by: { id: TOMAS.user.id, kind: "USER", display_name: "Tomás Rivera" },
  created_at: "2026-09-12T19:02:00Z",
  revoked_at: null,
  revoked_by: null,
};

function serve(exceptions: readonly SodException[], searches: string[] = []) {
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/books"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/periods"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/saved-views"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/sod-rules"), ({ request }) =>
      HttpResponse.json(
        { items: RULES, next_cursor: null },
        {
          headers:
            new URL(request.url).searchParams.get("count") === "true"
              ? { "X-Erev-Total-Count": String(RULES.length) }
              : {},
        },
      ),
    ),
    http.get(apiUrl("/api/v1/sod-exceptions"), ({ request }) => {
      const url = new URL(request.url);
      searches.push(url.search);
      return HttpResponse.json(
        { items: exceptions, next_cursor: null },
        {
          headers:
            url.searchParams.get("count") === "true"
              ? { "X-Erev-Total-Count": String(exceptions.length) }
              : {},
        },
      );
    }),
  );
}

describe("SF-14:sod and REQ-PLT-010", () => {
  it("panel tabs Rules and Exceptions; the rules grid shows SoD-1 to SoD-7 with their functions, version and status", async () => {
    serve([EXCEPTION]);
    const { router } = renderApp("/settings/separation-of-duties", {
      me: TOMAS,
      screenRoutes: SCREEN_ROUTES,
    });

    const tabs = await screen.findByRole("tablist", { name: "Separation of duties panels" });
    expect(within(tabs).getByRole("tab", { name: "Rules", selected: true })).toBeTruthy();
    expect(within(tabs).getByRole("tab", { name: "Exceptions" })).toBeTruthy();
    const grid = await within(await screen.findByTestId("SF-14-grid-sod-rules")).findByRole(
      "grid",
      { name: "SoD rules" },
    );
    for (let n = 1; n <= 7; n++) {
      expect(await within(grid).findByRole("rowheader", { name: `SoD-${String(n)}` })).toBeTruthy();
    }
    const third = screen.getByTestId("SF-14-row-sod-3");
    expect(within(third).getByText("function_a.3")).toBeTruthy();
    expect(within(third).getByText("function_b.3")).toBeTruthy();
    expect(within(third).getByText("v2")).toBeTruthy();
    expect(within(third).getByText("Published")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "SoD conflict report" })).toBeNull();
    expect(screen.queryByText("SoD conflict report")).toBeNull();

    fireEvent.click(within(tabs).getByRole("tab", { name: "Exceptions" }));
    await waitFor(() => {
      expect(router.state.location.search).toBe("?pane=exceptions");
    });
    expect(await screen.findByTestId("SF-14-grid-sod-exceptions")).toBeTruthy();
    fireEvent.click(within(tabs).getByRole("tab", { name: "Rules" }));
    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
    expect(sodPaneOf(null)).toBe("rules");
    expect(sodPaneOf("exceptions")).toBe("exceptions");
    expect(sodPaneOf("other")).toBe("rules");
  });

  it("a panel tab takes the list parameters of the pane it leaves with it, so the next pane reports no bad link", async () => {
    // Crawl finding F4: the Rules grid's own sort stayed in the URL, and the Exceptions grid, which
    // lists no such key, dropped it with the SCR-URL-21 banner of a link that was never followed.
    serve([EXCEPTION]);
    const { router } = renderApp("/settings/separation-of-duties?sort=code", {
      me: TOMAS,
      screenRoutes: SCREEN_ROUTES,
    });
    const tabs = await screen.findByRole("tablist", { name: "Separation of duties panels" });
    await within(await screen.findByTestId("SF-14-grid-sod-rules")).findByRole("grid", {
      name: "SoD rules",
    });

    fireEvent.click(within(tabs).getByRole("tab", { name: "Exceptions" }));
    await waitFor(() => {
      expect(router.state.location.search).toBe("?pane=exceptions");
    });
    expect(await screen.findByTestId("SF-14-grid-sod-exceptions")).toBeTruthy();
    expect(
      screen.queryByText("Some filters in the link were not recognised and were removed."),
    ).toBeNull();

    // And back: the filter chip and the search of the Exceptions pane do not follow to Rules.
    await router.navigate(
      "/settings/separation-of-duties?pane=exceptions&f.status=is:APPROVED&q=audit",
    );
    fireEvent.click(
      within(await screen.findByRole("tablist", { name: "Separation of duties panels" })).getByRole(
        "tab",
        { name: "Rules" },
      ),
    );
    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
    expect(
      screen.queryByText("Some filters in the link were not recognised and were removed."),
    ).toBeNull();
  });

  it("the exceptions grid shows the compensating control, validity and status; Revoke exception requires a reason", async () => {
    const searches: string[] = [];
    const bodies: unknown[] = [];
    serve([EXCEPTION], searches);
    server.use(
      http.post(apiUrl(`/api/v1/sod-exceptions/${EXCEPTION.id}/revoke`), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({
          ...EXCEPTION,
          status: "REVOKED",
          revoked_at: "2026-09-19T12:00:00Z",
        });
      }),
    );
    renderApp("/settings/separation-of-duties?pane=exceptions&f.status=is:APPROVED", {
      me: TOMAS,
      screenRoutes: SCREEN_ROUTES,
    });

    const grid = await within(await screen.findByTestId("SF-14-grid-sod-exceptions")).findByRole(
      "grid",
      { name: "SoD exceptions" },
    );
    const row = await within(grid).findByRole("row", { name: /Lena Fischer/ });
    expect(
      within(row).getByText(
        "Controller reviews every approval by Lena Fischer monthly using the approvals register.",
      ),
    ).toBeTruthy();
    expect(within(row).getByText("12 Sep 2026")).toBeTruthy();
    expect(within(row).getByText("11 Dec 2026")).toBeTruthy();
    expect(within(row).getByText("Approved")).toBeTruthy();
    expect(new URLSearchParams(searches[0] ?? "").getAll("status")).toEqual(["APPROVED"]);

    fireEvent.click(within(row).getByRole("button", { name: "Revoke exception" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Revoke the SoD-3 exception for Lena Fischer?",
    });
    expect(
      within(dialog).getByText(
        "Revoking the exception blocks the conflicting role assignment. Revoke the role first or it becomes a conflict without an exception.",
      ),
    ).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Revoke exception" }));
    expect(await within(dialog).findByText(/at least 10 characters/i)).toBeTruthy();
    expect(bodies).toEqual([]);

    fireEvent.change(within(dialog).getByRole("textbox", { name: "Reason (required)" }), {
      target: { value: "Lena moved to the reviewer team only." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Revoke exception" }));
    expect(await screen.findByText("Exception SoD-3 for Lena Fischer revoked.")).toBeTruthy();
    expect(bodies).toEqual([{ reason: "Lena moved to the reviewer team only." }]);
    expect(exceptionQuery("?f.status=in:APPROVED,REQUESTED", exceptionFilterFields())).toEqual({
      status: ["APPROVED", "REQUESTED"],
    });
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): the dialog shows no message at its
  // reason, so the banner says every sentence of a refusal; one that names a member was shown nowhere.
  it("Revoke exception under a refused command says every sentence", async () => {
    const sentence = "Revoke the role this exception covers first.";
    serve([EXCEPTION]);
    server.use(
      http.post(apiUrl(`/api/v1/sod-exceptions/${EXCEPTION.id}/revoke`), () =>
        refusedWith({ status: sentence }),
      ),
    );
    renderApp("/settings/separation-of-duties?pane=exceptions&f.status=is:APPROVED", {
      me: TOMAS,
      screenRoutes: SCREEN_ROUTES,
    });
    const grid = await within(await screen.findByTestId("SF-14-grid-sod-exceptions")).findByRole(
      "grid",
      { name: "SoD exceptions" },
    );
    const row = await within(grid).findByRole("row", { name: /Lena Fischer/ });
    fireEvent.click(within(row).getByRole("button", { name: "Revoke exception" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Revoke the SoD-3 exception for Lena Fischer?",
    });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Reason (required)" }), {
      target: { value: "Lena moved to the reviewer team only." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Revoke exception" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + sentence + REFUSAL_REFERENCE);
  });

  it("the empty exceptions state reads No SoD exceptions", async () => {
    serve([]);
    renderApp("/settings/separation-of-duties?pane=exceptions", {
      me: TOMAS,
      screenRoutes: SCREEN_ROUTES,
    });
    expect(await screen.findByRole("heading", { name: "No SoD exceptions" })).toBeTruthy();
    expect(
      screen.getByText(
        "Approved exceptions allow a conflicting role combination for a limited time with a compensating control.",
      ),
    ).toBeTruthy();
  });
});
