// The members of the pass and their browser sessions (release candidate QA; PROGRESS.md D-99 (7)).
// Eleven are the personas of the demo world, signed in through the committed fixture. The twelfth,
// "lena", is made by the pass through the product — invited by tomas for AVM-DE alone — because the
// seed gives every role for all entities (PRD §2.3) and no test has ever signed in a member of named
// entities. `walkSignIn` signs a member in by hand and says what each step showed: the committed
// helper asserts a sign-in, this one describes it, and it walks the enrolment of a factor, which the
// committed helper does not.
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import type {
  Browser,
  BrowserContext,
  BrowserContextOptions,
  Page,
  TestInfo,
} from "@playwright/test";

import {
  demoPassword,
  MFA_CHALLENGE_PATH,
  type Persona,
  PERSONA_WORKSPACE,
  personaEmail,
  PERSONAS,
  SELECT_WORKSPACE_PATH,
  SIGN_IN_PATH,
} from "../auth";
import type { Personas } from "../fixtures";
import { installNetworkGuard, type NetworkRecord } from "../network";
import { codeAt, nextCode, stepAt, TOTP_PERIOD_SECONDS } from "../totp";
import { watchPage } from "./observe";
import { flat, type QaRecord, recordRoot } from "./record";

export const LENA = "lena";
export type Member = Persona | typeof LENA;
export const MEMBERS: readonly Member[] = [...PERSONAS, LENA];
export const MFA_ENROL_PATH = "/mfa/enrol";
const LOGIN_PATH = "/api/v1/session/login";
const STEP_MS = 30_000;
const PERIOD_MS = TOTP_PERIOD_SECONDS * 1000;
/** A code is computed a little inside its step, so that browser and server agree on the step. */
const STEP_MARGIN_MS = 400;

export function isPersona(member: Member): member is Persona {
  return member !== LENA;
}

/** What the pass keeps between its tests: a test that fails ends its worker, and the next one reads it. */
export interface LenaState {
  readonly email: string;
  readonly name: string;
  readonly password: string;
  /** The key of the factor she enrolled, when a role of hers asked for one. */
  readonly secret: string | null;
  /** The last TOTP step a code of hers was used for. */
  readonly lastStep: number;
  readonly membershipId: string | null;
  /** The invitation was accepted: she has a password and a session was opened once. */
  readonly accepted: boolean;
}

export interface QaState {
  /**
   * The world the record is of: the id of the Avenmoor workspace, which every seed makes anew. A
   * record is of one world — the member the pass made and the contract it booked are that world's.
   */
  readonly world?: string;
  readonly lena?: LenaState;
  /** The contract of flow A. */
  readonly contract?: { readonly id: string; readonly externalId: string };
}

function stateFile(): string {
  return join(recordRoot(), "state.json");
}

export function readState(): QaState {
  const file = stateFile();
  return existsSync(file) ? (JSON.parse(readFileSync(file, "utf8")) as QaState) : {};
}

export function patchState(patch: Partial<QaState>): QaState {
  mkdirSync(recordRoot(), { recursive: true });
  const next = { ...readState(), ...patch };
  const partial = `${stateFile()}.${String(process.pid)}.partial`;
  writeFileSync(partial, `${JSON.stringify(next, null, 2)}\n`);
  renameSync(partial, stateFile());
  return next;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** A code of `secret` from a step later than `after`; it waits for that step when it must. */
export async function laterCode(
  secret: string,
  after: number,
): Promise<{ readonly code: string; readonly step: number }> {
  for (;;) {
    const now = Date.now();
    const step = stepAt(now);
    if (step > after && now - step * PERIOD_MS >= STEP_MARGIN_MS) {
      return { code: codeAt(secret, step), step };
    }
    await sleep(step > after ? STEP_MARGIN_MS : (step + 1) * PERIOD_MS - now + STEP_MARGIN_MS);
  }
}

/**
 * Waits until the window's address satisfies `where`. `page.waitForURL` follows navigations, and a
 * navigation the application itself replaces — the redirect behind a sign-out, a landing rule — ends
 * it with net::ERR_ABORTED although the window arrives. What the pass asks for is the address, so
 * the address is read until it is there.
 */
export async function arrive(
  page: Page,
  where: (url: URL) => boolean,
  timeoutMs = 30_000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const url = new URL(page.url());
    if (where(url)) {
      return;
    }
    if (Date.now() > deadline) {
      throw new Error(
        `the window stayed on ${url.pathname} for ${String(timeoutMs / 1000)} s: the address the step leads to was not reached`,
      );
    }
    await sleep(200);
  }
}

