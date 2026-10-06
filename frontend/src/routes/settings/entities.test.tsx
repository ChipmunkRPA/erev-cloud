// @vitest-environment jsdom
// SF-15:entities (BUILD_SPEC RFD-18; SCREENS_B §9.2): the empty state reads "No entities yet" with the
// primary "New entity"; the grid "Entities" lists the sample world's codes with their functional
// currencies and time zones; "New entity" posts `POST /entities` and "Edit <code>" patches with `If-Match`
// and saves a changed book through `PUT /entities/{id}/books/{code}`.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import type { Calendar } from "../../lib/api/queries/calendars";
import type { TenantCurrency } from "../../lib/api/queries/currencies";
import { bookLabel, enabledBookLabels, entitiesUsing } from "../../lib/api/queries/entities";
import type { Book, Entity } from "../../lib/api/queries/tenant";
import { installMemoryStorage, preloadScreens, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";

installMswServer();
installMemoryStorage();
installGridViewport();

// F-ADM Q21: the first test paid the entities screen's module evaluation inside its findBy window.
beforeAll(() => preloadScreens(SCREEN_ROUTES, ["SF-15:entities"]));

afterEach(() => {
  cleanup();
});

const TOMAS = signedInMe({ permissions: ["config.read", "masterdata.maintain"] });
const READER = signedInMe({ permissions: ["config.read"] });

const MONTHLY: Calendar = {
  id: "ca1ca1ca-ca1c-4ca1-8ca1-ca1ca1ca1ca1",
  code: "MONTHLY",
  name: "Monthly, fiscal year starts January",
  pattern: "MONTHLY",
  fiscal_year_start_month: 1,
  week_end_day: null,
  year_end_anchor: null,
  row_version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};
const MONTHLY_AP: Calendar = {
  ...MONTHLY,
  id: "ca2ca2ca-ca2c-4ca2-8ca2-ca2ca2ca2ca2",
  code: "MONTHLY-AP",
  name: "Monthly, fiscal year starts April",
  fiscal_year_start_month: 4,
};

function book(code: Book["code"], name: string, primary: boolean): Book {
  return {
    id: `b00k${code.toLowerCase().padEnd(4, "0")}-0000-4000-8000-000000000000`.slice(0, 36),
    code,
    name,
    is_enabled: true,
    is_primary: primary,
    posting_target: primary ? "GL_PRIMARY" : "NONE",
    row_version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}
const BOOKS: readonly Book[] = [
  book("ASC606", "ASC 606", true),
  book("IFRS15", "IFRS 15", false),
  book("LEGACY", "Legacy", false),
];

function entity(
  id: string,
  code: string,
  name: string,
  country: string,
  currency: string,
  timeZone: string,
  calendarId: string,
  books: readonly Book["code"][],
): Entity {
  return {
    id,
    code,
    name,
    country_code: country,
    functional_currency: currency,
    time_zone: timeZone,
    calendar_id: calendarId,
    parent_entity_id: null,
    tax_id: null,
    is_active: true,
    row_version: 3,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    books: books.map((bookCode) => ({
      id: `${id.slice(0, 8)}-${bookCode.toLowerCase().padEnd(4, "0")}-4000-8000-000000000000`,
      entity_id: id,
      book_code: bookCode,
      is_enabled: true,
      first_period_id: "p1p1p1p1-p1p1-4p1p-8p1p-p1p1p1p1p1p1",
      first_period_key: "FY2026-P01",
      row_version: 1,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    })),
  };
}

const US = entity(
  "e1e1e1e1-e1e1-4e1e-8e1e-e1e1e1e1e1e1",
  "AVM-US",
  "Avenmoor Inc. (Demo)",
  "US",
  "USD",
  "America/New_York",
  MONTHLY.id,
  ["ASC606"],
);
const UK = entity(
  "e2e2e2e2-e2e2-4e2e-8e2e-e2e2e2e2e2e2",
  "AVM-UK",
  "Avenmoor UK Ltd (Demo)",
  "GB",
  "GBP",
  "Europe/London",
  MONTHLY.id,
  ["ASC606", "IFRS15"],
);
const JP = entity(
  "e4e4e4e4-e4e4-4e4e-8e4e-e4e4e4e4e4e4",
  "AVM-JP",
  "Avenmoor Media KK (Demo)",
  "JP",
  "JPY",
  "Asia/Tokyo",
  MONTHLY_AP.id,
  ["ASC606"],
);

const TENANT_CURRENCIES: readonly TenantCurrency[] = ["USD", "GBP", "EUR", "JPY"].map((code) => ({
  currency_code: code,
  name: code,
  minor_unit: code === "JPY" ? 0 : 2,
  is_enabled: true,
  is_reporting_currency: code === "USD",
  row_version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}));

function serve(entities: readonly Entity[]) {
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/periods"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/saved-views"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), ({ request }) =>
      HttpResponse.json(
        { items: entities, next_cursor: null },
        {
          headers:
            new URL(request.url).searchParams.get("count") === "true"
              ? { "X-Erev-Total-Count": String(entities.length) }
              : {},
        },
      ),
    ),
    http.get(apiUrl("/api/v1/books"), () => HttpResponse.json({ items: BOOKS, next_cursor: null })),
    http.get(apiUrl("/api/v1/calendars"), () =>
      HttpResponse.json({ items: [MONTHLY, MONTHLY_AP], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/tenant-currencies"), () =>
      HttpResponse.json({ items: TENANT_CURRENCIES, next_cursor: null }),
    ),
  );
}

describe("SF-15:entities", () => {
  it("renders the empty state", async () => {
    serve([]);
    renderApp("/settings/entities", { me: TOMAS, screenRoutes: SCREEN_ROUTES });

    const empty = await screen.findByTestId("SF-15-empty-entities");
    expect(within(empty).getByRole("heading", { name: "No entities yet" })).toBeTruthy();
    expect(
      within(empty).getByText(
        "An entity sets the functional currency, time zone, calendar and books for its contracts and postings.",
      ),
    ).toBeTruthy();
    expect(within(empty).getByRole("button", { name: "New entity" })).toBeTruthy();
  });

  it("the grid Entities lists the codes with their functional currencies, time zones, calendars and books", async () => {
    serve([US, UK, JP]);
    renderApp("/settings/entities", { me: TOMAS, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-15-grid-entities")).findByRole("grid", {
      name: "Entities",
    });
    const headers = within(grid)
      .getAllByRole("columnheader")
      .map((header) => header.textContent?.trim() ?? "");
    for (const name of [
      "Code",
      "Name",
      "Country",
      "Functional currency",
      "Time zone",
      "Calendar",
      "Parent entity",
      "Books",
      "Active",
    ]) {
      expect(headers.some((header) => header.startsWith(name))).toBe(true);
    }
    const us = await within(grid).findByTestId("SF-15-row-avm-us");
    expect(within(us).getByRole("rowheader").textContent).toBe("AVM-US");
    expect(within(us).getByText("USD")).toBeTruthy();
    expect(within(us).getByText("America/New_York")).toBeTruthy();
    expect(within(us).getByText("ASC 606")).toBeTruthy();
    expect(within(us).getByText("Yes")).toBeTruthy();
    const uk = within(grid).getByTestId("SF-15-row-avm-uk");
    expect(within(uk).getByText("ASC 606, IFRS 15")).toBeTruthy();
    const jp = within(grid).getByTestId("SF-15-row-avm-jp");
    expect(within(jp).getByText("MONTHLY-AP")).toBeTruthy();
    expect(within(jp).getByText("JPY")).toBeTruthy();
    // The calendar code links SF-15:calendars with the calendar selected (SCREENS_B §9.2 drill).
    expect(within(jp).getByRole("link", { name: "MONTHLY-AP" }).getAttribute("href")).toBe(
      "/settings/calendars?calendar=MONTHLY-AP",
    );
    // The count shows under the title and in the grid toolbar.
    expect(screen.getAllByText("3 entities").length).toBeGreaterThan(0);

    expect(enabledBookLabels(UK, BOOKS)).toEqual(["ASC 606", "IFRS 15"]);
    expect(bookLabel("LEGACY")).toBe("Legacy");
    expect(entitiesUsing([US, UK, JP], "GBP")).toEqual(["AVM-UK"]);
  });

  it("New entity posts the entity and reopens the drawer on the created entity", async () => {
    const bodies: unknown[] = [];
    serve([US]);
    server.use(
      http.post(apiUrl("/api/v1/entities"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(
          { ...UK, id: "e9e9e9e9-e9e9-4e9e-8e9e-e9e9e9e9e9e9", code: "AVM-DE" },
          { status: 201 },
        );
      }),
    );
    const { router } = renderApp("/settings/entities", { me: TOMAS, screenRoutes: SCREEN_ROUTES });
    await screen.findByTestId("SF-15-grid-entities");
    fireEvent.click(screen.getByRole("button", { name: "New entity" }));

    const dialog = await screen.findByRole("dialog", { name: "New entity" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save entity" }));
    expect(await within(dialog).findByText("Enter the entity code.")).toBeTruthy();
    expect(within(dialog).getByText("Enter the entity name.")).toBeTruthy();
    expect(within(dialog).getByText("Choose the functional currency.")).toBeTruthy();
    expect(within(dialog).getByText("Choose the time zone.")).toBeTruthy();
    expect(within(dialog).getByText("Choose the calendar.")).toBeTruthy();
    expect(bodies).toEqual([]);

    fireEvent.change(within(dialog).getByLabelText(/^Code/), { target: { value: "avm de" } });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), {
      target: { value: "Avenmoor Devices GmbH (Demo)" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save entity" }));
    expect(await within(dialog).findByText("Use letters, digits and hyphens.")).toBeTruthy();
    fireEvent.change(within(dialog).getByLabelText(/^Code/), { target: { value: "AVM-DE" } });

    fireEvent.click(within(dialog).getByRole("combobox", { name: /^Functional currency/ }));
    fireEvent.mouseDown(await screen.findByRole("option", { name: "EUR" }));
    const zone = within(dialog).getByRole("combobox", { name: /^Time zone/ });
    fireEvent.change(zone, { target: { value: "Europe/Berlin" } });
    fireEvent.mouseDown(await screen.findByRole("option", { name: "Europe/Berlin" }));
    fireEvent.click(within(dialog).getByRole("combobox", { name: /^Calendar/ }));
    fireEvent.mouseDown(
      await screen.findByRole("option", { name: "MONTHLY · Monthly, fiscal year starts January" }),
    );
    fireEvent.change(within(dialog).getByLabelText(/^First period \(ASC 606\)/), {
      target: { value: "FY2026-P01" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save entity" }));

    expect(await screen.findByText("Saved entity AVM-DE.")).toBeTruthy();
    expect(bodies).toEqual([
      {
        code: "AVM-DE",
        name: "Avenmoor Devices GmbH (Demo)",
        country_code: null,
        functional_currency: "EUR",
        time_zone: "Europe/Berlin",
        calendar_id: MONTHLY.id,
        parent_entity_id: null,
        tax_id: null,
        is_active: true,
        first_period_key: "FY2026-P01",
      },
    ]);
    await waitFor(() =>
      expect(router.state.location.search).toBe(
        "?drawer=entity&row=e9e9e9e9-e9e9-4e9e-8e9e-e9e9e9e9e9e9",
      ),
    );
  });

  it("Edit <code> patches the changed fields with If-Match and saves a changed book", async () => {
    const patches: { readonly ifMatch: string | null; readonly body: unknown }[] = [];
    const bookPuts: { readonly url: string; readonly body: unknown }[] = [];
    serve([US, UK]);
    server.use(
      http.patch(apiUrl(`/api/v1/entities/${UK.id}`), async ({ request }) => {
        patches.push({ ifMatch: request.headers.get("If-Match"), body: await request.json() });
        return HttpResponse.json({ ...UK, name: "Avenmoor UK Limited", row_version: 4 });
      }),
      http.put(apiUrl(`/api/v1/entities/${UK.id}/books/LEGACY`), async ({ request }) => {
        bookPuts.push({ url: new URL(request.url).pathname, body: await request.json() });
        return HttpResponse.json({
          id: "bkbkbkbk-bkbk-4bkb-8bkb-bkbkbkbkbkbk",
          entity_id: UK.id,
          book_code: "LEGACY",
          is_enabled: true,
          first_period_id: "p2p2p2p2-p2p2-4p2p-8p2p-p2p2p2p2p2p2",
          first_period_key: "FY2026-P07",
          row_version: 1,
          created_at: "2026-09-19T10:00:00Z",
          updated_at: "2026-09-19T10:00:00Z",
        });
      }),
    );
    renderApp(`/settings/entities?drawer=entity&row=${UK.id}`, {
      me: TOMAS,
      screenRoutes: SCREEN_ROUTES,
    });

    const dialog = await screen.findByRole("dialog", { name: "Edit AVM-UK" });
    expect((within(dialog).getByLabelText(/^Code/) as HTMLInputElement).readOnly).toBe(true);
    fireEvent.change(within(dialog).getByLabelText(/^Name/), {
      target: { value: "Avenmoor UK Limited" },
    });
    const legacy = within(dialog).getByTestId("SF-15-book-LEGACY");
    fireEvent.click(within(legacy).getByRole("checkbox", { name: "Legacy" }));
    fireEvent.change(within(legacy).getByLabelText(/^First period \(Legacy\)/), {
      target: { value: "FY2026-P07" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save entity" }));

    expect(await screen.findByText("Saved entity AVM-UK.")).toBeTruthy();
    expect(patches).toEqual([{ ifMatch: '"r3"', body: { name: "Avenmoor UK Limited" } }]);
    expect(bookPuts).toEqual([
      {
        url: `/api/v1/entities/${UK.id}/books/LEGACY`,
        body: { is_enabled: true, first_period_key: "FY2026-P07" },
      },
    ]);
  });

  // SCREENS §0.7 SCR-ST-13, DG-FE-06 rev 1.228 (item KIT-UNPLACED-ERRORS-1): the drawer showed its
  // banner only while the problem carried no field errors at all, and no field read the first
  // period's message, so an entity refused for its first period was refused without a word.
  it("a refusal of New entity stands at the first period it names, and in the banner for a member without a field", async () => {
    serve([US]);
    server.use(
      http.post(apiUrl("/api/v1/entities"), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            {
              field: "first_period_key",
              sheet: null,
              row: null,
              rule_id: null,
              message: "Calendar MONTHLY has no period FY2026-P13.",
            },
            {
              field: "is_active",
              sheet: null,
              row: null,
              rule_id: null,
              message: "A new entity starts active.",
            },
          ],
        }),
      ),
    );
    renderApp("/settings/entities", { me: TOMAS, screenRoutes: SCREEN_ROUTES });
    await screen.findByTestId("SF-15-grid-entities");
    fireEvent.click(screen.getByRole("button", { name: "New entity" }));

    const dialog = await screen.findByRole("dialog", { name: "New entity" });
    fireEvent.change(within(dialog).getByLabelText(/^Code/), { target: { value: "AVM-DE" } });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), {
      target: { value: "Avenmoor Devices GmbH (Demo)" },
    });
    fireEvent.click(within(dialog).getByRole("combobox", { name: /^Functional currency/ }));
    fireEvent.mouseDown(await screen.findByRole("option", { name: "EUR" }));
    const zone = within(dialog).getByRole("combobox", { name: /^Time zone/ });
    fireEvent.change(zone, { target: { value: "Europe/Berlin" } });
    fireEvent.mouseDown(await screen.findByRole("option", { name: "Europe/Berlin" }));
    fireEvent.click(within(dialog).getByRole("combobox", { name: /^Calendar/ }));
    fireEvent.mouseDown(
      await screen.findByRole("option", { name: "MONTHLY · Monthly, fiscal year starts January" }),
    );
    const firstPeriod = within(dialog).getByLabelText(/^First period \(ASC 606\)/);
    fireEvent.change(firstPeriod, { target: { value: "FY2026-P13" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save entity" }));

    const banner = await within(dialog).findByRole("alert");
    expect(within(banner).getByText("A new entity starts active.")).toBeTruthy();
    expect(within(banner).queryByText("Calendar MONTHLY has no period FY2026-P13.")).toBeNull();
    const row = within(dialog).getByTestId("SF-15-book-ASC606");
    expect(within(row).getByText("Calendar MONTHLY has no period FY2026-P13.")).toBeTruthy();
    expect(within(dialog).getAllByText("Calendar MONTHLY has no period FY2026-P13.")).toHaveLength(
      1,
    );
    expect(firstPeriod.getAttribute("aria-invalid")).toBe("true");

    // The message describes the value that was sent: it leaves when that value is edited.
    fireEvent.change(firstPeriod, { target: { value: "FY2026-P12" } });
    expect(within(dialog).queryByText("Calendar MONTHLY has no period FY2026-P13.")).toBeNull();
    expect(within(dialog).getByText("A new entity starts active.")).toBeTruthy();
  });

  it("a book that is switched off and refused says why in the banner", async () => {
    serve([US, UK]);
    server.use(
      http.put(apiUrl(`/api/v1/entities/${UK.id}/books/IFRS15`), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            {
              field: "is_enabled",
              sheet: null,
              row: null,
              rule_id: null,
              message: "IFRS 15 holds posted entries of AVM-UK and stays enabled.",
            },
          ],
        }),
      ),
    );
    renderApp(`/settings/entities?drawer=entity&row=${UK.id}`, {
      me: TOMAS,
      screenRoutes: SCREEN_ROUTES,
    });

    const dialog = await screen.findByRole("dialog", { name: "Edit AVM-UK" });
    const ifrs = within(dialog).getByTestId("SF-15-book-IFRS15");
    fireEvent.click(within(ifrs).getByRole("checkbox", { name: "IFRS 15" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save entity" }));

    const banner = await within(dialog).findByRole("alert");
    expect(
      within(banner).getByText("IFRS 15 holds posted entries of AVM-UK and stays enabled."),
    ).toBeTruthy();
  });

  it("a config.read holder without a maintain permission sees the grid read-only", async () => {
    serve([US]);
    renderApp("/settings/entities", { me: READER, screenRoutes: SCREEN_ROUTES });

    await within(await screen.findByTestId("SF-15-grid-entities")).findByRole("grid", {
      name: "Entities",
    });
    expect(screen.queryByRole("button", { name: "New entity" })).toBeNull();
    fireEvent.click(screen.getByRole("link", { name: "AVM-US" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit AVM-US" });
    expect(within(dialog).queryByRole("button", { name: "Save entity" })).toBeNull();
    expect((within(dialog).getByLabelText(/^Name/) as HTMLInputElement).readOnly).toBe(true);
  });
});
