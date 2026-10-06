// The release candidate's multi-role browser QA, core depth (PROGRESS.md, sequence D-99 (7); the
// supervisor's acceptance of 2026-10-02; record form of docs/qa/G12-multi-role-qa-2026-09-17.md).
// Twelve members — the eleven personas of the demo world and one the pass makes through the product,
// invited for AVM-DE alone — walk the product as built on a world seeded with its close (PRD §2.2
// WLD-P-02 rev 1.162: AVM-US closed January to August 2026, September open).
//
// The pass is not a gate and is not part of `make e2e`: no project of the ordinary configuration
// takes this file and scripts/e2e.sh neither lists nor runs it (frontend/config/qa-rc-project.test.ts
// holds that), because it changes the world for good — it locks September — and because its product
// is a record, not a verdict. It is run by hand, one worker, as project `qa-rc` on a stack seeded
// with the close. A test here does not assert the product. Every check writes one row to
// `${EREV_RUN_DIR}/qa-rc/rows.jsonl` — persona, address, expected with its reference, observed,
// result — and the pass goes on, so that one finding does not hide the next. A finding is of three
// classes and no other: a wrong figure, a bound that does not hold, a core flow that stops; each is
// read a second time before its row says FINDING, and the pass repairs nothing. What it sees outside
// the three classes is one parked line.
//
// The sections run in this order, one worker, each in its own test so that a section that breaks
// ends alone. The bounds come first, then the two flows — the contract before the close, which
// takes its September revenue into the month it locks — and last what reads a world at rest:
//   [S] sign-in, landing, rail and sign-out of every seeded member
//   [G] the member for AVM-DE alone: invitation, approval, acceptance, first session
//   [K] the entity bound, as that member
//   [L] the workspace bound, as maya and samuel
//   [A] one contract from draft to revenue
//   [C] September's close to its lock
//   [P] where a lock request is decided: the request's own screen, read and not pressed
//   [M] denial per member, read against the permission catalogue
//   [E] the figures of the months the seed closed
// A section is run alone with `--grep "\[K\]"`; [K] and [M] need the member of [G], which the pass
// keeps in `${EREV_RUN_DIR}/qa-rc/state.json`.
import { Api, items, text } from "../support/qa/api";
import { expect, type Qa, test } from "../support/qa/fixtures";
import { errorLine } from "../support/qa/record";
import { closeSection } from "../support/qa/sections/close";
import { contractSection } from "../support/qa/sections/contract";
import { denialSection } from "../support/qa/sections/denial";
import { entityBoundSection } from "../support/qa/sections/entity-bound";
import { figuresSection } from "../support/qa/sections/figures";
import { lockScreensSection } from "../support/qa/sections/lock-screens";
import { memberSection } from "../support/qa/sections/member";
import { signInSection } from "../support/qa/sections/sign-in";
import { workspaceBoundSection } from "../support/qa/sections/workspace-bound";
import { patchState, readState } from "../support/qa/sessions";
import { BOOK } from "../support/qa/world";

const MINUTE = 60_000;

/**
 * Runs one section. A check of a section never throws; what does is the section's own ground — a
 * member who cannot sign in, a world that holds no entity — and is written as a row before the test
 * fails with it, so that the record says why its rows are missing.
 */
async function section(qa: Qa, name: string, run: (qa: Qa) => Promise<void>): Promise<void> {
  try {
    await run(qa);
  } catch (error) {
    qa.record.row({
      check: `${name} the section`,
      persona: "the pass",
      address: "the section's own steps, outside a check",
      expected: "the section runs to its end",
      observed: `the section stopped: ${errorLine(error)}`,
      result: "not run",
    });
    throw error;
  }
}

