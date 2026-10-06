// SF-02 Contracts list (SCREENS §3.1 to §3.12; §0.4 RT-08; §0.5 SCR-URL-01, SCR-URL-07 to SCR-URL-10,
// SCR-URL-21; §0.6 SCR-PERM-01, SCR-PERM-02; §0.7 SCR-ST-01 to SCR-ST-06; §0.8 E-17; §1.3 SF-02 context;
// DESIGN_SYSTEM DS-CMP-10, DS-CMP-13, DS-CMP-19, DS-CMP-23; 04 API-R-28, API-R-16; docs/dev-guide.md
// DG-FE-03 to DG-FE-08; BUILD_SPEC CTR-21). The h1 "Contracts" with "<n> contracts" from
// `X-Erev-Total-Count`, then the DataGrid "Contracts" with the saved-view selector (quick lists first),
// the FilterBar and the selection bar. The URL holds the grid state (`view`, `q`, `sort`, `f.*`); the
// context `entity` (absent: all entities, SCR-URL-01; an Entity chip replaces it), `book` and the end date
// of the context period as `as_of` reach the read. Actions and links whose route is not built do not render
// (XR-14); the export menu and the currency view switch are not rendered (L5-4-Q-14, L5-4-Q-15). Amounts
// are the API's strings and no cell shows a signed balance of the contract (DS-FMT-28; D-12).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import { SavedViewSelector, VIEW_PARAM } from "../../components/data-grid/SavedViewSelector";
import {
  type GridColumn,
  type GridColumnState,
  type GridSelection,
  type GridSource,
  initialColumnState,
} from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import {
  FILTER_PREFIX,
  type Filter,
  type FilterField,
  parseFilters,
  withFilters,
} from "../../components/filter-bar/filters";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { DotsThree } from "../../components/icons/registry";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { Menu, type MenuItem } from "../../components/ui/Menu";
import { Modal } from "../../components/ui/Modal";
import { chipFor, OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { isTypingTarget } from "../../lib/a11y/typing";
import { useCommandKeys } from "../../lib/api/commands";
import { currencyRegistered } from "../../lib/api/queries/approvals";
import {
  type BulkAction,
  type BulkResult,
  commandContracts,
  CONTRACT_CREATE_PERMISSION,
  CONTRACT_LIST_KEYS,
  CONTRACT_READ_PERMISSION,
  CONTRACT_STATUSES,
  type ContractListItem,
  type ContractListQuery,
  type ContractSourceSystem,
  contractsKey,
  type Customer,
  customersKey,
  fetchContractsPage,
  fetchCustomers,
  type HoldType,
  QUICK_LISTS,
  quickList,
} from "../../lib/api/queries/contracts";
import { type Me, useMe } from "../../lib/api/queries/me";
import { useCreateSavedView } from "../../lib/api/queries/saved-views";
import {
  type Entity,
  entitiesKey,
  fetchActiveEntities,
  fetchPeriods,
  type Period,
  periodLabel,
  periodsKey,
  STRUCTURE_READ_PERMISSION,
} from "../../lib/api/queries/tenant";
import { formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { decodeValue, rawParams, withParams } from "../../lib/url/params";
import { useBuiltPaths } from "../settings/index";

/** SCREENS SCR-IA-07 screen code of the grid's saved views. */
export const SCREEN_CODE = "SF-02";
/** SCREENS RT-10 SF-03, the record route of a row. */
export const CONTRACT_ROUTE = "/contracts/:contractId/obligations";
/** SCREENS_B SF-15:customer, the target of the Customer cell. */
export const CUSTOMER_ROUTE = "/settings/customers/:customerId";
export const NEW_CONTRACT_ROUTE = "/contracts/new";
export const REVIEW_DOCUMENT_ROUTE = "/contracts/review/new";
export const DEAL_PREVIEW_ROUTE = "/contracts/deal-preview";
export const NEW_IMPORT_ROUTE = "/data/imports/new";
export const HOME_ROUTE = "/home";

/** SCREENS §3.5 columns hidden by default. */
export const HIDDEN_BY_DEFAULT: readonly string[] = [
  "scheduled",
  "awaiting_trigger",
  "contract_no",
  "source",
  "region",
  "channel",
  "contract_type",
  "signature_date",
  "updated_at",
];

/** SCREENS §3.5 column 15 labels of E-38 `source_system`. */
const SOURCE_KEYS: Readonly<Record<ContractSourceSystem, string>> = {
  LEGACY_TEMPLATE_V1: "legacyTemplate",
  CSV_V2: "csv",
  API: "api",
  MANUAL_UI: "manual",
  SALESFORCE: "salesforce",
  STRIPE: "stripe",
  NETSUITE: "netsuite",
  QUICKBOOKS_ONLINE: "quickbooks",
  LEGACY_DB: "legacyDatabase",
};

type Kpis = NonNullable<ContractListItem["kpis"]>;
type KpiName = keyof Kpis;

export function contractPath(contract: Pick<ContractListItem, "id">): string {
  return `/contracts/${contract.id}/obligations`;
}

/** SCREENS §3.5 column 3: the E-17 chip, "On hold", and the outline "Combined" of a group member. */
function StatusCell({ contract }: { readonly contract: ContractListItem }) {
  const chip = chipFor("E-17", contract.status);
  return (
    <span className="inline-flex items-center gap-1">
      {chip === null ? null : <StatusChip status={chip.status} />}
      {contract.on_hold ? <StatusChip status="On hold" /> : null}
      {contract.combination_group.is_singleton ? null : (
        <OutlineChip label={t("contracts.list.combined")} />
      )}
    </span>
  );
}

function mono(text: string | null): ReactNode {
  return text === null ? null : <span className="font-mono text-mono-sm text-fg-1">{text}</span>;
}

/** A money column of a KPI; an amount whose currency is not registered shows no value (DS-FMT-03). */
function kpiColumn(
  id: string,
  kpi: KpiName,
  headerKey: string,
  sortKey?: string,
): GridColumn<ContractListItem> {
  return {
    id,
    header: t(headerKey),
    kind: "money",
    value: (contract) => {
      const figure = contract.kpis?.[kpi];
      return figure === undefined || !currencyRegistered(figure.currency) ? null : figure.amount;
    },
    currency: (contract) => contract.kpis?.[kpi].currency ?? contract.transaction_currency,
    sortKey,
    // DS-CMP-10: amounts are never truncated; the width holds the longest header.
    width: 176,
  };
}

export interface ColumnOptions {
  readonly built: ReadonlySet<string>;
  readonly rowActions?: ((contract: ContractListItem) => readonly MenuItem[]) | undefined;
}

/** SCREENS §3.5 grid columns in order. */
export function contractColumns({
  built,
  rowActions,
}: ColumnOptions): readonly GridColumn<ContractListItem>[] {
  const recordBuilt = built.has(CONTRACT_ROUTE);
  const customerBuilt = built.has(CUSTOMER_ROUTE);
  const columns: GridColumn<ContractListItem>[] = [
    {
      id: "contract",
      header: t("contracts.list.column.contract"),
      kind: "identifier",
      value: (contract) => contract.external_id,
      href: recordBuilt ? contractPath : undefined,
      width: 160,
    },
    {
      id: "customer",
      header: t("contracts.list.column.customer"),
      kind: "text",
      value: (contract) => contract.customer.name,
      render: customerBuilt
        ? (contract) => (
            <Link
              to={`/settings/customers/${contract.customer.id}`}
              tabIndex={-1}
              className="truncate text-fg-1 underline decoration-control decoration-dotted underline-offset-3 hover:decoration-fg-1 hover:decoration-solid"
            >
              {contract.customer.name}
            </Link>
          )
        : undefined,
      width: 208,
    },
    {
      id: "status",
      header: t("contracts.list.column.status"),
      kind: "status",
      value: (contract) => contract.status,
      render: (contract) => <StatusCell contract={contract} />,
      width: 176,
    },
    {
      id: "entity",
      header: t("contracts.list.column.entity"),
      kind: "text",
      value: (contract) => contract.contracting_entity.code,
      render: (contract) => mono(contract.contracting_entity.code),
      width: 96,
    },
    {
      id: "inception_date",
      header: t("contracts.list.column.inceptionDate"),
      kind: "date",
      value: (contract) => contract.inception_date,
      sortKey: "inception_date",
      width: 152,
    },
    {
      id: "currency",
      header: t("contracts.list.column.currency"),
      kind: "text",
      value: (contract) => contract.transaction_currency,
      render: (contract) => mono(contract.transaction_currency),
      width: 104,
    },
    kpiColumn(
      "transaction_price",
      "transaction_price",
      "contracts.list.column.transactionPrice",
      "transaction_price",
    ),
    kpiColumn("revenue_to_date", "revenue_to_date", "contracts.list.column.recognizedToDate"),
    kpiColumn("billed_to_date", "billed_to_date", "contracts.list.column.billedToDate"),
    kpiColumn("rpo", "rpo", "contracts.list.column.rpo"),
    {
      id: "open_exceptions",
      header: t("contracts.list.column.openExceptions"),
      kind: "number",
      numberKind: "count",
      value: (contract) => String(contract.open_exception_count),
      width: 152,
    },
    kpiColumn("scheduled", "scheduled", "contracts.list.column.scheduled"),
    kpiColumn("awaiting_trigger", "awaiting_trigger", "contracts.list.column.awaitingTrigger"),
    {
      id: "contract_no",
      header: t("contracts.list.column.contractNumber"),
      kind: "text",
      value: (contract) => contract.contract_no,
      render: (contract) => mono(contract.contract_no),
      sortKey: "contract_no",
      width: 160,
    },
    {
      id: "source",
      header: t("contracts.list.column.source"),
      kind: "text",
      value: (contract) => t(`contracts.list.source.${SOURCE_KEYS[contract.source_system]}`),
    },
    {
      id: "region",
      header: t("contracts.list.column.region"),
      kind: "text",
      value: (contract) => contract.region,
    },
    {
      id: "channel",
      header: t("contracts.list.column.channel"),
      kind: "text",
      value: (contract) => contract.channel,
    },
    {
      id: "contract_type",
      header: t("contracts.list.column.contractType"),
      kind: "text",
      value: (contract) => contract.contract_type,
    },
    {
      id: "signature_date",
      header: t("contracts.list.column.signatureDate"),
      kind: "date",
      value: (contract) => contract.signature_date,
      width: 144,
    },
    {
      id: "updated_at",
      header: t("contracts.list.column.updated"),
      kind: "timestamp",
      value: (contract) => contract.updated_at,
      sortKey: "updated_at",
    },
  ];
  if (rowActions !== undefined) {
    columns.push({
      id: "actions",
      header: t("contracts.list.column.actions"),
      kind: "actions",
      value: () => null,
      render: (contract) => (
        <Menu
          label={t("contracts.list.row.menu", { contract: contract.external_id })}
          icon={DotsThree}
          iconOnly
          variant="ghost"
          size="sm"
          align="end"
          items={rowActions(contract)}
        />
      ),
    });
  }
  return columns;
}

/** The values of the URL chip `f.<field>`, read before the field's options have loaded. */
export function urlChipValues(search: string, field: string): readonly string[] {
  const param = rawParams(search).find((item) => item.name === `${FILTER_PREFIX}${field}`);
  const colon = param?.value.indexOf(":") ?? -1;
  if (param === undefined || colon < 0) {
    return [];
  }
  return param.value
    .slice(colon + 1)
    .split(",")
    .map(decodeValue)
    .filter((value) => value !== "");
}

export interface FilterSources {
  readonly search: string;
  readonly entities?: readonly Entity[] | undefined;
  readonly customers?: readonly Customer[] | undefined;
  readonly periods?: readonly Period[] | undefined;
}

/**
 * SCREENS §3.6 filters. While entities or customers load, the chip's own values stand in as options, so
 * a link's chips are not dropped under SCR-URL-21 before the options arrive.
 */
export function contractFilterFields({
  search,
  entities,
  customers,
  periods,
}: FilterSources): readonly FilterField[] {
  const pending = (field: string) =>
    urlChipValues(search, field).map((value) => ({ value, label: value }));
  return [
    {
      name: "entity",
      label: t("contracts.list.filter.entity"),
      kind: "enum",
      // SCREENS §3.6 "is, in": one value is `is`, several `in` (DS-CMP-13 editor).
      operators: ["is", "in"],
      options:
        entities === undefined
          ? pending("entity")
          : entities.map((entity) => ({ value: entity.code, label: entity.code })),
      optionsLoading: entities === undefined,
    },
    {
      name: "customer",
      label: t("contracts.list.filter.customer"),
      kind: "user",
      operators: ["is"],
      options:
        customers === undefined
          ? pending("customer")
          : customers.map((customer) => ({ value: customer.id, label: customer.name })),
      optionsLoading: customers === undefined,
    },
    {
      name: "status",
      label: t("contracts.list.filter.status"),
      kind: "enum",
      // SCREENS §3.6 "is, in": one value is `is`, several `in` (DS-CMP-13 editor).
      operators: ["is", "in"],
      options: CONTRACT_STATUSES.map((status) => ({
        value: status,
        label: chipFor("E-17", status)?.status ?? status,
      })),
    },
    {
      name: "on_hold",
      label: t("contracts.list.filter.onHold"),
      kind: "boolean",
      operators: ["is"],
    },
    {
      name: "modified_in_period",
      label: t("contracts.list.filter.modifiedInPeriod"),
      kind: "period",
      operators: ["is"],
      periods: periods?.map((item) => ({
        key: item.period.period_key,
        label: periodLabel(item.period),
        fiscalYear: `FY${String(item.period.fiscal_year)}`,
        state: item.state,
      })),
    },
    {
      name: "transaction_price",
      label: t("contracts.list.filter.transactionPrice"),
      kind: "money",
      operators: ["between", "gte", "lte"],
    },
    {
      name: "has_exceptions",
      label: t("contracts.list.filter.hasExceptions"),
      kind: "boolean",
      operators: ["is"],
    },
  ];
}

export interface ListContext {
  readonly entity: string | null;
  readonly book: string | null;
  readonly asOf: string | null;
}

function flag(filter: Filter | undefined): boolean | null {
  return filter === undefined ? null : filter.values[0] === "true";
}

/** The API query of a grid state: chips, quick search, quick list and the context (SCREENS §3.4). */
export function contractQuery(
  search: string,
  fields: readonly FilterField[],
  context: ListContext,
): ContractListQuery {
  const parsed = parseFilters(search, fields);
  const chip = (name: string) => parsed.filters.find((filter) => filter.field === name);
  const price = chip("transaction_price");
  const view = rawParams(search).find((param) => param.name === VIEW_PARAM);
  const entities = chip("entity")?.values;
  return {
    entity: entities ?? (context.entity === null ? [] : [context.entity]),
    customer: chip("customer")?.values[0] ?? null,
    status: chip("status")?.values ?? [],
    onHold: flag(chip("on_hold")),
    modifiedInPeriod: chip("modified_in_period")?.values[0] ?? null,
    valueMin:
      price?.operator === "between" || price?.operator === "gte" ? (price.values[0] ?? null) : null,
    valueMax:
      price?.operator === "between"
        ? (price.values[1] ?? null)
        : price?.operator === "lte"
          ? (price.values[0] ?? null)
          : null,
    hasExceptions: flag(chip("has_exceptions")),
    quickList: quickList(view === undefined ? null : decodeValue(view.value))?.literal ?? null,
    q: parsed.query === "" ? null : parsed.query,
    book: context.book,
    asOf: context.asOf,
  };
}

function PageHeader({
  count,
  actions,
}: {
  readonly count?: string | undefined;
  readonly actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-center gap-3">
      <h1 tabIndex={-1} className="text-title-lg text-fg-1">
        {t("contracts.list.title")}
      </h1>
      {count === undefined ? null : <span className="num text-body text-fg-3">{count}</span>}
      <span className="flex-1" />
      {actions}
    </header>
  );
}

export function ContractsList() {
  const me = useMe();
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={t("contracts.list.title")} shape="rows" count={10} />;
  } else if (!me.data.permissions.includes(CONTRACT_READ_PERMISSION)) {
    body = (
      <EmptyState
        title={t("settings.access.title", { area: t("contracts.access.area") })}
        description={t("settings.access.description", {
          permission: t("contracts.access.permission"),
        })}
      />
    );
  } else {
    return <ContractsPage me={me.data} />;
  }
  return (
    <div data-testid="SF-02-page" className="flex flex-col gap-4">
      <PageHeader />
      {body}
    </div>
  );
}

type BulkRun = { readonly kind: "submit" | "hold"; readonly result: BulkResult };

function ContractsPage({ me }: { readonly me: Me }) {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  // The keys of the bulk commands: a contract whose answer was lost goes out under the same key when
  // the action is run again (DG-FE-05 rev 1.156).
  const keys = useCommandKeys();
  const built = useBuiltPaths();
  const permissions = me.permissions;
  const canCreate = permissions.includes(CONTRACT_CREATE_PERMISSION);
  const structure = permissions.includes(STRUCTURE_READ_PERMISSION);
  const search = location.search;

  // SCREENS §1.3 SF-02: entity (absent means all entities), period (drives `as_of`) and book.
  const context = new URLSearchParams(search);
  const entity = context.get("entity");
  const period = context.get("period");
  const book = context.get("book");
  const entities = useQuery({
    queryKey: entitiesKey(),
    queryFn: fetchActiveEntities,
    enabled: structure,
  });
  const customers = useQuery({ queryKey: customersKey(), queryFn: fetchCustomers });
  const periodQuery = { entity: entity ?? "", book: book ?? "" };
  const periodsEnabled = structure && entity !== null && book !== null;
  const periods = useQuery({
    queryKey: periodsKey(periodQuery),
    queryFn: () => fetchPeriods(periodQuery),
    enabled: periodsEnabled,
  });
  const asOf =
    periods.data?.find((item) => item.period.period_key === period)?.period.end_date ?? null;
  const contextReady = !periodsEnabled || period === null || !periods.isPending;

  const fields = useMemo(
    () =>
      contractFilterFields({
        search,
        entities: entities.data,
        customers: customers.data,
        periods: periods.data,
      }),
    [search, entities.data, customers.data, periods.data],
  );
  const query = contractQuery(search, fields, { entity, book, asOf });
  const activeQuick = quickList(query.quickList);

  // Loaded rows by id of the current filters: the selection bar commands the selected contracts with
  // their stream versions, and "all matching" means the loaded rows of these filters.
  const listKey = contractsKey(query);
  const loaded = useRef({ key: "", rows: new Map<string, ContractListItem>() });
  const keyText = JSON.stringify(listKey);
  if (loaded.current.key !== keyText) {
    loaded.current = { key: keyText, rows: new Map() };
  }
  const source: GridSource<ContractListItem> = {
    queryKey: listKey,
    fetchPage: async (cursor, sort) => {
      const page = await fetchContractsPage(query, cursor, sort);
      for (const item of page.items) {
        loaded.current.rows.set(item.id, item);
      }
      return page;
    },
  };
  const [total, setTotal] = useState<number | undefined>(undefined);

  const pin = useCreateSavedView();
  const rowActions = built.has(CONTRACT_ROUTE)
    ? (contract: ContractListItem): readonly MenuItem[] => {
        const path = contractPath(contract);
        const items: MenuItem[] = [
          { id: "open", label: t("contracts.list.row.open"), onSelect: () => void navigate(path) },
          {
            id: "open-new-tab",
            label: t("contracts.list.row.openNewTab"),
            onSelect: () => {
              window.open(path, "_blank", "noopener");
            },
          },
        ];
        if (built.has(HOME_ROUTE)) {
          items.push({
            id: "pin",
            label: t("contracts.list.bulk.pin"),
            onSelect: () => {
              void pin
                .submit({
                  screen_code: "SF-03",
                  name: contract.external_id,
                  config: { target: "contract", path, label: contract.external_id },
                  is_shared: false,
                  is_favourite: true,
                })
                .then((outcome) => {
                  if (outcome.kind === "succeeded") {
                    toast.show({ tone: "positive", message: t("contracts.list.row.pinned") });
                  }
                });
            },
          });
        }
        items.push({
          id: "copy-link",
          label: t("contracts.list.row.copyLink"),
          onSelect: () => {
            void navigator.clipboard
              .writeText(new URL(path, window.location.origin).href)
              .then(() => toast.show({ tone: "neutral", message: t("contracts.list.row.copied") }));
          },
        });
        return items;
      }
    : undefined;
  const columns = useMemo(
    () => contractColumns({ built, rowActions }),
    // The row actions depend only on the built routes; their handlers read the latest hooks.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [built],
  );
  const defaultColumns = useMemo(() => initialColumnState(columns, HIDDEN_BY_DEFAULT), [columns]);
  const [columnState, setColumnState] = useState<GridColumnState>(defaultColumns);

  // SCREENS §3.9: `/` focuses the quick search when focus is not in a field.
  const pageRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "/" || event.defaultPrevented || isTypingTarget(event.target)) {
        return;
      }
      const input = pageRef.current?.querySelector<HTMLInputElement>("[role='toolbar'] input");
      if (input !== null && input !== undefined) {
        event.preventDefault();
        input.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  // SCREENS §3.7 selection bar.
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [holdTargets, setHoldTargets] = useState<readonly ContractListItem[] | null>(null);
  const [run, setRun] = useState<BulkRun | null>(null);
  const selected = (selection: GridSelection): ContractListItem[] =>
    selection.allMatching
      ? [...loaded.current.rows.values()]
      : [...selection.ids].flatMap((id) => loaded.current.rows.get(id) ?? []);
  const execute = async (
    kind: BulkRun["kind"],
    action: BulkAction,
    contracts: readonly ContractListItem[],
    skip: (contract: ContractListItem) => string | null,
  ) => {
    setProgress({ done: 0, total: contracts.length });
    const result = await commandContracts(
      keys,
      action,
      contracts,
      skip,
      (done, count) => setProgress({ done, total: count }),
      t("contracts.list.bulk.notReached"),
    );
    setProgress(null);
    await Promise.all(
      CONTRACT_LIST_KEYS.map((key) => queryClient.invalidateQueries({ queryKey: key })),
    );
    setRun({ kind, result });
  };
  const bulkActions = canCreate
    ? (selection: GridSelection) => (
        <>
          {progress === null ? null : (
            <span role="status" className="num text-body-sm text-fg-2">
              {t("contracts.list.bulk.progress", {
                done: formatNumber(progress.done, { kind: "count" }),
                total: formatNumber(progress.total, { kind: "count" }),
              })}
            </span>
          )}
          <Button
            variant="secondary"
            size="sm"
            disabledReason={progress === null ? undefined : t("contracts.list.bulk.running")}
            onClick={() =>
              void execute("submit", { kind: "submit-activation" }, selected(selection), (item) =>
                item.status === "DRAFT" ? null : t("contracts.list.bulk.notDraft"),
              )
            }
          >
            {t("contracts.list.bulk.submit")}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabledReason={progress === null ? undefined : t("contracts.list.bulk.running")}
            onClick={() => setHoldTargets(selected(selection))}
          >
            {t("contracts.list.bulk.hold")}
          </Button>
        </>
      )
    : undefined;

  const showAll = () => {
    void navigate({ search: withParams(search, { [VIEW_PARAM]: null, sort: null }) });
  };
  const clearFilters = () => {
    void navigate({ search: withFilters(search, "", []) }, { replace: true });
  };
  const importAction =
    built.has(NEW_IMPORT_ROUTE) && permissions.includes("import.upload")
      ? {
          label: t("contracts.list.import"),
          onAction: () => void navigate(`${NEW_IMPORT_ROUTE}?template=contracts`),
        }
      : undefined;

  const headerActions: ReactNode[] = [];
  if (
    built.has(REVIEW_DOCUMENT_ROUTE) &&
    permissions.includes("ai.use") &&
    me.tenant_settings.ai_enabled
  ) {
    headerActions.push(
      <Button key="review" variant="secondary" onClick={() => void navigate(REVIEW_DOCUMENT_ROUTE)}>
        {t("contracts.list.review")}
      </Button>,
    );
  }
  if (built.has(DEAL_PREVIEW_ROUTE) && permissions.includes("scenario.use")) {
    headerActions.push(
      <Button key="deal" variant="secondary" onClick={() => void navigate(DEAL_PREVIEW_ROUTE)}>
        {t("contracts.list.dealPreview")}
      </Button>,
    );
  }
  if (built.has(NEW_CONTRACT_ROUTE) && canCreate) {
    headerActions.push(
      <Button key="new" variant="primary" onClick={() => void navigate(NEW_CONTRACT_ROUTE)}>
        {t("contracts.list.new")}
      </Button>,
    );
  }
  if (importAction !== undefined) {
    headerActions.push(
      <Menu
        key="more"
        label={t("contracts.list.moreActions")}
        icon={DotsThree}
        iconOnly
        variant="ghost"
        align="end"
        items={[{ id: "import", label: importAction.label, onSelect: importAction.onAction }]}
      />,
    );
  }

  const countText =
    total === undefined
      ? undefined
      : t("contracts.list.count", {
          count: total,
          formatted: formatNumber(total, { kind: "count" }),
        });

  return (
    <div ref={pageRef} data-testid="SF-02-page" className="flex h-full min-h-0 flex-col gap-4">
      <PageHeader count={countText} actions={headerActions} />
      {contextReady ? (
        <div className="flex min-h-0 flex-1 flex-col">
          <DataGrid<ContractListItem>
            name="contracts"
            title={t("contracts.list.title")}
            titleVisible={false}
            errorTitle={t("contracts.list.loadError")}
            countLabel={(count, formatted) => t("contracts.list.count", { count, formatted })}
            columns={columns}
            source={source}
            rowKey={(contract) => contract.id}
            rowLabel={(contract) => contract.external_id}
            rowHref={built.has(CONTRACT_ROUTE) ? contractPath : undefined}
            testIdPrefix="SF-02"
            rowTestKey={(contract) => contract.external_id}
            selectable={canCreate}
            bulkActions={bulkActions}
            columnState={columnState}
            defaultColumnState={defaultColumns}
            onColumnStateChange={setColumnState}
            onTotalChange={(next) => setTotal(next?.count)}
            viewSelector={
              <SavedViewSelector
                screenCode={SCREEN_CODE}
                membershipId={me.active_membership_id}
                defaultLabel={t("contracts.list.view.default")}
                quickLists={QUICK_LISTS.map((item) => ({
                  literal: item.literal,
                  label: t(`contracts.list.quick.${item.key}`),
                  sort: item.sort,
                }))}
                columnState={columnState}
                defaultColumnState={defaultColumns}
                onApplyColumns={setColumnState}
                testId="SF-02-saved-view"
              />
            }
            filterBar={
              <FilterBar
                fields={fields}
                searchLabel={t("contracts.list.search")}
                resultCount={total}
                resultLabel={(count) =>
                  t("contracts.list.count", {
                    count,
                    formatted: formatNumber(count, { kind: "count" }),
                  })
                }
                testId="SF-02-filter-bar"
              />
            }
            emptyState={
              activeQuick === undefined ? (
                <div data-testid="SF-02-empty-contracts">
                  <EmptyState
                    title={t("contracts.list.empty.title")}
                    description={t("contracts.list.empty.description")}
                    action={importAction}
                  />
                </div>
              ) : (
                <EmptyState
                  title={t("contracts.list.quickEmpty", {
                    label: t(`contracts.list.quick.${activeQuick.key}`),
                  })}
                  description=""
                  action={{ label: t("contracts.list.showAll"), onAction: showAll }}
                />
              )
            }
            noResults={
              <EmptyState
                title={t("contracts.list.noResults")}
                description=""
                action={{ label: t("contracts.list.clearFilters"), onAction: clearFilters }}
              />
            }
          />
        </div>
      ) : (
        <Skeleton region={t("contracts.list.title")} shape="rows" count={10} />
      )}
      {holdTargets === null ? null : (
        <HoldDrawer
          count={Math.min(holdTargets.length, 200)}
          onClose={() => setHoldTargets(null)}
          onApply={(holdType, reason) => {
            const targets = holdTargets;
            setHoldTargets(null);
            void execute("hold", { kind: "apply-hold", holdType, reason }, targets, () => null);
          }}
        />
      )}
      {run === null ? null : <BulkResultModal run={run} onClose={() => setRun(null)} />}
    </div>
  );
}

interface HoldDrawerProps {
  readonly count: number;
  readonly onClose: () => void;
  readonly onApply: (holdType: HoldType, reason: string) => void;
}

/** SCREENS §3.7 "Apply hold to <n> contracts": hold type and a reason of at least 10 characters. */
function HoldDrawer({ count, onClose, onApply }: HoldDrawerProps) {
  const formId = useId();
  const typeName = useId();
  const [holdType, setHoldType] = useState<HoldType>("recognition");
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const types: readonly { readonly value: HoldType; readonly key: string }[] = [
    { value: "recognition", key: "recognition" },
    { value: "journal_export", key: "journalExport" },
  ];
  return (
    <Drawer
      open
      title={t("contracts.list.hold.title", {
        count,
        formatted: formatNumber(count, { kind: "count" }),
      })}
      initialFocus="field"
      dirty={reason !== ""}
      primaryAction={{ label: t("contracts.list.bulk.hold"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          setAttempted(true);
          if (reasonError(reason) === null) {
            onApply(holdType, reason.trim());
          }
        }}
      >
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-body-sm font-medium text-fg-1">
            {t("contracts.list.hold.type")}
          </legend>
          {types.map((type) => (
            <label key={type.value} className="flex items-center gap-2 text-body text-fg-1">
              <input
                type="radio"
                name={typeName}
                value={type.value}
                checked={holdType === type.value}
                onChange={() => setHoldType(type.value)}
              />
              {t(`contracts.list.hold.${type.key}`)}
            </label>
          ))}
        </fieldset>
        <ReasonField
          label={t("contracts.list.hold.reason")}
          value={reason}
          onChange={setReason}
          showError={attempted}
        />
      </form>
    </Drawer>
  );
}

/** SCREENS §3.7 result modal: "Submitted <m> of <n> contracts" and the failures in a static table. */
function BulkResultModal({
  run,
  onClose,
}: {
  readonly run: BulkRun;
  readonly onClose: () => void;
}) {
  const { result } = run;
  const titleKey =
    run.kind === "submit" ? "contracts.list.bulk.submitted" : "contracts.list.bulk.held";
  return (
    <Modal
      open
      variant="form"
      title={t(titleKey, {
        count: result.total,
        done: formatNumber(result.succeeded, { kind: "count" }),
        formatted: formatNumber(result.total, { kind: "count" }),
      })}
      primaryAction={{ label: t("contracts.list.bulk.done"), onAction: onClose }}
      onClose={onClose}
    >
      {result.failures.length === 0 ? null : (
        <table className="w-full text-body-sm">
          <caption className="sr-only">{t("contracts.list.bulk.failures")}</caption>
          <thead>
            <tr className="border-b border-default text-start text-fg-2">
              <th scope="col" className="py-1 pe-3 text-start font-medium">
                {t("contracts.list.bulk.column.contract")}
              </th>
              <th scope="col" className="py-1 pe-3 text-start font-medium">
                {t("contracts.list.bulk.column.problem")}
              </th>
              <th scope="col" className="py-1 text-start font-medium">
                {t("contracts.list.bulk.column.detail")}
              </th>
            </tr>
          </thead>
          <tbody>
            {result.failures.map((failure) => (
              <tr key={failure.contract.id} className="border-b border-hairline align-top">
                <th scope="row" className="py-1 pe-3 text-start font-normal">
                  {mono(failure.contract.external_id)}
                </th>
                <td className="py-1 pe-3 text-fg-1">{failure.problem}</td>
                <td className="py-1 text-fg-2">
                  {failure.detail.length === 0 ? null : (
                    <ul className="flex flex-col gap-0.5">
                      {failure.detail.map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Modal>
  );
}
