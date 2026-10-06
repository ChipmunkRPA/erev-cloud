// DG-FE-16 (docs/dev-guide.md §8.2, rev 1.175): the member's permissions are read in src/lib/access.ts
// only. `.includes` on `permissions` and any read of `permission_scopes` are reported in every other file
// of the product's source, except the files of the ratchet, which item W-12c converts family by family.
// The ratchet only shrinks: a listed file that no longer writes a bare gate must leave the list, and no
// file joins it. Lints as `make lint` does: from the repository root with --config frontend/eslint.config.js.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

const FRONTEND = fileURLToPath(new URL("..", import.meta.url));
/** The files not yet converted, as the configuration reads them. */
const BARE_PERMISSION_GATES = JSON.parse(
  readFileSync(resolve(FRONTEND, "config/bare-permission-gates.json"), "utf8"),
) as readonly string[];
const eslint = new ESLint({
  cwd: resolve(FRONTEND, ".."),
  overrideConfigFile: resolve(FRONTEND, "eslint.config.js"),
});

/** The ratchet as item W-12a left it. A file is removed here never, and added never. */
const INITIAL: readonly string[] = [
  "src/lib/api/queries/audit.ts",
  "src/lib/api/queries/reports.ts",
  "src/routes/approvals/delegations.tsx",
  "src/routes/approvals/toolbar.tsx",
  "src/routes/close/close-run.tsx",
  "src/routes/close/cockpit.tsx",
  "src/routes/close/history.tsx",
  "src/routes/close/journal-preview.tsx",
  "src/routes/close/multi-entity.tsx",
  "src/routes/close/reconciliation.tsx",
  "src/routes/close/reconciliations.tsx",
  "src/routes/contracts/draft-form.tsx",
  "src/routes/contracts/list.tsx",
  "src/routes/contracts/modification-detail.tsx",
  "src/routes/contracts/modification-wizard.tsx",
  "src/routes/contracts/obligation-pane.tsx",
  "src/routes/contracts/tabs/history.tsx",
  "src/routes/contracts/tabs/journals.tsx",
  "src/routes/contracts/tabs/modifications.tsx",
  "src/routes/contracts/tabs/schedules.tsx",
  "src/routes/contracts/workbench.tsx",
  "src/routes/data/exceptions.tsx",
  "src/routes/data/import-detail.tsx",
  "src/routes/data/import-new.tsx",
  "src/routes/data/imports.tsx",
  "src/routes/data/integration-connection.tsx",
  "src/routes/data/integrations.tsx",
  "src/routes/data/migration-detail.tsx",
  "src/routes/data/sync-run.tsx",
  "src/routes/data/templates.tsx",
  "src/routes/developer/developer.tsx",
  "src/routes/evidence/audit-log.tsx",
  "src/routes/evidence/event-drawer.tsx",
  "src/routes/evidence/verification.tsx",
  "src/routes/home/home.tsx",
  "src/routes/journals/entries.tsx",
  "src/routes/journals/journal-runs.tsx",
  "src/routes/journals/run-batches.tsx",
  "src/routes/journals/run.tsx",
  "src/routes/policies/account-mapping-version.tsx",
  "src/routes/policies/account-mapping.tsx",
  "src/routes/policies/accounting-version.tsx",
  "src/routes/policies/accounting.tsx",
  "src/routes/policies/revenue.tsx",
  "src/routes/policies/rule-set-version.tsx",
  "src/routes/policies/ssp-book-version.tsx",
  "src/routes/policies/ssp-books.tsx",
  "src/routes/policies/ssp-calculator-run.tsx",
  "src/routes/policies/ssp-calculator.tsx",
  "src/routes/policies/template-version.tsx",
  "src/routes/reports/frame.tsx",
  "src/routes/reports/report.tsx",
  "src/routes/reports/run.tsx",
  "src/routes/schedules/schedules.tsx",
  "src/routes/settings/calendars.tsx",
  "src/routes/settings/chart-of-accounts.tsx",
  "src/routes/settings/currencies.tsx",
  "src/routes/settings/customer.tsx",
  "src/routes/settings/customers.tsx",
  "src/routes/settings/entities.tsx",
  "src/routes/settings/index.tsx",
  "src/routes/settings/product.tsx",
  "src/routes/settings/products.tsx",
  "src/routes/settings/related-party-groups.tsx",
  "src/routes/settings/setup.tsx",
  "src/routes/settings/workspace.tsx",
];

