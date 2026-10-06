// DataGrid (DESIGN_SYSTEM DS-CMP-10, DS-A11Y-03, DS-A11Y-11; APG Grid; docs/dev-guide.md DG-FE-07,
// DG-LST-06). The single interactive grid, built on TanStack Table (column order, visibility, pinning
// and sizing) and TanStack Virtual. Sorting and filtering are server-side: the sort is the URL `sort`
// parameter and the source's query key carries the screen's filters. Pages of 200 rows load through an
// infinite query as the viewport nears the end; the DOM holds the visible rows plus 10 overscan rows,
// and `aria-rowcount` comes from `X-Erev-Total-Count`. Cells use a roving tabindex (one tab stop);
// Mod C copies raw values as tab-separated text; inline editing exists only when the grid is
// `editable` (draft data) and saves pessimistically.
import { useInfiniteQuery } from "@tanstack/react-query";
import {
  type ColumnDef,
  type ColumnSizingState,
  getCoreRowModel,
  type Updater,
  useReactTable,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  type CSSProperties,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useLocation, useNavigate } from "react-router";

import { announce } from "../../lib/a11y/announce";
import type { ListTotal } from "../../lib/api/lists";
import { formatNumber, minorUnitOf, parseDateInput, parseMoneyInput } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { decodeValue, rawParams, withParams } from "../../lib/url/params";
import { Banner } from "../feedback/Banner";
import { Skeleton } from "../feedback/Skeleton";
import { hasFilters } from "../filter-bar/filters";
import { CaretDown, CaretUp, CircleHalf, DotsThree, WarningCircle } from "../icons/registry";
import { Money } from "../money/Money";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { Tooltip } from "../ui/Tooltip";
import { CellContent, END_ALIGNED } from "./cells";
import { clipboardCell } from "./clipboard";
import { ColumnChooser } from "./ColumnChooser";
import { listedByAnotherGrid, registerSortKeys } from "./sort-keys";
import {
  DEFAULT_WIDTH,
  type EditOutcome,
  type GridColumn,
  type GridColumnState,
  type GridSelection,
  type GridSource,
  type GridTotalsRow,
  initialColumnState,
} from "./types";

export const OVERSCAN_ROWS = 10;
/** A page is requested when the last rendered row is within this many rows of the loaded end. */
export const PREFETCH_ROWS = 40;
/** Mirrors tokens.css `--row-h` per density. */
export const ROW_HEIGHT = { comfortable: 36, compact: 28 } as const;
export const SORT_PARAM = "sort";
const CHECKBOX_WIDTH = 40;
const MIN_WIDTH = 40;
const MAX_AUTOSIZE_WIDTH = 480;
const NUMBER = /^-?\d+(\.\d+)?$/;

export interface DataGridProps<Row> {
  /** The grid name of `data-testid="<SF id>-grid-<name>"`. */
  readonly name: string;
  readonly title: string;
  /** False keeps the title as the grid's name but hides it and the count (the page `h1` shows both). */
  readonly titleVisible?: boolean;
  /** The id of the element describing the grid, set as `aria-describedby` on the grid (D-88 L7-3-Q-22). */
  readonly describedBy?: string | undefined;
  /** The SCREENS SCR-ST-05 title of the load error banner, for example "Could not load contracts". */
  readonly errorTitle?: string | undefined;
  readonly headingLevel?: 2 | 3;
  /** The toolbar count, for example `(count, formatted) => "1,204 contracts"`. */
  readonly countLabel: (count: number, formatted: string) => string;
  readonly columns: readonly GridColumn<Row>[];
  readonly source: GridSource<Row>;
  readonly rowKey: (row: Row) => string;
  /** The business identifier naming a row's checkbox; defaults to the row key. */
  readonly rowLabel?: ((row: Row) => string) | undefined;
  /** Enter on a row that is not an identifier cell opens this route. */
  readonly rowHref?: ((row: Row) => string) | undefined;
  readonly selectable?: boolean;
  readonly bulkActions?: ((selection: GridSelection) => ReactNode) | undefined;
  readonly onSelectionChange?: ((selection: GridSelection) => void) | undefined;
  /** Draft data only (import staging rows, draft SSP book versions, draft contract lines). */
  readonly editable?: boolean;
  readonly columnState?: GridColumnState | undefined;
  readonly defaultColumnState?: GridColumnState | undefined;
  readonly onColumnStateChange?: ((state: GridColumnState) => void) | undefined;
  readonly viewSelector?: ReactNode;
  /** Currency view switch, export and overflow menus. */
  readonly toolbarActions?: ReactNode;
  readonly filterBar?: ReactNode;
  readonly totals?: readonly GridTotalsRow[] | undefined;
  readonly emptyState?: ReactNode;
  /** The DS-CMP-10 "no results for the filters" state with "Clear filters". */
  readonly noResults?: ReactNode;
  readonly onTotalChange?: ((total: ListTotal | null) => void) | undefined;
  /** The status footer "1,204 rows · 3 selected". */
  readonly footer?: boolean;
  readonly testIdPrefix?: string | undefined;
  readonly rowTestKey?: ((row: Row) => string) | undefined;
}

interface Cell {
  /** -1 is the header row. */
  readonly row: number;
  readonly col: number;
}

interface CellEdit {
  readonly text: string;
  readonly status: "saving" | "invalid";
  readonly message?: string | undefined;
}

interface Editor {
  readonly key: string;
  readonly text: string;
}

interface UndoEntry {
  readonly rowKey: string;
  readonly columnId: string;
  readonly previous: string;
}

interface MenuEntry {
  readonly id: string;
  readonly label: string;
  readonly onSelect: () => void;
}

type Checked = { readonly ok: true; readonly value: string } | EditOutcome;

