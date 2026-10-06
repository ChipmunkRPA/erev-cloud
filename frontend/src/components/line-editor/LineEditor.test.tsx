// @vitest-environment jsdom
// Line editor (DESIGN_SYSTEM DS-CMP-10 inline editing and keyboard table, DS-CMP-21, DS-A11Y-11; APG Grid;
// DS-VER-04): one tab stop with a roving tabindex; cell navigation; Enter, F2 and a printable character
// start editing; Enter, Tab and F2 commit and move; Esc restores the value; a wrong cell carries
// `aria-invalid` with its message; the toolbar counts the lines and the errors.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { registerLiveRegions } from "../../lib/a11y/announce";
import { registerCurrencies } from "../../lib/format";
import { type LineColumn, LineEditor } from "./LineEditor";

interface Line {
  readonly id: string;
  readonly key: string;
  readonly product: string;
  readonly quantity: string;
  readonly price: string;
  readonly start: string;
  readonly scope: string;
  readonly excluded: string;
}

const LINES: readonly Line[] = [
  {
    id: "l1",
    key: "O1",
    product: "AVM-PLAT-100",
    quantity: "12",
    price: "1,000.00",
    start: "01 Jan 2026",
    scope: "IN",
    excluded: "",
  },
  {
    id: "l2",
    key: "O2",
    product: "",
    quantity: "3",
    price: "250.00",
    start: "",
    scope: "LEASE",
    excluded: "40.00",
  },
];

const COLUMNS: readonly LineColumn<Line>[] = [
  {
    id: "key",
    header: "Obligation key",
    kind: "text",
    value: (line) => line.key,
    rowHeader: true,
    width: "w-32",
  },
  {
    id: "product",
    header: "Product",
    kind: "combobox",
    value: (line) => line.product,
    options: [
      { value: "AVM-PLAT-100", label: "AVM-PLAT-100 · Platform" },
      { value: "AVM-IMPL-PLUS", label: "AVM-IMPL-PLUS · Implementation" },
    ],
    width: "w-72",
  },
  {
    id: "quantity",
    header: "Quantity",
    kind: "decimal",
    value: (line) => line.quantity,
    width: "w-28",
  },
  {
    id: "price",
    header: "Total price (USD)",
    label: "Total price",
    kind: "money",
    currency: "USD",
    value: (line) => line.price,
    width: "w-48",
  },
  { id: "start", header: "Start date", kind: "date", value: (line) => line.start, width: "w-36" },
  {
    id: "scope",
    header: "Scope",
    kind: "select",
    value: (line) => line.scope,
    options: [
      { value: "IN", label: "In scope (ASC 606)" },
      { value: "LEASE", label: "Lease (ASC 842)" },
    ],
    width: "w-64",
  },
  {
    id: "excluded",
    header: "Out-of-scope amount (USD)",
    label: "Out-of-scope amount",
    kind: "money",
    currency: "USD",
    value: (line) => line.excluded,
    disabled: (line) => line.scope === "IN",
    width: "w-48",
  },
];

const cellName = (rowId: string, columnId: string) => `line-${rowId}-${columnId}`;

interface HarnessProps {
  readonly errors?: Readonly<Record<string, string>>;
  readonly onFormatError?: (name: string, message: string | null) => void;
  readonly onRemove?: (rowId: string) => void;
  readonly rows?: readonly Line[];
}

