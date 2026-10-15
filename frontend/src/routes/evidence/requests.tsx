// SCREENS_B §6.1 A-01–A-20. Destinations retain close context; report views decide
// their locked/live basis. Unsupported pack generators stay explicit and unavailable.
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useNavigate } from "react-router";
import { contextSearch } from "../../app/shell/IconRail";
import { Banner } from "../../components/feedback/Banner";
import { Button } from "../../components/ui/Button";
import { Menu, type MenuItem } from "../../components/ui/Menu";
import { isRefused } from "../../lib/api/problems";
import { useAccess } from "../../lib/access";
import { fetchReportDefinitions, reportDefinitionsKey } from "../../lib/api/queries/reports";
import { useMe } from "../../lib/api/queries/me";
import { reconciliationsRoute } from "../../lib/api/queries/reconciliations";
import { t } from "../../lib/i18n/t";

interface RequestRow {
  readonly id: string;
  readonly reports?: readonly string[];
  readonly destination?: "schedules" | "reconciliation" | "runs" | "audit" | "walkthrough";
  readonly pack?: "Sample" | "Access" | "Change";
  readonly outside?: boolean;
}

export const AUDITOR_REQUESTS: readonly RequestRow[] = [
  { id: "01", reports: ["je_population"] },
  { id: "02", destination: "schedules" },
  { id: "03", reports: ["extract_contracts", "modification_register"] },
  { id: "04", pack: "Sample" },
  {
    id: "05",
    reports: [
      "ssp_change_log",
      "ssp_version_diff",
      "allocations_by_ssp_version",
      "ssp_override_listing",
    ],
  },
  { id: "06", reports: ["modification_register"] },
  { id: "07", reports: ["estimate_change_listing", "revenue_from_prior_period_obligations"] },
  { id: "08", reports: ["contract_balance_rollforward", "revenue_from_opening_liability"] },
  { id: "09", reports: ["rpo", "rpo_rollforward"] },
  { id: "10", reports: ["disaggregation"] },
  { id: "11", reports: ["late_entry_report", "out_of_period_register"] },
  { id: "12", reports: ["manual_adjustment_register"] },
  { id: "13", destination: "reconciliation" },
  { id: "14", reports: ["balance_aging"] },
  { id: "15", reports: ["user_access_listing", "sod_conflict_report"], pack: "Access" },
  { id: "16", reports: ["config_change_register"], pack: "Change" },
  { id: "17", outside: true },
  { id: "18", destination: "runs" },
  { id: "19", destination: "audit", reports: ["chain_verification_report"] },
  { id: "20", destination: "walkthrough" },
];

export function requestDestination(
  destination: NonNullable<RequestRow["destination"]>,
  search: string,
  userId: string,
): string | null {
  const context = contextSearch(search, ["entity", "book", "period"]);
  if (destination === "reconciliation") {
    const params = new URLSearchParams(context);
    const entity = params.get("entity"),
      book = params.get("book"),
      period = params.get("period");
    return entity === null || book === null || period === null
      ? null
      : `${reconciliationsRoute({ entity, book, period })}${context}`;
  }
  if (destination === "walkthrough") {
    const params = new URLSearchParams(context);
    params.set("f.actor", `is:${userId}`);
    return `/reports/audit-log?${params.toString()}`;
  }
  const path = { schedules: "/schedules", runs: "/reports/runs", audit: "/reports/audit-log" }[
    destination
  ];
  return `${path}${context}`;
}

