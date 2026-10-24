import { useQuery } from "@tanstack/react-query";

import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Button } from "../../components/ui/Button";
import { ApiProblem } from "../../lib/api/problems";
import { readJson } from "../../lib/api/queries/contracts";
import { queryKey } from "../../lib/api/query-keys";
import type { components } from "../../lib/api/schema";
import { t } from "../../lib/i18n/t";

type Preview = components["schemas"]["PortfolioBreakagePreviewOut"];
const label = (key: string) => t(`settings.portfolioAllocation.${key}`);

export function PortfolioAllocation({
  path,
  revision,
}: {
  readonly path: string;
  readonly revision: string;
}) {
  const preview = useQuery({
    queryKey: queryKey("portfolios", "tenant", { path, revision, view: "allocation" }),
    queryFn: async () => (await readJson<Preview>(path)).data,
    enabled: false,
    retry: false,
  });
  return (
    <section className="flex flex-col gap-3" aria-label={label("title")}>
      <h4 className="text-heading-sm">{label("title")}</h4>
      <p className="text-body-sm text-fg-2">{label("help")}</p>
      <Button loading={preview.isFetching} onClick={() => void preview.refetch()}>
        {label(preview.isFetching ? "loading" : "preview")}
      </Button>
      {preview.error instanceof ApiProblem ? (
        <RefusalBanner problem={preview.error} />
      ) : preview.isError ? (
        <Banner tone="negative" title={label("networkError")} />
      ) : null}
      {preview.data && !preview.isError && !preview.isFetching ? (
        <>
          <p>
            {label("total")}: {preview.data.allocated_total} /{" "}
            {preview.data.total_breakage_quantity}
            {" · "}
            {preview.data.book_code}
            {" · "}
            {preview.data.currency}
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-body-sm">
              <caption>{label("sources")}</caption>
              <thead>
                <tr>
                  {["contract", "obligation", "ssp", "entitlement", "quantity", "version"].map(
                    (key) => (
                      <th key={key} scope="col" className="p-2">
                        {label(key)}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {preview.data.shares.map((share) => (
                  <tr key={`${share.contract_id}:${share.obligation_id}`}>
                    <td className="p-2">{share.contract_external_id}</td>
                    <td className="p-2">{share.obligation_key}</td>
                    <td className="p-2">{share.ssp}</td>
                    <td className="p-2">{share.entitlement_quantity}</td>
                    <td className="p-2">{share.breakage_quantity}</td>
                    <td className="p-2">{share.contract_version_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </section>
  );
}
