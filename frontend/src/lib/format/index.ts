// Format module (DESIGN_SYSTEM §6 DS-FMT-01 to DS-FMT-31, §9 DS-I18N-03, DS-I18N-04; docs/dev-guide.md
// DG-FE-08, DG-FE-20). The only place that turns API decimal strings, dates and timestamps into
// display text. Decimal strings reach Intl.NumberFormat as exact decimals with half-away-from-zero
// rounding (D-11); nothing here converts a money string to a JavaScript number. The negative style is
// applied here from the tenant setting, never from the sign output of Intl.
import { UI_LOCALE } from "../i18n/t";

export type NegativeStyle = "PARENTHESES" | "MINUS";

export interface FormatSettings {
  readonly locale: string;
  readonly negativeStyle: NegativeStyle;
}

export interface FormatOptions {
  readonly locale?: string;
  readonly negativeStyle?: NegativeStyle;
}

export const MINUS_SIGN = "−";
export const NO_VALUE = "—";
export const NBSP = "\u00A0";

const settings: { locale: string; negativeStyle: NegativeStyle } = {
  locale: "en-US",
  negativeStyle: "PARENTHESES",
};

/** Applies `format_locale` (DS-I18N-02) and `tenant_settings.negative_number_style` (DS-FMT-06). */
export function configureFormat(next: Partial<FormatSettings>): void {
  if (next.locale !== undefined) {
    settings.locale = next.locale;
  }
  if (next.negativeStyle !== undefined) {
    settings.negativeStyle = next.negativeStyle;
  }
}

export function formatSettings(): FormatSettings {
  return { ...settings };
}

// DS-FMT-03, DS-I18N-09: minor units come from the API currency reference, never from Intl
// defaults. An unregistered currency fails closed (SPEC-Q-199).
const minorUnits = new Map<string, number>();

export function registerCurrencies(
  entries: Iterable<{ readonly code: string; readonly minor_unit: number }>,
): void {
  for (const entry of entries) {
    minorUnits.set(entry.code, entry.minor_unit);
  }
}

export function minorUnitOf(currency: string): number {
  const unit = minorUnits.get(currency);
  if (unit === undefined) {
    throw new Error(`Unknown currency ${currency}: register the API currency reference first`);
  }
  return unit;
}

interface Decimal {
  readonly negative: boolean;
  readonly integer: string;
  readonly fraction: string;
}

const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/;

function parseDecimal(value: string): Decimal {
  const match = DECIMAL.exec(value);
  if (match === null) {
    throw new Error(`Not a decimal string: ${value}`);
  }
  return { negative: match[1] === "-", integer: match[2] ?? "0", fraction: match[3] ?? "" };
}

function literal(integer: string, fraction: string): Intl.StringNumericLiteral {
  return (fraction === "" ? integer : `${integer}.${fraction}`) as Intl.StringNumericLiteral;
}

/** The absolute value with its decimal point moved `places` digits to the left. */
function shiftLeft(decimal: Decimal, places: number): Intl.StringNumericLiteral {
  const digits = decimal.integer + decimal.fraction;
  const point = decimal.integer.length - places;
  if (point <= 0) {
    return literal("0", "0".repeat(-point) + digits);
  }
  return literal(digits.slice(0, point), digits.slice(point));
}

const formatters = new Map<string, Intl.NumberFormat>();

function numberFormat(locale: string, options: Intl.NumberFormatOptions): Intl.NumberFormat {
  const key = `${locale}|${JSON.stringify(options)}`;
  let formatter = formatters.get(key);
  if (formatter === undefined) {
    formatter = new Intl.NumberFormat(locale, {
      numberingSystem: "latn",
      roundingMode: "halfExpand",
      ...options,
    });
    formatters.set(key, formatter);
  }
  return formatter;
}

/** Structured output that `<Money>` and `<Num>` render with DS-FMT-29 accessible names. */
export interface SignedParts {
  /** ISO 4217 code shown before the figures outside grids (DS-FMT-05). */
  readonly code: string | null;
  readonly sign: "negative" | "plus" | null;
  /** Grouped figures, including any inner suffix such as `%` or `K`. */
  readonly body: string;
  /** Text after the figures and any closing parenthesis, such as ` pp`. */
  readonly suffix: string;
  readonly style: NegativeStyle;
}

