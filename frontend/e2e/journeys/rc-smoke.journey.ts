// SUP-RC-SMOKE release-candidate smoke journey (BUILD_SPEC RPS-7a; 01-DECISIONS D-81, D-82, D-86;
// docs/build-spec/sprint/sup-rc-smoke.md N-1 to N-8; docs/dev-guide.md DG-E2E-03 to DG-E2E-09). One serial
// journey over WLD-T-01 Avenmoor, context AVM-US, ASC606, FY2026-P09: each step consumes what the previous
// step created (the SKU SSP import and its approval, the Sep 2026 journal run, its approval and its CSV
// export). `make e2e` reseeds the e2e database on each run (E2E-03), so the journey starts from the seed.
// Personas sign in through the UI (WLD-U-R1); `priya` and `marcus` pass SF-22:mfa-challenge and `priya`
// confirms the step-up of `import.approve` and `journal.approve` with codes of `support/totp.ts` (WLD-U-R2,
// E2E-08). Money is asserted as the API decimal string and as rendered text (E2E-02); records are found by
// external id or name (DG-E2E-09). Every assertion is hard (D-89 L7-3-Q-27, Q-28, Q-29, Q-31).
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { inflateRawSync } from "node:zlib";

import type {
  APIRequestContext,
  Browser,
  BrowserContext,
  Locator,
  Page,
  TestInfo,
} from "@playwright/test";

import { expectDecimal, json } from "../support/api";
import {
  MFA_CHALLENGE_PATH,
  passwordStep,
  type Persona,
  PERSONA_WORKSPACE,
  personaEmail,
  SELECT_WORKSPACE_PATH,
  sessionOf,
  SIGN_IN_PATH,
  signInThroughUi,
  totpStep,
  workspaceStep,
} from "../support/auth";
import { expect, test } from "../support/fixtures";
import { appendProjectRecord, installNetworkGuard, type NetworkRecord } from "../support/network";
import { REPO_ROOT } from "../support/tenants";
import { nextCode } from "../support/totp";

/** SCREENS SCR-ST-20: the journey context. */
const CONTEXT = "entity=AVM-US&period=FY2026-P09&book=ASC606";
/** SCREENS SCR-IA-01 table and DS-CMP-02 groups: Work, then Govern, then Settings (L7-3-Q-28). */
const RAIL = [
  "Home",
  "Contracts",
  "Schedules",
  "Close",
  "Journals",
  "Reports",
  "Approvals",
  "Policies",
  "Data",
  "Settings",
] as const;
/** SCREENS §4.1.4: the six KPI cells of SF-03, each an Explain trigger. */
const KPI_CELLS = [
  "Transaction price",
  "Billed",
  "Recognized",
  "Scheduled",
  "Awaiting trigger",
  "Contract liability",
] as const;
/** SCREENS §4.1.4 cell 6 secondary line triggers (OQ-S-02). */
const KPI_SECONDARY = ["Contract asset", "Unbilled receivable"] as const;
/** PRD §2.12 WLD-F-01: the legacy SKU SSP upload of the UAT fixtures. */
const WLD_F_01_NAME = "SKU SSP Template.xlsx";
const WLD_F_01_PATH = join(
  REPO_ROOT,
  "backend",
  "tests",
  "fixtures",
  "legacy_uat",
  "01-ssp-upload",
  WLD_F_01_NAME,
);
const LEGACY_SSP_BOOK = "LEGACY-SKU-SSP";
const LEGACY_SSP_VERSION = "2023-01-01";
/** PRD §2.9 WLD-B-04. */
const WLD_B_04_FILE = "avm-us-progress-2026-09-invalid.csv";
/** PRD §2.7 WLD-K-01, WLD-K-02, WLD-K-09 external ids. */
const K01 = "SF-ORD-10001";
const K02 = "SF-ORD-10002";
const K09 = "SF-ORD-10417";
const TO_WATERFALL = "TO_WATERFALL_EQ_JE_REVENUE";
/** reports.tieOut name of TO_WATERFALL_EQ_JE_REVENUE (SCREENS_B RV-05). */
const TO_WATERFALL_NAME = "Waterfall revenue equals revenue journal total";
const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const MAX_CODES = 3;
const JOB_TIMEOUT_MS = 180_000;
/** The journey runs its ten steps in one test; sign-in and step-up codes wait for TOTP steps. */
const JOURNEY_TIMEOUT_MS = 30 * 60_000;

interface ImportRef {
  readonly id: string;
  readonly status: string;
  readonly approval_request_id: string | null;
  readonly counts: {
    readonly rows: number | null;
    readonly valid: number | null;
    readonly errors: number | null;
  };
}

interface ApprovalRef {
  readonly id: string;
  readonly request_no: string;
  readonly summary: string;
  readonly status: string;
}

interface JournalRunRef {
  readonly id: string;
  readonly run_no: string;
  readonly state: string;
  readonly approval_request_id: string | null;
  readonly approved_at: string | null;
}

interface JournalBatchRef {
  readonly id: string;
  readonly batch_no: number;
  readonly chunk_no: number;
  readonly state: string;
  readonly adapter: string | null;
  readonly external_id: string;
  readonly exported_at: string | null;
  readonly detail_sha256: string | null;
  readonly row_version: number;
  readonly acknowledgements: readonly unknown[];
}

/** CTL-021: what a repeated export must leave unchanged on a batch (D-89 L7-3-Q-31). */
function batchTuple(batch: JournalBatchRef): readonly unknown[] {
  return [
    batch.external_id,
    batch.state,
    batch.exported_at,
    batch.detail_sha256,
    batch.row_version,
    batch.acknowledgements.length,
  ];
}

interface ReportRunRef {
  readonly id: string;
  readonly status: string;
  readonly control_totals: Readonly<Record<string, unknown>> | null;
  readonly tie_out_results: readonly {
    readonly code: string;
    readonly result: string;
    /** API-S-ReportRun `difference`, actual − expected per currency (D-88 L7-3-Q-3). */
    readonly difference: unknown;
  }[];
}

type ReportRow = Readonly<Record<string, unknown>> & { readonly row_key: string };

