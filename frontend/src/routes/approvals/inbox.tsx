// SF-12 Approvals, SF-12:submitted and SF-12:all (SCREENS §15.1 to §15.3, §15.6, §15.10; §0.7; DESIGN_SYSTEM
// DS-CMP-07, DS-CMP-08, DS-CMP-19, DS-CMP-23, DS-CMP-29; 04 API-R-09; REQ-UX-012, REQ-PLT-013). One page
// for every view: the h1 "Approvals", route tabs "Waiting for me <n> · Submitted by me · All requests",
// and the DS-CMP-08 master list of the view's requests beside the detail pane. Each row reads the
// summary and the amount (DS-FMT-05), then the subject type label · entity codes · preparer · submitted
// date (DS-FMT-16), the status chip when not pending and the outline flag chips. Selecting a request
// opens RT-57 inside its view (`?view=`) and keeps focus on the selected option. A member without an
// approval permission sees "You have no approval permissions" on Waiting for me. BUILD_SPEC WEB-16: the
// header with the Delegations tab is `./tabs`; the FilterBar (Type, Entity, Status) and "Select for bulk
// approval" are `./toolbar`, their chips reach the list read and stay on a request opened from the
// list; the bulk layout of Waiting for me is `./bulk` (SCREENS §15.3, §15.5, §15.7).
import { useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useCallback, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { hasFilters } from "../../components/filter-bar/filters";
import { Money } from "../../components/money/Money";
import { MasterDetail, type MasterItem } from "../../components/record/MasterDetail";
import { Button } from "../../components/ui/Button";
import { chipFor, OutlineChip, StatusChip, type StatusWord } from "../../components/ui/StatusChip";
import { announce } from "../../lib/a11y/announce";
import { useAccess } from "../../lib/access";
import { ApiProblem } from "../../lib/api/problems";
import {
  type Approval,
  approvalListKey,
  type ApprovalSubjectType,
  type ApprovalView,
  currencyRegistered,
  holdsApprovalPermission,
  requestRoute,
  useApprovalList,
  VIEW_ROUTES,
} from "../../lib/api/queries/approvals";
import { useMe } from "../../lib/api/queries/me";
import { formatDate, NO_VALUE, timestampDate } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { BulkApproval } from "./bulk";
import { ApprovalsHeader } from "./tabs";
import { ApprovalsToolbar, useApprovalToolbar, withChips } from "./toolbar";

/** SCREENS §15.3 E-08 labels. */
export function subjectTypeLabel(type: ApprovalSubjectType): string {
  return t(`approvals.subjectType.${type}`);
}

/**
 * Flags with a catalogue label (`approvals.flag.<flag>`; SCREENS §15.3 rev 1.18: the routing flags the
 * API sets, 04 T-PLT-17; rev 1.70: the six an activation gained with item ACT-FLAGS-1); any other flag,
 * such as a routing string of a rule output, shows verbatim.
 */
export const CATALOGUED_FLAGS: ReadonlySet<string> = new Set([
  "ABOVE_CONTROLLER_THRESHOLD",
  "ABOVE_THRESHOLD",
  "AI_ASSISTED",
  "CATCH_UP_GE_50K",
  "MANUAL_ENTRY",
  "MATERIAL_RIGHT",
  "METHODOLOGY_CHANGE",
  "NEW_SKU",
  "NON_STANDARD_TERMS",
  "PERIOD_IN_CLOSE",
  "POSTED_LINES",
  "RATE_NOT_PUBLISHED",
  "SIDE_LETTER",
  "TERMS_NOT_STATED",
  "TP_CHANGE_GE_250K",
  "TREATMENT_OVERRIDE",
  "VARIABLE_CONSIDERATION",
]);

export function flagLabel(flag: string): string {
  return CATALOGUED_FLAGS.has(flag) ? t(`approvals.flag.${flag}`) : flag;
}

/**
 * The legal entities a request names (04 §16.10 API-S-Approval `entities`, `entity_count`,
 * `all_entities`): "All entities" for a request that spans every entity, else the codes the reader
 * may read, in code order, with the count of the ones outside the reader's entities; null for a
 * request that names none.
 */
export function entitiesLabel(
  approval: Pick<Approval, "entities" | "entity_count" | "all_entities">,
): string | null {
  if (approval.all_entities) return t("approvals.entities.all");
  const codes = approval.entities.map((entity) => entity.code).join(", ");
  const hidden = approval.entity_count - approval.entities.length;
  if (hidden > 0) {
    return codes === ""
      ? t("approvals.entities.hidden", { count: hidden })
      : t("approvals.entities.more", { codes, count: hidden });
  }
  return codes === "" ? null : codes;
}

/** SCREENS §0.8 E-05: the chip word of a request; VOIDED splits on `void_reason`. */
export function approvalChipWord(approval: Pick<Approval, "status" | "void_reason">): StatusWord {
  return (
    chipFor("E-05", approval.status, { void_reason: approval.void_reason })?.status ??
    "Pending approval"
  );
}

/** The request after `current` in list order, else the one before it, else null. */
export function nextRequestId(ids: readonly string[], current: string): string | null {
  const index = ids.indexOf(current);
  if (index === -1) {
    return ids[0] ?? null;
  }
  return ids[index + 1] ?? ids[index - 1] ?? null;
}

/** SCREENS §0.7 SCR-ST-05 message: the problem title, then "Reference <request id>." (CPY-05). */
export function problemMessage(error: unknown): string {
  if (error instanceof ApiProblem) {
    return error.requestId === null
      ? error.title
      : `${error.title} ${t("approvals.reference", { reference: error.requestId })}`;
  }
  return error instanceof Error ? error.message : String(error);
}

export interface DetailContext {
  /** After an approval: open the next request of the list and announce the list count. */
  readonly moveToNext: () => void;
}

export interface ApprovalsPageProps {
  readonly view: ApprovalView;
  /** The request open in the detail pane (SF-12:request). */
  readonly selectedId?: string | null;
  /** The DS-CMP-08 detail region name. */
  readonly detailLabel?: string;
  readonly renderDetail?: (context: DetailContext) => ReactNode;
}

/** Navigation state of a selection made in the list: focus returns to the selected option. */
interface SelectionState {
  readonly focusSelected?: boolean;
}

export function WaitingForMe() {
  return <ApprovalsPage view="waiting" />;
}

export function SubmittedByMe() {
  return <ApprovalsPage view="submitted" />;
}

export function AllRequests() {
  return <ApprovalsPage view="all" />;
}

function RowDetails({ approval }: { readonly approval: Approval }) {
  const parts = [
    subjectTypeLabel(approval.subject.type),
    entitiesLabel(approval),
    approval.preparer.display_name,
    formatDate(timestampDate(approval.submitted_at)),
  ].filter((part): part is string => typeof part === "string" && part !== "");
  return (
    <>
      {parts.map((part, index) => (
        <span
          key={`${String(index)}:${part}`}
          className="inline-flex items-center gap-2 text-body-sm"
        >
          {index === 0 ? null : <span aria-hidden="true">·</span>}
          <span>{part}</span>
        </span>
      ))}
      {approval.status === "PENDING" ? null : <StatusChip status={approvalChipWord(approval)} />}
      {approval.flags.map((flag) => (
        <OutlineChip key={flag} label={flagLabel(flag)} />
      ))}
    </>
  );
}

function ViewEmptyState({ view }: { readonly view: ApprovalView }) {
  switch (view) {
    case "waiting":
      return (
        <EmptyState
          title={t("approvals.empty.waiting.title")}
          description={t("approvals.empty.waiting.description")}
        />
      );
    case "submitted":
      return <EmptyState title={t("approvals.empty.submitted")} description="" />;
    case "all":
      return <EmptyState title={t("approvals.empty.all")} description="" />;
  }
}

export function ApprovalsPage({
  view,
  selectedId = null,
  detailLabel,
  renderDetail,
}: ApprovalsPageProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const master = useRef<HTMLDivElement>(null);
  const me = useMe();
  const access = useAccess();
  const permitted = me.data === undefined || holdsApprovalPermission(access);
  const noPermissions = view === "waiting" && !permitted;
  // WEB-16: the chips of the view reach its list read; Waiting for me has a bulk layout while no
  // request is open (SCREENS §15.3, §15.5).
  const chips = useApprovalToolbar(view);
  const bulkOffered =
    view === "waiting" && me.data !== undefined && holdsApprovalPermission(access);
  const bulk = chips.bulk && bulkOffered && selectedId === null;
  const list = useApprovalList(view, !noPermissions && !bulk, chips.filters);
  const items = list.data;
  const selectedIndex =
    items === undefined || selectedId === null
      ? -1
      : items.findIndex((approval) => approval.id === selectedId);

  // AppShell moves focus to the page heading on every route change (DS-A11Y-09); a selection made in
  // the list keeps focus on the selected option instead (DS-CMP-08 selection follows focus).
  const restoreFocus = (location.state as SelectionState | null)?.focusSelected === true;
  useEffect(() => {
    if (!restoreFocus || selectedIndex === -1) {
      return undefined;
    }
    const timer = setTimeout(() => {
      const options = master.current?.querySelectorAll<HTMLElement>("[role='option']") ?? [];
      const option = Array.from(options).find(
        (element, position) =>
          (element.getAttribute("aria-posinset") ?? String(position + 1)) ===
          String(selectedIndex + 1),
      );
      option?.focus();
    }, 0);
    return () => clearTimeout(timer);
  }, [restoreFocus, selectedIndex, location.key]);

  const select = useCallback(
    (id: string) => {
      if (id !== selectedId) {
        const state: SelectionState = { focusSelected: true };
        void navigate(withChips(requestRoute(id, view), location.search), { state });
      }
    },
    [navigate, selectedId, view, location.search],
  );

  const ids = (items ?? []).map((approval) => approval.id);
  const moveToNext = () => {
    // The command refreshed the list before answering, so the cache holds the list after the decision.
    const remaining =
      queryClient.getQueryData<readonly Approval[]>(approvalListKey(view, chips.filters)) ?? [];
    announce(t("approvals.list.count", { count: remaining.length }), "polite");
    const next = selectedId === null ? null : nextRequestId(ids, selectedId);
    if (next === null) {
      void navigate(withChips(VIEW_ROUTES[view], location.search));
      return;
    }
    const state: SelectionState = { focusSelected: true };
    void navigate(withChips(requestRoute(next, view), location.search), { state });
  };

  // SCREENS §15.1: a request renders inside its view, so that view's tab stays the current page.
  const header = (
    <ApprovalsHeader current={{ view, to: `${location.pathname}${location.search}` }} />
  );

  const masterItems: MasterItem[] = (items ?? []).map((approval) => ({
    id: approval.id,
    name: approval.summary,
    amount: approval.content_withheld ? (
      // SCREENS §15.4 "Content withheld": the amount is among what the reader is not shown.
      <span className="shrink-0 text-body-sm text-fg-3">{NO_VALUE}</span>
    ) : approval.amount === null || !currencyRegistered(approval.amount.currency) ? undefined : (
      <span className="shrink-0 text-body-sm text-fg-1">
        <Money
          value={approval.amount.amount}
          currency={approval.amount.currency}
          variant="inline"
        />
      </span>
    ),
    chips: <RowDetails approval={approval} />,
  }));

  const toolbar =
    items === undefined || items.length === 0 ? undefined : (
      <p className="flex items-center gap-1.5 text-body-sm text-fg-2">
        <span>{t("approvals.list.count", { count: items.length })}</span>
        <span aria-hidden="true">·</span>
        <span>
          {t(view === "waiting" ? "approvals.list.oldestFirst" : "approvals.list.newestFirst")}
        </span>
      </p>
    );

  const errorState = (
    <Banner
      tone="negative"
      title={t("approvals.list.loadError")}
      headingLevel={2}
      actions={
        <Button variant="link" onClick={() => void list.refetch()}>
          {t("approvals.retry")}
        </Button>
      }
    >
      {problemMessage(list.error)}
    </Banner>
  );

  let status: "loading" | "error" | "ready" = "ready";
  if (items === undefined) {
    status = list.isError ? "error" : "loading";
  }

  if (bulk) {
    return (
      <div data-testid="SF-12-page" className="flex h-full min-h-0 flex-col gap-3">
        {header}
        <ApprovalsToolbar view={view} state={chips} bulkOffered />
        <div className="min-h-0 flex-1">
          <BulkApproval filters={chips.filters} />
        </div>
      </div>
    );
  }

  return (
    <div data-testid="SF-12-page" className="flex h-full min-h-0 flex-col gap-3">
      {header}
      {noPermissions ? null : (
        <ApprovalsToolbar view={view} state={chips} bulkOffered={bulkOffered} />
      )}
      <div
        ref={master}
        className="min-h-0 flex-1 overflow-hidden rounded-md border border-hairline bg-surface"
      >
        {noPermissions ? (
          <div className="px-[var(--panel-pad)]">
            <EmptyState
              title={t("approvals.empty.noPermissions.title")}
              description={t("approvals.empty.noPermissions.description")}
            />
          </div>
        ) : (
          <MasterDetail
            type="approvals"
            listLabel={t("approvals.list.label")}
            items={masterItems}
            selectedId={selectedId}
            onSelect={select}
            toolbar={toolbar}
            status={status}
            errorState={errorState}
            emptyState={
              hasFilters(location.search) ? (
                <EmptyState title={t("approvals.noResults")} description="" />
              ) : (
                <ViewEmptyState view={view} />
              )
            }
            detailLabel={detailLabel ?? t("approvals.request.regionPending")}
            noSelection={t("approvals.noSelection")}
          >
            {renderDetail?.({ moveToNext })}
          </MasterDetail>
        )}
      </div>
    </div>
  );
}
