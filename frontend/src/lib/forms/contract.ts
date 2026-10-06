// Draft contract form (SCREENS §4.10 SF-03:new, SF-03:edit; 04 §16.1 API-S-ContractCreate, API-S-ContractLine,
// E-77; DESIGN_SYSTEM DS-CMP-21; docs/dev-guide.md DG-FE-06, DG-FE-20; BUILD_SPEC CTR-24). The form holds
// what the user typed as text. `buildDraft` runs every check of the form (required fields, formats and
// the cross-field rules "Enter an end date on or after <start date>." and "Obligation key <key> is used
// twice.") and, when nothing is wrong, answers the API-S-ContractCreate body: amounts through
// `parseMoneyInput` as decimal strings, dates through `parseDateInput` as business dates. `draftFromBooking`
// reads the booking a draft was last saved with and carries the members this form does not edit, so that
// "Save draft" on SF-03:edit sends them back unchanged. `placeProblem` maps the `errors[]` of a 422
// `validation-failed` onto the fields and the grid cells.
import type { ApiProblem } from "../api/problems";
import type { components } from "../api/schema";
import {
  formatDate,
  formatMoney,
  formatNumber,
  minorUnitOf,
  parseDateInput,
  parseMoneyInput,
} from "../format";
import { t } from "../i18n/t";

export type ContractCreateBody = components["schemas"]["ContractCreateIn"];
export type ContractLineBody = components["schemas"]["ContractLineIn"];
export type ScopeFlag = components["schemas"]["ScopeFlag"];
export type TerminationParty = components["schemas"]["TerminationV1"]["party"];

/** E-77 literals in 04 order; the first is the default "In scope (ASC 606)". */
export const SCOPE_FLAGS: readonly ScopeFlag[] = [
  "IN_SCOPE_606",
  "LEASE_842",
  "INSURANCE_944",
  "FINANCIAL_INSTRUMENT",
  "GUARANTEE_460",
  "CONTRIBUTION_958_605",
  "NONFINANCIAL_ASSET_610_20",
  "ALTERNATIVE_REVENUE_980_605",
  "COLLABORATION_808",
];
export const IN_SCOPE: ScopeFlag = "IN_SCOPE_606";
export const TERMINATION_PARTIES: readonly TerminationParty[] = [
  "NONE",
  "CUSTOMER",
  "ENTITY",
  "BOTH",
];
/** SCREENS §4.10: at most 500 lines (API-S-ContractCreate `lines`). */
export const MAX_LINES = 500;
/** 04 `Key`: identifiers hold 1 to 255 characters. */
export const KEY_MAX_LENGTH = 255;

export type YesNo = "YES" | "NO";

/** The customer of the draft: one on file, or one the save creates (`customer {code, name}`). */
export type DraftCustomer =
  | { readonly kind: "existing"; readonly id: string }
  | { readonly kind: "new"; readonly name: string };

/** SCREENS §4.10 lines grid columns, in order. */
export const LINE_COLUMNS = [
  "obligationKey",
  "product",
  "stratification",
  "quantity",
  "totalPrice",
  "unitPrice",
  "startDate",
  "endDate",
  "performingEntity",
  "sspVersion",
  "scope",
  "outOfScopeAmount",
  "memo1",
  "memo2",
  "memo3",
] as const;
export type DraftColumn = (typeof LINE_COLUMNS)[number];

/** Members of API-S-ContractLine the grid does not edit. */
export interface CarriedLine {
  readonly account_overrides: NonNullable<ContractLineBody["account_overrides"]> | null;
  readonly bundle_parent_obligation_key: string | null;
  readonly custom_attributes: NonNullable<ContractLineBody["custom_attributes"]> | null;
  readonly ssp_override_justification: string | null;
}

export interface DraftLine {
  /** The row's identity in the form; never sent. */
  readonly id: string;
  readonly obligationKey: string;
  readonly productCode: string | null;
  readonly stratification: string;
  readonly quantity: string;
  readonly totalPrice: string;
  readonly unitPrice: string;
  readonly startDate: string;
  readonly endDate: string;
  /** Null: the contracting entity performs (the default). */
  readonly performingEntity: string | null;
  readonly sspVersion: string;
  readonly scope: ScopeFlag;
  readonly outOfScopeAmount: string;
  readonly memo1: string;
  readonly memo2: string;
  readonly memo3: string;
  readonly carried: CarriedLine;
}

