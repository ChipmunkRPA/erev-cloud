// SF-03:history History tab (SCREENS §4.7; §0.4 RT-18; §0.8 E-17; DESIGN_SYSTEM DS-CMP-10, DS-CMP-12,
// DS-CMP-16, DS-CMP-31, DS-FMT-17, DS-FMT-31; D-12; 04 API-R-28 `GET /contracts/{id}/history`,
// `/versions`, `/versions/compare`, §16.14 API-S-ContractHistoryItem; API-R-10 `GET /audit-events`,
// `/audit-events/verifications`; BUILD_SPEC CTR-24). The view switch "History view" (`?view=`):
// - Activity: the timeline of the contract's events, calculations and approval decisions, newest first,
//   with the event-type filter, "Show system events" and "Load older activity";
// - Versions: the DataGrid "Contract versions" of the book in context; two selected versions enable
//   "Compare versions", whose field diff is grouped by obligation;
// - Audit trail (`audit.read`): the audit events whose object is the contract, under the latest chain
//   verification.
// The compare route answers the changed fields only, under their column names. Fields that are internal
// (ids, exact twins of rounded amounts, pinned policy JSON) or signed positions (D-12) are not listed;
// the panel says how many changes it did not list.
// Not rendered (XR-14; ruling R-93): the chip "Imports" until the history route answers items of kind
// IMPORT (item CTR-HISTORY-IMPORT-1; an imported event reads as a system event today), the Delta column
// until the compare route answers a difference (item CTR-COMPARE-DELTA-1; DG-FE-08 leaves money
// arithmetic to the server), the switch "Show unchanged fields" (the API answers no unchanged field) and
// the comment composer (04 has no comment resource).
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { type ReactNode, useId, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { DataGrid } from "../../../components/data-grid/DataGrid";
import type { GridColumn, GridSelection, GridSource } from "../../../components/data-grid/types";
import { Banner } from "../../../components/feedback/Banner";
import { EmptyState } from "../../../components/feedback/EmptyState";
import { Skeleton } from "../../../components/feedback/Skeleton";
import { Switch } from "../../../components/form/Switch";
import {
  ClockCounterClockwise,
  Function as FunctionIcon,
  type Icon,
  PencilSimpleLine,
  SealCheck,
  ShieldCheck,
  UploadSimple,
} from "../../../components/icons/registry";
import { NoValue } from "../../../components/money/Num";
import { Timeline, type TimelineEvent } from "../../../components/record/Timeline";
import { Button } from "../../../components/ui/Button";
import { cn } from "../../../components/ui/cn";
import { SegmentedControl } from "../../../components/ui/SegmentedControl";
import { chipFor, StatusChip, statusMessageKey } from "../../../components/ui/StatusChip";
import { useAccess } from "../../../lib/access";
import { ApiProblem } from "../../../lib/api/problems";
import {
  AUDIT_READ_PERMISSION,
  type AuditEvent,
  type Contract,
  contractAuditKey,
  type ContractHistoryItem,
  contractHistoryKey,
  contractVersionsKey,
  type ContractVersionSummary,
  fetchContractAuditPage,
  fetchContractHistoryPage,
  fetchContractVersionsPage,
  fetchLatestVerification,
  fetchVersionCompare,
  type HistoryItemKind,
  type HistoryQuery,
  latestVerificationKey,
  type VersionChange,
  versionCompareKey,
} from "../../../lib/api/queries/contracts";
import {
  formatDate,
  formatList,
  formatMoney,
  formatNumber,
  formatPercent,
  formatTimestamp,
  MINUS_SIGN,
  NO_VALUE,
  parseDateInput,
} from "../../../lib/format";
import { hasMessage, type MessageParams, t } from "../../../lib/i18n/t";
import { withParams } from "../../../lib/url/params";
import { useBuiltPaths } from "../../settings/index";
import { REQUEST_ROUTE } from "../obligation-pane";
import { readBook, type WorkbenchTabProps } from "./schedules";

export const HISTORY_VIEWS = ["activity", "versions", "audit"] as const;
export type HistoryView = (typeof HISTORY_VIEWS)[number];
const VIEW_PARAM = "view";
/** SCREENS RT-38 SF-09:verification, the target of the audit chain header once it is built. */
export const VERIFICATION_ROUTE = "/reports/audit-log/verifications/:verificationId";

/** SCREENS RT-18 `view=activity|versions|audit`; anything else, or `audit` without `audit.read`, is Activity. */
export function historyViewOf(value: string | null, audit: boolean): HistoryView {
  const view = HISTORY_VIEWS.find((candidate) => candidate === value) ?? "activity";
  return view === "audit" && !audit ? "activity" : view;
}

// ---------------------------------------------------------------------------------------------------
// Activity.

/** SCREENS §4.7 event-type chips: "All" and the E-116 kinds the history route answers (ruling R-93 (b)). */
export const ACTIVITY_FILTERS = ["ALL", "EVENT", "APPROVAL", "CALCULATION"] as const;
export type ActivityFilter = (typeof ACTIVITY_FILTERS)[number];

const KIND_ICON: Readonly<Record<HistoryItemKind, Icon>> = {
  EVENT: PencilSimpleLine,
  CALCULATION: FunctionIcon,
  APPROVAL: SealCheck,
  IMPORT: UploadSimple,
};

function param(item: Pick<ContractHistoryItem, "params">, name: string): string | null {
  const value = item.params[name];
  return typeof value === "string" && value !== "" ? value : null;
}

/** A catalogue phrase keyed by an API literal, or null when the catalogue has none for it. */
function phrase(prefix: string, literal: string | null, params: MessageParams = {}): string | null {
  const key = `${prefix}.${literal ?? ""}`;
  return literal !== null && hasMessage(key) ? t(key, params) : null;
}

/** The request an approval item decides: its number and, once SF-12:request is built, its route. */
function approvalRequest(
  item: ContractHistoryItem,
  requestBuilt: boolean,
): { readonly label: string; readonly to: string } | null {
  const number = param(item, "request_no");
  const id = /\/approvals\/([0-9a-f-]{36})$/.exec(item.links.approval ?? "")?.[1];
  return item.kind === "APPROVAL" && requestBuilt && number !== null && id !== undefined
    ? { label: number, to: `/approvals/requests/${id}` }
    : null;
}

/**
 * The verb phrase of a history item from its `summary_key` and `params` (04 §16.14). `linked` leaves
 * the request number of an approval decision to the link that follows the phrase.
 */
export function activityVerb(item: ContractHistoryItem, linked = false): string {
  switch (item.kind) {
    case "EVENT": {
      const verb =
        phrase("contracts.history.event", param(item, "event_type")) ??
        t("contracts.history.event.other");
      // `params.effective_date` is a business date in free-form JSON: shown only when it reads as one.
      const effective = parseDateInput(param(item, "effective_date") ?? "");
      return effective.ok
        ? t("contracts.history.effective", { verb, date: formatDate(effective.value) })
        : verb;
    }
    case "CALCULATION":
      return (
        phrase("contracts.history.computation", param(item, "status"), {
          engine: param(item, "engine_version") ?? NO_VALUE,
        }) ?? t("contracts.history.computation.other")
      );
    case "APPROVAL": {
      const request = param(item, "request_no");
      const prefix =
        linked || request === null
          ? "contracts.history.decision"
          : "contracts.history.decisionNumbered";
      const params = {
        subject:
          phrase("approvals.subjectType", param(item, "subject_type")) ??
          t("contracts.history.decision.subject"),
        request: request ?? "",
      };
      const decision = param(item, "decision");
      return (
        phrase(prefix, decision === "subject" ? null : decision, params) ??
        t(`${prefix}.other`, params)
      );
    }
    default:
      return t("contracts.history.event.other");
  }
}

function LoadError({
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
      headingLevel={3}
      actions={
        <Button variant="link" onClick={onRetry}>
          {t("common.grid.retry")}
        </Button>
      }
    >
      {problem instanceof ApiProblem ? <p>{problem.title}</p> : null}
      {problem instanceof ApiProblem && problem.requestId !== null ? (
        <p>{t("contracts.drawer.reference", { reference: problem.requestId })}</p>
      ) : null}
    </Banner>
  );
}

function ActivityView({ contract }: { readonly contract: Contract }) {
  const built = useBuiltPaths();
  const [filter, setFilter] = useState<ActivityFilter>("ALL");
  const [includeSystem, setIncludeSystem] = useState(false);
  // SCREENS §4.7 rev 1.39 (item HIST-CALC-CHIP-1): every computation is SYSTEM's (04
  // API-S-ContractHistoryItem rev 1.143), so the chip "Calculations" reads the system's items
  // whatever the switch says; the switch keeps the member's choice for the other chips.
  const query: HistoryQuery = {
    kind: filter === "ALL" ? null : filter,
    includeSystem: includeSystem || filter === "CALCULATION",
  };
  const history = useInfiniteQuery({
    queryKey: contractHistoryKey(contract.id, query),
    queryFn: ({ pageParam }) => fetchContractHistoryPage(contract.id, query, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.nextCursor,
  });
  const requestBuilt = built.has(REQUEST_ROUTE);
  const events: TimelineEvent[] = (history.data?.pages ?? [])
    .flatMap((page) => page.items)
    .map((item, index) => {
      const request = approvalRequest(item, requestBuilt);
      return {
        id: `${item.occurred_at}:${item.summary_key}:${String(index)}`,
        at: item.occurred_at,
        icon: KIND_ICON[item.kind],
        actor: item.actor.display_name,
        actorIsPerson: item.actor.kind === "USER",
        verb: activityVerb(item, request !== null),
        object: request ?? undefined,
      };
    });
  return (
    <Timeline
      events={events}
      headingLevel={3}
      status={history.isPending ? "loading" : history.isError ? "error" : "ready"}
      errorState={
        <LoadError
          title={t("contracts.history.activity.loadError")}
          problem={history.error}
          onRetry={() => void history.refetch()}
        />
      }
      filters={
        <div className="flex flex-wrap items-center gap-4">
          <SegmentedControl<ActivityFilter>
            label={t("contracts.history.activity.filter")}
            options={ACTIVITY_FILTERS.map((value) => ({
              value,
              label: t(`contracts.history.activity.kind.${value}`),
            }))}
            value={filter}
            onChange={setFilter}
          />
          <Switch
            label={t("contracts.history.activity.showSystem")}
            checked={includeSystem}
            onChange={setIncludeSystem}
          />
        </div>
      }
      hasOlder={history.hasNextPage}
      loadingOlder={history.isFetchingNextPage}
      onLoadOlder={() => void history.fetchNextPage()}
    />
  );
}

// ---------------------------------------------------------------------------------------------------
// Versions and their comparison.

const PLAIN_DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/;

type FieldKind =
  | "money"
  | "number"
  | "count"
  | "percent"
  | "share"
  | "date"
  | "text"
  | "boolean"
  | "list"
  | "status"
  | { readonly labels: string };

// The columns of a contract version and of an obligation version that the comparison lists, with how
// each value reads (04 T-CON-07, T-CON-08). A changed column outside this table is counted, not listed.
const VERSION_FIELDS: Readonly<Record<string, FieldKind>> = {
  obligation: "text",
  status_in_book: "status",
  status_reason_in_book: "text",
  transaction_currency: "text",
  transaction_price: "money",
  fixed_consideration: "money",
  vc_constrained_amount: "money",
  vc_excluded_amount: "money",
  expected_returns_amount: "money",
  consideration_payable_amount: "money",
  financing_adjustment_amount: "money",
  noncash_consideration_amount: "money",
  sales_tax_excluded_amount: "money",
  out_of_scope_amount: "money",
  total_ssp: "number",
  revenue_cum: "money",
  billed_cum: "money",
  rpo_amount: "money",
  scheduled_amount: "money",
  awaiting_trigger_amount: "money",
  modification_boundary_no: "count",
  legacy_record_key: "text",
  product_code: "text",
  sku_number: "text",
  stratification: "text",
  obligation_kind: { labels: "contracts.obligation.kind" },
  distinctness: { labels: "policies.ssp.distinctness" },
  series_increment_unit: "text",
  scope_flag: { labels: "contracts.obligation.scope" },
  satisfaction_pattern: { labels: "policies.template.satisfaction" },
  over_time_criterion: { labels: "contracts.obligation.criterion" },
  recognition_method: { labels: "policies.template.method" },
  ratable_convention: { labels: "policies.template.convention" },
  principal_agent: { labels: "policies.template.principalAgent" },
  licence_nature: { labels: "policies.template.licence" },
  warranty_type: { labels: "policies.template.warranty" },
  start_date: "date",
  end_date: "date",
  txn_currency: "text",
  memo_1: "text",
  memo_2: "text",
  memo_3: "text",
  legacy_deferred_revenue_account: "text",
  legacy_unbilled_ar_account: "text",
  legacy_revenue_account: "text",
  original_quantity: "number",
  original_stated_price: "money",
  quantity: "number",
  stated_price: "money",
  ssp_method: { labels: "policies.ssp.method" },
  ssp_version_label: "text",
  ssp_unit_list_price: "number",
  ssp_midpoint_discount_ratio: "percent",
  ssp_range_ratio: "percent",
  original_ssp_mid: "number",
  original_ssp_high: "number",
  original_ssp_low: "number",
  original_ssp_selected: "number",
  original_ssp_in_range: "boolean",
  original_total_contract_price: "money",
  original_total_contract_ssp: "number",
  original_allocated_amount: "money",
  original_unit_ssp: "number",
  original_unit_revenue_rate: "number",
  allocation_weight: "share",
  allocated_amount: "money",
  allocation_adjustment: "money",
  unit_ssp: "number",
  remaining_unit_revenue_rate: "number",
  delivered_quantity_cum: "number",
  returned_quantity_cum: "number",
  progress_ratio: "percent",
  ssp_delivered_cum: "number",
  catch_up_cum: "money",
  catch_up_modification_cum: "money",
  catch_up_tp_change_cum: "money",
  catch_up_estimate_cum: "money",
  pre_standard_revenue_cum: "money",
  delivered_quantity: "number",
  revenue_amount: "money",
  billed_amount: "money",
  ssp_delivered: "number",
  catch_up_amount: "money",
  pre_standard_revenue_amount: "money",
  remaining_quantity: "number",
  remaining_ssp: "number",
  remaining_allocation: "money",
  remaining_billing: "money",
  netting_reclass_amount: "money",
  netting_reclass_role: { labels: "accountRole" },
  satisfaction_status: { labels: "contracts.history.satisfaction" },
  satisfied_date: "date",
  hold_types: "list",
  gross_amount_memo: "money",
  effective_date: "date",
  previous_effective_date: "date",
};

function fieldKind(field: string): FieldKind | null {
  return Object.hasOwn(VERSION_FIELDS, field) ? (VERSION_FIELDS[field] ?? null) : null;
}

/** The display text of one side of a change; null shows the no-value dash. */
export function changeValue(kind: FieldKind, value: unknown, currency: string): string | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  if (kind === "boolean") {
    return t(value === true ? "common.grid.yes" : "common.grid.no");
  }
  if (kind === "list") {
    return Array.isArray(value) && value.length > 0
      ? formatList(
          value.map((item) => phrase("contracts.history.hold", String(item)) ?? String(item)),
          "unit",
        )
      : null;
  }
  const text = typeof value === "string" || typeof value === "number" ? String(value) : null;
  if (text === null) {
    return null;
  }
  const decimal = PLAIN_DECIMAL.test(text);
  switch (kind) {
    case "money":
      return decimal ? formatMoney(text, currency, { variant: "cell" }) : text;
    case "number":
      return decimal ? formatNumber(text) : text;
    case "count":
      return decimal ? formatNumber(text, { kind: "count" }) : text;
    case "percent":
      return decimal ? formatPercent(text) : text;
    case "share":
      return decimal ? formatPercent(text, { kind: "share" }) : text;
    case "date": {
      const parsed = parseDateInput(text);
      return parsed.ok ? formatDate(parsed.value) : text;
    }
    case "status": {
      const chip = chipFor("E-17", text);
      return chip === null ? text : t(statusMessageKey(chip.status));
    }
    case "text":
      return text;
    default:
      return phrase(kind.labels, text) ?? text;
  }
}

export interface CompareRow {
  readonly id: string;
  readonly label: string;
  readonly change: "added" | "removed" | "changed";
  readonly before: string | null;
  readonly after: string | null;
}

export interface CompareGroup {
  /** Null: the fields of the contract version. */
  readonly obligationKey: string | null;
  readonly rows: readonly CompareRow[];
}

export interface Comparison {
  readonly groups: readonly CompareGroup[];
  /** Changes in fields the table does not list. */
  readonly omitted: number;
}

/** The changes of `GET …/versions/compare` grouped by obligation, the contract's own fields first. */
export function compareGroups(changes: readonly VersionChange[], currency: string): Comparison {
  const groups = new Map<string | null, CompareRow[]>();
  let omitted = 0;
  for (const change of changes) {
    const kind = fieldKind(change.field);
    if (kind === null) {
      omitted += 1;
      continue;
    }
    const before = changeValue(kind, change.before, currency);
    const after = changeValue(kind, change.after, currency);
    const rows = groups.get(change.obligation_key) ?? [];
    rows.push({
      id: `${change.obligation_key ?? ""}:${change.field}`,
      label: t(`contracts.history.field.${change.field}`),
      change: before === null ? "added" : after === null ? "removed" : "changed",
      before,
      after,
    });
    groups.set(change.obligation_key, rows);
  }
  const ordered = [...groups.entries()].sort(([left], [right]) =>
    left === null ? -1 : right === null ? 1 : left.localeCompare(right),
  );
  return { groups: ordered.map(([obligationKey, rows]) => ({ obligationKey, rows })), omitted };
}

const MARKER: Readonly<Record<CompareRow["change"], string>> = {
  removed: MINUS_SIGN,
  added: "+",
  changed: "~",
};

function ComparePanel({
  contract,
  book,
  from,
  to,
  onClose,
}: {
  readonly contract: Contract;
  readonly book: string | null;
  readonly from: number;
  readonly to: number;
  readonly onClose: () => void;
}) {
  const compare = useQuery({
    queryKey: versionCompareKey(contract.id, from, to, book),
    queryFn: () => fetchVersionCompare(contract.id, from, to, book),
  });
  const versions = {
    from: formatNumber(from, { kind: "count" }),
    to: formatNumber(to, { kind: "count" }),
  };
  const caption = t("contracts.history.compare.caption", versions);
  let body: ReactNode;
  if (compare.isPending) {
    body = <Skeleton region={caption} shape="rows" count={6} />;
  } else if (compare.isError) {
    body = (
      <LoadError
        title={t("contracts.history.compare.loadError")}
        problem={compare.error}
        onRetry={() => void compare.refetch()}
      />
    );
  } else {
    const { groups, omitted } = compareGroups(compare.data.changes, contract.transaction_currency);
    body = (
      <>
        <table data-testid="SF-03-diff" className="w-full border-collapse text-body-sm">
          <caption className="pb-2 text-start text-body-sm font-semibold text-fg-1">
            {caption}
          </caption>
          <thead>
            <tr className="border-b border-default text-caption text-fg-3">
              <th scope="col" className="w-16 px-2 py-1.5 text-start font-medium">
                {t("common.diff.column.change")}
              </th>
              <th scope="col" className="px-2 py-1.5 text-start font-medium">
                {t("common.diff.column.field")}
              </th>
              <th scope="col" className="px-2 py-1.5 text-end font-medium">
                {t("contracts.history.compare.version", { version: versions.from })}
              </th>
              <th scope="col" className="px-2 py-1.5 text-end font-medium">
                {t("contracts.history.compare.version", { version: versions.to })}
              </th>
            </tr>
          </thead>
          {groups.map((group) => (
            <tbody key={group.obligationKey ?? ""}>
              <tr className="border-b border-hairline bg-subtle">
                <th
                  scope="rowgroup"
                  colSpan={4}
                  className="px-2 py-1.5 text-start text-caption text-fg-2"
                >
                  {group.obligationKey === null ? (
                    t("contracts.history.compare.contract")
                  ) : (
                    <>
                      {t("contracts.history.compare.obligation")}{" "}
                      <span className="font-mono text-mono-sm">{group.obligationKey}</span>
                    </>
                  )}
                </th>
              </tr>
              {group.rows.map((row) => (
                <tr
                  key={row.id}
                  data-change={row.change}
                  className={cn(
                    "border-b border-hairline align-top",
                    row.change === "removed" && "bg-diff-removed-bg",
                    row.change === "added" && "bg-diff-added-bg",
                  )}
                >
                  <td className="px-2 py-1.5">
                    <span aria-hidden="true" className="num font-medium text-fg-1">
                      {MARKER[row.change]}
                    </span>
                    <span className="sr-only">{t(`common.diff.prefix.${row.change}`)}</span>
                  </td>
                  <th scope="row" className="px-2 py-1.5 text-start font-medium text-fg-1">
                    {row.label}
                  </th>
                  <td
                    className={cn(
                      "num px-2 py-1.5 text-end",
                      row.change === "changed" && "bg-diff-removed-bg",
                    )}
                  >
                    <span className={cn(row.change !== "added" && "text-fg-2 line-through")}>
                      {row.before ?? NO_VALUE}
                    </span>
                  </td>
                  <td
                    className={cn(
                      "num px-2 py-1.5 text-end",
                      row.change === "changed" && "bg-diff-added-bg",
                    )}
                  >
                    {row.after ?? NO_VALUE}
                  </td>
                </tr>
              ))}
            </tbody>
          ))}
        </table>
        {groups.length === 0 ? (
          <p className="text-body-sm text-fg-2">{t("contracts.history.compare.none", versions)}</p>
        ) : null}
        {omitted === 0 ? null : (
          <p className="text-body-sm text-fg-3">
            {t("contracts.history.compare.omitted", {
              count: omitted,
              formatted: formatNumber(omitted, { kind: "count" }),
            })}
          </p>
        )}
      </>
    );
  }
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-hairline bg-surface p-[var(--panel-pad)]">
      {body}
      <div>
        <Button variant="secondary" size="sm" onClick={onClose}>
          {t("contracts.history.compare.close")}
        </Button>
      </div>
    </div>
  );
}

