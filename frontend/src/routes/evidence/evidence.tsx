import { useMemo } from "react";
import { Link, useLocation, useSearchParams } from "react-router";
import { DataGrid } from "../../components/data-grid/DataGrid";
import type { GridColumn, GridSource } from "../../components/data-grid/types";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import { parseFilters, type FilterField } from "../../components/filter-bar/filters";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
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
  mayCreateSampleEvidence,
  mayCreateRegisterEvidence,
  type EvidencePackSummary,
  type EvidencePackQuery,
} from "../../lib/api/queries/evidence-packs";
import { formatDate, formatTimestamp } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { GenerateClosePack } from "./generate";
import { GenerateRegisterPack } from "./generate-register";
import { GenerateSamplePack } from "./generate-sample";
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
  const [, setSearchParams] = useSearchParams();
  const access = useAccess();
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
  const requestedKind = params.get("kind");
  const kind =
    requestedKind === "CONTRACT_SAMPLE" || requestedKind === "CHANGE" || requestedKind === "ACCESS"
      ? requestedKind
      : "CLOSE";
  const query: EvidencePackQuery = {
    kind,
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
        value: (p) =>
          t(
            p.kind === "CONTRACT_SAMPLE"
              ? "evidence.packs.sample"
              : p.kind === "ACCESS"
                ? "evidence.packs.accessPack"
                : `evidence.packs.${p.kind.toLowerCase()}`,
          ),
      },
      ...(kind === "CLOSE"
        ? [
            {
              id: "entity",
              header: t("evidence.packs.entity"),
              kind: "text" as const,
              value: (p: EvidencePackSummary) => (p.kind === "CLOSE" ? p.entity_code : null),
            },
            {
              id: "book",
              header: t("evidence.packs.book"),
              kind: "text" as const,
              value: (p: EvidencePackSummary) => (p.kind === "CLOSE" ? bookLabel(p.book) : null),
            },
            {
              id: "period",
              header: t("evidence.packs.period"),
              kind: "text" as const,
              value: (p: EvidencePackSummary) => (p.kind === "CLOSE" ? p.period_key : null),
            },
          ]
        : kind !== "CONTRACT_SAMPLE"
          ? [
              {
                id: "entities",
                header: t("evidence.packs.entity"),
                kind: "text" as const,
                value: (p: EvidencePackSummary) =>
                  "entity_codes" in p ? p.entity_codes.join(", ") : null,
              },
              {
                id: "dates",
                header: t("evidence.register.dates"),
                kind: "text" as const,
                value: (p: EvidencePackSummary) =>
                  "from_date" in p ? (p.as_of ?? `${p.from_date} – ${p.to_date}`) : null,
              },
            ]
          : [
              {
                id: "contracts",
                header: t("evidence.packs.sampleContracts"),
                kind: "text" as const,
                value: (p: EvidencePackSummary) =>
                  p.kind === "CONTRACT_SAMPLE" ? p.contract_external_ids.join(", ") : null,
              },
              {
                id: "as_of",
                header: t("evidence.packs.sampleAsOf"),
                kind: "text" as const,
                value: (p: EvidencePackSummary) =>
                  p.kind === "CONTRACT_SAMPLE" ? formatDate(p.as_of) : null,
              },
              {
                id: "known_at",
                header: t("evidence.packs.sampleKnownAt"),
                kind: "text" as const,
                value: (p: EvidencePackSummary) =>
                  p.kind === "CONTRACT_SAMPLE" ? formatTimestamp(p.known_at) : null,
              },
            ]),
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
    [kind],
  );
  return (
    <>
      <SegmentedControl
        label={t("evidence.packs.kind")}
        value={kind}
        options={[
          ...(["CHANGE", "ACCESS"] as const).map((value) => ({
            value,
            label: t(value === "ACCESS" ? "evidence.packs.accessPack" : "evidence.packs.change"),
            disabledReason: mayCreateRegisterEvidence(access, value)
              ? undefined
              : t("evidence.packs.accessDescription"),
          })),
          { value: "CLOSE", label: t("evidence.packs.close") },
          {
            value: "CONTRACT_SAMPLE",
            label: t("evidence.packs.sample"),
            disabledReason: mayCreateSampleEvidence(access)
              ? undefined
              : t("evidence.packs.accessDescription"),
          },
        ]}
        onChange={(value) => {
          const next = new URLSearchParams(search);
          next.set("kind", value);
          for (const key of ["entity", "book", "period", "cursor", "sort"]) next.delete(key);
          setSearchParams(next);
        }}
      />
      <Banner tone="info" title={t("evidence.packs.scope")}>
        <p>
          {t(
            kind === "CLOSE"
              ? "evidence.packs.scopeDescription"
              : kind === "CONTRACT_SAMPLE"
                ? "evidence.packs.sampleScopeDescription"
                : "evidence.register.basis",
          )}
        </p>
      </Banner>
      {kind === "CONTRACT_SAMPLE" && !mayCreateSampleEvidence(access) ? (
        <EvidenceAccessLimited />
      ) : (
        <DataGrid<EvidencePackSummary>
          key={kind}
          filterBar={<FilterBar fields={fields} testId="SF-09-filter-bar" />}
          name={`evidence-packs-${kind}`}
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
      )}
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
            <div className="flex flex-wrap justify-end gap-2">
              <GenerateRegisterPack kind="CHANGE" />
              <GenerateRegisterPack kind="ACCESS" />
              <GenerateSamplePack />
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
