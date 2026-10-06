// Approval delegations and bulk approval (04 §15.3 API-R-09 `GET, POST /approval-delegations`, `POST
// /approval-delegations/{id}/revoke`, `POST /approvals/bulk-approve`; T-PLT-21; §16.10 bulk command;
// PRD BR-PLT-06, BR-PLT-07; REQ-PLT-013, REQ-PLT-017; SCREENS §15.5, §15.7; BUILD_SPEC WEB-16). A member
// lists the delegations they gave and received, newest first (sort keys `created_at`, `valid_from`,
// `valid_to`; no filters). Creating and revoking a delegation need an MFA-verified session with a
// verification at most five minutes old (403 `mfa-required`, `mfa-step-up-required`); only the delegator
// revokes. T-PLT-21 stores no status: a delegation is revoked when `revoked_at` is set, has ended when
// `valid_to` has passed, is in force between its two instants and has not started before the first. The
// bulk command takes 1 to 200 items, each with the hashes of its own request, approves every item in a
// transaction of its own and answers one result per item, a refusal as that item's problem.
import { addDays, instantMs } from "../../format";
import { fetchListPage, type ListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import type { Approval, ApprovalListFilters } from "./approvals";
import { type UserItem, USERS_PATH } from "./users";

export type Delegation = components["schemas"]["ApprovalDelegationOut"];
export type DelegationCreate = components["schemas"]["ApprovalDelegationIn"];
export type DelegationRevoke = components["schemas"]["ApprovalDelegationRevokeIn"];
export type BulkApprove = components["schemas"]["BulkApproveIn"];
export type BulkApproveItem = components["schemas"]["BulkApproveItemIn"];
export type BulkApproved = components["schemas"]["BulkApproveOut"];
export type BulkApproveResult = components["schemas"]["BulkApproveResultOut"];

export const DELEGATIONS_PATH = "/api/v1/approval-delegations";
export const BULK_APPROVE_PATH = "/api/v1/approvals/bulk-approve";
/** SCREENS §0.4 RT-58 SF-12:delegations. */
export const DELEGATIONS_ROUTE = "/approvals/delegations";
/** 04 §16.10: the bulk command refuses more items (REQ-PLT-017). */
export const BULK_LIMIT = 200;
/** PRD BR-PLT-07, T-PLT-21 CHECK: from the first instant to the last, at most 90 days. */
export const DELEGATION_MAX_DAYS = 90;

export const EVERY_DELEGATION: QueryKey = queryKey("approval-delegations", "tenant");

export function delegationsKey(): QueryKey {
  return queryKey("approval-delegations", "tenant", { list: true });
}

export function revokePath(delegationId: string): string {
  return `${DELEGATIONS_PATH}/${delegationId}/revoke`;
}

/** One page of the delegations the caller gave or received; without a sort, newest first (API-R-09). */
export function fetchDelegationsPage(
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<Delegation>> {
  return fetchListPage<Delegation>(DELEGATIONS_PATH, { sort }, cursor);
}

/**
 * True when the window of whole days from "Valid from" to "Valid to", its last day included (sent as
 * 00:00:00Z to 23:59:59Z, DS-I18N-08), lasts at most 90 days: "Valid to" is at most 89 days after
 * "Valid from" (PRD BR-PLT-07).
 */
export function delegationWithinLimit(validFrom: string, validTo: string): boolean {
  return validTo <= addDays(validFrom, DELEGATION_MAX_DAYS - 1);
}

/** The page size of the delegate choices, the API's maximum (04 API-C-09). */
const CHOICE_PAGE_SIZE = 500;
const CHOICE_MAX_PAGES = 10;

export function delegateChoicesKey(): QueryKey {
  return queryKey("users", "tenant", { view: "delegates" });
}

/**
 * SCREENS §15.7 "Delegate": the workspace's active members by name, from `GET /users` (API-R-05), which
 * needs `user.manage`. API-R-09 has no read of the members a delegation may name, so a member without
 * that permission has no choices (item reported to the supervisor).
 */
export async function fetchDelegateChoices(): Promise<readonly UserItem[]> {
  const members: UserItem[] = [];
  let cursor: string | null = null;
  for (let page = 0; page < CHOICE_MAX_PAGES; page += 1) {
    const result: ListPage<UserItem> = await fetchListPage<UserItem>(
      USERS_PATH,
      { status: ["ACTIVE"], sort: "display_name" },
      cursor,
      { limit: CHOICE_PAGE_SIZE, count: false },
    );
    members.push(...result.items);
    cursor = result.nextCursor;
    if (cursor === null) {
      break;
    }
  }
  return members;
}

/** SCREENS §15.7 Status. `NOT_STARTED` is a delegation whose first instant is still ahead. */
export type DelegationStatus = "ACTIVE" | "REVOKED" | "EXPIRED" | "NOT_STARTED";

/** The status of a delegation at `nowMs`, read from `revoked_at` and its two instants (T-PLT-21). */
export function delegationStatus(
  delegation: Pick<Delegation, "revoked_at" | "valid_from" | "valid_to">,
  nowMs: number,
): DelegationStatus {
  if (delegation.revoked_at !== null) {
    return "REVOKED";
  }
  if (instantMs(delegation.valid_to) <= nowMs) {
    return "EXPIRED";
  }
  return instantMs(delegation.valid_from) > nowMs ? "NOT_STARTED" : "ACTIVE";
}

/** The pages of the bulk grid: Waiting for me with the view's chips; a decision refreshes them. */
export function bulkGridKey(filters: ApprovalListFilters): QueryKey {
  return queryKey("approvals", "tenant", {
    view: "waiting",
    layout: "bulk",
    subject_type: filters.subjectType,
    entity: filters.entity.join(","),
  });
}

/** The item of the bulk command for a request: the hashes the approver reviewed (REQ-PLT-014). */
export function bulkItem(approval: Approval): BulkApproveItem {
  return {
    approval_request_id: approval.id,
    subject_content_sha256: approval.subject.content_sha256,
    ...(approval.impact_preview === null
      ? {}
      : { impact_preview_sha256: approval.impact_preview.sha256 }),
  };
}
