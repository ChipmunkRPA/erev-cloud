import type { DealPreview } from "../../lib/api/queries/deal-previews";
import { t } from "../../lib/i18n/t";

const text = (key: string) => t(`deal.${key}`);
export function DealResults({ preview }: { preview: DealPreview }) {
  return (
    <section className="flex flex-col gap-6">
      <h2 className="text-heading-md">{text("results")}</h2>
      <p>
        {preview.proposal.customer_name ?? preview.proposal.customer_id} ·{" "}
        {preview.proposal.entity_code} · {preview.proposal.start_date}
      </p>
      {preview.presentation.map((book) => (
        <section key={book.book_code} className="flex flex-col gap-3">
          <h3 className="text-heading-sm">{book.book_code}</h3>
          <dl className="grid grid-cols-2 gap-2">
            {(
              ["transaction_price", "total_allocated", "scheduled", "awaiting_trigger"] as const
            ).map((key) => (
              <div key={key}>
                <dt>{text(key)}</dt>
                <dd>
                  {book[key].amount} {book[key].currency}
                </dd>
              </div>
            ))}
          </dl>
          <p>
            {text("materialRight")}: {text(book.has_material_right ? "yes" : "no")} ·{" "}
            {text("variableConsideration")}: {text(book.has_variable_consideration ? "yes" : "no")}
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-left tabular-nums">
              <caption className="text-left font-semibold">{text("allocation")}</caption>
              <thead>
                <tr>
                  {[
                    "product",
                    "stated",
                    "low",
                    "mid",
                    "high",
                    "range",
                    "selected",
                    "weight",
                    "allocated",
                    "adjustment",
                  ].map((key) => (
                    <th className="p-2" key={key}>
                      {text(key)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {book.allocations.map((row) => (
                  <tr key={row.subject_key}>
                    {[
                      row.product_code,
                      `${row.stated_price.amount} ${row.stated_price.currency}`,
                      row.ssp_low,
                      row.ssp_mid,
                      row.ssp_high,
                      row.range_position === null ? null : text(row.range_position),
                      row.selected_ssp,
                      row.allocation_weight,
                      `${row.allocated_amount.amount} ${row.allocated_amount.currency}`,
                      `${row.allocation_adjustment.amount} ${row.allocation_adjustment.currency}`,
                    ].map((value, i) => (
                      <td className="border-t p-2" key={i}>
                        {value ?? text("unavailable")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left tabular-nums">
              <caption className="text-left font-semibold">{text("revenue")}</caption>
              <thead>
                <tr>
                  {["entity", "period", "product", "amount"].map((key) => (
                    <th className="p-2" key={key}>
                      {text(key)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {book.revenue_by_period.map((row) => (
                  <tr key={`${row.entity_code}/${row.period_key}/${row.subject_key}`}>
                    <td className="p-2">{row.entity_code}</td>
                    <td className="p-2">{row.period_key}</td>
                    <td className="p-2">{row.product_code ?? text("unavailable")}</td>
                    <td className="p-2">
                      {row.amount.amount} {row.amount.currency}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {book.revenue_by_period.length === 0 && <p>{text("noSchedule")}</p>}
        </section>
      ))}
      {preview.presentation.length === 0 && <p>{text("noResults")}</p>}
    </section>
  );
}
