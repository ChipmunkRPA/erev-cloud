// SF-05:history Close history (SCREENS_B §1.4; §0.4 E-04; SCREENS RT-101, RT-32, RT-57, SCR-URL-12,
// SCR-PERM-02, SCR-ST-03, SCR-ST-05; DESIGN_SYSTEM DS-CMP-09, DS-CMP-10, DS-CMP-12, DS-FMT-17, DS-FMT-23,
// DS-A11Y-12; 04 API-R-18 `locks` and `transitions`, T-CLS-04, E-63, table 3.4-R, API-R-09; PRD BR-CLS-07,
// J-14.7; supervisor ruling R-94 (d); BUILD_SPEC CLO-24). The History tab of the cockpit: the period's
// lock, reopen and permanent-lock records with their head sequences, snapshot manifest and the instant
// the snapshot was frozen at, and the audited changes of the period's state. A record names the person
// who made it (API-S-Actor) and its approval request by number; the re-lock's difference opens as the
// report `variance_between_closes`. Rev 1.67 (04 §16.8 API-S-PeriodLock, rev 1.207; item
// CLO-LOCKS-READ-1): a record and a transition state the number of their request, so every reader of
// the history reads it and it is a link where the reader may read the request itself (API-R-09); a
// record states the hash of its ledger head, the gate results it certified and the datasets it froze.
import { useInfiniteQuery, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useCallback, useEffect, useId, useMemo } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import {
  type GridColumn,
  type GridSource,
  initialColumnState,
} from "../../components/data-grid/types";
import { EmptyState } from "../../components/feedback/EmptyState";
import { CopySimple, ICONS } from "../../components/icons/registry";
import { NoValue } from "../../components/money/Num";
import { Timeline, type TimelineEvent } from "../../components/record/Timeline";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { chipFor, statusMessageKey } from "../../components/ui/StatusChip";
import { Tooltip } from "../../components/ui/Tooltip";
import { announce } from "../../lib/a11y/announce";
import {
  type Approval,
  approvalKey,
  fetchApproval,
  FILE_CONTENT_PATH,
  requestRoute,
} from "../../lib/api/queries/approvals";
import {
  fetchPeriodLocks,
  fetchPeriodTransitions,
  locksKey,
  PERIOD_CLOSE_PERMISSION,
  PERIOD_LOCK_PERMISSION,
  PERIOD_REOPEN_PERMISSION,
  type PeriodLockRow,
  type PeriodTransition,
  transitionsKey,
} from "../../lib/api/queries/periods";
import {
  REPORT_EXPORT_PERMISSION,
  REPORT_ROUTE,
  REPORT_RUN_PERMISSION,
} from "../../lib/api/queries/reports";
import { type Period, periodLabel, type PeriodState } from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import { formatNumber, formatTimestamp } from "../../lib/format";
import { hasMessage, t } from "../../lib/i18n/t";
import { withParams } from "../../lib/url/params";
import { hashPrefix } from "../reports/viewer/RunStamp";
import { useBuiltPaths } from "../settings/index";
import { bookLabel, type CockpitContext, CockpitFrame, Mono, RetryBanner } from "./cockpit";
import { ChecklistChip } from "./lock-drawer";

/** SCREENS RT-57 SF-12:request, the target of a record's approval. */
const APPROVAL_REQUEST_ROUTE = "/approvals/requests/:requestId";
/** SCREENS_B RPT-38: the re-lock's difference, between the two locks a record names. */
const DIFF_REPORT = "variance_between_closes";
/** SCREENS_B §1.4 "Roles and permissions": the stored diff file downloads with either. */
const EVIDENCE_EXPORT_PERMISSION = "evidence.export";
/**
 * API-R-09: a period's lock, reopen and permanent-lock requests are visible to those who may decide
 * them (`period.lock`, `period.reopen_approve`), to their preparer (a holder of `period.close` or of
 * `period.reopen_request`) and to those who decided them. A reader who holds none of these cannot
 * see any, so none is asked for: the API would answer 404 by name for each.
 */
const REQUEST_PERMISSIONS: ReadonlySet<string> = new Set([
  PERIOD_CLOSE_PERMISSION,
  PERIOD_LOCK_PERMISSION,
  PERIOD_REOPEN_PERMISSION,
  "period.reopen_approve",
]);
/** SCR-URL-12: the informational drawer of a lock record. */
const DRAWER_PARAM = "drawer";
const LOCK_DRAWER = "lock";

/**
 * E-110 reason labels (04 table 3.4-R). A period's records carry the reasons of a reopen and of an
 * ended soft close; the other codes of the enum read with the labels their own screens give them.
 */
