// @vitest-environment jsdom
// The context of a report view (item RPT-VIEW-CONTEXT-DEFAULT-1; SCREENS §0.5 SCR-URL-01 rev 1.61,
// SCR-URL-20; SCREENS_B §0.5 "The context of a view", §4.1, §5.2 rev 1.92; PRD BR-UX-01) on SF-08:report
// and SF-04: an address that names an entity is that entity's; `entities=all` says every entity in
// scope and fills nothing; any other address takes the context pill's — entity, book and period, each
// filled only where the address leaves it out — written before a run is asked. API answers are
// contract fakes of 04 API-R-17, API-R-18, API-R-35, API-R-41 and API-R-44 (V-C).
import { cleanup, configure, fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../../app/router";
import { contextStorageKey } from "../../../app/shell/ContextPill";
import type { ReportDefinition, ReportRow, ReportRun } from "../../../lib/api/queries/reports";
import type { Entity, Period } from "../../../lib/api/queries/tenant";
import { installMemoryStorage, renderApp, signedInMe } from "../../../test/app";
import { installGridViewport } from "../../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";

installMswServer();
installMemoryStorage();
installGridViewport();
// The screen reads the entities, the books and a calendar before its view is mounted.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
});

const ROBERT = signedInMe({
  permissions: ["contract.read", "config.read", "report.run", "report.export"],
});

const JOB_ID = "8e7d6c5b-4a3f-4e2d-9c1b-0a9f8e7d6c5b";
const JANUARY = "c0000000-0000-4000-8000-000000000001";
const APRIL = "c0000000-0000-4000-8000-000000000004";
/** The run of the `round`th creation. */
function runId(round = 1): string {
  return `5b0c7a1e-3d2f-4e6a-9b8c-7d6e5f4a3b0${String(round)}`;
}
/** Runs that were stored before the view opened. */
const STORED_RUN = "5b0c7a1e-3d2f-4e6a-9b8c-7d6e5f4a3bff";
const OTHER_STORED_RUN = "5b0c7a1e-3d2f-4e6a-9b8c-7d6e5f4a3bfe";

function money(amount: string, currency = "USD") {
  return { amount, currency };
}

const WATERFALL: ReportDefinition = {
  code: "revenue_waterfall",
  version: 1,
  name: "Revenue waterfall",
  kind: "STANDARD",
  description: "Recognized, scheduled and awaiting-trigger revenue by period over a range.",
  parameters_schema: {
    type: "object",
    additionalProperties: false,
    properties: {
      entity_codes: { type: "array" },
      book: { type: "string", enum: ["ASC606", "IFRS15", "LEGACY"] },
      from_period_key: { type: "string" },
      to_period_key: { type: "string" },
      as_of: { type: "string", format: "date" },
      known_at: { type: "string", format: "date-time" },
      period_lock_id: { type: "string", format: "uuid" },
      row_dimension: {
        type: "string",
        enum: ["CONTRACT", "OBLIGATION", "PRODUCT", "REVENUE_CATEGORY"],
      },
      granularity: { type: "string", enum: ["MONTH", "QUARTER", "YEAR"] },
      measure: { type: "string", enum: ["TOTAL", "BY_STATE"] },
      contract_external_id: { type: "string" },
      currency_view: { type: "string", enum: ["transaction", "functional", "reporting"] },
    },
  },
  output_formats: ["XLSX", "CSV", "JSON"],
  tie_outs: [],
  ipe_logic: null,
};

function entity(code: string, calendar: string, currency: string): Entity {
  return {
    id: `e0000000-0000-4000-8000-0000000000${code.slice(-2).toLowerCase()}`,
    code,
    name: `Avenmoor ${code}`,
    calendar_id: calendar,
    functional_currency: currency,
    country_code: null,
    tax_id: null,
    time_zone: "UTC",
    parent_entity_id: null,
    is_active: true,
    row_version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    books: [{ book_code: "ASC606", is_enabled: true }],
  } as unknown as Entity;
}

