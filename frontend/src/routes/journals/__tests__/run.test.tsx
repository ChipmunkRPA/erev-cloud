// @vitest-environment jsdom
// SF-06 journal run screens (BUILD_SPEC CLO-26; SCREENS_B §0.3 SB-R-08, §0.4 E-34 SMAP-05 to SMAP-08, §3.1
// to §3.3; docs/dev-guide.md DG-FE-08): the E-34 chips and their captions, the export control of a
// sandbox workspace, balance checks and totals rendered from API strings, and the account filter alias.
import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SCREEN_ROUTES } from "../../../app/router";
import {
  exportJobKey,
  type Job,
  type JournalBatch,
  type JournalLine,
  type JournalRun,
  type JournalRunSummary,
} from "../../../lib/api/queries/journal-runs";
import type { SubledgerLine } from "../../../lib/api/queries/subledger-lines";
import { installMemoryStorage, renderApp, signedInMe, signedInSession } from "../../../test/app";
import { installGridViewport } from "../../../test/layout";
import { instantMs } from "../../../lib/format";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import { REFUSAL_REFERENCE, REFUSAL_TITLE, refusedWith } from "../../../test/refusals";
import { textLines, TOAST_LINES, TOAST_MESSAGE_BOX } from "../../../test/text-lines";
import { parseCutoff } from "../journal-runs";
import { runChip } from "../run";
import { titledAmount } from "../run-lines";

installMswServer();
installMemoryStorage();
installGridViewport();
// The frame reads the run, then its summary, before the tab renders.
configure({ asyncUtilTimeout: 5000 });

/**
 * DESIGN_SYSTEM DS-CMP-22: a toast holds two lines and the kit cuts the third, which no assertion on
 * its text sees. Every toast a test of this module leaves on the page is therefore measured in the
 * toast's box (../../../test/text-lines): a sentence that needs more room is a banner of the frame.
 */
function expectToastsFit(): void {
  const region = screen.queryByRole("region", { name: "Messages" });
  for (const message of region?.querySelectorAll("p") ?? []) {
    const lines = textLines(message.textContent, TOAST_MESSAGE_BOX);
    expect(
      lines.length,
      `a toast of ${String(lines.length)} lines: ${lines.join(" / ")}`,
    ).toBeLessThanOrEqual(TOAST_LINES);
  }
}

afterEach(() => {
  try {
    expectToastsFit();
  } finally {
    cleanup();
    vi.restoreAllMocks();
  }
});

const MAYA = signedInMe({
  permissions: ["contract.read", "config.read", "journal.run", "journal.export", "report.export"],
});
/** The same member with `audit.read` for all entities: "History" is hers (SCREENS_B §3.2 rev 1.68). */
const READS_AUDIT = signedInMe({ permissions: [...MAYA.permissions, "audit.read"] });

const RUN_ID = "7c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e4f";
const REQUEST_ID = "9e8d7c6b-5a4f-4e3d-8c2b-1a0f9e8d7c6b";
const CONTEXT = "entity=AVM-US&period=FY2026-P08&book=ASC606";
const AVM_US = {
  id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000001",
  code: "AVM-US",
  name: "Avenmoor US Inc.",
};
const ACTOR = {
  id: "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a",
  display_name: "Maya Chen",
  kind: "USER" as const,
};

function money(amount: string, currency = "USD") {
  return { amount, currency };
}

function batch(chunk: number, state: JournalBatch["state"]): JournalBatch {
  return {
    id: `8d2e3f40-5b6c-4d7e-9f80-a1b2c3d4e5f${String(chunk)}`,
    journal_run_id: RUN_ID,
    batch_no: 1,
    chunk_no: chunk,
    txn_currency: "USD",
    functional_currency: "USD",
    state,
    line_count: 12,
    total_debit_txn: money("295.69"),
    total_credit_txn: money("295.69"),
    total_debit_functional: money("295.69"),
    total_credit_functional: money("295.69"),
    external_id: `erev:avenmoor:JR-000209:1:${String(chunk)}`,
    adapter: "CSV",
    detail_file_id: null,
    detail_sha256: null,
    attempt_count: state === "draft" || state === "approved" ? 0 : 1,
    last_error: null,
    exported_at: state === "draft" || state === "approved" ? null : "2026-09-06T09:00:00Z",
    acknowledged_at: state === "acknowledged" ? "2026-09-06T09:05:00Z" : null,
    handed_over_at: null,
    acknowledgements: [],
    row_version: 1,
  };
}

function run(overrides: Partial<JournalRun> = {}): JournalRun {
  return {
    id: RUN_ID,
    run_no: "JR-000209",
    entity: AVM_US,
    book: "ASC606",
    period: {
      id: "1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f",
      period_key: "FY2026-P08",
      name: "Aug 2026",
      start_date: "2026-08-01",
      end_date: "2026-08-31",
    },
    mode: "GROSS",
    delta_book: null,
    grain: "ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS",
    state: "draft",
    cutoff_known_at: "2026-09-05T10:00:00Z",
    coverage: {
      from_chain_seq: 1,
      to_chain_seq: 164,
      delta_from_chain_seq: null,
      delta_to_chain_seq: null,
    },
    totals: {
      line_count: 164,
      debit_functional: money("295.69"),
      credit_functional: money("295.69"),
      balanced: true,
    },
    batches: [batch(1, "draft")],
    je_range: { first_je_no: "JE-AVM-US-000101", last_je_no: "JE-AVM-US-000164", count: 64 },
    approval_request_id: null,
    approved_at: null,
    exported_at: null,
    acknowledged_at: null,
    cancelled_at: null,
    created_by: ACTOR,
    created_at: "2026-09-05T10:00:00Z",
    updated_at: "2026-09-05T10:00:00Z",
    row_version: 1,
    ...overrides,
  };
}

const BALANCED_SUMMARY: JournalRunSummary = {
  lines: [
    {
      account_code: "4010",
      account_name: "Revenue - services and subscriptions",
      currency: "USD",
      debit: money("0.00"),
      credit: money("295.69"),
    },
  ],
  balance_checks: [
    {
      entity_code: "AVM-US",
      currency: "USD",
      basis: "TRANSACTION",
      debit: money("295.69"),
      credit: money("295.69"),
      difference: money("0.00"),
    },
    {
      entity_code: "AVM-US",
      currency: "USD",
      basis: "FUNCTIONAL",
      debit: money("295.69"),
      credit: money("295.69"),
      difference: money("0.00"),
    },
  ],
};

function serveShell() {
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
    http.get(apiUrl("/api/v1/saved-views"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
  );
}

function serveRun(value: JournalRun, summary: JournalRunSummary = BALANCED_SUMMARY) {
  serveShell();
  server.use(
    http.get(apiUrl("/api/v1/journal-runs/:runId"), () => HttpResponse.json(value)),
    http.get(apiUrl("/api/v1/journal-runs/:runId/summary"), () => HttpResponse.json(summary)),
  );
}

/** The grid row holding the link of `runNo`. */
async function rowOf(runNo: string): Promise<HTMLElement> {
  const link = await screen.findByRole("link", { name: runNo });
  const row = link.closest<HTMLElement>('[role="row"]');
  if (row === null) {
    throw new Error(`no grid row for ${runNo}`);
  }
  return row;
}

/** The `dd` text of the figure whose `dt` reads `label`. */
function figure(strip: HTMLElement, label: string): string {
  const term = within(strip).getByText(label, { selector: "dt" });
  return term.nextElementSibling?.textContent ?? "";
}

// ---------------------------------------------------------------------------------------------------
// The exits of a failed run (SCREENS_B §3.2 and §3.4 rev 1.71; 04 §16.7 rev 1.159; item
// JRN-FAILED-EXITS-UI-1).

const JOB_ID = "6f5e4d3c-2b1a-4f0e-9d8c-0000000000aa";
const RUN_HREF = `/api/v1/journal-runs/${RUN_ID}`;
/** A job is read again every 2 seconds, so an ending the test serves later needs more than the default. */
const NEXT_POLL = { timeout: 10_000 };
const LEDGER_FIRST =
  "The ledger is asked first whether it holds a failed batch. If it holds none, the run and its batches are cancelled, and their subledger lines can be summarized again in a new run. A batch the ledger holds is acknowledged instead, and the run is not cancelled.";
const PLAIN_CANCEL =
  "The run and its batches are cancelled. Their subledger lines can be summarized again in a new run.";
const EXITS_BOTH =
  "If the ledger can never accept a batch, cancel the journal run, or hand the batch over for manual posting on the Batches tab.";
const EXITS_CANCEL =
  "If a batch can never be exported as it was calculated, cancel the journal run.";
const EXITS_HAND_OVER =
  "If the ledger can never accept a batch, hand it over for manual posting on the Batches tab.";

/** A batch of the NetSuite adapter; a failed one carries the ledger's refusal. */
function erp(chunk: number, state: JournalBatch["state"]): JournalBatch {
  return {
    ...batch(chunk, state),
    adapter: "NETSUITE",
    ...(state === "failed"
      ? { attempt_count: 8, last_error: "NetSuite: account 5003 is inactive." }
      : {}),
  };
}

/** A CSV batch that failed on eRev's own check of its accounts, before a file existed. */
function failedCsv(chunk: number): JournalBatch {
  return {
    ...batch(chunk, "failed"),
    last_error: "Account 5003 is not in the chart of accounts.",
  };
}

function failedRun(batches: JournalBatch[], overrides: Partial<JournalRun> = {}): JournalRun {
  return run({ state: "failed", approved_at: "2026-09-05T12:00:00Z", batches, ...overrides });
}

function exitJob(mode: "CANCEL" | "HAND_OVER", state: Job["state"], extra: Partial<Job> = {}): Job {
  const ended = state !== "QUEUED" && state !== "RUNNING";
  return {
    id: JOB_ID,
    kind: "JOURNAL_EXPORT",
    mode,
    state,
    progress: { done: 0, total: null },
    created_at: "2026-09-06T09:10:00Z",
    created_by: ACTOR,
    started_at: state === "QUEUED" ? null : "2026-09-06T09:10:01Z",
    finished_at: ended ? "2026-09-06T09:10:05Z" : null,
    problem: null,
    result: null,
    ...extra,
  };
}

/** The problem a job names in `result.refusal`, and a failed job in `problem` (04 §16.7). */
function refusal(detail: string) {
  return {
    type: "https://erev.dev/problems/invalid-transition",
    title: "Action not available in this state",
    status: 409,
    detail,
    instance: `/api/v1/jobs/${JOB_ID}`,
    errors: [{ field: "state", rule_id: "E-34", message: detail }],
  };
}

/** What the API holds; a test changes it as the command and the job would. */
interface ExitWorld {
  run: JournalRun;
  /** The answer of `GET /jobs/{id}`. */
  job: Job | null;
  /** The answer of `GET /jobs`: the run's active job as the reader is shown it. */
  listed: Job[];
  /** The bodies of the commands sent, null for a command without one. */
  readonly posted: unknown[];
  /** The audit events of the run, newest first; none unless a test states them. */
  events?: unknown[];
}

/** Serves `world`; the answer holds the queries of the reads of the run's active jobs. */
function serveExits(world: ExitWorld): { readonly activeJobReads: URLSearchParams[] } {
  const activeJobReads: URLSearchParams[] = [];
  serveShell();
  server.use(
    http.get(apiUrl("/api/v1/journal-runs/:runId"), () => HttpResponse.json(world.run)),
    http.get(apiUrl("/api/v1/journal-runs/:runId/summary"), () =>
      HttpResponse.json(BALANCED_SUMMARY),
    ),
    http.get(apiUrl("/api/v1/journal-runs/:runId/batches"), () =>
      HttpResponse.json(
        { items: world.run.batches, next_cursor: null },
        { headers: { "X-Erev-Total-Count": String(world.run.batches.length) } },
      ),
    ),
    http.get(apiUrl("/api/v1/journal-batches/:batchId"), ({ params }) =>
      HttpResponse.json(world.run.batches.find((item) => item.id === params.batchId)),
    ),
    http.get(apiUrl("/api/v1/jobs"), ({ request }) => {
      const asked = new URL(request.url).searchParams;
      if (asked.get("subject_id") !== RUN_ID) {
        return HttpResponse.json({ items: [], next_cursor: null });
      }
      activeJobReads.push(asked);
      return HttpResponse.json({ items: world.listed, next_cursor: null });
    }),
    http.get(apiUrl("/api/v1/jobs/:jobId"), () => HttpResponse.json(world.job)),
    http.get(apiUrl("/api/v1/audit-events"), () =>
      HttpResponse.json({ items: world.events ?? [], next_cursor: null }),
    ),
  );
  return { activeJobReads };
}

/**
 * A `JOURNAL_EXPORT` job without a mode: the run's export, or the retry of a batch (04 §16.7). It ends
 * `SUCCEEDED` whether or not it sent a batch; `result.waiting` names the batches that are sent later.
 */
function exportJob(state: Job["state"], extra: Partial<Job> = {}): Job {
  return { ...exitJob("CANCEL", state), mode: null, ...extra };
}

/** `result` of an export job that ended: what it did with the run's messages, and what it left. */
function relayed(
  counts: { readonly dispatched: number; readonly failed?: number; readonly dead?: number },
  waiting?: readonly { readonly batch: JournalBatch; readonly at: string }[],
): NonNullable<Job["result"]> {
  return {
    href: RUN_HREF,
    counts: {
      messages: 2,
      claimed: counts.dispatched + (counts.failed ?? 0) + (counts.dead ?? 0),
      dispatched: counts.dispatched,
      failed: counts.failed ?? 0,
      dead: counts.dead ?? 0,
    },
    // An API before 04 rev 1.221 states no `waiting`.
    ...(waiting === undefined
      ? {}
      : {
          waiting: waiting.map((item) => ({
            journal_batch_id: item.batch.id,
            external_id: item.batch.external_id,
            next_attempt_at: item.at,
          })),
        }),
  };
}

/**
 * The command at `path` answers 202 with its job; `then` is what it changes at once. A second command
 * of a test is accepted as another job, `id`.
 */
function accept(
  path: string,
  world: ExitWorld,
  mode: "CANCEL" | "HAND_OVER" | null,
  then: () => void = () => undefined,
  id: string = JOB_ID,
): void {
  server.use(
    http.post(apiUrl(path), async ({ request }) => {
      const text = await request.text();
      world.posted.push(text === "" ? null : (JSON.parse(text) as unknown));
      then();
      const job = mode === null ? exportJob("QUEUED") : exitJob(mode, "QUEUED");
      return HttpResponse.json(
        { ...job, id },
        { status: 202, headers: { Location: `/api/v1/jobs/${id}` } },
      );
    }),
  );
}

/**
 * Lets an ending that is said after a read be said, before a test states that nothing was: the read's
 * answer, the decision and the render that follows are done within it.
 */
function settled(): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, 250);
  });
}

/** Presses the row's "Retry export" of `label` and confirms it. */
async function retryBatch(grid: HTMLElement, label: string): Promise<void> {
  fireEvent.click(
    await within(grid).findByRole("button", { name: `Retry export for batch ${label}` }),
  );
  const dialog = await screen.findByRole("alertdialog", { name: `Retry batch ${label}?` });
  expect(
    within(dialog).getByText(
      "The chunk is sent again with the same external id. The GL will not post it twice.",
    ),
  ).toBeTruthy();
  fireEvent.click(within(dialog).getByRole("button", { name: "Retry export" }));
}

function stateProblem(sentence: string) {
  return problemResponse("invalid-transition", 409, "Action not available in this state", {
    detail: sentence,
    errors: [{ field: "state", rule_id: "E-34", message: sentence }],
  });
}

/** Opens "Cancel journal run" from the overflow and returns its dialog. */
async function openCancel(): Promise<HTMLElement> {
  fireEvent.click(await screen.findByRole("button", { name: "More actions" }));
  fireEvent.click(await screen.findByRole("menuitem", { name: "Cancel journal run" }));
  return screen.findByRole("alertdialog", { name: "Cancel journal run JR-000209?" });
}

function confirmCancel(dialog: HTMLElement, reason: string): void {
  fireEvent.change(within(dialog).getByRole("textbox", { name: "Reason" }), {
    target: { value: reason },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Cancel journal run" }));
}

/** The text an element is described by: the reason of a disabled control (DS-CMP-20, DS-CMP-28). */
function describedBy(element: HTMLElement): string | null {
  const ids = (element.getAttribute("aria-describedby") ?? "").split(" ").filter(Boolean);
  const texts = ids.map((id) => document.getElementById(id)?.textContent ?? "");
  return texts.length === 0 ? null : texts.join(" ");
}

/** The files the page saves: the names an anchor was pressed with, and the object URLs made. */
function watchSaves(): { readonly saved: string[]; readonly made: () => number } {
  const saved: string[] = [];
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    saved.push(this.download);
  });
  const createObjectURL = vi.fn(() => "blob:journal-batch");
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    writable: true,
    value: createObjectURL,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    writable: true,
    value: vi.fn(),
  });
  return { saved, made: () => createObjectURL.mock.calls.length };
}

