// FilterBar (DESIGN_SYSTEM DS-CMP-13; APG Toolbar; SCREENS SCR-URL-08, SCR-URL-10, SCR-URL-21). A wrapping
// row of quick search (debounced 250 ms), filter chips, "Filter" and "Clear all"; after two lines a
// "+<n> more" toggle. The chips, their remove buttons and the buttons form one tab stop moved with Left
// and Right (mirrored in RTL), Home and End; Backspace or Delete on a chip removes it. The URL is the
// state: `q` and one `f.<field>` parameter per chip, written with `history.replace`. A write starts
// from the search the router holds, not from the one last rendered (DG-FE-03 rev 1.215), so a chip
// removed before the render of the removal before it does not put the other chip back. Result counts
// are announced politely 500 ms after they settle, prefixed "Filter removed." after a removal.
import {
  type ReactNode,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useLocation, useNavigate } from "react-router";

import { announce } from "../../lib/a11y/announce";
import { t } from "../../lib/i18n/t";
import { useLiveSearch } from "../../lib/url/live-search";
import { Banner } from "../feedback/Banner";
import { controlClass } from "../form/Field";
import { Funnel, MagnifyingGlass, X } from "../icons/registry";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { focusableWithin } from "../ui/dialog";
import { FilterEditor } from "./FilterEditor";
import {
  chipText,
  type Filter,
  type FilterField,
  filterParam,
  parseFilters,
  withFilters,
} from "./filters";

export const SEARCH_DEBOUNCE_MS = 250;
export const RESULT_ANNOUNCE_MS = 500;

export interface FilterBarProps {
  readonly fields: readonly FilterField[];
  /**
   * The quick search name and placeholder, for example "Search contracts". A list route without
   * search (04 API-C-09 answers `q` with 422) omits it, and the bar holds the chips only.
   */
  readonly searchLabel?: string | undefined;
  /** The row count of the current filters, when known. */
  readonly resultCount?: number | undefined;
  /** For example `(n) => "214 contracts"`. */
  readonly resultLabel?: ((count: number) => string) | undefined;
  readonly testId?: string | undefined;
}

type Popover =
  { readonly kind: "fields" } | { readonly kind: "editor"; readonly field: string } | null;

type Announcement = { readonly kind: "removed" | "changed"; readonly serial: number } | null;

function isRtl(element: Element): boolean {
  return element.closest("[dir]")?.getAttribute("dir") === "rtl";
}

interface PopoverPanelProps {
  readonly label: string;
  readonly onClose: (returnFocus: boolean) => void;
  readonly children: ReactNode;
}

// A non-modal popover dialog: focus moves to its first control; Esc closes it and returns focus to
// the trigger; a press outside closes it.
function PopoverPanel({ label, onClose, children }: PopoverPanelProps) {
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  });
  useEffect(() => {
    const root = panel.current;
    if (root === null) {
      return undefined;
    }
    (focusableWithin(root)[0] ?? root).focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented) {
        event.preventDefault();
        event.stopPropagation();
        close.current(true);
      }
    };
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.contains(event.target)) {
        close.current(false);
      }
    };
    root.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      root.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, []);
  return (
    <div
      ref={panel}
      role="dialog"
      aria-label={label}
      tabIndex={-1}
      className="absolute start-0 top-full z-[var(--z-popover)] mt-1 rounded-lg border border-hairline bg-raised shadow-popover"
    >
      {children}
    </div>
  );
}

