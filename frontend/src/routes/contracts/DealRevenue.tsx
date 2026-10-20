import { useState } from "react";
import { Button } from "../../components/ui/Button";
import type { components } from "../../lib/api/schema";
import { t } from "../../lib/i18n/t";
import { barPercent, revenueGroups } from "./deal-revenue";

const PAGE_SIZE = 24;
const text = (key: string) => t(`deal.${key}`);
export function DealRevenue({ rows }: { rows: components["schemas"]["DealRevenueOut"][] }) {
  const groups = revenueGroups(rows);
  const [choice, setChoice] = useState("");
  const [page, setPage] = useState(0);
  const group = groups.find((item) => item.key === choice) ?? groups[0];
  if (!group) return <p>{text("noSchedule")}</p>;
  const pages = Math.ceil(group.periods.length / PAGE_SIZE);
  const currentPage = Math.min(page, pages - 1);
  const periods = group.periods.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);
  const values = group.periods.map((period) => period.total);
  return (
    <section className="flex flex-col gap-3">
      <h4 className="text-heading-sm">{text("periodSummary")}</h4>
      <label>
        {text("revenueScope")}{" "}
        <select
          className="border p-2"
          value={group.key}
          onChange={(event) => {
            setChoice(event.target.value);
            setPage(0);
          }}
        >
          {groups.map((item) => (
            <option key={item.key} value={item.key}>
              {item.entity} · {item.currency}
            </option>
          ))}
        </select>
      </label>
      <p>{text("scheduleBasis")}</p>
      <div
        role="img"
        aria-label={t("deal.chartSummary", {
          entity: group.entity,
          currency: group.currency,
          total: group.total,
        })}
        className="flex flex-col gap-2 rounded border p-3"
      >
        <p>{text("signedAxis")}</p>
        {periods.map((period) => (
          <div key={period.key} className="grid grid-cols-[8rem_1fr_10rem] items-center gap-2">
            <span>{period.key}</span>
            <div aria-hidden="true" className="grid grid-cols-2">
              <div className="flex justify-end border-r border-stroke-1">
                {period.total.startsWith("-") && (
                  <div
                    className="h-4 bg-current"
                    style={{ width: `${barPercent(period.total, values)}%` }}
                  />
                )}
              </div>
              <div>
                {!period.total.startsWith("-") && (
                  <div
                    className="h-4 bg-current"
                    style={{ width: `${barPercent(period.total, values)}%` }}
                  />
                )}
              </div>
            </div>
            <span className="text-right tabular-nums">
              {period.total} {group.currency}
            </span>
          </div>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left tabular-nums">
          <caption className="text-left">
            {group.entity} · {group.currency}
          </caption>
          <thead>
            <tr>
              <th scope="col" className="p-2">
                {text("period")}
              </th>
              {group.products.map((product) => (
                <th scope="col" className="p-2" key={product.key}>
                  {product.label}
                </th>
              ))}
              <th scope="col" className="p-2">
                {text("periodTotal")}
              </th>
            </tr>
          </thead>
          <tbody>
            {periods.map((period) => (
              <tr key={period.key}>
                <th scope="row" className="p-2">
                  {period.key}
                </th>
                {group.products.map((product) => (
                  <td className="p-2" key={product.key}>
                    {period.amounts[product.key]}
                  </td>
                ))}
                <td className="p-2 font-semibold">{period.total}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" className="p-2">
                {text("allPeriods")}
              </th>
              {group.products.map((product) => (
                <td className="p-2" key={product.key}>
                  {group.totals[product.key]}
                </td>
              ))}
              <td className="p-2 font-semibold">{group.total}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      {pages > 1 && (
        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            disabledReason={currentPage === 0 ? text("firstPage") : undefined}
            onClick={() => setPage(currentPage - 1)}
          >
            {text("previous")}
          </Button>
          <span>{t("deal.page", { current: currentPage + 1, total: pages })}</span>
          <Button
            variant="secondary"
            disabledReason={currentPage === pages - 1 ? text("lastPage") : undefined}
            onClick={() => setPage(currentPage + 1)}
          >
            {text("next")}
          </Button>
        </div>
      )}
    </section>
  );
}
