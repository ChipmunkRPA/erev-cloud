// @vitest-environment jsdom
// DG-FE-04 (docs/dev-guide.md §8.2; 04 API-C-02, API-C-05, API-C-15): the client middleware adds the
// synchronizer token and request id, parses problems and sends an ended session back to sign-in.
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { api, send, setNavigator, unwrap } from "./client";
import { getCsrfToken, setCsrfToken } from "./csrf";
import { ApiProblem } from "./problems";

installMswServer();

afterEach(() => {
  setCsrfToken(null);
  window.history.replaceState({}, "", "/");
});

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const CSRF = "csrf-4f7d1c9b2e8a";
const DECIDE = "/api/v1/approvals/1c2b3a4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d/decide";

function captureHeaders(method: "get" | "post", path: string, seen: Headers[]) {
  return http[method](apiUrl(path), ({ request }) => {
    seen.push(request.headers);
    return HttpResponse.json({});
  });
}

describe("DG-FE-04 client middleware", () => {
  it("sends X-CSRF-Token from module memory and X-Request-Id on state-changing requests", async () => {
    const posts: Headers[] = [];
    const gets: Headers[] = [];
    server.use(
      http.get(apiUrl("/api/v1/session"), () =>
        HttpResponse.json({ authenticated: true, csrf_token: CSRF }),
      ),
      captureHeaders("post", DECIDE, posts),
      captureHeaders("get", "/api/v1/me", gets),
    );

    await api.GET("/api/v1/session");
    expect(getCsrfToken()).toBe(CSRF);

    await send("POST", DECIDE, { body: { decision: "APPROVE" } });
    await send("GET", "/api/v1/me");

    expect(posts[0]?.get("X-CSRF-Token")).toBe(CSRF);
    expect(posts[0]?.get("X-Request-Id")).toMatch(UUID);
    expect(gets[0]?.get("X-Request-Id")).toMatch(UUID);
    expect(gets[0]?.get("X-CSRF-Token")).toBeNull();
  });

  it("never stores the token in localStorage or sessionStorage", async () => {
    server.use(
      http.post(apiUrl("/api/v1/session/login"), () =>
        HttpResponse.json({ authenticated: true, csrf_token: CSRF, mfa_required: false }),
      ),
    );

    await send("POST", "/api/v1/session/login", { body: { email: "ana@demo.erev" } });

    expect(getCsrfToken()).toBe(CSRF);
    for (const storage of [window.localStorage, window.sessionStorage]) {
      const values = Array.from({ length: storage.length }, (_, index) => {
        const key = storage.key(index);
        return key === null ? "" : `${key}=${storage.getItem(key) ?? ""}`;
      });
      expect(values.some((value) => value.includes(CSRF))).toBe(false);
    }
  });

  it("forgets the token when the session reports no sign-in", async () => {
    setCsrfToken(CSRF);
    server.use(
      http.get(apiUrl("/api/v1/session"), () => HttpResponse.json({ authenticated: false })),
    );

    await api.GET("/api/v1/session");

    expect(getCsrfToken()).toBeNull();
  });

  it("parses an application/problem+json body into ApiProblem", async () => {
    server.use(
      http.get(apiUrl("/api/v1/me"), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          detail: "1 field needs attention.",
          instance: "urn:erev:request:7a1d3c5e-9b2f-4e6a-8c4d-1f3e5a7b9c2d",
          errors: [
            {
              field: "Idempotency-Key",
              sheet: null,
              row: null,
              rule_id: "API-C-04",
              message: "Send an Idempotency-Key header with every command.",
            },
          ],
        }),
      ),
    );

    const error: unknown = await unwrap(api.GET("/api/v1/me")).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiProblem);
    const problem = error as ApiProblem;
    expect(problem.slug).toBe("validation-failed");
    expect(problem.type).toBe("https://erev.dev/problems/validation-failed");
    expect(problem.title).toBe("Check the highlighted fields");
    expect(problem.status).toBe(422);
    expect(problem.detail).toBe("1 field needs attention.");
    expect(problem.requestId).toBe("7a1d3c5e-9b2f-4e6a-8c4d-1f3e5a7b9c2d");
    expect(problem.errors).toEqual([
      {
        field: "Idempotency-Key",
        sheet: null,
        row: null,
        rule_id: "API-C-04",
        message: "Send an Idempotency-Key header with every command.",
      },
    ]);
  });

  it("gives an unhandled error no slug", async () => {
    server.use(
      http.get(apiUrl("/api/v1/me"), () => problemResponse(null, 500, "Internal Server Error")),
    );

    const error: unknown = await unwrap(api.GET("/api/v1/me")).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiProblem);
    expect((error as ApiProblem).slug).toBeNull();
    expect((error as ApiProblem).status).toBe(500);
  });

  it("navigates a 401 session-expired to sign-in with the reason and the current path", async () => {
    const navigate = vi.fn();
    setNavigator(navigate);
    setCsrfToken(CSRF);
    window.history.replaceState({}, "", "/contracts?entity=AVM-US");
    server.use(
      http.get(apiUrl("/api/v1/me"), () =>
        problemResponse("session-expired", 401, "Session ended"),
      ),
    );

    await api.GET("/api/v1/me");

    expect(navigate).toHaveBeenCalledWith(
      "/sign-in?reason=session-expired&next=%2Fcontracts%3Fentity%3DAVM-US",
    );
    expect(getCsrfToken()).toBeNull();
  });

  it("navigates another 401 to sign-in without a reason, and never from sign-in itself", async () => {
    const navigate = vi.fn();
    setNavigator(navigate);
    window.history.replaceState({}, "", "/approvals");
    server.use(
      http.get(apiUrl("/api/v1/me"), () =>
        problemResponse("unauthenticated", 401, "Sign-in required"),
      ),
    );

    await api.GET("/api/v1/me");
    expect(navigate).toHaveBeenCalledWith("/sign-in?next=%2Fapprovals");

    navigate.mockClear();
    window.history.replaceState({}, "", "/sign-in");
    await api.GET("/api/v1/me");
    expect(navigate).not.toHaveBeenCalled();
  });
});

