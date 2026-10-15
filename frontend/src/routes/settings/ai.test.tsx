// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { SCREEN_ROUTES } from "../../app/router";
import { installMemoryStorage, preloadScreens, renderApp, signedInMe } from "../../test/app";
import { apiUrl, installMswServer, server } from "../../test/msw";
import { aiPercentRatio } from "./ai";

installMswServer();
installMemoryStorage();
afterEach(cleanup);
beforeAll(() => preloadScreens(SCREEN_ROUTES, ["SF-15:ai"]));
const BASE = {
  "ai.enabled": false,
  "ai.send_contract_text": false,
  "ai.model": "reviewed-model",
  "ai.monthly_token_budget": 2000000,
  "ai.redact_contact_details": true,
  "ai.anomaly.revenue_change_ratio": "0.5",
  "ai.anomaly.revenue_ahead_of_billing_days": 60,
  "ai.anomaly.allocation_adjustment_ratio": "0.2",
};
type Call = { path: string; body: unknown; key: string | null; etag: string | null };
function serve(
  options: {
    pendingJob?: boolean;
    failedJob?: boolean;
    lostSubmit?: boolean;
    saved?: boolean;
    stale?: boolean;
    resetModel?: boolean;
    committedLoss?: boolean;
  } = {},
) {
  const calls: Call[] = [];
  let state = options.saved ? "DRAFT" : "";
  let lost = options.lostSubmit ?? false;
  let disabled = false;
  const version = () => ({
    id: "version-1",
    version_no: 2,
    status: state,
    row_version: 3,
    values: options.resetModel ? { ...BASE, "ai.model": undefined } : BASE,
    unset: options.resetModel ? ["ai.model"] : [],
    pending_approval_request_id: state === "SUBMITTED" ? "request-1" : null,
  });
  async function record(request: Request) {
    calls.push({
      path: new URL(request.url).pathname,
      body: await request.json(),
      key: request.headers.get("Idempotency-Key"),
      etag: request.headers.get("If-Match"),
    });
  }
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/books"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/approvals/request-1"), () =>
      HttpResponse.json({
        request_no: "APR-001",
        preparer: { display_name: "Workspace administrator" },
      }),
    ),
    http.get(apiUrl("/api/v1/tenant"), () =>
      HttpResponse.json({ id: "tenant-1", display_name: "Demo", setup_completed_at: "2026-01-01" }),
    ),
    http.get(apiUrl("/api/v1/ai/settings"), () =>
      HttpResponse.json({
        enabled: !disabled,
        registry_enabled: true,
        tenant_disabled_at: disabled ? "2026-10-15T12:00:00Z" : null,
        platform_disabled: false,
        workspace_active: true,
        provider: "fake",
        model: "reviewed-model",
        monthly_token_budget: 2000000,
        send_contract_text: false,
        redact_contact_details: true,
      }),
    ),
    http.get(apiUrl("/api/v1/ai/settings/values"), () =>
      HttpResponse.json({ values: BASE, defaults: { ...BASE, "ai.model": "default-model" } }),
    ),
    http.get(apiUrl("/api/v1/ai/settings/versions"), ({ request }) =>
      HttpResponse.json({
        items: new URL(request.url).searchParams.get("status") === state ? [version()] : [],
        next_cursor: null,
      }),
    ),
    http.post(apiUrl("/api/v1/ai/settings/versions"), async ({ request }) => {
      await record(request);
      state = "DRAFT";
      return HttpResponse.json(version(), { status: 201 });
    }),
    http.get(apiUrl("/api/v1/ai/settings/versions/version-1"), () =>
      HttpResponse.json(
        { ...version(), row_version: options.stale ? 4 : 3 },
        { headers: { ETag: options.stale ? '"r4"' : '"r3"' } },
      ),
    ),
    http.patch(apiUrl("/api/v1/ai/settings/versions/version-1"), async ({ request }) => {
      await record(request);
      if (options.stale)
        return HttpResponse.json(
          {
            type: "https://erev.dev/problems/precondition-failed",
            title: "Record changed",
            status: 412,
            detail: "Reload the changed version.",
            errors: [],
          },
          { status: 412, headers: { "Content-Type": "application/problem+json" } },
        );
      return HttpResponse.json(version());
    }),
    http.post(apiUrl("/api/v1/ai/settings/versions/version-1/test"), async ({ request }) => {
      await record(request);
      return HttpResponse.json({ id: "job-1" }, { status: 202 });
    }),
    http.get(apiUrl("/api/v1/jobs/job-1"), () =>
      HttpResponse.json({
        id: "job-1",
        state:
          options.pendingJob && !disabled ? "QUEUED" : options.failedJob ? "FAILED" : "SUCCEEDED",
        problem: null,
      }),
    ),
    http.post(apiUrl("/api/v1/ai/settings/versions/version-1/submit"), async ({ request }) => {
      await record(request);
      if (lost) {
        lost = false;
        if (options.committedLoss) state = "SUBMITTED";
        return HttpResponse.error();
      }
      state = "SUBMITTED";
      return HttpResponse.json(version());
    }),
    http.post(apiUrl("/api/v1/tenant/ai/disable"), async ({ request }) => {
      await record(request);
      disabled = true;
      return HttpResponse.json({ ai_disabled_at: "2026-10-15T12:00:00Z" });
    }),
  );
  return calls;
}
function renderSettings(permissions = ["settings.manage"]) {
  const me = signedInMe({ permissions });
  server.use(http.get(apiUrl("/api/v1/me"), () => HttpResponse.json(me)));
  return renderApp("/settings/ai", {
    me,
    screenRoutes: SCREEN_ROUTES,
  });
}
async function submitForm() {
  const form = await screen.findByRole("form", { name: "Change settings" });
  fireEvent.change(within(form).getByRole("textbox", { name: "Comment" }), {
    target: { value: "Reviewed settings for this workspace" },
  });
  fireEvent.click(within(form).getByRole("button", { name: "Submit for approval" }));
}

