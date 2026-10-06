// Estimate models (SCREENS §8.4, §8.5; 04 T-CON-12, T-CON-13 with its parameter schemas by kind,
// E-09, E-10, API-R-32; PRD SM-04, POL-040, POL-183; docs/dev-guide.md DG-FE-06; BUILD_SPEC CTR-25).
//
// `KIND_MEMBERS` names, per E-09 kind, the members of a version the drawer edits: a T-CON-13 column or
// a member of `parameters`. The same table feeds the figures of an element, the definition list of a
// version and the comparison of two versions, so a label and a format are written once. The forms hold
// what the user typed as text: `buildVersion` and `buildElement` check them and answer the API body
// with amounts as decimal strings, dates as business dates and a percent as the ratio the API stores
// (a decimal shift on the string, never a number). The server stays the authority: the method lock
// (IMP-71), the constraint range (IMP-74), the costs incurred (ERR-13) and a probability total other
// than 1 are its findings and reach the form through `errors[]`.
import type {
  Estimate,
  EstimateCreateBody,
  EstimateKind,
  EstimateMethod,
  EstimateTarget,
  EstimateVersion,
  EstimateVersionCreateBody,
  VcElementType,
} from "../api/queries/estimates";
import { formatDate, formatMoney, formatNumber, parseDateInput } from "../format";
import { t } from "../i18n/t";
import { blankToNull, currencyKnown, dateOf, moneyError, moneyOf } from "./contract";

/**
 * How a member reads and is typed: `money` an amount in the version's currency; `unit` a cost per
 * unit (a decimal, DS-FMT-13); `rate` a ratio shown and typed as a percent with two decimals
 * (DS-FMT-09); `progress` a ratio with one decimal; `quantity` units or hours (DS-FMT-11); `integer`
 * a count of months; `date`; `flag` a boolean; `period` a date range of two members (DS-FMT-20), a
 * figure only.
 */
export type ValueType =
  "money" | "unit" | "rate" | "progress" | "quantity" | "integer" | "date" | "flag" | "period";

export interface Member {
  /** The field name of the form and of `errors[].field`: the column, or `parameters.<name>`. */
  readonly id: string;
  readonly name: string;
  readonly parameter: boolean;
  readonly type: ValueType;
  /** The catalogue key of the field label. */
  readonly label: string;
  readonly required: boolean;
}

function column(name: string, type: ValueType, label: string, required = false): Member {
  return {
    id: name,
    name,
    parameter: false,
    type,
    label: `contracts.estimates.field.${label}`,
    required,
  };
}

function parameter(name: string, type: ValueType, label: string, required = false): Member {
  return {
    id: `parameters.${name}`,
    name,
    parameter: true,
    type,
    label: `contracts.estimates.field.${label}`,
    required,
  };
}

/** SCREENS §8.4 "Kind-specific fields" on the 04 T-CON-13 columns and parameter schemas. */
export const KIND_MEMBERS: Readonly<Record<EstimateKind, readonly Member[]>> = {
  VARIABLE_CONSIDERATION: [
    column("unconstrained_amount", "money", "unconstrainedAmount"),
    column("most_conservative_amount", "money", "mostConservativeAmount"),
    column("constrained_amount", "money", "constrainedAmount", true),
  ],
  RETURN_RATE: [
    column("rate", "rate", "rate"),
    column("expected_quantity", "quantity", "expectedReturns"),
    parameter("carrying_cost_per_unit", "unit", "carryingCost", true),
    parameter("recovery_cost_per_unit", "unit", "recoveryCost", true),
    parameter("window_end_date", "date", "windowEnd", true),
  ],
  BREAKAGE: [
    column("rate", "rate", "rate", true),
    column("expected_quantity", "quantity", "expectedRedemptions"),
  ],
  EAC: [
    column("expected_total_amount", "money", "estimatedTotalCosts", true),
    column("expected_quantity", "quantity", "expectedHours"),
  ],
  EXERCISE_LIKELIHOOD: [column("rate", "rate", "rate", true)],
  IMPLICIT_PRICE_CONCESSION: [
    column("rate", "rate", "rate"),
    column("constrained_amount", "money", "amount"),
  ],
  RENEWAL_EXPECTATION: [column("amortization_months", "integer", "amortisationMonths", true)],
  ROYALTY_ACCRUAL: [
    parameter("usage_period_start_date", "date", "usageStart", true),
    parameter("usage_period_end_date", "date", "usageEnd", true),
    column("expected_total_amount", "money", "estimatedRoyalties", true),
  ],
  EXPECTED_PURCHASES: [column("expected_total_amount", "money", "expectedTotalAmount", true)],
  SHARE_BASED_CONSIDERATION: [
    column("expected_total_amount", "money", "expectedRelatedRevenue", true),
    parameter("grant_date", "date", "grantDate", true),
    parameter("grant_date_fair_value", "money", "grantDateFairValue", true),
    parameter("vesting_probable", "flag", "vestingProbable"),
    parameter("expected_forfeiture_ratio", "rate", "expectedForfeiture"),
  ],
};