// The demo's shape: the first entity in code order is not the one a member last worked in, and one
// entity keeps an April year, so a period key names another month there.
const AVM_DE = entity("AVM-DE", JANUARY, "EUR");
const AVM_JP = entity("AVM-JP", APRIL, "JPY");
const AVM_US = entity("AVM-US", JANUARY, "USD");
const ENTITIES: readonly Entity[] = [AVM_US, AVM_JP, AVM_DE];

function period(
  of: Entity,
  fiscalYear: number,
  number: number,
  name: string,
  start: string,
  end: string,
  state: string,
): Period {
  const key = `FY${String(fiscalYear)}-P${String(number).padStart(2, "0")}`;
  const tail = `${of.code.slice(-2).toLowerCase()}${String(number).padStart(2, "0")}`;
  return {
    id: `1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d${tail}`,
    entity: { id: of.id, code: of.code, name: of.name },
    book: "ASC606",
    period: {
      id: `2c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d${tail}`,
      period_key: key,
      name,
      fiscal_year: fiscalYear,
      period_no: number,
      quarter_no: Math.floor((number - 1) / 3) + 1,
      start_date: start,
      end_date: end,
    },
    state,
    is_first_open: state === "open",
    row_version: 1,
    state_changed_at: "2026-09-03T09:14:00Z",
    close_run: null,
    current_lock: null,
    follows: null,
    blockers: {},
  } as unknown as Period;
}

/** August in soft close, September open, October to come; September is P09, and P06 of an April year. */
function calendarOf(of: Entity): readonly Period[] {
  const [year, first] = of.calendar_id === APRIL ? [2027, 5] : [2026, 8];
  return [
    period(of, year, first, "Aug 2026", "2026-08-01", "2026-08-31", "closing"),
    period(of, year, first + 1, "Sep 2026", "2026-09-01", "2026-09-30", "open"),
    period(of, year, first + 2, "Oct 2026", "2026-10-01", "2026-10-31", "future"),
  ];
}

function reportRun(id: string): ReportRun {
  return {
    id,
    report_run_no: `RPT-0004${id.slice(-2)}`,
    report: { code: "revenue_waterfall", version: 1, name: "Revenue waterfall" },
    status: "SUCCEEDED",
    parameters: {},
    entity_scope: [{ id: AVM_US.id, code: "AVM-US", name: AVM_US.name }],
    book: "ASC606",
    as_of: "2026-09-30",
    known_at: "2026-09-12T16:02:00Z",
    period_lock_id: null,
    engine_release: { engine_version: "1.0.0", build_sha: "3f9a1c22" },
    row_count: 1,
    control_totals: {},
    tie_out_results: [],
    ledger_heads: {},
    output: null,
    problem: null,
    job_id: null,
    sources: [],
    run_by: {
      id: "7d6c5b4a-3f2e-4d1c-8b0a-9f8e7d6c5b4a",
      display_name: "Robert Ames",
      kind: "USER",
    },
    started_at: "2026-09-12T16:02:11Z",
    finished_at: "2026-09-12T16:02:19Z",
  } as unknown as ReportRun;
}

const ROWS = [
  {
    row_key: "contract:SF-ORD-10001",
    contract_external_id: "SF-ORD-10001",
    customer_name: "Marrowby Health",
    entity_code: "AVM-US",
    "period:FY2026-P09": money("9764.38"),
    awaiting_trigger: money("0.00"),
    total: money("9764.38"),
  },
  {
    row_key: "TOTAL:USD",
    contract_external_id: null,
    customer_name: null,
    entity_code: null,
    "period:FY2026-P09": money("9764.38"),
    awaiting_trigger: money("0.00"),
    total: money("9764.38"),
  },
] as unknown as readonly ReportRow[];

