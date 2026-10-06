// Modification wizard models (SCREENS §7.3 to §7.8; 04 API-R-31, §16.14 API-S-Modification, T-CON-06;
// ENGINE_SPEC S06-R-19; PRD BR-MOD-01, SM-03; docs/dev-guide.md DG-FE-06; BUILD_SPEC CTR-27).
//
// Step "Change" holds what the user typed as text. `buildChange` checks the general form (kind,
// reference, effective date, scope description and the lines, or the one price change of kind
// `PRICE_CHANGE`) and answers the API-S-Modification body; `buildSubscription` does the same for a
// subscription action, whose one line has the S06-R-19 shape of its kind. Amounts go through
// `parseMoneyInput` as decimal strings and dates through `parseDateInput` as business dates.
//
// The questionnaire: `/classify` proposes the answers the system can compute and stores none, so a
// group is confirmed only when every question it shows has a stored answer — the preparer confirmed
// the group or changed the answer (BR-MOD-01; ruling R-82 (h)). `questionGroups` reads the stored
// answers of the row beside the proposals of the last classification.
import type {
  Modification,
  ModificationCreateBody,
  ModificationKind,
  ModificationLineBody,
  ModificationTreatment,
  Question,
} from "../api/queries/modifications";
import { addDays, formatDate, formatMoney, formatNumber, parseDateInput } from "../format";
import { t } from "../i18n/t";
import {
  blankToNull,
  currencyKnown,
  dateOf,
  decimalOf,
  KEY_MAX_LENGTH,
  MAX_LINES,
  moneyError,
  moneyOf,
} from "./contract";

export type LineAction = ModificationLineBody["action"];
/** T-CON-06 line actions in the order of the SCREENS §7.4 select: "Add", "Remove", "Change". */
export const LINE_ACTIONS: readonly LineAction[] = ["ADD", "REMOVE", "CHANGE"];

/** SCREENS §4.1.6 "Change subscription" items: the SF-07 `action` parameter (SCR-URL-31). */
export const SUBSCRIPTION_ACTIONS = [
  "upgrade",
  "downgrade",
  "co_term",
  "renew",
  "early_renew",
  "cancel",
] as const;
export type SubscriptionAction = (typeof SUBSCRIPTION_ACTIONS)[number];

/** 04 E-25: the kind each subscription action creates (API-R-31). */
export const SUBSCRIPTION_KIND: Readonly<Record<SubscriptionAction, ModificationKind>> = {
  upgrade: "UPGRADE",
  downgrade: "DOWNGRADE",
  co_term: "CO_TERM",
  renew: "RENEWAL",
  early_renew: "EARLY_RENEWAL",
  cancel: "CANCELLATION",
};

export function subscriptionActionOf(value: string | null): SubscriptionAction | null {
  return SUBSCRIPTION_ACTIONS.find((action) => action === value) ?? null;
}

/** What the forms read of an obligation of the contract. */
export interface ObligationFacts {
  readonly key: string;
  readonly productCode: string;
  readonly endDate: string | null;
}

/** What the builders read of the contract. */
export interface ChangeContext {
  readonly externalId: string;
  readonly currency: string;
  readonly obligations: readonly ObligationFacts[];
}

// ---------------------------------------------------------------------------------------------------
// The general form.

/** SCREENS §7.4 lines grid columns, in order. */
export const CHANGE_COLUMNS = [
  "action",
  "obligationKey",
  "product",
  "quantityChange",
  "considerationChange",
  "startDate",
  "endDate",
  "performingEntity",
  "sspVersion",
  "memo1",
  "memo2",
  "memo3",
] as const;
export type ChangeColumn = (typeof CHANGE_COLUMNS)[number];

/** Line members the grid does not edit; an edit of a draft sends them back as it holds them. */
export interface CarriedChangeLine {
  readonly account_codes: NonNullable<ModificationLineBody["account_codes"]> | null;
  readonly stratification: string | null;
}

const NO_CARRIED_LINE: CarriedChangeLine = { account_codes: null, stratification: null };

export interface ChangeLine {
  readonly id: string;
  readonly action: LineAction | null;
  readonly obligationKey: string;
  readonly productCode: string | null;
  readonly quantityChange: string;
  readonly considerationChange: string;
  readonly startDate: string;
  readonly endDate: string;
  /** Null: the contracting entity performs. */
  readonly performingEntity: string | null;
  readonly sspVersion: string;
  readonly memo1: string;
  readonly memo2: string;
  readonly memo3: string;
  readonly carried: CarriedChangeLine;
}

