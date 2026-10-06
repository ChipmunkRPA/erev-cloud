// @vitest-environment jsdom
// SF-03:modifications Modifications tab (BUILD_SPEC CTR-24; SCREENS §4.6; §0.8 E-26; DESIGN_SYSTEM
// DS-FMT-31; 04 API-R-31, §16.14 API-S-Modification list items): the grid of the contract's modifications
// with the reference (or the modification number), the kind, the treatment and status labels, the signed
// catch-up total of the stored preview and the preparer; the Status and Effective date filters reach the
// list request; the tab carries the count.
import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../../app/router";
import { installMemoryStorage, preloadScreens, renderApp, signedInMe } from "../../../test/app";
import {
  CONTEXT,
  CONTRACT_ID,
  K02,
  MAYA_USER,
  money,
  serveWorkbench,
  workbenchContract,
} from "../../../test/workbench";
import { installGridViewport } from "../../../test/layout";
import { apiUrl, installMswServer, server } from "../../../test/msw";
import { newModificationHref } from "./modifications";

installMswServer();
installMemoryStorage();
installGridViewport();
configure({ asyncUtilTimeout: 5000 });

beforeAll(async () => {
  await preloadScreens(SCREEN_ROUTES, ["SF-03:modifications"]);
});

afterEach(() => {
  cleanup();
});

const MAYA = signedInMe({
  permissions: ["contract.read", "contract.create", "config.read", "modification.create"],
});

function modification(overrides: Readonly<Record<string, unknown>>): Record<string, unknown> {
  return {
    id: "b1b1b1b1-b1b1-4b1b-8b1b-b1b1b1b1b1b1",
    contract_id: CONTRACT_ID,
    contracting_entity_id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000001",
    modification_no: "MOD-000007",
    reference: "CR-MARROWBY-2026-09",
    kind: "UPGRADE",
    status: "APPLIED",
    effective_date: "2026-09-16",
    currency: "USD",
    rationale: null,
    template_mode: null,
    treatment_summary: "PROSPECTIVE",
    proposed_treatments: { O1: "PROSPECTIVE" },
    chosen_treatments: { O1: "PROSPECTIVE" },
    impact_summary: { catch_up_total: money("0.00") },
    impact_preview_sha256: "a".repeat(64),
    content_sha256: "b".repeat(64),
    judgement_record_id: null,
    regroup_id: null,
    approval_request_id: null,
    applied_event_id: null,
    approver: null,
    approved_at: null,
    preparer: MAYA_USER,
    row_version: 6,
    created_at: "2026-09-16T09:00:00Z",
    updated_at: "2026-09-16T11:00:00Z",
    ...overrides,
  };
}

const MODIFICATIONS = [
  modification({}),
  modification({
    id: "b2b2b2b2-b2b2-4b2b-8b2b-b2b2b2b2b2b2",
    modification_no: "MOD-000009",
    reference: null,
    kind: "OTHER",
    status: "SUBMITTED",
    effective_date: "2026-09-10",
    treatment_summary: "CUMULATIVE_CATCH_UP",
    impact_summary: { catch_up_total: money("91463.41") },
  }),
  modification({
    id: "b3b3b3b3-b3b3-4b3b-8b3b-b3b3b3b3b3b3",
    modification_no: "MOD-000011",
    reference: "CR-MARROWBY-2026-10",
    kind: "PRICE_CHANGE",
    status: "DRAFT",
    effective_date: "2026-10-01",
    treatment_summary: null,
    impact_summary: { catch_up_total: null },
    template_mode: "pob_price_change",
  }),
];

