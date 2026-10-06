// Account-role mapping versions (04 API-R-20 `GET, POST /account-mappings`, `GET, PATCH
// /account-mappings/{id}` with `If-Match`, `POST …/test`, `/submit`, `GET, POST …/rules`, `DELETE
// …/rules/{rule_id}`, `GET /account-mappings/resolve`; T-REF-14, T-REF-15; E-01 account roles, E-109
// clearing purposes; REQ-REF-008, REQ-JE-022; SCREENS §11.6; BUILD_SPEC RFD-25). A version maps the
// account roles × entity × optional book, product or revenue category to GL accounts; billing clearing
// rules carry a clearing purpose; two roles are reserved and take no rule. Coverage is computed on the
// client from the loaded rules. Commands go through `useCommand` from the screens.
import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "../client";
import { fetchListPage, type ListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { STRUCTURE_LIMIT } from "./tenant";

export type AccountMapping = components["schemas"]["AccountMappingOut"];
export type AccountMappingCreate = components["schemas"]["AccountMappingIn"];
export type AccountMappingUpdate = components["schemas"]["AccountMappingUpdateIn"];
export type AccountMappingRule = components["schemas"]["AccountMappingRuleOut"];
export type AccountMappingRuleCreate = components["schemas"]["AccountMappingRuleIn"];
export type AccountResolution = components["schemas"]["AccountResolutionOut"];
export type AccountRole = components["schemas"]["AccountRole"];
export type ClearingPurpose = components["schemas"]["ClearingPurpose"];

export const ACCOUNT_MAPPINGS_PATH = "/api/v1/account-mappings";
export const ACCOUNT_MAPPINGS_RESOLVE_PATH = "/api/v1/account-mappings/resolve";
/** SCREENS RT-69 and RT-70. */
export const ACCOUNT_MAPPING_ROUTE = "/policies/account-mapping";
export const ACCOUNT_MAPPING_VERSION_ROUTE = "/policies/account-mapping/:mappingVersionId";

export type MappingPane = "rules" | "coverage" | "resolve" | "simulation" | "changes";
export const MAPPING_PANES: readonly MappingPane[] = [
  "rules",
  "coverage",
  "resolve",
  "simulation",
  "changes",
];

export function mappingPaneOf(value: string | null): MappingPane {
  return MAPPING_PANES.find((pane) => pane === value) ?? "rules";
}

/** E-01 literals in 04 order (D-14a: 33 roles). */
export const ACCOUNT_ROLES: readonly AccountRole[] = [
  "REVENUE",
  "CONTRACT_LIABILITY",
  "CONTRACT_ASSET",
  "UNBILLED_RECEIVABLE",
  "ACCOUNTS_RECEIVABLE",
  "BILLING_CLEARING",
  "REFUND_LIABILITY",
  "RETURN_ASSET",
  "DEPOSIT_LIABILITY",
  "CONSIDERATION_PAYABLE",
  "CUSTOMER_INCENTIVE_ASSET",
  "COST_TO_OBTAIN_ASSET",
  "COST_TO_FULFILL_ASSET",
  "CONTRACT_COST_AMORTIZATION",
  "CONTRACT_COST_IMPAIRMENT",
  "LOSS_PROVISION",
  "LOSS_EXPENSE",
  "WARRANTY_PROVISION",
  "WARRANTY_EXPENSE",
  "INTEREST_INCOME",
  "INTEREST_EXPENSE",
  "FX_GAIN_LOSS",
  "INTERCOMPANY_DUE_TO",
  "INTERCOMPANY_DUE_FROM",
  "NONCASH_CONSIDERATION_ASSET",
  "SALES_TAX_PAYABLE",
  "PRE_STANDARD_REVENUE",
  "ROUNDING",
  "COST_OF_REVENUE",
  "CONTRACT_COST_CLEARING",
  "RECEIVABLE_CONTRA",
  "RETAINED_EARNINGS",
  "FINANCING_OBLIGATION",
];
/** 04 `ck_account_mapping_rule__reserved_role`: these roles take no mapping rule. */
export const RESERVED_ROLES: ReadonlySet<AccountRole> = new Set([
  "RETAINED_EARNINGS",
  "FINANCING_OBLIGATION",
]);
/** The 31 mappable roles offered by the rule form. */
export const MAPPABLE_ROLES: readonly AccountRole[] = ACCOUNT_ROLES.filter(
  (role) => !RESERVED_ROLES.has(role),
);
/** E-109 literals in 04 order. */
export const CLEARING_PURPOSES: readonly ClearingPurpose[] = [
  "BILLING",
  "UNAPPLIED_CASH",
  "AP_SUPPLIER",
  "INVENTORY",
  "EQUITY",
  "INVESTMENTS",
];
export const BILLING_CLEARING: AccountRole = "BILLING_CLEARING";

export const EVERY_ACCOUNT_MAPPING: QueryKey = queryKey("account-mappings", "tenant");

export function mappingsGridKey(query: string): QueryKey {
  return queryKey("account-mappings", "tenant", { view: "grid", q: query });
}

export function fetchMappingsPage(
  query: string,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<AccountMapping>> {
  return fetchListPage<AccountMapping>(
    ACCOUNT_MAPPINGS_PATH,
    { q: query === "" ? null : query, sort: sort ?? "-version_no" },
    cursor,
  );
}

export function publishedMappingKey(): QueryKey {
  return queryKey("account-mappings", "tenant", { status: "PUBLISHED", view: "latest" });
}

/** The published mapping version, which "New mapping version" copies. */
export async function fetchPublishedMapping(): Promise<AccountMapping | null> {
  const page = await fetchListPage<AccountMapping>(
    ACCOUNT_MAPPINGS_PATH,
    { status: ["PUBLISHED"], sort: "-version_no" },
    null,
    { limit: 1, count: false },
  );
  return page.items[0] ?? null;
}

export function mappingKey(versionId: string): QueryKey {
  return queryKey("account-mappings", "tenant", { view: "record", id: versionId });
}

export function fetchMapping(versionId: string): Promise<AccountMapping> {
  return unwrap(
    api.GET("/api/v1/account-mappings/{version_id}", {
      params: { path: { version_id: versionId } },
    }),
  );
}

export function useMapping(versionId: string) {
  return useQuery({ queryKey: mappingKey(versionId), queryFn: () => fetchMapping(versionId) });
}

export function mappingPath(versionId: string): string {
  return `${ACCOUNT_MAPPINGS_PATH}/${versionId}`;
}

export function mappingCommandPath(versionId: string, command: "test" | "submit"): string {
  return `${mappingPath(versionId)}/${command}`;
}

export function rulesPath(versionId: string): string {
  return `${mappingPath(versionId)}/rules`;
}

export function rulePath(versionId: string, ruleId: string): string {
  return `${rulesPath(versionId)}/${ruleId}`;
}

export function rulesKey(versionId: string): QueryKey {
  return queryKey("account-mappings", "tenant", { view: "rules", id: versionId });
}

/** Every rule of a version, in the API order (role, then specificity and priority). */
export async function fetchAllRules(versionId: string): Promise<readonly AccountMappingRule[]> {
  const rules: AccountMappingRule[] = [];
  let cursor: string | null = null;
  do {
    const page: ListPage<AccountMappingRule> = await fetchListPage<AccountMappingRule>(
      rulesPath(versionId),
      {},
      cursor,
      { limit: STRUCTURE_LIMIT, count: false },
    );
    rules.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor !== null);
  return rules;
}

export function mappingVersionRoute(versionId: string): string {
  return `${ACCOUNT_MAPPING_ROUTE}/${versionId}`;
}

/** SCREENS §11.0: rules change only while the version is DRAFT or TESTED (DB-04). */
export function isMappingEditable(mapping: Pick<AccountMapping, "status">): boolean {
  return mapping.status === "DRAFT" || mapping.status === "TESTED";
}

export interface ResolveQuery {
  readonly role: AccountRole;
  readonly clearingPurpose: ClearingPurpose | null;
  readonly entity: string | null;
  readonly book: components["schemas"]["BookCode"] | null;
  readonly product: string | null;
  readonly revenueCategory: string | null;
  readonly knownAt: string | null;
}

/** `GET /account-mappings/resolve` for the Test resolution panel (SCREENS §11.6). */
export function resolveAccount(query: ResolveQuery): Promise<AccountResolution> {
  return unwrap(
    api.GET("/api/v1/account-mappings/resolve", {
      params: {
        query: {
          role: query.role,
          clearing_purpose: query.clearingPurpose,
          entity: query.entity,
          book: query.book,
          product: query.product,
          revenue_category: query.revenueCategory,
          known_at: query.knownAt,
        },
      },
    }),
  );
}

export type CoverageStatus = "mapped" | "not-mapped" | "reserved";

export interface CoverageRow {
  readonly role: AccountRole;
  readonly clearingPurpose: ClearingPurpose | null;
  readonly status: CoverageStatus;
  readonly ruleCount: number;
}

/** SCREENS §11.6 coverage: one row per role and one per clearing purpose of billing clearing (38 rows). */
export function coverageRows(rules: readonly AccountMappingRule[]): readonly CoverageRow[] {
  const count = (role: AccountRole, purpose: ClearingPurpose | null) =>
    rules.filter(
      (rule) =>
        rule.account_role === role && (purpose === null || rule.clearing_purpose === purpose),
    ).length;
  const rows: CoverageRow[] = [];
  for (const role of ACCOUNT_ROLES) {
    if (RESERVED_ROLES.has(role)) {
      rows.push({ role, clearingPurpose: null, status: "reserved", ruleCount: 0 });
    } else if (role === BILLING_CLEARING) {
      for (const purpose of CLEARING_PURPOSES) {
        const ruleCount = count(role, purpose);
        rows.push({
          role,
          clearingPurpose: purpose,
          status: ruleCount > 0 ? "mapped" : "not-mapped",
          ruleCount,
        });
      }
    } else {
      const ruleCount = count(role, null);
      rows.push({
        role,
        clearingPurpose: null,
        status: ruleCount > 0 ? "mapped" : "not-mapped",
        ruleCount,
      });
    }
  }
  return rows;
}

export interface RuleDraft {
  readonly role: AccountRole | null;
  readonly clearingPurpose: ClearingPurpose | null;
  readonly entityId: string | null;
  readonly book: components["schemas"]["BookCode"] | null;
  readonly productId: string | null;
  readonly revenueCategory: string;
  readonly glAccountId: string | null;
  readonly priority: string;
}

export const EMPTY_RULE_DRAFT: RuleDraft = {
  role: null,
  clearingPurpose: null,
  entityId: null,
  book: null,
  productId: null,
  revenueCategory: "",
  glAccountId: null,
  priority: "100",
};

export type RuleDraftError =
  | "role"
  | "clearingPurposeRequired"
  | "clearingPurposeForbidden"
  | "productOrCategory"
  | "glAccount"
  | "priority";

/** SCREENS §11.6 validation of a rule draft, in field order. */
export function ruleDraftErrors(draft: RuleDraft): readonly RuleDraftError[] {
  const errors: RuleDraftError[] = [];
  if (draft.role === null) {
    errors.push("role");
  }
  if (draft.role === BILLING_CLEARING && draft.clearingPurpose === null) {
    errors.push("clearingPurposeRequired");
  }
  if (draft.role !== null && draft.role !== BILLING_CLEARING && draft.clearingPurpose !== null) {
    errors.push("clearingPurposeForbidden");
  }
  if (draft.productId !== null && draft.revenueCategory.trim() !== "") {
    errors.push("productOrCategory");
  }
  if (draft.glAccountId === null) {
    errors.push("glAccount");
  }
  if (!/^\d+$/.test(draft.priority.trim())) {
    errors.push("priority");
  }
  return errors;
}

export function ruleInput(draft: RuleDraft): AccountMappingRuleCreate {
  return {
    account_role: draft.role ?? "REVENUE",
    clearing_purpose: draft.role === BILLING_CLEARING ? draft.clearingPurpose : null,
    entity_id: draft.entityId,
    book_code: draft.book,
    product_id: draft.productId,
    revenue_category: draft.revenueCategory.trim() === "" ? null : draft.revenueCategory.trim(),
    gl_account_id: draft.glAccountId ?? "",
    priority: Number(draft.priority.trim()),
    default_dimensions: {},
  };
}

/** The key that identifies a rule across versions in the Changes pane. */
export function ruleKey(rule: AccountMappingRule): string {
  return [
    rule.account_role,
    rule.clearing_purpose ?? "",
    rule.entity_id ?? "",
    rule.book_code ?? "",
    rule.product_id ?? "",
    rule.revenue_category ?? "",
    rule.gl_account.code,
    String(rule.priority),
  ].join("|");
}

export interface RuleChanges {
  readonly added: readonly AccountMappingRule[];
  readonly removed: readonly AccountMappingRule[];
}

/** The rules a version adds to and removes from the version it supersedes. */
export function ruleChanges(
  rules: readonly AccountMappingRule[],
  previous: readonly AccountMappingRule[],
): RuleChanges {
  const before = new Set(previous.map(ruleKey));
  const after = new Set(rules.map(ruleKey));
  return {
    added: rules.filter((rule) => !before.has(ruleKey(rule))),
    removed: previous.filter((rule) => !after.has(ruleKey(rule))),
  };
}
