// Command palette (DESIGN_SYSTEM DS-CMP-04; SCREENS §1.4 SF-24; 03 REQ-UX-002). `Mod K` or the top-bar
// search trigger toggles a modal dialog named "Command palette": an APG combobox over a listbox of
// found records, pages and commands. Pages are "Go to <destination>" for each built rail destination
// (XR-14); commands are the Theme and Density preferences. Up and Down move and wrap, Enter opens
// (`Mod Enter` opens a page or a record in a new tab), Esc clears a query and then closes, and focus
// returns to the element focused before opening. The result count is announced politely.
//
// Record search (BUILD_SPEC CTR-28; 04 API-R-55 `GET /search`): from two characters with a letter or
// a digit, 120 ms after the last key, for a holder of `contract.read` — at most 8 rows a scope, a
// group a scope in E-120 order ahead of the pages and commands, and "Show all results", which opens
// SF-24:results. The scope chips name what is listed: every group, one scope of records (the read
// then sends `scope`), the pages or the commands. While an answer is on its way the rows of the
// answer before it stay, the running mark stands at the end of the input, and Enter waits for the
// answer unless a page or a command the text matches is the active option. A record opens the route
// SCREENS §1.4 builds from its scope and id; an obligation's needs its contract, read from
// `GET /obligations/{id}` when its row becomes the active one, and Enter waits for that read. An
// answer that comes after the palette has closed, or after its page has left, opens nothing
// (docs/dev-guide.md DG-FE-03 (3)).
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  type KeyboardEvent,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router";

import {
  Buildings,
  CircleHalf,
  FileText,
  type Icon,
  ListChecks,
  MagnifyingGlass,
  Moon,
  Notebook,
  Receipt,
  Sun,
  Table,
} from "../../components/icons/registry";
import { Button } from "../../components/ui/Button";
import { cn } from "../../components/ui/cn";
import { trapTab, useModalFocus } from "../../components/ui/dialog";
import { chipFor, StatusChip, statusMessageKey } from "../../components/ui/StatusChip";
import { announce } from "../../lib/a11y/announce";
import { useAccess } from "../../lib/access";
import { ApiProblem } from "../../lib/api/problems";
import {
  fetchObligationContract,
  fetchSearch,
  fetchSearchScope,
  isSearchScope,
  markMatches,
  obligationContractKey,
  obligationRoute,
  PALETTE_LIMIT,
  RECORD_ROUTE_PATTERNS,
  recordRoute,
  SEARCH_PERMISSION,
  SEARCH_ROUTE,
  SEARCH_SCOPES,
  SEARCH_STATUS_ENUM,
  searchable,
  type SearchGroup,
  type SearchItem,
  searchKey,
  searchResultsRoute,
  type SearchScope,
  searchTerms,
} from "../../lib/api/queries/search";
import { t } from "../../lib/i18n/t";
import { useLivePath, usePageStays } from "../../lib/url/live-search";
import { contextSearch, RAIL_DESTINATIONS } from "./IconRail";
import { DENSITIES, THEMES, useDisplayPreferences } from "./UserMenu";

/** The groups of the list in their order: the E-120 scopes, "Show all results", pages, commands. */
export type PaletteGroup = SearchScope | "more" | "pages" | "commands";
/** DS-CMP-04 scope chips. */
export type PaletteChip = "all" | SearchScope | "pages" | "commands";

/** DS-CMP-04: record search is debounced 120 ms. */
export const SEARCH_DEBOUNCE_MS = 120;

export interface PaletteItem {
  readonly id: string;
  readonly group: PaletteGroup;
  readonly label: string;
  readonly icon: Icon;
  /** Enter, or a press. */
  readonly perform: () => void;
  /** `Mod Enter`: the route of a page or a record in a new tab; a command has none. */
  readonly performInNewTab?: (() => void) | undefined;
  /** A found record: its scope and the item the API answered. */
  readonly record?: { readonly scope: SearchScope; readonly item: SearchItem } | undefined;
}

const SECTIONS: readonly PaletteGroup[] = [...SEARCH_SCOPES, "more", "pages", "commands"];
const CHIPS: readonly PaletteChip[] = ["all", ...SEARCH_SCOPES, "pages", "commands"];
const SHOW_ALL_ID = "show-all";

