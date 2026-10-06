// @vitest-environment jsdom
// SF-13:ssp-book-version (BUILD_SPEC RFD-24; SCREENS §11.0 commands, §11.4 submission, entries grid and
// test hooks; 04 API-R-26): a refused submission without a study renders ERR-10; an approved version is
// read-only and "New draft version" copies it; the diff rows, the landing version and the percent
// conversions of the entry form.
import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import {
  diffRows,
  landingVersionId,
  percentTextToRatio,
  ratioToPercentText,
  type SspBook,
  type SspBookVersion,
  type SspEntry,
} from "../../lib/api/queries/ssp-books";
import type { Product } from "../../lib/api/queries/ssp-calculator";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

const BOOK_ID = "1b2c3d4e-5f60-4a71-8b92-a3b4c5d6e7f8";
const DRAFT_ID = "2c3d4e5f-6071-4b82-9ca3-b4c5d6e7f809";
const APPROVED_ID = "3d4e5f60-7182-4c93-8db4-c5d6e7f8091a";
const NEW_DRAFT_ID = "4e5f6071-8293-4da4-9ec5-d6e7f8091a2b";
const ENTRY_ID = "5f607182-93a4-4eb5-8fd6-e7f8091a2b3c";
const USER_ID = "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a";

const ANALYST = signedInMe({ permissions: ["ssp.read", "ssp.create"] });

function book(overrides: Partial<SspBook> = {}): SspBook {
  return {
    id: BOOK_ID,
    code: "US-LIST",
    name: "US list prices",
    description: null,
    entity_code: null,
    currency: "USD",
    channel: null,
    segment: null,
    resolution_mode: "EFFECTIVE_DATE",
    current_version: {
      id: APPROVED_ID,
      version_no: 1,
      legacy_version_label: "2026-H1",
      effective_from_date: "2026-01-01",
      effective_to_date: null,
    },
    draft_version_id: DRAFT_ID,
    row_version: 1,
    created_at: "2026-01-01T09:00:00Z",
    updated_at: "2026-09-01T09:00:00Z",
    ...overrides,
  };
}

function version(overrides: Partial<SspBookVersion> = {}): SspBookVersion {
  return {
    id: DRAFT_ID,
    ssp_book_id: BOOK_ID,
    version_no: 2,
    status: "DRAFT",
    legacy_version_label: "2026-H2",
    effective_from_date: "2026-10-01",
    effective_to_date: null,
    methodology_label: "Observable standalone sales, Jan-Aug 2026",
    is_methodology_change: false,
    entry_count: 1,
    diff_summary: null,
    ssp_calculator_run_id: null,
    study_attachment_ids: [],
    approval_request_id: null,
    content_sha256: null,
    published_at: null,
    created_by: { id: USER_ID, display_name: "Maya Chen", kind: "USER" },
    created_at: "2026-09-01T09:00:00Z",
    updated_at: "2026-09-02T09:30:00Z",
    row_version: 4,
    ...overrides,
  };
}

function entry(
  low: string,
  mid: string,
  high: string,
  overrides: Partial<SspEntry> = {},
): SspEntry {
  return {
    id: ENTRY_ID,
    product_code: "AVM-PLAT-100",
    stratification: "",
    region: null,
    channel: null,
    segment: null,
    deal_size_band: null,
    term_band: null,
    currency: "USD",
    method: "observable",
    value_basis: "AMOUNT",
    quantity_unit: null,
    unit_list_price: null,
    midpoint_discount_ratio: null,
    range_ratio: null,
    cost_basis: null,
    margin_ratio: null,
    observable_point: null,
    revenue_account_code: null,
    distinctness: "distinct",
    ranges: [
      {
        band_dimension: "NONE",
        band_from: null,
        band_to: null,
        point_value: null,
        low_value: low,
        mid_value: mid,
        high_value: high,
      },
    ],
    ...overrides,
  };
}

const H1_ENTRY = entry("85000.00", "100000.00", "115000.00");
const H2_ENTRY = entry("95200.00", "112000.00", "128800.00");

interface Recorded {
  readonly path: string;
  readonly ifMatch: string | null;
  readonly body: unknown;
}

