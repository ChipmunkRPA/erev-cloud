// @vitest-environment jsdom
// RV-04 "As locked" on a closed context period, report by report (item RV-AS-LOCKED-DEFAULT-1; SCREENS_B
// §0.5 RV-04 rev 1.98; ENGINE_SPEC_B S15-R-19; docs/dev-guide.md DG-FE-18). The definitions are the
// API's own (`src/test/as-locked.json`, written by `scripts/as_locked_fixture.py`) and the fake of
// `POST /report-runs` is the API's rule: it refuses what `locked.reconcile_selectors` refuses.
//   - The twelve reports with a lock dataset are as locked by default, on the lock and its own
//     selectors and nothing else, and their toolbar's fields are unavailable.
//   - Every other report shows current figures and says so: it writes no `snapshot`, sends no lock,
//     and offers no "Show as locked" — a period lock does not freeze it.
import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../../app/router";
import type { ReportDefinition, ReportRow, ReportRun } from "../../../lib/api/queries/reports";
import type { Period } from "../../../lib/api/queries/tenant";
import { installMemoryStorage, renderApp, signedInMe } from "../../../test/app";
import {
  AS_LOCKED,
  asLockedRefusal,
  definitionOf,
  type LockScope,
  rerunRefusal,
  takes,
} from "../../../test/as-locked";
import { installGridViewport } from "../../../test/layout";
import { apiUrl, installMswServer, server } from "../../../test/msw";
import { toolbarKeys } from "../viewer/ParametersToolbar";
import { LEGACY_JE_SUMMARY, PACK_CODES } from "../viewer/specs";

installMswServer();
installMemoryStorage();
installGridViewport();
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
});

/** A Controller: the reports, the calendar and the exports. */
const MARCUS = signedInMe({
  permissions: ["contract.read", "config.read", "report.run", "report.export"],
});

const JOB_ID = "8e7d6c5b-4a3f-4e2d-9c1b-0a9f8e7d6c5b";
const LOCK = AS_LOCKED.lock;
/** July's lock: a lock of the workspace that is not the context period's. */
const JULY_LOCK: LockScope = {
  id: "8b10c4d2-6e1f-4a3b-9c8d-7e6f5a4baa07",
  entity_code: LOCK.entity_code,
  book_code: LOCK.book_code,
  period_key: "FY2026-P07",
};
const CONTEXT = `entity=${LOCK.entity_code}&period=${LOCK.period_key}&book=${LOCK.book_code}`;
const AS_LOCKED_SENTENCE = "Showing Aug 2026 as locked on 03 Sep 2026 09:14 UTC.";
const CURRENT_SENTENCE = "Showing current figures. Aug 2026 was locked on 03 Sep 2026 09:14 UTC.";
const NOT_FROZEN = "A period lock does not freeze this report.";
const NO_PARAMETERS = "Figures as locked take no parameters. Show current figures to change them.";
const AVM_US = {
  id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000001",
  code: LOCK.entity_code,
  name: "Avenmoor Inc. (Demo)",
};

function runId(round = 1): string {
  return `5b0c7a1e-3d2f-4e6a-9b8c-7d6e5f4a3b0${String(round)}`;
}

/**
 * A lock record as API-S-Period serves it. E-63 `lock_kind`: the record of a close holds the
 * datasets; a permanent lock's holds none. The close of these fixtures was on 3 September, the
 * permanent lock on 20 September.
 */
function record(id: string, kind: "LOCK" | "PERMANENT_LOCK") {
  return {
    id,
    created_at: kind === "LOCK" ? "2026-09-03T09:14:00Z" : "2026-09-20T10:00:00Z",
    created_by: { id: null, kind: "SYSTEM", display_name: "System" },
    kind,
    ledger_head_chain_seq: 1388,
    snapshot_manifest_sha256: null,
  };
}

/**
 * A period of AVM-US. `lock` is the record of its close, null where it has none; `permanent` is the
 * record of its permanent lock. API-S-Period names two locks (04 §16.8, register index 280):
 * `current_lock`, the record that locked the period last, and `dataset_lock`, the LOCK whose datasets
 * stand — the same record while the period is `closed`, the LOCK the permanent lock sealed on a
 * `permanently_locked` one, null where no LOCK record exists.
 */
function period(
  key: string,
  name: string,
  start: string,
  end: string,
  lock: string | null,
  permanent: string | null = null,
): Period {
  const close = lock === null ? null : record(lock, "LOCK");
  return {
    id: `1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e${key.slice(-2)}`,
    entity: AVM_US,
    book: LOCK.book_code,
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
    state: permanent !== null ? "permanently_locked" : lock === null ? "open" : "closed",
    is_first_open: lock === null && permanent === null,
    row_version: 1,
    state_changed_at: "2026-09-03T09:14:00Z",
    close_run: null,
    current_lock: permanent === null ? close : record(permanent, "PERMANENT_LOCK"),
    dataset_lock: close,
    follows: null,
    blockers: null,
  } as unknown as Period;
}

/** July and August are closed, each under its lock; September is open. */
const PERIODS: readonly Period[] = [
  period("FY2026-P07", "Jul 2026", "2026-07-01", "2026-07-31", JULY_LOCK.id),
  period("FY2026-P08", "Aug 2026", "2026-08-01", "2026-08-31", LOCK.id),
  period("FY2026-P09", "Sep 2026", "2026-09-01", "2026-09-30", null),
];

