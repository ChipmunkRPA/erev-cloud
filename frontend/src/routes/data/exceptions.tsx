// SF-11 Exception queue and SF-11:item (SCREENS §13.1 to §13.9; §0.3 SCR-IA-02; §0.4 RT-46, RT-47; §0.5
// SCR-URL-08 to SCR-URL-10; §0.6 SCR-PERM-01 to SCR-PERM-05; §0.7 SCR-ST-01 to SCR-ST-07; §0.8 E-43, E-44;
// DESIGN_SYSTEM DS-CMP-06, DS-CMP-08, DS-CMP-09, DS-CMP-11, DS-CMP-13, DS-CMP-19, DS-CMP-23, DS-CMP-24;
// 04 API-R-44, T-IMP-05, §16.14; PRD BR-DAT-04, SM-06, ACT-17; BUILD_SPEC DIN-17). The Data frame with
// `h1` "Exceptions" and "<n> open", the FilterBar (Status defaults to `in:OPEN,IN_PROGRESS` on entry),
// and the DS-CMP-08 queue: severity chip at the end of line 1, then code · source · key · occurrences ·
// created date. Selecting an item opens RT-47 inside the queue and keeps the queue's search string. The
// detail pane holds the compact header, the message, suggestion, location, occurrences, the owner, the
// actions of `available_actions` (Reprocess, Mark resolved, Dismiss exception, Request waiver), the
// resolution and the source payload; without `DISMISS` the blocked-dismissal line describes the actions.
// [J] The context entity does not filter the queue: import findings carry no entity until their upload
// names one (L6-4-Q-24); only an Entity chip sends `entity`.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { JobProgress } from "../../components/feedback/JobProgress";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import {
  FILTER_PREFIX,
  type Filter,
  type FilterField,
  filterParam,
  parseFilters,
  withFilters,
} from "../../components/filter-bar/filters";
import { Combobox } from "../../components/form/Combobox";
import { Field } from "../../components/form/Field";
import type { ListOption } from "../../components/form/Listbox";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { MasterDetail, type MasterItem } from "../../components/record/MasterDetail";
import { RecordHeader } from "../../components/record/RecordHeader";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { Menu } from "../../components/ui/Menu";
import { Modal } from "../../components/ui/Modal";
import { chipFor, OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import { type EntityOf, useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { isTerminal } from "../../lib/api/jobs";
import { fetchListPage } from "../../lib/api/lists";
import { ApiProblem, fieldErrorsOf } from "../../lib/api/problems";
import { requestRoute } from "../../lib/api/queries/approvals";
import {
  DEFAULT_STATUSES,
  dismissBlocked,
  EVERY_EXCEPTION,
  EXCEPTION_READ_PERMISSION,
  EXCEPTION_RESOLVE_PERMISSION,
  EXCEPTION_SEVERITIES,
  EXCEPTION_SORTS,
  EXCEPTION_SOURCES,
  EXCEPTION_STATUSES,
  type ExceptionAction,
  type ExceptionCommand,
  exceptionCommandPath,
  type ExceptionItem,
  exceptionKey,
  type ExceptionListQuery,
  exceptionRoute,
  exceptionsKey,
  type ExceptionSort,
  fetchActiveMembers,
  fetchException,
  fetchExceptions,
  fetchOpenCount,
  type Member,
  membersKey,
  openCountKey,
  OWNER_ME,
  sortOf,
  sortParam,
  testKey,
  USER_MANAGE_PERMISSION,
  type WaiverRequested,
} from "../../lib/api/queries/exceptions";
import {
  fetchImport,
  fetchImportsPage,
  findImportRow,
  type ImportItem,
  importKey,
  importName,
  IMPORTS_ROUTE,
  importsKey,
  importStepRoute,
  stepOfStatus,
} from "../../lib/api/queries/imports";
import { type Me, useMe } from "../../lib/api/queries/me";
import {
  type Entity,
  entitiesKey,
  fetchActiveEntities,
  fetchPeriods,
  type Period,
  periodLabel,
  periodsKey,
  rowIfMatch,
  STRUCTURE_READ_PERMISSION,
} from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import { formatDate, formatNumber, formatTimestamp, timestampDate } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { useLiveSearch } from "../../lib/url/live-search";
import { decodeValue, rawParams, withParams } from "../../lib/url/params";
import { useBuiltPaths } from "../settings/index";
import { DataAccessLimited, DataPageHeader } from "./imports";

/** SCREENS SCR-TID-02 prefix of the queue. */
const SF = "SF-11";
/** SCREENS RT-10 SF-03, the target of a Contract location. */
const CONTRACT_ROUTE = "/contracts/:contractId/obligations";
const OBLIGATION_ROUTE = "/contracts/:contractId/obligations/:obligationId";
/** SCREENS RT-57 SF-12:request, the target of a waiver request link. */
const REQUEST_ROUTE = "/approvals/requests/:requestId";
/** The context parameters links carry to the records they open (SCR-URL-01 to SCR-URL-03). */
const CONTEXT_PARAMS = ["entity", "period", "book"] as const;
const SORT_PARAM = "sort";
/**
 * SCREENS §13.4 rev 1.37: the id of one period (API-S-Period `id`), written by BLK-02 of the close
 * cockpit and by the close row of Home. The list is then the items that hold that period's lock.
 */
const BLOCKING_PARAM = "blocking";
const STATUS_FIELD = "status";
/** 8 characters of an id where a record has no business identifier in the item (DS-FMT-23). */
const ID_PREFIX = 8;

/** E-42 labels (SCREENS §13.4). */
export function sourceLabel(source: ExceptionItem["source"]): string {
  return t(`data.exceptions.source.${source}`);
}

function idText(id: string): string {
  return t("data.exceptions.location.id", { id: id.slice(0, ID_PREFIX) });
}

function severityWord(severity: ExceptionItem["severity"]) {
  return chipFor("E-43", severity)?.status ?? "Info";
}

function statusWord(status: ExceptionItem["status"]) {
  return chipFor("E-44", status)?.status ?? "Open";
}

/** The raw `f.<field>` values of a URL chip, read before the field's options have loaded. */
function urlChipValues(search: string, field: string): readonly string[] {
  const param = rawParams(search).find((item) => item.name === `${FILTER_PREFIX}${field}`);
  const colon = param?.value.indexOf(":") ?? -1;
  if (param === undefined || colon < 0) {
    return [];
  }
  return param.value
    .slice(colon + 1)
    .split(",")
    .map((value) => decodeValue(value));
}

function hasStatusChip(search: string): boolean {
  return rawParams(search).some((param) => param.name === `${FILTER_PREFIX}${STATUS_FIELD}`);
}

/** SCREENS §13.3: the Status chip `in:OPEN,IN_PROGRESS`, added to a search string without one. */
export function withDefaultStatus(search: string): string {
  const chip: Filter = { field: STATUS_FIELD, operator: "in", values: DEFAULT_STATUSES };
  return withParams(search, { [`${FILTER_PREFIX}${STATUS_FIELD}`]: filterParam(chip) });
}

export interface FilterOptions {
  readonly search: string;
  readonly entities?: readonly Entity[] | undefined;
  readonly periods?: readonly Period[] | undefined;
  readonly members?: readonly Member[] | undefined;
  readonly contracts?: readonly ListOption<string>[] | undefined;
  readonly imports?: readonly ImportItem[] | undefined;
  /** The codes of the loaded items (L6-4-Q-25). */
  readonly codes?: readonly string[] | undefined;
}

/** SCREENS §13.3 FilterBar fields, in column order. */
export function exceptionFilterFields({
  search,
  entities,
  periods,
  members,
  contracts,
  imports,
  codes,
}: FilterOptions): readonly FilterField[] {
  const pending = (field: string) =>
    urlChipValues(search, field).map((value) => ({ value, label: value }));
  const merged = (field: string, options: readonly ListOption<string>[]) => {
    const known = new Set(options.map((option) => option.value));
    return [...options, ...pending(field).filter((option) => !known.has(option.value))];
  };
  return [
    {
      name: STATUS_FIELD,
      label: t("data.exceptions.filter.status"),
      kind: "enum",
      operators: ["is", "in"],
      options: EXCEPTION_STATUSES.map((status) => ({ value: status, label: statusWord(status) })),
    },
    {
      name: "severity",
      label: t("data.exceptions.filter.severity"),
      kind: "enum",
      operators: ["is", "in"],
      options: EXCEPTION_SEVERITIES.map((severity) => ({
        value: severity,
        label: severityWord(severity),
      })),
    },
    {
      name: "source",
      label: t("data.exceptions.filter.source"),
      kind: "enum",
      operators: ["is", "in"],
      options: EXCEPTION_SOURCES.map((source) => ({ value: source, label: sourceLabel(source) })),
    },
    {
      name: "code",
      label: t("data.exceptions.filter.code"),
      kind: "user",
      operators: ["is"],
      options: merged(
        "code",
        [...new Set(codes ?? [])].sort().map((code) => ({ value: code, label: code })),
      ),
    },
    {
      name: "entity",
      label: t("data.exceptions.filter.entity"),
      kind: "enum",
      operators: ["is", "in"],
      options:
        entities === undefined
          ? pending("entity")
          : merged(
              "entity",
              entities.map((entity) => ({ value: entity.code, label: entity.code })),
            ),
      optionsLoading: entities === undefined,
    },
    {
      name: "owner",
      label: t("data.exceptions.filter.owner"),
      kind: "user",
      operators: ["is"],
      options: merged("owner", [
        { value: OWNER_ME, label: t("data.exceptions.filter.me") },
        ...(members ?? []).map((member) => ({ value: member.id, label: member.display_name })),
      ]),
    },
    {
      name: "contract",
      label: t("data.exceptions.filter.contract"),
      kind: "user",
      operators: ["is"],
      options: merged("contract", contracts ?? []),
    },
    {
      name: "period",
      label: t("data.exceptions.filter.period"),
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
      name: "import",
      label: t("data.exceptions.filter.import"),
      kind: "user",
      operators: ["is"],
      options: merged(
        "import",
        (imports ?? []).map((item) => ({ value: item.id, label: importName(item) })),
      ),
    },
  ];
}

/**
 * The API query of the URL: quick search, chips, the sort and — passed through as it stands — the
 * period whose lock the listed items hold (SCREENS §13.4, rev 1.37 for `blocking`).
 */
export function exceptionQuery(search: string, fields: readonly FilterField[]): ExceptionListQuery {
  const parsed = parseFilters(search, fields);
  const chip = (name: string) => parsed.filters.find((filter) => filter.field === name)?.values;
  const params = rawParams(search);
  const sort = params.find((param) => param.name === SORT_PARAM);
  const blocking = params.find((param) => param.name === BLOCKING_PARAM);
  return {
    q: parsed.query === "" ? null : parsed.query,
    status: chip(STATUS_FIELD) ?? [],
    severity: chip("severity") ?? [],
    source: chip("source") ?? [],
    code: chip("code") ?? [],
    entity: chip("entity") ?? [],
    owner: chip("owner")?.[0] ?? null,
    contract: chip("contract") ?? [],
    period: chip("period") ?? [],
    importUploadId: chip("import") ?? [],
    blocking: blocking === undefined || blocking.value === "" ? null : decodeValue(blocking.value),
    sort: sortOf(sort === undefined ? null : decodeValue(sort.value)),
  };
}

/** True when the URL holds a quick search or a chip other than the default Status chip. */
export function hasOwnFilters(query: ExceptionListQuery): boolean {
  const defaultStatus =
    query.status.length === DEFAULT_STATUSES.length &&
    DEFAULT_STATUSES.every((status) => query.status.includes(status));
  return (
    query.q !== null ||
    (query.status.length > 0 && !defaultStatus) ||
    [
      query.severity,
      query.source,
      query.code,
      query.entity,
      query.contract,
      query.period,
      query.importUploadId,
    ].some((values) => values.length > 0) ||
    query.owner !== null
  );
}

/** SCREENS §0.7 SCR-ST-05 message: the problem title, then "Reference <request id>." (CPY-05). */
function problemMessage(error: unknown): string {
  if (error instanceof ApiProblem) {
    return error.requestId === null
      ? error.title
      : `${error.title} ${t("data.exceptions.reference", { reference: error.requestId })}`;
  }
  return error instanceof Error ? error.message : String(error);
}

/** Navigation state of a selection made in the list: focus returns to the selected option. */
interface SelectionState {
  readonly focusSelected?: boolean;
}

export function ExceptionQueue() {
  const me = useMe();
  const access = useAccess();
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={t("data.exceptions.title")} shape="rows" count={6} />;
  } else if (!access.holdsAnywhere(EXCEPTION_READ_PERMISSION)) {
    body = <DataAccessLimited area={t("data.access.exceptions")} />;
  } else {
    return <QueuePage me={me.data} />;
  }
  return (
    <div data-testid={`${SF}-page`} className="flex flex-col gap-4">
      <DataPageHeader title={t("data.exceptions.title")} />
      {body}
    </div>
  );
}

function QueuePage({ me }: { readonly me: Me }) {
  const access = useAccess();
  const location = useLocation();
  const navigate = useNavigate();
  const { exceptionId = null } = useParams();
  const built = useBuiltPaths();
  const master = useRef<HTMLDivElement>(null);
  const structure = access.holdsAnywhere(STRUCTURE_READ_PERMISSION);

  // SCREENS §13.3: Status defaults to `in:OPEN,IN_PROGRESS` when the queue opens without a Status
  // chip; the chip is written with history.replace, and removing it later lists every status.
  const [defaultPending, setDefaultPending] = useState(() => !hasStatusChip(location.search));
  useEffect(() => {
    if (!defaultPending) {
      return;
    }
    setDefaultPending(false);
    if (!hasStatusChip(location.search)) {
      void navigate(
        { pathname: location.pathname, search: withDefaultStatus(location.search) },
        { replace: true, state: location.state },
      );
    }
  }, [defaultPending, location.pathname, location.search, location.state, navigate]);
  const search = defaultPending ? withDefaultStatus(location.search) : location.search;
  const context = new URLSearchParams(location.search);
  const contextEntity = context.get("entity");
  const contextBook = context.get("book");

  const entities = useQuery({
    queryKey: entitiesKey(),
    queryFn: fetchActiveEntities,
    enabled: structure,
  });
  const periodQuery = { entity: contextEntity ?? "", book: contextBook ?? "" };
  const periods = useQuery({
    queryKey: periodsKey(periodQuery),
    queryFn: () => fetchPeriods(periodQuery),
    // The periods of one entity: `config.read` is asked for that entity (SCR-PERM-02 (a)).
    enabled:
      contextEntity !== null &&
      contextBook !== null &&
      access.holds(STRUCTURE_READ_PERMISSION, { code: contextEntity }),
  });
  const members = useQuery({
    queryKey: membersKey(),
    queryFn: fetchActiveMembers,
    enabled: access.holdsAnywhere(USER_MANAGE_PERMISSION),
  });
  const contracts = useQuery({
    queryKey: queryKey("contracts", "tenant", { view: "exception-options" }),
    queryFn: async () => {
      const page = await fetchListPage<{ readonly id: string; readonly external_id: string }>(
        "/api/v1/contracts",
        { sort: "contract_no" },
        null,
        { limit: 200, count: false },
      );
      return page.items.map((item) => ({ value: item.id, label: item.external_id }));
    },
  });
  const importQuery = { status: [], templateCode: null, createdFrom: null };
  const imports = useQuery({
    queryKey: importsKey(importQuery),
    queryFn: async () => (await fetchImportsPage(importQuery, null, null)).items,
  });

  // The list is read with the fields of the URL; the codes of the loaded items feed the Code field.
  const baseFields = useMemo(() => exceptionFilterFields({ search }), [search]);
  const query = exceptionQuery(search, baseFields);
  const list = useQuery({ queryKey: exceptionsKey(query), queryFn: () => fetchExceptions(query) });
  const openCount = useQuery({ queryKey: openCountKey(), queryFn: fetchOpenCount });
  const items = list.data?.items;
  const fields = useMemo(
    () =>
      exceptionFilterFields({
        search,
        entities: entities.data,
        periods: periods.data,
        members: members.data,
        contracts: contracts.data,
        imports: imports.data,
        codes: items?.map((item) => item.code),
      }),
    [search, entities.data, periods.data, members.data, contracts.data, imports.data, items],
  );
  const selected = useQuery({
    queryKey: exceptionKey(exceptionId ?? ""),
    queryFn: () => fetchException(exceptionId ?? ""),
    enabled: exceptionId !== null,
    retry: false,
  });

  const selectedIndex =
    items === undefined || exceptionId === null
      ? -1
      : items.findIndex((item) => item.id === exceptionId);
  // AppShell moves focus to the page heading on every route change (DS-A11Y-09); a selection made in
  // the list keeps focus on the selected option instead (DS-CMP-08 selection follows focus).
  const restoreFocus = (location.state as SelectionState | null)?.focusSelected === true;
  useEffect(() => {
    if (!restoreFocus || selectedIndex === -1) {
      return undefined;
    }
    const timer = setTimeout(() => {
      const options = master.current?.querySelectorAll<HTMLElement>("[role='option']") ?? [];
      const option = Array.from(options).find(
        (element, position) =>
          (element.getAttribute("aria-posinset") ?? String(position + 1)) ===
          String(selectedIndex + 1),
      );
      option?.focus();
    }, 0);
    return () => clearTimeout(timer);
  }, [restoreFocus, selectedIndex, location.key]);

  // The four controls below start from the search the router holds (docs/dev-guide.md DG-FE-03 rule
  // (2)), not from the one this render was made for: the page renders an address a moment after the
  // router takes it, and a control pressed in that moment undid the write before it — a row pressed
  // before the default Status chip was rendered opened the item without the chip.
  const liveSearch = useLiveSearch();
  const select = useCallback(
    (id: string) => {
      if (id !== exceptionId) {
        const state: SelectionState = { focusSelected: true };
        void navigate(exceptionRoute(id, liveSearch()), { state });
      }
    },
    [exceptionId, liveSearch, navigate],
  );

  const setSort = (sort: ExceptionSort) => {
    void navigate(
      { search: withParams(liveSearch(), { [SORT_PARAM]: sortParam(sort) }) },
      { replace: true, state: location.state },
    );
  };
  const clearFilters = () => {
    void navigate({ search: withFilters(liveSearch(), "", []) }, { replace: true });
  };
  /** "Show all exceptions": the address without the period whose lock the items hold. */
  const showAll = () => {
    void navigate(
      { search: withParams(liveSearch(), { [BLOCKING_PARAM]: null }) },
      { replace: true, state: location.state },
    );
  };

  const masterItems: MasterItem[] = (items ?? []).map((item) => ({
    id: item.id,
    name: item.title,
    amount: (
      <span className="shrink-0">
        <StatusChip status={severityWord(item.severity)} />
      </span>
    ),
    identifier: item.code,
    chips: <RowDetails item={item} />,
    testId: `${SF}-row-${testKey(item.code)}`,
  }));

  const total = list.data?.total?.count ?? items?.length;
  const toolbar =
    items === undefined ? undefined : (
      <div className="flex w-full flex-wrap items-center gap-2">
        <Menu
          label={t("data.exceptions.sort.label", {
            sort: t(`data.exceptions.sort.${query.sort}`),
          })}
          variant="ghost"
          size="sm"
          items={EXCEPTION_SORTS.map((sort) => ({
            id: sort,
            label: t(`data.exceptions.sort.${sort}`),
            onSelect: () => setSort(sort),
          }))}
        />
        <span className="flex-1" />
        {total === undefined ? null : (
          <span className="num text-body-sm text-fg-2">
            {t("data.exceptions.list.count", {
              count: total,
              formatted: formatNumber(total, { kind: "count" }),
            })}
          </span>
        )}
      </div>
    );

  const errorState = (
    <div data-testid={`${SF}-error-exceptions`}>
      <Banner
        tone="negative"
        title={t("data.exceptions.loadError")}
        headingLevel={2}
        actions={
          <Button variant="link" onClick={() => void list.refetch()}>
            {t("data.exceptions.retry")}
          </Button>
        }
      >
        {problemMessage(list.error)}
      </Banner>
    </div>
  );
  // The list of the items that hold a lock is a cut-down list as one under chips is: empty, it reads
  // "no exceptions match", not "no exceptions". Where no chip cuts it down as well, "Clear filters"
  // would change nothing, so the way out is the banner's own.
  const filtered = hasOwnFilters(query);
  const emptyState =
    filtered || query.blocking !== null ? (
      <EmptyState
        title={t("data.exceptions.noResults")}
        description=""
        action={
          filtered
            ? { label: t("data.exceptions.clearFilters"), onAction: clearFilters }
            : { label: t("data.exceptions.blocking.showAll"), onAction: showAll }
        }
      />
    ) : (
      <div data-testid={`${SF}-empty-exceptions`}>
        <EmptyState
          title={t("data.exceptions.empty.title")}
          description={t("data.exceptions.empty.description")}
          action={
            built.has(IMPORTS_ROUTE)
              ? {
                  label: t("data.exceptions.empty.action"),
                  onAction: () => void navigate(IMPORTS_ROUTE),
                }
              : undefined
          }
        />
      </div>
    );

  let status: "loading" | "error" | "ready" = "ready";
  if (items === undefined) {
    status = list.isError ? "error" : "loading";
  }
  const openTotal = openCount.data ?? undefined;

  return (
    <div data-testid={`${SF}-page`} className="relative flex h-full min-h-0 flex-col gap-3">
      <DataPageHeader
        title={t("data.exceptions.title")}
        count={
          openTotal === undefined
            ? undefined
            : t("data.exceptions.openCount", {
                count: openTotal,
                formatted: formatNumber(openTotal, { kind: "count" }),
              })
        }
      />
      <FilterBar
        fields={fields}
        searchLabel={t("data.exceptions.search")}
        resultCount={total}
        resultLabel={(value) =>
          t("data.exceptions.list.count", {
            count: value,
            formatted: formatNumber(value, { kind: "count" }),
          })
        }
        testId={`${SF}-filter-bar`}
      />
      {query.blocking === null ? null : (
        // A list cut down by a parameter no control shows would read as "there are only these".
        <div data-testid={`${SF}-banner-blocking`}>
          <Banner
            tone="info"
            announce="static"
            headingLevel={2}
            title={t("data.exceptions.blocking.title")}
            actions={
              <Button variant="link" onClick={showAll}>
                {t("data.exceptions.blocking.showAll")}
              </Button>
            }
          />
        </div>
      )}
      <div
        ref={master}
        data-testid={`${SF}-grid-exceptions`}
        className="min-h-0 flex-1 overflow-hidden rounded-md border border-hairline bg-surface"
      >
        <MasterDetail
          type="exceptions"
          listLabel={t("data.exceptions.list.label")}
          items={masterItems}
          selectedId={exceptionId}
          onSelect={select}
          toolbar={toolbar}
          status={status}
          errorState={errorState}
          emptyState={emptyState}
          detailLabel={
            selected.data === undefined
              ? t("data.exceptions.detail.regionPending")
              : t("data.exceptions.detail.region", { title: selected.data.title })
          }
          noSelection={t("data.exceptions.noSelection")}
          detailTestId={`${SF}-pane-exception`}
        >
          {exceptionId === null ? null : (
            <ExceptionDetail key={exceptionId} exceptionId={exceptionId} me={me} />
          )}
        </MasterDetail>
      </div>
    </div>
  );
}

/** SCREENS §13.4 master row line 2 after the code. One truncating span, so the row keeps its two
 * lines (DS-CMP-08) in the master pane width; the whole line is its tooltip. */
function RowDetails({ item }: { readonly item: ExceptionItem }) {
  const parts = [
    sourceLabel(item.source),
    item.business_key ?? item.contract_external_id,
    item.occurrence_count > 1
      ? t("data.exceptions.row.seen", { count: item.occurrence_count })
      : null,
    formatDate(timestampDate(item.created_at)),
  ].filter((part): part is string => typeof part === "string" && part !== "");
  return (
    <span
      title={parts.join(" · ")}
      className="min-w-0 flex-1 basis-0 truncate text-body-sm"
      data-testid={`${SF}-row-details`}
    >
      {parts.map((part, index) => (
        <span key={`${String(index)}:${part}`}>
          <span aria-hidden="true" className={index === 0 ? "pe-2" : "px-2"}>
            ·
          </span>
          {part}
        </span>
      ))}
    </span>
  );
}

interface ExceptionDetailProps {
  readonly exceptionId: string;
  readonly me: Me;
}

function ExceptionDetail({ exceptionId, me }: ExceptionDetailProps) {
  const item = useQuery({
    queryKey: exceptionKey(exceptionId),
    queryFn: () => fetchException(exceptionId),
    retry: false,
  });
  if (item.data === undefined) {
    if (item.isError) {
      const notFound = item.error instanceof ApiProblem && item.error.status === 404;
      return (
        <div className="p-[var(--panel-pad)]">
          {notFound ? (
            <EmptyState
              title={t("data.exceptions.notFound")}
              description={t("errors.notFound.description")}
            />
          ) : (
            <Banner
              tone="negative"
              title={t("data.exceptions.detail.loadError")}
              headingLevel={2}
              actions={
                <Button variant="link" onClick={() => void item.refetch()}>
                  {t("data.exceptions.retry")}
                </Button>
              }
            >
              {problemMessage(item.error)}
            </Banner>
          )}
        </div>
      );
    }
    return (
      <div className="flex flex-col gap-4 p-[var(--panel-pad)]">
        <Skeleton region={t("data.exceptions.detail.regionPending")} shape="text" count={3} />
        <Skeleton region={t("data.exceptions.detail.regionPending")} shape="rows" count={4} />
      </div>
    );
  }
  return <ExceptionReview item={item.data} me={me} />;
}

function useExceptionCommand<T>(item: ExceptionItem, command: ExceptionCommand) {
  return useCommand<T>({
    method: "POST",
    path: exceptionCommandPath(item.id, command),
    ifMatch: rowIfMatch(item.row_version),
    invalidates: [EVERY_EXCEPTION],
  });
}

function has(item: ExceptionItem, action: ExceptionAction): boolean {
  return item.available_actions.includes(action);
}

/**
 * The entity a command on an exception is asked for (SCREENS §0.6 SCR-PERM-02): its own where it has
 * one; an exception without one (raised on an import that names no entity) asks any entity.
 */
function entityOf(item: ExceptionItem): EntityOf | null {
  return item.entity_id === null ? null : { id: item.entity_id };
}

interface ExceptionReviewProps {
  readonly item: ExceptionItem;
  readonly me: Me;
}

function ExceptionReview({ item, me }: ExceptionReviewProps) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const built = useBuiltPaths();
  const blockedId = useId();
  const access = useAccess();
  const resolver = access.holds(EXCEPTION_RESOLVE_PERMISSION, entityOf(item));
  const reprocess = useExceptionCommand<unknown>(item, "reprocess");
  const [dialog, setDialog] = useState<"resolve" | "waiver" | "dismiss" | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [finding, setFinding] = useState<string | null>(null);
  const [waiver, setWaiver] = useState<WaiverRequested | null>(null);

  // SCREENS §13.5 Reprocess: once the job ends, the item reads again; resolved items toast, and an
  // item raised again shows its message in a negative banner. Each finished job is handled once.
  const job = reprocess.job;
  const handledJob = useRef<string | null>(null);
  useEffect(() => {
    if (job === undefined || !isTerminal(job) || handledJob.current === job.id) {
      return;
    }
    handledJob.current = job.id;
    if (job.state === "FAILED" || job.state === "CANCELLED") {
      return;
    }
    void queryClient
      .fetchQuery({ queryKey: exceptionKey(item.id), queryFn: () => fetchException(item.id) })
      .then((next) => {
        if (next.status === "RESOLVED") {
          toast.show({ tone: "positive", message: t("data.exceptions.reprocess.done") });
        } else {
          setFinding(next.message);
        }
      });
  }, [job, item.id, queryClient, toast]);

  const commandProblem = (outcome: { readonly kind: string; readonly problem?: ApiProblem }) => {
    if (outcome.kind === "network-error") {
      setProblem(t("data.exceptions.problem.network"));
      return;
    }
    const failure = outcome.problem;
    if (failure === undefined) {
      return;
    }
    if (failure.slug === "forbidden") {
      toast.show({ tone: "negative", message: t("data.exceptions.problem.forbidden") });
      return;
    }
    setProblem(failure.detail ?? failure.title);
  };

  const startReprocess = async () => {
    setProblem(null);
    setFinding(null);
    const outcome = await reprocess.submit();
    if (outcome.kind === "failed" || outcome.kind === "network-error") {
      commandProblem(outcome);
    }
  };

  const actions: ReactNode[] = [];
  if (resolver) {
    if (has(item, "REPROCESS")) {
      actions.push(
        <Button
          key="reprocess"
          variant={item.disposition === "remediable" ? "primary" : "secondary"}
          loading={reprocess.pending || (reprocess.jobId !== null && !isTerminal(job))}
          onClick={() => void startReprocess()}
        >
          {t("data.exceptions.reprocess")}
        </Button>,
      );
    }
    if (has(item, "RESOLVE")) {
      actions.push(
        <Button key="resolve" variant="secondary" onClick={() => setDialog("resolve")}>
          {t("data.exceptions.resolve")}
        </Button>,
      );
    }
    if (has(item, "DISMISS")) {
      actions.push(
        <Button key="dismiss" variant="secondary" onClick={() => setDialog("dismiss")}>
          {t("data.exceptions.dismiss")}
        </Button>,
      );
    }
    if (has(item, "REQUEST_WAIVER")) {
      actions.push(
        <Button key="waiver" variant="secondary" onClick={() => setDialog("waiver")}>
          {t("data.exceptions.requestWaiver")}
        </Button>,
      );
    }
  }
  const blocked = dismissBlocked(item);
  // The line points at "Request waiver" only while that command is among the ones offered here.
  const waiverOffered = resolver && has(item, "REQUEST_WAIVER");
  const closed =
    item.status === "RESOLVED" || item.status === "WAIVED" || item.status === "DISMISSED";

  return (
    <article className="flex min-h-full flex-col">
      <RecordHeader
        variant="compact"
        title={item.title}
        identifier={{
          value: item.exception_no,
          copyLabel: t("data.exceptions.copyNumber"),
          copiedMessage: t("data.exceptions.copied", { number: item.exception_no }),
          testId: `${SF}-identifier`,
        }}
        chips={
          <>
            <span className="font-mono text-mono-sm text-fg-2">{item.code}</span>
            <StatusChip status={severityWord(item.severity)} />
            <StatusChip status={statusWord(item.status)} />
            <OutlineChip label={t(`data.exceptions.disposition.${item.disposition}`)} />
          </>
        }
      />
      <div className="flex flex-col gap-4 p-[var(--panel-pad)]">
        {problem === null ? null : (
          <Banner tone="negative" title={problem} headingLevel={3} announce="live" />
        )}
        {reprocess.jobId !== null && job !== undefined && !isTerminal(job) ? (
          <section
            aria-label={t("data.exceptions.reprocess.region")}
            data-testid={`${SF}-job-reprocess`}
            className="rounded-lg border border-default bg-surface p-4"
          >
            <JobProgress
              label={t("data.exceptions.reprocess.job", { code: item.code })}
              job={job}
              unit={t("data.exceptions.reprocess.unit")}
            />
          </section>
        ) : null}
        {job?.state === "FAILED" ? (
          <JobProgress
            label={t("data.exceptions.reprocess.job", { code: item.code })}
            job={job}
            unit={t("data.exceptions.reprocess.unit")}
            onRetry={resolver && has(item, "REPROCESS") ? () => void startReprocess() : undefined}
          />
        ) : null}
        {finding === null ? null : (
          <Banner
            tone="negative"
            title={t("data.exceptions.reprocess.raisedAgain")}
            headingLevel={3}
            announce="live"
          >
            {finding}
          </Banner>
        )}
        {waiver === null ? null : (
          <div data-testid={`${SF}-banner-waiver`}>
            <Banner
              tone="positive"
              title={t("data.exceptions.requestWaiver.done", { request: waiver.request_no })}
              headingLevel={3}
              announce="live"
              actions={
                built.has(REQUEST_ROUTE) ? (
                  <Link
                    to={requestRoute(waiver.approval_request_id)}
                    className="text-body-sm text-accent-fg underline hover:text-accent-fg-hover"
                  >
                    {t("data.exceptions.requestWaiver.viewRequest")}
                  </Link>
                ) : undefined
              }
            />
          </div>
        )}
        <Section title={t("data.exceptions.section.message")}>
          <p className="whitespace-pre-wrap text-body text-fg-1">{item.message}</p>
        </Section>
        {item.suggestion === null ? null : (
          <Section title={t("data.exceptions.section.suggestion")}>
            <p className="whitespace-pre-wrap text-body text-fg-1">{item.suggestion}</p>
          </Section>
        )}
        <Section title={t("data.exceptions.section.location")}>
          <Location item={item} />
        </Section>
        <Section title={t("data.exceptions.section.occurrences")}>
          <p className="text-body-sm text-fg-1">
            {t("data.exceptions.occurrences", {
              count: item.occurrence_count,
              formatted: formatNumber(item.occurrence_count, { kind: "count" }),
              at: formatTimestamp(item.last_seen_at),
            })}
          </p>
        </Section>
        <Owner item={item} me={me} onProblem={commandProblem} />
        {actions.length === 0 && !blocked ? null : (
          <div className="flex flex-col gap-2">
            {actions.length === 0 ? null : (
              <div
                role="group"
                aria-label={t("data.exceptions.section.actions")}
                aria-describedby={blocked ? blockedId : undefined}
                data-testid={`${SF}-actions`}
                className="flex flex-wrap items-center gap-2"
              >
                {actions}
              </div>
            )}
            {blocked ? (
              <p
                id={blockedId}
                data-testid={`${SF}-dismiss-blocked`}
                className="text-body-sm text-fg-2"
              >
                {t(
                  waiverOffered
                    ? "data.exceptions.dismissBlocked"
                    : "data.exceptions.dismissBlockedNoWaiver",
                )}
              </p>
            ) : null}
          </div>
        )}
        {closed ? <Resolution item={item} /> : null}
        {item.source_payload === null ? null : (
          <details className="flex flex-col gap-2">
            <summary className="cursor-pointer rounded-sm text-body-sm font-semibold text-fg-1">
              {t("data.exceptions.section.payload")}
            </summary>
            <pre
              data-volatile=""
              className="mt-2 overflow-x-auto whitespace-pre-wrap rounded-md bg-subtle p-3 font-mono text-mono-sm text-fg-1"
            >
              {JSON.stringify(item.source_payload, null, 2)}
            </pre>
          </details>
        )}
      </div>
      {dialog === "resolve" ? (
        <RemarkModal
          item={item}
          command="resolve"
          onClose={() => setDialog(null)}
          onDone={() => {
            setDialog(null);
            toast.show({
              tone: "positive",
              message: t("data.exceptions.resolve.done", { code: item.code }),
            });
          }}
        />
      ) : null}
      {dialog === "dismiss" ? (
        <RemarkModal
          item={item}
          command="dismiss"
          onClose={() => setDialog(null)}
          onDone={() => {
            setDialog(null);
            toast.show({
              tone: "positive",
              message: t("data.exceptions.dismiss.done", { code: item.code }),
            });
          }}
        />
      ) : null}
      <WaiverDrawer
        item={item}
        open={dialog === "waiver"}
        onClose={() => setDialog(null)}
        onDone={(requested) => {
          setDialog(null);
          setWaiver(requested);
        }}
      />
    </article>
  );
}

