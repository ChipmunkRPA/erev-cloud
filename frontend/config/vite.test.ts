// DG-RUN-21 to DG-RUN-24 (docs/dev-guide.md §3.3): ports, cache directory, proxies and preview
// security headers of frontend/vite.config.ts.
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import type { ConfigEnv, ProxyOptions, UserConfig } from "vite";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import viteConfig, { omitPublicTests } from "../vite.config";

// docs/05-ARCHITECTURE.md SAR-20, verbatim.
const SAR_20_CSP =
  "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'";

const ENV_KEYS = ["EREV_API_PROXY_TARGET", "EREV_VITE_MODE", "EREV_WEB_PORT", "EREV_E2E_WEB_PORT"];
const RUN_TMP = fileURLToPath(new URL("../../.run/tmp/", import.meta.url));

function resolveConfig(env: ConfigEnv): UserConfig {
  if (typeof viteConfig !== "function") {
    throw new Error("vite.config.ts must export a configuration function");
  }
  return viteConfig(env) as UserConfig;
}

const SERVE: ConfigEnv = { command: "serve", mode: "development", isPreview: false };
const PREVIEW: ConfigEnv = { command: "serve", mode: "production", isPreview: true };

describe("DG-RUN-21 to DG-RUN-23", () => {
  const saved = new Map<string, string | undefined>();

  beforeEach(() => {
    for (const key of ENV_KEYS) {
      saved.set(key, process.env[key]);
      Reflect.deleteProperty(process.env, key);
    }
    process.env.EREV_API_PROXY_TARGET = "http://127.0.0.1:8190";
  });

  afterEach(() => {
    for (const [key, value] of saved) {
      if (value === undefined) {
        Reflect.deleteProperty(process.env, key);
      } else {
        process.env[key] = value;
      }
    }
  });

  it("binds the dev server to 127.0.0.1:5270 and preview to 5279, both strict", () => {
    const serve = resolveConfig(SERVE);
    expect(serve.server?.host).toBe("127.0.0.1");
    expect(serve.server?.port).toBe(5270);
    expect(serve.server?.strictPort).toBe(true);
    const preview = resolveConfig(PREVIEW);
    expect(preview.preview?.host).toBe("127.0.0.1");
    expect(preview.preview?.port).toBe(5279);
    expect(preview.preview?.strictPort).toBe(true);
  });

  it("uses node_modules/.vite-e2e as cache directory when EREV_VITE_MODE=e2e", () => {
    process.env.EREV_VITE_MODE = "e2e";
    expect(resolveConfig(PREVIEW).cacheDir).toBe("node_modules/.vite-e2e");
  });

  it("serves the SAR-20 Content-Security-Policy from vite preview", () => {
    const headers = resolveConfig(PREVIEW).preview?.headers as Record<string, string>;
    expect(headers["Content-Security-Policy"]).toBe(SAR_20_CSP);
    expect(headers["X-Frame-Options"]).toBe("DENY");
    expect(headers["X-Content-Type-Options"]).toBe("nosniff");
    expect(headers["Referrer-Policy"]).toBe("same-origin");
  });

  it("maps /api with changeOrigin false and ws false on both proxies", () => {
    for (const config of [resolveConfig(SERVE).server, resolveConfig(PREVIEW).preview]) {
      const api = config?.proxy?.["/api"] as ProxyOptions;
      expect(api.target).toBe("http://127.0.0.1:8190");
      expect(api.changeOrigin).toBe(false);
      expect(api.ws).toBe(false);
    }
  });

  it("has no server.fs.allow override", () => {
    expect(resolveConfig(SERVE).server?.fs?.allow).toBeUndefined();
  });

  it("builds without EREV_API_PROXY_TARGET", () => {
    delete process.env.EREV_API_PROXY_TARGET;
    expect(() => resolveConfig({ command: "build", mode: "production" })).not.toThrow();
  });
});

describe("omitPublicTests", () => {
  it("removes public test sources from the build output and keeps the scripts", () => {
    mkdirSync(RUN_TMP, { recursive: true });
    const root = mkdtempSync(join(RUN_TMP, "vite-public-"));
    try {
      const publicDir = join(root, "public");
      const outDir = join(root, "dist");
      for (const dir of [publicDir, outDir]) {
        mkdirSync(dir);
        writeFileSync(join(dir, "theme-init.js"), "");
        writeFileSync(join(dir, "theme-init.test.ts"), "");
      }
      const plugin = omitPublicTests(publicDir);
      const hook = plugin.writeBundle as (options: { dir?: string }) => void;
      hook.call(undefined, { dir: outDir });
      expect(existsSync(join(outDir, "theme-init.test.ts"))).toBe(false);
      expect(existsSync(join(outDir, "theme-init.js"))).toBe(true);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
});
