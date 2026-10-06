// RV-03 Run details (SCREENS_B §0.5; DESIGN_SYSTEM DS-CMP-09 docked panel; SCREENS SCR-URL-12
// `drawer=run-details`; CTL-029). Every API-S-ReportRun field: parameters (every key, including
// defaults), entity scope, `known_at`, `period_lock_id`, engine release, control totals, tie-out results,
// ledger heads, output format, SHA-256, manifest link, started and finished times and the problem.
// "Rerun from the same source" starts `POST /report-runs/{id}/rerun` and shows "Output identical: Yes"
// and "Control totals identical: Yes" from the job result. A rerun reads the stored source, so it is not an
// SCR-ST-10 command and stays while a lock snapshot is shown (D-88 L7-3-Q-2). A refused rerun is shown as
// any refused command is (DS-CMP-29; rev 1.101): the problem's title and every sentence of it — the API
// names the lock to pass in a finding alone where a run names a record that froze no dataset (S15-R-19).
import { useId } from "react";

import { Banner } from "../../../components/feedback/Banner";
import { JobProgress } from "../../../components/feedback/JobProgress";
import { RefusalBanner } from "../../../components/feedback/RefusalBanner";
import { Button } from "../../../components/ui/Button";
import { Drawer } from "../../../components/ui/Drawer";
import { chipFor, StatusChip } from "../../../components/ui/StatusChip";
import { useCommand } from "../../../lib/api/commands";
import { isTerminal } from "../../../lib/api/jobs";
import {
  EVERY_REPORT_RUN,
  REPORT_RUNS_PATH,
  type ReportRun,
} from "../../../lib/api/queries/reports";
import { formatTimestamp, NO_VALUE } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";
import { bookLabel } from "./RunStamp";
import { tieOutName } from "./specs";

/** A stored value as text; money strings stay strings (DG-FE-08). */
export function valueText(value: unknown): string {
  if (value === null || value === undefined) {
    return NO_VALUE;
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (
    Array.isArray(value) &&
    value.every((item) => typeof item === "string" || typeof item === "number")
  ) {
    return value.join(", ");
  }
  return JSON.stringify(value);
}

function Table({
  caption,
  rows,
}: {
  readonly caption: string;
  readonly rows: readonly (readonly [string, string])[];
}) {
  return (
    <table className="w-full text-body-sm">
      <caption className="mb-1 text-start text-title-sm text-fg-1">{caption}</caption>
      <tbody>
        {rows.map(([name, value]) => (
          <tr key={name} className="border-t border-hairline">
            <th
              scope="row"
              className="py-1 pe-3 text-start align-top font-mono text-mono-sm text-fg-2"
            >
              {name}
            </th>
            <td className="break-all py-1 text-fg-1">{value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function yesNo(value: unknown): string {
  return t(value === true ? "reports.runDetails.yes" : "reports.runDetails.no");
}

export interface RunDetailsDrawerProps {
  readonly run: ReportRun;
  readonly onClose: () => void;
  /** The SF id of the host screen. */
  readonly testIdPrefix?: string | undefined;
}

export function RunDetailsDrawer({ run, onClose, testIdPrefix = "SF-08" }: RunDetailsDrawerProps) {
  const resultId = useId();
  const rerun = useCommand({
    method: "POST",
    path: `${REPORT_RUNS_PATH}/${run.id}/rerun`,
    invalidates: [EVERY_REPORT_RUN],
  });
  const job = rerun.job;
  const done = job !== undefined && isTerminal(job) ? job : null;
  const status = chipFor("E-67", run.status);
  const output = run.output;
  return (
    <div data-testid={`${testIdPrefix}-drawer-run-details`} className="flex h-full">
      <Drawer open variant="docked" title={t("reports.runDetails.title")} onClose={onClose}>
        <div className="flex flex-col gap-4">
          <p className="flex items-center gap-2">
            <span className="font-mono text-mono-sm text-fg-1">{run.report_run_no}</span>
            {status === null ? null : (
              <StatusChip status={status.status} caption={status.caption} />
            )}
          </p>
          <Table
            caption={t("reports.runDetails.parameters")}
            rows={Object.entries(run.parameters).map(([key, value]) => [key, valueText(value)])}
          />
          <Table
            caption={t("reports.runDetails.source")}
            rows={[
              ["entity_scope", run.entity_scope.map((item) => item.code).join(", ") || NO_VALUE],
              ["book", bookLabel(run.book)],
              ["known_at", formatTimestamp(run.known_at)],
              ["period_lock_id", run.period_lock_id ?? NO_VALUE],
              [
                "engine_release",
                `${run.engine_release.engine_version} (${run.engine_release.build_sha.slice(0, 8)})`,
              ],
            ]}
          />
          <Table
            caption={t("reports.runDetails.controlTotals")}
            rows={Object.entries(run.control_totals ?? {}).map(([key, value]) => [
              key,
              valueText(value),
            ])}
          />
          <Table
            caption={t("reports.runDetails.tieOuts")}
            rows={run.tie_out_results.map((item) => [
              tieOutName(item.code),
              `${chipFor("T-RPT-02", item.result)?.status ?? item.result} · ${valueText(item.expected)} · ${valueText(item.actual)}`,
            ])}
          />
          <Table
            caption={t("reports.runDetails.ledgerHeads")}
            rows={Object.entries(run.ledger_heads).map(([key, value]) => [key, valueText(value)])}
          />
          <Table
            caption={t("reports.runDetails.output")}
            rows={[
              ["format", output?.format ?? NO_VALUE],
              ["sha256", output?.sha256 ?? NO_VALUE],
              ["manifest", output?.manifest_href ?? NO_VALUE],
              ["started_at", formatTimestamp(run.started_at)],
              ["finished_at", formatTimestamp(run.finished_at)],
            ]}
          />
          {output?.manifest_href === null || output?.manifest_href === undefined ? null : (
            <a href={output.manifest_href} className="text-body-sm text-accent-fg hover:underline">
              {t("reports.runDetails.manifest")}
            </a>
          )}
          {run.problem === null ? null : (
            <Banner tone="negative" title={run.problem.title} headingLevel={3} announce="static" />
          )}
          <div className="flex flex-col gap-2">
            <Button variant="secondary" loading={rerun.pending} onClick={() => void rerun.submit()}>
              {t("reports.runDetails.rerun")}
            </Button>
            {job !== undefined && !isTerminal(job) ? (
              <JobProgress
                label={t("reports.report.running", { name: run.report.name })}
                job={job}
                unit={t("reports.export.unit")}
              />
            ) : null}
            {done === null ? null : done.state === "SUCCEEDED" ? (
              <div id={resultId} role="status" data-testid={`${testIdPrefix}-banner-rerun-result`}>
                <p className="text-body-sm text-fg-1">
                  {t("reports.runDetails.outputIdentical", {
                    answer: yesNo(done.result?.output_sha256_equal),
                  })}
                </p>
                <p className="text-body-sm text-fg-1">
                  {t("reports.runDetails.totalsIdentical", {
                    answer: yesNo(done.result?.control_totals_equal),
                  })}
                </p>
              </div>
            ) : (
              <Banner
                tone="negative"
                headingLevel={3}
                title={t("common.job.failed", {
                  label: t("reports.report.running", { name: run.report.name }),
                })}
              />
            )}
            <RefusalBanner problem={rerun.problem} headingLevel={3} />
          </div>
        </div>
      </Drawer>
    </div>
  );
}
