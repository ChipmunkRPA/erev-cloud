// What the crawl watches and drives on a page (docs/dev-guide.md DG-E2E-13; supervisor ruling R-67 (b);
// browser-QA findings Q-9 and Q-30). `Watch` records every API answer of a page with status 400 or
// above, every request that failed on the network and every uncaught script error, and knows when the
// page has settled: no request of its document in flight, none finished within the quiet window and no
// region marked busy. `inspect` names what a settled page shows that a working screen never shows: the route error
// boundary, "Page not found" and the no-access state. `driveGrids`, `driveFilters` and `panelTabs` act
// on the shared components only (DS-CMP-10 DataGrid, DS-CMP-13 FilterBar, DS-CMP-07 panel tabs), so a
// screen that uses them is driven without a line here.
import { expect, type Locator, type Page, type Request } from "@playwright/test";

/** No request finished within this window and none is in flight: the page has settled. */
const QUIET_MS = 300;
const SETTLE_MS = 45_000;
const API_PREFIX = "/api/";

export interface Finding {
  /** The step of the crawl during which it happened, for example `sort "As of"`. */
  readonly step: string;
  readonly what: string;
}

export interface ApiFailure {
  readonly method: string;
  /** Pathname and search of the request. */
  readonly path: string;
  readonly status: number;
  /** `<rule or type>: <detail>` of the problem body, when the answer carries one. */
  readonly detail: string;
}

export interface Allowed {
  readonly method: string;
  /** Matched against the pathname of the request. */
  readonly path: RegExp;
  /** Matched against the search string, when the entry is about one parameter. */
  readonly query?: RegExp;
  readonly status: number;
  /** The rule or document that makes this answer correct, or the item that owns the defect. */
  readonly why: string;
}

interface Problem {
  readonly type?: unknown;
  readonly title?: unknown;
  readonly detail?: unknown;
  readonly rule?: unknown;
  readonly code?: unknown;
}

function isApi(url: string): boolean {
  try {
    return new URL(url).pathname.startsWith(API_PREFIX);
  } catch {
    return false;
  }
}

function pathOf(url: string): string {
  const parsed = new URL(url);
  return `${parsed.pathname}${parsed.search}`;
}

function problemText(body: string): string {
  try {
    const problem = JSON.parse(body) as Problem;
    const name = [problem.rule, problem.code, problem.type].find(
      (value): value is string => typeof value === "string" && value !== "",
    );
    const said = [problem.detail, problem.title].find(
      (value): value is string => typeof value === "string" && value !== "",
    );
    return [name, said].filter((part) => part !== undefined).join(": ");
  } catch {
    return body.slice(0, 120);
  }
}

export class Watch {
  private readonly inflight = new Set<Request>();
  private readonly reading: Promise<void>[] = [];
  private readonly failures: ApiFailure[] = [];
  private readonly broken: string[] = [];
  /** The main frame's navigation request that has not committed, failed or ended yet. */
  private navigation: Request | null = null;
  private last = Date.now();
  /** API requests the page has made, for the record of the route. */
  requests = 0;

  constructor(private readonly page: Page) {
    page.on("request", (request) => {
      this.inflight.add(request);
      this.last = Date.now();
      if (isApi(request.url())) {
        this.requests += 1;
      }
      if (request.isNavigationRequest() && request.frame() === page.mainFrame()) {
        this.navigation = request;
      }
    });
    // A new document has committed: the one it replaces is gone, and with it what it left in flight.
    // While a route of the context intercepts requests (support/network.ts) the browser reports no
    // end for such a request — neither `requestfailed` nor `requestfinished` nor a response — so the
    // watch would wait for it until its timeout. A persona that signs in within its test lands on
    // Home, whose reads are in flight when the route under test opens. A navigation inside the
    // document (the router's own) sends no navigation request and forgets nothing.
    page.on("framenavigated", (frame) => {
      if (frame === page.mainFrame() && this.navigation !== null) {
        this.navigation = null;
        this.inflight.clear();
        this.last = Date.now();
      }
    });
    page.on("requestfinished", (request) => this.ended(request));
    page.on("requestfailed", (request) => {
      this.ended(request);
      const reason = request.failure()?.errorText ?? "";
      // A navigation or a superseded query aborts its requests; that is not a failure of the API.
      if (isApi(request.url()) && !reason.includes("ERR_ABORTED")) {
        this.broken.push(`${request.method()} ${pathOf(request.url())} failed: ${reason}`);
      }
    });
    page.on("response", (response) => {
      const request = response.request();
      // Answered is done: a body the page never reads (a 202 with its job) keeps the request open.
      this.done(request);
      if (response.status() < 400 || !isApi(response.url())) {
        return;
      }
      const failure = {
        method: request.method(),
        path: pathOf(response.url()),
        status: response.status(),
      };
      this.reading.push(
        response.text().then(
          (body) => {
            this.failures.push({ ...failure, detail: problemText(body) });
          },
          () => {
            this.failures.push({ ...failure, detail: "" });
          },
        ),
      );
    });
    page.on("pageerror", (error) => {
      this.broken.push(`uncaught script error: ${error.message}`);
    });
  }

