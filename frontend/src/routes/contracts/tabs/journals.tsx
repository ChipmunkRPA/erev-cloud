// SF-03:journals Journals tab (SCREENS §4.5; §0.4 RT-16; SCR-IA-07 `SF-03:journals`; DESIGN_SYSTEM
// DS-CMP-10, DS-CMP-13, DS-CMP-15, DS-FMT-04, DS-FMT-06, DS-FMT-19, DS-FMT-22; 04 API-R-36; BUILD_SPEC
// CTR-23). The DataGrid "Journal lines" of the contract's subledger lines with the Period, Origin period and
// Account role filters and saved views. Every Debit and Credit cell is an Explain trigger
// (`subledger_line~<id>~amount`). Period labels come from the calendars of the contracting and performing
// entities (DS-FMT-19); without `config.read` the key's label stands.
import { useQueries } from "@tanstack/react-query";
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
  type FilterField,
  parseFilters,
  withFilters,
} from "../../../components/filter-bar/filters";
import { Money } from "../../../components/money/Money";
import { NoValue } from "../../../components/money/Num";
import type { Contract } from "../../../lib/api/queries/contracts";
import type { Obligation } from "../../../lib/api/queries/obligations";
import {
  ACCOUNT_ROLES,
  fetchSubledgerLinesPage,
  JOURNAL_LINES_SCREEN_CODE,
  type JournalLineQuery,
  reversesLine,
  sideAmount,
  type SubledgerLine,
  subledgerLinesKey,
} from "../../../lib/api/queries/subledger-lines";
import {
  fetchPeriods,
  periodLabel,
  periodsKey,
  STRUCTURE_READ_PERMISSION,
} from "../../../lib/api/queries/tenant";
import { formatNumber, formatPeriod } from "../../../lib/format";
import { t } from "../../../lib/i18n/t";
import { useBuiltPaths } from "../../settings/index";
import { figureFromLink, moneyText } from "../obligation-pane";
import {
  explainFromCell,
  ObligationKeyCell,
  obligationHref,
  periodOptions,
  readBook,
  useContractPeriods,
  type WorkbenchTabProps,
} from "./schedules";

/** SCREENS RT-29 SF-06:run, the target of "View run". */
export const JOURNAL_RUN_ROUTE = "/journals/runs/:runId";
/** SCREENS §4.5 columns hidden by default. */
export const JOURNAL_HIDDEN: readonly string[] = ["post_reopen", "reverses", "recorded_at"];

/** One page in period order: period descending, then entry number, the debit before the credit. */
export function periodOrder(items: readonly SubledgerLine[]): readonly SubledgerLine[] {
  return [...items].sort((left, right) => {
    if (left.period_key !== right.period_key) {
      return left.period_key < right.period_key ? 1 : -1;
    }
    if (left.entry_no !== right.entry_no) {
      return left.entry_no - right.entry_no;
    }
    return left.dr_cr === right.dr_cr ? 0 : left.dr_cr === "D" ? -1 : 1;
  });
}

interface JournalColumnSources {
  readonly contract: Contract;
  readonly obligations: readonly Obligation[];
  readonly labels: ReadonlyMap<string, string>;
  readonly book: string | null;
  readonly explainContext: string;
  readonly ctxSearch: string;
  readonly explain: ExplainActions;
  readonly runRouteBuilt: boolean;
}

