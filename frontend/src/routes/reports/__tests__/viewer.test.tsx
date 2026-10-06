// @vitest-environment jsdom
// SF-08 report catalogue and SF-08:report viewer (BUILD_SPEC RPS-6; SCREENS_B §5.1, §5.2, §0.5 RV-02,
// RV-04, RV-05, RV-06, RV-13; D-87 L6-3-Q-20, L6-3-Q-26): the run stamp and its volatile fields, the As
// locked default and banner, the export formats, the tie-out strip, an empty run, the currency view field
// error, the `rpo` bands and sections, and the catalogue groups. API answers are contract fakes of 04
// API-R-41 (V-C).
import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../../app/router";
import type {
  ReportDefinition,
  ReportRow,
  ReportRun,
  ReportRunColumn,
  TieOutResult,
} from "../../../lib/api/queries/reports";
import type { Period } from "../../../lib/api/queries/tenant";
import { installMemoryStorage, renderApp, signedInMe } from "../../../test/app";
import { AS_LOCKED, asLockedRefusal } from "../../../test/as-locked";
import { installGridViewport } from "../../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";

installMswServer();
installMemoryStorage();
installGridViewport();
// The view reads the definition, the calendar and the run before its rows render.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
});

const MARCUS = signedInMe({
  permissions: ["contract.read", "config.read", "report.run", "report.export"],
});

const RUN_ID = "5b0c7a1e-3d2f-4e6a-9b8c-7d6e5f4a3b2c";
const SECOND_RUN_ID = "5b0c7a1e-3d2f-4e6a-9b8c-7d6e5f4a3b2d";
const JOB_ID = "8e7d6c5b-4a3f-4e2d-9c1b-0a9f8e7d6c5b";
const LOCK_ID = "8b10c4d2-6e1f-4a3b-9c8d-7e6f5a4baa42";
const SHA = "5c1e7a90f3b2d4c6e8a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c004b2";
const AVM_US = {
  id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000001",
  code: "AVM-US",
  name: "Avenmoor US Inc.",
};
const CONTEXT = "entity=AVM-US&period=FY2026-P09&book=ASC606";
// PRD ERR-97, word for word.
const CALENDARS_DIFFER =
  "The entities of this run keep different fiscal calendars, so a period key can name different " +
  "months for them. Run the report for entities of one calendar.";

/** 04 T-RPT-01 rule 6: what `POST /report-runs` and its rerun answer for two calendars. */
function calendarsRefusal() {
  return problemResponse("validation-failed", 422, "Check the highlighted fields", {
    detail: CALENDARS_DIFFER,
    errors: [
      {
        field: "parameters.entity_codes",
        sheet: null,
        row: null,
        rule_id: "CALENDARS_DIFFER",
        message: CALENDARS_DIFFER,
      },
    ],
  });
}

function money(amount: string, currency = "USD") {
  return { amount, currency };
}

function schema(keys: Readonly<Record<string, Readonly<Record<string, unknown>>>>) {
  return { type: "object", additionalProperties: false, properties: keys };
}

const WATERFALL: ReportDefinition = {
  code: "revenue_waterfall",
  version: 1,
  name: "Revenue waterfall",
  kind: "STANDARD",
  description: "Recognized, scheduled and awaiting-trigger revenue by period over a range.",
  parameters_schema: schema({
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
  }),
  output_formats: ["XLSX", "CSV", "JSON"],
  tie_outs: ["TO_WATERFALL_EQ_JE_REVENUE"],
  ipe_logic: null,
};

const RPO: ReportDefinition = {
  code: "rpo",
  version: 1,
  name: "Remaining performance obligations",
  kind: "DISCLOSURE",
  description: "RPO by contract and expected timing of recognition (ASC 606-10-50-13).",
  parameters_schema: schema({
    entity_codes: { type: "array" },
    book: { type: "string", enum: ["ASC606", "IFRS15", "LEGACY"] },
    period_key: { type: "string" },
    period_lock_id: { type: "string", format: "uuid" },
    time_bands: { type: "array", items: { type: "integer" } },
    row_dimension: {
      type: "string",
      enum: ["CONTRACT", "ENTITY", "PRODUCT_FAMILY", "CUSTOMER_SEGMENT"],
    },
    currency_view: { type: "string", enum: ["transaction", "functional", "reporting"] },
    known_at: { type: "string", format: "date-time" },
  }),
  output_formats: ["XLSX", "CSV", "PDF", "JSON"],
  tie_outs: ["TO_RPO_ROLLFORWARD_EQ_RPO"],
  ipe_logic: null,
};

const LEGACY_HISTORY: ReportDefinition = {
  code: "legacy_contract_history_export",
  version: 1,
  name: "Legacy contract history export",
  kind: "LEGACY_EXPORT",
  description: "The contract history under the legacy column names, in legacy order.",
  parameters_schema: schema({
    entity_codes: { type: "array" },
    book: { type: "string", enum: ["ASC606"] },
    from_date: { type: "string", format: "date" },
    to_date: { type: "string", format: "date" },
    contract_external_id: { type: "string" },
  }),
  output_formats: ["XLSX", "CSV", "JSON"],
  tie_outs: [],
  ipe_logic: null,
};

function period(
  key: string,
  name: string,
  start: string,
  end: string,
  state: string,
  lock: Period["current_lock"] = null,
): Period {
  return {
    id: `1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e${key.slice(-2)}`,
    entity: AVM_US,
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
    current_lock: lock,
    // API-S-Period `dataset_lock`: the lock whose datasets stand — a closed period's own lock.
    dataset_lock: lock,
    blockers: {},
  } as unknown as Period;
}

const PERIODS: readonly Period[] = [
  period("FY2026-P08", "Aug 2026", "2026-08-01", "2026-08-31", "closed", {
    id: LOCK_ID,
    created_at: "2026-09-03T09:14:00Z",
    created_by: { id: null, kind: "SYSTEM", display_name: "System" },
    kind: "LOCK",
    ledger_head_chain_seq: 1388,
    snapshot_manifest_sha256: null,
  }),
  period("FY2026-P09", "Sep 2026", "2026-09-01", "2026-09-30", "open"),
];

