// @vitest-environment jsdom
// SF-10:detail Import wizard (BUILD_SPEC DIN-16; SCREENS §12.2 "Step redirect by status", Step 3 rows
// grid, §12.3 import row drawer, §0.4 RT-44, §0.5 SCR-URL-32; §0.8 E-41; DESIGN_SYSTEM DS-CMP-18): the
// redirect of `/data/imports/:importId` to the step of the status, and aggregated rows with the chip
// "Aggregated" and the link to the row they were combined into (PRD J-01.10), which opens the drawer.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { installMemoryStorage, preloadScreens, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";

installMswServer();
installMemoryStorage();
installGridViewport();

// F-ADM Q21: the first test paid the redirect and step pages' module evaluation inside its waitFor window.
beforeAll(() => preloadScreens(SCREEN_ROUTES, ["X:import-redirect", "SF-10:detail"]));

afterEach(() => {
  cleanup();
});

const MAYA = signedInMe({ permissions: ["contract.read", "import.upload"] });
const IMPORT_ID = "7c1d2e3f-4a5b-4c6d-8e7f-90a1b2c3d4e5";
const REQUEST_ID = "4b5c6d7e-8f90-4a1b-9c2d-3e4f5a6b7c8d";
const SHEET = "Progress Tracking";

/** Legacy v1: Contract Progress Tracking as API-S-ImportTemplate, with two of its columns. */
const TEMPLATE = {
  code: "legacy_progress_tracking",
  version: 1,
  name: "Contract Progress Tracking",
  family: "LEGACY_V1",
  file_format: "XLSX",
  headers: [
    { name: "Contract ID", type: "text", required: true, rule_ids: [] },
    { name: "POB ID", type: "text", required: true, rule_ids: [] },
  ],
  required_parameters: [{ name: "effective_date", type: "date", allowed_values: null }],
  download_href: "/api/v1/import-templates/legacy_progress_tracking/download",
};

/** API-S-Import of the J-01.10 upload in `status`. */
function importOut(status: string): Record<string, unknown> {
  const validated = status !== "UPLOADED" && status !== "VALIDATING";
  const submitted = ["SUBMITTED", "APPROVED", "COMMITTING", "COMMITTED", "FAILED"].includes(status);
  return {
    id: IMPORT_ID,
    import_no: "IMP-000007",
    template: { code: TEMPLATE.code, version: 1, name: TEMPLATE.name },
    file: {
      id: "8d2e3f4a-5b6c-4d7e-9f80-a1b2c3d4e5f6",
      original_filename: "Contract Progress Tracking Template 1.31.2023.xlsx",
      sha256: `9a1b${"0".repeat(56)}c2d3`,
      size_bytes: 20480,
    },
    parameters: { effective_date: "2023-01-31" },
    status,
    counts: validated
      ? {
          rows: 3,
          valid: 1,
          warnings: 0,
          errors: status === "INVALID" ? 1 : 0,
          aggregated: 2,
          blank: 0,
        }
      : { rows: null, valid: null, warnings: null, errors: null, aggregated: 0, blank: 0 },
    is_quarantine_mode: false,
    control_totals: validated
      ? {
          source: { rows: 3, amount_sums: {}, sha256: "0".repeat(64) },
          loaded: status === "COMMITTED" ? { rows: 3, amount_sums: {} } : null,
        }
      : null,
    finding_counts:
      status === "INVALID" ? [{ code: "CONTRACT_NOT_FOUND", severity: "ERROR", rows: 1 }] : [],
    header_match: [],
    diff_summary: ["DIFF_READY", ...(submitted ? [status] : [])].includes(status)
      ? {
          contracts_affected: 2,
          contracts_created: 0,
          allocation_changes: [],
          revenue_by_period_delta: [{ period_key: "FY2023-P01", amount: "128.84" }],
          journal_preview: [],
        }
      : null,
    approval_request_id: submitted ? REQUEST_ID : null,
    committed_at: status === "COMMITTED" ? "2023-02-01T10:00:00Z" : null,
    exceptions_href: `/api/v1/exceptions?import_upload_id=${IMPORT_ID}`,
    created_by: {
      id: "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a",
      kind: "USER",
      display_name: "Maya Chen",
    },
    created_at: "2023-02-01T09:30:00Z",
    updated_at: "2023-02-01T09:31:00Z",
  };
}

