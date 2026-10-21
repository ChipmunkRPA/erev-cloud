import type { ReportRun } from "../../../lib/api/queries/reports";
import { formatDate, formatTimestamp, NO_VALUE } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";

const FIELDS = [
  "entity_id",
  "base_currency",
  "quote_currency",
  "period_key",
  "period_end",
  "rate_type",
  "rate",
  "rate_cutoff",
] as const;
type Rate = Record<(typeof FIELDS)[number], string> & {
  rate_id?: string | null;
  version_id?: string | null;
};
function isRate(value: unknown): value is Rate {
  if (typeof value !== "object" || value === null) return false;
  const row = value as Record<string, unknown>;
  return (
    FIELDS.every((key) => typeof row[key] === "string") &&
    ["rate_id", "version_id"].every((key) => row[key] == null || typeof row[key] === "string")
  );
}

/** Show retained rate legs, including same-currency legs; never recalculate a report. */
export function RpoCurrencyDetails({ run }: { readonly run: ReportRun }) {
  if (run.report.code !== "rpo" && run.report.code !== "rpo_rollforward") return null;
  const raw = run.control_totals?.translation_rates;
  const rates = Array.isArray(raw) ? raw.filter(isRate) : [];
  if (rates.length === 0) return null;
  const entities = new Map(run.entity_scope.map((entity) => [entity.id, entity.code]));
  return (
    <details className="rounded border border-[var(--border-subtle)] p-3">
      <summary className="cursor-pointer font-medium">{t("reports.rpoFx.title")}</summary>
      <p className="my-2 text-sm">{t("reports.rpoFx.basis")}</p>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr>
              <th className="p-2">{t("reports.rpoFx.entityPeriod")}</th>
              <th className="p-2">{t("reports.rpoFx.kind")}</th>
              <th className="p-2">{t("reports.rpoFx.pair")}</th>
              <th className="p-2">{t("reports.rpoFx.rate")}</th>
              <th className="p-2">{t("reports.rpoFx.source")}</th>
              <th className="p-2">{t("reports.rpoFx.cutoff")}</th>
            </tr>
          </thead>
          <tbody>
            {rates.map((rate, index) => (
              <tr
                key={`${rate.entity_id}/${rate.period_key}/${rate.base_currency}/${rate.quote_currency}/${rate.rate_type}/${index}`}
              >
                <th scope="row" className="p-2 font-normal">
                  {entities.get(rate.entity_id) ?? rate.entity_id}
                  <div>
                    {rate.period_key} · {formatDate(rate.period_end)}
                  </div>
                </th>
                <td className="p-2">
                  {rate.rate_type === "average"
                    ? t("reports.rpoFx.average")
                    : rate.rate_type === "closing"
                      ? t("reports.rpoFx.closing")
                      : rate.rate_type}
                </td>
                <td className="p-2">
                  {rate.base_currency} → {rate.quote_currency}
                </td>
                <td className="num p-2">{rate.rate}</td>
                <td className="p-2">
                  {rate.base_currency === rate.quote_currency ? (
                    t("reports.rpoFx.identity")
                  ) : (
                    <>
                      <div>{t("reports.rpoFx.rateId", { id: rate.rate_id ?? NO_VALUE })}</div>
                      <div>{t("reports.rpoFx.versionId", { id: rate.version_id ?? NO_VALUE })}</div>
                    </>
                  )}
                </td>
                <td className="p-2">{formatTimestamp(rate.rate_cutoff)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
