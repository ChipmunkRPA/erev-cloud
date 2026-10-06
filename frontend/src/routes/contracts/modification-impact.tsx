// The impact preview of a modification (SCREENS §7.7, §7.9; DESIGN_SYSTEM DS-CMP-06, DS-FMT-30,
// DS-FMT-31; D-12, D-19; 04 §16.14 API-S-ImpactSummary; BUILD_SPEC CTR-27): the summary strip, the
// allocation by obligation, the progress line, the revenue by period, the labelled balances and the
// journal preview of a stored preview. SF-07 step "Impact preview" and SF-07:detail render the same view.
//
// Every figure is the API's (DG-FE-08; ruling R-93 (c)): the "Change" column of the allocation table and
// the totals rule of the journal preview are left out, because API-S-ImpactSummary answers neither and
// the browser computes no money. The figures are not Explain triggers: a dry run keeps no trace to read
// (XR-14). Under the journal preview the view states when and for which period its lines were
// computed (`computed_at`, `computed_period_key`; 04 rev 1.210, item MOD-PREVIEW-JOURNAL-RULE-1) and
// warns once that period is no longer the latest postable one: the entries at approval will differ.
import { useId } from "react";

import { Banner } from "../../components/feedback/Banner";
import { Money } from "../../components/money/Money";
import { NoValue } from "../../components/money/Num";
import { type Kpi, KpiStrip } from "../../components/record/KpiStrip";
import { Button } from "../../components/ui/Button";
import type { ImpactSummary } from "../../lib/api/queries/modifications";
import { formatDate, formatMoney, formatPercent, formatTimestamp } from "../../lib/format";
import { hasMessage, t } from "../../lib/i18n/t";

/** DS-FMT-19 label of a period key; the key itself where the calendar has no such period. */
export type PeriodLabel = (periodKey: string) => string;

export interface ModificationImpactProps {
  readonly summary: ImpactSummary;
  readonly currency: string;
  /** The period of the accounting context; its row of `revenue_by_period` fills the strip. */
  readonly contextPeriod: string | null;
  readonly periodLabel: PeriodLabel;
  /** The keys of the obligations the modification adds: they have no "before". */
  readonly added: readonly string[];
  readonly headingLevel?: 2 | 3;
  /**
   * The latest postable period of the contract's entity in the primary book as it is now (its key;
   * null: none; undefined: not read). When it is no longer the period the journal lines were computed
   * for, the view says that the entries at approval will differ (04 API-S-ImpactSummary rev 1.210).
   */
  readonly latestPostablePeriod?: string | null | undefined;
  /** The wizard's way to compute the preview again; SF-07:detail has none and only says so. */
  readonly onRunPreview?: (() => void) | undefined;
  /** A run started from here has not ended yet. */
  readonly previewRunning?: boolean;
}

const CELL = "px-2 py-1.5";
const HEAD = "px-2 py-1.5 font-medium";

function treatmentLabel(treatment: string | null): string | null {
  if (treatment === null) {
    return null;
  }
  const key = `modifications.treatment.${treatment}`;
  return hasMessage(key) ? t(key) : treatment;
}

function balanceLabel(balance: string): string {
  const key = `contracts.balance.${balance}`;
  return hasMessage(key) ? t(key) : balance;
}

function roleLabel(role: string): string {
  const key = `accountRole.${role}`;
  return hasMessage(key) ? t(key) : role;
}

/** An amount as text inside a sentence such as "Before 240,000.00" (DS-FMT-04). */
function formatMoneyCell(amount: string, currency: string): string {
  return formatMoney(amount, currency, { variant: "cell" });
}

function Caption({ children }: { readonly children: string }) {
  return <caption className="pb-2 text-start text-title-sm text-fg-1">{children}</caption>;
}