function reportRun(overrides: Partial<ReportRun> = {}): ReportRun {
  return {
    id: RUN_ID,
    report_run_no: "RPT-000412",
    report: { code: "revenue_waterfall", version: 1, name: "Revenue waterfall" },
    status: "SUCCEEDED",
    parameters: {
      entity_codes: ["AVM-US"],
      book: "ASC606",
      from_period_key: "FY2026-P09",
      to_period_key: "FY2026-P09",
      as_of: "2026-09-30",
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
    tie_out_results: [
      {
        code: "TO_WATERFALL_EQ_JE_REVENUE",
        result: "PASS",
        expected: [money("9764.38")],
        actual: [money("9764.38")],
        difference: [money("0.00")],
      },
    ],
    ledger_heads: {},
    output: {
      file_id: "6a5b4c3d-2e1f-4a0b-9c8d-7e6f5a4b3c2d",
      format: "JSON",
      sha256: SHA,
      href: `/api/v1/report-runs/${RUN_ID}/output`,
      manifest_href: null,
    },
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

/** A stored run serialises its rows with sorted keys (L7-3-Q-6), as the fakes do. */
function stored(row: Readonly<Record<string, unknown>>): ReportRow {
  return Object.fromEntries(
    Object.entries(row).sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0)),
  ) as ReportRow;
}

const WATERFALL_ROWS: readonly ReportRow[] = [
  stored({
    row_key: "contract:SF-ORD-10001",
    contract_external_id: "SF-ORD-10001",
    customer_name: "Marrowby Health",
    entity_code: "AVM-US",
    "period:FY2026-P08": money("9764.38"),
    "period:FY2026-P09": money("9764.38"),
    awaiting_trigger: money("0.00"),
    total: money("19528.76"),
  }),
  stored({
    row_key: "TOTAL:USD",
    contract_external_id: null,
    customer_name: null,
    entity_code: null,
    "period:FY2026-P08": money("9764.38"),
    "period:FY2026-P09": money("9764.38"),
    awaiting_trigger: money("0.00"),
    total: money("19528.76"),
  }),
];

interface Served {
  readonly posted: Record<string, unknown>[];
}

function serve(
  definition: ReportDefinition,
  runs: Readonly<Record<string, ReportRun>>,
  rows: readonly ReportRow[],
  created: readonly string[] = [RUN_ID],
  columns: readonly ReportRunColumn[] = [],
): Served {
  const posted: Record<string, unknown>[] = [];
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
        ],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/jobs"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/periods"), () =>
      HttpResponse.json({ items: PERIODS, next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/report-definitions/:code"), () => HttpResponse.json(definition)),
    http.get(apiUrl("/api/v1/report-runs/:runId"), ({ params }) => {
      const found = runs[String(params.runId)];
      return found === undefined
        ? problemResponse("not-found", 404, "Report run not found")
        : HttpResponse.json(found);
    }),
    http.get(apiUrl("/api/v1/report-runs/:runId/data"), () =>
      HttpResponse.json({ items: rows, next_cursor: null, columns }),
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
      const id = created[Math.min(posted.length - 1, created.length - 1)] ?? RUN_ID;
      return HttpResponse.json(
        { id: JOB_ID, kind: "REPORT_RUN", state: "QUEUED" },
        {
          status: 202,
          headers: { Location: `/api/v1/jobs/${JOB_ID}`, "X-Erev-Report-Run-Id": id },
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
  );
  return { posted };
}

describe("SF-08:report viewer", () => {
  it("run stamp", async () => {
    serve(WATERFALL, { [RUN_ID]: reportRun() }, WATERFALL_ROWS);
    renderApp(`/reports/revenue_waterfall?${CONTEXT}&run=${RUN_ID}`, {
      me: MARCUS,
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Revenue waterfall" }),
    ).toBeTruthy();
    const stamp = await screen.findByTestId("SF-08-run-stamp");
    const terms = [...stamp.querySelectorAll("dt")].map((term) => term.textContent);
    expect(terms).toEqual([
      "Report",
      "Run",
      "Entity",
      "Book",
      "As of",
      "Source",
      "Engine",
      "Run by",
      "Run at",
      "Rows",
      "Output SHA-256",
    ]);
    const volatile = [...stamp.querySelectorAll("dd[data-volatile]")].map(
      (value) => value.previousElementSibling?.textContent,
    );
    expect(volatile).toEqual(["Run", "Run at", "Output SHA-256"]);
    expect(stamp.textContent).toContain("Revenue waterfall v1");
    expect(stamp.textContent).toContain("RPT-000412");
    expect(stamp.textContent).toContain("30 Sep 2026");
    expect(stamp.textContent).toContain("Current, known at 12 Sep 2026 16:02 UTC");
    expect(stamp.textContent).toContain("5c1e7a90…04b2");
    // A stored run renders and creates none (RV-01; SCR-URL-16).
    const row = await screen.findByTestId("SF-08-row-sf-ord-10001");
    expect(row.textContent).toContain("9,764.38");
    // RPT-01 column order from row keys stored in sorted order; the totals row is a totals row.
    const grid = screen.getByTestId("SF-08-grid-revenue-waterfall");
    const headers = within(grid)
      .getAllByRole("columnheader")
      .map((header) => header.textContent ?? "");
    const at = (text: string) => headers.findIndex((header) => header.startsWith(text));
    expect(at("Contract")).toBe(0);
    expect(at("Customer")).toBeLessThan(at("Entity"));
    expect(at("Entity")).toBeLessThan(at("Aug 2026 (USD)"));
    expect(at("Aug 2026 (USD)")).toBeLessThan(at("Sep 2026 (USD)"));
    expect(at("Sep 2026 (USD)")).toBeLessThan(at("Awaiting trigger (USD)"));
    expect(at("Awaiting trigger (USD)")).toBeLessThan(at("Total (USD)"));
    expect(screen.queryByTestId("SF-08-row-usd")).toBeNull();
    expect(
      within(grid)
        .getAllByRole("rowheader")
        .map((cell) => cell.textContent),
    ).toContain("Total");
    // DS-CH-01 from the totals row (RV-10).
    expect(
      screen.getByTestId("SF-08-chart-revenue-waterfall").querySelector("figure"),
    ).not.toBeNull();
  });

  // SCREENS §0.6 SCR-PERM-02 (a) (rev 1.30; item W-12, slice c): the periods the view reads are those
  // of the context entity, so `config.read` is asked for it.
  it("the periods of the context entity are read with config.read for that entity", async () => {
    const other = "0a1b2c3d-4e5f-4a6b-8c7d-000000000004";
    const periodRequests: string[] = [];
    const arrange = () => {
      serve(WATERFALL, { [RUN_ID]: reportRun() }, WATERFALL_ROWS);
      periodRequests.length = 0;
      server.use(
        http.get(apiUrl("/api/v1/entities"), () =>
          HttpResponse.json({
            items: [
              { ...AVM_US, is_active: true, books: [] },
              { id: other, code: "AVM-JP", name: "Avenmoor Japan KK", is_active: true, books: [] },
            ],
            next_cursor: null,
          }),
        ),
        http.get(apiUrl("/api/v1/periods"), ({ request }) => {
          periodRequests.push(new URL(request.url).search);
          return HttpResponse.json({ items: PERIODS, next_cursor: null });
        }),
      );
    };
    const member = (entityId: string) =>
      signedInMe({
        permissions: MARCUS.permissions,
        permission_scopes: {
          "contract.read": "*",
          "config.read": [entityId],
          "report.run": "*",
          "report.export": "*",
        },
      });

    arrange();
    const first = renderApp(`/reports/revenue_waterfall?${CONTEXT}&run=${RUN_ID}`, {
      me: member(AVM_US.id),
      screenRoutes: SCREEN_ROUTES,
    });
    await screen.findByTestId("SF-08-run-stamp");
    await waitFor(() => expect(periodRequests.length).toBeGreaterThan(0));
    await waitFor(() => expect(first.queryClient.isFetching()).toBe(0));
    cleanup();

    arrange();
    const second = renderApp(`/reports/revenue_waterfall?${CONTEXT}&run=${RUN_ID}`, {
      me: member(other),
      screenRoutes: SCREEN_ROUTES,
    });
    await screen.findByTestId("SF-08-run-stamp");
    await waitFor(() => expect(second.queryClient.isFetching()).toBe(0));
    expect(periodRequests).toEqual([]);
  });

  it("as locked banner", async () => {
    const lockedRun = reportRun({
      report: { code: "rpo", version: 1, name: "Remaining performance obligations" },
      parameters: { entity_codes: ["AVM-US"], book: "ASC606", period_key: "FY2026-P08" },
      period_lock_id: LOCK_ID,
      as_of: "2026-08-31",
      row_count: 0,
      tie_out_results: [],
      control_totals: { as_of: "2026-08-31", bands: [], total: {}, notes: [] },
    });
    const { posted } = serve(
      RPO,
      {
        [RUN_ID]: lockedRun,
        [SECOND_RUN_ID]: reportRun({ ...lockedRun, id: SECOND_RUN_ID, period_lock_id: null }),
      },
      [],
      [RUN_ID, SECOND_RUN_ID],
    );
    const { router } = renderApp(`/reports/rpo?entity=AVM-US&period=FY2026-P08&book=ASC606`, {
      me: MARCUS,
      screenRoutes: SCREEN_ROUTES,
    });

    // RV-04: the closed context period sets `snapshot` to its lock and the run reads that lock.
    await waitFor(() => {
      expect(new URLSearchParams(router.state.location.search).get("snapshot")).toBe(LOCK_ID);
    });
    await waitFor(() => {
      expect(posted[0]).toEqual({
        report_code: "rpo",
        output_format: "JSON",
        parameters: {
          entity_codes: ["AVM-US"],
          book: "ASC606",
          period_key: "FY2026-P08",
          period_lock_id: LOCK_ID,
        },
      });
    });
    expect(
      await screen.findByText("Showing Aug 2026 as locked on 03 Sep 2026 09:14 UTC."),
    ).toBeTruthy();
    const showCurrent = screen.getByRole("button", { name: "Show current figures" });
    // D-88 L7-3-Q-2: a report run, an export and a rerun read the lock source, so they are not SCR-ST-10
    // commands: "Run report" and "Rerun from the same source" stay with `snapshot`. Rev 1.98: the
    // parameter fields are shown and unavailable — a lock's figures take no parameter — and the
    // toolbar says so.
    expect(screen.getByRole("button", { name: "Run report" })).toBeTruthy();
    const bar = screen.getByTestId("SF-08-filter-bar");
    expect(within(bar).getByRole("combobox", { name: /^Rows/ }).getAttribute("aria-disabled")).toBe(
      "true",
    );
    expect(document.getElementById(bar.getAttribute("aria-describedby") ?? "")?.textContent).toBe(
      "Figures as locked take no parameters. Show current figures to change them.",
    );
    fireEvent.click(await screen.findByRole("button", { name: "Run details" }));
    const drawer = await screen.findByTestId("SF-08-drawer-run-details");
    expect(
      await within(drawer).findByRole("button", { name: "Rerun from the same source" }),
    ).toBeTruthy();
    fireEvent.click(within(drawer).getByRole("button", { name: "Close" }));
    await waitFor(() => {
      expect(screen.queryByTestId("SF-08-drawer-run-details")).toBeNull();
    });

    fireEvent.click(showCurrent);
    expect(
      await screen.findByText(
        "Showing current figures. Aug 2026 was locked on 03 Sep 2026 09:14 UTC.",
      ),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Show as locked" })).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Run report" })).toBeTruthy();
    expect(new URLSearchParams(router.state.location.search).get("snapshot")).toBeNull();
    await waitFor(() => {
      expect(posted[1]?.parameters).not.toHaveProperty("period_lock_id");
    });
  });

  it("export menu formats", async () => {
    const { posted } = serve(WATERFALL, { [RUN_ID]: reportRun() }, WATERFALL_ROWS, [SECOND_RUN_ID]);
    renderApp(`/reports/revenue_waterfall?${CONTEXT}&run=${RUN_ID}`, {
      me: MARCUS,
      screenRoutes: SCREEN_ROUTES,
    });

    await screen.findByTestId("SF-08-run-stamp");
    fireEvent.click(screen.getByRole("button", { name: "Export" }));
    const items = screen.getAllByRole("menuitem").map((item) => item.textContent);
    // RV-06: only the definition's output formats.
    expect(items).toEqual(["Excel workbook (XLSX)", "CSV with manifest", "JSON"]);

    fireEvent.click(screen.getByRole("menuitem", { name: "Excel workbook (XLSX)" }));
    await waitFor(() => {
      expect(posted).toHaveLength(1);
    });
    expect(posted[0]).toEqual({
      report_code: "revenue_waterfall",
      parameters: reportRun().parameters,
      output_format: "XLSX",
    });
  });

  it("tie-out strip", async () => {
    const results: TieOutResult[] = [
      {
        code: "TO_WATERFALL_EQ_JE_REVENUE",
        result: "PASS",
        expected: [money("9764.38")],
        actual: [money("9764.38")],
        difference: [money("0.00")],
      },
      {
        code: "TO_RPO_ROLLFORWARD_EQ_RPO",
        result: "FAIL",
        expected: [money("105043.80")],
        actual: [money("104043.80")],
        // D-88 L7-3-Q-3: the API figure, actual − expected, computed when the run is serialised.
        difference: [money("-1000.00")],
      },
    ];
    serve(WATERFALL, { [RUN_ID]: reportRun({ tie_out_results: results }) }, WATERFALL_ROWS);
    renderApp(`/reports/revenue_waterfall?${CONTEXT}&run=${RUN_ID}`, {
      me: MARCUS,
      screenRoutes: SCREEN_ROUTES,
    });

    const strip = await screen.findByRole("region", { name: "Tie-outs (1 pass, 1 fail)" });
    expect(strip.getAttribute("data-testid")).toBe("SF-08-banner-tie-outs");
    const rows = within(strip).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    const [passing, failing] = rows;
    expect(passing?.textContent).toContain("Pass");
    expect(passing?.textContent).toContain("Waterfall revenue equals revenue journal total");
    expect(passing?.textContent).not.toContain("Difference");
    expect(failing?.textContent).toContain("Difference");
    expect(failing?.textContent).toContain("RPO rollforward closing equals RPO report total");
    expect(within(failing as HTMLElement).getByText(/^Expected USD\s105,043\.80$/)).toBeTruthy();
    expect(within(failing as HTMLElement).getByText(/^Actual USD\s104,043\.80$/)).toBeTruthy();
    expect(
      within(failing as HTMLElement).getByText(/^Difference USD\s(\(1,000\.00\)|−1,000\.00)$/),
    ).toBeTruthy();
  });

  it("tie-out difference is the API figure", async () => {
    // D-88 L7-3-Q-3: the strip renders `difference` as the API serialised it and derives nothing from
    // expected and actual (DG-FE-08); a failing result without a difference for a currency shows none.
    const results: TieOutResult[] = [
      {
        code: "TO_RPO_ROLLFORWARD_EQ_RPO",
        result: "FAIL",
        expected: [money("105043.80"), money("10.00", "JPY")],
        actual: [money("104043.80"), money("12.00", "JPY")],
        difference: [money("-7.25")],
      },
    ];
    serve(WATERFALL, { [RUN_ID]: reportRun({ tie_out_results: results }) }, WATERFALL_ROWS);
    renderApp(`/reports/revenue_waterfall?${CONTEXT}&run=${RUN_ID}`, {
      me: MARCUS,
      screenRoutes: SCREEN_ROUTES,
    });

    const strip = await screen.findByRole("region", { name: "Tie-outs (0 pass, 1 fail)" });
    const [failing] = within(strip).getAllByRole("listitem");
    expect(
      within(failing as HTMLElement).getByText(/^Difference USD\s(\(7\.25\)|−7\.25)$/),
    ).toBeTruthy();
    expect(within(failing as HTMLElement).getAllByText(/^Difference /)).toHaveLength(1);
  });

  it("empty run keeps stamp", async () => {
    const empty = reportRun({
      report: { code: "rpo", version: 1, name: "Remaining performance obligations" },
      parameters: { entity_codes: ["AVM-US"], book: "ASC606", period_key: "FY2026-P09" },
      // `rpo` resolves its as-of date from `period_key` into the control totals (L6-3-Q-26).
      as_of: null,
      row_count: 0,
      tie_out_results: [],
      control_totals: { as_of: "2026-09-30", bands: [], total: {}, notes: [] },
    });
    serve(RPO, { [RUN_ID]: empty }, []);
    renderApp(`/reports/rpo?${CONTEXT}&run=${RUN_ID}`, { me: MARCUS, screenRoutes: SCREEN_ROUTES });

    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: "No remaining performance obligations at 30 Sep 2026",
      }),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Unsatisfied and partially satisfied obligations appear here with their expected timing.",
      ),
    ).toBeTruthy();
    const stamp = screen.getByTestId("SF-08-run-stamp");
    expect(stamp.textContent).toContain("RPT-000412");
    expect(stamp.textContent).toContain("30 Sep 2026");
  });

  it("empty register run states its SCREENS_B copy", async () => {
    // SCREENS_B RPT-28 "Empty copy"; the range is the one the builder resolved into the control totals.
    const register: ReportDefinition = {
      code: "judgement_register",
      version: 1,
      name: "Judgement register",
      kind: "REGISTER",
      description: "Documented judgements with preparer and reviewer.",
      parameters_schema: schema({
        entity_codes: { type: "array" },
        book: { type: "string", enum: ["ASC606", "IFRS15", "LEGACY"] },
        from_date: { type: "string", format: "date" },
        to_date: { type: "string", format: "date" },
        known_at: { type: "string", format: "date-time" },
      }),
      output_formats: ["XLSX", "CSV", "PDF", "JSON"],
      tie_outs: [],
      ipe_logic: null,
    };
    const empty = reportRun({
      report: { code: "judgement_register", version: 1, name: "Judgement register" },
      parameters: { entity_codes: ["AVM-US"], book: "ASC606" },
      as_of: null,
      row_count: 0,
      tie_out_results: [],
      control_totals: { row_count: 0, from_date: "2026-01-01", to_date: "2026-09-12" },
    });
    serve(register, { [RUN_ID]: empty }, []);
    renderApp(`/reports/judgement_register?${CONTEXT}&run=${RUN_ID}`, {
      me: MARCUS,
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: "No judgement records from 01 Jan 2026 to 12 Sep 2026",
      }),
    ).toBeTruthy();
    expect(
      screen.getByText("Documented accounting judgements with preparer and reviewer appear here."),
    ).toBeTruthy();
    expect(screen.queryByText("No rows in this run")).toBeNull();
  });

  it("currency view refusal is a parameter field error", async () => {
    const message = "Functional and reporting views serve contracts in the functional currency.";
    serve(WATERFALL, {}, []);
    server.use(
      http.post(apiUrl("/api/v1/report-runs"), () =>
        problemResponse("validation-failed", 422, "1 field needs attention.", {
          errors: [{ field: "parameters.currency_view", rule_id: "T-RPT-01", message }],
        }),
      ),
    );
    renderApp(`/reports/revenue_waterfall?${CONTEXT}&currency_view=functional`, {
      me: MARCUS,
      screenRoutes: SCREEN_ROUTES,
    });

    const toolbar = await screen.findByRole("toolbar", { name: "Report parameters" });
    expect(await within(toolbar).findByText(message)).toBeTruthy();
    expect(within(toolbar).getByText("Currency view")).toBeTruthy();
    expect(screen.queryByText("1 field needs attention.")).toBeNull();
  });

  // PRD ERR-97 (04 T-RPT-01 rule 6; item RPT-PERIOD-KEY-CALENDARS-1): what the view sends without an
  // entity, and where it says the refusal. The answer is the API's: the sentence is the detail and the
  // message of the one error, which names the entity scope — the pill's, no toolbar field.
  it.each([
    // A definition of one period: every entity in scope, by the key the address names.
    ["rpo", RPO, { book: "ASC606", period_key: "FY2026-P09" }],
    // A definition of a range: its keys come from the entity's calendar, so none is sent — the
    // waterfall's default range, each entity's own fiscal year.
    ["revenue_waterfall", WATERFALL, { book: "ASC606" }],
  ] as const)(
    "a period without an entity, %s: the refusal of two calendars stands in the banner",
    async (code, definition, parameters) => {
      serve(definition, {}, []);
      const posted: Record<string, unknown>[] = [];
      server.use(
        http.post(apiUrl("/api/v1/report-runs"), async ({ request }) => {
          posted.push((await request.json()) as Record<string, unknown>);
          return calendarsRefusal();
        }),
      );
      renderApp(`/reports/${code}?period=FY2026-P09&book=ASC606`, {
        me: MARCUS,
        screenRoutes: SCREEN_ROUTES,
      });

      expect(await screen.findByText(CALENDARS_DIFFER)).toBeTruthy();
      expect(screen.getByRole("heading", { name: "Check the highlighted fields" })).toBeTruthy();
      // No entity in the address: no `entity_codes`, which the API reads as every entity in scope.
      expect(posted[0]?.parameters).toEqual(parameters);
      const toolbar = screen.getByRole("toolbar", { name: "Report parameters" });
      expect(within(toolbar).queryByText(CALENDARS_DIFFER)).toBeNull();
    },
  );

  it("rpo bands and sections", async () => {
    const bands = [
      { index: 0, key: "within_12_months", from_month: 1, to_month: 12 },
      { index: 1, key: "months_13_to_24", from_month: 13, to_month: 24 },
      { index: 2, key: "after_24_months", from_month: 25, to_month: null },
    ];
    const run = reportRun({
      report: { code: "rpo", version: 1, name: "Remaining performance obligations" },
      parameters: {
        entity_codes: ["AVM-US"],
        book: "ASC606",
        period_key: "FY2026-P09",
        time_bands: [12, 24],
      },
      row_count: 2,
      tie_out_results: [],
      control_totals: {
        as_of: "2026-09-30",
        bands,
        total: { USD: "105043.80" },
        notes: [
          {
            entity_code: "AVM-US",
            section: 2,
            note: "No contracts are excluded. AVM-US applies no RPO practical expedient.",
          },
        ],
      },
    });
    const figures = {
      currency: "USD",
      total: money("105043.80"),
      within_12_months: money("70043.80"),
      months_13_to_24: money("35000.00"),
      after_24_months: money("0.00"),
      current: money("70043.80"),
      noncurrent: money("35000.00"),
    };
    serve(RPO, { [RUN_ID]: run }, [
      stored({
        row_key: "contract:SF-ORD-10417",
        section: 1,
        contract_external_id: "SF-ORD-10417",
        customer_name: "Orrin Vale Advisory",
        entity_code: "AVM-US",
        ...figures,
      }),
      stored({
        row_key: "TOTAL:USD",
        section: 1,
        contract_external_id: null,
        customer_name: null,
        entity_code: null,
        ...figures,
      }),
    ]);
    renderApp(`/reports/rpo?${CONTEXT}&run=${RUN_ID}`, { me: MARCUS, screenRoutes: SCREEN_ROUTES });

    const grid = await screen.findByTestId("SF-08-grid-remaining-performance-obligations");
    const headers = within(grid)
      .getAllByRole("columnheader")
      .map((header) => header.textContent);
    // L6-3-Q-26: one money column per `control_totals.bands[].key`, in API order.
    for (const header of [
      "Total (USD)",
      "Within 12 months (USD)",
      "13 to 24 months (USD)",
      "After 24 months (USD)",
      "Current (USD)",
      "Noncurrent (USD)",
    ]) {
      expect(headers.some((text) => text?.includes(header) === true)).toBe(true);
    }
    const row = await screen.findByTestId("SF-08-row-sf-ord-10417");
    expect(row.textContent).toContain("105,043.80");
    expect(row.textContent).toContain("70,043.80");
    // Section 2 rows carry `section: 2`; an empty section keeps its grid and the footnote.
    expect(screen.getByTestId("SF-08-grid-exempt-contracts")).toBeTruthy();
    expect(
      screen.getByText("No contracts are excluded. AVM-US applies no RPO practical expedient."),
    ).toBeTruthy();
    // RPT-06 "Time bands": the resolved bands of the run, read-only.
    const toolbar = screen.getByRole("toolbar", { name: "Report parameters" });
    expect(within(toolbar).getByText("12, 24 months")).toBeTruthy();
  });

  it("legacy export column order", async () => {
    // D-88 L7-1-Q-5 (over L7-3-Q-6; SCREENS_B RPT-10): a legacy export grid follows the run's `columns`,
    // the builder's output order, neither the order in which the row fields arrive nor their sorted
    // order. Synthetic names stand in for the 71 legacy names.
    const names = Array.from(
      { length: 71 },
      (_, index) => `Legacy column ${String(index + 1).padStart(2, "0")}`,
    );
    // A permutation that is neither sorted nor reversed: 01, 30, 59, 17, …
    const columns: ReportRunColumn[] = names.map((_, index) => {
      const key = names[(index * 29) % names.length] ?? "";
      return { key, header: key, kind: "text" };
    });
    const legacyRow = (version: number): ReportRow =>
      Object.fromEntries([
        ["row_key", `version:SF-ORD-10001:${String(version)}:O1`],
        ...[...names].reverse().map((name) => [name, `Value ${String(version)}.${name.slice(-2)}`]),
      ]) as ReportRow;
    const run = reportRun({
      report: { code: LEGACY_HISTORY.code, version: 1, name: LEGACY_HISTORY.name },
      parameters: {
        entity_codes: ["AVM-US"],
        book: "ASC606",
        from_date: "2026-01-01",
        to_date: "2026-08-30",
      },
      as_of: null,
      row_count: 2,
      control_totals: { row_count: 2, from_date: "2026-01-01", to_date: "2026-08-30" },
      tie_out_results: [],
    });
    serve(LEGACY_HISTORY, { [RUN_ID]: run }, [legacyRow(1), legacyRow(2)], [RUN_ID], columns);
    renderApp(`/reports/${LEGACY_HISTORY.code}?${CONTEXT}&run=${RUN_ID}`, {
      me: MARCUS,
      screenRoutes: SCREEN_ROUTES,
    });

    const grid = await screen.findByTestId("SF-08-grid-legacy-contract-history-export");
    const headers = within(grid)
      .getAllByRole("columnheader")
      .map((header) => header.textContent);
    expect(headers).toEqual(columns.map((column) => column.header));
    expect(headers.slice(0, 4)).toEqual([
      "Legacy column 01",
      "Legacy column 30",
      "Legacy column 59",
      "Legacy column 17",
    ]);
    expect(headers).not.toEqual(names);
    expect(headers).not.toEqual([...names].reverse());
    // `row_key` stays hidden (STRUCTURAL).
    expect(headers).not.toContain("row_key");
  });
});