/**
 * August permanently locked: its current lock record is the permanent lock's, which holds no dataset
 * of its own (04 T-CLS-04; `close/commands.py` `_execute_permanent_lock`), and the lock whose
 * datasets stand is the one it sealed — August's lock of 3 September. A run that names the permanent
 * lock's record is refused; one that names the sealed lock reads what the close froze.
 */
const PERMANENT_LOCK: LockScope = { ...LOCK, id: "8b10c4d2-6e1f-4a3b-9c8d-7e6f5a4bff08" };
const JULY_PERMANENT = "8b10c4d2-6e1f-4a3b-9c8d-7e6f5a4bff07";
const PERMANENT: readonly Period[] = [
  period("FY2026-P07", "Jul 2026", "2026-07-01", "2026-07-31", JULY_LOCK.id, JULY_PERMANENT),
  period("FY2026-P08", "Aug 2026", "2026-08-01", "2026-08-31", LOCK.id, PERMANENT_LOCK.id),
  period("FY2026-P09", "Sep 2026", "2026-09-01", "2026-09-30", null),
];
/** August permanently locked with no record of a close: the API names no lock whose datasets stand. */
const UNSEALED: readonly Period[] = [
  period("FY2026-P08", "Aug 2026", "2026-08-01", "2026-08-31", null, PERMANENT_LOCK.id),
  period("FY2026-P09", "Sep 2026", "2026-09-01", "2026-09-30", null),
];
/** The current sentence with the permanent lock's time: said only where no lock's datasets stand. */
const PERMANENT_SENTENCE = "Showing current figures. Aug 2026 was locked on 20 Sep 2026 10:00 UTC.";

/**
 * The lock records of a fake's world, as the API reads them where a run names one (S15-R-19 rev
 * 1.167): each period's current record and the LOCK whose datasets stand for it, every record with
 * its kind and with that LOCK. A run that names a record which is no LOCK is refused by name.
 */
function locksOf(periods: readonly Period[]): LockScope[] {
  return periods.flatMap((item) => {
    const standing = item.dataset_lock ?? null;
    const records = new Map(
      [item.current_lock, standing].flatMap((lock) =>
        lock === null || lock === undefined ? [] : [[lock.id, lock] as const],
      ),
    );
    return [...records.values()].map((lock) => ({
      id: lock.id,
      entity_code: item.entity.code,
      book_code: item.book,
      period_key: item.period.period_key,
      kind: lock.kind,
      dataset_lock_id: standing?.id ?? null,
    }));
  });
}

interface Creation {
  readonly report_code: string;
  readonly output_format: string;
  readonly parameters: Record<string, unknown>;
}

interface Served {
  /** The body of each `POST /report-runs`, in order. */
  readonly posted: Creation[];
}

/** The frozen WATERFALL dataset as the API serves it: long form, every cell text (RV-04 rev 1.17). */
const FROZEN_ROWS = [
  {
    // `snapshots.row_key_of`: "obligation:" and the kind's key columns, joined with ":".
    row_key: "obligation:AVM-US:SF-ORD-10001:O1:FY2026-P08",
    entity_code: "AVM-US",
    contract_external_id: "SF-ORD-10001",
    obligation_key: "O1",
    period_key: "FY2026-P08",
    currency: "USD",
    customer_name: "Marrowby Health",
    product_code: "SUB-PLAT",
    revenue_category: "Subscription",
    recognised: "9764.38",
    scheduled: "0.00",
    awaiting_trigger: "0.00",
    total: "9764.38",
  },
] as unknown as readonly ReportRow[];

/**
 * The frozen RPO dataset (`snapshots.freeze_rpo`): ordinary obligations are section 1 and the exempt
 * ones section 2, under one header — and `section`, like every cell of a lock dataset, is text.
 */
const FROZEN_RPO = {
  entity_code: "AVM-US",
  currency: "USD",
  total: "",
  current: "",
  noncurrent: "",
  expedient: "",
  expedient_label: "",
  remaining_duration_months: "",
  excluded_amount: "",
  excluded_descriptor: "",
};
const FROZEN_RPO_ROWS = [
  {
    ...FROZEN_RPO,
    row_key: "obligation:AVM-US:SF-ORD-10417:O1",
    section: "1",
    contract_external_id: "SF-ORD-10417",
    obligation_key: "O1",
    customer_name: "Castellan Freight",
    nature: "Platform subscription",
    total: "105043.80",
    current: "70029.20",
    noncurrent: "35014.60",
  },
  {
    ...FROZEN_RPO,
    row_key: "obligation:AVM-US:SF-ORD-10555:O2",
    section: "2",
    contract_external_id: "SF-ORD-10555",
    obligation_key: "O2",
    customer_name: "Pellworth Logistics",
    nature: "Onboarding services",
    expedient: "POL-197",
    expedient_label: "Original expected duration of one year or less",
    remaining_duration_months: "7",
    excluded_amount: "1200.00",
    excluded_descriptor: "Fixed consideration",
  },
] as unknown as readonly ReportRow[];

