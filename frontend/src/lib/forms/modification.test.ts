// Modification wizard models (BUILD_SPEC CTR-27; SCREENS §7.4 to §7.6; 04 API-R-31, T-CON-06; ENGINE_SPEC
// S06-R-19; PRD BR-MOD-01, REQ-MOD-002): the line a subscription action sends has the shape of its
// kind; the general form names what is wrong; an answer counts once it is stored; a departure is read
// as `/submit` reads it, and a save keeps the departures the preparer made and drops the defaults.
import { beforeAll, describe, expect, it } from "vitest";

import type { Modification } from "../api/queries/modifications";
import { registerCurrencies } from "../format";
import {
  authoredChoices,
  buildChange,
  buildSubscription,
  type ChangeContext,
  changeFromModification,
  changeLinePatch,
  confirmedAnswers,
  departures,
  emptyChange,
  emptyChangeLine,
  emptySubscription,
  firstOpenStep,
  nextKey,
  priceTestOf,
  questionGroups,
  questionnaireConfirmed,
  stepReachable,
  type SubscriptionAction,
  type SubscriptionForm,
  subscriptionActionOf,
  withAnswer,
  withGroupConfirmed,
  withoutGroup,
} from "./modification";

const CONTEXT: ChangeContext = {
  externalId: "SF-ORD-10002",
  currency: "USD",
  obligations: [{ key: "O1", productCode: "AVM-SEAT-MO", endDate: "2027-12-31" }],
};
const USD = (amount: string) => ({ amount, currency: "USD" });

beforeAll(() => {
  // The screens register the contract currency when they read the contract (DS-FMT-03).
  registerCurrencies([{ code: "USD", minor_unit: 2 }]);
});

function subscription(
  action: SubscriptionAction,
  overrides: Partial<SubscriptionForm> = {},
): SubscriptionForm {
  return {
    ...emptySubscription(action, CONTEXT.obligations),
    quantity: "50",
    price: "60,000.00",
    effectiveDate: "16 Sep 2026",
    reference: "CR-MARROWBY-2026-09",
    ...overrides,
  };
}

