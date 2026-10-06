// DG-FE-20 (docs/dev-guide.md §8.2): `new Date(` and `Date.parse(` are reported outside
// src/lib/format; `Date.now()` is allowed everywhere. Lints as `make lint` does: from the repository
// root with --config frontend/eslint.config.js.
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

const FRONTEND = fileURLToPath(new URL("..", import.meta.url));
const eslint = new ESLint({
  cwd: resolve(FRONTEND, ".."),
  overrideConfigFile: resolve(FRONTEND, "eslint.config.js"),
});

const CONSTRUCTION = `export function toInstant(x: string, s: string): number {
  return new Date(x).getTime() + Date.parse(s);
}
`;
const DURATION = `export function elapsed(start: number): number {
  return Date.now() - start;
}
`;

async function restricted(path: string, code: string): Promise<string[]> {
  const [result] = await eslint.lintText(code, { filePath: resolve(FRONTEND, path) });
  expect(result?.messages.filter((message) => message.fatal === true)).toEqual([]);
  return (result?.messages ?? []).map((message) => String(message.ruleId));
}

describe("DG-FE-20", () => {
  it("reports new Date(x) and Date.parse(s) in src/routes/a.tsx", async () => {
    expect(await restricted("src/routes/a.tsx", CONSTRUCTION)).toEqual([
      "no-restricted-syntax",
      "no-restricted-syntax",
    ]);
  }, 30_000);

  it("allows both in src/lib/format/a.ts", async () => {
    expect(await restricted("src/lib/format/a.ts", CONSTRUCTION)).toEqual([]);
  }, 30_000);

  it("allows Date.now() everywhere", async () => {
    expect(await restricted("src/routes/a.tsx", DURATION)).toEqual([]);
    expect(await restricted("src/lib/format/a.ts", DURATION)).toEqual([]);
  }, 30_000);
});
