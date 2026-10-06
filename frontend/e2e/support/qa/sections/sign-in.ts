// Section S of the pass: every seeded member signs in through the screens, lands on Home, is offered
// the rail, and signs out. A member's sign-in is hers alone here — a new browser context, no stored
// session — so the record says what SF-22, the challenge of a factor and the workspace list each
// showed. The member for AVM-DE alone signs in under section G, where the pass makes her.
import type { Page } from "@playwright/test";

import { PERSONAS, SIGN_IN_PATH } from "../../auth";
import { Api, at, items, text } from "../api";
import type { Qa } from "../fixtures";
import { failuresText, look, open } from "../observe";
import { personaCredentials, sessionRead, signOut, type Trail, walkSignIn } from "../sessions";

/** SCREENS SCR-IA-01 and 03 REQ-UX-001: the ten destinations, in the rail's order. */
export const RAIL = [
  "Home",
  "Contracts",
  "Schedules",
  "Close",
  "Journals",
  "Reports",
  "Approvals",
  "Policies",
  "Data",
  "Settings",
] as const;

/** PRD BR-UX-04 with SCREENS SCR-PERM-06: the permissions that view records or run reports. */
const NON_COMMAND = new Set([
  "contract.read",
  "ssp.read",
  "config.read",
  "audit.read",
  "report.run",
  "report.export",
  "evidence.export",
  "ai.use",
]);

/** The names of the rail's links, as a screen reader hears them, without the pending count. */
export async function railOf(page: Page): Promise<readonly string[]> {
  const names = await page
    .getByRole("navigation", { name: "Primary" })
    .getByRole("link")
    .evaluateAll((elements) =>
      elements.map((element) =>
        (element.getAttribute("aria-label") ?? element.textContent ?? "")
          .replace(/\s+/g, " ")
          .trim(),
      ),
    )
    .catch(() => [] as string[]);
  return names.map((name) => name.replace(/, \d+ pending$/, ""));
}

export async function readOnlyChip(page: Page): Promise<boolean> {
  return (await page.getByText("Read-only access", { exact: true }).count()) > 0;
}

/** What a sign-in showed, as one sentence of the record. */
export function trailText(trail: Trail): string {
  return trail.steps.join("; ");
}

export async function signInSection({ record, sessions }: Qa): Promise<void> {
  for (const persona of PERSONAS) {
    const page = await sessions.blank(persona);
    let signedIn = false;
    await record.check(
      {
        check: "S-1 sign-in, landing and rail",
        persona,
        address: "/sign-in",
        expected:
          "SF-22 takes the password; a member with a factor is asked for a code and no other (03 REQ-PLT-005; PRD WLD-U-R2); a member of several workspaces chooses Avenmoor on SF-23:select, a member of one arrives in it (D-83); the landing is Home (RT-07) with the ten destinations of the rail (REQ-UX-001; SCR-IA-01); the Read-only access chip shows for a member without a command permission and for no other (BR-UX-04); no request the pages sent by themselves is refused",
      },
      async () => {
        const trail = await walkSignIn(page, personaCredentials(persona), persona);
        signedIn = true;
        // Where the sign-in left the window; then Home opened once more, so that the requests the
        // row judges are Home's own and not those of the pages before the session existed.
        const landing = await look(page, SIGN_IN_PATH);
        const seen = landing.landed.startsWith("/home")
          ? await open(page, landing.landed)
          : landing;
        const api = new Api(page);
        const me = (await api.get("/api/v1/me")).json;
        const permissions = items(me, "permissions").map(String);
        const enrolled = at(me, "mfa", "enrolled") === true;
        const rail = await railOf(page);
        const chip = await readOnlyChip(page);
        const chipExpected = !permissions.some((code) => !NON_COMMAND.has(code));
        // D-83: the workspaces a member can open are her ACTIVE memberships of ACTIVE workspaces.
        const memberships = items(me, "memberships").filter(
          (membership) =>
            text(membership, "status") === "ACTIVE" &&
            text(membership, "tenant", "status") === "ACTIVE",
        ).length;
        const problems: string[] = [];
        if (!landing.landed.startsWith("/home")) {
          problems.push(`the landing is ${landing.landed}, not Home`);
        }
        if (seen.state !== "rendered") {
          problems.push(`Home is in the state "${seen.state}" (${seen.heading})`);
        }
        if (rail.join("|") !== RAIL.join("|")) {
          problems.push(`the rail offers [${rail.join(", ")}]`);
        }
        if (trail.challenged !== enrolled) {
          problems.push(
            enrolled
              ? "a member with a confirmed factor was not asked for a code"
              : "a member without a factor was asked for a code",
          );
        }
        if ((trail.workspaces !== null) !== memberships > 1) {
          problems.push(
            `a member of ${String(memberships)} workspace(s) ${trail.workspaces === null ? "was not shown" : "was shown"} the workspace list`,
          );
        }
        if (chip !== chipExpected) {
          problems.push(
            `the Read-only access chip is ${chip ? "shown" : "not shown"} for a member ${chipExpected ? "without" : "with"} a command permission`,
          );
        }
        if (seen.failures.length > 0) {
          problems.push(`requests of Home refused or failed: ${failuresText(seen)}`);
        }
        const observed = `${trailText(trail)}; ${landing.landed}; heading "${seen.heading}"; rail ${String(rail.length)} destinations; factor ${enrolled ? "confirmed" : "none"}, ${trail.challenged ? "code asked" : "no code asked"}; ${String(memberships)} workspace(s); ${String(permissions.length)} permissions; Read-only access chip ${chip ? "shown" : "not shown"}; requests refused on the way in: ${failuresText(landing)}; on Home opened again: ${failuresText(seen)}`;
        if (problems.length === 0) {
          return { observed, result: "pass", page };
        }
        // A sign-in is a core flow: what keeps a member from her Home is a candidate of class 3;
        // anything else the row found is read by hand before it is called a finding.
        const stopped = !landing.landed.startsWith("/home") || seen.state !== "rendered";
        return {
          observed: `${problems.join("; ")}. ${observed}`,
          result: stopped ? "FINDING" : "seen once",
          finding: stopped ? "stopped flow" : undefined,
          page,
        };
      },
    );

    await record.check(
      {
        check: "S-2 sign-out",
        persona,
        address: "user menu → Sign out",
        expected:
          "The session ends on the server and the window stands on SF-22 (03 REQ-PLT-004 'Logout invalidates the session server-side'); an address typed afterwards leads to sign-in, not to the screen",
      },
      async () => {
        if (!signedIn) {
          return { observed: "the member was not signed in (S-1)", result: "not run" };
        }
        await signOut(page);
        const session = await sessionRead(page);
        const after = await open(page, "/contracts");
        const cleared = !session.authenticated && after.state === "sign-in";
        const observed = `after Sign out the window stands on ${new URL(page.url()).pathname}; GET /session says authenticated ${String(session.authenticated)}; /contracts typed afterwards lands on ${after.landed} (${after.state})`;
        return cleared
          ? { observed, result: "pass" }
          : { observed, result: "FINDING", finding: "bound", page };
      },
    );
    await page.context().close();
  }
}