describe("a subscription action", () => {
  it("sends one line of the S06-R-19 shape of its kind", () => {
    const built = (action: SubscriptionAction, overrides: Partial<SubscriptionForm> = {}) =>
      buildSubscription(subscription(action, overrides), CONTEXT).body;

    // Upgrade and downgrade change the obligation for the remaining term; a reduction is negative.
    expect(built("upgrade")).toEqual({
      kind: "UPGRADE",
      reference: "CR-MARROWBY-2026-09",
      effective_date: "2026-09-16",
      lines: [
        {
          action: "CHANGE",
          obligation_key: "O1",
          quantity_delta: "50",
          consideration_delta: USD("60000.00"),
          start_date: "2026-09-16",
          end_date: "2027-12-31",
        },
      ],
    });
    expect(built("downgrade")?.lines).toEqual([
      {
        action: "CHANGE",
        obligation_key: "O1",
        quantity_delta: "-50",
        consideration_delta: USD("-60000.00"),
        start_date: "2026-09-16",
        end_date: "2027-12-31",
      },
    ]);
    // Co-term adds an obligation of the same product from the effective date to the end of the term.
    expect(built("co_term")).toMatchObject({
      kind: "CO_TERM",
      lines: [
        {
          action: "ADD",
          obligation_key: "O2",
          product_code: "AVM-SEAT-MO",
          quantity_delta: "50",
          start_date: "2026-09-16",
          end_date: "2027-12-31",
        },
      ],
    });
    // A renewal adds the term that starts the day after the obligation ends.
    for (const [action, kind] of [
      ["renew", "RENEWAL"],
      ["early_renew", "EARLY_RENEWAL"],
    ] as const) {
      expect(built(action, { endDate: "31 Dec 2028" })).toMatchObject({
        kind,
        lines: [
          { action: "ADD", obligation_key: "O2", start_date: "2028-01-01", end_date: "2028-12-31" },
        ],
      });
    }
    expect(built("cancel", { price: "" })).toMatchObject({
      kind: "CANCELLATION",
      lines: [
        {
          action: "REMOVE",
          obligation_key: "O1",
          quantity_delta: "-50",
          consideration_delta: USD("0"),
          start_date: "2026-09-16",
          end_date: "2027-12-31",
        },
      ],
    });
  });

  it("names what is missing or out of the term", () => {
    const errors = (action: SubscriptionAction, overrides: Partial<SubscriptionForm>) =>
      buildSubscription(subscription(action, overrides), CONTEXT).errors;

    expect(errors("co_term", { reference: " " })).toEqual({
      reference: "Enter a reference for this modification.",
    });
    expect(errors("co_term", { quantity: "" })).toEqual({
      quantity: "Enter the quantity this change adds.",
    });
    expect(errors("upgrade", { quantity: "", price: "" })).toEqual({
      quantity: "Enter a quantity or a price.",
    });
    expect(errors("downgrade", { quantity: "-5" })).toEqual({
      quantity: "Enter a quantity of zero or more.",
    });
    expect(errors("co_term", { newKey: "O1" })).toEqual({
      newKey: "Obligation O1 exists on this contract. Use a new key for an added obligation.",
    });
    // Every action but a renewal is effective within the term.
    expect(errors("upgrade", { effectiveDate: "01 Jan 2028" })).toEqual({
      effectiveDate: "Enter an effective date on or before 31 Dec 2027, the end of the term.",
    });
    expect(errors("renew", { effectiveDate: "01 Jan 2028", endDate: "" })).toEqual({
      endDate: "Enter the end date of the renewal term.",
    });
    expect(errors("renew", { endDate: "31 Dec 2027" })).toEqual({
      endDate: "Enter an end date on or after 01 Jan 2028.",
    });
    expect(
      buildSubscription(subscription("cancel", { obligationKey: null }), CONTEXT).errors,
    ).toEqual({ obligationKey: "Select an obligation." });
    expect(
      buildSubscription(subscription("cancel"), {
        ...CONTEXT,
        obligations: [{ key: "O1", productCode: "AVM-SEAT-MO", endDate: null }],
      }).errors,
    ).toEqual({
      obligationKey: "Obligation O1 has no end date, so this change cannot be dated.",
    });
  });

  it("reads the action of the link and proposes the next free key", () => {
    expect(subscriptionActionOf("early_renew")).toBe("early_renew");
    expect(subscriptionActionOf("merge")).toBeNull();
    expect(subscriptionActionOf(null)).toBeNull();
    expect(
      nextKey([
        { key: "O1", productCode: "A", endDate: null },
        { key: "O7", productCode: "B", endDate: null },
        { key: "SETUP", productCode: "C", endDate: null },
      ]),
    ).toBe("O8");
    // A contract with several obligations leaves the choice to the preparer.
    expect(emptySubscription("upgrade", []).obligationKey).toBeNull();
    expect(emptySubscription("upgrade", CONTEXT.obligations)).toMatchObject({
      obligationKey: "O1",
      newKey: "",
    });
  });
});