interface World {
  readonly entities?: readonly Entity[];
  /** `GET /entities` answers 500 twice — the read and the one retry the client makes — then as usual. */
  readonly entitiesFail?: boolean;
}

interface Served {
  /** The `parameters` of each `POST /report-runs`, in order. */
  readonly asked: Record<string, unknown>[];
  /** The search of each `GET /schedule-lines`. */
  readonly lineReads: URLSearchParams[];
}

function serve(world: World = {}): Served {
  const asked: Record<string, unknown>[] = [];
  const lineReads: URLSearchParams[] = [];
  const entities = world.entities ?? ENTITIES;
  let failures = world.entitiesFail === true ? 2 : 0;
  const list = (items: readonly unknown[]) => HttpResponse.json({ items, next_cursor: null });
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () => list([])),
    http.get(apiUrl("/api/v1/jobs"), () => list([])),
    http.get(apiUrl("/api/v1/entities"), () => {
      if (failures > 0) {
        failures -= 1;
        return problemResponse(null, 500, "Internal Server Error");
      }
      return list(entities);
    }),
    http.get(apiUrl("/api/v1/books"), () =>
      list([
        { id: "b1", code: "ASC606", name: "ASC 606", is_primary: true, is_enabled: true },
        { id: "b2", code: "LEGACY", name: "Legacy", is_primary: false, is_enabled: true },
      ]),
    ),
    http.get(apiUrl("/api/v1/periods"), ({ request }) => {
      const code = new URL(request.url).searchParams.get("entity");
      const found = entities.find((item) => item.code === code);
      return list(found === undefined ? [] : calendarOf(found));
    }),
    http.get(apiUrl("/api/v1/currencies"), () =>
      list(
        ["USD", "EUR", "JPY"].map((code) => ({
          code,
          name: code,
          minor_unit: code === "JPY" ? 0 : 2,
          numeric_code: "000",
          is_active: true,
        })),
      ),
    ),
    http.get(apiUrl("/api/v1/report-definitions/:code"), () => HttpResponse.json(WATERFALL)),
    http.get(apiUrl("/api/v1/report-runs/:runId"), ({ params }) =>
      HttpResponse.json(reportRun(String(params.runId))),
    ),
    http.get(apiUrl("/api/v1/report-runs/:runId/data"), () =>
      HttpResponse.json({ items: ROWS, next_cursor: null, columns: [] }),
    ),
    http.post(apiUrl("/api/v1/report-runs"), async ({ request }) => {
      const body = (await request.json()) as { readonly parameters: Record<string, unknown> };
      asked.push(body.parameters);
      return HttpResponse.json(
        { id: JOB_ID, kind: "REPORT_RUN", state: "QUEUED" },
        {
          status: 202,
          headers: {
            Location: `/api/v1/jobs/${JOB_ID}`,
            "X-Erev-Report-Run-Id": runId(asked.length),
          },
        },
      );
    }),
    http.get(apiUrl("/api/v1/jobs/:jobId"), () =>
      HttpResponse.json({
        id: JOB_ID,
        kind: "REPORT_RUN",
        state: "SUCCEEDED",
        progress: null,
        started_at: "2026-09-12T16:02:11Z",
        finished_at: "2026-09-12T16:02:19Z",
        problem: null,
        result: null,
      }),
    ),
    http.get(apiUrl("/api/v1/schedule-lines"), ({ request }) => {
      lineReads.push(new URL(request.url).searchParams);
      return HttpResponse.json(
        { items: [], next_cursor: null },
        { headers: { "X-Total-Count": "0" } },
      );
    }),
    http.get(apiUrl("/api/v1/exceptions"), () => list([])),
  );
  return { asked, lineReads };
}

function open(path: string, me = ROBERT) {
  return renderApp(path, { me, screenRoutes: SCREEN_ROUTES });
}

