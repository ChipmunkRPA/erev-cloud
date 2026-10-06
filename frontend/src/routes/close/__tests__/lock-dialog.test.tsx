// @vitest-environment jsdom
// SF-05 "Lock period" (SCREENS_B §1.1 Lock period, SB-R-05; PRD ERR-52; supervisor ruling R-97 (6), item
// W-21): a lock answered 409 lock-conflict says "Resubmit the request", and the second press must be able
// to decide it. The API keeps the 409 as the first response of its Idempotency-Key (dev-guide
// DG-KRN-IDEM-03), so the second press carries a new key for the same body.
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import type { PeriodApproval } from "../../../lib/api/queries/periods";
import { renderWithApp } from "../../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import {
  RECORD_CHANGED,
  REFUSAL_REFERENCE,
  REFUSAL_TITLE,
  refusedWith,
} from "../../../test/refusals";
import { LockPeriodDialog } from "../lock-drawer";

installMswServer();

afterEach(() => {
  cleanup();
});

const REQUEST_ID = "8f0c5a1e-3b2d-4c6e-9a7f-1d2e3f4a5b6c";
const MARCUS = {
  id: "9e8d7c6b-5a4f-4e3d-8c2b-1a0f9e8d7c6b",
  display_name: "Marcus Webb",
  kind: "USER",
} as const;

const REQUEST: PeriodApproval = {
  id: REQUEST_ID,
  request_no: "APR-000451",
  subject: {
    type: "PERIOD_LOCK",
    id: "7d1e2f3a-4b5c-4d6e-8f7a-9b0c1d2e3f4a",
    display: "Lock Sep 2026 for AVM-US",
    href: null,
    content_sha256: "a".repeat(64),
    row_version: 2,
  },
  summary: "Lock Sep 2026 for AVM-US",
  status: "PENDING",
  entity: null,
  entities: [],
  entity_count: 0,
  all_entities: false,
  amount: null,
  flags: [],
  routing: { rule_set_version_id: null, rule_key: null },
  preparer: MARCUS,
  submitted_at: "2026-10-02T14:05:00Z",
  decided_at: null,
  voided_at: null,
  void_reason: null,
  current_step_no: 1,
  steps: [],
  impact_preview: null,
  attachments: [],
  can_decide: true,
  content_withheld: false,
  reason_code: null,
  comment: null,
};

describe("SF-05 Lock period after a lock-conflict", () => {
  it("the second press sends the same body under a new Idempotency-Key and locks the period", async () => {
    const sent: { readonly key: string | null; readonly body: unknown }[] = [];
    server.use(
      http.post(apiUrl(`/api/v1/approvals/${REQUEST_ID}/approve`), async ({ request }) => {
        sent.push({ key: request.headers.get("Idempotency-Key"), body: await request.json() });
        return sent.length === 1
          ? problemResponse("lock-conflict", 409, "Another change was in progress", {
              detail:
                "Another change to the same records was being saved at the same moment, so nothing was saved. Resubmit the request.",
            })
          : HttpResponse.json({ ...REQUEST, status: "APPROVED", can_decide: false });
      }),
      http.get(apiUrl("/api/v1/me/notifications"), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
    let closed = 0;
    renderWithApp(
      <LockPeriodDialog
        request={REQUEST}
        checklist={[]}
        entityCode="AVM-US"
        periodLabel="Sep 2026"
        nextPeriodLabel="Oct 2026"
        onClose={() => {
          closed += 1;
        }}
      />,
    );

    const dialog = await screen.findByRole("alertdialog", { name: "Lock Sep 2026 for AVM-US?" });
    fireEvent.change(screen.getByLabelText("Reason (required)"), {
      target: { value: "September 2026 close complete" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Lock period" }));
    expect(await screen.findByText("Another change was in progress")).toBeTruthy();
    expect(dialog.textContent).toContain("Resubmit the request.");

    fireEvent.click(screen.getByRole("button", { name: "Lock period" }));
    expect(await screen.findByText("AVM-US Sep 2026 locked.")).toBeTruthy();

    expect(closed).toBe(1);
    expect(sent).toHaveLength(2);
    expect(sent[1]?.body).toEqual(sent[0]?.body);
    expect(sent[0]?.body).toEqual({
      subject_content_sha256: "a".repeat(64),
      comment: "September 2026 close complete",
    });
    expect(sent[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
    expect(sent[1]?.key).toMatch(/^[0-9a-f-]{36}$/);
    expect(sent[1]?.key).not.toBe(sent[0]?.key);
  });
});

// docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): the dialog shows no message of the
// API at its reason, so the banner says every sentence of a refusal that is neither a stale request nor
// a lock conflict; one that names a member was shown nowhere. After a 412 it says that the record
// changed, in place of the problem (SCREENS SCR-ST-09), where the dialog showed both.
describe("SF-05 Lock period under a refused decision", () => {
  it("says every sentence of the refusal, and after a 412 that the record changed", async () => {
    const sentence = "The certification of this period was withdrawn.";
    let status = 422;
    server.use(
      http.post(apiUrl(`/api/v1/approvals/${REQUEST_ID}/approve`), () =>
        refusedWith({ subject_content_sha256: sentence }, { status }),
      ),
      http.get(apiUrl("/api/v1/me/notifications"), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
    renderWithApp(
      <LockPeriodDialog
        request={REQUEST}
        checklist={[]}
        entityCode="AVM-US"
        periodLabel="Sep 2026"
        nextPeriodLabel="Oct 2026"
        onClose={() => undefined}
      />,
    );
    const dialog = await screen.findByRole("alertdialog", { name: "Lock Sep 2026 for AVM-US?" });
    fireEvent.change(screen.getByLabelText("Reason (required)"), {
      target: { value: "September 2026 close complete" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Lock period" }));
    expect((await within(dialog).findByRole("alert")).textContent).toBe(
      REFUSAL_TITLE + sentence + REFUSAL_REFERENCE,
    );

    status = 412;
    fireEvent.click(screen.getByRole("button", { name: "Lock period" }));
    expect(await within(dialog).findByRole("heading", { name: RECORD_CHANGED })).toBeTruthy();
    expect(within(dialog).queryByRole("heading", { name: REFUSAL_TITLE })).toBeNull();
  });
});