/** The kinds that take one of two members ("Rate or Expected returns", "Rate or Amount"). */
const ONE_OF: Readonly<Partial<Record<EstimateKind, readonly [string, string]>>> = {
  RETURN_RATE: ["rate", "expected_quantity"],
  IMPLICIT_PRICE_CONCESSION: ["rate", "constrained_amount"],
};

/** The T-CON-13 columns a version body carries; a kind that does not use one sends null. */
const VALUE_COLUMNS = [
  "unconstrained_amount",
  "most_conservative_amount",
  "constrained_amount",
  "rate",
  "expected_total_amount",
  "expected_quantity",
  "amortization_months",
] as const;

/** The kinds whose versions need evidence before submission (SCREENS §8.4; PRD SM-04). */
export const EVIDENCE_REQUIRED: ReadonlySet<EstimateKind> = new Set([
  "VARIABLE_CONSIDERATION",
  "EAC",
  "RETURN_RATE",
]);

/**
 * The five factors of ASC 606-10-32-12 (a) to (e), in its order, as the keys of
 * `constraint_checklist` (SCREENS §8.4 rev 1.29; ruling of 2026-10-01 on the lane's point 8): one
 * boolean per factor, true where the factor is present. Every save writes all five.
 */
export const CONSTRAINT_FACTORS = [
  "susceptible_to_outside_factors",
  "long_resolution_period",
  "limited_experience",
  "price_concession_practice",
  "broad_range_of_amounts",
] as const;
export type ConstraintFactor = (typeof CONSTRAINT_FACTORS)[number];

export function factorFlag(factor: ConstraintFactor): string {
  return `factor.${factor}`;
}

/**
 * `constraint_checklist` as the API takes it (04 T-CON-13 rev 1.210, item EST-CONSTRAINT-KEYS-1):
 * all five factors, one boolean each — true where `present` says the factor is.
 */
function checklistOf(
  present: (factor: ConstraintFactor) => boolean,
): Record<ConstraintFactor, boolean> {
  return {
    susceptible_to_outside_factors: present("susceptible_to_outside_factors"),
    long_resolution_period: present("long_resolution_period"),
    limited_experience: present("limited_experience"),
    price_concession_practice: present("price_concession_practice"),
    broad_range_of_amounts: present("broad_range_of_amounts"),
  };
}

/** POL-183: an error correction is not an estimate version; the choice is not stored. */
export type EacClassification = "CHANGE_IN_ESTIMATE" | "ERROR_CORRECTION";
/** 04 T-CON-13 `VARIABLE_CONSIDERATION` parameter of a "No change" attestation (POL-042). */
export const NO_CHANGE = "no_change_attestation";
export const MEMO_MAX_LENGTH = 4000;
export const MAX_SCENARIOS = 100;
export const MAX_MONTHS = 1200;
/** 04 `erev.code` of an element code. */
const ELEMENT_CODE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const DECIMAL = /^\d+(?:\.\d+)?$/;