/** The member's last choice in the context pill (BR-UX-01), kept for the workspace. */
function remember(
  choice: { readonly entity: string; readonly period: string | null; readonly book: string },
  me = ROBERT,
): void {
  const [membership] = me.memberships;
  if (membership === undefined) {
    throw new Error("The member has no workspace");
  }
  window.localStorage.setItem(
    contextStorageKey({ userId: me.user.id, tenantId: membership.tenant.id }),
    JSON.stringify(choice),
  );
}

function searchOf(app: ReturnType<typeof open>): string {
  return app.router.state.location.search;
}

const REPORT = "/reports/revenue_waterfall";
const REPORT_ROW = "SF-08-row-sf-ord-10001";
const SCHEDULES = "/schedules";
const SCHEDULES_ROW = "SF-04-row-sf-ord-10001";
/** RPT-01: the context fiscal year as the range, the context period's last day as of. */
const YEAR_2026 = {
  from_period_key: "FY2026-P08",
  to_period_key: "FY2026-P10",
  as_of: "2026-09-30",
};
const YEAR_2027 = {
  from_period_key: "FY2027-P05",
  to_period_key: "FY2027-P07",
  as_of: "2026-09-30",
};

describe("the context of a view: SF-08:report", () => {
  it("SF-08:report: an address without a context takes the member's last choice, writes it and asks one run for that entity", async () => {
    remember({ entity: "AVM-US", period: "FY2026-P09", book: "ASC606" });
    const served = serve();
    const app = open(REPORT);
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();
    expect(served.asked).toEqual([{ entity_codes: ["AVM-US"], book: "ASC606", ...YEAR_2026 }]);
    expect(searchOf(app)).toBe(`?entity=AVM-US&period=FY2026-P09&book=ASC606&run=${runId()}`);
  });

  it("SF-08:report: without a last choice it is the first entity in code order, the primary book and the earliest open period", async () => {
    const served = serve();
    const app = open(REPORT);
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();
    expect(served.asked).toEqual([{ entity_codes: ["AVM-DE"], book: "ASC606", ...YEAR_2026 }]);
    expect(searchOf(app)).toBe(`?entity=AVM-DE&period=FY2026-P09&book=ASC606&run=${runId()}`);
  });

  it("SF-08:report: entities=all asks every entity in scope and fills nothing", async () => {
    // With the book and the period the address has — and with none: what an absent entity read
    // until rev 1.92. The member's last choice does not come into it.
    remember({ entity: "AVM-US", period: "FY2026-P09", book: "ASC606" });
    const served = serve();
    const app = open(`${REPORT}?period=FY2026-P09&book=ASC606&entities=all`);
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();
    expect(served.asked).toEqual([{ book: "ASC606" }]);
    expect(searchOf(app)).toBe(`?period=FY2026-P09&book=ASC606&run=${runId()}&entities=all`);
    cleanup();

    const alone = serve();
    const bare = open(`${REPORT}?entities=all`);
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();
    expect(alone.asked).toEqual([{}]);
    expect(searchOf(bare)).toBe(`?run=${runId()}&entities=all`);
    cleanup();

    // `all` is the one value that says it: any other leaves the address one that names no entity.
    const other = serve();
    const some = open(`${REPORT}?entities=two`);
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();
    expect(other.asked).toEqual([{ entity_codes: ["AVM-US"], book: "ASC606", ...YEAR_2026 }]);
    expect(searchOf(some)).toBe(
      `?entity=AVM-US&period=FY2026-P09&book=ASC606&run=${runId()}&entities=two`,
    );
  });

  it("SF-08:report: an entity named beside entities=all decides", async () => {
    const served = serve();
    const app = open(`${REPORT}?entity=AVM-US&entities=all`);
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();
    expect(served.asked).toEqual([{ entity_codes: ["AVM-US"], book: "ASC606", ...YEAR_2026 }]);
    expect(searchOf(app)).toBe(
      `?entity=AVM-US&period=FY2026-P09&book=ASC606&run=${runId()}&entities=all`,
    );
  });

  it("SF-08:report: a link to a stored run without a context keeps its run: the context is filled around it and no run is asked", async () => {
    const served = serve();
    const app = open(`${REPORT}?run=${STORED_RUN}`);
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();
    await waitFor(() => {
      expect(searchOf(app)).toBe(`?entity=AVM-DE&period=FY2026-P09&book=ASC606&run=${STORED_RUN}`);
    });
    expect(served.asked).toEqual([]);

    // On the page that already stands on that context: a link to another stored run that names the
    // entity and the book and no period is filled with the same period, so it is no other context.
    await app.router.navigate(`${REPORT}?entity=AVM-DE&book=ASC606&run=${OTHER_STORED_RUN}`);
    await waitFor(() => {
      expect(searchOf(app)).toBe(
        `?entity=AVM-DE&period=FY2026-P09&book=ASC606&run=${OTHER_STORED_RUN}`,
      );
    });
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();
    expect(served.asked).toEqual([]);
  });

  it("SF-08:report: without config.read there is no pill: the address stays as it is", async () => {
    const served = serve();
    const app = open(
      REPORT,
      signedInMe({ permissions: ["contract.read", "report.run", "report.export"] }),
    );
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();
    expect(served.asked).toEqual([{}]);
    expect(searchOf(app)).toBe(`?run=${runId()}`);
  });

  it("SF-08:report: what the address names is kept: an entity's book and period are filled for it", async () => {
    // The last choice is another entity's; its book and its period key are AVM-JP's too, on AVM-JP's
    // own calendar the key is not: the earliest open period there.
    remember({ entity: "AVM-US", period: "FY2026-P09", book: "ASC606" });
    const served = serve();
    const app = open(`${REPORT}?entity=AVM-JP`);
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();
    expect(served.asked).toEqual([{ entity_codes: ["AVM-JP"], book: "ASC606", ...YEAR_2027 }]);
    expect(searchOf(app)).toBe(`?entity=AVM-JP&period=FY2027-P06&book=ASC606&run=${runId()}`);
  });

  it("SF-08:report: a book the entity does not keep and an entity outside the member's list are left as they are", async () => {
    // Nothing is rewritten and nothing is filled beside them: the API answers such a run by name.
    const served = serve();
    const app = open(`${REPORT}?entity=AVM-US&book=LEGACY`);
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();
    expect(served.asked).toEqual([{ entity_codes: ["AVM-US"], book: "LEGACY" }]);
    expect(searchOf(app)).toBe(`?entity=AVM-US&book=LEGACY&run=${runId()}`);
    cleanup();

    const unknown = serve();
    const other = open(`${REPORT}?entity=AVM-XX`);
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();
    expect(unknown.asked).toEqual([{ entity_codes: ["AVM-XX"] }]);
    expect(searchOf(other)).toBe(`?entity=AVM-XX&run=${runId()}`);
  });

  it("SF-08:report: a period is not filled on a calendar the member may not read", async () => {
    // SCR-PERM-02 (a): the periods of one entity are read with `config.read` for that entity. Held for
    // AVM-DE alone, an address that names AVM-US keeps what it has; the view asks AVM-US's run without
    // a period, as it does for this member with the book in the address.
    const scoped = signedInMe({
      permissions: ["contract.read", "config.read", "report.run", "report.export"],
      permission_scopes: {
        "contract.read": "*",
        "config.read": [AVM_DE.id],
        "report.run": "*",
        "report.export": "*",
      },
    });
    const served = serve();
    const app = open(`${REPORT}?entity=AVM-US`, scoped);
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();
    expect(served.asked).toEqual([{ entity_codes: ["AVM-US"], book: "ASC606" }]);
    expect(searchOf(app)).toBe(`?entity=AVM-US&book=ASC606&run=${runId()}`);
  });

  it("SF-08:report: from one report to another whose address holds a stored run and no context, the run stays", async () => {
    // The two reports stand under one route, so the page that fills the address has stood on another
    // context before: that is no change of the context of this report, and its stored run is kept.
    const served = serve();
    const app = open(`${REPORT}?entity=AVM-US&period=FY2026-P09&book=ASC606&run=${STORED_RUN}`);
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();

    await app.router.navigate(`/reports/rpo?run=${STORED_RUN}`);
    await waitFor(() => {
      expect(app.router.state.location.pathname).toBe("/reports/rpo");
      expect(searchOf(app)).toBe(`?entity=AVM-DE&period=FY2026-P09&book=ASC606&run=${STORED_RUN}`);
    });
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();
    expect(served.asked).toEqual([]);
  });

  it("SF-08:report: the pill's change of entity: the period is filled before a run is asked, and the old run leaves the address with it", async () => {
    const served = serve();
    const app = open(`${REPORT}?entity=AVM-US&period=FY2026-P09&book=ASC606&run=${STORED_RUN}`);
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();
    expect(served.asked).toEqual([]);

    // What the pill writes for another entity (ContextPill `change`): the entity and the book, and
    // the period taken out — the new entity's calendar is another one.
    await app.router.navigate(
      { pathname: REPORT, search: `?entity=AVM-JP&book=ASC606&run=${STORED_RUN}` },
      { replace: true },
    );
    await waitFor(() => {
      expect(searchOf(app)).toBe(`?entity=AVM-JP&period=FY2027-P06&book=ASC606&run=${runId()}`);
    });
    // One run, of AVM-JP's own year: none was asked while the period was out of the address.
    expect(served.asked).toEqual([{ entity_codes: ["AVM-JP"], book: "ASC606", ...YEAR_2027 }]);
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();
  });

  it("SF-08:report: the entities cannot be read: no run is asked, the page says so, and Retry reads again", async () => {
    const served = serve({ entitiesFail: true });
    const app = open(REPORT);
    expect(await screen.findByText("Could not load the report")).toBeTruthy();
    expect(served.asked).toEqual([]);
    expect(searchOf(app)).toBe("");

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();
    expect(served.asked).toEqual([{ entity_codes: ["AVM-DE"], book: "ASC606", ...YEAR_2026 }]);
  });
});

