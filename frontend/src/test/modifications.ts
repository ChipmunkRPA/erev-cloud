// The modification world of the SF-07 tests (PRD §2.7 WLD-X-05, WLD-X-06; 04 API-R-31, §16.14): the
// K-02 co-term draft as the API answers it, and a stand-in of the modification routes that keeps one
// row as the API does. `PATCH` clears the proposal, the stored preview and what the classification
// answered; `/classify` proposes from the stored answers, keeps every stored choice, answers the
// prefill of the questions that have no stored answer (with `priceTestAlways`, the price test beside
// a stored answer too) and the engine's price test of the added line whatever is stored
// (`price_tests`, 04 §16.14 rev 1.250), and keeps both on the row, so that every later answer of the
// row carries them until the next edit (04 T-CON-06 `classification`); `/preview` is a 202 job whose
// run stores the preview, in place of an earlier one, with the period its journal lines were computed
// for (`postablePeriod`); `/submit`, `/withdraw` and `/discard` move the row and its request and
// answer the row as `GET` does, with its stored preview. With an estimates world attached
// (`estimates`), every answer lists the versions created inside the row and the submission and the
// discard refuse as the API does (PRD ERR-87, ERR-83). A suite reads `requests` for what the screen
// sent.
import { http, HttpResponse } from "msw";

import type { components } from "../lib/api/schema";
import type { EstimateWorld } from "./estimates";
import { apiUrl, problemResponse, server } from "./msw";
import { AVM_US, CONTRACT_ID, K02, MAYA_USER, money, PERIOD, PRIYA_USER } from "./workbench";

type Modification = components["schemas"]["ModificationOut"];
type LinkedVersion = components["schemas"]["LinkedEstimateVersionOut"];
type ImpactSummary = components["schemas"]["ImpactSummaryOut"];
type Judgement = components["schemas"]["JudgementOut"];
type Approval = components["schemas"]["ApprovalOut"];
type Job = components["schemas"]["JobOut"];

export const MODIFICATION_ID = "b4b4b4b4-b4b4-4b4b-8b4b-b4b4b4b4b4b4";
export const JOB_ID = "c5c5c5c5-c5c5-4c5c-8c5c-c5c5c5c5c5c5";
export const APPROVAL_ID = "d6d6d6d6-d6d6-4d6d-8d6d-d6d6d6d6d6d6";
export const JUDGEMENT_ID = "e7e7e7e7-e7e7-4e7e-8e7e-e7e7e7e7e7e7";
export const SSP_BOOK_ID = "f8f8f8f8-f8f8-4f8f-8f8f-f8f8f8f8f8f8";
/** `US-LIST 2026-H1`, the version the classification selects for the added line. */
export const SSP_VERSION_ID = "a9a9a9a9-a9a9-4a9a-8a9a-a9a9a9a9a9a9";
/** `US-LIST 2026-H2`, another approved version the preparer may name. */
export const OTHER_SSP_VERSION_ID = "bababa00-baba-4bab-8bab-babababababa";
export const REFERENCE = "CR-MARROWBY-2026-09";
/** The comment of the decision that rejects the row's request (`approvalStatus` REJECTED). */
export const REJECTION_COMMENT = "The seat count does not match the change order.";

/**
 * API-S-ImpactSummary of the K-02 co-term at 16 Sep 2026, as the dry run answers it while September
 * is the latest postable period: the split of PRD WLD-X-06, and the journal lines the approval would
 * post then — the change's effect with September's amounts not posted yet, each account with both
 * sides (04 rev 1.210, item MOD-PREVIEW-JOURNAL-RULE-1; measured on the e2e world on 2026-10-01).
 */
export const PREVIEW: ImpactSummary = {
  transaction_price_before: money("240000.00"),
  transaction_price_after: money("300000.00"),
  catch_up_total: money("0.00"),
  catch_up_by_obligation: [
    { obligation_key: "O1", treatment: "PROSPECTIVE", amount: money("0.00") },
    { obligation_key: "O2", treatment: "PROSPECTIVE", amount: money("0.00") },
  ],
  remaining_allocation_before: [{ obligation_key: "O1", amount: money("155178.08") }],
  remaining_allocation_after: [
    { obligation_key: "O1", amount: money("148451.55") },
    { obligation_key: "O2", amount: money("66726.53") },
  ],
  revenue_by_period: [
    {
      period_key: "FY2026-P09",
      before: money("9863.01"),
      after: money("11769.80"),
      change: money("1906.79"),
    },
    {
      period_key: "FY2026-P10",
      before: money("10191.79"),
      after: money("14132.46"),
      change: money("3940.67"),
    },
  ],
  rpo_before: money("155178.08"),
  rpo_after: money("215178.08"),
  rpo_date: "2026-09-16",
  balances_before: [],
  balances_after: [],
  journal_lines: [
    {
      gl_account: {
        id: "1a1a1a1a-1a1a-4a1a-8a1a-1a1a1a1a1a1a",
        code: "2100",
        name: "Contract liability",
      },
      account_role: "CONTRACT_LIABILITY",
      debit: money("2120.55"),
      credit: money("213.76"),
    },
    {
      gl_account: {
        id: "2b2b2b2b-2b2b-4b2b-8b2b-2b2b2b2b2b2b",
        code: "4010",
        name: "Revenue - services and subscriptions",
      },
      account_role: "REVENUE",
      debit: money("213.76"),
      credit: money("2120.55"),
    },
  ],
  progress_before: null,
  progress_after: null,
  replay_from_date: "2026-09-16",
  posting_period_key: "FY2026-P09",
  origin_period_key: null,
  computed_at: "2026-09-16T09:40:04Z",
  computed_period_key: "FY2026-P09",
};

