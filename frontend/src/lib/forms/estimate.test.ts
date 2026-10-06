// Estimate models (BUILD_SPEC CTR-25; SCREENS §8.4, §8.5; 04 T-CON-12, T-CON-13 and its parameter
// schemas by kind; PRD POL-040, POL-042): a percent is sent as the ratio the API stores, by a shift
// of the decimal point; a version body carries the columns of its kind and null for the others, the
// parameters the form shows beside those it does not; an attestation repeats the approved figures;
// the figures of an element follow its kind.
import { beforeAll, describe, expect, it } from "vitest";

import type { Estimate, EstimateKind, EstimateVersion } from "../api/queries/estimates";
import { registerCurrencies } from "../format";
import {
  attestationBody,
  buildElement,
  buildVersion,
  CONSTRAINT_FACTORS,
  defaultMethod,
  EMPTY_ELEMENT,
  emptyScenario,
  factorFlag,
  type Figure,
  figureBlank,
  figuresOf,
  keyFigure,
  membersOf,
  methodLocked,
  percentToRatio,
  ratioToPercent,
  type VersionForm,
  versionForm,
} from "./estimate";

const ACTOR = { id: "u1", kind: "USER", display_name: "Maya Chen" } as const;

beforeAll(() => {
  // The screens register the contract currency when they read the versions (DS-FMT-03).
  registerCurrencies([
    { code: "USD", minor_unit: 2 },
    { code: "JPY", minor_unit: 0 },
  ]);
});

function version(overrides: Partial<EstimateVersion> = {}): EstimateVersion {
  return {
    id: "v1",
    estimate_id: "e1",
    version_no: 1,
    status: "APPROVED",
    effective_date: "2026-07-01",
    scenarios: [],
    parameters: {},
    unconstrained_amount: null,
    most_conservative_amount: null,
    constrained_amount: null,
    rate: null,
    expected_total_amount: null,
    expected_quantity: null,
    amortization_months: null,
    currency: "USD",
    constraint_checklist: null,
    rationale: "As approved.",
    judgement_record_id: null,
    content_sha256: null,
    approval_request_id: null,
    applied_event_ids: [],
    supersedes_version_id: null,
    approver: null,
    approved_at: null,
    created_by: ACTOR,
    created_at: "2026-07-01T09:00:00Z",
    updated_at: "2026-07-01T09:00:00Z",
    row_version: 1,
    ...overrides,
  };
}

function form(
  kind: EstimateKind,
  overrides: Partial<VersionForm> = {},
  source: EstimateVersion | null = null,
): VersionForm {
  return {
    ...versionForm(kind, source, "USD", "new", (index) => `s${String(index)}`),
    effectiveDate: "30 Sep 2026",
    rationale: "Reassessed at the period end.",
    ...overrides,
  };
}

const NO_COLUMNS = {
  unconstrained_amount: null,
  most_conservative_amount: null,
  constrained_amount: null,
  rate: null,
  expected_total_amount: null,
  expected_quantity: null,
  amortization_months: null,
};

describe("a percent and the ratio the API stores", () => {
  it("moves the decimal point and never passes through a number", () => {
    expect(percentToRatio("80")).toBe("0.8");
    expect(percentToRatio("12.5")).toBe("0.125");
    expect(percentToRatio("100")).toBe("1");
    expect(percentToRatio("0")).toBe("0");
    expect(percentToRatio("0.05")).toBe("0.0005");
    expect(percentToRatio("33.333333333333333333")).toBe("0.33333333333333333333");
    expect(ratioToPercent("0.8")).toBe("80");
    expect(ratioToPercent("0.125")).toBe("12.5");
    expect(ratioToPercent("1")).toBe("100");
    expect(ratioToPercent("0")).toBe("0");
    expect(ratioToPercent("0.0005")).toBe("0.05");
    expect(ratioToPercent("0.33333333333333333333")).toBe("33.333333333333333333");
  });

  it("refuses what is not a percent between 0 and 100", () => {
    for (const text of ["", "abc", "-5", "100.01", "250", "1e2", "12,5,"]) {
      expect(percentToRatio(text), text).toBeNull();
    }
  });
});

