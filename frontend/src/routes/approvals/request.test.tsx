// @vitest-environment jsdom
// SF-12:request and REQ-UX-012 (BUILD_SPEC WEB-15; SCREENS §15.4, §15.6, §15.10; §0.6 SCR-PERM-05; 04
// API-R-09 §16.10; PRD ERR-02 to ERR-04, ERR-28): the request header and routing steps, the preparer
// notice, the required comment, Approve with the reviewed hashes and the move to the next request, the
// Reject confirmation, the decision problems, stale requests and the step-up resend.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { createQueryClient } from "../../app/providers";
import { appRoutes, builtPaths, SCREEN_ROUTES } from "../../app/router";
import type { Approval, PreviewDocument } from "../../lib/api/queries/approvals";
import type { Judgement } from "../../lib/api/queries/contracts";
import type { Period } from "../../lib/api/queries/tenant";
import { NBSP, registerCurrencies } from "../../lib/format";
import { installMemoryStorage, renderApp, signedInMe, signedInSession } from "../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import {
  containingView,
  displayValue,
  fieldChanges,
  impactIsEmpty,
  memberLabel,
  periodLabeller,
  SUBJECT_ROUTES,
} from "./request";

installMswServer();
installMemoryStorage();

afterEach(() => {
  cleanup();
});

const VIEWER_ID = signedInSession().user.id;
const TOMAS = {
  id: "9e8d7c6b-5a4f-4e3d-8c2b-1a0f9e8d7c6b",
  display_name: "Tomás Rivera",
  kind: "USER",
} as const;
const MAYA = { id: VIEWER_ID, display_name: "Maya Chen", kind: "USER" } as const;
const PRIYA = {
  id: "4d3c2b1a-0f9e-4d8c-9b7a-6f5e4d3c2b1a",
  display_name: "Priya Raman",
  kind: "USER",
} as const;

const REQUEST_A = "8f0c5a1e-3b2d-4c6e-9a7f-1d2e3f4a5b6c";
const REQUEST_B = "3c4d5e6f-7a8b-4c9d-8e0f-1a2b3c4d5e6f";
const PREVIEW_FILE = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d";
const SUBJECT_HASH = "a".repeat(64);
const PREVIEW_HASH = "b".repeat(64);
const COMMENT = "Supported by H1 standalone sales.";

const APPROVER = signedInMe({ permissions: ["ssp.read", "ssp.approve"] });

function approval(overrides: Partial<Approval> = {}): Approval {
  return {
    id: REQUEST_A,
    request_no: "APR-000231",
    subject: {
      type: "SSP_BOOK_VERSION",
      id: "7d1e2f3a-4b5c-4d6e-8f7a-9b0c1d2e3f4a",
      display: "SSP book version US-LIST 2026-H2",
      href: null,
      content_sha256: SUBJECT_HASH,
      row_version: 4,
    },
    summary: "SSP book version US-LIST 2026-H2",
    status: "PENDING",
    entity: null,
    entities: [],
    entity_count: 0,
    all_entities: false,
    amount: null,
    flags: [],
    routing: { rule_set_version_id: null, rule_key: null },
    preparer: TOMAS,
    submitted_at: "2026-09-12T14:05:00Z",
    decided_at: null,
    voided_at: null,
    void_reason: null,
    current_step_no: 2,
    steps: [
      {
        step_no: 1,
        name: "SSP approval",
        required_permission: "ssp.approve",
        min_approvers: 1,
        status: "APPROVED",
        decisions: [
          {
            id: "5e6f7a8b-9c0d-4e1f-8a2b-3c4d5e6f7a8b",
            decision: "APPROVE",
            approver: PRIYA,
            on_behalf_of: null,
            decided_at: "2026-09-12T15:10:00Z",
            comment: "Range supported by the study.",
            reason_code: null,
            auto_rule_key: null,
          },
        ],
      },
      {
        step_no: 2,
        name: "SSP approval",
        required_permission: "ssp.approve",
        min_approvers: 1,
        status: "ACTIVE",
        decisions: [],
      },
    ],
    impact_preview: null,
    attachments: [],
    can_decide: true,
    content_withheld: false,
    reason_code: null,
    comment: null,
    ...overrides,
  };
}

const SECOND = approval({
  id: REQUEST_B,
  request_no: "APR-000232",
  summary: "Manual adjustment BG-AVM-0022",
  subject: {
    type: "MANUAL_ADJUSTMENT",
    id: "2b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6e",
    display: "Manual adjustment BG-AVM-0022",
    href: null,
    content_sha256: "d".repeat(64),
    row_version: 1,
  },
});

const PREVIEW: PreviewDocument = {
  before: {
    object_type: "role",
    role_id: "6c5d4e3f-2a1b-4c0d-9e8f-7a6b5c4d3e2f",
    role_code: "deal_desk_analyst",
    permissions: [],
    is_active: false,
  },
  after: {
    object_type: "role",
    role_id: "6c5d4e3f-2a1b-4c0d-9e8f-7a6b5c4d3e2f",
    role_code: "deal_desk_analyst",
    permissions: ["scenario.use"],
  },
};

interface Reads {
  /** The detail of each request id; a function answers per call. */
  readonly details: Readonly<Record<string, Approval | (() => Approval)>>;
  /** The list answered for every view; a function answers per call. */
  readonly list: readonly Approval[] | (() => readonly Approval[]);
}

function serve({ details, list }: Reads): void {
  server.use(
    http.get(apiUrl("/api/v1/approvals"), () =>
      HttpResponse.json(
        { items: typeof list === "function" ? list() : list, next_cursor: null },
        { headers: { "X-Erev-Total-Count": "2" } },
      ),
    ),
    http.get(apiUrl("/api/v1/approvals/:id"), ({ params }) => {
      const detail = details[String(params.id)];
      if (detail === undefined) {
        return problemResponse("not-found", 404, "Not found");
      }
      return HttpResponse.json(typeof detail === "function" ? detail() : detail);
    }),
    http.get(apiUrl(`/api/v1/files/${PREVIEW_FILE}/content`), () => HttpResponse.json(PREVIEW)),
    // A successful command refreshes the shell's notifications badge (lib/api/commands.ts).
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
  );
}

function renderRequest(entry: string, me = APPROVER) {
  return renderApp(entry, { me, screenRoutes: SCREEN_ROUTES });
}

async function decisionForm(): Promise<HTMLElement> {
  return screen.findByRole("form", { name: "Decision" });
}

function typeComment(text: string): void {
  fireEvent.change(screen.getByLabelText("Comment (required)"), { target: { value: text } });
}