// ---------------------------------------------------------------------------------------------------
// Decimal strings.

/** A limit as the messages state it, for example "4,000". */
export function countText(value: number): string {
  return formatNumber(value, { kind: "count" });
}

/** A non-negative decimal as the API takes it, grouping separators removed; null when it is not one. */
export function plainDecimal(text: string): string | null {
  const value = text.trim().replace(/,/g, "");
  return DECIMAL.test(value) ? value : null;
}

function shifted(digits: string, scale: number): string {
  const padded = digits.padStart(scale + 1, "0");
  const whole = padded.slice(0, padded.length - scale).replace(/^0+(?=\d)/, "");
  const part = padded.slice(padded.length - scale).replace(/0+$/, "");
  return part === "" ? whole : `${whole}.${part}`;
}

/**
 * A typed percent as the ratio the API stores, by moving the decimal point: "80" → "0.8",
 * "12.5" → "0.125", "100" → "1". Null for text that is not a decimal between 0 and 100.
 */
export function percentToRatio(text: string): string | null {
  const value = plainDecimal(text);
  if (value === null) {
    return null;
  }
  const [integer = "0", fraction = ""] = value.split(".");
  const ratio = shifted(`${integer}${fraction}`, fraction.length + 2);
  const [whole = "0", part = ""] = ratio.split(".");
  return whole === "0" || (whole === "1" && part === "") ? ratio : null;
}

/** A stored ratio as the percent the field shows: "0.8" → "80", "0.125" → "12.5", "1" → "100". */
export function ratioToPercent(ratio: string): string {
  const value = plainDecimal(ratio);
  if (value === null) {
    return ratio;
  }
  const [integer = "0", fraction = ""] = value.split(".");
  const padded = fraction.padEnd(2, "0");
  const whole = `${integer}${padded.slice(0, 2)}`.replace(/^0+(?=\d)/, "");
  const part = padded.slice(2).replace(/0+$/, "");
  return part === "" ? whole : `${whole}.${part}`;
}

// ---------------------------------------------------------------------------------------------------
// Reading a version.

function text(value: unknown): string | null {
  if (typeof value === "string") {
    return value;
  }
  return typeof value === "number" ? String(value) : null;
}

/**
 * A date of the parameters. `parameters` is free-form JSON to the client (04 T-CON-13 types it per
 * kind), so the text counts as a business date only when it reads as one.
 */
function parameterDate(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const parsed = parseDateInput(value);
  return parsed.ok ? parsed.value : null;
}

/** The value of a member that is no date, as the API answers it: a decimal or "true" / "false". */
export function memberValue(version: EstimateVersion, member: Member): string | null {
  const raw: unknown = member.parameter
    ? version.parameters[member.name]
    : (version as unknown as Readonly<Record<string, unknown>>)[member.name];
  if (member.type === "flag") {
    return typeof raw === "boolean" ? String(raw) : null;
  }
  return text(raw);
}

/** Whether the version is a "No change" attestation (variable consideration only). */
export function isAttestation(version: EstimateVersion): boolean {
  return version.parameters[NO_CHANGE] === true;
}

export interface Scenario {
  readonly outcome: string;
  readonly amount: string;
  readonly probability: string | null;
}

/** The scenario table of a version as stored (T-CON-13 `scenarios`). */
export function scenariosOf(version: EstimateVersion): readonly Scenario[] {
  return version.scenarios.map((item) => ({
    outcome: text(item.outcome) ?? "",
    amount: text(item.amount) ?? "0",
    probability: text(item.probability),
  }));
}

/** The factors the version's checklist marks. */
export function factorsOf(version: EstimateVersion): readonly ConstraintFactor[] {
  const checklist = version.constraint_checklist ?? {};
  return CONSTRAINT_FACTORS.filter((factor) => checklist[factor] === true);
}

interface FigureBase {
  readonly id: string;
  /** The catalogue key of the label. */
  readonly label: string;
}