const RECORD_ICON: Readonly<Record<SearchScope, Icon>> = {
  contracts: FileText,
  customers: Buildings,
  invoices: Receipt,
  obligations: ListChecks,
  journals: Notebook,
};

interface ModifierKey {
  readonly key: string;
  readonly metaKey: boolean;
  readonly ctrlKey: boolean;
  readonly altKey: boolean;
  readonly shiftKey: boolean;
}

/** `Mod K`: Command+K or Control+K. */
export function isModK(event: ModifierKey): boolean {
  return (
    (event.metaKey || event.ctrlKey) &&
    !event.altKey &&
    !event.shiftKey &&
    event.key.toLowerCase() === "k"
  );
}

function normalise(text: string): string {
  return text.toLocaleLowerCase().replace(/\s+/g, " ").trim();
}

/** Case-insensitive substring match on the label; an empty query lists every item. */
export function matchItems(items: readonly PaletteItem[], query: string): readonly PaletteItem[] {
  const needle = normalise(query);
  return needle === "" ? items : items.filter((item) => normalise(item.label).includes(needle));
}

/** The heading of a group and the label of its scope chip. */
function groupLabel(group: SearchScope | "pages" | "commands"): string {
  return isSearchScope(group) ? t(`search.scope.${group}`) : t(`shell.palette.group.${group}`);
}

/** The pages and commands a scope chip lists; a chip of one record scope lists neither. */
function underChip(items: readonly PaletteItem[], chip: PaletteChip): readonly PaletteItem[] {
  if (chip === "all") {
    return items;
  }
  return chip === "pages" || chip === "commands" ? items.filter((item) => item.group === chip) : [];
}

function Highlighted({ label, query }: { readonly label: string; readonly query: string }) {
  const needle = normalise(query);
  const start = needle === "" ? -1 : label.toLocaleLowerCase().indexOf(needle);
  if (start < 0) {
    return <>{label}</>;
  }
  const end = start + needle.length;
  return (
    <>
      {label.slice(0, start)}
      <span className="font-semibold">{label.slice(start, end)}</span>
      {label.slice(end)}
    </>
  );
}

/** A text of a found record with the word beginnings the terms match in weight 600 (DS-CMP-04). */
function Marked({ text, terms }: { readonly text: string; readonly terms: readonly string[] }) {
  return (
    <>
      {markMatches(text, terms).map((part, index) =>
        part.match ? (
          <span key={index} className="font-semibold">
            {part.text}
          </span>
        ) : (
          <span key={index}>{part.text}</span>
        ),
      )}
    </>
  );
}

/** The status chip of a found record (SCREENS §1.4); none where the scope or the record has none. */
function recordChip(scope: SearchScope, item: SearchItem) {
  const enumId = SEARCH_STATUS_ENUM[scope];
  return enumId === null || item.status === null ? null : chipFor(enumId, item.status);
}

/** What a screen reader reads for a found record: its two texts and the word of its chip. */
function recordName(scope: SearchScope, item: SearchItem): string {
  const chip = recordChip(scope, item);
  return [item.primary, item.secondary, chip === null ? null : t(statusMessageKey(chip.status))]
    .filter((part): part is string => part !== null && part !== "")
    .join(", ");
}

export interface CommandPaletteProps {
  /** The built route paths; pages and records list only built destinations. */
  readonly built: ReadonlySet<string>;
}

export function CommandPalette({ built }: CommandPaletteProps) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.defaultPrevented || !isModK(event)) {
        return;
      }
      event.preventDefault();
      setOpen((current) => !current);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  const mac = /Mac|iPhone|iPad/.test(navigator.userAgent);
  const label = t("shell.search.trigger");
  return (
    <>
      <Button
        variant="secondary"
        icon={MagnifyingGlass}
        aria-label={label}
        aria-haspopup="dialog"
        aria-keyshortcuts="Meta+K Control+K"
        onClick={() => {
          setOpen(true);
        }}
        className="xl:w-80 xl:justify-start"
      >
        <span className="hidden flex-1 text-start text-fg-3 xl:inline">{label}</span>
        <kbd className="hidden font-mono text-mono-sm text-fg-3 xl:inline">
          {t(mac ? "shell.search.hintMac" : "shell.search.hintOther")}
        </kbd>
      </Button>
      {open
        ? createPortal(
            <PaletteDialog
              built={built}
              onClose={() => {
                setOpen(false);
              }}
            />,
            document.body,
          )
        : null}
    </>
  );
}