describe("SF-12:request and REQ-UX-012", () => {
  it("the header shows request_no, type label, status chip, preparer and routing steps <step name> · <n> of <min_approvers> recorded", async () => {
    serve({ details: { [REQUEST_A]: approval() }, list: [approval(), SECOND] });
    renderRequest(`/approvals/requests/${REQUEST_A}`);

    const region = await screen.findByRole("region", {
      name: "Request details: SSP book version US-LIST 2026-H2",
    });
    const header = within(region);
    expect(await header.findByText("APR-000231")).toBeTruthy();
    expect(
      header.getByRole("heading", { level: 2, name: "APR-000231 SSP book version" }),
    ).toBeTruthy();
    expect(header.getByText("Pending approval")).toBeTruthy();
    expect(header.getByText("Tomás Rivera submitted 12 Sep 2026 14:05 UTC")).toBeTruthy();
    const routing = header.getByRole("list", { name: "Routing" });
    expect(within(routing).getByText("SSP approval · 1 of 1 recorded")).toBeTruthy();
    expect(within(routing).getByText("SSP approval · 0 of 1 recorded")).toBeTruthy();
    expect(within(routing).getByText("Priya Raman")).toBeTruthy();
    expect(within(routing).getByText("12 Sep 2026 15:10 UTC")).toBeTruthy();
    expect(within(routing).getByText("Range supported by the study.")).toBeTruthy();
    // SCREENS §15.4 region 4 rev 1.18 (R-104 (a)): without a stored preview nothing was computed, so the
    // pane does not claim "No impact on revenue or balances."; it says that no preview is stored.
    expect(header.queryByText("No impact on revenue or balances.")).toBeNull();
    expect(header.getByText("No preview is stored for this request")).toBeTruthy();
    expect(await decisionForm()).toBeTruthy();

    // can_decide: the request renders inside Waiting for me.
    expect(
      screen.getByRole("link", { name: "Waiting for me 2" }).getAttribute("aria-current"),
    ).toBe("page");
  });

  it("the header names the entities of the request, and nothing for a request that names none (API-S-Approval entities)", async () => {
    const entities = [
      { id: "9f8e7d6c-5b4a-4c3d-8e2f-1a0b9c8d7e6f", code: "AVM-DE", name: "Avenmoor DE" },
      { id: "2a3b4c5d-6e7f-4a8b-9c0d-1e2f3a4b5c6d", code: "AVM-US", name: "Avenmoor US" },
    ];
    const named = approval({ entities, entity_count: 2 });
    serve({ details: { [REQUEST_A]: named, [REQUEST_B]: SECOND }, list: [named, SECOND] });
    renderRequest(`/approvals/requests/${REQUEST_A}`);

    const region = await screen.findByRole("region", {
      name: "Request details: SSP book version US-LIST 2026-H2",
    });
    expect(await within(region).findByText("Entities: AVM-DE, AVM-US")).toBeTruthy();

    cleanup();
    serve({ details: { [REQUEST_A]: approval() }, list: [approval(), SECOND] });
    renderRequest(`/approvals/requests/${REQUEST_A}`);
    const bare = await screen.findByRole("region", {
      name: "Request details: SSP book version US-LIST 2026-H2",
    });
    await within(bare).findByText("APR-000231");
    expect(within(bare).queryByTestId("SF-12-entities")).toBeNull();
  });

  it("the preparer sees You submitted this request. Another approver must review it. and no decision form", async () => {
    const own = approval({ preparer: MAYA, can_decide: false });
    serve({ details: { [REQUEST_A]: own }, list: [own] });
    renderRequest(`/approvals/requests/${REQUEST_A}`);

    const banner = await screen.findByTestId("SF-12-banner-sod");
    expect(
      within(banner).getByText("You submitted this request. Another approver must review it."),
    ).toBeTruthy();
    expect(screen.queryByRole("form", { name: "Decision" })).toBeNull();
    expect(screen.getByRole("button", { name: "Withdraw request" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Submitted by me" }).getAttribute("aria-current")).toBe(
      "page",
    );
  });

  it("the decision form requires Comment (required) of at least 10 characters", async () => {
    const posts: unknown[] = [];
    serve({ details: { [REQUEST_A]: approval() }, list: [approval()] });
    server.use(
      http.post(apiUrl(`/api/v1/approvals/${REQUEST_A}/approve`), async ({ request }) => {
        posts.push(await request.json());
        return HttpResponse.json(approval());
      }),
    );
    renderRequest(`/approvals/requests/${REQUEST_A}?view=waiting`);

    await decisionForm();
    typeComment("Too short");
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    expect(await screen.findByText("Enter at least 10 characters.")).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByLabelText("Comment (required)"));
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(posts).toEqual([]);
  });

  it("Approve sends subject_content_sha256 and impact_preview_sha256, shows the toast Approved: <summary>. and moves focus to the next request", async () => {
    const withPreview = approval({
      impact_preview: {
        file_id: PREVIEW_FILE,
        sha256: PREVIEW_HASH,
        summary: {
          revenue_by_period_before: null,
          revenue_by_period_after: null,
          balances_before: null,
          balances_after: null,
          journal_lines: null,
          catch_up_total: null,
          criteria_met: null,
        },
      },
    });
    let approved = false;
    const bodies: unknown[] = [];
    serve({
      details: { [REQUEST_A]: withPreview, [REQUEST_B]: SECOND },
      list: () => (approved ? [SECOND] : [withPreview, SECOND]),
    });
    server.use(
      http.post(apiUrl(`/api/v1/approvals/${REQUEST_A}/approve`), async ({ request }) => {
        bodies.push(await request.json());
        approved = true;
        return HttpResponse.json({ ...withPreview, status: "APPROVED", can_decide: false });
      }),
    );
    const { router } = renderRequest(`/approvals/requests/${REQUEST_A}?view=waiting`);

    const diff = await screen.findByRole("table", { name: /^Proposed changes/ });
    expect(within(diff).getByRole("rowheader", { name: "Permissions" })).toBeTruthy();
    expect(within(diff).getByText("scenario.use")).toBeTruthy();
    expect(screen.getByTestId("SF-12-diff")).toBeTruthy();

    typeComment(COMMENT);
    fireEvent.click(within(await decisionForm()).getByRole("button", { name: "Approve" }));

    expect(await screen.findByText("Approved: SSP book version US-LIST 2026-H2.")).toBeTruthy();
    expect(bodies).toEqual([
      {
        subject_content_sha256: SUBJECT_HASH,
        impact_preview_sha256: PREVIEW_HASH,
        comment: COMMENT,
      },
    ]);
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/approvals/requests/${REQUEST_B}`);
    });
    await waitFor(() => {
      const active = document.activeElement;
      expect(active?.getAttribute("role")).toBe("option");
      expect(active?.textContent).toContain("Manual adjustment BG-AVM-0022");
    });
  });

  it("a stored impact preview that cannot be loaded is named and Approve is unavailable until it loads (REQ-PLT-015)", async () => {
    const withPreview = approval({
      impact_preview: {
        file_id: PREVIEW_FILE,
        sha256: PREVIEW_HASH,
        summary: {
          revenue_by_period_before: null,
          revenue_by_period_after: null,
          balances_before: null,
          balances_after: null,
          journal_lines: null,
          catch_up_total: null,
          criteria_met: null,
        },
      },
    });
    let readable = false;
    const bodies: unknown[] = [];
    serve({ details: { [REQUEST_A]: withPreview }, list: [withPreview] });
    server.use(
      http.get(apiUrl(`/api/v1/files/${PREVIEW_FILE}/content`), () =>
        readable ? HttpResponse.json(PREVIEW) : problemResponse("not-found", 404, "Not found"),
      ),
      http.post(apiUrl(`/api/v1/approvals/${REQUEST_A}/approve`), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ ...withPreview, status: "APPROVED", can_decide: false });
      }),
    );
    renderRequest(`/approvals/requests/${REQUEST_A}?view=waiting`);

    // Security review P3-4: the panel rendered no diff, said nothing and offered Approve.
    const banner = await screen.findByTestId("SF-12-banner-preview");
    expect(within(banner).getByText("The impact preview could not be loaded")).toBeTruthy();
    expect(
      within(banner).getByText(
        "Approve is unavailable until the preview loads. Reload the page, or reject the request.",
      ),
    ).toBeTruthy();
    expect(screen.queryByTestId("SF-12-diff")).toBeNull();
    const form = await decisionForm();
    const approve = within(form).getByRole("button", { name: "Approve" });
    expect(approve.getAttribute("aria-disabled")).toBe("true");
    typeComment(COMMENT);
    fireEvent.click(approve);
    // The request can still be sent back.
    expect(
      within(form).getByRole("button", { name: "Reject" }).getAttribute("aria-disabled"),
    ).toBeNull();
    expect(bodies).toEqual([]);

    // Positive control: once the preview loads, the diff shows and Approve sends its hash.
    readable = true;
    fireEvent.click(within(banner).getByRole("button", { name: "Retry" }));
    expect(await screen.findByTestId("SF-12-diff")).toBeTruthy();
    expect(screen.queryByTestId("SF-12-banner-preview")).toBeNull();
    const available = within(await decisionForm()).getByRole("button", { name: "Approve" });
    expect(available.getAttribute("aria-disabled")).toBeNull();
    fireEvent.click(available);
    expect(await screen.findByText("Approved: SSP book version US-LIST 2026-H2.")).toBeTruthy();
    expect(bodies).toEqual([
      {
        subject_content_sha256: SUBJECT_HASH,
        impact_preview_sha256: PREVIEW_HASH,
        comment: COMMENT,
      },
    ]);
  });

  it("Reject opens Reject <summary>? with initial focus Cancel and the Danger Reject request", async () => {
    const bodies: unknown[] = [];
    serve({ details: { [REQUEST_A]: approval() }, list: [approval()] });
    server.use(
      http.post(apiUrl(`/api/v1/approvals/${REQUEST_A}/reject`), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ ...approval(), status: "REJECTED", can_decide: false });
      }),
    );
    renderRequest(`/approvals/requests/${REQUEST_A}?view=waiting`);

    await decisionForm();
    typeComment("Range too wide for the observed sales.");
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));

    const dialog = await screen.findByRole("alertdialog", {
      name: "Reject SSP book version US-LIST 2026-H2?",
    });
    expect(
      within(dialog).getByText("The preparer is notified and the item returns to Draft."),
    ).toBeTruthy();
    expect(within(dialog).getByText("Range too wide for the observed sales.")).toBeTruthy();
    expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: "Cancel" }));
    const danger = within(dialog).getByRole("button", { name: "Reject request" });
    expect(danger.className).toContain("bg-danger-solid");

    fireEvent.click(danger);
    expect(await screen.findByText("Rejected: SSP book version US-LIST 2026-H2.")).toBeTruthy();
    expect(bodies).toEqual([{ comment: "Range too wide for the observed sales." }]);
  });

  it.each([
    [
      "self-approval",
      403,
      "Self-approval not allowed",
      "You prepared this item, so another user must approve it.",
    ],
    [
      "approver-already-decided",
      409,
      "Approver already decided",
      "You approved an earlier step of this item. Another approver must decide this step.",
    ],
  ])(
    "a %s problem shows its ERR copy inside the decision form",
    async (slug, status, title, copy) => {
      serve({ details: { [REQUEST_A]: approval() }, list: [approval()] });
      server.use(
        http.post(apiUrl(`/api/v1/approvals/${REQUEST_A}/approve`), () =>
          problemResponse(slug, status, title, { detail: copy }),
        ),
      );
      renderRequest(`/approvals/requests/${REQUEST_A}?view=waiting`);

      await decisionForm();
      typeComment(COMMENT);
      fireEvent.click(screen.getByRole("button", { name: "Approve" }));

      const form = await decisionForm();
      expect(await within(form).findByRole("heading", { level: 3, name: copy })).toBeTruthy();
    },
  );

  it("a 409 stale-approval turns the chip to Stale, removes the form and shows Voided: this item changed after submission.", async () => {
    serve({ details: { [REQUEST_A]: approval() }, list: [approval()] });
    server.use(
      http.post(apiUrl(`/api/v1/approvals/${REQUEST_A}/approve`), () =>
        problemResponse("stale-approval", 409, "Approval voided", {
          detail:
            "This item changed after submission, so the approval request was voided. Review the latest version.",
        }),
      ),
    );
    renderRequest(`/approvals/requests/${REQUEST_A}?view=waiting`);

    await decisionForm();
    typeComment(COMMENT);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    expect(await screen.findByText("Voided: this item changed after submission.")).toBeTruthy();
    expect(
      screen.getByText(
        "The record changed after this request was submitted. The maker must resubmit it.",
      ),
    ).toBeTruthy();
    const region = screen.getByRole("region", {
      name: "Request details: SSP book version US-LIST 2026-H2",
    });
    expect(within(region).getByText("Stale")).toBeTruthy();
    expect(within(region).queryByText("Pending approval")).toBeNull();
    expect(screen.queryByRole("form", { name: "Decision" })).toBeNull();
  });

  it("an approval refused with PRD ERR-75 tells the approver what she can do, keeps the form, and does not ask her for a date", async () => {
    // PRD §5.5 ERR-75 at the decision (04 §16.5): nothing of the decision is kept and the request
    // stays pending. `detail` and `errors[].message` are the author's sentence.
    const authors =
      "This version replaces a published one. Choose an effective date later than today.";
    const pending = approval({
      summary: "Obligation template TPL-SUB-DAILY v2",
      subject: {
        type: "POB_TEMPLATE_VERSION",
        id: "7d1e2f3a-4b5c-4d6e-8f7a-9b0c1d2e3f4a",
        display: "Obligation template TPL-SUB-DAILY v2",
        href: null,
        content_sha256: SUBJECT_HASH,
        row_version: 4,
      },
    });
    serve({ details: { [REQUEST_A]: pending }, list: [pending] });
    server.use(
      http.post(apiUrl(`/api/v1/approvals/${REQUEST_A}/approve`), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          detail: authors,
          errors: [
            {
              field: "effective_from",
              sheet: null,
              row: null,
              rule_id: "REQ-POL-007",
              message: authors,
            },
          ],
        }),
      ),
    );
    renderRequest(`/approvals/requests/${REQUEST_A}?view=waiting`);

    const form = await decisionForm();
    typeComment(COMMENT);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    expect(
      await within(form).findByText(
        `This version replaces a published one and its effective date has been reached, so it can no longer be approved. Reject the request, or ask ${pending.preparer.display_name} to withdraw it: the version can then be given a later date and submitted again.`,
      ),
    ).toBeTruthy();
    // The approver has no effective-date field: neither the author's sentence nor the title that
    // points at one is shown.
    expect(screen.queryByText(authors)).toBeNull();
    expect(screen.queryByText("Check the highlighted fields")).toBeNull();
    // The request is still hers to decide.
    expect(within(form).getByRole("button", { name: "Approve" })).toBeTruthy();
    expect(within(form).getByRole("button", { name: "Reject" })).toBeTruthy();
  });

  it("a 403 mfa-step-up-required opens Confirm with your authenticator and resends with the same Idempotency-Key", async () => {
    const keys: (string | null)[] = [];
    const bodies: unknown[] = [];
    serve({ details: { [REQUEST_A]: approval() }, list: [approval()] });
    server.use(
      http.post(apiUrl(`/api/v1/approvals/${REQUEST_A}/approve`), async ({ request }) => {
        keys.push(request.headers.get("Idempotency-Key"));
        bodies.push(await request.json());
        if (keys.length === 1) {
          return problemResponse("mfa-step-up-required", 403, "Confirm with your authenticator", {
            detail: "Enter a code from your authenticator app to continue.",
          });
        }
        return HttpResponse.json({ ...approval(), status: "APPROVED", can_decide: false });
      }),
      http.post(apiUrl("/api/v1/session/mfa"), () =>
        HttpResponse.json({ ...signedInSession(), recovery_codes_remaining: null }),
      ),
    );
    renderRequest(`/approvals/requests/${REQUEST_A}?view=waiting`);

    await decisionForm();
    typeComment(COMMENT);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    const dialog = await screen.findByRole("dialog", { name: "Confirm with your authenticator" });
    const code = within(dialog).getByRole("textbox", { name: "Authentication code" });
    expect(code.getAttribute("autocomplete")).toBe("one-time-code");
    fireEvent.change(code, { target: { value: "123456" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm" }));

    expect(await screen.findByText("Approved: SSP book version US-LIST 2026-H2.")).toBeTruthy();
    expect(keys).toHaveLength(2);
    expect(keys[0]).not.toBeNull();
    expect(keys[1]).toBe(keys[0]);
    expect(bodies[1]).toEqual(bodies[0]);
  });

  it("an unknown request reads Approval request not found", async () => {
    serve({ details: {}, list: [] });
    renderRequest(`/approvals/requests/${REQUEST_B}?view=all`);

    expect(
      await screen.findByRole("heading", { level: 2, name: "Approval request not found" }),
    ).toBeTruthy();
  });

  it("containing view, impact notice and the generic field diff", () => {
    expect(containingView(approval(), VIEWER_ID)).toBe("waiting");
    expect(containingView(approval({ preparer: MAYA, can_decide: false }), VIEWER_ID)).toBe(
      "submitted",
    );
    expect(containingView(approval({ can_decide: false }), VIEWER_ID)).toBe("all");

    expect(impactIsEmpty(null)).toBe(true);
    expect(
      impactIsEmpty({
        file_id: PREVIEW_FILE,
        sha256: PREVIEW_HASH,
        summary: {
          revenue_by_period_before: {},
          revenue_by_period_after: { "FY2026-P09": "45000.00" },
          balances_before: null,
          balances_after: null,
          journal_lines: [],
          catch_up_total: null,
          criteria_met: null,
        },
      }),
    ).toBe(false);

    expect(memberLabel("role_code")).toBe("Role code");
    expect(displayValue(["a", "b"])).toBe("a, b");
    expect(displayValue([])).toBeNull();
    expect(displayValue(false)).toBe("No");
    expect(fieldChanges(PREVIEW)).toEqual([
      {
        id: "role_code",
        field: "Role code",
        kind: "unchanged",
        current: "deal_desk_analyst",
        proposed: "deal_desk_analyst",
      },
      {
        id: "permissions",
        field: "Permissions",
        kind: "changed",
        current: null,
        proposed: "scenario.use",
      },
      { id: "is_active", field: "Is active", kind: "removed", current: "No", proposed: null },
    ]);
  });

  it("the generic field diff formats money, period amounts and member labels (D-90a QA-L9-5a)", () => {
    registerCurrencies([{ code: "USD", minor_unit: 2 }]);
    const changes = fieldChanges(ACTIVATION_PREVIEW, { periodLabel: periodLabeller([SEP_2026]) });
    expect(changes).toEqual([
      { id: "status", field: "Status", kind: "changed", current: "DRAFT", proposed: "ACTIVE" },
      {
        id: "transaction_price",
        field: "Transaction price",
        kind: "changed",
        current: "USD 0.00",
        proposed: "USD 146,000.00",
      },
      {
        id: "rpo",
        field: "RPO",
        kind: "changed",
        current: "USD 0.00",
        proposed: "USD 146,000.00",
      },
      {
        id: "revenue_by_period",
        field: "Revenue by period",
        kind: "changed",
        // SCREENS §15.4 region 5 rev 1.18 (R-104 (b)): the row says which periods it lists.
        note: "The first six periods from Sep 2026; later periods are not listed.",
        // FY2026-P10 has no calendar row, so its raw key stands.
        current: "Sep 2026 USD 0.00\nFY2026-P10 USD 0.00",
        proposed: "Sep 2026 USD 12,166.67\nFY2026-P10 USD 12,166.67",
      },
      { id: "balances", field: "Balances", kind: "unchanged", current: null, proposed: null },
      {
        id: "journal_lines",
        field: "Journal lines",
        kind: "added",
        current: null,
        proposed:
          "GL account 2300 · Account role Contract liability · Debit USD 0.00 · Credit USD 12,166.67",
      },
    ]);
    // The status of a contract activation reads the contract status words (§0.8); a subject type
    // without a known enumeration keeps the literal, as above.
    expect(
      fieldChanges(ACTIVATION_PREVIEW, { subjectType: "CONTRACT_ACTIVATION" }).find(
        (change) => change.id === "status",
      ),
    ).toMatchObject({ current: "Draft", proposed: "Active" });
    expect(
      fieldChanges(
        { before: { status: "ARCHIVED" }, after: { status: "ACTIVE" } },
        { subjectType: "CONTRACT_VOID" },
      )[0],
    ).toMatchObject({ current: "ARCHIVED", proposed: "Active" });
    // No raw JSON reaches the reviewer.
    for (const change of changes) {
      expect(`${change.current ?? ""} ${change.proposed ?? ""}`).not.toMatch(/[{}"]/);
    }
    expect(displayValue([usd("1.00"), usd("2.50")])).toBe("USD 1.00, USD 2.50");
    // An unregistered currency shows no value (L3-3-Q-26).
    expect(displayValue({ amount: "10.00", currency: "XYZ" })).toBeNull();
    // A key without a row, or a row that cannot be labelled, reads as the raw key; nothing throws.
    const unlabelled = periodLabeller([
      { period: { ...SEP_2026.period, period_key: "2026-09", start_date: "not a date" } },
    ]);
    expect(unlabelled("2026-09")).toBe("2026-09");
    expect(periodLabeller(undefined)("FY2026-P09")).toBe("FY2026-P09");
  });

  it("an IMPORT_COMMIT diff_summary shows nested members to depth 2 and empty members as no value", () => {
    const committed: PreviewDocument = {
      before: { import_no: "IMP-000042", status: "DIFF_READY" },
      after: {
        diff_summary: {
          contracts_affected: 2,
          contracts_created: 1,
          allocation_changes: [
            { contract_external_id: "SF-ORD-10001", before: null, after: "118800.00" },
            { contract_external_id: "SF-ORD-10002", before: "16200.00", after: "16500.00" },
          ],
          revenue_by_period_delta: [{ period_key: "FY2026-P09", amount: "1200.00" }],
          journal_preview: [],
          balances: {},
        },
      },
    };
    expect(fieldChanges(committed, { periodLabel: periodLabeller([SEP_2026]) })).toEqual([
      { id: "import_no", field: "Import", kind: "removed", current: "IMP-000042", proposed: null },
      { id: "status", field: "Status", kind: "removed", current: "DIFF_READY", proposed: null },
      {
        id: "diff_summary",
        field: "Diff summary",
        kind: "added",
        current: null,
        proposed: [
          "Contracts affected 2",
          "Contracts created 1",
          "Allocation changes Contract SF-ORD-10001 · Before — · After 118800.00; Contract SF-ORD-10002 · Before 16200.00 · After 16500.00",
          "Revenue change by period Sep 2026 1200.00",
          "Journal preview —",
          "Balances —",
        ].join(" · "),
      },
    ]);
    // An empty diff_summary is no value, and a record below depth 2 is not expanded.
    expect(fieldChanges({ before: {}, after: { diff_summary: {} } })).toEqual([
      { id: "diff_summary", field: "Diff summary", kind: "added", current: null, proposed: null },
    ]);
    expect(displayValue({ outer: { inner: { deep: 1 } } })).toBe("Outer Inner —");
  });

  it("a record-array before-state shows one record per line and hides id and *_ids members", () => {
    const assignment: PreviewDocument = {
      before: {
        membership_id: "7a8b9c0d-1e2f-4a3b-8c4d-5e6f7a8b9c0d",
        assignments: [
          {
            role_code: "revenue_accountant",
            is_all_entities: false,
            entity_ids: ["0a1b2c3d-4e5f-4a6b-8c7d-000000000001"],
          },
          { role_code: "viewer", is_all_entities: true, entity_ids: [] },
        ],
      },
      after: {
        membership_id: "7a8b9c0d-1e2f-4a3b-8c4d-5e6f7a8b9c0d",
        assignments: [{ role_code: "viewer", is_all_entities: true, entity_ids: [] }],
      },
    };
    expect(fieldChanges(assignment)).toEqual([
      {
        id: "assignments",
        field: "Assignments",
        kind: "changed",
        current:
          "Role code revenue_accountant · Is all entities No\nRole code viewer · Is all entities Yes",
        proposed: "Role code viewer · Is all entities Yes",
      },
    ]);
  });

  it("SF-12:request shows a CONTRACT_ACTIVATION preview formatted, without raw JSON", async () => {
    const activation = approval({
      subject: {
        type: "CONTRACT_ACTIVATION",
        id: "6f7a8b9c-0d1e-4f2a-9b3c-4d5e6f7a8b9c",
        display: "Contract activation BG-AVM-0020",
        href: null,
        content_sha256: SUBJECT_HASH,
        row_version: 3,
      },
      summary: "Contract activation BG-AVM-0020",
      impact_preview: {
        file_id: PREVIEW_FILE,
        sha256: PREVIEW_HASH,
        summary: {
          revenue_by_period_before: {},
          revenue_by_period_after: { "FY2026-P09": "12166.67" },
          balances_before: null,
          balances_after: null,
          journal_lines: [],
          catch_up_total: null,
          criteria_met: null,
        },
      },
    });
    serve({ details: { [REQUEST_A]: activation }, list: [activation] });
    server.use(
      http.get(apiUrl(`/api/v1/files/${PREVIEW_FILE}/content`), () =>
        HttpResponse.json(ACTIVATION_PREVIEW),
      ),
      http.get(apiUrl("/api/v1/currencies"), () =>
        HttpResponse.json({ items: [{ code: "USD", minor_unit: 2 }], next_cursor: null }),
      ),
      http.get(apiUrl("/api/v1/periods"), () =>
        HttpResponse.json({ items: [SEP_2026], next_cursor: null }),
      ),
    );
    renderRequest(`/approvals/requests/${REQUEST_A}`);

    const diff = await screen.findByTestId("SF-12-diff");
    const row = (name: string) => within(diff).getByRole("rowheader", { name }).closest("tr");
    expect(row("RPO")?.textContent).toContain("USD 146,000.00");
    expect(row("Transaction price")?.textContent).toContain("USD 146,000.00");
    expect(row("Revenue by period")?.textContent).toContain("Sep 2026 USD 12,166.67");
    expect(within(diff).queryByRole("rowheader", { name: "Rpo" })).toBeNull();
    expect(diff.textContent).not.toMatch(/[{}"]/);
    // SCREENS §15.4 region 5 rev 1.18 (R-104 (b)): the row says which periods it lists (04
    // API-S-ImpactSummary: six periods from the effective period).
    expect(
      within(diff).getByText("The first six periods from Sep 2026; later periods are not listed."),
    ).toBeTruthy();
    // Enumeration values read the labels the rest of the product shows.
    const status = within(row("Status") as HTMLElement).getAllByRole("cell");
    expect(status.map((cell) => cell.textContent).slice(-2)).toEqual(["Draft", "Active"]);
    expect(row("Journal lines")?.textContent).toContain("Account role Contract liability");
    expect(diff.textContent).not.toMatch(/DRAFT|ACTIVE|CONTRACT_LIABILITY/);
  });
});

describe("SF-12:request regions 1 and 4, what an approver can open and what is not shown (R-104 (a))", () => {
  const RECORD_ID = "6f7a8b9c-0d1e-4f2a-9b3c-4d5e6f7a8b9c";

  function request(type: Approval["subject"]["type"], display: string, href: string | null) {
    return approval({
      subject: {
        type,
        id: RECORD_ID,
        display,
        href,
        content_sha256: SUBJECT_HASH,
        row_version: 1,
      },
      summary: display,
    });
  }

  async function open(item: Approval): Promise<HTMLElement> {
    serve({ details: { [REQUEST_A]: item }, list: [item] });
    renderRequest(`/approvals/requests/${REQUEST_A}`);
    return screen.findByRole("region", { name: `Request details: ${item.summary}` });
  }

  it.each([
    ["CONTRACT_ACTIVATION", "Activate BG-AVM-0020", `/contracts/${RECORD_ID}`, "Open contract"],
    [
      "JOURNAL_RUN",
      "Approve journal run JR-000001 of AVM-US for Jan 2026",
      `/journals/runs/${RECORD_ID}`,
      "Open journal run",
    ],
    [
      "PRINCIPAL_AGENT_CHANGE",
      "Principal or agent change AVM-PLAT-100",
      `/settings/products/${RECORD_ID}`,
      "Open product",
    ],
    [
      "REGISTRY_VERSION",
      "Policy version POL-013",
      `/policies/accounting/${RECORD_ID}`,
      "Open accounting policy",
    ],
    [
      "EXCEPTION_WAIVER",
      "Waive PROGRESS_OVER_DELIVERY",
      `/data/exceptions/${RECORD_ID}`,
      "Open exception",
    ],
    ["SUPPORT_GRANT", "Support access", "/settings/support-access", "Open support access"],
    // A route of the client that the table of record words does not name.
    ["ROLE_ASSIGNMENT", "Role assignment", `/settings/users/${RECORD_ID}`, "Open record"],
  ] as const)(
    "a %s request (%s) whose subject.href is %s links to it as %s",
    async (type, display, href, name) => {
      const region = await open(request(type, display, href));

      const link = within(region).getByRole("link", { name });
      expect(link.getAttribute("href")).toBe(href);
      expect(link.getAttribute("data-testid")).toBe("SF-12-subject-link");
      // With the link, the notice of a request without a preview points at it.
      expect(within(region).getByText("No preview is stored for this request")).toBeTruthy();
      expect(
        within(region).getByText(
          "Use the link above to open the record and read what you are approving before you decide.",
        ),
      ).toBeTruthy();
    },
  );

  it.each([
    ["no subject.href", null],
    // 04 sends these two paths at rev 1.18; SCREENS §0.4 defines no route for them.
    ["a path the client holds no route for", `/close/periods/${RECORD_ID}`],
    ["a modification path", `/modifications/${RECORD_ID}`],
    ["an address outside the application", "https://example.com/contracts/1"],
  ] as const)("%s renders no link and the pane says what the approver can do", async (_, href) => {
    const region = await open(
      request("JUDGEMENT_RECORD", "Review JDG-000039 (PRINCIPAL_AGENT)", href),
    );

    expect(within(region).queryByTestId("SF-12-subject-link")).toBeNull();
    const notice = within(region).getByTestId("SF-12-banner-no-preview");
    expect(within(notice).getByText("No preview is stored for this request")).toBeTruthy();
    expect(
      within(notice).getByText(
        "This screen does not show what the request changes, and it has no link to the record. Ask Tomás Rivera what it changes, or open the record from its own screen, before you decide.",
      ),
    ).toBeTruthy();
    expect(within(region).queryByText("No impact on revenue or balances.")).toBeNull();
  });

  it("a reader who does not decide the request is told what the pane lacks, not what to do before deciding", async () => {
    const decided = {
      ...request(
        "JOURNAL_RUN",
        "Approve journal run JR-000002 of AVM-US for Aug 2026",
        `/journals/runs/${RECORD_ID}`,
      ),
      status: "APPROVED" as const,
      can_decide: false,
    };
    const region = await open(decided);

    expect(within(region).getByRole("link", { name: "Open journal run" })).toBeTruthy();
    const notice = within(region).getByTestId("SF-12-banner-no-preview");
    expect(notice.textContent).toContain("The link above opens the record this request is about.");
    expect(notice.textContent).not.toContain("before you decide");
    cleanup();

    const unlinked = await open({
      ...request("JUDGEMENT_RECORD", "Review JDG-000198 (COLLECTIBILITY)", null),
      status: "APPROVED" as const,
      can_decide: false,
    });
    const bare = within(unlinked).getByTestId("SF-12-banner-no-preview");
    expect(bare.textContent).toContain(
      "This screen does not show what the request changes, and it has no link to the record.",
    );
    expect(bare.textContent).not.toContain("before you decide");
  });

  it("a stored preview that moves nothing keeps No impact on revenue or balances. and shows no notice", async () => {
    const computed = approval({
      impact_preview: {
        file_id: PREVIEW_FILE,
        sha256: PREVIEW_HASH,
        summary: {
          revenue_by_period_before: [],
          revenue_by_period_after: [],
          balances_before: [],
          balances_after: [],
          journal_lines: [],
          catch_up_total: null,
          criteria_met: null,
        },
      },
    });
    const region = await open(computed);

    expect(await within(region).findByText("No impact on revenue or balances.")).toBeTruthy();
    expect(within(region).queryByTestId("SF-12-banner-no-preview")).toBeNull();
  });

  it("while content of the pane lies beneath the sticky decision form, More below says so and scrolls one view", async () => {
    const item = request(
      "JOURNAL_RUN",
      "Approve journal run JR-000001 of AVM-US for Jan 2026",
      null,
    );
    const region = await open(item);
    const form = await decisionForm();
    // jsdom has no layout: a pane without overflow shows no cue.
    expect(within(form).queryByRole("button", { name: "More below" })).toBeNull();

    // A pane of 600 px that holds 900 px, under a footer of 180 px (the QA case: 1440 × 761).
    const metrics = { scrollHeight: 900, clientHeight: 600 };
    for (const [name, value] of Object.entries(metrics)) {
      Object.defineProperty(region, name, { configurable: true, value });
    }
    Object.defineProperty(region, "scrollTop", { configurable: true, writable: true, value: 0 });
    Object.defineProperty(form, "offsetHeight", { configurable: true, value: 180 });
    fireEvent.scroll(region);
    // DS-A11Y-03: a change row that takes focus scrolls clear of the footer. Before the cue is rendered
    // the padding already holds the row the cue will add: the whole gate caught a row that took focus
    // in that moment, stopped flush with the shorter footer and was covered when the cue appeared.
    expect(region.style.scrollPaddingBlockEnd).toBe("calc(180px + var(--control-h-sm) + 0px)");

    const more = await within(form).findByRole("button", { name: "More below" });
    expect(more.getAttribute("data-testid")).toBe("SF-12-more-below");
    // With the cue rendered the footer's own height includes its row.
    await waitFor(() => {
      expect(region.style.scrollPaddingBlockEnd).toBe("180px");
    });

    fireEvent.click(more);
    // One view less the footer: 600 - 180.
    expect(region.scrollTop).toBe(420);
    await waitFor(() => {
      expect(within(form).queryByRole("button", { name: "More below" })).toBeNull();
    });
  });

  it("More below appears when the request grows beneath the form without any box of the pane changing", async () => {
    // Found by the e2e row at 1440 × 761: the preview's rows arrive after the first paint, the request
    // overflows a box that keeps its height, and neither a scroll nor a resize follows.
    const item = request(
      "JOURNAL_RUN",
      "Approve journal run JR-000001 of AVM-US for Jan 2026",
      null,
    );
    const region = await open(item);
    const form = await decisionForm();
    expect(within(form).queryByRole("button", { name: "More below" })).toBeNull();

    Object.defineProperty(region, "scrollHeight", { configurable: true, value: 824 });
    Object.defineProperty(region, "clientHeight", { configurable: true, value: 570 });
    Object.defineProperty(region, "scrollTop", { configurable: true, writable: true, value: 0 });
    // Content arrives: a node is added inside the pane.
    form.parentElement?.insertBefore(document.createElement("p"), form);

    expect(await within(form).findByRole("button", { name: "More below" })).toBeTruthy();
  });

  it("every route the table of record words names is a route of the router", () => {
    const built = builtPaths(appRoutes(createQueryClient()));
    expect(SUBJECT_ROUTES.map((route) => route.path).filter((path) => !built.has(path))).toEqual(
      [],
    );
  });
});

describe("SF-12:request, the activation of a contract whose criteria were not met (R-61 (f))", () => {
  const CONTRACT_ID = "6f7a8b9c-0d1e-4f2a-9b3c-4d5e6f7a8b9c";
  const RECORD_ID = "1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f";

  function activation(criteria: boolean, currency = "USD"): Approval {
    const money = (amount: string) => ({ amount, currency });
    return approval({
      subject: {
        type: "CONTRACT_ACTIVATION",
        id: CONTRACT_ID,
        display: "Contract activation SF-ORD-10009",
        href: `/contracts/${CONTRACT_ID}/obligations`,
        content_sha256: SUBJECT_HASH,
        row_version: 5,
      },
      summary: "Contract activation SF-ORD-10009",
      impact_preview: {
        file_id: PREVIEW_FILE,
        sha256: PREVIEW_HASH,
        summary: {
          revenue_by_period_before: {},
          revenue_by_period_after: { "FY2026-P09": "2956.20" },
          balances_before: null,
          balances_after: null,
          journal_lines: [],
          catch_up_total: criteria ? money("985.40") : null,
          criteria_met: criteria
            ? [
                {
                  book: "ASC606",
                  effective_date: "2026-09-10",
                  judgement_record_id: RECORD_ID,
                  catch_up_total: money("985.40"),
                },
              ]
            : null,
        },
      },
    });
  }

  const RECORD: Judgement = {
    id: RECORD_ID,
    judgement_no: "JDG-000412",
    topic: "COLLECTIBILITY",
    subject_type: "contract",
    subject_id: CONTRACT_ID,
    contract_id: CONTRACT_ID,
    book: null,
    conclusion: "Collectibility is probable.",
    rationale: "The customer paid the deposit and its credit grade was raised to B.",
    alternatives_considered: null,
    codification_refs: ["606-10-25-1"],
    questionnaire: null,
    status: "REVIEWED",
    approval_request_id: "2d3e4f5a-6b7c-4d8e-9f0a-1b2c3d4e5f6a",
    supersedes_id: null,
    content_sha256: "c".repeat(64),
    created_by: MAYA,
    reviewer: PRIYA,
    reviewed_at: "2026-09-10T16:20:00Z",
    created_at: "2026-09-10T15:02:00Z",
    updated_at: "2026-09-10T16:20:00Z",
  };

  function serveActivation(item: Approval, requests: string[]): void {
    serve({ details: { [REQUEST_A]: item }, list: [item] });
    server.use(
      http.get(apiUrl(`/api/v1/files/${PREVIEW_FILE}/content`), () =>
        HttpResponse.json(ACTIVATION_PREVIEW),
      ),
      // As the API answers: the currencies asked for, and no other.
      http.get(apiUrl("/api/v1/currencies"), ({ request }) =>
        HttpResponse.json({
          items: new URL(request.url).searchParams
            .getAll("code")
            .flatMap((codes) => codes.split(","))
            .map((code) => ({ code, minor_unit: 2 })),
          next_cursor: null,
        }),
      ),
      http.get(apiUrl("/api/v1/periods"), () =>
        HttpResponse.json({ items: [SEP_2026], next_cursor: null }),
      ),
      http.get(apiUrl("/api/v1/judgements"), ({ request }) => {
        requests.push(new URL(request.url).search);
        return HttpResponse.json({ items: [RECORD], next_cursor: null });
      }),
    );
  }

  it("names each book that moves with its date, its reviewed Step 1 record and its catch-up", async () => {
    const requests: string[] = [];
    serveActivation(activation(true), requests);
    renderRequest(`/approvals/requests/${REQUEST_A}`);

    const region = await screen.findByRole("region", { name: "Criteria met" });
    expect(
      within(region).getByText(
        "Approving records that the contract criteria are met in the books below and activates the contract. Revenue for performance up to each date is recognised as a catch-up.",
      ),
    ).toBeTruthy();
    const table = within(region).getByRole("table", { name: "Books that move" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((cell) => cell.textContent),
    ).toEqual(["Book", "Criteria met on", "Step 1 review", "Catch-up"]);
    const row = within(table).getByRole("rowheader", { name: "ASC 606" }).closest("tr");
    await waitFor(() => {
      expect(row?.textContent).toContain("JDG-000412");
    });
    expect(
      within(row as HTMLElement)
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    ).toEqual([
      "10 Sep 2026",
      "JDG-000412 · Reviewed by Priya Raman, 10 Sep 2026 16:20 UTC",
      `USD${NBSP}985.40`,
    ]);
    // The books are parallel ledgers: no figure adds their catch-ups, and the primary book's is not
    // repeated under the table (04 §16.10 `impact_preview.summary.catch_up_total`).
    expect(within(region).queryByText(/total/i)).toBeNull();
    // One read, of the records of this contract.
    expect(requests.map((search) => new URLSearchParams(search).get("subject_id"))).toEqual([
      CONTRACT_ID,
    ]);
  });

  it("the catch-up is shown in a currency that nothing on the page had formatted before", async () => {
    // Found on the real stack: the region rendered before the preview document registered the
    // currency, and showed a dash for a catch-up the API stated (DS-FMT-03).
    serveActivation(activation(true, "CHF"), []);
    renderRequest(`/approvals/requests/${REQUEST_A}`);

    const region = await screen.findByRole("region", { name: "Criteria met" });
    const row = within(region).getByRole("rowheader", { name: "ASC 606" }).closest("tr");
    expect(
      within(row as HTMLElement)
        .getAllByRole("cell")
        .at(-1)?.textContent,
    ).toBe(`CHF${NBSP}985.40`);
  });

  it("a record that is not reviewed is named with its status in the words of the workbench, also a status the catalogue did not name", async () => {
    // SCREENS §0.8 (rev 1.66; 04 E-57 rev 1.242): the line read the status through a catalogue key
    // without a fallback — `t()` throws on a key the catalogue lacks — and E-57 gained `VOIDED`. A
    // record sent for review reads "Waiting for review".
    for (const [status, word] of [
      ["SUBMITTED", "Waiting for review"],
      ["REJECTED", "Rejected"],
      ["VOIDED", "Void"],
      ["ESCALATED", "ESCALATED"],
    ] as const) {
      serveActivation(activation(true), []);
      server.use(
        http.get(apiUrl("/api/v1/judgements"), () =>
          HttpResponse.json({
            items: [{ ...RECORD, status, reviewer: null, reviewed_at: null }],
            next_cursor: null,
          }),
        ),
      );
      renderRequest(`/approvals/requests/${REQUEST_A}`);

      const region = await screen.findByRole("region", { name: "Criteria met" });
      const row = within(region).getByRole("rowheader", { name: "ASC 606" }).closest("tr");
      await waitFor(() => {
        expect(row?.textContent).toContain("JDG-000412");
      });
      expect(within(row as HTMLElement).getAllByRole("cell")[1]?.textContent).toBe(
        `Record JDG-000412 · ${word}`,
      );
      cleanup();
      server.resetHandlers();
    }
  });

  it("an activation that moves no book out of NOT_A_CONTRACT shows no such region and reads no record", async () => {
    const requests: string[] = [];
    serveActivation(activation(false), requests);
    renderRequest(`/approvals/requests/${REQUEST_A}`);

    await screen.findByTestId("SF-12-diff");
    expect(screen.queryByRole("region", { name: "Criteria met" })).toBeNull();
    expect(requests).toEqual([]);
  });
});

// SCREENS §15.4 "Content withheld" (rev 1.32, restated in rev 1.48; 04 §16.10 API-S-Approval
// `content_withheld`; item W-12d): a request that names legal entities the reader does not cover is
// shown as its header and one banner. The fixtures carry an attachment the API would not send, so
// that what the pane leaves out is seen to be left out by the pane. A decision's comment is another
// matter: the API decides who reads which, and the pane renders the one it is sent.
describe("SF-12:request, a request whose content is withheld", () => {
  const WITHHELD_TITLE = "You see part of this request";
  const WITHHELD_MESSAGE =
    "This request names legal entities outside your access. Its summary, amount, impact preview, attachments and the approvers' comments are shown to people whose access covers every entity it names. An approver's comment on a rejection is also shown to the person who submitted the request.";
  const REJECTION = "Range too wide for the observed sales.";
  /** The steps as the API answers them with a withheld request: no decision carries its comment. */
  const withoutComments = (steps: Approval["steps"]): Approval["steps"] =>
    steps.map((step) => ({
      ...step,
      decisions: step.decisions.map((decision) => ({ ...decision, comment: null })),
    }));
  const withheld = (overrides: Partial<Approval> = {}) =>
    approval({
      summary: "SSP book version APR-000231",
      can_decide: false,
      content_withheld: true,
      steps: withoutComments(approval().steps),
      attachments: [
        {
          file_id: "6f7a8b9c-0d1e-4f2a-8b3c-4d5e6f7a8b9c",
          original_filename: "ssp-study-2026-h2.pdf",
        } as Approval["attachments"][number],
      ],
      ...overrides,
    });

  it("shows the header with the routing steps, and one banner in place of the content", async () => {
    const request = withheld();
    serve({ details: { [REQUEST_A]: request }, list: [request] });
    renderRequest(`/approvals/requests/${REQUEST_A}`);

    const banner = await screen.findByTestId("SF-12-banner-content-withheld");
    expect(within(banner).getByRole("heading", { level: 3, name: WITHHELD_TITLE })).toBeTruthy();
    expect(within(banner).getByText(WITHHELD_MESSAGE)).toBeTruthy();
    // Region 1 as for any request: number, type, summary as sent, who asked, how far it has come.
    const pane = screen.getByRole("region", {
      name: "Request details: SSP book version APR-000231",
    });
    expect(within(pane).getByText("APR-000231")).toBeTruthy();
    expect(within(pane).getByText("SSP book version")).toBeTruthy();
    expect(within(pane).getByText("SSP book version APR-000231")).toBeTruthy();
    const routing = within(pane).getByRole("list", { name: "Routing" });
    expect(within(routing).getByText("SSP approval · 1 of 1 recorded")).toBeTruthy();
    expect(within(routing).getByText("Priya Raman")).toBeTruthy();
    // What stands in place of regions 3 to 6: no notice about a preview, no attachments.
    expect(screen.queryByTestId("SF-12-banner-no-preview")).toBeNull();
    expect(within(pane).queryByText("ssp-study-2026-h2.pdf")).toBeNull();
    expect(within(pane).queryByText("Attachments")).toBeNull();
    // Nothing is decided here, and the pane does not say the reader lacks the right: the banner says why.
    expect(screen.queryByRole("form", { name: "Decision" })).toBeNull();
    expect(screen.queryByTestId("SF-12-banner-sod")).toBeNull();
    expect(screen.queryByRole("button", { name: "Withdraw request" })).toBeNull();
  });

  it("the preparer of a withheld request reads that she submitted it and keeps Withdraw request", async () => {
    const own = withheld({ preparer: MAYA });
    serve({ details: { [REQUEST_A]: own }, list: [own] });
    renderRequest(`/approvals/requests/${REQUEST_A}`);

    expect(await screen.findByTestId("SF-12-banner-content-withheld")).toBeTruthy();
    expect(
      within(screen.getByTestId("SF-12-banner-sod")).getByText(
        "You submitted this request. Another approver must review it.",
      ),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Withdraw request" })).toBeTruthy();
    expect(screen.queryByRole("form", { name: "Decision" })).toBeNull();
  });

  it("a comment the API sends with a withheld request is rendered: the preparer reads why her request was rejected", async () => {
    const [first] = withoutComments(approval().steps);
    if (first === undefined) {
      throw new Error("the fixture has no step");
    }
    const rejected = withheld({
      preparer: MAYA,
      status: "REJECTED",
      decided_at: "2026-09-12T15:10:00Z",
      current_step_no: 1,
      steps: [
        {
          ...first,
          status: "REJECTED",
          decisions: first.decisions.map((decision) => ({
            ...decision,
            decision: "REJECT" as const,
            comment: REJECTION,
          })),
        },
      ],
    });
    serve({ details: { [REQUEST_A]: rejected }, list: [rejected] });
    renderRequest(`/approvals/requests/${REQUEST_A}`);

    expect(await screen.findByTestId("SF-12-banner-content-withheld")).toBeTruthy();
    const routing = screen.getByRole("list", { name: "Routing" });
    expect(within(routing).getByText("Priya Raman")).toBeTruthy();
    expect(within(routing).getByText(REJECTION)).toBeTruthy();
    // A request that was decided is neither decided nor withdrawn here.
    expect(screen.queryByRole("form", { name: "Decision" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Withdraw request" })).toBeNull();
    expect(screen.queryByText("ssp-study-2026-h2.pdf")).toBeNull();
  });

  it("a request that is not withheld keeps its comment, its notice and its attachments", async () => {
    const whole = withheld({ content_withheld: false, steps: approval().steps });
    serve({ details: { [REQUEST_A]: whole }, list: [whole] });
    renderRequest(`/approvals/requests/${REQUEST_A}`);

    expect(await screen.findByText("Range supported by the study.")).toBeTruthy();
    expect(screen.getByTestId("SF-12-banner-no-preview")).toBeTruthy();
    expect(screen.getByRole("link", { name: "ssp-study-2026-h2.pdf" })).toBeTruthy();
    expect(
      within(screen.getByTestId("SF-12-banner-sod")).getByText(
        "You do not have approval rights for this request type.",
      ),
    ).toBeTruthy();
    expect(screen.queryByTestId("SF-12-banner-content-withheld")).toBeNull();
  });
});

// SCREENS §15.4 region 3 (04 API-S-Approval `comment`, rev 1.252; item APR-REQUEST-REASON-1): the
// comment a request was submitted with stands in the pane as a quoted block under "Justification".
// The API did not answer it before, so an approver decided without it.
describe("SF-12:request, the justification of a request", () => {
  const JUSTIFICATION = "Prices of the H2 list replace the range of the study.";

  it("shows the comment the request was submitted with, between the header and the impact", async () => {
    const request = approval({ comment: JUSTIFICATION });
    serve({ details: { [REQUEST_A]: request }, list: [request] });
    renderRequest(`/approvals/requests/${REQUEST_A}`);

    const region = await screen.findByRole("region", { name: "Justification" });
    expect(region.getAttribute("data-testid")).toBe("SF-12-justification");
    expect(within(region).getByRole("heading", { level: 3, name: "Justification" })).toBeTruthy();
    expect(within(region).getByText(JUSTIFICATION).tagName).toBe("BLOCKQUOTE");
    // Region 3 stands before the notice of region 4.
    const notice = screen.getByTestId("SF-12-banner-no-preview");
    expect(region.compareDocumentPosition(notice) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("a request submitted without a comment has no such region", async () => {
    const request = approval();
    serve({ details: { [REQUEST_A]: request }, list: [request] });
    renderRequest(`/approvals/requests/${REQUEST_A}`);

    await screen.findByTestId("SF-12-banner-no-preview");
    expect(screen.queryByRole("region", { name: "Justification" })).toBeNull();
  });

  // The supervisor's ruling of 2026-10-02 06:30: the API's bodies admit a comment of "" or of spaces
  // (`comment: str | None`, no minimum length), and such a comment says nothing. The pane treats it as
  // none: no heading over an empty block.
  it("a comment that is blank after trimming is treated as none", async () => {
    for (const blank of ["", "  \n "]) {
      const request = approval({ comment: blank });
      serve({ details: { [REQUEST_A]: request }, list: [request] });
      renderRequest(`/approvals/requests/${REQUEST_A}`);

      await screen.findByTestId("SF-12-banner-no-preview");
      expect(screen.queryByRole("region", { name: "Justification" })).toBeNull();
      expect(screen.queryByTestId("SF-12-justification")).toBeNull();
      cleanup();
    }
  });

  it("the preparer of a withheld request reads the comment she wrote, above the banner", async () => {
    const own = approval({
      summary: "SSP book version APR-000231",
      preparer: MAYA,
      can_decide: false,
      content_withheld: true,
      comment: JUSTIFICATION,
    });
    serve({ details: { [REQUEST_A]: own }, list: [own] });
    renderRequest(`/approvals/requests/${REQUEST_A}`);

    const banner = await screen.findByTestId("SF-12-banner-content-withheld");
    const region = screen.getByRole("region", { name: "Justification" });
    expect(within(region).getByText(JUSTIFICATION)).toBeTruthy();
    expect(region.compareDocumentPosition(banner) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

function usd(amount: string): { readonly amount: string; readonly currency: string } {
  return { amount, currency: "USD" };
}

/** The Avenmoor calendar row of FY2026-P09, a Gregorian month (DS-FMT-19 "Sep 2026"). */
const SEP_2026: Pick<Period, "period"> = {
  period: {
    id: "5b6c7d8e-9f0a-4b1c-8d2e-3f4a5b6c7d8e",
    name: "September 2026",
    fiscal_year: 2026,
    period_no: 9,
    quarter_no: 3,
    period_key: "FY2026-P09",
    start_date: "2026-09-01",
    end_date: "2026-09-30",
  },
};

/** A CONTRACT_ACTIVATION preview shaped like the stored document (contracts/activation.py `_preview`). */
const ACTIVATION_PREVIEW: PreviewDocument = {
  before: {
    status: "DRAFT",
    transaction_price: usd("0.00"),
    rpo: usd("0.00"),
    revenue_by_period: [
      { period_key: "FY2026-P09", amount: usd("0.00") },
      { period_key: "FY2026-P10", amount: usd("0.00") },
    ],
    balances: [],
  },
  after: {
    status: "ACTIVE",
    transaction_price: usd("146000.00"),
    rpo: usd("146000.00"),
    revenue_by_period: [
      { period_key: "FY2026-P09", amount: usd("12166.67") },
      { period_key: "FY2026-P10", amount: usd("12166.67") },
    ],
    balances: [],
    journal_lines: [
      {
        gl_account: {
          id: "3e4f5a6b-7c8d-4e9f-8a0b-1c2d3e4f5a6b",
          code: "2300",
          name: "Contract liability",
        },
        account_role: "CONTRACT_LIABILITY",
        debit: usd("0.00"),
        credit: usd("12166.67"),
      },
    ],
  },
};
