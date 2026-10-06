// DS-VER-02 (docs/design/DESIGN_SYSTEM.md §13, §5.2 DS-VIZ-01 to DS-VIZ-06): data-visualization
// palettes pass their colour-vision, monotonicity and ordinal-contrast gates in both themes.
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  contrastRatio,
  deltaE,
  lightness,
  readTokens,
  type Rgb8,
  type Theme,
  tokenRgb,
  type Tokens,
} from "../../config/colour";

const TOKENS = fileURLToPath(new URL("./tokens.css", import.meta.url));

// Tabulated results of DS-VIZ-02, DS-VIZ-01 and DS-VIZ-06.
const EXPECTED: Record<
  Theme,
  { cvdMin: number; normalMin: number; slotContrast: number[]; weakestBand: number }
> = {
  light: {
    cvdMin: 13.8,
    normalMin: 16.0,
    slotContrast: [3.96, 4.28, 4.14, 3.3, 3.92, 4.2, 3.66],
    weakestBand: 2.25,
  },
  dark: {
    cvdMin: 14.1,
    normalMin: 16.2,
    slotContrast: [4.76, 4.41, 4.54, 5.4, 4.78, 4.49, 5.14],
    weakestBand: 3.02,
  },
};

const THEMES: Theme[] = ["light", "dark"];

function series(tokens: Tokens, prefix: string, count: number): Rgb8[] {
  return Array.from({ length: count }, (_, index) => tokenRgb(tokens, `${prefix}${index + 1}`));
}

function adjacent<T>(values: T[]): [T, T][] {
  return values.slice(1).map((value, index) => [values[index] as T, value]);
}

function expectMonotoneRamp(ramp: Rgb8[], direction: 1 | -1): void {
  for (const [low, high] of adjacent(ramp.map(lightness))) {
    expect(direction * (high - low)).toBeGreaterThanOrEqual(0.06);
  }
}

describe("DS-VER-02", () => {
  describe.each(THEMES)("%s theme", (theme) => {
    const tokens = readTokens(TOKENS, theme);
    const expected = EXPECTED[theme];
    const categorical = series(tokens, "--viz-", 7);
    const surface = tokenRgb(tokens, "--bg-surface");
    // Light ramps darken as magnitude grows; dark ramps lighten (DS-VIZ-04).
    const direction = theme === "light" ? -1 : 1;

    it("categorical adjacent pairs: protanopia and deuteranopia ΔE ≥ 8, normal vision ΔE ≥ 15", () => {
      const pairs = adjacent(categorical);
      const cvd = Math.min(
        ...pairs.flatMap(([a, b]) => [deltaE(a, b, "protanopia"), deltaE(a, b, "deuteranopia")]),
      );
      const normal = Math.min(...pairs.map(([a, b]) => deltaE(a, b, "normal")));
      expect(cvd).toBeGreaterThanOrEqual(8);
      expect(normal).toBeGreaterThanOrEqual(15);
      expect(Math.abs(cvd - expected.cvdMin)).toBeLessThan(0.05);
      expect(Math.abs(normal - expected.normalMin)).toBeLessThan(0.05);
    });

    it("categorical marks reach 3:1 on --bg-surface", () => {
      categorical.forEach((slot, index) => {
        const ratio = contrastRatio(slot, surface);
        expect(ratio).toBeGreaterThanOrEqual(3);
        expect(Math.abs(ratio - (expected.slotContrast[index] as number))).toBeLessThanOrEqual(
          0.02,
        );
      });
    });

    it("the sequential ramp is monotone with ΔL ≥ 0.06", () => {
      expectMonotoneRamp(series(tokens, "--viz-seq-", 9), direction);
    });

    it("each diverging arm is monotone with ΔL ≥ 0.06", () => {
      expectMonotoneRamp(series(tokens, "--viz-div-pos-", 4), direction);
      expectMonotoneRamp(series(tokens, "--viz-div-neg-", 4), direction);
    });

    it("the ordinal ramp strengthens toward the nearest band and its weakest band meets 2:1", () => {
      expectMonotoneRamp(series(tokens, "--viz-rpo-", 5).reverse(), direction);
      const weakest = contrastRatio(tokenRgb(tokens, "--viz-rpo-5"), surface);
      expect(weakest).toBeGreaterThanOrEqual(2);
      expect(Math.abs(weakest - expected.weakestBand)).toBeLessThanOrEqual(0.02);
    });
  });
});
