// The record of the release candidate's multi-role browser QA (PROGRESS.md, sequence D-99 (7);
// docs/qa/). One row per check — persona, address, expected with its reference, observed, result —
// in the form of docs/qa/G12-multi-role-qa-2026-09-17.md, written as the pass goes, so that a run
// that is cut short still leaves what it saw. A finding is of one of three classes and of no other:
// a wrong figure, a bound that does not hold, a core flow that stops. Everything else the pass sees
// is one line under "parked". The pass repairs nothing.
import {
  appendFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  writeFileSync,
} from "node:fs";
import { isAbsolute, join } from "node:path";

import type { Page } from "@playwright/test";

import { normaliseKey } from "../screens";
import { REPO_ROOT } from "../tenants";

/** The three classes of a finding (the supervisor's test for a release candidate). */
export type FindingClass = "wrong figure" | "bound" | "stopped flow";

export type Result =
  /** What was expected was observed. */
  | "pass"
  /** A candidate of one of the three classes, seen twice. */
  | "FINDING"
  /** Seen once and not a second time: written, not counted. */
  | "seen once"
  /** A known item of the register: named with its index, not reported again. */
  | "KNOWN"
  /** The check could not be made, and why. */
  | "not run";

export interface Row {
  readonly check: string;
  readonly persona: string;
  readonly address: string;
  /** What should be there, with the document that says so. */
  readonly expected: string;
  readonly observed: string;
  readonly result: Result;
  readonly finding?: FindingClass | undefined;
  /** The register index of a known item. */
  readonly known?: string | undefined;
  /** The capture of the page, under the record's directory. */
  readonly capture?: string | undefined;
  readonly at: string;
}

/** What a check answers: the row without what the runner knows already. */
export interface Outcome {
  readonly observed: string;
  readonly result: Result;
  readonly finding?: FindingClass | undefined;
  readonly known?: string | undefined;
  /** The page to capture with the row. */
  readonly page?: Page | undefined;
}

export interface CheckHead {
  readonly check: string;
  readonly persona: string;
  readonly address: string;
  readonly expected: string;
}

/** `${EREV_RUN_DIR}/qa-rc`, relative paths from the repository root: it outlives a gate context. */
export function recordRoot(): string {
  const runDir = process.env.EREV_RUN_DIR ?? ".run";
  return join(isAbsolute(runDir) ? runDir : join(REPO_ROOT, runDir), "qa-rc");
}

/**
 * No check of the pass takes this long: the longest wait in one is the fifteen minutes a job is
 * given. A check that stands still beyond it is left, its row says so, and the pass goes on — a
 * wait that never ends would otherwise hold its section until the test's timeout and take the
 * section's later rows with it (the rehearsal of 2026-10-03, round 2, section S).
 */
export const CHECK_CAP_MS = 20 * 60_000;

const ROWS_FILE = "rows.jsonl";
const PARKED_FILE = "parked.txt";
const NOTES_FILE = "notes.txt";
const STAMP = new Intl.DateTimeFormat("sv-SE", {
  timeZone: "UTC",
  dateStyle: "short",
  timeStyle: "medium",
});

/** The instant in UTC, `YYYY-MM-DDTHH:MM:SSZ` (DG-FE-20 keeps `Date` objects out of this code). */
export function utcNow(): string {
  return `${STAMP.format(Date.now()).replace(" ", "T")}Z`;
}

/** One line of text: runs of white space are one space. */
export function flat(text: string, limit = 600): string {
  const line = text.replace(/\s+/g, " ").trim();
  return line.length > limit ? `${line.slice(0, limit)}…` : line;
}

