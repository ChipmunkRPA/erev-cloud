// @vitest-environment jsdom
// SF-15:products and SF-15:product (BUILD_SPEC RFD-21; SCREENS §10): the grid "Products" with the §10.3
// columns; the product page's attributes with the "Required" disaggregation chip; "Propose principal or
// agent change" calls `POST /products/{id}/propose-principal-agent-change` and renders the pending info
// banner; the SSP pane lists the entries pricing the product and, for the option product AVM-EXP-CREDIT,
// reads "SSP comes from the option record (discount × likelihood)."
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import {
  composeRationale,
  missingAttributes,
  policyValueRows,
  type Product,
  productPaneOf,
} from "../../lib/api/queries/products";
import type { PobTemplate } from "../../lib/api/queries/rule-sets";
import type { SspBook, SspBookVersion, SspEntry } from "../../lib/api/queries/ssp-books";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { REFUSAL_REFERENCE, REFUSAL_TITLE, refusedWith } from "../../test/refusals";

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

const MAINTAINER = signedInMe({ permissions: ["contract.read", "masterdata.maintain"] });

const SUB_VERSION = {
  id: "7f7f7f7f-7f7f-4f7f-8f7f-7f7f7f7f7f7f",
  version_no: 1,
  status: "PUBLISHED" as const,
  effective_from: null,
  published_at: null,
  lint_status: null,
  rule_count: null,
};
const OPTION_VERSION = { ...SUB_VERSION, id: "7b7b7b7b-7b7b-4b7b-8b7b-7b7b7b7b7b7b" };
const TPL_SUB: PobTemplate = {
  id: "7e7e7e7e-7e7e-4e7e-8e7e-7e7e7e7e7e7e",
  code: "TPL-SUB-DAILY",
  name: "Subscription, daily ratable",
  description: null,
  current_version: SUB_VERSION,
  latest_version: SUB_VERSION,
  row_version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};
const TPL_OPTION: PobTemplate = {
  ...TPL_SUB,
  id: "7a7a7a7a-7a7a-4a7a-8a7a-7a7a7a7a7a7a",
  code: "TPL-OPTION",
  name: "Customer option",
  current_version: OPTION_VERSION,
  latest_version: OPTION_VERSION,
};

function product(overrides: Partial<Product> & Pick<Product, "id" | "code" | "name">): Product {
  return {
    assurance_cost_per_unit: null,
    code_frozen: false,
    default_pob_template_id: TPL_SUB.id,
    disaggregation: {},
    distinctness_default: "distinct",
    is_active: true,
    is_bundle: false,
    is_franchisor_preopening_service: false,
    requires_explicit_ssp_basis: false,
    pending_approval_request_id: null,
    policy_values: {},
    principal_agent: "PRINCIPAL",
    product_family: "Platform",
    revenue_category: "SUBSCRIPTION",
    row_version: 2,
    sku_number: null,
    unit_of_measure: "EA",
    usability: { usable: true, missing: [] },
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    ...overrides,
  };
}
const PLAT_100 = product({
  id: "a1000000-0000-4000-8000-000000000100",
  code: "AVM-PLAT-100",
  name: "Platform, 100 seats, 12 months",
  disaggregation: { region: "NA" },
  policy_values: { "revenue.ratable_convention": "DAILY" },
});
const EXP_CREDIT = product({
  id: "a1000000-0000-4000-8000-000000000200",
  code: "AVM-EXP-CREDIT",
  name: "Expansion credit (customer option)",
  revenue_category: "MATERIAL_RIGHT",
  default_pob_template_id: TPL_OPTION.id,
  product_family: "Options",
});

