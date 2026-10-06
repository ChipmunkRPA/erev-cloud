// @vitest-environment jsdom
// "Discard" of a draft judgement record (SCREENS §4.1.3, §7.4, §7.6 and §8.3, rev 1.66; PRD SM-10
// `DRAFT` → `VOIDED`; 04 API-R-33 `POST /judgements/{id}/discard`, T-CON-19, E-57 rev 1.242): the
// command of the three places that can be left with a draft — the workbench's Step 1 evidence, the
// modification wizard and the estimate's evidence. It renders for a holder of `judgement.create` for
// the contract's entity on a draft that is not the proposal of a combination group, asks first, says
// where the contract is on hold that the hold stays, and shows the API's refusal in the confirmation.
//
// Rev 1.74 (PRD SM-10 rev 1.199, IMP-145; 04 rev 1.296): the discard takes a rejected record as it
// takes a draft — after a rejection the screens write a new record, and the rejected one failed the
// activation checklist with no command on any screen.
import { useQuery } from "@tanstack/react-query";
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Contract, Judgement } from "../../lib/api/queries/contracts";
import { queryKey } from "../../lib/api/query-keys";
import { renderWithApp, signedInMe } from "../../test/app";
import { JUDGEMENT_ID, judgementRecord } from "../../test/modifications";
import { apiUrl, heldRead, installMswServer, problemResponse, server } from "../../test/msw";
import { REFUSAL_REFERENCE } from "../../test/refusals";
import { AVM_US, K02, workbenchContract } from "../../test/workbench";
import { DiscardRecord } from "./judgement-discard";

installMswServer();

afterEach(() => {
  cleanup();
});

const READS = [queryKey("modification-judgements", "tenant")];
const CONSEQUENCE =
  "Record JDG-000012 is voided: it takes no further edit and no review, and its number is not given out again.";
const HOLD = `${K02} is on hold. The discard releases nothing: the hold stays and is released on the contract.`;
// The route's sentence since 04 rev 1.296 (measured on the API, register index 274).
const NOT_DISCARDABLE = "Only a draft or rejected judgement record can be discarded.";

const HOLDER = signedInMe({ permissions: ["contract.read", "judgement.create"] });

function holderFor(entityId: string) {
  return signedInMe({
    permissions: ["contract.read", "judgement.create"],
    permission_scopes: { "contract.read": "*", "judgement.create": [entityId] },
  });
}

interface Mounting {
  readonly me?: typeof HOLDER;
  readonly onHold?: boolean;
  readonly onDiscarded?: () => void;
}

function mount(record: Judgement, { me = HOLDER, onHold = false, onDiscarded }: Mounting = {}) {
  // A member of named entities resolves a record's entity against the workspace's entities.
  server.use(
    http.get(apiUrl("/api/v1/entities"), () =>
      HttpResponse.json({ items: [AVM_US], next_cursor: null }),
    ),
  );
  return renderWithApp(
    <DiscardRecord
      record={record}
      contract={workbenchContract({ on_hold: onHold }) as unknown as Contract}
      invalidates={READS}
      testId="SF-07-dialog-discard-record"
      onDiscarded={onDiscarded}
    />,
    { me },
  );
}

/** The discards the API was sent: the body and the Idempotency-Key of each. */
function serveDiscard(answer: () => Response) {
  const sent: { readonly body: string; readonly key: string | null }[] = [];
  server.use(
    http.post(apiUrl(`/api/v1/judgements/${JUDGEMENT_ID}/discard`), async ({ request }) => {
      sent.push({ body: await request.text(), key: request.headers.get("Idempotency-Key") });
      return answer();
    }),
  );
  return sent;
}