function serve(current: SspBookVersion, served: SspBook, recorded: Recorded[] = []) {
  const approved = version({
    id: APPROVED_ID,
    version_no: 1,
    status: "APPROVED",
    legacy_version_label: "2026-H1",
    effective_from_date: "2026-01-01",
    methodology_label: "List-price study",
    published_at: "2026-01-02T10:00:00Z",
  });
  const versions = current.id === APPROVED_ID ? [approved] : [current, approved];
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
    http.get(apiUrl("/api/v1/ssp-books/:bookId"), () => HttpResponse.json(served)),
    http.get(apiUrl("/api/v1/ssp-books/:bookId/versions"), () =>
      HttpResponse.json({ items: versions, next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/ssp-book-versions/:versionId"), ({ params }) =>
      HttpResponse.json(
        params.versionId === NEW_DRAFT_ID
          ? version({ id: NEW_DRAFT_ID, version_no: 2, legacy_version_label: null })
          : current,
      ),
    ),
    http.get(apiUrl("/api/v1/ssp-book-versions/:versionId/entries"), ({ params }) =>
      HttpResponse.json(
        { items: [params.versionId === APPROVED_ID ? H1_ENTRY : H2_ENTRY], next_cursor: null },
        { headers: { "X-Erev-Total-Count": "1" } },
      ),
    ),
    http.get(apiUrl("/api/v1/ssp-book-versions/:versionId/diff"), () =>
      HttpResponse.json({
        added: [],
        removed: [],
        changed: [
          {
            key: {
              product_code: "AVM-PLAT-100",
              stratification: "",
              region: null,
              channel: null,
              segment: null,
              deal_size_band: null,
              term_band: null,
              currency: "USD",
            },
            before: H1_ENTRY,
            after: H2_ENTRY,
            mid_change_ratio: "0.120000",
          },
        ],
      }),
    ),
    http.get(apiUrl("/api/v1/attachments"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.post(apiUrl("/api/v1/ssp-book-versions/:versionId/submit"), async ({ request }) => {
      recorded.push({
        path: new URL(request.url).pathname,
        ifMatch: request.headers.get("If-Match"),
        body: await request.json(),
      });
      return HttpResponse.json(
        {
          type: "https://erev.dev/problems/ssp-study-required",
          title: "SSP study required",
          status: 422,
          detail: "Attach an SSP study and a methodology label before you submit.",
          instance: "urn:erev:request:7d6c5b4a-3928-4716-9504-a3b2c1d0e9f8",
        },
        { status: 422, headers: { "Content-Type": "application/problem+json" } },
      );
    }),
    http.post(apiUrl("/api/v1/ssp-books/:bookId/versions"), async ({ request }) => {
      recorded.push({
        path: new URL(request.url).pathname,
        ifMatch: request.headers.get("If-Match"),
        body: await request.json(),
      });
      return HttpResponse.json(version({ id: NEW_DRAFT_ID, legacy_version_label: null }), {
        status: 201,
      });
    }),
  );
}

function renderVersion(versionId: string) {
  return renderApp(`/policies/ssp-books/${BOOK_ID}/versions/${versionId}`, {
    me: ANALYST,
    screenRoutes: SCREEN_ROUTES,
  });
}

describe("SF-13:ssp-book-version", () => {
  it("submit without study shows err-10", async () => {
    const recorded: Recorded[] = [];
    serve(version(), book(), recorded);
    renderVersion(DRAFT_ID);

    expect(await screen.findByRole("heading", { level: 1, name: "US list prices" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^Version / }).textContent).toContain(
      "Version 2026-H2 (Draft)",
    );
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));

    // SCREENS §11.4 (J-02-AC-5): 422 ssp-study-required is ERR-10, never the server's wording.
    expect(
      await screen.findByText("Attach the SSP study before submitting this version."),
    ).toBeTruthy();
    expect(
      screen.queryByText("Attach an SSP study and a methodology label before you submit."),
    ).toBeNull();
    expect(recorded).toEqual([
      { path: `/api/v1/ssp-book-versions/${DRAFT_ID}/submit`, ifMatch: '"r4"', body: {} },
    ]);
    // The version stays a draft: the entries grid is editable and "Add entry" is offered.
    const grid = within(await screen.findByTestId("SF-13-grid-ssp-entries")).getByRole("grid", {
      name: "SSP entries",
    });
    expect(await within(grid).findByRole("rowheader", { name: "AVM-PLAT-100" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add entry" })).toBeTruthy();
  });

  // docs/dev-guide.md DG-FE-06 rev 1.228 (item KIT-UNPLACED-ERRORS-1): a refusal that names a member the
  // details form has no field for is said in the banner; one that names a field stands at it, once.
  it("a refusal of Save version details says in the banner what no field of the form shows", async () => {
    serve(version(), book());
    server.use(
      http.patch(apiUrl(`/api/v1/ssp-book-versions/${DRAFT_ID}`), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            {
              field: "legacy_version_label",
              sheet: null,
              row: null,
              rule_id: null,
              message: "The book already has a version with this label.",
            },
            {
              field: "is_methodology_change",
              sheet: null,
              row: null,
              rule_id: null,
              message: "A new methodology label is a methodology change.",
            },
          ],
        }),
      ),
    );
    renderVersion(DRAFT_ID);
    const form = await screen.findByRole("form", { name: "Version details" });
    fireEvent.click(within(form).getByRole("button", { name: "Save version details" }));

    const details = screen.getByRole("region", { name: "Version details" });
    const banner = await within(details).findByRole("alert");
    expect(
      within(banner).getByText("A new methodology label is a methodology change."),
    ).toBeTruthy();
    expect(
      within(details).getAllByText("The book already has a version with this label."),
    ).toHaveLength(1);
    expect(
      within(form)
        .getByRole("textbox", { name: /^Version label/ })
        .getAttribute("aria-invalid"),
    ).toBe("true");
  });

  it("an approved version is read-only and New draft version copies it", async () => {
    const recorded: Recorded[] = [];
    serve(
      version({
        id: APPROVED_ID,
        version_no: 1,
        status: "APPROVED",
        legacy_version_label: "2026-H1",
        effective_from_date: "2026-01-01",
        methodology_label: "List-price study",
        published_at: "2026-01-02T10:00:00Z",
      }),
      book({ draft_version_id: null }),
      recorded,
    );
    const { router } = renderVersion(APPROVED_ID);

    const container = await screen.findByTestId("SF-13-grid-ssp-entries");
    const grid = within(container).getByRole("grid", { name: "SSP entries" });
    const row = await within(grid).findByRole("row", { name: /AVM-PLAT-100/ });
    for (const figure of ["85,000.00", "100,000.00", "115,000.00"]) {
      expect(within(row).getByText(figure)).toBeTruthy();
    }
    for (const name of ["Add entry", "Submit for approval", "Withdraw", "Save version details"]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
    expect(screen.getByText("Set when a later version is approved.")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "New draft version" }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(
        `/policies/ssp-books/${BOOK_ID}/versions/${NEW_DRAFT_ID}`,
      );
    });
    expect(recorded).toEqual([
      {
        path: `/api/v1/ssp-books/${BOOK_ID}/versions`,
        ifMatch: null,
        body: { copy_from_version_id: APPROVED_ID, methodology_label: "List-price study" },
      },
    ]);
  });
});

