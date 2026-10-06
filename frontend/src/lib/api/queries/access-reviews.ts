// Access review campaigns (04 API-R-51 `GET, POST /access-reviews`, `GET /access-reviews/{id}`,
// `POST /access-reviews/{id}/start`, `/complete`, `/cancel`, `GET /access-reviews/{id}/items`,
// `POST /access-reviews/{id}/items/{item_id}/decide`, `/confirm-revocation`; API-R-12
// `GET /files/{id}/content`; T-PLT-40, T-PLT-41; E-107, E-108; REQ-CTL-006; SCREENS_B §9.13; BUILD_SPEC
// WEB-21). A campaign snapshots every membership with its roles, scopes, last login, grant date and
// grantor; reviewers holding `access.approve` certify or request revocation per member and track
// revocations to completion. Commands go through `useCommand` from the screens.
import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "../client";
import { fetchListPage, type ListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type AccessReview = components["schemas"]["AccessReviewOut"];
export type AccessReviewCreate = components["schemas"]["AccessReviewCreateIn"];
export type AccessReviewItem = components["schemas"]["AccessReviewItemOut"];
export type AccessReviewDecide = components["schemas"]["AccessReviewDecideIn"];
export type AccessReviewStatus = components["schemas"]["AccessReviewStatus"];
export type AccessReviewDecision = components["schemas"]["AccessReviewDecision"];
export type AccessReviewRole = components["schemas"]["AccessReviewRoleOut"];
export type AccessReviewCounts = components["schemas"]["AccessReviewCountsOut"];

export const ACCESS_REVIEWS_PATH = "/api/v1/access-reviews";
/** SCREENS RT-90 SF-14:access-reviews and RT-109 SF-14:access-review. */
export const ACCESS_REVIEWS_ROUTE = "/settings/access-reviews";
export const ACCESS_REVIEW_ROUTE = "/settings/access-reviews/:reviewId";
/** SCREENS_B §9.13: read, start, decide and complete need `access.approve`. */
export const ACCESS_APPROVE_PERMISSION = "access.approve";
/** E-107 literals in 04 order. */
export const ACCESS_REVIEW_STATUSES: readonly AccessReviewStatus[] = [
  "DRAFT",
  "IN_REVIEW",
  "COMPLETED",
  "CANCELLED",
];
/**
 * Newest campaign first without a URL sort: 04 API-C-09 default order `id` descending (ids are
 * UUIDv7, NC-04). API-R-51 admits `id`, `as_of` and `name`.
 */
export const DEFAULT_REVIEW_SORT = "-id";

export interface AccessReviewQuery {
  readonly status: readonly string[];
}

/** Every campaign read, for invalidation after a command. */
export const EVERY_ACCESS_REVIEW: QueryKey = queryKey("access-reviews", "tenant");

export function accessReviewsKey(query: AccessReviewQuery): QueryKey {
  return queryKey("access-reviews", "tenant", { view: "list", status: query.status.join(",") });
}

export function fetchAccessReviewsPage(
  query: AccessReviewQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<AccessReview>> {
  return fetchListPage<AccessReview>(
    ACCESS_REVIEWS_PATH,
    { status: query.status, sort: sort ?? DEFAULT_REVIEW_SORT },
    cursor,
  );
}

export function reviewKey(reviewId: string): QueryKey {
  return queryKey("access-reviews", "tenant", { id: reviewId });
}

export function fetchReview(reviewId: string): Promise<AccessReview> {
  return unwrap(
    api.GET("/api/v1/access-reviews/{access_review_id}", {
      params: { path: { access_review_id: reviewId } },
    }),
  );
}

export function useReview(reviewId: string, enabled = true) {
  return useQuery({
    queryKey: reviewKey(reviewId),
    queryFn: () => fetchReview(reviewId),
    enabled,
  });
}

export function reviewItemsKey(reviewId: string): QueryKey {
  return queryKey("access-reviews", "tenant", { id: reviewId, view: "items" });
}

export function reviewItemsPath(reviewId: string): string {
  return `${ACCESS_REVIEWS_PATH}/${reviewId}/items`;
}

/** One DataGrid page of the campaign's items; the API orders by member. */
export function fetchReviewItemsPage(
  reviewId: string,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<AccessReviewItem>> {
  return fetchListPage<AccessReviewItem>(reviewItemsPath(reviewId), { sort }, cursor);
}

export type ReviewAction = "start" | "complete" | "cancel";

export function reviewActionPath(reviewId: string, action: ReviewAction): string {
  return `${ACCESS_REVIEWS_PATH}/${reviewId}/${action}`;
}

export function itemDecidePath(reviewId: string, itemId: string): string {
  return `${reviewItemsPath(reviewId)}/${itemId}/decide`;
}

export function itemConfirmRevocationPath(reviewId: string, itemId: string): string {
  return `${reviewItemsPath(reviewId)}/${itemId}/confirm-revocation`;
}

export function reviewRoute(reviewId: string): string {
  return `/settings/access-reviews/${reviewId}`;
}

/** API-R-12: the stored snapshot file of a started campaign. */
export function fileContentPath(fileId: string): string {
  return `/api/v1/files/${fileId}/content`;
}

/** SCREENS_B §9.13 "Decided <n> of <m>": every item past PENDING over the members. */
export function decidedCount(counts: AccessReviewCounts): number {
  return counts.certified + counts.revoke_requested + counts.revoked;
}

/** SCREENS_B §9.13 "Roles at snapshot": "<role> (<scope>)" joined with "; ". */
export function rolesSnapshotText(roles: readonly AccessReviewRole[], allEntities: string): string {
  return roles
    .map(
      (role) =>
        `${role.role_code} (${role.is_all_entities ? allEntities : role.entity_codes.join(", ")})`,
    )
    .join("; ");
}

/** The earliest grant of the snapshot, or null. */
export function earliestGrant(roles: readonly AccessReviewRole[]): string | null {
  return roles.reduce<string | null>(
    (earliest, role) =>
      earliest === null || role.granted_at < earliest ? role.granted_at : earliest,
    null,
  );
}

/** The distinct grantors of the snapshot, in order of appearance. */
export function grantors(roles: readonly AccessReviewRole[]): readonly string[] {
  const names: string[] = [];
  for (const role of roles) {
    if (role.granted_by !== null && !names.includes(role.granted_by)) {
      names.push(role.granted_by);
    }
  }
  return names;
}