const REASON_KEYS: Readonly<Record<NonNullable<PeriodLockRow["reason_code"]>, string>> = {
  AUDIT_ADJUSTMENT: "close.reopen.reasonCode.AUDIT_ADJUSTMENT",
  ERROR_CORRECTION: "close.reopen.reasonCode.ERROR_CORRECTION",
  LATE_SOURCE_DATA: "close.reopen.reasonCode.LATE_SOURCE_DATA",
  OTHER: "close.reopen.reasonCode.OTHER",
  CLOSE_RESTARTED: "close.cockpit.end.reasonCode.CLOSE_RESTARTED",
  DATA_CORRECTION_PENDING: "close.cockpit.end.reasonCode.DATA_CORRECTION_PENDING",
  DUPLICATE: "contracts.reasonCode.DUPLICATE",
  CREATED_IN_ERROR: "contracts.reasonCode.CREATED_IN_ERROR",
  CUSTOMER_CANCELLED: "contracts.reasonCode.CUSTOMER_CANCELLED",
  DATA_CORRECTION: "contracts.reasonCode.DATA_CORRECTION",
  ESTIMATE_CORRECTION: "contracts.reasonCode.ESTIMATE_CORRECTION",
};

export function CloseHistoryPage() {
  return <CockpitFrame tab="history">{(context) => <HistoryTab {...context} />}</CockpitFrame>;
}

function reasonLabel(code: PeriodLockRow["reason_code"]): string | null {
  return code === null ? null : t(REASON_KEYS[code]);
}

function kindLabel(kind: PeriodLockRow["kind"]): string {
  return t(`close.history.kind.${kind}`);
}

/** The E-04 chip word of a period state, in the reader's language. */
function stateWord(state: PeriodState): string {
  const chip = chipFor("E-04", state);
  if (chip === null) {
    throw new Error(`No status chip for E-04 ${state}`);
  }
  return t(statusMessageKey(chip.status));
}

/** The approval requests the records name, by id: the request, or null where the reader may not read it. */
type Approvals = ReadonlyMap<string, Approval | null>;

function useApprovals(ids: readonly string[], mayRead: boolean): Approvals {
  // One entry per id: the request, null where the API refused it, undefined while it is read. The
  // combined result keeps its identity between renders that change nothing, so the grid's columns do.
  const found = useQueries({
    queries: (mayRead ? ids : []).map((id) => ({
      queryKey: approvalKey(id),
      queryFn: () => fetchApproval(id),
      // API-R-09: a request outside the reader's visibility answers 404 by name; it is not retried.
      retry: false,
    })),
    combine: (results) =>
      results.map((result) =>
        result.data !== undefined ? result.data : result.isError ? null : undefined,
      ),
  });
  return useMemo(() => {
    const map = new Map<string, Approval | null>();
    ids.forEach((id, index) => {
      const request = mayRead ? found[index] : null;
      if (request !== undefined) {
        map.set(id, request);
      }
    });
    return map;
  }, [ids, mayRead, found]);
}

