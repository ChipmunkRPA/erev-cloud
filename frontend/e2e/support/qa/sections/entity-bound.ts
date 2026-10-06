// Section K of the pass: the entity bound, as the member for AVM-DE alone (03 REQ-PLT-012; PRD
// BR-UX-06: "An object outside the user's entity scope is 'not found' in the UI and 404 in the
// API"). A reader of every entity (maya) names one record of each kind in an entity the member does
// not cover; the member then asks for it through the API, by a typed address and through commands,
// and every screen she can open is read for a name of such a record. The rule the checks hold the
// product to is the document's own: an id of another entity is answered exactly as an id that names
// nothing. A read that is answered with content, and a command that is accepted, are candidates of
// class 2; each is asked a second time before its row says FINDING.
import { randomUUID } from "node:crypto";

import type { Page } from "@playwright/test";

import { Api, at, type Got, items, said, text } from "../api";
import type { Qa } from "../fixtures";
import {
  failuresText,
  type Foreign,
  foreignHits,
  hitsText,
  open,
  type Seen,
  wordAt,
} from "../observe";
import { flat, type Outcome } from "../record";
import { readRouter, readScreenRows, screenRowOf } from "../../routes";
import { LENA } from "../sessions";
import { dismissToasts } from "../steps";
import {
  AUGUST,
  BOOK,
  type Entity,
  type EntityWorld,
  makeWaterfallRun,
  periodId,
  type Probe,
  readEntities,
  readEntityWorld,
  reportRows,
  SEPTEMBER,
  unknownOf,
} from "../world";
import { HOME_ENTITY, pillOptions, pillText } from "./member";

/** The entity whose records the member asks to read, and the one her commands are sent against. */
const READ_ENTITY = "AVM-US";
const COMMAND_ENTITY = "AVM-UK";
/** A code in the form of an entity code that names none. */
const NO_ENTITY = "AVM-ZZ";

/** Lists of records that belong to one entity (04 RLS-TE), by their API path. */
const ENTITY_LISTS: readonly { readonly path: string; readonly params?: Record<string, string> }[] =
  [
    { path: "/api/v1/contracts" },
    { path: "/api/v1/journal-runs" },
    { path: "/api/v1/close-runs" },
    { path: "/api/v1/reconciliations" },
    { path: "/api/v1/exceptions" },
    { path: "/api/v1/manual-adjustments" },
    { path: "/api/v1/periods", params: { book: BOOK } },
    {
      path: "/api/v1/schedule-lines",
      params: { book: BOOK, from_period: AUGUST, to_period: SEPTEMBER },
    },
    { path: "/api/v1/subledger-lines", params: { book: BOOK, period: AUGUST } },
    // A judgement record names its contract, not an entity: it is judged by its contract's.
    { path: "/api/v1/judgements" },
  ];

/** Routes the pass does not open as a signed-in member: the sign-in surface and the design gallery. */
const NOT_A_SCREEN = new Set([
  "/sign-in",
  "/sign-in/mfa",
  "/mfa/enrol",
  "/accept-invitation",
  "/password/reset",
  "/password/reset/confirm",
  "/select-workspace",
  "/design",
]);

/** Screens that read the context of the address (SCREENS §1.3): asked again with another entity in it. */
const CONTEXT_SCREENS = [
  "/home",
  "/contracts",
  "/schedules",
  "/close",
  "/journals",
  "/journals/entries",
  "/reports",
  "/reports/revenue_waterfall",
  "/reports/contract_balances",
  "/reports/rpo",
  "/reports/dashboards/revenue",
  "/data/exceptions",
  "/data/imports",
  "/search?q=BG-AVM",
];

interface Worlds {
  readonly entities: readonly Entity[];
  readonly own: EntityWorld;
  readonly read: EntityWorld;
  readonly command: EntityWorld;
  /** Every id, external id and number of a contract outside the member's entity. */
  readonly contractWords: readonly string[];
  /** The codes and names of the entities outside her scope. */
  readonly entityWords: readonly string[];
  /** The entity of each contract a reader of every entity lists, by the contract's id. */
  readonly contractEntity: ReadonlyMap<string, string>;
}

function twoHundred(got: Got): boolean {
  return got.status >= 200 && got.status < 300;
}

/** Whether a 2xx answer holds anything: a list with items, or a record. */
function holdsContent(got: Got): boolean {
  if (!twoHundred(got)) {
    return false;
  }
  const listed = at(got.json, "items");
  if (Array.isArray(listed)) {
    return listed.length > 0;
  }
  return got.text.trim() !== "" && got.text.trim() !== "{}" && got.text.trim() !== "[]";
}

async function readWorlds(maya: Api): Promise<Worlds> {
  const entities = await readEntities(maya);
  const find = (code: string): Entity => {
    const entity = entities.find((item) => item.code === code);
    if (entity === undefined) {
      throw new Error(`GET /entities lists no ${code} for a reader of every entity`);
    }
    return entity;
  };
  const own = await readEntityWorld(maya, find(HOME_ENTITY));
  let read = await readEntityWorld(maya, find(READ_ENTITY));
  const command = await readEntityWorld(maya, find(COMMAND_ENTITY));
  // A report run over the entity, made by a member who covers it (04 API-R-41).
  const run = await makeWaterfallRun(maya, [READ_ENTITY], AUGUST, AUGUST);
  if (run.id !== "") {
    const reportRun: Probe = {
      kind: "report run",
      label: `revenue_waterfall ${READ_ENTITY} ${AUGUST}`,
      reads: [
        `/api/v1/report-runs/${run.id}`,
        `/api/v1/report-runs/${run.id}/data`,
        `/api/v1/report-runs/${run.id}/output`,
      ],
      screens: [
        `/reports/runs/${run.id}`,
        `/reports/revenue_waterfall?entity=${READ_ENTITY}&period=${AUGUST}&book=${BOOK}&run=${run.id}`,
        `/schedules?entity=${READ_ENTITY}&period=${AUGUST}&book=${BOOK}&run=${run.id}`,
      ],
      words: [run.id],
    };
    read = { ...read, probes: [...read.probes, reportRun] };
  }
  const outside = entities.filter((entity) => entity.code !== HOME_ENTITY);
  const contractWords: string[] = [];
  const contractEntity = new Map<string, string>(
    own.contracts.map((contract) => [contract.id, HOME_ENTITY]),
  );
  for (const entity of outside) {
    const world =
      entity.code === READ_ENTITY
        ? read
        : entity.code === COMMAND_ENTITY
          ? command
          : await readEntityWorld(maya, entity);
    for (const contract of world.contracts) {
      contractWords.push(contract.id, contract.externalId, contract.contractNo);
      contractEntity.set(contract.id, entity.code);
    }
  }
  // A key a contract of her own entity carries too names nothing of another entity.
  const ownWords = new Set(
    own.contracts.flatMap((contract) => [contract.id, contract.externalId, contract.contractNo]),
  );
  return {
    entities,
    own,
    read,
    command,
    contractWords: contractWords.filter((word) => word !== "" && !ownWords.has(word)),
    entityWords: outside.flatMap((entity) => [entity.code, entity.name, entity.id]),
    contractEntity,
  };
}

