// @vitest-environment jsdom
// DG-FE-05 (docs/dev-guide.md §8.2; PRD BR-PLT-03; 04 API-C-04, API-C-08, API-C-12): one
// Idempotency-Key per user intent, no automatic retry, 412 handling, field errors and job polling.
import { notifyManager, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "../../app/providers";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import {
  type CommandOptions,
  type CommandOutcome,
  createCommandKeys,
  onCommandSucceeded,
  useCommand,
} from "./commands";
import { JOB_POLL_INTERVAL_MS } from "./jobs";
import { type QueryKey, queryKeys } from "./query-keys";

installMswServer();

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  notifyManager.setScheduler((callback) => {
    setTimeout(callback, 0);
  });
});

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const PATH = "/api/v1/contracts/5b7e0c9a-1d2f-4c3b-9a8e-6f5d4c3b2a10/activate";
const JOB_ID = "8d4f2e1c-3b5a-4c7d-9e8f-0a1b2c3d4e5f";

function setup(options: CommandOptions) {
  const queryClient = createQueryClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  const { result } = renderHook(() => useCommand(options), { wrapper: Wrapper });
  const submit = (body?: unknown, ifMatch?: string) =>
    act(() => result.current.submit(body, ifMatch === undefined ? {} : { ifMatch }));
  return { queryClient, result, submit };
}

function jobBody(state: string) {
  return {
    id: JOB_ID,
    kind: "RETENTION_SWEEP",
    state,
    progress: { done: state === "SUCCEEDED" ? 3 : 1, total: 3 },
    result: null,
    problem: null,
    created_by: { kind: "USER", id: null, display_name: "Ana" },
    created_at: "2026-09-13T09:00:00Z",
    started_at: null,
    finished_at: null,
  };
}

// Lets MSW and TanStack Query settle without moving the fake clock.
async function settle(): Promise<void> {
  for (let turn = 0; turn < 10; turn += 1) {
    await act(async () => {
      await new Promise((resolve) => setImmediate(resolve));
      await vi.advanceTimersByTimeAsync(0);
    });
  }
}

async function advance(milliseconds: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(milliseconds);
  });
  await settle();
}