function HistoryTab({ cockpit, permissions, ctxSearch }: CockpitContext) {
  const location = useLocation();
  const navigate = useNavigate();
  const period = cockpit.period;
  const label = periodLabel(period.period);

  const locks = useQuery({
    queryKey: locksKey(period.id),
    queryFn: () => fetchPeriodLocks(period.id),
  });
  const transitions = useInfiniteQuery({
    queryKey: transitionsKey(period.id),
    queryFn: ({ pageParam }) => fetchPeriodTransitions(period.id, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.nextCursor,
  });
  const moves = useMemo(
    () => (transitions.data?.pages ?? []).flatMap((page) => page.items),
    [transitions.data],
  );
  const approvalIds = useMemo(() => {
    const ids = new Set<string>();
    for (const lock of locks.data ?? []) {
      ids.add(lock.approval_request_id);
    }
    for (const move of moves) {
      if (move.approval_request_id !== null) {
        ids.add(move.approval_request_id);
      }
    }
    return [...ids].sort();
  }, [locks.data, moves]);
  const approvals = useApprovals(
    approvalIds,
    permissions.some((permission) => REQUEST_PERMISSIONS.has(permission)),
  );

  // SCR-URL-12: the URL names the drawer; the record it shows is the one chosen on this page, and a
  // link that carries `drawer=lock` alone opens the newest record.
  const params = new URLSearchParams(location.search);
  const drawerOpen = params.get(DRAWER_PARAM) === LOCK_DRAWER;
  const chosen = chosenLock(location.state);
  const selected = drawerOpen
    ? ((locks.data ?? []).find((lock) => lock.id === chosen) ?? locks.data?.[0])
    : undefined;
  const stale = drawerOpen && locks.data !== undefined && selected === undefined;
  useEffect(() => {
    if (stale) {
      void navigate(
        { search: withParams(location.search, { [DRAWER_PARAM]: null }) },
        { replace: true },
      );
    }
  }, [stale, navigate, location.search]);
  const search = location.search;
  const openLock = useCallback(
    (lockId: string) => {
      void navigate(
        { search: withParams(search, { [DRAWER_PARAM]: LOCK_DRAWER }) },
        { state: { lock: lockId } satisfies LockChoice },
      );
    },
    [navigate, search],
  );
  const closeLock = () => {
    void navigate(
      { search: withParams(location.search, { [DRAWER_PARAM]: null }) },
      { replace: true },
    );
  };

  return (
    // SCREENS_B §1.4: the locks above the transitions; from 1440 px the transitions beside them, in a
    // column of 20 rem. The shown columns of the grid take 808 px (`LOCKS_ROOM_1440`), which the
    // second column holds at 1440 px.
    <div className="grid grid-cols-1 items-start gap-4 min-[1440px]:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
      <div className="min-w-0 min-[1440px]:col-start-2 min-[1440px]:row-start-1">
        <Locks
          period={period}
          periodLabel={label}
          locks={locks.data}
          error={locks.isError ? locks.error : null}
          onRetry={() => void locks.refetch()}
          approvals={approvals}
          permissions={permissions}
          ctxSearch={ctxSearch}
          onOpen={openLock}
        />
      </div>
      <div className="min-w-0 min-[1440px]:col-start-1 min-[1440px]:row-start-1">
        <Transitions
          moves={moves}
          status={transitions.isPending ? "loading" : transitions.isError ? "error" : "ready"}
          error={transitions.error}
          onRetry={() => void transitions.refetch()}
          hasOlder={transitions.hasNextPage}
          loadingOlder={transitions.isFetchingNextPage}
          onLoadOlder={() => void transitions.fetchNextPage()}
          approvals={approvals}
        />
      </div>
      {selected === undefined ? null : (
        <LockDrawer
          key={selected.id}
          lock={selected}
          locks={locks.data ?? []}
          approval={approvals.get(selected.approval_request_id) ?? null}
          permissions={permissions}
          ctxSearch={ctxSearch}
          onOpen={openLock}
          onClose={closeLock}
        />
      )}
    </div>
  );
}

interface LockChoice {
  readonly lock: string;
}

/** The lock record a link on this page chose, from the navigation state. */
function chosenLock(state: unknown): string | null {
  if (typeof state === "object" && state !== null && "lock" in state) {
    const lock = (state as { readonly lock: unknown }).lock;
    return typeof lock === "string" ? lock : null;
  }
  return null;
}

// ---------------------------------------------------------------------------------------------------
// State transitions.

interface TransitionsProps {
  readonly moves: readonly PeriodTransition[];
  readonly status: "loading" | "error" | "ready";
  readonly error: unknown;
  readonly onRetry: () => void;
  readonly hasOlder: boolean;
  readonly loadingOlder: boolean;
  readonly onLoadOlder: () => void;
  readonly approvals: Approvals;
}

function transitionEvent(
  move: PeriodTransition,
  approvals: Approvals,
  requestsBuilt: boolean,
): TimelineEvent {
  const chip = chipFor("E-04", move.to_state);
  if (chip === null) {
    throw new Error(`No status chip for E-04 ${move.to_state}`);
  }
  // The transition states the number of its request; it links where the reader may read the request.
  const number = move.approval_request_no;
  const approval =
    move.approval_request_id === null || !requestsBuilt
      ? null
      : (approvals.get(move.approval_request_id) ?? null);
  const words = {
    from: move.from_state === null ? "" : stateWord(move.from_state),
    to: stateWord(move.to_state),
  };
  const key = move.from_state === null ? "first" : "moved";
  const reason = reasonLabel(move.reason_code);
  const comment =
    reason === null
      ? (move.comment ?? undefined)
      : move.comment === null
        ? t("close.history.transition.reason", { reason })
        : t("close.history.transition.reasonComment", { reason, comment: move.comment });
  return {
    id: move.id,
    at: move.created_at,
    icon: ICONS[chip.icon],
    actor: move.created_by.display_name,
    actorIsPerson: move.created_by.kind === "USER",
    verb:
      number === null
        ? t(`close.history.transition.${key}`, words)
        : approval === null
          ? t(`close.history.transition.${key}ApprovedNo`, { ...words, request: number })
          : t(`close.history.transition.${key}Approved`, words),
    object:
      number === null || approval === null
        ? undefined
        : { label: number, to: requestRoute(approval.id) },
    comment,
  };
}

function Transitions({
  moves,
  status,
  error,
  onRetry,
  hasOlder,
  loadingOlder,
  onLoadOlder,
  approvals,
}: TransitionsProps) {
  const headingId = useId();
  const built = useBuiltPaths();
  const requestsBuilt = built.has(APPROVAL_REQUEST_ROUTE);
  const events = moves.map((move) => transitionEvent(move, approvals, requestsBuilt));
  return (
    <section
      aria-labelledby={headingId}
      data-testid="SF-05-timeline-transitions"
      className="flex flex-col gap-2 rounded-md border border-hairline bg-surface p-4"
    >
      <h2 id={headingId} className="text-title-sm text-fg-1">
        {t("close.history.transitions.title")}
      </h2>
      <Timeline
        events={events}
        status={status}
        errorState={
          <RetryBanner
            title={t("close.history.transitions.loadError")}
            problem={error}
            onRetry={onRetry}
          />
        }
        hasOlder={hasOlder}
        loadingOlder={loadingOlder}
        onLoadOlder={onLoadOlder}
      />
    </section>
  );
}

// ---------------------------------------------------------------------------------------------------
// Locks.

/** DS-FMT-23: a hash as its first 8 and last 4 characters, with the full value and copy (DS-A11Y-12). */
function HashValue({ value, name }: { readonly value: string; readonly name: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <Tooltip content={value}>
        {(trigger) => (
          <span
            {...trigger}
            // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- DS-CMP-27: a tooltip trigger is focusable
            tabIndex={0}
            className="font-mono text-mono-sm text-fg-1"
          >
            {hashPrefix(value)}
          </span>
        )}
      </Tooltip>
      <Button
        variant="ghost"
        size="sm"
        icon={CopySimple}
        aria-label={t("close.history.copy", { name })}
        onClick={() => {
          void navigator.clipboard
            .writeText(value)
            .then(() => announce(t("close.history.copied", { name }), "polite"));
        }}
      />
    </span>
  );
}

function lockName(lock: PeriodLockRow): string {
  return t("close.history.lock.name", {
    kind: kindLabel(lock.kind),
    recorded: formatTimestamp(lock.created_at),
  });
}

interface DiffProps {
  readonly lock: PeriodLockRow;
  readonly permissions: readonly string[];
  readonly ctxSearch: string;
  readonly inGrid?: boolean;
}

/**
 * SF-08:report `variance_between_closes` between the lock a record follows and the record itself
 * (`p.from_period_lock_id`, `p.to_period_lock_id`), for a holder of `report.run`; null otherwise.
 */
function diffReportRoute(
  lock: PeriodLockRow,
  permissions: readonly string[],
  reportsBuilt: boolean,
  ctxSearch: string,
): string | null {
  if (
    lock.kind === "REOPEN" ||
    lock.previous_lock_id === null ||
    !reportsBuilt ||
    !permissions.includes(REPORT_RUN_PERMISSION)
  ) {
    return null;
  }
  const search = withParams(ctxSearch, {
    "p.from_period_lock_id": lock.previous_lock_id,
    "p.to_period_lock_id": lock.id,
  });
  return `/reports/${DIFF_REPORT}${search}`;
}

/**
 * SCREENS_B §1.4 "Diff report": a record that follows another lock opens the report between the two
 * (`report.run`) and downloads the stored file (`report.export` or `evidence.export`); a first lock
 * has nothing to compare with, and a reopen record changes no figure.
 */
function DiffReport({ lock, permissions, ctxSearch, inGrid = false }: DiffProps) {
  const built = useBuiltPaths();
  if (lock.kind === "REOPEN") {
    return <NoValue />;
  }
  if (lock.previous_lock_id === null) {
    return <span className="text-fg-2">{t("close.history.diff.none")}</span>;
  }
  const report = diffReportRoute(lock, permissions, built.has(REPORT_ROUTE), ctxSearch);
  const mayDownload =
    lock.diff_report_file_id !== null &&
    (permissions.includes(REPORT_EXPORT_PERMISSION) ||
      permissions.includes(EVIDENCE_EXPORT_PERMISSION));
  if (report === null && !mayDownload) {
    return <NoValue />;
  }
  return (
    <span className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
      {report !== null ? (
        <Link
          to={report}
          tabIndex={inGrid ? -1 : undefined}
          data-testid="SF-05-row-diff-report"
          className="text-accent-fg hover:underline"
        >
          {t("close.history.diff.open")}
        </Link>
      ) : null}
      {mayDownload && lock.diff_report_file_id !== null ? (
        <a
          href={`${FILE_CONTENT_PATH}/${lock.diff_report_file_id}/content`}
          download
          tabIndex={inGrid ? -1 : undefined}
          className="text-accent-fg hover:underline"
        >
          {t("close.history.diff.download")}
        </a>
      ) : null}
    </span>
  );
}

/**
 * The number of a record's request (§1.4 rev 1.67). The record states it, so it shows at once and to
 * every reader; it is a link once the request itself was read, which only a reader inside its
 * visibility can (API-R-09). A request outside the reader's row scope has no number: a dash.
 */
function ApprovalNumber({
  number,
  approval,
  inGrid = false,
}: {
  readonly number: string | null;
  readonly approval: Approval | null | undefined;
  readonly inGrid?: boolean;
}) {
  const built = useBuiltPaths();
  if (number === null) {
    return <NoValue />;
  }
  return approval !== null && approval !== undefined && built.has(APPROVAL_REQUEST_ROUTE) ? (
    <Link
      to={requestRoute(approval.id)}
      tabIndex={inGrid ? -1 : undefined}
      className="font-mono text-mono-sm text-accent-fg hover:underline"
    >
      {number}
    </Link>
  ) : (
    <Mono>{number}</Mono>
  );
}

/**
 * §1.4 "Ledger head": the sequence, described by the prefix of the hash the record states. A record of
 * a book without a seal states none, and the sequence stands alone.
 */
function LedgerHead({
  lock,
  inGrid = false,
}: {
  readonly lock: PeriodLockRow;
  readonly inGrid?: boolean;
}) {
  const sequence = formatNumber(lock.ledger_head_chain_seq, { kind: "count" });
  if (lock.ledger_head_sha256 === null) {
    return <span className="num text-fg-1">{sequence}</span>;
  }
  return (
    <Tooltip content={hashPrefix(lock.ledger_head_sha256)}>
      {(trigger) => (
        <span
          {...trigger}
          // DS-CMP-27: a tooltip trigger is focusable; inside the grid the cell holds the focus.
          tabIndex={inGrid ? -1 : 0}
          className="num text-fg-1"
        >
          {sequence}
        </span>
      )}
    </Tooltip>
  );
}

interface LocksProps {
  readonly period: Period;
  readonly periodLabel: string;
  readonly locks: readonly PeriodLockRow[] | undefined;
  readonly error: unknown;
  readonly onRetry: () => void;
  readonly approvals: Approvals;
  readonly permissions: readonly string[];
  readonly ctxSearch: string;
  readonly onOpen: (lockId: string) => void;
}

/**
 * The grid shows the wireframe's columns; the others are in its column chooser (DS-CMP-10) and in the
 * record's drawer.
 */
export const HIDDEN_LOCK_COLUMNS: readonly string[] = [
  "reason",
  "ledger_head",
  "audit_head",
  "manifest",
  "cutoff",
  "previous",
];
/**
 * The room of the locks grid at 1440 px beside the open rail: the page's 1,160 px less the activity
 * column of 20 rem and the gap, the panel's border and a scrollbar's width.
 */
export const LOCKS_ROOM_1440 = 1160 - 320 - 16 - 2 - 14;

interface LockColumnsInput {
  readonly locks: readonly PeriodLockRow[] | undefined;
  readonly approvals: Approvals;
  readonly permissions: readonly string[];
  readonly ctxSearch: string;
  /** XR-14: a link is followed where its route is built. */
  readonly requestsBuilt: boolean;
  readonly reportsBuilt: boolean;
  /** Opens a record's drawer. */
  readonly onOpen: (lockId: string) => void;
  /** Follows the link of an Approval or Diff report cell on Enter. */
  readonly navigate: (to: string) => void;
}

function Locks({
  period,
  periodLabel: label,
  locks,
  error,
  onRetry,
  approvals,
  permissions,
  ctxSearch,
  onOpen,
}: LocksProps) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const built = useBuiltPaths();
  const requestsBuilt = built.has(APPROVAL_REQUEST_ROUTE);
  const reportsBuilt = built.has(REPORT_ROUTE);
  const source: GridSource<PeriodLockRow> = useMemo(
    () => ({
      // The grid reads the rows this page holds: one answer, newest first, no pages.
      queryKey: queryKey("periods", "tenant", { id: period.id, view: "locks-grid" }),
      fetchPage: async () => {
        const items = await queryClient.fetchQuery({
          queryKey: locksKey(period.id),
          queryFn: () => fetchPeriodLocks(period.id),
        });
        return { items, nextCursor: null, total: { count: items.length, capped: false } };
      },
    }),
    [queryClient, period.id],
  );
  const columns = useMemo(
    () =>
      lockColumns({
        locks,
        approvals,
        permissions,
        ctxSearch,
        requestsBuilt,
        reportsBuilt,
        onOpen,
        navigate: (to) => void navigate(to),
      }),
    [locks, approvals, permissions, ctxSearch, onOpen, navigate, requestsBuilt, reportsBuilt],
  );
  const defaultColumnState = useMemo(
    () => initialColumnState(columns, HIDDEN_LOCK_COLUMNS),
    [columns],
  );

  if (error !== null) {
    return (
      <RetryBanner title={t("close.history.locks.loadError")} problem={error} onRetry={onRetry} />
    );
  }
  const current = locks?.find((lock) => lock.kind !== "REOPEN");
  const follows = period.follows ?? null;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex min-h-48 flex-col">
        <DataGrid<PeriodLockRow>
          name="locks"
          title={t("close.history.locks.title")}
          errorTitle={t("close.history.locks.loadError")}
          countLabel={(count, formatted) => t("close.history.locks.count", { count, formatted })}
          columns={columns}
          defaultColumnState={defaultColumnState}
          source={source}
          rowKey={(lock) => lock.id}
          rowLabel={lockName}
          testIdPrefix="SF-05"
          emptyState={
            // A period of the LEGACY book follows another book's close (04 API-S-Period `follows`):
            // no lock of its own is to come.
            follows === null ? (
              <EmptyState
                title={t("close.history.locks.emptyTitle")}
                description={t("close.history.locks.emptyDescription", { period: label })}
                headingLevel={3}
              />
            ) : (
              <EmptyState
                title={t("close.history.locks.followsTitle")}
                description={t("close.history.locks.followsDescription", {
                  book: bookLabel(follows.book_code),
                })}
                headingLevel={3}
              />
            )
          }
        />
      </div>
      {current === undefined ? null : <CurrentLock lock={current} />}
    </div>
  );
}

