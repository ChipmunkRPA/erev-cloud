import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Banner } from "../../../components/feedback/Banner";
import { Button } from "../../../components/ui/Button";
import { fetchDisclosureSnapshot, fetchDisclosureSnapshots, type DisclosureSnapshot } from "../../../lib/api/queries/disclosures";
import { queryKey } from "../../../lib/api/query-keys";
import { t } from "../../../lib/i18n/t";

function Snapshot({ snapshot }: { snapshot: DisclosureSnapshot }) {
  const [open, setOpen] = useState(false);
  const detail = useQuery({
    queryKey: queryKey("disclosure-snapshots", "tenant", { id: snapshot.id }),
    queryFn: () => fetchDisclosureSnapshot(snapshot.id),
    enabled: open,
  });
  const data = detail.data?.data;
  return <details className="rounded border border-stroke-1 p-3" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer text-body-sm font-semibold">{t(`reports.disclosure.snapshots.kinds.${snapshot.disclosure_kind}`)} — {t(`reports.disclosure.snapshots.${snapshot.source}`)}</summary>
    <p className="text-body-sm">{snapshot.entity_code} · {snapshot.book} · {snapshot.period_key}</p>
    {detail.isError ? <Banner tone="negative" title={t("reports.disclosure.snapshots.error")} actions={<Button variant="link" onClick={() => void detail.refetch()}>{t("reports.report.retry")}</Button>} /> : data === undefined ? <p role="status">{t("reports.disclosure.loading")}</p> : <dl className="flex flex-col gap-2 text-body-sm">
      <div><dt>{t("reports.disclosure.snapshots.status")}</dt><dd>{t("reports.disclosure.snapshots.verified")}</dd></div>
      <div><dt>{t("reports.disclosure.snapshots.cutoff")}</dt><dd>{String(data.known_at ?? "")}</dd></div>
      <div><dt>{t("reports.disclosure.snapshots.scope")}</dt><dd>{t(data.quarter === true ? "reports.disclosure.quarter" : "reports.disclosure.period")}</dd></div>
      <div><dt>{t("reports.disclosure.snapshots.id")}</dt><dd className="break-all font-mono">{snapshot.id}</dd></div>
      <div><dt>{t("reports.disclosure.snapshots.digest")}</dt><dd className="break-all font-mono">{detail.data?.data_sha256}</dd></div>
      {snapshot.period_lock_id !== null && <div><dt>{t("reports.disclosure.snapshots.lock")}</dt><dd className="break-all font-mono">{snapshot.period_lock_id}</dd></div>}
    </dl>}
  </details>;
}

/** Metadata is lazy; expanding a record requests its independently checked saved payload. */
export function DisclosureSnapshots({ runId }: { runId: string }) {
  const [open, setOpen] = useState(false);
  const snapshots = useQuery({
    queryKey: queryKey("disclosure-snapshots", "tenant", { runId }),
    queryFn: () => fetchDisclosureSnapshots(runId),
    enabled: open,
  });
  return <details className="rounded border border-stroke-1 p-3" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer text-body-sm font-semibold">{t("reports.disclosure.snapshots.title")}</summary>
    <p className="my-2 text-body-sm text-fg-2">{t("reports.disclosure.snapshots.description")}</p>
    {snapshots.isError ? <Banner tone="negative" title={t("reports.report.dataLoadError")} actions={<Button variant="link" onClick={() => void snapshots.refetch()}>{t("reports.report.retry")}</Button>} /> : snapshots.data === undefined ? <p role="status">{t("reports.disclosure.loading")}</p> : snapshots.data.length === 0 ? <p>{t("reports.disclosure.snapshots.empty")}</p> : <div className="flex flex-col gap-2">{snapshots.data.map(snapshot => <Snapshot key={snapshot.id} snapshot={snapshot} />)}</div>}
  </details>;
}