describe("the context of a view: SF-04", () => {
  /** RPT-01 on SF-04: the screen's own parameters beside the context's. */
  const SCREEN = { row_dimension: "CONTRACT", granularity: "MONTH", measure: "TOTAL" };

  it("SF-04: an address without a context takes the pill's, writes it and asks one run for that entity", async () => {
    remember({ entity: "AVM-US", period: "FY2026-P09", book: "ASC606" });
    const served = serve();
    const app = open(SCHEDULES);
    expect(await screen.findByTestId(SCHEDULES_ROW)).toBeTruthy();
    expect(served.asked).toEqual([
      { entity_codes: ["AVM-US"], book: "ASC606", ...YEAR_2026, ...SCREEN },
    ]);
    expect(searchOf(app)).toBe(`?entity=AVM-US&period=FY2026-P09&book=ASC606&run=${runId()}`);
    cleanup();

    // Without a last choice: BR-UX-01's default.
    window.localStorage.clear();
    const first = serve();
    const fresh = open(SCHEDULES);
    expect(await screen.findByTestId(SCHEDULES_ROW)).toBeTruthy();
    expect(first.asked).toEqual([
      { entity_codes: ["AVM-DE"], book: "ASC606", ...YEAR_2026, ...SCREEN },
    ]);
    expect(searchOf(fresh)).toBe(`?entity=AVM-DE&period=FY2026-P09&book=ASC606&run=${runId()}`);
  });

  it("SF-04: entities=all: the waterfall names no entity and the lines are read without one", async () => {
    remember({ entity: "AVM-US", period: "FY2026-P09", book: "ASC606" });
    const served = serve();
    const app = open(`${SCHEDULES}?period=FY2026-P09&book=ASC606&entities=all`);
    expect(await screen.findByTestId(SCHEDULES_ROW)).toBeTruthy();
    // No calendar is read without an entity: the range is the address's period, as it was.
    expect(served.asked).toEqual([
      { book: "ASC606", from_period_key: "FY2026-P09", to_period_key: "FY2026-P09", ...SCREEN },
    ]);
    expect(searchOf(app)).toBe(`?period=FY2026-P09&book=ASC606&run=${runId()}&entities=all`);
    cleanup();

    const lines = serve();
    open(`${SCHEDULES}?period=FY2026-P09&book=ASC606&layout=lines&entities=all`);
    await waitFor(() => expect(lines.lineReads.length).toBeGreaterThan(0));
    expect(lines.lineReads[0]?.get("entity")).toBeNull();
    expect(lines.lineReads[0]?.get("book")).toBe("ASC606");
    expect(lines.asked).toEqual([]);
  });

  it("SF-04: the lines of an address without a context are the pill's entity's", async () => {
    const served = serve();
    const app = open(`${SCHEDULES}?layout=lines`);
    await waitFor(() => expect(served.lineReads.length).toBeGreaterThan(0));
    expect(served.lineReads[0]?.get("entity")).toBe("AVM-DE");
    expect(served.lineReads[0]?.get("book")).toBe("ASC606");
    expect(searchOf(app)).toBe("?entity=AVM-DE&period=FY2026-P09&book=ASC606&layout=lines");
    expect(served.asked).toEqual([]);
  });

  it("SF-04: the address is completed in place: Back leaves the page", async () => {
    // The fill replaces the history entry (SCR-URL-20). As an entry of its own it would keep the
    // member on the page: Back would open the address without a context, which is filled again.
    serve();
    const app = open(`${REPORT}?entity=AVM-US&period=FY2026-P09&book=ASC606&run=${STORED_RUN}`);
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();
    await app.router.navigate(SCHEDULES);
    expect(await screen.findByTestId(SCHEDULES_ROW)).toBeTruthy();
    expect(searchOf(app)).toBe(`?entity=AVM-DE&period=FY2026-P09&book=ASC606&run=${runId()}`);

    await app.router.navigate(-1);
    await waitFor(() => {
      expect(app.router.state.location.pathname).toBe(REPORT);
    });
    expect(await screen.findByTestId(REPORT_ROW)).toBeTruthy();
  });

  it("SF-04: the pill's change of entity: one run, for the new entity on its own year, and the old run leaves the address", async () => {
    const served = serve();
    const app = open(`${SCHEDULES}?entity=AVM-US&period=FY2026-P09&book=ASC606&run=${STORED_RUN}`);
    expect(await screen.findByTestId(SCHEDULES_ROW)).toBeTruthy();
    expect(served.asked).toEqual([]);

    await app.router.navigate(
      { pathname: SCHEDULES, search: `?entity=AVM-JP&book=ASC606&run=${STORED_RUN}` },
      { replace: true },
    );
    await waitFor(() => {
      expect(searchOf(app)).toBe(`?entity=AVM-JP&period=FY2027-P06&book=ASC606&run=${runId()}`);
    });
    expect(served.asked).toEqual([
      { entity_codes: ["AVM-JP"], book: "ASC606", ...YEAR_2027, ...SCREEN },
    ]);
  });

  it("SF-04: the entities cannot be read: no run is asked, the page says so, and Retry reads again", async () => {
    const served = serve({ entitiesFail: true });
    open(SCHEDULES);
    expect(await screen.findByText("Could not load the revenue waterfall")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1, name: "Schedules" })).toBeTruthy();
    expect(served.asked).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByTestId(SCHEDULES_ROW)).toBeTruthy();
    expect(served.asked).toEqual([
      { entity_codes: ["AVM-DE"], book: "ASC606", ...YEAR_2026, ...SCREEN },
    ]);
  });
});
