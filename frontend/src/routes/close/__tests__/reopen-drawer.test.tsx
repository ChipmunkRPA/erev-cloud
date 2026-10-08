// @vitest-environment jsdom
// SF-05 "Request reopen" (SCREENS_B §1.3; 04 API-R-36 `POST /periods/{id}/request-reopen`, API-R-12
// `POST /files`, `POST /attachments`): one press sends the request and then its attachments.
// DG-FE-05 rev 1.156 (item W-23): when an attachment gets no answer, the second press sends the request
// again under its key — the API replays the request it created instead of refusing a second one for a
// period that is already waiting — and saves the attachment.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Period } from "../../../lib/api/queries/tenant";
import { installMemoryStorage, renderWithApp, signedInMe } from "../../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import { REFUSAL_REFERENCE, REFUSAL_TITLE, refusedWith } from "../../../test/refusals";
import { ReopenDrawer } from "../reopen-drawer";
import { ReopenEvidence } from "../reopen-evidence";

installMswServer();
installMemoryStorage();

const JUDGEMENT_ID = "afe16a52-348b-40ca-b023-000000000001";
beforeEach(() => {
  server.use(
    http.get(apiUrl("/api/v1/judgements"), ({ request }) => {
      const query = new URL(request.url).searchParams;
      expect(query.get("topic")).toBe("ESTIMATE_VS_ERROR");
      expect(query.get("status")).toBe("REVIEWED");
      expect(query.get("entity_id")).toBe(PERIOD.entity.id);
      expect(query.get("book")).toBe("ASC606");
      return HttpResponse.json({
        items: [
          {
            id: JUDGEMENT_ID,
            judgement_no: "JDG-000042",
            conclusion: "Correct the duplicate August usage.",
            rationale: "Supported by the source file.",
            contract_id: "contract-42",
            reviewer: { display_name: "Marcus" },
          },
        ],
        next_cursor: null,
      });
    }),
  );
});

afterEach(() => {
  cleanup();
});

const STATE_ID = "7c1d2e3f-4a5b-4c6d-8e7f-000000000909";
const REQUEST_ID = "8d4f2e1c-3b5a-4c7d-9e8f-0a1b2c3d4e5f";
const FILE_ID = "9e5a3f2d-4c6b-4d8e-8f9a-1b2c3d4e5f6a";
const ATTACHMENT_ID = "af6b4a3e-5d7c-4e9f-9a0b-2c3d4e5f6a7b";
const SHA = "a".repeat(64);

const PERIOD: Period = {
  id: STATE_ID,
  entity: {
    id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000001",
    code: "AVM-US",
    name: "Avenmoor Inc. (Demo)",
  },
  book: "ASC606",
  period: {
    id: "1c2d3e4f-5a6b-4c7d-8e9f-000000000009",
    period_key: "FY2026-P08",
    name: "Aug 2026",
    fiscal_year: 2026,
    period_no: 8,
    quarter_no: 3,
    start_date: "2026-08-01",
    end_date: "2026-08-31",
  },
  state: "closed",
  state_changed_at: "2026-09-05T00:00:00Z",
  is_first_open: false,
  current_lock: null,
  blockers: {
    approvals_pending: 0,
    batches_unacknowledged: 0,
    batches_unexported: 0,
    exceptions_open: 0,
    groups_dirty: 0,
    holds_open: 0,
    interface_failures: 0,
    jobs_failed: 0,
    judgements_unreviewed: 0,
    manual_adjustments_pending: 0,
    reconciliations_unsigned: 0,
    unmapped_products: 0,
  },
  close_run: null,
  row_version: 5,
};

interface Sent {
  readonly path: string;
  readonly key: string | null;
  readonly ifMatch: string | null;
}