export interface Credentials {
  readonly email: string;
  readonly password: string;
  /** The key of the member's own factor; a persona's is the demo secret of the environment. */
  readonly secret: string | null;
  /** The last step used with `secret`. */
  readonly lastStep: number;
}

export interface SessionRead {
  readonly authenticated: boolean;
  readonly user?: { readonly email: string; readonly display_name?: string } | null;
  readonly active_tenant?: { readonly id: string; readonly code: string } | null;
  readonly mfa_required?: boolean;
  readonly mfa_enrolment_required?: boolean;
  readonly mfa_verified_at?: string | null;
}

export interface Trail {
  /** What each step of the sign-in showed, in order. */
  readonly steps: readonly string[];
  /** SF-22:mfa-challenge asked for a code. */
  readonly challenged: boolean;
  /** The key of a factor enrolled on SF-22:mfa-enrol, when the sign-in led there. */
  readonly enrolled: string | null;
  /** The workspaces SF-23:select offered, when the sign-in led there. */
  readonly workspaces: number | null;
  /** Pathname and search of the page the sign-in ended on. */
  readonly landed: string;
  readonly session: SessionRead;
  readonly lastStep: number;
}

function pathOf(page: Page): string {
  return new URL(page.url()).pathname;
}

async function mainText(page: Page): Promise<string> {
  return flat(
    await page
      .locator("body")
      .innerText({ timeout: 5_000 })
      .catch(() => ""),
    300,
  );
}

export async function sessionRead(page: Page): Promise<SessionRead> {
  const answer = await page.request.get("/api/v1/session");
  return (await answer.json()) as SessionRead;
}

/**
 * Signs a member in through SF-22 and whatever follows it — the challenge of a factor, the enrolment
 * of one, the choice of the workspace — and says what each step showed. It throws, naming what the
 * page shows, when a step leads nowhere: the caller's row then says where the sign-in stopped.
 */
