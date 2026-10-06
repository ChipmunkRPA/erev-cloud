// @vitest-environment jsdom
// SF-08:runs and SF-08:run (BUILD_SPEC RPS-18; SCREENS_B §5.3, §0.5 RV-03, RV-05, RV-14; SCREENS §0.3
// SCR-IA-02, §0.4 RT-106, RT-33, §0.6 SCR-PERM-01, §0.7 SCR-ST-07; 04 API-R-41 rev 1.128; REQ-RPT-002;
// CTL-029): the register lists the runs the API answers with their IPE fields and sends the route's four
// filters; it opens for `report.run` or `audit.read`; the run record shows the parameters, the control
// totals, the tie-outs, the output and the ledger heads; "Rerun from the same source" follows its job and
// opens the new run with "Output identical" and "Control totals identical"; a failed run says why; a run
// stored before source binding cannot be rerun.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../../app/router";
import type { ReportRun } from "../../../lib/api/queries/reports";
import { installMemoryStorage, preloadScreens, renderApp, signedInMe } from "../../../test/app";
import { AS_LOCKED, rerunRefusal } from "../../../test/as-locked";
import { narrowColumns } from "../../../test/grid-headers";
import { installGridViewport } from "../../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import { knownAtBasis, recorded, rerunOffer, sourcesText } from "../run";
import { reportViewHref } from "../run-links";
import { reportRunColumns } from "../runs";

installMswServer();
installMemoryStorage();
installGridViewport();

beforeAll(async () => {
  await preloadScreens(SCREEN_ROUTES, ["SF-08:runs", "SF-08:run"]);
});

afterEach(() => {
  cleanup();
});

const MARCUS_ID = "7d6c5b4a-3f2e-4d1c-8b0a-9f8e7d6c5b4a";
const MARCUS = signedInMe({
  user: {
    id: MARCUS_ID,
    email: "marcus@example.test",
    display_name: "Marcus Webb",
    status: "ACTIVE",
  },
  permissions: ["contract.read", "report.run", "report.export"],
});

const RUN_ID = "5b0c7a1e-3d2f-4e6a-9b8c-7d6e5f4a3b2c";
const RERUN_ID = "6c1d8b2f-4e3a-4f7b-8c9d-8e7f6a5b4c3d";
const FILE_RUN_ID = "7d2e9c3a-5f4b-4a8c-9d0e-9f8a7b6c5d4e";
const FAILED_RUN_ID = "8e3f0d4b-6a5c-4b9d-8e1f-0a9b8c7d6e5f";
const JOB_ID = "8e7d6c5b-4a3f-4e2d-9c1b-0a9f8e7d6c5b";
const LOCK_ID = "8b10c4d2-6e1f-4a3b-9c8d-7e6f5a4baa42";
const SHA = `5c1e7a90${"f".repeat(52)}04b2`;
const SEAL = `9d21e4f0${"a".repeat(52)}7c0e`;
const AVM_US = {
  id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000001",
  code: "AVM-US",
  name: "Avenmoor US Inc.",
};

function money(amount: string, currency = "USD") {
  return { amount, currency };
}

/** PRD J-15.6: the RPO run of AVM-US as locked, exported as a workbook. */
function reportRun(overrides: Partial<ReportRun> = {}): ReportRun {
  return {
    id: RUN_ID,
    report_run_no: "RPT-000412",
    report: { code: "rpo", version: 1, name: "Remaining performance obligations" },
    status: "SUCCEEDED",
    parameters: {
      entity_codes: ["AVM-US"],
      book: "ASC606",
      period_key: "FY2026-P09",
      as_of: "2026-09-30",
      period_lock_id: LOCK_ID,
      time_bands: [12, 24],
      known_at: "2026-10-01T09:14:02Z",
      known_at_basis: "historical",
    },
    entity_scope: [AVM_US],
    book: "ASC606",
    as_of: "2026-09-30",
    known_at: "2026-10-01T09:14:02Z",
    period_lock_id: LOCK_ID,
    engine_release: {
      engine_version: "1.0.0",
      build_sha: "3f9a1c22e41b7d0c5a6f8e9d0b1c2a3f4e5d6c7b",
    },
    row_count: 211,
    control_totals: { row_count: 211, total_rpo: { USD: "1234567.00" } },
    tie_out_results: [
      {
        code: "TO_RPO_ROLLFORWARD_EQ_RPO",
        result: "PASS",
        expected: [money("1234567.00")],
        actual: [money("1234567.00")],
        difference: [money("0.00")],
      },
    ],
    ledger_heads: { ASC606: { chain_seq: 1388, seal_sha256: SEAL } },
    sources: {
      bound: false,
      kind: "as_locked",
      strategy: null,
      cutoff: null,
      versions: 0,
      labels: 0,
      members: 0,
      rows: 0,
      open: [],
    },
    output: {
      file_id: "6a5b4c3d-2e1f-4a0b-9c8d-7e6f5a4b3c2d",
      format: "XLSX",
      sha256: SHA,
      href: `/api/v1/report-runs/${RUN_ID}/output`,
      manifest_href: "/api/v1/files/7b6c5d4e-3f2a-4b1c-8d0e-9f8a7b6c5d4e/content",
    },
    problem: null,
    job_id: JOB_ID,
    run_by: { id: MARCUS_ID, display_name: "Marcus Webb", kind: "USER" },
    started_at: "2026-09-12T16:02:11Z",
    finished_at: "2026-09-12T16:02:19Z",
    ...overrides,
  };
}

