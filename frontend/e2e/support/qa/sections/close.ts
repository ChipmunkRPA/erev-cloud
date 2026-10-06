// Section C of the pass: September 2026 of AVM-US in ASC 606 from the open period to its lock, as
// PRD J-13 walks it — the blockers cleared, the soft close, the close run, the journal run with its
// approval, export and the ledger's reference, the two reconciliations with their review, the
// submission for lock and the Controller's lock. marcus, maya and priya act; nobody decides what she
// prepared. Each step is taken on the screen first, under the rule of `steps.ts`; the API says
// whether its end state stands.
//
// The section measures one thing on top of the walk (the supervisor's word of 2026-10-02 on the
// reading of J-13.4). The seed with the close leaves a journal-export hold on a contract of AVM-US
// (PRD §2.9 WLD-B-05), an open hold holds every period of its entity (gate "Holds released or
// waived"), and J-13.4 has maya release it on the workbench. So the walk first goes ON THE SCREENS
// ALONE: it looks for a control that releases the hold, takes the only other exit the screens may
// offer — a waiver of the gate — and goes for the lock. What the lock then stands over is written
// down: the held contract's lines against the journal run, the completeness gate, the tie-out of the
// month. Only when the screens do not reach the lock is the hold released through the API, said so
// in its row, so that the rest of the walk is still measured.
import type { Locator, Page } from "@playwright/test";

import { Api, at, cents, decimal, type Got, grouped, items, said, text } from "../api";
import type { Qa } from "../fixtures";
import { open } from "../observe";
import { flat, type Outcome } from "../record";
import { journalRevenue, makeRun, money, subledgerRevenue, tieOuts } from "../reports";
import {
  afterStepUp,
  approveOnScreen,
  approveThroughApi,
  buttonsOf,
  dismissToasts,
  flowStep,
  modal,
  stepUpThroughApi,
  toasts,
} from "../steps";
import { BOOK, periodId, reportRows, SEPTEMBER } from "../world";

const ENTITY = "AVM-US";
const LABEL = "Sep 2026";
const CONTEXT = `entity=${ENTITY}&period=${SEPTEMBER}&book=${BOOK}`;
const COCKPIT = `/close/${ENTITY}/${BOOK}/${SEPTEMBER}`;
/** PRD §2.9 WLD-B-05: the contract under the journal-export hold of the open-period items. */
const HELD = "BG-AVM-0021";
const HOLD_GATE = "HOLDS_REVIEWED";
const HOLD_GATE_LABEL = "Holds released or waived";
const RELEASE_COMMENT = "Dispute resolved; credit memo CM-US-0410 issued in NetSuite.";
/**
 * Register index 281 (the supervisor's ruling of 2026-10-02 on this section's reading): no screen
 * releases a hold, and a journal-export hold then keeps the period from its lock. A row that shows
 * exactly that — no control named "Release hold" in any of its three places, at two looks — is
 * marked with the index and not reported again; the same stop for another reason, or in another
 * place, is new: a control that is offered and does not release the hold is a finding of its own.
 */
const HOLD_ITEM = "281";
/**
 * Register index 296, CLO-LOCK-REQUEST-OWN-GATE-1 (the supervisor's ruling of 2026-10-02 on row C-10
 * of the development session): the period's own pending lock request counts in the gate "No
 * pending approvals", so the cockpit calls the lock unavailable. Marked where that gate alone, at a
 * count of one, stands between the Controller and the lock.
 */
const LOCK_ITEM = "296";
const JOB_MS = 900_000;
/** How long the cockpit may take to show the Controller its "Lock period" control. */
const LOCK_CONTROL_MS = 30_000;
/** How long the banner of a lock request may take to come once the API lists the request. */
const LOCK_BANNER_MS = 30_000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function until<T>(
  read: () => Promise<T>,
  done: (value: T) => boolean,
  timeoutMs: number,
  everyMs = 2_000,
): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const value = await read();
    if (done(value) || Date.now() > deadline) {
      return value;
    }
    await sleep(everyMs);
  }
}

function stopped(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  return flat(message.split("Call log:")[0] ?? message, 200);
}

/** The blockers the cockpit lists, "label count", as the screen shows them. */
async function blockersOnScreen(page: Page): Promise<readonly string[]> {
  const rows = page.getByTestId("SF-05-grid-blockers").locator("tbody tr");
  const found: string[] = [];
  for (const row of await rows.all()) {
    const cells = (await row.locator("td, th").allInnerTexts()).map((cell) => flat(cell, 80));
    found.push(`${cells[1] ?? ""} ${cells[0] ?? ""}`.trim());
  }
  return found;
}

/**
 * The cockpit's "Lock period" as the Controller is shown it, read when the cockpit's own read of the
 * period's requests has ended. The cockpit draws its action bar with its first render and learns of
 * the lock request from a read of its own (routes/close/cockpit.tsx `requests`): until that read has
 * come, the bar is the one of a period that was not submitted — "Lock period" blocked with "Lock is
 * not available: the period has not been submitted for lock." The first run of record (5c3b5347c,
 * 2026-10-03, row C-10) read the control in that moment, twice, where four runs before it had read
 * it after; its own capture, taken as the check ended, shows the lock offered. So the caller lets
 * the page settle first, and where the API lists the request to the Controller this waits for what
 * only the arrived read shows — the banner of the lock request — before it reads the control. A
 * banner that does not come in its time is said in the row and the control is read as it stands.
 * The verdict is not weaker for the wait: the control is available only when it is offered, not
 * blocked, and no "Lock is not available" line stands on the page.
 */
export async function lockControl(
  page: Page,
  listed: boolean,
  wait: { readonly controlMs: number; readonly bannerMs: number } = {
    controlMs: LOCK_CONTROL_MS,
    bannerMs: LOCK_BANNER_MS,
  },
): Promise<{ readonly available: boolean; readonly said: string }> {
  const button = page.getByRole("button", { name: "Lock period" });
  await button
    .first()
    .waitFor({ state: "visible", timeout: wait.controlMs })
    .catch(() => undefined);
  if ((await button.count()) === 0) {
    return {
      available: false,
      said: `"Lock period" is not offered; the page offers [${(await buttonsOf(page.getByRole("main"))).slice(0, 8).join(", ")}]`,
    };
  }
  const banner = page.getByTestId("SF-05-banner-lock-request");
  let request = "the API lists the Controller no pending lock request of the period";
  if (listed) {
    const came = await banner
      .first()
      .waitFor({ state: "visible", timeout: wait.bannerMs })
      .then(
        () => true,
        () => false,
      );
    request = came
      ? `the banner of the lock request reads "${flat(
          await banner
            .first()
            .innerText({ timeout: 3_000 })
            .catch(() => ""),
          160,
        )}"`
      : `THE BANNER OF THE LOCK REQUEST DID NOT COME IN ${String(wait.bannerMs / 1000)} s, though the API lists the request to the Controller`;
  }
  const disabled = (await button.first().getAttribute("aria-disabled")) === "true";
  const reason = flat(
    await page
      .getByText(/^Lock is not available: /)
      .first()
      .innerText({ timeout: 3_000 })
      .catch(() => ""),
    200,
  );
  return {
    available: !disabled && reason === "",
    said: `${request}; "Lock period" is offered, aria-disabled ${String(disabled)}${reason === "" ? "" : `; the cockpit reads "${reason}"`}`,
  };
}

/** The walk's members and what they act on. */
class Close {
  readonly preparer: Api;
  readonly reviewer: Api;
  readonly controller: Api;
  /** The journal runs of the month the walk took through their cycle, in order. */
  readonly runs: string[] = [];
  /** How the hold left the lock's way: on the screen, by a waiver, through the API, or not at all. */
  hold: "on hold" | "released on the screen" | "waived" | "released through the API" = "on hold";

  constructor(
    readonly qa: Qa,
    readonly period: string,
    readonly heldId: string,
    readonly maya: Page,
    readonly priya: Page,
    readonly marcus: Page,
  ) {
    this.preparer = new Api(maya);
    this.reviewer = new Api(priya);
    this.controller = new Api(marcus);
  }

  async periodNow(): Promise<unknown> {
    return (await this.preparer.get(`/api/v1/periods/${this.period}`)).json;
  }

  async state(): Promise<string> {
    return text(await this.periodNow(), "state");
  }

  async ifMatch(): Promise<Record<string, string>> {
    return { "If-Match": `"r${text(await this.periodNow(), "row_version")}"` };
  }

  async checklist(): Promise<readonly unknown[]> {
    return items((await this.preparer.get(`/api/v1/periods/${this.period}/checklist`)).json);
  }

  /** The gates that are not cleared, "<name>: <status> (<detail>)". */
  async openGates(): Promise<readonly string[]> {
    return (await this.checklist())
      .filter((item) => !["PASSED", "WAIVED", "NOT_APPLICABLE"].includes(text(item, "status")))
      .map(
        (item) =>
          `${text(item, "name")}: ${text(item, "status")}${text(item, "result", "detail") === "" ? "" : ` (${flat(text(item, "result", "detail"), 160)})`}`,
      );
  }

  async gate(code: string): Promise<unknown> {
    return (await this.checklist()).find((item) => text(item, "gate_check_code") === code);
  }

  /**
   * The codes of the gates a submission for lock still waits for: every gate that is not cleared,
   * without the Controller's certification, which the lock itself gives (04 §16.8).
   */
  async openCodes(): Promise<readonly string[]> {
    return (await this.checklist())
      .filter((item) => !["PASSED", "WAIVED", "NOT_APPLICABLE"].includes(text(item, "status")))
      .map((item) => text(item, "gate_check_code") || text(item, "code"))
      .filter((code) => code !== "CONTROLLER_CERTIFIED");
  }

  async onHold(): Promise<boolean> {
    if (this.heldId === "") {
      return false;
    }
    return (
      at((await this.preparer.get(`/api/v1/contracts/${this.heldId}`)).json, "on_hold") === true
    );
  }

  async latestCloseRun(): Promise<unknown> {
    return at(
      (
        await this.preparer.get("/api/v1/close-runs", {
          entity: ENTITY,
          book: BOOK,
          period: SEPTEMBER,
          limit: 5,
        })
      ).json,
      "items",
      0,
    );
  }

  async run(id: string): Promise<unknown> {
    return (await this.preparer.get(`/api/v1/journal-runs/${id}`)).json;
  }

  async batches(id: string): Promise<readonly unknown[]> {
    return items(
      (await this.preparer.get(`/api/v1/journal-runs/${id}/batches`, { limit: 200 })).json,
    );
  }