// The widths add up to the panel at 1440 px beside the selection column, so "Status in book" shows
// without a horizontal scroll.
function versionColumns(contract: Contract): readonly GridColumn<ContractVersionSummary>[] {
  const currency = contract.transaction_currency;
  return [
    {
      id: "version_no",
      header: t("contracts.history.versions.column.version"),
      kind: "number",
      numberKind: "count",
      value: (version) => String(version.version_no),
      sortKey: "version_no",
      width: 80,
    },
    {
      id: "known_at",
      header: t("contracts.history.versions.column.knownAt"),
      kind: "timestamp",
      value: (version) => version.known_at,
      width: 180,
    },
    {
      id: "cause",
      header: t("contracts.history.versions.column.cause"),
      kind: "text",
      value: (version) => {
        const first = version.cause_events[0];
        return first === undefined
          ? null
          : t("contracts.history.versions.cause", {
              event:
                phrase("contracts.event.type", first.event_type) ??
                t("contracts.history.versions.otherEvent"),
              date: formatDate(first.effective_date),
            });
      },
      width: 288,
    },
    {
      id: "engine",
      header: t("contracts.history.versions.column.engine"),
      kind: "text",
      value: (version) => version.engine_version,
      render: (version) => <span className="font-mono text-mono-sm">{version.engine_version}</span>,
      width: 80,
    },
    {
      id: "transaction_price",
      header: t("contracts.history.versions.column.transactionPrice", { currency }),
      kind: "money",
      value: (version) => version.transaction_price_buildup.total.amount,
      currency: (version) => version.transaction_price_buildup.total.currency,
      width: 160,
    },
    {
      id: "revenue_to_date",
      header: t("contracts.history.versions.column.revenueToDate", { currency }),
      kind: "money",
      value: (version) => version.revenue_to_date.amount,
      currency: (version) => version.revenue_to_date.currency,
      width: 160,
    },
    {
      id: "status",
      header: t("contracts.history.versions.column.status"),
      kind: "status",
      value: (version) => {
        const chip = chipFor("E-17", version.status_in_book);
        return chip === null ? null : t(statusMessageKey(chip.status));
      },
      render: (version) => {
        const chip = chipFor("E-17", version.status_in_book);
        return chip === null ? <NoValue /> : <StatusChip status={chip.status} />;
      },
      width: 148,
    },
  ];
}

