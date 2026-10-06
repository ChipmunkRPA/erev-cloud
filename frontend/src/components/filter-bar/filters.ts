// Filter codec (SCREENS §0.5 SCR-URL-08, SCR-URL-10, SCR-URL-21; DESIGN_SYSTEM DS-CMP-13; docs/dev-guide.md
// DG-FE-03). One `f.<field>=<operator>:<value>[,<value>…]` parameter per chip; values are API literals,
// decimal strings or ISO dates, and a comma inside a value is percent-encoded. A parameter naming an
// unknown field, an operator the field does not offer or an invalid value is unrecognised.
import {
  formatDate,
  formatList,
  formatMoney,
  formatNumber,
  formatPeriod,
  parseDateInput,
} from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { decodeValue, rawParams, withParams } from "../../lib/url/params";
import type { ListOption } from "../form/Listbox";
import type { PeriodOption } from "../form/PeriodInput";

export const FILTER_PREFIX = "f.";
export const QUERY_PARAM = "q";

export const OPERATORS = [
  "is",
  "in",
  "not",
  "contains",
  "between",
  "gte",
  "lte",
  "empty",
  "notempty",
] as const;

export type FilterOperator = (typeof OPERATORS)[number];
export type FilterKind =
  "enum" | "text" | "money" | "number" | "date" | "period" | "user" | "boolean";

export interface DatePreset {
  /** For example "This period". */
  readonly label: string;
  readonly from: string;
  readonly to: string;
}

export interface FilterField {
  /** The URL field name, `f.<name>`. */
  readonly name: string;
  readonly label: string;
  readonly kind: FilterKind;
  readonly operators: readonly FilterOperator[];
  /** Enum and user options; boolean fields use Yes and No. */
  readonly options?: readonly ListOption<string>[] | undefined;
  readonly optionsLoading?: boolean;
  readonly periods?: readonly PeriodOption[] | undefined;
  readonly presets?: readonly DatePreset[] | undefined;
  /** Money fields: the minor unit of typed values. */
  readonly currency?: string | undefined;
}

export interface Filter {
  readonly field: string;
  readonly operator: FilterOperator;
  readonly values: readonly string[];
}

export interface ParsedFilters {
  readonly query: string;
  readonly filters: readonly Filter[];
  /** Parameter names dropped under SCR-URL-21. */
  readonly unrecognised: readonly string[];
}

const ARITY: Readonly<Record<FilterOperator, readonly [number, number]>> = {
  is: [1, 1],
  in: [1, Number.POSITIVE_INFINITY],
  not: [1, Number.POSITIVE_INFINITY],
  contains: [1, 1],
  between: [2, 2],
  gte: [1, 1],
  lte: [1, 1],
  empty: [0, 0],
  notempty: [0, 0],
};

const DECIMAL = /^-?\d+(\.\d+)?$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function isOperator(text: string): text is FilterOperator {
  return (OPERATORS as readonly string[]).includes(text);
}

export function validFilterValue(field: FilterField, value: string): boolean {
  switch (field.kind) {
    case "enum":
      return field.options?.some((option) => option.value === value) === true;
    case "boolean":
      return value === "true" || value === "false";
    case "money":
    case "number":
      return DECIMAL.test(value);
    case "date":
      return ISO_DATE.test(value) && parseDateInput(value).ok;
    case "period":
      return field.periods === undefined
        ? value !== ""
        : field.periods.some((period) => period.key === value);
    case "user":
    case "text":
      return value.trim() !== "";
  }
}

export function parseFilter(field: FilterField, raw: string): Filter | null {
  const colon = raw.indexOf(":");
  const operator = decodeValue(colon < 0 ? raw : raw.slice(0, colon));
  if (!isOperator(operator) || !field.operators.includes(operator)) {
    return null;
  }
  const body = colon < 0 ? "" : raw.slice(colon + 1);
  const values = body === "" ? [] : body.split(",").map(decodeValue);
  const [minimum, maximum] = ARITY[operator];
  if (
    values.length < minimum ||
    values.length > maximum ||
    !values.every((value) => validFilterValue(field, value))
  ) {
    return null;
  }
  return { field: field.name, operator, values };
}