  private done(request: Request): void {
    this.inflight.delete(request);
    this.last = Date.now();
  }

  /** A navigation that ends without a new document (a failure, a download) replaces nothing. */
  private ended(request: Request): void {
    this.done(request);
    if (request === this.navigation) {
      this.navigation = null;
    }
  }

  private async state(): Promise<string> {
    const [waiting] = this.inflight;
    if (waiting !== undefined) {
      return `waiting for ${waiting.method()} ${pathOf(waiting.url())}`;
    }
    if (Date.now() - this.last < QUIET_MS) {
      return "a request has just finished";
    }
    // Skeletons, running jobs and refreshing grids (DS-CMP-17, DS-CMP-18): still loading.
    const busy = await this.page
      .locator('[aria-busy="true"], [role="progressbar"]')
      .evaluateAll((elements) =>
        elements
          .filter((element) => element.checkVisibility())
          .map((element) => (element.textContent || element.getAttribute("aria-label")) ?? ""),
      );
    const [first] = busy;
    return first === undefined ? "settled" : `a region is busy: ${first.trim().slice(0, 80)}`;
  }

  /** Waits until the page has settled; the failure names what it was still waiting for. */
  async settle(): Promise<void> {
    await expect.poll(() => this.state(), { timeout: SETTLE_MS, intervals: [100] }).toBe("settled");
    await Promise.all(this.reading.splice(0));
  }

  /** The failures since the last call that no entry of `allowed` names, and the entries used. */
  drain(allowed: readonly Allowed[]): { readonly found: string[]; readonly used: Allowed[] } {
    const found = this.broken.splice(0);
    const used: Allowed[] = [];
    for (const failure of this.failures.splice(0)) {
      const [pathname = "", search = ""] = failure.path.split("?");
      const entry = allowed.find(
        (item) =>
          item.method === failure.method &&
          item.status === failure.status &&
          item.path.test(pathname) &&
          (item.query === undefined || item.query.test(search)),
      );
      if (entry === undefined) {
        const detail = failure.detail === "" ? "" : ` ${failure.detail}`;
        found.push(`${failure.method} ${failure.path} → ${String(failure.status)}${detail}`);
      } else {
        used.push(entry);
      }
    }
    return { found, used };
  }
}

/** What a settled page shows that a working screen does not. */
export async function inspect(page: Page): Promise<string[]> {
  const found: string[] = [];
  // X:route-error (SCREENS_B §12.4): an unhandled render or loader error replaced the screen.
  const boundary = page.getByTestId("X-banner-route-error");
  if ((await boundary.count()) > 0) {
    found.push(`the route error boundary rendered: ${(await boundary.first().innerText()).trim()}`);
  }
  // SCR-ST-05 no-access state, shared by the screens through `settings.access.title`.
  const refused = page.getByText(/^You do not have access to /);
  if ((await refused.count()) > 0) {
    found.push(`the no-access state rendered: ${(await refused.first().innerText()).trim()}`);
  }
  // SCR-URL-21: the screen dropped a `sort`, `f.*` or `view` value that its own controls wrote.
  const dropped = page.getByText("Some filters in the link were not recognised and were removed.");
  if ((await dropped.filter({ visible: true }).count()) > 0) {
    found.push(
      'the banner "Some filters in the link were not recognised and were removed." rendered',
    );
  }
  return found;
}

/** X:not-found (RT-98): the page-level empty state "Page not found". */
export function notFound(page: Page): Locator {
  return page.getByTestId("X-page").getByRole("heading", { level: 1, name: "Page not found" });
}

export interface Step {
  /** Runs after each action: waits for the page to settle and collects what went wrong. */
  readonly after: (step: string) => Promise<void>;
  /** Something the crawl did not drive, with its reason. */
  readonly note: (text: string) => void;
}

