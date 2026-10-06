// DG-FE-20 (docs/dev-guide.md §8.2), DS-FMT-16 and DS-FMT-17: an API field of `format: date-time` never
// reaches a business-date function of `src/lib/format` (`formatDate` throws "Not a business date" and
// the page falls to the error boundary), and a `format: date` field never reaches an instant function.
// The formats come from `docs/api/openapi.json`; `./api-dates` traces each argument back to its fields.
// An instant is shown as a date through `formatDate(timestampDate(value))`, its UTC date. The write
// direction (DS-I18N-08, supervisor ruling R-59): a business date never reaches a `date-time` member of an
// API-typed object; a picked date becomes an instant through `effectiveInstant`, `dayStartInstant` or
// `dayEndInstant`.
import { beforeAll, describe, expect, it } from "vitest";

import {
  type DateFlow,
  type FormatRoles,
  mismatches,
  type SinkUse,
  traceDateFlow,
  untraced,
} from "./api-dates";

const ROLES: FormatRoles = {
  dateSinks: ["formatDate", "dateParts", "addDays", "addMonths", "weekdayOf"],
  instantSinks: [
    "formatTimestamp",
    "instantMs",
    "formatRelative",
    "formatElapsed",
    "timestampDate",
  ],
  dateProducers: [
    "timestampDate",
    "utcDateOf",
    "currentDateIn",
    "addDays",
    "addMonths",
    "businessDate",
  ],
  instantProducers: ["effectiveInstant", "dayStartInstant", "dayEndInstant", "instantOf"],
  dateOptions: { formatPeriod: "startDate" },
  dateResults: ["ParsedDate"],
  dateCallbacks: { DateInput: "onValue" },
  // The date picker: typed text through `parseDateInput` and calendar arithmetic on its own dates.
  trusted: ["src/components/form/DateInput.tsx"],
};

/** Exported functions of the format module that neither take nor return a date or an instant. */
const OTHER_EXPORTS = [
  "compactParts",
  "configureFormat",
  "daysInMonth",
  "formatCompact",
  "formatDuration",
  "formatList",
  "formatMoney",
  "formatNumber",
  "formatPercent",
  "formatRate",
  "formatSettings",
  "joinParts",
  "minorUnitOf",
  "moneyParts",
  "numberParts",
  "parseDateInput",
  "parseMoneyInput",
  "percentParts",
  "rateParts",
  "registerCurrencies",
  "weekdayNames",
];

/**
 * Arguments the trace cannot follow to an API field, as `<file>: <sink>(<argument>)`, each with the
 * reason it is not an API `date-time` (or `date`) field. A new untraced argument fails the test until
 * it is traced (convert at the call, or pass the field itself) or reviewed here.
 */
