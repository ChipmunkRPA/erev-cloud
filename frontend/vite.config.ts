import { readdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

import { resolveProxyTarget } from "./config/proxy";

const FRONTEND_DIR = fileURLToPath(new URL(".", import.meta.url));

// docs/05-ARCHITECTURE.md SAR-20: the headers nginx sets on every response. vite preview serves
// them so e2e exercises the production Content-Security-Policy (DG-RUN-23, REQ-SEC-004).
export const SECURITY_HEADERS: Record<string, string> = {
  "Content-Security-Policy":
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; " +
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; " +
    "form-action 'self'; frame-ancestors 'none'",
  "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "same-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Resource-Policy": "same-origin",
};

// Unit tests of public/ files sit beside them (frontend/public/theme-init.test.ts); vite build
// copies public/ verbatim, so this plugin removes the test sources from the build output.
export function omitPublicTests(publicDir: string): Plugin {
  return {
    name: "erev-omit-public-tests",
    apply: "build",
    writeBundle(options) {
      if (options.dir === undefined) {
        return;
      }
      for (const name of readdirSync(publicDir)) {
        if (name.endsWith(".test.ts")) {
          rmSync(join(options.dir, name), { force: true });
        }
      }
    },
  };
}

// docs/dev-guide.md §3.3 (DG-RUN-20 to DG-RUN-24) and DG-FE-19.
export default defineConfig(({ command, mode, isPreview }) => {
  const serving = isPreview === true || (command === "serve" && mode !== "test");
  const proxy = serving
    ? {
        "/api": {
          target: resolveProxyTarget(process.env.EREV_API_PROXY_TARGET),
          changeOrigin: false,
          ws: false,
        },
      }
    : {};

  return {
    root: FRONTEND_DIR,
    cacheDir: `node_modules/.vite-${process.env.EREV_VITE_MODE ?? "dev"}`,
    plugins: [react(), tailwindcss(), omitPublicTests(join(FRONTEND_DIR, "public"))],
    server: {
      host: "127.0.0.1",
      port: Number(process.env.EREV_WEB_PORT ?? 5270),
      strictPort: true,
      proxy,
    },
    preview: {
      host: "127.0.0.1",
      port: Number(process.env.EREV_E2E_WEB_PORT ?? 5279),
      strictPort: true,
      proxy,
      headers: SECURITY_HEADERS,
    },
    build: {
      outDir: "dist",
      sourcemap: "hidden",
    },
    test: {
      include: ["src/**/*.test.{ts,tsx}", "config/**/*.test.ts", "public/**/*.test.ts"],
      // src/test/setup.ts gives every assertion five seconds to become true; a test makes several.
      setupFiles: [join(FRONTEND_DIR, "src", "test", "setup.ts")],
      testTimeout: 20_000,
    },
  };
});