function serveList(
  requests: string[],
  items: readonly Record<string, unknown>[] = MODIFICATIONS,
  contract?: Record<string, unknown>,
) {
  serveWorkbench({
    modificationCount: items.length,
    ...(contract === undefined ? {} : { contract }),
  });
  server.use(
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/modifications`), ({ request }) => {
      const url = new URL(request.url);
      requests.push(url.search);
      return HttpResponse.json(
        { items, next_cursor: null },
        { headers: { "X-Erev-Total-Count": String(items.length) } },
      );
    }),
  );
}

/** The text a sighted reader sees in each cell: the visually hidden sign words are left out. */
function cellTexts(row: HTMLElement): string[] {
  return Array.from(row.querySelectorAll("[role='rowheader'], [role='gridcell']"), (cell) => {
    const shown = cell.cloneNode(true) as HTMLElement;
    for (const hidden of shown.querySelectorAll(".sr-only")) {
      hidden.remove();
    }
    return (shown.textContent ?? "").trim();
  });
}

describe("SF-03:modifications", () => {
  it("lists the modifications with their labels, the signed catch-up and the preparer", async () => {
    const requests: string[] = [];
    serveList(requests);
    renderApp(`/contracts/${CONTRACT_ID}/modifications?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const section = await screen.findByTestId("SF-03-grid-modifications");
    const grid = await within(section).findByRole("grid", { name: "Modifications" });
    // SCREENS §4.2 to §4.10 accessibility: the tab root is a section with an h2 equal to the tab label.
    expect(within(section).getByRole("heading", { level: 2, name: "Modifications" })).toBeTruthy();
    expect(
      within(grid)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual([
      "Reference",
      "Kind",
      "Effective date",
      "Treatment",
      "Status",
      "Catch-up (USD)",
      "Prepared by",
    ]);
    const upgrade = await screen.findByTestId("SF-03-row-cr-marrowby-2026-09");
    expect(cellTexts(upgrade)).toEqual([
      "CR-MARROWBY-2026-09",
      "Upgrade",
      "16 Sep 2026",
      "Prospective (ASC 606-10-25-13(a))",
      "Applied",
      "0.00",
      "Maya Chen",
    ]);
    // No reference: the modification number stands; a positive catch-up carries its sign (DS-FMT-31).
    expect(cellTexts(screen.getByTestId("SF-03-row-mod-000009"))).toEqual([
      "MOD-000009",
      "Other",
      "10 Sep 2026",
      "Cumulative catch-up (ASC 606-10-25-13(b))",
      "Pending approval",
      "+91,463.41",
      "Maya Chen",
    ]);
    // A draft without a classification or a preview shows no treatment and no figure.
    expect(cellTexts(screen.getByTestId("SF-03-row-cr-marrowby-2026-10"))).toEqual([
      "CR-MARROWBY-2026-10",
      "Price change",
      "01 Oct 2026",
      "—",
      "Draft",
      "—",
      "Maya Chen",
    ]);
    expect(within(section).getByText("3 modifications")).toBeTruthy();

    // The frame: the tab is current and carries the count of the list read.
    const tab = screen
      .getByRole("navigation", { name: `${K02} sections` })
      .querySelector("a[aria-current='page']");
    expect(tab?.textContent?.replace(/\s+/g, " ").trim()).toBe("Modifications 3");
    // The default list request: newest first, no filter.
    expect(
      requests.some((search) => search.includes("sort=-id") && !search.includes("status=")),
    ).toBe(true);
  });

  it("the Status and Effective date filters reach the list request", async () => {
    const requests: string[] = [];
    serveList(requests);
    renderApp(
      `/contracts/${CONTRACT_ID}/modifications?${CONTEXT}&f.status=in:DRAFT,SUBMITTED&f.effective_date=between:2026-09-01,2026-09-30`,
      { me: MAYA, screenRoutes: SCREEN_ROUTES },
    );

    await screen.findByTestId("SF-03-row-cr-marrowby-2026-09");
    await waitFor(() =>
      expect(
        requests.some((search) => {
          const params = new URLSearchParams(search);
          return (
            params.getAll("status").join(",") === "DRAFT,SUBMITTED" &&
            params.get("effective_from") === "2026-09-01" &&
            params.get("effective_to") === "2026-09-30"
          );
        }),
      ).toBe(true),
    );
    const chips = screen.getByTestId("SF-03-filter-bar-modifications");
    expect(
      within(chips).getByRole("button", {
        name: "Status is Draft or Pending approval, edit filter",
      }),
    ).toBeTruthy();
  });

  it("New modification and Change subscription are the header's commands for a preparer on an active contract", async () => {
    serveList([]);
    renderApp(`/contracts/${CONTRACT_ID}/modifications?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const section = await screen.findByTestId("SF-03-grid-modifications");
    await screen.findByTestId("SF-03-row-cr-marrowby-2026-09");
    // SCREENS §4.1.6 (rev 1.29): the header is the one place of the two commands; the tab's
    // toolbar carries neither.
    expect(screen.getAllByRole("button", { name: "New modification" })).toHaveLength(1);
    expect(within(section).queryByRole("button", { name: "New modification" })).toBeNull();
    expect(within(section).queryByRole("button", { name: "Change subscription" })).toBeNull();
    const header = screen.getByRole("button", { name: "Change subscription" });
    fireEvent.click(header);
    expect((await screen.findAllByRole("menuitem")).map((item) => item.textContent)).toEqual([
      "Upgrade",
      "Downgrade",
      "Co-term",
      "Renew",
      "Early renew",
      "Cancel",
    ]);
    // The link of each command: SF-07 with the context and, for a subscription change, its action.
    expect(newModificationHref(CONTRACT_ID, `?${CONTEXT}`)).toBe(
      `/contracts/${CONTRACT_ID}/modifications/new?${CONTEXT}`,
    );
    expect(newModificationHref(CONTRACT_ID, `?${CONTEXT}`, "early_renew")).toBe(
      `/contracts/${CONTRACT_ID}/modifications/new?${CONTEXT}&action=early_renew`,
    );
  });

  it("offers neither command on a completed contract or without modification.create", async () => {
    // API-R-31 refuses a modification of a contract that is not active.
    serveList([], MODIFICATIONS, workbenchContract({ status: "COMPLETED" }));
    renderApp(`/contracts/${CONTRACT_ID}/modifications?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    await screen.findByTestId("SF-03-row-cr-marrowby-2026-09");
    expect(screen.queryByRole("button", { name: "New modification" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Change subscription" })).toBeNull();
    cleanup();
    server.resetHandlers();

    serveList([]);
    renderApp(`/contracts/${CONTRACT_ID}/modifications?${CONTEXT}`, {
      me: signedInMe({ permissions: ["contract.read", "config.read"] }),
      screenRoutes: SCREEN_ROUTES,
    });
    await screen.findByTestId("SF-03-row-cr-marrowby-2026-09");
    expect(screen.queryByRole("button", { name: "New modification" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Change subscription" })).toBeNull();
  });

  it("a contract without modifications shows the empty state", async () => {
    serveList([], []);
    renderApp(`/contracts/${CONTRACT_ID}/modifications?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    expect(await screen.findByRole("heading", { level: 3, name: "No modifications" })).toBeTruthy();
    expect(
      screen.getByText(
        "Changes to scope or price appear here with their classification and approval.",
      ),
    ).toBeTruthy();
    // The empty state of an active contract keeps its action beside the header's command.
    const section = screen.getByTestId("SF-03-grid-modifications");
    expect(within(section).getAllByRole("button", { name: "New modification" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "New modification" })).toHaveLength(2);
    cleanup();
    server.resetHandlers();

    // A contract that is not active takes no modification: the empty state offers none.
    serveList([], [], workbenchContract({ status: "COMPLETED" }));
    renderApp(`/contracts/${CONTRACT_ID}/modifications?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    expect(await screen.findByRole("heading", { level: 3, name: "No modifications" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "New modification" })).toBeNull();
  });
});
