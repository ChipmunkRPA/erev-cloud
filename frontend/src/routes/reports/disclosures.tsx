import { useInfiniteQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Field } from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { Button } from "../../components/ui/Button";
import { useAccess } from "../../lib/access";
import {
  fetchDisclosureSnapshotPage,
  type DisclosureSnapshot,
} from "../../lib/api/queries/disclosures";
import { reportRunRoute } from "../../lib/api/queries/reports";
import { queryKey } from "../../lib/api/query-keys";
import { t } from "../../lib/i18n/t";
import { ReportsHeader } from "./frame";
import { Snapshot } from "./viewer/DisclosureSnapshots";

const KINDS: readonly DisclosureSnapshot["disclosure_kind"][] = [
  "RPO",
  "CONTRACT_BALANCE_ROLLFORWARD",
  "REVENUE_FROM_OPENING_LIABILITY",
  "PRIOR_PERIOD_POB_REVENUE",
  "DISAGGREGATION",
  "COST_ROLLFORWARD",
  "EXPEDIENTS_USED",
];
export function DisclosureRegister() {
  const access = useAccess();
  const [search, setSearch] = useSearchParams();
  const kind = search.get("disclosure_kind") ?? "";
  const entity = search.get("entity");
  const source = search.get("source") ?? "";
  const query = {
    entity: entity === "all" ? null : entity,
    book: search.get("book"),
    period: search.get("period"),
    disclosure_kind: kind || null,
    sort: "-created_at",
    source: source || null,
  };
  const allowed = access.holdsAnywhere("report.run");
  const snapshots = useInfiniteQuery({
    queryKey: queryKey("disclosure-snapshots", "tenant", { view: "register", ...query }),
    queryFn: ({ pageParam }) => fetchDisclosureSnapshotPage(query, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    enabled: allowed,
    retry: false,
  });
  const records = snapshots.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <div className="flex flex-col gap-4">
      <ReportsHeader />
      <section
        className="flex flex-col gap-4 px-[var(--gutter)]"
        aria-label={t("reports.disclosures.title")}
      >
        <h2 className="text-title-md">{t("reports.disclosures.title")}</h2>
        <p>{t("reports.disclosures.description")}</p>
        {!allowed ? (
          <EmptyState
            title={t("settings.access.title", { area: t("reports.disclosures.title") })}
            description={t("settings.access.description", { permission: "report.run" })}
          />
        ) : (
          <>
            <Field name="disclosure-kind" label={t("reports.disclosures.kind")}>
              {(control) => (
                <Select
                  control={control}
                  value={kind}
                  options={[
                    { value: "", label: t("reports.disclosures.all") },
                    ...KINDS.map((value) => ({
                      value,
                      label: t(`reports.disclosure.snapshots.kinds.${value}`),
                    })),
                  ]}
                  onChange={(next) => {
                    const updated = new URLSearchParams(search);
                    if (next) updated.set("disclosure_kind", next);
                    else updated.delete("disclosure_kind");
                    setSearch(updated);
                  }}
                />
              )}
            </Field>
            <Field name="disclosure-source" label={t("reports.disclosures.source")}>
              {(control) => (
                <Select
                  control={control}
                  value={source}
                  options={[
                    { value: "", label: t("reports.disclosures.allSources") },
                    ...["DRAFT", "LOCKED"].map((value) => ({
                      value,
                      label: t(`reports.disclosure.snapshots.${value}`),
                    })),
                  ]}
                  onChange={(next) => {
                    const updated = new URLSearchParams(search);
                    if (next) updated.set("source", next);
                    else updated.delete("source");
                    setSearch(updated);
                  }}
                />
              )}
            </Field>
            {snapshots.isError ? (
              <Banner
                tone="negative"
                title={t("reports.disclosure.snapshots.error")}
                actions={
                  <Button
                    onClick={() =>
                      void (snapshots.isFetchNextPageError
                        ? snapshots.fetchNextPage()
                        : snapshots.refetch())
                    }
                  >
                    {t("reports.report.retry")}
                  </Button>
                }
              />
            ) : null}
            {snapshots.isPending ? (
              <p role="status">{t("reports.disclosure.loading")}</p>
            ) : snapshots.isSuccess && records.length === 0 ? (
              <EmptyState
                title={t("reports.disclosures.empty")}
                description={t("reports.disclosures.emptyHelp")}
              />
            ) : null}
            {records.map((record) => (
              <div key={record.id} className="flex flex-col gap-2">
                <Snapshot snapshot={record} />
                <Link className="text-body-sm" to={reportRunRoute(record.report_run_id)}>
                  {t("reports.disclosures.run")}
                </Link>
              </div>
            ))}
            {snapshots.hasNextPage ? (
              <Button loading={snapshots.isFetching} onClick={() => void snapshots.fetchNextPage()}>
                {t("reports.disclosures.more")}
              </Button>
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}
