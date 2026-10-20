import { useState } from "react";

import { DataGrid } from "../../components/data-grid/DataGrid";
import type { GridColumn } from "../../components/data-grid/types";
import { EmptyState } from "../../components/feedback/EmptyState";
import { queryKey } from "../../lib/api/query-keys";
import {
  fetchMigrationReconciliationLines,
  type Migration,
  type MigrationReconciliationLine,
} from "../../lib/api/queries/migrations";
import { t } from "../../lib/i18n/t";

/** Values retain the API's decimal precision: the migration line has no currency metadata. */
export function MigrationReconciliationLines({ migration }: { readonly migration: Migration }) {
  const [differencesOnly, setDifferencesOnly] = useState(false);
  const label = (key: string) => t(`data.migrations.reconcile.lines.${key}`);
  const numeric = ["source_value", "erev_value", "difference", "tolerance"] as const;
  const columns: readonly GridColumn<MigrationReconciliationLine>[] = [
    {
      id: "contract",
      header: label("contract"),
      kind: "identifier",
      value: (row) => row.contract_external_id,
    },
    {
      id: "obligation",
      header: label("obligation"),
      kind: "text",
      value: (row) => row.obligation_key,
    },
    {
      id: "measure",
      header: label("measure"),
      kind: "text",
      value: (row) => label(`measure.${row.measure}`),
    },
    ...numeric.map((field): GridColumn<MigrationReconciliationLine> => ({
      id: field,
      header: label(field),
      kind: "number",
      value: (row) => row[field],
      render: (row) => <span className="font-mono tabular-nums">{row[field]}</span>,
    })),
    {
      id: "within_tolerance",
      header: label("withinTolerance"),
      kind: "boolean",
      value: (row) => String(row.is_within_tolerance),
    },
    {
      id: "deviation",
      header: label("deviation"),
      kind: "text",
      value: (row) => row.deviation_ref ?? null,
    },
    {
      id: "exception",
      header: label("exception"),
      kind: "identifier",
      value: (row) => row.exception_no ?? row.exception_item_id ?? null,
    },
  ];
  return (
    <DataGrid<MigrationReconciliationLine>
      name="reconciliation-lines"
      title={label("title")}
      headingLevel={2}
      testIdPrefix="SF-19"
      columns={columns}
      countLabel={(count, formatted) => t("reports.report.section.count", { count, formatted })}
      rowKey={(row) =>
        row.id ?? JSON.stringify([row.contract_external_id, row.obligation_key, row.measure])
      }
      rowLabel={(row) => `${row.contract_external_id} ${row.measure}`}
      source={{
        queryKey: queryKey("migrations", "tenant", {
          id: migration.id,
          view: "reconciliation-lines",
          version: migration.row_version,
          differencesOnly,
        }),
        fetchPage: async () => {
          const all = await fetchMigrationReconciliationLines(migration.id);
          const items = differencesOnly ? all.filter((row) => !row.is_within_tolerance) : all;
          return { items, nextCursor: null, total: { count: items.length, capped: false } };
        },
      }}
      toolbarActions={
        <label className="flex items-center gap-2 text-body-sm">
          <input
            type="checkbox"
            checked={differencesOnly}
            onChange={(event) => setDifferencesOnly(event.target.checked)}
          />
          {label("differencesOnly")}
        </label>
      }
      errorTitle={label("error")}
      emptyState={
        <EmptyState
          title={label(differencesOnly ? "noDifferences" : "empty")}
          description={label(differencesOnly ? "clearFilter" : "noEvidence")}
        />
      }
    />
  );
}
