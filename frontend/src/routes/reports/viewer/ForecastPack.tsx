import { useQuery } from "@tanstack/react-query";

import { Banner } from "../../../components/feedback/Banner";
import { Button } from "../../../components/ui/Button";
import { fetchForecastSections } from "../../../lib/api/queries/reports";
import { queryKey } from "../../../lib/api/query-keys";
import { t } from "../../../lib/i18n/t";
import { SectionTable } from "./DisclosurePack";

/** Forecast tables read only the selected saved run; opening a table pages its own dataset. */
export function ForecastPack({ runId }: { runId: string }) {
  const result = useQuery({
    queryKey: queryKey("report-runs", "tenant", { runId, forecastSections: true }),
    queryFn: () => fetchForecastSections(runId),
  });
  if (result.isError) return <Banner tone="negative" title={t("reports.report.dataLoadError")} actions={<Button variant="link" onClick={() => void result.refetch()}>{t("reports.report.retry")}</Button>} />;
  if (result.data === undefined) return <p role="status">{t("reports.disclosure.loading")}</p>;
  const header = result.data.forecast;
  const first = header?.horizon_periods[0];
  const last = header?.horizon_periods.at(-1);
  if (header == null || first === undefined || last === undefined) return <Banner tone="negative" title={t("reports.forecast.missingHeader")} />;
  return <div className="flex flex-col gap-6">
    <div className="text-body-sm text-fg-2">
      <p>{t("reports.forecast.scenario", { name: header.scenario_name })}</p>
      <p>{t("reports.forecast.eventSet", { name: header.event_set_name, version: header.event_set_version })}</p>
      <p>{t("reports.forecast.horizon", { first, last })}</p>
      <p>{t("reports.forecast.knownAt", { time: header.known_at })}</p>
    </div>
    {(result.data.sections ?? []).map(section => <section key={section.number} className="flex flex-col gap-2">
      <h2 className="text-heading-sm">{section.number}. {section.title}</h2>
      {section.tables.map(table => <SectionTable key={table.key} runId={runId} table={table} number={section.number} />)}
    </section>)}
  </div>;
}