describe("SF-08 catalogue", () => {
  it("groups the definitions and hides the forecast and migration codes", async () => {
    const definition = (code: string, name: string, kind: string): ReportDefinition => ({
      ...WATERFALL,
      code,
      name,
      kind,
      output_formats: ["XLSX", "CSV", "PDF", "JSON"],
    });
    server.use(
      http.get(apiUrl("/api/v1/me/notifications"), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get(apiUrl("/api/v1/entities"), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get(apiUrl("/api/v1/books"), () => HttpResponse.json({ items: [], next_cursor: null })),
      http.get(apiUrl("/api/v1/jobs"), () => HttpResponse.json({ items: [], next_cursor: null })),
      http.get(apiUrl("/api/v1/report-definitions"), () =>
        HttpResponse.json({
          items: [
            definition("revenue_waterfall", "Revenue waterfall", "STANDARD"),
            definition("rpo", "Remaining performance obligations", "DISCLOSURE"),
            definition("forecast_outputs", "Forecast outputs", "STANDARD"),
            definition("migration_reconciliation", "Migration reconciliation", "STANDARD"),
            definition(
              "legacy_contract_history_export",
              "Legacy contract history export",
              "LEGACY_EXPORT",
            ),
          ],
          next_cursor: null,
        }),
      ),
      http.get(apiUrl("/api/v1/report-runs"), () =>
        HttpResponse.json({
          items: [
            reportRun({ run_by: { id: MARCUS.user.id, display_name: "Maya Chen", kind: "USER" } }),
          ],
          next_cursor: null,
        }),
      ),
    );
    renderApp(`/reports?${CONTEXT}`, { me: MARCUS, screenRoutes: SCREEN_ROUTES });

    expect(await screen.findByRole("heading", { level: 1, name: "Reports" })).toBeTruthy();
    const balances = await screen.findByTestId("SF-08-grid-balances-and-disclosures");
    expect(within(balances).getByText("Balances and disclosures (1)")).toBeTruthy();
    const link = within(balances).getByRole("link", { name: "Remaining performance obligations" });
    expect(link.getAttribute("href")).toBe(`/reports/rpo?${CONTEXT}`);
    expect(screen.getByTestId("SF-08-row-rpo").textContent).toContain("XLSX CSV PDF");
    expect(screen.getByTestId("SF-08-grid-legacy-exports")).toBeTruthy();
    expect(screen.queryByText("Forecast outputs")).toBeNull();
    expect(screen.queryByText("Migration reconciliation")).toBeNull();
    const recent = await screen.findByTestId("SF-08-grid-recent-runs");
    expect(within(recent).getByRole("link", { name: "RPT-000412" })).toBeTruthy();
  });
});

const LEGACY_JE: ReportDefinition = {
  code: "legacy_je_summary",
  version: 1,
  name: "Legacy journal summary",
  kind: "LEGACY_EXPORT",
  description: "Journal activity by account, by entity and by legacy line item over a date range.",
  parameters_schema: schema({
    entity_codes: { type: "array" },
    book: { type: "string", enum: ["ASC606"] },
    from_date: { type: "string", format: "date" },
    to_date: { type: "string", format: "date" },
    mode: { type: "string", enum: ["GROSS", "DELTA"] },
  }),
  output_formats: ["XLSX", "CSV", "JSON"],
  tie_outs: [],
  ipe_logic: null,
};

describe("SF-06:entries Journal entries by date range", () => {
  it("by account totals from the run and the gross parameters", async () => {
    const run = reportRun({
      report: { code: "legacy_je_summary", version: 1, name: "Legacy journal summary" },
      parameters: {
        entity_codes: ["AVM-US"],
        book: "ASC606",
        from_date: "2026-08-01",
        to_date: "2026-08-31",
        mode: "GROSS",
      },
      as_of: null,
      row_count: 6,
      tie_out_results: [],
      control_totals: {
        mode: "GROSS",
        book: "ASC606",
        from_date: "2026-08-01",
        to_date: "2026-08-31",
        lines: 3,
        total_debit: { USD: "354.54" },
        total_credit: { USD: "354.54" },
        net: { USD: "0.00" },
      },
    });
    const rows: ReportRow[] = [
      stored({
        row_key: "account:21001",
        section: "by_account",
        account: "21001",
        currency: "USD",
        debit: money("295.69"),
        credit: money("0.00"),
        net: money("295.69"),
      }),
      stored({
        row_key: "account:5001",
        section: "by_account",
        account: "5001",
        currency: "USD",
        debit: money("0.00"),
        credit: money("354.54"),
        net: money("-354.54"),
      }),
      stored({
        row_key: "account:15002",
        section: "by_account",
        account: "15002",
        currency: "USD",
        debit: money("58.85"),
        credit: money("0.00"),
        net: money("58.85"),
      }),
      stored({
        row_key: "entity:AVM-US",
        section: "by_entity",
        entity_code: "AVM-US",
        currency: "USD",
        debit: money("354.54"),
        credit: money("354.54"),
        balanced: true,
        difference: money("0.00"),
      }),
      stored({
        row_key: "item:Contract 1 POB #1 Hardware 1:5001",
        section: "line_items",
        key: "Contract 1 POB #1 Hardware 1",
        account: "5001",
        entity_code: "AVM-US",
        currency: "USD",
        amount: money("-354.54"),
      }),
    ];
    const { posted } = serve(LEGACY_JE, { [RUN_ID]: run }, rows);
    renderApp(
      "/journals/entries?entity=AVM-US&period=FY2026-P08&book=ASC606&format=gross&from=2026-08-01&to=2026-08-31",
      { me: MARCUS, screenRoutes: SCREEN_ROUTES },
    );

    expect(await screen.findByRole("heading", { level: 1, name: "Journals" })).toBeTruthy();
    await waitFor(() => {
      expect(posted[0]).toMatchObject({
        report_code: "legacy_je_summary",
        output_format: "JSON",
        parameters: {
          entity_codes: ["AVM-US"],
          book: "ASC606",
          from_date: "2026-08-01",
          to_date: "2026-08-31",
          mode: "GROSS",
        },
      });
    });
    const byAccount = await screen.findByTestId("SF-06-grid-entries-by-account");
    expect(within(byAccount).getByRole("grid", { name: "Journal lines by account" })).toBeTruthy();
    // D-88 L7-3-Q-22: each grid keeps its name and is described by the §3.5 caption of the posted range.
    const description = (grid: HTMLElement) =>
      document.getElementById(grid.getAttribute("aria-describedby") ?? "")?.textContent ?? null;
    expect(
      description(within(byAccount).getByRole("grid", { name: "Journal lines by account" })),
    ).toBe("Journal lines by account, 01 Aug 2026 to 31 Aug 2026, gross view");
    expect(
      description(
        within(screen.getByTestId("SF-06-grid-entries-by-entity")).getByRole("grid", {
          name: "Journal lines by entity",
        }),
      ),
    ).toBe("Journal lines by entity, 01 Aug 2026 to 31 Aug 2026, gross view");
    expect(
      description(
        within(screen.getByTestId("SF-06-grid-entries-line-items")).getByRole("grid", {
          name: "Line items",
        }),
      ),
    ).toBe("Line items, 01 Aug 2026 to 31 Aug 2026, gross view");
    const account = await screen.findByTestId("SF-06-row-21001");
    expect(account.textContent).toContain("295.69");
    const headers = within(byAccount)
      .getAllByRole("columnheader")
      .map((header) => header.textContent ?? "");
    expect(headers.map((header) => header.replace(/Column menu.*$/, ""))).toEqual([
      expect.stringMatching(/^Account/),
      expect.stringMatching(/^Debit \(USD\)/),
      expect.stringMatching(/^Credit \(USD\)/),
      expect.stringMatching(/^Net \(USD\)/),
    ]);
    // DS-FMT-02: the totals row is the run's control totals, Dr = Cr.
    const total = within(byAccount)
      .getAllByRole("row")
      .find((row) => within(row).queryByRole("rowheader", { name: "Total" }) !== null);
    const cells = total === undefined ? [] : within(total).getAllByRole("gridcell");
    expect(cells.map((cell) => cell.textContent)).toEqual(["354.54", "354.54", "0.00"]);
    expect(screen.getByTestId("SF-06-grid-entries-line-items")).toBeTruthy();
    expect(screen.getByTestId("SF-06-run-stamp").textContent).toContain(
      "Legacy journal summary v1",
    );
    expect(
      within(screen.getByTestId("SF-06-entries-format")).getByRole("radiogroup", {
        name: "Journal view",
      }),
    ).toBeTruthy();
  });

  // SCREENS §0.6 SCR-PERM-02 (a) (rev 1.30; item W-12, slice c): the periods the page reads are those
  // of the context entity, so `config.read` is asked for it.
  it("the periods of the context entity are read with config.read for that entity", async () => {
    const other = "0a1b2c3d-4e5f-4a6b-8c7d-000000000004";
    const run = reportRun({
      report: { code: "legacy_je_summary", version: 1, name: "Legacy journal summary" },
      parameters: {
        entity_codes: ["AVM-US"],
        book: "ASC606",
        from_date: "2026-08-01",
        to_date: "2026-08-31",
        mode: "GROSS",
      },
      as_of: null,
      row_count: 0,
      tie_out_results: [],
    });
    const periodRequests: string[] = [];
    const arrange = () => {
      serve(LEGACY_JE, { [RUN_ID]: run }, []);
      periodRequests.length = 0;
      server.use(
        http.get(apiUrl("/api/v1/entities"), () =>
          HttpResponse.json({
            items: [
              { ...AVM_US, is_active: true, books: [] },
              { id: other, code: "AVM-JP", name: "Avenmoor Japan KK", is_active: true, books: [] },
            ],
            next_cursor: null,
          }),
        ),
        http.get(apiUrl("/api/v1/periods"), ({ request }) => {
          periodRequests.push(new URL(request.url).search);
          return HttpResponse.json({ items: PERIODS, next_cursor: null });
        }),
      );
    };
    const member = (entityId: string) =>
      signedInMe({
        permissions: MARCUS.permissions,
        permission_scopes: {
          "contract.read": "*",
          "config.read": [entityId],
          "report.run": "*",
          "report.export": "*",
        },
      });
    const entries = `/journals/entries?entity=AVM-US&period=FY2026-P08&book=ASC606&format=gross&from=2026-08-01&to=2026-08-31&run=${RUN_ID}`;

    arrange();
    const first = renderApp(entries, { me: member(AVM_US.id), screenRoutes: SCREEN_ROUTES });
    await screen.findByTestId("SF-06-run-stamp");
    await waitFor(() => expect(periodRequests.length).toBeGreaterThan(0));
    await waitFor(() => expect(first.queryClient.isFetching()).toBe(0));
    cleanup();

    arrange();
    const second = renderApp(entries, { me: member(other), screenRoutes: SCREEN_ROUTES });
    await screen.findByTestId("SF-06-run-stamp");
    await waitFor(() => expect(second.queryClient.isFetching()).toBe(0));
    expect(periodRequests).toEqual([]);
  });

  it("legacy book banner answers only the T-REF-03 mode refusal", async () => {
    for (const field of ["mode", "parameters.mode"]) {
      const failed = reportRun({
        report: { code: "legacy_je_summary", version: 1, name: "Legacy journal summary" },
        status: "FAILED",
        parameters: {
          entity_codes: ["AVM-US"],
          book: "ASC606",
          from_date: "2026-08-01",
          to_date: "2026-08-31",
          mode: "DELTA",
        },
        as_of: null,
        row_count: 0,
        tie_out_results: [],
        control_totals: null,
        output: null,
        problem: {
          type: "validation-failed",
          title: "1 field needs attention.",
          status: 422,
          instance: `/api/v1/report-runs/${RUN_ID}`,
          errors: [
            {
              field,
              rule_id: "T-REF-03",
              message: "Enable the Legacy book for AVM-US before viewing adjustment journals.",
            },
          ],
        },
      });
      serve(LEGACY_JE, { [RUN_ID]: failed }, []);
      renderApp(
        `/journals/entries?entity=AVM-US&period=FY2026-P08&book=ASC606&format=adjustment&from=2026-08-01&to=2026-08-31&run=${RUN_ID}`,
        { me: MARCUS, screenRoutes: SCREEN_ROUTES },
      );
      // SCREENS_B §3.5 (POL-007): the RPS-5 LEGACY_NOT_KEPT refusal is the info banner, not SCR-ST-12.
      expect(
        await screen.findByText(
          "The adjustment view needs the Legacy book. Enable it for AVM-US to see pre-standard revenue reversals.",
        ),
      ).toBeTruthy();
      expect(
        screen.queryByText("Running Legacy journal summary failed. Nothing was committed."),
      ).toBeNull();
      cleanup();
    }
  });

  it("another failed adjustment run shows the job failed banner", async () => {
    const problems = [
      {
        type: "validation-failed",
        title: "1 field needs attention.",
        status: 422,
        instance: `/api/v1/report-runs/${RUN_ID}`,
        errors: [
          { field: "entity_codes", rule_id: "T-REF-03", message: "AVM-XX is not an entity." },
        ],
      },
      {
        type: "internal-error",
        title: "The journal summary could not be built.",
        status: 500,
        instance: `/api/v1/report-runs/${RUN_ID}`,
        errors: [],
      },
    ];
    for (const problem of problems) {
      const failed = reportRun({
        report: { code: "legacy_je_summary", version: 1, name: "Legacy journal summary" },
        status: "FAILED",
        parameters: {
          entity_codes: ["AVM-US"],
          book: "ASC606",
          from_date: "2026-08-01",
          to_date: "2026-08-31",
          mode: "DELTA",
        },
        as_of: null,
        row_count: 0,
        tie_out_results: [],
        control_totals: null,
        output: null,
        problem,
      });
      serve(LEGACY_JE, { [RUN_ID]: failed }, []);
      renderApp(
        `/journals/entries?entity=AVM-US&period=FY2026-P08&book=ASC606&format=adjustment&from=2026-08-01&to=2026-08-31&run=${RUN_ID}`,
        { me: MARCUS, screenRoutes: SCREEN_ROUTES },
      );
      // RV-14: SCR-ST-12 with the problem title and Retry.
      expect(
        await screen.findByText("Running Legacy journal summary failed. Nothing was committed."),
      ).toBeTruthy();
      expect(screen.getByText(problem.title)).toBeTruthy();
      expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
      expect(screen.queryByText(/^The adjustment view needs the Legacy book\./)).toBeNull();
      // A run opened from the URL was not created here, so no job reference is known.
      expect(screen.queryByText(/^Reference /)).toBeNull();
      cleanup();
    }
  });

  it("a failed run the page created names its job reference", async () => {
    // D-90 L8-R-Q-4: SCR-ST-12 "Reference <job id prefix>", as SF-08:report shows it.
    const failed = reportRun({
      report: { code: "legacy_je_summary", version: 1, name: "Legacy journal summary" },
      status: "FAILED",
      parameters: {
        entity_codes: ["AVM-US"],
        book: "ASC606",
        from_date: "2026-08-01",
        to_date: "2026-08-31",
        mode: "GROSS",
      },
      as_of: null,
      row_count: 0,
      tie_out_results: [],
      control_totals: null,
      output: null,
      problem: {
        type: "internal-error",
        title: "The journal summary could not be built.",
        status: 500,
        instance: `/api/v1/report-runs/${RUN_ID}`,
        errors: [],
      },
    });
    const { posted } = serve(LEGACY_JE, { [RUN_ID]: failed }, []);
    renderApp(
      "/journals/entries?entity=AVM-US&period=FY2026-P08&book=ASC606&format=gross&from=2026-08-01&to=2026-08-31",
      { me: MARCUS, screenRoutes: SCREEN_ROUTES },
    );

    expect(
      await screen.findByText("Running Legacy journal summary failed. Nothing was committed."),
    ).toBeTruthy();
    expect(posted).toHaveLength(1);
    expect(screen.getByText(`Reference ${JOB_ID.slice(0, 8)}.`)).toBeTruthy();
  });

  it("the legacy_je_summary report view redirects to SF-06:entries", async () => {
    serve(LEGACY_JE, { [RUN_ID]: reportRun() }, []);
    const { router } = renderApp(
      "/reports/legacy_je_summary?entity=AVM-US&period=FY2026-P08&book=ASC606&p.from_date=2026-08-01&p.to_date=2026-08-31&p.mode=DELTA",
      { me: MARCUS, screenRoutes: SCREEN_ROUTES },
    );
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/journals/entries");
    });
    expect(router.state.location.search).toBe(
      "?entity=AVM-US&period=FY2026-P08&book=ASC606&from=2026-08-01&to=2026-08-31&format=adjustment",
    );
  });
});

