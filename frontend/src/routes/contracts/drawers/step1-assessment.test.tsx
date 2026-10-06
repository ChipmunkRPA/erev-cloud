// @vitest-environment jsdom
// Record assessment (SCREENS §4.9.1; §0.8 rev 1.66; 04 E-57 rev 1.242): the drawer names the Step 1
// record it cites. A record it is handed without its reviewer is named with its status, which the
// drawer read through a catalogue key without a fallback — `t()` throws on a key the catalogue lacks
// — while E-57 gained `VOIDED`. It reads the status in the words every screen uses now.
//
// Rev 1.72 (supervisor ruling R-102 (c); REQ-POL-008): the API may refuse the record itself. The
// drawer compares no time of its own; it says the API's sentence and offers a new Step 1 review.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Contract, Judgement } from "../../../lib/api/queries/contracts";
import { renderWithApp } from "../../../test/app";
import { judgementRecord } from "../../../test/modifications";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import { CONTRACT_ID, PRIYA_USER, workbenchContract } from "../../../test/workbench";
import { Step1AssessmentDrawer } from "./step1-assessment";

installMswServer();

afterEach(() => {
  cleanup();
});

const CONTRACT = workbenchContract({ status: "DRAFT" }) as unknown as Contract;
const GATED = workbenchContract({ status: "NOT_A_CONTRACT" }) as unknown as Contract;

function review(overrides: Partial<Judgement>): Judgement {
  return judgementRecord({
    judgement_no: "JDG-000412",
    topic: "COLLECTIBILITY",
    subject_type: "contract",
    subject_id: CONTRACT_ID,
    conclusion: "Collectibility is probable.",
    questionnaire: { credit_grade: "B", mitigation: "ADVANCE_PAYMENT" },
    ...overrides,
  });
}

/** The value the drawer shows under "Step 1 review". */
function reviewFact(record: Judgement): string {
  renderWithApp(
    <Step1AssessmentDrawer
      contract={CONTRACT}
      record={record}
      books={["ASC606"]}
      today="2026-09-12"
      onClose={() => undefined}
      onNewReview={() => undefined}
    />,
  );
  const drawer = screen.getByRole("dialog", { name: "Record assessment" });
  const term = within(drawer).getByText("Step 1 review");
  return term.parentElement?.querySelector("dd")?.textContent ?? "";
}

describe("SF-03 Record assessment, the Step 1 record it cites", () => {
  it("Record assessment names a reviewed record with its reviewer, and any other with its status in the shared words", () => {
    expect(
      reviewFact(
        review({ status: "REVIEWED", reviewer: PRIYA_USER, reviewed_at: "2026-09-10T16:20:00Z" }),
      ),
    ).toBe("JDG-000412 · Reviewed by Priya Raman, 10 Sep 2026 16:20 UTC");
    cleanup();

    for (const [status, word] of [
      ["REVIEWED", "Reviewed"],
      ["SUBMITTED", "Waiting for review"],
      ["VOIDED", "Void"],
      // A literal a later API adds reads as itself.
      ["ESCALATED", "ESCALATED"],
    ] as const) {
      expect(reviewFact(review({ status: status as Judgement["status"] }))).toBe(
        `Record JDG-000412 · ${word}`,
      );
      cleanup();
    }
  });
});