/** Members of API-S-ContractCreate the form does not edit. */
export interface CarriedBooking {
  readonly consideration_payable: ContractCreateBody["consideration_payable"];
  readonly noncash_consideration: ContractCreateBody["noncash_consideration"];
  readonly payment_schedule: ContractCreateBody["payment_schedule"];
  readonly custom_attributes: NonNullable<ContractCreateBody["custom_attributes"]> | null;
  readonly scope_605_35: boolean;
  readonly renewal_of_contract_id: string | null;
}

export interface DraftForm {
  readonly externalId: string;
  readonly customer: DraftCustomer | null;
  /** The code of a customer the save creates. */
  readonly customerCode: string;
  readonly entity: string | null;
  readonly currency: string | null;
  readonly inceptionDate: string;
  readonly signatureDate: string;
  readonly documentRef: string;
  readonly paymentTerms: string;
  readonly terminationParty: TerminationParty | null;
  readonly hasPenalty: YesNo | null;
  readonly noticeDays: string;
  readonly hasCommercialSubstance: boolean;
  readonly region: string;
  readonly channel: string;
  readonly contractType: string;
  readonly memo1: string;
  readonly memo2: string;
  readonly memo3: string;
  readonly lines: readonly DraftLine[];
  readonly carried: CarriedBooking;
}

const NO_CARRIED_LINE: CarriedLine = {
  account_overrides: null,
  bundle_parent_obligation_key: null,
  custom_attributes: null,
  ssp_override_justification: null,
};

const NO_CARRIED_BOOKING: CarriedBooking = {
  consideration_payable: [],
  noncash_consideration: [],
  payment_schedule: [],
  custom_attributes: null,
  scope_605_35: false,
  renewal_of_contract_id: null,
};

/** The field name of a grid cell: the `Field` id, the error key and the error summary link target. */
export function lineField(lineId: string, column: string): string {
  return `line-${lineId}-${column}`;
}

/** The field name of the grid as a whole ("Add at least one line."). */
export const LINES_FIELD = "lines";

/** What a grid cell holds: the typed text, or the chosen option ("" while none is chosen). */
export function lineValue(
  line: DraftLine,
  column: DraftColumn,
  contractingEntity: string | null,
): string {
  switch (column) {
    case "product":
      return line.productCode ?? "";
    case "performingEntity":
      // The contracting entity performs unless the line names another entity.
      return line.performingEntity ?? contractingEntity ?? "";
    case "scope":
      return line.scope;
    default:
      return line[column];
  }
}

/** The change of a line when a grid cell takes `value`. */
export function linePatch(
  column: DraftColumn,
  value: string,
  contractingEntity: string | null,
): Partial<DraftLine> {
  switch (column) {
    case "product":
      return { productCode: value === "" ? null : value };
    case "performingEntity":
      return { performingEntity: value === "" || value === contractingEntity ? null : value };
    case "scope": {
      const scope = SCOPE_FLAGS.find((flag) => flag === value) ?? IN_SCOPE;
      // An in-scope line has no out-of-scope amount.
      return scope === IN_SCOPE ? { scope, outOfScopeAmount: "" } : { scope };
    }
    default:
      return { [column]: value };
  }
}

const KEY_NUMBER = /^O(\d+)$/;

/** "O<n>" after the highest numbered key in use: the key a new line starts with. */
export function nextObligationKey(lines: readonly Pick<DraftLine, "obligationKey">[]): string {
  const highest = lines.reduce((found, line) => {
    const match = KEY_NUMBER.exec(line.obligationKey.trim());
    return match === null ? found : Math.max(found, Number(match[1]));
  }, 0);
  return `O${String(highest + 1)}`;
}

export function emptyLine(id: string, obligationKey: string): DraftLine {
  return {
    id,
    obligationKey,
    productCode: null,
    stratification: "",
    quantity: "",
    totalPrice: "",
    unitPrice: "",
    startDate: "",
    endDate: "",
    performingEntity: null,
    sspVersion: "",
    scope: IN_SCOPE,
    outOfScopeAmount: "",
    memo1: "",
    memo2: "",
    memo3: "",
    carried: NO_CARRIED_LINE,
  };
}

/** SF-03:new: no value but the checked "Commercial substance" and one line keyed "O1". */
export function emptyDraft(firstLineId: string): DraftForm {
  return {
    externalId: "",
    customer: null,
    customerCode: "",
    entity: null,
    currency: null,
    inceptionDate: "",
    signatureDate: "",
    documentRef: "",
    paymentTerms: "",
    terminationParty: null,
    hasPenalty: null,
    noticeDays: "",
    hasCommercialSubstance: true,
    region: "",
    channel: "",
    contractType: "",
    memo1: "",
    memo2: "",
    memo3: "",
    lines: [emptyLine(firstLineId, "O1")],
    carried: NO_CARRIED_BOOKING,
  };
}