describe("SF-06 journal runs", () => {
  it("state chips", async () => {
    // SMAP-05 to SMAP-08 as pure mappings.
    expect(runChip({ ...run(), request_status: null })).toMatchObject({
      status: "Calculated",
      caption: null,
    });
    expect(
      runChip({ ...run({ approval_request_id: REQUEST_ID }), request_status: "PENDING" }),
    ).toMatchObject({ status: "Pending approval", caption: "Submitted" });
    expect(
      runChip({ ...run({ state: "approved" }), request_status: null }, "RUNNING"),
    ).toMatchObject({ status: "Running", caption: "Exporting" });
    expect(
      runChip({
        ...run({ state: "acknowledged", batches: [batch(1, "acknowledged")] }),
        request_status: null,
      }),
    ).toMatchObject({ status: "Posted", caption: null });
    const partial = [batch(1, "acknowledged"), batch(2, "exported"), batch(3, "exported")];
    expect(
      runChip({ ...run({ state: "exported", batches: partial }), request_status: null }),
    ).toMatchObject({ status: "Exported", caption: "Partially acknowledged: 1 of 3 batches" });

    // The same chips in the SF-06 grid, the request status read from the approval request.
    const runs = [
      run({ id: "7c1d2e3f-4a5b-4c6d-8e7f-000000000201", run_no: "JR-000201" }),
      run({
        id: "7c1d2e3f-4a5b-4c6d-8e7f-000000000202",
        run_no: "JR-000202",
        approval_request_id: REQUEST_ID,
      }),
      run({
        id: "7c1d2e3f-4a5b-4c6d-8e7f-000000000203",
        run_no: "JR-000203",
        state: "acknowledged",
        batches: [batch(1, "acknowledged")],
      }),
      run({
        id: "7c1d2e3f-4a5b-4c6d-8e7f-000000000204",
        run_no: "JR-000204",
        state: "exported",
        batches: partial,
      }),
    ];
    const listed: URL[] = [];
    serveShell();
    server.use(
      http.get(apiUrl("/api/v1/journal-runs"), ({ request }) => {
        listed.push(new URL(request.url));
        return HttpResponse.json(
          { items: runs, next_cursor: null },
          { headers: { "X-Erev-Total-Count": "4" } },
        );
      }),
      http.get(apiUrl("/api/v1/approvals/:requestId"), () =>
        HttpResponse.json({ id: REQUEST_ID, status: "PENDING" }),
      ),
    );
    renderApp(`/journals?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    expect(await screen.findByRole("heading", { level: 1, name: "Journals" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Run journals" })).toBeTruthy();
    const calculated = await rowOf("JR-000201");
    expect(calculated.textContent).toContain("Calculated");
    const pending = await rowOf("JR-000202");
    await waitFor(() => {
      expect(pending.textContent).toContain("Pending approval");
    });
    expect(pending.textContent).toContain("Submitted");
    expect((await rowOf("JR-000203")).textContent).toContain("Posted");
    const exported = await rowOf("JR-000204");
    expect(exported.textContent).toContain("Exported");
    expect(exported.textContent).toContain("Partially acknowledged: 1 of 3 batches");
    // SCREENS_B §3.1 data bindings: the context entity, book and period, newest period first.
    const first = listed[0];
    expect(first?.searchParams.get("entity")).toBe("AVM-US");
    expect(first?.searchParams.get("period")).toBe("FY2026-P08");
    expect(first?.searchParams.get("book")).toBe("ASC606");
    expect(first?.searchParams.get("sort")).toBe("-period");
  });

  it("sandbox export disabled", async () => {
    const approved = run({ state: "approved", approved_at: "2026-09-05T12:00:00Z" });
    serveRun(approved);
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, {
      session: signedInSession({
        active_tenant: {
          id: "0b6f3e2d-1c4a-4b8e-9d7f-6a5c4b3e2d1f",
          code: "avenmoor-sandbox",
          display_name: "Avenmoor sandbox",
          kind: "sandbox",
        },
      }),
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Journal run JR-000209" }),
    ).toBeTruthy();
    const control = await screen.findByRole("button", { name: "Export journals" });
    expect(control.getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByTestId("SF-06-sandbox-reason").textContent).toBe(
      "Sandbox workspaces cannot post or export journals.",
    );
    // SB-R-08: CSV downloads stay available.
    expect(
      screen.getByRole("button", { name: "Download batch files" }).getAttribute("aria-disabled"),
    ).toBeNull();
  });

  it("export enabled outside a sandbox", async () => {
    serveRun(run({ state: "approved", approved_at: "2026-09-05T12:00:00Z" }));
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const control = await screen.findByRole("button", { name: "Export journals" });
    expect(control.getAttribute("aria-disabled")).toBeNull();
    expect(screen.queryByTestId("SF-06-sandbox-reason")).toBeNull();
  });

  it("totals from api", async () => {
    // Past 2^53: a JavaScript number would print ...992.00, so the figures must be the API strings.
    const huge = "9007199254740993.01";
    serveRun(
      run({
        totals: {
          line_count: 164,
          debit_functional: money(huge),
          credit_functional: money(huge),
          balanced: true,
        },
      }),
      {
        lines: [
          {
            account_code: "4010",
            account_name: "Revenue - services and subscriptions",
            currency: "USD",
            debit: money("0.00"),
            credit: money(huge),
          },
        ],
        balance_checks: [
          {
            entity_code: "AVM-US",
            currency: "USD",
            basis: "TRANSACTION",
            debit: money(huge),
            credit: money(huge),
            difference: money("0.00"),
          },
          {
            entity_code: "AVM-US",
            currency: "USD",
            basis: "FUNCTIONAL",
            debit: money(huge),
            credit: money(huge),
            difference: money("0.00"),
          },
        ],
      },
    );
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const table = await screen.findByRole("table", { name: "Balance checks" });
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3);
    const transaction = rows[1]?.textContent ?? "";
    expect(transaction).toContain("AVM-US");
    expect(transaction).toContain("Transaction currency");
    expect(transaction).toContain("9,007,199,254,740,993.01");
    expect(transaction).toContain("0.00");
    expect(transaction).toContain("Balanced");
    expect(rows[2]?.textContent).toContain("Functional currency");

    const strip = screen.getByTestId("SF-06-kpi-strip");
    expect(within(strip).getByRole("heading", { name: "Totals (USD)" })).toBeTruthy();
    expect(figure(strip, "Debits")).toBe("9,007,199,254,740,993.01");
    expect(figure(strip, "Credits")).toBe("9,007,199,254,740,993.01");
    expect(figure(strip, "Lines")).toBe("164");
    expect(figure(strip, "Batches acknowledged")).toBe("0 of 1");
    const difference = screen.getByTestId("SF-06-kpi-difference");
    expect(difference.textContent).toBe("0.00Balanced");
    expect(within(difference).getByLabelText(/, balanced$/)).toBeTruthy();

    const summary = await screen.findByRole("grid", { name: "Summary by account" });
    await waitFor(() => {
      expect(summary.textContent).toContain("9,007,199,254,740,993.01");
    });
  });

  it("account filter alias", async () => {
    const requested: URL[] = [];
    serveRun(run());
    server.use(
      http.get(apiUrl("/api/v1/journal-runs/:runId/lines"), ({ request }) => {
        requested.push(new URL(request.url));
        return HttpResponse.json({ items: [], next_cursor: null });
      }),
    );
    const { router } = renderApp(`/journals/runs/${RUN_ID}/lines?${CONTEXT}&f.account=is:4010`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    expect(await screen.findByRole("grid", { name: "Journal lines" })).toBeTruthy();
    await waitFor(() => {
      expect(router.state.location.search).toContain("f.account_code=is:4010");
    });
    expect(router.state.location.search).not.toContain("f.account=");
    await waitFor(() => {
      expect(requested.some((url) => url.searchParams.get("account_code") === "4010")).toBe(true);
    });
    // CLO-26: the accepted alias raises no "not recognised" banner.
    expect(
      screen.queryByText("Some filters in the link were not recognised and were removed."),
    ).toBeNull();
    expect(screen.getByText("Account is 4010")).toBeTruthy();
  });
  it("the Contract filter is a combobox that sends the contract id, and the Batch filter lists the batches of the run (W-19)", async () => {
    // Crawl finding F1: both were text fields whose typed text went to the uuid filters `contract`
    // and `batch_id` of the route and answered 422 (SCREENS_B §3.3 rev 1.39).
    const CONTRACT_ID = "6f7a8b9c-0d1e-4f2a-9b3c-4d5e6f7a8b9c";
    const second = batch(2, "draft");
    const requested: URL[] = [];
    serveRun(run({ batches: [batch(1, "draft"), second] }));
    server.use(
      http.get(apiUrl("/api/v1/journal-runs/:runId/lines"), ({ request }) => {
        requested.push(new URL(request.url));
        return HttpResponse.json({ items: [], next_cursor: null });
      }),
      http.get(apiUrl("/api/v1/contracts"), () =>
        HttpResponse.json({
          items: [
            { id: "5e6f7a8b-9c0d-4e1f-8a2b-3c4d5e6f7a8b", external_id: "SF-ORD-10001" },
            { id: CONTRACT_ID, external_id: "SF-ORD-10003" },
          ],
          next_cursor: null,
        }),
      ),
    );
    const { router } = renderApp(`/journals/runs/${RUN_ID}/lines?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    expect(await screen.findByRole("grid", { name: "Journal lines" })).toBeTruthy();
    const bar = screen.getByRole("toolbar", { name: "Filters" });
    const field = (name: string) => {
      fireEvent.click(within(bar).getByRole("button", { name: "Filter" }));
      fireEvent.click(
        within(screen.getByRole("dialog", { name: "Filter" })).getByRole("button", { name }),
      );
      return screen.getByRole("dialog", { name: `${name} filter` });
    };

    const contract = field("Contract");
    // The options arrive by their own read; typing opens the list (DS-CMP-21).
    await waitFor(() => {
      fireEvent.change(within(contract).getByRole("combobox"), { target: { value: "10003" } });
      expect(screen.getByRole("option", { name: "SF-ORD-10003" })).toBeTruthy();
    });
    fireEvent.mouseDown(screen.getByRole("option", { name: "SF-ORD-10003" }));
    fireEvent.click(within(contract).getByRole("button", { name: "Apply" }));
    await waitFor(() => {
      expect(router.state.location.search).toContain(`f.contract=is:${CONTRACT_ID}`);
    });
    await waitFor(() => {
      expect(requested.at(-1)?.searchParams.get("contract")).toBe(CONTRACT_ID);
    });
    expect(
      within(bar).getByRole("button", { name: "Contract is SF-ORD-10003, edit filter" }),
    ).toBeTruthy();

    const batches = field("Batch");
    expect(
      within(batches)
        .getAllByRole("checkbox")
        .map((box) => box.closest("label")?.textContent),
    ).toEqual(["1 · 1", "1 · 2"]);
    fireEvent.click(within(batches).getByRole("checkbox", { name: "1 · 2" }));
    fireEvent.click(within(batches).getByRole("button", { name: "Apply" }));
    await waitFor(() => {
      expect(router.state.location.search).toContain(`f.batch=is:${second.id}`);
    });
    await waitFor(() => {
      expect(requested.at(-1)?.searchParams.get("batch_id")).toBe(second.id);
    });
    expect(within(bar).getByRole("button", { name: "Batch is 1 · 2, edit filter" })).toBeTruthy();
    // Every request of the grid carried ids, never typed text.
    for (const url of requested) {
      for (const name of ["contract", "batch_id"]) {
        expect(url.searchParams.get(name) ?? CONTRACT_ID).toMatch(/^[0-9a-f-]{36}$/);
      }
    }
  });

  it("a batch of another run in the link is dropped as an unrecognised value (W-19)", async () => {
    const requested: URL[] = [];
    serveRun(run());
    server.use(
      http.get(apiUrl("/api/v1/journal-runs/:runId/lines"), ({ request }) => {
        requested.push(new URL(request.url));
        return HttpResponse.json({ items: [], next_cursor: null });
      }),
      http.get(apiUrl("/api/v1/contracts"), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
    const { router } = renderApp(
      `/journals/runs/${RUN_ID}/lines?${CONTEXT}&f.batch=is:not-a-batch-of-this-run`,
      { me: MAYA, screenRoutes: SCREEN_ROUTES },
    );

    expect(await screen.findByRole("grid", { name: "Journal lines" })).toBeTruthy();
    expect(
      await screen.findByText("Some filters in the link were not recognised and were removed."),
    ).toBeTruthy();
    await waitFor(() => {
      expect(router.state.location.search).not.toContain("f.batch");
    });
    expect(requested.every((url) => url.searchParams.get("batch_id") === null)).toBe(true);
  });

  it("cancelled banner from the audit event", async () => {
    serveRun(run({ state: "cancelled", cancelled_at: "2026-09-06T08:31:00Z" }));
    const requested: URL[] = [];
    server.use(
      http.get(apiUrl("/api/v1/audit-events"), ({ request }) => {
        requested.push(new URL(request.url));
        return HttpResponse.json({
          items: [
            {
              id: "4b3a2c1d-0e9f-4a8b-9c7d-6e5f4a3b2c1d",
              action: "journal_run.cancel",
              outcome: "SUCCESS",
              actor: { id: ACTOR.id, display_name: "Priya Raman", kind: "USER" },
              on_behalf_of: null,
              occurred_at: "2026-09-06T08:30:00Z",
              comment: "Wrong period selected for this run.",
              detail: {},
            },
          ],
          next_cursor: null,
        });
      }),
    );
    // The banner's name and reason are an audit event: read with `audit.read` for all entities
    // (SCREENS_B §3.2 rev 1.68), which the Revenue Accountant holds.
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, {
      me: signedInMe({ permissions: [...MAYA.permissions, "audit.read"] }),
      screenRoutes: SCREEN_ROUTES,
    });

    // D-87 L6-5-Q-6: actor, time and reason of the `journal_run.cancel` audit event.
    expect(
      await screen.findByText(
        "Journal run JR-000209 was cancelled by Priya Raman on 06 Sep 2026 08:30 UTC: Wrong period selected for this run.",
      ),
    ).toBeTruthy();
    expect(requested[0]?.searchParams.get("object_type")).toBe("journal_run");
    expect(requested[0]?.searchParams.get("object_id")).toBe(RUN_ID);
    // SCREENS_B §3.2 action bar: a cancelled run offers no command; "Close run" stays absent.
    expect(screen.queryByRole("button", { name: "Submit for approval" })).toBeNull();
    expect(screen.queryByText("Close run")).toBeNull();
  });

  it("approval meta shows the request number", async () => {
    serveRun(run({ approval_request_id: REQUEST_ID }));
    server.use(
      http.get(apiUrl("/api/v1/approvals/:requestId"), () =>
        HttpResponse.json({ id: REQUEST_ID, request_no: "APR-000512", status: "PENDING" }),
      ),
    );
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    // D-87 L6-5-Q-6: "Approval" names `request_no` from `GET /approvals/{id}` and links to SF-12:request.
    const link = await screen.findByRole("link", { name: "APR-000512" });
    expect(link.getAttribute("href")).toBe(`/approvals/requests/${REQUEST_ID}`);
    expect(screen.getByText("Approval", { selector: "dt" })).toBeTruthy();
  });

  it("run journals cut-off behind advanced", async () => {
    expect(parseCutoff("", 0)).toEqual({ value: null, error: null });
    const now = instantMs("2026-09-16T12:00:00Z");
    expect(parseCutoff("2026-09-05 10:00", now)).toEqual({
      value: "2026-09-05T10:00:00Z",
      error: null,
    });
    expect(parseCutoff("2026-09-05T10:00:00+02:00", now).value).toBe("2026-09-05T10:00:00+02:00");
    expect(parseCutoff("2026-09-17 00:00", now).error).toBe(
      "Enter a time that is not in the future.",
    );
    expect(parseCutoff("05/09/2026", now).error).toBe("Enter a time as YYYY-MM-DD HH:mm in UTC.");

    const posted: Record<string, unknown>[] = [];
    serveShell();
    server.use(
      http.get(apiUrl("/api/v1/journal-runs"), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get(apiUrl("/api/v1/periods"), () =>
        HttpResponse.json({
          items: [
            {
              id: "1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e08",
              entity: AVM_US,
              book: "ASC606",
              period: {
                id: "2c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e08",
                period_key: "FY2026-P08",
                name: "Aug 2026",
                fiscal_year: 2026,
                period_no: 8,
                quarter_no: 3,
                start_date: "2026-08-01",
                end_date: "2026-08-31",
              },
              state: "open",
              is_first_open: true,
              row_version: 1,
              state_changed_at: "2026-09-01T00:00:00Z",
              close_run: null,
              current_lock: null,
              blockers: {},
            },
          ],
          next_cursor: null,
        }),
      ),
      http.post(apiUrl("/api/v1/journal-runs"), async ({ request }) => {
        posted.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json(
          { id: "5e4d3c2b-1a0f-4e9d-8c7b-6a5f4e3d2c1b", kind: "JOURNAL_RUN_CALCULATE" },
          {
            status: 202,
            headers: { Location: "/api/v1/jobs/5e4d3c2b-1a0f-4e9d-8c7b-6a5f4e3d2c1b" },
          },
        );
      }),
      http.get(apiUrl("/api/v1/jobs/:jobId"), () =>
        HttpResponse.json({
          id: "5e4d3c2b-1a0f-4e9d-8c7b-6a5f4e3d2c1b",
          kind: "JOURNAL_RUN_CALCULATE",
          state: "RUNNING",
          progress: null,
          started_at: "2026-09-16T11:59:00Z",
          finished_at: null,
          problem: null,
          result: null,
        }),
      ),
    );
    renderApp(`/journals?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    // D-87 L6-5-Q-8: saved views of screen code SF-06.
    expect(await screen.findByTestId("SF-06-saved-view")).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "Run journals" }));
    const dialog = await screen.findByRole("dialog", { name: "Run journals" });
    const advanced = within(dialog).getByTestId("SF-06-run-form-advanced");
    expect(advanced.hasAttribute("open")).toBe(false);
    fireEvent.click(within(advanced).getByText("Advanced"));
    const cutoff = within(advanced).getByRole("textbox", { name: /^Cut-off known at/ });
    fireEvent.change(cutoff, { target: { value: "2026-09-05 10:00" } });
    await waitFor(() => {
      expect(within(dialog).getByRole("combobox", { name: /^Period/ }).textContent).toContain(
        "Aug 2026",
      );
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Calculate journals" }));
    await waitFor(() => {
      expect(posted[0]).toEqual({
        entity_code: "AVM-US",
        book: "ASC606",
        period_key: "FY2026-P08",
        cutoff_known_at: "2026-09-05T10:00:00Z",
      });
    });
  });

  it("drawer title side and amount of a journal line", () => {
    // ENGINE_SPEC_B S14-R-18 nets the two currencies independently, so a journal line can carry
    // functional amounts only (every FX remeasurement) or a transaction debit with a functional
    // credit (an opposed delta, S14-R-10). It is titled by its transaction amount when it has one.
    const amounts = (
      debitTxn: string,
      creditTxn: string,
      debitFunctional: string,
      creditFunctional: string,
    ) =>
      ({
        debit_txn: money(debitTxn),
        credit_txn: money(creditTxn),
        debit_functional: money(debitFunctional, "GBP"),
        credit_functional: money(creditFunctional, "GBP"),
      }) as JournalLine;
    expect(titledAmount(amounts("1000.00", "0.00", "810.00", "0.00"))).toEqual({
      credit: false,
      amount: money("1000.00"),
    });
    expect(titledAmount(amounts("0.00", "295.69", "0.00", "239.51"))).toEqual({
      credit: true,
      amount: money("295.69"),
    });
    // Functional amounts only: the functional side and amount, not a transaction credit of 0.00.
    expect(titledAmount(amounts("0.00", "0.00", "960.00", "0.00"))).toEqual({
      credit: false,
      amount: money("960.00", "GBP"),
    });
    expect(titledAmount(amounts("0.00", "0.00", "0.00", "960.00"))).toEqual({
      credit: true,
      amount: money("960.00", "GBP"),
    });
    // A transaction debit with a functional credit: the transaction side.
    expect(titledAmount(amounts("1000.00", "0.00", "0.00", "190.00"))).toEqual({
      credit: false,
      amount: money("1000.00"),
    });
  });

  it("source lines drawer docks beside the page and filters by contract", async () => {
    const lineId = "6a5b4c3d-2e1f-4a0b-9c8d-000000000088";
    const otherContract = "3d2c1b0a-9f8e-4d7c-8b6a-000000010003";
    // A contract of an entity the reader does not hold: the drill names no external id for it.
    const outsideContract = "3d2c1b0a-9f8e-4d7c-8b6a-000000010009";
    const contractReads: string[] = [];
    const journalLine: JournalLine = {
      id: lineId,
      je_no: "JE-AVM-US-000088",
      je_type: "automated",
      journal_batch_id: batch(1, "exported").id,
      source_grouping_sha256: "7".repeat(64),
      line_no: 3,
      account: { id: "7f6e5d4c-3b2a-4c1d-9e8f-000000004010", code: "4010", name: "Revenue" },
      account_role: "REVENUE",
      dimensions: {},
      txn_currency: "USD",
      debit_txn: money("0.00"),
      credit_txn: money("295.69"),
      debit_functional: money("0.00"),
      credit_functional: money("295.69"),
      contract: null,
      obligation_key: null,
      legacy_key: null,
      counterparty_entity: null,
      origin_period_key: null,
      is_post_close: false,
      fx_rate_ids: [],
      memo: null,
      source_line_count: 2,
      links: { drill: `/api/v1/journal-lines/${lineId}/drill` },
    };
    const subledger = (
      id: string,
      contractId: string,
      externalId: string | null,
      scheduleLineId: string | null,
    ) =>
      ({
        id,
        account: journalLine.account,
        account_role: "REVENUE",
        amount_functional: money("-147.85"),
        amount_txn: money("-147.85"),
        book: "ASC606",
        contract_event_id: null,
        // API-S-SubledgerLine (04 §16.7; item JRN-DRILL-CONTRACT-NAME-1): the row names its contract.
        contract_external_id: externalId,
        contract_id: contractId,
        contract_version_id: null,
        dr_cr: "C",
        effective_date: "2026-08-31",
        entity: AVM_US,
        entry_kind: "REVENUE_RECOGNITION",
        entry_no: 1,
        fx_rate: null,
        is_post_reopen: false,
        journal_run_id: RUN_ID,
        links: {
          explain: `/api/v1/explain/subledger_line/${id}/amount`,
          event: null,
          schedule_line: null,
          source_row: null,
        },
        obligation_id: "9c8b7a6f-5e4d-4c3b-8a2f-000000000001",
        origin_period_key: null,
        period_key: "FY2026-P08",
        posting_id: "1f2e3d4c-5b6a-4978-8f6e-5d4c3b2a1f0e",
        posting_kind: "ENGINE_COMPUTE",
        reason_code: null,
        recorded_at: "2026-09-05T10:00:00Z",
        schedule_line_id: scheduleLineId,
      }) as unknown as SubledgerLine;
    serveRun(run());
    server.use(
      http.get(apiUrl("/api/v1/journal-runs/:runId/lines"), () =>
        HttpResponse.json({ items: [journalLine], next_cursor: null }),
      ),
      http.get(apiUrl("/api/v1/journal-lines/:lineId/drill"), () =>
        HttpResponse.json({
          items: [
            subledger(
              "2a1b0c9d-8e7f-4a6b-9c5d-000000000001",
              "3d2c1b0a-9f8e-4d7c-8b6a-000000010001",
              "SF-ORD-10001",
              "5f4e3d2c-1b0a-4f9e-8d7c-000000000001",
            ),
            subledger("2a1b0c9d-8e7f-4a6b-9c5d-000000000002", otherContract, "SF-ORD-10003", null),
            subledger("2a1b0c9d-8e7f-4a6b-9c5d-000000000003", outsideContract, null, null),
          ],
          next_cursor: null,
        }),
      ),
      // "Open schedule line" lands on SF-04, which reads the waterfall definition.
      http.get(apiUrl("/api/v1/report-definitions/:code"), () =>
        problemResponse("not-found", 404, "Report definition not found"),
      ),
      // The drawer once read every distinct contract for its name — 91 reads, 18.8 s together, for
      // one line of the seeded tenant. A read would now show its answer instead of the drill's.
      http.get(apiUrl("/api/v1/contracts/:contractId"), ({ params }) => {
        contractReads.push(String(params.contractId));
        return HttpResponse.json({ id: params.contractId, external_id: "READ-FROM-CONTRACT" });
      }),
    );
    const { router } = renderApp(
      `/journals/runs/${RUN_ID}/lines?${CONTEXT}&drawer=source-lines&row=${lineId}`,
      { me: MAYA, screenRoutes: SCREEN_ROUTES },
    );

    const drawer = await screen.findByTestId("SF-06-drawer-source-lines");
    // SCREENS_B §3.3: the drawer docks beside the page, not inside the run frame under the grid.
    const page = await screen.findByTestId("SF-06-page");
    expect(page.contains(drawer)).toBe(false);
    expect(drawer.closest("aside")).not.toBeNull();
    const grid = within(drawer).getByRole("grid", { name: "Source lines" });
    expect(await within(grid).findByText("SF-ORD-10003")).toBeTruthy();
    expect(within(grid).getByText("SF-ORD-10001")).toBeTruthy();
    // The names are the drill's own, the row without one reads a dash, and no contract is read.
    expect(
      [...grid.querySelectorAll('[role="row"] [data-column="contract"]')]
        .filter((cell) => cell.getAttribute("role") !== "columnheader")
        .map((cell) => cell.textContent),
    ).toEqual(["SF-ORD-10001", "SF-ORD-10003", "—No contract"]);
    expect(contractReads).toEqual([]);
    // SCREENS_B §3.3: the drawer opens on what it explains — whose line, which side, how much — and
    // the contract is the row header, the column the grid pins (DS-CMP-10).
    expect(
      within(grid)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual([
      "Contract",
      "Debit or credit",
      "Amount (txn)",
      "Effective",
      "Entry kind",
      "Posting kind",
      "Account role",
      "Amount (functional)",
      "FX rate",
      "Origin period",
      "Post-reopen",
      "Reason",
      "Recorded",
      "Actions",
    ]);
    expect(
      within(grid)
        .getAllByRole("rowheader")
        .map((cell) => cell.getAttribute("data-column")),
    ).toEqual(["contract", "contract", "contract"]);
    // A line without a contract shows the dash and names its row "No contract" (§3.3 rev 1.81): the
    // kit's dash reads "No value", which names a row by nothing.
    const unnamed = within(grid).getByRole("rowheader", { name: "No contract" });
    expect(unnamed.querySelector('[aria-hidden="true"]')?.textContent).toBe("—");
    expect(within(grid).queryByRole("rowheader", { name: "No value" })).toBeNull();

    // D-87 L6-5-Q-9: the Contract filter applies client-side by external id.
    const field = within(drawer).getByRole("textbox", { name: /^Contract/ });
    fireEvent.change(field, { target: { value: "sf-ord-10003" } });
    fireEvent.submit(field);
    await waitFor(() => {
      expect(within(grid).getByText("SF-ORD-10003")).toBeTruthy();
      expect(within(grid).queryByText("SF-ORD-10001")).toBeNull();
    });
    expect(within(drawer).queryByRole("button", { name: "Open event" })).toBeNull();

    fireEvent.change(field, { target: { value: "" } });
    fireEvent.submit(field);
    const open = await within(grid).findByRole("button", { name: "Open schedule line" });
    expect(within(grid).getAllByRole("button", { name: "Open schedule line" })).toHaveLength(1);
    fireEvent.click(open);
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/schedules");
    });
    const search = new URLSearchParams(router.state.location.search);
    expect(search.get("layout")).toBe("lines");
    expect(search.get("period")).toBe("FY2026-P08");
    expect(search.get("obligation")).toBe("9c8b7a6f-5e4d-4c3b-8a2f-000000000001");
  });

  it("batch attempts and last error", async () => {
    // D-87 L6-5-Q-1: the generated JournalBatchOut carries attempt_count and last_error (T-SL-07).
    const failing: JournalBatch = {
      ...batch(1, "approved"),
      attempt_count: 2,
      last_error: "Account 5003 is not in the chart of accounts.",
    };
    serveRun(run({ state: "approved", approved_at: "2026-09-05T12:00:00Z", batches: [failing] }));
    server.use(
      http.get(apiUrl("/api/v1/journal-runs/:runId/batches"), () =>
        HttpResponse.json(
          { items: [failing], next_cursor: null },
          { headers: { "X-Erev-Total-Count": "1" } },
        ),
      ),
      http.get(apiUrl("/api/v1/journal-batches/:batchId"), () => HttpResponse.json(failing)),
    );
    renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}&drawer=batch&row=${failing.id}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const drawer = await screen.findByTestId("SF-06-drawer-batch");
    const definition = async (label: string) =>
      (await within(drawer).findByText(label, { selector: "dt" })).closest("div")?.textContent;
    expect(await definition("Attempts")).toBe("Attempts2");
    expect(await definition("Last error")).toBe(
      "Last errorAccount 5003 is not in the chart of accounts.",
    );
  });

  it("export toasts", async () => {
    // SCREENS_B §3.2 Export; D-89 L7-3-Q-31 (c): a succeeded export job answers with the acknowledgement
    // counts of the refreshed run; the same command started from "Export again" posts nothing again.
    const jobIds = ["6f5e4d3c-2b1a-4f0e-9d8c-000000000001", "6f5e4d3c-2b1a-4f0e-9d8c-000000000002"];
    let current = run({
      state: "approved",
      approved_at: "2026-09-05T12:00:00Z",
      batches: [batch(1, "approved"), batch(2, "approved")],
    });
    const exported = run({
      state: "exported",
      approved_at: "2026-09-05T12:00:00Z",
      exported_at: "2026-09-06T09:00:00Z",
      batches: [batch(1, "acknowledged"), batch(2, "exported")],
    });
    const posted: unknown[] = [];
    serveShell();
    server.use(
      http.get(apiUrl("/api/v1/journal-runs/:runId"), () => HttpResponse.json(current)),
      http.get(apiUrl("/api/v1/journal-runs/:runId/summary"), () =>
        HttpResponse.json(BALANCED_SUMMARY),
      ),
      http.post(apiUrl("/api/v1/journal-runs/:runId/export"), async ({ request }) => {
        posted.push(await request.json());
        const jobId = jobIds[posted.length - 1] ?? "";
        current = exported;
        return HttpResponse.json(
          { id: jobId, kind: "JOURNAL_EXPORT" },
          { status: 202, headers: { Location: `/api/v1/jobs/${jobId}` } },
        );
      }),
      http.get(apiUrl("/api/v1/jobs/:jobId"), ({ params }) =>
        HttpResponse.json({
          id: String(params.jobId),
          kind: "JOURNAL_EXPORT",
          state: "SUCCEEDED",
          progress: null,
          started_at: "2026-09-06T08:59:00Z",
          finished_at: "2026-09-06T09:00:00Z",
          problem: null,
          result: null,
        }),
      ),
    );
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    fireEvent.click(await screen.findByRole("button", { name: "Export journals" }));
    const first = await screen.findByRole("alertdialog", {
      name: /^Export journal run JR-000209 to /,
    });
    fireEvent.click(within(first).getByRole("button", { name: "Export" }));
    expect(
      await screen.findByText("Journal run JR-000209 exported. 1 of 2 batches acknowledged."),
    ).toBeTruthy();
    expect(posted).toEqual([{ adapter: "CSV" }]);

    // SCREENS_B §3.2 Exported: no primary export action; the overflow offers "Export again".
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Export journals" })).toBeNull();
    });
    fireEvent.click(screen.getByRole("button", { name: "More actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Export again" }));
    const again = await screen.findByRole("alertdialog", {
      name: /^Export journal run JR-000209 to /,
    });
    fireEvent.click(within(again).getByRole("button", { name: "Export" }));
    expect(
      await screen.findByText("The export was already recorded. No batch was posted again."),
    ).toBeTruthy();
    expect(posted).toEqual([{ adapter: "CSV" }, { adapter: "CSV" }]);
  });

  it("a failed run is cancelled through its job", async () => {
    const world: ExitWorld = {
      run: failedRun([erp(1, "failed"), erp(2, "failed")]),
      job: exitJob("CANCEL", "RUNNING"),
      listed: [],
      posted: [],
    };
    const served = serveExits(world);
    accept("/api/v1/journal-runs/:runId/cancel", world, "CANCEL", () => {
      world.listed = [exitJob("CANCEL", "QUEUED")];
    });
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    // SCREENS_B §3.2 action bar, Failed (rev 1.71): the overflow offers the cancel, and the dialog says
    // that the ledger is asked first.
    expect(await screen.findByRole("button", { name: "Download batch files" })).toBeTruthy();
    const dialog = await openCancel();
    expect(within(dialog).getByText(LEDGER_FIRST)).toBeTruthy();
    expect(served.activeJobReads).toHaveLength(1);
    confirmCancel(dialog, "NetSuite rejects account 5003.");

    // The accepted command closes the dialog; the page follows the job and offers nothing meanwhile.
    expect(
      await screen.findByRole("progressbar", { name: "Cancelling journal run JR-000209" }),
    ).toBeTruthy();
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(world.posted).toEqual([{ reason: "NetSuite rejects account 5003." }]);
    // The run's active jobs are read again at once: read before the command, "none" would stay cached
    // for the frame of the next tab.
    await waitFor(() => {
      expect(served.activeJobReads.length).toBeGreaterThan(1);
    });
    expect(screen.queryByRole("button", { name: "Retry export" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Download batch files" })).toBeNull();
    // "History" alone is left, and it needs `audit.read` for all entities (rev 1.68): a member without
    // it is left no item, and a menu without an item is not rendered.
    expect(screen.queryByRole("button", { name: "More actions" })).toBeNull();

    // `result.outcome` CANCELLED: the run is read again and the toast says so.
    world.run = run({
      state: "cancelled",
      approved_at: "2026-09-05T12:00:00Z",
      cancelled_at: "2026-09-06T09:10:05Z",
      batches: [erp(1, "cancelled"), erp(2, "cancelled")],
    });
    world.listed = [];
    world.job = exitJob("CANCEL", "SUCCEEDED", {
      result: { href: RUN_HREF, counts: { asked: 2, held: 0, cancelled: 1 }, outcome: "CANCELLED" },
    });
    expect(
      await screen.findByText("Journal run JR-000209 was cancelled.", {}, NEXT_POLL),
    ).toBeTruthy();
    expect(await screen.findByTestId("SF-06-banner-cancelled")).toBeTruthy();
    expect(screen.queryByRole("progressbar", { name: /^Cancelling/ })).toBeNull();
    expect(screen.queryByTestId("SF-06-banner-exit-refused")).toBeNull();
  });

  it("a cancel its job refuses says why on the page", async () => {
    // PRD ERR-73: the ledger holds a failed batch, which is acknowledged; the run is not cancelled.
    const held =
      "NetSuite production holds batch erev:avenmoor:JR-000209:1:1 as JE-88412. The batch is acknowledged and journal run JR-000209 is not cancelled.";
    const decided: ExitWorld = {
      run: failedRun([erp(1, "failed"), erp(2, "failed")]),
      job: exitJob("CANCEL", "SUCCEEDED_WITH_EXCEPTIONS", {
        result: {
          href: RUN_HREF,
          counts: { asked: 2, held: 1, cancelled: 0 },
          outcome: "NOT_CANCELLED",
          refusal: refusal(held),
        },
      }),
      listed: [],
      posted: [],
    };
    const served = serveExits(decided);
    accept("/api/v1/journal-runs/:runId/cancel", decided, "CANCEL", () => {
      decided.run = failedRun([erp(1, "acknowledged"), erp(2, "failed")]);
      // The job writes its decision: the DENIED `journal_run.cancel` event of the run (04 §16.7).
      decided.events = [
        {
          id: "4b3a2c1d-0e9f-4a8b-9c7d-0000000000d1",
          action: "journal_run.cancel",
          outcome: "DENIED",
          actor: { id: null, display_name: "System", kind: "SYSTEM" },
          on_behalf_of: ACTOR,
          occurred_at: "2026-09-06T09:10:05Z",
          comment: "NetSuite rejects account 5003.",
          detail: { problem: "invalid-transition", rule_id: "E-34", message: held, job_id: JOB_ID },
        },
      ];
    });
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}&drawer=history`, {
      me: READS_AUDIT,
      screenRoutes: SCREEN_ROUTES,
    });

    const history = await screen.findByRole("complementary", { name: "History" });
    expect(
      await within(history).findByText(
        "No activity yet. Changes, approvals and calculations appear here.",
      ),
    ).toBeTruthy();
    confirmCancel(await openCancel(), "NetSuite rejects account 5003.");
    const banner = await screen.findByTestId("SF-06-banner-exit-refused");
    expect(within(banner).getByRole("alert")).toBeTruthy();
    expect(
      within(banner).getByRole("heading", { name: "Journal run JR-000209 was not cancelled" }),
    ).toBeTruthy();
    expect(within(banner).getByText(held)).toBeTruthy();
    expect(banner.textContent).not.toContain("Reference");
    // The run was read again: the batch the ledger holds is acknowledged by then.
    await waitFor(() => {
      expect(figure(screen.getByTestId("SF-06-kpi-strip"), "Batches acknowledged")).toBe("1 of 2");
    });
    expect(screen.queryByRole("progressbar", { name: /^Cancelling/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Download batch files" })).toBeTruthy();
    // No job was listed, so nothing polls: the frame's first read, the one at the accepted command and
    // the one at the job's end.
    await waitFor(() => {
      expect(served.activeJobReads).toHaveLength(3);
    });
    // The open History drawer is read again too: it holds the job's entry.
    expect(await within(history).findByText("was refused: cancelled the run")).toBeTruthy();
    expect(within(history).getByText(held)).toBeTruthy();
    cleanup();

    // A ledger that could not be reached: the job ends FAILED after its last attempt, with its problem.
    const unreachable =
      "The ledger could not be reached, so nothing was changed: NetSuite did not answer within 30 seconds. Ask again when the ledger answers.";
    const failed: ExitWorld = {
      run: failedRun([erp(1, "failed"), erp(2, "failed")]),
      job: exitJob("CANCEL", "FAILED", { problem: refusal(unreachable) }),
      listed: [],
      posted: [],
    };
    serveExits(failed);
    accept("/api/v1/journal-runs/:runId/cancel", failed, "CANCEL");
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    confirmCancel(await openCancel(), "NetSuite rejects account 5003.");
    const second = await screen.findByTestId("SF-06-banner-exit-refused");
    expect(
      within(second).getByRole("heading", { name: "Journal run JR-000209 was not cancelled" }),
    ).toBeTruthy();
    expect(within(second).getByText(unreachable)).toBeTruthy();
    expect(within(second).getByText("Reference 6f5e4d3c.")).toBeTruthy();
    // Nothing was changed: the command is offered again.
    fireEvent.click(screen.getByRole("button", { name: "More actions" }));
    const again = await screen.findByRole("menuitem", { name: "Cancel journal run" });
    expect(again.getAttribute("aria-disabled")).toBeNull();
  });

  it("a refused cancel command stays in the dialog", async () => {
    const underWay = "A cancellation of this journal run is already under way.";
    const world: ExitWorld = { run: failedRun([failedCsv(1)]), job: null, listed: [], posted: [] };
    serveExits(world);
    let lost = false;
    server.use(
      http.post(apiUrl("/api/v1/journal-runs/:runId/cancel"), () =>
        lost ? HttpResponse.error() : stateProblem(underWay),
      ),
    );
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    // A run whose failed batches are all CSV has no ledger to ask: the first consequence stands.
    const dialog = await openCancel();
    expect(within(dialog).getByText(PLAIN_CANCEL)).toBeTruthy();
    expect(within(dialog).queryByText(LEDGER_FIRST)).toBeNull();
    confirmCancel(dialog, "The chart will not take account 5003.");

    // The command's own refusal is a sentence ready to show, once, where it was asked.
    expect(await within(dialog).findByText(underWay)).toBeTruthy();
    expect(within(dialog).getAllByText(underWay)).toHaveLength(1);
    expect(within(dialog).getByText("Action not available in this state")).toBeTruthy();
    expect(screen.getByRole("alertdialog", { name: "Cancel journal run JR-000209?" })).toBe(dialog);
    expect(screen.queryByRole("progressbar", { name: /^Cancelling/ })).toBeNull();
    expect(screen.queryByTestId("SF-06-banner-exit-refused")).toBeNull();

    // A command that got no answer says so and leaves the dialog as it is.
    lost = true;
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel journal run" }));
    expect(await screen.findByText("No answer came back from the server. Try again.")).toBeTruthy();
    expect(screen.getByRole("alertdialog", { name: "Cancel journal run JR-000209?" })).toBe(dialog);
    expect(screen.queryByRole("progressbar", { name: /^Cancelling/ })).toBeNull();
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): the dialogs of a journal run and of
  // its batches show no message of the API at a field, so the banner says every sentence of a refusal;
  // a sentence of `errors[]` that is not also the detail was shown nowhere.
  it("Cancel journal run says every sentence of a refusal that names a member", async () => {
    const sentence = "Say which batch the ledger refused.";
    serveExits({ run: failedRun([failedCsv(1)]), job: null, listed: [], posted: [] });
    server.use(
      http.post(apiUrl("/api/v1/journal-runs/:runId/cancel"), () =>
        refusedWith({ reason: sentence }),
      ),
    );
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    const dialog = await openCancel();
    confirmCancel(dialog, "The chart will not take account 5003.");

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + sentence + REFUSAL_REFERENCE);
  });

  it("Retry export says every sentence of a refusal that names a member", async () => {
    const sentence = "The connection of this batch is disabled.";
    serveExits({
      run: failedRun([erp(1, "exported"), erp(2, "failed")], {
        state: "exported",
        exported_at: "2026-09-06T09:00:00Z",
      }),
      job: null,
      listed: [],
      posted: [],
    });
    server.use(
      http.post(apiUrl("/api/v1/journal-batches/:batchId/retry"), () =>
        refusedWith({ connection_id: sentence }),
      ),
    );
    renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    const grid = await screen.findByRole("grid", { name: "Batches" });
    fireEvent.click(
      await within(grid).findByRole("button", { name: "Retry export for batch 1 · 2" }),
    );
    const retry = await screen.findByRole("alertdialog", { name: "Retry batch 1 · 2?" });
    fireEvent.click(within(retry).getByRole("button", { name: "Retry export" }));

    const banner = await within(retry).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + sentence + REFUSAL_REFERENCE);
  });

  it("cancel is disabled on a failed run partly in a ledger", async () => {
    // SCREENS SCR-PERM-03 with PRD ERR-74: the record itself says that the command would be refused.
    serveExits({
      // Two batches are outside eRev; the API names the first in batch and chunk order.
      run: failedRun([erp(3, "acknowledged"), erp(1, "acknowledged"), erp(2, "failed")]),
      job: null,
      listed: [],
      posted: [],
    });
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    fireEvent.click(await screen.findByRole("button", { name: "More actions" }));
    const item = await screen.findByRole("menuitem", { name: "Cancel journal run" });
    expect(item.getAttribute("aria-disabled")).toBe("true");
    expect(describedBy(item)).toBe(
      "Journal run JR-000209 has a batch that a ledger holds or that was handed out (erev:avenmoor:JR-000209:1:1). Retry its failed batch, or hand it over for manual posting.",
    );
    fireEvent.click(item);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    cleanup();

    // Failed beside exported rolls up to Exported (SMAP-08): the cancel could only be refused.
    serveExits({
      run: run({
        state: "exported",
        approved_at: "2026-09-05T12:00:00Z",
        exported_at: "2026-09-06T09:00:00Z",
        batches: [erp(1, "exported"), erp(2, "failed")],
      }),
      job: null,
      listed: [],
      posted: [],
    });
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(await screen.findByRole("button", { name: "More actions" }));
    expect(await screen.findByRole("menuitem", { name: "Export again" })).toBeTruthy();
    expect(screen.queryByRole("menuitem", { name: "Cancel journal run" })).toBeNull();
  });

  it("the failed banner names the exits offered", async () => {
    const READER = signedInMe({ permissions: ["contract.read", "report.export"] });
    const banner = async (
      value: JournalRun,
      options: Parameters<typeof renderApp>[1] = {},
    ): Promise<string> => {
      cleanup();
      serveExits({ run: value, job: null, listed: [], posted: [] });
      renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, {
        me: MAYA,
        screenRoutes: SCREEN_ROUTES,
        ...options,
      });
      return (await screen.findByTestId("SF-06-banner-export-failed")).textContent ?? "";
    };
    const exits = [EXITS_BOTH, EXITS_CANCEL, EXITS_HAND_OVER];
    const named = (text: string) => exits.filter((sentence) => text.includes(sentence));

    // Both exits: a failed batch of an ERP adapter and nothing of the run outside eRev.
    expect(named(await banner(failedRun([erp(1, "failed")])))).toEqual([EXITS_BOTH]);
    // A CSV batch is never handed over.
    expect(named(await banner(failedRun([failedCsv(1)])))).toEqual([EXITS_CANCEL]);
    // A run that is partly in a ledger cannot be cancelled.
    expect(named(await banner(failedRun([erp(1, "acknowledged"), erp(2, "failed")])))).toEqual([
      EXITS_HAND_OVER,
    ]);
    // A sandbox hands nothing over.
    expect(
      named(
        await banner(failedRun([erp(1, "failed")]), {
          session: signedInSession({
            active_tenant: {
              id: "0b6f3e2d-1c4a-4b8e-9d7f-6a5c4b3e2d1f",
              code: "avenmoor-sandbox",
              display_name: "Avenmoor sandbox",
              kind: "sandbox",
            },
          }),
        }),
      ),
    ).toEqual([EXITS_CANCEL]);
    // A reader who holds neither command is told of neither.
    expect(named(await banner(failedRun([erp(1, "failed")]), { me: READER }))).toEqual([]);
  });

  it("a failed batch of an ERP adapter is handed over", async () => {
    const world: ExitWorld = {
      run: failedRun([erp(1, "acknowledged"), erp(2, "failed"), failedCsv(3)]),
      job: exitJob("HAND_OVER", "RUNNING"),
      listed: [],
      posted: [],
    };
    serveExits(world);
    accept("/api/v1/journal-batches/:batchId/hand-over", world, "HAND_OVER", () => {
      world.listed = [exitJob("HAND_OVER", "QUEUED")];
    });
    renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    // SCREENS_B §3.4 Actions (rev 1.71): "Hand over" on a failed batch of an ERP adapter only.
    const grid = await screen.findByRole("grid", { name: "Batches" });
    const handOver = await within(grid).findByRole("button", {
      name: "Hand over batch 1 · 2 for manual posting",
    });
    expect(within(grid).getByRole("button", { name: "Retry export for batch 1 · 3" })).toBeTruthy();
    expect(within(grid).queryByRole("button", { name: /^Hand over batch 1 · [13] / })).toBeNull();
    fireEvent.click(handOver);
    const dialog = await screen.findByRole("alertdialog", {
      name: "Hand over batch 1 · 2 for manual posting?",
    });
    expect(
      within(dialog).getByText(
        "The ledger is asked first whether it holds the batch. If it does not, the batch leaves eRev as its file and is not sent again: download the file, post it in the ledger by hand, then record the ERP reference.",
      ),
    ).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Hand over" }));

    // The frame follows the job; the commands of the failed batches wait for its end.
    expect(
      await screen.findByRole("progressbar", { name: "Handing over batch 1 · 2" }),
    ).toBeTruthy();
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(world.posted).toEqual([null]);
    await waitFor(() => {
      expect(within(grid).queryByRole("button", { name: /^Hand over batch / })).toBeNull();
    });
    expect(within(grid).queryByRole("button", { name: /^Retry export for batch / })).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry export" })).toBeNull();

    // HANDED_OVER: the batch is exported with its file and waits for its ERP reference.
    world.run = failedRun([erp(1, "acknowledged"), erp(2, "exported"), failedCsv(3)], {
      state: "exported",
    });
    world.listed = [];
    world.job = exitJob("HAND_OVER", "SUCCEEDED", {
      result: {
        href: RUN_HREF,
        counts: { asked: 1, held: 0, handed_over: 1 },
        outcome: "HANDED_OVER",
      },
    });
    // The toast says the outcome alone (rev 1.77): a toast holds two lines, and the instruction, which
    // the confirmation states, was cut in it.
    expect(await screen.findByText("Batch 1 · 2 was handed over.", {}, NEXT_POLL)).toBeTruthy();
    expect(
      await within(grid).findByRole("button", { name: "Record ERP reference for batch 1 · 2" }),
    ).toBeTruthy();
    expect(screen.queryByRole("progressbar", { name: /^Handing over/ })).toBeNull();
    expect(
      await within(grid).findByRole("button", { name: "Retry export for batch 1 · 3" }),
    ).toBeTruthy();
  });

  it("a hand-over its job refuses says why on the page", async () => {
    const underWay = "A hand-over of this batch is already under way.";
    const held =
      "NetSuite production holds batch erev:avenmoor:JR-000209:1:2 as JE-88413. The batch is acknowledged and is not handed over.";
    const world: ExitWorld = {
      run: failedRun([erp(1, "acknowledged"), erp(2, "failed")]),
      job: exitJob("HAND_OVER", "SUCCEEDED_WITH_EXCEPTIONS", {
        result: {
          href: RUN_HREF,
          counts: { asked: 1, held: 1, handed_over: 0 },
          outcome: "NOT_HANDED_OVER",
          refusal: refusal(held),
        },
      }),
      listed: [],
      posted: [],
    };
    serveExits(world);
    let answer: "lost" | "refused" | "accepted" = "lost";
    server.use(
      http.post(apiUrl("/api/v1/journal-batches/:batchId/hand-over"), () => {
        if (answer === "lost") {
          return HttpResponse.error();
        }
        if (answer === "refused") {
          return stateProblem(underWay);
        }
        world.run = run({
          state: "acknowledged",
          approved_at: "2026-09-05T12:00:00Z",
          acknowledged_at: "2026-09-06T09:10:05Z",
          batches: [erp(1, "acknowledged"), erp(2, "acknowledged")],
        });
        return HttpResponse.json(exitJob("HAND_OVER", "QUEUED"), {
          status: 202,
          headers: { Location: `/api/v1/jobs/${JOB_ID}` },
        });
      }),
    );
    renderApp(
      `/journals/runs/${RUN_ID}/batches?${CONTEXT}&drawer=batch&row=${erp(2, "failed").id}`,
      { me: MAYA, screenRoutes: SCREEN_ROUTES },
    );

    const drawer = await screen.findByTestId("SF-06-drawer-batch");
    const lastError = async () =>
      (await within(drawer).findByText("Last error", { selector: "dt" })).closest("div")
        ?.textContent;
    expect(await lastError()).toBe("Last errorNetSuite: account 5003 is inactive.");
    const grid = await screen.findByRole("grid", { name: "Batches" });
    fireEvent.click(
      await within(grid).findByRole("button", { name: "Hand over batch 1 · 2 for manual posting" }),
    );
    const dialog = await screen.findByRole("alertdialog", {
      name: "Hand over batch 1 · 2 for manual posting?",
    });
    // A command that got no answer says so; a refusal of the command stays in the dialog, as sent.
    fireEvent.click(within(dialog).getByRole("button", { name: "Hand over" }));
    expect(await screen.findByText("No answer came back from the server. Try again.")).toBeTruthy();
    answer = "refused";
    fireEvent.click(within(dialog).getByRole("button", { name: "Hand over" }));
    expect(await within(dialog).findByText(underWay)).toBeTruthy();
    expect(within(dialog).getByText("Action not available in this state")).toBeTruthy();
    expect(screen.queryByRole("progressbar", { name: /^Handing over/ })).toBeNull();

    // The job's refusal stays on the page: the ledger holds the batch, which is acknowledged instead.
    answer = "accepted";
    fireEvent.click(within(dialog).getByRole("button", { name: "Hand over" }));
    const banner = await screen.findByTestId("SF-06-banner-exit-refused");
    expect(within(banner).getByRole("alert")).toBeTruthy();
    expect(
      within(banner).getByRole("heading", { name: "Batch 1 · 2 was not handed over" }),
    ).toBeTruthy();
    expect(within(banner).getByText(held)).toBeTruthy();
    expect(screen.queryByRole("alertdialog")).toBeNull();
    await waitFor(() => {
      expect(figure(screen.getByTestId("SF-06-kpi-strip"), "Batches acknowledged")).toBe("2 of 2");
    });
    // The open batch drawer is read again too: the batch no longer carries its failure.
    await waitFor(async () => {
      expect(await lastError()).toBe("Last error—");
    });
  });

  it("hand over is disabled in a sandbox", async () => {
    serveExits({
      run: failedRun([erp(1, "acknowledged"), erp(2, "failed")]),
      job: null,
      listed: [],
      posted: [],
    });
    renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`, {
      session: signedInSession({
        active_tenant: {
          id: "0b6f3e2d-1c4a-4b8e-9d7f-6a5c4b3e2d1f",
          code: "avenmoor-sandbox",
          display_name: "Avenmoor sandbox",
          kind: "sandbox",
        },
      }),
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    // SB-R-08: the API answers 403 `sandbox-restricted`, so the control says so and opens nothing.
    const grid = await screen.findByRole("grid", { name: "Batches" });
    const handOver = await within(grid).findByRole("button", {
      name: "Hand over batch 1 · 2 for manual posting",
    });
    expect(handOver.getAttribute("aria-disabled")).toBe("true");
    expect(describedBy(handOver)).toBe("Sandbox workspaces cannot post or export journals.");
    fireEvent.click(handOver);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("record ERP reference on every exported batch", async () => {
    // A batch handed over is `exported` and waits for its ERP reference as a CSV batch does (BR-JE-03).
    serveExits({
      run: failedRun(
        [erp(1, "acknowledged"), erp(2, "exported"), batch(3, "exported"), erp(4, "failed")],
        { state: "exported", exported_at: "2026-09-06T09:00:00Z" },
      ),
      job: null,
      listed: [],
      posted: [],
    });
    renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const grid = await screen.findByRole("grid", { name: "Batches" });
    expect(
      await within(grid).findByRole("button", { name: "Record ERP reference for batch 1 · 2" }),
    ).toBeTruthy();
    expect(
      within(grid).getByRole("button", { name: "Record ERP reference for batch 1 · 3" }),
    ).toBeTruthy();
    expect(
      within(grid).queryByRole("button", { name: /^Record ERP reference for batch 1 · [14]$/ }),
    ).toBeNull();
  });

  it("a refused row command stays in its dialog", async () => {
    // 04 §16.7: a 409 of `retry` and of `acknowledge` is a sentence ready to show, as the 409 of
    // `hand-over` is; the first is what a retry answers while the batch's export message is being sent.
    const beingSent =
      "Batch erev:avenmoor:JR-000209:1:2 is being sent. It cannot be retried while it is being sent. An interrupted export resumes about 15 minutes after it stopped.";
    const notExported = "Only an exported batch can be acknowledged.";
    serveExits({
      run: failedRun([erp(1, "exported"), erp(2, "failed")], {
        state: "exported",
        exported_at: "2026-09-06T09:00:00Z",
      }),
      job: null,
      listed: [],
      posted: [],
    });
    server.use(
      http.post(apiUrl("/api/v1/journal-batches/:batchId/retry"), () => stateProblem(beingSent)),
      http.post(apiUrl("/api/v1/journal-batches/:batchId/acknowledge"), () =>
        stateProblem(notExported),
      ),
    );
    renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const grid = await screen.findByRole("grid", { name: "Batches" });
    fireEvent.click(
      await within(grid).findByRole("button", { name: "Retry export for batch 1 · 2" }),
    );
    const retry = await screen.findByRole("alertdialog", { name: "Retry batch 1 · 2?" });
    fireEvent.click(within(retry).getByRole("button", { name: "Retry export" }));
    expect(await within(retry).findByText(beingSent)).toBeTruthy();
    expect(within(retry).getAllByText(beingSent)).toHaveLength(1);
    expect(within(retry).getByText("Action not available in this state")).toBeTruthy();
    expect(screen.getByRole("alertdialog", { name: "Retry batch 1 · 2?" })).toBe(retry);
    fireEvent.click(within(retry).getByRole("button", { name: "Cancel" }));

    fireEvent.click(
      await within(grid).findByRole("button", { name: "Record ERP reference for batch 1 · 1" }),
    );
    const record = await screen.findByRole("dialog", {
      name: "Record ERP reference for batch 1 · 1",
    });
    fireEvent.change(within(record).getByRole("textbox", { name: "ERP document reference" }), {
      target: { value: "JE-88412" },
    });
    fireEvent.click(within(record).getByRole("button", { name: "Record reference" }));
    expect(await within(record).findByText(notExported)).toBeTruthy();
    expect(within(record).getByText("Action not available in this state")).toBeTruthy();
    expect(screen.getByRole("dialog", { name: "Record ERP reference for batch 1 · 1" })).toBe(
      record,
    );
  });

  it("a refused download saves nothing", async () => {
    const differs =
      "Batch erev:avenmoor:JR-000209:1:1 differs from what was calculated and approved: line count 12 stored, 13 found. It cannot be downloaded.";
    const files = watchSaves();
    const differing = () =>
      problemResponse("invalid-transition", 409, "Action not available in this state", {
        detail: differs,
        errors: [{ field: "lines", rule_id: "BATCH_RECOUNT", message: differs }],
      });
    let answer: () => Response = differing;
    const requested: string[] = [];
    serveExits({
      run: run({
        state: "acknowledged",
        approved_at: "2026-09-05T12:00:00Z",
        acknowledged_at: "2026-09-06T09:05:00Z",
        batches: [erp(1, "acknowledged")],
      }),
      job: null,
      listed: [],
      posted: [],
    });
    server.use(
      http.get(apiUrl("/api/v1/journal-batches/:batchId/download"), ({ params }) => {
        requested.push(String(params.batchId));
        return answer();
      }),
    );
    renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    // PRD ERR-79 at the row's link: nothing is saved, and the sentence is said whole in a banner of the
    // frame (rev 1.77) — a toast holds two lines and cut it before its differences.
    const grid = await screen.findByRole("grid", { name: "Batches" });
    const link = await within(grid).findByRole("link", { name: "Download batch 1 · 1" });
    expect(link.getAttribute("href")).toBe(
      `/api/v1/journal-batches/${batch(1, "acknowledged").id}/download`,
    );
    fireEvent.click(link);
    const refused = await screen.findByTestId("SF-06-banner-download-refused");
    expect(within(refused).getByRole("alert")).toBeTruthy();
    expect(
      within(refused).getByRole("heading", { name: "Batch 1 · 1 was not downloaded" }),
    ).toBeTruthy();
    expect(within(refused).getByText(differs)).toBeTruthy();
    expect(screen.getAllByText(differs)).toHaveLength(1);
    expect(refused.textContent).not.toContain("Reference");
    expect(files.made()).toBe(0);
    expect(files.saved).toEqual([]);
    // A problem without a sentence shows its title and reference, in place of the banner before it.
    answer = () => problemResponse("forbidden", 403, "You do not have permission for this action");
    fireEvent.click(link);
    expect(await screen.findByText("Reference 0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d.")).toBeTruthy();
    const forbidden = screen.getByTestId("SF-06-banner-download-refused");
    expect(
      within(forbidden).getByRole("heading", { name: "Batch 1 · 1 was not downloaded" }),
    ).toBeTruthy();
    expect(within(forbidden).getByText("You do not have permission for this action")).toBeTruthy();
    expect(screen.queryByText(differs)).toBeNull();
    // A request that got no answer says so in a toast, and the banner of the download before it goes
    // when the next one is asked.
    answer = () => HttpResponse.error();
    fireEvent.click(link);
    expect(await screen.findByText("No answer came back from the server. Try again.")).toBeTruthy();
    expect(screen.queryByTestId("SF-06-banner-download-refused")).toBeNull();
    expect(files.made()).toBe(0);
    expect(files.saved).toEqual([]);
    // A press with a modifier key stays the browser's: the page neither fetches nor cancels it.
    let cancelled: boolean | null = null;
    document.addEventListener(
      "click",
      (event) => {
        cancelled = event.defaultPrevented;
        event.preventDefault();
      },
      { once: true },
    );
    fireEvent.click(link, { ctrlKey: true });
    expect(cancelled).toBe(false);
    expect(requested).toHaveLength(3);

    // A file the API gives is saved under the API's name, from the row and from the header's menu.
    answer = () =>
      new HttpResponse(new Uint8Array([0x50, 0x4b, 0x03, 0x04]), {
        headers: {
          "Content-Type": "application/zip",
          "Content-Disposition": 'attachment; filename="named-by-the-api.zip"',
        },
      });
    fireEvent.click(link);
    await waitFor(() => {
      expect(files.saved).toEqual(["named-by-the-api.zip"]);
    });
    // An answer that names no file is saved under the batch's external id.
    answer = () =>
      new HttpResponse(new Uint8Array([0x50, 0x4b, 0x03, 0x04]), {
        headers: { "Content-Type": "application/zip" },
      });
    fireEvent.click(screen.getByRole("button", { name: "Download batch files" }));
    fireEvent.click(
      await screen.findByRole("menuitem", { name: "Batch 1 · chunk 1 · USD (CSV and manifest)" }),
    );
    await waitFor(() => {
      expect(files.saved).toHaveLength(2);
    });
    expect(files.saved[1]).toBe("erev_avenmoor_JR-000209_1_1.zip");
    expect(files.made()).toBe(2);
    expect(requested).toHaveLength(5);
    // The header's menu says a refusal in the same banner.
    answer = differing;
    fireEvent.click(screen.getByRole("button", { name: "Download batch files" }));
    fireEvent.click(
      await screen.findByRole("menuitem", { name: "Batch 1 · chunk 1 · USD (CSV and manifest)" }),
    );
    const again = await screen.findByTestId("SF-06-banner-download-refused");
    expect(within(again).getByText(differs)).toBeTruthy();
    expect(files.saved).toHaveLength(2);
    expect(requested).toHaveLength(6);
  });

  it("commands of a run are asked for its entity", async () => {
    const OTHER_ENTITY = "0a1b2c3d-4e5f-4a6b-8c7d-000000000002";
    const memberOf = (entity: string) =>
      signedInMe({
        permissions: ["contract.read", "journal.run", "journal.export", "report.export"],
        permission_scopes: {
          "contract.read": "*",
          "journal.run": [entity],
          "journal.export": [entity],
          "report.export": [entity],
        },
      });
    const world = (): ExitWorld => ({
      run: failedRun([erp(1, "failed")]),
      job: null,
      listed: [],
      posted: [],
    });

    // SCREENS SCR-PERM-02 (a): a command held for another entity only is not rendered.
    serveExits(world());
    renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`, {
      me: memberOf(OTHER_ENTITY),
      screenRoutes: SCREEN_ROUTES,
    });
    const grid = await screen.findByRole("grid", { name: "Batches" });
    expect(await within(grid).findByRole("button", { name: "1 · 1" })).toBeTruthy();
    expect(within(grid).queryByRole("link", { name: /^Download batch / })).toBeNull();
    expect(within(grid).queryByRole("button", { name: /^(Retry export|Hand over) / })).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry export" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Download batch files" })).toBeNull();
    expect(screen.queryByRole("button", { name: "More actions" })).toBeNull();
    cleanup();

    serveExits(world());
    renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`, {
      me: memberOf(AVM_US.id),
      screenRoutes: SCREEN_ROUTES,
    });
    const offered = await screen.findByRole("grid", { name: "Batches" });
    expect(
      await within(offered).findByRole("button", {
        name: "Hand over batch 1 · 1 for manual posting",
      }),
    ).toBeTruthy();
    expect(within(offered).getByRole("link", { name: "Download batch 1 · 1" })).toBeTruthy();
    expect(
      within(offered).getByRole("button", { name: "Retry export for batch 1 · 1" }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Download batch files" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "More actions" }));
    expect(await screen.findByRole("menuitem", { name: "Cancel journal run" })).toBeTruthy();
    expect(screen.queryByRole("menuitem", { name: "History" })).toBeNull();
  });

  it("a frame follows an exit job it did not start", async () => {
    // Each tab mounts the frame: the run's active job, as `GET /jobs` lists it, is followed to its end.
    const sent =
      "Batch erev:avenmoor:JR-000209:1:1 was sent again while the ledger was asked, so nothing was changed. Ask again.";
    // A retry of a batch is a job of the same kind without a mode: the exit is found beside it.
    const retry: Job = {
      ...exitJob("CANCEL", "RUNNING"),
      id: "6f5e4d3c-2b1a-4f0e-9d8c-0000000000ab",
      mode: null,
    };
    const cancelling: ExitWorld = {
      run: failedRun([erp(1, "failed")]),
      job: exitJob("CANCEL", "RUNNING"),
      listed: [retry, exitJob("CANCEL", "RUNNING")],
      posted: [],
    };
    const served = serveExits(cancelling);
    // The API lists a job to the member who started it and to a holder of `audit.read`.
    renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`, {
      me: READS_AUDIT,
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("progressbar", { name: "Cancelling journal run JR-000209" }),
    ).toBeTruthy();
    // SMAP-07 and §3.2 rev 1.71: the queued and running JOURNAL_EXPORT jobs of the run.
    const read = served.activeJobReads[0];
    expect(read?.getAll("kind")).toEqual(["JOURNAL_EXPORT"]);
    expect(read?.getAll("state")).toEqual(["QUEUED", "RUNNING"]);
    expect(read?.get("subject_type")).toBe("journal_run");
    const grid = await screen.findByRole("grid", { name: "Batches" });
    expect(await within(grid).findByRole("link", { name: "Download batch 1 · 1" })).toBeTruthy();
    expect(within(grid).queryByRole("button", { name: /^(Retry export|Hand over) / })).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry export" })).toBeNull();
    // The action bar offers "History" alone, to the reader who may read it.
    fireEvent.click(screen.getByRole("button", { name: "More actions" }));
    expect((await screen.findAllByRole("menuitem")).map((item) => item.textContent)).toEqual([
      "History",
    ]);
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    cancelling.listed = [];
    cancelling.job = exitJob("CANCEL", "SUCCEEDED_WITH_EXCEPTIONS", {
      result: {
        href: RUN_HREF,
        counts: { asked: 1, held: 0, cancelled: 0 },
        outcome: "NOT_CANCELLED",
        refusal: refusal(sent),
      },
    });
    const banner = await screen.findByTestId("SF-06-banner-exit-refused", {}, NEXT_POLL);
    expect(
      within(banner).getByRole("heading", { name: "Journal run JR-000209 was not cancelled" }),
    ).toBeTruthy();
    expect(within(banner).getByText(sent)).toBeTruthy();
    expect(
      await within(grid).findByRole("button", { name: "Hand over batch 1 · 1 for manual posting" }),
    ).toBeTruthy();
    cleanup();

    // API-S-Job names no batch: a hand-over this frame did not start is told by its run.
    const handing: ExitWorld = {
      run: failedRun([erp(1, "acknowledged"), erp(2, "failed")]),
      job: exitJob("HAND_OVER", "RUNNING"),
      listed: [exitJob("HAND_OVER", "RUNNING")],
      posted: [],
    };
    serveExits(handing);
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    expect(
      await screen.findByRole("progressbar", {
        name: "Handing over a batch of journal run JR-000209",
      }),
    ).toBeTruthy();
    handing.listed = [];
    handing.job = exitJob("HAND_OVER", "SUCCEEDED", {
      result: {
        href: RUN_HREF,
        counts: { asked: 1, held: 0, handed_over: 1 },
        outcome: "HANDED_OVER",
      },
    });
    expect(
      await screen.findByText("A batch of journal run JR-000209 was handed over.", {}, NEXT_POLL),
    ).toBeTruthy();
  });

  // -------------------------------------------------------------------------------------------------
  // The retry of a failed batch and the job without a mode (SCREENS_B §3.2 and §3.4 rev 1.77; 04
  // §16.7 rows `retry` and `export`, rev 1.221; item JRN-RETRY-FOLLOW-1). The job of a retry ends
  // SUCCEEDED whether or not it sent the batch, so its ending is said after the run is read again, of
  // the batch as it then is.

  it("a retried batch is followed to its toast", async () => {
    const world: ExitWorld = {
      run: failedRun([erp(1, "acknowledged"), erp(2, "failed"), failedCsv(3)]),
      job: exportJob("RUNNING"),
      listed: [],
      posted: [],
    };
    const served = serveExits(world);
    accept("/api/v1/journal-batches/:batchId/retry", world, null, () => {
      world.listed = [exportJob("QUEUED")];
    });
    renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const grid = await screen.findByRole("grid", { name: "Batches" });
    expect(await screen.findByRole("button", { name: "Download batch files" })).toBeTruthy();
    expect(served.activeJobReads).toHaveLength(1);
    await retryBatch(grid, "1 · 2");

    // The accepted command closes the dialog; the frame follows the job and offers nothing meanwhile.
    expect(
      await screen.findByRole("progressbar", { name: "Sending batch 1 · 2 again" }),
    ).toBeTruthy();
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(world.posted).toEqual([null]);
    // The run's active jobs are read again at once, for the frame of the next tab.
    await waitFor(() => {
      expect(served.activeJobReads.length).toBeGreaterThan(1);
    });
    await waitFor(() => {
      expect(within(grid).queryByRole("button", { name: /^Retry export for batch / })).toBeNull();
    });
    expect(within(grid).queryByRole("button", { name: /^Hand over batch / })).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry export" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Download batch files" })).toBeNull();
    expect(screen.queryByRole("button", { name: "More actions" })).toBeNull();
    // The line names the batch, not the run: one progress line.
    expect(screen.queryByRole("progressbar", { name: /^Exporting journal run/ })).toBeNull();

    // The ledger took the batch: when the run is read again it is acknowledged, and that is what is said.
    world.run = failedRun([erp(1, "acknowledged"), erp(2, "acknowledged"), failedCsv(3)]);
    world.listed = [];
    world.job = exportJob("SUCCEEDED", { result: relayed({ dispatched: 1 }, []) });
    expect(await screen.findByText("Batch 1 · 2 was sent again.", {}, NEXT_POLL)).toBeTruthy();
    expect(screen.queryByRole("progressbar", { name: /^Sending batch/ })).toBeNull();
    expect(screen.queryByTestId("SF-06-banner-retry-not-sent")).toBeNull();
    // The run and its batches were read again, and the other failed batch offers its retry again.
    await waitFor(() => {
      expect(figure(screen.getByTestId("SF-06-kpi-strip"), "Batches acknowledged")).toBe("2 of 3");
    });
    expect(
      await within(grid).findByRole("button", { name: "Retry export for batch 1 · 3" }),
    ).toBeTruthy();
    await waitFor(() => {
      expect(
        within(grid).queryByRole("button", { name: "Retry export for batch 1 · 2" }),
      ).toBeNull();
    });
    expect(screen.getAllByText("Batch 1 · 2 was sent again.")).toHaveLength(1);
  });

  it("a retry whose batch waits says when", async () => {
    // 04 §16.7 rev 1.221: the batch's message keeps its schedule, and the job says what it left. The
    // job covers every batch of the run, so `waiting` names another batch too.
    const first = erp(1, "failed");
    const second = erp(2, "failed");
    const world: ExitWorld = {
      run: failedRun([first, second]),
      job: exportJob("SUCCEEDED", {
        result: relayed({ dispatched: 0 }, [
          { batch: first, at: "2026-09-06T09:20:00Z" },
          { batch: second, at: "2026-09-06T09:25:30Z" },
        ]),
      }),
      listed: [],
      posted: [],
    };
    serveExits(world);
    accept("/api/v1/journal-batches/:batchId/retry", world, null);
    renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const grid = await screen.findByRole("grid", { name: "Batches" });
    await retryBatch(grid, "1 · 2");
    const banner = await screen.findByTestId("SF-06-banner-retry-not-sent");
    // Nothing failed: a status, not an alert.
    expect(within(banner).getByRole("status")).toBeTruthy();
    expect(within(banner).queryByRole("alert")).toBeNull();
    expect(
      within(banner).getByRole("heading", { name: "Batch 1 · 2 was not sent again" }),
    ).toBeTruthy();
    expect(
      within(banner).getByText("It is waiting to be sent again at 06 Sep 2026 09:25 UTC."),
    ).toBeTruthy();
    // The frame says it of the batch whose retry it sent.
    expect(banner.textContent).not.toContain("09:20");
    expect(banner.textContent).not.toContain("Reference");
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(screen.queryByRole("progressbar", { name: /^Sending batch/ })).toBeNull();
    // The commands are offered again; a second press would not send the batch earlier, and may be made.
    expect(
      await within(grid).findByRole("button", { name: "Retry export for batch 1 · 2" }),
    ).toBeTruthy();
    await settled();
    expect(screen.queryByText("Batch 1 · 2 was sent again.")).toBeNull();
    // The banner is said of the job the frame follows: it goes when the frame follows the next one.
    const next = "6f5e4d3c-2b1a-4f0e-9d8c-0000000000ac";
    world.job = exportJob("RUNNING", { id: next });
    accept("/api/v1/journal-batches/:batchId/retry", world, null, undefined, next);
    await retryBatch(grid, "1 · 2");
    expect(
      await screen.findByRole("progressbar", { name: "Sending batch 1 · 2 again" }),
    ).toBeTruthy();
    expect(screen.queryByTestId("SF-06-banner-retry-not-sent")).toBeNull();
    cleanup();

    // A batch `waiting` names and the frame did not send: the batch pressed was refused again, and
    // nothing is said of the other.
    const other: ExitWorld = {
      run: failedRun([first, second]),
      job: exportJob("SUCCEEDED", {
        result: relayed({ dispatched: 0, dead: 1 }, [{ batch: first, at: "2026-09-06T09:20:00Z" }]),
      }),
      listed: [],
      posted: [],
    };
    const served = serveExits(other);
    accept("/api/v1/journal-batches/:batchId/retry", other, null);
    renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    const again = await screen.findByRole("grid", { name: "Batches" });
    await retryBatch(again, "1 · 2");
    await waitFor(() => {
      expect(served.activeJobReads).toHaveLength(3);
    });
    await settled();
    expect(screen.queryByTestId("SF-06-banner-retry-not-sent")).toBeNull();
    expect(screen.queryByText("Batch 1 · 2 was sent again.")).toBeNull();
  });

  it("a retry the ledger refuses again adds nothing", async () => {
    const closed = "NetSuite: the posting period Aug 2026 is closed.";
    const refusedAgain = (): JournalBatch => ({
      ...erp(1, "failed"),
      attempt_count: 9,
      last_error: closed,
    });
    const banner = () => screen.getByTestId("SF-06-banner-export-failed").textContent;
    for (const result of [
      relayed({ dispatched: 0, dead: 1 }, []),
      // An API before 04 rev 1.221: the job states no `waiting` at all.
      relayed({ dispatched: 0, dead: 1 }),
      // A job's `result` is a free object in the OpenAPI document: what is not a list of batches with
      // their instants names no waiting batch.
      { ...relayed({ dispatched: 0, dead: 1 }), waiting: "erev:avenmoor:JR-000209:1:1" },
      {
        ...relayed({ dispatched: 0, dead: 1 }),
        waiting: [
          null,
          "erev:avenmoor:JR-000209:1:1",
          { journal_batch_id: erp(1, "failed").id },
          { journal_batch_id: erp(1, "failed").id, next_attempt_at: 1_788_772_800 },
          // An instant is in UTC (04 §16.7): no other text is formatted as one (DG-FE-20).
          { journal_batch_id: erp(1, "failed").id, next_attempt_at: "in about 15 minutes" },
          { journal_batch_id: erp(1, "failed").id, next_attempt_at: "2026-09-06T11:25:30+02:00" },
        ],
      },
    ]) {
      const world: ExitWorld = {
        run: failedRun([erp(1, "failed")]),
        job: exportJob("RUNNING"),
        listed: [],
        posted: [],
      };
      serveExits(world);
      accept("/api/v1/journal-batches/:batchId/retry", world, null);
      renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`, {
        me: MAYA,
        screenRoutes: SCREEN_ROUTES,
      });

      const grid = await screen.findByRole("grid", { name: "Batches" });
      await retryBatch(grid, "1 · 1");
      expect(
        await screen.findByRole("progressbar", { name: "Sending batch 1 · 1 again" }),
      ).toBeTruthy();
      expect(banner()).toContain("NetSuite: account 5003 is inactive.");
      // The job ends SUCCEEDED over a batch the ledger refused again.
      world.run = failedRun([refusedAgain()]);
      world.job = exportJob("SUCCEEDED", { result });
      // The failed banner states the batch's new error, and the commands are offered again.
      await waitFor(() => {
        expect(banner()).toContain(closed);
      }, NEXT_POLL);
      expect(
        await within(grid).findByRole("button", { name: "Retry export for batch 1 · 1" }),
      ).toBeTruthy();
      expect(screen.queryByRole("progressbar", { name: /^Sending batch/ })).toBeNull();
      await settled();
      expect(screen.queryByText("Batch 1 · 1 was sent again.")).toBeNull();
      expect(screen.queryByTestId("SF-06-banner-retry-not-sent")).toBeNull();
      cleanup();
    }
  });

  it("a retry whose job fails says why", async () => {
    const stopped =
      "The export stopped before batch erev:avenmoor:JR-000209:1:1 was sent: the worker lost its connection to the database.";
    const world: ExitWorld = {
      run: failedRun([erp(1, "failed")]),
      job: exportJob("FAILED", { problem: refusal(stopped) }),
      listed: [],
      posted: [],
    };
    serveExits(world);
    accept("/api/v1/journal-batches/:batchId/retry", world, null);
    renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const grid = await screen.findByRole("grid", { name: "Batches" });
    await retryBatch(grid, "1 · 1");
    const banner = await screen.findByTestId("SF-06-banner-retry-not-sent");
    expect(within(banner).getByRole("alert")).toBeTruthy();
    expect(
      within(banner).getByRole("heading", { name: "Batch 1 · 1 was not sent again" }),
    ).toBeTruthy();
    expect(within(banner).getByText(stopped)).toBeTruthy();
    expect(within(banner).getByText("Reference 6f5e4d3c.")).toBeTruthy();
    expect(banner.textContent).not.toContain("waiting");
    expect(
      await within(grid).findByRole("button", { name: "Retry export for batch 1 · 1" }),
    ).toBeTruthy();
    cleanup();

    // A job that failed after the ledger took the batch: the batch as it is decides, not the job.
    const sent: ExitWorld = {
      run: failedRun([erp(1, "failed")]),
      job: exportJob("FAILED", { problem: refusal(stopped) }),
      listed: [],
      posted: [],
    };
    serveExits(sent);
    accept("/api/v1/journal-batches/:batchId/retry", sent, null, () => {
      sent.run = run({
        state: "acknowledged",
        approved_at: "2026-09-05T12:00:00Z",
        acknowledged_at: "2026-09-06T09:10:05Z",
        batches: [erp(1, "acknowledged")],
      });
    });
    renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    await retryBatch(await screen.findByRole("grid", { name: "Batches" }), "1 · 1");
    expect(await screen.findByText("Batch 1 · 1 was sent again.")).toBeTruthy();
    expect(screen.queryByTestId("SF-06-banner-retry-not-sent")).toBeNull();
  });

  it("a frame follows an export it did not start and reads the run again", async () => {
    // SMAP-07: the export of an approved run that another member, or another tab, sent. The API lists
    // a job to the member who started it and to a holder of `audit.read`.
    const exporting: ExitWorld = {
      run: run({
        state: "approved",
        approved_at: "2026-09-05T12:00:00Z",
        batches: [batch(1, "approved"), batch(2, "approved")],
      }),
      job: exportJob("RUNNING"),
      listed: [exportJob("RUNNING")],
      posted: [],
    };
    serveExits(exporting);
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, {
      me: READS_AUDIT,
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("progressbar", { name: "Exporting journal run JR-000209 to CSV" }),
    ).toBeTruthy();
    // SMAP-07: the chip of the approved run says so too.
    expect(screen.getByText("Exporting")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Export journals" })).toBeNull();
    // The job ends: the run is read again, and the page is the Exported one, with the export's toast.
    exporting.run = run({
      state: "exported",
      approved_at: "2026-09-05T12:00:00Z",
      exported_at: "2026-09-06T09:00:00Z",
      batches: [batch(1, "acknowledged"), batch(2, "exported")],
    });
    exporting.listed = [];
    exporting.job = exportJob("SUCCEEDED", { result: relayed({ dispatched: 2 }, []) });
    expect(
      await screen.findByText(
        "Journal run JR-000209 exported. 1 of 2 batches acknowledged.",
        {},
        NEXT_POLL,
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("progressbar", { name: /^Exporting journal run/ })).toBeNull();
    await waitFor(() => {
      expect(figure(screen.getByTestId("SF-06-kpi-strip"), "Batches acknowledged")).toBe("1 of 2");
    });
    expect(screen.queryByRole("button", { name: "Export journals" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "More actions" }));
    expect((await screen.findAllByRole("menuitem")).map((item) => item.textContent)).toEqual([
      "Export again",
      "History",
    ]);
    cleanup();

    // On a run with a failed batch a job without a mode is a retry another frame sent, or the run's
    // export sent again: the same line, where nothing showed, and the commands wait for its end.
    const failed = erp(1, "failed");
    const retried: ExitWorld = {
      run: failedRun([failed]),
      job: exportJob("RUNNING"),
      listed: [exportJob("RUNNING")],
      posted: [],
    };
    serveExits(retried);
    renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    expect(
      await screen.findByRole("progressbar", {
        name: "Exporting journal run JR-000209 to NetSuite",
      }),
    ).toBeTruthy();
    const grid = await screen.findByRole("grid", { name: "Batches" });
    expect(await within(grid).findByRole("link", { name: "Download batch 1 · 1" })).toBeTruthy();
    expect(within(grid).queryByRole("button", { name: /^(Retry export|Hand over) / })).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry export" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Download batch files" })).toBeNull();
    // It ends over a batch that waits: the commands return, and a frame that did not send the retry
    // says nothing — API-S-Job names no batch.
    retried.listed = [];
    retried.job = exportJob("SUCCEEDED", {
      result: relayed({ dispatched: 0 }, [{ batch: failed, at: "2026-09-06T09:25:30Z" }]),
    });
    expect(
      await within(grid).findByRole("button", { name: "Retry export for batch 1 · 1" }, NEXT_POLL),
    ).toBeTruthy();
    expect(screen.queryByRole("progressbar", { name: /^Exporting journal run/ })).toBeNull();
    await settled();
    expect(screen.queryByTestId("SF-06-banner-retry-not-sent")).toBeNull();
    expect(screen.queryByText(/^Journal run JR-000209 exported\./)).toBeNull();
  });

  it("a failed run is retried on its rows alone", async () => {
    // §3.2 action bar, Failed (rev 1.77; the supervisor's ruling of 2026-10-01): the header's "Retry
    // export" and the failed banner's link sent the run's `export`, which writes no message for a batch
    // that has one and so sent nothing for a failed batch (04 T-SL-07). Neither is offered until the
    // command retries the failed batches of a run (item JRN-RUN-RETRY-1).
    const failed = (): ExitWorld => ({
      run: failedRun([erp(1, "failed"), failedCsv(2)]),
      job: null,
      listed: [],
      posted: [],
    });
    serveExits(failed());
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    const banner = await screen.findByTestId("SF-06-banner-export-failed");
    expect(await screen.findByRole("button", { name: "Download batch files" })).toBeTruthy();
    expect(within(banner).queryByRole("button")).toBeNull();
    expect(screen.queryByRole("button", { name: /^(Retry export|Export )/ })).toBeNull();
    // The banner still names the exits, and the overflow the cancel.
    expect(banner.textContent).toContain(EXITS_BOTH);
    fireEvent.click(screen.getByRole("button", { name: "More actions" }));
    expect((await screen.findAllByRole("menuitem")).map((item) => item.textContent)).toEqual([
      "Cancel journal run",
    ]);
    cleanup();

    // A failed batch beside an exported one rolls the run up to Exported (SMAP-08): "Export again" is
    // its own command and stays; the banner offers no retry there either.
    serveExits({
      run: failedRun([erp(1, "exported"), erp(2, "failed")], {
        state: "exported",
        exported_at: "2026-09-06T09:00:00Z",
      }),
      job: null,
      listed: [],
      posted: [],
    });
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    const partly = await screen.findByTestId("SF-06-banner-export-failed");
    expect(within(partly).queryByRole("button")).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry export" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "More actions" }));
    expect(await screen.findByRole("menuitem", { name: "Export again" })).toBeTruthy();
    cleanup();

    // The rows are the way: each failed batch has its "Retry export".
    serveExits(failed());
    renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    const grid = await screen.findByRole("grid", { name: "Batches" });
    expect(
      await within(grid).findByRole("button", { name: "Retry export for batch 1 · 1" }),
    ).toBeTruthy();
    expect(within(grid).getByRole("button", { name: "Retry export for batch 1 · 2" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Retry export" })).toBeNull();
  });

  it("exported is said only of a run the job exported", async () => {
    // A job without a mode ends SUCCEEDED whatever it sent. On a Failed run the run's export writes no
    // message for a batch that has one (04 T-SL-07): sent from another frame, it sends nothing.
    const world: ExitWorld = {
      run: failedRun([failedCsv(1), batch(2, "acknowledged")]),
      job: exportJob("RUNNING"),
      listed: [exportJob("RUNNING")],
      posted: [],
    };
    const served = serveExits(world);
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    expect(
      await screen.findByRole("progressbar", { name: "Exporting journal run JR-000209 to CSV" }),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Download batch files" })).toBeNull();
    const reads = served.activeJobReads.length;
    world.listed = [];
    world.job = exportJob("SUCCEEDED", { result: relayed({ dispatched: 0 }, []) });
    // The job's end reads the run and its active jobs again, and the actions return.
    expect(
      await screen.findByRole("button", { name: "Download batch files" }, NEXT_POLL),
    ).toBeTruthy();
    await waitFor(() => {
      expect(served.activeJobReads.length).toBeGreaterThan(reads);
    });
    await settled();
    // The run is still Failed: nothing says "exported", and the failed banner stands.
    expect(screen.queryByText(/^Journal run JR-000209 exported\./)).toBeNull();
    expect(screen.getByTestId("SF-06-banner-export-failed").textContent).toContain(
      "Account 5003 is not in the chart of accounts.",
    );
    expect(screen.queryByRole("progressbar")).toBeNull();
    // The job ended well: no banner says that it did not export (rev 1.85).
    expect(screen.queryByTestId("SF-06-banner-export-not-done")).toBeNull();
    cleanup();

    // A run that was Exported when the frame began to follow the job — a failed batch beside an
    // exported one (SMAP-08), retried from another frame — is not said to be exported by that job.
    const retried: ExitWorld = {
      run: failedRun([erp(1, "exported"), erp(2, "failed")], {
        state: "exported",
        exported_at: "2026-09-06T09:00:00Z",
      }),
      job: exportJob("RUNNING"),
      listed: [exportJob("RUNNING")],
      posted: [],
    };
    serveExits(retried);
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    expect(
      await screen.findByRole("progressbar", {
        name: "Exporting journal run JR-000209 to NetSuite",
      }),
    ).toBeTruthy();
    expect(screen.getByTestId("SF-06-banner-export-failed")).toBeTruthy();
    retried.run = failedRun([erp(1, "exported"), erp(2, "exported")], {
      state: "exported",
      exported_at: "2026-09-06T09:00:00Z",
    });
    retried.listed = [];
    retried.job = exportJob("SUCCEEDED", { result: relayed({ dispatched: 1 }, []) });
    // The run is read again: its failed banner goes.
    await waitFor(() => {
      expect(screen.queryByTestId("SF-06-banner-export-failed")).toBeNull();
    }, NEXT_POLL);
    await settled();
    expect(screen.queryByText(/^Journal run JR-000209 exported\./)).toBeNull();
    cleanup();

    // "Export again" keeps its own toast, and says it of a job that ended well only.
    const again: ExitWorld = {
      run: run({
        state: "exported",
        approved_at: "2026-09-05T12:00:00Z",
        exported_at: "2026-09-06T09:00:00Z",
        batches: [batch(1, "exported")],
      }),
      job: exportJob("FAILED", {
        problem: refusal("The export worker lost its connection to the database."),
      }),
      listed: [],
      posted: [],
    };
    serveExits(again);
    accept("/api/v1/journal-runs/:runId/export", again, null);
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(await screen.findByRole("button", { name: "More actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Export again" }));
    const repeat = await screen.findByRole("alertdialog", {
      name: "Export journal run JR-000209 to CSV?",
    });
    fireEvent.click(within(repeat).getByRole("button", { name: "Export" }));
    await waitFor(() => {
      expect(again.posted).toEqual([{ adapter: "CSV" }]);
    });
    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).toBeNull();
    });
    // The job has ended when the actions are offered again.
    expect(await screen.findByRole("button", { name: "Download batch files" })).toBeTruthy();
    await settled();
    expect(
      screen.queryByText("The export was already recorded. No batch was posted again."),
    ).toBeNull();
    expect(screen.queryByText(/^Journal run JR-000209 exported\./)).toBeNull();
  });

  it("a failed export job says that the run was not exported", async () => {
    // §3.2 States "Exporting" (rev 1.85): a job of the run's own export that ends FAILED or CANCELLED
    // left the page as it was, and said nothing. It is told as the retry's failed job is: a negative
    // banner with the job's sentence and its reference.
    const LOST = "The export worker lost its connection to the database.";
    const approved = () =>
      run({
        state: "approved",
        approved_at: "2026-09-05T12:00:00Z",
        batches: [batch(1, "approved"), batch(2, "approved")],
      });
    const sent: ExitWorld = { run: approved(), job: null, listed: [], posted: [] };
    serveExits(sent);
    accept("/api/v1/journal-runs/:runId/export", sent, null, () => {
      sent.job = exportJob("FAILED", { problem: refusal(LOST) });
    });
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(await screen.findByRole("button", { name: "Export journals" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Export journal run JR-000209 to CSV?",
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Export" }));

    const banner = await screen.findByTestId("SF-06-banner-export-not-done");
    expect(
      within(banner).getByRole("heading", { name: "Journal run JR-000209 was not exported" }),
    ).toBeTruthy();
    expect(within(banner).getByRole("alert").textContent).toContain(LOST);
    expect(banner.textContent).toContain("Reference 6f5e4d3c.");
    // The run is Approved still, and its action is offered again.
    expect(await screen.findByRole("button", { name: "Export journals" })).toBeTruthy();
    await settled();
    expect(screen.queryByText(/^Journal run JR-000209 exported\./)).toBeNull();

    // The banner is of that job: it leaves when the frame follows the next one.
    const SECOND = "6f5e4d3c-2b1a-4f0e-9d8c-0000000000bb";
    accept(
      "/api/v1/journal-runs/:runId/export",
      sent,
      null,
      () => {
        sent.job = { ...exportJob("RUNNING"), id: SECOND };
        sent.listed = [{ ...exportJob("RUNNING"), id: SECOND }];
      },
      SECOND,
    );
    fireEvent.click(screen.getByRole("button", { name: "Export journals" }));
    fireEvent.click(
      within(
        await screen.findByRole("alertdialog", { name: "Export journal run JR-000209 to CSV?" }),
      ).getByRole("button", { name: "Export" }),
    );
    expect(
      await screen.findByRole("progressbar", { name: "Exporting journal run JR-000209 to CSV" }),
    ).toBeTruthy();
    expect(screen.queryByTestId("SF-06-banner-export-not-done")).toBeNull();
    cleanup();

    // A frame that did not send the export says it too: its reader saw the page say "Exporting".
    const found: ExitWorld = {
      run: approved(),
      job: exportJob("RUNNING"),
      listed: [exportJob("RUNNING")],
      posted: [],
    };
    serveExits(found);
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, {
      me: READS_AUDIT,
      screenRoutes: SCREEN_ROUTES,
    });
    expect(
      await screen.findByRole("progressbar", { name: "Exporting journal run JR-000209 to CSV" }),
    ).toBeTruthy();
    found.listed = [];
    // A cancelled job states no problem: the banner holds its title and the reference.
    found.job = exportJob("CANCELLED");
    const other = await screen.findByTestId("SF-06-banner-export-not-done", {}, NEXT_POLL);
    expect(
      within(other).getByRole("heading", { name: "Journal run JR-000209 was not exported" }),
    ).toBeTruthy();
    expect(within(other).getByRole("alert").textContent).toBe(
      "Journal run JR-000209 was not exportedReference 6f5e4d3c.",
    );
    cleanup();

    // The run decides before the job: a job that failed over a run it exported all the same is told
    // by the export's toast, and no banner says that it was not.
    const late: ExitWorld = {
      run: approved(),
      job: exportJob("RUNNING"),
      listed: [exportJob("RUNNING")],
      posted: [],
    };
    serveExits(late);
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, {
      me: READS_AUDIT,
      screenRoutes: SCREEN_ROUTES,
    });
    expect(
      await screen.findByRole("progressbar", { name: "Exporting journal run JR-000209 to CSV" }),
    ).toBeTruthy();
    late.run = run({
      state: "exported",
      approved_at: "2026-09-05T12:00:00Z",
      exported_at: "2026-09-06T09:00:00Z",
      batches: [batch(1, "exported"), batch(2, "exported")],
    });
    late.listed = [];
    late.job = exportJob("FAILED", { problem: refusal(LOST) });
    expect(
      await screen.findByText(
        "Journal run JR-000209 exported. 0 of 2 batches acknowledged.",
        {},
        NEXT_POLL,
      ),
    ).toBeTruthy();
    await settled();
    expect(screen.queryByTestId("SF-06-banner-export-not-done")).toBeNull();
  });

  it("a failed repeat of an export says that it was not repeated", async () => {
    // §3.2 (rev 1.85; the supervisor's ruling of 2026-10-01): over an Exported run "was not exported"
    // would be false. The run's status and its batches stay as they are, and the page says what the
    // job did not do.
    const LOST = "The export worker lost its connection to the database.";
    const exported = () =>
      run({
        state: "exported",
        approved_at: "2026-09-05T12:00:00Z",
        exported_at: "2026-09-06T09:00:00Z",
        batches: [batch(1, "exported")],
      });
    const again: ExitWorld = { run: exported(), job: null, listed: [], posted: [] };
    serveExits(again);
    accept("/api/v1/journal-runs/:runId/export", again, null, () => {
      again.job = exportJob("FAILED", { problem: refusal(LOST) });
    });
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(await screen.findByRole("button", { name: "More actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Export again" }));
    fireEvent.click(
      within(
        await screen.findByRole("alertdialog", { name: "Export journal run JR-000209 to CSV?" }),
      ).getByRole("button", { name: "Export" }),
    );

    const banner = await screen.findByTestId("SF-06-banner-export-not-done");
    expect(
      within(banner).getByRole("heading", {
        name: "The export of journal run JR-000209 was not repeated",
      }),
    ).toBeTruthy();
    expect(within(banner).getByRole("alert").textContent).toContain(LOST);
    expect(banner.textContent).toContain("Reference 6f5e4d3c.");
    // The run stays Exported, and nothing says that it was not.
    expect(screen.getByText("Exported")).toBeTruthy();
    await settled();
    expect(screen.queryByText("Journal run JR-000209 was not exported")).toBeNull();
    expect(
      screen.queryByText("The export was already recorded. No batch was posted again."),
    ).toBeNull();
    cleanup();

    // A frame that found a job under way on an Exported run says the same of it. A frame reads the
    // active jobs of an Exported run only beside a failed batch (SMAP-08 rolls such a run up to
    // Exported): the job is the run's export sent again, or a retry another frame sent.
    const found: ExitWorld = {
      run: failedRun([erp(1, "exported"), erp(2, "failed")], {
        state: "exported",
        exported_at: "2026-09-06T09:00:00Z",
      }),
      job: exportJob("RUNNING"),
      listed: [exportJob("RUNNING")],
      posted: [],
    };
    serveExits(found);
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, {
      me: READS_AUDIT,
      screenRoutes: SCREEN_ROUTES,
    });
    expect(
      await screen.findByRole("progressbar", {
        name: "Exporting journal run JR-000209 to NetSuite",
      }),
    ).toBeTruthy();
    found.listed = [];
    found.job = exportJob("FAILED", { problem: refusal(LOST) });
    const other = await screen.findByTestId("SF-06-banner-export-not-done", {}, NEXT_POLL);
    expect(
      within(other).getByRole("heading", {
        name: "The export of journal run JR-000209 was not repeated",
      }),
    ).toBeTruthy();
    expect(within(other).getByRole("alert").textContent).toContain(LOST);
    cleanup();

    // A repeat that ends well keeps its toast.
    const well: ExitWorld = { run: exported(), job: null, listed: [], posted: [] };
    serveExits(well);
    accept("/api/v1/journal-runs/:runId/export", well, null, () => {
      well.job = exportJob("SUCCEEDED", { result: relayed({ dispatched: 0 }, []) });
    });
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(await screen.findByRole("button", { name: "More actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Export again" }));
    fireEvent.click(
      within(
        await screen.findByRole("alertdialog", { name: "Export journal run JR-000209 to CSV?" }),
      ).getByRole("button", { name: "Export" }),
    );
    expect(
      await screen.findByText("The export was already recorded. No batch was posted again."),
    ).toBeTruthy();
    expect(screen.queryByTestId("SF-06-banner-export-not-done")).toBeNull();
    cleanup();

    // A job found under way on an Exported run that ends well says nothing: the frame did not send
    // "Export again", and API-S-Job names no batch for it to speak of.
    const quiet: ExitWorld = {
      run: failedRun([erp(1, "exported"), erp(2, "failed")], {
        state: "exported",
        exported_at: "2026-09-06T09:00:00Z",
      }),
      job: exportJob("RUNNING"),
      listed: [exportJob("RUNNING")],
      posted: [],
    };
    serveExits(quiet);
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, {
      me: READS_AUDIT,
      screenRoutes: SCREEN_ROUTES,
    });
    expect(
      await screen.findByRole("progressbar", {
        name: "Exporting journal run JR-000209 to NetSuite",
      }),
    ).toBeTruthy();
    quiet.listed = [];
    quiet.job = exportJob("SUCCEEDED", { result: relayed({ dispatched: 0 }, []) });
    // The job has ended when the actions are offered again.
    expect(
      await screen.findByRole("button", { name: "Download batch files" }, NEXT_POLL),
    ).toBeTruthy();
    await settled();
    expect(screen.queryByTestId("SF-06-banner-export-not-done")).toBeNull();
    expect(
      screen.queryByText("The export was already recorded. No batch was posted again."),
    ).toBeNull();
  });

  it("the failed banner opens the batches from Summary and Lines", async () => {
    // §3.2 Banners (rev 1.85): since a Failed run has no command in its header, the banner of a run
    // opened on Summary or Lines named no place for the retry. On Batches the rows are in view.
    const failed = (): ExitWorld => ({
      run: failedRun([erp(1, "failed"), failedCsv(2)]),
      job: null,
      listed: [],
      posted: [],
    });
    for (const tab of ["", "/lines"]) {
      serveExits(failed());
      server.use(
        http.get(apiUrl("/api/v1/journal-runs/:runId/lines"), () =>
          HttpResponse.json({ items: [], next_cursor: null }),
        ),
      );
      renderApp(`/journals/runs/${RUN_ID}${tab}?${CONTEXT}`, {
        me: MAYA,
        screenRoutes: SCREEN_ROUTES,
      });
      const banner = await screen.findByTestId("SF-06-banner-export-failed");
      expect(
        within(banner).getByRole("link", { name: "Open batches" }).getAttribute("href"),
        tab,
      ).toBe(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`);
      expect(within(banner).queryByRole("button")).toBeNull();
      cleanup();
    }
    serveExits(failed());
    renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    const banner = await screen.findByTestId("SF-06-banner-export-failed");
    await screen.findByRole("grid", { name: "Batches" });
    expect(within(banner).queryByRole("link")).toBeNull();
  });

  it("a request without an answer is said in the four older dialogs", async () => {
    const NO_ANSWER = "No answer came back from the server. Try again.";
    const lost = (path: string) => http.post(apiUrl(path), () => HttpResponse.error());

    // "Submit for approval" on a calculated run.
    serveExits({ run: run(), job: null, listed: [], posted: [] });
    server.use(lost("/api/v1/journal-runs/:runId/submit"));
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(await screen.findByRole("button", { name: "Submit for approval" }));
    const submit = await screen.findByRole("dialog", {
      name: "Submit journal run JR-000209 for approval?",
    });
    fireEvent.click(within(submit).getByRole("button", { name: "Submit for approval" }));
    expect(await screen.findByText(NO_ANSWER)).toBeTruthy();
    expect(screen.getByRole("dialog", { name: "Submit journal run JR-000209 for approval?" })).toBe(
      submit,
    );
    cleanup();

    // "Export" on an approved run.
    serveExits({
      run: run({ state: "approved", approved_at: "2026-09-05T12:00:00Z" }),
      job: null,
      listed: [],
      posted: [],
    });
    server.use(lost("/api/v1/journal-runs/:runId/export"));
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(await screen.findByRole("button", { name: "Export journals" }));
    const exportDialog = await screen.findByRole("alertdialog", {
      name: "Export journal run JR-000209 to CSV?",
    });
    fireEvent.click(within(exportDialog).getByRole("button", { name: "Export" }));
    expect(await screen.findByText(NO_ANSWER)).toBeTruthy();
    expect(screen.getByRole("alertdialog", { name: "Export journal run JR-000209 to CSV?" })).toBe(
      exportDialog,
    );
    expect(screen.queryByRole("progressbar")).toBeNull();
    cleanup();

    // "Retry export" and "Record ERP reference" on the rows.
    serveExits({
      run: failedRun([erp(1, "exported"), erp(2, "failed")], {
        state: "exported",
        exported_at: "2026-09-06T09:00:00Z",
      }),
      job: null,
      listed: [],
      posted: [],
    });
    server.use(
      lost("/api/v1/journal-batches/:batchId/retry"),
      lost("/api/v1/journal-batches/:batchId/acknowledge"),
    );
    renderApp(`/journals/runs/${RUN_ID}/batches?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    const grid = await screen.findByRole("grid", { name: "Batches" });
    await retryBatch(grid, "1 · 2");
    expect(await screen.findByText(NO_ANSWER)).toBeTruthy();
    const retry = screen.getByRole("alertdialog", { name: "Retry batch 1 · 2?" });
    expect(screen.queryByRole("progressbar")).toBeNull();
    fireEvent.click(within(retry).getByRole("button", { name: "Cancel" }));

    fireEvent.click(
      await within(grid).findByRole("button", { name: "Record ERP reference for batch 1 · 1" }),
    );
    const record = await screen.findByRole("dialog", {
      name: "Record ERP reference for batch 1 · 1",
    });
    fireEvent.change(within(record).getByRole("textbox", { name: "ERP document reference" }), {
      target: { value: "JE-88412" },
    });
    fireEvent.click(within(record).getByRole("button", { name: "Record reference" }));
    await waitFor(() => {
      expect(screen.getAllByText(NO_ANSWER)).toHaveLength(2);
    });
    expect(screen.getByRole("dialog", { name: "Record ERP reference for batch 1 · 1" })).toBe(
      record,
    );
    expect(screen.queryByText("Batch 1 · 1 acknowledged with reference JE-88412.")).toBeNull();
  });

  it("the export dialog names the adapter of the run's batches", async () => {
    // 04 §16.7 rev 1.145: a run's batches are calculated for one adapter, and `export` answers 422 for
    // any other. The dialog sent `CSV` for every run.
    const world: ExitWorld = {
      run: run({
        state: "approved",
        approved_at: "2026-09-05T12:00:00Z",
        batches: [erp(1, "approved"), erp(2, "approved")],
      }),
      job: exportJob("RUNNING"),
      listed: [],
      posted: [],
    };
    serveExits(world);
    accept("/api/v1/journal-runs/:runId/export", world, null);
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    fireEvent.click(await screen.findByRole("button", { name: "Export to NetSuite" }));
    expect(screen.queryByRole("button", { name: "Export journals" })).toBeNull();
    const dialog = await screen.findByRole("alertdialog", {
      name: "Export journal run JR-000209 to NetSuite?",
    });
    const target = within(within(dialog).getByTestId("SF-06-export-target")).getByRole("combobox", {
      name: "Target",
    });
    expect(target.textContent).toBe("NetSuite");
    fireEvent.click(target);
    expect((await screen.findAllByRole("option")).map((option) => option.textContent)).toEqual([
      "NetSuite",
    ]);
    // A second press closes the list of the one target.
    fireEvent.click(target);
    expect(screen.queryByRole("option")).toBeNull();
    fireEvent.click(within(dialog).getByRole("button", { name: "Export" }));
    expect(
      await screen.findByRole("progressbar", {
        name: "Exporting journal run JR-000209 to NetSuite",
      }),
    ).toBeTruthy();
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(world.posted).toEqual([{ adapter: "NETSUITE" }]);
    // A ledger answers with its document at once: the run is Posted when it is read again, and that
    // is an export too.
    world.run = run({
      state: "acknowledged",
      approved_at: "2026-09-05T12:00:00Z",
      exported_at: "2026-09-06T09:00:00Z",
      acknowledged_at: "2026-09-06T09:00:00Z",
      batches: [erp(1, "acknowledged"), erp(2, "acknowledged")],
    });
    world.job = exportJob("SUCCEEDED", { result: relayed({ dispatched: 2 }, []) });
    expect(
      await screen.findByText(
        "Journal run JR-000209 exported. 2 of 2 batches acknowledged.",
        {},
        NEXT_POLL,
      ),
    ).toBeTruthy();
    cleanup();

    // A CSV run keeps "Export journals" and its one target, the download.
    const csv: ExitWorld = {
      run: run({ state: "approved", approved_at: "2026-09-05T12:00:00Z" }),
      job: exportJob("RUNNING"),
      listed: [],
      posted: [],
    };
    serveExits(csv);
    accept("/api/v1/journal-runs/:runId/export", csv, null);
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(await screen.findByRole("button", { name: "Export journals" }));
    const plain = await screen.findByRole("alertdialog", {
      name: "Export journal run JR-000209 to CSV?",
    });
    const download = within(within(plain).getByTestId("SF-06-export-target")).getByRole(
      "combobox",
      { name: "Target" },
    );
    expect(download.textContent).toBe("CSV download");
    fireEvent.click(within(plain).getByRole("button", { name: "Export" }));
    await waitFor(() => {
      expect(csv.posted).toEqual([{ adapter: "CSV" }]);
    });
  });

  // A failed run its job cancelled at the second request (04 §16.7 rev 1.159), as `GET /audit-events`
  // lists it. The attempt the job refused and the cancel carry one action and, here, one instant: only
  // the outcome tells them apart.
  const SENT_MEANWHILE =
    "Batch erev:avenmoor:JR-000209:1:1 was sent again while the ledger was asked, so nothing was changed. Ask again.";
  const SYSTEM = { id: null, display_name: "System", kind: "SYSTEM" };
  const CANCELLED_BY_JOB = [
    {
      id: "4b3a2c1d-0e9f-4a8b-9c7d-0000000000e1",
      action: "journal_run.cancel",
      outcome: "DENIED",
      actor: SYSTEM,
      on_behalf_of: ACTOR,
      occurred_at: "2026-09-06T09:10:05Z",
      comment: "NetSuite rejects account 5003.",
      detail: {
        problem: "invalid-transition",
        rule_id: "E-34",
        message: SENT_MEANWHILE,
        job_id: JOB_ID,
      },
    },
    {
      id: "4b3a2c1d-0e9f-4a8b-9c7d-0000000000e2",
      action: "journal_run.cancel",
      outcome: "SUCCESS",
      actor: SYSTEM,
      on_behalf_of: ACTOR,
      occurred_at: "2026-09-06T09:10:05Z",
      comment: "NetSuite can never accept account 5003.",
      detail: {},
    },
    {
      id: "4b3a2c1d-0e9f-4a8b-9c7d-0000000000e3",
      action: "journal_run.request_cancel",
      outcome: "SUCCESS",
      actor: ACTOR,
      on_behalf_of: null,
      occurred_at: "2026-09-06T09:10:00Z",
      comment: "NetSuite can never accept account 5003.",
      detail: {},
    },
  ];
  const cancelledByJob = (): ExitWorld => ({
    run: run({
      state: "cancelled",
      approved_at: "2026-09-05T12:00:00Z",
      cancelled_at: "2026-09-06T09:10:05Z",
      batches: [erp(1, "cancelled")],
    }),
    job: null,
    listed: [],
    posted: [],
    events: CANCELLED_BY_JOB,
  });

  it("cancelled banner names who asked a job to cancel", async () => {
    serveExits(cancelledByJob());
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, {
      me: READS_AUDIT,
      screenRoutes: SCREEN_ROUTES,
    });

    // The SUCCESS event, though a DENIED one of the same action stands before it; the person the job
    // acted for, not "System".
    const banner = await screen.findByTestId("SF-06-banner-cancelled");
    expect(
      within(banner).getByRole("heading", {
        name: "Journal run JR-000209 was cancelled by Maya Chen on 06 Sep 2026 09:10 UTC: NetSuite can never accept account 5003.",
      }),
    ).toBeTruthy();
  });

  it("the history marks a refused cancel and names who a job acted for", async () => {
    serveExits(cancelledByJob());
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}&drawer=history`, {
      me: READS_AUDIT,
      screenRoutes: SCREEN_ROUTES,
    });

    const history = await screen.findByRole("complementary", { name: "History" });
    expect(await within(history).findAllByText("System on behalf of Maya Chen")).toHaveLength(2);
    const [refused, cancelled, requested, ...others] = within(history).getAllByRole("listitem");
    expect(others).toEqual([]);
    if (refused === undefined || cancelled === undefined || requested === undefined) {
      throw new Error("the History drawer lists fewer than three entries");
    }
    // A refused event says so before its action and quotes the refusal above the reason given.
    expect(within(refused).getByText("was refused: cancelled the run")).toBeTruthy();
    expect(within(refused).getByText(SENT_MEANWHILE)).toBeTruthy();
    expect(within(refused).getByText("NetSuite rejects account 5003.")).toBeTruthy();
    expect(within(cancelled).getByText("System on behalf of Maya Chen")).toBeTruthy();
    expect(within(cancelled).getByText("cancelled the run")).toBeTruthy();
    expect(within(cancelled).queryByText(SENT_MEANWHILE)).toBeNull();
    // The person's own entry is on nobody's behalf.
    expect(within(requested).getByText("Maya Chen")).toBeTruthy();
    expect(within(requested).getByText("asked for the run to be cancelled")).toBeTruthy();
    expect(within(requested).queryByText(/on behalf of/)).toBeNull();
  });

  it("the history words the run's actions", async () => {
    // §3.2 History (rev 1.85): DS-CMP-12 leads an event with its actor and a verb phrase. The drawer
    // printed the audit action literal there — "Maya Chen journal_run.submit". The seven literals the
    // journals domain records for a run have words; an event that did not succeed keeps the form of
    // the contract trail, and a literal the catalogue does not know reads as itself.
    const event = (index: number, action: string, outcome = "SUCCESS") => ({
      id: `4b3a2c1d-0e9f-4a8b-9c7d-0000000001${String(index).padStart(2, "0")}`,
      action,
      outcome,
      actor: ACTOR,
      on_behalf_of: null,
      occurred_at: `2026-09-06T09:${String(30 - index).padStart(2, "0")}:00Z`,
      comment: null,
      detail: {},
    });
    serveExits({
      run: run({ state: "acknowledged", batches: [batch(1, "acknowledged")] }),
      job: null,
      listed: [],
      posted: [],
      events: [
        event(0, "journal_run.cancel"),
        event(1, "journal_run.request_cancel"),
        event(2, "journal_run.request_export"),
        event(3, "journal_run.approve"),
        event(4, "journal_run.submit"),
        event(5, "journal_run.calculate"),
        event(6, "journal_run.request_calculation"),
        event(7, "journal_run.calculate", "FAILED"),
        event(8, "journal_run.request_export", "DENIED"),
        event(9, "journal_run.rebuild"),
        event(10, "journal_run.rebuild", "DENIED"),
      ],
    });
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}&drawer=history`, {
      me: READS_AUDIT,
      screenRoutes: SCREEN_ROUTES,
    });

    const history = await screen.findByRole("complementary", { name: "History" });
    await within(history).findByText("cancelled the run");
    const said = [
      "cancelled the run",
      "asked for the run to be cancelled",
      "started the export",
      "approved the run",
      "submitted the run for approval",
      "calculated the journals",
      "started the journal run",
      "failed: calculated the journals",
      "was refused: started the export",
      "journal_run.rebuild",
      "was refused: journal_run.rebuild",
    ];
    const entries = within(history).getAllByRole("listitem");
    expect(entries).toHaveLength(said.length);
    // The actor, then the phrase: nothing stands between them.
    for (const [index, entry] of entries.entries()) {
      expect(entry.textContent, said[index]).toContain(`Maya Chen ${said[index] ?? ""}`);
    }
    expect(history.textContent).not.toMatch(/journal_run\.(?!rebuild)/);
  });
});

// SCREENS_B §3.2 (rev 1.68) and SCREENS §0.6 SCR-PERM-02 (item W-12, slice b; supervisor ruling R-28):
// "History" and the name and reason of the Cancelled banner are read from the audit events, a list of
// the whole workspace that is read with `audit.read` for all entities. Without it nothing is asked,
// and a read the API refuses gives the same screen, not an error with "Retry". The jobs of the
// workspace answer every member their own; a refused read of them shows no job and is not repeated.
describe("SF-06 journal run: the audit events and the jobs of the workspace", () => {
  const AUDITOR = signedInMe({ permissions: [...MAYA.permissions, "audit.read"] });
  const SCOPED = signedInMe({
    permissions: [...MAYA.permissions, "audit.read"],
    permission_scopes: Object.fromEntries(
      [...MAYA.permissions, "audit.read"].map((code) => [code, [AVM_US.id]]),
    ),
  });
  /** A posted run: "History" is the only item of its overflow menu (SCREENS_B §3.2 action bar). */
  const posted = () => run({ state: "acknowledged", batches: [batch(1, "acknowledged")] });
  const cancelled = () => run({ state: "cancelled", cancelled_at: "2026-09-06T08:31:00Z" });

  /** Records the reads of the audit events; `refuse` answers them with 403. */
  function watchAudit(refuse = false): URL[] {
    const requested: URL[] = [];
    server.use(
      http.get(apiUrl("/api/v1/audit-events"), ({ request }) => {
        requested.push(new URL(request.url));
        return refuse
          ? problemResponse("forbidden", 403, "Permission denied")
          : HttpResponse.json({
              items: [
                {
                  id: "4b3a2c1d-0e9f-4a8b-9c7d-6e5f4a3b2c1d",
                  action: "journal_run.cancel",
                  outcome: "SUCCESS",
                  actor: { id: ACTOR.id, display_name: "Priya Raman", kind: "USER" },
                  on_behalf_of: null,
                  occurred_at: "2026-09-06T08:30:00Z",
                  comment: "Wrong period selected for this run.",
                  detail: {},
                },
              ],
              next_cursor: null,
            });
      }),
    );
    return requested;
  }

  it("History opens the audit timeline of the run for a holder of audit.read for all entities", async () => {
    serveRun(posted());
    const requested = watchAudit();
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: AUDITOR, screenRoutes: SCREEN_ROUTES });

    fireEvent.click(await screen.findByRole("button", { name: "More actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "History" }));
    const drawer = await screen.findByRole("complementary", { name: "History" });
    expect(await within(drawer).findByText("Wrong period selected for this run.")).toBeTruthy();
    expect(requested[0]?.searchParams.get("object_id")).toBe(RUN_ID);
  });

  it("History is not offered without audit.read for all entities, and a menu without an item is not rendered", async () => {
    for (const me of [MAYA, SCOPED]) {
      serveRun(posted());
      const requested = watchAudit();
      renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me, screenRoutes: SCREEN_ROUTES });

      expect(await screen.findByRole("button", { name: "Download batch files" })).toBeTruthy();
      expect(screen.queryByRole("button", { name: "More actions" })).toBeNull();
      expect(requested).toEqual([]);
      cleanup();
    }
  });

  it("drawer=history opens nothing without the permission and leaves the address", async () => {
    serveRun(posted());
    const requested = watchAudit();
    const { router } = renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}&drawer=history`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    expect(await screen.findByRole("button", { name: "Download batch files" })).toBeTruthy();
    await waitFor(() => {
      expect(router.state.location.search).toBe(`?${CONTEXT}`);
    });
    expect(screen.queryByRole("complementary", { name: "History" })).toBeNull();
    expect(requested).toEqual([]);
  });

  it("a read of the history that is refused closes the drawer and removes the item, without an error", async () => {
    serveRun(posted());
    const requested = watchAudit(true);
    const { router } = renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}&drawer=history`, {
      me: AUDITOR,
      screenRoutes: SCREEN_ROUTES,
    });

    expect(await screen.findByRole("button", { name: "Download batch files" })).toBeTruthy();
    await waitFor(() => {
      expect(router.state.location.search).toBe(`?${CONTEXT}`);
    });
    expect(screen.queryByRole("complementary", { name: "History" })).toBeNull();
    expect(screen.queryByRole("button", { name: "More actions" })).toBeNull();
    expect(screen.queryByText("Could not load the history")).toBeNull();
    expect(screen.queryByText("Permission denied")).toBeNull();
    // The refused read is not sent again.
    expect(requested).toHaveLength(1);
  });

  it("the Cancelled banner names the time and reads nothing without audit.read for all entities", async () => {
    for (const me of [MAYA, SCOPED]) {
      serveRun(cancelled());
      const requested = watchAudit();
      renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me, screenRoutes: SCREEN_ROUTES });

      expect(
        await screen.findByText("Journal run JR-000209 was cancelled on 06 Sep 2026 08:31 UTC."),
      ).toBeTruthy();
      expect(requested).toEqual([]);
      cleanup();
    }
  });

  it("the Cancelled banner names the time when the read of the audit events is refused, and asks once", async () => {
    serveRun(cancelled());
    const requested = watchAudit(true);
    renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, { me: AUDITOR, screenRoutes: SCREEN_ROUTES });

    expect(
      await screen.findByText("Journal run JR-000209 was cancelled on 06 Sep 2026 08:31 UTC."),
    ).toBeTruthy();
    expect(requested).toHaveLength(1);
    expect(screen.queryByText("Permission denied")).toBeNull();
  });

  it("a refused read of the jobs shows the approved run with its export action and is not sent again", async () => {
    serveRun(run({ state: "approved", approved_at: "2026-09-05T12:00:00Z" }));
    const asked: string[] = [];
    server.use(
      http.get(apiUrl("/api/v1/jobs"), ({ request }) => {
        asked.push(new URL(request.url).search);
        return problemResponse("forbidden", 403, "Permission denied");
      }),
    );
    const { queryClient } = renderApp(`/journals/runs/${RUN_ID}?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    expect(await screen.findByRole("button", { name: "Export journals" })).toBeTruthy();
    // Settled as answered with no job: a query that has succeeded is not retried.
    await waitFor(() => {
      const read = queryClient.getQueryCache().find({ queryKey: exportJobKey(RUN_ID) });
      expect([read?.state.status, read?.state.data, read?.state.fetchFailureCount]).toEqual([
        "success",
        [],
        0,
      ]);
    });
    expect(asked).toHaveLength(1);
    expect(screen.queryByText("Permission denied")).toBeNull();
  });
});
