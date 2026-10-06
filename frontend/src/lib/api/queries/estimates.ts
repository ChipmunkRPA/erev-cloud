// Estimates and estimate versions (04 API-R-32 `GET, POST /contracts/{id}/estimates`,
// `GET, POST /estimates/{id}/versions`, `GET, PATCH /estimate-versions/{id}`,
// `POST /estimate-versions/{id}/preview`, `/submit`, `/withdraw`; §16.14 estimates; T-CON-12, T-CON-13,
// E-09, E-10, E-12; SCREENS §8; BUILD_SPEC CTR-25). The element list answers the summaries of the
// current and the latest version without their figures, so the screens read the versions of each
// element. No estimate command takes `If-Match`: a version answers `row_version` and the last write
// stands. The preview is a 202 `CONTRACT_COMPUTE` job whose `result.summary` is API-S-ImpactSummary;
// nothing of it is stored on the version. The dry run a version is submitted with is kept with its
// approval request (REQ-PLT-015; API-S-Approval `impact_preview`).
import { fetchListPage, type ListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { type Approval, ensureCurrencyCodes, EVERY_APPROVAL, fetchApproval } from "./approvals";
import {
  type Attachment,
  ATTACHMENTS_PATH,
  contractPathOf,
  type Judgement,
  JUDGEMENTS_PATH,
  readJson,
} from "./contracts";
import { type ExceptionItem, EXCEPTIONS_PATH } from "./exceptions";
import { EVERY_MODIFICATION } from "./modifications";

/** T-CON-12: an estimated element of a contract with the summaries of two of its versions. */
export type Estimate = components["schemas"]["EstimateOut"];
/** T-CON-13 with the 04 §16.14 additions (`excluded_amount`, `costs_incurred_to_date`, `progress_ratio`). */
export type EstimateVersion = components["schemas"]["EstimateVersionOut"];
export type EstimateVersionSummary = components["schemas"]["EstimateVersionSummaryOut"];
/** E-09. */
export type EstimateKind = components["schemas"]["EstimateKind"];
/** E-10. */
export type EstimateMethod = components["schemas"]["EstimateMethod"];
/** E-12 of a version. */
export type EstimateStatus = components["schemas"]["ConfigStatus"];
export type EstimateCreateBody = components["schemas"]["EstimateCreateIn"];
export type EstimateVersionCreateBody = components["schemas"]["EstimateVersionCreateIn"];
export type EstimateVersionUpdateBody = components["schemas"]["EstimateVersionUpdateIn"];
export type EstimateVersionSubmitBody = components["schemas"]["EstimateVersionSubmitIn"];
export type EstimateVersionWithdrawBody = components["schemas"]["EstimateVersionWithdrawIn"];
export type EstimateScenario = components["schemas"]["ScenarioIn"];
export type EstimateTarget = Estimate["allocation_target"];
export type VcElementType = NonNullable<EstimateCreateBody["vc_element_type"]>;
/** The 202 job of `POST /estimate-versions/{id}/preview`. */
export type EstimatePreviewJob = components["schemas"]["JobOut"];
/** API-S-ImpactSummary: `result.summary` of a succeeded preview job. */
export type EstimateImpact = components["schemas"]["ImpactSummaryOut"];

/** T-PLT-11: preparing estimates (SCREENS §8.1; ACT-11). */
export const ESTIMATE_CREATE_PERMISSION = "estimate.create";
/** SCREENS RT-13 SF-03:estimate; RT-12 is the workbench's `ESTIMATES_ROUTE`. */
export const ESTIMATE_ROUTE = "/contracts/:contractId/estimates/:estimateId";
export const ESTIMATES_PATH = "/api/v1/estimates";
export const ESTIMATE_VERSIONS_PATH = "/api/v1/estimate-versions";
/** T-PLT-30 and T-CON-19 subject type of a version's attachments and judgement records. */
export const ESTIMATE_VERSION_SUBJECT = "estimate_version";
/** 04 table 15.4: an open element without a version or attestation effective at period end (POL-042). */
export const REASSESSMENT_MISSING = "VC_REASSESSMENT_MISSING";
/** PRD IMP-71 and IMP-74; 04 §15.2 ERR-13. */
export const ESTIMATE_METHOD_LOCKED = "ESTIMATE_METHOD_LOCKED";
/**
 * PRD IMP-138 and IMP-140, findings of a submission (04 §16.14 rev 1.241): the first names no field,
 * the second `judgement_record_id`, which no form holds. The drawer places both by their rule id.
 */
export const ESTIMATE_EVIDENCE_REQUIRED = "ESTIMATE_EVIDENCE_REQUIRED";
export const ESTIMATE_CONSTRAINT_RECORD = "ESTIMATE_CONSTRAINT_RECORD";
export const EAC_BELOW_COSTS = "eac-below-costs-incurred";

/** E-09 in the order of SCREENS §8.4; the kind SCREENS does not list comes last. */
export const ESTIMATE_KINDS: readonly EstimateKind[] = [
  "VARIABLE_CONSIDERATION",
  "RETURN_RATE",
  "BREAKAGE",
  "EAC",
  "EXERCISE_LIKELIHOOD",
  "IMPLICIT_PRICE_CONCESSION",
  "RENEWAL_EXPECTATION",
  "ROYALTY_ACCRUAL",
  "EXPECTED_PURCHASES",
  "SHARE_BASED_CONSIDERATION",
];
/** E-10 in the order of SCREENS §8.4. */
export const ESTIMATE_METHODS: readonly EstimateMethod[] = [
  "EXPECTED_VALUE",
  "MOST_LIKELY_AMOUNT",
  "ENTERED_AMOUNT",
  "RATE",
  "COST_BUILDUP",
];
/** T-CON-12 `vc_element_type` in the order of SCREENS §8.4. */
export const VC_ELEMENT_TYPES: readonly VcElementType[] = [
  "BONUS",
  "PENALTY",
  "PERFORMANCE_INCENTIVE",
  "REBATE",
  "VOLUME_TIER",
  "PRICE_PROTECTION",
  "SLA_CREDIT",
  "DISCOUNT",
  "RETURN",
  "REFUND",
  "IMPLICIT_PRICE_CONCESSION",
  "CLAIM",
  "UNPRICED_CHANGE_ORDER",
  "USAGE",
  "ROYALTY",
  "MILESTONE",
];
export const ESTIMATE_TARGETS: readonly EstimateTarget[] = [
  "CONTRACT",
  "OBLIGATIONS",
  "INCREMENTS",
];
/** E-12 statuses of a version that can be edited: a PATCH returns the last two to DRAFT. */
export const EDITABLE_STATUSES: ReadonlySet<EstimateStatus> = new Set([
  "DRAFT",
  "REJECTED",
  "WITHDRAWN",
]);

export function contractEstimatesPath(contractId: string): string {
  return `${contractPathOf(contractId)}/estimates`;
}

export function estimateVersionsPath(estimateId: string): string {
  return `${ESTIMATES_PATH}/${estimateId}/versions`;
}

export function estimateVersionPath(versionId: string): string {
  return `${ESTIMATE_VERSIONS_PATH}/${versionId}`;
}

export function estimatesRoute(contractId: string): string {
  return `/contracts/${contractId}/estimates`;
}

export function estimateRoute(contractId: string, estimateId: string): string {
  return `/contracts/${contractId}/estimates/${estimateId}`;
}

export function contractEstimatesKey(contractId: string): QueryKey {
  return queryKey("contract-estimates", "tenant", { contractId });
}

export function estimateCountKey(contractId: string): QueryKey {
  return queryKey("contract-estimates", "tenant", { contractId, view: "count" });
}

export function estimateVersionsKey(estimateId: string): QueryKey {
  return queryKey("estimate-versions", "tenant", { estimateId });
}

/** One version by its id; refreshed with the versions of its element (`ESTIMATE_RECORD_KEYS`). */
export function estimateVersionKey(versionId: string): QueryKey {
  return queryKey("estimate-versions", "tenant", { versionId });
}

export function versionAttachmentsKey(versionId: string): QueryKey {
  return queryKey("attachments", "tenant", {
    subject_type: ESTIMATE_VERSION_SUBJECT,
    subject_id: versionId,
  });
}

export function versionJudgementsKey(versionId: string): QueryKey {
  return queryKey("estimate-judgements", "tenant", { versionId });
}

/**
 * The judgement record a version names (`judgement_record_id`), read by its id whatever its subject.
 * A key of the estimate judgements: every estimate command reads it again (`ESTIMATE_RECORD_KEYS`).
 */
export function judgementKey(judgementId: string): QueryKey {
  return queryKey("estimate-judgements", "tenant", { judgementId });
}

export function reassessmentKey(contractId: string): QueryKey {
  return queryKey("exceptions", "tenant", { contract: contractId, code: REASSESSMENT_MISSING });
}

/**
 * The request of a version as read for one status of that version: a version that leaves SUBMITTED
 * reads its request again, so the pane never judges a returned version by the request as it was
 * while pending. The key is one of the approval's (`approvalKey(requestId)` matches it).
 */
export function versionRequestKey(requestId: string, versionStatus: string): QueryKey {
  return queryKey("approvals", "tenant", { id: requestId, versionStatus });
}

/**
 * The approval request of a version, with the currency of the catch-up of its stored preview known to
 * the formatter (DS-FMT-03).
 */
export async function fetchVersionRequest(requestId: string): Promise<Approval> {
  const approval = await fetchApproval(requestId);
  const catchUp = approval.impact_preview?.summary.catch_up_total ?? null;
  if (catchUp !== null) {
    await ensureCurrencyCodes([catchUp.currency]);
  }
  return approval;
}

/**
 * Every read an estimate command can change: the elements, their versions, evidence and requests —
 * and the modification rows, each of which lists the versions created inside it with their status
 * (04 §16.14 rev 1.210 `linked_estimate_versions`), wherever the command on such a version is sent.
 */
export const ESTIMATE_RECORD_KEYS: readonly QueryKey[] = [
  queryKey("contract-estimates", "tenant"),
  queryKey("estimate-versions", "tenant"),
  queryKey("estimate-judgements", "tenant"),
  queryKey("attachments", "tenant"),
  EVERY_APPROVAL,
  EVERY_MODIFICATION,
];

async function fetchAll<T>(path: string, query: Readonly<Record<string, string>>): Promise<T[]> {
  const items: T[] = [];
  let cursor: string | null = null;
  do {
    const page: ListPage<T> = await fetchListPage<T>(path, query, cursor, { count: false });
    items.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor !== null);
  return items;
}

/** The estimated elements of a contract in element-code order. */
export function fetchEstimates(contractId: string): Promise<readonly Estimate[]> {
  return fetchAll<Estimate>(contractEstimatesPath(contractId), { sort: "element_code" });
}

/** The "Estimates <n>" tab count (SCREENS §8.2: `count=true&limit=1`). */
export async function fetchEstimateCount(contractId: string): Promise<number | null> {
  const page = await fetchListPage<Estimate>(contractEstimatesPath(contractId), {}, null, {
    limit: 1,
    count: true,
  });
  return page.total?.count ?? null;
}

/** Every version of an element, newest first, with the currencies of their figures registered. */
export async function fetchEstimateVersions(
  estimateId: string,
): Promise<readonly EstimateVersion[]> {
  const items = await fetchAll<EstimateVersion>(estimateVersionsPath(estimateId), {
    sort: "-version_no",
  });
  await ensureCurrencyCodes(
    items.flatMap((item) => (item.currency === null ? [] : [item.currency])),
  );
  return items;
}

/** One version (`GET /estimate-versions/{id}`), with the currency of its figures registered. */
export async function fetchEstimateVersion(versionId: string): Promise<EstimateVersion> {
  const { data } = await readJson<EstimateVersion>(estimateVersionPath(versionId));
  await ensureCurrencyCodes(data.currency === null ? [] : [data.currency]);
  return data;
}

/** The live attachments of a version, newest first (SCREENS §8.6 Evidence). */
export async function fetchVersionAttachments(versionId: string): Promise<readonly Attachment[]> {
  const items = await fetchAll<Attachment>(ATTACHMENTS_PATH, {
    subject_type: ESTIMATE_VERSION_SUBJECT,
    subject_id: versionId,
  });
  return items.filter((item) => item.voided_at === null);
}

/** The judgement records whose subject is the version, newest first (REQ-TP-003). */
export async function fetchVersionJudgements(versionId: string): Promise<readonly Judgement[]> {
  const page = await fetchListPage<Judgement>(
    JUDGEMENTS_PATH,
    { subject_type: ESTIMATE_VERSION_SUBJECT, subject_id: versionId },
    null,
    { limit: 200, count: false },
  );
  return page.items;
}

/** One judgement record (04 API-R-33 `GET /judgements/{id}`). */
export async function fetchJudgement(judgementId: string): Promise<Judgement> {
  const { data } = await readJson<Judgement>(`${JUDGEMENTS_PATH}/${judgementId}`);
  return data;
}

/** The open `VC_REASSESSMENT_MISSING` items of a contract (SCREENS §8.6 Exceptions; IMP-72). */
export async function fetchReassessmentDue(contractId: string): Promise<readonly ExceptionItem[]> {
  const page = await fetchListPage<ExceptionItem>(
    EXCEPTIONS_PATH,
    { contract: contractId, code: REASSESSMENT_MISSING, status: "OPEN" },
    null,
    { limit: 200, count: false },
  );
  return page.items;
}

/**
 * The approved version in force and the latest version of an element's versions (newest first). A
 * discarded version (E-12 `VOIDED`) keeps its number and is not the latest one: "latest" is the
 * highest version number that is not `VOIDED`, as the API's `latest_version` reads it (04 §16.14 rev
 * 1.210, item EST-DISCARD-1).
 */
export function currentAndLatest(versions: readonly EstimateVersion[]): {
  readonly current: EstimateVersion | null;
  readonly latest: EstimateVersion | null;
} {
  return {
    current: versions.find((item) => item.status === "APPROVED") ?? null,
    latest: versions.find((item) => item.status !== "VOIDED") ?? null,
  };
}

/**
 * The open version of an element — the one that is `DRAFT` and the one that is `SUBMITTED` — whichever
 * its number (04 §16.14 rev 1.241, PRD ERR-93: at most one version of an element is open, and a
 * rejected or withdrawn version below the latest can be returned to draft). Of several, a state kept
 * from before that rule, the newest.
 */
export function openVersions(versions: readonly EstimateVersion[]): {
  readonly draft: EstimateVersion | null;
  readonly pending: EstimateVersion | null;
} {
  return {
    draft: versions.find((item) => item.status === "DRAFT") ?? null,
    pending: versions.find((item) => item.status === "SUBMITTED") ?? null,
  };
}
