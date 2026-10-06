// Approval requests (04 API-R-09, §16.10 API-S-Approval; SCREENS §15.3 to §15.6; PRD SM-01, BR-PLT-06).
// The three inbox views bind `GET /approvals` with their SCREENS §15.3 filters and order; the "Waiting
// for me" tab count reads the same filters with `count=true`. A request is `GET /approvals/{id}`, and
// approve, reject and withdraw are commands that invalidate every approval read. The generic field diff
// reads the request's stored impact preview document `{before, after}` (REQ-PLT-015) through
// `GET /files/{id}/content`; a document the caller cannot read gives no diff (L3-3-Q-22).
import { useQuery } from "@tanstack/react-query";

import type { Access } from "../../access";
import { api, send, unwrap } from "../client";
import { useCommand } from "../commands";
import { fetchListPage, type ListPage, type ListQuery } from "../lists";
import { minorUnitOf, registerCurrencies } from "../../format";
import { ApiProblem, readProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type Approval = components["schemas"]["ApprovalOut"];
export type ApprovalStep = components["schemas"]["ApprovalStepOut"];
export type ApprovalDecision = components["schemas"]["ApprovalDecisionOut"];
export type ApprovalSubjectType = components["schemas"]["ApprovalSubjectType"];
export type ApprovalStatus = components["schemas"]["ApprovalRequestStatus"];
export type ApprovalApproveIn = components["schemas"]["ApprovalApproveIn"];
export type ApprovalRejectIn = components["schemas"]["ApprovalRejectIn"];
export type ApprovalWithdrawIn = components["schemas"]["ApprovalWithdrawIn"];

export const APPROVALS_PATH = "/api/v1/approvals";
export const FILE_CONTENT_PATH = "/api/v1/files";

/** 03 REQ-POL-007, the rule of PRD ERR-75: the effective date of a version that replaces a published one. */
export const EFFECTIVE_DATE_RULE = "REQ-POL-007";

/**
 * PRD ERR-75 at the decision (04 §16.5; SCREENS §15.4 Problems, rev 1.31): the effective date of a
 * version that replaces a published one has been reached, so its request cannot be approved any more
 * and stays pending. The server's sentence asks for another date, which an approver cannot give.
 */
export function effectiveDateReached(problem: {
  readonly errors?: readonly { readonly rule_id?: string | null }[] | null;
}): boolean {
  return (problem.errors ?? []).some((error) => error.rule_id === EFFECTIVE_DATE_RULE);
}

/** SCREENS §15.3 master list views. */
export type ApprovalView = "waiting" | "submitted" | "all";
export const APPROVAL_VIEWS: readonly ApprovalView[] = ["waiting", "submitted", "all"];

/** SCREENS §0.4 RT-54 to RT-56. */
export const VIEW_ROUTES: Readonly<Record<ApprovalView, string>> = {
  waiting: "/approvals",
  submitted: "/approvals/submitted",
  all: "/approvals/all",
};

/** RT-57 `/approvals/requests/:requestId`; `view` names the containing view (SCREENS §15.1). */
export function requestRoute(requestId: string, view?: ApprovalView): string {
  const path = `/approvals/requests/${requestId}`;
  return view === undefined ? path : `${path}?view=${view}`;
}

export function isApprovalView(value: string | null | undefined): value is ApprovalView {
  return value === "waiting" || value === "submitted" || value === "all";
}

/**
 * SCREENS §15.3 FilterBar (BUILD_SPEC WEB-16): the chips a view adds to its binding. API-R-09 takes one
 * `subject_type`, one `status` and any number of `entity` codes; a request without an entity matches an
 * entity only through its subject.
 */
export interface ApprovalListFilters {
  readonly subjectType: ApprovalSubjectType | null;
  readonly entity: readonly string[];
  /** All requests only: the other two views fix or leave out the status. */
  readonly status: ApprovalStatus | null;
}

export const NO_APPROVAL_FILTERS: ApprovalListFilters = {
  subjectType: null,
  entity: [],
  status: null,
};

/** The SCREENS §15.3 binding of a view: its fixed filters, the chips and its order. */
export function viewQuery(
  view: ApprovalView,
  filters: ApprovalListFilters = NO_APPROVAL_FILTERS,
): ListQuery {
  switch (view) {
    case "waiting":
      return {
        assigned_to_me: true,
        status: "PENDING",
        subject_type: filters.subjectType,
        entity: filters.entity,
        sort: "submitted_at",
      };
    case "submitted":
      return {
        preparer: "me",
        subject_type: filters.subjectType,
        entity: filters.entity,
        sort: "-submitted_at",
      };
    case "all":
      return {
        status: filters.status,
        subject_type: filters.subjectType,
        entity: filters.entity,
        sort: "-submitted_at",
      };
  }
}

/** Rows per page, and the pages a view reads: at most 1,000 requests (L3-3-Q-25). */
export const LIST_PAGE_SIZE = 200;
export const LIST_MAX_PAGES = 5;

/** 04 E-08 in catalogue order; labels are `approvals.subjectType.<literal>` (SCREENS §15.3). */
export const SUBJECT_TYPES: readonly ApprovalSubjectType[] = [
  "SSP_BOOK_VERSION",
  "SSP_OVERRIDE",
  "CONTRACT_ACTIVATION",
  "MODIFICATION",
  "MANUAL_EVENT",
  "ESTIMATE_VERSION",
  "MANUAL_ADJUSTMENT",
  "REGISTRY_VERSION",
  "RULE_SET_VERSION",
  "POB_TEMPLATE_VERSION",
  "ACCOUNT_MAPPING_VERSION",
  "FX_RATE_SET_VERSION",
  "ROLE_CHANGE",
  "ROLE_ASSIGNMENT",
  "SOD_EXCEPTION",
  "PERIOD_LOCK",
  "PERIOD_REOPEN",
  "IMPORT_COMMIT",
  "CONTRACT_VOID",
  "COMBINATION_GROUP",
  "JUDGEMENT_RECORD",
  "JOURNAL_RUN",
  "SUPPORT_GRANT",
  "AI_PROPOSAL_ACCEPTANCE",
  "PRINCIPAL_AGENT_CHANGE",
  "ATTRIBUTE_CHANGE",
  "EXCEPTION_WAIVER",
  "MIGRATION_PROMOTION",
  "MAPPING_PROFILE_VERSION",
  "POLICY_OVERRIDE",
  "MIGRATION_SSP_REPLAY",
  "EVIDENCE_SHRED",
];

/**
 * 04 T-PLT-11 permissions with `is_approval` (PRD §5.6 catalogue). SCREENS §15.6: a member holding none
 * sees "You have no approval permissions" on Waiting for me.
 */
export const APPROVAL_PERMISSIONS: ReadonlySet<string> = new Set([
  "contract.approve",
  "modification.approve",
  "event.approve",
  "estimate.approve",
  "judgement.review",
  "ssp.approve",
  "adjustment.approve",
  "config.approve",
  "import.approve",
  "journal.approve",
  "period.lock",
  "period.reopen_approve",
  "recon.signoff",
  "exception.waive",
  "access.approve",
  "support_grant.approve",
  "migration.approve",
]);

/** The member holds an approval permission for some entity (SCREENS §0.6 SCR-PERM-02 (b)). */
export function holdsApprovalPermission(access: Access): boolean {
  return [...APPROVAL_PERMISSIONS].some((code) => access.holdsAnywhere(code));
}

const EVERY_APPROVAL = queryKey("approvals", "tenant");

export function approvalListKey(
  view: ApprovalView,
  filters: ApprovalListFilters = NO_APPROVAL_FILTERS,
): QueryKey {
  return queryKey("approvals", "tenant", {
    view,
    subject_type: filters.subjectType,
    entity: filters.entity.join(","),
    status: filters.status,
  });
}

export function waitingCountKey(): QueryKey {
  return queryKey("approvals", "tenant", { count: "waiting" });
}

export function approvalKey(requestId: string): QueryKey {
  return queryKey("approvals", "tenant", { id: requestId });
}

export function previewKey(fileId: string): QueryKey {
  return queryKey("files", "tenant", { id: fileId, content: "impact-preview" });
}

export const CURRENCIES_PATH = "/api/v1/currencies";
type CurrencyOut = components["schemas"]["CurrencyOut"];

/** True when the format module holds the currency's minor unit (DS-FMT-03). */
export function currencyRegistered(code: string): boolean {
  try {
    minorUnitOf(code);
    return true;
  } catch {
    return false;
  }
}

/**
 * Registers the minor units of `codes` from `GET /currencies` (DS-FMT-03, DS-I18N-09). A caller without
 * `config.read` gets none, and such amounts are not shown (L3-3-Q-26). The one registration helper of
 * the query modules; journal-runs re-exports it.
 */
export async function ensureCurrencyCodes(codes: Iterable<string>): Promise<void> {
  const missing = [...new Set(codes)].filter((code) => code !== "" && !currencyRegistered(code));
  if (missing.length === 0) {
    return;
  }
  try {
    const page = await fetchListPage<CurrencyOut>(CURRENCIES_PATH, { code: missing }, null, {
      limit: 200,
      count: false,
    });
    registerCurrencies(page.items);
  } catch (error) {
    if (!(error instanceof ApiProblem && error.status === 403)) {
      throw error;
    }
  }
}

/**
 * The currencies of the amounts a request itself states (DS-FMT-03): its amount and, for the activation
 * of a contract behind the not-a-contract gate, the catch-up of each book and its total (SCREENS §15.4
 * region 4).
 */
export async function ensureCurrencies(approvals: readonly Approval[]): Promise<void> {
  await ensureCurrencyCodes(
    approvals.flatMap((approval) => {
      const summary = approval.impact_preview?.summary ?? null;
      return [
        approval.amount,
        summary?.catch_up_total ?? null,
        ...(summary?.criteria_met ?? []).map((book) => book.catch_up_total),
      ].flatMap((money) => (money === null ? [] : [money.currency]));
    }),
  );
}

/** Every request of a view and its chips, page by page, up to `LIST_MAX_PAGES` pages. */
export async function fetchApprovals(
  view: ApprovalView,
  filters: ApprovalListFilters = NO_APPROVAL_FILTERS,
): Promise<readonly Approval[]> {
  const items: Approval[] = [];
  let cursor: string | null = null;
  for (let page = 0; page < LIST_MAX_PAGES; page += 1) {
    const result: ListPage<Approval> = await fetchListPage<Approval>(
      APPROVALS_PATH,
      viewQuery(view, filters),
      cursor,
      { limit: LIST_PAGE_SIZE, count: false },
    );
    items.push(...result.items);
    cursor = result.nextCursor;
    if (cursor === null) {
      break;
    }
  }
  await ensureCurrencies(items);
  return items;
}

export function useApprovalList(
  view: ApprovalView,
  enabled = true,
  filters: ApprovalListFilters = NO_APPROVAL_FILTERS,
) {
  return useQuery({
    queryKey: approvalListKey(view, filters),
    queryFn: () => fetchApprovals(view, filters),
    enabled,
  });
}

/** The "Waiting for me <n>" count: `X-Erev-Total-Count` of the Waiting for me binding. */
export async function fetchWaitingCount(): Promise<number> {
  const page = await fetchListPage<Approval>(APPROVALS_PATH, viewQuery("waiting"), null, {
    limit: 1,
    count: true,
  });
  return page.total?.count ?? page.items.length;
}

export function useWaitingCount(enabled = true) {
  return useQuery({ queryKey: waitingCountKey(), queryFn: fetchWaitingCount, enabled });
}

export function fetchApproval(requestId: string): Promise<Approval> {
  return unwrap(
    api.GET("/api/v1/approvals/{approval_request_id}", {
      params: { path: { approval_request_id: requestId } },
    }),
  );
}

export function useApproval(requestId: string) {
  return useQuery({
    queryKey: approvalKey(requestId),
    queryFn: async () => {
      const approval = await fetchApproval(requestId);
      // The request view formats these amounts as soon as it renders; the list registers them too,
      // but a request opened from a link has no list before it.
      await ensureCurrencies([approval]);
      return approval;
    },
    retry: false,
  });
}

/** The stored impact preview snapshot (04 §16.10 `impact_preview.file_id`; REQ-PLT-015). */
export interface PreviewDocument {
  readonly before: Readonly<Record<string, unknown>>;
  readonly after: Readonly<Record<string, unknown>>;
}

export function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isPreviewDocument(value: unknown): value is PreviewDocument {
  return isRecord(value) && isRecord(value.before) && isRecord(value.after);
}

const DECIMAL = /^-?\d+(?:\.\d+)?$/;
const CURRENCY_CODE = /^[A-Z]{3}$/;

/** API-S-Money (API-C-06): exactly `amount`, a decimal string, and `currency`, an ISO 4217 code. */
export function isMoney(
  value: unknown,
): value is { readonly amount: string; readonly currency: string } {
  return (
    isRecord(value) &&
    Object.keys(value).length === 2 &&
    typeof value.amount === "string" &&
    typeof value.currency === "string" &&
    DECIMAL.test(value.amount) &&
    CURRENCY_CODE.test(value.currency)
  );
}

/** The currencies of every API-S-Money member of a preview document member, at any depth. */
export function previewCurrencies(value: unknown): string[] {
  if (Array.isArray(value)) {
    const items: readonly unknown[] = value;
    return items.flatMap((item) => previewCurrencies(item));
  }
  if (isMoney(value)) {
    return [value.currency];
  }
  return isRecord(value) ? Object.values(value).flatMap((item) => previewCurrencies(item)) : [];
}

/** The preview document, or null when the caller cannot read the file or it holds no document. */
export async function fetchPreviewDocument(fileId: string): Promise<PreviewDocument | null> {
  const response = await send("GET", `${FILE_CONTENT_PATH}/${fileId}/content`);
  if (response.status === 404 || response.status === 403) {
    return null;
  }
  if (!response.ok) {
    throw await readProblem(response);
  }
  const body: unknown = await response.json();
  if (!isPreviewDocument(body)) {
    return null;
  }
  // D-90a QA-L9-5a: the generic field diff formats the document's amounts (DS-FMT-03).
  await ensureCurrencyCodes([...previewCurrencies(body.before), ...previewCurrencies(body.after)]);
  return body;
}

export function usePreviewDocument(fileId: string | null) {
  return useQuery({
    queryKey: previewKey(fileId ?? ""),
    queryFn: () => fetchPreviewDocument(fileId ?? ""),
    enabled: fileId !== null,
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });
}

export type ApprovalAction = "approve" | "reject" | "withdraw";

/** `POST /approvals/{id}/<action>`; a success refreshes every approval read. */
export function useApprovalCommand(requestId: string, action: ApprovalAction) {
  return useCommand<Approval>({
    method: "POST",
    path: `${APPROVALS_PATH}/${requestId}/${action}`,
    invalidates: [EVERY_APPROVAL],
  });
}

export { EVERY_APPROVAL };