const V_H1: SspBookVersion = {
  id: "5b5b5b5b-5b5b-4b5b-8b5b-5b5b5b5b5b5b",
  ssp_book_id: "5a5a5a5a-5a5a-4a5a-8a5a-5a5a5a5a5a5a",
  version_no: 1,
  status: "PUBLISHED",
  legacy_version_label: "2026-H1",
  methodology_label: "Observable list prices",
  effective_from_date: "2026-01-01",
  effective_to_date: "2026-09-30",
  entry_count: 1,
  is_methodology_change: false,
  approval_request_id: null,
  content_sha256: null,
  diff_summary: null,
  published_at: "2026-01-02T00:00:00Z",
  ssp_calculator_run_id: null,
  study_attachment_ids: [],
  created_by: { id: null, kind: "SYSTEM", display_name: "Seed" },
  row_version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
};
const US_LIST: SspBook = {
  id: V_H1.ssp_book_id,
  code: "US-LIST",
  name: "US list prices",
  description: null,
  currency: "USD",
  entity_code: "AVM-US",
  channel: null,
  segment: null,
  resolution_mode: "EFFECTIVE_DATE",
  current_version: {
    id: V_H1.id,
    version_no: 1,
    legacy_version_label: "2026-H1",
    effective_from_date: "2026-01-01",
    effective_to_date: "2026-09-30",
  },
  draft_version_id: null,
  row_version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
};
const ENTRY: SspEntry = {
  id: "5c5c5c5c-5c5c-4c5c-8c5c-5c5c5c5c5c5c",
  product_code: "AVM-PLAT-100",
  currency: "USD",
  method: "observable",
  value_basis: "AMOUNT",
  quantity_unit: null,
  distinctness: "distinct",
  stratification: "NONE",
  ranges: [
    {
      band_dimension: "NONE",
      band_from: null,
      band_to: null,
      low_value: "85000.00",
      mid_value: "100000.00",
      high_value: "115000.00",
      point_value: null,
    },
  ],
  observable_point: null,
  channel: null,
  cost_basis: null,
  deal_size_band: null,
  margin_ratio: null,
  midpoint_discount_ratio: null,
  range_ratio: null,
  region: null,
  revenue_account_code: null,
  segment: null,
  term_band: null,
  unit_list_price: null,
};

