// The API as a member's own session asks it (release candidate QA; PROGRESS.md D-99 (7)). Every
// request goes through the request context of the member's browser context, so it carries her
// cookie and nothing else: what it is answered is what a screen of hers could be answered. A check
// reads the status and the problem type; it never asserts, so that a refused read is a row of the
// record and not the end of the pass. An answer 429 (05 SOP-4: 1,200 requests a minute per browser
// session) is waited out and asked again.
import { randomUUID } from "node:crypto";

import type { APIResponse, Page } from "@playwright/test";

import { webOrigin } from "../api";

export type Params = Readonly<Record<string, string | number | boolean>>;
export type Method = "POST" | "PUT" | "PATCH" | "DELETE";

export interface Got {
  readonly status: number;
  readonly text: string;
  /** The parsed body, or null when it is not JSON. */
  readonly json: unknown;
  /** The last segment of a problem's `type` ("not-found", "forbidden"), or "". */
  readonly problem: string;
  readonly headers: Readonly<Record<string, string>>;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** A member of a JSON value by path, or undefined: the pass reads shapes it does not own. */
export function at(value: unknown, ...path: readonly (string | number)[]): unknown {
  let current: unknown = value;
  for (const key of path) {
    if (typeof key === "number") {
      current = Array.isArray(current) ? (current as unknown[])[key] : undefined;
    } else {
      current = isRecord(current) ? current[key] : undefined;
    }
  }
  return current;
}

export function text(value: unknown, ...path: readonly (string | number)[]): string {
  const found = at(value, ...path);
  return typeof found === "string" ? found : typeof found === "number" ? String(found) : "";
}

export function items(value: unknown, ...path: readonly (string | number)[]): readonly unknown[] {
  const found = path.length === 0 ? at(value, "items") : at(value, ...path);
  return Array.isArray(found) ? (found as unknown[]) : [];
}

async function read(response: APIResponse): Promise<Got> {
  const body = await response.text().catch(() => "");
  let json: unknown = null;
  try {
    json = body === "" ? null : (JSON.parse(body) as unknown);
  } catch {
    json = null;
  }
  const type = text(json, "type");
  return {
    status: response.status(),
    text: body,
    json,
    problem: response.status() >= 400 ? (type.split("/").at(-1) ?? "") : "",
    headers: response.headers(),
  };
}

/** `404 not-found`, `200`: the answer as the record writes it. */
export function said(got: Got): string {
  return got.problem === "" ? String(got.status) : `${String(got.status)} ${got.problem}`;
}

/**
 * 04 API-C-02: the refusal of a command whose CSRF token is not the session's. It is 403 forbidden,
 * as a missing permission is, and names its rule; the guard of a permission names none.
 */
export function csrfRefused(got: Got): boolean {
  return (
    got.status === 403 &&
    items(got.json, "errors").some((error) => text(error, "rule_id") === "API-C-02")
  );
}

export class Api {
  private csrf: string | null = null;

  constructor(readonly page: Page) {}

  private async asked(ask: () => Promise<APIResponse>): Promise<Got> {
    for (let attempt = 0; ; attempt += 1) {
      const got = await read(await ask());
      if (got.status !== 429 || attempt >= 3) {
        return got;
      }
      const wait = Number(got.headers["retry-after"] ?? "5");
      await sleep((Number.isFinite(wait) ? Math.min(Math.max(wait, 1), 60) : 5) * 1000);
    }
  }

  get(path: string, params: Params = {}): Promise<Got> {
    return this.asked(() => this.page.request.get(path, { params: { ...params } }));
  }

  private async token(): Promise<string> {
    if (this.csrf === null) {
      const session = await this.get("/api/v1/session");
      this.csrf = text(session.json, "csrf_token");
    }
    return this.csrf;
  }

  /**
   * A command with the session's CSRF token, a new key and the web origin (04 API-C-02).
   *
   * The token is the session's: a step-up or a switch of workspace ends the session and opens its
   * successor with a new one (05 SAR-09), and a command with the old token is refused 403 forbidden
   * — the answer a missing permission gets. That refusal is no answer to the command, so the token
   * is read again and the command sent once more; a second refusal stops the check that asked, so
   * that no row takes it for a denial.
   */
  private async command(
    name: string,
    ask: (headers: Readonly<Record<string, string>>) => Promise<APIResponse>,
  ): Promise<Got> {
    for (let attempt = 0; ; attempt += 1) {
      const token = await this.token();
      const got = await this.asked(() =>
        ask({ "X-CSRF-Token": token, "Idempotency-Key": randomUUID(), Origin: webOrigin() }),
      );
      if (!csrfRefused(got)) {
        return got;
      }
      if (attempt >= 1) {
        throw new Error(
          `${name}: the session's CSRF token was refused twice (04 API-C-02); the command was not asked`,
        );
      }
      this.csrf = null;
    }
  }