/** The one line of the draft: 50 seats added for the remaining term (ENGINE_SPEC S06-R-19 `CO_TERM`). */
export const ADDED_LINE = {
  action: "ADD",
  obligation_key: "O2",
  product_code: "AVM-SEAT-MO",
  quantity_delta: "50",
  consideration_delta: money("60000.00"),
  start_date: "2026-09-16",
  end_date: "2027-12-31",
  selling_entity_code: null,
  ssp_version_label: null,
  memo_1: null,
  memo_2: null,
  memo_3: null,
  account_codes: null,
  stratification: null,
};

/** API-S-Modification of the K-02 draft as `POST /contracts/{id}/modifications` answers it. */
export function modificationRow(overrides: Partial<Modification> = {}): Modification {
  return {
    id: MODIFICATION_ID,
    contract_id: CONTRACT_ID,
    contracting_entity_id: AVM_US.id,
    modification_no: "MOD-000003",
    reference: REFERENCE,
    kind: "CO_TERM",
    status: "DRAFT",
    effective_date: "2026-09-16",
    currency: "USD",
    rationale: null,
    lines: [ADDED_LINE],
    questionnaire: {},
    proposed_treatments: {},
    chosen_treatments: {},
    treatment_summary: null,
    ssp_basis: {},
    price_change_amount: null,
    noncash_consideration: null,
    consideration_payable: null,
    scope_605_35: null,
    template_mode: null,
    impact_preview: null,
    impact_preview_file_id: null,
    impact_preview_withheld: false,
    impact_preview_sha256: null,
    impact_summary: { catch_up_total: null },
    content_sha256: null,
    judgement_record_id: null,
    regroup_id: null,
    approval_request_id: null,
    applied_event_id: null,
    approver: null,
    approved_at: null,
    preparer: MAYA_USER,
    row_version: 1,
    created_at: "2026-09-16T09:00:00Z",
    updated_at: "2026-09-16T09:00:00Z",
    ...overrides,
  };
}

const PROSPECTIVE = { O1: "PROSPECTIVE", O2: "PROSPECTIVE" };
const CONFIRMED = {
  O1: { remaining_goods_distinct_from_transferred: true },
  O2: { added_goods_distinct: true, priced_at_ssp: false },
};
const DEFAULT_BASIS = {
  O2: { ssp_book_version_id: SSP_VERSION_ID, is_override: false, justification: null },
};

/** The figures of the POL-101 price test of the added line O2, as the engine's node states them. */
const PRICE_TEST_PARAMS = {
  price: "60000",
  ssp_version_key: "US-LIST@v1",
  low: "69750",
  high: "85250",
};

/**
 * 04 §16.14 rev 1.250 `price_tests` of this world, as measured through the routes on K-02: the
 * engine compares the price with the range while `priced_at_ssp` is unanswered or answered false
 * (`below_range`), and passes on the preparer's answer of true without comparing (`attested`), the
 * figures staying the same.
 */
export function priceTests(pricedAtSsp: unknown): NonNullable<Modification["price_tests"]> {
  const attested = pricedAtSsp === true;
  return {
    O2: {
      value: attested,
      reason_key: `modifications.prefill.priced_at_ssp.${attested ? "attested" : "below_range"}`,
      params: PRICE_TEST_PARAMS,
    },
  };
}

/** The draft once it is classified and every answer is confirmed. */
export function classifiedRow(overrides: Partial<Modification> = {}): Modification {
  return modificationRow({
    questionnaire: CONFIRMED,
    proposed_treatments: PROSPECTIVE,
    chosen_treatments: PROSPECTIVE,
    treatment_summary: "PROSPECTIVE",
    ssp_basis: DEFAULT_BASIS,
    price_tests: priceTests(CONFIRMED.O2.priced_at_ssp),
    row_version: 4,
    ...overrides,
  });
}

/** The classified draft with the stored preview of its row version. */
export function previewedRow(overrides: Partial<Modification> = {}): Modification {
  return classifiedRow({
    impact_preview: PREVIEW,
    impact_preview_file_id: "3c3c3c3c-3c3c-4c3c-8c3c-3c3c3c3c3c3c",
    impact_preview_sha256: "e9ac7d5ea7aa".padEnd(64, "0"),
    impact_summary: { catch_up_total: money("0.00") },
    row_version: 5,
    ...overrides,
  });
}