describe("a version body", () => {
  it("an estimate of total costs sends its total, null for every other column and no checklist", () => {
    const built = buildVersion(
      "EAC",
      "COST_BUILDUP",
      form("EAC", { values: { expected_total_amount: "850,000.00", expected_quantity: "" } }),
      "USD",
    );
    expect(built.errors).toEqual({});
    expect(built.body).toEqual({
      effective_date: "2026-09-30",
      rationale: "Reassessed at the period end.",
      scenarios: [],
      parameters: {},
      constraint_checklist: null,
      ...NO_COLUMNS,
      expected_total_amount: "850000.00",
    });
  });

  it("names every wrong field in the order of the form", () => {
    const built = buildVersion(
      "EAC",
      "COST_BUILDUP",
      form("EAC", {
        effectiveDate: "",
        rationale: " ",
        values: { expected_total_amount: "", expected_quantity: "12,5x" },
      }),
      "USD",
    );
    expect(built.body).toBeNull();
    expect(Object.entries(built.errors)).toEqual([
      ["effective_date", "Enter the effective date."],
      ["expected_total_amount", "Enter a value."],
      ["expected_quantity", "Enter a number of 0 or more."],
      ["rationale", "Enter the rationale."],
    ]);
  });

  it("a return rate takes a rate or the expected returns, and its three parameters", () => {
    const blank = buildVersion("RETURN_RATE", "RATE", form("RETURN_RATE"), "USD");
    expect(blank.errors).toMatchObject({
      rate: "Enter a rate or the expected returns.",
      "parameters.carrying_cost_per_unit": "Enter a value.",
      "parameters.recovery_cost_per_unit": "Enter a value.",
      "parameters.window_end_date": "Enter a value.",
    });
    const built = buildVersion(
      "RETURN_RATE",
      "RATE",
      form("RETURN_RATE", {
        values: {
          rate: "2.5",
          expected_quantity: "3",
          "parameters.carrying_cost_per_unit": "60.00",
          "parameters.recovery_cost_per_unit": "0",
          "parameters.window_end_date": "31 Dec 2026",
        },
      }),
      "USD",
    );
    expect(built.body).toMatchObject({
      rate: "0.025",
      expected_quantity: "3",
      parameters: {
        carrying_cost_per_unit: "60.00",
        recovery_cost_per_unit: "0",
        window_end_date: "2026-12-31",
      },
    });
  });

  it("a royalty accrual orders its usage period and takes amounts in the version's currency", () => {
    const values = {
      "parameters.usage_period_start_date": "01 Jul 2026",
      "parameters.usage_period_end_date": "30 Jun 2026",
      expected_total_amount: "25,000,000",
    };
    const wrong = buildVersion(
      "ROYALTY_ACCRUAL",
      "ENTERED_AMOUNT",
      form("ROYALTY_ACCRUAL", { values }),
      "JPY",
    );
    expect(wrong.errors).toEqual({
      "parameters.usage_period_end_date": "The usage period ends on or after its start.",
    });
    const built = buildVersion(
      "ROYALTY_ACCRUAL",
      "ENTERED_AMOUNT",
      form("ROYALTY_ACCRUAL", {
        values: { ...values, "parameters.usage_period_end_date": "30 Sep 2026" },
      }),
      "JPY",
    );
    expect(built.body).toMatchObject({
      expected_total_amount: "25000000",
      parameters: { usage_period_start_date: "2026-07-01", usage_period_end_date: "2026-09-30" },
    });
    // JPY has no minor unit: decimals are refused before the API sees them.
    expect(
      buildVersion(
        "ROYALTY_ACCRUAL",
        "ENTERED_AMOUNT",
        form("ROYALTY_ACCRUAL", {
          values: {
            ...values,
            "parameters.usage_period_end_date": "30 Sep 2026",
            expected_total_amount: "25,000,000.50",
          },
        }),
        "JPY",
      ).errors,
    ).toEqual({ expected_total_amount: "Enter a whole amount without decimals." });
  });

  it("amortisation months are a whole number up to 1,200", () => {
    const months = (text: string) =>
      buildVersion(
        "RENEWAL_EXPECTATION",
        "ENTERED_AMOUNT",
        form("RENEWAL_EXPECTATION", { values: { amortization_months: text } }),
        "USD",
      );
    expect(months("36").body).toMatchObject({ amortization_months: 36 });
    expect(months("1201").errors).toEqual({
      amortization_months: "Enter a whole number of months up to 1,200.",
    });
    expect(months("3.5").errors).toEqual({
      amortization_months: "Enter a whole number of months up to 1,200.",
    });
  });

  it("an expected value carries each outcome with its probability as a ratio, and the five factors", () => {
    const earned = {
      ...emptyScenario("a"),
      outcome: "Bonus earned",
      amount: "200,000.00",
      probability: "60",
    };
    const scenarios = [
      earned,
      { ...emptyScenario("b"), outcome: "Bonus missed", amount: "0.00", probability: "40" },
    ];
    const base = form("VARIABLE_CONSIDERATION", {
      scenarios,
      values: {
        unconstrained_amount: "120,000.00",
        most_conservative_amount: "0.00",
        constrained_amount: "0.00",
      },
    });
    const built = buildVersion(
      "VARIABLE_CONSIDERATION",
      "EXPECTED_VALUE",
      { ...base, flags: { ...base.flags, [factorFlag("limited_experience")]: true } },
      "USD",
    );
    expect(built.body).toEqual({
      effective_date: "2026-09-30",
      rationale: "Reassessed at the period end.",
      scenarios: [
        { outcome: "Bonus earned", amount: "200000.00", probability: "0.6" },
        { outcome: "Bonus missed", amount: "0.00", probability: "0.4" },
      ],
      parameters: {},
      constraint_checklist: {
        susceptible_to_outside_factors: false,
        long_resolution_period: false,
        limited_experience: true,
        price_concession_practice: false,
        broad_range_of_amounts: false,
      },
      ...NO_COLUMNS,
      unconstrained_amount: "120000.00",
      most_conservative_amount: "0.00",
      constrained_amount: "0.00",
    });
    expect(Object.keys(built.body?.constraint_checklist ?? {})).toEqual([...CONSTRAINT_FACTORS]);

    // Without a probability the row is named; a most likely amount asks for none.
    const noProbability = { ...base, scenarios: [{ ...earned, probability: "" }] };
    expect(
      buildVersion("VARIABLE_CONSIDERATION", "EXPECTED_VALUE", noProbability, "USD").errors,
    ).toEqual({
      "scenarios.0.probability": "Enter a percent between 0 and 100.",
    });
    expect(
      buildVersion("VARIABLE_CONSIDERATION", "MOST_LIKELY_AMOUNT", noProbability, "USD").body
        ?.scenarios,
    ).toEqual([{ outcome: "Bonus earned", amount: "200000.00" }]);
  });

  it("keeps the parameters the form does not show and never carries an attestation over", () => {
    const source = version({
      parameters: { no_change_attestation: true, refund_liability_target: "5750.00" },
      constrained_amount: "5750.00",
    });
    const built = buildVersion(
      "VARIABLE_CONSIDERATION",
      "MOST_LIKELY_AMOUNT",
      form("VARIABLE_CONSIDERATION", {}, source),
      "USD",
      source.parameters,
    );
    expect(built.body?.parameters).toEqual({ refund_liability_target: "5750.00" });
    expect(built.body?.constrained_amount).toBe("5750.00");
  });

  it("a share-based consideration sends its grant, its vesting conclusion and the forfeiture ratio", () => {
    const base = form("SHARE_BASED_CONSIDERATION", {
      values: {
        expected_total_amount: "1,000,000.00",
        "parameters.grant_date": "01 Mar 2026",
        "parameters.grant_date_fair_value": "250,000.00",
        "parameters.expected_forfeiture_ratio": "5",
      },
    });
    const built = buildVersion(
      "SHARE_BASED_CONSIDERATION",
      "ENTERED_AMOUNT",
      { ...base, flags: { "parameters.vesting_probable": true } },
      "USD",
    );
    expect(built.body).toMatchObject({
      expected_total_amount: "1000000.00",
      parameters: {
        grant_date: "2026-03-01",
        grant_date_fair_value: "250000.00",
        vesting_probable: true,
        expected_forfeiture_ratio: "0.05",
      },
    });
    // The checkbox left clear is a conclusion too: the member is sent as false.
    expect(
      buildVersion("SHARE_BASED_CONSIDERATION", "ENTERED_AMOUNT", base, "USD").body?.parameters,
    ).toMatchObject({ vesting_probable: false });
  });
});

