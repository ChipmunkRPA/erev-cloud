// @vitest-environment jsdom
// SF-04 Schedules (BUILD_SPEC RPS-7; SCREENS_B §4.1, §0.5; §5.6 RPT-01; SCREENS SCR-URL-18, SCR-URL-24;
// PRD WLD-P-05; DESIGN_SYSTEM DS-FMT-03, DS-FMT-19): fiscal quarter column labels, the `layout=lines`
// binding of `GET /schedule-lines`, the "Flags" column of open anomaly flags, and the As locked source that
// keeps "Run report" and "Rerun from the same source" (D-88 L7-3-Q-2) and makes the bar's fields
// unavailable (RV-04 rev 1.98). API answers are contract fakes of 04 API-R-18, API-R-35, API-R-41 and
// API-R-44 (V-C); a creation that names a lock is answered by the API's own rule (DG-FE-18).
import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../../app/router";
import type { ReportDefinition, ReportRow, ReportRun } from "../../../lib/api/queries/reports";
import type { ScheduleLine } from "../../../lib/api/queries/schedule-lines";
import type { Period } from "../../../lib/api/queries/tenant";
import { installMemoryStorage, renderApp, signedInMe } from "../../../test/app";
import { AS_LOCKED, asLockedRefusal } from "../../../test/as-locked";
import { installGridViewport } from "../../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";

installMswServer();
installMemoryStorage();
installGridViewport();
// The screen reads the definition, the calendar and the run before its rows render.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
});

const MARCUS = signedInMe({
  permissions: ["contract.read", "config.read", "report.run", "report.export"],
});

const RUN_ID = "4a0c7a1e-3d2f-4e6a-9b8c-7d6e5f4a3b2c";
const JOB_ID = "8e7d6c5b-4a3f-4e2d-9c1b-0a9f8e7d6c5c";

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
  output_formats: ["XLSX", "CSV", "PDF", "JSON"],
  tie_outs: ["TO_WATERFALL_EQ_JE_REVENUE"],
  ipe_logic: null,
};

interface EntityRef {
  readonly id: string;
  readonly code: string;
  readonly name: string;
}

const AVM_US: EntityRef = {
  id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000001",
  code: "AVM-US",
  name: "Avenmoor US Inc.",
};
const AVM_JP: EntityRef = {
  id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000004",
  code: "AVM-JP",
  name: "Avenmoor Japan KK",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** A calendar of twelve monthly periods starting at `startMonth` of `startYear` (WLD-P-05). */
function calendar(entity: EntityRef, fiscalYear: number, startYear: number, startMonth: number) {
  return Array.from({ length: 12 }, (_, index): Period => {
    const month = ((startMonth - 1 + index) % 12) + 1;
    const year = startYear + Math.floor((startMonth - 1 + index) / 12);
    const mm = String(month).padStart(2, "0");
    // 2026 and 2027 are not leap years (DG-FE-20: no Date construction outside src/lib/format).
    const last = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1] ?? 30;
    const number = String(index + 1).padStart(2, "0");
    return {
      id: `1c2d3e4f-5a6b-4c7d-8e9f-${entity.code === "AVM-JP" ? "1" : "0"}a1b2c3d4e${number}`,
      entity,
      book: "ASC606",
      period: {
        id: `2c2d3e4f-5a6b-4c7d-8e9f-${entity.code === "AVM-JP" ? "1" : "0"}a1b2c3d4e${number}`,
        period_key: `FY${String(fiscalYear)}-P${number}`,
        name: `${MONTHS[month - 1] ?? ""} ${String(year)}`,
        fiscal_year: fiscalYear,
        period_no: index + 1,
        quarter_no: Math.floor(index / 3) + 1,
        start_date: `${String(year)}-${mm}-01`,
        end_date: `${String(year)}-${mm}-${String(last)}`,
      },
      state:
        `${String(year)}-${mm}` < "2026-09"
          ? "closing"
          : `${String(year)}-${mm}` === "2026-09"
            ? "open"
            : "future",
      is_first_open: `${String(year)}-${mm}` === "2026-09",
      row_version: 1,
      state_changed_at: "2026-09-03T09:14:00Z",
      close_run: null,
      current_lock: null,
      blockers: {},
    } as unknown as Period;
  });
}

