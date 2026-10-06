// Line editor (DESIGN_SYSTEM DS-CMP-10 inline editing of draft data, DS-CMP-21, DS-A11Y-03, DS-A11Y-11; APG
// Grid; docs/dev-guide.md DG-FE-07). The grid of draft lines a form holds in its own state and saves in one
// body (the lines of a draft contract, of a draft modification): the shared DataGrid reads server pages and
// saves cell by cell, so a form-held set of lines has this grid, which keeps the DS-CMP-10 anatomy,
// keyboard and ARIA and holds one DS-CMP-21 control in each cell.
//
// One tab stop with a roving `tabindex` on the cells. On a cell: arrows move one cell (mirrored in RTL),
// Home and End go to the row's first and last cell, with Mod to the grid's, Page Up and Page Down move by
// the visible rows, Mod C copies the cell's value, and Enter, F2 or a printable character starts editing
// (the character replaces the value). In a control: Enter commits and moves down, Tab commits and moves to
// the next cell, F2 finishes, Esc restores the value the cell had and returns to it. A wrong cell carries
// `aria-invalid`, its message below the control and in `aria-describedby`; the toolbar shows the count,
// "<n> errors" with "Next error", and the add button. The row header column is pinned to the start and the
// remove button to the end. Not built: the cell range (Shift+Arrow), which serves read-only grids.
import {
  type FocusEvent,
  type KeyboardEvent,
  type ReactNode,
  useId,
  useRef,
  useState,
} from "react";

import { announce } from "../../lib/a11y/announce";
import { formatDate, formatNumber, parseDateInput } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { Combobox } from "../form/Combobox";
import { controlClass, type FieldControlProps, fieldId, fieldLabelId } from "../form/Field";
import type { ListOption } from "../form/Listbox";
import { MoneyInput } from "../form/MoneyInput";
import { Plus, Trash, WarningCircle } from "../icons/registry";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";

export type LineCellKind = "text" | "decimal" | "money" | "date" | "select" | "combobox";

export interface LineColumn<Row> {
  readonly id: string;
  /** The column header, for example "Total price (USD)". */
  readonly header: string;
  /** The column's name in a cell's accessible name and in announcements; the header when absent. */
  readonly label?: string | undefined;
  readonly kind: LineCellKind;
  /** The typed text of a text, decimal, money or date cell; the chosen option value otherwise ("" none). */
  readonly value: (row: Row) => string;
  /** The options of a select or combobox cell. */
  readonly options?: readonly ListOption<string>[] | undefined;
  /** Money cells: the currency whose minor unit the blur check and echo use; null until it is known. */
  readonly currency?: string | null | undefined;
  /** The cell takes no input in this row. */
  readonly disabled?: ((row: Row) => boolean) | undefined;
  /** The identifier column: `role="rowheader"`, mono, pinned to the start. */
  readonly rowHeader?: boolean | undefined;
  /** The width classes of the column, for example "w-32 min-w-32". */
  readonly width: string;
}

export interface LineEditorProps<Row> {
  /** The grid's name, for example "Contract lines". */
  readonly title: string;
  readonly countLabel: (count: number, formatted: string) => string;
  readonly columns: readonly LineColumn<Row>[];
  readonly rows: readonly Row[];
  readonly rowId: (row: Row) => string;
  /** The field name of the grid itself: the key of its own message and the id of the add button. */
  readonly name: string;
  /** The field name of a cell: `fieldId(name)` is its control, and the key of its message. */
  readonly cellName: (rowId: string, columnId: string) => string;
  /** Field name → message. */
  readonly errors: Readonly<Record<string, string>>;
  readonly onChange: (rowId: string, columnId: string, value: string) => void;
  /** The format message of a money or date cell after its blur, or null (DS-CMP-21). */
  readonly onFormatError: (name: string, message: string | null) => void;
  readonly addLabel: string;
  /** Set when no further line may be added: the reason the add button states. */
  readonly addDisabledReason?: string | undefined;
  readonly onAdd: () => void;
  /** The name of a row's remove button, for example "Remove line O1". */
  readonly removeLabel: (row: Row, index: number) => string;
  readonly onRemove: (rowId: string) => void;
  /** Shown in place of the rows while there is none. */
  readonly emptyText: string;
  /** SCREENS SCR-TID-04 `grid-<name>`, for example "SF-03-grid-lines". */
  readonly testId?: string | undefined;
}

