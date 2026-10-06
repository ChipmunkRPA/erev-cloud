// Section L of the pass: the workspace bound (03 REQ-PLT-001 "A cross-tenant read, insert, update
// or delete fails on every table"). maya is a member of several workspaces and switches between two
// of them in one window; samuel is a member of Avenmoor alone. A record of the workspace a session
// is not in is asked for by a typed address and through the API, and after a switch the screens of
// the second workspace are read for anything of the first.
import { randomUUID } from "node:crypto";

import type { Page } from "@playwright/test";

import { Api, at, type Got, items, said, text } from "../api";
import type { Qa } from "../fixtures";
import { failuresText, type Foreign, foreignHits, hitsText, open, wordAt } from "../observe";
import { flat, type Outcome } from "../record";
import { normaliseKey } from "../../screens";
import { personaCredentials, readState, sessionRead, walkSignIn } from "../sessions";
import { dismissToasts } from "../steps";
import { unknownOf } from "../world";

/** PRD §2.4 WLD-T-02: the second workspace of the check; every persona but samuel is a member. */
const OTHER = { code: "fernhill", name: "Fernhill Software, Inc. (Demo)" } as const;
const HOME = { code: "avenmoor", name: "Avenmoor Holdings (Demo)" } as const;
/** The screens read after a switch: where a figure, a recent item or a search result would stand. */
const AFTER_SWITCH = [
  "/home",
  "/contracts",
  "/schedules",
  "/journals",
  "/approvals",
  "/data/imports",
  "/reports",
];

interface Sample {
  readonly tenantId: string;
  /** A contract of the workspace, or "" where it lists the member none. */
  readonly contractId: string;
  readonly externalId: string;
  /** A legal entity and a period state of the workspace: records every workspace holds. */
  readonly entityId: string;
  readonly entityCode: string;
  readonly periodId: string;
  /**
   * Ids and external ids of the workspace's contracts, and its entities' ids and codes. Not the
   * contract numbers: each workspace counts its own from one, so two workspaces share them.
   */
  readonly words: readonly string[];
}

/** What a session was shown of another workspace: the lines of the row and what they amount to. */
interface Found {
  readonly lines: string[];
  /** Shown with content, or accepted. */
  readonly leaks: string[];
  /** Answers of 500 and above on the way. */
  readonly server: string[];
  /** Answers that differ from the answer for an id that names nothing. */
  readonly told: string[];
}

function twoHundred(got: Got): boolean {
  return got.status >= 200 && got.status < 300;
}

/** The workspace the session is in, as far as the checks name it. */
async function sample(api: Api): Promise<Sample> {
  const session = (await api.get("/api/v1/session")).json;
  const contracts = await api.list("/api/v1/contracts", {}, 600);
  const entities = await api.list("/api/v1/entities");
  const [first] = contracts;
  const [entity] = entities;
  const period = at((await api.get("/api/v1/periods", { limit: 1 })).json, "items", 0);
  return {
    tenantId: text(session, "active_tenant", "id"),
    contractId: text(first, "id"),
    externalId: text(first, "external_id"),
    entityId: text(entity, "id"),
    entityCode: text(entity, "code"),
    periodId: text(period, "id"),
    words: [
      ...contracts.flatMap((contract) => [text(contract, "id"), text(contract, "external_id")]),
      ...entities.flatMap((entity) => [text(entity, "id"), text(entity, "code")]),
    ].filter((word) => word.length >= 6),
  };
}