/**
 * One figure of a version: a strip cell, a grid cell or a row of the definition list. A date and a
 * date range keep their dates apart from the decimals, so that each reaches the formatter of its
 * kind (DG-FE-20). Null shows the no-value dash.
 */
export type Figure =
  | (FigureBase & { readonly type: "date"; readonly date: string | null })
  | (FigureBase & {
      readonly type: "period";
      readonly start: string | null;
      readonly end: string | null;
    })
  | (FigureBase & {
      readonly type: Exclude<ValueType, "date" | "period">;
      readonly value: string | null;
    });

/** Whether the version holds nothing for the figure. */
export function figureBlank(cell: Figure): boolean {
  switch (cell.type) {
    case "date":
      return cell.date === null;
    case "period":
      return cell.start === null || cell.end === null;
    default:
      return cell.value === null;
  }
}

function figure(
  id: string,
  label: string,
  type: Exclude<ValueType, "date" | "period">,
  value: string | null,
): Figure {
  return { id, label: `contracts.estimates.field.${label}`, type, value };
}

function ofMember(version: EstimateVersion, kind: EstimateKind, id: string): Figure {
  const member = KIND_MEMBERS[kind].find((item) => item.id === id);
  if (member === undefined) {
    throw new Error(`${kind} has no member ${id}`);
  }
  if (member.type === "date") {
    // Every date member is a parameter; the effective date is the version's own column.
    return {
      id,
      label: member.label,
      type: "date",
      date: parameterDate(version.parameters[member.name]),
    };
  }
  if (member.type === "period") {
    throw new Error(`${id} is a range of two members`);
  }
  return { id, label: member.label, type: member.type, value: memberValue(version, member) };
}

/** SCREENS §8.4 "Figures (cells)" of a version, in that order; the first is the kind's key figure. */
export function figuresOf(kind: EstimateKind, version: EstimateVersion): readonly Figure[] {
  switch (kind) {
    case "VARIABLE_CONSIDERATION":
      return [
        ofMember(version, kind, "constrained_amount"),
        ofMember(version, kind, "unconstrained_amount"),
        figure(
          "excluded_amount",
          "excludedAmount",
          "money",
          version.excluded_amount?.amount ?? null,
        ),
        {
          id: "effective_date",
          label: "contracts.estimates.field.effectiveDate",
          type: "date",
          date: version.effective_date,
        },
      ];
    case "RETURN_RATE":
      return [
        ofMember(version, kind, "expected_quantity"),
        ofMember(version, kind, "rate"),
        ofMember(version, kind, "parameters.carrying_cost_per_unit"),
        ofMember(version, kind, "parameters.recovery_cost_per_unit"),
      ];
    case "BREAKAGE":
      return [ofMember(version, kind, "rate"), ofMember(version, kind, "expected_quantity")];
    case "EAC":
      return [
        ofMember(version, kind, "expected_total_amount"),
        figure(
          "costs_incurred_to_date",
          "costsIncurred",
          "money",
          version.costs_incurred_to_date?.amount ?? null,
        ),
        figure("progress_ratio", "progress", "progress", version.progress_ratio ?? null),
      ];
    case "EXERCISE_LIKELIHOOD":
      return [ofMember(version, kind, "rate")];
    case "IMPLICIT_PRICE_CONCESSION": {
      // "Rate or constrained amount": the member the version holds; the rate when it holds neither.
      const cells = [
        ofMember(version, kind, "rate"),
        figure("constrained_amount", "constrainedAmount", "money", version.constrained_amount),
      ].filter((cell) => !figureBlank(cell));
      return cells.length === 0 ? [ofMember(version, kind, "rate")] : cells;
    }
    case "RENEWAL_EXPECTATION":
      return [ofMember(version, kind, "amortization_months")];
    case "ROYALTY_ACCRUAL":
      return [
        ofMember(version, kind, "expected_total_amount"),
        {
          id: "usage_period",
          label: "contracts.estimates.field.usagePeriod",
          type: "period",
          start: parameterDate(version.parameters.usage_period_start_date),
          end: parameterDate(version.parameters.usage_period_end_date),
        },
      ];
    case "EXPECTED_PURCHASES":
      return [
        figure(
          "expected_total_amount",
          "expectedPurchases",
          "money",
          version.expected_total_amount,
        ),
      ];
    case "SHARE_BASED_CONSIDERATION":
      return [
        ofMember(version, kind, "expected_total_amount"),
        ofMember(version, kind, "parameters.grant_date_fair_value"),
        ofMember(version, kind, "parameters.grant_date"),
      ];
  }
}

