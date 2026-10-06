// The closed world (docs/dev-guide.md DG-E2E-02 rev 1.277, DG-MK-e2e; SCREENS_B §0.5 RV-04 rev 1.98, §1.1,
// §15 rows SF-04, SF-08:report and SF-05; BUILD_SPEC RPS-6, RPS-7, CLO-23). `make e2e CLOSE=1` seeds
// WLD-T-01 with its close stage (CLO-22): AVM-US in book ASC606 is `closed` from January to August 2026,
// each month with its lock and the twelve datasets a lock freezes. The six projects of the ordinary run
// need every period of 2026 open and never see a lock; this project is the one place where the screens
// of a locked period meet the API, and it runs on no other world (playwright.config.ts).
//
// What the rows hold. A report the lock freezes opens as locked and is not refused: the page asks the
// lock's own entity, book and period and nothing else, its parameter fields are shown and unavailable,
// and the frozen rows are a table. A report the lock does not freeze opens on current figures and says
// so; it never says "as locked". The cockpit of the newest locked month offers no command of a close.
// And a Controller requests the permanent lock of the earliest locked month, which a holder of
// `period.close` alone is not offered (supervisor ruling R-83 (a)); that request is withdrawn again.
//
// The last row of the cockpit's group then takes the decision (RV-04 rev 1.101; register index 280):
// the request is made once more, the world's second Controller approves it, and January is permanently
// locked. Its current lock is then the permanent lock's record, which holds no dataset; a frozen report
// of January opens as locked on the lock of its close, which API-S-Period names as `dataset_lock`. A
// permanent lock cannot be undone: a project that runs on this world after this one finds January
// permanently locked and an approved request of AVM-US, and nothing else changed (DG-E2E-02).
import type { APIRequestContext, Locator, Page } from "@playwright/test";

import { ApiClient, json } from "../support/api";
import { type Persona, personaEmail } from "../support/auth";
import { type A11y, expect, type Screens, test } from "../support/fixtures";
import { nextCode } from "../support/totp";

const AUGUST = "entity=AVM-US&period=FY2026-P08&book=ASC606";
const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
/** DS-FMT-07: a timestamp as the screens print it. */
const TIMESTAMP = "\\d{2} [A-Z][a-z]{2} \\d{4} \\d{2}:\\d{2} UTC";
/**
 * A report run is a job the worker takes in turn: what waits for one states the job's bound, not the ten
 * seconds an assertion has for what the page does by itself.
 */
const REPORT_RUN_WAIT = { timeout: 60_000 } as const;

const AS_LOCKED = new RegExp(`^Showing Aug 2026 as locked on ${TIMESTAMP}\\.$`);
const CURRENT = new RegExp(`^Showing current figures\\. Aug 2026 was locked on ${TIMESTAMP}\\.$`);
const NOT_FROZEN = "A period lock does not freeze this report.";
const NO_PARAMETERS = "Figures as locked take no parameters. Show current figures to change them.";
/** RV-14: the title of a refused creation (422 `validation-failed`). */
const REFUSED = "Check the highlighted fields";
/** A computed colour that draws nothing. */
const TRANSPARENT = /^(transparent|rgba\(0, 0, 0, 0\))$/;

interface ListedLock {
  readonly id: string;
  readonly created_at: string;
}

interface ListedPeriod {
  readonly id: string;
  readonly state: string;
  readonly period: { readonly period_key: string };
  /** The record that locked the period last. */
  readonly current_lock: ListedLock | null;
  /** The lock whose datasets stand (04 §16.8): the lock of the period's close. */
  readonly dataset_lock: ListedLock | null;
}

/** E2E-02, the API first: a period of AVM-US in book ASC606 as `GET /periods` lists it. */
async function avmUsPeriod(request: APIRequestContext, periodKey: string): Promise<ListedPeriod> {
  const periods = await json<{ readonly items: readonly ListedPeriod[] }>(
    await request.get("/api/v1/periods", {
      params: { entity: "AVM-US", book: "ASC606", limit: 200 },
    }),
  );
  const found = periods.items.find((item) => item.period.period_key === periodKey);
  if (found === undefined) {
    throw new Error(`GET /periods lists no AVM-US ASC606 ${periodKey} period`);
  }
  return found;
}

/**
 * The lock whose datasets stand for August 2026: the one the seed's close stage made. While a period
 * is closed, API-S-Period names one record as its current lock and as that lock.
 */