/** A view run of the waterfall: JSON, current figures, a source bound at its cutoff. */
const VIEW_RUN = reportRun({
  id: FILE_RUN_ID,
  report_run_no: "RPT-000410",
  report: { code: "revenue_waterfall", version: 2, name: "Revenue waterfall" },
  parameters: {
    entity_codes: ["AVM-US"],
    book: "ASC606",
    from_period_key: "FY2026-P01",
    to_period_key: "FY2026-P12",
    granularity: "MONTH",
    known_at: "2026-09-12T15:40:00Z",
    known_at_basis: "record",
  },
  as_of: null,
  known_at: "2026-09-12T15:40:00Z",
  period_lock_id: null,
  row_count: 18,
  control_totals: { recognized_total: { USD: "9764.38" } },
  tie_out_results: [],
  sources: {
    bound: true,
    kind: "bound",
    strategy: "adapter",
    cutoff: "2026-09-12T15:40:00Z",
    versions: 18,
    labels: 3,
    members: 2,
    rows: 18,
    open: [],
  },
  output: {
    file_id: "5a4b3c2d-1e0f-4a9b-8c7d-6e5f4a3b2c1d",
    format: "JSON",
    sha256: `1a2b3c4d${"0".repeat(52)}9f8e`,
    href: `/api/v1/report-runs/${FILE_RUN_ID}/output`,
    manifest_href: null,
  },
  started_at: "2026-09-12T15:40:01Z",
  finished_at: "2026-09-12T15:40:03Z",
});

/** A run that failed before its source was captured. */
const FAILED_RUN = reportRun({
  id: FAILED_RUN_ID,
  report_run_no: "RPT-000409",
  status: "FAILED",
  row_count: null,
  control_totals: null,
  tie_out_results: [],
  ledger_heads: {},
  sources: {
    bound: false,
    kind: "failed_without_capture",
    strategy: "adapter",
    cutoff: null,
    versions: 0,
    labels: 0,
    members: 0,
    rows: 0,
    open: [],
  },
  output: null,
  problem: {
    type: "https://erev.example/problems/validation-failed",
    title: "The period lock holds no RPO dataset",
    status: 422,
    detail: "Run the report on current figures, or lock the period again.",
    instance: `/api/v1/report-runs/${FAILED_RUN_ID}`,
    errors: [],
  },
  started_at: "2026-09-12T15:30:00Z",
  finished_at: "2026-09-12T15:30:02Z",
});

const DEFINITIONS = [
  { code: "rpo", name: "Remaining performance obligations" },
  { code: "revenue_waterfall", name: "Revenue waterfall" },
].map((item) => ({
  ...item,
  version: 1,
  kind: "STANDARD",
  description: "",
  parameters_schema: { type: "object", additionalProperties: false, properties: {} },
  output_formats: ["JSON", "XLSX"],
  tie_outs: [],
  ipe_logic: null,
}));

function list(items: readonly unknown[], request?: Request) {
  const counting =
    request !== undefined && new URL(request.url).searchParams.get("count") === "true";
  return HttpResponse.json(
    { items, next_cursor: null },
    { headers: counting ? { "X-Erev-Total-Count": String(items.length) } : {} },
  );
}

function job(state: "QUEUED" | "SUCCEEDED", result: Record<string, unknown> | null = null) {
  return {
    id: JOB_ID,
    kind: "REPORT_RUN",
    state,
    mode: null,
    progress: { done: state === "SUCCEEDED" ? 211 : 0, total: null },
    result,
    problem: null,
    created_by: { id: MARCUS_ID, kind: "USER", display_name: "Marcus Webb" },
    created_at: "2026-09-12T16:10:00Z",
    started_at: state === "QUEUED" ? null : "2026-09-12T16:10:01Z",
    finished_at: state === "SUCCEEDED" ? "2026-09-12T16:10:04Z" : null,
  };
}

interface Served {
  /** The searches of `GET /report-runs`, without the paging parameters. */
  readonly lists: string[];
  /** The Idempotency-Key of every `POST /report-runs/{id}/rerun`, by run id. */
  readonly reruns: [string, string][];
}

/** The shell's reads and the reads of both screens over `runs`. */
function serve(runs: readonly ReportRun[] = [reportRun(), VIEW_RUN, FAILED_RUN]): Served {
  const served: Served = { lists: [], reruns: [] };
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () => list([])),
    http.get(apiUrl("/api/v1/entities"), () => list([])),
    http.get(apiUrl("/api/v1/books"), () => list([])),
    http.get(apiUrl("/api/v1/periods"), () => list([])),
    http.get(apiUrl("/api/v1/saved-views"), () => list([])),
    http.get(apiUrl("/api/v1/currencies"), () =>
      list([
        { code: "USD", name: "US dollar", minor_unit: 2, numeric_code: "840", is_active: true },
      ]),
    ),
    http.get(apiUrl("/api/v1/report-definitions"), () => list(DEFINITIONS)),
    http.get(apiUrl("/api/v1/report-runs"), ({ request }) => {
      const params = new URL(request.url).searchParams;
      for (const name of ["limit", "cursor", "count"]) {
        params.delete(name);
      }
      served.lists.push(params.toString());
      return list(runs, request);
    }),
    http.get(apiUrl("/api/v1/report-runs/:runId"), ({ params }) => {
      const found = runs.find((run) => run.id === params.runId);
      return found === undefined
        ? problemResponse("not-found", 404, "Report run not found")
        : HttpResponse.json(found);
    }),
    http.post(apiUrl("/api/v1/report-runs/:runId/rerun"), ({ request, params }) => {
      served.reruns.push([String(params.runId), request.headers.get("Idempotency-Key") ?? ""]);
      return HttpResponse.json(job("QUEUED"), {
        status: 202,
        headers: { Location: `/api/v1/jobs/${JOB_ID}`, "X-Erev-Report-Run-Id": RERUN_ID },
      });
    }),
  );
  return served;
}

