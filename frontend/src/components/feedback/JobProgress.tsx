// Job progress (DESIGN_SYSTEM DS-CMP-24; REQ-UX-021; SCREENS SCR-ST-12; SCREENS_B SB-R-06). Progress
// shows in place while a 202 job runs and nothing blocks the page. Completion is announced politely and
// failure assertively (DS-A11Y-08); a failed job leaves the negative banner "<job label> failed. Nothing
// was committed." with the problem title, the job reference and Retry where the command repeats.
import { type ReactNode, useEffect, useRef } from "react";

import { announce } from "../../lib/a11y/announce";
import type { Job, JobState } from "../../lib/api/jobs";
import { formatElapsed, formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { Button } from "../ui/Button";
import { Banner } from "./Banner";

export type JobProgressJob = Pick<Job, "id" | "state" | "progress" | "started_at" | "problem">;

export interface JobProgressProps {
  /** The SB-R-06 label, for example "Close run for US01 Sep 2026". */
  readonly label: string;
  readonly job: JobProgressJob;
  /** The plural noun of what the job counts, for example "contracts". */
  readonly unit: string;
  /** The result summary that replaces the indicator on success. */
  readonly summary?: ReactNode;
  readonly onRetry?: (() => void) | undefined;
  readonly onCancel?: (() => void) | undefined;
  /** The clock of the elapsed time, in epoch milliseconds (tests pass a fixed value). */
  readonly now?: number | undefined;
}

const TERMINAL: ReadonlySet<JobState> = new Set<JobState>([
  "SUCCEEDED",
  "SUCCEEDED_WITH_EXCEPTIONS",
  "FAILED",
  "CANCELLED",
]);

export function JobProgress({
  label,
  job,
  unit,
  summary,
  onRetry,
  onCancel,
  now,
}: JobProgressProps) {
  const previous = useRef<JobState>(job.state);
  useEffect(() => {
    const before = previous.current;
    previous.current = job.state;
    if (before === job.state || TERMINAL.has(before)) {
      return;
    }
    if (job.state === "FAILED") {
      announce(t("common.job.failed", { label }), "assertive");
    } else if (job.state === "CANCELLED") {
      announce(t("common.job.cancelled", { label }), "polite");
    } else if (TERMINAL.has(job.state)) {
      announce(t("common.job.succeeded", { label }), "polite");
    }
  }, [job.state, label]);

  if (job.state === "FAILED") {
    return (
      <Banner
        tone="negative"
        announce="static"
        title={t("common.job.failed", { label })}
        actions={
          onRetry === undefined ? undefined : (
            <Button variant="link" onClick={onRetry}>
              {t("common.job.retry")}
            </Button>
          )
        }
      >
        {job.problem === null ? null : <span>{job.problem.title} </span>}
        <span>{t("common.job.reference", { reference: job.id.slice(0, 8) })}</span>
      </Banner>
    );
  }
  if (job.state === "CANCELLED") {
    return <p className="text-body-sm text-fg-2">{t("common.job.cancelled", { label })}</p>;
  }
  if (TERMINAL.has(job.state)) {
    return summary === undefined ? null : <>{summary}</>;
  }

  const { done, total } = job.progress;
  const doneText = formatNumber(done, { kind: "count" });
  const totalText = total !== null && total > 0 ? formatNumber(total, { kind: "count" }) : null;
  const percent = total !== null && total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  const elapsed = job.started_at === null ? null : formatElapsed(job.started_at, now ?? Date.now());

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-body-sm font-medium text-fg-1">{label}</span>
        <span className="flex-1" />
        <span className="num text-body-sm text-fg-2">
          {totalText === null
            ? t("common.job.inProgress")
            : t("common.job.counts", { done: doneText, total: totalText })}
        </span>
        {elapsed === null ? null : <span className="num text-body-sm text-fg-3">{elapsed}</span>}
        {onCancel === undefined ? null : (
          <Button variant="ghost" size="sm" onClick={onCancel}>
            {t("common.job.cancel")}
          </Button>
        )}
      </div>
      {totalText === null ? (
        <div
          role="progressbar"
          aria-label={label}
          aria-valuetext={t("common.job.inProgress")}
          className="h-1 w-full overflow-hidden rounded-full bg-active"
        >
          <div className="h-full w-2/5 animate-progress-indeterminate bg-accent-solid" />
        </div>
      ) : (
        <div
          role="progressbar"
          aria-label={label}
          aria-valuemin={0}
          aria-valuemax={total ?? 0}
          aria-valuenow={done}
          aria-valuetext={t("common.job.valueText", { done: doneText, total: totalText, unit })}
          className="h-1 w-full overflow-hidden rounded-full bg-active"
        >
          <div className="h-full bg-accent-solid" style={{ inlineSize: `${String(percent)}%` }} />
        </div>
      )}
    </div>
  );
}
