// Context pill (DESIGN_SYSTEM DS-CMP-03; SCREENS §1.3 SF-23). One bordered group of three segment
// buttons, entity, period and book, each opening a popover listbox. A segment that the page does not use
// is aria-disabled with the tooltip "Not used on this page". A change is announced politely: "Context
// changed to <entity>, <period label>, <book label>". WEB built the component for the design gallery;
// RFD-19 binds it to entities, periods and books with the BR-UX-01 defaults and places it in the top
// bar (`AccountingContextPill` below; BUILD_SPEC BS1-D-34, PHASES BS-D-17, DG-FE-03).
import { useQuery } from "@tanstack/react-query";
import { useCallback, useReducer, useRef, useState } from "react";
import { type UIMatch, useLocation, useMatches, useNavigate } from "react-router";

import {
  Books,
  Buildings,
  CalendarBlank,
  HourglassMedium,
  type Icon,
  LockSimple,
} from "../../components/icons/registry";
import { cn } from "../../components/ui/cn";
import { Tooltip, type TooltipTriggerProps } from "../../components/ui/Tooltip";
import { announce } from "../../lib/a11y/announce";
import { accessOf } from "../../lib/access";
import { type Me, useMe } from "../../lib/api/queries/me";
import {
  booksKey,
  entitiesKey,
  fetchActiveEntities,
  fetchBooks,
  fetchPeriods,
  periodLabel,
  periodsKey,
  STRUCTURE_READ_PERMISSION,
} from "../../lib/api/queries/tenant";
import { NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { withParams } from "../../lib/url/params";
import type { SessionState } from "../auth/RequireSession";
import { ListboxPopover } from "./ListboxPopover";
import { openMembership } from "./open-workspace";
import { useShellSession } from "./SandboxIndicator";

export type ContextDimension = "entity" | "period" | "book";
export type PeriodMarker = "open" | "soft-close" | "locked";

export interface ContextOption {
  /** The API-C-11 literal: entity code, `period_key` or book literal. */
  readonly value: string;
  /** The display text, for example "US01 · eRev Demo Inc.", "Sep 2026" or "ASC 606". */
  readonly label: string;
  /** The announcement text when it differs from the label, for example the entity code "US01". */
  readonly spoken?: string | undefined;
  readonly group?: string | undefined;
  /** Periods only: the DS-CMP-03 period-state marker. */
  readonly marker?: PeriodMarker | undefined;
}

export interface ContextSegment {
  readonly value: string;
  readonly options: readonly ContextOption[];
  /** SCREENS §1.3 "Disabled": the page does not use this dimension. */
  readonly disabled?: boolean | undefined;
}

export type ContextValue = Readonly<Record<ContextDimension, string>>;

export interface ContextPillProps {
  readonly entity: ContextSegment;
  readonly period: ContextSegment;
  readonly book: ContextSegment;
  readonly onChange: (next: ContextValue) => void;
}

const DIMENSIONS: readonly ContextDimension[] = ["entity", "period", "book"];

const SEGMENT_ICON: Readonly<Record<ContextDimension, Icon>> = {
  entity: Buildings,
  period: CalendarBlank,
  book: Books,
};

const MARKER_KEY: Readonly<Record<PeriodMarker, string>> = {
  open: "open",
  "soft-close": "softClose",
  locked: "locked",
};

function currentOption(segment: ContextSegment): ContextOption | undefined {
  return segment.options.find((option) => option.value === segment.value);
}

/** The segment's accessible name, for example "Period: Sep 2026, open". */
export function segmentName(dimension: ContextDimension, segment: ContextSegment): string {
  const option = currentOption(segment);
  const value = option?.label ?? segment.value;
  if (dimension === "period" && option?.marker !== undefined) {
    return t("shell.context.periodState", {
      value,
      state: t(`shell.context.state.${MARKER_KEY[option.marker]}`),
    });
  }
  return t(`shell.context.${dimension}`, { value });
}

function Marker({ marker }: { readonly marker: PeriodMarker }) {
  const text = t(`shell.context.marker.${MARKER_KEY[marker]}`);
  if (marker === "open") {
    return <span className="text-fg-3">{text}</span>;
  }
  const MarkerIcon = marker === "locked" ? LockSimple : HourglassMedium;
  return (
    <span
      className={cn(
        "flex items-center gap-1",
        marker === "locked" ? "text-fg-2" : "text-warning-fg",
      )}
    >
      <MarkerIcon aria-hidden="true" className="shrink-0" />
      {text}
    </span>
  );
}

export function ContextPill({ entity, period, book, onChange }: ContextPillProps) {
  const segments: Readonly<Record<ContextDimension, ContextSegment>> = { entity, period, book };
  const [open, setOpen] = useState<ContextDimension | null>(null);
  const group = useRef<HTMLDivElement>(null);
  const triggers = useRef(new Map<ContextDimension, HTMLButtonElement>());

  const close = useCallback(
    (returnFocus: boolean) => {
      setOpen(null);
      if (returnFocus && open !== null) {
        triggers.current.get(open)?.focus();
      }
    },
    [open],
  );

  const select = (dimension: ContextDimension, value: string) => {
    close(true);
    if (value === segments[dimension].value) {
      return;
    }
    const next: ContextValue = {
      entity: entity.value,
      period: period.value,
      book: book.value,
      [dimension]: value,
    };
    onChange(next);
    const spoken = (name: ContextDimension) => {
      const option = segments[name].options.find((candidate) => candidate.value === next[name]);
      return option?.spoken ?? option?.label ?? next[name];
    };
    announce(
      t("shell.context.changed", {
        entity: spoken("entity"),
        period: spoken("period"),
        book: spoken("book"),
      }),
      "polite",
    );
  };

  return (
    <div
      ref={group}
      role="group"
      aria-label={t("shell.context.label")}
      className="flex h-[var(--control-h)] items-stretch rounded-md border border-default bg-surface"
    >
      {DIMENSIONS.map((dimension, index) => {
        const segment = segments[dimension];
        const option = currentOption(segment);
        const disabled = segment.disabled === true;
        const SegmentIcon = SEGMENT_ICON[dimension];
        const name = segmentName(dimension, segment);
        const button = (trigger: TooltipTriggerProps | null) => (
          <button
            ref={(element) => {
              if (element === null) {
                triggers.current.delete(dimension);
              } else {
                triggers.current.set(dimension, element);
              }
            }}
            type="button"
            aria-label={name}
            aria-haspopup="listbox"
            aria-expanded={open === dimension}
            aria-disabled={disabled ? true : undefined}
            aria-describedby={trigger?.["aria-describedby"]}
            onMouseEnter={trigger?.onMouseEnter}
            onMouseLeave={trigger?.onMouseLeave}
            onFocus={trigger?.onFocus}
            onBlur={trigger?.onBlur}
            onKeyDown={trigger?.onKeyDown}
            onClick={() => {
              if (!disabled) {
                setOpen(open === dimension ? null : dimension);
              }
            }}
            className={cn(
              "focus-inset flex h-full items-center gap-1.5 px-2.5 text-body-sm",
              index > 0 && "border-s border-hairline",
              disabled ? "text-fg-disabled" : "text-fg-1 hover:bg-hover",
            )}
          >
            <SegmentIcon aria-hidden="true" className="shrink-0" />
            <span aria-hidden="true" className="truncate">
              {option?.label ?? segment.value}
            </span>
            {dimension === "period" && option?.marker !== undefined ? (
              <span aria-hidden="true">
                <Marker marker={option.marker} />
              </span>
            ) : null}
          </button>
        );
        return (
          <div key={dimension} className="relative flex">
            {disabled ? (
              <Tooltip content={t("shell.context.notUsed")}>{button}</Tooltip>
            ) : (
              button(null)
            )}
            {open === dimension ? (
              <ListboxPopover
                label={name}
                options={segment.options.map((candidate) => ({
                  id: candidate.value,
                  label: candidate.label,
                  group: candidate.group,
                }))}
                selectedId={segment.value}
                onSelect={(value) => {
                  select(dimension, value);
                }}
                onClose={close}
                boundary={group}
                className="start-0"
              />
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

// --- Binding (BUILD_SPEC RFD-19; PHASES BS-D-17; PRD BR-UX-01; SCREENS §1.3, §0.5 SCR-URL-01 to 03) ---
// The top bar's pill reads the active entities in scope (`GET /entities`, code order), the books
// (`GET /books`) and the periods of the context entity and book (`GET /periods?entity=&book=`). Each
// dimension takes the first valid value of the URL parameter, then the user's last choice (stored per
// workspace under `erev.context.<tenant id>`), then the BR-UX-01 default: the first entity in code
// order, the primary book it keeps and its earliest `open` period (`is_first_open`). A change stores
// the choice and replaces the parameters of the dimensions the page uses; a new entity or book drops
// the period, so its default applies. Segments are aria-disabled per the SCREENS §1.3 table.

export interface ContextEntity {
  readonly code: string;
  readonly name: string;
  readonly books: readonly { readonly book_code: string; readonly is_enabled: boolean }[];
}

export interface ContextBook {
  readonly code: string;
  readonly is_primary: boolean;
  readonly is_enabled: boolean;
}

export interface ContextPeriod {
  readonly period: {
    readonly period_key: string;
    readonly fiscal_year: number;
    readonly start_date: string;
    readonly end_date: string;
  };
  readonly state: string;
  readonly is_first_open: boolean;
}

/** Candidate values of one source (URL parameters or the stored choice); null means absent. */
export type ContextChoice = Readonly<Partial<Record<ContextDimension, string | null>>>;

export interface ResolvedEntityBook<E extends ContextEntity, B extends ContextBook> {
  readonly entity: E;
  readonly book: B;
  /** The books the entity keeps, primary first. */
  readonly books: readonly B[];
}

function byCode<T extends { readonly code: string }>(items: readonly T[]): T[] {
  return [...items].sort((a, b) => (a.code < b.code ? -1 : a.code > b.code ? 1 : 0));
}

/** The enabled books the entity keeps, the primary book first, then in code order. */
export function keptBooks<B extends ContextBook>(entity: ContextEntity, books: readonly B[]): B[] {
  const kept = new Set(
    entity.books
      .filter((candidate) => candidate.is_enabled)
      .map((candidate) => candidate.book_code),
  );
  return byCode(books.filter((candidate) => candidate.is_enabled && kept.has(candidate.code))).sort(
    (a, b) => Number(b.is_primary) - Number(a.is_primary),
  );
}

function firstValid(
  choices: readonly ContextChoice[],
  dimension: ContextDimension,
  valid: (value: string) => boolean,
): string | null {
  for (const choice of choices) {
    const value = choice[dimension];
    if (typeof value === "string" && valid(value)) {
      return value;
    }
  }
  return null;
}

/** BR-UX-01 entity and book: a valid choice, else the first entity in code order and its primary book. */
export function resolveEntityBook<E extends ContextEntity, B extends ContextBook>(
  entities: readonly E[],
  books: readonly B[],
  choices: readonly ContextChoice[],
): ResolvedEntityBook<E, B> | null {
  const ordered = byCode(entities);
  const code = firstValid(choices, "entity", (value) =>
    ordered.some((item) => item.code === value),
  );
  const entity = ordered.find((item) => item.code === code) ?? ordered[0];
  if (entity === undefined) {
    return null;
  }
  const kept = keptBooks(entity, books);
  const bookCode = firstValid(choices, "book", (value) => kept.some((item) => item.code === value));
  const book = kept.find((item) => item.code === bookCode) ?? kept[0];
  return book === undefined ? null : { entity, book, books: kept };
}

/** BR-UX-01 period: a valid choice, else the earliest `open` period, else the latest started period. */
export function resolvePeriod<P extends ContextPeriod>(
  periods: readonly P[],
  choices: readonly ContextChoice[],
): P | null {
  const key = firstValid(choices, "period", (value) =>
    periods.some((item) => item.period.period_key === value),
  );
  return (
    periods.find((item) => item.period.period_key === key) ??
    periods.find((item) => item.is_first_open) ??
    periods.filter((item) => item.state !== "future").at(-1) ??
    periods[0] ??
    null
  );
}

/** The DS-CMP-03 marker of an E-04 period state; `future` periods carry none. */
export function periodMarker(state: string): PeriodMarker | undefined {
  switch (state) {
    case "open":
    case "reopened":
      return "open";
    case "closing":
      return "soft-close";
    case "closed":
    case "permanently_locked":
      return "locked";
    default:
      return undefined;
  }
}

function inFamily(screen: string, sf: string): boolean {
  return screen === sf || screen.startsWith(`${sf}:`);
}

/** SCREENS §1.3 "SF-15 reference data" (SCREENS §0.3 Settings › Reference data). */
const REFERENCE_DATA_SCREENS: ReadonlySet<string> = new Set([
  "SF-15:customers",
  "SF-15:customer",
  "SF-15:related-party-groups",
  "SF-15:products",
  "SF-15:product",
]);

const NONE_DISABLED: Readonly<Record<ContextDimension, boolean>> = {
  entity: false,
  period: false,
  book: false,
};

/** SCREENS §1.3: the segments a screen does not use; screens the table does not list use all three. */
export function disabledDimensions(
  screen: string | null,
): Readonly<Record<ContextDimension, boolean>> {
  if (screen === null) {
    return NONE_DISABLED;
  }
  if (
    // SCREENS rev 1.20: the SF-12 lists filter by the Entity chip `f.entity`, never by the pill (§15.3).
    inFamily(screen, "SF-12") ||
    inFamily(screen, "SF-13") ||
    inFamily(screen, "SF-16") ||
    screen === "SF-24:results" ||
    REFERENCE_DATA_SCREENS.has(screen)
  ) {
    return { entity: true, period: true, book: true };
  }
  if (inFamily(screen, "SF-10")) {
    return { entity: false, period: true, book: true };
  }
  if (inFamily(screen, "SF-11")) {
    return { entity: false, period: false, book: true };
  }
  return NONE_DISABLED;
}

export const CONTEXT_STORAGE_PREFIX = "erev.context.";

/** Whose choice a stored context is: one user in one workspace (PRD BR-UX-01 "the user's last choice"). */
export interface ContextOwner {
  readonly userId: string;
  readonly tenantId: string;
}

/**
 * The storage key of a user's last choice in a workspace. The user is part of the key: another
 * person who signs in at the same browser neither starts from nor overwrites this person's entity,
 * period and book (security review 2026-09-29, P3-12).
 */
export function contextStorageKey(owner: ContextOwner): string {
  return `${CONTEXT_STORAGE_PREFIX}${owner.userId}.${owner.tenantId}`;
}

/**
 * The signed-in user in the workspace the session is in, or null while no workspace is open. The
 * workspace is the session's (`open-workspace.ts`): a workspace and its sandbox copies hold one
 * membership id, and a choice made in one must not be read or overwritten in the other.
 */
export function contextOwner(
  me: Me | undefined,
  session: SessionState | undefined,
): ContextOwner | null {
  const open = openMembership(me, session);
  return me === undefined || open === null
    ? null
    : { userId: me.user.id, tenantId: open.tenant.id };
}

/** The user's last choice in the workspace, or null. */
export function readStoredContext(owner: ContextOwner): ContextChoice | null {
  try {
    const text = window.localStorage.getItem(contextStorageKey(owner));
    if (text === null) {
      return null;
    }
    const parsed: unknown = JSON.parse(text);
    if (typeof parsed !== "object" || parsed === null) {
      return null;
    }
    const fields = parsed as Record<string, unknown>;
    const value = (name: ContextDimension) =>
      typeof fields[name] === "string" ? (fields[name] as string) : null;
    return { entity: value("entity"), period: value("period"), book: value("book") };
  } catch {
    return null;
  }
}

export function storeContext(owner: ContextOwner, choice: ContextChoice): void {
  try {
    window.localStorage.setItem(contextStorageKey(owner), JSON.stringify(choice));
  } catch {
    // Storage may be unavailable (private windows); the URL still carries the context.
  }
}

function currentScreen(matches: readonly UIMatch[]): string | null {
  for (let index = matches.length - 1; index >= 0; index -= 1) {
    const handle: unknown = matches[index]?.handle;
    if (typeof handle === "object" && handle !== null && "screen" in handle) {
      const { screen } = handle as { readonly screen: unknown };
      if (typeof screen === "string") {
        return screen;
      }
    }
  }
  return null;
}

/** The context pill of the top bar, bound to the workspace's entities, periods and books. */
export function AccountingContextPill() {
  const me = useMe();
  const matches = useMatches();
  const location = useLocation();
  const navigate = useNavigate();
  const [, rerender] = useReducer((count: number) => count + 1, 0);

  const data = me.data;
  const owner = contextOwner(data, useShellSession());
  const enabled = owner !== null && accessOf(data).holdsAnywhere(STRUCTURE_READ_PERMISSION);
  const entities = useQuery({ queryKey: entitiesKey(), queryFn: fetchActiveEntities, enabled });
  const books = useQuery({ queryKey: booksKey(), queryFn: fetchBooks, enabled });

  const params = new URLSearchParams(location.search);
  const url: ContextChoice = {
    entity: params.get("entity"),
    period: params.get("period"),
    book: params.get("book"),
  };
  const stored = owner === null ? null : readStoredContext(owner);
  const choices = stored === null ? [url] : [url, stored];
  const head =
    entities.data === undefined || books.data === undefined
      ? null
      : resolveEntityBook(entities.data, books.data, choices);
  const periodQuery = { entity: head?.entity.code ?? "", book: head?.book.code ?? "" };
  const periods = useQuery({
    queryKey: periodsKey(periodQuery),
    queryFn: () => fetchPeriods(periodQuery),
    enabled: enabled && head !== null,
  });

  if (!enabled || owner === null || head === null || periods.data === undefined) {
    return null;
  }
  const period = resolvePeriod(periods.data, choices);
  const disabled = disabledDimensions(currentScreen(matches));

  const change = (next: ContextValue) => {
    const regrouped = next.entity !== head.entity.code || next.book !== head.book.code;
    const choice: ContextChoice = { ...next, period: regrouped ? null : next.period };
    storeContext(owner, choice);
    const changes: Record<string, string | null> = {};
    for (const dimension of DIMENSIONS) {
      if (!disabled[dimension]) {
        const value = choice[dimension];
        changes[dimension] =
          value === null || value === undefined ? null : encodeURIComponent(value);
      }
    }
    rerender();
    if (Object.keys(changes).length > 0) {
      void navigate(
        {
          pathname: location.pathname,
          search: withParams(location.search, changes),
          hash: location.hash,
        },
        { replace: true },
      );
    }
  };

  return (
    <ContextPill
      entity={{
        value: head.entity.code,
        options: byCode(entities.data ?? []).map((item) => ({
          value: item.code,
          label: `${item.code} · ${item.name}`,
          spoken: item.code,
        })),
        disabled: disabled.entity,
      }}
      period={{
        value: period?.period.period_key ?? NO_VALUE,
        options: periods.data.map((item) => ({
          value: item.period.period_key,
          label: periodLabel(item.period),
          group: `FY${String(item.period.fiscal_year)}`,
          marker: periodMarker(item.state),
        })),
        disabled: disabled.period || period === null,
      }}
      book={{
        value: head.book.code,
        options: head.books.map((item) => ({
          value: item.code,
          label: t(`shell.context.books.${item.code}`),
        })),
        disabled: disabled.book,
      }}
      onChange={change}
    />
  );
}