function open(entry: string, me = MARCUS) {
  return renderApp(entry, { me, screenRoutes: SCREEN_ROUTES });
}

async function grid(): Promise<HTMLElement> {
  return within(await screen.findByTestId("SF-08-grid-runs")).findByRole("grid", {
    name: "Report runs",
  });
}

function cells(row: HTMLElement): (string | null)[] {
  return Array.from(row.querySelectorAll("[role='rowheader'], [role='gridcell']"), (cell) =>
    cell.textContent.replaceAll("\u00a0", " "),
  );
}

/** The names and values of a record table, in row order. */
function pairs(table: HTMLElement): (string | null)[][] {
  return within(table)
    .getAllByRole("row")
    .map((row) => Array.from(row.querySelectorAll("th, td"), (cell) => cell.textContent));
}

describe("SF-08:runs", () => {
  it("the register lists every run with its REQ-RPT-002 fields", async () => {
    const served = serve();
    open("/reports/runs");
    const runs = await grid();
    expect(
      within(runs)
        .getAllByRole("columnheader")
        .map((header) => header.textContent.replace(/Column options: .*$/, "")),
    ).toEqual([
      "Run",
      "Report",
      "Status",
      "Entity",
      "Book",
      "As of",
      "Source",
      "Format",
      "Rows",
      "Output SHA-256",
      "Run by",
      "Started",
      "Finished",
    ]);
    const locked = await screen.findByTestId("SF-08-row-rpt-000412");
    expect(cells(locked)).toEqual([
      "RPT-000412",
      "Remaining performance obligations v1",
      "Succeeded",
      "AVM-US",
      "ASC 606",
      "30 Sep 2026",
      "As locked",
      "XLSX",
      "211",
      // The prefix, the whole hash for assistive technology and the name of the copy button.
      `5c1e7a90…04b2${SHA}Copy output SHA-256`,
      "Marcus Webb",
      "12 Sep 2026 16:02 UTC",
      "12 Sep 2026 16:02 UTC",
    ]);
    // The run number opens the run record; the hash is copied whole.
    expect(within(locked).getByRole("link", { name: "RPT-000412" }).getAttribute("href")).toBe(
      `/reports/runs/${RUN_ID}`,
    );
    expect(within(locked).getByRole("button", { name: "Copy output SHA-256" })).toBeTruthy();
    // A current run of a view, and a failed run without output, rows or an as-of date of its own.
    expect(cells(screen.getByTestId("SF-08-row-rpt-000410")).slice(4, 9)).toEqual([
      "ASC 606",
      "—No value",
      "Current",
      "JSON",
      "18",
    ]);
    const failed = cells(screen.getByTestId("SF-08-row-rpt-000409"));
    expect(failed[2]).toBe("Failed");
    expect(failed.slice(7, 10)).toEqual(["—No value", "—No value", "—No value"]);
    expect(screen.getByText("3 runs")).toBeTruthy();

    // The list is read once, unfiltered and in the API's order: no sort is sent and no column sorts.
    expect(served.lists).toEqual([""]);
    expect(within(runs).queryAllByRole("columnheader", { name: /sort/i })).toEqual([]);
    for (const header of within(runs).getAllByRole("columnheader")) {
      expect(header.getAttribute("aria-sort")).toBeNull();
    }

    // SCR-IA-02: the Reports tabs of the built pages the member may read.
    const tabs = screen.getByRole("navigation", { name: "Reports sections" });
    expect(
      within(tabs)
        .getAllByRole("link")
        .map((tab) => [tab.textContent, tab.getAttribute("aria-current")]),
    ).toEqual([
      ["Catalogue", null],
      ["Report runs", "page"],
    ]);
  });

  it("the Report cell opens the report view of the run", async () => {
    serve();
    open("/reports/runs");
    await grid();
    // A JSON run is rendered from the stored run; its parameters ride along for the toolbar.
    const view = within(await screen.findByTestId("SF-08-row-rpt-000410")).getByRole("link", {
      name: "Revenue waterfall v2",
    });
    expect(view.getAttribute("href")).toBe(
      `/reports/revenue_waterfall?entity=AVM-US&book=ASC606&run=${FILE_RUN_ID}&p.from_period_key=FY2026-P01&p.to_period_key=FY2026-P12&p.granularity=MONTH`,
    );
    // A file run opens the view on the same parameters, which runs it on screen.
    const file = within(screen.getByTestId("SF-08-row-rpt-000412")).getByRole("link", {
      name: "Remaining performance obligations v1",
    });
    expect(file.getAttribute("href")).toBe(
      `/reports/rpo?entity=AVM-US&period=FY2026-P09&book=ASC606&known_at=2026-10-01T09%3A14%3A02Z&snapshot=${LOCK_ID}&p.as_of=2026-09-30&p.time_bands=12%2C24`,
    );
  });

  it("the chips reach the API as the route's four filters", async () => {
    const served = serve();
    open(
      "/reports/runs?f.report_code=in:rpo,revenue_waterfall&f.status=is:SUCCEEDED&f.created_from=gte:2026-09-01&f.created_to=lte:2026-09-12",
    );
    await grid();
    await waitFor(() => expect(served.lists.length).toBeGreaterThan(0));
    // Whole days of platform time: from 00:00:00Z of the first day to 00:00:00Z after the last.
    expect(served.lists.at(-1)).toBe(
      "report_code=rpo&report_code=revenue_waterfall&status=SUCCEEDED&created_from=2026-09-01T00%3A00%3A00Z&created_to=2026-09-13T00%3A00%3A00Z",
    );
    const bar = screen.getByTestId("SF-08-filter-bar");
    for (const chip of [
      "Report is Remaining performance obligations or Revenue waterfall",
      "Status is Succeeded",
      "Created from on or after 01 Sep 2026",
      "Created to on or before 12 Sep 2026",
    ]) {
      expect(await within(bar).findByRole("button", { name: `${chip}, edit filter` })).toBeTruthy();
    }
    // The route has no search.
    expect(within(bar).queryByRole("searchbox")).toBeNull();
  });

  it("an empty register says what belongs here", async () => {
    serve([]);
    open("/reports/runs");
    expect(await screen.findByRole("heading", { name: "No report runs yet" })).toBeTruthy();
    expect(
      screen.getByText("Every report view, export and pack creates a run record here."),
    ).toBeTruthy();
  });

  it("audit.read opens the register without report.run; neither is access-limited", async () => {
    const served = serve([reportRun()]);
    open("/reports/runs", signedInMe({ permissions: ["audit.read"] }));
    await grid();
    expect(await screen.findByTestId("SF-08-row-rpt-000412")).toBeTruthy();
    expect(served.lists).toEqual([""]);
    const tabs = screen.getByRole("navigation", { name: "Reports sections" });
    expect(
      within(tabs)
        .getAllByRole("link")
        .map((tab) => tab.textContent),
    ).toEqual(["Report runs", "Audit log"]);
    cleanup();

    const closed = serve([reportRun()]);
    open("/reports/runs", signedInMe({ permissions: ["contract.read"] }));
    expect(
      await screen.findByRole("heading", { name: "You do not have access to report runs" }),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Ask a workspace administrator for a role that includes running reports or viewing the audit log.",
      ),
    ).toBeTruthy();
    expect(closed.lists).toEqual([]);
  });
});