/** Reads `q` and every `f.*` parameter of a search string. */
export function parseFilters(search: string, fields: readonly FilterField[]): ParsedFilters {
  let query = "";
  const filters: Filter[] = [];
  const unrecognised: string[] = [];
  for (const param of rawParams(search)) {
    if (param.name === QUERY_PARAM) {
      query = decodeValue(param.value);
    } else if (param.name.startsWith(FILTER_PREFIX)) {
      const name = param.name.slice(FILTER_PREFIX.length);
      const field = fields.find((candidate) => candidate.name === name);
      const filter = field === undefined ? null : parseFilter(field, param.value);
      if (filter === null || filters.some((existing) => existing.field === name)) {
        unrecognised.push(param.name);
      } else {
        filters.push(filter);
      }
    }
  }
  return { query, filters, unrecognised };
}

/** The raw `f.<field>` value of a filter. */
export function filterParam(filter: Filter): string {
  return filter.values.length === 0
    ? filter.operator
    : `${filter.operator}:${filter.values.map(encodeURIComponent).join(",")}`;
}

/** Replaces `q` and every `f.*` parameter of a search string. */
export function withFilters(search: string, query: string, filters: readonly Filter[]): string {
  const changes: Record<string, string | null> = {
    [QUERY_PARAM]: query === "" ? null : encodeURIComponent(query),
  };
  for (const filter of filters) {
    changes[`${FILTER_PREFIX}${filter.field}`] = filterParam(filter);
  }
  return withParams(search, changes, [FILTER_PREFIX]);
}

/** True when a search string carries a quick search or a filter chip. */
export function hasFilters(search: string): boolean {
  return rawParams(search).some(
    (param) => param.name === QUERY_PARAM || param.name.startsWith(FILTER_PREFIX),
  );
}

type OperatorWord =
  | "is"
  | "isNot"
  | "contains"
  | "between"
  | "atLeast"
  | "atMost"
  | "onOrAfter"
  | "onOrBefore"
  | "empty"
  | "notEmpty";

function operatorWord(kind: FilterKind, operator: FilterOperator): OperatorWord {
  switch (operator) {
    case "is":
    case "in":
      return "is";
    case "not":
      return "isNot";
    case "contains":
      return "contains";
    case "between":
      return "between";
    case "gte":
      return kind === "date" ? "onOrAfter" : "atLeast";
    case "lte":
      return kind === "date" ? "onOrBefore" : "atMost";
    case "empty":
      return "empty";
    case "notempty":
      return "notEmpty";
  }
}

/** The words of an operator in the editor, for example "at least" or "on or after". */
export function operatorLabel(kind: FilterKind, operator: FilterOperator): string {
  return t(`common.filters.op.${operatorWord(kind, operator)}`);
}

export function valueLabel(field: FilterField, value: string): string {
  switch (field.kind) {
    case "boolean":
      return t(value === "true" ? "common.filters.yes" : "common.filters.no");
    case "enum":
    case "user":
      return field.options?.find((option) => option.value === value)?.label ?? value;
    case "money":
      return field.currency === undefined
        ? formatNumber(value)
        : formatMoney(value, field.currency, { variant: "inline" });
    case "number":
      return formatNumber(value);
    case "date":
      return formatDate(value);
    case "period":
      return field.periods?.find((period) => period.key === value)?.label ?? formatPeriod(value);
    case "text":
      return value;
  }
}

// DS-CMP-13: values are truncated after two items ("Status is Draft, Void +2"); the count after the
// plus sign is a figure, not copy.
function valuesLabel(field: FilterField, filter: Filter): string {
  const labels = filter.values.map((value) => valueLabel(field, value));
  if (labels.length <= 2) {
    return formatList(labels, filter.operator === "between" ? "and" : "or");
  }
  return `${formatList(labels.slice(0, 2), "unit")} +${formatNumber(labels.length - 2, { kind: "count" })}`;
}

/** The chip text "<Field> <operator> <value>", for example "Status is Draft or Pending approval". */
export function chipText(field: FilterField, filter: Filter): string {
  const word = operatorWord(field.kind, filter.operator);
  return filter.values.length === 0
    ? t(`common.filters.chip.${word}`, { field: field.label })
    : t(`common.filters.chip.${word}`, { field: field.label, value: valuesLabel(field, filter) });
}
