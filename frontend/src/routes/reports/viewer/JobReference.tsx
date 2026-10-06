// SCR-ST-12 "Reference <job id prefix>" of a failed run (SCREENS_B §0.5 RV-14 rev 1.7; DS-CMP-24): the run's
// own job (API-S-ReportRun `job_id`, 04 rev 1.17), else the job of the creation this mounted view started
// while that run is displayed (the rev 1.5 pair, L9-PLT plt-job-reference). One rule for SF-08:report,
// SF-06:entries and SF-04.
import type { ReportRun } from "../../../lib/api/queries/reports";
import { t } from "../../../lib/i18n/t";

/** The job the Reference line names, or null when neither the run nor this view knows one. */
export function jobReferenceOf(
  run: Pick<ReportRun, "job_id">,
  createdJobId: string | null,
): string | null {
  return run.job_id ?? createdJobId;
}

export interface JobReferenceProps {
  readonly run: Pick<ReportRun, "job_id">;
  /** The job of the creation this mounted view started, only while its run is displayed. */
  readonly createdJobId: string | null;
}

export function JobReference({ run, createdJobId }: JobReferenceProps) {
  const reference = jobReferenceOf(run, createdJobId);
  return reference === null ? null : (
    <p>{t("common.job.reference", { reference: reference.slice(0, 8) })}</p>
  );
}
