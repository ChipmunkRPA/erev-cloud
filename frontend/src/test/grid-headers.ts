// A grid column must be at least as wide as its header and its values need (DS-CMP-10, DS-AP-10). A header
// cell holds its label, the cell padding, the column menu button and, for a sortable column, the sort
// mark; a column narrower than that cuts its label, which a text test does not see. The e2e rows
// measure the rendered boxes (`clippedBoxes`); jsdom has no layout, so a suite estimates the room
// from the label's length. Found on the bulk approval grid, whose 88 px "Currency" column left its
// label 44 of the 58 px it needs (make e2e on main 5c2edff7).
import { DEFAULT_WIDTH, type GridColumn } from "../components/data-grid/types";

/** The cell's inline padding (24 px) and the column menu button (20 px). */
export const HEADER_CHROME_PX = 44;
/** The sort mark of a sorted column and its gap. */
export const SORT_MARK_PX = 16;
/** An upper estimate of a character of the header face (text-body-sm, medium). */
export const HEADER_CHARACTER_PX = 7.5;
/**
 * A DS-FMT-17 instant, "01 Oct 2026 06:42 UTC", with the cell padding: 186 px as the e2e row of the
 * report run register measured it ("(186 > 176)" at the kit's default width), on the 8 px grid.
 */
export const TIMESTAMP_CELL_PX = 192;

/** The width a column needs for its header, sorted where it can be. */
export function headerWidth(header: string, sortable: boolean): number {
  return (
    HEADER_CHROME_PX +
    Math.ceil(header.length * HEADER_CHARACTER_PX) +
    (sortable ? SORT_MARK_PX : 0)
  );
}

/** The columns narrower than their header needs, as "<header> (<width> < <needed>)". */
export function narrowColumns<Row>(columns: readonly GridColumn<Row>[]): readonly string[] {
  return columns.flatMap((column) => {
    const width = column.width ?? DEFAULT_WIDTH[column.kind];
    const needed = Math.max(
      headerWidth(column.header, column.sortKey !== undefined),
      column.kind === "timestamp" ? TIMESTAMP_CELL_PX : 0,
    );
    return width < needed ? [`${column.header} (${String(width)} < ${String(needed)})`] : [];
  });
}
