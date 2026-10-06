// Screen steps several sections of the pass share (release candidate QA; PROGRESS.md D-99 (7)): a
// decision on SF-12:request with its step-up (PRD BR-PLT-06), the toasts, the figures a screen
// states, and the rule of the pass for a flow step — the screen first, twice, and only then the API,
// said in the row. The control names are those the committed rows of project `screens` and the rc
// smoke journey press.
import type { Locator, Page } from "@playwright/test";

import { type Persona, personaEmail } from "../auth";
import { nextCode } from "../totp";
import type { Api, Got } from "./api";
import { said, text } from "./api";
import { look } from "./observe";
import { type CheckHead, errorLine, flat, type Outcome, type QaRecord } from "./record";

const STEP_MS = 30_000;
/**
 * The cap of a flow step (record.ts `check`): the screen twice and the API once, each of which may
 * wait fifteen minutes for a job. A step that is left while it still runs would run into the steps
 * behind it, so its cap is the three waits and a margin, not the cap of a plain check.
 */
const FLOW_CAP_MS = 50 * 60_000;

/** The messages shown now (DS-CMP-20), newest last. */
export async function toasts(page: Page): Promise<readonly string[]> {
  const texts = await page
    .getByRole("region", { name: "Messages" })
    .locator('[role="status"], [role="alert"]')
    .allInnerTexts()
    .catch(() => [] as string[]);
  return texts.map((item) => flat(item, 300)).filter((item) => item !== "");
}

export async function dismissToasts(page: Page): Promise<void> {
  const buttons = page
    .getByRole("region", { name: "Messages" })
    .getByRole("button", { name: "Dismiss message" });
  for (let left = await buttons.count(); left > 0; left -= 1) {
    await buttons
      .first()
      .click({ timeout: 2_000 })
      .catch(() => undefined);
  }
}

/** Answers "Confirm with your authenticator" when it shows; a refused code is tried with a later step. */
export async function answerStepUp(page: Page, persona: Persona): Promise<boolean> {
  const dialog = page.getByRole("dialog", { name: "Confirm with your authenticator" });
  if (!(await dialog.isVisible().catch(() => false))) {
    return false;
  }
  let refused: number | undefined;
  for (let attempt = 0; attempt < 3 && (await dialog.isVisible()); attempt += 1) {
    const { code, step } = await nextCode(personaEmail(persona), refused);
    await dialog.getByRole("textbox", { name: /^Authentication code/ }).fill(code);
    await dialog.getByRole("button", { name: "Confirm", exact: true }).click();
    const wrong = dialog.getByText(/did not match/);
    await Promise.race([
      dialog.waitFor({ state: "hidden", timeout: 15_000 }),
      wrong.waitFor({ state: "visible", timeout: 15_000 }),
    ]).catch(() => undefined);
    refused = step;
  }
  if (await dialog.isVisible().catch(() => false)) {
    throw new Error("the step-up dialog refused three codes");
  }
  return true;
}

/** Waits for `outcome`, answering the step-up when the command asks for one first. */
export async function afterStepUp(
  page: Page,
  persona: Persona,
  outcome: Locator,
): Promise<boolean> {
  const dialog = page.getByRole("dialog", { name: "Confirm with your authenticator" });
  await outcome.or(dialog).first().waitFor({ state: "visible", timeout: STEP_MS });
  const asked = await answerStepUp(page, persona);
  await outcome.first().waitFor({ state: "visible", timeout: STEP_MS });
  return asked;
}

/**
 * A fresh second-factor verification of a persona's session through the API (04 POST /session/mfa),
 * for a command the pass sends itself after a screen did not reach its end state (PRD BR-PLT-06).
 * The session is reissued by it (05 SAR-09); the pass's client reads its token again by itself.
 */
export async function stepUpThroughApi(api: Api, persona: Persona): Promise<string> {
  let refused: number | undefined;
  let last = "";
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const { code, step } = await nextCode(personaEmail(persona), refused);
    const got = await api.send("POST", "/api/v1/session/mfa", { code });
    if (got.status === 200) {
      return "verified";
    }
    refused = step;
    last = said(got);
  }
  return `three codes refused (${last})`;
}

/**
 * The decision of SF-12:request through the API, for a flow whose screen step did not reach it: a
 * fresh verification, then the approval with the hashes the request states (04 REQ-PLT-014).
 */
