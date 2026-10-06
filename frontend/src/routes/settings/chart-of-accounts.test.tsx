// @vitest-environment jsdom
// SF-15:chart-of-accounts, the account drawer's refusals (docs/dev-guide.md DG-FE-06 rev 1.228; item
// KIT-UNPLACED-ERRORS-1): a refusal that names a member the drawer has no field for is said in the
// banner; one that names a field stands at that field, once. API answers are contract fakes of 04
// API-R-20.
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
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

const AUTHOR = signedInMe({ permissions: ["config.read", "config.author", "masterdata.maintain"] });

function serve(): unknown[] {
  const bodies: unknown[] = [];
  server.use(
    http.post(apiUrl("/api/v1/gl-accounts"), async ({ request }) => {
      bodies.push(await request.json());
      return problemResponse("validation-failed", 422, "Check the highlighted fields", {
        errors: [
          {
            field: "code",
            sheet: null,
            row: null,
            rule_id: null,
            message: "Account 41000 already exists.",
          },
          {
            field: "is_active",
            sheet: null,
            row: null,
            rule_id: null,
            message: "A new account starts active.",
          },
        ],
      });
    }),
    // The lists of the page and of the shell: empty.
    http.get(apiUrl("/api/v1/*"), () =>
      HttpResponse.json(
        { items: [], next_cursor: null },
        { headers: { "X-Erev-Total-Count": "0" } },
      ),
    ),
  );
  return bodies;
}

describe("SF-15:chart-of-accounts", () => {
  it("a refusal of New account says in the banner what no field of the drawer shows", async () => {
    const bodies = serve();
    renderApp("/settings/chart-of-accounts?drawer=new-account", {
      me: AUTHOR,
      screenRoutes: SCREEN_ROUTES,
    });
    const dialog = await screen.findByRole("dialog", { name: "New account" });
    fireEvent.change(within(dialog).getByLabelText(/^Code/), { target: { value: "41000" } });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), {
      target: { value: "Subscription revenue" },
    });
    for (const [field, option] of [
      ["Type", "Revenue"],
      ["Normal balance", "Credit"],
    ] as const) {
      const select = within(dialog).getByRole("combobox", { name: new RegExp(`^${field}`) });
      fireEvent.keyDown(select, { key: "ArrowDown" });
      fireEvent.mouseDown(await within(dialog).findByRole("option", { name: option }));
    }
    fireEvent.click(within(dialog).getByRole("button", { name: "Save account" }));

    const banner = await within(dialog).findByRole("alert");
    expect(bodies).toHaveLength(1);
    expect(within(banner).getByText("A new account starts active.")).toBeTruthy();
    expect(within(banner).queryByText("Account 41000 already exists.")).toBeNull();
    expect(within(dialog).getAllByText("Account 41000 already exists.")).toHaveLength(1);
    expect(within(dialog).getByLabelText(/^Code/).getAttribute("aria-invalid")).toBe("true");
  });

  it("a refusal of New dimension says in the banner what no field of the drawer shows", async () => {
    server.use(
      http.post(apiUrl("/api/v1/dimensions"), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            {
              field: "code",
              sheet: null,
              row: null,
              rule_id: null,
              message: "Dimension REGION already exists.",
            },
            {
              field: "value_type",
              sheet: null,
              row: null,
              rule_id: null,
              message: "A custom dimension holds text values.",
            },
          ],
        }),
      ),
    );
    serve();
    renderApp("/settings/chart-of-accounts?drawer=new-dimension", {
      me: AUTHOR,
      screenRoutes: SCREEN_ROUTES,
    });
    const dialog = await screen.findByRole("dialog", { name: "New dimension" });
    fireEvent.change(within(dialog).getByLabelText(/^Code/), { target: { value: "REGION" } });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), { target: { value: "Region" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save dimension" }));

    const banner = await within(dialog).findByRole("alert");
    expect(within(banner).getByText("A custom dimension holds text values.")).toBeTruthy();
    expect(within(banner).queryByText("Dimension REGION already exists.")).toBeNull();
    expect(within(dialog).getAllByText("Dimension REGION already exists.")).toHaveLength(1);
    expect(within(dialog).getByLabelText(/^Code/).getAttribute("aria-invalid")).toBe("true");
  });

  it("a refusal of Add value says in the banner what no field of the drawer shows", async () => {
    server.use(
      http.post(apiUrl("/api/v1/dimensions/REGION/values"), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            {
              field: "code",
              sheet: null,
              row: null,
              rule_id: null,
              message: "Value EMEA already exists.",
            },
            {
              field: "parent_code",
              sheet: null,
              row: null,
              rule_id: null,
              message: "A value of this dimension names its parent.",
            },
          ],
        }),
      ),
    );
    serve();
    renderApp("/settings/chart-of-accounts?drawer=dimension-values&row=REGION", {
      me: AUTHOR,
      screenRoutes: SCREEN_ROUTES,
    });
    const dialog = await screen.findByRole("dialog", { name: "Dimension values" });
    fireEvent.change(within(dialog).getByLabelText(/^Value code/), { target: { value: "EMEA" } });
    fireEvent.change(within(dialog).getByLabelText(/^Value name/), {
      target: { value: "Europe, Middle East and Africa" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add value" }));

    const banner = await within(dialog).findByRole("alert");
    expect(within(banner).getByText("A value of this dimension names its parent.")).toBeTruthy();
    expect(within(banner).queryByText("Value EMEA already exists.")).toBeNull();
    expect(within(dialog).getAllByText("Value EMEA already exists.")).toHaveLength(1);
    expect(
      within(dialog)
        .getByLabelText(/^Value code/)
        .getAttribute("aria-invalid"),
    ).toBe("true");
  });
});