/** The accessible names of the visible grids, read in one step so that a redirect cannot stall it. */
function gridNames(page: Page): Promise<string[]> {
  return page.getByRole("grid").evaluateAll((elements) =>
    elements
      .filter((element) => element.checkVisibility())
      .map((element) => {
        const labelled = element.getAttribute("aria-labelledby");
        const label = labelled === null ? null : document.getElementById(labelled);
        return (label?.textContent ?? element.getAttribute("aria-label") ?? "").trim();
      }),
  );
}

const NEXT_SORT: Readonly<Record<string, string>> = {
  none: "ascending",
  ascending: "descending",
  descending: "none",
};

/**
 * DS-CMP-10: clicks every sortable column header of every visible grid once; a header is sortable when
 * it carries `aria-sort`. Grids named in `driven` are left alone and the driven ones are added.
 */
export async function driveGrids(page: Page, step: Step, driven: Set<string>): Promise<string[]> {
  const clicked: string[] = [];
  for (const name of await gridNames(page)) {
    if (name === "" || driven.has(`grid ${name}`)) {
      continue;
    }
    driven.add(`grid ${name}`);
    const columns = await page
      .getByRole("grid", { name, exact: true })
      .locator('[role="columnheader"][aria-sort]')
      .evaluateAll((elements) => elements.map((element) => element.getAttribute("data-column")));
    for (const column of columns) {
      if (column === null) {
        continue;
      }
      const header = page
        .getByRole("grid", { name, exact: true })
        .locator(`[role="columnheader"][data-column="${column}"]`);
      const label = (await header.locator("span").first().innerText()).trim();
      const before = (await header.getAttribute("aria-sort")) ?? "none";
      await header.locator("span").first().click();
      await expect
        .soft(header, `grid "${name}": the header "${label}" takes the sort`)
        .toHaveAttribute("aria-sort", NEXT_SORT[before] ?? "ascending");
      await step.after(`sort "${label}" of grid "${name}"`);
      clicked.push(`${name}: ${label}`);
    }
  }
  return clicked;
}

const FILTER_DATES = ["2026-09-01", "2026-09-30"] as const;
const FILTER_NUMBERS = ["1", "2"] as const;

/** Fills the editor of one filter field; the text says why it could not. */
async function fillEditor(page: Page, editor: Locator): Promise<string | null> {
  const loading = editor.getByRole("status").filter({ hasText: "Loading options" });
  await expect(loading).toHaveCount(0);
  const boxes = editor.getByRole("checkbox");
  if ((await boxes.count()) > 0) {
    await boxes.first().check();
    return null;
  }
  // Radio groups other than "Condition": Yes / No, and the date presets with "Custom range" last.
  for (const group of await editor.locator("fieldset").all()) {
    const legend = (await group.locator("legend").first().innerText()).trim();
    const radios = group.getByRole("radio");
    if (legend !== "Condition" && (await radios.count()) > 0) {
      await radios.first().check();
    }
  }
  // DS-CMP-21 selects and comboboxes: the first option of the list the control names.
  const choices = editor.getByRole("combobox");
  for (const choice of await choices.all()) {
    const options = page.locator(
      `[id="${(await choice.getAttribute("aria-controls")) ?? ""}"] [role="option"]`,
    );
    // A select opens on the click; a combobox input opens on ArrowDown.
    await choice.click();
    if ((await choice.getAttribute("aria-expanded")) !== "true") {
      await choice.press("ArrowDown");
    }
    await expect(choice).toHaveAttribute("aria-expanded", "true");
    if ((await options.count()) === 0) {
      return "its list offers no option";
    }
    await options.first().click();
  }
  const fields = editor.locator('input[type="text"]:not([role="combobox"])');
  const count = await fields.count();
  for (let index = 0; index < count; index += 1) {
    const field = fields.nth(index);
    const dated = (await field.locator("xpath=..").getByRole("button").count()) > 0;
    const decimal = (await field.getAttribute("inputmode")) === "decimal";
    const slot = index === 0 ? 0 : 1;
    await field.fill(dated ? FILTER_DATES[slot] : decimal ? FILTER_NUMBERS[slot] : "a");
  }
  const filled = (await editor.getByRole("radio").count()) + (await choices.count()) + count;
  return filled === 0 ? "its editor offers no control this crawl knows" : null;
}