export function ModificationImpact({
  summary,
  currency,
  contextPeriod,
  periodLabel,
  added,
  headingLevel = 2,
  latestPostablePeriod,
  onRunPreview,
  previewRunning = false,
}: ModificationImpactProps) {
  const journalId = useId();
  // 04 API-S-ImpactSummary (rev 1.210): the journal lines are the entries the approval's computation
  // would post at `computed_at` — the change's effect together with the amounts of the period that
  // are not posted yet — into `computed_period_key`. A preview stored before the two members existed
  // states neither, and the view then says nothing about them.
  const computedAt = summary.computed_at ?? null;
  const computedFor = summary.computed_period_key ?? null;
  const computed = computedAt !== null && computedFor !== null;
  const periodMoved =
    computed && latestPostablePeriod !== undefined && latestPostablePeriod !== computedFor;
  const revenue =
    summary.revenue_by_period.find((row) => row.period_key === contextPeriod) ??
    summary.revenue_by_period[0] ??
    null;
  const kpis: Kpi[] = [
    {
      id: "transaction-price",
      label: t("modifications.impact.transactionPrice"),
      value: summary.transaction_price_after.amount,
      currency,
      secondary: t("modifications.impact.before", {
        value: formatMoneyCell(summary.transaction_price_before.amount, currency),
      }),
    },
    {
      id: "catch-up",
      label: t("modifications.impact.catchUp"),
      value: summary.catch_up_total.amount,
      currency,
    },
    ...(revenue === null
      ? []
      : [
          {
            id: "revenue",
            label: t("modifications.impact.revenue", { period: periodLabel(revenue.period_key) }),
            value: revenue.after.amount,
            currency,
            secondary: t("modifications.impact.before", {
              value: formatMoneyCell(revenue.before.amount, currency),
            }),
          },
        ]),
    {
      id: "rpo",
      label: t("modifications.impact.rpo", { date: formatDate(summary.rpo_date) }),
      value: summary.rpo_after.amount,
      currency,
      secondary: t("modifications.impact.before", {
        value: formatMoneyCell(summary.rpo_before.amount, currency),
      }),
    },
    {
      id: "journal-lines",
      label: t("modifications.impact.journalLines"),
      value: String(summary.journal_lines.length),
      currency,
      kind: "count",
    },
  ];

  const before = new Map(
    summary.remaining_allocation_before.map((row) => [row.obligation_key, row.amount]),
  );
  const after = new Map(
    summary.remaining_allocation_after.map((row) => [row.obligation_key, row.amount]),
  );
  const catchUp = new Map(summary.catch_up_by_obligation.map((row) => [row.obligation_key, row]));
  const keys = [...new Set([...before.keys(), ...after.keys(), ...catchUp.keys()])].sort(
    (left, right) => left.localeCompare(right, undefined, { numeric: true }),
  );
  const balancesBefore = new Map(summary.balances_before.map((row) => [row.balance, row.amount]));
  const balancesAfter = new Map(summary.balances_after.map((row) => [row.balance, row.amount]));
  const balances = [...new Set([...balancesBefore.keys(), ...balancesAfter.keys()])];
  const closed = summary.origin_period_key !== null && summary.posting_period_key !== null;

  return (
    <div className="flex flex-col gap-6">
      {closed ? (
        <Banner
          tone="info"
          announce="static"
          headingLevel={headingLevel === 2 ? 3 : 4}
          title={t("modifications.impact.closedPeriod", {
            origin: periodLabel(summary.origin_period_key ?? ""),
            posting: periodLabel(summary.posting_period_key ?? ""),
          })}
        />
      ) : null}
      <KpiStrip
        heading={t("modifications.impact.summary", { currency })}
        kpis={kpis}
        region
        headingLevel={headingLevel}
        testId="SF-07-kpi-strip"
      />

      <table data-testid="SF-07-grid-allocation" className="w-full border-collapse text-body-sm">
        <Caption>{t("modifications.impact.allocation.caption")}</Caption>
        <thead>
          <tr className="border-b border-default text-caption text-fg-3">
            <th scope="col" className={`${HEAD} text-start`}>
              {t("modifications.impact.allocation.obligation")}
            </th>
            <th scope="col" className={`${HEAD} text-start`}>
              {t("modifications.impact.allocation.treatment")}
            </th>
            <th scope="col" className={`${HEAD} text-end`}>
              {t("modifications.impact.allocation.before")}
            </th>
            <th scope="col" className={`${HEAD} text-end`}>
              {t("modifications.impact.allocation.after")}
            </th>
            <th scope="col" className={`${HEAD} text-end`}>
              {t("modifications.impact.catchUp")}
            </th>
          </tr>
        </thead>
        <tbody>
          {keys.map((key) => {
            const row = catchUp.get(key);
            const treatment = treatmentLabel(row?.treatment ?? null);
            return (
              <tr key={key} className="border-b border-hairline align-top">
                <th scope="row" className={`${CELL} text-start font-medium text-fg-1`}>
                  <span className="font-mono text-mono-sm">{key}</span>
                  {added.includes(key) ? (
                    <>
                      {" "}
                      <span className="ms-1 text-fg-3">{t("modifications.impact.added")}</span>
                    </>
                  ) : null}
                </th>
                <td className={CELL}>{treatment ?? <NoValue />}</td>
                <td className={`${CELL} text-end`}>
                  <Money value={before.get(key)?.amount ?? null} currency={currency} />
                </td>
                <td className={`${CELL} text-end`}>
                  <Money value={after.get(key)?.amount ?? null} currency={currency} />
                </td>
                <td className={`${CELL} text-end`}>
                  <Money value={row?.amount.amount ?? null} currency={currency} delta />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {summary.progress_before === null && summary.progress_after === null ? null : (
        <p className="text-body text-fg-1">
          {t("modifications.impact.progress", {
            before: formatPercent(summary.progress_before),
            after: formatPercent(summary.progress_after),
          })}
        </p>
      )}

      <table data-testid="SF-07-grid-revenue" className="w-full border-collapse text-body-sm">
        <Caption>{t("modifications.impact.revenueByPeriod.caption")}</Caption>
        <thead>
          <tr className="border-b border-default text-caption text-fg-3">
            <th scope="col" className={`${HEAD} text-start`}>
              {t("modifications.impact.revenueByPeriod.period")}
            </th>
            <th scope="col" className={`${HEAD} text-end`}>
              {t("modifications.impact.revenueByPeriod.before")}
            </th>
            <th scope="col" className={`${HEAD} text-end`}>
              {t("modifications.impact.revenueByPeriod.after")}
            </th>
            <th scope="col" className={`${HEAD} text-end`}>
              {t("modifications.impact.revenueByPeriod.change")}
            </th>
          </tr>
        </thead>
        <tbody>
          {summary.revenue_by_period.map((row) => (
            <tr key={row.period_key} className="border-b border-hairline">
              <th scope="row" className={`${CELL} text-start font-medium text-fg-1`}>
                {periodLabel(row.period_key)}
              </th>
              <td className={`${CELL} text-end`}>
                <Money value={row.before.amount} currency={currency} />
              </td>
              <td className={`${CELL} text-end`}>
                <Money value={row.after.amount} currency={currency} />
              </td>
              <td className={`${CELL} text-end`}>
                <Money value={row.change.amount} currency={currency} delta />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {balances.length === 0 ? null : (
        <table data-testid="SF-07-grid-balances" className="w-full border-collapse text-body-sm">
          <Caption>{t("modifications.impact.balances.caption")}</Caption>
          <thead>
            <tr className="border-b border-default text-caption text-fg-3">
              <th scope="col" className={`${HEAD} text-start`}>
                {t("modifications.impact.balances.balance")}
              </th>
              <th scope="col" className={`${HEAD} text-end`}>
                {t("modifications.impact.revenueByPeriod.before")}
              </th>
              <th scope="col" className={`${HEAD} text-end`}>
                {t("modifications.impact.revenueByPeriod.after")}
              </th>
            </tr>
          </thead>
          <tbody>
            {balances.map((balance) => (
              <tr key={balance} className="border-b border-hairline">
                <th scope="row" className={`${CELL} text-start font-medium text-fg-1`}>
                  {balanceLabel(balance)}
                </th>
                <td className={`${CELL} text-end`}>
                  <Money value={balancesBefore.get(balance)?.amount ?? null} currency={currency} />
                </td>
                <td className={`${CELL} text-end`}>
                  <Money value={balancesAfter.get(balance)?.amount ?? null} currency={currency} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="flex flex-col gap-2">
        {summary.journal_lines.length === 0 ? (
          <section aria-labelledby={journalId} className="flex flex-col gap-1">
            <h3 id={journalId} className="text-title-sm text-fg-1">
              {t("modifications.impact.journal.caption")}
            </h3>
            <p className="text-body-sm text-fg-2">{t("modifications.wizard.preview.noJournal")}</p>
          </section>
        ) : (
          <table data-testid="SF-07-grid-journal" className="w-full border-collapse text-body-sm">
            <Caption>{t("modifications.impact.journal.caption")}</Caption>
            <thead>
              <tr className="border-b border-default text-caption text-fg-3">
                <th scope="col" className={`${HEAD} text-start`}>
                  {t("modifications.impact.journal.account")}
                </th>
                <th scope="col" className={`${HEAD} text-start`}>
                  {t("modifications.impact.journal.role")}
                </th>
                <th scope="col" className={`${HEAD} text-end`}>
                  {t("modifications.impact.journal.debit")}
                </th>
                <th scope="col" className={`${HEAD} text-end`}>
                  {t("modifications.impact.journal.credit")}
                </th>
              </tr>
            </thead>
            <tbody>
              {summary.journal_lines.map((line, index) => (
                <tr
                  key={`${line.gl_account?.code ?? ""}:${line.account_role}:${String(index)}`}
                  className="border-b border-hairline"
                >
                  <th scope="row" className={`${CELL} text-start font-medium text-fg-1`}>
                    {line.gl_account === null ? (
                      <NoValue />
                    ) : (
                      `${line.gl_account.code} · ${line.gl_account.name}`
                    )}
                  </th>
                  <td className={CELL}>{roleLabel(line.account_role)}</td>
                  <td className={`${CELL} text-end`}>
                    <Money value={line.debit.amount} currency={currency} />
                  </td>
                  <td className={`${CELL} text-end`}>
                    <Money value={line.credit.amount} currency={currency} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {computedAt !== null && computedFor !== null ? (
          <p data-testid="SF-07-journal-computed" className="text-body-sm text-fg-2">
            {t("modifications.impact.journal.computed", {
              at: formatTimestamp(computedAt),
              period: periodLabel(computedFor),
            })}
          </p>
        ) : null}
        {periodMoved && computedFor !== null ? (
          <div data-testid="SF-07-banner-period-moved">
            <Banner
              tone="warning"
              announce="static"
              headingLevel={headingLevel === 2 ? 3 : 4}
              title={t("modifications.impact.journal.periodMoved", {
                period: periodLabel(computedFor),
              })}
              actions={
                onRunPreview === undefined ? undefined : (
                  <Button variant="link" loading={previewRunning} onClick={onRunPreview}>
                    {t("modifications.wizard.preview.run")}
                  </Button>
                )
              }
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
