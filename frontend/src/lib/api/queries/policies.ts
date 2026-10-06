// The policy registry (04 API-R-13 `GET, POST /policies`, `GET, PATCH /policies/{id}` with `If-Match`,
// `POST /policies/{id}/test`, `/submit`, `/withdraw`, `POST /policies/presets/legacy-parity`, `GET
// /policies/resolve`, `GET /registry/parameters`; API-S-Policy, API-S-RegistryParameter; T-PLT-31; E-53;
// REQ-POL-003 to REQ-POL-007, REQ-POL-011; POLICIES §1; SCREENS §11.3; BUILD_SPEC RFD-23). Tenant,
// entity and book registry versions with framework defaults, legacy-parity values, levels, pinning and
// approval codes; the legacy-parity preset; simulation before approval. Commands go through
// `useCommand` from the screens.
import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "../client";
import { fetchListPage, type ListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { STRUCTURE_LIMIT } from "./tenant";

export type Policy = components["schemas"]["PolicyOut"];
export type PolicyCreate = components["schemas"]["PolicyIn"];
export type PolicyUpdate = components["schemas"]["PolicyUpdateIn"];
export type PolicyTest = components["schemas"]["PolicyTestIn"];
export type PolicyComment = components["schemas"]["PolicyCommentIn"];
export type PolicyDiff = components["schemas"]["PolicyDiffOut"];
export type RegistryParameter = components["schemas"]["RegistryParameterOut"];
export type RegistryCategory = components["schemas"]["RegistryCategory"];
export type RegistryScope = components["schemas"]["RegistryScope"];
export type LegacyParityPreset = components["schemas"]["LegacyParityPresetIn"];
export type SimulationSummary = components["schemas"]["SimulationSummaryOut"];

export const POLICIES_PATH = "/api/v1/policies";
export const LEGACY_PARITY_PATH = "/api/v1/policies/presets/legacy-parity";
export const REGISTRY_PARAMETERS_PATH = "/api/v1/registry/parameters";
/** SCREENS RT-63 and RT-64. */
export const ACCOUNTING_ROUTE = "/policies/accounting";
export const ACCOUNTING_VERSION_ROUTE = "/policies/accounting/:policyId";
/** E-53 literals in 04 order. */
export const REGISTRY_CATEGORIES: readonly RegistryCategory[] = [
  "ACCOUNTING_POLICY",
  "PRACTICAL_EXPEDIENT",
  "DISCLOSURE_ELECTION",
  "CLOSE",
  "PLATFORM",
  "SECURITY",
  "AI",
  "INTEGRATION",
];
/** SCREENS §11.3: these categories are edited on their Settings pages; the list shows them read-only. */
export const SETTINGS_CATEGORIES: ReadonlySet<RegistryCategory> = new Set([
  "PLATFORM",
  "SECURITY",
  "AI",
]);
/**
 * 04 §16.5 rev 1.183: a version of these categories needs no effective date; without one it takes
 * effect when it is published.
 */
export const INSTANT_CATEGORIES: ReadonlySet<RegistryCategory> = new Set([
  "PLATFORM",
  "CLOSE",
  "INTEGRATION",
  "SECURITY",
  "AI",
]);
/** The Settings page that edits each settings-owned category (SCREENS_B). */
export const SETTINGS_CATEGORY_ROUTES: Readonly<Partial<Record<RegistryCategory, string>>> = {
  PLATFORM: "/settings/workspace",
  CLOSE: "/settings/workspace",
  INTEGRATION: "/settings/workspace",
  SECURITY: "/settings/security",
  AI: "/settings/ai",
};
/** The version scopes a registry version can take (T-PLT-31). */
export const VERSION_SCOPES: readonly RegistryScope[] = ["TENANT", "ENTITY", "BOOK"];
export const PRESET_LEGACY_PARITY = "LEGACY_PARITY";
export const PRESET_DEFAULT = "DEFAULT";

export const EVERY_POLICY: QueryKey = queryKey("policies", "tenant");

export function policiesGridKey(): QueryKey {
  return queryKey("policies", "tenant", { view: "grid" });
}

/** One DataGrid page of `GET /policies`, newest first. 04 API-R-13 lists no `q`: no search. */
export function fetchPoliciesPage(
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<Policy>> {
  return fetchListPage<Policy>(POLICIES_PATH, { sort: sort ?? "-created_at" }, cursor);
}

export function allPoliciesKey(): QueryKey {
  return queryKey("policies", "tenant", { view: "all" });
}

/** Every registry version in scope (the published versions of each scope decide "Current value"). */
export async function fetchAllPolicies(): Promise<readonly Policy[]> {
  const policies: Policy[] = [];
  let cursor: string | null = null;
  do {
    const page: ListPage<Policy> = await fetchListPage<Policy>(POLICIES_PATH, {}, cursor, {
      limit: STRUCTURE_LIMIT,
      count: false,
    });
    policies.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor !== null);
  return policies;
}

export function policyKey(policyId: string): QueryKey {
  return queryKey("policies", "tenant", { view: "record", id: policyId });
}

export function fetchPolicy(policyId: string): Promise<Policy> {
  return unwrap(
    api.GET("/api/v1/policies/{policy_id}", { params: { path: { policy_id: policyId } } }),
  );
}

export function usePolicy(policyId: string) {
  return useQuery({ queryKey: policyKey(policyId), queryFn: () => fetchPolicy(policyId) });
}

export function policyPath(policyId: string): string {
  return `${POLICIES_PATH}/${policyId}`;
}

export function policyCommandPath(
  policyId: string,
  command: "test" | "submit" | "withdraw",
): string {
  return `${policyPath(policyId)}/${command}`;
}

export function accountingVersionRoute(policyId: string): string {
  return `${ACCOUNTING_ROUTE}/${policyId}`;
}

export function parametersKey(): QueryKey {
  return queryKey("registry-parameters", "public", { view: "all" });
}

/** Every registry parameter (POLICIES §1 plus the platform sections), in code order. */
export async function fetchAllParameters(): Promise<readonly RegistryParameter[]> {
  const parameters: RegistryParameter[] = [];
  let cursor: string | null = null;
  do {
    const page: ListPage<RegistryParameter> = await fetchListPage<RegistryParameter>(
      REGISTRY_PARAMETERS_PATH,
      { sort: "code" },
      cursor,
      { limit: STRUCTURE_LIMIT, count: false },
    );
    parameters.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor !== null);
  return parameters;
}

export function useParameters(enabled = true) {
  return useQuery({ queryKey: parametersKey(), queryFn: fetchAllParameters, enabled });
}

/** SCREENS §11.0: values change only while the version is DRAFT or TESTED (DB-04). */
export function isPolicyEditable(policy: Pick<Policy, "status">): boolean {
  return policy.status === "DRAFT" || policy.status === "TESTED";
}

/** True when two versions address the same registry scope (category, scope, entity and book). */
export function sameScope(
  a: Pick<Policy, "category" | "scope" | "entity_code" | "book">,
  b: Pick<Policy, "category" | "scope" | "entity_code" | "book">,
): boolean {
  return (
    a.category === b.category &&
    a.scope === b.scope &&
    (a.entity_code ?? null) === (b.entity_code ?? null) &&
    (a.book ?? null) === (b.book ?? null)
  );
}

/** The published version of the same scope, if any, whose values are the "Current value" column. */
export function currentPublished(
  policies: readonly Policy[],
  version: Pick<Policy, "category" | "scope" | "entity_code" | "book" | "id">,
): Policy | null {
  return (
    policies
      .filter(
        (candidate) =>
          candidate.id !== version.id &&
          candidate.status === "PUBLISHED" &&
          sameScope(candidate, version),
      )
      .sort((a, b) => b.version_no - a.version_no)[0] ?? null
  );
}

/** PRD SM-04: the statuses in which a version of a scope key is open. */
const OPEN_STATUSES: ReadonlySet<Policy["status"]> = new Set([
  "DRAFT",
  "TESTED",
  "SUBMITTED",
  "APPROVED",
]);

/**
 * The open version of the same scope other than `version`, if any. One version of a scope key is
 * open at a time (PRD SM-04): while it is, the API refuses a new version of the key and the edit
 * that reopens a rejected or withdrawn one.
 */
export function openVersion(
  policies: readonly Policy[],
  version: Pick<Policy, "category" | "scope" | "entity_code" | "book" | "id">,
): Policy | null {
  return (
    policies.find(
      (candidate) =>
        candidate.id !== version.id &&
        OPEN_STATUSES.has(candidate.status) &&
        sameScope(candidate, version),
    ) ?? null
  );
}

export type ValueKind = "enum" | "boolean" | "number" | "list" | "text";

export interface ValueControl {
  readonly kind: ValueKind;
  readonly options: readonly string[];
}

/** The editor a parameter's `value_schema` calls for (JSON Schema `enum`, `type`). */
export function valueControl(schema: Readonly<Record<string, unknown>>): ValueControl {
  const literals = schema.enum;
  if (Array.isArray(literals)) {
    return { kind: "enum", options: literals.map((literal) => String(literal)) };
  }
  const type = schema.type;
  if (type === "boolean") {
    return { kind: "boolean", options: ["true", "false"] };
  }
  if (type === "integer" || type === "number") {
    return { kind: "number", options: [] };
  }
  if (type === "array") {
    return { kind: "list", options: [] };
  }
  return { kind: "text", options: [] };
}

/** A registry value as the literal shown in the grid (lists joined by commas). */
export function formatLiteral(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (Array.isArray(value)) {
    return value.map((item) => formatLiteral(item)).join(", ");
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value);
}

/** Parses typed text back into the parameter's value type; null for an empty text. */
export function parseLiteral(
  control: ValueControl,
  schema: Readonly<Record<string, unknown>>,
  text: string,
): unknown {
  const trimmed = text.trim();
  if (trimmed === "") {
    return null;
  }
  switch (control.kind) {
    case "boolean":
      return trimmed === "true";
    case "number":
      return Number(trimmed);
    case "list": {
      const items = trimmed
        .split(",")
        .map((item) => item.trim())
        .filter((item) => item !== "");
      const itemType =
        typeof schema.items === "object" && schema.items !== null
          ? (schema.items as Record<string, unknown>).type
          : undefined;
      return itemType === "integer" || itemType === "number" ? items.map(Number) : items;
    }
    default:
      return trimmed;
  }
}

export interface ParameterRow {
  readonly parameter: RegistryParameter;
  /** The published value of the same scope, else the framework default. */
  readonly current: unknown;
  readonly currentLevel: "published" | "default";
  /** The version's proposed value, if the version sets the key. */
  readonly proposed: unknown;
  /** The version returns the key to the default (`diff_against_current[].change`, 04 §16.5). */
  readonly returned: boolean;
  /**
   * The version holds its author's statement (`DRAFT`, `TESTED`): a key it does not state keeps
   * the published value. A later version holds the whole value set: a key it does not hold is at
   * the framework default (04 T-PLT-32).
   */
  readonly statement: boolean;
  readonly changed: boolean;
  readonly forced: boolean;
}

/**
 * What the version holds for the key (SCREENS §11.3 "Proposed"): the value it states; the
 * framework default for a key it returns to the default; otherwise, for a statement, the
 * published value, which the version keeps — and for a version that holds the whole set, the
 * framework default: it holds no value for the key, whatever the published version holds now.
 */
export function proposedValue(row: ParameterRow): unknown {
  if (row.returned) {
    return row.parameter.default_asc606;
  }
  if (row.proposed !== undefined) {
    return row.proposed;
  }
  return row.statement ? row.current : row.parameter.default_asc606;
}

/** SCREENS §11.3 parameter grid rows: the category's parameters joined with the version's values. */
export function parameterRows(
  parameters: readonly RegistryParameter[],
  version: Pick<Policy, "category" | "values" | "diff_against_current" | "status">,
  published: Pick<Policy, "values"> | null,
): readonly ParameterRow[] {
  const changedCodes = new Set(version.diff_against_current.map((diff) => diff.code));
  const returnedCodes = new Set(
    version.diff_against_current
      .filter((diff) => diff.change === "RETURNED_TO_DEFAULT")
      .map((diff) => diff.code),
  );
  const statement = isPolicyEditable(version);
  return parameters
    .filter((parameter) => parameter.category === version.category)
    .map((parameter) => {
      const publishedValue = published?.values[parameter.code];
      const proposed = version.values[parameter.code];
      return {
        parameter,
        current: publishedValue ?? parameter.default_asc606,
        currentLevel: publishedValue === undefined ? "default" : "published",
        proposed,
        returned: returnedCodes.has(parameter.code),
        statement,
        // A statement is compared with the published value it stands on. A version that holds
        // the whole set is what the API says it changed: against the published version while
        // it is not published, and afterwards the difference it made to the one it superseded.
        changed:
          changedCodes.has(parameter.code) ||
          (statement &&
            proposed !== undefined &&
            formatLiteral(proposed) !== formatLiteral(publishedValue ?? parameter.default_asc606)),
        forced: parameter.is_forced_asc606,
      };
    });
}

/** The POLICIES §1 sections present among the rows, in order of first appearance. */
export function sectionsOf(rows: readonly ParameterRow[]): readonly string[] {
  return [...new Set(rows.map((row) => row.parameter.section))];
}

export interface ParameterFilter {
  readonly q: string;
  readonly section: string | null;
  readonly changedOnly: boolean;
}

export function filterRows(
  rows: readonly ParameterRow[],
  filter: ParameterFilter,
): readonly ParameterRow[] {
  const needle = filter.q.trim().toLowerCase();
  return rows.filter(
    (row) =>
      (filter.section === null || row.parameter.section === filter.section) &&
      (!filter.changedOnly || row.changed) &&
      (needle === "" ||
        row.parameter.code.toLowerCase().includes(needle) ||
        row.parameter.description.toLowerCase().includes(needle) ||
        (row.parameter.pol_id ?? "").toLowerCase().includes(needle)),
  );
}