  async reconciliation(kind: string): Promise<unknown> {
    return at(
      (
        await this.preparer.get("/api/v1/reconciliations", {
          entity: ENTITY,
          book: BOOK,
          period: SEPTEMBER,
          kind,
          is_current: true,
          limit: 5,
        })
      ).json,
      "items",
      0,
    );
  }

  async pendingLock(): Promise<unknown> {
    return (
      await this.controller.list("/api/v1/approvals", {
        status: "PENDING",
        subject_type: "PERIOD_LOCK",
      })
    ).find((item) => text(item, "subject", "id") === this.period);
  }
}

const head = (check: string, persona: string, address: string, expected: string) => ({
  check,
  persona,
  address,
  expected,
});

/** The cockpit as it stands: its counts against the lists they link to. */
async function cockpitCheck(close: Close): Promise<Outcome> {
  const { marcus, controller } = close;
  const seen = await open(marcus, COCKPIT);
  const shown = await blockersOnScreen(marcus);
  const period = (await controller.get(`/api/v1/periods/${close.period}`)).json;
  const blockers = (at(period, "blockers") ?? {}) as Record<string, unknown>;
  const pending = await controller.total("/api/v1/approvals", {
    entity: ENTITY,
    status: "PENDING",
  });
  const exceptions = await controller.get("/api/v1/exceptions", {
    blocking: close.period,
    status: "OPEN",
    limit: 1,
    count: true,
  });
  const held = await controller.total("/api/v1/contracts", { entity: ENTITY, on_hold: true });
  const lock = marcus.getByRole("button", { name: "Lock period" });
  const lockState =
    (await lock.count()) === 0
      ? "not offered"
      : `offered, aria-disabled ${(await lock.first().getAttribute("aria-disabled")) ?? "false"}`;
  const stated = Object.entries(blockers)
    .filter(([, count]) => Number(count) > 0)
    .map(([name, count]) => `${name} ${String(count)}`)
    .join(", ");
  const observed = `${seen.state} "${seen.heading}"; the screen lists [${shown.join("; ")}]; the API's period states ${stated || "no blocker"}; lists: ${String(pending)} pending request(s) of ${ENTITY} visible to marcus, ${exceptions.headers["x-erev-total-count"] ?? "?"} open exception(s) holding the period, ${String(held)} contract(s) on hold; "Lock period" ${lockState}; gates not cleared: ${(await close.openGates()).join("; ")}`;
  const holds = Number(blockers["holds_open"] ?? 0);
  if (held !== null && holds !== held) {
    return {
      observed: `THE COUNT IS NOT THE LIST'S: Holds ${String(holds)} on the period, ${String(held)} contract(s) on hold in the list. ${observed}`,
      result: "seen once",
      page: marcus,
    };
  }
  return seen.state === "rendered"
    ? { observed, result: "pass", page: marcus }
    : { observed, result: "FINDING", finding: "stopped flow", page: marcus };
}

/** Every pending request of the entity priya can decide: the activation and the judgement of J-13.2. */
async function decideRequests(close: Close): Promise<Outcome> {
  const { priya, reviewer } = close;
  const waiting = (
    await reviewer.list("/api/v1/approvals", { status: "PENDING", assigned_to_me: true })
  ).filter(
    (item) =>
      text(item, "entity", "code") === ENTITY &&
      ["CONTRACT_ACTIVATION", "JUDGEMENT_RECORD"].includes(text(item, "subject", "type")),
  );
  if (waiting.length === 0) {
    return {
      observed: `no pending activation or judgement request of ${ENTITY} waits for priya`,
      result: "pass",
    };
  }
  const lines: string[] = [];
  const stuck: string[] = [];
  const onward: string[] = [];
  let second = 0;
  const comment = "Reviewed for the September close.";
  for (const request of waiting) {
    const id = text(request, "id");
    const status = async () => text((await reviewer.get(`/api/v1/approvals/${id}`)).json, "status");
    let line = `${text(request, "request_no")} "${text(request, "summary")}"`;
    // The screen, twice; then the same decision through the API, so that the close can go on.
    for (let attempt = 1; attempt <= 2 && (await status()) === "PENDING"; attempt += 1) {
      try {
        const decided = await approveOnScreen(priya, "priya", id, comment);
        line += `: "${decided.toast}"`;
        second += attempt === 2 ? 1 : 0;
      } catch (error) {
        line += `: screen attempt ${String(attempt)} stopped (${stopped(error)})`;
      }
      await dismissToasts(priya);
    }
    if ((await status()) !== "APPROVED") {
      const got = await approveThroughApi(reviewer, "priya", id, comment);
      const after = await status();
      stuck.push(`${line}; through the API: ${said(got)}; the request is ${after}`);
      if (after === "APPROVED") {
        onward.push(text(request, "request_no"));
      }
    }
    lines.push(line);
  }
  if (stuck.length > 0) {
    return {
      observed: `NOT DECIDED ON THE SCREEN, twice: ${stuck.join(" | ")}. ${onward.length === stuck.length ? "The decisions went through the API and the close goes on." : "Not every request is decided."} ${lines.join("; ")}`,
      result: "FINDING",
      finding: "stopped flow",
      page: priya,
    };
  }
  return second === 0
    ? { observed: lines.join("; "), result: "pass", page: priya }
    : {
        observed: `${String(second)} request(s) were decided at the second attempt on the screen: ${lines.join("; ")}`,
        result: "seen once",
        page: priya,
      };
}

/** J-13.3: the exception items that hold the period, dismissed on SF-11:item. */
async function dismissExceptions(close: Close): Promise<Outcome> {
  const { maya, preparer } = close;
  const holding = async () => {
    const found = [
      ...(await preparer.list("/api/v1/exceptions", { blocking: close.period, status: "OPEN" })),
      ...(await preparer.list("/api/v1/exceptions", {
        blocking: close.period,
        status: "IN_PROGRESS",
      })),
    ];
    return found.filter(
      (item, index) => found.findIndex((other) => text(other, "id") === text(item, "id")) === index,
    );
  };
  const waiting = await holding();
  if (waiting.length === 0) {
    return { observed: "no open exception holds the period", result: "pass" };
  }
  const REASON = "Replaced by the corrected import committed on the same day.";
  const lines: string[] = [];
  const throughApi: string[] = [];
  let second = 0;
  for (const item of waiting) {
    const id = text(item, "id");
    const code = `${text(item, "exception_no")} ${text(item, "code")}`;
    const actions = items(item, "available_actions").map(String);
    const stands = async () =>
      ["OPEN", "IN_PROGRESS"].includes(
        text((await preparer.get(`/api/v1/exceptions/${id}`)).json, "status"),
      );
    let line = `${code} (actions ${actions.join(", ") || "none"})`;
    // The screen, twice; then the same dismissal through the API, so that the close can go on.
    for (let attempt = 1; attempt <= 2 && (await stands()); attempt += 1) {
      try {
        await maya.goto(`/data/exceptions/${id}`);
        await maya
          .getByRole("button", { name: "Dismiss exception" })
          .first()
          .click({ timeout: 15_000 });
        const dialog = modal(maya, /^Dismiss exception /);
        await dialog.getByRole("textbox").first().fill(REASON);
        await dialog.getByRole("button", { name: /^Dismiss/ }).click();
        await maya
          .getByText(/^Dismissed /)
          .first()
          .waitFor({ state: "visible", timeout: 20_000 });
        line += ": dismissed on the screen";
        second += attempt === 2 ? 1 : 0;
      } catch (error) {
        line += `: screen attempt ${String(attempt)} stopped (${stopped(error)}); the page offers [${(await buttonsOf(maya.getByRole("main"))).slice(0, 12).join(", ")}]`;
      }
      await dismissToasts(maya);
    }
    if (await stands()) {
      const got = await preparer.send("POST", `/api/v1/exceptions/${id}/dismiss`, {
        comment: REASON,
      });
      throughApi.push(`${line}; through the API: ${said(got)}`);
    }
    lines.push(line);
  }
  const left = await holding();
  if (left.length > 0 || throughApi.length > 0) {
    return {
      observed: `NOT DISMISSED ON THE SCREEN, twice: ${throughApi.join(" | ") || "none sent through the API"}. ${left.length === 0 ? "The dismissals went through the API and the close goes on." : `${String(left.length)} exception(s) still hold the period: ${left.map((item) => `${text(item, "exception_no")} ${text(item, "code")} ${text(item, "status")}`).join(", ")}.`} ${lines.join("; ")}`,
      result: "FINDING",
      finding: "stopped flow",
      page: maya,
    };
  }
  return second === 0
    ? { observed: lines.join("; "), result: "pass", page: maya }
    : {
        observed: `${String(second)} item(s) were dismissed at the second attempt on the screen: ${lines.join("; ")}`,
        result: "seen once",
        page: maya,
      };
}

/**
 * The open holds of the contract as its reads list them (04 §16.1 API-S-Contract `holds`, §16.2
 * API-S-Obligation `holds`): each with its type, source and level and the API's sentence for a hold
 * that is not released by hand. `byHand` is null where the contract's read has no such member.
 */
async function holdsRead(
  close: Close,
): Promise<{ readonly said: string; readonly byHand: number | null }> {
  const { preparer, heldId } = close;
  const contract = (await preparer.get(`/api/v1/contracts/${heldId}`)).json;
  if (at(contract, "holds") === undefined) {
    return { said: "the contract's read has no member `holds`", byHand: null };
  }
  const obligations = await preparer.get(`/api/v1/contracts/${heldId}/obligations`, {
    book: BOOK,
    limit: 200,
  });
  const all = [
    ...items(contract, "holds"),
    ...items(obligations.json).flatMap((item) => items(item, "holds")),
  ];
  const lines = all.map(
    (hold) =>
      `${text(hold, "hold_type")}, ${text(hold, "hold_source")}, ${text(hold, "level")} level, release_refusal ${text(hold, "release_refusal") === "" ? "none" : `"${flat(text(hold, "release_refusal"), 120)}"`}`,
  );
  return {
    said: `the reads list ${String(all.length)} open hold(s) [${lines.join("; ")}]`,
    byHand: all.filter((hold) => text(hold, "release_refusal") === "").length,
  };
}

