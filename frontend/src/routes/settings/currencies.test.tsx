// @vitest-environment jsdom
// SF-15:currencies (BUILD_SPEC RFD-18; SCREENS_B §9.4): the table "Enabled currencies" and "Save
// currencies" (`PUT /tenant-currencies`); the region "FX rate sets" with the rate set select, version tabs
// and the rates grid "Rates" whose row header reads "EUR to USD 30 Sep 2026" with the value "1.120000"
// through the format module (DS-FMT-14); a draft rate is inline editable ("Enter a rate above 0.",
// `PATCH /fx-rate-set-versions/{id}` with `If-Match`) and "Submit for approval" posts the version.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import {
  type Currency,
  type FxRate,
  type FxRateSet,
  type FxRateSetVersion,
  type FxRateSetVersionDetail,
  latestApproved,
  ratePositive,
  rateRowKey,
  selectVersion,
  type TenantCurrency,
} from "../../lib/api/queries/currencies";
import type { Entity } from "../../lib/api/queries/tenant";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, server } from "../../test/msw";
import { describedBy, REFUSAL_REFERENCE, REFUSAL_TITLE, refusedWith } from "../../test/refusals";
import { ratePeriodLabel } from "./currencies";

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

const AUTHOR = signedInMe({ permissions: ["config.read", "config.author"] });
const MANAGER = signedInMe({ permissions: ["config.read", "settings.manage"] });

const TENANT_CURRENCIES: readonly TenantCurrency[] = (
  [
    ["USD", "US dollar", 2, true],
    ["GBP", "Pound sterling", 2, false],
    ["EUR", "Euro", 2, false],
    ["JPY", "Japanese yen", 0, false],
  ] as const
).map(([code, name, minorUnit, reporting]) => ({
  currency_code: code,
  name,
  minor_unit: minorUnit,
  is_enabled: true,
  is_reporting_currency: reporting,
  row_version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}));

const CATALOGUE: readonly Currency[] = [
  ...TENANT_CURRENCIES.map((row) => ({
    code: row.currency_code,
    name: row.name,
    minor_unit: row.minor_unit,
    numeric_code: "000",
    is_active: true,
  })),
  { code: "CHF", name: "Swiss franc", minor_unit: 2, numeric_code: "756", is_active: true },
];

function entity(code: string, currency: string): Entity {
  return {
    id: `${code.toLowerCase().replace("-", "0").padEnd(8, "0")}-0000-4000-8000-000000000000`,
    code,
    name: code,
    country_code: "US",
    functional_currency: currency,
    time_zone: "America/New_York",
    calendar_id: "ca1ca1ca-ca1c-4ca1-8ca1-ca1ca1ca1ca1",
    parent_entity_id: null,
    tax_id: null,
    is_active: true,
    row_version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    books: [],
  };
}
const ENTITIES = [
  entity("AVM-US", "USD"),
  entity("AVM-UK", "GBP"),
  entity("AVM-DE", "EUR"),
  entity("AVM-JP", "JPY"),
];

