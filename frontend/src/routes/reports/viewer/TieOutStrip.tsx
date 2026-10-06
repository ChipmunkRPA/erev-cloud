// RV-05 Tie-out strip (SCREENS_B §0.5, §0.4 tie-out chips, RPT-R-08; 04 T-RPT-02 `tie_out_results`).
// Below the run stamp: the heading "Tie-outs (<n> pass, <m> fail)" and one row per result with the
// DS-CMP-19 chip, the tie-out name, "Expected <currency> <amount>", "Actual <currency> <amount>" and,
// when failing, "Difference <currency> <amount>". The difference is the API `difference`, actual − expected
// per currency, computed when the run is serialised (04 API-S-ReportRun; D-88 L7-3-Q-3); the browser does
// no money arithmetic (DG-FE-08).
import { useId } from "react";

import { chipFor, StatusChip } from "../../../components/ui/StatusChip";
import { currencyRegistered } from "../../../lib/api/queries/approvals";
import type { TieOutResult } from "../../../lib/api/queries/reports";
import { formatMoney, NO_VALUE } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";
import { isMoney, type Money, tieOutName } from "./specs";

function amounts(value: unknown): readonly Money[] {
  if (isMoney(value)) {
    return [value];
  }
  return Array.isArray(value) ? value.filter(isMoney) : [];
}

function inline(money: Money): string {
  // A currency the caller cannot read shows no value (DS-FMT-03; L3-3-Q-26).
  return currencyRegistered(money.currency)
    ? formatMoney(money.amount, money.currency, { variant: "inline" })
    : NO_VALUE;
}

export interface TieOutStripProps {
  readonly results: readonly TieOutResult[];
  /** The SF id of the host screen: `<SF id>-banner-tie-outs`. */
  readonly testIdPrefix?: string | undefined;
}

export function TieOutStrip({ results, testIdPrefix = "SF-08" }: TieOutStripProps) {
  const headingId = useId();
  if (results.length === 0) {
    return null;
  }
  const passed = results.filter((item) => item.result === "PASS").length;
  const failed = results.filter((item) => item.result === "FAIL").length;
  return (
    <section
      aria-labelledby={headingId}
      data-testid={`${testIdPrefix}-banner-tie-outs`}
      className="flex flex-col gap-2 rounded-md border border-hairline bg-surface px-4 py-3"
    >
      <h2 id={headingId} className="text-title-sm text-fg-1">
        {t("reports.tieOuts.heading", { passed, failed })}
      </h2>
      <ul className="flex flex-col gap-2">
        {results.map((item) => {
          const chip = chipFor("T-RPT-02", item.result);
          const expected = amounts(item.expected);
          const actual = amounts(item.actual);
          const differences = amounts(item.difference);
          return (
            <li key={item.code} className="flex flex-wrap items-center gap-x-4 gap-y-1">
              {chip === null ? null : <StatusChip status={chip.status} caption={chip.caption} />}
              <span className="text-body-sm font-medium text-fg-1">{tieOutName(item.code)}</span>
              {expected.map((money) => {
                const pair = actual.find((other) => other.currency === money.currency);
                const difference = differences.find((other) => other.currency === money.currency);
                return (
                  <span
                    key={money.currency}
                    className="flex flex-wrap gap-x-4 text-body-sm text-fg-2"
                  >
                    <span className="num">
                      {t("reports.tieOuts.expected", { amount: inline(money) })}
                    </span>
                    {pair === undefined ? null : (
                      <span className="num">
                        {t("reports.tieOuts.actual", { amount: inline(pair) })}
                      </span>
                    )}
                    {item.result === "FAIL" && difference !== undefined ? (
                      <span className="num text-fg-1">
                        {t("reports.tieOuts.difference", { amount: inline(difference) })}
                      </span>
                    ) : null}
                  </span>
                );
              })}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