/** The drawer of "Release hold" (SCREENS §4.9.4) once a control opened it: what it took or showed. */
async function fillRelease(maya: Page): Promise<string> {
  const dialog = maya.getByRole("dialog", { name: /Release hold/ });
  await dialog.waitFor({ state: "visible", timeout: 15_000 });
  const comment = dialog.getByRole("textbox");
  if ((await comment.count()) === 0) {
    // A drawer without a comment field offers no hold to release by hand: it says why.
    const read = flat(await dialog.innerText(), 300);
    await maya.keyboard.press("Escape");
    return `the drawer takes no comment and reads "${read}"`;
  }
  await comment.last().fill(RELEASE_COMMENT);
  await dialog.getByRole("button", { name: /^Release hold/ }).click();
  const closed = await dialog
    .waitFor({ state: "hidden", timeout: 20_000 })
    .then(() => true)
    .catch(() => false);
  return closed
    ? "the drawer took the comment and closed"
    : `the drawer stayed open and reads "${flat(await dialog.innerText().catch(() => ""), 400)}"`;
}

/** J-13.4 as the PRD has it: maya releases the hold with the control SCREENS puts in three places. */
async function releaseOnScreen(close: Close): Promise<Outcome> {
  const { maya, preparer } = close;
  if (close.heldId === "") {
    return { observed: `the world holds no contract ${HELD}`, result: "not run" };
  }
  if (!(await close.onHold())) {
    close.hold = "released on the screen";
    return { observed: `${HELD} is not on hold`, result: "pass" };
  }
  const read = await holdsRead(close);
  /** One look at the three places; a control that is found is pressed, and what it did is said. */
  const look = async (): Promise<{ readonly offered: boolean; readonly said: string }> => {
    const places: string[] = [];
    let offered = false;
    const press = async (place: string, control: Locator): Promise<void> => {
      offered = true;
      try {
        await control.click({ timeout: 10_000 });
        places.push(`${place}: "Release hold" was pressed and ${await fillRelease(maya)}`);
      } catch (error) {
        places.push(`${place}: "Release hold" is offered and the step stopped (${stopped(error)})`);
        await maya.keyboard.press("Escape").catch(() => undefined);
      }
    };
    const workbench = async (): Promise<void> => {
      await maya.goto(`/contracts/${close.heldId}/obligations?${CONTEXT}`);
      await maya.getByTestId("SF-03-identifier").waitFor({ state: "visible", timeout: 30_000 });
    };
    await workbench();
    // The header (SCREENS §4.1.6: "Release hold" renders only when the contract is on hold).
    const header = await buttonsOf(maya.getByRole("main"));
    places.push(`the workbench's buttons [${header.slice(0, 18).join(", ")}]`);
    const direct = maya.getByRole("button", { name: "Release hold" });
    if ((await direct.count()) > 0) {
      await press("the workbench's header", direct.first());
      if (await close.onHold()) {
        // A drawer that stayed open is left behind: the menu is looked for on the page opened again.
        await workbench();
      }
    }
    const more = maya.getByRole("button", { name: "More actions" });
    if ((await close.onHold()) && (await more.count()) > 0) {
      try {
        await more.first().click({ timeout: 10_000 });
        await maya
          .getByRole("menu")
          .first()
          .waitFor({ state: "visible", timeout: 5_000 })
          .catch(() => undefined);
        const menu = (await maya.getByRole("menuitem").allInnerTexts()).map((item) =>
          flat(item, 60),
        );
        places.push(`"More actions" [${menu.join(", ")}]`);
        const release = maya.getByRole("menuitem", { name: "Release hold" });
        if ((await release.count()) > 0) {
          await press('"More actions"', release.first());
        } else {
          await maya.keyboard.press("Escape");
        }
      } catch (error) {
        places.push(`"More actions" could not be opened (${stopped(error)})`);
      }
    }
    // The obligation's pane (SCREENS §5.6 Panels: "Holds … action 'Release hold'").
    if (await close.onHold()) {
      const obligation = text(
        (
          await preparer.get(`/api/v1/contracts/${close.heldId}/obligations`, {
            book: BOOK,
            limit: 1,
          })
        ).json,
        "items",
        0,
        "id",
      );
      if (obligation !== "") {
        await maya.goto(`/contracts/${close.heldId}/obligations/${obligation}?${CONTEXT}`);
        const pane = maya.getByTestId("SF-03-pane-obligation");
        await pane.waitFor({ state: "visible", timeout: 20_000 }).catch(() => undefined);
        const holds = flat(
          await pane
            .getByText(/holds?/i)
            .first()
            .innerText({ timeout: 3_000 })
            .catch(() => ""),
          80,
        );
        places.push(
          `the obligation's pane [${(await buttonsOf(pane)).slice(0, 14).join(", ")}], its hold line "${holds}"`,
        );
        const inPane = pane.getByRole("button", { name: "Release hold" });
        if ((await inPane.count()) > 0) {
          await press("the obligation's pane", inPane.first());
        }
      }
    }
    return { offered, said: places.join("; ") };
  };
  const released = async (looks: readonly string[]): Promise<string> => {
    const gate = await close.gate(HOLD_GATE);
    return `released on the screen; messages [${(await toasts(maya)).join(" | ")}]; the gate "${HOLD_GATE_LABEL}" is ${text(gate, "status")}; before the release ${read.said}; ${looks.join(" || second look: ")}`;
  };
  const first = await look();
  if (!(await close.onHold())) {
    close.hold = "released on the screen";
    return { observed: await released([first.said]), result: "pass", page: maya };
  }
  // Looked for twice before the row is written: the three places are walked once more.
  const second = await look();
  if (!(await close.onHold())) {
    close.hold = "released on the screen";
    return {
      observed: `at the second look: ${await released([first.said, second.said])}`,
      result: "seen once",
      page: maya,
    };
  }
  const banner = flat(
    await maya
      .getByTestId("SF-03-banner-header")
      .innerText({ timeout: 3_000 })
      .catch(() => ""),
    200,
  );
  if (!first.offered && !second.offered) {
    return {
      observed: `NO SCREEN RELEASES THE HOLD: ${HELD} is on hold (the header banner reads "${banner}") and no control named "Release hold" is offered at two looks — ${first.said} || second look: ${second.said}; ${read.said}. The API has the command (POST /contracts/{id}/release-hold); the pass does not send it here.`,
      result: "KNOWN",
      known: HOLD_ITEM,
      page: maya,
    };
  }
  const observed = `"RELEASE HOLD" IS OFFERED AND THE HOLD STANDS, twice: ${HELD} is on hold (the header banner reads "${banner}"); ${read.said}; ${first.said} || second look: ${second.said}. The pass does not send the API's command here.`;
  // The drawer chooses a hold by itself only where one is released by hand: among several the
  // pass chose none, which is the pass's own limit and no stop of the product.
  return read.byHand !== null && read.byHand !== 1
    ? { observed, result: "seen once", page: maya }
    : { observed, result: "FINDING", finding: "stopped flow", page: maya };
}