export function FilterBar({
  fields,
  searchLabel,
  resultCount,
  resultLabel,
  testId,
}: FilterBarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const parsed = useMemo(() => parseFilters(location.search, fields), [location.search, fields]);
  const latest = useRef({ search: location.search, parsed, fields });
  useEffect(() => {
    latest.current = { search: location.search, parsed, fields };
  });
  const liveSearch = useLiveSearch();
  // What a write starts from: the router's search, parsed again when it is ahead of the render.
  const current = useCallback(() => {
    const search = liveSearch();
    const rendered = latest.current;
    return search === rendered.search
      ? rendered
      : { search, parsed: parseFilters(search, rendered.fields) };
  }, [liveSearch]);

  const [unrecognised, setUnrecognised] = useState(false);
  const [text, setText] = useState(parsed.query);
  const [popover, setPopover] = useState<Popover>(null);
  const [fieldSearch, setFieldSearch] = useState("");
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [pendingFocus, setPendingFocus] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState<Announcement>(null);
  const [expanded, setExpanded] = useState(false);
  const [limit, setLimit] = useState<number | null>(null);
  const [width, setWidth] = useState(0);
  const toolbar = useRef<HTMLDivElement>(null);
  const chips = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLElement | null>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const labelRef = useRef(resultLabel);
  useEffect(() => {
    labelRef.current = resultLabel;
  });

  const write = useCallback(
    (query: string, filters: readonly Filter[]) => {
      void navigate({ search: withFilters(liveSearch(), query, filters) }, { replace: true });
    },
    [navigate, liveSearch],
  );

  // SCR-URL-21: unparseable `f.*` values are dropped with a banner.
  useEffect(() => {
    if (parsed.unrecognised.length > 0) {
      setUnrecognised(true);
      const held = current().parsed;
      if (held.unrecognised.length > 0) {
        write(held.query, held.filters);
      }
    }
  }, [parsed, current, write]);

  // The quick search follows the URL when it changes from outside the input.
  useEffect(() => {
    if (searchTimer.current === null) {
      setText(parsed.query);
    }
  }, [parsed.query]);
  useEffect(
    () => () => {
      if (searchTimer.current !== null) {
        clearTimeout(searchTimer.current);
      }
    },
    [],
  );

  useEffect(() => {
    if (announcement === null || resultCount === undefined) {
      return undefined;
    }
    const timer = setTimeout(() => {
      const label = labelRef.current;
      if (label !== undefined) {
        const result = label(resultCount);
        announce(
          announcement.kind === "removed" ? t("common.filters.removed", { result }) : result,
        );
      }
      setAnnouncement(null);
    }, RESULT_ANNOUNCE_MS);
    return () => clearTimeout(timer);
  }, [announcement, resultCount]);

  const signal = useCallback(
    (kind: "removed" | "changed") =>
      setAnnouncement((current) => ({ kind, serial: (current?.serial ?? 0) + 1 })),
    [],
  );

  const remove = useCallback(
    (name: string) => {
      const { query, filters } = current().parsed;
      const index = filters.findIndex((filter) => filter.field === name);
      const rest = filters.filter((filter) => filter.field !== name);
      const next = rest[Math.min(index, rest.length - 1)];
      setPendingFocus(next === undefined ? "add" : `chip:${next.field}`);
      signal("removed");
      write(query, rest);
    },
    [current, signal, write],
  );
  const removeRef = useRef(remove);
  useEffect(() => {
    removeRef.current = remove;
  });

  const apply = (filter: Filter) => {
    const { query, filters: held } = current().parsed;
    const exists = held.some((item) => item.field === filter.field);
    const filters = exists
      ? held.map((item) => (item.field === filter.field ? filter : item))
      : [...held, filter];
    setPopover(null);
    setPendingFocus(`chip:${filter.field}`);
    signal("changed");
    write(query, filters);
  };

  const closePopover = (returnFocus: boolean) => {
    setPopover(null);
    setFieldSearch("");
    if (returnFocus && trigger.current?.isConnected === true) {
      trigger.current.focus();
    }
  };
  const openPopover = (next: Popover, opener: HTMLElement) => {
    trigger.current = opener;
    setPopover(next);
  };

  // APG Toolbar keys on the roving items.
  useEffect(() => {
    const bar = toolbar.current;
    if (bar === null) {
      return undefined;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || !(event.target instanceof HTMLElement)) {
        return;
      }
      const items = Array.from(bar.querySelectorAll<HTMLElement>("[data-roving]"));
      const index = items.indexOf(event.target);
      if (index < 0) {
        return;
      }
      const direction = isRtl(bar) ? -1 : 1;
      let next: number;
      switch (event.key) {
        case "ArrowRight":
          next = index + direction;
          break;
        case "ArrowLeft":
          next = index - direction;
          break;
        case "Home":
          next = 0;
          break;
        case "End":
          next = items.length - 1;
          break;
        case "Backspace":
        case "Delete": {
          const field = event.target.dataset.filterField;
          if (field !== undefined) {
            event.preventDefault();
            removeRef.current(field);
          }
          return;
        }
        default:
          return;
      }
      event.preventDefault();
      const target = items[Math.min(Math.max(next, 0), items.length - 1)];
      if (target !== undefined) {
        setActiveKey(target.dataset.roving ?? null);
        target.focus();
      }
    };
    bar.addEventListener("keydown", onKeyDown);
    return () => bar.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (pendingFocus === null) {
      return;
    }
    const target = Array.from(
      toolbar.current?.querySelectorAll<HTMLElement>("[data-roving]") ?? [],
    ).find((item) => item.dataset.roving === pendingFocus);
    if (target !== undefined) {
      setActiveKey(pendingFocus);
      target.focus();
      setPendingFocus(null);
    }
  }, [pendingFocus, location.search]);

  // Two lines of chips, then "+<n> more": measure with every chip shown, then keep what fits.
  const signature = `${parsed.filters.map(filterParam).join("&")}|${String(width)}`;
  useLayoutEffect(() => setLimit(null), [signature, expanded]);
  useLayoutEffect(() => {
    const container = chips.current;
    if (limit !== null || expanded || container === null) {
      return;
    }
    const items = Array.from(container.querySelectorAll<HTMLElement>("[data-filter-chip]"));
    const lines = Array.from(new Set(items.map((item) => item.offsetTop))).sort((a, b) => a - b);
    const second = lines[1];
    if (lines.length <= 2 || second === undefined) {
      setLimit(Number.POSITIVE_INFINITY);
      return;
    }
    const fitting = items.filter((item) => item.offsetTop <= second).length;
    setLimit(Math.max(fitting - 1, 1));
  }, [limit, expanded, signature]);
  useEffect(() => {
    const container = chips.current;
    if (container === null || typeof ResizeObserver === "undefined") {
      return undefined;
    }
    const observer = new ResizeObserver(() => setWidth(container.clientWidth));
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  const byName = new Map(fields.map((field) => [field.name, field]));
  const visible = expanded || limit === null ? parsed.filters.length : limit;
  const hidden = Math.max(parsed.filters.length - visible, 0);
  const rovingKeys = [
    ...parsed.filters
      .slice(0, visible)
      .flatMap((filter) => [`chip:${filter.field}`, `remove:${filter.field}`]),
    ...(hidden > 0 || expanded ? ["more"] : []),
    "add",
    ...(parsed.filters.length > 0 ? ["clear"] : []),
  ];
  const tabbable = activeKey !== null && rovingKeys.includes(activeKey) ? activeKey : rovingKeys[0];
  const roving = (key: string) => ({
    "data-roving": key,
    tabIndex: key === tabbable ? 0 : -1,
    onFocus: () => setActiveKey(key),
  });

  const editing = popover?.kind === "editor" ? byName.get(popover.field) : undefined;
  const query = fieldSearch.trim().toLocaleLowerCase();
  const fieldMatches = fields.filter((field) => field.label.toLocaleLowerCase().includes(query));

  return (
    <div className="flex flex-col gap-2" data-testid={testId}>
      {unrecognised ? (
        <Banner
          tone="warning"
          announce="live"
          title={t("common.filters.unrecognised")}
          onDismiss={() => setUnrecognised(false)}
        />
      ) : null}
      <div
        ref={toolbar}
        role="toolbar"
        aria-label={t("common.filters.label")}
        className="relative flex flex-wrap items-start gap-2"
      >
        {searchLabel === undefined ? null : (
          <span className="relative inline-flex items-center">
            <MagnifyingGlass
              aria-hidden="true"
              className="pointer-events-none absolute start-2 text-fg-3"
            />
            <input
              type="search"
              aria-label={searchLabel}
              placeholder={searchLabel}
              value={text}
              onChange={(event) => {
                const value = event.target.value;
                setText(value);
                if (searchTimer.current !== null) {
                  clearTimeout(searchTimer.current);
                }
                searchTimer.current = setTimeout(() => {
                  searchTimer.current = null;
                  signal("changed");
                  write(value, current().parsed.filters);
                }, SEARCH_DEBOUNCE_MS);
              }}
              className={cn(controlClass(false), "h-[var(--control-h-sm)] w-60 ps-8")}
            />
          </span>
        )}
        <div ref={chips} className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          {parsed.filters.slice(0, visible).map((filter) => {
            const field = byName.get(filter.field);
            if (field === undefined) {
              return null;
            }
            const label = chipText(field, filter);
            return (
              <span
                key={filter.field}
                data-filter-chip=""
                className="inline-flex h-[var(--control-h-sm)] max-w-full items-center rounded-sm border border-default bg-surface"
              >
                <button
                  type="button"
                  {...roving(`chip:${filter.field}`)}
                  data-filter-field={filter.field}
                  aria-label={t("common.filters.editChip", { filter: label })}
                  aria-haspopup="dialog"
                  aria-expanded={popover?.kind === "editor" && popover.field === filter.field}
                  onClick={(event) =>
                    openPopover({ kind: "editor", field: filter.field }, event.currentTarget)
                  }
                  className="focus-inset h-full truncate rounded-sm ps-2 pe-1 text-body-sm text-fg-1 hover:bg-hover"
                >
                  {label}
                </button>
                <Button
                  variant="ghost"
                  size="sm"
                  icon={X}
                  {...roving(`remove:${filter.field}`)}
                  data-filter-field={filter.field}
                  aria-label={t("common.filters.remove", { field: field.label })}
                  onClick={() => remove(filter.field)}
                />
              </span>
            );
          })}
          {hidden > 0 || expanded ? (
            <Button
              variant="link"
              size="sm"
              {...roving("more")}
              aria-expanded={expanded}
              onClick={() => setExpanded((current) => !current)}
            >
              {expanded ? t("common.filters.fewer") : t("common.filters.more", { count: hidden })}
            </Button>
          ) : null}
          <Button
            variant="ghost"
            size="sm"
            icon={Funnel}
            {...roving("add")}
            aria-haspopup="dialog"
            aria-expanded={popover?.kind === "fields"}
            onClick={(event) => openPopover({ kind: "fields" }, event.currentTarget)}
          >
            {t("common.filters.add")}
          </Button>
          {parsed.filters.length > 0 ? (
            <Button
              variant="link"
              size="sm"
              {...roving("clear")}
              onClick={() => {
                setPendingFocus("add");
                signal("removed");
                write(current().parsed.query, []);
              }}
            >
              {t("common.filters.clearAll")}
            </Button>
          ) : null}
        </div>
        {popover?.kind === "fields" ? (
          <PopoverPanel label={t("common.filters.add")} onClose={closePopover}>
            <div className="flex w-64 flex-col gap-2 p-2">
              <input
                type="search"
                aria-label={t("common.filters.searchFields")}
                placeholder={t("common.filters.searchFields")}
                value={fieldSearch}
                onChange={(event) => setFieldSearch(event.target.value)}
                className={controlClass(false)}
              />
              {fieldMatches.length === 0 ? (
                <p className="px-2 text-body-sm text-fg-3">{t("common.filters.noFields")}</p>
              ) : (
                <ul className="flex max-h-60 flex-col overflow-y-auto">
                  {fieldMatches.map((field) => (
                    <li key={field.name}>
                      <button
                        type="button"
                        onClick={() => {
                          setFieldSearch("");
                          setPopover({ kind: "editor", field: field.name });
                        }}
                        className="focus-inset flex h-[var(--row-h)] w-full items-center rounded-sm px-2 text-start text-body-sm text-fg-1 hover:bg-hover"
                      >
                        {field.label}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </PopoverPanel>
        ) : null}
        {editing === undefined ? null : (
          <PopoverPanel
            key={editing.name}
            label={t("common.filters.editorLabel", { field: editing.label })}
            onClose={closePopover}
          >
            <FilterEditor
              field={editing}
              initial={parsed.filters.find((filter) => filter.field === editing.name) ?? null}
              onApply={apply}
            />
          </PopoverPanel>
        )}
      </div>
    </div>
  );
}