interface Position {
  readonly row: number;
  readonly col: number;
}

interface Snapshot {
  readonly cell: string;
  readonly rowId: string;
  readonly columnId: string;
  readonly value: string;
}

const END_ALIGNED: ReadonlySet<LineCellKind> = new Set(["decimal", "money"]);
/** Page Up and Page Down where the viewport cannot be measured. */
const FALLBACK_PAGE_ROWS = 10;
const EDITOR =
  "input:not([type='hidden']):not([disabled]), select:not([disabled]), button:not([disabled])";

function cellKey(position: Position): string {
  return `${String(position.row)}:${String(position.col)}`;
}

function isRtl(element: Element): boolean {
  return element.closest("[dir]")?.getAttribute("dir") === "rtl";
}

/** The control props of a cell: outside the tab order, because the grid is one tab stop. */
function cellControl(name: string, errorId: string, invalid: boolean): FieldControlProps {
  const control = {
    id: fieldId(name),
    name,
    tabIndex: -1,
    ...(invalid ? { "aria-describedby": errorId, "aria-invalid": true as const } : {}),
  };
  return control;
}

interface DateCellProps {
  readonly control: FieldControlProps;
  readonly value: string;
  readonly invalid: boolean;
  readonly onChange: (text: string) => void;
  readonly onFormatError: (message: string | null) => void;
}

/** A typed date, as the DataGrid's date editor: checked and echoed as DS-FMT-16 on blur. */
function DateCell({ control, value, invalid, onChange, onFormatError }: DateCellProps) {
  const onBlur = () => {
    if (value.trim() === "") {
      onFormatError(null);
      return;
    }
    const parsed = parseDateInput(value);
    if (parsed.ok) {
      onChange(formatDate(parsed.value));
      onFormatError(null);
    } else {
      onFormatError(t("common.form.date.invalid"));
    }
  };
  return (
    <input
      {...control}
      type="text"
      autoComplete="off"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      onBlur={onBlur}
      className={cn(controlClass(invalid), "num")}
    />
  );
}

