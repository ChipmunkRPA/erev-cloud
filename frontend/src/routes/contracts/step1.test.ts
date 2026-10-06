// @vitest-environment jsdom
// The Step 1 path (SCREENS §4.1.3 "Step 1 path", rev 1.11; supervisor ruling R-89): what the workbench
// reads from the judgement records and the assessment events of a contract. The path reads which
// events are voided through `lib/api/queries/contracts`, whose client names the page origin when it
// loads: hence the environment.
import { describe, expect, it } from "vitest";

import type { ContractEvent, Judgement } from "../../lib/api/queries/contracts";
import { isProbable, latestAssessments, step1Path } from "./step1";

const CONTRACT_ID = "9a8b7c6d-5e4f-4a3b-9c2d-1e0f9a8b7c6d";
const MAYA = {
  id: "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d",
  display_name: "Maya Chen",
  kind: "USER",
} as const;
const PRIYA = {
  id: "4d3c2b1a-0f9e-4d8c-9b7a-6f5e4d3c2b1a",
  display_name: "Priya Raman",
  kind: "USER",
} as const;

function record(overrides: Partial<Judgement>): Judgement {
  return {
    id: "1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f",
    judgement_no: "JDG-000412",
    topic: "COLLECTIBILITY",
    subject_type: "contract",
    subject_id: CONTRACT_ID,
    contract_id: CONTRACT_ID,
    book: null,
    conclusion: "Collectibility is probable.",
    rationale: "The customer paid the deposit.",
    alternatives_considered: null,
    codification_refs: ["606-10-25-1"],
    questionnaire: null,
    status: "SUBMITTED",
    approval_request_id: "2d3e4f5a-6b7c-4d8e-9f0a-1b2c3d4e5f6a",
    supersedes_id: null,
    content_sha256: "c".repeat(64),
    created_by: MAYA,
    reviewer: null,
    reviewed_at: null,
    created_at: "2026-09-10T15:02:00Z",
    updated_at: "2026-09-10T15:02:00Z",
    ...overrides,
  } as Judgement;
}

let sequence = 0;

function eventId(seq: number): string {
  return `bb000000-0000-4000-8000-${String(seq).padStart(12, "0")}`;
}

function assessed(book: string, recordId: string, probable: boolean, date: string): ContractEvent {
  sequence += 1;
  return {
    id: eventId(sequence),
    event_type: "COLLECTIBILITY_ASSESSED",
    effective_date: date,
    record_seq: sequence,
    supersedes_event_id: null,
    payload: { book, is_probable: probable, judgement_record_id: recordId },
  } as unknown as ContractEvent;
}

/**
 * The `EVENT_VOIDED` that names `target`, as `replace-draft` appends it for an assessment of the booking
 * it replaces (04 §16.1 rev 1.150): the route lists it beside the event it voids.
 */
function voided(target: Pick<ContractEvent, "id" | "effective_date">): ContractEvent {
  sequence += 1;
  return {
    id: eventId(sequence),
    event_type: "EVENT_VOIDED",
    effective_date: target.effective_date,
    record_seq: sequence,
    supersedes_event_id: target.id,
    payload: {
      reason_code: "DATA_CORRECTION",
      comment: "Step 1 assessment of a booking replaced by a corrected draft (replace-draft).",
    },
  } as unknown as ContractEvent;
}

const GATE = record({
  id: "aa000000-0000-4000-8000-000000000001",
  judgement_no: "JDG-000398",
  topic: "NOT_A_CONTRACT",
  status: "REVIEWED",
  reviewer: PRIYA,
  reviewed_at: "2026-09-01T10:00:00Z",
  created_at: "2026-09-01T09:00:00Z",
});
const REVIEW = record({});
const REVIEWED = record({
  status: "REVIEWED",
  reviewer: PRIYA,
  reviewed_at: "2026-09-10T16:20:00Z",
});

