// Screenshots for designer review (docs/dev-guide.md DG-E2E-06; SCREENS SCR-TID-05; PHASES BS-D-09).
// `capture(page, name)` waits for the fonts, asserts Inter is loaded, masks `[data-volatile]` elements,
// disables animations and writes `frontend/e2e/.screens/<spec slug>/<nn>-<name>.light.png` and
// `….dark.png` by setting `data-theme` on `<html>`, then records both files in
// `frontend/e2e/.screens/index.json`. Screenshots are never asserted pixel by pixel.
import { existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { basename, join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, type Page, type TestInfo } from "@playwright/test";

export const E2E_DIR = fileURLToPath(new URL("..", import.meta.url));
export const SCREENS_DIR = join(E2E_DIR, ".screens");
export const RESULTS_DIR = join(E2E_DIR, ".results");
export const INDEX_FILE = join(SCREENS_DIR, "index.json");

export const THEMES = ["light", "dark"] as const;
export type Theme = (typeof THEMES)[number];

/** BS-D-09: the SCR-TID-03 normalisation of the screen id plus an optional state slug. */
export const CAPTURE_NAME = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const LOCK_WAIT_MS = 25;
const LOCK_TIMEOUT_MS = 10_000;

export interface CaptureOptions {
  /** The SCREENS surface id, for example "SF-22" or "SF-22:mfa-challenge". */
  readonly surface?: string;
  /** The journey step id, for example "J-05-AC-2". */
  readonly step?: string;
}

export interface ScreenEntry {
  readonly spec: string;
  readonly name: string;
  readonly journey: string | null;
  readonly step: string | null;
  readonly surface: string | null;
  readonly light: string;
  readonly dark: string;
}

/** SCREENS SCR-TID-03: lowercase, runs outside `[a-z0-9]` become one hyphen, no edge hyphens. */
export function normaliseKey(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** The spec slug of a spec file: its name without `.spec.ts`. */
export function specSlug(file: string): string {
  return basename(file).replace(/\.spec\.ts$/, "");
}

/** The PRD journey of a test: the first describe title that starts with a journey id. */
export function journeyOf(titlePath: readonly string[]): string | null {
  const title = titlePath.find((part) => /^J-\d{2}\b/.test(part));
  return title === undefined ? null : (/^J-\d{2}/.exec(title)?.[0] ?? null);
}

function sleep(ms: number): void {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

/** Runs `action` holding a directory lock, so workers never interleave index updates. */
export function withDirectoryLock<T>(lock: string, action: () => T): T {
  const started = Date.now();
  for (;;) {
    try {
      mkdirSync(lock);
      break;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") {
        throw error;
      }
      if (Date.now() - started > LOCK_TIMEOUT_MS) {
        throw new Error(`lock ${lock} held for more than ${String(LOCK_TIMEOUT_MS)} ms`, {
          cause: error,
        });
      }
      sleep(LOCK_WAIT_MS);
    }
  }
  try {
    return action();
  } finally {
    rmSync(lock, { recursive: true, force: true });
  }
}

function readIndex(): ScreenEntry[] {
  if (!existsSync(INDEX_FILE)) {
    return [];
  }
  return JSON.parse(readFileSync(INDEX_FILE, "utf8")) as ScreenEntry[];
}

function writeIndex(entries: readonly ScreenEntry[]): void {
  const partial = `${INDEX_FILE}.${String(process.pid)}.partial`;
  writeFileSync(partial, `${JSON.stringify(entries, null, 2)}\n`);
  renameSync(partial, INDEX_FILE);
}

/**
 * The file stem `<nn>-<name>` of a capture. A name captured before in the same spec keeps its number,
 * so a repeated run replaces its files; a new name takes the next number.
 */
function reserveStem(spec: string, name: string): string {
  return withDirectoryLock(join(SCREENS_DIR, ".index.lock"), () => {
    const entries = readIndex();
    const earlier = entries.find((entry) => entry.spec === spec && entry.name === name);
    if (earlier !== undefined) {
      return basename(earlier.light).replace(/\.light\.png$/, "");
    }
    const count = entries.filter((entry) => entry.spec === spec).length;
    const stem = `${String(count + 1).padStart(2, "0")}-${name}`;
    const placeholder: ScreenEntry = {
      spec,
      name,
      journey: null,
      step: null,
      surface: null,
      light: `${spec}/${stem}.light.png`,
      dark: `${spec}/${stem}.dark.png`,
    };
    writeIndex([...entries, placeholder]);
    return stem;
  });
}

function recordEntry(entry: ScreenEntry): void {
  withDirectoryLock(join(SCREENS_DIR, ".index.lock"), () => {
    const others = readIndex().filter(
      (item) => !(item.spec === entry.spec && item.name === entry.name),
    );
    writeIndex([...others, entry]);
  });
}

/** Waits for two animation frames, so a theme change has painted. */
export async function nextFrames(page: Page): Promise<void> {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            resolve();
          });
        });
      }),
  );
}

/** Sets `data-theme` on `<html>` (DG-FE-13) and waits for the repaint; returns the previous value. */
export async function setTheme(page: Page, theme: Theme | null): Promise<string | null> {
  const previous = await page.evaluate((next) => {
    const root = document.documentElement;
    const before = root.getAttribute("data-theme");
    if (next === null) {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", next);
    }
    return before;
  }, theme);
  await nextFrames(page);
  return previous;
}

export async function capture(
  page: Page,
  testInfo: TestInfo,
  name: string,
  options: CaptureOptions = {},
): Promise<ScreenEntry> {
  expect(name, "capture names follow BS-D-09").toMatch(CAPTURE_NAME);
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
  const interLoaded = await page.evaluate(() =>
    Array.from(document.fonts).some(
      (face) => face.family.replace(/["']/g, "") === "Inter" && face.status === "loaded",
    ),
  );
  expect(interLoaded, "the Inter font is loaded (DG-E2E-06)").toBe(true);

  const spec = specSlug(testInfo.file);
  mkdirSync(join(SCREENS_DIR, spec), { recursive: true });
  const stem = reserveStem(spec, name);
  const previous = await setTheme(page, "light");
  try {
    for (const theme of THEMES) {
      await setTheme(page, theme);
      await page.screenshot({
        path: join(SCREENS_DIR, spec, `${stem}.${theme}.png`),
        fullPage: true,
        animations: "disabled",
        caret: "hide",
        mask: [page.locator("[data-volatile]")],
      });
    }
  } finally {
    await setTheme(page, previous === "light" || previous === "dark" ? previous : null);
  }
  const entry: ScreenEntry = {
    spec,
    name,
    journey: journeyOf(testInfo.titlePath),
    step: options.step ?? null,
    surface: options.surface ?? null,
    light: `${spec}/${stem}.light.png`,
    dark: `${spec}/${stem}.dark.png`,
  };
  recordEntry(entry);
  return entry;
}
