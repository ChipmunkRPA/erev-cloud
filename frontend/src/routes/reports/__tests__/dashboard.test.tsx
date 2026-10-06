// @vitest-environment jsdom
// SF-08:dashboard, the revenue dashboard (BUILD_SPEC RPS-19; SCREENS_B §5.5 rev 1.82, §5.1; SCREENS RT-107,
// SCR-URL-26): the route and its codes, the four panels as one report run each with `run.<panel>` in the
// address, the page's rule for a context without an entity, a panel's own refusal and failure, "Refresh",
// the bridge and the category bars from the runs' rows, the flags panel, the marks' drills and the
// catalogue's list. API answers are contract fakes of 04 API-R-41, API-R-44, API-R-17 and API-R-18 (V-C).
import {
  act,
  cleanup,
  configure,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { useEffect } from "react";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SCREEN_ROUTES } from "../../../app/router";
import { contextStorageKey } from "../../../app/shell/ContextPill";
import type { ExceptionItem } from "../../../lib/api/queries/exceptions";
import type { ReportDefinition, ReportRow, ReportRun } from "../../../lib/api/queries/reports";
import type { Entity, Period } from "../../../lib/api/queries/tenant";
import { installMemoryStorage, renderApp, signedInMe } from "../../../test/app";
import { installGridViewport } from "../../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import { bridgeOf, categoriesOf, useSearchWriter } from "../dashboard";

installMswServer();
installMemoryStorage();
installGridViewport();
// The page reads the structure, the definitions and four runs before its charts render.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const ROBERT = signedInMe({
  permissions: ["contract.read", "config.read", "report.run"],
});

const JOB_ID = "8e7d6c5b-4a3f-4e2d-9c1b-0a9f8e7d6c5b";
const JANUARY = "c0000000-0000-4000-8000-000000000001";
const APRIL = "c0000000-0000-4000-8000-000000000004";
const CONTEXT = "entity=AVM-US&period=FY2026-P09&book=ASC606";
/** SCR-URL-01 rev 1.61: an address says all entities with the screen parameter, and names none. */
const ALL_CONTEXT = "period=FY2026-P09&book=ASC606&entities=all";

type Panel = "revenue" | "rollforward" | "rpo" | "disaggregation";
const PANELS: readonly Panel[] = ["revenue", "rollforward", "rpo", "disaggregation"];
const REPORT: Readonly<Record<Panel, { readonly code: string; readonly name: string }>> = {
  revenue: { code: "revenue_waterfall", name: "Revenue waterfall" },
  rollforward: { code: "contract_balance_rollforward", name: "Contract balance rollforward" },
  rpo: { code: "rpo", name: "Remaining performance obligations" },
  disaggregation: { code: "disaggregation", name: "Disaggregation of revenue" },
};
const PANEL_OF = new Map(PANELS.map((panel) => [REPORT[panel].code, panel]));

/** The id of the `round`th run a panel creates. */
function runId(panel: Panel, round = 1): string {
  return `a${String(PANELS.indexOf(panel) + 1)}000000-0000-4000-8000-00000000000${String(round)}`;
}

function money(amount: string, currency = "USD") {
  return { amount, currency };
}

function schema(keys: Readonly<Record<string, Readonly<Record<string, unknown>>>>) {
  return { type: "object", additionalProperties: false, properties: keys };
}

const COMMON = {
  entity_codes: { type: "array" },
  book: { type: "string", enum: ["ASC606", "IFRS15", "LEGACY"] },
  period_lock_id: { type: "string", format: "uuid" },
  currency_view: { type: "string", enum: ["transaction", "functional", "reporting"] },
};

/** The parameter keys of 04 T-RPT-01 for the four reports (backend catalogue). */
const DEFINITIONS: readonly ReportDefinition[] = [
  {
    code: "revenue_waterfall",
    version: 1,
    name: "Revenue waterfall",
    kind: "STANDARD",
    description: "Recognized, scheduled and awaiting-trigger revenue by period over a range.",
    parameters_schema: schema({
      ...COMMON,
      from_period_key: { type: "string" },
      to_period_key: { type: "string" },
      as_of: { type: "string", format: "date" },
      known_at: { type: "string", format: "date-time" },
      row_dimension: { type: "string" },
      granularity: { type: "string" },
      measure: { type: "string" },
      contract_external_id: { type: "string" },
    }),
    output_formats: ["XLSX", "CSV", "PDF", "JSON"],
    tie_outs: ["TO_WATERFALL_EQ_JE_REVENUE"],
    ipe_logic: null,
  },
  {
    code: "contract_balance_rollforward",
    version: 1,
    name: "Contract balance rollforward",
    kind: "DISCLOSURE",
    description: "Opening balance, activity and closing balance of the contract balances.",
    parameters_schema: schema({
      ...COMMON,
      from_period_key: { type: "string" },
      to_period_key: { type: "string" },
      balance_role: { type: "string" },
    }),
    output_formats: ["XLSX", "CSV", "PDF", "JSON"],
    tie_outs: ["TO_ROLLFORWARD_BALANCES"],
    ipe_logic: null,
  },
  {
    code: "rpo",
    version: 1,
    name: "Remaining performance obligations",
    kind: "DISCLOSURE",
    description: "RPO by contract and expected timing of recognition.",
    parameters_schema: schema({
      ...COMMON,
      period_key: { type: "string" },
      time_bands: { type: "array", items: { type: "integer" } },
      row_dimension: { type: "string" },
    }),
    output_formats: ["XLSX", "CSV", "PDF", "JSON"],
    tie_outs: ["TO_RPO_ROLLFORWARD_EQ_RPO"],
    ipe_logic: null,
  },
  {
    code: "disaggregation",
    version: 1,
    name: "Disaggregation of revenue",
    kind: "DISCLOSURE",
    description: "Revenue by a disaggregation dimension and timing of transfer over a range.",
    parameters_schema: schema({
      ...COMMON,
      from_period_key: { type: "string" },
      to_period_key: { type: "string" },
      dimension_code: { type: "string" },
      include_timing: { type: "boolean" },
    }),
    output_formats: ["XLSX", "CSV", "PDF", "JSON"],
    tie_outs: ["TO_DISAGGREGATION_EQ_JE_REVENUE"],
    ipe_logic: null,
  },
] as unknown as readonly ReportDefinition[];

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

const AVM_US = entity("AVM-US", JANUARY, "USD");
const AVM_UK = entity("AVM-UK", JANUARY, "GBP");
const AVM_CA = entity("AVM-CA", JANUARY, "USD");
const AVM_JP = entity("AVM-JP", APRIL, "JPY");
const AVM_NZ = entity("AVM-NZ", APRIL, "USD");

