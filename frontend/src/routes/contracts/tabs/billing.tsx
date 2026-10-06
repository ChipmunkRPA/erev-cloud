// SF-03:billing Billing tab (SCREENS §4.4; §0.4 RT-15; DESIGN_SYSTEM DS-CMP-10, DS-CMP-15, DS-CMP-21,
// DS-FMT-04, DS-FMT-28; D-12; 04 API-R-28 `GET /contracts/{id}/balances`, API-R-30 `GET
// /contracts/{id}/events`; BUILD_SPEC CTR-23). Panel 1 "Balances by entity": the transposed table of the
// labelled balances, one column per legal entity, a cell an Explain trigger where its row names the
// explanation of that balance (rev 1.24; 04 API-S-ContractBalance `links`); a row that is 0.00 in every
// entity collapses under "Show zero balances" (off by default), and `net_position` is never rendered. Panel
// 2 "Invoices and credit memos": the DataGrid of the contract's BILLING_RECORDED and CREDIT_MEMO_RECORDED
// events, newest first.
// Not rendered (R-RC-1; XR-14; CTR-14 post-rc): panel 3 "Billing plan" and panel 4 "Minimum commitment"
// (L5-4-Q-48).
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useId, useMemo, useState } from "react";

import { DataGrid } from "../../../components/data-grid/DataGrid";
import {
  type GridColumn,
  type GridColumnState,
  type GridSource,
  initialColumnState,
} from "../../../components/data-grid/types";
import { ExplainTrigger } from "../../../components/explain/ExplainTrigger";
import { Banner } from "../../../components/feedback/Banner";
import { EmptyState } from "../../../components/feedback/EmptyState";
import { Skeleton } from "../../../components/feedback/Skeleton";
import { Switch } from "../../../components/form/Switch";
import { Money } from "../../../components/money/Money";
import { NoValue } from "../../../components/money/Num";
import { Button } from "../../../components/ui/Button";
import {
  billingEventsKey,
  type Contract,
  type ContractBalance,
  contractBalancesKey,
  type ContractEvent,
  fetchBillingEventsPage,
  fetchContractBalances,
  type RecordContext,
} from "../../../lib/api/queries/contracts";
import type { Obligation } from "../../../lib/api/queries/obligations";
import { t } from "../../../lib/i18n/t";
import { eventOriginText } from "../event-origin";
import { balanceFigure, dateRange, moneyText } from "../obligation-pane";
import { ObligationKeyCell, obligationHref, type WorkbenchTabProps } from "./schedules";

/** SCREENS §4.4 panel 1 rows in order (API-S-ContractBalance members; `net_position` is not one). */
export const BALANCE_ROWS = [
  "contract_liability",
  "contract_liability_current",
  "contract_asset",
  "contract_asset_current",
  "unbilled_receivable",
  "accounts_receivable",
  "refund_liability",
  "return_asset",
  "deposit_liability",
  "customer_incentive_asset",
  "consideration_payable",
  "cost_asset_carrying",
  "loss_provision",
] as const satisfies readonly (keyof ContractBalance)[];

export type BalanceRow = (typeof BALANCE_ROWS)[number];

const ZERO = /^[-+]?0*(\.0*)?$/;

/** True for a decimal string whose digits are all zero. */
export function isZeroAmount(value: string): boolean {
  return ZERO.test(value.trim());
}

/** SCREENS §4.4: the rows shown; a row that is 0.00 in every entity only with the switch on. */
export function visibleBalanceRows(
  items: readonly ContractBalance[],
  showZero: boolean,
): readonly BalanceRow[] {
  return BALANCE_ROWS.filter(
    (field) => showZero || items.some((item) => !isZeroAmount(item[field].amount)),
  );
}

