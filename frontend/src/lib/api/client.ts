// API client (docs/dev-guide.md DG-FE-04, DG-FE-05; 04 API-C-02, API-C-05, API-C-15). One request
// pipeline serves the typed openapi-fetch client and the command helper: it adds `X-Request-Id` and,
// on state-changing requests, `X-CSRF-Token` from module memory; it remembers the token that session
// responses carry; a 401 sends the browser to sign-in; and a 403 that says the session owes its
// second factor (03 REQ-PLT-005) tells the session guard to read the session again.
import createClient, { type Middleware } from "openapi-fetch";

import { getCsrfToken, setCsrfToken } from "./csrf";
import { parseProblem, readProblem } from "./problems";
import type { paths } from "./schema";

export const SESSION_PATH = "/api/v1/session";
export const SIGN_IN_PATH = "/sign-in";
const STATE_CHANGING = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/**
 * 04 §15.2, API-C-03: what the API answers a session that still owes its second factor, on every
 * route but the ones that settle the step (REQ-PLT-005).
 */
export const SECOND_FACTOR_SLUG = "mfa-required";

type Navigate = (href: string) => void;
type SessionListener = () => void;

let navigate: Navigate = (href) => {
  window.location.assign(href);
};
let secondFactorOwed: SessionListener | null = null;

/** Replaces the navigation that the 401 redirect uses. */
export function setNavigator(next: Navigate): void {
  navigate = next;
}

/**
 * Registers what happens when the API refuses a call because the session owes its second factor:
 * the session guard reads the session again and routes to the step (app/auth/RequireSession).
 */
export function setSecondFactorListener(next: SessionListener | null): void {
  secondFactorOwed = next;
}

export function prepareRequest(request: Request): Request {
  if (!request.headers.has("X-Request-Id")) {
    request.headers.set("X-Request-Id", crypto.randomUUID());
  }
  const token = getCsrfToken();
  if (token !== null && STATE_CHANGING.has(request.method.toUpperCase())) {
    request.headers.set("X-CSRF-Token", token);
  }
  return request;
}

async function rememberSession(response: Response): Promise<void> {
  if (!(response.headers.get("Content-Type") ?? "").includes("application/json")) {
    return;
  }
  let body: unknown;
  try {
    body = await response.clone().json();
  } catch {
    return;
  }
  if (typeof body !== "object" || body === null) {
    return;
  }
  const fields = body as Record<string, unknown>;
  if (typeof fields.csrf_token === "string") {
    setCsrfToken(fields.csrf_token);
  } else if (fields.authenticated === false) {
    setCsrfToken(null);
  }
}

// SCREENS_B §12.1 and SCREENS SCR-URL-30: `reason=session-expired` only for an ended session, and
// `next` is the same-origin path the user was on. Sign-in itself never redirects to itself.
function redirectToSignIn(expired: boolean): void {
  const { pathname, search } = window.location;
  if (pathname === SIGN_IN_PATH) {
    return;
  }
  const params = new URLSearchParams();
  if (expired) {
    params.set("reason", "session-expired");
  }
  params.set("next", `${pathname}${search}`);
  navigate(`${SIGN_IN_PATH}?${params.toString()}`);
}

export async function inspectResponse(request: Request, response: Response): Promise<void> {
  const { pathname } = new URL(request.url);
  if (response.ok && (pathname === SESSION_PATH || pathname.startsWith(`${SESSION_PATH}/`))) {
    await rememberSession(response);
  }
  if (response.status === 401) {
    setCsrfToken(null);
    const problem = await readProblem(response);
    redirectToSignIn(problem.slug === "session-expired");
  }
  if (response.status === 403 && secondFactorOwed !== null) {
    const problem = await readProblem(response);
    if (problem.slug === SECOND_FACTOR_SLUG) {
      secondFactorOwed();
    }
  }
}

const middleware: Middleware = {
  onRequest({ request }) {
    return prepareRequest(request);
  },
  async onResponse({ request, response }) {
    await inspectResponse(request, response);
    return response;
  },
};

// The generated paths already begin with /api/v1, so the base URL is the page origin (SPEC-Q-196).
// `fetch` is looked up per call so a test's interception applies after this module loads.
export const api = createClient<paths>({
  baseUrl: globalThis.location.origin,
  fetch: (request) => globalThis.fetch(request),
});
api.use(middleware);

export interface SendInit {
  /** A JSON body. */
  readonly body?: unknown;
  /** A multipart body (an upload); the browser writes its Content-Type with the boundary. */
  readonly form?: FormData;
  readonly headers?: Readonly<Record<string, string>>;
}

/**
 * Sends one request through the pipeline; the command helper uses it for untyped command paths.
 *
 * A command's answer is received whole before it is handed on (DG-FE-05; KIT-202-BODY-1). Many
 * callers need only its status or a header — a 202 is adopted by its `Location` — and read no body,
 * and an answer nobody reads stays open in the browser for the life of the page: it never finishes
 * for the developer tools or for a tool that waits for it. The caller still reads the body as before.
 * A read is left to its reader.
 */
export async function send(method: string, path: string, init: SendInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  let body: string | FormData | null = init.form ?? null;
  if (init.body !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.body);
  }
  const request = prepareRequest(
    new Request(new URL(path, globalThis.location.origin), {
      method,
      headers,
      body,
      credentials: "same-origin",
    }),
  );
  const response = await globalThis.fetch(request);
  await inspectResponse(request, response);
  if (method !== "GET" && response.body !== null) {
    // The copy is read to its end, which takes the answer off the network; the answer handed on is
    // untouched. A body that breaks off is the caller's to meet when it reads.
    await response
      .clone()
      .arrayBuffer()
      .catch(() => undefined);
  }
  return response;
}

/** Returns the data of a typed call, or throws its `ApiProblem`. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (error !== undefined || !response.ok) {
    throw parseProblem(error, response);
  }
  return data as T;
}
