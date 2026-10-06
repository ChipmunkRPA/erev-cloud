// DG-FE-05 (docs/dev-guide.md §8.2, rev 1.156): the `Idempotency-Key` header is written in
// src/lib/api/commands.ts only — as an object key, through `Headers.set` / `append`, assigned to a member
// or as the name of a `[name, value]` pair it is reported in every other file of the product's source.
// The e2e suite, a client of its own, may write it. Lints as
// `make lint` does: from the repository root with --config frontend/eslint.config.js.
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

const FRONTEND = fileURLToPath(new URL("..", import.meta.url));
const eslint = new ESLint({
  cwd: resolve(FRONTEND, ".."),
  overrideConfigFile: resolve(FRONTEND, "eslint.config.js"),
});

const OWN_KEY = `export function headers(): Record<string, string> {
  return { "Idempotency-Key": crypto.randomUUID() };
}
`;
const SET_KEY = `export function mark(headers: Headers, key: string): void {
  headers.set("Idempotency-Key", key);
  headers.append("Idempotency-Key", key);
}
`;
const ASSIGNED_KEY = `export function mark(headers: Record<string, string>, key: string): void {
  headers["Idempotency-Key"] = key;
}
`;
const PAIRED_KEY = `export function headers(key: string): Headers {
  return new Headers([["Idempotency-Key", key]]);
}
`;
const READ_KEY = `export function keyOf(request: Request): string | null {
  return request.headers.get("Idempotency-Key");
}
`;
const CONSTRUCTION = `export function toInstant(x: string): number {
  return new Date(x).getTime();
}
`;

async function reported(path: string, code: string): Promise<string[]> {
  const [result] = await eslint.lintText(code, { filePath: resolve(FRONTEND, path) });
  expect(result?.messages.filter((message) => message.fatal === true)).toEqual([]);
  return (result?.messages ?? []).map((message) => `${String(message.ruleId)}: ${message.message}`);
}

const KEY_RULE =
  "no-restricted-syntax: A command's Idempotency-Key comes from src/lib/api/commands.ts: useCommand, or the CommandKeys of useCommandKeys (DG-FE-05).";

describe("DG-FE-05 the Idempotency-Key is written in one file", () => {
  it("reports the header as an object key in a route, a query module and a component", async () => {
    for (const path of [
      "src/routes/policies/a.tsx",
      "src/lib/api/queries/a.ts",
      "src/components/form/a.tsx",
    ]) {
      expect(await reported(path, OWN_KEY), path).toEqual([KEY_RULE]);
    }
  }, 30_000);

  it("reports Headers.set and Headers.append of the header", async () => {
    expect(await reported("src/routes/a.tsx", SET_KEY)).toEqual([KEY_RULE, KEY_RULE]);
  }, 30_000);

  it("reports the header assigned to a member and as the name of a pair", async () => {
    expect(await reported("src/routes/a.tsx", ASSIGNED_KEY)).toEqual([KEY_RULE]);
    expect(await reported("src/lib/api/queries/a.ts", PAIRED_KEY)).toEqual([KEY_RULE]);
  }, 30_000);

  it("allows it in src/lib/api/commands.ts, and reading it anywhere", async () => {
    expect(await reported("src/lib/api/commands.ts", OWN_KEY)).toEqual([]);
    expect(await reported("src/routes/a.test.tsx", READ_KEY)).toEqual([]);
  }, 30_000);

  it("allows it in the e2e suite, which is an API client of its own", async () => {
    expect(await reported("e2e/support/a.ts", OWN_KEY)).toEqual([]);
  }, 30_000);

  it("keeps both rules apart: src/lib/format may construct dates and may not write the header; commands.ts the reverse", async () => {
    expect(await reported("src/lib/format/a.ts", CONSTRUCTION)).toEqual([]);
    expect(await reported("src/lib/format/a.ts", OWN_KEY)).toEqual([KEY_RULE]);
    expect((await reported("src/lib/api/commands.ts", CONSTRUCTION)).length).toBe(1);
    expect((await reported("src/routes/a.tsx", CONSTRUCTION)).length).toBe(1);
    expect((await reported("e2e/support/a.ts", CONSTRUCTION)).length).toBe(1);
  }, 30_000);
});