function reportRun(overrides: Partial<ReportRun> = {}): ReportRun {
  return {
    id: RUN_ID,
    report_run_no: "RPT-000388",
    report: { code: "revenue_waterfall", version: 1, name: "Revenue waterfall" },
    status: "SUCCEEDED",
    parameters: {
      entity_codes: ["AVM-US"],
      book: "ASC606",
      from_period_key: "FY2026-P01",
      to_period_key: "FY2026-P12",
      as_of: "2026-09-30",
      row_dimension: "CONTRACT",
      granularity: "MONTH",
      measure: "TOTAL",
    },
    entity_scope: [AVM_US],
    book: "ASC606",
    as_of: "2026-09-30",
    known_at: "2026-09-12T16:02:00Z",
    period_lock_id: null,
    engine_release: {
      engine_version: "1.0.0",
      build_sha: "3f9a1c22e41b7d0c5a6f8e9d0b1c2a3f4e5d6c7b",
    },
    row_count: 1,
    control_totals: {
      recognized_total: { USD: "9764.38" },
      scheduled_total: { USD: "0.00" },
      awaiting_trigger_total: { USD: "0.00" },
    },
    tie_out_results: [],
    ledger_heads: {},
    output: null,
    problem: null,
    run_by: {
      id: "7d6c5b4a-3f2e-4d1c-8b0a-9f8e7d6c5b4a",
      display_name: "Marcus Webb",
      kind: "USER",
    },
    started_at: "2026-09-12T16:02:11Z",
    finished_at: "2026-09-12T16:02:19Z",
    ...overrides,
  } as ReportRun;
}

interface Served {
  readonly posted: Record<string, unknown>[];
  readonly lineRequests: URL[];
  readonly flagRequests: URL[];
}

