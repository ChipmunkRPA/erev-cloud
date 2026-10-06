// SB-R-07 report cell explain (SCREENS_B §0.3, RV-09; SCREENS §6.1; DESIGN_SYSTEM DS-CMP-15;
// REQ-RPT-017). A report figure opens `GET /explain/report-runs/{id}/cell`, which lists the records
// behind it. A single contributor opens its own explanation in the Explain panel; several are listed
// in this docked panel, and each opens its explanation. Esc closes and returns focus to the originating
// cell (REQ-UX-009). The panel carries `data-testid="SF-08-explain"` (SCREENS §6.7).
import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useRef } from "react";

import { useExplain } from "../../../components/explain/ExplainTrigger";
import { Banner } from "../../../components/feedback/Banner";
import { Skeleton } from "../../../components/feedback/Skeleton";
import { X } from "../../../components/icons/registry";
import { Button } from "../../../components/ui/Button";
import { EXPLAIN_OBJECT_TYPES, measureLabelKey } from "../../../lib/api/queries/explain";
import {
  fetchReportCell,
  type ReportCellContributor,
  reportCellKey,
} from "../../../lib/api/queries/reports";
import { formatMoney } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";

export interface CellRequest {
  readonly runId: string;
  readonly rowKey: string;
  readonly columnKey: string;
  /** The figure name, for example "Sep 2026 (USD) · SF-ORD-10001". */
  readonly label: string;
  /** The originating cell. */
  readonly element: HTMLElement | null;
}

function objectLabel(objectType: string): string {
  return EXPLAIN_OBJECT_TYPES.some((item) => item === objectType)
    ? t(`reports.explain.object.${objectType}`)
    : objectType;
}

function measureLabel(measure: string): string {
  const key = measureLabelKey(measure);
  return key === null ? measure : t(key);
}

function figureOf(contributor: ReportCellContributor) {
  const objectType = EXPLAIN_OBJECT_TYPES.find((item) => item === contributor.object_type);
  return objectType === undefined
    ? null
    : { objectType, id: contributor.id, measure: contributor.measure };
}

export interface CellContributorsProps {
  readonly request: CellRequest;
  /** `restoreFocus` false when an explanation takes over the dock. */
  readonly onClose: (restoreFocus: boolean) => void;
  /** The SF id of the host screen: `<SF id>-explain` (SCREENS §6.7). */
  readonly testIdPrefix?: string | undefined;
}

export function CellContributors({
  request,
  onClose,
  testIdPrefix = "SF-08",
}: CellContributorsProps) {
  const { open } = useExplain();
  const titleId = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const panel = useRef<HTMLElement>(null);
  const cell = useQuery({
    queryKey: reportCellKey(request.runId, request.rowKey, request.columnKey),
    queryFn: () => fetchReportCell(request.runId, request.rowKey, request.columnKey),
  });
  const contributors = cell.data?.contributors.items;

  const openContributor = (contributor: ReportCellContributor) => {
    const figure = figureOf(contributor);
    if (figure === null) {
      return;
    }
    open(
      {
        figure,
        label: `${objectLabel(contributor.object_type)} · ${request.label}`,
      },
      request.element,
    );
    onClose(false);
  };
  const single = contributors?.length === 1 ? contributors[0] : undefined;
  const openSingle = useRef(openContributor);
  useEffect(() => {
    openSingle.current = openContributor;
  });
  useEffect(() => {
    if (single !== undefined && figureOf(single) !== null) {
      openSingle.current(single);
    }
  }, [single]);

  useEffect(() => {
    heading.current?.focus();
  }, []);

  useEffect(() => {
    const element = panel.current;
    if (element === null) {
      return undefined;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented) {
        event.preventDefault();
        onClose(true);
      }
    };
    element.addEventListener("keydown", onKeyDown);
    return () => element.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const value = cell.data?.value;
  return (
    <aside
      ref={panel}
      aria-labelledby={titleId}
      data-explain-panel=""
      data-testid={`${testIdPrefix}-explain`}
      className="flex h-full w-[var(--explain-w)] max-w-full shrink-0 flex-col border-s border-hairline bg-raised"
    >
      <div className="flex items-start gap-2 border-b border-hairline px-[var(--panel-pad)] py-3">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="text-caption text-fg-3">{t("common.explain.eyebrow")}</span>
          <h2 ref={heading} id={titleId} tabIndex={-1} className="text-title-md text-fg-1">
            {request.label}
          </h2>
          {value === undefined ? null : (
            <span className="num text-kpi text-fg-1">
              {formatMoney(value.amount, value.currency, { variant: "kpi" })}
            </span>
          )}
        </div>
        <Button
          variant="ghost"
          size="sm"
          icon={X}
          aria-label={t("common.dialog.close")}
          onClick={() => onClose(true)}
        />
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-[var(--panel-pad)]">
        {cell.isError ? (
          <Banner
            tone="negative"
            headingLevel={3}
            title={t("reports.explain.loadError")}
            actions={
              <Button variant="link" onClick={() => void cell.refetch()}>
                {t("common.explain.retry")}
              </Button>
            }
          />
        ) : contributors === undefined ? (
          <Skeleton
            region={t("reports.explain.contributors", { count: 0 })}
            shape="rows"
            count={3}
          />
        ) : contributors.length === 0 ? (
          <p className="text-body-sm text-fg-2">{t("reports.explain.none")}</p>
        ) : (
          <table className="w-full text-body-sm">
            <caption className="mb-2 text-start text-title-sm text-fg-1">
              {t("reports.explain.contributors", { count: contributors.length })}
            </caption>
            <thead>
              <tr className="text-caption text-fg-3">
                <th scope="col" className="py-1 text-start font-medium">
                  {t("reports.explain.column.record")}
                </th>
                <th scope="col" className="py-1 text-start font-medium">
                  {t("reports.explain.column.measure")}
                </th>
                <th scope="col" className="py-1 text-end font-medium">
                  {t("reports.explain.column.amount")}
                </th>
              </tr>
            </thead>
            <tbody>
              {contributors.map((contributor) => (
                <tr
                  key={`${contributor.object_type}:${contributor.id}`}
                  className="border-t border-hairline"
                >
                  <td className="py-1 pe-2">
                    <Button variant="link" onClick={() => openContributor(contributor)}>
                      {objectLabel(contributor.object_type)}
                    </Button>
                  </td>
                  <td className="py-1 pe-2 text-fg-2">{measureLabel(contributor.measure)}</td>
                  <td className="num py-1 text-end text-fg-1">
                    {formatMoney(contributor.value.amount, contributor.value.currency, {
                      variant: "cell",
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </aside>
  );
}