function usePaletteItems(built: ReadonlySet<string>, close: () => void): readonly PaletteItem[] {
  const navigate = useNavigate();
  const { search } = useLocation();
  const { chooseTheme, chooseDensity } = useDisplayPreferences();
  return useMemo(() => {
    const pages: PaletteItem[] = RAIL_DESTINATIONS.filter((destination) =>
      built.has(destination.defaultRoute),
    ).map((destination) => {
      const href = `${destination.defaultRoute}${contextSearch(search, destination.context)}`;
      return {
        id: `page-${destination.key}`,
        group: "pages",
        label: t("shell.palette.goTo", { destination: t(destination.labelKey) }),
        icon: destination.icon,
        perform: () => {
          close();
          void navigate(href);
        },
        performInNewTab: () => {
          window.open(href, "_blank", "noopener");
        },
      };
    });
    const themeIcon: Readonly<Record<(typeof THEMES)[number], Icon>> = {
      system: CircleHalf,
      light: Sun,
      dark: Moon,
    };
    const themes: PaletteItem[] = THEMES.map((value) => ({
      id: `theme-${value}`,
      group: "commands",
      label: t(`shell.palette.theme.${value}`),
      icon: themeIcon[value],
      perform: () => {
        chooseTheme(value);
        close();
      },
    }));
    const densities: PaletteItem[] = DENSITIES.map((value) => ({
      id: `density-${value}`,
      group: "commands",
      label: t(`shell.palette.density.${value}`),
      icon: Table,
      perform: () => {
        chooseDensity(value);
        close();
      },
    }));
    return [...pages, ...themes, ...densities];
  }, [built, search, navigate, chooseTheme, chooseDensity, close]);
}

interface PaletteDialogProps {
  readonly built: ReadonlySet<string>;
  readonly onClose: () => void;
}