/**
 * The entity a list's item belongs to, by its code: every item of the lists of `ENTITY_LISTS` names
 * its entity (`entity`, `contracting_entity`, or `entity_id` for an exception item); null for an
 * item that names none.
 */
function entityOf(
  item: unknown,
  entities: readonly Entity[],
  contractEntity: ReadonlyMap<string, string>,
): string | null {
  const code = text(item, "entity", "code") || text(item, "contracting_entity", "code");
  if (code !== "") {
    return code;
  }
  const id = text(item, "entity_id");
  if (id !== "") {
    return entities.find((entity) => entity.id === id)?.code ?? id;
  }
  // A record that names a contract and no entity (a judgement record) is its contract's.
  return contractEntity.get(text(item, "contract_id")) ?? null;
}

function kindsText(world: EntityWorld): string {
  return `${world.entity.code}: ${String(world.contracts.length)} contracts; records of [${world.probes.map((probe) => probe.kind).join(", ")}]${world.absent.length === 0 ? "" : `; none of [${world.absent.join(", ")}]`}`;
}

/** The imports a reader of every entity lists and the member does not: uploads that name another entity. */
async function importProbes(
  maya: Api,
  lena: Api,
): Promise<{ readonly foreign: Probe | null; readonly own: Probe | null }> {
  const all = await maya.list("/api/v1/imports");
  const hers = new Set((await lena.list("/api/v1/imports")).map((item) => text(item, "id")));
  const probe = (item: unknown): Probe => {
    const id = text(item, "id");
    return {
      kind: "import",
      label: `${text(item, "import_no")} ${text(item, "file", "original_filename")}`,
      reads: [
        `/api/v1/imports/${id}`,
        `/api/v1/imports/${id}/rows`,
        `/api/v1/imports/${id}/diff`,
        ...(text(item, "file", "id") === "" ? [] : [`/api/v1/files/${text(item, "file", "id")}`]),
      ],
      screens: [`/data/imports/${id}/review`, `/data/imports/${id}/committed`],
      words: [id, text(item, "import_no")],
    };
  };
  const outside = all.find((item) => !hers.has(text(item, "id")));
  const inside = all.find((item) => hers.has(text(item, "id")));
  return {
    foreign: outside === undefined ? null : probe(outside),
    own: inside === undefined ? null : probe(inside),
  };
}

interface ReadResult {
  readonly path: string;
  readonly foreign: Got;
  readonly unknown: Got;
}

/** A read of another entity's record against the same read of an id that names nothing. */
async function askForeign(lena: Api, path: string): Promise<ReadResult> {
  return { path, foreign: await lena.get(path), unknown: await lena.get(unknownOf(path)) };
}

/** The reads of one entity's records, as the member is answered them. */
async function readsCheck(
  lena: Api,
  world: EntityWorld,
  own: EntityWorld,
  extra: readonly Probe[],
  ownExtra: readonly Probe[],
): Promise<Outcome> {
  const probes = [...world.probes, ...extra];
  const controls = [...own.probes, ...ownExtra];
  const leaks: string[] = [];
  const oracles: string[] = [];
  const answers = new Map<string, number>();
  let asked = 0;
  for (const probe of probes) {
    for (const path of probe.reads) {
      asked += 1;
      const first = await askForeign(lena, path);
      answers.set(said(first.foreign), (answers.get(said(first.foreign)) ?? 0) + 1);
      if (holdsContent(first.foreign)) {
        // A candidate: asked a second time before it is written.
        const second = await lena.get(path);
        if (holdsContent(second)) {
          leaks.push(
            `${probe.kind} ${probe.label}: GET ${path} → ${said(second)} with content ("${flat(second.text, 160)}")`,
          );
        }
        continue;
      }
      if (said(first.foreign) !== said(first.unknown)) {
        oracles.push(
          `${probe.kind}: GET ${path} → ${said(first.foreign)}, an id that names nothing → ${said(first.unknown)}`,
        );
      }
    }
  }
  // The control: the same kinds of her own entity are readable, so a 404 above is the bound and not
  // a permission she lacks.
  const unread: string[] = [];
  let readable = 0;
  for (const probe of controls) {
    const [path] = probe.reads;
    if (path === undefined) {
      continue;
    }
    const got = await lena.get(path);
    if (twoHundred(got)) {
      readable += 1;
    } else {
      unread.push(`${probe.kind} (${said(got)})`);
    }
  }
  const summary = `${String(asked)} reads of ${String(probes.length)} kinds of ${world.entity.code} records [${probes.map((probe) => probe.kind).join(", ")}]: answers ${[...answers.entries()].map(([answer, count]) => `${answer} × ${String(count)}`).join(", ")}; control: ${String(readable)} of ${String(controls.length)} kinds of her own ${own.entity.code} records read${unread.length === 0 ? "" : `, not read: ${unread.join(", ")}`}${world.absent.length === 0 ? "" : `; the world holds no ${world.absent.join(", ")} for ${world.entity.code}`}`;
  if (leaks.length > 0) {
    return {
      observed: `ANSWERED WITH CONTENT, twice: ${leaks.slice(0, 10).join(" | ")}${leaks.length > 10 ? ` | and ${String(leaks.length - 10)} more` : ""}. ${summary}`,
      result: "FINDING",
      finding: "bound",
    };
  }
  if (oracles.length > 0) {
    return {
      observed: `no read is answered with content; ${String(oracles.length)} read(s) tell another entity's id from an id that names nothing: ${oracles.slice(0, 8).join(" | ")}. ${summary}`,
      result: "seen once",
    };
  }
  return {
    observed: `every read is answered as an id that names nothing is. ${summary}`,
    result: "pass",
  };
}

/** An amount other than zero in a body: `"amount": "12.50"`. */
const NON_ZERO = /"amount":\s*"-?(?!0+(?:\.0+)?")\d+(?:\.\d+)?"/;

