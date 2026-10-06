// DG-FE-06 (docs/dev-guide.md §8.2, rev 1.228; item KIT-UNPLACED-ERRORS-1): the field-error map of a
// refused command is read in src/lib/api only. A banner that stands only while that map is empty shows
// nothing when the refusal names a member the form has no field for; fifteen forms did so, and they
// wrote the gate in four ways — on the member, through `fieldErrorsOf`, through an alias and through a
// spread — so the rule reports every read of the map, not one of its uses. The files of the ratchet
// still read it: 17 after the item's first head, 9 since its second (rev 1.265), which
// KIT-REFUSAL-SENTENCES-2 converts. The ratchet only shrinks: a listed file that no longer reads the map
// must leave the list, and no file joins it.
// Lints as `make lint` does: from the repository root with --config frontend/eslint.config.js.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

const FRONTEND = fileURLToPath(new URL("..", import.meta.url));
/** The files not yet converted, as the configuration reads them. */
const FIELD_ERROR_READERS = JSON.parse(
  readFileSync(resolve(FRONTEND, "config/field-error-readers.json"), "utf8"),
) as readonly string[];
const eslint = new ESLint({
  cwd: resolve(FRONTEND, ".."),
  overrideConfigFile: resolve(FRONTEND, "eslint.config.js"),
});

/** The ratchet as head 1 of the item left it. A file is removed here never, and added never. */
const INITIAL: readonly string[] = [
  "src/components/data-grid/SavedViewSelector.tsx",
  "src/routes/auth/password-shared.tsx",
  "src/routes/auth/sign-in.tsx",
  "src/routes/data/exceptions.tsx",
  "src/routes/data/import-detail.tsx",
  "src/routes/policies/account-mapping-version.tsx",
  "src/routes/policies/account-mapping.tsx",
  "src/routes/policies/accounting.tsx",
  "src/routes/policies/rule-set-version.tsx",
  "src/routes/policies/ssp-book-version.tsx",
  "src/routes/policies/ssp-calculator.tsx",
  "src/routes/policies/template-version.tsx",
  "src/routes/policies/version-meta.tsx",
  "src/routes/settings/calendars.tsx",
  "src/routes/settings/currencies.tsx",
  "src/routes/settings/product.tsx",
  "src/routes/settings/sandbox.tsx",
];

// The four ways the gate was written, and a field's own message read from the map.
const ON_THE_MEMBER = `export function shows(command: { problem: object | null; fieldErrors: Record<string, string> }): boolean {
  return command.problem !== null && Object.keys(command.fieldErrors).length === 0;
}
`;
const THROUGH_THE_CALL = `declare function fieldErrorsOf(problem: object): Record<string, string>;
export function shows(problem: object | null): boolean {
  return problem !== null && Object.keys(fieldErrorsOf(problem)).length === 0;
}
`;
const THROUGH_AN_ALIAS = `export function shows(create: { problem: object | null; fieldErrors: Record<string, string> }): boolean {
  const errors = create.fieldErrors;
  return create.problem !== null && Object.keys(errors).length === 0;
}
`;
const THROUGH_A_SPREAD = `export function shows(command: { problem: object | null; fieldErrors: Record<string, string> }, local: Record<string, string>): boolean {
  const errors = { ...command.fieldErrors, ...local };
  return command.problem !== null && Object.keys(errors).length === 0;
}
`;
const TAKEN_OUT = `export function shows(command: { problem: object | null; fieldErrors: Record<string, string> }): boolean {
  const { problem, fieldErrors } = command;
  return problem !== null && Object.keys(fieldErrors).length === 0;
}
`;
const ONE_FIELD = `export function codeError(command: { fieldErrors: Record<string, string> }): string | null {
  return command.fieldErrors.code ?? null;
}
`;
// A form's own map of what its fields show, and the placing of the kit.
const OTHER_MAPS = `export function empty(errors: Record<string, string>, refusals: { fields: Record<string, string | null> }): boolean {
  return Object.keys(errors).length === 0 && Object.values(refusals.fields).every((message) => message === null);
}
`;

