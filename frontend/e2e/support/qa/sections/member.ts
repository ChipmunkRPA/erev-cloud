// Section G of the pass: the member for AVM-DE alone, made through the product. tomas invites her
// with one role for one legal entity (PRD J-22.1; 04 T-PLT-10), grace decides the request, the
// invitation's link is opened in a browser of her own, she chooses a password and is signed in. The
// record says what the invitation, the acceptance and the first session each showed: the seed gives
// every role for all entities (PRD §2.3), so no test has signed in a member of named entities.
import { randomUUID } from "node:crypto";

import type { Page } from "@playwright/test";

import { PERSONA_WORKSPACE } from "../../auth";
import { linkIn, waitForMail } from "../../mail";
import { Api, at, items, said, text } from "../api";
import type { Qa } from "../fixtures";
import { failuresText, look } from "../observe";
import { flat } from "../record";
import { arrive, LENA, patchState, readState, sessionRead, signOut, walkSignIn } from "../sessions";
import { approveOnScreen } from "../steps";
import { readEntities } from "../world";
import { railOf, RAIL, trailText } from "./sign-in";

/** The entity the member is given, and the role (PRD §5.6 default role of a preparer). */
export const HOME_ENTITY = "AVM-DE";
export const LENA_ROLE = "Revenue Accountant";

/** The options a segment of the context pill offers, read from its listbox and closed again. */
export async function pillOptions(
  page: Page,
  dimension: "Entity" | "Period" | "Book",
): Promise<readonly string[]> {
  const group = page.getByRole("group", { name: "Accounting context" });
  const segment = group.getByRole("button", { name: new RegExp(`^${dimension}: `) });
  if ((await segment.getAttribute("aria-disabled").catch(() => null)) === "true") {
    return [];
  }
  await segment.click();
  const options = await group
    .getByRole("listbox")
    .getByRole("option")
    .allInnerTexts()
    .catch(() => [] as string[]);
  await page.keyboard.press("Escape");
  return options.map((option) => flat(option, 80));
}

export async function pillText(page: Page): Promise<string> {
  const names = await page
    .getByRole("group", { name: "Accounting context" })
    .getByRole("button")
    .evaluateAll((elements) => elements.map((element) => element.getAttribute("aria-label") ?? ""))
    .catch(() => [] as string[]);
  return names.join("; ");
}