async function listsCheck(lena: Api, maya: Api, worlds: Worlds): Promise<Outcome> {
  const lines: string[] = [];
  const leaks: string[] = [];
  const totals: string[] = [];
  const named = new Set<string>();
  /** A record of another entity in a body: a contract's id, key or number; where it stands. */
  const record = (body: string): string | null => {
    const word = worlds.contractWords.find((item) => wordAt(body, item) !== -1);
    if (word === undefined) {
      return null;
    }
    const at2 = wordAt(body, word);
    return `${word} ("${flat(body.slice(Math.max(0, at2 - 80), at2 + 80), 170)}")`;
  };
  for (const list of ENTITY_LISTS) {
    const params = list.params ?? {};
    const name = list.path.replace("/api/v1/", "");
    const head = await lena.get(list.path, { limit: 1, count: true, ...params });
    if (head.status !== 200) {
      lines.push(`${name}: ${said(head)}`);
      continue;
    }
    // Every page of the list without an entity: each item names its entity, which must be hers;
    // and no key of another entity's contract stands anywhere in it. Read twice before it is a leak.
    const outsideOf = (listed: readonly unknown[]) =>
      listed.filter((item) => {
        const code = entityOf(item, worlds.entities, worlds.contractEntity);
        return code !== null && code !== HOME_ENTITY;
      });
    let listed = await lena.list(list.path, params, 3_000);
    let outside = outsideOf(listed);
    let body = JSON.stringify(listed);
    let hit = record(body);
    if (outside.length > 0 || hit !== null) {
      listed = await lena.list(list.path, params, 3_000);
      outside = outsideOf(listed);
      body = JSON.stringify(listed);
      hit = record(body);
      if (outside.length > 0) {
        const codes = [
          ...new Set(
            outside.map((item) => entityOf(item, worlds.entities, worlds.contractEntity) ?? ""),
          ),
        ];
        leaks.push(
          `GET ${name} without an entity holds ${String(outside.length)} record(s) of [${codes.join(", ")}] ("${flat(JSON.stringify(outside[0]), 170)}")`,
        );
      } else if (hit !== null) {
        leaks.push(`GET ${name} without an entity holds ${hit}`);
      }
    }
    const unnamed = listed.filter(
      (item) => entityOf(item, worlds.entities, worlds.contractEntity) === null,
    ).length;
    for (const word of worlds.entityWords) {
      if (wordAt(body, word) !== -1) {
        named.add(`${word} in ${name}`);
      }
    }
    // "All entities" for her is her entities: the total of the list without an entity against the
    // total a reader of every entity gets for her entity. The two lists are not one definition — an
    // item that names no entity is in the first and not in the second — so a difference is said
    // and read by hand; a record of another entity is the leak above.
    const hers = head.headers["x-erev-total-count"];
    const expected = await maya.total(list.path, { ...params, entity: HOME_ENTITY });
    if (hers !== undefined && expected !== null && Number(hers) !== expected) {
      totals.push(
        `${name}: ${hers} for her, ${String(expected)} for ${HOME_ENTITY} as a reader of every entity${unnamed === 0 ? "" : ` (${String(unnamed)} of her items name no entity)`}`,
      );
    }
    // The same list asked for an entity she does not cover, and for a code that names none.
    const other = await lena.get(list.path, { limit: 200, ...params, entity: READ_ENTITY });
    const none = await lena.get(list.path, { limit: 200, ...params, entity: NO_ENTITY });
    let asked = `?entity=${READ_ENTITY} → ${said(other)}`;
    if (twoHundred(other)) {
      const count = items(other.json).length;
      const theirs = outsideOf(items(other.json)).length;
      asked += ` (${String(count)} items${count > 0 && theirs === 0 ? ", none of another entity: the filter is not applied" : ""})`;
      if (theirs > 0) {
        const again = await lena.get(list.path, { limit: 200, ...params, entity: READ_ENTITY });
        const still = outsideOf(items(again.json));
        if (still.length > 0) {
          leaks.push(
            `GET ${name}?entity=${READ_ENTITY} → ${said(again)} with ${String(still.length)} record(s) of another entity ("${flat(JSON.stringify(still[0]), 170)}")`,
          );
        }
      }
    }
    lines.push(
      `${name}: ${hers ?? "no total"} for her; ${asked}, ?entity=${NO_ENTITY} → ${said(none)}`,
    );
  }
  // The search (04 API-R-47) and Home's figures for an entity of the address.
  const [contract] = worlds.read.contracts;
  if (contract !== undefined) {
    const found = await lena.get("/api/v1/search", { q: contract.externalId, limit: 20 });
    const names =
      wordAt(found.text, contract.id) !== -1 || wordAt(found.text, contract.externalId) !== -1;
    if (twoHundred(found) && names) {
      leaks.push(`GET search?q=${contract.externalId} names the ${READ_ENTITY} contract`);
    }
    lines.push(
      `search?q=${contract.externalId} → ${said(found)}${names ? ", naming it" : ", naming nothing of it"}`,
    );
  }
  const context = { period: AUGUST, book: BOOK };
  const home = await lena.get("/api/v1/dashboard/home", { ...context, entity: READ_ENTITY });
  const noHome = await lena.get("/api/v1/dashboard/home", { ...context, entity: NO_ENTITY });
  if (twoHundred(home) && NON_ZERO.test(home.text)) {
    const again = await lena.get("/api/v1/dashboard/home", { ...context, entity: READ_ENTITY });
    if (twoHundred(again) && NON_ZERO.test(again.text)) {
      leaks.push(
        `GET dashboard/home?entity=${READ_ENTITY} → ${said(again)} with figures ("${flat(again.text, 200)}")`,
      );
    }
  }
  lines.push(
    `dashboard/home?entity=${READ_ENTITY} → ${said(home)}${twoHundred(home) && !NON_ZERO.test(home.text) ? " without a figure" : ""}, ?entity=${NO_ENTITY} → ${said(noHome)}`,
  );
  const summary = `${lines.join("; ")}${named.size === 0 ? "" : `; a code, name or id of another entity stands in: ${[...named].slice(0, 10).join(", ")}`}`;
  if (leaks.length > 0) {
    return { observed: `${leaks.join(" | ")}. ${summary}`, result: "FINDING", finding: "bound" };
  }
  if (totals.length > 0) {
    return {
      observed: `no record of another entity is listed; a total without an entity is not the total asked for her entity: ${totals.join(" | ")}. ${summary}`,
      result: "seen once",
    };
  }
  return { observed: summary, result: named.size === 0 ? "pass" : "seen once" };
}

/** 04 T-PLT-10: the rule a refusal names where a member's own access does not cover what she asks. */
const OWN_SCOPE_RULE = "T-PLT-10";
const WORKSPACE_FORM = "/settings/workspace";

interface PolicyItem {
  readonly sent: { readonly what: string; readonly got: Got; readonly none?: Got }[];
  /** A refusal that is not the one the rule names, and a control that was not taken. */
  readonly unproven: string[];
  /** What the control left in the world, and what SF-15 shows her. */
  readonly said: string;
}