describe("the general form", () => {
  it("names the kind, the reference, the date and what is wrong on each line", () => {
    const form = {
      ...emptyChange("l1"),
      lines: [
        { ...emptyChangeLine("l1"), action: "ADD" as const, obligationKey: "O1" },
        { ...emptyChangeLine("l2"), action: "CHANGE" as const, obligationKey: "O9" },
        { ...emptyChangeLine("l3"), obligationKey: " ", quantityChange: "ten" },
      ],
    };
    const { body, errors } = buildChange(form, CONTEXT);

    expect(body).toBeNull();
    expect(errors).toEqual({
      kind: "Select the kind of modification.",
      reference: "Enter a reference for this modification.",
      effectiveDate: "Enter the effective date.",
      "line-l1-obligationKey":
        "Obligation O1 exists on this contract. Use a new key for an added obligation.",
      "line-l1-product": "Select the product of the added obligation.",
      "line-l2-obligationKey": "SF-ORD-10002 has no obligation O9.",
      "line-l3-action": "Select an action.",
      "line-l3-obligationKey": "Enter an obligation key.",
      "line-l3-quantityChange": "Enter a quantity such as 50 or -50.",
    });
    expect(buildChange({ ...emptyChange("l1"), lines: [] }, CONTEXT).errors.lines).toBe(
      "Add at least one line or a price change.",
    );
  });

  it("posts the lines with decimal strings and business dates", () => {
    const { body, errors } = buildChange(
      {
        kind: "ADD_OBLIGATION",
        reference: " CR-7 ",
        effectiveDate: "16 Sep 2026",
        rationale: " Fifty more seats. ",
        priceObligationKey: null,
        priceChangeAmount: "",
        lines: [
          {
            ...emptyChangeLine("l1"),
            action: "ADD",
            obligationKey: "O2",
            productCode: "AVM-SEAT-MO",
            quantityChange: "50",
            considerationChange: "60,000.00",
            startDate: "16 Sep 2026",
            endDate: "31 Dec 2027",
            memo1: " change order 7 ",
          },
          { ...emptyChangeLine("l2"), action: "REMOVE", obligationKey: "O1" },
        ],
      },
      CONTEXT,
    );

    expect(errors).toEqual({});
    expect(body).toMatchObject({
      kind: "ADD_OBLIGATION",
      reference: "CR-7",
      effective_date: "2026-09-16",
      rationale: "Fifty more seats.",
      lines: [
        {
          action: "ADD",
          obligation_key: "O2",
          product_code: "AVM-SEAT-MO",
          quantity_delta: "50",
          consideration_delta: USD("60000.00"),
          start_date: "2026-09-16",
          end_date: "2027-12-31",
          memo_1: "change order 7",
        },
        // A line without a quantity or an amount: quantity 0, no consideration.
        {
          action: "REMOVE",
          obligation_key: "O1",
          product_code: null,
          quantity_delta: "0",
          consideration_delta: null,
        },
      ],
    });
    expect(body).not.toHaveProperty("price_change_amount");
  });

  it("only an added line names a product, and a stored draft reads back as it was typed", () => {
    expect(changeLinePatch("action", "REMOVE")).toEqual({ action: "REMOVE", productCode: null });
    expect(changeLinePatch("action", "ADD")).toEqual({ action: "ADD" });

    const stored = {
      kind: "PRICE_CHANGE",
      reference: "CR-8",
      effective_date: "2026-10-01",
      rationale: null,
      currency: "USD",
      price_change_amount: "12000.00",
      lines: [
        {
          action: "CHANGE",
          obligation_key: "O1",
          quantity_delta: "0",
          consideration_delta: USD("12000.00"),
          start_date: null,
          end_date: null,
        },
      ],
    } satisfies Pick<
      Modification,
      | "kind"
      | "reference"
      | "effective_date"
      | "rationale"
      | "lines"
      | "price_change_amount"
      | "currency"
    >;
    const form = changeFromModification(stored, (index) => `l${String(index + 1)}`);
    expect(form).toMatchObject({
      kind: "PRICE_CHANGE",
      reference: "CR-8",
      effectiveDate: "01 Oct 2026",
      priceObligationKey: "O1",
      priceChangeAmount: "12,000.00",
    });
    // The form answers the body the row was stored from.
    expect(buildChange(form, CONTEXT).body).toEqual({
      kind: "PRICE_CHANGE",
      reference: "CR-8",
      effective_date: "2026-10-01",
      rationale: null,
      lines: [
        {
          action: "CHANGE",
          obligation_key: "O1",
          quantity_delta: "0",
          consideration_delta: USD("12000.00"),
        },
      ],
      price_change_amount: "12000.00",
    });
  });
});

