// @vitest-environment jsdom
// SF-13:rule-set-version (BUILD_SPEC RFD-22; SCREENS §11.0 lifecycle commands, §11.1 decision-table editor,
// lint copy and test hooks; 04 API-R-25): lint findings render with the negative chip only and no
// "Submit for approval"; a SUBMITTED version renders the grid "Rules" without edit actions and a
// read-only rule drawer; "New draft version" copies a published version; the condition and output
// summaries and the changes diff. Item TPL-EFFECTIVE-FROM-UI-1 (SCREENS rev 1.31, §11.0 "Effective
// date" and "Refused command"; PRD ERR-75): a version read at an instant goes without a date or with a
// later one, a version chosen by a contract date keeps its date, and a refusal of the date stands at
// the field.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import {
  compareRules,
  conditionSummary,
  outputSummary,
  type Rule,
  type RuleSet,
  type RuleSetVersion,
} from "../../lib/api/queries/rule-sets";
import { instantMs } from "../../lib/format";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, heldRead, installMswServer, problemResponse, server } from "../../test/msw";

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

const RULE_SET_ID = "6f1c2a3b-4d5e-4f60-8a1b-2c3d4e5f6a7b";
const VERSION_ID = "7a2b3c4d-5e6f-4a70-9b1c-2d3e4f5a6b7c";
const DRAFT_ID = "9c4d5e6f-7a8b-4c92-8d3e-4f5a6b7c8d9e";
const APPROVAL_ID = "8b3c4d5e-6f7a-4b81-8c2d-3e4f5a6b7c8d";

const AUTHOR = signedInMe({ permissions: ["config.read", "config.author"] });

function summary(status: RuleSetVersion["status"], id = VERSION_ID) {
  return {
    id,
    version_no: 1,
    status,
    effective_from: "2026-01-01T00:00:00Z",
    published_at: null,
    rule_count: 2,
    lint_status: null,
  };
}

function ruleSet(status: RuleSetVersion["status"]): RuleSet {
  return {
    id: RULE_SET_ID,
    code: "APPROVAL_ROUTING",
    name: "Approval routing",
    kind: "APPROVAL_ROUTING",
    description: null,
    current_version: status === "PUBLISHED" ? summary(status) : null,
    latest_version: summary(status),
    created_at: "2026-09-01T12:00:00Z",
    updated_at: "2026-09-01T12:00:00Z",
    row_version: 1,
  };
}

function version(overrides: Partial<RuleSetVersion>): RuleSetVersion {
  return {
    id: VERSION_ID,
    rule_set_id: RULE_SET_ID,
    rule_set_code: "APPROVAL_ROUTING",
    kind: "APPROVAL_ROUTING",
    version_no: 1,
    status: "DRAFT",
    effective_from: "2026-01-01T00:00:00Z",
    effective_to: null,
    content_sha256: null,
    approval_request_id: null,
    pending_approval_request_id: null,
    published_at: null,
    published_by: null,
    supersedes_version_id: null,
    rule_count: 2,
    lint_result: null,
    test_evidence: {
      total: 2,
      passed: 2,
      failed: 0,
      not_run: 0,
      last_run_at: "2026-09-01T12:00:00Z",
    },
    impact_simulation: null,
    created_at: "2026-09-01T12:00:00Z",
    updated_at: "2026-09-02T09:30:00Z",
    row_version: 3,
    ...overrides,
  };
}

function rule(key: string, overrides: Partial<Rule> = {}): Rule {
  return {
    id: `${key === "ROUTE-CON-01" ? "1" : "2"}a2b3c4d-5e6f-4a70-9b1c-2d3e4f5a6b7c`,
    rule_set_version_id: VERSION_ID,
    rule_key: key,
    priority: 0,
    specificity: 1,
    conditions: [{ field: "subject.type", op: "eq", value: "CONTRACT_ACTIVATION" }],
    outputs: {
      steps: [{ name: "Revenue review", permission: "contract.approve", min_approvers: 1 }],
    },
    description: null,
    ...overrides,
  };
}

