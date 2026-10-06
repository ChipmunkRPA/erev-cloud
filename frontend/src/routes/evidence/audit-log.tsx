// SF-09:audit-log Audit log (SCREENS_B §6.3; §0.3 SB-R-06; §0.4 E-98; §5.6.5 RPT-43, RPT-44; SCREENS
// §0.3 SCR-IA-02; §0.4 RT-37; §0.5 SCR-URL-10, SCR-URL-12, SCR-URL-32 `event`; §0.6 SCR-PERM-01;
// DESIGN_SYSTEM DS-CMP-09, DS-CMP-10, DS-CMP-12 audit header, DS-CMP-13, DS-CMP-16, DS-CMP-19, DS-CMP-22,
// DS-CMP-24, DS-FMT-17, DS-FMT-23; 04 API-R-10, T-PLT-19, T-PLT-23; REQ-PLT-018 to 020; BUILD_SPEC
// RPS-21). The Reports frame with the tab "Audit log"; the verification header (the E-98 chip and
// "Audit chain verified <timestamp> · <n> events" linking to the verification, or the negative banner of a
// failed one) with "Verify chain now", which starts the `AUDIT_CHAIN_VERIFY` job, shows its progress in the
// header and ends with the toast "Audit chain verified: <n> events, last chain value <prefix>."; and the
// DataGrid "Audit events" with the saved-view selector, the filter chips and "Export" (RPT-43).
//
// The list is tenant-wide and read over a stated range: without `f.occurred` the screen reads the last
// 30 days through today (UTC) and says so under the chips; `f.occurred=between:<date>,<date>` replaces it
// (the table is partitioned by month, so an unbounded read probes every partition). `f.object` takes the
// business id of a contract, resolved through the contract search, and lists the trail of that contract:
// every event that names it, whatever its object type, read whole unless `f.occurred` narrows it.
// `f.object_type`, `f.actor`, `f.action` and `f.outcome` reach the API as they are; the options of the
// actor filter are those who acted in the range on screen. API-R-10 has no search, so the screen offers
// none. Selecting a row's sequence (or Enter on the row) opens the docked event drawer, `drawer=event`
// with `event=<chain sequence>` (SCREENS SCR-URL-32 rev 1.20); a sequence the loaded rows do not hold is
// read alone, whatever the filters (SCREENS_B rev 1.57; item AUD-SCREEN-BIND-1).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";

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
import { JobProgress, type JobProgressJob } from "../../components/feedback/JobProgress";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import {
  type Filter,
  type FilterField,
  parseFilters,
  withFilters,
} from "../../components/filter-bar/filters";
import type { ListOption } from "../../components/form/Listbox";
import { NoValue } from "../../components/money/Num";
import { DownloadSimple } from "../../components/icons/registry";
import { Button } from "../../components/ui/Button";
import { cn } from "../../components/ui/cn";
import { StatusChip } from "../../components/ui/StatusChip";
import { Tooltip } from "../../components/ui/Tooltip";
import { announce } from "../../lib/a11y/announce";
import { type Access, accessOf, useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { isTerminal } from "../../lib/api/jobs";
import type { ListPage } from "../../lib/api/lists";
import { ApiProblem, isRefused } from "../../lib/api/problems";
import {
  AUDIT_EVENT_DRAWER,
  AUDIT_EVENT_PARAM,
  AUDIT_LOG_EXPORT_CODE,
  AUDIT_LOG_ROUTE,
  AUDIT_READ_PERMISSION,
  AUDIT_VERIFY_PATH,
  type AuditActor,
  auditActorsKey,
  type AuditEvent,
  auditEventKey,
  type AuditEventQuery,
  auditEventsKey,
  type AuditOutcome,
  contractObjectKey,
  EVERY_AUDIT_EVENT,
  EVERY_VERIFICATION,
  fetchAuditActors,
  fetchAuditEvent,
  fetchAuditEventsPage,
  fetchContractObjectId,
  fetchLatestVerification,
  latestVerificationKey,
  objectRoute,
  VERIFICATION_REPORT_CODE,
  verificationRoute,
} from "../../lib/api/queries/audit";
import { type Me, useMe } from "../../lib/api/queries/me";
import {
  fetchReportDefinition,
  fetchReportRun,
  REPORT_EXPORT_PERMISSION,
  REPORT_ROUTE,
  REPORT_RUN_PERMISSION,
  reportDefinitionKey,
  reportRunKey,
} from "../../lib/api/queries/reports";
import {
  addDays,
  dayStartInstant,
  formatDate,
  formatNumber,
  formatTimestamp,
  parseDateInput,
  utcDateOf,
} from "../../lib/format";
import { hasMessage, t } from "../../lib/i18n/t";
import { withParams } from "../../lib/url/params";
import { ReportsHeader } from "../reports/frame";
import { ExportMenu } from "../reports/viewer/ExportMenu";
import { RunDetailsDrawer } from "../reports/viewer/RunDetailsDrawer";
import { useBuiltPaths } from "../settings/index";
import { AuditAccessLimited, failureTitle, resultWord } from "./chain";
import {
  actorName,
  ActorName,
  actorRoute,
  EventDrawer,
  ObjectLink,
  objectTypeLabel,
  OUTCOME_CHIPS,
  OutcomeChip,
} from "./event-drawer";

/** SCREENS SCR-IA-07 saved-view code. */
export const AUDIT_LOG_SCREEN_CODE = "SF-09:audit-log";
/** The range the log is read over when the link names none. */
export const DEFAULT_RANGE_DAYS = 30;
/** SCREENS_B §6.3, 1280 px: columns hidden by default. */
export const HIDDEN_BY_DEFAULT: readonly string[] = ["actor_roles", "request_id"];
const CONTRACT_READ_PERMISSION = "contract.read";
const DRAWER_PARAM = "drawer";
const EVENT_PARAM = AUDIT_EVENT_PARAM;
const EVENT_DRAWER = AUDIT_EVENT_DRAWER;
const RUN_DETAILS_DRAWER = "run-details";
/**
 * A chain sequence as the link writes it: a positive integer without sign or leading zero, of at most
 * fifteen digits (a number holds it exactly).
 */
const SEQUENCE = /^[1-9]\d{0,14}$/;
const RANGE_PRESETS = [7, 30, 90, 365] as const;
/** E-81 `audit_outcome`, in the order the Outcome filter offers. */
const OUTCOMES = Object.keys(OUTCOME_CHIPS) as readonly AuditOutcome[];
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
/** A resolved business id stays fresh for the life of the page. */
const LOOKUP_STALE_MS = 5 * 60_000;
const NO_ACTORS: readonly ListOption<string>[] = [];
/** DS-FMT-23: the leading characters of a request id. */
const REQUEST_ID_PREFIX = 8;

/** A `YYYY-MM-DD` chip operand as a business date, or null. */
function chipDate(value: string | undefined): string | null {
  const parsed = parseDateInput(value ?? "");
  return parsed.ok ? parsed.value : null;
}

/** The object type literal of what was typed: "Contract hold" reads `contract_hold`. */
export function objectTypeLiteral(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
}

/**
 * SCREENS_B §6.3 (rev 1.57): the options of the Actor filter — who acted in the range on screen
 * (`GET /audit-events/actors`), named as the Actor column names a principal. An actor the link names
 * and the range does not hold stays an option, so that its chip is kept.
 */
export function actorOptions(
  acted: readonly AuditActor[],
  linked: string | null,
): readonly ListOption<string>[] {
  const options = acted
    .flatMap((actor) => (actor.id === null ? [] : [{ value: actor.id, label: actorName(actor) }]))
    .sort((a, b) => a.label.localeCompare(b.label));
  return linked === null || options.some((option) => option.value === linked)
    ? options
    : [...options, { value: linked, label: t("evidence.auditLog.filter.actorUnnamed") }];
}

/** SCREENS_B §6.3 filters, in route order. */
export function auditFilterFields(
  today: string,
  actors: readonly ListOption<string>[],
  access: Access,
  actorsLoading = false,
): readonly FilterField[] {
  const fields: FilterField[] = [
    {
      name: "object_type",
      label: t("evidence.auditLog.filter.objectType"),
      kind: "text",
      operators: ["is"],
    },
    {
      name: "actor",
      label: t("evidence.auditLog.filter.actor"),
      kind: "enum",
      operators: ["is"],
      options: actors,
      optionsLoading: actorsLoading,
    },
    {
      name: "action",
      label: t("evidence.auditLog.filter.action"),
      kind: "text",
      operators: ["is"],
    },
    {
      name: "outcome",
      label: t("evidence.auditLog.filter.outcome"),
      kind: "enum",
      operators: ["is", "in"],
      options: OUTCOMES.map((outcome) => ({ value: outcome, label: OUTCOME_CHIPS[outcome] })),
    },
    {
      name: "occurred",
      label: t("evidence.auditLog.filter.occurred"),
      kind: "date",
      operators: ["between"],
      presets: RANGE_PRESETS.map((days) => ({
        label: t(`evidence.auditLog.filter.last${String(days)}`),
        from: addDays(today, -days),
        to: today,
      })),
    },
  ];
  // The object filter names a contract through the contract search, which needs `contract.read`.
  return access.holdsAnywhere(CONTRACT_READ_PERMISSION)
    ? [
        {
          name: "object",
          label: t("evidence.auditLog.filter.object"),
          kind: "text",
          operators: ["is"],
        },
        ...fields,
      ]
    : fields;
}

export interface AuditLogRead {
  /** The business id the Object chip names, before the contract search resolves it; else null. */
  readonly contractText: string | null;
  /** True when the URL carries an Occurred chip. */
  readonly ranged: boolean;
  /** The first day of the default range, for the caption and the empty state. */
  readonly defaultFrom: string;
  /** The list's query but for the contract's id, which the contract search answers. */
  readonly query: Omit<AuditEventQuery, "contractId">;
}

/**
 * The read of the URL chips (SCREENS_B §6.3 "Range", rev 1.57). The log as a whole is read over the
 * Occurred chip's days or, without one, over the last 30 days through `today`, sent explicitly so
 * that the caption and the read agree. The trail of a contract is read whole: with an Object chip
 * and no Occurred chip the read carries neither `from` nor `to`.
 */
export function auditLogRead(
  search: string,
  fields: readonly FilterField[],
  today: string,
): AuditLogRead {
  const { filters } = parseFilters(search, fields);
  const chip = (name: string): Filter | undefined =>
    filters.find((filter) => filter.field === name);
  const occurred = chip("occurred");
  const contractText = chip("object")?.values[0] ?? null;
  const typeText = chip("object_type")?.values[0] ?? null;
  const defaultFrom = addDays(today, -DEFAULT_RANGE_DAYS);
  const whole = contractText !== null && occurred === undefined;
  const from = chipDate(occurred?.values[0]) ?? defaultFrom;
  const to = chipDate(occurred?.values[1]) ?? today;
  return {
    contractText,
    ranged: occurred !== undefined,
    defaultFrom,
    query: {
      objectTypes: typeText === null ? [] : [objectTypeLiteral(typeText)],
      actorId: chip("actor")?.values[0] ?? null,
      action: chip("action")?.values[0] ?? null,
      outcomes: chip("outcome")?.values ?? [],
      from: whole ? null : dayStartInstant(from),
      // Exclusive: the first instant of the day after the last day of the range.
      to: whole ? null : dayStartInstant(addDays(to, 1)),
    },
  };
}

/** The search of the list with the event drawer open on the event of that chain sequence. */
export function eventSearch(search: string, chainSeq: number): string {
  return withParams(search, {
    [DRAWER_PARAM]: EVENT_DRAWER,
    [EVENT_PARAM]: String(chainSeq),
  });
}

function mono(text: string): ReactNode {
  return <span className="truncate font-mono text-mono-sm text-fg-1">{text}</span>;
}

/** SCREENS_B §6.3 "Action": mono, with the catalogue verb of a known action in the tooltip. */
function ActionCell({ action }: { readonly action: string }) {
  const key = `audit.action.${action}`;
  if (!hasMessage(key)) {
    return mono(action);
  }
  return (
    <Tooltip content={t(key)}>
      {(trigger) => (
        <span
          onMouseEnter={trigger.onMouseEnter}
          onMouseLeave={trigger.onMouseLeave}
          aria-describedby={trigger["aria-describedby"]}
          className="truncate font-mono text-mono-sm text-fg-1"
        >
          {action}
        </span>
      )}
    </Tooltip>
  );
}

export interface AuditColumnOptions {
  /** The current search, which the drawer link keeps. */
  readonly search: string;
  readonly built: ReadonlySet<string>;
  readonly access: Access;
  /** Opens a route: Enter on the Object cell drills as a click on its link does. */
  readonly open: (to: string) => void;
}

/**
 * SCREENS_B §6.3 columns bound to API-R-10 as it stands. "Actor" and "On behalf of" name the principal
 * of an API-S-Actor (rev 1.45); since rev 1.57 "Actor" links to the user screen for a holder of
 * `user.manage` and "Object" shows the business label the event carries. Enter on either cell opens
 * its link, and the event drawer where the cell shows none.
 */
export function auditColumns({
  search,
  built,
  access,
  open,
}: AuditColumnOptions): readonly GridColumn<AuditEvent>[] {
  const route = (event: AuditEvent) =>
    objectRoute(event.object_type, event.object_id, built, access);
  const drawer = (event: AuditEvent) => `${AUDIT_LOG_ROUTE}${eventSearch(search, event.chain_seq)}`;
  return [
    {
      id: "chain_seq",
      header: t("evidence.auditLog.column.sequence"),
      kind: "identifier",
      value: (event) => String(event.chain_seq),
      href: drawer,
      render: (event) => (
        <Link
          to={drawer(event)}
          tabIndex={-1}
          data-event={event.chain_seq}
          className="num font-mono text-mono-sm text-fg-1 underline decoration-control decoration-dotted underline-offset-3 hover:decoration-fg-1 hover:decoration-solid"
        >
          {formatNumber(event.chain_seq, { kind: "count" })}
        </Link>
      ),
      sortKey: "chain_seq",
      // The label with its sort mark and the column menu button.
      width: 128,
    },
    {
      id: "occurred_at",
      header: t("evidence.auditLog.column.occurred"),
      kind: "timestamp",
      value: (event) => event.occurred_at,
      // The instant with seconds stays on one line; it is when the event was recorded (SCR-TID-05).
      render: (event) => (
        <time dateTime={event.occurred_at} data-volatile="" className="num whitespace-nowrap">
          {formatTimestamp(event.occurred_at, { seconds: true })}
        </time>
      ),
      sortKey: "occurred_at",
      width: 232,
    },
    {
      id: "actor",
      header: t("evidence.auditLog.column.actor"),
      kind: "user",
      value: (event) => actorName(event.actor),
      render: (event) => <ActorName event={event} built={built} access={access} inGrid />,
      activate: (event) => open(actorRoute(event, built, access) ?? drawer(event)),
      width: 200,
    },
    {
      id: "actor_roles",
      header: t("evidence.auditLog.column.roles"),
      kind: "text",
      value: (event) => (event.actor_roles.length === 0 ? null : event.actor_roles.join(", ")),
      render: (event) =>
        event.actor_roles.length === 0 ? <NoValue /> : mono(event.actor_roles.join(", ")),
      width: 200,
    },
    {
      id: "action",
      header: t("evidence.auditLog.column.action"),
      kind: "text",
      value: (event) => event.action,
      render: (event) => <ActionCell action={event.action} />,
      width: 288,
    },
    {
      id: "object_type",
      header: t("evidence.auditLog.column.objectType"),
      kind: "text",
      value: (event) => objectTypeLabel(event.object_type),
      width: 208,
    },
    {
      id: "object",
      header: t("evidence.auditLog.column.object"),
      kind: "text",
      value: (event) =>
        event.object_label ?? (route(event) === null ? null : objectTypeLabel(event.object_type)),
      render: (event) => (
        <ObjectLink
          objectType={event.object_type}
          objectId={event.object_id}
          label={event.object_label}
          built={built}
          access={access}
          inGrid
        />
      ),
      activate: (event) => open(route(event) ?? drawer(event)),
      // A composed label ("AVM-US · FY2026-P09 · ASC606") stays whole (DS-FMT-23).
      width: 232,
    },
    {
      id: "outcome",
      header: t("evidence.auditLog.column.outcome"),
      kind: "status",
      value: (event) => event.outcome,
      render: (event) => <OutcomeChip outcome={event.outcome} />,
      width: 128,
    },
    {
      id: "reason_code",
      header: t("evidence.auditLog.column.reason"),
      kind: "text",
      value: (event) => event.reason_code,
      render: (event) => (event.reason_code === null ? <NoValue /> : mono(event.reason_code)),
    },
    {
      id: "mfa_verified",
      header: t("evidence.auditLog.column.mfa"),
      kind: "boolean",
      value: (event) => (event.mfa_verified === null ? null : String(event.mfa_verified)),
    },
    {
      id: "on_behalf_of",
      header: t("evidence.auditLog.column.onBehalfOf"),
      kind: "user",
      value: (event) => (event.on_behalf_of === null ? null : actorName(event.on_behalf_of)),
      width: 200,
    },
    {
      id: "request_id",
      header: t("evidence.auditLog.column.requestId"),
      kind: "text",
      value: (event) => event.request_id,
      render: (event) => (
        <span className="font-mono text-mono-sm text-fg-2" data-volatile="">
          {event.request_id.slice(0, REQUEST_ID_PREFIX)}
        </span>
      ),
      width: 120,
    },
  ];
}

/** The default layout: every column in definition order, the sequence pinned to the start. */
const DEFAULT_COLUMNS: GridColumnState = initialColumnState(
  auditColumns({
    search: "",
    built: new Set(),
    access: accessOf(undefined),
    open: () => undefined,
  }),
  HIDDEN_BY_DEFAULT,
);

interface ObjectLookupPanelProps {
  readonly filterBar: ReactNode;
  readonly children: ReactNode;
}

/**
 * The grid's panel while the object filter is looked up, and when no contract has the id: the title and
 * the chips stay, so the filter can be changed, and no event is read.
 */
function ObjectLookupPanel({ filterBar, children }: ObjectLookupPanelProps) {
  const titleId = useId();
  return (
    <section
      aria-labelledby={titleId}
      className="flex min-h-0 flex-1 flex-col rounded-lg border border-hairline bg-surface"
    >
      <div className="flex min-h-[var(--control-h)] flex-wrap items-center gap-2 px-[var(--panel-pad)] py-2">
        <h2 id={titleId} className="text-title-sm text-fg-1">
          {t("evidence.auditLog.grid")}
        </h2>
      </div>
      <div className="px-[var(--panel-pad)] pb-2">{filterBar}</div>
      <div className="px-[var(--panel-pad)] py-6">{children}</div>
    </section>
  );
}

/** The audit events the query cache holds, so a drawer link opens after a return to the list. */
function cachedEvents(data: readonly (readonly [unknown, unknown])[]): readonly AuditEvent[] {
  return data.flatMap(([, value]) => {
    if (typeof value !== "object" || value === null || !("pages" in value)) {
      return [];
    }
    const { pages } = value as { readonly pages: unknown };
    return Array.isArray(pages)
      ? (pages as readonly ListPage<AuditEvent>[]).flatMap((page) => page.items)
      : [];
  });
}

export function AuditLog() {
  const me = useMe();
  const access = useAccess();
  // SCREENS_B §6.3 SCR-ST-06 (SCREENS §0.6 SCR-PERM-01, -02; ruling R-28): the log is a list of the
  // whole workspace, read with `audit.read` for all entities. A read of it the API refuses all the
  // same renders the state of a member without access in place of the page.
  const [refused, setRefused] = useState(false);
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={t("evidence.auditLog.title")} shape="rows" count={10} />;
  } else if (refused || !access.holdsForAll(AUDIT_READ_PERMISSION)) {
    body = (
      <AuditAccessLimited allEntities={refused || access.holdsAnywhere(AUDIT_READ_PERMISSION)} />
    );
  } else {
    return (
      <AuditLogPage
        me={me.data}
        onRefused={() => {
          setRefused(true);
        }}
      />
    );
  }
  return (
    <div data-testid="SF-09-page" className="flex flex-col">
      <ReportsHeader />
      <div className="px-[var(--gutter)] py-[var(--panel-pad)]">{body}</div>
    </div>
  );
}