export function LineEditor<Row>({
  title,
  countLabel,
  columns,
  rows,
  rowId,
  name,
  cellName,
  errors,
  onChange,
  onFormatError,
  addLabel,
  addDisabledReason,
  onAdd,
  removeLabel,
  onRemove,
  emptyText,
  testId,
}: LineEditorProps<Row>) {
  const titleId = useId();
  const scroller = useRef<HTMLDivElement>(null);
  const snapshot = useRef<Snapshot | null>(null);
  const [focus, setFocus] = useState<Position>({ row: 0, col: 0 });
  const lastRow = rows.length - 1;
  // The actions column follows the data columns.
  const lastCol = columns.length;
  const active: Position = {
    row: Math.min(Math.max(focus.row, 0), Math.max(lastRow, 0)),
    col: Math.min(Math.max(focus.col, 0), lastCol),
  };
  const invalidCells = rows.flatMap((row) =>
    columns
      .map((column) => cellName(rowId(row), column.id))
      .filter((cell) => Object.hasOwn(errors, cell)),
  );

  const cellElement = (position: Position) =>
    scroller.current?.querySelector<HTMLElement>(`[data-cell="${cellKey(position)}"]`) ?? null;
  const focusCell = (position: Position) => {
    const next: Position = {
      row: Math.min(Math.max(position.row, 0), Math.max(lastRow, 0)),
      col: Math.min(Math.max(position.col, 0), lastCol),
    };
    const element = cellElement(next);
    if (element === null) {
      return;
    }
    setFocus(next);
    element.focus();
    if (typeof element.scrollIntoView === "function") {
      element.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  };
  const startEdit = (cell: HTMLElement): boolean => {
    const editor = cell.querySelector<HTMLElement>(EDITOR);
    if (editor === null) {
      return false;
    }
    editor.focus();
    if (editor instanceof HTMLInputElement) {
      editor.select();
    }
    return true;
  };
  const positionOf = (cell: HTMLElement): Position => {
    const [row = 0, col = 0] = (cell.dataset.cell ?? "").split(":").map(Number);
    return { row, col };
  };

  const onFocus = (event: FocusEvent<HTMLTableElement>) => {
    const target = event.target as HTMLElement;
    const cell = target.closest<HTMLElement>("[data-cell]");
    if (cell === null) {
      return;
    }
    const position = positionOf(cell);
    setFocus(position);
    const row = rows[position.row];
    const column = columns[position.col];
    if (target === cell || row === undefined || column === undefined) {
      snapshot.current = null;
      return;
    }
    // Focus entered the cell's control: editing starts, and Esc returns to this value.
    const key = cellKey(position);
    if (snapshot.current?.cell !== key) {
      const value = column.value(row);
      snapshot.current = { cell: key, rowId: rowId(row), columnId: column.id, value };
      const option = column.options?.find((item) => item.value === value);
      announce(
        t("common.grid.editing", {
          column: column.label ?? column.header,
          value: option?.label ?? value,
        }),
      );
    }
  };

  const copy = (position: Position) => {
    const row = rows[position.row];
    const column = columns[position.col];
    if (row !== undefined && column !== undefined) {
      void navigator.clipboard.writeText(column.value(row));
    }
  };

  const navigate = (event: KeyboardEvent<HTMLTableElement>, cell: HTMLElement) => {
    const { row, col } = positionOf(cell);
    const mod = event.metaKey || event.ctrlKey;
    const { key } = event;
    const move = (next: Position) => {
      event.preventDefault();
      focusCell(next);
    };
    if (key === "ArrowRight" || key === "ArrowLeft") {
      const forward = (key === "ArrowRight") !== isRtl(event.currentTarget);
      move({ row, col: col + (forward ? 1 : -1) });
    } else if (key === "ArrowDown" || key === "ArrowUp") {
      move({ row: row + (key === "ArrowDown" ? 1 : -1), col });
    } else if (key === "Home") {
      move(mod ? { row: 0, col: 0 } : { row, col: 0 });
    } else if (key === "End") {
      move(mod ? { row: lastRow, col: lastCol } : { row, col: lastCol });
    } else if (key === "PageDown" || key === "PageUp") {
      const height = cell.getBoundingClientRect().height;
      const viewport = scroller.current?.closest("main")?.clientHeight ?? 0;
      const page = height > 0 && viewport > 0 ? Math.max(1, Math.floor(viewport / height) - 1) : 0;
      const step = page > 0 ? page : FALLBACK_PAGE_ROWS;
      move({ row: row + (key === "PageDown" ? step : -step), col });
    } else if (mod && key.toLowerCase() === "c") {
      event.preventDefault();
      copy({ row, col });
    } else if (key === "Enter" || key === "F2") {
      event.preventDefault();
      if (col === lastCol) {
        cell.querySelector<HTMLButtonElement>("button")?.click();
      } else {
        startEdit(cell);
      }
    } else if (key.length === 1 && !mod && !event.altKey && col !== lastCol) {
      // The character is typed into the control, where it replaces the selected value.
      startEdit(cell);
    } else if (key === " " && col === lastCol) {
      event.preventDefault();
      cell.querySelector<HTMLButtonElement>("button")?.click();
    }
  };

  const edit = (event: KeyboardEvent<HTMLTableElement>, cell: HTMLElement) => {
    const { row, col } = positionOf(cell);
    const { key } = event;
    if (key === "Enter") {
      // A combobox with its list open takes Enter for the option.
      if (event.defaultPrevented || col === lastCol) {
        return;
      }
      event.preventDefault();
      focusCell({ row: row < lastRow ? row + 1 : row, col });
    } else if (key === "F2") {
      event.preventDefault();
      focusCell({ row, col });
    } else if (key === "Tab") {
      const step = event.shiftKey ? -1 : 1;
      let next: Position = { row, col: col + step };
      if (next.col > lastCol) {
        next = { row: row + 1, col: 0 };
      } else if (next.col < 0) {
        next = { row: row - 1, col: lastCol };
      }
      // Past the last cell, or before the first, Tab leaves the grid.
      if (next.row >= 0 && next.row <= lastRow) {
        event.preventDefault();
        focusCell(next);
      }
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTableElement>) => {
    const target = event.target as HTMLElement;
    const cell = target.closest<HTMLElement>("[data-cell]");
    if (cell === null) {
      return;
    }
    if (target === cell) {
      navigate(event, cell);
    } else {
      edit(event, cell);
    }
  };
  // Esc in a control cancels the edit before the control reads the key (a combobox would clear itself);
  // an open list closes first.
  const onKeyDownCapture = (event: KeyboardEvent<HTMLTableElement>) => {
    const target = event.target as HTMLElement;
    const cell = target.closest<HTMLElement>("[data-cell]");
    if (
      event.key !== "Escape" ||
      cell === null ||
      target === cell ||
      target.getAttribute("aria-expanded") === "true"
    ) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const taken = snapshot.current;
    const position = positionOf(cell);
    // The control's own blur (its format check and echo) runs as the focus leaves it; the restored
    // value and the cleared message are written after it, so they are what remains.
    focusCell(position);
    if (taken !== null && taken.cell === cellKey(position)) {
      onChange(taken.rowId, taken.columnId, taken.value);
      onFormatError(cellName(taken.rowId, taken.columnId), null);
    }
  };
  const nextError = () => {
    const ids = invalidCells.map(fieldId);
    const at = ids.indexOf(document.activeElement?.id ?? "");
    document.getElementById(ids[(at + 1) % ids.length] ?? "")?.focus();
  };

  const renderControl = (
    column: LineColumn<Row>,
    row: Row,
    control: FieldControlProps,
    invalid: boolean,
  ): ReactNode => {
    const id = rowId(row);
    const value = column.value(row);
    const change = (next: string) => onChange(id, column.id, next);
    const disabled = column.disabled?.(row) === true;
    const formatError = (message: string | null) => onFormatError(control.name, message);
    if (disabled) {
      return (
        <input
          {...control}
          type="text"
          disabled
          value=""
          readOnly
          className={cn(controlClass(false), END_ALIGNED.has(column.kind) && "text-end")}
        />
      );
    }
    switch (column.kind) {
      case "combobox":
        return (
          <Combobox<string>
            control={control}
            options={column.options ?? []}
            value={value === "" ? null : value}
            onChange={(next) => change(next ?? "")}
            invalid={invalid}
          />
        );
      case "select":
        return (
          <select
            {...control}
            value={value}
            onChange={(event) => change(event.target.value)}
            className={controlClass(invalid)}
          >
            {value === "" ? <option value="">{t("common.form.select.placeholder")}</option> : null}
            {(column.options ?? []).map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        );
      case "date":
        return (
          <DateCell
            control={control}
            value={value}
            invalid={invalid}
            onChange={change}
            onFormatError={formatError}
          />
        );
      case "money":
        if (column.currency !== null && column.currency !== undefined) {
          return (
            <MoneyInput
              control={control}
              currency={column.currency}
              value={value}
              onChange={change}
              onFormatError={formatError}
              invalid={invalid}
            />
          );
        }
        return (
          <input
            {...control}
            type="text"
            inputMode="decimal"
            autoComplete="off"
            value={value}
            onChange={(event) => change(event.target.value)}
            className={cn(controlClass(invalid), "num text-end")}
          />
        );
      case "decimal":
        return (
          <input
            {...control}
            type="text"
            inputMode="decimal"
            autoComplete="off"
            value={value}
            onChange={(event) => change(event.target.value)}
            className={cn(controlClass(invalid), "num text-end")}
          />
        );
      case "text":
        return (
          <input
            {...control}
            type="text"
            autoComplete="off"
            value={value}
            onChange={(event) => change(event.target.value)}
            className={cn(
              controlClass(invalid),
              column.rowHeader === true && "font-mono text-mono",
            )}
          />
        );
    }
  };

  return (
    <section
      aria-labelledby={titleId}
      data-testid={testId}
      className="flex flex-col rounded-lg border border-hairline bg-surface"
    >
      <div className="flex min-h-[var(--control-h)] flex-wrap items-center gap-2 px-[var(--panel-pad)] py-2">
        <h2 id={titleId} className="text-title-sm text-fg-1">
          {title}
        </h2>
        <span className="num text-body-sm text-fg-3">
          {countLabel(rows.length, formatNumber(rows.length, { kind: "count" }))}
        </span>
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
        <Button
          id={fieldId(name)}
          variant="secondary"
          size="sm"
          icon={Plus}
          disabledReason={addDisabledReason}
          onClick={onAdd}
        >
          {addLabel}
        </Button>
      </div>
      {Object.hasOwn(errors, name) ? (
        <p className="flex items-start gap-1 px-[var(--panel-pad)] pb-2 text-body-sm text-negative-fg">
          <WarningCircle aria-hidden="true" className="mt-0.5 shrink-0" />
          {errors[name]}
        </p>
      ) : null}
      {/* The list of a combobox opened in a cell needs room below the last line. */}
      <div ref={scroller} className="group/lines overflow-x-auto">
        <table
          role="grid"
          aria-labelledby={titleId}
          aria-rowcount={rows.length + 1}
          aria-colcount={columns.length + 1}
          tabIndex={-1}
          onFocus={onFocus}
          onKeyDown={onKeyDown}
          onKeyDownCapture={onKeyDownCapture}
          className="w-max min-w-full border-separate border-spacing-0 text-grid text-fg-1"
        >
          <thead>
            <tr role="row" aria-rowindex={1}>
              {columns.map((column, index) => (
                <th
                  key={column.id}
                  role="columnheader"
                  scope="col"
                  aria-colindex={index + 1}
                  className={cn(
                    "h-[var(--header-row-h)] whitespace-nowrap border-b border-default bg-subtle px-2 text-body-sm font-medium text-fg-2",
                    column.width,
                    END_ALIGNED.has(column.kind) ? "text-end" : "text-start",
                    column.rowHeader === true &&
                      "sticky start-0 z-[var(--z-sticky)] border-e border-e-default",
                  )}
                >
                  {column.header}
                </th>
              ))}
              <th
                role="columnheader"
                scope="col"
                aria-colindex={columns.length + 1}
                className="sticky end-0 z-[var(--z-sticky)] w-10 min-w-10 border-b border-default bg-subtle"
              >
                <span className="sr-only">{t("common.lineEditor.actions")}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => {
              const id = rowId(row);
              const line = formatNumber(rowIndex + 1, { kind: "count" });
              const tabbable = (col: number) =>
                active.row === rowIndex && active.col === col ? 0 : -1;
              return (
                <tr key={id} role="row" aria-rowindex={rowIndex + 2}>
                  {columns.map((column, colIndex) => {
                    const cell = cellName(id, column.id);
                    const error = errors[cell] ?? null;
                    const invalid = error !== null;
                    const errorId = `${fieldId(cell)}-error`;
                    const control = cellControl(cell, errorId, invalid);
                    const disabled = column.disabled?.(row) === true;
                    const Cell = column.rowHeader === true ? "th" : "td";
                    return (
                      <Cell
                        key={column.id}
                        role={column.rowHeader === true ? "rowheader" : "gridcell"}
                        scope={column.rowHeader === true ? "row" : undefined}
                        aria-colindex={colIndex + 1}
                        aria-invalid={invalid ? true : undefined}
                        aria-describedby={invalid ? errorId : undefined}
                        aria-readonly={disabled ? true : undefined}
                        data-cell={cellKey({ row: rowIndex, col: colIndex })}
                        data-column={column.id}
                        tabIndex={tabbable(colIndex)}
                        className={cn(
                          "focus-inset border-b border-hairline p-1 text-start align-top font-normal",
                          column.rowHeader === true &&
                            "sticky start-0 z-[var(--z-sticky)] border-e border-e-default bg-surface",
                        )}
                      >
                        <label id={fieldLabelId(cell)} htmlFor={control.id} className="sr-only">
                          {t("common.lineEditor.cell", {
                            column: column.label ?? column.header,
                            line,
                          })}
                        </label>
                        {renderControl(column, row, control, invalid)}
                        {invalid ? (
                          <p
                            id={errorId}
                            className="mt-1 flex items-start gap-1 text-caption text-negative-fg"
                          >
                            <WarningCircle
                              aria-hidden="true"
                              size={12}
                              className="mt-0.5 shrink-0"
                            />
                            {error}
                          </p>
                        ) : null}
                      </Cell>
                    );
                  })}
                  <td
                    role="gridcell"
                    aria-colindex={columns.length + 1}
                    data-cell={cellKey({ row: rowIndex, col: lastCol })}
                    tabIndex={tabbable(lastCol)}
                    className="focus-inset sticky end-0 z-[var(--z-sticky)] border-b border-hairline bg-surface p-1 align-top"
                  >
                    <Button
                      variant="ghost"
                      icon={Trash}
                      tabIndex={-1}
                      aria-label={removeLabel(row, rowIndex)}
                      onClick={() => onRemove(id)}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {rows.length === 0 ? (
          <p className="px-[var(--panel-pad)] py-6 text-body-sm text-fg-2">{emptyText}</p>
        ) : null}
        <div
          aria-hidden="true"
          className="hidden h-80 group-has-[[aria-expanded=true]]/lines:block"
        />
      </div>
    </section>
  );
}