function period(key: string, name: string, start: string, end: string, state: string): Period {
  return {
    id: `1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e${key.slice(-2)}`,
    entity: { id: AVM_US.id, code: "AVM-US", name: AVM_US.name },
    book: "ASC606",
    period: {
      id: `2c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e${key.slice(-2)}`,
      period_key: key,
      name,
      fiscal_year: 2026,
      period_no: Number.parseInt(key.slice(-2), 10),
      quarter_no: 3,
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

const PERIODS: readonly Period[] = [
  period("FY2026-P08", "Aug 2026", "2026-08-01", "2026-08-31", "closed"),
  period("FY2026-P09", "Sep 2026", "2026-09-01", "2026-09-30", "open"),
  period("FY2026-P10", "Oct 2026", "2026-10-01", "2026-10-31", "future"),
];

function reportRun(panel: Panel, overrides: Partial<ReportRun> = {}): ReportRun {
  const report = REPORT[panel];
  return {
    id: runId(panel),
    report_run_no: `RPT-00043${String(PANELS.indexOf(panel) + 1)}`,
    report: { code: report.code, version: 1, name: report.name },
    status: "SUCCEEDED",
    parameters: {},
    entity_scope: [{ id: AVM_US.id, code: "AVM-US", name: AVM_US.name }],
    book: "ASC606",
    as_of: "2026-09-30",
    known_at: "2026-09-12T16:20:00Z",
    period_lock_id: null,
    engine_release: { engine_version: "1.0.0", build_sha: "3f9a1c22" },
    row_count: 2,
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
    started_at: "2026-09-12T16:20:01Z",
    finished_at: "2026-09-12T16:21:09Z",
    ...overrides,
  } as unknown as ReportRun;
}

const WATERFALL_RUN = reportRun("revenue", {
  control_totals: {
    recognized_total: { USD: "19528.76" },
    scheduled_total: { USD: "9764.38" },
    awaiting_trigger_total: { USD: "0.00" },
  },
});
const WATERFALL_ROWS = [
  {
    row_key: "contract:SF-ORD-10001",
    contract_external_id: "SF-ORD-10001",
    customer_name: "Marrowby Health",
    entity_code: "AVM-US",
    "period:FY2026-P08": money("9764.38"),
    "period:FY2026-P09": money("9764.38"),
    "period:FY2026-P10": money("9764.38"),
    awaiting_trigger: money("0.00"),
    total: money("29293.14"),
  },
  {
    row_key: "TOTAL:USD",
    contract_external_id: null,
    customer_name: null,
    entity_code: null,
    "period:FY2026-P08": money("9764.38"),
    "period:FY2026-P09": money("9764.38"),
    "period:FY2026-P10": money("9764.38"),
    awaiting_trigger: money("0.00"),
    total: money("29293.14"),
  },
] as unknown as readonly ReportRow[];

/** Section 1 of RPT-03 as the builder writes it: nine lines in order, three balance columns. */
function rollforwardRows(
  amounts: Readonly<Record<string, string>>,
  currency = "USD",
  mixed = false,
): readonly ReportRow[] {
  const labels: readonly (readonly [string, string])[] = [
    ["OPENING", "Opening balance"],
    ["BILLINGS", "Billings"],
    ["REVENUE_FROM_OPENING", "Revenue recognized from the opening balance"],
    ["REVENUE_FROM_PERIOD_BILLINGS", "Revenue recognized from billings of the period"],
    ["RECLASSIFICATIONS", "Reclassifications"],
    ["FX_REMEASUREMENT", "FX remeasurement"],
    ["BUSINESS_COMBINATIONS", "Business combinations"],
    ["OTHER", "Other"],
    ["CLOSING", "Closing balance"],
  ];
  return labels.map(([code, label]) => ({
    row_key: mixed ? `${code}:${currency}` : code,
    section: 1,
    line_code: code,
    line_label: label,
    contract_external_id: null,
    currency,
    contract_liability: money(amounts[code] ?? "0.00", currency),
    contract_asset: money("0.00", currency),
    unbilled_receivable: money("0.00", currency),
  })) as unknown as readonly ReportRow[];
}

const LIABILITY = {
  OPENING: "39708.49",
  BILLINGS: "12000.00",
  REVENUE_FROM_OPENING: "-9764.38",
  CLOSING: "41944.11",
};
const ROLLFORWARD_RUN = reportRun("rollforward", {
  tie_out_results: [
    {
      code: "TO_ROLLFORWARD_BALANCES",
      result: "PASS",
      expected: [money("41944.11")],
      actual: [money("41944.11")],
      difference: [money("0.00")],
    },
  ],
} as Partial<ReportRun>);

const BANDS = [
  { index: 0, key: "within_12_months", from_month: 1, to_month: 12 },
  { index: 1, key: "months_13_to_24", from_month: 13, to_month: 24 },
  { index: 2, key: "after_24_months", from_month: 25, to_month: null },
];
const RPO_RUN = reportRun("rpo", {
  control_totals: { as_of: "2026-09-30", bands: BANDS, total: { USD: "105043.80" } },
});
const RPO_FIGURES = {
  currency: "USD",
  total: money("105043.80"),
  within_12_months: money("70043.80"),
  months_13_to_24: money("35000.00"),
  after_24_months: money("0.00"),
  current: money("70043.80"),
  noncurrent: money("35000.00"),
};
const RPO_ROWS = [
  { row_key: "entity:AVM-US", section: 1, entity_code: "AVM-US", ...RPO_FIGURES },
  { row_key: "TOTAL:USD", section: 1, entity_code: null, ...RPO_FIGURES },
] as unknown as readonly ReportRow[];

function category(value: string, total: string, currency = "USD", mixed = false) {
  return {
    row_key: mixed ? `${value}:${currency}` : value,
    dimension_code: "revenue_category",
    dimension_value: value,
    timing_code: null,
    dimension_value_label: value,
    timing: null,
    currency,
    "period:FY2026-P09": money(total, currency),
    total: money(total, currency),
  };
}

function categoryTotal(total: string, currency = "USD") {
  return {
    row_key: `TOTAL:${currency}`,
    dimension_value_label: null,
    timing: null,
    currency,
    "period:FY2026-P09": money(total, currency),
    total: money(total, currency),
  };
}

const CATEGORY_RUN = reportRun("disaggregation");
/** In the builder's order: by the dimension value, not by the amounts. */
const CATEGORY_ROWS = [
  category("Licences", "20000.00"),
  category("Products", "40000.00"),
  category("Services", "80000.00"),
  category("Subscription", "150000.00"),
  categoryTotal("290000.00"),
] as unknown as readonly ReportRow[];

/** An anomaly flag about a contract, or — `key` — about a record that has only a business key. */
function flag(
  number: number,
  code: string,
  record: string | null,
  key: string | null = null,
): ExceptionItem {
  return {
    id: `f0000000-0000-4000-8000-00000000000${String(number)}`,
    exception_no: `EXC-00000${String(number)}`,
    source: "ANOMALY",
    code,
    severity: "WARNING",
    status: "OPEN",
    title: "Revenue changed by more than the threshold",
    message: "Revenue changed by more than the threshold.",
    business_key: key,
    contract_external_id: record,
    created_at: "2026-09-12T10:00:00Z",
  } as unknown as ExceptionItem;
}

/** A read the fake can fail: a list, or the run or the rows of one run id. */
type Read = "entities" | "definitions" | "flags" | `run:${string}` | `rows:${string}`;

const BOOK_NAMES: Readonly<Record<string, string>> = { ASC606: "ASC 606", IFRS15: "IFRS 15" };

interface World {
  readonly entities?: readonly Entity[];
  /** The books of the workspace; ASC 606 alone unless a test states them. */
  readonly books?: readonly string[];
  readonly periods?: readonly Period[];
  readonly definitions?: readonly ReportDefinition[];
  readonly runs?: Readonly<Record<string, ReportRun>>;
  readonly rows?: Readonly<Record<string, readonly ReportRow[]>>;
  /** The answer to `POST /report-runs` of a report code, in place of the 202; undefined for the 202. */
  readonly refuse?: Readonly<Record<string, () => Response | undefined>>;
  /** The 202 of a report code's `call`th creation is answered once this has settled. */
  readonly createAfter?: (code: string, call: number) => Promise<void> | undefined;
  readonly flags?: readonly ExceptionItem[];
  readonly flagCount?: number;
  /** The flags of an entity, where they differ by entity. */
  readonly flagsOf?: (entity: string | null) => readonly ExceptionItem[];
  /** Reads answered 500 twice — the read and the one retry the client makes — and then as usual. */
  readonly failing?: readonly Read[];
  /** A run that is RUNNING at its first read and has succeeded at the next. */
  readonly running?: string;
  /** The catalogue of reports is answered once this has settled. */
  readonly definitionsAfter?: Promise<void>;
  /** Called at each `POST /report-runs`, after the view has taken the time it began. */
  readonly onCreate?: () => void;
}

interface Served {
  /** The bodies of `POST /report-runs`, in order. */
  readonly posted: Record<string, unknown>[];
  /** The search strings of `GET /exceptions`. */
  readonly flagReads: string[];
}

function serve(world: World = {}): Served {
  const posted: Record<string, unknown>[] = [];
  const flagReads: string[] = [];
  const created = new Map<string, number>();
  const runs: Record<string, ReportRun> = {
    [runId("revenue")]: WATERFALL_RUN,
    [runId("rollforward")]: ROLLFORWARD_RUN,
    [runId("rpo")]: RPO_RUN,
    [runId("disaggregation")]: CATEGORY_RUN,
    ...world.runs,
  };
  const rows: Record<string, readonly ReportRow[]> = {
    [runId("revenue")]: WATERFALL_ROWS,
    [runId("rollforward")]: rollforwardRows(LIABILITY),
    [runId("rpo")]: RPO_ROWS,
    [runId("disaggregation")]: CATEGORY_ROWS,
    ...world.rows,
  };
  const list = (items: readonly unknown[]) => HttpResponse.json({ items, next_cursor: null });
  const failures = new Map<Read, number>();
  /** True for the first two reads of a failing kind: the read and its one retry. */
  const fails = (read: Read): boolean => {
    if (world.failing?.includes(read) !== true) {
      return false;
    }
    const seen = failures.get(read) ?? 0;
    failures.set(read, seen + 1);
    return seen < 2;
  };
  const unavailable = () => problemResponse(null, 500, "Internal Server Error");
  let computing = world.running;
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () => list([])),
    http.get(apiUrl("/api/v1/jobs"), () => list([])),
    http.get(apiUrl("/api/v1/saved-views"), () => list([])),
    http.get(apiUrl("/api/v1/entities"), () =>
      fails("entities") ? unavailable() : list(world.entities ?? [AVM_US]),
    ),
    http.get(apiUrl("/api/v1/books"), () =>
      list(
        (world.books ?? ["ASC606"]).map((code, index) => ({
          id: `b${String(index + 1)}`,
          code,
          name: BOOK_NAMES[code] ?? code,
          is_primary: index === 0,
          is_enabled: true,
        })),
      ),
    ),
    http.get(apiUrl("/api/v1/periods"), () => list(world.periods ?? PERIODS)),
    http.get(apiUrl("/api/v1/currencies"), () =>
      list(
        ["USD", "GBP", "JPY"].map((code) => ({
          code,
          name: code,
          minor_unit: code === "JPY" ? 0 : 2,
          numeric_code: "000",
          is_active: true,
        })),
      ),
    ),
    http.get(apiUrl("/api/v1/report-definitions"), async () => {
      await world.definitionsAfter;
      return fails("definitions") ? unavailable() : list(world.definitions ?? DEFINITIONS);
    }),
    http.get(apiUrl("/api/v1/report-definitions/:code"), ({ params }) => {
      const found = DEFINITIONS.find((definition) => definition.code === params.code);
      return found === undefined
        ? problemResponse("not-found", 404, "Report not found")
        : HttpResponse.json(found);
    }),
    http.get(apiUrl("/api/v1/report-runs"), () => list([])),
    http.get(apiUrl("/api/v1/report-runs/:runId"), ({ params }) => {
      const id = String(params.runId);
      if (fails(`run:${id}`)) {
        return unavailable();
      }
      const found = runs[id];
      if (found === undefined) {
        return problemResponse("not-found", 404, "Report run not found");
      }
      if (computing === id) {
        computing = undefined;
        return HttpResponse.json({ ...found, status: "RUNNING", finished_at: null });
      }
      return HttpResponse.json(found);
    }),
    http.get(apiUrl("/api/v1/report-runs/:runId/data"), ({ params }) => {
      const id = String(params.runId);
      return fails(`rows:${id}`)
        ? unavailable()
        : HttpResponse.json({ items: rows[id] ?? [], next_cursor: null, columns: [] });
    }),
    http.post(apiUrl("/api/v1/report-runs"), async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      posted.push(body);
      world.onCreate?.();
      const code = String(body.report_code);
      const refused = world.refuse?.[code]?.();
      if (refused !== undefined) {
        return refused;
      }
      const round = (created.get(code) ?? 0) + 1;
      created.set(code, round);
      await world.createAfter?.(code, round);
      const panel = PANEL_OF.get(code) ?? "revenue";
      return HttpResponse.json(
        { id: JOB_ID, kind: "REPORT_RUN", state: "QUEUED" },
        {
          status: 202,
          headers: {
            Location: `/api/v1/jobs/${JOB_ID}`,
            "X-Erev-Report-Run-Id": runId(panel, round),
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
        started_at: "2026-09-12T16:20:01Z",
        finished_at: "2026-09-12T16:20:09Z",
        problem: null,
        result: null,
      }),
    ),
    http.get(apiUrl("/api/v1/exceptions"), ({ request }) => {
      const url = new URL(request.url);
      if (fails("flags")) {
        return unavailable();
      }
      flagReads.push(url.search);
      const items = world.flagsOf?.(url.searchParams.get("entity")) ?? world.flags ?? [];
      return HttpResponse.json(
        { items, next_cursor: null },
        { headers: { "X-Erev-Total-Count": String(world.flagCount ?? items.length) } },
      );
    }),
  );
  return { posted, flagReads };
}

function open(path: string, me = ROBERT) {
  return renderApp(path, { me, screenRoutes: SCREEN_ROUTES });
}

/** The member's last choice in the context pill (BR-UX-01), kept for the workspace. */
function remember(
  choice: { readonly entity: string; readonly period: string; readonly book: string },
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

function figure(name: string | RegExp) {
  return screen.findByRole("figure", { name });
}

/** The panels of a second round of runs: the same reports under new ids. */
function secondRound(): {
  readonly runs: Record<string, ReportRun>;
  readonly rows: Record<string, readonly ReportRow[]>;
} {
  const runs: Record<string, ReportRun> = {};
  const rows: Record<string, readonly ReportRow[]> = {};
  const first: Readonly<Record<Panel, readonly [ReportRun, readonly ReportRow[]]>> = {
    revenue: [WATERFALL_RUN, WATERFALL_ROWS],
    rollforward: [ROLLFORWARD_RUN, rollforwardRows(LIABILITY)],
    rpo: [RPO_RUN, RPO_ROWS],
    disaggregation: [CATEGORY_RUN, CATEGORY_ROWS],
  };
  for (const panel of PANELS) {
    const [run, data] = first[panel];
    const id = runId(panel, 2);
    runs[id] = { ...run, id, report_run_no: `RPT-00053${String(PANELS.indexOf(panel) + 1)}` };
    rows[id] = data;
  }
  return { runs, rows };
}

function searchOf(app: ReturnType<typeof open>): URLSearchParams {
  return new URLSearchParams(app.router.state.location.search);
}

describe("SF-08:dashboard", () => {
  it("unknown code not found", async () => {
    serve();
    // RT-107: `revenue` is the page; another code of the pattern is X:not-found.
    const page = open(`/reports/dashboards/revenue?${CONTEXT}`);
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Revenue dashboard · AVM-US · Sep 2026 · ASC 606",
      }),
    ).toBeTruthy();
    expect(page.router.state.location.pathname).toBe("/reports/dashboards/revenue");
    await waitFor(() => expect(document.title).toBe("Dashboard · eRev Cloud"));
    // The breadcrumb leads to the catalogue in the page's context.
    expect(
      within(screen.getByRole("navigation", { name: "Breadcrumb" }))
        .getByRole("link", { name: "Reports" })
        .getAttribute("href"),
    ).toBe(`/reports?${CONTEXT}`);
    cleanup();

    serve();
    open(`/reports/dashboards/sales?${CONTEXT}`);
    expect(await screen.findByTestId("X-page")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeTruthy();
    expect(screen.queryByTestId("SF-08-page")).toBeNull();
    cleanup();

    // Panels whose read permission is missing are not rendered: without `config.read` no chart panel
    // and no run, without `contract.read` no flags panel.
    const served = serve();
    open(
      `/reports/dashboards/revenue?${CONTEXT}`,
      signedInMe({ permissions: ["contract.read", "report.run"] }),
    );
    expect(await screen.findByTestId("SF-08-dashboard-flags")).toBeTruthy();
    for (const panel of PANELS) {
      expect(screen.queryByTestId(`SF-08-chart-dashboard-${panel}`)).toBeNull();
    }
    expect(served.posted).toEqual([]);
    cleanup();

    serve();
    open(
      `/reports/dashboards/revenue?${CONTEXT}`,
      signedInMe({ permissions: ["config.read", "report.run"] }),
    );
    await figure("Revenue by period · USD · ASC 606");
    expect(screen.queryByTestId("SF-08-dashboard-flags")).toBeNull();
    cleanup();

    // The exception queue is read with `contract.read` (04 API-R-44); `exception.resolve` is its
    // commands' and opens no panel.
    serve();
    open(
      `/reports/dashboards/revenue?${CONTEXT}`,
      signedInMe({ permissions: ["exception.resolve", "config.read", "report.run"] }),
    );
    await figure("Revenue by period · USD · ASC 606");
    expect(screen.queryByTestId("SF-08-dashboard-flags")).toBeNull();
    cleanup();

    // Nor without an entity in the context.
    serve();
    open(
      "/reports/dashboards/revenue?period=FY2026-P09&book=ASC606",
      signedInMe({ permissions: ["config.read", "report.run"] }),
    );
    await figure("Revenue by category · USD · Sep 2026");
    expect(screen.queryByTestId("SF-08-dashboard-flags")).toBeNull();
    cleanup();

    // Neither the calendar nor the queue: the page says which access is missing.
    serve();
    open(`/reports/dashboards/revenue?${CONTEXT}`, signedInMe({ permissions: ["report.run"] }));
    expect(
      await screen.findByText(
        "Ask a workspace administrator for a role that includes viewing configuration.",
      ),
    ).toBeTruthy();
    cleanup();

    // SCR-PERM-01: the route is `report.run`'s.
    serve();
    open(
      `/reports/dashboards/revenue?${CONTEXT}`,
      signedInMe({ permissions: ["contract.read", "config.read", "audit.read"] }),
    );
    expect(
      await screen.findByRole("heading", { name: "You do not have access to the dashboards" }),
    ).toBeTruthy();
    expect(
      screen.getByText("Ask a workspace administrator for a role that includes running reports."),
    ).toBeTruthy();
  });

  it("one entity: four runs under the functional view, each kept in the address", async () => {
    const served = serve();
    const app = open(`/reports/dashboards/revenue?${CONTEXT}`);

    await figure("Revenue by period · USD · ASC 606");
    await figure("Contract liability rollforward · USD");
    await figure("Remaining performance obligations by time band · USD · ASC 606");
    await figure("Revenue by category · USD · Sep 2026");

    // RV-01: one JSON run per panel, with the context's parameters and the page's view.
    expect(served.posted).toHaveLength(4);
    const sent = new Map(served.posted.map((body) => [String(body.report_code), body]));
    for (const body of served.posted) {
      expect(body.output_format).toBe("JSON");
    }
    const shared = { entity_codes: ["AVM-US"], book: "ASC606", currency_view: "functional" };
    expect(sent.get("revenue_waterfall")?.parameters).toEqual({
      ...shared,
      as_of: "2026-09-30",
      from_period_key: "FY2026-P08",
      to_period_key: "FY2026-P10",
    });
    expect(sent.get("contract_balance_rollforward")?.parameters).toEqual({
      ...shared,
      from_period_key: "FY2026-P09",
      to_period_key: "FY2026-P09",
    });
    expect(sent.get("rpo")?.parameters).toEqual({
      ...shared,
      period_key: "FY2026-P09",
      row_dimension: "ENTITY",
    });
    expect(sent.get("disaggregation")?.parameters).toEqual({
      ...shared,
      from_period_key: "FY2026-P09",
      to_period_key: "FY2026-P09",
      dimension_code: "revenue_category",
      include_timing: false,
    });

    // SCR-URL-26: the four runs stand in the address together; none replaced another.
    await waitFor(() => {
      const search = searchOf(app);
      for (const panel of PANELS) {
        expect(search.get(`run.${panel}`)).toBe(runId(panel));
      }
    });
    expect(searchOf(app).get("entity")).toBe("AVM-US");
    expect(searchOf(app).get("currency_view")).toBeNull();

    // The page states its view, and each panel its run with the way to the report.
    const header = screen.getByRole("heading", { level: 1 }).closest("section");
    expect([...(header?.querySelectorAll("dt, dd") ?? [])].map((cell) => cell.textContent)).toEqual(
      ["Currency", "Functional"],
    );
    expect(screen.getByRole("button", { name: "Refresh" })).toBeTruthy();
    const revenue = screen.getByTestId("SF-08-chart-dashboard-revenue");
    const stamp = revenue.querySelector("[data-volatile]");
    expect(stamp?.textContent).toBe("Run RPT-000431 · 12 Sep 2026 16:21 UTC");
    expect(
      within(revenue).getByRole("link", { name: "Open report: Revenue waterfall" }).textContent,
    ).toBe("Open report");
    expect(
      within(revenue)
        .getByRole("link", { name: "Open report: Revenue waterfall" })
        .getAttribute("href"),
    ).toBe(
      `/reports/revenue_waterfall?${CONTEXT}&currency_view=functional&run=${runId("revenue")}`,
    );
    expect(
      within(screen.getByTestId("SF-08-chart-dashboard-rpo"))
        .getByRole("link", { name: "Open report: Remaining performance obligations" })
        .getAttribute("href"),
    ).toBe(
      `/reports/rpo?${CONTEXT}&currency_view=functional&run=${runId("rpo")}&p.row_dimension=ENTITY`,
    );
    expect(
      within(screen.getByTestId("SF-08-chart-dashboard-disaggregation"))
        .getByRole("link", { name: "Open report: Disaggregation of revenue" })
        .getAttribute("href"),
    ).toBe(
      `/reports/disaggregation?${CONTEXT}&currency_view=functional&run=${runId("disaggregation")}&p.dimension_code=revenue_category&p.include_timing=false`,
    );

    // §5.5 order, which is the one column of 1280 px: the flags stand before the last chart.
    const order = [
      ...document.querySelectorAll(
        '[data-testid^="SF-08-chart-dashboard-"], [data-testid="SF-08-dashboard-flags"]',
      ),
    ].map((element) => element.getAttribute("data-testid"));
    expect(order).toEqual([
      "SF-08-chart-dashboard-revenue",
      "SF-08-chart-dashboard-rollforward",
      "SF-08-chart-dashboard-rpo",
      "SF-08-dashboard-flags",
      "SF-08-chart-dashboard-disaggregation",
    ]);
  });

  it("a shared link shows its four runs and creates none", async () => {
    const served = serve();
    const runs = PANELS.map((panel) => `run.${panel}=${runId(panel)}`).join("&");
    open(`/reports/dashboards/revenue?${CONTEXT}&${runs}`);

    await figure("Revenue by period · USD · ASC 606");
    await figure("Contract liability rollforward · USD");
    await figure("Remaining performance obligations by time band · USD · ASC 606");
    await figure("Revenue by category · USD · Sep 2026");
    expect(served.posted).toEqual([]);
  });

  it("all entities on different calendars or currencies: no run, the banner says why", async () => {
    const cases: readonly (readonly [readonly Entity[], string])[] = [
      [
        [AVM_US, AVM_JP],
        "The entities in scope keep different calendars and functional currencies. Select an entity to see its charts.",
      ],
      [
        [AVM_US, AVM_NZ],
        "The entities in scope keep different calendars. Select an entity to see its charts.",
      ],
      [
        [AVM_US, AVM_UK],
        "The entities in scope keep different functional currencies. Select an entity to see its charts.",
      ],
    ];
    for (const [entities, sentence] of cases) {
      const served = serve({ entities });
      open(`/reports/dashboards/revenue?${ALL_CONTEXT}`);
      expect(
        await screen.findByRole("heading", {
          level: 1,
          name: "Revenue dashboard · All entities · Sep 2026 · ASC 606",
        }),
      ).toBeTruthy();
      const banner = await screen.findByTestId("SF-08-dashboard-banner-scope");
      expect(banner.textContent).toBe(sentence);
      // Information that stands with the page, not an announcement.
      expect(banner.querySelector('[data-tone="info"]')).not.toBeNull();
      expect(banner.querySelector("[role]")).toBeNull();
      // The flags name no period and stay; nothing is run, so nothing is refreshed or stated.
      expect((await screen.findByTestId("SF-08-dashboard-flags")).textContent).toContain(
        "No open anomaly flags",
      );
      for (const panel of PANELS) {
        expect(screen.queryByTestId(`SF-08-chart-dashboard-${panel}`)).toBeNull();
      }
      expect(screen.queryByRole("button", { name: "Refresh" })).toBeNull();
      expect(screen.queryByText("Functional")).toBeNull();
      expect(served.posted).toEqual([]);
      // No entity is asked of the flags either.
      expect(new URLSearchParams(served.flagReads[0]).get("entity")).toBeNull();
      cleanup();
    }
  });

  it("all entities on one calendar and one currency: the panels run without an entity", async () => {
    const served = serve({ entities: [AVM_CA, AVM_US] });
    const app = open(`/reports/dashboards/revenue?${ALL_CONTEXT}`);

    await figure("Revenue by period · USD · ASC 606");
    await figure("Revenue by category · USD · Sep 2026");
    expect(screen.queryByTestId("SF-08-dashboard-banner-scope")).toBeNull();
    expect(served.posted).toHaveLength(4);
    for (const body of served.posted) {
      const parameters = body.parameters as Record<string, unknown>;
      expect(parameters.entity_codes).toBeUndefined();
      expect(parameters.currency_view).toBe("functional");
    }
    // The address stays the one of all entities: no entity is written into it.
    expect(searchOf(app).get("entity")).toBeNull();
    expect(searchOf(app).get("entities")).toBe("all");
    // The links to the report views say what the page shows: all entities (SCR-URL-01 rev 1.61) —
    // without it the report view would open the pill's entity around a run of all entities.
    expect(
      within(screen.getByTestId("SF-08-chart-dashboard-rollforward"))
        .getByRole("link", { name: "Open report: Contract balance rollforward" })
        .getAttribute("href"),
    ).toBe(
      `/reports/contract_balance_rollforward?period=FY2026-P09&book=ASC606&currency_view=functional&run=${runId("rollforward")}&entities=all`,
    );
    // The other links name no entity and carry no `entities`: no other screen reads it.
    expect(
      within(screen.getByRole("navigation", { name: "Breadcrumb" }))
        .getByRole("link", { name: "Reports" })
        .getAttribute("href"),
    ).toBe("/reports?period=FY2026-P09&book=ASC606");
    // A period of "Revenue by period" opens Schedules for all entities too.
    const column = (await figure("Revenue by period · USD · ASC 606")).querySelector(
      '[data-period="FY2026-P08"]',
    );
    if (column === null) {
      throw new Error("No column for Aug 2026");
    }
    fireEvent.click(column);
    await waitFor(() => {
      expect(app.router.state.location.pathname).toBe("/schedules");
    });
    expect(app.router.state.location.search).toMatch(
      /^\?period=FY2026-P08&book=ASC606(&run=[0-9a-f-]{36})?&entities=all$/,
    );
  });

  it("an entity that does not keep the book is not of the scope", async () => {
    // A run without an entity reads the entities that keep the book: one on another calendar and in
    // another currency that keeps another book, or keeps this one disabled, changes nothing.
    const other = {
      ...AVM_JP,
      books: [
        { book_code: "IFRS15", is_enabled: true },
        { book_code: "ASC606", is_enabled: false },
      ],
    } as unknown as Entity;
    const served = serve({ entities: [AVM_CA, other, AVM_US] });
    open(`/reports/dashboards/revenue?${ALL_CONTEXT}`);
    await figure("Revenue by period · USD · ASC 606");
    expect(screen.queryByTestId("SF-08-dashboard-banner-scope")).toBeNull();
    expect(served.posted).toHaveLength(4);
    for (const body of served.posted) {
      expect((body.parameters as Record<string, unknown>).entity_codes).toBeUndefined();
    }
  });

  it("the flags are asked of the context entity's permission", async () => {
    // `contract.read` for AVM-UK alone: no flags of AVM-US; for all entities, the flags of the scope.
    const scoped = signedInMe({
      permissions: ["contract.read", "config.read", "report.run"],
      permission_scopes: { "contract.read": [AVM_UK.id], "config.read": "*", "report.run": "*" },
    });
    const runs = PANELS.map((panel) => `run.${panel}=${runId(panel)}`).join("&");
    serve({ entities: [AVM_UK, AVM_US] });
    open(`/reports/dashboards/revenue?${CONTEXT}&${runs}`, scoped);
    await figure("Revenue by period · USD · ASC 606");
    await figure("Revenue by category · USD · Sep 2026");
    expect(screen.queryByTestId("SF-08-dashboard-flags")).toBeNull();
    cleanup();

    const all = serve({ entities: [AVM_UK, AVM_US] });
    open(`/reports/dashboards/revenue?${ALL_CONTEXT}`, scoped);
    expect(await screen.findByTestId("SF-08-dashboard-flags")).toBeTruthy();
    expect(new URLSearchParams(all.flagReads[0]).get("entity")).toBeNull();
  });

  it("the charts are asked of the context entity's permission to run reports; for all entities, of the member's scope", async () => {
    // A run that names an entity outside the member's `report.run` scope is refused (04 API-R-41):
    // with `report.run` for AVM-UK alone, AVM-US has no chart panel and makes no run.
    const scoped = signedInMe({
      permissions: ["contract.read", "config.read", "report.run"],
      permission_scopes: { "contract.read": "*", "config.read": "*", "report.run": [AVM_UK.id] },
    });
    const served = serve({ entities: [AVM_UK, AVM_US] });
    open(`/reports/dashboards/revenue?${CONTEXT}`, scoped);
    expect(await screen.findByTestId("SF-08-dashboard-flags")).toBeTruthy();
    for (const panel of PANELS) {
      expect(screen.queryByTestId(`SF-08-chart-dashboard-${panel}`)).toBeNull();
    }
    expect(screen.queryByRole("button", { name: "Refresh" })).toBeNull();
    expect(served.posted).toEqual([]);
    cleanup();

    // Without the queue's read either, the page names what the charts lack.
    serve({ entities: [AVM_UK, AVM_US] });
    open(
      `/reports/dashboards/revenue?${CONTEXT}`,
      signedInMe({
        permissions: ["config.read", "report.run"],
        permission_scopes: { "config.read": "*", "report.run": [AVM_UK.id] },
      }),
    );
    expect(
      await screen.findByRole("heading", { name: "You do not have access to the dashboards" }),
    ).toBeTruthy();
    expect(
      screen.getByText("Ask a workspace administrator for a role that includes running reports."),
    ).toBeTruthy();
    cleanup();

    // For all entities the run reads the member's scope: AVM-UK alone is one calendar and one
    // currency, whatever AVM-JP keeps. The pill's entity, AVM-US, keeps AVM-UK's calendar.
    remember({ entity: "AVM-US", period: "FY2026-P09", book: "ASC606" }, scoped);
    const all = serve({ entities: [AVM_JP, AVM_UK, AVM_US] });
    open(`/reports/dashboards/revenue?${ALL_CONTEXT}`, scoped);
    await figure("Revenue by period · USD · ASC 606");
    expect(screen.queryByTestId("SF-08-dashboard-banner-scope")).toBeNull();
    expect(all.posted).toHaveLength(4);
    cleanup();

    // The context period is a period of the pill's entity, and a run reads it by its key. Where the
    // pill's entity keeps another calendar than the scope's, that key is another month there: no
    // run is made.
    remember({ entity: "AVM-JP", period: "FY2026-P09", book: "ASC606" }, scoped);
    const elsewhere = serve({ entities: [AVM_JP, AVM_UK, AVM_US] });
    open(`/reports/dashboards/revenue?${ALL_CONTEXT}`, scoped);
    expect((await screen.findByTestId("SF-08-dashboard-banner-scope")).textContent).toBe(
      "The entities in scope keep different calendars. Select an entity to see its charts.",
    );
    expect(await screen.findByTestId("SF-08-dashboard-flags")).toBeTruthy();
    expect(elsewhere.posted).toEqual([]);
  });

  it("without a context in the address: the pill's — the member's last entity, period and book — written into it", async () => {
    // SCR-URL-01 rev 1.61 with BR-UX-01: an address that names no entity is not all entities but the
    // pill's context, and the page writes it before a run is asked.
    remember({ entity: "AVM-US", period: "FY2026-P08", book: "ASC606" });
    const served = serve({ entities: [AVM_CA, AVM_US] });
    const app = open("/reports/dashboards/revenue");
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Revenue dashboard · AVM-US · Aug 2026 · ASC 606",
      }),
    ).toBeTruthy();
    await figure("Revenue by category · USD · Aug 2026");
    expect(served.posted).toHaveLength(4);
    const sent = new Map(
      served.posted.map((body) => [
        String(body.report_code),
        body.parameters as Record<string, unknown>,
      ]),
    );
    expect(sent.get("rpo")).toEqual({
      entity_codes: ["AVM-US"],
      book: "ASC606",
      currency_view: "functional",
      period_key: "FY2026-P08",
      row_dimension: "ENTITY",
    });
    await waitFor(() => {
      for (const panel of PANELS) {
        expect(searchOf(app).get(`run.${panel}`)).toBe(runId(panel));
      }
    });
    expect(app.router.state.location.search.split("&run.")[0]).toBe(
      "?entity=AVM-US&period=FY2026-P08&book=ASC606",
    );
    // The links say the context the page shows.
    expect(
      within(screen.getByRole("navigation", { name: "Breadcrumb" }))
        .getByRole("link", { name: "Reports" })
        .getAttribute("href"),
    ).toBe("/reports?entity=AVM-US&period=FY2026-P08&book=ASC606");
    cleanup();

    // Without a last choice: the first entity in code order, the primary book, its earliest open
    // period (BR-UX-01).
    window.localStorage.clear();
    const first = serve({ entities: [AVM_US, AVM_CA] });
    const fresh = open("/reports/dashboards/revenue");
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Revenue dashboard · AVM-CA · Sep 2026 · ASC 606",
      }),
    ).toBeTruthy();
    await waitFor(() => expect(first.posted).toHaveLength(4));
    for (const body of first.posted) {
      expect((body.parameters as Record<string, unknown>).entity_codes).toEqual(["AVM-CA"]);
    }
    await waitFor(() => {
      expect(fresh.router.state.location.search.split("&run.")[0]).toBe(
        "?entity=AVM-CA&period=FY2026-P09&book=ASC606",
      );
    });
  });

  it("a shared link without a context keeps its four runs: the context is filled around them and no run is asked", async () => {
    const runs = PANELS.map((panel) => `run.${panel}=${runId(panel)}`).join("&");
    const served = serve();
    const app = open(`/reports/dashboards/revenue?${runs}`);
    await figure("Revenue by period · USD · ASC 606");
    await figure("Revenue by category · USD · Sep 2026");
    expect(served.posted).toEqual([]);
    expect(app.router.state.location.search).toBe(`?${CONTEXT}&${runs}`);
  });

  it("a new context drops the four runs and makes four new ones", async () => {
    const served = serve(secondRound());
    const app = open(`/reports/dashboards/revenue?${CONTEXT}`);
    await figure("Revenue by category · USD · Sep 2026");
    await waitFor(() => {
      for (const panel of PANELS) {
        expect(searchOf(app).get(`run.${panel}`)).toBe(runId(panel));
      }
    });

    // The pill writes the new period and leaves the rest of the address as it is.
    const search = app.router.state.location.search.replace("FY2026-P09", "FY2026-P08");
    await app.router.navigate({ pathname: "/reports/dashboards/revenue", search });
    await waitFor(() => expect(served.posted).toHaveLength(8));
    const sent = new Map(
      served.posted.slice(4).map((body) => [String(body.report_code), body.parameters]),
    );
    expect(sent.get("rpo")).toMatchObject({ period_key: "FY2026-P08" });
    expect(sent.get("contract_balance_rollforward")).toMatchObject({
      from_period_key: "FY2026-P08",
      to_period_key: "FY2026-P08",
    });
    expect(sent.get("revenue_waterfall")).toMatchObject({ as_of: "2026-08-31" });
    expect(sent.get("disaggregation")).toMatchObject({ to_period_key: "FY2026-P08" });
    await waitFor(() => {
      for (const panel of PANELS) {
        expect(searchOf(app).get(`run.${panel}`)).toBe(runId(panel, 2));
      }
    });
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Revenue dashboard · AVM-US · Aug 2026 · ASC 606",
      }),
    ).toBeTruthy();
  });

  it("a new entity or book does the same, though the calendar is read again in between", async () => {
    // Another entity or book has its own periods: while they load no panel is mounted, and the
    // panels that mount afterwards must not take the runs still in the address for a link's.
    const both = (kept: Entity): Entity =>
      ({
        ...kept,
        books: [
          { book_code: "ASC606", is_enabled: true },
          { book_code: "IFRS15", is_enabled: true },
        ],
      }) as unknown as Entity;
    const cases = [
      {
        from: "entity=AVM-US",
        to: "entity=AVM-UK",
        heading: "Revenue dashboard · AVM-UK · Sep 2026 · ASC 606",
        asked: { entity_codes: ["AVM-UK"], book: "ASC606", period_key: "FY2026-P09" },
      },
      {
        from: "book=ASC606",
        to: "book=IFRS15",
        heading: "Revenue dashboard · AVM-US · Sep 2026 · IFRS 15",
        asked: { entity_codes: ["AVM-US"], book: "IFRS15", period_key: "FY2026-P09" },
      },
      // As the pill writes it (ContextPill `change`): a new entity takes the period out of the
      // address. The page is not mounted while its context is incomplete; the period is filled and
      // the four runs leave the address in the same write (SCREENS_B §0.5, rev 1.92).
      {
        from: "entity=AVM-US&period=FY2026-P09",
        to: "entity=AVM-UK",
        heading: "Revenue dashboard · AVM-UK · Sep 2026 · ASC 606",
        asked: { entity_codes: ["AVM-UK"], book: "ASC606", period_key: "FY2026-P09" },
      },
    ];
    for (const { from, to, heading, asked } of cases) {
      const served = serve({
        ...secondRound(),
        entities: [both(AVM_UK), both(AVM_US)],
        books: ["ASC606", "IFRS15"],
        flagsOf: (code) =>
          code === "AVM-UK" ? [flag(3, "ANOMALY_REVENUE_CHANGE", "SF-ORD-UK-2001")] : [],
      });
      const app = open(`/reports/dashboards/revenue?${CONTEXT}`);
      await figure("Revenue by category · USD · Sep 2026");
      await waitFor(() => {
        for (const panel of PANELS) {
          expect(searchOf(app).get(`run.${panel}`)).toBe(runId(panel));
        }
      });

      const search = app.router.state.location.search.replace(from, to);
      await app.router.navigate({ pathname: "/reports/dashboards/revenue", search });
      expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeTruthy();
      await waitFor(() => expect(served.posted).toHaveLength(8));
      for (const body of served.posted.slice(4)) {
        expect(body.parameters).toMatchObject({
          entity_codes: asked.entity_codes,
          book: asked.book,
        });
      }
      expect(
        served.posted.slice(4).find((body) => body.report_code === "rpo")?.parameters,
      ).toMatchObject(asked);
      await waitFor(() => {
        for (const panel of PANELS) {
          expect(searchOf(app).get(`run.${panel}`)).toBe(runId(panel, 2));
        }
      });
      expect(searchOf(app).get("period")).toBe("FY2026-P09");
      if (to === "entity=AVM-UK") {
        // The flags are the new entity's, and their links say its context.
        expect(new URLSearchParams(served.flagReads.at(-1)).get("entity")).toBe("AVM-UK");
        expect(
          (
            await screen.findByRole("link", { name: "ANOMALY_REVENUE_CHANGE SF-ORD-UK-2001" })
          ).getAttribute("href"),
        ).toBe(
          "/data/exceptions/f0000000-0000-4000-8000-000000000003?entity=AVM-UK&period=FY2026-P09&book=ASC606",
        );
      }
      cleanup();
    }
  });

  it("a context whose panels are not drawn keeps no run in the address", async () => {
    // From AVM-US to all entities, which keep different calendars here: the banner, and the address
    // names the four runs of AVM-US no more.
    const served = serve({ entities: [AVM_JP, AVM_US] });
    const app = open(`/reports/dashboards/revenue?${CONTEXT}`);
    await figure("Revenue by category · USD · Sep 2026");
    await waitFor(() => {
      for (const panel of PANELS) {
        expect(searchOf(app).get(`run.${panel}`)).toBe(runId(panel));
      }
    });
    const search = `${app.router.state.location.search.replace("entity=AVM-US&", "")}&entities=all`;
    await app.router.navigate({ pathname: "/reports/dashboards/revenue", search });
    expect(await screen.findByTestId("SF-08-dashboard-banner-scope")).toBeTruthy();
    await waitFor(() => {
      expect(app.router.state.location.search).toBe(`?${ALL_CONTEXT}`);
    });
    expect(served.posted).toHaveLength(4);
  });

  it("a run answered as the reader leaves its context does not ride on the next writes", async () => {
    // The time bands' creation is answered, and before the address has taken its run the reader moves
    // to another period, where that report is refused. The run of the period left must not come into
    // the address with the other panels' writes.
    let release = (): void => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    let asked = 0;
    serve({
      ...secondRound(),
      createAfter: (code, call) => (code === "rpo" && call === 1 ? held : undefined),
      refuse: {
        rpo: () => {
          asked += 1;
          return asked === 1 ? undefined : problemResponse("forbidden", 403, "Permission denied");
        },
      },
    });
    const app = open(`/reports/dashboards/revenue?${CONTEXT}`);
    const others = ["revenue", "rollforward", "disaggregation"] as const;
    await figure("Revenue by category · USD · Sep 2026");
    await waitFor(() => {
      for (const panel of others) {
        expect(searchOf(app).get(`run.${panel}`)).toBe(runId(panel));
      }
    });
    expect(searchOf(app).get("run.rpo")).toBeNull();

    // The moment the page asks the address to take the run, the reader's navigation overtakes it.
    const search = app.router.state.location.search.replace("FY2026-P09", "FY2026-P08");
    let overtaken = false;
    const stop = app.router.subscribe((state) => {
      if (!overtaken && state.navigation.location?.search.includes("run.rpo=") === true) {
        overtaken = true;
        void app.router.navigate({ pathname: "/reports/dashboards/revenue", search });
      }
    });
    release();
    await waitFor(() => expect(overtaken).toBe(true));
    stop();

    await waitFor(() => {
      expect(
        within(screen.getByTestId("SF-08-chart-dashboard-rpo")).getByText("Permission denied"),
      ).toBeTruthy();
    });
    await waitFor(() => {
      for (const panel of others) {
        expect(searchOf(app).get(`run.${panel}`)).toBe(runId(panel, 2));
      }
    });
    expect(searchOf(app).get("run.rpo")).toBeNull();
    expect(searchOf(app).get("period")).toBe("FY2026-P08");
  });

  it("a refused run says the API's sentence in its panel; the other panels render", async () => {
    const sentence =
      "The functional and reporting views show contracts in the entity's functional currency only.";
    const served = serve({
      refuse: {
        rpo: () =>
          problemResponse("validation-failed", 422, "Check the highlighted fields", {
            detail: "1 field needs attention.",
            errors: [
              { field: "parameters.currency_view", rule_id: "API-C-11", message: sentence },
              { field: "parameters.entity_codes", rule_id: "API-C-11", message: sentence },
            ],
          }),
      },
    });
    const app = open(`/reports/dashboards/revenue?${CONTEXT}`);

    await figure("Revenue by period · USD · ASC 606");
    await figure("Contract liability rollforward · USD");
    await figure("Revenue by category · USD · Sep 2026");
    await waitFor(() => {
      expect(screen.getByTestId("SF-08-chart-dashboard-rpo").textContent).toContain(sentence);
    });
    const refused = screen.getByTestId("SF-08-chart-dashboard-rpo");
    expect(
      within(refused).getByRole("heading", {
        level: 2,
        name: "Remaining performance obligations by time band",
      }),
    ).toBeTruthy();
    // SCREENS SCR-ST-13 in a panel: what was not run in place of the API's title — the panel has no
    // field to highlight — then the detail, each finding once, and the request.
    expect(
      within(refused).getByRole("heading", {
        level: 3,
        name: "Running Remaining performance obligations failed. Nothing was committed.",
      }),
    ).toBeTruthy();
    expect([...refused.querySelectorAll("p")].map((line) => line.textContent)).toEqual([
      "1 field needs attention.",
      sentence,
      "Reference 0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d.",
    ]);
    expect(refused.textContent).not.toContain("Check the highlighted fields");
    expect(within(refused).queryByRole("figure")).toBeNull();
    expect(searchOf(app).get("run.rpo")).toBeNull();
    expect(served.posted).toHaveLength(4);

    // "Retry" asks for that panel's run again, and for no other.
    fireEvent.click(within(refused).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(served.posted).toHaveLength(5));
    expect(served.posted[4]?.report_code).toBe("rpo");
    cleanup();

    // A refusal without findings says its detail; one that states neither says its title, under the
    // panel's.
    const reference = "Reference 0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d.";
    const plain: readonly (readonly [() => Response, readonly string[]])[] = [
      [
        () =>
          problemResponse("validation-failed", 422, "Check the highlighted fields", {
            detail: "This report is not available yet.",
          }),
        ["This report is not available yet.", reference],
      ],
      [
        () => problemResponse("forbidden", 403, "Permission denied"),
        ["Permission denied", reference],
      ],
    ];
    for (const [refusal, lines] of plain) {
      serve({ refuse: { rpo: refusal } });
      open(`/reports/dashboards/revenue?${CONTEXT}`);
      await waitFor(() => {
        expect(
          [...screen.getByTestId("SF-08-chart-dashboard-rpo").querySelectorAll("p")].map(
            (line) => line.textContent,
          ),
        ).toEqual(lines);
      });
      cleanup();
    }
  });

  it("a failed run names its job; retry creates a new run for that panel alone", async () => {
    const failed = reportRun("rollforward", {
      status: "FAILED",
      job_id: JOB_ID,
      problem: { type: "about:blank", title: "The ledger could not be read.", status: 500 },
    } as Partial<ReportRun>);
    const second = secondRound();
    const served = serve({
      runs: { [runId("rollforward")]: failed, ...second.runs },
      rows: second.rows,
    });
    const app = open(`/reports/dashboards/revenue?${CONTEXT}`);

    await figure("Revenue by period · USD · ASC 606");
    const panel = await screen.findByText(
      "Running Contract balance rollforward failed. Nothing was committed.",
    );
    const frame = screen.getByTestId("SF-08-chart-dashboard-rollforward");
    expect(frame.contains(panel)).toBe(true);
    expect(within(frame).getByText("The ledger could not be read.")).toBeTruthy();
    // SCR-ST-12: the job's reference.
    expect(within(frame).getByText("Reference 8e7d6c5b.")).toBeTruthy();
    await figure("Revenue by category · USD · Sep 2026");

    fireEvent.click(within(frame).getByRole("button", { name: "Retry" }));
    await figure("Contract liability rollforward · USD");
    expect(served.posted).toHaveLength(5);
    expect(served.posted[4]?.report_code).toBe("contract_balance_rollforward");
    await waitFor(() => {
      expect(searchOf(app).get("run.rollforward")).toBe(runId("rollforward", 2));
    });
    // The other panels keep the runs they had.
    expect(searchOf(app).get("run.revenue")).toBe(runId("revenue"));
  });

  it("a retry writes on the address as it is, not on what the page once wrote", async () => {
    // The page makes its four runs; a link then brings four others, one of them failed. Its retry
    // must leave the three others of the link where they are.
    const second = secondRound();
    const failedId = "a2000000-0000-4000-8000-00000000000f";
    const failed = {
      ...reportRun("rollforward", { status: "FAILED" } as Partial<ReportRun>),
      id: failedId,
    };
    const served = serve({ runs: { ...second.runs, [failedId]: failed }, rows: second.rows });
    const app = open(`/reports/dashboards/revenue?${CONTEXT}`);
    await figure("Revenue by category · USD · Sep 2026");
    await waitFor(() => {
      for (const panel of PANELS) {
        expect(searchOf(app).get(`run.${panel}`)).toBe(runId(panel));
      }
    });
    // The link's runs are stored ones: three of the second round and the failed one.
    served.posted.length = 0;
    const others = ["revenue", "rpo", "disaggregation"] as const;
    const link = [
      ...others.map((panel) => `run.${panel}=${runId(panel, 2)}`),
      `run.rollforward=${failedId}`,
    ].join("&");
    await app.router.navigate(`/reports/dashboards/revenue?${CONTEXT}&${link}`);
    const frame = await screen.findByText(
      "Running Contract balance rollforward failed. Nothing was committed.",
    );
    expect(served.posted).toEqual([]);

    const panel = frame.closest('[data-testid="SF-08-chart-dashboard-rollforward"]');
    if (!(panel instanceof HTMLElement)) {
      throw new Error("The failed banner is outside its panel");
    }
    fireEvent.click(within(panel).getByRole("button", { name: "Retry" }));
    // The one creation is the report's second; its run takes the failed one's place.
    await waitFor(() => {
      expect(searchOf(app).get("run.rollforward")).toBe(runId("rollforward", 2));
    });
    expect(served.posted.map((body) => body.report_code)).toEqual(["contract_balance_rollforward"]);
    for (const other of others) {
      expect(searchOf(app).get(`run.${other}`)).toBe(runId(other, 2));
    }
  });

  it("refresh makes four new runs", async () => {
    const served = serve(secondRound());
    const app = open(`/reports/dashboards/revenue?${CONTEXT}`);
    await figure("Revenue by category · USD · Sep 2026");
    await waitFor(() => {
      for (const panel of PANELS) {
        expect(searchOf(app).get(`run.${panel}`)).toBe(runId(panel));
      }
    });
    expect(served.posted).toHaveLength(4);
    await waitFor(() => {
      for (const panel of PANELS) {
        expect(
          screen.getByTestId(`SF-08-chart-dashboard-${panel}`).querySelector("[data-volatile]"),
        ).not.toBeNull();
      }
    });

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    // The runs shown are left at once: no panel shows one while the address still names it.
    expect(searchOf(app).get("run.revenue")).toBe(runId("revenue"));
    for (const panel of PANELS) {
      expect(
        screen.getByTestId(`SF-08-chart-dashboard-${panel}`).querySelector("[data-volatile]"),
      ).toBeNull();
    }
    await waitFor(() => expect(served.posted).toHaveLength(8));
    expect(
      served.posted
        .slice(4)
        .map((body) => String(body.report_code))
        .sort(),
    ).toEqual(PANELS.map((panel) => REPORT[panel].code).sort());
    await waitFor(() => {
      for (const panel of PANELS) {
        expect(searchOf(app).get(`run.${panel}`)).toBe(runId(panel, 2));
      }
    });
    // The panels show the new runs.
    await waitFor(() => {
      expect(
        screen.getByTestId("SF-08-chart-dashboard-revenue").querySelector("[data-volatile]")
          ?.textContent,
      ).toBe("Run RPT-000531 · 12 Sep 2026 16:21 UTC");
    });
  });

  it("the bridge leaves out the lines without movement and reports an unbalanced run", async () => {
    serve();
    const runs = PANELS.map((panel) => `run.${panel}=${runId(panel)}`).join("&");
    open(`/reports/dashboards/revenue?${CONTEXT}&${runs}`);
    const bridge = await figure("Contract liability rollforward · USD");
    // The API's order; the five lines of 0.00 between them draw nothing and are left out.
    expect(
      [...bridge.querySelectorAll("rect[data-category]")].map((bar) => [
        bar.getAttribute("data-category"),
        bar.getAttribute("data-tone"),
      ]),
    ).toEqual([
      ["OPENING", "total"],
      ["BILLINGS", "increase"],
      ["REVENUE_FROM_OPENING", "decrease"],
      ["CLOSING", "total"],
    ]);
    fireEvent.click(within(bridge).getByRole("radio", { name: "Table" }));
    expect(
      within(bridge)
        .getAllByRole("row")
        .slice(1)
        .map((row) => [...row.children].map((cell) => cell.textContent)),
    ).toEqual([
      ["Opening balance", "39,708.49"],
      ["Billings", "12,000.00"],
      ["Revenue recognized from the opening balance", "(9,764.38)"],
      ["Closing balance", "41,944.11"],
    ]);
    cleanup();

    // RPT-03: when `TO_ROLLFORWARD_BALANCES` fails, the DS-CH-02 banner stands in place of the plot,
    // with the API's difference — the tie-out states one per currency, and the bridge's is its own.
    const unbalanced = reportRun("rollforward", {
      tie_out_results: [
        { code: "TO_OTHER", result: "PASS", expected: [], actual: [], difference: [] },
        {
          code: "TO_ROLLFORWARD_BALANCES",
          result: "FAIL",
          expected: [money("41944.11")],
          actual: [money("41444.11")],
          difference: [money("1.00", "GBP"), money("500.00")],
        },
      ],
    } as Partial<ReportRun>);
    serve({
      runs: { [runId("rollforward")]: unbalanced },
      rows: { [runId("rollforward")]: rollforwardRows({ ...LIABILITY, OTHER: "500.00" }) },
    });
    open(`/reports/dashboards/revenue?${CONTEXT}&${runs}`);
    const failed = await figure("Contract liability rollforward · USD");
    expect(
      within(failed).getByRole("heading", {
        name: "This rollforward does not balance. Difference USD 500.00.",
      }),
    ).toBeTruthy();
    expect(failed.querySelector("rect[data-category]")).toBeNull();
  });

  it("figures in several currencies are not drawn", async () => {
    serve({
      rows: {
        [runId("rollforward")]: [
          ...rollforwardRows(LIABILITY, "GBP", true),
          ...rollforwardRows(LIABILITY, "USD", true),
        ],
        [runId("disaggregation")]: [
          category("Services", "500.00", "GBP", true),
          category("Services", "80000.00", "USD", true),
          categoryTotal("500.00", "GBP"),
          categoryTotal("80000.00", "USD"),
        ] as unknown as readonly ReportRow[],
      },
    });
    const runs = PANELS.map((panel) => `run.${panel}=${runId(panel)}`).join("&");
    open(`/reports/dashboards/revenue?${CONTEXT}&${runs}`);
    await figure("Revenue by period · USD · ASC 606");
    const sentence = "These figures cannot be drawn as one chart. Open the report to read them.";
    for (const [panel, title, report] of [
      ["rollforward", "Contract liability rollforward", "Contract balance rollforward"],
      ["disaggregation", "Revenue by category", "Disaggregation of revenue"],
    ] as const) {
      await waitFor(() => {
        expect(
          within(screen.getByTestId(`SF-08-chart-dashboard-${panel}`)).getByText(sentence),
        ).toBeTruthy();
      });
      const frame = screen.getByTestId(`SF-08-chart-dashboard-${panel}`);
      expect(within(frame).getByRole("heading", { level: 2, name: title })).toBeTruthy();
      expect(within(frame).queryByRole("figure")).toBeNull();
      // The run and the way to the report stay.
      expect(within(frame).getByRole("link", { name: `Open report: ${report}` })).toBeTruthy();
      expect(frame.querySelector("[data-volatile]")?.textContent).toBe(
        `Run RPT-00043${String(PANELS.indexOf(panel) + 1)} · 12 Sep 2026 16:21 UTC`,
      );
    }
  });

  it("an empty run shows the panel's empty text with its run", async () => {
    serve({ rows: { [runId("rpo")]: [] } });
    const runs = PANELS.map((panel) => `run.${panel}=${runId(panel)}`).join("&");
    open(`/reports/dashboards/revenue?${CONTEXT}&${runs}`);
    // The panel keeps its name without a currency: an empty run states none.
    const name = "Remaining performance obligations by time band";
    await waitFor(() => {
      expect(
        screen.getByRole("figure", { name }).querySelector('[data-chart-view="chart"]')
          ?.textContent,
      ).toBe("No revenue scheduled for this range.");
    });
    const empty = screen.getByRole("figure", { name });
    expect(empty.closest('[data-testid="SF-08-chart-dashboard-rpo"]')).not.toBeNull();
    expect(empty.querySelector("[data-volatile]")?.textContent).toBe(
      "Run RPT-000433 · 12 Sep 2026 16:21 UTC",
    );
    expect(
      within(empty).getByRole("link", { name: "Open report: Remaining performance obligations" }),
    ).toBeTruthy();
  });

  it("a retry that is refused leaves the failed run out of the address", async () => {
    const failed = reportRun("rollforward", { status: "FAILED" } as Partial<ReportRun>);
    const served = serve({
      runs: { [runId("rollforward")]: failed },
      refuse: {
        contract_balance_rollforward: () => problemResponse("forbidden", 403, "Permission denied"),
      },
    });
    const runs = PANELS.map((panel) => `run.${panel}=${runId(panel)}`).join("&");
    const app = open(`/reports/dashboards/revenue?${CONTEXT}&${runs}`);
    await screen.findByText("Running Contract balance rollforward failed. Nothing was committed.");
    fireEvent.click(
      within(screen.getByTestId("SF-08-chart-dashboard-rollforward")).getByRole("button", {
        name: "Retry",
      }),
    );
    await waitFor(() => {
      expect(
        within(screen.getByTestId("SF-08-chart-dashboard-rollforward")).getByText(
          "Permission denied",
        ),
      ).toBeTruthy();
    });
    await waitFor(() => expect(searchOf(app).get("run.rollforward")).toBeNull());
    expect(searchOf(app).get("run.revenue")).toBe(runId("revenue"));
    expect(served.posted.map((body) => body.report_code)).toEqual(["contract_balance_rollforward"]);
  });

  it("a run that is still computing is its panel's loading state until it has succeeded", async () => {
    serve({ running: runId("rpo") });
    const runs = PANELS.map((panel) => `run.${panel}=${runId(panel)}`).join("&");
    open(`/reports/dashboards/revenue?${CONTEXT}&${runs}`);
    await figure("Revenue by period · USD · ASC 606");
    const loading = screen.getByRole("figure", {
      name: "Remaining performance obligations by time band",
    });
    expect(loading.getAttribute("aria-busy")).toBe("true");
    expect(loading.closest('[data-testid="SF-08-chart-dashboard-rpo"]')).not.toBeNull();
    expect(loading.querySelector("[data-volatile]")).toBeNull();
    // The run is read again while it computes (04 API-R-41) and drawn once it has succeeded.
    await screen.findByRole(
      "figure",
      { name: "Remaining performance obligations by time band · USD · ASC 606" },
      { timeout: 10_000 },
    );
  });

  it("a run or rows that cannot be read are the panel's banner; Retry reads again", async () => {
    const runs = PANELS.map((panel) => `run.${panel}=${runId(panel)}`).join("&");
    const cases: readonly (readonly [Read, string])[] = [
      [`run:${runId("rpo")}`, "Could not load the report"],
      [`rows:${runId("rpo")}`, "Could not load the report rows"],
    ];
    for (const [read, title] of cases) {
      const served = serve({ failing: [read] });
      open(`/reports/dashboards/revenue?${CONTEXT}&${runs}`);
      await figure("Revenue by period · USD · ASC 606");
      await waitFor(() => {
        expect(
          within(screen.getByTestId("SF-08-chart-dashboard-rpo")).getByRole("heading", {
            level: 3,
            name: title,
          }),
        ).toBeTruthy();
      });
      const frame = screen.getByTestId("SF-08-chart-dashboard-rpo");
      expect(
        within(frame).getByRole("heading", {
          level: 2,
          name: "Remaining performance obligations by time band",
        }),
      ).toBeTruthy();
      expect(within(frame).getByText("Internal Server Error")).toBeTruthy();
      expect(
        within(frame).getByText("Reference 0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d."),
      ).toBeTruthy();
      // The other panels stand; the retry reads the stored run again and creates none.
      await figure("Revenue by category · USD · Sep 2026");
      fireEvent.click(within(frame).getByRole("button", { name: "Retry" }));
      await figure("Remaining performance obligations by time band · USD · ASC 606");
      expect(served.posted).toEqual([]);
      cleanup();
    }
  });

  it("the reports' catalogue: unread, one banner beside the flags; a report it lacks has no panel", async () => {
    const served = serve({ failing: ["definitions"] });
    open(`/reports/dashboards/revenue?${CONTEXT}`);
    const page = await screen.findByTestId("SF-08-page");
    expect(
      await within(page).findByRole("heading", { level: 2, name: "Could not load the dashboard" }),
    ).toBeTruthy();
    expect(within(page).getByText("Internal Server Error")).toBeTruthy();
    expect(await screen.findByTestId("SF-08-dashboard-flags")).toBeTruthy();
    for (const panel of PANELS) {
      expect(screen.queryByTestId(`SF-08-chart-dashboard-${panel}`)).toBeNull();
    }
    expect(served.posted).toEqual([]);
    fireEvent.click(within(page).getByRole("button", { name: "Retry" }));
    await figure("Revenue by period · USD · ASC 606");
    cleanup();

    // A report the member's catalogue does not hold has no panel and no run (SCR-PERM-02).
    const partial = serve({
      definitions: DEFINITIONS.filter((definition) => definition.code !== "rpo"),
    });
    open(`/reports/dashboards/revenue?${CONTEXT}`);
    await figure("Revenue by period · USD · ASC 606");
    await figure("Contract liability rollforward · USD");
    await figure("Revenue by category · USD · Sep 2026");
    expect(screen.queryByTestId("SF-08-chart-dashboard-rpo")).toBeNull();
    expect(partial.posted.map((body) => String(body.report_code)).sort()).toEqual([
      "contract_balance_rollforward",
      "disaggregation",
      "revenue_waterfall",
    ]);
  });

  it("the entities cannot be read: the page's banner, and Retry reads again", async () => {
    // With its context in the address, and without one — where the entities are what fills it and
    // no run is asked on half a context.
    for (const address of [
      `/reports/dashboards/revenue?${CONTEXT}`,
      "/reports/dashboards/revenue",
    ]) {
      const served = serve({ failing: ["entities"] });
      const app = open(address);
      const page = await screen.findByTestId("SF-08-page");
      expect(
        await within(page).findByRole("heading", {
          level: 2,
          name: "Could not load the dashboard",
        }),
      ).toBeTruthy();
      expect(within(page).getByText("Internal Server Error")).toBeTruthy();
      expect(
        within(page).getByText("Reference 0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d."),
      ).toBeTruthy();
      expect(screen.queryByTestId("SF-08-dashboard-flags")).toBeNull();
      expect(served.posted).toEqual([]);
      fireEvent.click(within(page).getByRole("button", { name: "Retry" }));
      await figure("Revenue by period · USD · ASC 606");
      expect(served.posted).toHaveLength(4);
      expect(searchOf(app).get("entity")).toBe("AVM-US");
      cleanup();
    }
  });

  it("a workspace without a period to report on says so", async () => {
    for (const world of [{ periods: [] }, { entities: [] }]) {
      const served = serve(world);
      open("/reports/dashboards/revenue");
      expect(
        await screen.findByRole("heading", { level: 2, name: "No period to report on" }),
      ).toBeTruthy();
      expect(
        screen.getByText("No entity of this workspace keeps a book with periods."),
      ).toBeTruthy();
      expect(screen.queryByTestId("SF-08-dashboard-flags")).toBeNull();
      expect(served.posted).toEqual([]);
      cleanup();
    }
  });

  it("the flags do not wait for the charts and are not mounted again when the charts arrive", async () => {
    let release = (): void => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    serve({ definitionsAfter: held });
    open(`/reports/dashboards/revenue?${CONTEXT}`);
    const flags = await screen.findByRole("region", { name: "Open anomaly flags (0)" });
    expect(document.querySelector('[data-testid^="SF-08-chart-dashboard-"]')).toBeNull();
    release();
    await figure("Revenue by period · USD · ASC 606");
    expect(screen.getByTestId("SF-08-dashboard-flags")).toBe(flags);
  });

  it("flags that cannot be read are the panel's banner under its plain heading", async () => {
    serve({ failing: ["flags"] });
    const runs = PANELS.map((panel) => `run.${panel}=${runId(panel)}`).join("&");
    open(`/reports/dashboards/revenue?${CONTEXT}&${runs}`);
    // No count is known, so the heading states none.
    const panel = await screen.findByRole("region", { name: "Open anomaly flags" });
    expect(
      await within(panel).findByRole("heading", {
        level: 3,
        name: "Could not load the anomaly flags",
      }),
    ).toBeTruthy();
    expect(within(panel).getByText("Internal Server Error")).toBeTruthy();
    expect(within(panel).queryByRole("link")).toBeNull();
    // The charts do not wait for the flags.
    await figure("Revenue by category · USD · Sep 2026");
    fireEvent.click(within(panel).getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("region", { name: "Open anomaly flags (0)" })).toBeTruthy();
  });

  it("the flags panel lists the open anomaly flags with their count", async () => {
    const served = serve({
      flags: [
        flag(1, "ANOMALY_REVENUE_CHANGE", "BG-AVM-0004", "bg-avm-0004/2026-09"),
        flag(2, "ANOMALY_NEGATIVE_REVENUE", null),
        flag(3, "ANOMALY_REVENUE_CHANGE", null, "inv-2026-0917"),
      ],
      flagCount: 11,
    });
    const runs = PANELS.map((panel) => `run.${panel}=${runId(panel)}`).join("&");
    open(`/reports/dashboards/revenue?${CONTEXT}&${runs}`);

    const panel = await screen.findByRole("region", { name: "Open anomaly flags (11)" });
    expect(panel.getAttribute("data-testid")).toBe("SF-08-dashboard-flags");
    // §5.5: `source=ANOMALY`, the open statuses, the context entity, eight items and the count.
    const read = new URLSearchParams(served.flagReads[0]);
    expect(read.getAll("source")).toEqual(["ANOMALY"]);
    expect(read.getAll("status")).toEqual(["OPEN", "IN_PROGRESS"]);
    expect(read.get("entity")).toBe("AVM-US");
    expect(read.get("limit")).toBe("8");
    expect(read.get("count")).toBe("true");
    expect(read.get("period")).toBeNull();

    const items = within(panel).getAllByRole("listitem");
    // The code, then the record: the contract, else the record's business key, else nothing.
    expect(items.map((item) => item.textContent)).toEqual([
      "WarningANOMALY_REVENUE_CHANGE BG-AVM-0004",
      "WarningANOMALY_NEGATIVE_REVENUE",
      "WarningANOMALY_REVENUE_CHANGE inv-2026-0917",
    ]);
    expect(
      within(panel)
        .getByRole("link", { name: "ANOMALY_REVENUE_CHANGE BG-AVM-0004" })
        .getAttribute("href"),
    ).toBe(`/data/exceptions/f0000000-0000-4000-8000-000000000001?${CONTEXT}`);
    // "View all" opens the list the count counts; the queue adds its own Status chip.
    expect(within(panel).getByRole("link", { name: "View all" }).getAttribute("href")).toBe(
      `/data/exceptions?${CONTEXT}&f.source=is:ANOMALY&f.entity=is:AVM-US`,
    );
    cleanup();

    // No flag: the sentence, the heading with its zero, and no link to an empty list.
    serve();
    open(`/reports/dashboards/revenue?${CONTEXT}&${runs}`);
    const none = await screen.findByRole("region", { name: "Open anomaly flags (0)" });
    expect(within(none).getByText("No open anomaly flags")).toBeTruthy();
    expect(within(none).queryByRole("link")).toBeNull();
  });

  it("a mark opens its report with the panel's run; a period opens the schedules", async () => {
    serve();
    const runs = PANELS.map((panel) => `run.${panel}=${runId(panel)}`).join("&");
    const app = open(`/reports/dashboards/revenue?${CONTEXT}&${runs}`);

    const bars = await figure("Revenue by category · USD · Sep 2026");
    // DS-VIZ-03: the largest first, whatever the builder's order.
    expect(
      [...bars.querySelectorAll("rect[data-category]")].map((bar) =>
        bar.getAttribute("data-category"),
      ),
    ).toEqual(["Subscription", "Services", "Products", "Licences"]);
    // The Table view names its columns and ends with the run's own total.
    fireEvent.click(within(bars).getByRole("radio", { name: "Table" }));
    expect(
      within(bars)
        .getAllByRole("columnheader")
        .map((cell) => cell.textContent),
    ).toEqual(["Revenue category", "Amount (USD)"]);
    expect(within(bars).getAllByRole("row").at(-1)?.textContent).toBe("Total290,000.00");
    fireEvent.click(within(bars).getByRole("radio", { name: "Chart" }));
    const services = bars.querySelector('rect[data-category="Services"]');
    if (services === null) {
      throw new Error("No bar for Services");
    }
    fireEvent.click(services);
    await waitFor(() => {
      expect(app.router.state.location.pathname).toBe("/reports/disaggregation");
    });
    const report = searchOf(app);
    expect(report.get("run")).toBe(runId("disaggregation"));
    expect(report.get("p.include_timing")).toBe("false");
    expect(report.get("currency_view")).toBe("functional");
    cleanup();

    serve();
    const again = open(`/reports/dashboards/revenue?${CONTEXT}&${runs}`);
    const waterfall = await figure("Revenue by period · USD · ASC 606");
    const column = waterfall.querySelector('[data-period="FY2026-P08"]');
    if (column === null) {
      throw new Error("No column for Aug 2026");
    }
    fireEvent.click(column);
    await waitFor(() => {
      expect(again.router.state.location.pathname).toBe("/schedules");
    });
    expect(again.router.state.location.search).toBe("?entity=AVM-US&period=FY2026-P08&book=ASC606");
    cleanup();

    // A bar of the bridge and a band of the time bands open their reports with the panel's run.
    for (const [name, mark, path, panel] of [
      [
        "Contract liability rollforward · USD",
        'rect[data-category="BILLINGS"]',
        "/reports/contract_balance_rollforward",
        "rollforward",
      ],
      [
        "Remaining performance obligations by time band · USD · ASC 606",
        'rect[data-row="entity:AVM-US"]',
        "/reports/rpo",
        "rpo",
      ],
    ] as const) {
      serve();
      const page = open(`/reports/dashboards/revenue?${CONTEXT}&${runs}`);
      const chart = await figure(name);
      const target = chart.querySelector(mark);
      if (target === null) {
        throw new Error(`No mark ${mark}`);
      }
      fireEvent.click(target);
      await waitFor(() => {
        expect(page.router.state.location.pathname).toBe(path);
      });
      expect(searchOf(page).get("run")).toBe(runId(panel));
      cleanup();
    }
  });

  it("a slow run is not announced by the panels", async () => {
    // Every run takes longer than the two seconds after which the report view says "Report … ran.":
    // the clock moves three seconds on while a creation is answered.
    const clock = Date.now.bind(Date);
    let late = 0;
    vi.spyOn(Date, "now").mockImplementation(() => clock() + late);
    const slow = { onCreate: () => (late += 3_000) };
    serve(slow);
    open(`/reports/dashboards/revenue?${CONTEXT}`);
    await figure("Revenue by period · USD · ASC 606");
    await figure("Contract liability rollforward · USD");
    await figure("Remaining performance obligations by time band · USD · ASC 606");
    await figure("Revenue by category · USD · Sep 2026");
    expect(screen.queryByText(/ran\./)).toBeNull();
    cleanup();

    // The report view itself still says it (SCREENS_B §5.2): the option is the dashboard's alone.
    serve(slow);
    open(`/reports/rpo?${CONTEXT}`);
    expect(
      await screen.findByText("Report Remaining performance obligations ran. 2 rows."),
    ).toBeTruthy();
  });

  it("links only to what is built (XR-14)", async () => {
    const without = (...ids: readonly string[]) =>
      SCREEN_ROUTES.filter((route) => route.id === undefined || !ids.includes(route.id));
    const runs = PANELS.map((panel) => `run.${panel}=${runId(panel)}`).join("&");
    serve({ flags: [flag(1, "ANOMALY_REVENUE_CHANGE", "BG-AVM-0004")] });
    const app = renderApp(`/reports/dashboards/revenue?${CONTEXT}&${runs}`, {
      me: ROBERT,
      screenRoutes: without("SF-08:report", "SF-04", "SF-11", "SF-11:item"),
    });
    const bars = await figure("Revenue by category · USD · Sep 2026");
    const waterfall = await figure("Revenue by period · USD · ASC 606");
    const bridge = await figure("Contract liability rollforward · USD");
    const bands = await figure("Remaining performance obligations by time band · USD · ASC 606");
    // Each run is still stated; no link leads to a report view that is not there.
    expect(bars.querySelector("[data-volatile]")?.textContent).toBe(
      "Run RPT-000434 · 12 Sep 2026 16:21 UTC",
    );
    expect(screen.queryByRole("link", { name: /^Open report/ })).toBeNull();
    // The flags are text, and there is no list to view.
    const flags = await screen.findByRole("region", { name: "Open anomaly flags (1)" });
    expect(within(flags).getByRole("listitem").textContent).toBe(
      "WarningANOMALY_REVENUE_CHANGE BG-AVM-0004",
    );
    expect(within(flags).queryByRole("link")).toBeNull();
    // A mark opens nothing: no schedules, no report.
    for (const mark of [
      bars.querySelector('rect[data-category="Services"]'),
      waterfall.querySelector('[data-period="FY2026-P08"]'),
      bridge.querySelector('rect[data-category="BILLINGS"]'),
      bands.querySelector('rect[data-row="entity:AVM-US"]'),
    ]) {
      if (mark === null) {
        throw new Error("A mark is missing");
      }
      fireEvent.click(mark);
      expect(app.router.state.location.pathname).toBe("/reports/dashboards/revenue");
      expect(app.router.state.navigation.state).toBe("idle");
    }
    cleanup();

    // The catalogue lists no dashboard while the page is not built.
    serve();
    renderApp(`/reports?${CONTEXT}`, { me: ROBERT, screenRoutes: without("SF-08:dashboard") });
    expect(await screen.findByRole("heading", { name: "Recent runs" })).toBeTruthy();
    expect(screen.queryByTestId("SF-08-dashboards")).toBeNull();
    expect(screen.queryByRole("link", { name: "Revenue dashboard" })).toBeNull();
  });

  it("the catalogue lists the dashboard with the page's context", async () => {
    serve();
    open(`/reports?${CONTEXT}&q=rollforward`);
    const list = await screen.findByRole("region", { name: "Dashboards" });
    expect(list.getAttribute("data-testid")).toBe("SF-08-dashboards");
    const items = within(list).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      "Revenue dashboardRevenue, balances, RPO and anomaly flags",
    ]);
    // The context of the pill, and nothing of the catalogue's own search.
    expect(within(list).getByRole("link", { name: "Revenue dashboard" }).getAttribute("href")).toBe(
      `/reports/dashboards/revenue?${CONTEXT}`,
    );
  });
});

