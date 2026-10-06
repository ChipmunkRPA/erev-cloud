// Job polling (docs/dev-guide.md DG-FE-05; DESIGN_SYSTEM DS-CMP-24; 04 API-C-12): `GET /jobs/{id}`
// every 2 seconds until the job reaches a terminal state.
import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "./client";
import { queryKeys } from "./query-keys";
import type { components } from "./schema";

export type Job = components["schemas"]["JobOut"];
export type JobState = components["schemas"]["JobState"];

export const JOB_POLL_INTERVAL_MS = 2_000;

const TERMINAL_STATES: ReadonlySet<JobState> = new Set<JobState>([
  "SUCCEEDED",
  "SUCCEEDED_WITH_EXCEPTIONS",
  "FAILED",
  "CANCELLED",
]);

export function isTerminal(job: Job | undefined): boolean {
  return job !== undefined && TERMINAL_STATES.has(job.state);
}

/**
 * The job holds the summary of a dry run that this reader is not shown (04 API-S-Job `result` rev
 * 1.314; §16.10 "Who reads a stored preview"). The API answers the summary to a reader of the job who
 * holds the read permission of the dry run's subject for every entity the subject is bound to; to
 * every other reader, the job's initiator included, `result.summary` is null and
 * `result.summary_withheld` is true. The member is absent from every other result, so nothing but
 * `true` says it: one rule for every screen that reads a summary from a job.
 */
export function summaryWithheld(job: Pick<Job, "result"> | undefined): boolean {
  return job?.result?.summary_withheld === true;
}

export function fetchJob(jobId: string): Promise<Job> {
  return unwrap(api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: jobId } } }));
}

/** Polls a job while it runs; `null` keeps the query idle. */
export function useJob(jobId: string | null) {
  return useQuery({
    queryKey: queryKeys.job(jobId ?? ""),
    queryFn: () => fetchJob(jobId ?? ""),
    enabled: jobId !== null,
    refetchInterval: (query) => (isTerminal(query.state.data) ? false : JOB_POLL_INTERVAL_MS),
    refetchIntervalInBackground: true,
  });
}
