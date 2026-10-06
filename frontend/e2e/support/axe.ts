// Accessibility check (docs/dev-guide.md DG-E2E-07; PRD E2E-09, NFR-20; DESIGN_SYSTEM DS-VER-05).
// `check(page, surfaceId)` runs axe with the WCAG 2.0 to 2.2 A and AA tags in the light and the dark
// theme, writes the full results to `frontend/e2e/.results/axe/<spec slug>/<surface>.json` and fails
// on any violation of impact `serious` or `critical`.
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, type TestInfo } from "@playwright/test";
import type { AxeResults } from "axe-core";

import { normaliseKey, RESULTS_DIR, setTheme, specSlug, THEMES, type Theme } from "./screens";

export const AXE_TAGS: readonly string[] = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
export const BLOCKING_IMPACTS: ReadonlySet<string> = new Set(["serious", "critical"]);

export interface CheckOptions {
  /** A state slug when one surface is checked in several states, for example "session-expired". */
  readonly state?: string;
}

export interface BlockingViolation {
  readonly theme: Theme;
  readonly id: string;
  readonly impact: string;
  readonly help: string;
  readonly targets: readonly string[];
}

/** The serious and critical violations of one theme's results. */
export function blockingViolations(theme: Theme, results: AxeResults): BlockingViolation[] {
  return results.violations
    .filter((violation) => BLOCKING_IMPACTS.has(violation.impact ?? ""))
    .map((violation) => ({
      theme,
      id: violation.id,
      impact: violation.impact ?? "",
      help: violation.help,
      targets: violation.nodes.map((node) => node.target.join(" ")),
    }));
}

export async function check(
  page: Page,
  testInfo: TestInfo,
  surfaceId: string,
  options: CheckOptions = {},
): Promise<void> {
  const themes: Partial<Record<Theme, AxeResults>> = {};
  const blocking: BlockingViolation[] = [];
  const previous = await setTheme(page, "light");
  try {
    for (const theme of THEMES) {
      await setTheme(page, theme);
      const results = await new AxeBuilder({ page }).withTags([...AXE_TAGS]).analyze();
      themes[theme] = results;
      blocking.push(...blockingViolations(theme, results));
    }
  } finally {
    await setTheme(page, previous === "light" || previous === "dark" ? previous : null);
  }

  const directory = join(RESULTS_DIR, "axe", specSlug(testInfo.file));
  mkdirSync(directory, { recursive: true });
  const file = normaliseKey(
    options.state === undefined ? surfaceId : `${surfaceId}-${options.state}`,
  );
  writeFileSync(
    join(directory, `${file}.json`),
    `${JSON.stringify({ surface: surfaceId, state: options.state ?? null, url: page.url(), themes }, null, 2)}\n`,
  );
  expect(blocking, `serious or critical axe violations on ${surfaceId} (DG-E2E-07)`).toEqual([]);
}
