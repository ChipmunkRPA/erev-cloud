import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { JobProgress } from "../../components/feedback/JobProgress";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Button } from "../../components/ui/Button";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { fetchComparisonForecasts, type ForecastRun } from "../../lib/api/queries/forecasts";
import { reportRunRoute } from "../../lib/api/queries/reports";
import { entitiesKey, fetchActiveEntities } from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import { t } from "../../lib/i18n/t";

export function ForecastComparisonForm({ initialForecast }: { initialForecast?: ForecastRun }) {
  const access = useAccess();
  const [cursor, setCursor] = useState<string | null>(null);
  const [selection, setSelected] = useState<ForecastRun | null | undefined>(initialForecast);
  const [firstChoice, setFirst] = useState<string | undefined>();
  const [lastChoice, setLast] = useState<string | undefined>();
  const [dimension, setDimension] = useState("CONTRACT");
  const [format, setFormat] = useState("JSON");
  const [networkError, setNetworkError] = useState(false);
  const choices = useQuery({
    queryKey: queryKey("forecast-comparison-runs", "tenant", { cursor }),
    queryFn: () => fetchComparisonForecasts(cursor),
  });
  const entities = useQuery({ queryKey: entitiesKey(), queryFn: fetchActiveEntities });
  const command = useCommand({ method: "POST", path: "/api/v1/report-runs" });
  const cancel = useCommand({ method: "POST", path: `/api/v1/jobs/${command.jobId ?? ""}/cancel` });
  const selected = selection === undefined ? (choices.data?.items[0] ?? null) : selection;
  const horizon = selected?.parameters.horizon_periods ?? [];
  const first = firstChoice ?? horizon[0] ?? "";
  const last = lastChoice ?? horizon.at(-1) ?? "";
  const scope = (entities.data ?? []).filter((e) => selected?.parameters.entity_ids.includes(e.id));
  const canExport = scope.length > 0 && access.holdsForEvery("report.export", scope);
  const running =
    command.pending || command.job?.state === "QUEUED" || command.job?.state === "RUNNING";
  const valid =
    selected !== null &&
    scope.length === selected.parameters.entity_ids.length &&
    scope.length > 0 &&
    access.holdsForEvery("report.run", scope) &&
    horizon.includes(first) &&
    horizon.indexOf(last) >= horizon.indexOf(first) &&
    (format === "JSON" || canExport);
  const items = [...(choices.data?.items ?? [])];
  if (selected && !items.some((r) => r.id === selected.id)) items.unshift(selected);
  const outputId = command.job?.state === "SUCCEEDED" ? command.job.result?.report_run_id : null;
  async function submit() {
    if (!valid || running || selected === null) return;
    setSelected(selected);
    setNetworkError(false);
    const outcome = await command.submit({
      report_code: "actual_vs_forecast",
      output_format: format,
      parameters: {
        forecast_run_id: selected.id,
        entity_codes: scope.map((e) => e.code),
        row_dimension: dimension,
        from_period_key: first,
        to_period_key: last,
        currency_view: selected.parameters.currency_view,
      },
    });
    setNetworkError(outcome.kind === "network-error");
  }
  return (
    <section className="flex flex-col gap-4 rounded border border-stroke-1 p-4">
      <h3 className="text-heading-sm">{t("reports.comparison.title")}</h3>
      <p>{t("reports.comparison.basis")}</p>
      {(choices.isError || entities.isError) && (
        <Banner
          tone="negative"
          title={t("reports.report.dataLoadError")}
          actions={
            <Button
              variant="link"
              onClick={() => {
                setCursor(null);
                void choices.refetch();
                void entities.refetch();
              }}
            >
              {t("reports.report.retry")}
            </Button>
          }
        />
      )}
      {choices.isPending && <p role="status">{t("reports.forecasts.loading")}</p>}
      {choices.data?.items.length === 0 && !cursor && <p>{t("reports.comparison.empty")}</p>}
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <label>
          {t("reports.comparison.forecast")}
          <select
            className="ml-2 rounded border p-2"
            value={selected?.id ?? ""}
            onChange={(e) => {
              const run = items.find((r) => r.id === e.target.value) ?? null;
              setSelected(run);
              setFirst(run?.parameters.horizon_periods[0] ?? "");
              setLast(run?.parameters.horizon_periods.at(-1) ?? "");
            }}
          >
            <option value="">{t("reports.forecasts.choose")}</option>
            {items.map((run) => (
              <option key={run.id} value={run.id}>
                {run.created_at} · {run.parameters.book_code} ·{" "}
                {run.parameters.horizon_periods.join(" / ")} · {run.id.slice(-8)}
              </option>
            ))}
          </select>
        </label>
        <div className="flex gap-2">
          {cursor && (
            <Button
              variant="secondary"
              onClick={() => {
                setSelected(selected);
                setCursor(null);
              }}
            >
              {t("reports.forecasts.latest")}
            </Button>
          )}
          {choices.data?.nextCursor && (
            <Button
              variant="secondary"
              onClick={() => {
                setSelected(selected);
                setCursor(choices.data?.nextCursor ?? null);
              }}
            >
              {t("reports.forecasts.older")}
            </Button>
          )}
        </div>
        <label>
          {t("reports.comparison.dimension")}
          <select
            className="ml-2 rounded border p-2"
            value={dimension}
            onChange={(e) => {
              setSelected(selected);
              setDimension(e.target.value);
            }}
          >
            <option value="CONTRACT">{t("reports.comparison.contract")}</option>
            <option value="REVENUE_CATEGORY">{t("reports.comparison.category")}</option>
          </select>
        </label>
        {(["first", "last"] as const).map((side) => (
          <label key={side}>
            {t(`reports.forecasts.${side}`)}
            <select
              className="ml-2 rounded border p-2"
              value={side === "first" ? first : last}
              onChange={(e) => {
                setSelected(selected);
                (side === "first" ? setFirst : setLast)(e.target.value);
              }}
            >
              <option value="">{t("reports.forecasts.choose")}</option>
              {horizon.map((key) => (
                <option key={key} value={key}>
                  {key}
                </option>
              ))}
            </select>
          </label>
        ))}
        <label>
          {t("reports.comparison.format")}
          <select
            className="ml-2 rounded border p-2"
            value={format}
            onChange={(e) => {
              setSelected(selected);
              setFormat(e.target.value);
            }}
          >
            {["JSON", "XLSX", "CSV", "PDF"].map((value) => (
              <option key={value} value={value} disabled={value !== "JSON" && !canExport}>
                {value}
              </option>
            ))}
          </select>
        </label>
        {selected && (
          <p>
            {selected.parameters.book_code} ·{" "}
            {t(
              selected.parameters.currency_view === "functional"
                ? "reports.forecasts.functional"
                : "reports.forecasts.transaction",
            )}
          </p>
        )}
        <RefusalBanner problem={command.problem} />
        <RefusalBanner problem={cancel.problem} />
        {(networkError || command.jobError) && (
          <Banner tone="negative" title={t("reports.forecasts.connectionError")} />
        )}
        <Button
          type="submit"
          loading={running}
          disabledReason={!valid ? t("reports.forecasts.complete") : undefined}
        >
          {t("reports.comparison.run")}
        </Button>
      </form>
      {command.job && (
        <JobProgress
          job={command.job}
          label={t("reports.comparison.title")}
          unit={t("reports.comparison.rows")}
          onCancel={
            running && !cancel.pending
              ? () => {
                  void cancel.submit();
                }
              : undefined
          }
        />
      )}
      {typeof outputId === "string" && (
        <Link className="underline" to={reportRunRoute(outputId)}>
          {t("reports.comparison.open")}
        </Link>
      )}
    </section>
  );
}