const RULES: readonly Rule[] = [rule("ROUTE-CON-01"), rule("ROUTE-CON-02")];

interface Posted {
  readonly path: string;
  readonly body: unknown;
}

/** The screen's reads for one version, and the new-version command recorded in `posted`. */
function serveVersion(current: RuleSetVersion, set: RuleSet, posted: Posted[] = []) {
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/books"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/rule-sets/:ruleSetId"), () => HttpResponse.json(set)),
    http.get(apiUrl("/api/v1/rule-set-versions/:versionId"), ({ params }) =>
      HttpResponse.json(
        params.versionId === DRAFT_ID
          ? version({ id: DRAFT_ID, version_no: 2, status: "DRAFT", supersedes_version_id: null })
          : current,
      ),
    ),
    http.get(apiUrl("/api/v1/rule-set-versions/:versionId/rules"), () =>
      HttpResponse.json(
        { items: RULES, next_cursor: null },
        { headers: { "X-Erev-Total-Count": String(RULES.length) } },
      ),
    ),
    http.get(apiUrl("/api/v1/config-test-cases"), () =>
      HttpResponse.json(
        { items: [], next_cursor: null },
        { headers: { "X-Erev-Total-Count": "0" } },
      ),
    ),
    http.get(apiUrl("/api/v1/approvals/:requestId"), () =>
      HttpResponse.json({
        id: APPROVAL_ID,
        preparer: {
          id: "4b0c7d6e-1a3f-4b5c-8d9e-6f5a4b3c2d1e",
          display_name: "Maya Chen",
          kind: "USER",
        },
        steps: [],
      }),
    ),
    http.post(apiUrl("/api/v1/rule-sets/:ruleSetId/versions"), async ({ request }) => {
      posted.push({ path: new URL(request.url).pathname, body: await request.json() });
      return HttpResponse.json(version({ id: DRAFT_ID, version_no: 2 }), { status: 201 });
    }),
  );
}

function renderVersion(search = "") {
  return renderApp(`/policies/rule-sets/${RULE_SET_ID}/versions/${VERSION_ID}${search}`, {
    me: AUTHOR,
    screenRoutes: SCREEN_ROUTES,
  });
}

