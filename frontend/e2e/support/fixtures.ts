// Test fixtures (docs/dev-guide.md DG-E2E-05 to DG-E2E-08). `network` is automatic: each test's browser
// context runs the DG-E2E-08 guard and the SAR-20 CSP-violation recorder, and a non-empty record fails
// the test. `personas` opens a browser context signed in as a WLD-U persona through the UI (password,
// then the TOTP code for a persona with a factor), reusing the storage state cached under
// `e2e/.results/auth/<persona>.json` while its session holds; each persona context runs the same guard.
// `screens` and `a11y` bind the capture and the axe check to the running test; `api` is a request
// context for exact-decimal assertions.
import {
  type BrowserContext,
  type BrowserContextOptions,
  expect,
  type Page,
  test as base,
  type TestInfo,
} from "@playwright/test";

import { ApiClient, newApiContext } from "./api";
import {
  hasStorageState,
  type Persona,
  personaEmail,
  sessionOf,
  signInThroughUi,
  storageStatePath,
  writeStorageState,
} from "./auth";
import { check, type CheckOptions } from "./axe";
import {
  appendProjectRecord,
  installNetworkGuard,
  type NetworkRecord,
  readProjectRecord,
} from "./network";
import { capture, type CaptureOptions, type ScreenEntry } from "./screens";

export interface Screens {
  capture(page: Page, name: string, options?: CaptureOptions): Promise<ScreenEntry>;
}

export interface A11y {
  check(page: Page, surfaceId: string, options?: CheckOptions): Promise<void>;
}

export interface Network {
  /** The record of this test's browser context. */
  record(): NetworkRecord;
  /** The record of every test of this project so far in the run, this test excluded. */
  projectRecord(): NetworkRecord;
}

export interface Personas {
  /** A page of a new browser context signed in as `persona` through the UI (DG-E2E-05). */
  page(persona: Persona): Promise<Page>;
}

export interface Fixtures {
  network: Network;
  personas: Personas;
  screens: Screens;
  a11y: A11y;
  api: ApiClient;
}

function assertEmpty(record: NetworkRecord, label: string): void {
  expect(
    record.requests,
    `REQ-SEC-008: requests to non-loopback hosts (DG-E2E-08)${label}`,
  ).toEqual([]);
  expect(record.cspViolations, `SAR-20: Content-Security-Policy violations${label}`).toEqual([]);
}

/** The project's context options, applied to the persona contexts as to the default context. */
function contextOptions(testInfo: TestInfo): BrowserContextOptions {
  const use = testInfo.project.use;
  return {
    ...(use.baseURL === undefined ? {} : { baseURL: use.baseURL }),
    ...(use.locale === undefined ? {} : { locale: use.locale }),
    ...(use.timezoneId === undefined ? {} : { timezoneId: use.timezoneId }),
    ...(use.viewport === undefined ? {} : { viewport: use.viewport }),
  };
}

export const test = base.extend<Fixtures>({
  network: [
    async ({ context }, provide, testInfo) => {
      const record = await installNetworkGuard(context);
      await provide({
        record: () => record,
        projectRecord: () => readProjectRecord(testInfo.project.name),
      });
      appendProjectRecord(testInfo, record);
      assertEmpty(record, "");
    },
    { auto: true },
  ],
  personas: async ({ browser }, provide, testInfo) => {
    const opened: { persona: Persona; context: BrowserContext; record: NetworkRecord }[] = [];
    const options = contextOptions(testInfo);
    await provide({
      page: async (persona) => {
        let context: BrowserContext | null = null;
        if (hasStorageState(persona)) {
          const cached = await browser.newContext({
            ...options,
            storageState: storageStatePath(persona),
          });
          const session = await sessionOf(cached.request);
          if (session.authenticated && session.user?.email === personaEmail(persona)) {
            context = cached;
          } else {
            await cached.close();
          }
        }
        const signIn = context === null;
        context ??= await browser.newContext(options);
        const record = await installNetworkGuard(context);
        opened.push({ persona, context, record });
        const page = await context.newPage();
        if (signIn) {
          await signInThroughUi(page, persona);
          writeStorageState(persona, await context.storageState());
        }
        return page;
      },
    });
    for (const { persona, context, record } of opened) {
      appendProjectRecord(testInfo, record);
      await context.close();
      assertEmpty(record, ` (persona ${persona})`);
    }
  },
  // eslint-disable-next-line no-empty-pattern -- Playwright fixtures need an object pattern.
  screens: async ({}, provide, testInfo) => {
    await provide({ capture: (page, name, options) => capture(page, testInfo, name, options) });
  },
  // eslint-disable-next-line no-empty-pattern -- Playwright fixtures need an object pattern.
  a11y: async ({}, provide, testInfo) => {
    await provide({
      check: (page, surfaceId, options) => check(page, testInfo, surfaceId, options),
    });
  },
  // eslint-disable-next-line no-empty-pattern -- Playwright fixtures need an object pattern.
  api: async ({}, provide) => {
    const context = await newApiContext();
    await provide(new ApiClient(context));
    await context.dispose();
  },
});

export { expect };
