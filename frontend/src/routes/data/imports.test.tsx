// @vitest-environment jsdom
// SF-10 Imports list (BUILD_SPEC DIN-15; SCREENS §12.1 columns, states and test hooks, §0.3 SCR-IA-02, §0.8
// E-40; PRD SM-05, §2.9 WLD-B-04): an `INVALID` import renders "Error" with the caption "Rejected: fix the
// file and upload again"; the Data frame shows the built tabs; the grid binds `GET /imports` newest first
// and the Status chip reaches the API. SF-10:templates (§12.4): the static table "Import templates" and the
// mapping profiles grid against a fake of the DIN-10 contract (D-81 integration after merge; V-C).
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

const MAYA = signedInMe({ permissions: ["contract.read", "import.upload", "config.author"] });

/** `name` as seeded, without the family; the screens show the SCREENS §12.4 copy (L6-4-Q-12). */
const TEMPLATE = {
  code: "progress_events",
  version: 1,
  name: "Progress events",
  family: "CSV_V2",
  file_format: "CSV",
  headers: [],
  required_parameters: [],
  download_href: "/api/v1/import-templates/progress_events/download",
};

/** PRD §2.9 WLD-B-04 as API-S-Import. */
function invalidImport(): Record<string, unknown> {
  const id = "7c1d2e3f-4a5b-4c6d-8e7f-90a1b2c3d4e5";
  return {
    id,
    import_no: "IMP-000001",
    template: { code: "progress_events", version: 1, name: "Progress events" },
    file: {
      id: "8d2e3f4a-5b6c-4d7e-9f80-a1b2c3d4e5f6",
      original_filename: "avm-us-progress-2026-09-invalid.csv",
      sha256: `3f9c${"0".repeat(56)}7d1e`,
      size_bytes: 1520,
    },
    parameters: {},
    status: "INVALID",
    counts: { rows: 14, valid: 12, warnings: 0, errors: 2, aggregated: 0, blank: 0 },
    is_quarantine_mode: false,
    control_totals: null,
    finding_counts: [{ code: "PROGRESS_OVER_DELIVERY", severity: "ERROR", rows: 2 }],
    header_match: [],
    diff_summary: null,
    approval_request_id: null,
    committed_at: null,
    exceptions_href: `/api/v1/exceptions?import_upload_id=${id}`,
    created_by: {
      id: "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a",
      kind: "USER",
      display_name: "Maya Chen",
    },
    created_at: "2026-09-12T09:30:00Z",
    updated_at: "2026-09-12T09:30:05Z",
  };
}

/** The shell's reads and the screen's reads; each `GET /imports` search is recorded. */
function serve(searches: string[]) {
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
    http.get(apiUrl("/api/v1/import-templates"), () =>
      HttpResponse.json({ items: [TEMPLATE], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/imports"), ({ request }) => {
      const url = new URL(request.url);
      searches.push(url.search);
      const counting = url.searchParams.get("count") === "true";
      return HttpResponse.json(
        { items: [invalidImport()], next_cursor: null },
        { headers: counting ? { "X-Erev-Total-Count": "1" } : {} },
      );
    }),
  );
}

/** The recorded searches without the paging parameters `limit`, `cursor` and `count`. */
function bindings(searches: readonly string[]): string[] {
  return searches.map((search) => {
    const params = new URLSearchParams(search);
    params.delete("limit");
    params.delete("cursor");
    params.delete("count");
    return params.toString();
  });
}