function serve(options: {
  readonly periods: readonly Period[];
  readonly run: ReportRun;
  readonly rows: readonly ReportRow[];
  readonly lines?: readonly ScheduleLine[];
  readonly flags?: readonly Readonly<Record<string, unknown>>[];
}): Served {
  const posted: Record<string, unknown>[] = [];
  const lineRequests: URL[] = [];
  const flagRequests: URL[] = [];
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
          { code: "JPY", name: "Yen", minor_unit: 0, numeric_code: "392", is_active: true },
        ],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/jobs"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/periods"), () =>
      HttpResponse.json({ items: options.periods, next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/report-definitions/:code"), () => HttpResponse.json(WATERFALL)),
    http.get(apiUrl("/api/v1/report-runs/:runId"), () => HttpResponse.json(options.run)),
    http.get(apiUrl("/api/v1/report-runs/:runId/data"), () =>
      HttpResponse.json({ items: options.rows, next_cursor: null }),
    ),
    http.post(apiUrl("/api/v1/report-runs"), async ({ request }) => {
      const body = (await request.json()) as {
        readonly report_code: string;
        readonly parameters: Record<string, unknown>;
      };
      posted.push(body);
      // A creation that names a lock is answered as the API answers it (DG-FE-18): refused where
      // `locked.reconcile_selectors` refuses its parameters.
      const refusal = asLockedRefusal(body.report_code, body.parameters, [AS_LOCKED.lock]);
      if (refusal !== null) {
        return refusal;
      }
      return HttpResponse.json(
        { id: JOB_ID, kind: "REPORT_RUN", state: "QUEUED" },
        {
          status: 202,
          headers: { Location: `/api/v1/jobs/${JOB_ID}`, "X-Erev-Report-Run-Id": RUN_ID },
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
      lineRequests.push(new URL(request.url));
      return HttpResponse.json(
        { items: options.lines ?? [], next_cursor: null },
        { headers: { "X-Total-Count": String(options.lines?.length ?? 0) } },
      );
    }),
    http.get(apiUrl("/api/v1/exceptions"), ({ request }) => {
      flagRequests.push(new URL(request.url));
      return HttpResponse.json({ items: options.flags ?? [], next_cursor: null });
    }),
  );
  return { posted, lineRequests, flagRequests };
}

const US_CONTEXT = "entity=AVM-US&period=FY2026-P09&book=ASC606";

const US_ROWS: readonly ReportRow[] = [
  {
    row_key: "contract:SF-ORD-10001",
    contract_external_id: "SF-ORD-10001",
    customer_name: "Pellworth Analytics",
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
];

describe("SF-04 Schedules", () => {
  it("fiscal quarter labels", async () => {
    const jp = calendar(AVM_JP, 2027, 2026, 4);
    const { posted } = serve({
      periods: jp,
      run: reportRun({
        parameters: {
          entity_codes: ["AVM-JP"],
          book: "ASC606",
          from_period_key: "FY2027-P01",
          to_period_key: "FY2027-P12",
          as_of: "2026-09-30",
          row_dimension: "CONTRACT",
          granularity: "QUARTER",
          measure: "TOTAL",
        },
        entity_scope: [AVM_JP],
        control_totals: {
          recognized_total: { JPY: "50000000" },
          scheduled_total: { JPY: "5000000" },
          awaiting_trigger_total: { JPY: "0" },
        },
      }),
      rows: [
        {
          row_key: "contract:JP-LIC-0001",
          contract_external_id: "JP-LIC-0001",
          customer_name: "Kurobane Systems",
          entity_code: "AVM-JP",
          "period:FY2027-Q1": money("50000000", "JPY"),
          "period:FY2027-Q2": money("5000000", "JPY"),
          awaiting_trigger: money("0", "JPY"),
          total: money("55000000", "JPY"),
        },
      ],
    });
    renderApp("/schedules?entity=AVM-JP&book=ASC606&granularity=quarter", {
      me: MARCUS,
      screenRoutes: SCREEN_ROUTES,
    });

    expect(await screen.findByRole("heading", { level: 1, name: "Schedules" })).toBeTruthy();
    // SCR-URL-24: the screen parameter reaches the run in uppercase over the context fiscal year.
    await waitFor(() => {
      expect(posted[0]).toMatchObject({
        report_code: "revenue_waterfall",
        output_format: "JSON",
        parameters: {
          entity_codes: ["AVM-JP"],
          book: "ASC606",
          from_period_key: "FY2027-P01",
          to_period_key: "FY2027-P12",
          granularity: "QUARTER",
          row_dimension: "CONTRACT",
          measure: "TOTAL",
        },
      });
    });
    const row = await screen.findByTestId("SF-04-row-jp-lic-0001");
    const grid = screen.getByTestId("SF-04-grid-waterfall");
    const headers = within(grid)
      .getAllByRole("columnheader")
      .map((header) => header.textContent ?? "");
    // WLD-P-05: an April fiscal year labels its quarters "FY2027 Q1", not a calendar quarter.
    expect(headers.some((header) => header.startsWith("FY2027 Q1 (JPY)"))).toBe(true);
    expect(headers.some((header) => header.startsWith("FY2027 Q2 (JPY)"))).toBe(true);
    expect(headers.some((header) => header.startsWith("Q1 2026"))).toBe(false);
    // DS-FMT-03: JPY has no minor unit.
    expect(row.textContent).toContain("50,000,000");
    expect(row.textContent).not.toContain("50,000,000.00");
  });

  it("lines layout binds schedule lines", async () => {
    const line = {
      id: "6f5e4d3c-2b1a-4c0d-9e8f-7a6b5c4d3e2f",
      contract_version_id: "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d",
      schedule_kind: "REVENUE",
      obligation_key: "O1",
      entity: AVM_US,
      period: {
        id: "2c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e09",
        period_key: "FY2026-P09",
        name: "Sep 2026",
        end_date: "2026-09-30",
      },
      line_type: "NORMAL",
      state: "SCHEDULED",
      amount: money("9764.38"),
      cumulative_amount: money("87879.42"),
      quantity: null,
      links: {
        explain: "/api/v1/explain/schedule_line/6f5e4d3c-2b1a-4c0d-9e8f-7a6b5c4d3e2f/amount",
      },
    } as unknown as ScheduleLine;
    const { posted, lineRequests } = serve({
      periods: calendar(AVM_US, 2026, 2026, 1),
      run: reportRun(),
      rows: US_ROWS,
      lines: [line],
    });
    renderApp(`/schedules?${US_CONTEXT}&layout=lines`, { me: MARCUS, screenRoutes: SCREEN_ROUTES });

    const grid = await screen.findByTestId("SF-04-grid-lines");
    expect(within(grid).getByRole("grid", { name: "Schedule lines" })).toBeTruthy();
    await waitFor(() => {
      expect(lineRequests.length).toBeGreaterThan(0);
    });
    const request = lineRequests[0]?.searchParams;
    expect(request?.get("entity")).toBe("AVM-US");
    expect(request?.get("book")).toBe("ASC606");
    expect(request?.get("from_period")).toBe("FY2026-P01");
    expect(request?.get("to_period")).toBe("FY2026-P12");
    expect(request?.get("count")).toBe("true");
    expect(await within(grid).findByText("9,764.38")).toBeTruthy();
    // SCREENS_B §4.1: Lines reads current schedule lines, so it creates no run and has no run stamp.
    expect(posted).toHaveLength(0);
    expect(screen.queryByTestId("SF-04-run-stamp")).toBeNull();
  });

  it("anomaly counts absent without flags", async () => {
    const { flagRequests } = serve({
      periods: calendar(AVM_US, 2026, 2026, 1),
      run: reportRun(),
      rows: US_ROWS,
      flags: [],
    });
    renderApp(`/schedules?${US_CONTEXT}&run=${RUN_ID}`, {
      me: MARCUS,
      screenRoutes: SCREEN_ROUTES,
    });

    const row = await screen.findByTestId("SF-04-row-sf-ord-10001");
    expect(row.textContent).toContain("9,764.38");
    await waitFor(() => {
      expect(flagRequests.length).toBeGreaterThan(0);
    });
    const request = flagRequests[0]?.searchParams;
    expect(request?.getAll("source")).toEqual(["ANOMALY"]);
    expect(request?.getAll("status")).toEqual(["OPEN", "IN_PROGRESS"]);
    expect(request?.get("entity")).toBe("AVM-US");
    expect(request?.get("period")).toBe("FY2026-P09");
    const grid = screen.getByTestId("SF-04-grid-waterfall");
    expect(within(grid).getByRole("columnheader", { name: /^Flags/ })).toBeTruthy();
    // Without ANOMALY exception items no flag count renders (the §8.4 flag block arrives with AIX).
    expect(grid.textContent).not.toMatch(/\bflags?\b/);
    expect(within(grid).queryByText(/anomaly flag/)).toBeNull();
  });

  // SCREENS §0.6 SCR-PERM-02 (a) (rev 1.30; item W-12, slice c): the periods and the anomaly flags
  // are those of the context entity, so `config.read` and `contract.read` are asked for it. A reader
  // of AVM-JP alone who opens a stored run of AVM-US asks for neither of AVM-US.
  it("the periods and the anomaly flags of an entity are read with the permission for that entity", async () => {
    const run = () => ({
      periods: calendar(AVM_US, 2026, 2026, 1),
      run: reportRun(),
      rows: US_ROWS,
      flags: [],
    });
    const periodRequests: URL[] = [];
    const watchStructure = () =>
      server.use(
        http.get(apiUrl("/api/v1/entities"), () =>
          HttpResponse.json({
            items: [AVM_US, AVM_JP].map((entity) => ({ ...entity, is_active: true, books: [] })),
            next_cursor: null,
          }),
        ),
        http.get(apiUrl("/api/v1/periods"), ({ request }) => {
          periodRequests.push(new URL(request.url));
          return HttpResponse.json({ items: calendar(AVM_US, 2026, 2026, 1), next_cursor: null });
        }),
      );
    const member = (entityId: string) =>
      signedInMe({
        permissions: MARCUS.permissions,
        permission_scopes: {
          "contract.read": [entityId],
          "config.read": [entityId],
          "report.run": "*",
          "report.export": "*",
        },
      });

    const hers = serve(run());
    watchStructure();
    const first = renderApp(`/schedules?${US_CONTEXT}&run=${RUN_ID}`, {
      me: member(AVM_US.id),
      screenRoutes: SCREEN_ROUTES,
    });
    await screen.findByTestId("SF-04-row-sf-ord-10001");
    await waitFor(() => {
      expect(hers.flagRequests.length).toBeGreaterThan(0);
      expect(periodRequests.length).toBeGreaterThan(0);
    });
    expect(hers.flagRequests[0]?.searchParams.get("entity")).toBe("AVM-US");
    await waitFor(() => expect(first.queryClient.isFetching()).toBe(0));
    cleanup();

    const others = serve(run());
    periodRequests.length = 0;
    watchStructure();
    const second = renderApp(`/schedules?${US_CONTEXT}&run=${RUN_ID}`, {
      me: member(AVM_JP.id),
      screenRoutes: SCREEN_ROUTES,
    });
    await screen.findByTestId("SF-04-row-sf-ord-10001");
    await waitFor(() => expect(second.queryClient.isFetching()).toBe(0));
    expect(others.flagRequests).toEqual([]);
    expect(periodRequests).toEqual([]);
  });

  it("anomaly counts per contract", async () => {
    serve({
      periods: calendar(AVM_US, 2026, 2026, 1),
      run: reportRun(),
      rows: US_ROWS,
      flags: [
        {
          id: "3e2d1c0b-9a8f-4e7d-8c6b-5a4f3e2d1c0b",
          source: "ANOMALY",
          status: "OPEN",
          contract_external_id: "SF-ORD-10001",
        },
      ],
    });
    renderApp(`/schedules?${US_CONTEXT}&run=${RUN_ID}`, {
      me: MARCUS,
      screenRoutes: SCREEN_ROUTES,
    });

    const row = await screen.findByTestId("SF-04-row-sf-ord-10001");
    expect(await within(row).findByText("Warning, 1 anomaly flag")).toBeTruthy();
    expect(row.textContent).toContain("1 flag");
  });

  it("as locked keeps run report and rerun", async () => {
    // The lock of the API's table (`src/test/as-locked.json`): AVM-US, ASC 606, August 2026.
    const lockId = AS_LOCKED.lock.id;
    const lock = {
      id: lockId,
      created_at: "2026-09-03T09:14:00Z",
      created_by: null,
      kind: "LOCK",
      ledger_head_chain_seq: 1388,
      snapshot_manifest_sha256: null,
    };
    const periods = calendar(AVM_US, 2026, 2026, 1).map((item) =>
      item.period.period_key === "FY2026-P08"
        ? ({
            ...item,
            state: "closed",
            is_first_open: false,
            // A closed period's two locks are one record: the lock whose datasets stand is its own.
            current_lock: lock,
            dataset_lock: lock,
          } as unknown as Period)
        : item,
    );
    const { posted } = serve({
      periods,
      run: reportRun({ period_lock_id: lockId }),
      rows: US_ROWS,
    });
    const { router } = renderApp("/schedules?entity=AVM-US&period=FY2026-P08&book=ASC606", {
      me: MARCUS,
      screenRoutes: SCREEN_ROUTES,
    });

    // RV-04: the closed context period sets `snapshot` and the waterfall run reads that lock.
    await waitFor(() => {
      expect(new URLSearchParams(router.state.location.search).get("snapshot")).toBe(lockId);
    });
    // Rev 1.98: the run is the lock's own entity, book and period and nothing else — not the fiscal
    // year, the as-of date and the screen's three choices, each of which the API refuses by name.
    await waitFor(() => {
      expect(posted[0]?.parameters).toEqual({
        period_lock_id: lockId,
        entity_codes: ["AVM-US"],
        book: "ASC606",
        from_period_key: "FY2026-P08",
        to_period_key: "FY2026-P08",
      });
    });
    // D-88 L7-3-Q-2: with `snapshot` "Run report" and "Rerun from the same source" stay, because a
    // report run and a rerun read the lock source (not SCR-ST-10 commands). The bar's fields are
    // shown and unavailable: a lock's figures take no parameter.
    expect(await screen.findByRole("button", { name: "Run report" })).toBeTruthy();
    expect(
      within(screen.getByTestId("SF-04-filter-bar"))
        .getByRole("combobox", { name: /^Rows/ })
        .getAttribute("aria-disabled"),
    ).toBe("true");
    fireEvent.click(await screen.findByRole("button", { name: "Run details" }));
    const drawer = await screen.findByTestId("SF-04-drawer-run-details");
    expect(
      await within(drawer).findByRole("button", { name: "Rerun from the same source" }),
    ).toBeTruthy();
  });
});

// L9-PLT-Q-6 (D-90e (i); SCREENS_B rev 1.6 RV-01; PR-8.2): the refusal of the run this view tried to create
// is not shown for a stored run opened afterwards by `run=` in the same mounted view, and returns with its
// parameter set without a second creation.
describe("SF-04 creation problem bound to its parameter set", () => {
  const REFUSED_TITLE = "The report parameters were refused.";
  const REFUSED_MESSAGE = "AVM-US keeps no ASC606 book before FY2026-P01.";

  it("A to B to A: a stored run shows no refusal of A, which returns with A", async () => {
    serve({ periods: calendar(AVM_US, 2026, 2026, 1), run: reportRun(), rows: US_ROWS });
    let posts = 0;
    server.use(
      http.post(apiUrl("/api/v1/report-runs"), () => {
        posts += 1;
        return problemResponse("validation-failed", 422, REFUSED_TITLE, {
          errors: [{ field: null, rule_id: "T-RPT-02", message: REFUSED_MESSAGE }],
        });
      }),
    );
    const { router } = renderApp(`/schedules?${US_CONTEXT}`, {
      me: MARCUS,
      screenRoutes: SCREEN_ROUTES,
    });

    expect(await screen.findByText(REFUSED_TITLE)).toBeTruthy();
    expect(screen.getByText(REFUSED_MESSAGE)).toBeTruthy();
    expect(posts).toBe(1);

    await router.navigate(`/schedules?${US_CONTEXT}&run=${RUN_ID}`);
    expect(await screen.findByTestId("SF-04-row-sf-ord-10001")).toBeTruthy();
    expect(screen.queryByText(REFUSED_TITLE)).toBeNull();
    expect(screen.queryByText(REFUSED_MESSAGE)).toBeNull();
    expect(posts).toBe(1);

    await router.navigate(`/schedules?${US_CONTEXT}`);
    expect(await screen.findByText(REFUSED_TITLE)).toBeTruthy();
    expect(posts).toBe(1);
  });

  // REPORT-RERUN-AFTER-REFUSAL-1 (SCREENS_B rev 1.92 RV-01): "Run report" asks. Pressed on the parameter
  // set of a refused creation it sends that creation again; before, nothing was sent.
  it("Run report on a refused parameter set asks the creation again", async () => {
    serve({ periods: calendar(AVM_US, 2026, 2026, 1), run: reportRun(), rows: US_ROWS });
    const posted: Record<string, unknown>[] = [];
    server.use(
      http.post(apiUrl("/api/v1/report-runs"), async ({ request }) => {
        posted.push((await request.json()) as Record<string, unknown>);
        if (posted.length === 1) {
          return problemResponse("validation-failed", 422, REFUSED_TITLE, {
            errors: [{ field: null, rule_id: "T-RPT-02", message: REFUSED_MESSAGE }],
          });
        }
        return HttpResponse.json(
          { id: JOB_ID, kind: "REPORT_RUN", state: "QUEUED" },
          {
            status: 202,
            headers: { Location: `/api/v1/jobs/${JOB_ID}`, "X-Erev-Report-Run-Id": RUN_ID },
          },
        );
      }),
    );
    const { router } = renderApp(`/schedules?${US_CONTEXT}`, {
      me: MARCUS,
      screenRoutes: SCREEN_ROUTES,
    });
    expect(await screen.findByText(REFUSED_MESSAGE)).toBeTruthy();
    expect(posted).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Run report" }));
    expect(await screen.findByTestId("SF-04-row-sf-ord-10001")).toBeTruthy();
    expect(posted).toHaveLength(2);
    expect(posted[1]).toEqual(posted[0]);
    expect(new URLSearchParams(router.state.location.search).get("run")).toBe(RUN_ID);
    expect(screen.queryByText(REFUSED_TITLE)).toBeNull();
    expect(screen.queryByText(REFUSED_MESSAGE)).toBeNull();
  });

  // PRD ERR-97 (04 T-RPT-01 rule 6; item RPT-PERIOD-KEY-CALENDARS-1). The screen reads the address
  // alone: without an entity it asks the waterfall for every entity in scope, and without their
  // calendar it names no period — the default range, each entity's own fiscal year. Where the
  // entities keep different calendars the API refuses that run; the sentence stands in the banner,
  // its member being the pill's and no toolbar field.
  it("opened without an entity: the refusal of two calendars stands in the banner", async () => {
    const sentence =
      "The entities of this run keep different fiscal calendars, so a period key can name different " +
      "months for them. Run the report for entities of one calendar.";
    serve({ periods: [], run: reportRun(), rows: US_ROWS });
    const posted: Record<string, unknown>[] = [];
    server.use(
      http.post(apiUrl("/api/v1/report-runs"), async ({ request }) => {
        posted.push((await request.json()) as Record<string, unknown>);
        return problemResponse("validation-failed", 422, "Check the highlighted fields", {
          detail: sentence,
          errors: [
            {
              field: "parameters.entity_codes",
              sheet: null,
              row: null,
              rule_id: "CALENDARS_DIFFER",
              message: sentence,
            },
          ],
        });
      }),
    );
    renderApp("/schedules", { me: MARCUS, screenRoutes: SCREEN_ROUTES });

    expect(await screen.findByText(sentence)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Check the highlighted fields" })).toBeTruthy();
    expect(posted).toHaveLength(1);
    // No entity and no period key: only what the toolbar holds.
    expect(posted[0]?.parameters).toEqual({
      row_dimension: "CONTRACT",
      granularity: "MONTH",
      measure: "TOTAL",
    });
  });
});

// RV-14 rev 1.7 (D-90e (i) L9-PLT-Q-5; D-91 SF-04 addition; PR-8.1): SF-04's failed-run banner carries the
// SCR-ST-12 "Reference <job id prefix>" line — the run's own job (API-S-ReportRun `job_id`) for a stored run,
// and for the run this view created.
describe("SF-04 failed run names its job", () => {
  const JOB_B = "b0b0b0b0-1111-4222-8333-444455556666";
  const FAILED_TITLE = "The waterfall run failed.";

  function failedRun(jobId: string | null): ReportRun {
    return reportRun({
      status: "FAILED",
      as_of: null,
      row_count: 0,
      tie_out_results: [],
      control_totals: null,
      output: null,
      job_id: jobId,
      problem: {
        type: "internal-error",
        title: FAILED_TITLE,
        status: 500,
        instance: `/api/v1/report-runs/${RUN_ID}`,
        errors: [],
      },
    });
  }

  it("the run this view created names the 202 job", async () => {
    const { posted } = serve({
      periods: calendar(AVM_US, 2026, 2026, 1),
      run: failedRun(JOB_ID),
      rows: [],
    });
    renderApp(`/schedules?${US_CONTEXT}`, { me: MARCUS, screenRoutes: SCREEN_ROUTES });
    expect(await screen.findByText(FAILED_TITLE)).toBeTruthy();
    expect(screen.getByText(`Reference ${JOB_ID.slice(0, 8)}.`)).toBeTruthy();
    expect(posted).toHaveLength(1);
  });

  it("a stored failed run rendered from run= names its own job", async () => {
    const { posted } = serve({
      periods: calendar(AVM_US, 2026, 2026, 1),
      run: failedRun(JOB_B),
      rows: [],
    });
    renderApp(`/schedules?${US_CONTEXT}&run=${RUN_ID}`, {
      me: MARCUS,
      screenRoutes: SCREEN_ROUTES,
    });
    expect(await screen.findByText(FAILED_TITLE)).toBeTruthy();
    expect(screen.getByText(`Reference ${JOB_B.slice(0, 8)}.`)).toBeTruthy();
    expect(screen.queryByText(`Reference ${JOB_ID.slice(0, 8)}.`)).toBeNull();
    expect(posted).toHaveLength(0);
  });
});
