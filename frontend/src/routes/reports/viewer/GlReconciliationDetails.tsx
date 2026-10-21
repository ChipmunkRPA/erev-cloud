import { useId, useState } from "react";
import { Link } from "react-router";

import { chipFor, StatusChip } from "../../../components/ui/StatusChip";
import { currencyRegistered } from "../../../lib/api/queries/approvals";
import type { TieOutResult } from "../../../lib/api/queries/reports";
import { formatMoney, formatTimestamp, NO_VALUE } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";

type Detail = NonNullable<TieOutResult["details"]>[number];
const AMOUNTS = [
  ["gl", "gl"],
  ["source_subledger", "subledger"],
  ["rollforward", "report"],
  ["subledger_gl_difference", "subledgerGl"],
  ["report_subledger_difference", "reportSubledger"],
  ["difference", "net"],
] as const;

function status(value: string | undefined) {
  const chip = value ? chipFor("T-RPT-02", value) : null;
  return chip ? <StatusChip status={chip.status} caption={chip.caption} /> : NO_VALUE;
}

function amount(detail: Detail, field: string): string {
  const value = detail[field];
  return value !== undefined &&
    value !== "" &&
    detail.currency &&
    currencyRegistered(detail.currency)
    ? formatMoney(value, detail.currency, { variant: "inline" })
    : NO_VALUE;
}

/** Render retained GL evidence; filters never recalculate or net the recorded comparisons. */
export function GlReconciliationDetails({ details }: { readonly details: readonly Detail[] }) {
  const id = useId();
  const [filter, setFilter] = useState("all");
  const rows = details.filter((detail) => detail.entity || detail.role || detail.reconciliation_id);
  const notes = details.filter((detail) => !rows.includes(detail));
  const shown = rows.filter((detail) => {
    if (filter === "fail") return detail.result === "FAIL" || detail.bridge_result === "FAIL";
    if (filter === "unavailable") {
      return (
        !detail.result ||
        detail.result === "NOT_APPLICABLE" ||
        detail.bridge_result === "NOT_APPLICABLE"
      );
    }
    return true;
  });
  return (
    <div className="mt-2 flex flex-col gap-2">
      <label htmlFor={id} className="flex items-center gap-2">
        {t("reports.glDetails.show")}
        <select
          id={id}
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          className="rounded border border-hairline bg-surface px-2 py-1"
        >
          <option value="all">{t("reports.glDetails.all")}</option>
          <option value="fail">{t("reports.glDetails.fail")}</option>
          <option value="unavailable">{t("reports.glDetails.unavailable")}</option>
        </select>
      </label>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-body-sm">
          <caption className="text-left text-fg-2">
            {t("reports.glDetails.caption", { shown: shown.length, total: rows.length })}
          </caption>
          <thead>
            <tr>
              <th scope="col" className="p-2 text-left">
                {t("reports.glDetails.scope")}
              </th>
              {AMOUNTS.map(([field, label]) => (
                <th scope="col" key={field} className="p-2 text-right">
                  {t(`reports.glDetails.${label}`)}
                </th>
              ))}
              <th scope="col" className="p-2 text-left">
                {t("reports.glDetails.result")}
              </th>
              <th scope="col" className="p-2 text-left">
                {t("reports.glDetails.bridge")}
              </th>
              <th scope="col" className="p-2 text-left">
                {t("reports.glDetails.source")}
              </th>
            </tr>
          </thead>
          <tbody>
            {shown.map((detail, index) => (
              <tr key={index} className="border-t border-hairline">
                <th scope="row" className="p-2 text-left font-medium">
                  {[detail.entity, detail.role].filter(Boolean).join(" · ") || NO_VALUE}
                  <div className="font-normal">
                    {[detail.book_code, detail.period_key, detail.currency]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                </th>
                {AMOUNTS.map(([field]) => (
                  <td key={field} className="num whitespace-nowrap p-2 text-right">
                    {amount(detail, field)}
                  </td>
                ))}
                <td className="p-2">{status(detail.result)}</td>
                <td className="p-2">{status(detail.bridge_result)}</td>
                <td className="min-w-48 p-2">
                  {detail.source_status ? (
                    <div>{t("reports.glDetails.review", { status: detail.source_status })}</div>
                  ) : null}
                  {detail.source_recorded_at ? (
                    <div>
                      {t("reports.glDetails.captured", {
                        at: formatTimestamp(detail.source_recorded_at),
                      })}
                    </div>
                  ) : null}
                  {detail.reason ? <div>{detail.reason}</div> : null}
                  {detail.bridge_reason ? <div>{detail.bridge_reason}</div> : null}
                  {detail.reconciliation_id &&
                  detail.entity &&
                  detail.book_code &&
                  detail.period_key ? (
                    <Link
                      className="underline"
                      to={`/close/${[detail.entity, detail.book_code, detail.period_key].map(encodeURIComponent).join("/")}/reconciliations/${encodeURIComponent(detail.reconciliation_id)}`}
                    >
                      {t("reports.tieOuts.source")}
                    </Link>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {shown.length === 0 ? <p role="status">{t("reports.glDetails.empty")}</p> : null}
      {notes.map((note, index) => (
        <p key={index}>{note.reason ?? note.bridge_reason}</p>
      ))}
    </div>
  );
}
