// SF-03 Contract workbench frame and Obligations tab (SCREENS §4.1.1 to §4.1.12, §4.2, §4.8, §4.9;
// §0.4 RT-10, RT-11; §0.5 SCR-URL-01 to SCR-URL-06; §0.7 SCR-ST-05, SCR-ST-07, SCR-ST-08, SCR-ST-10;
// DESIGN_SYSTEM DS-CMP-06, DS-CMP-07, DS-CMP-08, DS-CMP-15, DS-CMP-17; 04 API-R-28 to API-R-30, API-R-33,
// API-R-12; docs/dev-guide.md DG-FE-15; BUILD_SPEC CTR-22). The record header (breadcrumb, identifier,
// h1 customer name, chips, commands by status, meta row, one banner, the five-step tracker with its
// evidence regions and the six-cell KPI strip), the route tabs of the built tab routes, and the
// Obligations master list with the obligation pane. Every computed figure sits in `<ExplainTrigger
// figureRef>` and opens the docked Explain panel. `/contracts/:contractId` redirects to `/obligations`.
// The Schedules, Billing and Journals routes (RT-14 to RT-16; CTR-23) and the Modifications and History
// routes (RT-17, RT-18; CTR-24) render the same frame with the panels of `tabs/`, the Estimates routes
// (RT-12, RT-13; CTR-25) with `estimates.tsx`. A draft shows "Edit draft" (SF-03:edit, RT-19; CTR-24);
// an active contract shows "New modification" and "Change subscription" (SF-07, RT-20; CTR-27).
// A contract on hold shows "Release hold" (§4.1.6 and §4.9.4 rev 1.75; 04 rev 1.299).
// Not rendered (XR-14; R-RC-1): "Pin to Home", "Void contract" (CTR-11), "Regroup lines" (CTR-17),
// the currency view switch (L5-4-Q-24) and the tab warnings (L5-4-Q-25).
import { useQueries, useQuery } from "@tanstack/react-query";
import { type ReactNode, useCallback, useState } from "react";
import { Link, useLocation, useMatch, useNavigate, useParams } from "react-router";

