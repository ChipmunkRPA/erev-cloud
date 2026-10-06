// SF-03:obligation Obligation detail pane (SCREENS §5.1 to §5.11; §4.2 chips; DESIGN_SYSTEM DS-CMP-06
// obligation variant, DS-CMP-07 panel tabs, DS-CMP-08, DS-CMP-10 static tables, DS-CMP-15; 04
// API-S-Obligation, API-S-ScheduleLine, API-S-Event; BUILD_SPEC CTR-22). A compact record header (h2
// product name, key, chips, "Record event" menu and the overflow), the four figures, and the panel tabs
// Overview, Attributes, SSP and allocation, Schedule and Events (`pane=` with `history.replace`). Every
// figure is an Explain trigger; the pane never computes allocated = recognized + scheduled + awaiting
// trigger (REQ-REC-021). "Change price" opens SF-07 with the kind and the obligation preselected
// (§5.8, LTM-06; rev 1.29). "Change attributes", "Request SSP override" and the material-right commands
// are not rendered (XR-14; L5-4-Q-32). "Request policy override" is not rendered either (§4.9.7 rev
// 1.80; supervisor ruling R-126 (c)): release 1.0 takes no policy override.
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { Link } from "react-router";

import {
  type ExplainObjectType,
  ExplainTrigger,
  type FigureRef,
} from "../../components/explain/ExplainTrigger";
import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useNoAnswer, useToast } from "../../components/feedback/Toast";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { DotsThree } from "../../components/icons/registry";
import { Money } from "../../components/money/Money";
import { type Kpi, KpiStrip } from "../../components/record/KpiStrip";
import { RecordHeader } from "../../components/record/RecordHeader";
import { PanelTabs } from "../../components/record/Tabs";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { Menu, type MenuItem } from "../../components/ui/Menu";
import { Modal } from "../../components/ui/Modal";
import { OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { useCommandKeys } from "../../lib/api/commands";
import { ApiProblem } from "../../lib/api/problems";
import {
  type Contract,
  CONTRACT_CREATE_PERMISSION,
  EVENT_RECORD_PERMISSION,
  type RecordContext,
  sendCommand,
} from "../../lib/api/queries/contracts";
import {
  fetchObligation,
  fetchObligationEvents,
  fetchObligationSchedule,
  fetchSspVersionLabel,
  type Obligation,
  type ObligationEvent,
  obligationEventsKey,
  obligationKey,
  obligationScheduleKey,
  sspVersionLabelKey,
} from "../../lib/api/queries/obligations";
import {
  formatDate,
  formatMoney,
  formatNumber,
  formatPercent,
  formatRate,
  formatTimestamp,
  NBSP,
  NO_VALUE,
} from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { type Choice, SelectField, useRefreshRecord } from "./drawers/common";
import { type EventKind, eventKindsFor } from "./drawers/record-event";
import { eventOriginText } from "./event-origin";

export const PANE_TABS = ["overview", "attributes", "ssp", "schedule", "events"] as const;
export type PaneTab = (typeof PANE_TABS)[number];

export function isPaneTab(value: string | null): value is PaneTab {
  return value !== null && (PANE_TABS as readonly string[]).includes(value);
}

export type PaneCommand =
  | { readonly kind: "record-event"; readonly event: EventKind; readonly obligationKey: string }
  | { readonly kind: "apply-hold"; readonly obligationKey: string }
  | { readonly kind: "edit-memos"; readonly obligationKey: string }
  | { readonly kind: "release-hold"; readonly holdId: string };

/** SCREENS SCR-ROUTE RT-14 SF-03:schedules, the target of "Open in Schedules". */
export const SCHEDULES_ROUTE = "/contracts/:contractId/schedules";
export const REQUEST_ROUTE = "/approvals/requests/:requestId";
export const SSP_BOOK_VERSION_ROUTE = "/policies/ssp-books/:bookId/versions/:versionId";

const EXPLAIN_TYPES: readonly ExplainObjectType[] = [
  "contract_version",
  "obligation",
  "obligation_version",
  "schedule_line",
  "subledger_line",
  "journal_line",
  "contract_version_balance",
];

/**
 * The figure of an API `links.explain_*` URL `/api/v1/explain/<type>/<id>/<measure>[?period=<key>]`.
 * A to-date measure is read at the period its link names (04 API-S-Obligation `links`, rev 1.132):
 * without it the panel would explain the version's node, the figure at the version's own date.
 */
export function figureFromLink(link: string | null, book: string | null): FigureRef | undefined {
  const match = /\/explain\/([a-z_]+)\/([^/?]+)\/([a-z_]+)(?:\?(.*))?$/.exec(link ?? "");
  const type = match?.[1];
  const id = match?.[2];
  const measure = match?.[3];
  if (type === undefined || id === undefined || measure === undefined) {
    return undefined;
  }
  const objectType = EXPLAIN_TYPES.find((item) => item === type);
  if (objectType === undefined) {
    return undefined;
  }
  const period = new URLSearchParams(match?.[4] ?? "").get("period");
  return {
    objectType,
    id,
    measure,
    ...(period === null || period === "" ? {} : { periodKey: period }),
    book: book ?? undefined,
  };
}

/**
 * The figure a balance entry names for one of its balances (04 API-S-Contract `kpis.balances[].links`
 * and API-S-ContractBalance `links`, rev 1.174; SCREENS §4.1.4 and §4.4 rev 1.24): the member
 * `explain_<measure>`, the address of the balance row — an id no other member carries — at the period
 * the balance was read at. Undefined where the entry names none or a null one: that figure has no
 * explanation to open and prints without a trigger.
 */
export function balanceFigure(
  links: Readonly<Record<string, string | null | undefined>> | undefined,
  measure: string,
  book: string | null,
): FigureRef | undefined {
  const named = Object.entries(links ?? {}).find(([name]) => name === `explain_${measure}`);
  return figureFromLink(named?.[1] ?? null, book);
}

/** DS-FMT-20: "15 Sep 2026 – 14 Sep 2027"; a missing end shows the start alone. */
export function dateRange(start: string | null, end: string | null): string | undefined {
  if (start === null) {
    return undefined;
  }
  return end === null ? formatDate(start) : `${formatDate(start)} – ${formatDate(end)}`;
}

/** SCREENS §4.1.3.1 column 8 words of the E-114 position and the resolved POL-072 point. */
export function rangePositionText(position: string | null, point: string | null): string {
  if (position === null) {
    return NO_VALUE;
  }
  if (position === "INSIDE") {
    return t("contracts.allocation.range.INSIDE");
  }
  const words = point === null ? "" : t(`contracts.allocation.point.${point}`);
  return t(`contracts.allocation.range.${position === "BELOW" ? "BELOW" : "ABOVE"}`, {
    point: words,
  });
}

/** "USD 1,234.00" with an ordinary space, for accessible names. */
export function moneyText(value: string, currency: string): string {
  return formatMoney(value, currency, { variant: "inline" }).replace(NBSP, " ");
}

/** SCREENS §4.2 line 2 chips of an obligation. */
export function ObligationChips({ obligation }: { readonly obligation: Obligation }) {
  const performing = obligation.performing_entity;
  return (
    <>
      <OutlineChip label={t(`policies.template.satisfaction.${obligation.satisfaction_pattern}`)} />
      {obligation.recognition_method === "TIME_ELAPSED" ? (
        <OutlineChip label={t("contracts.obligation.chip.ratable")} />
      ) : null}
      {obligation.distinctness === "series" ? (
        <OutlineChip label={t("contracts.obligation.chip.series")} />
      ) : null}
      {obligation.obligation_kind === "MATERIAL_RIGHT" ? (
        <OutlineChip label={t("contracts.obligation.chip.materialRight")} />
      ) : null}
      {performing.id === obligation.contracting_entity.id ? null : (
        <OutlineChip
          label={t("contracts.obligation.chip.intercompany", { entity: performing.code })}
        />
      )}
      {obligation.satisfaction_status === "SATISFIED" ? <StatusChip status="Satisfied" /> : null}
      {obligation.holds.length > 0 ? <StatusChip status="On hold" /> : null}
    </>
  );
}

function Explained({
  figure,
  label,
  context,
  value,
  currency,
  delta = false,
}: {
  readonly figure: FigureRef | undefined;
  readonly label: string;
  readonly context: string;
  readonly value: string;
  readonly currency: string;
  readonly delta?: boolean;
}) {
  const money = <Money value={value} currency={currency} variant="inline" delta={delta} />;
  return figure === undefined ? (
    money
  ) : (
    <ExplainTrigger
      figureRef={figure}
      label={label}
      context={context}
      valueText={moneyText(value, currency)}
    >
      {money}
    </ExplainTrigger>
  );
}

function Definition({ label, children }: { readonly label: string; readonly children: ReactNode }) {
  return (
    <div className="grid grid-cols-[minmax(10rem,14rem)_1fr] gap-3 border-b border-hairline py-1.5">
      <dt className="text-body-sm text-fg-3">{label}</dt>
      <dd className="text-body-sm text-fg-1">{children}</dd>
    </div>
  );
}

function progressText(obligation: Obligation): string {
  const ratio = formatPercent(obligation.to_date.progress_ratio);
  switch (obligation.recognition_method) {
    case "UNITS_DELIVERED":
      return t("contracts.obligation.progress.UNITS_DELIVERED", {
        delivered: formatNumber(obligation.to_date.delivered_quantity),
        quantity: formatNumber(obligation.current.quantity),
        ratio,
      });
    case "TIME_ELAPSED":
    case "COST_TO_COST":
    case "LABOUR_HOURS":
    case "OUTPUT_PERCENT":
    case "MILESTONE":
      return t(`contracts.obligation.progress.${obligation.recognition_method}`, { ratio });
    case "USAGE":
    case "ROYALTY":
      return t("contracts.obligation.progress.usage");
    case "POINT_IN_TIME":
      return obligation.satisfied_date === null
        ? t("contracts.obligation.progress.notTransferred")
        : t("contracts.obligation.progress.transferred", {
            date: formatDate(obligation.satisfied_date),
          });
    default:
      return ratio;
  }
}

function satisfactionText(obligation: Obligation): string {
  switch (obligation.satisfaction_status) {
    case "SATISFIED":
      return obligation.satisfied_date === null
        ? t("common.status.satisfied")
        : t("contracts.obligation.satisfaction.satisfiedOn", {
            date: formatDate(obligation.satisfied_date),
          });
    case "PARTIALLY_SATISFIED":
      return t("contracts.obligation.satisfaction.partial");
    case "CANCELLED":
      return t("contracts.obligation.satisfaction.cancelled");
    default:
      return t("contracts.obligation.satisfaction.not");
  }
}

/**
 * The obligation's own open holds (SCREENS §5.6 rev 1.75; 04 §16.2 rev 1.299 API-S-Obligation
 * `holds`): a hold of the whole contract is the contract's and is not repeated here. The column
 * "Release" stands where a row has something for it — "Release hold" for a viewer `onRelease` is
 * given for, or, for every reader, the API's sentence where the hold is not released by hand.
 */
function HoldsTable({
  holds,
  onRelease,
}: {
  readonly holds: Obligation["holds"];
  readonly onRelease: ((holdId: string) => void) | null;
}) {
  const releases = onRelease !== null || holds.some((hold) => hold.release_refusal !== null);
  const head = "pe-3 text-start font-medium";
  return (
    <table data-testid="SF-03-grid-obligation-holds" className="w-full text-body-sm">
      <caption className="sr-only">{t("contracts.obligation.overview.holds")}</caption>
      <thead>
        <tr className="text-caption text-fg-3">
          <th scope="col" className={head}>
            {t("contracts.list.hold.type")}
          </th>
          <th scope="col" className={head}>
            {t("contracts.obligation.holds.source")}
          </th>
          <th scope="col" className={head}>
            {t("contracts.list.hold.reason")}
          </th>
          <th scope="col" className={head}>
            {t("contracts.obligation.holds.appliedAt")}
          </th>
          {releases ? (
            <th scope="col" className="text-start font-medium">
              {t("contracts.obligation.holds.release")}
            </th>
          ) : null}
        </tr>
      </thead>
      <tbody>
        {holds.map((hold) => (
          <tr key={hold.id} className="align-top">
            <th scope="row" className="pe-3 text-start font-normal">
              {t(`contracts.history.hold.${hold.hold_type}`)}
            </th>
            <td className="pe-3">{t(`contracts.obligation.holds.source.${hold.hold_source}`)}</td>
            <td className="pe-3">{hold.reason}</td>
            <td className="pe-3" data-volatile="">
              {formatTimestamp(hold.applied_at)}
            </td>
            {releases ? (
              <td>
                {hold.release_refusal !== null ? (
                  hold.release_refusal
                ) : onRelease === null ? null : (
                  <Button variant="link" onClick={() => onRelease(hold.id)}>
                    {t("contracts.drawer.release.title")}
                  </Button>
                )}
              </td>
            ) : null}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function OverviewPanel({
  obligation,
  onRelease,
}: {
  readonly obligation: Obligation;
  /** "Release hold" of one of the obligation's holds; null for a viewer who is not offered it. */
  readonly onRelease: ((holdId: string) => void) | null;
}) {
  const currency = obligation.currency;
  const inline = (value: string, delta = false) => (
    <Money value={value} currency={currency} variant="inline" delta={delta} />
  );
  const position = obligation.position;
  return (
    <dl>
      <Definition label={t("contracts.obligation.overview.progress")}>
        {progressText(obligation)}
      </Definition>
      <Definition label={t("contracts.obligation.overview.billed")}>
        {inline(obligation.to_date.billed.amount)}
      </Definition>
      <Definition label={t("contracts.obligation.overview.catchUp")}>
        <span className="flex flex-col">
          {inline(obligation.to_date.catch_up.amount, true)}
          <span className="text-fg-3">
            {t("contracts.obligation.overview.catchUpParts", {
              modification: moneyText(obligation.to_date.catch_up_modification.amount, currency),
              tpChange: moneyText(obligation.to_date.catch_up_tp_change.amount, currency),
              estimate: moneyText(obligation.to_date.catch_up_estimate.amount, currency),
            })}
          </span>
        </span>
      </Definition>
      <Definition label={t("contracts.obligation.overview.remainingAllocation")}>
        {inline(obligation.remaining.allocation.amount)}
      </Definition>
      <Definition label={t("contracts.obligation.overview.remainingBilling")}>
        {inline(obligation.remaining.billing.amount)}
      </Definition>
      {/^0+(?:\.0+)?$/.test(obligation.to_date.returned_quantity) ? null : (
        <Definition label={t("contracts.obligation.overview.returned")}>
          {formatNumber(obligation.to_date.returned_quantity)}
        </Definition>
      )}
      <Definition label={t("contracts.obligation.overview.balance")}>
        {position.label === "CONTRACT_LIABILITY" || position.label === "CONTRACT_ASSET"
          ? t(`contracts.obligation.position.${position.label}`, {
              amount: moneyText(position.amount.amount, position.amount.currency),
            })
          : t("contracts.obligation.position.NONE")}
      </Definition>
      <Definition label={t("contracts.obligation.overview.satisfaction")}>
        {satisfactionText(obligation)}
      </Definition>
      <Definition label={t("contracts.obligation.overview.holds")}>
        {obligation.holds.length === 0 ? (
          t("contracts.obligation.overview.noHolds")
        ) : (
          <HoldsTable holds={obligation.holds} onRelease={onRelease} />
        )}
      </Definition>
    </dl>
  );
}

function AttributesPanel({ obligation }: { readonly obligation: Obligation }) {
  const template = obligation.pob_template_version;
  const overrides = Object.entries(obligation.account_overrides);
  const optional = (label: string, value: string | null | undefined, mono = false) =>
    value === null || value === undefined || value === "" ? null : (
      <Definition label={label}>
        {mono ? <span className="font-mono text-mono-sm">{value}</span> : value}
      </Definition>
    );
  const distinctness =
    obligation.distinctness === "series"
      ? t("contracts.obligation.attributes.seriesIncrement", {
          unit: obligation.series_increment_unit ?? NO_VALUE,
        })
      : t(`policies.ssp.distinctness.${obligation.distinctness}`);
  return (
    <dl>
      {optional(t("contracts.obligation.attributes.key"), obligation.obligation_key, true)}
      {optional(t("contracts.obligation.attributes.legacyKey"), obligation.legacy_record_key, true)}
      <Definition label={t("contracts.obligation.attributes.product")}>
        <span className="font-mono text-mono-sm">{obligation.product.code}</span>
        {` · ${obligation.product.name}`}
      </Definition>
      {optional(t("contracts.obligation.attributes.stratification"), obligation.stratification)}
      {optional(
        t("contracts.obligation.attributes.kind"),
        t(`contracts.obligation.kind.${obligation.obligation_kind}`),
      )}
      {optional(t("contracts.obligation.attributes.distinctness"), distinctness)}
      {optional(
        t("contracts.obligation.attributes.template"),
        `${template.template_code} v${String(template.version_no)}`,
        true,
      )}
      {optional(
        t("contracts.obligation.attributes.scope"),
        t(`contracts.obligation.scope.${obligation.scope_flag}`),
      )}
      {optional(
        t("contracts.obligation.attributes.pattern"),
        t(`policies.template.satisfaction.${obligation.satisfaction_pattern}`),
      )}
      {obligation.over_time_criterion === "NOT_APPLICABLE" || obligation.over_time_criterion === ""
        ? null
        : optional(
            t("contracts.obligation.attributes.criterion"),
            t(`contracts.obligation.criterion.${obligation.over_time_criterion}`),
          )}
      {optional(
        t("contracts.obligation.attributes.method"),
        t(`policies.template.method.${obligation.recognition_method}`),
      )}
      {obligation.ratable_convention === null
        ? null
        : optional(
            t("contracts.obligation.attributes.convention"),
            t(`policies.template.convention.${obligation.ratable_convention}`),
          )}
      {optional(
        t("contracts.obligation.attributes.principalAgent"),
        obligation.principal_agent,
        true,
      )}
      {optional(
        t("contracts.obligation.attributes.licenceNature"),
        obligation.licence_nature,
        true,
      )}
      {optional(t("contracts.obligation.attributes.warrantyType"), obligation.warranty_type, true)}
      {optional(
        t("contracts.obligation.attributes.startDate"),
        obligation.start_date === null ? null : formatDate(obligation.start_date),
      )}
      {optional(
        t("contracts.obligation.attributes.endDate"),
        obligation.end_date === null ? null : formatDate(obligation.end_date),
      )}
      {optional(
        t("contracts.obligation.attributes.contractingEntity"),
        `${obligation.contracting_entity.code} · ${obligation.contracting_entity.name}`,
      )}
      {optional(
        t("contracts.obligation.attributes.performingEntity"),
        `${obligation.performing_entity.code} · ${obligation.performing_entity.name}`,
      )}
      {optional(t("contracts.obligation.attributes.currency"), obligation.currency, true)}
      {optional(t("contracts.obligation.attributes.memo", { position: 1 }), obligation.memo_1)}
      {optional(t("contracts.obligation.attributes.memo", { position: 2 }), obligation.memo_2)}
      {optional(t("contracts.obligation.attributes.memo", { position: 3 }), obligation.memo_3)}
      {overrides.length === 0 ? null : (
        <Definition label={t("contracts.obligation.attributes.accountOverrides")}>
          <table className="w-full text-body-sm">
            <caption className="sr-only">
              {t("contracts.obligation.attributes.accountOverrides")}
            </caption>
            <thead>
              <tr className="text-caption text-fg-3">
                <th scope="col" className="pe-3 text-start font-medium">
                  {t("contracts.obligation.attributes.accountRole")}
                </th>
                <th scope="col" className="text-start font-medium">
                  {t("contracts.obligation.attributes.account")}
                </th>
              </tr>
            </thead>
            <tbody>
              {overrides.map(([role, account]) => (
                <tr key={role}>
                  <th scope="row" className="pe-3 text-start font-mono text-mono-sm font-normal">
                    {role}
                  </th>
                  <td>{`${account.code} · ${account.name}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Definition>
      )}
    </dl>
  );
}

function SspPanel({
  obligation,
  context,
  book,
  built,
}: {
  readonly obligation: Obligation;
  readonly context: string;
  readonly book: string | null;
  readonly built: ReadonlySet<string>;
}) {
  const ssp = obligation.ssp;
  const versionId = ssp.book_version_id;
  const label = useQuery({
    queryKey: sspVersionLabelKey(versionId ?? ""),
    queryFn: () => fetchSspVersionLabel(versionId ?? "", ssp.version_label),
    enabled: versionId !== null,
  });
  const currency = obligation.currency;
  const rate = (value: string | null) => formatRate(value, { kind: "unit", currency });
  const figure = (measure: string): FigureRef => ({
    objectType: "obligation",
    id: obligation.id,
    measure,
    book: book ?? undefined,
  });
  const original = obligation.original;
  const versionText = label.data?.label ?? ssp.version_label ?? NO_VALUE;
  const bookId = label.data?.bookId ?? null;
  const versionLink =
    versionId !== null && bookId !== null && built.has(SSP_BOOK_VERSION_ROUTE)
      ? `/policies/ssp-books/${bookId}/versions/${versionId}?f.product=${encodeURIComponent(obligation.product.code)}`
      : null;
  return (
    <div data-testid="SF-03-pane-ssp" className="flex flex-col gap-4">
      <section aria-labelledby="ssp-derivation" className="flex flex-col gap-1">
        <h3 id="ssp-derivation" className="text-body-sm font-medium text-fg-1">
          {t("contracts.obligation.ssp.derivation")}
        </h3>
        <dl>
          <Definition label={t("contracts.obligation.ssp.version")}>
            {versionLink === null ? (
              versionText
            ) : (
              <Link
                to={versionLink}
                className="underline decoration-control decoration-dotted underline-offset-3"
              >
                {versionText}
              </Link>
            )}
          </Definition>
          <Definition label={t("contracts.obligation.ssp.method")}>
            {ssp.method === null ? NO_VALUE : t(`policies.ssp.method.${ssp.method}`)}
          </Definition>
          {ssp.unit_list_price === null ? null : (
            <Definition label={t("contracts.obligation.ssp.unitListPrice")}>
              <span className="num">{rate(ssp.unit_list_price)}</span>
            </Definition>
          )}
          {ssp.midpoint_discount_ratio === null ? null : (
            <Definition label={t("contracts.obligation.ssp.midpointDiscount")}>
              <span className="num">
                {formatPercent(ssp.midpoint_discount_ratio, { kind: "share" })}
              </span>
            </Definition>
          )}
          {ssp.range_ratio === null ? null : (
            <Definition label={t("contracts.obligation.ssp.range")}>
              <span className="num">
                {t("contracts.obligation.ssp.rangeValue", {
                  percent: formatPercent(ssp.range_ratio, { kind: "share" }),
                })}
              </span>
            </Definition>
          )}
          <Definition label={t("contracts.allocation.column.low")}>
            <span className="num">{rate(original.ssp_low)}</span>
          </Definition>
          <Definition label={t("contracts.allocation.column.mid")}>
            <span className="num">{rate(original.ssp_mid)}</span>
          </Definition>
          <Definition label={t("contracts.allocation.column.high")}>
            <span className="num">{rate(original.ssp_high)}</span>
          </Definition>
          <Definition label={t("contracts.allocation.column.stated")}>
            <Money
              value={original.stated_price.amount}
              currency={original.stated_price.currency}
              variant="inline"
            />
          </Definition>
          <Definition label={t("contracts.obligation.ssp.rangePosition")}>
            {rangePositionText(ssp.range_position, ssp.outside_range_point)}
          </Definition>
          <Definition label={t("contracts.allocation.column.selected")}>
            <ExplainTrigger
              figureRef={figure("selected_ssp")}
              label={t("contracts.allocation.column.selected")}
              context={context}
              valueText={`${currency} ${rate(original.ssp_selected)}`}
            >
              <span className="num">{rate(original.ssp_selected)}</span>
            </ExplainTrigger>
          </Definition>
          {ssp.override_approval_request_id === null || !built.has(REQUEST_ROUTE) ? null : (
            <Definition label={t("contracts.obligation.ssp.override")}>
              <Link
                to={`/approvals/requests/${ssp.override_approval_request_id}`}
                className="underline decoration-control decoration-dotted underline-offset-3"
              >
                {t("contracts.obligation.ssp.overrideLink")}
              </Link>
            </Definition>
          )}
        </dl>
      </section>
      <section aria-labelledby="ssp-allocation" className="flex flex-col gap-1">
        <h3 id="ssp-allocation" className="text-body-sm font-medium text-fg-1">
          {t("contracts.obligation.ssp.allocation")}
        </h3>
        <dl>
          <Definition label={t("contracts.obligation.ssp.totalSsp")}>
            <span className="num">{rate(original.total_contract_ssp)}</span>
          </Definition>
          <Definition label={t("contracts.allocation.column.weight")}>
            <span className="num" aria-hidden="true">
              {formatPercent(obligation.current.allocation_weight, { kind: "share" })}
            </span>
            <span className="sr-only">
              {t("contracts.obligation.ssp.weightName", {
                percent: formatPercent(obligation.current.allocation_weight, { kind: "share" }),
              })}
            </span>
          </Definition>
          <Definition label={t("contracts.allocation.column.allocated")}>
            <Explained
              figure={figure("allocated_amount")}
              label={t("contracts.allocation.column.allocated")}
              context={context}
              value={obligation.current.allocated_amount.amount}
              currency={currency}
            />
          </Definition>
          <Definition label={t("contracts.allocation.column.adjustment")}>
            <Explained
              figure={figure("allocation_adjustment")}
              label={t("contracts.allocation.column.adjustment")}
              context={context}
              value={obligation.current.allocation_adjustment.amount}
              currency={currency}
              delta
            />
          </Definition>
          {obligation.current.unit_ssp === null ? null : (
            <Definition label={t("contracts.obligation.ssp.unitSsp")}>
              <span className="num">{rate(obligation.current.unit_ssp)}</span>
            </Definition>
          )}
          {obligation.current.remaining_unit_revenue_rate === null ? null : (
            <Definition label={t("contracts.obligation.ssp.remainingRate")}>
              <span className="num">{rate(obligation.current.remaining_unit_revenue_rate)}</span>
            </Definition>
          )}
        </dl>
      </section>
    </div>
  );
}

function SchedulePanel({
  obligation,
  recordContext,
  context,
  schedulesPath,
}: {
  readonly obligation: Obligation;
  readonly recordContext: RecordContext;
  readonly context: string;
  readonly schedulesPath: string | null;
}) {
  const lines = useQuery({
    queryKey: obligationScheduleKey(obligation.id, recordContext),
    queryFn: () => fetchObligationSchedule(obligation.id, recordContext),
  });
  if (lines.isPending) {
    return <Skeleton region={t("contracts.obligation.tabs.schedule")} shape="rows" count={4} />;
  }
  if (lines.isError) {
    return (
      <Banner
        tone="negative"
        title={t("contracts.obligation.schedule.loadError")}
        actions={
          <Button variant="link" onClick={() => void lines.refetch()}>
            {t("common.grid.retry")}
          </Button>
        }
      />
    );
  }
  if (lines.data.length === 0) {
    return <p className="text-body-sm text-fg-2">{t("contracts.obligation.schedule.empty")}</p>;
  }
  const currency = obligation.currency;
  return (
    <div className="flex flex-col gap-2">
      <table
        data-testid="SF-03-grid-obligation-schedule"
        className="w-full border-collapse text-body-sm"
      >
        <caption className="mb-1 text-start text-caption text-fg-3">
          {t("contracts.obligation.schedule.caption", { currency })}
        </caption>
        <thead>
          <tr className="border-b border-default bg-subtle text-fg-2">
            {(["period", "lineType", "state", "quantity", "amount", "cumulative"] as const).map(
              (column) => (
                <th
                  key={column}
                  scope="col"
                  className={
                    column === "quantity" || column === "amount" || column === "cumulative"
                      ? "px-2 py-1 text-end font-medium"
                      : "px-2 py-1 text-start font-medium"
                  }
                >
                  {t(`contracts.obligation.schedule.column.${column}`)}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody>
          {lines.data.map((line) => (
            <tr key={line.id} className="border-b border-hairline">
              <th scope="row" className="num px-2 py-1 text-start font-normal">
                {line.period.name}
              </th>
              <td className="px-2 py-1">{t(`contracts.schedule.lineType.${line.line_type}`)}</td>
              <td className="px-2 py-1">{t(`contracts.schedule.state.${line.state}`)}</td>
              <td className="num px-2 py-1 text-end">
                {line.quantity === null ? NO_VALUE : formatNumber(line.quantity)}
              </td>
              <td className="px-2 py-1 text-end">
                <ExplainTrigger
                  figureRef={{ objectType: "schedule_line", id: line.id, measure: "amount" }}
                  label={t("contracts.obligation.schedule.explainLabel", {
                    period: line.period.name,
                  })}
                  context={context}
                  valueText={moneyText(line.amount.amount, line.amount.currency)}
                >
                  <Money
                    value={line.amount.amount}
                    currency={line.amount.currency}
                    variant="cell"
                  />
                </ExplainTrigger>
              </td>
              <td className="px-2 py-1 text-end">
                <Money value={line.cumulative_amount.amount} currency={currency} variant="cell" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {schedulesPath === null ? null : (
        <Link
          to={`${schedulesPath}?f.obligation=is:${encodeURIComponent(obligation.obligation_key)}`}
          className="text-body-sm underline decoration-control decoration-dotted underline-offset-3"
        >
          {t("contracts.obligation.schedule.open")}
        </Link>
      )}
    </div>
  );
}

function eventDetails(event: ObligationEvent, currency: string): string {
  const payload = event.payload;
  const text = (name: string) =>
    typeof payload[name] === "string" ? (payload[name] as string) : null;
  const amount = (name: string) => {
    const value = payload[name];
    if (typeof value === "string") {
      return formatMoney(value, currency);
    }
    if (typeof value === "object" && value !== null && "amount" in value) {
      return formatMoney(String((value as { readonly amount: unknown }).amount), currency);
    }
    return null;
  };
  switch (event.event_type) {
    case "DELIVERY_RECORDED": {
      const trigger = text("trigger");
      return t("contracts.obligation.events.delivery", {
        quantity: formatNumber(text("quantity") ?? "0"),
        trigger: trigger === null ? NO_VALUE : t(`contracts.drawer.event.trigger.${trigger}`),
      });
    }
    case "BILLING_RECORDED":
      return t("contracts.obligation.events.invoice", {
        number: text("invoice_number") ?? NO_VALUE,
        amount: amount("amount") ?? NO_VALUE,
      });
    case "CREDIT_MEMO_RECORDED":
      return t("contracts.obligation.events.creditMemo", {
        number: text("credit_memo_number") ?? NO_VALUE,
        amount: amount("amount") ?? NO_VALUE,
      });
    case "RETURN_RECORDED":
      return t("contracts.obligation.events.return", {
        quantity: formatNumber(text("quantity") ?? "0"),
      });
    default:
      return NO_VALUE;
  }
}

function EventsPanel({
  obligation,
  knownAt,
  built,
  onOpen,
}: {
  readonly obligation: Obligation;
  readonly knownAt: string | null;
  readonly built: ReadonlySet<string>;
  readonly onOpen: (event: ObligationEvent) => void;
}) {
  const events = useQuery({
    queryKey: obligationEventsKey(obligation.id, knownAt),
    queryFn: () => fetchObligationEvents(obligation.id, knownAt),
  });
  if (events.isPending) {
    return <Skeleton region={t("contracts.obligation.tabs.events")} shape="rows" count={4} />;
  }
  if (events.isError) {
    return (
      <Banner
        tone="negative"
        title={t("contracts.obligation.events.loadError")}
        actions={
          <Button variant="link" onClick={() => void events.refetch()}>
            {t("common.grid.retry")}
          </Button>
        }
      />
    );
  }
  if (events.data.length === 0) {
    return <p className="text-body-sm text-fg-2">{t("contracts.obligation.events.empty")}</p>;
  }
  return (
    <table
      data-testid="SF-03-grid-obligation-events"
      className="w-full border-collapse text-body-sm"
    >
      <caption className="mb-1 text-start text-caption text-fg-3">
        {t("contracts.obligation.events.caption")}
      </caption>
      <thead>
        <tr className="border-b border-default bg-subtle text-fg-2">
          {(["effectiveDate", "event", "details", "origin", "approval", "recordedAt"] as const).map(
            (column) => (
              <th key={column} scope="col" className="px-2 py-1 text-start font-medium">
                {t(`contracts.obligation.events.column.${column}`)}
              </th>
            ),
          )}
        </tr>
      </thead>
      <tbody>
        {events.data.map((event) => (
          <tr key={event.id} className="border-b border-hairline">
            <td className="num px-2 py-1">{formatDate(event.effective_date)}</td>
            <th scope="row" className="px-2 py-1 text-start font-normal">
              <Button variant="link" onClick={() => onOpen(event)}>
                {t(`contracts.event.type.${event.event_type}`)}
              </Button>
            </th>
            <td className="px-2 py-1">{eventDetails(event, obligation.currency)}</td>
            <td className="px-2 py-1">{eventOriginText(event)}</td>
            <td className="px-2 py-1">
              {event.approval_request_id === null || !built.has(REQUEST_ROUTE) ? (
                NO_VALUE
              ) : (
                <Link
                  to={`/approvals/requests/${event.approval_request_id}`}
                  className="underline decoration-control decoration-dotted underline-offset-3"
                >
                  {t("contracts.obligation.events.viewRequest")}
                </Link>
              )}
            </td>
            <td className="px-2 py-1" data-volatile="">
              {formatTimestamp(event.recorded_at)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

type ReasonCode =
  | "DUPLICATE"
  | "CREATED_IN_ERROR"
  | "CUSTOMER_CANCELLED"
  | "DATA_CORRECTION"
  | "ESTIMATE_CORRECTION"
  | "OTHER";

/** The read-only event drawer of the Events panel with "Void event" (SCREENS §5.6). */
function EventDrawer({
  event,
  canVoid,
  onClose,
}: {
  readonly event: ObligationEvent;
  readonly canVoid: boolean;
  readonly onClose: () => void;
}) {
  const [voiding, setVoiding] = useState(false);
  const entries = Object.entries(event.payload);
  return (
    <Drawer
      open
      title={t(`contracts.event.type.${event.event_type}`)}
      subtitle={formatDate(event.effective_date)}
      initialFocus="title"
      primaryAction={
        canVoid
          ? { label: t("contracts.obligation.events.void"), onAction: () => setVoiding(true) }
          : undefined
      }
      onClose={onClose}
    >
      <dl data-testid="SF-03-drawer-event">
        {entries.map(([name, value]) => (
          <Definition key={name} label={name}>
            <span className="font-mono text-mono-sm">
              {typeof value === "string" ? value : JSON.stringify(value)}
            </span>
          </Definition>
        ))}
        {event.source_row === null ? null : (
          <Definition label={t("contracts.obligation.events.sourceRow")}>
            {t("contracts.obligation.events.origin.importRow", {
              row: formatNumber(event.source_row.row_number),
            })}
          </Definition>
        )}
        {event.supersedes_event_id === null ? null : (
          <Definition label={t("contracts.obligation.events.supersedes")}>
            <span className="font-mono text-mono-sm">{event.supersedes_event_id}</span>
          </Definition>
        )}
        {event.computation === null ? null : (
          <Definition label={t("contracts.obligation.events.computation")}>
            {String((event.computation as { readonly status?: unknown }).status ?? NO_VALUE)}
          </Definition>
        )}
      </dl>
      {voiding ? (
        <VoidEventModal event={event} onClose={() => setVoiding(false)} onDone={onClose} />
      ) : null}
    </Drawer>
  );
}

/** "Void this event?": a reason code and a reason; the void is a request for approval. */
export function VoidEventModal({
  event,
  onClose,
  onDone,
}: {
  readonly event: ObligationEvent;
  readonly onClose: () => void;
  readonly onDone: () => void;
}) {
  const toast = useToast();
  const noAnswer = useNoAnswer();
  const keys = useCommandKeys();
  const refresh = useRefreshRecord();
  const [code, setCode] = useState<ReasonCode | null>(null);
  const [comment, setComment] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const codes: readonly Choice<ReasonCode>[] = (
    [
      "DUPLICATE",
      "CREATED_IN_ERROR",
      "CUSTOMER_CANCELLED",
      "DATA_CORRECTION",
      "ESTIMATE_CORRECTION",
      "OTHER",
    ] as const
  ).map((value) => ({ value, label: t(`contracts.reasonCode.${value}`) }));
  const submit = async () => {
    setAttempted(true);
    if (code === null || reasonError(comment) !== null) {
      return;
    }
    setSubmitting(true);
    try {
      const outcome = await sendCommand(keys, "POST", `/api/v1/events/${event.id}/request-void`, {
        reason_code: code,
        comment: comment.trim(),
      });
      if (!outcome.ok) {
        setProblem(outcome.problem);
        return;
      }
      await refresh();
      toast.show({ tone: "positive", message: t("contracts.obligation.events.voidSubmitted") });
      onDone();
    } catch {
      // No answer: the next press sends the request under the same key (DG-FE-05).
      noAnswer();
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <Modal
      open
      variant="confirmation"
      title={t("contracts.obligation.events.voidTitle")}
      description={t("contracts.obligation.events.voidDescription")}
      submitting={submitting}
      primaryAction={{
        label: t("contracts.obligation.events.void"),
        destructive: true,
        onAction: () => void submit(),
      }}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        <RefusalBanner problem={problem} />
        <SelectField
          name="event-void-reason-code"
          label={t("contracts.obligation.events.reasonCode")}
          options={codes}
          value={code}
          onChange={setCode}
          error={attempted && code === null ? t("contracts.drawer.choose") : null}
        />
        <ReasonField
          name="event-void-comment"
          label={t("contracts.list.hold.reason")}
          value={comment}
          onChange={setComment}
          showError={attempted}
        />
      </div>
    </Modal>
  );
}

export interface ObligationPaneProps {
  readonly contract: Contract;
  readonly obligationId: string;
  readonly recordContext: RecordContext;
  readonly bookLabel: string;
  readonly permissions: readonly string[];
  /** SCR-ST-10 time travel: every command control is hidden. */
  readonly commandsHidden: boolean;
  readonly built: ReadonlySet<string>;
  readonly tab: PaneTab;
  readonly onTabChange: (tab: PaneTab) => void;
  readonly onCommand: (command: PaneCommand) => void;
  /**
   * "Change price" (SCREENS §5.8): given where the session may prepare a modification of the
   * contract (`modification.create`, an active contract, SF-07 built).
   */
  readonly onChangePrice?: ((obligationId: string) => void) | undefined;
  /** The obligations route of the contract with the context, for "Back to obligations". */
  readonly backPath: string;
}

export function ObligationPane({
  contract,
  obligationId,
  recordContext,
  bookLabel,
  permissions,
  commandsHidden,
  built,
  tab,
  onTabChange,
  onCommand,
  onChangePrice,
  backPath,
}: ObligationPaneProps) {
  const toast = useToast();
  const access = useAccess();
  const [openEvent, setOpenEvent] = useState<ObligationEvent | null>(null);
  const query = useQuery({
    queryKey: obligationKey(obligationId, recordContext),
    queryFn: () => fetchObligation(obligationId, recordContext),
    retry: (count, error) => !(error instanceof ApiProblem && error.status === 404) && count < 2,
  });

  if (query.isPending) {
    return (
      <div className="flex flex-col gap-3 p-[var(--panel-pad)]" aria-busy="true">
        <Skeleton region={t("contracts.obligation.region")} shape="text" count={2} />
        <Skeleton region={t("contracts.obligation.region")} shape="kpi" count={4} />
        <Skeleton region={t("contracts.obligation.region")} shape="rows" count={4} />
      </div>
    );
  }
  const notFound =
    (query.isError && query.error instanceof ApiProblem && query.error.status === 404) ||
    (query.data !== undefined && query.data.contract_id !== contract.id);
  if (notFound) {
    return (
      <div className="flex flex-col items-start gap-2 p-[var(--panel-pad)]">
        <p className="text-body text-fg-1">{t("contracts.obligation.notFound")}</p>
        <Link
          to={backPath}
          className="text-body-sm underline decoration-control decoration-dotted underline-offset-3"
        >
          {t("contracts.obligation.back")}
        </Link>
      </div>
    );
  }
  if (query.isError) {
    return (
      <div className="p-[var(--panel-pad)]">
        <Banner
          tone="negative"
          title={t("contracts.obligation.loadError")}
          actions={
            <Button variant="link" onClick={() => void query.refetch()}>
              {t("common.grid.retry")}
            </Button>
          }
        >
          <p>{query.error.message}</p>
        </Banner>
      </div>
    );
  }

  const obligation = query.data;
  const currency = obligation.currency;
  const key = obligation.obligation_key;
  const context = [contract.external_id, key, bookLabel, contract.contracting_entity.code].join(
    " · ",
  );
  const book = recordContext.book;
  const active = contract.status === "ACTIVE" || contract.status === "COMPLETED";
  const kinds =
    active && permissions.includes(EVENT_RECORD_PERMISSION) ? eventKindsFor(obligation) : [];
  const canCreate = permissions.includes(CONTRACT_CREATE_PERMISSION);
  const overflow: MenuItem[] = [];
  if (canCreate) {
    overflow.push(
      {
        id: "hold",
        label: t("contracts.list.bulk.hold"),
        onSelect: () => onCommand({ kind: "apply-hold", obligationKey: key }),
      },
      {
        id: "memos",
        label: t("contracts.drawer.memos.title"),
        onSelect: () => onCommand({ kind: "edit-memos", obligationKey: key }),
      },
    );
  }
  overflow.push({
    id: "copy-link",
    label: t("contracts.list.row.copyLink"),
    onSelect: () => {
      void navigator.clipboard
        .writeText(globalThis.location.href)
        .then(() => toast.show({ tone: "neutral", message: t("contracts.list.row.copied") }));
    },
  });
  const actions = commandsHidden ? undefined : (
    <>
      {kinds.length === 0 ? null : (
        <Menu
          label={t("contracts.obligation.actions.recordEvent")}
          size="sm"
          items={kinds.map((kind) => ({
            id: kind,
            label: t(`contracts.drawer.event.title.${kind}`),
            onSelect: () => onCommand({ kind: "record-event", event: kind, obligationKey: key }),
          }))}
        />
      )}
      {onChangePrice === undefined ? null : (
        <Button variant="secondary" size="sm" onClick={() => onChangePrice(obligation.id)}>
          {t("contracts.obligation.actions.changePrice")}
        </Button>
      )}
      <Menu
        label={t("contracts.obligation.actions.more", { key })}
        icon={DotsThree}
        iconOnly
        variant="ghost"
        size="sm"
        align="end"
        items={overflow}
      />
    </>
  );

  const bar = (ratio: string | null, figureLabel: string) =>
    ratio === null
      ? {}
      : {
          bar: { ratio, overLabel: t("contracts.obligation.overAllocation") },
          secondary: t("contracts.obligation.ofAllocation", { ratio: formatPercent(ratio) }),
          label: figureLabel,
        };
  const kpis: Kpi[] = [
    {
      id: "allocated",
      label: t("contracts.allocation.column.allocated"),
      value: obligation.current.allocated_amount.amount,
      currency,
      testId: "SF-03-kpi-allocated-amount",
      explain: {
        figureRef: figureFromLink(obligation.links.explain_allocated_amount, book) ?? {
          objectType: "obligation",
          id: obligation.id,
          measure: "allocated_amount",
        },
        context,
      },
    },
    {
      id: "recognized",
      label: t("contracts.workbench.kpi.recognized"),
      value: obligation.to_date.revenue.amount,
      currency,
      testId: "SF-03-kpi-revenue-to-date",
      explain: {
        figureRef: figureFromLink(obligation.links.explain_revenue_to_date, book) ?? {
          objectType: "obligation",
          id: obligation.id,
          measure: "revenue_to_date",
        },
        context,
      },
      ...bar(obligation.ratios.recognized, t("contracts.workbench.kpi.recognized")),
    },
    {
      id: "scheduled",
      label: t("contracts.workbench.kpi.scheduled"),
      value: obligation.scheduled.amount,
      currency,
      testId: "SF-03-kpi-scheduled",
      explain: {
        figureRef: {
          objectType: "obligation",
          id: obligation.id,
          measure: "scheduled",
          book: book ?? undefined,
        },
        context,
      },
      ...bar(obligation.ratios.scheduled, t("contracts.workbench.kpi.scheduled")),
    },
    {
      id: "awaiting",
      label: t("contracts.workbench.kpi.awaitingTrigger"),
      value: obligation.awaiting_trigger.amount,
      currency,
      testId: "SF-03-kpi-awaiting-trigger",
      explain: {
        figureRef: {
          objectType: "obligation",
          id: obligation.id,
          measure: "awaiting_trigger",
          book: book ?? undefined,
        },
        context,
      },
      ...bar(obligation.ratios.awaiting_trigger, t("contracts.workbench.kpi.awaitingTrigger")),
    },
  ];

  const tabs = PANE_TABS.map((id) => ({ id, label: t(`contracts.obligation.tabs.${id}`) }));
  const schedulesPath = built.has(SCHEDULES_ROUTE) ? `/contracts/${contract.id}/schedules` : null;
  let panel: ReactNode;
  switch (tab) {
    case "overview":
      panel = (
        <OverviewPanel
          obligation={obligation}
          onRelease={
            // SCREENS §5.6 (rev 1.75): for a holder of `contract.create` for the contract's entity
            // (04 API-R-28; asked of the access module), not on a view of an earlier `known_at`.
            !commandsHidden && access.holds(CONTRACT_CREATE_PERMISSION, contract.contracting_entity)
              ? (holdId) => onCommand({ kind: "release-hold", holdId })
              : null
          }
        />
      );
      break;
    case "attributes":
      panel = <AttributesPanel obligation={obligation} />;
      break;
    case "ssp":
      panel = <SspPanel obligation={obligation} context={context} book={book} built={built} />;
      break;
    case "schedule":
      panel = (
        <SchedulePanel
          obligation={obligation}
          recordContext={recordContext}
          context={context}
          schedulesPath={schedulesPath}
        />
      );
      break;
    case "events":
      panel = (
        <EventsPanel
          obligation={obligation}
          knownAt={recordContext.knownAt}
          built={built}
          onOpen={setOpenEvent}
        />
      );
      break;
  }

  return (
    <div className="flex flex-col">
      <RecordHeader
        variant="compact"
        title={obligation.product.name}
        identifier={{ value: key }}
        chips={<ObligationChips obligation={obligation} />}
        actions={actions}
        kpis={
          <KpiStrip
            compact
            headingLevel={3}
            heading={t("contracts.obligation.figures.heading", { currency })}
            kpis={kpis}
          />
        }
      />
      <div className="p-[var(--panel-pad)]">
        <PanelTabs
          label={t("contracts.obligation.tabs.label")}
          tabs={tabs}
          selectedId={tab}
          onChange={(id) => {
            if (isPaneTab(id)) {
              onTabChange(id);
            }
          }}
        >
          {panel}
        </PanelTabs>
      </div>
      {openEvent === null ? null : (
        <EventDrawer
          event={openEvent}
          canVoid={!commandsHidden && permissions.includes(EVENT_RECORD_PERMISSION)}
          onClose={() => setOpenEvent(null)}
        />
      )}
    </div>
  );
}
