// DG-FE-13 (docs/dev-guide.md §8.2): the blocking bootstrap applies the stored theme and density to
// <html> before first paint.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const SOURCE = readFileSync(fileURLToPath(new URL("./theme-init.js", import.meta.url)), "utf8");

function boot(storage: Record<string, string>): HTMLElement {
  const dom = new JSDOM("<!doctype html><html><head></head><body></body></html>", {
    url: "http://127.0.0.1:5270/",
    runScripts: "outside-only",
  });
  for (const [key, value] of Object.entries(storage)) {
    dom.window.localStorage.setItem(key, value);
  }
  dom.window.eval(SOURCE);
  return dom.window.document.documentElement;
}

describe("DG-FE-13", () => {
  it("applies erev.theme=dark and erev.density=compact", () => {
    const html = boot({ "erev.theme": "dark", "erev.density": "compact" });
    expect(html.getAttribute("data-theme")).toBe("dark");
    expect(html.getAttribute("data-density")).toBe("compact");
  });

  it("leaves data-theme absent and sets comfortable density when neither key is stored", () => {
    const html = boot({});
    expect(html.hasAttribute("data-theme")).toBe(false);
    expect(html.getAttribute("data-density")).toBe("comfortable");
  });

  it("ignores unknown stored values", () => {
    const html = boot({ "erev.theme": "sepia", "erev.density": "cosy" });
    expect(html.hasAttribute("data-theme")).toBe(false);
    expect(html.getAttribute("data-density")).toBe("comfortable");
  });
});
