// Audit events, chain verifications and the on-demand verification (04 §15.3 API-R-10 rev 1.154,
// T-PLT-19, T-PLT-23; API-R-12 `GET /files/{id}/content`; SCREENS_B §6.3, §6.4; BUILD_SPEC RPS-21; item
// AUD-SCREEN-BIND-1). `GET /audit-events` admits `object_type`, `actor_id`, `action`, `outcome` (any of
// the outcomes sent), `contract_id` (every event that names the contract, whatever its object type),
// `chain_seq` (the event of that sequence), `from` (inclusive) and `to` (exclusive), and sorts by
// `chain_seq` (default, newest first), `occurred_at` or `id`; it has no search. The table is partitioned
// by month: a read of the log carries a time bound (the API starts 30 days back when none is sent), while
// the trail of a contract and one event by its sequence are read whole. `GET /audit-events/actors` answers
// who acted in a range, the options of the actor filter; `GET /audit-events/verifications/{id}` one
// verification. An event carries the business label of its object (`object_label`) and the membership
// of the person who acted (`actor_membership_id`); the object filter finds a contract's id through the
// contract search.
import type { Access } from "../../access";
import { send } from "../client";
import { fetchListPage, type ListPage, listSearch } from "../lists";
import { readProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type AuditEvent = components["schemas"]["AuditEventOut"];
export type AuditOutcome = components["schemas"]["AuditOutcome"];
export type AuditVerification = components["schemas"]["AuditChainVerificationOut"];

export const AUDIT_EVENTS_PATH = "/api/v1/audit-events";
export const AUDIT_VERIFICATIONS_PATH = "/api/v1/audit-events/verifications";
export const AUDIT_VERIFY_PATH = "/api/v1/audit-events/verify";
export const AUDIT_READ_PERMISSION = "audit.read";
/** SCREENS RT-37 SF-09:audit-log and RT-38 SF-09:verification. */
export const AUDIT_LOG_ROUTE = "/reports/audit-log";
export const VERIFICATION_ROUTE = "/reports/audit-log/verifications/:verificationId";
/** SCREENS_B RPT-43 and RPT-44. */
export const AUDIT_LOG_EXPORT_CODE = "audit_log_export";
export const VERIFICATION_REPORT_CODE = "chain_verification_report";
/** The audit object type of a contract (04 T-PLT-19 `object_type`, the table name). */
export const CONTRACT_OBJECT = "contract";
export const AUDIT_ACTORS_PATH = "/api/v1/audit-events/actors";
export const RECENT_VERIFICATIONS = 10;
const CONTRACTS_PATH = "/api/v1/contracts";
/** The contract search reads at most this many matches; an exact id is among the first. */
const CONTRACT_MATCHES = 50;

/** Invalidates every audit event read and every verification read. */
export const EVERY_AUDIT_EVENT: QueryKey = queryKey("audit-events", "tenant");
export const EVERY_VERIFICATION: QueryKey = queryKey("audit-verifications", "tenant");

/** SCREENS SCR-URL-12 `drawer=event` and its companion parameter SCR-URL-32 `event` (rev 1.20). */
export const AUDIT_EVENT_DRAWER = "event";
export const AUDIT_EVENT_PARAM = "event";

/**
 * SF-09:audit-log with the event drawer open on one event. The link names the event by its chain
 * sequence: unique in the workspace, immutable, the first column of the grid and what a verification
 * cites (`first_failure_seq`); no index of the audit table leads with the event's id.
 */
export function auditEventRoute(chainSeq: number): string {
  return `${AUDIT_LOG_ROUTE}?drawer=${AUDIT_EVENT_DRAWER}&${AUDIT_EVENT_PARAM}=${String(chainSeq)}`;
}

export function verificationRoute(verificationId: string): string {
  return `${AUDIT_LOG_ROUTE}/verifications/${verificationId}`;
}

export interface AuditEventQuery {
  readonly objectTypes: readonly string[];
  /** The contract whose trail is read: every event that names it, whatever its object type. */
  readonly contractId: string | null;
  readonly actorId: string | null;
  readonly action: string | null;
  /** E-81 literals; none reads every outcome. */
  readonly outcomes: readonly string[];
  /** The first instant of the range, inclusive (RFC 3339 UTC); null where the read takes none. */
  readonly from: string | null;
  /** The end of the range, exclusive (RFC 3339 UTC); null where the read takes none. */
  readonly to: string | null;
}

export function auditEventsKey(query: AuditEventQuery): QueryKey {
  return queryKey("audit-events", "tenant", {
    view: "log",
    objectTypes: query.objectTypes.join(","),
    contractId: query.contractId,
    actorId: query.actorId,
    action: query.action,
    outcomes: query.outcomes.join(","),
    from: query.from,
    to: query.to,
  });
}

/** One page of `GET /audit-events`; without a URL sort the API's `-chain_seq` applies. */
export function fetchAuditEventsPage(
  query: AuditEventQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<AuditEvent>> {
  return fetchListPage<AuditEvent>(
    AUDIT_EVENTS_PATH,
    {
      object_type: query.objectTypes.length === 0 ? null : query.objectTypes,
      contract_id: query.contractId,
      actor_id: query.actorId,
      action: query.action,
      outcome: query.outcomes.length === 0 ? null : query.outcomes,
      from: query.from,
      to: query.to,
      sort,
    },
    cursor,
  );
}

export function auditEventKey(chainSeq: number): QueryKey {
  return queryKey("audit-events", "tenant", { view: "event", chainSeq });
}

/**
 * `GET /audit-events?chain_seq=<n>`: the event of that chain sequence, at any age and whatever the
 * filters of the list; null when the workspace holds none.
 */
export async function fetchAuditEvent(chainSeq: number): Promise<AuditEvent | null> {
  const page = await fetchListPage<AuditEvent>(
    AUDIT_EVENTS_PATH,
    { chain_seq: String(chainSeq) },
    null,
    { limit: 1, count: false },
  );
  return page.items[0] ?? null;
}

export type AuditActor = components["schemas"]["ActorOut"];

export interface AuditActors {
  readonly items: readonly AuditActor[];
  /** True when the range holds more than the API answers (100). */
  readonly truncated: boolean;
}

export function auditActorsKey(from: string | null, to: string | null): QueryKey {
  return queryKey("audit-events", "tenant", { view: "actors", from, to });
}

/**
 * `GET /audit-events/actors`: the users, operators and API clients the events of a range name as
 * their actor, by name, at most 100. Without `from` and `to` the API reads the last 30 days.
 */
export async function fetchAuditActors(
  from: string | null,
  to: string | null,
): Promise<AuditActors> {
  const response = await send("GET", `${AUDIT_ACTORS_PATH}${listSearch({ from, to })}`);
  if (!response.ok) {
    throw await readProblem(response);
  }
  const body = (await response.json()) as components["schemas"]["AuditActorsOut"];
  return { items: body.items, truncated: body.is_truncated };
}

export function latestVerificationKey(): QueryKey {
  return queryKey("audit-verifications", "tenant", { view: "latest" });
}

/** `GET /audit-events/verifications?limit=1`: the verification that finished last, or null. */
export async function fetchLatestVerification(): Promise<AuditVerification | null> {
  const page = await fetchListPage<AuditVerification>(AUDIT_VERIFICATIONS_PATH, {}, null, {
    limit: 1,
    count: false,
  });
  return page.items[0] ?? null;
}

export function recentVerificationsKey(): QueryKey {
  return queryKey("audit-verifications", "tenant", { view: "recent" });
}

/** SCREENS_B §6.4 "Recent verifications": the ten that finished last. */
export async function fetchRecentVerifications(): Promise<readonly AuditVerification[]> {
  const page = await fetchListPage<AuditVerification>(AUDIT_VERIFICATIONS_PATH, {}, null, {
    limit: RECENT_VERIFICATIONS,
    count: false,
  });
  return page.items;
}

export function verificationKey(verificationId: string): QueryKey {
  return queryKey("audit-verifications", "tenant", { id: verificationId });
}

/**
 * SCREENS_B §6.4: `GET /audit-events/verifications/{id}`, one verification of the workspace; null for
 * an id the workspace does not hold (404; SCR-ST-07). The router shows its own not-found page for a
 * path value that is not an id (SCREENS §0.4), so only an id is read.
 */
export async function fetchVerification(verificationId: string): Promise<AuditVerification | null> {
  const response = await send(
    "GET",
    `${AUDIT_VERIFICATIONS_PATH}/${encodeURIComponent(verificationId)}`,
  );
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw await readProblem(response);
  }
  return (await response.json()) as AuditVerification;
}

/** API-R-12: the digest file of a verification that passed, downloaded as an attachment. */
export function digestHref(fileId: string): string {
  return `/api/v1/files/${fileId}/content`;
}

async function readJson(path: string): Promise<Readonly<Record<string, unknown>>> {
  const response = await send("GET", path);
  if (!response.ok) {
    throw await readProblem(response);
  }
  return (await response.json()) as Readonly<Record<string, unknown>>;
}

interface ObjectScreen {
  /** The record's screen (SCREENS §0.4), which opens from the id alone. */
  readonly route: (id: string) => string;
  /** The route pattern of that screen; the link needs it built (BUILD_SPEC XR-14). */
  readonly pattern: string;
  /** The read permission of the route; null where the API decides per record. */
  readonly permission: string | null;
}

/** The audit object types whose record has a screen that opens from the id the event carries. */
const OBJECT_SCREENS: Readonly<Record<string, ObjectScreen>> = {
  [CONTRACT_OBJECT]: {
    route: (id) => `/contracts/${id}`,
    pattern: "/contracts/:contractId",
    permission: "contract.read",
  },
  approval_request: {
    route: (id) => `/approvals/requests/${id}`,
    pattern: "/approvals/requests/:requestId",
    permission: null,
  },
  import_upload: {
    route: (id) => `/data/imports/${id}`,
    pattern: "/data/imports/:importId",
    permission: "contract.read",
  },
  journal_run: {
    route: (id) => `/journals/runs/${id}`,
    pattern: "/journals/runs/:runId",
    permission: "contract.read",
  },
  // SF-08:run: the report routes admit a holder of `audit.read` and decide per run (API-R-41).
  report_run: {
    route: (id) => `/reports/runs/${id}`,
    pattern: "/reports/runs/:runId",
    permission: null,
  },
};

/**
 * The object types whose label is a name a person gave — a member, a user, an API client, a review
 * campaign, a calculator run, a mapping version (04 §16.14 "Object label") — and not an identifier:
 * the audit log shows these in the text face and every other label in the identifier face (DS-FMT-23).
 */
const NAMED_OBJECTS: ReadonlySet<string> = new Set([
  "tenant_membership",
  "app_user",
  "api_client",
  "access_review_campaign",
  "ssp_calculator_run",
  "account_mapping_version",
]);

export function isNamedObject(objectType: string): boolean {
  return NAMED_OBJECTS.has(objectType);
}

/**
 * The screen of an event's object, where its type has one that opens from the id, the route is built
 * and the user holds its read permission; else null. The link shows the label the event carries
 * (`object_label`); no record is read for one here.
 */
export function objectRoute(
  objectType: string,
  objectId: string | null,
  built: ReadonlySet<string>,
  access: Access,
): string | null {
  const screen = OBJECT_SCREENS[objectType];
  if (
    objectId === null ||
    screen === undefined ||
    !built.has(screen.pattern) ||
    (screen.permission !== null && !access.holdsAnywhere(screen.permission))
  ) {
    return null;
  }
  return screen.route(objectId);
}

export function contractObjectKey(businessId: string): QueryKey {
  return queryKey("audit-object", "tenant", { lookup: "contract", businessId });
}

/**
 * SCREENS_B §6.3 object filter: the id of the contract whose external id or contract number is
 * `businessId`, through the contract search (`GET /contracts?q=`); null when no contract has it.
 */
export async function fetchContractObjectId(businessId: string): Promise<string | null> {
  const wanted = businessId.trim().toLocaleLowerCase();
  const body = await readJson(
    `${CONTRACTS_PATH}${listSearch({ q: businessId.trim(), limit: CONTRACT_MATCHES })}`,
  );
  const items = Array.isArray(body.items) ? (body.items as readonly unknown[]) : [];
  for (const item of items) {
    if (typeof item !== "object" || item === null) {
      continue;
    }
    const {
      id,
      external_id: externalId,
      contract_no: contractNo,
    } = item as Readonly<Record<string, unknown>>;
    const names = [externalId, contractNo].filter(
      (name): name is string => typeof name === "string",
    );
    if (typeof id === "string" && names.some((name) => name.toLocaleLowerCase() === wanted)) {
      return id;
    }
  }
  return null;
}
