// Shared parts of the estimates workbench (SCREENS §8.3, §8.4, §8.10; DESIGN_SYSTEM DS-CMP-19,
// DS-CMP-27, DS-FMT-04, DS-FMT-09, DS-FMT-11, DS-FMT-13, DS-FMT-20; 04 API-S-ImpactSummary; BUILD_SPEC
// CTR-25): the labels of the E-09 kinds, the E-10 methods and the allocation targets, the text of a
// figure, the method chip with its POL-040 lock, the line of a command that did not succeed and the
// preview region of the version drawer.
//
// Every figure is the API's (DG-FE-08; ruling R-93 (c)): the preview shows the transaction price before
// and after instead of one "change" figure, and no loss test, because API-S-ImpactSummary answers
// neither and the browser compares and subtracts no money.
import { useId } from "react";

import { Banner } from "../../components/feedback/Banner";
import { LockSimple } from "../../components/icons/registry";
import { Money } from "../../components/money/Money";
import { NoValue } from "../../components/money/Num";
import { Button } from "../../components/ui/Button";
import { OutlineChip } from "../../components/ui/StatusChip";
import { Tooltip } from "../../components/ui/Tooltip";
import type { ApiProblem } from "../../lib/api/problems";
import type {
  Estimate,
  EstimateImpact,
  EstimateKind,
  EstimateMethod,
  EstimateTarget,
} from "../../lib/api/queries/estimates";
import { currencyKnown } from "../../lib/forms/contract";
import type { Figure } from "../../lib/forms/estimate";
import {
  formatDate,
  formatMoney,
  formatNumber,
  formatPercent,
  formatRate,
  NO_VALUE,
} from "../../lib/format";
import { hasMessage, t } from "../../lib/i18n/t";
import { dateRange } from "./obligation-pane";

/** DS-FMT-19 label of a period key; the key itself where the calendar has no such period. */
export type PeriodLabel = (periodKey: string) => string;

/** SCREENS §8.4 label of an E-09 kind. */
export function kindLabel(kind: EstimateKind): string {
  return t(`contracts.estimates.kind.${kind}`);
}

/** SCREENS §8.4 label of an E-10 method. */
export function methodLabel(method: EstimateMethod): string {
  return t(`contracts.estimates.method.${method}`);
}

/** SCREENS §8.4 label of a T-CON-12 element type; the literal where the catalogue has none. */
export function elementTypeLabel(type: string): string {
  const key = `contracts.estimates.vcType.${type}`;
  return hasMessage(key) ? t(key) : type;
}

/** SCREENS §8.3 allocation target label: "Whole contract", "Specific obligations: <keys>", "Increments". */
export function targetLabel(
  element: Pick<Estimate, "allocation_target" | "target_obligation_keys">,
): string {
  const target: EstimateTarget = element.allocation_target;
  return target === "OBLIGATIONS"
    ? t("contracts.estimates.target.obligationsOf", {
        keys: element.target_obligation_keys.join(", "),
      })
    : t(`contracts.estimates.target.${target}`);
}

/** A figure as text in its format; the no-value dash where the version holds none. */
export function figureText(figure: Figure, currency: string | null): string {
  if (figure.type === "date") {
    return figure.date === null ? NO_VALUE : formatDate(figure.date);
  }
  if (figure.type === "period") {
    return figure.end === null ? NO_VALUE : (dateRange(figure.start, figure.end) ?? NO_VALUE);
  }
  const value = figure.value;
  if (value === null) {
    return NO_VALUE;
  }
  const money = currency !== null && currencyKnown(currency) ? currency : null;
  switch (figure.type) {
    case "money":
      return money === null ? value : formatMoney(value, money);
    case "unit":
      return money === null ? value : formatRate(value, { kind: "unit", currency: money });
    case "rate":
      return formatPercent(value, { kind: "share" });
    case "progress":
      return formatPercent(value);
    case "quantity":
      return formatNumber(value, { kind: "quantity" });
    case "integer":
      return formatNumber(value, { kind: "count" });
    case "flag":
      return value === "true" ? t("contracts.drawer.yes") : t("contracts.drawer.no");
  }
}

