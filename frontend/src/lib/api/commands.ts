// Commands (docs/dev-guide.md DG-FE-05; PRD BR-PLT-03; 04 API-C-04, API-C-08, API-C-12).
// One Idempotency-Key per user intent: the key is kept while the same body is retried and the API has
// kept no answer for it, so a retry after a lost response or a 5xx cannot run the command twice. A
// success, a different body, `reset()` and an answered problem the API keeps end the intent (SPEC-Q-197;
// DG-FE-05 rev 1.132, supervisor rulings R-97 (6) and R-102 (e)): the API stores every problem below 500
// except 401, 403, 412, 428, 429 and 409 `idempotency-in-progress` as the first response of its key and
// replays it (dev-guide DG-KRN-IDEM-03), so "try again" after `lock-conflict`, a failed checklist or a
// 422 that the record and not the body caused must carry a new key to be decided at all. Nothing is
// retried automatically and nothing is updated optimistically. Every submit carries an attempt identity
// (DG-FE-05 rev 1.16; D-97 (38)): a later submit, a change of the command's `path` or `reset()` supersede
// the attempts before them, whose answers no longer reach `pending`, `problem`, `banner` or `jobId`; the
// awaiting caller still receives its own outcome. The cache refresh of an answer is bound to the keys
// listed when that command was submitted, never to the keys of a later path (Codex FWR-CMD-R1, C09): a 200
// or 412 refreshes them on arrival, a superseded 202 refreshes them at once because its job is not adopted
// or polled (FWR-CMD-R2, C10), and the job a current 202 adopts refreshes them when it reaches a terminal
// state.
//
// Commands outside the hook (DG-FE-05 rev 1.156; item W-23) take their key from `CommandKeys`, the keys
// of one component: the steps of a press that sends several commands, a loop over records, a module
// function. A step is a method, a path and a body, and its key follows the same rule — kept through a
// lost response, a 5xx and an answer the API does not keep; ended by a success and by a problem the API
// keeps. Inside a sequence a step that succeeded keeps its key (`keep`) until the sequence completes
// and calls `clear()`: when a later step fails, the second press sends the earlier steps again under
// their keys, the API replays what it stored — the same record — and the sequence continues at the
// step that failed instead of creating the record twice. No other file writes the header
// (`frontend/eslint.config.js`).
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { t } from "../i18n/t";
import { send } from "./client";
import { isTerminal, type Job, useJob } from "./jobs";
import { type ApiProblem, fieldErrorsOf, readProblem } from "./problems";
import type { QueryKey } from "./query-keys";

export type CommandMethod = "POST" | "PUT" | "PATCH" | "DELETE";

export interface CommandOptions {
  readonly method: CommandMethod;
  /** The API path, for example `/api/v1/approvals/<id>/decide`. */
  readonly path: string;
  readonly ifMatch?: string;
  readonly invalidates?: readonly QueryKey[];
}

export interface SubmitOptions {
  readonly ifMatch?: string;
}

export type CommandOutcome<T> =
  | { readonly kind: "succeeded"; readonly data: T | null; readonly response: Response }
  | { readonly kind: "accepted"; readonly jobId: string; readonly response: Response }
  | { readonly kind: "failed"; readonly problem: ApiProblem }
  | { readonly kind: "network-error"; readonly error: unknown };

export interface CommandState<T> {
  readonly submit: (body?: unknown, options?: SubmitOptions) => Promise<CommandOutcome<T>>;
  readonly reset: () => void;
  readonly pending: boolean;
  readonly problem: ApiProblem | null;
  readonly fieldErrors: Readonly<Record<string, string>>;
  /** SCREENS SCR-ST-09 banner text after a 412, else null. */
  readonly banner: string | null;
  readonly jobId: string | null;
  readonly job: Job | undefined;
}

type CommandListener = () => void;

const commandListeners = new Set<CommandListener>();

/**
 * Subscribes to every successful command: a 2xx answer, or a job that reached a terminal state.
 * Shell regions that refresh after any command (SCREENS §1.2 notifications badge) listen here.
 */
export function onCommandSucceeded(listener: CommandListener): () => void {
  commandListeners.add(listener);
  return () => {
    commandListeners.delete(listener);
  };
}

