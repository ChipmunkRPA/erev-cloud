// SF-10:detail import row drawer (SCREENS §12.3, §6.6; SCR-URL-32 `row`, `sheet`; §0.8 E-41; DESIGN_SYSTEM
// DS-CMP-09, DS-CMP-19, DS-FMT-23; 04 API-R-43 `GET /imports/{id}/rows?row_number&sheet_name`,
// API-S-ImportRow; API-R-09 `GET /approvals/{id}`; BUILD_SPEC DIN-16). The standard drawer "Row <n>"
// lists the file, sheet, row number, status and business key; the table "Cell values" with the raw and
// normalised value of each column; the findings, the created records (lineage), the uploader and the
// approver. [J] L6-4-Q-16: the lineage names a target type and id only, so a record links where its
// route is built from that id alone (a contract); other targets show their label and id.
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { Drawer } from "../../components/ui/Drawer";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import messages from "../../messages/en.json";
import { approvalKey, fetchApproval } from "../../lib/api/queries/approvals";
import { fetchImportRow, type ImportItem, type ImportRow } from "../../lib/api/queries/imports";
import { queryKey } from "../../lib/api/query-keys";
import { formatNumber, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { digestText } from "./imports";

const CATALOGUE: Readonly<Record<string, string>> = messages;

/** The label of a lineage `target_type` ("Contract event"); an unknown type shows as is. */
export function targetLabel(targetType: string): string {
  const key = `data.imports.target.${targetType}`;
  return CATALOGUE[key] === undefined ? targetType : t(key);
}

/** The route of a created record, where one is built from its id alone. */
export function targetRoute(targetType: string, targetId: string): string | null {
  return targetType === "contract" ? `/contracts/${targetId}` : null;
}

/** CPY-06: a message with its code in parentheses, unless the message already ends with it. */
export function messageText(message: { readonly message: string; readonly rule_id: string }) {
  const suffix = `(${message.rule_id})`;
  return message.message.endsWith(suffix) ? message.message : `${message.message} ${suffix}`;
}

/** A cell value of `raw` or `normalized` as text. */
export function cellText(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return NO_VALUE;
  }
  return typeof value === "string" ? value : JSON.stringify(value);
}

function Definition({ term, children }: { readonly term: string; readonly children: ReactNode }) {
  return (
    <>
      <dt className="text-fg-3">{term}</dt>
      <dd className="min-w-0 break-words text-fg-1">{children}</dd>
    </>
  );
}

/** "Approved by": the approvers of the import's request. */
function ApprovedBy({ requestId }: { readonly requestId: string | null }) {
  const approval = useQuery({
    queryKey: approvalKey(requestId ?? ""),
    queryFn: () => fetchApproval(requestId ?? ""),
    enabled: requestId !== null,
    retry: false,
  });
  if (requestId === null || approval.isError) {
    return NO_VALUE;
  }
  if (approval.data === undefined) {
    return <span className="text-fg-3">{t("data.imports.row.loading")}</span>;
  }
  const names = approval.data.steps.flatMap((step) =>
    step.decisions
      .filter((decision) => decision.decision !== "REJECT")
      .map((decision) => decision.approver.display_name),
  );
  return names.length === 0 ? NO_VALUE : names.join(", ");
}

export interface ImportRowDrawerProps {
  readonly item: ImportItem;
  readonly rowNumber: number;
  readonly sheetName: string | null;
  /** CSV files carry no sheet: "Sheet" reads "—". */
  readonly csv: boolean;
  readonly onClose: () => void;
}

export function ImportRowDrawer({
  item,
  rowNumber,
  sheetName,
  csv,
  onClose,
}: ImportRowDrawerProps) {
  const row = useQuery({
    queryKey: queryKey("imports", "tenant", {
      id: item.id,
      row: rowNumber,
      sheet: sheetName,
    }),
    queryFn: () => fetchImportRow(item.id, rowNumber, sheetName),
    retry: false,
  });
  const title = t("data.imports.row.title", { row: formatNumber(rowNumber) });
  let body: ReactNode;
  if (row.isError) {
    body = (
      <Banner tone="negative" title={t("data.imports.row.loadError")}>
        {row.error.message}
      </Banner>
    );
  } else if (row.data === undefined) {
    body = <Skeleton region={title} shape="text" count={6} />;
  } else if (row.data === null) {
    body = <p className="text-body-sm text-fg-2">{t("data.imports.row.notFound")}</p>;
  } else {
    body = <RowDetails item={item} row={row.data} csv={csv} />;
  }
  return (
    <Drawer
      open
      wide
      title={title}
      subtitle={item.import_no}
      initialFocus="title"
      onClose={onClose}
    >
      {/* A focusable region, so the drawer body scrolls from the keyboard when the row holds no link
          (axe scrollable-region-focusable). */}
      <div
        data-testid="SF-10-drawer-row"
        role="region"
        aria-label={t("data.imports.row.region", { row: formatNumber(rowNumber) })}
        // WCAG 2.1.1: keyboard users reach and scroll a scrolling region that holds no control, which
        // the plugin's role table does not model (DG-E2E-07 axe scrollable-region-focusable).
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
        tabIndex={0}
        className="focus-inset flex flex-col gap-5 rounded-sm"
      >
        {body}
      </div>
    </Drawer>
  );
}

