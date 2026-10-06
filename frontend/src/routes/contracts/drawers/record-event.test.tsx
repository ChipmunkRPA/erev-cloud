// @vitest-environment jsdom
// The Preview panel of the five "Record …" drawers (SCREENS §4.9.3 rev 1.79; §0.7 SCR-ST-12; 04
// API-S-Job `result` rev 1.314, §16.10 "Who reads a stored preview"; register index 300 on the
// screens): the figures of the dry run's summary, and what became of a dry run that ended without
// one — the banner of a failed or cancelled job with "Retry", or the notice of a summary this reader
// is not shown. Before, the panel said "No figures change." of each of them.
import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import type { Job } from "../../../lib/api/jobs";
import type { Contract } from "../../../lib/api/queries/contracts";
import type { Obligation } from "../../../lib/api/queries/obligations";
import { registerCurrencies } from "../../../lib/format";
import { renderWithApp } from "../../../test/app";
import { apiUrl, installMswServer, server } from "../../../test/msw";
import {
  CONTRACT_ID,
  MAYA_USER,
  money,
  workbenchContract,
  workbenchObligation,
} from "../../../test/workbench";
import { type EventKind, RecordEventDrawer } from "./record-event";

installMswServer();
// The preview is asked for 600 ms after the last change of the fields.
configure({ asyncUtilTimeout: 10_000 });

beforeAll(() => {
  registerCurrencies([{ code: "USD", minor_unit: 2 }]);
});

afterEach(() => {
  cleanup();
});

const CONTRACT = workbenchContract() as unknown as Contract;
const O1 = workbenchObligation() as unknown as Obligation;
const JOB_ID = "e7e7e7e7-e7e7-4e7e-8e7e-e7e7e7e7e7e0";
const REFERENCE = "Reference e7e7e7e7.";
const FAILED = "The preview failed. Nothing was committed.";
const CANCELLED = "The preview was cancelled. Nothing was committed.";
const WITHHELD = "You are not shown this preview";
const WITHHELD_TEXT =
  "The preview holds figures of legal entities outside your access. It is shown to people whose access covers every entity of the contract's combination group.";
const NO_FIGURES = "No figures change.";
const PERIODS = [
  "FY2026-P09",
  "FY2026-P10",
  "FY2026-P11",
  "FY2026-P12",
  "FY2027-P01",
  "FY2027-P02",
] as const;

const TITLES: Readonly<Record<EventKind, string>> = {
  delivery: "Record delivery",
  progress: "Record progress",
  milestone: "Record milestone",
  cost: "Record cost",
  return: "Record return",
};

/** The problem of a job that failed, as the API stores it (05 JOB-07). */
const ENGINE_ERROR: NonNullable<Job["problem"]> = {
  type: "https://erev.dev/problems/engine-error",
  title: "The computation failed",
  status: 500,
  detail: null,
  instance: `/api/v1/jobs/${JOB_ID}`,
  errors: [],
};

/**
 * API-S-ImpactSummary of a dry run of pending events, as the API stores it: every member, the six
 * periods from the replay date on, no balances and no progress (04 §16.3). `change` is the revenue of
 * the first period and the catch-up.
 */
function summary(change: string) {
  return {
    transaction_price_before: money("120000.00"),
    transaction_price_after: money("120000.00"),
    catch_up_total: money(change),
    catch_up_by_obligation: [{ obligation_key: "O1", treatment: null, amount: money(change) }],
    remaining_allocation_before: [{ obligation_key: "O1", amount: money("60000.00") }],
    remaining_allocation_after: [{ obligation_key: "O1", amount: money("60000.00") }],
    revenue_by_period: PERIODS.map((period_key, index) => ({
      period_key,
      before: money("0.00"),
      after: money(index === 0 ? change : "0.00"),
      change: money(index === 0 ? change : "0.00"),
    })),
    rpo_before: money("60000.00"),
    rpo_after: money("60000.00"),
    rpo_date: "2026-09-30",
    balances_before: [],
    balances_after: [],
    journal_lines: [],
    progress_before: null,
    progress_after: null,
    replay_from_date: "2026-09-30",
    posting_period_key: "FY2026-P09",
    origin_period_key: null,
    computed_at: "2026-09-30T09:40:02Z",
    computed_period_key: "FY2026-P09",
  };
}

/** The result of a dry run that succeeded: `summary`, or what the API answers in its place. */
function resultWith(members: Readonly<Record<string, unknown>>): Readonly<Record<string, unknown>> {
  return { href: `/api/v1/contracts/${CONTRACT_ID}`, counts: { events: 1 }, ...members };
}

