// @vitest-environment jsdom
// SF-13:template-version (BUILD_SPEC RFD-23; SCREENS §11.2): the outputs form "Template outputs" shows
// TPL-SUB-DAILY's current version as Series (increment: day), Over time, ASC 606-10-25-27(a), Time
// elapsed, Daily; a published version is read-only; a draft's "Save outputs" patches the changed fields
// with `If-Match`; the Changes pane lists the outputs that differ from the superseded version.
// Item TPL-EFFECTIVE-FROM-UI-1 (SCREENS rev 1.31, §11.0 "Refused command" and §11.2 Meta; PRD ERR-75):
// the Meta "Version details" with "Effective from" — required for a version that replaces the published
// one, optional for the first — the refusal of the date at the field, and a refused command's messages.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import {
  outputChanges,
  type PobTemplate,
  type PobTemplateVersion,
  templatePaneOf,
} from "../../lib/api/queries/pob-templates";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, heldRead, installMswServer, problemResponse, server } from "../../test/msw";
import { describedBy, REFUSAL_REFERENCE, REFUSAL_TITLE, refusedWith } from "../../test/refusals";
import { distinctnessText } from "./template-version";

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

const MAYA = signedInMe({ permissions: ["config.read", "config.author"] });

const V1_ID = "7f7f7f7f-7f7f-4f7f-8f7f-7f7f7f7f7f7f";
const V2_ID = "7e7e7e7e-7e7e-4e7e-8e7e-7e7e7e7e7e7e";
const TEMPLATE: PobTemplate = {
  id: "7a7a7a7a-7a7a-4a7a-8a7a-7a7a7a7a7a7a",
  code: "TPL-SUB-DAILY",
  name: "Subscription, daily ratable",
  description: null,
  current_version: {
    id: V1_ID,
    version_no: 1,
    status: "PUBLISHED",
    effective_from: null,
    published_at: null,
    lint_status: null,
    rule_count: null,
  },
  latest_version: {
    id: V2_ID,
    version_no: 2,
    status: "DRAFT",
    effective_from: null,
    published_at: null,
    lint_status: null,
    rule_count: null,
  },
  row_version: 2,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};

function version(
  overrides: Partial<PobTemplateVersion> & Pick<PobTemplateVersion, "id" | "version_no" | "status">,
): PobTemplateVersion {
  return {
    pob_template_id: TEMPLATE.id,
    template_code: TEMPLATE.code,
    obligation_kind: "STANDARD",
    distinctness: "series",
    series_increment_unit: "day",
    satisfaction_pattern: "OVER_TIME",
    over_time_criterion: "OT_A",
    recognition_method: "TIME_ELAPSED",
    ratable_convention: "DAILY",
    start_date_rule: "LINE_START",
    end_date_rule: "LINE_END",
    term_months: null,
    principal_agent: "PRINCIPAL",
    warranty_type: "NONE",
    licence_nature: "NOT_APPLICABLE",
    sfc_assessment_required: false,
    revenue_category: "SUBSCRIPTION",
    stratification_label: null,
    is_excluded_from_netting_attribution: false,
    account_role_overrides: {},
    disaggregation: {},
    policy_values: {},
    effective_from: "2026-01-01T12:00:00Z",
    effective_to: null,
    approval_request_id: null,
    pending_approval_request_id: null,
    content_sha256: null,
    published_at: "2026-01-02T00:00:00Z",
    published_by: null,
    supersedes_version_id: null,
    test_evidence: {
      passed: 2,
      failed: 0,
      not_run: 0,
      total: 2,
      last_run_at: "2026-01-01T12:00:00Z",
    },
    created_by: null,
    row_version: 4,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    ...overrides,
  };
}
const V1 = version({ id: V1_ID, version_no: 1, status: "PUBLISHED" });
const V2 = version({
  id: V2_ID,
  version_no: 2,
  status: "DRAFT",
  supersedes_version_id: V1_ID,
  start_date_rule: "BOOKING_DATE",
  published_at: null,
  effective_from: null,
  test_evidence: { passed: 0, failed: 0, not_run: 2, total: 2, last_run_at: null },
  row_version: 1,
});