describe("DG-FE-05 useCommand", () => {
  it("sends a UUID Idempotency-Key once per intent and reuses it when the intent is retried", async () => {
    const keys: (string | null)[] = [];
    const statuses = [500, 200, 200, 200];
    server.use(
      http.post(apiUrl(PATH), ({ request }) => {
        keys.push(request.headers.get("Idempotency-Key"));
        return statuses[keys.length - 1] === 500
          ? problemResponse(null, 500, "Internal Server Error")
          : HttpResponse.json({ id: "5b7e0c9a-1d2f-4c3b-9a8e-6f5d4c3b2a10" });
      }),
    );
    const { submit } = setup({ method: "POST", path: PATH });

    expect((await submit({ reason: "Signed order" })).kind).toBe("failed");
    expect((await submit({ reason: "Signed order" })).kind).toBe("succeeded");
    await submit({ reason: "Signed order" });
    await submit({ reason: "Countersigned order" });

    expect(keys).toHaveLength(4);
    for (const key of keys) {
      expect(key).toMatch(UUID);
    }
    expect(keys[1]).toBe(keys[0]);
    expect(keys[2]).not.toBe(keys[1]);
    expect(keys[3]).not.toBe(keys[2]);
  });

  // The API keeps every problem below 500 as the first response of its key, except 401, 403, 412, 428,
  // 429 and 409 idempotency-in-progress, and replays it (DG-KRN-IDEM-03). A second press with the same
  // key could never be decided, so a kept answer ends the intent (supervisor rulings R-97 (6) and
  // R-102 (e); PRD ERR-52).
  it.each([
    [400, "bad-request", "Bad request"],
    [404, "not-found", "Not found"],
    [409, "lock-conflict", "Another change was in progress"],
    [410, "gone", "Gone"],
    [422, "validation-failed", "Check the highlighted fields"],
  ] as const)(
    "an answered %i the API keeps ends the intent: the next submission of the same body carries a new key",
    async (status, slug, title) => {
      const keys: (string | null)[] = [];
      server.use(
        http.post(apiUrl(PATH), ({ request }) => {
          keys.push(request.headers.get("Idempotency-Key"));
          return keys.length === 1
            ? problemResponse(slug, status, title)
            : HttpResponse.json({ id: "5b7e0c9a-1d2f-4c3b-9a8e-6f5d4c3b2a10" });
        }),
      );
      const { result, submit } = setup({ method: "POST", path: PATH });

      expect((await submit({ reason: "Signed order" })).kind).toBe("failed");
      expect(result.current.problem?.slug).toBe(slug);
      expect((await submit({ reason: "Signed order" })).kind).toBe("succeeded");

      expect(keys).toHaveLength(2);
      expect(keys[0]).toMatch(UUID);
      expect(keys[1]).toMatch(UUID);
      expect(keys[1]).not.toBe(keys[0]);
    },
  );

  it("an answer the API does not keep leaves the intent open: a lost response, 5xx, 401, 403, 412, 428 and 429 resend the key", async () => {
    const keys: (string | null)[] = [];
    const answers = [
      () => HttpResponse.error(),
      () => problemResponse(null, 503, "Service Unavailable"),
      () => problemResponse("internal-error", 500, "Something went wrong"),
      () => problemResponse("unauthenticated", 401, "Sign in again"),
      () => problemResponse("mfa-step-up-required", 403, "Confirm with your authenticator"),
      () => problemResponse("precondition-failed", 412, "The record changed"),
      () => problemResponse("precondition-required", 428, "Reload the record"),
      () => problemResponse("rate-limited", 429, "Too many requests"),
      () => HttpResponse.json({}),
    ];
    server.use(
      http.post(apiUrl(PATH), ({ request }) => {
        keys.push(request.headers.get("Idempotency-Key"));
        return answers[keys.length - 1]?.() ?? HttpResponse.json({});
      }),
    );
    const { submit } = setup({ method: "POST", path: PATH });

    expect((await submit({ reason: "Signed order" })).kind).toBe("network-error");
    for (let refusal = 0; refusal < 7; refusal += 1) {
      expect((await submit({ reason: "Signed order" })).kind).toBe("failed");
    }
    expect((await submit({ reason: "Signed order" })).kind).toBe("succeeded");

    expect(keys).toHaveLength(9);
    expect(new Set(keys).size).toBe(1);
  });

  it("409 idempotency-in-progress keeps the key: the first attempt is still running under it", async () => {
    const keys: (string | null)[] = [];
    server.use(
      http.post(apiUrl(PATH), ({ request }) => {
        keys.push(request.headers.get("Idempotency-Key"));
        return keys.length === 1
          ? problemResponse("idempotency-in-progress", 409, "Request still in progress")
          : HttpResponse.json({});
      }),
    );
    const { submit } = setup({ method: "POST", path: PATH });

    expect((await submit({ reason: "Signed order" })).kind).toBe("failed");
    expect((await submit({ reason: "Signed order" })).kind).toBe("succeeded");

    expect(keys[1]).toBe(keys[0]);
  });

  it("starts a new intent with a new key after a changed body or a reset", async () => {
    const keys: (string | null)[] = [];
    server.use(
      http.post(apiUrl(PATH), ({ request }) => {
        keys.push(request.headers.get("Idempotency-Key"));
        return problemResponse(null, 500, "Internal Server Error");
      }),
    );
    const { result, submit } = setup({ method: "POST", path: PATH });

    await submit({ reason: "A" });
    await submit({ reason: "B" });
    act(() => {
      result.current.reset();
    });
    await submit({ reason: "B" });

    expect(new Set(keys).size).toBe(3);
  });

  it("sends If-Match when given", async () => {
    const versions: (string | null)[] = [];
    server.use(
      http.post(apiUrl(PATH), ({ request }) => {
        versions.push(request.headers.get("If-Match"));
        return HttpResponse.json({});
      }),
    );

    await setup({ method: "POST", path: PATH, ifMatch: '"s7"' }).submit({});
    await setup({ method: "POST", path: PATH, ifMatch: '"s7"' }).submit({}, '"s8"');
    await setup({ method: "POST", path: PATH }).submit({});

    expect(versions).toEqual(['"s7"', '"s8"', null]);
  });

  it("does not retry a 500", async () => {
    let calls = 0;
    server.use(
      http.post(apiUrl(PATH), () => {
        calls += 1;
        return problemResponse(null, 500, "Internal Server Error");
      }),
    );
    const { result, submit } = setup({ method: "POST", path: PATH });

    const outcome = await submit({});

    expect(calls).toBe(1);
    expect(outcome.kind).toBe("failed");
    expect(result.current.problem?.status).toBe(500);
    expect(result.current.pending).toBe(false);
  });

  it("invalidates the listed keys on 412 and exposes the record-changed banner", async () => {
    server.use(
      http.post(apiUrl(PATH), () => problemResponse("precondition-failed", 412, "Record changed")),
    );
    const { queryClient, result, submit } = setup({
      method: "POST",
      path: PATH,
      ifMatch: '"s3"',
      invalidates: [queryKeys.me()],
    });
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");

    await submit({});

    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["me", "session", {}] });
    expect(result.current.banner).toBe("This record changed. Reload to see the latest version.");
  });

  it("maps problem errors onto form field names", async () => {
    server.use(
      http.post(apiUrl(PATH), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            { field: "amount", sheet: null, row: null, rule_id: null, message: "Enter an amount." },
            { field: "amount", sheet: null, row: null, rule_id: null, message: "Second message." },
            {
              field: "effective_date",
              sheet: null,
              row: null,
              rule_id: null,
              message: "Enter a date.",
            },
          ],
        }),
      ),
    );
    const { result, submit } = setup({ method: "POST", path: PATH });

    await submit({ amount: "12.3" });

    expect(result.current.fieldErrors).toEqual({
      amount: "Enter an amount.",
      effective_date: "Enter a date.",
    });
    expect(result.current.banner).toBeNull();
  });

  it("starts useJob on 202 and polls every 2,000 ms until SUCCEEDED", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    // A zero-delay timeout created while the fake clock ticks is scheduled 1 ms later, so query
    // notifications go through microtasks here; the polling interval stays on the fake clock.
    notifyManager.setScheduler(queueMicrotask);
    const states = ["RUNNING", "RUNNING", "SUCCEEDED"];
    let polls = 0;
    server.use(
      http.post(apiUrl(PATH), () =>
        HttpResponse.json(jobBody("QUEUED"), {
          status: 202,
          headers: { Location: `/api/v1/jobs/${JOB_ID}` },
        }),
      ),
      http.get(apiUrl(`/api/v1/jobs/${JOB_ID}`), () => {
        const state = states[Math.min(polls, states.length - 1)] ?? "SUCCEEDED";
        polls += 1;
        return HttpResponse.json(jobBody(state));
      }),
    );
    const { queryClient, result, submit } = setup({
      method: "POST",
      path: PATH,
      invalidates: [queryKeys.me()],
    });
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");

    const outcome = await submit({});
    await settle();

    expect(JOB_POLL_INTERVAL_MS).toBe(2_000);
    expect(outcome).toMatchObject({ kind: "accepted", jobId: JOB_ID });
    expect(result.current.jobId).toBe(JOB_ID);
    expect(polls).toBe(1);
    expect(result.current.job?.state).toBe("RUNNING");
    expect(invalidate).not.toHaveBeenCalled();

    await advance(1_999);
    expect(polls).toBe(1);
    await advance(1);
    expect(polls).toBe(2);
    await advance(2_000);
    expect(polls).toBe(3);
    expect(result.current.job?.state).toBe("SUCCEEDED");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["me", "session", {}] });

    await advance(10_000);
    expect(polls).toBe(3);
  });
});

