// SF-06:entries Journal entries by date range (SCREENS_B §3 area header, §3.5; §0.5 RV-01 to RV-14; §5.6
// RPT-13 `legacy_je_summary`; SCREENS RT-30, SCR-URL-16, SCR-URL-25; DESIGN_SYSTEM DS-CMP-10, DS-CMP-21,
// DS-CMP-31; REQ-JE-007 to REQ-JE-009; BUILD_SPEC RPS-7). The Journals area header with the route tabs,
// the parameters toolbar (Entities, From, To, the segmented control "Journal view", "Run report"), the run
// stamp with "Run details" and "Export", and one grid per RPT-13 section: "Journal lines by account" with
// the totals row of the run's control totals, "Journal lines by entity" with the balance flag, and "Line
// items" keyed by the legacy key. `format=gross|adjustment` reaches the run as `mode` `GROSS` or `DELTA`,
// and `from` and `to` as `from_date` and `to_date` (SCREENS_B §3.5 route). [J] Integration after merge
// (D-81): the RPT-13 builder is RPS-5 (lane L7-1); its rows name `section` `by_account`, `by_entity` or
// `line_items`, and its control totals `total_debit`, `total_credit` and `net` per currency. D-88 L7-3-Q-22:
// each grid is described by the §3.5 caption "<grid>, <from> to <to>, <view> view"; the Legacy book banner
// answers only the RPS-5 LEGACY_NOT_KEPT refusal, and any other failed run shows SCR-ST-12 (RV-14).
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useCallback, useEffect, useId, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router";

import type { GridColumn, GridTotalsRow } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { JobProgress } from "../../components/feedback/JobProgress";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { Field } from "../../components/form/Field";
import { MultiSelect } from "../../components/form/MultiSelect";
import { Button } from "../../components/ui/Button";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { StatusChip } from "../../components/ui/StatusChip";
import { type Access, useAccess } from "../../lib/access";
import { ApiProblem } from "../../lib/api/problems";
import { useMe } from "../../lib/api/queries/me";
import {
  fetchReportDefinition,
  fetchReportRun,
  REPORT_EXPORT_PERMISSION,
  type ReportDefinition,
  reportDefinitionKey,
  type ReportRow,
  type ReportRun,
  reportRunKey,
} from "../../lib/api/queries/reports";
import {
  entitiesKey,
  fetchActiveEntities,
  fetchPeriods,
  type Period,
  periodsKey,
  STRUCTURE_READ_PERMISSION,
} from "../../lib/api/queries/tenant";
import { formatDate } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { withParams } from "../../lib/url/params";
import { ExportMenu } from "../reports/viewer/ExportMenu";
import { DateParameter } from "../reports/viewer/ParametersToolbar";
import { type DrillRequest, ReportGrid } from "../reports/viewer/ReportGrid";
import { RunDetailsDrawer } from "../reports/viewer/RunDetailsDrawer";
import { RunStamp } from "../reports/viewer/RunStamp";
import {
  CURRENCY_COLUMN_KEY,
  isMoney,
  JOURNAL_VIEW_FORMATS,
  LEGACY_JE_SUMMARY,
  type ReportColumn,
  type ReportColumnKind,
  type ReportSection,
  validateParameters,
} from "../reports/viewer/specs";
import { JobReference } from "../reports/viewer/JobReference";
import { useReportRun } from "../reports/viewer/useReportRun";
import { JournalsAreaHeader } from "./journal-runs";

const RUN_DETAILS = "run-details";
/** SCREENS_B §3.5 `format` literals in the segmented control's order. */
export const JOURNAL_VIEWS = ["gross", "adjustment"] as const;
export type JournalView = (typeof JOURNAL_VIEWS)[number];

export function JournalEntries() {
  const me = useMe();
  const access = useAccess();
  const definition = useQuery({
    queryKey: reportDefinitionKey(LEGACY_JE_SUMMARY),
    queryFn: () => fetchReportDefinition(LEGACY_JE_SUMMARY),
    retry: (count, error) => !(error instanceof ApiProblem && error.status === 404) && count < 1,
  });
  if (me.isError) {
    return <Banner tone="negative" title={me.error.message} />;
  }
  if (definition.error !== null) {
    return (
      <div data-testid="SF-06-page" className="flex flex-col gap-4">
        <JournalsAreaHeader />
        <Banner
          tone="negative"
          title={t("journals.entries.loadError")}
          actions={
            <Button variant="link" onClick={() => void definition.refetch()}>
              {t("journals.retry")}
            </Button>
          }
        >
          <p>{definition.error.message}</p>
        </Banner>
      </div>
    );
  }
  if (me.data === undefined || definition.data === undefined) {
    return <Skeleton region={t("journals.entries.region")} shape="rows" count={8} />;
  }
  return <EntriesBody definition={definition.data} access={access} />;
}