function Harness({
  errors = {},
  onFormatError = () => undefined,
  onRemove,
  rows = LINES,
}: HarnessProps) {
  const [lines, setLines] = useState(rows);
  return (
    <>
      <button type="button">Before</button>
      <LineEditor<Line>
        title="Contract lines"
        countLabel={(count, formatted) => `${formatted} ${count === 1 ? "line" : "lines"}`}
        columns={COLUMNS}
        rows={lines}
        rowId={(line) => line.id}
        name="lines"
        cellName={cellName}
        errors={errors}
        onChange={(rowId, columnId, value) =>
          setLines((current) =>
            current.map((line) => (line.id === rowId ? { ...line, [columnId]: value } : line)),
          )
        }
        onFormatError={onFormatError}
        addLabel="Add line"
        onAdd={() => undefined}
        removeLabel={(line) => `Remove line ${line.key}`}
        onRemove={
          onRemove ??
          ((rowId) => setLines((current) => current.filter((line) => line.id !== rowId)))
        }
        emptyText="No lines."
        testId="SF-03-grid-lines"
      />
      <button type="button">After</button>
    </>
  );
}

beforeAll(() => {
  registerCurrencies([{ code: "USD", minor_unit: 2 }]);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function grid(): HTMLElement {
  return screen.getByRole("grid", { name: "Contract lines" });
}

/** The cell at a 0-based row and column of the body. */
function cellAt(row: number, col: number): HTMLElement {
  const cell = grid().querySelector<HTMLElement>(`[data-cell="${String(row)}:${String(col)}"]`);
  if (cell === null) {
    throw new Error(`No cell ${String(row)}:${String(col)}`);
  }
  return cell;
}

function focusCell(row: number, col: number): HTMLElement {
  const cell = cellAt(row, col);
  act(() => cell.focus());
  return cell;
}

function press(key: string, init: KeyboardEventInit = {}): boolean {
  const target = document.activeElement;
  if (target === null) {
    throw new Error("Nothing has focus");
  }
  // False when the key's default action was prevented.
  return fireEvent.keyDown(target, { key, ...init });
}

describe("line editor structure", () => {
  it("is a named grid with row and column counts, a row header column and one tab stop", () => {
    render(<Harness />);

    const table = grid();
    expect(screen.getByTestId("SF-03-grid-lines").contains(table)).toBe(true);
    expect(screen.getByRole("heading", { level: 2, name: "Contract lines" })).toBeTruthy();
    expect(screen.getByText("2 lines")).toBeTruthy();
    expect(table.getAttribute("aria-rowcount")).toBe("3");
    expect(table.getAttribute("aria-colcount")).toBe("8");
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual([
      "Obligation key",
      "Product",
      "Quantity",
      "Total price (USD)",
      "Start date",
      "Scope",
      "Out-of-scope amount (USD)",
      "Actions",
    ]);
    expect(within(table).getAllByRole("rowheader")).toHaveLength(2);
    expect(within(table).getAllByRole("row")[1]?.getAttribute("aria-rowindex")).toBe("2");
    expect(cellAt(0, 2).getAttribute("aria-colindex")).toBe("3");

    // Roving tabindex: the first cell is the grid's one tab stop; no control is in the tab order.
    const stops = Array.from(table.querySelectorAll<HTMLElement>("[tabindex='0']"));
    expect(stops).toEqual([cellAt(0, 0)]);
    for (const control of table.querySelectorAll<HTMLElement>(
      "input:not([type='hidden']), select, button",
    )) {
      expect(control.tabIndex).toBe(-1);
    }
    // Each control is named by its column and line.
    expect(screen.getByRole("textbox", { name: "Quantity, line 2" })).toBeTruthy();
    expect(screen.getByRole("combobox", { name: "Product, line 1" })).toBeTruthy();
    expect(screen.getByRole("combobox", { name: "Scope, line 2" }).tagName).toBe("SELECT");
    expect(screen.getByRole("button", { name: "Remove line O2" })).toBeTruthy();
    // A cell that takes no input in its row is read-only to the grid.
    expect(cellAt(0, 6).getAttribute("aria-readonly")).toBe("true");
    expect(cellAt(1, 6).hasAttribute("aria-readonly")).toBe(false);
  });

  it("shows no row and the empty text while the form holds no line", () => {
    render(<Harness rows={[]} />);

    expect(screen.getByText("0 lines")).toBeTruthy();
    expect(screen.getByText("No lines.")).toBeTruthy();
    expect(within(grid()).getAllByRole("row")).toHaveLength(1);
  });
});

describe("line editor cell navigation", () => {
  it("arrows, Home and End, with Mod the grid's corners, Page Down by rows", () => {
    render(<Harness />);
    focusCell(0, 0);

    expect(press("ArrowRight")).toBe(false);
    expect(document.activeElement).toBe(cellAt(0, 1));
    // The roving tab stop follows the focused cell.
    expect(cellAt(0, 1).tabIndex).toBe(0);
    expect(cellAt(0, 0).tabIndex).toBe(-1);
    press("ArrowDown");
    expect(document.activeElement).toBe(cellAt(1, 1));
    press("ArrowDown");
    expect(document.activeElement).toBe(cellAt(1, 1));
    press("ArrowLeft");
    press("ArrowLeft");
    expect(document.activeElement).toBe(cellAt(1, 0));
    press("End");
    expect(document.activeElement).toBe(cellAt(1, 7));
    press("Home");
    expect(document.activeElement).toBe(cellAt(1, 0));
    press("Home", { ctrlKey: true });
    expect(document.activeElement).toBe(cellAt(0, 0));
    press("End", { metaKey: true });
    expect(document.activeElement).toBe(cellAt(1, 7));
    press("PageUp");
    expect(document.activeElement).toBe(cellAt(0, 7));
    press("PageDown");
    expect(document.activeElement).toBe(cellAt(1, 7));
  });

  it("mirrors Left and Right in a right-to-left context", () => {
    render(
      <div dir="rtl">
        <Harness />
      </div>,
    );
    focusCell(0, 1);

    press("ArrowLeft");
    expect(document.activeElement).toBe(cellAt(0, 2));
    press("ArrowRight");
    expect(document.activeElement).toBe(cellAt(0, 1));
  });

  it("Tab on a cell is left to the browser, so the grid is entered and left in one step", () => {
    render(<Harness />);
    focusCell(1, 3);

    expect(press("Tab")).toBe(true);
    expect(press("Tab", { shiftKey: true })).toBe(true);
    expect(document.activeElement).toBe(cellAt(1, 3));
  });

  it("Mod C copies the value of the focused cell", () => {
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    render(<Harness />);
    focusCell(0, 3);

    expect(press("c", { metaKey: true })).toBe(false);
    expect(writeText).toHaveBeenCalledWith("1,000.00");
  });
});

describe("line editor editing", () => {
  it("Enter and F2 start editing; Enter commits and moves down; F2 finishes", () => {
    const spoken: string[] = [];
    const unregister = registerLiveRegions(
      (message) => spoken.push(message),
      () => undefined,
    );
    render(<Harness />);
    focusCell(0, 2);

    expect(press("Enter")).toBe(false);
    const quantity = screen.getByRole("textbox", { name: "Quantity, line 1" }) as HTMLInputElement;
    expect(document.activeElement).toBe(quantity);
    // The value is selected, so typing replaces it.
    expect([quantity.selectionStart, quantity.selectionEnd]).toEqual([0, 2]);
    expect(spoken).toEqual(["Editing Quantity, 12"]);

    fireEvent.change(quantity, { target: { value: "15" } });
    expect(press("Enter")).toBe(false);
    expect(document.activeElement).toBe(cellAt(1, 2));
    expect(quantity.value).toBe("15");

    press("F2");
    expect(document.activeElement).toBe(screen.getByRole("textbox", { name: "Quantity, line 2" }));
    press("F2");
    expect(document.activeElement).toBe(cellAt(1, 2));
    // Enter in the last row commits and stays on the cell.
    press("Enter");
    press("Enter");
    expect(document.activeElement).toBe(cellAt(1, 2));
    unregister();
  });

  it("a printable character starts editing without being swallowed", () => {
    render(<Harness />);
    focusCell(1, 2);

    // Not prevented: the browser types the character into the control, which now has the focus.
    expect(press("7")).toBe(true);
    const quantity = screen.getByRole("textbox", { name: "Quantity, line 2" }) as HTMLInputElement;
    expect(document.activeElement).toBe(quantity);
    expect([quantity.selectionStart, quantity.selectionEnd]).toEqual([0, 1]);

    // A modified key and a cell without input start nothing.
    focusCell(0, 6);
    expect(press("7")).toBe(true);
    expect(document.activeElement).toBe(cellAt(0, 6));
    press("Enter");
    expect(document.activeElement).toBe(cellAt(0, 6));
  });

  it("Tab commits and moves to the next cell, across rows, and leaves the grid at its ends", () => {
    render(<Harness />);
    focusCell(0, 5);
    press("Enter");
    expect(document.activeElement).toBe(screen.getByRole("combobox", { name: "Scope, line 1" }));

    expect(press("Tab")).toBe(false);
    expect(document.activeElement).toBe(cellAt(0, 6));
    // From the remove button of a row, Tab reaches the first cell of the next row.
    act(() => screen.getByRole("button", { name: "Remove line O1" }).focus());
    expect(press("Tab")).toBe(false);
    expect(document.activeElement).toBe(cellAt(1, 0));
    // Shift+Tab from the first control of a row reaches the last cell of the row before.
    press("Enter");
    expect(press("Tab", { shiftKey: true })).toBe(false);
    expect(document.activeElement).toBe(cellAt(0, 7));

    // At the grid's ends the key is the browser's.
    act(() => screen.getByRole("button", { name: "Remove line O2" }).focus());
    expect(press("Tab")).toBe(true);
    act(() => screen.getByRole("textbox", { name: "Obligation key, line 1" }).focus());
    expect(press("Tab", { shiftKey: true })).toBe(true);
  });

  it("Esc restores the value the cell had and returns to the cell", () => {
    const onFormatError = vi.fn();
    render(<Harness onFormatError={onFormatError} />);
    focusCell(0, 3);
    press("Enter");
    const price = screen.getByRole("textbox", { name: "Total price, line 1" }) as HTMLInputElement;
    fireEvent.change(price, { target: { value: "9,999.999" } });
    expect(price.value).toBe("9,999.999");

    expect(press("Escape")).toBe(false);
    expect(price.value).toBe("1,000.00");
    expect(document.activeElement).toBe(cellAt(0, 3));
    // The control's blur reported the amount it could not read; the cancelled edit clears it after.
    expect(onFormatError.mock.calls).toEqual([
      ["line-l1-price", "Enter at most 2 decimal places."],
      ["line-l1-price", null],
    ]);

    // An amount the control would echo on blur is restored as well.
    press("F2");
    fireEvent.change(price, { target: { value: "2000" } });
    press("Escape");
    expect(price.value).toBe("1,000.00");
  });

  it("a combobox keeps Esc and Enter while its list is open", () => {
    render(<Harness />);
    focusCell(1, 1);
    press("Enter");
    const product = screen.getByRole("combobox", { name: "Product, line 2" }) as HTMLInputElement;
    fireEvent.change(product, { target: { value: "IMPL" } });
    expect(product.getAttribute("aria-expanded")).toBe("true");

    // Esc closes the list and the focus stays in the control.
    press("Escape");
    expect(product.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(product);

    // Enter picks the option; the next Enter commits and keeps the last row.
    fireEvent.change(product, { target: { value: "AVM-IMPL" } });
    press("Enter");
    expect(product.value).toBe("AVM-IMPL-PLUS · Implementation");
    expect(document.activeElement).toBe(product);
    press("Enter");
    expect(document.activeElement).toBe(cellAt(1, 1));

    // Esc with the list closed restores the product the cell had.
    press("Enter");
    fireEvent.change(product, { target: { value: "PLAT" } });
    press("Enter");
    expect(product.value).toBe("AVM-PLAT-100 · Platform");
    press("Escape");
    expect(document.activeElement).toBe(cellAt(1, 1));
    expect(product.value).toBe("AVM-IMPL-PLUS · Implementation");
  });

  it("a date cell echoes DS-FMT-16 on blur and reports a date it cannot read", () => {
    const onFormatError = vi.fn();
    render(<Harness onFormatError={onFormatError} />);
    const start = screen.getByRole("textbox", { name: "Start date, line 2" }) as HTMLInputElement;

    fireEvent.change(start, { target: { value: "2026-03-01" } });
    fireEvent.blur(start);
    expect(start.value).toBe("01 Mar 2026");
    expect(onFormatError).toHaveBeenLastCalledWith("line-l2-start", null);

    fireEvent.change(start, { target: { value: "31 Feb 2026" } });
    fireEvent.blur(start);
    expect(start.value).toBe("31 Feb 2026");
    expect(onFormatError).toHaveBeenLastCalledWith(
      "line-l2-start",
      "Enter a date such as 07 Sep 2026.",
    );
  });

  it("Enter or Space on the remove cell removes the line", () => {
    const onRemove = vi.fn();
    render(<Harness onRemove={onRemove} />);
    focusCell(1, 7);

    expect(press("Enter")).toBe(false);
    expect(onRemove).toHaveBeenLastCalledWith("l2");
    focusCell(0, 7);
    expect(press(" ")).toBe(false);
    expect(onRemove).toHaveBeenLastCalledWith("l1");
  });
});

describe("line editor errors", () => {
  it("marks a wrong cell, shows its message and steps through the errors", () => {
    render(
      <Harness
        errors={{
          "line-l1-start": "Enter a date such as 07 Sep 2026.",
          "line-l2-key": "Obligation key O1 is used twice.",
          lines: "Add at least one line.",
        }}
      />,
    );

    const start = screen.getByRole("textbox", { name: "Start date, line 1" });
    expect(start.getAttribute("aria-invalid")).toBe("true");
    expect(document.getElementById(start.getAttribute("aria-describedby") ?? "")?.textContent).toBe(
      "Enter a date such as 07 Sep 2026.",
    );
    // The cell carries the same state for a reader moving by cell.
    expect(cellAt(0, 4).getAttribute("aria-invalid")).toBe("true");
    expect(cellAt(0, 4).getAttribute("aria-describedby")).toBe(
      start.getAttribute("aria-describedby"),
    );
    expect(cellAt(0, 3).hasAttribute("aria-invalid")).toBe(false);
    // The grid's own message and the count of wrong cells.
    expect(screen.getByText("Add at least one line.")).toBeTruthy();
    expect(screen.getByText("2 errors")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Next error" }));
    expect(document.activeElement).toBe(start);
    fireEvent.click(screen.getByRole("button", { name: "Next error" }));
    expect(document.activeElement).toBe(
      screen.getByRole("textbox", { name: "Obligation key, line 2" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Next error" }));
    expect(document.activeElement).toBe(start);
  });

  it("the add button states why no further line can be added", () => {
    render(
      <LineEditor<Line>
        title="Contract lines"
        countLabel={(_, formatted) => `${formatted} lines`}
        columns={COLUMNS}
        rows={LINES}
        rowId={(line) => line.id}
        name="lines"
        cellName={cellName}
        errors={{}}
        onChange={() => undefined}
        onFormatError={() => undefined}
        addLabel="Add line"
        addDisabledReason="A contract holds at most 500 lines."
        onAdd={() => {
          throw new Error("An unavailable button was pressed");
        }}
        removeLabel={(line) => `Remove line ${line.key}`}
        onRemove={() => undefined}
        emptyText="No lines."
      />,
    );

    const add = screen.getByRole("button", { name: "Add line" });
    expect(add.getAttribute("aria-disabled")).toBe("true");
    expect(add.id).toBe("field-lines");
    fireEvent.click(add);
  });
});