/** SCREENS SCR-TID-03: a business identifier as a test id key. */
export function testIdKey(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * The URL sort, or null when the key is not a sort key of the grid; `foreign` then carries the value,
 * which is unrecognised (SCR-URL-21) unless another grid on the screen lists its key (SCR-URL-09).
 */
export function parseSort(
  search: string,
  sortKeys: ReadonlySet<string>,
): { readonly sort: string | null; readonly foreign: string | null } {
  const param = rawParams(search).find((item) => item.name === SORT_PARAM);
  if (param === undefined) {
    return { sort: null, foreign: null };
  }
  const value = decodeValue(param.value);
  const key = value.startsWith("-") ? value.slice(1) : value;
  return sortKeys.has(key) ? { sort: value, foreign: null } : { sort: null, foreign: value };
}

function hasMod(event: KeyboardEvent): boolean {
  return event.metaKey || event.ctrlKey;
}

function isRtl(element: Element): boolean {
  return element.closest("[dir]")?.getAttribute("dir") === "rtl";
}

function editKey(rowKey: string, columnId: string): string {
  return `${rowKey}${columnId}`;
}

function rowHeight(): number {
  return document.documentElement.dataset.density === "compact"
    ? ROW_HEIGHT.compact
    : ROW_HEIGHT.comfortable;
}

interface ColumnMenuProps {
  readonly label: string;
  readonly items: readonly MenuEntry[];
  readonly onClose: (returnFocus: boolean) => void;
}

// The column menu (APG Menu) opened by Shift+F10, the context-menu key or the header's DotsThree.
function ColumnMenu({ label, items, onClose }: ColumnMenuProps) {
  const menu = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  });
  useEffect(() => {
    menu.current?.querySelectorAll<HTMLElement>("[role='menuitem']")[active]?.focus();
  }, [active]);
  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && menu.current?.contains(event.target) !== true) {
        close.current(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, []);
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    event.stopPropagation();
    const count = items.length;
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setActive((index) => (index + 1) % count);
        return;
      case "ArrowUp":
        event.preventDefault();
        setActive((index) => (index - 1 + count) % count);
        return;
      case "Home":
        event.preventDefault();
        setActive(0);
        return;
      case "End":
        event.preventDefault();
        setActive(count - 1);
        return;
      case "Escape":
        event.preventDefault();
        onClose(true);
        return;
      case "Tab":
        onClose(false);
        return;
      default:
    }
  };
  return (
    <div
      ref={menu}
      role="menu"
      aria-label={label}
      tabIndex={-1}
      onKeyDown={onKeyDown}
      className="absolute start-0 top-full z-[var(--z-popover)] mt-1 flex min-w-48 flex-col rounded-lg border border-hairline bg-raised p-1 font-normal shadow-popover"
    >
      {items.map((item, index) => (
        <button
          key={item.id}
          type="button"
          role="menuitem"
          tabIndex={index === active ? 0 : -1}
          onClick={() => {
            onClose(true);
            item.onSelect();
          }}
          className="focus-inset flex h-[var(--row-h)] w-full items-center rounded-sm px-2 text-start text-body-sm text-fg-1 hover:bg-hover"
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

export function DataGrid<Row>({
  name,
  title,
  titleVisible = true,
  describedBy,
  errorTitle,
  headingLevel = 2,
  countLabel,
  columns,
  source,
  rowKey,
  rowLabel,
  rowHref,
  selectable = false,
  bulkActions,
  onSelectionChange,
  editable = false,
  columnState,
  defaultColumnState,
  onColumnStateChange,
  viewSelector,
  toolbarActions,
  filterBar,
  totals,
  emptyState,
  noResults,
  onTotalChange,
  footer = false,
  testIdPrefix,
  rowTestKey,
}: DataGridProps<Row>) {
  const gridId = useId();
  const titleId = `${gridId}-title`;
  const location = useLocation();
  const navigate = useNavigate();
  const scroller = useRef<HTMLDivElement>(null);
  const shouldFocus = useRef(false);
  const editorInput = useRef<HTMLInputElement>(null);
  const undo = useRef<UndoEntry[]>([]);
  const height = rowHeight();
  const offset = selectable ? 1 : 0;

  // Columns: controlled by a saved view when the screen passes `columnState`.
  const baseline = useMemo(
    () => defaultColumnState ?? initialColumnState(columns),
    [defaultColumnState, columns],
  );
  const [internalState, setInternalState] = useState(baseline);
  const layout = columnState ?? internalState;
  const updateColumns = useCallback(
    (next: GridColumnState) => {
      onColumnStateChange?.(next);
      if (columnState === undefined) {
        setInternalState(next);
      }
    },
    [columnState, onColumnStateChange],
  );

  // Sort: one key in the URL (SCR-URL-09). A key of this grid is applied; a key of another grid on the
  // screen is left alone; a key no grid lists is dropped with the SCR-URL-21 banner.
  const sortKeys = useMemo(
    () =>
      new Set(columns.flatMap((column) => (column.sortKey === undefined ? [] : [column.sortKey]))),
    [columns],
  );
  // Registered in the layout phase, so every grid of the commit is known before any grid judges a key.
  useLayoutEffect(() => registerSortKeys(sortKeys), [sortKeys]);
  const { sort, foreign: foreignSort } = parseSort(location.search, sortKeys);
  const [unrecognised, setUnrecognised] = useState(false);
  useEffect(() => {
    if (foreignSort !== null && !listedByAnotherGrid(foreignSort, sortKeys)) {
      setUnrecognised(true);
      void navigate(
        { search: withParams(location.search, { [SORT_PARAM]: null }) },
        { replace: true },
      );
    }
  }, [foreignSort, sortKeys, location.search, navigate]);

  const query = useInfiniteQuery({
    queryKey: [...source.queryKey, { sort }],
    queryFn: ({ pageParam }) => source.fetchPage(pageParam, sort),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.nextCursor,
  });
  const { hasNextPage, isFetchingNextPage, fetchNextPage, refetch } = query;
  const rows = useMemo(() => query.data?.pages.flatMap((page) => page.items) ?? [], [query.data]);
  const total = query.data?.pages[0]?.total ?? null;
  const totalChange = useRef(onTotalChange);
  useEffect(() => {
    totalChange.current = onTotalChange;
  });
  const totalCount = total?.count;
  const totalCapped = total?.capped;
  useEffect(() => {
    totalChange.current?.(
      totalCount === undefined ? null : { count: totalCount, capped: totalCapped === true },
    );
  }, [totalCount, totalCapped]);

  const definitions = useMemo<ColumnDef<Row>[]>(
    () =>
      columns.map((column) => ({
        id: column.id,
        header: column.header,
        accessorFn: (row: Row) => column.value(row),
        size: column.width ?? DEFAULT_WIDTH[column.kind],
        minSize: MIN_WIDTH,
        enableResizing: column.kind !== "actions",
      })),
    [columns],
  );
  const table = useReactTable<Row>({
    data: rows as Row[],
    columns: definitions,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => rowKey(row),
    manualSorting: true,
    manualFiltering: true,
    enableColumnResizing: true,
    columnResizeMode: "onChange",
    state: {
      columnOrder: [...layout.order],
      columnVisibility: Object.fromEntries(layout.hidden.map((id) => [id, false])),
      columnPinning: { left: [...layout.pinned.start], right: [...layout.pinned.end] },
      columnSizing: { ...layout.widths },
    },
    onColumnSizingChange: (updater: Updater<ColumnSizingState>) =>
      updateColumns({
        ...layout,
        widths: typeof updater === "function" ? updater({ ...layout.widths }) : updater,
      }),
  });
  const specs = new Map(columns.map((column) => [column.id, column]));
  const visible = [
    ...table.getLeftVisibleLeafColumns(),
    ...table.getCenterVisibleLeafColumns(),
    ...table.getRightVisibleLeafColumns(),
  ].flatMap((column) => {
    const spec = specs.get(column.id);
    return spec === undefined ? [] : [{ spec, column }];
  });
  const colCount = visible.length + offset;
  const totalWidth = table.getTotalSize() + offset * CHECKBOX_WIDTH;
  const lastStartPinned = layout.pinned.start.filter((id) => !layout.hidden.includes(id)).at(-1);
  const resizeHandlers = new Map(
    table.getFlatHeaders().map((header) => [header.id, header.getResizeHandler()]),
  );

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => height,
    overscan: OVERSCAN_ROWS,
  });
  const virtualRows = virtualizer.getVirtualItems();
  const lastRendered = virtualRows.at(-1)?.index ?? -1;
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage && lastRendered >= rows.length - 1 - PREFETCH_ROWS) {
      void fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage, lastRendered, rows.length]);

  // Focus, cell range and selection.
  const [focus, setFocus] = useState<Cell>({ row: 0, col: 0 });
  const [anchor, setAnchor] = useState<Cell | null>(null);
  const lastRow = rows.length - 1;
  const clamp = (cell: Cell): Cell => ({
    row: Math.min(Math.max(cell.row, -1), Math.max(lastRow, -1)),
    col: Math.min(Math.max(cell.col, 0), Math.max(colCount - 1, 0)),
  });
  const active = clamp(focus);
  const moveTo = (next: Cell, extend = false) => {
    setAnchor(extend ? (anchor ?? active) : null);
    shouldFocus.current = true;
    setFocus(clamp(next));
  };
  useEffect(() => {
    if (!shouldFocus.current) {
      return;
    }
    const element = scroller.current?.querySelector<HTMLElement>(
      `[data-cell="${String(active.row)}:${String(active.col)}"]`,
    );
    if (element !== null && element !== undefined) {
      shouldFocus.current = false;
      element.focus();
      if (typeof element.scrollIntoView === "function") {
        element.scrollIntoView({ block: "nearest", inline: "nearest" });
      }
    } else if (active.row >= 0) {
      virtualizer.scrollToIndex(active.row);
    }
  });
  const inRange = (row: number, col: number) =>
    anchor !== null &&
    row >= Math.min(anchor.row, active.row) &&
    row <= Math.max(anchor.row, active.row) &&
    col >= Math.min(anchor.col, active.col) &&
    col <= Math.max(anchor.col, active.col);

  const [selection, setSelection] = useState<GridSelection>({ ids: new Set(), allMatching: false });
  const selectionScope = JSON.stringify([source.queryKey, sort]);
  useEffect(() => setSelection({ ids: new Set(), allMatching: false }), [selectionScope]);
  const changeSelection = (next: GridSelection) => {
    setSelection(next);
    onSelectionChange?.(next);
  };
  const toggleRow = (key: string, value?: boolean) => {
    const ids = new Set(selection.ids);
    if (value ?? !ids.has(key)) {
      ids.add(key);
    } else {
      ids.delete(key);
    }
    changeSelection({ ids, allMatching: false });
  };
  const selectLoaded = () =>
    changeSelection({ ids: new Set(rows.map((row) => rowKey(row))), allMatching: false });
  const clearSelection = () => changeSelection({ ids: new Set(), allMatching: false });
  const selectedCount = selection.allMatching ? (total?.count ?? rows.length) : selection.ids.size;
  const loadedSelected = rows.length > 0 && rows.every((row) => selection.ids.has(rowKey(row)));

  // Sorting.
  const writeSort = (spec: GridColumn<Row>, next: string | null) => {
    void navigate(
      {
        search: withParams(location.search, {
          [SORT_PARAM]: next === null ? null : encodeURIComponent(next),
        }),
      },
      { replace: true },
    );
    announce(
      next === null
        ? t("common.grid.unsorted", { column: spec.header })
        : t("common.grid.sorted", {
            column: spec.header,
            direction: t(next.startsWith("-") ? "common.grid.descending" : "common.grid.ascending"),
          }),
    );
  };
  const cycleSort = (spec: GridColumn<Row>) => {
    const key = spec.sortKey;
    if (key === undefined) {
      return;
    }
    writeSort(spec, sort === key ? `-${key}` : sort === `-${key}` ? null : key);
  };

  // Draft editing.
  const [edits, setEdits] = useState<ReadonlyMap<string, CellEdit>>(() => new Map());
  const [editor, setEditor] = useState<Editor | null>(null);
  const updateEdit = (key: string, edit: CellEdit | null) =>
    setEdits((current) => {
      const next = new Map(current);
      if (edit === null) {
        next.delete(key);
      } else {
        next.set(key, edit);
      }
      return next;
    });
  const editorKey = editor?.key;
  useEffect(() => {
    if (editorKey !== undefined) {
      editorInput.current?.focus();
      editorInput.current?.select();
    }
  }, [editorKey]);

  const validate = (spec: GridColumn<Row>, row: Row, text: string): Checked => {
    const kind = spec.edit?.kind ?? "text";
    if (kind === "date") {
      const parsed = parseDateInput(text);
      return parsed.ok
        ? { ok: true, value: parsed.value }
        : { ok: false, message: t("common.form.date.invalid") };
    }
    if (kind === "decimal") {
      const currency = spec.currency?.(row);
      if (currency === undefined) {
        const plain = text.trim().replace(/[\s,]/g, "");
        return NUMBER.test(plain)
          ? { ok: true, value: plain }
          : { ok: false, message: t("common.filters.numberInvalid") };
      }
      const parsed = parseMoneyInput(text, currency);
      if (parsed.ok) {
        return { ok: true, value: parsed.value };
      }
      if (parsed.error === "invalid") {
        return { ok: false, message: t("common.form.money.invalid") };
      }
      const unit = minorUnitOf(currency);
      return {
        ok: false,
        message:
          unit === 0
            ? t("common.form.money.noDecimals")
            : t("common.form.money.tooManyDecimals", { count: unit }),
      };
    }
    return { ok: true, value: text };
  };

  const commit = async (row: Row, spec: GridColumn<Row>, text: string, record = true) => {
    const edit = spec.edit;
    if (edit === undefined) {
      return;
    }
    const key = editKey(rowKey(row), spec.id);
    const checked = validate(spec, row, text);
    if (!checked.ok) {
      updateEdit(key, { text, status: "invalid", message: checked.message });
      return;
    }
    if (!("value" in checked)) {
      return;
    }
    updateEdit(key, { text, status: "saving" });
    const previous = spec.value(row) ?? "";
    let outcome: EditOutcome;
    try {
      outcome = await edit.save(row, checked.value);
    } catch {
      outcome = { ok: false, message: t("common.grid.saveFailed") };
    }
    if (!outcome.ok) {
      updateEdit(key, { text, status: "invalid", message: outcome.message });
      return;
    }
    if (record) {
      undo.current.push({ rowKey: rowKey(row), columnId: spec.id, previous });
    }
    await refetch();
    updateEdit(key, null);
  };

  const startEdit = (rowIndex: number, colIndex: number, initial?: string): boolean => {
    const spec = visible[colIndex - offset]?.spec;
    const row = rows[rowIndex];
    if (!editable || spec?.edit === undefined || row === undefined) {
      return false;
    }
    const key = editKey(rowKey(row), spec.id);
    const existing = edits.get(key);
    if (existing?.status !== "saving") {
      setEditor({ key, text: initial ?? existing?.text ?? spec.value(row) ?? "" });
      announce(t("common.grid.editing", { column: spec.header, value: spec.value(row) ?? "" }));
    }
    return true;
  };

  const undoLast = async () => {
    const entry = undo.current.pop();
    const row = rows.find((item) => rowKey(item) === entry?.rowKey);
    const spec = entry === undefined ? undefined : specs.get(entry.columnId);
    if (entry !== undefined && row !== undefined && spec !== undefined) {
      await commit(row, spec, entry.previous, false);
    }
  };

  const invalidCells = rows.flatMap((row, rowIndex) =>
    visible.flatMap(({ spec }, index) =>
      edits.get(editKey(rowKey(row), spec.id))?.status === "invalid"
        ? [{ row: rowIndex, col: index + offset }]
        : [],
    ),
  );
  const nextError = () => {
    const after = invalidCells.find(
      (cell) => cell.row > active.row || (cell.row === active.row && cell.col > active.col),
    );
    const target = after ?? invalidCells[0];
    if (target !== undefined) {
      moveTo(target);
    }
  };

  // REQ-SEC-011 on the clipboard: every copied cell and header passes `clipboardCell`, so a paste
  // into a spreadsheet shows tenant text and never evaluates it.
  const copy = () => {
    const cell = (spec: GridColumn<Row>, row: Row) =>
      clipboardCell(spec.value(row) ?? "", spec.kind);
    const heading = (spec: GridColumn<Row>) => clipboardCell(spec.header, "text");
    let text: string;
    if (anchor !== null) {
      const fromRow = Math.max(Math.min(anchor.row, active.row), 0);
      const toRow = Math.max(anchor.row, active.row);
      const fromCol = Math.max(Math.min(anchor.col, active.col) - offset, 0);
      const toCol = Math.max(anchor.col, active.col) - offset;
      const range = visible.slice(fromCol, toCol + 1);
      text = rows
        .slice(fromRow, toRow + 1)
        .map((row) => range.map(({ spec }) => cell(spec, row)).join("\t"))
        .join("\n");
    } else if (selection.ids.size > 0) {
      const data = visible.filter(({ spec }) => spec.kind !== "actions");
      text = [
        data.map(({ spec }) => heading(spec)).join("\t"),
        ...rows
          .filter((row) => selection.ids.has(rowKey(row)))
          .map((row) => data.map(({ spec }) => cell(spec, row)).join("\t")),
      ].join("\n");
    } else {
      const spec = visible[active.col - offset]?.spec;
      const row = rows[active.row];
      text = spec === undefined ? "" : row === undefined ? heading(spec) : cell(spec, row);
    }
    void navigator.clipboard.writeText(text);
  };

  // Column menu.
  const [menuColumn, setMenuColumn] = useState<string | null>(null);
  const autosize = (id: string) => {
    const cells = Array.from(
      scroller.current?.querySelectorAll<HTMLElement>(`[data-column="${id}"]`) ?? [],
    );
    const measured = Math.max(0, ...cells.map((cell) => cell.scrollWidth));
    const width = Math.min(Math.max(measured, MIN_WIDTH), MAX_AUTOSIZE_WIDTH);
    updateColumns({ ...layout, widths: { ...layout.widths, [id]: width } });
  };
  const menuItems = (spec: GridColumn<Row>): MenuEntry[] => {
    const items: MenuEntry[] = [];
    const key = spec.sortKey;
    if (key !== undefined) {
      items.push(
        {
          id: "asc",
          label: t("common.grid.menu.sortAscending"),
          onSelect: () => writeSort(spec, key),
        },
        {
          id: "desc",
          label: t("common.grid.menu.sortDescending"),
          onSelect: () => writeSort(spec, `-${key}`),
        },
      );
    }
    const start = layout.pinned.start.filter((id) => id !== spec.id);
    const end = layout.pinned.end.filter((id) => id !== spec.id);
    const pinned =
      start.length !== layout.pinned.start.length || end.length !== layout.pinned.end.length;
    if (!layout.pinned.start.includes(spec.id)) {
      items.push({
        id: "pin-start",
        label: t("common.grid.menu.pinStart"),
        onSelect: () => updateColumns({ ...layout, pinned: { start: [...start, spec.id], end } }),
      });
    }
    if (!layout.pinned.end.includes(spec.id)) {
      items.push({
        id: "pin-end",
        label: t("common.grid.menu.pinEnd"),
        onSelect: () => updateColumns({ ...layout, pinned: { start, end: [spec.id, ...end] } }),
      });
    }
    if (pinned) {
      items.push({
        id: "unpin",
        label: t("common.grid.menu.unpin"),
        onSelect: () => updateColumns({ ...layout, pinned: { start, end } }),
      });
    }
    items.push(
      { id: "autosize", label: t("common.grid.menu.autosize"), onSelect: () => autosize(spec.id) },
      {
        id: "hide",
        label: t("common.grid.menu.hide"),
        onSelect: () => updateColumns({ ...layout, hidden: [...layout.hidden, spec.id] }),
      },
    );
    return items;
  };

  const onGridKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (editor !== null || event.defaultPrevented) {
      return;
    }
    if (!(event.target instanceof HTMLElement) || event.target.closest("[data-cell]") === null) {
      return;
    }
    const { row, col } = active;
    const spec = visible[col - offset]?.spec;
    const current = rows[row];
    const { key } = event;
    const handled = () => event.preventDefault();
    if (key === "ArrowRight" || key === "ArrowLeft") {
      handled();
      const forward = (key === "ArrowRight") !== isRtl(event.currentTarget);
      moveTo({ row, col: col + (forward ? 1 : -1) }, event.shiftKey);
    } else if (key === "ArrowDown" || key === "ArrowUp") {
      handled();
      moveTo({ row: row + (key === "ArrowDown" ? 1 : -1), col }, event.shiftKey);
    } else if (key === "Home") {
      handled();
      moveTo(hasMod(event) ? { row: 0, col: 0 } : { row, col: 0 });
    } else if (key === "End") {
      handled();
      moveTo(hasMod(event) ? { row: lastRow, col: colCount - 1 } : { row, col: colCount - 1 });
    } else if (key === "PageDown" || key === "PageUp") {
      handled();
      const page = Math.max(1, Math.floor((scroller.current?.clientHeight ?? 0) / height) - 1);
      moveTo({ row: row + (key === "PageDown" ? page : -page), col });
    } else if (key === "Escape") {
      if (anchor !== null) {
        handled();
        setAnchor(null);
      }
    } else if (hasMod(event) && key.toLowerCase() === "c") {
      handled();
      copy();
    } else if (hasMod(event) && key.toLowerCase() === "a") {
      if (selectable) {
        handled();
        selectLoaded();
      }
    } else if (hasMod(event) && key.toLowerCase() === "z") {
      if (editable) {
        handled();
        void undoLast();
      }
    } else if (key === " " && (event.shiftKey || (selectable && col === 0))) {
      if (selectable && current !== undefined) {
        handled();
        toggleRow(rowKey(current), event.shiftKey ? true : undefined);
      }
    } else if ((key === "F10" && event.shiftKey) || key === "ContextMenu") {
      handled();
      if (row === -1 && spec !== undefined) {
        setMenuColumn(spec.id);
      } else {
        const actions = visible.findIndex((item) => item.spec.kind === "actions");
        scroller.current
          ?.querySelector<HTMLElement>(
            `[data-cell="${String(row)}:${String(actions + offset)}"] button`,
          )
          ?.click();
      }
    } else if (row === -1) {
      if (key === "Enter" && spec?.sortKey !== undefined) {
        handled();
        cycleSort(spec);
      }
    } else if (key === "Enter" || key === "F2") {
      if (startEdit(row, col)) {
        handled();
      } else if (key === "Enter" && current !== undefined && spec?.activate !== undefined) {
        handled();
        spec.activate(current);
      } else if (key === "Enter" && current !== undefined) {
        const destination =
          (spec?.kind === "identifier" ? spec.href?.(current) : undefined) ?? rowHref?.(current);
        if (destination !== undefined) {
          handled();
          void navigate(destination);
        }
      }
    } else if (
      (key === "e" || key === "E") &&
      !hasMod(event) &&
      !event.altKey &&
      spec?.explain !== undefined &&
      current !== undefined
    ) {
      handled();
      spec.explain(current);
    } else if (key.length === 1 && !hasMod(event) && !event.altKey && startEdit(row, col, key)) {
      handled();
    }
  };

  const onGridMouseDown = (event: MouseEvent<HTMLDivElement>) => {
    if (!(event.target instanceof HTMLElement)) {
      return;
    }
    const handle = event.target.closest<HTMLElement>("[data-resize]");
    if (handle !== null) {
      resizeHandlers.get(handle.dataset.resize ?? "")?.(event);
      event.preventDefault();
      return;
    }
    const cell = event.target.closest<HTMLElement>("[data-cell]");
    if (cell === null || event.target.closest("[role='menu']") !== null) {
      return;
    }
    const [row = 0, col = 0] = (cell.dataset.cell ?? "").split(":").map(Number);
    if (editor !== null && cell.contains(editorInput.current)) {
      return;
    }
    setEditor(null);
    setAnchor(event.shiftKey ? (anchor ?? active) : null);
    setFocus({ row, col });
  };

  const onGridClick = (event: MouseEvent<HTMLDivElement>) => {
    if (!(event.target instanceof HTMLElement)) {
      return;
    }
    const header = event.target.closest<HTMLElement>("[role='columnheader']");
    if (
      header === null ||
      event.target.closest("button, input, [data-resize], [role='menu']") !== null
    ) {
      return;
    }
    const spec = specs.get(header.dataset.column ?? "");
    if (spec !== undefined) {
      cycleSort(spec);
    }
  };

  const pinnedStyle = (
    column: (typeof visible)[number]["column"],
    width: number,
  ): CSSProperties => {
    const style: CSSProperties = { inlineSize: `${String(width)}px` };
    const side = column.getIsPinned();
    if (side === "left") {
      style.insetInlineStart = `${String(column.getStart("left") + offset * CHECKBOX_WIDTH)}px`;
    } else if (side === "right") {
      style.insetInlineEnd = `${String(column.getAfter("right"))}px`;
    }
    return style;
  };
  const cellClass = (spec: GridColumn<Row>, pinned: boolean) =>
    cn(
      "focus-inset relative flex h-full shrink-0 items-center gap-1 overflow-hidden px-[var(--cell-px)]",
      END_ALIGNED.has(spec.kind) ? "justify-end text-end" : "justify-start text-start",
      pinned && "sticky z-[var(--z-sticky)] bg-surface",
      spec.id === lastStartPinned && "border-e border-default",
    );

  const bodyCount =
    total === null ? (hasNextPage ? -1 : rows.length) : total.capped ? -1 : total.count;
  const rowCount = bodyCount < 0 ? -1 : bodyCount + 1 + (totals?.length ?? 0);
  const formattedTotal =
    total === null
      ? formatNumber(rows.length, { kind: "count" })
      : `${formatNumber(total.count, { kind: "count" })}${total.capped ? "+" : ""}`;
  const Heading = headingLevel === 3 ? "h3" : "h2";
  const loading = query.isPending;
  const refreshing = query.isFetching && !loading && !isFetchingNextPage;
  const empty = !loading && !query.isError && rows.length === 0;
  const tabbable = (row: number, col: number) => active.row === row && active.col === col;
  const inlineSize = `${String(totalWidth)}px`;

  const header = (
    <div role="rowgroup" className="sticky top-0 z-[var(--z-sticky)]">
      <div
        role="row"
        aria-rowindex={1}
        className="flex h-[var(--header-row-h)] border-b border-default bg-subtle"
        style={{ inlineSize }}
      >
        {selectable ? (
          <div
            role="columnheader"
            aria-colindex={1}
            data-cell="-1:0"
            tabIndex={tabbable(-1, 0) ? 0 : -1}
            className="focus-inset sticky start-0 z-[var(--z-sticky)] flex w-10 shrink-0 items-center justify-center bg-subtle"
          >
            <input
              type="checkbox"
              tabIndex={-1}
              aria-label={t("common.grid.selectLoaded")}
              checked={loadedSelected}
              ref={(element) => {
                if (element !== null) {
                  element.indeterminate = !loadedSelected && selection.ids.size > 0;
                }
              }}
              onChange={() => (loadedSelected ? clearSelection() : selectLoaded())}
            />
          </div>
        ) : null}
        {visible.map(({ spec, column }, index) => {
          const col = index + offset;
          const direction =
            spec.sortKey === undefined
              ? undefined
              : sort === spec.sortKey
                ? "ascending"
                : sort === `-${spec.sortKey}`
                  ? "descending"
                  : "none";
          const SortIcon =
            direction === "ascending" ? CaretUp : direction === "descending" ? CaretDown : null;
          return (
            <div
              key={spec.id}
              role="columnheader"
              aria-colindex={col + 1}
              aria-sort={direction}
              data-cell={`-1:${String(col)}`}
              data-column={spec.id}
              tabIndex={tabbable(-1, col) ? 0 : -1}
              className={cn(
                cellClass(spec, column.getIsPinned() !== false),
                "group cursor-default bg-subtle text-body-sm font-medium text-fg-2",
              )}
              style={pinnedStyle(column, column.getSize())}
            >
              <span className="truncate">{spec.header}</span>
              {SortIcon === null ? null : (
                <SortIcon aria-hidden="true" size={12} className="shrink-0" />
              )}
              <button
                type="button"
                tabIndex={-1}
                aria-label={t("common.grid.menu.label", { column: spec.header })}
                aria-haspopup="menu"
                aria-expanded={menuColumn === spec.id}
                onClick={() => setMenuColumn(spec.id)}
                className="ms-auto inline-flex shrink-0 rounded-sm text-fg-3 opacity-0 hover:text-fg-1 group-hover:opacity-100 group-focus:opacity-100"
              >
                <DotsThree aria-hidden="true" />
              </button>
              {column.getCanResize() ? (
                <div
                  data-resize={spec.id}
                  aria-hidden="true"
                  className="absolute inset-y-0 end-0 w-1 cursor-col-resize touch-none"
                />
              ) : null}
              {menuColumn === spec.id ? (
                <ColumnMenu
                  label={t("common.grid.menu.label", { column: spec.header })}
                  items={menuItems(spec)}
                  onClose={(returnFocus) => {
                    setMenuColumn(null);
                    if (returnFocus) {
                      moveTo({ row: -1, col });
                    }
                  }}
                />
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );

  const body = (
    <div
      role="rowgroup"
      className="relative"
      style={{ blockSize: `${String(virtualizer.getTotalSize())}px`, inlineSize }}
    >
      {virtualRows.map((item) => {
        const row = rows[item.index];
        if (row === undefined) {
          return null;
        }
        const key = rowKey(row);
        const selected = selection.allMatching || selection.ids.has(key);
        return (
          <div
            key={key}
            role="row"
            aria-rowindex={item.index + 2}
            aria-selected={selectable ? selected : undefined}
            data-testid={
              testIdPrefix === undefined || rowTestKey === undefined
                ? undefined
                : `${testIdPrefix}-row-${testIdKey(rowTestKey(row))}`
            }
            className={cn(
              "absolute start-0 top-0 flex border-b border-hairline text-grid text-fg-1",
              selected ? "bg-accent-subtle" : "bg-surface hover:bg-hover",
            )}
            style={{
              blockSize: `${String(height)}px`,
              inlineSize,
              transform: `translateY(${String(item.start)}px)`,
            }}
          >
            {selectable ? (
              <div
                role="gridcell"
                aria-colindex={1}
                data-cell={`${String(item.index)}:0`}
                tabIndex={tabbable(item.index, 0) ? 0 : -1}
                className="focus-inset sticky start-0 z-[var(--z-sticky)] flex w-10 shrink-0 items-center justify-center bg-inherit"
              >
                <input
                  type="checkbox"
                  tabIndex={-1}
                  aria-label={t("common.grid.selectRow", { row: (rowLabel ?? rowKey)(row) })}
                  checked={selected}
                  onChange={() => toggleRow(key)}
                />
              </div>
            ) : null}
            {visible.map(({ spec, column }, index) => {
              const col = index + offset;
              const cellKey = editKey(key, spec.id);
              const edit = edits.get(cellKey);
              const errorId = `${gridId}-error-${String(item.index)}-${String(col)}`;
              return (
                <div
                  key={spec.id}
                  role={spec.kind === "identifier" ? "rowheader" : "gridcell"}
                  aria-colindex={col + 1}
                  aria-readonly={editable && spec.edit === undefined ? true : undefined}
                  aria-invalid={edit?.status === "invalid" ? true : undefined}
                  aria-describedby={edit?.status === "invalid" ? errorId : undefined}
                  aria-busy={edit?.status === "saving" ? true : undefined}
                  data-cell={`${String(item.index)}:${String(col)}`}
                  data-column={spec.id}
                  data-in-range={inRange(item.index, col) ? "" : undefined}
                  tabIndex={tabbable(item.index, col) ? 0 : -1}
                  className={cn(
                    cellClass(spec, column.getIsPinned() !== false),
                    column.getIsPinned() !== false && !selected && "bg-surface",
                    inRange(item.index, col) && "bg-accent-subtle",
                    editable && spec.edit !== undefined && "cursor-text hover:bg-hover",
                    edit?.status === "invalid" && "ring-1 ring-inset ring-negative-fg",
                  )}
                  style={pinnedStyle(column, column.getSize())}
                >
                  {editor?.key === cellKey ? (
                    <input
                      ref={editorInput}
                      aria-label={spec.header}
                      value={editor.text}
                      onChange={(event) => setEditor({ key: cellKey, text: event.target.value })}
                      onKeyDown={(event) => {
                        event.stopPropagation();
                        const text = editor.text;
                        if (event.key === "Enter" || event.key === "Tab" || event.key === "F2") {
                          event.preventDefault();
                          setEditor(null);
                          void commit(row, spec, text);
                          if (event.key === "Enter") {
                            moveTo({ row: item.index + 1, col });
                          } else if (event.key === "Tab") {
                            moveTo({ row: item.index, col: col + (event.shiftKey ? -1 : 1) });
                          } else {
                            moveTo({ row: item.index, col });
                          }
                        } else if (event.key === "Escape") {
                          event.preventDefault();
                          setEditor(null);
                          moveTo({ row: item.index, col });
                        }
                      }}
                      className="h-full w-full min-w-0 bg-surface text-grid text-fg-1"
                    />
                  ) : edit === undefined ? (
                    <CellContent column={spec} row={row} />
                  ) : (
                    <>
                      <span className="truncate">{edit.text}</span>
                      {edit.status === "saving" ? (
                        <CircleHalf
                          data-spinner=""
                          aria-hidden="true"
                          size={12}
                          className="shrink-0 text-fg-3"
                        />
                      ) : (
                        <>
                          <span id={errorId} className="sr-only">
                            {edit.message}
                          </span>
                          <Tooltip content={edit.message ?? ""} kind="label">
                            {(trigger) => (
                              <span
                                onMouseEnter={trigger.onMouseEnter}
                                onMouseLeave={trigger.onMouseLeave}
                                className="inline-flex shrink-0 text-negative-fg"
                              >
                                <WarningCircle aria-hidden="true" />
                              </span>
                            )}
                          </Tooltip>
                        </>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );

  // DS-CMP-10 item 7 (rev 1.4): a totals row names its currency in the DS-FMT-12 Currency column; while that
  // column is hidden and the grid holds several totals rows, the label carries the code instead.
  const currencyCellVisible = visible.some(
    ({ spec }, index) => index > 0 && spec.currencyColumn === true,
  );
  const totalLabel = (currency: string) =>
    currencyCellVisible || (totals?.length ?? 0) < 2
      ? t("common.grid.total")
      : t("common.grid.totalCurrency", { currency });
  const totalsRows =
    totals === undefined || totals.length === 0 ? null : (
      <div role="rowgroup" className="sticky bottom-0 z-[var(--z-sticky)]">
        {totals.map((totalRow, index) => (
          <div
            key={totalRow.key}
            role="row"
            aria-rowindex={bodyCount < 0 ? undefined : bodyCount + 2 + index}
            className="flex border-t bg-surface font-semibold text-grid text-fg-1"
            style={{
              blockSize: `${String(height)}px`,
              inlineSize,
              borderBlockStartColor: "var(--rule-total)",
            }}
          >
            {selectable ? <div role="gridcell" className="w-10 shrink-0" /> : null}
            {visible.map(({ spec, column }, columnIndex) => {
              const value = totalRow.values[spec.id];
              return (
                <div
                  key={spec.id}
                  role={columnIndex === 0 ? "rowheader" : "gridcell"}
                  aria-colindex={columnIndex + offset + 1}
                  className={cellClass(spec, column.getIsPinned() !== false)}
                  style={pinnedStyle(column, column.getSize())}
                >
                  {columnIndex === 0 ? (
                    totalLabel(totalRow.currency)
                  ) : spec.currencyColumn === true ? (
                    <span className="truncate">{totalRow.currency}</span>
                  ) : value === undefined ? null : (
                    <Money value={value} currency={totalRow.currency} variant="cell" />
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    );

  return (
    <section
      aria-labelledby={titleId}
      className="flex min-h-0 flex-1 flex-col rounded-lg border border-hairline bg-surface"
      data-testid={testIdPrefix === undefined ? undefined : `${testIdPrefix}-grid-${name}`}
    >
      <div className="flex min-h-[var(--control-h)] flex-wrap items-center gap-2 px-[var(--panel-pad)] py-2">
        <Heading
          id={titleId}
          className={cn(
            "text-title-sm text-fg-1",
            (selectedCount > 0 || !titleVisible) && "sr-only",
          )}
        >
          {title}
        </Heading>
        {selectedCount > 0 ? (
          <div
            role="region"
            aria-label={t("common.grid.selected", { count: selectedCount })}
            className="flex items-center gap-2"
          >
            <span className="text-body-sm font-medium text-fg-1">
              {t("common.grid.selected", { count: selectedCount })}
            </span>
            {bulkActions?.(selection)}
            <Button variant="link" size="sm" onClick={clearSelection}>
              {t("common.grid.clearSelection")}
            </Button>
          </div>
        ) : (
          <>
            {loading || !titleVisible ? null : (
              <span className="num text-body-sm text-fg-3">
                {countLabel(total?.count ?? rows.length, formattedTotal)}
              </span>
            )}
            {viewSelector}
          </>
        )}
        <span className="flex-1" />
        {invalidCells.length > 0 ? (
          <span className="flex items-center gap-2 text-body-sm text-negative-fg">
            <WarningCircle aria-hidden="true" />
            {t("common.grid.errors", { count: invalidCells.length })}
            <Button variant="link" size="sm" onClick={nextError}>
              {t("common.grid.nextError")}
            </Button>
          </span>
        ) : null}
        {toolbarActions}
        <ColumnChooser
          columns={columns
            .filter((column) => column.kind !== "actions")
            .map((column) => ({ id: column.id, label: column.header }))}
          layout={{ order: layout.order, hidden: layout.hidden }}
          defaultLayout={{ order: baseline.order, hidden: baseline.hidden }}
          onChange={(next) => updateColumns({ ...layout, ...next })}
        />
      </div>
      {filterBar === undefined ? null : (
        <div className="px-[var(--panel-pad)] pb-2">{filterBar}</div>
      )}
      {unrecognised ? (
        <div className="px-[var(--panel-pad)] pb-2">
          <Banner
            tone="warning"
            announce="live"
            title={t("common.filters.unrecognised")}
            onDismiss={() => setUnrecognised(false)}
          />
        </div>
      ) : null}
      {selectable && loadedSelected && total !== null && total.count > rows.length ? (
        <div className="flex items-center gap-2 bg-subtle px-[var(--panel-pad)] py-1 text-body-sm text-fg-1">
          {selection.allMatching ? t("common.grid.allSelected", { total: formattedTotal }) : null}
          <Button
            variant="link"
            size="sm"
            onClick={() =>
              selection.allMatching
                ? clearSelection()
                : changeSelection({ ids: selection.ids, allMatching: true })
            }
          >
            {selection.allMatching
              ? t("common.grid.clearSelection")
              : t("common.grid.selectAllMatching", { total: formattedTotal })}
          </Button>
        </div>
      ) : null}
      {query.isError ? (
        <div className="px-[var(--panel-pad)] pb-2">
          <Banner
            tone="negative"
            announce="live"
            title={errorTitle ?? t("common.grid.loadError")}
            actions={
              <Button variant="link" size="sm" onClick={() => void refetch()}>
                {t("common.grid.retry")}
              </Button>
            }
          />
        </div>
      ) : null}
      <div className="relative flex min-h-0 flex-1 flex-col">
        {refreshing ? (
          <div
            role="progressbar"
            aria-label={t("common.grid.refreshing")}
            className="absolute inset-x-0 top-0 z-[var(--z-sticky)] h-0.5 bg-accent-solid"
          />
        ) : null}
        <div
          ref={scroller}
          id={gridId}
          role="grid"
          aria-labelledby={titleId}
          aria-describedby={describedBy}
          aria-rowcount={rowCount}
          aria-colcount={colCount}
          aria-multiselectable={selectable ? true : undefined}
          tabIndex={-1}
          onKeyDown={onGridKeyDown}
          onMouseDown={onGridMouseDown}
          onClick={onGridClick}
          className="max-h-screen min-h-0 flex-1 overflow-auto scroll-pt-[var(--header-row-h)]"
        >
          {header}
          {loading || empty ? null : body}
          {loading || empty ? null : totalsRows}
        </div>
        {loading ? (
          <div className="px-[var(--cell-px)]">
            <Skeleton region={title} shape="rows" count={10} />
          </div>
        ) : null}
        {empty ? (
          <div className="px-[var(--panel-pad)] py-6">
            {hasFilters(location.search) ? noResults : emptyState}
          </div>
        ) : null}
      </div>
      {footer ? (
        <div className="border-t border-hairline px-[var(--panel-pad)] py-1 text-caption text-fg-3">
          {t("common.grid.footer", {
            rows: formattedTotal,
            selected: formatNumber(selectedCount, { kind: "count" }),
          })}
        </div>
      ) : null}
    </section>
  );
}