describe("the form of a version", () => {
  it("an edit shows what the draft holds; a new version starts from the figures and not the date", () => {
    const source = version({
      status: "DRAFT",
      effective_date: "2026-09-30",
      rationale: "Draft rationale.",
      rate: "0.8",
      expected_quantity: "1200",
      scenarios: [{ outcome: "Threshold expected", amount: "5750.00", probability: "0.25" }],
      constrained_amount: "5750.00",
      constraint_checklist: { broad_range_of_amounts: true, limited_experience: false },
    });
    const edit = versionForm(
      "VARIABLE_CONSIDERATION",
      source,
      "USD",
      "edit",
      (index) => `s${String(index)}`,
    );
    expect(edit.effectiveDate).toBe("30 Sep 2026");
    expect(edit.rationale).toBe("Draft rationale.");
    expect(edit.values.constrained_amount).toBe("5,750.00");
    expect(edit.scenarios).toEqual([
      { id: "s0", outcome: "Threshold expected", amount: "5,750.00", probability: "25" },
    ]);
    expect(edit.flags[factorFlag("broad_range_of_amounts")]).toBe(true);
    expect(edit.flags[factorFlag("limited_experience")]).toBe(false);

    const fresh = versionForm(
      "VARIABLE_CONSIDERATION",
      source,
      "USD",
      "new",
      (index) => `s${String(index)}`,
    );
    expect(fresh.effectiveDate).toBe("");
    expect(fresh.rationale).toBe("");
    expect(fresh.values.constrained_amount).toBe("5,750.00");

    expect(versionForm("BREAKAGE", source, "USD", "edit", () => "s").values).toEqual({
      rate: "80",
      expected_quantity: "1200",
    });
  });
});

