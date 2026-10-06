// DG-E2E-02 rev 1.277 (docs/dev-guide.md §9.8): the Playwright projects of a run. `make e2e CLOSE=1`
// seeds the world with its closed months, and scripts/e2e.sh names that run to the configuration with
// EREV_E2E_CLOSE=1 — and clears the variable for every other run (backend/tests/unit/
// test_e2e_script.py). The ordinary e2e therefore neither lists nor runs the project `closed`, whose
// rows need a lock, and a closed-world run lists nothing else, whose rows need every period open.
// Rev 1.280: the closed world has a second project, `qa-rc` (DG-E2E-14), which the configuration
// lists there beside `closed`; that the script runs it only when `PROJECT` names it is held by the
// script's own test.
// What Playwright itself lists is asked here, with the terminal's reporter: the configured JSON
// reporter writes the gate's report file.
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const FRONTEND = fileURLToPath(new URL("..", import.meta.url));
const PLAYWRIGHT = createRequire(import.meta.url).resolve("@playwright/test/cli");
const VARIABLE = "EREV_E2E_CLOSE";
/** DG-E2E-02: the projects of the open world, in execution order. */
const ORDINARY = ["avenmoor-serial", "fresh-tenant", "industry", "screens", "design", "crawl"];
/**
 * DG-E2E-02: the projects of the closed world, in execution order, each with the files its tests are
 * declared in. A project that joins that world is a row here.
 */
const CLOSED_WORLD: readonly (readonly [project: string, files: RegExp])[] = [
  ["closed", /^closed\.spec\.ts$/],
  ["qa-rc", /^qa-rc\.spec\.ts$/],
];
/** A listing transforms every spec file: seconds, more on a busy machine. */
const LISTING_TIMEOUT_MS = 120_000;

interface Listed {
  readonly project: string;
  readonly file: string;
}

interface Listing {
  /** The "Total: N tests" figure, which scripts/e2e.sh reads too. */
  readonly total: number;
  readonly tests: readonly Listed[];
}

/** `playwright test --list` with the variable set to `close`, or without it. */
function listing(close: string | undefined): Listing {
  const env: NodeJS.ProcessEnv = {};
  for (const [key, value] of Object.entries(process.env)) {
    // The runner's own variables are not the child's: Playwright is no test of this suite.
    if (key !== VARIABLE && key !== "JEST_WORKER_ID" && !key.startsWith("VITEST")) {
      env[key] = value;
    }
  }
  if (close !== undefined) {
    env[VARIABLE] = close;
  }
  const output = execFileSync(
    process.execPath,
    [PLAYWRIGHT, "test", "-c", "e2e/playwright.config.ts", "--list", "--reporter=list"],
    { cwd: FRONTEND, env, encoding: "utf8", timeout: LISTING_TIMEOUT_MS },
  );
  const total = /^Total: (\d+) tests? in \d+ files?$/m.exec(output);
  if (total === null) {
    throw new Error(`playwright test --list printed no total:\n${output}`);
  }
  // "  [<project>] › <file>:<line>:<column> › <titles>"; a journey's file stands beside the spec's
  // directory ("../journeys/…").
  const tests = [...output.matchAll(/^ {2}\[([a-z-]+)\] › (\S+):\d+:\d+ › /gm)].map(
    ([, project = "", file = ""]) => ({ project, file }),
  );
  return { total: Number(total[1]), tests };
}

/** The row of the closed world a listed test belongs to, by its file. */
function closedWorldOf(test: Listed): string | undefined {
  return CLOSED_WORLD.find(([, files]) => files.test(test.file))?.[0];
}

describe("DG-E2E-02: the projects of the closed world", () => {
  it(
    "an ordinary run lists tests of the six projects and none of the closed world's",
    () => {
      const ordinary = listing(undefined);
      expect(ordinary.total).toBeGreaterThan(0);
      // Every listed test was read, so the two checks below are of the whole listing.
      expect(ordinary.tests).toHaveLength(ordinary.total);
      expect(ordinary.tests.filter((test) => !ORDINARY.includes(test.project))).toEqual([]);
      expect(ordinary.tests.filter((test) => closedWorldOf(test) !== undefined)).toEqual([]);
      // Only "1" asks for the closed world: any other value is the ordinary run, test for test.
      expect(listing("0")).toEqual(ordinary);
    },
    LISTING_TIMEOUT_MS * 2,
  );

  it(
    "a CLOSE=1 run lists the projects of the closed world alone, each with its own files' tests",
    () => {
      const closed = listing("1");
      expect(closed.total).toBeGreaterThan(0);
      expect(closed.tests).toHaveLength(closed.total);
      // No test of another project, none under a project that is not its file's, and every project
      // of the table with a test.
      expect(closed.tests.filter((test) => closedWorldOf(test) !== test.project)).toEqual([]);
      expect([...new Set(closed.tests.map((test) => test.project))]).toEqual(
        CLOSED_WORLD.map(([project]) => project),
      );
    },
    LISTING_TIMEOUT_MS,
  );
});