/** One journal run through its cycle: submitted by maya, approved by priya, exported, acknowledged. */
async function journalCycle(close: Close, name: string, runId: string): Promise<boolean> {
  const { qa, maya, priya, preparer } = close;
  const runNo = text(await close.run(runId), "run_no");
  close.runs.push(runId);
  const submitted = await flowStep(qa.record, {
    head: head(
      `${name}a the journal run ${runNo}, submitted`,
      "maya",
      `/journals/runs/<${runNo}>?${CONTEXT}`,
      'The run reads "Calculated" and balanced; "Submit for approval" sends it to a reviewer (PRD J-13.8; BR-JE-01)',
    ),
    page: maya,
    screen: async () => {
      await maya.goto(`/journals/runs/${runId}?${CONTEXT}`);
      const frame = maya.getByTestId("SF-06-page");
      const difference = flat(
        await maya.getByTestId("SF-06-kpi-difference").innerText({ timeout: 20_000 }),
        80,
      );
      await frame.getByRole("button", { name: "Submit for approval", exact: true }).first().click();
      const dialog = modal(maya, `Submit journal run ${runNo} for approval?`);
      await dialog
        .getByRole("textbox", { name: /^Comment/ })
        .fill("Sep 2026 AVM-US journals for approval.");
      await dialog.getByRole("button", { name: "Submit for approval", exact: true }).click();
      await maya
        .getByText(`Submitted journal run ${runNo} for approval.`, { exact: true })
        .waitFor({ state: "visible", timeout: 30_000 });
      return `difference "${difference}"; "Submitted journal run ${runNo} for approval."`;
    },
    reached: async () => {
      const run = await close.run(runId);
      return text(run, "approval_request_id") !== "" || text(run, "state") !== "draft"
        ? null
        : `the run is ${text(run, "state")} with no request`;
    },
    api: () =>
      preparer.send("POST", `/api/v1/journal-runs/${runId}/submit`, {
        comment: "Sep 2026 AVM-US journals for approval.",
      }),
  });
  if (!submitted) {
    return false;
  }
  const approved = await flowStep(qa.record, {
    head: head(
      `${name}b the journal run ${runNo}, approved`,
      "priya",
      "/approvals/requests/<the journal run's request>",
      "priya, who did not run the journals, approves with a fresh code (PRD J-13.8; BR-JE-01; BR-PLT-06); the run is approved",
    ),
    page: priya,
    screen: async () => {
      const run = await close.run(runId);
      const decided = await approveOnScreen(
        priya,
        "priya",
        text(run, "approval_request_id"),
        "Reviewed the Sep 2026 AVM-US journal run and its balance checks.",
      );
      return `"${decided.toast}"; ${decided.stepUp ? "a code was asked" : "no code was asked"}; the run is ${text(await close.run(runId), "state")}`;
    },
    reached: async () => {
      const state = text(await close.run(runId), "state");
      return ["approved", "exported", "acknowledged"].includes(state)
        ? null
        : `the run is ${state}`;
    },
    api: async () =>
      approveThroughApi(
        close.reviewer,
        "priya",
        text(await close.run(runId), "approval_request_id"),
        "Reviewed the Sep 2026 AVM-US journal run and its balance checks.",
      ),
  });
  if (!approved) {
    return false;
  }
  const ended = (state: string) => ["exported", "acknowledged", "failed"].includes(state);
  const exported = await flowStep(qa.record, {
    head: head(
      `${name}c the journal run ${runNo}, exported`,
      "maya",
      `/journals/runs/<${runNo}>?${CONTEXT}`,
      'An approved run offers "Export journals" for a workspace without a GL connection; the dialog names its one target and the run is exported as its batch files (PRD J-13.9; BR-JE-02; 05 ADP-30)',
    ),
    page: maya,
    screen: async () => {
      await maya.goto(`/journals/runs/${runId}?${CONTEXT}`);
      await maya
        .getByTestId("SF-06-page")
        .getByRole("button", { name: /^Export (journals|to )/ })
        .first()
        .click({ timeout: 30_000 });
      const dialog = modal(maya, /^Export journal run /);
      const title = flat(
        await dialog
          .getByRole("heading")
          .first()
          .innerText({ timeout: 10_000 })
          .catch(() => ""),
        120,
      );
      await dialog.getByRole("button", { name: "Export", exact: true }).click();
      const after = await until(
        () => close.run(runId),
        (item) => ended(text(item, "state")),
        180_000,
      );
      const told = (await toasts(maya)).filter((line) => line.includes("exported"));
      return `"${title}"; the run is ${text(after, "state")}; messages [${told.join(" | ")}]`;
    },
    reached: async () => {
      const state = text(await close.run(runId), "state");
      return ["exported", "acknowledged"].includes(state) ? null : `the run is ${state}`;
    },
    api: async () => {
      const started = await preparer.send("POST", `/api/v1/journal-runs/${runId}/export`, {
        adapter: "CSV",
      });
      await until(
        () => close.run(runId),
        (item) => ended(text(item, "state")),
        180_000,
      );
      return started;
    },
  });
  if (!exported) {
    return false;
  }
  const reference = (batch: unknown) =>
    `GL-${ENTITY}-${SEPTEMBER}-${text(batch, "batch_no").padStart(2, "0")}-${text(batch, "chunk_no").padStart(2, "0")}`;
  const waiting = async () =>
    (await close.batches(runId)).filter((batch) => text(batch, "state") !== "acknowledged");
  return flowStep(qa.record, {
    head: head(
      `${name}d the ledger's reference for each batch of ${runNo}`,
      "maya",
      `/journals/runs/<${runNo}>/batches?${CONTEXT}`,
      'Each exported batch of a workspace without a GL connection is acknowledged by "Record ERP reference" (BR-JE-03); the run is acknowledged and the batches blocker clears (PRD J-13.9)',
    ),
    page: maya,
    screen: async () => {
      await maya.goto(`/journals/runs/${runId}/batches?${CONTEXT}`);
      const grid = maya.getByTestId("SF-06-grid-batches").getByRole("grid", { name: "Batches" });
      await grid.waitFor({ state: "visible", timeout: 30_000 });
      const before = await waiting();
      for (const batch of before.slice(0, 40)) {
        await maya
          .getByRole("button", { name: /^Record ERP reference for batch / })
          .first()
          .click();
        const dialog = modal(maya, /^Record ERP reference for batch /);
        await dialog
          .getByRole("textbox", { name: /^ERP document reference/ })
          .fill(reference(batch));
        await dialog.getByRole("button", { name: "Record reference" }).click();
        await maya
          .getByText(/acknowledged with reference/)
          .first()
          .waitFor({ state: "visible", timeout: 30_000 });
        await dismissToasts(maya);
      }
      return `${String(before.length)} batch(es) acknowledged on the screen`;
    },
    reached: async () => {
      const left = await waiting();
      return left.length === 0
        ? null
        : `${String(left.length)} batch(es) not acknowledged (${[...new Set(left.map((batch) => text(batch, "state")))].join(", ")})`;
    },
    api: async () => {
      let last: Got = await preparer.get(`/api/v1/journal-runs/${runId}`);
      for (const batch of await waiting()) {
        last = await preparer.send(
          "POST",
          `/api/v1/journal-batches/${text(batch, "id")}/acknowledge`,
          {
            gl_document_id: reference(batch),
            gl_posted_date: "2026-09-30",
            message: "Imported into the general ledger from the CSV export.",
          },
        );
      }
      return last;
    },
  });
}

