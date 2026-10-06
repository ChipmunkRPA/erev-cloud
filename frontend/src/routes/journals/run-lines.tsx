// SF-06:run-lines Journal run: lines and source drill (SCREENS_B §3.3; SCREENS RT-104; DESIGN_SYSTEM
// DS-CMP-09, DS-CMP-10, DS-CMP-13, DS-CMP-15, DS-FMT-14, DS-FMT-16, DS-FMT-17, DS-FMT-19, DS-SP-04, DS-SP-07;
// 04 API-R-38 `GET /journal-runs/{id}/lines`, `GET /journal-lines/{id}/drill`, API-S-JournalLine,
// API-S-SubledgerLine; REQ-JE-003, REQ-JE-010, REQ-JE-018, REQ-RPT-017; BUILD_SPEC CLO-26; D-87 L6-5-Q-4,
// L6-5-Q-9). The journal lines grid with the Account, Account role, Contract and Batch filters (Contract a
// combobox of contracts and Batch the batches of the run, both sending ids; rev 1.39, item W-19), its first
// column pinned while the grid scrolls in its own viewport, every transaction amount an Explain trigger
// (`journal_line~<id>~amount`), and the source-lines drawer (`drawer=source-lines&row=<line id>`), docked
// beside the page so the content reflows (DS-SP-04 at 1440 px and wider). The drawer lists the
// contributing subledger lines, filters them client-side by contract external id, and offers "Explain",
// "Open schedule line" (SF-04 `layout=lines`) and "Open source row" (the SF-10 import row drawer); "Open
// event" stays absent with CTR-24 post-rc. [J] BUILD_SPEC CLO-26 names the account filter `f.account` and
// SCREENS_B §3.3 `f.account_code`; the screen rewrites the alias before its filter bar reads the URL, so the
// alias raises no "not recognised" banner (L6-5-Q-4).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import {
  type GridColumn,
  type GridColumnState,
  type GridSource,
  initialColumnState,
} from "../../components/data-grid/types";
import {
  type Explanation,
  ExplainPanel,
  ExplainProvider,
} from "../../components/explain/ExplainPanel";
import {
  type ExplainActions,
  ExplainTrigger,
  type FigureRef,
  useExplain,
} from "../../components/explain/ExplainTrigger";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import { type FilterField, parseFilters, withFilters } from "../../components/filter-bar/filters";
import { NoValue, Num } from "../../components/money/Num";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import {
  fetchJournalLinesPage,
  fetchLineDrill,
  type JournalBatch,
  type JournalLine,
  type JournalLineQuery,
  journalLinesKey,
  lineDrillKey,
} from "../../lib/api/queries/journal-runs";
import {
  contractOptionsKey,
  fetchContractOptions,
  fetchExplanation,
} from "../../lib/api/queries/contracts";
import { ACCOUNT_ROLES, type SubledgerLine } from "../../lib/api/queries/subledger-lines";
import { formatNumber, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { decodeValue, rawParams, withParams } from "../../lib/url/params";
import { TextField } from "../contracts/drawers/common";
import { urlChipValues } from "../contracts/list";
import { useBuiltPaths } from "../settings/index";
import { batchLabel, MoneyCell, Mono, moneyText, RunFrame, type RunContext } from "./run";

/** SCREENS RT-10 SF-03, the target of the Contract column. */
export const CONTRACT_ROUTE = "/contracts/:contractId/obligations";
/** SCREENS_B RT-25 SF-04, the target of "Open schedule line" (D-87 L6-5-Q-9). */
export const SCHEDULES_ROUTE = "/schedules";
/** SCREENS RT-44 SF-10:detail, whose import row drawer is the target of "Open source row". */
export const IMPORT_DETAIL_ROUTE = "/data/imports/:importId/:step";
/** SCREENS_B §3.3 columns hidden by the default view (the 1440 px wireframe). */
export const LINES_HIDDEN: readonly string[] = [
  "je_type",
  "dimensions",
  "debit_functional",
  "credit_functional",
  "obligation_key",
  "counterparty_entity",
  "origin_period",
  "is_post_close",
  "memo",
];
/** L6-5-Q-4: the BUILD_SPEC spelling of the account filter. */
export const ACCOUNT_ALIAS = "f.account";
const SOURCE_LINES = "source-lines";

const ZERO = /^-?0+(\.0+)?$/;
const IMPORT_ROWS_PATH = /^\/api\/v1\/imports\/([0-9a-f-]{36})\/rows$/;

interface LineFieldSources {
  readonly search: string;
  /** The contract options, undefined while they load. */
  readonly contracts: readonly { readonly value: string; readonly label: string }[] | undefined;
  readonly batches: readonly JournalBatch[];
}

/**
 * SCREENS_B §3.3 FilterBar fields (rev 1.39). The route's `contract` and `batch_id` filters are uuids, so
 * both fields offer records and send their ids: the contracts by external id, the batches of the run.
 */
export function lineFields({
  search,
  contracts,
  batches,
}: LineFieldSources): readonly FilterField[] {
  // A contract of the link that the first page of options does not hold keeps its chip.
  const known = new Set((contracts ?? []).map((option) => option.value));
  const linked = urlChipValues(search, "contract")
    .filter((value) => !known.has(value))
    .map((value) => ({ value, label: value }));
  return [
    {
      name: "account_code",
      label: t("journals.lines.filter.account"),
      kind: "text",
      operators: ["is"],
    },
    {
      name: "account_role",
      label: t("journals.lines.filter.accountRole"),
      kind: "enum",
      operators: ["is"],
      options: ACCOUNT_ROLES.map((value) => ({ value, label: t(`accountRole.${value}`) })),
    },
    {
      name: "contract",
      label: t("journals.lines.filter.contract"),
      kind: "user",
      operators: ["is"],
      options: [...(contracts ?? []), ...linked],
    },
    {
      name: "batch",
      label: t("journals.lines.filter.batch"),
      kind: "enum",
      operators: ["is"],
      options: [...batches]
        .sort((left, right) => left.batch_no - right.batch_no || left.chunk_no - right.chunk_no)
        .map((batch) => ({ value: batch.id, label: batchLabel(batch) })),
    },
  ];
}

/**
 * The side and amount the source-lines drawer titles a journal line by: its transaction amount, or,
 * for a line that carries functional amounts only (every FX remeasurement line; ENGINE_SPEC_B
 * S14-R-18 nets the two currencies independently), its functional amount. A line with a transaction
 * amount on one side and a functional amount on the other is titled by its transaction side.
 */
export function titledAmount(line: JournalLine): {
  readonly credit: boolean;
  readonly amount: JournalLine["debit_txn"];
} {
  if (!ZERO.test(line.debit_txn.amount)) return { credit: false, amount: line.debit_txn };
  if (!ZERO.test(line.credit_txn.amount)) return { credit: true, amount: line.credit_txn };
  if (!ZERO.test(line.debit_functional.amount)) {
    return { credit: false, amount: line.debit_functional };
  }
  return { credit: true, amount: line.credit_functional };
}

/** "department: SALES · location: NYC" (§3.3 Dimensions). */
export function dimensionsText(dimensions: Readonly<Record<string, unknown>>): string | null {
  const parts = Object.entries(dimensions)
    .filter(([, value]) => typeof value === "string" && value !== "")
    .map(([name, value]) => `${name}: ${String(value)}`);
  return parts.length === 0 ? null : parts.join(" · ");
}

/**
 * The SF-04 `layout=lines` link of a subledger line's schedule line: its entity, book and period, the
 * period as the range and its obligation (D-87 L6-5-Q-9; SCREENS_B §4.1; SCR-URL-24).
 */
export function scheduleLineHref(line: SubledgerLine): string {
  const period = encodeURIComponent(line.period_key);
  const parts = [
    `entity=${encodeURIComponent(line.entity.code)}`,
    `period=${period}`,
    `book=${encodeURIComponent(line.book)}`,
    "layout=lines",
    `f.period=between:${period},${period}`,
    ...(line.obligation_id === null
      ? []
      : [`obligation=${encodeURIComponent(line.obligation_id)}`]),
  ];
  return `${SCHEDULES_ROUTE}?${parts.join("&")}`;
}

/**
 * The SF-10:detail import row drawer of a `links.source_row` naming an import row
 * (`/api/v1/imports/{id}/rows?row_number=<n>&sheet_name=<s>`), else null. The §6.6 source record drawer
 * is not built in the rc, so other source rows have no destination (L7-3-Q-19).
 */
export function sourceRowHref(link: string | null): string | null {
  if (link === null) {
    return null;
  }
  const url = new URL(link, "http://erev.invalid");
  const match = IMPORT_ROWS_PATH.exec(url.pathname);
  const row = url.searchParams.get("row_number");
  if (match === null || row === null) {
    return null;
  }
  const sheet = url.searchParams.get("sheet_name");
  const search = sheet === null ? `row=${row}` : `row=${row}&sheet=${encodeURIComponent(sheet)}`;
  return `/data/imports/${match[1] ?? ""}/committed?${search}`;
}

interface LineColumnSources {
  readonly contractBuilt: boolean;
  readonly openSource: (line: JournalLine, element: HTMLElement) => void;
}

function lineColumns({
  contractBuilt,
  openSource,
}: LineColumnSources): readonly GridColumn<JournalLine>[] {
  const txn = (id: "debit_txn" | "credit_txn", header: string): GridColumn<JournalLine> => ({
    id,
    header,
    kind: "money",
    value: (line) => line[id].amount,
    currency: (line) => line[id].currency,
    render: (line) => {
      const amount = line[id];
      if (ZERO.test(amount.amount)) {
        return <MoneyCell value={amount.amount} currency={amount.currency} />;
      }
      return (
        <ExplainTrigger
          tabIndex={-1}
          figureRef={{ objectType: "journal_line", id: line.id, measure: "amount" }}
          label={header}
          context={t("journals.lines.rowLabel", { entry: line.je_no, line: line.line_no })}
          valueText={moneyText(amount.amount, amount.currency, "inline")}
        >
          <MoneyCell value={amount.amount} currency={amount.currency} />
        </ExplainTrigger>
      );
    },
    width: 144,
  });
  const functional = (
    id: "debit_functional" | "credit_functional",
    header: string,
  ): GridColumn<JournalLine> => ({
    id,
    header,
    kind: "money",
    value: (line) => line[id].amount,
    currency: (line) => line[id].currency,
    render: (line) => <MoneyCell value={line[id].amount} currency={line[id].currency} />,
    width: 176,
  });
  // Widths hold each figure and header without clipping, and the default columns fit a 1440 px window
  // with the rail expanded (CLO-26; DS-AP-10).
  return [
    {
      id: "je_no",
      header: t("journals.lines.column.entry"),
      kind: "text",
      value: (line) => line.je_no,
      render: (line) => <Mono>{line.je_no}</Mono>,
      width: 160,
    },
    {
      id: "je_type",
      header: t("journals.lines.column.type"),
      kind: "text",
      value: (line) => t(`journals.lines.jeType.${line.je_type}`),
      width: 112,
    },
    {
      id: "line_no",
      header: t("journals.lines.column.line"),
      kind: "number",
      value: (line) => String(line.line_no),
      width: 72,
    },
    {
      id: "account",
      header: t("journals.lines.column.account"),
      kind: "text",
      value: (line) => line.account.code,
      render: (line) => (
        <span title={line.account.name}>
          <Mono>{line.account.code}</Mono>
        </span>
      ),
      width: 112,
    },
    {
      id: "account_role",
      header: t("journals.lines.column.accountRole"),
      kind: "text",
      value: (line) => t(`accountRole.${line.account_role}`),
      width: 152,
    },
    {
      id: "dimensions",
      header: t("journals.lines.column.dimensions"),
      kind: "text",
      value: (line) => dimensionsText(line.dimensions),
      width: 240,
    },
    {
      id: "currency",
      header: t("journals.lines.column.currency"),
      kind: "text",
      value: (line) => line.debit_txn.currency,
      render: (line) => <Mono>{line.debit_txn.currency}</Mono>,
      width: 108,
    },
    txn("debit_txn", t("journals.lines.column.debitTxn")),
    txn("credit_txn", t("journals.lines.column.creditTxn")),
    functional("debit_functional", t("journals.lines.column.debitFunctional")),
    functional("credit_functional", t("journals.lines.column.creditFunctional")),
    {
      id: "contract",
      header: t("journals.lines.column.contract"),
      kind: "text",
      value: (line) => line.contract?.external_id ?? null,
      render: (line) =>
        line.contract === null ? (
          <NoValue />
        ) : contractBuilt ? (
          <Link
            to={`/contracts/${line.contract.id}/obligations`}
            tabIndex={-1}
            className="font-mono text-mono-sm text-accent-fg hover:underline"
          >
            {line.contract.external_id}
          </Link>
        ) : (
          <Mono>{line.contract.external_id}</Mono>
        ),
      width: 144,
    },
    {
      id: "obligation_key",
      header: t("journals.lines.column.obligation"),
      kind: "text",
      value: (line) => line.obligation_key,
      render: (line) =>
        line.obligation_key === null ? <NoValue /> : <Mono>{line.obligation_key}</Mono>,
      width: 120,
    },
    {
      id: "counterparty_entity",
      header: t("journals.lines.column.counterparty"),
      kind: "text",
      value: (line) => line.counterparty_entity?.code ?? null,
      width: 184,
    },
    {
      id: "origin_period",
      header: t("journals.lines.column.originPeriod"),
      // The cell renders the key through `formatPeriod` (DS-FMT-19).
      kind: "period",
      value: (line) => line.origin_period_key,
      width: 136,
    },
    {
      id: "is_post_close",
      header: t("journals.lines.column.postClose"),
      kind: "boolean",
      value: (line) => String(line.is_post_close),
      width: 120,
    },
    {
      id: "memo",
      header: t("journals.lines.column.memo"),
      kind: "text",
      value: (line) => line.memo,
      width: 240,
    },
    {
      id: "source_line_count",
      header: t("journals.lines.column.sourceLines"),
      kind: "number",
      value: (line) => String(line.source_line_count),
      render: (line) => (
        <Button
          variant="link"
          tabIndex={-1}
          aria-label={t("journals.lines.openSource", {
            entry: line.je_no,
            line: line.line_no,
            count: line.source_line_count,
          })}
          onClick={(event) => openSource(line, event.currentTarget)}
        >
          <span className="num">{formatNumber(line.source_line_count, { kind: "count" })}</span>
        </Button>
      ),
      width: 128,
    },
  ];
}

export function JournalRunLinesPage() {
  const location = useLocation();
  const navigate = useNavigate();
  // Every line amount and the source drill open Explain (DS-CMP-15), so the page hosts the provider
  // and docks the panel beside the frame, as SF-03 does.
  const loadExplanation = useCallback(
    async (figure: FigureRef) => (await fetchExplanation(figure)) as Explanation,
    [],
  );
  const params = new URLSearchParams(location.search);
  const drawerLineId = params.get("drawer") === SOURCE_LINES ? params.get("row") : null;
  const [selected, setSelected] = useState<JournalLine | null>(null);
  const origin = useRef<HTMLElement | null>(null);
  const latestSearch = useRef(location.search);
  useEffect(() => {
    latestSearch.current = location.search;
  });
  const writeDrawer = useCallback(
    (lineId: string | null) => {
      const changes =
        lineId === null ? { drawer: null, row: null } : { drawer: SOURCE_LINES, row: lineId };
      void navigate({ search: withParams(latestSearch.current, changes) }, { replace: true });
    },
    [navigate],
  );
  const openSource = useCallback(
    (line: JournalLine, element: HTMLElement) => {
      setSelected(line);
      origin.current = element.closest<HTMLElement>('[role="gridcell"]') ?? element;
      writeDrawer(line.id);
    },
    [writeDrawer],
  );
  // SCREENS_B §3.3: Esc closes the drawer and returns focus to the originating cell (J-16.6).
  const closeSource = useCallback(() => {
    writeDrawer(null);
    const element = origin.current;
    origin.current = null;
    if (element?.isConnected === true) {
      element.focus();
    }
  }, [writeDrawer]);

  const line = selected !== null && selected.id === drawerLineId ? selected : null;
  return (
    <ExplainProvider load={loadExplanation}>
      <div className="flex min-h-full gap-4">
        <div className="min-w-0 flex-1">
          <RunFrame tab="lines">
            {(context) => <LinesTab {...context} onOpenSource={openSource} />}
          </RunFrame>
        </div>
        {drawerLineId === null ? null : (
          <SourceLinesDrawer
            key={drawerLineId}
            lineId={drawerLineId}
            line={line}
            onClose={closeSource}
          />
        )}
        <ExplainPanel />
      </div>
    </ExplainProvider>
  );
}

interface LinesTabProps extends RunContext {
  readonly onOpenSource: (line: JournalLine, element: HTMLElement) => void;
}

function LinesTab({ run, onOpenSource }: LinesTabProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const built = useBuiltPaths();
  const search = location.search;

  // L6-5-Q-4: `f.account=is:<code>` becomes `f.account_code=is:<code>`. Search updates keep raw values,
  // so the operator colon of `f.*` values stays unencoded (SCR-URL-20; `parseFilter`).
  const alias = rawParams(search).find((param) => param.name === ACCOUNT_ALIAS)?.value ?? null;
  useEffect(() => {
    if (alias === null) {
      return;
    }
    const kept = rawParams(search).some((param) => param.name === "f.account_code");
    void navigate(
      {
        search: withParams(search, {
          [ACCOUNT_ALIAS]: null,
          ...(kept ? {} : { "f.account_code": alias }),
        }),
      },
      { replace: true },
    );
  }, [alias, navigate, search]);

  const contracts = useQuery({ queryKey: contractOptionsKey(), queryFn: fetchContractOptions });
  const fields = useMemo(
    () => lineFields({ search, contracts: contracts.data, batches: run.batches }),
    [search, contracts.data, run.batches],
  );
  const parsed = parseFilters(search, fields);
  const chip = (name: string) =>
    parsed.filters.find((filter) => filter.field === name)?.values[0] ?? null;
  const query: JournalLineQuery = {
    accountCode:
      chip("account_code") ?? (alias === null ? null : decodeValue(alias).replace(/^is:/, "")),
    accountRole: chip("account_role"),
    contract: chip("contract"),
    batchId: chip("batch"),
  };
  const source: GridSource<JournalLine> = {
    queryKey: journalLinesKey(run.id, query),
    fetchPage: (cursor, sort) => fetchJournalLinesPage(run.id, query, cursor, sort),
  };

  const openSource = useRef(onOpenSource);
  useEffect(() => {
    openSource.current = onOpenSource;
  });

  const contractBuilt = built.has(CONTRACT_ROUTE);
  const columns = useMemo(
    () =>
      lineColumns({
        contractBuilt,
        openSource: (line, element) => openSource.current(line, element),
      }),
    [contractBuilt],
  );
  // DS-SP-07: the journal entry column stays pinned while the grid scrolls in its viewport.
  const defaultColumns = useMemo(
    (): GridColumnState => ({
      ...initialColumnState(columns, LINES_HIDDEN),
      pinned: { start: ["je_no"], end: [] },
    }),
    [columns],
  );
  const [columnState, setColumnState] = useState<GridColumnState>(defaultColumns);
  const [total, setTotal] = useState<number | undefined>(undefined);
  const clearFilters = () => {
    void navigate({ search: withFilters(search, "", []) }, { replace: true });
  };

  if (alias !== null) {
    // The alias is rewritten first, so the filter bar never reads it as an unknown field (L6-5-Q-4).
    return <Skeleton region={t("journals.lines.title")} shape="rows" count={8} />;
  }
  return (
    <div className="flex min-h-120 flex-col">
      <DataGrid<JournalLine>
        name="lines"
        title={t("journals.lines.title")}
        errorTitle={t("journals.lines.loadError")}
        countLabel={(count, formatted) => t("journals.lines.count", { count, formatted })}
        columns={columns}
        source={source}
        rowKey={(item) => item.id}
        rowLabel={(item) => t("journals.lines.rowLabel", { entry: item.je_no, line: item.line_no })}
        testIdPrefix="SF-06"
        columnState={columnState}
        defaultColumnState={defaultColumns}
        onColumnStateChange={setColumnState}
        onTotalChange={(next) => setTotal(next?.count)}
        filterBar={
          <FilterBar
            fields={fields}
            resultCount={total}
            resultLabel={(value) =>
              t("journals.lines.count", {
                count: value,
                formatted: formatNumber(value, { kind: "count" }),
              })
            }
            testId="SF-06-filter-bar-lines"
          />
        }
        emptyState={
          <EmptyState
            title={t("journals.lines.empty")}
            description={t("journals.lines.emptyDescription")}
            headingLevel={3}
          />
        }
        noResults={
          <EmptyState
            title={t("journals.lines.noResults")}
            description=""
            headingLevel={3}
            action={{ label: t("journals.clearFilters"), onAction: clearFilters }}
          />
        }
      />
    </div>
  );
}

interface DrillColumnSources {
  readonly explain: ExplainActions;
  readonly openScheduleLine: ((line: SubledgerLine) => void) | null;
  readonly openSourceRow: ((href: string) => void) | null;
  /** Some loaded line names an import row, so the Actions column holds a third button. */
  readonly sourceRows: boolean;
}

function drillColumns({
  explain,
  openScheduleLine,
  openSourceRow,
  sourceRows,
}: DrillColumnSources): readonly GridColumn<SubledgerLine>[] {
  // SCREENS_B §3.3: the order follows the question the drawer answers — which lines make up this
  // amount. Whose line, which side and how much stand in view in the 720 px drawer (608 of its 686 px);
  // the first four columns were Effective, Recorded, Posting kind and Entry kind, 688 px that read
  // alike on every row, with the contract the drawer filters by out of view.
  return [
    {
      id: "contract",
      header: t("journals.lines.drill.column.contract"),
      // The leading identifier: the grid pins it and makes its cell the row header (DS-CMP-10). A line
      // without a contract keeps the dash for the eye; as the row's name it reads "No contract", where
      // the kit's "No value" would name a row by nothing (§3.3 rev 1.81).
      kind: "identifier",
      value: (item) => item.contract_external_id,
      render: (item) =>
        item.contract_external_id === null ? (
          <span className="text-fg-3">
            <span aria-hidden="true">{NO_VALUE}</span>
            <span className="sr-only">{t("journals.lines.drill.noContract")}</span>
          </span>
        ) : (
          <Mono>{item.contract_external_id}</Mono>
        ),
      width: 176,
    },
    {
      id: "dr_cr",
      header: t("journals.lines.drill.column.side"),
      kind: "text",
      value: (item) =>
        item.dr_cr === "D" ? t("journals.lines.drill.debit") : t("journals.lines.drill.credit"),
      width: 144,
    },
    {
      id: "amount_txn",
      header: t("journals.lines.drill.column.amountTxn"),
      kind: "money",
      value: (item) => item.amount_txn.amount,
      currency: (item) => item.amount_txn.currency,
      render: (item) => (
        <MoneyCell value={item.amount_txn.amount} currency={item.amount_txn.currency} />
      ),
      width: 160,
    },
    {
      id: "effective_date",
      header: t("journals.lines.drill.column.effective"),
      kind: "date",
      value: (item) => item.effective_date,
      width: 128,
    },
    {
      id: "entry_kind",
      header: t("journals.lines.drill.column.entryKind"),
      kind: "text",
      value: (item) => t(`je.entryKind.${item.entry_kind}`),
      width: 192,
    },
    {
      id: "posting_kind",
      header: t("journals.lines.drill.column.postingKind"),
      kind: "text",
      value: (item) => t(`journals.postingKind.${item.posting_kind}`),
      width: 176,
    },
    {
      id: "account_role",
      header: t("journals.lines.drill.column.accountRole"),
      kind: "text",
      value: (item) => t(`accountRole.${item.account_role}`),
      width: 176,
    },
    {
      id: "amount_functional",
      header: t("journals.lines.drill.column.amountFunctional"),
      kind: "money",
      value: (item) => item.amount_functional.amount,
      currency: (item) => item.amount_functional.currency,
      render: (item) => (
        <MoneyCell
          value={item.amount_functional.amount}
          currency={item.amount_functional.currency}
        />
      ),
      width: 192,
    },
    {
      id: "fx_rate",
      header: t("journals.lines.drill.column.fxRate"),
      kind: "number",
      value: (item) => item.fx_rate?.rate ?? null,
      render: (item) =>
        item.fx_rate === null ? <NoValue /> : <Num value={item.fx_rate.rate} kind="fx" />,
      width: 120,
    },
    {
      id: "origin_period",
      header: t("journals.lines.drill.column.originPeriod"),
      kind: "period",
      value: (item) => item.origin_period_key,
      width: 136,
    },
    {
      id: "is_post_reopen",
      header: t("journals.lines.drill.column.postReopen"),
      kind: "boolean",
      value: (item) => String(item.is_post_reopen),
      width: 128,
    },
    {
      id: "reason_code",
      header: t("journals.lines.drill.column.reason"),
      kind: "text",
      value: (item) => item.reason_code,
      render: (item) => (item.reason_code === null ? <NoValue /> : <Mono>{item.reason_code}</Mono>),
      width: 144,
    },
    {
      id: "recorded_at",
      header: t("journals.lines.drill.column.recorded"),
      kind: "timestamp",
      value: (item) => item.recorded_at,
      width: 192,
    },
    {
      id: "actions",
      header: t("journals.lines.drill.column.actions"),
      kind: "text",
      value: () => null,
      render: (item) => {
        const sourceRow = openSourceRow === null ? null : sourceRowHref(item.links.source_row);
        return (
          <span className="inline-flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              tabIndex={-1}
              aria-label={t("journals.lines.drill.explainName", {
                amount: moneyText(item.amount_txn.amount, item.amount_txn.currency, "inline"),
              })}
              onClick={(event) =>
                explain.open(
                  {
                    figure: { objectType: "subledger_line", id: item.id, measure: "amount" },
                    label: t("journals.lines.drill.column.amountTxn"),
                  },
                  event.currentTarget,
                )
              }
            >
              {t("journals.lines.drill.explain")}
            </Button>
            {openScheduleLine === null || item.schedule_line_id === null ? null : (
              <Button
                variant="ghost"
                size="sm"
                tabIndex={-1}
                onClick={() => openScheduleLine(item)}
              >
                {t("journals.lines.drill.openScheduleLine")}
              </Button>
            )}
            {openSourceRow === null || sourceRow === null ? null : (
              <Button
                variant="ghost"
                size="sm"
                tabIndex={-1}
                onClick={() => openSourceRow(sourceRow)}
              >
                {t("journals.lines.drill.openSourceRow")}
              </Button>
            )}
          </span>
        );
      },
      width: sourceRows ? 384 : 256,
    },
  ];
}

/** §3.3 source-lines drawer (DS-CMP-09 docked, `--drawer-w-wide`). */
function SourceLinesDrawer({
  lineId,
  line,
  onClose,
}: {
  readonly lineId: string;
  readonly line: JournalLine | null;
  readonly onClose: () => void;
}) {
  const explain = useExplain();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const built = useBuiltPaths();
  const [contractText, setContractText] = useState("");
  const [contract, setContract] = useState<string | null>(null);
  const [sourceRows, setSourceRows] = useState(false);
  const schedulesBuilt = built.has(SCHEDULES_ROUTE);
  const importsBuilt = built.has(IMPORT_DETAIL_ROUTE);
  const columns = useMemo(
    () =>
      drillColumns({
        explain,
        openScheduleLine: schedulesBuilt ? (item) => void navigate(scheduleLineHref(item)) : null,
        openSourceRow: importsBuilt ? (href) => void navigate(href) : null,
        sourceRows,
      }),
    [explain, importsBuilt, navigate, schedulesBuilt, sourceRows],
  );
  const source: GridSource<SubledgerLine> = {
    queryKey: lineDrillKey(lineId, contract),
    // D-87 L6-5-Q-9: the Contract filter applies client-side by external id over every source line;
    // the lines are read once under the unfiltered key, so a filter change reads nothing again.
    fetchPage: async () => {
      const items = await queryClient.fetchQuery({
        queryKey: lineDrillKey(lineId, null),
        queryFn: () => fetchLineDrill(lineId),
      });
      setSourceRows(items.some((item) => sourceRowHref(item.links.source_row) !== null));
      const wanted = contract?.toLowerCase() ?? null;
      const filtered =
        wanted === null
          ? items
          : items.filter((item) => item.contract_external_id?.toLowerCase() === wanted);
      return {
        items: filtered,
        nextCursor: null,
        total: { count: filtered.length, capped: false },
      };
    },
  };
  const apply = (event: FormEvent) => {
    event.preventDefault();
    const text = contractText.trim();
    setContract(text === "" ? null : text);
  };
  const titled = line === null ? null : titledAmount(line);
  return (
    <Drawer
      open
      variant="docked"
      wide
      title={
        line === null
          ? t("journals.lines.drawer.titleGeneric")
          : t("journals.lines.drawer.title", {
              entry: line.je_no,
              line: line.line_no,
            })
      }
      subtitle={
        line === null || titled === null
          ? undefined
          : t("journals.lines.drawer.subtitle", {
              account: line.account.code,
              side: titled.credit
                ? t("journals.lines.drill.credit")
                : t("journals.lines.drill.debit"),
              amount: moneyText(titled.amount.amount, titled.amount.currency, "inline"),
            })
      }
      initialFocus="title"
      onClose={onClose}
    >
      <div data-testid="SF-06-drawer-source-lines" className="flex min-h-100 flex-col gap-3">
        <form noValidate onSubmit={apply}>
          <TextField
            name="journal-line-drill-contract"
            label={t("journals.lines.drawer.contract")}
            optional
            help={t("journals.lines.drawer.contractHelp")}
            value={contractText}
            onChange={setContractText}
          />
        </form>
        <div className="flex min-h-80 flex-col">
          <DataGrid<SubledgerLine>
            name="source-lines"
            title={t("journals.lines.drill.title")}
            errorTitle={t("journals.lines.drill.loadError")}
            countLabel={(count, formatted) => t("journals.lines.drill.count", { count, formatted })}
            columns={columns}
            source={source}
            rowKey={(item) => item.id}
            rowLabel={(item) => `${item.effective_date} ${String(item.entry_no)}`}
            testIdPrefix="SF-06"
            emptyState={
              <EmptyState title={t("journals.lines.drill.empty")} description="" headingLevel={3} />
            }
          />
        </div>
      </div>
    </Drawer>
  );
}