async function augustLock(request: APIRequestContext): Promise<string> {
  const august = await avmUsPeriod(request, "FY2026-P08");
  expect(august.state, "the world was seeded with its close stage (make e2e CLOSE=1)").toBe(
    "closed",
  );
  const lockId = august.dataset_lock?.id ?? "";
  expect(lockId).toMatch(new RegExp(`^${UUID}$`));
  expect(august.current_lock?.id).toBe(lockId);
  return lockId;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * DS-FMT-17: an instant as the screens print it, "03 Sep 2026 09:14 UTC". The API states its instants
 * in UTC (`…Z`), so the text is read off the instant itself; no date is constructed (DG-FE-20).
 */
function printed(instant: string): string {
  const read = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):\d{2}(?:\.\d+)?Z$/.exec(instant);
  if (read === null) {
    throw new Error(`not an RFC 3339 UTC instant: ${instant}`);
  }
  const [, year = "", month = "", day = "", hour = "", minute = ""] = read;
  return `${day} ${MONTHS[Number(month) - 1] ?? ""} ${year} ${hour}:${minute} UTC`;
}

interface Creation {
  readonly report_code: string;
  readonly output_format: string;
  readonly parameters: Readonly<Record<string, unknown>>;
}

/** The report-run creations a page sends from here on, in order (RV-01: one for a parameter set). */
function creationsOf(page: Page): Creation[] {
  const sent: Creation[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === "/api/v1/report-runs") {
      sent.push(request.postDataJSON() as Creation);
    }
  });
  return sent;
}

interface StoredRun {
  readonly status: string;
  readonly period_lock_id: string | null;
  readonly row_count: number | null;
}

/** The run the address names, once the page has written it, as the API stores it. */
async function storedRun(page: Page): Promise<StoredRun> {
  await expect(page).toHaveURL(new RegExp(`[?&]run=${UUID}(&|$)`), REPORT_RUN_WAIT);
  const runId = new URL(page.url()).searchParams.get("run") ?? "";
  const path = `/api/v1/report-runs/${runId}`;
  await expect
    .poll(async () => (await json<StoredRun>(await page.request.get(path))).status, {
      ...REPORT_RUN_WAIT,
      intervals: [500],
    })
    .not.toMatch(/^(QUEUED|RUNNING)$/);
  return json<StoredRun>(await page.request.get(path));
}

interface Fields {
  /** The parameter fields of the toolbar. */
  readonly count: number;
  /** Those of them that take input, by name. */
  readonly open: readonly string[];
}

/** The parameter fields of a toolbar. SF-04's "Layout" is the screen's own control and no parameter. */
function fieldsOf(bar: Locator): Promise<Fields> {
  return bar.evaluate((element) => {
    const fields = [
      ...element.querySelectorAll<HTMLElement>(
        '[role="combobox"], [role="radio"], input:not([type="hidden"])',
      ),
    ].filter(
      (field) => field.closest('[role="radiogroup"]')?.getAttribute("aria-label") !== "Layout",
    );
    const open = fields.filter(
      (field) =>
        field.getAttribute("aria-disabled") !== "true" &&
        !(field instanceof HTMLInputElement && field.disabled),
    );
    return {
      count: fields.length,
      open: open.map((field) => field.getAttribute("name") ?? field.id),
    };
  });
}

/** The sentence a toolbar is described by, under its fields; null where it has none. */
async function noteOf(page: Page, bar: Locator): Promise<string | null> {
  const id = await bar.getAttribute("aria-describedby");
  return id === null ? null : page.locator(`[id="${id}"]`).textContent();
}

/** The top bar is complete before a capture: the context pill loads after the page. */
async function settled(page: Page): Promise<void> {
  await expect(page.getByRole("group", { name: "Accounting context" })).toBeVisible();
}

/**
 * Approve the open request with a comment; the SCR-PERM-05 step-up takes a fresh code (BS1-D-19). The
 * twin of the approvals rows' helper in screens.spec.ts, which that file keeps to itself.
 */
async function approveOpenRequest(page: Page, persona: Persona, comment: string): Promise<void> {
  const form = page.getByRole("form", { name: "Decision" });
  await form.getByRole("textbox", { name: /^Comment/ }).fill(comment);
  await form.getByRole("button", { name: "Approve", exact: true }).click();
  const toast = page.getByText(/^Approved: /);
  const stepUp = page.getByRole("dialog", { name: "Confirm with your authenticator" });
  // The decision executes the lock: its answer is a command's, not what the page does by itself.
  await expect(toast.or(stepUp).first()).toBeVisible({ timeout: 30_000 });
  if (await stepUp.isVisible()) {
    const wrong = stepUp.getByText(
      "That code did not match. Check your authenticator app and try again.",
    );
    let refused: number | undefined;
    for (let attempt = 0; attempt < 3 && (await stepUp.isVisible()); attempt += 1) {
      const { code, step } = await nextCode(personaEmail(persona), refused);
      await stepUp.getByRole("textbox", { name: /^Authentication code/ }).fill(code);
      await stepUp.getByRole("button", { name: "Confirm", exact: true }).click();
      await expect(async () => {
        expect((await stepUp.isHidden()) || (await wrong.isVisible())).toBe(true);
      }).toPass({ timeout: 15_000 });
      refused = step;
    }
  }
  await expect(toast).toBeVisible({ timeout: 30_000 });
}