/**
 * DS-CMP-13: for every visible filter bar, types one term into the quick search and applies every
 * field once with the first value its editor offers, removing each again. Bars named in `driven` are
 * left alone.
 */
export async function driveFilters(page: Page, step: Step, driven: Set<string>): Promise<string[]> {
  const applied: string[] = [];
  const bars = page
    .getByRole("toolbar", { name: "Filters", exact: true })
    .filter({ visible: true });
  // The bars and the key of each are read in one evaluation, as `gridNames` reads the grids. A count
  // and a later look at a bar are two moments: on SF-16 the bar counted was once gone at the look
  // (2026-10-03, seen once, not reproduced), and the look waited an action's whole time for it.
  const keys = await bars.evaluateAll((elements) =>
    elements.map((element) => element.parentElement?.getAttribute("data-testid") ?? null),
  );
  for (const [index, testId] of keys.entries()) {
    const key = `filters ${testId ?? String(index)}`;
    if (driven.has(key)) {
      continue;
    }
    driven.add(key);
    const bar = bars.nth(index);
    // A bar that left the page before its turn fails the node by name. The page settles, what it was
    // refused and the state it shows are collected under the bar's name, and the route goes on.
    const left = (await bars.count()) <= index;
    expect.soft(left, `${key}: the filter bar left the page before it was driven`).toBe(false);
    if (left) {
      await step.after(`${key}: the filter bar left the page before it was driven`);
      step.note(`${key}: the filter bar left the page before it was driven`);
      continue;
    }
    const add = bar.getByRole("button", { name: "Filter", exact: true });
    const search = bar.locator('input[type="search"]').first();
    if ((await search.count()) > 0) {
      const label = (await search.getAttribute("aria-label")) ?? "search";
      await search.fill("a");
      await expect.poll(() => new URL(page.url()).searchParams.get("q")).toBe("a");
      await step.after(`${key}: search "${label}"`);
      await search.fill("");
      await expect.poll(() => new URL(page.url()).searchParams.get("q")).toBeNull();
      await step.after(`${key}: search cleared`);
      applied.push(`${key}: search "${label}"`);
    }
    if ((await add.count()) === 0) {
      continue;
    }
    await add.click();
    const list = bar.getByRole("dialog", { name: "Filter", exact: true });
    const labels = (await list.getByRole("listitem").allInnerTexts()).map((text) => text.trim());
    await page.keyboard.press("Escape");
    await expect(list).toBeHidden();
    for (const label of labels) {
      await add.click();
      await list.getByRole("button", { name: label, exact: true }).click();
      const editor = bar.getByRole("dialog", { name: `${label} filter`, exact: true });
      await expect(editor).toBeVisible();
      const refusal = await fillEditor(page, editor);
      if (refusal === null) {
        await editor.getByRole("button", { name: "Apply", exact: true }).click();
      }
      // Applied: the chip with its remove button. Refused: the editor stays and says why.
      const remove = bar.getByRole("button", { name: `Remove filter: ${label}`, exact: true });
      const refused = editor.locator('[role="alert"], [aria-invalid="true"]');
      if (refusal === null) {
        await expect(remove.or(refused).first()).toBeVisible();
      }
      if (refusal !== null || (await remove.count()) === 0) {
        const said =
          refusal ??
          (await editor.locator('[role="alert"], [id$="-error"]').allInnerTexts()).join(" ");
        step.note(`${key}: field "${label}" not driven: ${said.trim()}`);
        await page.keyboard.press("Escape");
        await expect(editor).toBeHidden();
        continue;
      }
      await step.after(`${key}: field "${label}"`);
      await remove.click();
      await expect(remove).toHaveCount(0);
      await step.after(`${key}: field "${label}" removed`);
      applied.push(`${key}: ${label}`);
    }
  }
  return applied;
}

export interface PanelTab {
  readonly id: string;
  readonly name: string;
}

/** DS-CMP-07: the panel tabs of the page that are neither selected nor disabled. */
export async function panelTabs(page: Page): Promise<PanelTab[]> {
  const tabs = await page
    .getByRole("tablist")
    .getByRole("tab", { selected: false, disabled: false })
    .evaluateAll((elements) =>
      elements
        .filter((element) => element.checkVisibility())
        .map((element) => ({
          id: element.id,
          name: (element.textContent ?? "").replace(/\s+/g, " ").trim(),
        })),
    );
  return tabs.filter((tab) => tab.id !== "");
}
