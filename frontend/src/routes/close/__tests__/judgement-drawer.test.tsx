// @vitest-environment jsdom
// SF-05 "Record estimate-versus-error judgement" (SCREENS_B §1.1; 04 T-CON-19 `POST /judgements` and
// `/submit`): one press creates the record and submits it for review.
// DG-FE-05 rev 1.156 (item W-23): when the submission gets no answer, the drawer does not know the
// record it created, and the second press sends the create again — under the key it had, so that the
// API replays the record instead of creating a second one — and then the submission under its key.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Period } from "../../../lib/api/queries/tenant";
import { installMemoryStorage, renderWithApp, signedInMe } from "../../../test/app";
import { apiUrl, installMswServer, server } from "../../../test/msw";
import { REFUSAL_REFERENCE, REFUSAL_TITLE, refusedWith } from "../../../test/refusals";
import { JudgementDrawer } from "../judgement-drawer";

installMswServer();
installMemoryStorage();

afterEach(() => {
  cleanup();
});

const CONTRACT_ID = "5e6f7a8b-9c0d-4e1f-8a2b-3c4d5e6f7a8b";
const JUDGEMENT_ID = "6f7a8b9c-0d1e-4f2a-9b3c-4d5e6f7a8b9c";

const PERIOD: Period = {
  id: "7c1d2e3f-4a5b-4c6d-8e7f-000000000909",
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
}

describe("SF-05 Record estimate-versus-error judgement", () => {
  it("the submission gets no answer: the second press sends the record and its submission under the keys they had", async () => {
    const sent: Sent[] = [];
    const note = (request: Request) => {
      sent.push({
        path: new URL(request.url).pathname.replace("/api/v1", ""),
        key: request.headers.get("Idempotency-Key"),
      });
    };
    let lose = true;
    server.use(
      http.get(apiUrl("/api/v1/me/notifications"), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get(apiUrl("/api/v1/contracts"), () =>
        HttpResponse.json({
          items: [
            {
              id: CONTRACT_ID,
              external_id: "PRJ-CB-2026-01",
              customer: { id: "c0", code: "CASTELLAN", name: "Castellan Builders" },
            },
          ],
          next_cursor: null,
        }),
      ),
      http.post(apiUrl("/api/v1/judgements"), ({ request }) => {
        note(request);
        // What the API answers to the first send, and replays to the second under the same key.
        return HttpResponse.json({ id: JUDGEMENT_ID, judgement_no: "JDG-000041" }, { status: 201 });
      }),
      http.post(apiUrl(`/api/v1/judgements/${JUDGEMENT_ID}/submit`), ({ request }) => {
        note(request);
        if (lose) {
          lose = false;
          return HttpResponse.error();
        }
        return HttpResponse.json({ id: JUDGEMENT_ID, judgement_no: "JDG-000041" });
      }),
    );
    const onClose = vi.fn();
    renderWithApp(
      <JudgementDrawer
        period={PERIOD}
        periodLabel="Aug 2026"
        bookLabel="ASC 606"
        onOpenRegister={null}
        onClose={onClose}
      />,
      {
        entry: "/close/AVM-US/ASC606/FY2026-P08",
        me: signedInMe({ permissions: ["contract.read", "judgement.create"] }),
      },
    );

    await screen.findByRole("dialog", { name: "Estimate-versus-error judgement for Aug 2026" });
    fireEvent.change(await screen.findByRole("combobox", { name: /^Contract/ }), {
      target: { value: "PRJ" },
    });
    fireEvent.mouseDown(
      await screen.findByRole("option", { name: "PRJ-CB-2026-01 · Castellan Builders" }),
    );
    fireEvent.change(screen.getByRole("textbox", { name: /^Conclusion/ }), {
      target: { value: "Error: costs incurred in August were omitted from the cost file." },
    });
    fireEvent.change(screen.getByRole("textbox", { name: /^Rationale/ }), {
      target: { value: "The costs were known at the close and are not a change in estimate." },
    });
    const press = screen.getByRole("button", { name: "Record judgement" });

    fireEvent.click(press);
    await waitFor(() => {
      expect(sent.map((item) => item.path)).toEqual([
        "/judgements",
        `/judgements/${JUDGEMENT_ID}/submit`,
      ]);
    });
    // No answer to the submission: the drawer says so and stays.
    expect(
      await screen.findByText(
        "The request did not reach the server. Nothing was recorded. Try again.",
      ),
    ).toBeTruthy();
    expect(onClose).not.toHaveBeenCalled();
    const [create, submission] = sent;
    expect(create?.key).toMatch(/^[0-9a-f-]{36}$/);
    expect(submission?.key).not.toBe(create?.key);

    await waitFor(() => {
      expect(press.getAttribute("aria-busy")).toBeNull();
    });
    fireEvent.click(press);
    expect(await screen.findByText("Judgement JDG-000041 was submitted for review.")).toBeTruthy();
    expect(sent.map((item) => item.path)).toEqual([
      "/judgements",
      `/judgements/${JUDGEMENT_ID}/submit`,
      "/judgements",
      `/judgements/${JUDGEMENT_ID}/submit`,
    ]);
    // The create is replayed under its key — the same record — and so is the submission.
    expect(sent[2]?.key).toBe(create?.key);
    expect(sent[3]?.key).toBe(submission?.key);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): the drawer shows no message of the
  // API at a field, so the banner says every sentence of a refusal; one that names a member was shown
  // nowhere.
  it("a refused record says every sentence of the refusal", async () => {
    const first = "Say which period the costs belong to.";
    const second = "Cite the paragraph of ASC 250 the conclusion rests on.";
    server.use(
      http.get(apiUrl("/api/v1/me/notifications"), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.get(apiUrl("/api/v1/contracts"), () =>
        HttpResponse.json({
          items: [
            {
              id: CONTRACT_ID,
              external_id: "PRJ-CB-2026-01",
              customer: { id: "c0", code: "CASTELLAN", name: "Castellan Builders" },
            },
          ],
          next_cursor: null,
        }),
      ),
      http.post(apiUrl("/api/v1/judgements"), () =>
        refusedWith({ rationale: first, codification_refs: second }),
      ),
    );
    renderWithApp(
      <JudgementDrawer
        period={PERIOD}
        periodLabel="Aug 2026"
        bookLabel="ASC 606"
        onOpenRegister={null}
        onClose={() => undefined}
      />,
      {
        entry: "/close/AVM-US/ASC606/FY2026-P08",
        me: signedInMe({ permissions: ["contract.read", "judgement.create"] }),
      },
    );
    const drawer = await screen.findByRole("dialog", {
      name: "Estimate-versus-error judgement for Aug 2026",
    });
    fireEvent.change(await screen.findByRole("combobox", { name: /^Contract/ }), {
      target: { value: "PRJ" },
    });
    fireEvent.mouseDown(
      await screen.findByRole("option", { name: "PRJ-CB-2026-01 · Castellan Builders" }),
    );
    fireEvent.change(screen.getByRole("textbox", { name: /^Conclusion/ }), {
      target: { value: "Error: costs incurred in August were omitted from the cost file." },
    });
    fireEvent.change(screen.getByRole("textbox", { name: /^Rationale/ }), {
      target: { value: "The costs were known at the close and are not a change in estimate." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Record judgement" }));

    const banner = await within(drawer).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + first + second + REFUSAL_REFERENCE);
  });
});