/**
 * SCREENS_B §1.4 "Grid columns: locks". Each column is as wide as its header needs beside the column
 * menu button, and a column of instants as wide as an instant needs: "01 Oct 2026 09:14 UTC" with the
 * cell padding is 186 px (measured by the report run register's e2e row at the kit's 176 px), so
 * "Recorded" is 192 px. The shown columns take `LOCKS_ROOM_1440`.
 */
export function lockColumns({
  locks,
  approvals,
  permissions,
  ctxSearch,
  requestsBuilt,
  reportsBuilt,
  onOpen,
  navigate,
}: LockColumnsInput): readonly GridColumn<PeriodLockRow>[] {
  const byId = new Map((locks ?? []).map((lock) => [lock.id, lock]));
  // Enter on a cell opens the record's drawer; the Approval and Diff report cells follow their link.
  const open = (lock: PeriodLockRow) => onOpen(lock.id);
  return [
    {
      id: "kind",
      header: t("close.history.locks.column.kind"),
      // The row's header: a record is named by its kind and the instant it was recorded.
      kind: "identifier",
      value: (lock) => kindLabel(lock.kind),
      render: (lock) => (
        <button
          type="button"
          tabIndex={-1}
          aria-label={lockName(lock)}
          onClick={() => onOpen(lock.id)}
          className="truncate text-start text-accent-fg hover:underline"
        >
          {kindLabel(lock.kind)}
        </button>
      ),
      activate: open,
      width: 120,
    },
    {
      id: "recorded",
      header: t("close.history.locks.column.recorded"),
      kind: "timestamp",
      value: (lock) => lock.created_at,
      activate: open,
      width: 192,
    },
    {
      id: "by",
      header: t("close.history.locks.column.by"),
      kind: "user",
      value: (lock) => lock.created_by.display_name,
      activate: open,
      width: 136,
    },
    {
      id: "approval",
      header: t("close.history.locks.column.approval"),
      kind: "text",
      value: (lock) => lock.approval_request_no,
      render: (lock) => (
        <ApprovalNumber
          number={lock.approval_request_no}
          approval={approvals.get(lock.approval_request_id)}
          inGrid
        />
      ),
      activate: (lock) => {
        const approval = approvals.get(lock.approval_request_id);
        const named = lock.approval_request_no !== null;
        if (named && approval !== undefined && approval !== null && requestsBuilt) {
          navigate(requestRoute(approval.id));
        } else {
          open(lock);
        }
      },
      width: 112,
    },
    {
      id: "reason",
      header: t("close.history.locks.column.reason"),
      kind: "text",
      value: (lock) => reasonLabel(lock.reason_code),
      activate: open,
      width: 152,
    },
    {
      id: "ledger_head",
      header: t("close.history.locks.column.ledgerHead"),
      kind: "number",
      numberKind: "count",
      value: (lock) => String(lock.ledger_head_chain_seq),
      render: (lock) => <LedgerHead lock={lock} inGrid />,
      activate: open,
      width: 128,
    },
    {
      id: "audit_head",
      header: t("close.history.locks.column.auditHead"),
      kind: "number",
      numberKind: "count",
      value: (lock) => String(lock.audit_head_chain_seq),
      activate: open,
      width: 120,
    },
    {
      id: "manifest",
      header: t("close.history.locks.column.manifest"),
      kind: "text",
      value: (lock) => lock.snapshot_manifest_sha256,
      render: (lock) =>
        lock.snapshot_manifest_sha256 === null ? (
          <NoValue />
        ) : (
          <Mono>{hashPrefix(lock.snapshot_manifest_sha256)}</Mono>
        ),
      activate: open,
      width: 176,
    },
    {
      id: "cutoff",
      header: t("close.history.locks.column.cutoff"),
      kind: "timestamp",
      value: (lock) => lock.cutoff_known_at,
      // To the second: the instant decides which versions the snapshot holds.
      render: (lock) =>
        lock.cutoff_known_at === null ? (
          <NoValue />
        ) : (
          <span className="num">{formatTimestamp(lock.cutoff_known_at, { seconds: true })}</span>
        ),
      activate: open,
      // With its seconds the instant is three characters longer than the 186 px of "Recorded".
      width: 216,
    },
    {
      id: "previous",
      header: t("close.history.locks.column.previous"),
      kind: "text",
      value: (lock) => {
        const previous =
          lock.previous_lock_id === null ? undefined : byId.get(lock.previous_lock_id);
        return previous === undefined ? null : lockName(previous);
      },
      activate: (lock) => onOpen(lock.previous_lock_id ?? lock.id),
      // "Reopen, recorded 01 Oct 2026 16:40 UTC": the longest name of a record another follows.
      width: 296,
    },
    {
      id: "diff",
      header: t("close.history.locks.column.diff"),
      kind: "text",
      value: (lock) =>
        lock.kind === "REOPEN"
          ? null
          : lock.previous_lock_id === null
            ? t("close.history.diff.none")
            : t("close.history.diff.open"),
      render: (lock) => (
        <DiffReport lock={lock} permissions={permissions} ctxSearch={ctxSearch} inGrid />
      ),
      activate: (lock) => {
        const to = diffReportRoute(lock, permissions, reportsBuilt, ctxSearch);
        if (to === null) {
          open(lock);
        } else {
          navigate(to);
        }
      },
      width: 248,
    },
  ];
}