export function joinParts(parts: SignedParts): string {
  const prefix = parts.code === null ? "" : `${parts.code}${NBSP}`;
  let figures = parts.body;
  if (parts.sign === "plus") {
    figures = `+${figures}`;
  } else if (parts.sign === "negative") {
    figures = parts.style === "PARENTHESES" ? `(${figures})` : `${MINUS_SIGN}${figures}`;
  }
  return `${prefix}${figures}${parts.suffix}`;
}

// A value that rounds to zero displays as zero without a sign (DS-FMT-06, DS-FMT-31).
function signOf(decimal: Decimal, body: string, plus: boolean): SignedParts["sign"] {
  if (!/[1-9]/.test(body)) {
    return null;
  }
  if (decimal.negative) {
    return "negative";
  }
  return plus ? "plus" : null;
}

function styleOf(options: FormatOptions): NegativeStyle {
  return options.negativeStyle ?? settings.negativeStyle;
}

function localeOf(options: FormatOptions): string {
  return options.locale ?? settings.locale;
}

export type MoneyVariant = "cell" | "inline" | "kpi";

export interface MoneyOptions extends FormatOptions {
  /** `cell`: grids and report tables; `inline` and `kpi` carry the currency code; `csv`: exports. */
  readonly variant?: MoneyVariant | "csv";
  /** DS-FMT-31: a positive delta carries `+`. */
  readonly delta?: boolean;
}

export function moneyParts(
  value: string,
  currency: string,
  options: MoneyOptions = {},
): SignedParts {
  const decimal = parseDecimal(value);
  const unit = minorUnitOf(currency);
  const body = numberFormat(localeOf(options), {
    minimumFractionDigits: unit,
    maximumFractionDigits: unit,
  }).format(literal(decimal.integer, decimal.fraction));
  return {
    code: (options.variant ?? "cell") === "cell" ? null : currency,
    sign: signOf(decimal, body, options.delta === true),
    body,
    suffix: "",
    style: styleOf(options),
  };
}

// DS-FMT-25: raw signed values; trailing digits beyond the minor unit are trimmed only where they
// are zeros, so an unrounded value stays raw.
function moneyCsv(value: string, currency: string): string {
  const decimal = parseDecimal(value);
  const unit = minorUnitOf(currency);
  if (/[1-9]/.test(decimal.fraction.slice(unit))) {
    return value;
  }
  const integer = decimal.integer.replace(/^0+(?=\d)/, "");
  const fraction = decimal.fraction.slice(0, unit).padEnd(unit, "0");
  const negative = decimal.negative && /[1-9]/.test(integer + fraction);
  return `${negative ? "-" : ""}${integer}${unit > 0 ? `.${fraction}` : ""}`;
}

export function formatMoney(
  value: string | null,
  currency: string,
  options: MoneyOptions = {},
): string {
  if (options.variant === "csv") {
    return value === null ? "" : moneyCsv(value, currency);
  }
  return value === null ? NO_VALUE : joinParts(moneyParts(value, currency, options));
}

export type NumberKind = "quantity" | "count";

export interface NumberOptions extends FormatOptions {
  /** `quantity`: up to 4 decimals, trailing zeros trimmed (DS-FMT-11); `count`: integers (DS-FMT-21). */
  readonly kind?: NumberKind;
  readonly delta?: boolean;
}

function decimalString(value: string | number): string {
  if (typeof value === "string") {
    return value;
  }
  if (!Number.isSafeInteger(value)) {
    throw new Error(`Only integer counts may be JSON numbers: ${String(value)}`);
  }
  return String(value);
}

export function numberParts(value: string | number, options: NumberOptions = {}): SignedParts {
  const decimal = parseDecimal(decimalString(value));
  const body = numberFormat(localeOf(options), {
    minimumFractionDigits: 0,
    maximumFractionDigits: options.kind === "count" ? 0 : 4,
  }).format(literal(decimal.integer, decimal.fraction));
  return {
    code: null,
    sign: signOf(decimal, body, options.delta === true),
    body,
    suffix: "",
    style: styleOf(options),
  };
}

export function formatNumber(value: string | number | null, options: NumberOptions = {}): string {
  return value === null ? NO_VALUE : joinParts(numberParts(value, options));
}