function serve() {
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/books"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/periods"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/saved-views"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl(`/api/v1/pob-templates/${TEMPLATE.id}`), () => HttpResponse.json(TEMPLATE)),
    http.get(apiUrl("/api/v1/pob-template-versions/:versionId"), ({ params }) => {
      const found = [V1, V2].find((item) => item.id === params.versionId);
      return found === undefined
        ? problemResponse("not-found", 404, "Not found")
        : HttpResponse.json(found);
    }),
    http.get(apiUrl("/api/v1/registry/parameters"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/config-test-cases"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
  );
}

const APPROVAL_ID = "7d7d7d7d-7d7d-4d7d-8d7d-7d7d7d7d7d7d";
// PRD §5.5 ERR-75, the date form: `detail` and `errors[].message` are the same sentence.
const ERR_75 = "This version replaces a published one. Choose an effective date later than today.";
const DATE_HELP = "Contracts dated on or after this date use this version.";
const SUPERSEDING_HELP = `${DATE_HELP} It replaces a published one, so choose a date later than today; the approval must come before that date.`;

function err75() {
  return problemResponse("validation-failed", 422, "Check the highlighted fields", {
    detail: ERR_75,
    errors: [
      { field: "effective_from", sheet: null, row: null, rule_id: "REQ-POL-007", message: ERR_75 },
    ],
  });
}

/** The text of the elements that describe a control: its error first, then its help. */
function descriptionsOf(element: HTMLElement): string {
  return (element.getAttribute("aria-describedby") ?? "")
    .split(" ")
    .map((id) => document.getElementById(id)?.textContent ?? "")
    .join(" | ");
}

/** The banner of a refused command: the alert that holds the heading `title`. */
async function refusalBanner(title: string): Promise<HTMLElement> {
  const heading = await screen.findByRole("heading", { name: title });
  const alert = heading.closest<HTMLElement>('[role="alert"]');
  if (alert === null) {
    throw new Error(`"${title}" is not inside an alert`);
  }
  return alert;
}

function renderVersion(versionId: string) {
  return renderApp(`/policies/templates/${TEMPLATE.id}/versions/${versionId}`, {
    me: MAYA,
    screenRoutes: SCREEN_ROUTES,
  });
}

async function effectiveField(): Promise<{
  readonly form: HTMLElement;
  readonly field: HTMLInputElement;
}> {
  const details = await screen.findByRole("region", { name: "Version details" });
  const form = within(details).getByRole("form", { name: "Effective date" });
  return {
    form,
    field: within(form).getByRole<HTMLInputElement>("textbox", { name: /^Effective from/ }),
  };
}

describe("SF-13:template-version Meta and refused commands (SCREENS rev 1.31; PRD ERR-75)", () => {
  it("a draft that replaces the published version asks for Effective from, and Save effective date sends 12:00:00Z of the date with If-Match", async () => {
    const patches: { readonly ifMatch: string | null; readonly body: unknown }[] = [];
    serve();
    server.use(
      http.patch(apiUrl(`/api/v1/pob-template-versions/${V2_ID}`), async ({ request }) => {
        patches.push({ ifMatch: request.headers.get("If-Match"), body: await request.json() });
        return HttpResponse.json({ ...V2, effective_from: "2026-11-01T12:00:00Z", row_version: 2 });
      }),
    );
    renderVersion(V2_ID);

    const { form, field } = await effectiveField();
    expect(field.value).toBe("");
    expect(field.getAttribute("aria-required")).toBe("true");
    expect(within(form).queryByText("(optional)")).toBeNull();
    expect(descriptionsOf(field)).toBe(SUPERSEDING_HELP);
    fireEvent.change(field, { target: { value: "2026-11-01" } });
    fireEvent.blur(field);
    fireEvent.click(within(form).getByRole("button", { name: "Save effective date" }));

    expect(await screen.findByText("Saved the effective date.")).toBeTruthy();
    // PobTemplateVersionUpdateIn `effective_from` is date-time: an instant, never a date (DS-I18N-08).
    expect(patches).toEqual([
      { ifMatch: '"r1"', body: { effective_from: "2026-11-01T12:00:00Z" } },
    ]);
    expect(field.value).toBe("01 Nov 2026");
  });

  it("Save effective date without a date on a draft that replaces the published version says Enter the effective date. and sends nothing", async () => {
    let patched = 0;
    serve();
    server.use(
      http.patch(apiUrl(`/api/v1/pob-template-versions/${V2_ID}`), () => {
        patched += 1;
        return HttpResponse.json(V2);
      }),
    );
    renderVersion(V2_ID);

    const { form, field } = await effectiveField();
    fireEvent.click(within(form).getByRole("button", { name: "Save effective date" }));

    expect(await within(form).findByText("Enter the effective date.")).toBeTruthy();
    expect(field.getAttribute("aria-invalid")).toBe("true");
    expect(document.activeElement).toBe(field);
    expect(patched).toBe(0);
    // The message is about the empty field: it leaves when a date is typed.
    fireEvent.change(field, { target: { value: "2026-11-01" } });
    expect(within(form).queryByText("Enter the effective date.")).toBeNull();
  });

  it("the first version of a template keeps a free date: Effective from is optional and can be cleared", async () => {
    const patches: unknown[] = [];
    const first = version({
      id: V2_ID,
      version_no: 1,
      status: "DRAFT",
      published_at: null,
      effective_from: "2026-01-01T12:00:00Z",
      row_version: 1,
    });
    serve();
    server.use(
      http.get(apiUrl(`/api/v1/pob-templates/${TEMPLATE.id}`), () =>
        HttpResponse.json({
          ...TEMPLATE,
          current_version: null,
          latest_version: { ...TEMPLATE.latest_version, version_no: 1 },
        }),
      ),
      http.get(apiUrl(`/api/v1/pob-template-versions/${V2_ID}`), () => HttpResponse.json(first)),
      http.patch(apiUrl(`/api/v1/pob-template-versions/${V2_ID}`), async ({ request }) => {
        patches.push(await request.json());
        return HttpResponse.json({ ...first, effective_from: null, row_version: 2 });
      }),
    );
    renderVersion(V2_ID);

    const { form, field } = await effectiveField();
    expect(field.value).toBe("01 Jan 2026");
    expect(field.getAttribute("aria-required")).toBeNull();
    expect(within(form).getByText("(optional)")).toBeTruthy();
    expect(descriptionsOf(field)).toBe(DATE_HELP);
    fireEvent.change(field, { target: { value: "" } });
    fireEvent.blur(field);
    fireEvent.click(within(form).getByRole("button", { name: "Save effective date" }));

    expect(await screen.findByText("Saved the effective date.")).toBeTruthy();
    expect(patches).toEqual([{ effective_from: null }]);
  });

  it("Submit for approval refused with PRD ERR-75 shows the sentence at Effective from with focus, the banner does not repeat it, and both leave when the date is edited", async () => {
    serve();
    server.use(
      // The draft is dated the day before the clock of the server: PRD ERR-75 refuses it.
      http.get(apiUrl(`/api/v1/pob-template-versions/${V2_ID}`), () =>
        HttpResponse.json({ ...V2, status: "TESTED", effective_from: "2026-09-30T12:00:00Z" }),
      ),
      http.post(apiUrl(`/api/v1/pob-template-versions/${V2_ID}/submit`), () => err75()),
    );
    renderVersion(V2_ID);

    const { field } = await effectiveField();
    expect(field.value).toBe("30 Sep 2026");
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));

    await waitFor(() => {
      expect(descriptionsOf(field)).toBe(`${ERR_75} | ${SUPERSEDING_HELP}`);
    });
    expect(field.getAttribute("aria-invalid")).toBe("true");
    expect(document.activeElement).toBe(field);
    // "Check the highlighted fields" stands over a field that is highlighted, and says it once.
    const alert = await refusalBanner("Check the highlighted fields");
    expect(within(alert).queryByText(ERR_75)).toBeNull();
    expect(screen.getAllByText(ERR_75)).toHaveLength(1);

    // Leaving the field echoes the same date: that is no edit, and the sentence stays.
    fireEvent.blur(field);
    expect(field.value).toBe("30 Sep 2026");
    expect(descriptionsOf(field)).toBe(`${ERR_75} | ${SUPERSEDING_HELP}`);
    // The sentence describes the date that was submitted: it leaves once another date is typed.
    fireEvent.change(field, { target: { value: "2026-11-02" } });
    expect(screen.queryByText(ERR_75)).toBeNull();
    expect(field.getAttribute("aria-invalid")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Check the highlighted fields" })).toBeNull();
  });

  it("a refused submission that names no field of the screen lists its messages in the banner, and Run tests clears it", async () => {
    const changed = "This version changed after its tests ran. Run the tests again.";
    serve();
    server.use(
      http.post(apiUrl(`/api/v1/pob-template-versions/${V2_ID}/submit`), () =>
        problemResponse("invalid-transition", 409, "Action not available in this state", {
          errors: [
            { field: "status", sheet: null, row: null, rule_id: "REQ-POL-003", message: changed },
          ],
        }),
      ),
      http.post(apiUrl(`/api/v1/pob-template-versions/${V2_ID}/test`), () =>
        HttpResponse.json({
          ...V2,
          status: "TESTED",
          test_evidence: { passed: 2, failed: 0, not_run: 0, total: 2, last_run_at: null },
        }),
      ),
    );
    renderVersion(V2_ID);

    await effectiveField();
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    const alert = await refusalBanner("Action not available in this state");
    // Before rev 1.31 the banner held the title alone: the reason was not on the screen.
    expect(within(alert).getByText(changed)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Run tests" }));
    expect(await screen.findByText("2 of 2 tests passed.")).toBeTruthy();
    expect(screen.queryByText(changed)).toBeNull();
    expect(
      screen.queryByRole("heading", { name: "Action not available in this state" }),
    ).toBeNull();
  });

  it("a saved effective date clears the refusal of an earlier submission", async () => {
    const changed = "This version changed after its tests ran. Run the tests again.";
    let stored = V2;
    serve();
    server.use(
      http.get(apiUrl(`/api/v1/pob-template-versions/${V2_ID}`), () => HttpResponse.json(stored)),
      http.patch(apiUrl(`/api/v1/pob-template-versions/${V2_ID}`), () => {
        stored = { ...V2, effective_from: "2026-11-02T12:00:00Z", row_version: 2 };
        return HttpResponse.json(stored);
      }),
      http.post(apiUrl(`/api/v1/pob-template-versions/${V2_ID}/submit`), () =>
        problemResponse("invalid-transition", 409, "Action not available in this state", {
          errors: [
            { field: "status", sheet: null, row: null, rule_id: "REQ-POL-003", message: changed },
          ],
        }),
      ),
    );
    renderVersion(V2_ID);

    const { form, field } = await effectiveField();
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    const alert = await refusalBanner("Action not available in this state");
    expect(within(alert).getByText(changed)).toBeTruthy();

    fireEvent.change(field, { target: { value: "2026-11-02" } });
    fireEvent.blur(field);
    // An edit of the date answers a sentence about the date; this one is not, and stays until the save.
    expect(screen.getByText(changed)).toBeTruthy();
    fireEvent.click(within(form).getByRole("button", { name: "Save effective date" }));
    expect(await screen.findByText("Saved the effective date.")).toBeTruthy();
    expect(screen.queryByText(changed)).toBeNull();
    expect(
      screen.queryByRole("heading", { name: "Action not available in this state" }),
    ).toBeNull();
  });

  // POLICY-VERSION-RESET-RACE-1: a command's success is known to the page only after the reads it
  // causes, and "Submit for approval" can be sent meanwhile. Before, the success then cleared the
  // refusal of that submission as if it were the earlier one: a refused command without a word.
  it("a submission refused while the reads after Run tests are on their way keeps its refusal when they arrive", async () => {
    const dated: PobTemplateVersion = {
      ...V2,
      status: "TESTED",
      effective_from: "2026-09-30T12:00:00Z",
    };
    const read = heldRead();
    serve();
    server.use(
      http.get(apiUrl(`/api/v1/pob-template-versions/${V2_ID}`), async () => {
        await read.passed();
        return HttpResponse.json(dated);
      }),
      http.post(apiUrl(`/api/v1/pob-template-versions/${V2_ID}/test`), () => {
        read.hold();
        return HttpResponse.json({
          ...dated,
          test_evidence: { passed: 2, failed: 0, not_run: 0, total: 2, last_run_at: null },
        });
      }),
      http.post(apiUrl(`/api/v1/pob-template-versions/${V2_ID}/submit`), () => err75()),
    );
    renderVersion(V2_ID);

    const { field } = await effectiveField();
    fireEvent.click(screen.getByRole("button", { name: "Run tests" }));
    // The tests have answered; the version the page reads again has not.
    await waitFor(() => {
      expect(read.waiting()).toBeGreaterThan(0);
    });
    expect(screen.queryByText("2 of 2 tests passed.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    await waitFor(() => {
      expect(descriptionsOf(field)).toBe(`${ERR_75} | ${SUPERSEDING_HELP}`);
    });

    read.release();
    expect(await screen.findByText("2 of 2 tests passed.")).toBeTruthy();
    // The submission was sent after the tests: it is not the earlier one their success answers.
    expect(descriptionsOf(field)).toBe(`${ERR_75} | ${SUPERSEDING_HELP}`);
    expect(field.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByRole("heading", { name: "Check the highlighted fields" })).toBeTruthy();
  });

  it("a submission refused while the reads after Save effective date are on their way keeps its refusal when they arrive", async () => {
    const changed = "This version changed after its tests ran. Run the tests again.";
    const read = heldRead();
    let stored = V2;
    serve();
    server.use(
      http.get(apiUrl(`/api/v1/pob-template-versions/${V2_ID}`), async () => {
        await read.passed();
        return HttpResponse.json(stored);
      }),
      http.patch(apiUrl(`/api/v1/pob-template-versions/${V2_ID}`), () => {
        read.hold();
        stored = { ...V2, effective_from: "2026-11-02T12:00:00Z", row_version: 2 };
        return HttpResponse.json(stored);
      }),
      http.post(apiUrl(`/api/v1/pob-template-versions/${V2_ID}/submit`), () =>
        problemResponse("invalid-transition", 409, "Action not available in this state", {
          errors: [
            { field: "status", sheet: null, row: null, rule_id: "REQ-POL-003", message: changed },
          ],
        }),
      ),
    );
    renderVersion(V2_ID);

    const { form, field } = await effectiveField();
    fireEvent.change(field, { target: { value: "2026-11-02" } });
    fireEvent.blur(field);
    fireEvent.click(within(form).getByRole("button", { name: "Save effective date" }));
    await waitFor(() => {
      expect(read.waiting()).toBeGreaterThan(0);
    });
    expect(screen.queryByText("Saved the effective date.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    const alert = await refusalBanner("Action not available in this state");
    expect(within(alert).getByText(changed)).toBeTruthy();

    read.release();
    expect(await screen.findByText("Saved the effective date.")).toBeTruthy();
    expect(
      within(await refusalBanner("Action not available in this state")).getByText(changed),
    ).toBeTruthy();
  });

  it("a published version shows Effective from, Effective to, Author, Approver and Content SHA-256 as Version details", async () => {
    serve();
    server.use(
      http.get(apiUrl(`/api/v1/pob-template-versions/${V1_ID}`), () =>
        HttpResponse.json({
          ...V1,
          approval_request_id: APPROVAL_ID,
          effective_to: "2026-11-01T12:00:00Z",
          content_sha256: "ab".repeat(32),
        }),
      ),
      http.get(apiUrl(`/api/v1/approvals/${APPROVAL_ID}`), () =>
        HttpResponse.json({
          id: APPROVAL_ID,
          preparer: { id: "4b0c7d6e-1a3f-4b5c-8d9e-6f5a4b3c2d1e", display_name: "Maya Chen" },
          steps: [{ decisions: [{ approver: { display_name: "Marcus Webb" } }] }],
        }),
      ),
    );
    renderVersion(V1_ID);

    const details = await screen.findByRole("region", { name: "Version details" });
    const value = (term: string) =>
      within(details).getByText(term, { selector: "dt" }).nextElementSibling?.firstChild
        ?.textContent;
    expect(within(details).queryByRole("form")).toBeNull();
    expect(value("Effective from")).toBe("01 Jan 2026");
    expect(value("Effective to")).toBe("01 Nov 2026");
    await waitFor(() => {
      expect(value("Author")).toBe("Maya Chen");
    });
    expect(value("Approver")).toBe("Marcus Webb");
    expect(value("Content SHA-256")).toBe("ab".repeat(32));
  });
});

describe("SF-13:template-version", () => {
  it("TPL-SUB-DAILY current version shows Series (increment day), Over time, Time elapsed, Daily read-only", async () => {
    serve();
    renderApp(`/policies/templates/${TEMPLATE.id}/versions/${V1_ID}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Subscription, daily ratable" }),
    ).toBeTruthy();
    expect(screen.getByTestId("SF-13-identifier").textContent).toContain("TPL-SUB-DAILY");
    // The status chip and the lifecycle step both read "Published".
    expect(screen.getAllByText("Published").length).toBeGreaterThan(0);
    expect(screen.getByText("v1")).toBeTruthy();
    const form = screen.getByRole("form", { name: "Template outputs" });
    expect(form.getAttribute("data-testid")).toBe("SF-13-pane-template-outputs");
    expect((within(form).getByRole("radio", { name: "Series" }) as HTMLInputElement).checked).toBe(
      true,
    );
    expect((within(form).getByRole("radio", { name: "Series" }) as HTMLInputElement).disabled).toBe(
      true,
    );
    expect(within(form).getByText("Day")).toBeTruthy();
    expect(
      (within(form).getByRole("radio", { name: "Over time" }) as HTMLInputElement).checked,
    ).toBe(true);
    expect(within(form).getByText("ASC 606-10-25-27(a)")).toBeTruthy();
    expect(within(form).getByText("Time elapsed")).toBeTruthy();
    expect(within(form).getByText("Daily")).toBeTruthy();
    expect(within(form).getByText("Standard")).toBeTruthy();
    expect(within(form).getByText("Line start")).toBeTruthy();
    expect(within(form).queryByRole("button", { name: "Save outputs" })).toBeNull();
    expect(screen.getByRole("button", { name: "New draft version" })).toBeTruthy();
    expect(
      screen.getByText(/This version is no longer a draft, so it is read-only\./),
    ).toBeTruthy();
    // 04 SC-V `effective_from` is an instant: the lifecycle caption shows its UTC date.
    expect(screen.getByText("Effective 01 Jan 2026")).toBeTruthy();
    expect(distinctnessText(V1)).toBe("Series (increment: Day)");
    expect(templatePaneOf("changes")).toBe("changes");
    expect(templatePaneOf(null)).toBe("outputs");
  });

  it("a draft's Save outputs patches the changed fields with If-Match; Changes lists the differences", async () => {
    const patches: { readonly ifMatch: string | null; readonly body: unknown }[] = [];
    serve();
    server.use(
      http.patch(apiUrl(`/api/v1/pob-template-versions/${V2_ID}`), async ({ request }) => {
        patches.push({ ifMatch: request.headers.get("If-Match"), body: await request.json() });
        return HttpResponse.json({ ...V2, warranty_type: "SERVICE", row_version: 2 });
      }),
    );
    renderApp(`/policies/templates/${TEMPLATE.id}/versions/${V2_ID}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const form = await screen.findByRole("form", { name: "Template outputs" });
    expect(screen.getByRole("button", { name: "Run tests" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Submit for approval" })).toBeTruthy();
    const save = within(form).getByRole("button", { name: "Save outputs" });
    expect(save.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(within(form).getByRole("combobox", { name: /^Warranty type/ }));
    fireEvent.mouseDown(await screen.findByRole("option", { name: "Service" }));
    fireEvent.click(within(form).getByRole("button", { name: "Save outputs" }));

    expect(await screen.findByText("Saved the outputs of TPL-SUB-DAILY v2.")).toBeTruthy();
    expect(patches).toEqual([{ ifMatch: '"r1"', body: { warranty_type: "SERVICE" } }]);

    fireEvent.click(screen.getByRole("tab", { name: "Changes" }));
    const changes = await screen.findByRole("table", { name: "Changes" });
    const row = within(changes).getByRole("row", { name: /start_date_rule/ });
    expect(within(row).getByText("Line start")).toBeTruthy();
    expect(within(row).getByText("Booking date")).toBeTruthy();
    expect(outputChanges(V2, V1)).toEqual([
      { field: "start_date_rule", before: "LINE_START", after: "BOOKING_DATE" },
    ]);
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): a message that names a member no
  // field on screen sends was shown nowhere — the term in months is asked only of an end date of start
  // plus term. The banner lists it, and what a field shows is not said again.
  it("Save outputs under a refused command: the banner lists what no field on screen shows", async () => {
    const notOnScreen = "Enter the term in months.";
    const noField = "An override names an account role this template does not post.";
    const atField = "A service warranty needs a separate obligation.";
    serve();
    server.use(
      http.patch(apiUrl(`/api/v1/pob-template-versions/${V2_ID}`), () =>
        refusedWith({
          term_months: notOnScreen,
          "account_role_overrides.REVENUE": noField,
          warranty_type: atField,
        }),
      ),
    );
    renderApp(`/policies/templates/${TEMPLATE.id}/versions/${V2_ID}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    const form = await screen.findByRole("form", { name: "Template outputs" });
    expect(within(form).queryByLabelText(/^Term/)).toBeNull();
    const warranty = within(form).getByRole("combobox", { name: /^Warranty type/ });
    fireEvent.click(warranty);
    fireEvent.mouseDown(await screen.findByRole("option", { name: "Service" }));
    fireEvent.click(within(form).getByRole("button", { name: "Save outputs" }));

    const banner = await within(form).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + notOnScreen + noField + REFUSAL_REFERENCE);
    expect(describedBy(warranty)).toContain(atField);
  });

  it("Save policy values under a refused command: the pane has no field for a message, so the banner says every sentence", async () => {
    const sentence = "Use GROSS or NET.";
    const key = "billing.unbilled_presentation";
    serve();
    server.use(
      http.get(apiUrl("/api/v1/pob-template-versions/:versionId"), () =>
        HttpResponse.json({ ...V2, policy_values: { [key]: "GROSS" } }),
      ),
      http.patch(apiUrl(`/api/v1/pob-template-versions/${V2_ID}`), () =>
        refusedWith({ [`policy_values.${key}`]: sentence }),
      ),
    );
    renderApp(`/policies/templates/${TEMPLATE.id}/versions/${V2_ID}?pane=policy-values`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    const pane = await screen.findByTestId("SF-13-pane-template-policy-values");
    fireEvent.change(within(pane).getByRole("textbox", { name: `Value of ${key}` }), {
      target: { value: "NETT" },
    });
    fireEvent.click(within(pane).getByRole("button", { name: "Save policy values" }));

    const banner = await within(pane).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + sentence + REFUSAL_REFERENCE);
  });
});
