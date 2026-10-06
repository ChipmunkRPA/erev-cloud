// Screen audit rows (SCREENS_B §15; docs/dev-guide.md DG-E2E-05 to DG-E2E-07; PHASES BS-D-09). Each row
// opens its screen state as its persona, captures both themes and runs the axe check.
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";

import type {
  APIRequestContext,
  Browser,
  BrowserContext,
  Locator,
  Page,
  TestInfo,
} from "@playwright/test";

import { ApiClient, expectDecimal, json, newApiContext, webOrigin } from "../support/api";
import {
  demoPassword,
  hasStorageState,
  passwordStep,
  type Persona,
  personaEmail,
  sessionOf,
  signInThroughUi,
  storageStatePath,
  writeStorageState,
} from "../support/auth";
import { expect, test } from "../support/fixtures";
import { findMail, linkIn, waitForMail } from "../support/mail";
import { appendProjectRecord, installNetworkGuard, type NetworkRecord } from "../support/network";
import { createTenant } from "../support/tenants";
import { nextCode } from "../support/totp";
import { awaitJob, createPoolRun, POOL_RUN_NAME, sspBookByCode } from "../support/world";

/** 05 SAR-20: the policy nginx and `vite preview` send on every web response (DG-RUN-23). */
const CONTENT_SECURITY_POLICY =
  "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; " +
  "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; " +
  "form-action 'self'; frame-ancestors 'none'";

test.describe("SF-22 Sign in (RT-01 /sign-in), persona unauthenticated", () => {
  test("SF-22 empty form and session expired", async ({
    page,
    request,
    screens,
    a11y,
    network,
  }) => {
    await page.goto("/sign-in");
    await expect(page.getByRole("heading", { level: 1, name: "Sign in" })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Email" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    await screens.capture(page, "sf-22", { surface: "SF-22" });
    await a11y.check(page, "SF-22");

    await page.goto("/sign-in?reason=session-expired");
    await expect(
      page.getByText("Your session ended after 30 minutes without activity. Sign in again."),
    ).toBeVisible();
    await screens.capture(page, "sf-22-session-expired", { surface: "SF-22" });
    await a11y.check(page, "SF-22", { state: "session-expired" });

    await test.step("REQ-SEC-004 security headers on the web app", async () => {
      const response = await request.get("/sign-in");
      expect(response.status()).toBe(200);
      const headers = response.headers();
      expect(headers["content-security-policy"]).toBe(CONTENT_SECURITY_POLICY);
      expect(headers["x-frame-options"]).toBe("DENY");
      expect(headers["x-content-type-options"]).toBe("nosniff");
      expect(headers["referrer-policy"]).toBe("same-origin");
    });

    await test.step("REQ-SEC-008 no request to a non-loopback host is recorded", () => {
      expect(network.record()).toEqual({ requests: [], cspViolations: [] });
      expect(network.projectRecord()).toEqual({ requests: [], cspViolations: [] });
    });
  });
});

test.describe("SF-22:mfa-challenge Verify your sign-in (RT-02 /sign-in/mfa), persona marcus", () => {
  test("SF-22:mfa-challenge after the password step", async ({ page, screens, a11y, personas }) => {
    await passwordStep(page, "marcus");
    await expect(page).toHaveURL(/\/sign-in\/mfa$/);
    await expect(
      page.getByRole("heading", { level: 1, name: "Verify your sign-in" }),
    ).toBeVisible();
    await expect(
      page.getByText("Enter the 6-digit code from your authenticator app."),
    ).toBeVisible();
    const code = page.getByRole("textbox", { name: "Authentication code" });
    await expect(code).toHaveAttribute("autocomplete", "one-time-code");
    await expect(page.getByRole("button", { name: "Use a recovery code instead" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign in as someone else" })).toBeVisible();
    await screens.capture(page, "sf-22-mfa-challenge", { surface: "SF-22:mfa-challenge" });
    await a11y.check(page, "SF-22:mfa-challenge");

    await test.step("DG-E2E-05 personas: marcus and maya (TOTP) and samuel (password only) sign in through the UI", async () => {
      const marcus = await personas.page("marcus");
      const verified = await sessionOf(marcus.request);
      expect(verified.user?.email).toBe(personaEmail("marcus"));
      expect(verified.mfa_verified_at).not.toBeNull();

      // PRD WLD-U-R2 (rev 1.153): maya's journey signs off, so the seed enrols her as well.
      const maya = await personas.page("maya");
      const signer = await sessionOf(maya.request);
      expect(signer.user?.email).toBe(personaEmail("maya"));
      expect(signer.mfa_verified_at).not.toBeNull();

      const samuel = await personas.page("samuel");
      const passwordOnly = await sessionOf(samuel.request);
      expect(passwordOnly.user?.email).toBe(personaEmail("samuel"));
      expect(passwordOnly.mfa_verified_at).toBeNull();
    });
  });
});

test.describe("SF-23:select Choose a workspace (RT-06 /select-workspace), persona robert", () => {
  test("SF-23:select lists robert's workspaces", async ({ personas, screens, a11y }) => {
    const page = await personas.page("robert");
    await page.goto("/select-workspace");
    await expect(page.getByRole("heading", { level: 1, name: "Choose a workspace" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 2, name: "Demo workspaces" })).toBeVisible();
    await expect(page.getByRole("rowheader", { name: "Avenmoor Holdings (Demo)" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Open Fernhill Software, Inc. (Demo)" }),
    ).toBeVisible();
    await screens.capture(page, "sf-23-select", { surface: "SF-23:select" });
    await a11y.check(page, "SF-23:select");
  });
});

// SF-01 Home (BUILD_SPEC RPS-22; SCREENS §2.9, §0.12 rows SF-01, SCR-IA-01, SCR-IA-08). The Schedules
// and Reports destinations (RPS-7, RPS-6) arrive at the L7 merge, so the rail and favourite rows first
// pass on main.
const AVM_US_SEPTEMBER = "entity=AVM-US&period=FY2026-P09&book=ASC606";
const TEN_DESTINATIONS = [
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
];

interface PendingRequest {
  readonly id: string;
  readonly summary: string;
  readonly subject: { readonly type: string };
  readonly amount: { readonly amount: string; readonly currency: string } | null;
}

/** E2E-02: the DS-FMT-04 digits of a non-negative API decimal string, grouped in thousands. */
function groupedDigits(amount: string): string {
  const [whole = "", fraction] = amount.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return fraction === undefined ? grouped : `${grouped}.${fraction}`;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** J-16.1: the SF-04 waterfall total of AVM-US Sep 2026, from a `revenue_waterfall` JSON run. */
async function septemberWaterfallTotal(request: APIRequestContext): Promise<string> {
  const started = await new ApiClient(request).command("POST", "/api/v1/report-runs", {
    report_code: "revenue_waterfall",
    parameters: {
      entity_codes: ["AVM-US"],
      book: "ASC606",
      from_period_key: "FY2026-P09",
      to_period_key: "FY2026-P09",
    },
    output_format: "JSON",
  });
  const job = await json<{ readonly id: string }>(started, 202);
  const runId = started.headers()["x-erev-report-run-id"];
  if (runId === undefined) {
    throw new Error("POST /report-runs named no report run");
  }
  await awaitJob(request, `/api/v1/jobs/${job.id}`);
  const rows = await json<{ readonly items: readonly Readonly<Record<string, unknown>>[] }>(
    await request.get(`/api/v1/report-runs/${runId}/data`, { params: { limit: 200 } }),
  );
  const total = rows.items.find((row) => row["row_key"] === "TOTAL:USD");
  if (total === undefined) {
    throw new Error("the AVM-US Sep 2026 revenue_waterfall run has no TOTAL:USD row");
  }
  // The Sep 2026 column: the row's `total` column adds the awaiting trigger (RPT-01).
  const amount = amountText(total["period:FY2026-P09"]);
  if (typeof amount !== "string") {
    throw new Error("the TOTAL:USD row carries no decimal string for FY2026-P09");
  }
  return amount;
}

/** Waits until every Home read has settled, so the capture shows figures rather than skeletons. */
async function homeSettled(page: Page): Promise<void> {
  await expect(page.getByTestId("SF-01-kpi-revenue")).toHaveText(/\d/);
  await expect(page.getByRole("group", { name: "Accounting context" })).toBeVisible();
  await expect(page.getByRole("figure", { name: "Revenue by period" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Close status" })).toContainText(
    /Period open|Soft close|Locked|Reopened/,
  );
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
  await expect(page.locator("[data-skeleton]")).toHaveCount(0);
}

/** DG-E2E-07 clipping: a box that clips its content shows all of it (scrollWidth ≤ clientWidth). */
async function expectUnclipped(boxes: Locator): Promise<void> {
  for (const box of await boxes.all()) {
    expect(await box.evaluate((node) => node.scrollWidth <= node.clientWidth)).toBe(true);
  }
}

test.describe("SF-01 Home (RT-07 /home), personas priya, robert and maya", () => {
  test("SF-01 approver priya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("priya");
    await test.step("SF-01", async () => {
      // E2E-02: the figure and the requests first as API strings.
      const figures = await json<{
        readonly revenue: { readonly current: { readonly amount: string } };
      }>(
        await page.request.get("/api/v1/dashboard/home", {
          params: { entity: "AVM-US", period: "FY2026-P09", book: "ASC606" },
        }),
      );
      const total = await septemberWaterfallTotal(page.request);
      expectDecimal(figures.revenue.current.amount, total);
      const waiting = await json<{ readonly items: readonly PendingRequest[] }>(
        await page.request.get("/api/v1/approvals", {
          params: { assigned_to_me: true, status: "PENDING", sort: "submitted_at", limit: 200 },
        }),
      );
      // WLD-B-01 (BG-AVM-0020, USD 146,000.00) and WLD-B-03 (PRINCIPAL_AGENT on BG-AVM-0023). WLD-B-02
      // (USD 2,400.00) is not seeded (L5-4-Q-7; L7-2-Q-26).
      const activation = waiting.items.find(
        (item) =>
          item.subject.type === "CONTRACT_ACTIVATION" && item.amount?.amount === "146000.00",
      );
      const judgement = waiting.items.find((item) => item.subject.type === "JUDGEMENT_RECORD");
      if (activation === undefined || judgement === undefined) {
        throw new Error("priya waits for no WLD-B-01 activation or WLD-B-03 judgement request");
      }
      expectDecimal(activation.amount?.amount, "146000.00");

      await page.goto(`/home?${AVM_US_SEPTEMBER}`);
      await expect(page.getByRole("heading", { level: 1, name: "Home" })).toBeVisible();
      await expect(page.getByRole("region", { name: /^Key figures/ })).toBeVisible();
      await expect(page.getByTestId("SF-01-kpi-revenue")).toHaveText(groupedDigits(total));
      const table = page.getByRole("table", { name: "Waiting for you" });
      await expect(table).toBeVisible();
      const activationRow = table.getByRole("row", {
        name: new RegExp(`^${escapeRegExp(activation.summary)}`),
      });
      await expect(activationRow).toContainText("146,000.00");
      await expect(activationRow).toContainText("USD");
      await expect(
        table.getByRole("rowheader", { name: judgement.summary, exact: true }),
      ).toBeVisible();
      await expect(page.getByRole("region", { name: "Close status" })).toContainText("Period open");
      await homeSettled(page);
      await expectUnclipped(page.getByTestId("SF-01-kpi-strip").locator("dd"));
      await expectUnclipped(page.locator('[data-testid^="SF-01-grid-"]'));
      await screens.capture(page, "sf-01-approver", { surface: "SF-01" });
      await a11y.check(page, "SF-01");
    });
  });

  test("SF-01 viewer robert", async ({ personas, screens, a11y }) => {
    const page = await personas.page("robert");
    await test.step("SF-01", async () => {
      // robert holds several workspaces: open Avenmoor as SF-23:select does (POST /session/tenant).
      const me = await json<{
        readonly memberships: readonly {
          readonly tenant: { readonly id: string; readonly code: string };
        }[];
      }>(await page.request.get("/api/v1/me"));
      const avenmoor = me.memberships.find((membership) => membership.tenant.code === "avenmoor");
      if (avenmoor === undefined) {
        throw new Error("robert is not a member of the avenmoor workspace");
      }
      const opened = await new ApiClient(page.request).command("POST", "/api/v1/session/tenant", {
        tenant_id: avenmoor.tenant.id,
      });
      expect(opened.ok(), await opened.text()).toBe(true);

      await page.goto(`/home?${AVM_US_SEPTEMBER}`);
      await expect(page.getByRole("heading", { level: 1, name: "Home" })).toBeVisible();
      await expect(
        page.getByRole("heading", { name: "You have no approval permissions" }),
      ).toBeVisible();
      await expect(
        page.getByText("Items you can view appear in reports and registers."),
      ).toBeVisible();
      await expect(page.getByRole("region", { name: "Recently viewed" })).toBeVisible();
      await expect(page.getByTestId("SF-01-pane-activity")).toHaveCount(0);
      await homeSettled(page);
      await expectUnclipped(page.getByTestId("SF-01-kpi-strip").locator("dd"));
      await expectUnclipped(page.locator('[data-testid^="SF-01-grid-"]'));
      await screens.capture(page, "sf-01-viewer", { surface: "SF-01" });
      await a11y.check(page, "SF-01", { state: "viewer" });
    });
  });

  test("SF-01 rail and favourite maya", async ({ personas }) => {
    const page = await personas.page("maya");
    await test.step("REQ-UX-001 the rail shows the ten D-02 destinations once Home exists", async () => {
      await page.goto(`/?${AVM_US_SEPTEMBER}`);
      await expect(page).toHaveURL(/\/home\?/);
      await expect(page.getByRole("heading", { level: 1, name: "Home" })).toBeVisible();
      const rail = page.getByRole("navigation", { name: "Primary" });
      await expect(rail.getByRole("link", { name: "Home" })).toHaveAttribute(
        "aria-current",
        "page",
      );
      const names = await rail
        .getByRole("link")
        .evaluateAll((links) => links.map((link) => link.getAttribute("aria-label") ?? ""));
      // The Approvals item carries its pending count in the name (SCR-IA-01 badge).
      expect(names.map((name) => name.replace(/, [\d,]+ pending$/, ""))).toEqual(TEN_DESTINATIONS);
    });

    await test.step("REQ-UX-017 SF-01 favourite added and opened", async () => {
      // [J] L7-2-Q-27: SF-08:report has no page menu with a pin (RPS-6), so the pin is the SCR-IA-08
      // favourite that the SCREENS_B §5.1 pin sends, created through the API.
      const label = `RPO ${randomUUID().slice(0, 8)}`;
      const created = await new ApiClient(page.request).command("POST", "/api/v1/saved-views", {
        screen_code: "SF-08:report",
        name: label,
        config: { target: "report", path: "/reports/rpo", label },
        is_shared: false,
        is_favourite: true,
      });
      const view = await json<{ readonly id: string }>(created, 201);
      try {
        await page.goto(`/home?${AVM_US_SEPTEMBER}`);
        const favourites = page.getByRole("region", { name: "Favourites" });
        await favourites.getByRole("link", { name: label, exact: true }).click();
        await expect(page).toHaveURL(/\/reports\/rpo(\?|$)/);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await page.goto(`/home?${AVM_US_SEPTEMBER}`);
        await page
          .getByRole("region", { name: "Favourites" })
          .getByRole("button", { name: `Unpin ${label}` })
          .click();
        await expect(
          page.getByRole("region", { name: "Favourites" }).getByRole("link", { name: label }),
        ).toHaveCount(0);
      } finally {
        await new ApiClient(page.request).command("DELETE", `/api/v1/saved-views/${view.id}`);
      }
    });
  });
});

/** BS1-D-17: the seeded ROLE_CHANGE request that `grace` approved for custom role deal_desk_analyst. */
const DEAL_DESK_REQUEST = "Add the custom role Deal desk analyst";

/** SCREENS_B §15: a record uuid is resolved by business key through the API before navigating. */
async function dealDeskRequestId(page: Page): Promise<string> {
  const response = await page.request.get(
    "/api/v1/approvals?subject_type=ROLE_CHANGE&sort=-submitted_at",
  );
  expect(response.status(), await response.text()).toBe(200);
  const body = (await response.json()) as {
    readonly items: readonly { readonly id: string; readonly summary: string }[];
  };
  const request = body.items.find((item) => item.summary === DEAL_DESK_REQUEST);
  if (request === undefined) {
    throw new Error(`No approval request "${DEAL_DESK_REQUEST}" is visible to grace`);
  }
  return request.id;
}

/** 04 API-R-09 Submitted by me binding of SCREENS §15.3: every request the persona prepared. */
async function submittedRequests(
  page: Page,
): Promise<{ readonly total: number; readonly summaries: readonly string[] }> {
  const response = await page.request.get(
    "/api/v1/approvals?preparer=me&sort=-submitted_at&limit=500&count=true",
  );
  expect(response.status(), await response.text()).toBe(200);
  const body = (await response.json()) as {
    readonly items: readonly { readonly summary: string }[];
  };
  return {
    total: Number(response.headers()["x-erev-total-count"]),
    summaries: body.items.map((item) => item.summary),
  };
}

// D-85 (L4-5-Q-27, L5-4-Q-1): the empty-state captures use personas without seeded submissions, and
// `sf-12-submitted` binds maya's seeded list (RFD-16 seed kept). [J] priya holds the WLD-B-01 activation
// and the WLD-B-03 review, and marcus and elena hold both permissions, so the empty inbox is tomas's: he
// holds `access.approve`, no seeded request waits for him, and the one request another screens row
// creates in parallel (SF-21) is his own proposal, which Waiting for me leaves out.
test.describe("SF-12 Approvals (RT-54 /approvals), persona tomas", () => {
  test("SF-12 empty inbox as tomas", async ({ personas, screens, a11y }) => {
    const page = await personas.page("tomas");

    await page.goto("/approvals");
    await expect(page.getByRole("heading", { level: 1, name: "Approvals" })).toBeVisible();
    await expect(page.getByRole("link", { name: /^Waiting for me/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await expect(page.getByRole("heading", { name: "No requests waiting for you" })).toBeVisible();
    await expect(
      page.getByText("Requests you can approve appear here, oldest first."),
    ).toBeVisible();
    await screens.capture(page, "sf-12", { surface: "SF-12" });
    await a11y.check(page, "SF-12");
  });
});

test.describe("SF-12:submitted Submitted by me (RT-55 /approvals/submitted), personas maya and priya", () => {
  test("SF-12:submitted seeded list as maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    // PRD WLD-R-02 and WLD-B-01: maya prepared the seeded configuration versions, SSP book versions,
    // activations and judgement records, including the pending activation of BG-AVM-0020.
    // Other rows of the project submit requests as maya while this one runs (the Step 1 row, three of
    // them; the template version row, one). The list is compared with a reading taken while her
    // requests stood still: read, load the page, read again, and take the page only when both
    // readings agree.
    let submitted = await submittedRequests(page);
    for (let attempt = 0; ; attempt += 1) {
      await page.goto("/approvals/submitted");
      await expect(page.getByText(/^[\d,]+ requests?$/)).toBeVisible();
      const after = await submittedRequests(page);
      if (after.total === submitted.total) {
        break;
      }
      expect(attempt, "maya's requests kept changing while the row looked").toBeLessThan(5);
      submitted = after;
    }
    expect(submitted.total).toBeGreaterThan(0);
    expect(submitted.summaries).toContain("Activate BG-AVM-0020");

    await expect(page.getByRole("heading", { level: 1, name: "Approvals" })).toBeVisible();
    await expect(page.getByRole("link", { name: /^Submitted by me/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
    const list = page.getByRole("listbox", { name: "Approval requests" });
    await expect(list).toBeVisible();
    await expect(
      page.getByText(`${String(submitted.total)} requests`, { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("newest first", { exact: true })).toBeVisible();
    // Newest first, in the order of the API binding.
    const options = list.getByRole("option");
    for (const [index, summary] of submitted.summaries.slice(0, 5).entries()) {
      await expect(options.nth(index)).toContainText(summary);
    }
    await screens.capture(page, "sf-12-submitted", { surface: "SF-12:submitted" });
    await a11y.check(page, "SF-12:submitted");
  });

  test("SF-12:submitted empty as priya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("priya");
    expect((await submittedRequests(page)).total).toBe(0);

    await page.goto("/approvals/submitted");
    await expect(page.getByRole("heading", { level: 1, name: "Approvals" })).toBeVisible();
    await expect(page.getByRole("link", { name: /^Submitted by me/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await expect(
      page.getByRole("heading", { name: "You have not submitted any requests." }),
    ).toBeVisible();
    await screens.capture(page, "sf-12-submitted-empty", { surface: "SF-12:submitted" });
    await a11y.check(page, "SF-12:submitted", { state: "empty" });
  });
});

test.describe("SF-12:all All requests (RT-56 /approvals/all), persona grace", () => {
  test("SF-12:all with the deal desk analyst role change selected", async ({
    personas,
    screens,
    a11y,
  }) => {
    const page = await personas.page("grace");

    await page.goto("/approvals/all");
    const list = page.getByRole("listbox", { name: "Approval requests" });
    await list.getByRole("option", { name: new RegExp(DEAL_DESK_REQUEST) }).click();
    await expect(page).toHaveURL(/\/approvals\/requests\/[0-9a-f-]{36}\?view=all$/);
    const detail = page.getByRole("region", { name: `Request details: ${DEAL_DESK_REQUEST}` });
    await expect(detail.getByText("Role change", { exact: true })).toBeVisible();
    await expect(detail.getByText("Approved", { exact: true })).toBeVisible();
    await screens.capture(page, "sf-12-all", { surface: "SF-12:all" });
    await a11y.check(page, "SF-12:all");
  });
});

test.describe("SF-12:request Request (RT-57 /approvals/requests/:requestId), persona grace", () => {
  test("SF-12:request of the deal desk analyst role change", async ({
    personas,
    screens,
    a11y,
  }) => {
    const page = await personas.page("grace");

    await page.goto(`/approvals/requests/${await dealDeskRequestId(page)}`);
    const detail = page.getByRole("region", { name: `Request details: ${DEAL_DESK_REQUEST}` });
    await expect(detail.getByRole("list", { name: "Routing" })).toBeVisible();
    await expect(detail.getByText("No impact on revenue or balances.")).toBeVisible();
    await expect(page.getByRole("form", { name: "Decision" })).toHaveCount(0);
    await screens.capture(page, "sf-12-request", { surface: "SF-12:request" });
    await a11y.check(page, "SF-12:request");
  });
});

// BUILD_SPEC WEB-16 (SCREENS §15.7; §0.12 row SF-12:delegations). The seed holds no delegation, and
// priya holds no `user.manage`: the grid is empty and "New delegation" states why it is unavailable to
// her (API-R-09 has no read of the members a delegation may name). The form and "Revoke delegation" run
// in vitest.
test.describe("SF-12:delegations Delegations (RT-58 /approvals/delegations), persona priya", () => {
  test("SF-12:delegations as priya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("priya");

    await page.goto("/approvals");
    await page.getByRole("link", { name: "Delegations", exact: true }).click();
    await expect(page).toHaveURL(/\/approvals\/delegations$/);
    await expect(page.getByRole("heading", { level: 1, name: "Approvals" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Delegations", exact: true })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await expect(
      page.getByTestId("SF-12-grid-delegations").getByRole("grid", { name: "Delegations" }),
    ).toBeVisible();
    const empty = page.getByTestId("SF-12-empty-delegations");
    await expect(empty.getByRole("heading", { name: "No delegations" })).toBeVisible();
    await expect(
      empty.getByText("Delegate approval permissions for up to 90 days when you are away."),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "New delegation" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    await expect(page.getByRole("group", { name: "Accounting context" })).toBeVisible();
    await screens.capture(page, "sf-12-delegations", { surface: "SF-12:delegations" });
    await a11y.check(page, "SF-12:delegations");
  });
});

// The Step 1 path of SF-03 and SF-12 (SCREENS §4.1.3 "Step 1 path", §4.1.5 banner 6, §4.9.1, §15.4
// region 4; PRD J-03.3 to J-03.3b, SM-02; supervisor ruling R-89). The judgement is recorded in two steps
// in two roles: the preparer submits the review, a reviewer approves it, the preparer records the
// assessment that cites the reviewed record. Every seeded draft already carries its reviewed record, so
// the row books its own contract with the terms of a seeded one. It walks a not-probable outcome to the
// not-a-contract gate and a probable one from there to the approved activation, the path on which three
// defects showed only against the real API (the NOT_A_CONTRACT questionnaire, the catch-up's currency and
// the stale review).
/**
 * A seeded contract whose booking terms the row copies: one subscription line, so that the
 * activation checklist asks for nothing but Step 1. It is a contract of AVM-UK, the entity whose
 * figures no other row of the project reads: the approved activation posts a catch-up, and a row that
 * compares two readings of AVM-US (the Home figures, the cockpit's journal gate) must not meet it.
 */
const STEP1_TERMS_OF = "BG-AVM-0106";
const STEP1_CONTEXT = "entity=AVM-UK&period=FY2026-P09&book=ASC606&step=1";

/** Approve the open request with a comment; the SCR-PERM-05 step-up takes a fresh code (BS1-D-19). */
async function approveOpenRequest(page: Page, persona: Persona, comment: string): Promise<void> {
  const form = page.getByRole("form", { name: "Decision" });
  await form.getByRole("textbox", { name: /^Comment/ }).fill(comment);
  await form.getByRole("button", { name: "Approve", exact: true }).click();
  const toast = page.getByText(/^Approved: /);
  const stepUp = page.getByRole("dialog", { name: "Confirm with your authenticator" });
  await expect(toast.or(stepUp).first()).toBeVisible({ timeout: 30_000 });
  if (await stepUp.isVisible()) {
    const wrong = stepUp.getByText(
      "That code did not match. Check your authenticator app and try again.",
    );
    let refused: number | undefined;
    for (let attempt = 0; attempt < 3 && (await stepUp.isVisible()); attempt += 1) {
      const { code, step } = await nextCode(personaEmail(persona), refused);
      await stepUp.getByRole("textbox", { name: /^Authentication code/ }).fill(code);
      await stepUp.getByRole("button", { name: "Confirm", exact: true }).click();
      await expect(async () => {
        expect((await stepUp.isHidden()) || (await wrong.isVisible())).toBe(true);
      }).toPass({ timeout: 15_000 });
      refused = step;
    }
  }
  await expect(toast).toBeVisible({ timeout: 30_000 });
}

interface Step1Record {
  readonly id: string;
  readonly judgement_no: string;
  readonly topic: string;
  readonly status: string;
  readonly approval_request_id: string | null;
}

/** The Step 1 records of a contract, newest first (04 API-R-13 `GET /judgements`). */
async function step1Records(page: Page, contractId: string): Promise<readonly Step1Record[]> {
  const listed = await json<{ readonly items: readonly Step1Record[] }>(
    await page.request.get("/api/v1/judgements", {
      params: { subject_type: "contract", subject_id: contractId, limit: 50 },
    }),
  );
  return listed.items;
}

test.describe("SF-03 and SF-12 Step 1 path (RT-10, RT-57), personas maya and priya", () => {
  test("Step 1 path: review, assessment, the not-a-contract gate and the approved criteria-met activation", async ({
    personas,
  }) => {
    test.setTimeout(240_000);
    const maya = await personas.page("maya");
    const priya = await personas.page("priya");
    const client = new ApiClient(maya.request);

    const contract =
      await test.step("a draft without a Step 1 record, booked with the terms of a seeded contract", async () => {
        const seeded = (
          await json<{
            readonly items: readonly { readonly id: string; readonly external_id: string }[];
          }>(await client.get("/api/v1/contracts", { q: STEP1_TERMS_OF, limit: 50 }))
        ).items.find((item) => item.external_id === STEP1_TERMS_OF);
        if (seeded === undefined) {
          throw new Error(`No contract ${STEP1_TERMS_OF}`);
        }
        const booked = await json<{
          readonly items: readonly { readonly payload: Readonly<Record<string, unknown>> }[];
        }>(
          await client.get(`/api/v1/contracts/${seeded.id}/events`, {
            event_type: "CONTRACT_BOOKED",
            limit: 5,
          }),
        );
        const terms = booked.items[0]?.payload;
        if (terms === undefined) {
          throw new Error(`${STEP1_TERMS_OF} has no CONTRACT_BOOKED event`);
        }
        const externalId = `E2E-STEP1-${randomUUID().slice(0, 8)}`;
        const made = await client.command("POST", "/api/v1/contracts", {
          ...terms,
          external_id: externalId,
        });
        expect(made.status(), await made.text()).toBe(201);
        const created = (
          await json<{
            readonly items: readonly {
              readonly id: string;
              readonly external_id: string;
              readonly status: string;
              readonly inception_date: string;
            }[];
          }>(await client.get("/api/v1/contracts", { q: externalId, limit: 50 }))
        ).items.find((item) => item.external_id === externalId);
        if (created === undefined) {
          throw new Error(`The booked contract ${externalId} is not listed`);
        }
        expect(created.status).toBe("DRAFT");
        // A contract with the customer and dates of another opens combination suggestions, and the
        // activation checklist refuses while one is open (PRD BR-CON-01): dismiss them, as a user would.
        const suggestions = await json<{ readonly items: readonly { readonly id: string }[] }>(
          await client.get("/api/v1/combination-suggestions", { contract: created.id, limit: 200 }),
        );
        for (const suggestion of suggestions.items) {
          const dismissed = await client.command(
            "POST",
            `/api/v1/combination-suggestions/${suggestion.id}/dismiss`,
            {
              rationale:
                "Booked for the Step 1 row: not negotiated as a package with another contract.",
            },
          );
          expect(dismissed.status(), await dismissed.text()).toBe(200);
        }
        return created;
      });

    const url = `/contracts/${contract.id}/obligations?${STEP1_CONTEXT}`;
    const line = maya.getByTestId("SF-03-step1-path");
    const banner = maya.getByTestId("SF-03-banner-header");

    /** The review drawer with the four criteria met and the outcome of criterion (e). */
    const recordReview = async (opener: Locator, probable: boolean): Promise<Step1Record> => {
      await opener.getByRole("button", { name: "Record Step 1 review" }).click();
      const drawer = maya.getByRole("dialog", { name: "Record Step 1 review" });
      for (const legend of [
        /^Approved and committed/,
        /^Rights identified/,
        /^Payment terms identified/,
        /^Commercial substance/,
      ]) {
        await drawer
          .getByRole("group", { name: legend })
          .getByRole("radio", { name: "Yes" })
          .check();
      }
      await drawer
        .getByRole("group", { name: /^Collectibility probable/ })
        .getByRole("radio", { name: probable ? "Yes" : "No" })
        .check();
      const nonrefundable = drawer.getByRole("group", {
        name: /^Consideration received is non-refundable/,
      });
      if (probable) {
        // 04 T-CON-19: the two members belong to the NOT_A_CONTRACT questionnaire only.
        await expect(nonrefundable).toHaveCount(0);
      } else {
        await nonrefundable.getByRole("radio", { name: "Yes" }).check();
      }
      await drawer
        .getByLabel(/^Rationale/)
        .fill(
          probable
            ? "The customer paid the deposit and its credit grade was raised."
            : "The customer missed two payments and no mitigation is in place.",
        );
      await drawer.getByRole("button", { name: "Submit for review" }).click();
      await expect(maya.getByText(/^Step 1 review JDG-\d+ submitted for review\.$/)).toBeVisible({
        timeout: 30_000,
      });
      const [latest] = await step1Records(maya, contract.id);
      if (latest === undefined) {
        throw new Error("The submitted Step 1 record is not listed");
      }
      expect(latest.status).toBe("SUBMITTED");
      expect(latest.topic).toBe(probable ? "COLLECTIBILITY" : "NOT_A_CONTRACT");
      return latest;
    };

    /** The reviewer opens the record's request and approves it. */
    const review = async (record: Step1Record): Promise<void> => {
      if (record.approval_request_id === null) {
        throw new Error(`${record.judgement_no} has no approval request`);
      }
      await priya.goto(`/approvals/requests/${record.approval_request_id}`);
      await approveOpenRequest(priya, "priya", "Reviewed the Step 1 conclusion and its evidence.");
      const [reviewed] = await step1Records(maya, contract.id);
      expect(reviewed?.status).toBe("REVIEWED");
    };

    const gate =
      await test.step("J-03.3: a not-probable review waits for a Revenue Reviewer and offers no Step 1 command", async () => {
        await maya.goto(url);
        await expect(line).toContainText("No Step 1 review is recorded.");
        const record = await recordReview(line, false);
        await expect(line).toContainText(
          `Step 1 review ${record.judgement_no} is waiting for review by a Revenue Reviewer.`,
        );
        await expect(line.getByRole("link", { name: "View request" })).toBeVisible();
        await expect(line.getByRole("button")).toHaveCount(0);
        await expect(maya.getByTestId("SF-03-tracker-step-1")).toHaveAttribute(
          "aria-label",
          `Step 1, Contract, in review, Review ${record.judgement_no} waiting for review`,
        );
        return record;
      });

    await test.step("J-03.3a and J-03.3b: after the review the assessment cites the record at inception and the API sets the gate", async () => {
      await review(gate);
      await maya.goto(url);
      await expect(line).toContainText(
        new RegExp(
          `^Step 1 review ${gate.judgement_no} was reviewed by Priya Raman on .+ UTC\\. Record the assessment to continue\\.`,
        ),
      );
      await line.getByRole("button", { name: "Record assessment" }).click();
      const drawer = maya.getByRole("dialog", { name: "Record assessment" });
      await expect(drawer).toContainText("Collectibility not probable");
      await expect(drawer).toContainText("ASC 606 and IFRS 15");
      await expect(drawer).toContainText(", the inception date");
      await drawer.getByRole("button", { name: "Record assessment" }).click();
      await expect(maya.getByText("Assessment recorded.")).toBeVisible({ timeout: 30_000 });
      const behind = await json<{ readonly status: string }>(
        await client.get(`/api/v1/contracts/${contract.id}`),
      );
      expect(behind.status).toBe("NOT_A_CONTRACT");
      const assessed = await json<{
        readonly items: readonly {
          readonly effective_date: string;
          readonly payload: {
            readonly book: string;
            readonly is_probable: boolean;
            readonly judgement_record_id: string;
          };
        }[];
      }>(
        await client.get(`/api/v1/contracts/${contract.id}/events`, {
          event_type: "COLLECTIBILITY_ASSESSED",
          limit: 50,
        }),
      );
      expect(
        assessed.items
          .map((event) => ({ date: event.effective_date, ...event.payload }))
          .sort((left, right) => left.book.localeCompare(right.book)),
      ).toMatchObject([
        {
          date: contract.inception_date,
          book: "ASC606",
          is_probable: false,
          judgement_record_id: gate.id,
        },
        {
          date: contract.inception_date,
          book: "IFRS15",
          is_probable: false,
          judgement_record_id: gate.id,
        },
      ]);
    });

    const met =
      await test.step("behind the gate: a probable review, then Record criteria met dated today, then Submit for activation", async () => {
        await maya.goto(url);
        await expect(banner).toContainText(
          "The contract criteria are not met. Receipts post to deposit liability until the criteria are met.",
        );
        await expect(banner).toContainText(
          `(Step 1 review ${gate.judgement_no}). Record a new Step 1 review when the criteria are met.`,
        );
        const record = await recordReview(banner, true);
        await maya.goto(url);
        await expect(banner).toContainText(
          `Step 1 review ${record.judgement_no} is waiting for review by a Revenue Reviewer.`,
        );
        await review(record);
        await maya.goto(url);
        await expect(banner).toContainText("Record criteria met to continue.");
        await banner.getByRole("button", { name: "Record criteria met" }).click();
        const drawer = maya.getByRole("dialog", { name: "Record criteria met" });
        // The date starts at today in the contracting entity's zone (05 TZ-02): read, never typed.
        const shown = await drawer.getByRole("textbox", { name: /^Effective date/ }).inputValue();
        expect(shown).toMatch(/^\d{2} [A-Z][a-z]{2} \d{4}$/);
        await drawer.getByRole("button", { name: "Record criteria met" }).click();
        await expect(
          maya.getByText("Criteria met recorded. Submit the contract for activation."),
        ).toBeVisible({ timeout: 30_000 });
        await maya.goto(url);
        await expect(banner).toContainText(
          `Criteria met on ${shown} (Step 1 review ${record.judgement_no}). Submit the contract for activation.`,
        );
        await banner.getByRole("button", { name: "Submit for activation" }).click();
        await expect(banner).toContainText("Activation is waiting for approval.", {
          timeout: 60_000,
        });
        return { record, shown };
      });

    await test.step("J-03.9: the approver reads the books that move, their dates, records and catch-up, and approves", async () => {
      const pending = await json<{
        readonly items: readonly {
          readonly id: string;
          readonly subject: { readonly id: string };
          readonly impact_preview: {
            readonly summary: {
              readonly criteria_met:
                | readonly {
                    readonly book: string;
                    readonly effective_date: string;
                    readonly judgement_record_id: string;
                    readonly catch_up_total: {
                      readonly amount: string;
                      readonly currency: string;
                    } | null;
                  }[]
                | null;
            };
          } | null;
        }[];
      }>(
        await priya.request.get("/api/v1/approvals", {
          params: { status: "PENDING", subject_type: "CONTRACT_ACTIVATION", limit: 200 },
        }),
      );
      const request = pending.items.find((item) => item.subject.id === contract.id);
      if (request === undefined) {
        throw new Error("No pending activation request of the booked contract");
      }
      const books = request.impact_preview?.summary.criteria_met ?? [];
      expect(books.map((book) => [book.book, book.judgement_record_id])).toEqual([
        ["ASC606", met.record.id],
        ["IFRS15", met.record.id],
      ]);

      await priya.goto(`/approvals/requests/${request.id}`);
      const region = priya.getByRole("region", { name: "Criteria met" });
      const table = region.getByRole("table", { name: "Books that move" });
      for (const [index, label] of ["ASC 606", "IFRS 15"].entries()) {
        const row = table.getByRole("row", { name: new RegExp(`^${label} `) });
        await expect(row).toContainText(met.shown);
        await expect(row).toContainText(`${met.record.judgement_no} · Reviewed by Priya Raman, `);
        // E2E-02: the API's exact decimal, then the rendered amount.
        const catchUp = books[index]?.catch_up_total ?? null;
        if (catchUp === null) {
          throw new Error(`The preview states no catch-up for ${label}`);
        }
        expect(catchUp.amount).toMatch(/^\d+\.\d{2}$/);
        await expect(row.getByRole("cell").last()).toHaveText(
          `${catchUp.currency} ${groupedDigits(catchUp.amount)}`,
        );
      }
      await approveOpenRequest(priya, "priya", "Criteria met: read the books, dates and catch-up.");
      const activated = await json<{ readonly status: string }>(
        await client.get(`/api/v1/contracts/${contract.id}`),
      );
      expect(activated.status).toBe("ACTIVE");
    });
  });
});

/** PRD §2.9 WLD-B-01: the activation of BG-AVM-0020 that waits for priya. */
const WLD_B_01_REQUEST = "Activate BG-AVM-0020";

test.describe("SF-12:request decision form at 1440 × 761 (SCREENS §15.4 region 7), persona priya", () => {
  test("SF-12:request the sticky decision form says when the request continues beneath it", async ({
    personas,
  }) => {
    const page = await personas.page("priya");
    // The viewport of the browser-QA finding: the form covered the fourth change row.
    await page.setViewportSize({ width: 1440, height: 761 });
    const response = await page.request.get(
      "/api/v1/approvals?assigned_to_me=true&status=PENDING&sort=submitted_at&limit=500",
    );
    expect(response.status(), await response.text()).toBe(200);
    const waiting = (
      (await response.json()) as {
        readonly items: readonly { readonly id: string; readonly summary: string }[];
      }
    ).items.find((item) => item.summary === WLD_B_01_REQUEST);
    if (waiting === undefined) {
      throw new Error(`No pending request "${WLD_B_01_REQUEST}" waits for priya`);
    }

    await page.goto(`/approvals/requests/${waiting.id}`);
    const pane = page.getByRole("region", { name: `Request details: ${WLD_B_01_REQUEST}` });
    const form = page.getByRole("form", { name: "Decision" });
    const rows = page.getByTestId("SF-12-diff").locator("tr[data-change-row]");
    await expect(form).toBeVisible();
    await expect(rows.first()).toBeVisible();
    // Region 1: the request opens the contract it activates.
    await expect(pane.getByRole("link", { name: "Open contract" })).toBeVisible();

    // Measured, not read: text assertions pass on a row the form covers.
    const beneath = () =>
      pane.evaluate((element) => element.scrollHeight - element.clientHeight - element.scrollTop);
    const edges = async () => {
      const footer = await form.boundingBox();
      const last = await rows.last().boundingBox();
      if (footer === null || last === null) {
        throw new Error("the decision form or the last change row has no box");
      }
      return { footerTop: footer.y, lastBottom: last.y + last.height };
    };
    expect(await beneath(), "the pane is taller than its viewport").toBeGreaterThan(1);
    const covered = await edges();
    expect(covered.lastBottom, "the form covers the last change row").toBeGreaterThan(
      covered.footerTop,
    );

    // While content lies beneath the form its upper edge says so: the cue is the form's first row, so
    // it covers nothing of the request itself.
    const more = page.getByTestId("SF-12-more-below");
    await expect(more).toBeVisible();
    const cue = await more.boundingBox();
    expect(cue === null ? Number.NaN : cue.y).toBeGreaterThanOrEqual(covered.footerTop);
    expect(cue === null ? Number.NaN : cue.y - covered.footerTop).toBeLessThan(24);

    await more.click();
    await expect.poll(beneath).toBeLessThanOrEqual(1);
    await expect(more).toHaveCount(0);
    const clear = await edges();
    expect(clear.lastBottom, "every change row is clear of the form").toBeLessThanOrEqual(
      clear.footerTop,
    );

    // DS-A11Y-03: N walks the changes; the row that takes focus is never under the form.
    await pane.evaluate((element) => {
      element.scrollTop = 0;
    });
    const count = await rows.count();
    for (let index = 0; index < count; index += 1) {
      await page.keyboard.press("n");
      const focused = rows.nth(index);
      await expect(focused).toBeFocused();
      const box = await focused.boundingBox();
      const footer = await form.boundingBox();
      expect(
        box === null || footer === null ? Number.NaN : box.y + box.height,
        `change row ${String(index + 1)} is clear of the form when it takes focus`,
      ).toBeLessThanOrEqual(footer === null ? 0 : footer.y);
    }
  });
});

/** PRD §2.9 WLD-B-04 and its corrected file (backend/erev_api/domain/demo/avenmoor/imports.py). */
const WLD_B_04_FILE = "avm-us-progress-2026-09-invalid.csv";
const WLD_B_04_CORRECTED_FILE = "avm-us-progress-2026-09.csv";
const XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

test.describe("SF-10 Imports (RT-42 /data/imports), persona maya", () => {
  test("SF-10 maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    // SCR-ST-20 context; the Data rail destination carries `entity` only (SCR-IA-01).
    await page.goto("/data/imports?entity=AVM-US");
    await expect(page.getByRole("heading", { level: 1, name: "Imports" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Data sections" })).toBeVisible();
    const grid = page.getByTestId("SF-10-grid-imports").getByRole("grid", { name: "Imports" });
    await expect(grid).toBeVisible();
    // WLD-B-04: the rejected upload with its caption (PRD SM-05), and the committed corrected file.
    const invalid = page.getByTestId("SF-10-row-avm-us-progress-2026-09-invalid-csv");
    await expect(invalid.getByRole("rowheader", { name: WLD_B_04_FILE })).toBeVisible();
    await expect(invalid.getByText("Rejected: fix the file and upload again")).toBeVisible();
    await expect(invalid.getByText("Progress events (CSV v2)")).toBeVisible();
    const corrected = page.getByTestId("SF-10-row-avm-us-progress-2026-09-csv");
    await expect(corrected.getByRole("rowheader", { name: WLD_B_04_CORRECTED_FILE })).toBeVisible();
    await expect(corrected.getByText("Committed", { exact: true })).toBeVisible();
    await screens.capture(page, "sf-10", { surface: "SF-10" });
    await a11y.check(page, "SF-10");
  });
});

test.describe("SF-10:new New import (RT-43 /data/imports/new), persona maya", () => {
  test("SF-10:new maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    // SCR-LTH-O5: the template and the mode arrive preselected and stay editable.
    await page.goto(
      "/data/imports/new?template=legacy_contract_modification&mode=prospective&entity=AVM-US",
    );
    await expect(page.getByRole("heading", { level: 1, name: "New import" })).toBeVisible();
    const stepper = page.getByTestId("SF-10-stepper");
    await expect(stepper.getByRole("navigation", { name: "Import steps" })).toBeVisible();
    await expect(stepper.locator("li[aria-current='step']")).toContainText("Step 1 of 6, Upload");
    await expect(page.getByRole("combobox", { name: "Template" })).toContainText(
      "Legacy v1: Contract Modification",
    );
    await expect(page.getByRole("radio", { name: "Prospective" })).toBeChecked();
    await expect(page.getByRole("radio", { name: "Retrospective" })).not.toBeChecked();
    await expect(page.getByRole("textbox", { name: /^Effective date/ })).toBeVisible();
    await expect(page.getByTestId("SF-10-dropzone")).toHaveAccessibleName(
      /^Drop a CSV or XLSX file here, or choose a file/,
    );
    await expect(
      page.getByText("Import files must be .xlsx or .csv and at most 50 MiB."),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Upload and validate" })).toBeVisible();
    await screens.capture(page, "sf-10-new", { surface: "SF-10:new" });
    await a11y.check(page, "SF-10:new");
  });
});

/** SCREENS SCR-ST-20: the capture context of WLD-T-01 on SF-10:detail. */
const SF_10_CONTEXT = "entity=AVM-US&period=FY2026-P09&book=ASC606";

/** PRD WLD-F-21 (J-04.1): K-11 O1, 120 units delivered 12 Sep 2026, a Progress events (CSV v2) file. */
const WLD_F_21_FILE = "avm-de-progress-2026-09.csv";
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/** The WLD-F-21 rows under the template's own columns (`GET /import-templates`, NC-19 headers). */
async function progressFile(request: APIRequestContext): Promise<Buffer> {
  const client = new ApiClient(request);
  const listed = await json<{
    readonly items: readonly {
      readonly code: string;
      readonly headers: readonly { readonly name: string }[];
    }[];
  }>(await client.get("/api/v1/import-templates"));
  const template = listed.items.find((item) => item.code === "progress_events");
  if (template === undefined || template.headers.length === 0) {
    throw new Error("the progress_events template lists no columns");
  }
  const values: Readonly<Record<string, string>> = {
    contract: "NS-SO-DE-5004",
    event_type: "DELIVERY_RECORDED",
    effective_date: "2026-09-12",
    obligation_key: "O1",
    quantity: "120",
    trigger: "DELIVERY",
  };
  const names = template.headers.map((header) => header.name);
  const lines = [names.join(","), names.map((name) => values[name] ?? "").join(",")];
  return Buffer.from(`${lines.join("\n")}\n`, "utf-8");
}

test.describe("SF-10:detail Import (RT-44 /data/imports/:importId/:step), persona maya", () => {
  test("SF-10:detail maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    await page.goto("/data/imports?entity=AVM-US");
    const listed = page.getByTestId("SF-10-row-avm-us-progress-2026-09-invalid-csv");
    await listed.getByRole("link", { name: WLD_B_04_FILE }).click();
    // RT-44: `/data/imports/:importId` redirects an INVALID import to `validate` (SCREENS §12.2).
    await expect(page).toHaveURL(/\/data\/imports\/[0-9a-f-]{36}\/validate(\?|$)/);
    const detailPath = new URL(page.url()).pathname;
    const importPath = detailPath.replace(/\/validate$/, "");
    // The redirect keeps the search string; the capture opens the step itself, with the SCR-ST-20
    // context, so no route change moves focus onto the h1 before the capture.
    await page.goto(`${importPath}?${SF_10_CONTEXT}`);
    await expect(page).toHaveURL(new RegExp(`${detailPath}\\?.*entity=AVM-US`));
    await page.goto(`${detailPath}?${SF_10_CONTEXT}`);
    await expect(page).toHaveURL(new RegExp(`${detailPath}\\?.*entity=AVM-US`));
    await expect(
      page.getByRole("heading", { level: 1, name: "Progress events (CSV v2)" }),
    ).toBeVisible();
    await expect(
      page.getByRole("navigation", { name: "Breadcrumb" }).getByText(WLD_B_04_FILE),
    ).toBeVisible();
    const stepper = page.getByTestId("SF-10-stepper");
    await expect(stepper.locator("li[aria-current='step']")).toContainText(
      "Step 3 of 6, Validate, 2 errors in 2 rows",
    );
    const banner = page.getByTestId("SF-10-banner-rejected");
    await expect(
      banner.getByRole("heading", { name: "Rejected: fix the file and upload again" }),
    ).toBeVisible();
    await expect(
      banner.getByText(
        "2 errors in 2 rows. Nothing was committed. Exception items were raised for each finding group.",
      ),
    ).toBeVisible();
    const strip = page.getByTestId("SF-10-kpi-strip");
    await expect(strip).toHaveAccessibleName("Import figures");
    await expect(page.getByTestId("SF-10-kpi-rows")).toHaveText("14");
    await expect(page.getByTestId("SF-10-kpi-valid")).toHaveText("12");
    await expect(page.getByTestId("SF-10-kpi-errors")).toHaveText("2");
    await expect(
      page.getByRole("button", { name: /^PROGRESS_OVER_DELIVERY · 2 rows/ }),
    ).toBeVisible();
    const grid = page.getByTestId("SF-10-grid-rows").getByRole("grid", { name: "Import rows" });
    await expect(grid).toBeVisible();
    // WLD-B-04: two PROGRESS_OVER_DELIVERY messages, errors first (L6-4-Q-14). The code stays in view
    // when the message prose truncates (L6-4-Q-18).
    const codes = grid.getByText("(PROGRESS_OVER_DELIVERY)", { exact: true });
    await expect(codes).toHaveCount(2);
    for (const code of await codes.all()) {
      await expect(code).toBeVisible();
      expect(await code.evaluate((node) => node.scrollWidth <= node.clientWidth)).toBe(true);
    }
    await expect(page.getByTestId("SF-10-row-5")).toContainText("Error");
    await expect(page.getByTestId("SF-10-row-9")).toContainText("Error");
    await expect(page.getByTestId("SF-10-next-blocked")).toHaveText(
      "Validation found 2 errors in 2 rows. Upload a corrected file to continue.",
    );
    await screens.capture(page, "sf-10-detail", { surface: "SF-10:detail" });
    await a11y.check(page, "SF-10:detail");
    // SCREENS §12.3, SCR-URL-32: `row` opens the import row drawer with the whole message.
    await page.goto(`${detailPath}?${SF_10_CONTEXT}&row=5`);
    const drawer = page.getByRole("dialog", { name: /^Row / });
    await expect(drawer).toHaveAccessibleName(/^Row 5/);
    const finding = drawer
      .getByTestId("SF-10-drawer-row")
      .getByRole("listitem")
      .filter({ hasText: "(PROGRESS_OVER_DELIVERY)" });
    await expect(finding).toHaveText(
      /^Row 5, column Quantity: BG-AVM-0004, obligation O1 \(AVM-SEAT-MO\): requested \d+, remaining \d+\. \(PROGRESS_OVER_DELIVERY\)$/,
    );
    expect(await finding.evaluate((node) => node.scrollWidth <= node.clientWidth)).toBe(true);
    await a11y.check(page, "SF-10:detail", { state: "row-drawer" });
  });

  test("SF-10:detail job progress maya", async ({ personas }) => {
    const page = await personas.page("maya");
    const file = await progressFile(page.request);
    let importId: string | null = null;
    try {
      await test.step("REQ-UX-021 SF-10:detail job progress (DS-CMP-24) through validate and diff", async () => {
        await page.goto("/data/imports/new?template=progress_events");
        await expect(page.getByRole("combobox", { name: "Template" })).toContainText(
          "Progress events (CSV v2)",
        );
        await page.getByTestId("SF-10-file-input").setInputFiles({
          name: WLD_F_21_FILE,
          mimeType: "text/csv",
          buffer: file,
        });
        await expect(page.getByTestId("SF-10-file-selected")).toContainText(WLD_F_21_FILE);
        const created = page.waitForResponse(
          (response) =>
            new URL(response.url()).pathname === "/api/v1/imports" &&
            response.request().method() === "POST",
        );
        await page.getByRole("button", { name: "Upload and validate" }).click();
        const response = await created;
        expect(response.status(), await response.text()).toBe(202);
        importId = response.headers()["x-erev-import-id"] ?? null;
        expect(importId ?? "").toMatch(UUID_PATTERN);
        await expect(page).toHaveURL(new RegExp(`/data/imports/${importId ?? ""}/validate$`));
        // DS-CMP-24: the validation job is in place on `validate`, nothing blocks the page.
        await expect(
          page.getByRole("progressbar", { name: `Validating ${WLD_F_21_FILE}` }),
        ).toBeVisible();
        await expect(page.getByTestId("SF-10-stepper")).toBeVisible();
        // The user leaves for Contracts while the jobs run and comes back.
        await page
          .getByRole("navigation", { name: "Primary" })
          .getByRole("link", { name: "Contracts" })
          .click();
        await expect(page.getByRole("heading", { level: 1, name: "Contracts" })).toBeVisible();
        await expect(page.locator("main[aria-busy='true']")).toHaveCount(0);
        await page.goBack();
        await expect(page.getByTestId("SF-10-stepper")).toBeVisible();
        await expect(page.locator("main[aria-busy='true']")).toHaveCount(0);
        // The dry run finishes and the page moves on to `review` (PRD SM-05: VALIDATED → DIFFING →
        // DIFF_READY).
        await expect(page).toHaveURL(new RegExp(`/data/imports/${importId ?? ""}/review$`), {
          timeout: 60_000,
        });
        await expect(
          page.getByTestId("SF-10-diff").getByRole("grid", { name: "Affected records" }),
        ).toBeVisible();
        const shown = await json<{ readonly status: string }>(
          await page.request.get(`/api/v1/imports/${importId ?? ""}`),
        );
        expect(shown.status).toBe("DIFF_READY");
        // SCREENS §12.2 J-04.1: revenue 53,504.59 in Sep 2026.
        await expect(page.getByTestId("SF-10-grid-revenue-delta")).toContainText("53,504.59");
      });
    } finally {
      if (importId !== null) {
        // The upload is not committed: cancelling it leaves K-11 and the duplicate check as seeded.
        const cancelled = await new ApiClient(page.request).command(
          "POST",
          `/api/v1/imports/${importId}/cancel`,
        );
        expect([200, 409], await cancelled.text()).toContain(cancelled.status());
      }
    }
  });
});

test.describe("SF-10:templates Import templates (RT-45 /data/templates), persona maya", () => {
  test("SF-10:templates maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    await page.goto("/data/templates?entity=AVM-US");
    await expect(page.getByRole("heading", { level: 1, name: "Import templates" })).toBeVisible();
    const table = page.getByTestId("SF-10-grid-templates");
    await expect(table).toHaveAccessibleName("Import templates");
    await expect(table.getByRole("rowheader", { name: "Legacy v1: SKU SSP" })).toBeVisible();
    // The button fetches the XLSX (05 UPL-10) and saves it under the template code.
    const answered = page.waitForResponse((response) =>
      response.url().endsWith("/api/v1/import-templates/legacy_sku_ssp/download"),
    );
    const downloaded = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download Legacy v1: SKU SSP" }).click();
    const response = await answered;
    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).toBe(XLSX_MEDIA_TYPE);
    const download = await downloaded;
    expect(download.suggestedFilename()).toBe("legacy_sku_ssp.xlsx");
    // The saved file is the workbook: an XLSX is a ZIP container, which opens with "PK". The fetch
    // response body is not kept once the page has read it as a blob.
    const saved = readFileSync(await download.path());
    expect(saved.subarray(0, 2).toString("latin1")).toBe("PK");
    await screens.capture(page, "sf-10-templates", { surface: "SF-10:templates" });
    await a11y.check(page, "SF-10:templates");
  });
});

/** SCREENS §13.8 WLD-B-04: the catalogue title of the two items of the rejected upload. */
const WLD_B_04_TITLE = "Delivery exceeds the remaining quantity";

test.describe("SF-11 Exceptions (RT-46 /data/exceptions), persona maya", () => {
  test("SF-11 maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    await page.goto(`/data/exceptions?${SF_10_CONTEXT}`);
    await expect(page.getByRole("heading", { level: 1, name: "Exceptions" })).toBeVisible();
    await expect(
      page
        .getByRole("navigation", { name: "Data sections" })
        .getByRole("link", { name: "Exceptions" }),
    ).toHaveAttribute("aria-current", "page");
    // SCREENS §13.3: the queue opens with Status is Open or In progress, sorted by severity.
    await expect(page).toHaveURL(/[?&]f\.status=in:OPEN,IN_PROGRESS(&|$)/);
    await expect(page.getByRole("button", { name: /^Sort: Severity/ })).toBeVisible();
    const list = page
      .getByTestId("SF-11-grid-exceptions")
      .getByRole("listbox", { name: "Exceptions" });
    await expect(list).toBeVisible();
    // WLD-B-04: rows 5 and 9 of the rejected upload raised two Blocking import items (SCREENS §13.8).
    const option = page.getByTestId("SF-11-row-progress-over-delivery").first();
    await expect(option).toHaveAttribute("role", "option");
    await expect(option).toContainText(WLD_B_04_TITLE);
    await expect(option).toContainText("Blocking");
    await expect(option).toContainText("Import");
    await expect(list.getByRole("option", { name: /PROGRESS_OVER_DELIVERY/ })).toHaveCount(2);
    for (const key of ["BG-AVM-0004", "BG-AVM-0008"]) {
      await expect(
        list.getByRole("option", { name: new RegExp(`PROGRESS_OVER_DELIVERY.*${key}`) }),
      ).toBeVisible();
    }
    await expect(
      page.getByText("Select an exception to see its location, message and next steps."),
    ).toBeVisible();
    await screens.capture(page, "sf-11", { surface: "SF-11" });
    await a11y.check(page, "SF-11");
  });
});

test.describe("SF-11:item Exception (RT-47 /data/exceptions/:exceptionId), persona maya", () => {
  test("SF-11:item maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    await page.goto(`/data/exceptions?${SF_10_CONTEXT}`);
    const list = page
      .getByTestId("SF-11-grid-exceptions")
      .getByRole("listbox", { name: "Exceptions" });
    // Selecting the WLD-B-04 row 5 item opens RT-47 inside the queue and keeps the queue's search.
    await list.getByRole("option", { name: /PROGRESS_OVER_DELIVERY.*BG-AVM-0004/ }).click();
    await expect(page).toHaveURL(
      /\/data\/exceptions\/[0-9a-f-]{36}\?.*entity=AVM-US.*f\.status=in:OPEN,IN_PROGRESS/,
    );
    const itemUrl = page.url();
    const pane = page.getByRole("region", { name: `Exception details: ${WLD_B_04_TITLE}` });
    await expect(pane).toHaveAttribute("data-testid", "SF-11-pane-exception");
    await expect(
      list.getByRole("option", { name: /PROGRESS_OVER_DELIVERY.*BG-AVM-0004/ }),
    ).toHaveAttribute("aria-selected", "true");
    // The capture opens the item URL in a new document, so neither a route change nor the history
    // state of the selection (focus on the selected option) moves focus before the capture.
    await page.goto("about:blank");
    await page.goto(itemUrl);
    await expect(pane.getByRole("heading", { level: 2, name: WLD_B_04_TITLE })).toBeVisible();
    await expect(pane.getByText("PROGRESS_OVER_DELIVERY", { exact: true })).toBeVisible();
    await expect(pane.getByText("Blocking", { exact: true })).toBeVisible();
    await expect(pane.getByText("Open", { exact: true })).toBeVisible();
    await expect(
      pane.getByText(
        /^Row 5, column Quantity: BG-AVM-0004, obligation O1 \(AVM-SEAT-MO\): requested \d+, remaining \d+\. \(PROGRESS_OVER_DELIVERY\)$/,
      ),
    ).toBeVisible();
    await expect(pane.getByRole("link", { name: WLD_B_04_FILE })).toBeVisible();
    // The input was never committed, so dismissal is available and no blocked line shows (§13.5).
    const actions = pane.getByRole("group", { name: "Actions" });
    await expect(actions.getByRole("button", { name: "Dismiss exception" })).toBeVisible();
    await expect(actions.getByRole("button", { name: "Request waiver" })).toBeVisible();
    await expect(pane.getByTestId("SF-11-dismiss-blocked")).toHaveCount(0);
    await screens.capture(page, "sf-11-item", { surface: "SF-11:item" });
    await a11y.check(page, "SF-11:item");
  });
});

test.describe("SF-15 Settings (RT-71 /settings), persona tomas", () => {
  test("SF-15 section index as tomas", async ({ personas, screens, a11y }) => {
    const page = await personas.page("tomas");

    await page.goto("/settings");
    await expect(page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
    const preferences = page.getByRole("region", { name: "Your preferences" });
    await expect(preferences.getByRole("link", { name: "Notifications" })).toBeVisible();
    await expect(preferences.getByRole("link", { name: "Profile" })).toBeVisible();
    // SCREENS_B §9.1 sample world: WLD-T-01 completed setup, so no setup banner.
    await expect(page.getByTestId("SF-15-banner-setup")).toHaveCount(0);
    await screens.capture(page, "sf-15", { surface: "SF-15" });
    await a11y.check(page, "SF-15");
  });
});

test.describe("SF-15:notifications Notification preferences (RT-72 /settings/notifications), persona maya", () => {
  test("SF-15:notifications as maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");

    await page.goto("/settings/notifications");
    await expect(
      page.getByRole("heading", { level: 1, name: "Notification preferences" }),
    ).toBeVisible();
    const table = page.getByRole("table", { name: "Notification preferences" });
    await expect(table.getByRole("rowheader")).toHaveCount(12);
    await expect(
      page.getByRole("switch", { name: "Audit chain verification failed, email" }),
    ).toHaveAttribute("aria-disabled", "true");
    await expect(
      page.getByText(
        "Emails contain the object reference and a link, never amounts or customer data.",
      ),
    ).toBeVisible();
    await screens.capture(page, "sf-15-notifications", { surface: "SF-15:notifications" });
    await a11y.check(page, "SF-15:notifications");
  });
});

/** WEB-17: the custom role `tomas` proposes, so `grace` receives APPROVAL_ASSIGNED (BSF-D-04). */
const CAPTURE_NOTIFY_ROLE = {
  code: "capture_notify_role",
  name: "Capture notify role",
  description: "Proposed by the SF-21 capture step.",
  permissions: ["contract.read"],
};

/** WEB-16: four custom roles `tomas` proposes for `grace`: one approved, one rejected, two in bulk. */
const CAPTURE_ROLES = (["A", "B", "C", "D"] as const).map((letter) => ({
  code: `capture_role_${letter.toLowerCase()}`,
  name: `Capture role ${letter}`,
  description: "Proposed by the SF-12 decision step.",
  permissions: ["contract.read"],
}));

function captureRequest(letter: "A" | "B" | "C" | "D"): string {
  return `Add the custom role Capture role ${letter}`;
}

/** SCR-PERM-05: answers the step-up dialog a command opened; a refused code is retried with a later step. */
async function answerStepUp(page: Page, persona: Persona): Promise<void> {
  const dialog = page.getByRole("dialog", { name: "Confirm with your authenticator" });
  const wrong = dialog.getByText(
    "That code did not match. Check your authenticator app and try again.",
  );
  let refused: number | undefined;
  for (let attempt = 0; attempt < 3; attempt += 1) {
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
  throw new Error(`the step-up refused three codes for ${persona}`);
}

/** The outcome of a command that may ask for a step-up first: the dialog is answered, then `outcome` shows. */
async function afterStepUp(page: Page, persona: Persona, outcome: Locator): Promise<void> {
  const stepUp = page.getByRole("dialog", { name: "Confirm with your authenticator" });
  await expect(outcome.or(stepUp).first()).toBeVisible({ timeout: 30_000 });
  if (await stepUp.isVisible()) {
    await answerStepUp(page, persona);
  }
  await expect(outcome).toBeVisible({ timeout: 30_000 });
}

test.describe("SF-21 Notifications (placement, /approvals), persona grace", () => {
  // WEB-16: every role `tomas` proposes notifies `grace`, and the SF-21 row counts her unread
  // notifications. The two rows run in one worker, SF-21 first.
  test.describe.configure({ mode: "serial" });

  test("SF-21 popover with one unread APPROVAL_ASSIGNED item, then a saved preference", async ({
    personas,
    screens,
    a11y,
  }) => {
    const tomas = await personas.page("tomas");
    const page = await personas.page("grace");

    await test.step("REQ-PLT-021 SF-21 popover: unread count, mark read, open link; SF-15:notifications saves a preference", async () => {
      const proposed = await new ApiClient(tomas.request).command(
        "POST",
        "/api/v1/roles",
        CAPTURE_NOTIFY_ROLE,
      );
      const role = await json<{ readonly pending_approval_request_id: string | null }>(
        proposed,
        201,
      );
      const requestId = role.pending_approval_request_id;
      expect(requestId, "the proposal opened a ROLE_CHANGE approval request").not.toBeNull();

      await page.goto("/approvals");
      const bell = page.getByRole("button", { name: "Notifications, 1 unread" });
      await expect(bell).toBeVisible();
      await bell.click();
      const panel = page.getByRole("dialog", { name: "Notifications" });
      const item = panel.getByRole("link", { name: new RegExp(CAPTURE_NOTIFY_ROLE.name) });
      await expect(item).toBeVisible();
      await screens.capture(page, "sf-21", { surface: "SF-21" });
      await a11y.check(page, "SF-21");

      // L3-3-Q-36: DS-CMP-05 renders "Mark all as read" only while the Unread tab lists an item, and
      // opening the only unread item marks it read, so the step marks all read first and then opens
      // the item from "All". L3-3-Q-37: the shell names the bell "Notifications" at zero unread.
      await panel.getByRole("button", { name: "Mark all as read" }).click();
      await expect(page.getByRole("button", { name: "Notifications", exact: true })).toBeVisible();
      await panel.getByRole("tab", { name: "All" }).click();
      await panel.getByRole("link", { name: new RegExp(CAPTURE_NOTIFY_ROLE.name) }).click();
      await expect(page).toHaveURL(new RegExp(`/approvals/requests/${String(requestId)}$`));

      await page.goto("/settings/notifications");
      const approvedEmail = page.getByRole("switch", { name: "Your item was approved, email" });
      await expect(approvedEmail).toHaveAttribute("aria-checked", "false");
      await approvedEmail.click();
      await expect(page.getByText("Preferences saved.")).toBeVisible();
      await page.reload();
      await expect(
        page.getByRole("switch", { name: "Your item was approved, email" }),
      ).toHaveAttribute("aria-checked", "true");
    });
  });

  // BUILD_SPEC WEB-16 (SCREENS §15.4, §15.5; §0.12 row SF-12 bulk selection; PHASES §15.2 REQ-UX-013).
  test("SF-12 decisions and bulk selection as grace", async ({ personas, screens, a11y }) => {
    const tomas = await personas.page("tomas");
    const page = await personas.page("grace");
    for (const role of CAPTURE_ROLES) {
      const proposed = await json<{ readonly pending_approval_request_id: string | null }>(
        await new ApiClient(tomas.request).command("POST", "/api/v1/roles", role),
        201,
      );
      expect(proposed.pending_approval_request_id, `${role.name} opened a request`).not.toBeNull();
    }

    await test.step("REQ-UX-013 SF-12 inbox: approve with comment, reject, bulk selection", async () => {
      // SCREENS §15.3: the Type chip keeps the inbox to the role changes waiting for grace.
      await page.goto("/approvals?f.type=is:ROLE_CHANGE");
      await expect(
        page
          .getByTestId("SF-12-filter-bar")
          .getByRole("button", { name: "Type is Role change, edit filter" }),
      ).toBeVisible();
      const list = page.getByRole("listbox", { name: "Approval requests" });
      const form = page.getByRole("form", { name: "Decision" });

      await test.step("approve Capture role A with a comment", async () => {
        await list.getByRole("option", { name: new RegExp(captureRequest("A")) }).click();
        await expect(
          page.getByRole("region", { name: `Request details: ${captureRequest("A")}` }),
        ).toBeVisible();
        await approveOpenRequest(page, "grace", "Read access for the capture.");
        await expect(
          page.getByText(`Approved: ${captureRequest("A")}.`, { exact: true }),
        ).toBeVisible();
      });

      await test.step("reject Capture role C with a comment", async () => {
        await list.getByRole("option", { name: new RegExp(captureRequest("C")) }).click();
        await expect(
          page.getByRole("region", { name: `Request details: ${captureRequest("C")}` }),
        ).toBeVisible();
        await form.getByRole("textbox", { name: /^Comment/ }).fill("Not needed for the capture.");
        await form.getByRole("button", { name: "Reject", exact: true }).click();
        await page
          .getByRole("alertdialog", { name: `Reject ${captureRequest("C")}?` })
          .getByRole("button", { name: "Reject request" })
          .click();
        await afterStepUp(
          page,
          "grace",
          page.getByText(`Rejected: ${captureRequest("C")}.`, { exact: true }),
        );
      });

      await test.step("bulk selection: Capture role B and Capture role D", async () => {
        await page.getByRole("button", { name: "Select for bulk approval" }).click();
        // The request closes for the grid, and the chip stays.
        await expect(page).toHaveURL(/\/approvals\?layout=bulk&f\.type=is:ROLE_CHANGE$/);
        const grid = page
          .getByTestId("SF-12-grid-bulk")
          .getByRole("grid", { name: "Requests waiting for me" });
        await expect(grid).toHaveAttribute("aria-multiselectable", "true");
        for (const header of ["Request", "Type", "Currency", "Amount", "Preparer", "Submitted"]) {
          // A header's name ends with its menu button: "<header> Column options: <header>".
          await expect(
            grid.getByRole("columnheader", {
              name: `${header} Column options: ${header}`,
              exact: true,
            }),
          ).toBeVisible();
        }
        for (const letter of ["B", "D"] as const) {
          await grid.getByRole("checkbox", { name: `Select ${captureRequest(letter)}` }).check();
        }
        const bar = page.getByRole("region", { name: "2 selected" });
        await expect(bar.getByRole("button", { name: "Approve 2 items" })).toBeVisible();
        await expect.poll(() => clippedBoxes(grid)).toEqual([]);
        await expect(page.getByRole("group", { name: "Accounting context" })).toBeVisible();
        // The toast of the rejection leaves by itself before the capture.
        await expect(page.getByText(/^Rejected: /)).toHaveCount(0);
        await screens.capture(page, "sf-12-bulk", { surface: "SF-12" });
        await a11y.check(page, "SF-12", { state: "bulk" });

        await bar.getByRole("button", { name: "Approve 2 items" }).click();
        const dialog = page.getByRole("dialog", { name: "Approve 2 items" });
        for (const letter of ["B", "D"] as const) {
          await expect(dialog.getByText(captureRequest(letter), { exact: true })).toBeVisible();
        }
        await dialog.getByRole("textbox", { name: /^Comment/ }).fill("Both roles read contracts.");
        await dialog
          .getByRole("checkbox", {
            name: "I reviewed the changes and impact of every selected item.",
          })
          .check();
        await dialog.getByRole("button", { name: "Approve 2 items" }).click();
        await afterStepUp(page, "grace", page.getByText("Approved 2 items.", { exact: true }));
        await expect(dialog).toHaveCount(0);
        for (const letter of ["B", "D"] as const) {
          await expect(
            grid.getByRole("checkbox", { name: `Select ${captureRequest(letter)}` }),
          ).toHaveCount(0);
        }
      });

      await test.step("the resulting chips: Approved, Rejected, Approved, Approved", async () => {
        await page.goto("/approvals/all?f.type=is:ROLE_CHANGE");
        const all = page.getByRole("listbox", { name: "Approval requests" });
        for (const [letter, chip] of [
          ["A", "Approved"],
          ["C", "Rejected"],
          ["B", "Approved"],
          ["D", "Approved"],
        ] as const) {
          await expect(
            all
              .getByRole("option", { name: new RegExp(captureRequest(letter)) })
              .getByText(chip, { exact: true }),
          ).toBeVisible();
        }
      });
    });
  });

  // W-12 (SCREENS_B §9.10 rev 1.60; PRD J-22.1; 04 T-PLT-10 rev 1.148): a role for one legal entity,
  // granted through the product. The row sits in this describe, after SF-21, because the request it
  // opens notifies grace and the SF-21 row counts her unread notifications. It leaves an invited
  // member with an active Revenue Reviewer role for AVM-DE and an approved ROLE_ASSIGNMENT request.
  test("SF-14 J-22.1: tomas invites a reviewer for AVM-DE only, grace approves, and the role names its entity", async ({
    personas,
  }) => {
    const tomas = await personas.page("tomas");
    const tag = randomUUID().slice(0, 8);
    const name = `Lena Fischer ${tag}`;
    const email = `lena.${tag}@demo.erev`;

    await tomas.goto("/settings/users");
    await tomas.getByRole("button", { name: "Invite user" }).click();
    const drawer = tomas.getByRole("dialog", { name: "Invite user" });
    await drawer.getByLabel("Email").fill(email);
    await drawer.getByLabel("Display name").fill(name);
    await drawer.getByRole("combobox", { name: "Role" }).click();
    await tomas.getByRole("option", { name: "Revenue Reviewer", exact: true }).click();
    // tomas holds user.manage for all entities: both scopes are his to give.
    await expect(drawer.getByRole("radio", { name: "All entities" })).toBeChecked();
    await drawer.getByRole("radio", { name: "Selected entities" }).check();
    await drawer.getByRole("combobox", { name: "Entities" }).fill("AVM-DE");
    await tomas.getByRole("option", { name: /^AVM-DE · / }).click();
    await drawer.getByRole("button", { name: "Send invitation" }).click();
    await expect(tomas.getByText(`Invitation for ${email} is waiting for approval.`)).toBeVisible();

    // The request names the entity (04 T-PLT-10: "Grant <role> to <member> for <codes>"), and the
    // second administrator decides it.
    const grace = await personas.page("grace");
    const waiting = await json<{
      readonly items: readonly { readonly id: string; readonly summary: string }[];
    }>(
      await grace.request.get("/api/v1/approvals", {
        params: { assigned_to_me: true, status: "PENDING", limit: 200 },
      }),
    );
    const request = waiting.items.find((item) => item.summary.includes(name));
    expect(request?.summary, `a request for ${name} waits for grace`).toContain("AVM-DE");
    await grace.goto(`/approvals/requests/${request?.id ?? ""}`);
    await approveOpenRequest(grace, "grace", "Scope AVM-DE as requested.");

    // The member's page: the role is active for AVM-DE, and tomas, whose role.manage covers every
    // entity, may revoke it.
    const listed = await json<{ readonly items: readonly { readonly id: string }[] }>(
      await tomas.request.get("/api/v1/users", { params: { q: email, limit: 5 } }),
    );
    await tomas.goto(`/settings/users/${listed.items[0]?.id ?? ""}`);
    const role = tomas
      .getByRole("table", { name: "Roles" })
      .getByRole("row", { name: /Revenue Reviewer/ });
    await expect(role).toContainText("AVM-DE");
    await expect(role).toContainText("Active");
    await expect(role.getByRole("button", { name: "Revoke role" })).toBeVisible();
  });
});

test.describe("SF-15:profile Profile (RT-73 /settings/profile), persona maya", () => {
  test("SF-15:profile as maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");

    await page.goto("/settings/profile");
    await expect(page.getByRole("heading", { level: 1, name: "Profile" })).toBeVisible();
    const security = page.getByRole("region", { name: "Sign-in and security" });
    // PRD WLD-U-R2 (rev 1.153): maya's journey signs off, so the seed enrols her in a factor.
    await expect(security.getByText("Enrolled", { exact: true })).toBeVisible();
    await expect(security.getByRole("button", { name: "Regenerate recovery codes" })).toBeVisible();
    await expect(page.getByRole("radiogroup", { name: "Theme" })).toBeVisible();
    await expect(page.getByRole("combobox", { name: "Number format" })).toBeVisible();
    await screens.capture(page, "sf-15-profile", { surface: "SF-15:profile" });
    await a11y.check(page, "SF-15:profile");

    // SCREENS_B §9.9 States, "Not enrolled": read as samuel, whose Auditor role asks for no factor.
    const samuel = await personas.page("samuel");
    await samuel.goto("/settings/profile");
    const optional = samuel.getByRole("region", { name: "Sign-in and security" });
    await expect(optional.getByText("Not enrolled")).toBeVisible();
    await expect(
      optional.getByRole("link", { name: "Set up multi-factor authentication" }),
    ).toBeVisible();
  });
});

/** DS-FMT-19 label of a Gregorian month period from its start date, for example "Jan 2026". */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function monthLabel(startDate: string): string {
  const [year = "", month = ""] = startDate.split("-");
  return `${MONTHS[Number(month) - 1] ?? month} ${year}`;
}

test.describe("SF-23 Top bar and context pill (SCREENS §1.1, §1.3), persona maya", () => {
  test("REQ-UX-002 top bar as maya", async ({ personas }) => {
    const page = await personas.page("maya");

    await test.step("REQ-UX-002 top bar, context pill defaults (BR-UX-01), command palette trigger", async () => {
      await page.goto("/settings/profile");
      // Without a stored context (BR-UX-01 "if none").
      await page.evaluate(() => {
        for (const key of Object.keys(window.localStorage)) {
          if (key.startsWith("erev.context.")) {
            window.localStorage.removeItem(key);
          }
        }
      });
      await page.reload();
      const periods = await json<{
        readonly items: readonly {
          readonly is_first_open: boolean;
          readonly period: { readonly start_date: string };
        }[];
      }>(
        await page.request.get("/api/v1/periods", {
          params: { entity: "AVM-DE", book: "ASC606", state: "open" },
        }),
      );
      const first = periods.items.find((item) => item.is_first_open);
      if (first === undefined) {
        throw new Error("AVM-DE keeps no open ASC 606 period with is_first_open");
      }
      const group = page.getByRole("group", { name: "Accounting context" });
      await expect(group.getByRole("button", { name: /^Entity: AVM-DE · / })).toBeVisible();
      await expect(
        group.getByRole("button", { name: `Period: ${monthLabel(first.period.start_date)}, open` }),
      ).toBeVisible();
      await expect(group.getByRole("button", { name: "Book: ASC 606" })).toBeVisible();
      await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
      await page.getByRole("button", { name: "Search or run a command" }).click();
      await expect(page.getByRole("dialog", { name: "Command palette" })).toBeVisible();
    });
  });
});

/** 04 E-120 scopes and the captions of their tables (SCREENS §1.4). */
const SEARCH_CAPTIONS: Readonly<Record<string, string>> = {
  contracts: "Contracts",
  customers: "Customers",
  invoices: "Invoices",
  obligations: "Obligations",
  journals: "Journals",
};

interface SearchAnswer {
  readonly results: readonly {
    readonly scope: string;
    readonly items: readonly {
      readonly id: string;
      readonly primary: string;
      readonly secondary: string;
    }[];
    readonly next_cursor: string | null;
  }[];
}

test.describe("SF-24 Command palette and SF-24:results Search results (RT-95 /search), persona maya", () => {
  test("SF-24:results maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    // SCREENS §1.4: the first load reads `GET /search?q=SF-ORD&limit=25`, the first page of every
    // scope; the page shows what that answers, a table a scope that found something.
    const answer = await json<SearchAnswer>(
      await new ApiClient(page.request).get("/api/v1/search", { q: "SF-ORD", limit: 25 }),
    );
    expect(answer.results.map((group) => group.scope)).toEqual(Object.keys(SEARCH_CAPTIONS));
    const found = answer.results.find((group) => group.scope === "contracts")?.items ?? [];
    const k01 = found.find((item) => item.primary === "SF-ORD-10001");
    expect(k01, "the search for SF-ORD answers the contract SF-ORD-10001").toBeDefined();

    await page.goto("/search?q=SF-ORD");
    await expect(
      page.getByRole("heading", { level: 1, name: 'Search results for "SF-ORD"' }),
    ).toBeVisible();
    const contracts = page.getByRole("table", { name: "Contracts", exact: true });
    await expect(
      contracts.getByRole("link", { name: "SF-ORD-10001", exact: true }),
    ).toHaveAttribute("href", `/contracts/${k01?.id ?? ""}/obligations`);
    for (const group of answer.results) {
      const caption = SEARCH_CAPTIONS[group.scope] ?? group.scope;
      const table = page.getByRole("table", { name: caption, exact: true });
      const first = group.items[0];
      if (first === undefined) {
        await expect(table).toHaveCount(0);
        continue;
      }
      await expect(table.getByRole("rowheader")).toHaveCount(group.items.length);
      await expect(table.getByRole("row").nth(1)).toContainText(first.primary);
      await expect(table.getByRole("row").nth(1)).toContainText(first.secondary);
      // "Show more <scope>" stands under a table whose scope holds a further page (the paging itself
      // is held by `routes/search/results.test.tsx`; item CTR-28, ruling P6).
      await expect(
        page.getByRole("button", { name: `Show more ${caption.toLowerCase()}`, exact: true }),
      ).toHaveCount(group.next_cursor === null ? 0 : 1);
    }
    // SCREENS §1.3: the page uses no dimension of the accounting context.
    const pill = page.getByRole("group", { name: "Accounting context" });
    await expect(pill.getByRole("button", { name: /^Entity: / })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    // An obligation's route needs its contract: the rows shown have read theirs.
    await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
    await expectUnclipped(page.getByTestId("SF-24-results-page").locator("th, td"));
    await screens.capture(page, "sf-24-results", { surface: "SF-24:results" });
    await a11y.check(page, "SF-24:results");

    // The chip "Scope": the read sends `scope`, and the page shows that scope's table alone.
    const filters = page.getByTestId("SF-24-filters").getByRole("toolbar", { name: "Filters" });
    await filters.getByRole("button", { name: "Filter", exact: true }).click();
    await page
      .getByRole("dialog", { name: "Filter" })
      .getByRole("button", { name: "Scope" })
      .click();
    const editor = page.getByRole("dialog", { name: "Scope filter" });
    await editor.getByRole("checkbox", { name: "Contracts" }).check();
    const scoped = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname === "/api/v1/search" && url.searchParams.get("scope") === "contracts";
    });
    await editor.getByRole("button", { name: "Apply" }).click();
    expect((await scoped).status()).toBe(200);
    await expect(
      filters.getByRole("button", { name: "Scope is Contracts, edit filter" }),
    ).toBeVisible();
    await expect(page).toHaveURL(/[?&]f\.scope=is(:|%3A)contracts(&|$)/);
    await expect(page.getByRole("table")).toHaveCount(1);
    await expect(contracts.getByRole("rowheader")).toHaveCount(found.length);

    // SF-24 (DESIGN_SYSTEM DS-CMP-04): the palette finds the records of the same text, a group a
    // scope ahead of the pages and commands, and "Show all results" opens this page for the text.
    await page.getByRole("button", { name: "Search or run a command" }).click();
    const palette = page.getByRole("dialog", { name: "Command palette" });
    await expect(
      palette.getByRole("radiogroup", { name: "Search scope" }).getByRole("radio"),
    ).toHaveCount(8);
    await palette.getByRole("combobox").fill("SF-ORD");
    await expect(palette.getByRole("option", { name: /^SF-ORD-10001, / })).toBeVisible();
    await expect(palette.getByTestId("SF-24-searching")).toHaveCount(0);
    const all = palette.getByRole("option", { name: "Show all results", exact: true });
    await expect(all).toBeVisible();
    await screens.capture(page, "sf-24-palette", { surface: "SF-24" });
    await a11y.check(page, "SF-24");
    await all.click();
    await expect(palette).toHaveCount(0);
    await expect(page).toHaveURL(/\/search\?q=SF-ORD$/);
    await expect(page.getByRole("table", { name: "Contracts", exact: true })).toBeVisible();
  });
});

test.describe("SF-15:chart-of-accounts Chart of accounts (RT-78 /settings/chart-of-accounts), persona tomas", () => {
  test("SF-15:chart-of-accounts tomas", async ({ personas, screens, a11y }) => {
    const page = await personas.page("tomas");
    await page.goto("/settings/chart-of-accounts");
    await expect(page.getByRole("heading", { level: 1, name: "Chart of accounts" })).toBeVisible();
    const accounts = page.getByTestId("SF-15-grid-accounts");
    await expect(accounts.getByRole("grid", { name: "Accounts" })).toBeVisible();
    await expect(
      page.getByTestId("SF-15-row-2090").getByRole("rowheader", { name: "2090" }),
    ).toBeVisible();
    const dimensions = page.getByTestId("SF-15-grid-dimensions");
    await expect(
      dimensions.getByRole("grid", { name: "Dimensions" }).getByRole("rowheader"),
    ).toHaveCount(5);
    await expect(page.getByRole("group", { name: "Accounting context" })).toBeVisible();
    await screens.capture(page, "sf-15-chart-of-accounts", { surface: "SF-15:chart-of-accounts" });
    await a11y.check(page, "SF-15:chart-of-accounts");
  });
});

test.describe("SF-15:workspace Workspace settings (RT-110 /settings/workspace), persona tomas", () => {
  test("SF-15:workspace tomas", async ({ personas, screens, a11y }) => {
    const page = await personas.page("tomas");
    await page.goto("/settings/workspace");
    await expect(page.getByRole("heading", { level: 1, name: "Workspace settings" })).toBeVisible();
    const style = page.getByRole("radiogroup", { name: "Negative amounts" });
    await expect(style).toHaveAttribute("data-testid", "SF-15-workspace-negative-style");
    await expect(style.getByRole("radio", { name: "Parentheses, (4,000.00)" })).toBeChecked();
    await expect(page.getByRole("group", { name: "Accounting context" })).toBeVisible();
    await screens.capture(page, "sf-15-workspace", { surface: "SF-15:workspace" });
    await a11y.check(page, "SF-15:workspace");
  });
});

test.describe("SF-15:sandbox Sandbox copies (RT-84 /settings/sandbox), persona marcus", () => {
  // BUILD_SPEC SNP-5 (fragment 14 rev 1.25): what the demo world reaches. It holds no confirmed
  // snapshot retention policy, so no sandbox copy of WLD-T-01 can be created through the API on the
  // day of a run — the step "REQ-PLT-003 sandbox banner on every screen" and the listing of that
  // copy here are owed to item DEMO-RETENTION-CONFIRMED-1.
  test("SF-15:sandbox as marcus", async ({ personas, screens, a11y }) => {
    const page = await personas.page("marcus");
    await page.goto("/settings/sandbox");
    await expect(page.getByRole("heading", { level: 1, name: "Sandbox copies" })).toBeVisible();
    await expect(
      page.getByText(
        "A sandbox copy is a separate workspace. Nothing in a sandbox posts or exports, and production is never overwritten.",
      ),
    ).toBeVisible();
    const empty = page.getByTestId("SF-15-empty-sandboxes");
    await expect(empty.getByText("No sandbox copies")).toBeVisible();
    await expect(
      empty.getByText(
        "Copy this workspace to rehearse a close, test a policy change or train users without touching production.",
      ),
    ).toBeVisible();
    await expect(empty.getByRole("button", { name: "Create sandbox copy" })).toBeVisible();
    await expect(page.getByRole("table", { name: "Sandboxes" })).toHaveCount(0);
    // J-25.4: production renders no reset control at all.
    await expect(page.getByRole("button", { name: "Reset sandbox" })).toHaveCount(0);
    await screens.capture(page, "sf-15-sandbox", { surface: "SF-15:sandbox" });
    await a11y.check(page, "SF-15:sandbox");
  });
});

/** BS3-D-08 (DG-E2E-12): the fresh tenant of the SF-15:setup capture. */
const SETUP_CAPTURE = {
  code: "setup-capture",
  name: "Setup capture (Demo)",
  reportingCurrency: "USD",
  demo: true,
  admin: "tomas@demo.erev",
} as const;

/**
 * `tomas` accepts the invitation of `setup-capture` from the fake outbox, verifies his factor and
 * creates one entity with one open period through the API; the request context holds that session.
 */
async function setupCaptureSession(): Promise<APIRequestContext> {
  // The fake outbox keeps earlier runs' messages (.run/mail), so the invitation is the newer one.
  const earlier = findMail({ tenant: SETUP_CAPTURE.code, to: SETUP_CAPTURE.admin })?.file;
  await createTenant(SETUP_CAPTURE);
  // The CLI queues the invitation in the outbox, which the worker's `outbox_sweeper` relays once a
  // minute (`cron="* * * * *"`), so the wait covers one full sweep period (L4-5-Q-50).
  const mail = await waitForMail(
    {
      tenant: SETUP_CAPTURE.code,
      to: SETUP_CAPTURE.admin,
      ...(earlier === undefined ? {} : { after: earlier }),
    },
    90_000,
  );
  const link = new URL(linkIn(mail, "/accept-invitation"));
  const token = new URLSearchParams(link.hash.slice(1)).get("token");
  if (token === null) {
    throw new Error(`the invitation link of ${mail.file} carries no token`);
  }
  const context = await newApiContext();
  await json(
    await context.post("/api/v1/session/accept-invitation", {
      data: { token, password: demoPassword() },
    }),
  );
  const client = new ApiClient(context);
  const { code } = await nextCode(SETUP_CAPTURE.admin);
  await json(await client.command("POST", "/api/v1/session/mfa", { code }));
  const calendar = await json<{ readonly id: string }>(
    await client.command("POST", "/api/v1/calendars", {
      code: "SETUP-CAL",
      name: "Setup capture calendar",
    }),
    201,
  );
  await json(
    await client.command("POST", `/api/v1/calendars/${calendar.id}/generate-year`, {
      fiscal_year: 2026,
    }),
  );
  await json(
    await client.command("POST", "/api/v1/entities", {
      code: "SETUP-US",
      name: "Setup Capture Inc.",
      functional_currency: "USD",
      time_zone: "America/New_York",
      calendar_id: calendar.id,
    }),
    201,
  );
  const periods = await json<{
    readonly items: readonly { readonly id: string; readonly row_version: number }[];
  }>(await client.get("/api/v1/periods", { entity: "SETUP-US", limit: 1 }));
  const first = periods.items[0];
  if (first === undefined) {
    throw new Error("SETUP-US has no period to open");
  }
  await json(
    await context.fetch(`/api/v1/periods/${first.id}/open`, {
      method: "POST",
      headers: {
        "X-CSRF-Token": await client.csrfToken(),
        "Idempotency-Key": randomUUID(),
        Origin: webOrigin(),
        "If-Match": `"r${String(first.row_version)}"`,
      },
      data: {},
    }),
  );
  return context;
}

test.describe("SF-15:setup Workspace setup (RT-74 /settings/setup), persona tomas", () => {
  let storageState: Awaited<ReturnType<APIRequestContext["storageState"]>> | null = null;

  test.beforeAll(async () => {
    const context = await setupCaptureSession();
    storageState = await context.storageState();
    await context.dispose();
  });

  test("SF-15:setup tomas", async ({ browser, screens, a11y }, testInfo) => {
    if (storageState === null) {
      throw new Error("the setup-capture session was not created");
    }
    const context = await browser.newContext({
      baseURL: webOrigin(),
      locale: "en-US",
      timezoneId: "UTC",
      viewport: { width: 1440, height: 900 },
      storageState,
    });
    const record = await installNetworkGuard(context);
    const page = await context.newPage();

    // SCREENS_B §11.1: a settings.manage holder lands on setup while setup_completed_at is null.
    await page.goto("/");
    await expect(page).toHaveURL(/\/settings\/setup$/);
    await expect(page.getByRole("heading", { level: 1, name: "Workspace setup" })).toBeVisible();
    const checklist = page.getByRole("table", { name: "Setup checklist" });
    await expect(checklist).toHaveAttribute("data-testid", "SF-15-grid-setup");
    await expect(page.getByTestId("SF-15-row-setup-1")).toContainText("Passed");
    await expect(page.getByTestId("SF-15-row-setup-2")).toContainText("Passed");
    await expect(page.getByTestId("SF-15-row-setup-3")).toContainText("Not started");
    await expect(page.getByRole("group", { name: "Accounting context" })).toBeVisible();
    await screens.capture(page, "sf-15-setup", { surface: "SF-15:setup" });
    await a11y.check(page, "SF-15:setup");

    await context.close();
    appendProjectRecord(testInfo, record);
    expect(record).toEqual({ requests: [], cspViolations: [] });
  });
});

test.describe("SF-23 Context pill (placement, /settings/workspace), persona tomas", () => {
  test("SF-23 tomas", async ({ personas, screens, a11y }) => {
    const page = await personas.page("tomas");
    await page.goto("/settings/workspace");
    await expect(page.getByRole("heading", { level: 1, name: "Workspace settings" })).toBeVisible();
    const listed = await json<{
      readonly items: readonly { readonly code: string; readonly name: string }[];
    }>(await page.request.get("/api/v1/entities", { params: { is_active: true, limit: 200 } }));
    const group = page.getByRole("group", { name: "Accounting context" });
    const entity = group.getByRole("button", { name: /^Entity: / });
    const name = (await entity.getAttribute("aria-label")) ?? "";
    await entity.click();
    const listbox = page.getByRole("listbox", { name });
    await expect(listbox).toBeVisible();
    await expect(listbox.getByRole("option")).toHaveText(
      listed.items.map((item) => `${item.code} · ${item.name}`),
    );
    await expect(listbox.getByRole("option", { selected: true })).toHaveText(
      name.replace(/^Entity: /, ""),
    );
    await screens.capture(page, "sf-23", { surface: "SF-23" });
    await a11y.check(page, "SF-23");
  });
});

interface ListedRuleSet {
  readonly id: string;
  readonly code: string;
  readonly current_version: { readonly id: string; readonly version_no: number } | null;
}

/** SCREENS_B §15: the rule set and its current version resolved by code through the API. */
async function currentRuleSetVersion(page: Page, code: string): Promise<ListedRuleSet> {
  const listed = await json<{ readonly items: readonly ListedRuleSet[] }>(
    await page.request.get("/api/v1/rule-sets", { params: { q: code, limit: 50 } }),
  );
  const set = listed.items.find((item) => item.code === code);
  if (set?.current_version === null || set === undefined) {
    throw new Error(`rule set ${code} has no published version visible to this persona`);
  }
  return set;
}

test.describe("SF-13:revenue Revenue policies (RT-59 /policies/revenue), persona maya", () => {
  test("SF-13:revenue maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    // SCREENS SCR-IA-01: the Policies destination redirects to its first tab.
    await page.goto("/policies");
    await expect(page).toHaveURL(/\/policies\/revenue$/);
    await expect(page.getByRole("heading", { level: 1, name: "Policies" })).toBeVisible();
    await expect(
      page.getByRole("navigation", { name: "Policies sections" }).getByRole("link", {
        name: "Revenue policies",
      }),
    ).toHaveAttribute("aria-current", "page");
    const templates = page.getByTestId("SF-13-grid-templates");
    await expect(templates.getByRole("grid", { name: "Obligation templates" })).toBeVisible();
    await expect(
      page
        .getByTestId("SF-13-row-template-tpl-sub-daily")
        .getByRole("rowheader", { name: "TPL-SUB-DAILY" }),
    ).toBeVisible();
    const ruleSets = page.getByTestId("SF-13-grid-rule-sets");
    await expect(ruleSets.getByRole("grid", { name: "Assignment rules" })).toBeVisible();
    await expect(page.getByRole("group", { name: "Accounting context" })).toBeVisible();
    await screens.capture(page, "sf-13-revenue", { surface: "SF-13:revenue" });
    await a11y.check(page, "SF-13:revenue");
  });
});

test.describe("SF-13:control-rules Control rules (RT-60 /policies/control-rules), persona maya", () => {
  test("SF-13:control-rules maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    await page.goto("/policies/control-rules");
    await expect(page.getByRole("heading", { level: 1, name: "Policies" })).toBeVisible();
    const grid = page.getByTestId("SF-13-grid-control-rules");
    await expect(grid.getByRole("grid", { name: "Control rules" })).toBeVisible();
    // PRD §2.5: APPROVAL_ROUTING version 1 and AUTO_APPROVAL version 1, both published.
    for (const code of ["APPROVAL_ROUTING", "AUTO_APPROVAL"]) {
      const row = page.getByTestId(`SF-13-row-${code.toLowerCase().replace(/_/g, "-")}`);
      await expect(row.getByRole("rowheader", { name: code })).toBeVisible();
      await expect(row.getByText("v1", { exact: true })).toBeVisible();
      await expect(row.getByText("Published", { exact: true })).toBeVisible();
    }
    await expect(grid.getByRole("toolbar", { name: "Filters" })).toBeVisible();
    await screens.capture(page, "sf-13-control-rules", { surface: "SF-13:control-rules" });
    await a11y.check(page, "SF-13:control-rules");
  });
});

test.describe("SF-13:rule-set-version Rule set version (RT-62 /policies/rule-sets/:ruleSetId/versions/:versionId), persona maya", () => {
  test("SF-13:rule-set-version maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    const routing = await currentRuleSetVersion(page, "APPROVAL_ROUTING");
    expect(routing.current_version?.version_no).toBe(1);
    await page.goto(
      `/policies/rule-sets/${routing.id}/versions/${routing.current_version?.id ?? ""}`,
    );
    await expect(page.getByRole("heading", { level: 1, name: "Approval routing" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Version lifecycle" })).toBeVisible();
    const grid = page.getByTestId("SF-13-grid-rules").getByRole("grid", { name: "Rules" });
    const activation = grid
      .getByRole("row")
      .filter({ hasText: "Subject is CONTRACT_ACTIVATION" })
      .first();
    await expect(activation).toBeVisible();
    const key = ((await activation.getByRole("rowheader").textContent()) ?? "").trim();
    expect(key).not.toBe("");
    await screens.capture(page, "sf-13-rule-set-version", { surface: "SF-13:rule-set-version" });
    await a11y.check(page, "SF-13:rule-set-version");

    await test.step("drawer Rule <key> opens read-only on the published version", async () => {
      await activation.getByRole("link", { name: key }).click();
      const drawer = page.getByRole("dialog", { name: `Rule ${key}` });
      await expect(drawer.getByTestId("SF-13-drawer-rule")).toBeVisible();
      await expect(drawer.getByText("CONTRACT_ACTIVATION", { exact: true })).toBeVisible();
      await expect(drawer.getByRole("button", { name: "Save rule" })).toHaveCount(0);
      await a11y.check(page, "SF-13:rule-set-version", { state: "drawer-rule" });
    });
  });
});

/** DS-FMT-16 as the Policies screens show the UTC date of an effective instant (SCREENS §11.0). */
const EFFECTIVE_DATE = /^\d{2} [A-Z][a-z]{2} \d{4}$/;

interface ListedTemplate {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly current_version: { readonly id: string; readonly version_no: number } | null;
  readonly latest_version: {
    readonly id: string;
    readonly version_no: number;
    readonly status: string;
  } | null;
}

interface ReadTemplateVersion {
  readonly id: string;
  readonly version_no: number;
  readonly status: string;
  readonly effective_from: string | null;
  readonly supersedes_version_id: string | null;
  readonly pending_approval_request_id: string | null;
}

/** PRD §5.5 ERR-75, the date form: the server's sentence for a version that replaces a published one. */
const ERR_75_DATE =
  "This version replaces a published one. Choose an effective date later than today.";

test.describe("SF-13:template-version Obligation template version (RT-61 /policies/templates/:templateId/versions/:versionId), persona maya", () => {
  test("SF-13:template-version maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    const listed = await json<{ readonly items: readonly ListedTemplate[] }>(
      await page.request.get("/api/v1/pob-templates", { params: { sort: "code", limit: 200 } }),
    );
    const template = listed.items.find((item) => item.code === "TPL-SUB-DAILY");
    const current = template?.current_version ?? null;
    if (template === undefined || current === null) {
      throw new Error("template TPL-SUB-DAILY has no published version visible to this persona");
    }
    await page.goto(`/policies/templates/${template.id}/versions/${current.id}`);
    await expect(page.getByRole("heading", { level: 1, name: template.name })).toBeVisible();
    await expect(page.getByTestId("SF-13-identifier")).toContainText("TPL-SUB-DAILY");
    await expect(page.getByRole("navigation", { name: "Version lifecycle" })).toBeVisible();
    await expect(page.getByRole("form", { name: "Template outputs" })).toBeVisible();
    // A published version is read-only.
    await expect(page.getByRole("button", { name: "Save outputs" })).toHaveCount(0);
    // The top bar is complete before the capture (the context pill loads after the page).
    await expect(page.getByRole("group", { name: "Accounting context" })).toBeVisible();
    await screens.capture(page, "sf-13-template-version", { surface: "SF-13:template-version" });
    await a11y.check(page, "SF-13:template-version");
  });

  // Item TPL-EFFECTIVE-FROM-UI-1 (SCREENS §11.0 "Effective date" and "Refused command", §11.2 Meta,
  // rev 1.31; PRD ERR-75; 04 §16.5): a version that replaces the published one of its template needs
  // an effective date later than today in every active entity. The row takes `TPL-OPTION`, which no
  // other row opens, through the screen as its author: a draft of the published version, today's date
  // refused at the field, a later date, the tests the changed date asks for, the submission, and the
  // withdrawal. It leaves the withdrawn version and its withdrawn request; nothing stays pending.
  test("SF-13:template-version maya submits a version that replaces the published one and withdraws it", async ({
    personas,
    screens,
    a11y,
  }) => {
    const page = await personas.page("maya");
    const api = new ApiClient(page.request);
    const listed = await json<{ readonly items: readonly ListedTemplate[] }>(
      await page.request.get("/api/v1/pob-templates", { params: { sort: "code", limit: 200 } }),
    );
    const template = listed.items.find((item) => item.code === "TPL-OPTION");
    const current = template?.current_version ?? null;
    if (template === undefined || current === null) {
      throw new Error("template TPL-OPTION has no published version visible to this persona");
    }
    const readVersion = async (versionId: string) =>
      json<ReadTemplateVersion>(
        await page.request.get(`/api/v1/pob-template-versions/${versionId}`),
      );
    const versionIdOf = (url: string) => /\/versions\/([0-9a-f-]{36})/.exec(url)?.[1] ?? "";
    const details = page.getByRole("region", { name: "Version details" });
    const field = details.getByRole("textbox", { name: /^Effective from/ });
    const saveDate = details.getByRole("button", { name: "Save effective date" });
    const commandAnswered = (suffix: string, method = "POST") =>
      page.waitForResponse(
        (response) =>
          response.request().method() === method &&
          new URL(response.url()).pathname.endsWith(suffix),
      );
    /**
     * Picks a date in the calendar of the field, which opens on today's UTC date while the field is
     * empty and on the field's date otherwise: that day, or the day `ahead` days after it.
     */
    const pickDate = async (ahead: number) => {
      await details.getByRole("button", { name: "Choose date" }).click();
      const calendar = details.getByRole("dialog");
      const day = calendar.locator("button:focus");
      await expect(day).toHaveAttribute("aria-label", EFFECTIVE_DATE);
      for (let moved = 0; moved < ahead; moved += 1) {
        const before = (await day.getAttribute("aria-label")) ?? "";
        await page.keyboard.press("ArrowRight");
        await expect(day).not.toHaveAttribute("aria-label", before);
      }
      await page.keyboard.press("Enter");
      await expect(calendar).toHaveCount(0);
    };
    /** Saves the date the field holds and waits until the stepper shows it as the effective date. */
    const saveEffective = async () => {
      const shown = await field.inputValue();
      expect(shown).toMatch(EFFECTIVE_DATE);
      await saveDate.click();
      await expect(page.getByText(`Effective ${shown}`, { exact: true })).toBeVisible();
    };

    // An earlier run that stopped before its submission left its draft open: the row takes it up,
    // since a template holds one open version at a time.
    const open = template.latest_version;
    if (open !== null && (open.status === "DRAFT" || open.status === "TESTED")) {
      await page.goto(`/policies/templates/${template.id}/versions/${open.id}`);
    } else {
      await page.goto(`/policies/templates/${template.id}/versions/${current.id}`);
      // The published version shows its date as a definition, not as a field.
      await expect(details.getByRole("form")).toHaveCount(0);
      await expect(details.getByText("Effective from", { exact: true })).toBeVisible();
      await page.getByRole("button", { name: "New draft version" }).click();
    }
    await expect(page).not.toHaveURL(new RegExp(`/versions/${current.id}`));
    await expect(page.getByRole("form", { name: "Template outputs" })).toBeVisible();
    const draftId = versionIdOf(page.url());
    expect(draftId).not.toBe("");
    expect((await readVersion(draftId)).supersedes_version_id).toBe(current.id);

    try {
      // SCREENS §11.2 Meta (rev 1.31): the date is required, because the draft replaces version 1.
      await expect(field).toHaveAttribute("aria-required", "true");
      await expect(
        details.getByText(
          "Contracts dated on or after this date use this version. It replaces a published one, so choose a date later than today; the approval must come before that date.",
        ),
      ).toBeVisible();
      // The capture shows the Meta, not the toast of the draft's creation, under a complete top bar.
      await dismissToasts(page);
      await expect(page.getByRole("group", { name: "Accounting context" })).toBeVisible();
      await screens.capture(page, "sf-13-template-version-draft", {
        surface: "SF-13:template-version",
      });
      await a11y.check(page, "SF-13:template-version", { state: "draft" });

      await test.step("today's date is refused at the field with the server's sentence (PRD ERR-75)", async () => {
        // The field of an earlier run's draft may hold a date: the calendar then opens on today.
        await field.fill("");
        await field.blur();
        await pickDate(0);
        await saveEffective();
        const tested = commandAnswered("/test");
        await page.getByRole("button", { name: "Run tests" }).click();
        expect((await tested).status()).toBe(200);
        expect((await readVersion(draftId)).status).toBe("TESTED");
        await page.getByRole("button", { name: "Submit for approval" }).click();
        await expect(details.getByText(ERR_75_DATE)).toBeVisible();
        // The sentence stands once, at the field it is about, and the field has the focus.
        await expect(page.getByText(ERR_75_DATE)).toHaveCount(1);
        await expect(field).toBeFocused();
        await expect(field).toHaveAttribute("aria-invalid", "true");
        await expect(
          page.getByRole("heading", { name: "Check the highlighted fields" }),
        ).toBeVisible();
        expect((await readVersion(draftId)).pending_approval_request_id).toBeNull();
      });

      await test.step("a later date is new content: the banner asks for the tests, which clear it", async () => {
        // Two days after today's UTC date is later than today in every time zone, Asia/Tokyo of
        // AVM-JP included.
        await pickDate(2);
        // The sentence was about the date that was sent: it leaves with the edit, and the banner with it.
        await expect(page.getByText(ERR_75_DATE)).toHaveCount(0);
        await expect(
          page.getByRole("heading", { name: "Check the highlighted fields" }),
        ).toHaveCount(0);
        await saveEffective();
        await page.getByRole("button", { name: "Submit for approval" }).click();
        const banner = page
          .getByRole("alert")
          .filter({ hasText: "Action not available in this state" });
        await expect(banner).toContainText(
          "This version changed after its tests ran. Run the tests again.",
        );
        const tested = commandAnswered("/test");
        await page.getByRole("button", { name: "Run tests" }).click();
        expect((await tested).status()).toBe(200);
        await expect(banner).toHaveCount(0);
      });

      await test.step("the submission waits for approval, and its author withdraws it", async () => {
        const submitted = commandAnswered("/submit");
        await page.getByRole("button", { name: "Submit for approval" }).click();
        expect((await submitted).status()).toBe(200);
        await expect(page.getByText("Pending approval").first()).toBeVisible();
        const pending = await readVersion(draftId);
        expect(pending.status).toBe("SUBMITTED");
        expect(pending.pending_approval_request_id).not.toBeNull();
        // The date is a definition again: a submitted version does not change.
        await expect(details.getByRole("form")).toHaveCount(0);

        const withdrawn = commandAnswered("/withdraw");
        await page.getByRole("button", { name: "Withdraw", exact: true }).click();
        expect((await withdrawn).status()).toBe(200);
        await expect(page.getByText("Withdrawn").first()).toBeVisible();
        const left = await readVersion(draftId);
        expect(left.status).toBe("WITHDRAWN");
        expect(left.pending_approval_request_id).toBeNull();
      });
    } finally {
      // A request this row submitted never stays pending, whatever failed before its withdrawal.
      const left = await readVersion(draftId);
      if (left.status === "SUBMITTED" && left.pending_approval_request_id !== null) {
        await json(
          await api.command(
            "POST",
            `/api/v1/approvals/${left.pending_approval_request_id}/withdraw`,
            { comment: "Screen audit row: withdrawn after a failed step." },
          ),
        );
      }
    }
  });
});

interface ListedPolicy {
  readonly id: string;
  readonly version_no: number;
  readonly effective_from: string | null;
}

test.describe("SF-13:accounting Accounting policies (RT-63 /policies/accounting, RT-64 /policies/accounting/:policyId), persona marcus", () => {
  test("SF-13:accounting marcus", async ({ personas, screens, a11y }) => {
    const page = await personas.page("marcus");
    await page.goto("/policies/accounting");
    await expect(page.getByRole("heading", { level: 1, name: "Policies" })).toBeVisible();
    await expect(
      page.getByRole("navigation", { name: "Policies sections" }).getByRole("link", {
        name: "Accounting policies",
      }),
    ).toHaveAttribute("aria-current", "page");
    const grid = page
      .getByTestId("SF-13-grid-policy-versions")
      .getByRole("grid", { name: "Policy versions" });
    await expect(grid).toBeVisible();
    // 04 SC-V: a published version carries an effective instant, shown as its UTC date.
    const published = grid.getByRole("row").filter({ hasText: "Published" }).first();
    await expect(published).toBeVisible();
    await expect(published.locator('[data-column="effective_from"]')).toHaveText(EFFECTIVE_DATE);
    // Marcus approves and does not author (SoD-5).
    await expect(page.getByRole("button", { name: "New policy version" })).toHaveCount(0);
    await screens.capture(page, "sf-13-accounting", { surface: "SF-13:accounting" });
    await a11y.check(page, "SF-13:accounting");
  });

  test("SF-13:accounting-version marcus", async ({ personas, screens, a11y }) => {
    const page = await personas.page("marcus");
    const listed = await json<{ readonly items: readonly ListedPolicy[] }>(
      await page.request.get("/api/v1/policies", {
        params: { category: "ACCOUNTING_POLICY", scope: "TENANT", status: "PUBLISHED", limit: 1 },
      }),
    );
    const [policy] = listed.items;
    if (policy === undefined) {
      throw new Error("no published TENANT accounting policy version is visible to this persona");
    }
    expect(policy.effective_from).not.toBeNull();
    await page.goto(`/policies/accounting/${policy.id}`);
    await expect(
      page.getByRole("heading", { level: 1, name: "Accounting policies · Tenant" }),
    ).toBeVisible();
    await expect(page.getByText(`v${String(policy.version_no)}`, { exact: true })).toBeVisible();
    const lifecycle = page.getByRole("navigation", { name: "Version lifecycle" });
    await expect(lifecycle.getByText(/^Effective \d{2} [A-Z][a-z]{2} \d{4}$/)).toBeVisible();
    await expect(page.getByLabel("Effective from")).toHaveText(EFFECTIVE_DATE);
    const parameters = page.getByTestId("SF-13-grid-parameters");
    await expect(parameters.getByRole("grid", { name: "Policy parameters" })).toBeVisible();
    // SCREENS §11.3 rev 1.56: the grid keeps a floor of eight rows, the page scrolling below it.
    // At this viewport (1440 x 900) the blocks above it left a draft three rows and a published
    // version one; vitest has no layout, so the floor is held here.
    await expect
      .poll(() =>
        parameters.evaluate((element) => {
          const scroller = element.querySelector('[role="grid"]');
          const header = element.querySelector('[role="columnheader"]');
          if (scroller === null || header === null) {
            return 0;
          }
          const top = header.getBoundingClientRect().bottom;
          const bottom = scroller.getBoundingClientRect().bottom;
          return [...element.querySelectorAll('[role="row"][data-testid^="SF-13-row-"]')].filter(
            (row) => {
              const box = row.getBoundingClientRect();
              return box.top >= top - 1 && box.bottom <= bottom + 1;
            },
          ).length;
        }),
      )
      .toBeGreaterThanOrEqual(8);
    await screens.capture(page, "sf-13-accounting-version", {
      surface: "SF-13:accounting-version",
    });
    await a11y.check(page, "SF-13:accounting-version");
  });
});

interface ListedMapping {
  readonly id: string;
  readonly name: string;
  readonly version_no: number;
}

/** SCREENS §0.12: the published account mapping version, resolved through the API. */
async function publishedMapping(request: APIRequestContext): Promise<ListedMapping> {
  const listed = await json<{ readonly items: readonly ListedMapping[] }>(
    await request.get("/api/v1/account-mappings", {
      params: { status: "PUBLISHED", sort: "-version_no", limit: 1 },
    }),
  );
  const [mapping] = listed.items;
  if (mapping === undefined) {
    throw new Error("no published account mapping version is visible to this persona");
  }
  return mapping;
}

test.describe("SF-13:account-mapping Account mapping (RT-69 /policies/account-mapping, RT-70 /policies/account-mapping/:mappingVersionId), persona marcus", () => {
  test("SF-13:account-mapping marcus", async ({ personas, screens, a11y }) => {
    const page = await personas.page("marcus");
    const mapping = await publishedMapping(page.request);
    await page.goto("/policies/account-mapping");
    await expect(page.getByRole("heading", { level: 1, name: "Policies" })).toBeVisible();
    const grid = page
      .getByTestId("SF-13-grid-account-mappings")
      .getByRole("grid", { name: "Account mappings" });
    await expect(grid).toBeVisible();
    const row = grid.getByRole("row").filter({ hasText: "Published" }).first();
    await expect(row.getByRole("link", { name: mapping.name })).toHaveAttribute(
      "href",
      `/policies/account-mapping/${mapping.id}`,
    );
    await expect(row.locator('[data-column="effective_from"]')).toHaveText(EFFECTIVE_DATE);
    await screens.capture(page, "sf-13-account-mapping", { surface: "SF-13:account-mapping" });
    await a11y.check(page, "SF-13:account-mapping");
  });

  test("SF-13:account-mapping-version marcus", async ({ personas, screens, a11y }) => {
    const page = await personas.page("marcus");
    const mapping = await publishedMapping(page.request);
    await page.goto(`/policies/account-mapping/${mapping.id}`);
    await expect(page.getByRole("heading", { level: 1, name: mapping.name })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Version lifecycle" })).toBeVisible();
    // The header chip and the "Published" step caption (SCREENS §11.0 "Effective <date>").
    await expect(page.getByText(/^Effective \d{2} [A-Z][a-z]{2} \d{4}$/)).toHaveCount(2);
    await expect(
      page.getByTestId("SF-13-grid-mapping-rules").getByRole("grid", { name: "Mapping rules" }),
    ).toBeVisible();
    await screens.capture(page, "sf-13-account-mapping-version", {
      surface: "SF-13:account-mapping-version",
    });
    await a11y.check(page, "SF-13:account-mapping-version");
  });
});

test.describe("SF-13:ssp-books SSP books (RT-65 /policies/ssp-books), persona maya", () => {
  test("SF-13:ssp-books maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    await page.goto("/policies/ssp-books");
    await expect(page.getByRole("heading", { level: 1, name: "Policies" })).toBeVisible();
    await expect(
      page.getByRole("navigation", { name: "Policies sections" }).getByRole("link", {
        name: "SSP books",
      }),
    ).toHaveAttribute("aria-current", "page");
    const grid = page.getByTestId("SF-13-grid-ssp-books");
    await expect(grid.getByRole("grid", { name: "SSP books" })).toBeVisible();
    // PRD §2.6: US-LIST 2026-H1, approved, is the current version.
    const row = page.getByTestId("SF-13-row-us-list");
    await expect(row.getByRole("rowheader", { name: "US-LIST" })).toBeVisible();
    await expect(row.getByText("2026-H1 · v1", { exact: true })).toBeVisible();
    await screens.capture(page, "sf-13-ssp-books", { surface: "SF-13:ssp-books" });
    await a11y.check(page, "SF-13:ssp-books");
  });
});

test.describe("SF-13:ssp-book-version SSP book version (RT-66 /policies/ssp-books/:bookId/versions/:versionId), persona maya", () => {
  test("SF-13:ssp-book-version maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    const book = await sspBookByCode(page.request, "US-LIST");
    const current = book.current_version;
    expect(current?.legacy_version_label).toBe("2026-H1");
    // RT-66: the book path redirects to the current approved version.
    await page.goto(`/policies/ssp-books/${book.id}`);
    await expect(page).toHaveURL(
      new RegExp(`/policies/ssp-books/${book.id}/versions/${current?.id ?? "none"}$`),
    );
    await expect(page.getByRole("heading", { level: 1, name: "US list prices" })).toBeVisible();
    await expect(page.getByRole("button", { name: /^Version / })).toContainText(
      "Version 2026-H1 (Approved)",
    );
    const grid = page.getByTestId("SF-13-grid-ssp-entries");
    await expect(grid.getByRole("grid", { name: "SSP entries" })).toBeVisible();
    const row = grid.getByTestId("SF-13-row-avm-plat-100");
    await expect(row.getByRole("rowheader", { name: "AVM-PLAT-100" })).toBeVisible();
    for (const figure of ["85,000.00", "100,000.00", "115,000.00"]) {
      await expect(row.getByText(figure, { exact: true })).toBeVisible();
    }
    await screens.capture(page, "sf-13-ssp-book-version", { surface: "SF-13:ssp-book-version" });
    await a11y.check(page, "SF-13:ssp-book-version");
  });
});

/** The options of a persona's browser context outside the `personas` fixture. */
function personaContextOptions() {
  return {
    baseURL: webOrigin(),
    locale: "en-US",
    timezoneId: "UTC",
    viewport: { width: 1440, height: 900 },
  };
}

/** A browser context signed in as `persona` (DG-E2E-05), reusing the cached storage state. */
async function personaContext(browser: Browser, persona: Persona): Promise<BrowserContext> {
  const options = personaContextOptions();
  if (hasStorageState(persona)) {
    const cached = await browser.newContext({
      ...options,
      storageState: storageStatePath(persona),
    });
    const session = await sessionOf(cached.request);
    if (
      session.authenticated &&
      session.user?.email === personaEmail(persona) &&
      session.active_tenant !== null &&
      session.active_tenant !== undefined
    ) {
      return cached;
    }
    await cached.close();
  }
  const context = await browser.newContext(options);
  const page = await context.newPage();
  await signInThroughUi(page, persona);
  writeStorageState(persona, await context.storageState());
  await page.close();
  return context;
}

/**
 * A browser context of `persona` signed in now, for a decision a setup sends through the API. A
 * decision needs a second-factor verification at most five minutes old (BR-PLT-06), and the cached
 * sign-in of `personaContext` is as old as the run has made it: a setup that decided on it was
 * refused 403 `mfa-step-up-required` once the project reached it later than that. So the persona
 * verifies a fresh code, as the step-up dialog asks of her on the screen. The session is this
 * context's own — the cached one stays with the rows that hold it — and the guard records the
 * sign-in's requests too.
 */
async function freshSignIn(
  browser: Browser,
  persona: Persona,
): Promise<{ readonly context: BrowserContext; readonly record: NetworkRecord }> {
  const context = await browser.newContext(personaContextOptions());
  const record = await installNetworkGuard(context);
  const page = await context.newPage();
  await signInThroughUi(page, persona);
  await page.close();
  // The session states the verification this sign-in made, seconds ago.
  const session = await sessionOf(context.request);
  expect(session.mfa_verified_at, `second-factor verification of ${persona}`).toEqual(
    expect.any(String),
  );
  return { context, record };
}

test.describe("SF-13:ssp-calculator Historical SSP calculator (RT-67, RT-68), persona maya", () => {
  // One worker runs both rows, so beforeAll creates one run over WLD-F-18.
  test.describe.configure({ mode: "serial" });
  let runId: string | null = null;

  test.beforeAll(async ({ browser }, testInfo: TestInfo) => {
    const context = await personaContext(browser, "maya");
    const record = await installNetworkGuard(context);
    try {
      runId = await createPoolRun(context.request);
    } finally {
      await context.close();
    }
    appendProjectRecord(testInfo, record);
    expect(record).toEqual({ requests: [], cspViolations: [] });
  });

  test("SF-13:ssp-calculator maya", async ({ personas, screens, a11y }) => {
    if (runId === null) {
      throw new Error("the WLD-F-18 calculator run was not created");
    }
    const page = await personas.page("maya");
    await page.goto("/policies/ssp-calculator");
    await expect(page.getByRole("heading", { level: 1, name: "Policies" })).toBeVisible();
    await expect(
      page.getByRole("navigation", { name: "Policies sections" }).getByRole("link", {
        name: "SSP calculator",
      }),
    ).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { level: 2, name: "New run" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Run calculator" })).toBeVisible();
    const row = page.getByTestId(`SF-13-row-run-${runId}`);
    await expect(row.getByRole("link", { name: POOL_RUN_NAME })).toBeVisible();
    await expect(row.getByText("40", { exact: true })).toBeVisible();
    await expect(row.getByText("Succeeded", { exact: true })).toBeVisible();
    await screens.capture(page, "sf-13-ssp-calculator", { surface: "SF-13:ssp-calculator" });
    await a11y.check(page, "SF-13:ssp-calculator");
  });

  test("SF-13:ssp-calculator-run maya", async ({ personas, screens, a11y }) => {
    if (runId === null) {
      throw new Error("the WLD-F-18 calculator run was not created");
    }
    const page = await personas.page("maya");
    await page.goto(`/policies/ssp-calculator/runs/${runId}`);
    await expect(page.getByRole("heading", { level: 1, name: POOL_RUN_NAME })).toBeVisible();
    const strip = page.getByTestId("SF-13-kpi-strip");
    const figure = (label: string) =>
      strip.locator("dt", { hasText: label }).locator("xpath=following-sibling::dd[1]");
    // PRD WLD-X-24: 40 observations, median 112,000.00.
    await expect(figure("Observations")).toHaveText("40");
    await expect(figure("Median (USD)")).toHaveText("112,000.00");
    await expect(page.getByRole("figure", { name: /^Distribution/ })).toBeVisible();
    await expect(
      page.getByTestId("SF-13-grid-observations").getByRole("grid", { name: "Observations" }),
    ).toBeVisible();
    await screens.capture(page, "sf-13-ssp-calculator-run", {
      surface: "SF-13:ssp-calculator-run",
    });
    await a11y.check(page, "SF-13:ssp-calculator-run");
  });
});

/** SCREENS SCR-ST-20: the capture context of WLD-T-01. */
const AVM_US_CONTEXT = "entity=AVM-US&period=FY2026-P09&book=ASC606";
/** BUILD_SPEC CTR-21: the saved view of the REQ-CON-017 round trip. */
const ACTIVE_US_VIEW = "Active US";

/** The first `GET /contracts` page of the grid, which carries `X-Erev-Total-Count`. */
function contractsCount(response: APIResponseLike): boolean {
  const url = new URL(response.url());
  return (
    url.pathname === "/api/v1/contracts" &&
    response.request().method() === "GET" &&
    url.searchParams.get("count") === "true"
  );
}

interface APIResponseLike {
  url(): string;
  request(): { method(): string };
}

async function listedTotal(page: Page, action: () => Promise<unknown>): Promise<number> {
  const listed = page.waitForResponse(contractsCount);
  await action();
  const response = await listed;
  expect(response.status(), await response.text()).toBe(200);
  const header = response.headers()["x-erev-total-count"] ?? "";
  expect(header).toMatch(/^\d+$/);
  return Number(header);
}

test.describe("SF-02 Contracts (RT-08 /contracts), persona maya", () => {
  test("SF-02 maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    const total = await listedTotal(page, () => page.goto(`/contracts?${AVM_US_CONTEXT}`));
    await expect(page.getByRole("heading", { level: 1, name: "Contracts" })).toBeVisible();
    const grid = page.getByTestId("SF-02-grid-contracts").getByRole("grid", { name: "Contracts" });
    await expect(grid).toBeVisible();
    // DS-FMT-21: the page count is X-Erev-Total-Count, "<n> contracts".
    await expect(
      page
        .getByTestId("SF-02-page")
        .getByText(`${total.toLocaleString("en-US")} contracts`, { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "View: All contracts" })).toBeVisible();
    await expect(
      page.getByTestId("SF-02-filter-bar").getByRole("toolbar", { name: "Filters" }),
    ).toBeVisible();
    await screens.capture(page, "sf-02", { surface: "SF-02" });
    await a11y.check(page, "SF-02");

    // The grid is virtualised, so the viewport scrolls until the K-01 row renders.
    const k01 = page.getByTestId("SF-02-row-sf-ord-10001");
    await expect
      .poll(
        async () => {
          if ((await k01.count()) > 0) {
            return true;
          }
          await grid.evaluate((element) => {
            element.scrollTop += Math.max(element.clientHeight / 2, 100);
          });
          return false;
        },
        { timeout: 30_000, intervals: [100] },
      )
      .toBe(true);
    await expect(k01.getByRole("rowheader", { name: "SF-ORD-10001" })).toBeVisible();

    await test.step("REQ-CON-017 SF-02 quick lists, filters and a saved view round trip", async () => {
      // Earlier runs' "Active US" views of maya are removed, so the round trip names one view.
      const client = new ApiClient(page.request);
      const listed = await json<{
        readonly items: readonly {
          readonly id: string;
          readonly name: string;
          readonly is_shared: boolean;
        }[];
      }>(await client.get("/api/v1/saved-views", { screen_code: "SF-02", limit: 500 }));
      for (const view of listed.items.filter(
        (item) => item.name === ACTIVE_US_VIEW && !item.is_shared,
      )) {
        const removed = await client.command("DELETE", `/api/v1/saved-views/${view.id}`);
        expect(removed.status(), await removed.text()).toBe(204);
      }

      // The total of this step's own page load: another test of the project may book a contract
      // between two page loads, and the "All contracts" state below is served from this load's cache.
      const loaded = await listedTotal(page, () => page.goto(`/contracts?${AVM_US_CONTEXT}`));
      const selector = page.getByRole("button", { name: /^View:/ });
      await selector.click();
      await page.getByRole("menuitemradio", { name: "On hold" }).click();
      await expect(page).toHaveURL(/[?&]view=ON_HOLD(&|$)/);
      // PRD WLD-B-05: the journal export hold on BG-AVM-0021.
      await expect(
        page.getByTestId("SF-02-row-bg-avm-0021").getByRole("rowheader", { name: "BG-AVM-0021" }),
      ).toBeVisible();

      // A grid state read before is served from the query cache, so the counts come from the page
      // header "<n> contracts" (X-Erev-Total-Count of the state shown).
      const headerCount = page
        .getByTestId("SF-02-page")
        .locator("header")
        .getByText(/^[\d,]+ contracts?$/);
      const shownCount = async (): Promise<number> => {
        if ((await headerCount.count()) === 0) {
          return -1;
        }
        return Number(((await headerCount.textContent()) ?? "").replace(/[^0-9]/g, ""));
      };
      await selector.click();
      await page.getByRole("menuitemradio", { name: "All contracts" }).click();
      await expect.poll(shownCount).toBe(loaded);
      const filters = page
        .getByTestId("SF-02-filter-bar")
        .getByRole("toolbar", { name: "Filters" });
      await filters.getByRole("button", { name: "Filter", exact: true }).click();
      await page
        .getByRole("dialog", { name: "Filter" })
        .getByRole("button", { name: "Status" })
        .click();
      const statusEditor = page.getByRole("dialog", { name: "Status filter" });
      await statusEditor.getByRole("checkbox", { name: "Active" }).check();
      await statusEditor.getByRole("button", { name: "Apply" }).click();
      await expect(
        filters.getByRole("button", { name: "Status is Active, edit filter" }),
      ).toBeVisible();
      await expect.poll(shownCount).toBeGreaterThan(0);
      await expect.poll(shownCount).toBeLessThan(loaded);
      const active = await shownCount();
      await filters.getByRole("button", { name: "Filter", exact: true }).click();
      await page
        .getByRole("dialog", { name: "Filter" })
        .getByRole("button", { name: "Entity" })
        .click();
      const entityEditor = page.getByRole("dialog", { name: "Entity filter" });
      await entityEditor.getByRole("checkbox", { name: "AVM-US" }).check();
      await entityEditor.getByRole("button", { name: "Apply" }).click();
      await expect(
        filters.getByRole("button", { name: "Entity is AVM-US, edit filter" }),
      ).toBeVisible();
      await expect.poll(shownCount).toBeGreaterThan(0);
      expect(await shownCount()).toBeLessThanOrEqual(active);

      await page.getByRole("button", { name: /^View:/ }).click();
      await page.getByRole("menuitem", { name: "Save as new view" }).click();
      const dialog = page.getByRole("dialog", { name: "Save as new view" });
      await dialog.getByRole("textbox", { name: "Name" }).fill(ACTIVE_US_VIEW);
      await dialog.getByRole("button", { name: "Save view" }).click();
      await expect(page).toHaveURL(/[?&]view=[0-9a-f-]{36}(&|$)/);
      const viewId = new URL(page.url()).searchParams.get("view") ?? "";

      const restored = await listedTotal(page, () => page.goto(`/contracts?view=${viewId}`));
      await expect(page).toHaveURL(/f\.status=(is|in)(:|%3A)ACTIVE/);
      await expect(page.getByRole("button", { name: `View: ${ACTIVE_US_VIEW}` })).toBeVisible();
      const chips = page.getByTestId("SF-02-filter-bar").getByRole("toolbar", { name: "Filters" });
      await expect(
        chips.getByRole("button", { name: "Status is Active, edit filter" }),
      ).toBeVisible();
      await expect(
        chips.getByRole("button", { name: "Entity is AVM-US, edit filter" }),
      ).toBeVisible();
      expect(restored).toBeGreaterThan(0);
    });
  });
});

/** PRD §2.7 WLD-K-01 and WLD-K-11 external ids. */
const K01 = "SF-ORD-10001";
const K11 = "NS-SO-DE-5004";
/** SCREENS §0.12 SF-03:obligation context `entity=AVM-DE`. */
const AVM_DE_CONTEXT = "entity=AVM-DE&period=FY2026-P09&book=ASC606";

async function contractIdOf(page: Page, externalId: string): Promise<string> {
  const client = new ApiClient(page.request);
  const listed = await json<{
    readonly items: readonly { readonly id: string; readonly external_id: string }[];
  }>(await client.get("/api/v1/contracts", { q: externalId, limit: 50 }));
  const found = listed.items.find((item) => item.external_id === externalId);
  expect(found, `${externalId} is seeded (CTR-20)`).toBeDefined();
  return found?.id ?? "";
}

async function obligationIdOf(page: Page, contractId: string, key: string): Promise<string> {
  const client = new ApiClient(page.request);
  const listed = await json<{
    readonly items: readonly { readonly id: string; readonly obligation_key: string }[];
  }>(await client.get(`/api/v1/contracts/${contractId}/obligations`, { book: "ASC606" }));
  const found = listed.items.find((item) => item.obligation_key === key);
  expect(found, `obligation ${key} of ${contractId}`).toBeDefined();
  return found?.id ?? "";
}

/**
 * DS-VER-05 compact density on the page (DG-FE-13 `data-density`, as `screens.setTheme` sets the
 * theme). [J] The preference is not stored through `PATCH /me/preferences`, so the other `maya` rows
 * running in parallel keep the comfortable density of SCR-ST-20.
 */
async function setDensity(page: Page, density: "compact" | "comfortable"): Promise<void> {
  await page.evaluate((next) => {
    document.documentElement.setAttribute("data-density", next);
  }, density);
  await expect(page.locator("html")).toHaveAttribute("data-density", density);
}

test.describe("SF-03 Contract workbench (RT-10 /contracts/:contractId/obligations), persona maya", () => {
  test("SF-03 maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    const k01 = await contractIdOf(page, K01);

    // RT-10: `/contracts/<id>` redirects to the Obligations tab and keeps the context parameters.
    await page.goto(`/contracts/${k01}?${AVM_US_CONTEXT}`);
    await expect(page).toHaveURL(new RegExp(`/contracts/${k01}/obligations\\?entity=AVM-US`));
    const root = page.getByTestId("SF-03-page");
    await expect(root.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByTestId("SF-03-identifier")).toContainText(K01);
    // SCREENS §4.1.4 rev 1.21: the heading names the period the figures are measured at.
    await expect(
      page.getByRole("region", { name: "Key figures at Sep 2026 (USD, ASC 606)" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /^Explain Transaction price, USD / }),
    ).toBeVisible();
    await expect(page.getByRole("list", { name: "ASC 606 steps" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: `${K01} sections` })).toBeVisible();
    await expect(page.getByRole("listbox", { name: "Obligations" })).toBeVisible();
    await expect(
      page.getByText("Select an obligation to see its allocation, schedule and history."),
    ).toBeVisible();
    await screens.capture(page, "sf-03", { surface: "SF-03" });
    await a11y.check(page, "SF-03");

    await test.step("SCREENS §4.1.4: every KPI cell opens its explanation, not the load error (DG-FE-15)", async () => {
      const strip = page.getByTestId("SF-03-kpi-strip");
      const panel = page.getByRole("complementary");
      const failed = page.getByText("The explanation could not be loaded.");
      // Cells 1 and 5 name one node of the trace; cells 2 to 4 open the list level (rev 1.21).
      for (const [cell, heading, level] of [
        ["Transaction price", "Transaction price", "figure"],
        ["Billed", "Billed to date · Sep 2026", "list"],
        ["Recognized", "Recognized to date · Sep 2026", "list"],
        ["Scheduled", "Scheduled · Sep 2026", "list"],
        ["Awaiting trigger", "Awaiting trigger", "figure"],
      ] as const) {
        await strip.getByRole("button", { name: new RegExp(`^Explain ${cell}, USD `) }).click();
        await expect(panel.getByRole("heading", { level: 2, name: heading })).toBeVisible();
        if (level === "list") {
          await expect(panel.getByRole("table", { name: "By obligation" })).toBeVisible();
        } else {
          // The API answered the node: the sections render in place of the skeleton.
          await expect(panel.getByRole("heading", { level: 3, name: "Versions" })).toBeVisible();
        }
        await expect(failed).toHaveCount(0);
        await page.keyboard.press("Escape");
        await expect(panel).toHaveCount(0);
      }

      // Cell 6 (rev 1.24). Its three figures are explained at the address their balance entry names:
      // the id of the balance row, which only `kpis.balances[].links` carries (04 rev 1.174). A figure
      // the entry names no explanation for has no trigger, so each click also holds the link.
      for (const figure of ["Contract liability", "Contract asset", "Unbilled receivable"]) {
        await strip.getByRole("button", { name: new RegExp(`^Explain ${figure}, USD `) }).click();
        await expect(panel.getByRole("heading", { level: 2, name: figure })).toBeVisible();
        await expect(panel.getByRole("heading", { level: 3, name: "Versions" })).toBeVisible();
        await expect(failed).toHaveCount(0);
        await page.keyboard.press("Escape");
        await expect(panel).toHaveCount(0);
      }
    });

    await test.step("SCREENS §4.1.4 and §6.3 rev 1.21: Recognized opens the obligations at the measured period", async () => {
      // The trace holds no contract-level node per period, so the cell lists the obligations and each
      // entry opens the obligation's own node at the period its link carries (04 API-C-10).
      const read = await json<{
        readonly items: readonly {
          readonly obligation_key: string;
          readonly product: { readonly code: string };
          readonly to_date: {
            readonly revenue: { readonly amount: string; readonly currency: string };
          };
        }[];
      }>(
        await new ApiClient(page.request).get(`/api/v1/contracts/${k01}/obligations`, {
          book: "ASC606",
          as_of: "2026-09-30",
        }),
      );
      expect(read.items.length, `${K01} has obligations`).toBeGreaterThan(0);
      const first = read.items[0];
      if (first === undefined) {
        throw new Error(`${K01} has no obligation`);
      }

      await page
        .getByTestId("SF-03-kpi-strip")
        .getByRole("button", { name: /^Explain Recognized, USD / })
        .click();
      const name = "Recognized to date · Sep 2026";
      const list = page.getByRole("complementary", { name });
      await expect(list).toBeVisible();
      const rows = list.getByRole("table", { name: "By obligation" }).locator("tbody tr");
      await expect(rows).toHaveCount(read.items.length);
      for (const [index, item] of read.items.entries()) {
        await expect(rows.nth(index).getByRole("rowheader")).toHaveText(
          `${item.obligation_key} · ${item.product.code}`,
        );
        // E2E-02: the API's decimal, as the list prints it.
        await expect(rows.nth(index).getByRole("cell").first()).toHaveText(
          `${item.to_date.revenue.currency} ${groupedDigits(item.to_date.revenue.amount)}`,
        );
      }
      await expect(list.getByRole("button", { name: "Verify" })).toHaveCount(0);
      await expect(list.getByRole("link", { name: "Open calculation trace" })).toHaveCount(0);
      await expect(page).not.toHaveURL(/[?&]explain=/);

      await list.getByRole("button", { name: `Explain ${first.obligation_key}` }).click();
      const entry = page.getByRole("complementary", {
        name: `Recognized to date · ${first.obligation_key} · Sep 2026`,
      });
      // The API answers the obligation's node at that period: the sections render, not the error.
      await expect(entry.getByRole("heading", { level: 3, name: "Formula" })).toBeVisible();
      await expect(entry.getByRole("button", { name: "Verify" })).toBeVisible();
      await expect(entry.getByText("The explanation could not be loaded.")).toHaveCount(0);
      await expect(page).toHaveURL(
        /[?&]explain=obligation_version(~|%7E)[0-9a-f-]{36}(~|%7E)revenue_cum(~|%7E)FY2026-P09/,
      );
      await entry.getByRole("button", { name: `Back to ${name}` }).click();
      await expect(list.getByRole("table", { name: "By obligation" })).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(page.getByRole("complementary", { name })).toHaveCount(0);
      await expect(page).not.toHaveURL(/[?&]explain=/);
    });

    await test.step("REQ-UX-003 record header, KPI strip, tabs and obligation pane on SF-03", async () => {
      await expect(page.getByTestId("SF-03-page")).toBeVisible();
      await expect(page.getByTestId("SF-03-kpi-strip")).toBeVisible();
      await expect(page.getByTestId("SF-03-tracker")).toBeVisible();
      await expect(page.getByTestId("SF-03-tabs")).toBeVisible();
      await page.getByTestId("SF-03-row-o1").click();
      await expect(page).toHaveURL(new RegExp(`/contracts/${k01}/obligations/[0-9a-f-]{36}\\?`));
      const pane = page.getByTestId("SF-03-pane-obligation");
      await expect(pane).toHaveAttribute("role", "region");
      await expect(pane).toHaveAttribute("aria-label", /^Obligation details: .+/);
      await expect(page.getByRole("region", { name: /^Obligation details: .+/ })).toBeVisible();
      await expect(pane.getByRole("tablist", { name: "Obligation sections" })).toBeVisible();
      await expect(pane.getByRole("button", { name: /^Explain Recognized, USD / })).toBeVisible();
    });

    await test.step("REQ-UX-008 compact density captures of SF-02 and SF-03", async () => {
      await page.goto(`/contracts?${AVM_US_CONTEXT}`);
      await expect(
        page.getByTestId("SF-02-grid-contracts").getByRole("grid", { name: "Contracts" }),
      ).toBeVisible();
      // The rows have loaded: the header count is shown and a data row renders.
      await expect(
        page
          .getByTestId("SF-02-page")
          .locator("header")
          .getByText(/^[\d,]+ contracts?$/),
      ).toBeVisible();
      await expect(
        page.getByTestId("SF-02-grid-contracts").getByRole("rowheader").first(),
      ).toBeVisible();
      await setDensity(page, "compact");
      await screens.capture(page, "sf-02-compact", { surface: "SF-02" });

      await page.goto(`/contracts/${k01}/obligations?${AVM_US_CONTEXT}`);
      await expect(page.getByTestId("SF-03-kpi-strip")).toBeVisible();
      await expect(page.getByRole("listbox", { name: "Obligations" })).toBeVisible();
      await setDensity(page, "compact");
      await screens.capture(page, "sf-03-compact", { surface: "SF-03" });
      await setDensity(page, "comfortable");
    });
  });
});

test.describe("SF-03:obligation Obligation detail pane (RT-11 /contracts/:contractId/obligations/:obligationId), persona maya", () => {
  test("SF-03:obligation maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    const k11 = await contractIdOf(page, K11);
    const o1 = await obligationIdOf(page, k11, "O1");
    await page.goto(`/contracts/${k11}/obligations/${o1}?${AVM_DE_CONTEXT}&pane=ssp`);
    const pane = page.getByTestId("SF-03-pane-obligation");
    await expect(pane).toHaveAttribute("aria-label", /^Obligation details: .+/);
    await expect(page.getByRole("tabpanel", { name: "SSP and allocation" })).toBeVisible();
    const ssp = page.getByTestId("SF-03-pane-ssp");
    // PRD WLD-X-22: DE-LIST 2026, low 81,000.00, mid 90,000.00, high 99,000.00, inside range.
    await expect(ssp).toContainText("DE-LIST 2026");
    await expect(ssp).toContainText("81,000.00");
    await expect(ssp).toContainText("90,000.00");
    await expect(ssp).toContainText("99,000.00");
    await expect(ssp).toContainText("Inside range");
    // `main` scrolls inside the viewport: bring the asserted panel into the capture.
    await ssp.scrollIntoViewIfNeeded();
    await screens.capture(page, "sf-03-obligation", { surface: "SF-03:obligation" });
    await a11y.check(page, "SF-03:obligation");
  });
});

/** PRD §2.7 WLD-K-02; SCREENS §0.12 captures SF-03:schedules, SF-03:billing and SF-03:journals on K-02. */
const K02 = "SF-ORD-10002";

/**
 * `main` scrolls inside the viewport. A tab panel is brought just below the tabs, so the capture shows
 * the tabs, the panel's toolbar and its rows, while the record header is still partly in view and the
 * condensed header (DS-CMP-06) does not cover the toolbar.
 */
async function frameTabPanel(page: Page, panel: Locator): Promise<void> {
  await panel.evaluate((element) => {
    const main = element.closest("main");
    if (main !== null) {
      main.scrollTop += element.getBoundingClientRect().top - 130;
    }
  });
  await expect(page.getByTestId("SF-03-tabs")).toBeInViewport();
}

test.describe("SF-03:schedules Schedules tab (RT-14 /contracts/:contractId/schedules), persona maya", () => {
  test("SF-03:schedules maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    const k02 = await contractIdOf(page, K02);
    await page.goto(`/contracts/${k02}/schedules?${AVM_US_CONTEXT}`);
    await expect(page.getByTestId("SF-03-identifier")).toContainText(K02);
    await expect(
      page
        .getByRole("navigation", { name: `${K02} sections` })
        .getByRole("link", { name: "Schedules" }),
    ).toHaveAttribute("aria-current", "page");
    const section = page.getByTestId("SF-03-grid-revenue-schedule");
    const grid = section.getByRole("grid", { name: "Revenue schedule" });
    await expect(grid).toBeVisible();
    // PRD WLD-K-02 (CTR-20 test_key_figures): the O1 normal line of FY2026-P09 is 9,863.01.
    const p09 = grid
      .getByRole("row")
      .filter({ hasText: "Sep 2026" })
      .filter({ hasText: "9,863.01" });
    await expect(p09).toHaveCount(1);
    await expect(
      p09.getByRole("button", { name: "Explain Revenue · Sep 2026 · O1, USD 9,863.01" }),
    ).toBeVisible();
    await frameTabPanel(page, section);
    await expect(p09).toBeInViewport();
    await screens.capture(page, "sf-03-schedules", { surface: "SF-03:schedules" });
    await a11y.check(page, "SF-03:schedules");
  });
});

test.describe("SF-03:billing Billing tab (RT-15 /contracts/:contractId/billing), persona maya", () => {
  test("SF-03:billing maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    const k02 = await contractIdOf(page, K02);
    await page.goto(`/contracts/${k02}/billing?${AVM_US_CONTEXT}`);
    const balances = page.getByRole("table", { name: "Balances by entity (USD)" });
    await expect(balances).toBeVisible();
    await expect(page.getByTestId("SF-03-grid-balances")).toBeVisible();
    await expect(balances.getByRole("columnheader", { name: "AVM-US" })).toBeVisible();
    await expect(balances.getByRole("rowheader", { name: "Contract liability" })).toBeVisible();
    // D-12: labelled balances only; the signed net position never renders.
    await expect(page.getByTestId("SF-03-page")).not.toContainText(/net position/i);
    const grid = page
      .getByTestId("SF-03-grid-invoices")
      .getByRole("grid", { name: "Invoices and credit memos" });
    await expect(grid).toBeVisible();
    // PRD WLD-K-02: invoice INV-US-1002 of 120,000.00.
    const invoice = page.getByTestId("SF-03-row-inv-us-1002");
    await expect(invoice.getByRole("rowheader", { name: "INV-US-1002" })).toBeVisible();
    await expect(invoice).toContainText("120,000.00");
    // R-RC-1 (L5-4-Q-48): the billing plan row "120,000.00 due 01 Jan 2027" waits for CTR-14 (post-rc),
    // so no billing plan panel renders.
    await expect(page.getByRole("table", { name: /^Billing plan/ })).toHaveCount(0);
    await page
      .getByRole("heading", { level: 2, name: "Balances by entity (USD)" })
      .scrollIntoViewIfNeeded();
    await screens.capture(page, "sf-03-billing", { surface: "SF-03:billing" });
    await a11y.check(page, "SF-03:billing");

    await test.step("SCREENS §4.4 rev 1.24: every balance trigger opens its explanation, not the load error (DG-FE-15)", async () => {
      // A cell is a trigger where its row names the explanation of that balance. With the zero rows
      // shown, every trigger of the table is followed to the panel of its figure.
      await page.getByRole("switch", { name: "Show zero balances" }).click();
      await expect(balances.getByRole("rowheader", { name: "Loss provision" })).toBeVisible();
      const names = await balances
        .getByRole("button", { name: /^Explain / })
        .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("aria-label") ?? ""));
      // The API names the three balances of the workbench's sixth cell (04 rev 1.174).
      for (const balance of ["Contract liability", "Contract asset", "Unbilled receivable"]) {
        expect(
          names.filter((name) => name.startsWith(`Explain ${balance} · AVM-US, USD `)),
          `${balance} of AVM-US is an Explain trigger`,
        ).toHaveLength(1);
      }
      const panel = page.getByRole("complementary");
      for (const name of names) {
        const figure = /^Explain (.+), [A-Z]{3} /.exec(name)?.[1] ?? name;
        await balances.getByRole("button", { name, exact: true }).click();
        await expect(
          panel.getByRole("heading", { level: 2, name: figure, exact: true }),
        ).toBeVisible();
        await expect(panel.getByRole("heading", { level: 3, name: "Versions" })).toBeVisible();
        await expect(page.getByText("The explanation could not be loaded.")).toHaveCount(0);
        await page.keyboard.press("Escape");
        await expect(panel).toHaveCount(0);
      }
    });
  });
});

test.describe("SF-03:journals Journals tab (RT-16 /contracts/:contractId/journals), persona maya", () => {
  test("SF-03:journals maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    const k02 = await contractIdOf(page, K02);
    await page.goto(`/contracts/${k02}/journals?${AVM_US_CONTEXT}`);
    const section = page.getByTestId("SF-03-grid-journal-lines");
    const grid = section.getByRole("grid", { name: "Journal lines" });
    await expect(grid).toBeVisible();
    const rows = grid.locator('[role="row"][aria-rowindex]:not([aria-rowindex="1"])');
    await expect(rows.first()).toBeVisible();
    // SCREENS §4.5: every Debit and Credit cell holding a figure is an Explain trigger, one side a line.
    const amounts = grid
      .locator('[role="gridcell"][data-column="debit"], [role="gridcell"][data-column="credit"]')
      .filter({ hasText: /\d/ });
    const count = await amounts.count();
    expect(count).toBeGreaterThan(0);
    expect(count).toBe(await rows.count());
    for (let index = 0; index < count; index += 1) {
      await expect(
        amounts
          .nth(index)
          .getByRole("button", { name: /^Explain (Debit|Credit) for .+, USD [\d,]+\.\d{2}$/ }),
      ).toHaveCount(1);
    }
    await frameTabPanel(page, section);
    // The period is pinned: the grid scrolls to its end, so Debit and Credit are in the capture.
    await grid.evaluate((element) => {
      element.scrollLeft = element.scrollWidth;
    });
    await expect(amounts.first()).toBeInViewport();
    await screens.capture(page, "sf-03-journals", { surface: "SF-03:journals" });
    await a11y.check(page, "SF-03:journals");
  });
});

/** SCREENS §7.12 J-05: the wording of the items of the K-02 change, as the screens show them. */
const K02_CHANGE = {
  // 775 seats for the remaining term price the line below its SSP range of 69,750.00 to 85,250.00.
  quantity: "775",
  price: "60,000.00",
  effective: "2026-09-16",
  priceReason: /^60,000\.00 is below the range low 69,750\.00 \(US-LIST/,
  prospective: "Prospective (ASC 606-10-25-13(a))",
} as const;

interface ModificationRef {
  readonly id: string;
  readonly contractId: string;
  readonly reference: string;
}

interface ModificationRead {
  readonly id: string;
  readonly reference: string | null;
  readonly kind: string;
  readonly status: string;
  readonly approval_request_id: string | null;
  readonly chosen_treatments: Readonly<Record<string, string>>;
  /** 04 §16.14 rev 1.250: the engine's price test of each added line, whatever is answered. */
  readonly price_tests?: Readonly<
    Record<string, { readonly value: boolean; readonly reason_key: string } | undefined>
  >;
  /** 04 §16.14 rev 1.210: the estimate versions created inside the modification. */
  readonly linked_estimate_versions: readonly { readonly id: string }[];
  readonly impact_preview: {
    readonly transaction_price_before: { readonly amount: unknown };
    readonly transaction_price_after: { readonly amount: unknown };
    readonly catch_up_total: { readonly amount: unknown };
    readonly rpo_before: { readonly amount: unknown };
    readonly rpo_after: { readonly amount: unknown };
    readonly revenue_by_period: readonly {
      readonly period_key: string;
      readonly before: { readonly amount: unknown };
      readonly after: { readonly amount: unknown };
      readonly change: { readonly amount: unknown };
    }[];
    readonly remaining_allocation_before: readonly ImpactAllocation[];
    readonly remaining_allocation_after: readonly ImpactAllocation[];
    readonly computed_at?: string | null;
    readonly computed_period_key?: string | null;
  } | null;
}

interface ImpactAllocation {
  readonly obligation_key: string;
  readonly amount: { readonly amount: unknown };
}

/** The remaining allocation a preview states for one obligation, or undefined when it names none. */
function remainingOf(rows: readonly ImpactAllocation[], key: string): unknown {
  return rows.find((row) => row.obligation_key === key)?.amount.amount;
}

function readModification(page: Page, id: string): Promise<ModificationRead> {
  return new ApiClient(page.request)
    .get(`/api/v1/modifications/${id}`)
    .then((response) => json<ModificationRead>(response));
}

test.describe("SF-03:modifications, SF-07 and SF-07:detail: the modifications of K-02 (RT-17, RT-20, RT-21), persona maya", () => {
  // BUILD_SPEC CTR-27: the two SF-07 rows put a modification on K-02, whose list the tab row reads
  // first, and "SF-07:detail maya" takes the draft "SF-07 maya" leaves. One worker, in order. That
  // row submits the draft, withdraws the request, reads step Change of the draft again — its linked
  // estimate versions, none on K-02, which holds no estimated element (item MOD-LINKED-ESTIMATES-1) —
  // and discards the draft (PRD SM-03 "Discard draft"; item MOD-DISCARD-1): the modification stays on
  // K-02 as Void under a reference of its own, and the crawl opens RT-21 on it (crawl.spec.ts
  // LEFT_BY_SCREENS).
  test.describe.configure({ mode: "serial" });
  let draft: ModificationRef | null = null;

  test("SF-03:modifications maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    const k02 = await contractIdOf(page, K02);
    await page.goto(`/contracts/${k02}/modifications?${AVM_US_CONTEXT}`);
    await expect(page.getByTestId("SF-03-identifier")).toContainText(K02);
    await expect(
      page
        .getByRole("navigation", { name: `${K02} sections` })
        .getByRole("link", { name: /^Modifications/ }),
    ).toHaveAttribute("aria-current", "page");
    const section = page.getByTestId("SF-03-grid-modifications");
    const grid = section.getByRole("grid", { name: "Modifications" });
    await expect(grid).toBeVisible();
    await expect(section.getByRole("heading", { level: 2, name: "Modifications" })).toBeVisible();
    // SCREENS §4.6 columns; "Template mode" stays hidden by default.
    for (const header of [
      "Reference",
      "Kind",
      "Effective date",
      "Treatment",
      "Status",
      "Catch-up (USD)",
      "Prepared by",
    ]) {
      // A DataGrid header cell is named by its label and its column menu ("… Column options: …").
      await expect(
        grid.getByRole("columnheader", { name: new RegExp(`^${escapeRegExp(header)} `) }),
      ).toBeVisible();
    }
    await expect(grid.getByRole("columnheader", { name: /^Template mode / })).toHaveCount(0);
    // The grid shows what `GET /contracts/{id}/modifications` answers: its rows, else the empty state.
    const listed = await json<{ readonly items: readonly { readonly id: string }[] }>(
      await new ApiClient(page.request).get(`/api/v1/contracts/${k02}/modifications`, {
        limit: 200,
      }),
    );
    if (listed.items.length === 0) {
      await expect(section.getByRole("heading", { name: "No modifications" })).toBeVisible();
      await expect(
        section.getByText(
          "Changes to scope or price appear here with their classification and approval.",
        ),
      ).toBeVisible();
    } else {
      await expect(grid.getByRole("rowheader")).toHaveCount(listed.items.length);
    }
    // The header's five steps have read their facts: a step still reading shows a bar where its
    // status line stands — the capture of 2026-10-01 23:10 held one for the SSP version of step 4.
    await expect(
      page.getByTestId("SF-03-tracker").locator('[aria-busy="true"], [data-skeleton]'),
    ).toHaveCount(0);
    await frameTabPanel(page, section);
    await screens.capture(page, "sf-03-modifications", { surface: "SF-03:modifications" });
    await a11y.check(page, "SF-03:modifications");
  });

  test("SF-07 maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    const k02 = await contractIdOf(page, K02);
    const reference = `CR-E2E-${randomUUID().slice(0, 8).toUpperCase()}`;

    // SCREENS §4.1.6: the header of an active contract offers the change, and it is the one place of
    // the command (rev 1.29); "Co-term" opens SF-07 with its action. API-R-31 has no subscription
    // route of its own (CTR-18), and its `UPGRADE` line changes an obligation, so the seats added
    // for the remaining term are a co-term line (`ADD`).
    await page.goto(`/contracts/${k02}/modifications?${AVM_US_CONTEXT}`);
    await expect(page.getByTestId("SF-03-identifier")).toContainText(K02);
    await page.getByRole("button", { name: "Change subscription" }).click();
    await page.getByRole("menuitem", { name: "Co-term" }).click();
    await expect(page).toHaveURL(
      new RegExp(`/contracts/${k02}/modifications/new\\?${AVM_US_CONTEXT}&action=co_term$`),
    );
    const wizard = page.getByTestId("SF-07-page");
    await expect(wizard.getByRole("heading", { level: 1, name: "New modification" })).toBeVisible();
    const steps = page.getByRole("navigation", { name: "Modification steps" });
    await expect(steps.getByRole("listitem")).toHaveCount(5);
    await expect(steps.locator('[aria-current="step"]')).toContainText("Change");

    // Step 1: the one obligation of K-02 is chosen and the added obligation takes the next key.
    await expect(page.getByRole("combobox", { name: /^Obligation/ })).toContainText("O1");
    await expect(page.getByRole("textbox", { name: /^New obligation key/ })).toHaveValue("O2");
    await expect(page.getByText("Ends on 31 Dec 2027")).toBeVisible();
    await page.getByRole("textbox", { name: /^Quantity/ }).fill(K02_CHANGE.quantity);
    const price = page.getByRole("textbox", { name: /^Price/ });
    await price.fill("60000");
    await page.getByRole("textbox", { name: /^Effective date/ }).fill(K02_CHANGE.effective);
    await expect(price).toHaveValue(K02_CHANGE.price);
    await page.getByRole("textbox", { name: /^Reference/ }).fill(reference);
    await page.getByRole("button", { name: "Next" }).click();

    // The draft exists: the URL is SF-07:detail at step 2, and the classification proposes the answers.
    await expect(page).toHaveURL(
      new RegExp(
        `/contracts/${k02}/modifications/[0-9a-f-]{36}\\?${AVM_US_CONTEXT}&step=questionnaire$`,
      ),
    );
    const id = new URL(page.url()).pathname.split("/")[4] ?? "";
    draft = { id, contractId: k02, reference };
    await expect(page.getByTestId("SF-07-stepper")).toBeVisible();
    await expect(steps.locator('[aria-current="step"]')).toContainText("Questionnaire");
    await expect(page.getByTestId("SF-07-identifier")).toHaveText(reference);
    const priced = page.getByRole("radiogroup", { name: /^Is the added price at SSP\?/ });
    await expect(priced.getByRole("radio", { name: "No" })).toBeChecked();
    await expect(page.getByText(K02_CHANGE.priceReason)).toBeVisible();
    await expect(
      page
        .getByRole("radiogroup", { name: /^Are the added goods or services distinct\?/ })
        .getByRole("radio", { name: "Yes" }),
    ).toBeChecked();
    await expect(
      page
        .getByRole("radiogroup", { name: /^Are the remaining goods or services distinct/ })
        .getByRole("radio", { name: "Yes" }),
    ).toBeChecked();
    await expect(page.getByText("Prefilled", { exact: true })).toHaveCount(3);
    await expect(page.getByText(`Proposed treatment: ${K02_CHANGE.prospective}`)).toBeVisible();
    // BR-MOD-01: a proposed answer is not the preparer's until it is confirmed.
    await expect(page.getByTestId("SF-07-blocked")).toHaveText("Confirm every answer to continue.");
    await expect(page.getByRole("button", { name: "Next" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    const stored = await readModification(page, id);
    expect(stored).toMatchObject({ reference, kind: "CO_TERM", status: "DRAFT" });
    await screens.capture(page, "sf-07", { surface: "SF-07" });
    await a11y.check(page, "SF-07");
  });

  test("SF-07:detail maya", async ({ personas, screens, a11y }) => {
    test.setTimeout(240_000);
    const made = draft;
    if (made === null) {
      throw new Error('"SF-07 maya" left no draft for this test to open');
    }
    const page = await personas.page("maya");
    const api = new ApiClient(page.request);
    const next = page.getByRole("button", { name: "Next" });
    let submittedToast = "";

    // BUILD_SPEC CTR-27 names the seeded modification CR-PELLWORTH-2026-07; the demo world holds no
    // modification, and as maya a draft renders the wizard, so the row takes the K-02 draft through
    // the product until it is submitted, withdraws the request afterwards and discards the draft.
    try {
      await test.step("steps 2 to 5: confirmed answers, the proposed treatments, the preview, the submission", async () => {
        await page.goto(
          `/contracts/${made.contractId}/modifications/${made.id}?${AVM_US_CONTEXT}&step=questionnaire`,
        );
        for (const key of ["O2", "O1"]) {
          // The box is checked once the answers are stored and the classification has answered.
          const confirm = page.getByRole("checkbox", {
            name: `I confirm these answers for ${key}`,
          });
          await confirm.click();
          await expect(confirm).toBeChecked();
        }
        await expect(page.getByTestId("SF-07-blocked")).toHaveCount(0);
        await expect(next).not.toHaveAttribute("aria-busy", "true");
        // 04 §16.14 rev 1.250 (item MOD-PRICE-TEST-FACT-1): the row states the engine's price test
        // of the added line whatever is stored — both answers of O2 are — and the screen keeps its
        // sentence under the answer, as a fact and no longer as a proposal (SCREENS §7.5).
        const tested = (await readModification(page, made.id)).price_tests?.O2;
        expect(tested?.reason_key).toBe("modifications.prefill.priced_at_ssp.below_range");
        expect(tested?.value).toBe(false);
        await expect(page.getByText(K02_CHANGE.priceReason)).toBeVisible();
        await expect(page.getByText("Prefilled", { exact: true })).toHaveCount(0);
        await next.click();

        const treatments = page.getByRole("table", { name: "Treatment by obligation" });
        for (const key of ["O1", "O2"]) {
          await expect(
            treatments.getByRole("combobox", { name: `Chosen treatment for ${key}` }),
          ).toHaveValue("PROSPECTIVE");
        }
        // The SSP basis of the added line: the version and the range of its price test.
        await expect(treatments.getByRole("row", { name: /^O2 AVM-SEAT-MO / })).toContainText(
          "69,750.00 to 85,250.00",
        );
        await expect(page.getByTestId("SF-07-banner-override")).toHaveCount(0);
        await next.click();

        // Step 4 runs the preview job; the figures are the API's (E2E-02), read as strings first.
        const strip = page.getByRole("region", { name: "Impact summary (USD)" });
        await expect(strip).toBeVisible({ timeout: 120_000 });
        const preview = (await readModification(page, made.id)).impact_preview;
        if (preview === null) {
          throw new Error("the modification holds no preview after its job");
        }
        // PRD WLD-X-05, WLD-X-06 (J-05.3).
        expectDecimal(preview.transaction_price_before.amount, "240000.00");
        expectDecimal(preview.transaction_price_after.amount, "300000.00");
        expectDecimal(preview.catch_up_total.amount, "0.00");
        expectDecimal(preview.rpo_before.amount, "155178.08");
        expectDecimal(preview.rpo_after.amount, "215178.08");
        const september = preview.revenue_by_period.find(
          (period) => period.period_key === "FY2026-P09",
        );
        expectDecimal(september?.before.amount, "9863.01");
        expectDecimal(september?.after.amount, "11769.80");
        expectDecimal(september?.change.amount, "1906.79");
        await expect(strip).toContainText("300,000.00");
        await expect(strip).toContainText("Before 240,000.00");
        await expect(strip).toContainText("215,178.08");
        await expect(strip).toContainText("Before 155,178.08");
        await expect(strip).toContainText("11,769.80");
        await expect(strip).toContainText("Before 9,863.01");
        // PRD WLD-X-06, SCREENS §7.12: the pool 215,178.08 splits over the remaining O1 and the added
        // obligation by their SSPs at the modification date (item DEMO-SSP-BASIS-1).
        expectDecimal(remainingOf(preview.remaining_allocation_before, "O1"), "155178.08");
        expectDecimal(remainingOf(preview.remaining_allocation_after, "O1"), "148451.55");
        expectDecimal(remainingOf(preview.remaining_allocation_after, "O2"), "66726.53");
        const allocation = page.getByRole("table", { name: "Allocation by obligation" });
        await expect(allocation.getByRole("rowheader", { name: "O2 (added)" })).toBeVisible();
        const remainingO1 = allocation.getByRole("row", { name: /^O1 / });
        await expect(remainingO1).toContainText("155,178.08");
        await expect(remainingO1).toContainText("148,451.55");
        await expect(allocation.getByRole("row", { name: /^O2 \(added\) / })).toContainText(
          "66,726.53",
        );
        await expect(
          page.getByRole("table", { name: "Revenue by period" }).getByRole("row", {
            name: /^Sep 2026 /,
          }),
        ).toContainText("+1,906.79");
        // 04 API-S-ImpactSummary (rev 1.210; SCREENS §7.7 rev 1.52): the journal preview states the
        // instant and the period its lines were computed for, the latest postable period of the
        // entity as the API answers it; while that period is still the latest one nothing is added.
        // No figure of the journal is read: it moves with the open period.
        expect(typeof preview.computed_at).toBe("string");
        const calendar = await json<{
          readonly items: readonly {
            readonly state: string;
            readonly period: {
              readonly period_key: string;
              readonly name: string;
              readonly end_date: string;
            };
          }[];
        }>(await api.get("/api/v1/periods", { entity: "AVM-US", limit: 200 }));
        const postable = calendar.items
          .filter((item) => ["open", "closing", "reopened"].includes(item.state))
          .sort((left, right) => left.period.end_date.localeCompare(right.period.end_date));
        const latest = postable[postable.length - 1]?.period;
        expect(preview.computed_period_key).toBe(latest?.period_key);
        const computed = page.getByTestId("SF-07-journal-computed");
        await expect(computed).toHaveText(
          /^Computed \d{2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2} UTC for .+: the entries the approval would post then/,
        );
        await expect(computed).toContainText(`for ${latest?.name ?? ""}:`);
        await expect(page.getByTestId("SF-07-banner-period-moved")).toHaveCount(0);
        await expectUnclipped(page.getByTestId("SF-07-kpi-strip").locator("dd"));
        await next.click();

        await expect(page.getByTestId("SF-07-summary")).toContainText(made.reference);
        await page.getByRole("button", { name: "Submit for approval" }).click();
        // SCREENS §7.8 (rev 1.42; PRD rev 1.158 J-06.5): a submission routes one request, and the
        // toast names it.
        const toast = page.getByText(
          /^Submitted for approval\. Request \S+ is waiting for approval\.$/,
        );
        await expect(toast).toBeVisible({ timeout: 30_000 });
        submittedToast = (await toast.innerText()).trim();
        // The toast would cover the lower right of the captures.
        await page
          .getByRole("region", { name: "Messages" })
          .getByRole("button", { name: "Dismiss message" })
          .click();
        await expect(toast).toHaveCount(0);
      });

      // SF-07:detail of a modification that is not a draft: read-only, with its routing.
      const detail = page.getByTestId("SF-07-detail-page");
      await expect(
        detail.getByRole("heading", { level: 1, name: `Modification ${made.reference}` }),
      ).toBeVisible();
      const submitted = await readModification(page, made.id);
      expect(submitted.status).toBe("SUBMITTED");
      expect(submitted.chosen_treatments).toEqual({ O1: "PROSPECTIVE", O2: "PROSPECTIVE" });
      await expect(detail.getByText("Co-term · effective 16 Sep 2026")).toBeVisible();
      const steps = page.getByRole("navigation", { name: "Modification steps" });
      await expect(steps.locator('[aria-current="step"]')).toContainText("Pending approval");
      await expect(steps.getByRole("link")).toHaveCount(0);
      for (const heading of [
        "Change",
        "Answers",
        "Treatments",
        "Impact preview as submitted",
        "Approval",
      ]) {
        await expect(detail.getByRole("heading", { level: 2, name: heading })).toBeVisible();
      }
      const treatments = detail.getByRole("table", { name: "Treatment by obligation" });
      await expect(treatments.getByRole("combobox")).toHaveCount(0);
      // The treatment this world produces; BUILD_SPEC names "Separate contract" for the seeded record.
      await expect(treatments.getByText(K02_CHANGE.prospective)).toHaveCount(4);
      // SCREENS §7.9 (rev 1.52; 04 §16.14 rev 1.250): the submitted row still states the engine's
      // price test, and the reviewer reads it — its sentence under the answer of the price question
      // and its range beside the SSP basis of the added line.
      expect(submitted.price_tests?.O2?.reason_key).toBe(
        "modifications.prefill.priced_at_ssp.below_range",
      );
      await expect(
        page.getByTestId("SF-07-section-answers").getByText(K02_CHANGE.priceReason),
      ).toBeVisible();
      await expect(treatments.getByRole("row", { name: /^O2 / })).toContainText(
        "69,750.00 to 85,250.00",
      );
      await expect(
        detail.getByText(/^Snapshot [0-9a-f]{12} reviewed by the approver\.$/),
      ).toBeVisible();
      await expect(detail.getByRole("region", { name: "Impact summary (USD)" })).toContainText(
        "300,000.00",
      );
      // One row per routing step of the request, as `GET /approvals/{id}` answers them.
      const request = await json<{
        readonly request_no: string;
        readonly status: string;
        readonly steps: readonly { readonly name: string }[];
      }>(await api.get(`/api/v1/approvals/${submitted.approval_request_id ?? ""}`));
      expect(request.status).toBe("PENDING");
      expect(submittedToast).toBe(
        `Submitted for approval. Request ${request.request_no} is waiting for approval.`,
      );
      const routing = page.getByRole("list", { name: "Approval routing" });
      await expect(routing.getByRole("listitem")).toHaveCount(request.steps.length);
      await expect(routing.getByRole("listitem").first()).toContainText(
        `${request.steps[0]?.name ?? ""} · Approve contract modifications`,
      );
      await expect(routing.getByRole("listitem").first()).toContainText("Pending approval");
      await expect(detail.getByText(request.request_no, { exact: true })).toBeVisible();
      await expect(page.getByTestId("SF-07-routing")).toBeVisible();
      await screens.capture(page, "sf-07-detail", { surface: "SF-07:detail" });
      await a11y.check(page, "SF-07:detail");
      // The lower half of the page: the stored preview's tables and the approval routing.
      await page.getByTestId("SF-07-section-approval").scrollIntoViewIfNeeded();
      await screens.capture(page, "sf-07-detail-approval", { surface: "SF-07:detail" });

      await test.step("the preparer withdraws the request and the modification is a draft again", async () => {
        await page.getByRole("button", { name: "Withdraw request" }).click();
        const dialog = page.getByRole("dialog", { name: "Withdraw request" });
        await dialog
          .getByRole("textbox", { name: /^Comment/ })
          .fill("Screen audit row: the request is withdrawn after its capture.");
        await dialog.getByRole("button", { name: "Withdraw request" }).click();
        await expect(
          page.getByText("The request was withdrawn. The modification is a draft again."),
        ).toBeVisible({ timeout: 30_000 });
        await expect(page.getByTestId("SF-07-page")).toBeVisible();
        expect((await readModification(page, made.id)).status).toBe("DRAFT");
      });

      await test.step("step Change of the draft: its linked estimate versions and what Add estimate version says (SCREENS §7.4)", async () => {
        await page.goto(
          `/contracts/${made.contractId}/modifications/${made.id}?${AVM_US_CONTEXT}&step=change`,
        );
        const heading = page.getByRole("heading", { level: 3, name: "Linked estimate versions" });
        await expect(heading).toBeVisible();
        // 04 §16.14 rev 1.210: the row names the estimate versions created inside it. None was.
        expect((await readModification(page, made.id)).linked_estimate_versions).toEqual([]);
        await expect(page.getByText("No estimate version is linked.")).toBeVisible();
        await expect(page.getByTestId("SF-07-grid-estimate-versions")).toHaveCount(0);
        // maya holds `estimate.create` for AVM-US, so the command renders; it is unavailable while
        // the contract has no estimated element, as `GET …/estimates` answers, and its reason is
        // a visible line (SCREENS §0.6 SCR-PERM-03).
        const elements = await json<{ readonly items: readonly { readonly id: string }[] }>(
          await api.get(`/api/v1/contracts/${made.contractId}/estimates`, { limit: 200 }),
        );
        const add = page.getByRole("button", { name: "Add estimate version" });
        await expect(add).not.toHaveAttribute("aria-busy", "true");
        await heading.scrollIntoViewIfNeeded();
        if (elements.items.length === 0) {
          await expect(add).toHaveAttribute("aria-disabled", "true");
          await expect(page.getByTestId("SF-07-linked-blocked")).toHaveText(
            "Add an estimated element on the Estimates tab first.",
          );
          await expect(page.getByTestId("SF-07-linked-blocked")).toBeVisible();
        }
        await screens.capture(page, "sf-07-change", { surface: "SF-07" });
      });

      await test.step("Discard draft voids the draft and opens the Modifications tab (SCREENS §7.3; PRD SM-03)", async () => {
        await page.getByRole("button", { name: "Discard draft" }).click();
        const confirm = page.getByRole("alertdialog", { name: "Discard this draft modification?" });
        await expect(confirm).toBeVisible();
        await confirm.getByRole("button", { name: "Discard draft" }).click();
        await expect(page.getByText("The draft modification was discarded.")).toBeVisible({
          timeout: 30_000,
        });
        await expect(page).toHaveURL(
          new RegExp(`/contracts/${made.contractId}/modifications\\?${AVM_US_CONTEXT}$`),
        );
        expect((await readModification(page, made.id)).status).toBe("VOIDED");
        // The tab lists it under its reference, as Void.
        const grid = page
          .getByTestId("SF-03-grid-modifications")
          .getByRole("grid", { name: "Modifications" });
        await expect(
          grid.getByRole("row", { name: new RegExp(escapeRegExp(made.reference)) }),
        ).toContainText("Void");
      });
    } finally {
      // A request this row submitted never stays pending, whatever failed before its withdrawal.
      const left = await readModification(page, made.id);
      if (left.status === "SUBMITTED") {
        await json(
          await api.command("POST", `/api/v1/modifications/${made.id}/withdraw`, {
            comment: "Screen audit row: withdrawn after a failed step.",
          }),
        );
      }
    }
  });
});

const K03 = "PRJ-CB-2026-01";
/** SCREENS §8.9 K-03 `EAC`: version 1 (WLD-X-12), as the rows type and read it. */
const K03_EAC = {
  code: "EAC",
  effective: "01 Feb 2026",
  total: "700,000.00",
  totalDecimal: "700000.00",
  rationale: "Bid estimate at contract inception.",
  evidence: "eac-bid-estimate-castellan-2026-02.csv",
} as const;

interface EstimateRef {
  readonly id: string;
  readonly contractId: string;
}

interface EstimateVersionRead {
  readonly id: string;
  readonly version_no: number;
  readonly status: string;
  readonly effective_date: string;
  readonly expected_total_amount: string | null;
  readonly approval_request_id: string | null;
}

async function estimateVersions(
  page: Page,
  estimateId: string,
): Promise<readonly EstimateVersionRead[]> {
  const listed = await json<{ readonly items: readonly EstimateVersionRead[] }>(
    await new ApiClient(page.request).get(`/api/v1/estimates/${estimateId}/versions`, {
      sort: "-version_no",
      limit: 200,
    }),
  );
  return listed.items;
}

test.describe("SF-03:estimates and SF-03:estimate: the estimates of K-03 (RT-12, RT-13), persona maya", () => {
  // BUILD_SPEC CTR-25: the demo world holds no estimate (the seed owes the SCREENS §8.9 world), so
  // "SF-03:estimates maya" adds the `EAC` element of K-03 and saves version 1 through the two drawers,
  // and "SF-03:estimate maya" reads that version, submits it, withdraws the request and discards the
  // version once it is a draft again (item EST-DISCARD-1). One worker, in order. No route removes an
  // element: it stays on K-03 with its discarded version 1, and the crawl opens RT-13 on it
  // (crawl.spec.ts LEFT_BY_SCREENS).
  test.describe.configure({ mode: "serial" });
  let element: EstimateRef | null = null;

  test("SF-03:estimates maya", async ({ personas, screens, a11y }) => {
    test.setTimeout(240_000);
    const page = await personas.page("maya");
    const api = new ApiClient(page.request);
    const k03 = await contractIdOf(page, K03);
    const listed = await json<{ readonly items: readonly { readonly id: string }[] }>(
      await api.get(`/api/v1/contracts/${k03}/estimates`, { limit: 200 }),
    );
    expect(listed.items, "the demo world seeds no estimate on K-03 (SCREENS §8.9 is owed)").toEqual(
      [],
    );

    await page.goto(`/contracts/${k03}/estimates?${AVM_US_CONTEXT}`);
    await expect(page.getByTestId("SF-03-identifier")).toContainText(K03);
    const tab = page
      .getByRole("navigation", { name: `${K03} sections` })
      .getByRole("link", { name: /^Estimates/ });
    await expect(tab).toHaveAttribute("aria-current", "page");
    // SCREENS §8.7: the empty list and the pane without a selection.
    await expect(
      page.getByRole("heading", { level: 3, name: "No estimated elements" }),
    ).toBeVisible();
    await expect(
      page.getByText("Select an estimated element to see its versions and evidence."),
    ).toBeVisible();

    await test.step("Add estimated element: the EAC of the contract", async () => {
      await page
        .getByRole("searchbox", { name: "Filter estimates" })
        .locator("xpath=..")
        .getByRole("button", { name: "Add estimated element" })
        .click();
      const drawer = page.getByRole("dialog", { name: "Add estimated element" });
      await drawer.getByRole("combobox", { name: "Kind" }).click();
      await page.getByRole("option", { name: "Estimated total costs" }).click();
      await drawer.getByRole("textbox", { name: "Element code" }).fill(K03_EAC.code);
      // The kind proposes its method.
      await expect(drawer.getByRole("combobox", { name: "Method" })).toContainText("Cost build-up");
      await drawer.getByRole("button", { name: "Add element" }).click();
    });

    // SCREENS §8.4: "Add element", then the version drawer opens for version 1.
    const drawer = page.getByRole("dialog", { name: `New estimate version · ${K03_EAC.code}` });
    await expect(drawer).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("SF-03-drawer-estimate-version")).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`/contracts/${k03}/estimates/[0-9a-f-]{36}\\?`));
    const created = await json<{
      readonly items: readonly { readonly id: string; readonly element_code: string }[];
    }>(await api.get(`/api/v1/contracts/${k03}/estimates`, { limit: 200 }));
    const added = created.items.find((item) => item.element_code === K03_EAC.code);
    if (added === undefined) {
      throw new Error("the element drawer created no EAC element on K-03");
    }
    element = { id: added.id, contractId: k03 };

    await test.step("version 1: saved as a draft with its evidence, then previewed", async () => {
      await drawer.getByRole("textbox", { name: "Effective date" }).fill(K03_EAC.effective);
      await drawer
        .getByRole("textbox", { name: "Estimated total costs (USD)" })
        .fill(K03_EAC.total);
      await drawer.getByRole("textbox", { name: "Rationale" }).fill(K03_EAC.rationale);
      await drawer.getByLabel("Evidence", { exact: true }).setInputFiles({
        name: K03_EAC.evidence,
        mimeType: "text/csv",
        buffer: Buffer.from("line,amount\nbid estimate,700000.00\n", "utf-8"),
      });
      const preview = drawer.getByRole("region", { name: "Preview" });
      await expect(preview.getByText("The preview runs when the draft is saved.")).toBeVisible();
      const accepted = page.waitForResponse(
        (response) =>
          response.request().method() === "POST" &&
          new URL(response.url()).pathname.endsWith("/preview"),
        { timeout: 60_000 },
      );
      await drawer.getByRole("button", { name: "Save draft" }).click();
      // The toast of the save leaves by itself after 6 s: it is read before the preview is waited for.
      const toast = page.getByText("Version 1 saved as a draft.");
      await expect(toast).toBeVisible({ timeout: 30_000 });
      await page
        .getByRole("region", { name: "Messages" })
        .getByRole("button", { name: "Dismiss message" })
        .click();
      await expect(toast).toHaveCount(0);
      const answered = await accepted;
      expect(answered.status()).toBe(202);
      // DG-FE-05: the page adopts the job by the `Location` header and leaves the body of the 202
      // unread, so the browser never reports that response as finished; the row reads the header too.
      const location = answered.headers().location ?? "";
      const jobId = /\/api\/v1\/jobs\/([0-9a-f-]{36})$/.exec(
        new URL(location, "http://127.0.0.1").pathname,
      )?.[1];
      if (jobId === undefined) {
        throw new Error(`the preview answered no job in its Location header: "${location}"`);
      }

      // The figures are the API's (E2E-02): the summary of the job, read as strings first.
      const figures = preview.getByRole("table", { name: "Before and after (USD)" });
      await expect(figures).toBeVisible({ timeout: 120_000 });
      const ended = await json<{
        readonly state: string;
        readonly result: {
          readonly summary: {
            readonly transaction_price_before: { readonly amount: string };
            readonly transaction_price_after: { readonly amount: string };
            readonly catch_up_total: { readonly amount: string };
          };
        } | null;
      }>(await api.get(`/api/v1/jobs/${jobId}`));
      expect(ended.state).toBe("SUCCEEDED");
      const summary = ended.result?.summary;
      if (summary === undefined) {
        throw new Error("the preview job answered no summary");
      }
      const price = figures.getByRole("row", { name: /^Transaction price / });
      await expect(price.getByRole("cell").nth(0)).toHaveText(
        groupedDigits(summary.transaction_price_before.amount),
      );
      await expect(price.getByRole("cell").nth(1)).toHaveText(
        groupedDigits(summary.transaction_price_after.amount),
      );
      // K-03 is a draft in the demo world: its estimate recognises nothing yet.
      expectDecimal(summary.catch_up_total.amount, "0.00");
      await expect(page.getByTestId("SF-03-estimate-preview-catch-up")).toContainText("0.00");
      await expect(drawer.getByRole("list", { name: "Attached evidence" })).toContainText(
        K03_EAC.evidence,
      );
      await preview.scrollIntoViewIfNeeded();
      await screens.capture(page, "sf-03-estimate-version", { surface: "SF-03:estimate" });
      await drawer.getByRole("button", { name: "Cancel" }).click();
      await expect(drawer).toHaveCount(0);
    });

    // RT-12: the list with the element under its kind, the key figure of its latest version, and
    // nothing selected.
    await page.goto(`/contracts/${k03}/estimates?${AVM_US_CONTEXT}`);
    const list = page.getByRole("listbox", { name: "Estimated elements" });
    await expect(page.getByTestId("SF-03-grid-estimates")).toBeVisible();
    const row = list.getByRole("option", { name: /^EAC/ });
    await expect(row).toBeVisible();
    await expect(page.getByTestId("SF-03-row-eac")).toContainText(K03_EAC.total);
    await expect(row).toContainText(`v1 · effective ${K03_EAC.effective}`);
    await expect(row).toContainText("Draft");
    await expect(list.getByText("Estimated total costs", { exact: true })).toBeVisible();
    await expect(page.getByText("1 estimated element", { exact: true })).toBeVisible();
    await expect(tab).toContainText("1");
    await expect(
      page.getByText("Select an estimated element to see its versions and evidence."),
    ).toBeVisible();
    await frameTabPanel(page, page.getByTestId("SF-03-grid-estimates"));
    await screens.capture(page, "sf-03-estimates", { surface: "SF-03:estimates" });
    await a11y.check(page, "SF-03:estimates");
  });

  test("SF-03:estimate maya", async ({ personas, screens, a11y }) => {
    test.setTimeout(240_000);
    const made = element;
    if (made === null) {
      throw new Error('"SF-03:estimates maya" left no element for this test to open');
    }
    const page = await personas.page("maya");
    const api = new ApiClient(page.request);
    try {
      await page.goto(
        `/contracts/${made.contractId}/estimates/${made.id}?${AVM_US_CONTEXT}&pane=versions`,
      );
      const pane = page.getByTestId("SF-03-pane-estimate");
      await expect(pane.getByRole("heading", { level: 2, name: K03_EAC.code })).toBeVisible();
      // No version is approved: the method shows without the lock of POL-040.
      await expect(page.getByTestId("SF-03-chip-method")).toHaveText("Cost build-up");
      await expect(pane.getByRole("img", { name: /locked$/ })).toHaveCount(0);

      // BUILD_SPEC CTR-25: the table "Versions" lists version 1 700,000.00 — the API's figure first.
      const [first] = await estimateVersions(page, made.id);
      expect(first?.version_no).toBe(1);
      expectDecimal(first?.expected_total_amount, K03_EAC.totalDecimal);
      const versions = page.getByRole("table", { name: "Versions" });
      await expect(page.getByTestId("SF-03-grid-estimate-versions")).toBeVisible();
      const version = page.getByTestId("SF-03-row-estimate-version-1");
      await expect(versions.getByRole("row")).toHaveCount(2);
      await expect(version.getByRole("rowheader")).toHaveText("1");
      await expect(version).toContainText(K03_EAC.effective);
      await expect(version).toContainText(K03_EAC.total);
      await expect(version).toContainText("Draft");
      const strip = page.getByTestId("SF-03-kpi-strip-estimate");
      await expect(strip.getByRole("heading")).toHaveText("Estimate figures of version 1 (USD)");
      await expect(page.getByTestId("SF-03-kpi-estimate-expected-total-amount")).toHaveText(
        K03_EAC.total,
      );
      await expectUnclipped(strip.locator("dd"));

      await test.step("the draft is submitted from its banner and waits for approval", async () => {
        const banner = page.getByTestId("SF-03-banner-estimate");
        await expect(banner.getByText("Version 1 is a draft.")).toBeVisible();
        await banner.getByRole("button", { name: "Submit for approval" }).click();
        const toast = page.getByText(
          /^Submitted for approval\. Request APR-\d+ is waiting for approval\.$/,
        );
        await expect(toast).toBeVisible({ timeout: 60_000 });
        // The toast would cover the lower right of the capture.
        await page
          .getByRole("region", { name: "Messages" })
          .getByRole("button", { name: "Dismiss message" })
          .click();
        await expect(toast).toHaveCount(0);
        await expect(banner.getByText("Version 1 is waiting for approval.")).toBeVisible();
        await expect(version).toContainText("Pending approval");
        const [submitted] = await estimateVersions(page, made.id);
        expect(submitted?.status).toBe("SUBMITTED");
        await expect(banner.getByRole("link", { name: "View request" })).toHaveAttribute(
          "href",
          new RegExp(`^/approvals/requests/${submitted?.approval_request_id ?? ""}\\?`),
        );
        // maya prepared the request: the banner offers its withdrawal (SCREENS §8.3).
        await expect(banner.getByRole("button", { name: "Withdraw request" })).toBeVisible();
      });
      await frameTabPanel(page, page.getByTestId("SF-03-grid-estimates"));
      await screens.capture(page, "sf-03-estimate", { surface: "SF-03:estimate" });
      await a11y.check(page, "SF-03:estimate");

      await test.step("Current version: the pending version with its stored preview and its evidence", async () => {
        await pane.getByRole("tab", { name: "Current version" }).click();
        await expect(page).not.toHaveURL(/[?&]pane=/);
        await expect(
          pane.getByText("No version is approved yet. The latest version is shown."),
        ).toBeVisible();
        const details = page.getByTestId("SF-03-estimate-version");
        await expect(details).toContainText(K03_EAC.rationale);
        // SCREENS §8.3 "its preview snapshot" is the request's (REQ-PLT-015): the API's figure first.
        const [pending] = await estimateVersions(page, made.id);
        const requestId = pending?.approval_request_id ?? "";
        const request = await json<{
          readonly impact_preview: {
            readonly summary: { readonly catch_up_total: { readonly amount: string } | null };
          } | null;
        }>(await api.get(`/api/v1/approvals/${requestId}`));
        const catchUp = request.impact_preview?.summary.catch_up_total ?? null;
        if (catchUp === null) {
          throw new Error("the request of the version answered no catch-up");
        }
        // K-03 is a draft in the demo world: its estimate recognises nothing yet.
        expectDecimal(catchUp.amount, "0.00");
        const shown = page.getByTestId("SF-03-estimate-version-catch-up");
        await expect(shown).toContainText("Catch-up");
        await expect(shown).toContainText("0.00");
        await expect(details.getByRole("link", { name: "View request" })).toHaveAttribute(
          "href",
          new RegExp(`^/approvals/requests/${requestId}\\?`),
        );
        await expect(
          details
            .getByRole("list", { name: "Attachments of version 1" })
            .getByRole("link", { name: K03_EAC.evidence }),
        ).toBeVisible();
        await frameTabPanel(page, page.getByTestId("SF-03-grid-estimates"));
        await screens.capture(page, "sf-03-estimate-current", { surface: "SF-03:estimate" });
      });

      await test.step("the preparer withdraws the request and the version can be edited again", async () => {
        const banner = page.getByTestId("SF-03-banner-estimate");
        await banner.getByRole("button", { name: "Withdraw request" }).click();
        const dialog = page.getByRole("dialog", { name: "Withdraw this request?" });
        await dialog
          .getByRole("textbox", { name: /^Comment/ })
          .fill("Screen audit row: the request is withdrawn after its capture.");
        await dialog.getByRole("button", { name: "Withdraw request" }).click();
        await expect(
          banner.getByText("Version 1 was withdrawn. Edit it to submit it again."),
        ).toBeVisible({ timeout: 30_000 });
        // The withdrawn version keeps the way to its request and is the preparer's to edit.
        await expect(banner.getByRole("link", { name: "View request" })).toBeVisible();
        await expect(banner.getByRole("button", { name: "Edit draft" })).toBeVisible();
        const [withdrawn] = await estimateVersions(page, made.id);
        expect(withdrawn?.status).toBe("WITHDRAWN");
      });

      await test.step("the withdrawn version is a draft again once it is saved, and Discard draft voids it (SCREENS §8.3; PRD SM-04)", async () => {
        const banner = page.getByTestId("SF-03-banner-estimate");
        await banner.getByRole("button", { name: "Edit draft" }).click();
        const drawer = page.getByRole("dialog", { name: `Edit version 1 · ${K03_EAC.code}` });
        await drawer.getByRole("button", { name: "Save draft" }).click();
        const saved = page.getByText("Version 1 saved as a draft.");
        await expect(saved).toBeVisible({ timeout: 30_000 });
        await page
          .getByRole("region", { name: "Messages" })
          .getByRole("button", { name: "Dismiss message" })
          .click();
        await expect(saved).toHaveCount(0);
        // The save runs the preview of the draft: it is left to end before the draft is discarded.
        await expect(
          drawer
            .getByRole("region", { name: "Preview" })
            .getByRole("table", { name: "Before and after (USD)" }),
        ).toBeVisible({ timeout: 120_000 });
        await drawer.getByRole("button", { name: "Cancel" }).click();
        await expect(drawer).toHaveCount(0);
        await expect(banner.getByText("Version 1 is a draft.")).toBeVisible({ timeout: 30_000 });

        await banner.getByRole("button", { name: "Discard draft" }).click();
        const confirm = page.getByRole("alertdialog", { name: "Discard this draft version?" });
        await expect(confirm).toBeVisible();
        await screens.capture(page, "sf-03-estimate-discard", { surface: "SF-03:estimate" });
        await confirm.getByRole("button", { name: "Discard draft" }).click();
        await expect(page.getByText("Version 1 was discarded.")).toBeVisible({ timeout: 30_000 });
        // 04 §16.14 rev 1.210: the version keeps its number, reads Void and is no longer the latest
        // one, so the element shows no draft and a new version may start.
        const [discarded] = await estimateVersions(page, made.id);
        expect(discarded?.version_no).toBe(1);
        expect(discarded?.status).toBe("VOIDED");
        await expect(page.getByTestId("SF-03-banner-estimate")).toHaveCount(0);
        await page.goto(
          `/contracts/${made.contractId}/estimates/${made.id}?${AVM_US_CONTEXT}&pane=versions`,
        );
        await expect(page.getByTestId("SF-03-row-estimate-version-1")).toContainText("Void");
        await expect(
          page
            .getByTestId("SF-03-pane-estimate")
            .getByRole("button", { name: "New estimate version" })
            .first(),
        ).not.toHaveAttribute("aria-disabled", "true");
      });
    } finally {
      // A request this row submitted never stays pending, whatever failed before its withdrawal.
      const [left] = await estimateVersions(page, made.id);
      if (left?.status === "SUBMITTED") {
        const withdrawn = await api.command(
          "POST",
          `/api/v1/estimate-versions/${left.id}/withdraw`,
          {
            comment: "Screen audit row: the request is withdrawn.",
          },
        );
        expect(withdrawn.ok(), await withdrawn.text()).toBe(true);
      }
    }
  });
});

test.describe("SF-03:history History tab (RT-18 /contracts/:contractId/history), persona maya", () => {
  test("SF-03:history maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    const k02 = await contractIdOf(page, K02);
    await page.goto(`/contracts/${k02}/history?${AVM_US_CONTEXT}`);
    await expect(
      page
        .getByRole("navigation", { name: `${K02} sections` })
        .getByRole("link", { name: "History" }),
    ).toHaveAttribute("aria-current", "page");
    const views = page.getByRole("radiogroup", { name: "History view" });
    await expect(views.getByRole("radio", { name: "Activity" })).toBeChecked();
    // maya holds audit.read, so the third view is offered (SCREENS §4.7).
    await expect(views.getByRole("radio", { name: "Audit trail" })).toBeVisible();
    const activity = page.getByRole("list", { name: "Activity" });
    await expect(activity).toBeVisible();
    // Ruling R-93 (b): no chip "Imports" until the history route answers items of kind IMPORT.
    await expect(
      page.getByRole("radiogroup", { name: "Activity type" }).getByRole("radio"),
    ).toHaveText(["All", "Changes", "Approvals", "Calculations"]);
    // The seeded booking of K-02 by maya, with its effective date (PRD §2.7 WLD-K-02).
    await expect(
      activity
        .getByRole("listitem")
        .filter({ hasText: "booked the contract, effective 01 Jan 2026" }),
    ).toHaveCount(1);

    // "Versions": two selected versions compare as a field diff (REQ-CON-014).
    await views.getByRole("radio", { name: "Versions" }).click();
    await expect(page).toHaveURL(/[?&]view=versions(&|$)/);
    const section = page.getByTestId("SF-03-grid-versions");
    const grid = section.getByRole("grid", { name: "Contract versions" });
    await expect(grid).toBeVisible();
    const versions = await json<{
      readonly items: readonly { readonly version_no: number }[];
    }>(
      await new ApiClient(page.request).get(`/api/v1/contracts/${k02}/versions`, {
        book: "ASC606",
        limit: 2,
      }),
    );
    const [later, earlier] = versions.items.map((item) => item.version_no);
    expect(later, "K-02 holds at least two versions (CTR-20)").toBeDefined();
    expect(earlier, "K-02 holds at least two versions (CTR-20)").toBeDefined();
    const compare = section.getByRole("button", { name: "Compare versions" });
    await expect(compare).toHaveAttribute("aria-disabled", "true");
    await expect(
      page.getByText("Select two versions to compare.").filter({ visible: true }),
    ).toHaveCount(1);
    await grid.getByRole("checkbox", { name: `Select version ${String(later)}` }).check();
    await grid.getByRole("checkbox", { name: `Select version ${String(earlier)}` }).check();
    await expect(compare).not.toHaveAttribute("aria-disabled", "true");
    await compare.click();
    const diff = page.getByRole("table", {
      name: `Changes from version ${String(earlier)} to version ${String(later)}`,
    });
    await expect(diff).toBeVisible();
    await expect(page.getByTestId("SF-03-diff")).toBeVisible();
    await expect(
      diff.getByRole("columnheader", { name: `Version ${String(earlier)}`, exact: true }),
    ).toBeVisible();
    // D-12: a signed position is never a row of the comparison. Ruling R-93 (c): no Delta column
    // until the compare route answers the difference.
    await expect(diff).not.toContainText(/position/i);
    await expect(diff.getByRole("columnheader", { name: "Delta" })).toHaveCount(0);
    await frameTabPanel(page, page.getByRole("heading", { level: 2, name: "History" }));
    await screens.capture(page, "sf-03-history", { surface: "SF-03:history" });
    await a11y.check(page, "SF-03:history");

    await test.step("REQ-UX-004 the audit trail of the contract", async () => {
      await views.getByRole("radio", { name: "Audit trail" }).click();
      await expect(page).toHaveURL(/[?&]view=audit(&|$)/);
      await expect(page.getByTestId("SF-03-pane-audit")).toBeVisible();
      await expect(
        page.getByTestId("SF-03-pane-audit").getByRole("list", { name: "Activity" }),
      ).toBeVisible();
    });
  });
});

test.describe("SF-03:new and SF-03:edit Draft contract form (RT-09 /contracts/new, RT-19 /contracts/:contractId/edit), persona maya", () => {
  // BUILD_SPEC CTR-24: "SF-03:edit maya" opens the draft "SF-03:new maya" saves, so the two run in order
  // in one worker. They stand after the read-only SF-03 rows: a contract created while "SF-02 maya"
  // compares its two readings of the list total would move the second one.
  test.describe.configure({ mode: "serial" });
  let savedDraft: { readonly id: string; readonly externalId: string } | null = null;

  test("SF-03:new maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    await page.goto(`/contracts/new?${AVM_US_CONTEXT}`);
    const root = page.getByTestId("SF-03-new-page");
    await expect(root.getByRole("heading", { level: 1, name: "New contract" })).toBeVisible();
    const section = page.getByTestId("SF-03-grid-lines");
    const grid = section.getByRole("grid", { name: "Contract lines" });
    await expect(grid).toBeVisible();
    // SCREENS §4.10 empty form: nothing entered but "Commercial substance" and one line keyed O1.
    await expect(page.getByRole("textbox", { name: "External id" })).toHaveValue("");
    await expect(page.getByRole("checkbox", { name: "Commercial substance" })).toBeChecked();
    await expect(grid.getByRole("textbox", { name: "Obligation key, line 1" })).toHaveValue("O1");
    await expect(section.getByText("1 line", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Save draft" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Save and submit for activation" }),
    ).toBeVisible();
    await expect(page.getByRole("group", { name: "Accounting context" })).toContainText("AVM-US");
    await screens.capture(page, "sf-03-new", { surface: "SF-03:new" });
    await a11y.check(page, "SF-03:new");

    await test.step("REQ-CON-018 a draft with one AVM-PLAT-100 line is saved and opens in SF-03", async () => {
      const externalId = `E2E-DRAFT-${randomUUID().slice(0, 8).toUpperCase()}`;
      await page.getByRole("textbox", { name: "External id" }).fill(externalId);
      // PRD §2.6 WLD-C-01 Pellworth, picked from the customers on file.
      await page.getByRole("combobox", { name: "Customer" }).fill("Pellworth");
      await page
        .getByRole("listbox", { name: "Customer" })
        .getByRole("option", { name: /^Pellworth Logistics/ })
        .click();
      await page.getByRole("combobox", { name: "Contracting entity" }).click();
      await page
        .getByRole("listbox", { name: "Contracting entity" })
        .getByRole("option", { name: /^AVM-US / })
        .click();
      // The entity's functional currency is offered as the contract currency.
      await expect(page.getByRole("combobox", { name: "Currency" })).toContainText("USD");
      await expect(grid.getByRole("columnheader", { name: "Total price (USD)" })).toBeVisible();
      // An inception date inside the first open period (Sep 2026): the draft computes at once.
      await page.getByRole("textbox", { name: "Inception date" }).fill("2026-09-01");

      await grid.getByRole("combobox", { name: "Product, line 1" }).fill("AVM-PLAT-100");
      await section
        .getByRole("listbox", { name: "Product, line 1" })
        .getByRole("option", { name: /^AVM-PLAT-100 / })
        .click();
      const price = grid.getByRole("textbox", { name: "Total price, line 1" });
      await price.fill("120000");
      await grid.getByRole("textbox", { name: "Start date, line 1" }).fill("2026-09-01");
      // DS-CMP-21: leaving the amount echoes it at the currency's minor unit.
      await expect(price).toHaveValue("120,000.00");
      await grid.getByRole("textbox", { name: "End date, line 1" }).fill("2027-08-31");

      // DS-CMP-10 in the browser: a printable character on a cell starts editing and replaces the
      // value; Enter commits and returns to the cell.
      const quantityCell = grid.locator('[data-column="quantity"]').first();
      const quantity = grid.getByRole("textbox", { name: "Quantity, line 1" });
      await quantity.fill("9");
      await page.keyboard.press("F2");
      await expect(quantityCell).toBeFocused();
      await page.keyboard.type("1");
      await expect(quantity).toBeFocused();
      await expect(quantity).toHaveValue("1");
      await page.keyboard.press("Enter");
      await expect(quantityCell).toBeFocused();
      // The arrows move by cell; the grid is one tab stop.
      await page.keyboard.press("ArrowRight");
      await expect(grid.locator('[data-column="totalPrice"]').first()).toBeFocused();
      await expect(grid.locator('[tabindex="0"]')).toHaveCount(1);

      await section.scrollIntoViewIfNeeded();
      await screens.capture(page, "sf-03-new-lines", { surface: "SF-03:new" });

      await page.getByRole("button", { name: "Save draft" }).click();
      await expect(page).toHaveURL(/\/contracts\/[0-9a-f-]{36}\/obligations\?entity=AVM-US/);
      await expect(page.getByText("Draft saved.")).toBeVisible();
      await expect(page.getByTestId("SF-03-identifier")).toContainText(externalId);
      const contractId = new URL(page.url()).pathname.split("/")[2] ?? "";
      const saved = await json<{
        readonly status: string;
        readonly external_id: string;
        readonly source_system: string;
      }>(await new ApiClient(page.request).get(`/api/v1/contracts/${contractId}`));
      expect(saved).toMatchObject({
        status: "DRAFT",
        external_id: externalId,
        source_system: "MANUAL_UI",
      });
      const booked = await json<{
        readonly items: readonly {
          readonly obligation_key: string;
          readonly product: { readonly code: string };
          readonly current: { readonly stated_price: { readonly amount: unknown } };
        }[];
      }>(
        await new ApiClient(page.request).get(`/api/v1/contracts/${contractId}/obligations`, {
          book: "ASC606",
        }),
      );
      expect(booked.items.map((item) => [item.obligation_key, item.product.code])).toEqual([
        ["O1", "AVM-PLAT-100"],
      ]);
      expectDecimal(booked.items[0]?.current.stated_price.amount, "120000.00");
      savedDraft = { id: contractId, externalId };
    });
  });

  test("SF-03:edit maya", async ({ personas, screens, a11y }) => {
    const draft = savedDraft;
    if (draft === null) {
      throw new Error('"SF-03:new maya" saved no draft for this test to open');
    }
    const page = await personas.page("maya");
    const client = new ApiClient(page.request);
    const workbench = new RegExp(`/contracts/${draft.id}/obligations\\?entity=AVM-US`);
    const headOf = async (): Promise<number> =>
      (
        await json<{ readonly head_stream_version: number }>(
          await client.get(`/api/v1/contracts/${draft.id}`),
        )
      ).head_stream_version;
    const statedPrice = async (): Promise<unknown> =>
      (
        await json<{
          readonly items: readonly {
            readonly current: { readonly stated_price: { readonly amount: unknown } };
          }[];
        }>(await client.get(`/api/v1/contracts/${draft.id}/obligations`, { book: "ASC606" }))
      ).items[0]?.current.stated_price.amount;
    const replaceRequest = () =>
      page.waitForRequest(
        (request) =>
          request.method() === "POST" &&
          new URL(request.url()).pathname === `/api/v1/contracts/${draft.id}/replace-draft`,
      );

    // SCREENS §4.1.6: the workbench of a draft offers "Edit draft".
    await page.goto(`/contracts/${draft.id}/obligations?${AVM_US_CONTEXT}`);
    await expect(page.getByTestId("SF-03-identifier")).toContainText(draft.externalId);
    await page.getByRole("button", { name: "Edit draft" }).click();
    await expect(page).toHaveURL(new RegExp(`/contracts/${draft.id}/edit\\?entity=AVM-US`));
    const root = page.getByTestId("SF-03-edit-page");
    await expect(root.getByRole("heading", { level: 1, name: "Edit draft" })).toBeVisible();
    const section = page.getByTestId("SF-03-grid-lines");
    const grid = section.getByRole("grid", { name: "Contract lines" });
    await expect(grid).toBeVisible();
    // The form holds the draft as "SF-03:new maya" saved it; the external id, the contracting entity
    // and the currency stay as booked (04 §16.1).
    const externalId = page.getByRole("textbox", { name: "External id" });
    await expect(externalId).toHaveValue(draft.externalId);
    await expect(externalId).toHaveAttribute("readonly", "");
    await expect(page.getByRole("combobox", { name: "Customer" })).toHaveValue(
      /^Pellworth Logistics Inc\. \(Demo\)/,
    );
    await expect(page.getByRole("textbox", { name: "Contracting entity" })).toHaveValue(/^AVM-US /);
    await expect(page.getByRole("textbox", { name: "Currency" })).toHaveValue("USD");
    await expect(page.getByRole("textbox", { name: "Inception date" })).toHaveValue("01 Sep 2026");
    await expect(grid.getByRole("textbox", { name: "Obligation key, line 1" })).toHaveValue("O1");
    await expect(grid.getByRole("combobox", { name: "Product, line 1" })).toHaveValue(
      /^AVM-PLAT-100 /,
    );
    const price = grid.getByRole("textbox", { name: "Total price, line 1" });
    await expect(price).toHaveValue("120,000.00");
    await expect(grid.getByRole("textbox", { name: "Start date, line 1" })).toHaveValue(
      "01 Sep 2026",
    );
    await expect(grid.getByRole("textbox", { name: "End date, line 1" })).toHaveValue(
      "31 Aug 2027",
    );
    await screens.capture(page, "sf-03-edit", { surface: "SF-03:edit" });
    await a11y.check(page, "SF-03:edit");

    await test.step("04 §16.1 Save draft replaces the draft with the head the form was read at", async () => {
      const head = await headOf();
      await price.fill("132000");
      const replaced = replaceRequest();
      await page.getByRole("button", { name: "Save draft" }).click();
      expect((await replaced).headers()["if-match"]).toBe(`"s${String(head)}"`);
      await expect(page).toHaveURL(workbench);
      await expect(page.getByText("Draft saved.")).toBeVisible();
      // The earlier booking is voided and the new one appended: two events on the stream.
      expect(await headOf()).toBe(head + 2);
      expectDecimal(await statedPrice(), "132000.00");
    });

    await test.step("rulings R-89, R-93 a refused activation opens the draft at step 1", async () => {
      await page.goto(`/contracts/${draft.id}/edit?${AVM_US_CONTEXT}`);
      await expect(price).toHaveValue("132,000.00");
      await price.fill("144000");
      await page.getByRole("button", { name: "Save and submit for activation" }).click();
      // The draft is saved; activation waits for the Step 1 review of a new manual contract.
      await expect(page).toHaveURL(workbench);
      await expect(page).toHaveURL(/[?&]step=1(&|$)/);
      const refused = page.getByText(
        "Draft saved. Not submitted: record the Step 1 review first.",
        { exact: true },
      );
      await expect(refused).toBeVisible();
      // DS-CMP-22: a toast holds two lines, so the message is read whole, not clamped.
      expect(await refused.evaluate((node) => node.scrollHeight <= node.clientHeight + 1)).toBe(
        true,
      );
      await expect(page.getByTestId("SF-03-tracker-step-1")).toHaveAttribute(
        "aria-expanded",
        "true",
      );
      expectDecimal(await statedPrice(), "144000.00");
      const saved = await json<{ readonly status: string }>(
        await client.get(`/api/v1/contracts/${draft.id}`),
      );
      expect(saved.status).toBe("DRAFT");
    });

    await test.step("ruling R-93 (a) a draft changed after it was booked is not edited here", async () => {
      // A memo update follows the booking (04 §16.1 `update-memos`, as maya through the API).
      const updated = await page.request.fetch(`/api/v1/contracts/${draft.id}/update-memos`, {
        method: "POST",
        headers: {
          "X-CSRF-Token": await client.csrfToken(),
          "Idempotency-Key": randomUUID(),
          Origin: webOrigin(),
          "If-Match": `"s${String(await headOf())}"`,
        },
        data: { memo_1: "Renewal desk", comment: "Memo for the renewal desk" },
      });
      expect(updated.status(), await updated.text()).toBe(200);
      await page.goto(`/contracts/${draft.id}/edit?${AVM_US_CONTEXT}`);
      await expect(
        root.getByRole("heading", { level: 2, name: "Changed after it was booked" }),
      ).toBeVisible();
      await expect(
        root.getByText("This draft was changed after it was booked; it cannot be edited here yet."),
      ).toBeVisible();
      await expect(page.getByTestId("SF-03-grid-lines")).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Save draft" })).toHaveCount(0);
      await root.getByRole("button", { name: "Back to the contract" }).click();
      await expect(page).toHaveURL(workbench);
    });
  });
});

/**
 * PRD WLD-X-02 (SCREENS §4.3 sample world): the K-01 O1 normal schedule line of Sep 2026, 9,764.38,
 * whose `explain` parameter opens the Explain panel capture (SCREENS §0.12).
 */
async function k01ScheduleLine(
  page: Page,
): Promise<{ readonly contractId: string; readonly explainPath: string }> {
  const contractId = await contractIdOf(page, K01);
  const client = new ApiClient(page.request);
  const listed = await json<{
    readonly items: readonly {
      readonly id: string;
      readonly obligation_key: string | null;
      readonly line_type: string;
      readonly amount: { readonly amount: string };
    }[];
  }>(
    await client.get("/api/v1/schedule-lines", {
      contract: contractId,
      schedule_kind: "REVENUE",
      book: "ASC606",
      from_period: "FY2026-P09",
      to_period: "FY2026-P09",
      limit: 200,
    }),
  );
  const line = listed.items.find(
    (item) => item.obligation_key === "O1" && item.line_type === "NORMAL",
  );
  expect(line, `${K01} O1 FY2026-P09 normal schedule line`).toBeDefined();
  expect(line?.amount.amount).toBe("9764.38");
  const explain = `schedule_line~${line?.id ?? ""}~amount~FY2026-P09`;
  return {
    contractId,
    explainPath: `/contracts/${contractId}/schedules?${AVM_US_CONTEXT}&explain=${explain}`,
  };
}

/** SCREENS §6.3: the sections of an engine figure's explanation, in panel order. */
const EXPLAIN_SECTIONS = [
  "Narrative",
  "Formula",
  "Inputs",
  "Calculation steps",
  "Source records",
  "Versions",
  "History",
] as const;

test.describe("Explain panel (placement on SF-03, URL parameter explain), persona maya", () => {
  test("Explain panel maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    const { explainPath } = await k01ScheduleLine(page);
    await page.goto(explainPath);
    const panel = page.getByTestId("SF-03-explain");
    await expect(panel).toBeVisible();
    // SCREENS §6.3 row 1 "<measure label> · <period label>"; §6.7 hook by the figure name.
    await expect(page.getByRole("complementary", { name: /^Amount · / })).toBeVisible();
    // The header value; the History section repeats it for the latest contract version.
    await expect(panel.getByText(/^USD\s9,764\.38$/).first()).toHaveClass(/text-kpi/);
    for (const section of EXPLAIN_SECTIONS) {
      await expect(panel.getByRole("heading", { level: 3, name: section })).toBeVisible();
    }
    await expect(panel.getByRole("button", { name: "Verify" })).toBeVisible();
    await expect(panel.getByRole("link", { name: "Open calculation trace" })).toBeVisible();
    // The host schedule has loaded beside the docked panel (DS-CMP-15 reflow at 1440 px).
    await expect(
      page
        .getByTestId("SF-03-grid-revenue-schedule")
        .getByRole("row")
        .filter({ hasText: "9,764.38" })
        .first(),
    ).toBeVisible();
    await screens.capture(page, "explain-panel", { surface: "Explain panel" });
    await a11y.check(page, "Explain panel");
  });
});

test.describe("X:trace Calculation trace (RT-96 /trace/:calcTraceId), persona maya", () => {
  test("X:trace maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    const { explainPath } = await k01ScheduleLine(page);
    await page.goto(explainPath);
    await page
      .getByTestId("SF-03-explain")
      .getByRole("link", { name: "Open calculation trace" })
      .click();
    await expect(page).toHaveURL(/\/trace\/[0-9a-f-]{36}\?node=.+$/);
    await expect(page.getByRole("heading", { level: 1, name: "Calculation trace" })).toBeVisible();
    const grid = page
      .getByTestId("X-grid-trace")
      .getByRole("treegrid", { name: "Calculation trace" });
    await expect(grid).toBeVisible();
    // `?node=` expands the path to the figure's node and selects it.
    const selected = grid.locator('[role="row"][aria-selected="true"]');
    await expect(selected).toHaveCount(1);
    await expect(selected).toContainText("9764.38");
    await screens.capture(page, "x-trace", { surface: "X:trace" });
    await a11y.check(page, "X:trace");
  });
});

/**
 * BLK-10 of AVM-US Sep 2026 in one book as the API answers it: the `JOURNAL_RUN_NOT_CALCULATED` count of
 * the cockpit and the number of journal runs of the period that are not cancelled.
 */
async function journalRunMissing(
  request: APIRequestContext,
  book: "ASC606" | "IFRS15",
): Promise<{ readonly count: number; readonly runs: number }> {
  const periods = await json<{
    readonly items: readonly {
      readonly id: string;
      readonly period: { readonly period_key: string };
    }[];
  }>(await request.get("/api/v1/periods", { params: { entity: "AVM-US", book, limit: 200 } }));
  const september = periods.items.find((item) => item.period.period_key === "FY2026-P09");
  if (september === undefined) {
    throw new Error(`GET /periods lists no AVM-US ${book} FY2026-P09 period`);
  }
  const cockpit = await json<{
    readonly derived_blockers: readonly { readonly code: string; readonly count: number }[];
  }>(await request.get(`/api/v1/periods/${september.id}/cockpit`));
  const derived = cockpit.derived_blockers.find(
    (item) => item.code === "JOURNAL_RUN_NOT_CALCULATED",
  );
  if (derived === undefined) {
    throw new Error("the cockpit names no JOURNAL_RUN_NOT_CALCULATED blocker (04 E-122)");
  }
  const runs = await json<{ readonly items: readonly { readonly state: string }[] }>(
    await request.get("/api/v1/journal-runs", {
      params: { entity: "AVM-US", period: "FY2026-P09", book, limit: 200 },
    }),
  );
  return {
    count: derived.count,
    runs: runs.items.filter((item) => item.state !== "cancelled").length,
  };
}

/** API-S-Period `id` of AVM-US Sep 2026 in the ASC 606 book: what `blocking` names (04 §16.14). */
async function avmUsSeptemberId(request: APIRequestContext): Promise<string> {
  const periods = await json<{
    readonly items: readonly {
      readonly id: string;
      readonly period: { readonly period_key: string };
    }[];
  }>(
    await request.get("/api/v1/periods", {
      params: { entity: "AVM-US", book: "ASC606", limit: 200 },
    }),
  );
  const september = periods.items.find((item) => item.period.period_key === "FY2026-P09");
  if (september === undefined) {
    throw new Error("GET /periods lists no AVM-US ASC606 FY2026-P09 period");
  }
  return september.id;
}

/**
 * BUILD_SPEC CLO-26 under R-RC-1 (SPRINT-vabc §3.2, §6.2; L6-5-Q-2): no seeded close history and no
 * NetSuite acknowledgements in the rc, so the Aug 2026 AVM-US run is calculated, submitted by `maya`,
 * approved by `priya` and exported to CSV through the API in `beforeAll`.
 */
test.describe("SF-05 Close cockpit (RT-26 /close/:entity/:book/:period, RT-100), persona maya", () => {
  // R-RC-1 (SPRINT-vabc §6.2): the seeded locked FY2026-P08 row `sf-05-locked` waits for CLO-6 and
  // CLO-22 (L7-2-Q-14).
  test("SF-05 cockpit maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    await test.step("SF-05 cockpit", async () => {
      await page.goto("/close/AVM-US/ASC606/FY2026-P09");
      await expect(
        page.getByRole("heading", { level: 1, name: "Close · AVM-US · Sep 2026 · ASC 606" }),
      ).toBeVisible();
      // WLD-T-01 seeds the 14 T-CLS-02 system gates and no custom task.
      const checklist = page.getByTestId("SF-05-grid-checklist");
      await expect(checklist.getByRole("grid", { name: "Checklist" })).toBeVisible();
      await expect(checklist).toContainText("14 gates, 0 custom tasks");
      await expect(page.getByTestId("SF-05-row-interfaces-complete").first()).toBeVisible();
      // Rows with count 0 are hidden: every listed blocker carries a positive count.
      const blockers = page
        .getByTestId("SF-05-grid-blockers")
        .getByRole("table", { name: /^Blockers \(\d+\)$/ });
      await expect(blockers).toBeVisible();
      const rows = blockers.locator("tbody tr");
      await expect(rows.first()).toBeVisible();
      const listed = await rows.count();
      for (let index = 0; index < listed; index += 1) {
        await expect(rows.nth(index).locator("td").first()).toHaveText(/^[1-9][\d,]*$/);
      }
      // BLK-10 of this context follows the API (04 API-S-PeriodCockpit `derived_blockers`, E-122): 1 and
      // listed while no journal run of the period exists, 0 and not listed once RC-SMOKE.7 of project
      // `avenmoor-serial`, which DG-E2E-02 runs first, has calculated one (SCREENS SCR-ST-20; SCREENS_B
      // §1 sample world: "after J-13.7 BLK-10 clears").
      const missing = await journalRunMissing(page.request, "ASC606");
      expect(missing.count).toBe(missing.runs === 0 ? 1 : 0);
      await expect(page.getByTestId("SF-05-row-journal-run-missing")).toHaveCount(missing.count);
      await expect(page.getByTestId("SF-05-kpi-days-to-close").locator("dd")).toHaveCount(3);
      await screens.capture(page, "sf-05-open", { surface: "SF-05" });
      await a11y.check(page, "SF-05");
    });
    await test.step("SF-05 BLK-10 Journal run not calculated", async () => {
      // The J-13.1 figure where no journey has calculated a run: the same entity and period in the
      // IFRS 15 book. The check first as the API answers (E2E-02), then the row.
      expect(await journalRunMissing(page.request, "IFRS15")).toEqual({ count: 1, runs: 0 });
      await page.goto("/close/AVM-US/IFRS15/FY2026-P09");
      await expect(
        page.getByRole("heading", { level: 1, name: "Close · AVM-US · Sep 2026 · IFRS 15" }),
      ).toBeVisible();
      await expect(
        page.getByTestId("SF-05-row-journal-run-missing").locator("td").first(),
      ).toHaveText("1");
    });
    await test.step("SF-05 BLK-02 opens the queue on the list it counts", async () => {
      // E2E-02, the API first: the id of the period, which the link and the queue's read name.
      const periodId = await avmUsSeptemberId(page.request);
      const target = `/data/exceptions?blocking=${periodId}`;
      await page.goto("/close/AVM-US/ASC606/FY2026-P09");
      const blockers = page
        .getByTestId("SF-05-grid-blockers")
        .getByRole("table", { name: /^Blockers \(\d+\)$/ });
      await expect(blockers).toBeVisible();
      // BLK-02 is listed while an item other than a missing reassessment holds the lock, a count the
      // rows that run beside this one move: its link is read where this world lists the row. It names
      // the period by its id and no entity, period or status (SCREENS_B §1.1 rev 1.66).
      for (const link of await blockers
        .getByTestId("SF-05-row-exceptions")
        .getByRole("link")
        .all()) {
        await expect(link).toHaveAttribute("href", target);
      }
      // The queue at that address (SCREENS §13.4 rev 1.50): its read passes `blocking` through, the
      // list is the one the API answers, and the queue says that it is cut down.
      const answered = page.waitForResponse((response) => {
        const url = new URL(response.url());
        return (
          response.request().method() === "GET" &&
          url.pathname === "/api/v1/exceptions" &&
          url.searchParams.get("blocking") === periodId &&
          url.searchParams.getAll("status").join() === "OPEN,IN_PROGRESS" &&
          url.searchParams.get("limit") === "200"
        );
      });
      await page.goto(target);
      const read = await answered;
      expect(read.status()).toBe(200);
      const total = Number(read.headers()["x-erev-total-count"]);
      expect(Number.isInteger(total)).toBe(true);
      await expect(page.getByRole("heading", { level: 1, name: "Exceptions" })).toBeVisible();
      const banner = page.getByTestId("SF-11-banner-blocking");
      await expect(banner).toContainText(
        "Showing the exceptions that hold the lock of one period.",
      );
      await expect(
        page
          .getByTestId("SF-11-grid-exceptions")
          .getByText(total === 1 ? "1 exception" : `${countText(total)} exceptions`, {
            exact: true,
          }),
      ).toBeVisible();
      await screens.capture(page, "sf-11-blocking", { surface: "SF-11" });
      await a11y.check(page, "SF-11", { state: "blocking" });
      // "Show all exceptions" drops the parameter and nothing else.
      await banner.getByRole("button", { name: "Show all exceptions" }).click();
      await expect(banner).toHaveCount(0);
      await expect(page).not.toHaveURL(/[?&]blocking=/);
      await expect(page).toHaveURL(/[?&]f\.status=in:OPEN,IN_PROGRESS(&|$)/);
    });
  });

  // Lane F-CLO-WEB item 1b: the periods of AVM-UK, which no other row of this file moves. A period is
  // submitted for lock only when no earlier period of its entity and book is postable (PRD BR-CLS-08), and
  // the demo world keeps the periods of 2026 open until its close history is seeded (WLD-P-02): Sep 2026
  // waits for the earliest of them, and the close gates are met there. Each period is left open again, so
  // a repeated run in the same world starts from the same state.
  test("SF-05 submit for lock maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    const readPeriods = async (): Promise<readonly ClosePeriodRef[]> => {
      const listed = await json<{ readonly items: readonly ClosePeriodRef[] }>(
        await page.request.get("/api/v1/periods", {
          params: { entity: "AVM-UK", book: "ASC606", limit: 200 },
        }),
      );
      return [...listed.items].sort((left, right) =>
        left.period.start_date.localeCompare(right.period.start_date),
      );
    };
    const periods = await readPeriods();
    const september = periods.find((item) => item.period.period_key === "FY2026-P09");
    const first = periods.find((item) => ["open", "closing", "reopened"].includes(item.state));
    if (september === undefined || first === undefined) {
      throw new Error("GET /periods lists no postable AVM-UK ASC606 period, or no FY2026-P09");
    }
    const startSoftClose = (label: string) => startSoftCloseOf(page, label);
    const endSoftClose = (label: string) =>
      endSoftCloseOf(page, label, "Lock submission refused; the close continues.");

    if (first.id !== september.id) {
      await test.step("SF-05 submit for lock waits for the earlier period (BR-CLS-08, ERR-65)", async () => {
        await page.goto("/close/AVM-UK/ASC606/FY2026-P09");
        await expect(
          page.getByRole("heading", { level: 1, name: "Close · AVM-UK · Sep 2026 · ASC 606" }),
        ).toBeVisible();
        await startSoftClose("Sep 2026");
        // The command's message arrives after the banner. Once it is there it is dismissed, so that
        // the captures show the page without it.
        await expect(page.getByText("Soft close started for AVM-UK Sep 2026.")).toBeVisible();
        await dismissToasts(page);
        // The cockpit knows the order from its read of the periods: the action is offered, disabled,
        // with the reason and the way to the period that is locked first.
        const submit = page.getByRole("button", { name: "Submit for lock" });
        await expect(submit).toHaveAttribute("aria-disabled", "true");
        const reason = page.getByTestId("SF-05-banner-lock-unavailable");
        await expect(reason).toContainText(
          `Lock ${first.period.name} first. An earlier period of AVM-UK in book ASC 606 is not closed.`,
        );
        await expect(
          reason.getByRole("link", { name: `Go to ${first.period.name}` }),
        ).toHaveAttribute(
          "href",
          new RegExp(`^/close/AVM-UK/ASC606/${first.period.period_key}\\?`),
        );
        // Playwright does not press a control that says it is disabled; forced, the press reaches the
        // button, which opens nothing (SCR-PERM-03).
        await submit.click({ force: true });
        await expect(page.getByRole("dialog", { name: "Submit Sep 2026 for lock" })).toHaveCount(0);
        // The press leaves the pointer and the focus on the control, which shows its reason as a
        // tooltip over the header: both leave it, so the capture shows the reason line itself.
        await submit.blur();
        await page.mouse.move(0, 0);
        await expect(page.getByRole("tooltip")).toHaveCount(0);
        // E2E-02: the API refuses the same request, naming the same period (PRD ERR-65).
        const closing = (await readPeriods()).find((item) => item.id === september.id);
        if (closing === undefined) {
          throw new Error("GET /periods no longer lists AVM-UK FY2026-P09");
        }
        expect(closing.state).toBe("closing");
        const refused = await page.request.fetch(`/api/v1/periods/${september.id}/request-lock`, {
          method: "POST",
          headers: {
            "X-CSRF-Token": await new ApiClient(page.request).csrfToken(),
            "Idempotency-Key": randomUUID(),
            Origin: webOrigin(),
            "If-Match": `"r${String(closing.row_version)}"`,
          },
          data: { certification_comment: "September 2026 close is complete and reviewed." },
        });
        const problem = await json<{ readonly type: string; readonly detail: string }>(
          refused,
          409,
        );
        expect(problem.type).toMatch(/\/earlier-period-open$/);
        expect(problem.detail).toContain(`Lock ${first.period.name} first.`);
        await screens.capture(page, "sf-05-submit-lock-order", { surface: "SF-05" });
        await a11y.check(page, "SF-05");
        await endSoftClose("Sep 2026");
      });
    }
    const label = first.period.name;
    await test.step("SF-05 submit for lock refused by name (J-13-AC-1, ERR-14)", async () => {
      await page.goto(`/close/AVM-UK/ASC606/${first.period.period_key}`);
      await expect(
        page.getByRole("heading", { level: 1, name: `Close · AVM-UK · ${label} · ASC 606` }),
      ).toBeVisible();
      await startSoftClose(label);
      await expect(page.getByText(`Soft close started for AVM-UK ${label}.`)).toBeVisible();
      await dismissToasts(page);

      await page.getByRole("button", { name: "Submit for lock" }).click();
      const dialog = page.getByRole("dialog", { name: `Submit ${label} for lock` });
      await expect(dialog.getByRole("table", { name: "Close gates" })).toBeVisible();
      await dialog
        .getByRole("textbox", { name: /^Certification comment \(required\)/ })
        .fill(`${label} close is complete and reviewed.`);
      const answered = page.waitForResponse(
        (response) =>
          response.request().method() === "POST" && response.url().endsWith("/request-lock"),
      );
      await dialog.getByRole("button", { name: "Submit for lock" }).click();
      // 04 §16.8; BS4-D-08: 409 `close-gates-failed` with one errors[] entry per failing gate.
      const refused = await answered;
      expect(refused.status()).toBe(409);
      const problem = (await refused.json()) as {
        readonly type: string;
        readonly errors: readonly { readonly rule_id: string | null }[];
      };
      expect(problem.type).toMatch(/\/close-gates-failed$/);
      expect(problem.errors.length).toBeGreaterThan(0);
      // ERR-14 on the screen: the same count, and each failing gate by its label as a link.
      const refusal = dialog.getByRole("alert");
      await expect(refusal).toContainText(
        problem.errors.length === 1
          ? "1 close gate has not passed:"
          : `${countText(problem.errors.length)} close gates have not passed:`,
      );
      await expect(refusal.getByRole("button")).toHaveCount(problem.errors.length);
      // The typed comment stays for the next attempt.
      await expect(
        dialog.getByRole("textbox", { name: /^Certification comment \(required\)/ }),
      ).toHaveValue(`${label} close is complete and reviewed.`);
      await screens.capture(page, "sf-05-submit-lock-refused", { surface: "SF-05" });
      await a11y.check(page, "SF-05");
      await dialog.getByRole("button", { name: "Cancel" }).click();
    });
    await test.step("SF-05 end soft close returns the period to open", async () => {
      await endSoftClose(label);
    });
  });

  test("SF-05:journal-preview maya", async ({ personas, screens, a11y }) => {
    const page = await personas.page("maya");
    await test.step("SF-05:journal-preview", async () => {
      // E2E-02: the check first as the API strings.
      const listed = await json<{
        readonly items: readonly {
          readonly id: string;
          readonly period: { readonly period_key: string };
        }[];
      }>(
        await page.request.get("/api/v1/periods", {
          params: { entity: "AVM-US", book: "ASC606", limit: 200 },
        }),
      );
      const august = listed.items.find((item) => item.period.period_key === "FY2026-P08");
      if (august === undefined) {
        throw new Error("GET /periods lists no AVM-US ASC606 FY2026-P08 period");
      }
      const cockpit = await json<{
        readonly journal_preview: {
          readonly balanced: boolean;
          readonly difference_functional: unknown;
        };
      }>(await page.request.get(`/api/v1/periods/${august.id}/cockpit`));
      expect(cockpit.journal_preview.balanced).toBe(true);
      expectDecimal(amountText(cockpit.journal_preview.difference_functional), "0.00");
      await page.goto("/close/AVM-US/ASC606/FY2026-P08/journal-preview");
      const check = page.getByRole("region", { name: /^Journal preview \(USD\) balanced$/ });
      await expect(check).toBeVisible();
      await expect(check.getByText("Pass", { exact: true })).toBeVisible();
      await expect(check.getByText("Balanced", { exact: true })).toBeVisible();
      await screens.capture(page, "sf-05-journal-preview", { surface: "SF-05:journal-preview" });
      await a11y.check(page, "SF-05:journal-preview");
    });
  });
});

/**
 * BUILD_SPEC CLO-25 (SCREENS_B §2.1, §2.2). The §15 rows `sf-05-reconciliations` and `sf-05-reconciliation`
 * (`priya`, AVM-US FY2026-P09: billing to subledger, and the subledger-to-GL reconciliation of J-13.11 with
 * its 250.00 difference) wait for the seeded reconciliations of the demo world. Until then the two screens
 * are reached through the product in the world as it is: `maya` generates billing to subledger for AVM-DE
 * Sep 2026, an open period that no other row of this file reads, and opens its detail; `priya` then opens
 * the same reconciliation; `maya` generates the subledger-to-GL reconciliation and attaches an uploaded
 * trial balance (BUILD_SPEC CLO-17; the demo world holds no GL connection to pull through). The preparer
 * signs in an MFA-verified session (04 §16.8); since PRD WLD-U-R2 rev 1.153 the seed enrols `maya`, so she
 * can sign. These rows were written when she held no factor and still stop at the draft, where the
 * reviewer's control has nothing to sign.
 */
const AVM_DE_CLOSE = "/close/AVM-DE/ASC606/FY2026-P09";

interface ReconciliationRef {
  readonly id: string;
  readonly reconciliation_no: string;
  readonly status: string;
  readonly is_current: boolean;
  readonly variance_count: number;
}

/** The current billing-to-subledger reconciliation of AVM-DE FY2026-P09 (04 T-CLS-06), if generated. */
async function currentBilling(request: APIRequestContext): Promise<ReconciliationRef | undefined> {
  const listed = await json<{ readonly items: readonly ReconciliationRef[] }>(
    await request.get("/api/v1/reconciliations", {
      params: {
        entity: "AVM-DE",
        book: "ASC606",
        period: "FY2026-P09",
        kind: "BILLING_TO_SUBLEDGER",
        limit: 200,
      },
    }),
  );
  return listed.items.find((item) => item.is_current);
}

/** API-S-Period of `GET /periods`, as far as the lock rows read it. */
interface ClosePeriodRef {
  readonly id: string;
  readonly state: string;
  readonly row_version: number;
  readonly period: {
    readonly period_key: string;
    readonly name: string;
    readonly start_date: string;
  };
}

/** API-S-Reconciliation of a subledger-to-GL reconciliation, as far as the rows read it. */
interface LedgerReconciliation {
  readonly id: string;
  readonly status: string;
  readonly variance_count: number;
  readonly summary: readonly { readonly currency: string; readonly account_count: number }[];
  readonly gl_connections: readonly { readonly id: string; readonly name: string }[];
  readonly trial_balance: {
    readonly source: string;
    readonly file: { readonly name: string } | null;
    readonly attached_at: string | null;
    readonly job: { readonly state: string };
  } | null;
}

/** J-13.6: starts the soft close of the cockpit's period (PRD SM-07). */
async function startSoftCloseOf(page: Page, label: string): Promise<void> {
  await page.getByRole("button", { name: "Start soft close" }).click();
  const start = page.getByRole("dialog", { name: `Start soft close for ${label}?` });
  await start.getByRole("button", { name: "Start soft close" }).click();
  await expect(page.getByTestId("SF-05-banner-soft-close")).toBeVisible();
}

/** Ends the soft close with the reason "Close restarted" and `comment`: the period is open again. */
async function endSoftCloseOf(page: Page, label: string, comment: string): Promise<void> {
  await page.getByRole("button", { name: "More close actions" }).click();
  await page.getByRole("menuitem", { name: "End soft close" }).click();
  const end = page.getByRole("alertdialog", { name: `End soft close for ${label}?` });
  await end.getByRole("combobox", { name: /^Reason/ }).click();
  await page.getByRole("option", { name: "Close restarted" }).click();
  await end.getByRole("textbox", { name: /^Comment \(required\)/ }).fill(comment);
  await end.getByRole("button", { name: "End soft close" }).click();
  await expect(page.getByTestId("SF-05-banner-soft-close")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Start soft close" })).toBeVisible();
}

/** The `period_state` id of AVM-DE ASC 606 Sep 2026 (`GET /periods`). */
async function avmDeSeptember(request: APIRequestContext): Promise<string> {
  const listed = await json<{
    readonly items: readonly {
      readonly id: string;
      readonly period: { readonly period_key: string };
    }[];
  }>(
    await request.get("/api/v1/periods", {
      params: { entity: "AVM-DE", book: "ASC606", limit: 200 },
    }),
  );
  const september = listed.items.find((item) => item.period.period_key === "FY2026-P09");
  if (september === undefined) {
    throw new Error("GET /periods lists no AVM-DE ASC606 FY2026-P09 period");
  }
  return september.id;
}

/** DS-FMT-21 count text of the en-US format locale the project runs in. */
function countText(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

test.describe("SF-05:reconciliations and SF-05:reconciliation (RT-102, RT-103), personas maya and priya", () => {
  // One worker runs both rows over the reconciliation the first one generates.
  test.describe.configure({ mode: "serial" });

  test("SF-05:reconciliations maya generates billing to subledger", async ({
    personas,
    screens,
    a11y,
  }) => {
    const page = await personas.page("maya");
    let generated: ReconciliationRef | undefined;
    await test.step("SF-05:reconciliations generated through the product (CLO-25)", async () => {
      await page.goto(`${AVM_DE_CLOSE}/reconciliations`);
      await expect(
        page.getByRole("heading", { level: 1, name: "Close · AVM-DE · Sep 2026 · ASC 606" }),
      ).toBeVisible();
      // The tab sits in the cockpit's route tabs (SCREENS_B §1).
      await expect(
        page
          .getByRole("navigation", { name: "Close of Sep 2026" })
          .getByRole("link", { name: "Reconciliations" }),
      ).toHaveAttribute("aria-current", "page");
      const region = page.getByTestId("SF-05-grid-reconciliations");
      await expect(region.getByRole("grid", { name: "Reconciliations" })).toBeVisible();
      await region.getByRole("button", { name: "Generate reconciliation" }).first().click();
      await page.getByRole("menuitem", { name: "Billing to subledger" }).click();
      // 202 API-S-Job `RECONCILIATION_GENERATE` (SB-R-06), then the toast that names the reconciliation.
      await expect(page.getByText(/^Generated REC-\d+ \(Billing to subledger\)\.$/)).toBeVisible({
        timeout: 60_000,
      });
      generated = await currentBilling(page.request);
      if (generated === undefined) {
        throw new Error("GET /reconciliations lists no current AVM-DE FY2026-P09 billing row");
      }
      expect(generated.status).toBe("DRAFT");
      const row = page.getByTestId("SF-05-row-billing-to-subledger");
      await expect(row.getByRole("link", { name: generated.reconciliation_no })).toBeVisible();
      await expect(row).toContainText("Billing to subledger");
      // E-59 `DRAFT` reads Draft; the count is the API's (E2E-02).
      await expect(row.locator('[data-column="status"]')).toContainText("Draft");
      await expect(row.locator('[data-column="variances"]')).toHaveText(
        countText(generated.variance_count),
      );
      // DS-AP-10: no header label or cell of the grid is cut off (a text test passes on a clipped line).
      await expect
        .poll(() => clippedBoxes(region.getByRole("grid", { name: "Reconciliations" })))
        .toEqual([]);
      await screens.capture(page, "sf-05-reconciliations-generated", {
        surface: "SF-05:reconciliations",
      });
      await a11y.check(page, "SF-05:reconciliations");
    });
    await test.step("SF-05:reconciliations menu lists what the API generates (XR-14)", async () => {
      // 04 §16.8 API-S-ReconciliationCreate: the rollforward kinds are report runs, so the two other
      // menu items of SCREENS_B §2.1 have no command to bind and are not listed.
      for (const kind of ["CONTRACT_BALANCE_ROLLFORWARD", "RPO_ROLLFORWARD"]) {
        const refused = await new ApiClient(page.request).command(
          "POST",
          "/api/v1/reconciliations",
          { kind, entity_code: "AVM-DE", book: "ASC606", period_key: "FY2026-P09" },
        );
        const problem = await json<{
          readonly type: string;
          readonly errors: readonly { readonly field: string | null }[];
        }>(refused, 422);
        expect(problem.type, kind).toMatch(/\/validation-failed$/);
        expect(problem.errors.map((error) => error.field)).toEqual(["kind"]);
      }
      await page
        .getByTestId("SF-05-grid-reconciliations")
        .getByRole("button", { name: "Generate reconciliation" })
        .click();
      await expect(page.getByRole("menuitem")).toHaveText([
        "Billing to subledger",
        "Subledger to GL",
      ]);
      await page.keyboard.press("Escape");
    });
    await test.step("SF-05:reconciliation draft opened from the list (CLO-25)", async () => {
      if (generated === undefined) {
        throw new Error("the generation step named no reconciliation");
      }
      await page
        .getByTestId("SF-05-row-billing-to-subledger")
        .getByRole("link", { name: generated.reconciliation_no })
        .click();
      await expect(
        page.getByRole("heading", {
          level: 1,
          name: `${generated.reconciliation_no} · Billing to subledger · Sep 2026`,
        }),
      ).toBeVisible();
      await expect(page).toHaveURL(new RegExp(`/reconciliations/${generated.id}\\?`));
      const totals = page
        .getByTestId("SF-05-grid-recon-totals")
        .getByRole("grid", { name: "Totals by account" });
      await expect(totals).toBeVisible();
      const differences = page
        .getByTestId("SF-05-grid-recon-items")
        .getByRole("grid", { name: "Differences" });
      await expect(differences).toBeVisible();
      // DS-AP-10: no header label or cell of either grid is cut off.
      await expect.poll(() => clippedBoxes(totals)).toEqual([]);
      await expect.poll(() => clippedBoxes(differences)).toEqual([]);
      // E2E-02: the variance count as the API value, then as the key figure.
      await expect(page.getByTestId("SF-05-kpi-variances").locator("dd")).toHaveText(
        countText(generated.variance_count),
      );
      // A current draft in an open period: the preparer's control, and no reviewer's (PRD SM-09).
      await expect(page.getByRole("button", { name: "Sign as preparer" })).toBeVisible();
      await expect(page.getByRole("button", { name: "Sign as reviewer" })).toHaveCount(0);
      const signoffs = page.getByRole("region", { name: "Sign-offs" });
      await expect(signoffs).toContainText("Preparer");
      await expect(signoffs).toContainText("Reviewer");
      await screens.capture(page, "sf-05-reconciliation-draft", {
        surface: "SF-05:reconciliation",
      });
      await a11y.check(page, "SF-05:reconciliation");
    });
  });

  test("SF-05:reconciliation priya reads the draft", async ({ personas, screens, a11y }) => {
    const page = await personas.page("priya");
    await test.step("SF-05:reconciliation sign-off controls of a reviewer (CLO-25)", async () => {
      const generated = await currentBilling(page.request);
      if (generated === undefined) {
        throw new Error("no current AVM-DE FY2026-P09 billing row: the generation row did not run");
      }
      await page.goto(`${AVM_DE_CLOSE}/reconciliations/${generated.id}`);
      await expect(
        page.getByRole("heading", {
          level: 1,
          name: `${generated.reconciliation_no} · Billing to subledger · Sep 2026`,
        }),
      ).toBeVisible();
      const signoffs = page.getByRole("region", { name: "Sign-offs" });
      await expect(signoffs).toContainText("Preparer");
      await expect(signoffs).toContainText("Reviewer");
      // SCR-PERM-02: `priya` holds `recon.signoff` and no `recon.prepare`, and a draft has nothing for
      // a reviewer to sign or reopen (PRD SM-09), so the record is read-only for her.
      await expect(page.getByRole("button", { name: "Sign as preparer" })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Sign as reviewer" })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "More reconciliation actions" })).toHaveCount(
        0,
      );
      await expect(page.getByRole("button", { name: "Add explanation" })).toHaveCount(0);
      // The record sets the accounting context it belongs to (the URL named none).
      const context = page.getByRole("group", { name: "Accounting context" });
      await expect(context).toContainText("AVM-DE");
      await expect(context).toContainText("Sep 2026");
      await screens.capture(page, "sf-05-reconciliation-reviewer", {
        surface: "SF-05:reconciliation",
      });
      await a11y.check(page, "SF-05:reconciliation");
      // The breadcrumb leads to the period's list, where a reviewer generates nothing.
      await page
        .getByRole("navigation", { name: "Breadcrumb" })
        .getByRole("link", { name: "Reconciliations" })
        .click();
      const region = page.getByTestId("SF-05-grid-reconciliations");
      await expect(region.getByRole("link", { name: generated.reconciliation_no })).toBeVisible();
      await expect(page.getByRole("button", { name: "Generate reconciliation" })).toHaveCount(0);
    });
  });

  // BUILD_SPEC CLO-17 through the product: the demo world holds no GL connection, so the trial balance
  // is an uploaded file; the pull is witnessed in vitest against the API's contract.
  test("SF-05:reconciliation maya attaches a trial balance", async ({
    personas,
    screens,
    a11y,
  }) => {
    const page = await personas.page("maya");
    const readLedger = async (): Promise<LedgerReconciliation> => {
      const listed = await json<{ readonly items: readonly LedgerReconciliation[] }>(
        await page.request.get("/api/v1/reconciliations", {
          params: {
            entity: "AVM-DE",
            book: "ASC606",
            period: "FY2026-P09",
            kind: "SUBLEDGER_TO_GL",
            is_current: "true",
            limit: 200,
          },
        }),
      );
      const [current] = listed.items;
      if (current === undefined) {
        throw new Error(
          "GET /reconciliations lists no current AVM-DE FY2026-P09 subledger-to-GL row",
        );
      }
      return current;
    };
    await test.step("SF-05:reconciliation subledger to GL opens in its attach state (CLO-25)", async () => {
      await page.goto(`${AVM_DE_CLOSE}/reconciliations`);
      const region = page.getByTestId("SF-05-grid-reconciliations");
      await expect(region.getByRole("grid", { name: "Reconciliations" })).toBeVisible();
      await region.getByRole("button", { name: "Generate reconciliation" }).click();
      await page.getByRole("menuitem", { name: "Subledger to GL" }).click();
      // SCREENS_B §2.1: the job ends, and the new reconciliation opens where its source is attached.
      await expect(
        page.getByRole("heading", { level: 1, name: /^REC-\d+ · Subledger to GL · Sep 2026$/ }),
      ).toBeVisible({ timeout: 60_000 });
      const ledger = await readLedger();
      expect(ledger.status).toBe("DRAFT");
      expect(ledger.trial_balance).toBeNull();
      await expect(page).toHaveURL(new RegExp(`/reconciliations/${ledger.id}\\?`));
      const attach = page.getByTestId("SF-05-attach-trial-balance");
      await expect(attach.getByRole("heading", { name: "Attach a trial balance" })).toBeVisible();
      // E2E-02: the ways to attach are the connections the API names, and the upload.
      if (ledger.gl_connections.length === 0) {
        await expect(attach).toContainText(
          "No GL connection is set up for AVM-DE. Upload a CSV of account balances.",
        );
        await expect(attach.getByRole("radiogroup")).toHaveCount(0);
      } else {
        await expect(attach.getByRole("radio")).toHaveText([
          ...ledger.gl_connections.map((connection) => `Pull from ${connection.name}`),
          "Upload CSV",
        ]);
        await attach.getByRole("radio", { name: "Upload CSV" }).click();
      }
      await expect(attach.getByRole("button", { name: "Upload and compare" })).toBeVisible();
      // Nothing is compared yet: no totals, no sign-off.
      await expect(page.getByTestId("SF-05-grid-recon-totals")).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Sign as preparer" })).toHaveCount(0);
      await screens.capture(page, "sf-05-reconciliation-attach", {
        surface: "SF-05:reconciliation",
      });
      await a11y.check(page, "SF-05:reconciliation");
    });
    await test.step("SF-05:reconciliation trial balance uploaded and compared (CLO-25)", async () => {
      const before = await readLedger();
      const functional = (
        await json<{
          readonly journal_preview: { readonly debit_functional: { readonly currency: string } };
        }>(await page.request.get(`/api/v1/periods/${await avmDeSeptember(page.request)}/cockpit`))
      ).journal_preview.debit_functional.currency;
      // 04 §16.8: the columns account, currency and amount; one closing balance in the entity's
      // functional currency is a trial balance the API compares.
      await page.getByTestId("SF-05-trial-balance-file").setInputFiles({
        name: "tb-avm-de-sep-2026.csv",
        mimeType: "text/csv",
        buffer: Buffer.from(`account,currency,amount\n2100,${functional},0.00\n`, "utf-8"),
      });
      await expect(page.getByTestId("SF-05-trial-balance-selected")).toContainText(
        "tb-avm-de-sep-2026.csv",
      );
      await page.getByRole("button", { name: "Upload and compare" }).click();
      // The request is followed on the record: every reader sees the same state.
      await expect
        .poll(async () => (await readLedger()).trial_balance?.job.state ?? null, {
          timeout: 60_000,
        })
        .toBe("SUCCEEDED");
      const ledger = await readLedger();
      expect(ledger.id).toBe(before.id);
      expect(ledger.trial_balance?.source).toBe("FILE");
      expect(ledger.trial_balance?.file?.name).toBe("tb-avm-de-sep-2026.csv");
      expect(ledger.trial_balance?.attached_at).not.toBeNull();
      const totals = page
        .getByTestId("SF-05-grid-recon-totals")
        .getByRole("grid", { name: "Totals by account" });
      await expect(totals).toBeVisible({ timeout: 30_000 });
      await expect(page.getByTestId("SF-05-attach-trial-balance")).toHaveCount(0);
      // The header names the uploaded file as the source.
      await expect(page.getByTestId("SF-05-page")).toContainText(
        "tb-avm-de-sep-2026.csv · uploaded",
      );
      // E2E-02: the figures of the strip are the API's summary and variance count.
      await expect(page.getByTestId("SF-05-kpi-variances").locator("dd")).toHaveText(
        countText(ledger.variance_count),
      );
      const [only] = ledger.summary;
      if (ledger.summary.length === 1 && only !== undefined && only.account_count > 0) {
        await expect(page.getByTestId("SF-05-kpi-accounts").locator("dd")).toHaveText(
          countText(only.account_count),
        );
      }
      const items = await json<{ readonly items: readonly unknown[] }>(
        await page.request.get(`/api/v1/reconciliations/${ledger.id}/items`, {
          params: { limit: 200 },
        }),
      );
      const differences = page
        .getByTestId("SF-05-grid-recon-items")
        .getByRole("grid", { name: "Differences" });
      if (items.items.length > 0) {
        await expect(differences).toHaveAttribute("aria-rowcount", String(items.items.length + 1));
      }
      // A compared draft is the preparer's to sign (PRD SM-09).
      await expect(page.getByRole("button", { name: "Sign as preparer" })).toBeVisible();
      await expect.poll(() => clippedBoxes(totals)).toEqual([]);
      await screens.capture(page, "sf-05-reconciliation-gl", { surface: "SF-05:reconciliation" });
      await a11y.check(page, "SF-05:reconciliation");
    });
  });
});

const AVM_US_AUGUST = "entity=AVM-US&period=FY2026-P08&book=ASC606";

/**
 * The bound of an assertion that waits for a report run the page has asked for (RV-01): the creation,
 * the worker's job and the rows. The 10 s an assertion gets by default hold on a quiet machine and not
 * on a loaded one: in the gate of f5a1df88, at a load average of 63, a creation alone answered in 3.9 s
 * and a waterfall's job took 11.3 s, and the rows SF-08:report and SF-08:dashboard failed on their
 * first run. These waits take the bound the rows give a command's job.
 */
const REPORT_RUN_WAIT = { timeout: 60_000 } as const;

interface JournalRunRef {
  readonly id: string;
  readonly run_no: string;
  readonly state: string;
  readonly approval_request_id: string | null;
  readonly created_at: string;
}

interface JournalBatchRef {
  readonly batch_no: number;
  readonly chunk_no: number;
  readonly state: string;
  readonly external_id: string;
}

/** `GET /journal-runs?entity=AVM-US&period=FY2026-P08&book=ASC606`, earliest first, cancelled runs left out. */
async function augustRuns(request: APIRequestContext): Promise<readonly JournalRunRef[]> {
  const listed = await json<{ readonly items: readonly JournalRunRef[] }>(
    await request.get("/api/v1/journal-runs", {
      params: { entity: "AVM-US", period: "FY2026-P08", book: "ASC606", limit: 50 },
    }),
  );
  return [...listed.items]
    .filter((item) => item.state !== "cancelled")
    .sort((left, right) => (left.created_at < right.created_at ? -1 : 1));
}

function amountText(value: unknown): unknown {
  return typeof value === "object" && value !== null && "amount" in value
    ? (value as { readonly amount: unknown }).amount
    : value;
}

/**
 * BUILD_SPEC CLO-24 (SCREENS_B §1.2, §1.4, §1.5). The §15 rows `sf-05-close-run` (`maya`, the seeded
 * succeeded run of AVM-US FY2026-P08), `sf-05-history` (`marcus`: lock, reopen with two decisions and
 * re-lock of WLD-P-03) and `sf-05-multi-entity` (`marcus`, the three J-13.16 runs) wait for the seeded
 * close of the demo world. Until then the three screens are reached through the product, in one row so
 * that its steps keep their order, on AVM-JP and its Sep 2026 (FY2027-P06): no other row of this file
 * closes, locks or counts that entity and period (the SF-04 row reads its schedules, which a close run
 * does not write). What the world answers there (E2E-02): the recalculation of a close run refuses the
 * three AVM-JP licences of the background data (the engine finds no SSP for them, as it did when the
 * seed booked them), so the run ends BLOCKED at "Recompute changed contracts" with three quarantined
 * contracts and posts nothing. The row shows that state, the run in the multi-entity close — where a
 * second start answers the run that has not ended — a resume, which blocks again, and the cancel that
 * leaves the period without a run that has not ended. A run that SUCCEEDS needs the quarantined
 * contracts resolved or waived: a waiver is an approval request, which the approval rows of this file
 * would see while they run beside this one, so that path belongs to a journey of the serial project.
 * AVM-DE and AVM-UK are not started: the reconciliation and lock rows read their Sep 2026.
 */
const AVM_JP_CLOSE = "/close/AVM-JP/ASC606/FY2027-P06";
const AVM_JP_CONTEXT = "entity=AVM-JP&period=FY2027-P06&book=ASC606";

/** API-S-CloseRun, as far as the row reads it (04 §16.8, T-CLS-01). */
interface CloseRunRef {
  readonly id: string;
  readonly close_run_no: string;
  readonly status: string;
  readonly current_step_code: string | null;
  readonly steps: readonly {
    readonly step_code: string;
    readonly status: string;
    readonly finished_at: string | null;
    readonly counts: Readonly<Record<string, unknown>>;
    readonly problem: { readonly title: string; readonly detail: string | null } | null;
  }[];
}

/** Closes the toasts still shown, so that a capture shows the screen and not an earlier step's message. */
async function dismissToasts(page: Page): Promise<void> {
  const buttons = page
    .getByRole("region", { name: "Messages" })
    .getByRole("button", { name: "Dismiss message" });
  for (let left = await buttons.count(); left > 0; left -= 1) {
    // A toast may leave by itself between the count and the press: the press is bounded.
    await buttons
      .first()
      .click({ timeout: 2_000 })
      .catch(() => undefined);
  }
  await expect(buttons).toHaveCount(0);
}

/** The close runs of AVM-JP ASC 606 FY2027-P06, newest first (`GET /close-runs`, default sort). */
async function avmJpCloseRuns(request: APIRequestContext): Promise<readonly CloseRunRef[]> {
  const listed = await json<{ readonly items: readonly CloseRunRef[] }>(
    await request.get("/api/v1/close-runs", {
      params: { entity: "AVM-JP", book: "ASC606", period: "FY2027-P06", limit: 50 },
    }),
  );
  return listed.items;
}

/** The one close run of AVM-JP FY2027-P06 this row starts. */
async function avmJpCloseRun(request: APIRequestContext): Promise<CloseRunRef> {
  const runs = await avmJpCloseRuns(request);
  const [run] = runs;
  if (run === undefined || runs.length !== 1) {
    throw new Error(`GET /close-runs lists ${String(runs.length)} AVM-JP FY2027-P06 runs, not one`);
  }
  return run;
}

/** `steps[RECOMPUTE_DIRTY]` of a run: its status, its counts and when it last ended. */
function recomputeStep(run: CloseRunRef): CloseRunRef["steps"][number] {
  const step = run.steps.find((item) => item.step_code === "RECOMPUTE_DIRTY");
  if (step === undefined) {
    throw new Error(`${run.close_run_no} has no RECOMPUTE_DIRTY step`);
  }
  return step;
}

/** What a run says of itself, for a failure message that names the API's answer. */
function closeRunAnswer(run: CloseRunRef) {
  return {
    status: run.status,
    step: run.current_step_code,
    problems: run.steps
      .filter((step) => step.problem !== null)
      .map(
        (step) => `${step.step_code}: ${step.problem?.title ?? ""} ${step.problem?.detail ?? ""}`,
      ),
  };
}

/** An item of the quarantined grid, as far as the row reads it (04 T-IMP-05, §16.14 rev 1.206). */
interface QuarantineRef {
  readonly exception_no: string;
  readonly code: string;
  readonly contract_external_id: string | null;
  readonly combination_group_code: string | null;
}

/**
 * The quarantined contracts of AVM-JP Sep 2026 as SF-05:close-run reads them (SCREENS_B §1.2 rev 1.66):
 * the blocking items of the engine that the period's close gates count, asked by the period's id. The
 * list holds open items only and names no entity, period or code.
 */
async function avmJpQuarantines(request: APIRequestContext): Promise<readonly QuarantineRef[]> {
  const periods = await json<{
    readonly items: readonly {
      readonly id: string;
      readonly period: { readonly period_key: string };
    }[];
  }>(
    await request.get("/api/v1/periods", {
      params: { entity: "AVM-JP", book: "ASC606", limit: 200 },
    }),
  );
  const september = periods.items.find((item) => item.period.period_key === "FY2027-P06");
  if (september === undefined) {
    throw new Error("GET /periods lists no AVM-JP ASC606 FY2027-P06 period");
  }
  const listed = await json<{ readonly items: readonly QuarantineRef[] }>(
    await request.get("/api/v1/exceptions", {
      params: { blocking: september.id, source: "ENGINE", severity: "BLOCKING", limit: 200 },
    }),
  );
  return listed.items;
}

test.describe("SF-05:close-run, SF-05:history and SF-05:multi-entity (RT-99, RT-101, RT-27), personas maya and marcus", () => {
  test("SF-05:close-run maya runs the close of AVM-JP", async ({ personas, screens, a11y }) => {
    // A soft close, a close run with its recalculation, a resume with a second one, and a cancel.
    test.setTimeout(600_000);
    const page = await personas.page("maya");
    const transitions = async () => {
      const periods = await json<{
        readonly items: readonly {
          readonly id: string;
          readonly period: { readonly period_key: string };
        }[];
      }>(
        await page.request.get("/api/v1/periods", {
          params: { entity: "AVM-JP", book: "ASC606", limit: 200 },
        }),
      );
      const september = periods.items.find((item) => item.period.period_key === "FY2027-P06");
      if (september === undefined) {
        throw new Error("GET /periods lists no AVM-JP ASC606 FY2027-P06 period");
      }
      const listed = await json<{
        readonly items: readonly {
          readonly from_state: string | null;
          readonly to_state: string;
          readonly created_by: { readonly display_name: string };
        }[];
      }>(await page.request.get(`/api/v1/periods/${september.id}/transitions`));
      return listed.items;
    };

    await test.step("SF-05:history", async () => {
      // A soft close started and ended: two state changes of the period, the second with its reason.
      await page.goto(AVM_JP_CLOSE);
      await expect(
        page.getByRole("heading", { level: 1, name: "Close · AVM-JP · Sep 2026 · ASC 606" }),
      ).toBeVisible();
      await startSoftCloseOf(page, "Sep 2026");
      await endSoftCloseOf(page, "Sep 2026", "The September cost file is not final.");
      await page
        .getByRole("navigation", { name: "Close of Sep 2026" })
        .getByRole("link", { name: "History" })
        .click();
      await expect(page).toHaveURL(/\/close\/AVM-JP\/ASC606\/FY2027-P06\/history\?/);
      const moves = await transitions();
      const [ended, started] = moves;
      if (ended === undefined || started === undefined) {
        throw new Error("GET /periods/{id}/transitions lists fewer than two state changes");
      }
      expect([started.from_state, started.to_state, ended.from_state, ended.to_state]).toEqual([
        "open",
        "closing",
        "closing",
        "open",
      ]);
      const activity = page
        .getByTestId("SF-05-timeline-transitions")
        .getByRole("list", { name: "Activity" });
      await expect(activity.getByRole("listitem")).toHaveCount(moves.length);
      await expect(activity.getByRole("listitem").nth(0)).toContainText(
        `${ended.created_by.display_name} changed the period from Soft close to Period open`,
      );
      await expect(activity.getByRole("listitem").nth(0)).toContainText(
        "Reason: Close restarted. The September cost file is not final.",
      );
      await expect(activity.getByRole("listitem").nth(1)).toContainText(
        `${started.created_by.display_name} changed the period from Period open to Soft close`,
      );
      // No lock, reopen or permanent lock in this world (R-RC-1): SCR-ST-03 of the locks.
      await expect(page.getByRole("heading", { name: "No locks yet" })).toBeVisible();
      await dismissToasts(page);
      await screens.capture(page, "sf-05-history", { surface: "SF-05:history" });
      // Measured on the captured layout: the shown columns of the locks grid hold their headers and
      // fit the room beside the activity at 1440 px (SCREENS_B §1.4; DS-AP-10).
      const locks = page.getByRole("grid", { name: "Locks" });
      await expect.poll(() => clippedBoxes(locks)).toEqual([]);
      expect(await locks.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(
        true,
      );
      await a11y.check(page, "SF-05:history");
    });

    const header = page.getByRole("region", { name: /^Close run CLS-\d+$/ });
    const blocked = page.getByTestId("SF-05-banner-close-run-blocked");
    // The ordered list carries the test id itself (SCREENS_B §1.2 "Test hooks").
    const stepList = page.getByRole("list", { name: "Close run steps" });
    const steps = stepList.getByRole("listitem");
    let run: CloseRunRef | undefined;
    let quarantined = 0;

    await test.step("SF-05:close-run", async () => {
      await page
        .getByRole("navigation", { name: "Close of Sep 2026" })
        .getByRole("link", { name: "Close run" })
        .click();
      // The world holds no close run (R-RC-1): SCR-ST-03, and the command for `period.close`.
      expect(await avmJpCloseRuns(page.request)).toEqual([]);
      await expect(
        page.getByRole("heading", { level: 2, name: "No close run for Sep 2026" }),
      ).toBeVisible();
      await page.getByRole("button", { name: "Run close" }).first().click();
      await expect(header).toBeVisible();
      // E2E-02: the run as the API answers it; the screen follows it without a reload.
      await expect
        .poll(async () => (await avmJpCloseRun(page.request)).status, {
          timeout: 240_000,
          intervals: [2_000],
        })
        .not.toMatch(/^(PENDING|RUNNING)$/);
      run = await avmJpCloseRun(page.request);
      expect(closeRunAnswer(run)).toEqual({
        status: "BLOCKED",
        step: "RECOMPUTE_DIRTY",
        problems: [],
      });
      quarantined = Number(recomputeStep(run).counts.groups_quarantined);
      const items = await avmJpQuarantines(page.request);
      // Each quarantined contract is an open blocking item of the engine, with its own code.
      expect(quarantined).toBeGreaterThan(0);
      expect(items).toHaveLength(quarantined);

      await expect(header).toHaveAccessibleName(`Close run ${run.close_run_no}`);
      await expect(header).toContainText("Blocked");
      await expect(header).toContainText("Step 4 of 14: Recompute changed contracts");
      await expect(blocked).toContainText(
        `Close run ${run.close_run_no} is blocked: ${countText(quarantined)} contracts were quarantined. Resolve or waive them, then resume.`,
      );
      await expect(blocked.getByRole("button", { name: "Resume close run" })).toBeVisible();
      await expect(header.getByRole("button", { name: "Cancel close run" })).toBeVisible();
      // Steps 1 to 3 succeeded, step 4 is blocked, the others have not started.
      await expect(stepList).toHaveAttribute("data-testid", "SF-05-close-run-steps");
      await expect(steps).toHaveCount(14);
      for (const [index, step] of run.steps.entries()) {
        const word = index < 3 ? "Succeeded" : index === 3 ? "Blocked" : "Queued";
        expect(step.status).toBe(index < 3 ? "SUCCEEDED" : index === 3 ? "BLOCKED" : "PENDING");
        await expect(steps.nth(index)).toHaveAccessibleName(
          new RegExp(`^Step ${String(index + 1)} of 14, .+, ${word}$`),
        );
      }
      await expect(page.getByTestId("SF-05-row-recompute-dirty")).toContainText(
        new RegExp(`\\d+ groups? recomputed, ${countText(quarantined)} quarantined`),
      );
      // The contracts to resolve or waive, each with the code of its refusal and its exception.
      const grid = page
        .getByTestId("SF-05-grid-quarantined")
        .getByRole("grid", { name: "Quarantined contracts" });
      await expect(grid.getByRole("rowheader")).toHaveCount(quarantined);
      for (const item of items) {
        const row = grid.getByRole("row").filter({ hasText: item.exception_no });
        // The item of a group of several contracts names no contract: the group's code stands there.
        await expect(row.getByRole("rowheader")).toHaveText(
          item.contract_external_id ?? item.combination_group_code ?? "",
        );
        await expect(row).toContainText(item.code);
        await expect(row.getByRole("link", { name: item.exception_no })).toHaveAttribute(
          "href",
          /^\/data\/exceptions\/[0-9a-f-]{36}\?/,
        );
      }
      // No header or cell of the grid is cut, and its four columns fit the page at 1440 px; the
      // message is cut last, inside its own box, and keeps its whole text in its title.
      await expect.poll(() => clippedBoxes(grid)).toEqual([]);
      expect(await grid.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(
        true,
      );
      await dismissToasts(page);
      await screens.capture(page, "sf-05-close-run", { surface: "SF-05:close-run" });
      await a11y.check(page, "SF-05:close-run");
    });

    await test.step("SF-05:multi-entity", async () => {
      if (run === undefined) {
        throw new Error("the step SF-05:close-run left no run");
      }
      const controller = await personas.page("marcus");
      await controller.goto(`/close/multi-entity?${AVM_JP_CONTEXT}`);
      await expect(
        controller.getByRole("heading", {
          level: 1,
          name: "Multi-entity close · Sep 2026 · ASC 606",
        }),
      ).toBeVisible();
      // The run of AVM-JP has not ended, so AVM-JP is chosen when the page opens and its row shows
      // the run of its own period: AVM-JP's Sep 2026 is FY2027-P06.
      const selector = controller.getByTestId("SF-05-multi-entity-entities");
      await expect(selector.getByRole("button", { name: /^Remove AVM-JP · / })).toBeVisible();
      // SCREENS_B §1.5 wireframe: the command sits on the selector's row, not beside the note under it.
      const control = await selector.getByRole("combobox", { name: "Entities" }).boundingBox();
      const command = await controller
        .getByRole("button", { name: "Start close runs" })
        .boundingBox();
      if (control === null || command === null) {
        throw new Error("the entity selector or its command has no box");
      }
      expect(
        Math.abs(command.y + command.height / 2 - (control.y + control.height / 2)),
      ).toBeLessThanOrEqual(4);
      const grid = controller
        .getByTestId("SF-05-grid-multi-entity")
        .getByRole("grid", { name: "Close runs" });
      const row = grid.getByTestId("SF-05-row-avm-jp");
      await expect(row.getByRole("rowheader")).toHaveText("AVM-JP");
      await expect(row).toContainText("Sep 2026");
      await expect(row).toContainText(run.close_run_no);
      await expect(row).toContainText("Blocked");
      await expect(row).toContainText("Step 4 of 14");
      await expect(row.getByRole("link", { name: run.close_run_no })).toHaveAttribute(
        "href",
        `${AVM_JP_CLOSE}/close-run?${AVM_JP_CONTEXT}`,
      );
      await expect(row.getByRole("link", { name: "Open the cockpit of AVM-JP" })).toHaveAttribute(
        "href",
        `${AVM_JP_CLOSE}?${AVM_JP_CONTEXT}`,
      );
      // A start while the run has not ended answers that run (04 §16.8): none is added.
      await controller.getByRole("button", { name: "Start close runs" }).click();
      await expect(
        controller.getByText("AVM-JP already has a running close run. It was not started again."),
      ).toBeVisible();
      expect((await avmJpCloseRun(controller.request)).id).toBe(run.id);
      await expect(row).toContainText(run.close_run_no);
      await expect.poll(() => clippedBoxes(grid)).toEqual([]);
      await dismissToasts(controller);
      await screens.capture(controller, "sf-05-multi-entity", { surface: "SF-05:multi-entity" });
      await a11y.check(controller, "SF-05:multi-entity");
    });

    await test.step("SF-05:close-run resume blocks again; cancel ends the run", async () => {
      if (run === undefined) {
        throw new Error("the step SF-05:close-run left no run");
      }
      const number = run.close_run_no;
      const before = recomputeStep(run).finished_at;
      // NFR-14: the run restarts at the first step that has not succeeded. Nothing was resolved or
      // waived, so the recalculation refuses the same contracts and the run is blocked again.
      await blocked.getByRole("button", { name: "Resume close run" }).click();
      await expect
        .poll(
          async () => {
            const current = await avmJpCloseRun(page.request);
            return current.status === "BLOCKED" && recomputeStep(current).finished_at !== before;
          },
          { timeout: 240_000, intervals: [2_000] },
        )
        .toBe(true);
      const resumed = await avmJpCloseRun(page.request);
      expect(Number(recomputeStep(resumed).counts.groups_quarantined)).toBe(quarantined);
      await expect(blocked).toContainText(
        `Close run ${number} is blocked: ${countText(quarantined)} contracts were quarantined.`,
      );
      await expect(header).toContainText("Blocked");

      // SB-R-05: a reason of at least 10 characters. A blocked run is cancelled at once.
      await header.getByRole("button", { name: "Cancel close run" }).click();
      const dialog = page.getByRole("alertdialog", { name: `Cancel close run ${number}?` });
      await dialog
        .getByRole("textbox", { name: /^Reason \(required\)/ })
        .fill("The SSP of the AVM-JP licences is corrected first.");
      await dialog.getByRole("button", { name: "Cancel close run", exact: true }).click();
      await expect(page.getByText(`Close run ${number} was cancelled.`)).toBeVisible();
      await expect(dialog).toHaveCount(0);
      expect((await avmJpCloseRun(page.request)).status).toBe("CANCELLED");
      await expect(header).toContainText("Cancelled");
      await expect(blocked).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Cancel close run" })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Resume close run" })).toHaveCount(0);
    });
  });
});

/**
 * CLO-26 (DS-AP-10): the header labels and cells of a grid whose content is cut off, as
 * "<text> (<scrollWidth> > <clientWidth>)". A text test passes on a clipped line, so the clipping box is
 * measured (scrollWidth <= clientWidth).
 */
async function clippedBoxes(grid: Locator): Promise<readonly string[]> {
  return grid.evaluate((element) =>
    [
      ...element.querySelectorAll<HTMLElement>(
        '[role="columnheader"] .truncate, [role="gridcell"], [role="rowheader"]',
      ),
    ]
      .filter((box) => box.clientWidth > 0 && box.scrollWidth > box.clientWidth + 1)
      .map(
        (box) =>
          `${(box.textContent ?? "").trim()} (${String(box.scrollWidth)} > ${String(box.clientWidth)})`,
      ),
  );
}

test.describe("SF-06 Journal runs (RT-28, RT-29, RT-104, RT-105), persona maya", () => {
  // One worker runs the four rows over the same run.
  test.describe.configure({ mode: "serial" });
  let run: JournalRunRef | null = null;

  test.beforeAll(async ({ browser }, testInfo: TestInfo) => {
    const maya = await personaContext(browser, "maya");
    const records = [await installNetworkGuard(maya)];
    let priya: BrowserContext | null = null;
    try {
      let earliest = (await augustRuns(maya.request))[0];
      if (earliest === undefined) {
        const created = await new ApiClient(maya.request).command("POST", "/api/v1/journal-runs", {
          entity_code: "AVM-US",
          period_key: "FY2026-P08",
          book: "ASC606",
        });
        expect(created.status(), await created.text()).toBe(202);
        await awaitJob(maya.request, created.headers()["location"]);
        earliest = (await augustRuns(maya.request))[0];
      }
      if (earliest === undefined) {
        throw new Error("POST /journal-runs created no AVM-US FY2026-P08 run");
      }
      if (earliest.state === "draft") {
        let requestId = earliest.approval_request_id;
        if (requestId === null) {
          const submitted = await json<JournalRunRef>(
            await new ApiClient(maya.request).command(
              "POST",
              `/api/v1/journal-runs/${earliest.id}/submit`,
              { comment: "Aug 2026 AVM-US journals for approval." },
            ),
          );
          requestId = submitted.approval_request_id;
        }
        if (requestId === null) {
          throw new Error("POST /journal-runs/{id}/submit named no approval request");
        }
        // The approver signs in for this decision: her cached sign-in may be older than the five
        // minutes a decision allows its second factor (BR-PLT-06).
        const approver = await freshSignIn(browser, "priya");
        priya = approver.context;
        records.push(approver.record);
        // ApprovalApproveIn carries the hashes the approver reviewed (REQ-PLT-014), as SF-12:request sends them.
        const approval = await json<{
          subject: { content_sha256: string };
          impact_preview: { sha256: string } | null;
        }>(await priya.request.get(`/api/v1/approvals/${requestId}`));
        const approved = await new ApiClient(priya.request).command(
          "POST",
          `/api/v1/approvals/${requestId}/approve`,
          {
            subject_content_sha256: approval.subject.content_sha256,
            ...(approval.impact_preview === null
              ? {}
              : { impact_preview_sha256: approval.impact_preview.sha256 }),
            comment: "Reviewed the Aug 2026 AVM-US journal run.",
          },
        );
        // D-87 L6-5-Q-1: approve answers 200 API-S-ApprovalRequest.
        expect(approved.status(), await approved.text()).toBe(200);
      }
      const current = await json<JournalRunRef>(
        await maya.request.get(`/api/v1/journal-runs/${earliest.id}`),
      );
      if (current.state === "approved") {
        const exported = await new ApiClient(maya.request).command(
          "POST",
          `/api/v1/journal-runs/${earliest.id}/export`,
          { adapter: "CSV" },
        );
        expect(exported.status(), await exported.text()).toBe(202);
        await awaitJob(maya.request, exported.headers()["location"]);
      }
      run = await json<JournalRunRef>(
        await maya.request.get(`/api/v1/journal-runs/${earliest.id}`),
      );
    } finally {
      await maya.close();
      await priya?.close();
    }
    for (const record of records) {
      appendProjectRecord(testInfo, record);
      expect(record).toEqual({ requests: [], cspViolations: [] });
    }
  });

  function created(): JournalRunRef {
    if (run === null) {
      throw new Error("the AVM-US FY2026-P08 journal run was not created");
    }
    return run;
  }

  test("SF-06 maya", async ({ personas, screens, a11y }) => {
    const { run_no: runNo } = created();
    const page = await personas.page("maya");
    await page.goto(`/journals?${AVM_US_AUGUST}`);
    await expect(page.getByRole("heading", { level: 1, name: "Journals" })).toBeVisible();
    const grid = page.getByTestId("SF-06-grid-runs").getByRole("grid", { name: "Journal runs" });
    await expect(grid).toBeVisible();
    await expect(grid.getByRole("link", { name: runNo })).toBeVisible();
    await expect(page.getByTestId("SF-06-row-avm-us-fy2026-p08").first()).toBeVisible();
    await screens.capture(page, "sf-06", { surface: "SF-06" });
    // CLO-26: measured on the captured layout, the default columns fit the grid viewport at 1440 px
    // and no figure or header clips.
    await expect.poll(() => clippedBoxes(grid)).toEqual([]);
    expect(await grid.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
    await a11y.check(page, "SF-06");
  });

  test("SF-06:run maya", async ({ personas, screens, a11y }) => {
    const { id, run_no: runNo } = created();
    const page = await personas.page("maya");
    // E2E-02: balancing per entity and currency, difference 0.00, first as the API strings.
    const summary = await json<{
      readonly balance_checks: readonly { readonly difference: unknown }[];
    }>(await page.request.get(`/api/v1/journal-runs/${id}/summary`));
    expect(summary.balance_checks.length).toBeGreaterThan(0);
    for (const check of summary.balance_checks) {
      expectDecimal(amountText(check.difference), "0.00");
    }
    await page.goto(`/journals/runs/${id}?${AVM_US_AUGUST}`);
    await expect(
      page.getByRole("heading", { level: 1, name: `Journal run ${runNo}` }),
    ).toBeVisible();
    const rows = page.getByRole("table", { name: "Balance checks" }).locator("tbody tr");
    await expect(rows).toHaveCount(summary.balance_checks.length);
    for (let index = 0; index < summary.balance_checks.length; index += 1) {
      const row = rows.nth(index);
      await expect(row.locator("td").nth(5)).toContainText("0.00");
      await expect(row.getByText("Balanced", { exact: true })).toBeVisible();
    }
    await expect(page.getByTestId("SF-06-kpi-difference")).toContainText("0.00");
    await screens.capture(page, "sf-06-run", { surface: "SF-06:run" });
    await a11y.check(page, "SF-06:run");
  });

  test("SF-06:run-lines maya", async ({ personas, screens, a11y }) => {
    const { id } = created();
    const page = await personas.page("maya");
    await page.goto(`/journals/runs/${id}/lines?${AVM_US_AUGUST}&f.account=is:4010`);
    // L6-5-Q-4: the BUILD_SPEC `f.account` spelling becomes the SCREENS_B `f.account_code`.
    await expect(page).toHaveURL(/f\.account_code=is:4010/);
    const grid = page.getByTestId("SF-06-grid-lines").getByRole("grid", { name: "Journal lines" });
    const rows = grid.locator('[role="row"][aria-rowindex]:not([aria-rowindex="1"])');
    await expect(rows.first()).toBeVisible();
    // CLO-26: the accepted alias raises no "not recognised" banner, and no figure or header clips.
    await expect(
      page.getByText("Some filters in the link were not recognised and were removed."),
    ).toHaveCount(0);
    await expect.poll(() => clippedBoxes(grid)).toEqual([]);
    await rows
      .first()
      .getByRole("button", { name: /^Source lines for / })
      .click();
    const drawer = page.getByTestId("SF-06-drawer-source-lines");
    await expect(drawer).toBeVisible();
    await expect(page.getByRole("complementary", { name: /^Source lines for / })).toBeVisible();
    const drill = drawer.getByRole("grid", { name: "Source lines" });
    await expect(
      drill.locator('[role="row"][aria-rowindex]:not([aria-rowindex="1"])').first(),
    ).toBeVisible();
    // CLO-26 (SCREENS_B §3.3; DS-SP-04): the drawer docks beside the page, right of the run frame.
    const frame = await page.getByTestId("SF-06-page").boundingBox();
    const aside = await page
      .getByRole("complementary", { name: /^Source lines for / })
      .boundingBox();
    expect(frame).not.toBeNull();
    expect(aside).not.toBeNull();
    if (frame !== null && aside !== null) {
      expect(aside.x).toBeGreaterThanOrEqual(frame.x + frame.width);
      expect(aside.y).toBeLessThanOrEqual(frame.y + 1);
    }
    // SCREENS_B §3.3: the drawer opens on what it explains — whose line, which side, how much and
    // when lie inside it before any scroll. The first four columns were 688 px of the 686 it has.
    // A header cell of a DataGrid is named by its text and by its options button after it —
    // "Contract Column options: Contract" — so a header is found by the text its name begins with.
    const headerOf = (name: string) =>
      drill.getByRole("columnheader", { name: new RegExp(`^${escapeRegExp(name)} `) });
    const opened = await drill.boundingBox();
    expect(opened).not.toBeNull();
    for (const name of ["Contract", "Debit or credit", "Amount (txn)", "Effective"]) {
      await expect(headerOf(name), name).toBeVisible();
      const header = await headerOf(name).boundingBox();
      expect(header, name).not.toBeNull();
      if (opened !== null && header !== null) {
        expect(header.x, name).toBeGreaterThanOrEqual(opened.x);
        expect(header.x + header.width, name).toBeLessThanOrEqual(opened.x + opened.width + 1);
      }
    }
    await screens.capture(page, "sf-06-run-lines", { surface: "SF-06:run-lines" });
    // Measured on the captured layout, with the drawer docked and the frame reflowed.
    await expect.poll(() => clippedBoxes(grid)).toEqual([]);
    await expect.poll(() => clippedBoxes(drill)).toEqual([]);
    // The contract is the row header, and pinned: it keeps its place when the last column is in view.
    const pinned = await headerOf("Contract").boundingBox();
    expect(pinned).not.toBeNull();
    await drill.evaluate((element) => {
      element.scrollLeft = element.scrollWidth;
    });
    await expect(headerOf("Actions")).toBeInViewport();
    const kept = await headerOf("Contract").boundingBox();
    expect(kept).not.toBeNull();
    if (pinned !== null && kept !== null) {
      expect(Math.abs(kept.x - pinned.x)).toBeLessThanOrEqual(1);
    }
    await drill.evaluate((element) => {
      element.scrollLeft = 0;
    });
    await a11y.check(page, "SF-06:run-lines");
  });

  test("SF-06:run-batches maya", async ({ personas, screens, a11y }) => {
    const { id, run_no: runNo } = created();
    const page = await personas.page("maya");
    const batches = await json<{ readonly items: readonly JournalBatchRef[] }>(
      await page.request.get(`/api/v1/journal-runs/${id}/batches`),
    );
    expect(batches.items.length).toBeGreaterThan(0);
    for (const batch of batches.items) {
      expect(batch.external_id).toBe(
        `erev:avenmoor:${runNo}:${String(batch.batch_no)}:${String(batch.chunk_no)}`,
      );
      // R-RC-1 (CLO-14, CLO-15 post-rc): exported through the CSV adapter, not acknowledged.
      expect(batch.state).toBe("exported");
    }
    await page.goto(`/journals/runs/${id}/batches?${AVM_US_AUGUST}`);
    const grid = page.getByTestId("SF-06-grid-batches").getByRole("grid", { name: "Batches" });
    await expect(grid).toBeVisible();
    for (const batch of batches.items) {
      await expect(grid.getByText(batch.external_id, { exact: true })).toBeVisible();
    }
    await screens.capture(page, "sf-06-run-batches", { surface: "SF-06:run-batches" });
    await expect.poll(() => clippedBoxes(grid)).toEqual([]);
    await a11y.check(page, "SF-06:run-batches");
  });

  /**
   * BUILD_SPEC RPS-7 under R-RC-1 (SPRINT-vabc §3.2, §6.2): the Aug 2026 AVM-US journal activity is the run
   * `beforeAll` created through the API, not seeded close history. The RPT-13 builder is RPS-5 (lane L7-1),
   * so this row first runs at the L7 merge gate.
   */
  test("SF-06:entries maya", async ({ personas, screens, a11y }) => {
    created();
    const page = await personas.page("maya");
    await page.goto(
      `/journals/entries?${AVM_US_AUGUST}&format=gross&from=2026-08-01&to=2026-08-31`,
    );
    await expect(page.getByRole("heading", { level: 1, name: "Journals" })).toBeVisible();
    // RV-01: opening the view creates one run, and the URL names it (SCR-URL-16).
    await expect(page).toHaveURL(/[?&]run=[0-9a-f-]{36}(&|$)/, REPORT_RUN_WAIT);
    const runId = new URL(page.url()).searchParams.get("run") ?? "";
    await expect(page.getByTestId("SF-06-run-stamp")).toContainText(
      "Legacy journal summary v1",
      REPORT_RUN_WAIT,
    );
    // E2E-02: Dr = Cr, first as the API decimal strings of the run's control totals.
    await expect
      .poll(
        async () =>
          (await json<{ status: string }>(await page.request.get(`/api/v1/report-runs/${runId}`)))
            .status,
        REPORT_RUN_WAIT,
      )
      .toBe("SUCCEEDED");
    const stored = await json<{
      readonly control_totals: {
        readonly total_debit: Readonly<Record<string, string>>;
        readonly total_credit: Readonly<Record<string, string>>;
      };
    }>(await page.request.get(`/api/v1/report-runs/${runId}`));
    expect(Object.keys(stored.control_totals.total_debit).length).toBeGreaterThan(0);
    for (const [currency, debit] of Object.entries(stored.control_totals.total_debit)) {
      expectDecimal(stored.control_totals.total_credit[currency], debit);
    }
    const grid = page
      .getByTestId("SF-06-grid-entries-by-account")
      .getByRole("grid", { name: "Journal lines by account" });
    await expect(grid).toBeVisible();
    const total = grid
      .getByRole("row")
      .filter({ has: page.getByRole("rowheader", { name: "Total", exact: true }) });
    await expect(total).toHaveCount(1);
    const cells = total.getByRole("gridcell");
    await expect(cells.nth(0)).toHaveText(await cells.nth(1).innerText());
    await expect(page.getByTestId("SF-06-grid-entries-line-items")).toBeVisible();
    await screens.capture(page, "sf-06-entries", { surface: "SF-06:entries" });
    await a11y.check(page, "SF-06:entries");
  });
});

/**
 * BUILD_SPEC RPS-6 (SCREENS_B §5.1, §5.2, §0.5; §15 rows SF-08 and SF-08:report). Under R-RC-1 the seeded
 * AVM-US FY2026-P08 lock moves to DMO (CLO-22 post-rc; SPRINT-vabc §6.2), so the `rpo` step reads the open
 * Sep 2026 period here. This world holds no lock: `rpo` as locked and `sf-08-report-rpo-locked` are the
 * closed world's (projects/closed.spec.ts, `make e2e CLOSE=1`; BUILD_SPEC rev 1.76). The legacy export
 * builder is RPS-5 (lane L7-1), so that step first runs at the L7 merge gate.
 */
const SF_08_HIDDEN_CODES = [
  "forecast_outputs",
  "actual_vs_forecast",
  "migration_reconciliation",
  "parallel_run_comparison",
] as const;

function reportRowOf(page: Page, externalId: string, prefix = "SF-08"): Locator {
  return page.getByTestId(`${prefix}-row-${externalId.toLowerCase()}`);
}

/**
 * DS-CMP-10 grids hold the visible rows plus 10 overscan rows (DG-FE-07), so a report row further down
 * enters the DOM once the grid scrolls to it.
 */
async function scrolledReportRow(
  page: Page,
  grid: Locator,
  externalId: string,
  prefix = "SF-08",
): Promise<Locator> {
  const row = reportRowOf(page, externalId, prefix);
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

test.describe("SF-08 Reports (RT-31 /reports), persona robert", () => {
  test("SF-08 robert", async ({ personas, screens, a11y }) => {
    const page = await personas.page("robert");
    await test.step("SF-08 catalogue", async () => {
      await page.goto(`/reports?${AVM_US_CONTEXT}`);
      await expect(page.getByRole("heading", { level: 1, name: "Reports" })).toBeVisible();
      const balances = page.getByTestId("SF-08-grid-balances-and-disclosures");
      await expect(balances.getByText(/^Balances and disclosures \(\d+\)$/)).toBeVisible();
      for (const name of ["Contract balances", "Remaining performance obligations"]) {
        await expect(balances.getByRole("link", { name, exact: true })).toBeVisible();
      }
      await expect(
        page
          .getByTestId("SF-08-grid-revenue-and-analysis")
          .getByRole("link", { name: "Revenue waterfall", exact: true }),
      ).toBeVisible();
      await expect(
        page
          .getByTestId("SF-08-grid-legacy-exports")
          .getByRole("link", { name: "Legacy contract history export", exact: true }),
      ).toBeVisible();
      // §5.1 visibility: WLD-T-01 is a production tenant without a migration.
      for (const code of SF_08_HIDDEN_CODES) {
        await expect(page.getByTestId(`SF-08-row-${code.replaceAll("_", "-")}`)).toHaveCount(0);
      }
      await expect(page.getByTestId("SF-08-grid-forecasts-and-migration")).toHaveCount(0);
      await screens.capture(page, "sf-08", { surface: "SF-08" });
      await a11y.check(page, "SF-08");
    });
  });
});

test.describe("SF-08:report Report view (RT-32 /reports/:reportCode), persona marcus", () => {
  test("SF-08:report marcus", async ({ personas, screens, a11y }) => {
    const page = await personas.page("marcus");
    await test.step("SF-08:report", async () => {
      await test.step("revenue_waterfall with chart and tie-out strip", async () => {
        await page.goto(`/reports/revenue_waterfall?${AVM_US_CONTEXT}`);
        await expect(
          page.getByRole("heading", { level: 1, name: "Revenue waterfall" }),
        ).toBeVisible();
        // RV-01: opening the view creates one run, and the URL names it (SCR-URL-16).
        await expect(page).toHaveURL(/[?&]run=[0-9a-f-]{36}(&|$)/, REPORT_RUN_WAIT);
        const stamp = page.getByTestId("SF-08-run-stamp");
        await expect(stamp).toContainText("Revenue waterfall v1", REPORT_RUN_WAIT);
        await expect(stamp).toContainText("Current, known at");
        await expect(
          page.getByTestId("SF-08-chart-revenue-waterfall").getByRole("figure"),
        ).toBeVisible(REPORT_RUN_WAIT);
        const strip = page.getByTestId("SF-08-banner-tie-outs");
        await expect(
          strip.getByRole("heading", { name: /^Tie-outs \(\d+ pass, \d+ fail\)$/ }),
        ).toBeVisible();
        await expect(strip).toContainText("Waterfall revenue equals revenue journal total");
        await expect(strip).toContainText("Expected USD");
        const grid = page
          .getByTestId("SF-08-grid-revenue-waterfall")
          .getByRole("grid", { name: "Revenue waterfall" });
        await expect(grid).toBeVisible();
        // RPT-01 column order: Contract first, then the periods, Awaiting trigger and Total.
        await expect(grid.getByRole("columnheader").first()).toContainText("Contract");
        await screens.capture(page, "sf-08-report-revenue-waterfall", { surface: "SF-08:report" });
        await a11y.check(page, "SF-08:report revenue_waterfall");
      });

      await test.step("RV-09 a report cell opens Explain through SB-R-07; Esc returns focus to the cell", async () => {
        const grid = page
          .getByTestId("SF-08-grid-revenue-waterfall")
          .getByRole("grid", { name: "Revenue waterfall" });
        const row = await scrolledReportRow(page, grid, K01);
        const figureName = new RegExp(`^Explain Sep 2026 \\(USD\\) · ${K01}, USD\\s`);
        const figure = row.getByRole("button", { name: figureName });
        // A `has` locator is resolved inside each candidate cell, so it starts from the page.
        const cell = row
          .getByRole("gridcell")
          .filter({ has: page.getByRole("button", { name: figureName }) });
        await figure.click();
        const panel = page.getByTestId("SF-08-explain");
        await expect(panel).toBeVisible();
        await page.keyboard.press("Escape");
        await expect(panel).toHaveCount(0);
        await expect(cell).toBeFocused();
      });

      await test.step("rpo at 30 Sep 2026 with time-band columns and the exempt section", async () => {
        await page.goto(`/reports/rpo?${AVM_US_CONTEXT}`);
        await expect(
          page.getByRole("heading", { level: 1, name: "Remaining performance obligations" }),
        ).toBeVisible();
        await expect(page.getByTestId("SF-08-run-stamp")).toContainText(
          "30 Sep 2026",
          REPORT_RUN_WAIT,
        );
        const grid = page.getByTestId("SF-08-grid-remaining-performance-obligations");
        for (const header of [
          "Within 12 months (USD)",
          "13 to 24 months (USD)",
          "After 24 months (USD)",
        ]) {
          await expect(grid.getByRole("columnheader", { name: header })).toBeAttached(
            REPORT_RUN_WAIT,
          );
        }
        await expect(page.getByTestId("SF-08-grid-exempt-contracts")).toBeVisible();
        // Checked before scrolling: the grid's roving tab stop is row 0, which scrolling virtualises away.
        await a11y.check(page, "SF-08:report rpo");
        // PRD J-15.4 (K-09): SF-ORD-10417 total 105,043.80.
        const k09 = await scrolledReportRow(
          page,
          grid.getByRole("grid", { name: "Remaining performance obligations" }),
          "SF-ORD-10417",
        );
        await expect(k09).toContainText("105,043.80");
      });

      await test.step("legacy_contract_history_export for SF-ORD-10001 from 01 Jan 2026 to 30 Aug 2026", async () => {
        await page.goto(
          `/reports/legacy_contract_history_export?${AVM_US_CONTEXT}&p.contract_external_id=${K01}&p.from_date=2026-01-01&p.to_date=2026-08-30`,
        );
        await expect(
          page.getByRole("heading", { level: 1, name: "Legacy contract history export" }),
        ).toBeVisible();
        await expect(page.getByTestId("SF-08-run-stamp")).toContainText(
          "Legacy contract history export v1",
          REPORT_RUN_WAIT,
        );
        const grid = page.getByTestId("SF-08-grid-legacy-contract-history-export");
        // D-33: the legacy column names are the headers (04 §17.2 LM-CL-01 to LM-CL-71).
        await expect(
          grid.getByRole("columnheader", { name: "Current Contract Position - Contract Level" }),
        ).toBeAttached(REPORT_RUN_WAIT);
        // D-88 L7-1-Q-5: the grid follows the run's `columns`, the legacy output order (SCREENS_B RPT-10).
        const headers = grid.getByRole("columnheader");
        await expect(headers.nth(0)).toHaveText("Contract Unique Name");
        await expect(headers.nth(1)).toHaveText("POB Unique ID");
        await expect(headers.nth(2)).toHaveText("SKU Name");
        await screens.capture(page, "sf-08-report-legacy-contract-history-export", {
          surface: "SF-08:report",
        });
        await a11y.check(page, "SF-08:report legacy_contract_history_export");
      });

      await test.step("a report opened without a context takes the context pill's", async () => {
        // SCREENS SCR-URL-01 rev 1.61 (item RPT-VIEW-CONTEXT-DEFAULT-1): the address names no entity,
        // so the view fills entity, period and book from the pill — marcus's last choice, else
        // BR-UX-01's default — writes them and asks one run for that entity, not for every entity.
        await page.goto("/reports/rpo");
        await expect(page).toHaveURL(
          /\/reports\/rpo\?entity=AVM-[A-Z]{2}&period=FY\d{4}-P\d{2}&book=[A-Z0-9]+&run=[0-9a-f-]{36}$/,
          REPORT_RUN_WAIT,
        );
        const address = new URL(page.url()).searchParams;
        const stored = await json<{ readonly parameters: Readonly<Record<string, unknown>> }>(
          await page.request.get(`/api/v1/report-runs/${address.get("run") ?? ""}`),
        );
        expect(stored.parameters).toMatchObject({
          entity_codes: [address.get("entity")],
          book: address.get("book"),
          period_key: address.get("period"),
        });
        await expect(page.getByTestId("SF-08-run-stamp")).toContainText(
          address.get("entity") ?? "",
          REPORT_RUN_WAIT,
        );
      });
    });
  });
});

/**
 * BUILD_SPEC RPS-19, first head (SCREENS_B §5.5 rev 1.82; §15 row SF-08:dashboard): the revenue dashboard.
 * For all entities — `entities=all`, SCREENS SCR-URL-01 rev 1.61 — robert's scope is the four entities of
 * WLD-T-01, which keep different calendars (AVM-JP: an April fiscal year, PRD WLD-P-05) and functional
 * currencies, so no report run is made: the banner says why and the flags panel stays. An address without
 * a context takes the context pill's and is written (item RPT-VIEW-CONTEXT-DEFAULT-1). With
 * `entity=AVM-US` the four panels are drawn from four runs under the functional view. The close dashboard
 * follows with the item's second head.
 */
test.describe("SF-08:dashboard Revenue dashboard (RT-107 /reports/dashboards/:dashboardCode), persona robert", () => {
  test("SF-08:dashboard robert", async ({ personas, screens, a11y }) => {
    const page = await personas.page("robert");
    await test.step("SF-08:dashboard for all entities", async () => {
      await page.goto("/reports/dashboards/revenue?period=FY2026-P09&book=ASC606&entities=all");
      await expect(
        page.getByRole("heading", {
          level: 1,
          name: "Revenue dashboard · All entities · Sep 2026 · ASC 606",
        }),
      ).toBeVisible();
      await expect(page.getByTestId("SF-08-dashboard-banner-scope")).toHaveText(
        "The entities in scope keep different calendars and functional currencies. Select an entity to see its charts.",
      );
      await expect(
        page
          .getByTestId("SF-08-dashboard-flags")
          .getByText("No open anomaly flags", { exact: true }),
      ).toBeVisible();
      // No run is made: no panel, nothing to refresh, no run in the address.
      await expect(page.locator('[data-testid^="SF-08-chart-dashboard-"]')).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Refresh" })).toHaveCount(0);
      await expect(page).not.toHaveURL(/[?&]run\./);
      await screens.capture(page, "sf-08-dashboard-revenue", { surface: "SF-08:dashboard" });
      await a11y.check(page, "SF-08:dashboard revenue, all entities");
    });

    await test.step("SF-08:dashboard without a context", async () => {
      // SCREENS SCR-URL-01 rev 1.61: an address that names no entity is the context pill's —
      // robert's last choice, else BR-UX-01's default — and the page writes entity, period and book
      // into it before a run is asked.
      await page.goto("/reports/dashboards/revenue");
      await expect(page).toHaveURL(
        /\/reports\/dashboards\/revenue\?entity=AVM-[A-Z]{2}&period=FY\d{4}-P\d{2}&book=[A-Z0-9]+(&|$)/,
      );
      const entity = new URL(page.url()).searchParams.get("entity") ?? "";
      await expect(
        page.getByRole("heading", {
          level: 1,
          name: new RegExp(`^Revenue dashboard · ${entity} · `),
        }),
      ).toBeVisible();
      await expect(page.getByTestId("SF-08-dashboard-banner-scope")).toHaveCount(0);
      // Each panel has left its loading state: a chart, its empty text or its own refusal.
      await expect(page.locator('[data-testid^="SF-08-chart-dashboard-"]')).toHaveCount(4);
      await expect(
        page.locator('[data-testid^="SF-08-chart-dashboard-"] [aria-busy="true"]'),
      ).toHaveCount(0, REPORT_RUN_WAIT);
      await screens.capture(page, "sf-08-dashboard-revenue-default", {
        surface: "SF-08:dashboard",
      });
      await a11y.check(page, "SF-08:dashboard revenue, the pill's entity");
    });

    await test.step("SF-08:dashboard with an entity", async () => {
      await page.goto(`/reports/dashboards/revenue?${AVM_US_CONTEXT}`);
      await expect(
        page.getByRole("heading", {
          level: 1,
          name: "Revenue dashboard · AVM-US · Sep 2026 · ASC 606",
        }),
      ).toBeVisible();
      // RV-01 and SCR-URL-26: one run per panel, each named in the address.
      const panels = [
        ["revenue", "Revenue by period · USD · ASC 606", "revenue_waterfall"],
        ["rollforward", "Contract liability rollforward · USD", "contract_balance_rollforward"],
        ["rpo", "Remaining performance obligations by time band · USD · ASC 606", "rpo"],
        ["disaggregation", "Revenue by category · USD · Sep 2026", "disaggregation"],
      ] as const;
      for (const [panel, name, report] of panels) {
        await expect(page).toHaveURL(
          new RegExp(`[?&]run\\.${panel}=[0-9a-f-]{36}(&|$)`),
          REPORT_RUN_WAIT,
        );
        const frame = page.getByTestId(`SF-08-chart-dashboard-${panel}`);
        await expect(frame.getByRole("figure", { name, exact: true })).toBeVisible(REPORT_RUN_WAIT);
        // The footer states the run and leads to its report under the page's view.
        await expect(frame.locator("[data-volatile]")).toHaveText(/^Run RPT-\d{6} · /);
        await expect(frame.getByRole("link", { name: /^Open report: / })).toHaveAttribute(
          "href",
          new RegExp(
            `^/reports/${report}\\?${AVM_US_CONTEXT}&currency_view=functional&run=[0-9a-f-]{36}`,
          ),
        );
      }
      await expect(page.getByText("Functional", { exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "Refresh" })).toBeVisible();
      await expect(page.getByTestId("SF-08-dashboard-banner-scope")).toHaveCount(0);
      await screens.capture(page, "sf-08-dashboard-revenue-entity", { surface: "SF-08:dashboard" });
      await a11y.check(page, "SF-08:dashboard revenue, AVM-US");
      // The shell scrolls inside the viewport, so a capture holds one screen of the page: the second
      // shows its lower half, the time bands' footer and the category bars.
      await page.getByTestId("SF-08-chart-dashboard-disaggregation").scrollIntoViewIfNeeded();
      await screens.capture(page, "sf-08-dashboard-revenue-categories", {
        surface: "SF-08:dashboard",
      });
    });
  });
});

/**
 * BUILD_SPEC RPS-18 (SCREENS_B §5.3; §15 rows SF-08:runs and SF-08:run). The demo seed holds no report run
 * (the seeded runs of the item's acceptance line are owed to the seed), so the step creates its run through
 * the product: marcus opens the RPO report view, which creates one JSON run (RV-01). The register lists
 * that run with the REQ-RPT-002 fields, its number opens the run record, and "Rerun from the same source"
 * opens the new run with "Output identical: Yes" and "Control totals identical: Yes" (PRD J-15.6; CTL-029).
 * SF-08:disclosure-pack is not built: API-R-42 is not on main.
 */
test.describe("SF-08:runs Report runs (RT-106 /reports/runs, RT-33), persona marcus", () => {
  test("SF-08:runs and SF-08:run marcus", async ({ personas, screens, a11y }) => {
    const page = await personas.page("marcus");
    await test.step("SF-08:runs and SF-08:run", async () => {
      await page.goto(`/reports/rpo?${AVM_US_CONTEXT}`);
      await expect(
        page.getByRole("heading", { level: 1, name: "Remaining performance obligations" }),
      ).toBeVisible();
      await expect(page).toHaveURL(/[?&]run=[0-9a-f-]{36}(&|$)/);
      const runId = new URL(page.url()).searchParams.get("run") ?? "";
      // The run is a job: on a quiet stack the worker takes it up after its polling interval, which
      // alone can exceed the default wait (this row run by itself: the stamp still read "As of —").
      await expect(page.getByTestId("SF-08-run-stamp")).toContainText("30 Sep 2026", {
        timeout: 90_000,
      });
      const run = await json<{
        readonly report_run_no: string;
        readonly status: string;
        readonly report: { readonly name: string; readonly version: number };
        readonly row_count: number | null;
        readonly run_by: { readonly display_name: string };
        readonly job_id: string | null;
      }>(await page.request.get(`/api/v1/report-runs/${runId}`));
      expect(run.status).toBe("SUCCEEDED");
      const rowId = `SF-08-row-${run.report_run_no.toLowerCase()}`;

      await test.step("the register lists the run with its REQ-RPT-002 fields", async () => {
        await page.goto("/reports");
        await page
          .getByRole("navigation", { name: "Reports sections" })
          .getByRole("link", { name: "Report runs" })
          .click();
        await expect(page).toHaveURL(/\/reports\/runs(\?|$)/);
        // Other rows run reports at the same time: the Report and Status chips keep the list short.
        await page.goto("/reports/runs?f.report_code=is:rpo&f.status=is:SUCCEEDED");
        const bar = page.getByTestId("SF-08-filter-bar");
        await expect(
          bar.getByRole("button", {
            name: "Report is Remaining performance obligations, edit filter",
          }),
        ).toBeVisible();
        const grid = page.getByTestId("SF-08-grid-runs").getByRole("grid", { name: "Report runs" });
        for (const header of [
          "Run",
          "Report",
          "Status",
          "Entity",
          "Book",
          "As of",
          "Source",
          "Format",
          "Rows",
          "Output SHA-256",
          "Run by",
          "Started",
          "Finished",
        ]) {
          // A header's name ends with its menu button: "<header> Column options: <header>". The
          // whole name is matched, so "Run" is not also "Run by".
          await expect(
            grid.getByRole("columnheader", {
              name: `${header} Column options: ${header}`,
              exact: true,
            }),
          ).toBeAttached();
        }
        const row = page.getByTestId(rowId);
        await expect(row.getByRole("rowheader")).toHaveText(run.report_run_no);
        for (const cell of [
          `${run.report.name} v${String(run.report.version)}`,
          "Succeeded",
          "AVM-US",
          "ASC 606",
          "30 Sep 2026",
          "Current",
          "JSON",
        ]) {
          await expect(row.getByText(cell, { exact: true })).toBeVisible();
        }
        await expect(page.getByRole("group", { name: "Accounting context" })).toBeVisible();
        await expect.poll(() => clippedBoxes(grid)).toEqual([]);
        await screens.capture(page, "sf-08-runs", { surface: "SF-08:runs" });
        await a11y.check(page, "SF-08:runs");
      });

      await test.step("the run number opens the run record", async () => {
        await page.getByTestId(rowId).getByRole("link", { name: run.report_run_no }).click();
        await expect(page).toHaveURL(new RegExp(`/reports/runs/${runId}$`));
        await expect(
          page.getByRole("heading", { level: 1, name: `Report run ${run.report_run_no}` }),
        ).toBeVisible();
        const parameters = page.getByTestId("SF-08-grid-run-parameters");
        await expect(parameters.getByRole("row", { name: /^entity_codes AVM-US$/ })).toBeVisible();
        await expect(page.getByTestId("SF-08-grid-run-control-totals")).toBeVisible();
        // A long recorded value wraps: no table of the record is wider than the column it stands in.
        const wide = await page
          .getByTestId("SF-08-page")
          .locator("table")
          .evaluateAll((tables) =>
            tables
              .filter((table) => {
                const room = table.parentElement?.getBoundingClientRect().right ?? 0;
                return table.getBoundingClientRect().right > room + 0.5;
              })
              .map((table) => table.getAttribute("data-testid")),
          );
        expect(wide).toEqual([]);
        await expect(page.getByRole("link", { name: "Open report view" })).toHaveAttribute(
          "href",
          new RegExp(`^/reports/rpo\\?.*run=${runId}`),
        );
        await expect(page.getByRole("group", { name: "Accounting context" })).toBeVisible();
        await screens.capture(page, "sf-08-run", { surface: "SF-08:run" });
        await a11y.check(page, "SF-08:run");
      });

      await test.step("Rerun from the same source: output and control totals identical", async () => {
        await page.getByRole("button", { name: "Rerun from the same source" }).click();
        // RV-03: the job is followed on the record, and its result opens the new run.
        await expect(page).not.toHaveURL(new RegExp(`/reports/runs/${runId}$`), {
          timeout: 120_000,
        });
        await expect(page).toHaveURL(/\/reports\/runs\/[0-9a-f-]{36}$/);
        const result = page.getByTestId("SF-08-banner-rerun-result");
        await expect(
          result.getByRole("heading", { name: `Rerun of ${run.report_run_no}` }),
        ).toBeVisible();
        await expect(result.getByText("Output identical: Yes", { exact: true })).toBeVisible();
        await expect(
          result.getByText("Control totals identical: Yes", { exact: true }),
        ).toBeVisible();
        await expect(
          result.getByRole("link", { name: `Open ${run.report_run_no}` }),
        ).toHaveAttribute("href", `/reports/runs/${runId}`);
        await a11y.check(page, "SF-08:run", { state: "rerun-result" });
      });

      await test.step("who reads the run's job: its starter and a holder of audit.read", async () => {
        // 04 API-R-11, measured with three personas on the job of marcus's run: the record asks for
        // the job only where the API answers it (the rule `mayReadRunJob` binds).
        expect(run.job_id).not.toBeNull();
        const jobPath = `/api/v1/jobs/${run.job_id ?? ""}`;
        expect((await page.request.get(jobPath)).status(), "marcus, who started the run").toBe(200);
        // hannah (Auditor) holds `audit.read` and did not start the run.
        const hannah = await personas.page("hannah");
        expect((await hannah.request.get(jobPath)).status(), "hannah, audit.read").toBe(200);
        // robert (Viewer) may run and read reports, did not start the run and holds no `audit.read`.
        const robert = await personas.page("robert");
        expect(
          (await robert.request.get(`/api/v1/report-runs/${runId}`)).status(),
          "robert reads the run",
        ).toBe(200);
        expect((await robert.request.get(jobPath)).status(), "robert, the run's job").toBe(404);
        // The record of a run he did not start opens for him.
        await robert.goto(`/reports/runs/${runId}`);
        await expect(
          robert.getByRole("heading", { level: 1, name: `Report run ${run.report_run_no}` }),
        ).toBeVisible();
      });
    });
  });
});

/**
 * BUILD_SPEC RPS-7 (SCREENS_B §4.1, §0.5; §15 row SF-04). Under R-RC-1 the seeded AVM-US FY2026-P08 lock
 * moves to DMO (CLO-22 post-rc; SPRINT-vabc §6.2), so this world holds no lock (L7-3-Q-15): "SF-04 as locked"
 * and `sf-04-locked` are the closed world's (projects/closed.spec.ts, `make e2e CLOSE=1`; BUILD_SPEC rev
 * 1.76). The steps name the Sep 2026 context: the context pill writes no default book into a link,
 * and the first open AVM-JP period is Jan 2026, whose fiscal year holds no FY2027 quarter (L7-3-Q-20). K-10
 * `JP-LIC-0001` and the AVM-JP licences stay drafts (L5-4-Q-12), so AVM-JP has no schedule rows: "SF-04
 * quarter" asserts the quarter run over the April fiscal year and the §4.1 empty state, and the fiscal quarter
 * columns are asserted on AVM-US; the K-10 JPY figures first run when K-10 activates (L7-3-Q-21).
 */
test.describe("SF-04 Schedules (RT-25 /schedules), persona marcus", () => {
  test("SF-04 marcus", async ({ personas, screens, a11y }) => {
    const page = await personas.page("marcus");
    await test.step("SF-04 quarter", async () => {
      await page.goto("/schedules?entity=AVM-JP&period=FY2027-P06&book=ASC606&granularity=quarter");
      await expect(page.getByRole("heading", { level: 1, name: "Schedules" })).toBeVisible();
      await expect(page).toHaveURL(/[?&]run=[0-9a-f-]{36}(&|$)/, REPORT_RUN_WAIT);
      const runId = new URL(page.url()).searchParams.get("run") ?? "";
      await expect(page.getByTestId("SF-04-run-stamp")).toContainText(
        "Revenue waterfall v1",
        REPORT_RUN_WAIT,
      );
      // SCR-URL-24: the quarter granularity reaches the run over the April fiscal year FY2027.
      const stored = await json<{ readonly parameters: Readonly<Record<string, unknown>> }>(
        await page.request.get(`/api/v1/report-runs/${runId}`),
      );
      expect(stored.parameters).toMatchObject({
        entity_codes: ["AVM-JP"],
        granularity: "QUARTER",
        from_period_key: "FY2027-P01",
        to_period_key: "FY2027-P12",
      });
      const toolbar = page.getByTestId("SF-04-filter-bar");
      await expect(toolbar.getByRole("radio", { name: "Quarter" })).toBeChecked();
      await expect(toolbar.getByRole("combobox", { name: "From" })).toContainText("Apr 2026");
      await expect(toolbar.getByRole("combobox", { name: "To" })).toContainText("Mar 2027");
      await expect(
        page.getByRole("heading", { level: 2, name: "No schedules for Sep 2026" }),
      ).toBeVisible(REPORT_RUN_WAIT);
      await screens.capture(page, "sf-04-quarter", { surface: "SF-04" });
      await a11y.check(page, "SF-04 quarter");
    });

    await test.step("SF-04 fiscal quarter columns on AVM-US", async () => {
      await page.goto("/schedules?entity=AVM-US&period=FY2026-P09&book=ASC606&granularity=quarter");
      const grid = page
        .getByTestId("SF-04-grid-waterfall")
        .getByRole("grid", { name: "Revenue waterfall" });
      await expect(grid).toBeVisible(REPORT_RUN_WAIT);
      // WLD-P-05: a January fiscal year labels its quarters "Q<n> 2026".
      for (const header of ["Q1 2026 (USD)", "Q3 2026 (USD)", "Q4 2026 (USD)"]) {
        await expect(grid.getByRole("columnheader", { name: header })).toBeAttached();
      }
      await screens.capture(page, "sf-04-avm-us-quarter", { surface: "SF-04" });
      await expect.poll(() => clippedBoxes(grid)).toEqual([]);
      // Checked before scrolling: the grid's roving tab stop is row 0, which scrolling virtualises away.
      await a11y.check(page, "SF-04 AVM-US quarter");
      // The rows sort by external id, so K-01 enters the DOM once the grid scrolls to it (DG-FE-07).
      await expect(await scrolledReportRow(page, grid, K01, "SF-04")).toBeVisible();
    });

    await test.step("SF-04 opened from the rail without a context", async () => {
      // SCREENS SCR-URL-01 rev 1.61 (item RPT-VIEW-CONTEXT-DEFAULT-1). Approvals keeps no context in
      // its address (SCREENS §1.3), so the rail's link from there names none: Schedules takes the
      // context pill's — marcus's last choice, else BR-UX-01's default — writes it and asks one run
      // for that entity, where it used to ask one for every entity in scope.
      await page.goto("/approvals");
      const link = page
        .getByRole("navigation", { name: "Primary" })
        .getByRole("link", { name: "Schedules" });
      await expect(link).toHaveAttribute("href", "/schedules");
      await link.click();
      await expect(page).toHaveURL(
        /\/schedules\?entity=AVM-[A-Z]{2}&period=FY\d{4}-P\d{2}&book=[A-Z0-9]+&run=[0-9a-f-]{36}$/,
        REPORT_RUN_WAIT,
      );
      const address = new URL(page.url()).searchParams;
      const stored = await json<{ readonly parameters: Readonly<Record<string, unknown>> }>(
        await page.request.get(`/api/v1/report-runs/${address.get("run") ?? ""}`),
      );
      expect(stored.parameters).toMatchObject({
        entity_codes: [address.get("entity")],
        book: address.get("book"),
      });
      await expect(page.getByTestId("SF-04-run-stamp")).toContainText(
        "Revenue waterfall v1",
        REPORT_RUN_WAIT,
      );
    });
  });
});

/**
 * BUILD_SPEC RPS-21 (SCREENS_B §6.3, §6.4; §15 row SF-09:audit-log, SF-09:verification). The seed holds the
 * draft contract `PRJ-CB-2026-01` and no chain verification, so the step starts one with "Verify chain now"
 * (PRD J-17.5), captures the log under the header of the verified chain and opens the run's record. The
 * field-level diffs of the modification and estimate events of J-17.5 first run with DMO J-17.5. Item
 * AUD-SCREEN-BIND-1 (SCREENS_B rev 1.57): the object filter lists the trail of the contract — every event
 * that names it — and an event on the contract itself shows the contract's external id; the Outcome chip
 * reaches the API; and a link opens an event the filtered list does not hold, read alone by its sequence.
 */
test.describe("SF-09:audit-log Audit log (RT-37 /reports/audit-log, RT-38), persona hannah", () => {
  test("SF-09:audit-log hannah", async ({ personas, screens, a11y }) => {
    const page = await personas.page("hannah");
    await test.step("SF-09:audit-log and SF-09:verification", async () => {
      await test.step("the log filtered to object PRJ-CB-2026-01 lists the contract's trail", async () => {
        await page.goto("/reports/audit-log?f.object=is:PRJ-CB-2026-01");
        await expect(page.getByRole("heading", { level: 1, name: "Reports" })).toBeVisible();
        await expect(
          page
            .getByRole("navigation", { name: "Reports sections" })
            .getByRole("link", { name: "Audit log" }),
        ).toHaveAttribute("aria-current", "page");
        await expect(
          page.getByRole("button", { name: "Object is PRJ-CB-2026-01, edit filter" }),
        ).toBeVisible();
        const grid = page
          .getByTestId("SF-09-grid-audit-events")
          .getByRole("grid", { name: "Audit events" });
        await expect(grid).toBeVisible();
        // The trail is read whole, and the screen says so in place of the 30 days.
        await expect(
          page.getByText(
            "Showing every event that names PRJ-CB-2026-01. Add the Occurred filter to narrow the range.",
          ),
        ).toBeVisible();
        const rows = grid.getByRole("row").filter({ has: page.getByRole("rowheader") });
        await expect.poll(() => rows.count()).toBeGreaterThan(0);
        // An event on the contract itself names it by its external id, linked to the one contract.
        const objects = grid.getByRole("link", { name: "PRJ-CB-2026-01", exact: true });
        await expect.poll(() => objects.count()).toBeGreaterThan(0);
        const targets = await objects.evaluateAll((links) => [
          ...new Set(links.map((link) => link.getAttribute("href"))),
        ]);
        expect(targets).toHaveLength(1);
        expect(targets[0]).toMatch(/^\/contracts\/[0-9a-f-]{36}$/);
        await expect.poll(() => clippedBoxes(grid)).toEqual([]);
      });

      const header = page.getByTestId("SF-09-banner-chain");
      const verified = header.getByRole("link", {
        name: /^Audit chain verified \d{2} \w{3} \d{4} \d{2}:\d{2} UTC · [\d,]+ events$/,
      });
      await test.step("Verify chain now: the header shows Verified with the event count", async () => {
        await header.getByRole("button", { name: "Verify chain now" }).click();
        await expect(verified).toBeVisible({ timeout: 60_000 });
        await expect(header.getByText("Verified", { exact: true })).toBeVisible();
        const messages = page.getByRole("region", { name: "Messages" });
        const toast = messages.getByText(
          /^Audit chain verified: [\d,]+ events, last chain value [0-9a-f]{8}\.$/,
        );
        await expect(toast).toBeVisible();
        // The toast names the run it reports: "View details" opens that verification, and a toast with
        // an action stays until it is dismissed.
        await expect(messages.getByRole("button", { name: "View details" })).toBeVisible();
        await messages.getByRole("button", { name: "Dismiss message" }).click();
        await expect(toast).toHaveCount(0);
      });

      await test.step("the sequence opens the event drawer with the recorded values of the chain", async () => {
        // The top bar is complete before the capture (the context pill loads after the page).
        await expect(page.getByRole("group", { name: "Accounting context" })).toBeVisible();
        const grid = page
          .getByTestId("SF-09-grid-audit-events")
          .getByRole("grid", { name: "Audit events" });
        const rows = grid.getByRole("row").filter({ has: page.getByRole("rowheader") });
        const sequence = rows.first().getByRole("rowheader").getByRole("link");
        const label = (await sequence.innerText()).trim();
        await sequence.click();
        // SCR-URL-32 (SCREENS rev 1.20): the link names the event by its chain sequence, not its id.
        await expect(page).toHaveURL(
          new RegExp(`[?&]drawer=event&event=${label.replaceAll(",", "")}(&|$)`),
        );
        const drawer = page.getByTestId("SF-09-drawer-event");
        await expect(drawer.getByRole("heading", { name: `Event ${label}` })).toBeVisible();
        await expect(drawer.getByText("Recorded values")).toBeVisible();
        await screens.capture(page, "sf-09-audit-log", { surface: "SF-09:audit-log" });
        await a11y.check(page, "SF-09:audit-log");
        await drawer.getByRole("button", { name: "Close" }).click();
        await expect(drawer).toHaveCount(0);
        await expect(page).not.toHaveURL(/[?&]drawer=/);
      });

      await test.step("the Outcome chip filters the list, and a link opens an event it does not hold", async () => {
        const grid = page
          .getByTestId("SF-09-grid-audit-events")
          .getByRole("grid", { name: "Audit events" });
        const rows = grid.getByRole("row").filter({ has: page.getByRole("rowheader") });
        // An event that succeeded, by its sequence: the list of refused and failed events cannot hold it.
        const succeeded = rows
          .filter({ has: page.locator('[data-column="outcome"]', { hasText: "Succeeded" }) })
          .first();
        const label = (await succeeded.getByRole("rowheader").getByRole("link").innerText()).trim();
        const sequence = label.replaceAll(",", "");
        await page.goto(
          `/reports/audit-log?f.outcome=in:DENIED,FAILED&drawer=event&event=${sequence}`,
        );
        await expect(
          page.getByRole("button", { name: "Outcome is Denied or Failed, edit filter" }),
        ).toBeVisible();
        // The event is read alone by its sequence, whatever the filters of the list.
        const drawer = page.getByTestId("SF-09-drawer-event");
        await expect(drawer.getByRole("heading", { name: `Event ${label}` })).toBeVisible();
        await expect(drawer.getByText("Recorded values")).toBeVisible();
        await expect(drawer.getByText("Succeeded", { exact: true }).first()).toBeVisible();
        // The list under the chip: refused and failed events only, or none at all.
        const listed = page.getByTestId("SF-09-grid-audit-events");
        await expect(
          rows
            .first()
            .or(listed.getByRole("heading", { name: "No audit events match these filters" })),
        ).toBeVisible();
        await expect(
          rows.locator('[data-column="outcome"]').filter({ hasText: "Succeeded" }),
        ).toHaveCount(0);
        await expect(page.getByTestId(`SF-09-row-${sequence}`)).toHaveCount(0);
        await drawer.getByRole("button", { name: "Close" }).click();
        await expect(drawer).toHaveCount(0);
        await expect(page).toHaveURL(/\/reports\/audit-log\?f\.outcome=in:DENIED,FAILED$/);
        await page.goto("/reports/audit-log");
        await expect(page.getByTestId("SF-09-banner-chain")).toBeVisible();
      });

      await test.step("the latest verification record shows Verified and a digest download link", async () => {
        await verified.click();
        await expect(page).toHaveURL(/\/reports\/audit-log\/verifications\/[0-9a-f-]{36}$/);
        const record = page.getByRole("region", { name: "Audit chain verification", exact: true });
        await expect(
          record.getByRole("heading", { level: 1, name: "Audit chain verification" }),
        ).toBeVisible();
        await expect(record.getByText("Verified", { exact: true })).toBeVisible();
        await expect(record.getByText("On demand", { exact: true })).toBeVisible();
        await expect(page.getByTestId("SF-09-kpi-strip")).toContainText("Events checked");
        await expect(page.getByRole("link", { name: "Download digest" })).toHaveAttribute(
          "href",
          /^\/api\/v1\/files\/[0-9a-f-]{36}\/content$/,
        );
        await expect(
          page.getByTestId("SF-09-grid-verifications").getByText("On demand").first(),
        ).toBeVisible();
        await screens.capture(page, "sf-09-verification", { surface: "SF-09:verification" });
        await a11y.check(page, "SF-09:verification");
      });
    });
  });
});

/**
 * BUILD_SPEC DIN-18 (SCREENS §14; §0.12 rows SF-16, SF-16:connection, SF-16:sync-run). The demo seed holds no
 * connection (the item's seed file is another lane's), so the three tests reach the screens through the
 * product: `nikhil` adds a connection against the in-process Salesforce mock (its address is the API's
 * own origin followed by the mock router's path: the adapter client connects to an absolute address),
 * tests it and opens the run the test recorded. The connection stays Disabled and no poll is run: the mock serves the Quayside
 * scenario only, and polled into Avenmoor its orders would leave failure items and a failed run that the
 * interface close gate counts for every Avenmoor entity (rulings R-45 (d), R-56). The seeded "Salesforce
 * orders" and "NetSuite GL", the run with the control totals "1 order · 2 lines · USD 120,000.00" and the
 * captures of that seeded state are owed to the seed.
 */
test.describe("SF-16 Integrations (RT-48 /data/integrations, RT-49, RT-50), persona nikhil", () => {
  test.describe.configure({ mode: "serial" });
  const suffix = randomUUID().slice(0, 8);
  const connection = {
    code: `e2e-salesforce-${suffix}`,
    name: `Salesforce mock ${suffix}`,
    path: "",
  };
  // DG-E2E-01: the port of api-e2e, which serves the mock routers (05 ADP-20).
  const mockAddress = `http://127.0.0.1:${process.env.EREV_E2E_API_PORT ?? "8199"}/api/v1/__mocks__/salesforce`;

  test("SF-16 nikhil", async ({ personas, screens, a11y }) => {
    const page = await personas.page("nikhil");
    await page.goto("/data/integrations");
    await expect(page.getByRole("heading", { level: 1, name: "Integrations" })).toBeVisible();
    // The top bar is complete before the drawer opens over it (the context pill loads after the page).
    await expect(page.getByRole("group", { name: "Accounting context" })).toBeVisible();
    await expect(
      page
        .getByRole("navigation", { name: "Data sections" })
        .getByRole("link", { name: "Integrations" }),
    ).toHaveAttribute("aria-current", "page");

    await test.step("Add connection: the credential is a reference name, the connection starts Disabled", async () => {
      await page.getByRole("button", { name: "Add connection" }).first().click();
      const drawer = page.getByRole("dialog", { name: "Add connection" });
      await drawer.getByRole("combobox", { name: /^Adapter/ }).click();
      await page.getByRole("option", { name: "Salesforce", exact: true }).click();
      // SCREENS §14.4: Salesforce defaults to Inbound.
      await expect(drawer.getByRole("combobox", { name: /^Direction/ })).toContainText("Inbound");
      await drawer.getByRole("textbox", { name: /^Name/ }).fill(connection.name);
      await drawer.getByRole("textbox", { name: /^Code/ }).fill(connection.code);
      await drawer.getByRole("textbox", { name: /^Base URL/ }).fill(mockAddress);
      // SCREENS §14.4 (rev 1.13; 04 T-INT-01 rev 1.108): the workspace's namespace of the secret store
      // stands before the field, and the field holds the rest of the reference.
      await expect(
        drawer.getByText(/^tenant-[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}-$/),
      ).toBeVisible();
      await expect(
        drawer.getByText(
          "Enter the rest of the secret's name and its version number, for example netsuite-token@3. The secret itself is never stored. Leave the field empty for a connection that sends no credential.",
        ),
      ).toBeVisible();
      await screens.capture(page, "sf-16-add-connection", { surface: "SF-16" });

      // SCR-PERM-05: a command may ask for a step-up once.
      const stepUp = page.getByRole("dialog", { name: "Confirm with your authenticator" });
      const confirmStepUp = async () => {
        if (await stepUp.isVisible()) {
          const { code } = await nextCode(personaEmail("nikhil"));
          await stepUp.getByRole("textbox", { name: /^Authentication code/ }).fill(code);
          await stepUp.getByRole("button", { name: "Confirm" }).click();
        }
      };
      // A version without a name names no secret of the workspace: the API refuses the reference, and the
      // refusal is shown on the field in the API's words.
      const reference = drawer.getByRole("textbox", { name: /^Credential reference/ });
      await reference.fill("@1");
      await drawer.getByRole("button", { name: "Save connection" }).click();
      const refusal = drawer.getByText(
        /^Enter the name of a secret of this workspace\. It begins with tenant-[0-9a-f-]{36}- and continues after it\.$/,
      );
      await expect(refusal.or(stepUp)).toBeVisible();
      await confirmStepUp();
      await expect(refusal).toBeVisible();
      await expect(reference).toHaveAttribute("aria-invalid", "true");

      // The mock route takes no credential: the connection is saved without a reference.
      await reference.fill("");
      await drawer.getByRole("button", { name: "Save connection" }).click();
      const heading = page.getByRole("heading", { level: 1, name: connection.name });
      await expect(heading.or(stepUp)).toBeVisible();
      await confirmStepUp();
      await expect(heading).toBeVisible();
      await expect(page).toHaveURL(/\/data\/integrations\/[0-9a-f-]{36}$/);
      connection.path = new URL(page.url()).pathname;
    });

    await test.step("SF-16 list: the connection with the outline chip Mock", async () => {
      await page.goto("/data/integrations");
      const grid = page
        .getByTestId("SF-16-grid-connections")
        .getByRole("grid", { name: "Integrations" });
      await expect(grid).toBeVisible();
      const row = page.getByTestId(`SF-16-row-${connection.code}`);
      await expect(row.getByRole("link", { name: connection.name })).toHaveAttribute(
        "href",
        connection.path,
      );
      await expect(row).toContainText("Salesforce");
      await expect(row.getByText("Mock", { exact: true })).toBeVisible();
      await expect(row).toContainText("Inbound");
      await expect(row).toContainText("All entities");
      await expect(row.getByText("Disabled", { exact: true })).toBeVisible();
      await expect.poll(() => clippedBoxes(grid)).toEqual([]);
      await expect(page.getByRole("group", { name: "Accounting context" })).toBeVisible();
      await screens.capture(page, "sf-16", { surface: "SF-16" });
      await a11y.check(page, "SF-16");
    });
  });

  test("SF-16:connection nikhil", async ({ personas, screens, a11y }) => {
    const page = await personas.page("nikhil");
    await page.goto(connection.path);
    await expect(page.getByRole("heading", { level: 1, name: connection.name })).toBeVisible();
    await expect(page.getByText("This connection has not been tested.")).toBeVisible();
    // SCR-PERM-03: a disabled connection cannot sync, and says why.
    const sync = page.getByRole("button", { name: "Run sync" });
    await expect(sync).toHaveAttribute("aria-disabled", "true");

    await test.step("Test connection: Connection succeeded with the UTC time (J-01.13)", async () => {
      await page.getByRole("button", { name: "Test connection" }).click();
      const banner = page.getByTestId("SF-16-banner-test");
      await expect(
        banner.getByText(/^Connection succeeded · \d{2} \w{3} \d{4} \d{2}:\d{2} UTC$/),
      ).toBeVisible();
      await expect(banner.getByRole("status")).toBeVisible();
    });

    await test.step("Sync runs: the run the test recorded", async () => {
      const grid = page
        .getByTestId("SF-16-grid-sync-runs")
        .getByRole("grid", { name: "Sync runs" });
      await expect(grid).toBeVisible();
      const rows = grid.getByRole("row").filter({ has: page.getByRole("rowheader") });
      await expect(rows).toHaveCount(1);
      await expect(rows.first()).toContainText("Test connection");
      await expect(rows.first().getByText("Succeeded", { exact: true })).toBeVisible();
      await expect.poll(() => clippedBoxes(grid)).toEqual([]);
      await expect(page.getByRole("group", { name: "Accounting context" })).toBeVisible();
      await screens.capture(page, "sf-16-connection", { surface: "SF-16:connection" });
      await a11y.check(page, "SF-16:connection");
    });

    await test.step("Settings: the reference name only", async () => {
      await page.getByRole("tab", { name: "Settings" }).click();
      await expect(page).toHaveURL(/[?&]pane=settings(&|$)/);
      const pane = page.getByTestId("SF-16-pane-settings");
      await expect(pane.getByText(mockAddress)).toBeVisible();
      await expect(pane.getByText(connection.code, { exact: true })).toBeVisible();
    });
  });

  test("SF-16:sync-run nikhil", async ({ personas, screens, a11y }) => {
    const page = await personas.page("nikhil");
    await page.goto(connection.path);
    const grid = page.getByTestId("SF-16-grid-sync-runs").getByRole("grid", { name: "Sync runs" });
    await grid.getByRole("rowheader").first().getByRole("link").click();
    await expect(page).toHaveURL(/\/data\/integrations\/[0-9a-f-]{36}\/sync-runs\/[0-9a-f-]{36}$/);
    await expect(
      page.getByRole("heading", { level: 1, name: `Sync run · ${connection.name}` }),
    ).toBeVisible();
    await expect(
      page.getByTestId("SF-16-page").getByText("Succeeded", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Test connection", { exact: true })).toBeVisible();
    // A test asks the source one question and loads nothing: no totals, no exceptions.
    await expect(page.getByText("This run recorded no control totals.")).toBeVisible();
    await expect(page.getByText("This run raised no exceptions.")).toBeVisible();
    await expect(
      page
        .getByRole("navigation", { name: "Breadcrumb" })
        .getByRole("link", { name: connection.name }),
    ).toHaveAttribute("href", connection.path);
    await expect(page.getByRole("group", { name: "Accounting context" })).toBeVisible();
    await screens.capture(page, "sf-16-sync-run", { surface: "SF-16:sync-run" });
    await a11y.check(page, "SF-16:sync-run");
  });
});
