import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { JobProgress } from "../../components/feedback/JobProgress";
import { Button } from "../../components/ui/Button";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import {
  fetchForecastInputs,
  fetchForecastRuns,
  forecastInputsKey,
  forecastRunsKey,
  type ForecastRequest,
  type ForecastRun,
} from "../../lib/api/queries/forecasts";
import { useMe } from "../../lib/api/queries/me";
import { fetchReportRun, reportRunKey, reportRunRoute } from "../../lib/api/queries/reports";
import {
  entitiesKey,
  fetchActiveEntities,
  fetchPeriods,
  type Period,
} from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import { t } from "../../lib/i18n/t";
import { ReportsHeader } from "./frame";
import { ForecastComparisonForm } from "./ForecastComparisonForm";
import { ForecastPack } from "./viewer/ForecastPack";

type Format = "JSON" | "XLSX" | "CSV";

function Output({ id }: { id: string }) {
  const access = useAccess();
  const [open, setOpen] = useState(false);
  const report = useQuery({ queryKey: reportRunKey(id), queryFn: () => fetchReportRun(id) });
  const canPreview =
    report.data?.status === "SUCCEEDED" &&
    (report.data.output?.format === "JSON" ||
      (report.data.output != null &&
        ["CSV", "XLSX"].includes(report.data.output.format) &&
        access.holdsForEvery("report.export", report.data.entity_scope)));
  return (
    <div className="flex flex-col gap-2">
      {report.isError && (
        <Banner
          tone="negative"
          title={t("reports.report.dataLoadError")}
          actions={
            <Button
              variant="link"
              onClick={() => {
                void report.refetch();
              }}
            >
              {t("reports.report.retry")}
            </Button>
          }
        />
      )}
      <Link to={reportRunRoute(id)} className="underline">
        {report.data?.output?.format ?? t("reports.forecasts.output")} —{" "}
        {report.data?.report_run_no ?? id}
      </Link>
      {canPreview && (
        <Button variant="secondary" onClick={() => setOpen(!open)}>
          {t(open ? "reports.forecasts.hide" : "reports.forecasts.view")}
        </Button>
      )}
      {open && canPreview && <ForecastPack runId={id} />}
    </div>
  );
}

function CompareSavedForecast({ run }: { run: ForecastRun }) {
  const [open, setOpen] = useState(false);
  const access = useAccess();
  if (
    run.status !== "SUCCEEDED" ||
    !access.holdsForEvery(
      "report.run",
      run.parameters.entity_ids.map((id) => ({ id })),
    )
  )
    return null;
  return open ? (
    <ForecastComparisonForm initialForecast={run} />
  ) : (
    <Button variant="secondary" onClick={() => setOpen(true)}>
      {t("reports.comparison.title")}
    </Button>
  );
}

