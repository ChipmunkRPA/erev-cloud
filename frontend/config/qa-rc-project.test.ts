// The release candidate's multi-role browser QA (PROGRESS.md sequence D-99 (7); docs/dev-guide.md
// DG-E2E-14, rev 1.280; frontend/e2e/projects/qa-rc.spec.ts) is a project of the closed world that
// no run takes unless it is named: it invites a member and locks a month of the world it runs on,
// and its product is a record, not a verdict. Three things hold that. The Playwright configuration
// lists the project `qa-rc` in a CLOSE=1 run, behind `closed`, and in no other (what Playwright
// itself lists is asked in e2e-projects.test.ts). scripts/e2e.sh keeps the project in a list of its
// own, run by name only: a run without `PROJECT` never takes it, on either world; on the closed
// world `PROJECT` may name it, alone or with `closed`, and it then runs after `closed` with one
// worker; without CLOSE=1 the name is refused with the command that runs it — asked of the script
// itself, sourced as backend/tests/unit/test_e2e_script.py sources it ("Sourcing the script defines
// the functions and runs nothing"). And no make target names it.
import { spawnSync } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const ROOT = fileURLToPath(new URL("../..", import.meta.url));
const read = (path: string): string =>
  readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const CONFIG = read("../e2e/playwright.config.ts");
const MAKEFILE = read("../../Makefile");
const SPEC_FILES = readdirSync(fileURLToPath(new URL("../e2e/projects", import.meta.url))).filter(
  (name) => name.endsWith(".spec.ts"),
);
const QA = "qa-rc";
const RUN_IT = `make e2e CLOSE=1 PROJECT=${QA}`;

interface Project {
  readonly name: string;
  readonly testMatch: RegExp;
  readonly fullyParallel: boolean;
}

/** The projects a part of the Playwright config writes: `name: "…", testMatch: /…/, fullyParallel: …`. */
function projectsIn(text: string): readonly Project[] {
  return [
    ...text.matchAll(/name: "([^"]+)",\s+testMatch: \/(.+?)\/,\s+fullyParallel: (true|false)/g),
  ].map((match) => ({
    name: match[1] ?? "",
    testMatch: new RegExp(match[2] ?? ""),
    fullyParallel: match[3] === "true",
  }));
}

/** The two lists of `projects: CLOSED_WORLD ? [ … ] : [ … ]`: the closed world's, then the ordinary one. */
function worlds(): { readonly closed: readonly Project[]; readonly ordinary: readonly Project[] } {
  const lists = /projects: CLOSED_WORLD\s*\? \[(.*?)\]\s*: \[(.*?)\],\n\}\);/s.exec(CONFIG);
  return { closed: projectsIn(lists?.[1] ?? ""), ordinary: projectsIn(lists?.[2] ?? "") };
}

/** A function of scripts/e2e.sh, called in a shell that sourced the script, with `CLOSE` and `PROJECT` as given. */
function script(
  call: string,
  run: { readonly close?: boolean; readonly project?: string } = {},
): { readonly status: number | null; readonly out: string } {
  const env = { ...process.env };
  delete env.PROJECT;
  delete env.SPEC;
  delete env.CLOSE;
  const ran = spawnSync("bash", ["-c", `source scripts/e2e.sh && ${call}`], {
    cwd: ROOT,
    env: {
      ...env,
      ...(run.close === true ? { CLOSE: "1" } : {}),
      ...(run.project === undefined ? {} : { PROJECT: run.project }),
    },
    encoding: "utf8",
  });
  return { status: ran.status, out: `${ran.stdout}${ran.stderr}`.trim() };
}

const names = (out: string): readonly string[] => out.split("\n").filter((name) => name !== "");

describe("the multi-role browser QA of the release candidate (qa-rc)", () => {
  it("is a project of the closed world's configuration, behind closed, and of no other", () => {
    expect(SPEC_FILES).toContain(`${QA}.spec.ts`);
    const { closed, ordinary } = worlds();
    expect(closed.map((project) => project.name)).toEqual(["closed", QA]);
    expect(ordinary.length).toBeGreaterThan(1);
    // A project of the ordinary run that matched the file would run the pass with `make e2e`.
    expect(
      ordinary
        .filter((project) => project.testMatch.test(`${QA}.spec.ts`))
        .map((project) => project.name),
    ).toEqual([]);
    // Each project of either world takes a file of its own, and the pass is one worker's walk.
    for (const project of [...closed, ...ordinary]) {
      expect(SPEC_FILES.filter((name) => project.testMatch.test(name))).toEqual([
        `${project.name}.spec.ts`,
      ]);
    }
    expect(closed.find((project) => project.name === QA)?.fullyParallel).toBe(false);
    // A section is one test of many minutes: no trace is written while it runs (DG-E2E-14).
    expect(CONFIG).toMatch(/name: "qa-rc",[^}]*?\buse: \{ trace: "off" \}/);
  });

  it("is in the list of no run without PROJECT, on either world", () => {
    const ordinary = script("selected_projects");
    expect(ordinary.status).toBe(0);
    expect(names(ordinary.out).length).toBeGreaterThan(1);
    expect(names(ordinary.out)).not.toContain(QA);
    const closed = script("selected_projects", { close: true });
    expect(closed.status).toBe(0);
    expect(names(closed.out)).toEqual(["closed"]);
  });

  it("runs by name on the closed world, after closed, with one worker", () => {
    expect(script("validate_projects", { close: true, project: QA }).status).toBe(0);
    expect(names(script("selected_projects", { close: true, project: QA }).out)).toEqual([QA]);
    for (const project of [`closed,${QA}`, `${QA},closed`]) {
      expect(script("validate_projects", { close: true, project }).status).toBe(0);
      expect(names(script("selected_projects", { close: true, project }).out)).toEqual([
        "closed",
        QA,
      ]);
    }
    expect(script(`workers_of ${QA}`).out).toBe("1");
  });

  it("is refused by name without CLOSE=1, with the command that runs it", () => {
    const refused = script("validate_projects", { project: QA });
    expect(refused.status).toBe(1);
    expect(refused.out).toBe(`project ${QA} runs on the closed world only: ${RUN_IT}`);
    expect(script("selected_projects", { project: QA }).out).toBe("");
    // The control: a project of the ordinary list is taken, and refused on the closed world.
    expect(script("validate_projects", { project: "screens" }).status).toBe(0);
    expect(script("validate_projects", { close: true, project: "screens" }).status).toBe(1);
  });

  it("is named by no make target", () => {
    expect(MAKEFILE).not.toContain(QA);
  });
});
