import { useQuery } from "@tanstack/react-query";

import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Button } from "../../components/ui/Button";
import { ApiProblem } from "../../lib/api/problems";
import { readJson } from "../../lib/api/queries/contracts";
import { queryKey } from "../../lib/api/query-keys";
import type { components } from "../../lib/api/schema";
import { hasMessage, t } from "../../lib/i18n/t";

const label = (key: string) => t(`settings.portfolioImpact.${key}`);
type Preview = components["schemas"]["PortfolioImpactOut"];
export function PortfolioImpact({
  path,
  revision,
}: {
  readonly path: string;
  readonly revision: string;
}) {
  const preview = useQuery({
    queryKey: queryKey("portfolios", "tenant", { path, revision, view: "impact" }),
    queryFn: async () => (await readJson<Preview>(path)).data,
    enabled: false,
    retry: false,
  });
  return (
    <section className="flex flex-col gap-3" aria-label={label("title")}>
      <h4 className="text-heading-sm">{label("title")}</h4>
      <p className="text-body-sm text-fg-2">{label("help")}</p>
      <Button loading={preview.isFetching} onClick={() => void preview.refetch()}>
        {label("preview")}
      </Button>
      {preview.error instanceof ApiProblem ? (
        <RefusalBanner problem={preview.error} />
      ) : preview.isError ? (
        <Banner tone="negative" title={label("networkError")} />
      ) : null}
      {preview.data && !preview.isError && !preview.isFetching
        ? preview.data.groups.map((group) => (
            <div key={group.combination_group_id} className="flex flex-col gap-2">
              <p>
                {group.book_code} · {group.currency} · {label("catchUp")}: {group.catch_up_amount}
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-body-sm">
                  <caption>{label("balances")}</caption>
                  <thead>
                    <tr>
                      {["contract", "balance", "before", "after", "currency"].map((key) => (
                        <th key={key} scope="col" className="p-2">
                          {label(key)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {group.members.flatMap((member) =>
                      member.balances_after.map((after) => {
                        const before = member.balances_before.find(
                          (item) => item.balance === after.balance,
                        );
                        return (
                          <tr key={`${member.contract_id}:${after.balance}`}>
                            <td className="p-2">{member.contract_external_id}</td>
                            <td className="p-2">
                              {hasMessage(`contracts.balance.${after.balance}`)
                                ? t(`contracts.balance.${after.balance}`)
                                : after.balance}
                            </td>
                            <td className="p-2">{before?.amount.amount ?? "—"}</td>
                            <td className="p-2">{after.amount.amount}</td>
                            <td className="p-2">{after.amount.currency}</td>
                          </tr>
                        );
                      }),
                    )}
                  </tbody>
                </table>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-body-sm">
                  <caption>{label("revenue")}</caption>
                  <thead>
                    <tr>
                      {["contract", "period", "before", "after", "change", "currency"].map(
                        (key) => (
                          <th scope="col" key={key} className="p-2">
                            {label(key)}
                          </th>
                        ),
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {group.members.flatMap((member) =>
                      member.revenue_by_period.map((row) => (
                        <tr key={`${member.contract_id}:${row.period_key}`}>
                          <td className="p-2">{member.contract_external_id}</td>
                          <td className="p-2">{row.period_key}</td>
                          <td className="p-2">{row.before.amount}</td>
                          <td className="p-2">{row.after.amount}</td>
                          <td className="p-2">{row.change.amount}</td>
                          <td className="p-2">{row.after.currency}</td>
                        </tr>
                      )),
                    )}
                  </tbody>
                </table>
              </div>
              <details>
                <summary>{label("sources")}</summary>
                <p>
                  {label("sourceVersion")}: {group.source_contract_version_id}
                </p>
                <p>
                  {label("inputHash")}: {group.input_sha256}
                </p>
              </details>
            </div>
          ))
        : null}
    </section>
  );
}