describe("the page's writes to the address", () => {
  type Write = (changes: Readonly<Record<string, string | null>>) => void;

  /** A component under the writer's that writes from an effect of its own. */
  function Follower({ write, period }: { readonly write: Write; readonly period: string }) {
    useEffect(() => {
      write({ "p.seen": period });
    }, [write, period]);
    return null;
  }

  function Page() {
    const location = useLocation();
    const params = new URLSearchParams(location.search);
    const write = useSearchWriter();
    return (
      <>
        <Follower write={write} period={params.get("period") ?? ""} />
        <button
          type="button"
          onClick={() => {
            write({ "run.revenue": "r1" });
            write({ "run.rpo": "r2" });
          }}
        >
          Two runs
        </button>
        <button type="button" onClick={() => write({ "run.rollforward": "r3" })}>
          One more
        </button>
      </>
    );
  }

  /** The route has a loader, as the dashboard's has: a navigation is committed after it, not at once. */
  function mount(path: string) {
    const router = createMemoryRouter([{ path: "/", element: <Page />, loader: () => null }], {
      initialEntries: [path],
    });
    render(<RouterProvider router={router} />);
    return router;
  }

  function shown(router: ReturnType<typeof mount>): Record<string, string> {
    return Object.fromEntries(new URLSearchParams(router.state.location.search));
  }

  it("writes close together all arrive, on the address the router holds", async () => {
    const router = mount("/?entity=AVM-US&period=FY2026-P09");
    await waitFor(() => expect(shown(router)["p.seen"]).toBe("FY2026-P09"));
    // A write replaces the entry of the history; it adds none.
    expect(router.state.historyAction).toBe("REPLACE");

    // The reader moves to another period. The write an effect makes in that render is made on the
    // new address: on the one the page rendered before it would put the old period back.
    await act(async () => {
      await router.navigate("/?entity=AVM-US&period=FY2026-P08&p.seen=FY2026-P09");
    });
    await waitFor(() => {
      expect(shown(router)).toEqual({
        entity: "AVM-US",
        period: "FY2026-P08",
        "p.seen": "FY2026-P08",
      });
    });

    // Two writes before the first is committed: the second carries the first.
    fireEvent.click(screen.getByRole("button", { name: "Two runs" }));
    await waitFor(() => {
      expect(shown(router)).toMatchObject({ "run.revenue": "r1", "run.rpo": "r2" });
    });

    // Nothing is kept of a write once it is made: the reader opens an address without one of the
    // runs, and a later write does not bring it back.
    await act(async () => {
      await router.navigate("/?entity=AVM-US&period=FY2026-P08&p.seen=FY2026-P08&run.rpo=r2");
    });
    fireEvent.click(screen.getByRole("button", { name: "One more" }));
    await waitFor(() => expect(shown(router)["run.rollforward"]).toBe("r3"));
    expect(shown(router)).toEqual({
      entity: "AVM-US",
      period: "FY2026-P08",
      "p.seen": "FY2026-P08",
      "run.rpo": "r2",
      "run.rollforward": "r3",
    });
  });

  it("a write the reader's navigation overtakes does not travel with the next one", async () => {
    const router = mount("/?entity=AVM-US&period=FY2026-P09");
    await waitFor(() => expect(shown(router)["p.seen"]).toBe("FY2026-P09"));

    // A write, and before it is committed the reader's own navigation to another entity.
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "One more" }));
      await router.navigate("/?entity=AVM-UK&period=FY2026-P09");
    });
    expect(shown(router)).toEqual({ entity: "AVM-UK", period: "FY2026-P09" });

    fireEvent.click(screen.getByRole("button", { name: "Two runs" }));
    await waitFor(() => expect(shown(router)["run.rpo"]).toBe("r2"));
    expect(shown(router)).toEqual({
      entity: "AVM-UK",
      period: "FY2026-P09",
      "run.revenue": "r1",
      "run.rpo": "r2",
    });
  });
});