describe("SF-10 imports list", () => {
  it("rejected caption", async () => {
    const searches: string[] = [];
    serve(searches);
    renderApp("/data/imports", { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-10-grid-imports")).findByRole("grid", {
      name: "Imports",
    });
    expect(
      await within(grid).findByRole("rowheader", { name: "avm-us-progress-2026-09-invalid.csv" }),
    ).toBeTruthy();
    const row = screen.getByTestId("SF-10-row-avm-us-progress-2026-09-invalid-csv");
    expect(within(row).getByText("Error")).toBeTruthy();
    expect(within(row).getByText("Rejected: fix the file and upload again")).toBeTruthy();
    expect(within(row).getByText("Progress events (CSV v2)")).toBeTruthy();

    expect(screen.getByRole("heading", { level: 1, name: "Imports" })).toBeTruthy();
    // The count label follows the total from the page header in a later commit (F-ADM Q21).
    expect(await screen.findByText("1 import")).toBeTruthy();
    // SCR-IA-02: the tabs of built Data pages; SF-11 is built (BUILD_SPEC DIN-17).
    const tabs = screen.getByRole("navigation", { name: "Data sections" });
    expect(
      within(tabs)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["Imports", "Exceptions", "Templates"]);
    // SF-10:new is built (BUILD_SPEC DIN-16), so "New import" renders beside "Download templates".
    expect(screen.getByRole("button", { name: "New import" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Download templates" })).toBeTruthy();
    expect(bindings(searches)).toEqual(["sort=-created_at"]);
  });

  it("status chip sends literals", async () => {
    const searches: string[] = [];
    serve(searches);
    renderApp("/data/imports?f.status=in:INVALID,FAILED", {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    await within(await screen.findByTestId("SF-10-grid-imports")).findByRole("grid", {
      name: "Imports",
    });
    await waitFor(() => {
      expect(bindings(searches)).toContain("status=INVALID&status=FAILED&sort=-created_at");
    });
  });
});

const LEGACY_SKU_SSP = {
  code: "legacy_sku_ssp",
  version: 1,
  name: "SKU SSP",
  family: "LEGACY_V1",
  file_format: "XLSX",
  headers: [],
  required_parameters: [],
  download_href: "/api/v1/import-templates/legacy_sku_ssp/download",
};

/** One DRAFT version as DIN-10 `MappingProfileOut` (the contract fake of integration after merge). */
function draftProfile(status: string): Record<string, unknown> {
  return {
    id: "2e4f6a8b-1c3d-4e5f-8a9b-0c1d2e3f4a5b",
    code: "NS-PROGRESS",
    name: "NetSuite progress export",
    template_code: "progress_events",
    mappings: { aliases: { "SO Number": "contract" }, constants: {}, custom_attributes: [] },
    version_no: 1,
    status,
    effective_from: null,
    effective_to: null,
    content_sha256: null,
    approval_request_id: null,
    published_at: null,
    published_by: null,
    supersedes_version_id: null,
    created_at: "2026-09-12T09:00:00Z",
    updated_at: "2026-09-12T09:00:00Z",
    row_version: 1,
  };
}

describe("SF-10:templates", () => {
  it("templates table and mapping profile commands", async () => {
    const searches: string[] = [];
    const commands: { readonly path: string; readonly key: string | null }[] = [];
    serve(searches);
    server.use(
      http.get(apiUrl("/api/v1/import-templates"), () =>
        HttpResponse.json({ items: [LEGACY_SKU_SSP, TEMPLATE], next_cursor: null }),
      ),
      http.get(apiUrl("/api/v1/import-mapping-profiles"), ({ request }) => {
        searches.push(new URL(request.url).search);
        return HttpResponse.json(
          { items: [draftProfile("DRAFT")], next_cursor: null },
          { headers: { "X-Erev-Total-Count": "1" } },
        );
      }),
      http.post(apiUrl("/api/v1/import-mapping-profiles/:profileId/test"), ({ request }) => {
        commands.push({
          path: new URL(request.url).pathname,
          key: request.headers.get("Idempotency-Key"),
        });
        return HttpResponse.json(draftProfile("TESTED"));
      }),
    );
    renderApp("/data/templates", { me: MAYA, screenRoutes: SCREEN_ROUTES });

    expect(await screen.findByRole("heading", { level: 1, name: "Import templates" })).toBeTruthy();
    const table = await screen.findByRole("table", { name: "Import templates" });
    expect(table.dataset.testid).toBe("SF-10-grid-templates");
    expect(within(table).getByRole("rowheader", { name: "Legacy v1: SKU SSP" })).toBeTruthy();
    expect(within(table).getByText("Legacy v1")).toBeTruthy();
    expect(within(table).getByRole("button", { name: "Download Legacy v1: SKU SSP" })).toBeTruthy();
    expect(within(table).getByRole("rowheader", { name: "Progress events (CSV v2)" })).toBeTruthy();

    const profiles = await screen.findByRole("grid", { name: "Mapping profiles" });
    expect(await within(profiles).findByRole("rowheader", { name: "NS-PROGRESS" })).toBeTruthy();
    expect(within(profiles).getByText("Progress events (CSV v2)")).toBeTruthy();
    expect(screen.getByRole("button", { name: "New mapping profile" })).toBeTruthy();
    expect(bindings(searches)).toContain("sort=code");

    fireEvent.click(within(profiles).getByRole("button", { name: "Actions for NS-PROGRESS" }));
    expect(screen.queryByRole("menuitem", { name: "Submit for approval" })).toBeNull();
    fireEvent.click(screen.getByRole("menuitem", { name: "Run tests" }));
    expect(await screen.findByText("Tests ran for NS-PROGRESS version 1.")).toBeTruthy();
    expect(commands).toHaveLength(1);
    expect(commands[0]?.path).toBe(
      "/api/v1/import-mapping-profiles/2e4f6a8b-1c3d-4e5f-8a9b-0c1d2e3f4a5b/test",
    );
    expect(commands[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
  });

  // SCREENS §0.7 SCR-ST-13, DG-FE-06 rev 1.228 (item KIT-UNPLACED-ERRORS-1): the drawer showed its
  // banner only while the problem carried no field errors at all, and the rows of its three editors
  // have no field of their own, so a profile refused for an alias was refused without a word.
  it("a refusal of New mapping profile says in the banner what no field of the drawer shows", async () => {
    serve([]);
    server.use(
      http.get(apiUrl("/api/v1/import-templates"), () =>
        HttpResponse.json({ items: [LEGACY_SKU_SSP, TEMPLATE], next_cursor: null }),
      ),
      http.get(apiUrl("/api/v1/import-mapping-profiles"), () =>
        HttpResponse.json(
          { items: [draftProfile("DRAFT")], next_cursor: null },
          { headers: { "X-Erev-Total-Count": "1" } },
        ),
      ),
      http.post(apiUrl("/api/v1/import-mapping-profiles"), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            {
              field: "code",
              sheet: null,
              row: null,
              rule_id: null,
              message: "Profile NS-PROGRESS already exists.",
            },
            {
              field: "mappings.aliases.SO Number",
              sheet: null,
              row: null,
              rule_id: null,
              message: "Template progress_events has no column contract_no.",
            },
          ],
        }),
      ),
    );
    renderApp("/data/templates", { me: MAYA, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(await screen.findByRole("button", { name: "New mapping profile" }));

    const dialog = await screen.findByRole("dialog", { name: "New mapping profile" });
    fireEvent.change(within(dialog).getByLabelText(/^Code/), { target: { value: "NS-PROGRESS" } });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), {
      target: { value: "NetSuite progress export" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save draft" }));

    const banner = await within(dialog).findByRole("alert");
    expect(
      within(banner).getByText("Template progress_events has no column contract_no."),
    ).toBeTruthy();
    expect(within(banner).queryByText("Profile NS-PROGRESS already exists.")).toBeNull();
    expect(within(dialog).getAllByText("Profile NS-PROGRESS already exists.")).toHaveLength(1);
    expect(within(dialog).getByLabelText(/^Code/).getAttribute("aria-invalid")).toBe("true");
  });
});