function notifyCommandSucceeded(): void {
  for (const listener of commandListeners) {
    listener();
  }
}

const JOB_PATH = /^\/api\/v1\/jobs\/([^/]+)$/;
/** The statuses the API never keeps as the first response of a key (dev-guide DG-KRN-IDEM-03). */
const UNKEPT_STATUSES: ReadonlySet<number> = new Set([401, 403, 412, 428, 429]);
/** 04 §15.2: the 409 that names the key itself; the first attempt may still succeed under it. */
const IN_PROGRESS_SLUG = "idempotency-in-progress";

/** True when the API keeps this answer for the key and would replay it to a retry (DG-KRN-IDEM-03). */
function keptForKey(status: number, slug: string | null): boolean {
  return (
    status >= 400 &&
    status < 500 &&
    !UNKEPT_STATUSES.has(status) &&
    !(status === 409 && slug === IN_PROGRESS_SLUG)
  );
}

function jobIdFrom(location: string | null): string | null {
  if (location === null) {
    return null;
  }
  const match = JOB_PATH.exec(new URL(location, globalThis.location.origin).pathname);
  return match?.[1] ?? null;
}

/** The job a command was accepted as (202 with `Location: /api/v1/jobs/<id>`), else null. */
export function acceptedJobId(response: Response): string | null {
  return response.status === 202 ? jobIdFrom(response.headers.get("Location")) : null;
}

async function readBody(response: Response): Promise<unknown> {
  if (response.status === 204 || !(response.headers.get("Content-Type") ?? "").includes("json")) {
    return null;
  }
  return response.json();
}

export function useCommand<T = unknown>(options: CommandOptions): CommandState<T> {
  const queryClient = useQueryClient();
  const latest = useRef(options);
  const intent = useRef<{ readonly key: string; readonly body: string } | null>(null);
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [conflict, setConflict] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob(jobId);
  // The identity of the latest attempt; an answer whose attempt is no longer current is discarded.
  const attempts = useRef(0);

  useEffect(() => {
    latest.current = options;
  });

  /** Refreshes the reads a command listed when it was submitted (DG-FE-05). */
  const refresh = useCallback(
    async (keys: readonly QueryKey[]) => {
      await Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey })));
    },
    [queryClient],
  );
  // The keys of the attempt whose job this hook adopted: its terminal state refreshes those, not the keys of
  // whatever path the hook shows by then.
  const adoptedKeys = useRef<readonly QueryKey[]>([]);

  const finished = jobId !== null && isTerminal(job.data);
  useEffect(() => {
    if (finished) {
      void refresh(adoptedKeys.current);
      notifyCommandSucceeded();
    }
  }, [finished, refresh]);

  const submit = useCallback(
    async (body?: unknown, submitOptions: SubmitOptions = {}): Promise<CommandOutcome<T>> => {
      const { method, path, ifMatch, invalidates } = latest.current;
      // Captured with the path: the answer refreshes these keys whatever the hook shows when it arrives.
      const keys: readonly QueryKey[] = invalidates ?? [];
      const serialised = body === undefined ? "" : JSON.stringify(body);
      if (intent.current === null || intent.current.body !== serialised) {
        intent.current = { key: crypto.randomUUID(), body: serialised };
      }
      const key = intent.current.key;
      const headers: Record<string, string> = { "Idempotency-Key": key };
      const version = submitOptions.ifMatch ?? ifMatch;
      if (version !== undefined) {
        headers["If-Match"] = version;
      }
      const attempt = (attempts.current += 1);
      const current = () => attempts.current === attempt;
      setPending(true);
      setProblem(null);
      setConflict(false);
      let response: Response;
      try {
        response = await send(method, path, { body, headers });
      } catch (error) {
        if (current()) {
          setPending(false);
        }
        return { kind: "network-error", error };
      }
      if (current()) {
        setPending(false);
      }
      if (response.ok) {
        if (current()) {
          intent.current = null;
        }
        const accepted =
          response.status === 202 ? jobIdFrom(response.headers.get("Location")) : null;
        if (accepted !== null) {
          if (current()) {
            // The adopted job refreshes this attempt's keys when it ends.
            adoptedKeys.current = keys;
            setJobId(accepted);
          } else {
            // A superseded job is neither adopted nor polled, so its only refresh of the submitted reads
            // happens now (FWR-CMD-R2); the caller still learns that its command was accepted.
            await refresh(keys);
          }
          return { kind: "accepted", jobId: accepted, response };
        }
        // The server changed even when the view moved on: the submitted reads are stale either way.
        await refresh(keys);
        notifyCommandSucceeded();
        return { kind: "succeeded", data: (await readBody(response)) as T | null, response };
      }
      const failure = await readProblem(response);
      // The refused command had no effect, and a kept refusal is what a retry of the key would get back.
      if (keptForKey(response.status, failure.slug) && intent.current?.key === key) {
        intent.current = null;
      }
      if (current()) {
        setProblem(failure);
      }
      if (response.status === 412) {
        if (current()) {
          setConflict(true);
        }
        await refresh(keys);
      }
      return { kind: "failed", problem: failure };
    },
    [refresh],
  );

  const reset = useCallback(() => {
    attempts.current += 1;
    intent.current = null;
    setPending(false);
    setProblem(null);
    setConflict(false);
    setJobId(null);
  }, []);

  // A change of the command's path is a change of subject: the attempts before it are superseded and
  // their state cleared, as reset() does (DG-FE-05 rev 1.16).
  const previousPath = useRef(options.path);
  useEffect(() => {
    if (previousPath.current === options.path) {
      return;
    }
    previousPath.current = options.path;
    reset();
  }, [options.path, reset]);

  return {
    submit,
    reset,
    pending,
    problem,
    fieldErrors: problem === null ? {} : fieldErrorsOf(problem),
    banner: conflict ? t("common.command.recordChanged") : null,
    jobId,
    job: job.data,
  };
}

