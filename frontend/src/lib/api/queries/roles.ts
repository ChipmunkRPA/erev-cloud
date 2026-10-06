// Roles and separation of duties (04 API-R-06 `GET /roles`, `GET /roles/{id}`, `POST /roles`, `POST /roles/{id}/propose-change`, `GET /permissions`, `GET, POST /role-assignments`,
// `POST /role-assignments/{id}/revoke`; API-R-07 `GET /sod-rules`, `GET, POST /sod-exceptions`,
// `POST /sod-exceptions/{id}/revoke`; §16.12; T-PLT-09, T-PLT-11, T-PLT-13, T-PLT-14; REQ-PLT-008 to
// REQ-PLT-010; SCREENS_B §9.10 to §9.12; BUILD_SPEC WEB-19, WEB-20). The live SoD check of the invite and
// add-role drawers mirrors `auth/sod.py`: a member conflicts with a published rule when the permissions
// of the roles held or requested, plus the roles being added, meet both function A and function B. The
// API stays the enforcer (DG-FE-16): a refused assignment answers 409 `sod-conflict`.
import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "../client";
import { fetchListPage, type ListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { addDays } from "../../format";

export type Role = components["schemas"]["RoleOut"];
export type SodRule = components["schemas"]["SodRuleOut"];
export type SodException = components["schemas"]["SodExceptionOut"];
export type SodExceptionIn = components["schemas"]["SodExceptionIn"];
export type RoleAssignment = components["schemas"]["RoleAssignmentOut"];
export type RoleAssignmentIn = components["schemas"]["RoleAssignmentIn"];

export const ROLES_PATH = "/api/v1/roles";
export const ROLE_ASSIGNMENTS_PATH = "/api/v1/role-assignments";
export const SOD_RULES_PATH = "/api/v1/sod-rules";
export const SOD_EXCEPTIONS_PATH = "/api/v1/sod-exceptions";
/** SCREENS RT-88 SF-14:roles and RT-89 SF-14:sod. */
export const ROLES_ROUTE = "/settings/roles";
export const SOD_ROUTE = "/settings/separation-of-duties";
/** One page of choices (04 API-C-09 limit maximum); a workspace holds far fewer roles and rules. */
export const CHOICE_LIMIT = 200;
/** SCREENS_B §9.10, 04 T-PLT-14: a SoD exception lasts at most 366 days. */
export const EXCEPTION_MAX_DAYS = 366;

export function rolesKey(): QueryKey {
  return queryKey("roles", "tenant", { view: "active" });
}

/** The active roles by name (API-R-06), with their permission codes. */
export async function fetchActiveRoles(): Promise<readonly Role[]> {
  const page = await fetchListPage<Role>(ROLES_PATH, { is_active: true, sort: "name" }, null, {
    limit: CHOICE_LIMIT,
    count: false,
  });
  return page.items;
}

export function useActiveRoles(enabled = true) {
  return useQuery({ queryKey: rolesKey(), queryFn: fetchActiveRoles, enabled });
}

export function sodRulesKey(): QueryKey {
  return queryKey("sod-rules", "tenant", { status: "PUBLISHED" });
}

/** The published rule versions (DG-KRN-PERM-03), the ones the API checks at `now`. */
export async function fetchPublishedSodRules(): Promise<readonly SodRule[]> {
  const page = await fetchListPage<SodRule>(
    SOD_RULES_PATH,
    { status: ["PUBLISHED"], sort: "code" },
    null,
    { limit: CHOICE_LIMIT, count: false },
  );
  return page.items;
}

export function useSodRules(enabled = true) {
  return useQuery({ queryKey: sodRulesKey(), queryFn: fetchPublishedSodRules, enabled });
}

/** The permission codes of the given roles. */
export function permissionsOf(
  roleIds: readonly (string | null)[],
  roles: readonly Pick<Role, "id" | "permissions">[],
): ReadonlySet<string> {
  const held = new Set<string>();
  for (const id of roleIds) {
    const role = roles.find((candidate) => candidate.id === id);
    for (const permission of role?.permissions ?? []) {
      held.add(permission);
    }
  }
  return held;
}

/** The published rules whose function A and function B both meet the held permissions. */
export function sodConflicts(
  held: ReadonlySet<string>,
  rules: readonly SodRule[],
): readonly SodRule[] {
  return rules.filter(
    (rule) =>
      rule.function_a_permissions.some((code) => held.has(code)) &&
      rule.function_b_permissions.some((code) => held.has(code)),
  );
}

/**
 * True when the window of whole days from "Valid from" to "Valid to", its last day included (it is sent
 * as 00:00:00Z to 23:59:59Z, DS-I18N-08), lasts at most 366 days: "Valid to" is not before "Valid from"
 * and at most 365 days after it.
 */
export function validityWithinLimit(validFrom: string, validTo: string): boolean {
  return validTo >= validFrom && validTo <= addDays(validFrom, EXCEPTION_MAX_DAYS - 1);
}

export function roleAssignmentRevokePath(assignmentId: string): string {
  return `${ROLE_ASSIGNMENTS_PATH}/${assignmentId}/revoke`;
}

/** SCREENS_B §9.10 "SoD exception" column: the id prefix. */
export function idPrefix(id: string): string {
  return id.slice(0, 8);
}

// --- WEB-20: roles, permissions and the SoD screens ----------------------------------------------

export type Permission = components["schemas"]["PermissionOut"];
export type RoleCreateIn = components["schemas"]["RoleCreateIn"];
export type RoleChangeIn = components["schemas"]["RoleChangeIn"];
export type SodExceptionRevokeIn = components["schemas"]["SodExceptionRevokeIn"];
export type GrantStatus = components["schemas"]["GrantStatus"];

export const PERMISSIONS_PATH = "/api/v1/permissions";
/** SCREENS_B §9.11 "Use lowercase letters and underscores." */
export const ROLE_CODE_PATTERN = /^[a-z][a-z_]*$/;
/** E-96 literals in 04 order, the options of the exceptions Status chip. */
export const GRANT_STATUSES: readonly GrantStatus[] = [
  "REQUESTED",
  "APPROVED",
  "REJECTED",
  "REVOKED",
  "EXPIRED",
];
/** The exception statuses that can still be revoked (SCREENS_B §9.12). */
export const REVOCABLE_EXCEPTION_STATUSES: ReadonlySet<GrantStatus> = new Set([
  "REQUESTED",
  "APPROVED",
]);

export function roleCodeValid(code: string): boolean {
  return ROLE_CODE_PATTERN.test(code);
}

export function permissionsKey(): QueryKey {
  return queryKey("permissions", "tenant");
}

/** The T-PLT-11 permission catalogue (API-R-06 `GET /permissions`). */
export async function fetchPermissions(): Promise<readonly Permission[]> {
  const page = await fetchListPage<Permission>(PERMISSIONS_PATH, {}, null, {
    limit: CHOICE_LIMIT,
    count: false,
  });
  return page.items;
}

export function usePermissions(enabled = true) {
  return useQuery({ queryKey: permissionsKey(), queryFn: fetchPermissions, enabled });
}

/** Permissions by area, areas in catalogue order. */
export function groupPermissions(
  permissions: readonly Permission[],
): readonly (readonly [string, readonly Permission[]])[] {
  const groups = new Map<string, Permission[]>();
  for (const permission of permissions) {
    const group = groups.get(permission.area) ?? [];
    group.push(permission);
    groups.set(permission.area, group);
  }
  return [...groups.entries()];
}

/** Every role read, for invalidation after a command. */
export const EVERY_ROLE: QueryKey = queryKey("roles", "tenant");

export function rolesListKey(): QueryKey {
  return queryKey("roles", "tenant", { view: "list" });
}

/** One DataGrid page of `GET /roles` (DG-FE-07); by name without a URL sort. */
export function fetchRolesPage(
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<Role>> {
  return fetchListPage<Role>(ROLES_PATH, { sort: sort ?? "name" }, cursor);
}

export function roleKey(roleId: string): QueryKey {
  return queryKey("roles", "tenant", { id: roleId });
}

export function fetchRole(roleId: string): Promise<Role> {
  return unwrap(api.GET("/api/v1/roles/{role_id}", { params: { path: { role_id: roleId } } }));
}

export function useRole(roleId: string | null) {
  return useQuery({
    queryKey: roleKey(roleId ?? ""),
    queryFn: () => fetchRole(roleId ?? ""),
    enabled: roleId !== null,
  });
}

export function roleProposeChangePath(roleId: string): string {
  return `${ROLES_PATH}/${roleId}/propose-change`;
}

export function sodRulesListKey(): QueryKey {
  return queryKey("sod-rules", "tenant", { view: "list" });
}

/** One DataGrid page of `GET /sod-rules`, by code. */
export function fetchSodRulesPage(
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<SodRule>> {
  return fetchListPage<SodRule>(SOD_RULES_PATH, { sort: sort ?? "code" }, cursor);
}

export interface SodExceptionQuery {
  readonly status: readonly string[];
}

/** Every exception read, for invalidation after a command. */
export const EVERY_SOD_EXCEPTION: QueryKey = queryKey("sod-exceptions", "tenant");

export function sodExceptionsKey(query: SodExceptionQuery): QueryKey {
  return queryKey("sod-exceptions", "tenant", { view: "list", status: query.status.join(",") });
}

/**
 * One DataGrid page of `GET /sod-exceptions?status` (API-R-07), newest first: 04 API-C-09 default
 * order `id` descending. The route admits `id`, `valid_from` and `valid_to`.
 */
export function fetchSodExceptionsPage(
  query: SodExceptionQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<SodException>> {
  return fetchListPage<SodException>(
    SOD_EXCEPTIONS_PATH,
    { status: query.status, sort: sort ?? "-id" },
    cursor,
  );
}

export function sodExceptionRevokePath(exceptionId: string): string {
  return `${SOD_EXCEPTIONS_PATH}/${exceptionId}/revoke`;
}