describe("SCREENS §4.1.3 Step 1 path", () => {
  it("no record, a draft or a superseded record: nothing is recorded yet", () => {
    expect(step1Path([], [], ["ASC606"])).toEqual({ kind: "none" });
    expect(step1Path([record({ status: "DRAFT" })], [], ["ASC606"])).toEqual({ kind: "none" });
    expect(step1Path([record({ status: "SUPERSEDED" })], [], ["ASC606"])).toEqual({ kind: "none" });
    // A record of another topic is not a Step 1 record.
    expect(
      step1Path([record({ topic: "CONSTRAINT", status: "REVIEWED" })], [], ["ASC606"]),
    ).toEqual({ kind: "none" });
  });

  it("a discarded record is no Step 1 record: the path reads the record behind it", () => {
    // E-57 VOIDED (04 T-CON-19 rev 1.242): a draft that was discarded and never reviewed. Read as
    // "neither a draft nor superseded" it was the latest record, and the path said "reviewed".
    const discarded = record({
      id: "cc000000-0000-4000-8000-000000000003",
      judgement_no: "JDG-000431",
      status: "VOIDED",
      approval_request_id: null,
      created_at: "2026-09-12T09:00:00Z",
    });
    expect(step1Path([discarded], [], ["ASC606"])).toEqual({ kind: "none" });
    expect(step1Path([discarded, REVIEWED], [], ["ASC606"])).toEqual({
      kind: "reviewed",
      record: REVIEWED,
    });
  });

  it("the latest record decides: waiting, rejected, reviewed", () => {
    expect(step1Path([GATE, REVIEW], [], ["ASC606"])).toEqual({ kind: "waiting", record: REVIEW });
    const rejected = record({ status: "REJECTED" });
    expect(step1Path([rejected, GATE], [], ["ASC606"])).toEqual({
      kind: "rejected",
      record: rejected,
    });
    expect(step1Path([REVIEWED], [], ["ASC606"])).toEqual({ kind: "reviewed", record: REVIEWED });
  });

  it("a reviewed record is assessed only when the latest assessment of every enabled book cites it", () => {
    const gate = [assessed("ASC606", GATE.id, false, "2026-09-01")];
    // Behind the gate: the gate's own record is cited, not probable.
    expect(step1Path([GATE], gate, ["ASC606"])).toEqual({
      kind: "assessed",
      record: GATE,
      probable: false,
      date: "2026-09-01",
    });
    // The new review is reviewed and no assessment cites it yet.
    expect(step1Path([GATE, REVIEWED], gate, ["ASC606"])).toEqual({
      kind: "reviewed",
      record: REVIEWED,
    });
    // One of two books assessed: the other still waits for its assessment.
    const one = [...gate, assessed("ASC606", REVIEWED.id, true, "2026-09-10")];
    expect(step1Path([GATE, REVIEWED], one, ["ASC606", "IFRS15"]).kind).toBe("reviewed");
    const both = [...one, assessed("IFRS15", REVIEWED.id, true, "2026-09-11")];
    expect(step1Path([GATE, REVIEWED], both, ["ASC606", "IFRS15"])).toEqual({
      kind: "assessed",
      record: REVIEWED,
      probable: true,
      date: "2026-09-11",
    });
  });

  it("the latest assessment of a book is the one in force: effective date, then record order", () => {
    const early = assessed("ASC606", GATE.id, false, "2026-09-01");
    const late = assessed("ASC606", REVIEWED.id, true, "2026-09-10");
    const sameDay = assessed("ASC606", GATE.id, false, "2026-09-10");
    expect(latestAssessments([late, early]).get("ASC606")?.recordId).toBe(REVIEWED.id);
    // Recorded later on the same date wins.
    expect(latestAssessments([late, sameDay, early]).get("ASC606")?.probable).toBe(false);
  });

  // Rev 1.72 (supervisor ruling R-102 (c); 04 §16.1 rev 1.150): `replace-draft` voids the assessments
  // of the draft it replaces. The events route lists a voided assessment like any other, and the path
  // read "assessed" over it while the activation checklist said "Step 1 review not recorded."
  it("an assessment that a void names counts for nothing: the replaced draft is reviewed, not assessed", () => {
    const first = assessed("ASC606", REVIEWED.id, true, "2026-09-10");
    const second = assessed("IFRS15", REVIEWED.id, true, "2026-09-10");
    const books = ["ASC606", "IFRS15"];
    expect(step1Path([REVIEWED], [first, second], books).kind).toBe("assessed");

    const replaced = [first, second, voided(first), voided(second)];
    expect(latestAssessments(replaced).size).toBe(0);
    expect(step1Path([REVIEWED], replaced, books)).toEqual({ kind: "reviewed", record: REVIEWED });
    // One book's assessment voided, the other's standing: that book still waits.
    expect(step1Path([REVIEWED], [first, second, voided(second)], books)).toEqual({
      kind: "reviewed",
      record: REVIEWED,
    });
    // The order the route lists them in does not matter.
    expect(latestAssessments([voided(first), first, second]).get("ASC606")).toBeUndefined();
    expect(latestAssessments([voided(first), first, second]).get("IFRS15")?.recordId).toBe(
      REVIEWED.id,
    );
  });

  it("behind a voided assessment the book's latest standing one is in force", () => {
    const gate = assessed("ASC606", GATE.id, false, "2026-09-01");
    const later = assessed("ASC606", REVIEWED.id, true, "2026-09-10");
    expect(latestAssessments([gate, later]).get("ASC606")?.recordId).toBe(REVIEWED.id);
    expect(latestAssessments([gate, later, voided(later)]).get("ASC606")).toEqual({
      book: "ASC606",
      probable: false,
      recordId: GATE.id,
      date: "2026-09-01",
    });
    // A void that names another event of the stream takes no assessment out.
    const other = voided({
      id: "dd000000-0000-4000-8000-000000000009",
      effective_date: "2026-09-10",
    });
    expect(latestAssessments([gate, later, other]).get("ASC606")?.recordId).toBe(REVIEWED.id);
  });

  it("the topic of the record is its outcome", () => {
    expect(isProbable(REVIEWED)).toBe(true);
    expect(isProbable(GATE)).toBe(false);
  });
});