describe("SF-13 SSP book helpers", () => {
  it("diff rows carry the changed cells and the Mid change", () => {
    const rows = diffRows(
      {
        added: [],
        removed: [],
        changed: [
          {
            key: {
              product_code: "AVM-PLAT-100",
              stratification: "",
              region: null,
              channel: null,
              segment: null,
              deal_size_band: null,
              term_band: null,
              currency: "USD",
            },
            before: H1_ENTRY,
            after: entry("95200.000000", "112000.00", "128800.00"),
            mid_change_ratio: "0.120000",
          },
        ],
      },
      [H2_ENTRY, entry("90.00", "100.00", "110.00", { id: "x", product_code: "AVM-SEAT-MO" })],
      true,
    );
    expect(rows.map((row) => [row.kind, row.entry.product_code, [...row.changed]])).toEqual([
      ["changed", "AVM-PLAT-100", ["low", "mid", "high"]],
      ["unchanged", "AVM-SEAT-MO", []],
    ]);
    expect(rows[0]?.midChangeRatio).toBe("0.120000");
  });

  it("the landing version is the approved version, else the draft, else the newest", () => {
    const approved = book();
    expect(landingVersionId(approved, [])).toBe(APPROVED_ID);
    expect(landingVersionId(book({ current_version: null }), [])).toBe(DRAFT_ID);
    expect(
      landingVersionId(book({ current_version: null, draft_version_id: null }), [
        version({ id: NEW_DRAFT_ID, status: "SUBMITTED" }),
      ]),
    ).toBe(NEW_DRAFT_ID);
  });

  it("percents convert to ratios on their digits", () => {
    expect(percentTextToRatio("15.00")).toBe("0.1500");
    expect(percentTextToRatio("12.3456")).toBe("0.123456");
    expect(percentTextToRatio("100")).toBe("1.00");
    expect(percentTextToRatio("15%")).toBeNull();
    expect(ratioToPercentText("0.150000")).toBe("15.00");
    expect(ratioToPercentText("0.123456")).toBe("12.3456");
    expect(ratioToPercentText(null)).toBe("");
  });
});