/** API-S-Judgement of a record whose subject is the modification. */
export function judgementRecord(overrides: Partial<Judgement> = {}): Judgement {
  return {
    id: JUDGEMENT_ID,
    judgement_no: "JDG-000012",
    topic: "MODIFICATION_TREATMENT_OVERRIDE",
    status: "DRAFT",
    subject_type: "modification",
    subject_id: MODIFICATION_ID,
    contract_id: CONTRACT_ID,
    book: null,
    conclusion: "The added seats change the pricing of the remaining seats.",
    rationale: "The discount applies to the whole term.",
    alternatives_considered: null,
    codification_refs: [],
    questionnaire: null,
    content_sha256: null,
    approval_request_id: null,
    supersedes_id: null,
    reviewer: null,
    reviewed_at: null,
    created_by: MAYA_USER,
    created_at: "2026-09-16T09:30:00Z",
    updated_at: "2026-09-16T09:30:00Z",
    ...overrides,
  };
}

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};
}

/**
 * The row as `PATCH` answers it: an edit clears the stored preview, so its answer carries none.
 * `/submit`, `/withdraw` and `/discard` answer the row as `GET` does, with its retained preview (04
 * §16.14 rev 1.188, item MOD-ANSWER-PREVIEW-1).
 */
function answered(row: Modification): Modification {
  return { ...row, impact_preview: null, impact_summary: { catch_up_total: null } };
}

/**
 * 04 T-CON-06: the authored members whose column is nullable. `PATCH` clears one of them when it is
 * sent as null; null for another member leaves the stored value (04 §16.14 rev 1.188, item
 * MOD-PATCH-CLEAR-1).
 */
const CLEARABLE: ReadonlySet<string> = new Set([
  "reference",
  "price_change_amount",
  "noncash_consideration",
  "consideration_payable",
  "scope_605_35",
  "rationale",
  "judgement_record_id",
]);

export interface SentRequest {
  readonly method: string;
  /** The path after `/api/v1`. */
  readonly path: string;
  readonly body: unknown;
}

export interface ModificationWorld {
  /** The row as the API holds it now. */
  row: Modification;
  judgements: Judgement[];
  /** E-08 status of the row's approval request. */
  approvalStatus: Approval["status"];
  /** Every command the screen sent, in order. */
  readonly requests: SentRequest[];
  /** How often the row was read (`GET /modifications/{id}`). */
  rowReads: number;
  /** Answers a suite puts in place of the next 2xx of a command; null leaves the command as it is. */
  refuse: {
    classify: (() => Response) | null;
    preview: (() => Response) | null;
    submit: (() => Response) | null;
    patch: (() => Response) | null;
    discard: (() => Response) | null;
    judgementSubmit: (() => Response) | null;
    judgementDiscard: (() => Response) | null;
  };
  /** The state the preview job ends in. */
  previewEnds: Job["state"];
  /**
   * The latest postable period at the time of a preview run: the run computes its journal lines for
   * it and says so (`computed_period_key`; 04 API-S-ImpactSummary rev 1.210).
   */
  postablePeriod: string;
  /**
   * `/classify` reports the price test of the added line whatever the preparer answered, so its
   * `prefill_reasons` names an answer the row holds (an API that reports the test as a fact beside
   * the stored answer). Off, it names only a question without a stored answer.
   */
  priceTestAlways: boolean;
  /**
   * The estimates world whose versions may name this modification (04 T-CON-13 `modification_id`;
   * §16.14 rev 1.210). Every answer of the row then lists them as `linked_estimate_versions`; the
   * submission is refused while one is not approved (PRD ERR-87) and the discard while one waits for
   * approval (PRD ERR-83). Null: the row answers the member as it holds it.
   */
  estimates: EstimateWorld | null;
  /**
   * The reader of this world is not shown a stored preview (04 §16.10 rev 1.300 "Who reads a stored
   * preview"; measured through the routes, register index 276): while the row stores one, every
   * answer of the row carries `impact_preview` and `impact_preview_file_id` null and
   * `impact_preview_withheld` true; the hash and `impact_summary` stay. Off, the row is answered as
   * it is held.
   */
  previewWithheld: boolean;
  /** The commands sent to a path that ends with `suffix`. */
  readonly sent: (method: string, suffix: string) => readonly SentRequest[];
}

/** The estimate versions created inside the row, by element code and version number. */
function linkedVersions(world: ModificationWorld): LinkedVersion[] {
  if (world.estimates === null) {
    return [...(world.row.linked_estimate_versions ?? [])];
  }
  const found: LinkedVersion[] = [];
  for (const element of world.estimates.elements) {
    for (const version of world.estimates.versions.get(element.id) ?? []) {
      if (version.modification_id === world.row.id) {
        found.push({
          id: version.id,
          estimate_id: element.id,
          element_code: element.element_code,
          estimate_kind: element.estimate_kind,
          version_no: version.version_no,
          status: version.status,
          effective_date: version.effective_date,
        });
      }
    }
  }
  return found.sort(
    (left, right) =>
      left.element_code.localeCompare(right.element_code) || left.version_no - right.version_no,
  );
}