/**
 * Register index 291 (the supervisor's word of 2026-10-03): authority over a policy version across
 * the entity bound. Her role holds `config.author` for her entity alone (PRD BR-UX-06; 04 T-PLT-10).
 * A version of TENANT or of BOOK scope applies to every entity: refused 403 by name. A version of
 * ENTITY scope for an entity her session does not read: answered as for a code that names nothing.
 * And the control, without which the refusals prove nothing: a version of ENTITY scope for her own
 * entity is taken. Each version states one registry parameter at its default, so that no figure
 * could move even if a version were published; a draft has no command that removes it, so the
 * control's draft stays in her entity and the row says so.
 */
async function policyVersions(lena: Api, page: Page, other: string): Promise<PolicyItem> {
  const sent: { what: string; got: Got; none?: Got }[] = [];
  const unproven: string[] = [];
  const levels = (item: unknown) => items(item, "allowed_levels").map(String);
  const candidates = (await lena.list("/api/v1/registry/parameters", {}, 2_000)).filter(
    (item) =>
      levels(item).includes("ENTITY") &&
      levels(item).includes("TENANT") &&
      typeof at(item, "default_asc606") === "string" &&
      at(item, "is_forced_asc606") !== true,
  );
  const body = (parameter: unknown, scope: Record<string, unknown>) => ({
    category: text(parameter, "category"),
    values: { [text(parameter, "code")]: at(parameter, "default_asc606") },
    ...scope,
  });
  const own = { scope: "ENTITY", entity_code: HOME_ENTITY };
  // The control first: it finds a statement the API takes for a version of ENTITY scope. A version
  // of an earlier round of the pass on this world still holds its key and stands for the control.
  const standing = (await lena.list("/api/v1/policies", { entity: HOME_ENTITY })).find(
    (item) =>
      text(item, "scope") === "ENTITY" &&
      text(item, "entity_code") === HOME_ENTITY &&
      ["DRAFT", "TESTED"].includes(text(item, "status")),
  );
  let chosen: unknown = candidates.find(
    (item) => text(item, "category") === text(standing, "category"),
  );
  let control = "";
  if (standing !== undefined && chosen !== undefined) {
    control = `the control stood already: version ${text(standing, "version_no")} of ${text(standing, "category")} for ${HOME_ENTITY} is ${text(standing, "status")}, of an earlier round of the pass`;
  } else {
    chosen = undefined;
    const tried: string[] = [];
    for (const parameter of candidates.slice(0, 6)) {
      const got = await lena.send("POST", "/api/v1/policies", body(parameter, own));
      tried.push(`${text(parameter, "code")} → ${said(got)}`);
      if (got.status === 201) {
        chosen = parameter;
        control = `the control: POST policies of ENTITY scope for ${HOME_ENTITY}, stating ${text(parameter, "code")} at its default "${text(parameter, "default_asc606")}" → 201, version ${text(got.json, "version_no")} of ${text(got.json, "category")}, ${text(got.json, "status")}; a draft has no command that removes it: it stays in ${HOME_ENTITY}, unpublished, and states the default`;
        break;
      }
    }
    if (chosen === undefined) {
      unproven.push(
        `the control was not taken: POST policies of ENTITY scope for ${HOME_ENTITY} → ${tried.join(", ") || "no parameter of ENTITY level with a default is listed"}`,
      );
      chosen = candidates[0];
    }
  }
  if (chosen === undefined) {
    return { sent, unproven, said: "no policy command was sent" };
  }
  const byName = (got: Got): boolean =>
    got.status === 403 &&
    got.problem === "forbidden" &&
    items(got.json, "errors").some((error) => text(error, "rule_id") === OWN_SCOPE_RULE);
  for (const [what, scope] of [
    ["POST policies of TENANT scope", { scope: "TENANT" }],
    ["POST policies of BOOK scope", { scope: "BOOK", book: BOOK }],
  ] as const) {
    const got = await lena.send("POST", "/api/v1/policies", body(chosen, scope));
    sent.push({ what, got });
    if (!twoHundred(got) && !byName(got)) {
      unproven.push(
        `${what} → ${said(got)} "${flat(text(got.json, "detail"), 120)}": not the refusal by rule ${OWN_SCOPE_RULE}`,
      );
    }
  }
  sent.push({
    what: `POST policies of ENTITY scope for ${other}`,
    got: await lena.send(
      "POST",
      "/api/v1/policies",
      body(chosen, { scope: "ENTITY", entity_code: other }),
    ),
    none: await lena.send(
      "POST",
      "/api/v1/policies",
      body(chosen, { scope: "ENTITY", entity_code: NO_ENTITY }),
    ),
  });
  // SF-15, where a workspace's version is written: what the form gives her. A radio group is one
  // control and carries the mark for its radios, which have none of their own.
  const seen = await open(page, WORKSPACE_FORM);
  const form = page.getByTestId("SF-15-workspace-form");
  const fields = await form
    .locator(
      'input:not([type="hidden"]):not([type="radio"]), textarea, [role="combobox"], [role="radiogroup"]',
    )
    .evaluateAll((elements) => ({
      all: elements.length,
      readOnly: elements.filter(
        (element) =>
          element.hasAttribute("readonly") ||
          element.getAttribute("aria-readonly") === "true" ||
          element.getAttribute("aria-disabled") === "true" ||
          (element as HTMLInputElement).disabled,
      ).length,
    }))
    .catch(() => ({ all: 0, readOnly: 0 }));
  const submit = await page.getByRole("button", { name: "Submit for approval" }).count();
  const formSaid = `${WORKSPACE_FORM} is ${seen.state} for her: ${String(fields.readOnly)} of ${String(fields.all)} controls read-only (a radio group is one control), "Submit for approval" ${submit === 0 ? "not offered" : "OFFERED"}`;
  return { sent, unproven, said: `${control}; ${formSaid}` };
}

