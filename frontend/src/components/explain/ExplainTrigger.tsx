// Explain trigger (DESIGN_SYSTEM DS-CMP-15, DS-CMP-26; docs/dev-guide.md DG-FE-15; REQ-UX-005). Every
// computed figure sits in `<ExplainTrigger figureRef>`: a button without visible chrome that shows a
// dotted underline and the Function icon on hover or focus, and opens the Explain panel on click, Enter
// or `E`. The figure reference names the API-R-49 node the panel loads. A figure the trace holds at no
// node of its own names a list of the host instead (`list`; SCREENS §6.3 list level, rev 1.21): the
// panel then shows the entries the API does explain.
import { createContext, type ReactNode, useContext, useRef } from "react";

import type { ExplainObjectTypeValue } from "../../lib/api/queries/explain";
import { t } from "../../lib/i18n/t";
import { Function as FunctionIcon } from "../icons/registry";

/** 04 §16.11 object types of `GET /explain/{object_type}/{id}/{measure}`. */
export type ExplainObjectType = ExplainObjectTypeValue;

export interface FigureRef {
  readonly objectType: ExplainObjectType;
  readonly id: string;
  /** The node measure name, for example `revenue_to_date`. */
  readonly measure: string;
  readonly periodKey?: string | undefined;
  readonly book?: string | undefined;
  /** The calculation trace of the figure on the page; the panel warns when the API returns another. */
  readonly calcTraceId?: string | undefined;
}

export interface ExplainRequest {
  readonly figure: FigureRef;
  /** The figure name, for example "Recognized revenue · Sep 2026". */
  readonly label: string;
  /** The context line: contract, obligation, book and entity. */
  readonly context?: string | undefined;
}

/** One entry of a list level: an amount the API explains on its own. */
export interface ExplainListRow {
  readonly id: string;
  /** The entry's name, for example "O1 · AVM-PLAT-100". */
  readonly label: string;
  /** The API amount and its currency. */
  readonly amount: string;
  readonly currency: string;
  /**
   * The entry's own explanation and the name of the button that opens it, for example "Explain O1";
   * absent when the API links none.
   */
  readonly explain?: { readonly request: ExplainRequest; readonly label: string } | undefined;
}

/**
 * A level of the panel without a figure of its own (SCREENS §6.3 list level, rev 1.21): the trace holds
 * no node for the value, so the panel lists the entries that do have one. The host owns the content and
 * keeps it current; the panel prints what it is given and adds no money (DG-FE-08).
 */
export interface ExplainList {
  /** The level's name, for example "Recognized to date · Sep 2026". */
  readonly label: string;
  /** The value above the table: the API's figure, which is the total. */
  readonly value: string;
  readonly currency: string;
  /** The context line: contract, book and entity. */
  readonly context?: string | undefined;
  /** The section heading and table name, for example "By obligation". */
  readonly caption: string;
  /** The column headers of the entry and of its amount. */
  readonly columns: { readonly entry: string; readonly amount: string };
  /** The entries; undefined while the host reads them. */
  readonly rows: readonly ExplainListRow[] | undefined;
  /** The host's read of the entries failed: what to say and how to repeat it. */
  readonly error?: { readonly title: string; readonly onRetry: () => void } | undefined;
  /** Shown in place of the table when there is no entry. */
  readonly empty: string;
  /** A sentence above the table that says what the table shows. */
  readonly intro?: string | undefined;
  /** Sentences below the table; a node, so that the host reads what decides them only when shown. */
  readonly notes?: ReactNode;
}

export interface ExplainActions {
  /** Opens the panel for a figure; `trigger` receives focus when the panel closes. */
  readonly open: (request: ExplainRequest, trigger: HTMLElement | null) => void;
  /** Opens the panel at the list level the host provides under `list`. */
  readonly openList: (list: string, trigger: HTMLElement | null) => void;
}

export const ExplainContext = createContext<ExplainActions | null>(null);

export function useExplain(): ExplainActions {
  const actions = useContext(ExplainContext);
  if (actions === null) {
    throw new Error("Explain triggers need an ExplainProvider (DS-CMP-15)");
  }
  return actions;
}

/** What the trigger opens: a figure, or a list level of the host by its id. */
export type ExplainTarget =
  | { readonly figureRef: FigureRef; readonly list?: undefined }
  | { readonly list: string; readonly figureRef?: undefined };

export type ExplainTriggerProps = ExplainTarget & {
  /** The figure name, for example "Recognized revenue · Sep 2026". */
  readonly label: string;
  /** The context line of the panel: contract, obligation, book and entity. */
  readonly context?: string | undefined;
  /** The value as spoken, with its currency code, for example "USD 55,440.00". */
  readonly valueText: string;
  /** The formatted figure. */
  readonly children: ReactNode;
  /**
   * -1 inside a DataGrid cell, so the grid keeps one tab stop (DS-A11Y-03); the cell's `E` opens the
   * panel through the column's `explain`.
   */
  readonly tabIndex?: number | undefined;
};

export function ExplainTrigger({
  figureRef,
  list,
  label,
  context,
  valueText,
  children,
  tabIndex,
}: ExplainTriggerProps) {
  const { open, openList } = useExplain();
  const button = useRef<HTMLButtonElement>(null);
  const request = () => {
    if (figureRef === undefined) {
      openList(list, button.current);
    } else {
      open({ figure: figureRef, label, context }, button.current);
    }
  };
  return (
    <button
      ref={button}
      type="button"
      tabIndex={tabIndex}
      aria-label={t("common.explain.trigger", { label, value: valueText })}
      onClick={request}
      onKeyDown={(event) => {
        if (
          (event.key === "e" || event.key === "E") &&
          !event.altKey &&
          !event.ctrlKey &&
          !event.metaKey
        ) {
          event.preventDefault();
          request();
        }
      }}
      className="group inline-flex items-center gap-1 rounded-sm decoration-control decoration-dotted underline-offset-4 hover:underline focus-visible:underline"
    >
      {children}
      <FunctionIcon
        aria-hidden="true"
        className="invisible shrink-0 text-fg-3 group-hover:visible group-focus-visible:visible"
      />
    </button>
  );
}