describe("SF-05 Request reopen", () => {
  it("an attachment gets no answer: the second press sends the request under its old key and saves the attachment", async () => {
    const sent: Sent[] = [];
    const note = (request: Request) => {
      sent.push({
        path: new URL(request.url).pathname,
        key: request.headers.get("Idempotency-Key"),
        ifMatch: request.headers.get("If-Match"),
      });
    };
    let lose = true;
    server.use(
      http.get(apiUrl("/api/v1/me/notifications"), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.post(apiUrl(`/api/v1/periods/${STATE_ID}/request-reopen`), async ({ request }) => {
        expect(await request.json()).toMatchObject({ judgement_record_id: JUDGEMENT_ID });
        note(request);
        // What the API answers to the first send, and replays to the second under the same key.
        return HttpResponse.json({ approval_request_id: REQUEST_ID });
      }),
      http.post(apiUrl("/api/v1/files"), ({ request }) => {
        note(request);
        // Identical content of the same purpose answers with the stored file (API-R-12).
        return HttpResponse.json(
          {
            id: FILE_ID,
            purpose: "ATTACHMENT",
            media_type: "application/pdf",
            original_filename: "memo.pdf",
            size_bytes: 4,
            sha256: SHA,
            legal_hold: false,
            retention_until: null,
            shredded_at: null,
            shred_completed_at: null,
            created_at: "2026-09-13T09:00:00Z",
            created_by: null,
            created_by_kind: "USER",
          },
          { status: 201 },
        );
      }),
      http.post(apiUrl("/api/v1/attachments"), ({ request }) => {
        note(request);
        if (lose) {
          lose = false;
          return HttpResponse.error();
        }
        return HttpResponse.json(
          {
            id: ATTACHMENT_ID,
            file_object_id: FILE_ID,
            subject_type: "approval_request",
            subject_id: REQUEST_ID,
            description: null,
            original_filename: "memo.pdf",
            media_type: "application/pdf",
            size_bytes: 4,
            sha256: SHA,
            created_at: "2026-09-13T09:00:00Z",
            created_by: null,
            created_by_kind: "USER",
            voided_at: null,
            voided_by: null,
            voided_by_kind: null,
            void_reason: null,
          },
          { status: 201 },
        );
      }),
      // The partial notice names the request by its number when it can read it.
      http.get(apiUrl(`/api/v1/approvals/${REQUEST_ID}`), () =>
        problemResponse("not-found", 404, "Not found"),
      ),
      http.get(apiUrl("/api/v1/periods"), () =>
        HttpResponse.json({ items: [PERIOD], next_cursor: null }),
      ),
    );
    const onClose = vi.fn();
    renderWithApp(
      <ReopenDrawer
        period={PERIOD}
        periodLabel="Aug 2026"
        bookLabel="ASC 606"
        canViewRequest={false}
        canAttach
        canJudge={false}
        judgementRegisterHref={null}
        onClose={onClose}
      />,
      {
        entry: "/close/AVM-US/ASC606/FY2026-P08",
        me: signedInMe({ permissions: ["contract.read", "period.reopen_request"] }),
      },
    );

    await screen.findByRole("dialog", { name: "Request reopen of Aug 2026" });
    fireEvent.click(screen.getByRole("combobox", { name: /^Reason/ }));
    fireEvent.mouseDown(screen.getByRole("option", { name: "Error correction" }));
    await screen.findByRole("combobox", { name: /^Reviewed judgement/ });
    fireEvent.click(screen.getByRole("combobox", { name: /^Reviewed judgement/ }));
    fireEvent.mouseDown(await screen.findByRole("option", { name: "JDG-000042" }));
    expect(screen.getByText("Reviewed by Marcus")).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: /^Comment/ }), {
      target: { value: "The August usage file was loaded twice." },
    });
    const memo = new File(["memo"], "memo.pdf", { type: "application/pdf", lastModified: 1 });
    fireEvent.change(screen.getByLabelText(/^Attachments/), { target: { files: [memo] } });
    const press = screen.getByRole("button", { name: "Submit reopen request" });
    fireEvent.click(press);

    // First press: the request exists, the attachment's answer is lost. The drawer says what is
    // missing and stays open.
    expect(
      await screen.findByText(
        `Reopen request ${REQUEST_ID} was created, but 1 attachment was not saved. Add it from the request in Approvals.`,
      ),
    ).toBeTruthy();
    expect(onClose).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(press.getAttribute("aria-busy")).not.toBe("true");
    });

    fireEvent.click(press);
    expect(
      await screen.findByText("Reopen requested for AVM-US Aug 2026. Two approvers must approve."),
    ).toBeTruthy();
    expect(onClose).toHaveBeenCalledTimes(1);
    const request = `/api/v1/periods/${STATE_ID}/request-reopen`;
    expect(sent.map((item) => item.path)).toEqual([
      request,
      "/api/v1/files",
      "/api/v1/attachments",
      request,
      "/api/v1/files",
      "/api/v1/attachments",
    ]);
    // Second press, step 1: the request under its old key. A new key would be a second request for a
    // period that already waits for its approval.
    expect(sent[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
    expect(sent[0]?.ifMatch).toBe('"r5"');
    expect(sent[3]?.key).toBe(sent[0]?.key);
    // The attachment that got no answer goes out again under its old key: if the API did save it,
    // it replays that one.
    expect(sent[5]?.key).toBe(sent[2]?.key);
    expect(new Set([sent[0]?.key, sent[1]?.key, sent[2]?.key]).size).toBe(3);
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): the drawer shows no message of the
  // API at a field, so the banner says every sentence of a refusal; one that names a member was shown
  // nowhere.
  it("a refused request says every sentence of the refusal", async () => {
    const first = "A later period of this entity is closed. Reopen it first.";
    const second = "Say which entries are corrected.";
    server.use(
      http.get(apiUrl("/api/v1/me/notifications"), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.post(apiUrl(`/api/v1/periods/${STATE_ID}/request-reopen`), () =>
        refusedWith({ reason_code: first, comment: second }),
      ),
      http.get(apiUrl("/api/v1/periods"), () =>
        HttpResponse.json({ items: [PERIOD], next_cursor: null }),
      ),
    );
    renderWithApp(
      <ReopenDrawer
        period={PERIOD}
        periodLabel="Aug 2026"
        bookLabel="ASC 606"
        canViewRequest={false}
        canAttach={false}
        canJudge={false}
        judgementRegisterHref={null}
        onClose={() => undefined}
      />,
      {
        entry: "/close/AVM-US/ASC606/FY2026-P08",
        me: signedInMe({ permissions: ["contract.read", "period.reopen_request"] }),
      },
    );
    const drawer = await screen.findByRole("dialog", { name: "Request reopen of Aug 2026" });
    fireEvent.click(screen.getByRole("combobox", { name: /^Reason/ }));
    fireEvent.mouseDown(screen.getByRole("option", { name: "Error correction" }));
    await screen.findByRole("combobox", { name: /^Reviewed judgement/ });
    fireEvent.click(screen.getByRole("combobox", { name: /^Reviewed judgement/ }));
    fireEvent.mouseDown(await screen.findByRole("option", { name: "JDG-000042" }));
    expect(screen.getByText("Reviewed by Marcus")).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: /^Comment/ }), {
      target: { value: "The August usage file was loaded twice." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit reopen request" }));

    const banner = await within(drawer).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + first + second + REFUSAL_REFERENCE);
  });
});