test.describe("qa-rc: the release candidate's multi-role browser QA, core", () => {
  test("[0] the world of the pass", async ({ qa }) => {
    const api = new Api(await qa.sessions.page("maya"));
    // A record is of one world. The run directory outlives a stack (DG-E2E-14): rows and a state
    // of a world seeded before this one — its member, its contract — are set aside, not read.
    const world = text((await api.get("/api/v1/session")).json, "active_tenant", "id");
    const earlier = readState().world;
    let aside = "";
    if (
      world !== "" &&
      earlier !== world &&
      (earlier !== undefined || qa.record.rows().length > 0)
    ) {
      aside = qa.record.startOver(earlier === undefined ? "earlier" : earlier.slice(0, 8));
    }
    if (world !== "") {
      patchState({ world });
    }
    const me = (await api.get("/api/v1/me")).json;
    // The head under test is the commit the stack was built from, as the API states it. A runner
    // that names a commit of its own (EREV_QA_HEAD) is said beside it where the two differ.
    const build = text(me, "engine_release", "build_sha");
    const named = process.env.EREV_QA_HEAD ?? "";
    const head =
      build === ""
        ? named || "not named"
        : named === "" || build.startsWith(named)
          ? build
          : `${build} (the runner names ${named})`;
    const entities = await api.list("/api/v1/entities");
    const periods = await api.list("/api/v1/periods", { entity: "AVM-US", book: BOOK });
    const year = periods.filter((period) => text(period, "period", "fiscal_year") === "2026");
    const states = year.map(
      (period) => `${text(period, "period", "period_key").slice(-3)} ${text(period, "state")}`,
    );
    // A month the closed world's own project has locked for good is a closed month too.
    const closed = year.filter((period) =>
      ["closed", "permanently_locked"].includes(text(period, "state")),
    ).length;
    const open = year.filter((period) => text(period, "state") === "open").length;
    // The first line of the record: the head the pass ran on and the world it found.
    qa.record.row({
      check: "0 the head and the world of the pass",
      persona: "the pass",
      address: "GET /api/v1/me, /entities, /periods",
      expected:
        "A world seeded with its close (PRD §2.2 WLD-P-02 rev 1.162): AVM-US closed January to August 2026 in ASC 606, September open",
      observed: `head ${head}; engine ${text(me, "engine_release", "engine_version")}, schema ${text(me, "engine_release", "schema_revision")}; ${String(items(me, "memberships").length)} workspaces for maya; Avenmoor entities [${entities.map((entity) => text(entity, "code")).join(", ")}]; AVM-US ${BOOK} 2026: ${states.join(", ")}${aside === "" ? "" : `; the record of an earlier world was set aside as ${aside.split("/").at(-1) ?? aside}`}`,
      result: closed === 8 && open >= 1 ? "pass" : "not run",
    });
    expect(entities.length, "the world holds the entities of Avenmoor").toBeGreaterThan(0);
  });

  test("[S] every seeded member signs in, lands on Home and signs out", async ({ qa }) => {
    test.setTimeout(30 * MINUTE);
    await section(qa, "S", signInSection);
  });

  test("[G] the member for AVM-DE alone: invitation, approval, acceptance, first session", async ({
    qa,
  }) => {
    test.setTimeout(20 * MINUTE);
    await section(qa, "G", memberSection);
  });

  test("[K] the entity bound, as the member for AVM-DE alone", async ({ qa }) => {
    test.setTimeout(75 * MINUTE);
    await section(qa, "K", entityBoundSection);
  });

  test("[L] the workspace bound, as maya and samuel", async ({ qa }) => {
    test.setTimeout(25 * MINUTE);
    await section(qa, "L", workspaceBoundSection);
  });

  test("[A] one contract from draft to revenue", async ({ qa }) => {
    test.setTimeout(30 * MINUTE);
    await section(qa, "A", contractSection);
  });

  test("[C] September's close to its lock", async ({ qa }) => {
    test.setTimeout(90 * MINUTE);
    await section(qa, "C", closeSection);
  });

  test("[P] where a lock request is decided", async ({ qa }) => {
    test.setTimeout(10 * MINUTE);
    await section(qa, "P", lockScreensSection);
  });

  test("[M] denial per member, read against the permission catalogue", async ({ qa }) => {
    test.setTimeout(60 * MINUTE);
    await section(qa, "M", denialSection);
  });

  test("[E] the figures of the closed periods", async ({ qa }) => {
    test.setTimeout(40 * MINUTE);
    await section(qa, "E", figuresSection);
  });

  test("[Z] the record", ({ qa }) => {
    const rows = qa.record.rows();
    const file = qa.record.writeMarkdown(
      "Release candidate multi-role browser QA: the rows of the pass",
    );
    const count = (result: string) => rows.filter((row) => row.result === result).length;
    console.log(
      `qa-rc: ${String(rows.length)} rows: ${String(count("pass"))} pass, ${String(count("FINDING"))} FINDING, ${String(count("seen once"))} seen once, ${String(count("KNOWN"))} KNOWN, ${String(count("not run"))} not run; ${file}`,
    );
    for (const row of rows.filter((item) => item.result === "FINDING")) {
      console.log(`  FINDING (${row.finding ?? "unclassified"}) ${row.check} as ${row.persona}`);
    }
    expect(rows.length, "the pass wrote its rows").toBeGreaterThan(0);
  });
});
