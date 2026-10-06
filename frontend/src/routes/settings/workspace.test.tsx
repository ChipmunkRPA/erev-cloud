// @vitest-environment jsdom
// SF-15:workspace (BUILD_SPEC RFD-19; SCREENS_B §9.6 data bindings, field table and test hooks; 04 API-R-13
// `GET /policies/resolve`, `POST /policies`, `/test`, `/submit`; API-R-17 `GET, PATCH /tenant`): the
// registry versions per changed category, the field validation copy, the read-only viewer and the
// percentage conversion without JavaScript numbers.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { accessDescription } from "../../test/access";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { percentToRatio, ratioToPercent, workspaceChanges, WORKSPACE_FIELDS } from "./workspace";

installMswServer();
installMemoryStorage();

afterEach(() => {
  cleanup();
});

/** WLD-T-01 values (SCREENS_B §9.6 sample world) and the T-PLT-31 defaults. */
const RESOLVED: Readonly<Record<string, unknown>> = {
  "ui.negative_number_style": "PARENTHESES",
  "close.require_reconciliations_for_lock": true,
  "close.unacknowledged_export_block_days": 5,
  "close.late_entry_window_days": 5,
  "close.rollforward_other_threshold_ratio": "0.01",
  "close.dq_revenue_without_billing_days": 60,
  "close.dq_inactive_contract_days": 90,
  "platform.job_concurrency": 4,
  "platform.audit_retention_years": 7,
  "approval.ssp_second_approver_threshold_ratio": "0.10",
  "data.quarantine_failed_rows": false,
  "integration.grouping_fields": ["order_number"],
  "disclosure.mandatory_disaggregation_attributes": [],
};

const TENANT = {
  id: "0b6f3e2d-1c4a-4b8e-9d7f-6a5c4b3e2d1f",
  code: "avenmoor",
  kind: "production",
  status: "ACTIVE",
  display_name: "Avenmoor Holdings (Demo)",
  reporting_currency: "USD",
  is_demo: true,
  setup_completed_at: "2026-09-01T12:00:00Z",
  row_version: 3,
};

interface Call {
  readonly path: string;
  readonly body: unknown;
}

