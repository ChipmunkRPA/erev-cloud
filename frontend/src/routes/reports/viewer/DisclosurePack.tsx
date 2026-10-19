import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Banner } from "../../../components/feedback/Banner";
import { Button } from "../../../components/ui/Button";
import { queryKey } from "../../../lib/api/query-keys";
import { fetchDisclosureSections, fetchReportRows, type DisclosureTable, type ReportRow } from "../../../lib/api/queries/reports";
import { t } from "../../../lib/i18n/t";
import { ReportGrid } from "./ReportGrid";
import { isMoney, type ReportColumn } from "./specs";

function Table({ runId, table, number }: { runId: string; table: DisclosureTable; number: number }) {
  const [open, setOpen] = useState(false);
  const rows = useQuery({
    queryKey: queryKey("report-runs", "tenant", { runId, sectionTable: table.key }),
    queryFn: () => fetchReportRows(runId, table.key),
    enabled: open && !table.omitted,
  });
  const values: ReportRow[] = (rows.data?.rows ?? []).map(row => ({ ...row }));
  const columns: ReportColumn[] = [];
  for (const column of rows.data?.columns ?? []) {
    const currencies = column.kind === "money" ? [...new Set(values.flatMap(row => {
      const value = row[column.key];
      return isMoney(value) ? [value.currency] : [];
    }))] : [];
    columns.push({
      key: column.key,
      header: currencies.length === 1 ? `${column.header} (${currencies[0]})` : column.header,
      drillable: false,
      kind: column.kind === "money" ? "money" : column.kind === "integer" ? "number" : "text",
    });
    if (currencies.length > 1) {
      const key = `${column.key}:currency`;
      columns.push({ key, header: t("reports.disclosure.currency", { column: column.header }), kind: "text", drillable: false });
      for (const row of values) {
        const value = row[column.key];
        row[key] = isMoney(value) ? value.currency : null;
      }
    }
  }
  return <details onToggle={event => setOpen(event.currentTarget.open)} className="rounded border border-stroke-1 p-3">
    <summary className="cursor-pointer text-body-sm font-semibold">
      {table.title} — {t(table.basis === "QUARTER_TO_DATE" ? "reports.disclosure.quarter" : "reports.disclosure.period")} ({table.row_count})
    </summary>
    <p className="break-all text-body-sm text-fg-2">{t("reports.disclosure.source", { source: table.source_run_id ?? t("reports.disclosure.policy") })} · {table.source_sha256}</p>
    {table.notes.map(note => <p key={note} className="text-body-sm text-fg-2">{note}</p>)}
    {table.omitted ? <p>{t("reports.disclosure.omitted")}</p> : rows.isError ? <Banner tone="negative" title={t("reports.report.dataLoadError")} actions={<Button variant="link" onClick={() => void rows.refetch()}>{t("reports.report.retry")}</Button>} /> : rows.data === undefined ? <p role="status">{t("reports.disclosure.loading")}</p> : <ReportGrid
      runId={runId} name={table.key} title={table.title}
      section={{ number, heading: table.title, rows: values, totals: [] }}
      columns={columns} totals={[]} onDrill={() => undefined}
      emptyState={<p className="p-4 text-body-sm">{t("reports.disclosure.empty")}</p>}
    />}
  </details>;
}

export function DisclosurePack({ runId }: { runId: string }) {
  const sections = useQuery({
    queryKey: queryKey("report-runs", "tenant", { runId, disclosureSections: true }),
    queryFn: () => fetchDisclosureSections(runId),
  });
  if (sections.isError) return <Banner tone="negative" title={t("reports.report.dataLoadError")} actions={<Button variant="link" onClick={() => void sections.refetch()}>{t("reports.report.retry")}</Button>} />;
  if (sections.data === undefined) return <p role="status">{t("reports.disclosure.loading")}</p>;
  return <div className="flex flex-col gap-6">
    <p className="text-body-sm text-fg-2">{t("reports.disclosure.draft")}</p>
    {sections.data.map(section => <section key={section.number} className="flex flex-col gap-2">
      <h2 className="text-heading-sm">{section.number}. {section.title}</h2>
      {section.interim_required && <p className="text-body-sm text-fg-2">{t("reports.disclosure.interim")}</p>}
      {section.tables.map(table => <Table key={table.key} runId={runId} table={table} number={section.number} />)}
    </section>)}
  </div>;
}