export type ListStyle = "or" | "and" | "unit";

/** Joins words in the UI language: `or` "Draft or Void", `and` "a and b", `unit` "Draft, Void". */
export function formatList(items: readonly string[], style: ListStyle): string {
  const type = style === "or" ? "disjunction" : style === "and" ? "conjunction" : "unit";
  return new Intl.ListFormat(UI_LOCALE, {
    type,
    style: style === "unit" ? "short" : "long",
  }).format(items);
}

export interface PercentOptions extends FormatOptions {
  /**
   * `percent`: a ratio with one decimal; `share`: allocation shares and SSP ratios with two
   * (DS-FMT-09); `pp`: a percentage-point change given in points, with a sign (DS-FMT-10).
   */
  readonly kind?: "percent" | "share" | "pp";
  /** DS-FMT-31: a change ratio, so a positive value carries `+` (for example "+3.1%"). */
  readonly delta?: boolean;
}

export function percentParts(value: string, options: PercentOptions = {}): SignedParts {
  const decimal = parseDecimal(value);
  const kind = options.kind ?? "percent";
  const absolute = literal(decimal.integer, decimal.fraction);
  if (kind === "pp") {
    const body = numberFormat(localeOf(options), {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(absolute);
    return {
      code: null,
      sign: signOf(decimal, body, true),
      body,
      suffix: " pp",
      style: styleOf(options),
    };
  }
  const digits = kind === "share" ? 2 : 1;
  const body = numberFormat(localeOf(options), {
    style: "percent",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(absolute);
  return {
    code: null,
    sign: signOf(decimal, body, options.delta === true),
    body,
    suffix: "",
    style: styleOf(options),
  };
}

export function formatPercent(value: string | null, options: PercentOptions = {}): string {
  return value === null ? NO_VALUE : joinParts(percentParts(value, options));
}

export interface RateOptions extends FormatOptions {
  /** `unit`: unit prices and SSP rates, minor unit to 6 decimals (DS-FMT-13); `fx`: 6 fixed (DS-FMT-14). */
  readonly kind: "unit" | "fx";
  /** The price currency; required for `unit`. */
  readonly currency?: string;
}

export function rateParts(value: string, options: RateOptions): SignedParts {
  const decimal = parseDecimal(value);
  let minimum = 6;
  if (options.kind === "unit") {
    if (options.currency === undefined) {
      throw new Error("A unit rate needs its currency");
    }
    minimum = minorUnitOf(options.currency);
  }
  const body = numberFormat(localeOf(options), {
    minimumFractionDigits: minimum,
    maximumFractionDigits: 6,
  }).format(literal(decimal.integer, decimal.fraction));
  return {
    code: null,
    sign: signOf(decimal, body, false),
    body,
    suffix: "",
    style: styleOf(options),
  };
}

export function formatRate(value: string | null, options: RateOptions): string {
  return value === null ? NO_VALUE : joinParts(rateParts(value, options));
}

const COMPACT_SUFFIXES = ["", "K", "M", "B", "T"] as const;

// DS-FMT-15: chart ticks, data labels and sparkline end labels only; 3 significant digits.
export function compactParts(value: string, options: FormatOptions = {}): SignedParts {
  const decimal = parseDecimal(value);
  const integer = decimal.integer.replace(/^0+(?=\d)/, "");
  const last = COMPACT_SUFFIXES.length - 1;
  let tier = integer === "0" ? 0 : Math.min(Math.floor((integer.length - 1) / 3), last);
  // Rounding to 3 significant digits can reach the next tier: 999,950 is 1M, not 1,000K.
  const probe = numberFormat("en-US", { maximumSignificantDigits: 3, useGrouping: false });
  if (tier < last && /^\d{4}/.test(probe.format(shiftLeft(decimal, 3 * tier)))) {
    tier += 1;
  }
  const scaled = shiftLeft(decimal, 3 * tier);
  const body = `${numberFormat(localeOf(options), { maximumSignificantDigits: 3 }).format(scaled)}${
    COMPACT_SUFFIXES[tier] ?? ""
  }`;
  return {
    code: null,
    sign: signOf(decimal, body, false),
    body,
    suffix: "",
    style: styleOf(options),
  };
}

export function formatCompact(value: string | null, options: FormatOptions = {}): string {
  return value === null ? NO_VALUE : joinParts(compactParts(value, options));
}

const monthFormatter = new Intl.DateTimeFormat(UI_LOCALE, { month: "short", timeZone: "UTC" });

function monthAbbreviation(month: number): string {
  return monthFormatter.format(Date.UTC(2000, month - 1, 1));
}

function two(value: number): string {
  return String(value).padStart(2, "0");
}

const BUSINESS_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** DS-FMT-16: `DD MMM YYYY` from the `YYYY-MM-DD` parts; no Date and no browser time zone. */
export function formatDate(value: string | null): string {
  if (value === null) {
    return NO_VALUE;
  }
  const match = BUSINESS_DATE.exec(value);
  const month = Number(match?.[2]);
  if (match === null || month < 1 || month > 12) {
    throw new Error(`Not a business date: ${value}`);
  }
  return `${match[3] ?? ""} ${monthAbbreviation(month)} ${match[1] ?? ""}`;
}

export interface TimestampOptions {
  /** DS-FMT-17: seconds in the audit trail and timeline detail. */
  readonly seconds?: boolean;
}

/** DS-FMT-17: `DD MMM YYYY HH:mm UTC` on the 24-hour clock, always UTC (SPEC-Q-200). */
export function formatTimestamp(value: string | null, options: TimestampOptions = {}): string {
  if (value === null) {
    return NO_VALUE;
  }
  const instant = new Date(value);
  if (!/Z$/.test(value) || Number.isNaN(instant.getTime())) {
    throw new Error(`Not an RFC 3339 UTC timestamp: ${value}`);
  }
  const date = `${two(instant.getUTCDate())} ${monthAbbreviation(instant.getUTCMonth() + 1)} ${String(
    instant.getUTCFullYear(),
  )}`;
  const time = `${two(instant.getUTCHours())}:${two(instant.getUTCMinutes())}${
    options.seconds === true ? `:${two(instant.getUTCSeconds())}` : ""
  }`;
  return `${date} ${time} UTC`;
}

export interface PeriodOptions {
  /** The period start date of a Gregorian monthly calendar, which labels the period `MMM YYYY`. */
  readonly startDate?: string;
}

const FISCAL_KEY = /^FY(\d{4})(?:-([PQ])(\d{1,2}))?$/;

/** DS-FMT-19: `Sep 2026` for Gregorian months, else `FY2026 P09`, `FY2026 Q3` or `FY2026`. */
export function formatPeriod(periodKey: string | null, options: PeriodOptions = {}): string {
  if (periodKey === null) {
    return NO_VALUE;
  }
  if (options.startDate !== undefined) {
    const match = BUSINESS_DATE.exec(options.startDate);
    if (match === null) {
      throw new Error(`Not a business date: ${options.startDate}`);
    }
    return `${monthAbbreviation(Number(match[2]))} ${match[1] ?? ""}`;
  }
  const match = FISCAL_KEY.exec(periodKey);
  if (match === null) {
    throw new Error(`Not a period key: ${periodKey}`);
  }
  const [, year = "", unit, number = ""] = match;
  if (unit === undefined) {
    return `FY${year}`;
  }
  return unit === "P" ? `FY${year} P${number.padStart(2, "0")}` : `FY${year} Q${number}`;
}

export type ParsedMoney =
  | { readonly ok: true; readonly value: string }
  | { readonly ok: false; readonly error: "invalid" | "too-many-decimals" };

function separators(locale: string): { readonly group: string; readonly decimal: string } {
  const parts = numberFormat(locale, {}).formatToParts(12345.6);
  return {
    group: parts.find((part) => part.type === "group")?.value ?? ",",
    decimal: parts.find((part) => part.type === "decimal")?.value ?? ".",
  };
}

/**
 * DS-I18N-04: parses typed money with the `format_locale` separators into an API decimal string.
 * Parentheses, U+2212 and hyphen-minus mark negatives; more decimals than the minor unit are refused.
 */
export function parseMoneyInput(
  text: string,
  currency: string,
  options: FormatOptions = {},
): ParsedMoney {
  const { group, decimal } = separators(localeOf(options));
  let body = text.trim();
  let negative = false;
  if (body.startsWith("(") && body.endsWith(")")) {
    negative = true;
    body = body.slice(1, -1).trim();
  }
  if (body.startsWith("-") || body.startsWith(MINUS_SIGN)) {
    if (negative) {
      return { ok: false, error: "invalid" };
    }
    negative = true;
    body = body.slice(1);
  }
  body = body
    .replace(/[\s\u00A0\u202F]/g, "")
    .split(group)
    .join("");
  if (decimal !== ".") {
    body = body.split(decimal).join(".");
  }
  const match = DECIMAL.exec(body);
  if (match === null || match[1] === "-") {
    return { ok: false, error: "invalid" };
  }
  const integer = (match[2] ?? "0").replace(/^0+(?=\d)/, "");
  const fraction = match[3] ?? "";
  if (fraction.length > minorUnitOf(currency)) {
    return { ok: false, error: "too-many-decimals" };
  }
  const sign = negative && /[1-9]/.test(integer + fraction) ? "-" : "";
  return { ok: true, value: `${sign}${integer}${fraction === "" ? "" : `.${fraction}`}` };
}

const DURATION_UNITS = [
  { name: "d", seconds: 86_400 },
  { name: "h", seconds: 3_600 },
  { name: "min", seconds: 60 },
  { name: "s", seconds: 1 },
] as const;

/** DS-FMT-24: the largest two units, the second with two digits: `2 min 14 s`, `3 h 05 min`. */
export function formatDuration(milliseconds: number): string {
  if (!Number.isFinite(milliseconds) || milliseconds < 0) {
    throw new Error(`Not a duration: ${String(milliseconds)}`);
  }
  const seconds = Math.floor(milliseconds / 1_000);
  const first = DURATION_UNITS.findIndex((unit) => seconds >= unit.seconds);
  const unit = DURATION_UNITS[first];
  if (unit === undefined) {
    return "0 s";
  }
  const major = Math.floor(seconds / unit.seconds);
  const next = DURATION_UNITS[first + 1];
  if (next === undefined) {
    return `${String(major)} ${unit.name}`;
  }
  const minor = Math.floor((seconds % unit.seconds) / next.seconds);
  return `${String(major)} ${unit.name} ${two(minor)} ${next.name}`;
}

const INSTANT_OFFSET = /(?:Z|[+-]\d{2}:\d{2})$/;

/** The epoch milliseconds of an RFC 3339 instant with an offset, for timers (DG-FE-20). */
export function instantMs(value: string): number {
  const instant = Date.parse(value);
  if (!INSTANT_OFFSET.test(value) || Number.isNaN(instant)) {
    throw new Error(`Not an RFC 3339 instant with an offset: ${value}`);
  }
  return instant;
}

/** The RFC 3339 UTC instant of an epoch time, for a command that names "now" (DG-FE-20). */
export function instantOf(epochMs: number): string {
  return new Date(epochMs).toISOString();
}

const RELATIVE_WEEK_DAYS = 7;

/**
 * DS-FMT-18 relative time, only for the notifications panel and toasts (with the DS-FMT-17 timestamp
 * in the tooltip): `just now`, `4 min ago`, `3 h ago`, `2 d ago`; from 7 days the DS-FMT-17 timestamp.
 */
export function formatRelative(value: string, nowMs: number): string {
  const minutes = Math.floor(Math.max(0, nowMs - instantMs(value)) / 60_000);
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return `${String(minutes)} min ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${String(hours)} h ago`;
  }
  const days = Math.floor(hours / 24);
  return days < RELATIVE_WEEK_DAYS ? `${String(days)} d ago` : formatTimestamp(value);
}

/** DS-FMT-24 elapsed time of a job since its RFC 3339 UTC `started_at`. */
export function formatElapsed(startedAt: string, nowMs: number): string {
  const started = Date.parse(startedAt);
  if (!/Z$/.test(startedAt) || Number.isNaN(started)) {
    throw new Error(`Not an RFC 3339 UTC timestamp: ${startedAt}`);
  }
  return formatDuration(Math.max(0, nowMs - started));
}

// Calendar arithmetic over `YYYY-MM-DD` business dates with integer day numbers (days from civil,
// H. Hinnant), so no Date object and no browser time zone takes part (DG-FE-20).
export interface DateParts {
  readonly year: number;
  readonly month: number;
  readonly day: number;
}

export function daysInMonth(year: number, month: number): number {
  if (month === 2) {
    return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0 ? 29 : 28;
  }
  return month === 4 || month === 6 || month === 9 || month === 11 ? 30 : 31;
}

function validParts(year: number, month: number, day: number): boolean {
  return (
    Number.isInteger(year) &&
    Number.isInteger(month) &&
    Number.isInteger(day) &&
    year >= 1 &&
    year <= 9999 &&
    month >= 1 &&
    month <= 12 &&
    day >= 1 &&
    day <= daysInMonth(year, month)
  );
}

export function businessDate(year: number, month: number, day: number): string {
  if (!validParts(year, month, day)) {
    throw new Error(`Not a calendar date: ${String(year)}-${String(month)}-${String(day)}`);
  }
  return `${String(year).padStart(4, "0")}-${two(month)}-${two(day)}`;
}

export function dateParts(value: string): DateParts {
  const match = BUSINESS_DATE.exec(value);
  const parts = { year: Number(match?.[1]), month: Number(match?.[2]), day: Number(match?.[3]) };
  if (match === null || !validParts(parts.year, parts.month, parts.day)) {
    throw new Error(`Not a business date: ${value}`);
  }
  return parts;
}

function daysFromCivil({ year, month, day }: DateParts): number {
  const y = month <= 2 ? year - 1 : year;
  const era = Math.floor(y / 400);
  const yearOfEra = y - era * 400;
  const dayOfYear = Math.floor((153 * (month > 2 ? month - 3 : month + 9) + 2) / 5) + day - 1;
  const dayOfEra =
    yearOfEra * 365 + Math.floor(yearOfEra / 4) - Math.floor(yearOfEra / 100) + dayOfYear;
  return era * 146_097 + dayOfEra - 719_468;
}

function civilFromDays(days: number): DateParts {
  const z = days + 719_468;
  const era = Math.floor(z / 146_097);
  const dayOfEra = z - era * 146_097;
  const yearOfEra = Math.floor(
    (dayOfEra -
      Math.floor(dayOfEra / 1_460) +
      Math.floor(dayOfEra / 36_524) -
      Math.floor(dayOfEra / 146_096)) /
      365,
  );
  const dayOfYear =
    dayOfEra - (365 * yearOfEra + Math.floor(yearOfEra / 4) - Math.floor(yearOfEra / 100));
  const monthIndex = Math.floor((5 * dayOfYear + 2) / 153);
  const month = monthIndex < 10 ? monthIndex + 3 : monthIndex - 9;
  return {
    year: yearOfEra + era * 400 + (month <= 2 ? 1 : 0),
    month,
    day: dayOfYear - Math.floor((153 * monthIndex + 2) / 5) + 1,
  };
}

function fromParts(parts: DateParts): string {
  return businessDate(parts.year, parts.month, parts.day);
}

export function addDays(value: string, days: number): string {
  return fromParts(civilFromDays(daysFromCivil(dateParts(value)) + days));
}

/** Moves by whole months and clamps the day to the target month (31 Jan + 1 month = 28 Feb). */
export function addMonths(value: string, months: number): string {
  const { year, month, day } = dateParts(value);
  const index = year * 12 + (month - 1) + months;
  const targetYear = Math.floor(index / 12);
  const targetMonth = index - targetYear * 12 + 1;
  return businessDate(targetYear, targetMonth, Math.min(day, daysInMonth(targetYear, targetMonth)));
}

/** ISO 8601 weekday order: 0 = Monday … 6 = Sunday. */
export function weekdayOf(value: string): number {
  return (((daysFromCivil(dateParts(value)) + 3) % 7) + 7) % 7;
}

/** The UTC calendar date of an epoch instant, for a date picker's starting month. */
export function utcDateOf(epochMs: number): string {
  return fromParts(civilFromDays(Math.floor(epochMs / 86_400_000)));
}

/**
 * The calendar date of an epoch instant in an IANA time zone: "today" for the effective date of an
 * event, whose owning zone is the contracting entity's (05 TZ-02). Independent of the browser's zone.
 */
export function currentDateIn(timeZone: string, epochMs: number): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(epochMs));
  const part = (type: string) => Number(parts.find((item) => item.type === type)?.value);
  return businessDate(part("year"), part("month"), part("day"));
}

/** The UTC calendar date of an RFC 3339 UTC instant, for timeline date headings (DS-CMP-12). */
export function timestampDate(value: string): string {
  const instant = new Date(value);
  if (!/Z$/.test(value) || Number.isNaN(instant.getTime())) {
    throw new Error(`Not an RFC 3339 UTC timestamp: ${value}`);
  }
  return utcDateOf(instant.getTime());
}

/**
 * DS-I18N-08 (supervisor ruling R-59): the instant a picked effective date of a versioned configuration
 * (04 SC-V `effective_from`) goes on the wire as, 12:00:00Z of that date. The screens show the UTC date of
 * the stored instant (`timestampDate`), so the date picked is the date shown, and the entity-local date
 * equals it for every zone from UTC-12 to UTC+11. Known limitation: an entity beyond UTC+11 reads the
 * next day (item CFG-EFFECTIVE-DATE-1).
 */
export function effectiveInstant(date: string): string {
  dateParts(date);
  return `${date}T12:00:00Z`;
}

/** DS-I18N-08: the first instant of a day in platform time (UTC), the start of a validity window. */
export function dayStartInstant(date: string): string {
  dateParts(date);
  return `${date}T00:00:00Z`;
}

/** DS-I18N-08: the last second of a day in platform time (UTC), the inclusive end of a validity window. */
export function dayEndInstant(date: string): string {
  dateParts(date);
  return `${date}T23:59:59Z`;
}

const weekdayFormatters = {
  short: new Intl.DateTimeFormat(UI_LOCALE, { weekday: "short", timeZone: "UTC" }),
  long: new Intl.DateTimeFormat(UI_LOCALE, { weekday: "long", timeZone: "UTC" }),
} as const;

/** Monday-first weekday names; 01 Jan 2024 was a Monday. */
export function weekdayNames(width: "short" | "long"): readonly string[] {
  return Array.from({ length: 7 }, (_, index) =>
    weekdayFormatters[width].format(Date.UTC(2024, 0, 1 + index)),
  );
}

export type ParsedDate = { readonly ok: true; readonly value: string } | { readonly ok: false };

const NAMED_DATE = /^(\d{1,2})\s+(\p{L}+)\.?\s+(\d{4})$/u;
const NUMERIC_DATE = /^(\d{1,4})[./\-\s]+(\d{1,2})[./\-\s]+(\d{1,4})\.?$/;

function parsed(year: number, month: number, day: number): ParsedDate {
  return validParts(year, month, day)
    ? { ok: true, value: businessDate(year, month, day) }
    : { ok: false };
}

function numericOrder(locale: string): readonly string[] {
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    timeZone: "UTC",
  })
    .formatToParts(Date.UTC(2026, 10, 22))
    .map((part) => part.type)
    .filter((type) => type === "year" || type === "month" || type === "day");
}