/**
 * The method of an element (SCREENS §8.3, §8.10). Once a version is approved the method is fixed
 * (POL-040): the chip carries the lock, the tooltip and the accessible name "Method <method>, locked".
 */
export function MethodChip({
  method,
  locked,
  testId,
}: {
  readonly method: EstimateMethod;
  readonly locked: boolean;
  readonly testId?: string | undefined;
}) {
  if (!locked) {
    return (
      <span data-testid={testId} className="inline-flex">
        <OutlineChip label={methodLabel(method)} />
      </span>
    );
  }
  return (
    <Tooltip content={t("contracts.estimates.methodLocked")}>
      {(trigger) => (
        <span
          {...trigger}
          role="img"
          aria-label={t(`contracts.estimates.methodLockedName.${method}`)}
          data-testid={testId}
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- DS-CMP-27: a tooltip trigger is focusable
          tabIndex={0}
          className="inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-sm border border-default bg-transparent px-1.5 text-caption font-medium text-fg-2"
        >
          <LockSimple aria-hidden="true" size={12} className="shrink-0" />
          {methodLabel(method)}
        </span>
      )}
    </Tooltip>
  );
}

/** A command that did not answer 2xx: its problem, or a server that did not answer. */
export type Failure = ApiProblem | "unreached";

/**
 * The banner of a failed command: the title, the detail and the messages that name no field of the
 * form, or the line of a server that did not answer. `fields` are the names the form shows inline;
 * `placedRules` are the rule ids of findings the form shows on a field of its own although the API
 * names none, or one the form does not hold.
 */
export function FailureNotice({
  failure,
  fields = [],
  placedRules = [],
  onRetry,
}: {
  readonly failure: Failure | null;
  readonly fields?: readonly string[];
  readonly placedRules?: readonly string[];
  readonly onRetry?: (() => void) | undefined;
}) {
  if (failure === null) {
    return null;
  }
  const actions =
    onRetry === undefined ? undefined : (
      <Button variant="link" onClick={onRetry}>
        {t("common.grid.retry")}
      </Button>
    );
  if (failure === "unreached") {
    return (
      <Banner
        tone="negative"
        title={t("contracts.estimates.notReached")}
        announce="live"
        headingLevel={3}
        actions={actions}
      />
    );
  }
  const messages = [
    ...new Set(
      failure.errors
        .filter((error) => error.rule_id === null || !placedRules.includes(error.rule_id))
        .filter((error) => error.field === null || !fields.includes(error.field))
        .map((error) => error.message),
    ),
  ];
  return (
    <Banner
      tone="negative"
      title={failure.title}
      announce="live"
      headingLevel={3}
      actions={actions}
    >
      {failure.detail === null || messages.includes(failure.detail) ? null : (
        <p>{failure.detail}</p>
      )}
      {messages.map((message) => (
        <p key={message}>{message}</p>
      ))}
      {failure.requestId === null ? null : (
        <p>{t("contracts.drawer.reference", { reference: failure.requestId })}</p>
      )}
    </Banner>
  );
}

function balanceLabel(balance: string): string {
  const key = `contracts.balance.${balance}`;
  return hasMessage(key) ? t(key) : balance;
}

const CELL = "px-2 py-1.5";
const HEAD = "px-2 py-1.5 font-medium";

export interface EstimatePreviewProps {
  /** `result.summary` of the succeeded preview job, as the API answered it. */
  readonly summary: EstimateImpact;
  readonly currency: string;
  /** The period of the accounting context; its row of `revenue_by_period` is shown. */
  readonly contextPeriod: string | null;
  readonly periodLabel: PeriodLabel;
}

/**
 * The figures of a version's dry run (SCREENS §8.4): the catch-up, then before and after of the
 * transaction price, the revenue of the context period, the progress and the labelled balances.
 */