function serve(products: readonly Product[]) {
  const pending = new Map<string, string>();
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
    http.get(apiUrl("/api/v1/products"), ({ request }) =>
      HttpResponse.json(
        { items: products, next_cursor: null },
        {
          headers:
            new URL(request.url).searchParams.get("count") === "true"
              ? { "X-Erev-Total-Count": String(products.length) }
              : {},
        },
      ),
    ),
    http.get(apiUrl("/api/v1/products/:productId"), ({ params }) => {
      const found = products.find((item) => item.id === params.productId);
      if (found === undefined) {
        return problemResponse("not-found", 404, "Not found");
      }
      const requestId = pending.get(found.id) ?? null;
      return HttpResponse.json({ ...found, pending_approval_request_id: requestId });
    }),
    http.post(
      apiUrl("/api/v1/products/:productId/propose-principal-agent-change"),
      ({ params }) => {
        pending.set(String(params.productId), "0a0a0a0a-0a0a-4a0a-8a0a-0a0a0a0a0a0a");
        return HttpResponse.json(
          { approval_request_id: "0a0a0a0a-0a0a-4a0a-8a0a-0a0a0a0a0a0a" },
          { status: 202 },
        );
      },
    ),
    http.get(apiUrl("/api/v1/pob-templates"), () =>
      HttpResponse.json({ items: [TPL_SUB, TPL_OPTION], next_cursor: null }),
    ),
    http.get(apiUrl(`/api/v1/pob-template-versions/${TPL_SUB.current_version?.id ?? ""}`), () =>
      HttpResponse.json({
        id: TPL_SUB.current_version?.id,
        pob_template_id: TPL_SUB.id,
        template_code: TPL_SUB.code,
        version_no: 1,
        status: "PUBLISHED",
        policy_values: { "revenue.ratable_convention": "MONTHLY_EVEN" },
      }),
    ),
    http.get(apiUrl("/api/v1/policies/resolve"), () =>
      HttpResponse.json({
        key: "disclosure.mandatory_disaggregation_attributes",
        value: ["region"],
        chain: [],
        is_forced: false,
      }),
    ),
    http.get(apiUrl("/api/v1/currencies"), () =>
      HttpResponse.json({
        items: [
          { code: "USD", name: "US dollar", minor_unit: 2, numeric_code: "840", is_active: true },
        ],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/ssp-books"), () =>
      HttpResponse.json({ items: [US_LIST], next_cursor: null }),
    ),
    http.get(apiUrl(`/api/v1/ssp-book-versions/${V_H1.id}`), () => HttpResponse.json(V_H1)),
    http.get(apiUrl(`/api/v1/ssp-book-versions/${V_H1.id}/entries`), ({ request }) =>
      HttpResponse.json({
        items:
          new URL(request.url).searchParams.get("product") === ENTRY.product_code ? [ENTRY] : [],
        next_cursor: null,
      }),
    ),
  );
}

/** One entry of a 422's `errors[]` (04 API-C-05). */
function refused(field: string, message: string, rule = "T-REF-20") {
  return { field, sheet: null, row: null, rule_id: rule, message };
}

/** The product's page with its "Edit product" drawer open. */
async function editDrawer(subject: Product): Promise<HTMLElement> {
  renderApp(`/settings/products/${subject.id}`, { me: MAINTAINER, screenRoutes: SCREEN_ROUTES });
  fireEvent.click(await screen.findByRole("button", { name: "Edit product" }));
  return screen.findByRole("dialog", { name: "Edit product" });
}

/** The texts an element is described by, in the order of `aria-describedby`. */
function describedBy(element: HTMLElement): string[] {
  return (element.getAttribute("aria-describedby") ?? "")
    .split(" ")
    .filter((id) => id !== "")
    .map((id) => document.getElementById(id)?.textContent ?? "");
}

describe("SF-15:product", () => {
  it("principal or agent proposal uses the approval command", async () => {
    const bodies: unknown[] = [];
    serve([PLAT_100]);
    server.use(
      http.post(
        apiUrl(`/api/v1/products/${PLAT_100.id}/propose-principal-agent-change`),
        async ({ request }) => {
          bodies.push(await request.json());
          return HttpResponse.json(
            { approval_request_id: "0a0a0a0a-0a0a-4a0a-8a0a-0a0a0a0a0a0a" },
            { status: 202 },
          );
        },
      ),
      http.get(apiUrl(`/api/v1/products/${PLAT_100.id}`), () =>
        HttpResponse.json({
          ...PLAT_100,
          pending_approval_request_id:
            bodies.length === 0 ? null : "0a0a0a0a-0a0a-4a0a-8a0a-0a0a0a0a0a0a",
        }),
      ),
    );
    renderApp(`/settings/products/${PLAT_100.id}`, { me: MAINTAINER, screenRoutes: SCREEN_ROUTES });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Platform, 100 seats, 12 months" }),
    ).toBeTruthy();
    expect(screen.queryByTestId("SF-15-banner-principal-agent")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Propose principal or agent change" }));

    const dialog = await screen.findByRole("dialog", { name: "Propose principal or agent change" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Submit for approval" }));
    expect(
      await within(dialog).findByText("Enter the rationale (at least 10 characters)."),
    ).toBeTruthy();
    expect(bodies).toEqual([]);

    fireEvent.click(within(dialog).getByRole("radio", { name: "Agent" }));
    const inventory = within(dialog).getByRole("group", { name: "Has inventory risk" });
    fireEvent.click(within(inventory).getByRole("radio", { name: "No" }));
    fireEvent.change(within(inventory).getByRole("textbox", { name: /^Note/ }), {
      target: { value: "Stock stays with the vendor." },
    });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Rationale/ }), {
      target: { value: "The vendor controls the goods before transfer." },
    });
    expect(
      within(dialog).getByText("The change applies prospectively after approval."),
    ).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Submit for approval" }));

    expect(
      await screen.findByText("Principal or agent change submitted for approval."),
    ).toBeTruthy();
    expect(bodies).toHaveLength(1);
    const body = bodies[0] as { principal_agent: string; rationale: string };
    expect(body.principal_agent).toBe("AGENT");
    expect(body.rationale).toContain("Has inventory risk: No (Stock stays with the vendor.)");
    expect(body.rationale).toContain("The vendor controls the goods before transfer.");

    const banner = await screen.findByTestId("SF-15-banner-principal-agent");
    expect(
      within(banner).getByText("A principal or agent change is waiting for approval."),
    ).toBeTruthy();
    expect(within(banner).getByRole("link", { name: "View request" }).getAttribute("href")).toBe(
      "/approvals/requests/0a0a0a0a-0a0a-4a0a-8a0a-0a0a0a0a0a0a",
    );
    expect(
      composeRationale(
        [
          { label: "Has inventory risk", answer: "no", note: "" },
          { label: "Pricing", answer: null, note: "x" },
        ],
        "Because.",
      ),
    ).toBe("Has inventory risk: No\nBecause.");
  });

  it("a product whose code is frozen shows Code read-only with the line that says why, and a save sends the rest", async () => {
    // 04 API-R-23 rev 1.223: `code_frozen` is the predicate of DB-05 — a contract line, an SSP entry or
    // an account mapping rule references the product — so the drawer no longer offers a field whose
    // save the server refuses (SCREENS §10.4, rev 1.44).
    const inUse = product({ ...PLAT_100, code_frozen: true });
    const renamed = "Platform, 100 seats, annual";
    const patches: unknown[] = [];
    serve([inUse]);
    server.use(
      http.patch(apiUrl(`/api/v1/products/${inUse.id}`), async ({ request }) => {
        patches.push(await request.json());
        return HttpResponse.json({ ...inUse, name: renamed, row_version: inUse.row_version + 1 });
      }),
    );
    const drawer = await editDrawer(inUse);
    const code = within(drawer).getByRole<HTMLInputElement>("textbox", { name: "Code" });
    expect(code.readOnly).toBe(true);
    expect(code.value).toBe(inUse.code);
    expect(describedBy(code)).toEqual([
      "The code is fixed once a contract line, an SSP entry or an account mapping rule references the product.",
    ]);
    // The other fields stay editable, and what is saved names no code.
    const name = within(drawer).getByRole<HTMLInputElement>("textbox", { name: "Name" });
    expect(name.readOnly).toBe(false);
    fireEvent.change(name, { target: { value: renamed } });
    fireEvent.click(within(drawer).getByRole("button", { name: "Save product" }));
    await waitFor(() => {
      expect(patches).toEqual([{ name: renamed }]);
    });
  });

  it("a refused change of the code shows the server's sentence at Code, and the help names what fixes the code", async () => {
    // 04 T-REF-20 DB-05 (item PRODUCT-CODE-FREEZE-1). The read model says `code_frozen` false here, so
    // Code is a field (SCREENS §10.4, rev 1.44); the code froze after the product was read — another
    // session booked a line — and the server's refusal stands at the field.
    const frozen =
      "The code cannot change: contract lines and SSP entries use this product. Create a new product for the new code.";
    const patches: unknown[] = [];
    serve([PLAT_100]);
    server.use(
      http.patch(apiUrl(`/api/v1/products/${PLAT_100.id}`), async ({ request }) => {
        patches.push(await request.json());
        return problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [{ field: "code", sheet: null, row: null, rule_id: "DB-05", message: frozen }],
        });
      }),
    );
    renderApp(`/settings/products/${PLAT_100.id}`, { me: MAINTAINER, screenRoutes: SCREEN_ROUTES });

    fireEvent.click(await screen.findByRole("button", { name: "Edit product" }));
    const drawer = await screen.findByRole("dialog", { name: "Edit product" });
    const code = within(drawer).getByRole<HTMLInputElement>("textbox", { name: "Code" });
    const descriptions = () =>
      (code.getAttribute("aria-describedby") ?? "")
        .split(" ")
        .map((id) => document.getElementById(id)?.textContent ?? "")
        .join(" | ");
    expect(code.readOnly).toBe(false);
    expect(descriptions()).toBe(
      "The code is fixed once a contract line, an SSP entry or an account mapping rule references the product.",
    );
    fireEvent.change(code, { target: { value: "AVM-PLAT-101" } });
    fireEvent.click(within(drawer).getByRole("button", { name: "Save product" }));

    await waitFor(() => {
      expect(descriptions()).toContain(frozen);
    });
    expect(patches).toEqual([{ code: "AVM-PLAT-101" }]);
    expect(code.getAttribute("aria-invalid")).toBe("true");
    // The field the refusal names is highlighted and holds the sentence, once.
    expect(within(drawer).getAllByText(frozen)).toHaveLength(1);
  });

  it("a refusal that names a member the drawer has no control for is listed in the banner, each sentence once", async () => {
    // SCREENS §10.4 (rev 1.35): the banner was dropped as soon as the problem carried a field error,
    // so a refusal on a member without a control showed nothing at all.
    const cost = "Enter an assurance cost per unit of zero or more.";
    const unknown = "Use the code of a policy parameter.";
    serve([PLAT_100]);
    server.use(
      http.patch(apiUrl(`/api/v1/products/${PLAT_100.id}`), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            refused("assurance_cost_per_unit", cost),
            refused("policy_values.x.one", unknown),
            refused("policy_values.x.two", unknown),
          ],
        }),
      ),
    );
    const drawer = await editDrawer(PLAT_100);
    fireEvent.change(within(drawer).getByRole("textbox", { name: "Name" }), {
      target: { value: "Platform, 100 seats" },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Save product" }));

    const banner = (
      await within(drawer).findByRole("heading", { name: "Check the highlighted fields" })
    ).closest<HTMLElement>('[role="alert"]');
    if (banner === null) {
      throw new Error("the refusal is not announced as an alert");
    }
    expect(within(banner).getAllByText(cost)).toHaveLength(1);
    expect(within(banner).getAllByText(unknown)).toHaveLength(1);
    // Nothing of the form is highlighted: the banner is all the refusal has.
    expect(drawer.querySelectorAll('[aria-invalid="true"]')).toHaveLength(0);
  });

  it("a refused Bundle shows the server's sentence at Bundle and leaves when Bundle is changed", async () => {
    const fleet = product({
      id: "a1000000-0000-4000-8000-000000000300",
      code: "AVM-FLEET",
      name: "Gateway fleet package",
      is_bundle: true,
    });
    const components = "Remove the bundle components before clearing Bundle.";
    const patches: unknown[] = [];
    serve([fleet]);
    server.use(
      http.patch(apiUrl(`/api/v1/products/${fleet.id}`), async ({ request }) => {
        patches.push(await request.json());
        return problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [refused("is_bundle", components, "T-REF-21")],
        });
      }),
    );
    const drawer = await editDrawer(fleet);
    const bundle = within(drawer).getByRole<HTMLInputElement>("checkbox", { name: "Bundle" });
    expect(bundle.checked).toBe(true);
    fireEvent.click(bundle);
    fireEvent.click(within(drawer).getByRole("button", { name: "Save product" }));

    await waitFor(() => {
      expect(bundle.getAttribute("aria-invalid")).toBe("true");
    });
    expect(patches).toEqual([{ is_bundle: false }]);
    expect(describedBy(bundle)).toEqual([components]);
    // The banner points at the control and does not say its sentence again.
    expect(
      within(drawer).getByRole("heading", { name: "Check the highlighted fields" }),
    ).toBeTruthy();
    expect(within(drawer).getAllByText(components)).toHaveLength(1);

    // The message describes the value that was sent: it leaves with it, and so does a banner
    // that has nothing else to say.
    fireEvent.click(bundle);
    expect(bundle.getAttribute("aria-invalid")).toBeNull();
    expect(within(drawer).queryByText(components)).toBeNull();
    expect(
      within(drawer).queryByRole("heading", { name: "Check the highlighted fields" }),
    ).toBeNull();
  });

  it("a refused attribute value shows at the row its pointer names, above the warning of the missing attribute", async () => {
    const enterprise = product({
      id: "a1000000-0000-4000-8000-000000000400",
      code: "AVM-PLAT-ENT",
      name: "Platform, enterprise tier, 12 months",
      disaggregation: { channel: "Direct", region: "NA" },
    });
    const value = "Enter a value for this disaggregation attribute.";
    const patches: unknown[] = [];
    serve([enterprise]);
    server.use(
      http.patch(apiUrl(`/api/v1/products/${enterprise.id}`), async ({ request }) => {
        patches.push(await request.json());
        return problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [refused("disaggregation.region", value)],
        });
      }),
    );
    const drawer = await editDrawer(enterprise);
    const rows = within(drawer).getByTestId("SF-15-product-attributes");
    const [channel, region] = within(rows).getAllByRole<HTMLInputElement>("textbox", {
      name: "Value",
    });
    if (channel === undefined || region === undefined) {
      throw new Error("the drawer does not show the two attribute rows");
    }
    expect([channel.value, region.value]).toEqual(["Direct", "NA"]);
    fireEvent.change(region, { target: { value: "" } });
    fireEvent.click(within(drawer).getByRole("button", { name: "Save product" }));

    await waitFor(() => {
      expect(region.getAttribute("aria-invalid")).toBe("true");
    });
    expect(patches).toEqual([{ disaggregation: { channel: "Direct", region: "" } }]);
    expect(describedBy(region)).toEqual([value]);
    expect(channel.getAttribute("aria-invalid")).toBeNull();
    expect(within(drawer).getAllByText(value)).toHaveLength(1);
    // The refusal's banner stands above the warning of the required attribute, which stays.
    const refusal = within(drawer).getByRole("heading", { name: "Check the highlighted fields" });
    const warning = within(drawer).getByRole("heading", {
      name: "This product cannot be used on contracts until region are set.",
    });
    expect(
      refusal.compareDocumentPosition(warning) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    fireEvent.change(region, { target: { value: "EMEA" } });
    expect(region.getAttribute("aria-invalid")).toBeNull();
    expect(within(drawer).queryByText(value)).toBeNull();
  });

  it("a refused attribute that is no row of the drawer stands under the heading of the rows", async () => {
    const named = "Name the disaggregation attribute.";
    serve([PLAT_100]);
    server.use(
      http.patch(apiUrl(`/api/v1/products/${PLAT_100.id}`), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [refused("disaggregation.segment", named)],
        }),
      ),
    );
    const drawer = await editDrawer(PLAT_100);
    const rows = within(drawer).getByTestId("SF-15-product-attributes");
    fireEvent.change(within(rows).getByRole("textbox", { name: "Value" }), {
      target: { value: "EMEA" },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Save product" }));

    expect(await within(rows).findByText(named)).toBeTruthy();
    expect(describedBy(rows)).toEqual([named]);
    expect(within(rows).getByRole("textbox", { name: "Value" }).getAttribute("aria-invalid")).toBe(
      null,
    );
    expect(within(drawer).getAllByText(named)).toHaveLength(1);
  });

  it("a message at a field leaves when that field is edited, and the banner once it points at nothing", async () => {
    const length = "Use 1 to 400 characters.";
    const published = "Choose an obligation template with a published version.";
    serve([PLAT_100]);
    server.use(
      http.patch(apiUrl(`/api/v1/products/${PLAT_100.id}`), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [refused("name", length), refused("default_pob_template_id", published)],
        }),
      ),
    );
    const drawer = await editDrawer(PLAT_100);
    const name = within(drawer).getByRole<HTMLInputElement>("textbox", { name: "Name" });
    const template = within(drawer).getByRole("combobox", { name: /^Default obligation template/ });
    fireEvent.change(name, { target: { value: "Platform, 100 seats" } });
    fireEvent.click(within(drawer).getByRole("button", { name: "Save product" }));

    await waitFor(() => {
      expect(name.getAttribute("aria-invalid")).toBe("true");
    });
    expect(describedBy(name)).toEqual([length]);
    expect(describedBy(template)).toEqual([published]);
    const banner = () =>
      within(drawer).queryByRole("heading", { name: "Check the highlighted fields" });
    expect(banner()).not.toBeNull();

    // One field edited: its message leaves, and the banner still points at the other.
    fireEvent.change(name, { target: { value: "Platform, 100 seats, 12 months" } });
    expect(name.getAttribute("aria-invalid")).toBeNull();
    expect(within(drawer).queryByText(length)).toBeNull();
    expect(template.getAttribute("aria-invalid")).toBe("true");
    expect(banner()).not.toBeNull();

    fireEvent.click(template);
    fireEvent.mouseDown(await screen.findByRole("option", { name: "No default template" }));
    expect(template.getAttribute("aria-invalid")).toBeNull();
    expect(within(drawer).queryByText(published)).toBeNull();
    expect(banner()).toBeNull();
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): a message that names a member no
  // field shows was shown nowhere, and the API's message on the conclusion was drawn only while no
  // conclusion was chosen — never, since one is sent. The banner lists what no field shows.
  it("the proposal under a refused command: the banner lists what no field shows, and the conclusion's message stands at it", async () => {
    const noField = "A change of this product is waiting for approval.";
    const atConclusion = "The product is a principal already.";
    serve([PLAT_100]);
    server.use(
      http.post(apiUrl(`/api/v1/products/${PLAT_100.id}/propose-principal-agent-change`), () =>
        refusedWith({ product_id: noField, principal_agent: atConclusion }),
      ),
    );
    renderApp(`/settings/products/${PLAT_100.id}`, { me: MAINTAINER, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(
      await screen.findByRole("button", { name: "Propose principal or agent change" }),
    );
    const dialog = await screen.findByRole("dialog", { name: "Propose principal or agent change" });
    fireEvent.click(within(dialog).getByRole("radio", { name: "Agent" }));
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Rationale/ }), {
      target: { value: "The vendor controls the goods before transfer." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Submit for approval" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + noField + REFUSAL_REFERENCE);
    expect(within(dialog).getByText(atConclusion)).toBeTruthy();
  });

  it("Save components under a refused command: the pane shows no message at a field, so the banner says every sentence", async () => {
    const sentence = "A component cannot be a bundle itself.";
    const bundle = { ...PLAT_100, is_bundle: true };
    serve([bundle, EXP_CREDIT]);
    server.use(
      http.get(apiUrl(`/api/v1/products/${PLAT_100.id}/bundle-components`), () =>
        HttpResponse.json({ bundle_product_id: PLAT_100.id, components: [] }),
      ),
      http.put(apiUrl(`/api/v1/products/${PLAT_100.id}/bundle-components`), () =>
        refusedWith({ "components.0.component_product_id": sentence }),
      ),
    );
    renderApp(`/settings/products/${PLAT_100.id}?pane=bundle`, {
      me: MAINTAINER,
      screenRoutes: SCREEN_ROUTES,
    });
    const pane = await screen.findByTestId("SF-15-pane-bundle");
    fireEvent.click(await within(pane).findByRole("button", { name: "Add component row" }));
    const component = within(pane).getByRole("combobox", { name: /^Component/ });
    fireEvent.change(component, { target: { value: EXP_CREDIT.code } });
    fireEvent.mouseDown(
      await screen.findByRole("option", { name: `${EXP_CREDIT.code} · ${EXP_CREDIT.name}` }),
    );
    fireEvent.change(within(pane).getByLabelText(/^Quantity per bundle/), {
      target: { value: "1" },
    });
    const from = within(pane).getByLabelText(/^Valid from/);
    fireEvent.change(from, { target: { value: "2026-10-01" } });
    fireEvent.blur(from);
    fireEvent.click(within(pane).getByRole("button", { name: "Save components" }));

    const heading = await within(pane).findByRole("heading", { name: REFUSAL_TITLE });
    expect(heading.closest('[role="alert"]')?.textContent).toBe(
      REFUSAL_TITLE + sentence + REFUSAL_REFERENCE,
    );
  });

  it("option product ssp empty text", async () => {
    serve([EXP_CREDIT]);
    renderApp(`/settings/products/${EXP_CREDIT.id}?pane=ssp`, {
      me: MAINTAINER,
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByText("SSP comes from the option record (discount × likelihood)."),
    ).toBeTruthy();
    expect(screen.queryByTestId("SF-15-grid-product-ssp")).toBeNull();
    expect(productPaneOf("ssp")).toBe("ssp");
    expect(productPaneOf("nonsense")).toBe("attributes");
  });

  it("the SSP pane lists the entries of the current version pricing the product", async () => {
    serve([PLAT_100]);
    renderApp(`/settings/products/${PLAT_100.id}?pane=ssp`, {
      me: MAINTAINER,
      screenRoutes: SCREEN_ROUTES,
    });

    const table = await screen.findByRole("table", { name: "SSP entries" }, { timeout: 4000 });
    expect(table.getAttribute("data-testid")).toBe("SF-15-grid-product-ssp");
    const row = within(table).getByTestId("SF-15-ssp-US-LIST-1");
    expect(within(row).getByRole("link", { name: "US-LIST" })).toBeTruthy();
    expect(within(row).getByText("2026-H1")).toBeTruthy();
    expect(within(row).getByText("Published")).toBeTruthy();
    expect(within(row).getByText("01 Jan 2026 – 30 Sep 2026")).toBeTruthy();
    expect(within(row).getByText("Observable")).toBeTruthy();
    expect(within(row).getByText("85,000.00")).toBeTruthy();
    expect(within(row).getByText("100,000.00")).toBeTruthy();
    expect(within(row).getByText("115,000.00")).toBeTruthy();
    expect(within(row).getByText("USD")).toBeTruthy();
  });

  it("the attributes pane marks required disaggregation attributes and the policy values pane layers template values", async () => {
    serve([PLAT_100]);
    renderApp(`/settings/products/${PLAT_100.id}`, { me: MAINTAINER, screenRoutes: SCREEN_ROUTES });

    const attributes = await screen.findByTestId("SF-15-pane-attributes");
    expect(within(attributes).getByText("Platform")).toBeTruthy();
    expect(await within(attributes).findByText("TPL-SUB-DAILY v1")).toBeTruthy();
    const table = await within(attributes).findByRole("table", {
      name: "Disaggregation attributes",
    });
    const region = within(table).getByRole("row", { name: /region/ });
    expect(await within(region).findByText("Required")).toBeTruthy();
    expect(within(region).getByText("NA")).toBeTruthy();
    expect(
      missingAttributes({ usability: { usable: true, missing: [] }, disaggregation: {} }, [
        "region",
      ]),
    ).toEqual(["region"]);

    fireEvent.click(screen.getByRole("tab", { name: "Policy values" }));
    const values = await screen.findByRole("table", { name: "Policy values" });
    const rows = within(values).getAllByRole("row").slice(1);
    expect(rows.map((r) => r.textContent)).toEqual([
      "revenue.ratable_conventionDAILYProduct",
      "revenue.ratable_conventionMONTHLY_EVENTemplate TPL-SUB-DAILY v1",
    ]);
    expect(
      policyValueRows({ policy_values: { a: 1 } }, { policy_values: { a: "x" } }).map(
        (r) => r.level,
      ),
    ).toEqual(["product", "template"]);
  });
});

describe("SF-15:products", () => {
  it("the grid Products shows the §10.3 columns and keys rows by code", async () => {
    serve([PLAT_100, EXP_CREDIT]);
    renderApp("/settings/products", { me: MAINTAINER, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-15-grid-products")).findByRole("grid", {
      name: "Products",
    });
    const headers = within(grid)
      .getAllByRole("columnheader")
      .map((header) => header.textContent?.trim() ?? "");
    for (const name of [
      "Product",
      "Name",
      "SKU number",
      "Product family",
      "Revenue category",
      "Default template",
      "Principal or agent",
      "Distinct by default",
      "Unit",
      "Bundle",
      "Active",
    ]) {
      expect(headers.some((header) => header.startsWith(name))).toBe(true);
    }
    const row = await within(grid).findByTestId("SF-15-row-avm-plat-100");
    expect(within(grid).getByRole("row", { name: /AVM-PLAT-100/ })).toBe(row);
    expect(within(row).getByRole("link", { name: "AVM-PLAT-100" }).getAttribute("href")).toBe(
      `/settings/products/${PLAT_100.id}`,
    );
    expect(within(row).getByText("Platform, 100 seats, 12 months")).toBeTruthy();
    expect(within(row).getByText("SUBSCRIPTION")).toBeTruthy();
    expect(await within(row).findByText("TPL-SUB-DAILY")).toBeTruthy();
    expect(within(row).getByText("Principal")).toBeTruthy();
    expect(within(row).getByText("Distinct")).toBeTruthy();
    expect(within(row).getByText("No")).toBeTruthy();
    expect(within(row).getByText("Yes")).toBeTruthy();
    expect(screen.getByRole("searchbox", { name: "Search products" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "New product" })).toBeTruthy();
  });
});
