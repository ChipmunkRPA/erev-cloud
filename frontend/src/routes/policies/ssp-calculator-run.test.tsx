// @vitest-environment jsdom
// SF-13:ssp-calculator-run (BUILD_SPEC RFD-24; SCREENS §11.5 figures per product, statistics,
// distribution and observations; 04 API-R-27, §16.14; docs/dev-guide.md DG-FE-08): the figures strip
// renders the API's strings without converting money to numbers, and the band label trims its ratio.
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import {
  ratioPercentFigures,
  type SspCalculatorResult,
  type SspCalculatorRun,
} from "../../lib/api/queries/ssp-calculator";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

const RUN_ID = "6a7b8c9d-0e1f-4a2b-8c3d-4e5f6a7b8c9d";
const BOOK_ID = "1b2c3d4e-5f60-4a71-8b92-a3b4c5d6e7f8";
const POOL_ID = "7b8c9d0e-1f2a-4b3c-9d4e-5f6a7b8c9d0e";

const ANALYST = signedInMe({ permissions: ["ssp.read", "ssp.create"] });

function run(): SspCalculatorRun {
  return {
    id: RUN_ID,
    name: "AVM-PLAT-100 standalone sales 2026",
    parameters: {
      source: "source_order_lines",
      product_ids: ["8c9d0e1f-2a3b-4c4d-8e5f-6a7b8c9d0e1f"],
      dimensions: {},
      date_from: "2026-01-01",
      date_to: "2026-08-31",
      band_ratio: "0.150000",
      currency: "USD",
      ssp_book_id: BOOK_ID,
      pool_file_id: POOL_ID,
    },
    status: "SUCCEEDED",
    observation_count: 40,
    result_file_id: null,
    draft_ssp_book_version_id: null,
    job_id: null,
    started_at: "2026-09-10T09:00:00Z",
    finished_at: "2026-09-10T09:00:05Z",
    created_by: {
      id: "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a",
      display_name: "Maya Chen",
      kind: "USER",
    },
    created_at: "2026-09-10T08:59:58Z",
  };
}

function result(overrides: Partial<SspCalculatorResult>): SspCalculatorResult {
  return {
    id: "9d0e1f2a-3b4c-4d5e-8f6a-7b8c9d0e1f2a",
    ssp_calculator_run_id: RUN_ID,
    product_id: "8c9d0e1f-2a3b-4c4d-8e5f-6a7b8c9d0e1f",
    product_code: "AVM-PLAT-100",
    stratification: "",
    dimension_key: {},
    currency: "USD",
    observation_count: 40,
    excluded_count: 0,
    median_unit_price: "112000.00",
    mean_unit_price: "112000.00",
    p10_unit_price: "80800.00",
    p25_unit_price: "92500.00",
    p75_unit_price: "131500.00",
    p90_unit_price: "143200.00",
    band_ratio: "0.150000",
    compliance_ratio: "0.400000",
    inside_count: 16,
    proposed_low: "95200.00",
    proposed_mid: "112000.00",
    proposed_high: "128800.00",
    histogram: [
      { from: "73000.00", to: "80800.00", count: 4 },
      { from: "80800.00", to: "88600.00", count: 4 },
      { from: "88600.00", to: "151000.00", count: 32 },
    ],
    ...overrides,
  };
}

