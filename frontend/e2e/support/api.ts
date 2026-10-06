// API request context for exact-decimal assertions (docs/dev-guide.md DG-E2E-05, DG-E2E-10; PRD
// E2E-02; 04 API-C-02). Requests go through the web origin, so the `vite preview` proxy and the
// api's origin check see what a browser sends. Commands carry the CSRF token of `GET /session`, an
// `Idempotency-Key` and the `Origin` header.
import { randomUUID } from "node:crypto";

import { type APIRequestContext, type APIResponse, expect, request } from "@playwright/test";

export type CommandMethod = "POST" | "PUT" | "PATCH" | "DELETE";

/** The web origin of the e2e stack (DG-RUN-06). */
export function webOrigin(): string {
  return `http://127.0.0.1:${process.env.EREV_E2E_WEB_PORT ?? "5279"}`;
}

/** A request context on the web origin; `storageState` signs it in as a persona (DG-E2E-05). */
export function newApiContext(storageState?: string): Promise<APIRequestContext> {
  return request.newContext({
    baseURL: webOrigin(),
    extraHTTPHeaders: { Origin: webOrigin() },
    ...(storageState === undefined ? {} : { storageState }),
  });
}

/** The JSON body of a response with the expected status; the body text explains a mismatch. */
export async function json<T>(response: APIResponse, status = 200): Promise<T> {
  expect(response.status(), await response.text()).toBe(status);
  return (await response.json()) as T;
}

/** E2E-02: a money or decimal value from the API is asserted as its exact string. */
export function expectDecimal(value: unknown, expected: string): void {
  expect(typeof value, `decimal ${String(value)} is a string`).toBe("string");
  expect(value).toBe(expected);
}

export class ApiClient {
  readonly context: APIRequestContext;

  constructor(context: APIRequestContext) {
    this.context = context;
  }

  get(path: string, params?: Readonly<Record<string, string | number | boolean>>) {
    return this.context.get(path, params === undefined ? {} : { params: { ...params } });
  }

  /** The synchronizer token of the context's session (DG-KRN-AUTH-07). */
  async csrfToken(): Promise<string> {
    const body = await json<{ authenticated: boolean; csrf_token?: string }>(
      await this.context.get("/api/v1/session"),
    );
    if (!body.authenticated || body.csrf_token === undefined) {
      throw new Error("this request context has no signed-in session");
    }
    return body.csrf_token;
  }

  async command(method: CommandMethod, path: string, body?: unknown): Promise<APIResponse> {
    // `Origin` is sent here too, so a persona page's request context passes the api's origin check.
    const headers = {
      "X-CSRF-Token": await this.csrfToken(),
      "Idempotency-Key": randomUUID(),
      Origin: webOrigin(),
    };
    return this.context.fetch(path, {
      method,
      headers,
      ...(body === undefined ? {} : { data: body }),
    });
  }
}
