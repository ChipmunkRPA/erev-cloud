// Contracts list (04 API-R-28 `GET /contracts`, `POST /contracts/{id}/submit-activation`,
// `POST /contracts/{id}/apply-hold`; E-111 quick lists, E-17, E-38; API-R-19 `GET /customers`; SCREENS
// §3.4 to §3.7; BUILD_SPEC CTR-21). The SF-02 grid reads pages of 200 contracts with its filters and the
// context `book` and `as_of` (BR-UX-02). The bulk actions command each contract one at a time with its
// own `Idempotency-Key` and `If-Match: "s<head_stream_version>"` (OQ-S-16), at most 200 per action.
import { registerCurrencies } from "../../format";
import { send } from "../client";
import type { CommandKeys } from "../commands";
import { fetchListPage, type ListPage, type ListQuery, listSearch } from "../lists";
import { ApiProblem, isRefused, readProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { currencyRegistered, CURRENCIES_PATH } from "./approvals";

export type ContractListItem = components["schemas"]["ContractListItemOut"];
export type ContractStatus = components["schemas"]["ContractStatus"];
export type ContractQuickList = components["schemas"]["ContractQuickList"];
export type ContractSourceSystem = components["schemas"]["SourceSystem"];
export type HoldType = components["schemas"]["HoldType"];
export type Customer = components["schemas"]["CustomerOut"];

export const CONTRACTS_PATH = "/api/v1/contracts";
export const CUSTOMERS_PATH = "/api/v1/customers";
/** API-R-28: reads need `contract.read`; drafts, activation and holds `contract.create`. */
export const CONTRACT_READ_PERMISSION = "contract.read";
export const CONTRACT_CREATE_PERMISSION = "contract.create";
/** SCREENS §3.7: at most 200 contracts per bulk action. */
export const BULK_LIMIT = 200;
/** SCREENS §3.4: the default view's sort. */
export const DEFAULT_CONTRACT_SORT = "-updated_at";
const CUSTOMER_PAGE_LIMIT = 500;

export interface QuickListSpec {
  readonly literal: ContractQuickList;
  /** The message key suffix of the label, `contracts.list.quick.<key>`. */
  readonly key: string;
  /** SCREENS §3.4 default sort; none keeps the server order. */
  readonly sort?: string;
}

/** SCREENS §3.4 quick lists in the order of the saved-view selector (E-111). */
export const QUICK_LISTS: readonly QuickListSpec[] = [
  { literal: "RECENTLY_VIEWED", key: "recentlyViewed" },
  { literal: "ON_HOLD", key: "onHold", sort: DEFAULT_CONTRACT_SORT },
  { literal: "LARGEST_VALUE", key: "largestValue", sort: "-transaction_price" },
  { literal: "MODIFIED_THIS_PERIOD", key: "modifiedThisPeriod", sort: DEFAULT_CONTRACT_SORT },
  { literal: "CREATED_MANUALLY", key: "createdManually", sort: DEFAULT_CONTRACT_SORT },
  {
    literal: "CREATED_FROM_INTEGRATIONS_THIS_PERIOD",
    key: "createdFromIntegrations",
    sort: DEFAULT_CONTRACT_SORT,
  },
];

export function quickList(literal: string | null): QuickListSpec | undefined {
  return QUICK_LISTS.find((item) => item.literal === literal);
}

/** E-17 literals in the Status filter order. */
export const CONTRACT_STATUSES: readonly ContractStatus[] = [
  "DRAFT",
  "PENDING_REVIEW",
  "ACTIVE",
  "COMPLETED",
  "TERMINATED",
  "VOIDED",
  "NOT_A_CONTRACT",
];

/** The API parameters of one grid state (SCREENS §3.4, §3.6). */
export interface ContractListQuery {
  readonly entity: readonly string[];
  readonly customer: string | null;
  readonly status: readonly string[];
  readonly onHold: boolean | null;
  readonly modifiedInPeriod: string | null;
  readonly valueMin: string | null;
  readonly valueMax: string | null;
  readonly hasExceptions: boolean | null;
  readonly quickList: ContractQuickList | null;
  readonly q: string | null;
  readonly book: string | null;
  readonly asOf: string | null;
}

export const EMPTY_CONTRACT_QUERY: ContractListQuery = {
  entity: [],
  customer: null,
  status: [],
  onHold: null,
  modifiedInPeriod: null,
  valueMin: null,
  valueMax: null,
  hasExceptions: null,
  quickList: null,
  q: null,
  book: null,
  asOf: null,
};

/** The `GET /contracts` search parameters; arrays repeat their parameter. */
export function contractListParams(query: ContractListQuery): ListQuery {
  return {
    entity: query.entity.length === 0 ? undefined : query.entity,
    customer: query.customer,
    status: query.status.length === 0 ? undefined : query.status,
    on_hold: query.onHold,
    modified_in_period: query.modifiedInPeriod,
    value_min: query.valueMin,
    value_max: query.valueMax,
    has_exceptions: query.hasExceptions,
    quick_list: query.quickList,
    q: query.q === "" ? null : query.q,
    book: query.book,
    as_of: query.asOf,
  };
}

export function contractsKey(query: ContractListQuery): QueryKey {
  return queryKey("contracts", "tenant", {
    entity: query.entity.join(","),
    customer: query.customer,
    status: query.status.join(","),
    on_hold: query.onHold,
    modified_in_period: query.modifiedInPeriod,
    value_min: query.valueMin,
    value_max: query.valueMax,
    has_exceptions: query.hasExceptions,
    quick_list: query.quickList,
    q: query.q,
    book: query.book,
    as_of: query.asOf,
  });
}

const EVERY_CONTRACT_LIST = queryKey("contracts", "tenant");

/** Registers the minor units of the page's currencies (DS-FMT-03); without `config.read` none. */
async function ensureCurrencies(items: readonly ContractListItem[]): Promise<void> {
  const codes = [
    ...new Set(
      items.flatMap((item) => [
        item.transaction_currency,
        ...(item.kpis === null ? [] : [item.kpis.transaction_price.currency]),
      ]),
    ),
  ].filter((code) => !currencyRegistered(code));
  if (codes.length === 0) {
    return;
  }
  try {
    const page = await fetchListPage<components["schemas"]["CurrencyOut"]>(
      CURRENCIES_PATH,
      { code: codes },
      null,
      { limit: CUSTOMER_PAGE_LIMIT, count: false },
    );
    registerCurrencies(page.items);
  } catch (error) {
    if (!(error instanceof ApiProblem && error.status === 403)) {
      throw error;
    }
  }
}

/** One page of `GET /contracts`; without a URL sort the quick list's or the default sort applies. */
export async function fetchContractsPage(
  query: ContractListQuery,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<ContractListItem>> {
  const fallback =
    query.quickList === null ? DEFAULT_CONTRACT_SORT : quickList(query.quickList)?.sort;
  const page = await fetchListPage<ContractListItem>(
    CONTRACTS_PATH,
    { ...contractListParams(query), sort: sort ?? fallback },
    cursor,
  );
  await ensureCurrencies(page.items);
  return page;
}

export function customersKey(): QueryKey {
  return queryKey("customers", "tenant", { purpose: "filter" });
}

/** Every customer in scope, in code order, for the Customer filter (SCREENS §3.6). */
export async function fetchCustomers(): Promise<readonly Customer[]> {
  const customers: Customer[] = [];
  let cursor: string | null = null;
  do {
    const page: ListPage<Customer> = await fetchListPage<Customer>(CUSTOMERS_PATH, {}, cursor, {
      limit: CUSTOMER_PAGE_LIMIT,
      count: false,
    });
    customers.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor !== null);
  return customers;
}

/** API-C-08: a contract's `If-Match` is `"s<head_stream_version>"`. */
export function contractIfMatch(headStreamVersion: number): string {
  return `"s${String(headStreamVersion)}"`;
}

export interface BulkFailure {
  readonly contract: ContractListItem;
  /** The problem title, or the skip reason. */
  readonly problem: string;
  /** Checklist items of `activation-checklist-failed` (ERR-31) and field messages. */
  readonly detail: readonly string[];
}

export interface BulkResult {
  readonly total: number;
  readonly succeeded: number;
  readonly failures: readonly BulkFailure[];
}

export type BulkAction =
  | { readonly kind: "submit-activation" }
  | { readonly kind: "apply-hold"; readonly holdType: HoldType; readonly reason: string };

function actionPath(action: BulkAction, contract: ContractListItem): string {
  return `${CONTRACTS_PATH}/${contract.id}/${action.kind}`;
}

function actionBody(action: BulkAction): unknown {
  return action.kind === "submit-activation"
    ? {}
    : { hold_type: action.holdType, reason: action.reason };
}

/**
 * Commands each contract in turn (SCREENS §3.7): its own Idempotency-Key and If-Match, no automatic
 * retry and no optimistic update. `skip` names a contract the action does not apply to. The key of a
 * contract's command comes from `keys` (DG-FE-05 rev 1.156): a command whose response was lost goes
 * out under the same key when the action is run again.
 */
export async function commandContracts(
  keys: CommandKeys,
  action: BulkAction,
  contracts: readonly ContractListItem[],
  skip: (contract: ContractListItem) => string | null,
  onProgress: (done: number, total: number) => void,
  notReached: string,
): Promise<BulkResult> {
  const chosen = contracts.slice(0, BULK_LIMIT);
  const failures: BulkFailure[] = [];
  let succeeded = 0;
  for (const [index, contract] of chosen.entries()) {
    const reason = skip(contract);
    if (reason !== null) {
      failures.push({ contract, problem: reason, detail: [] });
    } else {
      try {
        const response = await keys.send("POST", actionPath(action, contract), {
          body: actionBody(action),
          headers: { "If-Match": contractIfMatch(contract.head_stream_version) },
        });
        if (response.ok) {
          succeeded += 1;
        } else {
          const problem = await readProblem(response);
          failures.push({
            contract,
            problem: problem.title,
            detail: problem.errors.map((error) => error.message),
          });
        }
      } catch {
        failures.push({ contract, problem: notReached, detail: [] });
      }
    }
    onProgress(index + 1, chosen.length);
  }
  return { total: chosen.length, succeeded, failures };
}

/** The keys a bulk action refreshes: every contract list. */
export const CONTRACT_LIST_KEYS: readonly QueryKey[] = [EVERY_CONTRACT_LIST];

// --- SF-03 contract workbench (04 API-R-28 detail reads, API-R-11 jobs, API-R-12 attachments, API-R-15
// approvals, API-R-49 explain; SCREENS §4.1.7; BUILD_SPEC CTR-22). Reads pass the context `book`,
// `as_of` and `known_at` (BR-UX-02, SCR-URL-23); commands keep `If-Match: "s<head_stream_version>"`.

export type Contract = components["schemas"]["ContractOut"];
export type ContractStepState = components["schemas"]["ContractStepState"];
export type AllocationWalk = components["schemas"]["AllocationWalkOut"];
export type AllocationLine = components["schemas"]["AllocationLineOut"];
export type ContractVersion = components["schemas"]["ContractVersionOut"];
export type Judgement = components["schemas"]["JudgementOut"];
export type CombinationSuggestion = components["schemas"]["CombinationSuggestionOut"];
export type Attachment = components["schemas"]["AttachmentOut"];
export type ContractJob = components["schemas"]["JobOut"];
export type ApprovalItem = components["schemas"]["ApprovalOut"];

export const JUDGEMENTS_PATH = "/api/v1/judgements";
export const ATTACHMENTS_PATH = "/api/v1/attachments";
export const JOBS_PATH = "/api/v1/jobs";
export const APPROVALS_LIST_PATH = "/api/v1/approvals";
export const COMBINATION_SUGGESTIONS_PATH = "/api/v1/combination-suggestions";
export const COMBINATION_GROUPS_PATH = "/api/v1/combination-groups";
export const POLICY_OVERRIDES_PATH = "/api/v1/policy-overrides";
/** 04 §16.1: the header naming the routed CONTRACT_ACTIVATION request. */
export const APPROVAL_REQUEST_HEADER = "X-Erev-Approval-Request";
/** 04 §15.2 slug of a refused activation (ERR-31). */
export const ACTIVATION_CHECKLIST_FAILED = "activation-checklist-failed";
/** T-PLT-11 permission codes of the workbench commands (SCREENS §4.1.6, §5.1). */
export const EVENT_RECORD_PERMISSION = "event.record";
export const JUDGEMENT_CREATE_PERMISSION = "judgement.create";
export const ADJUSTMENT_CREATE_PERMISSION = "adjustment.create";
/** SCREENS §4.8: attachments are listed a page at a time. */
const DOCUMENTS_LIMIT = 200;
const APPROVAL_PAGES = 5;

/** The read context of a record screen (SCREENS §0.5 SCR-URL-02, SCR-URL-03, SCR-URL-05). */
export interface RecordContext {
  readonly book: string | null;
  /** The end date of the context period for the context entity. */
  readonly asOf: string | null;
  readonly knownAt: string | null;
}

export function recordParams(context: RecordContext): ListQuery {
  return { book: context.book, as_of: context.asOf, known_at: context.knownAt };
}

function contextParams(context: RecordContext): Readonly<Record<string, string | null>> {
  return { book: context.book, as_of: context.asOf, known_at: context.knownAt };
}

/** One JSON read of an untyped path; throws the `ApiProblem` of a refusal. */
export async function readJson<T>(
  path: string,
  query: ListQuery = {},
): Promise<{ readonly data: T; readonly response: Response }> {
  const response = await send("GET", `${path}${listSearch(query)}`);
  if (!response.ok) {
    throw await readProblem(response);
  }
  return { data: (await response.json()) as T, response };
}

export function contractPathOf(contractId: string): string {
  return `${CONTRACTS_PATH}/${contractId}`;
}

export function contractKey(contractId: string, context: RecordContext): QueryKey {
  return queryKey("contract", "tenant", { contractId, ...contextParams(context) });
}

/** API-S-Contract at the version in context, with its currency registered (DS-FMT-03). */
export async function fetchContract(contractId: string, context: RecordContext): Promise<Contract> {
  const { data } = await readJson<Contract>(contractPathOf(contractId), recordParams(context));
  await registerCodes([data.transaction_currency]);
  return data;
}

export function allocationKey(contractId: string, context: RecordContext): QueryKey {
  return queryKey("contract-allocation", "tenant", { contractId, ...contextParams(context) });
}

/** API-S-AllocationWalk (REQ-ALC-009); 404 while no version exists. */
export async function fetchAllocationWalk(
  contractId: string,
  context: RecordContext,
): Promise<AllocationWalk> {
  return (
    await readJson<AllocationWalk>(
      `${contractPathOf(contractId)}/allocation`,
      recordParams(context),
    )
  ).data;
}

export function contractVersionKey(
  contractId: string,
  versionNo: number,
  book: string | null,
): QueryKey {
  return queryKey("contract-version", "tenant", { contractId, versionNo, book });
}

/** API-S-ContractVersion: the Step 3 `transaction_price_buildup`. */
export async function fetchContractVersion(
  contractId: string,
  versionNo: number,
  book: string | null,
): Promise<ContractVersion> {
  return (
    await readJson<ContractVersion>(`${contractPathOf(contractId)}/versions/${String(versionNo)}`, {
      book,
    })
  ).data;
}

async function everyPage<T>(path: string, query: ListQuery, pages = APPROVAL_PAGES): Promise<T[]> {
  const items: T[] = [];
  let cursor: string | null = null;
  let read = 0;
  do {
    const page: ListPage<T> = await fetchListPage<T>(path, query, cursor, {
      limit: DOCUMENTS_LIMIT,
      count: false,
    });
    items.push(...page.items);
    cursor = page.nextCursor;
    read += 1;
  } while (cursor !== null && read < pages);
  return items;
}

export function contractJudgementsKey(contractId: string): QueryKey {
  return queryKey("contract-judgements", "tenant", { contractId });
}

/** The judgement records whose subject is the contract (Step 1 evidence, SCREENS §4.1.7). */
export function fetchContractJudgements(contractId: string): Promise<readonly Judgement[]> {
  return everyPage<Judgement>(JUDGEMENTS_PATH, {
    subject_type: "contract",
    subject_id: contractId,
  });
}

/**
 * One of the contract's judgement reads: a command that refreshes `CONTRACT_RECORD_KEYS` reads it
 * again with the records whose subject is the contract.
 */
export function contractUnreviewedJudgementsKey(contractId: string): QueryKey {
  return queryKey("contract-judgements", "tenant", { contractId, unreviewed: true });
}

/**
 * E-57 statuses the activation checklist counts (04 table 15.4-I `JUDGEMENT_RECORDS`): a draft, a
 * record that waits for review, and a rejected one.
 */
const UNREVIEWED_STATUSES: readonly string[] = ["DRAFT", "SUBMITTED", "REJECTED"];

/**
 * The judgement records of the contract that fail its activation checklist, whatever their subject —
 * the contract, one of its obligations, an estimate version (04 T-CON-19 `contract_id`): the rejected
 * ones, which the checklist names by number (PRD IMP-145; SCREENS §4.9.8 rev 1.74), and the drafts
 * and the records that wait for review, which it names by topic alone (PRD IMP-104; rev 1.76). The
 * list route filters no contract, so the workspace's records in the three statuses are read and
 * kept by `contract_id`.
 */
export async function fetchUnreviewedJudgements(contractId: string): Promise<readonly Judgement[]> {
  const items = await everyPage<Judgement>(JUDGEMENTS_PATH, { status: UNREVIEWED_STATUSES });
  return items.filter((item) => item.contract_id === contractId);
}

export type PolicyOverride = components["schemas"]["PolicyOverrideOut"];

export function contractOverridesKey(contractId: string): QueryKey {
  return queryKey("contract-policy-overrides", "tenant", { contractId });
}

/**
 * The policy overrides of the contract, of every status (04 API-R-13 `GET /policy-overrides`, filter
 * `contract`; T-CON-23 `judgement_record_id`): each names the judgement record it rests on. Read with
 * `config.read`.
 */
export function fetchContractOverrides(contractId: string): Promise<readonly PolicyOverride[]> {
  return everyPage<PolicyOverride>(POLICY_OVERRIDES_PATH, { contract: contractId });
}

/** E-12 statuses of an override that is in force or waits for approval. */
const STANDING_OVERRIDE: ReadonlySet<string> = new Set(["SUBMITTED", "APPROVED"]);

/**
 * The ids of the judgement records that an override in force or waiting for approval names (SCREENS
 * §4.9.8, rev 1.76). The override's approval certifies the record's id and nothing of its state, so
 * such a record is not discarded on a screen: the override would keep naming a record that can
 * never be reviewed. An override that was rejected, withdrawn, superseded or never submitted names
 * a record that is free again.
 */
export function recordsOfStandingOverrides(
  overrides: readonly Pick<PolicyOverride, "status" | "judgement_record_id">[],
): ReadonlySet<string> {
  return new Set(
    overrides.flatMap((item) =>
      STANDING_OVERRIDE.has(item.status) && item.judgement_record_id !== null
        ? [item.judgement_record_id]
        : [],
    ),
  );
}

/**
 * The ids of the events that an `EVENT_VOIDED` of `events` names. A voided event counts for nothing,
 * and no member of API-S-Event marks it: the void is another event of the stream (04 §16.3).
 */
export function voidedEventIds(events: readonly ContractEvent[]): ReadonlySet<string> {
  const ids = new Set<string>();
  for (const event of events) {
    if (event.event_type === "EVENT_VOIDED" && event.supersedes_event_id !== null) {
      ids.add(event.supersedes_event_id);
    }
  }
  return ids;
}

export function contractAssessmentsKey(contractId: string): QueryKey {
  return queryKey("contract-assessments", "tenant", { contractId });
}

/**
 * The `COLLECTIBILITY_ASSESSED` events of the contract (Step 1 path, SCREENS §4.1.3 rev 1.11; 04
 * §16.3): with the judgement records they say whether a reviewed record still waits for its assessment.
 * The `EVENT_VOIDED` events are read with them (rev 1.72; ruling R-102 (c)): `replace-draft` voids the
 * assessments of the draft it replaces, and the route lists a voided assessment like any other.
 */
export function fetchContractAssessments(contractId: string): Promise<readonly ContractEvent[]> {
  return everyPage<ContractEvent>(`${contractPathOf(contractId)}/events`, {
    event_type: ["COLLECTIBILITY_ASSESSED", "EVENT_VOIDED"],
  });
}

export function distinctReviewsKey(contractId: string): QueryKey {
  return queryKey("contract-distinct-reviews", "tenant", { contractId });
}

/**
 * The `POB_DISTINCT_OVERRIDE` records of the contract's obligations (Step 2 "Distinct review"). The list
 * route filters one subject id, so the topic's obligation records are read and kept by `contract_id`.
 */
export async function fetchDistinctReviews(contractId: string): Promise<readonly Judgement[]> {
  const items = await everyPage<Judgement>(JUDGEMENTS_PATH, {
    topic: ["POB_DISTINCT_OVERRIDE"],
    subject_type: "obligation",
  });
  return items.filter((item) => item.contract_id === contractId);
}

export function contractOptionsKey(): QueryKey {
  return queryKey("contracts", "tenant", { view: "options" });
}

/**
 * The contracts a filter offers by external id: the first 200 in contract-number order, value the
 * contract id (SCREENS_B §3.3 rev 1.39; the exceptions screen reads the same list for its own field).
 */
export async function fetchContractOptions(): Promise<
  readonly { readonly value: string; readonly label: string }[]
> {
  const page = await fetchListPage<{ readonly id: string; readonly external_id: string }>(
    CONTRACTS_PATH,
    { sort: "contract_no" },
    null,
    { limit: 200, count: false },
  );
  return page.items.map((item) => ({ value: item.id, label: item.external_id }));
}

export function combinationSuggestionsKey(contractId: string): QueryKey {
  return queryKey("combination-suggestions", "tenant", { contractId });
}

/** Open `COMBINATION_SUGGESTED` items naming the contract (04 §16.14). */
export function fetchCombinationSuggestions(
  contractId: string,
): Promise<readonly CombinationSuggestion[]> {
  return everyPage<CombinationSuggestion>(
    COMBINATION_SUGGESTIONS_PATH,
    { contract: contractId },
    1,
  );
}

export function documentsKey(contractId: string): QueryKey {
  return queryKey("contract-documents", "tenant", { contractId });
}

/** The attachments of the contract, newest first (SCREENS §4.8), with the total count. */
export async function fetchDocuments(contractId: string): Promise<ListPage<Attachment>> {
  return fetchListPage<Attachment>(
    ATTACHMENTS_PATH,
    { subject_type: "contract", subject_id: contractId },
    null,
    { limit: DOCUMENTS_LIMIT, count: true },
  );
}

export function computeJobsKey(contractId: string): QueryKey {
  return queryKey("contract-jobs", "tenant", { contractId });
}

/**
 * Queued or running `CONTRACT_COMPUTE` jobs of the contract (SCR-ST-08); none when the API refuses
 * the read of the jobs (SCREENS §0.6 SCR-PERM-02).
 */
export async function fetchComputeJobs(contractId: string): Promise<readonly ContractJob[]> {
  try {
    const page = await fetchListPage<ContractJob>(
      JOBS_PATH,
      {
        kind: ["CONTRACT_COMPUTE"],
        state: ["QUEUED", "RUNNING"],
        subject_type: "contract",
        subject_id: contractId,
      },
      null,
      { limit: 10, count: false },
    );
    return page.items;
  } catch (error) {
    if (isRefused(error)) {
      return [];
    }
    throw error;
  }
}

export function pendingActivationKey(contractId: string): QueryKey {
  return queryKey("contract-pending-activation", "tenant", { contractId });
}

/**
 * The PENDING `CONTRACT_ACTIVATION` request of the contract (banner priority 3, SCREENS §4.1.5). The
 * approvals list has no subject filter, so the pending activations are read and matched by subject id.
 */
export async function fetchPendingActivation(contractId: string): Promise<ApprovalItem | null> {
  try {
    const items = await everyPage<ApprovalItem>(APPROVALS_LIST_PATH, {
      status: ["PENDING"],
      subject_type: ["CONTRACT_ACTIVATION"],
    });
    return items.find((item) => item.subject.id === contractId) ?? null;
  } catch (error) {
    if (error instanceof ApiProblem && error.status === 403) {
      return null;
    }
    throw error;
  }
}

/** The figure of `GET /explain/{object_type}/{id}/{measure}` (API-R-49). */
export interface ExplainFigure {
  readonly objectType: string;
  readonly id: string;
  readonly measure: string;
  readonly periodKey?: string | undefined;
  readonly book?: string | undefined;
}

/** API-S-Explain of one figure (SCREENS §6.3 binding). */
export async function fetchExplanation(figure: ExplainFigure): Promise<unknown> {
  const path = `/api/v1/explain/${figure.objectType}/${figure.id}/${figure.measure}`;
  const data = (
    await readJson<unknown>(path, { period: figure.periodKey, book: figure.book, depth: 6 })
  ).data;
  // A panel opened from the URL renders before the contract query registers its currency, so the
  // explanation registers the currencies of its own nodes first (DS-FMT-03; fail closed otherwise).
  const nodes = (data as { nodes?: readonly { currency?: string | null }[] }).nodes ?? [];
  await registerCodes(
    nodes.flatMap((node) => (typeof node.currency === "string" ? [node.currency] : [])),
  );
  return data;
}

/** Registers the minor units of currencies not yet known; without `config.read` none. */
async function registerCodes(codes: readonly string[]): Promise<void> {
  const missing = [...new Set(codes)].filter((code) => !currencyRegistered(code));
  if (missing.length === 0) {
    return;
  }
  try {
    const page = await fetchListPage<components["schemas"]["CurrencyOut"]>(
      CURRENCIES_PATH,
      { code: missing },
      null,
      { limit: CUSTOMER_PAGE_LIMIT, count: false },
    );
    registerCurrencies(page.items);
  } catch (error) {
    if (!(error instanceof ApiProblem && error.status === 403)) {
      throw error;
    }
  }
}

export type CommandResult<T> =
  | { readonly ok: true; readonly data: T; readonly response: Response }
  | { readonly ok: false; readonly problem: ApiProblem };

async function keyed<T>(
  keys: CommandKeys,
  keep: boolean,
  method: "POST" | "PATCH" | "DELETE",
  path: string,
  body: unknown,
  ifMatch: string | undefined,
): Promise<CommandResult<T>> {
  const response = await keys.send(method, path, {
    body,
    keep,
    ...(ifMatch === undefined ? {} : { headers: { "If-Match": ifMatch } }),
  });
  if (!response.ok) {
    return { ok: false, problem: await readProblem(response) };
  }
  const text = response.status === 204 ? "" : await response.text();
  return { ok: true, data: (text === "" ? null : JSON.parse(text)) as T, response };
}

/**
 * One command outside `useCommand`, or the last step of a sequence, with an optional `If-Match`; no
 * retry and no optimistic update (DG-FE-05). Its Idempotency-Key is the key `keys` holds for the
 * step — method, path and body — so a second press after a lost response sends the same key; a
 * success or a problem the API keeps ends it. A network failure rejects. The caller refreshes
 * `CONTRACT_RECORD_KEYS` afterwards.
 */
export function sendCommand<T>(
  keys: CommandKeys,
  method: "POST" | "PATCH" | "DELETE",
  path: string,
  body: unknown,
  ifMatch?: string,
): Promise<CommandResult<T>> {
  return keyed<T>(keys, false, method, path, body, ifMatch);
}

/**
 * A step of a sequence that one press sends (SCREENS §4.9.1, §4.9.7: a record created, then submitted
 * or appended): as `sendCommand`, but the step keeps its key after it succeeded, until the sequence
 * completes and calls `keys.clear()`. When a later step fails, the second press sends this step
 * again under its key, the API replays the answer it stored — the same record — and the sequence
 * continues at the step that failed (DG-FE-05 rev 1.156; item W-23).
 */
export function sendStep<T>(
  keys: CommandKeys,
  method: "POST" | "PATCH" | "DELETE",
  path: string,
  body: unknown,
  ifMatch?: string,
): Promise<CommandResult<T>> {
  return keyed<T>(keys, true, method, path, body, ifMatch);
}

// --- SF-03:billing (04 API-R-28 `GET /contracts/{id}/balances`, API-R-30 `GET /contracts/{id}/events`;
// SCREENS §4.4; BUILD_SPEC CTR-23). The balances per entity at the version in context; the invoices and
// credit memos of the stream recorded by `known_at`.

export type ContractBalance = components["schemas"]["ContractBalanceOut"];
export type ContractEvent = components["schemas"]["EventOut"];

/** E-03 literals of the "Invoices and credit memos" grid. */
export const BILLING_EVENT_TYPES = ["BILLING_RECORDED", "CREDIT_MEMO_RECORDED"] as const;
/**
 * [J] L5-4-Q-49: API-R-30 sorts by `stream_version`, `effective_date`, `recorded_at` or `id`, not by
 * `payload.issue_date`, so "Issue date, default descending" reads `-effective_date`.
 */
export const DEFAULT_BILLING_EVENT_SORT = "-effective_date";

export function contractBalancesKey(contractId: string, context: RecordContext): QueryKey {
  return queryKey("contract-balances", "tenant", { contractId, ...contextParams(context) });
}

/** API-S-ContractBalance per entity at the version in context (one page), currencies registered. */
export async function fetchContractBalances(
  contractId: string,
  context: RecordContext,
): Promise<readonly ContractBalance[]> {
  const { data } = await readJson<{ readonly items: readonly ContractBalance[] }>(
    `${contractPathOf(contractId)}/balances`,
    recordParams(context),
  );
  await registerCodes(data.items.map((item) => item.contract_liability.currency));
  return data.items;
}

export function billingEventsKey(contractId: string, knownAt: string | null): QueryKey {
  return queryKey("contract-billing-events", "tenant", { contractId, known_at: knownAt });
}

/** One page of the contract's `BILLING_RECORDED` and `CREDIT_MEMO_RECORDED` events. */
export function fetchBillingEventsPage(
  contractId: string,
  knownAt: string | null,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<ContractEvent>> {
  return fetchListPage<ContractEvent>(
    `${contractPathOf(contractId)}/events`,
    {
      event_type: [...BILLING_EVENT_TYPES],
      known_at: knownAt,
      sort: sort ?? DEFAULT_BILLING_EVENT_SORT,
    },
    cursor,
  );
}

/** Every read of the workbench and the contract lists: a command on the record refreshes them all. */
export const CONTRACT_RECORD_KEYS: readonly QueryKey[] = [
  EVERY_CONTRACT_LIST,
  queryKey("contract", "tenant"),
  queryKey("contract-obligations", "tenant"),
  queryKey("contract-allocation", "tenant"),
  queryKey("contract-version", "tenant"),
  queryKey("contract-judgements", "tenant"),
  queryKey("contract-assessments", "tenant"),
  queryKey("contract-distinct-reviews", "tenant"),
  queryKey("combination-suggestions", "tenant"),
  queryKey("contract-documents", "tenant"),
  queryKey("contract-jobs", "tenant"),
  queryKey("contract-pending-activation", "tenant"),
  queryKey("obligation", "tenant"),
  queryKey("obligation-schedule", "tenant"),
  queryKey("obligation-events", "tenant"),
  queryKey("contract-balances", "tenant"),
  queryKey("contract-billing-events", "tenant"),
  queryKey("schedule-lines", "tenant"),
  queryKey("subledger-lines", "tenant"),
  queryKey("contract-versions", "tenant"),
  queryKey("contract-version-compare", "tenant"),
  queryKey("contract-history", "tenant"),
  queryKey("contract-audit-events", "tenant"),
  queryKey("contract-modifications", "tenant"),
];

// --- SF-03:new, SF-03:edit and SF-03:history (04 API-R-28 `POST /contracts`, `POST
// /contracts/{id}/replace-draft`, `GET /contracts/{id}/versions`, `/versions/compare`, `/history`; API-R-30
// `GET /contracts/{id}/events`; API-R-10 `GET /audit-events`, `/audit-events/verifications`; §16.14
// API-S-ContractHistoryItem; SCREENS §4.7, §4.10; BUILD_SPEC CTR-24).

export type ContractCreateBody = components["schemas"]["ContractCreateIn"];
export type ContractVersionSummary = components["schemas"]["ContractVersionSummaryOut"];
export type VersionCompare = components["schemas"]["VersionCompareOut"];
export type VersionChange = components["schemas"]["VersionChangeOut"];
export type ContractHistoryItem = components["schemas"]["ContractHistoryItemOut"];
export type HistoryItemKind = components["schemas"]["HistoryItemKind"];
export type AuditEvent = components["schemas"]["AuditEventOut"];
export type AuditChainVerification = components["schemas"]["AuditChainVerificationOut"];
type Product = components["schemas"]["ProductOut"];

export const AUDIT_EVENTS_PATH = "/api/v1/audit-events";
export const PRODUCTS_PATH = "/api/v1/products";
/** T-PLT-11: the audit trail slice of a record needs `audit.read` (SCREENS §4.7). */
export const AUDIT_READ_PERMISSION = "audit.read";
/** SCREENS §4.7 "Load older activity": one page of the timeline. */
export const HISTORY_PAGE_SIZE = 50;
/** The audit `object_type` of a contract (T-PLT-19). */
const CONTRACT_OBJECT_TYPE = "contract";

export function replaceDraftPath(contractId: string): string {
  return `${contractPathOf(contractId)}/replace-draft`;
}

export function submitActivationPath(contractId: string): string {
  return `${contractPathOf(contractId)}/submit-activation`;
}

export function productChoicesKey(): QueryKey {
  return queryKey("products", "tenant", { view: "active" });
}

/** Every active product in code order, for the Product cells of the draft lines (SCREENS §4.10). */
export async function fetchProductChoices(): Promise<readonly Product[]> {
  const products: Product[] = [];
  let cursor: string | null = null;
  do {
    const page: ListPage<Product> = await fetchListPage<Product>(
      PRODUCTS_PATH,
      { is_active: true, sort: "code" },
      cursor,
      { limit: CUSTOMER_PAGE_LIMIT, count: false },
    );
    products.push(...page.items);
    cursor = page.nextCursor;
  } while (cursor !== null);
  return products;
}

/**
 * What SF-03:edit may do with a draft (SCREENS §4.10; rulings R-93 (a), R-102 (c)). No read answers a
 * draft as it stands (item CTR-DRAFT-READ-1), so the form opens only while the latest booking still is
 * the draft.
 */
export type DraftEdit =
  | {
      readonly kind: "open";
      /** The latest `CONTRACT_BOOKED` that no `EVENT_VOIDED` names: the body `replace-draft` replaces. */
      readonly booking: ContractEvent;
      /** The stream version the guard read; `replace-draft` takes it as `If-Match`, not a later read. */
      readonly head: number;
      /**
       * A `COLLECTIBILITY_ASSESSED` that no `EVENT_VOIDED` names is on the stream: `replace-draft` voids
       * it with the booking (ruling R-102 (c)), and the form says so before the save.
       */
      readonly assessed: boolean;
    }
  /** An event that may change the draft followed the booking, or the stream was not read to its start. */
  | { readonly kind: "changed" };

/**
 * E-03 literals that leave every member of the booking as it was booked: a hold applied or released,
 * and a Step 1 assessment, which states the outcome of a judgement record and no term of the contract.
 */
const DRAFT_KEEPING_EVENTS: ReadonlySet<ContractEvent["event_type"]> = new Set([
  "HOLD_APPLIED",
  "HOLD_RELEASED",
  "COLLECTIBILITY_ASSESSED",
]);
/** The events of a draft are read whole, up to this many pages of `DOCUMENTS_LIMIT`. */
const DRAFT_STREAM_PAGES = 5;

/**
 * The guard over the events of a draft's stream; `complete` is false when the read stopped before the
 * first event. Fail-closed: the form opens only when every event after the latest booking is a hold
 * applied or released, a Step 1 assessment or the void of one. `MEMO_UPDATED`,
 * `LINE_ATTRIBUTES_CHANGED` and `REGROUPED` change members the booking payload still states as booked.
 * An assessment does not close the form (rev 1.72; ruling R-102 (c)): the API takes the edit whatever
 * assessments the stream holds and voids those that stand, so the guard says whether one does.
 */
export function draftEditOf(events: readonly ContractEvent[], complete: boolean): DraftEdit {
  const newestFirst = [...events].sort((a, b) => b.stream_version - a.stream_version);
  const voided = voidedEventIds(newestFirst);
  const index = newestFirst.findIndex(
    (event) => event.event_type === "CONTRACT_BOOKED" && !voided.has(event.id),
  );
  const booking = newestFirst[index];
  const newest = newestFirst[0];
  if (!complete || booking === undefined || newest === undefined) {
    return { kind: "changed" };
  }
  const assessments = newestFirst.filter((event) => event.event_type === "COLLECTIBILITY_ASSESSED");
  const assessmentIds = new Set(assessments.map((event) => event.id));
  const keepsDraft = (event: ContractEvent) =>
    DRAFT_KEEPING_EVENTS.has(event.event_type) ||
    (event.event_type === "EVENT_VOIDED" &&
      event.supersedes_event_id !== null &&
      assessmentIds.has(event.supersedes_event_id));
  if (!newestFirst.slice(0, index).every(keepsDraft)) {
    return { kind: "changed" };
  }
  return {
    kind: "open",
    booking,
    head: newest.stream_version,
    assessed: assessments.some((event) => !voided.has(event.id)),
  };
}

/** What SF-03:edit reads when it opens and again on "Reload". */
export interface DraftForEdit {
  readonly contract: Contract;
  /** Null when the contract is not a draft: its stream is not read. */
  readonly edit: DraftEdit | null;
}

/**
 * One key per opening of the form (`seed` counts its reloads). The key is not among
 * `CONTRACT_RECORD_KEYS`: the refresh after a 412 must not move the form under the typed input
 * (SCR-ST-09, DS-A11Y-19), and a cached answer must not open a draft that has changed since.
 */
export function draftForEditKey(contractId: string, seed: number): QueryKey {
  return queryKey("contract-draft-edit", "tenant", { contractId, seed });
}

/** The contract without a period context, then the guard over its stream (a draft only). */
export async function fetchDraftForEdit(contractId: string): Promise<DraftForEdit> {
  const contract = await fetchContract(contractId, { book: null, asOf: null, knownAt: null });
  return { contract, edit: contract.status === "DRAFT" ? await fetchDraftEdit(contractId) : null };
}

/** The guard of SF-03:edit over every event of the contract's stream, newest first. */
async function fetchDraftEdit(contractId: string): Promise<DraftEdit> {
  const events: ContractEvent[] = [];
  let cursor: string | null = null;
  let read = 0;
  do {
    const page: ListPage<ContractEvent> = await fetchListPage<ContractEvent>(
      `${contractPathOf(contractId)}/events`,
      { sort: "-stream_version" },
      cursor,
      { limit: DOCUMENTS_LIMIT, count: false },
    );
    events.push(...page.items);
    cursor = page.nextCursor;
    read += 1;
  } while (cursor !== null && read < DRAFT_STREAM_PAGES);
  return draftEditOf(events, cursor === null);
}

export function contractVersionsKey(contractId: string, book: string | null): QueryKey {
  return queryKey("contract-versions", "tenant", { contractId, book });
}

/** One page of API-S-ContractVersion list items, newest first unless the grid sorts. */
export async function fetchContractVersionsPage(
  contractId: string,
  book: string | null,
  cursor: string | null,
  sort: string | null,
): Promise<ListPage<ContractVersionSummary>> {
  const page = await fetchListPage<ContractVersionSummary>(
    `${contractPathOf(contractId)}/versions`,
    { book, sort: sort ?? "-version_no" },
    cursor,
  );
  await registerCodes(page.items.map((item) => item.revenue_to_date.currency));
  return page;
}

export function versionCompareKey(
  contractId: string,
  from: number,
  to: number,
  book: string | null,
): QueryKey {
  return queryKey("contract-version-compare", "tenant", { contractId, from, to, book });
}

/** The fields that differ between two versions of the book (REQ-CON-014). */
export async function fetchVersionCompare(
  contractId: string,
  from: number,
  to: number,
  book: string | null,
): Promise<VersionCompare> {
  return (
    await readJson<VersionCompare>(`${contractPathOf(contractId)}/versions/compare`, {
      from,
      to,
      book,
    })
  ).data;
}

/** The filters of the activity timeline (SCREENS §4.7). */
export interface HistoryQuery {
  /** Null reads every kind ("All"). */
  readonly kind: HistoryItemKind | null;
  readonly includeSystem: boolean;
}

export function contractHistoryKey(contractId: string, query: HistoryQuery): QueryKey {
  return queryKey("contract-history", "tenant", {
    contractId,
    kind: query.kind,
    include_system: query.includeSystem,
  });
}

/** One page of API-S-ContractHistoryItem, newest first. */
export function fetchContractHistoryPage(
  contractId: string,
  query: HistoryQuery,
  cursor: string | null,
): Promise<ListPage<ContractHistoryItem>> {
  return fetchListPage<ContractHistoryItem>(
    `${contractPathOf(contractId)}/history`,
    {
      kind: query.kind === null ? undefined : [query.kind],
      include_system: query.includeSystem ? true : undefined,
    },
    cursor,
    { limit: HISTORY_PAGE_SIZE, count: false },
  );
}

export function contractAuditKey(contractId: string): QueryKey {
  return queryKey("contract-audit-events", "tenant", { contractId });
}

/**
 * One page of the audit events whose object is the contract, newest first; null when the API refuses
 * the read (ruling R-28: the audit events are read with `audit.read` for all entities).
 */
export async function fetchContractAuditPage(
  contractId: string,
  cursor: string | null,
): Promise<ListPage<AuditEvent> | null> {
  try {
    return await fetchListPage<AuditEvent>(
      AUDIT_EVENTS_PATH,
      { object_type: CONTRACT_OBJECT_TYPE, object_id: contractId },
      cursor,
      { limit: HISTORY_PAGE_SIZE, count: false },
    );
  } catch (error) {
    if (isRefused(error)) {
      return null;
    }
    throw error;
  }
}

export function latestVerificationKey(): QueryKey {
  return queryKey("audit-verifications", "tenant", { view: "latest" });
}

/**
 * The latest audit chain verification of the workspace, or null when none has run and when the API
 * refuses the read.
 */
export async function fetchLatestVerification(): Promise<AuditChainVerification | null> {
  try {
    const page = await fetchListPage<AuditChainVerification>(
      `${AUDIT_EVENTS_PATH}/verifications`,
      {},
      null,
      { limit: 1, count: false },
    );
    return page.items[0] ?? null;
  } catch (error) {
    if (isRefused(error)) {
      return null;
    }
    throw error;
  }
}
