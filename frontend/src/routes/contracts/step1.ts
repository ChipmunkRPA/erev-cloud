// The Step 1 path of a contract (SCREENS §4.1.3 "Step 1 path", rev 1.11; supervisor ruling R-89; PRD
// SM-02; 04 §16.3, T-CON-19). A Step 1 judgement is recorded in two steps: the review (a judgement
// record, submitted) and, once it is reviewed, the assessment that cites it. The path is read from the
// latest Step 1 record and the latest standing `COLLECTIBILITY_ASSESSED` event of each enabled book, and
// says which line the workbench shows and which command comes next. An assessment that an `EVENT_VOIDED`
// names counts for nothing (rev 1.72; ruling R-102 (c)): `replace-draft` voids the assessments of the
// draft it replaces.
import {
  type ContractEvent,
  type Judgement,
  voidedEventIds,
} from "../../lib/api/queries/contracts";

/** T-CON-19 topics of a Step 1 record: the screen writes NOT_A_CONTRACT for a not-probable outcome. */
export const STEP1_TOPICS: ReadonlySet<string> = new Set(["COLLECTIBILITY", "NOT_A_CONTRACT"]);

export interface Assessment {
  readonly book: string;
  readonly probable: boolean;
  readonly recordId: string | null;
  /** The effective date of the event (a business date). */
  readonly date: string;
}

export type Step1Path =
  /** No Step 1 review is recorded. */
  | { readonly kind: "none" }
  /** The latest record waits for its review. */
  | { readonly kind: "waiting"; readonly record: Judgement }
  | { readonly kind: "rejected"; readonly record: Judgement }
  /** The latest record is reviewed and an enabled book's latest standing assessment does not cite it. */
  | { readonly kind: "reviewed"; readonly record: Judgement }
  /** The latest record is reviewed and cited by the latest standing assessment of every enabled book. */
  | {
      readonly kind: "assessed";
      readonly record: Judgement;
      readonly probable: boolean;
      /** The latest effective date among those assessments. */
      readonly date: string;
    };

/** A record of topic COLLECTIBILITY concludes that collectibility is probable (SCREENS §4.9.1). */
export function isProbable(record: Pick<Judgement, "topic">): boolean {
  return record.topic === "COLLECTIBILITY";
}

/**
 * The latest standing assessment of each book: by effective date, then record order (ENG-06). `events`
 * holds the assessments and the voids of the stream; an assessment a void names is left out.
 */
export function latestAssessments(
  events: readonly ContractEvent[],
): ReadonlyMap<string, Assessment> {
  const voided = voidedEventIds(events);
  const latest = new Map<string, { readonly event: ContractEvent; readonly item: Assessment }>();
  for (const event of events) {
    if (event.event_type !== "COLLECTIBILITY_ASSESSED" || voided.has(event.id)) {
      continue;
    }
    const book = event.payload.book;
    if (typeof book !== "string") {
      continue;
    }
    const record = event.payload.judgement_record_id;
    const item: Assessment = {
      book,
      probable: event.payload.is_probable === true,
      recordId: typeof record === "string" ? record : null,
      date: event.effective_date,
    };
    const held = latest.get(book)?.event;
    if (
      held === undefined ||
      event.effective_date > held.effective_date ||
      (event.effective_date === held.effective_date && event.record_seq > held.record_seq)
    ) {
      latest.set(book, { event, item });
    }
  }
  return new Map([...latest].map(([book, found]) => [book, found.item]));
}

/**
 * The latest Step 1 record: newest first, without drafts, superseded records and discarded drafts
 * (E-57 `VOIDED`, 04 T-CON-19 rev 1.242: a discarded draft was never reviewed).
 */
export function latestStep1Record(records: readonly Judgement[]): Judgement | undefined {
  return records
    .filter(
      (record) =>
        STEP1_TOPICS.has(record.topic) &&
        record.status !== "DRAFT" &&
        record.status !== "SUPERSEDED" &&
        record.status !== "VOIDED",
    )
    .sort((left, right) => (left.created_at < right.created_at ? 1 : -1))[0];
}

/** Where the contract stands on the Step 1 path, for the enabled books of its contracting entity. */
export function step1Path(
  records: readonly Judgement[],
  events: readonly ContractEvent[],
  books: readonly string[],
): Step1Path {
  const record = latestStep1Record(records);
  if (record === undefined) {
    return { kind: "none" };
  }
  if (record.status === "SUBMITTED") {
    return { kind: "waiting", record };
  }
  if (record.status === "REJECTED") {
    return { kind: "rejected", record };
  }
  const latest = latestAssessments(events);
  const citing = books.map((book) => latest.get(book));
  const cited = citing.filter(
    (item): item is Assessment => item !== undefined && item.recordId === record.id,
  );
  if (books.length === 0 || cited.length < books.length) {
    return { kind: "reviewed", record };
  }
  return {
    kind: "assessed",
    record,
    probable: cited.every((item) => item.probable),
    date:
      cited
        .map((item) => item.date)
        .sort()
        .at(-1) ?? "",
  };
}
