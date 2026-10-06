// SF-03:schedules Schedules tab (SCREENS §4.3; §0.4 RT-14; SCR-IA-07 `SF-03:schedules#revenue`;
// DESIGN_SYSTEM DS-CMP-10, DS-CMP-13, DS-CMP-15, DS-FMT-04, DS-FMT-19; 04 API-R-35; BUILD_SPEC CTR-23).
// Panel 1 "Revenue schedule": the DataGrid of the contract's revenue schedule lines with the From period,
// To period, Obligation and Line type filters and saved views. Every Amount cell is an Explain trigger
// (`schedule_line~<id>~amount`), and the obligation key links to SF-03:obligation.
// Not rendered (XR-14): panel 2 "Contract costs" (R-RC-1, CTR-14 post-rc; L5-4-Q-51), panel 3 "Loss
// provision" (no `GET /contracts/{id}/loss-provisions` route; L5-4-Q-52) and the export menu (L5-4-Q-15).
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { DataGrid } from "../../../components/data-grid/DataGrid";
import { SavedViewSelector } from "../../../components/data-grid/SavedViewSelector";
import {
  type GridColumn,
  type GridColumnState,
  type GridSource,
  initialColumnState,
} from "../../../components/data-grid/types";
import {
  type ExplainActions,
  ExplainTrigger,
  type FigureRef,
  useExplain,
} from "../../../components/explain/ExplainTrigger";
import { EmptyState } from "../../../components/feedback/EmptyState";
import { FilterBar } from "../../../components/filter-bar/FilterBar";
import {
  FILTER_PREFIX,
  type FilterField,
  parseFilters,
  withFilters,
} from "../../../components/filter-bar/filters";
import type { PeriodOption } from "../../../components/form/PeriodInput";
import { Money } from "../../../components/money/Money";
import { NoValue } from "../../../components/money/Num";
import type { Contract, RecordContext } from "../../../lib/api/queries/contracts";
import type { Me } from "../../../lib/api/queries/me";
import type { Obligation } from "../../../lib/api/queries/obligations";
import {
  fetchScheduleLinesPage,
  REVENUE_SCHEDULE_SCREEN_CODE,
  SCHEDULE_LINE_TYPES,
  type ScheduleLine,
  type ScheduleLineQuery,
  scheduleLinesKey,
} from "../../../lib/api/queries/schedule-lines";
import {
  fetchPeriods,
  type Period,
  periodLabel,
  periodsKey,
  STRUCTURE_READ_PERMISSION,
} from "../../../lib/api/queries/tenant";
import { formatNumber } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";
import { decodeValue, rawParams } from "../../../lib/url/params";
import { figureFromLink, moneyText } from "../obligation-pane";

/** The workbench facts every tab reads (SCREENS §4.1.7 context). */
export interface WorkbenchTabProps {
  readonly contract: Contract;
  readonly context: RecordContext;
  readonly obligations: readonly Obligation[];
  /** True while the contract's obligations load: chips naming an obligation are kept meanwhile. */
  readonly obligationsLoading: boolean;
  /** The Explain panel context line, for example "SF-ORD-10002 · ASC 606 · AVM-US". */
  readonly explainContext: string;
  readonly me: Me;
  /** The SCREENS §0.5 context parameters a record link keeps, for example "?entity=AVM-US". */
  readonly ctxSearch: string;
}

/** SCREENS §4.3 columns hidden by default. */
export const SCHEDULE_HIDDEN: readonly string[] = ["quantity", "entity"];

