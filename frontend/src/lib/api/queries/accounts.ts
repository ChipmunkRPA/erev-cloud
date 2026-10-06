// GL accounts (04 API-R-20 `GET, POST /gl-accounts`, `PATCH /gl-accounts/{id}`, T-REF-13; SCREENS_B
// §9.5; BUILD_SPEC RFD-19) and the account roles the published account mapping resolves to each
// account (API-R-20 `GET /account-mappings`, `GET /account-mappings/{id}/rules`; E-01).
import { fetchListPage, type ListPage, type ListQuery } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type GlAccount = components["schemas"]["GlAccountOut"];
export type GlAccountCreate = components["schemas"]["GlAccountIn"];
export type GlAccountUpdate = components["schemas"]["GlAccountUpdateIn"];
export type AccountType = components["schemas"]["AccountType"];
export type SourceSystem = components["schemas"]["SourceSystem"];
type AccountMapping = components["schemas"]["AccountMappingOut"];
type AccountMappingRule = components["schemas"]["AccountMappingRuleOut"];

export const GL_ACCOUNTS_PATH = "/api/v1/gl-accounts";
export const ACCOUNT_MAPPINGS_PATH = "/api/v1/account-mappings";
/** API-R-20: reads need `config.read`; account commands need `config.author`. */
export const ACCOUNT_AUTHOR_PERMISSION = "config.author";

/** E-52 in SCREENS_B §9.5 column order. */
export const ACCOUNT_TYPES: readonly AccountType[] = [
  "ASSET",
  "LIABILITY",
  "EQUITY",
  "REVENUE",
  "EXPENSE",
];

export function accountsKey(query: Readonly<Record<string, string>> = {}): QueryKey {
  return queryKey("gl-accounts", "tenant", query);
}

export function accountPath(accountId: string): string {
  return `${GL_ACCOUNTS_PATH}/${accountId}`;
}

/** One DataGrid page of `GET /gl-accounts` (DG-FE-07). */
export function fetchAccountsPage(
  query: ListQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<GlAccount>> {
  return fetchListPage<GlAccount>(GL_ACCOUNTS_PATH, { ...query, sort }, cursor);
}

/** Every account of the workspace, following cursors (drawer lookups; T-REF-13 lists are small). */
export async function fetchAllAccounts(): Promise<readonly GlAccount[]> {
  const items: GlAccount[] = [];
  let cursor: string | null = null;
  do {
    const page: ListPage<GlAccount> = await fetchListPage<GlAccount>(GL_ACCOUNTS_PATH, {}, cursor, {
      count: false,
    });
    items.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor !== null);
  return items;
}

export function mappedRolesKey(): QueryKey {
  return queryKey("account-mappings", "tenant", { status: "PUBLISHED", view: "roles" });
}

/**
 * The account roles of the published mapping by account code, each role once and in rule order; an
 * empty map when no mapping is published.
 */
export async function fetchMappedRoles(): Promise<ReadonlyMap<string, readonly string[]>> {
  const published = await fetchListPage<AccountMapping>(
    ACCOUNT_MAPPINGS_PATH,
    { status: "PUBLISHED" },
    null,
    { limit: 1, count: false },
  );
  const version = published.items[0];
  const roles = new Map<string, string[]>();
  if (version === undefined) {
    return roles;
  }
  let cursor: string | null = null;
  do {
    const page: ListPage<AccountMappingRule> = await fetchListPage<AccountMappingRule>(
      `${ACCOUNT_MAPPINGS_PATH}/${version.id}/rules`,
      {},
      cursor,
      { count: false },
    );
    for (const item of page.items) {
      const held = roles.get(item.gl_account.code) ?? [];
      if (!held.includes(item.account_role)) {
        held.push(item.account_role);
      }
      roles.set(item.gl_account.code, held);
    }
    cursor = page.nextCursor;
  } while (cursor !== null);
  return roles;
}

/** SCREENS_B §7 E-01 label: the literal in sentence case, for example "Billing clearing". */
export function accountRoleLabel(role: string): string {
  const words = role.toLowerCase().split("_");
  const [first = "", ...rest] = words;
  return [first.charAt(0).toUpperCase() + first.slice(1), ...rest].join(" ");
}
