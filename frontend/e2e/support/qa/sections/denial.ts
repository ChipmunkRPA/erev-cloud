// Section M of the pass: denial, per member, read against the permission catalogue. The catalogue
// is the committed API document (docs/api/openapi.json): every operation names the permission its
// route asks (`x-erev-permission`, 04 API-C-03). For each member, every operation whose permission
// she does not hold is sent — a read as it is, a command with an empty body — and must be refused
// 403 before anything else is looked at; one screen per area she holds no permission for must show
// the access-limited state (SCREENS SCR-PERM-01); and a command of a page she can open is offered
// to her only with its permission (SCR-PERM-02; PRD BR-UX-05).
import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { join } from "node:path";

import type { Page } from "@playwright/test";

import { Api, type Got, items, said } from "../api";
import type { Qa } from "../fixtures";
import { open } from "../observe";
import { flat, type Outcome } from "../record";
import { readRouter, readScreenRows, screenRowOf } from "../../routes";
import { type Member, MEMBERS } from "../sessions";
import { dismissToasts } from "../steps";
import { REPO_ROOT } from "../../tenants";
import { BOOK, SEPTEMBER } from "../world";
import { HOME_ENTITY } from "./member";

interface Operation {
  readonly method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  readonly path: string;
  readonly permission: string;
}

const METHODS = ["get", "post", "put", "patch", "delete"] as const;

/** The operations of the API document that name one permission. */
export function readOperations(): readonly Operation[] {
  const document = JSON.parse(
    readFileSync(join(REPO_ROOT, "docs", "api", "openapi.json"), "utf8"),
  ) as {
    readonly paths: Readonly<
      Record<string, Readonly<Record<string, Readonly<Record<string, unknown>>>>>
    >;
  };
  const found: Operation[] = [];
  for (const [path, operations] of Object.entries(document.paths)) {
    for (const method of METHODS) {
      const permission = operations[method]?.["x-erev-permission"];
      if (typeof permission === "string" && permission !== "") {
        found.push({ method: method.toUpperCase() as Operation["method"], path, permission });
      }
    }
  }
  if (found.length === 0) {
    throw new Error("docs/api/openapi.json names no operation with x-erev-permission");
  }
  return found;
}

/** The path with every parameter filled by a value that names nothing. */
function concrete(path: string): string {
  return path.replace(/\{([a-z_]+)\}/g, (_, name: string) =>
    name.endsWith("_no") ? "1" : name === "object_type" ? "contract" : randomUUID(),
  );
}

function twoHundred(got: Got): boolean {
  return got.status >= 200 && got.status < 300;
}

/** Every operation whose permission the member lacks, as her session is answered it. */
async function matrix(
  api: Api,
  held: ReadonlySet<string>,
  operations: readonly Operation[],
): Promise<Outcome> {
  const lacking = operations.filter((operation) => !held.has(operation.permission));
  const accepted: string[] = [];
  const other = new Map<string, string[]>();
  let refused = 0;
  for (const operation of lacking) {
    const path = concrete(operation.path);
    const ask = () =>
      operation.method === "GET" ? api.get(path) : api.send(operation.method, path, {});
    let got = await ask();
    // The guard of a permission answers 403 forbidden and nothing else (04 API-C-03). A 403 of
    // another kind — a factor asked for, a session refused — is not that answer and is listed.
    if (got.status === 403 && got.problem === "forbidden") {
      refused += 1;
      continue;
    }
    const name = `${operation.method} ${operation.path.replace("/api/v1", "")} (${operation.permission})`;
    if (twoHundred(got)) {
      // A candidate: sent a second time before it is written.
      got = await ask();
      if (twoHundred(got)) {
        accepted.push(`${name} → ${said(got)} "${flat(got.text, 120)}"`);
        continue;
      }
    }
    const answer = said(got);
    other.set(answer, [...(other.get(answer) ?? []), name]);
  }
  const permissions = new Set(lacking.map((operation) => operation.permission));
  const rest = [...other.entries()].map(
    ([answer, names]) =>
      `${answer} × ${String(names.length)} (${names.slice(0, 3).join("; ")}${names.length > 3 ? "; …" : ""})`,
  );
  const summary = `${String(lacking.length)} operations of the ${String(permissions.size)} permissions she lacks: 403 forbidden × ${String(refused)}${rest.length === 0 ? "" : `; ${rest.join("; ")}`}`;
  if (accepted.length > 0) {
    return {
      observed: `ANSWERED WITHOUT THE PERMISSION, twice: ${accepted.slice(0, 10).join(" | ")}${accepted.length > 10 ? ` | and ${String(accepted.length - 10)} more` : ""}. ${summary}`,
      result: "FINDING",
      finding: "bound",
    };
  }
  return other.size === 0
    ? { observed: `${summary}; she holds ${String(held.size)} permissions`, result: "pass" }
    : {
        observed: `nothing is answered with content; not every refusal is a 403 forbidden. ${summary}`,
        result: "seen once",
      };
}

