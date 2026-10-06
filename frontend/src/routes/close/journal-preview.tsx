// SF-05:journal-preview Journal preview (SCREENS_B §1.3; §0.4 tie-out words; SCREENS RT-100, SCR-ST-03;
// DESIGN_SYSTEM DS-CMP-06 journal batch variant, DS-CMP-10 static table, DS-ELV-02; 04 API-S-PeriodCockpit
// `journal_preview`, API-R-38 `GET /journal-runs`; BUILD_SPEC CLO-23). The period's journal totals by
// account role with the debits = credits check. Every figure is an API string, the difference included
// (DG-FE-08; L7-2-Q-12). No commands on this tab.
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useId } from "react";
import { Link } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { StatusChip } from "../../components/ui/StatusChip";
import { currencyRegistered } from "../../lib/api/queries/approvals";
import { JOURNAL_RUN_PERMISSION, runRoute } from "../../lib/api/queries/journal-runs";
import { fetchLatestJournalRun, latestRunKey } from "../../lib/api/queries/periods";
import { periodLabel } from "../../lib/api/queries/tenant";
import { formatMoney, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { useBuiltPaths } from "../settings/index";
import { type CockpitContext, CockpitFrame, journalRunMissing } from "./cockpit";

/** SCREENS RT-29 SF-06:run, the target of "Open journal run". */
const RUN_ROUTE = "/journals/runs/:runId";
const JOURNALS_ROUTE = "/journals";
const CELL = "px-3 py-2 text-body-sm";
const LINK_BUTTON =
  "inline-flex h-[var(--control-h)] items-center rounded-md border border-control bg-surface px-3 text-body-sm font-medium text-fg-1 hover:bg-hover";

export function JournalPreviewPage() {
  return (
    <CockpitFrame tab="journal-preview">
      {(context) => <JournalPreviewTab {...context} />}
    </CockpitFrame>
  );
}

function money(value: string, currency: string): string {
  return currencyRegistered(currency) ? formatMoney(value, currency) : NO_VALUE;
}

function JournalPreviewTab({ cockpit, permissions, ctxSearch }: CockpitContext) {
  const headingId = useId();
  const wordId = useId();
  const built = useBuiltPaths();
  const { period, journal_preview: preview } = cockpit;
  const currency = preview.debit_functional.currency;
  const label = periodLabel(period.period);
  const noRun = journalRunMissing(cockpit);
  const entity = period.entity.code;
  const periodKey = period.period.period_key;
  const latest = useQuery({
    queryKey: latestRunKey(entity, period.book, periodKey),
    queryFn: () => fetchLatestJournalRun(entity, period.book, periodKey),
    enabled: !noRun && built.has(RUN_ROUTE),
  });
  const run = latest.data ?? null;

  let runControl: ReactNode = null;
  if (noRun) {
    runControl = (
      <span className="flex items-center gap-3 text-body-sm text-fg-2">
        <span>{t("close.journalPreview.notCalculated")}</span>
        {permissions.includes(JOURNAL_RUN_PERMISSION) && built.has(JOURNALS_ROUTE) ? (
          <Link to={`${JOURNALS_ROUTE}${ctxSearch}`} className={LINK_BUTTON}>
            {t("close.journalPreview.runJournals")}
          </Link>
        ) : null}
      </span>
    );
  } else if (run !== null) {
    runControl = (
      <Link to={`${runRoute(run.id)}${ctxSearch}`} className={LINK_BUTTON}>
        {t("close.journalPreview.openRun", { run: run.run_no })}
      </Link>
    );
  }

  const figures: readonly {
    readonly id: string;
    readonly label: string;
    readonly value: string;
  }[] = [
    {
      id: "debits",
      label: t("close.journalPreview.debits"),
      value: money(preview.debit_functional.amount, currency),
    },
    {
      id: "credits",
      label: t("close.journalPreview.credits"),
      value: money(preview.credit_functional.amount, currency),
    },
  ];
  const cell =
    "flex min-w-40 flex-col gap-1 border-s border-hairline px-4 first:border-s-0 first:ps-0";

  return (
    <div className="flex flex-col gap-4">
      <section
        aria-labelledby={`${headingId} ${wordId}`}
        data-testid="SF-05-kpi-journal-difference"
        className="flex flex-col gap-3 rounded-md border border-hairline bg-surface p-4"
      >
        <div className="flex flex-wrap items-center gap-3">
          <h2 id={headingId} className="text-title-sm text-fg-1">
            {t("close.journalPreview.heading", { currency })}
          </h2>
          <span id={wordId} className="sr-only">
            {t(
              preview.balanced
                ? "close.journalPreview.word.balanced"
                : "close.journalPreview.word.open",
            )}
          </span>
          <span className="ms-auto">{runControl}</span>
        </div>
        <dl className="flex flex-wrap gap-y-3">
          {figures.map((figure) => (
            <div key={figure.id} className={cell}>
              <dt className="text-caption text-fg-3">{figure.label}</dt>
              <dd className="num text-kpi text-fg-1">{figure.value}</dd>
            </div>
          ))}
          <div className={cell}>
            <dt className="text-caption text-fg-3">{t("close.journalPreview.difference")}</dt>
            <dd className="flex flex-wrap items-center gap-2">
              <span className="num text-kpi text-fg-1">
                {money(preview.difference_functional.amount, currency)}
              </span>
              <StatusChip status={preview.balanced ? "Pass" : "Difference"} />
              {preview.balanced ? (
                <span className="text-body-sm text-fg-2">{t("close.journalPreview.balanced")}</span>
              ) : null}
            </dd>
          </div>
        </dl>
      </section>
      {preview.balanced ? null : (
        <Banner
          tone="negative"
          announce="static"
          title={t("close.journalPreview.unbalanced", {
            amount: currencyRegistered(currency)
              ? formatMoney(preview.difference_functional.amount, currency, { variant: "inline" })
              : NO_VALUE,
          })}
        />
      )}
      {preview.by_account_role.length === 0 ? (
        <EmptyState
          title={t("close.journalPreview.emptyTitle", { period: label })}
          description={t("close.journalPreview.emptyDescription")}
          headingLevel={3}
        />
      ) : (
        <div
          data-testid="SF-05-grid-journal-preview"
          className="overflow-x-auto rounded-md border border-hairline bg-surface"
        >
          <table className="w-full border-collapse">
            <caption className="px-3 py-2 text-start text-title-sm text-fg-1">
              {t("close.journalPreview.table", { currency })}
            </caption>
            <thead>
              <tr className="border-b border-hairline">
                <th scope="col" className={`${CELL} w-90 text-start text-caption text-fg-3`}>
                  {t("close.journalPreview.column.role")}
                </th>
                <th scope="col" className={`${CELL} text-end text-caption text-fg-3`}>
                  {t("close.journalPreview.column.debit", { currency })}
                </th>
                <th scope="col" className={`${CELL} text-end text-caption text-fg-3`}>
                  {t("close.journalPreview.column.credit", { currency })}
                </th>
              </tr>
            </thead>
            <tbody>
              {preview.by_account_role.map((row) => (
                <tr key={row.account_role} className="border-b border-hairline last:border-b-0">
                  <th scope="row" className={`${CELL} text-start font-normal text-fg-1`}>
                    {t(`accountRole.${row.account_role}`)}
                  </th>
                  <td className={`${CELL} num text-end text-fg-1`}>
                    {money(row.debit.amount, currency)}
                  </td>
                  <td className={`${CELL} num text-end text-fg-1`}>
                    {money(row.credit.amount, currency)}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2" style={{ borderBlockStartColor: "var(--rule-total)" }}>
                <th scope="row" className={`${CELL} text-start font-semibold text-fg-1`}>
                  {t("close.journalPreview.column.total")}
                </th>
                <td className={`${CELL} num text-end font-semibold text-fg-1`}>
                  {money(preview.debit_functional.amount, currency)}
                </td>
                <td className={`${CELL} num text-end font-semibold text-fg-1`}>
                  {money(preview.credit_functional.amount, currency)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
