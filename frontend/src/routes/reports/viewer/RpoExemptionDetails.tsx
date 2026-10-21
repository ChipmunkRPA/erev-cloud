import { currencyRegistered } from "../../../lib/api/queries/approvals";
import type { ReportRun } from "../../../lib/api/queries/reports";
import { formatMoney, NO_VALUE } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";

const FIELDS = [
  "contract",
  "obligation",
  "entity",
  "currency",
  "opening_date",
  "closing_date",
  "opening_excluded",
  "closing_excluded",
  "movement",
] as const;
type Detail = Record<(typeof FIELDS)[number], string> & {
  opening_rule: string | null;
  closing_rule: string | null;
};
function isDetail(value: unknown): value is Detail {
  if (typeof value !== "object" || value === null) return false;
  const row = value as Record<string, unknown>;
  return (
    FIELDS.every((key) => typeof row[key] === "string") &&
    [row.opening_rule, row.closing_rule].every((rule) => rule === null || typeof rule === "string")
  );
}
function ruleName(rule: string | null): string {
  if (rule === "POL-197") return t("reports.exemptions.shortTerm");
  if (rule === "POL-198") return t("reports.exemptions.invoice");
  if (rule === "POL-200") return t("reports.exemptions.variable");
  return rule ?? t("reports.exemptions.none");
}
function money(amount: string, currency: string): string {
  return currencyRegistered(currency)
    ? formatMoney(amount, currency, { variant: "inline" })
    : NO_VALUE;
}
const TRANSLATION_FIELDS = [
  "contract",
  "entity",
  "period",
  "currency",
  "movement",
  "translated_currency",
  "translated_movement",
] as const;
type Translation = Record<(typeof TRANSLATION_FIELDS)[number], string>;
function isTranslation(value: unknown): value is Translation {
  if (typeof value !== "object" || value === null) return false;
  const row = value as Record<string, unknown>;
  return TRANSLATION_FIELDS.every((key) => typeof row[key] === "string");
}

export function RpoExemptionDetails({ run }: { readonly run: ReportRun }) {
  const raw = run.control_totals?.exemption_changes;
  if (run.report.code !== "rpo_rollforward") return null;
  const rows = Array.isArray(raw) ? raw.filter(isDetail) : [];
  const translated = run.control_totals?.exemption_translation;
  const translations = Array.isArray(translated) ? translated.filter(isTranslation) : [];
  if (rows.length === 0 && translations.length === 0) return null;
  return (
    <details className="rounded border border-[var(--border-subtle)] p-3">
      <summary className="cursor-pointer font-medium">{t("reports.exemptions.title")}</summary>
      <p hidden={rows.length === 0} className="my-2 text-sm">
        {t("reports.exemptions.basis")}
      </p>
      <div hidden={rows.length === 0} className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr>
              <th className="p-2">{t("reports.exemptions.obligation")}</th>
              <th className="p-2">{t("reports.exemptions.opening")}</th>
              <th className="p-2">{t("reports.exemptions.closing")}</th>
              <th className="p-2">{t("reports.exemptions.movement")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.entity}/${row.contract}/${row.obligation}/${row.currency}`}>
                <th className="p-2 font-normal" scope="row">
                  {row.contract} · {row.obligation}
                  <div>{row.entity}</div>
                </th>
                <td className="p-2">
                  <div>{row.opening_date}</div>
                  <div>{ruleName(row.opening_rule)}</div>
                  <div className="num">{money(row.opening_excluded, row.currency)}</div>
                </td>
                <td className="p-2">
                  <div>{row.closing_date}</div>
                  <div>{ruleName(row.closing_rule)}</div>
                  <div className="num">{money(row.closing_excluded, row.currency)}</div>
                </td>
                <td className="num p-2">{money(row.movement, row.currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {translations.length > 0 ? (
        <div className="mt-4 overflow-x-auto">
          <h3 className="font-medium">{t("reports.exemptions.translationTitle")}</h3>
          <p className="my-2 text-sm">{t("reports.exemptions.translationBasis")}</p>
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                <th className="p-2">{t("reports.exemptions.contractPeriod")}</th>
                <th className="p-2">{t("reports.exemptions.originalMovement")}</th>
                <th className="p-2">{t("reports.exemptions.translatedMovement")}</th>
              </tr>
            </thead>
            <tbody>
              {translations.map((row) => (
                <tr
                  key={`${row.entity}/${row.contract}/${row.period}/${row.currency}/${row.translated_currency}`}
                >
                  <th scope="row" className="p-2 font-normal">
                    {row.contract}
                    <div>
                      {row.entity} · {row.period}
                    </div>
                  </th>
                  <td className="num p-2">{money(row.movement, row.currency)}</td>
                  <td className="num p-2">
                    {money(row.translated_movement, row.translated_currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </details>
  );
}