/** `stored`: runs the API holds before the page opens, by id, each with the creation that made it. */
function serve(
  definition: ReportDefinition,
  rows: readonly ReportRow[] = [],
  stored: Readonly<Record<string, Creation>> = {},
  periods: readonly Period[] = PERIODS,
): Served {
  const posted: Creation[] = [];
  const list = (items: readonly unknown[]) => HttpResponse.json({ items, next_cursor: null });
  const made = new Map<string, Creation>(Object.entries(stored));
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () => list([])),
    http.get(apiUrl("/api/v1/entities"), () => list([])),
    http.get(apiUrl("/api/v1/books"), () => list([])),
    http.get(apiUrl("/api/v1/jobs"), () => list([])),
    http.get(apiUrl("/api/v1/exceptions"), () => list([])),
    http.get(apiUrl("/api/v1/currencies"), () =>
      list([
        { code: "USD", name: "US dollar", minor_unit: 2, numeric_code: "840", is_active: true },
      ]),
    ),
    http.get(apiUrl("/api/v1/periods"), () => list(periods)),
    http.get(apiUrl("/api/v1/report-definitions/:code"), () => HttpResponse.json(definition)),
    http.post(apiUrl("/api/v1/report-runs"), async ({ request }) => {
      const body = (await request.json()) as Creation;
      posted.push(body);
      // The API's rule: a creation that names a lock is answered as `locked.py` answers it, for the
      // records of the periods this world serves.
      const refusal = asLockedRefusal(body.report_code, body.parameters, locksOf(periods));
      if (refusal !== null) {
        return refusal;
      }
      const id = runId(posted.length);
      made.set(id, body);
      return HttpResponse.json(
        { id: JOB_ID, kind: "REPORT_RUN", state: "QUEUED" },
        {
          status: 202,
          headers: { Location: `/api/v1/jobs/${JOB_ID}`, "X-Erev-Report-Run-Id": id },
        },
      );
    }),
    http.post(apiUrl("/api/v1/report-runs/:runId/rerun"), ({ params }) => {
      // `framework.rerun`: a stored run that names a record which froze nothing is refused as its
      // creation is. No case here follows a rerun that is admitted.
      const lock = made.get(String(params.runId))?.parameters.period_lock_id;
      return (
        rerunRefusal(typeof lock === "string" ? lock : null, locksOf(periods)) ??
        HttpResponse.json(
          { id: JOB_ID, kind: "REPORT_RUN", state: "QUEUED" },
          { status: 202, headers: { Location: `/api/v1/jobs/${JOB_ID}` } },
        )
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
    http.get(apiUrl("/api/v1/report-runs/:runId"), ({ params }) => {
      const id = String(params.runId);
      const body = made.get(id);
      const lock = body?.parameters.period_lock_id;
      return HttpResponse.json({
        id,
        report_run_no: `RPT-0004${id.slice(-2)}`,
        report: { code: definition.code, version: definition.version, name: definition.name },
        status: "SUCCEEDED",
        parameters: body?.parameters ?? {},
        entity_scope: [AVM_US],
        book: LOCK.book_code,
        as_of: "2026-08-31",
        known_at: "2026-09-12T16:02:00Z",
        period_lock_id: typeof lock === "string" ? lock : null,
        engine_release: { engine_version: "1.0.0", build_sha: "3f9a1c22" },
        row_count: rows.length,
        control_totals: {},
        tie_out_results: [],
        ledger_heads: {},
        output: null,
        problem: null,
        job_id: null,
        sources: [],
        run_by: {
          id: "6d2e9b8f-3c5a-4d7e-8f9b-8a7c6d5e4f3b",
          display_name: "Marcus Webb",
          kind: "USER",
        },
        started_at: "2026-09-12T16:02:11Z",
        finished_at: "2026-09-12T16:02:19Z",
      } as unknown as ReportRun);
    }),
    http.get(apiUrl("/api/v1/report-runs/:runId/data"), () =>
      HttpResponse.json({
        items: rows,
        next_cursor: null,
        // An as-locked run's columns are the frozen header, each a text column (`locked.report_data`).
        columns:
          rows.length === 0
            ? []
            : Object.keys(rows[0] ?? {})
                .filter((key) => key !== "row_key")
                .map((key) => ({ key, label: key, kind: "text" })),
      }),
    ),
  );
  return { posted };
}

function open(path: string) {
  return renderApp(path, { me: MARCUS, screenRoutes: SCREEN_ROUTES });
}

function searchOf(app: ReturnType<typeof open>): string {
  return app.router.state.location.search;
}

/**
 * The as-locked run is in the address: the page has asked it and written it. A case that then leaves
 * the lock waits for this first. The answer of a creation still in flight writes the address from the
 * search the view rendered last, and where it lands between a click and that click's render it undoes
 * the click — the address read `snapshot=<lock>&run=<the first run>` after "Show current figures" in
 * one run at load 73. That window is the product's and is reported; these cases are not about it.
 */
async function asLockedRunWritten(app: ReturnType<typeof open>): Promise<void> {
  await waitFor(() => {
    expect(searchOf(app)).toBe(`?${CONTEXT}&snapshot=${LOCK.id}&run=${runId()}`);
  });
}

/** The lock with the selectors of the report's schema that are the lock's own: all an as-locked run says. */
function ownSelectors(
  definition: ReportDefinition,
  lock: LockScope = LOCK,
): Record<string, unknown> {
  const parameters: Record<string, unknown> = { period_lock_id: lock.id };
  if (takes(definition, "entity_codes")) {
    parameters.entity_codes = [LOCK.entity_code];
  }
  if (takes(definition, "book")) {
    parameters.book = LOCK.book_code;
  }
  for (const key of AS_LOCKED.period_keys) {
    if (takes(definition, key)) {
      parameters[key] = LOCK.period_key;
    }
  }
  return parameters;
}

/** The fields of the parameters toolbar: not "Run report", and not SF-04's own "Layout". */
function fieldsOf(bar: HTMLElement): HTMLElement[] {
  return [
    ...within(bar).queryAllByRole("combobox"),
    ...within(bar).queryAllByRole("textbox"),
    ...within(bar).queryAllByRole("radio"),
  ].filter(
    (field) => field.closest('[role="radiogroup"]')?.getAttribute("aria-label") !== "Layout",
  );
}

/** The sentence the toolbar is described by, under its fields; null where it has none. */
function noteOf(bar: HTMLElement): string | null {
  const id = bar.getAttribute("aria-describedby");
  return id === null ? null : (document.getElementById(id)?.textContent ?? null);
}

function unavailable(field: HTMLElement): boolean {
  return (
    (field as HTMLInputElement).disabled === true || field.getAttribute("aria-disabled") === "true"
  );
}

/** The reports that open in SF-08:report: every definition but the packs and the journal summary. */
const VIEWS = AS_LOCKED.definitions
  .map((definition) => definition.code)
  .filter((code) => !PACK_CODES.has(code) && code !== LEGACY_JE_SUMMARY);
const WITH_DATASET = VIEWS.filter((code) => Object.hasOwn(AS_LOCKED.kinds, code));
const WITHOUT_DATASET = VIEWS.filter((code) => !Object.hasOwn(AS_LOCKED.kinds, code));

/**
 * SF-08:report of a frozen report on a locked August: as locked by default on the lock whose
 * datasets stand — August's lock of 3 September — with the lock's own selectors and nothing else,
 * the time of that lock in the banner and the stamp, and the toolbar unavailable.
 */
async function expectAsLockedByDefault(code: string, periods: readonly Period[]): Promise<void> {
  const definition = definitionOf(code);
  const served = serve(definition, [], {}, periods);
  const app = open(`/reports/${code}?${CONTEXT}`);
  // RV-04: the locked context period sets `snapshot` to that lock; the API admits the creation.
  await waitFor(() => {
    expect(searchOf(app)).toBe(`?${CONTEXT}&snapshot=${LOCK.id}&run=${runId()}`);
  });
  expect(served.posted).toEqual([
    { report_code: code, parameters: ownSelectors(definition), output_format: "JSON" },
  ]);
  const stamp = await screen.findByTestId("SF-08-run-stamp");
  expect(within(stamp).getByText("As locked on 03 Sep 2026 09:14 UTC")).toBeTruthy();
  expect(screen.getByText(AS_LOCKED_SENTENCE)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Show current figures" })).toBeTruthy();
  expect(screen.queryByText("Check the highlighted fields")).toBeNull();

  // Rev 1.98: a lock's figures take no parameter, so every field is shown and unavailable, and
  // the page says why; "Run report" stays — it asks the same lock again.
  const bar = screen.getByTestId("SF-08-filter-bar");
  const fields = fieldsOf(bar);
  expect(fields.length > 0).toBe(toolbarKeys(definition).length > 0);
  expect(fields.filter((field) => !unavailable(field))).toEqual([]);
  expect(noteOf(bar)).toBe(fields.length > 0 ? NO_PARAMETERS : null);
  // A range the bar shows is the lock's one period, not the default range of the report.
  expect(
    within(bar)
      .queryAllByRole("combobox", { name: /^(From|To)/ })
      .map((field) => field.textContent),
  ).toEqual(takes(definition, "from_period_key") ? ["Aug 2026", "Aug 2026"] : []);
  const again = within(bar).getByRole("button", { name: "Run report" });
  expect(unavailable(again)).toBe(false);
  fireEvent.click(again);
  await waitFor(() => {
    expect(served.posted).toHaveLength(2);
  });
  expect(served.posted[1]?.parameters).toEqual(ownSelectors(definition));
}

describe("RV-04 on a closed period: the reports with a lock dataset", () => {
  it("are the twelve of the API's kinds table", () => {
    expect(WITH_DATASET).toHaveLength(12);
    expect([...WITH_DATASET].sort()).toEqual(Object.keys(AS_LOCKED.kinds).sort());
  });

  it.each(WITH_DATASET)(
    "%s: as locked by default, on the lock's own selectors, the toolbar unavailable",
    async (code) => {
      await expectAsLockedByDefault(code, PERIODS);
    },
  );

  it("SF-04: the waterfall as locked by default, on the lock's own selectors, the bar unavailable", async () => {
    const definition = definitionOf("revenue_waterfall");
    const served = serve(definition, FROZEN_ROWS);
    const app = open(`/schedules?${CONTEXT}`);
    await waitFor(() => {
      expect(searchOf(app)).toBe(`?${CONTEXT}&snapshot=${LOCK.id}&run=${runId()}`);
    });
    // Not the fiscal year, the as-of date and the screen's three choices: the API refuses all six.
    expect(served.posted.map((body) => body.parameters)).toEqual([ownSelectors(definition)]);
    expect(await screen.findByText(AS_LOCKED_SENTENCE)).toBeTruthy();
    const bar = screen.getByTestId("SF-04-filter-bar");
    const fields = fieldsOf(bar);
    expect(fields.length).toBeGreaterThan(0);
    expect(fields.filter((field) => !unavailable(field))).toEqual([]);
    expect(noteOf(bar)).toBe(NO_PARAMETERS);
    // The range the bar shows is the lock's period, not the fiscal year a lock does not hold.
    expect(within(bar).getByRole("combobox", { name: /^From/ }).textContent).toContain("Aug 2026");
    expect(within(bar).getByRole("combobox", { name: /^To/ }).textContent).toContain("Aug 2026");
    // The frozen dataset is long form and text: the grid shows it, and no chart is drawn from it.
    expect(await screen.findByTestId("SF-04-row-avm-us-sf-ord-10001-o1-fy2026-p08")).toBeTruthy();
    expect(screen.queryByTestId("SF-04-chart-waterfall")).toBeNull();
  });

  it("a cutoff the address names goes with the lock, and nothing else of the address does", async () => {
    const definition = definitionOf("rpo");
    const served = serve(definition);
    open(`/reports/rpo?${CONTEXT}&known_at=2026-09-10T00:00:00Z&currency_view=functional`);
    expect(await screen.findByTestId("SF-08-run-stamp")).toBeTruthy();
    expect(served.posted.map((body) => body.parameters)).toEqual([
      { ...ownSelectors(definition), known_at: "2026-09-10T00:00:00Z" },
    ]);
  });

  it("SF-04: another period's lock is kept as written, and neither sentence is said of it", async () => {
    const definition = definitionOf("revenue_waterfall");
    const served = serve(definition);
    const app = open(`/schedules?${CONTEXT}&snapshot=${JULY_LOCK.id}`);
    // The screen's own parameters go beside the lock the address names, and the API says which of
    // them a lock's dataset does not take.
    expect(
      await screen.findByText(
        `as_of cannot be applied to an as-locked run: the frozen WATERFALL dataset of lock ${JULY_LOCK.id} carries no such selector. Run the report current to apply it.`,
        undefined,
        { timeout: 5000 },
      ),
    ).toBeTruthy();
    expect(searchOf(app)).toBe(`?${CONTEXT}&snapshot=${JULY_LOCK.id}`);
    expect(served.posted).toHaveLength(1);
    expect(served.posted[0]?.parameters).toMatchObject({ period_lock_id: JULY_LOCK.id });
    expect(screen.queryByText(AS_LOCKED_SENTENCE)).toBeNull();
    expect(screen.queryByText(CURRENT_SENTENCE)).toBeNull();
    const bar = screen.getByTestId("SF-04-filter-bar");
    expect(noteOf(bar)).toBeNull();
    expect(fieldsOf(bar).filter(unavailable)).toEqual([]);
  });

  it("SF-04: Run report under a lock asks the same run again and writes no range into the address", async () => {
    const definition = definitionOf("revenue_waterfall");
    const served = serve(definition, FROZEN_ROWS);
    const app = open(`/schedules?${CONTEXT}`);
    await waitFor(() => {
      expect(searchOf(app)).toBe(`?${CONTEXT}&snapshot=${LOCK.id}&run=${runId()}`);
    });
    fireEvent.click(screen.getByRole("button", { name: "Run report" }));
    // The bar's range is the lock's month and no choice: as `f.period` it would outlive the lock
    // and stand in the address when current figures are shown.
    await waitFor(() => {
      expect(searchOf(app)).toBe(`?${CONTEXT}&snapshot=${LOCK.id}&run=${runId(2)}`);
    });
    expect(served.posted.map((body) => body.parameters)).toEqual([
      ownSelectors(definition),
      ownSelectors(definition),
    ]);
  });

  it("the frozen rows are a table without a chart on SF-08:report too", async () => {
    serve(definitionOf("revenue_waterfall"), FROZEN_ROWS);
    open(`/reports/revenue_waterfall?${CONTEXT}`);
    expect(await screen.findByTestId("SF-08-row-avm-us-sf-ord-10001-o1-fy2026-p08")).toBeTruthy();
    expect(screen.getByText(AS_LOCKED_SENTENCE)).toBeTruthy();
    expect(screen.queryByTestId("SF-08-chart-revenue-waterfall")).toBeNull();
  });

  it("an as-locked RPO keeps its two sections: a frozen row states its section as text", async () => {
    serve(definitionOf("rpo"), FROZEN_RPO_ROWS);
    open(`/reports/rpo?${CONTEXT}`);
    const ordinary = await screen.findByTestId("SF-08-row-avm-us-sf-ord-10417-o1");
    const exempt = screen.getByTestId("SF-08-row-avm-us-sf-ord-10555-o2");
    expect(screen.getByText(AS_LOCKED_SENTENCE)).toBeTruthy();
    // The exempt obligation is listed under "Exempt contracts", and that grid does not say it is
    // empty beside a first grid that holds its rows.
    const first = screen.getByTestId("SF-08-grid-remaining-performance-obligations");
    const second = screen.getByTestId("SF-08-grid-exempt-contracts");
    expect(first.contains(ordinary)).toBe(true);
    expect(first.contains(exempt)).toBe(false);
    expect(second.contains(exempt)).toBe(true);
    expect(within(second).queryByText("No rows in this section.")).toBeNull();
  });

  it("Show current figures gives the toolbar back and runs the report's own defaults", async () => {
    const definition = definitionOf("revenue_waterfall");
    const served = serve(definition);
    const app = open(`/reports/revenue_waterfall?${CONTEXT}`);
    await asLockedRunWritten(app);
    fireEvent.click(screen.getByRole("button", { name: "Show current figures" }));
    await waitFor(() => {
      expect(searchOf(app)).toBe(`?${CONTEXT}&run=${runId(2)}`);
    });
    expect(await screen.findByText(CURRENT_SENTENCE)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Show as locked" })).toBeTruthy();
    expect(screen.queryByText(NOT_FROZEN)).toBeNull();
    const bar = screen.getByTestId("SF-08-filter-bar");
    expect(noteOf(bar)).toBeNull();
    expect(fieldsOf(bar).filter(unavailable)).toEqual([]);
    // RPT-01's defaults: the context period's fiscal year and its last day.
    expect(served.posted[1]?.parameters).toEqual({
      entity_codes: ["AVM-US"],
      book: "ASC606",
      as_of: "2026-08-31",
      from_period_key: "FY2026-P07",
      to_period_key: "FY2026-P09",
    });
  });

  it("an address with another period's lock is kept as written, and the API's refusal stands", async () => {
    // D3: only a hand-made address says this. Nothing is rewritten; the view says what the API says.
    const definition = definitionOf("rpo");
    const served = serve(definition);
    const app = open(`/reports/rpo?${CONTEXT}&snapshot=${JULY_LOCK.id}`);
    expect(
      await screen.findByText(
        `period_key must be FY2026-P07, the period of lock ${JULY_LOCK.id}.`,
        undefined,
        { timeout: 5000 },
      ),
    ).toBeTruthy();
    expect(searchOf(app)).toBe(`?${CONTEXT}&snapshot=${JULY_LOCK.id}`);
    expect(served.posted.map((body) => body.parameters)).toEqual([
      ownSelectors(definition, JULY_LOCK),
    ]);
    // The sentences of RV-04 are August's lock's: neither is said of July's.
    expect(screen.queryByText(AS_LOCKED_SENTENCE)).toBeNull();
    expect(screen.queryByText(CURRENT_SENTENCE)).toBeNull();
    const bar = screen.getByTestId("SF-08-filter-bar");
    expect(noteOf(bar)).toBeNull();
    expect(fieldsOf(bar).filter(unavailable)).toEqual([]);
  });

  it("a stored run of another period's lock is shown as it is, and the page does not call it the context period's", async () => {
    // SF-08:runs opens a stored run on its own parameters. The modification register's name no
    // period, so the context is filled around the run — here with August, whose lock is another:
    // the rows are July's, and "Showing Aug 2026 as locked on <August's time>" was said of them.
    const definition = definitionOf("modification_register");
    const stored = runId(7);
    const served = serve(definition, [], {
      [stored]: {
        report_code: definition.code,
        output_format: "JSON",
        parameters: ownSelectors(definition, JULY_LOCK),
      },
    });
    const app = open(
      `/reports/modification_register?${CONTEXT}&snapshot=${JULY_LOCK.id}&run=${stored}`,
    );
    // The stamp states the source, and cannot date a lock the context period does not hold.
    const stamp = await screen.findByTestId("SF-08-run-stamp");
    expect(within(stamp).getByText("As locked")).toBeTruthy();
    expect(served.posted).toEqual([]);
    expect(searchOf(app)).toBe(`?${CONTEXT}&snapshot=${JULY_LOCK.id}&run=${stored}`);
    expect(screen.queryByText(AS_LOCKED_SENTENCE)).toBeNull();
    expect(screen.queryByText(CURRENT_SENTENCE)).toBeNull();
    expect(screen.queryByRole("button", { name: "Show current figures" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Show as locked" })).toBeNull();
  });
});

describe("RV-04 on a closed period: the reports without a lock dataset", () => {
  it("are the forty-one other report views", () => {
    expect(WITHOUT_DATASET).toHaveLength(41);
    // Seventeen take the lock and the API has no dataset for it; twenty-four take none.
    expect(
      WITHOUT_DATASET.filter((code) => takes(definitionOf(code), "period_lock_id")),
    ).toHaveLength(17);
  });

  it.each(WITHOUT_DATASET)(
    "%s: current figures, said as current, and no lock sent",
    async (code) => {
      const definition = definitionOf(code);
      const served = serve(definition);
      const app = open(`/reports/${code}?${CONTEXT}`);
      await waitFor(() => {
        expect(searchOf(app)).toBe(`?${CONTEXT}&run=${runId()}`);
      });
      expect(served.posted).toHaveLength(1);
      expect(served.posted[0]?.parameters).not.toHaveProperty("period_lock_id");
      expect(await screen.findByTestId("SF-08-run-stamp")).toBeTruthy();
      // RV-04's own sentence for current figures, and why no other source is offered.
      expect(screen.getByText(CURRENT_SENTENCE)).toBeTruthy();
      expect(screen.getByText(NOT_FROZEN)).toBeTruthy();
      expect(screen.queryByText(AS_LOCKED_SENTENCE)).toBeNull();
      expect(screen.queryByRole("button", { name: "Show as locked" })).toBeNull();
      const bar = screen.getByTestId("SF-08-filter-bar");
      expect(noteOf(bar)).toBeNull();
      expect(fieldsOf(bar).filter(unavailable)).toEqual([]);
    },
  );

  it("a hand-made address with a lock: the API's refusal for a report that takes it, nothing for one that does not", async () => {
    // D3. `extract_contracts` takes `period_lock_id` and has no dataset: the lock is sent as the
    // address says, the API refuses it by name, and "Show current figures" is the way out.
    const extract = serve(definitionOf("extract_contracts"));
    const app = open(`/reports/extract_contracts?${CONTEXT}&snapshot=${LOCK.id}`);
    expect(
      await screen.findByText(
        "extract_contracts has no lock dataset (E-64): an as-locked run of this report is not supported; run it current (known_at) instead.",
        undefined,
        { timeout: 5000 },
      ),
    ).toBeTruthy();
    expect(extract.posted[0]?.parameters).toMatchObject({ period_lock_id: LOCK.id });
    fireEvent.click(screen.getByRole("button", { name: "Show current figures" }));
    await waitFor(() => {
      expect(searchOf(app)).toBe(`?${CONTEXT}&run=${runId(2)}`);
    });
    expect(extract.posted[1]?.parameters).not.toHaveProperty("period_lock_id");
    expect(await screen.findByText(NOT_FROZEN)).toBeTruthy();
    cleanup();

    // `judgement_register` takes no lock: the address's `snapshot` is sent nowhere, and the page
    // does not say "as locked" over figures that are current.
    const register = serve(definitionOf("judgement_register"));
    const other = open(`/reports/judgement_register?${CONTEXT}&snapshot=${LOCK.id}`);
    expect(await screen.findByTestId("SF-08-run-stamp")).toBeTruthy();
    expect(register.posted).toHaveLength(1);
    expect(register.posted[0]?.parameters).not.toHaveProperty("period_lock_id");
    expect(screen.getByText(CURRENT_SENTENCE)).toBeTruthy();
    expect(screen.getByText(NOT_FROZEN)).toBeTruthy();
    expect(screen.queryByText(AS_LOCKED_SENTENCE)).toBeNull();
    expect(searchOf(other)).toBe(`?${CONTEXT}&snapshot=${LOCK.id}&run=${runId()}`);
  });
});

describe("RV-04 on a permanently locked period: the lock the permanent lock sealed", () => {
  it.each(WITH_DATASET)(
    "%s: as locked by default on the sealed lock, at the time of the close",
    async (code) => {
      // Red first on rev 1.98: current figures with nothing offered — and before that the permanent
      // lock's own record in the address, whose run fails.
      await expectAsLockedByDefault(code, PERMANENT);
      // The figures were frozen at the close of 3 September; the permanent lock of the 20th froze
      // nothing, and the page does not date them by it.
      expect(screen.queryByText(/20 Sep 2026/)).toBeNull();
    },
  );

  it("SF-04: the waterfall of a permanently locked period is as locked on the sealed lock", async () => {
    const definition = definitionOf("revenue_waterfall");
    const served = serve(definition, FROZEN_ROWS, {}, PERMANENT);
    const app = open(`/schedules?${CONTEXT}`);
    await waitFor(() => {
      expect(searchOf(app)).toBe(`?${CONTEXT}&snapshot=${LOCK.id}&run=${runId()}`);
    });
    expect(served.posted.map((body) => body.parameters)).toEqual([ownSelectors(definition)]);
    expect(await screen.findByText(AS_LOCKED_SENTENCE)).toBeTruthy();
    expect(
      within(await screen.findByTestId("SF-04-run-stamp")).getByText(
        "As locked on 03 Sep 2026 09:14 UTC",
      ),
    ).toBeTruthy();
    const bar = screen.getByTestId("SF-04-filter-bar");
    expect(noteOf(bar)).toBe(NO_PARAMETERS);
    expect(fieldsOf(bar).filter((field) => !unavailable(field))).toEqual([]);
    expect(await screen.findByTestId("SF-04-row-avm-us-sf-ord-10001-o1-fy2026-p08")).toBeTruthy();
  });

  it("Show current figures says the time of the close there too, and offers the sealed lock again", async () => {
    const definition = definitionOf("rpo");
    const served = serve(definition, [], {}, PERMANENT);
    const app = open(`/reports/rpo?${CONTEXT}`);
    await asLockedRunWritten(app);
    fireEvent.click(screen.getByRole("button", { name: "Show current figures" }));
    await waitFor(() => {
      expect(searchOf(app)).toBe(`?${CONTEXT}&run=${runId(2)}`);
    });
    expect(served.posted[1]?.parameters).not.toHaveProperty("period_lock_id");
    expect(await screen.findByText(CURRENT_SENTENCE)).toBeTruthy();
    expect(screen.queryByText(NOT_FROZEN)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show as locked" }));
    await waitFor(() => {
      expect(searchOf(app)).toBe(`?${CONTEXT}&snapshot=${LOCK.id}&run=${runId(3)}`);
    });
    expect(served.posted[2]?.parameters).toEqual(ownSelectors(definition));
    expect(await screen.findByText(AS_LOCKED_SENTENCE)).toBeTruthy();
  });

  it("a report without a lock dataset says there what it says on a closed period", async () => {
    const served = serve(definitionOf("judgement_register"), [], {}, PERMANENT);
    open(`/reports/judgement_register?${CONTEXT}`);
    expect(await screen.findByTestId("SF-08-run-stamp")).toBeTruthy();
    expect(served.posted[0]?.parameters).not.toHaveProperty("period_lock_id");
    expect(screen.getByText(CURRENT_SENTENCE)).toBeTruthy();
    expect(screen.getByText(NOT_FROZEN)).toBeTruthy();
  });

  it("a permanently locked period without a record of its close: current figures, nothing offered", async () => {
    // API-S-Period `dataset_lock` is null where no LOCK record exists: no lock's datasets stand, so
    // nothing defaults to one and nothing offers one. The sentence dates the period by the record
    // that locked it, the only one there is.
    const definition = definitionOf("rpo");
    const served = serve(definition, [], {}, UNSEALED);
    const app = open(`/reports/rpo?${CONTEXT}`);
    await waitFor(() => {
      expect(searchOf(app)).toBe(`?${CONTEXT}&run=${runId()}`);
    });
    expect(served.posted).toHaveLength(1);
    expect(served.posted[0]?.parameters).not.toHaveProperty("period_lock_id");
    expect(await screen.findByTestId("SF-08-run-stamp")).toBeTruthy();
    expect(screen.getByText(PERMANENT_SENTENCE)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Show as locked" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Show current figures" })).toBeNull();
    expect(screen.queryByText(NOT_FROZEN)).toBeNull();
    expect(screen.queryByText(/^Showing .+ as locked on/)).toBeNull();
    const bar = screen.getByTestId("SF-08-filter-bar");
    expect(noteOf(bar)).toBeNull();
    expect(fieldsOf(bar).filter(unavailable)).toEqual([]);
  });

  it("SF-04: without a record of the close the waterfall is current, over its fiscal year", async () => {
    const definition = definitionOf("revenue_waterfall");
    const served = serve(definition, [], {}, UNSEALED);
    const app = open(`/schedules?${CONTEXT}`);
    await waitFor(() => {
      expect(searchOf(app)).toBe(`?${CONTEXT}&run=${runId()}`);
    });
    expect(served.posted).toHaveLength(1);
    expect(served.posted[0]?.parameters).not.toHaveProperty("period_lock_id");
    expect(served.posted[0]?.parameters).toMatchObject({
      from_period_key: "FY2026-P08",
      to_period_key: "FY2026-P09",
    });
    expect(await screen.findByText(PERMANENT_SENTENCE)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Show as locked" })).toBeNull();
    expect(screen.queryByText(NOT_FROZEN)).toBeNull();
    const bar = screen.getByTestId("SF-04-filter-bar");
    expect(noteOf(bar)).toBeNull();
    expect(fieldsOf(bar).filter(unavailable)).toEqual([]);
  });

  it("an address that names the permanent lock's record is kept as written, and the API's refusal names the lock to pass", async () => {
    // The address these screens wrote themselves for a permanently locked period before rev 1.98,
    // or one made by hand. The record is no lock whose datasets stand: it goes with the view's own
    // parameters, as any lock that is not the source does, and the API answers — since S15-R-19
    // rev 1.167 at the creation, by the record's name and the lock whose datasets stand.
    const definition = definitionOf("rpo");
    const served = serve(definition, [], {}, PERMANENT);
    const app = open(`/reports/rpo?${CONTEXT}&snapshot=${PERMANENT_LOCK.id}`);
    expect(
      await screen.findByText(
        `Lock ${PERMANENT_LOCK.id} is the permanent lock of FY2026-P08: it froze no dataset ` +
          `(E-63 PERMANENT_LOCK). The datasets of FY2026-P08 are those of lock ${LOCK.id}; ` +
          "pass that lock.",
      ),
    ).toBeTruthy();
    expect(served.posted).toHaveLength(1);
    expect(served.posted[0]?.parameters).toMatchObject({ period_lock_id: PERMANENT_LOCK.id });
    expect(searchOf(app)).toContain(`snapshot=${PERMANENT_LOCK.id}`);
    // Neither sentence: not "as locked", and not "current figures" of a run that names a lock.
    expect(screen.queryByText(/locked on/)).toBeNull();
    const bar = screen.getByTestId("SF-08-filter-bar");
    expect(noteOf(bar)).toBeNull();
    expect(fieldsOf(bar).filter(unavailable)).toEqual([]);
  });

  it("the rerun of a stored run that names the permanent lock's record is refused in the drawer, by the lock to pass", async () => {
    // A run stored before S15-R-19 rev 1.167 — the one these screens made for a permanently locked
    // period. Its rerun is refused as its creation would be, and the finding alone names the lock
    // to pass: the drawer says the problem's sentences, not its title alone (DS-CMP-29).
    const definition = definitionOf("rpo");
    const stored = runId(7);
    serve(
      definition,
      [],
      {
        [stored]: {
          report_code: definition.code,
          output_format: "JSON",
          parameters: ownSelectors(definition, PERMANENT_LOCK),
        },
      },
      PERMANENT,
    );
    open(`/reports/rpo?${CONTEXT}&snapshot=${PERMANENT_LOCK.id}&run=${stored}`);
    fireEvent.click(await screen.findByRole("button", { name: "Run details" }));
    const drawer = await screen.findByTestId("SF-08-drawer-run-details");
    fireEvent.click(within(drawer).getByRole("button", { name: "Rerun from the same source" }));
    expect(
      await within(drawer).findByRole("heading", { name: "Check the highlighted fields" }),
    ).toBeTruthy();
    expect(
      within(drawer).getByText(
        `Lock ${PERMANENT_LOCK.id} is the permanent lock of FY2026-P08: it froze no dataset ` +
          `(E-63 PERMANENT_LOCK). The datasets of FY2026-P08 are those of lock ${LOCK.id}; ` +
          "pass that lock.",
      ),
    ).toBeTruthy();
    expect(screen.queryByTestId("SF-08-banner-rerun-result")).toBeNull();
  });
});
