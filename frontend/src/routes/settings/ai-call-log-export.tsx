// SF-15 call exports retain the submitting actor and are evaluated at execution time.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Banner } from "../../components/feedback/Banner";
import { JobProgress } from "../../components/feedback/JobProgress";
import { useToast } from "../../components/feedback/Toast";
import { DownloadSimple } from "../../components/icons/registry";
import { Menu } from "../../components/ui/Menu";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { isTerminal } from "../../lib/api/jobs";
import {
  EVERY_REPORT_RUN,
  fetchReportDefinition,
  fetchReportOutput,
  fetchReportRun,
  reportDefinitionKey,
  REPORT_RUN_ID_HEADER,
  REPORT_RUNS_PATH,
  type ReportDefinition,
} from "../../lib/api/queries/reports";
import { t } from "../../lib/i18n/t";

const CODE = "ai_call_log_export";
const label = (key: string) => t("settings.aiCallLog." + key);

export function CallLogExport() {
  const access = useAccess();
  const admin = access.holdsForAll("settings.manage");
  const allowed = admin
    ? access.holdsForAll("report.export")
    : access.holdsAnywhere("ai.use") && access.holdsAnywhere("report.export");
  const definition = useQuery({
    queryKey: reportDefinitionKey(CODE),
    queryFn: () => fetchReportDefinition(CODE),
    enabled: allowed,
  });
  if (!allowed) return null;
  if (definition.isError) {
    return (
      <Banner tone="negative" title={label("exportError")}>
        {definition.error.message}
      </Banner>
    );
  }
  return definition.data === undefined ? null : <ExportAction definition={definition.data} />;
}

interface Target {
  readonly runId: string;
  readonly jobId: string;
  readonly format: string;
}

function ExportAction({ definition }: { readonly definition: ReportDefinition }) {
  const toast = useToast();
  const command = useCommand({
    method: "POST",
    path: REPORT_RUNS_PATH,
    invalidates: [EVERY_REPORT_RUN],
  });
  const [target, setTarget] = useState<Target | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const locked = useRef(false);
  const active = useRef(true);
  const handled = useRef<string | null>(null);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  const { job, jobError, reset } = command;
  const runningLabel = t("reports.report.running", { name: definition.name });

  useEffect(() => {
    if (target === null) return;
    if (jobError !== null) {
      setError(jobError.message);
      setTarget(null);
      setBusy(false);
      locked.current = false;
      reset();
      return;
    }
    if (job?.id !== target.jobId || !isTerminal(job) || handled.current === job.id) return;
    handled.current = job.id;
    const finish = async () => {
      try {
        if (job.state !== "SUCCEEDED")
          throw new Error(t("common.job.failed", { label: runningLabel }));
        const run = await fetchReportRun(target.runId);
        if (!active.current) return;
        if (run.status !== "SUCCEEDED" || run.report.code !== CODE)
          throw new Error(label("exportUnexpected"));
        const blob = await fetchReportOutput(run.id);
        if (!active.current) return;
        const href = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = href;
        anchor.download = `ai-call-log-${run.id}.${target.format.toLowerCase()}`;
        document.body.append(anchor);
        anchor.click();
        anchor.remove();
        window.setTimeout(() => URL.revokeObjectURL(href), 0);
        toast.show({
          tone: "positive",
          message: t("reports.export.done", {
            name: definition.name,
            format: target.format,
            run: run.report_run_no,
          }),
        });
      } catch (failure) {
        if (active.current)
          setError(failure instanceof Error ? failure.message : label("exportError"));
      } finally {
        if (active.current) {
          setTarget(null);
          setBusy(false);
          locked.current = false;
        }
      }
    };
    void finish();
  }, [jobError, reset, definition.name, job, runningLabel, target, toast]);

  const choose = async (format: string) => {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setError(null);
    const outcome = await command.submit({
      report_code: CODE,
      parameters: {},
      output_format: format,
    });
    if (!active.current) return;
    if (outcome.kind === "accepted") {
      const runId = outcome.response.headers.get(REPORT_RUN_ID_HEADER);
      if (runId !== null) {
        setTarget({ runId, jobId: outcome.jobId, format });
        return;
      }
    }
    setError(outcome.kind === "failed" ? outcome.problem.message : label("exportUnexpected"));
    setBusy(false);
    locked.current = false;
    // Keep the command's idempotency key after a network failure for safe retries.
  };
  return (
    <span className="inline-flex flex-col gap-2">
      <span className="inline-flex items-center gap-3">
        {busy && job !== undefined && !isTerminal(job) ? (
          <JobProgress label={runningLabel} job={job} unit={t("reports.export.unit")} />
        ) : null}
        <Menu
          label={t("reports.export.label")}
          icon={DownloadSimple}
          align="end"
          items={definition.output_formats
            .filter((format) => format === "CSV" || format === "XLSX")
            .map((format) => ({
              id: format,
              label: format,
              disabledReason: busy ? label("exportBusy") : undefined,
              onSelect: () => {
                void choose(format);
              },
            }))}
        />
      </span>
      <span className="text-xs text-fg-2">{label("exportScope")}</span>
      {error !== null ? (
        <Banner tone="negative" title={label("exportError")}>
          {error}
        </Banner>
      ) : null}
    </span>
  );
}
