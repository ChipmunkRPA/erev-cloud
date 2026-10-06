// Select (DESIGN_SYSTEM DS-CMP-21; APG Select-Only Combobox), for up to 10 options. Down, Up, Enter or
// Space opens; Up and Down move; Home and End; type-ahead; Enter, Space or Tab picks; Esc closes. A
// disabled select shows its value, keeps focus through aria-disabled and opens for no key or click;
// the page states the reason beside the fields it makes unavailable.
import { type KeyboardEvent, type ReactNode, useRef, useState } from "react";

import { t } from "../../lib/i18n/t";
import { CaretDown } from "../icons/registry";
import { cn } from "../ui/cn";
import { controlClass, type FieldControlProps, fieldLabelId } from "./Field";
import { type ListOption, Listbox, optionId } from "./Listbox";

export interface SelectProps<T extends string> {
  readonly control: FieldControlProps;
  readonly options: readonly ListOption<T>[];
  readonly value: T | null;
  readonly onChange: (value: T) => void;
  readonly placeholder?: string | undefined;
  readonly invalid?: boolean;
  /** DS-CMP-21 "Disabled": the value is shown and cannot be changed. */
  readonly disabled?: boolean;
  readonly renderExtra?: ((option: ListOption<T>) => ReactNode) | undefined;
}

export const TYPEAHEAD_RESET_MS = 500;

export function Select<T extends string>({
  control,
  options,
  value,
  onChange,
  placeholder,
  invalid = false,
  disabled = false,
  renderExtra,
}: SelectProps<T>) {
  const { name, id, ...aria } = control;
  const listId = `${id}-listbox`;
  const selectedIndex = options.findIndex((option) => option.value === value);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const search = useRef({ text: "", at: 0 });
  const last = options.length - 1;

  const show = (index: number) => {
    setActive(Math.min(Math.max(index, 0), last));
    setOpen(true);
  };
  const pick = (index: number) => {
    const option = options[index];
    if (option !== undefined) {
      onChange(option.value);
    }
    setOpen(false);
  };
  const typeahead = (key: string) => {
    const now = Date.now();
    const text = now - search.current.at < TYPEAHEAD_RESET_MS ? search.current.text + key : key;
    search.current = { text, at: now };
    const lower = text.toLocaleLowerCase();
    const start = open ? active : Math.max(selectedIndex, 0);
    for (let step = lower.length === 1 ? 1 : 0; step <= options.length; step += 1) {
      const index = (start + step) % options.length;
      if (options[index]?.label.toLocaleLowerCase().startsWith(lower) === true) {
        show(index);
        return;
      }
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (disabled) {
      return;
    }
    if (
      event.key.length === 1 &&
      event.key !== " " &&
      !event.altKey &&
      !event.ctrlKey &&
      !event.metaKey
    ) {
      typeahead(event.key);
      return;
    }
    if (!open) {
      if (
        event.key === "ArrowDown" ||
        event.key === "ArrowUp" ||
        event.key === "Enter" ||
        event.key === " "
      ) {
        event.preventDefault();
        show(Math.max(selectedIndex, 0));
      } else if (event.key === "Home" || event.key === "End") {
        event.preventDefault();
        show(event.key === "Home" ? 0 : last);
      }
      return;
    }
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setActive((index) => Math.min(last, index + 1));
        return;
      case "ArrowUp":
        event.preventDefault();
        setActive((index) => Math.max(0, index - 1));
        return;
      case "Home":
      case "End":
        event.preventDefault();
        setActive(event.key === "Home" ? 0 : last);
        return;
      case "Enter":
      case " ":
        event.preventDefault();
        pick(active);
        return;
      case "Escape":
        event.preventDefault();
        event.stopPropagation();
        setOpen(false);
        return;
      case "Tab":
        pick(active);
        return;
      default:
    }
  };

  return (
    <div className="relative">
      <input type="hidden" name={name} value={value ?? ""} />
      <div
        {...aria}
        id={id}
        role="combobox"
        tabIndex={0}
        aria-labelledby={fieldLabelId(name)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={open ? optionId(listId, active) : undefined}
        aria-disabled={disabled ? true : undefined}
        onKeyDown={onKeyDown}
        onClick={() => {
          if (!disabled) {
            if (open) {
              setOpen(false);
            } else {
              show(Math.max(selectedIndex, 0));
            }
          }
        }}
        onBlur={() => setOpen(false)}
        className={cn(
          controlClass(invalid),
          "flex cursor-default items-center justify-between gap-2 text-start",
          disabled && "bg-subtle text-fg-disabled hover:border-control",
        )}
      >
        <span className={cn("truncate", selectedIndex < 0 && "text-fg-3")}>
          {options[selectedIndex]?.label ?? placeholder ?? t("common.form.select.placeholder")}
        </span>
        <CaretDown aria-hidden="true" className="shrink-0 text-fg-2" />
      </div>
      {open && options.length > 0 ? (
        <Listbox
          id={listId}
          labelledBy={fieldLabelId(name)}
          options={options}
          active={active}
          selected={new Set(value === null ? [] : [value])}
          onPick={pick}
          renderExtra={renderExtra}
        />
      ) : null}
    </div>
  );
}