describe("the questionnaire", () => {
  const LINES = [{ action: "ADD", obligation_key: "O2" }];
  const PROPOSED = { O1: "PROSPECTIVE", O2: "PROSPECTIVE" };
  // 04 §16.14 rev 1.286: every key of `prefill_reasons` is an obligation key.
  const REASONS = {
    O1: {
      remaining_goods_distinct_from_transferred: {
        value: true,
        reason_key: "modifications.prefill.remaining_goods_distinct_from_transferred.series",
        params: { progress: "0.35", progress_measure: "TIME_ELAPSED" },
      },
    },
    O2: {
      priced_at_ssp: {
        value: false,
        reason_key: "modifications.prefill.priced_at_ssp.below_range",
        params: { price: "60000", low: "69750", high: "85250" },
      },
    },
  };

  it("asks each obligation what applies to it and counts an answer once it is stored", () => {
    const groups = questionGroups(
      {
        lines: LINES,
        questionnaire: { O2: { added_goods_distinct: true } },
        proposed_treatments: PROPOSED,
      },
      REASONS,
    );

    // The added line first with its two questions; the existing obligation with the third.
    expect(groups.map((group) => [group.obligationKey, group.added, group.confirmed])).toEqual([
      ["O2", true, false],
      ["O1", false, false],
    ]);
    expect(groups[0]?.questions).toEqual([
      {
        question: "added_goods_distinct",
        value: true,
        stored: true,
        prefill: null,
        priceTest: null,
      },
      {
        question: "priced_at_ssp",
        value: false,
        stored: false,
        prefill: {
          value: false,
          reasonKey: "modifications.prefill.priced_at_ssp.below_range",
          params: { price: "60000", low: "69750", high: "85250" },
        },
        // The row states no price test (04 §16.14 rev 1.250 `price_tests`).
        priceTest: null,
      },
    ]);
    expect(groups[1]?.questions.map((item) => [item.question, item.value, item.stored])).toEqual([
      ["remaining_goods_distinct_from_transferred", true, false],
    ]);
    expect(questionnaireConfirmed(groups)).toBe(false);
    expect(confirmedAnswers(groups)).toBe(1);
  });

  it("the price test of the row stands beside the price question alone, whatever is stored, and is no proposal", () => {
    // 04 §16.14 rev 1.250: the engine's price test of an added line is a member of its own.
    const attested = {
      value: true,
      reason_key: "modifications.prefill.priced_at_ssp.attested",
      params: { price: "60000", ssp_version_key: "US-LIST@v1", low: "69750", high: "85250" },
    };
    const row = {
      lines: LINES,
      questionnaire: {
        O1: { remaining_goods_distinct_from_transferred: true },
        O2: { added_goods_distinct: true, priced_at_ssp: true },
      },
      proposed_treatments: PROPOSED,
      price_tests: { O2: attested, O1: attested },
    };
    const groups = questionGroups(row, {});

    const fact = {
      value: true,
      reasonKey: "modifications.prefill.priced_at_ssp.attested",
      params: attested.params,
    };
    expect(
      groups.flatMap((group) =>
        group.questions.map((item) => [group.obligationKey, item.question, item.priceTest]),
      ),
    ).toEqual([
      ["O2", "added_goods_distinct", null],
      ["O2", "priced_at_ssp", fact],
      ["O1", "remaining_goods_distinct_from_transferred", null],
    ]);
    // A fact changes nothing of what is stored, proposed or confirmed.
    expect(groups.every((group) => group.questions.every((item) => item.prefill === null))).toBe(
      true,
    );
    expect(questionnaireConfirmed(groups)).toBe(true);
    expect(priceTestOf(row, "O2")).toEqual(fact);
    // No entry: a row that is not classified or was edited since, a line the engine does not test.
    expect(priceTestOf({ price_tests: {} }, "O2")).toBeNull();
    expect(priceTestOf({}, "O2")).toBeNull();
    expect(priceTestOf({ price_tests: { O2: { value: true } } }, "O2")).toBeNull();
  });

  it("an existing obligation the classification proposes nothing for is not asked", () => {
    const groups = questionGroups(
      { lines: LINES, questionnaire: {}, proposed_treatments: PROPOSED },
      {},
    );

    // The added line is always asked; without a proposal its answers are the preparer's to give.
    expect(groups.map((group) => group.obligationKey)).toEqual(["O2"]);
    expect(groups[0]?.questions.map((item) => item.value)).toEqual([null, null]);
  });

  it("an obligation keyed like a member of the classification is asked as any other", () => {
    // 04 T-CON-06 `classification` rev 1.286: an obligation key is free text. `proposal` was the
    // member of `prefill_reasons` that held the engine's detail; an added line of that name now
    // reads its own two proposals, and its price test under the same key.
    const tested = {
      value: false,
      reason_key: "modifications.prefill.priced_at_ssp.below_range",
      params: { price: "60000", low: "69750", high: "85250" },
    };
    const groups = questionGroups(
      {
        lines: [{ action: "ADD", obligation_key: "proposal" }],
        questionnaire: {},
        proposed_treatments: { O1: "PROSPECTIVE", proposal: "PROSPECTIVE" },
        price_tests: { proposal: tested },
      },
      {
        proposal: {
          added_goods_distinct: {
            value: true,
            reason_key: "modifications.prefill.added_goods_distinct.new_distinct",
            params: {},
          },
          priced_at_ssp: tested,
        },
      },
    );

    expect(groups.map((group) => [group.obligationKey, group.added])).toEqual([["proposal", true]]);
    expect(
      groups[0]?.questions.map((item) => [
        item.question,
        item.value,
        item.prefill?.reasonKey ?? null,
        item.priceTest?.reasonKey ?? null,
      ]),
    ).toEqual([
      [
        "added_goods_distinct",
        true,
        "modifications.prefill.added_goods_distinct.new_distinct",
        null,
      ],
      [
        "priced_at_ssp",
        false,
        "modifications.prefill.priced_at_ssp.below_range",
        "modifications.prefill.priced_at_ssp.below_range",
      ],
    ]);
  });

  it("confirming, changing and reopening a group replace the stored member whole", () => {
    const [added] = questionGroups(
      { lines: LINES, questionnaire: {}, proposed_treatments: PROPOSED },
      {
        ...REASONS,
        O2: { ...REASONS.O2, added_goods_distinct: { value: true, reason_key: "k", params: {} } },
      },
    );
    if (added === undefined) {
      throw new Error("the added line has a group");
    }
    const stored = { O1: { remaining_goods_distinct_from_transferred: true } };

    const confirmed = withGroupConfirmed(stored, added);
    expect(confirmed).toEqual({
      ...stored,
      O2: { added_goods_distinct: true, priced_at_ssp: false },
    });
    expect(withAnswer(confirmed, "O2", "priced_at_ssp", true)).toEqual({
      ...stored,
      O2: { added_goods_distinct: true, priced_at_ssp: true },
    });
    // Reopened: the answers of the group go, so the system proposes them again.
    expect(withoutGroup(confirmed, added)).toEqual(stored);
    expect(
      questionnaireConfirmed(
        questionGroups(
          { lines: LINES, questionnaire: confirmed, proposed_treatments: PROPOSED },
          {},
        ),
      ),
    ).toBe(true);
  });
});