function serve(results: readonly SspCalculatorResult[]) {
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/books"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/currencies"), () =>
      HttpResponse.json({
        items: [
          { code: "USD", name: "US dollar", minor_unit: 2, numeric_code: "840", is_active: true },
        ],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/ssp-calculator-runs/:runId"), () => HttpResponse.json(run())),
    http.get(apiUrl("/api/v1/ssp-calculator-runs/:runId/results"), () =>
      HttpResponse.json({ items: results, next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/ssp-calculator-runs/:runId/observations"), () =>
      HttpResponse.json(
        {
          items: [
            {
              date: "2026-01-03",
              source_reference: "SO-AVM-2026-0001",
              product_code: "AVM-PLAT-100",
              customer: null,
              quantity: "1",
              unit_price: "73000.00",
              in_band: false,
              exclusion_reason: null,
            },
          ],
          next_cursor: null,
        },
        { headers: { "X-Erev-Total-Count": "40" } },
      ),
    ),
    http.get(apiUrl("/api/v1/ssp-books/:bookId"), () =>
      HttpResponse.json({
        id: BOOK_ID,
        code: "US-LIST",
        name: "US list prices",
        description: null,
        entity_code: null,
        currency: "USD",
        channel: null,
        segment: null,
        resolution_mode: "EFFECTIVE_DATE",
        current_version: null,
        draft_version_id: null,
        row_version: 1,
        created_at: "2026-01-01T09:00:00Z",
        updated_at: "2026-01-01T09:00:00Z",
      }),
    ),
    http.get(apiUrl("/api/v1/files/:fileId"), () =>
      HttpResponse.json({
        id: POOL_ID,
        purpose: "IMPORT_SOURCE",
        media_type: "text/csv",
        original_filename: "avm-plat-100-standalone-sales-2026.csv",
        size_bytes: 1834,
        sha256: "0".repeat(64),
        legal_hold: false,
        retention_until: null,
        shredded_at: null,
        shred_completed_at: null,
        created_at: "2026-09-10T08:59:50Z",
        created_by: null,
        created_by_kind: "USER",
      }),
    ),
  );
}

/** The `dd` text of the figure whose `dt` reads `label`. */
function figure(strip: HTMLElement, label: string): string {
  const term = within(strip).getByText(label, { selector: "dt" });
  return term.nextElementSibling?.textContent ?? "";
}

describe("SF-13:ssp-calculator-run", () => {
  it("figures strip uses api values", async () => {
    // A second product whose median is past 2^53: a JavaScript number would print ...992.00.
    serve([
      result({}),
      result({
        id: "0e1f2a3b-4c5d-4e6f-9a7b-8c9d0e1f2a3b",
        product_code: "AVM-BIG",
        observation_count: 3,
        excluded_count: 1,
        median_unit_price: "9007199254740993.01",
        compliance_ratio: "0.333333",
        inside_count: 1,
        band_ratio: "0.125000",
      }),
    ]);
    renderApp(`/policies/ssp-calculator/runs/${RUN_ID}`, {
      me: ANALYST,
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("heading", { level: 1, name: "AVM-PLAT-100 standalone sales 2026" }),
    ).toBeTruthy();
    const strips = await screen.findAllByTestId("SF-13-kpi-strip");
    expect(strips).toHaveLength(2);
    const [platform, big] = strips;
    if (platform === undefined || big === undefined) {
      throw new Error("no figures strip");
    }
    // PRD WLD-X-24: 40 observations, median 112,000.00, 16 inside ±15% (40.0%).
    expect(figure(platform, "Observations")).toBe("40");
    expect(figure(platform, "Excluded")).toBe("0");
    expect(figure(platform, "Median (USD)")).toBe("112,000.00");
    expect(figure(platform, "Inside ±15%")).toBe("40.0%16 of 40");
    expect(figure(big, "Median (USD)")).toBe("9,007,199,254,740,993.01");
    expect(figure(big, "Inside ±12.5%")).toBe("33.3%1 of 3");
    expect(figure(big, "Excluded")).toBe("1");

    // The header parameters and the distribution figure (SCREENS §11.5 test hooks).
    expect(await screen.findByText("avm-plat-100-standalone-sales-2026.csv")).toBeTruthy();
    const charts = screen.getAllByTestId("SF-13-chart-distribution");
    expect(
      within(charts[0] ?? document.body).getByRole("figure", { name: /^Distribution/ }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Create draft version from results" })).toBeTruthy();
    const observations = within(await screen.findByTestId("SF-13-grid-observations")).getByRole(
      "grid",
      { name: "Observations" },
    );
    expect(
      await within(observations).findByRole("button", {
        name: "Exclude observation SO-AVM-2026-0001",
      }),
    ).toBeTruthy();
  });

  // docs/dev-guide.md DG-FE-06 rev 1.228 (item KIT-UNPLACED-ERRORS-1; lane QA-BE's browser look): the
  // draft of a version from a study was refused on a member the dialog has no field for, and the dialog
  // stayed open with no message at all. The banner says what no field shows.
  it("a refusal of Create draft version says in the banner what no field of the dialog shows", async () => {
    serve([result({})]);
    server.use(
      http.post(apiUrl(`/api/v1/ssp-calculator-runs/${RUN_ID}/create-draft-version`), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            {
              field: "version_label",
              sheet: null,
              row: null,
              rule_id: null,
              message: "The book already has a version with this label.",
            },
            {
              field: "value_basis",
              sheet: null,
              row: null,
              rule_id: null,
              message: "AVM-PLAT-100 is a series product: its entry is a rate for one month.",
            },
          ],
        }),
      ),
    );
    renderApp(`/policies/ssp-calculator/runs/${RUN_ID}`, {
      me: ANALYST,
      screenRoutes: SCREEN_ROUTES,
    });
    fireEvent.click(
      await screen.findByRole("button", { name: "Create draft version from results" }),
    );
    const dialog = await screen.findByRole("dialog", { name: "Create draft version" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Version label/ }), {
      target: { value: "2026-H2" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create draft version" }));

    const banner = await within(dialog).findByRole("alert");
    expect(
      within(banner).getByText(
        "AVM-PLAT-100 is a series product: its entry is a rate for one month.",
      ),
    ).toBeTruthy();
    expect(
      within(dialog).getAllByText("The book already has a version with this label."),
    ).toHaveLength(1);
    expect(
      within(banner).queryByText("The book already has a version with this label."),
    ).toBeNull();
  });

  it("a refusal of Exclude says in the banner what the reason field does not show", async () => {
    serve([result({})]);
    server.use(
      http.post(apiUrl(`/api/v1/ssp-calculator-runs/${RUN_ID}/exclusions`), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            {
              field: "reason",
              sheet: null,
              row: null,
              rule_id: null,
              message: "Say why the observation is not a standalone sale.",
            },
            {
              field: "source_reference",
              sheet: null,
              row: null,
              rule_id: null,
              message: "SO-AVM-2026-0001 is excluded already.",
            },
          ],
        }),
      ),
    );
    renderApp(`/policies/ssp-calculator/runs/${RUN_ID}`, {
      me: ANALYST,
      screenRoutes: SCREEN_ROUTES,
    });
    fireEvent.click(
      await screen.findByRole("button", { name: "Exclude observation SO-AVM-2026-0001" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Exclude observation SO-AVM-2026-0001",
    });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Reason/ }), {
      target: { value: "A bundle sale, not standalone." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Exclude" }));

    const banner = await within(dialog).findByRole("alert");
    expect(within(banner).getByText("SO-AVM-2026-0001 is excluded already.")).toBeTruthy();
    expect(
      within(dialog).getAllByText("Say why the observation is not a standalone sale."),
    ).toHaveLength(1);
  });

  it("the band ratio reads as trimmed percent figures", () => {
    expect(ratioPercentFigures("0.150000")).toBe("15");
    expect(ratioPercentFigures("0.125000")).toBe("12.5");
    expect(ratioPercentFigures("1.000000")).toBe("100");
  });
});