/** The kind's key figure (SCREENS §8.3 master row, §8.5 column "Figure"). */
export function keyFigure(kind: EstimateKind, version: EstimateVersion): Figure {
  const [first] = figuresOf(kind, version);
  if (first === undefined) {
    throw new Error(`${kind} has no figure`);
  }
  return first;
}

/** Every member of a version in the drawer's order, for the definition list and the comparison. */
export function membersOf(kind: EstimateKind, version: EstimateVersion): readonly Figure[] {
  return KIND_MEMBERS[kind].map((member) => ofMember(version, kind, member.id));
}

// ---------------------------------------------------------------------------------------------------
// The version form.

export interface ScenarioRow {
  readonly id: string;
  readonly outcome: string;
  readonly amount: string;
  /** A percent as typed; read for `EXPECTED_VALUE` only. */
  readonly probability: string;
}

export interface VersionForm {
  readonly effectiveDate: string;
  readonly rationale: string;
  /** Typed text by member id. */
  readonly values: Readonly<Record<string, string>>;
  /** Flag members by member id and the constraint factors by `factorFlag`. */
  readonly flags: Readonly<Record<string, boolean>>;
  readonly scenarios: readonly ScenarioRow[];
  readonly classification: EacClassification;
}

export function emptyScenario(id: string): ScenarioRow {
  return { id, outcome: "", amount: "", probability: "" };
}

/** A stored decimal as the text of its field; dates are typed apart (`parameterDate`). */
function typedText(type: ValueType, value: string | null, currency: string): string {
  if (value === null) {
    return "";
  }
  switch (type) {
    case "money":
      return currencyKnown(currency) ? formatMoney(value, currency) : value;
    case "rate":
    case "progress":
      return ratioToPercent(value);
    default:
      return value;
  }
}

/**
 * The form of a version. `source` is the draft that is edited, or the version a new one starts
 * from (its figures are a starting point; the effective date and the rationale are the new
 * version's own). Without a source every field is empty.
 */
export function versionForm(
  kind: EstimateKind,
  source: EstimateVersion | null,
  currency: string,
  mode: "edit" | "new",
  scenarioId: (index: number) => string,
): VersionForm {
  const values: Record<string, string> = {};
  const flags: Record<string, boolean> = {};
  for (const member of KIND_MEMBERS[kind]) {
    if (member.type === "date") {
      const date = source === null ? null : parameterDate(source.parameters[member.name]);
      values[member.id] = date === null ? "" : formatDate(date);
      continue;
    }
    const value = source === null ? null : memberValue(source, member);
    if (member.type === "flag") {
      flags[member.id] = value === "true";
    } else {
      values[member.id] = typedText(member.type, value, currency);
    }
  }
  if (kind === "VARIABLE_CONSIDERATION") {
    const marked = source === null ? [] : factorsOf(source);
    for (const factor of CONSTRAINT_FACTORS) {
      flags[factorFlag(factor)] = marked.includes(factor);
    }
  }
  const scenarios =
    source === null
      ? []
      : scenariosOf(source).map((item, index) => ({
          id: scenarioId(index),
          outcome: item.outcome,
          amount: typedText("money", item.amount, currency),
          probability: item.probability === null ? "" : ratioToPercent(item.probability),
        }));
  return {
    effectiveDate: mode === "edit" && source !== null ? formatDate(source.effective_date) : "",
    rationale: mode === "edit" && source !== null ? source.rationale : "",
    values,
    flags,
    scenarios,
    classification: "CHANGE_IN_ESTIMATE",
  };
}