/** The two reconciliations the lock asks for: generated, compared, explained, prepared, reviewed. */
async function reconcile(close: Close, name: string): Promise<boolean> {
  const { qa, maya, priya, preparer } = close;
  const generate = async (item: string, kind: string) => {
    const before = text(await close.reconciliation(kind), "id");
    await maya.goto(`${COCKPIT}/reconciliations`);
    await maya.getByRole("button", { name: "Generate reconciliation" }).first().click();
    await maya.getByRole("menuitem", { name: item }).click();
    return until(
      () => close.reconciliation(kind),
      (found) => text(found, "id") !== "" && text(found, "id") !== before,
      120_000,
    );
  };
  /** Explains the first difference on the screen and the others through the API, then signs. */
  const prepare = async (kind: string): Promise<string> => {
    const reconciliation = await close.reconciliation(kind);
    const id = text(reconciliation, "id");
    const number = text(reconciliation, "reconciliation_no");
    if (text(reconciliation, "status") !== "DRAFT") {
      return `${number} is ${text(reconciliation, "status")}: nothing to sign as preparer`;
    }
    const differing = async () =>
      (await preparer.list(`/api/v1/reconciliations/${id}/items`)).filter(
        (item) =>
          cents(text(item, "difference", "amount")) !== 0n && text(item, "explanation") === "",
      );
    const unexplained = await differing();
    let explained = "no difference to explain";
    if (unexplained.length > 0) {
      const words = EXPLANATION;
      await maya.goto(`${COCKPIT}/reconciliations/${id}?${CONTEXT}`);
      let onScreen = "0 explained on the screen";
      try {
        await maya
          .getByRole("button", { name: "Add explanation" })
          .first()
          .click({ timeout: 15_000 });
        const dialog = modal(maya, "Explain difference");
        await dialog.getByRole("textbox").first().fill(words);
        await dialog.getByRole("button", { name: "Save explanation" }).click();
        await maya
          .getByText("Explanation saved.")
          .first()
          .waitFor({ state: "visible", timeout: 20_000 });
        onScreen = "1 explained on the screen";
      } catch (error) {
        onScreen = `the screen's "Add explanation" stopped (${stopped(error)})`;
      }
      let byApi = 0;
      for (const item of await differing()) {
        const got = await preparer.send(
          "PATCH",
          `/api/v1/reconciliations/${id}/items/${text(item, "id")}`,
          { explanation: words },
          { "If-Match": `"r${text(item, "row_version")}"` },
        );
        byApi += got.status === 200 ? 1 : 0;
      }
      explained = `${String(unexplained.length)} difference(s): ${onScreen}, ${String(byApi)} through the API, as the seed explains the closed months'`;
    }
    await maya.goto(`${COCKPIT}/reconciliations/${id}?${CONTEXT}`);
    await maya.getByRole("button", { name: "Sign as preparer" }).first().click();
    const dialog = modal(maya, `Sign ${number} as preparer?`);
    await dialog.getByRole("checkbox", { name: "I confirm this statement" }).check();
    await dialog.getByRole("button", { name: /^Sign/ }).click();
    await afterStepUp(maya, "maya", maya.getByText(`Signed ${number} as preparer.`));
    return `${number}: ${explained}; signed as preparer on the screen`;
  };
  const review = async (kind: string): Promise<string> => {
    const reconciliation = await close.reconciliation(kind);
    const number = text(reconciliation, "reconciliation_no");
    if (text(reconciliation, "status") !== "PREPARED") {
      return `${number} is ${text(reconciliation, "status")}: nothing to sign as reviewer`;
    }
    await priya.goto(`${COCKPIT}/reconciliations/${text(reconciliation, "id")}?${CONTEXT}`);
    await priya.getByRole("button", { name: "Sign as reviewer" }).first().click();
    const dialog = modal(priya, `Sign ${number} as reviewer?`);
    await dialog.getByRole("checkbox", { name: "I confirm this statement" }).check();
    await dialog.getByRole("button", { name: /^Sign/ }).click();
    await afterStepUp(priya, "priya", priya.getByText(`Signed ${number} as reviewer.`));
    return `${number}: signed as reviewer on the screen`;
  };
  const LABELS: Readonly<Record<string, string>> = {
    BILLING_TO_SUBLEDGER: "Billing to subledger",
    SUBLEDGER_TO_GL: "Subledger to GL",
  };
  /** The gate's own word for a reviewed reconciliation the period has overtaken (04 T-CLS-06). */
  const outOfDate = async (kind: string): Promise<string | null> => {
    const detail = text(await close.gate("RECONCILIATIONS_GENERATED"), "result", "detail");
    return detail.includes(`out of date, generate it again: ${LABELS[kind] ?? kind}`)
      ? `the gate says "${flat(detail, 200)}"`
      : null;
  };
  const cleared = async (kind: string) => {
    const status = text(await close.reconciliation(kind), "status");
    return ["REVIEWED", "AUTO_CERTIFIED", "CERTIFIED"].includes(status)
      ? outOfDate(kind)
      : `the current ${kind} reconciliation is ${status === "" ? "not generated" : status}`;
  };

  const EXPLANATION =
    "Recorded by hand from the invoice: no billing document reaches this workspace yet.";
  /** The account balances a compared reconciliation states, as lines of a trial balance file. */
  const balancesOf = (compared: unknown, currency: string): string[] =>
    items(compared, "totals")
      .filter(
        (total) =>
          text(total, "account_code") !== "" && text(total, "subledger_amount", "amount") !== "",
      )
      .map(
        (total) =>
          `${text(total, "account_code")},${text(total, "currency") || currency},${text(total, "subledger_amount", "amount")}`,
      );
  const functionalCurrency = async () =>
    text(
      (await preparer.get(`/api/v1/periods/${close.period}/cockpit`)).json,
      "journal_preview",
      "debit_functional",
      "currency",
    );
  /**
   * The same reconciliation through the API, in the order the seed's close stage takes it
   * (backend domain/demo/closing.py): generated, a ledger one compared with its file, every
   * difference explained, prepared by maya, reviewed by priya after a fresh verification.
   */
  const throughApi = async (kind: "BILLING_TO_SUBLEDGER" | "SUBLEDGER_TO_GL"): Promise<Got> => {
    const generated = async (): Promise<Got> => {
      const started = await preparer.send("POST", "/api/v1/reconciliations", {
        kind,
        entity_code: ENTITY,
        period_key: SEPTEMBER,
        book: BOOK,
      });
      if (started.status === 202) {
        await preparer.job(started, 180_000);
      }
      return started;
    };
    const attached = async (file: string, lines: readonly string[]): Promise<Got> => {
      const uploaded = await preparer.upload(
        file,
        `account,currency,amount\n${lines.join("\n")}\n`,
      );
      if (uploaded.status >= 300) {
        return uploaded;
      }
      const started = await preparer.send(
        "POST",
        `/api/v1/reconciliations/${text(await close.reconciliation(kind), "id")}/attach-trial-balance`,
        { file_id: text(uploaded.json, "id") },
      );
      if (started.status === 202) {
        await preparer.job(started, 180_000);
      }
      return started;
    };
    let current = await close.reconciliation(kind);
    let last: Got = await preparer.get(`/api/v1/reconciliations/${text(current, "id") || "none"}`);
    if (
      !["DRAFT", "PREPARED", "REVIEWED", "AUTO_CERTIFIED", "CERTIFIED"].includes(
        text(current, "status"),
      ) ||
      (await outOfDate(kind)) !== null
    ) {
      last = await generated();
      current = await close.reconciliation(kind);
    }
    if (
      kind === "SUBLEDGER_TO_GL" &&
      text(current, "status") === "DRAFT" &&
      (at(current, "trial_balance") ?? null) === null
    ) {
      const currency = await functionalCurrency();
      last = await attached("tb-avm-us-sep-2026-first-api.csv", [`2100,${currency},0.00`]);
      const balances = balancesOf(await close.reconciliation(kind), currency);
      if (balances.length > 0) {
        last = await generated();
        last = await attached("tb-avm-us-sep-2026-api.csv", balances);
      }
      current = await close.reconciliation(kind);
    }
    const id = text(current, "id");
    if (text(current, "status") === "DRAFT") {
      for (const item of await preparer.list(`/api/v1/reconciliations/${id}/items`)) {
        if (cents(text(item, "difference", "amount")) !== 0n && text(item, "explanation") === "") {
          await preparer.send(
            "PATCH",
            `/api/v1/reconciliations/${id}/items/${text(item, "id")}`,
            { explanation: EXPLANATION },
            { "If-Match": `"r${text(item, "row_version")}"` },
          );
        }
      }
      last = await preparer.send("POST", `/api/v1/reconciliations/${id}/prepare`);
      current = await close.reconciliation(kind);
    }
    if (text(current, "status") === "PREPARED") {
      await stepUpThroughApi(close.reviewer, "priya");
      last = await close.reviewer.send("POST", `/api/v1/reconciliations/${id}/sign`, {
        role: "REVIEWER",
        statement_accepted: true,
      });
    }
    return last;
  };

  const billing = await flowStep(qa.record, {
    head: head(
      `${name}a billing to subledger`,
      "maya, priya",
      `${COCKPIT}/reconciliations`,
      '"Generate reconciliation" → "Billing to subledger"; a difference is explained, maya signs as preparer and priya as reviewer, or the rule certifies a reconciliation without a difference (PRD J-13.10, SM-09; CTL-026)',
    ),
    page: maya,
    screen: async () => {
      let standing = await close.reconciliation("BILLING_TO_SUBLEDGER");
      let lead = `${text(standing, "reconciliation_no")} stood ${text(standing, "status")}`;
      if (!["DRAFT", "PREPARED"].includes(text(standing, "status"))) {
        standing = await generate("Billing to subledger", "BILLING_TO_SUBLEDGER");
        lead = `${text(standing, "reconciliation_no")} generated: ${text(standing, "status")}, ${text(standing, "variance_count")} difference(s)`;
      }
      return `${lead}; ${await prepare("BILLING_TO_SUBLEDGER")}; ${await review("BILLING_TO_SUBLEDGER")}`;
    },
    reached: () => cleared("BILLING_TO_SUBLEDGER"),
    api: () => throughApi("BILLING_TO_SUBLEDGER"),
  });

  const ledger = await flowStep(qa.record, {
    head: head(
      `${name}b subledger to GL`,
      "maya, priya",
      `${COCKPIT}/reconciliations`,
      '"Generate reconciliation" → "Subledger to GL" opens where the trial balance is attached; a CSV of the ledger\'s balances is uploaded and compared, differences are explained, maya signs as preparer and priya as reviewer (PRD J-13.11, J-13.12; BUILD_SPEC CLO-17)',
    ),
    page: maya,
    screen: async () => {
      const currency = await functionalCurrency();
      const attach = async (file: string, lines: readonly string[]) => {
        // A subledger-to-GL reconciliation opens on its "Attach a trial balance" state by itself
        // (SCREENS_B §2.1); the file field stands there once "Upload CSV" is the source.
        const panel = maya.getByTestId("SF-05-attach-trial-balance");
        await panel.waitFor({ state: "visible", timeout: 60_000 });
        const choice = panel.getByRole("radio", { name: "Upload CSV" });
        if ((await choice.count()) > 0) {
          await choice.first().click();
        }
        await maya.getByTestId("SF-05-trial-balance-file").setInputFiles({
          name: file,
          mimeType: "text/csv",
          buffer: Buffer.from(`account,currency,amount\n${lines.join("\n")}\n`, "utf-8"),
        });
        await panel.getByRole("button", { name: "Upload and compare" }).click();
        return until(
          () => close.reconciliation("SUBLEDGER_TO_GL"),
          (found) => ["SUCCEEDED", "FAILED"].includes(text(found, "trial_balance", "job", "state")),
          120_000,
        );
      };
      // The balances a ledger would hold are the subledger's own (PRD §2.2 WLD-P-02: the demo
      // world's file shows the form of the tie-out). They are stated once a file is compared, so
      // a first reconciliation is compared with one line and a second with the balances it states.
      let compared = await close.reconciliation("SUBLEDGER_TO_GL");
      let lead = `${text(compared, "reconciliation_no")} stood ${text(compared, "status")}`;
      if (!["DRAFT", "PREPARED"].includes(text(compared, "status"))) {
        compared = await generate("Subledger to GL", "SUBLEDGER_TO_GL");
        lead = `${text(compared, "reconciliation_no")} generated`;
      } else if ((at(compared, "trial_balance") ?? null) === null) {
        await maya.goto(`${COCKPIT}/reconciliations/${text(compared, "id")}?${CONTEXT}`);
      }
      if (
        text(compared, "status") === "DRAFT" &&
        (at(compared, "trial_balance") ?? null) === null
      ) {
        const first = await attach("tb-avm-us-sep-2026-first.csv", [`2100,${currency},0.00`]);
        const balances = balancesOf(first, currency);
        compared = first;
        lead += `; compared with one line (job ${text(first, "trial_balance", "job", "state")}) it states ${String(balances.length)} account balance(s)`;
        if (balances.length > 0) {
          const second = await generate("Subledger to GL", "SUBLEDGER_TO_GL");
          if (text(second, "id") !== text(first, "id")) {
            compared = await attach("tb-avm-us-sep-2026.csv", balances);
            lead += `; ${text(second, "reconciliation_no")} compared with them: job ${text(compared, "trial_balance", "job", "state")}, ${text(compared, "variance_count")} difference(s)`;
          } else {
            lead += "; a second reconciliation was not generated, so the first is explained";
          }
        }
      }
      return `${lead}; ${await prepare("SUBLEDGER_TO_GL")}; ${await review("SUBLEDGER_TO_GL")}`;
    },
    reached: () => cleared("SUBLEDGER_TO_GL"),
    api: () => throughApi("SUBLEDGER_TO_GL"),
  });
  return billing && ledger;
}

/** "Submit for lock" on the cockpit; the row says what the dialog answered. */
function submitForLock(close: Close, name: string, expected: string): Promise<boolean> {
  const { qa, maya, preparer } = close;
  /**
   * A refused submission is index 281 where the hold alone refuses it: the contract is on hold, and
   * the gates that have not passed are the hold's own and journal completeness with nothing but
   * held postings in its detail (the Controller's certification is the lock's, not the request's).
   */
  const theHoldAlone = async (): Promise<string | undefined> => {
    if (!(await close.onHold())) {
      return undefined;
    }
    const failing = (await close.checklist()).filter(
      (item) => !["PASSED", "WAIVED", "NOT_APPLICABLE"].includes(text(item, "status")),
    );
    const codes = failing.map((item) => text(item, "gate_check_code"));
    const hold = codes.includes(HOLD_GATE);
    const complete = failing.find((item) => text(item, "gate_check_code") === "JE_COMPLETE");
    if (
      codes.some((code) => ![HOLD_GATE, "JE_COMPLETE", "CONTROLLER_CERTIFIED"].includes(code)) ||
      (!hold && complete === undefined)
    ) {
      return undefined;
    }
    const detail = text(complete, "result", "detail");
    if (
      complete !== undefined &&
      (!/: held /.test(detail) ||
        /: uncovered |differs from covered activity|JE sequence gap|held detail unverifiable|not calculated/.test(
          detail,
        ))
    ) {
      return undefined;
    }
    return HOLD_ITEM;
  };
  return flowStep(qa.record, {
    head: head(name, "maya", COCKPIT, expected),
    page: maya,
    known: theHoldAlone,
    screen: async () => {
      await maya.goto(COCKPIT);
      const shown = await blockersOnScreen(maya);
      await maya.getByRole("button", { name: "Submit for lock" }).first().click();
      const dialog = modal(maya, `Submit ${LABEL} for lock`);
      await dialog
        .getByRole("textbox", { name: /^Certification comment/ })
        .fill("September 2026 close is complete and reviewed.");
      await dialog.getByRole("button", { name: "Submit for lock" }).click();
      const done = maya.getByText(new RegExp(`^Submitted ${LABEL} for lock`));
      const refused = dialog.getByRole("alert");
      await done.or(refused).first().waitFor({ state: "visible", timeout: 60_000 });
      const before = `blockers on the screen before the press: [${shown.join("; ") || "none"}]`;
      const isRefused = await refused
        .first()
        .isVisible()
        .catch(() => false);
      if (isRefused) {
        const words = flat(await refused.first().innerText(), 500);
        await dialog
          .getByRole("button", { name: "Cancel" })
          .click()
          .catch(() => undefined);
        return `refused: "${words}"; ${before}; gates not cleared by the API: ${(await close.openGates()).join("; ")}`;
      }
      return `"${flat(await done.first().innerText(), 160)}"; ${before}`;
    },
    reached: async () =>
      (await close.state()) === "closed" || (await close.pendingLock()) !== undefined
        ? null
        : `no pending PERIOD_LOCK request of the period; gates not cleared: ${(await close.openGates()).join("; ")}`,
    api: async () =>
      preparer.send(
        "POST",
        `/api/v1/periods/${close.period}/request-lock`,
        { certification_comment: "September 2026 close is complete and reviewed." },
        await close.ifMatch(),
      ),
  });
}

