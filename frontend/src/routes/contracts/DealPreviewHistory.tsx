import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { Banner } from "../../components/feedback/Banner";
import { Button } from "../../components/ui/Button";
import { fetchDealPreviews, dealHistoryKey } from "../../lib/api/queries/deal-previews";
import { formatTimestamp } from "../../lib/format";
import { t } from "../../lib/i18n/t";

export function DealPreviewHistory() {
  const [open, setOpen] = useState(false);
  const records = useInfiniteQuery({
    queryKey: dealHistoryKey,
    queryFn: ({ pageParam }) => fetchDealPreviews(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    enabled: open,
    retry: false,
  });
  const rows = records.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <section className="flex flex-col gap-3">
      <Button variant="secondary" onClick={() => setOpen(!open)}>
        {t(open ? "deal.history.hide" : "deal.history.show")}
      </Button>
      {open && (
        <>
          <h2 className="text-heading-sm">{t("deal.history.title")}</h2>
          <p>{t("deal.history.hint")}</p>
          <Button
            variant="secondary"
            loading={records.isFetching && !records.isFetchingNextPage}
            onClick={() => {
              void records.refetch();
            }}
          >
            {t("deal.history.refresh")}
          </Button>
          {records.isPending && <p role="status">{t("deal.loading")}</p>}
          {records.isError && (
            <Banner
              tone="negative"
              title={t("deal.loadError")}
              actions={
                <Button
                  onClick={() => {
                    void (records.isFetchNextPageError
                      ? records.fetchNextPage()
                      : records.refetch());
                  }}
                >
                  {t("deal.retry")}
                </Button>
              }
            />
          )}
          {records.isSuccess && rows.length === 0 && <p>{t("deal.history.empty")}</p>}
          {rows.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <caption className="sr-only">{t("deal.history.title")}</caption>
                <thead>
                  <tr>
                    {["created", "customer", "entity", "start", "products", "state", "actions"].map(
                      (key) => (
                        <th className="p-2" scope="col" key={key}>
                          {t(`deal.history.${key}`)}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id}>
                      <td className="p-2">{formatTimestamp(row.created_at)}</td>
                      <td className="p-2">
                        {row.proposal.customer_name ?? row.proposal.customer_id}
                      </td>
                      <td className="p-2">{row.proposal.entity_code}</td>
                      <td className="p-2">{row.proposal.start_date}</td>
                      <td className="p-2">
                        {[...new Set(row.proposal.lines.map((line) => line.product_code))].join(
                          ", ",
                        )}
                      </td>
                      <td className="p-2">
                        {t(
                          row.saved_contract_id ? "deal.history.saved" : "deal.history.previewOnly",
                        )}
                      </td>
                      <td className="p-2">
                        <Link
                          className="underline"
                          target="_blank"
                          rel="noreferrer"
                          to={`/contracts/deal-preview?preview=${encodeURIComponent(row.id)}`}
                        >
                          {t("deal.history.open")}
                        </Link>
                        {row.saved_contract_id && (
                          <>
                            {" "}
                            ·{" "}
                            <Link
                              className="underline"
                              target="_blank"
                              rel="noreferrer"
                              to={`/contracts/${row.saved_contract_id}/obligations`}
                            >
                              {t("deal.history.openDraft")}
                            </Link>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {records.hasNextPage && (
            <Button
              variant="secondary"
              loading={records.isFetchingNextPage}
              disabledReason={records.isFetching ? t("deal.loading") : undefined}
              onClick={() => {
                void records.fetchNextPage();
              }}
            >
              {t("deal.history.more")}
            </Button>
          )}
        </>
      )}
    </section>
  );
}