describe("the charts' figures", () => {
  it("bridgeOf reads the contract liability column in the API's order", () => {
    expect(bridgeOf(rollforwardRows(LIABILITY))).toEqual({
      currency: "USD",
      categories: [
        { key: "OPENING", label: "Opening balance", kind: "TOTAL", amount: "39708.49" },
        { key: "BILLINGS", label: "Billings", kind: "ACTIVITY", amount: "12000.00" },
        {
          key: "REVENUE_FROM_OPENING",
          label: "Revenue recognized from the opening balance",
          kind: "ACTIVITY",
          amount: "-9764.38",
        },
        { key: "CLOSING", label: "Closing balance", kind: "TOTAL", amount: "41944.11" },
      ],
    });
    // A balance of 0.00 is still a total: opening and closing always stand.
    expect(bridgeOf(rollforwardRows({}))?.categories.map((item) => item.key)).toEqual([
      "OPENING",
      "CLOSING",
    ]);
    // Several currencies, or no rows, make no bridge.
    expect(
      bridgeOf([
        ...rollforwardRows(LIABILITY, "GBP", true),
        ...rollforwardRows(LIABILITY, "USD", true),
      ]),
    ).toBeNull();
    expect(bridgeOf([])).toBeNull();
  });

  it("categoriesOf takes each row's total and the run's own total", () => {
    const [licences, products, services, subscription, total] = CATEGORY_ROWS;
    const section = {
      number: 1,
      heading: "Disaggregation of revenue",
      rows: [licences, products, services, subscription].filter((row) => row !== undefined),
      totals: total === undefined ? [] : [total],
    };
    expect(categoriesOf(section)).toEqual({
      currency: "USD",
      total: "290000.00",
      categories: [
        { key: "Licences", label: "Licences", amount: "20000.00" },
        { key: "Products", label: "Products", amount: "40000.00" },
        { key: "Services", label: "Services", amount: "80000.00" },
        { key: "Subscription", label: "Subscription", amount: "150000.00" },
      ],
    });
    // The label is the row's own, whatever its key; a row of the nonpublic election has no
    // dimension label, and its timing names it.
    const keyed = {
      ...category("Services", "290000.00"),
      row_key: "revenue_category:SVC",
      timing: "Over time",
    } as unknown as ReportRow;
    const timing = {
      row_key: "timing:OVER_TIME",
      dimension_value_label: null,
      timing: "Over time",
      total: money("290000.00"),
    } as unknown as ReportRow;
    expect(categoriesOf({ ...section, rows: [keyed] })?.categories).toEqual([
      { key: "revenue_category:SVC", label: "Services", amount: "290000.00" },
    ]);
    expect(categoriesOf({ ...section, rows: [timing] })?.categories).toEqual([
      { key: "timing:OVER_TIME", label: "Over time", amount: "290000.00" },
    ]);
    // Two totals rows are two currencies; a row in another currency than the total's is refused too.
    expect(categoriesOf({ ...section, totals: [...section.totals, ...section.totals] })).toBeNull();
    expect(
      categoriesOf({
        ...section,
        rows: [category("Services", "500.00", "GBP") as unknown as ReportRow],
      }),
    ).toBeNull();
    expect(categoriesOf({ ...section, totals: [] })).toBeNull();
  });
});