function VersionsView({
  contract,
  book,
}: {
  readonly contract: Contract;
  readonly book: string | null;
}) {
  const reasonId = useId();
  const [selected, setSelected] = useState<readonly number[]>([]);
  const [compared, setCompared] = useState<readonly [number, number] | null>(null);
  const columns = useMemo(() => versionColumns(contract), [contract]);
  const source: GridSource<ContractVersionSummary> = {
    queryKey: contractVersionsKey(contract.id, book),
    fetchPage: (cursor, sort) => fetchContractVersionsPage(contract.id, book, cursor, sort),
  };
  const pair =
    selected.length === 2 ? ([...selected].sort((a, b) => a - b) as [number, number]) : null;
  const onSelection = (selection: GridSelection) => {
    // The row key is the version number, so the selection names the two versions to compare.
    setSelected([...selection.ids].map(Number).filter((value) => Number.isInteger(value)));
  };
  return (
    <div className="flex flex-col gap-3">
      <div className="flex min-h-96 flex-col">
        <DataGrid<ContractVersionSummary>
          name="versions"
          title={t("contracts.history.versions.title")}
          headingLevel={3}
          describedBy={pair === null ? reasonId : undefined}
          errorTitle={t("contracts.history.versions.loadError")}
          countLabel={(count, formatted) =>
            t("contracts.history.versions.count", { count, formatted })
          }
          columns={columns}
          source={source}
          rowKey={(version) => String(version.version_no)}
          rowLabel={(version) =>
            t("contracts.history.versions.rowLabel", {
              version: formatNumber(version.version_no, { kind: "count" }),
            })
          }
          selectable
          onSelectionChange={onSelection}
          toolbarActions={
            <Button
              variant={pair === null ? "secondary" : "primary"}
              size="sm"
              disabledReason={pair === null ? t("contracts.history.compare.selectTwo") : undefined}
              onClick={() => setCompared(pair)}
            >
              {t("contracts.history.compare.action")}
            </Button>
          }
          testIdPrefix="SF-03"
          emptyState={
            <EmptyState
              title={t("contracts.history.versions.empty")}
              description={t("contracts.history.versions.emptyDescription")}
              headingLevel={4}
            />
          }
        />
      </div>
      {pair === null ? (
        <p id={reasonId} className="text-body-sm text-fg-3">
          {t("contracts.history.compare.selectTwo")}
        </p>
      ) : null}
      {compared === null ? null : (
        <ComparePanel
          contract={contract}
          book={book}
          from={compared[0]}
          to={compared[1]}
          onClose={() => setCompared(null)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// Audit trail.

/** The verb phrase of an audit event: the catalogue phrase of its action, else the action literal. */
export function auditVerb(event: Pick<AuditEvent, "action" | "outcome">): string {
  const verb = phrase("contracts.history.audit.action", event.action) ?? event.action;
  return event.outcome === "SUCCESS"
    ? verb
    : t(`contracts.history.audit.outcome.${event.outcome}`, { verb });
}

/** The audit events of the contract, read while the view asks for them; a refused read is a null page. */
function useContractAudit(contractId: string, enabled: boolean) {
  return useInfiniteQuery({
    queryKey: contractAuditKey(contractId),
    queryFn: ({ pageParam }) => fetchContractAuditPage(contractId, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last?.nextCursor ?? null,
    enabled,
  });
}

function AuditView({ audit }: { readonly audit: ReturnType<typeof useContractAudit> }) {
  const built = useBuiltPaths();
  const verification = useQuery({
    queryKey: latestVerificationKey(),
    queryFn: fetchLatestVerification,
  });
  const latest = verification.data ?? null;
  const detail =
    latest !== null && built.has(VERIFICATION_ROUTE)
      ? `/reports/audit-log/verifications/${latest.id}`
      : null;
  let header: ReactNode = null;
  if (latest !== null && latest.result === "FAIL") {
    header = (
      <Banner
        tone="negative"
        announce="static"
        headingLevel={3}
        title={t("common.timeline.auditFailed", {
          event:
            latest.first_failure_seq === null
              ? NO_VALUE
              : formatNumber(latest.first_failure_seq, { kind: "count" }),
        })}
        actions={
          detail === null ? undefined : (
            <Link to={detail} className="text-body-sm text-accent-fg hover:underline">
              {t("common.timeline.auditDetails")}
            </Link>
          )
        }
      />
    );
  } else if (latest !== null && latest.result === "PASS") {
    const text = (
      <>
        <ShieldCheck aria-hidden="true" className="shrink-0 text-positive-fg" />
        {t("common.timeline.auditVerified", { timestamp: formatTimestamp(latest.finished_at) })}
      </>
    );
    header =
      detail === null ? (
        <p className="inline-flex items-center gap-1.5 self-start text-body-sm text-fg-2">{text}</p>
      ) : (
        <Link
          to={detail}
          className="inline-flex items-center gap-1.5 self-start text-body-sm text-fg-2 hover:text-fg-1 hover:underline"
        >
          {text}
        </Link>
      );
  }
  const events: TimelineEvent[] = (audit.data?.pages ?? [])
    .flatMap((page) => page?.items ?? [])
    .map((event) => ({
      id: event.id,
      at: event.occurred_at,
      icon: ClockCounterClockwise,
      // SCREENS §4.7 rev 1.39: an event written for a principal names both ("System on behalf of
      // Maya Chen"); API-S-ContractHistoryItem names no such principal, so Activity cannot.
      actor:
        event.on_behalf_of === null
          ? event.actor.display_name
          : t("contracts.history.actor.onBehalfOf", {
              actor: event.actor.display_name,
              name: event.on_behalf_of.display_name,
            }),
      actorIsPerson: event.actor.kind === "USER",
      verb: auditVerb(event),
      comment: event.comment ?? undefined,
    }));
  return (
    <Timeline
      events={events}
      headingLevel={3}
      status={audit.isPending ? "loading" : audit.isError ? "error" : "ready"}
      errorState={
        <LoadError
          title={t("contracts.history.audit.loadError")}
          problem={audit.error}
          onRetry={() => void audit.refetch()}
        />
      }
      filters={header}
      hasOlder={audit.hasNextPage}
      loadingOlder={audit.isFetchingNextPage}
      onLoadOlder={() => void audit.fetchNextPage()}
    />
  );
}

// ---------------------------------------------------------------------------------------------------

export function HistoryTab({ contract, context }: WorkbenchTabProps) {
  const headingId = useId();
  const location = useLocation();
  const navigate = useNavigate();
  const access = useAccess();
  const param = new URLSearchParams(location.search).get(VIEW_PARAM);
  // SCREENS §4.7 (SCR-PERM-02; ruling R-28): the audit events are a list of the whole workspace, read
  // with `audit.read` for all entities. A read the API refuses all the same removes the option, and
  // the view is the one of a member without the permission.
  const offered = access.holdsForAll(AUDIT_READ_PERMISSION);
  const trail = useContractAudit(contract.id, offered && historyViewOf(param, true) === "audit");
  const audit = offered && trail.data?.pages[0] !== null;
  const view = historyViewOf(param, audit);
  const views = HISTORY_VIEWS.filter((candidate) => candidate !== "audit" || audit);
  const setView = (next: HistoryView) => {
    void navigate(
      { search: withParams(location.search, { [VIEW_PARAM]: next === "activity" ? null : next }) },
      { replace: true },
    );
  };
  return (
    <section aria-labelledby={headingId} className="flex min-h-120 flex-col gap-4">
      <div className="flex flex-wrap items-center gap-4">
        <h2 id={headingId} className="text-title-sm text-fg-1">
          {t("contracts.workbench.tabs.history")}
        </h2>
        <SegmentedControl<HistoryView>
          label={t("contracts.history.view.label")}
          options={views.map((value) => ({
            value,
            label: t(`contracts.history.view.${value}`),
          }))}
          value={view}
          onChange={setView}
        />
      </div>
      {view === "versions" ? (
        <VersionsView contract={contract} book={readBook(contract, context)} />
      ) : view === "audit" ? (
        <div
          data-testid="SF-03-pane-audit"
          className="rounded-lg border border-hairline bg-surface p-[var(--panel-pad)]"
        >
          <AuditView audit={trail} />
        </div>
      ) : (
        <div
          data-testid="SF-03-pane-activity"
          className="rounded-lg border border-hairline bg-surface p-[var(--panel-pad)]"
        >
          <ActivityView contract={contract} />
        </div>
      )}
    </section>
  );
}