describe("Discard of a draft judgement record", () => {
  it("Discard voids the draft after a confirmation: a POST without a body, a toast, and the reads that list the record are read again", async () => {
    const sent = serveDiscard(() => HttpResponse.json(judgementRecord({ status: "VOIDED" })));
    const { queryClient } = mount(judgementRecord());
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");

    fireEvent.click(await screen.findByRole("button", { name: "Discard" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Discard this draft record?" });
    expect(dialog.getAttribute("data-testid")).toBe("SF-07-dialog-discard-record");
    expect(within(dialog).getByText(CONSEQUENCE)).toBeTruthy();
    // Nothing is sent before the confirmation.
    expect(sent).toEqual([]);
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard" }));

    expect(await screen.findByText("Record JDG-000012 was discarded.")).toBeTruthy();
    expect(sent.map((item) => item.body)).toEqual([""]);
    expect(invalidate.mock.calls.map(([filters]) => filters?.queryKey)).toEqual(READS);
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
  });

  it("Discard is offered to a holder of judgement.create for the contract's entity, on a draft that is not the proposal of a combination group", async () => {
    // The API asks the permission for the record's entity of anyone, not of the creator alone.
    mount(judgementRecord(), { me: holderFor(AVM_US.id) });
    expect(await screen.findByRole("button", { name: "Discard" })).toBeTruthy();
    cleanup();

    const withoutCommand: readonly (readonly [Judgement, typeof HOLDER])[] = [
      // A reader, and a holder for another entity (SCREENS §0.6 SCR-PERM-02 (a)).
      [judgementRecord(), signedInMe({ permissions: ["contract.read"] })],
      [judgementRecord(), holderFor("0a1b2c3d-4e5f-4a6b-8c7d-0000000000ff")],
      // The proposal of a combination group is decided with its group (the API answers 409).
      [judgementRecord({ topic: "COMBINATION", subject_type: "combination_group" }), HOLDER],
      // A record that waits for review, is reviewed, superseded or discarded takes no discard.
      [judgementRecord({ status: "SUBMITTED" }), HOLDER],
      [judgementRecord({ status: "REVIEWED" }), HOLDER],
      [judgementRecord({ status: "SUPERSEDED" }), HOLDER],
      [judgementRecord({ status: "VOIDED" }), HOLDER],
    ];
    for (const [record, me] of withoutCommand) {
      mount(record, { me });
      // Nothing renders for them; the pause lets a late read of the session's entities answer.
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(screen.queryByRole("button", { name: "Discard" })).toBeNull();
      cleanup();
    }
  });

  it("the confirmation of a contract on hold says that the hold stays and is released on the contract", async () => {
    mount(judgementRecord(), { onHold: true });
    fireEvent.click(await screen.findByRole("button", { name: "Discard" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Discard this draft record?" });
    expect(within(dialog).getByText(`${CONSEQUENCE} ${HOLD}`)).toBeTruthy();
    cleanup();

    // A contract that is not on hold: the consequence alone.
    mount(judgementRecord());
    fireEvent.click(await screen.findByRole("button", { name: "Discard" }));
    const plain = await screen.findByRole("alertdialog", { name: "Discard this draft record?" });
    expect(within(plain).getByText(CONSEQUENCE)).toBeTruthy();
    expect(within(plain).queryByText(/on hold/)).toBeNull();
  });

  it("a refused discard is shown in the confirmation, and the record stays", async () => {
    const sent = serveDiscard(() =>
      problemResponse("invalid-transition", 409, "Action not available in this state", {
        code: null,
        detail: NOT_DISCARDABLE,
        errors: [
          { field: "status", message: NOT_DISCARDABLE, row: null, rule_id: "DB-03", sheet: null },
        ],
      }),
    );
    const onDiscarded = vi.fn();
    const { queryClient } = mount(judgementRecord(), { onDiscarded });
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");

    fireEvent.click(await screen.findByRole("button", { name: "Discard" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Discard this draft record?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard" }));

    const banner = await within(dialog).findByRole("alert");
    expect(
      within(banner).getByRole("heading", { name: "Action not available in this state" }),
    ).toBeTruthy();
    // The sentence once: the detail and the entry of `errors[]` say the same.
    expect(within(banner).getAllByText(NOT_DISCARDABLE)).toHaveLength(1);
    expect(within(banner).getByText(REFUSAL_REFERENCE)).toBeTruthy();
    expect(sent).toHaveLength(1);
    expect(screen.queryByText("Record JDG-000012 was discarded.")).toBeNull();
    expect(invalidate).not.toHaveBeenCalled();
    expect(onDiscarded).not.toHaveBeenCalled();
    // A confirmation opened again starts without the refusal of the last one.
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    const again = await screen.findByRole("alertdialog", { name: "Discard this draft record?" });
    expect(within(again).queryByRole("alert")).toBeNull();
  });

  it("a discard that gets no answer says so, keeps the confirmation and goes out again under the key it had", async () => {
    let answers = 0;
    const sent = serveDiscard(() => {
      answers += 1;
      return answers === 1
        ? HttpResponse.error()
        : HttpResponse.json(judgementRecord({ status: "VOIDED" }));
    });
    mount(judgementRecord());

    fireEvent.click(await screen.findByRole("button", { name: "Discard" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Discard this draft record?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard" }));
    expect(await screen.findByText("No answer came back from the server. Try again.")).toBeTruthy();
    expect(screen.getByRole("alertdialog", { name: "Discard this draft record?" })).toBeTruthy();

    await waitFor(() =>
      expect(
        within(dialog).getByRole("button", { name: "Discard" }).getAttribute("aria-busy"),
      ).toBeNull(),
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard" }));
    expect(await screen.findByText("Record JDG-000012 was discarded.")).toBeTruthy();
    expect(sent).toHaveLength(2);
    expect(sent[0]?.key).not.toBeNull();
    expect(sent[1]?.key).toBe(sent[0]?.key);
  });
});

// SCREENS §4.1.3 (rev 1.74; PRD SM-10 rev 1.199; 04 rev 1.296): `POST /judgements/{id}/discard` takes
// a rejected record as it takes a draft, for the same holder.
describe("Discard of a rejected judgement record", () => {
  // The record as the route lists it after a rejection (measured): its request stays on the row.
  const REJECTED = judgementRecord({
    status: "REJECTED",
    approval_request_id: "2d3e4f5a-6b7c-4d8e-9f0a-1b2c3d4e5f6a",
    content_sha256: "c".repeat(64),
  });

  it("a rejected record is discarded as a draft is, under a title that names it rejected", async () => {
    const sent = serveDiscard(() => HttpResponse.json({ ...REJECTED, status: "VOIDED" }));
    const onDiscarded = vi.fn();
    const { queryClient } = mount(REJECTED, { onHold: true, onDiscarded });
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");

    fireEvent.click(await screen.findByRole("button", { name: "Discard" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Discard this rejected record?",
    });
    // The consequence and the sentence of a contract on hold are the draft's.
    expect(within(dialog).getByText(`${CONSEQUENCE} ${HOLD}`)).toBeTruthy();
    expect(sent).toEqual([]);
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard" }));

    expect(await screen.findByText("Record JDG-000012 was discarded.")).toBeTruthy();
    expect(sent.map((item) => item.body)).toEqual([""]);
    expect(invalidate.mock.calls.map(([filters]) => filters?.queryKey)).toEqual(READS);
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    // The caller is told once, after the reads.
    expect(onDiscarded).toHaveBeenCalledTimes(1);
  });

  it("the confirmation names the record rejected until it closes, also while the record is read again as discarded", async () => {
    // Where the record's row stays — the wizard's linked records, an estimate's evidence — the record
    // is read again before the confirmation closes. One read answers at once and the other is held:
    // for that time the confirmation stands over a record that is discarded already.
    const recordKey = queryKey("probe-record", "tenant");
    const slowKey = queryKey("probe-slow", "tenant");
    const slow = heldRead();
    let status: Judgement["status"] = "REJECTED";
    server.use(
      http.get(apiUrl("/api/v1/entities"), () =>
        HttpResponse.json({ items: [AVM_US], next_cursor: null }),
      ),
    );
    serveDiscard(() => {
      status = "VOIDED";
      return HttpResponse.json({ ...REJECTED, status });
    });
    function Row() {
      const record = useQuery({
        queryKey: recordKey,
        queryFn: () => Promise.resolve({ ...REJECTED, status }),
      });
      useQuery({
        queryKey: slowKey,
        queryFn: async () => {
          await slow.passed();
          return null;
        },
      });
      return record.data === undefined ? null : (
        <>
          <span data-testid="row-status">{record.data.status}</span>
          <DiscardRecord
            record={record.data}
            contract={workbenchContract() as unknown as Contract}
            invalidates={[recordKey, slowKey]}
            testId="SF-07-dialog-discard-record"
          />
        </>
      );
    }
    renderWithApp(<Row />, { me: HOLDER });

    fireEvent.click(await screen.findByRole("button", { name: "Discard" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Discard this rejected record?",
    });
    slow.hold();
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard" }));

    await waitFor(() => expect(screen.getByTestId("row-status").textContent).toBe("VOIDED"));
    expect(slow.waiting()).toBe(1);
    expect(screen.getByRole("alertdialog", { name: "Discard this rejected record?" })).toBeTruthy();
    slow.release();
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    // The row stays, and the command is gone with the record's status.
    expect(screen.getByTestId("row-status").textContent).toBe("VOIDED");
    expect(screen.queryByRole("button", { name: "Discard" })).toBeNull();
  });
});