/** The screen's reads, and `POST /policies` → `/test` (job) → `/submit`, recorded in order. */
function serveWorkspace(calls: Call[]) {
  let versions = 0;
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    // The top bar's context pill: a workspace without entities renders no pill.
    http.get(apiUrl("/api/v1/entities"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/books"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/tenant"), () => HttpResponse.json(TENANT)),
    http.get(apiUrl("/api/v1/policies/resolve"), ({ request }) => {
      const key = new URL(request.url).searchParams.get("key") ?? "";
      return HttpResponse.json({
        key,
        value: RESOLVED[key],
        level: "TENANT",
        source: { type: "REGISTRY_VERSION", id: null },
        is_forced: false,
        known_at: "2026-09-13T08:00:00Z",
        chain: [],
      });
    }),
    http.get(apiUrl("/api/v1/policies"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.post(apiUrl("/api/v1/policies"), async ({ request }) => {
      versions += 1;
      calls.push({ path: "/api/v1/policies", body: await request.json() });
      return HttpResponse.json(
        { id: `version-${String(versions)}`, status: "DRAFT" },
        { status: 201 },
      );
    }),
    http.post(apiUrl("/api/v1/policies/:versionId/test"), async ({ request, params }) => {
      calls.push({
        path: `/api/v1/policies/${String(params.versionId)}/test`,
        body: await request.json(),
      });
      return HttpResponse.json(
        { id: `job-${String(params.versionId)}`, kind: "POLICY_SIMULATION", state: "QUEUED" },
        { status: 202, headers: { Location: `/api/v1/jobs/job-${String(params.versionId)}` } },
      );
    }),
    http.get(apiUrl("/api/v1/jobs/:jobId"), ({ params }) =>
      HttpResponse.json({
        id: params.jobId,
        kind: "POLICY_SIMULATION",
        state: "SUCCEEDED",
        problem: null,
      }),
    ),
    http.post(apiUrl("/api/v1/policies/:versionId/submit"), async ({ request, params }) => {
      calls.push({
        path: `/api/v1/policies/${String(params.versionId)}/submit`,
        body: await request.json(),
      });
      return HttpResponse.json({ id: params.versionId, status: "SUBMITTED" });
    }),
  );
}

const ADMIN_AUTHOR = signedInMe({
  permissions: ["settings.manage", "config.read", "config.author"],
});

function renderWorkspace(me = ADMIN_AUTHOR) {
  return renderApp("/settings/workspace", { me, screenRoutes: SCREEN_ROUTES });
}

describe("SF-15:workspace", () => {
  it("submit creates registry versions per category", async () => {
    const calls: Call[] = [];
    serveWorkspace(calls);
    renderWorkspace();

    expect(
      await screen.findByRole("heading", { level: 1, name: "Workspace settings" }),
    ).toBeTruthy();
    const form = await screen.findByRole("form", { name: "Workspace settings" });
    expect(form.getAttribute("data-testid")).toBe("SF-15-workspace-form");
    const style = within(form).getByRole("radiogroup", { name: "Negative amounts" });
    expect(style.getAttribute("data-testid")).toBe("SF-15-workspace-negative-style");
    const parentheses = within(style).getByRole("radio", { name: "Parentheses, (4,000.00)" });
    expect((parentheses as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole("textbox", { name: "Name" }) as HTMLInputElement).value).toBe(
      "Avenmoor Holdings (Demo)",
    );

    fireEvent.click(within(style).getByRole("radio", { name: "Minus sign, −4,000.00" }));
    fireEvent.change(within(form).getByRole("textbox", { name: "Comment" }), {
      target: { value: "Minus sign for the board pack" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Submit for approval" }));

    expect(await screen.findByText("Submitted workspace settings for approval.")).toBeTruthy();
    expect(calls).toEqual([
      {
        path: "/api/v1/policies",
        body: {
          category: "PLATFORM",
          scope: "TENANT",
          values: { "ui.negative_number_style": "MINUS" },
        },
      },
      { path: "/api/v1/policies/version-1/test", body: { run_simulation: false } },
      {
        path: "/api/v1/policies/version-1/submit",
        body: { comment: "Minus sign for the board pack" },
      },
    ]);
  });

  // DG-FE-05 rev 1.156 (item W-23): one press creates a version, tests it and submits it. When the
  // submission gets no answer, the second press must not create a second version.
  it("the submission gets no answer: the second press sends the version, its test and its submission under the keys they had", async () => {
    serveWorkspace([]);
    const sent: { readonly path: string; readonly key: string | null }[] = [];
    let lose = true;
    server.use(
      http.post(apiUrl("/api/v1/policies"), ({ request }) => {
        sent.push({ path: "/api/v1/policies", key: request.headers.get("Idempotency-Key") });
        // What the API answers to the first send, and replays to the second under the same key.
        return HttpResponse.json({ id: "version-1", status: "DRAFT" }, { status: 201 });
      }),
      http.post(apiUrl("/api/v1/policies/:versionId/test"), ({ request, params }) => {
        sent.push({
          path: `/api/v1/policies/${String(params.versionId)}/test`,
          key: request.headers.get("Idempotency-Key"),
        });
        return HttpResponse.json(
          { id: "job-version-1", kind: "POLICY_SIMULATION", state: "QUEUED" },
          { status: 202, headers: { Location: "/api/v1/jobs/job-version-1" } },
        );
      }),
      http.post(apiUrl("/api/v1/policies/:versionId/submit"), ({ request, params }) => {
        sent.push({
          path: `/api/v1/policies/${String(params.versionId)}/submit`,
          key: request.headers.get("Idempotency-Key"),
        });
        if (lose) {
          lose = false;
          return HttpResponse.error();
        }
        return HttpResponse.json({ id: params.versionId, status: "SUBMITTED" });
      }),
    );
    renderWorkspace();

    const form = await screen.findByRole("form", { name: "Workspace settings" });
    const style = within(form).getByRole("radiogroup", { name: "Negative amounts" });
    fireEvent.click(within(style).getByRole("radio", { name: "Minus sign, −4,000.00" }));
    fireEvent.change(within(form).getByRole("textbox", { name: "Comment" }), {
      target: { value: "Minus sign for the board pack" },
    });
    const press = within(form).getByRole("button", { name: "Submit for approval" });
    fireEvent.click(press);

    // First press: the version exists and is tested, the submission's answer is lost. The form says
    // so and keeps its input.
    expect(await screen.findByText("No answer came back from the server. Try again.")).toBeTruthy();
    expect(
      (within(form).getByRole("textbox", { name: "Comment" }) as HTMLTextAreaElement).value,
    ).toBe("Minus sign for the board pack");
    await waitFor(() => {
      expect(press.getAttribute("aria-busy")).not.toBe("true");
    });

    fireEvent.click(press);
    expect(await screen.findByText("Submitted workspace settings for approval.")).toBeTruthy();
    expect(sent.map((item) => item.path)).toEqual([
      "/api/v1/policies",
      "/api/v1/policies/version-1/test",
      "/api/v1/policies/version-1/submit",
      "/api/v1/policies",
      "/api/v1/policies/version-1/test",
      "/api/v1/policies/version-1/submit",
    ]);
    // Second press: every step under its old key — the API replays the version and its test, and the
    // submission is for the same version.
    expect(sent[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
    expect(sent.slice(3).map((item) => item.key)).toEqual(sent.slice(0, 3).map((item) => item.key));
    expect(new Set(sent.slice(0, 3).map((item) => item.key)).size).toBe(3);
  });

  it("changes in two categories create two versions; invalid values and a short comment stop the submit", async () => {
    const calls: Call[] = [];
    serveWorkspace(calls);
    renderWorkspace();

    const form = await screen.findByRole("form", { name: "Workspace settings" });
    const lateEntry = within(form).getByRole("textbox", { name: "Late-entry window" });
    fireEvent.change(lateEntry, { target: { value: "40" } });
    fireEvent.change(within(form).getByRole("textbox", { name: "Comment" }), {
      target: { value: "Short" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Submit for approval" }));
    expect((await within(form).findAllByText("Enter 0 to 31 days.")).length).toBeGreaterThan(0);
    expect(within(form).getAllByText("Enter at least 10 characters.").length).toBeGreaterThan(0);
    expect(calls).toEqual([]);

    fireEvent.change(lateEntry, { target: { value: "7" } });
    fireEvent.click(within(form).getByRole("checkbox", { name: "Quarantine failed import rows" }));
    fireEvent.change(within(form).getByRole("textbox", { name: "SSP second-approver threshold" }), {
      target: { value: "12.5" },
    });
    fireEvent.change(within(form).getByRole("textbox", { name: "Comment" }), {
      target: { value: "Close window and quarantine" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Submit for approval" }));

    await waitFor(() => {
      expect(
        calls.filter((call) => call.path === "/api/v1/policies").map((call) => call.body),
      ).toEqual([
        {
          category: "PLATFORM",
          scope: "TENANT",
          values: { "approval.ssp_second_approver_threshold_ratio": "0.125" },
        },
        { category: "CLOSE", scope: "TENANT", values: { "close.late_entry_window_days": 7 } },
        {
          category: "INTEGRATION",
          scope: "TENANT",
          values: { "data.quarantine_failed_rows": true },
        },
      ]);
    });
    expect(await screen.findByText("Submitted workspace settings for approval.")).toBeTruthy();
    expect(calls.filter((call) => call.path.endsWith("/submit")).length).toBe(3);
  });

  // docs/dev-guide.md DG-FE-06 rev 1.228 (item KIT-UNPLACED-ERRORS-1): a refused step of the submission
  // is shown with every sentence of the refusal; before, the banner read its title and nothing else.
  it("a refused version says every sentence of the refusal in the form's banner", async () => {
    const calls: Call[] = [];
    serveWorkspace(calls);
    server.use(
      http.post(apiUrl("/api/v1/policies"), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            {
              field: "values.ui.negative_number_style",
              sheet: null,
              row: null,
              rule_id: null,
              message: "A workspace in the legacy-parity preset keeps parentheses.",
            },
          ],
        }),
      ),
    );
    renderWorkspace();
    const form = await screen.findByRole("form", { name: "Workspace settings" });
    const style = within(form).getByRole("radiogroup", { name: "Negative amounts" });
    fireEvent.click(within(style).getByRole("radio", { name: "Minus sign, −4,000.00" }));
    fireEvent.change(within(form).getByRole("textbox", { name: "Comment" }), {
      target: { value: "Minus sign for the board pack" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Submit for approval" }));

    const banner = await within(form).findByRole("alert");
    expect(
      within(banner).getByRole("heading", { name: "Check the highlighted fields" }),
    ).toBeTruthy();
    expect(
      within(banner).getByText("A workspace in the legacy-parity preset keeps parentheses."),
    ).toBeTruthy();
  });

  it("a refused name says at the field what names it and in the banner what names another member", async () => {
    serveWorkspace([]);
    server.use(
      http.patch(apiUrl("/api/v1/tenant"), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            {
              field: "display_name",
              sheet: null,
              row: null,
              rule_id: null,
              message: "Use 1 to 200 characters.",
            },
            {
              field: "row_version",
              sheet: null,
              row: null,
              rule_id: null,
              message: "The workspace is being copied; try again when the copy has ended.",
            },
          ],
        }),
      ),
    );
    renderWorkspace();
    const name = await screen.findByRole("textbox", { name: "Name" });
    fireEvent.change(name, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save name" }));

    expect(await screen.findByText("Use 1 to 200 characters.")).toBeTruthy();
    expect(screen.getAllByText("Use 1 to 200 characters.")).toHaveLength(1);
    expect(name.getAttribute("aria-invalid")).toBe("true");
    // The field's own message is an alert too: the banner is the one with the refusal's title.
    const banner = screen
      .getByRole("heading", { name: "Check the highlighted fields" })
      .closest<HTMLElement>('[role="alert"]');
    expect(banner).not.toBeNull();
    expect(
      within(banner ?? document.body).getByText(
        "The workspace is being copied; try again when the copy has ended.",
      ),
    ).toBeTruthy();
    expect(within(banner ?? document.body).queryByText("Use 1 to 200 characters.")).toBeNull();
  });

  it("settings.manage without config.author sees the values read-only without a submit control", async () => {
    serveWorkspace([]);
    renderWorkspace(signedInMe({ permissions: ["settings.manage", "config.read"] }));

    const form = await screen.findByRole("form", { name: "Workspace settings" });
    expect(
      within(form)
        .getByRole("radiogroup", { name: "Negative amounts" })
        .getAttribute("aria-readonly"),
    ).toBe("true");
    expect(within(form).queryByRole("button", { name: "Submit for approval" })).toBeNull();
    expect(
      (within(form).getByRole("textbox", { name: "Job concurrency" }) as HTMLInputElement).readOnly,
    ).toBe(true);
    // Workspace identity: code, kind, reporting currency and the demo flag.
    expect(screen.getByText("avenmoor")).toBeTruthy();
    expect(screen.getByText("Production")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save name" })).toBeTruthy();
  });

  // W-12e: the workspace is one for all entities. A holder of settings.manage for one entity sent
  // `GET /tenant`, was refused, and was shown a load-error banner with "Retry" in place of the page.
  it("settings.manage for one entity alone: the page says that workspace settings cover every entity, and with config.read the values show without the tenant being asked", async () => {
    const asked: string[] = [];
    const record = () =>
      server.use(
        http.get(apiUrl("/api/v1/*"), ({ request }) => {
          asked.push(new URL(request.url).pathname);
        }),
      );
    serveWorkspace([]);
    record();
    renderWorkspace(
      signedInMe({
        permissions: ["settings.manage"],
        permission_scopes: { "settings.manage": ["0a1b2c3d-4e5f-4a6b-8c7d-0000000000de"] },
      }),
    );
    expect(
      await screen.findByRole("heading", { name: "You do not have access to Workspace settings" }),
    ).toBeTruthy();
    expect(accessDescription()).toBe(
      "Workspace settings cover every entity of the workspace. Ask a workspace administrator for a role that includes managing workspace settings (settings.manage) for all entities.",
    );
    expect(asked.filter((path) => path === "/api/v1/tenant")).toEqual([]);
    cleanup();

    serveWorkspace([]);
    record();
    renderWorkspace(
      signedInMe({
        permissions: ["settings.manage", "config.read"],
        permission_scopes: {
          "settings.manage": ["0a1b2c3d-4e5f-4a6b-8c7d-0000000000de"],
          "config.read": "*",
        },
      }),
    );
    const form = await screen.findByRole("form", { name: "Workspace settings" });
    expect(
      (within(form).getByRole("textbox", { name: "Job concurrency" }) as HTMLInputElement).readOnly,
    ).toBe(true);
    expect(screen.queryByRole("button", { name: "Save name" })).toBeNull();
    expect(asked.filter((path) => path === "/api/v1/tenant")).toEqual([]);
  });

  // SCREENS_B §9.6 rev 1.102 (item POLICY-TENANT-SCOPE-ALL-ENTITIES-1; 04 §16.5 rev 1.309): the form
  // states TENANT versions, which a member authors only with `config.author` for ALL entities. Before
  // the item a member whose permission names one entity was given the controls and her submission
  // was accepted (04 rev 1.309); with the API's refusal alone her submit would have been refused.
  it("config.author for named entities sees the values read-only without a submit control", async () => {
    serveWorkspace([]);
    renderWorkspace(
      signedInMe({
        permissions: ["settings.manage", "config.read", "config.author"],
        permission_scopes: {
          "settings.manage": "*",
          "config.read": "*",
          "config.author": ["3f2a1b0c-9d8e-4f7a-8b6c-5d4e3f2a1b0c"],
        },
      }),
    );

    const form = await screen.findByRole("form", { name: "Workspace settings" });
    expect(
      within(form)
        .getByRole("radiogroup", { name: "Negative amounts" })
        .getAttribute("aria-readonly"),
    ).toBe("true");
    expect(within(form).queryByRole("button", { name: "Submit for approval" })).toBeNull();
    expect(
      (within(form).getByRole("textbox", { name: "Job concurrency" }) as HTMLInputElement).readOnly,
    ).toBe(true);
    // The workspace's name is `settings.manage`'s, as before.
    expect(screen.getByRole("button", { name: "Save name" })).toBeTruthy();
  });

  // SCREENS_B §9.6 rev 1.94 (item POLICY-WITHDRAW-ROUTES-1; the supervisor's ruling of 2026-10-02):
  // one version of a category is open at a time (PRD SM-04) and the form creates a new one. A DRAFT
  // or TESTED version — a request withdrawn on the version's page, a submission that stopped
  // half-way — is withdrawn or deleted by no command: before, the form sent the create, showed the
  // refusal and gave no way to the version.
  const OPEN_PLATFORM = {
    id: "0e0e0e0e-0e0e-4e0e-8e0e-0e0e0e0e0e0e",
    category: "PLATFORM",
    scope: "TENANT",
    status: "TESTED",
    version_no: 4,
    pending_approval_request_id: null,
  };
  const OPEN_SENTENCE = "Version 4 of Platform is open. Finish it on its page.";

  it("an open version of a category is named with the link to its page, and that category is not submitted", async () => {
    const calls: Call[] = [];
    serveWorkspace(calls);
    server.use(
      http.get(apiUrl("/api/v1/policies"), () =>
        HttpResponse.json({ items: [OPEN_PLATFORM], next_cursor: null }),
      ),
    );
    renderWorkspace();

    const form = await screen.findByRole("form", { name: "Workspace settings" });
    const notice = (await screen.findByRole("heading", { name: OPEN_SENTENCE })).closest(
      "[data-tone]",
    ) as HTMLElement;
    expect(within(notice).getByRole("link", { name: "Open version 4" }).getAttribute("href")).toBe(
      `/policies/accounting/${OPEN_PLATFORM.id}`,
    );

    // A PLATFORM value alone: nothing is sent, and the form says what stands in its way.
    fireEvent.change(within(form).getByRole("textbox", { name: "Job concurrency" }), {
      target: { value: "6" },
    });
    fireEvent.change(within(form).getByRole("textbox", { name: "Comment" }), {
      target: { value: "More workers for the close week" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Submit for approval" }));
    expect(await within(form).findByText(OPEN_SENTENCE)).toBeTruthy();
    expect(calls).toEqual([]);

    // With a CLOSE value beside it the CLOSE version goes through: the notice is the category's.
    fireEvent.change(within(form).getByRole("textbox", { name: "Late-entry window" }), {
      target: { value: "7" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Submit for approval" }));
    expect(await screen.findByText("Submitted workspace settings for approval.")).toBeTruthy();
    expect(calls.map((call) => [call.path, call.body])).toEqual([
      [
        "/api/v1/policies",
        { category: "CLOSE", scope: "TENANT", values: { "close.late_entry_window_days": 7 } },
      ],
      ["/api/v1/policies/version-1/test", { run_simulation: false }],
      ["/api/v1/policies/version-1/submit", { comment: "More workers for the close week" }],
    ]);
    expect(within(form).getByText(OPEN_SENTENCE)).toBeTruthy();
  });

  it("the versions are read again before anything is sent", async () => {
    // The form was opened before the request was withdrawn on the version's page.
    const calls: Call[] = [];
    let listed: readonly unknown[] = [];
    serveWorkspace(calls);
    server.use(
      http.get(apiUrl("/api/v1/policies"), () =>
        HttpResponse.json({ items: listed, next_cursor: null }),
      ),
    );
    renderWorkspace();

    const form = await screen.findByRole("form", { name: "Workspace settings" });
    expect(screen.queryByRole("heading", { name: OPEN_SENTENCE })).toBeNull();
    fireEvent.change(within(form).getByRole("textbox", { name: "Job concurrency" }), {
      target: { value: "6" },
    });
    fireEvent.change(within(form).getByRole("textbox", { name: "Comment" }), {
      target: { value: "More workers for the close week" },
    });
    listed = [{ ...OPEN_PLATFORM, status: "DRAFT" }];
    fireEvent.click(within(form).getByRole("button", { name: "Submit for approval" }));

    expect(await screen.findByRole("heading", { name: OPEN_SENTENCE })).toBeTruthy();
    expect(await within(form).findByText(OPEN_SENTENCE)).toBeTruthy();
    expect(calls).toEqual([]);
  });

  /** A submission of "Negative amounts" whose steps answer as `answer` says; the versions listed are `listed()`. */
  function serveSubmission(
    listed: () => readonly unknown[],
    answer: (step: "create" | "test" | "submit", nth: number) => Response | undefined,
  ) {
    const sent: { readonly step: string; readonly key: string | null }[] = [];
    const count = (step: string) => sent.filter((item) => item.step === step).length;
    server.use(
      http.get(apiUrl("/api/v1/policies"), () =>
        HttpResponse.json({ items: listed(), next_cursor: null }),
      ),
      http.post(apiUrl("/api/v1/policies"), ({ request }) => {
        sent.push({ step: "create", key: request.headers.get("Idempotency-Key") });
        return (
          answer("create", count("create")) ??
          HttpResponse.json({ id: OPEN_PLATFORM.id, status: "DRAFT" }, { status: 201 })
        );
      }),
      http.post(apiUrl("/api/v1/policies/:versionId/test"), ({ request }) => {
        sent.push({ step: "test", key: request.headers.get("Idempotency-Key") });
        return (
          answer("test", count("test")) ??
          HttpResponse.json(
            { id: "job-1", kind: "POLICY_SIMULATION", state: "QUEUED" },
            { status: 202, headers: { Location: "/api/v1/jobs/job-1" } },
          )
        );
      }),
      http.post(apiUrl("/api/v1/policies/:versionId/submit"), ({ request, params }) => {
        sent.push({ step: "submit", key: request.headers.get("Idempotency-Key") });
        return (
          answer("submit", count("submit")) ??
          HttpResponse.json({ id: params.versionId, status: "SUBMITTED" })
        );
      }),
    );
    return sent;
  }

  async function changeNegativeStyle(): Promise<HTMLElement> {
    const form = await screen.findByRole("form", { name: "Workspace settings" });
    const style = within(form).getByRole("radiogroup", { name: "Negative amounts" });
    fireEvent.click(within(style).getByRole("radio", { name: "Minus sign, −4,000.00" }));
    fireEvent.change(within(form).getByRole("textbox", { name: "Comment" }), {
      target: { value: "Minus sign for the board pack" },
    });
    return within(form).getByRole("button", { name: "Submit for approval" });
  }

  it.each([
    { name: "its submission", lost: "submit" as const },
    { name: "its create", lost: "create" as const },
  ])(
    "a press that got no answer to $name is continued under its keys, though its version is open",
    async ({ lost }) => {
      // DG-FE-05 rev 1.156: the version the first press created is open and is this form's. The
      // read before the second press lists it, and must not hold the press that continues it.
      serveWorkspace([]);
      let listed: readonly unknown[] = [];
      const sent = serveSubmission(
        () => listed,
        (step, nth) => {
          if (step === "create") {
            listed = [{ ...OPEN_PLATFORM, status: "DRAFT" }];
          }
          return step === lost && nth === 1 ? HttpResponse.error() : undefined;
        },
      );
      renderWorkspace();

      const press = await changeNegativeStyle();
      fireEvent.click(press);
      expect(
        await screen.findByText("No answer came back from the server. Try again."),
      ).toBeTruthy();
      await waitFor(() => {
        expect(press.getAttribute("aria-busy")).not.toBe("true");
      });
      const first = sent.length;
      fireEvent.click(press);

      expect(await screen.findByText("Submitted workspace settings for approval.")).toBeTruthy();
      expect(sent.slice(first).map((item) => item.step)).toEqual(["create", "test", "submit"]);
      // The create is the same command as before: the API replays the version it made.
      expect(sent[first]?.key).toBe(sent[0]?.key);
    },
  );

  it("a submission the API refused leaves its version open: the form names it at once and sends nothing more", async () => {
    // PRD ERR-81 as the API words it: the published version of the category takes effect later,
    // and the form states no date. The version exists and is tested; the form cannot change what
    // was refused, so the version is finished on its page, where the date is chosen.
    const refusedFor =
      "Version 2 takes effect on 01 Nov 2026. Choose an effective date after it, or submit this version once version 2 is in effect.";
    serveWorkspace([]);
    let listed: readonly unknown[] = [];
    const sent = serveSubmission(
      () => listed,
      (step) => {
        if (step === "create") {
          listed = [OPEN_PLATFORM];
        }
        return step === "submit"
          ? problemResponse("validation-failed", 422, "Check the highlighted fields", {
              errors: [
                {
                  field: "effective_from",
                  rule_id: "REGISTRY_EFFECTIVE_ORDER",
                  message: refusedFor,
                },
              ],
            })
          : undefined;
      },
    );
    renderWorkspace();

    const press = await changeNegativeStyle();
    fireEvent.click(press);

    const form = screen.getByRole("form", { name: "Workspace settings" });
    expect(await within(form).findByText(refusedFor)).toBeTruthy();
    const notice = (await screen.findByRole("heading", { name: OPEN_SENTENCE })).closest(
      "[data-tone]",
    ) as HTMLElement;
    expect(within(notice).getByRole("link", { name: "Open version 4" }).getAttribute("href")).toBe(
      `/policies/accounting/${OPEN_PLATFORM.id}`,
    );
    expect(sent.map((item) => item.step)).toEqual(["create", "test", "submit"]);

    await waitFor(() => {
      expect(press.getAttribute("aria-busy")).not.toBe("true");
    });
    fireEvent.click(press);
    expect(await within(form).findByText(OPEN_SENTENCE)).toBeTruthy();
    expect(sent).toHaveLength(3);

    // The version was finished on its page meanwhile. The same change in the same form is a new
    // command, not the replay of the one that made the refused version.
    listed = [];
    fireEvent.click(press);
    await waitFor(() => expect(sent.length).toBeGreaterThan(3));
    expect(sent[3]?.step).toBe("create");
    expect(sent[3]?.key).not.toBe(sent[0]?.key);
  });

  it("a version that waits for approval, and one of another scope, hold nothing", async () => {
    // A SUBMITTED version is the pending notice's; an ENTITY version is no version of this form.
    const calls: Call[] = [];
    serveWorkspace(calls);
    server.use(
      http.get(apiUrl("/api/v1/policies"), () =>
        HttpResponse.json({
          items: [
            { ...OPEN_PLATFORM, category: "CLOSE", scope: "ENTITY", status: "DRAFT" },
            { ...OPEN_PLATFORM, category: "ACCOUNTING_POLICY", status: "DRAFT" },
            { ...OPEN_PLATFORM, category: "INTEGRATION", status: "SUBMITTED" },
          ],
          next_cursor: null,
        }),
      ),
    );
    renderWorkspace();

    const form = await screen.findByRole("form", { name: "Workspace settings" });
    expect(
      await screen.findByText("Changes to Integrations are waiting for approval."),
    ).toBeTruthy();
    fireEvent.change(within(form).getByRole("textbox", { name: "Late-entry window" }), {
      target: { value: "7" },
    });
    fireEvent.click(within(form).getByRole("checkbox", { name: "Quarantine failed import rows" }));
    fireEvent.change(within(form).getByRole("textbox", { name: "Comment" }), {
      target: { value: "A longer window for late entries" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Submit for approval" }));

    // Both are sent: what the API says of a category that waits for approval is the API's to say.
    expect(await screen.findByText("Submitted workspace settings for approval.")).toBeTruthy();
    expect(screen.queryByText(/is open\. Finish it on its page\./)).toBeNull();
    expect(
      calls.filter((call) => call.path === "/api/v1/policies").map((call) => call.body),
    ).toEqual([
      { category: "CLOSE", scope: "TENANT", values: { "close.late_entry_window_days": 7 } },
      { category: "INTEGRATION", scope: "TENANT", values: { "data.quarantine_failed_rows": true } },
    ]);
  });

  it("a reader without config.author sees which version is open, with the link", async () => {
    serveWorkspace([]);
    server.use(
      http.get(apiUrl("/api/v1/policies"), () =>
        HttpResponse.json({ items: [OPEN_PLATFORM], next_cursor: null }),
      ),
    );
    renderWorkspace(signedInMe({ permissions: ["settings.manage", "config.read"] }));

    await screen.findByRole("form", { name: "Workspace settings" });
    expect(await screen.findByRole("heading", { name: OPEN_SENTENCE })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open version 4" }).getAttribute("href")).toBe(
      `/policies/accounting/${OPEN_PLATFORM.id}`,
    );
  });

  it("percentages move the decimal point; unchanged values create nothing", () => {
    expect(ratioToPercent("0.10")).toBe("10");
    expect(ratioToPercent("0.01")).toBe("1");
    expect(ratioToPercent("0.125")).toBe("12.5");
    expect(ratioToPercent("1")).toBe("100");
    expect(percentToRatio("10")).toBe("0.1");
    expect(percentToRatio("12.5")).toBe("0.125");
    expect(percentToRatio("100")).toBe("1");
    expect(percentToRatio("0")).toBe("0");
    expect(percentToRatio("100.5")).toBeNull();
    expect(percentToRatio("abc")).toBeNull();

    const values = Object.fromEntries(
      WORKSPACE_FIELDS.map((field) => {
        const stored = RESOLVED[field.key];
        if (field.control.kind === "percent") {
          return [field.key, ratioToPercent(String(stored))];
        }
        if (field.control.kind === "integer") {
          return [field.key, String(stored)];
        }
        return [field.key, stored as string | boolean | readonly string[]];
      }),
    );
    expect(workspaceChanges(RESOLVED, values)).toEqual({ changes: [], errors: {} });
  });
});