// L9-PLT batch 2 (plt-job-reference): SCR-ST-12 names the job of "a command started on the screen", so the
// "Reference <job id prefix>" line is bound to the (run, job) pair the mounted view created. A stored run
// opened afterwards in the same mounted view (a `run` navigation; SCR-URL-16, RV-01) was not started here
// and shows no reference; the created run names its job again when it is displayed again; Retry from a
// stored failed run binds the new job to the run the retry created. No shipped link changes `run` on a
// mounted view today, so the tests drive the navigation with `router.navigate`.
describe("job reference is bound to the displayed run (SF-08:report, SF-06:entries)", () => {
  const THIRD_RUN_ID = "5b0c7a1e-3d2f-4e6a-9b8c-7d6e5f4a3b2e";
  const JOB_C = "c0ffee11-2222-4333-8444-555566667777";
  const REF_A = `Reference ${JOB_ID.slice(0, 8)}.`;
  const REF_C = `Reference ${JOB_C.slice(0, 8)}.`;
  const ANY_REFERENCE = /^Reference /;
  const OPTIONS = { me: MARCUS, screenRoutes: SCREEN_ROUTES };
  const ENTRIES_SEARCH =
    "?entity=AVM-US&period=FY2026-P08&book=ASC606&format=gross&from=2026-08-01&to=2026-08-31";
  const entries = (suffix = "") => `/journals/entries${ENTRIES_SEARCH}${suffix}`;
  const report = (suffix = "") => `/reports/revenue_waterfall?${CONTEXT}${suffix}`;
  const LEGACY_REPORT = { code: "legacy_je_summary", version: 1, name: "Legacy journal summary" };
  const LEGACY_PARAMETERS = {
    entity_codes: ["AVM-US"],
    book: "ASC606",
    from_date: "2026-08-01",
    to_date: "2026-08-31",
    mode: "GROSS",
  };
  const A_TITLE = "The run this view created failed.";
  const B_TITLE = "The stored run B failed earlier.";
  const C_TITLE = "The run the retry created failed too.";

  function failedRun(
    id: string,
    title: string,
    shape: Partial<ReportRun> = {},
    extra: Partial<ReportRun> = {},
  ): ReportRun {
    return reportRun({
      ...shape,
      id,
      status: "FAILED",
      as_of: null,
      row_count: 0,
      tie_out_results: [],
      control_totals: null,
      output: null,
      problem: {
        type: "internal-error",
        title,
        status: 500,
        instance: `/api/v1/report-runs/${id}`,
        errors: [],
      },
      ...extra,
    });
  }
  const legacyRuns = () => ({
    [RUN_ID]: failedRun(RUN_ID, A_TITLE, { report: LEGACY_REPORT, parameters: LEGACY_PARAMETERS }),
    [SECOND_RUN_ID]: failedRun(
      SECOND_RUN_ID,
      B_TITLE,
      { report: LEGACY_REPORT, parameters: LEGACY_PARAMETERS },
      { report_run_no: "RPT-000398" },
    ),
    [THIRD_RUN_ID]: failedRun(
      THIRD_RUN_ID,
      C_TITLE,
      { report: LEGACY_REPORT, parameters: LEGACY_PARAMETERS },
      { report_run_no: "RPT-000399" },
    ),
  });
  const waterfallRuns = () => ({
    [RUN_ID]: failedRun(RUN_ID, A_TITLE),
    [SECOND_RUN_ID]: failedRun(SECOND_RUN_ID, B_TITLE, {}, { report_run_no: "RPT-000398" }),
    [THIRD_RUN_ID]: failedRun(THIRD_RUN_ID, C_TITLE, {}, { report_run_no: "RPT-000399" }),
  });

  interface CreatedPair {
    readonly run: string;
    readonly job: string;
  }
  /**
   * Each creation answers its own (run, job) pair, as the API does: the first POST creates A with JOB_ID,
   * the second creates C with JOB_C. msw prepends later handlers, so this shadows the `serve()` POST.
   */
  function servePairs(pairs: readonly [CreatedPair, ...CreatedPair[]]) {
    let count = 0;
    server.use(
      http.post(apiUrl("/api/v1/report-runs"), () => {
        const chosen = pairs[Math.min(count, pairs.length - 1)] ?? pairs[0];
        count += 1;
        return HttpResponse.json(
          { id: chosen.job, kind: "REPORT_RUN", state: "QUEUED" },
          {
            status: 202,
            headers: { Location: `/api/v1/jobs/${chosen.job}`, "X-Erev-Report-Run-Id": chosen.run },
          },
        );
      }),
      http.get(apiUrl("/api/v1/jobs/:jobId"), ({ params }) =>
        HttpResponse.json({
          id: String(params.jobId),
          kind: "REPORT_RUN",
          state: "SUCCEEDED",
          progress: null,
          started_at: "2026-09-12T16:02:11Z",
          finished_at: "2026-09-12T16:02:19Z",
          problem: null,
          result: null,
        }),
      ),
    );
    return { posts: () => count };
  }
  const runOf = (router: { readonly state: { readonly location: { readonly search: string } } }) =>
    new URLSearchParams(router.state.location.search).get("run");

  it("SF-06:entries A to B: a stored failed run opened in the mounted view shows no reference", async () => {
    const { posted } = serve(LEGACY_JE, legacyRuns(), []);
    const { router } = renderApp(entries(), OPTIONS);

    // Run A: created by this view (one POST); its job is named (D-90 L8-R-Q-4).
    expect(await screen.findByText(REF_A)).toBeTruthy();
    expect(screen.getByText(A_TITLE)).toBeTruthy();
    expect(posted).toHaveLength(1);
    expect(runOf(router)).toBe(RUN_ID);

    // Run B: a stored run opened in the same mounted view; SCR-URL-16 renders it and creates none.
    await router.navigate(entries(`&run=${SECOND_RUN_ID}`));
    expect(await screen.findByText(B_TITLE)).toBeTruthy();
    expect(screen.queryByText(A_TITLE)).toBeNull();
    expect(posted).toHaveLength(1);
    // B was not started on this screen, and the API names no job of B: no reference may be shown.
    expect(screen.queryByText(ANY_REFERENCE)).toBeNull();
  });

  it("SF-08:report A to B: a stored failed run opened in the mounted view shows no reference", async () => {
    const { posted } = serve(WATERFALL, waterfallRuns(), []);
    const { router } = renderApp(report(), OPTIONS);

    expect(await screen.findByText(REF_A)).toBeTruthy();
    expect(screen.getByText(A_TITLE)).toBeTruthy();
    expect(posted).toHaveLength(1);
    expect(runOf(router)).toBe(RUN_ID);

    await router.navigate(report(`&run=${SECOND_RUN_ID}`));
    expect(await screen.findByText(B_TITLE)).toBeTruthy();
    expect(screen.queryByText(A_TITLE)).toBeNull();
    expect(posted).toHaveLength(1);
    expect(screen.queryByText(ANY_REFERENCE)).toBeNull();
  });

  it("SF-06:entries A to B to A: the created run names its job again when displayed again", async () => {
    const { posted } = serve(LEGACY_JE, legacyRuns(), []);
    const { router } = renderApp(entries(), OPTIONS);
    expect(await screen.findByText(REF_A)).toBeTruthy();

    await router.navigate(entries(`&run=${SECOND_RUN_ID}`));
    expect(await screen.findByText(B_TITLE)).toBeTruthy();
    expect(screen.queryByText(ANY_REFERENCE)).toBeNull();

    // Back to A: the stored pair still names A's job; no run was created on the way.
    await router.navigate(entries(`&run=${RUN_ID}`));
    expect(await screen.findByText(A_TITLE)).toBeTruthy();
    expect(screen.getByText(REF_A)).toBeTruthy();
    expect(posted).toHaveLength(1);
  });

  it("SF-08:report A to B to A: the created run names its job again when displayed again", async () => {
    const { posted } = serve(WATERFALL, waterfallRuns(), []);
    const { router } = renderApp(report(), OPTIONS);
    expect(await screen.findByText(REF_A)).toBeTruthy();

    await router.navigate(report(`&run=${SECOND_RUN_ID}`));
    expect(await screen.findByText(B_TITLE)).toBeTruthy();
    expect(screen.queryByText(ANY_REFERENCE)).toBeNull();

    await router.navigate(report(`&run=${RUN_ID}`));
    expect(await screen.findByText(A_TITLE)).toBeTruthy();
    expect(screen.getByText(REF_A)).toBeTruthy();
    expect(posted).toHaveLength(1);
  });

  it("SF-06:entries Retry from stored failed B binds the new job to the run the retry created", async () => {
    serve(LEGACY_JE, legacyRuns(), []);
    const { posts } = servePairs([
      { run: RUN_ID, job: JOB_ID },
      { run: THIRD_RUN_ID, job: JOB_C },
    ]);
    const { router } = renderApp(entries(), OPTIONS);
    expect(await screen.findByText(REF_A)).toBeTruthy();

    await router.navigate(entries(`&run=${SECOND_RUN_ID}`));
    expect(await screen.findByText(B_TITLE)).toBeTruthy();
    expect(screen.queryByText(ANY_REFERENCE)).toBeNull();

    // Retry on B creates a run (the API names it C with its own job); the reference is C's, never A's.
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(C_TITLE)).toBeTruthy();
    expect(screen.getByText(REF_C)).toBeTruthy();
    expect(screen.queryByText(REF_A)).toBeNull();
    expect(posts()).toBe(2);
    expect(runOf(router)).toBe(THIRD_RUN_ID);
  });

  it("SF-08:report Retry from stored failed B binds the new job to the run the retry created", async () => {
    serve(WATERFALL, waterfallRuns(), []);
    const { posts } = servePairs([
      { run: RUN_ID, job: JOB_ID },
      { run: THIRD_RUN_ID, job: JOB_C },
    ]);
    const { router } = renderApp(report(), OPTIONS);
    expect(await screen.findByText(REF_A)).toBeTruthy();

    await router.navigate(report(`&run=${SECOND_RUN_ID}`));
    expect(await screen.findByText(B_TITLE)).toBeTruthy();
    expect(screen.queryByText(ANY_REFERENCE)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(C_TITLE)).toBeTruthy();
    expect(screen.getByText(REF_C)).toBeTruthy();
    expect(screen.queryByText(REF_A)).toBeNull();
    expect(posts()).toBe(2);
    expect(runOf(router)).toBe(THIRD_RUN_ID);
  });
});