const REVIEWED: Readonly<Record<string, string>> = {
  "src/components/data-grid/cells.tsx: formatDate(value)":
    "the default renderer; the `value` of every `kind: date` column is checked at the column",
  "src/components/data-grid/cells.tsx: formatTimestamp(value)":
    "the default renderer; the `value` of every `kind: timestamp` column is checked at the column",
  "src/components/explain/ExplainPanel.tsx: formatDate(explanation.context.as_of)":
    "chosen by shape: the branch runs only for a `YYYY-MM-DD` value (04 API-S-Explain ContextOut)",
  "src/components/explain/ExplainPanel.tsx: formatTimestamp(explanation.context.as_of)":
    "chosen by shape: the branch runs only when the value is not `YYYY-MM-DD`",
  "src/components/filter-bar/FilterEditor.tsx: formatDate(value)":
    "a filter operand of a `date` field: typed by the user or read from the URL, validated as a date",
  "src/components/filter-bar/filters.ts: formatDate(value)":
    "a filter operand of a `date` field: typed by the user or read from the URL, validated as a date",
  "src/components/record/DiffView.tsx: formatTimestamp(submittedAt)":
    "a prop no product screen passes yet; documented as an RFC 3339 UTC instant",
  "src/components/record/Timeline.tsx: formatTimestamp(state.verifiedAt)":
    "a prop no product screen passes yet (the audit chain header)",
  "src/lib/api/queries/rule-sets.ts: formatDate(text)":
    "a rule output literal (free-form JSON): formatted only when it matches `YYYY-MM-DD`",
  'src/routes/access/access-reviews.tsx: member AccessReviewCreateIn.as_of(`${date}T${time === "" ? "00:00" : time}:00Z`)':
    "an instant assembled from the picked As of date and the typed UTC time of day",
  "src/routes/contracts/obligation-pane.tsx: formatDate(start)":
    "also an event payload member (free-form JSON, 04 §15.4 payload dates are `YYYY-MM-DD`)",
  "src/routes/contracts/obligation-pane.tsx: formatDate(end)":
    "also an event payload member and the recognition step detail (free-form JSON dates)",
  'src/routes/contracts/tabs/billing.tsx: column kind "date"(payloadString(event, "issue_date"))':
    "the invoice event payload `issue_date` (free-form JSON; SCREENS §6.4 DS-FMT-16)",
  "src/routes/contracts/workbench.tsx: formatDate(trigger.expected_date)":
    "the recognition step detail `expected_date` (free-form JSON date)",
  "src/routes/data/import-detail.tsx: formatDate(effective)":
    "the import parameter `effective_date` (free-form JSON; sent as a business date by SF-10:new)",
  "src/routes/data/import-new.tsx: formatDate(initialEffective)":
    "the corrected import's parameter `effective_date` carried in the navigation state",
  "src/routes/journals/journal-runs.tsx: instantMs(value)":
    "an instant assembled from the typed cut-off; a malformed one is caught and shown as an error",
  "src/routes/journals/run.tsx: formatTimestamp(ending.at)":
    "an export job's `result.waiting[].next_attempt_at` (free-form JSON; 04 §16.7 rev 1.221), chosen by shape: only an RFC 3339 UTC instant is read as a waiting batch",
  "src/routes/reports/report.tsx: formatDate(asOf)":
    "also the run's control total `as_of` (free-form JSON; SCREENS_B RV-04 as-of date)",
  "src/routes/reports/report.tsx: formatDate(from)":
    "the report parameter `from_date` (free-form JSON; SCREENS_B parameter tables: a date control)",
  "src/routes/reports/report.tsx: formatDate(to)":
    "the report parameter `to_date` (free-form JSON; SCREENS_B parameter tables: a date control)",
  "src/routes/reports/run.tsx: formatDate(asOf)":
    'also the run\'s control total `as_of` (free-form JSON; SCREENS_B §5.3 meta row "As of")',
  'src/routes/reports/runs.tsx: column kind "date"(runAsOf(run))':
    'also the run\'s control total `as_of` (free-form JSON; SCREENS_B §5.3 column "As of")',
  "src/routes/reports/viewer/ParametersToolbar.tsx: formatDate(value)":
    "a report date parameter from the URL, the run parameters or a period boundary",
  "src/routes/reports/viewer/RunStamp.tsx: formatDate(asOf)":
    "also the run's control total `as_of` (free-form JSON; SCREENS_B RV-04 as-of date)",
  "src/routes/reports/viewer/specs.ts: formatDate(value)":
    "a run parameter or control total (free-form JSON), chosen by shape: only a `YYYY-MM-DD` value reaches the call",
  "src/routes/reports/viewer/specs.ts: formatTimestamp(value)":
    "a run parameter or control total (free-form JSON), chosen by shape: only an RFC 3339 UTC instant reaches the call",
  "src/routes/settings/currencies.tsx: formatPeriod startDate(start)":
    "the first day of the rate's month, assembled from `dateParts` of its effective date",
};

const PROBE_PATH = "src/__probe__/api-dates.tsx";
// A source file that exists only in this test's program: the forms the trace must tell apart.
const PROBE = `import type { GridColumn } from "../components/data-grid/types";
import type { components } from "../lib/api/schema";
import { effectiveInstant, formatDate, formatTimestamp, timestampDate } from "../lib/format";

type Policy = components["schemas"]["PolicyOut"];
type Rate = components["schemas"]["FxRateOut"];

export function direct(policy: Policy): string {
  return formatDate(policy.effective_from);
}
export function aliased(policy: Policy): string {
  const from = policy.effective_from;
  return from === null ? "" : formatDate(from);
}
export function converted(policy: Policy): string {
  return policy.effective_from === null ? "" : formatDate(timestampDate(policy.effective_from));
}
export function reversed(rate: Rate): string {
  return formatTimestamp(rate.effective_date);
}
export function businessDate(rate: Rate): string {
  return formatDate(rate.effective_date);
}
function label(value: string | null): string {
  return formatDate(value);
}
export function throughParameter(policy: Policy): string {
  return label(policy.effective_to);
}
function Shown({ at }: { readonly at: string | null }) {
  return <span>{formatDate(at)}</span>;
}
export function Parent({ policy }: { readonly policy: Policy }) {
  return <Shown at={policy.effective_from} />;
}
export function columns(): GridColumn<Policy>[] {
  return [
    { id: "from", header: "From", kind: "date", value: (policy) => policy.effective_from },
    {
      id: "to",
      header: "To",
      kind: "date",
      value: (policy) => (policy.effective_to === null ? null : timestampDate(policy.effective_to)),
    },
    { id: "updated", header: "Updated", kind: "timestamp", value: (policy) => policy.updated_at },
  ];
}
export function opaque(values: Readonly<Record<string, string>>, key: string): string {
  return formatDate(values[key] ?? null);
}
type Update = components["schemas"]["PolicyUpdateIn"];
export function dateOnWire(policy: Policy): Update {
  const picked = policy.effective_from === null ? null : timestampDate(policy.effective_from);
  return { effective_from: picked };
}
export function instantOnWire(picked: string | null): Update {
  return { effective_from: picked === null ? null : effectiveInstant(picked) };
}
export function untypedBody(policy: Policy): unknown {
  return { effective_from: policy.effective_from === null ? null : timestampDate(policy.effective_from) };
}
export function checkedBody(policy: Policy): unknown {
  return {
    effective_from: policy.effective_from === null ? null : timestampDate(policy.effective_from),
  } satisfies Update;
}
`;