export interface BuiltVersion {
  /** The body of `POST /estimates/{id}/versions`, also sent whole to PATCH; null while a field is wrong. */
  readonly body: EstimateVersionCreateBody | null;
  /** Field name → message, in form order. */
  readonly errors: Readonly<Record<string, string>>;
}

function memberError(member: Member, typed: string, currency: string): string | null {
  switch (member.type) {
    case "money":
      return moneyError(typed, currency);
    case "rate":
    case "progress":
      return percentToRatio(typed) === null ? t("contracts.drawer.event.percentError") : null;
    case "unit":
    case "quantity":
      return plainDecimal(typed) === null ? t("contracts.estimates.error.decimal") : null;
    case "integer": {
      const value = typed.trim();
      return /^\d+$/.test(value) && Number(value) <= MAX_MONTHS
        ? null
        : t("contracts.estimates.error.months", { max: countText(MAX_MONTHS) });
    }
    case "date":
      return parseDateInput(typed).ok ? null : t("common.form.date.invalid");
    default:
      return null;
  }
}

function memberBody(member: Member, typed: string, currency: string): string | number | null {
  switch (member.type) {
    case "money":
      return moneyOf(typed, currency);
    case "rate":
    case "progress":
      return percentToRatio(typed);
    case "unit":
    case "quantity":
      return plainDecimal(typed);
    case "integer":
      return Number(typed.trim());
    case "date":
      return dateOf(typed);
    default:
      return null;
  }
}

/**
 * Every check of the version form, then the body (DS-CMP-21 "all checks run on submit"). `carried`
 * are the parameters of the version the form came from: the members the form does not show stay as
 * they are (for example `refund_liability_target`), and a new version is never an attestation.
 */