/**
 * A row as every route of one modification answers it: with its linked estimate versions, and
 * without its stored preview where the reader of the world is not shown one.
 */
function withLinked(world: ModificationWorld, row: Modification = world.row): Modification {
  const answer = { ...row, linked_estimate_versions: linkedVersions(world) };
  return world.previewWithheld && row.impact_preview !== null
    ? {
        ...answer,
        impact_preview: null,
        impact_preview_file_id: null,
        impact_preview_withheld: true,
      }
    : answer;
}

/**
 * The sentence of a discard the API refuses because the record is neither a draft nor rejected (04
 * API-R-33 rev 1.296; measured on the API, register index 274).
 */
export const NOT_DISCARDABLE = "Only a draft or rejected judgement record can be discarded.";

/**
 * 409 `invalid-transition` of `POST /judgements/{id}/discard` on a record that waits for review, is
 * reviewed, superseded or discarded already — the body as the route answers it.
 */
export function notDiscardable(): Response {
  return problemResponse("invalid-transition", 409, "Action not available in this state", {
    code: null,
    detail: NOT_DISCARDABLE,
    errors: [
      { field: "status", message: NOT_DISCARDABLE, row: null, rule_id: "DB-03", sheet: null },
    ],
  });
}

/**
 * PRD ERR-95: 409 `invalid-transition` under SM-03 of `/submit`, one entry without a field per
 * judgement record of the modification that is a draft or waits for review.
 */
export function recordsNotReviewed(numbers: readonly string[]): Response {
  return problemResponse("invalid-transition", 409, "Action not available in this state", {
    errors: numbers.map((number) => ({
      field: null,
      rule_id: "SM-03",
      message: `Judgement record ${number} of this modification is not reviewed. It is reviewed, or discarded, before the modification is submitted.`,
    })),
  });
}

/** PRD ERR-83, ERR-87: 409 `invalid-transition` under SM-03, one entry per linked version held. */
function linkedRefusal(
  world: ModificationWorld,
  statuses: readonly string[],
  message: (version: LinkedVersion) => string,
): Response | null {
  const held = linkedVersions(world).filter((item) => statuses.includes(item.status));
  return held.length === 0
    ? null
    : problemResponse("invalid-transition", 409, "Action not available in this state", {
        errors: held.map((item) => ({ field: null, rule_id: "SM-03", message: message(item) })),
      });
}

function approval(world: ModificationWorld): Approval {
  const status = world.approvalStatus;
  const voided = status === "VOIDED";
  const approved = status === "APPROVED";
  // A rejection closes the step it was decided at and skips the steps that waited behind it
  // (`approvals.engine._advance`): the request then reads REJECTED and stays closed.
  const rejected = status === "REJECTED";
  const stepStatus = (pending: "ACTIVE" | "WAITING") =>
    status === "PENDING"
      ? pending
      : approved
        ? "APPROVED"
        : rejected
          ? pending === "ACTIVE"
            ? "REJECTED"
            : "SKIPPED"
          : "VOIDED";
  const decision = (
    id: string,
    at: string,
    comment: string,
    kind: "APPROVE" | "REJECT" = "APPROVE",
  ) => ({
    id,
    decision: kind,
    approver: PRIYA_USER,
    on_behalf_of: null,
    comment,
    reason_code: null,
    auto_rule_key: null,
    decided_at: at,
  });
  return {
    id: APPROVAL_ID,
    request_no: "APR-000434",
    status,
    summary: `Approve modification ${world.row.modification_no} of ${K02}`,
    subject: {
      type: "MODIFICATION",
      id: MODIFICATION_ID,
      display: REFERENCE,
      href: `/contracts/${CONTRACT_ID}/modifications/${MODIFICATION_ID}`,
      row_version: world.row.row_version,
      content_sha256: "a4cb2b0cbd66".padEnd(64, "0"),
    },
    entity: AVM_US,
    // One entity names the request (04 API-S-Approval since revision 0086: `entities`,
    // `entity_count`, `all_entities`; supervisor ruling R-25).
    entities: [AVM_US],
    entity_count: 1,
    all_entities: false,
    amount: money("60000.00"),
    flags: [],
    attachments: [],
    impact_preview: null,
    preparer: MAYA_USER,
    routing: { rule_key: null, rule_set_version_id: null },
    can_decide: false,
    content_withheld: false,
    reason_code: null,
    comment: null,
    current_step_no: 1,
    submitted_at: "2026-09-16T10:00:00Z",
    decided_at: approved || rejected ? "2026-09-17T09:15:00Z" : null,
    // The approvals engine closes a stale request as VOIDED and a withdrawn one as WITHDRAWN, each
    // with its reason (04 T-PLT-17).
    void_reason: voided ? "STALE_SUBJECT" : status === "WITHDRAWN" ? "WITHDRAWN_BY_PREPARER" : null,
    voided_at: voided || status === "WITHDRAWN" ? "2026-09-16T10:30:00Z" : null,
    steps: [
      {
        step_no: 1,
        name: "Revenue review",
        required_permission: "modification.approve",
        min_approvers: 1,
        status: stepStatus("ACTIVE"),
        decisions: approved
          ? [
              decision(
                "5e5e5e5e-5e5e-4e5e-8e5e-5e5e5e5e5e5e",
                "2026-09-17T09:15:00Z",
                "Agrees with the change order.",
              ),
            ]
          : rejected
            ? [
                decision(
                  "5f5f5f5f-5f5f-4f5f-8f5f-5f5f5f5f5f5f",
                  "2026-09-17T09:15:00Z",
                  REJECTION_COMMENT,
                  "REJECT",
                ),
              ]
            : [],
      },
      {
        step_no: 2,
        name: "Controller approval",
        required_permission: "modification.approve",
        min_approvers: 1,
        status: stepStatus("WAITING"),
        decisions: [],
      },
    ],
  };
}