function key(use: SinkUse): string {
  return `${use.file}: ${use.sink}(${use.argument})`;
}

function described(use: SinkUse): string {
  const received = mismatches(use).map((origin) => `${origin.text} (${origin.format ?? ""})`);
  return `${use.file}:${String(use.line)} ${use.sink}(${use.argument}) wants ${use.wants}, receives ${received.join(", ")}`;
}

describe("DG-FE-20 API date formats at the format module", () => {
  let flow: DateFlow;
  let product: readonly SinkUse[];
  let probe: readonly SinkUse[];

  beforeAll(() => {
    flow = traceDateFlow(ROLES, { [PROBE_PATH]: PROBE });
    product = flow.uses.filter((use) => use.file !== PROBE_PATH);
    probe = flow.uses.filter((use) => use.file === PROBE_PATH);
  }, 300_000);

  it("every exported function of the format module has a date role or is listed as having none", () => {
    const classified = new Set([
      ...ROLES.dateSinks,
      ...ROLES.instantSinks,
      ...ROLES.dateProducers,
      ...ROLES.instantProducers,
      ...Object.keys(ROLES.dateOptions),
      ...OTHER_EXPORTS,
    ]);
    expect(flow.formatExports.filter((name) => !classified.has(name))).toEqual([]);
    expect([...classified].filter((name) => !flow.formatExports.includes(name))).toEqual([]);
  });

  it("the trace reports a date-time field at a date function through an alias, a parameter, a prop and a column, and a date at a date-time member", () => {
    const verdicts = probe.map((use) => {
      const verdict =
        mismatches(use).length > 0 ? "mismatch" : untraced(use).length > 0 ? "untraced" : "ok";
      return `${use.sink}(${use.argument}) ${verdict}`;
    });
    expect(verdicts).toEqual([
      "formatDate(policy.effective_from) mismatch",
      "formatDate(from) mismatch",
      "formatDate(timestampDate(policy.effective_from)) ok",
      "timestampDate(policy.effective_from) ok",
      "formatTimestamp(rate.effective_date) mismatch",
      "formatDate(rate.effective_date) ok",
      "formatDate(value) mismatch",
      "formatDate(at) mismatch",
      'column kind "date"(policy.effective_from) mismatch',
      'column kind "date"(policy.effective_to === null ? null : timestampDate(policy.effective_to)) ok',
      "timestampDate(policy.effective_to) ok",
      'column kind "timestamp"(policy.updated_at) ok',
      "formatDate(values[key] ?? null) untraced",
      // The write direction: a business date at a date-time member of a typed body is a mismatch; the
      // instant helper passes; an untyped body is not seen; `satisfies` brings it under the check.
      "timestampDate(policy.effective_from) ok",
      "member PolicyUpdateIn.effective_from(picked) mismatch",
      "member PolicyUpdateIn.effective_from(picked === null ? null : effectiveInstant(picked)) ok",
      "timestampDate(policy.effective_from) ok",
      "member PolicyUpdateIn.effective_from(policy.effective_from === null ? null : timestampDate(policy.effective_from)) mismatch",
      "timestampDate(policy.effective_from) ok",
    ]);
    const [direct] = probe;
    expect(direct === undefined ? [] : mismatches(direct)).toEqual([
      { kind: "field", text: "PolicyOut.effective_from", format: "date-time" },
    ]);
  });

  it("no product call passes a date-time field to a date function or a date field to an instant function", () => {
    expect(product.length).toBeGreaterThan(200);
    expect(product.filter((use) => mismatches(use).length > 0).map(described)).toEqual([]);
  });

  it("every argument the trace cannot follow is reviewed, and every review is still needed", () => {
    const open = new Set(
      product.filter((use) => mismatches(use).length === 0 && untraced(use).length > 0).map(key),
    );
    expect([...open].filter((entry) => !(entry in REVIEWED)).sort()).toEqual([]);
    expect(Object.keys(REVIEWED).filter((entry) => !open.has(entry))).toEqual([]);
  });
});