/** The wireframe's line under the grid: the head sequences and the manifest of the newest lock. */
function CurrentLock({ lock }: { readonly lock: PeriodLockRow }) {
  const facts: readonly { readonly label: string; readonly value: ReactNode }[] = [
    {
      label: t("close.history.locks.column.manifest"),
      value:
        lock.snapshot_manifest_sha256 === null ? (
          <NoValue />
        ) : (
          <HashValue
            value={lock.snapshot_manifest_sha256}
            name={t("close.history.locks.column.manifest")}
          />
        ),
    },
    {
      label: t("close.history.locks.column.ledgerHead"),
      value: <LedgerHead lock={lock} />,
    },
    {
      label: t("close.history.locks.column.auditHead"),
      value: (
        <span className="num text-fg-1">
          {formatNumber(lock.audit_head_chain_seq, { kind: "count" })}
        </span>
      ),
    },
  ];
  return (
    <div role="group" aria-label={lockName(lock)} data-testid="SF-05-current-lock">
      <dl className="flex flex-wrap items-center gap-x-6 gap-y-1 px-1 text-body-sm">
        {facts.map((fact) => (
          <div key={fact.label} className="flex items-center gap-2">
            <dt className="text-fg-3">{fact.label}</dt>
            <dd>{fact.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// The record's drawer (`drawer=lock`).

interface LockDrawerProps {
  readonly lock: PeriodLockRow;
  readonly locks: readonly PeriodLockRow[];
  readonly approval: Approval | null;
  readonly permissions: readonly string[];
  readonly ctxSearch: string;
  readonly onOpen: (lockId: string) => void;
  readonly onClose: () => void;
}

const LIST = "grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-body-sm";
const CELL = "px-3 py-2 text-body-sm";
const HEAD = `${CELL} text-caption text-fg-3`;

/** The cockpit's label of a system gate; a code the catalogue does not know reads as itself. */
function gateName(code: string): string {
  const key = `close.gate.${code}`;
  return hasMessage(key) ? t(key) : code;
}

/**
 * §1.4 rev 1.67, the static table "Certification": the gate results the lock certified, as it stored
 * them and in the API's order — the gate, its status, its count and the instant it was evaluated. A
 * waived gate names its waiver's request and the count when the waiver was approved; a request
 * outside the reader's row scope has no number, as a record's own has none, and the chip stands
 * alone. A result the replay of a source lock laid over a sandbox's own is not marked (rev 1.81).
 */
function Certification({ gates }: { readonly gates: PeriodLockRow["certification"] }) {
  return (
    <div className="overflow-x-auto rounded-md border border-hairline">
      <table className="w-full border-collapse">
        <caption className="px-3 py-2 text-start text-title-sm text-fg-1">
          {t("close.history.certification.caption")}
        </caption>
        <thead>
          <tr className="border-b border-hairline">
            <th scope="col" className={`${HEAD} text-start`}>
              {t("close.gates.column.gate")}
            </th>
            <th scope="col" className={`${HEAD} text-start`}>
              {t("close.gates.column.status")}
            </th>
            <th scope="col" className={`${HEAD} text-end`}>
              {t("close.cockpit.checklist.column.count")}
            </th>
            <th scope="col" className={`${HEAD} text-start`}>
              {t("close.cockpit.checklist.column.evaluated")}
            </th>
          </tr>
        </thead>
        <tbody>
          {gates.map((gate) => {
            const request = gate.waiver_approval_request_no ?? null;
            const waived = gate.waived_count ?? null;
            return (
              <tr key={gate.gate_check_code} className="border-b border-hairline last:border-b-0">
                <th scope="row" className={`${CELL} text-start font-normal text-fg-1`}>
                  {gateName(gate.gate_check_code)}
                </th>
                <td className={CELL}>
                  <span className="flex flex-col items-start gap-1">
                    <ChecklistChip status={gate.status} />
                    {request === null || waived === null ? null : (
                      <span className="text-fg-2">
                        {t("close.history.certification.waiver", {
                          request,
                          waived: formatNumber(waived, { kind: "count" }),
                        })}
                      </span>
                    )}
                  </span>
                </td>
                <td className={`${CELL} text-end whitespace-nowrap`}>
                  {gate.count === null ? (
                    <NoValue />
                  ) : (
                    <span className="num">{formatNumber(gate.count, { kind: "count" })}</span>
                  )}
                </td>
                {/* The four columns ask for more than the drawer's 720 px at their widest: the gate's
                    label and the waiver's line break, the count and the instant do not. */}
                <td className={`${CELL} whitespace-nowrap`}>
                  <span className="num">{formatTimestamp(gate.evaluated_at)}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * §1.4 rev 1.67: the datasets the lock froze, in the API's order (E-64) — the report each is the run
 * of, its rows and the hash of its file.
 */
function Datasets({ snapshots }: { readonly snapshots: PeriodLockRow["snapshots"] }) {
  return (
    <div className="overflow-x-auto rounded-md border border-hairline">
      <table className="w-full border-collapse">
        <caption className="px-3 py-2 text-start text-title-sm text-fg-1">
          {t("close.history.datasets.caption")}
        </caption>
        <thead>
          <tr className="border-b border-hairline">
            <th scope="col" className={`${HEAD} text-start`}>
              {t("close.history.datasets.column.dataset")}
            </th>
            <th scope="col" className={`${HEAD} text-end`}>
              {t("close.history.datasets.column.rows")}
            </th>
            <th scope="col" className={`${HEAD} text-start`}>
              {t("close.history.datasets.column.hash")}
            </th>
          </tr>
        </thead>
        <tbody>
          {snapshots.map((snapshot) => {
            const dataset = t(`close.history.dataset.${snapshot.snapshot_kind}`);
            return (
              <tr key={snapshot.snapshot_kind} className="border-b border-hairline last:border-b-0">
                <th scope="row" className={`${CELL} text-start font-normal text-fg-1`}>
                  {dataset}
                </th>
                <td className={`${CELL} text-end`}>
                  <span className="num">{formatNumber(snapshot.row_count, { kind: "count" })}</span>
                </td>
                <td className={CELL}>
                  <HashValue
                    value={snapshot.file_sha256}
                    name={t("close.history.datasets.hashOf", { dataset })}
                  />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Definition({ term, children }: { readonly term: string; readonly children: ReactNode }) {
  return (
    <>
      <dt className="text-fg-3">{term}</dt>
      <dd className="min-w-0 break-words text-fg-1">{children}</dd>
    </>
  );
}

function LockDrawer({
  lock,
  locks,
  approval,
  permissions,
  ctxSearch,
  onOpen,
  onClose,
}: LockDrawerProps) {
  const previous =
    lock.previous_lock_id === null
      ? undefined
      : locks.find((item) => item.id === lock.previous_lock_id);
  const decisions = (approval?.steps ?? []).flatMap((step) => step.decisions);
  const reason = reasonLabel(lock.reason_code);
  return (
    // Wide: the record holds two tables since rev 1.67.
    <Drawer open wide title={lockName(lock)} initialFocus="title" onClose={onClose}>
      <div className="flex flex-col gap-4" data-testid="SF-05-drawer-lock">
        <dl className={LIST}>
          <Definition term={t("close.history.locks.column.kind")}>
            {kindLabel(lock.kind)}
          </Definition>
          <Definition term={t("close.history.locks.column.recorded")}>
            <span className="num">{formatTimestamp(lock.created_at, { seconds: true })}</span>
          </Definition>
          <Definition term={t("close.history.locks.column.by")}>
            {lock.created_by.display_name}
          </Definition>
          <Definition term={t("close.history.locks.column.approval")}>
            <ApprovalNumber number={lock.approval_request_no} approval={approval} />
          </Definition>
          {reason === null ? null : (
            <Definition term={t("close.history.locks.column.reason")}>{reason}</Definition>
          )}
          {lock.comment === null ? null : (
            <Definition term={t("close.history.drawer.comment")}>
              <blockquote className="rounded-md bg-subtle px-3 py-2">{lock.comment}</blockquote>
            </Definition>
          )}
          {lock.cutoff_known_at === null ? null : (
            <Definition term={t("close.history.drawer.snapshot")}>
              {t("close.history.drawer.frozen", {
                instant: formatTimestamp(lock.cutoff_known_at, { seconds: true }),
              })}
            </Definition>
          )}
          <Definition term={t("close.history.locks.column.manifest")}>
            {lock.snapshot_manifest_sha256 === null ? (
              <NoValue />
            ) : (
              <HashValue
                value={lock.snapshot_manifest_sha256}
                name={t("close.history.locks.column.manifest")}
              />
            )}
          </Definition>
          <Definition term={t("close.history.locks.column.ledgerHead")}>
            <span className="inline-flex flex-wrap items-center gap-x-3">
              <span className="num">
                {formatNumber(lock.ledger_head_chain_seq, { kind: "count" })}
              </span>
              {lock.ledger_head_sha256 === null ? null : (
                <HashValue
                  value={lock.ledger_head_sha256}
                  name={t("close.history.locks.column.ledgerHead")}
                />
              )}
            </span>
          </Definition>
          <Definition term={t("close.history.locks.column.auditHead")}>
            <span className="num">
              {formatNumber(lock.audit_head_chain_seq, { kind: "count" })}
            </span>
          </Definition>
          <Definition term={t("close.history.locks.column.previous")}>
            {previous === undefined ? (
              <NoValue />
            ) : (
              <Button variant="link" onClick={() => onOpen(previous.id)}>
                {lockName(previous)}
              </Button>
            )}
          </Definition>
          <Definition term={t("close.history.locks.column.diff")}>
            <DiffReport lock={lock} permissions={permissions} ctxSearch={ctxSearch} />
          </Definition>
        </dl>
        {lock.certification.length === 0 ? null : <Certification gates={lock.certification} />}
        {lock.snapshots.length === 0 ? null : <Datasets snapshots={lock.snapshots} />}
        {decisions.length === 0 ? null : (
          <section className="flex flex-col gap-2">
            <h3 className="text-body-sm font-semibold text-fg-1">
              {t("close.history.drawer.decisions")}
            </h3>
            <ul className="flex flex-col gap-1 text-body-sm">
              {decisions.map((decision) => (
                <li key={decision.id} className="flex flex-wrap gap-x-2 text-fg-1">
                  <span>
                    {t(`close.history.decision.${decision.decision}`, {
                      name: decision.approver.display_name,
                    })}
                  </span>
                  {decision.on_behalf_of === null ? null : (
                    <span>
                      {t("approvals.request.onBehalfOf", {
                        name: decision.on_behalf_of.display_name,
                      })}
                    </span>
                  )}
                  <span className="num text-fg-2">{formatTimestamp(decision.decided_at)}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </Drawer>
  );
}