function BalancesPanel({
  contract,
  context,
  explainContext,
}: {
  readonly contract: Contract;
  readonly context: RecordContext;
  readonly explainContext: string;
}) {
  const headingId = useId();
  const [showZero, setShowZero] = useState(false);
  const balances = useQuery({
    queryKey: contractBalancesKey(contract.id, context),
    queryFn: () => fetchContractBalances(contract.id, context),
  });
  const currency = balances.data?.[0]?.contract_liability.currency ?? contract.transaction_currency;
  const title = t("contracts.billing.balances.title", { currency });

  let content: ReactNode;
  if (balances.isPending) {
    content = <Skeleton region={title} shape="rows" count={5} />;
  } else if (balances.isError) {
    content = (
      <Banner
        tone="negative"
        title={t("contracts.billing.balances.loadError")}
        announce="live"
        actions={
          <Button variant="link" onClick={() => void balances.refetch()}>
            {t("common.grid.retry")}
          </Button>
        }
      />
    );
  } else if (balances.data.length === 0) {
    content = <p className="text-body-sm text-fg-2">{t("contracts.billing.balances.empty")}</p>;
  } else {
    const items = balances.data;
    const rows = visibleBalanceRows(items, showZero);
    content =
      rows.length === 0 ? (
        <p className="text-body-sm text-fg-2">{t("contracts.billing.balances.allZero")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table data-testid="SF-03-grid-balances" className="w-full border-collapse text-body-sm">
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr className="border-b border-default bg-subtle text-fg-2">
                <th scope="col" className="px-2 py-1 text-start font-medium">
                  {t("contracts.billing.balances.column.balance")}
                </th>
                {items.map((item) => (
                  <th key={item.entity.id} scope="col" className="px-2 py-1 text-end font-medium">
                    <span className="font-mono text-mono-sm">{item.entity.code}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((field) => {
                const label = t(`contracts.balance.${field}`);
                return (
                  <tr key={field} className="border-b border-hairline">
                    <th scope="row" className="px-2 py-1 text-start font-normal">
                      {label}
                    </th>
                    {items.map((item) => {
                      const money = item[field];
                      const amount = (
                        <Money value={money.amount} currency={money.currency} variant="cell" />
                      );
                      // §4.4 (rev 1.24): the row names the explanation of a balance by the id of
                      // the balance row, which no other member carries; a balance it names none for
                      // prints without a trigger.
                      const figure = balanceFigure(item.links, field, item.book);
                      return (
                        <td key={item.entity.id} className="px-2 py-1 text-end">
                          {figure === undefined ? (
                            amount
                          ) : (
                            <ExplainTrigger
                              figureRef={figure}
                              label={`${label} · ${item.entity.code}`}
                              context={explainContext}
                              valueText={moneyText(money.amount, money.currency)}
                            >
                              {amount}
                            </ExplainTrigger>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      );
  }

  return (
    <section
      aria-labelledby={headingId}
      className="flex flex-col gap-3 rounded-lg border border-hairline bg-surface p-[var(--panel-pad)]"
    >
      <div className="flex flex-wrap items-center gap-3">
        <h2 id={headingId} className="text-title-sm text-fg-1">
          {title}
        </h2>
        <span className="flex-1" />
        <Switch
          label={t("contracts.billing.balances.showZero")}
          checked={showZero}
          onChange={setShowZero}
        />
      </div>
      {content}
    </section>
  );
}

function payloadString(event: ContractEvent, name: string): string | null {
  const value = event.payload[name];
  return typeof value === "string" && value !== "" ? value : null;
}

/** The event's `payload.amount`: a money object `{amount, currency}`, or a decimal string. */
function payloadMoney(
  event: ContractEvent,
  fallback: string,
): { amount: string; currency: string } | null {
  const value = event.payload.amount;
  if (typeof value === "string") {
    return { amount: value, currency: fallback };
  }
  if (typeof value === "object" && value !== null) {
    const { amount, currency } = value as {
      readonly amount?: unknown;
      readonly currency?: unknown;
    };
    if (typeof amount === "string") {
      return { amount, currency: typeof currency === "string" ? currency : fallback };
    }
  }
  return null;
}

function isCreditMemo(event: ContractEvent): boolean {
  return event.event_type === "CREDIT_MEMO_RECORDED";
}

/** SCREENS §4.4 column 1: the invoice or credit memo number. */
export function documentOf(event: ContractEvent): string {
  return (
    payloadString(event, isCreditMemo(event) ? "credit_memo_number" : "invoice_number") ?? event.id
  );
}

/** SCREENS §4.4 columns hidden by default. */
export const INVOICE_HIDDEN: readonly string[] = ["service_period", "recorded_at"];

function invoiceColumns(
  contract: Contract,
  obligations: readonly Obligation[],
  ctxSearch: string,
): readonly GridColumn<ContractEvent>[] {
  const currency = contract.transaction_currency;
  const byKey = new Map(obligations.map((item) => [item.obligation_key, item]));
  const amount = (event: ContractEvent, credit: boolean): string | null => {
    const money = isCreditMemo(event) === credit ? payloadMoney(event, currency) : null;
    if (money === null) {
      return null;
    }
    // Credited is the magnitude of the credit memo (DS-FMT-28: no signed balance).
    return credit && money.amount.startsWith("-") ? money.amount.slice(1) : money.amount;
  };
  return [
    {
      id: "document",
      header: t("contracts.billing.invoices.column.document"),
      kind: "identifier",
      value: documentOf,
      width: 160,
    },
    {
      id: "kind",
      header: t("contracts.billing.invoices.column.kind"),
      kind: "text",
      value: (event) =>
        t(
          isCreditMemo(event)
            ? "contracts.billing.invoices.kind.creditMemo"
            : "contracts.billing.invoices.kind.invoice",
        ),
      width: 128,
    },
    {
      id: "issue_date",
      header: t("contracts.billing.invoices.column.issueDate"),
      kind: "date",
      value: (event) => payloadString(event, "issue_date"),
      sortKey: "effective_date",
      width: 136,
    },
    {
      id: "obligation",
      header: t("contracts.billing.invoices.column.obligation"),
      kind: "text",
      value: (event) => payloadString(event, "obligation_key"),
      render: (event) => {
        const key = payloadString(event, "obligation_key");
        return (
          <ObligationKeyCell
            obligationKey={key}
            href={key === null ? null : obligationHref(contract, byKey.get(key), ctxSearch)}
          />
        );
      },
      width: 120,
    },
    {
      id: "service_period",
      header: t("contracts.billing.invoices.column.servicePeriod"),
      kind: "text",
      value: (event) =>
        dateRange(
          payloadString(event, "service_period_start"),
          payloadString(event, "service_period_end"),
        ) ?? null,
      render: (event) => {
        const range = dateRange(
          payloadString(event, "service_period_start"),
          payloadString(event, "service_period_end"),
        );
        return range === undefined ? <NoValue /> : <span className="num">{range}</span>;
      },
      width: 232,
    },
    {
      id: "invoiced",
      header: t("contracts.billing.invoices.column.invoiced", { currency }),
      kind: "money",
      value: (event) => amount(event, false),
      currency: (event) => payloadMoney(event, currency)?.currency ?? currency,
      width: 176,
    },
    {
      id: "credited",
      header: t("contracts.billing.invoices.column.credited", { currency }),
      kind: "money",
      value: (event) => amount(event, true),
      currency: (event) => payloadMoney(event, currency)?.currency ?? currency,
      width: 176,
    },
    {
      id: "effective_date",
      header: t("contracts.billing.invoices.column.effectiveDate"),
      kind: "date",
      value: (event) => event.effective_date,
      width: 136,
    },
    {
      id: "origin",
      header: t("contracts.billing.invoices.column.origin"),
      kind: "text",
      value: eventOriginText,
      width: 176,
    },
    {
      id: "recorded_at",
      header: t("contracts.billing.invoices.column.recordedAt"),
      kind: "timestamp",
      value: (event) => event.recorded_at,
      width: 192,
    },
  ];
}

function InvoicesGrid({
  contract,
  context,
  obligations,
  ctxSearch,
}: {
  readonly contract: Contract;
  readonly context: RecordContext;
  readonly obligations: readonly Obligation[];
  readonly ctxSearch: string;
}) {
  const columns = useMemo(
    () => invoiceColumns(contract, obligations, ctxSearch),
    [contract, obligations, ctxSearch],
  );
  const defaultColumns = useMemo(() => initialColumnState(columns, INVOICE_HIDDEN), [columns]);
  const [columnState, setColumnState] = useState<GridColumnState>(defaultColumns);
  const source: GridSource<ContractEvent> = {
    queryKey: billingEventsKey(contract.id, context.knownAt),
    fetchPage: (cursor, sort) => fetchBillingEventsPage(contract.id, context.knownAt, cursor, sort),
  };
  return (
    <div className="flex flex-col">
      <DataGrid<ContractEvent>
        name="invoices"
        title={t("contracts.billing.invoices.title")}
        errorTitle={t("contracts.billing.invoices.loadError")}
        countLabel={(count, formatted) =>
          t("contracts.billing.invoices.count", { count, formatted })
        }
        columns={columns}
        source={source}
        rowKey={(event) => event.id}
        rowLabel={documentOf}
        testIdPrefix="SF-03"
        rowTestKey={documentOf}
        columnState={columnState}
        defaultColumnState={defaultColumns}
        onColumnStateChange={setColumnState}
        emptyState={
          <EmptyState
            title={t("contracts.billing.invoices.empty")}
            description={t("contracts.billing.invoices.emptyDescription")}
            headingLevel={3}
          />
        }
      />
    </div>
  );
}

export function BillingTab({
  contract,
  context,
  obligations,
  explainContext,
  ctxSearch,
}: WorkbenchTabProps) {
  return (
    <div className="flex flex-col gap-4">
      <BalancesPanel contract={contract} context={context} explainContext={explainContext} />
      <InvoicesGrid
        contract={contract}
        context={context}
        obligations={obligations}
        ctxSearch={ctxSearch}
      />
    </div>
  );
}