/** The currency's minor unit is registered, so its amounts parse and echo (DS-FMT-03). */
export function currencyKnown(currency: string | null): currency is string {
  if (currency === null) {
    return false;
  }
  try {
    minorUnitOf(currency);
    return true;
  } catch {
    return false;
  }
}

function tooLong(): string {
  return t("contracts.draft.error.tooLong", {
    limit: formatNumber(KEY_MAX_LENGTH, { kind: "count" }),
  });
}

export function blankToNull(text: string): string | null {
  const value = text.trim();
  return value === "" ? null : value;
}

const PLAIN_DECIMAL = /^-?\d+(?:\.\d+)?$/;

/** A typed decimal without grouping, as the DataGrid's decimal editor reads one; null when it is none. */
export function decimalOf(text: string): string | null {
  const value = text.trim().replace(/[\s,]/g, "");
  return PLAIN_DECIMAL.test(value) ? value : null;
}

function isZero(decimal: string): boolean {
  return !/[1-9]/.test(decimal);
}

/** The business date of typed text; null when the text is no date. */
export function dateOf(text: string): string | null {
  const parsed = parseDateInput(text);
  return parsed.ok ? parsed.value : null;
}

/** DS-CMP-21 money messages of typed text; null when it parses. */
export function moneyError(text: string, currency: string): string | null {
  const parsed = parseMoneyInput(text, currency);
  if (parsed.ok) {
    return null;
  }
  if (parsed.error === "invalid") {
    return t("common.form.money.invalid");
  }
  const unit = minorUnitOf(currency);
  return unit === 0
    ? t("common.form.money.noDecimals")
    : t("common.form.money.tooManyDecimals", { count: unit });
}

/** The API decimal string of typed money (DG-FE-06): never a number. */
export function moneyOf(text: string, currency: string): string | null {
  const parsed = parseMoneyInput(text, currency);
  return parsed.ok ? parsed.value : null;
}

export interface BuiltDraft {
  /** The API-S-ContractCreate body, or null while a field is wrong. */
  readonly body: ContractCreateBody | null;
  /** Field name → message, in form order. */
  readonly errors: Readonly<Record<string, string>>;
}

