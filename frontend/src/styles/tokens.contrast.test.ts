// DS-VER-01 (docs/design/DESIGN_SYSTEM.md §13): every pair of the §2.6 contrast table, computed from
// tokens.css with the DS-COL-02 algorithm, meets its requirement and equals the tabulated ratio.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { contrastRatio, readTokens, type Theme, tokenRgb } from "../../config/colour";

const TOKENS = fileURLToPath(new URL("./tokens.css", import.meta.url));
const DESIGN_SYSTEM = fileURLToPath(
  new URL("../../../docs/design/DESIGN_SYSTEM.md", import.meta.url),
);

interface Pair {
  id: string;
  foreground: string;
  background: string;
  required: number | null;
  light: number;
  dark: number;
}

const ROW =
  /^\| (C\d{2}) \| `(--[\w-]+)` \| `(--[\w-]+)` \| [^|]+ \| (4\.5:1|3:1|—) \| ([\d.]+) \| ([\d.]+) \| (?:Pass|Not required) \|$/;

function contrastTable(): Pair[] {
  const markdown = readFileSync(DESIGN_SYSTEM, "utf8");
  const section = markdown.slice(
    markdown.indexOf("### 2.6 Contrast table"),
    markdown.indexOf("### 2.7 Usage rules"),
  );
  return section.split("\n").flatMap((line) => {
    const match = ROW.exec(line);
    if (match === null) {
      return [];
    }
    const [, id, foreground, background, required, light, dark] = match as unknown as string[];
    return [
      {
        id: id as string,
        foreground: foreground as string,
        background: background as string,
        required: required === "—" ? null : Number((required as string).split(":")[0]),
        light: Number(light),
        dark: Number(dark),
      },
    ];
  });
}

const PAIRS = contrastTable();
const THEMES: Theme[] = ["light", "dark"];

describe("DS-VER-01", () => {
  it("reads the 81 rows of the §2.6 table, 72 of them required", () => {
    expect(PAIRS).toHaveLength(81);
    expect(PAIRS.filter((pair) => pair.required !== null)).toHaveLength(72);
  });

  it("computes C01 --fg-1 on --bg-canvas as 16.45 light and 16.29 dark", () => {
    const ratio = (theme: Theme): number => {
      const tokens = readTokens(TOKENS, theme);
      return contrastRatio(tokenRgb(tokens, "--fg-1"), tokenRgb(tokens, "--bg-canvas"));
    };
    expect(Math.abs(ratio("light") - 16.45)).toBeLessThanOrEqual(0.02);
    expect(Math.abs(ratio("dark") - 16.29)).toBeLessThanOrEqual(0.02);
  });

  describe.each(THEMES)("%s theme", (theme) => {
    const tokens = readTokens(TOKENS, theme);

    it.each(PAIRS)("$id $foreground on $background", (pair) => {
      const ratio = contrastRatio(
        tokenRgb(tokens, pair.foreground),
        tokenRgb(tokens, pair.background),
      );
      if (pair.required !== null) {
        expect(ratio).toBeGreaterThanOrEqual(pair.required);
      }
      expect(Math.abs(ratio - pair[theme])).toBeLessThanOrEqual(0.02);
    });
  });
});