// SCREENS §11.4 rows 5 and 5a (rev 1.5; D-97 (3)/(3a); readiness row SSP-EDITOR-ADMISSION; ENG-C1b API at
// 1434d07): a series product's entry declares its basis (no silent AMOUNT), a PER_INCREMENT entry declares its
// quantity unit (required, shown only then), both round-trip through every edit, and the API's 422 refusals at
// `entries[i].value_basis` / `entries[i].quantity_unit` show at the field.
describe("SF-13:ssp-book-version series basis and quantity unit (D-97 (3)/(3a))", () => {
  const SERIES_CODE = "AVM-SERIES-12";
  const PLAIN_CODE = "AVM-PLAT-100";
  const BASIS_REQUIRED = "Choose the value basis of this series product's entry.";
  const UNIT_REQUIRED = "Choose what the line quantity counts for a per-increment entry.";
  const UNIT_DISAGREES =
    "Entries of one product declare one quantity unit; entries[0] declares another.";

  function product(code: string, distinctness: "distinct" | "series"): Product {
    return {
      id: `7a6b5c4d-3e2f-4a1b-9c8d-${code.length.toString().padStart(12, "0")}`,
      code,
      name: distinctness === "series" ? "Managed service (series)" : "Platform subscription",
      is_active: true,
      is_bundle: false,
      distinctness_default: distinctness,
      default_pob_template_id: null,
    } as unknown as Product;
  }

  /** The draft version with its products and a recording entries endpoint answering `answer`. */
  function serveDraft(entries: readonly SspEntry[], answer: () => Response) {
    const posted: unknown[] = [];
    serve(version(), book());
    server.use(
      http.get(apiUrl("/api/v1/products"), () =>
        HttpResponse.json({
          items: [product(PLAIN_CODE, "distinct"), product(SERIES_CODE, "series")],
          next_cursor: null,
        }),
      ),
      http.get(apiUrl("/api/v1/tenant-currencies"), () =>
        HttpResponse.json({
          items: [{ code: "USD", name: "US dollar", minor_unit: 2, is_enabled: true }],
          next_cursor: null,
        }),
      ),
      http.get(apiUrl("/api/v1/ssp-book-versions/:versionId/entries"), () =>
        HttpResponse.json(
          { items: entries, next_cursor: null },
          { headers: { "X-Erev-Total-Count": String(entries.length) } },
        ),
      ),
      http.post(apiUrl("/api/v1/ssp-book-versions/:versionId/entries"), async ({ request }) => {
        posted.push(await request.json());
        return answer();
      }),
    );
    return { posted };
  }

  const saved = () => HttpResponse.json({ items: [] });

  async function openNewEntry() {
    renderVersion(DRAFT_ID);
    fireEvent.click(await screen.findByRole("button", { name: "Add entry" }));
    return await screen.findByTestId("SF-13-drawer-entry");
  }

  async function chooseProduct(drawer: HTMLElement, code: string) {
    const input = within(drawer).getByRole("combobox", { name: "Product" });
    await waitFor(() => {
      expect(input.hasAttribute("aria-controls")).toBe(true);
    });
    fireEvent.change(input, { target: { value: code } });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => {
      expect((input as HTMLInputElement).value).toContain(code);
    });
  }

  function pick(drawer: HTMLElement, field: string, label: string) {
    const select = within(drawer).getByRole("combobox", { name: field });
    fireEvent.click(select);
    fireEvent.mouseDown(screen.getByRole("option", { name: label }));
  }

  it("a series product has no default basis: Save entry refuses at the Basis field and posts nothing", async () => {
    const { posted } = serveDraft([], saved);
    const drawer = await openNewEntry();
    await chooseProduct(drawer, SERIES_CODE);

    expect(within(drawer).getByRole("combobox", { name: "Basis" }).textContent).toBe(
      "Choose a basis",
    );
    fireEvent.click(screen.getByRole("button", { name: "Save entry" }));
    expect(await within(drawer).findByText(BASIS_REQUIRED)).toBeTruthy();
    expect(posted).toHaveLength(0);
  });

  it("a per-increment entry requires its quantity unit and the body carries both declarations", async () => {
    const { posted } = serveDraft([], saved);
    const drawer = await openNewEntry();
    await chooseProduct(drawer, SERIES_CODE);
    expect(within(drawer).queryByRole("combobox", { name: "Quantity unit" })).toBeNull();

    pick(drawer, "Basis", "Per increment (series)");
    expect(within(drawer).getByRole("combobox", { name: "Quantity unit" }).textContent).toBe(
      "Choose a unit",
    );
    fireEvent.click(screen.getByRole("button", { name: "Save entry" }));
    expect(await within(drawer).findByText(UNIT_REQUIRED)).toBeTruthy();
    expect(posted).toHaveLength(0);

    pick(drawer, "Quantity unit", "Service units");
    fireEvent.click(screen.getByRole("button", { name: "Save entry" }));
    await waitFor(() => {
      expect(posted).toHaveLength(1);
    });
    const body = posted[0] as { entries: Record<string, unknown>[] };
    expect(body.entries[0]).toMatchObject({
      product_code: SERIES_CODE,
      value_basis: "PER_INCREMENT",
      quantity_unit: "SERVICE_UNITS",
    });
  });

  it("an API refusal at entries[0].quantity_unit shows at the Quantity unit field", async () => {
    const { posted } = serveDraft([], () =>
      problemResponse("validation-failed", 422, "1 field needs attention.", {
        errors: [
          {
            field: "entries[0].quantity_unit",
            sheet: null,
            row: null,
            rule_id: null,
            message: UNIT_DISAGREES,
          },
        ],
      }),
    );
    const drawer = await openNewEntry();
    await chooseProduct(drawer, SERIES_CODE);
    pick(drawer, "Basis", "Per increment (series)");
    pick(drawer, "Quantity unit", "Increments");
    fireEvent.click(screen.getByRole("button", { name: "Save entry" }));
    await waitFor(() => {
      expect(posted).toHaveLength(1);
    });

    const unitField = within(drawer).getByRole("combobox", { name: "Quantity unit" });
    const message = await within(drawer).findByText(UNIT_DISAGREES);
    // The refusal sits on the field (its error id describes the control), not only in the banner.
    expect(unitField.getAttribute("aria-describedby") ?? "").toContain(message.id);
    expect(unitField.getAttribute("aria-invalid")).toBe("true");
  });

  it("an inline band edit round-trips a stored entry's quantity unit", async () => {
    const stored = {
      ...entry("100.00", "110.00", "120.00"),
      product_code: SERIES_CODE,
      value_basis: "PER_INCREMENT",
      quantity_unit: "INCREMENTS",
      distinctness: "series",
    } as unknown as SspEntry;
    const { posted } = serveDraft([stored], saved);
    renderVersion(DRAFT_ID);
    const grid = within(await screen.findByTestId("SF-13-grid-ssp-entries")).getByRole("grid", {
      name: "SSP entries",
    });
    await within(grid).findByText(SERIES_CODE);
    // The first `mid` cell is the header; the row cell follows (as DataGrid.edit.test.tsx activates cells).
    const mid = grid.querySelectorAll<HTMLElement>("[data-column='mid']")[1];
    if (mid === undefined) {
      throw new Error("mid cell not found");
    }
    expect(mid.textContent).toContain("110.00");
    fireEvent.mouseDown(mid);
    act(() => mid.focus());
    fireEvent.keyDown(mid, { key: "Enter" });
    const input = await screen.findByRole("textbox", { name: "Mid" });
    fireEvent.change(input, { target: { value: "115.00" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => {
      expect(posted).toHaveLength(1);
    });
    const body = posted[0] as { entries: Record<string, unknown>[] };
    expect(body.entries[0]).toMatchObject({
      product_code: SERIES_CODE,
      value_basis: "PER_INCREMENT",
      quantity_unit: "INCREMENTS",
    });
  });

  it("a non-series product keeps the Amount default and shows no Quantity unit field", async () => {
    const { posted } = serveDraft([], saved);
    const drawer = await openNewEntry();
    await chooseProduct(drawer, PLAIN_CODE);
    expect(within(drawer).getByRole("combobox", { name: "Basis" }).textContent).toBe("Amount");
    expect(within(drawer).queryByRole("combobox", { name: "Quantity unit" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save entry" }));
    await waitFor(() => {
      expect(posted).toHaveLength(1);
    });
    const body = posted[0] as { entries: Record<string, unknown>[] };
    expect(body.entries[0]).toMatchObject({ product_code: PLAIN_CODE, value_basis: "AMOUNT" });
    expect(body.entries[0]?.quantity_unit ?? null).toBeNull();
  });
});

// SSP-ADMISSION-R1 (Codex `PRODUCTION-SSP-EDITOR-ADMISSION-ad8a117.md`, SHA-256 9f6ae136…4c6951d3, case S09;
// SCREENS §11.4 row 5 rev 1.6; joint ruling with ENG-C1b): the API classifies a series product by its default POB
// template's distinctness and exposes that as the derived `requires_explicit_ssp_basis`; the product's own
// `distinctness_default` can differ and is display-only. The original series fixtures above stay unchanged as
// the distinct integration controls Codex asked to preserve.
describe("SF-13:ssp-book-version series classification follows the API's requires_explicit_ssp_basis", () => {
  const TEMPLATE_SERIES_CODE = "AVM-TPL-SERIES";
  const LABELLED_SERIES_CODE = "AVM-LBL-SERIES";
  const BASIS_REQUIRED = "Choose the value basis of this series product's entry.";

  function product(
    code: string,
    distinctness: "distinct" | "series",
    requiresExplicit: boolean,
  ): Product {
    return {
      id: `8b7c6d5e-4f3a-4b2c-9d1e-${code.length.toString().padStart(12, "0")}`,
      code,
      name: `${code} product`,
      is_active: true,
      is_bundle: false,
      distinctness_default: distinctness,
      default_pob_template_id: "9c8d7e6f-5a4b-4c3d-8e2f-000000000001",
      requires_explicit_ssp_basis: requiresExplicit,
      default_pob_template_id_note: undefined,
    } as unknown as Product;
  }

  function serveDraft() {
    const posted: unknown[] = [];
    serve(version(), book());
    server.use(
      http.get(apiUrl("/api/v1/products"), () =>
        HttpResponse.json({
          items: [
            product(TEMPLATE_SERIES_CODE, "distinct", true),
            product(LABELLED_SERIES_CODE, "series", false),
          ],
          next_cursor: null,
        }),
      ),
      http.get(apiUrl("/api/v1/tenant-currencies"), () =>
        HttpResponse.json({
          items: [{ code: "USD", name: "US dollar", minor_unit: 2, is_enabled: true }],
          next_cursor: null,
        }),
      ),
      http.get(apiUrl("/api/v1/ssp-book-versions/:versionId/entries"), () =>
        HttpResponse.json(
          { items: [], next_cursor: null },
          { headers: { "X-Erev-Total-Count": "0" } },
        ),
      ),
      http.post(apiUrl("/api/v1/ssp-book-versions/:versionId/entries"), async ({ request }) => {
        posted.push(await request.json());
        return HttpResponse.json({ items: [] });
      }),
    );
    return { posted };
  }

  async function openNewEntry() {
    renderVersion(DRAFT_ID);
    fireEvent.click(await screen.findByRole("button", { name: "Add entry" }));
    return await screen.findByTestId("SF-13-drawer-entry");
  }

  async function chooseProduct(drawer: HTMLElement, code: string) {
    const input = within(drawer).getByRole("combobox", { name: "Product" });
    await waitFor(() => {
      expect(input.hasAttribute("aria-controls")).toBe(true);
    });
    fireEvent.change(input, { target: { value: code } });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => {
      expect((input as HTMLInputElement).value).toContain(code);
    });
  }

  it("S09: a distinct-labelled product whose default template is series must still choose its basis", async () => {
    const { posted } = serveDraft();
    const drawer = await openNewEntry();
    await chooseProduct(drawer, TEMPLATE_SERIES_CODE);
    expect(within(drawer).getByRole("combobox", { name: "Basis" }).textContent).toBe(
      "Choose a basis",
    );
    fireEvent.click(screen.getByRole("button", { name: "Save entry" }));
    expect(await within(drawer).findByText(BASIS_REQUIRED)).toBeTruthy();
    expect(posted).toHaveLength(0);
  });

  it("a series-labelled product the API does not mark keeps the Amount default (the label is display-only)", async () => {
    const { posted } = serveDraft();
    const drawer = await openNewEntry();
    await chooseProduct(drawer, LABELLED_SERIES_CODE);
    expect(within(drawer).getByRole("combobox", { name: "Basis" }).textContent).toBe("Amount");
    fireEvent.click(screen.getByRole("button", { name: "Save entry" }));
    await waitFor(() => {
      expect(posted).toHaveLength(1);
    });
    const body = posted[0] as { entries: Record<string, unknown>[] };
    expect(body.entries[0]).toMatchObject({
      product_code: LABELLED_SERIES_CODE,
      value_basis: "AMOUNT",
    });
  });
});
