// SF-15:calendars Calendars and periods (SCREENS_B §9.3; SCREENS §0.4 RT-76, §0.5 SCR-URL-27 `calendar`,
// `f.fiscal_year`, §0.7 SCR-ST-03, SCR-PERM-01, SCR-PERM-02, §0.4 E-04, E-50; DESIGN_SYSTEM DS-CMP-08,
// DS-CMP-10, DS-CMP-11, DS-CMP-19; 04 API-R-18 `GET, POST /calendars`, `POST /calendars/{id}/generate-year`,
// `GET /periods?fiscal_year&entity`, `POST /periods/{id}/open` (`If-Match`), API-R-17 `GET /entities`,
// `GET /books`, `GET /tenant`; BR-REF-02; REQ-REF-002, REQ-REF-003; BUILD_SPEC RFD-18). The Settings frame
// with the Workspace route tabs and a master-detail: the calendars list (selection in `calendar`) and,
// for the selected calendar, the "Fiscal year" select, "Generate fiscal year" and the DataGrid "Periods"
// with one E-04 chip column per entity × enabled book using the calendar; a ghost "Open" sits in
// `future` cells whose previous period is not `future`. "New calendar" and "Generate fiscal year" need
// `masterdata.maintain` or `settings.manage`; "Open period" needs `period.close`, or `settings.manage`
// while `tenant.setup_completed_at` is null (J-01.2). Editing a calendar (BR-REF-02 future-period
// preview) has no API route in API-R-18 and is not built.
import { useQuery } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useCallback, useId, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import { type GridColumn, type GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { controlClass, Field } from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { MasterDetail, type MasterItem } from "../../components/record/MasterDetail";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { type Access, useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import {
  buildPeriodRows,
  type Calendar,
  CALENDAR_CODE_PATTERN,
  CALENDAR_MAINTAIN_PERMISSIONS,
  CALENDAR_PATTERNS,
  type CalendarCreate,
  type CalendarPattern,
  CALENDARS_PATH,
  calendarSearch,
  canOpenCell,
  EVERY_CALENDAR,
  fiscalYearLabel,
  fiscalYearOf,
  fiscalYearOptions,
  fiscalYearParam,
  type GenerateYearResult,
  generateYearPath,
  matrixColumnKey,
  type PeriodMatrixRow,
  selectCalendar,
  useCalendars,
  WEEK_BASED_PATTERNS,
  YEAR_END_ANCHORS,
  type YearEndAnchor,
} from "../../lib/api/queries/calendars";
import { BOOK_CODES, bookLabel, useAllEntities } from "../../lib/api/queries/entities";
import { useMe } from "../../lib/api/queries/me";
import {
  EVERY_PERIOD,
  PERIOD_CLOSE_PERMISSION,
  periodCommandPath,
} from "../../lib/api/queries/periods";
import {
  type Book,
  type BookCode,
  booksKey,
  type Entity,
  fetchBooks,
  fetchPeriods,
  type Period,
  periodLabel,
  periodsKey,
  rowIfMatch,
  STRUCTURE_READ_PERMISSION,
  useTenant,
} from "../../lib/api/queries/tenant";
import { fieldMessages, placeProblem } from "../../lib/api/refusals";
import { dateParts, formatDate, formatNumber, utcDateOf } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { SettingsPageHeader, useBuiltPaths } from "./index";

/** SCREENS RT-59 SF-05: the period cockpit of an entity, book and period. */
const COCKPIT_ROUTE = "/close/:entity/:book/:period";
const SETTINGS_MANAGE_PERMISSION = "settings.manage";
const MONTHS: readonly number[] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
const WEEKDAYS: readonly number[] = [1, 2, 3, 4, 5, 6, 7];

function patternLabel(pattern: CalendarPattern): string {
  return t(`settings.calendars.pattern.${pattern}`);
}

function monthLabel(month: number): string {
  return t(`settings.calendars.month.${String(month)}`);
}

/** SCREENS_B §9.3 list line 2: "Monthly · January", or with the week end for week-based patterns. */
export function calendarSummary(calendar: Calendar): string {
  const params = {
    pattern: patternLabel(calendar.pattern),
    month: monthLabel(calendar.fiscal_year_start_month),
  };
  // The plain form is a join of two catalogue values, so it needs no template of its own.
  return calendar.week_end_day === null
    ? `${params.pattern} · ${params.month}`
    : t("settings.calendars.summaryWeekly", {
        ...params,
        weekday: t(`settings.calendars.weekday.${String(calendar.week_end_day)}`),
      });
}

function stateLabel(period: Period): string {
  return chipFor("E-04", period.state)?.status ?? period.state;
}

interface MatrixColumn {
  readonly key: string;
  readonly entity: Entity;
  readonly book: BookCode;
  readonly label: string;
}

/** One column per entity × enabled book using the calendar, entities in code order, books in E-02 order. */
export function matrixColumns(
  entities: readonly Entity[],
  calendarId: string,
  books: readonly Book[],
): readonly MatrixColumn[] {
  const columns: MatrixColumn[] = [];
  for (const entity of entities.filter((candidate) => candidate.calendar_id === calendarId)) {
    for (const book of BOOK_CODES) {
      if (entity.books.some((row) => row.book_code === book && row.is_enabled)) {
        columns.push({
          key: matrixColumnKey(entity.code, book),
          entity,
          book,
          label: `${entity.code} ${bookLabel(book, books)}`,
        });
      }
    }
  }
  return columns;
}

export function CalendarsScreen() {
  const me = useMe();
  const access = useAccess();
  const title = t("settings.calendars.title");

  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else if (!access.holdsAnywhere(STRUCTURE_READ_PERMISSION)) {
    body = (
      <EmptyState
        title={t("settings.access.title", { area: title })}
        description={t("settings.access.description", {
          permission: t("settings.access.permission.configRead"),
        })}
      />
    );
  } else {
    return <CalendarsPage access={access} />;
  }
  return (
    <div
      data-testid="SF-15-calendars-page"
      className="flex w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="workspace" />
      {body}
    </div>
  );
}

type Dialog =
  | { readonly kind: "none" }
  | { readonly kind: "new-calendar" }
  | { readonly kind: "generate"; readonly calendar: Calendar }
  | { readonly kind: "open"; readonly period: Period; readonly column: MatrixColumn };

function CalendarsPage({ access }: { readonly access: Access }) {
  const { search } = useLocation();
  const navigate = useNavigate();
  const title = t("settings.calendars.title");
  const maintain = CALENDAR_MAINTAIN_PERMISSIONS.some((permission) =>
    access.holdsAnywhere(permission),
  );
  const tenant = useTenant(access.holdsForAll(SETTINGS_MANAGE_PERMISSION));
  const inSetup = tenant.data?.setup_completed_at === null;
  // 04 API-R-18; SCREENS §0.6 SCR-PERM-02 (a) and (c): a period is opened for one entity by
  // `period.close` held for that entity. While the workspace is being set up `settings.manage`
  // opens it too — the setup is the workspace's, so held for all entities, which is also what the
  // read that says "in setup" asks.
  const canOpen = useCallback(
    (column: MatrixColumn) =>
      access.holds(PERIOD_CLOSE_PERMISSION, column.entity) ||
      (inSetup && access.holdsForAll(SETTINGS_MANAGE_PERMISSION)),
    [access, inSetup],
  );
  const calendars = useCalendars();
  const [dialog, setDialog] = useState<Dialog>({ kind: "none" });
  const params = new URLSearchParams(search);
  const selected = selectCalendar(calendars.data ?? [], params.get("calendar"));
  const fiscalYear = fiscalYearParam(search);
  const items: MasterItem[] = (calendars.data ?? []).map((calendar) => ({
    id: calendar.id,
    name: calendar.code,
    identifier: calendarSummary(calendar),
    optionLabel: `${calendar.code}, ${calendarSummary(calendar)}`,
    testId: `SF-15-calendar-${calendar.code}`,
  }));
  const select = (calendarId: string) => {
    const code = calendars.data?.find((calendar) => calendar.id === calendarId)?.code ?? null;
    void navigate({ search: calendarSearch(code, fiscalYear) }, { replace: true });
  };
  const newCalendar = maintain
    ? { label: t("settings.calendars.new"), onAction: () => setDialog({ kind: "new-calendar" }) }
    : undefined;
  const close = () => setDialog({ kind: "none" });

  let body: ReactNode;
  if (calendars.isError) {
    body = <Banner tone="negative" title={t("settings.calendars.loadError")} />;
  } else if (calendars.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else if (calendars.data.length === 0) {
    body = (
      <div data-testid="SF-15-empty-calendars">
        <EmptyState
          title={t("settings.calendars.empty.title")}
          description={t("settings.calendars.empty.description")}
          action={newCalendar}
        />
      </div>
    );
  } else {
    body = (
      <div data-testid="SF-15-calendars-list" className="flex min-h-0 flex-1 flex-col">
        <MasterDetail
          type="calendars"
          listLabel={t("settings.calendars.list")}
          items={items}
          selectedId={selected?.id ?? null}
          onSelect={select}
          toolbar={
            <div className="flex items-center justify-between gap-3 px-3 py-2">
              <span className="text-body-sm font-medium text-fg-1">
                {t("settings.calendars.listCount", {
                  formatted: formatNumber(calendars.data.length, { kind: "count" }),
                })}
              </span>
              {newCalendar === undefined ? null : (
                <Button variant="secondary" size="sm" onClick={newCalendar.onAction}>
                  {newCalendar.label}
                </Button>
              )}
            </div>
          }
          detailLabel={t("settings.calendars.detailLabel", { code: selected?.code ?? "" })}
          noSelection={t("settings.calendars.noSelection")}
          detailTestId="SF-15-pane-periods"
        >
          {selected === null ? null : (
            <CalendarDetail
              calendar={selected}
              fiscalYear={fiscalYear}
              maintain={maintain}
              canOpen={canOpen}
              onFiscalYear={(year) =>
                void navigate({ search: calendarSearch(selected.code, year) }, { replace: true })
              }
              onGenerate={() => setDialog({ kind: "generate", calendar: selected })}
              onOpen={(period, column) => setDialog({ kind: "open", period, column })}
            />
          )}
        </MasterDetail>
      </div>
    );
  }

  return (
    <div
      data-testid="SF-15-calendars-page"
      className="flex h-full min-h-0 w-full flex-col gap-4 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="workspace" />
      {body}
      {dialog.kind === "new-calendar" ? (
        <NewCalendarModal
          onClose={close}
          onCreated={(calendar) => {
            close();
            void navigate({ search: calendarSearch(calendar.code, fiscalYear) }, { replace: true });
          }}
        />
      ) : null}
      {dialog.kind === "generate" ? (
        <GenerateYearModal calendar={dialog.calendar} defaultYear={fiscalYear} onClose={close} />
      ) : null}
      {dialog.kind === "open" ? (
        <OpenPeriodModal period={dialog.period} column={dialog.column} onClose={close} />
      ) : null}
    </div>
  );
}

interface CalendarDetailProps {
  readonly calendar: Calendar;
  readonly fiscalYear: number | null;
  readonly maintain: boolean;
  /** Whether the member may open a period of the column's entity. */
  readonly canOpen: (column: MatrixColumn) => boolean;
  readonly onFiscalYear: (year: number) => void;
  readonly onGenerate: () => void;
  readonly onOpen: (period: Period, column: MatrixColumn) => void;
}

function CalendarDetail({
  calendar,
  fiscalYear,
  maintain,
  canOpen,
  onFiscalYear,
  onGenerate,
  onOpen,
}: CalendarDetailProps) {
  const built = useBuiltPaths();
  const entities = useAllEntities();
  const books = useBooks();
  const currentYear = fiscalYearOf(calendar, dateParts(utcDateOf(Date.now())));
  const year = fiscalYear ?? currentYear;
  const years = fiscalYearOptions(currentYear, fiscalYear);
  const columns = useMemo(
    () => matrixColumns(entities.data ?? [], calendar.id, books.data ?? []),
    [entities.data, calendar.id, books.data],
  );
  const cockpitBuilt = built.has(COCKPIT_ROUTE);
  const entityCodes = columns.map((column) => column.entity.code);
  const source: GridSource<PeriodMatrixRow> = useMemo(
    () => ({
      queryKey: periodsKey({
        view: "matrix",
        calendar: calendar.id,
        fiscal_year: String(year),
        entities: [...new Set(entityCodes)].join(","),
      }),
      fetchPage: async () => {
        const rows =
          entityCodes.length === 0
            ? []
            : markOpenable(
                buildPeriodRows(
                  await fetchPeriods({ fiscal_year: year, entity: [...new Set(entityCodes)] }),
                ),
              );
        return { items: rows, nextCursor: null, total: { count: rows.length, capped: false } };
      },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the entity codes are joined into the key
    [calendar.id, year, entityCodes.join(",")],
  );
  const gridColumns = useMemo(
    () => periodColumns(columns, canOpen, cockpitBuilt, onOpen),
    [columns, canOpen, cockpitBuilt, onOpen],
  );
  const countLabel = (value: number, formatted: string) =>
    t("settings.calendars.periods.count", { count: value, formatted });
  const generate = maintain
    ? { label: t("settings.calendars.generate"), onAction: onGenerate }
    : undefined;
  const yearId = useId();
  const emptyPeriods = (
    <div data-testid="SF-15-empty-periods">
      <EmptyState
        title={t("settings.calendars.periods.empty.title", { fiscalYear: fiscalYearLabel(year) })}
        description={t("settings.calendars.periods.empty.description")}
        action={generate}
      />
    </div>
  );

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col">
          <h2 className="text-title-sm text-fg-1">
            <span className="font-mono text-mono">{calendar.code}</span> · {calendar.name}
          </h2>
          <p className="text-body-sm text-fg-3">{calendarSummary(calendar)}</p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <Field
            name={`fiscal-year-${yearId}`}
            label={t("settings.calendars.fiscalYear")}
            width="period"
          >
            {(control) => (
              <Select<string>
                control={control}
                options={years.map((candidate) => ({
                  value: String(candidate),
                  label: fiscalYearLabel(candidate),
                }))}
                value={String(year)}
                onChange={(value) => onFiscalYear(Number(value))}
              />
            )}
          </Field>
          {generate === undefined ? null : (
            <Button variant="secondary" onClick={generate.onAction}>
              {generate.label}
            </Button>
          )}
        </div>
      </div>
      {columns.length === 0 && entities.data !== undefined ? (
        <Banner tone="info" announce="static" title={t("settings.calendars.periods.noEntities")} />
      ) : null}
      <div className="flex min-h-0 flex-1 flex-col">
        {entities.data === undefined || books.data === undefined ? (
          // The state columns need the calendar's entities and books before the grid asks for periods.
          <Skeleton region={t("settings.calendars.periods.grid")} shape="rows" count={6} />
        ) : (
          <DataGrid<PeriodMatrixRow>
            name="periods"
            title={t("settings.calendars.periods.grid")}
            errorTitle={t("settings.calendars.periods.loadError")}
            countLabel={countLabel}
            columns={gridColumns}
            source={source}
            rowKey={(row) => row.key}
            rowLabel={(row) => row.key}
            testIdPrefix="SF-15"
            rowTestKey={(row) => row.key}
            emptyState={emptyPeriods}
            // `f.fiscal_year` is a screen parameter (SCR-URL-27), not a grid filter: the same state.
            noResults={emptyPeriods}
          />
        )}
      </div>
    </div>
  );
}

function useBooks() {
  return useQuery({ queryKey: booksKey(), queryFn: fetchBooks });
}

/** SCREENS_B §9.3 periods grid: the calendar columns, then one state column per entity × book. */
export function periodColumns(
  matrix: readonly MatrixColumn[],
  canOpen: (column: MatrixColumn) => boolean,
  cockpitBuilt: boolean,
  onOpen: (period: Period, column: MatrixColumn) => void,
): readonly GridColumn<PeriodMatrixRow>[] {
  const fixed: GridColumn<PeriodMatrixRow>[] = [
    {
      id: "period_key",
      header: t("settings.calendars.periods.column.period"),
      kind: "identifier",
      value: (row) => row.key,
      width: 128,
    },
    {
      id: "name",
      header: t("settings.calendars.periods.column.name"),
      kind: "text",
      value: (row) => periodLabel(row.period),
      width: 112,
    },
    {
      id: "start_date",
      header: t("settings.calendars.periods.column.start"),
      kind: "date",
      value: (row) => row.period.start_date,
      render: (row) => <span className="num">{formatDate(row.period.start_date)}</span>,
    },
    {
      id: "end_date",
      header: t("settings.calendars.periods.column.end"),
      kind: "date",
      value: (row) => row.period.end_date,
      render: (row) => <span className="num">{formatDate(row.period.end_date)}</span>,
    },
    {
      id: "quarter_no",
      header: t("settings.calendars.periods.column.quarter"),
      kind: "number",
      numberKind: "count",
      value: (row) => String(row.period.quarter_no),
      width: 88,
    },
  ];
  const states: GridColumn<PeriodMatrixRow>[] = matrix.map((column) => ({
    id: `state:${column.key}`,
    header: column.label,
    kind: "status",
    value: (row) => {
      const cell = row.cells.get(column.key);
      return cell === undefined ? null : stateLabel(cell);
    },
    render: (row) => (
      <StateCell
        row={row}
        column={column}
        canOpen={canOpen(column)}
        cockpitBuilt={cockpitBuilt}
        onOpen={onOpen}
      />
    ),
    width: 184,
  }));
  return [...fixed, ...states];
}

function StateCell({
  row,
  column,
  canOpen,
  cockpitBuilt,
  onOpen,
}: {
  readonly row: PeriodMatrixRow;
  readonly column: MatrixColumn;
  readonly canOpen: boolean;
  readonly cockpitBuilt: boolean;
  readonly onOpen: (period: Period, column: MatrixColumn) => void;
}) {
  const cell = row.cells.get(column.key);
  if (cell === undefined) {
    return <span className="text-fg-3">—</span>;
  }
  // SCREENS_B §9.3 accessibility: "<entity code> <book label> <period label>: <state>", a join of
  // values rather than a catalogue template.
  const label = `${column.entity.code} ${bookLabel(column.book)} ${periodLabel(row.period)}: ${stateLabel(cell)}`;
  const chip = <StatusChip status={stateLabel(cell)} />;
  return (
    <span className="flex items-center gap-2" aria-label={label} role="group">
      {cockpitBuilt ? (
        <Link
          to={`/close/${encodeURIComponent(column.entity.code)}/${encodeURIComponent(column.book)}/${encodeURIComponent(row.key)}`}
          className="rounded-sm hover:underline"
        >
          {chip}
        </Link>
      ) : (
        chip
      )}
      {canOpen && cell.state === "future" && openable(row, column) ? (
        <Button
          variant="ghost"
          size="sm"
          aria-label={t("settings.calendars.periods.openFor", {
            period: periodLabel(row.period),
            entity: column.entity.code,
            book: bookLabel(column.book),
          })}
          onClick={() => onOpen(cell, column)}
        >
          {t("settings.calendars.periods.open")}
        </Button>
      ) : null}
    </span>
  );
}

// The grid renders one row at a time, so the previous-period rule reads the row's own marker set by
// `markOpenable` when the page is built.
const OPENABLE = new WeakMap<PeriodMatrixRow, ReadonlySet<string>>();

function openable(row: PeriodMatrixRow, column: MatrixColumn): boolean {
  return OPENABLE.get(row)?.has(column.key) ?? false;
}

/** Marks, per row, the columns whose `future` cell may be opened (SCREENS_B §9.3). */
export function markOpenable(rows: readonly PeriodMatrixRow[]): readonly PeriodMatrixRow[] {
  rows.forEach((row, index) => {
    const keys = new Set<string>();
    for (const key of row.cells.keys()) {
      if (canOpenCell(rows, index, key)) {
        keys.add(key);
      }
    }
    OPENABLE.set(row, keys);
  });
  return rows;
}

/** SCREENS_B §9.3 "New calendar" form modal. */
/**
 * docs/dev-guide.md DG-FE-06: the fields of "New calendar" that show a message of the API and the
 * members each sends. The week's end day and the year end's anchor are on screen for a week-based
 * pattern only; the start month shows no message. An error on a member without a field on screen is
 * the banner's.
 */
function calendarMembers(weekBased: boolean) {
  return {
    code: ["code"],
    name: ["name"],
    pattern: ["pattern"],
    week_end_day: weekBased ? ["week_end_day"] : [],
    year_end_anchor: weekBased ? ["year_end_anchor"] : [],
  } as const;
}
const GENERATE_MEMBERS = { fiscalYear: ["fiscal_year"] } as const;

function NewCalendarModal({
  onClose,
  onCreated,
}: {
  readonly onClose: () => void;
  readonly onCreated: (calendar: Calendar) => void;
}) {
  const formId = useId();
  const toast = useToast();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [pattern, setPattern] = useState<CalendarPattern | null>(null);
  const [startMonth, setStartMonth] = useState(1);
  const [weekEndDay, setWeekEndDay] = useState<number | null>(null);
  const [anchor, setAnchor] = useState<YearEndAnchor | null>(null);
  const [attempted, setAttempted] = useState(false);
  const create = useCommand<Calendar>({
    method: "POST",
    path: CALENDARS_PATH,
    invalidates: [EVERY_CALENDAR],
  });
  const weekBased = pattern !== null && WEEK_BASED_PATTERNS.has(pattern);
  const placed = useMemo(
    () => placeProblem(create.problem, calendarMembers(weekBased)),
    [create.problem, weekBased],
  );
  const errors: Record<string, string> = { ...fieldMessages(placed.fields) };
  if (attempted) {
    if (code.trim() === "") {
      errors.code ??= t("settings.calendars.newDialog.codeRequired");
    } else if (!CALENDAR_CODE_PATTERN.test(code.trim())) {
      errors.code ??= t("settings.calendars.newDialog.codeRule");
    }
    if (name.trim() === "") {
      errors.name ??= t("settings.calendars.newDialog.nameRequired");
    }
    if (pattern === null) {
      errors.pattern ??= t("settings.calendars.newDialog.patternRequired");
    }
    if (weekBased && weekEndDay === null) {
      errors.week_end_day ??= t("settings.calendars.newDialog.weekEndDayRequired");
    }
    if (weekBased && anchor === null) {
      errors.year_end_anchor ??= t("settings.calendars.newDialog.yearEndAnchorRequired");
    }
  }
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (
      code.trim() === "" ||
      !CALENDAR_CODE_PATTERN.test(code.trim()) ||
      name.trim() === "" ||
      pattern === null ||
      (weekBased && (weekEndDay === null || anchor === null))
    ) {
      return;
    }
    const body: CalendarCreate = {
      code: code.trim(),
      name: name.trim(),
      pattern,
      fiscal_year_start_month: startMonth,
      week_end_day: weekBased ? weekEndDay : null,
      year_end_anchor: weekBased ? anchor : null,
    };
    const outcome = await create.submit(body);
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      toast.show({
        tone: "positive",
        message: t("settings.calendars.newDialog.created", { code: outcome.data.code }),
      });
      onCreated(outcome.data);
    }
  };
  return (
    <Modal
      open
      variant="form"
      title={t("settings.calendars.newDialog.title")}
      primaryAction={{ label: t("settings.calendars.newDialog.submit"), form: formId }}
      submitting={create.pending}
      onClose={onClose}
      testId="SF-15-dialog-new-calendar"
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-3"
        onSubmit={(event) => void submit(event)}
      >
        <RefusalBanner problem={create.problem} placed={placed} />
        <Field
          name="code"
          label={t("settings.calendars.newDialog.code")}
          required
          error={errors.code ?? null}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              className={`${controlClass(errors.code !== undefined)} font-mono`}
            />
          )}
        </Field>
        <Field
          name="name"
          label={t("settings.calendars.newDialog.name")}
          required
          error={errors.name ?? null}
          width="full"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              className={controlClass(errors.name !== undefined)}
            />
          )}
        </Field>
        <Field
          name="pattern"
          label={t("settings.calendars.newDialog.pattern")}
          required
          error={errors.pattern ?? null}
          width="text"
        >
          {(control) => (
            <Select<CalendarPattern>
              control={control}
              options={CALENDAR_PATTERNS.map((value) => ({ value, label: patternLabel(value) }))}
              value={pattern}
              invalid={errors.pattern !== undefined}
              onChange={setPattern}
            />
          )}
        </Field>
        <Field
          name="fiscal_year_start_month"
          label={t("settings.calendars.newDialog.startMonth")}
          required
          width="text"
        >
          {(control) => (
            <Select<string>
              control={control}
              options={MONTHS.map((month) => ({ value: String(month), label: monthLabel(month) }))}
              value={String(startMonth)}
              onChange={(value) => setStartMonth(Number(value))}
            />
          )}
        </Field>
        {weekBased ? (
          <>
            <Field
              name="week_end_day"
              label={t("settings.calendars.newDialog.weekEndDay")}
              required
              error={errors.week_end_day ?? null}
              width="text"
            >
              {(control) => (
                <Select<string>
                  control={control}
                  options={WEEKDAYS.map((day) => ({
                    value: String(day),
                    label: t(`settings.calendars.weekday.${String(day)}`),
                  }))}
                  value={weekEndDay === null ? null : String(weekEndDay)}
                  invalid={errors.week_end_day !== undefined}
                  onChange={(value) => setWeekEndDay(Number(value))}
                />
              )}
            </Field>
            <Field
              name="year_end_anchor"
              label={t("settings.calendars.newDialog.yearEndAnchor")}
              required
              error={errors.year_end_anchor ?? null}
              width="text"
            >
              {(control) => (
                <Select<YearEndAnchor>
                  control={control}
                  options={YEAR_END_ANCHORS.map((value) => ({
                    value,
                    label: t(`settings.calendars.anchor.${value}`),
                  }))}
                  value={anchor}
                  invalid={errors.year_end_anchor !== undefined}
                  onChange={setAnchor}
                />
              )}
            </Field>
          </>
        ) : null}
      </form>
    </Modal>
  );
}

