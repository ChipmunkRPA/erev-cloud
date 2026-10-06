// Cell renderers (DESIGN_SYSTEM DS-CMP-10 column types; DS-FMT-04, DS-FMT-16, DS-FMT-17, DS-FMT-19,
// DS-FMT-23). Identifiers are mono links with a dotted underline; amounts and numbers align to the end;
// text truncates.
import type { ReactNode } from "react";
import { Link } from "react-router";

import { formatDate, formatPeriod, formatTimestamp } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { Money } from "../money/Money";
import { NoValue, Num } from "../money/Num";
import type { ColumnKind, GridColumn } from "./types";

export const END_ALIGNED: ReadonlySet<ColumnKind> = new Set(["money", "number", "actions"]);

export interface CellContentProps<Row> {
  readonly column: GridColumn<Row>;
  readonly row: Row;
}

export function CellContent<Row>({ column, row }: CellContentProps<Row>): ReactNode {
  if (column.render !== undefined) {
    return column.render(row);
  }
  const value = column.value(row);
  if (value === null) {
    return <NoValue />;
  }
  switch (column.kind) {
    case "identifier": {
      const href = column.href?.(row);
      return href === undefined ? (
        <span className="font-mono text-mono-sm text-fg-1">{value}</span>
      ) : (
        <Link
          to={href}
          tabIndex={-1}
          className="font-mono text-mono-sm text-fg-1 underline decoration-control decoration-dotted underline-offset-3 hover:decoration-fg-1 hover:decoration-solid"
        >
          {value}
        </Link>
      );
    }
    case "money": {
      const currency = column.currency?.(row);
      return currency === undefined ? (
        <Num value={value} kind="quantity" />
      ) : (
        <Money value={value} currency={currency} variant="cell" />
      );
    }
    case "number":
      return <Num value={value} kind={column.numberKind ?? "quantity"} />;
    case "date":
      return <span className="num">{formatDate(value)}</span>;
    case "timestamp":
      return <span className="num">{formatTimestamp(value)}</span>;
    case "period":
      return <span className="num">{formatPeriod(value)}</span>;
    case "boolean":
      return t(value === "true" ? "common.grid.yes" : "common.grid.no");
    case "text":
    case "status":
    case "user":
    case "actions":
      return (
        <span className="truncate" title={value}>
          {value}
        </span>
      );
  }
}