export function ForecastRunsPage() {
  const me = useMe();
  const access = useAccess();
  const tenant = me.data?.memberships.find(
    (m) => m.membership_id === me.data?.active_membership_id,
  )?.tenant;
  const enabled = tenant?.kind === "sandbox" && access.holdsForAll("scenario.use");
  const [input, setInput] = useState("");
  const [entityIds, setEntityIds] = useState<string[]>([]);
  const [book, setBook] = useState<"ASC606" | "IFRS15">("ASC606");
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [currency, setCurrency] = useState<"transaction" | "functional">("transaction");
  const [networkError, setNetworkError] = useState(false);
  const [formats, setFormats] = useState<Format[]>(["JSON"]);
  const [cursor, setCursor] = useState<string | null>(null);
  const inputs = useQuery({ queryKey: forecastInputsKey, queryFn: fetchForecastInputs, enabled });
  const entities = useQuery({ queryKey: entitiesKey(), queryFn: fetchActiveEntities, enabled });
  const available = (entities.data ?? []).filter(
    (e) => access.holds("report.run", e) && access.holds("config.read", e),
  );
  const selected = available.filter((e) => entityIds.includes(e.id));
  const periods = useQuery({
    queryKey: queryKey("forecast-periods", "tenant", {
      entityIds: selected.map((e) => e.id).join(","),
      book,
    }),
    queryFn: () =>
      Promise.all(selected.map((entity) => fetchPeriods({ entity: entity.code, book }))),
    enabled: enabled && selected.length > 0,
  });
  const calendar: readonly Period[] = periods.data?.[0] ?? [];
  const common = calendar.filter((p) =>
    periods.data?.every((rows) => rows.some((r) => r.period.period_key === p.period.period_key)),
  );
  const start = common.findIndex((p) => p.period.period_key === first);
  const end = common.findIndex((p) => p.period.period_key === last);
  const horizon =
    start >= 0 && end >= start ? common.slice(start, end + 1).map((p) => p.period.period_key) : [];
  const canExport = selected.length > 0 && access.holdsForEvery("report.export", selected);
  const runs = useQuery({
    queryKey: [...forecastRunsKey, { cursor }],
    queryFn: () => fetchForecastRuns(cursor),
    enabled,
    refetchInterval: (query) =>
      query.state.data?.items.some((r) => r.status === "QUEUED" || r.status === "RUNNING")
        ? 2000
        : false,
  });
  const command = useCommand({
    method: "POST",
    path: "/api/v1/forecast-runs",
    invalidates: [forecastRunsKey, queryKey("forecast-comparison-runs", "tenant")],
  });
  const cancel = useCommand({
    method: "POST",
    path: `/api/v1/jobs/${command.jobId ?? ""}/cancel`,
    invalidates: [forecastRunsKey, queryKey("forecast-comparison-runs", "tenant")],
  });
  const running =
    command.pending || command.job?.state === "QUEUED" || command.job?.state === "RUNNING";
  const continuous =
    horizon.length > 0 &&
    periods.data?.every((rows) => {
      const begin = rows.findIndex((r) => r.period.period_key === first);
      const finish = rows.findIndex((r) => r.period.period_key === last);
      return (
        begin >= 0 &&
        finish >= begin &&
        rows
          .slice(begin, finish + 1)
          .map((r) => r.period.period_key)
          .join(",") === horizon.join(",")
      );
    });
  const valid =
    continuous &&
    selected.length === entityIds.length &&
    selected.length > 0 &&
    horizon.length > 0 &&
    formats.length > 0 &&
    inputs.data?.some((i) => i.id === input) &&
    (canExport || formats.every((f) => f === "JSON"));
  const resetRange = () => {
    setFirst("");
    setLast("");
  };
  const submit = async () => {
    if (!valid || running) return;
    setNetworkError(false);
    const body: ForecastRequest = {
      forecast_event_set_id: input,
      parameters: {
        entity_ids: entityIds,
        horizon_periods: horizon,
        book_code: book,
        currency_view: currency,
        output_formats: formats,
      },
    };
    const outcome = await command.submit(body);
    setNetworkError(outcome.kind === "network-error");
    setCursor(null);
    void runs.refetch();
  };
  return (
    <div className="flex flex-col gap-6">
      <ReportsHeader />
      <h2 className="text-heading-md">{t("reports.forecasts.title")}</h2>
      {!enabled ? (
        <p>{t("reports.forecasts.scenarioOnly")}</p>
      ) : (
        <>
          {(inputs.isError || entities.isError || periods.isError || runs.isError) && (
            <Banner
              tone="negative"
              title={t("reports.report.dataLoadError")}
              actions={
                <Button
                  variant="link"
                  onClick={() => {
                    void inputs.refetch();
                    void entities.refetch();
                    if (selected.length) void periods.refetch();
                    void runs.refetch();
                  }}
                >
                  {t("reports.report.retry")}
                </Button>
              }
            />
          )}
          {(networkError || command.jobError) && (
            <Banner tone="negative" title={t("reports.forecasts.connectionError")} />
          )}
          <RefusalBanner problem={cancel.problem} />
          {(inputs.isPending || entities.isPending || runs.isPending) && (
            <p role="status">{t("reports.forecasts.loading")}</p>
          )}
          {entities.isSuccess && available.length === 0 && (
            <p>{t("reports.forecasts.noEntities")}</p>
          )}
          <form
            className="flex flex-col gap-4 rounded border border-stroke-1 p-4"
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            <label>
              {t("reports.forecasts.input")}
              <select
                value={input}
                onChange={(e) => setInput(e.target.value)}
                className="ml-2 rounded border p-2"
                required
              >
                <option value="">{t("reports.forecasts.choose")}</option>
                {inputs.data?.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.name} v{i.version_no}
                  </option>
                ))}
              </select>
            </label>
            {inputs.data?.length === 0 && <p>{t("reports.forecasts.noInputs")}</p>}
            <fieldset>
              <legend>{t("reports.forecasts.entities")}</legend>
              {available.map((e) => (
                <label key={e.id} className="mr-4 inline-flex gap-2">
                  <input
                    type="checkbox"
                    checked={entityIds.includes(e.id)}
                    onChange={(event) => {
                      setEntityIds(
                        event.target.checked
                          ? [...entityIds, e.id]
                          : entityIds.filter((id) => id !== e.id),
                      );
                      resetRange();
                    }}
                  />
                  {e.code}
                </label>
              ))}
            </fieldset>
            <label>
              {t("reports.forecasts.book")}
              <select
                className="ml-2 rounded border p-2"
                value={book}
                onChange={(e) => {
                  setBook(e.target.value === "IFRS15" ? "IFRS15" : "ASC606");
                  resetRange();
                }}
              >
                <option value="ASC606">ASC606</option>
                <option value="IFRS15">IFRS15</option>
              </select>
            </label>
            {(["first", "last"] as const).map((side) => (
              <label key={side}>
                {t(`reports.forecasts.${side}`)}
                <select
                  className="ml-2 rounded border p-2"
                  value={side === "first" ? first : last}
                  onChange={(e) => (side === "first" ? setFirst : setLast)(e.target.value)}
                  required
                  disabled={periods.isFetching || selected.length === 0}
                >
                  <option value="">{t("reports.forecasts.choose")}</option>
                  {common.map((p) => (
                    <option key={p.period.period_key} value={p.period.period_key}>
                      {p.period.name}
                    </option>
                  ))}
                </select>
              </label>
            ))}
            <label>
              {t("reports.forecasts.currency")}
              <select
                className="ml-2 rounded border p-2"
                value={currency}
                onChange={(e) =>
                  setCurrency(e.target.value === "functional" ? "functional" : "transaction")
                }
              >
                <option value="transaction">{t("reports.forecasts.transaction")}</option>
                <option value="functional">{t("reports.forecasts.functional")}</option>
              </select>
            </label>
            <fieldset>
              <legend>{t("reports.forecasts.formats")}</legend>
              {(["JSON", "XLSX", "CSV"] as const).map((format) => (
                <label key={format} className="mr-4 inline-flex gap-2">
                  <input
                    type="checkbox"
                    checked={formats.includes(format)}
                    disabled={format !== "JSON" && !canExport}
                    onChange={(e) =>
                      setFormats(
                        e.target.checked
                          ? [...formats, format]
                          : formats.filter((f) => f !== format),
                      )
                    }
                  />
                  {format}
                </label>
              ))}
            </fieldset>
            <p className="text-body-sm text-fg-2">{t("reports.forecasts.basis")}</p>
            <RefusalBanner problem={command.problem} />
            <Button
              type="submit"
              loading={running}
              disabledReason={!valid ? t("reports.forecasts.complete") : undefined}
            >
              {t("reports.forecasts.run")}
            </Button>
          </form>
          {command.job && (
            <JobProgress
              job={command.job}
              label={t("reports.forecasts.title")}
              unit={t("reports.forecasts.groups")}
              onCancel={
                running && !cancel.pending
                  ? () => {
                      void cancel.submit();
                    }
                  : undefined
              }
            />
          )}
          <ForecastComparisonForm key={me.data?.active_membership_id} />
          <h2 className="text-heading-sm">{t("reports.forecasts.history")}</h2>
          {runs.data?.items.length === 0 && <p>{t("reports.forecasts.noRuns")}</p>}
          {runs.data?.items.map((run) => (
            <section
              key={run.id}
              className="flex flex-col gap-3 rounded border border-stroke-1 p-4"
            >
              <h3>
                {run.parameters.horizon_periods.join(" · ")} — {run.status}
              </h3>
              <p>{run.created_at}</p>
              {run.problem && (
                <Banner
                  tone="negative"
                  title={String(run.problem.title ?? run.problem.detail ?? run.status)}
                />
              )}
              <CompareSavedForecast run={run} />
              {run.report_run_ids.map((id) => (
                <Output key={id} id={id} />
              ))}
            </section>
          ))}
          <div className="flex gap-2">
            {cursor && (
              <Button variant="secondary" onClick={() => setCursor(null)}>
                {t("reports.forecasts.latest")}
              </Button>
            )}
            {runs.data?.nextCursor && (
              <Button variant="secondary" onClick={() => setCursor(runs.data?.nextCursor ?? null)}>
                {t("reports.forecasts.older")}
              </Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
