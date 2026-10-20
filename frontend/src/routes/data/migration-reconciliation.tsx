import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { JobProgress } from "../../components/feedback/JobProgress";
import { Button } from "../../components/ui/Button";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { isTerminal, useJob } from "../../lib/api/jobs";
import { EVERY_MIGRATION, MIGRATIONS_PATH, type Migration } from "../../lib/api/queries/migrations";
import { reportRunRoute } from "../../lib/api/queries/reports";
import { t } from "../../lib/i18n/t";

/** The reconciliation command uses retained migration evidence; reports open with this batch pinned. */
export function MigrationReconciliation({ migration }: { readonly migration: Migration }) {
  const access = useAccess();
  const cache = useQueryClient();
  const [networkError, setNetworkError] = useState(false);
  const command = useCommand({
    method: "POST",
    path: `${MIGRATIONS_PATH}/${encodeURIComponent(migration.id)}/reconcile`,
    invalidates: [EVERY_MIGRATION],
  });
  const jobId = command.jobId ?? migration.job_id;
  const savedJob = useJob(jobId);
  const job = command.job ?? savedJob.data;
  const terminal = isTerminal(job);
  useEffect(() => {
    if (terminal) void cache.invalidateQueries({ queryKey: EVERY_MIGRATION });
  }, [cache, jobId, terminal]);
  // A stored import job may still be loading. Resolve it before offering another operation.
  const busy =
    command.pending ||
    (jobId !== null && !terminal) ||
    (job?.kind === "MIGRATION_RECONCILE" &&
      ["SUCCEEDED", "SUCCEEDED_WITH_EXCEPTIONS"].includes(job.state));
  const ready = migration.status === "IMPORTED";
  const reconciled = ["RECONCILED", "SUBMITTED", "PROMOTED"].includes(migration.status);
  const problem = command.problem?.detail ?? command.banner;
  const reportSearch = new URLSearchParams({ "p.migration_id": migration.id });
  const run = async () => {
    if (!ready || busy) return;
    setNetworkError(false);
    const result = await command.submit();
    setNetworkError(result.kind === "network-error");
  };
  return (
    <section aria-label={t("data.migrations.step.reconciliation")} className="flex flex-col gap-4">
      <p>
        {t(
          reconciled
            ? "data.migrations.reconcile.complete"
            : ready
              ? "data.migrations.reconcile.ready"
              : "data.migrations.reconcile.wait",
        )}
      </p>
      {problem || networkError ? (
        <Banner tone="negative" title={t("data.migrations.reconcile.error")}>
          {problem ?? t("data.migrations.reconcile.network")}
        </Banner>
      ) : null}
      {savedJob.isError || command.jobError ? (
        <Banner
          tone="negative"
          title={t("data.migrations.reconcile.jobError")}
          actions={<Button onClick={() => void savedJob.refetch()}>{t("common.job.retry")}</Button>}
        />
      ) : null}
      {job?.kind === "MIGRATION_RECONCILE" ? (
        <JobProgress label={t("data.migrations.reconcile.running")} job={job} unit="" />
      ) : null}
      {ready ? (
        <Button
          variant="primary"
          loading={busy}
          disabledReason={busy ? t("data.migrations.reconcile.running") : undefined}
          onClick={() => void run()}
        >
          {t("data.migrations.reconcile.run")}
        </Button>
      ) : null}
      {access.holdsForAll("report.run") && (ready || reconciled) ? (
        <div className="flex flex-wrap gap-4">
          {reconciled ? (
            <Link
              to={
                migration.reconciliation_report_run_id
                  ? reportRunRoute(migration.reconciliation_report_run_id)
                  : `/reports/migration_reconciliation?${reportSearch.toString()}`
              }
            >
              {t("data.migrations.reconcile.report")}
            </Link>
          ) : null}
          <Link to={`/reports/parallel_run_comparison?${reportSearch.toString()}`}>
            {t("data.migrations.reconcile.parallel")}
          </Link>
        </div>
      ) : null}
    </section>
  );
}
