// The estimate versions created inside a modification (SCREENS §7.4 "Linked items panel", §7.8, §7.9;
// 04 §16.14 rev 1.210 API-S-Modification `linked_estimate_versions`, T-CON-13 `modification_id`; PRD
// BR-MOD-02, ERR-83, ERR-87; BUILD_SPEC CTR-27). The row of the modification lists them by element
// code and version number: element, kind, version and status. The figure of each is the key figure of
// its kind, read from the version itself (`GET /estimate-versions/{id}`).
//
// "Add estimate version" opens the version drawer of SF-03:estimate for one element of the contract
// and sends `modification_id` with its `POST`; it is offered while the modification is a draft. A
// linked version is edited, submitted, withdrawn and discarded on SF-03:estimate, which the element's
// cell links to. The versions are approved before the modification is submitted: `/submit` names each
// that is not (PRD ERR-87), and the modification's discard names one that waits for approval (PRD
// ERR-83). A discarded version stays in the list and reads Void.
import { useQueries, useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Link } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { useToast } from "../../components/feedback/Toast";
import { NoValue } from "../../components/money/Num";
import { Button } from "../../components/ui/Button";
import { Menu } from "../../components/ui/Menu";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { requestRoute } from "../../lib/api/queries/approvals";
import type { Contract } from "../../lib/api/queries/contracts";
import {
  contractEstimatesKey,
  currentAndLatest,
  type Estimate,
  ESTIMATE_ROUTE,
  estimateRoute,
  type EstimateVersion,
  estimateVersionKey,
  estimateVersionsKey,
  fetchEstimates,
  fetchEstimateVersion,
  fetchEstimateVersions,
} from "../../lib/api/queries/estimates";
import type { Modification } from "../../lib/api/queries/modifications";
import { keyFigure } from "../../lib/forms/estimate";
import { formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { useBuiltPaths } from "../settings/index";
import { requestNumber } from "./drawers/common";
import { figureText, kindLabel, type PeriodLabel } from "./estimate-parts";
import { VersionDrawer } from "./estimate-version";
import { REQUEST_ROUTE } from "./obligation-pane";

/** One entry of API-S-Modification `linked_estimate_versions`. */
export type LinkedVersion = NonNullable<Modification["linked_estimate_versions"]>[number];

/** The linked versions of a row; a row answered before the member existed has none. */
export function linkedVersionsOf(row: Modification): readonly LinkedVersion[] {
  return row.linked_estimate_versions ?? [];
}

function versionNumber(version: { readonly version_no: number }): string {
  return formatNumber(version.version_no, { kind: "count" });
}

/** E-12 of a linked version `/submit` waits for (PRD ERR-87): not approved, and not discarded. */
const NOT_APPROVED: ReadonlySet<string> = new Set(["DRAFT", "SUBMITTED", "REJECTED", "WITHDRAWN"]);

/**
 * The sentence of PRD ERR-87 for the first linked version that is not approved, in the order of the
 * list; null when the submission waits for none. `APPROVED` and `SUPERSEDED` pass, and a discarded
 * (`VOIDED`) version is not counted (04 §16.14 rev 1.210). The API's refusal stays the backstop.
 */
export function unapprovedVersionLine(row: Modification): string | null {
  const held = linkedVersionsOf(row).find((item) => NOT_APPROVED.has(item.status));
  return held === undefined
    ? null
    : t("modifications.wizard.submit.versionNotApproved", {
        code: held.element_code,
        version: versionNumber(held),
      });
}

function StatusOf({ status }: { readonly status: string }) {
  const chip = chipFor("E-12", status);
  return chip === null ? <span>{status}</span> : <StatusChip status={chip.status} />;
}

const COLUMNS = ["element", "kind", "version", "figure", "status"] as const;

/**
 * SCREENS §7.4 "Linked estimate versions": Element, Kind, Version, Figure, Status. With `requests`
 * (SF-07:detail "Linked requests") a last column links the request of a version that has one.
 */
export function LinkedVersionsTable({
  contractId,
  versions,
  labelledBy,
  ctxSearch,
  requests = false,
}: {
  readonly contractId: string;
  readonly versions: readonly LinkedVersion[];
  readonly labelledBy: string;
  /** The SCREENS §0.5 context parameters a record link keeps. */
  readonly ctxSearch: string;
  readonly requests?: boolean;
}) {
  const built = useBuiltPaths();
  const reads = useQueries({
    queries: versions.map((item) => ({
      queryKey: estimateVersionKey(item.id),
      queryFn: () => fetchEstimateVersion(item.id),
    })),
  });
  const columns = requests ? [...COLUMNS, "request" as const] : COLUMNS;
  return (
    <table
      aria-labelledby={labelledBy}
      data-testid="SF-07-grid-estimate-versions"
      className="w-full border-collapse text-body-sm"
    >
      <thead>
        <tr className="border-b border-default text-caption text-fg-3">
          {columns.map((column) => (
            <th
              key={column}
              scope="col"
              className={
                column === "version" || column === "figure"
                  ? "px-2 py-1.5 text-end font-medium"
                  : "px-2 py-1.5 text-start font-medium"
              }
            >
              {t(`modifications.wizard.linked.column.${column}`)}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {versions.map((item, index) => {
          const read = reads[index];
          const version = read?.data;
          const requestId = version?.approval_request_id ?? null;
          return (
            <tr key={item.id} className="border-b border-default">
              <th scope="row" className="px-2 py-1.5 text-start font-normal">
                {built.has(ESTIMATE_ROUTE) ? (
                  <Link
                    to={`${estimateRoute(contractId, item.estimate_id)}${ctxSearch}`}
                    className="font-mono text-mono-sm text-fg-1 underline decoration-dotted underline-offset-4 hover:decoration-solid"
                  >
                    {item.element_code}
                  </Link>
                ) : (
                  <span className="font-mono text-mono-sm text-fg-1">{item.element_code}</span>
                )}
              </th>
              <td className="px-2 py-1.5 text-fg-1">{kindLabel(item.estimate_kind)}</td>
              <td className="num px-2 py-1.5 text-end text-fg-1">{versionNumber(item)}</td>
              <td
                className="num px-2 py-1.5 text-end text-fg-1"
                aria-busy={read?.isPending === true || undefined}
              >
                {version !== undefined ? (
                  figureText(keyFigure(item.estimate_kind, version), version.currency)
                ) : read?.isError === true ? (
                  <NoValue />
                ) : null}
              </td>
              <td className="px-2 py-1.5">
                <StatusOf status={item.status} />
              </td>
              {requests ? (
                <td className="px-2 py-1.5">
                  {requestId === null ? (
                    read?.isPending === true ? null : (
                      <NoValue />
                    )
                  ) : built.has(REQUEST_ROUTE) ? (
                    <Link
                      to={`${requestRoute(requestId)}${ctxSearch}`}
                      className="text-body-sm text-accent-fg hover:underline"
                    >
                      {t("contracts.workbench.banner.viewRequest")}
                    </Link>
                  ) : (
                    <NoValue />
                  )}
                </td>
              ) : null}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/** The reason a new version of the element cannot start, as SF-03:estimate states it; else undefined. */
function openReason(element: Estimate): string | undefined {
  const latest = element.latest_version;
  if (latest === null) {
    return undefined;
  }
  if (latest.status === "DRAFT") {
    return t("contracts.estimates.blocked.draft", { version: versionNumber(latest) });
  }
  if (latest.status === "SUBMITTED") {
    return t("contracts.estimates.blocked.pending", { version: versionNumber(latest) });
  }
  return undefined;
}

export interface LinkedEstimateVersionsProps {
  readonly contract: Contract;
  /** The DRAFT modification. */
  readonly row: Modification;
  /** `estimate.create` for the contract's entity: "Add estimate version" renders only for a holder. */
  readonly canAdd: boolean;
  readonly canJudge: boolean;
  readonly contextPeriod: string | null;
  readonly periodLabel: PeriodLabel;
  readonly ctxSearch: string;
}

/** Step 1 of a draft: the linked estimate versions and "Add estimate version" (SCREENS §7.4). */
export function LinkedEstimateVersions({
  contract,
  row,
  canAdd,
  canJudge,
  contextPeriod,
  periodLabel,
  ctxSearch,
}: LinkedEstimateVersionsProps) {
  const toast = useToast();
  const headingId = useId();
  const [adding, setAdding] = useState<Estimate | null>(null);
  const versions = linkedVersionsOf(row);
  const elements = useQuery({
    queryKey: contractEstimatesKey(contract.id),
    queryFn: () => fetchEstimates(contract.id),
    enabled: canAdd,
  });
  // A new version starts from the figures of the approved version, else of the latest one (§8.4).
  const source = useQuery({
    queryKey: estimateVersionsKey(adding?.id ?? ""),
    queryFn: () => fetchEstimateVersions(adding?.id ?? ""),
    enabled: adding !== null,
  });
  const list = elements.data ?? [];
  const [only] = list;
  const label = t("modifications.wizard.linked.addVersion");

  const announceSubmitted = async (version: EstimateVersion) => {
    setAdding(null);
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

  // The reason the one button is unavailable: a contract without an estimated element, or the open
  // version of its one element. A menu states the reason of each element in its item.
  const reason =
    !canAdd || elements.isError || list.length > 1
      ? undefined
      : only === undefined
        ? elements.isSuccess
          ? t("modifications.wizard.linked.noElements")
          : undefined
        : openReason(only);
  let add = null;
  // Without the elements nothing can be said about the command: the failed read shows below instead.
  if (canAdd && !elements.isError) {
    add =
      list.length > 1 ? (
        <Menu
          label={label}
          variant="secondary"
          size="sm"
          align="end"
          items={list.map((element) => ({
            id: element.id,
            // Two values and a separator: no sentence of the catalogue (DS-I18N-01).
            label: `${element.element_code} · ${kindLabel(element.estimate_kind)}`,
            disabledReason: openReason(element),
            onSelect: () => setAdding(element),
          }))}
        />
      ) : (
        <Button
          variant="secondary"
          size="sm"
          loading={elements.isPending || (adding !== null && source.isFetching)}
          disabledReason={reason}
          onClick={() => {
            if (only !== undefined) {
              setAdding(only);
            }
          }}
        >
          {label}
        </Button>
      );
  }

  const { current, latest } = currentAndLatest(source.data ?? []);
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-3">
        <h3 id={headingId} className="text-title-sm text-fg-1">
          {t("modifications.wizard.linked.versions")}
        </h3>
        <span className="flex-1" />
        {add}
      </div>
      {canAdd && elements.isError ? (
        <Banner
          tone="negative"
          headingLevel={4}
          title={t("contracts.estimates.loadError")}
          actions={
            <Button variant="link" onClick={() => void elements.refetch()}>
              {t("common.grid.retry")}
            </Button>
          }
        />
      ) : null}
      {adding !== null && source.isError ? (
        <Banner
          tone="negative"
          headingLevel={4}
          title={t("contracts.estimates.versions.loadError")}
          actions={
            <Button variant="link" onClick={() => void source.refetch()}>
              {t("common.grid.retry")}
            </Button>
          }
        />
      ) : null}
      {versions.length === 0 || reason !== undefined ? (
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          {versions.length === 0 ? (
            <p className="text-body-sm text-fg-2">{t("modifications.wizard.linked.noVersions")}</p>
          ) : null}
          <span className="flex-1" />
          {reason === undefined ? null : (
            // SCREENS §0.6 SCR-PERM-03, DESIGN_SYSTEM DS-CMP-27: the reason of an unavailable
            // command is a visible line; the button's tooltip only repeats it.
            <p data-testid="SF-07-linked-blocked" className="text-body-sm text-fg-2">
              {reason}
            </p>
          )}
        </div>
      ) : null}
      {versions.length === 0 ? null : (
        <LinkedVersionsTable
          contractId={contract.id}
          versions={versions}
          labelledBy={headingId}
          ctxSearch={ctxSearch}
        />
      )}
      {adding !== null && source.isSuccess ? (
        <VersionDrawer
          contract={contract}
          estimate={adding}
          mode={{ kind: "new", source: current ?? latest }}
          canJudge={canJudge}
          contextPeriod={contextPeriod}
          periodLabel={periodLabel}
          modificationId={row.id}
          onClose={() => setAdding(null)}
          onSubmitted={(version) => void announceSubmitted(version)}
        />
      ) : null}
    </section>
  );
}

/** Step 5 and SF-07:detail: the linked versions in one list, "<element> v<n>" with the status chip. */
export function LinkedVersionsSummary({
  versions,
}: {
  readonly versions: readonly LinkedVersion[];
}) {
  if (versions.length === 0) {
    return <>{t("modifications.wizard.linked.noVersions")}</>;
  }
  return (
    <ul className="flex flex-col gap-0.5">
      {versions.map((item) => (
        <li key={item.id} className="flex flex-wrap items-center gap-2">
          <span>
            <span className="font-mono text-mono-sm">{item.element_code}</span>{" "}
            {t("modifications.wizard.linked.versionNo", { version: versionNumber(item) })}
          </span>
          <StatusOf status={item.status} />
        </li>
      ))}
    </ul>
  );
}