// KIT-202-BODY-1 (lane F-CTR-WEB's report on CTR-25): `useCommand` adopts a 202 by its `Location` and
// reads no body. The answer has arrived whole all the same when `submit` resolves, and a caller that
// wants the job — the import page — reads it from the outcome's response as before.
describe("DG-FE-05 an accepted command leaves no answer open", () => {
  it("the 202's body has arrived when submit resolves, and the caller can still read the job", async () => {
    const encoder = new TextEncoder();
    const pieces = [
      JSON.stringify(jobBody("QUEUED")).slice(0, 20),
      JSON.stringify(jobBody("QUEUED")).slice(20),
    ];
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
          controller.enqueue(encoder.encode(piece));
        },
      },
      { highWaterMark: 0 },
    );
    server.use(
      http.get(apiUrl(`/api/v1/jobs/${JOB_ID}`), () => HttpResponse.json(jobBody("RUNNING"))),
    );
    const fetched = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(body, {
        status: 202,
        headers: { "Content-Type": "application/json", Location: `/api/v1/jobs/${JOB_ID}` },
      }),
    );
    const { submit } = setup({ method: "POST", path: PATH });

    const outcome = await submit({});
    fetched.mockRestore();

    expect(outcome).toMatchObject({ kind: "accepted", jobId: JOB_ID });
    expect(whole).toBe(true);
    if (outcome.kind !== "accepted") {
      throw new Error("not accepted");
    }
    expect(await outcome.response.json()).toMatchObject({ id: JOB_ID, state: "QUEUED" });
  });
});

