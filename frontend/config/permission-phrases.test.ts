// DG-FE-16 (docs/dev-guide.md rev 1.274; SCREENS §0.6 SCR-PERM-01 rev 1.71; item W-12e): a sentence
// that names a permission says its phrase and, in parentheses, its code, and takes both from one
// function, `permissionWords` of src/lib/permission-words.ts, which is given the constant the gate
// asks. The compiler holds that a sentence names no permission without a phrase: the function takes
// the union of `PHRASED_PERMISSIONS`. This test holds the rest: the phrases of the catalogue and that
// list are one set, each is a permission the API's document names, each is named by a sentence of the
// product, and no sentence of the catalogue spells a phrase of its own. The sentences of a missing
// permission on the pages item PERM-SENTENCE-NAMES-CODE-1 (register index 271) converts still take a
// phrase by its key: that list only shrinks.
import { readdirSync, readFileSync } from "node:fs";
import { relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const FRONTEND = fileURLToPath(new URL("..", import.meta.url));
const SOURCES = resolve(FRONTEND, "src");
const PHRASE_PREFIX = "permission.phrase.";

/**
 * The phrase keys a sentence of a missing permission still reads by itself, as item W-12e left them.
 * No key joins the list; a key leaves it when its last sentence takes `permissionWords`.
 */
const PHRASES_BY_KEY: readonly string[] = [
  "approvals.delegations.access.permission",
  "close.multi.access.permission",
  "contracts.access.permission",
  "contracts.draft.access.permission",
  "data.imports.new.permission",
  "data.integrations.access.permission",
  "explain.trace.access.permission",
  "modifications.access.judgements",
  "modifications.access.permission",
  "reports.dashboard.access.permission",
  "reports.runs.access.permission",
  "settings.access.permission.configRead",
  "settings.access.permission.contractRead",
  "settings.access.permission.roleManage",
  "settings.access.permission.sspRead",
  "settings.access.permission.userManage",
];

function productFiles(directory: string = SOURCES): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) {
      return entry.name === "test" || entry.name === "__tests__" ? [] : productFiles(path);
    }
    return /\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name) && !/\.d\.ts$/.test(path)
      ? [path]
      : [];
  });
}

const PRODUCT = productFiles().map((path) => ({
  path: relative(FRONTEND, path),
  text: readFileSync(path, "utf8"),
}));
const CATALOGUE = JSON.parse(
  readFileSync(resolve(SOURCES, "messages/en.json"), "utf8"),
) as Readonly<Record<string, string>>;

/** `PHRASED_PERMISSIONS` as the module writes it. */
function phrasedPermissions(): string[] {
  const source = readFileSync(resolve(SOURCES, "lib/permission-words.ts"), "utf8");
  const list = /export const PHRASED_PERMISSIONS = \[([^\]]*)\] as const;/.exec(source)?.[1] ?? "";
  return Array.from(list.matchAll(/"([^"]+)"/g), (match) => match[1] ?? "");
}

/** The permissions the API's document names: `x-erev-permission` of every operation. */
function documentPermissions(): ReadonlySet<string> {
  const document = JSON.parse(
    readFileSync(resolve(FRONTEND, "../docs/api/openapi.json"), "utf8"),
  ) as { readonly paths: Readonly<Record<string, Readonly<Record<string, unknown>>>> };
  const codes = new Set<string>();
  for (const operations of Object.values(document.paths)) {
    for (const operation of Object.values(operations)) {
      const code = (operation as { readonly "x-erev-permission"?: unknown })["x-erev-permission"];
      if (typeof code === "string") {
        codes.add(code);
      }
    }
  }
  return codes;
}

/** Every `const NAME = "<area>.<verb>"` of the product: the permission constants among them. */
function constants(): ReadonlyMap<string, ReadonlySet<string>> {
  const found = new Map<string, Set<string>>();
  for (const { text } of PRODUCT) {
    for (const match of text.matchAll(/\bconst ([A-Z][A-Z0-9_]*)\s*=\s*"([a-z_]+\.[a-z_]+)"/g)) {
      const [, name = "", code = ""] = match;
      found.set(name, (found.get(name) ?? new Set<string>()).add(code));
    }
  }
  return found;
}

/**
 * What the sentences of the product name: the arguments of `permissionWords(…)`, and of
 * `<AccessLimited>` its `permissions={[…]}` and the `permission:` of its `allEntities`.
 */