export async function walkSignIn(page: Page, who: Credentials, persona?: Persona): Promise<Trail> {
  const steps: string[] = [];
  let challenged = false;
  let enrolled: string | null = null;
  let workspaces: number | null = null;
  let secret = who.secret;
  let lastStep = who.lastStep;

  await page.goto(SIGN_IN_PATH);
  await page.getByRole("textbox", { name: "Email" }).fill(who.email);
  await page.getByLabel("Password", { exact: true }).fill(who.password);
  const answered = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === LOGIN_PATH && response.request().method() === "POST",
    { timeout: STEP_MS },
  );
  await page.getByRole("button", { name: "Sign in" }).click();
  const answer = await answered;
  if (!answer.ok()) {
    throw new Error(
      `SF-22: the password step was refused: ${String(answer.status())} ${flat(await answer.text().catch(() => ""), 200)}; the page reads: ${await mainText(page)}`,
    );
  }
  await arrive(page, (url) => url.pathname !== SIGN_IN_PATH, STEP_MS);
  steps.push("SF-22: password accepted");

  for (let turn = 0; turn < 8; turn += 1) {
    const path = pathOf(page);
    if (path === MFA_CHALLENGE_PATH) {
      challenged = true;
      const field = page.getByRole("textbox", { name: "Authentication code" });
      await field.waitFor({ timeout: STEP_MS });
      const banner = page.getByTestId("SF-22-banner-error");
      let passed = false;
      let refused: number | undefined;
      for (let attempt = 0; attempt < 3 && !passed; attempt += 1) {
        let code: string;
        if (secret === null) {
          if (persona === undefined) {
            throw new Error(
              "SF-22:mfa-challenge asks for a code of a factor the pass does not know",
            );
          }
          const next = await nextCode(personaEmail(persona), refused);
          code = next.code;
          refused = next.step;
        } else {
          const next = await laterCode(secret, lastStep);
          code = next.code;
          lastStep = next.step;
        }
        await field.fill(code);
        await page.getByRole("button", { name: "Verify" }).click();
        await Promise.race([
          page.waitForURL((url) => url.pathname !== MFA_CHALLENGE_PATH, { timeout: STEP_MS }),
          banner.waitFor({ state: "visible", timeout: STEP_MS }),
        ]).catch(() => undefined);
        passed = pathOf(page) !== MFA_CHALLENGE_PATH;
      }
      if (!passed) {
        throw new Error(
          `SF-22:mfa-challenge refused three codes; the page reads: ${await mainText(page)}`,
        );
      }
      steps.push("SF-22:mfa-challenge: asked for a code and took it");
      continue;
    }
    if (path === MFA_ENROL_PATH) {
      const key = page.getByTestId("SF-22-mfa-key");
      await key.waitFor({ timeout: STEP_MS });
      const banner = flat(
        await page
          .getByRole("main")
          .innerText({ timeout: 5_000 })
          .catch(() => ""),
        200,
      );
      const shown = (await key.innerText()).replace(/\s+/g, "");
      await page.getByRole("button", { name: "Next" }).click();
      const codes = page.getByTestId("SF-22-mfa-recovery-codes");
      const wrong = page.getByText(/did not match/);
      for (let attempt = 0; attempt < 3; attempt += 1) {
        const next = await laterCode(shown, lastStep);
        lastStep = next.step;
        await page.getByRole("textbox", { name: "Authentication code" }).fill(next.code);
        await page.getByRole("button", { name: "Verify code" }).click();
        await codes.or(wrong).first().waitFor({ state: "visible", timeout: STEP_MS });
        if (await codes.isVisible()) {
          break;
        }
      }
      if (!(await codes.isVisible())) {
        throw new Error(
          `SF-22:mfa-enrol refused three codes; the page reads: ${await mainText(page)}`,
        );
      }
      await page.getByRole("checkbox", { name: "I have stored these recovery codes" }).check();
      await page.getByRole("button", { name: "Continue" }).click();
      await arrive(page, (url) => url.pathname !== MFA_ENROL_PATH, STEP_MS);
      secret = shown;
      enrolled = shown;
      steps.push(`SF-22:mfa-enrol: a factor was asked for and enrolled ("${banner}")`);
      continue;
    }
    if (path === SELECT_WORKSPACE_PATH) {
      const open = page.getByRole("button", { name: `Open ${PERSONA_WORKSPACE.name}` });
      const offered = await open
        .waitFor({ state: "visible", timeout: STEP_MS })
        .then(() => true)
        .catch(() => false);
      if (pathOf(page) !== SELECT_WORKSPACE_PATH) {
        continue;
      }
      if (!offered) {
        // A member who must enrol is sent on by the application's gate, not by this page.
        const session = await sessionRead(page);
        if (session.mfa_enrolment_required === true) {
          await page.goto(MFA_ENROL_PATH);
          continue;
        }
        throw new Error(
          `SF-23:select does not offer "Open ${PERSONA_WORKSPACE.name}"; the page reads: ${await mainText(page)}`,
        );
      }
      workspaces = await page.getByRole("button", { name: /^Open / }).count();
      await open.click();
      await arrive(page, (url) => url.pathname !== SELECT_WORKSPACE_PATH, STEP_MS);
      steps.push(`SF-23:select: ${String(workspaces)} workspaces offered, Avenmoor opened`);
      continue;
    }
    break;
  }
  // The landing route redirects from "/" (RT-07): the sign-in has ended where that settles.
  await page.waitForURL((url) => url.pathname !== "/", { timeout: STEP_MS }).catch(() => undefined);
  const session = await sessionRead(page);
  const url = new URL(page.url());
  steps.push(`landed on ${url.pathname}`);
  return {
    steps,
    challenged,
    enrolled,
    workspaces,
    landed: `${url.pathname}${url.search}`,
    session,
    lastStep,
  };
}

