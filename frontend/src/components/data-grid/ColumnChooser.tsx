// Column chooser (DESIGN_SYSTEM DS-CMP-10 "Column chooser"; WCAG 2.2 SC 2.5.7): a docked non-modal popover
// with search, visibility checkboxes and the buttons "Move up" and "Move down", which reorder columns
// without dragging. "Reset to view default" restores the saved view's columns. Esc closes the popover
// and returns focus to the trigger; a press outside closes it.
import { useEffect, useId, useRef, useState } from "react";

import { t } from "../../lib/i18n/t";
import { controlClass } from "../form/Field";
import { CaretDown, CaretUp, Columns } from "../icons/registry";
import { Button } from "../ui/Button";
import { focusableWithin } from "../ui/dialog";

export interface ChooserColumn {
  readonly id: string;
  readonly label: string;
}

export interface ColumnLayout {
  readonly order: readonly string[];
  readonly hidden: readonly string[];
}

export interface ColumnChooserProps {
  readonly columns: readonly ChooserColumn[];
  readonly layout: ColumnLayout;
  /** The active saved view's columns, or the screen default. */
  readonly defaultLayout: ColumnLayout;
  readonly onChange: (layout: ColumnLayout) => void;
}

export function ColumnChooser({ columns, layout, defaultLayout, onChange }: ColumnChooserProps) {
  const panelId = useId();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const root = useRef<HTMLSpanElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  const labels = new Map(columns.map((column) => [column.id, column.label]));
  const order = [
    ...layout.order.filter((id) => labels.has(id)),
    ...columns.map((column) => column.id).filter((id) => !layout.order.includes(id)),
  ];

  useEffect(() => {
    const element = panel.current;
    if (!open || element === null) {
      return undefined;
    }
    focusableWithin(element)[0]?.focus();
    const close = (returnFocus: boolean) => {
      setOpen(false);
      setSearch("");
      if (returnFocus) {
        trigger.current?.focus();
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        close(true);
      }
    };
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && root.current?.contains(event.target) !== true) {
        close(false);
      }
    };
    element.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      element.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [open]);

  const move = (id: string, step: -1 | 1) => {
    const index = order.indexOf(id);
    const target = index + step;
    const other = order[target];
    if (index < 0 || other === undefined) {
      return;
    }
    const next = [...order];
    next[target] = id;
    next[index] = other;
    onChange({ order: next, hidden: layout.hidden });
  };

  const toggle = (id: string) =>
    onChange({
      order,
      hidden: layout.hidden.includes(id)
        ? layout.hidden.filter((hidden) => hidden !== id)
        : [...layout.hidden, id],
    });

  const query = search.trim().toLocaleLowerCase();
  const shown = order.filter((id) => (labels.get(id) ?? id).toLocaleLowerCase().includes(query));

  return (
    <span ref={root} className="relative inline-flex">
      <Button
        ref={trigger}
        variant="ghost"
        icon={Columns}
        aria-label={t("common.grid.columns.label")}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => {
          setOpen((current) => !current);
          setSearch("");
        }}
      />
      {open ? (
        <div
          ref={panel}
          id={panelId}
          role="dialog"
          aria-label={t("common.grid.columns.label")}
          tabIndex={-1}
          className="absolute end-0 top-full z-[var(--z-popover)] mt-1 flex w-72 flex-col gap-2 rounded-lg border border-hairline bg-raised p-2 shadow-popover"
        >
          <input
            type="search"
            aria-label={t("common.grid.columns.search")}
            placeholder={t("common.grid.columns.search")}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className={controlClass(false)}
          />
          <div className="flex max-h-80 flex-col overflow-y-auto">
            {shown.map((id) => {
              const index = order.indexOf(id);
              const labelId = `${panelId}-${id}`;
              return (
                <div
                  key={id}
                  role="group"
                  aria-labelledby={labelId}
                  className="flex h-[var(--row-h)] shrink-0 items-center gap-2 px-1"
                >
                  <input
                    id={`${labelId}-visible`}
                    type="checkbox"
                    checked={!layout.hidden.includes(id)}
                    onChange={() => toggle(id)}
                  />
                  <label
                    id={labelId}
                    htmlFor={`${labelId}-visible`}
                    className="min-w-0 flex-1 truncate text-body-sm text-fg-1"
                  >
                    {labels.get(id)}
                  </label>
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={CaretUp}
                    aria-label={t("common.grid.columns.moveUp")}
                    disabledReason={index === 0 ? t("common.grid.columns.first") : undefined}
                    onClick={() => move(id, -1)}
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={CaretDown}
                    aria-label={t("common.grid.columns.moveDown")}
                    disabledReason={
                      index === order.length - 1 ? t("common.grid.columns.last") : undefined
                    }
                    onClick={() => move(id, 1)}
                  />
                </div>
              );
            })}
          </div>
          <div className="flex justify-end border-t border-hairline pt-2">
            <Button variant="link" size="sm" onClick={() => onChange(defaultLayout)}>
              {t("common.grid.columns.reset")}
            </Button>
          </div>
        </div>
      ) : null}
    </span>
  );
}