interface EntrySection {
  readonly id: "by_account" | "by_entity" | "line_items";
  /** The row key prefix of the section (RPT-13). */
  readonly prefix: string;
  readonly name: string;
  readonly titleKey: string;
}

/** RPT-13 sections in order, with the SCREENS_B §3.5 grid names and test ids. */
const SECTIONS: readonly EntrySection[] = [
  {
    id: "by_account",
    prefix: "account:",
    name: "entries-by-account",
    titleKey: "journals.entries.byAccount",
  },
  {
    id: "by_entity",
    prefix: "entity:",
    name: "entries-by-entity",
    titleKey: "journals.entries.byEntity",
  },
  {
    id: "line_items",
    prefix: "item:",
    name: "entries-line-items",
    titleKey: "journals.entries.lineItems",
  },
];

function sectionRows(rows: readonly ReportRow[], section: EntrySection): readonly ReportRow[] {
  return rows.filter((row) =>
    typeof row.section === "string"
      ? row.section === section.id
      : row.row_key.startsWith(section.prefix),
  );
}

function currenciesOf(rows: readonly ReportRow[]): ReadonlySet<string> {
  return new Set(
    rows.flatMap((row) =>
      Object.values(row).flatMap((value) => (isMoney(value) ? [value.currency] : [])),
    ),
  );
}

/** RPT-13 §5.6 columns of a section; money headers carry the ISO code of a one-currency run (RPT-R-03). */
export function entryColumns(section: EntrySection, rows: readonly ReportRow[]): ReportColumn[] {
  const currencies = currenciesOf(rows);
  const single = currencies.size === 1 ? [...currencies][0] : undefined;
  const entities = new Set(rows.map((row) => row.entity_code));
  const column = (key: string, kind: ReportColumnKind): ReportColumn => {
    const header = t(`journals.entries.column.${key}`);
    return {
      key,
      header: kind === "money" && single !== undefined ? `${header} (${single})` : header,
      kind,
      drillable: false,
    };
  };
  // RPT-R-03: the Currency column of a mixed-currency run; its totals cells name each row currency.
  const currency = currencies.size > 1 ? [column(CURRENCY_COLUMN_KEY, "text")] : [];
  switch (section.id) {
    case "by_account":
      return [
        column("account", "identifier"),
        ...currency,
        column("debit", "money"),
        column("credit", "money"),
        column("net", "money"),
      ];
    case "by_entity":
      return [
        column("entity_code", "identifier"),
        ...currency,
        column("debit", "money"),
        column("credit", "money"),
      ];
    case "line_items":
      return [
        column("key", "identifier"),
        column("account", "text"),
        ...(entities.size > 1 ? [column("entity_code", "text")] : []),
        ...currency,
        column("amount", "money"),
      ];
  }
}

/** The "By account" totals rows: one per currency from the run's control totals (DS-FMT-02). */
export function accountTotals(run: ReportRun): GridTotalsRow[] {
  const totals = run.control_totals ?? {};
  const byCurrency = (key: string): Readonly<Record<string, unknown>> => {
    const value = totals[key];
    return typeof value === "object" && value !== null
      ? (value as Readonly<Record<string, unknown>>)
      : {};
  };
  const debit = byCurrency("total_debit");
  const credit = byCurrency("total_credit");
  const net = byCurrency("net");
  return Object.keys(debit).flatMap((currency) => {
    const values: Record<string, string> = {};
    for (const [key, source] of [
      ["debit", debit],
      ["credit", credit],
      ["net", net],
    ] as const) {
      const amount = source[currency];
      if (typeof amount === "string") {
        values[key] = amount;
      }
    }
    return [{ key: `TOTAL:${currency}`, currency, values }];
  });
}

const BALANCED_COLUMN: GridColumn<ReportRow> = {
  id: "balanced",
  header: "",
  kind: "text",
  value: (row) => (row.balanced === true ? t("journals.yes") : t("journals.no")),
  render: (row) =>
    row.balanced === true ? (
      t("journals.yes")
    ) : (
      <span className="inline-flex items-center gap-1.5">
        {t("journals.no")}
        <StatusChip status="Difference" />
      </span>
    ),
  width: 144,
};

