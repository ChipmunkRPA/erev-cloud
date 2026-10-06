// DS-TYP-05 (docs/design/DESIGN_SYSTEM.md §3.1): fonts are vendored with their licence and never
// requested from a remote host.
import { existsSync, readFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const STYLES = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(STYLES, "..");
const FONTS_CSS = readFileSync(resolve(STYLES, "fonts.css"), "utf8");
const FACES = [...FONTS_CSS.matchAll(/@font-face\s*\{([^}]*)\}/g)].map(
  (match) => match[1] as string,
);

describe("DS-TYP-05", () => {
  it("declares the Inter and JetBrains Mono families of the token font stacks", () => {
    const families = new Set(FACES.map((face) => /font-family:\s*"([^"]+)"/.exec(face)?.[1]));
    expect(families).toEqual(new Set(["Inter", "JetBrains Mono"]));
    for (const face of FACES) {
      expect(face).toMatch(/font-display:\s*swap/);
    }
  });

  it("loads every @font-face src from a relative URL under src/assets/fonts/", () => {
    const urls = FACES.flatMap((face) =>
      [...face.matchAll(/url\(\s*["']?([^"')]+)["']?\s*\)/g)].map((match) => match[1] as string),
    );
    expect(urls.length).toBeGreaterThan(0);
    for (const url of urls) {
      expect(url).not.toMatch(/^(?:[a-z][a-z0-9+.-]*:|\/)/i);
      const file = resolve(STYLES, url);
      expect(relative(SRC, file).startsWith("assets/fonts/")).toBe(true);
      expect(existsSync(file)).toBe(true);
    }
  });

  it("ships OFL.txt for both families", () => {
    for (const family of ["inter", "jetbrains-mono"]) {
      const licence = resolve(SRC, "assets/fonts", family, "OFL.txt");
      expect(existsSync(licence)).toBe(true);
      expect(readFileSync(licence, "utf8")).toContain("SIL Open Font License, Version 1.1");
    }
  });

  it("names no remote host", () => {
    expect(FONTS_CSS).not.toMatch(/https?:|\/\//);
  });
});
