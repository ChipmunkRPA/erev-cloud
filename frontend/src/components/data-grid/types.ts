// DataGrid contracts (DESIGN_SYSTEM DS-CMP-10 column types, saved view contents; docs/dev-guide.md DG-FE-07).
import type { ReactNode } from "react";

import type { ListPage } from "../../lib/api/lists";
import type { QueryKey } from "../../lib/api/query-keys";
import type { NumKind } from "../money/Num";

export type ColumnKind =
  | "identifier"
  | "text"
  | "money"
  | "number"
  | "date"
  | "timestamp"
  | "period"
  | "status"
  | "boolean"
  | "user"
  | "actions";

/** DS-CMP-10 default column widths in px. */
export const DEFAULT_WIDTH: Readonly<Record<ColumnKind, number>> = {
  identifier: 128,
  text: 160,
  money: 144,
  number: 112,
  date: 112,
  timestamp: 176,
  period: 96,
  status: 136,
  boolean: 72,
  user: 160,
  actions: 40,
};

export type EditOutcome = { readonly ok: true } | { readonly ok: false; readonly message: string };

export interface ColumnEdit<Row> {
  /** `decimal` keeps a string and validates against the row currency's minor unit. */
  readonly kind: "text" | "decimal" | "date";
  /** Resolves after the API answers; a refusal keeps the typed text in the cell. */
  readonly save: (row: Row, value: string) => Promise<EditOutcome>;
}

export interface GridColumn<Row> {
  readonly id: string;
  readonly header: string;
  readonly kind: ColumnKind;
  /** The raw value: copied by Mod C and shown by the default renderer. */
  readonly value: (row: Row) => string | null;
  readonly render?: ((row: Row) => ReactNode) | undefined;
  /** The API sort key; a column without one is not sortable. */
  readonly sortKey?: string | undefined;
  /** Money columns: the ISO 4217 code of the row. */
  readonly currency?: ((row: Row) => string) | undefined;
  /** The DS-FMT-12 Currency column of a mixed-currency grid: a totals row names its ISO code here (DS-CMP-10 item 7). */
  readonly currencyColumn?: boolean | undefined;
  readonly numberKind?: NumKind | undefined;
  /** Identifier columns: the record route. */
  readonly href?: ((row: Row) => string) | undefined;
  /** Editable cells of draft data; used only when the grid is `editable`. */
  readonly edit?: ColumnEdit<Row> | undefined;
  /** Computed cells: `E` opens the Explain panel for the row's figure (DS-CMP-15). */
  readonly explain?: ((row: Row) => void) | undefined;
  /** Drillable cells: Enter drills as a click on the cell's link does (SCREENS_B RV-09). */
  readonly activate?: ((row: Row) => void) | undefined;
  readonly width?: number | undefined;
}

/** Column order, visibility, widths and pinning: the column part of a saved view. */
export interface GridColumnState {
  readonly order: readonly string[];
  readonly hidden: readonly string[];
  readonly widths: Readonly<Record<string, number>>;
  readonly pinned: { readonly start: readonly string[]; readonly end: readonly string[] };
}

/** Every column in definition order; a leading identifier column is pinned to the start. */
export function initialColumnState<Row>(
  columns: readonly GridColumn<Row>[],
  hidden: readonly string[] = [],
): GridColumnState {
  const first = columns[0];
  return {
    order: columns.map((column) => column.id),
    hidden,
    widths: {},
    pinned: { start: first?.kind === "identifier" ? [first.id] : [], end: [] },
  };
}

export interface GridSource<Row> {
  /** The screen's list and filters; the grid appends the sort. */
  readonly queryKey: QueryKey;
  readonly fetchPage: (cursor: string | null, sort: string | null) => Promise<ListPage<Row>>;
}

export interface GridSelection {
  readonly ids: ReadonlySet<string>;
  /** "Select all <n> matching rows" was chosen. */
  readonly allMatching: boolean;
}

/** One totals row per currency; the API supplies the figures (DS-FMT-02). */
export interface GridTotalsRow {
  readonly key: string;
  readonly currency: string;
  readonly values: Readonly<Record<string, string>>;
}
