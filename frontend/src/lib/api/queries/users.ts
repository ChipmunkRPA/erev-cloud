// Members (04 API-R-05 `GET /users`, `POST /users`, `GET /users/{membership_id}`, `POST /users/{id}/suspend`,
// `/reactivate`, `/remove`, `/reset-mfa`, `/resend-invitation`; §16.12 API-S-User; E-78; SCREENS_B §9.10;
// SCREENS §0.4 RT-87, RT-108; BUILD_SPEC WEB-19). Lists are keyset pages of API-S-User rows, each with its
// active and requested roles; commands go through `useCommand` from the screens.
import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "../client";
import { fetchListPage, type ListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type UserItem = components["schemas"]["UserOut"];
export type UserRole = components["schemas"]["UserRoleOut"];
export type UserInvite = components["schemas"]["UserInviteIn"];
export type UserRoleGrant = components["schemas"]["UserRoleIn"];
export type MembershipStatus = components["schemas"]["MembershipStatus"];
export type MembershipReason = components["schemas"]["MembershipReasonIn"];
export type UserRoleStatus = UserRole["status"];

export const USERS_PATH = "/api/v1/users";
/** SCREENS RT-87 SF-14. */
export const USERS_ROUTE = "/settings/users";
/** SCREENS RT-108 SF-14:user. */
export const USER_ROUTE = "/settings/users/:membershipId";
/** SCREENS_B §9.10: reads and membership commands need `user.manage`; roles and exceptions `role.manage`. */
export const USER_MANAGE_PERMISSION = "user.manage";
export const ROLE_MANAGE_PERMISSION = "role.manage";
/** API-R-05 sort keys: `display_name`, `email`, `invited_at`, `id`; the grid opens by name. */
export const DEFAULT_USER_SORT = "display_name";
/** E-78 literals in 04 order. */
export const MEMBERSHIP_STATUSES: readonly MembershipStatus[] = [
  "INVITED",
  "ACTIVE",
  "SUSPENDED",
  "REMOVED",
];

export type MembershipAction =
  "suspend" | "reactivate" | "remove" | "reset-mfa" | "resend-invitation";

export interface UserListQuery {
  readonly status: readonly string[];
  readonly q: string | null;
}

export function usersKey(query: UserListQuery): QueryKey {
  return queryKey("users", "tenant", { view: "list", status: query.status.join(","), q: query.q });
}

/** Every member read, for invalidation after a command. */
export const EVERY_USER: QueryKey = queryKey("users", "tenant");

export function userKey(membershipId: string): QueryKey {
  return queryKey("users", "tenant", { id: membershipId });
}

/** One DataGrid page of `GET /users` (DG-FE-07). */
export function fetchUsersPage(
  query: UserListQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<UserItem>> {
  return fetchListPage<UserItem>(
    USERS_PATH,
    { status: query.status, q: query.q, sort: sort ?? DEFAULT_USER_SORT },
    cursor,
  );
}

export function fetchUser(membershipId: string): Promise<UserItem> {
  return unwrap(
    api.GET("/api/v1/users/{membership_id}", { params: { path: { membership_id: membershipId } } }),
  );
}

export function useUser(membershipId: string) {
  return useQuery({ queryKey: userKey(membershipId), queryFn: () => fetchUser(membershipId) });
}

export function userRoute(membershipId: string): string {
  return `/settings/users/${membershipId}`;
}

export function userPath(membershipId: string): string {
  return `${USERS_PATH}/${membershipId}`;
}

export function userActionPath(membershipId: string, action: MembershipAction): string {
  return `${userPath(membershipId)}/${action}`;
}

/** The roles a member holds or waits for: `ACTIVE` and `REQUESTED` assignments. */
export function currentRoles(user: Pick<UserItem, "roles">): readonly UserRole[] {
  return user.roles.filter((role) => role.status !== "REVOKED");
}

/** SCREENS_B §9.10 "Scope": null for all entities, else the entity codes in order. */
export function scopeCodes(role: Pick<UserRole, "is_all_entities" | "entities">): string | null {
  return role.is_all_entities ? null : role.entities.map((entity) => entity.code).join(", ");
}

/**
 * SCREENS_B §9.10: while setup is incomplete every grant is approved by rule AUTO-BOOTSTRAP, so the
 * answered invitation carries no requested role; otherwise the roles wait for approval.
 */
export function invitationOutcome(user: Pick<UserItem, "roles">): "bootstrap" | "pending" {
  return user.roles.some((role) => role.status === "REQUESTED") ? "pending" : "bootstrap";
}