export async function memberSection({ record, sessions }: Qa): Promise<void> {
  let lena = readState().lena;
  const tomas = await sessions.page("tomas");
  const admin = new Api(tomas);

  if (lena === undefined) {
    const tag = randomUUID().slice(0, 8);
    lena = {
      email: `qa.lena.${tag}@demo.erev`,
      name: `Lena Brandt ${tag}`,
      password: `Qa-${randomUUID()}`,
      secret: null,
      lastStep: 0,
      membershipId: null,
      accepted: false,
    };
    patchState({ lena });
  }
  const member = lena;
  let requestId = "";

  await record.check(
    {
      check: "G-1 invitation for one entity",
      persona: "tomas",
      address: "/settings/users → Invite user",
      expected: `The drawer offers the role and, for a grantor who covers every entity, both scopes; "Selected entities" with ${HOME_ENTITY} sends one request that names the entity ("Grant <role> to <member> for <codes>", 04 T-PLT-10; PRD J-22.1) and the invitation waits for a second administrator (PRD BR-PLT-02 rev 1.33)`,
    },
    async () => {
      const users = await admin.list("/api/v1/users", { q: member.email });
      const existing = users.find((user) => text(user, "email") === member.email);
      if (existing !== undefined) {
        patchState({ lena: { ...member, membershipId: text(existing, "id") } });
        return {
          observed: `the member was invited in an earlier run of the pass on this world: status ${text(existing, "status")}`,
          result: "pass",
        };
      }
      await tomas.goto("/settings/users");
      await tomas.getByRole("button", { name: "Invite user" }).click();
      const drawer = tomas.getByRole("dialog", { name: "Invite user" });
      await drawer.getByLabel("Email").fill(member.email);
      await drawer.getByLabel("Display name").fill(member.name);
      await drawer.getByRole("combobox", { name: "Role" }).click();
      await tomas.getByRole("option", { name: LENA_ROLE, exact: true }).click();
      const scopes = await drawer
        .getByRole("radio")
        .evaluateAll((elements) =>
          elements.map((element) => (element.closest("label")?.textContent ?? "").trim()),
        );
      await drawer.getByRole("radio", { name: "Selected entities" }).check();
      await drawer.getByRole("combobox", { name: "Entities" }).fill(HOME_ENTITY);
      await tomas.getByRole("option", { name: new RegExp(`^${HOME_ENTITY} · `) }).click();
      await drawer.getByRole("button", { name: "Send invitation" }).click();
      const toast = tomas.getByText(`Invitation for ${member.email}`, { exact: false });
      await toast.first().waitFor({ state: "visible", timeout: 30_000 });
      const message = flat(await toast.first().innerText(), 200);
      const listed = await admin.list("/api/v1/users", { q: member.email });
      const made = listed.find((user) => text(user, "email") === member.email);
      const role = at(made, "roles", 0);
      patchState({ lena: { ...member, membershipId: text(made, "id") } });
      const scope = items(role, "entities")
        .map((entity) => text(entity, "code"))
        .join(", ");
      const observed = `scopes offered: [${scopes.join(", ")}]; toast "${message}"; the member is listed ${text(made, "status")} with ${text(role, "role", "name")} ${text(role, "status")} for [${scope}] (all entities: ${String(at(role, "is_all_entities"))})`;
      const named = scope === HOME_ENTITY && at(role, "is_all_entities") === false;
      return named
        ? { observed, result: "pass", page: tomas }
        : { observed, result: "FINDING", finding: "bound", page: tomas };
    },
  );

  await record.check(
    {
      check: "G-2 the second administrator decides",
      persona: "grace",
      address: "/approvals/requests/<the role request>",
      expected:
        "The request names the member, the role and the entity; grace approves it with a fresh code (PRD BR-PLT-06); the role is then ACTIVE for AVM-DE on the member's page and the invitation email goes out (04 T-PLT-07)",
    },
    async () => {
      const state = readState().lena ?? member;
      const user = (await admin.get(`/api/v1/users/${state.membershipId ?? ""}`)).json;
      const role = at(user, "roles", 0);
      requestId = text(role, "approval_request_id");
      if (text(role, "status") === "ACTIVE") {
        return {
          observed: "the role is ACTIVE already (an earlier run of the pass)",
          result: "pass",
        };
      }
      if (requestId === "") {
        return {
          observed: `the member's role names no approval request: status ${text(role, "status")}`,
          result: "FINDING",
          finding: "stopped flow",
        };
      }
      const grace = await sessions.page("grace");
      const request = (await new Api(grace).get(`/api/v1/approvals/${requestId}`)).json;
      const decided = await approveOnScreen(
        grace,
        "grace",
        requestId,
        `${LENA_ROLE} for ${HOME_ENTITY} as requested.`,
      );
      const after = (await admin.get(`/api/v1/users/${state.membershipId ?? ""}`)).json;
      const granted = at(after, "roles", 0);
      const summary = text(request, "summary");
      const observed = `request ${text(request, "request_no")} "${summary}", entities [${items(
        request,
        "entities",
      )
        .map((entity) => text(entity, "code"))
        .join(
          ", ",
        )}]; ${decided.stepUp ? "a code was asked" : "no code was asked"}; toast "${decided.toast}"; the role is ${text(granted, "status")} for [${items(
        granted,
        "entities",
      )
        .map((entity) => text(entity, "code"))
        .join(", ")}]`;
      const ok = text(granted, "status") === "ACTIVE" && summary.includes(HOME_ENTITY);
      return ok
        ? { observed, result: "pass", page: grace }
        : { observed, result: "FINDING", finding: "stopped flow", page: grace };
    },
  );

  const page = await sessions.blank(LENA);
  let accepted = (readState().lena ?? member).accepted;
  await record.check(
    {
      check: "G-3 acceptance",
      persona: LENA,
      address: "/accept-invitation#token=<token>",
      expected:
        'The email carries one link to SF-22:accept-invitation; the page says "<inviter> invited <email> to <workspace>." and asks a new member for a password twice (SCREENS_B §12.3; 03 REQ-PLT-004); "Accept invitation" opens her session and applies the landing rules of §12.1',
    },
    async () => {
      if (accepted) {
        return {
          observed: "the invitation was accepted in an earlier run of the pass",
          result: "pass",
        };
      }
      // The outbox is relayed by the worker once a minute (frontend/e2e/projects/screens.spec.ts,
      // `setupCaptureSession`): the wait covers two sweeps.
      const mail = await waitForMail({ tenant: PERSONA_WORKSPACE.code, to: member.email }, 150_000);
      const link = linkIn(mail, "/accept-invitation");
      await page.goto(link);
      const heading = page.getByTestId("SF-22-invitation-heading");
      await heading.waitFor({ state: "visible", timeout: 30_000 });
      const invited = flat(await heading.innerText(), 200);
      await page.getByLabel("Choose a password").fill(member.password);
      await page.getByLabel("Confirm password").fill(member.password);
      await page.getByRole("button", { name: "Accept invitation" }).click();
      await arrive(page, (url) => url.pathname !== "/accept-invitation");
      accepted = true;
      patchState({ lena: { ...(readState().lena ?? member), accepted: true } });
      const session = await sessionRead(page);
      const observed = `mail "${mail.subject}" to ${mail.to}; the page says "${invited}"; after "Accept invitation" the window stands on ${new URL(page.url()).pathname}; session authenticated ${String(session.authenticated)}, workspace ${session.active_tenant?.code ?? "none"}, factor to enrol ${String(session.mfa_enrolment_required ?? false)}`;
      return session.authenticated
        ? { observed, result: "pass", page }
        : { observed, result: "FINDING", finding: "stopped flow", page };
    },
  );

  await record.check(
    {
      check: "G-4 the first session of a member of one entity",
      persona: LENA,
      address: "/home",
      expected: `Home (RT-07) with the ten destinations; GET /me holds every permission of the role for ${HOME_ENTITY} and for no other entity (04 API-S-Me permission_scopes; 03 REQ-PLT-012); the context pill stands on ${HOME_ENTITY} and offers no other entity (PRD BR-UX-01: "the first entity in the user's scope"); no request of the page is refused`,
    },
    async () => {
      if (!accepted) {
        return { observed: "the invitation was not accepted (G-3)", result: "not run" };
      }
      // A session the acceptance did not open, or one that still owes a factor, is walked from
      // SF-22: the walk enrols a factor where the roles ask for one.
      const opened = await sessionRead(page);
      let onTheWay = "";
      if (
        new URL(page.url()).pathname === "/accept-invitation" ||
        !opened.authenticated ||
        opened.mfa_enrolment_required === true ||
        opened.mfa_required === true
      ) {
        const trail = await walkSignIn(page, readState().lena ?? member);
        onTheWay = `the session of the acceptance was not usable as it stood (authenticated ${String(opened.authenticated)}, factor to enrol ${String(opened.mfa_enrolment_required ?? false)}); a sign-in followed: ${trail.steps.join("; ")}. `;
        patchState({
          lena: {
            ...(readState().lena ?? member),
            secret: trail.enrolled ?? member.secret,
            lastStep: trail.lastStep,
          },
        });
      }
      const seen = await look(page, "/home");
      const api = new Api(page);
      const me = (await api.get("/api/v1/me")).json;
      const entities = await readEntities(admin);
      const home = entities.find((entity) => entity.code === HOME_ENTITY);
      const scopes = (at(me, "permission_scopes") ?? {}) as Record<string, unknown>;
      const wide = Object.entries(scopes).filter(
        ([, scope]) => !(Array.isArray(scope) && scope.length === 1 && scope[0] === home?.id),
      );
      const rail = await railOf(page);
      const pill = await pillText(page);
      const offered = await pillOptions(page, "Entity");
      const listed = await api.get("/api/v1/entities", { limit: 200 });
      const codes = items(listed.json).map((entity) => text(entity, "code"));
      // A permission held for more than her entity, or another entity's record in the catalogue she
      // is answered, crosses the bound. A name among the options of the pill is said and read by
      // hand, as in section K.
      const problems: string[] = [];
      const offers: string[] = [];
      if (wide.length > 0) {
        problems.push(
          `permissions not held for ${HOME_ENTITY} alone: ${wide.map(([code, scope]) => `${code}=${JSON.stringify(scope)}`).join(", ")}`,
        );
      }
      if (offered.some((option) => !option.startsWith(HOME_ENTITY))) {
        offers.push(`the context pill offers [${offered.join(" | ")}]`);
      }
      if (codes.some((code) => code !== HOME_ENTITY)) {
        problems.push(`GET /entities answers ${said(listed)} with [${codes.join(", ")}]`);
      }
      const observed = `${onTheWay}landed ${seen.landed} ("${seen.heading}", ${seen.state}); rail ${rail.join("|") === RAIL.join("|") ? "the ten destinations" : `[${rail.join(", ")}]`}; ${String(Object.keys(scopes).length)} permissions, entity_scope ${JSON.stringify(at(me, "entity_scope"))}; context pill "${pill}", entity options [${offered.join(" | ")}]; GET /entities lists [${codes.join(", ")}]; ${String(items(me, "memberships").length)} workspace(s); refused requests: ${failuresText(seen)}`;
      await sessions.keep(page);
      if (problems.length > 0) {
        return {
          observed: `${[...problems, ...offers].join("; ")}. ${observed}`,
          result: "FINDING",
          finding: "bound",
          page,
        };
      }
      if (offers.length > 0) {
        return { observed: `${offers.join("; ")}. ${observed}`, result: "seen once", page };
      }
      return seen.state === "rendered" && seen.failures.length === 0
        ? { observed, result: "pass", page }
        : { observed, result: "seen once", page };
    },
  );

  await record.check(
    {
      check: "G-5 sign-out and a sign-in with the chosen password",
      persona: LENA,
      address: "/sign-in",
      expected:
        "The password chosen on acceptance signs her in; a role that asks for no factor asks for none (03 REQ-PLT-005: Revenue Accountant is not among the roles that must enrol); she arrives in her one workspace without the list (D-83)",
    },
    async () => {
      if (!accepted) {
        return { observed: "the invitation was not accepted (G-3)", result: "not run" };
      }
      await signOut(page);
      const state = readState().lena ?? member;
      const trail = await walkSignIn(page, state);
      patchState({
        lena: { ...state, secret: trail.enrolled ?? state.secret, lastStep: trail.lastStep },
      });
      await sessions.keep(page);
      const observed = `${trailText(trail)}; ${trail.landed}; factor ${trail.enrolled === null ? "not asked for" : "enrolled on the way"}; workspace list ${trail.workspaces === null ? "not shown" : "shown"}`;
      return trail.landed.startsWith("/home")
        ? { observed, result: "pass", page }
        : { observed, result: "FINDING", finding: "stopped flow", page };
    },
  );
}