// L9-PLT-Q-6 (D-90e (i); SCREENS_B rev 1.6 RV-01; PR-8.2): the problem of a refused `POST /report-runs`
// belongs to the parameter set and source it was attempted for, not to the mounted view. A stored run opened
// afterwards by a `run` navigation (RV-01; SCR-URL-16) shows none of it, and the problem returns with its
// parameter set without a second creation.
describe("the creation problem is bound to its parameter set (SF-08:report, SF-06:entries)", () => {
  const OPTIONS = { me: MARCUS, screenRoutes: SCREEN_ROUTES };
  const ENTRIES_SEARCH =
    "?entity=AVM-US&period=FY2026-P08&book=ASC606&format=gross&from=2026-08-01&to=2026-08-31";
  const entries = (suffix = "") => `/journals/entries${ENTRIES_SEARCH}${suffix}`;
  const report = (suffix = "") => `/reports/revenue_waterfall?${CONTEXT}${suffix}`;
  const REFUSED_TITLE = "The report parameters were refused.";
  const REFUSED_MESSAGE = "AVM-US keeps no ASC606 book before FY2026-P01.";
  const STORED_B_NO = "RPT-000398";
  const runOf = (router: { readonly state: { readonly location: { readonly search: string } } }) =>
    new URLSearchParams(router.state.location.search).get("run");

  /** Every creation is refused with one finding naming no field, so it renders in the problem banner (L6-3-Q-20). */
  function refuseCreation() {
    let count = 0;
    server.use(
      http.post(apiUrl("/api/v1/report-runs"), () => {
        count += 1;
        return problemResponse("validation-failed", 422, REFUSED_TITLE, {
          errors: [{ field: null, rule_id: "T-RPT-02", message: REFUSED_MESSAGE }],
        });
      }),
    );
    return { posts: () => count };
  }

  it("SF-08:report A to B to A: a stored run shows no refusal of A, which returns with A", async () => {
    serve(
      WATERFALL,
      { [SECOND_RUN_ID]: reportRun({ id: SECOND_RUN_ID, report_run_no: STORED_B_NO }) },
      WATERFALL_ROWS,
    );
    const { posts } = refuseCreation();
    const { router } = renderApp(report(), OPTIONS);

    // A: the creation is refused; no run exists and the banner names the finding.
    expect(await screen.findByText(REFUSED_TITLE)).toBeTruthy();
    expect(screen.getByText(REFUSED_MESSAGE)).toBeTruthy();
    expect(posts()).toBe(1);
    expect(runOf(router)).toBeNull();

    // B: a stored run opened in the same mounted view renders and creates none; A's refusal is not B's.
    await router.navigate(report(`&run=${SECOND_RUN_ID}`));
    expect(await screen.findByTestId("SF-08-row-sf-ord-10001")).toBeTruthy();
    expect(screen.queryByText(REFUSED_TITLE)).toBeNull();
    expect(screen.queryByText(REFUSED_MESSAGE)).toBeNull();
    expect(posts()).toBe(1);

    // A again: the refusal belongs to A's parameter set and returns without a second creation.
    await router.navigate(report());
    expect(await screen.findByText(REFUSED_TITLE)).toBeTruthy();
    expect(screen.getByText(REFUSED_MESSAGE)).toBeTruthy();
    expect(posts()).toBe(1);
  });

  it("SF-06:entries A to B to A: a stored run shows no refusal of A, which returns with A", async () => {
    const storedB = reportRun({
      id: SECOND_RUN_ID,
      report_run_no: STORED_B_NO,
      report: { code: "legacy_je_summary", version: 1, name: "Legacy journal summary" },
      parameters: {
        entity_codes: ["AVM-US"],
        book: "ASC606",
        from_date: "2026-08-01",
        to_date: "2026-08-31",
        mode: "GROSS",
      },
      as_of: null,
      row_count: 0,
      tie_out_results: [],
      control_totals: null,
    });
    serve(LEGACY_JE, { [SECOND_RUN_ID]: storedB }, []);
    const { posts } = refuseCreation();
    const { router } = renderApp(entries(), OPTIONS);

    expect(await screen.findByText(REFUSED_TITLE)).toBeTruthy();
    expect(screen.getByText(REFUSED_MESSAGE)).toBeTruthy();
    expect(posts()).toBe(1);
    expect(runOf(router)).toBeNull();

    await router.navigate(entries(`&run=${SECOND_RUN_ID}`));
    const stamp = await screen.findByTestId("SF-06-run-stamp");
    expect(stamp.textContent).toContain(STORED_B_NO);
    expect(screen.queryByText(REFUSED_TITLE)).toBeNull();
    expect(screen.queryByText(REFUSED_MESSAGE)).toBeNull();
    expect(posts()).toBe(1);

    await router.navigate(entries());
    expect(await screen.findByText(REFUSED_TITLE)).toBeTruthy();
    expect(screen.getByText(REFUSED_MESSAGE)).toBeTruthy();
    expect(posts()).toBe(1);
  });

  // REPORT-RERUN-AFTER-REFUSAL-1 (SCREENS_B rev 1.92 RV-01): "Run report" asks. Pressed on the parameter
  // set of a refused creation it sends that creation again — before, the refusal was cleared and nothing
  // was sent, so the view stood empty — and a parameter changed first is asked once, with its new value.
  /** The first creation is refused as `refuseCreation` refuses; every later one is accepted as `RUN_ID`. */
  function refuseFirstCreation() {
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
    return { posted };
  }

  it("SF-08:report: Run report on a refused parameter set asks the creation again", async () => {
    serve(WATERFALL, { [RUN_ID]: reportRun() }, WATERFALL_ROWS);
    const { posted } = refuseFirstCreation();
    const { router } = renderApp(report(), OPTIONS);
    expect(await screen.findByText(REFUSED_MESSAGE)).toBeTruthy();
    expect(posted).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Run report" }));
    // The same parameter set, asked again: the run it makes is shown and the refusal is gone.
    expect(await screen.findByTestId("SF-08-row-sf-ord-10001")).toBeTruthy();
    expect(posted).toHaveLength(2);
    expect(posted[1]).toEqual(posted[0]);
    expect(runOf(router)).toBe(RUN_ID);
    expect(screen.queryByText(REFUSED_TITLE)).toBeNull();
    expect(screen.queryByText(REFUSED_MESSAGE)).toBeNull();
  });

  it("SF-08:report: a parameter changed after a refusal is asked once, with its new value", async () => {
    serve(WATERFALL, { [RUN_ID]: reportRun() }, WATERFALL_ROWS);
    const { posted } = refuseFirstCreation();
    const { router } = renderApp(report(), OPTIONS);
    expect(await screen.findByText(REFUSED_MESSAGE)).toBeTruthy();
    expect(posted).toHaveLength(1);
    expect(posted[0]?.parameters).not.toHaveProperty("granularity");

    const toolbar = screen.getByRole("toolbar", { name: "Report parameters" });
    fireEvent.click(within(toolbar).getByRole("radio", { name: "Quarter" }));
    fireEvent.click(within(toolbar).getByRole("button", { name: "Run report" }));
    expect(await screen.findByTestId("SF-08-row-sf-ord-10001")).toBeTruthy();
    // One creation, for the set the address now holds: the set that was refused is not sent beside it.
    expect(posted).toHaveLength(2);
    expect(posted[1]?.parameters).toMatchObject({ granularity: "QUARTER" });
    expect(new URLSearchParams(router.state.location.search).get("p.granularity")).toBe("QUARTER");
  });

  it("SF-06:entries: Run report on a refused parameter set asks the creation again", async () => {
    const run = reportRun({
      report: { code: "legacy_je_summary", version: 1, name: "Legacy journal summary" },
      parameters: {
        entity_codes: ["AVM-US"],
        book: "ASC606",
        from_date: "2026-08-01",
        to_date: "2026-08-31",
        mode: "GROSS",
      },
      as_of: null,
      row_count: 0,
      tie_out_results: [],
      control_totals: null,
    });
    serve(LEGACY_JE, { [RUN_ID]: run }, []);
    const { posted } = refuseFirstCreation();
    const { router } = renderApp(entries(), OPTIONS);
    expect(await screen.findByText(REFUSED_MESSAGE)).toBeTruthy();
    expect(posted).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Run report" }));
    const stamp = await screen.findByTestId("SF-06-run-stamp");
    expect(stamp.textContent).toContain("RPT-000412");
    expect(posted).toHaveLength(2);
    expect(posted[1]).toEqual(posted[0]);
    expect(runOf(router)).toBe(RUN_ID);
    expect(screen.queryByText(REFUSED_MESSAGE)).toBeNull();
  });

  it("SF-06:entries: entities and a date changed after a refusal are asked once, with both", async () => {
    const run = reportRun({
      report: { code: "legacy_je_summary", version: 1, name: "Legacy journal summary" },
      parameters: {
        entity_codes: ["AVM-UK", "AVM-US"],
        book: "ASC606",
        from_date: "2026-08-01",
        to_date: "2026-08-30",
        mode: "GROSS",
      },
      as_of: null,
      row_count: 0,
      tie_out_results: [],
      control_totals: null,
    });
    serve(LEGACY_JE, { [RUN_ID]: run }, []);
    server.use(
      http.get(apiUrl("/api/v1/entities"), () =>
        HttpResponse.json({
          items: ["AVM-UK", "AVM-US"].map((code, index) => ({
            id: `e0000000-0000-4000-8000-00000000000${String(index + 1)}`,
            code,
            name: `Avenmoor ${code}`,
            calendar_id: "c0000000-0000-4000-8000-000000000001",
            functional_currency: "USD",
            country_code: null,
            tax_id: null,
            time_zone: "UTC",
            parent_entity_id: null,
            is_active: true,
            row_version: 1,
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
            books: [{ book_code: "ASC606", is_enabled: true }],
          })),
          next_cursor: null,
        }),
      ),
    );
    const { posted } = refuseFirstCreation();
    renderApp(entries(), OPTIONS);
    expect(await screen.findByText(REFUSED_MESSAGE)).toBeTruthy();
    expect(posted).toHaveLength(1);

    // The entities are the screen's own state and the dates are the address's: both change with one press.
    const toolbar = screen.getByRole("toolbar", { name: "Report parameters" });
    fireEvent.change(within(toolbar).getByRole("combobox", { name: /^Entities/ }), {
      target: { value: "AVM-UK" },
    });
    fireEvent.mouseDown(await within(toolbar).findByRole("option", { name: "AVM-UK" }));
    const to = within(toolbar).getByRole("textbox", { name: /^To/ });
    fireEvent.change(to, { target: { value: "30 Aug 2026" } });
    fireEvent.blur(to);
    fireEvent.click(within(toolbar).getByRole("button", { name: "Run report" }));

    expect(await screen.findByTestId("SF-06-run-stamp")).toBeTruthy();
    expect(posted).toHaveLength(2);
    expect(posted[1]?.parameters).toMatchObject({
      entity_codes: ["AVM-US", "AVM-UK"],
      to_date: "2026-08-30",
    });
  });
});

