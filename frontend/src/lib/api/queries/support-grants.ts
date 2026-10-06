// Support grants (04 API-R-14 `GET /support-grants?status`, `POST /support-grants/{id}/revoke`; T-PLT-33
// `support_grant`; E-96 `grant_status`; REQ-PLT-036; 05 SAR-29; SCREENS_B §9.14; BUILD_SPEC WEB-22). A
// platform operator reads a workspace only under a tenant-approved, time-boxed (at most 72 hours),
// read-only grant; a workspace administrator holding `support_grant.approve` decides the request in
// SF-12 and can revoke an approved grant here. Commands go through `useCommand` from the screen.
import { instantMs } from "../../format";
import { fetchListPage, type ListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type SupportGrant = components["schemas"]["SupportGrantOut"];
export type SupportGrantRevoke = components["schemas"]["SupportGrantRevokeIn"];
export type GrantStatus = components["schemas"]["GrantStatus"];

export const SUPPORT_GRANTS_PATH = "/api/v1/support-grants";
/** SCREENS RT-91 SF-14:security and RT-92 SF-14:support-access. */
export const SECURITY_ROUTE = "/settings/security";
export const SUPPORT_ACCESS_ROUTE = "/settings/support-access";
/** SCREENS §0.4: RT-91 reads with `settings.manage`; RT-92 reads and revokes with `support_grant.approve`. */
export const SETTINGS_MANAGE_PERMISSION = "settings.manage";
export const SUPPORT_GRANT_APPROVE_PERMISSION = "support_grant.approve";
/** T-PLT-33 `scope`: `CHECK (scope = 'READ_ONLY')` in 1.0. */
export const READ_ONLY_SCOPE = "READ_ONLY";
/** The most recent validity window first without a URL sort (API sorts `id`, `valid_from`, `valid_to`). */
export const DEFAULT_GRANT_SORT = "-valid_from";

export interface SupportGrantQuery {
  readonly status: readonly string[];
}

/** Every support-grant read, for invalidation after a command. */
export const EVERY_SUPPORT_GRANT: QueryKey = queryKey("support-grants", "tenant");

export function supportGrantsKey(query: SupportGrantQuery): QueryKey {
  return queryKey("support-grants", "tenant", { view: "list", status: query.status.join(",") });
}

export function fetchSupportGrantsPage(
  query: SupportGrantQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<SupportGrant>> {
  return fetchListPage<SupportGrant>(
    SUPPORT_GRANTS_PATH,
    { status: query.status, sort: sort ?? DEFAULT_GRANT_SORT },
    cursor,
  );
}

/** The requests awaiting a decision, one info banner each (SCREENS_B §9.14). */
export const PENDING_GRANTS_QUERY: SupportGrantQuery = { status: ["REQUESTED"] };

export function pendingGrantsKey(): QueryKey {
  return queryKey("support-grants", "tenant", { view: "pending" });
}

export function fetchPendingGrants(): Promise<readonly SupportGrant[]> {
  return fetchSupportGrantsPage(PENDING_GRANTS_QUERY, null, DEFAULT_GRANT_SORT).then(
    (page) => page.items,
  );
}

export function supportGrantRevokePath(grantId: string): string {
  return `${SUPPORT_GRANTS_PATH}/${grantId}/revoke`;
}

/** SCREENS_B §9.14 "Revoke" shows for approved and unexpired grants. */
export function isRevocable(grant: SupportGrant, nowMs: number): boolean {
  return grant.status === "APPROVED" && instantMs(grant.valid_to) > nowMs;
}
