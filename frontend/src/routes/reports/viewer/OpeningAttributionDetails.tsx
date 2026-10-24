import { Link } from "react-router";
import type { ReportRun } from "../../../lib/api/queries/reports";
import { t } from "../../../lib/i18n/t";

const BASES = ["ZERO_GROUP_OPENING", "ZERO_CONSUMPTION", "CREATED_AFTER_OPENING"] as const;
type Basis = (typeof BASES)[number];
type Detail = {
  subject: string;
  contract_id: string;
  basis: Basis;
  event_id: string;
  effective_date: string;
};
function isDetail(value: unknown): value is Detail {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Record<string, unknown>;
  return (
    ["subject", "contract_id", "basis", "event_id", "effective_date"].every(
      (key) => typeof item[key] === "string",
    ) && BASES.some((basis) => basis === item.basis)
  );
}
function OpeningSourceDetails({ run }: { readonly run: ReportRun }) {
  const raw = run.control_totals?.opening_attribution_explanation;
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return null;
  const items = (raw as Record<string, unknown>).items;
  if (!Array.isArray(items)) return null;
  const details = items.filter(isDetail);
  if (details.length === 0) return null;
  return (
    <details className="rounded-md border border-hairline p-3">
      <summary className="cursor-pointer">{t("reports.openingAttribution.title")}</summary>
      <ul className="mt-2 flex flex-col gap-2">
        {details.map((item, index) => (
          <li key={index}>
            <p>
              {item.subject} · {t(`reports.openingAttribution.${item.basis}`)}
            </p>
            {item.effective_date ? (
              <p>{t("reports.openingAttribution.created", { date: item.effective_date })}</p>
            ) : null}
            {item.event_id ? (
              <p>{t("reports.openingAttribution.event", { id: item.event_id })}</p>
            ) : null}
            {item.contract_id ? (
              <Link
                className="underline"
                to={`/contracts/${encodeURIComponent(item.contract_id)}/history`}
              >
                {t("reports.openingAttribution.history")}
              </Link>
            ) : null}
          </li>
        ))}
      </ul>
    </details>
  );
}

export function OpeningAttributionDetails({ run }: { readonly run: ReportRun }) {
  const availability = run.control_totals?.opening_attribution_availability;
  const incomplete =
    typeof availability === "object" &&
    availability !== null &&
    "status" in availability &&
    availability.status === "INCOMPLETE";
  return (
    <>
      {incomplete ? (
        <p role="status" className="rounded-md border border-hairline p-3">
          {t("reports.openingAttribution.incomplete")}
        </p>
      ) : null}
      <OpeningSourceDetails run={run} />
    </>
  );
}