/** The values of one `f.<field>` chip in the URL, before its options have loaded (SCR-URL-21). */
export function chipValues(search: string, field: string): readonly string[] {
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

/** The book of the reads: the context book, else the version's book. */
export function readBook(contract: Contract, context: RecordContext): string | null {
  return context.book ?? contract.context?.book ?? null;
}

/** DS-CMP-13 period options of an entity's calendar in the book. */
export function periodOptions(periods: readonly Period[] | undefined): PeriodOption[] | undefined {
  return periods?.map((item) => ({
    key: item.period.period_key,
    label: periodLabel(item.period),
    fiscalYear: `FY${String(item.period.fiscal_year)}`,
    state: item.state,
  }));
}

/** The periods of the contracting entity in the book, for the period filters; needs `config.read`. */
export function useContractPeriods(contract: Contract, context: RecordContext, me: Me) {
  const book = readBook(contract, context);
  const query = { entity: contract.contracting_entity.code, book: book ?? "" };
  return useQuery({
    queryKey: periodsKey(query),
    queryFn: () => fetchPeriods(query),
    enabled: book !== null && me.permissions.includes(STRUCTURE_READ_PERMISSION),
  });
}

/** SF-03:obligation of an obligation with the context parameters; null when it cannot be resolved. */
export function obligationHref(
  contract: Contract,
  obligation: Obligation | undefined,
  ctxSearch: string,
): string | null {
  return obligation === undefined
    ? null
    : `/contracts/${contract.id}/obligations/${obligation.id}${ctxSearch}`;
}

/** SCREENS §4.3 column 2, §4.4 column 4, §4.5 column 10: the obligation key in mono, as a link. */
export function ObligationKeyCell({
  obligationKey,
  href,
}: {
  readonly obligationKey: string | null;
  readonly href: string | null;
}) {
  if (obligationKey === null) {
    return <NoValue />;
  }
  return href === null ? (
    <span className="font-mono text-mono-sm text-fg-1">{obligationKey}</span>
  ) : (
    <Link
      to={href}
      tabIndex={-1}
      className="font-mono text-mono-sm text-fg-1 underline decoration-control decoration-dotted underline-offset-3 hover:decoration-fg-1 hover:decoration-solid"
    >
      {obligationKey}
    </Link>
  );
}

/** Opens the Explain panel from a grid cell's `E`, returning focus to that cell (DS-CMP-15). */
export function explainFromCell(
  actions: ExplainActions,
  figure: FigureRef,
  label: string,
  context: string,
): void {
  const active = document.activeElement;
  actions.open({ figure, label, context }, active instanceof HTMLElement ? active : null);
}

interface ScheduleColumnSources {
  readonly contract: Contract;
  readonly obligations: readonly Obligation[];
  readonly book: string | null;
  readonly explainContext: string;
  readonly ctxSearch: string;
  readonly explain: ExplainActions;
}

function scheduleColumns({
  contract,
  obligations,
  book,
  explainContext,
  ctxSearch,
  explain,
}: ScheduleColumnSources): readonly GridColumn<ScheduleLine>[] {
  const currency = contract.transaction_currency;
  const byKey = new Map(obligations.map((item) => [item.obligation_key, item]));
  const figure = (line: ScheduleLine): FigureRef =>
    figureFromLink(line.links.explain, book) ?? {
      objectType: "schedule_line",
      id: line.id,
      measure: "amount",
      book: book ?? undefined,
    };
  const label = (line: ScheduleLine) =>
    line.obligation_key === null
      ? t("contracts.obligation.schedule.explainLabel", { period: line.period.name })
      : t("contracts.schedules.explainLabel", {
          period: line.period.name,
          obligation: line.obligation_key,
        });
  return [
    {
      id: "period",
      header: t("contracts.schedules.column.period"),
      kind: "period",
      value: (line) => line.period.name,
      render: (line) => <span className="num">{line.period.name}</span>,
      sortKey: "period_end_date",
      width: 112,
    },
    {
      id: "obligation",
      header: t("contracts.schedules.column.obligation"),
      kind: "text",
      value: (line) => line.obligation_key,
      render: (line) => (
        <ObligationKeyCell
          obligationKey={line.obligation_key}
          href={
            line.obligation_key === null
              ? null
              : obligationHref(contract, byKey.get(line.obligation_key), ctxSearch)
          }
        />
      ),
      width: 120,
    },
    {
      id: "line_type",
      header: t("contracts.schedules.column.lineType"),
      kind: "text",
      value: (line) => t(`contracts.schedule.lineType.${line.line_type}`),
      width: 200,
    },
    {
      id: "state",
      header: t("contracts.schedules.column.state"),
      kind: "text",
      value: (line) => t(`contracts.schedule.state.${line.state}`),
      width: 128,
    },
    {
      id: "quantity",
      header: t("contracts.schedules.column.quantity"),
      kind: "number",
      value: (line) => line.quantity,
      numberKind: "quantity",
      width: 112,
    },
    {
      id: "amount",
      header: t("contracts.schedules.column.amount", { currency }),
      kind: "money",
      value: (line) => line.amount.amount,
      currency: (line) => line.amount.currency,
      render: (line) => (
        <ExplainTrigger
          tabIndex={-1}
          figureRef={figure(line)}
          label={label(line)}
          context={explainContext}
          valueText={moneyText(line.amount.amount, line.amount.currency)}
        >
          <Money value={line.amount.amount} currency={line.amount.currency} variant="cell" />
        </ExplainTrigger>
      ),
      explain: (line) => explainFromCell(explain, figure(line), label(line), explainContext),
      width: 176,
    },
    {
      id: "cumulative",
      header: t("contracts.schedules.column.cumulative", { currency }),
      kind: "money",
      value: (line) => line.cumulative_amount.amount,
      currency: (line) => line.cumulative_amount.currency,
      width: 192,
    },
    {
      id: "entity",
      header: t("contracts.schedules.column.entity"),
      kind: "text",
      value: (line) => line.entity.code,
      render: (line) => <span className="font-mono text-mono-sm">{line.entity.code}</span>,
      width: 112,
    },
  ];
}

export function SchedulesTab({
  contract,
  context,
  obligations,
  obligationsLoading,
  explainContext,
  me,
  ctxSearch,
}: WorkbenchTabProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const explain = useExplain();
  const search = location.search;
  const book = readBook(contract, context);
  const periods = useContractPeriods(contract, context, me);

  const fields = useMemo((): readonly FilterField[] => {
    const options = periodOptions(periods.data);
    return [
      {
        name: "from_period",
        label: t("contracts.schedules.filter.fromPeriod"),
        kind: "period",
        operators: ["is"],
        periods: options,
      },
      {
        name: "to_period",
        label: t("contracts.schedules.filter.toPeriod"),
        kind: "period",
        operators: ["is"],
        periods: options,
      },
      {
        name: "obligation",
        label: t("contracts.schedules.filter.obligation"),
        kind: "enum",
        operators: ["is"],
        options: obligationsLoading
          ? chipValues(search, "obligation").map((value) => ({ value, label: value }))
          : obligations.map((item) => ({ value: item.obligation_key, label: item.obligation_key })),
        optionsLoading: obligationsLoading,
      },
      {
        name: "line_type",
        label: t("contracts.schedules.filter.lineType"),
        kind: "enum",
        operators: ["is"],
        options: SCHEDULE_LINE_TYPES.map((value) => ({
          value,
          label: t(`contracts.schedule.lineType.${value}`),
        })),
      },
    ];
  }, [periods.data, obligations, obligationsLoading, search]);

  const parsed = parseFilters(search, fields);
  const chip = (name: string) =>
    parsed.filters.find((filter) => filter.field === name)?.values[0] ?? null;
  const query: ScheduleLineQuery = {
    contractId: contract.id,
    book,
    knownAt: context.knownAt,
    fromPeriod: chip("from_period"),
    toPeriod: chip("to_period"),
    obligation: chip("obligation"),
    lineType: chip("line_type"),
  };
  const source: GridSource<ScheduleLine> = {
    queryKey: scheduleLinesKey(query),
    fetchPage: (cursor, sort) => fetchScheduleLinesPage(query, cursor, sort),
  };

  const columns = useMemo(
    () => scheduleColumns({ contract, obligations, book, explainContext, ctxSearch, explain }),
    [contract, obligations, book, explainContext, ctxSearch, explain],
  );
  const defaultColumns = useMemo(() => initialColumnState(columns, SCHEDULE_HIDDEN), [columns]);
  const [columnState, setColumnState] = useState<GridColumnState>(defaultColumns);
  const [total, setTotal] = useState<number | undefined>(undefined);

  const byKey = new Map(obligations.map((item) => [item.obligation_key, item]));
  const obligationsPath = `/contracts/${contract.id}/obligations${ctxSearch}`;
  // SCREENS §4.3 "Show all periods": the period chips are removed, else every chip.
  const showAllPeriods = () => {
    const rest = parsed.filters.filter(
      (filter) => filter.field !== "from_period" && filter.field !== "to_period",
    );
    const next = rest.length === parsed.filters.length ? [] : rest;
    void navigate({ search: withFilters(search, parsed.query, next) }, { replace: true });
  };
  const count = (value: number, formatted: string) =>
    t("contracts.schedules.count", { count: value, formatted });

  return (
    <div className="flex min-h-120 flex-col">
      <DataGrid<ScheduleLine>
        name="revenue-schedule"
        title={t("contracts.schedules.title")}
        errorTitle={t("contracts.schedules.loadError")}
        countLabel={count}
        columns={columns}
        source={source}
        rowKey={(line) => line.id}
        rowLabel={(line) => `${line.period.name} ${line.obligation_key ?? ""}`.trim()}
        rowHref={(line) =>
          (line.obligation_key === null
            ? null
            : obligationHref(contract, byKey.get(line.obligation_key), ctxSearch)) ??
          obligationsPath
        }
        testIdPrefix="SF-03"
        columnState={columnState}
        defaultColumnState={defaultColumns}
        onColumnStateChange={setColumnState}
        onTotalChange={(next) => setTotal(next?.count)}
        viewSelector={
          <SavedViewSelector
            screenCode={REVENUE_SCHEDULE_SCREEN_CODE}
            membershipId={me.active_membership_id}
            defaultLabel={t("contracts.schedules.view.default")}
            columnState={columnState}
            defaultColumnState={defaultColumns}
            onApplyColumns={setColumnState}
          />
        }
        filterBar={
          <FilterBar
            fields={fields}
            resultCount={total}
            resultLabel={(value) =>
              t("contracts.schedules.count", {
                count: value,
                formatted: formatNumber(value, { kind: "count" }),
              })
            }
            testId="SF-03-filter-bar-revenue-schedule"
          />
        }
        emptyState={
          <EmptyState
            title={t("contracts.schedules.empty")}
            description={t("contracts.schedules.emptyDescription")}
            headingLevel={3}
          />
        }
        noResults={
          <EmptyState
            title={t("contracts.schedules.empty")}
            description={t("contracts.schedules.noResultsDescription")}
            headingLevel={3}
            action={{ label: t("contracts.schedules.showAllPeriods"), onAction: showAllPeriods }}
          />
        }
      />
    </div>
  );
}