function Section({ title, children }: { readonly title: string; readonly children: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="flex flex-col gap-1.5">
      <h3 id={id} className="text-body-sm font-semibold text-fg-1">
        {title}
      </h3>
      {children}
    </section>
  );
}

interface Term {
  readonly label: string;
  readonly value: ReactNode;
}

function Terms({
  terms,
  testId,
}: {
  readonly terms: readonly Term[];
  readonly testId?: string | undefined;
}) {
  return (
    <dl data-testid={testId} className="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-4 gap-y-1">
      {terms.map((term) => (
        <div key={term.label} className="contents">
          <dt className="text-body-sm text-fg-3">{term.label}</dt>
          <dd className="min-w-0 break-words text-body-sm text-fg-1">{term.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** DS-CMP-10 links: a dotted underline in `--border-control`, solid on hover (WCAG 1.4.1). */
const LINK_CLASS =
  "text-fg-1 underline decoration-control decoration-dotted underline-offset-3 hover:decoration-fg-1 hover:decoration-solid";

/** The context parameters of the current URL, for links to records (SCR-URL-01 to SCR-URL-03). */
function contextSearch(search: string): string {
  const kept = rawParams(search).filter((param) =>
    (CONTEXT_PARAMS as readonly string[]).includes(param.name),
  );
  return kept.length === 0 ? "" : `?${kept.map((param) => param.raw).join("&")}`;
}

/** SCREENS §13.5 Location. [J] Records without a business identifier in the item show their id prefix
 * (L6-4-Q-26); run routes are not built, so runs show text (XR-14). */
function Location({ item }: { readonly item: ExceptionItem }) {
  const location = useLocation();
  const built = useBuiltPaths();
  const access = useAccess();
  const structure = access.holdsAnywhere(STRUCTURE_READ_PERMISSION);
  const context = contextSearch(location.search);
  const upload = useQuery({
    queryKey: importKey(item.import_upload_id ?? ""),
    queryFn: () => fetchImport(item.import_upload_id ?? ""),
    enabled: item.import_upload_id !== null,
    retry: false,
  });
  const row = useQuery({
    queryKey: queryKey("imports", "tenant", {
      id: item.import_upload_id,
      view: "row-of-exception",
      row_id: item.import_row_id,
    }),
    queryFn: () => findImportRow(item.import_upload_id ?? "", item.import_row_id ?? ""),
    enabled: item.import_upload_id !== null && item.import_row_id !== null,
    retry: false,
  });
  const entities = useQuery({
    queryKey: entitiesKey(),
    queryFn: fetchActiveEntities,
    enabled: structure && item.entity_id !== null,
  });
  const params = new URLSearchParams(location.search);
  const periodQuery = { entity: params.get("entity") ?? "", book: params.get("book") ?? "" };
  const periods = useQuery({
    queryKey: periodsKey(periodQuery),
    queryFn: () => fetchPeriods(periodQuery),
    // The periods of the context entity: `config.read` is asked for that entity.
    enabled:
      item.period_id !== null &&
      periodQuery.entity !== "" &&
      access.holds(STRUCTURE_READ_PERMISSION, { code: periodQuery.entity }),
  });

  const terms: Term[] = [
    { label: t("data.exceptions.location.source"), value: sourceLabel(item.source) },
  ];
  if (item.import_upload_id !== null) {
    const name =
      upload.data === undefined ? idText(item.import_upload_id) : importName(upload.data);
    const rowNumber = row.data?.row_number;
    const step = upload.data === undefined ? null : stepOfStatus(upload.data.status);
    let href: string | null = null;
    if (step !== null && built.has("/data/imports/:importId/:step")) {
      const drawer = step === "validate" || step === "committed";
      const search =
        drawer && rowNumber !== undefined
          ? withParams(context, { row: String(rowNumber) })
          : context;
      href = `${importStepRoute(item.import_upload_id, step)}${search}`;
    }
    terms.push({
      label: t("data.exceptions.location.import"),
      value:
        href === null ? (
          name
        ) : (
          <Link to={href} className={LINK_CLASS}>
            {name}
          </Link>
        ),
    });
    if (rowNumber !== undefined) {
      terms.push({
        label: t("data.exceptions.location.row"),
        value: <span className="num">{formatNumber(rowNumber, { kind: "count" })}</span>,
      });
    }
  }
  if (item.field !== null) {
    terms.push({
      label: t("data.exceptions.location.field"),
      value: <span className="font-mono text-mono-sm">{item.field}</span>,
    });
  }
  if (item.contract_id !== null) {
    const label = item.contract_external_id ?? idText(item.contract_id);
    terms.push({
      label: t("data.exceptions.location.contract"),
      value: built.has(CONTRACT_ROUTE) ? (
        <Link to={`/contracts/${item.contract_id}/obligations${context}`} className={LINK_CLASS}>
          <span className="font-mono text-mono-sm">{label}</span>
        </Link>
      ) : (
        <span className="font-mono text-mono-sm">{label}</span>
      ),
    });
  }
  if (item.obligation_id !== null) {
    const label = idText(item.obligation_id);
    terms.push({
      label: t("data.exceptions.location.obligation"),
      value:
        item.contract_id !== null && built.has(OBLIGATION_ROUTE) ? (
          <Link
            to={`/contracts/${item.contract_id}/obligations/${item.obligation_id}${context}`}
            className={LINK_CLASS}
          >
            {label}
          </Link>
        ) : (
          label
        ),
    });
  }
  if (item.entity_id !== null) {
    const entity = entities.data?.find((candidate) => candidate.id === item.entity_id);
    terms.push({
      label: t("data.exceptions.location.entity"),
      value: (
        <span className="font-mono text-mono-sm">{entity?.code ?? idText(item.entity_id)}</span>
      ),
    });
  }
  if (item.period_id !== null) {
    const found = periods.data?.find(
      (candidate) => candidate.id === item.period_id || candidate.period.id === item.period_id,
    );
    terms.push({
      label: t("data.exceptions.location.period"),
      value: found === undefined ? idText(item.period_id) : periodLabel(found.period),
    });
  }
  const runs: readonly (readonly [string, string | null])[] = [
    ["closeRun", item.close_run_id],
    ["journalRun", item.journal_run_id],
    ["syncRun", item.sync_run_id],
  ];
  for (const [key, id] of runs) {
    if (id !== null) {
      terms.push({
        label: t(`data.exceptions.location.${key}`),
        value: <span className="font-mono text-mono-sm">{idText(id)}</span>,
      });
    }
  }
  return <Terms terms={terms} testId={`${SF}-location`} />;
}

/** A member's name: the viewer, a directory member, else "Member <id prefix>" (L6-4-Q-27). */
function memberName(membershipId: string, me: Me, members: readonly Member[] | undefined): string {
  if (membershipId === me.active_membership_id) {
    return me.user.display_name;
  }
  return (
    members?.find((member) => member.id === membershipId)?.display_name ??
    t("data.exceptions.owner.member", { id: membershipId.slice(0, ID_PREFIX) })
  );
}

const UNASSIGNED = "unassigned";

interface OwnerProps {
  readonly item: ExceptionItem;
  readonly me: Me;
  readonly onProblem: (outcome: { readonly kind: string; readonly problem?: ApiProblem }) => void;
}

/** SCREENS §13.5 Owner: changing the owner sends `assign`, which moves OPEN to IN_PROGRESS. */
function Owner({ item, me, onProblem }: OwnerProps) {
  const toast = useToast();
  const access = useAccess();
  const assign = useExceptionCommand<ExceptionItem>(item, "assign");
  const members = useQuery({
    queryKey: membersKey(),
    queryFn: fetchActiveMembers,
    enabled: access.holdsAnywhere(USER_MANAGE_PERMISSION),
  });
  const owner = item.owner_membership_id;
  // `owner` is the API-S-Actor of `owner_membership_id` (04 §16.14, rev 1.139): the owner's name
  // comes with the item, whoever reads it.
  const ownerName = (membershipId: string) =>
    item.owner?.display_name ?? memberName(membershipId, me, members.data);
  const canAssign =
    access.holds(EXCEPTION_RESOLVE_PERMISSION, entityOf(item)) && has(item, "ASSIGN");
  const mine = me.active_membership_id;
  // The member chosen while `assign` is on its way. The field shows that member until the item
  // answers with its new owner, and the item's owner again when the command is refused: it kept
  // showing the refused member.
  const [chosen, setChosen] = useState<string | null>(null);
  useEffect(() => {
    setChosen(null);
  }, [owner]);

  const send = async (membershipId: string) => {
    if (membershipId === owner || membershipId === UNASSIGNED) {
      return;
    }
    setChosen(membershipId);
    const outcome = await assign.submit({ owner_membership_id: membershipId });
    if (outcome.kind !== "succeeded") {
      setChosen(null);
    }
    if (outcome.kind === "succeeded") {
      toast.show({
        tone: "positive",
        message: t("data.exceptions.owner.assigned", {
          name: memberName(membershipId, me, members.data),
        }),
      });
    } else if (outcome.kind === "failed" || outcome.kind === "network-error") {
      onProblem(outcome);
    }
  };

  if (!canAssign) {
    return (
      <Section title={t("data.exceptions.section.owner")}>
        <p className="text-body-sm text-fg-1">
          {owner === null ? t("data.exceptions.owner.unassigned") : ownerName(owner)}
        </p>
      </Section>
    );
  }

  // [J] L6-4-Q-27: API-R-44 has no unassign command, so "Unassigned" is listed only while no one owns
  // the item; the directory of other members needs `user.manage` (API-R-05).
  const options: ListOption<string>[] = [];
  if (owner === null) {
    options.push({ value: UNASSIGNED, label: t("data.exceptions.owner.unassigned") });
  } else if (owner !== mine) {
    options.push({ value: owner, label: ownerName(owner) });
  }
  if (mine !== null) {
    options.push({ value: mine, label: me.user.display_name });
  }
  for (const member of members.data ?? []) {
    if (member.id !== owner && member.id !== mine) {
      options.push({ value: member.id, label: member.display_name });
    }
  }
  return (
    <section
      aria-label={t("data.exceptions.section.owner")}
      className="flex flex-wrap items-end gap-2"
    >
      <div className="w-64">
        <Field name="exceptionOwner" label={t("data.exceptions.owner.label")}>
          {(control) => (
            <Combobox
              control={control}
              options={options}
              value={chosen ?? owner ?? UNASSIGNED}
              onChange={(value) => {
                if (value !== null) {
                  void send(value);
                }
              }}
            />
          )}
        </Field>
      </div>
      {mine === null || owner === mine ? null : (
        <Button variant="secondary" loading={assign.pending} onClick={() => void send(mine)}>
          {t("data.exceptions.assignToMe")}
        </Button>
      )}
    </section>
  );
}

/** SCREENS §13.5 Resolution of a RESOLVED, WAIVED or DISMISSED item. */
function Resolution({ item }: { readonly item: ExceptionItem }) {
  const built = useBuiltPaths();
  // `resolved_by` is API-S-Actor (04 §16.14, rev 1.139): the name comes with the item.
  let resolvedBy: string | null = null;
  if (item.resolved_by !== null) {
    resolvedBy =
      item.resolved_by.kind === "SYSTEM"
        ? t("data.exceptions.resolution.system")
        : item.resolved_by.display_name;
  }
  const terms: Term[] = [];
  if (item.resolution !== null) {
    terms.push({
      label: t("data.exceptions.resolution.text"),
      value: <span className="whitespace-pre-wrap">{item.resolution}</span>,
    });
  }
  if (resolvedBy !== null) {
    terms.push({ label: t("data.exceptions.resolution.by"), value: resolvedBy });
  }
  if (item.resolved_at !== null) {
    terms.push({
      label: t("data.exceptions.resolution.at"),
      value: <span data-volatile="">{formatTimestamp(item.resolved_at)}</span>,
    });
  }
  if (item.waiver_approval_request_id !== null) {
    terms.push({
      label: t("data.exceptions.resolution.waiver"),
      value: built.has(REQUEST_ROUTE) ? (
        <Link to={requestRoute(item.waiver_approval_request_id)} className={LINK_CLASS}>
          {t("data.exceptions.resolution.viewWaiver")}
        </Link>
      ) : (
        idText(item.waiver_approval_request_id)
      ),
    });
  }
  return (
    <Section title={t("data.exceptions.section.resolution")}>
      <Terms terms={terms} testId={`${SF}-resolution`} />
    </Section>
  );
}

interface RemarkModalProps {
  readonly item: ExceptionItem;
  readonly command: "resolve" | "dismiss";
  readonly onClose: () => void;
  readonly onDone: () => void;
}

/** "Mark resolved" (form modal) and "Dismiss exception" (confirmation; Danger), each with a remark. */
function RemarkModal({ item, command, onClose, onDone }: RemarkModalProps) {
  const send = useExceptionCommand<ExceptionItem>(item, command);
  const [text, setText] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const field = command === "resolve" ? "resolution" : "comment";
  const name = command === "resolve" ? "exceptionResolution" : "exceptionDismissReason";

  const submit = async () => {
    setAttempted(true);
    if (reasonError(text) !== null) {
      document.getElementById(`field-${name}`)?.focus();
      return;
    }
    setProblem(null);
    const outcome = await send.submit({ [field]: text.trim() });
    if (outcome.kind === "succeeded") {
      onDone();
    } else if (outcome.kind === "network-error") {
      setProblem(t("data.exceptions.problem.network"));
    } else if (outcome.kind === "failed") {
      const failure = outcome.problem;
      if (fieldErrorsOf(failure)[field] === undefined) {
        setProblem(
          failure.slug === "forbidden"
            ? t("data.exceptions.problem.forbidden")
            : (failure.detail ?? failure.title),
        );
      }
    }
  };

  const dismiss = command === "dismiss";
  return (
    <Modal
      open
      variant={dismiss ? "confirmation" : "form"}
      title={
        dismiss
          ? t("data.exceptions.dismiss.title", { code: item.code })
          : t("data.exceptions.resolve.title", { code: item.code })
      }
      description={dismiss ? t("data.exceptions.dismiss.description") : undefined}
      primaryAction={{
        label: dismiss ? t("data.exceptions.dismiss") : t("data.exceptions.resolve"),
        destructive: dismiss,
        onAction: () => void submit(),
      }}
      submitting={send.pending}
      onClose={onClose}
      testId={dismiss ? `${SF}-dialog-dismiss` : `${SF}-dialog-resolve`}
    >
      <div className="flex flex-col gap-3">
        {problem === null ? null : <Banner tone="negative" title={problem} headingLevel={3} />}
        <ReasonField
          name={name}
          label={dismiss ? t("data.exceptions.dismiss.reason") : t("data.exceptions.resolve.field")}
          value={text}
          onChange={setText}
          showError={attempted}
          error={send.fieldErrors[field]}
        />
      </div>
    </Modal>
  );
}

interface WaiverDrawerProps {
  readonly item: ExceptionItem;
  readonly open: boolean;
  readonly onClose: () => void;
  readonly onDone: (requested: WaiverRequested) => void;
}

/** SCREENS §13.5 Request waiver drawer (SM-06; `EXCEPTION_WAIVER`). [J] L6-4-Q-28: no attachments. */
function WaiverDrawer({ item, open, onClose, onDone }: WaiverDrawerProps) {
  const send = useExceptionCommand<WaiverRequested>(item, "request-waiver");
  const [comment, setComment] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const formId = useId();
  const name = "exceptionWaiverComment";

  useEffect(() => {
    if (!open) {
      setComment("");
      setAttempted(false);
      setProblem(null);
    }
  }, [open]);

  const submit = async () => {
    setAttempted(true);
    if (reasonError(comment) !== null) {
      document.getElementById(`field-${name}`)?.focus();
      return;
    }
    setProblem(null);
    const outcome = await send.submit({ comment: comment.trim() });
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      onDone(outcome.data);
    } else if (outcome.kind === "network-error") {
      setProblem(t("data.exceptions.problem.network"));
    } else if (outcome.kind === "failed" && fieldErrorsOf(outcome.problem).comment === undefined) {
      setProblem(
        outcome.problem.slug === "forbidden"
          ? t("data.exceptions.problem.forbidden")
          : (outcome.problem.detail ?? outcome.problem.title),
      );
    }
  };

  return (
    <Drawer
      open={open}
      title={t("data.exceptions.requestWaiver")}
      subtitle={item.code}
      dirty={comment.trim() !== ""}
      submitting={send.pending}
      banner={
        problem === null ? undefined : <Banner tone="negative" title={problem} headingLevel={3} />
      }
      primaryAction={{ label: t("data.exceptions.requestWaiver"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <ReasonField
          name={name}
          label={t("data.exceptions.requestWaiver.comment")}
          value={comment}
          onChange={setComment}
          showError={attempted}
          error={send.fieldErrors.comment}
        />
      </form>
    </Drawer>
  );
}
