// TOTP enrolment (04 API-R-03 `POST /me/mfa/enroll`, `POST /me/mfa/confirm`; §16.12; 05 SAR-26;
// 03 REQ-PLT-005; BUILD_SPEC WEB-13). Both routes are commands: `useCommand` sends the Idempotency-Key
// and parses problems. A confirmed enrolment rotates the session (SAR-09) and changes `GET /me` `mfa`,
// so the confirm command invalidates the cached `/me`.
import { type CommandState, useCommand } from "../commands";
import { queryKeys } from "../query-keys";
import type { components } from "../schema";

export type MfaEnrolment = components["schemas"]["MfaEnrolmentOut"];
export type MfaConfirmIn = components["schemas"]["MfaConfirmIn"];
export type RecoveryCodes = components["schemas"]["RecoveryCodesOut"];

export const MFA_ENROL_PATH = "/api/v1/me/mfa/enroll";
export const MFA_CONFIRM_PATH = "/api/v1/me/mfa/confirm";
/** SCREENS_B §12.2: the file "Download codes" saves. */
export const RECOVERY_CODES_FILE = "erev-recovery-codes.txt";

/** Starts or restarts enrolment: a new seed for the authenticator app. */
export function useMfaEnrol(): CommandState<MfaEnrolment> {
  return useCommand<MfaEnrolment>({ method: "POST", path: MFA_ENROL_PATH });
}

/** Confirms the pending factor with its first code; the answer is the one-time recovery codes. */
export function useMfaConfirm(): CommandState<RecoveryCodes> {
  return useCommand<RecoveryCodes>({
    method: "POST",
    path: MFA_CONFIRM_PATH,
    invalidates: [queryKeys.me()],
  });
}

/** SCREENS_B §12.2: the manual key "grouped in fours". */
export function groupedKey(secretBase32: string): string {
  return secretBase32.match(/.{1,4}/g)?.join(" ") ?? secretBase32;
}

/** The text of the downloaded and copied recovery codes: one code per line. */
export function recoveryCodesText(codes: readonly string[]): string {
  return `${codes.join("\n")}\n`;
}