export async function approveThroughApi(
  api: Api,
  persona: Persona,
  requestId: string,
  comment: string,
): Promise<Got> {
  await stepUpThroughApi(api, persona);
  const request = (await api.get(`/api/v1/approvals/${requestId}`)).json;
  const preview = text(request, "impact_preview", "sha256");
  return api.send("POST", `/api/v1/approvals/${requestId}/approve`, {
    subject_content_sha256: text(request, "subject", "content_sha256"),
    ...(preview === "" ? {} : { impact_preview_sha256: preview }),
    comment,
  });
}

/**
 * Approves the request the page shows (SF-12:request): the comment, "Approve", the step-up when it
 * is asked, the toast. It returns what the toast said and whether a code was asked.
 */
export async function approveOnScreen(
  page: Page,
  persona: Persona,
  requestId: string,
  comment: string,
): Promise<{ readonly toast: string; readonly stepUp: boolean }> {
  await page.goto(`/approvals/requests/${requestId}`);
  const form = page.getByRole("form", { name: "Decision" });
  await form.getByRole("textbox", { name: /^Comment/ }).fill(comment);
  await form.getByRole("button", { name: "Approve", exact: true }).click();
  const toast = page.getByText(/^Approved: /);
  const stepUp = await afterStepUp(page, persona, toast);
  return { toast: flat(await toast.first().innerText(), 200), stepUp };
}

/** A modal by its title: a plain one is a dialog, a confirmation an alertdialog (DS-CMP-11). */
export function modal(page: Page, name: string | RegExp): Locator {
  return page.getByRole("dialog", { name }).or(page.getByRole("alertdialog", { name }));
}

/** What the dialogs open now read, for a row whose step stopped inside one; empty when none is open. */
export async function openDialogs(page: Page): Promise<string> {
  const texts = await page
    .locator('[role="dialog"], [role="alertdialog"]')
    .evaluateAll((elements) =>
      elements
        .filter((element) => element.checkVisibility())
        .map((element) => (element as HTMLElement).innerText),
    )
    .catch(() => [] as string[]);
  return flat(texts.join(" / "), 400);
}

/** The commands a page offers now: the names of its visible buttons, for a row that found none. */
export async function buttonsOf(scope: Page | Locator): Promise<readonly string[]> {
  const names = await scope
    .getByRole("button")
    .evaluateAll((elements) =>
      elements
        .filter((element) => element.checkVisibility())
        .map((element) =>
          (element.getAttribute("aria-label") ?? element.textContent ?? "")
            .replace(/\s+/g, " ")
            .trim(),
        ),
    )
    .catch(() => [] as string[]);
  return [...new Set(names.filter((name) => name !== "" && !name.startsWith("Explain ")))];
}

export interface Figure {
  /** The figure's name, for example "Revenue · Sep 2026 · O1". */
  readonly label: string;
  /** The value as spoken, with its currency code: "USD 9,764.38". */
  readonly value: string;
}

/**
 * The figures a screen states: every computed number is an Explain trigger named
 * "Explain <label>, <value>" (DS-CMP-15; REQ-UX-005), so its accessible name carries the figure.
 */
export async function figures(scope: Page | Locator): Promise<readonly Figure[]> {
  const names = await scope
    .locator('button[aria-label^="Explain "]')
    .evaluateAll((elements) => elements.map((element) => element.getAttribute("aria-label") ?? ""));
  const found: Figure[] = [];
  for (const name of names) {
    const body = name.replace(/^Explain /, "");
    const at = body.lastIndexOf(", ");
    if (at === -1) {
      continue;
    }
    found.push({
      label: body.slice(0, at).trim(),
      value: body
        .slice(at + 2)
        .replace(/\s+/g, " ")
        .trim(),
    });
  }
  return found;
}

