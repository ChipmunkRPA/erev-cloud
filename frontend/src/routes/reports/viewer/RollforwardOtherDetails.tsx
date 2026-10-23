import { Link } from "react-router";

import { Banner } from "../../../components/feedback/Banner";
import { currencyRegistered } from "../../../lib/api/queries/approvals";
import type { ReportRun } from "../../../lib/api/queries/reports";
import { formatMoney, formatPercent, NO_VALUE } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";

const FIELDS = [
  "contract",
  "entity",
  "period",
  "book",
  "currency",
  "role",
  "other",
  "closing",
] as const;
type Detail = Record<(typeof FIELDS)[number], string>;
function isDetail(value: unknown): value is Detail {
  return (
    typeof value === "object" &&
    value !== null &&
    FIELDS.every((key) => typeof (value as Record<string, unknown>)[key] === "string")
  );
}
export function RollforwardOtherDetails({ run }: { readonly run: ReportRun }) {
  const raw = run.control_totals?.other_explanation;
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return null;
  const value = raw as Record<string, unknown>;
  if (typeof value.threshold_ratio !== "string" || !Array.isArray(value.items)) return null;
  const details = value.items.filter(isDetail);
  if (details.length === 0) return null;
  const money = (amount: string, currency: string) =>
    currencyRegistered(currency) ? formatMoney(amount, currency, { variant: "inline" }) : NO_VALUE;
  return (
    <Banner tone="warning" title={t("reports.other.title")}>
      <p>
        {t("reports.other.basis", {
          threshold: formatPercent(value.threshold_ratio, { kind: "share" }),
        })}
      </p>
      <details className="mt-2">
        <summary className="cursor-pointer">
          {t("reports.other.details", { count: details.length })}
        </summary>
        <ul className="mt-2 flex flex-col gap-2">
          {details.map((item, index) => (
            <li key={index}>
              <span>
                {item.contract || t("reports.other.total")} {item.entity} ·{" "}
                {t(`reports.other.role.${item.role}`)}
              </span>
              <span className="num">
                {t("reports.other.amounts", {
                  other: money(item.other, item.currency),
                  closing: money(item.closing, item.currency),
                })}
              </span>
              {item.entity && item.book && item.period ? (
                <Link
                  className="ml-2 underline"
                  to={`/close/${[item.entity, item.book, item.period].map(encodeURIComponent).join("/")}/reconciliations`}
                >
                  {t("reports.other.reconcile")}
                </Link>
              ) : null}
            </li>
          ))}
        </ul>
      </details>
    </Banner>
  );
}
