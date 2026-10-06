// SF-03:estimate — the detail of an estimated element (SCREENS §8.3 to §8.8, §8.10; §0.4 RT-13; §0.8
// E-12; DESIGN_SYSTEM DS-CMP-06 compact, DS-CMP-07, DS-CMP-10 static, DS-CMP-11, DS-CMP-16, DS-CMP-29;
// 04 API-R-32 `GET /estimates/{id}/versions`, `POST /estimate-versions/{id}/submit`, `/withdraw`,
// API-R-12 `GET /attachments`, API-R-33 `GET /judgements`; PRD SM-04, POL-040, POL-042; BUILD_SPEC
// CTR-25). The header with the method chip, the figures of the latest version, the banner slot (a
// draft, a pending request, a reassessment that is due) and the panel tabs "Current version",
// "Versions" and "Evidence"; the drawer of a version, the "Attest no change" modal and the withdrawal.
//
// The master row and the strip show the latest version and name it; "Current version" is the approved
// one, with the catch-up of the preview it was submitted with (kept with its approval request) and
// its evidence. "Discard draft" voids a draft version after a confirmation (`POST
// /estimate-versions/{id}/discard`, 04 §16.14 rev 1.210, item EST-DISCARD-1): the version keeps its
// number, reads Void and is no longer the latest one. The
// Versions panel is the static table at every size: the screen holds every version of the element for
// the figures and the comparison. The comparison is of the two rows the screen holds, field by field,
// and states no difference in money (ruling R-93 (c)).
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { DateInput } from "../../components/form/DateInput";
import { Field } from "../../components/form/Field";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { DotsThree, WarningCircle } from "../../components/icons/registry";
import { Money } from "../../components/money/Money";
import { NoValue } from "../../components/money/Num";
import { type Kpi, KpiStrip } from "../../components/record/KpiStrip";
import { RecordHeader } from "../../components/record/RecordHeader";
import { PanelTabs } from "../../components/record/Tabs";
import { Button } from "../../components/ui/Button";
import { cn } from "../../components/ui/cn";
import { Menu, type MenuItem } from "../../components/ui/Menu";
import { Modal } from "../../components/ui/Modal";
import { chipFor, StatusChip, ToneChip } from "../../components/ui/StatusChip";
import { isTypingTarget } from "../../lib/a11y/typing";
import { useCommandKeys } from "../../lib/api/commands";
import { approvalKey, FILE_CONTENT_PATH, requestRoute } from "../../lib/api/queries/approvals";
import {
  type Attachment,
  type Contract,
  type Judgement,
  sendCommand,
} from "../../lib/api/queries/contracts";
import {
  currentAndLatest,
  type Estimate,
  ESTIMATE_RECORD_KEYS,
  type EstimateVersion,
  estimateVersionPath,
  estimateVersionsKey,
  estimateVersionsPath,
  fetchEstimateVersions,
  fetchJudgement,
  fetchVersionAttachments,
  fetchVersionJudgements,
  fetchVersionRequest,
  judgementKey,
  openVersions,
  versionAttachmentsKey,
  versionJudgementsKey,
  versionRequestKey,
} from "../../lib/api/queries/estimates";
import type { ExceptionItem } from "../../lib/api/queries/exceptions";
import { judgementStatusLabel, recordStands } from "../../lib/api/queries/judgements";
import { dateOf } from "../../lib/forms/contract";
import {
  attestationBody,
  EVIDENCE_REQUIRED,
  factorsOf,
  type Figure,
  figureBlank,
  figuresOf,
  isAttestation,
  keyFigure,
  membersOf,
  methodLocked,
  scenariosOf,
} from "../../lib/forms/estimate";
import {
  formatDate,
  formatMoney,
  formatNumber,
  formatPercent,
  formatTimestamp,
  MINUS_SIGN,
  NO_VALUE,
} from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { requestNumber } from "./drawers/common";
import {
  type Failure,
  FailureNotice,
  figureText,
  kindLabel,
  MethodChip,
  type PeriodLabel,
  targetLabel,
} from "./estimate-parts";
import { VersionDrawer, type VersionDrawerMode } from "./estimate-version";
import { DiscardRecord } from "./judgement-discard";

/** SCREENS §8.1 `pane` values; "current" is the default and leaves the URL without the parameter. */
export const ESTIMATE_PANES = ["current", "versions", "evidence"] as const;
export type EstimatePaneTab = (typeof ESTIMATE_PANES)[number];

export function isEstimatePane(value: string | null): value is EstimatePaneTab {
  return value !== null && (ESTIMATE_PANES as readonly string[]).includes(value);
}

function versionNumber(version: Pick<EstimateVersion, "version_no">): string {
  return formatNumber(version.version_no, { kind: "count" });
}

function StatusOf({ status }: { readonly status: string }) {
  const chip = chipFor("E-12", status);
  return chip === null ? <span>{status}</span> : <StatusChip status={chip.status} />;
}

const CELL = "px-2 py-1.5";
const HEAD = "px-2 py-1.5 font-medium";

// ---------------------------------------------------------------------------------------------------
// "Current version" (SCREENS §8.3): the definition list of one version.

function scenarioText(version: EstimateVersion, currency: string | null): string | null {
  const rows = scenariosOf(version);
  if (rows.length === 0) {
    return null;
  }
  return rows
    .map((row) => {
      const amount = figureText(
        { id: "amount", label: "", type: "money", value: row.amount },
        currency,
      );
      return row.probability === null
        ? `${row.outcome}: ${amount}`
        : t("contracts.estimates.scenarios.lineWithProbability", {
            outcome: row.outcome,
            amount,
            probability: formatPercent(row.probability, { kind: "share" }),
          });
    })
    .join("; ");
}

function factorText(version: EstimateVersion): string | null {
  const factors = factorsOf(version);
  return factors.length === 0
    ? null
    : factors.map((factor) => t(`contracts.estimates.factors.${factor}`)).join("; ");
}

const LINK = "text-body-sm underline decoration-control decoration-dotted underline-offset-3";

/** An attachment as the link that opens its file. */
function FileLink({ file }: { readonly file: Attachment }) {
  return (
    <a
      href={`${FILE_CONTENT_PATH}/${file.file_object_id}/content`}
      className="text-fg-1 underline decoration-control decoration-dotted underline-offset-3"
    >
      {file.original_filename ?? file.file_object_id}
    </a>
  );
}

/** The statuses whose request holds the preview of the version as it stands (04 E-12). */
const SNAPSHOT_STATUSES: ReadonlySet<string> = new Set(["SUBMITTED", "APPROVED", "SUPERSEDED"]);

function Item({ label, children }: { readonly label: string; readonly children: ReactNode }) {
  return (
    <div className="grid grid-cols-[12rem_1fr] gap-x-4 gap-y-0.5 py-1">
      <dt className="text-body-sm text-fg-3">{label}</dt>
      <dd className="text-body text-fg-1">{children}</dd>
    </div>
  );
}

