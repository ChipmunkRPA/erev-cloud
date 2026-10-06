// Rule sets and their versions (04 API-R-25 `GET, POST /rule-sets`, `GET, POST /rule-sets/{id}/versions`,
// `GET, PATCH /rule-set-versions/{id}`, `GET, POST /rule-set-versions/{id}/rules`, `DELETE
// /rule-set-versions/{id}/rules/{rule_id}`, `POST /rule-set-versions/{id}/lint`, `/test`, `/submit`,
// `POST /rule-sets/{id}/evaluate`; T-REF-24 to T-REF-26; SCREENS §11.1; BUILD_SPEC RFD-22), with the
// condition and output summaries of the decision-table editor (`erev_engine.rules.FIELDS`, OPERATORS).
// The revenue policies page also lists obligation templates (API-R-24 `GET /pob-templates`,
// `GET /pob-template-versions/{id}`); RFD-23 owns their editor.
import { formatDate, formatList, formatNumber, NO_VALUE } from "../../format";
import { t } from "../../i18n/t";
import { api, unwrap } from "../client";
import { fetchListPage, type ListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type RuleSet = components["schemas"]["RuleSetOut"];
export type RuleSetVersion = components["schemas"]["RuleSetVersionOut"];
export type RuleSetVersionUpdate = components["schemas"]["RuleSetVersionUpdateIn"];
export type Rule = components["schemas"]["RuleOut"];
export type RuleSetKind = components["schemas"]["RuleSetKind"];
export type ConfigStatus = components["schemas"]["ConfigStatus"];
export type LintFinding = components["schemas"]["LintFindingOut"];
export type RuleSetEvaluation = components["schemas"]["RuleSetEvaluationOut"];
export type PobTemplate = components["schemas"]["PobTemplateOut"];
export type PobTemplateVersion = components["schemas"]["PobTemplateVersionOut"];

export const RULE_SETS_PATH = "/api/v1/rule-sets";
export const RULE_SET_VERSIONS_PATH = "/api/v1/rule-set-versions";
export const POB_TEMPLATES_PATH = "/api/v1/pob-templates";
/** API-R-25: reads and evaluation need `config.read`; authoring and the lifecycle `config.author`. */
export const CONFIG_READ_PERMISSION = "config.read";
export const CONFIG_AUTHOR_PERMISSION = "config.author";

/** SCREENS §11.1 revenue policies page: the "Assignment rules" kinds. */
export const REVENUE_KINDS: readonly RuleSetKind[] = ["POB_ASSIGNMENT", "SSP_ASSIGNMENT"];
/** SCREENS §11.1 control rules page, in the order of the page text. */
export const CONTROL_KINDS: readonly RuleSetKind[] = [
  "APPROVAL_ROUTING",
  "AUTO_APPROVAL",
  "HOLD",
  "COMBINATION_DETECTION",
  "DATA_QUALITY",
];

/** 04 DB-04: rules and example cases change only while the version is DRAFT or TESTED. */
export function isEditableStatus(status: ConfigStatus): boolean {
  return status === "DRAFT" || status === "TESTED";
}

const LINE_FACTS: readonly string[] = [
  "product.code",
  "product.product_family",
  "bundle_parent.code",
  "contract.region",
  "contract.channel",
  "customer.segment",
  "contract.contract_type",
  "line.term_band",
  "contract.currency",
  "effective_date",
];

/** `erev_engine.rules.FIELDS`: the condition fields of each E-55 kind. */
export const RULE_FIELDS: Readonly<Record<RuleSetKind, readonly string[]>> = {
  POB_ASSIGNMENT: LINE_FACTS,
  SSP_ASSIGNMENT: LINE_FACTS,
  APPROVAL_ROUTING: ["subject.type", "entity.code", "amount.functional", "flags"],
  AUTO_APPROVAL: [
    "subject.type",
    "preparer.role_codes",
    "tenant.setup_completed",
    "source.channel",
  ],
  COMBINATION_DETECTION: [],
  HOLD: [],
  DATA_QUALITY: [],
};

export const RULE_OPERATORS = ["eq", "in", "range", "prefix", "gte", "lte"] as const;
export type RuleOperator = (typeof RULE_OPERATORS)[number];

/** The fact types of `erev_api.domain.policies.rule_sets`; every other field holds text. */
const DECIMAL_FIELDS: ReadonlySet<string> = new Set(["amount.functional"]);
const DATE_FIELDS: ReadonlySet<string> = new Set(["effective_date"]);
const BOOLEAN_FIELDS: ReadonlySet<string> = new Set(["tenant.setup_completed"]);
/** Collection facts: a line carries several values, which conditions match with `eq` or `in`. */
export const LIST_FIELDS: ReadonlySet<string> = new Set(["flags", "preparer.role_codes"]);

export function isBooleanField(field: string): boolean {
  return BOOLEAN_FIELDS.has(field);
}

export function ruleSetsKey(kinds: readonly RuleSetKind[], search = ""): QueryKey {
  return queryKey("rule-sets", "tenant", { kind: kinds.join(","), q: search });
}

/** Every rule set list of the policies pages, for invalidation after a create. */
export const EVERY_RULE_SET: QueryKey = queryKey("rule-sets", "tenant");

export function ruleSetKey(ruleSetId: string): QueryKey {
  return queryKey("rule-sets", "tenant", { id: ruleSetId });
}

export function ruleSetVersionKey(versionId: string): QueryKey {
  return queryKey("rule-set-versions", "tenant", { id: versionId });
}

export function rulesKey(versionId: string): QueryKey {
  return queryKey("rule-set-versions", "tenant", { id: versionId, view: "rules" });
}

export function templatesKey(): QueryKey {
  return queryKey("pob-templates", "tenant", { view: "current-outputs" });
}

/** RT-62 SF-13:rule-set-version. */
export function ruleSetVersionRoute(ruleSetId: string, versionId: string): string {
  return `/policies/rule-sets/${ruleSetId}/versions/${versionId}`;
}

export function ruleSetVersionPath(versionId: string): string {
  return `${RULE_SET_VERSIONS_PATH}/${versionId}`;
}

/** One DataGrid page of `GET /rule-sets?kind=…&q=…` (DG-FE-07); `q` searches code and name. */
export function fetchRuleSetsPage(
  kinds: readonly RuleSetKind[],
  cursor: string | null,
  sort: string | null,
  search = "",
): Promise<ListPage<RuleSet>> {
  return fetchListPage<RuleSet>(
    RULE_SETS_PATH,
    { kind: kinds, sort, q: search === "" ? undefined : search },
    cursor,
  );
}

export function fetchRuleSet(ruleSetId: string): Promise<RuleSet> {
  return unwrap(
    api.GET("/api/v1/rule-sets/{rule_set_id}", { params: { path: { rule_set_id: ruleSetId } } }),
  );
}

export function fetchRuleSetVersion(versionId: string): Promise<RuleSetVersion> {
  return unwrap(
    api.GET("/api/v1/rule-set-versions/{version_id}", {
      params: { path: { version_id: versionId } },
    }),
  );
}

/** One DataGrid page of the rules of a version, in priority order. */
export function fetchRulesPage(
  versionId: string,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<Rule>> {
  return fetchListPage<Rule>(`${ruleSetVersionPath(versionId)}/rules`, { sort }, cursor);
}

/** Every rule of a version, following cursors (the drawers, lint copy and the changes diff). */
export async function fetchAllRules(versionId: string): Promise<readonly Rule[]> {
  const items: Rule[] = [];
  let cursor: string | null = null;
  do {
    const page: ListPage<Rule> = await fetchListPage<Rule>(
      `${ruleSetVersionPath(versionId)}/rules`,
      { sort: "rule_key" },
      cursor,
      { count: false },
    );
    items.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor !== null);
  return items;
}

export const SSP_BOOKS_PATH = "/api/v1/ssp-books";

async function allCodes(path: string): Promise<readonly string[]> {
  const codes: string[] = [];
  let cursor: string | null = null;
  do {
    const page: ListPage<{ readonly code: string }> = await fetchListPage<{
      readonly code: string;
    }>(path, { sort: "code" }, cursor, { count: false });
    codes.push(...page.items.map((item) => item.code));
    cursor = page.nextCursor;
  } while (cursor !== null);
  return codes;
}

/** The template codes of the `POB_ASSIGNMENT` output select (T-REF-26 `pob_template_code`). */
export function fetchTemplateCodes(): Promise<readonly string[]> {
  return allCodes(POB_TEMPLATES_PATH);
}

/** The SSP book codes of the `SSP_ASSIGNMENT` output select (T-REF-26 `ssp_book_code`). */
export function fetchSspBookCodes(): Promise<readonly string[]> {
  return allCodes(SSP_BOOKS_PATH);
}

export interface TemplateRow {
  readonly template: PobTemplate;
  /** The current PUBLISHED version, else the latest version; null for a template without one. */
  readonly version: PobTemplateVersion | null;
}

/**
 * One DataGrid page of `GET /pob-templates`. API-S-PobTemplate carries only version summaries, so each
 * row reads its current (else latest) version for the output columns (L4-5-Q-31).
 */
export async function fetchTemplatesPage(
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<TemplateRow>> {
  const page = await fetchListPage<PobTemplate>(POB_TEMPLATES_PATH, { sort }, cursor);
  const versions = await Promise.all(
    page.items.map((template) => {
      const summary = template.current_version ?? template.latest_version;
      return summary === null
        ? Promise.resolve(null)
        : unwrap(
            api.GET("/api/v1/pob-template-versions/{version_id}", {
              params: { path: { version_id: summary.id } },
            }),
          );
    }),
  );
  return {
    ...page,
    items: page.items.map((template, index) => ({ template, version: versions[index] ?? null })),
  };
}

/** SCREENS §11.1 kind labels. */
export function ruleSetKindLabel(kind: RuleSetKind): string {
  return t(`policies.ruleSets.kind.${kind}`);
}

/** SCREENS §11.1 Lint column: `PASS` "Valid", `FAIL` "Error", `NOT_APPLICABLE` or null "—". */
export function lintStatusWord(status: string | null): "Valid" | "Error" | null {
  if (status === "PASS") {
    return "Valid";
  }
  return status === "FAIL" ? "Error" : null;
}

export function fieldLabel(field: string): string {
  return t(`policies.field.${field}`);
}

/** SCREENS §11.1 operators; `gte` and `lte` read "on or after" and "on or before" for dates. */
export function operatorLabel(op: string, field: string): string {
  if (DATE_FIELDS.has(field) && (op === "gte" || op === "lte")) {
    return t(`policies.operator.${op}Date`);
  }
  return RULE_OPERATORS.includes(op as RuleOperator) ? t(`policies.operator.${op}`) : op;
}

function operandText(field: string, value: unknown): string {
  if (value === null || value === undefined) {
    return NO_VALUE;
  }
  if (typeof value === "boolean") {
    return t(value ? "common.grid.yes" : "common.grid.no");
  }
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (DECIMAL_FIELDS.has(field) && /^-?[0-9]+(\.[0-9]+)?$/.test(text)) {
    return formatNumber(text);
  }
  if (DATE_FIELDS.has(field) && /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(text)) {
    return formatDate(text);
  }
  return text;
}

export interface Condition {
  readonly field: string;
  readonly op: string;
  readonly value: unknown;
}

export function asCondition(raw: Readonly<Record<string, unknown>>): Condition {
  return {
    field: typeof raw.field === "string" ? raw.field : "",
    op: typeof raw.op === "string" ? raw.op : "",
    value: raw.value,
  };
}

/** "Subject is CONTRACT_ACTIVATION · Amount at least 1,000,000" (SCREENS §11.1 Conditions column). */
export function conditionSummary(conditions: readonly Readonly<Record<string, unknown>>[]): string {
  return conditions
    .map(asCondition)
    .map((condition) => {
      const label = fieldLabel(condition.field);
      const operator = operatorLabel(condition.op, condition.field);
      const operands = Array.isArray(condition.value) ? (condition.value as unknown[]) : null;
      let value: string;
      if (condition.op === "range" && operands !== null) {
        value = t("policies.operator.rangeValues", {
          lower: operandText(condition.field, operands[0]),
          upper: operandText(condition.field, operands[1]),
        });
      } else if (operands !== null) {
        value = formatList(
          operands.map((operand) => operandText(condition.field, operand)),
          "or",
        );
      } else {
        value = operandText(condition.field, condition.value);
      }
      return `${label} ${operator} ${value}`;
    })
    .join(" · ");
}

export interface RoutingStep {
  readonly name: string;
  readonly permission: string;
  readonly min_approvers: number;
}

export function routingSteps(outputs: Readonly<Record<string, unknown>>): readonly RoutingStep[] {
  const steps = outputs.steps;
  if (!Array.isArray(steps)) {
    return [];
  }
  return steps.map((step: unknown) => {
    const record = (typeof step === "object" && step !== null ? step : {}) as Record<
      string,
      unknown
    >;
    return {
      name: typeof record.name === "string" ? record.name : "",
      permission: typeof record.permission === "string" ? record.permission : "",
      min_approvers: typeof record.min_approvers === "number" ? record.min_approvers : 1,
    };
  });
}

function text(value: unknown): string {
  return typeof value === "string" ? value : NO_VALUE;
}

/** The Outputs column text of a rule, by kind (T-REF-26 outputs). */
export function outputSummary(
  kind: RuleSetKind,
  outputs: Readonly<Record<string, unknown>>,
): string {
  switch (kind) {
    case "APPROVAL_ROUTING":
      return routingSteps(outputs)
        .map((step, index) =>
          t(
            step.min_approvers > 1 ? "policies.rule.stepSummaryMany" : "policies.rule.stepSummary",
            {
              position: formatNumber(index + 1, { kind: "count" }),
              permission: step.permission,
              approvers: formatNumber(step.min_approvers, { kind: "count" }),
            },
          ),
        )
        .join(" · ");
    case "AUTO_APPROVAL":
      return t("policies.rule.output.autoApprove");
    case "POB_ASSIGNMENT":
      return text(outputs.pob_template_code);
    case "SSP_ASSIGNMENT":
      return text(outputs.ssp_book_code);
    case "COMBINATION_DETECTION":
      return t("policies.rule.combinationSummary", {
        days:
          typeof outputs.window_days === "number" ? formatNumber(outputs.window_days) : NO_VALUE,
        match:
          typeof outputs.match === "string"
            ? t(`policies.rule.output.match.${outputs.match}`)
            : NO_VALUE,
      });
    case "HOLD":
      return `${text(outputs.hold_type)} · ${
        typeof outputs.level === "string"
          ? t(`policies.rule.output.level.${outputs.level}`)
          : NO_VALUE
      }`;
    case "DATA_QUALITY":
      return `${
        typeof outputs.severity === "string"
          ? t(`policies.rule.output.severity.${outputs.severity}`)
          : NO_VALUE
      } · ${text(outputs.message)}`;
  }
}

/** The text of a condition value in the rule drawer: members and bounds separated by commas. */
export function conditionValueText(value: unknown): string {
  if (Array.isArray(value)) {
    return (value as unknown[]).map((item) => (item === null ? "" : String(item))).join(", ");
  }
  if (value === null || value === undefined) {
    return "";
  }
  return String(value);
}

/** The condition value the API takes for the typed text (decimals and dates travel as text). */
export function parseConditionValue(field: string, op: string, typed: string): unknown {
  const parts = typed.split(",").map((part) => part.trim());
  const scalar = (part: string): unknown =>
    BOOLEAN_FIELDS.has(field) ? part.toLowerCase() === "true" : part;
  if (op === "in") {
    return parts.filter((part) => part !== "").map(scalar);
  }
  if (op === "range") {
    const [lower = "", upper = ""] = parts;
    return [lower === "" ? null : lower, upper === "" ? null : upper];
  }
  return scalar(typed.trim());
}

/**
 * SCREENS §11.1 lint copy "Rules <a> and <b> have equal specificity (<n>) and priority (<p>)…"; the API
 * message when a finding names a rule the version no longer holds.
 */
export function lintMessage(finding: LintFinding, rules: readonly Rule[]): string {
  const [first, second] = finding.rule_keys;
  const rule = rules.find((candidate) => candidate.rule_key === first);
  if (first === undefined || second === undefined || rule === undefined) {
    return finding.message;
  }
  return t("policies.lint.overlap", {
    first,
    second,
    specificity: formatNumber(rule.specificity, { kind: "count" }),
    priority: formatNumber(rule.priority),
  });
}

export type ChangeKind = "added" | "removed" | "changed";

export interface RuleChange {
  readonly kind: ChangeKind;
  readonly rule: Rule;
  /** The baseline rule of a changed or removed row. */
  readonly previous: Rule | null;
  /** The columns whose values differ: priority, conditions, outputs, description. */
  readonly changed: ReadonlySet<string>;
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(canonical).join(",")}]`;
  }
  if (typeof value === "object" && value !== null) {
    const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) =>
      a < b ? -1 : a > b ? 1 : 0,
    );
    return `{${entries.map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

/** DS-CMP-16 grid diff: the rules added, removed and changed against the baseline, by rule key. */
export function compareRules(
  rules: readonly Rule[],
  baseline: readonly Rule[],
): readonly RuleChange[] {
  const before = new Map(baseline.map((rule) => [rule.rule_key, rule]));
  const after = new Set(rules.map((rule) => rule.rule_key));
  const changes: RuleChange[] = [];
  for (const rule of rules) {
    const previous = before.get(rule.rule_key);
    if (previous === undefined) {
      changes.push({ kind: "added", rule, previous: null, changed: new Set() });
      continue;
    }
    const changed = new Set<string>();
    if (previous.priority !== rule.priority) {
      changed.add("priority");
    }
    if (canonical(previous.conditions) !== canonical(rule.conditions)) {
      changed.add("conditions");
    }
    if (canonical(previous.outputs) !== canonical(rule.outputs)) {
      changed.add("outputs");
    }
    if ((previous.description ?? null) !== (rule.description ?? null)) {
      changed.add("description");
    }
    if (changed.size > 0) {
      changes.push({ kind: "changed", rule, previous, changed });
    }
  }
  for (const previous of baseline) {
    if (!after.has(previous.rule_key)) {
      changes.push({ kind: "removed", rule: previous, previous, changed: new Set() });
    }
  }
  return changes;
}

/** SCREENS §4 Distinctness words; a series names its increment unit. */
export function distinctnessLabel(version: PobTemplateVersion): string {
  if (version.distinctness === "series") {
    const unit = version.series_increment_unit;
    return t("policies.template.series", {
      unit: unit === null ? NO_VALUE : sentenceCase(unit),
    });
  }
  return t(`policies.template.distinctness.${version.distinctness}`);
}

/** A literal in sentence case, for example `MONTH` "Month". */
export function sentenceCase(literal: string): string {
  const words = literal.toLowerCase().split("_");
  const [first = "", ...rest] = words;
  return [first.charAt(0).toUpperCase() + first.slice(1), ...rest].join(" ");
}