function job(id: string, state: Job["state"]): Job {
  const ended = state !== "QUEUED" && state !== "RUNNING";
  return {
    id,
    kind: "CONTRACT_COMPUTE",
    state,
    progress: { done: ended ? 1 : 0, total: 1 },
    problem:
      state === "FAILED"
        ? {
            type: "https://erev.dev/problems/engine-error",
            title: "The computation failed",
            status: 500,
            detail: null,
            instance: null,
            errors: [],
          }
        : null,
    result: null,
    created_by: MAYA_USER,
    created_at: "2026-09-16T09:40:00Z",
    started_at: "2026-09-16T09:40:01Z",
    finished_at: ended ? "2026-09-16T09:40:04Z" : null,
  } as Job;
}

/** `/classify` as 04 §16.14 states it, for the two obligations of this world. */
function classify(world: ModificationWorld): Modification {
  const stored = record(world.row.questionnaire);
  const added = record(stored.O2);
  const separate = added.priced_at_ssp === true;
  const proposed: Record<string, string> = separate
    ? { O2: "SEPARATE_CONTRACT" }
    : { ...PROSPECTIVE };
  // A stored choice stays; the proposal fills in where the preparer chose nothing.
  const chosen = { ...proposed, ...world.row.chosen_treatments };
  const authored = Object.fromEntries(
    Object.entries(record(world.row.ssp_basis)).filter(
      ([, entry]) => record(entry).is_override === true,
    ),
  );
  world.row = {
    ...world.row,
    proposed_treatments: proposed,
    chosen_treatments: Object.fromEntries(
      Object.entries(chosen).sort(([left], [right]) => left.localeCompare(right)),
    ),
    treatment_summary: separate ? "SEPARATE_CONTRACT" : "PROSPECTIVE",
    ssp_basis: { ...DEFAULT_BASIS, ...authored },
    impact_preview: null,
    impact_preview_file_id: null,
    impact_preview_sha256: null,
    impact_summary: { catch_up_total: null },
    row_version: world.row.row_version + 1,
  };
  // The prefill: only a question without a stored answer, unless the world reports the price test
  // beside a stored answer too. The stored answer stays in `questionnaire` either way.
  const reasons: Record<string, Record<string, unknown>> = {};
  const propose = (
    key: string,
    question: string,
    value: boolean,
    reason: string,
    params = {},
    whateverIsStored = false,
  ) => {
    if (whateverIsStored || typeof record(stored[key])[question] !== "boolean") {
      reasons[key] = {
        ...reasons[key],
        [question]: {
          value,
          reason_key: `modifications.prefill.${question}.${reason}`,
          params,
        },
      };
    }
  };
  propose("O2", "added_goods_distinct", true, "new_distinct");
  propose("O2", "priced_at_ssp", false, "below_range", PRICE_TEST_PARAMS, world.priceTestAlways);
  if (!separate) {
    propose("O1", "remaining_goods_distinct_from_transferred", true, "series", {
      progress: "0.354794520547945205",
      progress_measure: "TIME_ELAPSED",
    });
  }
  const merged: Record<string, unknown> = { ...stored };
  for (const [key, questions] of Object.entries(reasons)) {
    const answers = { ...record(merged[key]) };
    for (const [question, item] of Object.entries(questions)) {
      answers[question] ??= record(item).value;
    }
    merged[key] = answers;
  }
  // 04 T-CON-06 `classification` (rev 1.210, rev 1.250, rev 1.286): the proposals of the
  // obligations, the engine's detail and the price tests are kept on the row, each a member of
  // its own, so every later answer of it carries them until an edit clears them. The prefilled
  // answers beside the stored ones are this answer's alone.
  world.row = {
    ...world.row,
    prefill_reasons: reasons,
    proposal_detail: { "class[O1]": "D", "class[O2]": "D", "ssp_version[O2]": "US-LIST@v1" },
    price_tests: priceTests(added.priced_at_ssp),
  };
  return { ...world.row, questionnaire: merged };
}