/**
 * DS-CMP-21 date input: `YYYY-MM-DD`, `DD MMM YYYY` (DS-FMT-16) or the `format_locale` numeric short
 * date with a four-digit year, into a business date string.
 */
export function parseDateInput(text: string, options: FormatOptions = {}): ParsedDate {
  const body = text.trim();
  const iso = BUSINESS_DATE.exec(body);
  if (iso !== null) {
    return parsed(Number(iso[1]), Number(iso[2]), Number(iso[3]));
  }
  const named = NAMED_DATE.exec(body);
  if (named !== null) {
    const name = (named[2] ?? "").toLocaleLowerCase(UI_LOCALE);
    const month = Array.from({ length: 12 }, (_, index) => index + 1).find(
      (candidate) => monthAbbreviation(candidate).toLocaleLowerCase(UI_LOCALE) === name,
    );
    return month === undefined ? { ok: false } : parsed(Number(named[3]), month, Number(named[1]));
  }
  const numeric = NUMERIC_DATE.exec(body);
  if (numeric === null) {
    return { ok: false };
  }
  const fields = [numeric[1] ?? "", numeric[2] ?? "", numeric[3] ?? ""];
  const order = numericOrder(localeOf(options));
  const field = (type: string) => fields[order.indexOf(type)] ?? "";
  if (field("year").length !== 4) {
    return { ok: false };
  }
  return parsed(Number(field("year")), Number(field("month")), Number(field("day")));
}