describe("treatments and steps", () => {
  const PROPOSED = { O1: "PROSPECTIVE", O2: "PROSPECTIVE" };

  it("reads a departure as /submit does", () => {
    expect(departures(PROPOSED, PROPOSED)).toEqual([]);
    expect(departures(PROPOSED, { O1: "CUMULATIVE_CATCH_UP", O2: "PROSPECTIVE" })).toEqual(["O1"]);
    // A chosen key the proposal no longer holds departs too (REQ-MOD-002).
    expect(departures({ O2: "SEPARATE_CONTRACT" }, { ...PROPOSED })).toEqual(["O1", "O2"]);
    // A row without a proposal has none to depart from.
    expect(departures({}, PROPOSED)).toEqual([]);
  });

  it("a save keeps the departures the preparer made and drops the defaults", () => {
    const row = {
      proposed_treatments: PROPOSED,
      chosen_treatments: { O1: "CUMULATIVE_CATCH_UP", O2: "PROSPECTIVE", O3: "MIXED" },
    };

    // O2 is the default of the classification; O3 is of a line that is gone.
    expect(authoredChoices(row)).toEqual({ O1: "CUMULATIVE_CATCH_UP" });
    expect(authoredChoices(row, new Set(["O2"]))).toEqual({});
    expect(authoredChoices({ ...row, chosen_treatments: PROPOSED })).toEqual({});
    // Unclassified: the choices cannot be told apart, so the member is left as it is.
    expect(authoredChoices({ ...row, proposed_treatments: {} })).toBeUndefined();
  });

  it("opens the first step that is not done", () => {
    const done = {
      classified: true,
      answersConfirmed: true,
      departs: false,
      judgementLinked: false,
      previewed: true,
    };

    expect(firstOpenStep({ ...done, classified: false })).toBe("questionnaire");
    expect(firstOpenStep({ ...done, answersConfirmed: false })).toBe("questionnaire");
    expect(firstOpenStep({ ...done, departs: true })).toBe("treatment");
    expect(firstOpenStep({ ...done, departs: true, judgementLinked: true })).toBe("submit");
    expect(firstOpenStep({ ...done, previewed: false })).toBe("preview");
    expect(firstOpenStep(done)).toBe("submit");
    // A step is open when every step before it is done; step 1 always is.
    expect(stepReachable("change", { ...done, classified: false })).toBe(true);
    expect(stepReachable("treatment", { ...done, answersConfirmed: false })).toBe(false);
    expect(stepReachable("submit", { ...done, previewed: false })).toBe(false);
    expect(stepReachable("treatment", { ...done, previewed: false })).toBe(true);
  });
});
