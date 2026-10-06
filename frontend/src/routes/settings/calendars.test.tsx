// @vitest-environment jsdom
// SF-15:calendars (BUILD_SPEC RFD-18; SCREENS_B §9.3): the calendars listbox and `calendar=<code>`;
// the periods grid with one state column per entity × book; a `future` row's "Open <period> for
// <entity> <book>" calls `POST /periods/{id}/open` through `useCommand` with `If-Match`; the empty
// states "No calendars yet" and "No periods for <fiscal year>"; "Generate fiscal year".
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import {
  buildPeriodRows,
  type Calendar,
  canOpenCell,
  fiscalYearOf,
  fiscalYearOptions,
  fiscalYearParam,
  matrixColumnKey,
} from "../../lib/api/queries/calendars";
import type { Book, Entity, Period, PeriodState } from "../../lib/api/queries/tenant";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, server } from "../../test/msw";
import {
  describedBy,
  RECORD_CHANGED,
  REFUSAL_REFERENCE,
  REFUSAL_TITLE,
  refusedWith,
} from "../../test/refusals";
import { calendarSummary } from "./calendars";

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

const TOMAS = signedInMe({
  permissions: ["config.read", "masterdata.maintain", "period.close"],
});

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

const BOOKS: readonly Book[] = (
  [
    ["ASC606", "ASC 606", true],
    ["IFRS15", "IFRS 15", false],
    ["LEGACY", "Legacy", false],
  ] as const
).map(([code, name, primary]) => ({
  id: `b00b00b0-${code.toLowerCase().padEnd(4, "0")}-4000-8000-000000000000`,
  code,
  name,
  is_enabled: true,
  is_primary: primary,
  posting_target: primary ? "GL_PRIMARY" : "NONE",
  row_version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
}));