/** Commands of her role sent against an entity she does not cover; none may be accepted. */
async function commandsCheck(lena: Api, maya: Api, worlds: Worlds, page: Page): Promise<Outcome> {
  const target = worlds.command;
  const code = target.entity.code;
  const september = await periodId(maya, code, SEPTEMBER);
  const before = (await maya.get(`/api/v1/periods/${september}`)).json;
  const [contract] = target.contracts;
  const sent: { readonly what: string; readonly got: Got; readonly none?: Got }[] = [];
  const key = { entity_code: code, period_key: SEPTEMBER, book: BOOK };
  const noKey = { ...key, entity_code: NO_ENTITY };
  sent.push({
    what: `POST journal-runs for ${code}`,
    got: await lena.send("POST", "/api/v1/journal-runs", key),
    none: await lena.send("POST", "/api/v1/journal-runs", noKey),
  });
  sent.push({
    what: `POST close-runs for ${code}`,
    got: await lena.send("POST", "/api/v1/close-runs", key),
    none: await lena.send("POST", "/api/v1/close-runs", noKey),
  });
  sent.push({
    what: `POST reconciliations for ${code}`,
    got: await lena.send("POST", "/api/v1/reconciliations", {
      ...key,
      kind: "BILLING_TO_SUBLEDGER",
    }),
    none: await lena.send("POST", "/api/v1/reconciliations", {
      ...noKey,
      kind: "BILLING_TO_SUBLEDGER",
    }),
  });
  const report = (entity: string) => ({
    report_code: "revenue_waterfall",
    parameters: {
      entity_codes: [entity],
      book: BOOK,
      from_period_key: AUGUST,
      to_period_key: AUGUST,
    },
    output_format: "JSON",
  });
  sent.push({
    what: `POST report-runs over ${code}`,
    got: await lena.send("POST", "/api/v1/report-runs", report(code)),
    none: await lena.send("POST", "/api/v1/report-runs", report(NO_ENTITY)),
  });
  if (september !== "") {
    sent.push({
      what: `POST periods/<${code} ${SEPTEMBER}>/start-close`,
      got: await lena.send(
        "POST",
        `/api/v1/periods/${september}/start-close`,
        { comment: "QA pass: a close of another entity." },
        { "If-Match": `"r${text(before, "row_version")}"` },
      ),
      none: await lena.send(
        "POST",
        `/api/v1/periods/${randomUUID()}/start-close`,
        { comment: "QA pass: a close of another entity." },
        { "If-Match": '"r1"' },
      ),
    });
  }
  if (contract !== undefined) {
    const read = (await maya.get(`/api/v1/contracts/${contract.id}`)).json;
    const match = { "If-Match": `"s${text(read, "head_stream_version")}"` };
    const hold = {
      hold_type: "journal_export",
      reason: "QA pass: a hold on a contract of another entity.",
    };
    sent.push({
      what: `POST contracts/<${contract.externalId}>/apply-hold`,
      got: await lena.send("POST", `/api/v1/contracts/${contract.id}/apply-hold`, hold, match),
      none: await lena.send("POST", `/api/v1/contracts/${randomUUID()}/apply-hold`, hold, match),
    });
    sent.push({
      what: `POST contracts/<${contract.externalId}>/submit-activation`,
      got: await lena.send("POST", `/api/v1/contracts/${contract.id}/submit-activation`, {}, match),
      none: await lena.send(
        "POST",
        `/api/v1/contracts/${randomUUID()}/submit-activation`,
        {},
        match,
      ),
    });
  }
  // The writes on a judgement record of the other entity (register index 232): a reader of every
  // entity prepares a DRAFT record on one of its contracts, the member asks to edit, submit and
  // discard it, and the record is read again and discarded by the one who prepared it.
  let judgement = "";
  if (contract !== undefined) {
    const rationale =
      "Prepared by a member who covers the entity; discarded at the end of the check.";
    const made = await maya.send("POST", "/api/v1/judgements", {
      topic: "OTHER",
      subject_type: "contract",
      subject_id: contract.id,
      conclusion: "QA pass: a record prepared to ask the entity bound of its writes.",
      rationale,
    });
    const id = text(made.json, "id");
    if (id === "") {
      judgement = `; no DRAFT judgement record could be prepared on ${contract.externalId} (POST judgements → ${said(made)}), so its writes were not asked`;
    } else {
      const edit = { rationale: "QA pass: an edit asked by a member of another entity." };
      sent.push({
        what: `PATCH judgements/<a DRAFT record of ${contract.externalId}>`,
        got: await lena.send("PATCH", `/api/v1/judgements/${id}`, edit),
        none: await lena.send("PATCH", `/api/v1/judgements/${randomUUID()}`, edit),
      });
      sent.push({
        what: "POST judgements/<it>/submit",
        got: await lena.send("POST", `/api/v1/judgements/${id}/submit`, {}),
        none: await lena.send("POST", `/api/v1/judgements/${randomUUID()}/submit`, {}),
      });
      sent.push({
        what: "POST judgements/<it>/discard",
        got: await lena.send("POST", `/api/v1/judgements/${id}/discard`),
        none: await lena.send("POST", `/api/v1/judgements/${randomUUID()}/discard`),
      });
      const after = (await maya.get(`/api/v1/judgements/${id}`)).json;
      judgement = `; the judgement record ${text(after, "judgement_no")} is ${text(after, "status")} afterwards, its rationale ${text(after, "rationale") === rationale ? "as it was prepared" : `CHANGED to "${flat(text(after, "rationale"), 120)}"`}`;
      if (text(after, "status") === "DRAFT") {
        const discarded = await maya.send("POST", `/api/v1/judgements/${id}/discard`);
        judgement += ` and was discarded by the member who prepared it (${said(discarded)})`;
      }
    }
  }
  // A contract booked in the other entity with the terms of one of her own.
  const [mine] = worlds.own.contracts;
  if (mine !== undefined) {
    const booked = await lena.get(`/api/v1/contracts/${mine.id}/events`, {
      event_type: "CONTRACT_BOOKED",
      limit: 1,
    });
    const terms = at(booked.json, "items", 0, "payload");
    if (typeof terms === "object" && terms !== null) {
      const body = (entity: string) => ({
        ...(terms as Record<string, unknown>),
        external_id: `QA-RC-BOUND-${randomUUID().slice(0, 8)}`,
        contracting_entity_code: entity,
      });
      sent.push({
        what: `POST contracts with contracting_entity_code ${code}`,
        got: await lena.send("POST", "/api/v1/contracts", body(code)),
        none: await lena.send("POST", "/api/v1/contracts", body(NO_ENTITY)),
      });
    }
  }
  /**
   * The answer with the members a 422 names: a refusal of the entity's code is told from a refusal
   * of another member of the body, which would be no answer about the bound.
   */
  const answer = (got: Got): string => {
    const fields = items(got.json, "errors")
      .map((error) => text(error, "field"))
      .filter((field) => field !== "");
    if (got.status === 422 && fields.length > 0) {
      return `${said(got)} on [${[...new Set(fields)].slice(0, 3).join(", ")}]`;
    }
    // A refusal by a rule says which: T-PLT-10 is the one of a policy version beyond her entity.
    const rules = items(got.json, "errors")
      .map((error) => text(error, "rule_id"))
      .filter((rule) => rule !== "");
    return got.status === 403 && rules.length > 0
      ? `${said(got)} by rule ${[...new Set(rules)].slice(0, 3).join(", ")}`
      : said(got);
  };
  const policy = await policyVersions(lena, page, code);
  sent.push(...policy.sent);
  const accepted = sent.filter((item) => twoHundred(item.got));
  const told = sent.filter(
    (item) =>
      !twoHundred(item.got) && item.none !== undefined && answer(item.got) !== answer(item.none),
  );
  const after = (await maya.get(`/api/v1/periods/${september}`)).json;
  const runs = await maya.total("/api/v1/journal-runs", {
    entity: code,
    period: SEPTEMBER,
    book: BOOK,
  });
  const closes = await maya.total("/api/v1/close-runs", {
    entity: code,
    period: SEPTEMBER,
    book: BOOK,
  });
  const held =
    contract === undefined
      ? ""
      : String(at((await maya.get(`/api/v1/contracts/${contract.id}`)).json, "on_hold"));
  const state = `afterwards, as a reader of every entity: ${code} ${SEPTEMBER} is ${text(after, "state")} (was ${text(before, "state")}), ${String(runs)} journal run(s), ${String(closes)} close run(s)${contract === undefined ? "" : `, ${contract.externalId} on hold: ${held}`}${judgement}. Policy versions (register index 291): ${policy.said}`;
  const answers = sent
    .map(
      (item) =>
        `${item.what} → ${answer(item.got)}${item.none === undefined ? "" : ` (${NO_ENTITY} or an unknown id → ${answer(item.none)})`}`,
    )
    .join("; ");
  if (accepted.length > 0) {
    return {
      observed: `ACCEPTED: ${accepted.map((item) => `${item.what} → ${said(item.got)} "${flat(item.got.text, 140)}"`).join(" | ")}. ${answers}. ${state}`,
      result: "FINDING",
      finding: "bound",
    };
  }
  if (told.length > 0) {
    return {
      observed: `no command is accepted; ${String(told.length)} answer(s) differ from the answer for a code or id that names nothing. ${answers}. ${state}`,
      result: "seen once",
    };
  }
  if (policy.unproven.length > 0) {
    // Nothing was accepted, but a refusal of a policy version is not shown to be the bound's.
    return {
      observed: `no command is accepted; the refusals of the policy versions are not proved: ${policy.unproven.join(" | ")}. ${answers}. ${state}`,
      result: "seen once",
    };
  }
  return { observed: `${answers}. ${state}`, result: "pass" };
}