/**
 * The calendar of the entity once October has opened: September is closing and October is the latest
 * postable period. Register after `serveWorkbench`, whose calendar holds September alone.
 */
export function serveOctoberOpen(): void {
  server.use(
    http.get(apiUrl("/api/v1/periods"), () =>
      HttpResponse.json({
        items: [
          { ...PERIOD, state: "closing" },
          {
            period: {
              ...PERIOD.period,
              id: "2d3e4f5a-6b7c-4d8e-9f0a-1b2c3d4e5f6a",
              period_key: "FY2026-P10",
              name: "Oct 2026",
              period_no: 10,
              quarter_no: 4,
              start_date: "2026-10-01",
              end_date: "2026-10-31",
            },
            state: "open",
            is_first_open: false,
          },
        ],
        next_cursor: null,
      }),
    ),
  );
}

/**
 * Serves the modification routes and the reads of the wizard beside the workbench world
 * (`serveWorkbench` comes first). The world starts with `row`.
 */
export function serveModification(
  row: Modification,
  judgements: readonly Judgement[] = [],
): ModificationWorld {
  const requests: SentRequest[] = [];
  const world: ModificationWorld = {
    row,
    judgements: [...judgements],
    approvalStatus: "PENDING",
    requests,
    rowReads: 0,
    refuse: {
      classify: null,
      preview: null,
      submit: null,
      patch: null,
      discard: null,
      judgementSubmit: null,
      judgementDiscard: null,
    },
    previewEnds: "SUCCEEDED",
    postablePeriod: "FY2026-P09",
    priceTestAlways: false,
    estimates: null,
    previewWithheld: false,
    sent: (method, suffix) =>
      requests.filter((item) => item.method === method && item.path.endsWith(suffix)),
  };
  const log = async (request: Request): Promise<unknown> => {
    const text = await request.text();
    const body: unknown = text === "" ? null : JSON.parse(text);
    requests.push({
      method: request.method,
      path: new URL(request.url).pathname.replace("/api/v1", ""),
      body,
    });
    return body;
  };
  const base = `/api/v1/modifications/${MODIFICATION_ID}`;
  // The preview jobs whose run has stored its preview: a run stores once.
  const stored = new Set<string>();
  const version = (id: string, label: string, versionNo: number) => ({
    id,
    ssp_book_id: SSP_BOOK_ID,
    version_no: versionNo,
    status: "APPROVED",
    legacy_version_label: label,
    methodology_label: "List price",
    is_methodology_change: false,
    entry_count: 12,
    effective_from_date: "2026-01-01",
    effective_to_date: null,
    published_at: "2026-01-01T00:00:00Z",
    approval_request_id: null,
    content_sha256: null,
    diff_summary: null,
    ssp_calculator_run_id: null,
    study_attachment_ids: [],
    created_by: MAYA_USER,
    row_version: 2,
    created_at: "2025-12-15T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  });
  const versions = [
    version(OTHER_SSP_VERSION_ID, "2026-H2", 2),
    version(SSP_VERSION_ID, "2026-H1", 1),
  ];
  const book = {
    id: SSP_BOOK_ID,
    code: "US-LIST",
    name: "US list prices",
    description: null,
    currency: "USD",
    entity_code: null,
    channel: null,
    segment: null,
    resolution_mode: "EFFECTIVE_DATE",
    current_version: null,
    draft_version_id: null,
    row_version: 1,
    created_at: "2025-12-01T00:00:00Z",
    updated_at: "2025-12-01T00:00:00Z",
  };

  server.use(
    http.get(apiUrl(base), () => {
      world.rowReads += 1;
      return HttpResponse.json(withLinked(world));
    }),
    http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/modifications`), async ({ request }) => {
      const body = record(await log(request));
      world.row = modificationRow({
        ...(body as Partial<Modification>),
        lines: (body.lines as Modification["lines"] | undefined) ?? [],
        price_change_amount: (body.price_change_amount as string | undefined) ?? null,
        reference: (body.reference as string | undefined) ?? null,
        rationale: (body.rationale as string | undefined) ?? null,
      });
      return HttpResponse.json(world.row, { status: 201, headers: { ETag: '"r1"' } });
    }),
    http.patch(apiUrl(base), async ({ request }) => {
      const body = record(await log(request));
      if (world.refuse.patch !== null) {
        return world.refuse.patch();
      }
      const submitted = world.row.status === "SUBMITTED";
      // An edit of a rejected row returns it to Draft as well ("Revise"; 04 §16.14 rev 1.236): its
      // request was decided and stays REJECTED, where the pending request of a submitted row is
      // voided.
      const returned = submitted || world.row.status === "REJECTED";
      if (submitted) {
        world.approvalStatus = "VOIDED";
      }
      // A member that is not sent stays as it is; so does one sent as null, unless its column is
      // nullable: that one is cleared (04 API-R-31; §16.14 rev 1.188).
      const authored = Object.fromEntries(
        Object.entries(body).filter(([name, value]) => value !== null || CLEARABLE.has(name)),
      ) as Partial<Modification>;
      world.row = {
        ...world.row,
        ...authored,
        status: "DRAFT",
        proposed_treatments: {},
        // 04 T-CON-06 `classification`: an edit clears what the classification answered.
        prefill_reasons: {},
        proposal_detail: {},
        price_tests: {},
        treatment_summary: null,
        impact_preview: null,
        impact_preview_file_id: null,
        impact_preview_sha256: null,
        impact_summary: { catch_up_total: null },
        content_sha256: null,
        row_version: world.row.row_version + (returned ? 2 : 1),
      };
      return HttpResponse.json(withLinked(world, answered(world.row)));
    }),
    http.post(apiUrl(`${base}/classify`), async ({ request }) => {
      await log(request);
      if (world.refuse.classify !== null) {
        return world.refuse.classify();
      }
      return HttpResponse.json(withLinked(world, classify(world)));
    }),
    http.post(apiUrl(`${base}/preview`), async ({ request }) => {
      await log(request);
      if (world.refuse.preview !== null) {
        return world.refuse.preview();
      }
      // Every run is a job of its own.
      const id = `${JOB_ID.slice(0, -1)}${String(world.sent("POST", "/preview").length)}`;
      return HttpResponse.json(job(id, "QUEUED"), {
        status: 202,
        headers: { Location: `/api/v1/jobs/${id}` },
      });
    }),
    http.get(apiUrl("/api/v1/jobs/:jobId"), ({ params }) => {
      // The job of another stand-in (the preview of an estimate version) is answered by its world.
      if (!String(params.jobId).startsWith(JOB_ID.slice(0, -1))) {
        return undefined;
      }
      // The run stores the preview on the row, in place of an earlier one, and moves its version;
      // its journal lines are computed for the latest postable period of that moment.
      const id = String(params.jobId);
      if (world.previewEnds === "SUCCEEDED" && !stored.has(id)) {
        stored.add(id);
        world.row = {
          ...world.row,
          impact_preview: { ...PREVIEW, computed_period_key: world.postablePeriod },
          impact_preview_file_id: "3c3c3c3c-3c3c-4c3c-8c3c-3c3c3c3c3c3c",
          impact_preview_sha256: "e9ac7d5ea7aa".padEnd(64, "0"),
          impact_summary: { catch_up_total: money("0.00") },
          row_version: world.row.row_version + 1,
        };
      }
      return HttpResponse.json(job(String(params.jobId), world.previewEnds));
    }),
    http.post(apiUrl(`${base}/submit`), async ({ request }) => {
      await log(request);
      if (world.refuse.submit !== null) {
        return world.refuse.submit();
      }
      // PRD ERR-87: the linked versions are approved first; a discarded one is not counted.
      const unapproved = linkedRefusal(
        world,
        ["DRAFT", "SUBMITTED", "REJECTED", "WITHDRAWN"],
        (item) =>
          `Estimate version ${item.element_code} v${String(item.version_no)} of this modification is not approved. It is approved before the modification is submitted.`,
      );
      if (unapproved !== null) {
        return unapproved;
      }
      world.approvalStatus = "PENDING";
      world.row = {
        ...world.row,
        status: "SUBMITTED",
        approval_request_id: APPROVAL_ID,
        content_sha256: "a4cb2b0cbd66".padEnd(64, "0"),
        row_version: world.row.row_version + 2,
      };
      return HttpResponse.json(withLinked(world));
    }),
    http.post(apiUrl(`${base}/withdraw`), async ({ request }) => {
      await log(request);
      world.approvalStatus = "WITHDRAWN";
      world.row = { ...world.row, status: "DRAFT", row_version: world.row.row_version + 1 };
      return HttpResponse.json(withLinked(world));
    }),
    http.post(apiUrl(`${base}/discard`), async ({ request }) => {
      await log(request);
      if (world.refuse.discard !== null) {
        return world.refuse.discard();
      }
      // PRD ERR-83: a linked version that waits for approval holds the discard.
      const waiting = linkedRefusal(
        world,
        ["SUBMITTED"],
        (item) =>
          `Estimate version ${item.element_code} v${String(item.version_no)} of this modification is waiting for approval. Its preparer withdraws it first.`,
      );
      if (waiting !== null) {
        return waiting;
      }
      // PRD SM-03 `DRAFT` → `VOIDED`: nothing else is written.
      world.row = { ...world.row, status: "VOIDED", row_version: world.row.row_version + 1 };
      return HttpResponse.json(withLinked(world));
    }),
    http.get(apiUrl(`/api/v1/approvals/${APPROVAL_ID}`), () => HttpResponse.json(approval(world))),
    http.get(apiUrl("/api/v1/judgements"), ({ request }) => {
      const subject = new URL(request.url).searchParams.get("subject_type");
      return HttpResponse.json({
        items: subject === "modification" ? world.judgements : [],
        next_cursor: null,
      });
    }),
    http.post(apiUrl("/api/v1/judgements"), async ({ request }) => {
      const body = record(await log(request));
      const created = judgementRecord({ ...(body as Partial<Judgement>), status: "DRAFT" });
      world.judgements = [created, ...world.judgements];
      return HttpResponse.json(created, { status: 201 });
    }),
    http.patch(apiUrl(`/api/v1/judgements/${JUDGEMENT_ID}`), async ({ request }) => {
      const body = record(await log(request));
      world.judgements = world.judgements.map((item) =>
        item.id === JUDGEMENT_ID ? { ...item, ...(body as Partial<Judgement>) } : item,
      );
      return HttpResponse.json(world.judgements.find((item) => item.id === JUDGEMENT_ID));
    }),
    http.post(apiUrl(`/api/v1/judgements/${JUDGEMENT_ID}/submit`), async ({ request }) => {
      await log(request);
      if (world.refuse.judgementSubmit !== null) {
        return world.refuse.judgementSubmit();
      }
      world.judgements = world.judgements.map((item) =>
        item.id === JUDGEMENT_ID ? { ...item, status: "SUBMITTED" } : item,
      );
      return HttpResponse.json(world.judgements.find((item) => item.id === JUDGEMENT_ID));
    }),
    // 04 API-R-33 `POST /judgements/{id}/discard` (rev 1.242, rev 1.296; PRD SM-10 `DRAFT` →
    // `VOIDED` and, rev 1.199, `REJECTED` → `VOIDED`): a draft or a rejected record is voided and
    // keeps its number; a record in any other status is refused (409).
    http.post(apiUrl("/api/v1/judgements/:judgementId/discard"), async ({ request, params }) => {
      await log(request);
      if (world.refuse.judgementDiscard !== null) {
        return world.refuse.judgementDiscard();
      }
      const found = world.judgements.find((item) => item.id === params.judgementId);
      if (found === undefined || (found.status !== "DRAFT" && found.status !== "REJECTED")) {
        return notDiscardable();
      }
      world.judgements = world.judgements.map((item) =>
        item.id === found.id ? { ...item, status: "VOIDED" } : item,
      );
      return HttpResponse.json({ ...found, status: "VOIDED" });
    }),
    http.get(apiUrl("/api/v1/products"), () =>
      HttpResponse.json({
        items: [
          {
            id: "8f90a1b2-c3d4-4e5f-9a6b-7c8d9e0f1a2b",
            code: "AVM-SEAT-MO",
            name: "Avenmoor seat, monthly",
            is_active: true,
            is_bundle: false,
          },
          {
            id: "8f90a1b2-c3d4-4e5f-9a6b-7c8d9e0f1a2c",
            code: "AVM-IMPL-PLUS",
            name: "Implementation Plus",
            is_active: true,
            is_bundle: false,
          },
        ],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/events`), () =>
      HttpResponse.json({
        items: [
          {
            id: "4d4d4d4d-4d4d-4d4d-8d4d-4d4d4d4d4d4d",
            contract_id: CONTRACT_ID,
            event_type: "BILLING_RECORDED",
            effective_date: "2026-09-20",
            recorded_at: "2026-09-20T08:00:00Z",
            stream_version: 5,
            record_seq: 5,
            obligation_keys: ["O1"],
            payload: {},
            is_manual: false,
            created_by: MAYA_USER,
          },
        ],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/policies/resolve"), ({ request }) =>
      HttpResponse.json({
        key: new URL(request.url).searchParams.get("key"),
        value: "ENGINE_PROPOSES_PREPARER_CONFIRMS",
        level: "FRAMEWORK_DEFAULT",
        is_forced: false,
        known_at: "2026-09-16T09:00:00Z",
        source: { id: null, type: "REGISTRY" },
        chain: [],
      }),
    ),
    http.get(apiUrl("/api/v1/ssp-books"), () =>
      HttpResponse.json({ items: [book], next_cursor: null }),
    ),
    http.get(apiUrl(`/api/v1/ssp-books/${SSP_BOOK_ID}`), () => HttpResponse.json(book)),
    http.get(apiUrl(`/api/v1/ssp-books/${SSP_BOOK_ID}/versions`), () =>
      HttpResponse.json({ items: versions, next_cursor: null }),
    ),
    ...versions.map((item) =>
      http.get(apiUrl(`/api/v1/ssp-book-versions/${item.id}`), () => HttpResponse.json(item)),
    ),
  );
  return world;
}

/** A 422 `validation-failed` as `/submit` answers a departure without a reviewed record. */
export function overrideRefusal() {
  return problemResponse("validation-failed", 422, "The request is not valid", {
    detail: "1 field is not valid.",
    errors: [
      {
        field: "chosen_treatments.O1",
        rule_id: "REQ-MOD-002",
        message:
          "The chosen treatment of O1 differs from the proposal; link a reviewed judgement record of topic MODIFICATION_TREATMENT_OVERRIDE.",
      },
    ],
  });
}