import { testIdKey } from "../../components/data-grid/DataGrid";
import {
  type Explanation,
  ExplainPanel,
  ExplainProvider,
} from "../../components/explain/ExplainPanel";
import {
  type ExplainList,
  ExplainTrigger,
  type FigureRef,
} from "../../components/explain/ExplainTrigger";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useNoAnswer, useToast } from "../../components/feedback/Toast";
import { DotsThree, Info } from "../../components/icons/registry";
import { Money } from "../../components/money/Money";
import {
  FiveStepTracker,
  type TrackerState,
  type TrackerStep,
} from "../../components/record/FiveStepTracker";
import { type Kpi, KpiStrip } from "../../components/record/KpiStrip";
import { MasterDetail, type MasterItem } from "../../components/record/MasterDetail";
import { type MetaItem, RecordHeader } from "../../components/record/RecordHeader";
import { type RouteTab, RouteTabs } from "../../components/record/Tabs";
import { Button } from "../../components/ui/Button";
import { Menu, type MenuItem } from "../../components/ui/Menu";
import { chipFor, OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { useCommand, useCommandKeys } from "../../lib/api/commands";
import { JOB_POLL_INTERVAL_MS } from "../../lib/api/jobs";
import { ApiProblem } from "../../lib/api/problems";
import {
  ACTIVATION_CHECKLIST_FAILED,
  allocationKey,
  APPROVAL_REQUEST_HEADER,
  type ApprovalItem,
  type CombinationSuggestion,
  combinationSuggestionsKey,
  computeJobsKey,
  type Contract,
  CONTRACT_CREATE_PERMISSION,
  CONTRACT_READ_PERMISSION,
  CONTRACT_RECORD_KEYS,
  contractIfMatch,
  contractJudgementsKey,
  contractAssessmentsKey,
  contractKey,
  contractOverridesKey,
  CONTRACTS_PATH,
  type ContractStepState,
  contractUnreviewedJudgementsKey,
  contractVersionKey,
  distinctReviewsKey,
  documentsKey,
  EVENT_RECORD_PERMISSION,
  fetchAllocationWalk,
  fetchCombinationSuggestions,
  fetchComputeJobs,
  fetchContract,
  fetchContractAssessments,
  fetchContractJudgements,
  fetchContractOverrides,
  fetchContractVersion,
  fetchDistinctReviews,
  fetchDocuments,
  fetchExplanation,
  fetchPendingActivation,
  fetchUnreviewedJudgements,
  JUDGEMENT_CREATE_PERMISSION,
  type Judgement,
  JUDGEMENTS_PATH,
  pendingActivationKey,
  type RecordContext,
  recordsOfStandingOverrides,
  sendCommand,
} from "../../lib/api/queries/contracts";
import {
  ESTIMATE_ROUTE,
  estimateCountKey,
  fetchEstimateCount,
} from "../../lib/api/queries/estimates";
import { judgementStatusLabel } from "../../lib/api/queries/judgements";
import { type Me, useMe } from "../../lib/api/queries/me";
import {
  fetchModificationCount,
  MODIFICATION_CREATE_PERMISSION,
  MODIFICATION_NEW_ROUTE,
  modificationCountKey,
} from "../../lib/api/queries/modifications";
import {
  contractObligationsKey,
  fetchContractObligations,
  fetchSspVersionLabel,
  matchesObligation,
  type Obligation,
  type ObligationSort,
  sortObligations,
  sspVersionLabelKey,
} from "../../lib/api/queries/obligations";
import {
  entitiesKey,
  fetchActiveEntities,
  fetchPeriods,
  type Period,
  periodLabel,
  periodsKey,
  STRUCTURE_READ_PERMISSION,
} from "../../lib/api/queries/tenant";
import {
  currentDateIn,
  formatDate,
  formatMoney,
  formatNumber,
  formatPercent,
  formatPeriod,
  formatRate,
  formatTimestamp,
  NO_VALUE,
} from "../../lib/format";
import { SUBSCRIPTION_ACTIONS } from "../../lib/forms/modification";
import { t } from "../../lib/i18n/t";
import { useBuiltPaths } from "../settings/index";
import { requestNumber, useRefreshRecord } from "./drawers/common";
import { EstimatesTab } from "./estimates";
import { CombineDrawer, DismissSuggestionModal } from "./drawers/combine";
import { DistinctReviewDrawer } from "./drawers/distinct-review";
import { DocumentsDrawer } from "./drawers/documents";
import { ApplyHoldDrawer, ReleaseHoldDrawer } from "./drawers/holds";
import { EditMemosDrawer } from "./drawers/memos";
import { type EventKind, EVENT_KINDS, RecordEventDrawer } from "./drawers/record-event";
import { Step1AssessmentDrawer } from "./drawers/step1-assessment";
import { Step1ReviewDrawer } from "./drawers/step1-review";
import { DiscardRecord } from "./judgement-discard";
import { isProbable, latestStep1Record, STEP1_TOPICS, type Step1Path, step1Path } from "./step1";
import {
  balanceFigure,
  dateRange,
  figureFromLink,
  isPaneTab,
  moneyText,
  ObligationChips,
  ObligationPane,
  type PaneCommand,
  type PaneTab,
  rangePositionText,
  REQUEST_ROUTE,
  SCHEDULES_ROUTE,
} from "./obligation-pane";
import { BillingTab, isZeroAmount } from "./tabs/billing";
import { HistoryTab } from "./tabs/history";
import { JournalsTab } from "./tabs/journals";
import {
  acceptsModifications,
  changePriceHref,
  ModificationsTab,
  newModificationHref,
} from "./tabs/modifications";
import { SchedulesTab, type WorkbenchTabProps } from "./tabs/schedules";

/** SCREENS RT-10 SF-03 and RT-11 SF-03:obligation. */
export const OBLIGATIONS_ROUTE = "/contracts/:contractId/obligations";
export const OBLIGATION_ROUTE = "/contracts/:contractId/obligations/:obligationId";
/** SCREENS RT-10: `/contracts/:contractId` redirects to the Obligations tab. */
export const CONTRACT_ROOT_ROUTE = "/contracts/:contractId";
export const ESTIMATES_ROUTE = "/contracts/:contractId/estimates";
export const BILLING_ROUTE = "/contracts/:contractId/billing";
export const JOURNALS_ROUTE = "/contracts/:contractId/journals";
export const MODIFICATIONS_ROUTE = "/contracts/:contractId/modifications";
export const HISTORY_ROUTE = "/contracts/:contractId/history";
export const EDIT_ROUTE = "/contracts/:contractId/edit";

/** SCREENS §0.5 context parameters a record link keeps (SCR-URL-01 to SCR-URL-06). */
export const CONTEXT_PARAMS = [
  "entity",
  "period",
  "book",
  "currency_view",
  "known_at",
  "snapshot",
] as const;

export function contextSearch(search: string): string {
  const params = new URLSearchParams(search);
  const kept = new URLSearchParams();
  for (const name of CONTEXT_PARAMS) {
    const value = params.get(name);
    if (value !== null) {
      kept.set(name, value);
    }
  }
  const text = kept.toString();
  return text === "" ? "" : `?${text}`;
}

/** While the obligations load: one array, so memoised tab columns are not rebuilt on every render. */
const NO_OBLIGATIONS: readonly Obligation[] = [];
/** 04 API-C-10: the rule id of a to-date measure the version's trace cannot answer at the cut. */
const UNREADABLE_RULE = "API-C-10";

/** The DS-FMT-19 label of a period among the periods read, else the fiscal label of its key. */
function contextPeriodLabel(periods: readonly Period[], periodKey: string): string {
  const found = periods.find((item) => item.period.period_key === periodKey);
  if (found !== undefined) {
    return periodLabel(found.period);
  }
  try {
    return formatPeriod(periodKey);
  } catch {
    return periodKey;
  }
}

/**
 * SCREENS §6.3 list level (rev 1.21): the contract's revenue is net of consideration payable released
 * (ENGINE_SPEC S04-R-02) while an obligation's is gross of it, so the rows need not add up to the value
 * above them. The sentence is shown when the version's build-up has consideration payable; the read
 * is made only while the list is open.
 */
function ConsiderationPayableNote({
  contract,
  book,
}: {
  readonly contract: Contract;
  readonly book: string | null;
}) {
  const versionNo = contract.context?.version_no ?? null;
  const version = useQuery({
    queryKey: contractVersionKey(contract.id, versionNo ?? 0, book),
    queryFn: () => fetchContractVersion(contract.id, versionNo ?? 0, book),
    enabled: versionNo !== null,
  });
  const payable = version.data?.transaction_price_buildup.consideration_payable.amount;
  return payable === undefined || isZeroAmount(payable) ? null : (
    <p className="text-body-sm text-fg-2">{t("contracts.workbench.explainList.payable")}</p>
  );
}

/** SCREENS SCR-URL-03 book labels. */
export function bookLabel(code: string | null | undefined): string {
  return code === "ASC606" || code === "IFRS15" || code === "LEGACY"
    ? t(`contracts.workbench.book.${code}`)
    : (code ?? NO_VALUE);
}

const STEP_STATE: Readonly<Record<ContractStepState, TrackerState>> = {
  COMPLETE: "complete",
  NEEDS_ATTENTION: "attention",
  BLOCKED: "blocked",
  IN_REVIEW: "review",
  NOT_STARTED: "notStarted",
};

export const STEP_ORDER = [
  "CONTRACT",
  "OBLIGATIONS",
  "TRANSACTION_PRICE",
  "ALLOCATION",
  "RECOGNITION",
] as const;

export interface TrackerFacts {
  readonly suggestions: readonly CombinationSuggestion[];
  /** The external ids of the other members of the combination group. */
  readonly members: readonly string[];
  readonly obligations: readonly Obligation[];
  readonly sspLabel: string | null;
  /** The obligations or the label of their SSP book version are still being read. */
  readonly sspLabelPending?: boolean;
  /** SCREENS §4.1.3 Step 1 path (rev 1.11); null or absent while it is not read. */
  readonly step1?: Step1Path | null;
}

export interface TrackerLine {
  readonly state: TrackerState;
  readonly status: string;
  /** The status line waits for a read: the step shows nothing partial (SCREENS §4.1.3 rev 1.29). */
  readonly busy?: boolean;
}

function stepOf(contract: Contract, step: (typeof STEP_ORDER)[number]) {
  return contract.steps.find((item) => item.step === step);
}

/** The judgement.review permission of the Step 1 record's reviewer (PRD §2.5 JUDGEMENT_RECORD). */
const JUDGEMENT_REVIEW_PERMISSION = "judgement.review";

/** SCREENS §4.1.3 Step 1 path: the command that comes next, or null while someone else acts. */
export type Step1Command = "review" | "assessment" | "criteriaMet" | "submit";

export interface Step1Next {
  /** The line of the evidence region and of banner 6: what is recorded and who acts next. */
  readonly line: string;
  readonly command: Step1Command | null;
  /** The record whose review is pending, for "View request". */
  readonly waiting: Judgement | null;
}

/** SCREENS §4.1.3 Step 1 path table (rev 1.11; supervisor ruling R-89). */
export function step1Next(contract: Pick<Contract, "status">, path: Step1Path): Step1Next {
  const gated = contract.status === "NOT_A_CONTRACT";
  switch (path.kind) {
    case "none":
      return { line: t("contracts.workbench.step1.path.none"), command: "review", waiting: null };
    case "waiting":
      return {
        line: t("contracts.workbench.step1.path.waiting", { number: path.record.judgement_no }),
        command: null,
        waiting: path.record,
      };
    case "rejected":
      return {
        line: t("contracts.workbench.step1.path.rejected", { number: path.record.judgement_no }),
        command: "review",
        waiting: null,
      };
    case "reviewed": {
      // Behind the gate a reviewed probable record is recorded as criteria met; the line names it.
      const criteriaMet = gated && isProbable(path.record);
      return {
        line: t(
          criteriaMet
            ? "contracts.workbench.step1.path.reviewedCriteriaMet"
            : "contracts.workbench.step1.path.reviewed",
          {
            number: path.record.judgement_no,
            name: path.record.reviewer?.display_name ?? NO_VALUE,
            at:
              path.record.reviewed_at === null
                ? NO_VALUE
                : formatTimestamp(path.record.reviewed_at),
          },
        ),
        command: criteriaMet ? "criteriaMet" : "assessment",
        waiting: null,
      };
    }
    case "assessed": {
      const params = { number: path.record.judgement_no, date: formatDate(path.date) };
      if (!gated) {
        return {
          line: t("contracts.workbench.step1.path.assessed", params),
          command: "submit",
          waiting: null,
        };
      }
      return path.probable
        ? {
            line: t("contracts.workbench.step1.path.criteriaMet", params),
            command: "submit",
            waiting: null,
          }
        : {
            line: t("contracts.workbench.step1.path.criteriaNotMet", params),
            command: "review",
            waiting: null,
          };
    }
  }
}

/**
 * SCREENS §4.1.3 row 1 (rev 1.11): the status line of step 1 while the Step 1 path of a DRAFT or
 * NOT_A_CONTRACT contract is not at its last row, and the state shown when `steps[0]` reads COMPLETE.
 */
function step1Status(
  contract: Contract,
  path: Step1Path | null | undefined,
): { readonly status: string; readonly state: TrackerState } | null {
  if (path === null || path === undefined) {
    return null;
  }
  const gated = contract.status === "NOT_A_CONTRACT";
  if (contract.status !== "DRAFT" && !gated) {
    return null;
  }
  switch (path.kind) {
    case "none":
      return gated
        ? null
        : { status: t("contracts.workbench.tracker.needsReview"), state: "attention" };
    case "waiting":
      return {
        status: t("contracts.workbench.tracker.reviewWaiting", {
          number: path.record.judgement_no,
        }),
        state: "review",
      };
    case "rejected":
      return {
        status: t("contracts.workbench.tracker.reviewRejected", {
          number: path.record.judgement_no,
        }),
        state: "attention",
      };
    case "reviewed":
      return {
        status: t(
          gated && isProbable(path.record)
            ? "contracts.workbench.tracker.reviewedCriteriaMet"
            : "contracts.workbench.tracker.reviewedAssessment",
          { number: path.record.judgement_no },
        ),
        state: "attention",
      };
    case "assessed":
      return gated && path.probable
        ? {
            status: t("contracts.workbench.tracker.criteriaMetOn", { date: formatDate(path.date) }),
            state: "attention",
          }
        : null;
  }
}

/** SCREENS §4.1.3 status lines of the five steps from `steps[]` (E-112, E-113) and the record facts. */
export function trackerLines(contract: Contract, facts: TrackerFacts): readonly TrackerLine[] {
  const draft = contract.status === "DRAFT" || contract.status === "PENDING_REVIEW";
  const price = contract.kpis?.transaction_price;
  return STEP_ORDER.map((name) => {
    const found = stepOf(contract, name);
    let state = found === undefined ? "notStarted" : STEP_STATE[found.state];
    const done = state === "complete" || state === "review";
    const detail = found?.detail ?? {};
    let status = "";
    let busy = false;
    switch (name) {
      case "CONTRACT": {
        const path = step1Status(contract, facts.step1);
        if (path !== null) {
          status = path.status;
          if (state === "complete") {
            state = path.state;
          }
        } else if (done) {
          status = contract.combination_group.is_singleton
            ? t("contracts.workbench.tracker.standAlone")
            : t("contracts.workbench.tracker.combinedWith", {
                contracts:
                  facts.members.length === 0
                    ? contract.combination_group.code
                    : facts.members.join(", "),
              });
        } else if (contract.status === "NOT_A_CONTRACT") {
          status = t("contracts.workbench.tracker.criteriaNotMet");
        } else if (facts.suggestions.length > 0) {
          status = t("contracts.workbench.tracker.suggested", {
            contracts: facts.suggestions
              .flatMap((item) => item.contract_external_ids)
              .filter((id) => id !== contract.external_id)
              .join(", "),
          });
        } else {
          status = t("contracts.workbench.tracker.needsReview");
        }
        break;
      }
      case "OBLIGATIONS": {
        if (state === "notStarted") {
          break;
        }
        const rights = facts.obligations.filter(
          (item) => item.obligation_kind === "MATERIAL_RIGHT",
        ).length;
        const count = facts.obligations.length;
        status = !done
          ? t("contracts.workbench.tracker.needsReview")
          : rights === 0
            ? t("contracts.workbench.tracker.obligations", {
                count,
                formatted: formatNumber(count, { kind: "count" }),
              })
            : t("contracts.workbench.tracker.obligationsWithRights", {
                count,
                formatted: formatNumber(count, { kind: "count" }),
                rights: formatNumber(rights, { kind: "count" }),
              });
        break;
      }
      case "TRANSACTION_PRICE":
        if (price !== undefined && state !== "notStarted") {
          const amount = moneyText(price.amount, price.currency);
          status = draft ? t("contracts.workbench.tracker.computed", { value: amount }) : amount;
        }
        break;
      case "ALLOCATION": {
        if (state === "notStarted") {
          break;
        }
        const missing = facts.obligations.find((item) => item.ssp.book_version_id === null);
        if (state === "blocked" && missing !== undefined) {
          status = t("contracts.workbench.tracker.noSsp", { product: missing.product.code });
        } else if (draft) {
          status = t("contracts.workbench.tracker.computedRelativeSsp");
        } else if (facts.sspLabelPending === true) {
          // The line names the SSP book version: it is not shown without it and then with it.
          busy = true;
        } else {
          status =
            facts.sspLabel === null
              ? t("contracts.workbench.tracker.relativeSsp")
              : t("contracts.workbench.tracker.relativeSspWith", { label: facts.sspLabel });
        }
        break;
      }
      case "RECOGNITION": {
        if (state === "notStarted") {
          break;
        }
        const ratio =
          typeof detail.recognized_ratio === "string"
            ? detail.recognized_ratio
            : contract.kpis_ratios.recognized;
        status = draft
          ? t("contracts.workbench.tracker.preview")
          : ratio === null
            ? ""
            : t("contracts.workbench.tracker.recognized", { ratio: formatPercent(ratio) });
        break;
      }
    }
    return busy ? { state, status, busy } : { state, status };
  });
}

function Th({
  children,
  end = false,
}: {
  readonly children: ReactNode;
  readonly end?: boolean | undefined;
}) {
  return (
    <th
      scope="col"
      className={end ? "px-2 py-1 text-end font-medium" : "px-2 py-1 text-start font-medium"}
    >
      {children}
    </th>
  );
}

function StaticTable({
  caption,
  testId,
  headers,
  children,
  footer,
}: {
  readonly caption: string;
  readonly testId?: string;
  readonly headers: readonly { readonly label: string; readonly end?: boolean | undefined }[];
  readonly children: ReactNode;
  readonly footer?: ReactNode;
}) {
  return (
    <table data-testid={testId} className="w-full border-collapse text-body-sm">
      <caption className="mb-1 text-start text-caption text-fg-3">{caption}</caption>
      <thead>
        <tr className="border-b border-default bg-subtle text-fg-2">
          {headers.map((header) => (
            <Th key={header.label} end={header.end}>
              {header.label}
            </Th>
          ))}
        </tr>
      </thead>
      <tbody>{children}</tbody>
      {footer === undefined ? null : <tfoot>{footer}</tfoot>}
    </table>
  );
}

function RetryBanner({
  title,
  onRetry,
  problem,
}: {
  readonly title: string;
  readonly onRetry: () => void;
  readonly problem?: unknown;
}) {
  const reference = problem instanceof ApiProblem ? problem.requestId : null;
  return (
    <Banner
      tone="negative"
      title={title}
      actions={
        <Button variant="link" onClick={onRetry}>
          {t("common.grid.retry")}
        </Button>
      }
    >
      {problem instanceof ApiProblem ? <p>{problem.title}</p> : null}
      {reference === null ? null : <p>{t("contracts.drawer.reference", { reference })}</p>}
    </Banner>
  );
}

const CRITERIA = ["a", "b", "c", "d", "e"] as const;

/**
 * The route of a judgement record's review request, for "View request" on the record's line (SCREENS
 * §4.1.3 and §4.9.8, rev 1.76: a rejected record, where the reviewer's reason stands, and a record
 * the activation checklist waits for) — as the waiting line of the Step 1 path offers it, to a holder
 * of `judgement.review` and to the preparer. Null for a record that was never sent, where the
 * request screen is not built, and for a viewer the API would answer 404: a request is read by who
 * holds its step's permission for its entity, by its preparer and by its deciders (04 §16.10). The
 * permission is asked for the contract's entity (the access module; SCREENS §0.6 SCR-PERM-02 (a)).
 */
function useRecordRequest(
  contract: Pick<Contract, "contracting_entity">,
): (record: Pick<Judgement, "approval_request_id" | "created_by">) => string | null {
  const access = useAccess();
  const me = useMe().data;
  const built = useBuiltPaths();
  const reviews = access.holds(JUDGEMENT_REVIEW_PERMISSION, contract.contracting_entity);
  return (record) =>
    record.approval_request_id !== null &&
    built.has(REQUEST_ROUTE) &&
    (reviews || (me !== undefined && record.created_by.id === me.user.id))
      ? `/approvals/requests/${record.approval_request_id}`
      : null;
}

/** "View request" of a record's line; nothing where `to` is null. */
function RecordRequestLink({ to }: { readonly to: string | null }) {
  return to === null ? null : (
    <Link to={to} className="text-body-sm text-accent-fg hover:underline">
      {t("contracts.workbench.banner.viewRequest")}
    </Link>
  );
}

function Step1Evidence({
  contract,
  suggestions,
  members,
  commands,
  path,
  onCombine,
  onDismiss,
}: {
  readonly contract: Contract;
  readonly suggestions: readonly CombinationSuggestion[];
  readonly members: readonly string[];
  /**
   * What the view may command: `combine` for a holder of `contract.create`; `discard` on every view
   * but one of an earlier `known_at`, where no command renders — who may discard a draft or a
   * rejected record is asked beside the command itself.
   */
  readonly commands: { readonly combine: boolean; readonly discard: boolean };
  /** The line of the Step 1 path with its action (SCREENS §4.1.3, rev 1.11). */
  readonly path: ReactNode;
  readonly onCombine: () => void;
  readonly onDismiss: (suggestion: CombinationSuggestion) => void;
}) {
  const requestOf = useRecordRequest(contract);
  const judgements = useQuery({
    queryKey: contractJudgementsKey(contract.id),
    queryFn: () => fetchContractJudgements(contract.id),
  });
  // The latest Step 1 record, of either topic: NOT_A_CONTRACT records a not-probable conclusion.
  // A discarded draft (E-57 `VOIDED`, 04 T-CON-19 rev 1.242) is no record of the contract's
  // Step 1: neither list takes it.
  const record =
    latestStep1Record(judgements.data ?? []) ??
    (judgements.data ?? [])
      .filter((item) => STEP1_TOPICS.has(item.topic) && item.status !== "VOIDED")
      .sort((left, right) => (left.created_at < right.created_at ? 1 : -1))[0];
  // SCREENS §4.1.3 (rev 1.66): the Step 1 review creates its record and sends it for review as two
  // requests. A draft whose submission was refused is no step of the path — the path offers the
  // review again — and it holds the activation (PRD IMP-104): each is named here, newest first,
  // with "Discard" for a holder of `judgement.create` for the contract's entity. So is each
  // rejected record (rev 1.74; PRD SM-10 rev 1.199, IMP-145): the path writes a new record after a
  // rejection, and the rejected one fails the activation checklist until it is discarded.
  const unanswered = (judgements.data ?? [])
    .filter(
      (item) =>
        STEP1_TOPICS.has(item.topic) && (item.status === "DRAFT" || item.status === "REJECTED"),
    )
    .sort((left, right) => (left.created_at < right.created_at ? 1 : -1));
  const awaitsActivation = contract.status === "DRAFT" || contract.status === "NOT_A_CONTRACT";
  const questionnaire =
    record?.questionnaire === null || record?.questionnaire === undefined
      ? undefined
      : (record.questionnaire as { readonly criteria?: Readonly<Record<string, unknown>> });
  const conclusion = (criterion: (typeof CRITERIA)[number]) => {
    const stored = questionnaire?.criteria?.[criterion];
    if (stored === "YES") {
      return t("contracts.drawer.yes");
    }
    if (stored === "NO") {
      return t("contracts.drawer.no");
    }
    if (criterion === "d") {
      return t(contract.has_commercial_substance ? "contracts.drawer.yes" : "contracts.drawer.no");
    }
    if (criterion === "e" && record !== undefined) {
      return t(isProbable(record) ? "contracts.drawer.yes" : "contracts.drawer.no");
    }
    return t("contracts.workbench.step1.notRecorded");
  };
  const term = stepOf(contract, "CONTRACT")?.detail.enforceable_term as
    { readonly end_date?: string | null } | undefined;
  const termination = contract.termination;
  return (
    <div className="flex flex-col gap-4">
      {judgements.isPending ? (
        <Skeleton region={t("contracts.workbench.step1.criteria")} shape="rows" count={5} />
      ) : judgements.isError ? (
        <RetryBanner
          title={t("contracts.workbench.step1.loadError")}
          onRetry={() => void judgements.refetch()}
          problem={judgements.error}
        />
      ) : (
        <StaticTable
          caption={t("contracts.workbench.step1.criteria")}
          headers={[
            { label: t("contracts.workbench.step1.column.criterion") },
            { label: t("contracts.workbench.step1.column.conclusion") },
            { label: t("contracts.workbench.step1.column.evidence") },
            { label: t("contracts.workbench.step1.column.citation") },
          ]}
        >
          {CRITERIA.map((criterion) => (
            <tr key={criterion} className="border-b border-hairline">
              <th scope="row" className="px-2 py-1 text-start font-normal">
                {t(`contracts.workbench.step1.criterion.${criterion}`)}
              </th>
              <td className="px-2 py-1">{conclusion(criterion)}</td>
              <td className="px-2 py-1">
                {record === undefined ||
                (criterion === "d" && questionnaire?.criteria === undefined)
                  ? NO_VALUE
                  : t("contracts.workbench.step1.record", {
                      number: record.judgement_no,
                      status: judgementStatusLabel(record.status),
                    })}
              </td>
              <td className="px-2 py-1 font-mono text-mono-sm">{`ASC 606-10-25-1(${criterion})`}</td>
            </tr>
          ))}
        </StaticTable>
      )}
      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-body-sm">
        {termination === null ? null : (
          <div className="flex gap-1.5">
            <dt className="text-fg-3">{t("contracts.workbench.step1.termination")}</dt>
            <dd className="text-fg-1">
              {t("contracts.workbench.step1.terminationValue", {
                party: t(
                  `contracts.drawer.step1.party.${termination.party === "NONE" ? "none" : termination.party.toLowerCase()}`,
                ),
                penalty:
                  termination.has_penalty === null
                    ? NO_VALUE
                    : t(termination.has_penalty ? "contracts.drawer.yes" : "contracts.drawer.no"),
                days:
                  termination.notice_days === null
                    ? NO_VALUE
                    : formatNumber(termination.notice_days, { kind: "count" }),
              })}
            </dd>
          </div>
        )}
        {term?.end_date === null || term?.end_date === undefined ? null : (
          <div className="flex gap-1.5">
            <dt className="text-fg-3">{t("contracts.workbench.step1.enforceableTerm")}</dt>
            <dd className="num text-fg-1">{dateRange(contract.inception_date, term.end_date)}</dd>
          </div>
        )}
        <div className="flex gap-1.5">
          <dt className="text-fg-3">{t("contracts.workbench.step1.combination")}</dt>
          <dd className="text-fg-1">
            <span className="font-mono text-mono-sm">{contract.combination_group.code}</span>
            {members.length === 0 ? null : ` · ${members.join(", ")}`}
          </dd>
        </div>
      </dl>
      {suggestions.length === 0 ? null : (
        <StaticTable
          caption={t("contracts.workbench.step1.suggestions")}
          headers={[
            { label: t("contracts.workbench.step1.column.contracts") },
            { label: t("contracts.workbench.step1.column.inception") },
            { label: t("contracts.workbench.step1.column.actions") },
          ]}
        >
          {suggestions.map((suggestion) => (
            <tr key={suggestion.id} className="border-b border-hairline">
              <th scope="row" className="px-2 py-1 text-start font-mono text-mono-sm font-normal">
                {suggestion.contract_external_ids.join(", ")}
              </th>
              <td className="num px-2 py-1">
                {suggestion.inception_dates.map((date) => formatDate(date)).join(", ")}
              </td>
              <td className="px-2 py-1">
                {commands.combine ? (
                  <span className="flex gap-3">
                    <Button variant="link" onClick={onCombine}>
                      {t("contracts.workbench.step1.combine")}
                    </Button>
                    <Button variant="link" onClick={() => onDismiss(suggestion)}>
                      {t("contracts.workbench.step1.dismiss")}
                    </Button>
                  </span>
                ) : (
                  NO_VALUE
                )}
              </td>
            </tr>
          ))}
        </StaticTable>
      )}
      {unanswered.map((item) => (
        <div
          key={item.id}
          data-testid={item.status === "DRAFT" ? "SF-03-step1-draft" : "SF-03-step1-rejected"}
          className="flex flex-wrap items-center gap-x-3 gap-y-1"
        >
          <p className="text-body-sm text-fg-1">
            {item.status === "DRAFT"
              ? t("contracts.judgement.draft", { number: item.judgement_no })
              : t(
                  awaitsActivation
                    ? "contracts.judgement.rejected.beforeActivation"
                    : "contracts.judgement.rejected",
                  { number: item.judgement_no },
                )}
          </p>
          {/* Rev 1.76: the record's request, where the reviewer's reason stands. A draft that was
              never sent names none. */}
          <RecordRequestLink to={requestOf(item)} />
          {commands.discard ? (
            <DiscardRecord
              record={item}
              contract={contract}
              invalidates={CONTRACT_RECORD_KEYS}
              testId="SF-03-dialog-discard-record"
            />
          ) : null}
        </div>
      ))}
      {path}
    </div>
  );
}

/** SCREENS §4.1.3 Step 1 path: the line with the command that comes next, or "View request". */
function Step1PathLine({
  next,
  command,
  request,
}: {
  readonly next: Step1Next;
  /** The command's label and handler, when the viewer may run it. */
  readonly command: { readonly label: string; readonly onSelect: () => void } | null;
  /** The route of the pending review request, when the viewer may open it. */
  readonly request: string | null;
}) {
  return (
    <div data-testid="SF-03-step1-path" className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <p className="text-body-sm text-fg-1">{next.line}</p>
      {command === null ? null : (
        <Button variant="secondary" size="sm" onClick={command.onSelect}>
          {command.label}
        </Button>
      )}
      {request === null ? null : (
        <Link to={request} className="text-body-sm text-accent-fg hover:underline">
          {t("contracts.workbench.banner.viewRequest")}
        </Link>
      )}
    </div>
  );
}

/** E-57 statuses of a record that is not reviewed and still counts: what the checklist waits for. */
const UNREVIEWED: ReadonlySet<string> = new Set(["DRAFT", "SUBMITTED", "REJECTED"]);

/**
 * The word of step 2's "Distinct review" cell (SCREENS §4.1.3, rev 1.76): "Recorded" where a reviewed
 * record of the obligation exists — what the checklist's `DISTINCT_REVIEW` asks (PRD IMP-102) — else
 * the status, in the words of §0.8, of the obligation's newest record that is not reviewed and still
 * counts, else "Not recorded". Before, the cell read "Recorded" for a record of any status, beside a
 * checklist that said the review was not recorded.
 */
export function distinctReviewWord(reviews: readonly Judgement[], obligationId: string): string {
  const own = reviews.filter((item) => item.subject_id === obligationId);
  if (own.some((item) => item.status === "REVIEWED")) {
    return t("contracts.workbench.step2.recorded");
  }
  // The series gives its numbers in the order of creation: the highest number is the newest record.
  const newest = own
    .filter((item) => UNREVIEWED.has(item.status))
    .sort((left, right) => (left.judgement_no < right.judgement_no ? 1 : -1))[0];
  return newest === undefined
    ? t("contracts.workbench.step2.notRecorded")
    : judgementStatusLabel(newest.status);
}

function Step2Evidence({
  contract,
  obligations,
  canReview,
  onReview,
}: {
  readonly contract: Contract;
  readonly obligations: readonly Obligation[];
  readonly canReview: boolean;
  readonly onReview: (obligation: Obligation) => void;
}) {
  const reviews = useQuery({
    queryKey: distinctReviewsKey(contract.id),
    queryFn: () => fetchDistinctReviews(contract.id),
  });
  return (
    <StaticTable
      caption={t("contracts.workbench.step2.caption")}
      headers={[
        { label: t("contracts.workbench.step2.column.obligation") },
        { label: t("contracts.workbench.step2.column.product") },
        { label: t("contracts.workbench.step2.column.kind") },
        { label: t("contracts.workbench.step2.column.distinctness") },
        { label: t("contracts.workbench.step2.column.template") },
        { label: t("contracts.workbench.step2.column.review") },
        { label: t("contracts.workbench.step1.column.actions") },
      ]}
    >
      {obligations.map((obligation) => (
        <tr key={obligation.id} className="border-b border-hairline">
          <th scope="row" className="px-2 py-1 text-start font-mono text-mono-sm font-normal">
            {obligation.obligation_key}
          </th>
          <td className="px-2 py-1 font-mono text-mono-sm">{obligation.product.code}</td>
          <td className="px-2 py-1">
            {t(`contracts.obligation.kind.${obligation.obligation_kind}`)}
          </td>
          <td className="px-2 py-1">{t(`policies.ssp.distinctness.${obligation.distinctness}`)}</td>
          <td className="px-2 py-1 font-mono text-mono-sm">
            {`${obligation.pob_template_version.template_code} v${String(obligation.pob_template_version.version_no)}`}
          </td>
          <td className="px-2 py-1">
            {reviews.isPending ? NO_VALUE : distinctReviewWord(reviews.data ?? [], obligation.id)}
          </td>
          <td className="px-2 py-1">
            {canReview ? (
              <Button variant="link" onClick={() => onReview(obligation)}>
                {t("contracts.drawer.distinct.title")}
              </Button>
            ) : (
              NO_VALUE
            )}
          </td>
        </tr>
      ))}
    </StaticTable>
  );
}

const BUILDUP_ROWS = [
  "fixed",
  "vc_constrained",
  "expected_returns",
  "consideration_payable",
  "financing_adjustment",
  "noncash",
  "sales_tax_excluded",
  "out_of_scope",
] as const;

function Step3Evidence({
  contract,
  book,
}: {
  readonly contract: Contract;
  readonly book: string | null;
}) {
  const versionNo = contract.context?.version_no ?? null;
  const version = useQuery({
    queryKey: contractVersionKey(contract.id, versionNo ?? 0, book),
    queryFn: () => fetchContractVersion(contract.id, versionNo ?? 0, book),
    enabled: versionNo !== null,
  });
  if (versionNo === null) {
    return <p className="text-body-sm text-fg-2">{t("contracts.workbench.step3.notComputed")}</p>;
  }
  if (version.isPending) {
    return (
      <Skeleton
        region={t("contracts.workbench.step3.caption", { currency: contract.transaction_currency })}
        shape="rows"
        count={9}
      />
    );
  }
  if (version.isError) {
    return (
      <RetryBanner
        title={t("contracts.workbench.step3.loadError")}
        onRetry={() => void version.refetch()}
        problem={version.error}
      />
    );
  }
  const buildup = version.data.transaction_price_buildup;
  const note = stepOf(contract, "TRANSACTION_PRICE")?.detail.financing_note as
    { readonly assessed?: boolean; readonly exception_32_17?: string | null } | undefined;
  const financing =
    note === undefined
      ? null
      : note.assessed === true
        ? t("contracts.workbench.step3.financingAssessed")
        : note.exception_32_17 === null || note.exception_32_17 === undefined
          ? t("contracts.workbench.step3.financingNotAssessed")
          : t("contracts.workbench.step3.financingException");
  return (
    <div className="flex flex-col gap-2">
      <StaticTable
        caption={t("contracts.workbench.step3.caption", {
          currency: contract.transaction_currency,
        })}
        headers={[
          { label: t("contracts.workbench.step3.column.component") },
          { label: t("contracts.workbench.step3.column.amount"), end: true },
        ]}
        footer={
          <>
            <tr className="border-t border-default font-semibold">
              <th scope="row" className="px-2 py-1 text-start">
                {t("contracts.workbench.total")}
              </th>
              <td className="px-2 py-1 text-end">
                <Money
                  value={buildup.total.amount}
                  currency={buildup.total.currency}
                  variant="cell"
                />
              </td>
            </tr>
            <tr>
              <th scope="row" className="px-2 py-1 text-start font-normal text-fg-3">
                {t("contracts.workbench.step3.excluded")}
              </th>
              <td className="px-2 py-1 text-end text-fg-3">
                <Money
                  value={buildup.vc_excluded.amount}
                  currency={buildup.vc_excluded.currency}
                  variant="cell"
                />
              </td>
            </tr>
          </>
        }
      >
        {BUILDUP_ROWS.map((row) => (
          <tr key={row} className="border-b border-hairline">
            <th scope="row" className="px-2 py-1 text-start font-normal">
              {t(`contracts.workbench.step3.row.${row}`)}
            </th>
            <td className="px-2 py-1 text-end">
              <Money value={buildup[row].amount} currency={buildup[row].currency} variant="cell" />
            </td>
          </tr>
        ))}
      </StaticTable>
      {financing === null ? null : <p className="text-body-sm text-fg-2">{financing}</p>}
    </div>
  );
}

function AllocationWalkTable({
  contract,
  context,
  obligations,
  explainContext,
}: {
  readonly contract: Contract;
  readonly context: RecordContext;
  readonly obligations: readonly Obligation[];
  readonly explainContext: string;
}) {
  const walk = useQuery({
    queryKey: allocationKey(contract.id, context),
    queryFn: () => fetchAllocationWalk(contract.id, context),
    enabled: contract.context !== null,
  });
  const currency = contract.transaction_currency;
  if (contract.context === null) {
    return <p className="text-body-sm text-fg-2">{t("contracts.workbench.step3.notComputed")}</p>;
  }
  if (walk.isPending) {
    return (
      <Skeleton
        region={t("contracts.workbench.allocation.caption", { currency })}
        shape="rows"
        count={4}
      />
    );
  }
  if (walk.isError) {
    return (
      <RetryBanner
        title={t("contracts.workbench.allocation.loadError")}
        onRetry={() => void walk.refetch()}
        problem={walk.error}
      />
    );
  }
  const byKey = new Map(obligations.map((item) => [item.obligation_key, item]));
  const rate = (value: string | null) => formatRate(value, { kind: "unit", currency });
  const explained = (key: string, measure: string, label: string, value: string, delta = false) => {
    const obligation = byKey.get(key);
    const money = <Money value={value} currency={currency} variant="cell" delta={delta} />;
    return obligation === undefined ? (
      money
    ) : (
      <ExplainTrigger
        figureRef={{
          objectType: "obligation",
          id: obligation.id,
          measure,
          book: context.book ?? undefined,
        }}
        label={`${label} · ${key}`}
        context={explainContext}
        valueText={moneyText(value, currency)}
      >
        {money}
      </ExplainTrigger>
    );
  };
  const headers = [
    ["obligation", false],
    ["product", false],
    ["source", false],
    ["low", true],
    ["mid", true],
    ["high", true],
    ["stated", true],
    ["range", false],
    ["selected", true],
    ["weight", true],
    ["allocated", true],
    ["adjustment", true],
  ] as const;
  return (
    <div className="overflow-x-auto">
      <StaticTable
        testId="SF-03-grid-allocation-walk"
        caption={t("contracts.workbench.allocation.caption", { currency })}
        headers={headers.map(([key, end]) => ({
          label: t(`contracts.allocation.column.${key}`),
          end,
        }))}
        footer={
          <tr className="border-t border-default font-semibold">
            <th scope="row" className="px-2 py-1 text-start">
              {t("contracts.workbench.total")}
            </th>
            <td colSpan={9} />
            <td className="px-2 py-1 text-end">
              <Money value={walk.data.totals.allocated.amount} currency={currency} variant="cell" />
            </td>
            <td className="px-2 py-1 text-end">
              <Money
                value={walk.data.totals.allocation_adjustment.amount}
                currency={currency}
                variant="cell"
                delta
              />
            </td>
          </tr>
        }
      >
        {walk.data.lines.map((line) => (
          <tr key={line.obligation_key} className="border-b border-hairline">
            <th scope="row" className="px-2 py-1 text-start font-mono text-mono-sm font-normal">
              {line.obligation_key}
            </th>
            <td className="px-2 py-1 font-mono text-mono-sm">{line.product.code}</td>
            <td className="px-2 py-1">
              {[
                line.ssp_book_version?.label ?? null,
                line.ssp_method === null ? null : t(`policies.ssp.method.${line.ssp_method}`),
              ]
                .filter((part): part is string => part !== null)
                .join(" · ") || NO_VALUE}
            </td>
            <td className="num px-2 py-1 text-end">{rate(line.low)}</td>
            <td className="num px-2 py-1 text-end">{rate(line.mid)}</td>
            <td className="num px-2 py-1 text-end">{rate(line.high)}</td>
            <td className="px-2 py-1 text-end">
              <Money
                value={line.stated_price.amount}
                currency={line.stated_price.currency}
                variant="cell"
              />
            </td>
            <td className="px-2 py-1">
              {rangePositionText(line.range_position, line.outside_range_point)}
            </td>
            <td className="px-2 py-1 text-end">
              {byKey.get(line.obligation_key) === undefined ? (
                <span className="num">{rate(line.selected_ssp)}</span>
              ) : (
                <ExplainTrigger
                  figureRef={{
                    objectType: "obligation",
                    id: byKey.get(line.obligation_key)?.id ?? "",
                    measure: "selected_ssp",
                    book: context.book ?? undefined,
                  }}
                  label={`${t("contracts.allocation.column.selected")} · ${line.obligation_key}`}
                  context={explainContext}
                  valueText={`${currency} ${rate(line.selected_ssp)}`}
                >
                  <span className="num">{rate(line.selected_ssp)}</span>
                </ExplainTrigger>
              )}
            </td>
            <td className="num px-2 py-1 text-end">
              {formatPercent(line.weight, { kind: "share" })}
            </td>
            <td className="px-2 py-1 text-end">
              {explained(
                line.obligation_key,
                "allocated_amount",
                t("contracts.allocation.column.allocated"),
                line.allocated.amount,
              )}
            </td>
            <td className="px-2 py-1 text-end">
              {explained(
                line.obligation_key,
                "allocation_adjustment",
                t("contracts.allocation.column.adjustment"),
                line.allocation_adjustment.amount,
                true,
              )}
            </td>
          </tr>
        ))}
      </StaticTable>
    </div>
  );
}

function Step5Evidence({
  contract,
  obligations,
  schedulesPath,
}: {
  readonly contract: Contract;
  readonly obligations: readonly Obligation[];
  readonly schedulesPath: string | null;
}) {
  const detail = stepOf(contract, "RECOGNITION")?.detail.obligations;
  const next = new Map<
    string,
    { readonly recognition_method?: string; readonly expected_date?: string | null }
  >(
    Array.isArray(detail)
      ? (
          detail as {
            readonly obligation_key: string;
            readonly next_trigger?: {
              readonly recognition_method?: string;
              readonly expected_date?: string | null;
            };
          }[]
        ).map((item) => [item.obligation_key, item.next_trigger ?? {}])
      : [],
  );
  const currency = contract.transaction_currency;
  return (
    <div className="flex flex-col gap-2">
      <StaticTable
        caption={t("contracts.workbench.step5.caption", { currency })}
        headers={[
          { label: t("contracts.workbench.step5.column.obligation") },
          { label: t("contracts.workbench.step5.column.pattern") },
          { label: t("contracts.workbench.kpi.recognized"), end: true },
          { label: t("contracts.workbench.kpi.scheduled"), end: true },
          { label: t("contracts.workbench.kpi.awaitingTrigger"), end: true },
          { label: t("contracts.workbench.step5.column.next") },
        ]}
      >
        {obligations.map((obligation) => {
          const trigger = next.get(obligation.obligation_key);
          const pattern = [
            t(`policies.template.satisfaction.${obligation.satisfaction_pattern}`),
            t(`policies.template.method.${obligation.recognition_method}`),
            obligation.ratable_convention === null
              ? null
              : t(`policies.template.convention.${obligation.ratable_convention}`),
          ]
            .filter((part): part is string => part !== null)
            .join(" · ");
          return (
            <tr key={obligation.id} className="border-b border-hairline">
              <th scope="row" className="px-2 py-1 text-start font-mono text-mono-sm font-normal">
                {obligation.obligation_key}
              </th>
              <td className="px-2 py-1">{pattern}</td>
              <td className="px-2 py-1 text-end">
                <Money
                  value={obligation.to_date.revenue.amount}
                  currency={currency}
                  variant="cell"
                />
              </td>
              <td className="px-2 py-1 text-end">
                <Money value={obligation.scheduled.amount} currency={currency} variant="cell" />
              </td>
              <td className="px-2 py-1 text-end">
                <Money
                  value={obligation.awaiting_trigger.amount}
                  currency={currency}
                  variant="cell"
                />
              </td>
              <td className="px-2 py-1">
                {trigger?.recognition_method === undefined
                  ? NO_VALUE
                  : [
                      t(`policies.template.method.${trigger.recognition_method}`),
                      trigger.expected_date === null || trigger.expected_date === undefined
                        ? null
                        : formatDate(trigger.expected_date),
                    ]
                      .filter((part): part is string => part !== null)
                      .join(" · ")}
              </td>
            </tr>
          );
        })}
      </StaticTable>
      {schedulesPath === null ? null : (
        <Link
          to={schedulesPath}
          className="text-body-sm underline decoration-control decoration-dotted underline-offset-3"
        >
          {t("contracts.workbench.step5.open")}
        </Link>
      )}
    </div>
  );
}

type OpenDrawer =
  | { readonly kind: "step1" }
  | {
      readonly kind: "assessment";
      readonly record: Judgement;
      /** Today in the contracting entity's time zone when the drawer opened (05 TZ-02). */
      readonly today: string;
    }
  | { readonly kind: "distinct"; readonly obligationKey: string }
  | {
      readonly kind: "event";
      readonly event: EventKind;
      readonly obligationKey?: string | undefined;
    }
  | { readonly kind: "hold"; readonly obligationKey?: string | undefined }
  | { readonly kind: "release"; readonly holdId?: string | undefined }
  | { readonly kind: "memos"; readonly obligationKey?: string | undefined }
  | { readonly kind: "combine" }
  | { readonly kind: "documents" }
  | { readonly kind: "dismiss"; readonly suggestion: CombinationSuggestion };

/** SCREENS §4.9.8 fix link of a failed activation checklist item. */
export type FixAction =
  "documents" | "step4" | "distinct" | "step1" | "step2" | "step1Review" | "editDraft" | null;

export function fixActionOf(code: string | null): FixAction {
  switch (code) {
    case "MANDATORY_FIELDS":
      return "editDraft";
    case "SOURCE_REFERENCE":
      return "documents";
    case "PRODUCT_TEMPLATE_SSP":
      return "step4";
    case "DISTINCT_REVIEW":
      return "distinct";
    case "COMBINATION_SUGGESTIONS":
      return "step1";
    case "STEP1_RECORD":
      return "step1Review";
    default:
      return null;
  }
}

/** 04 table 15.4-I: the checklist item of the contract's judgement records (PRD IMP-104, IMP-145). */
const JUDGEMENT_RECORDS_ITEM = "JUDGEMENT_RECORDS";

/**
 * The record a line of the checklist names by its number, among `records` (PRD IMP-145: "Judgement
 * record <judgement no> (<topic>) was rejected. …"). The number is looked for among the line's words,
 * so the line is found whatever else the API's sentence says.
 */
function recordNamed(message: string, records: readonly Judgement[]): Judgement | undefined {
  const words = new Set(message.split(/[\s()]+/));
  return records.find((record) => words.has(record.judgement_no));
}

/**
 * "Send for review" of a draft judgement record that a policy override names (SCREENS §4.9.8, rev
 * 1.76): `POST /judgements/{id}/submit`, the request the override's drawer sent for a new record
 * (§4.9.7; the drawer is withdrawn for release 1.0, rev 1.80, and an override that exists is still
 * read). It stands in the place of "Discard", for a holder of `judgement.create` for the
 * contract's entity — the API asks the permission of anyone, not of the record's creator alone. A
 * refusal is shown under the record's line.
 */
function SendForReview({
  record,
  contract,
}: {
  readonly record: Judgement;
  readonly contract: Pick<Contract, "contracting_entity">;
}) {
  const access = useAccess();
  const refresh = useRefreshRecord();
  const toast = useToast();
  const noAnswer = useNoAnswer();
  const keys = useCommandKeys();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  if (!access.holds(JUDGEMENT_CREATE_PERMISSION, contract.contracting_entity)) {
    return null;
  }

  const send = async () => {
    setBusy(true);
    setProblem(null);
    try {
      const outcome = await sendCommand<Judgement>(
        keys,
        "POST",
        `${JUDGEMENTS_PATH}/${record.id}/submit`,
        { comment: null },
      );
      if (!outcome.ok) {
        setProblem(outcome.problem);
        return;
      }
      toast.show({
        tone: "positive",
        message: t("contracts.judgement.sent", { number: record.judgement_no }),
      });
      await refresh();
    } catch {
      // No answer: the next press sends the submission under the same key (DG-FE-05).
      noAnswer();
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Button variant="link" loading={busy} onClick={() => void send()}>
        {t("contracts.judgement.send")}
      </Button>
      {problem === null ? null : (
        <div className="basis-full">
          <RefusalBanner problem={problem} headingLevel={3} />
        </div>
      )}
    </>
  );
}

function ActivationFailure({
  problem,
  contract,
  canEdit,
  onFix,
}: {
  readonly problem: ApiProblem;
  readonly contract: Contract;
  readonly canEdit: boolean;
  readonly onFix: (action: FixAction, message: string) => void;
}) {
  const lines = problem.errors.filter((error) => error.rule_id !== null);
  const requestOf = useRecordRequest(contract);
  // SCREENS §4.9.8: the checklist names each rejected record of the contract by its number, whatever
  // the record's subject, and the line carries "Discard" (rev 1.74) — before, such a line led
  // nowhere, and a record of a topic outside Step 1 had no command on any screen. A draft and a
  // record that waits for review it names by topic alone (PRD IMP-104): they are listed under that
  // line by number (rev 1.76). One read of the three statuses the item counts; the list route
  // filters no contract, so it is made only once a refusal names the item.
  const waitsForRecords = lines.some((line) => line.rule_id === JUDGEMENT_RECORDS_ITEM);
  const unreviewed = useQuery({
    queryKey: contractUnreviewedJudgementsKey(contract.id),
    queryFn: () => fetchUnreviewedJudgements(contract.id),
    enabled: waitsForRecords,
  });
  const records = unreviewed.data ?? [];
  // A draft that an override in force or waiting for approval names is sent for review and not
  // discarded: the override's approval certifies the record's id alone, and the override would keep
  // naming a record that can never be reviewed. The API refuses neither, so this rule is the whole
  // guard on the screens — and a draft takes no command at all until the contract's overrides are
  // read: a read that failed, or one the member may not make, answers nothing about the record.
  const overrides = useQuery({
    queryKey: contractOverridesKey(contract.id),
    queryFn: () => fetchContractOverrides(contract.id),
    enabled: waitsForRecords,
  });
  const standing = overrides.data === undefined ? null : recordsOfStandingOverrides(overrides.data);
  const rejected = records.filter((record) => record.status === "REJECTED");
  // The lines whose record was discarded from here, with the record's number: the banner stays as
  // the API answered it, and such a line says what happened in the command's place.
  const [discarded, setDiscarded] = useState<ReadonlyMap<string, string>>(new Map());
  // The drafts discarded from the list below, by id with their number: each stays in the list and
  // says so, as a rejected record's line does.
  const [dropped, setDropped] = useState<ReadonlyMap<string, string>>(new Map());
  // The item's last line that names no record: the line of a topic, under which the list stands. It
  // is one list for the item — the API prints its own title of a topic, which the screens do not
  // hold, so a record is told by its number and its conclusion and not by the line of its topic.
  const topicLines = lines.filter(
    (line) =>
      line.rule_id === JUDGEMENT_RECORDS_ITEM &&
      recordNamed(line.message, rejected) === undefined &&
      !discarded.has(line.message),
  );
  const listedUnder = topicLines[topicLines.length - 1];
  // The entries of the list by record id: a draft and a record that waits for review as they are
  // read, and a record discarded from the list in the place of what the read says of it.
  const entries = new Map<string, { number: string; record: Judgement | null }>();
  for (const record of records) {
    if (record.status !== "REJECTED") {
      entries.set(record.id, { number: record.judgement_no, record });
    }
  }
  for (const [id, number] of dropped) {
    entries.set(id, { number, record: null });
  }
  const waiting = [...entries]
    .map(([id, entry]) => ({ id, ...entry }))
    .sort((left, right) => (left.number < right.number ? -1 : 1));
  return (
    <Banner tone="negative" title={t("contracts.workbench.activation.failedTitle")} announce="live">
      {problem.detail === null ? null : <p>{problem.detail}</p>}
      <ul className="flex flex-col gap-1">
        {lines.map((line) => {
          const action = fixActionOf(line.rule_id);
          const shown = action === "editDraft" ? (canEdit ? action : null) : action;
          const named = recordNamed(line.message, rejected);
          const gone = discarded.get(line.message);
          return (
            <li
              key={`${line.rule_id ?? ""}:${line.message}`}
              className="flex flex-wrap items-baseline gap-2"
            >
              <span>{line.message}</span>
              {shown === null ? null : (
                <Button variant="link" onClick={() => onFix(shown, line.message)}>
                  {t(`contracts.workbench.activation.fix.${shown}`)}
                </Button>
              )}
              {named === undefined ? null : (
                <>
                  {/* Rev 1.76: the request, where the reviewer's reason stands. */}
                  <RecordRequestLink to={requestOf(named)} />
                  <DiscardRecord
                    record={named}
                    contract={contract}
                    invalidates={CONTRACT_RECORD_KEYS}
                    testId="SF-03-dialog-discard-record"
                    onDiscarded={() =>
                      setDiscarded((current) =>
                        new Map(current).set(line.message, named.judgement_no),
                      )
                    }
                  />
                </>
              )}
              {gone === undefined ? null : (
                <span className="text-fg-2">
                  {t("contracts.judgement.discarded", { number: gone })}
                </span>
              )}
              {line !== listedUnder || waiting.length === 0 ? null : (
                <ul
                  aria-label={t("contracts.workbench.activation.records")}
                  className="flex basis-full flex-col gap-1 ps-4"
                >
                  {waiting.map(({ id, number, record }) => (
                    <li key={id} className="flex flex-wrap items-baseline gap-x-2">
                      {record === null ? (
                        <span className="text-fg-2">
                          {t("contracts.judgement.discarded", { number })}
                        </span>
                      ) : (
                        <>
                          <span className="font-mono text-mono-sm">{number}</span>
                          <span>{record.conclusion}</span>
                          <span className="text-fg-2">{judgementStatusLabel(record.status)}</span>
                          <RecordRequestLink to={requestOf(record)} />
                          {record.status === "DRAFT" && standing !== null ? (
                            standing.has(id) ? (
                              <SendForReview record={record} contract={contract} />
                            ) : (
                              <DiscardRecord
                                record={record}
                                contract={contract}
                                invalidates={CONTRACT_RECORD_KEYS}
                                testId="SF-03-dialog-discard-record"
                                onDiscarded={() =>
                                  setDropped((current) => new Map(current).set(id, number))
                                }
                              />
                            )
                          ) : null}
                        </>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </Banner>
  );
}

function PageState({
  title,
  description,
  action,
}: {
  readonly title: string;
  readonly description: string;
  readonly action?: { readonly label: string; readonly onAction: () => void };
}) {
  return (
    <div data-testid="SF-03-page" className="flex max-w-120 flex-col items-start gap-2 pt-12">
      <h1 tabIndex={-1} className="text-title-lg text-fg-1">
        {title}
      </h1>
      <p className="text-body-sm text-fg-2">{description}</p>
      {action === undefined ? null : (
        <div className="mt-2">
          <Button variant="primary" onClick={action.onAction}>
            {action.label}
          </Button>
        </div>
      )}
    </div>
  );
}

export function ContractWorkbench() {
  const me = useMe();
  if (me.isError) {
    return <Banner tone="negative" title={me.error.message} />;
  }
  if (me.data === undefined) {
    return <Skeleton region={t("contracts.workbench.region")} shape="rows" count={8} />;
  }
  if (!me.data.permissions.includes(CONTRACT_READ_PERMISSION)) {
    return (
      <div data-testid="SF-03-page">
        <EmptyState
          title={t("settings.access.title", { area: t("contracts.access.area") })}
          description={t("settings.access.description", {
            permission: t("contracts.access.permission"),
          })}
          headingLevel={2}
        />
      </div>
    );
  }
  return <WorkbenchPage me={me.data} />;
}

function WorkbenchPage({ me }: { readonly me: Me }) {
  const params = useParams();
  const contractId = params.contractId ?? "";
  const obligationId = useMatch(OBLIGATION_ROUTE)?.params.obligationId ?? null;
  // SCREENS RT-14 to RT-16 (CTR-23): the tab routes render the frame with their own panels.
  const onSchedules = useMatch(SCHEDULES_ROUTE) !== null;
  const onBilling = useMatch(BILLING_ROUTE) !== null;
  const onJournals = useMatch(JOURNALS_ROUTE) !== null;
  // SCREENS RT-12 and RT-13 (CTR-25): the estimates workbench and its selected element.
  const onEstimateList = useMatch(ESTIMATES_ROUTE) !== null;
  const onEstimate = useMatch(ESTIMATE_ROUTE) !== null;
  const onEstimates = onEstimateList || onEstimate;
  // SCREENS RT-17 and RT-18 (CTR-24).
  const onModifications = useMatch(MODIFICATIONS_ROUTE) !== null;
  const onHistory = useMatch(HISTORY_ROUTE) !== null;
  const location = useLocation();
  const navigate = useNavigate();
  const toast = useToast();
  const noAnswer = useNoAnswer();
  // The keys of the commands this page sends outside a hook (DG-FE-05 rev 1.156).
  const keys = useCommandKeys();
  const refresh = useRefreshRecord();
  const built = useBuiltPaths();
  const access = useAccess();
  const permissions = me.permissions;
  const search = new URLSearchParams(location.search);
  const entity = search.get("entity");
  const period = search.get("period");
  const book = search.get("book");
  const knownAt = search.get("known_at");
  const hidden = knownAt !== null;
  const structure = permissions.includes(STRUCTURE_READ_PERMISSION);
  const canCreate = permissions.includes(CONTRACT_CREATE_PERMISSION);
  const canJudge = permissions.includes(JUDGEMENT_CREATE_PERMISSION);
  const canRecord = permissions.includes(EVENT_RECORD_PERMISSION);
  const ctxSearch = contextSearch(location.search);

  const periodQuery = { entity: entity ?? "", book: book ?? "" };
  const periodsEnabled = structure && entity !== null && book !== null;
  const periods = useQuery({
    queryKey: periodsKey(periodQuery),
    queryFn: () => fetchPeriods(periodQuery),
    enabled: periodsEnabled,
  });
  const asOf =
    periods.data?.find((item) => item.period.period_key === period)?.period.end_date ?? null;
  const contextReady = !periodsEnabled || period === null || !periods.isPending;
  const context: RecordContext = { book, asOf, knownAt };

  const contract = useQuery({
    queryKey: contractKey(contractId, context),
    queryFn: () => fetchContract(contractId, context),
    enabled: contextReady,
    // An answered refusal (not found, or a measure the trace cannot answer) is not asked again.
    retry: (count, error) =>
      !(error instanceof ApiProblem && (error.status === 404 || error.status === 422)) && count < 2,
  });
  const data = contract.data;
  const unreadable =
    contract.error instanceof ApiProblem &&
    contract.error.status === 422 &&
    contract.error.errors.some((error) => error.rule_id === UNREADABLE_RULE)
      ? contract.error
      : null;
  const obligations = useQuery({
    queryKey: contractObligationsKey(contractId, context),
    queryFn: () => fetchContractObligations(contractId, context),
    enabled: data !== undefined,
  });
  const suggestions = useQuery({
    queryKey: combinationSuggestionsKey(contractId),
    queryFn: () => fetchCombinationSuggestions(contractId),
    enabled: data !== undefined,
  });
  const documents = useQuery({
    queryKey: documentsKey(contractId),
    queryFn: () => fetchDocuments(contractId),
    enabled: data !== undefined,
  });
  const jobs = useQuery({
    queryKey: computeJobsKey(contractId),
    queryFn: () => fetchComputeJobs(contractId),
    enabled: data !== undefined,
    refetchInterval: (query) =>
      (query.state.data?.length ?? 0) > 0 ? JOB_POLL_INTERVAL_MS : false,
  });
  // SCREENS §8.2 tab count "Estimates <n>".
  const estimateCount = useQuery({
    queryKey: estimateCountKey(contractId),
    queryFn: () => fetchEstimateCount(contractId),
    enabled: data !== undefined && built.has(ESTIMATES_ROUTE),
  });
  // SCREENS §4.1.7 tab count "Modifications <n>".
  const modificationCount = useQuery({
    queryKey: modificationCountKey(contractId),
    queryFn: () => fetchModificationCount(contractId),
    enabled: data !== undefined && built.has(MODIFICATIONS_ROUTE),
  });
  const pending = useQuery({
    queryKey: pendingActivationKey(contractId),
    queryFn: () => fetchPendingActivation(contractId),
    enabled: data?.status === "PENDING_REVIEW",
  });
  const entities = useQuery({
    queryKey: entitiesKey(),
    queryFn: fetchActiveEntities,
    enabled: structure,
  });
  // SCREENS §4.1.3 Step 1 path (rev 1.11): the Step 1 records and the assessments of a contract that is
  // not activated yet.
  const onStep1Path = data?.status === "DRAFT" || data?.status === "NOT_A_CONTRACT";
  const step1Records = useQuery({
    queryKey: contractJudgementsKey(contractId),
    queryFn: () => fetchContractJudgements(contractId),
    enabled: onStep1Path,
  });
  const assessments = useQuery({
    queryKey: contractAssessmentsKey(contractId),
    queryFn: () => fetchContractAssessments(contractId),
    enabled: onStep1Path,
  });
  const lockQuery = { entity: data?.contracting_entity.code ?? "", book: book ?? "" };
  const lockPeriods = useQuery({
    queryKey: periodsKey(lockQuery),
    queryFn: () => fetchPeriods(lockQuery),
    enabled: structure && data !== undefined && book !== null,
  });
  const memberIds = (data?.combination_group.member_contract_ids ?? []).filter(
    (id) => id !== contractId,
  );
  const members = useQueries({
    queries: memberIds.map((id) => ({
      queryKey: contractKey(id, context),
      queryFn: () => fetchContract(id, context),
    })),
  });
  const firstSsp = obligations.data?.find((item) => item.ssp.book_version_id !== null)?.ssp;
  const sspLabel = useQuery({
    queryKey: sspVersionLabelKey(firstSsp?.book_version_id ?? ""),
    queryFn: () =>
      fetchSspVersionLabel(firstSsp?.book_version_id ?? "", firstSsp?.version_label ?? null),
    enabled: firstSsp !== undefined,
  });
  const submitActivation = useCommand<Contract>({
    method: "POST",
    path: `${CONTRACTS_PATH}/${contractId}/submit-activation`,
    invalidates: CONTRACT_RECORD_KEYS,
  });
  const [drawer, setDrawer] = useState<OpenDrawer | null>(null);
  const [activationProblem, setActivationProblem] = useState<ApiProblem | null>(null);
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState<ObligationSort>("key");

  const replaceParam = useCallback(
    (name: string, value: string | null) => {
      const next = new URLSearchParams(location.search);
      if (value === null) {
        next.delete(name);
      } else {
        next.set(name, value);
      }
      const text = next.toString();
      void navigate(
        { pathname: location.pathname, search: text === "" ? "" : `?${text}` },
        { replace: true },
      );
    },
    [location.pathname, location.search, navigate],
  );
  const loadExplanation = useCallback(
    async (figure: FigureRef) => (await fetchExplanation(figure)) as Explanation,
    [],
  );

  const stepParam = Number(search.get("step"));
  const openStep =
    Number.isInteger(stepParam) && stepParam >= 1 && stepParam <= 5 ? stepParam - 1 : null;
  const paneParam = search.get("pane");
  const paneTab: PaneTab = isPaneTab(paneParam) ? paneParam : "overview";

  let body: ReactNode;
  // SCREENS §6.3 list level: the lists the three to-date cells of the strip open.
  let explainLists: Readonly<Record<string, ExplainList>> | undefined;
  if (contract.isPending) {
    body = (
      <div data-testid="SF-03-page" className="flex flex-col gap-4" aria-busy="true">
        <RecordHeader
          title={t("contracts.workbench.region")}
          breadcrumb={[
            { label: t("contracts.workbench.breadcrumb"), to: `/contracts${ctxSearch}` },
          ]}
          tracker={<FiveStepTracker steps={[]} loading testIdScreen="SF-03" />}
          kpis={
            <KpiStrip
              loading
              heading={t("contracts.workbench.kpi.headingLoading")}
              kpis={[
                "transactionPrice",
                "billed",
                "recognized",
                "scheduled",
                "awaitingTrigger",
                "contractLiability",
              ].map((id) => ({
                id,
                label: t(`contracts.workbench.kpi.${id}`),
                value: null,
                currency: "USD",
              }))}
            />
          }
        />
      </div>
    );
  } else if (
    contract.isError &&
    contract.error instanceof ApiProblem &&
    contract.error.status === 404
  ) {
    body = (
      <PageState
        title={t("contracts.workbench.notFound")}
        description={t("errors.notFound.description")}
        action={{
          label: t("contracts.workbench.goToContracts"),
          onAction: () => void navigate(`/contracts${ctxSearch}`),
        }}
      />
    );
  } else if (unreadable !== null) {
    // 04 API-C-10 (rev 1.132): a to-date measure the version's trace cannot answer at the cut is
    // refused by name and no figure is served in its place. The screen says so, with what the API
    // names (contract, obligation or entity, measure, date); it is not a failed load.
    body = (
      <div data-testid="SF-03-page" className="flex flex-col gap-4">
        <h1 tabIndex={-1} className="text-title-lg text-fg-1">
          {t("contracts.workbench.region")}
        </h1>
        <div data-testid="SF-03-figures-unreadable">
          <Banner
            tone="warning"
            title={
              period === null
                ? t("contracts.workbench.unreadable.titleToday")
                : t("contracts.workbench.unreadable.title", {
                    period: contextPeriodLabel(periods.data ?? [], period),
                  })
            }
            headingLevel={2}
            announce="static"
          >
            {unreadable.errors
              .filter((error) => error.rule_id === UNREADABLE_RULE)
              .map((error) => (
                <p key={error.message}>{error.message}</p>
              ))}
            <p>{t("contracts.workbench.unreadable.next")}</p>
            {unreadable.requestId === null ? null : (
              <p>{t("contracts.drawer.reference", { reference: unreadable.requestId })}</p>
            )}
          </Banner>
        </div>
      </div>
    );
  } else if (contract.isError || data === undefined) {
    body = (
      <div data-testid="SF-03-page" className="flex flex-col gap-4">
        <h1 tabIndex={-1} className="text-title-lg text-fg-1">
          {t("contracts.workbench.region")}
        </h1>
        <RetryBanner
          title={t("contracts.workbench.loadError")}
          onRetry={() => void contract.refetch()}
          problem={contract.error}
        />
      </div>
    );
  } else {
    const items = obligations.data ?? NO_OBLIGATIONS;
    const openSuggestions = (suggestions.data ?? []).filter(
      (item) => item.status === "OPEN" || item.status === "IN_PROGRESS",
    );
    const memberExternalIds = members
      .map((member) => member.data?.external_id)
      .filter((id): id is string => id !== undefined);
    const contractingEntity = entities.data?.find(
      (item) => item.code === data.contracting_entity.code,
    );
    const enabledBooks =
      contractingEntity?.books.filter((item) => item.is_enabled).map((item) => item.book_code) ??
      [];
    const books = enabledBooks.length > 0 ? enabledBooks : [book ?? data.context?.book ?? "ASC606"];
    // 05 TZ-02: the effective date of an event is a date of the contracting entity.
    const openAssessment = (record: Judgement) =>
      setDrawer({
        kind: "assessment",
        record,
        today: currentDateIn(contractingEntity?.time_zone ?? "UTC", Date.now()),
      });
    const path =
      onStep1Path && step1Records.data !== undefined && assessments.data !== undefined
        ? step1Path(step1Records.data, assessments.data, books)
        : null;
    const next = path === null ? null : step1Next(data, path);
    const lines = trackerLines(data, {
      suggestions: openSuggestions,
      members: memberExternalIds,
      obligations: items,
      sspLabel: sspLabel.data?.label ?? firstSsp?.version_label ?? null,
      sspLabelPending: obligations.isPending || (firstSsp !== undefined && sspLabel.isPending),
      step1: path,
    });
    const currency = data.transaction_currency;
    const versionId = data.context?.contract_version_id ?? null;
    const label = bookLabel(book ?? data.context?.book);
    const explainContext = [data.external_id, label, data.contracting_entity.code].join(" · ");
    const schedulesPath = built.has(SCHEDULES_ROUTE)
      ? `/contracts/${data.id}/schedules${ctxSearch}`
      : null;
    const obligationsPath = `/contracts/${data.id}/obligations${ctxSearch}`;

    const onFix = (action: FixAction, message: string) => {
      switch (action) {
        case "documents":
          setDrawer({ kind: "documents" });
          return;
        case "step4":
          replaceParam("step", "4");
          return;
        case "step1":
          replaceParam("step", "1");
          return;
        case "step2":
          replaceParam("step", "2");
          return;
        case "step1Review":
          // The command the Step 1 path offers; while the record waits for review, its line.
          if (path?.kind === "reviewed") {
            openAssessment(path.record);
          } else if (path?.kind === "waiting") {
            replaceParam("step", "1");
          } else {
            setDrawer({ kind: "step1" });
          }
          return;
        case "distinct": {
          const key = /for (\S+) \(/.exec(message)?.[1];
          if (key !== undefined && items.some((item) => item.obligation_key === key)) {
            setDrawer({ kind: "distinct", obligationKey: key });
          } else {
            replaceParam("step", "2");
          }
          return;
        }
        case "editDraft":
          void navigate(`/contracts/${data.id}/edit${ctxSearch}`);
          return;
        default:
          return;
      }
    };

    const submit = async () => {
      setActivationProblem(null);
      const outcome = await submitActivation.submit(
        {},
        { ifMatch: contractIfMatch(data.head_stream_version) },
      );
      if (outcome.kind === "succeeded") {
        const requestId = outcome.response.headers.get(APPROVAL_REQUEST_HEADER);
        toast.show({
          tone: "positive",
          message:
            outcome.data?.status === "ACTIVE" || requestId === null
              ? t("contracts.workbench.activation.activated")
              : t("contracts.workbench.activation.submitted", {
                  request: await requestNumber(requestId),
                }),
        });
      } else if (outcome.kind === "failed") {
        setActivationProblem(outcome.problem);
      } else if (outcome.kind === "network-error") {
        toast.show({ tone: "negative", message: t("contracts.list.bulk.notReached") });
      }
    };

    const withdraw = async (request: ApprovalItem) => {
      try {
        const outcome = await sendCommand(
          keys,
          "POST",
          `/api/v1/approvals/${request.id}/withdraw`,
          { comment: null },
        );
        if (outcome.ok) {
          await refresh();
          toast.show({ tone: "positive", message: t("contracts.workbench.banner.withdrawn") });
        } else {
          toast.show({ tone: "negative", message: outcome.problem.title });
        }
      } catch {
        // No answer: the next press sends the withdrawal under the same key (DG-FE-05).
        noAnswer();
      }
    };

    // SCREENS §4.1.3 Step 1 path (rev 1.11): the command that comes next, for a viewer who may run it,
    // and the pending review request for a viewer who may open it.
    const canReview = !hidden && canCreate && canJudge;
    let step1Command: { readonly label: string; readonly onSelect: () => void } | null = null;
    if (next?.command === "review" && canReview) {
      step1Command = {
        label: t("contracts.drawer.step1.title"),
        onSelect: () => setDrawer({ kind: "step1" }),
      };
    } else if (
      (next?.command === "assessment" || next?.command === "criteriaMet") &&
      canReview &&
      path?.kind === "reviewed"
    ) {
      const record = path.record;
      step1Command = {
        label: t(`contracts.drawer.assessment.title.${next.command}`),
        onSelect: () => openAssessment(record),
      };
    } else if (next?.command === "submit" && !hidden && canCreate) {
      step1Command = {
        label: t("contracts.list.bulk.submit"),
        onSelect: () => void submit(),
      };
    }
    const waiting = next?.waiting ?? null;
    const step1Request =
      waiting !== null &&
      waiting.approval_request_id !== null &&
      built.has(REQUEST_ROUTE) &&
      (permissions.includes(JUDGEMENT_REVIEW_PERMISSION) || waiting.created_by.id === me.user.id)
        ? `/approvals/requests/${waiting.approval_request_id}`
        : null;
    const pathFailed = onStep1Path && (step1Records.isError || assessments.isError);
    const retryPath = () => {
      void step1Records.refetch();
      void assessments.refetch();
    };
    let step1Line: ReactNode = null;
    if (pathFailed) {
      step1Line = (
        <RetryBanner
          title={t("contracts.workbench.step1.pathError")}
          onRetry={retryPath}
          problem={step1Records.error ?? assessments.error}
        />
      );
    } else if (next !== null) {
      step1Line = <Step1PathLine next={next} command={step1Command} request={step1Request} />;
    }

    // SCREENS §4.1.5: at most one banner; a refused activation takes the slot.
    let banner: ReactNode = null;
    const lockedPeriod = lockPeriods.data?.find((item) => item.period.period_key === period);
    const firstOpen = lockPeriods.data?.find((item) => item.is_first_open);
    const pendingRequest = pending.data ?? null;
    if (activationProblem !== null) {
      banner =
        activationProblem.slug === ACTIVATION_CHECKLIST_FAILED ? (
          <ActivationFailure
            problem={activationProblem}
            contract={data}
            canEdit={built.has(EDIT_ROUTE) && canCreate}
            onFix={onFix}
          />
        ) : (
          <Banner tone="negative" title={activationProblem.title} announce="live">
            {activationProblem.detail === null ? null : <p>{activationProblem.detail}</p>}
          </Banner>
        );
    } else if (data.status === "PENDING_REVIEW") {
      banner = (
        <Banner
          tone="info"
          title={t("contracts.workbench.banner.activationPending")}
          actions={
            pendingRequest === null ? undefined : (
              <span className="flex gap-3">
                {built.has(REQUEST_ROUTE) ? (
                  <Link
                    to={`/approvals/requests/${pendingRequest.id}`}
                    className="text-body-sm text-accent-fg hover:underline"
                  >
                    {t("contracts.workbench.banner.viewRequest")}
                  </Link>
                ) : null}
                {!hidden && pendingRequest.preparer.id === me.user.id ? (
                  <Button variant="link" onClick={() => void withdraw(pendingRequest)}>
                    {t("contracts.workbench.banner.withdraw")}
                  </Button>
                ) : null}
              </span>
            )
          }
        />
      );
    } else if ((jobs.data ?? []).length > 0) {
      const running = (jobs.data ?? []).some((job) => job.state === "RUNNING");
      banner = (
        <Banner tone="info" title={t("contracts.workbench.banner.stale")}>
          <StatusChip status={running ? "Running" : "Queued"} />
        </Banner>
      );
    } else if (
      lockedPeriod !== undefined &&
      (lockedPeriod.state === "closed" || lockedPeriod.state === "permanently_locked")
    ) {
      banner = (
        <Banner
          tone="info"
          title={t("contracts.workbench.banner.locked", {
            period: periodLabel(lockedPeriod.period),
            entity: data.contracting_entity.code,
            open: firstOpen === undefined ? NO_VALUE : periodLabel(firstOpen.period),
          })}
        />
      );
    } else if (data.status === "NOT_A_CONTRACT") {
      banner = (
        <Banner
          tone="warning"
          title={t("contracts.workbench.banner.notAContract")}
          actions={
            step1Command !== null ? (
              <Button variant="link" onClick={step1Command.onSelect}>
                {step1Command.label}
              </Button>
            ) : step1Request !== null ? (
              <Link to={step1Request} className="text-body-sm text-accent-fg hover:underline">
                {t("contracts.workbench.banner.viewRequest")}
              </Link>
            ) : pathFailed ? (
              <Button variant="link" onClick={retryPath}>
                {t("common.grid.retry")}
              </Button>
            ) : undefined
          }
        >
          {pathFailed ? (
            <p>{t("contracts.workbench.step1.pathError")}</p>
          ) : next === null ? null : (
            <p>{next.line}</p>
          )}
        </Banner>
      );
    }

    // SCREENS §4.1.6 commands by status.
    const statusChip = chipFor("E-17", data.status);
    const documentCount = documents.data?.total?.count ?? documents.data?.items.length ?? 0;
    const documentsButton = (
      <Button variant="secondary" size="sm" onClick={() => setDrawer({ kind: "documents" })}>
        {t("contracts.workbench.action.documents", {
          count: formatNumber(documentCount, { kind: "count" }),
        })}
      </Button>
    );
    const copyLink: MenuItem = {
      id: "copy-link",
      label: t("contracts.list.row.copyLink"),
      onSelect: () => {
        void navigator.clipboard
          .writeText(globalThis.location.href)
          .then(() => toast.show({ tone: "neutral", message: t("contracts.list.row.copied") }));
      },
    };
    const overflow: MenuItem[] = [];
    let primary: ReactNode = null;
    // SCREENS §4.1.6 DRAFT secondary "Edit draft" (SF-03:edit).
    let editDraft: ReactNode = null;
    // SCREENS §4.1.6 ACTIVE secondary "Change subscription" (SF-07 with `action`).
    let changeSubscription: ReactNode = null;
    if (!hidden) {
      if (data.status === "DRAFT") {
        if (canCreate && built.has(EDIT_ROUTE)) {
          editDraft = (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void navigate(`/contracts/${data.id}/edit${ctxSearch}`)}
            >
              {t("contracts.workbench.action.editDraft")}
            </Button>
          );
        }
        if (canCreate) {
          primary = (
            <Button
              variant="primary"
              size="sm"
              loading={submitActivation.pending}
              onClick={() => void submit()}
            >
              {t("contracts.list.bulk.submit")}
            </Button>
          );
          // The Step 1 path: a review, or the assessment of a reviewed record; a new review also
          // once the assessment is recorded. None while a record waits for review. Beside the
          // assessment stands a new review (rev 1.72): the API may refuse the reviewed record —
          // it was reviewed before the draft was last replaced (ruling R-102 (c)) — and no read
          // tells the screen before the attempt, so a new review is never out of reach.
          if (canJudge && next !== null && next.command !== null) {
            if (step1Command !== null && next.command !== "review" && next.command !== "submit") {
              overflow.push({
                id: "step1-assessment",
                label: step1Command.label,
                onSelect: step1Command.onSelect,
              });
            }
            overflow.push({
              id: "step1",
              label: t("contracts.drawer.step1.title"),
              onSelect: () => setDrawer({ kind: "step1" }),
            });
          }
          overflow.push({
            id: "combine",
            label: t("contracts.drawer.combine.title"),
            onSelect: () => setDrawer({ kind: "combine" }),
          });
        }
      } else if (data.status === "NOT_A_CONTRACT") {
        // The command of the Step 1 path; none while its record waits for review.
        if (step1Command !== null) {
          primary = (
            <Button
              variant="primary"
              size="sm"
              loading={next?.command === "submit" && submitActivation.pending}
              onClick={step1Command.onSelect}
            >
              {step1Command.label}
            </Button>
          );
        }
      } else if (data.status === "ACTIVE" || data.status === "COMPLETED") {
        if (
          acceptsModifications(data) &&
          built.has(MODIFICATION_NEW_ROUTE) &&
          me.permissions.includes(MODIFICATION_CREATE_PERMISSION)
        ) {
          primary = (
            <Button
              variant="primary"
              size="sm"
              onClick={() => void navigate(newModificationHref(data.id, ctxSearch))}
            >
              {t("contracts.workbench.action.newModification")}
            </Button>
          );
          changeSubscription = (
            <Menu
              label={t("contracts.workbench.action.changeSubscription")}
              size="sm"
              align="end"
              items={SUBSCRIPTION_ACTIONS.map((action) => ({
                id: action,
                label: t(`contracts.workbench.subscription.${action}`),
                onSelect: () => void navigate(newModificationHref(data.id, ctxSearch, action)),
              }))}
            />
          );
        }
        if (canRecord) {
          for (const kind of EVENT_KINDS) {
            overflow.push({
              id: `event-${kind}`,
              label: t(`contracts.drawer.event.title.${kind}`),
              onSelect: () => setDrawer({ kind: "event", event: kind }),
            });
          }
        }
        // The commands of a holder of `contract.create`. "Request policy override" is not one of
        // them (SCREENS §4.9.7 rev 1.80; supervisor ruling R-126 (c)): release 1.0 takes no policy
        // override, and the API refuses its creation.
        if (canCreate) {
          overflow.push(
            {
              id: "hold",
              label: t("contracts.list.bulk.hold"),
              onSelect: () => setDrawer({ kind: "hold" }),
            },
            {
              id: "memos",
              label: t("contracts.drawer.memos.title"),
              onSelect: () => setDrawer({ kind: "memos" }),
            },
            {
              id: "combine",
              label: t("contracts.drawer.combine.title"),
              onSelect: () => setDrawer({ kind: "combine" }),
            },
          );
        }
      }
    }
    // SCREENS §4.1.6 (rev 1.75): "Release hold" while the contract is on hold, whatever its status —
    // a hold is applied on a draft too, and a hold of the whole contract is listed by the contract's
    // read alone — behind "Apply hold" where that stands. For a holder of `contract.create` for the
    // contract's entity (04 API-R-28; asked of the access module). Which hold is released by hand is
    // the API's to say: the drawer lists each with the sentence of the one that is not.
    if (
      !hidden &&
      data.on_hold &&
      access.holds(CONTRACT_CREATE_PERMISSION, data.contracting_entity)
    ) {
      const applies = overflow.findIndex((item) => item.id === "hold");
      overflow.splice(applies === -1 ? overflow.length : applies + 1, 0, {
        id: "release-hold",
        label: t("contracts.drawer.release.title"),
        onSelect: () => setDrawer({ kind: "release" }),
      });
    }
    overflow.push(copyLink);
    const actions = (
      <>
        {editDraft}
        {changeSubscription}
        {documentsButton}
        {primary}
        <Menu
          label={t("contracts.workbench.action.more")}
          icon={DotsThree}
          iconOnly
          variant="ghost"
          size="sm"
          align="end"
          items={overflow}
        />
      </>
    );

    const computedAt = data.context?.computed_at ?? null;
    // The period the to-date figures were measured at, named only when it ends before the context
    // period (04 API-C-10: a read beyond the version's horizon answers at the horizon).
    const measuredPeriod = data.context?.measured_period ?? null;
    // Its label in the contracting entity's calendar, then in the context entity's.
    const calendars = [...(lockPeriods.data ?? []), ...(periods.data ?? [])];
    const measuredLabel =
      measuredPeriod === null ? null : contextPeriodLabel(calendars, measuredPeriod.period_key);
    const measuredBefore =
      measuredPeriod === null || asOf === null || measuredPeriod.end_date >= asOf
        ? null
        : measuredLabel;
    const metaRows: readonly (MetaItem | null)[] = [
      { label: t("contracts.workbench.meta.customer"), value: data.customer.name },
      {
        label: t("contracts.workbench.meta.entity"),
        value: `${data.contracting_entity.code} · ${data.contracting_entity.name}`,
      },
      { label: t("contracts.workbench.meta.currency"), value: currency },
      { label: t("contracts.workbench.meta.inception"), value: formatDate(data.inception_date) },
      data.signature_date === null
        ? null
        : {
            label: t("contracts.workbench.meta.signature"),
            value: formatDate(data.signature_date),
          },
      data.payment_terms === null || data.payment_terms === ""
        ? null
        : { label: t("contracts.workbench.meta.paymentTerms"), value: data.payment_terms },
      {
        label: t("contracts.workbench.meta.source"),
        value: t(`contracts.workbench.source.${data.source_system}`),
      },
      {
        label: t("contracts.workbench.meta.contractNo"),
        value: <span className="font-mono text-mono-sm">{data.contract_no}</span>,
      },
      // SCREENS §4.1.2 (rev 1.10): the time of the computation that produced the version in
      // context, not `known_at`, the read's record cut-off.
      computedAt === null
        ? null
        : {
            label: t("contracts.workbench.meta.lastComputed"),
            value: <span data-volatile="">{formatTimestamp(computedAt)}</span>,
          },
      // The to-date figures were measured at the version's horizon, a period before the context's.
      measuredBefore === null
        ? null
        : {
            label: t("contracts.workbench.meta.figuresAsOf"),
            value: (
              <span data-testid="SF-03-figures-as-of" className="inline-flex items-center gap-1">
                {measuredBefore}
                {/* DS-CMP-26 stale marker: an Info icon whose tooltip says what the period is. The
                    negative block margin keeps the row's text on the baseline of its neighbours. */}
                <span className="-my-1.5 inline-flex">
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={Info}
                    aria-label={t("contracts.workbench.meta.figuresAsOfNote", {
                      period: measuredBefore,
                    })}
                  />
                </span>
              </span>
            ),
          },
    ];
    const meta = metaRows.filter((item): item is MetaItem => item !== null);

    const chips = (
      <>
        {statusChip === null ? null : <StatusChip status={statusChip.status} />}
        {data.on_hold ? <StatusChip status="On hold" /> : null}
        {data.combination_group.is_singleton ? null : (
          <OutlineChip label={t("contracts.list.combined")} />
        )}
        {data.context === null ? null : (
          <OutlineChip
            label={
              hidden
                ? t("contracts.workbench.versionKnownAt", {
                    version: formatNumber(data.context.version_no, { kind: "count" }),
                    timestamp: formatTimestamp(data.context.known_at),
                  })
                : t("contracts.workbench.version", {
                    version: formatNumber(data.context.version_no, { kind: "count" }),
                  })
            }
          />
        )}
      </>
    );

    const trackerSteps: TrackerStep[] = lines.map((line, index) => {
      let evidence: ReactNode = null;
      switch (index) {
        case 0:
          evidence = (
            <Step1Evidence
              contract={data}
              suggestions={openSuggestions}
              members={memberExternalIds}
              commands={{ combine: !hidden && canCreate, discard: !hidden }}
              path={step1Line}
              onCombine={() => setDrawer({ kind: "combine" })}
              onDismiss={(suggestion) => setDrawer({ kind: "dismiss", suggestion })}
            />
          );
          break;
        case 1:
          evidence = (
            <Step2Evidence
              contract={data}
              obligations={items}
              canReview={!hidden && canJudge}
              onReview={(obligation) =>
                setDrawer({ kind: "distinct", obligationKey: obligation.obligation_key })
              }
            />
          );
          break;
        case 2:
          evidence = <Step3Evidence contract={data} book={book} />;
          break;
        case 3:
          evidence = (
            <AllocationWalkTable
              contract={data}
              context={context}
              obligations={items}
              explainContext={explainContext}
            />
          );
          break;
        default:
          evidence = (
            <Step5Evidence contract={data} obligations={items} schedulesPath={schedulesPath} />
          );
      }
      return { state: line.state, status: line.status, busy: line.busy, evidence };
    });

    const kpis = data.kpis;
    const ratios = data.kpis_ratios;
    const cell = (
      id: string,
      measure: string,
      value: string | null,
      extra: Partial<Kpi> = {},
    ): Kpi => {
      const figureRef: FigureRef | undefined =
        versionId === null || value === null
          ? undefined
          : { objectType: "contract_version", id: versionId, measure, book: book ?? undefined };
      return {
        id,
        label: t(`contracts.workbench.kpi.${id}`),
        value,
        currency,
        testId: `SF-03-kpi-${measure.replace(/_/g, "-")}`,
        explain: figureRef === undefined ? undefined : { figureRef, context: explainContext },
        ...extra,
      };
    };
    // SCREENS §4.1.4 (rev 1.21): the trace holds no contract-level node per period for Billed,
    // Recognized and Scheduled, so their cells open the list level of §6.3 under the cell's id.
    const listCell = (
      id: string,
      measure: string,
      value: string | null,
      extra: Partial<Kpi> = {},
    ) => ({
      ...cell(id, measure, value, extra),
      explain: value === null ? undefined : { list: id },
    });
    const toDateList = (
      measure: "billed_to_date" | "revenue_to_date" | "scheduled",
      value: string,
      amounts: "billed" | "revenue",
      sentences: { readonly intro?: string; readonly payable: boolean },
    ): ExplainList => {
      const amountLabel = t(
        amounts === "billed" ? "explain.measure.billed_to_date" : "explain.measure.revenue_to_date",
      );
      const name = t(`explain.measure.${measure}`);
      return {
        label: measuredLabel === null ? name : `${name} · ${measuredLabel}`,
        value,
        currency,
        context: explainContext,
        caption: t("contracts.workbench.explainList.caption"),
        columns: { entry: t("contracts.workbench.explainList.obligation"), amount: amountLabel },
        rows: obligations.data?.map((obligation) => {
          const figure = figureFromLink(
            amounts === "billed"
              ? (obligation.links.explain_billed_to_date ?? null)
              : obligation.links.explain_revenue_to_date,
            book,
          );
          const amount = obligation.to_date[amounts];
          return {
            id: obligation.id,
            label: `${obligation.obligation_key} · ${obligation.product.code}`,
            amount: amount.amount,
            currency: amount.currency,
            explain:
              figure === undefined
                ? undefined
                : {
                    request: {
                      figure,
                      // Named apart from the list above it in the path. The period is the one the
                      // link carries: the billing node's is one of the contracting entity's
                      // (SCREENS §4.1.4).
                      label: [
                        amountLabel,
                        obligation.obligation_key,
                        ...(figure.periodKey === undefined
                          ? []
                          : [contextPeriodLabel(calendars, figure.periodKey)]),
                      ].join(" · "),
                      context: [
                        data.external_id,
                        obligation.obligation_key,
                        label,
                        data.contracting_entity.code,
                      ].join(" · "),
                    },
                    label: t("common.explain.explainInput", { name: obligation.obligation_key }),
                  },
          };
        }),
        error: obligations.isError
          ? {
              title: t("contracts.workbench.obligations.loadError"),
              onRetry: () => void obligations.refetch(),
            }
          : undefined,
        empty: t("contracts.workbench.obligations.emptyTitle"),
        intro: sentences.intro,
        notes: sentences.payable ? <ConsiderationPayableNote contract={data} book={book} /> : null,
      };
    };
    if (kpis !== null) {
      explainLists = {
        billed: toDateList("billed_to_date", kpis.billed_to_date.amount, "billed", {
          payable: false,
        }),
        recognized: toDateList("revenue_to_date", kpis.revenue_to_date.amount, "revenue", {
          payable: true,
        }),
        scheduled: toDateList("scheduled", kpis.scheduled.amount, "revenue", {
          intro: t("contracts.workbench.explainList.scheduled"),
          payable: false,
        }),
      };
    }
    const withBar = (ratio: string | null) =>
      ratio === null
        ? {}
        : {
            bar: { ratio, overLabel: t("contracts.workbench.kpi.over") },
            secondary: t("contracts.workbench.kpi.ofTransactionPrice", {
              ratio: formatPercent(ratio),
            }),
          };
    const balances = kpis?.balances ?? [];
    const balance =
      balances.find((item) => item.entity.code === entity) ??
      balances.find((item) => item.entity.code === data.contracting_entity.code) ??
      balances[0];
    // §4.1.4 (rev 1.24): the entry names the explanation of its three figures — the balance row at
    // the period it was read at — and a figure it names none for has no trigger.
    const figureOf = (measure: string): FigureRef | undefined =>
      balanceFigure(balance?.links, measure, book);
    const liabilityFigure = figureOf("contract_liability");
    const secondaryTrigger = (measure: string, labelKey: string, value: string) => {
      const figure = figureOf(measure);
      // DS-CMP-06: digits without the code, which the heading carries; the name keeps the code.
      const money = <Money value={value} currency={currency} variant="cell" />;
      return figure === undefined ? (
        money
      ) : (
        <ExplainTrigger
          figureRef={figure}
          label={t(labelKey)}
          context={explainContext}
          valueText={moneyText(value, currency)}
        >
          {money}
        </ExplainTrigger>
      );
    };
    const liability: Kpi = {
      id: "contractLiability",
      label: t("contracts.workbench.kpi.contractLiability"),
      value: balance?.contract_liability.amount ?? null,
      currency,
      testId: "SF-03-kpi-contract-liability",
      explain:
        liabilityFigure === undefined
          ? undefined
          : { figureRef: liabilityFigure, context: explainContext },
      secondary:
        balance === undefined ? undefined : (
          <span className="flex flex-col items-start gap-y-2">
            {/* One label and figure per line: the Explain triggers keep their 24 px spacing
                (WCAG 2.5.8, axe target-size) in the narrow cell. */}
            <span className="inline-flex items-baseline gap-1 whitespace-nowrap">
              <span>{t("contracts.workbench.kpi.contractAsset")}</span>
              {secondaryTrigger(
                "contract_asset",
                "contracts.workbench.kpi.contractAsset",
                balance.contract_asset.amount,
              )}
            </span>
            <span className="inline-flex items-baseline gap-1 whitespace-nowrap">
              <span>{t("contracts.workbench.kpi.unbilledReceivable")}</span>
              {secondaryTrigger(
                "unbilled_receivable",
                "contracts.workbench.kpi.unbilledReceivable",
                balance.unbilled_receivable.amount,
              )}
            </span>
            {balances.length > 1 ? (
              <span className="whitespace-nowrap">
                {built.has(BILLING_ROUTE) ? (
                  <Link
                    to={`/contracts/${data.id}/billing${ctxSearch}`}
                    className="underline decoration-control decoration-dotted underline-offset-3"
                  >
                    {t("contracts.workbench.kpi.entities", {
                      count: formatNumber(balances.length, { kind: "count" }),
                    })}
                  </Link>
                ) : (
                  <span>
                    {t("contracts.workbench.kpi.entities", {
                      count: formatNumber(balances.length, { kind: "count" }),
                    })}
                  </span>
                )}
              </span>
            ) : null}
          </span>
        ),
    };
    const strip: Kpi[] = [
      {
        ...cell("transactionPrice", "transaction_price", kpis?.transaction_price.amount ?? null),
        explain:
          kpis === null
            ? undefined
            : {
                figureRef:
                  figureFromLink(data.links.explain_transaction_price, book) ??
                  ({
                    objectType: "contract_version",
                    id: versionId ?? "",
                    measure: "transaction_price",
                  } as FigureRef),
                context: explainContext,
              },
      },
      listCell(
        "billed",
        "billed_to_date",
        kpis?.billed_to_date.amount ?? null,
        kpis === null ? {} : withBar(ratios.billed),
      ),
      listCell(
        "recognized",
        "revenue_to_date",
        kpis?.revenue_to_date.amount ?? null,
        kpis === null ? {} : withBar(ratios.recognized),
      ),
      listCell("scheduled", "scheduled", kpis?.scheduled.amount ?? null),
      cell(
        "awaitingTrigger",
        "awaiting_trigger",
        kpis?.awaiting_trigger.amount ?? null,
        ratios.pending_trigger_count > 0
          ? {
              secondary: t("contracts.workbench.kpi.triggersPending", {
                count: ratios.pending_trigger_count,
                formatted: formatNumber(ratios.pending_trigger_count, { kind: "count" }),
              }),
            }
          : {},
      ),
      liability,
    ];

    const tabRoutes: readonly (readonly [string, string])[] = [
      [ESTIMATES_ROUTE, "estimates"],
      [SCHEDULES_ROUTE, "schedules"],
      [BILLING_ROUTE, "billing"],
      [JOURNALS_ROUTE, "journals"],
      [MODIFICATIONS_ROUTE, "modifications"],
      [HISTORY_ROUTE, "history"],
    ];
    const tabs: RouteTab[] = [
      {
        id: "obligations",
        label: t("contracts.workbench.tabs.obligations"),
        count: obligations.data?.length,
        to: obligationsPath,
      },
      ...tabRoutes
        .filter(([route]) => built.has(route))
        .map(([, id]) => ({
          id,
          label: t(`contracts.workbench.tabs.${id}`),
          count:
            id === "modifications"
              ? (modificationCount.data ?? undefined)
              : id === "estimates"
                ? (estimateCount.data ?? undefined)
                : undefined,
          to: `/contracts/${data.id}/${id}${ctxSearch}`,
        })),
    ];

    const filtered = sortObligations(
      items.filter((item) => matchesObligation(item, filter)),
      sort,
    );
    const masterItems: MasterItem[] = filtered.map((item) => ({
      id: item.id,
      name: item.product.name,
      amount: (
        <span className="num text-body text-fg-1">
          {formatMoney(item.current.allocated_amount.amount, item.currency)}
        </span>
      ),
      identifier: item.obligation_key,
      chips: <ObligationChips obligation={item} />,
      dateRange: dateRange(item.start_date, item.end_date),
      optionLabel: `${item.product.name}, ${item.obligation_key}`,
      testId: `SF-03-row-${testIdKey(item.obligation_key)}`,
    }));
    const selected = items.find((item) => item.id === obligationId);
    const sortLabels: Readonly<Record<ObligationSort, string>> = {
      key: t("contracts.workbench.obligations.sort.key"),
      start: t("contracts.workbench.obligations.sort.start"),
      product: t("contracts.workbench.obligations.sort.product"),
    };
    const paneSearch = (tab: PaneTab | null) => {
      const next = new URLSearchParams(ctxSearch);
      if (tab !== null && tab !== "overview") {
        next.set("pane", tab);
      }
      const text = next.toString();
      return text === "" ? "" : `?${text}`;
    };
    const onPaneCommand = (command: PaneCommand) => {
      switch (command.kind) {
        case "record-event":
          setDrawer({ kind: "event", event: command.event, obligationKey: command.obligationKey });
          return;
        case "apply-hold":
          setDrawer({ kind: "hold", obligationKey: command.obligationKey });
          return;
        case "edit-memos":
          setDrawer({ kind: "memos", obligationKey: command.obligationKey });
          return;
        case "release-hold":
          setDrawer({ kind: "release", holdId: command.holdId });
          return;
      }
    };
    const tabHeadingId = `contract-tab-obligations-${data.id}`;
    const tabProps: WorkbenchTabProps = {
      contract: data,
      context,
      obligations: items,
      obligationsLoading: obligations.isPending,
      explainContext,
      me,
      ctxSearch,
    };

    body = (
      <div data-testid="SF-03-page" className="flex flex-col gap-4">
        {hidden ? (
          <Banner
            tone="info"
            title={t("contracts.workbench.banner.knownAt", { timestamp: formatTimestamp(knownAt) })}
            actions={
              <Button variant="link" onClick={() => replaceParam("known_at", null)}>
                {t("contracts.workbench.banner.showCurrent")}
              </Button>
            }
          />
        ) : null}
        <RecordHeader
          title={data.customer.name}
          breadcrumb={[
            { label: t("contracts.workbench.breadcrumb"), to: `/contracts${ctxSearch}` },
          ]}
          identifier={{
            value: data.external_id,
            copyLabel: t("contracts.workbench.copyId"),
            copiedMessage: t("contracts.workbench.copied", { id: data.external_id }),
            testId: "SF-03-identifier",
          }}
          chips={chips}
          actions={actions}
          primaryAction={primary ?? undefined}
          meta={meta}
          banner={
            banner === null ? undefined : <div data-testid="SF-03-banner-header">{banner}</div>
          }
          tracker={
            <FiveStepTracker
              steps={trackerSteps}
              open={openStep}
              onOpenChange={(next) => replaceParam("step", next === null ? null : String(next + 1))}
              testIdScreen="SF-03"
            />
          }
          kpis={
            <KpiStrip
              region
              testId="SF-03-kpi-strip"
              heading={
                measuredLabel === null
                  ? t("contracts.workbench.kpi.heading", { currency, book: label })
                  : t("contracts.workbench.kpi.headingAt", {
                      period: measuredLabel,
                      currency,
                      book: label,
                    })
              }
              kpis={strip}
            />
          }
        />
        <div data-testid="SF-03-tabs">
          <RouteTabs
            label={t("contracts.workbench.tabs.label", { id: data.external_id })}
            tabs={tabs}
          />
        </div>
        {onEstimates ? (
          <EstimatesTab {...tabProps} />
        ) : onSchedules ? (
          <SchedulesTab {...tabProps} />
        ) : onBilling ? (
          <BillingTab {...tabProps} />
        ) : onJournals ? (
          <JournalsTab {...tabProps} />
        ) : onModifications ? (
          <ModificationsTab {...tabProps} />
        ) : onHistory ? (
          <HistoryTab {...tabProps} />
        ) : (
          <section aria-labelledby={tabHeadingId} className="flex min-h-120 flex-col">
            <h2 id={tabHeadingId} className="sr-only">
              {t("contracts.workbench.tabs.obligations")}
            </h2>
            <div className="min-h-120 rounded-md border border-hairline bg-surface">
              <MasterDetail
                type="obligations"
                listLabel={t("contracts.workbench.obligations.list")}
                items={masterItems}
                selectedId={obligationId}
                onSelect={(id) =>
                  void navigate(`/contracts/${data.id}/obligations/${id}${paneSearch(paneTab)}`)
                }
                status={obligations.isPending ? "loading" : obligations.isError ? "error" : "ready"}
                errorState={
                  <RetryBanner
                    title={t("contracts.workbench.obligations.loadError")}
                    onRetry={() => void obligations.refetch()}
                    problem={obligations.error}
                  />
                }
                emptyState={
                  <EmptyState
                    title={t("contracts.workbench.obligations.emptyTitle")}
                    description={t("contracts.workbench.obligations.emptyDescription")}
                    headingLevel={3}
                  />
                }
                toolbar={
                  <div className="flex w-full flex-col gap-1.5">
                    <div className="flex items-center gap-2">
                      <input
                        type="search"
                        aria-label={t("contracts.workbench.obligations.filter")}
                        placeholder={t("contracts.workbench.obligations.filter")}
                        value={filter}
                        onChange={(event) => setFilter(event.target.value)}
                        className="h-[var(--control-h-sm)] min-w-0 flex-1 rounded-md border border-control bg-surface px-2 text-body-sm text-fg-1 placeholder:text-fg-3"
                      />
                      <Menu
                        label={t("contracts.workbench.obligations.sortLabel", {
                          sort: sortLabels[sort],
                        })}
                        size="sm"
                        align="end"
                        items={(["key", "start", "product"] as const).map((value) => ({
                          id: value,
                          label: sortLabels[value],
                          onSelect: () => setSort(value),
                        }))}
                      />
                    </div>
                    <p className="text-caption text-fg-3">
                      {t("contracts.workbench.obligations.caption", {
                        count: items.length,
                        formatted: formatNumber(items.length, { kind: "count" }),
                        currency,
                      })}
                    </p>
                  </div>
                }
                detailLabel={t("contracts.workbench.obligations.detail", {
                  name: selected?.product.name ?? "",
                })}
                noSelection={t("contracts.workbench.obligations.noSelection")}
                detailTestId="SF-03-pane-obligation"
              >
                {obligationId === null ? null : (
                  <ObligationPane
                    contract={data}
                    obligationId={obligationId}
                    recordContext={context}
                    bookLabel={label}
                    permissions={permissions}
                    commandsHidden={hidden}
                    built={built}
                    tab={paneTab}
                    onTabChange={(tab) => replaceParam("pane", tab === "overview" ? null : tab)}
                    onCommand={onPaneCommand}
                    onChangePrice={
                      !hidden &&
                      acceptsModifications(data) &&
                      built.has(MODIFICATION_NEW_ROUTE) &&
                      permissions.includes(MODIFICATION_CREATE_PERMISSION)
                        ? (id) => void navigate(changePriceHref(data.id, ctxSearch, id))
                        : undefined
                    }
                    backPath={obligationsPath}
                  />
                )}
              </MasterDetail>
            </div>
          </section>
        )}
        {drawer === null ? null : (
          <WorkbenchDrawer
            drawer={drawer}
            contract={data}
            obligations={items}
            books={books}
            canUpload={!hidden && canCreate}
            onClose={() => setDrawer(null)}
            onNewReview={() => setDrawer({ kind: "step1" })}
          />
        )}
      </div>
    );
  }

  return (
    <ExplainProvider load={loadExplanation} lists={explainLists}>
      <div className="flex min-h-full gap-4">
        <div className="min-w-0 flex-1">{body}</div>
        <ExplainPanel />
      </div>
    </ExplainProvider>
  );
}

function WorkbenchDrawer({
  drawer,
  contract,
  obligations,
  books,
  canUpload,
  onClose,
  onNewReview,
}: {
  readonly drawer: OpenDrawer;
  readonly contract: Contract;
  readonly obligations: readonly Obligation[];
  readonly books: readonly string[];
  readonly canUpload: boolean;
  readonly onClose: () => void;
  /** SCREENS §4.9.1 (rev 1.72): the review drawer in place of the assessment the API refused. */
  readonly onNewReview: () => void;
}) {
  switch (drawer.kind) {
    case "step1":
      return <Step1ReviewDrawer contract={contract} onClose={onClose} />;
    case "assessment":
      return (
        <Step1AssessmentDrawer
          contract={contract}
          record={drawer.record}
          books={books}
          today={drawer.today}
          onClose={onClose}
          onNewReview={onNewReview}
        />
      );
    case "distinct": {
      const obligation = obligations.find((item) => item.obligation_key === drawer.obligationKey);
      return obligation === undefined ? null : (
        <DistinctReviewDrawer
          contract={contract}
          obligation={obligation}
          obligations={obligations}
          onClose={onClose}
        />
      );
    }
    case "event":
      return (
        <RecordEventDrawer
          contract={contract}
          obligations={obligations}
          kind={drawer.event}
          obligationKey={drawer.obligationKey}
          onClose={onClose}
        />
      );
    case "hold":
      return (
        <ApplyHoldDrawer
          contract={contract}
          obligations={obligations}
          obligationKey={drawer.obligationKey}
          onClose={onClose}
        />
      );
    case "release":
      return (
        <ReleaseHoldDrawer
          contract={contract}
          obligations={obligations}
          holdId={drawer.holdId}
          onClose={onClose}
        />
      );
    case "memos":
      return (
        <EditMemosDrawer
          contract={contract}
          obligations={obligations}
          obligationKey={drawer.obligationKey}
          onClose={onClose}
        />
      );
    case "combine":
      return <CombineDrawer contract={contract} onClose={onClose} />;
    case "documents":
      return <DocumentsDrawer contract={contract} canUpload={canUpload} onClose={onClose} />;
    case "dismiss":
      return <DismissSuggestionModal suggestion={drawer.suggestion} onClose={onClose} />;
  }
}