/** What a dry run ended with, as `GET /jobs/{id}` answers it. */
interface Ended {
  readonly state: Job["state"];
  readonly result?: Readonly<Record<string, unknown>>;
  readonly problem?: NonNullable<Job["problem"]>;
}

interface Asked {
  readonly body: unknown;
  readonly key: string | null;
}

/**
 * Answers every preview with a job of its own; the job of the n-th preview has ended as the n-th
 * answer says, and every later one as the last. `asked` lists the previews in the order they came,
 * `read` the ids of the jobs as they were read.
 */
function serveDryRuns(...answers: readonly Ended[]): {
  readonly asked: readonly Asked[];
  readonly read: readonly string[];
} {
  const asked: Asked[] = [];
  const read: string[] = [];
  const jobOf = (id: string, ended: Ended): Job =>
    ({
      id,
      kind: "CONTRACT_COMPUTE",
      mode: "PREVIEW",
      state: ended.state,
      progress: { done: 1, total: 1 },
      problem: ended.problem ?? null,
      result: ended.result ?? null,
      created_by: MAYA_USER,
      created_at: "2026-09-30T09:40:00Z",
      started_at: "2026-09-30T09:40:01Z",
      finished_at: "2026-09-30T09:40:03Z",
    }) as Job;
  server.use(
    http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/events/preview`), async ({ request }) => {
      asked.push({ body: await request.json(), key: request.headers.get("Idempotency-Key") });
      const id = `${JOB_ID.slice(0, -1)}${String(asked.length)}`;
      return HttpResponse.json(jobOf(id, { state: "QUEUED" }), {
        status: 202,
        headers: { Location: `/api/v1/jobs/${id}` },
      });
    }),
    http.get(apiUrl("/api/v1/jobs/:jobId"), ({ params }) => {
      const id = String(params.jobId);
      read.push(id);
      const place = Math.min(Number(id.slice(-1)), answers.length) - 1;
      return HttpResponse.json(jobOf(id, answers[place] ?? { state: "FAILED" }));
    }),
  );
  return { asked, read };
}

/** Picks an option of a Select inside `scope`. */
function select(scope: HTMLElement, name: RegExp, option: string): void {
  const trigger = within(scope).getByRole("combobox", { name });
  fireEvent.click(trigger);
  const list = document.getElementById(trigger.getAttribute("aria-controls") ?? "");
  if (list === null) {
    throw new Error(`The select ${String(name)} has no open list`);
  }
  fireEvent.mouseDown(within(list).getByRole("option", { name: option }));
}

function type(scope: HTMLElement, name: RegExp, value: string): void {
  const field = within(scope).getByRole("textbox", { name });
  fireEvent.change(field, { target: { value } });
  fireEvent.blur(field);
}

/** Opens the drawer of `kind` on O1 and fills the fields its events need: the preview is asked for. */
async function open(
  kind: EventKind = "delivery",
): Promise<{ readonly drawer: HTMLElement; readonly panel: HTMLElement }> {
  renderWithApp(
    <RecordEventDrawer
      contract={CONTRACT}
      obligations={[O1]}
      kind={kind}
      obligationKey="O1"
      onClose={() => undefined}
    />,
  );
  const drawer = await screen.findByRole("dialog", { name: TITLES[kind] });
  const panel = within(drawer).getByRole("region", { name: "Preview" });
  expect(panel.textContent).toBe("PreviewThe preview appears once the fields are valid.");
  switch (kind) {
    case "delivery":
      type(drawer, /^Quantity/, "120");
      select(drawer, /^Trigger/, "Delivery");
      break;
    case "progress":
      select(drawer, /^Measure/, "Output percent");
      type(drawer, /^Cumulative progress/, "50");
      break;
    case "milestone":
      type(drawer, /^Milestone code/, "M1");
      type(drawer, /^Cumulative weight/, "50");
      break;
    case "cost":
      select(drawer, /^Purpose/, "Progress input");
      type(drawer, /^Amount/, "100.00");
      break;
    case "return":
      type(drawer, /^Quantity returned/, "2");
      type(drawer, /^Return reference/, "RMA-DE-0077");
      select(drawer, /^Condition/, "Resaleable");
      break;
  }
  type(drawer, /^Effective date/, "30 Sep 2026");
  return { drawer, panel };
}

/** The text a sighted reader sees: without the visually hidden sign words, spaces as spaces. */
function shown(element: Element): string {
  const copy = element.cloneNode(true) as HTMLElement;
  for (const hidden of copy.querySelectorAll(".sr-only")) {
    hidden.remove();
  }
  return (copy.textContent ?? "").replaceAll(String.fromCharCode(160), " ");
}

/** The figures the panel lists: each term with its value. */
function figures(panel: HTMLElement): string[][] {
  return within(panel)
    .getAllByRole("term")
    .map((term) => [shown(term), shown(term.nextElementSibling ?? term)]);
}

/** The banner the panel shows under `title`. */
async function bannerOf(panel: HTMLElement, title: string): Promise<HTMLElement> {
  const heading = await within(panel).findByRole("heading", { name: title, level: 4 });
  const banner = heading.closest<HTMLElement>("[data-tone]");
  if (banner === null) {
    throw new Error(`"${title}" is not the title of a banner`);
  }
  return banner;
}

function submitAvailable(drawer: HTMLElement): boolean {
  const button = within(drawer).getByRole<HTMLButtonElement>("button", {
    name: "Submit for approval",
  });
  return !button.disabled && button.getAttribute("aria-disabled") !== "true";
}

describe("SF-03 Record event: what the preview panel says of its dry run", () => {
  it("before the fields are valid the panel waits for them, and while the dry run runs it says so", async () => {
    const { asked, read } = serveDryRuns({ state: "RUNNING" });
    const { panel } = await open();

    await waitFor(() => {
      expect(panel.textContent).toBe("PreviewCalculating the preview.");
    });
    // The job is read again two seconds after its first answer, which says that it runs: by then
    // that answer is on the screen, and the panel still says that the preview is calculated.
    await waitFor(() => {
      expect(read.length).toBeGreaterThan(1);
    });
    expect(panel.textContent).toBe("PreviewCalculating the preview.");
    expect(asked).toHaveLength(1);
  });

  it("a dry run that succeeded lists its figures, also where every one of them is 0.00", async () => {
    serveDryRuns({ state: "SUCCEEDED", result: resultWith({ summary: summary("12000.00") }) });
    const changed = await open();

    await within(changed.panel).findByText("Catch-up");
    expect(figures(changed.panel).slice(0, 7)).toEqual([
      ["Revenue FY2026 P09", "USD +12,000.00"],
      ["Revenue FY2026 P10", "USD 0.00"],
      ["Revenue FY2026 P11", "USD 0.00"],
      ["Revenue FY2026 P12", "USD 0.00"],
      ["Revenue FY2027 P01", "USD 0.00"],
      ["Revenue FY2027 P02", "USD 0.00"],
      ["Catch-up", "USD +12,000.00"],
    ]);
    cleanup();

    // A dry run that changes nothing answers the same members: the panel lists them at 0.00 and
    // says nothing else of them.
    serveDryRuns({ state: "SUCCEEDED", result: resultWith({ summary: summary("0.00") }) });
    const unchanged = await open();

    await within(unchanged.panel).findByText("Catch-up");
    expect(figures(unchanged.panel).slice(0, 7)).toEqual([
      ...PERIODS.map((period) => [`Revenue ${period.replace("-", " ")}`, "USD 0.00"]),
      ["Catch-up", "USD 0.00"],
    ]);
    expect(within(unchanged.panel).queryByRole("heading", { level: 4 })).toBeNull();
    expect(unchanged.panel.textContent).not.toContain(NO_FIGURES);
  });

  it("a failed dry run shows the banner of a failed job with the problem's title, the reference and Retry, and no sentence about figures", async () => {
    serveDryRuns({ state: "FAILED", problem: ENGINE_ERROR });
    const { drawer, panel } = await open();

    const banner = await bannerOf(panel, FAILED);
    expect(banner.getAttribute("data-tone")).toBe("negative");
    // Inserted after load: announced as an alert.
    expect(banner.getAttribute("role")).toBe("alert");
    expect(banner.textContent).toBe(`${FAILED}The computation failed${REFERENCE}Retry`);
    expect(within(banner).getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(panel.textContent).toBe(`Preview${banner.textContent}`);
    expect(panel.textContent).not.toContain(NO_FIGURES);
    expect(within(panel).queryByRole("term")).toBeNull();
    // The submission does not wait for the preview: the API decides it.
    expect(submitAvailable(drawer)).toBe(true);
  });

  it("a failed dry run whose problem carries messages shows each message in the place of the problem's title", async () => {
    const closed = "The period of this date is closed.";
    const stale = "The contract changed after the preview was asked for.";
    serveDryRuns({
      state: "FAILED",
      problem: {
        ...ENGINE_ERROR,
        title: "Check the highlighted fields",
        errors: [
          { field: "events.0.effective_date", message: closed },
          { field: null, message: stale },
        ],
      },
    });
    const { panel } = await open();

    const banner = await bannerOf(panel, FAILED);
    expect(banner.textContent).toBe(`${FAILED}${closed}${stale}${REFERENCE}Retry`);
  });

  it("Retry asks for the preview of the same fields again under a new key, and the figures of the new dry run take the banner's place", async () => {
    const submissions: unknown[] = [];
    const { asked } = serveDryRuns(
      { state: "FAILED", problem: ENGINE_ERROR },
      { state: "SUCCEEDED", result: resultWith({ summary: summary("12000.00") }) },
    );
    server.use(
      http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/events`), async ({ request }) => {
        submissions.push(await request.json());
        return new HttpResponse(null, { status: 500 });
      }),
    );
    const { panel } = await open();
    const banner = await bannerOf(panel, FAILED);
    expect(asked).toHaveLength(1);

    fireEvent.click(within(banner).getByRole("button", { name: "Retry" }));

    await within(panel).findByText("Catch-up");
    expect(asked).toHaveLength(2);
    expect(asked[1]?.body).toEqual(asked[0]?.body);
    // A second command, not the replay of the first: the kept key would answer the failed job again.
    expect(asked[0]?.key).toBeTruthy();
    expect(asked[1]?.key).toBeTruthy();
    expect(asked[1]?.key).not.toBe(asked[0]?.key);
    expect(within(panel).queryByRole("heading", { level: 4 })).toBeNull();
    expect(figures(panel)[6]).toEqual(["Catch-up", "USD +12,000.00"]);
    // "Retry" stands inside the drawer's form and submits nothing.
    expect(submissions).toEqual([]);
  });

  it("a cancelled dry run shows the banner under its own title, without a problem; one that left a summary lists its figures", async () => {
    serveDryRuns({ state: "CANCELLED" });
    const without = await open();

    const banner = await bannerOf(without.panel, CANCELLED);
    expect(banner.getAttribute("data-tone")).toBe("negative");
    expect(banner.textContent).toBe(`${CANCELLED}${REFERENCE}Retry`);
    expect(without.panel.textContent).toBe(`Preview${banner.textContent}`);
    cleanup();

    // 05 JOB-05: a handler that finished after the cancellation was asked for ends CANCELLED with
    // its result.
    serveDryRuns({ state: "CANCELLED", result: resultWith({ summary: summary("12000.00") }) });
    const withSummary = await open();

    await within(withSummary.panel).findByText("Catch-up");
    expect(figures(withSummary.panel)[6]).toEqual(["Catch-up", "USD +12,000.00"]);
    expect(within(withSummary.panel).queryByRole("heading", { level: 4 })).toBeNull();
  });

  it("a summary the API withholds from this reader shows the notice in the place of the figures: no figure, no Retry, and the submission stays available", async () => {
    serveDryRuns({
      state: "SUCCEEDED",
      result: resultWith({ summary: null, summary_withheld: true }),
    });
    const { drawer, panel } = await open();

    const notice = await bannerOf(panel, WITHHELD);
    expect(notice.getAttribute("data-tone")).toBe("info");
    // Inserted after load: announced politely.
    expect(notice.getAttribute("role")).toBe("status");
    expect(notice.textContent).toBe(`${WITHHELD}${WITHHELD_TEXT}`);
    expect(panel.textContent).toBe(`Preview${notice.textContent}`);
    expect(within(panel).queryByRole("term")).toBeNull();
    expect(within(panel).queryByRole("button")).toBeNull();
    expect(submitAvailable(drawer)).toBe(true);
  });

  it("the notice follows the member the API answers, true and nothing else: a result without a summary and without it reads as failed", async () => {
    for (const members of [
      { summary: null },
      { summary: null, summary_withheld: false },
      { summary: null, summary_withheld: "true" },
    ]) {
      serveDryRuns({ state: "SUCCEEDED", result: resultWith(members) });
      const { panel } = await open();

      const banner = await bannerOf(panel, FAILED);
      // No problem to name: the title, the reference and the action.
      expect(banner.textContent).toBe(`${FAILED}${REFERENCE}Retry`);
      expect(within(panel).queryByRole("heading", { name: WITHHELD })).toBeNull();
      cleanup();
    }
  }, 60_000);

  it("each of the five drawers shows the banner of its failed dry run and the notice of a withheld summary", async () => {
    for (const kind of ["delivery", "progress", "milestone", "cost", "return"] as const) {
      serveDryRuns({ state: "FAILED", problem: ENGINE_ERROR });
      const failed = await open(kind);
      const banner = await bannerOf(failed.panel, FAILED);
      expect(banner.textContent).toBe(`${FAILED}The computation failed${REFERENCE}Retry`);
      cleanup();

      serveDryRuns({
        state: "SUCCEEDED",
        result: resultWith({ summary: null, summary_withheld: true }),
      });
      const withheld = await open(kind);
      const notice = await bannerOf(withheld.panel, WITHHELD);
      expect(notice.textContent).toBe(`${WITHHELD}${WITHHELD_TEXT}`);
      cleanup();
    }
  }, 120_000);
});