const ROW_2 = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d";

/** PRD J-01.10: the two Contract 1 POB #1 rows 3 and 4 are aggregated into row 2. */
function rows(): Record<string, unknown>[] {
  const row = (number: number, id: string, status: string, into: string | null) => ({
    id,
    sheet_name: SHEET,
    row_number: number,
    status,
    business_key: "Contract 1 / POB #1",
    raw: { "Contract ID": "Contract 1", "POB ID": "POB #1" },
    normalized: null,
    messages: [],
    aggregated_into_row_id: into,
    lineage: [],
  });
  return [
    row(3, "2b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6e", "AGGREGATED", ROW_2),
    row(4, "3c4d5e6f-7a8b-4c9d-8e0f-2a3b4c5d6e7f", "AGGREGATED", ROW_2),
    row(2, ROW_2, "VALID", null),
  ];
}

const APPROVAL = {
  id: REQUEST_ID,
  request_no: "AR-000031",
  status: "PENDING",
  subject: {
    type: "IMPORT_COMMIT",
    id: IMPORT_ID,
    display: "IMP-000007",
    href: null,
    content_sha256: "0".repeat(64),
  },
  summary: "Commit IMP-000007",
  preparer: { id: "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a", kind: "USER", display_name: "Maya Chen" },
  submitted_at: "2023-02-01T09:40:00Z",
  current_step_no: 1,
  steps: [
    {
      step_no: 1,
      name: "Controller approval",
      required_permission: "import.approve",
      min_approvers: 1,
      status: "ACTIVE",
      decisions: [],
    },
  ],
  routing: { rule_key: null, rule_set_version_id: null },
  can_decide: false,
  flags: [],
  attachments: [],
  amount: null,
  entity: null,
  impact_preview: null,
  decided_at: null,
  voided_at: null,
  void_reason: null,
};