it("requires reviewed evidence before sending an error-correction reopen", async () => {
  const sent = vi.fn();
  server.use(
    http.post(apiUrl(`/api/v1/periods/${STATE_ID}/request-reopen`), () => {
      sent();
      return HttpResponse.json({ approval_request_id: REQUEST_ID });
    }),
  );
  renderWithApp(
    <ReopenDrawer
      period={PERIOD}
      periodLabel="Aug 2026"
      bookLabel="ASC 606"
      canViewRequest={false}
      canAttach={false}
      canJudge={false}
      judgementRegisterHref={null}
      onClose={() => undefined}
    />,
    {
      entry: "/close/AVM-US/ASC606/FY2026-P08",
      me: signedInMe({ permissions: ["contract.read", "period.reopen_request"] }),
    },
  );
  fireEvent.click(await screen.findByRole("combobox", { name: /^Reason/ }));
  fireEvent.mouseDown(screen.getByRole("option", { name: "Error correction" }));
  fireEvent.change(screen.getByRole("textbox", { name: /^Comment/ }), {
    target: { value: "Correct the duplicate August usage." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Submit reopen request" }));
  expect(
    await screen.findByText("Select the reviewed judgement supporting this error correction."),
  ).toBeTruthy();
  expect(sent).not.toHaveBeenCalled();
});

it("loads later pages of reviewed evidence without dropping entity and book filters", async () => {
  const cursors: (string | null)[] = [];
  server.use(
    http.get(apiUrl("/api/v1/judgements"), ({ request }) => {
      const query = new URL(request.url).searchParams;
      const cursor = query.get("cursor");
      cursors.push(cursor);
      expect(query.get("entity_id")).toBe(PERIOD.entity.id);
      expect(query.get("book")).toBe("ASC606");
      expect(query.get("status")).toBe("REVIEWED");
      expect(query.get("topic")).toBe("ESTIMATE_VS_ERROR");
      return HttpResponse.json(
        cursor === null
          ? { items: [], next_cursor: "second-page" }
          : {
              items: [
                {
                  id: JUDGEMENT_ID,
                  judgement_no: "JDG-000043",
                  conclusion: "Second page evidence.",
                  rationale: "The later page remains selectable.",
                  contract_id: null,
                  reviewer: { display_name: "Elena" },
                },
              ],
              next_cursor: null,
            },
      );
    }),
  );
  renderWithApp(
    <ReopenEvidence
      entityId={PERIOD.entity.id}
      book="ASC606"
      value={JUDGEMENT_ID}
      onChange={() => undefined}
      error={null}
    />,
    {
      entry: "/close/AVM-US/ASC606/FY2026-P08",
      me: signedInMe({ permissions: ["contract.read"] }),
    },
  );
  expect(await screen.findByText("Second page evidence.")).toBeTruthy();
  expect(screen.getByText("Reviewed by Elena")).toBeTruthy();
  expect(cursors).toEqual([null, "second-page"]);
});