// DG-FE-05 rev 1.16 (D-97 (38) as dispatched; the useReportRun attempt rule generalised): every submit carries
// an attempt identity. A later submit, a change of the command's path or reset() supersede the attempts before
// them, whose answers no longer reach the hook's own pending / problem / banner / jobId state; the awaiting
// caller still receives its own outcome. Each POST is held until the test answers it, so answers arrive in the
// order the case names (the actual hook, useCommand state and readProblem; only HTTP is served by MSW).
describe("DG-FE-05 attempt identity: superseded answers never reach the hook state", () => {
  function holdPosts(path: string) {
    const held: ((response: Response) => void)[] = [];
    server.use(
      http.post(
        apiUrl(path),
        () =>
          new Promise<Response>((resolve) => {
            held.push(resolve);
          }),
      ),
    );
    return {
      count: () => held.length,
      answer: async (index: number, response: Response) => {
        const resolve = held[index];
        if (resolve === undefined) {
          throw new Error(`no held request ${String(index)}`);
        }
        resolve(response);
        // msw → fetch → the hook: let the answer land before the assertions.
        await act(async () => {
          await new Promise((finish) => setTimeout(finish, 50));
        });
      },
    };
  }

  function refused(title: string) {
    return problemResponse("validation-failed", 422, title, {
      errors: [{ field: "reason", sheet: null, row: null, rule_id: null, message: title }],
    });
  }

  /** Starts a submit without awaiting its answer (the harness's `submit` awaits, which a held request never allows). */
  function begin(
    result: { readonly current: ReturnType<typeof useCommand> },
    body: unknown,
  ): Promise<CommandOutcome<unknown>> {
    let started: Promise<CommandOutcome<unknown>> | undefined;
    act(() => {
      started = result.current.submit(body);
    });
    if (started === undefined) {
      throw new Error("submit did not start");
    }
    return started;
  }

  it("an out-of-order pair: the older attempt's late refusal does not replace the newer refusal", async () => {
    const posts = holdPosts(PATH);
    const { result } = setup({ method: "POST", path: PATH });
    const first = begin(result, { reason: "first" });
    await waitFor(() => {
      expect(posts.count()).toBe(1);
    });
    const second = begin(result, { reason: "second" });
    await waitFor(() => {
      expect(posts.count()).toBe(2);
    });

    await posts.answer(1, refused("second refused"));
    expect((await second).kind).toBe("failed");
    expect(result.current.problem?.title).toBe("second refused");
    expect(result.current.fieldErrors).toEqual({ reason: "second refused" });
    expect(result.current.pending).toBe(false);

    await posts.answer(0, refused("first refused, obsolete"));
    const outcome = await first;
    // The awaiting caller still receives its own outcome …
    expect(outcome.kind === "failed" ? outcome.problem.title : null).toBe(
      "first refused, obsolete",
    );
    // … but the hook keeps the newer attempt's state.
    expect(result.current.problem?.title).toBe("second refused");
    expect(result.current.fieldErrors).toEqual({ reason: "second refused" });
    expect(result.current.pending).toBe(false);
  });

  it("an older attempt answering first leaves pending true while the newer attempt is in flight", async () => {
    const posts = holdPosts(PATH);
    const { result } = setup({ method: "POST", path: PATH });
    const first = begin(result, { reason: "first" });
    await waitFor(() => {
      expect(posts.count()).toBe(1);
    });
    const second = begin(result, { reason: "second" });
    await waitFor(() => {
      expect(posts.count()).toBe(2);
    });

    await posts.answer(0, refused("first refused, obsolete"));
    expect((await first).kind).toBe("failed");
    expect(result.current.pending).toBe(true);
    expect(result.current.problem).toBeNull();

    await posts.answer(1, HttpResponse.json({ id: "5b7e0c9a-1d2f-4c3b-9a8e-6f5d4c3b2a10" }));
    expect((await second).kind).toBe("succeeded");
    expect(result.current.pending).toBe(false);
    expect(result.current.problem).toBeNull();
  });

  it("a path change supersedes the attempt in flight: its late refusal never shows for the new subject", async () => {
    const OTHER = "/api/v1/contracts/6c8f1dab-2e30-4d4c-8b9f-7a6e5d4c3b21/activate";
    const posts = holdPosts(PATH);
    const queryClient = createQueryClient();
    function Wrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    }
    const { result, rerender } = renderHook((options: CommandOptions) => useCommand(options), {
      wrapper: Wrapper,
      initialProps: { method: "POST", path: PATH },
    });
    const first = begin(result, { reason: "first subject" });
    await waitFor(() => {
      expect(posts.count()).toBe(1);
    });
    expect(result.current.pending).toBe(true);

    rerender({ method: "POST", path: OTHER });

    await posts.answer(0, refused("first subject refused, obsolete"));
    expect((await first).kind).toBe("failed");
    // The first subject's refusal never shows for the new subject, and nothing is pending for it.
    expect(result.current.problem).toBeNull();
    expect(result.current.fieldErrors).toEqual({});
    expect(result.current.pending).toBe(false);
  });

  it("reset() supersedes the attempt in flight: its late refusal never shows", async () => {
    const posts = holdPosts(PATH);
    const { result } = setup({ method: "POST", path: PATH });
    const first = begin(result, { reason: "first" });
    await waitFor(() => {
      expect(posts.count()).toBe(1);
    });
    act(() => {
      result.current.reset();
    });

    await posts.answer(0, refused("first refused, obsolete"));
    expect((await first).kind).toBe("failed");
    // The forgotten intent's refusal never shows, and nothing stays pending for it.
    expect(result.current.problem).toBeNull();
    expect(result.current.pending).toBe(false);
  });
});