interface Held {
  readonly said: string;
  /** The subledger lines of the month that belong to the contract under the hold. */
  readonly lines: number;
  /** The subledger's REVENUE of the month less the journals', in minor units; null when unread. */
  readonly apart: bigint | null;
  readonly tieFailed: boolean;
  /** Every one of those lines is answered without the journal run that covers it. */
  readonly unnamed: boolean;
}

/**
 * What the journals of the month hold of the subledger, and of the contract under the hold. The
 * subledger line's own `journal_run_id` is not read: the API answers null for every line. So the
 * measure is the figure itself — the REVENUE role of the month in the subledger (the cockpit's
 * journal preview, every line of the period) against the REVENUE lines of the month's journal runs —
 * beside what the gates say and the tie-out of the month's waterfall.
 */
async function heldLines(close: Close): Promise<Held> {
  const { preparer, heldId } = close;
  let ofContract = `the world holds no contract ${HELD}`;
  let count = 0;
  let unnamed = false;
  if (heldId !== "") {
    const lines = await preparer.list("/api/v1/subledger-lines", {
      contract: heldId,
      book: BOOK,
      period: SEPTEMBER,
    });
    count = lines.length;
    unnamed = count > 0 && lines.every((line) => text(line, "journal_run_id") === "");
    // Amounts are signed debit positive (04 API-S-SubledgerLine): revenue is the credit side.
    let revenue = 0n;
    for (const line of lines) {
      if (text(line, "account_role") === "REVENUE") {
        revenue -= cents(money(at(line, "amount_functional"))) ?? 0n;
      }
    }
    ofContract = `${HELD} is ${(await close.onHold()) ? "on hold" : "not on hold"}; its subledger lines of ${SEPTEMBER}: ${String(count)}, REVENUE ${decimal(revenue)}`;
  }
  const subledger = await subledgerRevenue(preparer, close.period);
  const journals = await journalRevenue(preparer, ENTITY, BOOK, SEPTEMBER);
  const left = cents(subledger);
  const right = cents(journals.total);
  const apart = left === null || right === null ? null : left - right;
  const gate = async (code: string) => {
    const item = await close.gate(code);
    return `${text(item, "name")}: ${text(item, "status")}${text(item, "result", "count") === "" ? "" : `, count ${text(item, "result", "count")}`}${text(item, "result", "detail") === "" ? "" : ` (${flat(text(item, "result", "detail"), 300)})`}${text(item, "waiver_approval_request_id") === "" ? "" : ", under a waiver request"}`;
  };
  const waterfall = await makeRun(preparer, "revenue_waterfall", {
    entity_codes: [ENTITY],
    book: BOOK,
    from_period_key: SEPTEMBER,
    to_period_key: SEPTEMBER,
  });
  const ties = tieOuts(waterfall.run);
  return {
    said: `${ofContract}; REVENUE of ${SEPTEMBER}: subledger ${subledger || "unread"}, journals ${journals.total || "unread"}${apart === null ? "" : `, apart by ${decimal(apart)}`}; journal runs of the month: ${journals.runs.join("; ") || "none"}; gates — ${await gate(HOLD_GATE)}; ${await gate("JE_COMPLETE")}; ${await gate("JE_BALANCED")}; the month's waterfall (${waterfall.said}): ${ties.lines.join("; ") || "no tie-out stated"}`,
    lines: count,
    apart,
    tieFailed: ties.failed.length > 0,
    unnamed,
  };
}