describe("an attestation", () => {
  it("repeats the approved figures, scenarios and checklist with the no-change parameter", () => {
    const approved = version({
      scenarios: [{ outcome: "Threshold not expected", amount: "0.00" }],
      unconstrained_amount: "5750.00",
      most_conservative_amount: "0.00",
      constrained_amount: "0.00",
      parameters: { refund_liability_target: "0.00" },
      constraint_checklist: { broad_range_of_amounts: true },
    });
    expect(attestationBody(approved, "2026-09-30", "Forecast unchanged.")).toEqual({
      effective_date: "2026-09-30",
      rationale: "Forecast unchanged.",
      scenarios: [{ outcome: "Threshold not expected", amount: "0.00" }],
      parameters: { refund_liability_target: "0.00", no_change_attestation: true },
      // 04 T-CON-13 rev 1.210 (item EST-CONSTRAINT-KEYS-1): the API takes all five factors or no
      // checklist, so a version stored with fewer keys is repeated with the factors it marks.
      constraint_checklist: {
        susceptible_to_outside_factors: false,
        long_resolution_period: false,
        limited_experience: false,
        price_concession_practice: false,
        broad_range_of_amounts: true,
      },
      ...NO_COLUMNS,
      unconstrained_amount: "5750.00",
      most_conservative_amount: "0.00",
      constrained_amount: "0.00",
    });
    const without = version({ constraint_checklist: null });
    expect(attestationBody(without, "2026-09-30", "Forecast unchanged.").constraint_checklist).toBe(
      null,
    );
  });
});

describe("the element form", () => {
  it("names what is missing and builds the body of a targeted variable consideration", () => {
    expect(buildElement(EMPTY_ELEMENT).errors).toEqual({
      estimate_kind: "Choose a value.",
      element_code: "Enter the element code.",
      method: "Choose a value.",
    });
    const targeted = {
      ...EMPTY_ELEMENT,
      kind: "VARIABLE_CONSIDERATION" as const,
      elementCode: " BONUS-CB-01 ",
      method: "MOST_LIKELY_AMOUNT" as const,
      target: "OBLIGATIONS" as const,
    };
    expect(buildElement(targeted).errors).toEqual({
      vc_element_type: "Choose a value.",
      target_obligation_keys: "Choose the obligations the element is allocated to.",
      allocation_criteria_evidence: "Describe how the criteria of ASC 606-10-32-40 are met.",
    });
    expect(
      buildElement({
        ...targeted,
        vcElementType: "BONUS",
        targetKeys: ["O1"],
        criteriaEvidence: "The bonus relates to the build obligation alone.",
      }).body,
    ).toEqual({
      estimate_kind: "VARIABLE_CONSIDERATION",
      element_code: "BONUS-CB-01",
      method: "MOST_LIKELY_AMOUNT",
      allocation_target: "OBLIGATIONS",
      target_obligation_keys: ["O1"],
      vc_element_type: "BONUS",
      obligation_key: null,
      allocation_criteria_evidence: "The bonus relates to the build obligation alone.",
    });
    expect(buildElement({ ...targeted, elementCode: "EAC 1" }).errors.element_code).toBe(
      "Use up to 64 letters, digits, dots, hyphens and underscores, starting with a letter or a digit.",
    );
  });

  it("proposes a method per kind and locks the method once a version is approved", () => {
    expect(defaultMethod("EAC")).toBe("COST_BUILDUP");
    expect(defaultMethod("RETURN_RATE")).toBe("RATE");
    expect(defaultMethod("VARIABLE_CONSIDERATION")).toBeNull();
    expect(defaultMethod("EXPECTED_PURCHASES")).toBe("ENTERED_AMOUNT");
    const summary = {
      id: "v1",
      version_no: 1,
      status: "APPROVED",
      effective_date: "2026-07-01",
      approver: null,
      approved_at: null,
    } satisfies NonNullable<Estimate["current_version"]>;
    expect(methodLocked({ current_version: null })).toBe(false);
    expect(methodLocked({ current_version: summary })).toBe(true);
  });
});

