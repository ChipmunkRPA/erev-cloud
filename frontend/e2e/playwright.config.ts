// Playwright harness (docs/dev-guide.md §9.8 binding shape; DG-E2E-01 to DG-E2E-12; PRD E2E-04 to
// E2E-06). scripts/e2e.sh runs each project as its own invocation (DG-E2E-02) against the production
// build served by `vite preview` on the e2e ports (DG-RUN-04 to DG-RUN-06).
import { defineConfig } from "@playwright/test";

// DG-E2E-02 rev 1.277: `make e2e CLOSE=1` is a run of its own on the world seeded with its closed
// months (BUILD_SPEC CLO-22), and scripts/e2e.sh names it to this file with EREV_E2E_CLOSE=1. That
// run has the projects of the closed world; every other run has the six projects of the open world
// and neither lists nor runs one of the closed world (frontend/config/e2e-projects.test.ts).
// Rev 1.280: `qa-rc` is the release candidate's multi-role browser QA (DG-E2E-14), a pass that
// writes a record and locks a month; scripts/e2e.sh runs it only when `PROJECT` names it.
const CLOSED_WORLD = process.env.EREV_E2E_CLOSE === "1";

export default defineConfig({
  testDir: "./projects",
  outputDir: "./.results",
  forbidOnly: true,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["json", { outputFile: "../../.run/reports/e2e/report.json" }]],
  use: {
    baseURL: `http://127.0.0.1:${process.env.EREV_E2E_WEB_PORT ?? "5279"}`,
    trace: "retain-on-failure",
    screenshot: "off",
    video: "off",
    locale: "en-US",
    timezoneId: "UTC",
    viewport: { width: 1440, height: 900 },
  },
  projects: CLOSED_WORLD
    ? [
        { name: "closed", testMatch: /closed\.spec\.ts$/, fullyParallel: true },
        {
          name: "qa-rc",
          testMatch: /qa-rc\.spec\.ts$/,
          fullyParallel: false,
          // DG-E2E-14: a section of the pass is one test of many minutes and hundreds of pages,
          // and a trace is written while a test runs, kept or not. The record has a capture a row.
          use: { trace: "off" },
        },
      ]
    : [
        { name: "avenmoor-serial", testMatch: /avenmoor-serial\.spec\.ts$/, fullyParallel: false },
        { name: "fresh-tenant", testMatch: /fresh-tenant\.spec\.ts$/, fullyParallel: true },
        { name: "industry", testMatch: /industry\.spec\.ts$/, fullyParallel: true },
        { name: "screens", testMatch: /screens\.spec\.ts$/, fullyParallel: true },
        { name: "design", testMatch: /design\.spec\.ts$/, fullyParallel: false },
        { name: "crawl", testMatch: /crawl\.spec\.ts$/, fullyParallel: true },
      ],
});
