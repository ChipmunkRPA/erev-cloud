// SF-03:modifications Modifications tab (SCREENS §4.6; §0.4 RT-17; §0.8 E-26; DESIGN_SYSTEM DS-CMP-10,
// DS-CMP-13, DS-FMT-16, DS-FMT-31; 04 API-R-31 `GET /contracts/{id}/modifications`, §16.14
// API-S-Modification list items; BUILD_SPEC CTR-24). The DataGrid "Modifications" of the contract with the
// Status and Effective date filters: reference (the link to SF-07:detail once that route is built; the
// modification number where no reference was given), kind, effective date, treatment, status, the
// catch-up total of the stored preview and the preparer. The commands "New modification" and "Change
// subscription" are the workbench header's (SCREENS §4.1.6, rev 1.29: the one place); the empty state of
// an active contract keeps "New modification" for a holder of `modification.create` (API-R-31 refuses
// every other status).
import { useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router";

import { DataGrid } from "../../../components/data-grid/DataGrid";
import {
  type GridColumn,
  type GridColumnState,
  type GridSource,
  initialColumnState,
} from "../../../components/data-grid/types";
import { EmptyState } from "../../../components/feedback/EmptyState";
import { FilterBar } from "../../../components/filter-bar/FilterBar";
import {
  type FilterField,
  parseFilters,
  withFilters,
} from "../../../components/filter-bar/filters";
import { Money } from "../../../components/money/Money";
import { NoValue } from "../../../components/money/Num";
import { chipFor, StatusChip, statusMessageKey } from "../../../components/ui/StatusChip";
import type { Contract } from "../../../lib/api/queries/contracts";
import {
  contractModificationsKey,
  fetchContractModificationsPage,
  MODIFICATION_CREATE_PERMISSION,
  MODIFICATION_NEW_ROUTE,
  MODIFICATION_ROUTE,
  MODIFICATION_STATUSES,
  type ModificationListItem,
  type ModificationListQuery,
  modificationRoute,
  TEMPLATE_MODES,
} from "../../../lib/api/queries/modifications";
import type { SubscriptionAction } from "../../../lib/forms/modification";
import { formatNumber } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";
import { useBuiltPaths } from "../../settings/index";
import type { WorkbenchTabProps } from "./schedules";

/** SCREENS §4.6 columns hidden by default. */
export const MODIFICATION_HIDDEN: readonly string[] = ["template_mode"];
/** SF-07 for a new modification, with the context parameters and the optional `action`. */
export function newModificationHref(
  contractId: string,
  ctxSearch: string,
  action?: SubscriptionAction,
): string {
  const params = new URLSearchParams(ctxSearch);
  if (action !== undefined) {
    params.set("action", action);
  }
  const search = params.toString();
  return `/contracts/${contractId}/modifications/new${search === "" ? "" : `?${search}`}`;
}

/**
 * SF-07 for the price change of one obligation (SCREENS §5.8 "Change price", LTM-06; SCR-URL-31):
 * the kind and the obligation are preselected.
 */
export function changePriceHref(
  contractId: string,
  ctxSearch: string,
  obligationId: string,
): string {
  const params = new URLSearchParams(ctxSearch);
  params.set("kind", "PRICE_CHANGE");
  params.set("obligation", obligationId);
  return `/contracts/${contractId}/modifications/new?${params.toString()}`;
}

/** SCREENS §4.1.6: a modification is prepared on an active contract (API-R-31 `invalid-transition`). */
export function acceptsModifications(contract: Pick<Contract, "status">): boolean {
  return contract.status === "ACTIVE";
}

/** SCREENS §4.6 column 1: the reference, else the modification number. */
export function modificationLabel(
  item: Pick<ModificationListItem, "reference" | "modification_no">,
): string {
  return item.reference ?? item.modification_no;
}

function templateModeLabel(mode: string | null): string | null {
  if (mode === null) {
    return null;
  }
  return (TEMPLATE_MODES as readonly string[]).includes(mode)
    ? t(`contracts.modifications.templateMode.${mode}`)
    : mode;
}

interface ColumnSources {
  readonly contract: Contract;
  readonly ctxSearch: string;
  readonly detailBuilt: boolean;
}

function modificationColumns({
  contract,
  ctxSearch,
  detailBuilt,
}: ColumnSources): readonly GridColumn<ModificationListItem>[] {
  const currency = contract.transaction_currency;
  // The seven columns shown by default add up to the panel at 1440 px: no horizontal scroll.
  return [
    {
      id: "reference",
      header: t("contracts.modifications.column.reference"),
      kind: "identifier",
      value: modificationLabel,
      href: detailBuilt
        ? (item) => `${modificationRoute(contract.id, item.id)}${ctxSearch}`
        : undefined,
      sortKey: "modification_no",
      width: 160,
    },
    {
      id: "kind",
      header: t("contracts.modifications.column.kind"),
      kind: "text",
      value: (item) => t(`modification.kind.${item.kind}`),
      width: 148,
    },
    {
      id: "effective_date",
      header: t("contracts.modifications.column.effectiveDate"),
      kind: "date",
      value: (item) => item.effective_date,
      sortKey: "effective_date",
      width: 124,
    },
    {
      id: "treatment",
      header: t("contracts.modifications.column.treatment"),
      kind: "text",
      value: (item) =>
        item.treatment_summary === null
          ? null
          : t(`modifications.treatment.${item.treatment_summary}`),
      width: 272,
    },
    {
      id: "status",
      header: t("contracts.modifications.column.status"),
      kind: "status",
      value: (item) => {
        const chip = chipFor("E-26", item.status);
        return chip === null ? null : t(statusMessageKey(chip.status));
      },
      render: (item) => {
        const chip = chipFor("E-26", item.status);
        return chip === null ? <NoValue /> : <StatusChip status={chip.status} />;
      },
      width: 136,
    },
    {
      id: "catch_up",
      header: t("contracts.modifications.column.catchUp", { currency }),
      kind: "money",
      value: (item) => item.impact_summary.catch_up_total?.amount ?? null,
      currency: (item) => item.impact_summary.catch_up_total?.currency ?? item.currency,
      render: (item) => {
        const total = item.impact_summary.catch_up_total;
        return total === null ? (
          <NoValue />
        ) : (
          <Money value={total.amount} currency={total.currency} variant="cell" delta />
        );
      },
      width: 144,
    },
    {
      id: "prepared_by",
      header: t("contracts.modifications.column.preparedBy"),
      kind: "user",
      value: (item) => item.preparer.display_name,
      width: 152,
    },
    {
      id: "template_mode",
      header: t("contracts.modifications.column.templateMode"),
      kind: "text",
      value: (item) => templateModeLabel(item.template_mode),
      width: 160,
    },
  ];
}

export function ModificationsTab({ contract, me, ctxSearch }: WorkbenchTabProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const built = useBuiltPaths();
  const search = location.search;
  const hidden = new URLSearchParams(search).has("known_at");
  const canPrepare =
    !hidden &&
    built.has(MODIFICATION_NEW_ROUTE) &&
    me.permissions.includes(MODIFICATION_CREATE_PERMISSION) &&
    acceptsModifications(contract);
  const detailBuilt = built.has(MODIFICATION_ROUTE);

  const fields = useMemo(
    (): readonly FilterField[] => [
      {
        name: "status",
        label: t("contracts.modifications.filter.status"),
        kind: "enum",
        operators: ["is", "in"],
        options: MODIFICATION_STATUSES.map((value) => {
          const chip = chipFor("E-26", value);
          return { value, label: chip === null ? value : t(statusMessageKey(chip.status)) };
        }),
      },
      {
        name: "effective_date",
        label: t("contracts.modifications.filter.effectiveDate"),
        kind: "date",
        operators: ["between", "gte", "lte"],
      },
    ],
    [],
  );
  const parsed = parseFilters(search, fields);
  const status = parsed.filters.find((filter) => filter.field === "status")?.values ?? [];
  const dates = parsed.filters.find((filter) => filter.field === "effective_date");
  const query: ModificationListQuery = {
    contractId: contract.id,
    status,
    effectiveFrom:
      dates === undefined || dates.operator === "lte" ? null : (dates.values[0] ?? null),
    effectiveTo:
      dates === undefined || dates.operator === "gte"
        ? null
        : ((dates.operator === "between" ? dates.values[1] : dates.values[0]) ?? null),
  };
  const source: GridSource<ModificationListItem> = {
    queryKey: contractModificationsKey(query),
    fetchPage: (cursor, sort) => fetchContractModificationsPage(query, cursor, sort),
  };
  const columns = useMemo(
    () => modificationColumns({ contract, ctxSearch, detailBuilt }),
    [contract, ctxSearch, detailBuilt],
  );
  const defaultColumns = useMemo(() => initialColumnState(columns, MODIFICATION_HIDDEN), [columns]);
  const [columnState, setColumnState] = useState<GridColumnState>(defaultColumns);
  const [total, setTotal] = useState<number | undefined>(undefined);
  const open = () => void navigate(newModificationHref(contract.id, ctxSearch));
  const clearFilters = () => {
    void navigate({ search: withFilters(search, "", []) }, { replace: true });
  };

  return (
    // An empty list does not hold the panel open: its empty state follows the header row.
    <div className={total === 0 ? "flex flex-col" : "flex min-h-120 flex-col"}>
      <DataGrid<ModificationListItem>
        name="modifications"
        title={t("contracts.workbench.tabs.modifications")}
        errorTitle={t("contracts.modifications.loadError")}
        countLabel={(count, formatted) => t("contracts.modifications.count", { count, formatted })}
        columns={columns}
        source={source}
        rowKey={(item) => item.id}
        rowLabel={modificationLabel}
        rowHref={
          detailBuilt
            ? (item) => `${modificationRoute(contract.id, item.id)}${ctxSearch}`
            : undefined
        }
        testIdPrefix="SF-03"
        rowTestKey={modificationLabel}
        columnState={columnState}
        defaultColumnState={defaultColumns}
        onColumnStateChange={setColumnState}
        onTotalChange={(next) => setTotal(next?.count)}
        filterBar={
          <FilterBar
            fields={fields}
            resultCount={total}
            resultLabel={(value) =>
              t("contracts.modifications.count", {
                count: value,
                formatted: formatNumber(value, { kind: "count" }),
              })
            }
            testId="SF-03-filter-bar-modifications"
          />
        }
        emptyState={
          <EmptyState
            title={t("contracts.modifications.empty")}
            description={t("contracts.modifications.emptyDescription")}
            headingLevel={3}
            action={
              canPrepare
                ? {
                    label: t("contracts.workbench.action.newModification"),
                    onAction: () => open(),
                  }
                : undefined
            }
          />
        }
        noResults={
          <EmptyState
            title={t("contracts.modifications.noResults")}
            description=""
            headingLevel={3}
            action={{ label: t("contracts.list.clearFilters"), onAction: clearFilters }}
          />
        }
      />
    </div>
  );
}