/** What a typed address of another entity's record shows the member. */
async function addressesCheck(page: Page, probe: Probe, foreign: Foreign): Promise<Outcome> {
  const shown: string[] = [];
  const leaks: string[] = [];
  const open2: string[] = [];
  for (const address of probe.screens) {
    let seen = await open(page, address);
    let hits = foreignHits(seen, {
      words: [...probe.words, ...foreign.words],
      apart: foreign.apart,
    });
    if (hits.length > 0) {
      // A candidate: read a second time before it is written.
      seen = await open(page, address);
      hits = foreignHits(seen, { words: [...probe.words, ...foreign.words], apart: foreign.apart });
      if (hits.length > 0) {
        leaks.push(`${address} (${seen.state}, "${seen.heading}"): ${hitsText(hits, 3)}`);
      }
    }
    if (seen.state !== "not found" && seen.state !== "access-limited") {
      open2.push(`${address} → ${seen.state} "${seen.heading}"`);
    }
    shown.push(
      `${address.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, "<id>")} → ${seen.state} "${seen.heading}"`,
    );
    await dismissToasts(page);
  }
  const summary = `${probe.kind} ${probe.label}: ${[...new Set(shown)].join("; ")}`;
  if (leaks.length > 0) {
    return {
      observed: `SHOWN, twice: ${leaks.join(" | ")}. ${summary}`,
      result: "FINDING",
      finding: "bound",
      page,
    };
  }
  if (open2.length > 0) {
    return {
      observed: `nothing of the record is shown, but ${String(open2.length)} address(es) do not answer "not found": ${open2.slice(0, 6).join(" | ")}. ${summary}`,
      result: "seen once",
      page,
    };
  }
  return { observed: summary, result: "pass" };
}

/** What her permissions say a screen shows; "any" where the address itself is the test. */
type Expected = "rendered" | "access-limited" | "any";

interface Visit {
  readonly address: string;
  readonly seen: Seen;
  readonly expected: Expected;
}

/** Every screen she can type an address for, and the screens of her own records. */
async function screensCheck(
  page: Page,
  lena: Api,
  worlds: Worlds,
  foreign: Foreign,
  record: Qa["record"],
): Promise<Outcome> {
  const me = (await lena.get("/api/v1/me")).json;
  const held = new Set(items(me, "permissions").map(String));
  const rows = readScreenRows();
  const addresses: { readonly address: string; readonly expected: Expected }[] = [];
  for (const route of readRouter()) {
    if (route.params.length > 0 || route.path === "*" || NOT_A_SCREEN.has(route.path)) {
      continue;
    }
    const row = screenRowOf(route, rows);
    const permitted =
      row === undefined ||
      row.permissions.length === 0 ||
      row.permissions.some((code) => held.has(code));
    addresses.push({ address: route.path, expected: permitted ? "rendered" : "access-limited" });
  }
  for (const probe of worlds.own.probes) {
    for (const address of probe.screens) {
      addresses.push({ address, expected: "rendered" });
    }
  }
  const outside = `entity=${READ_ENTITY}&period=${AUGUST}&book=${BOOK}`;
  for (const address of CONTEXT_SCREENS) {
    addresses.push({
      address: `${address}${address.includes("?") ? "&" : "?"}${outside}`,
      expected: "any",
    });
  }
  const visits: Visit[] = [];
  const leaks: string[] = [];
  const names = new Map<string, Set<string>>();
  for (const { address, expected } of addresses) {
    let seen = await open(page, address);
    let hits = foreignHits(seen, foreign);
    if (hits.length > 0) {
      seen = await open(page, address);
      hits = foreignHits(seen, foreign);
      if (hits.length > 0) {
        leaks.push(`${address} (${seen.state}): ${hitsText(hits, 3)}`);
      }
    }
    // Codes and names of the other entities: where they stand is written per source, once.
    for (const hit of foreignHits(seen, { words: worlds.entityWords, apart: foreign.apart })) {
      const where = hit.where.replace(/\?.*$/, "").replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, "<id>");
      const pages = names.get(`${hit.word} in ${where}`) ?? new Set<string>();
      pages.add(address.replace(/\?.*$/, ""));
      names.set(`${hit.word} in ${where}`, pages);
    }
    visits.push({ address, seen, expected });
    await dismissToasts(page);
  }
  const count = (state: string) => visits.filter((visit) => visit.seen.state === state).length;
  const off = visits.filter(
    (visit) => visit.expected !== "any" && visit.seen.state !== visit.expected,
  );
  for (const visit of off) {
    record.parked(
      LENA,
      visit.address,
      `the screen is ${visit.seen.state} ("${visit.seen.heading}") where her permissions say ${visit.expected}`,
    );
  }
  const refused = visits.filter((visit) => visit.seen.failures.length > 0);
  for (const visit of refused) {
    record.parked(
      LENA,
      visit.address,
      `requests of the page refused or failed: ${failuresText(visit.seen, 4)}`,
    );
  }
  const named = [...names.entries()].map(
    ([what, pages]) =>
      `${what} (on ${[...pages].slice(0, 3).join(", ")}${pages.size > 3 ? ` and ${String(pages.size - 3)} more` : ""})`,
  );
  const summary = `${String(visits.length)} addresses opened: ${String(count("rendered"))} rendered, ${String(count("access-limited"))} access-limited, ${String(count("not found"))} not found, ${String(count("route error"))} route error, ${String(count("did not settle"))} did not settle; ${String(off.length)} in another state than her permissions say and ${String(refused.length)} with a refused request (parked lines); the context pill reads "${await pillText(page)}"`;
  if (leaks.length > 0) {
    return {
      observed: `A RECORD OF ANOTHER ENTITY IS NAMED, twice: ${leaks.slice(0, 8).join(" | ")}${leaks.length > 8 ? ` | and ${String(leaks.length - 8)} more` : ""}. ${summary}`,
      result: "FINDING",
      finding: "bound",
      page,
    };
  }
  if (named.length > 0) {
    return {
      observed: `no record of another entity is named; a code, a name or the id of another entity stands in: ${named.slice(0, 12).join(" | ")}${named.length > 12 ? ` | and ${String(named.length - 12)} more` : ""}. ${summary}`,
      result: "seen once",
      page,
    };
  }
  return { observed: summary, result: "pass" };
}