/** The user menu's "Switch tenant", then the workspace by its name; the window ends on its landing. */
async function switchTo(page: Page, name: string, code: string): Promise<string> {
  await page.getByRole("button", { name: /^User menu for / }).click();
  await page.getByRole("menuitem", { name: "Switch tenant" }).click();
  const list = page.getByRole("listbox", { name: "Workspaces" });
  const offered = (await list.getByRole("option").allInnerTexts()).map((option) =>
    flat(option, 60),
  );
  await list
    .getByRole("option", { name: new RegExp(`^${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`) })
    .click();
  for (let turn = 0; turn < 60; turn += 1) {
    if ((await sessionRead(page)).active_tenant?.code === code) {
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return `the switcher offered ${String(offered.length)} workspaces`;
}

/** What a session of one workspace is shown of the other: the screens, a typed address, the API. */
async function asked(
  page: Page,
  api: Api,
  other: Sample,
  own: Sample | null,
  label: string,
): Promise<Found> {
  const lines: string[] = [];
  const leaks: string[] = [];
  const server: string[] = [];
  const told: string[] = [];
  /** A command on the other workspace's record against the same command on an unknown id. */
  const command = async (
    name: string,
    path: (id: string) => string,
    id: string,
    body: unknown,
    match: string,
  ): Promise<void> => {
    const got = await api.send("POST", path(id), body, { "If-Match": match });
    const none = await api.send("POST", path(randomUUID()), body, { "If-Match": match });
    if (twoHundred(got)) {
      leaks.push(`POST ${name} → ${said(got)}: ACCEPTED`);
    } else if (said(got) !== said(none)) {
      told.push(`POST ${name} → ${said(got)}, an id that names nothing → ${said(none)}`);
    }
    lines.push(`POST ${name} → ${said(got)} (an id that names nothing → ${said(none)})`);
  };
  if (other.contractId === "" && other.entityId === "" && other.periodId === "") {
    // Without a record of the other workspace there is no id to ask for: an address built from an
    // empty id would be the member's own list.
    return {
      lines: [
        `${label} listed no contract, entity or period to the member who sampled it: nothing of it could be asked for`,
      ],
      leaks,
      server,
      told,
    };
  }
  // A key both workspaces use (an external id of the same source system) names nothing of the other.
  const shared = new Set(own?.words ?? []);
  const foreign: Foreign = {
    words: other.words.filter((word) => !shared.has(word)),
    // The member's own list of workspaces names each of them: it is hers to read.
    apart: [/^\/api\/v1\/me(\?|$)/, /^\/api\/v1\/session(\/|\?|$)/],
  };
  for (const address of [
    ...AFTER_SWITCH,
    `/search?q=${encodeURIComponent(other.externalId === "" ? other.entityCode : other.externalId)}`,
  ]) {
    let seen = await open(page, address);
    let hits = foreignHits(seen, foreign);
    if (hits.length > 0) {
      seen = await open(page, address);
      hits = foreignHits(seen, foreign);
      if (hits.length > 0) {
        leaks.push(`${address}: ${hitsText(hits, 3)}`);
      }
    }
    server.push(
      ...seen.failures
        .filter((failure) => / → 5\d\d/.test(failure))
        .map((failure) => `${address}: ${failure}`),
    );
    lines.push(
      `${address} ${seen.state}${seen.failures.length === 0 ? "" : ` (refused: ${failuresText(seen, 2)})`}`,
    );
    await dismissToasts(page);
  }
  /** A read of the other workspace's record by its id, against the same read of an unknown id. */
  const read = async (path: string, id: string): Promise<void> => {
    const got = await api.get(path);
    const none = await api.get(unknownOf(path));
    const content =
      twoHundred(got) && items(got.json).length + (at(got.json, "id") === undefined ? 0 : 1) > 0;
    if (content && twoHundred(await api.get(path))) {
      leaks.push(`GET ${path.replace(id, "<id>")} → ${said(got)} with content`);
    } else if (!twoHundred(got) && said(got) !== said(none)) {
      told.push(
        `GET ${path.replace(id, "<id>")} → ${said(got)}, an id that names nothing → ${said(none)}`,
      );
    }
    lines.push(
      `GET ${path.replace(id, "<id>").replace("/api/v1/", "")} → ${said(got)} (an id that names nothing → ${said(none)})`,
    );
  };
  if (other.contractId === "") {
    lines.push(`${label} lists the member who sampled it no contract`);
  } else {
    const typed = `/contracts/${other.contractId}/obligations`;
    const seen = await open(page, typed);
    const hits = foreignHits(seen, foreign);
    if (hits.length > 0 || (seen.state !== "not found" && seen.state !== "access-limited")) {
      const again = await open(page, typed);
      if (foreignHits(again, foreign).length > 0) {
        leaks.push(
          `the typed address of ${label}'s contract (${again.state}): ${hitsText(foreignHits(again, foreign), 3)}`,
        );
      }
    }
    lines.push(`the typed address of ${label}'s contract → ${seen.state} "${seen.heading}"`);
    for (const path of [
      `/api/v1/contracts/${other.contractId}`,
      `/api/v1/contracts/${other.contractId}/obligations?book=ASC606`,
      `/api/v1/schedule-lines?contract=${other.contractId}&book=ASC606`,
    ]) {
      await read(path, other.contractId);
    }
    await command(
      "contracts/<id>/apply-hold",
      (id) => `/api/v1/contracts/${id}/apply-hold`,
      other.contractId,
      {
        hold_type: "journal_export",
        reason: "QA pass: a hold on a contract of another workspace.",
      },
      '"s1"',
    );
  }
  // The records every workspace holds: a legal entity and a period state, read by their ids, and a
  // command on the period.
  if (other.entityId !== "") {
    await read(`/api/v1/entities/${other.entityId}`, other.entityId);
  }
  if (other.periodId !== "") {
    await read(`/api/v1/periods/${other.periodId}`, other.periodId);
    await read(`/api/v1/periods/${other.periodId}/checklist`, other.periodId);
    await command(
      "periods/<id>/start-close",
      (id) => `/api/v1/periods/${id}/start-close`,
      other.periodId,
      { comment: "QA pass: a close of a period of another workspace." },
      '"r1"',
    );
  }
  return { lines, leaks, server, told };
}

/** The role the second workspace asks for the member it invites, and the name its administrator types. */
const INVITED_ROLE = "Revenue Accountant";
const TYPED_NAME = "Invited for the QA pass";

/**
 * Register index 298 (the supervisor's word of 2026-10-03): what a workspace is shown of a person
 * another workspace made, before she accepts (D-80 rule 5; 04 T-PLT-02 "What a workspace is shown of
 * a person"). The member the pass made in Avenmoor is invited by the administrator of the second
 * workspace; the answers and the screens that name her there are read for the name Avenmoor holds,
 * and her membership of the second workspace is removed again.
 */
async function invitedElsewhere(
  page: Page,
  home: Api,
  second: { readonly code: string; readonly name: string },
  parked: (address: string, line: string) => void,
): Promise<Outcome> {
  const member = readState().lena;
  if (member === undefined || !member.accepted) {
    return {
      observed: "the member for AVM-DE alone was not made (section G): nobody to invite",
      result: "not run",
    };
  }
  await walkSignIn(page, personaCredentials("tomas"), "tomas");
  const switched = await switchTo(page, second.name, second.code);
  const session = await sessionRead(page);
  if (session.active_tenant?.code !== second.code) {
    return {
      observed: `${switched}; tomas asked for ${second.code}, the session stayed in ${session.active_tenant?.code ?? "no workspace"}`,
      result: "not run",
    };
  }
  const api = new Api(page);
  const roles = await api.get("/api/v1/roles", { q: INVITED_ROLE, limit: 50 });
  const role = items(roles.json).find((item) => text(item, "name") === INVITED_ROLE);
  const entity = text((await api.get("/api/v1/entities", { limit: 1 })).json, "items", 0, "code");
  if (role === undefined || entity === "") {
    return {
      observed: `${second.code}: GET roles?q=${INVITED_ROLE} → ${said(roles)}${role === undefined ? ", the role is not listed" : ""}; first entity "${entity}": the invitation was not sent`,
      result: "not run",
    };
  }
  const invited = await api.send("POST", "/api/v1/users", {
    email: member.email,
    display_name: TYPED_NAME,
    roles: [{ role_id: text(role, "id"), is_all_entities: false, entity_codes: [entity] }],
  });
  const membership = text(invited.json, "id");
  if (invited.status !== 201 || membership === "") {
    return {
      observed: `${second.code}: POST users for the Avenmoor member's address → ${said(invited)} ${flat(text(invited.json, "detail"), 200)}: nothing to read`,
      result: "not run",
    };
  }
  // What the second workspace is answered and shown of her; each is read for the name Avenmoor holds.
  const requestId = text(invited.json, "roles", 0, "approval_request_id");
  const read = async (): Promise<{ readonly named: string[]; readonly said: string[] }> => {
    const named: string[] = [];
    const lines: string[] = [];
    const answers: [string, Got][] = [
      ["GET users/<membership>", await api.get(`/api/v1/users/${membership}`)],
      ["GET users?q=<her address>", await api.get("/api/v1/users", { q: member.email })],
    ];
    if (requestId !== "") {
      answers.push([
        "GET approvals/<her role request>",
        await api.get(`/api/v1/approvals/${requestId}`),
      ]);
    }
    for (const [what, got] of answers) {
      if (wordAt(got.text, member.name) !== -1) {
        named.push(what);
      }
    }
    const user = answers[0]?.[1].json;
    const request = requestId === "" ? null : answers[2]?.[1].json;
    lines.push(
      `GET users/<membership> → ${said(answers[0]?.[1] ?? invited)}: display_name "${text(user, "display_name")}", status ${text(user, "status")}`,
    );
    if (request !== null) {
      lines.push(
        `her role request ${text(request, "request_no")} (${text(request, "status")}) reads "${text(request, "summary")}"`,
      );
    }
    const screens =
      requestId === ""
        ? ["/settings/users"]
        : [`/approvals/requests/${requestId}`, "/settings/users"];
    for (const address of screens) {
      const seen = await open(page, address);
      const inText = wordAt(seen.text, member.name) !== -1;
      const inAnswers = seen.answers.some(
        (answer) => answer.status < 400 && wordAt(answer.body, member.name) !== -1,
      );
      if (inText || inAnswers) {
        named.push(
          `${address.replace(requestId, "<id>")} (${inText ? "the page's text" : "an answer of the page"})`,
        );
      }
      lines.push(`${address.replace(requestId, "<id>")} ${seen.state}`);
      if (address === "/settings/users") {
        // Her row in the Users grid (SF-14): what the workspace is shown of her sign-in before she
        // accepts, and whether a cell clips its words — the box that clips, not the text's span.
        const cells = await page
          .getByTestId(`SF-14-row-${normaliseKey(member.email)}`)
          .first()
          .evaluate(
            (row) => {
              const grid = row.closest('[role="grid"]');
              return ["mfa", "last_login_at"].map((column) => {
                const index =
                  grid
                    ?.querySelector(`[role="columnheader"][data-column="${column}"]`)
                    ?.getAttribute("aria-colindex") ?? "";
                const cell = row.querySelector(`[role="gridcell"][aria-colindex="${index}"]`);
                const boxes =
                  cell === null ? [] : [cell, ...cell.querySelectorAll<HTMLElement>("*")];
                return {
                  column,
                  found: cell !== null,
                  text: (cell?.textContent ?? "").replace(/\s+/g, " ").trim(),
                  clipped: boxes.some(
                    (box) =>
                      box.scrollWidth > box.clientWidth &&
                      getComputedStyle(box).overflowX !== "visible",
                  ),
                };
              });
            },
            undefined,
            { timeout: 10_000 },
          )
          .catch(() => null);
        if (cells === null) {
          lines.push("her row is not in the Users grid");
        } else {
          lines.push(
            `her row in the Users grid reads ${cells.map((cell) => `${cell.column} ${cell.found ? `"${cell.text}"${cell.clipped ? " (the cell clips its words)" : ""}` : "(no such cell)"}`).join(", ")}`,
          );
          for (const cell of cells.filter((item) => item.clipped)) {
            parked(
              address,
              `the ${cell.column} cell of an invited member clips its words in the Users grid: "${cell.text}"`,
            );
          }
        }
      }
      await dismissToasts(page);
    }
    return { named, said: lines };
  };
  let found = await read();
  if (found.named.length > 0) {
    // A candidate: read a second time before it is written.
    found = await read();
  }
  const removed = await api.send("POST", `/api/v1/users/${membership}/remove`, {
    reason: "QA pass: invited to read what the workspace is shown of her; removed at once.",
  });
  const after = text((await api.get(`/api/v1/users/${membership}`)).json, "status");
  // The other direction of the bound: the name the second workspace typed must not replace the one
  // Avenmoor holds of its own member.
  const kept =
    member.membershipId === null
      ? ""
      : text((await home.get(`/api/v1/users/${member.membershipId}`)).json, "display_name");
  const body = `tomas in ${second.code} invited ${member.email} (in Avenmoor: "${member.name}") as ${INVITED_ROLE} for ${entity}, typing the name "${TYPED_NAME}": POST users → ${said(invited)}; ${found.said.join("; ")}. Afterwards POST users/<membership>/remove → ${said(removed)}; the membership is ${after || "unread"}.`;
  if (found.named.length > 0) {
    return {
      observed: `THE NAME AVENMOOR HOLDS IS SHOWN TO ANOTHER WORKSPACE BEFORE SHE ACCEPTS, twice: ${found.named.join(" | ")}. ${body}`,
      result: "FINDING",
      finding: "bound",
      page,
    };
  }
  if (kept !== "" && kept !== member.name) {
    return {
      observed: `THE INVITATION OF ANOTHER WORKSPACE CHANGED THE NAME AVENMOOR HOLDS: Avenmoor's administrator now reads "${kept}" for its member. ${body}`,
      result: "FINDING",
      finding: "bound",
      page,
    };
  }
  return {
    observed: `her name in Avenmoor stands in none of them, and Avenmoor still reads "${kept || "unread"}" for its member. ${body}`,
    result: "pass",
  };
}

function outcome(found: Found, lead: string, page: Page): Outcome {
  const body = `${lead} ${found.lines.join("; ")}`;
  if (found.leaks.length > 0) {
    return {
      observed: `SHOWN OR ACCEPTED, twice: ${found.leaks.join(" | ")}. ${body}`,
      result: "FINDING",
      finding: "bound",
      page,
    };
  }
  if (found.told.length > 0) {
    // Nothing is shown or accepted, but an answer tells a record of the other workspace from an id
    // that names nothing: said, and read by hand.
    return {
      observed: `nothing of the other workspace is shown or accepted; ${String(found.told.length)} answer(s) differ from the answer for an id that names nothing: ${found.told.join(" | ")}. ${body}`,
      result: "seen once",
      page,
    };
  }
  if (found.server.length > 0) {
    // Register index 228 names the 500s of a member of two workspaces: read against it by hand.
    return {
      observed: `nothing of the other workspace is shown; server errors on the way: ${found.server.slice(0, 5).join(" | ")}. ${body}`,
      result: "seen once",
      page,
    };
  }
  return { observed: body, result: "pass" };
}

export async function workspaceBoundSection({ record, sessions }: Qa): Promise<void> {
  // A window of maya's own for the switch: her cached session stays in Avenmoor for the other sections.
  const page = await sessions.blank("maya");
  let avenmoor: Sample | null = null;
  let other: Sample | null = null;
  // The second workspace of the checks: the first of maya's other workspaces that lists her a
  // contract, Fernhill first. The seed gives an industry workspace its entities, calendar, chart
  // and mapping and no contract (backend domain/demo/builders.py), and the legacy parity pack
  // nothing: on a seeded world the checks ask for a legal entity and a period of Fernhill.
  let second: { readonly code: string; readonly name: string } = OTHER;
  /** A check that needs a record of the second workspace, when its sample holds none. */
  const noRecord = () =>
    ({
      observed: `none of maya's other workspaces lists her a contract, an entity or a period: nothing of another workspace could be asked for (${second.name} was the last one tried)`,
      result: "not run",
    }) as const;

  await record.check(
    {
      check: "L-1 after a switch to another workspace",
      persona: "maya",
      address: "user menu → Switch tenant → another workspace of hers",
      expected: `The window lands on the second workspace's Home; no figure, recent item, favourite, list row or search result of ${HOME.name} remains on its screens, a typed address of an Avenmoor contract answers "not found", the API answers its id as an id that names nothing, and no command reaches it (03 REQ-PLT-001; SCREENS §1.3 "clears the query cache")`,
    },
    async () => {
      await walkSignIn(page, personaCredentials("maya"), "maya");
      const api = new Api(page);
      // What a switch would have to forget: a record opened, a search made, the context chosen.
      avenmoor = await sample(api);
      await open(page, `/contracts/${avenmoor.contractId}/obligations`);
      await open(page, `/search?q=${encodeURIComponent(avenmoor.externalId)}`);
      const me = (await api.get("/api/v1/me")).json;
      const candidates = items(me, "memberships")
        .filter(
          (membership) =>
            text(membership, "status") === "ACTIVE" &&
            text(membership, "tenant", "status") === "ACTIVE" &&
            text(membership, "tenant", "code") !== HOME.code,
        )
        .map((membership) => ({
          code: text(membership, "tenant", "code"),
          name: text(membership, "tenant", "display_name"),
        }))
        .sort(
          (left, right) => Number(right.code === OTHER.code) - Number(left.code === OTHER.code),
        );
      const tried: string[] = [];
      let switched = "";
      /** The switch to a workspace of hers; what stopped it, or null when the session is in it. */
      const enter = async (candidate: typeof second): Promise<Outcome | null> => {
        switched = await switchTo(page, candidate.name, candidate.code);
        const session = await sessionRead(page);
        return session.active_tenant?.code === candidate.code
          ? null
          : {
              observed: `${switched}; asked for ${candidate.code}, the session stayed in ${session.active_tenant?.code ?? "no workspace"}`,
              result: "FINDING",
              finding: "stopped flow",
              page,
            };
      };
      // The first workspace that lists her a legal entity or a period, kept for a world in which
      // none lists her a contract.
      let held: { readonly candidate: typeof second; readonly sample: Sample } | null = null;
      for (const candidate of candidates.slice(0, 7)) {
        const stopped = await enter(candidate);
        if (stopped !== null) {
          return stopped;
        }
        const sampled = await sample(new Api(page));
        second = candidate;
        other = sampled;
        const holds = sampled.entityId !== "" || sampled.periodId !== "";
        tried.push(
          `${candidate.code} ${sampled.contractId === "" ? (holds ? "lists her no contract" : "lists her no contract, entity or period") : "lists her contracts"}`,
        );
        if (sampled.contractId !== "") {
          break;
        }
        if (held === null && holds) {
          held = { candidate, sample: sampled };
        }
      }
      if (other === null) {
        return { observed: "maya is a member of no other workspace", result: "not run" };
      }
      if (other.contractId === "" && held !== null && held.candidate.code !== second.code) {
        // No workspace lists her a contract: the checks ask for the entity and the period of the
        // first one that lists her any, and the session goes back into it.
        const stopped = await enter(held.candidate);
        if (stopped !== null) {
          return stopped;
        }
        second = held.candidate;
        other = held.sample;
        tried.push(`the checks use ${second.code}`);
      }
      const found = await asked(page, new Api(page), avenmoor, other, HOME.name);
      return outcome(
        found,
        `${switched}; workspaces tried: ${tried.join(", ")}; the session is in ${second.code}, on ${new URL(page.url()).pathname}.`,
        page,
      );
    },
  );

  await record.check(
    {
      check: "L-2 after the switch back",
      persona: "maya",
      address: `user menu → Switch tenant → ${HOME.name}`,
      expected: `Back in ${HOME.name} nothing of the other workspace remains, and its contract answers "not found" by address and by id (03 REQ-PLT-001)`,
    },
    async () => {
      if (other === null) {
        return {
          observed: "the switch of L-1 did not reach the second workspace",
          result: "not run",
        };
      }
      const switched = await switchTo(page, HOME.name, HOME.code);
      const session = await sessionRead(page);
      if (session.active_tenant?.code !== HOME.code) {
        return {
          observed: `${switched}; the session stayed in ${session.active_tenant?.code ?? "no workspace"}`,
          result: "FINDING",
          finding: "stopped flow",
          page,
        };
      }
      if (other.contractId === "" && other.entityId === "" && other.periodId === "") {
        return noRecord();
      }
      const found = await asked(page, new Api(page), other, avenmoor, second.name);
      return outcome(found, `${switched}; the session is in ${HOME.code}.`, page);
    },
  );

  await record.check(
    {
      check: "L-3 a member of one workspace",
      persona: "samuel",
      address: "/contracts/<a contract of another workspace>",
      expected: `samuel is a member of ${HOME.name} alone (PRD §2.3 WLD-U-07): a contract of another workspace answers "not found" by address and by id, and the workspace itself cannot be opened by its id (03 REQ-PLT-001; 04 API-R-01 POST /session/tenant)`,
    },
    async () => {
      if (other === null) {
        return { observed: "L-1 named no record of the second workspace", result: "not run" };
      }
      if (other.contractId === "" && other.entityId === "" && other.periodId === "") {
        return noRecord();
      }
      const samuel = await sessions.page("samuel");
      const api = new Api(samuel);
      const me = (await api.get("/api/v1/me")).json;
      const memberships = items(me, "memberships").map((membership) =>
        text(membership, "tenant", "code"),
      );
      const found = await asked(samuel, api, other, avenmoor, second.name);
      const opened = await api.send("POST", "/api/v1/session/tenant", {
        tenant_id: other.tenantId,
      });
      const session = await sessionRead(samuel);
      if (twoHundred(opened) || session.active_tenant?.code !== HOME.code) {
        found.leaks.push(
          `POST session/tenant for ${second.code} → ${said(opened)}; the session is now in ${session.active_tenant?.code ?? "no workspace"}`,
        );
      }
      return outcome(
        found,
        `memberships [${memberships.join(", ")}]; POST session/tenant for ${second.code} → ${said(opened)}, the session stays in ${session.active_tenant?.code ?? "none"}.`,
        samuel,
      );
    },
  );
  await page.context().close();

  const admin = await sessions.blank("tomas");
  await record.check(
    {
      check: "L-4 a member of Avenmoor invited by another workspace",
      persona: "tomas",
      address: `POST /api/v1/users in ${second.name}; /approvals/requests/<her role request>; /settings/users`,
      expected:
        "Before she accepts, the inviting workspace is shown her address and nothing another workspace holds of her: the role request's summary, the member's read and list and the screens name the address, not the name Avenmoor holds (D-80 rule 5; 04 T-PLT-02 'What a workspace is shown of a person'; register index 298)",
    },
    async () =>
      invitedElsewhere(admin, new Api(await sessions.page("tomas")), second, (address, line) => {
        record.parked("tomas", address, line);
      }),
  );
  await admin.context().close();
}