function journalColumns({
  contract,
  obligations,
  labels,
  book,
  explainContext,
  ctxSearch,
  explain,
  runRouteBuilt,
}: JournalColumnSources): readonly GridColumn<SubledgerLine>[] {
  const byId = new Map(obligations.map((item) => [item.id, item]));
  const periodText = (line: SubledgerLine, key: string | null): string | null =>
    key === null ? null : (labels.get(`${line.entity.code}|${key}`) ?? formatPeriod(key));
  const figure = (line: SubledgerLine): FigureRef =>
    figureFromLink(line.links.explain, book) ?? {
      objectType: "subledger_line",
      id: line.id,
      measure: "amount",
      book: book ?? undefined,
    };
  const side = (id: "debit" | "credit", code: "D" | "C"): GridColumn<SubledgerLine> => {
    const label = (line: SubledgerLine) =>
      t("contracts.journals.explainLabel", {
        side: t(`contracts.journals.column.${id}`),
        period: periodText(line, line.period_key) ?? line.period_key,
      });
    return {
      id,
      header: t(`contracts.journals.column.${id}`),
      kind: "money",
      value: (line) => sideAmount(line, code),
      currency: (line) => line.amount_txn.currency,
      render: (line) => {
        const amount = sideAmount(line, code);
        return amount === null ? null : (
          <ExplainTrigger
            tabIndex={-1}
            figureRef={figure(line)}
            label={label(line)}
            context={explainContext}
            valueText={moneyText(amount, line.amount_txn.currency)}
          >
            <Money value={amount} currency={line.amount_txn.currency} variant="cell" />
          </ExplainTrigger>
        );
      },
      explain: (line) => {
        if (line.dr_cr === code) {
          explainFromCell(explain, figure(line), label(line), explainContext);
        }
      },
      width: 160,
    };
  };
  const keyOf = (line: SubledgerLine) =>
    line.obligation_id === null ? null : (byId.get(line.obligation_id)?.obligation_key ?? null);
  return [
    {
      id: "period",
      header: t("contracts.journals.column.period"),
      kind: "period",
      value: (line) => periodText(line, line.period_key),
      render: (line) => <span className="num">{periodText(line, line.period_key)}</span>,
      width: 112,
    },
    {
      id: "origin_period",
      header: t("contracts.journals.column.originPeriod"),
      kind: "period",
      value: (line) => periodText(line, line.origin_period_key),
      render: (line) =>
        line.origin_period_key === null ? (
          <NoValue />
        ) : (
          <span className="num">{periodText(line, line.origin_period_key)}</span>
        ),
      width: 136,
    },
    {
      id: "effective_date",
      header: t("contracts.journals.column.effectiveDate"),
      kind: "date",
      value: (line) => line.effective_date,
      width: 136,
    },
    {
      id: "entry",
      header: t("contracts.journals.column.entry"),
      kind: "text",
      value: (line) => t(`je.entryKind.${line.entry_kind}`),
      width: 208,
    },
    {
      id: "account_role",
      header: t("contracts.journals.column.accountRole"),
      kind: "text",
      // [J] L5-4-Q-53: API-S-SubledgerLine carries no clearing purpose, so BILLING_CLEARING shows the
      // role label alone.
      value: (line) => t(`accountRole.${line.account_role}`),
      width: 208,
    },
    {
      id: "account",
      header: t("contracts.journals.column.account"),
      kind: "text",
      value: (line) => `${line.account.code} · ${line.account.name}`,
      render: (line) => (
        <span className="truncate" title={`${line.account.code} · ${line.account.name}`}>
          <span className="font-mono text-mono-sm">{line.account.code}</span>
          {` · ${line.account.name}`}
        </span>
      ),
      width: 240,
    },
    {
      id: "currency",
      header: t("contracts.journals.column.currency"),
      kind: "text",
      value: (line) => line.amount_txn.currency,
      render: (line) => <span className="font-mono text-mono-sm">{line.amount_txn.currency}</span>,
      width: 104,
    },
    side("debit", "D"),
    side("credit", "C"),
    {
      id: "obligation",
      header: t("contracts.journals.column.obligation"),
      kind: "text",
      value: keyOf,
      render: (line) => {
        const key = keyOf(line);
        const obligation = line.obligation_id === null ? undefined : byId.get(line.obligation_id);
        return (
          <ObligationKeyCell
            obligationKey={key}
            href={obligationHref(contract, obligation, ctxSearch)}
          />
        );
      },
      width: 120,
    },
    {
      id: "post_reopen",
      header: t("contracts.journals.column.postReopen"),
      kind: "boolean",
      value: (line) => String(line.is_post_reopen),
      width: 128,
    },
    {
      id: "reverses",
      header: t("contracts.journals.column.reverses"),
      kind: "boolean",
      value: (line) => String(reversesLine(line)),
      width: 112,
    },
    {
      id: "journal_run",
      header: t("contracts.journals.column.journalRun"),
      kind: "text",
      value: (line) => line.journal_run_id,
      render: (line) =>
        line.journal_run_id === null || !runRouteBuilt ? (
          <NoValue />
        ) : (
          <Link
            to={`/journals/runs/${line.journal_run_id}`}
            tabIndex={-1}
            className="text-body-sm underline decoration-control decoration-dotted underline-offset-3"
          >
            {t("contracts.journals.viewRun")}
          </Link>
        ),
      width: 128,
    },
    {
      id: "recorded_at",
      header: t("contracts.journals.column.recordedAt"),
      kind: "timestamp",
      value: (line) => line.recorded_at,
      width: 192,
    },
  ];
}

/** The entities whose calendars label the lines: the contracting and the performing entities. */
function entityCodes(contract: Contract, obligations: readonly Obligation[]): readonly string[] {
  return [
    ...new Set([
      contract.contracting_entity.code,
      ...obligations.map((item) => item.performing_entity.code),
    ]),
  ];
}