function named(): { readonly codes: ReadonlySet<string>; readonly unresolved: readonly string[] } {
  const known = constants();
  const codes = new Set<string>();
  const unresolved: string[] = [];
  const take = (path: string, list: string) => {
    for (const raw of list.split(",")) {
      const argument = raw.trim();
      if (argument === "" || argument.startsWith("...")) {
        continue;
      }
      const literal = /^"([a-z_]+\.[a-z_]+)"$/.exec(argument)?.[1];
      const values = literal === undefined ? known.get(argument) : new Set([literal]);
      if (values === undefined || values.size !== 1) {
        unresolved.push(`${path}: ${argument}`);
        continue;
      }
      for (const code of values) {
        codes.add(code);
      }
    }
  };
  for (const { path, text } of PRODUCT) {
    if (
      path === "src/lib/permission-words.ts" ||
      path === "src/components/feedback/AccessLimited.tsx"
    ) {
      continue;
    }
    for (const match of text.matchAll(/\bpermissionWords\(([^()]*)\)/g)) {
      take(path, match[1] ?? "");
    }
    for (const match of text.matchAll(/<AccessLimited\b[\s\S]*?\/>/g)) {
      const element = match[0];
      take(path, /\bpermissions=\{\[([^\]]*)\]\}/.exec(element)?.[1] ?? "");
      for (const permission of element.matchAll(/\bpermission:\s*([A-Za-z0-9_"./]+)/g)) {
        take(path, permission[1] ?? "");
      }
    }
  }
  return { codes, unresolved };
}

/**
 * The phrase keys a sentence still reads by itself: `permission: t("<key>")`, plain or chosen between
 * two, and `permission={t("<key>")}` where a page hands the phrase to a wrapper of its own.
 */
function phrasesReadByKey(): string[] {
  const keys = new Set<string>();
  for (const { text } of PRODUCT) {
    for (const match of text.matchAll(/\bpermission(?::|=\{)\s*t\(([^()]*)\)/g)) {
      for (const key of (match[1] ?? "").matchAll(/"([^"]+)"/g)) {
        keys.add(key[1] ?? "");
      }
    }
  }
  return [...keys].sort();
}

describe("DG-FE-16 a sentence names a permission by its phrase and its code", () => {
  const phrased = phrasedPermissions();

  it("the phrases of the catalogue and the permissions the function names are one set", () => {
    const keys = Object.keys(CATALOGUE)
      .filter((key) => key.startsWith(PHRASE_PREFIX))
      .map((key) => key.slice(PHRASE_PREFIX.length));
    expect(phrased.length).toBeGreaterThan(0);
    expect([...phrased].sort()).toEqual(phrased);
    expect(keys.sort()).toEqual(phrased);
    // Each phrase carries the place of its code and spells none: the code comes from the constant.
    expect(
      keys.filter(
        (code) => !/^[a-z][^{}()]* \(\{code\}\)$/.test(CATALOGUE[`${PHRASE_PREFIX}${code}`] ?? ""),
      ),
    ).toEqual([]);
  });

  it("each is a permission the API's document names", () => {
    const document = documentPermissions();
    expect(document.size).toBeGreaterThan(30);
    expect(phrased.filter((code) => !document.has(code))).toEqual([]);
  });

  it("each is named by a sentence of the product, from a constant, and none is left without one", () => {
    const { codes, unresolved } = named();
    expect(unresolved).toEqual([]);
    expect([...codes].sort()).toEqual(phrased);
  });

  it("no sentence of the catalogue spells a permission's phrase or code of its own", () => {
    const spelled = Object.entries(CATALOGUE)
      .filter(([key]) => !key.startsWith(PHRASE_PREFIX))
      .filter(
        ([, text]) =>
          (text.includes("a role that includes") && !text.includes("{permission}")) ||
          phrased.some((code) => text.includes(`(${code})`)),
      )
      .map(([key]) => key);
    expect(spelled).toEqual([]);
  });

  it("the sentences that still read a phrase by its key are those item 271 converts, and no other", () => {
    expect(phrasesReadByKey()).toEqual([...PHRASES_BY_KEY]);
    expect(PHRASES_BY_KEY.filter((key) => CATALOGUE[key] === undefined)).toEqual([]);
  });
});