export function buildVersion(
  kind: EstimateKind,
  method: EstimateMethod,
  form: VersionForm,
  currency: string,
  carried: Readonly<Record<string, unknown>> = {},
): BuiltVersion {
  const errors: Record<string, string> = {};
  const effective = dateOf(form.effectiveDate);
  if (form.effectiveDate.trim() === "") {
    errors.effective_date = t("contracts.estimates.error.effectiveDate");
  } else if (effective === null) {
    errors.effective_date = t("common.form.date.invalid");
  }

  const expectedValue = method === "EXPECTED_VALUE";
  const scenarios: EstimateVersionCreateBody["scenarios"] = [];
  if (kind === "VARIABLE_CONSIDERATION") {
    form.scenarios.forEach((row, index) => {
      const outcome = blankToNull(row.outcome);
      if (outcome === null) {
        errors[`scenarios.${String(index)}.outcome`] = t("contracts.estimates.error.outcome");
      }
      const amountError =
        row.amount.trim() === ""
          ? t("contracts.drawer.override.valueRequired")
          : moneyError(row.amount, currency);
      if (amountError !== null) {
        errors[`scenarios.${String(index)}.amount`] = amountError;
      }
      const probability = expectedValue ? percentToRatio(row.probability) : null;
      if (expectedValue && probability === null) {
        errors[`scenarios.${String(index)}.probability`] = t("contracts.drawer.event.percentError");
      }
      scenarios.push({
        outcome: outcome ?? "",
        amount: moneyOf(row.amount, currency) ?? "0",
        ...(expectedValue ? { probability: probability ?? "0" } : {}),
      });
    });
    if (form.scenarios.length > MAX_SCENARIOS) {
      errors.scenarios = t("contracts.estimates.error.scenarios", {
        max: countText(MAX_SCENARIOS),
      });
    }
  }

  const members = KIND_MEMBERS[kind];
  const columns: Record<string, string | number | null> = {};
  const parameters = new Map<string, unknown>(Object.entries(carried));
  parameters.delete(NO_CHANGE);
  for (const member of members) {
    if (member.type === "flag") {
      parameters.set(member.name, form.flags[member.id] === true);
      continue;
    }
    const typed = form.values[member.id] ?? "";
    let value: string | number | null = null;
    if (typed.trim() === "") {
      if (member.required) {
        errors[member.id] = t("contracts.drawer.override.valueRequired");
      }
    } else {
      const error = memberError(member, typed, currency);
      if (error === null) {
        value = memberBody(member, typed, currency);
      } else {
        errors[member.id] = error;
      }
    }
    if (member.parameter) {
      if (value === null) {
        parameters.delete(member.name);
      } else {
        parameters.set(member.name, value);
      }
    } else {
      columns[member.name] = value;
    }
  }
  const pair = ONE_OF[kind];
  if (pair !== undefined) {
    const [first, second] = pair;
    const blank = (id: string) => (form.values[id] ?? "").trim() === "";
    if (blank(first) && blank(second)) {
      errors[first] = t(`contracts.estimates.error.oneOf.${kind}`);
    }
  }
  if (kind === "ROYALTY_ACCRUAL") {
    const start = parameters.get("usage_period_start_date");
    const end = parameters.get("usage_period_end_date");
    if (typeof start === "string" && typeof end === "string" && end < start) {
      errors["parameters.usage_period_end_date"] = t("contracts.estimates.error.usageOrder");
    }
  }

  const rationale = blankToNull(form.rationale);
  if (rationale === null) {
    errors.rationale = t("contracts.estimates.error.rationale");
  } else if (rationale.length > MEMO_MAX_LENGTH) {
    errors.rationale = t("contracts.estimates.error.tooLong", {
      max: countText(MEMO_MAX_LENGTH),
    });
  }

  if (Object.keys(errors).length > 0 || effective === null || rationale === null) {
    return { body: null, errors: ordered(errors, kind, form) };
  }
  const body: EstimateVersionCreateBody = {
    effective_date: effective,
    rationale,
    scenarios,
    parameters: Object.fromEntries(parameters),
    constraint_checklist:
      kind === "VARIABLE_CONSIDERATION"
        ? checklistOf((factor) => form.flags[factorFlag(factor)] === true)
        : null,
  };
  const target = body as Record<string, unknown>;
  for (const name of VALUE_COLUMNS) {
    target[name] = columns[name] ?? null;
  }
  return { body, errors: {} };
}

/** The errors in the order of the form: effective date, scenarios, the members, the rationale. */
function ordered(
  errors: Readonly<Record<string, string>>,
  kind: EstimateKind,
  form: VersionForm,
): Record<string, string> {
  const order = [
    "effective_date",
    "scenarios",
    ...form.scenarios.flatMap((_, index) =>
      ["outcome", "amount", "probability"].map((name) => `scenarios.${String(index)}.${name}`),
    ),
    ...KIND_MEMBERS[kind].map((member) => member.id),
    "rationale",
  ];
  const sorted: Record<string, string> = {};
  for (const name of order) {
    const message = errors[name];
    if (message !== undefined) {
      sorted[name] = message;
    }
  }
  return sorted;
}

/**
 * The body of a "No change" attestation (SCREENS §8.4; 04 T-CON-13; POL-042): the figures of the
 * approved version as they stand, its parameters with `no_change_attestation` true, the effective
 * date and the rationale of the attestation.
 */
export function attestationBody(
  approved: EstimateVersion,
  effectiveDate: string,
  rationale: string,
): EstimateVersionCreateBody {
  const body: EstimateVersionCreateBody = {
    effective_date: effectiveDate,
    rationale,
    scenarios: scenariosOf(approved).map((item) => ({
      outcome: item.outcome,
      amount: item.amount,
      ...(item.probability === null ? {} : { probability: item.probability }),
    })),
    parameters: { ...approved.parameters, [NO_CHANGE]: true },
    // The factors the approved version marks, as the five booleans the API takes; none where the
    // approved version holds no checklist.
    constraint_checklist:
      approved.constraint_checklist === null
        ? null
        : checklistOf((factor) => factorsOf(approved).includes(factor)),
  };
  const target = body as Record<string, unknown>;
  const source = approved as unknown as Readonly<Record<string, unknown>>;
  for (const name of VALUE_COLUMNS) {
    target[name] = source[name] ?? null;
  }
  return body;
}