/** SCREENS_B §9.3 "Generate fiscal year" form modal. */
function GenerateYearModal({
  calendar,
  defaultYear,
  onClose,
}: {
  readonly calendar: Calendar;
  readonly defaultYear: number | null;
  readonly onClose: () => void;
}) {
  const formId = useId();
  const toast = useToast();
  const [text, setText] = useState(
    String(defaultYear ?? fiscalYearOf(calendar, dateParts(utcDateOf(Date.now())))),
  );
  const [attempted, setAttempted] = useState(false);
  const generate = useCommand<GenerateYearResult>({
    method: "POST",
    path: generateYearPath(calendar.id),
    invalidates: [EVERY_CALENDAR, EVERY_PERIOD],
  });
  const year = /^\d{4}$/.test(text.trim()) ? Number(text.trim()) : null;
  const valid = year !== null && year >= 1900 && year <= 2999;
  const placed = useMemo(
    () => placeProblem(generate.problem, GENERATE_MEMBERS),
    [generate.problem],
  );
  const error =
    placed.fields.fiscalYear ??
    (attempted && !valid ? t("settings.calendars.generateDialog.fiscalYearRequired") : null);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (!valid || year === null) {
      return;
    }
    const outcome = await generate.submit({ fiscal_year: year });
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      toast.show({
        tone: "positive",
        message: t("settings.calendars.generateDialog.generated", {
          formatted: formatNumber(outcome.data.inserted_count, { kind: "count" }),
          fiscalYear: fiscalYearLabel(outcome.data.fiscal_year),
        }),
      });
      onClose();
    }
  };
  return (
    <Modal
      open
      variant="form"
      title={t("settings.calendars.generateDialog.title")}
      primaryAction={{ label: t("settings.calendars.generateDialog.submit"), form: formId }}
      submitting={generate.pending}
      onClose={onClose}
      testId="SF-15-dialog-generate-year"
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-3"
        onSubmit={(event) => void submit(event)}
      >
        <RefusalBanner problem={generate.problem} placed={placed} />
        <Field
          name="fiscal_year"
          label={t("settings.calendars.generateDialog.fiscalYear")}
          required
          help={t("settings.calendars.generateDialog.fiscalYearHelp")}
          error={error}
          width="period"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              inputMode="numeric"
              value={text}
              onChange={(event) => setText(event.target.value)}
              className={`${controlClass(error !== null)} num`}
            />
          )}
        </Field>
      </form>
    </Modal>
  );
}

