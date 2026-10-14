import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { RecordHeader } from "../../components/record/RecordHeader";
import { Button } from "../../components/ui/Button";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { ApiProblem, isRefused } from "../../lib/api/problems";
import {
  downloadEvidencePack,
  EVIDENCE_PACKS_ROUTE,
  evidencePackKey,
  fetchEvidencePack,
  mayDownloadEvidence,
  mayReadEvidence,
} from "../../lib/api/queries/evidence-packs";
import { useMe } from "../../lib/api/queries/me";
import { reportRunRoute } from "../../lib/api/queries/reports";
import { formatNumber, formatTimestamp } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { bookLabel } from "../reports/viewer/RunStamp";
import { EvidenceAccessLimited } from "./evidence";

export function EvidencePackStatus({ status }: { readonly status: string }) {
  const chip = chipFor("E-67", status);
  return chip === null ? null : <StatusChip status={chip.status} caption={chip.caption} />;
}

function PackRecord({ id }: { readonly id: string }) {
  const access = useAccess();
  const pack = useQuery({
    queryKey: evidencePackKey(id),
    queryFn: () => fetchEvidencePack(id),
    retry: (count, error) =>
      !(error instanceof ApiProblem && [403, 404].includes(error.status)) && count < 1,
    refetchInterval: (query) =>
      ["QUEUED", "RUNNING"].includes(query.state.data?.status ?? "") ? 5000 : false,
  });
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (isRefused(pack.error)) return <EvidenceAccessLimited />;
  if (pack.error instanceof ApiProblem && pack.error.status === 404)
    return <EmptyState title={t("evidence.packs.notFound")} description="" />;
  if (pack.isError)
    return (
      <Banner
        tone="negative"
        title={t("evidence.packs.loadError")}
        actions={<Button onClick={() => void pack.refetch()}>{t("evidence.packs.retry")}</Button>}
      />
    );
  if (pack.data === undefined)
    return <Skeleton region={t("evidence.packs.detailTitle")} shape="rows" count={6} />;
  const data = pack.data;
  const succeeded = data.status === "SUCCEEDED";
  async function download(artifact: "download" | "manifest") {
    setDownloading(true);
    setError(null);
    try {
      const blob = await downloadEvidencePack(id, artifact);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${data.pack_no}${artifact === "manifest" ? ".manifest.json" : ".zip"}`;
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("evidence.packs.downloadError"));
    } finally {
      setDownloading(false);
    }
  }
  return (
    <>
      <RecordHeader
        title={data.pack_no}
        breadcrumb={[{ label: t("evidence.packs.title"), to: EVIDENCE_PACKS_ROUTE }]}
        chips={<EvidencePackStatus status={data.status} />}
        meta={[
          { label: t("evidence.packs.kind"), value: t("evidence.packs.close") },
          { label: t("evidence.packs.entity"), value: data.entity_code },
          { label: t("evidence.packs.book"), value: bookLabel(data.book) },
          { label: t("evidence.packs.period"), value: data.period_key },
          { label: t("evidence.packs.created"), value: formatTimestamp(data.created_at) },
        ]}
        actions={
          succeeded && data.download_href !== null && mayDownloadEvidence(access, data) ? (
            <>
              <Button loading={downloading} onClick={() => void download("manifest")}>
                {t("evidence.packs.downloadManifest")}
              </Button>
              <Button loading={downloading} onClick={() => void download("download")}>
                {t("evidence.packs.download")}
              </Button>
            </>
          ) : null
        }
      />
      {error === null ? null : (
        <Banner tone="negative" title={t("evidence.packs.downloadError")}>
          {error}
        </Banner>
      )}
      {!succeeded ? (
        <Banner
          tone={data.status === "FAILED" ? "negative" : "info"}
          title={t(data.status === "FAILED" ? "evidence.packs.failed" : "evidence.packs.pending")}
        />
      ) : null}
      {succeeded && data.manifest !== null ? (
        <section className="space-y-4 p-[var(--panel-pad)]">
          <h2 className="text-title-md">{t("evidence.packs.files")}</h2>
          <dl>
            <dt>{t("evidence.packs.manifest")}</dt>
            <dd className="break-all font-mono text-mono-sm">{data.manifest_sha256}</dd>
          </dl>
          <div className="overflow-auto">
            <table className="w-full text-left text-body-sm">
              <caption className="sr-only">{t("evidence.packs.files")}</caption>
              <thead>
                <tr>
                  {["path", "report", "bytes", "sha"].map((key) => (
                    <th scope="col" className="p-2" key={key}>
                      {t(`evidence.packs.${key}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.manifest.files.map((file) => (
                  <tr key={file.path} className="border-t border-hairline">
                    <th scope="row" className="break-all p-2 font-normal">
                      {file.path}
                    </th>
                    <td className="p-2">
                      {file.report_run_id === null ? (
                        "—"
                      ) : (
                        <Link className="underline" to={reportRunRoute(file.report_run_id)}>
                          {file.report_run_id}
                        </Link>
                      )}
                    </td>
                    <td className="p-2 num">{formatNumber(file.bytes, { kind: "count" })}</td>
                    <td className="break-all p-2 font-mono text-mono-sm">{file.sha256}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </>
  );
}

export function EvidencePackPage() {
  const { packId = "" } = useParams();
  const me = useMe();
  const access = useAccess();
  return (
    <div data-testid="SF-09-pack-page" className="px-[var(--gutter)] py-[var(--panel-pad)]">
      {me.isError ? (
        <Banner tone="negative" title={me.error.message} />
      ) : me.data === undefined ? (
        <Skeleton region={t("evidence.packs.detailTitle")} shape="rows" count={6} />
      ) : !mayReadEvidence(access) ? (
        <EvidenceAccessLimited />
      ) : (
        <PackRecord key={packId} id={packId} />
      )}
    </div>
  );
}