/** What a figure holds, whatever its type: a date, the two dates of a range, or a decimal. */
function held(cell: Figure): string | null {
  switch (cell.type) {
    case "date":
      return cell.date;
    case "period":
      return cell.start === null || cell.end === null ? null : `${cell.start}/${cell.end}`;
    default:
      return cell.value;
  }
}

describe("the figures of a version", () => {
  it("follow the kind, the key figure first", () => {
    const eac = version({
      expected_total_amount: "850000.00",
      costs_incurred_to_date: { amount: "502000.00", currency: "USD" },
      progress_ratio: "0.591",
    });
    expect(figuresOf("EAC", eac).map((cell) => [cell.id, cell.type, held(cell)])).toEqual([
      ["expected_total_amount", "money", "850000.00"],
      ["costs_incurred_to_date", "money", "502000.00"],
      ["progress_ratio", "progress", "0.591"],
    ]);
    expect(held(keyFigure("EAC", eac))).toBe("850000.00");

    const variable = version({
      constrained_amount: "0.00",
      unconstrained_amount: "5750.00",
      excluded_amount: { amount: "5750.00", currency: "USD" },
    });
    expect(
      figuresOf("VARIABLE_CONSIDERATION", variable).map((cell) => [cell.id, cell.type, held(cell)]),
    ).toEqual([
      ["constrained_amount", "money", "0.00"],
      ["unconstrained_amount", "money", "5750.00"],
      ["excluded_amount", "money", "5750.00"],
      ["effective_date", "date", "2026-07-01"],
    ]);

    // "Rate or constrained amount": the member the version holds.
    expect(
      figuresOf("IMPLICIT_PRICE_CONCESSION", version({ constrained_amount: "1200.00" })).map(
        (cell) => [cell.id, held(cell)],
      ),
    ).toEqual([["constrained_amount", "1200.00"]]);
    expect(
      figuresOf("IMPLICIT_PRICE_CONCESSION", version({ rate: "0.02" })).map((cell) => cell.id),
    ).toEqual(["rate"]);
    expect(figuresOf("IMPLICIT_PRICE_CONCESSION", version()).map((cell) => cell.id)).toEqual([
      "rate",
    ]);

    const royalty = version({
      expected_total_amount: "25000000",
      currency: "JPY",
      parameters: { usage_period_start_date: "2026-07-01", usage_period_end_date: "2026-09-30" },
    });
    expect(figuresOf("ROYALTY_ACCRUAL", royalty).map((cell) => [cell.type, held(cell)])).toEqual([
      ["money", "25000000"],
      ["period", "2026-07-01/2026-09-30"],
    ]);
    expect(membersOf("ROYALTY_ACCRUAL", royalty).map((cell) => [cell.type, held(cell)])).toEqual([
      ["date", "2026-07-01"],
      ["date", "2026-09-30"],
      ["money", "25000000"],
    ]);
  });

  it("a parameter that does not read as a date is no date", () => {
    // `parameters` is free-form JSON to the client: only a business date reaches the date format.
    const odd = version({
      parameters: { usage_period_start_date: "Q3", usage_period_end_date: 20260930 },
    });
    expect(figuresOf("ROYALTY_ACCRUAL", odd).map(figureBlank)).toEqual([true, true]);
    expect(membersOf("ROYALTY_ACCRUAL", odd).map(held)).toEqual([null, null, null]);
    expect(
      versionForm("ROYALTY_ACCRUAL", odd, "USD", "edit", () => "s").values[
        "parameters.usage_period_start_date"
      ],
    ).toBe("");
  });
});