/** The context period: the URL period, else the first open period of the calendar (SCREENS §1.3). */
function resolvedPeriod(periods: readonly Period[], key: string | null): Period | null {
  return (
    periods.find((item) => item.period.period_key === key) ??
    periods.find((item) => item.is_first_open) ??
    null
  );
}

function viewOf(format: string | null): JournalView {
  return JOURNAL_VIEWS.find((item) => item === format) ?? "gross";
}

/** The T-REF-03 rule of the RPS-5 refusal "Enable the Legacy book for <code> before viewing …". */
const LEGACY_BOOK_RULE = "T-REF-03";
const MODE_FIELDS: ReadonlySet<string> = new Set(["mode", "parameters.mode"]);

/** The failed run's problem is the LEGACY_NOT_KEPT refusal: rule T-REF-03 on `mode` (D-88 L7-3-Q-22). */
export function legacyBookRefused(problem: ReportRun["problem"]): boolean {
  return (problem?.errors ?? []).some(
    (error) =>
      error.rule_id === LEGACY_BOOK_RULE &&
      typeof error.field === "string" &&
      MODE_FIELDS.has(error.field),
  );
}

interface EntriesBodyProps {
  readonly definition: ReportDefinition;
  readonly access: Access;
}

function EntriesBody({ definition, access }: EntriesBodyProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const toast = useToast();
  const search = location.search;
  const params = new URLSearchParams(search);
  const entity = params.get("entity");
  const book = params.get("book");
  const runId = params.get("run");
  const drawer = params.get("drawer");
  const view = viewOf(params.get("format"));
  const captionId = useId();

  // SCR-URL-20: search updates keep raw values; the latest search survives an awaited command.
  const latestSearch = useRef(search);
  useEffect(() => {
    latestSearch.current = search;
  });
  const replace = useCallback(
    (changes: Readonly<Record<string, string | null>>) => {
      void navigate({ search: withParams(latestSearch.current, changes) }, { replace: true });
    },
    [navigate],
  );

  const structure = access.holdsAnywhere(STRUCTURE_READ_PERMISSION);
  const periodQuery = { entity: entity ?? "", book: book ?? "" };
  // The periods of one entity: `config.read` is asked for that entity (SCR-PERM-02 (a)).
  const periodsEnabled =
    entity !== null && book !== null && access.holds(STRUCTURE_READ_PERMISSION, { code: entity });
  const periods = useQuery({
    queryKey: periodsKey(periodQuery),
    queryFn: () => fetchPeriods(periodQuery),
    enabled: periodsEnabled,
  });
  const entities = useQuery({
    queryKey: entitiesKey(),
    queryFn: fetchActiveEntities,
    enabled: structure,
  });
  const current = resolvedPeriod(periods.data ?? [], params.get("period"));
  const calendarReady = !periodsEnabled || periods.data !== undefined || periods.isError;

  // RPT-13 defaults: the first and last day of the context period; Gross; the context entity.
  const from = params.get("from") ?? current?.period.start_date ?? "";
  const to = params.get("to") ?? current?.period.end_date ?? "";
  const [appliedCodes, setAppliedCodes] = useState<readonly string[] | null>(null);
  const codes = appliedCodes ?? (entity === null ? [] : [entity]);
  const parameters: Record<string, unknown> = {
    ...(codes.length === 0 ? {} : { entity_codes: codes }),
    book: "ASC606",
    ...(from === "" ? {} : { from_date: from }),
    ...(to === "" ? {} : { to_date: to }),
    mode: JOURNAL_VIEW_FORMATS[view],
  };
  const [draft, setDraft] = useState<{
    readonly codes: readonly string[];
    readonly from: string;
    readonly to: string;
  } | null>(null);
  const values = draft ?? { codes, from, to };
  const [errors, setErrors] = useState<Readonly<Record<string, string>>>({});

  const { problem, run, rows, pendingJob, computing, createdJobId, restart } = useReportRun({
    definition,
    parameters,
    contextSignature: [entity, book, params.get("period")].join("|"),
    ready: calendarReady && from !== "" && to !== "",
    runId,
    replace,
  });

  const runReport = () => {
    const next: Record<string, string> = {};
    if (values.codes.length === 0) {
      next.entity_codes = t("journals.entries.entitiesMissing");
    }
    const order = validateParameters(
      {
        entity,
        book,
        periodKey: null,
        periods: [],
        snapshot: null,
        knownAt: null,
        currencyView: null,
      },
      { from_date: values.from, to_date: values.to },
    );
    const found = { ...next, ...order };
    setErrors(found);
    if (Object.keys(found).length > 0) {
      return;
    }
    if (computing) {
      toast.show({
        tone: "neutral",
        message: t("reports.report.alreadyRunning", { name: definition.name }),
      });
      return;
    }
    setAppliedCodes(values.codes);
    setDraft(null);
    restart();
    replace({
      run: null,
      from: values.from === "" ? null : encodeURIComponent(values.from),
      to: values.to === "" ? null : encodeURIComponent(values.to),
    });
  };

  // SCREENS_B §3.5: changing `format` re-runs with the new mode.
  const changeView = (next: JournalView) => {
    setDraft(null);
    restart();
    replace({ format: next === "gross" ? null : next, run: null });
  };

  const [detailsRunId, setDetailsRunId] = useState<string | null>(null);
  const details = useQuery({
    queryKey: reportRunKey(detailsRunId ?? runId ?? ""),
    queryFn: () => fetchReportRun(detailsRunId ?? runId ?? ""),
    enabled: drawer === RUN_DETAILS && (detailsRunId ?? runId) !== null,
  });
  const openDetails = useCallback(
    (id: string | null) => {
      setDetailsRunId(id);
      replace({ drawer: RUN_DETAILS });
    },
    [replace],
  );
  // RPT-13 names no drillable figure (§5.6 contributors wait for the explain cell route).
  const noDrill = (request: DrillRequest) => request;

  const data = run.data;
  const label = t("reports.report.running", { name: definition.name });
  // The refused creation's problem, bound to this parameter set and source (RV-01 rev 1.6; D-90e L9-PLT-Q-6).
  let body: ReactNode = null;
  if (computing && data?.status !== "FAILED") {
    body =
      pendingJob !== null ? (
        <JobProgress label={label} job={pendingJob} unit={t("reports.export.unit")} />
      ) : (
        <Skeleton region={label} shape="rows" count={6} />
      );
  } else if (
    data?.status === "FAILED" &&
    view === "adjustment" &&
    legacyBookRefused(data.problem)
  ) {
    body = (
      <Banner
        tone="info"
        announce="static"
        title={t("journals.entries.legacyBookNeeded", { entity: codes.join(", ") })}
      >
        {data.problem === null ? null : <p>{data.problem.title}</p>}
      </Banner>
    );
  } else if (data?.status === "FAILED") {
    body = (
      <Banner
        tone="negative"
        title={t("common.job.failed", { label })}
        actions={
          <Button variant="link" onClick={runReport}>
            {t("journals.retry")}
          </Button>
        }
      >
        {data.problem === null ? null : <p>{data.problem.title}</p>}
        {/* SCR-ST-12 "Reference <job id prefix>" as SF-08:report shows it (D-90 L8-R-Q-4): the run's own
            job, else the creation this view started (RV-14 rev 1.7). */}
        <JobReference run={data} createdJobId={createdJobId} />
      </Banner>
    );
  } else if (run.isError || rows.isError) {
    body = (
      <Banner
        tone="negative"
        title={t("journals.entries.loadError")}
        actions={
          <Button
            variant="link"
            onClick={() => void (run.isError ? run.refetch() : rows.refetch())}
          >
            {t("journals.retry")}
          </Button>
        }
      />
    );
  } else if (data?.status === "SUCCEEDED") {
    if (rows.data === undefined) {
      body = <Skeleton region={definition.name} shape="rows" count={8} />;
    } else if (rows.data.length === 0) {
      body = (
        <EmptyState
          title={t("journals.entries.empty.title", {
            from: from === "" ? "" : formatDate(from),
            to: to === "" ? "" : formatDate(to),
          })}
          description={t("journals.entries.empty.description")}
          headingLevel={2}
        />
      );
    } else {
      const all = rows.data;
      body = (
        <div className="flex flex-col gap-6">
          {SECTIONS.map((spec, index) => {
            const members = sectionRows(all, spec);
            const section: ReportSection = {
              number: index + 1,
              heading: t(spec.titleKey),
              rows: members,
              totals: [],
            };
            const balanced =
              spec.id === "by_entity"
                ? [{ ...BALANCED_COLUMN, header: t("journals.entries.column.balanced") }]
                : [];
            // §3.5 Accessibility: the grid keeps its name and is described by its range and view.
            const describedBy = `${captionId}-${spec.id}`;
            return (
              <div key={spec.id} className="flex flex-col">
                <p id={describedBy} className="sr-only">
                  {t(`journals.entries.caption.${view}`, {
                    grid: t(spec.titleKey),
                    from: from === "" ? "" : formatDate(from),
                    to: to === "" ? "" : formatDate(to),
                  })}
                </p>
                <ReportGrid
                  runId={data.id}
                  section={section}
                  columns={entryColumns(spec, members)}
                  totals={spec.id === "by_account" ? accountTotals(data) : []}
                  onDrill={noDrill}
                  testIdPrefix="SF-06"
                  name={spec.name}
                  describedBy={describedBy}
                  extraColumns={balanced}
                  emptyState={
                    <p className="p-4 text-body-sm text-fg-2">
                      {t("reports.report.section.empty")}
                    </p>
                  }
                />
              </div>
            );
          })}
        </div>
      );
    }
  }

  const canExport = access.holdsAnywhere(REPORT_EXPORT_PERMISSION);
  const entityOptions = (entities.data ?? []).map((item) => ({
    value: item.code,
    label: item.code,
  }));
  const codeOptions =
    entityOptions.length === 0
      ? values.codes.map((code) => ({ value: code, label: code }))
      : entityOptions;

  return (
    <div className="flex min-h-full gap-4">
      <div data-testid="SF-06-page" className="flex min-w-0 flex-1 flex-col gap-4">
        <JournalsAreaHeader />
        <div
          role="toolbar"
          aria-label={t("reports.parameters.label")}
          data-testid="SF-06-filter-bar-entries"
          className="flex flex-wrap items-end gap-3"
        >
          <Field
            name="entries-entities"
            label={t("journals.entries.entities")}
            required
            width="full"
            error={errors.entity_codes ?? null}
          >
            {(control) => (
              <MultiSelect
                control={control}
                options={codeOptions}
                values={values.codes}
                onChange={(next) => setDraft({ ...values, codes: next })}
                invalid={errors.entity_codes !== undefined}
              />
            )}
          </Field>
          <DateParameter
            key={`from:${values.from}`}
            name="entries-from"
            label={t("journals.entries.from")}
            value={values.from}
            error={errors.from_date}
            onChange={(next) => setDraft({ ...values, from: next })}
          />
          <DateParameter
            key={`to:${values.to}`}
            name="entries-to"
            label={t("journals.entries.to")}
            value={values.to}
            error={errors.to_date}
            onChange={(next) => setDraft({ ...values, to: next })}
          />
          <div data-testid="SF-06-entries-format">
            <SegmentedControl<JournalView>
              label={t("journals.entries.format")}
              options={JOURNAL_VIEWS.map((item) => ({
                value: item,
                label: t(`journals.entries.format.${item}`),
              }))}
              value={view}
              onChange={changeView}
            />
          </div>
          <Button variant="primary" onClick={runReport}>
            {t("reports.parameters.run")}
          </Button>
        </div>
        {data === undefined ? null : (
          <div className="flex flex-wrap items-start gap-3">
            <RunStamp run={data} lockCreatedAt={null} testIdPrefix="SF-06" />
            <span className="ms-auto inline-flex items-center gap-3">
              <Button variant="secondary" onClick={() => openDetails(null)}>
                {t("reports.report.runDetails")}
              </Button>
              {canExport && definition.output_formats.length > 0 ? (
                <ExportMenu
                  definition={definition}
                  parameters={data.parameters}
                  onDetails={openDetails}
                />
              ) : null}
            </span>
          </div>
        )}
        {problem === null ? null : (
          <Banner tone="negative" title={problem.title}>
            {problem.errors.map((error) => (
              <p key={error.message}>{error.message}</p>
            ))}
          </Banner>
        )}
        <div className="pb-[var(--panel-pad)]">{body}</div>
      </div>
      {drawer === RUN_DETAILS && details.data !== undefined ? (
        <RunDetailsDrawer
          run={details.data}
          testIdPrefix="SF-06"
          onClose={() => {
            setDetailsRunId(null);
            replace({ drawer: null });
          }}
        />
      ) : null}
    </div>
  );
}