// ---------------------------------------------------------------------------------------------------
// The "Add estimated element" form.

export interface ElementForm {
  readonly kind: EstimateKind | null;
  readonly elementCode: string;
  readonly vcElementType: VcElementType | null;
  readonly method: EstimateMethod | null;
  /** The obligation the element names (T-CON-12 `obligation_id`), or null for the contract. */
  readonly obligationKey: string | null;
  readonly target: EstimateTarget;
  readonly targetKeys: readonly string[];
  readonly criteriaEvidence: string;
}

export const EMPTY_ELEMENT: ElementForm = {
  kind: null,
  elementCode: "",
  vcElementType: null,
  method: null,
  obligationKey: null,
  target: "CONTRACT",
  targetKeys: [],
  criteriaEvidence: "",
};

/** The method a kind starts with; every E-10 method stays selectable until the element is stored. */
export function defaultMethod(kind: EstimateKind): EstimateMethod | null {
  switch (kind) {
    case "VARIABLE_CONSIDERATION":
      return null;
    case "EAC":
      return "COST_BUILDUP";
    case "RETURN_RATE":
    case "BREAKAGE":
    case "EXERCISE_LIKELIHOOD":
      return "RATE";
    default:
      return "ENTERED_AMOUNT";
  }
}

export interface BuiltElement {
  readonly body: EstimateCreateBody | null;
  readonly errors: Readonly<Record<string, string>>;
}

/** Every check of the element form, then the body of `POST /contracts/{id}/estimates`. */
export function buildElement(form: ElementForm): BuiltElement {
  const errors: Record<string, string> = {};
  if (form.kind === null) {
    errors.estimate_kind = t("contracts.drawer.choose");
  }
  const code = form.elementCode.trim();
  if (code === "") {
    errors.element_code = t("contracts.estimates.error.elementCode");
  } else if (!ELEMENT_CODE.test(code)) {
    errors.element_code = t("contracts.estimates.error.elementCodeFormat");
  }
  const variable = form.kind === "VARIABLE_CONSIDERATION";
  if (variable && form.vcElementType === null) {
    errors.vc_element_type = t("contracts.drawer.choose");
  }
  if (form.method === null) {
    errors.method = t("contracts.drawer.choose");
  }
  const targeted = form.target === "OBLIGATIONS";
  if (targeted && form.targetKeys.length === 0) {
    errors.target_obligation_keys = t("contracts.estimates.error.targets");
  }
  const evidence = blankToNull(form.criteriaEvidence);
  if (form.target !== "CONTRACT" && evidence === null) {
    errors.allocation_criteria_evidence = t("contracts.estimates.error.criteriaEvidence");
  } else if (evidence !== null && evidence.length > MEMO_MAX_LENGTH) {
    errors.allocation_criteria_evidence = t("contracts.estimates.error.tooLong", {
      max: countText(MEMO_MAX_LENGTH),
    });
  }
  if (Object.keys(errors).length > 0 || form.kind === null || form.method === null) {
    return { body: null, errors };
  }
  return {
    body: {
      estimate_kind: form.kind,
      element_code: code,
      method: form.method,
      allocation_target: form.target,
      target_obligation_keys: targeted ? [...form.targetKeys] : [],
      vc_element_type: variable ? form.vcElementType : null,
      obligation_key: form.obligationKey,
      allocation_criteria_evidence: form.target === "CONTRACT" ? null : evidence,
    },
    errors: {},
  };
}

/** T-CON-12 `method`: fixed once a version of the element is approved (POL-040; SCREENS §8.3). */
export function methodLocked(element: Pick<Estimate, "current_version">): boolean {
  return element.current_version !== null;
}
