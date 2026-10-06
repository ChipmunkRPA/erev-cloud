// TOTP codes for persona sign-in (docs/dev-guide.md DG-E2E-05; PRD WLD-U-R2, E2E-08; BUILD_SPEC WEB-12).
// `otpauth` computes the RFC 6238 code (SHA-1, 6 digits, 30-second steps) from `EREV_DEMO_TOTP_SECRET`,
// the base32 secret the demo seed enrols; specs never embed it. The api refuses a code of a step at or
// before the factor's last used step (replay), so each account's used step is recorded under a
// directory lock, and a second code for the same account waits for the next 30-second step.
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { Secret, TOTP } from "otpauth";

import { RESULTS_DIR, withDirectoryLock } from "./screens";

export const TOTP_PERIOD_SECONDS = 30;
export const TOTP_DIGITS = 6;
const PERIOD_MS = TOTP_PERIOD_SECONDS * 1000;
/** Codes are computed a little after a step boundary, so client and server agree on the step. */
const STEP_MARGIN_MS = 300;
export const TOTP_DIR = join(RESULTS_DIR, "auth");
const USED_FILE = join(TOTP_DIR, "totp-steps.json");
const LOCK = join(TOTP_DIR, ".totp.lock");

export const TOTP_SECRET_MESSAGE = "EREV_DEMO_TOTP_SECRET is not set. Copy it from .env.example.";

/** The demo TOTP secret from the environment (E2E-08). */
export function totpSecret(): string {
  const secret = process.env.EREV_DEMO_TOTP_SECRET;
  if (secret === undefined || secret.trim() === "") {
    throw new Error(TOTP_SECRET_MESSAGE);
  }
  return secret.trim();
}

/** The TOTP step of an epoch instant. */
export function stepAt(epochMs: number): number {
  return Math.floor(epochMs / PERIOD_MS);
}

/** The code of one step. */
export function codeAt(secret: string, step: number): string {
  return new TOTP({
    secret: Secret.fromBase32(secret),
    algorithm: "SHA1",
    digits: TOTP_DIGITS,
    period: TOTP_PERIOD_SECONDS,
  }).generate({ timestamp: step * PERIOD_MS });
}

export interface TotpCode {
  readonly code: string;
  readonly step: number;
}

function readUsed(): Record<string, number> {
  if (!existsSync(USED_FILE)) {
    return {};
  }
  return JSON.parse(readFileSync(USED_FILE, "utf8")) as Record<string, number>;
}

function writeUsed(used: Readonly<Record<string, number>>): void {
  const partial = `${USED_FILE}.${String(process.pid)}.partial`;
  writeFileSync(partial, `${JSON.stringify(used, null, 2)}\n`);
  renameSync(partial, USED_FILE);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * A code for `account` from a step later than every step used for it in this run and later than
 * `after` (a step the api refused). When the current step is not later, it waits for the next step.
 */
export async function nextCode(account: string, after?: number): Promise<TotpCode> {
  const secret = totpSecret();
  mkdirSync(TOTP_DIR, { recursive: true });
  for (;;) {
    const now = Date.now();
    const step = stepAt(now);
    const reserved = withDirectoryLock(LOCK, () => {
      const used = readUsed();
      const last = Math.max(
        used[account] ?? Number.NEGATIVE_INFINITY,
        after ?? Number.NEGATIVE_INFINITY,
      );
      if (step <= last || now - step * PERIOD_MS < STEP_MARGIN_MS) {
        return false;
      }
      writeUsed({ ...used, [account]: step });
      return true;
    });
    if (reserved) {
      return { code: codeAt(secret, step), step };
    }
    const wait =
      now - step * PERIOD_MS < STEP_MARGIN_MS ? STEP_MARGIN_MS : (step + 1) * PERIOD_MS - now;
    await sleep(wait + STEP_MARGIN_MS);
  }
}