// RV-14 rev 1.7 (D-90e (i) L9-PLT-Q-5; PR-8.1): the "Reference <job id prefix>" line names the displayed run's
// own job (API-S-ReportRun `job_id`, 04 rev 1.17) on every report surface, for created, stored and later-opened
// runs; a record without `job_id` keeps the rev 1.5 created-pair rule. Every creation answer is bound to the
// attempt that produced it: a 202 arriving after a later attempt is discarded (late-response ownership guard).
describe("the Reference line names the displayed run's own job (SF-08:report, SF-06:entries)", () => {
  const OPTIONS = { me: MARCUS, screenRoutes: SCREEN_ROUTES };
  const ENTRIES_SEARCH =
    "?entity=AVM-US&period=FY2026-P08&book=ASC606&format=gross&from=2026-08-01&to=2026-08-31";
  const entries = (suffix = "") => `/journals/entries${ENTRIES_SEARCH}${suffix}`;
  const report = (suffix = "") => `/reports/revenue_waterfall?${CONTEXT}${suffix}`;
  const LATE_RUN_ID = "5b0c7a1e-3d2f-4e6a-9b8c-7d6e5f4a3b2f";
  const JOB_B = "b0b0b0b0-1111-4222-8333-444455556666";
  const JOB_C = "c0ffee11-2222-4333-8444-555566667777";
  const REF_A = `Reference ${JOB_ID.slice(0, 8)}.`;
  const REF_B = `Reference ${JOB_B.slice(0, 8)}.`;
  const REF_C = `Reference ${JOB_C.slice(0, 8)}.`;
  const A_TITLE = "The run this view created failed.";
  const B_TITLE = "The stored run B failed earlier.";
  const C_TITLE = "The run the second attempt created failed.";
  const LEGACY_REPORT = { code: "legacy_je_summary", version: 1, name: "Legacy journal summary" };
  const LEGACY_PARAMETERS = {
    entity_codes: ["AVM-US"],
    book: "ASC606",
    from_date: "2026-08-01",
    to_date: "2026-08-31",
    mode: "GROSS",
  };
  const runOf = (router: { readonly state: { readonly location: { readonly search: string } } }) =>
    new URLSearchParams(router.state.location.search).get("run");

  /** A failed run whose record names its job (`job_id`), as the API stamps it at creation. */
  function failedRun(
    id: string,
    title: string,
    jobId: string | null,
    shape: Partial<ReportRun> = {},
  ): ReportRun {
    return reportRun({
      ...shape,
      id,
      status: "FAILED",
      as_of: null,
      row_count: 0,
      tie_out_results: [],
      control_totals: null,
      output: null,
      job_id: jobId,
      problem: {
        type: "internal-error",
        title,
        status: 500,
        instance: `/api/v1/report-runs/${id}`,
        errors: [],
      },
    });
  }

  function accepted(runId: string, jobId: string) {
    return HttpResponse.json(
      { id: jobId, kind: "REPORT_RUN", state: "QUEUED" },
      {
        status: 202,
        headers: { Location: `/api/v1/jobs/${jobId}`, "X-Erev-Report-Run-Id": runId },
      },
    );
  }

  it("SF-08:report: a stored failed run rendered from run= names its own job", async () => {
    const { posted } = serve(
      WATERFALL,
      {
        [SECOND_RUN_ID]: failedRun(SECOND_RUN_ID, B_TITLE, JOB_B, { report_run_no: "RPT-000398" }),
      },
      [],
    );
    renderApp(report(`&run=${SECOND_RUN_ID}`), OPTIONS);
    expect(await screen.findByText(B_TITLE)).toBeTruthy();
    expect(screen.getByText(REF_B)).toBeTruthy();
    expect(posted).toHaveLength(0);
  });

  it("SF-06:entries: a stored failed run rendered from run= names its own job", async () => {
    const { posted } = serve(
      LEGACY_JE,
      {
        [SECOND_RUN_ID]: failedRun(SECOND_RUN_ID, B_TITLE, JOB_B, {
          report: LEGACY_REPORT,
          parameters: LEGACY_PARAMETERS,
          report_run_no: "RPT-000398",
        }),
      },
      [],
    );
    renderApp(entries(`&run=${SECOND_RUN_ID}`), OPTIONS);
    expect(await screen.findByText(B_TITLE)).toBeTruthy();
    expect(screen.getByText(REF_B)).toBeTruthy();
    expect(posted).toHaveLength(0);
  });

  it("SF-08:report A to B: the stored run names its own job, never the job of A", async () => {
    const { posted } = serve(
      WATERFALL,
      {
        [RUN_ID]: failedRun(RUN_ID, A_TITLE, JOB_ID),
        [SECOND_RUN_ID]: failedRun(SECOND_RUN_ID, B_TITLE, JOB_B, { report_run_no: "RPT-000398" }),
      },
      [],
    );
    const { router } = renderApp(report(), OPTIONS);
    expect(await screen.findByText(REF_A)).toBeTruthy();
    expect(posted).toHaveLength(1);

    await router.navigate(report(`&run=${SECOND_RUN_ID}`));
    expect(await screen.findByText(B_TITLE)).toBeTruthy();
    expect(screen.getByText(REF_B)).toBeTruthy();
    expect(screen.queryByText(REF_A)).toBeNull();
    expect(posted).toHaveLength(1);
  });

  it("SF-08:report out-of-order creation answers: the late 202 of a superseded attempt is discarded", async () => {
    serve(
      WATERFALL,
      {
        [RUN_ID]: failedRun(RUN_ID, A_TITLE, JOB_ID),
        [LATE_RUN_ID]: failedRun(LATE_RUN_ID, C_TITLE, JOB_C, { report_run_no: "RPT-000399" }),
      },
      [],
    );
    let releaseFirst: () => void = () => undefined;
    const firstHeld = new Promise<void>((resolve) => {
      releaseFirst = resolve;
    });
    let posts = 0;
    let firstAnswered = false;
    server.use(
      http.post(apiUrl("/api/v1/report-runs"), async () => {
        posts += 1;
        if (posts === 1) {
          await firstHeld;
          firstAnswered = true;
          return accepted(RUN_ID, JOB_ID);
        }
        return accepted(LATE_RUN_ID, JOB_C);
      }),
      http.get(apiUrl("/api/v1/jobs/:jobId"), ({ params }) =>
        HttpResponse.json({
          id: String(params.jobId),
          kind: "REPORT_RUN",
          state: "SUCCEEDED",
          progress: null,
          started_at: "2026-09-12T16:02:11Z",
          finished_at: "2026-09-12T16:02:19Z",
          problem: null,
          result: null,
        }),
      ),
    );
    const { router } = renderApp(report(), OPTIONS);
    await waitFor(() => {
      expect(posts).toBe(1);
    });

    // The source changes while the first creation is unanswered: the second attempt supersedes the first.
    await router.navigate(report("&currency_view=functional"));
    expect(await screen.findByText(C_TITLE)).toBeTruthy();
    expect(screen.getByText(REF_C)).toBeTruthy();
    expect(runOf(router)).toBe(LATE_RUN_ID);
    expect(posts).toBe(2);

    // The first attempt answers late: its run is not shown and `run` stays on the second attempt's run.
    releaseFirst();
    await waitFor(() => {
      expect(firstAnswered).toBe(true);
    });
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(runOf(router)).toBe(LATE_RUN_ID);
    expect(screen.getByText(C_TITLE)).toBeTruthy();
    expect(screen.getByText(REF_C)).toBeTruthy();
    expect(screen.queryByText(A_TITLE)).toBeNull();
    expect(screen.queryByText(REF_A)).toBeNull();
  });

  // RPT-VIEWER-LATE-RUN-1: the view is keyed by its report, so the view of a report that gave way to
  // another report's under the same route is gone, and the late 202 of its creation is not its to
  // write. Before, the second report's address took the first report's run and parameters, and the
  // page showed that run under the second report's title.
  it("SF-08:report, one report to another: the late 202 of the first report's creation is not written onto the second report's address", async () => {
    serve(
      WATERFALL,
      {
        [RUN_ID]: failedRun(RUN_ID, A_TITLE, JOB_ID),
        [LATE_RUN_ID]: failedRun(LATE_RUN_ID, C_TITLE, JOB_C, {
          report: { code: "rpo", version: 1, name: RPO.name },
          report_run_no: "RPT-000399",
        }),
      },
      [],
    );
    let releaseFirst: () => void = () => undefined;
    const firstHeld = new Promise<void>((resolve) => {
      releaseFirst = resolve;
    });
    let firstAnswered = false;
    const posted: string[] = [];
    server.use(
      http.get(apiUrl("/api/v1/report-definitions/:code"), ({ params }) =>
        HttpResponse.json(params.code === "rpo" ? RPO : WATERFALL),
      ),
      http.post(apiUrl("/api/v1/report-runs"), async ({ request }) => {
        const { report_code: code } = (await request.json()) as { report_code: string };
        posted.push(code);
        if (code === "revenue_waterfall") {
          await firstHeld;
          firstAnswered = true;
          return accepted(RUN_ID, JOB_ID);
        }
        return accepted(LATE_RUN_ID, JOB_C);
      }),
      http.get(apiUrl("/api/v1/jobs/:jobId"), ({ params }) =>
        HttpResponse.json({
          id: String(params.jobId),
          kind: "REPORT_RUN",
          state: "SUCCEEDED",
          progress: null,
          started_at: "2026-09-12T16:02:11Z",
          finished_at: "2026-09-12T16:02:19Z",
          problem: null,
          result: null,
        }),
      ),
    );
    const { router } = renderApp(report("&p.granularity=QUARTER"), OPTIONS);
    await waitFor(() => {
      expect(posted).toEqual(["revenue_waterfall"]);
    });

    // Another report under the same route, while the first creation is unanswered.
    await router.navigate(`/reports/rpo?${CONTEXT}`);
    expect(await screen.findByText(C_TITLE)).toBeTruthy();
    expect(posted).toEqual(["revenue_waterfall", "rpo"]);
    const address = () => `${router.state.location.pathname}${router.state.location.search}`;
    const second = address();
    expect(runOf(router)).toBe(LATE_RUN_ID);

    // The first creation answers late: the second report keeps its address and its run.
    releaseFirst();
    await waitFor(() => {
      expect(firstAnswered).toBe(true);
    });
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(address()).toBe(second);
    expect(screen.getByText(C_TITLE)).toBeTruthy();
    expect(screen.queryByText(A_TITLE)).toBeNull();
  });
  // KIT-FILTER-LEAVING-2 (dev-guide DG-FE-03 rev 1.230): while a navigation to another page is on its
  // way the view is still on screen, and the 202 of its creation used to write `run` onto the page
  // being left, which cancelled the member's navigation without a word.
  it("SF-08:report: the 202 of a creation that arrives while the member is on the way to another page does not keep them", async () => {
    serve(WATERFALL, { [RUN_ID]: failedRun(RUN_ID, A_TITLE, JOB_ID) }, []);
    let answer: () => void = () => undefined;
    const answerHeld = new Promise<void>((resolve) => {
      answer = resolve;
    });
    let arrive: () => void = () => undefined;
    const fetched = new Promise<void>((resolve) => {
      arrive = resolve;
    });
    let posts = 0;
    let answered = false;
    server.use(
      http.post(apiUrl("/api/v1/report-runs"), async () => {
        posts += 1;
        await answerHeld;
        answered = true;
        return accepted(RUN_ID, JOB_ID);
      }),
    );
    const slow = {
      id: "X:slow",
      path: "/slow",
      handle: { sf: "X", screen: "X:slow", titleKey: "contracts.list.title" },
      lazy: async () => {
        await fetched;
        return { Component: () => <h1 tabIndex={-1}>The next page</h1> };
      },
    };
    const { router } = renderApp(report(), { ...OPTIONS, screenRoutes: [...SCREEN_ROUTES, slow] });
    await waitFor(() => {
      expect(posts).toBe(1);
    });
    void router.navigate("/slow");
    await waitFor(() => expect(router.state.navigation.state).toBe("loading"));

    answer();
    await waitFor(() => {
      expect(answered).toBe(true);
    });
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(router.state.navigation.location?.pathname).toBe("/slow");
    expect(runOf(router)).toBeNull();

    arrive();
    expect(await screen.findByRole("heading", { level: 1, name: "The next page" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/slow");
  });
});

// FWR-R1 (Codex `PRODUCTION-F-WEB-R-INDEPENDENT-d860d7e.md`, SHA-256 8ba5534b…124c6f; priority 2): the hook
// kept one refusal slot and wrote it whenever any `POST /report-runs` finished, so an obsolete attempt's late
// refusal replaced a newer one (H05, H08) or erased the current context's refusal (H06). Every creation
// attempt now carries an identity; a new start, a context change and "Run report" supersede earlier attempts,
// whose late answers (refusals and 202s alike) are discarded. H02 keeps the legitimately settled path: a
// settled refusal, a stored run B, then the original A shows the stored A refusal with no second POST. The
// schedules are mounted-view reproductions of Codex's hook-level cases (SF-08:report), answered in the order
// Codex names by holding each POST until the test releases it.
describe("FWR-R1 refusal ownership across overlapping creation attempts (SF-08:report)", () => {
  const OPTIONS = { me: MARCUS, screenRoutes: SCREEN_ROUTES };
  const report = (suffix = "") => `/reports/revenue_waterfall?${CONTEXT}${suffix}`;
  const OBSOLETE_A = "obsolete A attempt";
  const NEW_A = "new A attempt";
  const CURRENT_B = "current B";
  const SETTLED_A = "settled A refusal";
  const STORED_B_NO = "RPT-000398";

  function refusal(title: string) {
    return problemResponse("validation-failed", 422, title, {
      errors: [{ field: null, rule_id: "T-RPT-02", message: `${title}: finding` }],
    });
  }

  /** Every POST is held until the test releases it with an answer, so answers arrive in the order the case names. */
  function holdCreations() {
    const pending: ((response: Response) => void)[] = [];
    server.use(
      http.post(
        apiUrl("/api/v1/report-runs"),
        () =>
          new Promise<Response>((resolve) => {
            pending.push(resolve);
          }),
      ),
    );
    return {
      posts: () => pending.length,
      release: async (index: number, response: Response) => {
        const resolve = pending[index];
        if (resolve === undefined) {
          throw new Error(`no pending creation ${String(index)}`);
        }
        resolve(response);
        // The answer travels msw → fetch → useCommand → the hook before the assertions below.
        await new Promise((finish) => setTimeout(finish, 100));
      },
      settle: () => {
        for (const resolve of pending) {
          resolve(refusal("released at test end"));
        }
      },
    };
  }

  async function started(posts: () => number, count: number) {
    await waitFor(() => {
      expect(posts()).toBe(count);
    });
  }

  it("H05: A0 pending, context A→B→A starts B1 and A2; A2 refuses, then A0 refuses late — the new A attempt stays", async () => {
    serve(WATERFALL, {}, []);
    const held = holdCreations();
    const { router } = renderApp(report(), OPTIONS);
    await started(held.posts, 1);
    await router.navigate(report("&currency_view=functional"));
    await started(held.posts, 2);
    await router.navigate(report());
    await started(held.posts, 3);

    await held.release(2, refusal(NEW_A));
    expect(await screen.findByText(NEW_A)).toBeTruthy();

    await held.release(0, refusal(OBSOLETE_A));
    // The obsolete answer must not surface (asserted first, so a failure names the obsolete banner).
    expect(screen.queryByText(OBSOLETE_A)).toBeNull();
    expect(screen.getByText(NEW_A)).toBeTruthy();
    expect(held.posts()).toBe(3);
    held.settle();
  });

  it("H06: A0 pending, context A→B starts B1; B1 refuses, then A0 refuses late — the current B refusal stays", async () => {
    serve(WATERFALL, {}, []);
    const held = holdCreations();
    const { router } = renderApp(report(), OPTIONS);
    await started(held.posts, 1);
    await router.navigate(report("&currency_view=functional"));
    await started(held.posts, 2);

    await held.release(1, refusal(CURRENT_B));
    expect(await screen.findByText(CURRENT_B)).toBeTruthy();

    await held.release(0, refusal(OBSOLETE_A));
    // The current B refusal must survive the obsolete A answer (asserted first, so a failure shows the loss).
    expect(screen.getByText(CURRENT_B)).toBeTruthy();
    expect(screen.queryByText(OBSOLETE_A)).toBeNull();
    expect(held.posts()).toBe(2);
  });

  it("H08: A0 pending, parameters only A→B→A start B1 and A2; A2 refuses, then A0 refuses late — the new A attempt stays", async () => {
    serve(WATERFALL, {}, []);
    const held = holdCreations();
    const { router } = renderApp(report(), OPTIONS);
    await started(held.posts, 1);
    await router.navigate(report("&p.row_dimension=OBLIGATION"));
    await started(held.posts, 2);
    await router.navigate(report());
    await started(held.posts, 3);

    await held.release(2, refusal(NEW_A));
    expect(await screen.findByText(NEW_A)).toBeTruthy();

    await held.release(0, refusal(OBSOLETE_A));
    // The obsolete answer must not surface (asserted first, so a failure names the obsolete banner).
    expect(screen.queryByText(OBSOLETE_A)).toBeNull();
    expect(screen.getByText(NEW_A)).toBeTruthy();
    expect(held.posts()).toBe(3);
    held.settle();
  });

  it("H02: a settled A refusal, stored run B, then the original A shows the stored A refusal with no second POST", async () => {
    serve(
      WATERFALL,
      { [SECOND_RUN_ID]: reportRun({ id: SECOND_RUN_ID, report_run_no: STORED_B_NO }) },
      WATERFALL_ROWS,
    );
    const held = holdCreations();
    const { router } = renderApp(report(), OPTIONS);
    await started(held.posts, 1);
    await held.release(0, refusal(SETTLED_A));
    expect(await screen.findByText(SETTLED_A)).toBeTruthy();

    await router.navigate(report(`&run=${SECOND_RUN_ID}`));
    expect(await screen.findByTestId("SF-08-row-sf-ord-10001")).toBeTruthy();
    expect(screen.queryByText(SETTLED_A)).toBeNull();

    await router.navigate(report());
    expect(await screen.findByText(SETTLED_A)).toBeTruthy();
    expect(held.posts()).toBe(1);
  });
});
