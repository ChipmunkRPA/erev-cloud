// Master-detail list with pane (DESIGN_SYSTEM DS-CMP-08; APG Listbox, single select, selection follows
// focus). Up and Down move and select; the detail loads after a 150 ms debounce. Home and End; type-ahead
// on the name; `J` and `K` move when focus is not in a field (they take precedence over type-ahead);
// Enter moves focus to the detail heading and Esc in the detail returns it to the selected row. The
// resize handle is a focusable separator: Left and Right ±16 px (mirrored in RTL), Home and End to the
// minimum and maximum; the width persists under `erev.master.<type>`. A list of more than 100 rows
// renders only the rows in view (TanStack Virtual), with `aria-setsize` and `aria-posinset`. Items that
// name a `group` are listed under caption rows (consecutive items of one group under one caption) and
// each option names its group through `aria-describedby`; a grouped list renders every row.
import { measureElement, useVirtualizer } from "@tanstack/react-virtual";
import {
  type CSSProperties,
  Fragment,
  type KeyboardEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

import { isTypingTarget } from "../../lib/a11y/typing";
import { t } from "../../lib/i18n/t";
import { Skeleton } from "../feedback/Skeleton";
import { cn } from "../ui/cn";

export interface MasterItem {
  readonly id: string;
  readonly name: string;
  /** The name is an identifier: mono (SCREENS §8.3 `element_code`). */
  readonly mono?: boolean | undefined;
  /** The caption the item is listed under, for example an estimate kind (SCREENS §8.3). */
  readonly group?: string | undefined;
  /** The primary amount at the end of line 1, usually `<Money>`. */
  readonly amount?: ReactNode;
  readonly identifier?: string | undefined;
  /** Status and classification chips of line 2. */
  readonly chips?: ReactNode;
  /** DS-FMT-20 date range of line 2. */
  readonly dateRange?: string | undefined;
  /** The option's accessible name, for example "Sensor gateway unit, O1"; default its text. */
  readonly optionLabel?: string | undefined;
  /** SCREENS SCR-TID-04 `row-<key>` of the option. */
  readonly testId?: string | undefined;
}

export interface MasterDetailProps {
  /** The list type; the pane width persists under `erev.master.<type>`. */
  readonly type: string;
  readonly listLabel: string;
  /** SCREENS SCR-TID-04 `grid-<name>` of the list. */
  readonly listTestId?: string | undefined;
  readonly items: readonly MasterItem[];
  readonly selectedId: string | null;
  /** Called at once on a pointer press and after the debounce on keyboard moves. */
  readonly onSelect: (id: string) => void;
  /** Filter input, sort menu and count. */
  readonly toolbar?: ReactNode;
  readonly status?: "loading" | "error" | "ready";
  readonly errorState?: ReactNode;
  readonly emptyState?: ReactNode;
  /** The detail region name, for example "Obligation details: Platform subscription". */
  readonly detailLabel: string;
  /** The detail text while nothing is selected. */
  readonly noSelection: string;
  /** SCREENS SCR-TID-04 `pane-<name>` of the detail region. */
  readonly detailTestId?: string | undefined;
  readonly children?: ReactNode;
}

export const DETAIL_DEBOUNCE_MS = 150;
export const RESIZE_STEP_PX = 16;
/** Mirrors tokens.css `--master-w-min`, `--master-w` and `--master-w-max`. */
export const MASTER_WIDTH = { min: 280, initial: 360, max: 480 } as const;
/** DS-CMP-08: lists longer than this are virtualized. */
export const VIRTUALIZE_ABOVE = 100;
/** Mirrors tokens.css `--master-row-h` per density. */
export const MASTER_ROW_HEIGHT = { comfortable: 56, compact: 48 } as const;
const OVERSCAN_ROWS = 10;
const TYPE_AHEAD_RESET_MS = 500;

function clampWidth(width: number): number {
  return Math.min(Math.max(width, MASTER_WIDTH.min), MASTER_WIDTH.max);
}

function storageKey(type: string): string {
  return `erev.master.${type}`;
}

function storedWidth(type: string): number {
  try {
    const stored = Number(window.localStorage.getItem(storageKey(type)) ?? Number.NaN);
    return Number.isInteger(stored) ? clampWidth(stored) : MASTER_WIDTH.initial;
  } catch {
    return MASTER_WIDTH.initial;
  }
}

function masterRowHeight(): number {
  return document.documentElement.dataset.density === "compact"
    ? MASTER_ROW_HEIGHT.compact
    : MASTER_ROW_HEIGHT.comfortable;
}

function isRtl(element: Element): boolean {
  return element.closest("[dir]")?.getAttribute("dir") === "rtl";
}

export function MasterDetail({
  type,
  listLabel,
  listTestId,
  items,
  selectedId,
  onSelect,
  toolbar,
  status = "ready",
  errorState,
  emptyState,
  detailLabel,
  noSelection,
  detailTestId,
  children,
}: MasterDetailProps) {
  const [active, setActive] = useState<string | null>(selectedId);
  const [width, setWidth] = useState(() => storedWidth(type));
  const rows = useRef(new Map<string, HTMLDivElement>());
  const list = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const detail = useRef<HTMLDivElement>(null);
  const separator = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const typeAhead = useRef({ text: "", at: 0 });
  const widthRef = useRef(width);
  const pendingFocus = useRef<string | null>(null);
  const groupPrefix = useId();
  const grouped = items.some((item) => item.group !== undefined);
  const virtualized = items.length > VIRTUALIZE_ABOVE && !grouped;
  const rowHeight = masterRowHeight();
  const virtualizer = useVirtualizer({
    count: virtualized ? items.length : 0,
    getScrollElement: () => scroller.current,
    estimateSize: () => rowHeight,
    // A row whose second line wraps (for example an approval's status chip) is taller than the
    // two-line estimate; each rendered row is measured, never below `--master-row-h` (D-85).
    measureElement: (element, entry, instance) =>
      Math.max(measureElement(element, entry, instance), rowHeight),
    overscan: OVERSCAN_ROWS,
  });

  useEffect(() => setActive(selectedId), [selectedId]);
  useEffect(
    () => () => {
      if (timer.current !== null) {
        clearTimeout(timer.current);
      }
    },
    [],
  );
  useEffect(() => {
    widthRef.current = width;
    try {
      window.localStorage.setItem(storageKey(type), String(width));
    } catch {
      // Storage can be unavailable (privacy mode); the width then lasts for this page only.
    }
  }, [type, width]);

  const moveTo = useCallback(
    (index: number, focus: boolean) => {
      const position = Math.min(Math.max(index, 0), items.length - 1);
      const item = items[position];
      if (item === undefined) {
        return;
      }
      setActive(item.id);
      const row = rows.current.get(item.id);
      if (row === undefined && virtualized) {
        // The row is outside the rendered window: scroll it in, then focus it once it renders.
        pendingFocus.current = focus ? item.id : null;
        virtualizer.scrollToIndex(position);
      } else {
        if (focus) {
          row?.focus();
        }
        if (row !== undefined && typeof row.scrollIntoView === "function") {
          row.scrollIntoView({ block: "nearest" });
        }
      }
      if (timer.current !== null) {
        clearTimeout(timer.current);
      }
      timer.current = setTimeout(() => {
        timer.current = null;
        onSelect(item.id);
      }, DETAIL_DEBOUNCE_MS);
    },
    [items, onSelect, virtualized, virtualizer],
  );
  const activeIndex = items.findIndex((item) => item.id === active);

  useEffect(() => {
    const id = pendingFocus.current;
    const row = id === null ? undefined : rows.current.get(id);
    if (row !== undefined) {
      pendingFocus.current = null;
      row.focus();
    }
  });

  // J and K anywhere on the page while focus is not in a field and no modal dialog is open.
  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (
        (event.key !== "j" && event.key !== "k") ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        event.defaultPrevented ||
        isTypingTarget(event.target) ||
        document.querySelector("[aria-modal='true']") !== null
      ) {
        return;
      }
      event.preventDefault();
      const inList = list.current?.contains(document.activeElement) === true;
      moveTo(activeIndex + (event.key === "j" ? 1 : -1), inList);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [activeIndex, moveTo]);

  // Esc inside the detail pane returns focus to the selected row, unless a control handled it.
  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (
        event.key === "Escape" &&
        !event.defaultPrevented &&
        event.target instanceof Node &&
        detail.current?.contains(event.target) === true &&
        active !== null
      ) {
        rows.current.get(active)?.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [active]);

  // The resize handle: keyboard steps and pointer drags.
  useEffect(() => {
    const handle = separator.current;
    if (handle === null) {
      return undefined;
    }
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      const direction = isRtl(handle) ? -1 : 1;
      let next: ((current: number) => number) | null = null;
      if (event.key === "ArrowRight") {
        next = (current) => current + direction * RESIZE_STEP_PX;
      } else if (event.key === "ArrowLeft") {
        next = (current) => current - direction * RESIZE_STEP_PX;
      } else if (event.key === "Home") {
        next = () => MASTER_WIDTH.min;
      } else if (event.key === "End") {
        next = () => MASTER_WIDTH.max;
      }
      if (next !== null) {
        const step = next;
        event.preventDefault();
        setWidth((current) => clampWidth(step(current)));
      }
    };
    const onPointerDown = (event: PointerEvent) => {
      event.preventDefault();
      const startX = event.clientX;
      const direction = isRtl(handle) ? -1 : 1;
      const startWidth = widthRef.current;
      const onMove = (move: PointerEvent) =>
        setWidth(clampWidth(startWidth + direction * (move.clientX - startX)));
      const onUp = () => {
        document.removeEventListener("pointermove", onMove);
        document.removeEventListener("pointerup", onUp);
      };
      document.addEventListener("pointermove", onMove);
      document.addEventListener("pointerup", onUp);
    };
    handle.addEventListener("keydown", onKeyDown);
    handle.addEventListener("pointerdown", onPointerDown);
    return () => {
      handle.removeEventListener("keydown", onKeyDown);
      handle.removeEventListener("pointerdown", onPointerDown);
    };
  }, []);

  const onListKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        moveTo(activeIndex + 1, true);
        return;
      case "ArrowUp":
        event.preventDefault();
        moveTo(activeIndex < 0 ? 0 : activeIndex - 1, true);
        return;
      case "Home":
        event.preventDefault();
        moveTo(0, true);
        return;
      case "End":
        event.preventDefault();
        moveTo(items.length - 1, true);
        return;
      case "Enter": {
        const heading = detail.current?.querySelector<HTMLElement>("h1, h2, h3, h4, h5, h6");
        if (heading !== null && heading !== undefined) {
          event.preventDefault();
          if (!heading.hasAttribute("tabindex")) {
            heading.tabIndex = -1;
          }
          heading.focus();
        }
        return;
      }
      default:
        if (
          event.key.length === 1 &&
          event.key !== "j" &&
          event.key !== "k" &&
          !event.altKey &&
          !event.ctrlKey &&
          !event.metaKey
        ) {
          const now = Date.now();
          const text =
            now - typeAhead.current.at > TYPE_AHEAD_RESET_MS
              ? event.key
              : typeAhead.current.text + event.key;
          typeAhead.current = { text, at: now };
          const query = text.toLocaleLowerCase();
          const count = items.length;
          const start = text.length === 1 ? activeIndex + 1 : Math.max(activeIndex, 0);
          for (let step = 0; step < count; step += 1) {
            const index = (start + step) % count;
            if (items[index]?.name.toLocaleLowerCase().startsWith(query) === true) {
              moveTo(index, true);
              break;
            }
          }
        }
    }
  };

  const tabbable = active ?? items[0]?.id;
  // A caption row opens each run of items that name the same group; an option names its caption.
  const captionIds: (string | undefined)[] = [];
  const groupStarts = new Set<number>();
  items.forEach((item, index) => {
    if (item.group === undefined) {
      captionIds.push(undefined);
    } else if (item.group === items[index - 1]?.group) {
      captionIds.push(captionIds[index - 1]);
    } else {
      groupStarts.add(index);
      captionIds.push(`${groupPrefix}-group-${String(groupStarts.size)}`);
    }
  });
  const renderOption = (item: MasterItem, index: number, style?: CSSProperties) => {
    const selected = item.id === active;
    return (
      <div
        key={item.id}
        ref={(element) => {
          if (element === null) {
            rows.current.delete(item.id);
          } else {
            rows.current.set(item.id, element);
            if (virtualized) {
              virtualizer.measureElement(element);
            }
          }
        }}
        data-index={virtualized ? index : undefined}
        role="option"
        aria-label={item.optionLabel}
        aria-describedby={captionIds[index]}
        data-testid={item.testId}
        aria-selected={selected}
        aria-setsize={virtualized ? items.length : undefined}
        aria-posinset={virtualized ? index + 1 : undefined}
        tabIndex={item.id === tabbable ? 0 : -1}
        onMouseDown={() => {
          if (timer.current !== null) {
            clearTimeout(timer.current);
            timer.current = null;
          }
          setActive(item.id);
          onSelect(item.id);
        }}
        style={style}
        className={cn(
          "focus-inset flex min-h-[var(--master-row-h)] cursor-default flex-col justify-center gap-0.5 border-b border-hairline px-3 py-1.5",
          virtualized ? "absolute inset-x-0 top-0" : "relative",
          selected
            ? "bg-accent-subtle before:absolute before:inset-y-0 before:start-0 before:w-0.5 before:bg-selection-edge before:content-['']"
            : "hover:bg-hover",
        )}
      >
        <div className="flex items-baseline gap-2">
          <span
            className={cn(
              "min-w-0 flex-1 truncate font-medium text-fg-1",
              item.mono === true ? "font-mono text-mono-sm" : "text-body",
            )}
          >
            {item.name}
          </span>
          {item.amount}
        </div>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-fg-3">
          {item.identifier === undefined ? null : (
            <span className="font-mono text-mono-sm">{item.identifier}</span>
          )}
          {item.chips}
          {item.dateRange === undefined ? null : (
            <span className="num text-body-sm">{item.dateRange}</span>
          )}
        </div>
      </div>
    );
  };

  let listContent: ReactNode;
  if (status === "loading") {
    listContent = (
      <div className="p-2">
        <Skeleton region={listLabel} shape="rows" count={6} />
      </div>
    );
  } else if (status === "error") {
    listContent = <div className="p-2">{errorState}</div>;
  } else if (items.length === 0) {
    listContent = <div className="px-[var(--panel-pad)]">{emptyState}</div>;
  } else {
    listContent = (
      <div
        ref={list}
        role="listbox"
        aria-label={listLabel}
        data-testid={listTestId}
        tabIndex={-1}
        onKeyDown={onListKeyDown}
        className={virtualized ? "relative" : undefined}
        style={virtualized ? { blockSize: `${String(virtualizer.getTotalSize())}px` } : undefined}
      >
        {virtualized
          ? virtualizer.getVirtualItems().map((row) => {
              const item = items[row.index];
              return item === undefined
                ? null
                : renderOption(item, row.index, {
                    transform: `translateY(${String(row.start)}px)`,
                  });
            })
          : items.map((item, index) =>
              groupStarts.has(index) && item.group !== undefined ? (
                <Fragment key={item.id}>
                  <div
                    role="presentation"
                    id={captionIds[index]}
                    className="border-b border-hairline bg-subtle px-3 pb-1 pt-2 text-caption text-fg-3"
                  >
                    {item.group}
                  </div>
                  {renderOption(item, index)}
                </Fragment>
              ) : (
                renderOption(item, index)
              ),
            )}
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0">
      <div
        className="flex min-h-0 shrink-0 flex-col bg-surface"
        style={{ inlineSize: `${String(width)}px` }}
      >
        {toolbar === undefined ? null : (
          <div className="flex items-center gap-2 border-b border-hairline p-2">{toolbar}</div>
        )}
        <div ref={scroller} data-virtual-viewport="" className="min-h-0 flex-1 overflow-y-auto">
          {listContent}
        </div>
      </div>
      <div
        ref={separator}
        role="separator"
        aria-orientation="vertical"
        aria-label={t("common.master.resize")}
        aria-valuenow={width}
        aria-valuemin={MASTER_WIDTH.min}
        aria-valuemax={MASTER_WIDTH.max}
        // A focusable separator is a widget (WAI-ARIA 1.2 separator; DS-CMP-08 resize handle), which
        // the plugin's role table lists as non-interactive.
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
        tabIndex={0}
        className="focus-inset relative w-px shrink-0 cursor-col-resize touch-none bg-hairline before:absolute before:inset-y-0 before:-start-1 before:w-2 before:content-['']"
      />
      <div
        ref={detail}
        role="region"
        aria-label={detailLabel}
        data-testid={detailTestId}
        className="flex min-w-0 flex-1 flex-col overflow-y-auto"
      >
        {active === null ? (
          <p className="p-[var(--panel-pad)] text-body-sm text-fg-2">{noSelection}</p>
        ) : (
          children
        )}
      </div>
    </div>
  );
}