/** SCREENS_B §9.3 "Open period" confirmation: `POST /periods/{id}/open` with `If-Match`. */
function OpenPeriodModal({
  period,
  column,
  onClose,
}: {
  readonly period: Period;
  readonly column: MatrixColumn;
  readonly onClose: () => void;
}) {
  const toast = useToast();
  const open = useCommand<Period>({
    method: "POST",
    path: periodCommandPath(period.id, "open"),
    ifMatch: rowIfMatch(period.row_version),
    invalidates: [EVERY_PERIOD],
  });
  const params = {
    period: periodLabel(period.period),
    entity: column.entity.code,
    book: bookLabel(column.book),
  };
  return (
    <Modal
      open
      variant="confirmation"
      title={t("settings.calendars.openDialog.title", params)}
      description={t("settings.calendars.openDialog.description")}
      primaryAction={{
        label: t("settings.calendars.openDialog.confirm"),
        onAction: () => {
          void (async () => {
            const outcome = await open.submit({});
            if (outcome.kind === "succeeded") {
              toast.show({
                tone: "positive",
                message: t("settings.calendars.openDialog.opened", params),
              });
              onClose();
            }
          })();
        },
      }}
      submitting={open.pending}
      onClose={onClose}
      testId="SF-15-dialog-open-period"
    >
      <RefusalBanner problem={open.problem} conflict={open.banner} />
    </Modal>
  );
}