/** Signs out through the user menu; the page ends on SF-22. */
export async function signOut(page: Page): Promise<void> {
  await page.getByRole("button", { name: /^User menu for / }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await arrive(page, (url) => url.pathname === SIGN_IN_PATH, STEP_MS);
  // The application replaces its document on the way out: SF-22's own form says it has arrived.
  await page
    .getByRole("textbox", { name: "Email" })
    .waitFor({ state: "visible", timeout: STEP_MS })
    .catch(() => undefined);
}

function contextOptions(testInfo: TestInfo): BrowserContextOptions {
  const use = testInfo.project.use;
  return {
    ...(use.baseURL === undefined ? {} : { baseURL: use.baseURL }),
    ...(use.locale === undefined ? {} : { locale: use.locale }),
    ...(use.timezoneId === undefined ? {} : { timezoneId: use.timezoneId }),
    ...(use.viewport === undefined ? {} : { viewport: use.viewport }),
  };
}

function lenaStorage(): string {
  return join(recordRoot(), "auth", "lena.json");
}

/** The sessions of one test: a page per member, opened once and closed with the test. */
export class Sessions {
  private readonly pages = new Map<Member, Page>();
  private readonly opened: {
    readonly who: string;
    readonly context: BrowserContext;
    readonly record: NetworkRecord;
  }[] = [];

  constructor(
    private readonly browser: Browser,
    private readonly personas: Personas,
    private readonly record: QaRecord,
    private readonly testInfo: TestInfo,
  ) {}

  /** A page of a new browser context with no session, under the DG-E2E-08 network guard. */
  async blank(who: string): Promise<Page> {
    const context = await this.browser.newContext(contextOptions(this.testInfo));
    const record = await installNetworkGuard(context);
    this.opened.push({ who, context, record });
    const page = await context.newPage();
    page.setDefaultTimeout(20_000);
    watchPage(page);
    return page;
  }

  /** The member's page: a persona through the committed fixture, lena through her own sign-in. */
  async page(member: Member): Promise<Page> {
    const known = this.pages.get(member);
    if (known !== undefined && !known.isClosed()) {
      return known;
    }
    const page = isPersona(member) ? await this.personas.page(member) : await this.lena();
    page.setDefaultTimeout(20_000);
    watchPage(page);
    this.pages.set(member, page);
    return page;
  }

  private async lena(): Promise<Page> {
    const lena = readState().lena;
    if (lena === undefined || !lena.accepted) {
      throw new Error(
        "the member for AVM-DE alone has not been made yet: section G did not finish",
      );
    }
    if (existsSync(lenaStorage())) {
      const context = await this.browser.newContext({
        ...contextOptions(this.testInfo),
        storageState: lenaStorage(),
      });
      const session = (await (await context.request.get("/api/v1/session")).json()) as SessionRead;
      if (session.authenticated && session.user?.email === lena.email) {
        const record = await installNetworkGuard(context);
        this.opened.push({ who: LENA, context, record });
        return context.newPage();
      }
      await context.close();
    }
    const page = await this.blank(LENA);
    const trail = await walkSignIn(page, lena);
    patchState({
      lena: { ...lena, secret: trail.enrolled ?? lena.secret, lastStep: trail.lastStep },
    });
    await this.keep(page);
    return page;
  }

  /** Keeps lena's session for the next test. */
  async keep(page: Page): Promise<void> {
    mkdirSync(join(recordRoot(), "auth"), { recursive: true });
    await page.context().storageState({ path: lenaStorage() });
  }

  /** Closes what the test opened; a request to another host or a CSP violation is a parked line. */
  async close(): Promise<void> {
    for (const { who, context, record } of this.opened) {
      await context.close().catch(() => undefined);
      for (const request of record.requests) {
        this.record.parked(
          who,
          request.url,
          `a request to a non-loopback host was blocked (REQ-SEC-008): ${request.method} ${request.resourceType}`,
        );
      }
      for (const violation of record.cspViolations) {
        this.record.parked(
          who,
          violation.documentURI,
          `Content-Security-Policy violation (SAR-20): ${violation.violatedDirective} ${violation.blockedURI}`,
        );
      }
    }
  }
}

/** The credentials of a persona: the demo password; the code comes from the demo secret. */
export function personaCredentials(persona: Persona): Credentials {
  return { email: personaEmail(persona), password: demoPassword(), secret: null, lastStep: 0 };
}