// KIT-202-BODY-1 (docs/dev-guide.md DG-FE-05): a command's answer is received whole before `send`
// hands it on. A caller that needs only the status or a header — a 202 adopted by its `Location` —
// read no body, and the browser kept the response open for the life of the page: 0 of 32 such
// answers finished in a real browser, and a tool that waits for the response to finish waited for ever.
describe("a command's answer is received whole", () => {
  const encoder = new TextEncoder();

  /** An answer whose body arrives in three pieces, none of them before somebody reads. */
  function answer(status: number): {
    readonly response: Response;
    readonly arrived: () => boolean;
  } {
    const pieces = ['{"id":"job-1",', '"state":', '"QUEUED"}'].map((piece) =>
      encoder.encode(piece),
    );
    let sent = 0;
    let whole = false;
    const body = new ReadableStream<Uint8Array>(
      {
        pull(controller) {
          const piece = pieces[sent];
          if (piece === undefined) {
            whole = true;
            controller.close();
            return;
          }
          sent += 1;
          controller.enqueue(piece);
        },
      },
      { highWaterMark: 0 },
    );
    return {
      response: new Response(body, {
        status,
        headers: { "Content-Type": "application/json", Location: "/api/v1/jobs/job-1" },
      }),
      arrived: () => whole,
    };
  }

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("a 202 nobody reads has arrived whole when send returns, and can still be read", async () => {
    const accepted = answer(202);
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(accepted.response);

    const response = await send("POST", "/api/v1/audit-events/verify");

    expect(response.status).toBe(202);
    expect(response.headers.get("Location")).toBe("/api/v1/jobs/job-1");
    expect(accepted.arrived()).toBe(true);
    // The caller that wants the job reads it as before.
    expect(response.bodyUsed).toBe(false);
    expect(await response.json()).toEqual({ id: "job-1", state: "QUEUED" });
  });

  it("a read is left to its reader: nothing is taken before the caller asks", async () => {
    const listed = answer(200);
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(listed.response);

    const response = await send("GET", "/api/v1/jobs/job-1");

    expect(listed.arrived()).toBe(false);
    expect(await response.json()).toEqual({ id: "job-1", state: "QUEUED" });
    expect(listed.arrived()).toBe(true);
  });
});
