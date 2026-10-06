// The context a report screen runs in (RPT-VIEW-CONTEXT-DEFAULT-1; SCREENS §0.5 SCR-URL-01 rev 1.61,
// SCR-URL-20; SCREENS_B §0.5 "The context of a view", rev 1.92; PRD BR-UX-01). Schedules (SF-04), the
// report view (SF-08:report) and the dashboards (SF-08:dashboard) run for what their address says:
//   (1) an address that names an entity is that entity's;
//   (2) `entities=all` beside no entity says every entity in scope, with the book and the period the
//       address has: nothing is filled;
//   (3) any other address takes the context pill's — entity, book and period, each filled only where
//       the address leaves it out, by the member's last choice, else by the BR-UX-01 default — and the
//       address is written with `history.replace` before the screen asks a run. What the address
//       names is never rewritten.
// The screen mounts its view once the address is settled, so a view never runs on half a context: the
// pill takes `period` out of the address with its entity or book, and the report view asked a run
// without a period then. `entities` is a screen parameter of these screens: no link that copies the
// context carries it and no other screen reads it, which a value of `entity` that is no entity's code
// would not have been — the rail and thirteen files read `entity` as a code.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useLocation, useNavigate, useNavigation } from "react-router";

import {
  type ContextChoice,
  type ContextDimension,
  contextOwner,
  readStoredContext,
  resolveEntityBook,
  resolvePeriod,
} from "../../../app/shell/ContextPill";
import { useShellSession } from "../../../app/shell/SandboxIndicator";
import { useAccess } from "../../../lib/access";
import { useMe } from "../../../lib/api/queries/me";
import {
  booksKey,
  entitiesKey,
  fetchActiveEntities,
  fetchBooks,
  fetchPeriods,
  periodsKey,
  STRUCTURE_READ_PERMISSION,
} from "../../../lib/api/queries/tenant";
import { useLiveSearch } from "../../../lib/url/live-search";
import { withParams } from "../../../lib/url/params";

/** SCR-URL-01 rev 1.61: the screen parameter by which an address says "All entities". */
export const ENTITIES_PARAM = "entities";
export const ALL_ENTITIES = "all";
/** SCR-URL-16 `run` and SCR-URL-26 `run.<panel>`: the runs of the context the address had. */
const RUN_PARAM = "run";
const PANEL_RUN_PREFIX = "run.";

function named(params: URLSearchParams, name: ContextDimension): string | null {
  const value = params.get(name);
  return value === null || value === "" ? null : value;
}

export interface ViewContext {
  /** The address holds the context the view runs in: the screen mounts its view. */
  readonly settled: boolean;
  /** The read that failed while the address was being completed, else null. */
  readonly failure: Error | null;
  readonly retry: () => void;
}

function lost(query: { readonly data: unknown; readonly error: Error | null }): Error | null {
  return query.data === undefined ? query.error : null;
}