export function EstimatePreview({
  summary,
  currency,
  contextPeriod,
  periodLabel,
}: EstimatePreviewProps) {
  const captionId = useId();
  const revenue =
    summary.revenue_by_period.find((row) => row.period_key === contextPeriod) ??
    summary.revenue_by_period[0] ??
    null;
  const before = new Map(summary.balances_before.map((row) => [row.balance, row.amount.amount]));
  const after = new Map(summary.balances_after.map((row) => [row.balance, row.amount.amount]));
  const balances = [...new Set([...before.keys(), ...after.keys()])];
  const progress = summary.progress_before !== null || summary.progress_after !== null;
  return (
    <div className="flex flex-col gap-3">
      <dl className="flex flex-wrap gap-x-8 gap-y-2">
        <div className="flex flex-col gap-0.5">
          <dt className="text-caption text-fg-3">{t("contracts.drawer.preview.catchUp")}</dt>
          <dd className="text-body text-fg-1" data-testid="SF-03-estimate-preview-catch-up">
            <Money value={summary.catch_up_total.amount} currency={currency} delta />
          </dd>
        </div>
      </dl>
      <table aria-labelledby={captionId} className="w-full border-collapse text-body-sm">
        <caption id={captionId} className="pb-1 text-start text-caption text-fg-3">
          {t("contracts.estimates.preview.caption", { currency })}
        </caption>
        <thead>
          <tr className="border-b border-default text-caption text-fg-3">
            <th scope="col" className={`${HEAD} text-start`}>
              {t("contracts.estimates.preview.figure")}
            </th>
            <th scope="col" className={`${HEAD} text-end`}>
              {t("contracts.estimates.preview.before")}
            </th>
            <th scope="col" className={`${HEAD} text-end`}>
              {t("contracts.estimates.preview.after")}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr className="border-b border-hairline">
            <th scope="row" className={`${CELL} text-start font-medium text-fg-1`}>
              {t("contracts.estimates.preview.transactionPrice")}
            </th>
            <td className={`${CELL} text-end`}>
              <Money value={summary.transaction_price_before.amount} currency={currency} />
            </td>
            <td className={`${CELL} text-end`}>
              <Money value={summary.transaction_price_after.amount} currency={currency} />
            </td>
          </tr>
          {revenue === null ? null : (
            <tr className="border-b border-hairline">
              <th scope="row" className={`${CELL} text-start font-medium text-fg-1`}>
                {t("contracts.drawer.preview.revenue", {
                  period: periodLabel(revenue.period_key),
                })}
              </th>
              <td className={`${CELL} text-end`}>
                <Money value={revenue.before.amount} currency={currency} />
              </td>
              <td className={`${CELL} text-end`}>
                <Money value={revenue.after.amount} currency={currency} />
              </td>
            </tr>
          )}
          {progress ? (
            <tr className="border-b border-hairline">
              <th scope="row" className={`${CELL} text-start font-medium text-fg-1`}>
                {t("contracts.drawer.preview.progress")}
              </th>
              <td className={`${CELL} num text-end`}>
                {summary.progress_before === null ? (
                  <NoValue />
                ) : (
                  formatPercent(summary.progress_before)
                )}
              </td>
              <td className={`${CELL} num text-end`}>
                {summary.progress_after === null ? (
                  <NoValue />
                ) : (
                  formatPercent(summary.progress_after)
                )}
              </td>
            </tr>
          ) : null}
          {balances.map((balance) => (
            <tr key={balance} className="border-b border-hairline">
              <th scope="row" className={`${CELL} text-start font-medium text-fg-1`}>
                {balanceLabel(balance)}
              </th>
              <td className={`${CELL} text-end`}>
                <Money value={before.get(balance) ?? null} currency={currency} />
              </td>
              <td className={`${CELL} text-end`}>
                <Money value={after.get(balance) ?? null} currency={currency} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
