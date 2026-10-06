// Grid copy text (DESIGN_SYSTEM DS-CMP-10 "Copy"; 03 REQ-SEC-011; 05 UPL-20, THR-13). `Mod C` writes
// tab-separated values that a spreadsheet reads on paste, so a copied cell follows the rule of the
// server's CSV and XLSX writers (`domain/reports/outputs/sanitise.py`): text that begins with `=`, `+`,
// `-`, `@`, a tab or a carriage return gets a leading apostrophe and is shown, not evaluated. A money
// or number cell that holds a plain decimal stays as it is, so a negative amount pastes as a number.
// A tab or line break inside a cell becomes a space: it would otherwise start a new cell on paste,
// where the rest of the text is read on its own.
import type { ColumnKind } from "./types";

const FORMULA_TRIGGER = /^[=+\-@\t\r]/;
const PLAIN_DECIMAL = /^-?\d+(\.\d+)?$/;
const CELL_BREAK = /[\t\r\n]+/g;
const NUMERIC_KINDS: ReadonlySet<ColumnKind> = new Set<ColumnKind>(["money", "number"]);

/** The clipboard text of one cell of a column of `kind`. */
export function clipboardCell(text: string, kind: ColumnKind): string {
  const numeric = NUMERIC_KINDS.has(kind) && PLAIN_DECIMAL.test(text);
  const guarded = !numeric && FORMULA_TRIGGER.test(text) ? `'${text}` : text;
  return guarded.replace(CELL_BREAK, " ");
}