/** The shell's reads and the screen's reads; each rows search is recorded. */
function serve(status: () => string, searches: string[] = []) {
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/books"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/periods"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/import-templates"), () =>
      HttpResponse.json({ items: [TEMPLATE], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/jobs"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl(`/api/v1/imports/${IMPORT_ID}`), () => HttpResponse.json(importOut(status()))),
    http.get(apiUrl(`/api/v1/imports/${IMPORT_ID}/rows`), ({ request }) => {
      const url = new URL(request.url);
      searches.push(url.search);
      const number = url.searchParams.get("row_number");
      const items = rows().filter((row) => number === null || String(row.row_number) === number);
      return HttpResponse.json(
        { items, next_cursor: null },
        {
          headers:
            url.searchParams.get("count") === "true"
              ? { "X-Erev-Total-Count": String(items.length) }
              : {},
        },
      );
    }),
    http.get(apiUrl(`/api/v1/imports/${IMPORT_ID}/diff`), () =>
      HttpResponse.json({
        summary_counts: {
          contracts_added: 0,
          contracts_changed: 2,
          obligations_added: 0,
          obligations_changed: 1,
        },
        items: [
          {
            change: "CHANGED",
            contract_external_id: "Contract 1",
            obligation_key: "POB #1",
            measure: "revenue_cum",
            before: "0.00",
            after: "128.84",
          },
        ],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl(`/api/v1/approvals/${REQUEST_ID}`), () => HttpResponse.json(APPROVAL)),
  );
}

describe("SF-10:detail", () => {
  it("redirect by status", async () => {
    const cases: readonly (readonly [string, string])[] = [
      ["INVALID", "validate"],
      ["DIFF_READY", "review"],
      ["SUBMITTED", "approval"],
      ["COMMITTED", "committed"],
    ];
    for (const [status, step] of cases) {
      serve(() => status);
      const { router } = renderApp(`/data/imports/${IMPORT_ID}`, {
        me: MAYA,
        screenRoutes: SCREEN_ROUTES,
      });
      await waitFor(() => {
        expect(router.state.location.pathname).toBe(`/data/imports/${IMPORT_ID}/${step}`);
      });
      // The step page itself renders: the stepper marks its step as current.
      const stepper = await screen.findByRole("navigation", { name: "Import steps" });
      await waitFor(() => {
        expect(within(stepper).getByRole("listitem", { current: "step" }).textContent).toMatch(
          /^Step [3-6] of 6/,
        );
      });
      expect(
        screen.getByRole("heading", { level: 1, name: "Legacy v1: Contract Progress Tracking" }),
      ).toBeTruthy();
      cleanup();
    }
  });

  it("rows grid shows aggregated chip", async () => {
    const searches: string[] = [];
    serve(() => "DIFF_READY", searches);
    const { router } = renderApp(`/data/imports/${IMPORT_ID}/validate`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const grid = await within(await screen.findByTestId("SF-10-grid-rows")).findByRole("grid", {
      name: "Import rows",
    });
    const aggregated = await within(grid).findByTestId("SF-10-row-3");
    expect(within(aggregated).getByText("Aggregated")).toBeTruthy();
    const link = await within(aggregated).findByRole("link", { name: "Into row 2" });
    expect(link.getAttribute("href")).toBe(
      `/data/imports/${IMPORT_ID}/validate?row=2&sheet=Progress%20Tracking`,
    );
    expect(within(await within(grid).findByTestId("SF-10-row-2")).getByText("Valid")).toBeTruthy();
    // The grid binds the rows errors first (D-87, L6-4-Q-14) and the legacy columns follow.
    expect(searches.some((search) => search.includes("sort=severity"))).toBe(true);
    expect(within(grid).getAllByText("Contract 1").length).toBeGreaterThan(0);

    fireEvent.click(link);
    await waitFor(() => {
      expect(router.state.location.search).toBe("?row=2&sheet=Progress%20Tracking");
    });
    const drawer = await screen.findByRole("dialog", { name: /^Row / });
    expect(within(drawer).getByTestId("SF-10-drawer-row")).toBeTruthy();
    expect(await within(drawer).findByText("Contract 1 / POB #1")).toBeTruthy();
    expect(searches).toContain("?row_number=2&sheet_name=Progress+Tracking&limit=1");
  });

  // SCREENS §0.6 SCR-PERM-02 (rev 1.34; item W-12, slice b; supervisor ruling R-28): the page follows the
  // import through the jobs of the workspace. A read of them the API refuses leaves the stand-in the
  // page shows while a job is not readable, and is not sent again with the page's poll.
  it("a refused read of the jobs keeps the stand-in progress and is not sent again while the import runs", async () => {
    const jobs: string[] = [];
    let imports = 0;
    serve(() => "VALIDATING");
    server.use(
      http.get(apiUrl("/api/v1/jobs"), ({ request }) => {
        jobs.push(new URL(request.url).search);
        return problemResponse("forbidden", 403, "Permission denied");
      }),
      http.get(apiUrl(`/api/v1/imports/${IMPORT_ID}`), () => {
        imports += 1;
        return HttpResponse.json(importOut("VALIDATING"));
      }),
    );
    renderApp(`/data/imports/${IMPORT_ID}/validate`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    expect(await screen.findByRole("progressbar", { name: /^Validating / })).toBeTruthy();
    expect(screen.queryByText("Permission denied")).toBeNull();
    // The page polls the import every 2 s while it runs, and polled the jobs with it. Two more reads
    // of the import have passed; the jobs were asked once.
    await waitFor(
      () => {
        expect(imports).toBeGreaterThanOrEqual(3);
      },
      { timeout: 9000 },
    );
    expect(jobs).toHaveLength(1);
    expect(screen.getByRole("progressbar", { name: /^Validating / })).toBeTruthy();
  }, 15_000);
});