export interface ChangeForm {
  readonly kind: ModificationKind | null;
  readonly reference: string;
  readonly effectiveDate: string;
  readonly rationale: string;
  readonly lines: readonly ChangeLine[];
  /** Kind `PRICE_CHANGE`: the obligation whose price changes and the amount (SCREENS §7.4). */
  readonly priceObligationKey: string | null;
  readonly priceChangeAmount: string;
}

export const CHANGE_LINES_FIELD = "lines";
export const PRICE_CHANGE: ModificationKind = "PRICE_CHANGE";

export function changeLineField(lineId: string, column: string): string {
  return `line-${lineId}-${column}`;
}

export function emptyChangeLine(id: string): ChangeLine {
  return {
    id,
    action: null,
    obligationKey: "",
    productCode: null,
    quantityChange: "",
    considerationChange: "",
    startDate: "",
    endDate: "",
    performingEntity: null,
    sspVersion: "",
    memo1: "",
    memo2: "",
    memo3: "",
    carried: NO_CARRIED_LINE,
  };
}

/** A new general modification; `kind` and `obligationKey` come from SCR-URL-31 when the link names them. */
export function emptyChange(
  firstLineId: string,
  kind: ModificationKind | null = null,
  obligationKey: string | null = null,
): ChangeForm {
  return {
    kind,
    reference: "",
    effectiveDate: "",
    rationale: "",
    lines: [emptyChangeLine(firstLineId)],
    priceObligationKey: obligationKey,
    priceChangeAmount: "",
  };
}

/** The value of a grid cell as its control holds it. */
export function changeLineValue(line: ChangeLine, column: ChangeColumn): string {
  switch (column) {
    case "action":
      return line.action ?? "";
    case "product":
      return line.productCode ?? "";
    case "performingEntity":
      return line.performingEntity ?? "";
    default:
      return line[column];
  }
}

/** The change of a line when a grid cell takes `value`. Only an added line names a product. */
export function changeLinePatch(column: ChangeColumn, value: string): Partial<ChangeLine> {
  switch (column) {
    case "action": {
      const action = LINE_ACTIONS.find((candidate) => candidate === value) ?? null;
      return action === "ADD" ? { action } : { action, productCode: null };
    }
    case "product":
      return { productCode: value === "" ? null : value };
    case "performingEntity":
      return { performingEntity: value === "" ? null : value };
    default:
      return { [column]: value };
  }
}

export interface BuiltModification {
  /** The API-S-Modification create body, or null while a field is wrong. */
  readonly body: ModificationCreateBody | null;
  /** Field name → message, in form order. */
  readonly errors: Readonly<Record<string, string>>;
}

function tooLong(limit: number): string {
  return t("contracts.draft.error.tooLong", { limit: formatNumber(limit, { kind: "count" }) });
}

function isZero(decimal: string): boolean {
  return !/[1-9]/.test(decimal);
}

function money(amount: string, currency: string) {
  return { amount, currency };
}

interface Header {
  readonly reference: string | null;
  readonly effectiveDate: string | null;
}

function checkHeader(
  form: Pick<ChangeForm, "reference" | "effectiveDate">,
  errors: Record<string, string>,
): Header {
  const reference = blankToNull(form.reference);
  if (reference === null) {
    errors.reference = t("modifications.wizard.error.reference");
  } else if (reference.length > 200) {
    errors.reference = tooLong(200);
  }
  const effectiveDate = dateOf(form.effectiveDate);
  if (effectiveDate === null) {
    errors.effectiveDate = t("modifications.wizard.error.effectiveDate");
  }
  return { reference, effectiveDate };
}