const CLOSING: FxRateSet = {
  id: "5e75e75e-5e75-4e75-8e75-5e75e75e75e7",
  code: "AVM-RATES-CLOSING",
  name: "Avenmoor closing rates",
  rate_type: "closing",
  source: "Manual",
  row_version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function version(
  id: string,
  versionNo: number,
  status: FxRateSetVersion["status"],
  from: string,
  to: string,
  rowVersion: number,
): FxRateSetVersion {
  return {
    id,
    fx_rate_set_id: CLOSING.id,
    fx_rate_set_code: CLOSING.code,
    version_no: versionNo,
    status,
    rate_type: "closing",
    coverage_from: from,
    coverage_to: to,
    rate_count: 3,
    content_sha256: null,
    import_upload_id: null,
    approval_request_id: status === "APPROVED" ? "a9a9a9a9-a9a9-4a9a-8a9a-a9a9a9a9a9a9" : null,
    pending_approval_request_id: null,
    published_at: null,
    published_by: null,
    created_by: null,
    row_version: rowVersion,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  };
}
const V9 = version(
  "09090909-0909-4909-8909-090909090909",
  9,
  "APPROVED",
  "2026-01-01",
  "2026-09-30",
  4,
);
const V10 = version(
  "10101010-1010-4010-8010-101010101010",
  10,
  "DRAFT",
  "2026-10-01",
  "2026-10-31",
  2,
);

function rate(
  id: string,
  base: string,
  value: string,
  effectiveDate: string,
  periodKey: string,
): FxRate {
  return {
    id,
    base_currency: base,
    quote_currency: "USD",
    effective_date: effectiveDate,
    period_id: null,
    period_key: periodKey,
    rate: value,
    rate_type: "closing",
    is_derived: false,
  };
}
const V9_RATES: readonly FxRate[] = [
  rate("0e0e0e0e-0e0e-4e0e-8e0e-0e0e0e0e0e0e", "EUR", "1.120000", "2026-09-30", "FY2026-P09"),
  rate("0f0f0f0f-0f0f-4f0f-8f0f-0f0f0f0f0f0f", "GBP", "1.290000", "2026-09-30", "FY2026-P09"),
  rate("0a0a0a0a-0a0a-4a0a-8a0a-0a0a0a0a0a0a", "JPY", "0.006950", "2026-09-30", "FY2026-P09"),
];
const V10_RATES: readonly FxRate[] = [
  rate("1e1e1e1e-1e1e-4e1e-8e1e-1e1e1e1e1e1e", "EUR", "1.130000", "2026-10-31", "FY2026-P10"),
  rate("1f1f1f1f-1f1f-4f1f-8f1f-1f1f1f1f1f1f", "GBP", "1.300000", "2026-10-31", "FY2026-P10"),
  rate("1a1a1a1a-1a1a-4a1a-8a1a-1a1a1a1a1a1a", "JPY", "0.007000", "2026-10-31", "FY2026-P10"),
];

function detail(base: FxRateSetVersion, rates: readonly FxRate[]): FxRateSetVersionDetail {
  return { ...base, rates: [...rates] };
}

function serve(sets: readonly FxRateSet[], versions: readonly FxRateSetVersion[]) {
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/books"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/periods"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/saved-views"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), () =>
      HttpResponse.json({ items: ENTITIES, next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/currencies"), () =>
      HttpResponse.json({ items: CATALOGUE, next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/tenant-currencies"), () =>
      HttpResponse.json({ items: TENANT_CURRENCIES, next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/fx-rate-sets"), () =>
      HttpResponse.json({ items: sets, next_cursor: null }),
    ),
    http.get(apiUrl(`/api/v1/fx-rate-sets/${CLOSING.id}/versions`), () =>
      HttpResponse.json({ items: [...versions].reverse(), next_cursor: null }),
    ),
    http.get(apiUrl(`/api/v1/fx-rate-set-versions/${V9.id}`), () =>
      HttpResponse.json(detail(V9, V9_RATES)),
    ),
    http.get(apiUrl(`/api/v1/fx-rate-set-versions/${V10.id}`), () =>
      HttpResponse.json(detail(V10, V10_RATES)),
    ),
  );
}

describe("SF-15:currencies", () => {
  it("rates grid row header", async () => {
    serve([CLOSING], [V9, V10]);
    renderApp("/settings/currencies?rate_set=AVM-RATES-CLOSING&version=9", {
      me: AUTHOR,
      screenRoutes: SCREEN_ROUTES,
    });

    const table = await screen.findByRole("table", { name: "Enabled currencies" });
    expect(table.getAttribute("data-testid")).toBe("SF-15-grid-currencies");
    expect(
      within(table)
        .getAllByRole("rowheader")
        .map((cell) => cell.textContent),
    ).toEqual(["EUR", "GBP", "JPY", "USD"]);
    expect(within(screen.getByTestId("SF-15-currency-USD")).getByText("AVM-US")).toBeTruthy();
    expect(within(screen.getByTestId("SF-15-currency-JPY")).getByText("0")).toBeTruthy();
    // An author without settings.manage sees the table read-only.
    expect(screen.queryByRole("button", { name: "Save currencies" })).toBeNull();

    const region = screen.getByRole("region", { name: "FX rate sets (1)" });
    expect(region.getAttribute("data-testid")).toBe("SF-15-rate-sets");
    expect(
      await within(region).findByText("Latest approved v9 · coverage 01 Jan 2026 – 30 Sep 2026"),
    ).toBeTruthy();
    const tabs = await within(region).findByRole("tablist", { name: "Versions" });
    expect(
      within(tabs).getByRole("tab", { name: "v9 (Approved)" }).getAttribute("aria-selected"),
    ).toBe("true");
    expect(within(tabs).getByRole("tab", { name: "v10 (Draft)" })).toBeTruthy();
    expect(
      within(region).getByText("This version is no longer a draft, so it is read-only."),
    ).toBeTruthy();

    const grid = await within(await screen.findByTestId("SF-15-grid-rates")).findByRole("grid", {
      name: "Rates",
    });
    const row = await within(grid).findByTestId("SF-15-row-eur-usd-fy2026-p09");
    expect(within(row).getByRole("rowheader").textContent).toBe("EUR to USD 30 Sep 2026");
    expect(within(row).getByText("1.120000")).toBeTruthy();
    expect(within(row).getByText("Sep 2026")).toBeTruthy();
    expect(within(row).getByText("No")).toBeTruthy();
    const headers = within(grid)
      .getAllByRole("columnheader")
      .map((header) => header.textContent?.trim() ?? "");
    for (const name of [
      "Base",
      "Quote",
      "Effective date",
      "Period",
      "Rate (base to quote)",
      "Derived",
    ]) {
      expect(headers.some((header) => header.startsWith(name))).toBe(true);
    }
    // An approved version has no editor and no submit action (the grid edits the active cell).
    const approvedCell = row.querySelector('[data-column="rate"]') as HTMLElement;
    fireEvent.mouseDown(approvedCell);
    fireEvent.keyDown(approvedCell, { key: "F2" });
    expect(screen.queryByRole("textbox", { name: "Rate (base to quote)" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Submit for approval" })).toBeNull();

    expect(rateRowKey(V9_RATES[0] as FxRate)).toBe("EUR-USD-FY2026-P09");
    expect(ratePeriodLabel({ period_key: "FY2026-P09", effective_date: "2026-09-30" })).toBe(
      "Sep 2026",
    );
    expect(ratePeriodLabel({ period_key: "FY2026-P09", effective_date: "2026-09-15" })).toBe(
      "FY2026 P09",
    );
    expect(ratePeriodLabel({ period_key: null, effective_date: "2026-09-15" })).toBe("—");
    expect(latestApproved([V10, V9])?.version_no).toBe(9);
    expect(selectVersion([V10, V9], null)?.version_no).toBe(10);
  });

  it("a draft rate is inline editable with Enter a rate above 0. and patches the version; Submit for approval posts", async () => {
    const patches: { readonly ifMatch: string | null; readonly body: unknown }[] = [];
    const submits: string[] = [];
    serve([CLOSING], [V9, V10]);
    server.use(
      http.patch(apiUrl(`/api/v1/fx-rate-set-versions/${V10.id}`), async ({ request }) => {
        patches.push({ ifMatch: request.headers.get("If-Match"), body: await request.json() });
        return HttpResponse.json(detail({ ...V10, row_version: 3 }, V10_RATES));
      }),
      http.post(apiUrl(`/api/v1/fx-rate-set-versions/${V10.id}/submit`), ({ request }) => {
        submits.push(request.headers.get("Idempotency-Key") ?? "");
        return HttpResponse.json({ ...V10, status: "SUBMITTED", row_version: 4 });
      }),
    );
    renderApp("/settings/currencies?rate_set=AVM-RATES-CLOSING&version=10", {
      me: AUTHOR,
      screenRoutes: SCREEN_ROUTES,
    });

    const grid = await within(await screen.findByTestId("SF-15-grid-rates")).findByRole("grid", {
      name: "Rates",
    });
    const row = await within(grid).findByTestId("SF-15-row-eur-usd-fy2026-p10");
    const cell = row.querySelector('[data-column="rate"]') as HTMLElement;
    // The grid edits the active cell (mousedown selects it); the rate column becomes editable once
    // the draft detail with its row version has loaded, so the editor is awaited.
    const editor = await waitFor(() => {
      fireEvent.mouseDown(cell);
      fireEvent.keyDown(cell, { key: "F2" });
      return screen.getByRole("textbox", { name: "Rate (base to quote)" });
    });
    fireEvent.change(editor, { target: { value: "0" } });
    fireEvent.keyDown(editor, { key: "Enter" });
    await waitFor(() => expect(cell.getAttribute("aria-invalid")).toBe("true"));
    expect(document.getElementById(cell.getAttribute("aria-describedby") ?? "")?.textContent).toBe(
      "Enter a rate above 0.",
    );
    expect(patches).toEqual([]);

    fireEvent.mouseDown(cell);
    fireEvent.keyDown(cell, { key: "F2" });
    const again = screen.getByRole("textbox", { name: "Rate (base to quote)" });
    fireEvent.change(again, { target: { value: "1.125" } });
    fireEvent.keyDown(again, { key: "Enter" });
    await waitFor(() => expect(patches).toHaveLength(1));
    expect(patches[0]?.ifMatch).toBe('"r2"');
    expect(patches[0]?.body).toEqual({
      rates: [
        {
          base_currency: "EUR",
          quote_currency: "USD",
          effective_date: "2026-10-31",
          period_key: "FY2026-P10",
          rate: "1.125",
        },
        {
          base_currency: "GBP",
          quote_currency: "USD",
          effective_date: "2026-10-31",
          period_key: "FY2026-P10",
          rate: "1.300000",
        },
        {
          base_currency: "JPY",
          quote_currency: "USD",
          effective_date: "2026-10-31",
          period_key: "FY2026-P10",
          rate: "0.007000",
        },
      ],
    });
    expect(ratePositive("0")).toBe(false);
    expect(ratePositive("1.125")).toBe(true);
    expect(ratePositive("-1")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Submit AVM-RATES-CLOSING v10 with 3 rates for approval?",
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Submit for approval" }));
    expect(await screen.findByText("Submitted AVM-RATES-CLOSING v10 for approval.")).toBeTruthy();
    expect(submits).toHaveLength(1);
  });

  // DG-FE-05 rev 1.156 (item W-23): a cell save is a command outside the hook; its key is the pane's.
  it("a rate save that gets no answer says so in the cell, and the same rate saved again carries the same key", async () => {
    const keys: (string | null)[] = [];
    serve([CLOSING], [V9, V10]);
    server.use(
      http.patch(apiUrl(`/api/v1/fx-rate-set-versions/${V10.id}`), ({ request }) => {
        keys.push(request.headers.get("Idempotency-Key"));
        return keys.length === 1
          ? HttpResponse.error()
          : HttpResponse.json(detail({ ...V10, row_version: 3 }, V10_RATES));
      }),
    );
    renderApp("/settings/currencies?rate_set=AVM-RATES-CLOSING&version=10", {
      me: AUTHOR,
      screenRoutes: SCREEN_ROUTES,
    });

    const grid = await within(await screen.findByTestId("SF-15-grid-rates")).findByRole("grid", {
      name: "Rates",
    });
    const row = await within(grid).findByTestId("SF-15-row-eur-usd-fy2026-p10");
    const cell = row.querySelector('[data-column="rate"]') as HTMLElement;
    const save = async () => {
      const editor = await waitFor(() => {
        fireEvent.mouseDown(cell);
        fireEvent.keyDown(cell, { key: "F2" });
        return screen.getByRole("textbox", { name: "Rate (base to quote)" });
      });
      fireEvent.change(editor, { target: { value: "1.125" } });
      fireEvent.keyDown(editor, { key: "Enter" });
    };

    await save();
    await waitFor(() => expect(cell.getAttribute("aria-invalid")).toBe("true"));
    expect(document.getElementById(cell.getAttribute("aria-describedby") ?? "")?.textContent).toBe(
      "No answer came back from the server. Try again.",
    );
    expect(keys).toHaveLength(1);

    await save();
    await waitFor(() => expect(keys).toHaveLength(2));
    expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/);
    expect(keys[1]).toBe(keys[0]);
  });

  it("the empty state reads No FX rate sets and New rate set posts the set", async () => {
    const bodies: unknown[] = [];
    serve([], []);
    server.use(
      http.post(apiUrl("/api/v1/fx-rate-sets"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(
          {
            ...CLOSING,
            id: "5a5a5a5a-5a5a-4a5a-8a5a-5a5a5a5a5a5a",
            code: "AVM-RATES-SPOT",
            rate_type: "spot",
          },
          { status: 201 },
        );
      }),
    );
    renderApp("/settings/currencies", { me: AUTHOR, screenRoutes: SCREEN_ROUTES });

    const empty = await screen.findByTestId("SF-15-empty-rate-sets");
    expect(within(empty).getByRole("heading", { name: "No FX rate sets" })).toBeTruthy();
    expect(
      within(empty).getByText(
        "Rate sets hold spot, closing and average rates. Each version is approved before it is used.",
      ),
    ).toBeTruthy();
    fireEvent.click(within(empty).getByRole("button", { name: "New rate set" }));

    const dialog = await screen.findByRole("dialog", { name: "New rate set" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create rate set" }));
    expect(await within(dialog).findByText("Enter the rate set code.")).toBeTruthy();
    expect(within(dialog).getByText("Choose the rate type.")).toBeTruthy();
    fireEvent.change(within(dialog).getByLabelText(/^Code/), {
      target: { value: "AVM-RATES-SPOT" },
    });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), {
      target: { value: "Avenmoor spot rates" },
    });
    fireEvent.click(within(dialog).getByRole("combobox", { name: /^Rate type/ }));
    fireEvent.mouseDown(await screen.findByRole("option", { name: "spot" }));
    fireEvent.change(within(dialog).getByLabelText(/^Source/), { target: { value: "Manual" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create rate set" }));

    expect(await screen.findByText("Created rate set AVM-RATES-SPOT.")).toBeTruthy();
    expect(bodies).toEqual([
      { code: "AVM-RATES-SPOT", name: "Avenmoor spot rates", rate_type: "spot", source: "Manual" },
    ]);
  });

  it("Save currencies puts the enabled codes; the reporting currency and used currencies stay enabled", async () => {
    const bodies: unknown[] = [];
    serve([CLOSING], [V9]);
    server.use(
      http.put(apiUrl("/api/v1/tenant-currencies"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ items: TENANT_CURRENCIES, next_cursor: null });
      }),
    );
    renderApp("/settings/currencies", { me: MANAGER, screenRoutes: SCREEN_ROUTES });

    await screen.findByRole("table", { name: "Enabled currencies" });
    expect(
      (screen.getByRole("checkbox", { name: "Enable USD" }) as HTMLInputElement).disabled,
    ).toBe(true);
    // EUR is the functional currency of AVM-DE.
    await within(screen.getByTestId("SF-15-currency-EUR")).findByText("AVM-DE");
    expect(
      (screen.getByRole("checkbox", { name: "Enable EUR" }) as HTMLInputElement).disabled,
    ).toBe(true);
    const save = screen.getByRole("button", { name: "Save currencies" });
    expect(save.getAttribute("aria-disabled")).toBe("true");

    const add = screen.getByRole("combobox", { name: "Add currency" });
    fireEvent.change(add, { target: { value: "CHF" } });
    fireEvent.mouseDown(await screen.findByRole("option", { name: "CHF · Swiss franc" }));
    expect(
      ((await screen.findByRole("checkbox", { name: "Enable CHF" })) as HTMLInputElement).checked,
    ).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Save currencies" }));

    expect(await screen.findByText("Saved the enabled currencies.")).toBeTruthy();
    expect(bodies).toEqual([{ currency_codes: ["CHF", "EUR", "GBP", "JPY", "USD"] }]);
  });

  // W-12e: `PUT /tenant-currencies` is an act on the whole workspace. A holder of settings.manage for
  // one entity was offered "Save currencies" and the API refused the command.
  it("settings.manage for one entity alone: the currencies are read and Save currencies is not offered", async () => {
    serve([CLOSING], [V9]);
    renderApp("/settings/currencies", {
      me: signedInMe({
        permissions: ["config.read", "settings.manage"],
        permission_scopes: {
          "config.read": "*",
          "settings.manage": ["0a1b2c3d-4e5f-4a6b-8c7d-0000000000de"],
        },
      }),
      screenRoutes: SCREEN_ROUTES,
    });

    await screen.findByRole("table", { name: "Enabled currencies" });
    await within(screen.getByTestId("SF-15-currency-EUR")).findByText("AVM-DE");
    expect(screen.queryByRole("button", { name: "Save currencies" })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "Add currency" })).toBeNull();
  });
});

// docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): a message that names a member no
// field shows was shown nowhere. The banner lists it, and what a field shows is not said again. Where
// two members share one place for a message, the place shows the first and the banner the other.
describe("SF-15:currencies, a refused command", () => {
  it("New rate set: the banner lists what no field shows and leaves the code's message at its field", async () => {
    const noField = "A workspace holds at most 20 rate sets.";
    const atCode = "A rate set with this code exists.";
    serve([], []);
    server.use(
      http.post(apiUrl("/api/v1/fx-rate-sets"), () =>
        refusedWith({ tenant_id: noField, code: atCode }),
      ),
    );
    renderApp("/settings/currencies", { me: AUTHOR, screenRoutes: SCREEN_ROUTES });
    const empty = await screen.findByTestId("SF-15-empty-rate-sets");
    fireEvent.click(within(empty).getByRole("button", { name: "New rate set" }));
    const dialog = await screen.findByRole("dialog", { name: "New rate set" });
    const code = within(dialog).getByLabelText(/^Code/);
    fireEvent.change(code, { target: { value: "AVM-RATES-SPOT" } });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), {
      target: { value: "Avenmoor spot rates" },
    });
    fireEvent.click(within(dialog).getByRole("combobox", { name: /^Rate type/ }));
    fireEvent.mouseDown(await screen.findByRole("option", { name: "spot" }));
    fireEvent.change(within(dialog).getByLabelText(/^Source/), { target: { value: "Manual" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create rate set" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + noField + REFUSAL_REFERENCE);
    expect(describedBy(code)).toContain(atCode);
  });

  it("New version: the place of the two dates shows the first message and the banner the second", async () => {
    const atFrom = "Coverage starts after the last approved version ends.";
    const atTo = "Coverage ends within an open period.";
    serve([CLOSING], [V9]);
    server.use(
      http.post(apiUrl(`/api/v1/fx-rate-sets/${CLOSING.id}/versions`), () =>
        refusedWith({ coverage_from: atFrom, coverage_to: atTo }),
      ),
    );
    renderApp("/settings/currencies?rate_set=AVM-RATES-CLOSING", {
      me: AUTHOR,
      screenRoutes: SCREEN_ROUTES,
    });
    fireEvent.click(
      (await screen.findAllByRole("button", { name: "New version" }))[0] as HTMLElement,
    );
    const dialog = await screen.findByRole("dialog", { name: "New version" });
    const from = within(dialog).getByLabelText(/^Coverage from/);
    fireEvent.change(from, { target: { value: "2026-10-01" } });
    fireEvent.blur(from);
    const to = within(dialog).getByLabelText(/^Coverage to/);
    fireEvent.change(to, { target: { value: "2026-10-31" } });
    fireEvent.blur(to);
    fireEvent.click(within(dialog).getByRole("button", { name: "Create version" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + atTo + REFUSAL_REFERENCE);
    expect(describedBy(from)).toContain(atFrom);
  });

  it("Save currencies: the form has no field for a message, so the banner says every sentence", async () => {
    const sentence = "CHF has no approved rate for the open periods.";
    serve([CLOSING], [V9]);
    server.use(
      http.put(apiUrl("/api/v1/tenant-currencies"), () =>
        refusedWith({ "currency_codes.0": sentence }),
      ),
    );
    renderApp("/settings/currencies", { me: MANAGER, screenRoutes: SCREEN_ROUTES });
    await screen.findByRole("table", { name: "Enabled currencies" });
    const add = screen.getByRole("combobox", { name: "Add currency" });
    fireEvent.change(add, { target: { value: "CHF" } });
    fireEvent.mouseDown(await screen.findByRole("option", { name: "CHF · Swiss franc" }));
    await screen.findByRole("checkbox", { name: "Enable CHF" });
    fireEvent.click(screen.getByRole("button", { name: "Save currencies" }));

    const heading = await screen.findByRole("heading", { name: REFUSAL_TITLE });
    expect(heading.closest('[role="alert"]')?.textContent).toBe(
      REFUSAL_TITLE + sentence + REFUSAL_REFERENCE,
    );
  });
});