/** Every check of the form, then the body (SCREENS §4.10; DS-CMP-21 "all checks run on submit"). */
export function buildDraft(form: DraftForm): BuiltDraft {
  const errors: Record<string, string> = {};
  const externalId = form.externalId.trim();
  if (externalId === "") {
    errors.externalId = t("contracts.draft.error.externalId");
  } else if (externalId.length > KEY_MAX_LENGTH) {
    errors.externalId = tooLong();
  }
  const customerCode = form.customerCode.trim();
  if (form.customer === null) {
    errors.customer = t("contracts.draft.error.customer");
  } else if (form.customer.kind === "new") {
    if (form.customer.name.trim().length > KEY_MAX_LENGTH) {
      errors.customer = tooLong();
    }
    if (customerCode === "") {
      errors.customerCode = t("contracts.draft.error.customerCode");
    } else if (customerCode.length > KEY_MAX_LENGTH) {
      errors.customerCode = tooLong();
    }
  }
  if (form.entity === null) {
    errors.entity = t("contracts.draft.error.entity");
  }
  const currency = currencyKnown(form.currency) ? form.currency : null;
  if (currency === null) {
    errors.currency = t("contracts.draft.error.currency");
  }
  const inception = dateOf(form.inceptionDate);
  if (form.inceptionDate.trim() === "") {
    errors.inceptionDate = t("contracts.draft.error.inceptionDate");
  } else if (inception === null) {
    errors.inceptionDate = t("common.form.date.invalid");
  }
  const signature = dateOf(form.signatureDate);
  if (form.signatureDate.trim() !== "" && signature === null) {
    errors.signatureDate = t("common.form.date.invalid");
  }
  const hasRight = form.terminationParty !== null && form.terminationParty !== "NONE";
  const noticeDays = form.noticeDays.trim();
  if (hasRight && noticeDays !== "" && !/^\d+$/.test(noticeDays)) {
    errors.noticeDays = t("contracts.draft.error.noticeDays");
  }
  if (form.lines.length === 0) {
    errors[LINES_FIELD] = t("contracts.draft.error.noLines");
  } else if (form.lines.length > MAX_LINES) {
    errors[LINES_FIELD] = t("contracts.draft.error.tooManyLines", {
      limit: formatNumber(MAX_LINES, { kind: "count" }),
    });
  }

  const seen = new Set<string>();
  const lines: ContractLineBody[] = [];
  for (const line of form.lines) {
    const at = (column: DraftColumn) => lineField(line.id, column);
    const key = line.obligationKey.trim();
    if (key === "") {
      errors[at("obligationKey")] = t("contracts.draft.error.obligationKey");
    } else if (key.length > KEY_MAX_LENGTH) {
      errors[at("obligationKey")] = tooLong();
    } else if (seen.has(key)) {
      errors[at("obligationKey")] = t("contracts.draft.error.duplicateKey", { key });
    }
    seen.add(key);
    if (line.productCode === null) {
      errors[at("product")] = t("contracts.draft.error.product");
    }
    const quantity = decimalOf(line.quantity);
    if (quantity === null) {
      errors[at("quantity")] = t("contracts.draft.error.quantity");
    } else if (isZero(quantity)) {
      errors[at("quantity")] = t("contracts.draft.error.quantityZero");
    }
    let totalPrice: string | null = null;
    if (line.totalPrice.trim() === "") {
      errors[at("totalPrice")] = t("contracts.draft.error.totalPrice");
    } else if (currency !== null) {
      totalPrice = moneyOf(line.totalPrice, currency);
      const message = moneyError(line.totalPrice, currency);
      if (message !== null) {
        errors[at("totalPrice")] = message;
      }
    }
    const unitPrice = line.unitPrice.trim() === "" ? null : decimalOf(line.unitPrice);
    if (line.unitPrice.trim() !== "" && unitPrice === null) {
      errors[at("unitPrice")] = t("contracts.draft.error.unitPrice");
    }
    const start = parseDateInput(line.startDate);
    const end = parseDateInput(line.endDate);
    if (line.startDate.trim() !== "" && !start.ok) {
      errors[at("startDate")] = t("common.form.date.invalid");
    }
    if (line.endDate.trim() !== "" && !end.ok) {
      errors[at("endDate")] = t("common.form.date.invalid");
    } else if (start.ok && end.ok && end.value < start.value) {
      errors[at("endDate")] = t("contracts.draft.error.endBeforeStart", {
        start: formatDate(start.value),
      });
    }
    const outOfScope = line.scope !== IN_SCOPE;
    let outOfScopeAmount: string | null = null;
    if (outOfScope) {
      if (line.outOfScopeAmount.trim() === "") {
        errors[at("outOfScopeAmount")] = t("contracts.draft.error.outOfScopeAmount");
      } else if (currency !== null) {
        outOfScopeAmount = moneyOf(line.outOfScopeAmount, currency);
        const message = moneyError(line.outOfScopeAmount, currency);
        if (message !== null) {
          errors[at("outOfScopeAmount")] = message;
        }
      }
    }
    if (
      line.productCode !== null &&
      quantity !== null &&
      totalPrice !== null &&
      currency !== null
    ) {
      lines.push({
        obligation_key: key,
        product_code: line.productCode,
        stratification: blankToNull(line.stratification),
        quantity,
        total_price: { amount: totalPrice, currency },
        unit_price: unitPrice,
        start_date: dateOf(line.startDate),
        end_date: dateOf(line.endDate),
        performing_entity_code: line.performingEntity,
        ssp_version_label: blankToNull(line.sspVersion),
        scope_flag: line.scope,
        out_of_scope_amount:
          outOfScope && outOfScopeAmount !== null ? { amount: outOfScopeAmount, currency } : null,
        memo_1: blankToNull(line.memo1),
        memo_2: blankToNull(line.memo2),
        memo_3: blankToNull(line.memo3),
        ...line.carried,
      } satisfies ContractLineBody);
    }
  }

  if (
    Object.keys(errors).length > 0 ||
    form.customer === null ||
    form.entity === null ||
    currency === null ||
    inception === null
  ) {
    return { body: null, errors };
  }
  const body = {
    external_id: externalId,
    ...(form.customer.kind === "existing"
      ? { customer_id: form.customer.id }
      : { customer: { code: customerCode, name: form.customer.name.trim() } }),
    contracting_entity_code: form.entity,
    transaction_currency: currency,
    inception_date: inception,
    signature_date: signature,
    document_ref: blankToNull(form.documentRef),
    payment_terms: blankToNull(form.paymentTerms),
    termination:
      form.terminationParty === null
        ? null
        : {
            party: form.terminationParty,
            has_penalty: hasRight && form.hasPenalty !== null ? form.hasPenalty === "YES" : null,
            notice_days: hasRight && noticeDays !== "" ? Number(noticeDays) : null,
          },
    has_commercial_substance: form.hasCommercialSubstance,
    region: blankToNull(form.region),
    channel: blankToNull(form.channel),
    contract_type: blankToNull(form.contractType),
    memo_1: blankToNull(form.memo1),
    memo_2: blankToNull(form.memo2),
    memo_3: blankToNull(form.memo3),
    lines,
    // Activation is its own command: the API refuses the flag (04 §16.1; L3-1-Q-43).
    submit_for_activation: false,
    ...form.carried,
  } satisfies ContractCreateBody;
  return { body, errors };
}