describe("SF-08:run", () => {
  it("the record shows the run with its parameters, totals, tie-outs, output and ledger heads", async () => {
    serve();
    open(`/reports/runs/${RUN_ID}`);
    expect(
      await screen.findByRole("heading", { level: 1, name: "Report run RPT-000412" }),
    ).toBeTruthy();
    const record = screen.getByRole("region", { name: "Report run RPT-000412" });
    expect(within(record).getByText("Succeeded")).toBeTruthy();
    const crumbs = within(screen.getByRole("navigation", { name: "Breadcrumb" })).getAllByRole(
      "link",
    );
    expect(crumbs.map((crumb) => [crumb.textContent, crumb.getAttribute("href")])).toEqual([
      ["Reports", "/reports"],
      ["Report runs", "/reports/runs"],
    ]);
    const meta = Array.from(record.querySelectorAll("dt"), (term) => [
      term.textContent,
      term.nextElementSibling?.textContent,
    ]);
    expect(meta).toEqual([
      ["Report", "Remaining performance obligations v1"],
      ["Entity", "AVM-US"],
      ["Book", "ASC 606"],
      ["As of", "30 Sep 2026"],
      ["Source", "As locked (lock 8b10c4d2…aa42)"],
      ["Engine", "1.0.0 (build 3f9a1c22)"],
      ["Run by", "Marcus Webb"],
      ["Started", "12 Sep 2026 16:02:11 UTC"],
      ["Finished", "12 Sep 2026 16:02:19 UTC"],
    ]);

    // Every key the run stored, defaults included, as recorded.
    const parameters = screen.getByRole("table", { name: "Parameters" });
    expect(screen.getByTestId("SF-08-grid-run-parameters")).toBe(parameters);
    expect(pairs(parameters)).toEqual([
      ["entity_codes", "AVM-US"],
      ["book", "ASC606"],
      ["period_key", "FY2026-P09"],
      ["as_of", "2026-09-30"],
      ["period_lock_id", LOCK_ID],
      ["time_bands", "12, 24"],
      ["known_at", "2026-10-01T09:14:02Z"],
      ["known_at_basis", "historical"],
    ]);
    const totals = screen.getByRole("table", { name: "Control totals" });
    expect(screen.getByTestId("SF-08-grid-run-control-totals")).toBe(totals);
    expect(pairs(totals).map((row) => row.map((cell) => cell?.replaceAll("\u00a0", " ")))).toEqual([
      ["row_count", "211"],
      ["total_rpo", "USD 1,234,567.00"],
    ]);
    // RV-05: the tie-out strip of the report view.
    const tieOuts = screen.getByTestId("SF-08-banner-tie-outs");
    expect(
      within(tieOuts).getByRole("heading", { name: "Tie-outs (1 pass, 0 fail)" }),
    ).toBeTruthy();
    const output = pairs(screen.getByRole("table", { name: "Output" }));
    expect(output.map(([name]) => name)).toEqual(["Format", "Output SHA-256", "Manifest", "Rows"]);
    expect(output[0]?.[1]).toBe("XLSX");
    expect(output[1]?.[1]).toBe(`5c1e7a90…04b2${SHA}Copy output SHA-256`);
    expect(output[3]?.[1]).toBe("211");
    const manifest = screen.getByRole("link", { name: "Download manifest" });
    expect(manifest.getAttribute("href")).toBe(
      "/api/v1/files/7b6c5d4e-3f2a-4b1c-8d0e-9f8a7b6c5d4e/content",
    );
    expect(pairs(screen.getByRole("table", { name: "Ledger heads" }))).toEqual([
      ["ASC 606", `chain 1,388seal9d21e4f0…7c0e${SEAL}Copy seal`],
    ]);
    const source = pairs(screen.getByRole("table", { name: "Source" }));
    expect(source[1]).toEqual(["Known at", "01 Oct 2026 09:14:02 UTCAs of the supplied cutoff"]);
    expect(source[2]).toEqual(["Sources", "Frozen dataset (as locked)"]);

    // The wireframe's two columns: the parameters, with the run's source under them, then the figures.
    const columns = Array.from(parameters.parentElement?.parentElement?.children ?? [], (column) =>
      Array.from(column.querySelectorAll("table, [data-testid='SF-08-banner-tie-outs']"), (block) =>
        block.getAttribute("data-testid"),
      ),
    );
    expect(columns).toEqual([
      ["SF-08-grid-run-parameters", "SF-08-grid-run-source"],
      [
        "SF-08-grid-run-control-totals",
        "SF-08-banner-tie-outs",
        "SF-08-grid-run-output",
        "SF-08-grid-run-ledger-heads",
      ],
    ]);
    // A long recorded value wraps inside its table: the two columns of a table are fixed.
    for (const table of screen.getAllByRole("table")) {
      expect(table.className).toContain("table-fixed");
    }
    // What differs from one world to the next is marked for the captures (SCR-TID-05): an instant
    // and a system id among the parameters, and the ledger's chain sequence.
    const volatile = (table: HTMLElement, text: string) =>
      within(table).getByText(text).closest("[data-volatile]") !== null;
    expect(volatile(parameters, "2026-10-01T09:14:02Z")).toBe(true);
    expect(volatile(parameters, LOCK_ID)).toBe(true);
    expect(volatile(parameters, "FY2026-P09")).toBe(false);
    expect(volatile(parameters, "2026-09-30")).toBe(false);
    expect(volatile(screen.getByRole("table", { name: "Ledger heads" }), "chain 1,388")).toBe(true);

    // The actions: the report view on the same parameters, the output, the rerun.
    expect(screen.getByRole("link", { name: "Open report view" }).getAttribute("href")).toBe(
      `/reports/rpo?entity=AVM-US&period=FY2026-P09&book=ASC606&known_at=2026-10-01T09%3A14%3A02Z&snapshot=${LOCK_ID}&p.as_of=2026-09-30&p.time_bands=12%2C24`,
    );
    const download = screen.getByRole("link", { name: "Download XLSX" });
    expect(download.getAttribute("href")).toBe(`/api/v1/report-runs/${RUN_ID}/output`);
    expect(download.hasAttribute("download")).toBe(true);
    expect(screen.getByRole("button", { name: "Rerun from the same source" })).toBeTruthy();
    expect(screen.queryByTestId("SF-08-banner-rerun-result")).toBeNull();
  });

  it.each([
    [true, true, "Output identical: Yes", "Control totals identical: Yes", "positive"],
    [false, true, "Output identical: No", "Control totals identical: Yes", "warning"],
  ])(
    "Rerun from the same source opens the new run with the result lines (output %s, totals %s)",
    async (outputEqual, totalsEqual, outputLine, totalsLine, tone) => {
      let finish: (() => void) | undefined;
      const running = new Promise<void>((resolve) => {
        finish = resolve;
      });
      const rerunOf = reportRun({ id: RERUN_ID, report_run_no: "RPT-000413" });
      const served = serve([reportRun(), rerunOf]);
      server.use(
        http.get(apiUrl("/api/v1/jobs/:jobId"), async () => {
          await running;
          return HttpResponse.json(
            job("SUCCEEDED", {
              href: `/api/v1/report-runs/${RERUN_ID}`,
              counts: { rows: 211 },
              report_run_id: RERUN_ID,
              rerun_of: RUN_ID,
              output_sha256_equal: outputEqual,
              control_totals_equal: totalsEqual,
            }),
          );
        }),
      );
      const { router } = open(`/reports/runs/${RUN_ID}`);
      fireEvent.click(await screen.findByRole("button", { name: "Rerun from the same source" }));
      // DS-CMP-24: the job shows on the record while it runs; one command, one key.
      expect(
        await screen.findByRole("progressbar", {
          name: "Running Remaining performance obligations",
        }),
      ).toBeTruthy();
      expect(served.reruns).toHaveLength(1);
      expect(served.reruns[0]?.[0]).toBe(RUN_ID);
      expect(served.reruns[0]?.[1]).toMatch(/^[0-9a-f-]{36}$/);

      finish?.();
      // RV-03: the new run's record, named by the job result, with the two result lines.
      await waitFor(() => expect(router.state.location.pathname).toBe(`/reports/runs/${RERUN_ID}`));
      expect(
        await screen.findByRole("heading", { level: 1, name: "Report run RPT-000413" }),
      ).toBeTruthy();
      const result = await screen.findByTestId("SF-08-banner-rerun-result");
      const status = within(result).getByRole("status");
      expect(status.getAttribute("data-tone")).toBe(tone);
      expect(within(status).getByRole("heading", { name: "Rerun of RPT-000412" })).toBeTruthy();
      expect(within(status).getByText(outputLine)).toBeTruthy();
      expect(within(status).getByText(totalsLine)).toBeTruthy();
      expect(
        within(status).getByRole("link", { name: "Open RPT-000412" }).getAttribute("href"),
      ).toBe(`/reports/runs/${RUN_ID}`);
      // The new record offers its own rerun; the job of the first is gone with its page.
      expect(screen.getByRole("button", { name: "Rerun from the same source" })).toBeTruthy();
      expect(screen.queryByRole("progressbar")).toBeNull();
    },
  );

  // 04 API-R-11: a job is read by its owner or by a holder of `audit.read`.
  const COMPUTING = reportRun({
    status: "RUNNING",
    row_count: null,
    control_totals: null,
    tie_out_results: [],
    ledger_heads: {},
    output: null,
    finished_at: null,
  });
  const OTHER_READER = {
    id: "9f8e7d6c-5b4a-4c3d-8e2f-1a0b9c8d7e6f",
    email: "robert@example.test",
    display_name: "Robert Adeyemi",
    status: "ACTIVE",
  } as const;

  it.each([
    ["its starter", MARCUS],
    [
      "a holder of audit.read who did not start it",
      signedInMe({ user: OTHER_READER, permissions: ["report.run", "audit.read"] }),
    ],
  ])("a computing run shows the progress of its job to %s", async (_reader, me) => {
    serve([COMPUTING]);
    const jobs: string[] = [];
    server.use(
      http.get(apiUrl("/api/v1/jobs/:jobId"), ({ params }) => {
        jobs.push(String(params.jobId));
        return HttpResponse.json({
          ...job("QUEUED"),
          state: "RUNNING",
          progress: { done: 40, total: 211 },
          started_at: "2026-09-12T16:02:11Z",
        });
      }),
    );
    open(`/reports/runs/${RUN_ID}`, me);
    expect(
      await screen.findByRole("progressbar", { name: "Running Remaining performance obligations" }),
    ).toBeTruthy();
    expect(jobs[0]).toBe(JOB_ID);
    // The rerun waits for the run to end.
    expect(screen.queryByRole("button", { name: /^Rerun/ })).toBeNull();
  });

  it("another reader of a computing run sees it running, and its job is not asked for", async () => {
    // A member who may run reports, did not start this run and holds no `audit.read`: the API would
    // answer the job 404, so the record does not ask and reads the run again until it ends.
    let ended = false;
    const jobs: string[] = [];
    server.use(
      http.get(apiUrl("/api/v1/jobs/:jobId"), ({ params }) => {
        jobs.push(String(params.jobId));
        return problemResponse("not-found", 404, "Not found");
      }),
    );
    serve([COMPUTING]);
    server.use(
      http.get(apiUrl("/api/v1/report-runs/:runId"), () =>
        HttpResponse.json(ended ? reportRun() : COMPUTING),
      ),
    );
    open(
      `/reports/runs/${RUN_ID}`,
      signedInMe({ user: OTHER_READER, permissions: ["report.run"] }),
    );
    const line = await screen.findByText("Running Remaining performance obligations");
    expect(line.getAttribute("role")).toBe("status");
    expect(screen.queryByRole("progressbar")).toBeNull();
    ended = true;
    // The run is read again on the job's interval; its end shows without the job.
    expect(
      await screen.findByRole("button", { name: "Rerun from the same source" }, { timeout: 4_000 }),
    ).toBeTruthy();
    expect(screen.queryByText("Running Remaining performance obligations")).toBeNull();
    expect(jobs).toEqual([]);
  });

  // SCREENS §0.6 SCR-PERM-02 (c) (rev 1.34; item W-12, slice c; supervisor ruling R-28): the jobs of
  // other members are a list of the whole workspace, read with `audit.read` for all entities. A holder
  // for named entities who did not start the run is another reader of it.
  it("a holder of audit.read for named entities who did not start a computing run does not ask for its job", async () => {
    const jobs: string[] = [];
    server.use(
      http.get(apiUrl("/api/v1/jobs/:jobId"), ({ params }) => {
        jobs.push(String(params.jobId));
        return problemResponse("not-found", 404, "Not found");
      }),
    );
    serve([COMPUTING]);
    open(
      `/reports/runs/${RUN_ID}`,
      signedInMe({
        user: OTHER_READER,
        permissions: ["report.run", "audit.read"],
        permission_scopes: {
          "report.run": ["0a1b2c3d-4e5f-4a6b-8c7d-000000000003"],
          "audit.read": ["0a1b2c3d-4e5f-4a6b-8c7d-000000000003"],
        },
      }),
    );
    const line = await screen.findByText("Running Remaining performance obligations");
    expect(line.getAttribute("role")).toBe("status");
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(jobs).toEqual([]);
  });

  it("a failed run says why, exports nothing and reruns as a new evaluation", async () => {
    serve();
    open(`/reports/runs/${FAILED_RUN_ID}`);
    const banner = await screen.findByTestId("SF-08-banner-run-failed");
    expect(
      within(banner).getByRole("heading", {
        name: "The run failed: The period lock holds no RPO dataset. Nothing was exported.",
      }),
    ).toBeTruthy();
    expect(
      within(banner).getByText("Run the report on current figures, or lock the period again."),
    ).toBeTruthy();
    // RV-14: the reference of the run's own job. DS-CMP-29: present on load, so not an alert.
    expect(within(banner).getByText(`Reference ${JOB_ID.slice(0, 8)}.`)).toBeTruthy();
    expect(within(banner).queryByRole("alert")).toBeNull();
    expect(screen.getByText("Failed")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /^Download / })).toBeNull();
    expect(pairs(screen.getByRole("table", { name: "Control totals" }))).toEqual([
      ["No control totals recorded."],
    ]);
    expect(pairs(screen.getByRole("table", { name: "Output" }))).toEqual([["No output recorded."]]);
    expect(pairs(screen.getByRole("table", { name: "Source" }))[2]).toEqual([
      "Sources",
      "Failed before capture — a rerun is a new evaluation",
    ]);
    expect(screen.getByRole("button", { name: "Rerun (new evaluation)" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Rerun from the same source" })).toBeNull();
  });

  it("a run stored before source binding cannot be rerun", async () => {
    const served = serve([
      reportRun({
        period_lock_id: null,
        sources: {
          bound: false,
          kind: "legacy_unbound",
          strategy: "adapter",
          cutoff: null,
          versions: 0,
          labels: 0,
          members: 0,
          rows: 0,
          open: [],
        },
      }),
    ]);
    open(`/reports/runs/${RUN_ID}`);
    const rerun = await screen.findByRole("button", { name: "Rerun from the same source" });
    expect(rerun.getAttribute("aria-disabled")).toBe("true");
    expect(rerun.getAttribute("aria-describedby")).not.toBeNull();
    fireEvent.click(rerun);
    expect(served.reruns).toEqual([]);
    expect(
      screen.getAllByText(
        "Unbound (created before source binding) — rerun and cell explanation unavailable",
      ).length,
    ).toBeGreaterThan(0);
  });

  it("a refused rerun says the refusal's detail: PRD ERR-97 for a run of before the rule", async () => {
    // 04 T-RPT-01 rule 6: the refusal's sentence is the problem's detail as well as the message of
    // its one error, so the record, which prints a refused rerun's title and detail, says it.
    const sentence =
      "The entities of this run keep different fiscal calendars, so a period key can name different " +
      "months for them. Run the report for entities of one calendar.";
    serve();
    server.use(
      http.post(apiUrl("/api/v1/report-runs/:runId/rerun"), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
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
        }),
      ),
    );
    open(`/reports/runs/${RUN_ID}`);
    fireEvent.click(await screen.findByRole("button", { name: "Rerun from the same source" }));
    expect(
      await screen.findByRole("heading", { name: "Check the highlighted fields" }),
    ).toBeTruthy();
    expect(screen.getAllByText(sentence)).toHaveLength(1);
    expect(screen.queryByTestId("SF-08-banner-rerun-result")).toBeNull();
  });

  it("a refused rerun says the sentence of its finding: the lock to pass, for a run that names the permanent lock's record", async () => {
    // S15-R-19 rev 1.167 (register index 280): the rerun of a run that names a record which froze no
    // dataset is refused as its creation is. The detail counts the fields; the lock to pass stands
    // in the finding alone, and the record says every sentence of a refusal (DS-CMP-29).
    const lock = AS_LOCKED.lock;
    const permanent = {
      ...lock,
      id: "8b10c4d2-6e1f-4a3b-9c8d-7e6f5a4bff08",
      kind: "PERMANENT_LOCK",
      dataset_lock_id: lock.id,
    };
    serve();
    server.use(
      http.post(
        apiUrl("/api/v1/report-runs/:runId/rerun"),
        () => rerunRefusal(permanent.id, [lock, permanent]) ?? HttpResponse.error(),
      ),
    );
    open(`/reports/runs/${RUN_ID}`);
    fireEvent.click(await screen.findByRole("button", { name: "Rerun from the same source" }));
    expect(
      await screen.findByRole("heading", { name: "Check the highlighted fields" }),
    ).toBeTruthy();
    expect(screen.getByText("1 field needs attention.")).toBeTruthy();
    expect(
      screen.getByText(
        `Lock ${permanent.id} is the permanent lock of FY2026-P08: it froze no dataset ` +
          `(E-63 PERMANENT_LOCK). The datasets of FY2026-P08 are those of lock ${lock.id}; ` +
          "pass that lock.",
      ),
    ).toBeTruthy();
    expect(screen.queryByTestId("SF-08-banner-rerun-result")).toBeNull();
  });

  it("without report.export the record offers no download", async () => {
    serve();
    open(`/reports/runs/${RUN_ID}`, signedInMe({ permissions: ["contract.read", "report.run"] }));
    await screen.findByRole("heading", { level: 1, name: "Report run RPT-000412" });
    expect(screen.queryByRole("link", { name: "Download XLSX" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Download manifest" })).toBeNull();
    expect(screen.getByRole("button", { name: "Rerun from the same source" })).toBeTruthy();
  });

  it("an id the member may not see is not found", async () => {
    serve();
    const { router } = open("/reports/runs/00000000-0000-4000-8000-000000000000");
    expect(await screen.findByRole("heading", { name: "Report run not found" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Go to report runs" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/reports/runs"));
  });
});

describe("API-S-ReportRun as the screens read it", () => {
  it("every column of the register holds its header", () => {
    expect(narrowColumns(reportRunColumns({ built: new Set(), open: () => undefined }))).toEqual(
      [],
    );
  });

  it("RV-03: what a rerun reads follows the run's source binding", () => {
    const sources = (kind: string, strategy: string | null) => ({
      sources: { ...reportRun().sources, kind, strategy },
    });
    expect(rerunOffer(sources("bound", "adapter"))).toBe("same-source");
    expect(rerunOffer(sources("retained", "retained_inputs"))).toBe("same-source");
    expect(rerunOffer(sources("as_locked", null))).toBe("same-source");
    expect(rerunOffer(sources("open", "open"))).toBe("new-evaluation");
    expect(rerunOffer(sources("failed_without_capture", "adapter"))).toBe("new-evaluation");
    expect(rerunOffer(sources("legacy_unbound", "open"))).toBe("new-evaluation");
    expect(rerunOffer(sources("legacy_unbound", "adapter"))).toBe("unbound");
    expect(rerunOffer(sources("legacy_unbound", "retained_inputs"))).toBe("unbound");
  });

  it("RV-03: the Sources sentence of each kind", () => {
    expect(sourcesText(VIEW_RUN)).toBe(
      "Bound: 18 contract versions, 3 grouping labels, 2 memberships, 18 rows, cutoff 12 Sep 2026 15:40 UTC",
    );
    const sources = (kind: string, strategy: string | null = null) =>
      sourcesText({ sources: { ...reportRun().sources, kind, strategy } });
    expect(sources("retained")).toBe(
      "Retained inputs — a same-source rerun rebuilds from the run's retained evidence",
    );
    expect(sources("open")).toBe(
      "Open (no same-source support yet) — a rerun is a new live evaluation",
    );
    expect(sources("pending")).toBe("Pending (not yet captured)");
    expect(sources("legacy_unbound", "open")).toBe(
      "Unbound (created before source binding) — a rerun is a new live evaluation",
    );
    // A kind this release does not know reads as stored.
    expect(sources("mirrored")).toBe("mirrored");
  });

  it("RV-03: the basis of known_at is the parameter the run stored", () => {
    expect(knownAtBasis({ parameters: { known_at_basis: "historical" } })).toBe(
      "As of the supplied cutoff",
    );
    expect(knownAtBasis({ parameters: { known_at_basis: "record" } })).toBe("Recorded by the run");
    expect(knownAtBasis({ parameters: {} })).toBe("basis: record (pre-parameter run)");
  });

  it("a control total is shown as recorded: amounts per currency, anything else as stored", () => {
    const text = (value: unknown) => recorded(value).replaceAll("\u00a0", " ");
    expect(text(211)).toBe("211");
    expect(text("2026-09-30")).toBe("2026-09-30");
    expect(text({ rows: 3 })).toBe('{"rows":3}');
    // A map or a list the run recorded nothing in reads as no value, not as "{}" or an empty cell.
    expect(text({})).toBe("—");
    expect(text([])).toBe("—");
    expect(text(null)).toBe("—");
  });

  it("a control total without a value shows the no-value mark", async () => {
    serve([reportRun({ control_totals: { excluded_total: {}, row_count: 211 } })]);
    open(`/reports/runs/${RUN_ID}`);
    const totals = await screen.findByRole("table", { name: "Control totals" });
    expect(pairs(totals)).toEqual([
      ["excluded_total", "—No value"],
      ["row_count", "211"],
    ]);
  });

  it("a pack run has no report view; a run of several entities names none", () => {
    expect(
      reportViewHref(
        reportRun({ report: { code: "period_evidence_pack", version: 1, name: "Period pack" } }),
      ),
    ).toBeNull();
    expect(
      reportViewHref(
        reportRun({
          parameters: {
            entity_codes: ["AVM-US", "AVM-DE"],
            book: "ASC606",
            known_at_basis: "record",
          },
          output: null,
        }),
      ),
      // SCR-URL-01 rev 1.61: it says all entities, since an address that names none is the pill's entity.
    ).toBe(`/reports/rpo?book=ASC606&run=${RUN_ID}&entities=all`);
  });
});
