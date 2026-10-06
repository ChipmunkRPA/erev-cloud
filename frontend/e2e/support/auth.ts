// Persona sign-in through the UI (docs/dev-guide.md DG-E2E-05; PRD §2.3 WLD-U-01 to WLD-U-11,
// WLD-U-R1, WLD-U-R2, E2E-08; SCREENS_B §12.1). The password step fills SF-22 with the persona's
// `demo.erev` email and `EREV_DEMO_PASSWORD`; a persona with a TOTP factor then reaches
// SF-22:mfa-challenge, where `support/totp.ts` supplies the code and a refused code (replayed by an
// earlier sign-in of the same step) is retried with a later step. A persona with several ACTIVE
// memberships signs in without a workspace and opens WLD-T-01 on SF-23:select; a persona with one
// arrives with it open (D-83). The signed-in storage state is cached under
// `e2e/.results/auth/<persona>.json` for the run. A step the product refuses fails at once and says
// what the product answered: a step that waits for a page that will not come loses its row to the
// test's timeout and names no cause.
import { existsSync, mkdirSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { type APIRequestContext, expect, type Page, type Response } from "@playwright/test";

import { RESULTS_DIR } from "./screens";
import { nextCode } from "./totp";

/** PRD §2.3 personas with a UI sign-in. */
export const PERSONAS = [
  "maya",
  "priya",
  "marcus",
  "elena",
  "robert",
  "hannah",
  "samuel",
  "tomas",
  "grace",
  "nikhil",
  "jordan",
] as const;
export type Persona = (typeof PERSONAS)[number];

export const SIGN_IN_PATH = "/sign-in";
export const MFA_CHALLENGE_PATH = "/sign-in/mfa";
export const SELECT_WORKSPACE_PATH = "/select-workspace";
/** PRD §2.4 WLD-T-01, the workspace of the SCREENS_B §15 sample world; every persona is a member. */
export const PERSONA_WORKSPACE = { code: "avenmoor", name: "Avenmoor Holdings (Demo)" } as const;
export const AUTH_DIR = join(RESULTS_DIR, "auth");
export const PASSWORD_MESSAGE = "EREV_DEMO_PASSWORD is not set. Copy it from .env.example.";
const MAX_CODES = 3;
/** 04 API-R-01: the command of the password step. */
const LOGIN_PATH = "/api/v1/session/login";
/** How long a step waits for the page it expects before it says what the page shows instead. */
const STEP_TIMEOUT_MS = 30_000;
/** How long the body of a refusal is waited for; the status is known without it. */
const BODY_TIMEOUT_MS = 5_000;

export function personaEmail(persona: Persona): string {
  return `${persona}@demo.erev`;
}

/** WLD-U-R1: the demo password from the environment (E2E-08). */
export function demoPassword(): string {
  const password = process.env.EREV_DEMO_PASSWORD;
  if (password === undefined || password === "") {
    throw new Error(PASSWORD_MESSAGE);
  }
  return password;
}

/** DG-E2E-05: the cached storage state of a persona. */
export function storageStatePath(persona: Persona): string {
  return join(AUTH_DIR, `${persona}.json`);
}

/** API-S-Session as the specs read it. */
export interface SessionBody {
  readonly authenticated: boolean;
  readonly user?: { readonly email: string } | null;
  readonly active_tenant?: { readonly id: string; readonly code: string } | null;
  readonly mfa_verified_at?: string | null;
}

export async function sessionOf(request: APIRequestContext): Promise<SessionBody> {
  const response = await request.get("/api/v1/session");
  expect(response.status(), await response.text()).toBe(200);
  return (await response.json()) as SessionBody;
}

function pathOf(page: Page): string {
  return new URL(page.url()).pathname;
}

/** The problem of a refused answer in one line; the status alone when its body does not arrive. */
async function refusalOf(response: Response): Promise<string> {
  const body = await Promise.race([
    response.text().catch(() => ""),
    new Promise<string>((resolve) => {
      setTimeout(() => {
        resolve("");
      }, BODY_TIMEOUT_MS);
    }),
  ]);
  return `${String(response.status())} ${body.replace(/\s+/g, " ").slice(0, 300)}`.trim();
}

/**
 * The SF-22 password step: the page leaves `/sign-in` for the MFA challenge or the app. A refused
 * step fails at once with the API's answer in its message, where it used to wait out the test: two
 * workers that signed one persona in at the same moment got a 409 for one of them, and the row said
 * nothing of it for two minutes. It is not tried a second time: a retry would hide what the product
 * answered.
 */
export async function passwordStep(page: Page, persona: Persona): Promise<void> {
  await page.goto(SIGN_IN_PATH);
  await page.getByRole("textbox", { name: "Email" }).fill(personaEmail(persona));
  await page.getByLabel("Password", { exact: true }).fill(demoPassword());
  const answered = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === LOGIN_PATH && response.request().method() === "POST",
    { timeout: STEP_TIMEOUT_MS },
  );
  await page.getByRole("button", { name: "Sign in" }).click();
  const answer = await answered;
  if (!answer.ok()) {
    throw new Error(
      `SF-22: the password step of ${persona} was refused: ${await refusalOf(answer)}`,
    );
  }
  await page.waitForURL((url) => url.pathname !== SIGN_IN_PATH, { timeout: STEP_TIMEOUT_MS });
}

