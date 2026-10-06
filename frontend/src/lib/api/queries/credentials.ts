// Invitation lookup and acceptance (04 API-R-01 `POST /session/invitations/lookup`,
// `POST /session/accept-invitation`; §16.12 rev 1.38; T-PLT-07; 05 SAR-06, SAR-09; BUILD_SPEC WEB-13). Both
// routes need no session and are not commands (no Idempotency-Key), so they go through `send` as sign-in
// does; the accepted session answer sets the CSRF token through the client pipeline. Tokens travel only
// in request bodies: the pages read them from the URL fragment, which the browser never sends to the
// server (SCREENS RT-05, RT-112). `tokenFromFragment` serves the password-reset confirm page as well.
import { send } from "../client";
import { type ApiProblem, readProblem } from "../problems";
import type { components } from "../schema";

export type InvitationLookup = components["schemas"]["InvitationLookupOut"];
export type AcceptInvitationIn = components["schemas"]["SessionAcceptInvitationIn"];
export type SessionLoginOut = components["schemas"]["SessionLoginOut"];

export const INVITATION_LOOKUP_PATH = "/api/v1/session/invitations/lookup";
export const ACCEPT_INVITATION_PATH = "/api/v1/session/accept-invitation";

/** 04 §15.2: the slug of a refused password (PRD ERR-21). */
export const PASSWORD_POLICY_SLUG = "password-policy";

/** The `token` of a `#token=<token>` fragment; null when absent or empty. */
export function tokenFromFragment(hash: string): string | null {
  const fragment = hash.startsWith("#") ? hash.slice(1) : hash;
  const token = new URLSearchParams(fragment).get("token");
  return token === null || token === "" ? null : token;
}

/** The ERR-21 copy of a 422 `password-policy` problem, else null. */
export function passwordPolicyMessage(problem: ApiProblem): string | null {
  if (problem.status !== 422 || problem.slug !== PASSWORD_POLICY_SLUG) {
    return null;
  }
  return problem.errors[0]?.message ?? problem.detail ?? problem.title;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await send("POST", path, { body });
  if (!response.ok) {
    throw await readProblem(response);
  }
  return (await response.json()) as T;
}

/** The workspace, inviter, email and password state of an open invitation; a 404 is thrown as `ApiProblem`. */
export function lookupInvitation(token: string): Promise<InvitationLookup> {
  return post<InvitationLookup>(INVITATION_LOOKUP_PATH, { token });
}

/** Accepts the invitation; the answer is the new session with the workspace active. */
export function acceptInvitation(body: AcceptInvitationIn): Promise<SessionLoginOut> {
  return post<SessionLoginOut>(ACCEPT_INVITATION_PATH, body);
}