describe("SF-13:rule-set-version", () => {
  it("lint findings render and block publish", async () => {
    const failing = version({
      status: "TESTED",
      lint_result: {
        status: "FAIL",
        findings: [
          {
            rule_id: "REQ-POL-002",
            severity: "ERROR",
            rule_keys: ["ROUTE-CON-01", "ROUTE-CON-02"],
            message:
              "Rules ROUTE-CON-01 and ROUTE-CON-02 have the same specificity and priority and can match the same item. Change a condition or a priority.",
          },
        ],
        linted_at: "2026-09-02T09:30:00Z",
      },
    });
    serveVersion(failing, ruleSet("TESTED"));
    renderVersion("?pane=lint");

    expect(await screen.findByRole("heading", { level: 1, name: "Approval routing" })).toBeTruthy();
    const list = await screen.findByRole("list", { name: "Lint findings" });
    expect(list.getAttribute("data-testid")).toBe("SF-13-pane-lint");
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(1);
    const [row] = rows;
    if (row === undefined) {
      throw new Error("no lint row");
    }
    // SCREENS §11.1: lint error rows use the negative chip only.
    const chips = row.querySelectorAll("[data-tone]");
    expect(chips).toHaveLength(1);
    expect(chips[0]?.getAttribute("data-tone")).toBe("negative");
    expect(within(row).getByText("Error")).toBeTruthy();
    await waitFor(() => {
      expect(
        within(row).getByText(
          "Rules ROUTE-CON-01 and ROUTE-CON-02 have equal specificity (1) and priority (0). Change a priority or a condition.",
        ),
      ).toBeTruthy();
    });
    // A version with lint errors cannot be submitted: "Submit for approval" is not rendered.
    expect(screen.getByRole("button", { name: "Run tests" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Submit for approval" })).toBeNull();
    expect(screen.getByRole("tab", { name: /^Lint/ }).textContent).toContain("Lint errors");
  });

  // docs/dev-guide.md DG-FE-06 rev 1.228 (item KIT-UNPLACED-ERRORS-1): a refusal that names a member the
  // drawer has no field for is said in the banner; one that names a field stands at that field, once.
  it("a refusal of Add test case says in the banner what no field of the drawer shows", async () => {
    serveVersion(version({ status: "DRAFT" }), ruleSet("DRAFT"));
    server.use(
      http.post(apiUrl("/api/v1/config-test-cases"), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            {
              field: "name",
              sheet: null,
              row: null,
              rule_id: null,
              message: "This version already has a test case of this name.",
            },
            {
              field: "subject_id",
              sheet: null,
              row: null,
              rule_id: null,
              message: "The version is no longer a draft.",
            },
          ],
        }),
      ),
    );
    renderVersion("?pane=tests&drawer=new-test-case");
    const dialog = await screen.findByRole("dialog", { name: "Add test case" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Name/ }), {
      target: { value: "Routes a discount over 20%" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add test case" }));

    const banner = await within(dialog).findByRole("alert");
    expect(within(banner).getByText("The version is no longer a draft.")).toBeTruthy();
    expect(
      within(dialog).getAllByText("This version already has a test case of this name."),
    ).toHaveLength(1);
    expect(
      within(dialog).getByRole("textbox", { name: /^Name/ }).getAttribute("aria-invalid"),
    ).toBe("true");
  });

  it("rules are read-only outside draft or tested", async () => {
    serveVersion(
      version({ status: "SUBMITTED", pending_approval_request_id: APPROVAL_ID }),
      ruleSet("SUBMITTED"),
    );
    renderVersion();

    const container = await screen.findByTestId("SF-13-grid-rules");
    const grid = within(container).getByRole("grid", { name: "Rules" });
    expect(await within(grid).findByRole("rowheader", { name: "ROUTE-CON-01" })).toBeTruthy();
    expect(within(grid).getAllByText("Subject is CONTRACT_ACTIVATION")).toHaveLength(2);
    // The E-12 chip in the header (the stepper caption repeats the words).
    expect(
      [...document.querySelectorAll("[data-tone='info']")].map((chip) => chip.textContent),
    ).toContain("Pending approval");
    for (const name of ["Add rule", "Duplicate rule", "Remove rule", "Run tests", "Withdraw"]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
    expect(within(container).queryAllByRole("checkbox")).toHaveLength(0);
    // "Try a line" reads only (config.read), so it stays.
    expect(screen.getByRole("button", { name: "Try a line" })).toBeTruthy();

    fireEvent.click(within(grid).getByRole("link", { name: "ROUTE-CON-01" }));
    const drawer = await screen.findByRole("dialog", { name: "Rule ROUTE-CON-01" });
    expect(within(drawer).getByTestId("SF-13-drawer-rule")).toBeTruthy();
    expect(within(drawer).getByRole("group", { name: "Condition 1" })).toBeTruthy();
    expect(within(drawer).getByRole("rowheader", { name: "Revenue review" })).toBeTruthy();
    expect(within(drawer).queryByRole("button", { name: "Save rule" })).toBeNull();
  });

  it("New draft version copies a published version and opens the draft", async () => {
    const posted: Posted[] = [];
    serveVersion(
      version({
        status: "PUBLISHED",
        approval_request_id: APPROVAL_ID,
        published_at: "2026-09-02T10:00:00Z",
      }),
      ruleSet("PUBLISHED"),
      posted,
    );
    const { router } = renderVersion();

    fireEvent.click(await screen.findByRole("button", { name: "New draft version" }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(
        `/policies/rule-sets/${RULE_SET_ID}/versions/${DRAFT_ID}`,
      );
    });
    expect(posted).toEqual([
      {
        path: `/api/v1/rule-sets/${RULE_SET_ID}/versions`,
        body: { source_version_id: VERSION_ID },
      },
    ]);
    expect(await screen.findByRole("button", { name: "Run lint" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add rule" })).toBeTruthy();
  });
});

const INSTANT_HELP =
  "Empty or today: the version takes effect when it is approved. A later date: it takes effect at 12:00 UTC on that date, and the approval must come before then.";
// PRD §5.5 ERR-75, the instant form: `detail` and `errors[].message` are the same sentence.
const ERR_75_INSTANT =
  "This version replaces a published one. Choose an effective time that has not passed.";

/** The text of the elements that describe a control: its error first, then its help. */
function descriptionsOf(element: HTMLElement): string {
  return (element.getAttribute("aria-describedby") ?? "")
    .split(" ")
    .map((id) => document.getElementById(id)?.textContent ?? "")
    .join(" | ");
}

/** An obligation-assignment rule set: the engine chooses its version by a contract date (04 §16.5). */
function assignment(status: RuleSetVersion["status"]): RuleSet {
  return {
    ...ruleSet(status),
    code: "POB-ASSIGNMENT",
    name: "Obligation assignment",
    kind: "POB_ASSIGNMENT",
  };
}

function assignmentVersion(overrides: Partial<RuleSetVersion>): RuleSetVersion {
  return version({ rule_set_code: "POB-ASSIGNMENT", kind: "POB_ASSIGNMENT", ...overrides });
}

/** Serves `first` and records the bodies of its `PATCH`, which the next read answers with. */
function serveEditable(first: RuleSetVersion, set: RuleSet) {
  const patches: { readonly ifMatch: string | null; readonly body: unknown }[] = [];
  let stored = first;
  serveVersion(stored, set);
  server.use(
    http.get(apiUrl(`/api/v1/rule-set-versions/${VERSION_ID}`), () => HttpResponse.json(stored)),
    http.patch(apiUrl(`/api/v1/rule-set-versions/${VERSION_ID}`), async ({ request }) => {
      const body = (await request.json()) as { readonly effective_from: string | null };
      patches.push({ ifMatch: request.headers.get("If-Match"), body });
      stored = { ...stored, effective_from: body.effective_from, row_version: 4 };
      return HttpResponse.json(stored);
    }),
  );
  return patches;
}

async function effectiveField(): Promise<{
  readonly form: HTMLElement;
  readonly field: HTMLInputElement;
}> {
  const form = await screen.findByRole("form", { name: "Effective date" });
  return {
    form,
    field: within(form).getByRole<HTMLInputElement>("textbox", { name: /^Effective from/ }),
  };
}

describe("SF-13:rule-set-version effective date (DS-I18N-08; supervisor ruling R-59)", () => {
  // The editor reads today's UTC date when a date is saved (SCREENS §11.0, rev 1.31): the clock of
  // these cases stands at 15:00 UTC on 01 Oct 2026, after the 12:00 UTC a date goes on the wire as.
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"], now: instantMs("2026-10-01T15:00:00Z") });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("Save effective date sends 12:00:00Z of the picked date, and the stored instant reads back as that date", async () => {
    const patches: { readonly ifMatch: string | null; readonly body: unknown }[] = [];
    // A version stored before the ruling holds 00:00:00Z: it still reads as its UTC date.
    let stored = version({ status: "DRAFT" });
    serveVersion(stored, ruleSet("DRAFT"));
    server.use(
      http.get(apiUrl(`/api/v1/rule-set-versions/${VERSION_ID}`), () => HttpResponse.json(stored)),
      http.patch(apiUrl(`/api/v1/rule-set-versions/${VERSION_ID}`), async ({ request }) => {
        const body = (await request.json()) as { readonly effective_from: string };
        patches.push({ ifMatch: request.headers.get("If-Match"), body });
        stored = { ...stored, effective_from: body.effective_from, row_version: 4 };
        return HttpResponse.json(stored);
      }),
    );
    renderVersion();

    const form = await screen.findByRole("form", { name: "Effective date" });
    const field = within(form).getByRole<HTMLInputElement>("textbox", { name: /^Effective from/ });
    expect(field.value).toBe("01 Jan 2026");
    // Rev 1.31: an approval-routing rule set is read at an instant, so its date is optional.
    expect(within(form).getByText(INSTANT_HELP)).toBeTruthy();
    fireEvent.change(field, { target: { value: "2026-11-01" } });
    fireEvent.blur(field);
    fireEvent.click(within(form).getByRole("button", { name: "Save effective date" }));

    expect(await screen.findByText("Saved the effective date.")).toBeTruthy();
    // RuleSetVersionUpdateIn `effective_from` is date-time: an RFC 3339 UTC instant, never a date.
    expect(patches).toEqual([
      { ifMatch: '"r3"', body: { effective_from: "2026-11-01T12:00:00Z" } },
    ]);
    // The round trip: the refetched instant shows the date that was picked.
    expect(await screen.findByText("Effective 01 Nov 2026")).toBeTruthy();
    expect(field.value).toBe("01 Nov 2026");
  });

  it("a version that is no longer editable shows Effective from and Effective to as dates", async () => {
    serveVersion(
      version({
        status: "SUPERSEDED",
        approval_request_id: APPROVAL_ID,
        effective_from: "2026-01-01T12:00:00Z",
        effective_to: "2026-11-01T12:00:00Z",
        published_at: "2025-12-20T10:00:00Z",
      }),
      ruleSet("PUBLISHED"),
    );
    renderVersion();

    const details = await screen.findByRole("region", { name: "Version details" });
    const value = (term: string) =>
      within(details).getByText(term, { selector: "dt" }).nextElementSibling?.firstChild
        ?.textContent;
    expect(value("Effective from")).toBe("01 Jan 2026");
    expect(value("Effective to")).toBe("01 Nov 2026");
  });

  it("a version read at an instant and dated today is sent without an instant: it takes effect when it is approved", async () => {
    const patches = serveEditable(
      version({ status: "DRAFT", effective_from: "2026-11-01T12:00:00Z" }),
      ruleSet("DRAFT"),
    );
    renderVersion();

    const { form, field } = await effectiveField();
    expect(field.value).toBe("01 Nov 2026");
    expect(field.getAttribute("aria-required")).toBeNull();
    expect(within(form).getByText("(optional)")).toBeTruthy();
    // 12:00 UTC of 01 Oct 2026 has passed: the server would refuse it as a past instant (PRD ERR-75).
    fireEvent.change(field, { target: { value: "2026-10-01" } });
    fireEvent.blur(field);
    fireEvent.click(within(form).getByRole("button", { name: "Save effective date" }));

    expect(
      await screen.findByText("Saved. The version takes effect when it is approved."),
    ).toBeTruthy();
    expect(patches).toEqual([{ ifMatch: '"r3"', body: { effective_from: null } }]);
    // The field shows what is stored, and the stepper says when the version takes effect.
    expect(field.value).toBe("");
    expect(await screen.findByText("Effective on approval")).toBeTruthy();
  });

  it("a cleared date of a version read at an instant is saved as no instant", async () => {
    const patches = serveEditable(
      version({ status: "DRAFT", effective_from: "2026-11-01T12:00:00Z" }),
      ruleSet("DRAFT"),
    );
    renderVersion();

    const { form, field } = await effectiveField();
    fireEvent.change(field, { target: { value: "" } });
    fireEvent.blur(field);
    fireEvent.click(within(form).getByRole("button", { name: "Save effective date" }));

    expect(
      await screen.findByText("Saved. The version takes effect when it is approved."),
    ).toBeTruthy();
    expect(patches).toEqual([{ ifMatch: '"r3"', body: { effective_from: null } }]);
  });

  it("an assignment rule set is chosen by a contract date: today is sent as 12:00:00Z of today, and the date is required", async () => {
    const patches = serveEditable(
      assignmentVersion({ status: "DRAFT", effective_from: null }),
      assignment("DRAFT"),
    );
    renderVersion();

    const { form, field } = await effectiveField();
    expect(field.getAttribute("aria-required")).toBe("true");
    expect(within(form).queryByText("(optional)")).toBeNull();
    expect(descriptionsOf(field)).toBe("Contracts dated on or after this date use this version.");
    // Without a date nothing is sent, and the field says so.
    fireEvent.click(within(form).getByRole("button", { name: "Save effective date" }));
    expect(await within(form).findByText("Enter the effective date.")).toBeTruthy();
    expect(patches).toEqual([]);

    fireEvent.change(field, { target: { value: "2026-10-01" } });
    fireEvent.blur(field);
    fireEvent.click(within(form).getByRole("button", { name: "Save effective date" }));

    // The server decides whether today is late enough in every entity (PRD ERR-75, the date form).
    expect(await screen.findByText("Saved the effective date.")).toBeTruthy();
    expect(patches).toEqual([
      { ifMatch: '"r3"', body: { effective_from: "2026-10-01T12:00:00Z" } },
    ]);
    expect(field.value).toBe("01 Oct 2026");
  });

  it("a version that replaces the published one of an assignment rule set says so in the help of Effective from", async () => {
    serveEditable(
      assignmentVersion({ id: VERSION_ID, version_no: 2, status: "DRAFT", effective_from: null }),
      { ...assignment("PUBLISHED"), current_version: summary("PUBLISHED", DRAFT_ID) },
    );
    renderVersion();

    const { field } = await effectiveField();
    expect(descriptionsOf(field)).toBe(
      "Contracts dated on or after this date use this version. It replaces a published one, so choose a date later than today; the approval must come before that date.",
    );
  });

  it("Submit for approval needs a date on an assignment rule set and none on a version read at an instant", async () => {
    serveVersion(
      assignmentVersion({ status: "TESTED", effective_from: null }),
      assignment("TESTED"),
    );
    renderVersion();
    const blocked = await screen.findByRole("button", { name: "Submit for approval" });
    expect(blocked.getAttribute("aria-disabled")).toBe("true");
    cleanup();

    serveVersion(version({ status: "TESTED", effective_from: null }), ruleSet("TESTED"));
    renderVersion();
    const free = await screen.findByRole("button", { name: "Submit for approval" });
    expect(free.getAttribute("aria-disabled")).toBeNull();
    // Rev 1.31: without an instant the version takes effect when it is approved.
    expect(screen.getByText("Effective on approval")).toBeTruthy();
  });

  it("a version read at an instant without one reads On approval, and the date of its publication once it is published", async () => {
    serveVersion(
      version({ status: "SUBMITTED", approval_request_id: APPROVAL_ID, effective_from: null }),
      ruleSet("SUBMITTED"),
    );
    renderVersion();
    const details = await screen.findByRole("region", { name: "Version details" });
    const value = (region: HTMLElement, term: string) =>
      within(region).getByText(term, { selector: "dt" }).nextElementSibling?.firstChild
        ?.textContent;
    expect(value(details, "Effective from")).toBe("On approval");
    expect(screen.getByText("Effective on approval")).toBeTruthy();
    cleanup();

    serveVersion(
      version({
        status: "PUBLISHED",
        approval_request_id: APPROVAL_ID,
        effective_from: null,
        published_at: "2026-10-02T08:30:00Z",
      }),
      ruleSet("PUBLISHED"),
    );
    renderVersion();
    const published = await screen.findByRole("region", { name: "Version details" });
    expect(value(published, "Effective from")).toBe("02 Oct 2026");
    expect(screen.getByText("Effective 02 Oct 2026")).toBeTruthy();
  });

  it("Submit for approval refused with PRD ERR-75 shows the sentence at Effective from with focus, and the banner does not repeat it", async () => {
    serveVersion(
      version({ status: "TESTED", effective_from: "2026-09-30T12:00:00Z" }),
      ruleSet("TESTED"),
    );
    server.use(
      http.post(apiUrl(`/api/v1/rule-set-versions/${VERSION_ID}/submit`), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          detail: ERR_75_INSTANT,
          errors: [
            {
              field: "effective_from",
              sheet: null,
              row: null,
              rule_id: "REQ-POL-007",
              message: ERR_75_INSTANT,
            },
          ],
        }),
      ),
    );
    renderVersion();

    const { field } = await effectiveField();
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));

    await waitFor(() => {
      expect(descriptionsOf(field)).toBe(`${ERR_75_INSTANT} | ${INSTANT_HELP}`);
    });
    expect(field.getAttribute("aria-invalid")).toBe("true");
    expect(document.activeElement).toBe(field);
    const heading = screen.getByRole("heading", { name: "Check the highlighted fields" });
    expect(heading.closest('[role="alert"]')?.textContent).not.toContain(ERR_75_INSTANT);
    expect(screen.getAllByText(ERR_75_INSTANT)).toHaveLength(1);

    fireEvent.change(field, { target: { value: "2026-11-02" } });
    expect(screen.queryByText(ERR_75_INSTANT)).toBeNull();
    expect(screen.queryByRole("heading", { name: "Check the highlighted fields" })).toBeNull();
  });

  it("a successful Run tests and a saved effective date each clear the refusal of an earlier submission", async () => {
    const changed = "This version changed after its tests ran. Run the tests again.";
    let stored = version({ status: "TESTED", effective_from: null });
    serveVersion(stored, ruleSet("TESTED"));
    server.use(
      http.get(apiUrl(`/api/v1/rule-set-versions/${VERSION_ID}`), () => HttpResponse.json(stored)),
      http.patch(apiUrl(`/api/v1/rule-set-versions/${VERSION_ID}`), async ({ request }) => {
        const body = (await request.json()) as { readonly effective_from: string };
        stored = { ...stored, effective_from: body.effective_from, row_version: 4 };
        return HttpResponse.json(stored);
      }),
      http.post(apiUrl(`/api/v1/rule-set-versions/${VERSION_ID}/test`), () =>
        HttpResponse.json(stored),
      ),
      http.post(apiUrl(`/api/v1/rule-set-versions/${VERSION_ID}/submit`), () =>
        problemResponse("invalid-transition", 409, "Action not available in this state", {
          errors: [
            { field: "status", sheet: null, row: null, rule_id: "REQ-POL-003", message: changed },
          ],
        }),
      ),
    );
    renderVersion();

    const { form, field } = await effectiveField();
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    expect(await screen.findByText(changed)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Run tests" }));
    expect((await screen.findAllByText("2 of 2 tests passed.")).length).toBeGreaterThan(0);
    expect(screen.queryByText(changed)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    expect(await screen.findByText(changed)).toBeTruthy();
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
    const tested = version({ status: "TESTED", effective_from: "2026-09-30T12:00:00Z" });
    const read = heldRead();
    serveVersion(tested, ruleSet("TESTED"));
    server.use(
      http.get(apiUrl(`/api/v1/rule-set-versions/${VERSION_ID}`), async () => {
        await read.passed();
        return HttpResponse.json(tested);
      }),
      http.post(apiUrl(`/api/v1/rule-set-versions/${VERSION_ID}/test`), () => {
        read.hold();
        return HttpResponse.json(tested);
      }),
      http.post(apiUrl(`/api/v1/rule-set-versions/${VERSION_ID}/submit`), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          detail: ERR_75_INSTANT,
          errors: [
            {
              field: "effective_from",
              sheet: null,
              row: null,
              rule_id: "REQ-POL-007",
              message: ERR_75_INSTANT,
            },
          ],
        }),
      ),
    );
    renderVersion();

    const { field } = await effectiveField();
    fireEvent.click(screen.getByRole("button", { name: "Run tests" }));
    // The tests have answered; the version the page reads again has not.
    await waitFor(() => {
      expect(read.waiting()).toBeGreaterThan(0);
    });
    expect(screen.queryAllByText("2 of 2 tests passed.")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    await waitFor(() => {
      expect(descriptionsOf(field)).toBe(`${ERR_75_INSTANT} | ${INSTANT_HELP}`);
    });

    read.release();
    // The toast, and the same sentence announced.
    expect((await screen.findAllByText("2 of 2 tests passed.")).length).toBeGreaterThan(0);
    // The submission was sent after the tests: it is not the earlier one their success answers.
    expect(descriptionsOf(field)).toBe(`${ERR_75_INSTANT} | ${INSTANT_HELP}`);
    expect(field.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByRole("heading", { name: "Check the highlighted fields" })).toBeTruthy();
  });

  it("a submission refused while the reads after Save effective date are on their way keeps its refusal when they arrive", async () => {
    const changed = "This version changed after its tests ran. Run the tests again.";
    const read = heldRead();
    let stored = version({ status: "TESTED", effective_from: null });
    serveVersion(stored, ruleSet("TESTED"));
    server.use(
      http.get(apiUrl(`/api/v1/rule-set-versions/${VERSION_ID}`), async () => {
        await read.passed();
        return HttpResponse.json(stored);
      }),
      http.patch(apiUrl(`/api/v1/rule-set-versions/${VERSION_ID}`), async ({ request }) => {
        read.hold();
        const body = (await request.json()) as { readonly effective_from: string };
        stored = { ...stored, effective_from: body.effective_from, row_version: 4 };
        return HttpResponse.json(stored);
      }),
      http.post(apiUrl(`/api/v1/rule-set-versions/${VERSION_ID}/submit`), () =>
        problemResponse("invalid-transition", 409, "Action not available in this state", {
          errors: [
            { field: "status", sheet: null, row: null, rule_id: "REQ-POL-003", message: changed },
          ],
        }),
      ),
    );
    renderVersion();

    const { form, field } = await effectiveField();
    fireEvent.change(field, { target: { value: "2026-11-02" } });
    fireEvent.blur(field);
    fireEvent.click(within(form).getByRole("button", { name: "Save effective date" }));
    await waitFor(() => {
      expect(read.waiting()).toBeGreaterThan(0);
    });
    expect(screen.queryByText("Saved the effective date.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
    expect(await screen.findByText(changed)).toBeTruthy();

    read.release();
    expect(await screen.findByText("Saved the effective date.")).toBeTruthy();
    const heading = screen.getByRole("heading", { name: "Action not available in this state" });
    expect(heading.closest('[role="alert"]')?.textContent).toContain(changed);
  });
});

describe("SF-13 rule summaries and the changes diff", () => {
  it("conditions and outputs read as SCREENS §11.1 text", () => {
    expect(
      conditionSummary([
        { field: "subject.type", op: "eq", value: "CONTRACT_ACTIVATION" },
        { field: "amount.functional", op: "gte", value: "1000000.00" },
      ]),
    ).toBe("Subject is CONTRACT_ACTIVATION · Amount at least 1,000,000");
    expect(conditionSummary([{ field: "effective_date", op: "lte", value: "2026-12-31" }])).toBe(
      "Effective date on or before 31 Dec 2026",
    );
    expect(
      outputSummary("APPROVAL_ROUTING", {
        steps: [
          { name: "Revenue review", permission: "contract.approve", min_approvers: 1 },
          { name: "Controller approval", permission: "period.reopen_approve", min_approvers: 2 },
        ],
      }),
    ).toBe("Step 1: contract.approve · Step 2: period.reopen_approve × 2");
    expect(outputSummary("AUTO_APPROVAL", { auto_approve: true })).toBe("Approve automatically");
  });

  it("rules are added, removed and changed by rule key", () => {
    const changes = compareRules(
      [rule("ROUTE-CON-01", { priority: 10 }), rule("ROUTE-NEW")],
      [rule("ROUTE-CON-01"), rule("ROUTE-OLD")],
    );
    expect(
      changes.map((change) => [change.kind, change.rule.rule_key, [...change.changed]]),
    ).toEqual([
      ["changed", "ROUTE-CON-01", ["priority"]],
      ["added", "ROUTE-NEW", []],
      ["removed", "ROUTE-OLD", []],
    ]);
  });
});