/** The options the filter of a list offers for the entity, read from its editor and closed again. */
async function entityFilter(page: Page, address: string): Promise<string> {
  await open(page, address);
  const bar = page.getByRole("toolbar", { name: "Filters", exact: true }).first();
  const add = bar.getByRole("button", { name: "Filter", exact: true });
  if ((await add.count()) === 0) {
    return `${address}: no filter list`;
  }
  await add.click();
  const list = bar.getByRole("dialog", { name: "Filter", exact: true });
  const fields = (
    await list
      .getByRole("listitem")
      .allInnerTexts()
      .catch(() => [] as string[])
  ).map((item) => item.trim());
  const field = fields.find((item) => /entity/i.test(item));
  if (field === undefined) {
    await page.keyboard.press("Escape");
    return `${address}: its filters [${fields.join(", ")}] name no entity`;
  }
  await list.getByRole("button", { name: field, exact: true }).click();
  const editor = bar.getByRole("dialog", { name: `${field} filter`, exact: true });
  await editor.waitFor({ state: "visible", timeout: 10_000 });
  let options = await editor
    .getByRole("checkbox")
    .evaluateAll((elements) =>
      elements.map((element) =>
        (element.closest("label")?.textContent ?? element.getAttribute("aria-label") ?? "").trim(),
      ),
    );
  if (options.length === 0) {
    const choice = editor.getByRole("combobox").first();
    if ((await choice.count()) > 0) {
      await choice.click();
      options = (
        await page
          .getByRole("option")
          .allInnerTexts()
          .catch(() => [] as string[])
      ).map((item) => item.trim());
      await page.keyboard.press("Escape");
    }
  }
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");
  return `${address}: the filter "${field}" offers [${options.join(" | ")}]`;
}

/** What "All entities" offers her and what it totals. */
async function allEntitiesCheck(page: Page, lena: Api, maya: Api): Promise<Outcome> {
  const parts: string[] = [];
  // A run or a panel over more than her entity, or a total that is not her entity's, crosses the
  // bound. A code or a name of another entity among the options of a control is said and read by
  // hand, as the names of K-2 and K-5 are: it is no record of that entity.
  const wrong: string[] = [];
  const offers: string[] = [];
  // A run without an entity is a run over her scope; its total is the total of a run over AVM-DE.
  const mine = await makeWaterfallRun(lena, null, SEPTEMBER, SEPTEMBER);
  const named = await makeWaterfallRun(lena, [HOME_ENTITY], SEPTEMBER, SEPTEMBER);
  const reference = await makeWaterfallRun(maya, [HOME_ENTITY], SEPTEMBER, SEPTEMBER);
  const totalOf = async (api: Api, id: string): Promise<string> => {
    const totals = (await reportRows(api, id)).filter((row) =>
      text(row, "row_key").startsWith("TOTAL:"),
    );
    return (
      totals
        .map((row) => `${text(row, "row_key")} ${text(row, `period:${SEPTEMBER}`, "amount")}`)
        .join(", ") || "no total line"
    );
  };
  const scopeOf = async (api: Api, id: string): Promise<string> =>
    items((await api.get(`/api/v1/report-runs/${id}`)).json, "entity_scope")
      .map((entity) => text(entity, "code"))
      .join(", ");
  const expected = reference.id === "" ? null : await totalOf(maya, reference.id);
  if (mine.id === "") {
    parts.push(`a waterfall run asked without an entity is answered ${mine.said}`);
  } else {
    const scope = await scopeOf(lena, mine.id);
    const total = await totalOf(lena, mine.id);
    parts.push(
      `a waterfall run she asks without an entity (${mine.said}) covers [${scope}] and totals ${total} for ${SEPTEMBER}`,
    );
    if (scope !== HOME_ENTITY) {
      wrong.push(`her run without an entity covers [${scope}]`);
    }
    if (expected !== null && total !== expected) {
      wrong.push(`her run without an entity totals ${total}, ${HOME_ENTITY} totals ${expected}`);
    }
  }
  if (named.id === "") {
    parts.push(`her run over ${HOME_ENTITY} is answered ${named.said}`);
  } else {
    const total = await totalOf(lena, named.id);
    parts.push(`her run over ${HOME_ENTITY} totals ${total}`);
    if (expected !== null && total !== expected) {
      wrong.push(
        `her run over ${HOME_ENTITY} totals ${total}, a reader of every entity gets ${expected}`,
      );
    }
  }
  parts.push(
    `the same run by a reader of every entity (${reference.said}) totals ${expected ?? "nothing"}`,
  );
  // The revenue dashboard for all entities (SCREENS SCR-URL-01 rev 1.61; SCREENS_B §5.5).
  const dashboard = await open(
    page,
    `/reports/dashboards/revenue?period=${SEPTEMBER}&book=${BOOK}&entities=all`,
  );
  const runs = [...new URL(page.url()).searchParams.entries()].filter(([name]) =>
    name.startsWith("run."),
  );
  const scopes: string[] = [];
  for (const [name, id] of runs) {
    scopes.push(`${name.replace("run.", "")} over [${await scopeOf(lena, id)}]`);
  }
  const banner = await page
    .getByTestId("SF-08-dashboard-banner-scope")
    .innerText({ timeout: 2_000 })
    .catch(() => "");
  parts.push(
    `the revenue dashboard with entities=all reads "${dashboard.heading}" (${dashboard.state})${banner === "" ? "" : `, banner "${flat(banner, 160)}"`}, panels: ${scopes.length === 0 ? "none drawn" : scopes.join("; ")}`,
  );
  if (scopes.some((line) => !line.endsWith(`[${HOME_ENTITY}]`))) {
    wrong.push("a panel of the dashboard runs over more than her entity");
  }
  // The context pill and the entity filters.
  await open(page, "/contracts");
  const offered = await pillOptions(page, "Entity").catch(() => [] as string[]);
  parts.push(
    `on Contracts the context pill reads "${await pillText(page)}" and offers the entities [${offered.join(" | ")}]`,
  );
  if (offered.some((option) => !option.startsWith(HOME_ENTITY))) {
    offers.push("the context pill offers an entity outside her scope");
  }
  for (const address of ["/approvals/all", "/data/exceptions", "/journals"]) {
    let line: string;
    try {
      line = await entityFilter(page, address);
    } catch (error) {
      line = `${address}: its entity filter could not be read (${error instanceof Error ? flat(error.message.split("Call log:")[0] ?? "", 160) : String(error)})`;
      await page.keyboard.press("Escape").catch(() => undefined);
    }
    parts.push(line);
    if (/AVM-(US|UK|JP)/.test(line)) {
      offers.push(`${address}: the entity filter offers an entity outside her scope`);
    }
  }
  const observed = parts.join(". ");
  if (wrong.length > 0) {
    return {
      observed: `${[...wrong, ...offers].join("; ")}. ${observed}`,
      result: "FINDING",
      finding: "bound",
      page,
    };
  }
  return offers.length === 0
    ? { observed, result: "pass", page }
    : {
        observed: `no run and no panel covers more than her entity; ${offers.join("; ")}. ${observed}`,
        result: "seen once",
        page,
      };
}