describe("AI settings", () => {
  it("submits only after validation, with the server ETag and an approval link", async () => {
    const calls = serve();
    renderSettings();
    await submitForm();
    expect(await screen.findByText("Submitted AI settings for approval.")).toBeTruthy();
    expect((await screen.findByRole("link", { name: "View request" })).getAttribute("href")).toBe(
      "/approvals/requests/request-1",
    );
    expect(calls.map((c) => c.path)).toEqual([
      "/api/v1/ai/settings/versions",
      "/api/v1/ai/settings/versions/version-1",
      "/api/v1/ai/settings/versions/version-1/test",
      "/api/v1/ai/settings/versions/version-1/submit",
    ]);
    expect(calls[1]?.etag).toBe('"r3"');
    expect(calls[2]?.body).toEqual({ run_simulation: true });
    expect(calls.every((c) => c.key !== null)).toBe(true);
  });
  it("resumes a saved draft without creating another version", async () => {
    const calls = serve({ saved: true });
    renderSettings();
    await submitForm();
    expect(await screen.findByText("Submitted AI settings for approval.")).toBeTruthy();
    expect(calls.some((c) => c.path === "/api/v1/ai/settings/versions")).toBe(false);
  });
  it("retries a lost submission with the same key and does not repeat creation or validation", async () => {
    const calls = serve({ lostSubmit: true });
    renderSettings();
    await submitForm();
    const retry = await screen.findByRole("button", { name: "Retry submission" });
    // Wait for the request failure to release the form's loading state.
    await screen.findByText("Failed to fetch");
    fireEvent.click(retry);
    expect(await screen.findByText("Submitted AI settings for approval.")).toBeTruthy();
    const submissions = calls.filter((c) => c.path.endsWith("/submit"));
    expect(submissions).toHaveLength(2);
    expect(submissions[0]?.key).toBe(submissions[1]?.key);
    expect(calls.filter((c) => c.path.endsWith("/test"))).toHaveLength(1);
    expect(calls.filter((c) => c.path === "/api/v1/ai/settings/versions")).toHaveLength(1);
  });
  it("replays its submission key after the server committed but the response was lost", async () => {
    const calls = serve({ lostSubmit: true, committedLoss: true });
    renderSettings();
    await submitForm();
    await screen.findByText("Failed to fetch");
    fireEvent.click(screen.getByRole("button", { name: "Retry submission" }));
    expect(await screen.findByText("Submitted AI settings for approval.")).toBeTruthy();
    const submissions = calls.filter((c) => c.path.endsWith("/submit"));
    expect(submissions).toHaveLength(2);
    expect(submissions[0]?.key).toBe(submissions[1]?.key);
  });
  it("restores a saved reset-to-default rather than the published model", async () => {
    serve({ saved: true, resetModel: true });
    renderSettings();
    const form = await screen.findByRole("form", { name: "Change settings" });
    expect((within(form).getByRole("textbox", { name: "Model" }) as HTMLInputElement).value).toBe(
      "default-model",
    );
  });
  it("refuses invalid token budgets before creating a version", async () => {
    const calls = serve();
    renderSettings();
    const form = await screen.findByRole("form", { name: "Change settings" });
    fireEvent.change(within(form).getByRole("textbox", { name: "Monthly token budget" }), {
      target: { value: "-1" },
    });
    await submitForm();
    expect(await screen.findByText("Enter a whole number of tokens, 0 or more.")).toBeTruthy();
    expect(calls).toHaveLength(0);
  });
  it("does not submit after a failed validation job", async () => {
    const calls = serve({ failedJob: true });
    renderSettings();
    await submitForm();
    expect(
      await screen.findByText(
        "Validation did not succeed. Reload the saved version before trying again.",
      ),
    ).toBeTruthy();
    expect(calls.some((c) => c.path.endsWith("/submit"))).toBe(false);
  });
  it("refuses a stale draft instead of submitting or using a newer version", async () => {
    const calls = serve({ saved: true, stale: true });
    renderSettings();
    await submitForm();
    expect(await screen.findByText("Reload the changed version.")).toBeTruthy();
    expect(calls).toHaveLength(1);
    expect(calls[0]?.etag).toBe('"r3"');
  });
  it("keeps emergency disable available while validation is running", async () => {
    const calls = serve({ pendingJob: true });
    renderSettings();
    await submitForm();
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/test"))).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: "Turn off AI now" }));
    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Turn off AI now" }));
    expect(await screen.findByText("AI assistance turned off.")).toBeTruthy();
    expect(calls.some((c) => c.path === "/api/v1/tenant/ai/disable")).toBe(true);
    expect(await screen.findByText("Submitted AI settings for approval.")).toBeTruthy();
  });
  it("requires confirmation before immediate disable", async () => {
    const calls = serve();
    renderSettings();
    fireEvent.click(await screen.findByRole("button", { name: "Turn off AI now" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(calls).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole("button", { name: "Turn off AI now" }));
    expect(await screen.findByText("AI assistance turned off.")).toBeTruthy();
    expect(calls.map((c) => c.path)).toEqual(["/api/v1/tenant/ai/disable"]);
  });
  it("does not show the form to a non-administrator", async () => {
    serve();
    renderSettings(["config.read"]);
    expect(await screen.findByText(/You do not have access to AI assistance/)).toBeTruthy();
    expect(screen.queryByRole("form", { name: "Change settings" })).toBeNull();
  });
  it("converts percent inputs exactly and rejects values outside policy bounds", () => {
    expect(aiPercentRatio("1000", 1000)).toBe("10");
    expect(aiPercentRatio("20.125", 100)).toBe("0.20125");
    expect(aiPercentRatio("100.0001", 100)).toBeNull();
    expect(aiPercentRatio("-1", 100)).toBeNull();
  });
});
