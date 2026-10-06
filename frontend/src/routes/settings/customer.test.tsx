// @vitest-environment jsdom
// SF-15:customer (BUILD_SPEC RFD-20; SCREENS §9): the C-05 page `h1` is the customer name with the code,
// the Active chip and the meta row (group, country, source NetSuite, external id C-DE-3001); the contracts
// panel reads "No contracts for this customer yet."; the related customers table lists the other group
// member; "Edit customer" patches with `If-Match`; an unknown id shows "Customer not found".
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { installMemoryStorage, preloadScreens, renderApp, signedInMe } from "../../test/app";
import {
  HOLLENBRAND,
  KLINIKBEDARF,
  MEDIZINTECHNIK,
  PELLWORTH,
  serveCustomers,
} from "../../test/customers";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, server } from "../../test/msw";

installMswServer();
installMemoryStorage();
installGridViewport();

// F-ADM Q21: the first test paid the customer record's module evaluation inside its findBy window.
beforeAll(() => preloadScreens(SCREEN_ROUTES, ["SF-15:customer"]));

afterEach(() => {
  cleanup();
});

const MAINTAINER = signedInMe({ permissions: ["contract.read", "masterdata.maintain"] });

describe("SF-15:customer", () => {
  it("the C-05 page shows the name, code, chip, meta row, empty contracts panel and related customers", async () => {
    serveCustomers([KLINIKBEDARF, MEDIZINTECHNIK, PELLWORTH], [HOLLENBRAND]);
    renderApp(`/settings/customers/${KLINIKBEDARF.id}`, {
      me: MAINTAINER,
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Hollenbrand Klinikbedarf GmbH (Demo)",
      }),
    ).toBeTruthy();
    expect(screen.getByTestId("SF-15-identifier").textContent).toContain("CUST-0005");
    expect(screen.getByRole("button", { name: "Copy customer code" })).toBeTruthy();
    expect(screen.getByText("Active")).toBeTruthy();
    expect(screen.getByRole("link", { name: "HOLLENBRAND" }).getAttribute("href")).toBe(
      `/settings/related-party-groups?drawer=group&row=${HOLLENBRAND.id}`,
    );
    expect(screen.getByText("NetSuite")).toBeTruthy();
    expect(screen.getByText("C-DE-3001")).toBeTruthy();
    expect(screen.getByText("Healthcare")).toBeTruthy();

    expect(await screen.findByText("No contracts for this customer yet.")).toBeTruthy();
    const related = await screen.findByRole("table", { name: "Related customers in HOLLENBRAND" });
    expect(
      within(related)
        .getByRole("link", { name: "Hollenbrand Medizintechnik GmbH (Demo)" })
        .getAttribute("href"),
    ).toBe(`/settings/customers/${MEDIZINTECHNIK.id}`);
    expect(within(related).getByText("CUST-0011")).toBeTruthy();
    expect(within(related).queryByText("Hollenbrand Klinikbedarf GmbH (Demo)")).toBeNull();
  });

  it("Edit customer patches the changed fields with If-Match", async () => {
    const patches: { readonly ifMatch: string | null; readonly body: unknown }[] = [];
    serveCustomers([KLINIKBEDARF, MEDIZINTECHNIK], [HOLLENBRAND]);
    server.use(
      http.patch(apiUrl(`/api/v1/customers/${KLINIKBEDARF.id}`), async ({ request }) => {
        patches.push({ ifMatch: request.headers.get("If-Match"), body: await request.json() });
        return HttpResponse.json({ ...KLINIKBEDARF, segment: "Hospitals", row_version: 4 });
      }),
    );
    renderApp(`/settings/customers/${KLINIKBEDARF.id}`, {
      me: MAINTAINER,
      screenRoutes: SCREEN_ROUTES,
    });

    fireEvent.click(await screen.findByRole("button", { name: "Edit customer" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit customer" });
    // An integration-created customer shows Source and External id read-only.
    expect((within(dialog).getByLabelText(/^Source/) as HTMLInputElement).readOnly).toBe(true);
    expect((within(dialog).getByLabelText(/^External id/) as HTMLInputElement).readOnly).toBe(true);
    fireEvent.change(within(dialog).getByLabelText(/^Segment/), { target: { value: "Hospitals" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save customer" }));

    expect(await screen.findByText("Saved customer CUST-0005.")).toBeTruthy();
    expect(patches).toEqual([{ ifMatch: '"r3"', body: { segment: "Hospitals" } }]);
  });

  it("an unknown customer shows Customer not found", async () => {
    serveCustomers([KLINIKBEDARF], [HOLLENBRAND]);
    renderApp("/settings/customers/00000000-0000-4000-8000-000000000000", {
      me: MAINTAINER,
      screenRoutes: SCREEN_ROUTES,
    });

    // The query client retries a failed read once before the 404 surfaces.
    const notFound = await screen.findByTestId("SF-15-customer-not-found", {}, { timeout: 4000 });
    expect(within(notFound).getByRole("heading", { name: "Customer not found" })).toBeTruthy();
    expect(within(notFound).getByRole("link", { name: "Customers" }).getAttribute("href")).toBe(
      "/settings/customers",
    );
  });
});
