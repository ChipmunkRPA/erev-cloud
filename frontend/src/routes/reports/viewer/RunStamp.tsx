// RV-02 Run stamp (SCREENS_B §0.5; DESIGN_SYSTEM DS-CMP-06 meta row, DS-FMT-16, DS-FMT-17, DS-FMT-23).
// Directly under the report `h1`, a `dl` of: Report `<name> v<version>`; Run `<report run no>` (mono,
// copy); Entity; Book; As of; Source "As locked on <timestamp>" or "Current, known at <timestamp>";
// Engine `<engine_version>` with the first 8 characters of `build_sha` in a tooltip; Run by; Run at;
// Rows; Output SHA-256 as its first 8 and last 4 characters (copy). The run number, run time and hash
// carry `data-volatile`, which screenshots mask (DG-E2E-06).
import type { ReactNode } from "react";

import { CopySimple } from "../../../components/icons/registry";
import { Button } from "../../../components/ui/Button";
import { Tooltip } from "../../../components/ui/Tooltip";
import { announce } from "../../../lib/a11y/announce";
import type { ReportRun } from "../../../lib/api/queries/reports";
import { formatDate, formatNumber, formatTimestamp, NO_VALUE } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";

/** DS-FMT-23: the first 8 and last 4 characters of a hash. */
export function hashPrefix(value: string): string {
  return value.length <= 12 ? value : `${value.slice(0, 8)}…${value.slice(-4)}`;
}

/**
 * The run's as-of date: API-S-ReportRun `as_of`, else the single control total `as_of` of reports that
 * resolve it from `period_key` (`rpo`; D-87 L6-3-Q-26).
 */
export function runAsOf(run: Pick<ReportRun, "as_of" | "control_totals">): string | null {
  if (run.as_of !== null) {
    return run.as_of;
  }
  const total = run.control_totals?.as_of;
  return typeof total === "string" && /^\d{4}-\d{2}-\d{2}$/.test(total) ? total : null;
}

export function bookLabel(code: string | null): string {
  return code === "ASC606" || code === "IFRS15" || code === "LEGACY"
    ? t(`shell.context.books.${code}`)
    : (code ?? NO_VALUE);
}

function CopyButton({ value, label }: { readonly value: string; readonly label: string }) {
  return (
    <Button
      variant="ghost"
      size="sm"
      icon={CopySimple}
      aria-label={label}
      onClick={() => {
        void navigator.clipboard
          .writeText(value)
          .then(() => announce(t("reports.stamp.copied"), "polite"));
      }}
    />
  );
}

interface Item {
  readonly id: string;
  readonly label: string;
  readonly value: ReactNode;
  readonly volatile?: boolean;
}

export interface RunStampProps {
  readonly run: ReportRun;
  /** The `created_at` of the run's period lock, when the screen knows it. */
  readonly lockCreatedAt: string | null;
  /** The SF id of the host screen: `<SF id>-run-stamp` (RV-02). */
  readonly testIdPrefix?: string | undefined;
}

export function RunStamp({ run, lockCreatedAt, testIdPrefix = "SF-08" }: RunStampProps) {
  const sha = run.output?.sha256 ?? null;
  const runAt = run.started_at ?? run.finished_at;
  const asOf = runAsOf(run);
  const source =
    run.period_lock_id === null
      ? t("reports.stamp.current", { at: formatTimestamp(run.known_at) })
      : lockCreatedAt === null
        ? t("reports.stamp.asLockedUnknown")
        : t("reports.stamp.asLocked", { at: formatTimestamp(lockCreatedAt) });
  const items: readonly Item[] = [
    {
      id: "report",
      label: t("reports.stamp.report"),
      value: t("reports.stamp.reportValue", { name: run.report.name, version: run.report.version }),
    },
    {
      id: "run",
      label: t("reports.stamp.run"),
      volatile: true,
      value: (
        <span className="inline-flex items-center gap-1">
          <span className="font-mono text-mono-sm text-fg-1">{run.report_run_no}</span>
          <CopyButton value={run.report_run_no} label={t("reports.stamp.copyRun")} />
        </span>
      ),
    },
    {
      id: "entity",
      label: t("reports.stamp.entity"),
      value:
        run.entity_scope.length === 0
          ? NO_VALUE
          : run.entity_scope.map((item) => item.code).join(", "),
    },
    { id: "book", label: t("reports.stamp.book"), value: bookLabel(run.book) },
    {
      id: "asOf",
      label: t("reports.stamp.asOf"),
      value: asOf === null ? NO_VALUE : formatDate(asOf),
    },
    { id: "source", label: t("reports.stamp.source"), value: source },
    {
      id: "engine",
      label: t("reports.stamp.engine"),
      value: (
        <Tooltip
          content={t("reports.stamp.build", { sha: run.engine_release.build_sha.slice(0, 8) })}
        >
          {(trigger) => (
            <span
              {...trigger}
              // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- DS-CMP-27: a tooltip trigger is focusable
              tabIndex={0}
              className="font-mono text-mono-sm text-fg-1"
            >
              {run.engine_release.engine_version}
            </span>
          )}
        </Tooltip>
      ),
    },
    { id: "runBy", label: t("reports.stamp.runBy"), value: run.run_by.display_name },
    {
      id: "runAt",
      label: t("reports.stamp.runAt"),
      volatile: true,
      value: formatTimestamp(runAt),
    },
    {
      id: "rows",
      label: t("reports.stamp.rows"),
      value: run.row_count === null ? NO_VALUE : formatNumber(run.row_count, { kind: "count" }),
    },
    {
      id: "sha",
      label: t("reports.stamp.sha"),
      volatile: true,
      value:
        sha === null ? (
          NO_VALUE
        ) : (
          <span className="inline-flex items-center gap-1">
            <span aria-hidden="true" className="font-mono text-mono-sm text-fg-1">
              {hashPrefix(sha)}
            </span>
            <span className="sr-only">{sha}</span>
            <CopyButton value={sha} label={t("reports.stamp.copySha")} />
          </span>
        ),
    },
  ];
  return (
    <dl
      data-testid={`${testIdPrefix}-run-stamp`}
      aria-label={t("reports.stamp.label")}
      className="flex flex-wrap items-baseline gap-x-6 gap-y-1"
    >
      {items.map((item) => (
        <div key={item.id} className="flex items-baseline gap-1.5">
          <dt className="text-caption text-fg-3">{item.label}</dt>
          <dd
            data-volatile={item.volatile === true ? "" : undefined}
            className="text-body-sm text-fg-1"
          >
            {item.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
