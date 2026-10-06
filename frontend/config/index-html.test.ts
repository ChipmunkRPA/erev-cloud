// DG-FE-12 and DG-FE-13 (docs/dev-guide.md §8.2): index.html has no inline script, and the blocking
// theme bootstrap precedes the first stylesheet. DS-TYP-05: the upright Inter file is preloaded.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const HTML = readFileSync(fileURLToPath(new URL("../index.html", import.meta.url)), "utf8");

describe("DG-FE-12", () => {
  it("holds no inline <script> content", () => {
    const scripts = [...HTML.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)];
    expect(scripts.length).toBeGreaterThan(0);
    for (const [, attributes, body] of scripts) {
      expect(attributes).toMatch(/\bsrc="[^"]+"/);
      expect((body as string).trim()).toBe("");
    }
    expect(HTML).not.toMatch(/\son[a-z]+=/i);
  });

  it("places the blocking theme-init.js tag before the first stylesheet link", () => {
    const bootstrap = /<script src="\/theme-init\.js"><\/script>/.exec(HTML);
    const stylesheet = /<link\b[^>]*\brel="stylesheet"/.exec(HTML);
    expect(bootstrap).not.toBeNull();
    expect(stylesheet).not.toBeNull();
    expect(bootstrap?.index).toBeLessThan(stylesheet?.index ?? -1);
    expect(HTML.indexOf("</head>")).toBeGreaterThan(stylesheet?.index ?? Infinity);
  });

  it("preloads the upright Inter file", () => {
    expect(HTML).toMatch(
      /<link\s+rel="preload"\s+href="\/src\/assets\/fonts\/inter\/inter-latin-opsz-normal\.woff2"\s+as="font"/,
    );
  });
});