/**
 * The verification header (DS-CMP-12 audit variant): the latest verification, "Verification history"
 * (RPT-44) and "Verify chain now" with its job in place (DS-CMP-24, SCR-ST-12).
 */
function ChainHeader() {
  const access = useAccess();
  const navigate = useNavigate();
  const toast = useToast();
  const built = useBuiltPaths();
  const latest = useQuery({ queryKey: latestVerificationKey(), queryFn: fetchLatestVerification });
  const command = useCommand({
    method: "POST",
    path: AUDIT_VERIFY_PATH,
    invalidates: [EVERY_VERIFICATION, EVERY_AUDIT_EVENT],
  });
  const { jobId, job } = command;
  const verification = latest.data ?? null;
  // The verification this page started: its result is announced once, by a toast.
  const announced = useRef<string | null>(null);
  const [startedHere, setStartedHere] = useState<string | null>(null);

  useEffect(() => {
    if (
      verification === null ||
      jobId === null ||
      verification.job_id !== jobId ||
      announced.current === verification.id
    ) {
      return;
    }
    announced.current = verification.id;
    setStartedHere(verification.id);
    const details = {
      label: t("evidence.auditLog.verify.details"),
      onAction: () => void navigate(verificationRoute(verification.id)),
    };
    if (verification.result === "PASS") {
      toast.show({
        tone: "positive",
        message: t("evidence.auditLog.verify.done", {
          events: t("evidence.auditLog.count", {
            count: verification.events_checked,
            formatted: formatNumber(verification.events_checked, { kind: "count" }),
          }),
          value: (verification.digest_last_hmac ?? "").slice(0, REQUEST_ID_PREFIX),
        }),
        action: details,
      });
    } else {
      toast.show({ tone: "negative", message: failureTitle(verification), action: details });
    }
  }, [verification, jobId, toast, navigate]);

  const verify = async () => {
    const outcome = await command.submit();
    if (outcome.kind === "failed") {
      toast.show({ tone: "negative", message: outcome.problem.title });
    } else if (outcome.kind === "network-error") {
      toast.show({ tone: "negative", message: t("evidence.auditLog.verify.notSent") });
    }
  };

  const pendingJob: JobProgressJob | null =
    jobId === null
      ? null
      : (job ?? {
          id: jobId,
          state: "QUEUED",
          progress: { done: 0, total: null },
          started_at: null,
          problem: null,
        });
  const jobShown =
    pendingJob !== null &&
    pendingJob.state !== "SUCCEEDED" &&
    pendingJob.state !== "SUCCEEDED_WITH_EXCEPTIONS";
  const running = command.pending || (jobId !== null && !isTerminal(job));
  const failure =
    !jobShown && verification !== null && verification.result === "FAIL" ? verification : null;

  let status: ReactNode;
  if (jobShown) {
    status = (
      <JobProgress
        label={t("evidence.auditLog.chain.verifying")}
        job={pendingJob}
        unit={t("evidence.auditLog.chain.unit")}
        onRetry={() => void verify()}
      />
    );
  } else if (latest.isError) {
    status = (
      <span className="flex flex-wrap items-center gap-3">
        <span>{t("evidence.auditLog.chain.loadError")}</span>
        <Button variant="link" onClick={() => void latest.refetch()}>
          {t("evidence.auditLog.retry")}
        </Button>
      </span>
    );
  } else if (latest.data === undefined) {
    status = <Skeleton region={t("evidence.auditLog.chain.region")} count={1} />;
  } else if (verification === null) {
    status = <span className="text-fg-2">{t("evidence.auditLog.chain.none")}</span>;
  } else if (verification.result === "FAIL") {
    status = null;
  } else {
    status = (
      <>
        <StatusChip status={resultWord(verification.result)} />
        <Link
          to={verificationRoute(verification.id)}
          // The instant and the count of the run differ from one world to the next (SCR-TID-05).
          data-volatile=""
          className="whitespace-nowrap text-accent-fg hover:text-accent-fg-hover hover:underline"
        >
          {t("evidence.auditLog.chain.verified", {
            timestamp: formatTimestamp(verification.finished_at),
            events: t("evidence.auditLog.count", {
              count: verification.events_checked,
              formatted: formatNumber(verification.events_checked, { kind: "count" }),
            }),
          })}
        </Link>
      </>
    );
  }

  const history =
    built.has(REPORT_ROUTE) && access.holdsAnywhere(REPORT_RUN_PERMISSION) ? (
      <Link
        to={`/reports/${VERIFICATION_REPORT_CODE}`}
        className="text-body-sm text-accent-fg hover:text-accent-fg-hover hover:underline"
      >
        {t("evidence.auditLog.chain.history")}
      </Link>
    ) : null;

  return (
    <section
      aria-label={t("evidence.auditLog.chain.region")}
      data-testid="SF-09-banner-chain"
      className="flex flex-col gap-2"
    >
      {failure === null ? null : (
        <Banner
          tone="negative"
          // DS-CMP-29: an alert only when the failure arrived after load.
          announce={startedHere === failure.id ? "live" : "static"}
          title={failureTitle(failure)}
          actions={
            <Link
              to={verificationRoute(failure.id)}
              className="text-body-sm text-accent-fg hover:text-accent-fg-hover hover:underline"
            >
              {t("evidence.auditLog.chain.details")}
            </Link>
          }
        >
          {t("evidence.auditLog.chain.failedBody")}
        </Banner>
      )}
      {/* Beside the open drawer the row is narrow: the actions move to a second line as a group, and
          the chip and its sentence stay whole. */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div
          role="status"
          className={cn(
            "flex flex-wrap items-center gap-2 text-body-sm text-fg-1",
            jobShown && "min-w-0 flex-1",
          )}
        >
          {jobShown ? <div className="min-w-0 flex-1">{status}</div> : status}
        </div>
        <div className="ms-auto flex items-center gap-4">
          {history}
          <Button variant="secondary" loading={running} onClick={() => void verify()}>
            {t("evidence.auditLog.chain.verify")}
          </Button>
        </div>
      </div>
    </section>
  );
}

function AuditLogPage({
  me,
  onRefused,
}: {
  readonly me: Me;
  /** The API refused the read of the audit events. */
  readonly onRefused: () => void;
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const built = useBuiltPaths();
  const captionId = useId();
  const search = location.search;
  const access = useAccess();
  const params = new URLSearchParams(search);
  const drawer = params.get(DRAWER_PARAM);
  const eventParam = params.get(EVENT_PARAM);
  // An `event` that is not a sequence names no event.
  const eventSeq = eventParam !== null && SEQUENCE.test(eventParam) ? eventParam : null;

  // The rows the list has loaded, by chain sequence: the drawer opens on one without a read.
  const [events, setEvents] = useState<ReadonlyMap<string, AuditEvent>>(
    () =>
      new Map(
        cachedEvents(queryClient.getQueriesData({ queryKey: EVERY_AUDIT_EVENT })).map((event) => [
          String(event.chain_seq),
          event,
        ]),
      ),
  );
  const remember = (items: readonly AuditEvent[]) => {
    setEvents((current) => {
      const next = new Map(current);
      for (const item of items) {
        next.set(String(item.chain_seq), item);
      }
      return next;
    });
  };

  // The range ends today, the current UTC date. It is read from the chips before the actor's names
  // are known: they are the names of that range.
  const today = utcDateOf(Date.now());
  const rangeFields = useMemo(() => auditFilterFields(today, NO_ACTORS, access), [today, access]);
  const range = auditLogRead(search, rangeFields, today).query;

  const actorParam = useMemo(() => {
    const raw = new URLSearchParams(search).get("f.actor") ?? "";
    const value = raw.startsWith("is:") ? raw.slice(3) : "";
    return UUID.test(value) ? value : null;
  }, [search]);
  const acted = useQuery({
    queryKey: auditActorsKey(range.from, range.to),
    queryFn: () => fetchAuditActors(range.from, range.to),
  });
  const actors = useMemo(
    () => actorOptions(acted.data?.items ?? [], actorParam),
    [acted.data, actorParam],
  );

  const fields = useMemo(
    () => auditFilterFields(today, actors, access, acted.isPending),
    [today, actors, access, acted.isPending],
  );
  const { contractText, ranged, defaultFrom, query } = auditLogRead(search, fields, today);

  // SCREENS_B §6.3: the object filter resolves a business id through the contract search. The list
  // waits for the answer, and an id no contract has lists nothing.
  const lookup = useQuery({
    queryKey: contractObjectKey(contractText ?? ""),
    queryFn: () => fetchContractObjectId(contractText ?? ""),
    enabled: contractText !== null,
    staleTime: LOOKUP_STALE_MS,
    retry: false,
  });
  const contractId = contractText === null ? null : (lookup.data ?? null);
  const listed = contractText === null || contractId !== null;

  const source: GridSource<AuditEvent> = {
    queryKey: auditEventsKey({ ...query, contractId }),
    fetchPage: async (cursor, sort) => {
      try {
        const page = await fetchAuditEventsPage({ ...query, contractId }, cursor, sort);
        remember(page.items);
        return page;
      } catch (error) {
        // A refusal is answered as a page without rows, so the query does not ask again; the
        // page gives way to the access-limited state.
        if (isRefused(error)) {
          onRefused();
          return { items: [], nextCursor: null, total: null };
        }
        throw error;
      }
    },
  };

  const [total, setTotal] = useState<number | undefined>(undefined);
  const open = useCallback((to: string) => void navigate(to), [navigate]);
  const columns = useMemo(
    () => auditColumns({ search, built, access, open }),
    [search, built, access, open],
  );
  const [columnState, setColumnState] = useState<GridColumnState>(DEFAULT_COLUMNS);

  const countLabel = (value: number) =>
    t("evidence.auditLog.count", {
      count: value,
      formatted: formatNumber(value, { kind: "count" }),
    });
  const clearFilters = () => {
    void navigate({ search: withFilters(search, "", []) }, { replace: true });
  };

  // The event drawer: the event is one of the loaded rows, or it is read alone by its sequence —
  // at any age and whatever the filters. A value no event answers closes the drawer and says so.
  const wanted = drawer === EVENT_DRAWER ? eventSeq : null;
  const held = wanted === null ? undefined : events.get(wanted);
  const single = useQuery({
    queryKey: auditEventKey(Number(wanted ?? 0)),
    queryFn: () => fetchAuditEvent(Number(wanted ?? 0)),
    enabled: wanted !== null && held === undefined,
    retry: false,
  });
  const selected = wanted === null ? undefined : (held ?? single.data ?? undefined);
  // The drawer is open while its event is shown or read; an answer of no event closes it below.
  const opened = wanted !== null && (selected !== undefined || single.data !== null);
  let readError: string | null = null;
  if (selected === undefined && single.isError) {
    readError = single.error instanceof ApiProblem ? single.error.title : single.error.message;
  }
  const [unknown, setUnknown] = useState(false);
  const missing =
    drawer === EVENT_DRAWER && (eventSeq === null || (held === undefined && single.data === null));
  useEffect(() => {
    if (missing) {
      setUnknown(eventParam !== null);
      void navigate(
        { search: withParams(search, { [DRAWER_PARAM]: null, [EVENT_PARAM]: null }) },
        { replace: true },
      );
    }
  }, [missing, eventParam, search, navigate]);
  const openedSequence = selected?.chain_seq;
  useEffect(() => {
    if (openedSequence !== undefined) {
      // An event is open: the banner of an earlier link that named none has had its say.
      setUnknown(false);
      announce(
        t("evidence.auditLog.drawer.opened", {
          sequence: formatNumber(openedSequence, { kind: "count" }),
        }),
        "polite",
      );
    }
  }, [openedSequence]);
  const closeEvent = () => {
    const closed = eventSeq;
    void navigate(
      { search: withParams(search, { [DRAWER_PARAM]: null, [EVENT_PARAM]: null }) },
      { replace: true },
    );
    // Focus returns to the row the drawer was opened from (DS-CMP-09).
    setTimeout(() => {
      const link =
        closed === null ? null : document.querySelector<HTMLElement>(`[data-event="${closed}"]`);
      link?.closest<HTMLElement>("[data-cell]")?.focus();
    }, 0);
  };

  const [detailsRunId, setDetailsRunId] = useState<string | null>(null);
  const details = useQuery({
    queryKey: reportRunKey(detailsRunId ?? ""),
    queryFn: () => fetchReportRun(detailsRunId ?? ""),
    enabled: drawer === RUN_DETAILS_DRAWER && detailsRunId !== null,
  });
  const openDetails = (runId: string) => {
    setDetailsRunId(runId);
    void navigate(
      {
        search: withParams(search, { [DRAWER_PARAM]: RUN_DETAILS_DRAWER, [EVENT_PARAM]: null }),
      },
      { replace: true },
    );
  };

  // RPT-43 "Export": the range and the filters of the list as the parameters of the run. The report
  // takes neither the trail of a contract nor an outcome: with either chip the export would hold
  // other rows than the list, so it is not offered and says why.
  const canExport =
    access.holdsAnywhere(REPORT_RUN_PERMISSION) && access.holdsAnywhere(REPORT_EXPORT_PERMISSION);
  const definition = useQuery({
    queryKey: reportDefinitionKey(AUDIT_LOG_EXPORT_CODE),
    queryFn: () => fetchReportDefinition(AUDIT_LOG_EXPORT_CODE),
    enabled: canExport,
  });
  const exportable = contractText === null && query.outcomes.length === 0;
  const exportParameters: Record<string, string> = {};
  if (query.from !== null) {
    exportParameters.from = query.from;
  }
  if (query.to !== null) {
    exportParameters.to = query.to;
  }
  if (query.objectTypes[0] !== undefined) {
    exportParameters.object_type = query.objectTypes[0];
  }
  if (query.actorId !== null) {
    exportParameters.actor_id = query.actorId;
  }
  if (query.action !== null) {
    exportParameters.action = query.action;
  }
  let exportAction: ReactNode = null;
  if (definition.data !== undefined) {
    exportAction = exportable ? (
      <ExportMenu
        definition={definition.data}
        parameters={exportParameters}
        onDetails={openDetails}
      />
    ) : (
      <Button
        variant="secondary"
        icon={DownloadSimple}
        disabledReason={t("evidence.auditLog.export.unavailable")}
      >
        {t("reports.export.label")}
      </Button>
    );
  }

  let caption: string | null = null;
  if (!ranged) {
    caption =
      contractText === null
        ? t("evidence.auditLog.range.default", {
            days: DEFAULT_RANGE_DAYS,
            from: formatDate(defaultFrom),
            to: formatDate(today),
          })
        : t("evidence.auditLog.range.contract", { value: contractText });
  }
  const filterBar = (
    <div className="flex flex-col gap-2">
      <FilterBar
        fields={fields}
        resultCount={listed ? total : undefined}
        resultLabel={countLabel}
        testId="SF-09-filter-bar"
      />
      {caption === null ? null : (
        <p id={captionId} className="text-body-sm text-fg-2">
          {caption}
        </p>
      )}
      {acted.data?.truncated === true ? (
        <p className="text-body-sm text-fg-2">
          {t("evidence.auditLog.filter.actorsTruncated", {
            count: formatNumber(acted.data.items.length, { kind: "count" }),
          })}
        </p>
      ) : null}
      {acted.isError ? (
        <p className="flex flex-wrap items-center gap-3 text-body-sm text-fg-2">
          <span>{t("evidence.auditLog.filter.actorsError")}</span>
          <Button variant="link" onClick={() => void acted.refetch()}>
            {t("evidence.auditLog.retry")}
          </Button>
        </p>
      ) : null}
    </div>
  );
  const noResults = (description: string) => (
    <EmptyState
      title={t("evidence.auditLog.noResults")}
      description={description}
      action={{ label: t("evidence.auditLog.clearFilters"), onAction: clearFilters }}
    />
  );

  return (
    <div className="flex h-full min-h-0 gap-4">
      <div data-testid="SF-09-page" className="flex min-h-0 min-w-0 flex-1 flex-col">
        <ReportsHeader />
        <div className="flex min-h-0 flex-1 flex-col gap-4 px-[var(--gutter)] py-[var(--panel-pad)]">
          <ChainHeader />
          {unknown ? (
            <Banner
              tone="info"
              title={t("evidence.auditLog.eventUnknown")}
              onDismiss={() => setUnknown(false)}
            />
          ) : null}
          <div className="flex min-h-0 flex-1 flex-col">
            {listed ? null : (
              <ObjectLookupPanel filterBar={filterBar}>
                {lookup.isError ? (
                  <Banner
                    tone="negative"
                    title={t("evidence.auditLog.loadError")}
                    actions={
                      <Button variant="link" onClick={() => void lookup.refetch()}>
                        {t("evidence.auditLog.retry")}
                      </Button>
                    }
                  >
                    {lookup.error instanceof ApiProblem ? lookup.error.title : lookup.error.message}
                  </Banner>
                ) : lookup.data === undefined ? (
                  <Skeleton region={t("evidence.auditLog.grid")} shape="rows" count={10} />
                ) : (
                  noResults(t("evidence.auditLog.noContract", { id: contractText ?? "" }))
                )}
              </ObjectLookupPanel>
            )}
            {listed ? (
              <DataGrid<AuditEvent>
                name="audit-events"
                title={t("evidence.auditLog.grid")}
                describedBy={caption === null ? undefined : captionId}
                errorTitle={t("evidence.auditLog.loadError")}
                countLabel={(value, formatted) =>
                  t("evidence.auditLog.count", { count: value, formatted })
                }
                columns={columns}
                source={source}
                rowKey={(event) => event.id}
                rowLabel={(event) => formatNumber(event.chain_seq, { kind: "count" })}
                rowHref={(event) => `${AUDIT_LOG_ROUTE}${eventSearch(search, event.chain_seq)}`}
                testIdPrefix="SF-09"
                rowTestKey={(event) => String(event.chain_seq)}
                columnState={columnState}
                defaultColumnState={DEFAULT_COLUMNS}
                onColumnStateChange={setColumnState}
                onTotalChange={(next) => setTotal(next?.count)}
                viewSelector={
                  <SavedViewSelector
                    screenCode={AUDIT_LOG_SCREEN_CODE}
                    membershipId={me.active_membership_id}
                    defaultLabel={t("evidence.auditLog.view.default")}
                    columnState={columnState}
                    defaultColumnState={DEFAULT_COLUMNS}
                    onApplyColumns={setColumnState}
                    testId="SF-09-saved-view"
                  />
                }
                toolbarActions={exportAction}
                filterBar={filterBar}
                emptyState={
                  <div data-testid="SF-09-empty-audit-events">
                    <EmptyState
                      title={t("evidence.auditLog.empty.title", {
                        from: formatDate(defaultFrom),
                        to: formatDate(today),
                      })}
                      description={t("evidence.auditLog.empty.description")}
                    />
                  </div>
                }
                noResults={noResults("")}
              />
            ) : null}
          </div>
        </div>
      </div>
      {drawer === RUN_DETAILS_DRAWER && details.data !== undefined ? (
        <RunDetailsDrawer
          run={details.data}
          testIdPrefix="SF-09"
          onClose={() => {
            setDetailsRunId(null);
            void navigate(
              { search: withParams(search, { [DRAWER_PARAM]: null }) },
              { replace: true },
            );
          }}
        />
      ) : null}
      {opened ? (
        <EventDrawer
          key={wanted}
          sequence={Number(wanted)}
          event={selected}
          error={readError}
          onRetry={() => void single.refetch()}
          built={built}
          access={access}
          onClose={closeEvent}
        />
      ) : null}
    </div>
  );
}