/** The area of a route: the first segment of its path. */
function areaOf(path: string): string {
  return path.split("/")[1] ?? "";
}

/** One screen per area the member holds no permission for: each must be access-limited. */
async function screens(
  page: Page,
  held: ReadonlySet<string>,
  parked: (line: string) => void,
): Promise<Outcome> {
  const rows = readScreenRows();
  const chosen = new Map<
    string,
    { readonly address: string; readonly permissions: readonly string[] }
  >();
  for (const route of readRouter()) {
    const row = screenRowOf(route, rows);
    if (row === undefined || row.permissions.length === 0 || route.path === "*") {
      continue;
    }
    const area = areaOf(route.path);
    if (row.permissions.some((code) => held.has(code)) || chosen.has(area)) {
      continue;
    }
    const address = route.path
      .replace(":entity", HOME_ENTITY)
      .replace(":book", BOOK)
      .replace(":period", SEPTEMBER)
      .replace(":reportCode", "revenue_waterfall")
      .replace(":dashboardCode", "revenue")
      .replace(":step", "review")
      .replace(/:[A-Za-z]+/g, () => randomUUID());
    chosen.set(area, { address, permissions: row.permissions });
  }
  const shown: string[] = [];
  const open2: string[] = [];
  for (const { address, permissions } of chosen.values()) {
    const seen = await open(page, address);
    const line = `${address.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, "<id>")} (${permissions.join(" or ")}) → ${seen.state} "${seen.heading}"`;
    shown.push(line);
    if (seen.state !== "access-limited") {
      open2.push(line);
    }
    await dismissToasts(page);
  }
  if (chosen.size === 0) {
    return {
      observed: "she holds a permission of every area's routes: no screen to refuse",
      result: "pass",
    };
  }
  // A screen that renders without its permission shows what its reads are answered, and every
  // operation of a permission she lacks is asked in M-1: what crosses a bound is found there. The
  // screen's own state is outside the three classes: one parked line each.
  const rendered = open2.filter((line) => line.includes("→ rendered"));
  for (const line of rendered) {
    parked(`the screen renders where SCR-PERM-01 states the access-limited state: ${line}`);
  }
  if (rendered.length > 0) {
    return {
      observed: `rendered without the permission of its SCREENS row (parked lines; the operations behind are M-1's): ${rendered.join(" | ")}. All: ${shown.join("; ")}`,
      result: "seen once",
      page,
    };
  }
  return open2.length === 0
    ? {
        observed: `${String(chosen.size)} screens, one per area she lacks, all access-limited: ${shown.join("; ")}`,
        result: "pass",
      }
    : {
        observed: `not rendered, but not the access-limited state either: ${open2.join(" | ")}. All: ${shown.join("; ")}`,
        result: "seen once",
        page,
      };
}

/** Commands of pages most members can open: the control and the permission the API asks for it. */
const PAGE_COMMANDS = [
  {
    address: `/contracts?entity=${HOME_ENTITY}&period=${SEPTEMBER}&book=${BOOK}`,
    read: "contract.read",
    command: "New contract",
    permission: "contract.create",
  },
  {
    address: `/journals?entity=${HOME_ENTITY}&period=${SEPTEMBER}&book=${BOOK}`,
    read: "contract.read",
    command: "Run journals",
    permission: "journal.run",
  },
  {
    address: "/data/imports",
    read: "contract.read",
    command: "New import",
    permission: "import.upload",
  },
  {
    address: `/close/${HOME_ENTITY}/${BOOK}/${SEPTEMBER}`,
    read: "contract.read",
    command: "Start soft close",
    permission: "period.close",
  },
  {
    address: `/close/${HOME_ENTITY}/${BOOK}/${SEPTEMBER}/reconciliations`,
    read: "contract.read",
    command: "Generate reconciliation",
    permission: "recon.prepare",
  },
] as const;

