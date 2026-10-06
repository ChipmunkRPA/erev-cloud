// @vitest-environment jsdom
// SF-15:related-party-groups (BUILD_SPEC RFD-20; SCREENS §9): the grid "Related-party groups" lists
// HOLLENBRAND with 2 members; `?drawer=group&row=<id>` opens "Edit group" with the read-only members list
// and the note; "New group" posts the group; the empty state reads "No related-party groups".
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
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

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

const MAINTAINER = signedInMe({ permissions: ["contract.read", "masterdata.maintain"] });

describe("SF-15:related-party-groups", () => {
  it("the grid Related-party groups lists HOLLENBRAND with 2 members and the drawer shows its members", async () => {
    serveCustomers([KLINIKBEDARF, MEDIZINTECHNIK, PELLWORTH], [HOLLENBRAND]);
    renderApp(`/settings/related-party-groups?drawer=group&row=${HOLLENBRAND.id}`, {
      me: MAINTAINER,
      screenRoutes: SCREEN_ROUTES,
    });

    const grid = await within(
      await screen.findByTestId("SF-15-grid-related-party-groups"),
    ).findByRole("grid", { name: "Related-party groups" });
    const headers = within(grid)
      .getAllByRole("columnheader")
      .map((header) => header.textContent?.trim() ?? "");
    for (const name of ["Group", "Name", "Description", "Members", "Updated"]) {
      expect(headers.some((header) => header.startsWith(name))).toBe(true);
    }
    const row = await within(grid).findByTestId("SF-15-row-hollenbrand");
    expect(within(row).getByRole("link", { name: "HOLLENBRAND" }).getAttribute("href")).toBe(
      `/settings/related-party-groups?drawer=group&row=${HOLLENBRAND.id}`,
    );
    expect(within(row).getByText("Hollenbrand group")).toBeTruthy();
    expect(within(row).getByText("2")).toBeTruthy();

    const dialog = await screen.findByRole("dialog", { name: "Edit group" });
    expect((within(dialog).getByLabelText(/^Code/) as HTMLInputElement).value).toBe("HOLLENBRAND");
    const members = await within(dialog).findByRole("region", { name: "Members" });
    expect(
      within(members)
        .getByRole("link", { name: "Hollenbrand Klinikbedarf GmbH (Demo)" })
        .getAttribute("href"),
    ).toBe(`/settings/customers/${KLINIKBEDARF.id}`);
    expect(
      within(members).getByRole("link", { name: "Hollenbrand Medizintechnik GmbH (Demo)" }),
    ).toBeTruthy();
    expect(
      within(members).getByText("Add a customer to this group from the customer's page."),
    ).toBeTruthy();
  });

  it("New group posts the group; the empty state reads No related-party groups", async () => {
    const bodies: unknown[] = [];
    serveCustomers([PELLWORTH], []);
    server.use(
      http.post(apiUrl("/api/v1/related-party-groups"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ ...HOLLENBRAND, member_count: 0 }, { status: 201 });
      }),
    );
    renderApp("/settings/related-party-groups", { me: MAINTAINER, screenRoutes: SCREEN_ROUTES });

    const empty = await screen.findByTestId("SF-15-empty-related-party-groups");
    expect(within(empty).getByRole("heading", { name: "No related-party groups" })).toBeTruthy();
    expect(
      within(empty).getByText(
        "Group customers under common control so combination suggestions and disclosures can find them.",
      ),
    ).toBeTruthy();
    fireEvent.click(within(empty).getByRole("button", { name: "New group" }));

    const dialog = await screen.findByRole("dialog", { name: "New group" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save group" }));
    expect(await within(dialog).findByText("Enter the group code.")).toBeTruthy();
    expect(within(dialog).getByText("Enter the group name.")).toBeTruthy();
    fireEvent.change(within(dialog).getByLabelText(/^Code/), { target: { value: "HOLLENBRAND" } });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), {
      target: { value: "Hollenbrand group" },
    });
    fireEvent.change(within(dialog).getByLabelText(/^Description/), {
      target: { value: "Common control." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save group" }));

    expect(await screen.findByText("Saved group HOLLENBRAND.")).toBeTruthy();
    expect(bodies).toEqual([
      { code: "HOLLENBRAND", name: "Hollenbrand group", description: "Common control." },
    ]);
  });
  // docs/dev-guide.md DG-FE-06 rev 1.228 (item KIT-UNPLACED-ERRORS-1): a refusal that names a member the
  // drawer has no field for is said in the banner; one that names a field stands at that field, once.
  it("a refusal of New group says in the banner what no field of the drawer shows", async () => {
    serveCustomers([PELLWORTH], []);
    server.use(
      http.post(apiUrl("/api/v1/related-party-groups"), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            {
              field: "code",
              sheet: null,
              row: null,
              rule_id: null,
              message: "Use letters, digits and hyphens.",
            },
            {
              field: "member_ids",
              sheet: null,
              row: null,
              rule_id: null,
              message: "A group names at least two customers.",
            },
          ],
        }),
      ),
    );
    renderApp("/settings/related-party-groups", { me: MAINTAINER, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(
      within(await screen.findByTestId("SF-15-empty-related-party-groups")).getByRole("button", {
        name: "New group",
      }),
    );
    const dialog = await screen.findByRole("dialog", { name: "New group" });
    fireEvent.change(within(dialog).getByLabelText(/^Code/), { target: { value: "HOLLEN BRAND" } });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), {
      target: { value: "Hollenbrand group" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save group" }));

    const banner = await within(dialog).findByRole("alert");
    expect(within(banner).getByText("A group names at least two customers.")).toBeTruthy();
    expect(within(banner).queryByText("Use letters, digits and hyphens.")).toBeNull();
    expect(within(dialog).getAllByText("Use letters, digits and hyphens.")).toHaveLength(1);
    expect(within(dialog).getByLabelText(/^Code/).getAttribute("aria-invalid")).toBe("true");
  });
});