function entity(
  id: string,
  code: string,
  calendarId: string,
  books: readonly Book["code"][],
): Entity {
  return {
    id,
    code,
    name: code,
    country_code: "US",
    functional_currency: "USD",
    time_zone: "America/New_York",
    calendar_id: calendarId,
    parent_entity_id: null,
    tax_id: null,
    is_active: true,
    row_version: 1,
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
const US = entity("e1e1e1e1-e1e1-4e1e-8e1e-e1e1e1e1e1e1", "AVM-US", MONTHLY.id, ["ASC606"]);
const UK = entity("e2e2e2e2-e2e2-4e2e-8e2e-e2e2e2e2e2e2", "AVM-UK", MONTHLY.id, [
  "ASC606",
  "IFRS15",
]);
const JP = entity("e4e4e4e4-e4e4-4e4e-8e4e-e4e4e4e4e4e4", "AVM-JP", MONTHLY_AP.id, ["ASC606"]);

interface Spec {
  readonly key: string;
  readonly fiscalYear: number;
  readonly periodNo: number;
  readonly quarter: number;
  readonly start: string;
  readonly end: string;
}
const SEP: Spec = {
  key: "FY2026-P09",
  fiscalYear: 2026,
  periodNo: 9,
  quarter: 3,
  start: "2026-09-01",
  end: "2026-09-30",
};
const AUG: Spec = {
  key: "FY2026-P08",
  fiscalYear: 2026,
  periodNo: 8,
  quarter: 3,
  start: "2026-08-01",
  end: "2026-08-31",
};
const OCT: Spec = {
  key: "FY2026-P10",
  fiscalYear: 2026,
  periodNo: 10,
  quarter: 4,
  start: "2026-10-01",
  end: "2026-10-31",
};
const JP_SEP: Spec = {
  key: "FY2027-P06",
  fiscalYear: 2027,
  periodNo: 6,
  quarter: 2,
  start: "2026-09-01",
  end: "2026-09-30",
};

let sequence = 0;
function period(owner: Entity, book: Book["code"], spec: Spec, state: PeriodState): Period {
  sequence += 1;
  return {
    id: `${String(sequence).padStart(8, "0")}-0000-4000-8000-000000000000`,
    entity: { id: owner.id, code: owner.code, name: owner.name },
    book,
    period: {
      id: `${spec.key
        .toLowerCase()
        .replace(/[^a-z0-9]/g, "")
        .padEnd(8, "0")
        .slice(0, 8)}-0000-4000-8000-000000000000`,
      period_key: spec.key,
      name: spec.key,
      fiscal_year: spec.fiscalYear,
      period_no: spec.periodNo,
      quarter_no: spec.quarter,
      start_date: spec.start,
      end_date: spec.end,
    },
    state,
    state_changed_at: "2026-09-01T00:00:00Z",
    is_first_open: state === "open",
    current_lock: null,
    blockers: {
      exceptions_open: 0,
      holds_open: 0,
      unmapped_products: 0,
      judgements_unreviewed: 0,
      approvals_pending: 0,
      interface_failures: 0,
      jobs_failed: 0,
      groups_dirty: 0,
      batches_unexported: 0,
      batches_unacknowledged: 0,
      reconciliations_unsigned: 0,
      manual_adjustments_pending: 0,
    },
    close_run: null,
    row_version: 5,
  };
}

const PERIODS: readonly Period[] = [
  period(US, "ASC606", AUG, "closed"),
  period(US, "ASC606", SEP, "open"),
  period(US, "ASC606", OCT, "future"),
  period(UK, "ASC606", AUG, "closed"),
  period(UK, "ASC606", SEP, "open"),
  period(UK, "ASC606", OCT, "future"),
  period(UK, "IFRS15", AUG, "closed"),
  period(UK, "IFRS15", SEP, "open"),
  period(UK, "IFRS15", OCT, "future"),
  period(JP, "ASC606", JP_SEP, "open"),
];

function serve(calendars: readonly Calendar[], periods: readonly Period[]) {
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/saved-views"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), () =>
      HttpResponse.json({ items: [US, UK, JP], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/books"), () => HttpResponse.json({ items: BOOKS, next_cursor: null })),
    http.get(apiUrl("/api/v1/calendars"), () =>
      HttpResponse.json({ items: calendars, next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/periods"), ({ request }) => {
      const url = new URL(request.url);
      const fiscalYear = url.searchParams.get("fiscal_year");
      const entities = url.searchParams.getAll("entity");
      const items = periods.filter(
        (row) =>
          (fiscalYear === null || String(row.period.fiscal_year) === fiscalYear) &&
          (entities.length === 0 || entities.includes(row.entity.code)),
      );
      return HttpResponse.json({ items, next_cursor: null });
    }),
  );
}

/** `GET /tenant` of a workspace that is being set up; `reads` reports the requests served. */
function serveTenantInSetup(): { readonly reads: () => number } {
  let reads = 0;
  server.use(
    http.get(apiUrl("/api/v1/tenant"), () => {
      reads += 1;
      return HttpResponse.json({
        id: "0b6f3e2d-1c4a-4b8e-9d7f-6a5c4b3e2d1f",
        code: "avenmoor",
        display_name: "Avenmoor",
        setup_completed_at: null,
      });
    }),
  );
  return { reads: () => reads };
}

describe("SF-15:calendars", () => {
  it("open action names period entity and book", async () => {
    const opens: {
      readonly url: string;
      readonly ifMatch: string | null;
      readonly key: string | null;
    }[] = [];
    serve([MONTHLY, MONTHLY_AP], PERIODS);
    server.use(
      http.post(apiUrl("/api/v1/periods/:periodId/open"), ({ request, params }) => {
        opens.push({
          url: String(params.periodId),
          ifMatch: request.headers.get("If-Match"),
          key: request.headers.get("Idempotency-Key"),
        });
        const opened = PERIODS.find((row) => row.id === params.periodId);
        return HttpResponse.json({ ...opened, state: "open", row_version: 6 });
      }),
    );
    renderApp("/settings/calendars?calendar=MONTHLY&f.fiscal_year=is:2026", {
      me: TOMAS,
      screenRoutes: SCREEN_ROUTES,
    });

    const grid = await within(await screen.findByTestId("SF-15-grid-periods")).findByRole("grid", {
      name: "Periods",
    });
    const headers = within(grid)
      .getAllByRole("columnheader")
      .map((header) => header.textContent?.trim() ?? "");
    for (const name of [
      "Period",
      "Name",
      "Start",
      "End",
      "Quarter",
      "AVM-US ASC 606",
      "AVM-UK ASC 606",
      "AVM-UK IFRS 15",
    ]) {
      expect(headers.some((header) => header.startsWith(name))).toBe(true);
    }
    const sep = await within(grid).findByTestId("SF-15-row-fy2026-p09");
    expect(within(sep).getByRole("rowheader").textContent).toBe("FY2026-P09");
    expect(within(sep).getByText("Sep 2026")).toBeTruthy();
    expect(within(sep).getByText("01 Sep 2026")).toBeTruthy();
    expect(within(sep).getAllByText("Period open")).toHaveLength(3);
    expect(within(sep).queryByRole("button", { name: /^Open / })).toBeNull();
    const aug = within(grid).getByTestId("SF-15-row-fy2026-p08");
    expect(within(aug).getAllByText("Locked")).toHaveLength(3);

    const oct = within(grid).getByTestId("SF-15-row-fy2026-p10");
    expect(within(oct).getAllByText("Future")).toHaveLength(3);
    expect(
      within(oct).getByRole("group", { name: "AVM-US ASC 606 Oct 2026: Future" }),
    ).toBeTruthy();
    const open = within(oct).getByRole("button", { name: "Open Oct 2026 for AVM-US ASC 606" });
    fireEvent.click(open);
    const dialog = await screen.findByRole("alertdialog", {
      name: "Open Oct 2026 for AVM-US in book ASC 606?",
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Open period" }));
    expect(await screen.findByText("Oct 2026 is open for AVM-US ASC 606.")).toBeTruthy();
    const target = PERIODS.find(
      (row) => row.entity.code === "AVM-US" && row.period.period_key === "FY2026-P10",
    );
    expect(opens).toEqual([{ url: target?.id, ifMatch: '"r5"', key: expect.any(String) }]);
  });

  // SCREENS §0.6 SCR-PERM-02 (a) (rev 1.30; item W-12, slice c; 04 API-R-18): a period is opened for
  // one entity, and `period.close` is asked for that entity. A closer of AVM-UK is offered "Open" in
  // the AVM-UK columns of a future period and not in AVM-US's.
  it("Open is offered in the columns of the entities period.close is held for", async () => {
    serve([MONTHLY, MONTHLY_AP], PERIODS);
    renderApp("/settings/calendars?calendar=MONTHLY&f.fiscal_year=is:2026", {
      me: signedInMe({
        permissions: TOMAS.permissions,
        permission_scopes: {
          "config.read": "*",
          "masterdata.maintain": "*",
          "period.close": [UK.id],
        },
      }),
      screenRoutes: SCREEN_ROUTES,
    });

    const grid = await within(await screen.findByTestId("SF-15-grid-periods")).findByRole("grid", {
      name: "Periods",
    });
    const oct = await within(grid).findByTestId("SF-15-row-fy2026-p10");
    expect(within(oct).getAllByText("Future")).toHaveLength(3);
    expect(
      within(oct)
        .getAllByRole("button", { name: /^Open / })
        .map((button) => button.getAttribute("aria-label")),
    ).toEqual(["Open Oct 2026 for AVM-UK ASC 606", "Open Oct 2026 for AVM-UK IFRS 15"]);
  });

  // W-12e, the supervisor's ruling of 2026-10-02 02:43 (Q1; PRD ACT-44, BR-UX-06): the setup of the
  // workspace is the tenant's, so the setup branch of "Open" is offered to a holder of
  // `settings.manage` for all entities — who alone is told by `GET /tenant` that the workspace is
  // being set up (04 API-C-03).
  it("while the workspace is being set up, settings.manage for all entities opens a period of every entity", async () => {
    serve([MONTHLY, MONTHLY_AP], PERIODS);
    serveTenantInSetup();
    renderApp("/settings/calendars?calendar=MONTHLY&f.fiscal_year=is:2026", {
      me: signedInMe({ permissions: ["config.read", "settings.manage"] }),
      screenRoutes: SCREEN_ROUTES,
    });

    const grid = await within(await screen.findByTestId("SF-15-grid-periods")).findByRole("grid", {
      name: "Periods",
    });
    const oct = await within(grid).findByTestId("SF-15-row-fy2026-p10");
    expect(
      (await within(oct).findAllByRole("button", { name: /^Open / })).map((button) =>
        button.getAttribute("aria-label"),
      ),
    ).toEqual([
      "Open Oct 2026 for AVM-US ASC 606",
      "Open Oct 2026 for AVM-UK ASC 606",
      "Open Oct 2026 for AVM-UK IFRS 15",
    ]);
  });

  it("settings.manage for one entity alone: Open is not offered while the workspace is being set up, and the tenant is not asked for", async () => {
    serve([MONTHLY, MONTHLY_AP], PERIODS);
    const tenant = serveTenantInSetup();
    renderApp("/settings/calendars?calendar=MONTHLY&f.fiscal_year=is:2026", {
      me: signedInMe({
        permissions: ["config.read", "settings.manage"],
        permission_scopes: { "config.read": "*", "settings.manage": [US.id] },
      }),
      screenRoutes: SCREEN_ROUTES,
    });

    const grid = await within(await screen.findByTestId("SF-15-grid-periods")).findByRole("grid", {
      name: "Periods",
    });
    const oct = await within(grid).findByTestId("SF-15-row-fy2026-p10");
    // The periods are on screen, so a read of the tenant would have been sent and answered by now.
    expect(within(oct).getAllByText("Future")).toHaveLength(3);
    expect(within(oct).queryAllByRole("button", { name: /^Open / })).toEqual([]);
    expect(tenant.reads()).toBe(0);
  });

  it("the calendars listbox selects through calendar=<code>; AVM-JP's Sep 2026 is FY2027-P06", async () => {
    serve([MONTHLY, MONTHLY_AP], PERIODS);
    renderApp("/settings/calendars?calendar=MONTHLY-AP&f.fiscal_year=is:2027", {
      me: TOMAS,
      screenRoutes: SCREEN_ROUTES,
    });

    const list = await within(await screen.findByTestId("SF-15-calendars-list")).findByRole(
      "listbox",
      { name: "Calendars" },
    );
    const options = within(list).getAllByRole("option");
    expect(options.map((option) => option.getAttribute("aria-selected"))).toEqual([
      "false",
      "true",
    ]);
    expect(within(list).getByText("MONTHLY-AP")).toBeTruthy();
    expect(calendarSummary(MONTHLY_AP)).toBe("Monthly · April");

    const grid = await within(await screen.findByTestId("SF-15-grid-periods")).findByRole("grid", {
      name: "Periods",
    });
    const row = await within(grid).findByTestId("SF-15-row-fy2027-p06");
    expect(within(row).getByText("Sep 2026")).toBeTruthy();
    expect(
      within(grid)
        .getAllByRole("columnheader")
        .some((h) => h.textContent?.startsWith("AVM-JP ASC 606")),
    ).toBe(true);
    expect(within(grid).queryByText("AVM-US ASC 606")).toBeNull();

    // Pure helpers.
    expect(fiscalYearOf(MONTHLY_AP, { year: 2026, month: 9, day: 19 })).toBe(2027);
    expect(fiscalYearOf(MONTHLY_AP, { year: 2026, month: 3, day: 1 })).toBe(2026);
    expect(fiscalYearOf(MONTHLY, { year: 2026, month: 12, day: 31 })).toBe(2026);
    expect(fiscalYearOptions(2026, 2030)).toEqual([2024, 2025, 2026, 2027, 2028, 2030]);
    expect(fiscalYearParam("?calendar=X&f.fiscal_year=is:2027")).toBe(2027);
    expect(fiscalYearParam("?f.fiscal_year=in:2026,2027")).toBeNull();
    const rows = buildPeriodRows(PERIODS.filter((p) => p.period.fiscal_year === 2026));
    expect(rows.map((r) => r.key)).toEqual(["FY2026-P08", "FY2026-P09", "FY2026-P10"]);
    const us = matrixColumnKey("AVM-US", "ASC606");
    expect(canOpenCell(rows, 2, us)).toBe(true);
    expect(canOpenCell(rows, 1, us)).toBe(false);
    expect(canOpenCell(rows, 0, us)).toBe(false);
  });

  it("the empty state reads No calendars yet and New calendar posts the calendar", async () => {
    const bodies: unknown[] = [];
    serve([], []);
    server.use(
      http.post(apiUrl("/api/v1/calendars"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(
          {
            ...MONTHLY,
            id: "ca9ca9ca-ca9c-4ca9-8ca9-ca9ca9ca9ca9",
            code: "WEEKLY-445",
            pattern: "P445",
            week_end_day: 6,
            year_end_anchor: "LAST_WEEKDAY_OF_MONTH",
          },
          { status: 201 },
        );
      }),
    );
    renderApp("/settings/calendars", { me: TOMAS, screenRoutes: SCREEN_ROUTES });

    const empty = await screen.findByTestId("SF-15-empty-calendars");
    expect(within(empty).getByRole("heading", { name: "No calendars yet" })).toBeTruthy();
    expect(
      within(empty).getByText(
        "A calendar defines fiscal years and periods. Entities use one calendar each.",
      ),
    ).toBeTruthy();
    fireEvent.click(within(empty).getByRole("button", { name: "New calendar" }));

    const dialog = await screen.findByRole("dialog", { name: "New calendar" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create calendar" }));
    expect(await within(dialog).findByText("Enter the calendar code.")).toBeTruthy();
    expect(within(dialog).getByText("Choose the pattern.")).toBeTruthy();
    fireEvent.change(within(dialog).getByLabelText(/^Code/), { target: { value: "WEEKLY-445" } });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), { target: { value: "Retail 4-4-5" } });
    fireEvent.click(within(dialog).getByRole("combobox", { name: /^Pattern/ }));
    fireEvent.mouseDown(await screen.findByRole("option", { name: "4-4-5 weeks" }));
    fireEvent.click(within(dialog).getByRole("combobox", { name: /^Fiscal year starts in/ }));
    fireEvent.mouseDown(await screen.findByRole("option", { name: "February" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Create calendar" }));
    expect(await within(dialog).findByText("Choose the weekday on which weeks end.")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("combobox", { name: /^Week ends on/ }));
    fireEvent.mouseDown(await screen.findByRole("option", { name: "Saturday" }));
    fireEvent.click(within(dialog).getByRole("combobox", { name: /^Year-end anchor/ }));
    fireEvent.mouseDown(await screen.findByRole("option", { name: "Last weekday of the month" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Create calendar" }));

    expect(await screen.findByText("Created calendar WEEKLY-445.")).toBeTruthy();
    expect(bodies).toEqual([
      {
        code: "WEEKLY-445",
        name: "Retail 4-4-5",
        pattern: "P445",
        fiscal_year_start_month: 2,
        week_end_day: 6,
        year_end_anchor: "LAST_WEEKDAY_OF_MONTH",
      },
    ]);
  });

  it("without periods for the fiscal year the grid offers Generate fiscal year, which posts the year", async () => {
    const bodies: unknown[] = [];
    serve([MONTHLY], []);
    server.use(
      http.post(apiUrl(`/api/v1/calendars/${MONTHLY.id}/generate-year`), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({
          calendar_id: MONTHLY.id,
          fiscal_year: 2027,
          inserted_count: 12,
          periods: [],
        });
      }),
    );
    renderApp("/settings/calendars?calendar=MONTHLY&f.fiscal_year=is:2027", {
      me: TOMAS,
      screenRoutes: SCREEN_ROUTES,
    });

    const empty = await screen.findByTestId("SF-15-empty-periods");
    expect(within(empty).getByRole("heading", { name: "No periods for FY2027" })).toBeTruthy();
    expect(within(empty).getByText("Generate the fiscal year to create its periods.")).toBeTruthy();
    fireEvent.click(within(empty).getByRole("button", { name: "Generate fiscal year" }));

    const dialog = await screen.findByRole("dialog", { name: "Generate fiscal year" });
    const year = within(dialog).getByLabelText(/^Fiscal year/) as HTMLInputElement;
    expect(year.value).toBe("2027");
    expect(
      within(dialog).getByText(/AVM-JP's April 2026 to March 2027 year is FY2027\./),
    ).toBeTruthy();
    fireEvent.change(year, { target: { value: "27" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Generate fiscal year" }));
    expect(
      await within(dialog).findByText("Enter a fiscal year between 1900 and 2999."),
    ).toBeTruthy();
    fireEvent.change(year, { target: { value: "2027" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Generate fiscal year" }));

    expect(await screen.findByText("Generated 12 periods for FY2027.")).toBeTruthy();
    expect(bodies).toEqual([{ fiscal_year: 2027 }]);
  });
});

// docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): a message that names a member no
// field on screen sends was shown nowhere. The banner lists it, what a field shows is not said again,
// and after a 412 "Open period" says that the record changed (SCREENS SCR-ST-09), where it showed the
// API's problem.
describe("SF-15:calendars, a refused command", () => {
  it("New calendar: the banner lists what no field on screen shows", async () => {
    const notOnScreen = "A monthly calendar has no week end day.";
    const noField = "Choose a start month from 1 to 12.";
    const atCode = "A calendar with this code exists.";
    serve([], []);
    server.use(
      http.post(apiUrl("/api/v1/calendars"), () =>
        refusedWith({
          week_end_day: notOnScreen,
          fiscal_year_start_month: noField,
          code: atCode,
        }),
      ),
    );
    renderApp("/settings/calendars", { me: TOMAS, screenRoutes: SCREEN_ROUTES });
    const empty = await screen.findByTestId("SF-15-empty-calendars");
    fireEvent.click(within(empty).getByRole("button", { name: "New calendar" }));
    const dialog = await screen.findByRole("dialog", { name: "New calendar" });
    const code = within(dialog).getByLabelText(/^Code/);
    fireEvent.change(code, { target: { value: "MONTHLY-FEB" } });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), { target: { value: "Monthly" } });
    fireEvent.click(within(dialog).getByRole("combobox", { name: /^Pattern/ }));
    fireEvent.mouseDown(await screen.findByRole("option", { name: "Monthly" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Create calendar" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + notOnScreen + noField + REFUSAL_REFERENCE);
    expect(describedBy(code)).toContain(atCode);
  });

  it("Generate fiscal year: the banner lists what the year does not show", async () => {
    const noField = "The calendar has entities whose first period is later.";
    const atYear = "The periods of this fiscal year exist.";
    serve([MONTHLY], []);
    server.use(
      http.post(apiUrl(`/api/v1/calendars/${MONTHLY.id}/generate-year`), () =>
        refusedWith({ calendar_id: noField, fiscal_year: atYear }),
      ),
    );
    renderApp("/settings/calendars?calendar=MONTHLY&f.fiscal_year=is:2027", {
      me: TOMAS,
      screenRoutes: SCREEN_ROUTES,
    });
    const empty = await screen.findByTestId("SF-15-empty-periods");
    fireEvent.click(within(empty).getByRole("button", { name: "Generate fiscal year" }));
    const dialog = await screen.findByRole("dialog", { name: "Generate fiscal year" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Generate fiscal year" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + noField + REFUSAL_REFERENCE);
    expect(describedBy(within(dialog).getByLabelText(/^Fiscal year/))).toContain(atYear);
  });

  it("Open period says every sentence, and after a 412 that the record changed", async () => {
    const sentence = "An earlier period of this entity is not open yet.";
    let status = 422;
    serve([MONTHLY, MONTHLY_AP], PERIODS);
    server.use(
      http.post(apiUrl("/api/v1/periods/:periodId/open"), () =>
        refusedWith({ state: sentence }, { status }),
      ),
    );
    renderApp("/settings/calendars?calendar=MONTHLY&f.fiscal_year=is:2026", {
      me: TOMAS,
      screenRoutes: SCREEN_ROUTES,
    });
    const grid = await within(await screen.findByTestId("SF-15-grid-periods")).findByRole("grid", {
      name: "Periods",
    });
    const oct = await within(grid).findByTestId("SF-15-row-fy2026-p10");
    fireEvent.click(within(oct).getByRole("button", { name: "Open Oct 2026 for AVM-US ASC 606" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Open Oct 2026 for AVM-US in book ASC 606?",
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Open period" }));
    expect((await within(dialog).findByRole("alert")).textContent).toBe(
      REFUSAL_TITLE + sentence + REFUSAL_REFERENCE,
    );

    status = 412;
    fireEvent.click(within(dialog).getByRole("button", { name: "Open period" }));
    expect(await within(dialog).findByRole("heading", { name: RECORD_CHANGED })).toBeTruthy();
    expect(within(dialog).queryByRole("heading", { name: REFUSAL_TITLE })).toBeNull();
  });
});