interface OpenedContext {
  readonly context: BrowserContext;
  readonly page: Page;
  readonly record: NetworkRecord;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** The project's context options for a second browser context (as the `personas` fixture applies them). */
async function openContext(browser: Browser, testInfo: TestInfo): Promise<OpenedContext> {
  const use = testInfo.project.use;
  const context = await browser.newContext({
    ...(use.baseURL === undefined ? {} : { baseURL: use.baseURL }),
    ...(use.locale === undefined ? {} : { locale: use.locale }),
    ...(use.timezoneId === undefined ? {} : { timezoneId: use.timezoneId }),
    ...(use.viewport === undefined ? {} : { viewport: use.viewport }),
  });
  const record = await installNetworkGuard(context);
  return { context, page: await context.newPage(), record };
}

function pathOf(page: Page): string {
  return new URL(page.url()).pathname;
}

/** API-R-43 `GET /imports/{id}`. */
async function importOf(request: APIRequestContext, importId: string): Promise<ImportRef> {
  return json<ImportRef>(await request.get(`/api/v1/imports/${importId}`));
}

async function journalRunOf(request: APIRequestContext, runId: string): Promise<JournalRunRef> {
  return json<JournalRunRef>(await request.get(`/api/v1/journal-runs/${runId}`));
}

async function contractIdOf(request: APIRequestContext, externalId: string): Promise<string> {
  const listed = await json<{
    readonly items: readonly { readonly id: string; readonly external_id: string }[];
  }>(await request.get("/api/v1/contracts", { params: { q: externalId, limit: 50 } }));
  const found = listed.items.find((item) => item.external_id === externalId);
  expect(found, `${externalId} is seeded (CTR-20)`).toBeDefined();
  return found?.id ?? "";
}

/** API-R-35: the O1 normal REVENUE schedule line of FY2026-P09. */
async function p09LineAmount(request: APIRequestContext, contractId: string): Promise<unknown> {
  const listed = await json<{
    readonly items: readonly {
      readonly obligation_key: string | null;
      readonly line_type: string;
      readonly amount: { readonly amount: unknown };
    }[];
  }>(
    await request.get("/api/v1/schedule-lines", {
      params: {
        contract: contractId,
        schedule_kind: "REVENUE",
        book: "ASC606",
        from_period: "FY2026-P09",
        to_period: "FY2026-P09",
        limit: 200,
      },
    }),
  );
  const line = listed.items.find(
    (item) => item.obligation_key === "O1" && item.line_type === "NORMAL",
  );
  expect(line, `O1 FY2026-P09 normal schedule line of ${contractId}`).toBeDefined();
  return line?.amount.amount;
}

/** The amount string of an API-S-Money value, or the value itself. */
function amountOf(value: unknown): unknown {
  return typeof value === "object" && value !== null && "amount" in value
    ? (value as { readonly amount: unknown }).amount
    : value;
}

/** A decimal string as an integer count of 10^-scale units, with no floating point (DG-FE-08). */
function units(value: string, scale: number): bigint {
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value);
  if (match === null) {
    throw new Error(`not a decimal string: ${value}`);
  }
  const fraction = (match[3] ?? "").padEnd(scale, "0");
  if (fraction.length > scale) {
    throw new Error(`${value} has more than ${String(scale)} decimals`);
  }
  const magnitude = BigInt(`${match[2] ?? "0"}${fraction}`);
  return match[1] === "-" ? -magnitude : magnitude;
}

/** DS-FMT-01 en-US grouping of a non-negative decimal string: "105043.80" → "105,043.80". */
function groupedText(value: string): string {
  const [whole = "", fraction] = value.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return fraction === undefined ? grouped : `${grouped}.${fraction}`;
}

/** DS-FMT-01: a negative amount in parentheses. */
function moneyText(value: string): string {
  return value.startsWith("-") ? `(${groupedText(value.slice(1))})` : groupedText(value);
}

/** SF-22:mfa-challenge step-up (SCR-PERM-05): a fresh code; a refused code is retried with a later step. */
async function confirmStepUp(page: Page, persona: Persona, dialog: Locator): Promise<void> {
  const wrong = dialog.getByText(
    "That code did not match. Check your authenticator app and try again.",
  );
  let refused: number | undefined;
  for (let attempt = 0; attempt < MAX_CODES; attempt += 1) {
    const { code, step } = await nextCode(personaEmail(persona), refused);
    await dialog.getByRole("textbox", { name: /^Authentication code/ }).fill(code);
    await dialog.getByRole("button", { name: "Confirm", exact: true }).click();
    await expect(async () => {
      expect((await dialog.isHidden()) || (await wrong.isVisible())).toBe(true);
    }).toPass({ timeout: 15_000 });
    if (await dialog.isHidden()) {
      return;
    }
    refused = step;
  }
  throw new Error(`the step-up refused ${String(MAX_CODES)} codes for ${persona}`);
}

/** SF-12:request: the request of `requestId` with its decision form. */
async function openRequest(page: Page, requestId: string): Promise<ApprovalRef> {
  const approval = await json<ApprovalRef>(
    await page.request.get(`/api/v1/approvals/${requestId}`),
  );
  expect(approval.status).toBe("PENDING");
  await page.goto(`/approvals/requests/${requestId}?entity=AVM-US`);
  await expect(
    page.getByRole("region", { name: `Request details: ${approval.summary}` }),
  ).toBeVisible();
  await expect(page.getByRole("form", { name: "Decision" })).toBeVisible();
  return approval;
}

/** Approve with a comment; a 403 `mfa-step-up-required` opens the step-up modal first (BS1-D-19). */
async function approveRequest(
  page: Page,
  persona: Persona,
  approval: ApprovalRef,
  comment: string,
): Promise<void> {
  const form = page.getByRole("form", { name: "Decision" });
  await form.getByRole("textbox", { name: /^Comment/ }).fill(comment);
  await form.getByRole("button", { name: "Approve", exact: true }).click();
  const toast = page.getByText(`Approved: ${approval.summary}.`, { exact: true });
  const stepUp = page.getByRole("dialog", { name: "Confirm with your authenticator" });
  await expect(toast.or(stepUp).first()).toBeVisible({ timeout: 30_000 });
  if (await stepUp.isVisible()) {
    await confirmStepUp(page, persona, stepUp);
  }
  await expect(toast).toBeVisible({ timeout: 30_000 });
}

/** DS-CMP-10 grids render the visible rows plus overscan, so a row further down enters once scrolled to. */
async function scrolledRow(grid: Locator, row: Locator): Promise<Locator> {
  await expect
    .poll(
      async () => {
        if ((await row.count()) > 0) {
          return true;
        }
        await grid.evaluate((element) => {
          element.scrollTop += element.clientHeight;
        });
        return false;
      },
      { timeout: 30_000, intervals: [150] },
    )
    .toBe(true);
  await row.scrollIntoViewIfNeeded();
  return row;
}