export function JournalsTab({
  contract,
  context,
  obligations,
  explainContext,
  me,
  ctxSearch,
}: WorkbenchTabProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const explain = useExplain();
  const built = useBuiltPaths();
  const search = location.search;
  const book = readBook(contract, context);
  const structure = me.permissions.includes(STRUCTURE_READ_PERMISSION);
  const periods = useContractPeriods(contract, context, me);
  const codes = entityCodes(contract, obligations);
  const reads = useQueries({
    queries: codes.map((code) => {
      const query = { entity: code, book: book ?? "" };
      return {
        queryKey: periodsKey(query),
        queryFn: () => fetchPeriods(query),
        enabled: structure && book !== null,
      };
    }),
  });
  // A stable text of the labels, so the columns are rebuilt only when a label changes.
  const labelsText = reads
    .flatMap((read, index) =>
      (read.data ?? []).map(
        (item) => `${codes[index] ?? ""}|${item.period.period_key}\t${periodLabel(item.period)}`,
      ),
    )
    .join("\n");
  const labels = useMemo(
    () =>
      new Map(
        labelsText === ""
          ? []
          : labelsText.split("\n").map((row) => {
              const [key = "", label = ""] = row.split("\t");
              return [key, label] as const;
            }),
      ),
    [labelsText],
  );

  const fields = useMemo((): readonly FilterField[] => {
    const options = periodOptions(periods.data);
    return [
      {
        name: "period",
        label: t("contracts.journals.filter.period"),
        kind: "period",
        operators: ["is"],
        periods: options,
      },
      {
        name: "origin_period",
        label: t("contracts.journals.filter.originPeriod"),
        kind: "period",
        operators: ["is"],
        periods: options,
      },
      {
        name: "account_role",
        label: t("contracts.journals.filter.accountRole"),
        kind: "enum",
        operators: ["is"],
        options: ACCOUNT_ROLES.map((value) => ({ value, label: t(`accountRole.${value}`) })),
      },
    ];
  }, [periods.data]);
  const parsed = parseFilters(search, fields);
  const chip = (name: string) =>
    parsed.filters.find((filter) => filter.field === name)?.values[0] ?? null;
  const query: JournalLineQuery = {
    contractId: contract.id,
    book,
    knownAt: context.knownAt,
    period: chip("period"),
    originPeriod: chip("origin_period"),
    accountRole: chip("account_role"),
  };
  const source: GridSource<SubledgerLine> = {
    queryKey: subledgerLinesKey(query),
    fetchPage: async (cursor, sort) => {
      const page = await fetchSubledgerLinesPage(query, cursor, sort);
      // [J] L5-4-Q-50: API-R-36 has no period sort key, so without a URL sort each page is shown in
      // SCREENS §4.5 "Period, default descending" order.
      return sort === null ? { ...page, items: periodOrder(page.items) } : page;
    },
  };

  const runRouteBuilt = built.has(JOURNAL_RUN_ROUTE);
  const columns = useMemo(
    () =>
      journalColumns({
        contract,
        obligations,
        labels,
        book,
        explainContext,
        ctxSearch,
        explain,
        runRouteBuilt,
      }),
    [contract, obligations, labels, book, explainContext, ctxSearch, explain, runRouteBuilt],
  );
  const defaultColumns = useMemo((): GridColumnState => {
    const state = initialColumnState(columns, JOURNAL_HIDDEN);
    // [J] The period stays in view while the grid scrolls to Debit and Credit (DS-CMP-10 pinning).
    return { ...state, pinned: { start: ["period"], end: [] } };
  }, [columns]);
  const [columnState, setColumnState] = useState<GridColumnState>(defaultColumns);
  const [total, setTotal] = useState<number | undefined>(undefined);
  const clearFilters = () => {
    void navigate({ search: withFilters(search, "", []) }, { replace: true });
  };

  return (
    <div className="flex min-h-120 flex-col">
      <DataGrid<SubledgerLine>
        name="journal-lines"
        title={t("contracts.journals.title")}
        errorTitle={t("contracts.journals.loadError")}
        countLabel={(count, formatted) => t("contracts.journals.count", { count, formatted })}
        columns={columns}
        source={source}
        rowKey={(line) => line.id}
        rowLabel={(line) => `${line.period_key} ${String(line.entry_no)}`}
        testIdPrefix="SF-03"
        columnState={columnState}
        defaultColumnState={defaultColumns}
        onColumnStateChange={setColumnState}
        onTotalChange={(next) => setTotal(next?.count)}
        viewSelector={
          <SavedViewSelector
            screenCode={JOURNAL_LINES_SCREEN_CODE}
            membershipId={me.active_membership_id}
            defaultLabel={t("contracts.journals.view.default")}
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
              t("contracts.journals.count", {
                count: value,
                formatted: formatNumber(value, { kind: "count" }),
              })
            }
            testId="SF-03-filter-bar-journal-lines"
          />
        }
        emptyState={
          <EmptyState
            title={t("contracts.journals.empty")}
            description={t("contracts.journals.emptyDescription")}
            headingLevel={3}
          />
        }
        noResults={
          <EmptyState
            title={t("contracts.journals.noResults")}
            description=""
            headingLevel={3}
            action={{ label: t("contracts.list.clearFilters"), onAction: clearFilters }}
          />
        }
      />
    </div>
  );
}
