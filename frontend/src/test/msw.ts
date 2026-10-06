// MSW for Vitest (docs/dev-guide.md DG-FE-18): in-process Node interception, no service worker and
// no network. A request without a handler fails the test, and so does a mocked exchange whose dates
// do not have the shape the OpenAPI document gives them (`./contract`; supervisor ruling R-65): a
// fixture that the API could not send is no witness of the page.
import { HttpResponse, type JsonBodyType } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll } from "vitest";

import { contractViolations, type Exchange } from "./contract";

export const server = setupServer();

const reading: Promise<void>[] = [];
const violations: string[] = [];

function watch(exchange: Promise<Exchange>): void {
  reading.push(
    exchange.then(
      (found) => {
        violations.push(...contractViolations(found));
      },
      // A body that cannot be read (an aborted request) has nothing to check.
      () => undefined,
    ),
  );
}

/** The contract violations of the mocked traffic since the last call, each once. */
export async function mockedTrafficViolations(): Promise<string[]> {
  await Promise.all(reading.splice(0));
  return [...new Set(violations.splice(0))];
}

/** Starts the server for the calling test file and resets handlers after each test. */
export function installMswServer(): void {
  beforeAll(() => {
    server.listen({ onUnhandledRequest: "error" });
    server.events.on("request:start", ({ request }) => {
      const copy = request.clone();
      watch(copy.text().then((body) => ({ method: copy.method, url: copy.url, body })));
    });
    server.events.on("response:mocked", ({ request, response }) => {
      const copy = response.clone();
      watch(
        copy.text().then((body) => ({
          method: request.method,
          url: request.url,
          status: copy.status,
          body,
        })),
      );
    });
  });
  afterEach(async () => {
    server.resetHandlers();
    const found = await mockedTrafficViolations();
    if (found.length > 0) {
      throw new Error(
        `Mocked API traffic does not match docs/api/openapi.json (DG-FE-18):\n${found.join("\n")}`,
      );
    }
  });
  afterAll(() => {
    server.events.removeAllListeners();
    server.close();
  });
}

/** The absolute URL of an API path on the test page origin. */
export function apiUrl(path: string): string {
  return new URL(path, globalThis.location.origin).href;
}

export interface HeldRead {
  /** From now on the read waits for `release()`. */
  readonly hold: () => void;
  /** What the handler of the read awaits: nothing before `hold()`, `release()` after it. */
  readonly passed: () => Promise<void>;
  /** The reads that have come to wait. */
  readonly waiting: () => number;
  readonly release: () => void;
}

/**
 * A read a test holds back: a command has answered and the page still waits for what it reads again,
 * as it does behind a slow connection or under load.
 */
export function heldRead(): HeldRead {
  let release: () => void = () => undefined;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  let holding = false;
  let waiting = 0;
  return {
    hold: () => {
      holding = true;
    },
    passed: async () => {
      if (holding) {
        waiting += 1;
        await gate;
      }
    },
    waiting: () => waiting,
    release: () => {
      release();
    },
  };
}

/** An `application/problem+json` response; a null slug gives `about:blank`. */
export function problemResponse(
  slug: string | null,
  status: number,
  title: string,
  extra: Readonly<Record<string, JsonBodyType>> = {},
) {
  return HttpResponse.json(
    {
      type: slug === null ? "about:blank" : `https://erev.dev/problems/${slug}`,
      title,
      status,
      instance: "urn:erev:request:0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d",
      errors: [],
      ...extra,
    },
    { status, headers: { "Content-Type": "application/problem+json" } },
  );
}