  send(
    method: Method,
    path: string,
    body?: unknown,
    headers: Readonly<Record<string, string>> = {},
  ): Promise<Got> {
    return this.command(`${method} ${path}`, (own) =>
      this.page.request.fetch(path, {
        method,
        headers: { ...own, ...headers },
        ...(body === undefined ? {} : { data: body }),
      }),
    );
  }

  /** A CSV file uploaded as the member (04 API-C-17, the one multipart route); the answer names its id. */
  upload(name: string, content: string, purpose = "IMPORT_SOURCE"): Promise<Got> {
    return this.command("POST /api/v1/files", (own) =>
      this.page.request.post("/api/v1/files", {
        headers: { ...own },
        multipart: {
          purpose,
          file: { name, mimeType: "text/csv", buffer: Buffer.from(content, "utf-8") },
        },
      }),
    );
  }

  /** Every item of a list, following `next_cursor`, at most `cap` of them. */
  async list(path: string, params: Params = {}, cap = 5_000): Promise<readonly unknown[]> {
    const found: unknown[] = [];
    let cursor: string | null = null;
    for (;;) {
      const got = await this.get(path, {
        limit: 200,
        ...params,
        ...(cursor === null ? {} : { cursor }),
      });
      if (got.status !== 200) {
        throw new Error(`GET ${path} answered ${said(got)}`);
      }
      found.push(...items(got.json));
      const next = at(got.json, "next_cursor");
      if (typeof next !== "string" || next === "" || found.length >= cap) {
        return found;
      }
      cursor = next;
    }
  }

  /** The total a list states for its filter (`count=true`, header `x-erev-total-count`). */
  async total(path: string, params: Params = {}): Promise<number | null> {
    const got = await this.get(path, { limit: 1, count: true, ...params });
    const header = got.headers["x-erev-total-count"];
    return got.status === 200 && header !== undefined ? Number(header) : null;
  }

  /** Polls the job a 202 names until it leaves the queue; the state it ended in. */
  async job(started: Got, timeoutMs = 180_000): Promise<string> {
    const location = started.headers["location"];
    const id = text(started.json, "id");
    const path =
      location !== undefined && location !== ""
        ? new URL(location, webOrigin()).pathname
        : id === ""
          ? ""
          : `/api/v1/jobs/${id}`;
    if (path === "") {
      return "no job named";
    }
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const state = text((await this.get(path)).json, "state");
      if (/^(SUCCEEDED|FAILED|CANCELLED|DEAD)/.test(state)) {
        return state;
      }
      if (Date.now() > deadline) {
        return `still ${state === "" ? "unread" : state} after ${String(timeoutMs / 1000)} s`;
      }
      await sleep(1_000);
    }
  }
}

/** A decimal string as a number of minor units (two decimals), for sums the pass makes itself. */
export function cents(amount: unknown): bigint | null {
  if (typeof amount !== "string" || !/^-?\d+(\.\d+)?$/.test(amount)) {
    return null;
  }
  const negative = amount.startsWith("-");
  const [whole = "0", fraction = ""] = amount.replace("-", "").split(".");
  if (/[1-9]/.test(fraction.slice(2))) {
    return null;
  }
  const value = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0").slice(0, 2));
  return negative ? -value : value;
}

/** Minor units back as a decimal string with two places. */
export function decimal(value: bigint): string {
  const negative = value < 0n;
  const digits = (negative ? -value : value).toString().padStart(3, "0");
  return `${negative ? "-" : ""}${digits.slice(0, -2)}.${digits.slice(-2)}`;
}

/** DS-FMT-04: the digits of a decimal string as a screen groups them ("1,234.50"). */
export function grouped(amount: string): string {
  const negative = amount.startsWith("-");
  const [whole = "", fraction] = amount.replace("-", "").split(".");
  const digits = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const body = fraction === undefined ? digits : `${digits}.${fraction}`;
  return negative ? `(${body})` : body;
}
