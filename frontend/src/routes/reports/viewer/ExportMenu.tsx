// RV-06 Exports (SCREENS_B §0.5, §5.2; DESIGN_SYSTEM DS-CMP-24, DS-CMP-28). The menu "Export"
// (DownloadSimple) lists only the definition's `output_formats`. Choosing one creates a run with the
// view's parameters and that `output_format` (permission `report.export`), shows the job indicator in
// the menu row and, on success, downloads `GET /report-runs/{id}/output` with the toast "Exported
// <report name> as <format>. Run <report run no>." and the action "Run details".
import { useEffect, useRef } from "react";

import { JobProgress } from "../../../components/feedback/JobProgress";
import { useToast } from "../../../components/feedback/Toast";
import { DownloadSimple } from "../../../components/icons/registry";
import { Menu } from "../../../components/ui/Menu";
import { useCommand } from "../../../lib/api/commands";
import { isTerminal } from "../../../lib/api/jobs";
import {
  EVERY_REPORT_RUN,
  fetchReportRun,
  REPORT_RUN_ID_HEADER,
  REPORT_RUNS_PATH,
  type ReportDefinition,
  reportOutputHref,
} from "../../../lib/api/queries/reports";
import { t } from "../../../lib/i18n/t";
import { formatLabel } from "./specs";

export interface ExportMenuProps {
  readonly definition: ReportDefinition;
  /** The parameters of the run on screen (RV-06 "the same parameters"). */
  readonly parameters: Readonly<Record<string, unknown>>;
  /** Opens the run record of an export. */
  readonly onDetails: (runId: string) => void;
}

interface Target {
  readonly runId: string;
  readonly format: string;
}

export function ExportMenu({ definition, parameters, onDetails }: ExportMenuProps) {
  const toast = useToast();
  const command = useCommand({
    method: "POST",
    path: REPORT_RUNS_PATH,
    invalidates: [EVERY_REPORT_RUN],
  });
  const target = useRef<Target | null>(null);
  const handled = useRef<string | null>(null);
  const job = command.job;
  const label = t("reports.report.running", { name: definition.name });

  useEffect(() => {
    const current = target.current;
    if (job === undefined || !isTerminal(job) || current === null || handled.current === job.id) {
      return;
    }
    handled.current = job.id;
    target.current = null;
    if (job.state === "FAILED" || job.state === "CANCELLED") {
      toast.show({ tone: "negative", message: t("common.job.failed", { label }) });
      return;
    }
    void fetchReportRun(current.runId).then((run) => {
      window.location.assign(reportOutputHref(run.id));
      toast.show({
        tone: "positive",
        message: t("reports.export.done", {
          name: definition.name,
          format: formatLabel(current.format),
          run: run.report_run_no,
        }),
        action: { label: t("reports.report.runDetails"), onAction: () => onDetails(run.id) },
      });
    });
  }, [definition.name, job, label, onDetails, toast]);

  const choose = async (format: string) => {
    const outcome = await command.submit({
      report_code: definition.code,
      parameters,
      output_format: format,
    });
    if (outcome.kind === "accepted") {
      const runId = outcome.response.headers.get(REPORT_RUN_ID_HEADER);
      if (runId !== null) {
        target.current = { runId, format };
      }
    } else if (outcome.kind === "failed") {
      toast.show({ tone: "negative", message: outcome.problem.title });
    }
  };

  const running = job !== undefined && !isTerminal(job);
  return (
    <span className="inline-flex items-center gap-3">
      {running ? <JobProgress label={label} job={job} unit={t("reports.export.unit")} /> : null}
      <Menu
        label={t("reports.export.label")}
        icon={DownloadSimple}
        align="end"
        items={definition.output_formats.map((format) => ({
          id: format,
          label: formatLabel(format),
          onSelect: () => void choose(format),
        }))}
      />
    </span>
  );
}
