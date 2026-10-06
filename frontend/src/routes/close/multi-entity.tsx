// SF-05:multi-entity Multi-entity close (SCREENS_B §1.5; §0.4 E-04, E-62; SCREENS RT-27, RT-26, RT-99,
// RT-46, SCR-URL-01 to SCR-URL-03, SCR-PERM-01, SCR-PERM-02, SCR-ST-03, SCR-ST-05, SCR-ST-06;
// DESIGN_SYSTEM DS-CMP-10, DS-CMP-19, DS-CMP-21, DS-CMP-23; 04 API-R-39 §16.8, API-R-17, API-R-18,
// API-R-44; PRD J-13.16, J-13-AC-9, REQ-ENT-006, WLD-P-05; BUILD_SPEC CLO-24). Close runs for several
// entities of one period: the period and book are the context's, each chosen entity closes the period of
// its own calendar with the same dates (AVM-JP's Sep 2026 is FY2027-P06), and "Start close runs" sends
// one `POST /close-runs` per chosen entity, in the order shown, each row reading its own answer — 1.0
// has no route that starts several (supervisor ruling on question C of the lane's report). No period is
// locked here. The entities whose run for the period has not ended are chosen when the page opens, so a
// reader who returns finds the runs that are still moving.
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "react-router";

import { contextSearch } from "../../app/shell/IconRail";
import {
  type ContextChoice,
  contextOwner,
  readStoredContext,
  resolveEntityBook,
  resolvePeriod,
} from "../../app/shell/ContextPill";
import { useShellSession } from "../../app/shell/SandboxIndicator";
import { DataGrid } from "../../components/data-grid/DataGrid";
import type { GridColumn, GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { Field, fieldId } from "../../components/form/Field";
import { MultiSelect } from "../../components/form/MultiSelect";
import { NoValue } from "../../components/money/Num";
import { RecordHeader } from "../../components/record/RecordHeader";
import { Button } from "../../components/ui/Button";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { announce } from "../../lib/a11y/announce";
import { useCommandKeys } from "../../lib/api/commands";
import { sendCommand } from "../../lib/api/queries/contracts";
import {
  CLOSE_RUN_POLL_MS,
  type CloseRun,
  type CloseRunCreateIn,
  closeRunRoute,
  closeRunsKey,
  EVERY_CLOSE_RUN,
  fetchActiveCloseRuns,
  fetchCloseRuns,
  isMovingRun,
  stepNumber,
} from "../../lib/api/queries/close-runs";
import { EXCEPTION_QUEUE_ROUTE } from "../../lib/api/queries/exceptions";
import { useMe } from "../../lib/api/queries/me";
import {
  CLOSE_RUNS_PATH,
  EVERY_PERIOD,
  fetchOpenExceptionCount,
  openExceptionCountKey,
  PERIOD_CLOSE_PERMISSION,
} from "../../lib/api/queries/periods";
import {
  booksKey,
  type Entity,
  entitiesKey,
  fetchActiveEntities,
  fetchBooks,
  fetchPeriods,
  type Period,
  periodLabel,
  periodsKey,
} from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import type { ApiProblem } from "../../lib/api/problems";
import { formatDate, formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { withParams } from "../../lib/url/params";
import { useBuiltPaths } from "../settings/index";
import { bookLabel, cockpitRoute, FollowsLine, Mono, RetryBanner } from "./cockpit";

const CONTEXT = ["entity", "period", "book"] as const;
const COCKPIT_ROUTE = "/close/:entity/:book/:period";
const CLOSE_RUN_ROUTE = `${COCKPIT_ROUTE}/close-run`;
const FIELD_NAME = "multi-entity-entities";

export function MultiEntityClosePage() {
  const location = useLocation();
  const me = useMe();
  const ready = me.data !== undefined;
  const allowed = me.data?.permissions.includes(PERIOD_CLOSE_PERMISSION) === true;
  const entities = useQuery({
    queryKey: entitiesKey(),
    queryFn: fetchActiveEntities,
    enabled: ready && allowed,
  });
  const books = useQuery({ queryKey: booksKey(), queryFn: fetchBooks, enabled: ready && allowed });
  // The period and book are the context pill's (BR-UX-01): the URL, else the stored choice, else the
  // defaults; the period key is read on the calendar of the context entity.
  const params = new URLSearchParams(location.search);
  const url: ContextChoice = {
    entity: params.get("entity"),
    period: params.get("period"),
    book: params.get("book"),
  };
  const owner = contextOwner(me.data, useShellSession());
  const stored = owner === null ? null : readStoredContext(owner);
  const choices = stored === null ? [url] : [url, stored];
  const head =
    entities.data === undefined || books.data === undefined
      ? null
      : resolveEntityBook(entities.data, books.data, choices);
  const query = { entity: head?.entity.code ?? "", book: head?.book.code ?? "" };
  const periods = useQuery({
    queryKey: periodsKey(query),
    queryFn: () => fetchPeriods(query),
    enabled: head !== null,
  });

  if (me.error !== null) {
    return <Banner tone="negative" title={me.error.message} />;
  }
  if (ready && !allowed) {
    // SCR-PERM-01 (RT-27: `period.close`).
    return (
      <div data-testid="SF-05-page">
        <EmptyState
          title={t("settings.access.title", { area: t("close.multi.access.area") })}
          description={t("settings.access.description", {
            permission: t("close.multi.access.permission"),
          })}
        />
      </div>
    );
  }
  const failure = entities.error ?? books.error ?? periods.error;
  if (failure !== null) {
    return (
      <RetryBanner
        title={t("close.multi.loadError")}
        problem={failure}
        onRetry={() => {
          void entities.refetch();
          void books.refetch();
          void periods.refetch();
        }}
      />
    );
  }
  const reference =
    head === null || periods.data === undefined ? null : resolvePeriod(periods.data, choices);
  if (
    me.data === undefined ||
    entities.data === undefined ||
    books.data === undefined ||
    (head !== null && periods.data === undefined)
  ) {
    return (
      <div data-testid="SF-05-page">
        <Skeleton region={t("close.multi.region")} shape="rows" count={6} />
      </div>
    );
  }
  if (head === null || reference === null) {
    return (
      <div data-testid="SF-05-page">
        <EmptyState
          title={t("close.multi.noPeriodTitle")}
          description={t("close.multi.noPeriodDescription")}
        />
      </div>
    );
  }
  const book = head.book.code;
  const follows = reference.follows ?? null;
  if (follows !== null) {
    // 04 §16.8 rev 1.155, API-S-Period `follows` (supervisor rulings R-112 (e) and R-114 (d)): the
    // LEGACY book has no close of its own, so no entity is offered and nothing is started for it —
    // the line of the cockpit, and the way to this page in the book whose close it follows.
    const label = periodLabel(reference.period);
    const key = reference.period.period_key;
    return (
      <div data-testid="SF-05-page" className="flex flex-col gap-4">
        <RecordHeader
          title={t("close.multi.title", { period: label, book: bookLabel(book) })}
          breadcrumb={[
            {
              label: t("close.cockpit.documentTitle"),
              to: `/close${contextSearch(location.search, CONTEXT)}`,
            },
          ]}
        />
        <FollowsLine
          follows={follows}
          entity={head.entity.code}
          period={label}
          to={`${location.pathname}${withParams(location.search, {
            entity: encodeURIComponent(head.entity.code),
            period: encodeURIComponent(key),
            book: encodeURIComponent(follows.book_code),
          })}`}
          action={t("close.multi.follows.goTo", { book: bookLabel(follows.book_code) })}
        />
      </div>
    );
  }
  return (
    <MultiEntityView
      key={`${book}|${reference.period.start_date}|${reference.period.end_date}`}
      // SCREENS_B §1.5: the entities that keep the book, in code order.
      entities={entities.data
        .filter((entity) => entity.books.some((kept) => kept.book_code === book && kept.is_enabled))
        .sort((a, b) => (a.code < b.code ? -1 : a.code > b.code ? 1 : 0))}
      book={book}
      reference={reference}
    />
  );
}

/** One chosen entity: its period of the context's dates, its newest run there and its answer. */
export interface EntityRow {
  readonly entity: Entity;
  /** The entity's own period with the context period's dates; null where its calendar has none. */
  readonly period: Period | null;
  readonly run: CloseRun | null;
  /** The refusal of this page's last start for the entity, or that it did not reach the server. */
  readonly refusal: string | null;
  /** Open exceptions of the entity and period; null while they load or where there is no period. */
  readonly exceptions: number | null;
}

interface MultiEntityViewProps {
  readonly entities: readonly Entity[];
  readonly book: string;
  readonly reference: Period;
}

function MultiEntityView({ entities, book, reference }: MultiEntityViewProps) {
  const location = useLocation();
  const queryClient = useQueryClient();
  const toast = useToast();
  const built = useBuiltPaths();
  const label = periodLabel(reference.period);
  const ctxSearch = contextSearch(location.search, CONTEXT);
  const { start_date: startDate, end_date: endDate } = reference.period;

  const byCode = useMemo(
    () => new Map(entities.map((entity) => [entity.code, entity])),
    [entities],
  );
  // The runs of the book that have not ended: their entities are chosen until the reader chooses.
  const activeKey = useMemo(
    () => queryKey("close-runs", "tenant", { view: "active", book }),
    [book],
  );
  const active = useQuery({ queryKey: activeKey, queryFn: () => fetchActiveCloseRuns(book) });
  const [picked, setPicked] = useState<readonly string[] | null>(null);
  // The chosen entities in the order shown — code order, the order of their chips — which is the
  // order of the starts.
  const chosen = useMemo(() => {
    const codes = new Set(
      picked ??
        (active.data ?? [])
          .filter((run) => run.period.start_date === startDate && run.period.end_date === endDate)
          .map((run) => run.entity.code),
    );
    return entities.map((entity) => entity.code).filter((code) => codes.has(code));
  }, [picked, active.data, entities, startDate, endDate]);
  const [chooseError, setChooseError] = useState<string | null>(null);
  const [refusals, setRefusals] = useState<Readonly<Record<string, string>>>({});
  const [starting, setStarting] = useState(false);

  const setChosen = (codes: readonly string[]) => {
    for (const code of chosen) {
      if (!codes.includes(code)) {
        announce(t("close.multi.removed", { entity: code }), "polite");
      }
    }
    setChooseError(null);
    setPicked(codes);
  };

  // Each chosen entity closes the period of its own calendar that has the context period's dates.
  const calendars = useQueries({
    queries: chosen.map((code) => {
      const query = { entity: code, book };
      return { queryKey: periodsKey(query), queryFn: () => fetchPeriods(query) };
    }),
  });
  const own = chosen.map((_, index) => {
    const rows = calendars[index]?.data;
    return rows === undefined
      ? undefined
      : (rows.find(
          (item) => item.period.start_date === startDate && item.period.end_date === endDate,
        ) ?? null);
  });
  const runs = useQueries({
    queries: chosen.map((code, index) => {
      const scope = { entity: code, book, period: own[index]?.period.period_key ?? "" };
      return {
        queryKey: closeRunsKey(scope),
        queryFn: () => fetchCloseRuns(scope),
        enabled: own[index] !== undefined && own[index] !== null,
        // SCREENS_B §1.5: read again every 2 s while the entity's run is queued or running.
        refetchInterval: (query: {
          readonly state: { readonly data: readonly CloseRun[] | undefined };
        }) => (isMovingRun(query.state.data?.[0]) ? CLOSE_RUN_POLL_MS : false),
      };
    }),
  });
  const exceptions = useQueries({
    queries: chosen.map((code, index) => {
      const key = own[index]?.period.period_key ?? "";
      return {
        queryKey: openExceptionCountKey(code, key),
        queryFn: () => fetchOpenExceptionCount(code, key),
        enabled: own[index] !== undefined && own[index] !== null,
      };
    }),
  });

  const rows: readonly EntityRow[] = chosen.flatMap((code, index) => {
    const entity = byCode.get(code);
    const period = own[index];
    if (entity === undefined || period === undefined) {
      return [];
    }
    const run = runs[index]?.data?.[0] ?? null;
    const refusal =
      period === null
        ? t("close.multi.noMatchingPeriod", {
            entity: code,
            from: formatDate(startDate),
            to: formatDate(endDate),
          })
        : (refusals[code] ?? null);
    // SCREENS_B §1.5: a row is an entity with a close run of the period or an answer of this page.
    if (run === null && refusal === null) {
      return [];
    }
    return [{ entity, period, run, refusal, exceptions: exceptions[index]?.data ?? null }];
  });

  // One press sends one start per entity. Each start keeps its own key until it is answered (DG-FE-05
  // rev 1.156): the hook remembers the key of its last body alone, so the start of an entity that got
  // no answer would lose its key to the next entity's.
  const keys = useCommandKeys();
  const startAll = async () => {
    if (chosen.length === 0) {
      setChooseError(t("close.multi.chooseOne"));
      document.getElementById(fieldId(FIELD_NAME))?.focus();
      return;
    }
    setStarting(true);
    const answers: Record<string, string> = {};
    // One independent start per entity, in the order chosen; each row reads its own answer.
    for (const code of chosen) {
      const query = { entity: code, book };
      let calendar: readonly Period[];
      try {
        calendar = await queryClient.fetchQuery({
          queryKey: periodsKey(query),
          queryFn: () => fetchPeriods(query),
        });
      } catch {
        answers[code] = t("close.multi.network");
        continue;
      }
      const period = calendar.find(
        (item) => item.period.start_date === startDate && item.period.end_date === endDate,
      );
      if (period === undefined) {
        continue;
      }
      try {
        const outcome = await sendCommand<CloseRun | null>(keys, "POST", CLOSE_RUNS_PATH, {
          entity_code: code,
          book: period.book,
          period_key: period.period.period_key,
        } satisfies CloseRunCreateIn);
        if (!outcome.ok) {
          answers[code] = refusalText(outcome.problem);
        } else if (outcome.response.status === 200 && outcome.data !== null) {
          // 200: the entity's run for the period has not ended (04 §16.8); it was not started again.
          toast.show({
            tone: "neutral",
            message: t("close.multi.alreadyRunning", { entity: code }),
          });
        }
      } catch {
        // No answer: the start keeps its key for the next press.
        answers[code] = t("close.multi.network");
      }
    }
    setRefusals(answers);
    setStarting(false);
    await Promise.all(
      [EVERY_CLOSE_RUN, EVERY_PERIOD].map((key) =>
        queryClient.invalidateQueries({ queryKey: key }),
      ),
    );
  };

  // The grid shows the rows this page derives; it reads them again whenever one changes.
  const latest = useRef(rows);
  const gridKey = useMemo(
    () =>
      queryKey("close-runs", "tenant", {
        view: "multi-entity",
        book,
        from: startDate,
        to: endDate,
      }),
    [book, startDate, endDate],
  );
  const signature = JSON.stringify(
    rows.map((row) => [
      row.entity.code,
      row.period?.state ?? null,
      row.run?.id ?? null,
      row.run?.status ?? null,
      row.run?.current_step_code ?? null,
      row.refusal,
      row.exceptions,
    ]),
  );
  useEffect(() => {
    latest.current = rows;
    void queryClient.invalidateQueries({ queryKey: gridKey });
    // `signature` stands for `rows`: the grid is read again when a row's content changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, gridKey, queryClient]);
  const source: GridSource<EntityRow> = useMemo(
    () => ({
      queryKey: gridKey,
      fetchPage: () =>
        Promise.resolve({
          items: latest.current,
          nextCursor: null,
          total: { count: latest.current.length, capped: false },
        }),
    }),
    [gridKey],
  );

  const columns = useMemo(() => multiEntityColumns(built), [built]);

  return (
    <div data-testid="SF-05-page" className="flex flex-col gap-4">
      <RecordHeader
        title={t("close.multi.title", { period: label, book: bookLabel(book) })}
        breadcrumb={[{ label: t("close.cockpit.documentTitle"), to: `/close${ctxSearch}` }]}
      />
      {/* SCREENS_B §1.5 wireframe: the command sits on the selector's row and the note under both.
          The row is aligned at its top, so the offset of the button is the field's label and gap;
          the note or an error under the control does not move it. */}
      <div className="flex flex-wrap items-start gap-3">
        <div data-testid="SF-05-multi-entity-entities" className="min-w-0 flex-1">
          <Field
            name={FIELD_NAME}
            label={t("close.multi.entities")}
            help={t("close.multi.note")}
            error={chooseError}
          >
            {(control) => (
              <MultiSelect<string>
                control={control}
                options={entities.map((entity) => ({
                  value: entity.code,
                  label: `${entity.code} · ${entity.name}`,
                }))}
                values={chosen}
                invalid={chooseError !== null}
                onChange={setChosen}
              />
            )}
          </Field>
        </div>
        <div className="mt-6">
          <Button variant="primary" loading={starting} onClick={() => void startAll()}>
            {t("close.multi.start")}
          </Button>
        </div>
      </div>
      <div className="flex min-h-48 flex-col">
        <DataGrid<EntityRow>
          name="multi-entity"
          title={t("close.multi.runs")}
          errorTitle={t("close.multi.loadError")}
          countLabel={(count, formatted) => t("close.multi.count", { count, formatted })}
          columns={columns}
          source={source}
          rowKey={(row) => row.entity.code}
          rowLabel={(row) => row.entity.code}
          rowTestKey={(row) => row.entity.code}
          rowHref={(row) => {
            const period = row.period;
            return period === null
              ? `${location.pathname}${location.search}`
              : `${closeRunRoute({ entity: row.entity.code, book: period.book, period: period.period.period_key })}?entity=${encodeURIComponent(row.entity.code)}&period=${encodeURIComponent(period.period.period_key)}&book=${encodeURIComponent(period.book)}`;
          }}
          testIdPrefix="SF-05"
          emptyState={
            <EmptyState
              title={t("close.multi.emptyTitle")}
              description={t("close.multi.emptyDescription", { period: label })}
              headingLevel={2}
            />
          }
        />
      </div>
    </div>
  );
}

/** The copy of a refused start: the problem's own sentence, else its title. */
function refusalText(problem: ApiProblem): string {
  return problem.detail ?? problem.title;
}

/**
 * SCREENS_B §1.5 "Grid columns". A link is rendered where its route is built (XR-14). The six columns
 * take 1,128 px of the 1,158 px the grid has at 1440 px beside the open rail.
 */
export function multiEntityColumns(built: ReadonlySet<string>): readonly GridColumn<EntityRow>[] {
  const context = (row: EntityRow) =>
    row.period === null
      ? ""
      : `?entity=${encodeURIComponent(row.entity.code)}&period=${encodeURIComponent(row.period.period.period_key)}&book=${encodeURIComponent(row.period.book)}`;
  const runRoute = (row: EntityRow) =>
    row.period === null || !built.has(CLOSE_RUN_ROUTE)
      ? null
      : `${closeRunRoute({ entity: row.entity.code, book: row.period.book, period: row.period.period.period_key })}${context(row)}`;
  return [
    {
      id: "entity",
      header: t("close.multi.column.entity"),
      kind: "identifier",
      value: (row) => row.entity.code,
      render: (row) => <Mono>{row.entity.code}</Mono>,
      width: 120,
    },
    {
      id: "period",
      header: t("close.multi.column.period"),
      kind: "text",
      value: (row) => (row.period === null ? null : periodLabel(row.period.period)),
      render: (row) => {
        if (row.period === null) {
          return <NoValue />;
        }
        const chip = chipFor("E-04", row.period.state);
        return (
          <span className="flex min-w-0 items-center gap-2">
            <span className="truncate">{periodLabel(row.period.period)}</span>
            {chip === null ? null : <StatusChip status={chip.status} />}
          </span>
        );
      },
      width: 248,
    },
    {
      id: "run",
      header: t("close.multi.column.run"),
      // The entity is the row's header; a second identifier column would be one too.
      kind: "text",
      value: (row) => row.run?.close_run_no ?? null,
      render: (row) => {
        if (row.run === null) {
          return <NoValue />;
        }
        const to = runRoute(row);
        return to === null ? (
          <Mono>{row.run.close_run_no}</Mono>
        ) : (
          <Link
            to={to}
            tabIndex={-1}
            className="truncate font-mono text-mono-sm text-accent-fg hover:underline"
          >
            {row.run.close_run_no}
          </Link>
        );
      },
      width: 136,
    },
    {
      id: "status",
      header: t("close.multi.column.status"),
      kind: "status",
      value: (row) => row.refusal ?? row.run?.status ?? null,
      render: (row) => {
        if (row.refusal !== null) {
          return (
            <span className="truncate text-negative-fg" title={row.refusal}>
              {row.refusal}
            </span>
          );
        }
        if (row.run === null) {
          return <NoValue />;
        }
        const chip = chipFor("E-62", row.run.status);
        const position = stepNumber(row.run, row.run.current_step_code);
        const caption =
          position === null || row.run.status === "SUCCEEDED" || row.run.status === "CANCELLED"
            ? null
            : t("close.multi.step", {
                step: formatNumber(position, { kind: "count" }),
                total: formatNumber(row.run.steps.length, { kind: "count" }),
              });
        return chip === null ? <NoValue /> : <StatusChip status={chip.status} caption={caption} />;
      },
      width: 336,
    },
    {
      id: "exceptions",
      header: t("close.multi.column.exceptions"),
      kind: "number",
      numberKind: "count",
      value: (row) => (row.exceptions === null ? null : String(row.exceptions)),
      render: (row) => {
        if (row.exceptions === null || row.period === null) {
          return <NoValue />;
        }
        const count = formatNumber(row.exceptions, { kind: "count" });
        return built.has(EXCEPTION_QUEUE_ROUTE) ? (
          <Link
            to={`${EXCEPTION_QUEUE_ROUTE}?entity=${encodeURIComponent(row.entity.code)}&period=${encodeURIComponent(row.period.period.period_key)}&f.status=in:OPEN,IN_PROGRESS`}
            tabIndex={-1}
            aria-label={t("close.multi.exceptionsOf", {
              count: row.exceptions,
              formatted: count,
              entity: row.entity.code,
            })}
            className="num text-accent-fg hover:underline"
          >
            {count}
          </Link>
        ) : (
          <span className="num">{count}</span>
        );
      },
      // The header "Exceptions" with its column options needs more than the 120 px of "Entity".
      width: 136,
    },
    {
      id: "cockpit",
      header: t("close.multi.column.cockpit"),
      kind: "text",
      value: (row) => (row.period === null ? null : t("close.multi.openCockpit")),
      render: (row) =>
        row.period === null || !built.has(COCKPIT_ROUTE) ? (
          <NoValue />
        ) : (
          <Link
            to={`${cockpitRoute(row.entity.code, row.period.book, row.period.period.period_key)}${context(row)}`}
            tabIndex={-1}
            aria-label={t("close.multi.openCockpitOf", { entity: row.entity.code })}
            className="text-accent-fg hover:underline"
          >
            {t("close.multi.openCockpit")}
          </Link>
        ),
      width: 152,
    },
  ];
}