export function useViewContext(): ViewContext {
  const me = useMe();
  const access = useAccess();
  const session = useShellSession();
  const navigate = useNavigate();
  const liveSearch = useLiveSearch();
  // A write the router dropped while the member was on the way to another page is made again once
  // they have stayed (docs/dev-guide.md DG-FE-03 rule (1)).
  const moving = useNavigation().state !== "idle";
  const { pathname, search } = useLocation();
  const params = new URLSearchParams(search);
  const url: ContextChoice = {
    entity: named(params, "entity"),
    period: named(params, "period"),
    book: named(params, "book"),
  };
  // "All entities" is said beside no entity: an entity named beside it decides.
  const all = url.entity === null && params.get(ENTITIES_PARAM) === ALL_ENTITIES;
  const complete = url.entity !== null && url.book !== null && url.period !== null;
  const known = me.data !== undefined;
  // Something is left out, and the member reads what fills it: without `config.read` there is no
  // pill and no list of entities, and the address stays as it is.
  const fills = known && !all && !complete && access.holdsAnywhere(STRUCTURE_READ_PERMISSION);

  const entities = useQuery({
    queryKey: entitiesKey(),
    queryFn: fetchActiveEntities,
    enabled: fills,
  });
  const books = useQuery({ queryKey: booksKey(), queryFn: fetchBooks, enabled: fills });
  const owner = contextOwner(me.data, session);
  const stored = owner === null ? null : readStoredContext(owner);
  const choices = stored === null ? [url] : [url, stored];
  // An entity the address names is the only one offered: its book and period are filled for it, or
  // not at all when the member's list does not hold it.
  const offered =
    entities.data === undefined || url.entity === null
      ? entities.data
      : entities.data.filter((item) => item.code === url.entity);
  const head =
    !fills || offered === undefined || books.data === undefined
      ? null
      : resolveEntityBook(offered, books.data, choices);
  const entity = url.entity ?? head?.entity.code ?? null;
  const book = url.book ?? head?.book.code ?? null;
  // The period is filled on the calendar of the entity and a book it keeps: a book the address names
  // and the entity does not keep has no calendar to choose on. The periods of one entity are read
  // with `config.read` for that entity (SCR-PERM-02 (a)).
  const onCalendar =
    fills &&
    url.period === null &&
    head !== null &&
    head.book.code === book &&
    access.holds(STRUCTURE_READ_PERMISSION, head.entity);
  const periodQuery = { entity: entity ?? "", book: book ?? "" };
  const periods = useQuery({
    queryKey: periodsKey(periodQuery),
    queryFn: () => fetchPeriods(periodQuery),
    enabled: onCalendar,
  });
  const period =
    url.period ??
    (onCalendar && periods.data !== undefined
      ? (resolvePeriod(periods.data, choices)?.period.period_key ?? null)
      : null);

  const failure = fills
    ? (lost(entities) ?? lost(books) ?? (onCalendar ? lost(periods) : null))
    : null;
  const reading =
    fills &&
    failure === null &&
    (entities.data === undefined ||
      books.data === undefined ||
      (onCalendar && periods.data === undefined));
  const filled = fills && failure === null && !reading;
  const fillEntity = filled && url.entity === null ? entity : null;
  const fillBook = filled && url.book === null ? book : null;
  const fillPeriod = filled && url.period === null ? period : null;
  const writes = fillEntity !== null || fillBook !== null || fillPeriod !== null;
  const settled = known && (!fills || (filled && !writes));

  // The context the view last stood on, by page. One completed afterwards on the same page is another
  // context — the pill took the period out with its entity or book — and the runs still in the address
  // are the earlier one's (RV-01: a changed context drops `run`). The view is not mounted while its
  // context is incomplete and cannot drop them itself, so they leave the address with this write. An
  // address that arrives incomplete — a link, a shared `run=` — keeps its runs.
  const context = [all ? "*" : (entity ?? ""), book ?? "", period ?? ""].join("|");
  const stood = useRef<{ readonly pathname: string; readonly context: string } | null>(null);
  useEffect(() => {
    if (settled) {
      stood.current = { pathname, context };
    }
  });
  useEffect(() => {
    if (!writes) {
      return;
    }
    const before = stood.current;
    const moved = before !== null && before.pathname === pathname && before.context !== context;
    const changes: Record<string, string | null> = {};
    if (fillEntity !== null) {
      changes.entity = encodeURIComponent(fillEntity);
    }
    if (fillBook !== null) {
      changes.book = encodeURIComponent(fillBook);
    }
    if (fillPeriod !== null) {
      changes.period = encodeURIComponent(fillPeriod);
    }
    if (moved) {
      changes[RUN_PARAM] = null;
    }
    void navigate(
      { search: withParams(liveSearch(), changes, moved ? [PANEL_RUN_PREFIX] : []) },
      { replace: true },
    );
  }, [writes, fillEntity, fillBook, fillPeriod, context, pathname, navigate, liveSearch, moving]);

  const { refetch: readEntities } = entities;
  const { refetch: readBooks } = books;
  const { refetch: readPeriods } = periods;
  const retry = () => {
    void readEntities();
    void readBooks();
    if (onCalendar) {
      void readPeriods();
    }
  };

  return { settled, failure, retry };
}