// FWR-CMD-R1 / R2 (Codex `PRODUCTION-FWR-CMD-INDEPENDENT-bf94482.md`, SHA-256 ccfd3870…baeb245, cases C09 and
// C10; DG-FE-05 rev 1.18): the cache refresh of an answer is bound to the keys listed when the command was
// submitted, never to a later path's keys; a superseded 202 refreshes those keys at once and adopts no job. C08
// stays as the retained positive control: a same-key obsolete 200 still refreshes and notifies without touching
// the newer attempt's pending state.
describe("DG-FE-05 refresh binding: the submitted command's keys (FWR-CMD-R1 C09, R2 C10, C08 control)", () => {
  const OTHER = "/api/v1/contracts/6c8f1dab-2e30-4d4c-8b9f-7a6e5d4c3b21/activate";
  const KEY_A: QueryKey = ["contracts", "tenant", { id: "a" }];
  const KEY_B: QueryKey = ["contracts", "tenant", { id: "b" }];

  function holdPosts(path: string) {
    const held: ((response: Response) => void)[] = [];
    server.use(
      http.post(
        apiUrl(path),
        () =>
          new Promise<Response>((resolve) => {
            held.push(resolve);
          }),
      ),
    );
    return {
      count: () => held.length,
      answer: async (index: number, response: Response) => {
        const resolve = held[index];
        if (resolve === undefined) {
          throw new Error(`no held request ${String(index)}`);
        }
        resolve(response);
        await act(async () => {
          await new Promise((finish) => setTimeout(finish, 50));
        });
      },
    };
  }

  function begin(
    result: { readonly current: ReturnType<typeof useCommand> },
    body: unknown,
  ): Promise<CommandOutcome<unknown>> {
    let started: Promise<CommandOutcome<unknown>> | undefined;
    act(() => {
      started = result.current.submit(body);
    });
    if (started === undefined) {
      throw new Error("submit did not start");
    }
    return started;
  }

  function mount(initial: CommandOptions) {
    const queryClient = createQueryClient();
    const invalidated = vi.spyOn(queryClient, "invalidateQueries");
    function Wrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    }
    const rendered = renderHook((options: CommandOptions) => useCommand(options), {
      wrapper: Wrapper,
      initialProps: initial,
    });
    const keysInvalidated = () =>
      invalidated.mock.calls.map(([filters]) => JSON.stringify(filters?.queryKey));
    return { ...rendered, keysInvalidated };
  }

  it("C09: after a path change, the obsolete 200 refreshes the submitted command A's keys, not B's", async () => {
    const posts = holdPosts(PATH);
    const { result, rerender, keysInvalidated } = mount({
      method: "POST",
      path: PATH,
      invalidates: [KEY_A],
    });
    const first = begin(result, { reason: "A" });
    await waitFor(() => {
      expect(posts.count()).toBe(1);
    });
    rerender({ method: "POST", path: OTHER, invalidates: [KEY_B] });

    await posts.answer(0, HttpResponse.json({ id: "a" }));
    expect((await first).kind).toBe("succeeded");
    expect(keysInvalidated()).toEqual([JSON.stringify(KEY_A)]);
    expect(result.current.pending).toBe(false);
  });

  it("C10: a superseded 202 refreshes the submitted keys once and adopts no job", async () => {
    const posts = holdPosts(PATH);
    const { result, keysInvalidated } = mount({ method: "POST", path: PATH, invalidates: [KEY_A] });
    const first = begin(result, { reason: "A" });
    await waitFor(() => {
      expect(posts.count()).toBe(1);
    });
    act(() => {
      result.current.reset();
    });

    await posts.answer(
      0,
      HttpResponse.json(jobBody("QUEUED"), {
        status: 202,
        headers: { Location: `/api/v1/jobs/${JOB_ID}` },
      }),
    );
    const outcome = await first;
    expect(outcome.kind === "accepted" ? outcome.jobId : null).toBe(JOB_ID);
    expect(result.current.jobId).toBeNull();
    expect(result.current.job).toBeUndefined();
    expect(keysInvalidated()).toEqual([JSON.stringify(KEY_A)]);
    expect(result.current.pending).toBe(false);
  });

  it("C08 control: a same-key obsolete 200 refreshes and notifies without clearing the newer attempt's pending", async () => {
    const posts = holdPosts(PATH);
    const { result, keysInvalidated } = mount({ method: "POST", path: PATH, invalidates: [KEY_A] });
    let notified = 0;
    const stop = onCommandSucceeded(() => {
      notified += 1;
    });
    const first = begin(result, { reason: "first" });
    await waitFor(() => {
      expect(posts.count()).toBe(1);
    });
    const second = begin(result, { reason: "second" });
    await waitFor(() => {
      expect(posts.count()).toBe(2);
    });

    await posts.answer(0, HttpResponse.json({ id: "first" }));
    expect((await first).kind).toBe("succeeded");
    expect(keysInvalidated()).toEqual([JSON.stringify(KEY_A)]);
    expect(notified).toBe(1);
    expect(result.current.pending).toBe(true);

    await posts.answer(1, HttpResponse.json({ id: "second" }));
    expect((await second).kind).toBe("succeeded");
    expect(result.current.pending).toBe(false);
    expect(keysInvalidated()).toEqual([JSON.stringify(KEY_A), JSON.stringify(KEY_A)]);
    stop();
  });
});