/** The `run` parameter of the report view's URL (RV-01, SCR-URL-16). */
function runParam(page: Page): string {
  return new URL(page.url()).searchParams.get("run") ?? "";
}

/** "Run report" writes a new `run` into the URL (RV-01); the stored run then succeeds. */
async function runReport(page: Page, ready: Locator): Promise<ReportRunRef> {
  await expect(page).toHaveURL(new RegExp(`[?&]run=${UUID}(&|$)`));
  const opened = runParam(page);
  // RV-01: a press while the opening run computes answers "<report name> is already running.", so the
  // opening run succeeds and renders first.
  await succeededRun(page.request, opened);
  await expect(ready).toBeVisible({ timeout: JOB_TIMEOUT_MS });
  await page.getByRole("button", { name: "Run report", exact: true }).click();
  await expect.poll(() => runParam(page)).not.toBe(opened);
  await expect(page).toHaveURL(new RegExp(`[?&]run=${UUID}(&|$)`));
  return succeededRun(page.request, runParam(page));
}

async function succeededRun(request: APIRequestContext, runId: string): Promise<ReportRunRef> {
  await expect
    .poll(
      async () =>
        (await json<ReportRunRef>(await request.get(`/api/v1/report-runs/${runId}`))).status,
      { timeout: JOB_TIMEOUT_MS, intervals: [1_000] },
    )
    .toBe("SUCCEEDED");
  return json<ReportRunRef>(await request.get(`/api/v1/report-runs/${runId}`));
}

/** API-R-41 `GET /report-runs/{id}/data`: every page of rows. */
async function reportRows(request: APIRequestContext, runId: string): Promise<ReportRow[]> {
  const rows: ReportRow[] = [];
  let cursor: string | null = null;
  do {
    const params: Record<string, string | number> = { limit: 200 };
    if (cursor !== null) {
      params.cursor = cursor;
    }
    const page = await json<{
      readonly items: readonly ReportRow[];
      readonly next_cursor: string | null;
    }>(await request.get(`/api/v1/report-runs/${runId}/data`, { params }));
    rows.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor !== null);
  return rows;
}

/** The entries of a ZIP archive (APPNOTE central directory; STORED or DEFLATED entries). */
function unzip(archive: Buffer): Map<string, Buffer> {
  const END_SIGNATURE = 0x06054b50;
  const CENTRAL_SIGNATURE = 0x02014b50;
  let end = -1;
  for (
    let offset = archive.length - 22;
    offset >= Math.max(0, archive.length - 65_557);
    offset -= 1
  ) {
    if (archive.readUInt32LE(offset) === END_SIGNATURE) {
      end = offset;
      break;
    }
  }
  if (end < 0) {
    throw new Error("the download is not a ZIP archive");
  }
  const entries = new Map<string, Buffer>();
  const count = archive.readUInt16LE(end + 10);
  let pointer = archive.readUInt32LE(end + 16);
  for (let index = 0; index < count; index += 1) {
    if (archive.readUInt32LE(pointer) !== CENTRAL_SIGNATURE) {
      throw new Error(`ZIP central directory entry ${String(index)} is malformed`);
    }
    const method = archive.readUInt16LE(pointer + 10);
    const compressedSize = archive.readUInt32LE(pointer + 20);
    const nameLength = archive.readUInt16LE(pointer + 28);
    const extraLength = archive.readUInt16LE(pointer + 30);
    const commentLength = archive.readUInt16LE(pointer + 32);
    const localOffset = archive.readUInt32LE(pointer + 42);
    const name = archive.subarray(pointer + 46, pointer + 46 + nameLength).toString("utf8");
    const localNameLength = archive.readUInt16LE(localOffset + 26);
    const localExtraLength = archive.readUInt16LE(localOffset + 28);
    const start = localOffset + 30 + localNameLength + localExtraLength;
    const data = archive.subarray(start, start + compressedSize);
    entries.set(name, method === 0 ? Buffer.from(data) : inflateRawSync(data));
    pointer += 46 + nameLength + extraLength + commentLength;
  }
  return entries;
}

/** RFC 4180 records of a CSV text (quoted fields may hold commas, quotes and line breaks). */
function csvRecords(text: string): string[][] {
  const records: string[][] = [];
  let record: string[] = [];
  let field = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      record.push(field);
      field = "";
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && text[index + 1] === "\n") {
        index += 1;
      }
      record.push(field);
      records.push(record);
      record = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (field !== "" || record.length > 0) {
    record.push(field);
    records.push(record);
  }
  return records;
}