export async function closeSection(qa: Qa): Promise<void> {
  const { record, sessions } = qa;
  const maya = await sessions.page("maya");
  const priya = await sessions.page("priya");
  const marcus = await sessions.page("marcus");
  const reader = new Api(maya);
  const period = await periodId(reader, ENTITY, SEPTEMBER);
  const held = (await reader.list("/api/v1/contracts", { entity: ENTITY, q: HELD })).find(
    (item) => text(item, "external_id") === HELD,
  );
  const close = new Close(qa, period, text(held, "id"), maya, priya, marcus);
  const { preparer } = close;

  await record.check(
    head(
      "C-0 the cockpit before the close",
      "marcus",
      COCKPIT,
      'The cockpit lists the blockers with their counts and links, each count the count of the list it opens (PRD J-13.1); "Lock period" is offered to the Controller and disabled with its reasons',
    ),
    () => cockpitCheck(close),
  );
  if ((await close.state()) === "closed") {
    record.note(
      `C: ${ENTITY} ${SEPTEMBER} is closed already: the section ran on this world before`,
    );
    return;
  }

  await record.check(
    head(
      "C-1 the pending requests of the month",
      "priya",
      "/approvals/requests/<each>",
      "priya decides the pending activation and reviews the judgement record with a fresh code (PRD J-13.2; BR-PLT-06); the blocker counts fall",
    ),
    () => decideRequests(close),
  );
  await record.check(
    head(
      "C-2 the exceptions that hold the period",
      "maya",
      "/data/exceptions/<each>",
      "Each item of the rejected import is dismissed with its reason on SF-11:item (PRD J-13.3; BR-DAT-04) and leaves the period's blockers",
    ),
    () => dismissExceptions(close),
  );
  await record.check(
    head(
      "C-3 the hold released on the screen",
      "maya",
      `/contracts/<${HELD}>/obligations`,
      `The workbench of a contract on hold offers "Release hold" (SCREENS §4.1.6 'renders only when on_hold'; §4.9.4 the drawer; §5.6 the obligation pane's Holds table); maya releases the WLD-B-05 hold with her comment and the Holds blocker clears (PRD J-13.4)`,
    ),
    () => releaseOnScreen(close),
  );

  // The other exit the screens may offer: a waiver of the gate, asked by maya and decided by another.
  if (await close.onHold()) {
    const waiverOf = async () => text(await close.gate(HOLD_GATE), "waiver_approval_request_id");
    const cleared = async () =>
      ["WAIVED", "PASSED", "NOT_APPLICABLE"].includes(text(await close.gate(HOLD_GATE), "status"));
    const reason = "The dispute on invoice INV-US-3988 is open; the hold stays over the month end.";
    const asked = await flowStep(record, {
      head: head(
        "C-4a the gate of the hold: a waiver asked on the cockpit",
        "maya",
        COCKPIT,
        `The checklist's row "${HOLD_GATE_LABEL}" offers "Request waiver" to a member with period.close (SCREENS_B §1.1; 04 §16.8: every gate but journal balancing, journal completeness, the close run and the certification is waivable); the gate then names its waiver request`,
      ),
      page: maya,
      screen: async () => {
        await maya.goto(COCKPIT);
        const row = maya
          .getByTestId("SF-05-grid-checklist")
          .getByRole("row")
          .filter({ hasText: HOLD_GATE_LABEL });
        await row.first().waitFor({ state: "visible", timeout: 30_000 });
        const offered = await buttonsOf(row.first());
        await row
          .first()
          .getByRole("button", { name: "Request waiver" })
          .click({ timeout: 15_000 });
        const dialog = modal(maya, /^Request a waiver of /);
        await dialog.getByRole("textbox").first().fill(reason);
        await dialog.getByRole("button", { name: "Request waiver" }).click();
        await dialog.waitFor({ state: "hidden", timeout: 30_000 });
        await until(waiverOf, (found) => found !== "", 30_000);
        return `the row offered [${offered.join(", ")}]; the waiver was asked on the screen`;
      },
      reached: async () =>
        (await cleared()) || (await waiverOf()) !== ""
          ? null
          : `the gate "${HOLD_GATE_LABEL}" is ${text(await close.gate(HOLD_GATE), "status")}, is_waivable ${String(at(await close.gate(HOLD_GATE), "is_waivable"))}, and names no waiver request`,
      api: async () =>
        preparer.send(
          "POST",
          `/api/v1/periods/${period}/checklist/${text(await close.gate(HOLD_GATE), "id")}/waive`,
          { reason },
          await close.ifMatch(),
        ),
    });
    const waived =
      asked &&
      (await flowStep(record, {
        head: head(
          "C-4b the waiver decided",
          "priya or marcus",
          "/approvals/requests/<the waiver's request>",
          "The request goes to a holder of exception.waive other than the requester and the gate's owner (PRD §2.5; 04 §16.8), who approves with a fresh code (BR-PLT-06); the approved waiver clears the gate for the lock",
        ),
        page: priya,
        screen: async () => {
          const requestId = await waiverOf();
          if (requestId === "") {
            return "the gate names no waiver request";
          }
          // The decider: a holder of exception.waive who did not ask for it (PRD §2.5 routing).
          const said2: string[] = [];
          for (const [persona, page] of [
            ["priya", close.priya],
            ["marcus", close.marcus],
          ] as const) {
            const request = (await new Api(page).get(`/api/v1/approvals/${requestId}`)).json;
            if (at(request, "can_decide") !== true) {
              said2.push(
                `${persona} cannot decide ${text(request, "request_no") || requestId} (status ${text(request, "status") || "unread"})`,
              );
              continue;
            }
            const decided = await approveOnScreen(
              page,
              persona,
              requestId,
              "The dispute is documented; the hold may stand over the month end.",
            );
            return `${text(request, "request_no")} "${text(request, "summary")}" decided by ${persona}: "${decided.toast}"`;
          }
          return said2.join("; ");
        },
        reached: async () => {
          const item = await close.gate(HOLD_GATE);
          return (await cleared())
            ? null
            : `the gate "${text(item, "name")}" is ${text(item, "status")}${text(item, "waiver_approval_request_id") === "" ? "" : " with a waiver request pending"}`;
        },
        api: async () => {
          const requestId = await waiverOf();
          const comment = "The dispute is documented; the hold may stand over the month end.";
          const asPriya = (await close.reviewer.get(`/api/v1/approvals/${requestId}`)).json;
          return at(asPriya, "can_decide") === true
            ? approveThroughApi(close.reviewer, "priya", requestId, comment)
            : approveThroughApi(close.controller, "marcus", requestId, comment);
        },
      }));
    if (waived) {
      close.hold = "waived";
    }
  }

  const soft = await flowStep(record, {
    head: head(
      "C-5 the soft close",
      "marcus",
      COCKPIT,
      `"Start soft close" moves the period to closing and the cockpit says so (PRD J-13.6, SM-07; 03 REQ-CLS-003)`,
    ),
    page: marcus,
    screen: async () => {
      await marcus.goto(COCKPIT);
      await marcus.getByRole("button", { name: "Start soft close" }).first().click();
      const dialog = modal(marcus, `Start soft close for ${LABEL}?`);
      await dialog.getByRole("textbox").first().fill("September close in progress");
      await dialog.getByRole("button", { name: "Start soft close" }).click();
      const banner = marcus.getByTestId("SF-05-banner-soft-close");
      await banner.waitFor({ state: "visible", timeout: 30_000 });
      return `the soft-close banner reads "${flat(await banner.innerText(), 200)}"`;
    },
    reached: async () =>
      ["closing", "closed"].includes(await close.state())
        ? null
        : `the period is ${await close.state()}`,
    api: async () =>
      close.controller.send(
        "POST",
        `/api/v1/periods/${period}/start-close`,
        { comment: "September close in progress." },
        await close.ifMatch(),
      ),
  });
  if (!soft) {
    return;
  }

  const ran = await flowStep(record, {
    head: head(
      "C-6 the close run",
      "maya",
      `${COCKPIT}/close-run`,
      'The "Close run" tab offers "Run close"; the run shows its steps and ends SUCCEEDED with the period\'s journal run calculated as a draft (PRD J-13.7; 03 REQ-CLS-012)',
    ),
    page: maya,
    screen: async () => {
      await maya.goto(`${COCKPIT}/close-run`);
      await maya.getByRole("button", { name: "Run close" }).first().click();
      await maya
        .getByRole("region", { name: /^Close run CLS-\d+$/ })
        .waitFor({ state: "visible", timeout: 60_000 });
      const run = await until(
        () => close.latestCloseRun(),
        (item) => !["PENDING", "RUNNING", ""].includes(text(item, "status")),
        JOB_MS,
      );
      const steps = items(run, "steps").map(
        (step) =>
          `${text(step, "step_code")} ${text(step, "status")}${text(step, "problem", "title") === "" ? "" : ` (${text(step, "problem", "title")}: ${flat(text(step, "problem", "detail"), 120)})`}`,
      );
      const list = flat(
        await maya
          .getByRole("list", { name: "Close run steps" })
          .innerText({ timeout: 5_000 })
          .catch(() => ""),
        300,
      );
      return `${text(run, "close_run_no")} ${text(run, "status")}; steps: ${steps.join(", ")}; the screen's step list reads "${list}"`;
    },
    reached: async () => {
      const run = await close.latestCloseRun();
      return text(run, "status") === "SUCCEEDED"
        ? null
        : `the latest close run is ${text(run, "close_run_no") || "none"} ${text(run, "status")}`;
    },
    api: async () => {
      const started = await preparer.send("POST", "/api/v1/close-runs", {
        entity_code: ENTITY,
        period_key: SEPTEMBER,
        book: BOOK,
      });
      await until(
        () => close.latestCloseRun(),
        (item) => !["PENDING", "RUNNING", ""].includes(text(item, "status")),
        JOB_MS,
      );
      return started;
    },
  });
  if (!ran) {
    return;
  }
  // The fact the reading of the hold rests on, as soon as the close run has released the month.
  await record.check(
    head(
      "C-6a the held contract's postings of the month",
      "maya",
      `GET /api/v1/subledger-lines?contract=<${HELD}>&period=${SEPTEMBER}`,
      `The close run releases September for every contract, the one under a journal-export hold among them: a hold of that type keeps lines from the journal, not from the subledger (04 E-45; ENGINE_SPEC_B S14-R-17)`,
    ),
    async () => {
      const evidence = await heldLines(close);
      return {
        observed: `${evidence.said}; the hold was ${close.hold}`,
        result: evidence.lines > 0 ? "pass" : "seen once",
      };
    },
  );
  const firstRun = text(await close.latestCloseRun(), "journal_run_id");
  if (firstRun === "") {
    record.row({
      ...head(
        "C-7 the journal run of the close",
        "maya",
        `${COCKPIT}/close-run`,
        "The close run names the journal run it calculated (PRD J-13.7)",
      ),
      observed: "the close run that succeeded names no journal run",
      result: "FINDING",
      finding: "stopped flow",
    });
    return;
  }
  if (!(await journalCycle(close, "C-7", firstRun)) || !(await reconcile(close, "C-8"))) {
    return;
  }

  let submitted = await submitForLock(
    close,
    "C-9 submitted for lock, the screens alone",
    '"Submit for lock" shows the close gates and takes the certification comment; with every gate but the Controller\'s cleared the request goes to a Controller (PRD J-13.13; J-13-AC-1: until then 409 close-gates-failed names each failing gate)',
  );
  if (!submitted) {
    // The screens alone did not reach the lock. What holds it is written down first; when it is the
    // hold — its own gate, or the journal's completeness over the lines the hold keeps out — the
    // hold is released through the API, which is the one way left, and the walk goes on so that the
    // steps behind it are still measured. Gates of another kind end the walk here.
    const evidence = await heldLines(close);
    const statusOf = async (code: string) => text(await close.gate(code), "status");
    const open2 = (status: string) => !["PASSED", "WAIVED", "NOT_APPLICABLE"].includes(status);
    const holdGate = await statusOf(HOLD_GATE);
    const complete = await statusOf("JE_COMPLETE");
    const byTheHold =
      (await close.onHold()) && (open2(holdGate) || (open2(complete) && evidence.lines > 0));
    await record.check(
      head(
        "C-9a what holds the lock",
        "maya",
        COCKPIT,
        "Every gate but the Controller's certification is cleared before the submission (PRD J-13-AC-2)",
      ),
      async () => ({
        observed: `gates not cleared: ${(await close.openGates()).join("; ") || "none"}. The hold was ${close.hold}; ${evidence.said}. ${byTheHold ? `The hold stands in the lock's way ("${HOLD_GATE_LABEL}" ${holdGate}, journal completeness ${complete}, ${String(evidence.lines)} subledger line(s) of ${HELD} in the month): it is released through the API next.` : "The gates that refuse the lock are not the hold's: the walk ends here."}`,
        result: "seen once",
        page: maya,
      }),
    );
    if (!byTheHold) {
      return;
    }
    await record.check(
      head(
        "C-9b the hold released through the API",
        "maya",
        `POST /api/v1/contracts/<${HELD}>/release-hold`,
        "The command J-13.4 names releases the hold (04 §16.1); it is sent through the API because the screens did not release it (check C-3)",
      ),
      async () => {
        const contract = (await preparer.get(`/api/v1/contracts/${close.heldId}`)).json;
        // The id the command takes: the hold's own where the contract's read lists its holds
        // (04 §16.1 `holds`), else the id of its HOLD_APPLIED event, which is the same key.
        let holdId = text(contract, "holds", 0, "id");
        if (holdId === "") {
          const applied = await preparer.get(`/api/v1/contracts/${close.heldId}/events`, {
            event_type: "HOLD_APPLIED",
            limit: 5,
          });
          holdId = text(applied.json, "items", 0, "id");
        }
        const got = await preparer.send(
          "POST",
          `/api/v1/contracts/${close.heldId}/release-hold`,
          { hold_id: holdId, comment: RELEASE_COMMENT },
          { "If-Match": `"s${text(contract, "head_stream_version")}"` },
        );
        const released = !(await close.onHold());
        if (released) {
          close.hold = "released through the API";
        }
        return {
          observed: `POST release-hold → ${said(got)}; ${HELD} is ${released ? "not on hold" : "still on hold"}; gates not cleared now: ${(await close.openGates()).join("; ")}`,
          result: released ? "pass" : "not run",
        };
      },
    );
    // After the release the gates say what the lock still waits for, and the walk follows them
    // through the API, at most three rounds: a close run the contracts have overtaken is run
    // again (04 §16.8; SCREENS_B §1.1 "Close run out of date, run it again"); the lines the first
    // journal run left out are taken over by the month's next run (04 T-SL-06; ENGINE_SPEC_B
    // S14-R-17), which goes through its cycle; a reconciliation the period has overtaken is
    // generated again. The submission is asked for once no gate but the Controller's is open.
    const body = { entity_code: ENTITY, period_key: SEPTEMBER, book: BOOK };
    const draftRun = async () =>
      (
        await preparer.list("/api/v1/journal-runs", {
          entity: ENTITY,
          book: BOOK,
          period: SEPTEMBER,
        })
      ).find((run) => !close.runs.includes(text(run, "id")) && text(run, "state") === "draft");
    for (let round = 1; round <= 3 && (await close.openCodes()).length > 0; round += 1) {
      let nextRun = "";
      await record.check(
        head(
          `C-9c.${String(round)} after the release: the close run and the journal run the gates ask for`,
          "maya",
          "POST /api/v1/close-runs; POST /api/v1/journal-runs",
          "The lines a run left out as held are journalised by the next run of the month once the hold is released (04 T-SL-06; ENGINE_SPEC_B S14-R-17); a close run the contracts have overtaken is run again (04 §16.8)",
        ),
        async () => {
          const lines: string[] = [];
          const codes = await close.openCodes();
          lines.push(`gates not cleared: ${(await close.openGates()).join("; ") || "none"}`);
          if (codes.includes("CLOSE_RUN_COMPLETED") || codes.includes("NO_DIRTY_GROUPS")) {
            const before = text(await close.latestCloseRun(), "id");
            const started = await preparer.send("POST", "/api/v1/close-runs", body);
            const run = await until(
              () => close.latestCloseRun(),
              (item) =>
                started.status >= 300 ||
                (text(item, "id") !== before &&
                  !["PENDING", "RUNNING", ""].includes(text(item, "status"))),
              JOB_MS,
            );
            lines.push(
              `POST close-runs → ${said(started)}; the latest close run is ${text(run, "close_run_no")} ${text(run, "status")}`,
            );
          }
          let next = await draftRun();
          if (
            next === undefined &&
            (await close.openCodes()).some((code) => code.startsWith("JE_"))
          ) {
            const asked = await preparer.send("POST", "/api/v1/journal-runs", body);
            const job = asked.status === 202 ? await preparer.job(asked, JOB_MS) : "not started";
            lines.push(`POST journal-runs → ${said(asked)}, job ${job}`);
            next = await draftRun();
          }
          nextRun = text(next, "id");
          return {
            observed: `${lines.join("; ")}; ${next === undefined ? "no new draft journal run of the month" : `new journal run ${text(next, "run_no")} with ${text(next, "totals", "line_count")} lines`}`,
            result: "pass",
          };
        },
      );
      if (nextRun !== "") {
        await journalCycle(close, `C-9d.${String(round)}`, nextRun);
      }
      await reconcile(close, `C-9e.${String(round)}`);
    }
    const left = await close.openGates();
    if ((await close.openCodes()).length > 0) {
      record.row({
        ...head(
          "C-9f submitted for lock, after the release through the API",
          "maya",
          COCKPIT,
          "With the hold released and its lines journalised the request goes to a Controller (PRD J-13.13)",
        ),
        observed: `not asked for: three rounds after the release the gates still wait — ${left.join("; ")}`,
        result: "seen once",
      });
      return;
    }
    submitted = await submitForLock(
      close,
      "C-9f submitted for lock, after the release through the API",
      "With the hold released and its lines journalised the request goes to a Controller (PRD J-13.13)",
    );
  }
  if (!submitted) {
    return;
  }

  // The lock on the cockpit, as PRD J-13.14 has it. The control is read by its own attributes and
  // pressed only where it is available: the development session of 2026-10-02 found it disabled by
  // the pending lock request it decides (the gate "No pending approvals" counts that request). It
  // is read when the cockpit has settled and its read of the period's requests has come
  // (`lockControl`): the first run of record read it before that read, twice.
  const control = async (): Promise<{ readonly available: boolean; readonly said: string }> => {
    const seen = await open(marcus, COCKPIT);
    const found = await lockControl(marcus, (await close.pendingLock()) !== undefined);
    const blockers = await blockersOnScreen(marcus);
    return {
      available: found.available,
      said: `the cockpit is ${seen.state}; ${found.said}; blockers on the screen [${blockers.join("; ") || "none"}]; gates not cleared by the API: ${(await close.openGates()).join("; ") || "none"}`,
    };
  };
  let onCockpit = false;
  await record.check(
    head(
      "C-10 the lock on the cockpit",
      "marcus",
      COCKPIT,
      `"Lock period" takes the Controller's reason and a fresh code; ${ENTITY} ${LABEL} is closed and October opens (PRD J-13.14; BR-CLS-02, BR-CLS-03; BR-PLT-06)`,
    ),
    async () => {
      if ((await close.state()) === "closed") {
        onCockpit = true;
        return { observed: "the period is closed already; nothing was pressed", result: "pass" };
      }
      const first = await control();
      // Read twice before it is written: the cockpit is opened once more.
      const second = first.available ? first : await control();
      if (!second.available) {
        const request = await close.pendingLock();
        const open2 = await close.openCodes();
        const approvals = await close.gate("APPROVALS_CLEARED");
        // Index 296 where the lock request itself is the one pending approval that fails the gate.
        const ownRequest =
          request !== undefined &&
          open2.length === 1 &&
          open2[0] === "APPROVALS_CLEARED" &&
          text(approvals, "result", "count") === "1";
        const observed = `THE COCKPIT'S "LOCK PERIOD" IS NOT AVAILABLE TO THE CONTROLLER, twice: ${first.said} || ${second.said}. The pending lock request of the period is ${text(request, "request_no") || "not listed"}; the lock is taken on the request's own screen next (C-10b).`;
        return ownRequest
          ? { observed, result: "KNOWN", known: LOCK_ITEM, page: marcus }
          : { observed, result: "FINDING", finding: "stopped flow", page: marcus };
      }
      await marcus.getByRole("button", { name: "Lock period" }).first().click();
      const dialog = modal(marcus, `Lock ${LABEL} for ${ENTITY}?`);
      await dialog.getByRole("textbox").last().fill("September 2026 close complete.");
      await dialog.getByRole("button", { name: "Lock period" }).click();
      const asked = await afterStepUp(
        marcus,
        "marcus",
        marcus.getByText(`${ENTITY} ${LABEL} locked.`),
      );
      const state = await until(
        () => close.state(),
        (found) => found === "closed",
        120_000,
      );
      onCockpit = state === "closed";
      return {
        observed: `${second.said}; ${asked ? "a code was asked" : "no code was asked"}; "${ENTITY} ${LABEL} locked."; the period is ${state}`,
        result: onCockpit ? "pass" : "seen once",
        page: marcus,
      };
    },
  );
  // The other screen a lock request is decided on: its own (SF-12:request; the cockpit's "View lock
  // request"). Where the cockpit took the lock the end state stands and nothing is pressed.
  const locked = await flowStep(record, {
    head: head(
      "C-10b the lock on the request's own screen",
      "marcus",
      "/approvals/requests/<the lock request>",
      `A PERIOD_LOCK request is decided by a Controller other than its requester with a fresh code (PRD SM-07, BR-CLS-02, BR-PLT-06); the approved request locks the period: ${ENTITY} ${LABEL} is closed and October opens (BR-CLS-03)`,
    ),
    page: marcus,
    screen: async () => {
      const request = await close.pendingLock();
      if (request === undefined) {
        return "no pending PERIOD_LOCK request of the period is listed to marcus";
      }
      const decided = await approveOnScreen(
        marcus,
        "marcus",
        text(request, "id"),
        "September 2026 close complete.",
      );
      const state = await until(
        () => close.state(),
        (found) => found === "closed",
        120_000,
      );
      return `${text(request, "request_no")} "${text(request, "summary")}": ${decided.stepUp ? "a code was asked" : "no code was asked"}; "${decided.toast}"; the period is ${state}`;
    },
    reached: async () =>
      (await close.state()) === "closed" ? null : `the period is ${await close.state()}`,
    api: async () => {
      const request = await close.pendingLock();
      const got = await approveThroughApi(
        close.controller,
        "marcus",
        text(request, "id"),
        "September 2026 close complete.",
      );
      await until(
        () => close.state(),
        (found) => found === "closed",
        120_000,
      );
      return got;
    },
  });
  if (!locked) {
    return;
  }

  await record.check(
    head(
      "C-11 what the lock stands over",
      "maya",
      `${COCKPIT}; GET subledger-lines, journal-runs/<id>/lines, periods/<id>/checklist`,
      `A locked month's journals hold the month's subledger (PRD J-13-AC-2 "journal completeness"; J-13-AC-3 "journal totals by account equal waterfall activity", CTL-019): the REVENUE role of the month is one amount in the subledger and in the journal runs, with the lines of ${HELD} among them, and the month's waterfall ties to the revenue journal`,
    ),
    async () => {
      const lead = `the lock was reached with the hold ${close.hold}`;
      const evidence = await heldLines(close);
      if (evidence.unnamed) {
        // Outside the three classes: one line, no analysis.
        record.parked(
          "maya",
          `GET /api/v1/subledger-lines?contract=<${HELD}>&period=${SEPTEMBER}`,
          `KNOWN (register index 265): journal_run_id is null on each of the ${String(evidence.lines)} lines of a locked month; 04 API-S-SubledgerLine states it names the journal run whose range covers the line's posting`,
        );
      }
      if ((evidence.apart !== null && evidence.apart !== 0n) || evidence.tieFailed) {
        return {
          observed: `A LOCKED MONTH WHOSE JOURNALS DO NOT HOLD ITS SUBLEDGER: ${lead}; ${evidence.said}`,
          result: "FINDING",
          finding: "wrong figure",
          page: maya,
        };
      }
      return {
        observed: `${lead}; ${evidence.said}`,
        result: evidence.apart === null ? "seen once" : "pass",
      };
    },
  );

  await record.check(
    head(
      "C-12 the locked month, every place",
      "marcus",
      `${COCKPIT}; revenue_waterfall; GET periods/<id>/cockpit; GET dashboard/home`,
      `The period is closed and October is open (BR-CLS-03); both reconciliations are CERTIFIED; each journal run balances; the month's recognized revenue is one amount in the waterfall's total line, in the subledger's REVENUE role and in Home's key figure (PRD J-13.14, J-13-AC-3)`,
    ),
    async () => {
      const controller = close.controller;
      const periods = await controller.list("/api/v1/periods", { entity: ENTITY, book: BOOK });
      const october = periods.find((item) => text(item, "period", "period_key") === "FY2026-P10");
      const subledger = await subledgerRevenue(controller, period);
      const run = await makeRun(controller, "revenue_waterfall", {
        entity_codes: [ENTITY],
        book: BOOK,
        from_period_key: SEPTEMBER,
        to_period_key: SEPTEMBER,
      });
      const total = (run.id === "" ? [] : await reportRows(controller, run.id)).find((row) =>
        text(row, "row_key").startsWith("TOTAL:"),
      );
      const waterfall = money(at(total, `period:${SEPTEMBER}`));
      const home = money(
        at(
          (
            await controller.get("/api/v1/dashboard/home", {
              entity: ENTITY,
              period: SEPTEMBER,
              book: BOOK,
            })
          ).json,
          "revenue",
          "current",
        ),
      );
      const statuses = [
        text(await close.reconciliation("BILLING_TO_SUBLEDGER"), "status"),
        text(await close.reconciliation("SUBLEDGER_TO_GL"), "status"),
      ];
      const wrong: string[] = [];
      const journals: string[] = [];
      for (const id of close.runs) {
        const journal = await close.run(id);
        const debit = money(at(journal, "totals", "debit_functional"));
        const credit = money(at(journal, "totals", "credit_functional"));
        journals.push(
          `${text(journal, "run_no")} ${text(journal, "state")}, Dr ${grouped(debit)} Cr ${grouped(credit)}`,
        );
        if (at(journal, "totals", "balanced") !== true || cents(debit) !== cents(credit)) {
          wrong.push(`${text(journal, "run_no")} does not balance: Dr ${debit}, Cr ${credit}`);
        }
      }
      if (cents(waterfall) !== cents(subledger) || cents(waterfall) !== cents(home)) {
        wrong.push(
          `recognized revenue: waterfall ${waterfall}, subledger ${subledger}, Home ${home}`,
        );
      }
      const seen = await open(marcus, COCKPIT);
      const observed = `${ENTITY} ${SEPTEMBER} is ${await close.state()}, FY2026-P10 is ${text(october, "state")}; reconciliations ${statuses.join(" and ")}; journal runs: ${journals.join("; ")}; recognized revenue: waterfall ${waterfall} (${run.said}), subledger ${subledger}, Home ${home}; the cockpit reads "${seen.heading}" (${seen.state})`;
      return wrong.length === 0
        ? { observed, result: "pass", page: marcus }
        : {
            observed: `THE PLACES DISAGREE: ${wrong.join(" | ")}. ${observed}`,
            result: "FINDING",
            finding: "wrong figure",
            page: marcus,
          };
    },
  );
}