describe("SF-03 Record assessment, a record the API refuses", () => {
  const REVIEWED = review({
    status: "REVIEWED",
    reviewer: PRIYA_USER,
    reviewed_at: "2026-09-12T12:00:00Z",
  });
  const OFFER = "Record a new Step 1 review";
  const OLDER = "Use a judgement record reviewed after the draft was last replaced.";
  const TITLE = "Check the highlighted fields";

  /** One error of the Step 1 rule as the events route answers it (04 §16.3). */
  function refusal(field: string, message: string, ruleId = "REQ-POL-008") {
    return problemResponse("validation-failed", 422, TITLE, {
      code: null,
      detail: message,
      errors: [{ field, message, row: null, rule_id: ruleId, sheet: null }],
    });
  }

  function open(answer: () => Response, contract: Contract = CONTRACT) {
    const sent: unknown[] = [];
    server.use(
      http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/events`), async ({ request }) => {
        sent.push(await request.json());
        return answer();
      }),
    );
    const onClose = vi.fn();
    const onNewReview = vi.fn();
    renderWithApp(
      <Step1AssessmentDrawer
        contract={contract}
        record={REVIEWED}
        books={["ASC606"]}
        today="2026-09-12"
        onClose={onClose}
        onNewReview={onNewReview}
      />,
    );
    return { sent, onClose, onNewReview };
  }

  function press(title = "Record assessment"): HTMLElement {
    const drawer = screen.getByRole("dialog", { name: title });
    fireEvent.click(within(drawer).getByRole("button", { name: title }));
    return drawer;
  }

  // The body is the route's own, measured on the API (register index 267 (iii)): a draft reviewed,
  // then replaced a minute later, then assessed on the record of before the replacement.
  it("the record was reviewed before the draft was last replaced: the banner says the API's sentence once and offers a new Step 1 review", async () => {
    const { sent, onClose, onNewReview } = open(() =>
      refusal("events.0.payload.judgement_record_id", OLDER),
    );
    // Nothing is offered, and nothing refused, before the API answered.
    expect(screen.queryByRole("button", { name: OFFER })).toBeNull();
    const drawer = press();

    const banner = await within(drawer).findByRole("alert");
    expect(within(banner).getByRole("heading", { name: TITLE })).toBeTruthy();
    expect(Array.from(banner.querySelectorAll("p"), (line) => line.textContent)).toEqual([
      OLDER,
      "Reference 0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d.",
    ]);
    expect(sent).toHaveLength(1);
    expect(onNewReview).not.toHaveBeenCalled();

    fireEvent.click(within(banner).getByRole("button", { name: OFFER }));
    expect(onNewReview).toHaveBeenCalledTimes(1);
    // The offer hands the drawer over; it sends nothing and does not ask to discard anything.
    expect(onClose).not.toHaveBeenCalled();
    expect(sent).toHaveLength(1);
  });

  it("any refusal of the record offers the new review: a criterion the review answers No to", async () => {
    const unmet = (label: string) =>
      `The Step 1 review answers No for ${label}: the contract is not activated until the criterion is met.`;
    open(() => refusal("events.0.payload.judgement_record_id", unmet("Approved and committed")));
    const banner = await within(press()).findByRole("alert");
    expect(within(banner).getByText(unmet("Approved and committed"))).toBeTruthy();
    expect(within(banner).getByRole("button", { name: OFFER })).toBeTruthy();
    cleanup();

    // Behind the gate the header holds one command, "Record criteria met": the offer is the way
    // from a refused record to a new review there.
    const { onNewReview } = open(
      () => refusal("events.0.payload.judgement_record_id", unmet("Commercial substance")),
      GATED,
    );
    const gated = await within(press("Record criteria met")).findByRole("alert");
    expect(within(gated).getByText(unmet("Commercial substance"))).toBeTruthy();
    fireEvent.click(within(gated).getByRole("button", { name: OFFER }));
    expect(onNewReview).toHaveBeenCalledTimes(1);
  });

  it("a refusal that names the date or another member offers no new review: another date, or the record's own data, leads out", async () => {
    const dated =
      "This assessment is dated before the contract's latest Step 1 entry in ASC 606 (10 Sep 2026). Date it on or after that date.";
    // The same rule id, REQ-POL-008, on the date: the member the error names decides.
    open(() => refusal("events.0.effective_date", dated));
    const drawer = press();
    expect(await within(drawer).findByText(dated)).toBeTruthy();
    expect(within(drawer).queryByRole("button", { name: OFFER })).toBeNull();
    cleanup();

    const grade = "Use a credit grade of the entity's scale.";
    open(() => refusal("events.0.payload.credit_grade", grade, "T-CON-19"));
    const banner = await within(press()).findByRole("alert");
    expect(within(banner).getByText(grade)).toBeTruthy();
    expect(within(banner).queryByRole("button", { name: OFFER })).toBeNull();
  });

  it("the offer leaves with the refusal: the next press starts without it", async () => {
    let refuse = true;
    const { sent, onClose } = open(() =>
      refuse
        ? refusal("events.0.payload.judgement_record_id", OLDER)
        : HttpResponse.json(
            { events: [], contract: CONTRACT, computation: null, step1_gate: null },
            { status: 201 },
          ),
    );
    const drawer = press();
    expect(await within(drawer).findByRole("button", { name: OFFER })).toBeTruthy();

    refuse = false;
    fireEvent.click(within(drawer).getByRole("button", { name: "Record assessment" }));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(sent).toHaveLength(2);
    expect(await screen.findByText("Assessment recorded.")).toBeTruthy();
  });
});