async function commands(
  page: Page,
  held: ReadonlySet<string>,
  parked: (line: string) => void,
): Promise<Outcome> {
  const lines: string[] = [];
  const offered: string[] = [];
  const missing: string[] = [];
  for (const item of PAGE_COMMANDS) {
    if (!held.has(item.read)) {
      continue;
    }
    const seen = await open(page, item.address);
    const count =
      (await page.getByRole("button", { name: item.command, exact: true }).count()) +
      (await page.getByRole("link", { name: item.command, exact: true }).count());
    const holds = held.has(item.permission);
    lines.push(
      `"${item.command}" (${item.permission}, ${holds ? "held" : "not held"}): ${count > 0 ? "offered" : "absent"}`,
    );
    if (!holds && count > 0) {
      offered.push(`"${item.command}" on ${item.address} without ${item.permission}`);
    }
    if (holds && count === 0) {
      missing.push(`"${item.command}" on ${item.address} (${seen.state} "${seen.heading}")`);
    }
    await dismissToasts(page);
  }
  if (lines.length === 0) {
    return {
      observed: "she reads none of the pages of the check (no contract.read)",
      result: "pass",
    };
  }
  // A command offered without its permission is refused by the API (M-1 asks it): the control is
  // outside the three classes, one parked line each.
  for (const line of offered) {
    parked(`a command is offered where SCR-PERM-02 hides it: ${line}`);
  }
  if (offered.length > 0) {
    return {
      observed: `offered without the permission (parked lines; the API's answer is M-1's): ${offered.join(" | ")}. ${lines.join("; ")}`,
      result: "seen once",
      page,
    };
  }
  return missing.length === 0
    ? { observed: lines.join("; "), result: "pass" }
    : {
        observed: `a command she holds the permission for is not on its page: ${missing.join(" | ")}. ${lines.join("; ")}`,
        result: "seen once",
        page,
      };
}

export async function denialSection(
  { record, sessions }: Qa,
  members: readonly Member[] = MEMBERS,
): Promise<void> {
  const operations = readOperations();
  for (const member of members) {
    let page: Page;
    try {
      page = await sessions.page(member);
    } catch (error) {
      record.row({
        check: "M denial",
        persona: member,
        address: "every check of the section",
        expected: "04 API-C-03; SCREENS SCR-PERM-01, SCR-PERM-02",
        observed: `the member could not sign in: ${error instanceof Error ? flat(error.message, 300) : String(error)}`,
        result: "not run",
      });
      continue;
    }
    const api = new Api(page);
    const me = (await api.get("/api/v1/me")).json;
    const held = new Set(items(me, "permissions").map(String));
    await record.check(
      {
        check: "M-1 every operation of a permission she lacks",
        persona: member,
        address: "the API document's operations with x-erev-permission",
        expected:
          "403 forbidden for each, before the body or the record is looked at (04 API-C-03 'Each route declares one permission code'; PRD BR-UX-05); nothing is answered and nothing is done",
      },
      () => matrix(api, held, operations),
    );
    await record.check(
      {
        check: "M-2 one screen per area she holds no permission for",
        persona: member,
        address: "the first route of each area in SCREENS §0.4 whose permission she lacks",
        expected:
          'The access-limited state "You do not have access to <area>" and no read of the page answered (SCREENS SCR-PERM-01)',
      },
      () => screens(page, held, (line) => record.parked(member, "M-2", line)),
    );
    await record.check(
      {
        check: "M-3 the commands of pages she can open",
        persona: member,
        address: `Contracts, Journals, Imports and the Close of ${HOME_ENTITY}`,
        expected:
          "A command is offered with its permission and absent without it (SCREENS SCR-PERM-02; PRD BR-UX-05 'Screens show only actions the user may perform')",
      },
      () => commands(page, held, (line) => record.parked(member, "M-3", line)),
    );
  }
}