function PaletteDialog({ built, onClose }: PaletteDialogProps) {
  const listId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const chipRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // DG-FE-03 (3): what an answer opens, it opens for the palette that asked — still open, over the
  // page it was opened on. The palette outlives a change of page, so the path is asked before and
  // after as well.
  const stays = usePageStays();
  const livePath = useLivePath();
  // 04 API-R-55: the route asks `contract.read`. Without it no search is sent: the palette lists
  // pages and commands and says nothing of records (SCREENS §1.4 "As bound").
  const canSearch = useAccess().holdsAnywhere(SEARCH_PERMISSION);
  const [query, setQuery] = useState("");
  const [chip, setChip] = useState<PaletteChip>("all");
  /** The active option by its id: an answer that arrives does not move it. */
  const [activeId, setActiveId] = useState<string | null>(null);
  /** The text the search was last asked for, 120 ms after the last key. */
  const [asked, setAsked] = useState<string | null>(null);
  /** An obligation's contract is being read for an Enter or a press. */
  const [opening, setOpening] = useState(false);
  /** The record whose route could not be read. */
  const [unopened, setUnopened] = useState<string | null>(null);
  /** Enter was pressed with no active option while the answer for the text is on its way. */
  const waiting = useRef<{ readonly newTab: boolean; readonly path: string } | null>(null);
  /** The read of an obligation's contract an Enter waits for; any later act of the member ends it. */
  const awaited = useRef(0);
  const statics = usePaletteItems(built, onClose);
  useModalFocus({ panel, initialFocus: input });

  const chips = canSearch ? CHIPS : CHIPS.filter((value) => !isSearchScope(value));
  const scope = isSearchScope(chip) ? chip : null;
  const records = canSearch && (chip === "all" || scope !== null);
  const typed = records ? searchable(query) : null;
  useEffect(() => {
    if (typed === null || typed === asked) {
      return undefined;
    }
    const timer = setTimeout(() => {
      setAsked(typed);
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [typed, asked]);
  const q = typed === null ? null : asked;
  const search = useQuery({
    queryKey: searchKey(q ?? "", scope, PALETTE_LIMIT),
    queryFn: async (): Promise<readonly SearchGroup[]> =>
      scope === null
        ? fetchSearch(q ?? "", PALETTE_LIMIT)
        : [await fetchSearchScope(q ?? "", scope, PALETTE_LIMIT, null)],
    enabled: q !== null,
    // DS-CMP-04 "loading": the rows of the answer before stay until the next one is here.
    placeholderData: keepPreviousData,
    retry: false,
  });
  const searching = typed !== null && (typed !== asked || search.isFetching);
  // The rows shown are the answer for the text as it stands.
  const fresh = q !== null && typed === asked && search.isSuccess && !search.isPlaceholderData;
  // A 403 is a session whose access changed under it: no records, and no error line (§1.4).
  const refused = search.error instanceof ApiProblem && search.error.status === 403;
  const unavailable = q !== null && !searching && search.isError && !refused;
  const groups = useMemo(
    (): readonly SearchGroup[] => (q === null ? [] : (search.data ?? [])),
    [q, search.data],
  );

  const go = useCallback(
    (route: string, newTab: boolean) => {
      if (newTab) {
        window.open(route, "_blank", "noopener");
        return;
      }
      onClose();
      void navigate(route);
    },
    [navigate, onClose],
  );
  const openObligation = useCallback(
    (item: SearchItem, newTab: boolean) => {
      const key = obligationContractKey(item.id);
      const known = queryClient.getQueryData<string>(key);
      if (known !== undefined) {
        go(obligationRoute(known, item.id), newTab);
        return;
      }
      awaited.current += 1;
      const serial = awaited.current;
      const path = livePath();
      // The palette that asked is still open and nothing was typed or chosen since.
      const mine = () => awaited.current === serial && stays();
      setUnopened(null);
      setOpening(true);
      queryClient
        .fetchQuery({
          queryKey: key,
          queryFn: () => fetchObligationContract(item.id),
          staleTime: Number.POSITIVE_INFINITY,
          retry: false,
        })
        .then(
          (contractId) => {
            if (mine()) {
              setOpening(false);
              if (livePath() === path) {
                go(obligationRoute(contractId, item.id), newTab);
              }
            }
          },
          () => {
            if (mine()) {
              setOpening(false);
              if (livePath() === path) {
                setUnopened(item.primary);
              }
            }
          },
        );
    },
    [queryClient, go, stays, livePath],
  );

  const recordItems = useMemo((): readonly PaletteItem[] => {
    const items: PaletteItem[] = [];
    for (const group of groups) {
      // XR-14: a record is listed only when the route it opens is built.
      if (!built.has(RECORD_ROUTE_PATTERNS[group.scope])) {
        continue;
      }
      for (const item of group.items.slice(0, PALETTE_LIMIT)) {
        const route = recordRoute(group.scope, item);
        if (group.scope !== "obligations" && route === null) {
          continue;
        }
        items.push({
          id: `${group.scope}-${item.id}`,
          group: group.scope,
          label: recordName(group.scope, item),
          icon: RECORD_ICON[group.scope],
          perform: () => {
            if (route === null) {
              openObligation(item, false);
            } else {
              go(route, false);
            }
          },
          performInNewTab: () => {
            if (route === null) {
              openObligation(item, true);
            } else {
              go(route, true);
            }
          },
          record: { scope: group.scope, item },
        });
      }
    }
    return items;
  }, [groups, built, go, openObligation]);
  const showAll = useMemo((): PaletteItem | null => {
    const text = typed ?? q;
    if (recordItems.length === 0 || text === null || !built.has(SEARCH_ROUTE)) {
      return null;
    }
    const route = searchResultsRoute(text, scope);
    return {
      id: SHOW_ALL_ID,
      group: "more",
      label: t("shell.palette.showAll"),
      icon: MagnifyingGlass,
      perform: () => {
        go(route, false);
      },
      performInNewTab: () => {
        go(route, true);
      },
    };
  }, [recordItems.length, typed, q, scope, built, go]);
  const matches = underChip(matchItems(statics, query), chip);
  const ordered = useMemo(
    (): readonly PaletteItem[] => [
      ...recordItems,
      ...(showAll === null ? [] : [showAll]),
      ...matches.filter((item) => item.group === "pages"),
      ...matches.filter((item) => item.group === "commands"),
    ],
    [recordItems, showAll, matches],
  );

  // The active option: the one named, while it is listed. Else the first — but never a row of the
  // answer before the text changed, which the member did not ask for: then the first page or command.
  const named = activeId === null ? -1 : ordered.findIndex((item) => item.id === activeId);
  const first =
    fresh || recordItems.length === 0
      ? ordered.length > 0
        ? 0
        : -1
      : ordered.findIndex((item) => item.group === "pages" || item.group === "commands");
  const activeIndex = named >= 0 ? named : first;
  const active = activeIndex < 0 ? undefined : ordered[activeIndex];

  const resultCount = ordered.filter((item) => item.group !== "more").length;
  useEffect(() => {
    if (query.trim() !== "") {
      announce(t("shell.palette.results", { count: resultCount }), "polite");
    }
  }, [query, resultCount]);

  const optionId = (index: number) => `${listId}-option-${String(index)}`;
  const activeOptionId = activeIndex < 0 ? undefined : optionId(activeIndex);
  useEffect(() => {
    if (activeOptionId !== undefined) {
      const option = document.getElementById(activeOptionId);
      // jsdom has no layout and no `scrollIntoView`.
      if (option !== null && typeof option.scrollIntoView === "function") {
        option.scrollIntoView({ block: "nearest" });
      }
    }
  }, [activeOptionId]);

  // SCREENS §1.4 (ruling P3): the route of an obligation needs its contract; the read runs when its
  // row becomes the active one, so that Enter and `Mod Enter` have the route in hand.
  const activeObligation = active?.record?.scope === "obligations" ? active.record.item.id : null;
  useEffect(() => {
    if (activeObligation !== null) {
      void queryClient.prefetchQuery({
        queryKey: obligationContractKey(activeObligation),
        queryFn: () => fetchObligationContract(activeObligation),
        staleTime: Number.POSITIVE_INFINITY,
        retry: false,
      });
    }
  }, [activeObligation, queryClient]);

  const run = (item: PaletteItem, newTab: boolean) => {
    if (newTab && item.performInNewTab !== undefined) {
      item.performInNewTab();
    } else {
      item.perform();
    }
  };
  // An Enter that waited: once the answer is here it opens the option that is then the active one,
  // while the palette is still open over the page it was opened on (DG-FE-03 (3)).
  useEffect(() => {
    const queued = waiting.current;
    if (queued === null || searching) {
      return;
    }
    waiting.current = null;
    if (active !== undefined && stays() && livePath() === queued.path) {
      run(active, queued.newTab);
    }
  });

  const firstStatic = (text: string, under: PaletteChip): string | null =>
    underChip(matchItems(statics, text), under)[0]?.id ?? null;
  /** The member acts again: what an earlier Enter waited for is no longer wanted. */
  const startOver = useCallback(() => {
    waiting.current = null;
    awaited.current += 1;
    setOpening(false);
    setUnopened(null);
  }, []);
  const type = (text: string) => {
    startOver();
    setQuery(text);
    // A page or a command the text matches is the active option at once and stays it when records
    // arrive; with none the first record of the answer becomes it.
    setActiveId(firstStatic(text, chip));
  };
  const choose = (value: PaletteChip) => {
    startOver();
    setChip(value);
    setActiveId(firstStatic(query, value));
  };

  // Esc and Tab are handled on the dialog element itself (as Modal does), for the input and the list.
  const latest = useRef({ query, onClose });
  useEffect(() => {
    latest.current = { query, onClose };
  });
  useEffect(() => {
    const root = panel.current;
    if (root === null) {
      return undefined;
    }
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (latest.current.query !== "") {
          startOver();
          setQuery("");
          setActiveId(null);
        } else {
          latest.current.onClose();
        }
        return;
      }
      trapTab(event, root);
    };
    root.addEventListener("keydown", onKeyDown);
    return () => {
      root.removeEventListener("keydown", onKeyDown);
    };
  }, [startOver]);

  const onInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    const count = ordered.length;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (count > 0) {
        setActiveId(ordered[(activeIndex + 1) % count]?.id ?? null);
      }
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (count > 0) {
        const previous = activeIndex < 0 ? count - 1 : (activeIndex - 1 + count) % count;
        setActiveId(ordered[previous]?.id ?? null);
      }
    } else if (event.key === "Enter") {
      event.preventDefault();
      const newTab = event.metaKey || event.ctrlKey;
      if (active === undefined) {
        // No page or command matches and the answer for this text is not here yet: Enter waits.
        if (searching) {
          waiting.current = { newTab, path: livePath() };
        }
        return;
      }
      run(active, newTab);
    }
  };

  const onChipKeyDown = (index: number) => (event: KeyboardEvent<HTMLButtonElement>) => {
    const rtl = event.currentTarget.closest("[dir]")?.getAttribute("dir") === "rtl";
    const step =
      event.key === (rtl ? "ArrowLeft" : "ArrowRight")
        ? 1
        : event.key === (rtl ? "ArrowRight" : "ArrowLeft")
          ? -1
          : 0;
    if (step === 0) {
      return;
    }
    event.preventDefault();
    const next = (index + step + chips.length) % chips.length;
    const value = chips[next];
    if (value !== undefined) {
      chipRefs.current[next]?.focus();
      choose(value);
    }
  };

  const terms = searchTerms(typed ?? q ?? "");
  const renderOption = (item: PaletteItem) => {
    const index = ordered.indexOf(item);
    const ItemIcon = item.icon;
    const found = item.record;
    const status = found === undefined ? null : recordChip(found.scope, found.item);
    return (
      <div
        key={item.id}
        id={optionId(index)}
        role="option"
        tabIndex={-1}
        aria-selected={index === activeIndex}
        aria-label={found === undefined ? undefined : item.label}
        onMouseDown={(event) => {
          event.preventDefault();
          run(item, event.metaKey || event.ctrlKey);
        }}
        onMouseMove={() => {
          if (index !== activeIndex) {
            setActiveId(item.id);
          }
        }}
        className={cn(
          "flex h-[var(--row-h)] shrink-0 cursor-default items-center gap-2 rounded-sm px-2 text-body-sm text-fg-1",
          // "Show all results" stays in view at the lower edge of the list while the records
          // above it scroll; the row is opaque and ends the rows that pass beneath it at a line.
          item.group === "more" && "sticky bottom-0 z-[var(--z-sticky)] border-t border-hairline",
          index === activeIndex ? "bg-hover" : item.group === "more" && "bg-raised",
        )}
      >
        <ItemIcon aria-hidden="true" className="shrink-0 text-fg-2" />
        {found === undefined ? (
          <span className="truncate">
            <Highlighted label={item.label} query={query} />
          </span>
        ) : (
          <>
            <span className="min-w-0 truncate">
              <Marked text={found.item.primary} terms={terms} />
            </span>
            <span className="min-w-0 flex-1 truncate text-fg-2">
              <Marked text={found.item.secondary} terms={terms} />
            </span>
            {status === null ? null : <StatusChip status={status.status} />}
          </>
        )}
      </div>
    );
  };

  const hasResults = ordered.length > 0;
  const trimmed = query.trim();
  // What the list says when it is empty: nothing while an answer is on its way.
  const emptyLine = searching
    ? null
    : scope !== null && typed === null
      ? t("search.tooShort")
      : fresh
        ? t("search.noMatches", { query: trimmed })
        : unavailable || scope !== null
          ? null
          : t("shell.palette.noResults", { query: trimmed });
  return (
    <div
      className="fixed inset-0 z-[var(--z-modal)] flex justify-center bg-scrim p-4"
      style={{ paddingBlockStart: "12vh" }}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={t("shell.palette.label")}
        tabIndex={-1}
        className="flex max-h-full w-160 max-w-full flex-col self-start overflow-hidden rounded-xl border border-hairline bg-raised shadow-overlay"
      >
        <div className="flex items-center gap-2 border-b border-hairline px-4">
          <MagnifyingGlass aria-hidden="true" className="shrink-0 text-fg-3" />
          <input
            ref={input}
            type="text"
            role="combobox"
            aria-label={t(canSearch ? "shell.palette.inputRecords" : "shell.palette.input")}
            aria-expanded={hasResults}
            aria-controls={hasResults ? listId : undefined}
            aria-autocomplete="list"
            aria-activedescendant={activeOptionId}
            aria-busy={searching || opening ? true : undefined}
            placeholder={t(canSearch ? "shell.palette.inputRecords" : "shell.palette.input")}
            value={query}
            onChange={(event) => {
              type(event.target.value);
            }}
            onKeyDown={onInputKeyDown}
            className="focus-inset h-12 min-w-0 flex-1 rounded-sm bg-transparent px-2 text-body text-fg-1 placeholder:text-fg-3"
          />
          {searching || opening ? (
            <CircleHalf
              aria-hidden="true"
              data-testid="SF-24-searching"
              className="shrink-0 text-fg-3"
            />
          ) : null}
        </div>
        <div
          role="radiogroup"
          aria-label={t("shell.palette.scope.label")}
          className="flex flex-wrap gap-1 border-b border-hairline px-4 py-2"
        >
          {chips.map((value, index) => (
            <button
              key={value}
              ref={(element) => {
                chipRefs.current[index] = element;
              }}
              type="button"
              role="radio"
              aria-checked={value === chip}
              tabIndex={value === chip ? 0 : -1}
              // A press leaves the focus in the input, where the member goes on typing.
              onMouseDown={(event) => {
                event.preventDefault();
              }}
              onClick={() => {
                choose(value);
              }}
              onKeyDown={onChipKeyDown(index)}
              className={cn(
                "inline-flex h-6 items-center rounded-sm border px-2 text-caption font-medium",
                value === chip
                  ? "border-control bg-surface text-fg-1"
                  : "border-transparent text-fg-2 hover:bg-hover hover:text-fg-1",
              )}
            >
              {value === "all" ? t("shell.palette.scope.all") : groupLabel(value)}
            </button>
          ))}
        </div>
        {unavailable || unopened !== null ? (
          <div
            className={cn(
              "flex flex-col gap-1 px-4 pt-3 text-body-sm text-fg-2",
              !hasResults && emptyLine === null && "pb-3",
            )}
          >
            {unavailable ? <p role="alert">{t("shell.palette.unavailable")}</p> : null}
            {unopened === null ? null : (
              <p role="alert">{t("shell.palette.unopened", { record: unopened })}</p>
            )}
          </div>
        ) : null}
        {hasResults ? (
          <div
            id={listId}
            role="listbox"
            aria-label={t(canSearch ? "shell.palette.listLabelRecords" : "shell.palette.listLabel")}
            aria-busy={searching ? true : undefined}
            // No padding at the lower edge, where "Show all results" is pinned: a padding there
            // would show the rows that pass beneath it. The spacer below gives the list its end.
            className="flex max-h-96 flex-col overflow-y-auto px-2 pt-2"
          >
            {SECTIONS.map((group) => {
              const groupItems = ordered.filter((item) => item.group === group);
              if (groupItems.length === 0) {
                return null;
              }
              if (group === "more") {
                return groupItems.map(renderOption);
              }
              const headingId = `${listId}-${group}`;
              return (
                <div key={group} role="group" aria-labelledby={headingId} className="flex flex-col">
                  <div id={headingId} className="px-2 pb-1 pt-2 text-caption text-fg-3">
                    {groupLabel(group)}
                  </div>
                  {groupItems.map(renderOption)}
                </div>
              );
            })}
            <div aria-hidden="true" className="h-2 shrink-0" />
          </div>
        ) : emptyLine === null ? null : (
          <p className="px-4 py-6 text-body-sm text-fg-2">{emptyLine}</p>
        )}
        <div className="flex gap-4 border-t border-hairline px-4 py-2 text-caption text-fg-3">
          <span>{t("shell.palette.hint.move")}</span>
          <span>{t("shell.palette.hint.open")}</span>
          <span>{t("shell.palette.hint.close")}</span>
        </div>
      </div>
    </div>
  );
}
