// SF-05 Close cockpit: checklist and blockers (SCREENS_B §1.1; §0.3 SB-R-05, SB-R-06; §0.4 E-04, E-60,
// E-62; SCREENS RT-26, SCR-PERM-01 to SCR-PERM-07, SCR-ST-01 to SCR-ST-12, SCR-TID-02 to SCR-TID-04;
// DESIGN_SYSTEM DS-CMP-06, DS-CMP-10, DS-CMP-11, DS-CMP-19, DS-CMP-21, DS-CMP-24; 04 API-R-18 §16.8,
// API-R-09; BUILD_SPEC CLO-23). `/close` redirects to the context entity, primary book and earliest open
// period (BR-UX-01). The record frame is shared by the Checklist, Journal preview and Reconciliations
// route tabs: header with the E-04 chip and the §1.1 action bar, the "Close status" KPI strip, the lock
// reason line, the banners and route tabs that list built routes only (XR-14). Counts and money come
// from the API (DG-FE-08); blocker count arithmetic is permitted because counts are not money (§1.1 data
// bindings).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useId, useState } from "react";
import { Link, Navigate, useLocation, useNavigate, useParams } from "react-router";

import {
  type ContextChoice,
  contextOwner,
  readStoredContext,
  resolveEntityBook,
  resolvePeriod,
} from "../../app/shell/ContextPill";
import { contextSearch } from "../../app/shell/IconRail";
import { useShellSession } from "../../app/shell/SandboxIndicator";
import { DataGrid, testIdKey } from "../../components/data-grid/DataGrid";
import type { GridColumn, GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { DotsThree } from "../../components/icons/registry";
import { type MetaItem, RecordHeader } from "../../components/record/RecordHeader";
import { type RouteTab, RouteTabs } from "../../components/record/Tabs";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { Menu, type MenuItem } from "../../components/ui/Menu";
import { Modal } from "../../components/ui/Modal";
import { chipFor, OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { useCommand } from "../../lib/api/commands";
import { ApiProblem } from "../../lib/api/problems";
import { currencyRegistered } from "../../lib/api/queries/approvals";
import {
  type CloseRun,
  type CloseRunCreateIn,
  EVERY_CLOSE_RUN,
} from "../../lib/api/queries/close-runs";
import { JUDGEMENT_CREATE_PERMISSION } from "../../lib/api/queries/contracts";
import { type Me, useMe } from "../../lib/api/queries/me";
import {
  type BlockerCounts,
  blockerCountsKey,
  type ChecklistItem,
  CLOSE_RUNS_PATH,
  cockpitKey,
  EVERY_PERIOD,
  fetchBlockerCounts,
  fetchCockpit,
  fetchPeriodRequests,
  PERIOD_CLOSE_PERMISSION,
  PERIOD_LOCK_PERMISSION,
  PERIOD_REOPEN_PERMISSION,
  type PeriodCockpit,
  periodCommandPath,
  type PeriodLockRequestIn,
  type PeriodPermanentLockRequestIn,
  periodRequestsKey,
} from "../../lib/api/queries/periods";
import { REPORT_ROUTE } from "../../lib/api/queries/reports";
import {
  booksKey,
  entitiesKey,
  fetchActiveEntities,
  fetchBooks,
  fetchPeriods,
  type Period,
  periodLabel,
  periodsKey,
  rowIfMatch,
} from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import { formatDate, formatMoney, formatNumber, formatTimestamp, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { withParams } from "../../lib/url/params";
import { ReadOnlyItem, SelectField, TextField } from "../contracts/drawers/common";
import { useBuiltPaths } from "../settings/index";
import {
  ChecklistChip,
  checklistRowKey,
  failingGates,
  GateTable,
  gateLabel,
  isCleared,
  LockPeriodDialog,
} from "./lock-drawer";
import { JudgementDrawer } from "./judgement-drawer";
import { ATTACHMENT_PERMISSIONS, ReopenDrawer, ReopenRequestBanner } from "./reopen-drawer";

/** SCREENS RT-26: the rail destination and the redirect from the context. */
export const CLOSE_PATH = "/close";
/** 04 E-04 states in which a period takes postings (PRD BR-CLS-08). */
const POSTABLE_STATES: ReadonlySet<string> = new Set(["open", "closing", "reopened"]);
const COCKPIT_PATTERN = "/close/:entity/:book/:period";
const APPROVAL_REQUEST_ROUTE = "/approvals/requests/:requestId";

/** SCREENS RT-99 SF-05:close-run, where a close run is followed. */
const CLOSE_RUN_ROUTE = `${COCKPIT_PATTERN}/close-run`;
/** SCREENS RT-27 SF-05:multi-entity, opened by "Close several entities" (`period.close`). */
const MULTI_ENTITY_ROUTE = "/close/multi-entity";
/** SCREENS SCR-URL-01 to SCR-URL-03: the context a close link keeps. */
const CONTEXT = ["entity", "period", "book"] as const;
const LINK_BUTTON =
  "inline-flex h-[var(--control-h)] items-center rounded-md border border-control bg-surface px-3 text-body-sm font-medium text-fg-1 hover:bg-hover";
const CELL = "px-3 py-2 text-body-sm";

export type CockpitTab =
  "checklist" | "close-run" | "journal-preview" | "reconciliations" | "history";

export function cockpitRoute(
  entity: string,
  book: string,
  period: string,
  segment: string | null = null,
): string {
  const base = `${CLOSE_PATH}/${encodeURIComponent(entity)}/${encodeURIComponent(book)}/${encodeURIComponent(period)}`;
  return segment === null ? base : `${base}/${segment}`;
}

export function bookLabel(code: string): string {
  return code === "ASC606" || code === "IFRS15" || code === "LEGACY"
    ? t(`shell.context.books.${code}`)
    : code;
}

/** E-122 `JOURNAL_RUN_NOT_CALCULATED` (BLK-10): no non-cancelled journal run for the period. */
export function journalRunMissing(cockpit: Pick<PeriodCockpit, "derived_blockers">): boolean {
  return derivedCount(cockpit, "JOURNAL_RUN_NOT_CALCULATED") > 0;
}

function derivedCount(cockpit: Pick<PeriodCockpit, "derived_blockers">, code: string): number {
  return cockpit.derived_blockers.find((item) => item.code === code)?.count ?? 0;
}

/**
 * API-S-PeriodCockpit `pending_requests` (04 rev 1.8): the pending requests of the entity of one type,
 * counted for every reader alike, which BLK-06 and BLK-15 subtract (SCREENS_B §1.1 rev 1.3; D-90a QA-L9-7).
 */
function pendingRequestCount(
  cockpit: Pick<PeriodCockpit, "pending_requests">,
  subjectType: "JUDGEMENT_RECORD" | "MANUAL_ADJUSTMENT",
): number {
  return cockpit.pending_requests.find((item) => item.subject_type === subjectType)?.count ?? 0;
}

function contextParams(entity: string, book: string, period: string): Record<string, string> {
  return {
    entity: encodeURIComponent(entity),
    period: encodeURIComponent(period),
    book: encodeURIComponent(book),
  };
}

export function Mono({ children }: { readonly children: ReactNode }) {
  return <span className="font-mono text-mono-sm text-fg-1">{children}</span>;
}

/** SCREENS SCR-ST-05: the negative region banner with the problem title and Retry. */
export function RetryBanner({
  title,
  problem,
  onRetry,
}: {
  readonly title: string;
  readonly problem: unknown;
  readonly onRetry: () => void;
}) {
  return (
    <Banner
      tone="negative"
      title={title}
      actions={
        <Button variant="link" onClick={onRetry}>
          {t("close.cockpit.retry")}
        </Button>
      }
    >
      {problem instanceof ApiProblem ? <p>{problem.title}</p> : null}
      {problem instanceof ApiProblem && problem.requestId !== null ? (
        <p>{t("close.cockpit.reference", { reference: problem.requestId })}</p>
      ) : null}
    </Banner>
  );
}

/** SCREENS_B §1.1 SCR-ST-07 "Period not found" with "Go to Close". */
function PeriodNotFound() {
  const navigate = useNavigate();
  return (
    <div data-testid="SF-05-page">
      <EmptyState
        title={t("close.cockpit.notFound.title")}
        description={t("close.cockpit.notFound.description")}
        headingLevel={2}
        action={{
          label: t("close.cockpit.notFound.action"),
          onAction: () => void navigate(CLOSE_PATH),
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// `/close`: the BR-UX-01 context, as the context pill resolves it.

export function CloseRedirect() {
  const location = useLocation();
  const me = useMe();
  const ready = me.data !== undefined;
  const entities = useQuery({
    queryKey: entitiesKey(),
    queryFn: fetchActiveEntities,
    enabled: ready,
  });
  const books = useQuery({ queryKey: booksKey(), queryFn: fetchBooks, enabled: ready });
  const params = new URLSearchParams(location.search);
  const url: ContextChoice = {
    entity: params.get("entity"),
    period: params.get("period"),
    book: params.get("book"),
  };
  const owner = contextOwner(me.data, useShellSession());
  const stored = owner === null ? null : readStoredContext(owner);
  const choices = stored === null ? [url] : [url, stored];
  const head =
    entities.data === undefined || books.data === undefined
      ? null
      : resolveEntityBook(entities.data, books.data, choices);
  const query = { entity: head?.entity.code ?? "", book: head?.book.code ?? "" };
  const periods = useQuery({
    queryKey: periodsKey(query),
    queryFn: () => fetchPeriods(query),
    enabled: head !== null,
  });

  const failure = me.error ?? entities.error ?? books.error ?? periods.error;
  if (failure !== null) {
    return (
      <RetryBanner
        title={t("close.cockpit.loadError")}
        problem={failure}
        onRetry={() => {
          void entities.refetch();
          void books.refetch();
          void periods.refetch();
        }}
      />
    );
  }
  if (entities.data !== undefined && books.data !== undefined && head === null) {
    return <PeriodNotFound />;
  }
  if (head === null || periods.data === undefined) {
    return (
      <div data-testid="SF-05-page">
        <Skeleton region={t("close.cockpit.region")} shape="rows" count={8} />
      </div>
    );
  }
  const period = resolvePeriod(periods.data, choices);
  if (period === null) {
    return <PeriodNotFound />;
  }
  const entity = head.entity.code;
  const book = head.book.code;
  const key = period.period.period_key;
  return (
    <Navigate
      replace
      to={`${cockpitRoute(entity, book, key)}${withParams(location.search, contextParams(entity, book, key))}`}
    />
  );
}

// ---------------------------------------------------------------------------------------------------
// The record frame.

export interface CockpitContext {
  readonly cockpit: PeriodCockpit;
  readonly periods: readonly Period[];
  readonly permissions: readonly string[];
  readonly ctxSearch: string;
  /** SCREENS_B §1.1 blocker rows; null while their counts load. */
  readonly blockers: readonly BlockerRow[] | null;
  readonly blockersError: unknown;
  readonly retryBlockers: () => void;
  /** Focuses the checklist row of a gate or task (the reason line and BLK-16 links). */
  readonly focusRow: (item: ChecklistItem) => void;
}

export interface CockpitFrameProps {
  readonly tab: CockpitTab;
  readonly children: (context: CockpitContext) => ReactNode;
}

/**
 * The context pill reads the URL parameters: a close page writes its context when they are absent, and
 * opens the chosen period's close when the pill changes them (SCREENS SCR-URL-01 to SCR-URL-03). Shared
 * by the cockpit frame and SF-05:reconciliation, whose paths carry the entity, book and period.
 */
export function useCloseContext(entity: string, book: string, period: string): void {
  const location = useLocation();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const shown = {
    entity: params.get("entity"),
    book: params.get("book"),
    period: params.get("period"),
  };
  const unset = shown.entity === null && shown.book === null && shown.period === null;
  const moved =
    !unset && (shown.entity !== entity || shown.book !== book || shown.period !== period);
  useEffect(() => {
    if (unset) {
      void navigate(
        { search: withParams(location.search, contextParams(entity, book, period)) },
        { replace: true },
      );
    } else if (moved) {
      void navigate(`${CLOSE_PATH}${location.search}`, { replace: true });
    }
  }, [unset, moved, navigate, location.search, entity, book, period]);
}

export function CockpitFrame({ tab, children }: CockpitFrameProps) {
  const { entity = "", book = "", period = "" } = useParams();
  const me = useMe();
  const query = { entity, book };
  const periods = useQuery({ queryKey: periodsKey(query), queryFn: () => fetchPeriods(query) });
  const state = periods.data?.find((item) => item.period.period_key === period) ?? null;
  const stateId = state?.id ?? "";
  const cockpit = useQuery({
    queryKey: cockpitKey(stateId),
    queryFn: () => fetchCockpit(stateId),
    enabled: state !== null,
  });
  useCloseContext(entity, book, period);

  if (me.error !== null) {
    return <Banner tone="negative" title={me.error.message} />;
  }
  if (periods.error !== null) {
    const missing =
      periods.error instanceof ApiProblem &&
      (periods.error.status === 404 || periods.error.status === 422);
    return missing ? (
      <PeriodNotFound />
    ) : (
      <RetryBanner
        title={t("close.cockpit.loadError")}
        problem={periods.error}
        onRetry={() => void periods.refetch()}
      />
    );
  }
  if (periods.data !== undefined && state === null) {
    return <PeriodNotFound />;
  }
  if (cockpit.error !== null) {
    return cockpit.error instanceof ApiProblem && cockpit.error.status === 404 ? (
      <PeriodNotFound />
    ) : (
      <RetryBanner
        title={t("close.cockpit.loadError")}
        problem={cockpit.error}
        onRetry={() => void cockpit.refetch()}
      />
    );
  }
  if (me.data === undefined || periods.data === undefined || cockpit.data === undefined) {
    return (
      <div data-testid="SF-05-page">
        <Skeleton region={t("close.cockpit.region")} shape="rows" count={8} />
      </div>
    );
  }
  return (
    <CockpitView
      key={cockpit.data.period.id}
      cockpit={cockpit.data}
      periods={periods.data}
      me={me.data}
      tab={tab}
    >
      {children}
    </CockpitView>
  );
}

// ---------------------------------------------------------------------------------------------------
// Blocker rows (§1.1 "Blocker rows"): each item counted once; rows with count 0 are hidden.

export interface BlockerLink {
  readonly href: string;
  readonly destination: string;
}

export interface BlockerRow {
  /** SCREENS_B §1.1 test hook key, `SF-05-row-<key>`. */
  readonly key: string;
  readonly count: number;
  readonly owner: string;
  readonly link: BlockerLink | null;
  /** BLK-16: the first unsigned task, whose row the link focuses. */
  readonly task: ChecklistItem | null;
}

export function blockerRows(
  cockpit: PeriodCockpit,
  counts: BlockerCounts,
  built: ReadonlySet<string>,
): readonly BlockerRow[] {
  const { period, checklist } = cockpit;
  // 04 §16.8 rev 1.199: `blockers` is null in a row of `GET /periods` alone; the cockpit's own
  // `period` carries the counts. Without them the region must never read "No blockers".
  const blockers = period.blockers;
  if (blockers === null) {
    throw new Error("API-S-PeriodCockpit period.blockers is null");
  }
  const entity = encodeURIComponent(period.entity.code);
  const periodKey = encodeURIComponent(period.period.period_key);
  const book = encodeURIComponent(period.book);
  const ownerOf = (gate: string | null, role: string): string => {
    const item =
      gate === null ? undefined : checklist.find((candidate) => candidate.gate_check_code === gate);
    return item?.owner?.display_name ?? t(`close.cockpit.blockers.owner.${role}`);
  };
  const route = (path: string, search: string, destination: string): BlockerLink | null =>
    built.has(path)
      ? {
          href: `${path}?${search}`,
          destination: t(`close.cockpit.blockers.destination.${destination}`),
        }
      : null;
  const tabRoute = (segment: string, destination: string): BlockerLink | null =>
    built.has(`${COCKPIT_PATTERN}/${segment}`)
      ? {
          href: `${cockpitRoute(period.entity.code, period.book, period.period.period_key, segment)}?entity=${entity}&period=${periodKey}&book=${book}`,
          destination: t(`close.cockpit.blockers.destination.${destination}`),
        }
      : null;
  const journals = `entity=${entity}&period=${periodKey}&book=${book}`;
  // SF-08:report (RT-32): the register of `code` with its `p.` parameters and the period's context.
  const reportRoute = (code: string, search: string, destination: string): BlockerLink | null =>
    built.has(REPORT_ROUTE)
      ? {
          href: `/reports/${code}?${search}&${journals}`,
          destination: t(`close.cockpit.blockers.destination.${destination}`),
        }
      : null;
  const tasks = checklist.filter((item) => item.gate_kind === "MANUAL" && !isCleared(item));
  const rows: readonly BlockerRow[] = [
    {
      key: "approvals-pending",
      count: blockers.approvals_pending,
      owner: ownerOf("APPROVALS_CLEARED", "revenueReviewer"),
      link: route("/approvals/all", `entity=${entity}&f.status=is:PENDING`, "approvals"),
      task: null,
    },
    {
      key: "exceptions",
      count: Math.max(0, blockers.exceptions_open - counts.vcReassessmentMissing),
      owner: ownerOf("EXCEPTIONS_CLEARED", "exceptionOwners"),
      // BLK-02 (§1.1 rev 1.66; 04 §16.14 rev 1.206): the queue on the list `blockers.exceptions_open`
      // is counted from — the items that hold this period's lock, asked by the period's id. The link
      // names no entity, period or status: the queue reads none of them from a link, and an item that
      // names no entity or no period is among those counted.
      link: route("/data/exceptions", `blocking=${encodeURIComponent(period.id)}`, "exceptions"),
      task: null,
    },
    {
      key: "vc-reassessment-missing",
      count: counts.vcReassessmentMissing,
      owner: ownerOf("EXCEPTIONS_CLEARED", "revenueAccountant"),
      link: route(
        "/data/exceptions",
        `entity=${entity}&period=${periodKey}&f.code=is:VC_REASSESSMENT_MISSING`,
        "exceptions",
      ),
      task: null,
    },
    {
      key: "holds",
      count: blockers.holds_open,
      owner: ownerOf("HOLDS_REVIEWED", "revenueAccountant"),
      link: route("/contracts", `entity=${entity}&f.on_hold=is:true`, "contracts"),
      task: null,
    },
    {
      key: "unmapped-products",
      count: blockers.unmapped_products,
      owner: ownerOf(null, "integrationAdmin"),
      link: route("/data/exceptions", `entity=${entity}&f.code=is:PRODUCT_UNMAPPED`, "exceptions"),
      task: null,
    },
    {
      // BLK-06: SF-08:report `judgement_register` with `p.status=SUBMITTED` (RPS-11).
      key: "judgements-unreviewed",
      count: Math.max(
        0,
        blockers.judgements_unreviewed - pendingRequestCount(cockpit, "JUDGEMENT_RECORD"),
      ),
      owner: ownerOf("JUDGEMENTS_REVIEWED", "revenueReviewer"),
      link: reportRoute("judgement_register", "p.status=SUBMITTED", "judgementRegister"),
      task: null,
    },
    {
      // SF-16 sync runs wait for DIN-12 (R-RC-1, post-rc).
      key: "interface-failures",
      count: blockers.interface_failures,
      owner: ownerOf("INTERFACES_COMPLETE", "integrationAdmin"),
      link: null,
      task: null,
    },
    {
      key: "jobs-failed",
      count: blockers.jobs_failed,
      owner: ownerOf(null, "jobInitiator"),
      link: tabRoute("close-run", "closeRun"),
      task: null,
    },
    {
      key: "groups-dirty",
      count: blockers.groups_dirty,
      owner: ownerOf("NO_DIRTY_GROUPS", "revenueAccountant"),
      link: tabRoute("close-run", "closeRun"),
      task: null,
    },
    {
      key: "journal-run-missing",
      count: derivedCount(cockpit, "JOURNAL_RUN_NOT_CALCULATED"),
      owner: ownerOf("JE_COMPLETE", "revenueAccountant"),
      link: route("/journals", journals, "journals"),
      task: null,
    },
    {
      key: "batches-unexported",
      count: blockers.batches_unexported,
      owner: ownerOf("BATCHES_ACKNOWLEDGED", "revenueAccountant"),
      link: route("/journals", `${journals}&f.state=is:approved`, "journals"),
      task: null,
    },
    {
      key: "batches-unacknowledged",
      count: blockers.batches_unacknowledged,
      owner: ownerOf("BATCHES_ACKNOWLEDGED", "revenueAccountant"),
      link: route("/journals", `${journals}&f.state=in:exported,failed`, "journals"),
      task: null,
    },
    {
      key: "reconciliations-missing",
      count: derivedCount(cockpit, "RECONCILIATIONS_NOT_GENERATED"),
      owner: ownerOf("RECONCILIATIONS_GENERATED", "revenueAccountant"),
      link: tabRoute("reconciliations", "reconciliations"),
      task: null,
    },
    {
      key: "reconciliations-unsigned",
      count: blockers.reconciliations_unsigned,
      owner: ownerOf("RECONCILIATIONS_GENERATED", "revenueReviewer"),
      link: tabRoute("reconciliations", "reconciliations"),
      task: null,
    },
    {
      // BLK-15: SF-08:report `manual_adjustment_register` with `p.status=DRAFT` (RPS-8).
      key: "manual-adjustments-pending",
      count: Math.max(
        0,
        blockers.manual_adjustments_pending - pendingRequestCount(cockpit, "MANUAL_ADJUSTMENT"),
      ),
      owner: ownerOf("MANUAL_ADJUSTMENTS_CLEARED", "revenueAccountant"),
      link: reportRoute("manual_adjustment_register", "p.status=DRAFT", "manualAdjustmentRegister"),
      task: null,
    },
    {
      key: "close-tasks-unsigned",
      count: tasks.length,
      owner: tasks[0]?.owner?.display_name ?? t("close.cockpit.blockers.owner.taskOwners"),
      link: null,
      task: tasks[0] ?? null,
    },
  ];
  return rows.filter((row) => row.count > 0);
}

// ---------------------------------------------------------------------------------------------------
// The view.

type PeriodDialog =
  "open" | "start" | "end" | "submit-lock" | "lock" | "reopen" | "judgement" | "permanent-lock";

interface CockpitViewProps {
  readonly cockpit: PeriodCockpit;
  readonly periods: readonly Period[];
  readonly me: Me;
  readonly tab: CockpitTab;
  readonly children: (context: CockpitContext) => ReactNode;
}

function CockpitView({ cockpit, periods, me, tab, children }: CockpitViewProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const built = useBuiltPaths();
  const reasonId = useId();
  const openReasonId = useId();
  const [dialog, setDialog] = useState<PeriodDialog | null>(null);
  const period = cockpit.period;
  const permissions = me.permissions;
  const ctxSearch = contextSearch(location.search, CONTEXT);
  const canClose = permissions.includes(PERIOD_CLOSE_PERMISSION);
  const canLock = permissions.includes(PERIOD_LOCK_PERMISSION);
  const canReopen = permissions.includes(PERIOD_REOPEN_PERMISSION);
  const canJudge = permissions.includes(JUDGEMENT_CREATE_PERMISSION);
  const entityCode = period.entity.code;
  const periodKey = period.period.period_key;
  const label = periodLabel(period.period);
  const book = bookLabel(period.book);
  // 04 §16.8 rev 1.155, API-S-Period `follows` (supervisor rulings R-112 (e), R-113 (h) and R-114 (d);
  // PRD ERR-76): a period of the LEGACY book has no close of its own and follows the close of the
  // primary book. The API refuses its four close commands and keeps `open` and `cancel-close`; the
  // cockpit offers what the API keeps, shows one line in place of the close and reads neither the
  // period's requests nor its blocker counts.
  const follows = period.follows ?? null;
  const closes = follows === null;

  const requests = useQuery({
    queryKey: periodRequestsKey(period.id),
    queryFn: () => fetchPeriodRequests(period.id),
    enabled: closes,
  });
  const counts = useQuery({
    queryKey: blockerCountsKey(period.id),
    queryFn: () => fetchBlockerCounts(period.entity, periodKey),
    enabled: closes,
  });
  const rows = counts.data === undefined ? null : blockerRows(cockpit, counts.data, built);
  // 04 §16.8: 202 with the job of a new run, or 200 with the run that has not ended.
  const runClose = useCommand<CloseRun>({
    method: "POST",
    path: CLOSE_RUNS_PATH,
    invalidates: [EVERY_PERIOD, EVERY_CLOSE_RUN],
  });

  const lockRequest = requests.data?.lock ?? null;
  const reopenRequest = requests.data?.reopen ?? null;
  // A second request is not offered while one waits for its two decisions, nor before that is known.
  const reopenRequestable =
    requests.isError || (requests.data !== undefined && reopenRequest === null);
  const failing = failingGates(cockpit.checklist);
  const decider = lockRequest !== null && canLock && lockRequest.preparer.id !== me.user.id;

  const index = periods.findIndex((item) => item.id === period.id);
  const later = index < 0 ? [] : periods.slice(index + 1);
  const earlier = index < 0 ? [] : periods.slice(0, index);
  // BR-CLS-08 (ERR-65; supervisor ruling R-112 (a)): a period is submitted for lock, and locked, only
  // when no earlier period of the entity and book is postable; the refusal names the earliest of them.
  const earlierPostable = earlier.find((item) => POSTABLE_STATES.has(item.state));
  const orderReason =
    earlierPostable === undefined
      ? null
      : t("close.cockpit.lock.order", {
          earlier: periodLabel(earlierPostable.period),
          entity: entityCode,
          book,
        });
  // SM-07: periods open in order, so the one after a future period does not open yet.
  const previous = earlier.at(-1);
  const openReason =
    previous !== undefined && previous.state === "future"
      ? t("close.cockpit.open.order", { previous: periodLabel(previous.period) })
      : undefined;
  /** The cockpit of another period of this entity and book, in its own context. */
  const periodHref = (other: Period) =>
    `${cockpitRoute(entityCode, period.book, other.period.period_key)}${withParams(
      location.search,
      contextParams(entityCode, period.book, other.period.period_key),
    )}`;
  const lockUnavailable = orderReason !== null || lockRequest === null || failing.length > 0;
  const lockReason =
    orderReason ??
    (failing.length > 0
      ? t("close.cockpit.lock.gates", { count: failing.length })
      : t("close.cockpit.lock.noRequest"));
  const next = later[0];
  const nextLabel = next === undefined ? NO_VALUE : periodLabel(next.period);
  const laterClosed = [...later]
    .reverse()
    .find((item) => item.state === "closed" || item.state === "permanently_locked");
  // SM-07: a period is permanently locked only after every earlier one; the earliest that is not
  // names the reason of the disabled menu item.
  const earlierUnlocked = earlier.find((item) => item.state !== "permanently_locked");
  // A pending `PERIOD_LOCK` request on a locked period is its permanent-lock request (PRD Q14).
  const permanentLockRequestable =
    requests.isError || (requests.data !== undefined && lockRequest === null);

  const focusRow = (item: ChecklistItem) => {
    if (tab !== "checklist") {
      void navigate(`${cockpitRoute(entityCode, period.book, periodKey)}${ctxSearch}`);
      return;
    }
    const row = document.querySelector(
      `[data-testid="SF-05-row-${testIdKey(checklistRowKey(item))}"]`,
    );
    row?.querySelector<HTMLElement>('[role="gridcell"], [role="rowheader"]')?.focus();
  };

  // "Run close" (J-13.7): the run is followed on the Close run tab, by whoever reads it.
  const startCloseRun = async () => {
    const outcome = await runClose.submit({
      entity_code: entityCode,
      book: period.book,
      period_key: periodKey,
    } satisfies CloseRunCreateIn);
    if (outcome.kind === "failed" && outcome.problem.status === 409) {
      // A run starts in an open period, in soft close or in a reopened one (04 §16.8). The command is
      // offered by the state this page has read, so the refusal means that read is out of date: its
      // sentence stays in the banner, and the period and its runs are read again.
      await Promise.all(
        [EVERY_PERIOD, EVERY_CLOSE_RUN].map((key) =>
          queryClient.invalidateQueries({ queryKey: key }),
        ),
      );
      return;
    }
    if (outcome.kind !== "accepted" && outcome.kind !== "succeeded") {
      return;
    }
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      toast.show({
        tone: "neutral",
        message: t("close.run.alreadyRunning", { number: outcome.data.close_run_no }),
      });
    }
    await queryClient.invalidateQueries({ queryKey: EVERY_CLOSE_RUN });
    if (tab !== "close-run" && built.has(CLOSE_RUN_ROUTE)) {
      void navigate(`${cockpitRoute(entityCode, period.book, periodKey)}/close-run${ctxSearch}`);
    }
  };

  // §1.1 "Action bar": one primary per state; SCR-PERM-02 hides what the viewer may not perform.
  const lockButton = (variant: "primary" | "secondary") => (
    <Button
      key="lock"
      variant={variant}
      aria-describedby={lockUnavailable ? reasonId : undefined}
      disabledReason={lockUnavailable ? lockReason : undefined}
      onClick={() => setDialog("lock")}
    >
      {t("close.action.lock")}
    </Button>
  );
  const runCloseButton = (variant: "primary" | "secondary") => (
    <Button
      key="run-close"
      variant={variant}
      loading={runClose.pending}
      onClick={() => void startCloseRun()}
    >
      {t("close.action.runClose")}
    </Button>
  );
  const startSoftCloseButton = (variant: "primary" | "secondary") => (
    <Button key="start-soft-close" variant={variant} onClick={() => setDialog("start")}>
      {t("close.action.startSoftClose")}
    </Button>
  );
  let primary: ReactNode = null;
  const secondary: ReactNode[] = [];
  const overflow: MenuItem[] = [];
  let lockShown = false;
  let submitShown = false;
  // SCREENS_B §1.1: SF-05:multi-entity with the current period and book (the context of this cockpit).
  const closeSeveral: MenuItem | null =
    canClose && built.has(MULTI_ENTITY_ROUTE)
      ? {
          id: "close-several",
          label: t("close.action.closeSeveral"),
          onSelect: () => void navigate(`${MULTI_ENTITY_ROUTE}${ctxSearch}`),
        }
      : null;
  switch (period.state) {
    case "future":
      if (canClose) {
        primary = (
          <Button
            variant="primary"
            aria-describedby={openReason === undefined ? undefined : openReasonId}
            disabledReason={openReason}
            onClick={() => setDialog("open")}
          >
            {t("close.action.open")}
          </Button>
        );
      }
      break;
    case "open":
      if (!closes) {
        break;
      }
      if (canClose) {
        primary = startSoftCloseButton("primary");
        secondary.push(runCloseButton("secondary"));
      }
      if (canLock) {
        secondary.push(lockButton("secondary"));
        lockShown = true;
      }
      if (closeSeveral !== null) {
        overflow.push(closeSeveral);
      }
      break;
    case "closing":
      // A LEGACY row an earlier release left in soft close keeps "End soft close" alone, which
      // returns it to open (04 §16.8 rev 1.155); no request is read for it.
      if (closes && lockRequest === null) {
        if (canClose) {
          primary = runCloseButton("primary");
        }
        if (canClose) {
          secondary.push(
            <Button
              key="submit-lock"
              aria-describedby={orderReason === null ? undefined : reasonId}
              disabledReason={orderReason ?? undefined}
              onClick={() => setDialog("submit-lock")}
            >
              {t("close.action.submitLock")}
            </Button>,
          );
          submitShown = true;
        }
        if (canLock) {
          secondary.push(lockButton("secondary"));
          lockShown = true;
        }
      } else if (lockRequest !== null) {
        if (decider) {
          primary = lockButton("primary");
          lockShown = true;
        }
        if (built.has(APPROVAL_REQUEST_ROUTE)) {
          secondary.push(
            <Link
              key="view-lock-request"
              to={`/approvals/requests/${lockRequest.id}`}
              className={LINK_BUTTON}
            >
              {t("close.action.viewLockRequest")}
            </Link>,
          );
        }
      }
      if (canClose) {
        overflow.push({
          id: "end-soft-close",
          label: t("close.action.endSoftClose"),
          destructive: true,
          onSelect: () => setDialog("end"),
        });
      }
      if (closes && lockRequest === null && closeSeveral !== null) {
        overflow.push(closeSeveral);
      }
      break;
    case "closed":
      if (!closes) {
        break;
      }
      if (canReopen && reopenRequestable) {
        secondary.push(
          <Button
            key="reopen"
            disabledReason={
              laterClosed === undefined
                ? undefined
                : t("close.cockpit.reopenBlocked", {
                    later: periodLabel(laterClosed.period),
                    entity: entityCode,
                    book: period.book,
                  })
            }
            onClick={() => setDialog("reopen")}
          >
            {t("close.action.requestReopen")}
          </Button>,
        );
      }
      // Item CLO-JDG-ESTERR-UI-1 (supervisor ruling R-100 (a); PRD J-14.1): the judgement whether an
      // amount found after the lock is an error or a change of estimate is recorded on its own by a
      // holder of `judgement.create`, who need not be the one who requests the reopen.
      if (canJudge) {
        secondary.push(
          <Button key="judgement" onClick={() => setDialog("judgement")}>
            {t("close.action.recordJudgement")}
          </Button>,
        );
      }
      // `period.lock` (PRD ACT-27; supervisor ruling R-83 (a)); not rendered while a request is
      // pending (R-83 (b)); disabled with its reason while an earlier period is not permanently
      // locked (SCR-PERM-03; R-83 (c)).
      if (canLock && permanentLockRequestable) {
        overflow.push({
          id: "permanent-lock",
          label: t("close.action.permanentLock"),
          destructive: true,
          disabledReason:
            earlierUnlocked === undefined
              ? undefined
              : t("close.cockpit.permanentLock.blocked", {
                  earlier: periodLabel(earlierUnlocked.period),
                }),
          onSelect: () => setDialog("permanent-lock"),
        });
      }
      break;
    case "reopened":
      if (canClose && closes) {
        primary = runCloseButton("primary");
        secondary.push(startSoftCloseButton("secondary"));
      }
      break;
    case "permanently_locked":
      break;
  }

  const banners: ReactNode[] = [];
  if (runClose.problem !== null) {
    banners.push(<RefusalBanner key="close-run-problem" problem={runClose.problem} />);
  }
  if (period.state === "closing") {
    banners.push(
      <div key="soft-close" data-testid="SF-05-banner-soft-close">
        <Banner tone="warning" announce="static" title={t("close.cockpit.banner.softClose")} />
      </div>,
    );
    // SCREENS_B §1.1 rev 1.61 (PRD BR-CLS-06 rev 1.113, BR-CLS-07, REQ-CLS-011 rev 1.99; supervisor
    // rulings R-117 (c), R-118 (c) and R-119 (h)): a soft close does not end what a reopen began.
    // While the current lock record is the REOPEN the period was locked once and is not locked
    // now: a line posted is a post-reopen line and the re-lock produces its difference report.
    if (period.current_lock?.kind === "REOPEN") {
      banners.push(
        <div key="reopened-closing" data-testid="SF-05-banner-reopened-closing">
          <Banner
            tone="warning"
            announce="static"
            title={t("close.cockpit.banner.reopenedClosing", { period: label })}
          />
        </div>,
      );
    }
  } else if (period.state === "closed") {
    banners.push(
      <Banner
        key="locked"
        tone="info"
        announce="static"
        title={t("close.cockpit.banner.locked", {
          period: label,
          entity: entityCode,
          next: nextLabel,
        })}
      />,
    );
  } else if (period.state === "reopened") {
    banners.push(
      <Banner
        key="reopened"
        tone="warning"
        announce="static"
        title={t("close.cockpit.banner.reopened", { period: label })}
      />,
    );
  } else if (period.state === "permanently_locked") {
    banners.push(
      <Banner
        key="permanently-locked"
        tone="info"
        announce="static"
        title={t("close.cockpit.banner.permanentlyLocked", { period: label, entity: entityCode })}
      />,
    );
  }
  if (reopenRequest !== null) {
    banners.push(
      <ReopenRequestBanner
        key="reopen-request"
        request={reopenRequest}
        viewerId={me.user.id}
        canView={built.has(APPROVAL_REQUEST_ROUTE)}
      />,
    );
  }
  if (lockRequest !== null) {
    // On a locked period the pending request asks for the permanent lock; the request page decides
    // it, with its step-up (supervisor ruling R-83 (b)).
    const permanent = period.state === "closed";
    banners.push(
      <div
        key="lock-request"
        data-testid={
          permanent ? "SF-05-banner-permanent-lock-request" : "SF-05-banner-lock-request"
        }
      >
        <Banner
          tone="info"
          announce="static"
          title={t(
            permanent
              ? "close.cockpit.banner.permanentLockRequest"
              : "close.cockpit.banner.lockRequest",
            {
              name: lockRequest.preparer.display_name,
              at: formatTimestamp(lockRequest.submitted_at),
            },
          )}
          actions={
            built.has(APPROVAL_REQUEST_ROUTE) ? (
              <Link
                to={`/approvals/requests/${lockRequest.id}`}
                className="text-body-sm text-accent-fg hover:underline"
              >
                {t(permanent ? "close.action.viewRequest" : "close.action.viewLockRequest")}
              </Link>
            ) : undefined
          }
        />
      </div>,
    );
  }

  const closeRunChip = period.close_run === null ? null : chipFor("E-62", period.close_run.status);
  const meta: MetaItem[] = [
    {
      label: t("close.cockpit.meta.entity"),
      value: `${entityCode} · ${period.entity.name}`,
    },
    { label: t("close.cockpit.meta.book"), value: book },
    {
      label: t("close.cockpit.meta.period"),
      value: `${formatDate(period.period.start_date)} – ${formatDate(period.period.end_date)}`,
    },
  ];
  if (closes) {
    // A period that follows another book's close has no close run and no lock of its own to name.
    meta.push(
      {
        label: t("close.cockpit.meta.closeRun"),
        value:
          closeRunChip === null ? (
            t("close.cockpit.meta.none")
          ) : (
            <StatusChip status={closeRunChip.status} caption={closeRunChip.caption} />
          ),
      },
      {
        label: t("close.cockpit.meta.currentLock"),
        value:
          period.current_lock === null ? (
            t("close.cockpit.meta.none")
          ) : (
            <Mono>{period.current_lock.id.slice(0, 8)}</Mono>
          ),
      },
    );
  }

  const base = cockpitRoute(entityCode, period.book, periodKey);
  const candidates: readonly {
    readonly id: string;
    readonly segment: string | null;
    readonly key: string;
  }[] = [
    { id: "checklist", segment: null, key: "checklist" },
    { id: "close-run", segment: "close-run", key: "closeRun" },
    { id: "journal-preview", segment: "journal-preview", key: "journalPreview" },
    { id: "reconciliations", segment: "reconciliations", key: "reconciliations" },
    { id: "history", segment: "history", key: "history" },
  ];
  const tabs: readonly RouteTab[] = candidates
    .filter(
      (candidate) =>
        candidate.segment === null || built.has(`${COCKPIT_PATTERN}/${candidate.segment}`),
    )
    // The LEGACY book takes no close run, no journal run (04 T-SL-06) and no reconciliation: its
    // period keeps the line of the first tab and its own state history.
    .filter((candidate) => closes || candidate.id === "checklist" || candidate.id === "history")
    .map((candidate) =>
      candidate.segment === null
        ? {
            id: candidate.id,
            label: t(`close.cockpit.tabs.${candidate.key}`),
            to: `${base}${ctxSearch}`,
            end: true,
          }
        : {
            id: candidate.id,
            label: t(`close.cockpit.tabs.${candidate.key}`),
            to: `${base}/${candidate.segment}${ctxSearch}`,
          },
    );

  const chip = chipFor("E-04", period.state);
  const blockerTotal = rows === null ? null : rows.reduce((sum, row) => sum + row.count, 0);
  const openLine =
    period.state === "future" && canClose && openReason !== undefined && previous ? (
      <p
        id={openReasonId}
        data-testid="SF-05-banner-open-unavailable"
        className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-body-sm text-fg-2"
      >
        <span>{openReason}</span>
        <Link
          to={periodHref(previous)}
          className="inline-flex min-h-6 items-center text-accent-fg hover:underline"
        >
          {t("close.cockpit.order.goTo", { period: periodLabel(previous.period) })}
        </Link>
      </p>
    ) : null;

  return (
    <div data-testid="SF-05-page" className="flex flex-col gap-4">
      <RecordHeader
        title={t("close.cockpit.title", { entity: entityCode, period: label, book })}
        chips={
          chip === null ? undefined : <StatusChip status={chip.status} caption={chip.caption} />
        }
        actions={
          <>
            {secondary}
            {/* RecordHeader shows `primaryAction` only in its condensed bar; the page row carries it here. */}
            {primary}
            {overflow.length === 0 ? null : (
              <Menu
                label={t("close.action.more")}
                icon={DotsThree}
                iconOnly
                variant="ghost"
                align="end"
                items={overflow}
              />
            )}
          </>
        }
        primaryAction={primary ?? undefined}
        meta={meta}
        banner={
          banners.length === 0 ? undefined : <div className="flex flex-col gap-2">{banners}</div>
        }
        kpis={
          closes ? (
            <>
              <CloseStatusStrip cockpit={cockpit} periods={periods} blockers={blockerTotal} />
              {(lockShown && lockUnavailable) || (submitShown && earlierPostable !== undefined) ? (
                <p
                  id={reasonId}
                  data-testid="SF-05-banner-lock-unavailable"
                  className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-body-sm text-fg-2"
                >
                  <span>{lockReason}</span>
                  {earlierPostable === undefined ? null : (
                    // The way to the period that has to be locked first.
                    <Link
                      to={periodHref(earlierPostable)}
                      className="inline-flex min-h-6 items-center text-accent-fg hover:underline"
                    >
                      {t("close.cockpit.order.goTo", {
                        period: periodLabel(earlierPostable.period),
                      })}
                    </Link>
                  )}
                  {(earlierPostable === undefined ? failing : []).map((item) => (
                    // DS-DEN-03: a wrapping list of links keeps 24 px targets.
                    <Button
                      key={item.id}
                      variant="link"
                      className="min-h-6"
                      onClick={() => focusRow(item)}
                    >
                      {gateLabel(item)}
                    </Button>
                  ))}
                </p>
              ) : null}
              {openLine}
            </>
          ) : (
            // The close status is the close's: a period that follows another book's shows none.
            (openLine ?? undefined)
          )
        }
      />
      <RouteTabs label={t("close.cockpit.tabs.label", { period: label })} tabs={tabs} />
      {follows !== null && tab !== "history" ? (
        <FollowsLine
          follows={follows}
          entity={entityCode}
          period={label}
          to={`${cockpitRoute(entityCode, follows.book_code, periodKey)}${withParams(
            location.search,
            contextParams(entityCode, follows.book_code, periodKey),
          )}`}
          action={t("close.cockpit.follows.goTo", {
            period: label,
            book: bookLabel(follows.book_code),
          })}
        />
      ) : (
        children({
          cockpit,
          periods,
          permissions,
          ctxSearch,
          blockers: rows,
          blockersError: counts.error,
          retryBlockers: () => void counts.refetch(),
          focusRow,
        })
      )}
      {dialog === "open" || dialog === "start" ? (
        <TransitionDialog
          period={period}
          kind={dialog}
          label={label}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === "end" ? (
        <EndSoftCloseDialog period={period} label={label} onClose={() => setDialog(null)} />
      ) : null}
      {dialog === "submit-lock" ? (
        <SubmitForLockDialog
          cockpit={cockpit}
          label={label}
          onClose={() => setDialog(null)}
          onFocusGate={focusRow}
        />
      ) : null}
      {dialog === "lock" && lockRequest !== null ? (
        <LockPeriodDialog
          request={lockRequest}
          checklist={cockpit.checklist}
          entityCode={entityCode}
          periodLabel={label}
          nextPeriodLabel={nextLabel}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === "reopen" ? (
        <ReopenDrawer
          period={period}
          periodLabel={label}
          bookLabel={book}
          canViewRequest={built.has(APPROVAL_REQUEST_ROUTE)}
          canAttach={ATTACHMENT_PERMISSIONS.some((permission) => permissions.includes(permission))}
          canJudge={canJudge}
          judgementRegisterHref={
            built.has(REPORT_ROUTE) ? `/reports/judgement_register${ctxSearch}` : null
          }
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === "judgement" ? (
        <JudgementDrawer
          period={period}
          periodLabel={label}
          bookLabel={book}
          onOpenRegister={
            built.has(REPORT_ROUTE)
              ? () => void navigate(`/reports/judgement_register${ctxSearch}`)
              : null
          }
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === "permanent-lock" ? (
        <PermanentLockDialog
          period={period}
          label={label}
          bookLabel={book}
          onClose={() => setDialog(null)}
        />
      ) : null}
    </div>
  );
}

/**
 * SCREENS_B §1.1 rev 1.42 (04 §16.8 rev 1.155, API-S-Period `follows`; supervisor rulings R-112 (e),
 * R-113 (h) and R-114 (d)): the one line a period of the LEGACY book shows in place of a close — the
 * book whose close it follows, that book's state for the period, which the row carries, and the way
 * to the same page in that book. An entity that keeps no period of the followed book has no such page.
 */
export function FollowsLine({
  follows,
  entity,
  period,
  to,
  action,
}: {
  readonly follows: NonNullable<Period["follows"]>;
  readonly entity: string;
  /** The period's label. */
  readonly period: string;
  readonly to: string;
  /** The link's name, which says where it leads. */
  readonly action: string;
}) {
  const book = bookLabel(follows.book_code);
  const chip = follows.state === null ? null : chipFor("E-04", follows.state);
  return (
    <p
      data-testid="SF-05-follows"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-hairline bg-surface px-4 py-3 text-body-sm text-fg-1"
    >
      <span>{t("close.cockpit.follows.line", { book })}</span>
      {follows.state === null ? (
        <span className="text-fg-2">
          {t("close.cockpit.follows.noPeriod", { book, period, entity })}
        </span>
      ) : (
        <>
          <span className="flex items-center gap-2 text-fg-2">
            <span>{t("close.cockpit.follows.state", { book, period })}</span>
            {chip === null ? null : <StatusChip status={chip.status} caption={chip.caption} />}
          </span>
          <Link to={to} className="inline-flex min-h-6 items-center text-accent-fg hover:underline">
            {action}
          </Link>
        </>
      )}
    </p>
  );
}

/** DS-CMP-06 KPI strip "Close status" (§1.1 "Regions and components"); it wraps at 1280 px. */
function CloseStatusStrip({
  cockpit,
  periods,
  blockers,
}: {
  readonly cockpit: PeriodCockpit;
  readonly periods: readonly Period[];
  readonly blockers: number | null;
}) {
  const headingId = useId();
  const checklist = cockpit.checklist;
  const passed = checklist.filter((item) => item.status === "PASSED").length;
  const reviewed = cockpit.kpis.reconciliations_reviewed;
  const difference = cockpit.journal_preview.difference_functional;
  const differenceText =
    journalRunMissing(cockpit) || !currencyRegistered(difference.currency)
      ? NO_VALUE
      : formatMoney(difference.amount, difference.currency);
  const byKey = new Map(periods.map((item) => [item.period.period_key, item]));
  const days = cockpit.kpis.days_to_close_last_three.map((item) => {
    const found = byKey.get(item.period_key);
    const name = found === undefined ? item.period_key : periodLabel(found.period);
    return {
      key: item.period_key,
      text:
        item.days === null
          ? t("close.cockpit.kpi.inProgress", { period: name })
          : t("close.cockpit.kpi.days", { period: name, count: item.days }),
    };
  });
  const cell =
    "flex min-w-40 flex-col gap-1 border-s border-hairline px-4 first:border-s-0 first:ps-0";
  const figure = "num text-kpi text-fg-1";
  return (
    <section
      aria-labelledby={headingId}
      data-testid="SF-05-kpi-strip"
      className="flex flex-col gap-2 border-t border-hairline pt-3"
    >
      <h2 id={headingId} className="text-caption text-fg-3">
        {t("close.cockpit.kpi.heading")}
      </h2>
      <dl className="flex flex-wrap gap-y-3">
        <div className={cell}>
          <dt className="text-caption text-fg-3">{t("close.cockpit.kpi.blockers")}</dt>
          <dd className={figure}>
            {blockers === null ? NO_VALUE : formatNumber(blockers, { kind: "count" })}
          </dd>
        </div>
        <div className={cell}>
          <dt className="text-caption text-fg-3">{t("close.cockpit.kpi.checklist")}</dt>
          <dd className="text-kpi text-fg-1">
            {t("close.cockpit.kpi.checklistValue", {
              passed: formatNumber(passed, { kind: "count" }),
              total: formatNumber(checklist.length, { kind: "count" }),
            })}
          </dd>
        </div>
        <div className={cell}>
          <dt className="text-caption text-fg-3">{t("close.cockpit.kpi.reconciliations")}</dt>
          <dd className="text-kpi text-fg-1">
            {t("close.cockpit.kpi.reconciliationsValue", {
              reviewed: formatNumber(reviewed.reviewed, { kind: "count" }),
              required: formatNumber(reviewed.required, { kind: "count" }),
            })}
          </dd>
        </div>
        <div className={cell}>
          <dt className="text-caption text-fg-3">
            {t("close.cockpit.kpi.difference", { currency: difference.currency })}
          </dt>
          <dd className={figure}>{differenceText}</dd>
        </div>
        <div data-testid="SF-05-kpi-days-to-close" className={cell}>
          <dt className="text-caption text-fg-3">{t("close.cockpit.kpi.daysToClose")}</dt>
          {days.map((item) => (
            <dd key={item.key} className="text-body-sm text-fg-2">
              {item.text}
            </dd>
          ))}
        </div>
      </dl>
    </section>
  );
}

// ---------------------------------------------------------------------------------------------------
// Period commands (§1.1 "Interactions"); `If-Match` of the period state on each.

function TransitionDialog({
  period,
  kind,
  label,
  onClose,
}: {
  readonly period: Period;
  readonly kind: "open" | "start";
  readonly label: string;
  readonly onClose: () => void;
}) {
  const formId = useId();
  const toast = useToast();
  const [comment, setComment] = useState("");
  const command = useCommand({
    method: "POST",
    path: periodCommandPath(period.id, kind === "open" ? "open" : "start-close"),
    ifMatch: rowIfMatch(period.row_version),
    invalidates: [EVERY_PERIOD],
  });
  const copy = { entity: period.entity.code, period: label };
  const submit = async () => {
    const text = comment.trim();
    const outcome = await command.submit({ comment: text === "" ? null : text });
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t(`close.cockpit.${kind}.done`, copy) });
      onClose();
    }
  };
  return (
    <Modal
      open
      variant="form"
      title={t(`close.cockpit.${kind}.title`, copy)}
      description={t(`close.cockpit.${kind}.description`, copy)}
      primaryAction={{
        label: t(kind === "open" ? "close.action.open" : "close.action.startSoftClose"),
        form: formId,
      }}
      submitting={command.pending}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <RefusalBanner problem={command.problem} conflict={command.banner} />
        <TextField
          name={`period-${kind}-comment`}
          label={t("close.cockpit.comment")}
          optional
          multiline
          value={comment}
          onChange={setComment}
        />
      </form>
    </Modal>
  );
}

type EndReason = "CLOSE_RESTARTED" | "DATA_CORRECTION_PENDING" | "OTHER";
const END_REASONS: readonly EndReason[] = ["CLOSE_RESTARTED", "DATA_CORRECTION_PENDING", "OTHER"];

/** SB-R-05 "End soft close": reason select, comment of at least 10 characters, Danger. */
function EndSoftCloseDialog({
  period,
  label,
  onClose,
}: {
  readonly period: Period;
  readonly label: string;
  readonly onClose: () => void;
}) {
  const [reason, setReason] = useState<EndReason | null>(null);
  const [comment, setComment] = useState("");
  const [attempted, setAttempted] = useState(false);
  const command = useCommand({
    method: "POST",
    path: periodCommandPath(period.id, "cancel-close"),
    ifMatch: rowIfMatch(period.row_version),
    invalidates: [EVERY_PERIOD],
  });
  const submit = async () => {
    setAttempted(true);
    if (reason === null || reasonError(comment) !== null) {
      return;
    }
    const outcome = await command.submit({ reason_code: reason, comment: comment.trim() });
    if (outcome.kind === "succeeded") {
      onClose();
    }
  };
  return (
    <Modal
      open
      variant="confirmation"
      title={t("close.cockpit.end.title", { period: label })}
      description={t(
        // SCREENS_B §1.1 rev 1.49: a period that has been locked before is under its REOPEN
        // record and returns to reopened, not to open (04 §16.8 rev 1.170).
        period.current_lock?.kind === "REOPEN"
          ? "close.cockpit.end.descriptionReopened"
          : "close.cockpit.end.description",
      )}
      primaryAction={{
        label: t("close.action.endSoftClose"),
        destructive: true,
        onAction: () => void submit(),
      }}
      submitting={command.pending}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        <RefusalBanner problem={command.problem} conflict={command.banner} />
        <SelectField
          name="end-soft-close-reason"
          label={t("close.cockpit.end.reason")}
          options={END_REASONS.map((value) => ({
            value,
            label: t(`close.cockpit.end.reasonCode.${value}`),
          }))}
          value={reason}
          onChange={setReason}
          error={attempted && reason === null ? t("close.cockpit.end.reasonError") : null}
        />
        <ReasonField
          name="end-soft-close-comment"
          label={t("close.cockpit.end.comment")}
          value={comment}
          onChange={setComment}
          showError={attempted}
        />
      </div>
    </Modal>
  );
}

/** J-13.13 "Submit for lock": close gates, certification comment; a 409 lists the failing gates (ERR-14). */
function SubmitForLockDialog({
  cockpit,
  label,
  onClose,
  onFocusGate,
}: {
  readonly cockpit: PeriodCockpit;
  readonly label: string;
  readonly onClose: () => void;
  readonly onFocusGate: (item: ChecklistItem) => void;
}) {
  const period = cockpit.period;
  const formId = useId();
  const toast = useToast();
  const [comment, setComment] = useState("");
  const [attempted, setAttempted] = useState(false);
  const command = useCommand({
    method: "POST",
    path: periodCommandPath(period.id, "request-lock"),
    ifMatch: rowIfMatch(period.row_version),
    invalidates: [EVERY_PERIOD],
  });
  const submit = async () => {
    setAttempted(true);
    if (reasonError(comment) !== null) {
      return;
    }
    const outcome = await command.submit({
      certification_comment: comment.trim(),
    } satisfies PeriodLockRequestIn);
    if (outcome.kind === "succeeded") {
      toast.show({
        tone: "positive",
        message: t("close.cockpit.submitLock.done", { period: label }),
      });
      onClose();
    }
  };
  const problem = command.problem;
  const failures =
    problem !== null && problem.slug === "close-gates-failed" ? problem.errors : null;
  const failed =
    failures === null
      ? []
      : failures
          .map((error) => cockpit.checklist.find((item) => item.gate_check_code === error.rule_id))
          .filter((item): item is ChecklistItem => item !== undefined);
  return (
    <Modal
      open
      variant="form"
      title={t("close.cockpit.submitLock.title", { period: label })}
      primaryAction={{ label: t("close.action.submitLock"), form: formId }}
      submitting={command.pending}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        {failures === null ? (
          <RefusalBanner problem={problem} conflict={command.banner} />
        ) : (
          <Banner
            tone="negative"
            announce="live"
            title={t("close.cockpit.submitLock.failed", { count: failures.length })}
          >
            <p className="flex flex-wrap gap-x-3">
              {failed.map((item) => (
                // DS-DEN-03: a wrapping list of links keeps 24 px targets.
                <Button
                  key={item.id}
                  variant="link"
                  className="min-h-6"
                  onClick={() => {
                    onClose();
                    onFocusGate(item);
                  }}
                >
                  {gateLabel(item)}
                </Button>
              ))}
            </p>
          </Banner>
        )}
        <GateTable checklist={cockpit.checklist} />
        <ReasonField
          name="submit-lock-comment"
          label={t("close.cockpit.submitLock.comment")}
          value={comment}
          onChange={setComment}
          showError={attempted}
        />
      </form>
    </Modal>
  );
}

/** SB-R-05 "Permanently lock". */
function PermanentLockDialog({
  period,
  label,
  bookLabel: book,
  onClose,
}: {
  readonly period: Period;
  readonly label: string;
  readonly bookLabel: string;
  readonly onClose: () => void;
}) {
  const [comment, setComment] = useState("");
  const [attempted, setAttempted] = useState(false);
  const command = useCommand({
    method: "POST",
    path: periodCommandPath(period.id, "request-permanent-lock"),
    ifMatch: rowIfMatch(period.row_version),
    invalidates: [EVERY_PERIOD],
  });
  const submit = async () => {
    setAttempted(true);
    if (reasonError(comment) !== null) {
      return;
    }
    const outcome = await command.submit({
      comment: comment.trim(),
    } satisfies PeriodPermanentLockRequestIn);
    if (outcome.kind === "succeeded") {
      onClose();
    }
  };
  const copy = { entity: period.entity.code, period: label, book };
  return (
    <Modal
      open
      variant="confirmation"
      title={t("close.cockpit.permanentLock.title", copy)}
      description={t("close.cockpit.permanentLock.description", copy)}
      primaryAction={{
        label: t("close.cockpit.permanentLock.confirm"),
        destructive: true,
        onAction: () => void submit(),
      }}
      submitting={command.pending}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        <RefusalBanner problem={command.problem} conflict={command.banner} />
        <ReasonField
          name="permanent-lock-comment"
          label={t("close.cockpit.permanentLock.comment")}
          value={comment}
          onChange={setComment}
          showError={attempted}
        />
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------------------------------------
// The Checklist tab.

export function CloseCockpitPage() {
  return <CockpitFrame tab="checklist">{(context) => <ChecklistTab {...context} />}</CockpitFrame>;
}

function BlockersTable({
  rows,
  onFocusTask,
}: {
  readonly rows: readonly BlockerRow[];
  readonly onFocusTask: (item: ChecklistItem) => void;
}) {
  if (rows.length === 0) {
    return (
      <div
        data-testid="SF-05-grid-blockers"
        className="rounded-md border border-hairline bg-surface px-4 pb-4"
      >
        <EmptyState
          title={t("close.cockpit.blockers.emptyTitle")}
          description={t("close.cockpit.blockers.emptyDescription")}
          headingLevel={3}
        />
      </div>
    );
  }
  const total = rows.reduce((sum, row) => sum + row.count, 0);
  return (
    <div
      data-testid="SF-05-grid-blockers"
      className="overflow-x-auto rounded-md border border-hairline bg-surface"
    >
      <table className="w-full border-collapse">
        <caption className="px-3 py-2 text-start text-title-sm text-fg-1">
          {t("close.cockpit.blockers.caption", { total: formatNumber(total, { kind: "count" }) })}
        </caption>
        <thead>
          <tr className="border-b border-hairline">
            <th scope="col" className={`${CELL} text-start text-caption text-fg-3`}>
              {t("close.cockpit.blockers.column.blocker")}
            </th>
            <th scope="col" className={`${CELL} text-end text-caption text-fg-3`}>
              {t("close.cockpit.blockers.column.count")}
            </th>
            <th scope="col" className={`${CELL} text-start text-caption text-fg-3`}>
              {t("close.cockpit.blockers.column.owner")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const label = t(`close.cockpit.blockers.label.${row.key}`);
            const count = formatNumber(row.count, { kind: "count" });
            let name: ReactNode = label;
            if (row.link !== null) {
              name = (
                <Link
                  to={row.link.href}
                  aria-label={t("close.cockpit.blockers.linkName", {
                    label,
                    total: count,
                    destination: row.link.destination,
                  })}
                  className="text-accent-fg hover:underline"
                >
                  {label}
                </Link>
              );
            } else if (row.task !== null) {
              const task = row.task;
              name = (
                <Button
                  variant="link"
                  aria-label={t("close.cockpit.blockers.linkName", {
                    label,
                    total: count,
                    destination: t("close.cockpit.blockers.destination.checklist"),
                  })}
                  onClick={() => onFocusTask(task)}
                >
                  {label}
                </Button>
              );
            }
            return (
              <tr
                key={row.key}
                data-testid={`SF-05-row-${row.key}`}
                className="border-b border-hairline last:border-b-0"
              >
                <th scope="row" className={`${CELL} text-start font-normal text-fg-1`}>
                  {name}
                </th>
                <td className={`${CELL} num text-end text-fg-1`}>{count}</td>
                <td className={`${CELL} whitespace-nowrap text-fg-2`}>{row.owner}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

type TaskAction = { readonly kind: "sign" | "waive"; readonly item: ChecklistItem };

function ChecklistTab({
  cockpit,
  permissions,
  blockers,
  blockersError,
  retryBlockers,
  focusRow,
}: CockpitContext) {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const built = useBuiltPaths();
  const [action, setAction] = useState<TaskAction | null>(null);
  const period = cockpit.period;
  const canClose = permissions.includes(PERIOD_CLOSE_PERMISSION);
  const params = new URLSearchParams(location.search);
  const taskKey = params.get("drawer") === "task" ? params.get("task") : null;
  const drawerItem =
    taskKey === null
      ? null
      : (cockpit.checklist.find((item) => checklistRowKey(item) === taskKey) ?? null);
  // Search updates keep raw values, so `f.*` operator colons stay unencoded (SCR-URL-20).
  const openTask = (item: ChecklistItem | null) => {
    void navigate(
      {
        search: withParams(location.search, {
          drawer: item === null ? null : "task",
          task: item === null ? null : encodeURIComponent(checklistRowKey(item)),
        }),
      },
      { replace: true },
    );
  };

  const source: GridSource<ChecklistItem> = {
    queryKey: queryKey("periods", "tenant", { id: period.id, view: "checklist-grid" }),
    fetchPage: async () => {
      const data = await queryClient.fetchQuery({
        queryKey: cockpitKey(period.id),
        queryFn: () => fetchCockpit(period.id),
      });
      return {
        items: data.checklist,
        nextCursor: null,
        total: { count: data.checklist.length, capped: false },
      };
    },
  };
  const tasks = cockpit.checklist.filter((item) => item.gate_kind === "MANUAL").length;
  const gates = cockpit.checklist.length - tasks;

  const columns: readonly GridColumn<ChecklistItem>[] = [
    {
      id: "status",
      header: t("close.cockpit.checklist.column.status"),
      kind: "status",
      value: (item) => item.status,
      render: (item) => (
        <span className="inline-flex items-center gap-1.5">
          <ChecklistChip status={item.status} />
          {item.waiver_approval_request_id === null ? null : (
            <StatusChip status="Pending approval" />
          )}
        </span>
      ),
      width: 150,
    },
    {
      id: "gate",
      header: t("close.cockpit.checklist.column.gate"),
      kind: "text",
      value: (item) => gateLabel(item),
      render: (item) => (
        <Button variant="link" tabIndex={-1} onClick={() => openTask(item)}>
          {gateLabel(item)}
        </Button>
      ),
      width: 300,
    },
    {
      id: "kind",
      header: t("close.cockpit.checklist.column.kind"),
      kind: "text",
      value: (item) => item.gate_kind,
      render: (item) => <OutlineChip label={t(`close.cockpit.checklist.kind.${item.gate_kind}`)} />,
      width: 120,
    },
    {
      id: "count",
      header: t("close.cockpit.checklist.column.count"),
      kind: "number",
      value: (item) =>
        item.gate_kind === "MANUAL" || item.result === null || item.result.count === null
          ? null
          : String(item.result.count),
      render: (item) =>
        item.gate_kind === "MANUAL" || item.result === null || item.result.count === null ? (
          <span className="text-fg-3">{NO_VALUE}</span>
        ) : (
          <span className="num">{formatNumber(item.result.count, { kind: "count" })}</span>
        ),
      width: 96,
    },
    {
      id: "owner",
      header: t("close.cockpit.checklist.column.owner"),
      kind: "user",
      value: (item) => item.owner?.display_name ?? null,
      width: 160,
    },
    {
      id: "due",
      header: t("close.cockpit.checklist.column.due"),
      kind: "date",
      value: (item) => item.due_date,
      render: (item) => formatDate(item.due_date),
      width: 120,
    },
    {
      id: "signed",
      header: t("close.cockpit.checklist.column.signed"),
      kind: "text",
      value: (item) => item.signoff?.signer.display_name ?? null,
      render: (item) =>
        item.signoff === null ? (
          <span className="text-fg-3">{NO_VALUE}</span>
        ) : (
          <span data-volatile="">
            {`${item.signoff.signer.display_name} · ${formatTimestamp(item.signoff.signed_at)}`}
          </span>
        ),
      width: 260,
    },
    {
      id: "evaluated",
      header: t("close.cockpit.checklist.column.evaluated"),
      kind: "timestamp",
      value: (item) => item.result?.evaluated_at ?? null,
      render: (item) =>
        item.result === null ? (
          <span className="text-fg-3">{NO_VALUE}</span>
        ) : (
          <span data-volatile="">{formatTimestamp(item.result.evaluated_at)}</span>
        ),
      width: 200,
    },
    {
      id: "actions",
      header: t("close.cockpit.checklist.column.actions"),
      kind: "text",
      value: () => null,
      render: (item) => {
        const open = !isCleared(item);
        return (
          <span className="inline-flex items-center gap-2">
            {canClose && open && item.gate_kind === "MANUAL" ? (
              <Button
                variant="ghost"
                size="sm"
                tabIndex={-1}
                onClick={() => setAction({ kind: "sign", item })}
              >
                {t("close.cockpit.checklist.sign")}
              </Button>
            ) : null}
            {canClose && open && item.is_waivable && item.waiver_approval_request_id === null ? (
              <Button
                variant="ghost"
                size="sm"
                tabIndex={-1}
                onClick={() => setAction({ kind: "waive", item })}
              >
                {t("close.cockpit.checklist.waive")}
              </Button>
            ) : null}
            {item.waiver_approval_request_id !== null && built.has(APPROVAL_REQUEST_ROUTE) ? (
              <Link
                to={`/approvals/requests/${item.waiver_approval_request_id}`}
                tabIndex={-1}
                className="text-body-sm text-accent-fg hover:underline"
              >
                {t("close.cockpit.checklist.viewRequest")}
              </Link>
            ) : null}
          </span>
        );
      },
      width: 280,
    },
  ];

  let blockerRegion: ReactNode;
  if (blockersError !== null) {
    blockerRegion = (
      <RetryBanner
        title={t("close.cockpit.blockers.loadError")}
        problem={blockersError}
        onRetry={retryBlockers}
      />
    );
  } else if (blockers === null) {
    blockerRegion = <Skeleton region={t("close.cockpit.blockers.region")} shape="rows" count={4} />;
  } else {
    blockerRegion = <BlockersTable rows={blockers} onFocusTask={focusRow} />;
  }

  return (
    <div className="grid grid-cols-1 items-start gap-4 min-[1440px]:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]">
      <div>{blockerRegion}</div>
      <div className="flex min-h-96 flex-col">
        <DataGrid<ChecklistItem>
          name="checklist"
          title={t("close.cockpit.checklist.title")}
          errorTitle={t("close.cockpit.checklist.loadError")}
          countLabel={() => t("close.cockpit.checklist.count", { gates, count: tasks })}
          columns={columns}
          source={source}
          rowKey={(item) => item.id}
          rowLabel={(item) => gateLabel(item)}
          testIdPrefix="SF-05"
          rowTestKey={(item) => checklistRowKey(item)}
          emptyState={
            <EmptyState
              title={t("close.cockpit.checklist.emptyTitle")}
              description={t("close.cockpit.checklist.emptyDescription")}
              headingLevel={3}
            />
          }
        />
      </div>
      {drawerItem === null ? null : <TaskDrawer item={drawerItem} onClose={() => openTask(null)} />}
      {action?.kind === "sign" ? (
        <SignTaskDialog period={period} item={action.item} onClose={() => setAction(null)} />
      ) : null}
      {action?.kind === "waive" ? (
        <WaiverDialog period={period} item={action.item} onClose={() => setAction(null)} />
      ) : null}
    </div>
  );
}

/** §1.1 "Task details" informational drawer (`drawer=task`). */
function TaskDrawer({
  item,
  onClose,
}: {
  readonly item: ChecklistItem;
  readonly onClose: () => void;
}) {
  const built = useBuiltPaths();
  return (
    <Drawer
      open
      variant="docked"
      title={gateLabel(item)}
      subtitle={t(`close.cockpit.checklist.kind.${item.gate_kind}`)}
      initialFocus="title"
      onClose={onClose}
    >
      <dl data-testid="SF-05-drawer-task" className="flex flex-col gap-3">
        <ReadOnlyItem label={t("close.cockpit.task.status")}>
          <ChecklistChip status={item.status} />
        </ReadOnlyItem>
        <ReadOnlyItem label={t("close.cockpit.task.result")}>
          {item.result?.detail ?? NO_VALUE}
        </ReadOnlyItem>
        <ReadOnlyItem label={t("close.cockpit.checklist.column.owner")}>
          {item.owner?.display_name ?? NO_VALUE}
        </ReadOnlyItem>
        <ReadOnlyItem label={t("close.cockpit.checklist.column.due")}>
          {formatDate(item.due_date)}
        </ReadOnlyItem>
        <ReadOnlyItem label={t("close.cockpit.checklist.column.signed")}>
          {item.signoff === null
            ? NO_VALUE
            : `${item.signoff.signer.display_name} · ${formatTimestamp(item.signoff.signed_at)}`}
        </ReadOnlyItem>
        <ReadOnlyItem label={t("close.cockpit.checklist.column.evaluated")}>
          {item.result === null ? NO_VALUE : formatTimestamp(item.result.evaluated_at)}
        </ReadOnlyItem>
        {item.waiver_approval_request_id !== null && built.has(APPROVAL_REQUEST_ROUTE) ? (
          <ReadOnlyItem label={t("close.cockpit.task.waiver")}>
            <Link
              to={`/approvals/requests/${item.waiver_approval_request_id}`}
              className="text-accent-fg hover:underline"
            >
              {t("close.cockpit.checklist.viewRequest")}
            </Link>
          </ReadOnlyItem>
        ) : null}
      </dl>
    </Drawer>
  );
}

/** §1.1 "Sign task": the statement and "I confirm this statement" (OQ-B-05); MFA-verified session. */
function SignTaskDialog({
  period,
  item,
  onClose,
}: {
  readonly period: Period;
  readonly item: ChecklistItem;
  readonly onClose: () => void;
}) {
  const toast = useToast();
  const checkboxId = useId();
  const [accepted, setAccepted] = useState(false);
  const command = useCommand({
    method: "POST",
    path: periodCommandPath(period.id, `checklist/${item.id}/sign`),
    ifMatch: rowIfMatch(period.row_version),
    invalidates: [EVERY_PERIOD],
  });
  const label = periodLabel(period.period);
  const submit = async () => {
    const outcome = await command.submit({ statement_accepted: accepted });
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("close.cockpit.sign.done", { task: item.name }) });
      onClose();
    }
  };
  return (
    <Modal
      open
      variant="confirmation"
      title={t("close.cockpit.sign.title", { task: item.name })}
      description={t("close.cockpit.sign.statement", { entity: period.entity.code, period: label })}
      primaryAction={{ label: t("close.cockpit.checklist.sign"), onAction: () => void submit() }}
      submitting={command.pending}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        <RefusalBanner problem={command.problem} conflict={command.banner} />
        <label htmlFor={checkboxId} className="flex items-center gap-2 text-body-sm text-fg-1">
          <input
            id={checkboxId}
            type="checkbox"
            checked={accepted}
            onChange={(event) => {
              setAccepted(event.target.checked);
            }}
            className="size-4"
          />
          {t("close.cockpit.sign.confirm")}
        </label>
      </div>
    </Modal>
  );
}

/** SB-R-05 "Request waiver". */
function WaiverDialog({
  period,
  item,
  onClose,
}: {
  readonly period: Period;
  readonly item: ChecklistItem;
  readonly onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const command = useCommand({
    method: "POST",
    path: periodCommandPath(period.id, `checklist/${item.id}/waive`),
    ifMatch: rowIfMatch(period.row_version),
    invalidates: [EVERY_PERIOD],
  });
  const submit = async () => {
    setAttempted(true);
    if (reasonError(reason) !== null) {
      return;
    }
    const outcome = await command.submit({ reason: reason.trim() });
    if (outcome.kind === "succeeded") {
      onClose();
    }
  };
  return (
    <Modal
      open
      variant="confirmation"
      title={t("close.cockpit.waive.title", { gate: gateLabel(item) })}
      description={t("close.cockpit.waive.description")}
      primaryAction={{
        label: t("close.cockpit.checklist.waive"),
        destructive: true,
        onAction: () => void submit(),
      }}
      submitting={command.pending}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        <RefusalBanner problem={command.problem} conflict={command.banner} />
        <ReasonField
          name="checklist-waiver-reason"
          label={t("close.cockpit.waive.reason")}
          value={reason}
          onChange={setReason}
          showError={attempted}
        />
      </div>
    </Modal>
  );
}
