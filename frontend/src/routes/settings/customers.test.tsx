// @vitest-environment jsdom
// SF-15:customers (BUILD_SPEC RFD-20; SCREENS §9): the grid "Customers" with the §9.4 columns and the row
// keyed by external id; the quick search "Search customers"; "New customer" opens the drawer
// (`SF-15-drawer-customer`) whose Name carries the identity-only help; a 422 `validation-failed` naming
// `external_id` renders the field error in the drawer; the empty state with "New customer" and "Import
// customers".
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { http } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { groupDrawerRoute, groupLabel } from "../../lib/api/queries/customers";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import {
  HOLLENBRAND,
  KLINIKBEDARF,
  MEDIZINTECHNIK,
  PELLWORTH,
  serveCustomers,
} from "../../test/customers";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { customerFilterFields, customerQuery } from "./customers";

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

const MAINTAINER = signedInMe({
  permissions: ["contract.read", "masterdata.maintain", "import.upload"],
});
const READER = signedInMe({ permissions: ["contract.read"] });

describe("SF-15:customers", () => {
  it("customer drawer validates external id uniqueness", async () => {
    const bodies: unknown[] = [];
    serveCustomers([KLINIKBEDARF], [HOLLENBRAND]);
    server.use(
      http.post(apiUrl("/api/v1/customers"), async ({ request }) => {
        bodies.push(await request.json());
        return problemResponse("validation-failed", 422, "Validation failed", {
          detail: "One field is invalid.",
          errors: [
            {
              field: "external_id",
              rule_id: "REF-19-UNIQUE",
              message: "External id C-DE-3001 is already used by another NetSuite customer.",
            },
          ],
        });
      }),
    );
    renderApp("/settings/customers", { me: MAINTAINER, screenRoutes: SCREEN_ROUTES });
    await screen.findByTestId("SF-15-grid-customers");
    fireEvent.click(screen.getByRole("button", { name: "New customer" }));

    const dialog = await screen.findByRole("dialog", { name: /customer$/ });
    expect(within(dialog).getByTestId("SF-15-drawer-customer")).toBeTruthy();
    expect(
      within(dialog).getByText(
        "Customer records hold business identity only. Do not enter personal contact details.",
      ),
    ).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save customer" }));
    expect(await within(dialog).findByText("Enter the customer code.")).toBeTruthy();
    expect(within(dialog).getByText("Enter the customer name.")).toBeTruthy();
    expect(bodies).toEqual([]);

    fireEvent.change(within(dialog).getByLabelText(/^Code/), { target: { value: "CUST-0099" } });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), {
      target: { value: "Hollenbrand Labortechnik GmbH (Demo)" },
    });
    const externalId = within(dialog).getByLabelText(/^External id/);
    fireEvent.change(externalId, { target: { value: "C-DE-3001" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save customer" }));

    expect(
      await within(dialog).findByText(
        "External id C-DE-3001 is already used by another NetSuite customer.",
      ),
    ).toBeTruthy();
    expect(externalId.getAttribute("aria-invalid")).toBe("true");
    expect(bodies).toEqual([
      {
        code: "CUST-0099",
        name: "Hollenbrand Labortechnik GmbH (Demo)",
        related_party_group_id: null,
        parent_customer_id: null,
        credit_grade: null,
        segment: null,
        country_code: null,
        external_id: "C-DE-3001",
        source_system: "MANUAL_UI",
        is_active: true,
      },
    ]);
    // The drawer stays open with the typed values.
    expect((within(dialog).getByLabelText(/^Code/) as HTMLInputElement).value).toBe("CUST-0099");
  });

  // docs/dev-guide.md DG-FE-06 rev 1.228 (item KIT-UNPLACED-ERRORS-1): a refusal that names a member the
  // drawer has no field for is said in the banner; one that names a field stands at that field, once.
  it("a refusal of New customer says in the banner what no field of the drawer shows", async () => {
    serveCustomers([KLINIKBEDARF], [HOLLENBRAND]);
    server.use(
      http.post(apiUrl("/api/v1/customers"), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            {
              field: "external_id",
              rule_id: "REF-19-UNIQUE",
              message: "External id C-DE-3001 is already used by another NetSuite customer.",
            },
            {
              field: "source_system",
              rule_id: null,
              message: "A customer made here is of the source Manual.",
            },
          ],
        }),
      ),
    );
    renderApp("/settings/customers", { me: MAINTAINER, screenRoutes: SCREEN_ROUTES });
    await screen.findByTestId("SF-15-grid-customers");
    fireEvent.click(screen.getByRole("button", { name: "New customer" }));
    const dialog = await screen.findByRole("dialog", { name: /customer$/ });
    fireEvent.change(within(dialog).getByLabelText(/^Code/), { target: { value: "CUST-0099" } });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), {
      target: { value: "Hollenbrand Labortechnik GmbH (Demo)" },
    });
    fireEvent.change(within(dialog).getByLabelText(/^External id/), {
      target: { value: "C-DE-3001" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save customer" }));

    const banner = await within(dialog).findByRole("alert");
    expect(within(banner).getByText("A customer made here is of the source Manual.")).toBeTruthy();
    expect(
      within(dialog).getAllByText(
        "External id C-DE-3001 is already used by another NetSuite customer.",
      ),
    ).toHaveLength(1);
    expect(within(banner).queryByText(/^External id C-DE-3001/)).toBeNull();
    expect(
      within(dialog)
        .getByLabelText(/^External id/)
        .getAttribute("aria-invalid"),
    ).toBe("true");
  });

  it("the grid Customers shows the §9.4 columns, keys rows by external id and links the group drawer", async () => {
    serveCustomers([KLINIKBEDARF, MEDIZINTECHNIK, PELLWORTH], [HOLLENBRAND]);
    renderApp("/settings/customers", { me: READER, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-15-grid-customers")).findByRole(
      "grid",
      {
        name: "Customers",
      },
    );
    const headers = within(grid)
      .getAllByRole("columnheader")
      .map((header) => header.textContent?.trim() ?? "");
    for (const name of [
      "Customer",
      "Code",
      "Related-party group",
      "Country",
      "Segment",
      "Credit grade",
      "Source",
      "External id",
      "Active",
      "Updated",
    ]) {
      expect(headers.some((header) => header.startsWith(name))).toBe(true);
    }
    const row = await within(grid).findByTestId("SF-15-row-c-de-3001");
    expect(within(grid).getByRole("row", { name: /Hollenbrand Klinikbedarf/ })).toBe(row);
    expect(
      within(row)
        .getByRole("link", { name: "Hollenbrand Klinikbedarf GmbH (Demo)" })
        .getAttribute("href"),
    ).toBe(`/settings/customers/${KLINIKBEDARF.id}`);
    expect(within(row).getByText("CUST-0005")).toBeTruthy();
    expect(
      within(row)
        .getByRole("link", { name: groupLabel(HOLLENBRAND) })
        .getAttribute("href"),
    ).toBe(groupDrawerRoute(HOLLENBRAND.id));
    expect(within(row).getByText("DE")).toBeTruthy();
    expect(within(row).getByText("Healthcare")).toBeTruthy();
    expect(within(row).getByText("NetSuite")).toBeTruthy();
    expect(within(row).getByText("C-DE-3001")).toBeTruthy();
    expect(within(row).getByText("Yes")).toBeTruthy();
    expect(within(row).getByText("10 Sep 2026 08:00 UTC")).toBeTruthy();
    const pellworth = within(grid).getByTestId("SF-15-row-001demo0001");
    expect(within(pellworth).getByText("Salesforce")).toBeTruthy();
    expect(within(pellworth).getByText("A")).toBeTruthy();

    expect(screen.getByRole("searchbox", { name: "Search customers" })).toBeTruthy();
    expect(screen.getAllByText("3 customers").length).toBeGreaterThan(0);
    // A reader without masterdata.maintain gets no create action.
    expect(screen.queryByRole("button", { name: "New customer" })).toBeNull();

    const fields = customerFilterFields([HOLLENBRAND], false);
    expect(fields.map((field) => field.name)).toEqual(["group", "source", "external_id", "active"]);
    expect(
      customerQuery(
        `?q=holl&f.group=is:${HOLLENBRAND.id}&f.source=in:NETSUITE,SALESFORCE&f.external_id=is:C-DE-3001&f.active=is:true`,
        fields,
      ),
    ).toEqual({
      q: "holl",
      groupId: HOLLENBRAND.id,
      source: ["NETSUITE", "SALESFORCE"],
      externalId: "C-DE-3001",
      isActive: true,
    });
  });

  it("the empty state reads No customers yet with New customer and Import customers", async () => {
    serveCustomers([], []);
    renderApp("/settings/customers", { me: MAINTAINER, screenRoutes: SCREEN_ROUTES });

    const empty = await screen.findByTestId("SF-15-empty-customers");
    expect(within(empty).getByRole("heading", { name: "No customers yet" })).toBeTruthy();
    expect(
      within(empty).getByText(
        "Customers arrive with contracts from imports and integrations, or you can add one.",
      ),
    ).toBeTruthy();
    expect(within(empty).getByRole("button", { name: "New customer" })).toBeTruthy();
    expect(within(empty).getByRole("link", { name: "Import customers" }).getAttribute("href")).toBe(
      "/data/imports/new?template=customers",
    );
  });
});