function VersionDetails({
  estimate,
  version,
  ctxSearch,
}: {
  readonly estimate: Estimate;
  readonly version: EstimateVersion;
  readonly ctxSearch: string;
}) {
  const kind = estimate.estimate_kind;
  const variable = kind === "VARIABLE_CONSIDERATION";
  const scenarios = variable ? scenarioText(version, version.currency) : null;
  const factors = variable ? factorText(version) : null;
  // SCREENS §8.3 "its preview snapshot": the dry run a version was submitted with is kept with its
  // approval request (REQ-PLT-015), which a reader may not see; a version that came back or was
  // edited since is no longer the one its last request previewed.
  const requestId = SNAPSHOT_STATUSES.has(version.status) ? version.approval_request_id : null;
  const request = useQuery({
    queryKey: versionRequestKey(requestId ?? "", version.status),
    queryFn: () => fetchVersionRequest(requestId ?? ""),
    enabled: requestId !== null,
    retry: false,
  });
  const files = useQuery({
    queryKey: versionAttachmentsKey(version.id),
    queryFn: () => fetchVersionAttachments(version.id),
  });
  const reading = (requestId !== null && request.isPending) || files.isPending;
  const catchUp = request.data?.impact_preview?.summary.catch_up_total ?? null;
  const evidence = files.data ?? [];
  return (
    <div data-testid="SF-03-estimate-version" className="flex flex-col">
      <dl className="flex flex-col">
        <Item label={t("contracts.estimates.column.version")}>
          <span className="inline-flex items-center gap-2">
            <span className="num">{versionNumber(version)}</span>
            <StatusOf status={version.status} />
          </span>
        </Item>
        <Item label={t("contracts.estimates.field.effectiveDate")}>
          {formatDate(version.effective_date)}
        </Item>
        {variable && isAttestation(version) ? (
          <Item label={t("contracts.estimates.column.attestation")}>
            {t("contracts.estimates.attestation.yes")}
          </Item>
        ) : null}
        {scenarios === null ? null : (
          <Item label={t("contracts.estimates.scenarios.title")}>{scenarios}</Item>
        )}
        {membersOf(kind, version).map((figure) => (
          <Item key={figure.id} label={t(figure.label)}>
            <span className={figure.type === "flag" ? undefined : "num"}>
              {figureText(figure, version.currency)}
            </span>
          </Item>
        ))}
        {variable && version.excluded_amount != null ? (
          <Item label={t("contracts.estimates.field.excludedAmount")}>
            <span className="num">
              {figureText(
                { id: "excluded", label: "", type: "money", value: version.excluded_amount.amount },
                version.currency,
              )}
            </span>
          </Item>
        ) : null}
        {factors === null ? null : (
          <Item label={t("contracts.estimates.factors.legend")}>{factors}</Item>
        )}
        <Item label={t("contracts.drawer.rationale")}>
          <span className="whitespace-pre-wrap">{version.rationale}</span>
        </Item>
        <Item label={t("contracts.estimates.column.preparedBy")}>
          {version.created_by.display_name}
        </Item>
        {version.approver === null ? null : (
          <Item label={t("contracts.estimates.column.approvedBy")}>
            {version.approver.display_name}
            {version.approved_at === null ? null : (
              <span className="ms-2 text-fg-3" data-volatile="">
                {formatTimestamp(version.approved_at)}
              </span>
            )}
          </Item>
        )}
      </dl>
      {reading ? (
        <div className="py-1">
          <Skeleton region={t("contracts.estimates.current.reading")} shape="text" count={2} />
        </div>
      ) : catchUp === null && evidence.length === 0 ? null : (
        <dl className="flex flex-col">
          {catchUp === null || requestId === null ? null : (
            <Item label={t("contracts.drawer.preview.title")}>
              <span className="inline-flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                <span data-testid="SF-03-estimate-version-catch-up">
                  {t("contracts.drawer.preview.catchUp")}{" "}
                  <Money value={catchUp.amount} currency={catchUp.currency} delta />
                </span>
                <Link to={`${requestRoute(requestId)}${ctxSearch}`} className={LINK}>
                  {t("contracts.workbench.banner.viewRequest")}
                </Link>
              </span>
            </Item>
          )}
          {evidence.length === 0 ? null : (
            <Item label={t("contracts.drawer.evidence")}>
              <ul
                aria-label={t("contracts.estimates.evidence.files", {
                  version: versionNumber(version),
                })}
                className="flex flex-col gap-0.5"
              >
                {evidence.map((file) => (
                  <li key={file.id}>
                    <FileLink file={file} />
                  </li>
                ))}
              </ul>
            </Item>
          )}
        </dl>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// "Versions" (SCREENS §8.5).

interface CompareRow {
  readonly id: string;
  readonly label: string;
  readonly before: string | null;
  readonly after: string | null;
  readonly change: "added" | "removed" | "changed";
}

/** The fields in which two versions differ, as the two rows read (the earlier version first). */
export function compareVersions(
  estimate: Estimate,
  from: EstimateVersion,
  to: EstimateVersion,
): readonly CompareRow[] {
  const kind = estimate.estimate_kind;
  const read = (
    version: EstimateVersion,
  ): readonly (readonly [string, string, string | null])[] => {
    const shown = (figure: Figure): string | null =>
      figureBlank(figure) ? null : figureText(figure, version.currency);
    const rows: (readonly [string, string, string | null])[] = [
      [
        "effective_date",
        t("contracts.estimates.field.effectiveDate"),
        formatDate(version.effective_date),
      ],
      ...membersOf(kind, version).map(
        (figure) => [figure.id, t(figure.label), shown(figure)] as const,
      ),
    ];
    if (kind === "VARIABLE_CONSIDERATION") {
      rows.push(
        [
          "scenarios",
          t("contracts.estimates.scenarios.title"),
          scenarioText(version, version.currency),
        ],
        ["factors", t("contracts.estimates.factors.legend"), factorText(version)],
        [
          "attestation",
          t("contracts.estimates.column.attestation"),
          isAttestation(version) ? t("contracts.estimates.attestation.yes") : null,
        ],
      );
    }
    rows.push(["rationale", t("contracts.drawer.rationale"), version.rationale]);
    return rows;
  };
  const after = new Map(read(to).map(([id, , value]) => [id, value]));
  return read(from).flatMap(([id, label, before]): CompareRow[] => {
    const value = after.get(id) ?? null;
    if (value === before) {
      return [];
    }
    return [
      {
        id,
        label,
        before,
        after: value,
        change: before === null ? "added" : value === null ? "removed" : "changed",
      },
    ];
  });
}

const MARKER: Readonly<Record<CompareRow["change"], string>> = {
  removed: MINUS_SIGN,
  added: "+",
  changed: "~",
};

function ComparePanel({
  estimate,
  from,
  to,
  onClose,
}: {
  readonly estimate: Estimate;
  readonly from: EstimateVersion;
  readonly to: EstimateVersion;
  readonly onClose: () => void;
}) {
  const versions = { from: versionNumber(from), to: versionNumber(to) };
  const rows = compareVersions(estimate, from, to);
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-hairline bg-surface p-[var(--panel-pad)]">
      <table data-testid="SF-03-diff-estimate" className="w-full border-collapse text-body-sm">
        <caption className="pb-2 text-start text-body-sm font-semibold text-fg-1">
          {t("contracts.history.compare.caption", versions)}
        </caption>
        <thead>
          <tr className="border-b border-default text-caption text-fg-3">
            <th scope="col" className={`${HEAD} w-16 text-start`}>
              {t("common.diff.column.change")}
            </th>
            <th scope="col" className={`${HEAD} text-start`}>
              {t("common.diff.column.field")}
            </th>
            <th scope="col" className={`${HEAD} text-start`}>
              {t("contracts.history.compare.version", { version: versions.from })}
            </th>
            <th scope="col" className={`${HEAD} text-start`}>
              {t("contracts.history.compare.version", { version: versions.to })}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              data-change={row.change}
              className={cn(
                "border-b border-hairline align-top",
                row.change === "removed" && "bg-diff-removed-bg",
                row.change === "added" && "bg-diff-added-bg",
              )}
            >
              <td className={CELL}>
                <span aria-hidden="true" className="num font-medium text-fg-1">
                  {MARKER[row.change]}
                </span>
                <span className="sr-only">{t(`common.diff.prefix.${row.change}`)}</span>
              </td>
              <th scope="row" className={`${CELL} text-start font-medium text-fg-1`}>
                {row.label}
              </th>
              <td className={cn(CELL, row.change === "changed" && "bg-diff-removed-bg")}>
                <span className={cn(row.change !== "added" && "text-fg-2 line-through")}>
                  {row.before ?? NO_VALUE}
                </span>
              </td>
              <td className={cn(CELL, row.change === "changed" && "bg-diff-added-bg")}>
                {row.after ?? NO_VALUE}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 ? (
        <p className="text-body-sm text-fg-2">{t("contracts.history.compare.none", versions)}</p>
      ) : null}
      <div>
        <Button variant="secondary" size="sm" onClick={onClose}>
          {t("contracts.history.compare.close")}
        </Button>
      </div>
    </div>
  );
}

/** The header cells of the versions table: the rule below the header and its ground. */
const HEAD_ROW = "border-b border-default bg-subtle";
/** The pinned columns of the versions table: the selection box, then the version number. */
const PINNED_SELECT = "sticky start-0 z-[var(--z-sticky)] w-8 min-w-8";
const PINNED_VERSION = "sticky start-8 z-[var(--z-sticky)] border-e border-e-default";

/** §8.5: "Rate" is its own column where the kind's key figure is not the rate itself. */
const RATE_COLUMN: ReadonlySet<string> = new Set(["RETURN_RATE"]);

function VersionsPanel({
  estimate,
  versions,
}: {
  readonly estimate: Estimate;
  readonly versions: readonly EstimateVersion[];
}) {
  const reasonId = useId();
  const [selected, setSelected] = useState<readonly string[]>([]);
  const [compared, setCompared] = useState<readonly [string, string] | null>(null);
  const kind = estimate.estimate_kind;
  const variable = kind === "VARIABLE_CONSIDERATION";
  const rate = RATE_COLUMN.has(kind);
  const byId = new Map(versions.map((item) => [item.id, item]));
  const chosen = selected.flatMap((id) => {
    const version = byId.get(id);
    return version === undefined ? [] : [version];
  });
  const pair =
    chosen.length === 2
      ? ([...chosen].sort((a, b) => a.version_no - b.version_no) as [
          EstimateVersion,
          EstimateVersion,
        ])
      : null;
  const shownPair =
    compared === null ? null : ([byId.get(compared[0]), byId.get(compared[1])] as const);
  const toggle = (id: string) =>
    setSelected((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  const headers: readonly (readonly [string, boolean])[] = [
    [t("contracts.estimates.column.version"), true],
    [t("contracts.estimates.column.status"), false],
    [t("contracts.estimates.field.effectiveDate"), false],
    ...(variable ? [] : [[t("contracts.estimates.column.figure"), true] as const]),
    ...(variable ? [[t("contracts.estimates.field.constrainedAmount"), true] as const] : []),
    ...(rate ? [[t("contracts.estimates.field.rate"), true] as const] : []),
    ...(variable ? [[t("contracts.estimates.column.attestation"), false] as const] : []),
    [t("contracts.estimates.column.preparedBy"), false],
    [t("contracts.estimates.column.approvedBy"), false],
    [t("contracts.estimates.column.approvedAt"), false],
    [t("contracts.drawer.rationale"), false],
  ];
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-end">
        <Button
          variant={pair === null ? "secondary" : "primary"}
          size="sm"
          aria-describedby={pair === null ? reasonId : undefined}
          disabledReason={pair === null ? t("contracts.history.compare.selectTwo") : undefined}
          onClick={() => setCompared(pair === null ? null : [pair[0].id, pair[1].id])}
        >
          {t("contracts.history.compare.action")}
        </Button>
      </div>
      {/* DS-SP-07: a wide table scrolls inside its own viewport; the selection and the version stay. */}
      <div className="overflow-x-auto">
        <table
          data-testid="SF-03-grid-estimate-versions"
          className="w-max min-w-full border-separate border-spacing-0 text-body-sm"
        >
          <caption className="pb-1 text-start text-caption text-fg-3">
            {t("contracts.estimates.versions.caption")}
          </caption>
          <thead>
            <tr className="text-fg-2">
              <th scope="col" className={cn(HEAD, HEAD_ROW, PINNED_SELECT, "bg-subtle text-start")}>
                <span className="sr-only">{t("contracts.estimates.versions.select")}</span>
              </th>
              {headers.map(([label, end], index) => (
                <th
                  key={label}
                  scope="col"
                  className={cn(
                    HEAD,
                    HEAD_ROW,
                    "whitespace-nowrap",
                    end ? "text-end" : "text-start",
                    index === 0 && PINNED_VERSION,
                  )}
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {versions.map((version) => {
              const figure = keyFigure(kind, version);
              const number = versionNumber(version);
              return (
                <tr
                  key={version.id}
                  data-testid={`SF-03-row-estimate-version-${String(version.version_no)}`}
                  className="align-top [&>*]:border-b [&>*]:border-hairline"
                >
                  <td className={cn(CELL, PINNED_SELECT, "bg-surface")}>
                    <input
                      type="checkbox"
                      aria-label={t("contracts.estimates.versions.selectRow", { version: number })}
                      checked={selected.includes(version.id)}
                      onChange={() => toggle(version.id)}
                    />
                  </td>
                  <th
                    scope="row"
                    className={cn(
                      CELL,
                      PINNED_VERSION,
                      "num bg-surface text-end font-medium text-fg-1",
                    )}
                  >
                    {number}
                  </th>
                  <td className={CELL}>
                    <StatusOf status={version.status} />
                  </td>
                  <td className={`${CELL} whitespace-nowrap`}>
                    {formatDate(version.effective_date)}
                  </td>
                  {variable ? null : (
                    <td className={`${CELL} num text-end`}>
                      {figureText(figure, version.currency)}
                    </td>
                  )}
                  {variable ? (
                    <td className={`${CELL} num text-end`}>
                      {version.constrained_amount === null || version.currency === null ? (
                        <NoValue />
                      ) : (
                        formatMoney(version.constrained_amount, version.currency)
                      )}
                    </td>
                  ) : null}
                  {rate ? (
                    <td className={`${CELL} num text-end`}>
                      {version.rate === null ? (
                        <NoValue />
                      ) : (
                        formatPercent(version.rate, { kind: "share" })
                      )}
                    </td>
                  ) : null}
                  {variable ? (
                    <td className={CELL}>
                      {isAttestation(version) ? t("common.grid.yes") : t("common.grid.no")}
                    </td>
                  ) : null}
                  <td className={`${CELL} whitespace-nowrap`}>{version.created_by.display_name}</td>
                  <td className={`${CELL} whitespace-nowrap`}>
                    {version.approver === null ? <NoValue /> : version.approver.display_name}
                  </td>
                  <td className={`${CELL} whitespace-nowrap`} data-volatile="">
                    {version.approved_at === null ? (
                      <NoValue />
                    ) : (
                      formatTimestamp(version.approved_at)
                    )}
                  </td>
                  <td className={CELL}>
                    <span className="block w-72 truncate" title={version.rationale}>
                      {version.rationale}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {pair === null ? (
        <p id={reasonId} className="text-body-sm text-fg-3">
          {t("contracts.history.compare.selectTwo")}
        </p>
      ) : null}
      {shownPair === null || shownPair[0] === undefined || shownPair[1] === undefined ? null : (
        <ComparePanel
          estimate={estimate}
          from={shownPair[0]}
          to={shownPair[1]}
          onClose={() => setCompared(null)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// "Evidence" (SCREENS §8.3, §8.6): the attachments and the judgement records of every version.

function EvidencePanel({
  contract,
  versions,
  commands,
}: {
  readonly contract: Contract;
  readonly versions: readonly EstimateVersion[];
  /** The view takes commands: it is not one of an earlier known_at. */
  readonly commands: boolean;
}) {
  const attachments = useQueries({
    queries: versions.map((version) => ({
      queryKey: versionAttachmentsKey(version.id),
      queryFn: () => fetchVersionAttachments(version.id),
    })),
  });
  const judgements = useQueries({
    queries: versions.map((version) => ({
      queryKey: versionJudgementsKey(version.id),
      queryFn: () => fetchVersionJudgements(version.id),
    })),
  });
  const reads = [...attachments, ...judgements];
  const label = t("contracts.estimates.evidence.region");
  if (reads.some((read) => read.isPending)) {
    return <Skeleton region={label} shape="rows" count={3} />;
  }
  const failed = reads.find((read) => read.isError);
  if (failed !== undefined) {
    return (
      <Banner
        tone="negative"
        title={t("contracts.estimates.evidence.loadError")}
        headingLevel={4}
        actions={
          <Button variant="link" onClick={() => reads.forEach((read) => void read.refetch())}>
            {t("common.grid.retry")}
          </Button>
        }
      />
    );
  }
  const groups = versions.map((version, index) => ({
    version,
    files: (attachments[index]?.data ?? []) as readonly Attachment[],
    records: (judgements[index]?.data ?? []) as readonly Judgement[],
  }));
  if (groups.every((group) => group.files.length === 0 && group.records.length === 0)) {
    return <p className="text-body-sm text-fg-2">{t("contracts.estimates.evidence.none")}</p>;
  }
  return (
    <div className="flex flex-col gap-4">
      {groups
        .filter((group) => group.files.length > 0 || group.records.length > 0)
        .map(({ version, files, records }) => (
          <section
            key={version.id}
            aria-label={t("contracts.history.compare.version", {
              version: versionNumber(version),
            })}
            className="flex flex-col gap-2"
          >
            <h4 className="flex items-center gap-2 text-title-sm text-fg-1">
              {t("contracts.history.compare.version", { version: versionNumber(version) })}
              <StatusOf status={version.status} />
            </h4>
            {files.length === 0 ? null : (
              <table className="w-full border-collapse text-body-sm">
                <caption className="sr-only">
                  {t("contracts.estimates.evidence.files", { version: versionNumber(version) })}
                </caption>
                <thead>
                  <tr className="border-b border-default text-caption text-fg-3">
                    {(["file", "size", "uploadedBy", "uploadedAt"] as const).map((column) => (
                      <th key={column} scope="col" className="py-1 pe-3 text-start font-medium">
                        {t(`contracts.documents.column.${column}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {files.map((item) => (
                    <tr key={item.id} className="border-b border-hairline align-top">
                      <th scope="row" className="py-1 pe-3 text-start font-normal">
                        <FileLink file={item} />
                      </th>
                      <td className="num py-1 pe-3">
                        {t("contracts.documents.size", {
                          size: formatNumber(item.size_bytes, { kind: "count" }),
                        })}
                      </td>
                      <td className="py-1 pe-3">
                        {t(`contracts.documents.principal.${item.created_by_kind}`)}
                      </td>
                      <td className="py-1 pe-3" data-volatile="">
                        {formatTimestamp(item.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {records.length === 0 ? null : (
              <ul
                aria-label={t("contracts.estimates.evidence.records", {
                  version: versionNumber(version),
                })}
                className="flex flex-col gap-1 text-body-sm"
              >
                {records.map((record) => (
                  <li key={record.id} className="flex flex-wrap items-baseline gap-x-2">
                    <span className="font-mono text-mono-sm text-fg-1">{record.judgement_no}</span>
                    <span className="text-fg-1">{record.conclusion}</span>
                    <span className="text-fg-3">{judgementStatusLabel(record.status)}</span>
                    {commands ? (
                      <DiscardRecord
                        record={record}
                        contract={contract}
                        invalidates={ESTIMATE_RECORD_KEYS}
                        testId="SF-03-dialog-discard-record"
                      />
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </section>
        ))}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// "Attest no change" (SCREENS §8.4; POL-042) and the withdrawal of a pending request.

function AttestModal({
  estimate,
  approved,
  periodEnd,
  onClose,
  onSubmitted,
}: {
  readonly estimate: Estimate;
  readonly approved: EstimateVersion;
  /** The end date of the context period: the default effective date. */
  readonly periodEnd: string | null;
  readonly onClose: () => void;
  readonly onSubmitted: (version: EstimateVersion) => void;
}) {
  const queryClient = useQueryClient();
  // The keys of the draft and of its submission: a press repeated after a lost answer sends the
  // command under the key it had (DG-FE-05 rev 1.156).
  const keys = useCommandKeys();
  const [effective, setEffective] = useState(periodEnd === null ? "" : formatDate(periodEnd));
  const [rationale, setRationale] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  // The draft of this modal whose submission is still owed.
  const [draft, setDraft] = useState<EstimateVersion | null>(null);
  const date = dateOf(effective);
  const dateError =
    effective.trim() === ""
      ? t("contracts.estimates.error.effectiveDate")
      : date === null
        ? t("common.form.date.invalid")
        : null;

  const submit = async () => {
    setAttempted(true);
    if (date === null || reasonError(rationale) !== null) {
      return;
    }
    setBusy(true);
    setFailure(null);
    try {
      const body = attestationBody(approved, date, rationale.trim());
      let row = draft;
      if (row === null) {
        const created = await sendCommand<EstimateVersion>(
          keys,
          "POST",
          estimateVersionsPath(estimate.id),
          body,
        );
        if (!created.ok) {
          setFailure(created.problem);
          return;
        }
        row = created.data;
        setDraft(row);
      } else {
        const updated = await sendCommand<EstimateVersion>(
          keys,
          "PATCH",
          estimateVersionPath(row.id),
          body,
        );
        if (!updated.ok) {
          setFailure(updated.problem);
          return;
        }
        row = updated.data;
      }
      const submitted = await sendCommand<EstimateVersion>(
        keys,
        "POST",
        `${estimateVersionPath(row.id)}/submit`,
        { comment: null },
      );
      if (!submitted.ok) {
        setFailure(submitted.problem);
        return;
      }
      onSubmitted(submitted.data);
    } catch {
      setFailure("unreached");
    } finally {
      setBusy(false);
      void Promise.all(
        ESTIMATE_RECORD_KEYS.map((queryKey) => queryClient.invalidateQueries({ queryKey })),
      );
    }
  };

  return (
    <Modal
      open
      variant="form"
      title={t("contracts.estimates.attest.title", { code: estimate.element_code })}
      description={t("contracts.estimates.attest.description", {
        version: versionNumber(approved),
        date: date === null ? t("contracts.estimates.attest.theDate") : formatDate(date),
      })}
      primaryAction={{
        label: t("contracts.estimates.attest.submit"),
        onAction: () => void submit(),
      }}
      submitting={busy}
      onClose={onClose}
      testId="SF-03-dialog-attest"
    >
      <div className="flex flex-col gap-3">
        <FailureNotice failure={failure} />
        <Field
          name="attest-effective-date"
          label={t("contracts.estimates.field.effectiveDate")}
          required
          error={attempted ? dateError : null}
          width="date"
        >
          {(control) => (
            <DateInput
              control={control}
              value={effective}
              onChange={setEffective}
              invalid={attempted && dateError !== null}
            />
          )}
        </Field>
        {/* SCREENS §8.4 (rev 1.66): the reason says what was looked at, not only that the amount is
            unchanged — the factors of the constraint, the drawer's own list. */}
        <ReasonField
          name="attest-rationale"
          label={t("contracts.drawer.rationale")}
          value={rationale}
          onChange={setRationale}
          showError={attempted}
          hint={t("contracts.estimates.attest.rationaleHint")}
        />
      </div>
    </Modal>
  );
}

function WithdrawModal({
  version,
  onClose,
  onWithdrawn,
}: {
  readonly version: EstimateVersion;
  readonly onClose: () => void;
  readonly onWithdrawn: () => void;
}) {
  const queryClient = useQueryClient();
  const keys = useCommandKeys();
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const commentId = useId();
  const withdraw = async () => {
    setBusy(true);
    setFailure(null);
    try {
      const result = await sendCommand<EstimateVersion>(
        keys,
        "POST",
        `${estimateVersionPath(version.id)}/withdraw`,
        { comment: comment.trim() === "" ? null : comment.trim() },
      );
      if (!result.ok) {
        setFailure(result.problem);
        return;
      }
      onWithdrawn();
    } catch {
      setFailure("unreached");
    } finally {
      setBusy(false);
      void Promise.all(
        [...ESTIMATE_RECORD_KEYS, approvalKey(version.approval_request_id ?? "")].map((queryKey) =>
          queryClient.invalidateQueries({ queryKey }),
        ),
      );
    }
  };
  return (
    <Modal
      open
      variant="form"
      title={t("approvals.withdraw.confirm.title")}
      description={t("contracts.estimates.withdraw.description", {
        version: versionNumber(version),
      })}
      primaryAction={{ label: t("approvals.withdraw"), onAction: () => void withdraw() }}
      submitting={busy}
      onClose={onClose}
      testId="SF-03-dialog-withdraw-estimate"
    >
      <div className="flex flex-col gap-3">
        <FailureNotice failure={failure} />
        <label
          htmlFor={commentId}
          className="flex flex-col gap-1 text-body-sm font-medium text-fg-1"
        >
          <span>
            {t("approvals.withdraw.comment")}
            <span className="ms-1 font-normal text-fg-3">{t("common.form.optional")}</span>
          </span>
          <textarea
            id={commentId}
            value={comment}
            rows={3}
            onChange={(event) => setComment(event.target.value)}
            className="w-full rounded-md border border-control bg-surface px-2.5 py-1 text-body font-normal text-fg-1"
          />
        </label>
      </div>
    </Modal>
  );
}

/**
 * SCREENS §8.3 "Discard draft" (rev 1.33; PRD SM-04): `DRAFT` → `VOIDED`. The API refuses a version
 * that is no draft (409, rule `DB-03`); its messages are shown here and the version stays.
 */
function DiscardModal({
  version,
  onClose,
  onDiscarded,
}: {
  readonly version: EstimateVersion;
  readonly onClose: () => void;
  readonly onDiscarded: (version: EstimateVersion) => void;
}) {
  const queryClient = useQueryClient();
  const keys = useCommandKeys();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const discard = async () => {
    setBusy(true);
    setFailure(null);
    try {
      const result = await sendCommand<EstimateVersion>(
        keys,
        "POST",
        `${estimateVersionPath(version.id)}/discard`,
        undefined,
      );
      if (!result.ok) {
        setFailure(result.problem);
        return;
      }
      onDiscarded(result.data);
    } catch {
      setFailure("unreached");
    } finally {
      setBusy(false);
      void Promise.all(
        ESTIMATE_RECORD_KEYS.map((queryKey) => queryClient.invalidateQueries({ queryKey })),
      );
    }
  };
  return (
    <Modal
      open
      variant="confirmation"
      title={t("contracts.estimates.discard.title")}
      description={t("contracts.estimates.discard.description")}
      primaryAction={{
        label: t("contracts.estimates.banner.discard"),
        destructive: true,
        onAction: () => void discard(),
      }}
      submitting={busy}
      onClose={onClose}
      testId="SF-03-dialog-discard-estimate"
    >
      <FailureNotice failure={failure} />
    </Modal>
  );
}

// ---------------------------------------------------------------------------------------------------
// The pane.

export interface EstimatePaneProps {
  readonly contract: Contract;
  readonly estimate: Estimate;
  /** The session prepares estimates here: `estimate.create` on a view that is not `known_at`. */
  readonly canPrepare: boolean;
  readonly canJudge: boolean;
  readonly viewerId: string | null;
  /** The open `VC_REASSESSMENT_MISSING` item that names the element, with its period end. */
  readonly due: ExceptionItem | null;
  readonly duePeriodEnd: string | null;
  readonly contextPeriod: string | null;
  readonly contextPeriodEnd: string | null;
  readonly periodLabel: PeriodLabel;
  readonly tab: EstimatePaneTab;
  readonly onTabChange: (tab: EstimatePaneTab) => void;
  /** The element was just added: the drawer opens for its first version. */
  readonly startVersion: boolean;
  readonly onVersionStarted: () => void;
  /** The SCREENS §0.5 context parameters a record link keeps. */
  readonly ctxSearch: string;
  /** The view takes commands: it is not one of an earlier known_at. */
  readonly commands: boolean;
}

type Dialog =
  | { readonly kind: "version"; readonly mode: VersionDrawerMode }
  | { readonly kind: "attest" }
  | { readonly kind: "withdraw" }
  | { readonly kind: "discard" };

export function EstimatePane({
  contract,
  estimate,
  canPrepare,
  canJudge,
  viewerId,
  due,
  duePeriodEnd,
  contextPeriod,
  contextPeriodEnd,
  periodLabel,
  tab,
  onTabChange,
  startVersion,
  onVersionStarted,
  ctxSearch,
  commands,
}: EstimatePaneProps) {
  const toast = useToast();
  const queryClient = useQueryClient();
  // The key of the banner's submission (DG-FE-05 rev 1.156).
  const keys = useCommandKeys();
  const pane = useRef<HTMLDivElement>(null);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const kind = estimate.estimate_kind;
  const variable = kind === "VARIABLE_CONSIDERATION";

  const versions = useQuery({
    queryKey: estimateVersionsKey(estimate.id),
    queryFn: () => fetchEstimateVersions(estimate.id),
  });
  const rows = versions.data ?? [];
  const { current, latest } = currentAndLatest(rows);
  // The open version of the element, whichever its number (04 §16.14 rev 1.241, PRD ERR-93): it takes
  // the banner and holds a new version back. A rejected or withdrawn latest version has its banner,
  // with "Edit draft", only while no version is open: its edit would be refused beside an open one.
  const { draft, pending } = openVersions(rows);
  const returned =
    draft === null &&
    pending === null &&
    latest !== null &&
    (latest.status === "REJECTED" || latest.status === "WITHDRAWN")
      ? latest
      : null;
  // The request of a pending version, and the last request of a withdrawn one: a request the API
  // voided comes back as WITHDRAWN too (04 E-12), and the request says which it was.
  const requested = pending ?? (returned?.status === "WITHDRAWN" ? returned : null);
  const requestId = requested?.approval_request_id ?? null;
  const approval = useQuery({
    queryKey: versionRequestKey(requestId ?? "", requested?.status ?? ""),
    queryFn: () => fetchVersionRequest(requestId ?? ""),
    enabled: requestId !== null,
    retry: false,
  });
  const requestRead = requestId === null || !approval.isPending;
  // Only the preparer of the request may withdraw it (PRD SM-01).
  const isPreparer = viewerId !== null && approval.data?.preparer.id === viewerId;
  // REQ-PLT-014: the subject changed after the submission and the API voided the request.
  const staleRequest =
    approval.data?.status === "VOIDED" && approval.data.void_reason === "STALE_SUBJECT";
  // A draft that carries the attestation flag — "Attest no change" stored it and its submission
  // failed — owes neither a file nor a record: the API asks an attestation for its reason alone and
  // refuses the flag itself where the values differ (04 §16.14 rev 1.241; PRD IMP-139, IMP-141).
  const attests = draft !== null && isAttestation(draft);
  const needsEvidence = draft !== null && EVIDENCE_REQUIRED.has(kind) && !attests;
  // PRD ERR-94, its second refusal (SCREENS §8.3, rev 1.66): the approval of a pending version is
  // refused once its evidence is no longer attached — the uploader may void the attachment of a
  // submitted version. The banner reads the open version's live attachments, the read "Evidence"
  // makes, and says so; the preparer learnt it from the approver before.
  const pendingNeedsEvidence =
    draft === null && pending !== null && EVIDENCE_REQUIRED.has(kind) && !isAttestation(pending);
  const evidenceOf = needsEvidence ? draft : pendingNeedsEvidence ? pending : null;
  const openEvidence = useQuery({
    queryKey: versionAttachmentsKey(evidenceOf?.id ?? ""),
    queryFn: () => fetchVersionAttachments(evidenceOf?.id ?? ""),
    enabled: evidenceOf !== null,
  });
  // The CONSTRAINT record of the open version of a variable consideration (PRD IMP-140, ERR-94): a
  // draft is submitted once it names one that is sent for review or reviewed, and a pending version
  // is approved once its record is reviewed.
  const needsRecord =
    variable && ((draft !== null && !attests) || (draft === null && pending !== null));
  const recordId = needsRecord ? ((draft ?? pending)?.judgement_record_id ?? null) : null;
  const openRecord = useQuery({
    queryKey: judgementKey(recordId ?? ""),
    queryFn: () => fetchJudgement(recordId ?? ""),
    enabled: recordId !== null,
    retry: false,
  });
  // The banner states what it offers once it has read what decides it: the request of a pending or
  // withdrawn version, the evidence of an open version that needs some, the record it names.
  const bannerRead =
    requestRead &&
    (evidenceOf === null || !openEvidence.isPending) &&
    (recordId === null || !openRecord.isPending);

  const newVersion = () =>
    setDialog({ kind: "version", mode: { kind: "new", source: current ?? latest } });
  // A new version starts while no version is a draft or waits for approval.
  const canStart = canPrepare && versions.isSuccess && draft === null && pending === null;

  // The element was just added: its first version is written next (SCREENS §8.4).
  useEffect(() => {
    if (startVersion && versions.isSuccess) {
      onVersionStarted();
      if (canPrepare && rows.length === 0) {
        setDialog({ kind: "version", mode: { kind: "new", source: null } });
      }
    }
    // The drawer opens once, when the versions of the new element have been read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startVersion, versions.isSuccess]);

  // SCREENS §8.8: `N` opens "New estimate version" while focus is in the pane and not in a field.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        (event.key !== "n" && event.key !== "N") ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        event.defaultPrevented ||
        isTypingTarget(event.target) ||
        document.querySelector("[aria-modal='true']") !== null ||
        !(event.target instanceof Node) ||
        pane.current?.contains(event.target) !== true ||
        !canStart
      ) {
        return;
      }
      event.preventDefault();
      setDialog({ kind: "version", mode: { kind: "new", source: current ?? latest } });
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [canStart, current, latest]);

  const refresh = () =>
    Promise.all(
      ESTIMATE_RECORD_KEYS.map((queryKey) => queryClient.invalidateQueries({ queryKey })),
    );
  const announceSubmitted = async (version: EstimateVersion) => {
    setDialog(null);
    await refresh();
    if (version.status === "APPROVED") {
      toast.show({
        tone: "positive",
        message: t("contracts.estimates.version.approved", { version: versionNumber(version) }),
      });
      return;
    }
    const request =
      version.approval_request_id === null
        ? null
        : await requestNumber(version.approval_request_id);
    toast.show({
      tone: "positive",
      message:
        request === null
          ? t("contracts.estimates.version.submitted", { version: versionNumber(version) })
          : t("contracts.drawer.submittedForApproval", { request }),
    });
  };
  const submitDraft = async (version: EstimateVersion) => {
    setSubmitting(true);
    setFailure(null);
    try {
      const result = await sendCommand<EstimateVersion>(
        keys,
        "POST",
        `${estimateVersionPath(version.id)}/submit`,
        { comment: null },
      );
      if (!result.ok) {
        setFailure(result.problem);
        return;
      }
      await announceSubmitted(result.data);
    } catch {
      setFailure("unreached");
    } finally {
      setSubmitting(false);
      void refresh();
    }
  };

  if (versions.isPending) {
    return (
      <div className="flex flex-col gap-3 p-[var(--panel-pad)]" aria-busy="true">
        <Skeleton region={t("contracts.estimates.region")} shape="text" count={2} />
        <Skeleton region={t("contracts.estimates.region")} shape="kpi" count={3} />
        <Skeleton region={t("contracts.estimates.region")} shape="rows" count={4} />
      </div>
    );
  }
  if (versions.isError) {
    return (
      <div className="p-[var(--panel-pad)]">
        <Banner
          tone="negative"
          title={t("contracts.estimates.versions.loadError")}
          actions={
            <Button variant="link" onClick={() => void versions.refetch()}>
              {t("common.grid.retry")}
            </Button>
          }
        />
      </div>
    );
  }

  const openReason =
    draft !== null
      ? t("contracts.estimates.blocked.draft", { version: versionNumber(draft) })
      : pending !== null
        ? t("contracts.estimates.blocked.pending", { version: versionNumber(pending) })
        : undefined;
  const overflow: MenuItem[] = [
    {
      id: "compare",
      label: t("contracts.history.compare.action"),
      disabledReason: rows.length < 2 ? t("contracts.estimates.compare.needsTwo") : undefined,
      onSelect: () => onTabChange("versions"),
    },
    {
      id: "copy-link",
      label: t("contracts.list.row.copyLink"),
      onSelect: () => {
        void navigator.clipboard
          .writeText(globalThis.location.href)
          .then(() => toast.show({ tone: "neutral", message: t("contracts.list.row.copied") }));
      },
    },
  ];
  const actions = (
    <>
      {canPrepare && variable ? (
        <Button
          variant="secondary"
          size="sm"
          disabledReason={
            current === null ? t("contracts.estimates.attest.needsApproved") : openReason
          }
          onClick={() => setDialog({ kind: "attest" })}
        >
          {t("contracts.estimates.attest")}
        </Button>
      ) : null}
      {canPrepare ? (
        <Button variant="primary" size="sm" disabledReason={openReason} onClick={newVersion}>
          {t("contracts.estimates.new")}
        </Button>
      ) : null}
      <Menu
        label={t("contracts.estimates.more", { code: estimate.element_code })}
        icon={DotsThree}
        iconOnly
        variant="ghost"
        size="sm"
        align="end"
        items={overflow}
      />
    </>
  );

  const figures = latest === null ? [] : figuresOf(kind, latest);
  const kpis: Kpi[] = figures.map((figure) =>
    figure.type === "money" && latest?.currency != null
      ? {
          id: figure.id,
          label: t(figure.label),
          value: figure.value,
          currency: latest.currency,
          testId: `SF-03-kpi-estimate-${figure.id.replaceAll("_", "-")}`,
        }
      : {
          id: figure.id,
          label: t(figure.label),
          value: figureBlank(figure) ? null : figureText(figure, latest?.currency ?? null),
          currency: latest?.currency ?? contract.transaction_currency,
          kind: "figure",
          testId: `SF-03-kpi-estimate-${figure.id.replaceAll("_", "-")}`,
        },
  );

  const requestLink = (id: string | null) =>
    id === null ? null : (
      <Link
        to={`${requestRoute(id)}${ctxSearch}`}
        className="text-body-sm text-accent-fg hover:underline"
      >
        {t("contracts.workbench.banner.viewRequest")}
      </Link>
    );
  const editAction = (version: EstimateVersion) => (
    <Button
      variant="link"
      onClick={() => setDialog({ kind: "version", mode: { kind: "edit", version } })}
    >
      {t("contracts.estimates.banner.edit")}
    </Button>
  );
  const banners: ReactNode[] = [];
  if (!bannerRead) {
    banners.push(
      <Skeleton
        key="reading"
        region={t("contracts.estimates.banner.reading")}
        shape="text"
        count={1}
      />,
    );
  } else if (draft !== null) {
    const evidenceMissing =
      needsEvidence && openEvidence.isSuccess && openEvidence.data.length === 0;
    // A record whose read failed is left to the API: only a record known not to stand, or none,
    // holds the submission back here.
    const conclusionMissing =
      needsRecord &&
      (recordId === null || (openRecord.isSuccess && !recordStands(openRecord.data.status)));
    banners.push(
      <Banner
        key="draft"
        tone="info"
        announce="static"
        headingLevel={3}
        title={t("contracts.estimates.banner.draft", { version: versionNumber(draft) })}
        actions={
          canPrepare ? (
            <>
              {editAction(draft)}
              <Button
                variant="link"
                loading={submitting}
                disabledReason={
                  evidenceMissing
                    ? t("contracts.estimates.banner.evidenceFirst")
                    : conclusionMissing
                      ? t("contracts.estimates.banner.conclusionFirst")
                      : undefined
                }
                onClick={() => void submitDraft(draft)}
              >
                {t("contracts.drawer.submitForApproval")}
              </Button>
              <Button variant="link" onClick={() => setDialog({ kind: "discard" })}>
                {t("contracts.estimates.banner.discard")}
              </Button>
            </>
          ) : undefined
        }
      />,
    );
  } else if (returned !== null) {
    // SCREENS §15.4 names a request the API voided "Stale"; the pane says so in the same words.
    const outcome =
      returned.status === "REJECTED" ? "rejected" : staleRequest ? "stale" : "withdrawn";
    banners.push(
      <Banner
        key="returned"
        tone={outcome === "stale" ? "warning" : "info"}
        announce="static"
        headingLevel={3}
        title={t(`contracts.estimates.banner.${outcome}`, { version: versionNumber(returned) })}
        actions={
          <>
            {requestLink(returned.approval_request_id)}
            {canPrepare ? editAction(returned) : null}
          </>
        }
      />,
    );
  } else if (pending !== null) {
    // PRD ERR-94: the version is approved once its CONSTRAINT record is reviewed. While the record
    // waits the banner says so in the words of J-07.3; a record that will not be reviewed as it
    // stands — rejected, discarded — is named with its status and the way out. The approval is
    // refused in the same way once the evidence is no longer attached: that sentence stands first,
    // in the order of the draft's banner. A read that failed is left to the API.
    const waiting = openRecord.data ?? null;
    const evidenceGone =
      pendingNeedsEvidence && openEvidence.isSuccess && openEvidence.data.length === 0;
    banners.push(
      <Banner
        key="pending"
        tone="info"
        announce="static"
        headingLevel={3}
        title={t("contracts.estimates.banner.pending", { version: versionNumber(pending) })}
        actions={
          <>
            {requestLink(requestId)}
            {canPrepare && isPreparer ? (
              <Button variant="link" onClick={() => setDialog({ kind: "withdraw" })}>
                {t("approvals.withdraw")}
              </Button>
            ) : null}
          </>
        }
      >
        {evidenceGone ? <p>{t("contracts.estimates.banner.evidenceGone")}</p> : null}
        {waiting === null || waiting.status === "REVIEWED" ? null : (
          <p>
            {waiting.status === "SUBMITTED"
              ? t("contracts.estimates.banner.recordWaits", { number: waiting.judgement_no })
              : t("contracts.estimates.banner.recordNotReviewed", {
                  number: waiting.judgement_no,
                  status: judgementStatusLabel(waiting.status),
                })}
          </p>
        )}
      </Banner>,
    );
  }
  if (due !== null) {
    banners.push(
      <Banner
        key="due"
        tone="warning"
        announce="static"
        headingLevel={3}
        title={
          duePeriodEnd === null
            ? t("contracts.estimates.banner.due")
            : t("contracts.estimates.banner.dueAt", { date: formatDate(duePeriodEnd) })
        }
        actions={
          canPrepare ? (
            <>
              {variable ? (
                <Button
                  variant="link"
                  disabledReason={
                    current === null ? t("contracts.estimates.attest.needsApproved") : openReason
                  }
                  onClick={() => setDialog({ kind: "attest" })}
                >
                  {t("contracts.estimates.attest")}
                </Button>
              ) : null}
              <Button variant="link" disabledReason={openReason} onClick={newVersion}>
                {t("contracts.estimates.new")}
              </Button>
            </>
          ) : undefined
        }
      />,
    );
  }

  const tabs = ESTIMATE_PANES.map((id) => ({
    id,
    label: t(`contracts.estimates.tabs.${id}`),
    count: id === "versions" ? rows.length : undefined,
  }));
  let panel: ReactNode;
  if (tab === "versions") {
    panel =
      rows.length === 0 ? (
        <p className="text-body-sm text-fg-2">{t("contracts.estimates.versions.none")}</p>
      ) : (
        <VersionsPanel estimate={estimate} versions={rows} />
      );
  } else if (tab === "evidence") {
    panel =
      rows.length === 0 ? (
        <p className="text-body-sm text-fg-2">{t("contracts.estimates.evidence.none")}</p>
      ) : (
        <EvidencePanel contract={contract} versions={rows} commands={commands} />
      );
  } else if (current !== null) {
    panel = <VersionDetails estimate={estimate} version={current} ctxSearch={ctxSearch} />;
  } else if (latest !== null) {
    // No version is approved yet: the latest version is shown under its status.
    panel = (
      <div className="flex flex-col gap-2">
        <p className="text-body-sm text-fg-2">{t("contracts.estimates.current.noneApproved")}</p>
        <VersionDetails estimate={estimate} version={latest} ctxSearch={ctxSearch} />
      </div>
    );
  } else {
    panel = <p className="text-body-sm text-fg-2">{t("contracts.estimates.versions.none")}</p>;
  }

  return (
    <div ref={pane} className="flex flex-col">
      <RecordHeader
        variant="compact"
        title={estimate.element_code}
        chips={
          <>
            <span className="text-body-sm text-fg-2">{kindLabel(kind)}</span>
            <MethodChip
              method={estimate.method}
              locked={methodLocked(estimate)}
              testId="SF-03-chip-method"
            />
            <span className="text-body-sm text-fg-2">{targetLabel(estimate)}</span>
            {due === null ? null : (
              <ToneChip
                tone="warning"
                icon={WarningCircle}
                label={t("contracts.estimates.reassessmentDue")}
              />
            )}
          </>
        }
        actions={actions}
        banner={
          banners.length === 0 && failure === null ? undefined : (
            <div data-testid="SF-03-banner-estimate" className="flex flex-col gap-2">
              {banners}
              <FailureNotice failure={failure} />
            </div>
          )
        }
        kpis={
          latest === null ? undefined : (
            <KpiStrip
              compact
              headingLevel={3}
              heading={t("contracts.estimates.figures.heading", {
                version: versionNumber(latest),
                currency: latest.currency ?? contract.transaction_currency,
              })}
              kpis={kpis}
              testId="SF-03-kpi-strip-estimate"
            />
          )
        }
      />
      <div className="p-[var(--panel-pad)]">
        <PanelTabs
          label={t("contracts.estimates.tabs.label")}
          tabs={tabs}
          selectedId={tab}
          onChange={(id) => {
            if (isEstimatePane(id)) {
              onTabChange(id);
            }
          }}
        >
          {panel}
        </PanelTabs>
      </div>
      {dialog?.kind === "version" ? (
        <VersionDrawer
          contract={contract}
          estimate={estimate}
          mode={dialog.mode}
          canJudge={canJudge}
          contextPeriod={contextPeriod}
          periodLabel={periodLabel}
          onClose={() => setDialog(null)}
          onSubmitted={(version) => void announceSubmitted(version)}
        />
      ) : null}
      {dialog?.kind === "attest" && current !== null ? (
        <AttestModal
          estimate={estimate}
          approved={current}
          periodEnd={contextPeriodEnd}
          onClose={() => setDialog(null)}
          onSubmitted={(version) => void announceSubmitted(version)}
        />
      ) : null}
      {dialog?.kind === "withdraw" && pending !== null ? (
        <WithdrawModal
          version={pending}
          onClose={() => setDialog(null)}
          onWithdrawn={() => {
            setDialog(null);
            toast.show({ tone: "positive", message: t("contracts.workbench.banner.withdrawn") });
          }}
        />
      ) : null}
      {dialog?.kind === "discard" && draft !== null ? (
        <DiscardModal
          version={draft}
          onClose={() => setDialog(null)}
          onDiscarded={(version) => {
            setDialog(null);
            toast.show({
              tone: "positive",
              message: t("contracts.estimates.version.discarded", {
                version: versionNumber(version),
              }),
            });
          }}
        />
      ) : null}
    </div>
  );
}