const BARE_GATES = `interface Me {
  readonly permissions: readonly string[];
  readonly permission_scopes: Readonly<Record<string, "*" | readonly string[]>>;
}
export function gates(me: Me, data: { me?: Me }, permissions: readonly string[]): boolean[] {
  return [
    me.permissions.includes("contract.create"),
    data.me?.permissions.includes("contract.create") === true,
    permissions.includes("contract.create"),
    me.permission_scopes["contract.create"] === "*",
  ];
}
`;
// A role's own permissions, a rule's functions and a set are not the member's permissions.
const OTHER_LISTS = `export function other(
  role: { permissions: readonly string[] },
  held: ReadonlySet<string>,
  codes: readonly string[],
): boolean {
  return role.permissions.some((code) => held.has(code)) && codes.includes("contract.create");
}
`;

async function reported(path: string, code: string): Promise<string[]> {
  const [result] = await eslint.lintText(code, { filePath: resolve(FRONTEND, path) });
  expect(result?.messages.filter((message) => message.fatal === true)).toEqual([]);
  return (result?.messages ?? []).map((message) => `${String(message.ruleId)}: ${message.message}`);
}

const ACCESS_RULE =
  "no-restricted-syntax: The member's permissions are read in src/lib/access.ts: ask holds, holdsAnywhere, holdsForAll or holdsForEvery for the entities a permission covers (DG-FE-16).";

describe("DG-FE-16 the member's permissions are read in one file", () => {
  it("reports `.includes` on the member's permissions and a read of `permission_scopes`", async () => {
    for (const path of ["src/routes/zz/a.tsx", "src/components/form/a.tsx", "src/lib/api/a.ts"]) {
      expect(await reported(path, BARE_GATES), path).toEqual([
        ACCESS_RULE,
        ACCESS_RULE,
        ACCESS_RULE,
        ACCESS_RULE,
      ]);
    }
  }, 30_000);

  it("leaves other lists alone", async () => {
    expect(await reported("src/routes/zz/a.tsx", OTHER_LISTS)).toEqual([]);
  }, 30_000);

  it("allows them in src/lib/access.ts, in a test and in the test helpers", async () => {
    for (const path of ["src/lib/access.ts", "src/routes/zz/a.test.tsx", "src/test/app.tsx"]) {
      expect(await reported(path, BARE_GATES), path).toEqual([]);
    }
  }, 30_000);

  it("does not reach the e2e suite", async () => {
    expect(await reported("e2e/support/a.ts", BARE_GATES)).toEqual([]);
  }, 30_000);

  it("the ratchet only shrinks: no file has joined it", () => {
    expect(BARE_PERMISSION_GATES.filter((file) => !INITIAL.includes(file))).toEqual([]);
    expect(new Set(BARE_PERMISSION_GATES).size).toBe(BARE_PERMISSION_GATES.length);
  });

  it("the ratchet only shrinks: a listed file still writes a bare gate, else it leaves the list", async () => {
    const converted: string[] = [];
    for (const file of BARE_PERMISSION_GATES) {
      // Linted under a name outside the list, the file's own gates are reported.
      const source = readFileSync(resolve(FRONTEND, file), "utf8");
      const extension = file.endsWith(".tsx") ? "tsx" : "ts";
      const messages = await reported(`src/routes/zz/ratchet.${extension}`, source);
      if (!messages.includes(ACCESS_RULE)) {
        converted.push(file);
      }
    }
    expect(converted, "remove these from frontend/config/bare-permission-gates.json").toEqual([]);
  }, 240_000);
});