export async function entityBoundSection({ record, sessions }: Qa): Promise<void> {
  const maya = new Api(await sessions.page("maya"));
  let page: Page;
  try {
    page = await sessions.page(LENA);
  } catch (error) {
    record.row({
      check: "K the entity bound",
      persona: LENA,
      address: "every check of the section",
      expected: "03 REQ-PLT-012; PRD BR-UX-06",
      observed: `the member for ${HOME_ENTITY} alone could not sign in: ${error instanceof Error ? error.message : String(error)}`,
      result: "not run",
    });
    return;
  }
  const lena = new Api(page);
  const worlds = await readWorlds(maya);
  record.note(
    `K, the world: ${kindsText(worlds.own)} | ${kindsText(worlds.read)} | ${kindsText(worlds.command)}; ${String(worlds.contractWords.length / 3)} contracts outside ${HOME_ENTITY}`,
  );
  const imports = await importProbes(maya, lena);
  const foreign: Foreign = {
    words: [
      ...worlds.contractWords,
      ...worlds.read.probes.flatMap((probe) => probe.words),
      ...worlds.command.probes.flatMap((probe) => probe.words),
    ].filter(
      // A short key could stand inside another word; an entity's own id and code are read apart.
      (word) => word.length >= 6 && !worlds.entityWords.includes(word),
    ),
    // The catalogue of entities is read apart (check G-4): one answer, not one hit a page.
    apart: [/^\/api\/v1\/entities(\?|$)/],
  };

  for (const [world, extra] of [
    [worlds.read, imports.foreign === null ? [] : [imports.foreign]],
    [worlds.command, []],
  ] as const) {
    await record.check(
      {
        check: `K-1 records of ${world.entity.code} asked through the API`,
        persona: LENA,
        address: "GET /api/v1/<record of another entity>",
        expected:
          "Each read of a record of an entity outside her scope is answered exactly as the same read of an id that names nothing, 404 not-found (03 REQ-PLT-012 'out-of-scope ids return 404'; 04 API-C-03); the same kinds of her own entity are readable",
      },
      () => readsCheck(lena, world, worlds.own, extra, imports.own === null ? [] : [imports.own]),
    );
  }

  await record.check(
    {
      check: "K-2 lists, totals and search through the API",
      persona: LENA,
      address: "GET /api/v1/<list>",
      expected: `A list without an entity holds her entity's records and no other, and its total is the total of ${HOME_ENTITY}; the same list asked for ${READ_ENTITY} holds nothing; the search and Home's figures name nothing of ${READ_ENTITY} (03 REQ-PLT-012 'Reads, commands and reports return only in-scope entities')`,
    },
    () => listsCheck(lena, maya, worlds),
  );

  await record.check(
    {
      check: "K-3 commands of her role against another entity",
      persona: LENA,
      address: `POST /api/v1/<command> for ${COMMAND_ENTITY}`,
      expected: `No command is accepted: each is answered as for a code or an id that names nothing, and ${COMMAND_ENTITY} is unchanged afterwards (03 REQ-PLT-012; PRD BR-UX-05 'A hidden action is also refused by the API'). A policy version of TENANT or BOOK scope, which applies to every entity, is refused 403 by rule T-PLT-10 to a member whose config.author names one entity; a version for her own entity is taken (PRD BR-UX-06; register index 291)`,
    },
    () => commandsCheck(lena, maya, worlds, page),
  );

  for (const probe of [
    ...worlds.read.probes,
    ...(imports.foreign === null ? [] : [imports.foreign]),
  ]) {
    if (probe.screens.length === 0) {
      continue;
    }
    await record.check(
      {
        check: `K-4 a typed address: ${probe.kind} of ${READ_ENTITY}`,
        persona: LENA,
        address: probe.screens[0]?.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/g, "<id>") ?? "",
        expected:
          "The screen answers 'not found' and shows nothing of the record: no number, name or figure of it in the page or in an answer the page was given (PRD BR-UX-06)",
      },
      () => addressesCheck(page, probe, foreign),
    );
  }

  await record.check(
    {
      check: "K-5 every screen she can open",
      persona: LENA,
      address:
        "every route without a parameter, the screens of her own records, and the context screens with another entity in the address",
      expected: `A screen she holds the permission for renders her entity's records; a screen she does not is access-limited (SCR-PERM-01); none names a record of another entity, also when the address names ${READ_ENTITY} (PRD BR-UX-06; SCREENS SCR-URL-01)`,
    },
    () => screensCheck(page, lena, worlds, foreign, record),
  );

  await record.check(
    {
      check: 'K-6 what "All entities" offers her and what it totals',
      persona: LENA,
      address: "/reports/dashboards/revenue?entities=all, the context pill, the entity filters",
      expected: `"All entities" is her scope: a run without an entity covers ${HOME_ENTITY} alone and totals what ${HOME_ENTITY} totals; the pill and every entity filter offer ${HOME_ENTITY} and no other entity (PRD BR-UX-01; 04 §15.3 API-R-41 'A run names no entity outside a permission its report needs')`,
    },
    () => allEntitiesCheck(page, lena, maya),
  );
}