function RowDetails({
  item,
  row,
  csv,
}: {
  readonly item: ImportItem;
  readonly row: ImportRow;
  readonly csv: boolean;
}) {
  const chip = chipFor("E-41", row.status);
  const columns = Object.keys(row.raw);
  return (
    <>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-body-sm">
        <Definition term={t("data.imports.row.file")}>
          {item.file.original_filename ?? NO_VALUE}
        </Definition>
        <Definition term={t("data.imports.row.sha256")}>
          <span className="font-mono text-mono-sm" title={item.file.sha256}>
            {digestText(item.file.sha256)}
          </span>
        </Definition>
        <Definition term={t("data.imports.row.sheet")}>
          {csv ? NO_VALUE : row.sheet_name}
        </Definition>
        <Definition term={t("data.imports.row.number")}>
          <span className="num">{formatNumber(row.row_number)}</span>
        </Definition>
        <Definition term={t("data.imports.row.status")}>
          {chip === null ? row.status : <StatusChip status={chip.status} />}
        </Definition>
        <Definition term={t("data.imports.row.businessKey")}>
          {row.business_key === null ? (
            NO_VALUE
          ) : (
            <span className="font-mono text-mono-sm">{row.business_key}</span>
          )}
        </Definition>
      </dl>

      <table className="w-full border-collapse text-body-sm">
        <caption className="mb-2 text-start text-title-sm text-fg-1">
          {t("data.imports.row.cells")}
        </caption>
        <thead>
          <tr className="border-b border-default text-fg-2">
            <th scope="col" className="py-1.5 pe-3 text-start font-medium">
              {t("data.imports.row.column")}
            </th>
            <th scope="col" className="py-1.5 pe-3 text-start font-medium">
              {t("data.imports.row.raw")}
            </th>
            <th scope="col" className="py-1.5 text-start font-medium">
              {t("data.imports.row.normalized")}
            </th>
          </tr>
        </thead>
        <tbody>
          {columns.map((column) => (
            <tr key={column} className="border-b border-hairline align-top">
              <th scope="row" className="py-1.5 pe-3 text-start font-normal text-fg-2">
                {column}
              </th>
              <td className="py-1.5 pe-3 font-mono text-mono-sm text-fg-1">
                {cellText(row.raw[column])}
              </td>
              <td className="py-1.5 font-mono text-mono-sm text-fg-1">
                {row.normalized === null ? NO_VALUE : cellText(row.normalized[column])}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <section className="flex flex-col gap-1.5">
        <h3 className="text-title-sm text-fg-1">{t("data.imports.row.findings")}</h3>
        {row.messages.length === 0 ? (
          <p className="text-body-sm text-fg-2">{t("data.imports.row.noFindings")}</p>
        ) : (
          <ul className="flex flex-col gap-1 text-body-sm text-fg-1">
            {row.messages.map((message, index) => (
              <li key={`${message.rule_id}:${String(index)}`}>{messageText(message)}</li>
            ))}
          </ul>
        )}
      </section>

      <section className="flex flex-col gap-1.5">
        <h3 className="text-title-sm text-fg-1">{t("data.imports.row.created")}</h3>
        {row.lineage.length === 0 ? (
          <p className="text-body-sm text-fg-2">{t("data.imports.row.noCreated")}</p>
        ) : (
          <ul className="flex flex-col gap-1 text-body-sm">
            {row.lineage.map((target) => {
              const route = targetRoute(target.target_type, target.target_id);
              const label = t("data.imports.row.target", {
                type: targetLabel(target.target_type),
                id: target.target_id.slice(0, 8),
              });
              return (
                <li key={`${target.target_type}:${target.target_id}`}>
                  {route === null ? (
                    <span className="text-fg-1">{label}</span>
                  ) : (
                    <Link to={route} className="text-accent-fg hover:underline">
                      {label}
                    </Link>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-body-sm">
        <Definition term={t("data.imports.row.uploadedBy")}>
          {item.created_by.display_name}
        </Definition>
        <Definition term={t("data.imports.row.approvedBy")}>
          <ApprovedBy requestId={item.approval_request_id} />
        </Definition>
      </dl>
    </>
  );
}