/** SF-22:mfa-challenge with the persona's TOTP code; a refused code is retried with a later step. */
export async function totpStep(page: Page, persona: Persona): Promise<void> {
  const field = page.getByRole("textbox", { name: "Authentication code" });
  const banner = page.getByTestId("SF-22-banner-error");
  let refused: number | undefined;
  for (let attempt = 0; attempt < MAX_CODES; attempt += 1) {
    const { code, step } = await nextCode(personaEmail(persona), refused);
    await field.fill(code);
    await page.getByRole("button", { name: "Verify" }).click();
    await expect(async () => {
      expect(pathOf(page) !== MFA_CHALLENGE_PATH || (await banner.isVisible())).toBe(true);
    }).toPass({ timeout: 15_000 });
    if (pathOf(page) !== MFA_CHALLENGE_PATH) {
      return;
    }
    refused = step;
  }
  throw new Error(`SF-22:mfa-challenge refused ${String(MAX_CODES)} codes for ${persona}`);
}

/**
 * SF-23:select after sign-in: "Open" on WLD-T-01; the page leaves for the landing route (D-83). A
 * list that does not offer the workspace fails with what the page shows instead — a member whose
 * new role asks for a second factor is not answered the list at all.
 */
export async function workspaceStep(page: Page): Promise<void> {
  const open = page.getByRole("button", { name: `Open ${PERSONA_WORKSPACE.name}` });
  try {
    await open.click({ timeout: STEP_TIMEOUT_MS });
  } catch (error) {
    const shown = await page
      .getByRole("main")
      .innerText({ timeout: BODY_TIMEOUT_MS })
      .catch(() => "");
    throw new Error(
      `SF-23:select does not offer "Open ${PERSONA_WORKSPACE.name}"; the page reads: ${shown.replace(/\s+/g, " ").slice(0, 300)}`,
      { cause: error },
    );
  }
  await page.waitForURL((url) => url.pathname !== SELECT_WORKSPACE_PATH, {
    timeout: STEP_TIMEOUT_MS,
  });
}

/**
 * Signs `persona` in through SF-22, SF-22:mfa-challenge when the persona has a factor, and
 * SF-23:select when the sign-in opened no workspace; the session ends in WLD-T-01.
 */
export async function signInThroughUi(page: Page, persona: Persona): Promise<SessionBody> {
  await passwordStep(page, persona);
  if (pathOf(page) === MFA_CHALLENGE_PATH) {
    await totpStep(page, persona);
  }
  if (pathOf(page) === SELECT_WORKSPACE_PATH) {
    await workspaceStep(page);
  }
  const session = await sessionOf(page.request);
  expect(session.authenticated, `${persona} is signed in`).toBe(true);
  expect(session.user?.email).toBe(personaEmail(persona));
  expect(session.active_tenant?.code, `${persona} works in ${PERSONA_WORKSPACE.name}`).toBe(
    PERSONA_WORKSPACE.code,
  );
  return session;
}

/** Writes a storage state atomically, so a parallel worker never reads a partial file. */
export function writeStorageState(persona: Persona, state: unknown): void {
  mkdirSync(AUTH_DIR, { recursive: true });
  const path = storageStatePath(persona);
  const partial = `${path}.${String(process.pid)}.partial`;
  writeFileSync(partial, `${JSON.stringify(state, null, 2)}\n`);
  renameSync(partial, path);
}

export function hasStorageState(persona: Persona): boolean {
  return existsSync(storageStatePath(persona));
}