/** Scrolls a DS-CMP-10 grid until the row with `testId` is in the document (DG-FE-07), or gives up. */
export async function scrolledRow(
  page: Page,
  grid: Locator,
  testId: string,
): Promise<Locator | null> {
  const row = page.getByTestId(testId);
  await grid
    .evaluate((element) => {
      element.scrollTop = 0;
    })
    .catch(() => undefined);
  for (let turn = 0; turn < 200; turn += 1) {
    if ((await row.count()) > 0) {
      await row
        .first()
        .scrollIntoViewIfNeeded()
        .catch(() => undefined);
      return row.first();
    }
    const moved = await grid
      .evaluate((element) => {
        const before = element.scrollTop;
        element.scrollTop += element.clientHeight;
        return element.scrollTop > before;
      })
      .catch(() => false);
    if (!moved) {
      return (await row.count()) > 0 ? row.first() : null;
    }
    await page.evaluate(
      () =>
        new Promise<void>((resolve) =>
          requestAnimationFrame(() => {
            resolve();
          }),
        ),
    );
  }
  return null;
}

export interface FlowStep {
  readonly head: CheckHead;
  /** The page the step is taken on, captured with the row. */
  readonly page: Page;
  /** The step on the screen, as the member takes it. */
  readonly screen: () => Promise<string>;
  /** Null when the end state of the step is reached; otherwise what the API shows instead. */
  readonly reached: () => Promise<string | null>;
  /** The same command through the API, so that the flow can go on when the screen did not get there. */
  readonly api?: (() => Promise<Got>) | undefined;
  /**
   * The register index, when the stop is a known item: a number, or what answers it once the step
   * has stopped twice — a stop is the known item only where it shows what that item names.
   */
  readonly known?: string | (() => Promise<string | undefined>) | undefined;
}

/**
 * One step of a core flow under the rules of the pass. The screen is tried; when the end state is not
 * reached, it is tried a second time on a page opened again ("reproduced twice before it is
 * written"). A step that fails twice is a candidate of class 3; the pass then sends the command
 * through the API, where one is given, and says so, so that the steps behind it are still walked.
 * The answer says whether the end state stands when the step returns.
 */
export async function flowStep(record: QaRecord, step: FlowStep): Promise<boolean> {
  let ok = false;
  await record.check(
    step.head,
    async (): Promise<Outcome> => {
      const attempts: string[] = [];
      const before = await step.reached();
      if (before === null) {
        ok = true;
        return {
          observed: "the end state of the step stood already; nothing was pressed",
          result: "pass",
        };
      }
      for (let attempt = 1; attempt <= 2; attempt += 1) {
        let shown: string;
        let threw = false;
        try {
          shown = await step.screen();
        } catch (error) {
          threw = true;
          shown = `the screen step stopped: ${errorLine(error)}`;
        }
        const state = await step.reached();
        if (state === null) {
          ok = true;
          if (threw) {
            // The command went out from the screen and its end state stands; what ended early is the
            // pass's own wait for what the screen says next. Said, so that the row is not read as a stop.
            shown = `the end state of the step stands after the screen step; the pass's wait on the screen ended before it: ${shown}`;
          }
          return attempt === 1
            ? { observed: shown, result: "pass", page: step.page }
            : {
                observed: `first attempt: ${attempts.join(" | ")}; second attempt reached the end state: ${shown}`,
                result: "seen once",
                page: step.page,
              };
        }
        const seen = await look(step.page, step.head.address).catch(() => null);
        const dialogs = await openDialogs(step.page);
        attempts.push(
          `${shown}; the API shows: ${state}; the page: ${seen === null ? "unread" : `${seen.state}, "${seen.heading}", messages [${(await toasts(step.page)).join(" | ")}]`}${dialogs === "" ? "" : `; an open dialog reads "${dialogs}"`}`,
        );
        if (attempt === 1) {
          await step.page.reload().catch(() => undefined);
        }
      }
      let onward = "no API command was given for the step: the flow stops here";
      if (step.api !== undefined) {
        const got = await step.api();
        const state = await step.reached();
        ok = state === null;
        onward = `the same command through the API answered ${said(got)}${ok ? " and the end state stands: the flow goes on" : `; the API then shows: ${state ?? ""}`}`;
      }
      const known = typeof step.known === "function" ? await step.known() : step.known;
      return {
        observed: `the screen did not bring the step to its end state, twice: ${attempts.join(" || ")}. ${onward}`,
        result: known === undefined ? "FINDING" : "KNOWN",
        finding: known === undefined ? "stopped flow" : undefined,
        known,
        page: step.page,
      };
    },
    FLOW_CAP_MS,
  );
  return ok;
}
