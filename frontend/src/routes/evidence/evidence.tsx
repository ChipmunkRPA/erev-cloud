import { useMemo } from "react";
import { Link, useLocation } from "react-router";
import { DataGrid } from "../../components/data-grid/DataGrid";
import type { GridColumn, GridSource } from "../../components/data-grid/types";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import { parseFilters, type FilterField } from "../../components/filter-bar/filters";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { Button } from "../../components/ui/Button";
import { CopySimple } from "../../components/icons/registry";
import { NoValue } from "../../components/money/Num";
import { announce } from "../../lib/a11y/announce";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { useMe } from "../../lib/api/queries/me";
import {
  evidencePackRoute,
  evidencePacksKey,
  fetchEvidencePacksPage,
  mayReadEvidence,
  type EvidencePackSummary,
} from "../../lib/api/queries/evidence-packs";
import { formatTimestamp } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { GenerateClosePack } from "./generate";
import { AuditorRequests } from "./requests";
import { ReportsHeader } from "../reports/frame";
import { bookLabel, hashPrefix } from "../reports/viewer/RunStamp";

export function EvidenceAccessLimited() {
  return (
    <EmptyState
      title={t("evidence.packs.access")}
      description={t("evidence.packs.accessDescription")}
    />
  );
}

function ManifestHash({ sha }: { readonly sha: string | null }) {
  if (sha === null) return <NoValue />;
  return (
    <span className="inline-flex items-center gap-1">
      <span aria-hidden="true" className="font-mono text-mono-sm">
        {hashPrefix(sha)}
      </span>
      <span className="sr-only">{sha}</span>
      <Button
        variant="ghost"
        size="sm"
        icon={CopySimple}
        tabIndex={-1}
        aria-label={t("reports.stamp.copySha")}
        onClick={() => {
          void navigator.clipboard
            .writeText(sha)
            .then(() => announce(t("reports.stamp.copied"), "polite"))
            .catch(() => announce(t("evidence.packs.copyFailed"), "polite"));
        }}
      />
    </span>
  );
}

function PackRegister() {
  const { search } = useLocation();
  const fields: readonly FilterField[] = [
    {
      name: "status",
      label: t("evidence.packs.status"),
      kind: "enum",
      operators: ["is", "in"],
      options: ["QUEUED", "RUNNING", "SUCCEEDED", "FAILED"].map((value) => ({
        value,
        label: chipFor("E-67", value)?.status ?? value,
      })),
    },
  ];
  const filters = parseFilters(search, fields).filters;
  const params = new URLSearchParams(search);
  const query = {
    entities: params.getAll("entity"),
    book: params.get("book"),
    period: params.get("period"),
    statuses: filters.find((f) => f.field === "status")?.values ?? [],
  };
  const source: GridSource<EvidencePackSummary> = {
    queryKey: evidencePacksKey(query),
    fetchPage: (cursor, sort) => fetchEvidencePacksPage(query, cursor, sort),
  };
  const columns = useMemo<readonly GridColumn<EvidencePackSummary>[]>(
    () => [
      {
        id: "pack_no",
        header: t("evidence.packs.pack"),
        kind: "text",
        value: (p) => p.pack_no,
        render: (p) => (
          <Link
            className="inline-flex min-h-6 items-center underline"
            to={evidencePackRoute(p.id, p)}
          >
            {p.pack_no}
          </Link>
        ),
      },
      {
        id: "kind",
        header: t("evidence.packs.kind"),
        kind: "text",
        value: () => t("evidence.packs.close"),
      },
      {
        id: "entity",
        header: t("evidence.packs.entity"),
        kind: "text",
        value: (p) => p.entity_code,
      },
      {
        id: "book",
        header: t("evidence.packs.book"),
        kind: "text",
        value: (p) => bookLabel(p.book),
      },
      {
        id: "period",
        header: t("evidence.packs.period"),
        kind: "text",
        value: (p) => p.period_key,
      },
      {
        id: "status",
        header: t("evidence.packs.status"),
        kind: "text",
        value: (p) => p.status,
        render: (p) => {
          const chip = chipFor("E-67", p.status);
          return chip === null ? null : <StatusChip status={chip.status} caption={chip.caption} />;
        },
      },
      {
        id: "file_count",
        header: t("evidence.packs.files"),
        kind: "number",
        value: (p) => (p.file_count === null ? null : String(p.file_count)),
      },
      {
        id: "manifest_sha256",
        header: t("evidence.packs.manifest"),
        kind: "text",
        value: (p) => p.manifest_sha256,
        render: (p) => <ManifestHash sha={p.manifest_sha256} />,
        width: 200,
      },
      {
        id: "created_at",
        header: t("evidence.packs.created"),
        kind: "timestamp",
        value: (p) => p.created_at,
        render: (p) => <time dateTime={p.created_at}>{formatTimestamp(p.created_at)}</time>,
        width: 192,
      },
    ],
    [],
  );
  return (
    <>
      <Banner tone="info" title={t("evidence.packs.scope")}>
        <p>{t("evidence.packs.scopeDescription")}</p>
      </Banner>
      <DataGrid<EvidencePackSummary>
        filterBar={<FilterBar fields={fields} testId="SF-09-filter-bar" />}
        name="evidence-packs"
        title={t("evidence.packs.title")}
        errorTitle={t("evidence.packs.loadError")}
        columns={columns}
        source={source}
        countLabel={(count, formatted) => t("evidence.packs.count", { count, formatted })}
        rowKey={(p) => p.id}
        rowLabel={(p) => p.pack_no}
        rowHref={(p) => evidencePackRoute(p.id, p)}
        testIdPrefix="SF-09"
        rowTestKey={(p) => p.pack_no}
        emptyState={
          <EmptyState
            title={t("evidence.packs.empty")}
            description={t("evidence.packs.emptyDescription")}
          />
        }
      />
    </>
  );
}

export function EvidencePacksPage() {
  const me = useMe();
  const access = useAccess();
  return (
    <div data-testid="SF-09-page" className="flex h-full min-h-0 flex-col">
      <ReportsHeader />
      <div className="flex min-h-0 flex-1 flex-col gap-4 px-[var(--gutter)] py-[var(--panel-pad)]">
        {me.isError ? (
          <Banner tone="negative" title={me.error.message} />
        ) : me.data === undefined ? (
          <Skeleton region={t("evidence.packs.title")} shape="rows" count={6} />
        ) : !mayReadEvidence(access) ? (
          <EvidenceAccessLimited />
        ) : (
          <>
            <div className="flex justify-end">
              <GenerateClosePack />
            </div>
            <AuditorRequests />
            <PackRegister />
          </>
        )}
      </div>
    </div>
  );
}