// DG-FE-05 rev 1.156 (item W-23): the keys of commands sent outside the hook. A step is a method, a path
// and a body; its key follows the hook's rule, and inside a sequence a succeeded step keeps it.
describe("DG-FE-05 command keys: commands outside the hook", () => {
  const RECORDS = "/api/v1/judgements";
  const RECORD_ID = "3a4b5c6d-7e8f-4a1b-9c2d-3e4f5a6b7c8d";

  /** Answers each request with the next of `answers`; records every key by path. */
  function serve(path: string, answers: readonly (() => Response)[]) {
    const keys: (string | null)[] = [];
    server.use(
      http.post(apiUrl(path), ({ request }) => {
        keys.push(request.headers.get("Idempotency-Key"));
        const answer = answers[Math.min(keys.length, answers.length) - 1];
        return answer === undefined ? HttpResponse.error() : answer();
      }),
    );
    return keys;
  }
  const created = () => HttpResponse.json({ id: RECORD_ID }, { status: 201 });
  const lost = () => HttpResponse.error();

  it("a lost response and a second press send ONE key, and a success ends it", async () => {
    const keys = serve(RECORDS, [lost, created, created]);
    const commands = createCommandKeys();
    const body = { topic: "OTHER" };

    await expect(commands.send("POST", RECORDS, { body })).rejects.toBeDefined();
    const second = await commands.send("POST", RECORDS, { body });
    expect(second.status).toBe(201);
    expect(keys[0]).toMatch(UUID);
    expect(keys[1]).toBe(keys[0]);

    // The same command sent again after its success is a new one.
    await commands.send("POST", RECORDS, { body });
    expect(keys[2]).toMatch(UUID);
    expect(keys[2]).not.toBe(keys[0]);
  });

  it("a 5xx and an answer the API does not keep leave the key in force; a kept problem ends it", async () => {
    const keys = serve(RECORDS, [
      () => new HttpResponse(null, { status: 503 }),
      () => problemResponse("precondition-required", 428, "Precondition required"),
      () => problemResponse("idempotency-in-progress", 409, "Still running"),
      () => problemResponse("validation-failed", 422, "Check the highlighted fields"),
      created,
    ]);
    const commands = createCommandKeys();
    const body = { topic: "OTHER" };
    for (let press = 0; press < 5; press += 1) {
      await commands.send("POST", RECORDS, { body });
    }
    // 503, 428 and 409 `idempotency-in-progress` are not kept: four sends under one key. The 422 is
    // what a retry of that key would get back, so the fifth send carries a new one.
    expect(new Set(keys.slice(0, 4)).size).toBe(1);
    expect(keys[4]).not.toBe(keys[0]);
  });

  it("the answer's body is left to the caller", async () => {
    serve(RECORDS, [() => problemResponse("lock-conflict", 409, "Busy, try again")]);
    const response = await createCommandKeys().send("POST", RECORDS, { body: {} });
    expect(await response.json()).toMatchObject({ title: "Busy, try again" });
  });

  it("another body or another path is another step with its own key", async () => {
    const keys = serve(RECORDS, [lost]);
    const others = serve("/api/v1/attachments", [lost]);
    const commands = createCommandKeys();
    await expect(commands.send("POST", RECORDS, { body: { a: 1 } })).rejects.toBeDefined();
    await expect(commands.send("POST", RECORDS, { body: { a: 2 } })).rejects.toBeDefined();
    await expect(
      commands.send("POST", "/api/v1/attachments", { body: { a: 1 } }),
    ).rejects.toBeDefined();
    await expect(commands.send("POST", RECORDS, { body: { a: 1 } })).rejects.toBeDefined();
    expect(keys[1]).not.toBe(keys[0]);
    expect(others[0]).not.toBe(keys[0]);
    expect(keys[2]).toBe(keys[0]);
  });

  it("in a sequence a succeeded step keeps its key until clear(): the second press replays it and continues", async () => {
    const SUBMIT = `${RECORDS}/${RECORD_ID}/submit`;
    const creates = serve(RECORDS, [created, created, created]);
    const submits = serve(SUBMIT, [lost, () => HttpResponse.json({ id: RECORD_ID }), created]);
    const commands = createCommandKeys();
    const press = async () => {
      const first = await commands.send("POST", RECORDS, { body: { topic: "OTHER" }, keep: true });
      const record = (await first.json()) as { readonly id: string };
      return commands.send("POST", `${RECORDS}/${record.id}/submit`, { body: {} });
    };

    // First press: the record is created, the second step's response is lost.
    await expect(press()).rejects.toBeDefined();
    // Second press: step 1 under its old key (the API replays the record it stored), step 2 under its
    // old key.
    expect((await press()).ok).toBe(true);
    expect(creates).toHaveLength(2);
    expect(creates[1]).toBe(creates[0]);
    expect(submits[1]).toBe(submits[0]);

    // The sequence is complete: the same press again is a new record under new keys.
    commands.clear();
    await press();
    expect(creates[2]).not.toBe(creates[0]);
    expect(submits[2]).not.toBe(submits[0]);
  });

  it("an upload names its step itself: the same file sent again after a lost response carries ONE key", async () => {
    const FILES = "/api/v1/files";
    const types: (string | null)[] = [];
    const keys: (string | null)[] = [];
    server.use(
      http.post(apiUrl(FILES), ({ request }) => {
        keys.push(request.headers.get("Idempotency-Key"));
        types.push(request.headers.get("Content-Type"));
        return keys.length === 1 ? HttpResponse.error() : HttpResponse.json({ id: RECORD_ID });
      }),
    );
    const commands = createCommandKeys();
    const upload = (name: string) => {
      const form = new FormData();
      form.append("purpose", "EVIDENCE");
      form.append("file", new File(["study"], name));
      return commands.send("POST", FILES, { form, step: `EVIDENCE ${name} 5` });
    };
    await expect(upload("study.pdf")).rejects.toBeDefined();
    expect((await upload("study.pdf")).ok).toBe(true);
    expect(keys[1]).toBe(keys[0]);
    // A multipart body: the client leaves the Content-Type, with its boundary, to the browser.
    expect(types[1]).toMatch(/^multipart\/form-data; boundary=/);
    // Another file is another step.
    await upload("other.pdf");
    expect(keys[2]).not.toBe(keys[0]);
  });
});