/** What went wrong, in one line, without the call log Playwright appends. */
export function errorLine(error: unknown): string {
  const text = error instanceof Error ? error.message : String(error);
  // eslint-disable-next-line no-control-regex -- the colour codes of Playwright's messages.
  return flat((text.split("Call log:")[0] ?? text).replace(/\u001b\[[0-9;]*m/g, ""), 500);
}

export class QaRecord {
  private captures = 0;

  constructor(readonly directory: string = recordRoot()) {
    mkdirSync(join(directory, "captures"), { recursive: true });
    this.captures = this.rows().filter((row) => row.capture !== undefined).length;
  }

  /**
   * Sets the record of another world aside and starts this one's (DG-E2E-14): the directory is
   * renamed to `<directory>-<label>` — nothing of it is removed, its captures stay until they are
   * read — and an empty one stands in its place. It answers the name the earlier record now has.
   */
  startOver(label: string): string {
    let aside = `${this.directory}-${label}`;
    for (let turn = 2; existsSync(aside); turn += 1) {
      aside = `${this.directory}-${label}-${String(turn)}`;
    }
    renameSync(this.directory, aside);
    mkdirSync(join(this.directory, "captures"), { recursive: true });
    this.captures = 0;
    return aside;
  }

  /** Writes one row; the row is on disk when the call returns. */
  row(row: Omit<Row, "at">): Row {
    const written: Row = { ...row, at: utcNow() };
    appendFileSync(join(this.directory, ROWS_FILE), `${JSON.stringify(written)}\n`);
    return written;
  }

  /** What the pass saw outside the three classes: one line, no analysis. */
  parked(persona: string, address: string, line: string): void {
    appendFileSync(join(this.directory, PARKED_FILE), `${persona} | ${address} | ${flat(line)}\n`);
  }

  /** A fact about the run itself: the head, the world, what a step showed. */
  note(line: string): void {
    appendFileSync(join(this.directory, NOTES_FILE), `${utcNow()} ${flat(line, 2_000)}\n`);
  }

  /** A full-page capture; the name says the check and the persona. */
  async capture(page: Page, check: string, persona: string): Promise<string> {
    this.captures += 1;
    const name = `${String(this.captures).padStart(3, "0")}-${normaliseKey(check).slice(0, 60)}-${normaliseKey(persona)}.png`;
    await page
      .screenshot({
        path: join(this.directory, "captures", name),
        fullPage: true,
        animations: "disabled",
        timeout: 15_000,
      })
      .catch(() => undefined);
    return `captures/${name}`;
  }

  /**
   * Runs one check and writes its row. A check that throws is "not run" with what it threw, and so
   * is a check that has not ended in `capMs`: the pass goes on, and the row says what to look at.
   */
  async check(
    head: CheckHead,
    run: () => Promise<Outcome>,
    capMs: number = CHECK_CAP_MS,
  ): Promise<Row> {
    let outcome: Outcome;
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const work = run();
      // A check that is left may still end, and may end in an error: that error is nobody's.
      work.catch(() => undefined);
      outcome = await Promise.race([
        work,
        new Promise<Outcome>((resolve) => {
          timer = setTimeout(() => {
            resolve({
              observed: `the check did not end in ${String(Math.round(capMs / 1000))} s and was left standing; the pass goes on`,
              result: "not run",
            });
          }, capMs);
        }),
      ]);
    } catch (error) {
      outcome = { observed: `the check stopped: ${errorLine(error)}`, result: "not run" };
    } finally {
      clearTimeout(timer);
    }
    const capture =
      outcome.page === undefined || outcome.page.isClosed()
        ? undefined
        : await this.capture(outcome.page, head.check, head.persona);
    return this.row({
      ...head,
      observed: flat(outcome.observed, 4_000),
      result: outcome.result,
      finding: outcome.finding,
      known: outcome.known,
      capture,
    });
  }

  rows(): Row[] {
    const file = join(this.directory, ROWS_FILE);
    if (!existsSync(file)) {
      return [];
    }
    return readFileSync(file, "utf8")
      .split("\n")
      .filter((line) => line.trim() !== "")
      .map((line) => JSON.parse(line) as Row);
  }

  /** The record as a table, for docs/qa/: rows in the order of the pass, then the parked lines. */
  writeMarkdown(title: string): string {
    const cell = (text: string) => text.replace(/\|/g, "\\|").replace(/\s+/g, " ").trim();
    const rows = this.rows();
    const lines = [
      `# ${title}`,
      "",
      "| Check | Persona | Address | Expected (reference) | Observed | Result |",
      "|---|---|---|---|---|---|",
      ...rows.map((row) => {
        const result =
          row.result === "FINDING"
            ? `FINDING (${row.finding ?? "unclassified"})`
            : row.result === "KNOWN"
              ? `KNOWN (index ${row.known ?? "?"})`
              : row.result;
        return `| ${cell(row.check)} | ${cell(row.persona)} | ${cell(row.address)} | ${cell(row.expected)} | ${cell(row.observed)} | ${result} |`;
      }),
      "",
    ];
    const parked = join(this.directory, PARKED_FILE);
    if (existsSync(parked)) {
      lines.push(
        "## Parked",
        "",
        ...readFileSync(parked, "utf8")
          .split("\n")
          .filter(Boolean)
          .map((line) => `- ${line}`),
        "",
      );
    }
    const file = join(this.directory, "record.md");
    writeFileSync(file, lines.join("\n"));
    return file;
  }
}