export function AuditorRequests() {
  const location = useLocation();
  const navigate = useNavigate();
  const me = useMe();
  const access = useAccess();
  const definitions = useQuery({
    queryKey: reportDefinitionsKey(),
    queryFn: fetchReportDefinitions,
    retry: (count, error) => !isRefused(error) && count < 1,
  });
  const byCode = new Map((definitions.data ?? []).map((report) => [report.code, report]));
  const context = contextSearch(location.search, ["entity", "book", "period"]);
  const linkClass = "text-accent-fg underline";
  return (
    <section className="shrink-0 space-y-2" aria-labelledby="auditor-requests-title">
      <h2 id="auditor-requests-title" className="text-title-md">
        {t("evidence.requests.title")}
      </h2>
      {definitions.isError ? (
        <Banner
          tone="negative"
          title={t("evidence.requests.loadError")}
          actions={
            <Button onClick={() => void definitions.refetch()}>
              {t("evidence.requests.retry")}
            </Button>
          }
        />
      ) : null}
      <div className="max-h-80 overflow-auto rounded-md border border-hairline">
        <table data-testid="SF-09-grid-auditor-requests" className="w-full text-left text-body-sm">
          <caption className="sr-only">{t("evidence.requests.title")}</caption>
          <thead>
            <tr>
              {["request", "source", "action"].map((key) => (
                <th key={key} scope="col" className="p-3">
                  {t(`evidence.requests.${key}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {AUDITOR_REQUESTS.map((row) => {
              const reports = (row.reports ?? []).flatMap((code) => {
                const report = byCode.get(code);
                return report === undefined ? [] : [report];
              });
              const destination =
                row.destination === undefined
                  ? null
                  : requestDestination(row.destination, location.search, me.data?.user.id ?? "");
              const menu: MenuItem[] = reports.map((report) => ({
                id: report.code,
                label: report.name,
                onSelect: () => void navigate(`/reports/${report.code}${context}`),
              }));
              if (row.pack !== undefined && access.holdsAnywhere("evidence.export"))
                menu.push({
                  id: `pack-${row.pack}`,
                  label: t(`evidence.requests.generate${row.pack}`),
                  disabledReason: t("evidence.requests.packUnavailable"),
                  onSelect: () => undefined,
                });
              return (
                <tr
                  key={row.id}
                  data-testid={`SF-09-row-a-${row.id}`}
                  className="border-t border-hairline align-top"
                >
                  <th scope="row" className="p-3 font-normal">
                    <span className="font-mono">A-{row.id}</span>{" "}
                    {t(`evidence.requests.a${row.id}`)}
                  </th>
                  <td className="p-3">
                    {reports.map((report) => (
                      <p key={report.code}>{report.name}</p>
                    ))}
                    {row.destination === undefined ? null : (
                      <p>{t(`evidence.requests.${row.destination}`)}</p>
                    )}
                    {row.pack === undefined ? null : (
                      <p>{t(`evidence.requests.${row.pack.toLowerCase()}Source`)}</p>
                    )}
                    {row.outside ? <p>{t("evidence.requests.outside")}</p> : null}
                    {row.reports !== undefined && reports.length === 0 ? (
                      <p>
                        {t(
                          definitions.isPending
                            ? "evidence.requests.loading"
                            : "evidence.requests.unavailable",
                        )}
                      </p>
                    ) : null}
                  </td>
                  <td className="space-y-2 whitespace-nowrap p-3">
                    {row.outside ? (
                      <p className="max-w-64 whitespace-normal">
                        {t("evidence.requests.outsideNote")}
                      </p>
                    ) : null}
                    {destination === null ? (
                      row.destination === "reconciliation" ? (
                        <Button disabledReason={t("evidence.requests.selectContext")}>
                          {t("evidence.requests.open")}
                        </Button>
                      ) : null
                    ) : (
                      <p>
                        <Link className={linkClass} to={destination}>
                          {t("evidence.requests.open")}
                        </Link>
                      </p>
                    )}
                    {menu.length > 1 ? (
                      <Menu label={t("evidence.requests.run")} items={menu} />
                    ) : menu.length === 1 ? (
                      row.pack !== undefined && reports.length === 0 ? (
                        <Button disabledReason={t("evidence.requests.packUnavailable")}>
                          {menu[0]?.label}
                        </Button>
                      ) : (
                        <Link
                          className={linkClass}
                          to={`/reports/${reports[0]?.code ?? ""}${context}`}
                        >
                          {t("evidence.requests.run")}
                        </Link>
                      )
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