/** Every check of the general form, then the body (SCREENS §7.4; DS-CMP-21). */
export function buildChange(form: ChangeForm, context: ChangeContext): BuiltModification {
  const errors: Record<string, string> = {};
  const { currency } = context;
  const known = new Set(context.obligations.map((item) => item.key));
  if (form.kind === null) {
    errors.kind = t("modifications.wizard.error.kind");
  }
  const header = checkHeader(form, errors);
  if (form.rationale.length > 4000) {
    errors.rationale = tooLong(4000);
  }
  const lines: ModificationLineBody[] = [];
  let priceChangeAmount: string | null = null;

  if (form.kind === PRICE_CHANGE) {
    // SCREENS §7.4: one obligation, the amount, quantity fixed at 0 (IMP-33).
    const key = form.priceObligationKey;
    if (key === null || !known.has(key)) {
      errors.priceObligationKey = t("modifications.wizard.error.obligation");
    }
    const typed = form.priceChangeAmount.trim();
    const amount = typed === "" ? null : moneyOf(typed, currency);
    if (typed === "") {
      errors.priceChangeAmount = t("modifications.wizard.error.priceChangeAmount");
    } else if (amount === null) {
      errors.priceChangeAmount = moneyError(typed, currency) ?? t("common.form.money.invalid");
    } else if (isZero(amount)) {
      errors.priceChangeAmount = t("modifications.wizard.error.priceChangeAmount");
    }
    if (key !== null && amount !== null) {
      priceChangeAmount = amount;
      lines.push({
        action: "CHANGE",
        obligation_key: key,
        quantity_delta: "0",
        consideration_delta: money(amount, currency),
      });
    }
  } else {
    if (form.lines.length === 0) {
      errors[CHANGE_LINES_FIELD] = t("modifications.wizard.error.noLines");
    } else if (form.lines.length > MAX_LINES) {
      errors[CHANGE_LINES_FIELD] = t("contracts.draft.error.tooManyLines", {
        limit: formatNumber(MAX_LINES, { kind: "count" }),
      });
    }
    for (const line of form.lines) {
      const at = (column: ChangeColumn) => changeLineField(line.id, column);
      const key = line.obligationKey.trim();
      if (line.action === null) {
        errors[at("action")] = t("modifications.wizard.error.action");
      }
      if (key === "") {
        errors[at("obligationKey")] = t("contracts.draft.error.obligationKey");
      } else if (key.length > KEY_MAX_LENGTH) {
        errors[at("obligationKey")] = tooLong(KEY_MAX_LENGTH);
      } else if (line.action === "ADD" && known.has(key)) {
        errors[at("obligationKey")] = t("modifications.wizard.error.keyExists", { key });
      } else if (line.action !== null && line.action !== "ADD" && !known.has(key)) {
        errors[at("obligationKey")] = t("modifications.wizard.error.keyUnknown", {
          contract: context.externalId,
          key,
        });
      }
      if (line.action === "ADD" && line.productCode === null) {
        errors[at("product")] = t("modifications.wizard.error.product");
      }
      const quantityText = line.quantityChange.trim();
      const quantity = quantityText === "" ? "0" : decimalOf(quantityText);
      if (quantity === null) {
        errors[at("quantityChange")] = t("modifications.wizard.error.quantityChange");
      }
      const considerationText = line.considerationChange.trim();
      const consideration = considerationText === "" ? null : moneyOf(considerationText, currency);
      if (considerationText !== "" && consideration === null) {
        errors[at("considerationChange")] =
          moneyError(considerationText, currency) ?? t("common.form.money.invalid");
      }
      const start = line.startDate.trim() === "" ? null : dateOf(line.startDate);
      const end = line.endDate.trim() === "" ? null : dateOf(line.endDate);
      if (line.startDate.trim() !== "" && start === null) {
        errors[at("startDate")] = t("common.form.date.invalid");
      }
      if (line.endDate.trim() !== "" && end === null) {
        errors[at("endDate")] = t("common.form.date.invalid");
      } else if (start !== null && end !== null && end < start) {
        errors[at("endDate")] = t("contracts.draft.error.endBeforeStart", {
          start: formatDate(start),
        });
      }
      if (line.action !== null && quantity !== null) {
        lines.push({
          action: line.action,
          obligation_key: key,
          product_code: line.action === "ADD" ? line.productCode : null,
          quantity_delta: quantity,
          consideration_delta: consideration === null ? null : money(consideration, currency),
          start_date: start,
          end_date: end,
          selling_entity_code: line.performingEntity,
          ssp_version_label: blankToNull(line.sspVersion),
          memo_1: blankToNull(line.memo1),
          memo_2: blankToNull(line.memo2),
          memo_3: blankToNull(line.memo3),
          account_codes: line.carried.account_codes,
          stratification: line.carried.stratification,
        });
      }
    }
  }

  if (
    Object.keys(errors).length > 0 ||
    form.kind === null ||
    header.reference === null ||
    header.effectiveDate === null
  ) {
    return { body: null, errors };
  }
  return {
    body: {
      kind: form.kind,
      reference: header.reference,
      effective_date: header.effectiveDate,
      rationale: form.rationale.trim() === "" ? null : form.rationale.trim(),
      lines,
      ...(priceChangeAmount === null ? {} : { price_change_amount: priceChangeAmount }),
    } satisfies ModificationCreateBody,
    errors,
  };
}

