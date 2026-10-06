// SF-06 Journal runs (SCREENS_B §3 area header, §3.1; §0.3 SB-R-06; §0.4 E-34 SMAP-05 to SMAP-08; SCREENS
// RT-28, SCR-IA-01, SCR-IA-02; DESIGN_SYSTEM DS-CMP-06, DS-CMP-07, DS-CMP-10, DS-CMP-11, DS-CMP-13,
// DS-CMP-19, DS-CMP-24, DS-CMP-29; 04 API-R-38 `GET, POST /journal-runs`, API-S-JournalRunCreate; BUILD_SPEC
// CLO-26). The Journals area header ("Journals", "Run journals", the built route tabs), the runs grid of the
// context entity, book and period with the State and Mode filters, and the "Run journals" form: one
// `POST /journal-runs` per entity (202), followed in place by DS-CMP-24 progress, the success toast and
// the calculation failure banner. [J] API-S-Job names no subject, so only calculations started from this
// page are shown in progress (L6-5-Q-5). The toast's "Open run" opens SF-06:run in the calculation's own
// entity, period and book, not the page search (D-89 L7-3-Q-32).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useId, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router";

import { contextSearch } from "../../app/shell/IconRail";
import { DataGrid } from "../../components/data-grid/DataGrid";
import { SavedViewSelector } from "../../components/data-grid/SavedViewSelector";
import {
  type GridColumn,
  type GridColumnState,
  type GridSource,
  initialColumnState,
} from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { JobProgress } from "../../components/feedback/JobProgress";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useNoAnswer, useToast } from "../../components/feedback/Toast";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import { type FilterField, parseFilters, withFilters } from "../../components/filter-bar/filters";
import { Field } from "../../components/form/Field";
import { MultiSelect } from "../../components/form/MultiSelect";
import { Plus } from "../../components/icons/registry";
import { type RouteTab, RouteTabs } from "../../components/record/Tabs";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { OutlineChip, StatusChip, statusMessageKey } from "../../components/ui/StatusChip";
import { type Access, useAccess } from "../../lib/access";
import { acceptedJobId, useCommandKeys } from "../../lib/api/commands";
import { isTerminal, useJob } from "../../lib/api/jobs";
import { type ApiProblem, readProblem } from "../../lib/api/problems";
import {
  acknowledgedBatches,
  EVERY_JOURNAL_RUN,
  fetchJournalRunsPage,
  JOURNAL_RUN_PERMISSION,
  JOURNAL_RUNS_PATH,
  type JournalRunGrain,
  type JournalRunMode,
  type JournalRunQuery,
  type JournalRunRow,
  journalRunsKey,
  RUNS_SCREEN_CODE,
  runRoute,
} from "../../lib/api/queries/journal-runs";
import { useMe } from "../../lib/api/queries/me";
import {
  type Entity,
  entitiesKey,
  fetchActiveEntities,
  fetchPeriods,
  periodsKey,
  STRUCTURE_READ_PERMISSION,
} from "../../lib/api/queries/tenant";
import { formatNumber, formatPeriod, instantMs, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { withParams } from "../../lib/url/params";
import { type Choice, SelectField, TextField } from "../contracts/drawers/common";
import { useBuiltPaths } from "../settings/index";
import { bookText, CONTEXT, grainText, MoneyCell, Mono, modeText, RunStateChip } from "./run";

/** SCREENS RT-30 SF-06:entries, the second area tab once built (SCR-IA-02; XR-14). */
export const ENTRIES_ROUTE = "/journals/entries";
/**
 * SCREENS_B §3.1: columns hidden by the default view. The 1280 px wireframe hides Grain, Approved,
 * Exported and Created by, and neither wireframe shows Balanced; with the rail expanded a 1440 px window
 * holds the 1280 px column set, so Book (on the context pill) is hidden too and every figure fits
 * without clipping (CLO-26; DS-AP-10). Both stay available in Columns.
 */
export const RUNS_HIDDEN: readonly string[] = [
  "book",
  "grain",
  "balanced",
  "approved_at",
  "exported_at",
  "created_by",
];
/** "2026-09-05 10:00", "2026-09-05 10:00 UTC" or an RFC 3339 instant with an offset. */
const CUTOFF_INPUT =
  /^(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?(?:\s*UTC|Z|([+-]\d{2}:\d{2}))?$/;

export interface CutoffInput {
  /** The RFC 3339 `cutoff_known_at`, or null when the field is empty or invalid. */
  readonly value: string | null;
  readonly error: string | null;
}

/** SCREENS_B §3.1 "Cut-off known at (optional)": an instant that is not in the future (UTC unless named). */
export function parseCutoff(text: string, nowMs: number): CutoffInput {
  const trimmed = text.trim();
  if (trimmed === "") {
    return { value: null, error: null };
  }
  const match = CUTOFF_INPUT.exec(trimmed);
  if (match === null) {
    return { value: null, error: t("journals.runForm.cutoffFormat") };
  }
  const [, date = "", hours = "", minutes = "", seconds, offset] = match;
  const value = `${date}T${hours}:${minutes}:${seconds ?? "00"}${offset ?? "Z"}`;
  let instant: number;
  try {
    instant = instantMs(value);
  } catch {
    return { value: null, error: t("journals.runForm.cutoffFormat") };
  }
  return instant > nowMs
    ? { value: null, error: t("journals.runForm.cutoffFuture") }
    : { value, error: null };
}
export const JOURNAL_STATES = [
  "draft",
  "approved",
  "exported",
  "acknowledged",
  "failed",
  "cancelled",
] as const;
const MODES: readonly JournalRunMode[] = ["GROSS", "DELTA"];
const GRAINS: readonly JournalRunGrain[] = [
  "ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS",
  "CONTRACT_ACCOUNT_DIMENSIONS",
  "LEGACY_CONTRACT_POB",
];
/** SCREENS_B §3.1 "Period": the periods a run may calculate. */
const RUNNABLE_PERIODS: Readonly<Record<string, "Period open" | "Soft close" | "Reopened">> = {
  open: "Period open",
  closing: "Soft close",
  reopened: "Reopened",
};

function runFields(): readonly FilterField[] {
  return [
    {
      name: "state",
      label: t("journals.runs.filter.state"),
      kind: "enum",
      operators: ["is"],
      options: JOURNAL_STATES.map((value) => ({ value, label: t(`journals.state.${value}`) })),
    },
    {
      name: "mode",
      label: t("journals.runs.filter.mode"),
      kind: "enum",
      operators: ["is"],
      options: MODES.map((value) => ({ value, label: modeText(value) })),
    },
  ];
}

interface RunColumnSources {
  readonly functional: string | null;
  readonly ctxSearch: string;
}

function runColumns({
  functional,
  ctxSearch,
}: RunColumnSources): readonly GridColumn<JournalRunRow>[] {
  const money = (
    id: "debit" | "credit",
    pick: (run: JournalRunRow) => { readonly amount: string; readonly currency: string },
  ): GridColumn<JournalRunRow> => ({
    id,
    header:
      functional === null
        ? t(`journals.runs.column.${id}`)
        : t(`journals.runs.column.${id}In`, { currency: functional }),
    kind: "money",
    value: (run) => pick(run).amount,
    currency: (run) => pick(run).currency,
    render: (run) => <MoneyCell value={pick(run).amount} currency={pick(run).currency} />,
    width: 144,
  });
  return [
    {
      id: "run_no",
      header: t("journals.runs.column.run"),
      kind: "identifier",
      value: (run) => run.run_no,
      href: (run) => `${runRoute(run.id)}${ctxSearch}`,
      width: 112,
    },
    {
      id: "entity",
      header: t("journals.runs.column.entity"),
      kind: "text",
      value: (run) => run.entity.code,
      render: (run) => <Mono>{run.entity.code}</Mono>,
      width: 88,
    },
    {
      id: "book",
      header: t("journals.runs.column.book"),
      kind: "text",
      value: (run) => bookText(run.book),
      width: 104,
    },
    {
      id: "period",
      header: t("journals.runs.column.period"),
      // SCREENS_B §3.1: `period.name`, the calendar's DS-FMT-19 label.
      kind: "text",
      value: (run) => run.period.name,
      width: 104,
    },
    {
      id: "mode",
      header: t("journals.runs.column.mode"),
      kind: "text",
      value: (run) => modeText(run.mode),
      render: (run) => <OutlineChip label={modeText(run.mode)} />,
      width: 88,
    },
    {
      id: "grain",
      header: t("journals.runs.column.grain"),
      kind: "text",
      value: (run) => grainText(run.grain),
      width: 240,
    },
    {
      id: "state",
      header: t("journals.runs.column.state"),
      kind: "status",
      value: (run) => run.state,
      render: (run) => <RunStateChip run={run} />,
      width: 232,
    },
    {
      id: "line_count",
      header: t("journals.runs.column.lines"),
      kind: "number",
      value: (run) => String(run.totals.line_count),
      width: 80,
    },
    {
      id: "currency",
      header: t("journals.runs.column.currency"),
      kind: "text",
      value: (run) => run.totals.debit_functional.currency,
      render: (run) => <Mono>{run.totals.debit_functional.currency}</Mono>,
      width: 104,
    },
    money("debit", (run) => run.totals.debit_functional),
    money("credit", (run) => run.totals.credit_functional),
    {
      id: "balanced",
      header: t("journals.runs.column.balanced"),
      kind: "text",
      value: (run) => (run.totals.balanced ? t("journals.yes") : t("journals.no")),
      render: (run) =>
        run.totals.balanced ? (
          t("journals.yes")
        ) : (
          <span className="inline-flex items-center gap-1.5">
            {t("journals.no")}
            <StatusChip status="Difference" />
          </span>
        ),
      width: 144,
    },
    {
      id: "acknowledged",
      header: t("journals.runs.column.acknowledged"),
      kind: "text",
      // A count pair, not prose: "<n>/<m>" (SCREENS_B §3.1 "Acknowledged").
      value: (run) =>
        `${formatNumber(acknowledgedBatches(run.batches), { kind: "count" })}/${formatNumber(
          run.batches.length,
          { kind: "count" },
        )}`,
      width: 144,
    },
    {
      id: "approved_at",
      header: t("journals.runs.column.approved"),
      kind: "timestamp",
      value: (run) => run.approved_at,
      width: 192,
    },
    {
      id: "exported_at",
      header: t("journals.runs.column.exported"),
      kind: "timestamp",
      value: (run) => run.exported_at,
      width: 192,
    },
    {
      id: "created_by",
      header: t("journals.runs.column.createdBy"),
      kind: "user",
      value: (run) => run.created_by.display_name,
      width: 176,
    },
  ];
}

export function JournalRuns() {
  const me = useMe();
  const access = useAccess();
  if (me.isError) {
    return <Banner tone="negative" title={me.error.message} />;
  }
  if (me.data === undefined) {
    return <Skeleton region={t("journals.runs.region")} shape="rows" count={8} />;
  }
  return <RunsView access={access} membershipId={me.data.active_membership_id} />;
}

interface Calculation {
  readonly jobId: string;
  readonly entity: string;
  /** The calculated period and book: with `entity`, the context "Open run" keeps (D-89 L7-3-Q-32). */
  readonly periodKey: string;
  readonly book: string;
  readonly periodLabel: string;
}

function RunsView({
  access,
  membershipId,
}: {
  readonly access: Access;
  readonly membershipId: string | null;
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const search = location.search;
  const ctxSearch = contextSearch(search, CONTEXT);
  const context = new URLSearchParams(search);
  const entity = context.get("entity");
  const period = context.get("period");
  const book = context.get("book");
  // "Run journals" opens a form that names its entities, so the entry asks any entity; the form
  // offers the entities the permission is held for (SCREENS §0.6 SCR-PERM-02).
  const canRun = access.holdsAnywhere(JOURNAL_RUN_PERMISSION);
  const structure = access.holdsAnywhere(STRUCTURE_READ_PERMISSION);
  const entities = useQuery({
    queryKey: entitiesKey(),
    queryFn: fetchActiveEntities,
    enabled: structure,
  });
  const functional =
    entity === null
      ? null
      : (entities.data?.find((item) => item.code === entity)?.functional_currency ?? null);

  const fields = useMemo(runFields, []);
  const parsed = parseFilters(search, fields);
  const chip = (name: string) =>
    parsed.filters.find((filter) => filter.field === name)?.values[0] ?? null;
  const query: JournalRunQuery = {
    entity,
    book,
    period,
    state: chip("state"),
    mode: chip("mode"),
  };
  const [formOpen, setFormOpen] = useState(false);
  const [calculations, setCalculations] = useState<readonly Calculation[]>([]);

  return (
    <div data-testid="SF-06-page" className="flex flex-col gap-4">
      <JournalsAreaHeader
        actions={
          canRun ? (
            <Button variant="primary" icon={Plus} onClick={() => setFormOpen(true)}>
              {t("journals.runs.action.run")}
            </Button>
          ) : null
        }
      />
      {calculations.map((calculation) => (
        <CalculationProgress key={calculation.jobId} calculation={calculation} />
      ))}
      <RunsGrid
        key={functional ?? "all"}
        query={query}
        functional={functional}
        fields={fields}
        ctxSearch={ctxSearch}
        search={search}
        periodLabel={period === null ? null : formatPeriod(period)}
        membershipId={membershipId}
        canRun={canRun}
        onRun={() => setFormOpen(true)}
        onClear={() => void navigate({ search: withFilters(search, "", []) }, { replace: true })}
      />
      {formOpen ? (
        <RunJournalsDialog
          entities={entities.data ?? []}
          access={access}
          context={{ entity, period, book }}
          onClose={() => setFormOpen(false)}
          onStarted={(started) => setCalculations((previous) => [...previous, ...started])}
        />
      ) : null}
    </div>
  );
}

/**
 * SCREENS_B §3 area header: `h1` "Journals" with the route tabs Journal runs (SF-06) and Entries by date
 * range (SF-06:entries), each rendered once its route is built (SCR-IA-02; XR-14).
 */
export function JournalsAreaHeader({ actions }: { readonly actions?: ReactNode }) {
  const location = useLocation();
  const built = useBuiltPaths();
  const ctxSearch = contextSearch(location.search, CONTEXT);
  const tabs: RouteTab[] = [
    { id: "runs", label: t("journals.runs.tab"), to: `/journals${ctxSearch}`, end: true },
  ];
  if (built.has(ENTRIES_ROUTE)) {
    tabs.push({
      id: "entries",
      label: t("journals.entries.tab"),
      to: `${ENTRIES_ROUTE}${ctxSearch}`,
    });
  }
  return (
    <header className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <h1 tabIndex={-1} className="text-title-lg text-fg-1">
          {t("journals.title")}
        </h1>
        {actions === null || actions === undefined ? null : (
          <span className="ms-auto">{actions}</span>
        )}
      </div>
      <RouteTabs label={t("journals.tabs.label")} tabs={tabs} />
    </header>
  );
}

interface RunsGridProps {
  readonly query: JournalRunQuery;
  readonly functional: string | null;
  readonly fields: readonly FilterField[];
  readonly ctxSearch: string;
  readonly search: string;
  readonly periodLabel: string | null;
  /** `/me` `active_membership_id`: only the owner changes a saved view. */
  readonly membershipId: string | null;
  readonly canRun: boolean;
  readonly onRun: () => void;
  readonly onClear: () => void;
}

function RunsGrid({
  query,
  functional,
  fields,
  ctxSearch,
  periodLabel,
  membershipId,
  canRun,
  onRun,
  onClear,
}: RunsGridProps) {
  const source: GridSource<JournalRunRow> = {
    queryKey: journalRunsKey(query),
    fetchPage: (cursor, sort) => fetchJournalRunsPage(query, cursor, sort),
  };
  const columns = useMemo(() => runColumns({ functional, ctxSearch }), [functional, ctxSearch]);
  const defaultColumns = useMemo(
    (): GridColumnState =>
      initialColumnState(columns, functional === null ? RUNS_HIDDEN : [...RUNS_HIDDEN, "currency"]),
    [columns, functional],
  );
  const [columnState, setColumnState] = useState<GridColumnState>(defaultColumns);
  const [total, setTotal] = useState<number | undefined>(undefined);
  return (
    <div className="flex min-h-120 flex-col">
      <DataGrid<JournalRunRow>
        name="runs"
        title={t("journals.runs.title")}
        errorTitle={t("journals.runs.loadError")}
        countLabel={(count, formatted) => t("journals.runs.count", { count, formatted })}
        columns={columns}
        source={source}
        rowKey={(run) => run.id}
        rowLabel={(run) => run.run_no}
        rowTestKey={(run) => `${run.entity.code}-${run.period.period_key}`}
        testIdPrefix="SF-06"
        columnState={columnState}
        defaultColumnState={defaultColumns}
        onColumnStateChange={setColumnState}
        onTotalChange={(next) => setTotal(next?.count)}
        viewSelector={
          // D-87 L6-5-Q-8: saved views of screen code `SF-06` (SCREENS_B §3.1 data bindings).
          <SavedViewSelector
            screenCode={RUNS_SCREEN_CODE}
            membershipId={membershipId}
            defaultLabel={t("journals.runs.view.default")}
            columnState={columnState}
            defaultColumnState={defaultColumns}
            onApplyColumns={setColumnState}
            testId="SF-06-saved-view"
          />
        }
        filterBar={
          <FilterBar
            fields={fields}
            resultCount={total}
            resultLabel={(value) =>
              t("journals.runs.count", {
                count: value,
                formatted: formatNumber(value, { kind: "count" }),
              })
            }
            testId="SF-06-filter-bar-runs"
          />
        }
        emptyState={
          <EmptyState
            title={
              periodLabel === null
                ? t("journals.runs.emptyAny")
                : t("journals.runs.empty", { period: periodLabel })
            }
            description={t("journals.runs.emptyDescription")}
            headingLevel={3}
            action={canRun ? { label: t("journals.runs.action.run"), onAction: onRun } : undefined}
          />
        }
        noResults={
          <EmptyState
            title={t("journals.runs.noResults")}
            description=""
            headingLevel={3}
            action={{ label: t("journals.clearFilters"), onAction: onClear }}
          />
        }
      />
    </div>
  );
}

/** DS-CMP-24 progress of one calculation, then its toast or its failure banner (SB-R-06). */
function CalculationProgress({ calculation }: { readonly calculation: Calculation }) {
  const job = useJob(calculation.jobId);
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const announced = useRef(false);
  const data = job.data;
  const label = { entity: calculation.entity, period: calculation.periodLabel };
  useEffect(() => {
    if (data === undefined || !isTerminal(data) || announced.current) {
      return;
    }
    announced.current = true;
    void queryClient.invalidateQueries({ queryKey: EVERY_JOURNAL_RUN });
    if (data.state !== "SUCCEEDED" && data.state !== "SUCCEEDED_WITH_EXCEPTIONS") {
      return;
    }
    const match = /\/journal-runs\/([0-9a-f-]{36})/.exec(data.result?.href ?? "");
    const runId = match?.[1];
    toast.show({
      tone: "positive",
      message: t("journals.runs.calculated", label),
      action:
        runId === undefined
          ? undefined
          : {
              label: t("journals.runs.openRun"),
              // D-89 L7-3-Q-32: the run's own context in SCR-URL-20 order, not the page search.
              onAction: () =>
                void navigate(
                  `${runRoute(runId)}${withParams("", {
                    entity: encodeURIComponent(calculation.entity),
                    period: encodeURIComponent(calculation.periodKey),
                    book: encodeURIComponent(calculation.book),
                  })}`,
                ),
            },
    });
  });
  if (data === undefined) {
    return null;
  }
  if (data.state === "FAILED") {
    return (
      <div data-testid="SF-06-banner-calculation-failed">
        <Banner
          tone="negative"
          announce="static"
          title={t("journals.runs.calculationFailed", {
            ...label,
            problem: data.problem?.title ?? NO_VALUE,
          })}
        />
      </div>
    );
  }
  if (isTerminal(data)) {
    return null;
  }
  return (
    <JobProgress
      label={t("journals.runs.calculating", label)}
      job={data}
      unit={t("journals.runs.unit")}
    />
  );
}

interface RunJournalsDialogProps {
  readonly entities: readonly Entity[];
  readonly access: Access;
  readonly context: {
    readonly entity: string | null;
    readonly period: string | null;
    readonly book: string | null;
  };
  readonly onClose: () => void;
  readonly onStarted: (started: readonly Calculation[]) => void;
}

/** §3.1 "Run journals" (DS-CMP-11 form modal): one `POST /journal-runs` per entity. */
function RunJournalsDialog({
  entities,
  access,
  context,
  onClose,
  onStarted,
}: RunJournalsDialogProps) {
  const formId = useId();
  // A run is a record of one entity (SCR-PERM-02 (a)): the field offers the entities `journal.run` is
  // held for, and the context entity is chosen only when it is one of them.
  const [codes, setCodes] = useState<readonly string[]>(
    context.entity !== null && access.holds(JOURNAL_RUN_PERMISSION, { code: context.entity })
      ? [context.entity]
      : [],
  );
  const [book, setBook] = useState<"ASC606" | "IFRS15">(
    context.book === "IFRS15" ? "IFRS15" : "ASC606",
  );
  const [periodKey, setPeriodKey] = useState<string | null>(context.period);
  const [mode, setMode] = useState<JournalRunMode>("GROSS");
  const [modeChosen, setModeChosen] = useState(false);
  const [grain, setGrain] = useState<JournalRunGrain | null>(null);
  const [cutoffText, setCutoffText] = useState("");
  const [attempted, setAttempted] = useState(false);
  // D-87 L6-5-Q-8: "Cut-off known at (optional)" behind "Advanced"; the API defaults it to now.
  const cutoff = parseCutoff(cutoffText, Date.now());
  const first = codes[0] ?? null;
  const periodQuery = { entity: first ?? "", book };
  const periods = useQuery({
    queryKey: periodsKey(periodQuery),
    queryFn: () => fetchPeriods(periodQuery),
    // The periods of one entity: `config.read` is asked for that entity.
    enabled: first !== null && access.holds(STRUCTURE_READ_PERMISSION, { code: first }),
  });
  const periodOptions: readonly Choice<string>[] = (periods.data ?? []).flatMap((item) => {
    const word = RUNNABLE_PERIODS[item.state];
    return word === undefined
      ? []
      : [
          {
            value: item.period.period_key,
            // "Jan 2023 (Period open)": the period label and its DS-CMP-19 word (SCREENS_B §3.1).
            label: `${item.period.name} (${t(statusMessageKey(word))})`,
          },
        ];
  });
  const runnable = periodKey !== null && periodOptions.some((option) => option.value === periodKey);
  const periodLabel =
    periods.data?.find((item) => item.period.period_key === periodKey)?.period.name ??
    periodKey ??
    NO_VALUE;
  const queryClient = useQueryClient();
  const noAnswer = useNoAnswer();
  // One press sends one start per entity (DG-FE-05 rev 1.156). Each start keeps its key until the
  // whole press is done: when a later entity is refused or gets no answer, the next press sends
  // the earlier starts again under their keys and the API replays the runs it started, where one
  // hook would have forgotten every key but the last and started them a second time.
  const keys = useCommandKeys();
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  // The calculations the page already follows: a replayed start is not reported a second time.
  const followed = useRef(new Set<string>());

  const submit = async () => {
    setAttempted(true);
    if (codes.length === 0 || periodKey === null || !runnable || cutoff.error !== null) {
      return;
    }
    setPending(true);
    setProblem(null);
    const started: Calculation[] = [];
    try {
      for (const code of codes) {
        // POL-005 and POL-006 apply unless the user chose a mode or a summarization (API-S-JournalRunCreate).
        const response = await keys.send("POST", JOURNAL_RUNS_PATH, {
          body: {
            entity_code: code,
            book,
            period_key: periodKey,
            ...(modeChosen ? { mode } : {}),
            ...(grain === null ? {} : { grain }),
            ...(cutoff.value === null ? {} : { cutoff_known_at: cutoff.value }),
          },
          keep: true,
        });
        const jobId = acceptedJobId(response);
        if (jobId === null) {
          if (!response.ok) {
            setProblem(await readProblem(response));
          }
          break;
        }
        started.push({ jobId, entity: code, periodKey, book, periodLabel });
      }
    } catch {
      // No answer to a start: the dialog keeps its input and says so.
      noAnswer();
    } finally {
      setPending(false);
    }
    const fresh = started.filter((item) => !followed.current.has(item.jobId));
    for (const item of fresh) {
      followed.current.add(item.jobId);
    }
    if (fresh.length > 0) {
      void queryClient.invalidateQueries({ queryKey: EVERY_JOURNAL_RUN });
      onStarted(fresh);
    }
    if (started.length === codes.length) {
      keys.clear();
      onClose();
    }
  };

  const entityOptions = entities
    .filter((item) => access.holds(JOURNAL_RUN_PERMISSION, item))
    .map((item) => ({ value: item.code, label: item.code }));
  const books: readonly Choice<"ASC606" | "IFRS15">[] = [
    { value: "ASC606", label: bookText("ASC606") },
    { value: "IFRS15", label: bookText("IFRS15") },
  ];
  const grains: readonly Choice<JournalRunGrain>[] = GRAINS.map((value) => ({
    value,
    label: grainText(value),
  }));
  return (
    <Modal
      open
      variant="form"
      title={t("journals.runForm.title")}
      primaryAction={{ label: t("journals.runForm.confirm"), form: formId }}
      submitting={pending}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <RefusalBanner problem={problem} />
        <Field
          name="journal-run-entities"
          label={t("journals.runForm.entities")}
          required
          width="full"
          error={attempted && codes.length === 0 ? t("journals.runForm.entitiesMissing") : null}
        >
          {(control) => (
            <MultiSelect
              control={control}
              options={entityOptions}
              values={codes}
              onChange={setCodes}
              invalid={attempted && codes.length === 0}
            />
          )}
        </Field>
        <SelectField
          name="journal-run-book"
          label={t("journals.runForm.book")}
          options={books}
          value={book}
          onChange={setBook}
        />
        <SelectField
          name="journal-run-period"
          label={t("journals.runForm.period")}
          options={periodOptions}
          value={runnable ? periodKey : null}
          onChange={setPeriodKey}
          error={attempted && !runnable ? t("journals.runForm.periodMissing") : null}
        />
        <SegmentedControl<JournalRunMode>
          label={t("journals.runForm.mode")}
          options={MODES.map((value) => ({ value, label: modeText(value) }))}
          value={mode}
          onChange={(value) => {
            setMode(value);
            setModeChosen(true);
          }}
        />
        <SelectField
          name="journal-run-grain"
          label={t("journals.runForm.summarization")}
          optional
          options={grains}
          value={grain}
          onChange={setGrain}
        />
        <details
          data-testid="SF-06-run-form-advanced"
          className="flex flex-col gap-2"
          open={attempted && cutoff.error !== null ? true : undefined}
        >
          <summary className="cursor-pointer rounded-sm text-body-sm font-semibold text-fg-1">
            {t("journals.runForm.advanced")}
          </summary>
          <div className="mt-2">
            <TextField
              name="journal-run-cutoff"
              label={t("journals.runForm.cutoff")}
              optional
              help={t("journals.runForm.cutoffHelp")}
              value={cutoffText}
              onChange={setCutoffText}
              error={attempted ? cutoff.error : null}
            />
          </div>
        </details>
      </form>
    </Modal>
  );
}