function record(value: unknown): Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Readonly<Record<string, unknown>>)
    : {};
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function nullable(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

/** A stored business date as the date input echoes it; an unreadable value stays as it is stored. */
function dateText(value: unknown): string {
  if (typeof value !== "string") {
    return "";
  }
  const parsed = parseDateInput(value);
  return parsed.ok ? formatDate(parsed.value) : value;
}

/** A stored amount as the money input echoes it, once the currency's minor unit is known. */
function moneyText(value: unknown, currency: string): string {
  const amount = record(value).amount;
  if (typeof amount !== "string") {
    return "";
  }
  return currencyKnown(currency) && PLAIN_DECIMAL.test(amount)
    ? formatMoney(amount, currency, { variant: "cell" })
    : amount;
}

function scopeOf(value: unknown): ScopeFlag {
  return SCOPE_FLAGS.find((flag) => flag === value) ?? IN_SCOPE;
}

function partyOf(value: unknown): TerminationParty | null {
  return TERMINATION_PARTIES.find((party) => party === value) ?? null;
}

/** What SF-03:edit reads of the contract beside its booking (API-S-Contract). */
export interface BookedContract {
  readonly external_id: string;
  readonly customer: { readonly id: string };
  readonly contracting_entity: { readonly code: string };
  readonly transaction_currency: string;
}

/**
 * The form of a draft from its latest `CONTRACT_BOOKED` payload (04 §16.3: the API-S-ContractCreate
 * members with the resolved `customer_id`). The external id, the contracting entity and the currency come
 * from the contract itself: a replacement keeps them (04 §16.1). The caller opens the form only while
 * that payload still is the draft (`draftEditOf`, ruling R-93 (a)).
 */
export function draftFromBooking(
  contract: BookedContract,
  payload: unknown,
  lineId: (index: number) => string,
): DraftForm {
  const booking = record(payload);
  const currency = contract.transaction_currency;
  const termination = record(booking.termination);
  const penalty = termination.has_penalty;
  const days = termination.notice_days;
  const rows = Array.isArray(booking.lines) ? (booking.lines as readonly unknown[]) : [];
  return {
    externalId: contract.external_id,
    customer: {
      kind: "existing",
      id: typeof booking.customer_id === "string" ? booking.customer_id : contract.customer.id,
    },
    customerCode: "",
    entity: contract.contracting_entity.code,
    currency,
    inceptionDate: dateText(booking.inception_date),
    signatureDate: dateText(booking.signature_date),
    documentRef: text(booking.document_ref),
    paymentTerms: text(booking.payment_terms),
    terminationParty: partyOf(termination.party),
    hasPenalty: typeof penalty === "boolean" ? (penalty ? "YES" : "NO") : null,
    noticeDays: typeof days === "number" ? String(days) : "",
    hasCommercialSubstance: booking.has_commercial_substance !== false,
    region: text(booking.region),
    channel: text(booking.channel),
    contractType: text(booking.contract_type),
    memo1: text(booking.memo_1),
    memo2: text(booking.memo_2),
    memo3: text(booking.memo_3),
    lines: rows.map((row, index) => {
      const line = record(row);
      const performing = nullable(line.performing_entity_code);
      return {
        id: lineId(index),
        obligationKey: text(line.obligation_key),
        productCode: nullable(line.product_code),
        stratification: text(line.stratification),
        quantity: text(line.quantity),
        totalPrice: moneyText(line.total_price, currency),
        unitPrice: text(line.unit_price),
        startDate: dateText(line.start_date),
        endDate: dateText(line.end_date),
        performingEntity: performing === contract.contracting_entity.code ? null : performing,
        sspVersion: text(line.ssp_version_label),
        scope: scopeOf(line.scope_flag),
        outOfScopeAmount: moneyText(line.out_of_scope_amount, currency),
        memo1: text(line.memo_1),
        memo2: text(line.memo_2),
        memo3: text(line.memo_3),
        carried: {
          account_overrides: (line.account_overrides as CarriedLine["account_overrides"]) ?? null,
          bundle_parent_obligation_key: nullable(line.bundle_parent_obligation_key),
          custom_attributes: (line.custom_attributes as CarriedLine["custom_attributes"]) ?? null,
          ssp_override_justification: nullable(line.ssp_override_justification),
        },
      };
    }),
    carried: {
      consideration_payable: Array.isArray(booking.consideration_payable)
        ? (booking.consideration_payable as ContractCreateBody["consideration_payable"])
        : [],
      noncash_consideration: Array.isArray(booking.noncash_consideration)
        ? (booking.noncash_consideration as ContractCreateBody["noncash_consideration"])
        : [],
      payment_schedule: Array.isArray(booking.payment_schedule)
        ? (booking.payment_schedule as ContractCreateBody["payment_schedule"])
        : [],
      custom_attributes: (booking.custom_attributes as CarriedBooking["custom_attributes"]) ?? null,
      scope_605_35: booking.scope_605_35 === true,
      renewal_of_contract_id: nullable(booking.renewal_of_contract_id),
    },
  };
}

// API-S-ContractCreate member → form field.
const HEADER_FIELDS: Readonly<Record<string, string>> = {
  external_id: "externalId",
  customer_id: "customer",
  customer: "customer",
  "customer.name": "customer",
  "customer.code": "customerCode",
  // The customer a booking creates is refused by the customer command, which names its own members.
  code: "customerCode",
  name: "customer",
  contracting_entity_code: "entity",
  transaction_currency: "currency",
  inception_date: "inceptionDate",
  signature_date: "signatureDate",
  document_ref: "documentRef",
  payment_terms: "paymentTerms",
  termination: "terminationParty",
  "termination.party": "terminationParty",
  "termination.has_penalty": "hasPenalty",
  "termination.notice_days": "noticeDays",
  region: "region",
  channel: "channel",
  contract_type: "contractType",
  memo_1: "memo1",
  memo_2: "memo2",
  memo_3: "memo3",
  lines: LINES_FIELD,
};

// API-S-ContractLine member → grid column.
const LINE_FIELDS: Readonly<Record<string, DraftColumn>> = {
  obligation_key: "obligationKey",
  product_code: "product",
  stratification: "stratification",
  quantity: "quantity",
  total_price: "totalPrice",
  unit_price: "unitPrice",
  start_date: "startDate",
  end_date: "endDate",
  performing_entity_code: "performingEntity",
  ssp_version_label: "sspVersion",
  scope_flag: "scope",
  out_of_scope_amount: "outOfScopeAmount",
  memo_1: "memo1",
  memo_2: "memo2",
  memo_3: "memo3",
};

const LINE_POINTER = /^lines\.(\d+)(?:\.([a-z_0-9]+))?/;

export interface PlacedProblem {
  /** Field name → the server's message; the first message of a field wins. */
  readonly fields: Readonly<Record<string, string>>;
  /** Messages whose pointer names no field of the form. */
  readonly unplaced: readonly string[];
}

/**
 * Maps `errors[]` of a problem onto the form (DS-CMP-21 "server errors map to fields by their pointer"):
 * `external_id` to its field, `lines.<n>.<member>` to the cell of row n, and a rule of the whole row
 * (`lines.<n>`, for example the end date before the start date) to the row's first cell.
 */
export function placeProblem(problem: ApiProblem, form: DraftForm): PlacedProblem {
  const fields: Record<string, string> = {};
  const unplaced: string[] = [];
  for (const error of problem.errors) {
    const pointer = error.field ?? "";
    const line = LINE_POINTER.exec(pointer);
    let name: string | undefined;
    if (line !== null) {
      const row = form.lines[Number(line[1])];
      const column = line[2] === undefined ? "obligationKey" : LINE_FIELDS[line[2]];
      name = row === undefined || column === undefined ? undefined : lineField(row.id, column);
    } else {
      name = HEADER_FIELDS[pointer];
    }
    if (name === undefined) {
      unplaced.push(error.message);
    } else if (!(name in fields)) {
      fields[name] = error.message;
    }
  }
  return { fields, unplaced };
}