interface Locked {
  readonly page: Page;
  /** `SF-04` or `SF-08`: the prefix of the screen's test hooks. */
  readonly screen: string;
  readonly lockId: string;
  readonly sent: readonly Creation[];
  /** What the creation must be, whole. */
  readonly creation: Creation;
  /** The banner's sentence; August's, with any time, where the row does not state its own. */
  readonly sentence?: RegExp | string;
}

/**
 * RV-04 rev 1.98 on a page the lock freezes: the address names the lock, the page says "as locked", one
 * run was asked — the lock with its own selectors and nothing else — and the API made it from the lock.
 */
async function expectAsLocked({
  page,
  screen,
  lockId,
  sent,
  creation,
  sentence = AS_LOCKED,
}: Locked): Promise<StoredRun> {
  // The creation first: what the page asks is what the row is about, and a set the API would refuse
  // fails here, by what it holds, instead of as a run that never comes.
  await expect.poll(() => sent.length).toBeGreaterThan(0);
  expect(sent).toEqual([creation]);
  const run = await storedRun(page);
  expect(sent).toHaveLength(1);
  await expect(page).toHaveURL(new RegExp(`[?&]snapshot=${lockId}(&|$)`));
  expect(run).toMatchObject({ status: "SUCCEEDED", period_lock_id: lockId });
  await expect(page.getByRole("heading", { name: sentence, exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Show current figures" })).toBeVisible();
  await expect(page.getByTestId(`${screen}-run-stamp`)).toContainText(
    new RegExp(`As locked on ${TIMESTAMP}`),
    REPORT_RUN_WAIT,
  );
  await expect(page.getByRole("heading", { name: REFUSED })).toHaveCount(0);
  // The fields are shown and take no input, and the page says why under them.
  const bar = page.getByTestId(`${screen}-filter-bar`);
  const fields = await fieldsOf(bar);
  expect(fields.count).toBeGreaterThan(0);
  expect(fields.open).toEqual([]);
  expect(await noteOf(page, bar)).toBe(NO_PARAMETERS);
  await expect(bar.getByRole("button", { name: "Run report" })).toBeEnabled();
  return run;
}

/**
 * The creation of an as-locked run: the lock, its entity and book, and the period keys the report has,
 * each the lock's period — August where the row names no other.
 */
function lockedCreation(
  reportCode: string,
  lockId: string,
  periodKeys: readonly string[],
  period = "FY2026-P08",
): Creation {
  return {
    report_code: reportCode,
    output_format: "JSON",
    parameters: {
      period_lock_id: lockId,
      entity_codes: ["AVM-US"],
      book: "ASC606",
      ...Object.fromEntries(periodKeys.map((key) => [key, period])),
    },
  };
}

test.describe("SF-04 Schedules as locked (RT-25 /schedules), persona marcus", () => {
  test("SF-04 as locked marcus", async ({ personas, screens, a11y }) => {
    const page = await personas.page("marcus");
    const lockId = await augustLock(page.request);
    const sent = creationsOf(page);
    await page.goto(`/schedules?${AUGUST}`);
    await expect(page.getByRole("heading", { level: 1, name: "Schedules" })).toBeVisible();
    // Not the fiscal year, the as-of date and the screen's three choices: the API refuses each by name.
    const run = await expectAsLocked({
      page,
      screen: "SF-04",
      lockId,
      sent,
      creation: lockedCreation("revenue_waterfall", lockId, ["from_period_key", "to_period_key"]),
    });
    // The range the bar shows is the lock's month, not the fiscal year a lock does not hold.
    const bar = page.getByTestId("SF-04-filter-bar");
    await expect(bar.getByRole("combobox", { name: "From" })).toContainText("Aug 2026");
    await expect(bar.getByRole("combobox", { name: "To" })).toContainText("Aug 2026");
    // The frozen dataset is long form — a row an obligation of the one month — and the grid shows it;
    // there is no revenue by period to draw a chart from.
    expect(run.row_count).toBeGreaterThan(0);
    const grid = page
      .getByTestId("SF-04-grid-waterfall")
      .getByRole("grid", { name: "Revenue waterfall" });
    await expect(grid).toBeVisible();
    // A header cell holds its label and its options button, so its name in a browser begins with
    // the label and is not the label alone ("Contract Column options: Contract").
    await expect(grid.getByRole("columnheader", { name: /^Contract\b/ })).toBeAttached();
    await expect(page.getByTestId("SF-04-chart-waterfall")).toHaveCount(0);
    await settled(page);
    await screens.capture(page, "sf-04-locked", { surface: "SF-04" });
    await a11y.check(page, "SF-04 as locked");
  });
});

test.describe("SF-08:report Report view as locked (RT-32 /reports/:reportCode), persona marcus", () => {
  test("SF-08:report revenue_waterfall as locked marcus", async ({ personas, screens, a11y }) => {
    const page = await personas.page("marcus");
    const lockId = await augustLock(page.request);
    const sent = creationsOf(page);
    await page.goto(`/reports/revenue_waterfall?${AUGUST}`);
    await expect(page.getByRole("heading", { level: 1, name: "Revenue waterfall" })).toBeVisible();
    const run = await expectAsLocked({
      page,
      screen: "SF-08",
      lockId,
      sent,
      creation: lockedCreation("revenue_waterfall", lockId, ["from_period_key", "to_period_key"]),
    });
    expect(run.row_count).toBeGreaterThan(0);
    await expect(
      page.getByTestId("SF-08-grid-revenue-waterfall").getByRole("grid", {
        name: "Revenue waterfall",
      }),
    ).toBeVisible();
    await expect(page.getByTestId("SF-08-chart-revenue-waterfall")).toHaveCount(0);
    await settled(page);
    await screens.capture(page, "sf-08-report-revenue-waterfall-locked", {
      surface: "SF-08:report",
    });
    await a11y.check(page, "SF-08:report revenue_waterfall as locked");
  });

  test("SF-08:report modification_register as locked marcus", async ({
    personas,
    screens,
    a11y,
  }, testInfo) => {
    const page = await personas.page("marcus");
    const lockId = await augustLock(page.request);
    const sent = creationsOf(page);
    await page.goto(`/reports/modification_register?${AUGUST}`);
    await expect(
      page.getByRole("heading", { level: 1, name: "Modification register" }),
    ).toBeVisible();
    // The register has no period key: its as-locked run is the lock, the entity and the book — not
    // the two dates of the month, which the API refuses by name.
    const run = await expectAsLocked({
      page,
      screen: "SF-08",
      lockId,
      sent,
      creation: lockedCreation("modification_register", lockId, []),
    });
    // DS-CMP-21 "Disabled", in the browser: the register's two dates and its contract are text
    // inputs, and each keeps its fill and its border while it takes no input. CSS counts a disabled
    // input as read-only, and the control style's read-only rule once took both away: the three labels
    // stood over nothing (the closed world's first captures). jsdom computes no such style.
    const drawn = await page
      .getByTestId("SF-08-filter-bar")
      .locator('input:disabled:not([type="hidden"])')
      .evaluateAll((inputs) =>
        inputs.map((input) => {
          const style = getComputedStyle(input);
          return {
            name: input.getAttribute("name"),
            border: style.borderTopColor,
            borderWidth: style.borderTopWidth,
            fill: style.backgroundColor,
          };
        }),
      );
    expect(drawn.map((field) => field.name)).toEqual([
      "p-from_date",
      "p-to_date",
      "p-contract_external_id",
    ]);
    for (const field of drawn) {
      expect(field.border, `${field.name ?? ""}: the border`).not.toMatch(TRANSPARENT);
      expect(field.borderWidth, `${field.name ?? ""}: the border's width`).not.toBe("0px");
      expect(field.fill, `${field.name ?? ""}: the fill`).not.toMatch(TRANSPARENT);
    }
    // A lock freezes the register of its month as it stands, empty or not: the page shows the frozen
    // rows where the dataset holds some and the run's empty copy where it holds none.
    testInfo.annotations.push({
      type: "frozen MODIFICATION_REGISTER rows of AVM-US August 2026",
      description: String(run.row_count),
    });
    if (run.row_count === 0) {
      await expect(
        page.getByRole("heading", { level: 2, name: "No rows in this run" }),
      ).toBeVisible();
    } else {
      await expect(
        page.getByTestId("SF-08-grid-modification-register").getByRole("grid", {
          name: "Modification register",
        }),
      ).toBeVisible();
    }
    await settled(page);
    await screens.capture(page, "sf-08-report-modification-register-locked", {
      surface: "SF-08:report",
    });
    await a11y.check(page, "SF-08:report modification_register as locked");
  });

  test("SF-08:report rpo as locked marcus", async ({ personas, screens, a11y }) => {
    const page = await personas.page("marcus");
    const lockId = await augustLock(page.request);
    const sent = creationsOf(page);
    await page.goto(`/reports/rpo?${AUGUST}`);
    await expect(
      page.getByRole("heading", { level: 1, name: "Remaining performance obligations" }),
    ).toBeVisible();
    const run = await expectAsLocked({
      page,
      screen: "SF-08",
      lockId,
      sent,
      creation: lockedCreation("rpo", lockId, ["period_key"]),
    });
    expect(run.row_count).toBeGreaterThan(0);
    await expect(
      page.getByTestId("SF-08-grid-remaining-performance-obligations").getByRole("grid", {
        name: "Remaining performance obligations",
      }),
    ).toBeVisible();
    // The second section stands under its own heading, with the frozen rows that state it or none.
    await expect(page.getByTestId("SF-08-grid-exempt-contracts")).toBeVisible();
    await settled(page);
    await screens.capture(page, "sf-08-report-rpo-locked", { surface: "SF-08:report" });
    await a11y.check(page, "SF-08:report rpo as locked");
  });
});

/**
 * RV-04 rev 1.98 on a report the lock does not freeze: one creation without a lock, current figures said
 * as current, and nothing that offers or names a locked source.
 */
async function expectCurrent(
  page: Page,
  sent: readonly Creation[],
  reportCode: string,
): Promise<StoredRun> {
  // The creation first, as in `expectAsLocked`: a lock sent here is the defect, and fails by name.
  await expect.poll(() => sent.length).toBeGreaterThan(0);
  expect(sent[0]?.report_code).toBe(reportCode);
  expect(sent[0]?.parameters).not.toHaveProperty("period_lock_id");
  const run = await storedRun(page);
  expect(sent).toHaveLength(1);
  await expect(page).not.toHaveURL(/[?&]snapshot=/);
  expect(run).toMatchObject({ status: "SUCCEEDED", period_lock_id: null });
  await expect(page.getByRole("heading", { name: CURRENT })).toBeVisible();
  await expect(page.getByText(NOT_FROZEN, { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^Showing .+ as locked on / })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Show as locked" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Show current figures" })).toHaveCount(0);
  await expect(page.getByTestId("SF-08-run-stamp")).toContainText(
    "Current, known at",
    REPORT_RUN_WAIT,
  );
  await expect(page.getByRole("heading", { name: REFUSED })).toHaveCount(0);
  // The fields the report has take input, and no sentence says otherwise.
  const bar = page.getByTestId("SF-08-filter-bar");
  const fields = await fieldsOf(bar);
  expect(fields.open).toHaveLength(fields.count);
  expect(await noteOf(page, bar)).toBeNull();
  return run;
}

/**
 * The page shows the rows of the run it made. The API can know a run's end a poll before the page does:
 * the stamp then reads "Rows —" over a skeleton, and a capture taken there shows a page that is still
 * loading (the control's first capture did).
 */
async function expectRows(page: Page): Promise<void> {
  await expect(
    page.locator('[data-testid^="SF-08-grid-"]').getByRole("grid").first(),
  ).toBeVisible();
}

test.describe("SF-08:report Report view of a report a lock does not freeze (RT-32), persona marcus", () => {
  // It takes `period_lock_id` and has no lock dataset: sent the lock, the API refuses it by name. The
  // row is RV-04's own example of such a report, and one the API builds: the extracts take a lock too,
  // and their creation is answered "This report is not available yet." until RPS-14 — the first run
  // of this world met that with `extract_contracts`.
  test("SF-08:report revenue_from_opening_liability on a locked period marcus", async ({
    personas,
    screens,
    a11y,
  }) => {
    const page = await personas.page("marcus");
    await augustLock(page.request);
    const sent = creationsOf(page);
    await page.goto(`/reports/revenue_from_opening_liability?${AUGUST}`);
    await expect(
      page.getByRole("heading", { level: 1, name: "Revenue from the opening contract liability" }),
    ).toBeVisible();
    const run = await expectCurrent(page, sent, "revenue_from_opening_liability");
    // The capture is of the run's rows: AVM-US recognised revenue from its opening contract liability
    // in August.
    expect(run.row_count).toBeGreaterThan(0);
    await expectRows(page);
    await settled(page);
    await screens.capture(page, "sf-08-report-revenue-from-opening-liability-locked-period", {
      surface: "SF-08:report",
    });
    await a11y.check(page, "SF-08:report revenue_from_opening_liability on a locked period");
  });

  // It takes no `period_lock_id`: the lock was sent nowhere, and the page said "as locked" all the same.
  test("SF-08:report judgement_register on a locked period marcus", async ({ personas }) => {
    const page = await personas.page("marcus");
    await augustLock(page.request);
    const sent = creationsOf(page);
    await page.goto(`/reports/judgement_register?${AUGUST}`);
    await expect(page.getByRole("heading", { level: 1, name: "Judgement register" })).toBeVisible();
    const run = await expectCurrent(page, sent, "judgement_register");
    // The register's rows or, where the run holds none, the title the register states for that
    // (SCREENS_B §5.6.2 RPT-28) over the dates the run took — the view's defaults for August, the
    // fiscal year's first day to the month's last. "No rows in this run" is the title of a report
    // that states none of its own: the run of 2026-10-02 20:19 asked this page for it, and failed.
    if ((run.row_count ?? 0) === 0) {
      await expect(
        page.getByRole("heading", {
          level: 2,
          name: "No judgement records from 01 Jan 2026 to 31 Aug 2026",
          exact: true,
        }),
      ).toBeVisible();
    } else {
      await expectRows(page);
    }
  });
});

/**
 * BUILD_SPEC CLO-23 (SCREENS_B §1.1; PRD ACT-27, SM-07; supervisor ruling R-83 (a), whose e2e step this
 * is): the permanent lock is a Controller's request. January 2026 is the earliest period of AVM-US, so
 * no earlier period holds it back; the months after it are locked and stay as they are. The request's
 * row ends by withdrawing what it asked. The row after it takes the decision (RV-04 rev 1.101; register
 * index 280): the request made again, the second Controller's approval, January permanently locked —
 * and a frozen report of January, as locked on the lock of its close.
 *
 * One worker runs the three rows in this order. The first reads "Permanently lock Jan 2026 first." on
 * August's cockpit and the second finds January `closed`: both are true only until the third has run,
 * and what the third does cannot be undone.
 */
test.describe("SF-05 Close cockpit of a locked period (RT-26 /close/:entity/:book/:period), personas maya, marcus and elena", () => {
  test.describe.configure({ mode: "serial" });

  const COCKPIT = "/close/AVM-US/ASC606/FY2026-P01";
  const JANUARY = "entity=AVM-US&period=FY2026-P01&book=ASC606";
  const TITLE = "Close · AVM-US · Jan 2026 · ASC 606";
  const SUMMARY = "Permanently lock FY2026-P01 for AVM-US in book ASC606";
  const COMMENT =
    "January 2026 is final: the year-end audit of AVM-US has signed off its balances.";

  // BUILD_SPEC CLO-23 step "SF-05 locked" (SCREENS_B §15 row SF-05 `marcus`; PRD J-13-AC-5), owed since
  // the ordinary world lost its seeded lock: the cockpit of the newest locked month.
  test("SF-05 locked marcus", async ({ personas, screens, a11y }) => {
    const page = await personas.page("marcus");
    await augustLock(page.request);
    await page.goto("/close/AVM-US/ASC606/FY2026-P08");
    await expect(
      page.getByRole("heading", { level: 1, name: "Close · AVM-US · Aug 2026 · ASC 606" }),
    ).toBeVisible();
    await expect(
      page.getByTestId("SF-05-page").getByText("Locked", { exact: true }).first(),
    ).toBeVisible();
    // September is the first open period, so the sentence is true of this month.
    await expect(
      page.getByRole("heading", {
        name: "Aug 2026 is locked for AVM-US. Late events post to Sep 2026 with origin period Aug 2026.",
      }),
    ).toBeVisible();
    // J-13-AC-5: a locked period offers none of the commands of a close.
    for (const name of ["Start soft close", "Run close", "Submit for lock", "Lock period"]) {
      await expect(page.getByRole("button", { name, exact: true })).toHaveCount(0);
    }
    // SM-07: periods are permanently locked in their order — January before August — and the item
    // says so instead of opening its dialog.
    await page.getByRole("button", { name: "More close actions" }).click();
    const item = page.getByRole("menuitem", { name: "Permanently lock" });
    await expect(item).toHaveAttribute("aria-disabled", "true");
    const reason = (await item.getAttribute("aria-describedby")) ?? "";
    await expect(page.locator(`[id="${reason}"]`)).toHaveText("Permanently lock Jan 2026 first.");
    await page.keyboard.press("Escape");
    await expect(item).toHaveCount(0);
    await settled(page);
    await screens.capture(page, "sf-05-locked", { surface: "SF-05" });
    await a11y.check(page, "SF-05 locked");
  });

  test("SF-05 permanent lock request maya and marcus", async ({ personas, screens, a11y }) => {
    await test.step("maya holds period.close and not period.lock: the request is not offered", async () => {
      const maya = await personas.page("maya");
      expect((await avmUsPeriod(maya.request, "FY2026-P01")).state).toBe("closed");
      await maya.goto(COCKPIT);
      await expect(maya.getByRole("heading", { level: 1, name: TITLE })).toBeVisible();
      await expect(
        maya.getByRole("heading", { name: /^Jan 2026 is locked for AVM-US\. / }),
      ).toBeVisible();
      // Her bar is drawn — the judgement record is hers to prepare — and holds no overflow: the
      // permanent lock is its one item on a locked period.
      await expect(
        maya.getByRole("button", { name: "Record estimate-versus-error judgement" }),
      ).toBeVisible();
      await expect(maya.getByRole("button", { name: "More close actions" })).toHaveCount(0);
      await expect(maya.getByRole("menuitem", { name: "Permanently lock" })).toHaveCount(0);
    });

    const marcus = await personas.page("marcus");
    try {
      await requestAndWithdraw(marcus, screens, a11y);
    } finally {
      // Whatever the step above met, it leaves no request pending: a pending request of AVM-US
      // holds the lock of every period of the entity for the project that runs after this one. In
      // the step's own course the request is withdrawn on its page and nothing is left to do here.
      const api = new ApiClient(marcus.request);
      for (const id of await pendingLockRequests(marcus.request)) {
        await api.command("POST", `/api/v1/approvals/${id}/withdraw`, { comment: null });
      }
      expect(await pendingLockRequests(marcus.request)).toEqual([]);
    }
  });

  // SCREENS_B §0.5 RV-04 rev 1.101 (register index 280; 04 §16.8 API-S-Period `dataset_lock`): the
  // decision the row above stops before. `elena` is the world's second Controller (PRD WLD-U-04); the
  // requester cannot decide his own request (R-83 (a)), and her decision takes her step-up.
  test("SF-08:report rpo of a permanently locked period marcus and elena", async ({
    personas,
    screens,
    a11y,
  }) => {
    const marcus = await personas.page("marcus");
    const closed = await avmUsPeriod(marcus.request, "FY2026-P01");
    expect(closed.state).toBe("closed");
    const close = closed.dataset_lock;
    if (close === null) {
      throw new Error("GET /periods names no dataset_lock for the closed January of AVM-US");
    }
    expect(closed.current_lock?.id).toBe(close.id);

    const href = await askPermanentLock(marcus, false);
    await test.step("elena approves the request, with her step-up", async () => {
      const elena = await personas.page("elena");
      await elena.goto(href);
      await expect(
        elena.getByRole("region", { name: `Request details: ${SUMMARY}` }),
      ).toBeVisible();
      await approveOpenRequest(
        elena,
        "elena",
        "The audit's sign-off is on file: January is final.",
      );
    });

    await test.step("the API: January is permanently locked, and the lock of its close still holds its datasets", async () => {
      await expect
        .poll(async () => (await avmUsPeriod(marcus.request, "FY2026-P01")).state)
        .toBe("permanently_locked");
      const sealed = await avmUsPeriod(marcus.request, "FY2026-P01");
      // The period's current lock is the permanent lock's record now; the datasets are the close's.
      expect(sealed.current_lock?.id).toMatch(new RegExp(`^${UUID}$`));
      expect(sealed.current_lock?.id).not.toBe(close.id);
      expect(sealed.dataset_lock?.id).toBe(close.id);
    });

    await test.step("marcus: rpo of January opens as locked on the lock of its close, at the time of the close", async () => {
      const sent = creationsOf(marcus);
      await marcus.goto(`/reports/rpo?${JANUARY}`);
      await expect(
        marcus.getByRole("heading", { level: 1, name: "Remaining performance obligations" }),
      ).toBeVisible();
      // The lock in the address, in the creation and on the stored run is the close's — not the
      // permanent lock's record, whose run the API refuses — and the sentence dates the figures by it.
      const run = await expectAsLocked({
        page: marcus,
        screen: "SF-08",
        lockId: close.id,
        sent,
        creation: lockedCreation("rpo", close.id, ["period_key"], "FY2026-P01"),
        sentence: `Showing Jan 2026 as locked on ${printed(close.created_at)}.`,
      });
      expect(run.row_count).toBeGreaterThan(0);
      await expect(
        marcus.getByTestId("SF-08-grid-remaining-performance-obligations").getByRole("grid", {
          name: "Remaining performance obligations",
        }),
      ).toBeVisible();
      await settled(marcus);
      await screens.capture(marcus, "sf-08-report-rpo-permanently-locked", {
        surface: "SF-08:report",
      });
      await a11y.check(marcus, "SF-08:report rpo of a permanently locked period");

      // Current figures say when the period's figures were frozen, and offer them again.
      await marcus.getByRole("button", { name: "Show current figures" }).click();
      await expect(
        marcus.getByRole("heading", {
          name: `Showing current figures. Jan 2026 was locked on ${printed(close.created_at)}.`,
          exact: true,
        }),
      ).toBeVisible();
      await expect(marcus.getByRole("button", { name: "Show as locked" })).toBeVisible();
    });
  });

  /**
   * `marcus` asks for the permanent lock of January on its cockpit — the comment is required, ten
   * characters of it at least (SB-R-05), which `proveComment` shows first — and the banner stands
   * with its link, which is returned.
   */
  async function askPermanentLock(marcus: Page, proveComment: boolean): Promise<string> {
    await marcus.goto(COCKPIT);
    await expect(marcus.getByRole("heading", { level: 1, name: TITLE })).toBeVisible();
    await marcus.getByRole("button", { name: "More close actions" }).click();
    await marcus.getByRole("menuitem", { name: "Permanently lock" }).click();
    const dialog = marcus.getByRole("alertdialog", {
      name: "Permanently lock Jan 2026 for AVM-US?",
    });
    await expect(dialog).toContainText("A permanently locked period can never be reopened.");
    const request = dialog.getByRole("button", { name: "Request permanent lock" });
    if (proveComment) {
      await request.click();
      await expect(dialog.getByText("Enter at least 10 characters.")).toBeVisible();
    }
    await dialog.getByRole("textbox", { name: /^Comment \(required\)/ }).fill(COMMENT);
    await request.click();
    const link = marcus
      .getByTestId("SF-05-banner-permanent-lock-request")
      .getByRole("link", { name: "View request" });
    await expect(link).toHaveAttribute("href", new RegExp(`^/approvals/requests/${UUID}$`));
    await expect(dialog).toHaveCount(0);
    return (await link.getAttribute("href")) ?? "";
  }

  /** The permanent-lock requests `marcus` prepared for AVM-US that are still pending. */
  async function pendingLockRequests(request: APIRequestContext): Promise<readonly string[]> {
    const listed = await json<{ readonly items: readonly { readonly id: string }[] }>(
      await request.get("/api/v1/approvals", {
        params: {
          status: "PENDING",
          subject_type: "PERIOD_LOCK",
          preparer: "me",
          entity: "AVM-US",
          limit: 50,
        },
      }),
    );
    return listed.items.map((item) => item.id);
  }

  async function requestAndWithdraw(marcus: Page, screens: Screens, a11y: A11y): Promise<void> {
    await test.step("marcus holds period.lock: the request with its comment, then the banner with its link", async () => {
      const href = await askPermanentLock(marcus, true);
      const banner = marcus.getByTestId("SF-05-banner-permanent-lock-request");
      const link = banner.getByRole("link", { name: "View request" });
      // E2E-02, the API: the request the banner names is the one the command made.
      const approval = await json<{
        readonly status: string;
        readonly summary: string;
        readonly comment: string | null;
        readonly preparer: { readonly display_name: string };
      }>(await marcus.request.get(`/api/v1/approvals/${href.split("/").at(-1) ?? ""}`));
      expect(approval).toMatchObject({ status: "PENDING", summary: SUMMARY, comment: COMMENT });
      await expect(
        banner.getByRole("heading", {
          name: new RegExp(
            `^Permanent lock requested by ${approval.preparer.display_name} on ${TIMESTAMP}\\.$`,
          ),
        }),
      ).toBeVisible();
      // R-83 (b): while the request is pending the action is not offered again, and the period stays
      // as it was until a second Controller decides.
      await expect(marcus.getByRole("button", { name: "More close actions" })).toHaveCount(0);
      expect((await avmUsPeriod(marcus.request, "FY2026-P01")).state).toBe("closed");
      await settled(marcus);
      await screens.capture(marcus, "sf-05-permanent-lock-request", { surface: "SF-05" });
      await a11y.check(marcus, "SF-05 permanent lock request");

      await link.click();
      await expect(marcus).toHaveURL(new RegExp(`${href}$`));
      await expect(
        marcus.getByRole("region", { name: `Request details: ${approval.summary}` }),
      ).toBeVisible();

      // The request is withdrawn where it was read. A pending request of AVM-US holds the lock of
      // every period of the entity (close gate `APPROVALS_CLEARED`), and the projects that run on
      // this world after this one find it as it was seeded: January stays closed, and no request
      // is pending.
      await marcus.getByRole("button", { name: "Withdraw request" }).click();
      const confirm = marcus.getByRole("alertdialog", { name: "Withdraw this request?" });
      await confirm.getByRole("button", { name: "Withdraw request" }).click();
      await expect(
        marcus
          .getByRole("region", { name: "Messages" })
          .getByText(`Withdrawn: ${approval.summary}.`),
      ).toBeVisible();
      const after = await json<{ readonly status: string }>(
        await marcus.request.get(`/api/v1/approvals/${href.split("/").at(-1) ?? ""}`),
      );
      expect(after.status).toBe("WITHDRAWN");
      expect((await avmUsPeriod(marcus.request, "FY2026-P01")).state).toBe("closed");
    });
  }
});