export function rcSmoke(): void {
  test.describe("SUP-RC-SMOKE Release-candidate smoke on Avenmoor", () => {
    test("RC-SMOKE.1 to RC-SMOKE.10 on WLD-T-01, AVM-US, ASC606, FY2026-P09", async ({
      page,
      browser,
      personas,
      screens,
      a11y,
      network,
    }, testInfo) => {
      test.setTimeout(JOURNEY_TIMEOUT_MS);
      // A holder, because steps assign it inside callbacks that control-flow analysis does not follow.
      const second: { context: OpenedContext | null } = { context: null };
      const priyaPage = (): Page => {
        if (second.context === null) {
          throw new Error("priya signs in at RC-SMOKE.1");
        }
        return second.context.page;
      };
      let importId = "";
      let runId = "";
      let runNo = "";
      try {
        await test.step("RC-SMOKE.1 Sign-in: maya lands on /home with the rail; priya passes SF-22:mfa-challenge", async () => {
          await page.goto(SIGN_IN_PATH);
          await expect(page.getByRole("heading", { level: 1, name: "Sign in" })).toBeVisible();
          await a11y.check(page, "SF-22");
          await signInThroughUi(page, "maya");
          // BS-D-08 and SCR-IA-01 (RPS-22); the rail order is DS-CMP-02 (D-89 L7-3-Q-28).
          await expect(page).toHaveURL(/\/home(\?|$)/);
          const rail = page.getByRole("navigation", { name: "Primary" }).getByRole("link");
          await expect(rail.first()).toBeVisible();
          // The Approvals link names its badge, "Approvals, <n> pending" (SCR-IA-01).
          const railNames = await rail.evaluateAll((links) =>
            links.map((link) =>
              (link.getAttribute("aria-label") ?? link.textContent ?? "")
                .trim()
                .replace(/, \d+ pending$/, ""),
            ),
          );
          expect(railNames, "SCR-IA-01 rail destinations in DS-CMP-02 order").toEqual([...RAIL]);
          await a11y.check(page, "SF-01");

          second.context = await openContext(browser, testInfo);
          const priya = priyaPage();
          await passwordStep(priya, "priya");
          await expect(priya).toHaveURL(new RegExp(`${escapeRegExp(MFA_CHALLENGE_PATH)}$`));
          await expect(
            priya.getByRole("heading", { level: 1, name: "Verify your sign-in" }),
          ).toBeVisible();
          await a11y.check(priya, "SF-22:mfa-challenge");
          await totpStep(priya, "priya");
          if (pathOf(priya) === SELECT_WORKSPACE_PATH) {
            await workspaceStep(priya);
          }
          const session = await sessionOf(priya.request);
          expect(session.user?.email).toBe(personaEmail("priya"));
          expect(session.mfa_verified_at).not.toBeNull();
          expect(session.active_tenant?.code).toBe(PERSONA_WORKSPACE.code);
        });

        await test.step("RC-SMOKE.2 Legacy template import: WLD-F-01 validates, needs no mapping and is submitted", async () => {
          await page.goto("/data/imports/new?template=legacy_sku_ssp");
          await expect(page.getByRole("heading", { level: 1, name: "New import" })).toBeVisible();
          await expect(page.getByRole("combobox", { name: "Template" })).toContainText(
            "Legacy v1: SKU SSP",
          );
          await a11y.check(page, "SF-10:new");
          await page.getByTestId("SF-10-file-input").setInputFiles(WLD_F_01_PATH);
          await expect(page.getByTestId("SF-10-file-selected")).toContainText(WLD_F_01_NAME);
          const created = page.waitForResponse(
            (response) =>
              new URL(response.url()).pathname === "/api/v1/imports" &&
              response.request().method() === "POST",
          );
          await page.getByRole("button", { name: "Upload and validate" }).click();
          const response = await created;
          expect(response.status(), await response.text()).toBe(202);
          importId = response.headers()["x-erev-import-id"] ?? "";
          expect(importId).toMatch(new RegExp(`^${UUID}$`));
          await expect(page).toHaveURL(new RegExp(`/data/imports/${importId}/`));
          // The validation and dry-run jobs move the import on to DIFF_READY (PRD SM-05).
          await expect
            .poll(async () => (await importOf(page.request, importId)).status, {
              timeout: JOB_TIMEOUT_MS,
              intervals: [1_000],
            })
            .toBe("DIFF_READY");
          const validated = await importOf(page.request, importId);
          expect(validated.counts).toMatchObject({ rows: 7, valid: 7, errors: 0 });

          await page.goto(`/data/imports/${importId}/review?${CONTEXT}`);
          const stepper = page.getByTestId("SF-10-stepper");
          await expect(
            stepper.getByRole("listitem").filter({ hasText: "Map columns" }),
          ).toContainText("Not needed: legacy template headers matched");
          await expect(
            page.getByRole("heading", { level: 2, name: "Review changes" }),
          ).toBeVisible();
          // SCREENS §12.2 step 4. API-S-ImportDiff has no SSP member in the rc (D-89 L7-3-Q-27), so
          // RC-SMOKE.3 asserts the version, status, entry count and method through the API.
          await expect(page.getByTestId("SF-10-diff")).toBeVisible();
          await screens.capture(page, "rc-smoke-02-import-review", {
            surface: "SF-10:detail",
            step: "RC-SMOKE.2",
          });
          await a11y.check(page, "SF-10:detail", { state: "review" });

          await page.getByRole("button", { name: "Next", exact: true }).click();
          await expect(page).toHaveURL(new RegExp(`/data/imports/${importId}/approval`));
          await page
            .getByRole("textbox", { name: /^Comment/ })
            .fill("Legacy SKU SSP version 2023-01-01, 7 entries from the UAT template.");
          await page.getByRole("button", { name: "Submit for approval", exact: true }).click();
          const toast = page.getByText(
            /^Submitted for approval\. Request \S+ is waiting for approval\.$/,
          );
          await expect(toast).toBeVisible();
          const submitted = await importOf(page.request, importId);
          expect(submitted.status).toBe("SUBMITTED");
          expect(submitted.approval_request_id ?? "").toMatch(new RegExp(`^${UUID}$`));
          const approval = await json<ApprovalRef>(
            await page.request.get(`/api/v1/approvals/${submitted.approval_request_id ?? ""}`),
          );
          await expect(toast).toHaveText(
            `Submitted for approval. Request ${approval.request_no} is waiting for approval.`,
          );
        });

        await test.step("RC-SMOKE.3 Import approval: priya approves; the import commits the LEGACY-SKU-SSP version", async () => {
          const second = priyaPage();
          const requestId = (await importOf(page.request, importId)).approval_request_id ?? "";
          const approval = await openRequest(second, requestId);
          await a11y.check(second, "SF-12:request", { state: "import" });
          await approveRequest(
            second,
            "priya",
            approval,
            "Reviewed the 7 legacy SKU SSP entries of version 2023-01-01.",
          );
          await expect
            .poll(async () => (await importOf(page.request, importId)).status, {
              timeout: JOB_TIMEOUT_MS,
              intervals: [1_000],
            })
            .toBe("COMMITTED");
          await page.goto(`/data/imports/${importId}?${CONTEXT}`);
          await expect(page).toHaveURL(new RegExp(`/data/imports/${importId}/committed(\\?|$)`));
          await a11y.check(page, "SF-10:detail", { state: "committed" });

          // DIN-4: book LEGACY-SKU-SSP holds version 2023-01-01 APPROVED with 7 legacy_range entries.
          const books = await json<{
            readonly items: readonly { readonly id: string; readonly code: string }[];
          }>(
            await page.request.get("/api/v1/ssp-books", {
              params: { q: LEGACY_SSP_BOOK, limit: 50 },
            }),
          );
          const book = books.items.find((item) => item.code === LEGACY_SSP_BOOK);
          expect(book, `SSP book ${LEGACY_SSP_BOOK}`).toBeDefined();
          const versions = await json<{
            readonly items: readonly {
              readonly id: string;
              readonly legacy_version_label: string | null;
              readonly status: string;
              readonly entry_count: number;
            }[];
          }>(
            await page.request.get(`/api/v1/ssp-books/${book?.id ?? ""}/versions`, {
              params: { limit: 50 },
            }),
          );
          const version = versions.items.find(
            (item) => item.legacy_version_label === LEGACY_SSP_VERSION,
          );
          expect(version, `version ${LEGACY_SSP_VERSION} of ${LEGACY_SSP_BOOK}`).toBeDefined();
          expect(version?.status).toBe("APPROVED");
          expect(version?.entry_count).toBe(7);
          const entries = await json<{
            readonly items: readonly { readonly method: string }[];
          }>(
            await page.request.get(`/api/v1/ssp-book-versions/${version?.id ?? ""}/entries`, {
              params: { limit: 200 },
            }),
          );
          expect(entries.items.map((entry) => entry.method)).toEqual(
            Array.from({ length: 7 }, () => "legacy_range"),
          );
        });

        await test.step("RC-SMOKE.4 Import findings: WLD-B-04 is rejected with two PROGRESS_OVER_DELIVERY messages", async () => {
          await page.goto("/data/imports?entity=AVM-US");
          await page
            .getByTestId("SF-10-row-avm-us-progress-2026-09-invalid-csv")
            .getByRole("link", { name: WLD_B_04_FILE })
            .click();
          await expect(page).toHaveURL(new RegExp(`/data/imports/${UUID}/validate(\\?|$)`));
          const banner = page.getByTestId("SF-10-banner-rejected");
          await expect(
            banner.getByRole("heading", { name: "Rejected: fix the file and upload again" }),
          ).toBeVisible();
          const grid = page
            .getByTestId("SF-10-grid-rows")
            .getByRole("grid", { name: "Import rows" });
          await expect(grid).toBeVisible();
          await expect(grid.getByText("(PROGRESS_OVER_DELIVERY)", { exact: true })).toHaveCount(2);
          await a11y.check(page, "SF-10:detail", { state: "rejected" });
        });

        let k01Id = "";
        await test.step("RC-SMOKE.5 Contract workbench: SF-ORD-10001 from grid Contracts, KPI strip, tracker and O1", async () => {
          await page.goto(`/contracts?${CONTEXT}`);
          await expect(page.getByRole("heading", { level: 1, name: "Contracts" })).toBeVisible();
          await page
            .getByTestId("SF-02-filter-bar")
            .getByRole("searchbox", { name: "Search contracts" })
            .fill(K01);
          const grid = page
            .getByTestId("SF-02-grid-contracts")
            .getByRole("grid", { name: "Contracts" });
          await expect(grid).toBeVisible();
          const row = page.getByTestId("SF-02-row-sf-ord-10001");
          await expect(row.getByRole("rowheader", { name: K01 })).toBeVisible();
          await a11y.check(page, "SF-02");
          await row.getByRole("link", { name: K01 }).click();
          await expect(page).toHaveURL(new RegExp(`/contracts/(${UUID})/obligations`));
          k01Id = /\/contracts\/([0-9a-f-]{36})\//.exec(page.url())?.[1] ?? "";
          await expect(page.getByTestId("SF-03-identifier")).toContainText(K01);
          const strip = page.getByTestId("SF-03-kpi-strip");
          await expect(strip).toBeVisible();
          // SCREENS §4.1.4: six cells, all Explain triggers; cell 6 also carries Contract asset and
          // Unbilled receivable (OQ-S-02), so the strip holds eight triggers (L7-3-Q-30).
          for (const label of KPI_CELLS) {
            await expect(
              strip.getByRole("button", { name: new RegExp(`^Explain ${label}, `) }),
            ).toHaveCount(1);
          }
          await expect(strip.getByRole("button", { name: /^Explain / })).toHaveCount(
            KPI_CELLS.length + KPI_SECONDARY.length,
          );
          for (const label of KPI_SECONDARY) {
            await expect(
              strip.getByRole("button", { name: new RegExp(`^Explain ${label}, `) }),
            ).toHaveCount(1);
          }
          await expect(page.getByTestId("SF-03-tracker")).toBeVisible();
          await a11y.check(page, "SF-03");
          await page.getByTestId("SF-03-row-o1").click();
          const pane = page.getByTestId("SF-03-pane-obligation");
          await expect(pane).toHaveAttribute("role", "region");
          await expect(page.getByRole("region", { name: /^Obligation details: .+/ })).toBeVisible();
          await a11y.check(page, "SF-03:obligation");
        });

        await test.step("RC-SMOKE.6 Schedules: K-01 O1 Sep 2026 9,764.38 with Explain, K-02 9,863.01, SF-04 row", async () => {
          expectDecimal(await p09LineAmount(page.request, k01Id), "9764.38");
          await page.goto(`/contracts/${k01Id}/schedules?${CONTEXT}`);
          const schedule = page
            .getByTestId("SF-03-grid-revenue-schedule")
            .getByRole("grid", { name: "Revenue schedule" });
          await expect(schedule).toBeVisible();
          const p09 = schedule
            .getByRole("row")
            .filter({ hasText: "Sep 2026" })
            .filter({ hasText: "9,764.38" });
          await expect(p09).toHaveCount(1);
          const trigger = p09.getByRole("button", {
            name: "Explain Revenue · Sep 2026 · O1, USD 9,764.38",
          });
          await expect(trigger).toBeVisible();
          await a11y.check(page, "SF-03:schedules");
          await trigger.click();
          const panel = page.getByTestId("SF-03-explain");
          await expect(panel).toBeVisible();
          await expect(panel.getByText(/^USD\s9,764\.38$/).first()).toBeVisible();
          // The asserted Sep 2026 line enters the capture at its bottom edge, so the KPI strip and the Explain
          // header stay in view beside it.
          await p09.evaluate((row) => {
            row.scrollIntoView({ block: "end" });
          });
          await screens.capture(page, "rc-smoke-06-schedules", {
            surface: "SF-03:schedules",
            step: "RC-SMOKE.6",
          });
          await a11y.check(page, "Explain panel");
          await page.keyboard.press("Escape");
          await expect(panel).toHaveCount(0);
          await expect(trigger).toBeFocused();

          const k02Id = await contractIdOf(page.request, K02);
          expectDecimal(await p09LineAmount(page.request, k02Id), "9863.01");
          await page.goto(`/contracts/${k02Id}/schedules?${CONTEXT}`);
          const k02 = page
            .getByTestId("SF-03-grid-revenue-schedule")
            .getByRole("grid", { name: "Revenue schedule" });
          await expect(
            k02.getByRole("row").filter({ hasText: "Sep 2026" }).filter({ hasText: "9,863.01" }),
          ).toHaveCount(1);

          // SCR-URL-24 Rows: Obligation, because the row id names an obligation row (D-88 RC-SMOKE.6;
          // D-89 L7-3-Q-29). Opening the view creates the run (RV-01).
          await page.goto(`/schedules?${CONTEXT}&rows=obligation`);
          await expect(page.getByRole("heading", { level: 1, name: "Schedules" })).toBeVisible();
          await expect(page).toHaveURL(new RegExp(`[?&]run=${UUID}(&|$)`));
          await succeededRun(page.request, runParam(page));
          const grid = page
            .getByTestId("SF-04-grid-waterfall")
            .getByRole("grid", { name: "Revenue waterfall" });
          await expect(grid).toBeVisible({ timeout: JOB_TIMEOUT_MS });
          await expect(page).toHaveURL(/[?&]rows=obligation(&|$)/);
          await expect(grid.getByRole("columnheader", { name: "Sep 2026 (USD)" })).toBeAttached();
          // E2E-02: the run data row of K-01 O1 carries the API decimal string in the FY2026-P09 column.
          const obligationRows = (await reportRows(page.request, runParam(page))).filter(
            (item) => item.row_key === `obligation:${K01}:O1`,
          );
          expect(obligationRows).toHaveLength(1);
          const p09Cell = obligationRows[0]?.["period:FY2026-P09"];
          expectDecimal(amountOf(p09Cell), "9764.38");
          expect((p09Cell as { readonly currency?: unknown } | undefined)?.currency).toBe("USD");
          // Checked before scrolling: the grid's roving tab stop is row 0, which scrolling virtualises away.
          await a11y.check(page, "SF-04");
          const row = await scrolledRow(grid, page.getByTestId("SF-04-row-sf-ord-10001-o1"));
          await expect(
            row.getByRole("button", {
              name: /^Explain Sep 2026 \(USD\) · SF-ORD-10001 O1, USD\s9,764\.38$/,
            }),
          ).toBeVisible();
        });

        await test.step("RC-SMOKE.7 Journal run: maya calculates Sep 2026 AVM-US Gross, balanced, and submits it", async () => {
          await page.goto(`/journals?${CONTEXT}`);
          await expect(page.getByRole("heading", { level: 1, name: "Journals" })).toBeVisible();
          await a11y.check(page, "SF-06");
          await page.getByRole("button", { name: "Run journals", exact: true }).first().click();
          const dialog = page.getByRole("dialog", { name: "Run journals" });
          await expect(dialog).toBeVisible();
          await expect(dialog).toContainText("AVM-US");
          await dialog.getByRole("combobox", { name: "Book" }).click();
          await page.getByRole("option", { name: "ASC 606", exact: true }).click();
          await dialog.getByRole("combobox", { name: "Period" }).click();
          // SCREENS_B §3.1: the option names the period and its DS-CMP-19 word, "Sep 2026 (Period open)".
          await page.getByRole("option", { name: /^Sep 2026 \(/ }).click();
          await dialog.getByRole("radio", { name: "Gross", exact: true }).click();
          await expect(dialog.getByRole("radio", { name: "Gross", exact: true })).toBeChecked();
          await a11y.check(page, "SF-06", { state: "run-journals" });
          await dialog.getByRole("button", { name: "Calculate journals", exact: true }).click();
          await expect(
            page.getByText("Journals calculated for AVM-US Sep 2026.", { exact: true }),
          ).toBeVisible({ timeout: JOB_TIMEOUT_MS });
          await page.getByRole("button", { name: "Open run", exact: true }).click();
          // D-89 L7-3-Q-32: "Open run" carries the calculation's entity, period and book (SCR-URL-20 order).
          await expect(page).toHaveURL(
            new RegExp(`/journals/runs/${UUID}\\?entity=AVM-US&period=FY2026-P09&book=ASC606(&|$)`),
          );
          runId = /\/journals\/runs\/([0-9a-f-]{36})/.exec(page.url())?.[1] ?? "";
          const calculated = await journalRunOf(page.request, runId);
          expect(calculated.state).toBe("draft");
          runNo = calculated.run_no;

          // E2E-02: every balance check at difference 0.00, first as the API strings.
          const summary = await json<{
            readonly balance_checks: readonly { readonly difference: unknown }[];
          }>(await page.request.get(`/api/v1/journal-runs/${runId}/summary`));
          expect(summary.balance_checks.length).toBeGreaterThan(0);
          for (const check of summary.balance_checks) {
            expectDecimal(amountOf(check.difference), "0.00");
          }
          const frame = page.getByTestId("SF-06-page");
          await expect(
            page.getByRole("heading", { level: 1, name: `Journal run ${runNo}` }),
          ).toBeVisible();
          await expect(frame.getByText("Calculated", { exact: true }).first()).toBeVisible();
          const difference = page.getByTestId("SF-06-kpi-difference");
          await expect(difference).toContainText("0.00");
          await expect(difference.getByText("Balanced", { exact: true })).toBeVisible();
          const checks = page.getByTestId("SF-06-grid-balance-checks").locator("tbody tr");
          await expect(checks).toHaveCount(summary.balance_checks.length);
          for (let index = 0; index < summary.balance_checks.length; index += 1) {
            await expect(checks.nth(index).locator("td").nth(5)).toContainText("0.00");
          }
          await screens.capture(page, "rc-smoke-07-journal-run", {
            surface: "SF-06:run",
            step: "RC-SMOKE.7",
          });
          await a11y.check(page, "SF-06:run");

          await frame.getByRole("button", { name: "Submit for approval", exact: true }).click();
          const submit = page.getByRole("dialog", {
            name: `Submit journal run ${runNo} for approval?`,
          });
          await submit
            .getByRole("textbox", { name: /^Comment/ })
            .fill("Sep 2026 AVM-US gross journals for approval.");
          await submit.getByRole("button", { name: "Submit for approval", exact: true }).click();
          await expect(
            page.getByText(`Submitted journal run ${runNo} for approval.`, { exact: true }),
          ).toBeVisible();
        });

        await test.step("RC-SMOKE.8 Journal approval: priya approves the JOURNAL_RUN request; the run is Approved or Exported", async () => {
          const second = priyaPage();
          const pending = await journalRunOf(page.request, runId);
          expect(pending.approval_request_id ?? "").toMatch(new RegExp(`^${UUID}$`));
          const approval = await openRequest(second, pending.approval_request_id ?? "");
          await a11y.check(second, "SF-12:request", { state: "journal-run" });
          await approveRequest(
            second,
            "priya",
            approval,
            "Reviewed the Sep 2026 AVM-US journal run and its balance checks.",
          );
          // 05 ADP-30: the approval writes one JOURNAL_EXPORT outbox message per batch in the deciding
          // transaction, and the relay moves the run on to `exported` within seconds.
          await expect
            .poll(
              async () => {
                const decided = await journalRunOf(page.request, runId);
                return (
                  decided.approved_at !== null && ["approved", "exported"].includes(decided.state)
                );
              },
              { timeout: JOB_TIMEOUT_MS, intervals: [1_000] },
            )
            .toBe(true);
          await page.goto(`/journals/runs/${runId}?${CONTEXT}`);
          const frame = page.getByTestId("SF-06-page");
          // E-34: Approved until the relay exports the batches, then Exported (D-89 L7-3-Q-31).
          await expect(frame.getByText(/^(Approved|Exported)$/).first()).toBeVisible();
        });

        await test.step("RC-SMOKE.9 CSV export: the batches export once, the ZIP manifest ties, Export again posts nothing", async () => {
          // 05 ADP-30: the approval enqueued the export; the relay exports every batch through CSV.
          await expect
            .poll(async () => (await journalRunOf(page.request, runId)).state, {
              timeout: JOB_TIMEOUT_MS,
              intervals: [1_000],
            })
            .toBe("exported");
          await page.goto(`/journals/runs/${runId}?${CONTEXT}`);
          const frame = page.getByTestId("SF-06-page");
          await expect(frame.getByText("Exported", { exact: true }).first()).toBeVisible();
          // SCREENS_B §3.2 Exported: no primary export action, "Export journals" included (D-89 L7-3-Q-31).
          await expect(
            frame.getByRole("button", { name: /^(Export journals|Export to .+|Retry export)$/ }),
          ).toHaveCount(0);
          const listed = await json<{ readonly items: readonly JournalBatchRef[] }>(
            await page.request.get(`/api/v1/journal-runs/${runId}/batches`),
          );
          expect(listed.items.length).toBeGreaterThan(0);
          for (const batch of listed.items) {
            expect(batch.state).toBe("exported");
            expect(batch.adapter).toBe("CSV");
          }
          // The toast's figures on screen: KPI "Batches acknowledged" "0 of <m>" (SCREENS_B §3.2).
          await expect(frame.getByTestId("SF-06-kpi-strip")).toContainText(
            `0 of ${String(listed.items.length)}`,
          );

          await page.goto(`/journals/runs/${runId}/batches?${CONTEXT}`);
          const grid = page
            .getByTestId("SF-06-grid-batches")
            .getByRole("grid", { name: "Batches" });
          await expect(grid).toBeVisible();
          for (const batch of listed.items) {
            const row = grid.getByRole("row").filter({ hasText: batch.external_id });
            await expect(row).toContainText("CSV");
            await expect(row).toContainText("Exported");
          }
          await screens.capture(page, "rc-smoke-09-run-batches", {
            surface: "SF-06:run-batches",
            step: "RC-SMOKE.9",
          });
          await a11y.check(page, "SF-06:run-batches");

          // ADP-33: the first batch downloads as a ZIP of one CSV and its JSON manifest.
          const downloaded = page.waitForEvent("download");
          await grid
            .getByRole("link", { name: /^Download batch / })
            .first()
            .click();
          const download = await downloaded;
          expect(download.suggestedFilename()).toMatch(/\.zip$/);
          const archive = unzip(readFileSync(await download.path()));
          const names = [...archive.keys()];
          const csvNames = names.filter((name) => name.endsWith(".csv"));
          const manifestNames = names.filter((name) => name.endsWith(".json"));
          expect(csvNames).toHaveLength(1);
          expect(manifestNames).toHaveLength(1);
          const csvBytes = archive.get(csvNames[0] ?? "") ?? Buffer.alloc(0);
          const manifest = JSON.parse(
            (archive.get(manifestNames[0] ?? "") ?? Buffer.alloc(0)).toString("utf8"),
          ) as {
            readonly file: string;
            readonly row_count: number;
            readonly totals: { readonly debit: string; readonly credit: string };
            readonly sha256: string;
          };
          const records = csvRecords(csvBytes.toString("utf8")).filter(
            (record) => !(record.length === 1 && record[0] === ""),
          );
          const header = records[0] ?? [];
          const data = records.slice(1);
          expect(manifest.file).toBe(csvNames[0]);
          expect(manifest.row_count).toBe(data.length);
          expect(manifest.totals.debit).toBe(manifest.totals.credit);
          const scale = (manifest.totals.debit.split(".")[1] ?? "").length;
          const column = (name: string) => header.indexOf(name);
          // An empty debit or credit cell is a zero on the other side of the line.
          const sum = (index: number) =>
            data.reduce((total, record) => {
              const cell = record[index] ?? "";
              return total + (cell === "" ? 0n : units(cell, scale));
            }, 0n);
          expect(sum(column("debit"))).toBe(units(manifest.totals.debit, scale));
          expect(sum(column("credit"))).toBe(units(manifest.totals.credit, scale));
          expect(manifest.sha256).toBe(createHash("sha256").update(csvBytes).digest("hex"));

          // CTL-021 path: a repeated export is recorded once and posts no batch again. The batch tuples are
          // read just before the command (D-89 L7-3-Q-31).
          const before = await json<{ readonly items: readonly JournalBatchRef[] }>(
            await page.request.get(`/api/v1/journal-runs/${runId}/batches`),
          );
          expect(before.items.length).toBe(listed.items.length);
          await page.goto(`/journals/runs/${runId}?${CONTEXT}`);
          await page.getByRole("button", { name: "More actions" }).click();
          await page.getByRole("menuitem", { name: "Export again" }).click();
          // DS-CMP-11 confirmation variant: the export modal is an `alertdialog`.
          const again = page.getByRole("alertdialog", {
            name: new RegExp(`^Export journal run ${escapeRegExp(runNo)} to `),
          });
          await expect(
            again.getByTestId("SF-06-export-target").getByRole("combobox", { name: "Target" }),
          ).toContainText("CSV download");
          await a11y.check(page, "SF-06:run", { state: "export" });
          await again.getByRole("button", { name: "Export", exact: true }).click();
          await expect(
            page.getByText("The export was already recorded. No batch was posted again.", {
              exact: true,
            }),
          ).toBeVisible({ timeout: JOB_TIMEOUT_MS });
          const repeated = await json<{ readonly items: readonly JournalBatchRef[] }>(
            await page.request.get(`/api/v1/journal-runs/${runId}/batches`),
          );
          expect(repeated.items.map(batchTuple)).toEqual(before.items.map(batchTuple));
        });

        await test.step("RC-SMOKE.10 Waterfall and RPO reports: K-01 Sep 2026 9,764.38 with drill; K-09 RPO 105,043.80", async () => {
          const marcus = await personas.page("marcus");
          await marcus.goto(`/reports/revenue_waterfall?${CONTEXT}`);
          await expect(
            marcus.getByRole("heading", { level: 1, name: "Revenue waterfall" }),
          ).toBeVisible();
          const run = await runReport(
            marcus,
            marcus
              .getByTestId("SF-08-grid-revenue-waterfall")
              .getByRole("grid", { name: "Revenue waterfall" }),
          );
          await expect(marcus.getByTestId("SF-08-run-stamp")).toContainText("Revenue waterfall v1");
          const rows = await reportRows(marcus.request, run.id);
          const k01Row = rows.find((row) => row.row_key === `contract:${K01}`);
          expect(k01Row, `waterfall row of ${K01}`).toBeDefined();
          expect(Object.values(k01Row ?? {}).map(amountOf)).toContain("9764.38");
          const tieOut = run.tie_out_results.find((item) => item.code === TO_WATERFALL);
          expect(tieOut, `${TO_WATERFALL} in the run's tie-out results`).toBeDefined();
          const strip = marcus.getByTestId("SF-08-banner-tie-outs");
          const item = strip.getByRole("listitem").filter({ hasText: TO_WATERFALL_NAME });
          await expect(item).toContainText("Expected USD");
          await expect(item).toContainText("Actual USD");
          // D-88 L7-3-Q-3: the API serialises `difference` per currency; RV-05: a failing tie-out renders
          // exactly that figure (sup-rc-smoke N-4: present, not Pass).
          const differences = [tieOut?.difference]
            .flat()
            .filter(
              (value): value is { readonly amount: string; readonly currency: string } =>
                typeof value === "object" &&
                value !== null &&
                "amount" in value &&
                "currency" in value,
            );
          expect(differences.length).toBeGreaterThan(0);
          for (const money of differences) {
            expect(typeof money.amount).toBe("string");
            if (tieOut?.result === "FAIL") {
              await expect(item).toContainText(
                `Difference ${money.currency} ${moneyText(money.amount)}`,
              );
            }
          }
          await screens.capture(marcus, "rc-smoke-10-waterfall", {
            surface: "SF-08:report",
            step: "RC-SMOKE.10",
          });
          await a11y.check(marcus, "SF-08:report", { state: "revenue-waterfall" });
          const grid = marcus
            .getByTestId("SF-08-grid-revenue-waterfall")
            .getByRole("grid", { name: "Revenue waterfall" });
          const row = await scrolledRow(grid, marcus.getByTestId("SF-08-row-sf-ord-10001"));
          const figureName = /^Explain Sep 2026 \(USD\) · SF-ORD-10001, USD\s9,764\.38$/;
          const figure = row.getByRole("button", { name: figureName });
          await expect(figure).toBeVisible();
          const cell = row
            .getByRole("gridcell")
            .filter({ has: marcus.getByRole("button", { name: figureName }) });
          await figure.click();
          const panel = marcus.getByTestId("SF-08-explain");
          await expect(panel).toBeVisible();
          await marcus.keyboard.press("Escape");
          await expect(panel).toHaveCount(0);
          await expect(cell).toBeFocused();

          await marcus.goto(`/reports/rpo?${CONTEXT}`);
          await expect(
            marcus.getByRole("heading", { level: 1, name: "Remaining performance obligations" }),
          ).toBeVisible();
          await expect(marcus).toHaveURL(new RegExp(`[?&]run=${UUID}(&|$)`));
          const rpo = await succeededRun(marcus.request, runParam(marcus));
          await expect(marcus.getByTestId("SF-08-run-stamp")).toContainText("30 Sep 2026");
          const bands = (
            (rpo.control_totals?.bands ?? []) as readonly { readonly key: string }[]
          ).map((band) => band.key);
          expect(bands.length).toBeGreaterThan(0);
          const k09 = (await reportRows(marcus.request, rpo.id)).find(
            (item) => item.row_key === `contract:${K09}` && item.section !== 2,
          );
          expect(k09, `RPO row of ${K09}`).toBeDefined();
          expectDecimal(amountOf(k09?.total), "105043.80");
          const bandAmounts = bands.map((key) => String(amountOf(k09?.[key])));
          expect(bandAmounts.reduce((total, amount) => total + units(amount, 2), 0n)).toBe(
            units("105043.80", 2),
          );
          const rpoGrid = marcus.getByTestId("SF-08-grid-remaining-performance-obligations");
          await screens.capture(marcus, "rc-smoke-10-rpo", {
            surface: "SF-08:report",
            step: "RC-SMOKE.10",
          });
          await a11y.check(marcus, "SF-08:report", { state: "rpo" });
          const k09Row = await scrolledRow(
            rpoGrid.getByRole("grid", { name: "Remaining performance obligations" }),
            marcus.getByTestId("SF-08-row-sf-ord-10417"),
          );
          await expect(k09Row).toContainText("105,043.80");
          for (const amount of bandAmounts.filter((value) => units(value, 2) !== 0n)) {
            await expect(k09Row).toContainText(groupedText(amount));
          }
        });

        await test.step("DG-E2E-08 no request to a non-loopback host and no CSP violation", () => {
          expect(network.record()).toEqual({ requests: [], cspViolations: [] });
          expect(second.context?.record).toEqual({ requests: [], cspViolations: [] });
        });
      } finally {
        if (second.context !== null) {
          appendProjectRecord(testInfo, second.context.record);
          await second.context.context.close();
        }
      }
    });
  });
}