export interface KeyedInit {
  /** The JSON body; with the method and the path it names the step. */
  readonly body?: unknown;
  /** A multipart body (an upload). It cannot name the step: `step` does. */
  readonly form?: FormData;
  /** What names the step beside the method and the path when the body cannot, for an upload its file. */
  readonly step?: string;
  readonly headers?: Readonly<Record<string, string>>;
  /**
   * A step of a sequence that one press sends: its key outlives its success, until `clear()`, so that
   * a second press after a later step failed replays this step's stored answer.
   */
  readonly keep?: boolean;
}

/** The Idempotency-Keys of the commands a component sends outside `useCommand` (DG-FE-05). */
export interface CommandKeys {
  /**
   * Sends one command under the key of its step. A network failure rejects, as `send` does, and leaves
   * the key in force.
   */
  readonly send: (method: CommandMethod, path: string, init?: KeyedInit) => Promise<Response>;
  /** The press is complete: every key is forgotten, and the same commands sent again are new ones. */
  readonly clear: () => void;
}

export function createCommandKeys(): CommandKeys {
  const keys = new Map<string, string>();
  const keyOf = (step: string): string => {
    let key = keys.get(step);
    if (key === undefined) {
      key = crypto.randomUUID();
      keys.set(step, key);
    }
    return key;
  };
  const settle = async (step: string, response: Response, keep = false): Promise<void> => {
    if (response.ok) {
      if (!keep) {
        keys.delete(step);
      }
      return;
    }
    // Only a 409 needs its slug: `idempotency-in-progress` names the key itself. The clone leaves the
    // body to the caller.
    const slug = response.status === 409 ? (await readProblem(response.clone())).slug : null;
    if (keptForKey(response.status, slug)) {
      keys.delete(step);
    }
  };
  return {
    send: async (method, path, init = {}) => {
      const named = init.step ?? (init.body === undefined ? "" : JSON.stringify(init.body));
      const step = `${method} ${path} ${named}`;
      const response = await send(method, path, {
        ...(init.body === undefined ? {} : { body: init.body }),
        ...(init.form === undefined ? {} : { form: init.form }),
        headers: { ...init.headers, "Idempotency-Key": keyOf(step) },
      });
      await settle(step, response, init.keep);
      return response;
    },
    clear: () => {
      keys.clear();
    },
  };
}

/** The keys of one component instance; they go with it (a drawer that closes, a page that is left). */
export function useCommandKeys(): CommandKeys {
  const [keys] = useState(createCommandKeys);
  return keys;
}