function record(value: unknown): Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null
    ? (value as Readonly<Record<string, unknown>>)
    : {};
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function nullable(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

function dateText(value: unknown): string {
  if (typeof value !== "string") {
    return "";
  }
  const parsed = parseDateInput(value);
  return parsed.ok ? formatDate(parsed.value) : value;
}

const PLAIN_DECIMAL = /^-?\d+(?:\.\d+)?$/;

function moneyText(value: unknown, currency: string): string {
  const amount = record(value).amount;
  if (typeof amount !== "string") {
    return "";
  }
  return currencyKnown(currency) && PLAIN_DECIMAL.test(amount)
    ? formatMoney(amount, currency, { variant: "cell" })
    : amount;
}

/** The general form of a draft as it is stored (API-S-Modification `lines` are T-CON-06 JSON). */
export function changeFromModification(
  modification: Pick<
    Modification,
    | "kind"
    | "reference"
    | "effective_date"
    | "rationale"
    | "lines"
    | "price_change_amount"
    | "currency"
  >,
  lineId: (index: number) => string,
): ChangeForm {
  const { currency } = modification;
  const rows = modification.lines.map(record);
  const priced = modification.kind === PRICE_CHANGE ? rows[0] : undefined;
  return {
    kind: modification.kind,
    reference: modification.reference ?? "",
    effectiveDate: dateText(modification.effective_date),
    rationale: modification.rationale ?? "",
    priceObligationKey: priced === undefined ? null : nullable(priced.obligation_key),
    priceChangeAmount:
      modification.price_change_amount === null
        ? ""
        : moneyText({ amount: modification.price_change_amount }, currency),
    lines: rows.map((line, index) => {
      const quantity = text(line.quantity_delta);
      return {
        id: lineId(index),
        action: LINE_ACTIONS.find((action) => action === line.action) ?? null,
        obligationKey: text(line.obligation_key),
        productCode: nullable(line.product_code),
        quantityChange: quantity === "0" ? "" : quantity,
        considerationChange: moneyText(line.consideration_delta, currency),
        startDate: dateText(line.start_date),
        endDate: dateText(line.end_date),
        performingEntity: nullable(line.selling_entity_code),
        sspVersion: text(line.ssp_version_label),
        memo1: text(line.memo_1),
        memo2: text(line.memo_2),
        memo3: text(line.memo_3),
        carried: {
          account_codes: (line.account_codes as CarriedChangeLine["account_codes"]) ?? null,
          stratification: nullable(line.stratification),
        },
      };
    }),
  };
}

// ---------------------------------------------------------------------------------------------------
// A subscription action (SCREENS §7.4; ENGINE_SPEC S06-R-19).

export interface SubscriptionForm {
  readonly action: SubscriptionAction;
  readonly obligationKey: string | null;
  /** Co-term and renewals add an obligation: its key. */
  readonly newKey: string;
  readonly quantity: string;
  readonly price: string;
  readonly effectiveDate: string;
  /** Renewals: the end of the renewal term. */
  readonly endDate: string;
  readonly reference: string;
}

/** The actions whose line adds an obligation (S06-R-19 `ADD`). */
export const ADDING_ACTIONS: ReadonlySet<SubscriptionAction> = new Set([
  "co_term",
  "renew",
  "early_renew",
]);
/** The actions whose term the user ends: a renewal names its own end date. */
export const RENEWING_ACTIONS: ReadonlySet<SubscriptionAction> = new Set(["renew", "early_renew"]);

const KEY_NUMBER = /^O(\d+)$/;

/** The next free key of the pattern `O<n>` after the contract's obligations. */
export function nextKey(obligations: readonly ObligationFacts[]): string {
  const taken = obligations.flatMap((item) => {
    const match = KEY_NUMBER.exec(item.key);
    return match === null ? [] : [Number(match[1])];
  });
  return `O${String(Math.max(0, ...taken) + 1)}`;
}

/** A new subscription change; a contract with one obligation has it chosen. */
export function emptySubscription(
  action: SubscriptionAction,
  obligations: readonly ObligationFacts[],
): SubscriptionForm {
  return {
    action,
    obligationKey: obligations.length === 1 ? (obligations[0]?.key ?? null) : null,
    newKey: ADDING_ACTIONS.has(action) ? nextKey(obligations) : "",
    quantity: "",
    price: "",
    effectiveDate: "",
    endDate: "",
    reference: "",
  };
}

/** The decimal of a removed quantity or a reduction: the typed amount with the other sign. */
function removed(decimal: string): string {
  return isZero(decimal) ? decimal : `-${decimal}`;
}

/**
 * Every check of the subscription form, then the body: kind per 04 E-25 and one line of the S06-R-19
 * shape of that kind. `POST /contracts/{id}/subscription-changes` is not on main (CTR-18), so the body
 * is the one `POST /contracts/{id}/modifications` takes.
 */
export function buildSubscription(
  form: SubscriptionForm,
  context: ChangeContext,
): BuiltModification {
  const errors: Record<string, string> = {};
  const { currency } = context;
  const { action } = form;
  const obligation = context.obligations.find((item) => item.key === form.obligationKey) ?? null;
  if (obligation === null) {
    errors.obligationKey = t("modifications.wizard.error.obligation");
  } else if (obligation.endDate === null) {
    errors.obligationKey = t("modifications.wizard.error.noTermEnd", { key: obligation.key });
  }
  const adding = ADDING_ACTIONS.has(action);
  const newKey = form.newKey.trim();
  if (adding) {
    if (newKey === "") {
      errors.newKey = t("contracts.draft.error.obligationKey");
    } else if (newKey.length > KEY_MAX_LENGTH) {
      errors.newKey = tooLong(KEY_MAX_LENGTH);
    } else if (context.obligations.some((item) => item.key === newKey)) {
      errors.newKey = t("modifications.wizard.error.keyExists", { key: newKey });
    }
  }
  const quantityText = form.quantity.trim();
  const quantity = quantityText === "" ? "0" : decimalOf(quantityText);
  if (quantity === null || quantity.startsWith("-")) {
    errors.quantity = t("modifications.wizard.error.quantity");
  }
  const priceText = form.price.trim();
  const price = priceText === "" ? "0" : moneyOf(priceText, currency);
  if (price === null) {
    errors.price = moneyError(priceText, currency) ?? t("common.form.money.invalid");
  } else if (price.startsWith("-")) {
    errors.price = t("modifications.wizard.error.price");
  }
  if (quantity !== null && price !== null && errors.quantity === undefined) {
    const none = isZero(quantity) && isZero(price);
    if (adding && isZero(quantity)) {
      // S06-R-19: a co-term line and a renewal add units.
      errors.quantity = t("modifications.wizard.error.quantityRequired");
    } else if ((action === "upgrade" || action === "downgrade") && none) {
      errors.quantity = t("modifications.wizard.error.quantityOrPrice");
    }
  }
  const header = checkHeader(form, errors);
  const effective = header.effectiveDate;
  const termEnd = obligation?.endDate ?? null;
  const renewing = RENEWING_ACTIONS.has(action);
  if (effective !== null && termEnd !== null && action !== "renew" && effective > termEnd) {
    // S06-R-19: every action but a renewal is effective within the term.
    errors.effectiveDate = t("modifications.wizard.error.afterTerm", {
      end: formatDate(termEnd),
    });
  }
  const renewalStart = termEnd === null ? null : addDays(termEnd, 1);
  const renewalEnd = renewing ? dateOf(form.endDate) : null;
  if (renewing) {
    if (renewalEnd === null) {
      errors.endDate = t("modifications.wizard.error.renewalEnd");
    } else if (renewalStart !== null && renewalEnd < renewalStart) {
      errors.endDate = t("contracts.draft.error.endBeforeStart", {
        start: formatDate(renewalStart),
      });
    }
  }

  if (
    Object.keys(errors).length > 0 ||
    obligation === null ||
    termEnd === null ||
    quantity === null ||
    price === null ||
    header.reference === null ||
    effective === null
  ) {
    return { body: null, errors };
  }
  let line: ModificationLineBody;
  switch (action) {
    case "upgrade":
      line = {
        action: "CHANGE",
        obligation_key: obligation.key,
        quantity_delta: quantity,
        consideration_delta: money(price, currency),
        start_date: effective,
        end_date: termEnd,
      };
      break;
    case "downgrade":
      line = {
        action: "CHANGE",
        obligation_key: obligation.key,
        quantity_delta: removed(quantity),
        consideration_delta: money(removed(price), currency),
        start_date: effective,
        end_date: termEnd,
      };
      break;
    case "co_term":
      line = {
        action: "ADD",
        obligation_key: newKey,
        product_code: obligation.productCode,
        quantity_delta: quantity,
        consideration_delta: money(price, currency),
        start_date: effective,
        end_date: termEnd,
      };
      break;
    case "renew":
    case "early_renew":
      line = {
        action: "ADD",
        obligation_key: newKey,
        product_code: obligation.productCode,
        quantity_delta: quantity,
        consideration_delta: money(price, currency),
        start_date: renewalStart,
        end_date: renewalEnd,
      };
      break;
    case "cancel":
      line = {
        action: "REMOVE",
        obligation_key: obligation.key,
        quantity_delta: removed(quantity),
        consideration_delta: money(removed(price), currency),
        start_date: effective,
        end_date: termEnd,
      };
      break;
  }
  return {
    body: {
      kind: SUBSCRIPTION_KIND[action],
      reference: header.reference,
      effective_date: effective,
      lines: [line],
    } satisfies ModificationCreateBody,
    errors,
  };
}

// ---------------------------------------------------------------------------------------------------
// The questionnaire (SCREENS §7.5; BR-MOD-01).

type Answers = Readonly<Record<string, unknown>>;

/** The proposal of one answer by the last classification (04 §16.14 `prefill_reasons`). */
export interface Prefill {
  readonly value: boolean;
  readonly reasonKey: string;
  readonly params: Readonly<Record<string, string>>;
}

/**
 * The engine's price test of an added line as the row's latest classification read it (04 §16.14
 * rev 1.250 `price_tests`, item MOD-PRICE-TEST-FACT-1): a fact beside the answer, whatever the
 * preparer answered, and no proposal. It has the form of one: the outcome, its reason and the
 * price with the range or the point.
 */
export type PriceTest = Prefill;

export interface QuestionView {
  readonly question: Question;
  /** The stored answer, else the proposed one; null while the preparer has to answer. */
  readonly value: boolean | null;
  /** The answer is the preparer's: confirmed with its group, or changed. */
  readonly stored: boolean;
  /** The reason of a proposed answer that is not stored yet. */
  readonly prefill: Prefill | null;
  /**
   * The price test beside the answer of `priced_at_ssp`, stored or proposed; null for the other
   * questions, and where the row states none.
   */
  readonly priceTest: PriceTest | null;
}

export interface QuestionGroup {
  readonly obligationKey: string;
  /** The key of an `ADD` line: the group asks the two questions of added goods. */
  readonly added: boolean;
  readonly questions: readonly QuestionView[];
  /** Every question the group shows has a stored answer. */
  readonly confirmed: boolean;
}

const ADDED_QUESTIONS: readonly Question[] = ["added_goods_distinct", "priced_at_ssp"];
const REMAINING_QUESTION: Question = "remaining_goods_distinct_from_transferred";

function answerOf(section: unknown, question: Question): boolean | null {
  const value = record(section)[question];
  return typeof value === "boolean" ? value : null;
}

/** One `{value, reason_key, params}` of the classification (04 §16.14); null for anything else. */
function readingOf(entry: unknown): Prefill | null {
  const item = record(entry);
  if (typeof item.value !== "boolean" || typeof item.reason_key !== "string") {
    return null;
  }
  const params: Record<string, string> = {};
  for (const [name, value] of Object.entries(record(item.params))) {
    if (typeof value === "string") {
      params[name] = value;
    }
  }
  return { value: item.value, reasonKey: item.reason_key, params };
}

function prefillOf(reasons: Answers, key: string, question: Question): Prefill | null {
  return readingOf(record(reasons[key])[question]);
}

/**
 * The price test the row states for the added line `key`; null for a row that is not classified or
 * was edited since, and for a line the engine does not test (04 §16.14 rev 1.250).
 */
export function priceTestOf(
  modification: Pick<Modification, "price_tests">,
  key: string,
): PriceTest | null {
  return readingOf(record(modification.price_tests)[key]);
}

/** The keys of the `ADD` lines of a modification, in line order. */
export function addedKeys(modification: Pick<Modification, "lines">): readonly string[] {
  return modification.lines.flatMap((line) => {
    const item = record(line);
    return item.action === "ADD" && typeof item.obligation_key === "string"
      ? [item.obligation_key]
      : [];
  });
}

/**
 * One group per obligation the classification covers. An added line is asked whether its goods are
 * distinct and priced at SSP; an existing obligation is asked the remaining-goods question where the
 * system proposes an answer or the preparer stored one (a satisfied obligation leaves nothing
 * remaining, so the engine reads no answer for it).
 */
export function questionGroups(
  modification: Pick<
    Modification,
    "lines" | "questionnaire" | "proposed_treatments" | "price_tests"
  >,
  prefillReasons: Answers,
): readonly QuestionGroup[] {
  const stored = record(modification.questionnaire);
  const added = addedKeys(modification);
  const keys = [
    ...added,
    ...Object.keys(modification.proposed_treatments)
      .filter((key) => !added.includes(key))
      .sort((left, right) => left.localeCompare(right, undefined, { numeric: true })),
  ];
  const groups: QuestionGroup[] = [];
  for (const key of keys) {
    const isAdded = added.includes(key);
    const questions: QuestionView[] = [];
    for (const question of isAdded ? ADDED_QUESTIONS : [REMAINING_QUESTION]) {
      const answer = answerOf(stored[key], question);
      const prefill = answer === null ? prefillOf(prefillReasons, key, question) : null;
      if (!isAdded && answer === null && prefill === null) {
        continue;
      }
      questions.push({
        question,
        value: answer ?? prefill?.value ?? null,
        stored: answer !== null,
        prefill,
        priceTest: question === "priced_at_ssp" ? priceTestOf(modification, key) : null,
      });
    }
    if (questions.length > 0) {
      groups.push({
        obligationKey: key,
        added: isAdded,
        questions,
        confirmed: questions.every((item) => item.stored),
      });
    }
  }
  return groups;
}

/** BR-MOD-01: the preparer confirmed every answer. */
export function questionnaireConfirmed(groups: readonly QuestionGroup[]): boolean {
  return groups.every((group) => group.confirmed);
}

/** The stored answers of the row, for "<n> answers confirmed" (SCREENS §7.5 caption). */
export function confirmedAnswers(groups: readonly QuestionGroup[]): number {
  return groups.reduce(
    (count, group) => count + group.questions.filter((item) => item.stored).length,
    0,
  );
}

function withSection(
  stored: unknown,
  key: string,
  change: (section: Readonly<Record<string, unknown>>) => Readonly<Record<string, unknown>>,
): Record<string, unknown> {
  const current = record(stored);
  const section = change(record(current[key]));
  const others = Object.entries(current).filter(([name]) => name !== key);
  return Object.fromEntries(
    Object.keys(section).length === 0 ? others : [...others, [key, section]],
  );
}

/** The stored questionnaire with one answer set: `PATCH` replaces the member whole. */
export function withAnswer(
  stored: unknown,
  key: string,
  question: Question,
  value: boolean,
): Record<string, unknown> {
  return withSection(stored, key, (section) => ({ ...section, [question]: value }));
}

/** The stored questionnaire with every answer the group shows stored as it reads. */
export function withGroupConfirmed(stored: unknown, group: QuestionGroup): Record<string, unknown> {
  return withSection(stored, group.obligationKey, (section) => ({
    ...section,
    ...Object.fromEntries(
      group.questions.flatMap((item) => (item.value === null ? [] : [[item.question, item.value]])),
    ),
  }));
}

/** The stored questionnaire without the group's answers: the system proposes them again. */
export function withoutGroup(stored: unknown, group: QuestionGroup): Record<string, unknown> {
  const shown = new Set<string>(group.questions.map((item) => item.question));
  return withSection(stored, group.obligationKey, (section) =>
    Object.fromEntries(Object.entries(section).filter(([name]) => !shown.has(name))),
  );
}

// ---------------------------------------------------------------------------------------------------
// Treatments and steps (SCREENS §7.3, §7.6).

/** E-23 literals of the guided route (SCREENS §7.6). */
export const TREATMENTS: readonly ModificationTreatment[] = [
  "SEPARATE_CONTRACT",
  "PROSPECTIVE",
  "CUMULATIVE_CATCH_UP",
  "MIXED",
];
/** E-23 literals of the legacy presets, offered only under POL-100 `USER_SELECTED_TEMPLATE`. */
export const LEGACY_TREATMENTS: readonly ModificationTreatment[] = [
  "LEGACY_PROSPECTIVE",
  "LEGACY_RETROSPECTIVE",
  "LEGACY_POB_VC",
];

export function isTreatment(
  value: string,
  offered: readonly ModificationTreatment[],
): value is ModificationTreatment {
  return (offered as readonly string[]).includes(value);
}

const EVERY_TREATMENT: readonly ModificationTreatment[] = [...TREATMENTS, ...LEGACY_TREATMENTS];

/**
 * The keys whose chosen treatment differs from the proposal, as `/submit` reads them (REQ-MOD-002): a
 * chosen key the proposal does not hold departs too. A row without a proposal has none to depart from.
 */
export function departures(
  proposed: Readonly<Record<string, string>>,
  chosen: Readonly<Record<string, string>>,
): readonly string[] {
  if (Object.keys(proposed).length === 0) {
    return [];
  }
  return Object.keys(chosen)
    .filter((key) => chosen[key] !== proposed[key])
    .sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
}

/**
 * The `chosen_treatments` a save of step 1 or 2 sends. `/classify` keeps every stored choice and fills
 * in the proposal only where there is none, so a default of the last classification would stand as a
 * departure once an edit changes the proposal. The save keeps the departures the preparer made, for
 * the keys in `keys` when given (the obligations the edited modification still names), and drops the
 * defaults; undefined for a row without a proposal, whose choices cannot be told apart and stay.
 */
export function authoredChoices(
  row: Pick<Modification, "proposed_treatments" | "chosen_treatments">,
  keys?: ReadonlySet<string>,
): Record<string, ModificationTreatment> | undefined {
  const proposed = row.proposed_treatments;
  if (Object.keys(proposed).length === 0) {
    return undefined;
  }
  const authored: Record<string, ModificationTreatment> = {};
  for (const key of departures(proposed, row.chosen_treatments)) {
    const treatment = row.chosen_treatments[key];
    if (
      treatment !== undefined &&
      isTreatment(treatment, EVERY_TREATMENT) &&
      proposed[key] !== undefined &&
      (keys === undefined || keys.has(key))
    ) {
      authored[key] = treatment;
    }
  }
  return authored;
}

/** SCR-URL-15: the `step` values of SF-07, in order. */
export const WIZARD_STEPS = ["change", "questionnaire", "treatment", "preview", "submit"] as const;
export type WizardStep = (typeof WIZARD_STEPS)[number];

export function wizardStepOf(value: string | null): WizardStep | null {
  return WIZARD_STEPS.find((step) => step === value) ?? null;
}

/** What decides which steps of a draft are done. */
export interface DraftProgress {
  /** The row carries a proposal: it was classified since its last edit. */
  readonly classified: boolean;
  readonly answersConfirmed: boolean;
  /** A chosen treatment differs from the proposal. */
  readonly departs: boolean;
  /** A judgement record of the departure is linked to the row. */
  readonly judgementLinked: boolean;
  /** The row holds a preview of itself as it stands. */
  readonly previewed: boolean;
}

/** The first step of a draft that is not done; "submit" when every step before it is. */
export function firstOpenStep(progress: DraftProgress): WizardStep {
  if (!progress.classified || !progress.answersConfirmed) {
    return "questionnaire";
  }
  if (progress.departs && !progress.judgementLinked) {
    return "treatment";
  }
  if (!progress.previewed) {
    return "preview";
  }
  return "submit";
}

/** A step is open to the user when every step before it is done. */
export function stepReachable(step: WizardStep, progress: DraftProgress): boolean {
  return WIZARD_STEPS.indexOf(step) <= WIZARD_STEPS.indexOf(firstOpenStep(progress));
}