async function reported(path: string, code: string): Promise<string[]> {
  const [result] = await eslint.lintText(code, { filePath: resolve(FRONTEND, path) });
  expect(result?.messages.filter((message) => message.fatal === true)).toEqual([]);
  return (result?.messages ?? []).map((message) => `${String(message.ruleId)}: ${message.message}`);
}

const RULE =
  "no-restricted-syntax: The field-error map of a refused command is read in src/lib/api only: a form places the errors with src/lib/api/refusals.ts and shows RefusalBanner, which says what no field took (DG-FE-06).";

describe("DG-FE-06 the field-error map is read in the API library only", () => {
  it("reports the gate however it is written, in a route, a component and the shell", async () => {
    for (const path of [
      "src/routes/zz/a.tsx",
      "src/components/form/a.tsx",
      "src/app/shell/a.tsx",
    ]) {
      for (const code of [
        ON_THE_MEMBER,
        THROUGH_THE_CALL,
        THROUGH_AN_ALIAS,
        THROUGH_A_SPREAD,
        TAKEN_OUT,
      ]) {
        expect(await reported(path, code), `${path}\n${code}`).toEqual([RULE]);
      }
    }
  }, 60_000);

  it("reports a field's own message read from the map as well: a form reads the placing", async () => {
    expect(await reported("src/routes/zz/a.tsx", ONE_FIELD)).toEqual([RULE]);
  }, 30_000);

  it("leaves other maps alone", async () => {
    expect(await reported("src/routes/zz/a.tsx", OTHER_MAPS)).toEqual([]);
  }, 30_000);

  it("allows the map in the API library, in a test and in the test helpers", async () => {
    for (const path of [
      "src/lib/api/zz.ts",
      "src/lib/api/queries/zz.ts",
      "src/lib/api/commands.ts",
      "src/routes/zz/a.test.tsx",
      "src/test/zz.tsx",
    ]) {
      expect(await reported(path, ON_THE_MEMBER), path).toEqual([]);
      expect(await reported(path, THROUGH_THE_CALL), path).toEqual([]);
    }
  }, 30_000);

  it("does not reach the e2e suite", async () => {
    expect(await reported("e2e/support/a.ts", ON_THE_MEMBER)).toEqual([]);
  }, 30_000);

  it("the ratchet only shrinks: no file has joined it", () => {
    expect(FIELD_ERROR_READERS.filter((file) => !INITIAL.includes(file))).toEqual([]);
    expect(new Set(FIELD_ERROR_READERS).size).toBe(FIELD_ERROR_READERS.length);
  });

  it("the ratchet only shrinks: a listed file still reads the map, else it leaves the list", async () => {
    const converted: string[] = [];
    for (const file of FIELD_ERROR_READERS) {
      // Linted under a name outside the list, the file's own reads are reported.
      const source = readFileSync(resolve(FRONTEND, file), "utf8");
      const extension = file.endsWith(".tsx") ? "tsx" : "ts";
      const messages = await reported(`src/routes/zz/ratchet.${extension}`, source);
      if (!messages.includes(RULE)) {
        converted.push(file);
      }
    }
    expect(converted, "remove these from frontend/config/field-error-readers.json").toEqual([]);
  }, 240_000);

  it("a listed file is not reported for its reads, and keeps the other rules", async () => {
    const [listed] = FIELD_ERROR_READERS;
    if (listed === undefined) {
      return;
    }
    expect(await reported(listed, ON_THE_MEMBER)).toEqual([]);
    expect(await reported(listed, "export const stamp = new Date();\n")).toEqual([
      "no-restricted-syntax: Business dates stay YYYY-MM-DD strings; construct dates only in src/lib/format (DG-FE-20).",
    ]);
  }, 30_000);
});
