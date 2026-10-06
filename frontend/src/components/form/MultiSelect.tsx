// Multi-select (DESIGN_SYSTEM DS-CMP-21): a combobox whose selected values show as removable chips.
// Picking toggles an option and keeps the list open; Backspace in the empty input removes the last chip.
import { type KeyboardEvent, useState } from "react";

import { t } from "../../lib/i18n/t";
import { X } from "../icons/registry";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { matchOptions } from "./Combobox";
import { controlClass, type FieldControlProps, fieldLabelId } from "./Field";
import { type ListOption, Listbox, optionId } from "./Listbox";

export interface MultiSelectProps<T extends string> {
  readonly control: FieldControlProps;
  readonly options: readonly ListOption<T>[];
  readonly values: readonly T[];
  readonly onChange: (values: readonly T[]) => void;
  readonly invalid?: boolean;
}

export function MultiSelect<T extends string>({
  control,
  options,
  values,
  onChange,
  invalid = false,
}: MultiSelectProps<T>) {
  const { name, ...inputProps } = control;
  const listId = `${control.id}-listbox`;
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const matches = matchOptions(options, text);
  const chosen = options.filter((option) => values.includes(option.value));

  const toggle = (index: number) => {
    const option = matches[index];
    if (option === undefined) {
      return;
    }
    onChange(
      values.includes(option.value)
        ? values.filter((value) => value !== option.value)
        : [...values, option.value],
    );
    setText("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        if (open) {
          setActive((index) => Math.min(matches.length - 1, index + 1));
        } else {
          setActive(0);
          setOpen(true);
        }
        return;
      case "ArrowUp":
        event.preventDefault();
        setActive((index) => Math.max(0, index - 1));
        return;
      case "Enter":
        if (open && matches.length > 0) {
          event.preventDefault();
          toggle(active);
        }
        return;
      case "Escape":
        if (open) {
          event.preventDefault();
          setOpen(false);
        }
        return;
      case "Backspace":
        if (text === "" && values.length > 0) {
          onChange(values.slice(0, -1));
        }
        return;
      default:
    }
  };

  return (
    <div className="relative">
      {values.map((value) => (
        <input key={value} type="hidden" name={name} value={value} />
      ))}
      <div className={cn(controlClass(invalid, true), "flex flex-wrap items-center gap-1")}>
        {chosen.map((option) => (
          <span
            key={option.value}
            className="inline-flex items-center gap-0.5 rounded-sm border border-default bg-subtle ps-1.5 text-caption text-fg-1"
          >
            {option.label}
            <Button
              variant="ghost"
              size="sm"
              icon={X}
              aria-label={t("common.form.multiSelect.remove", { label: option.label })}
              onClick={() => onChange(values.filter((value) => value !== option.value))}
            />
          </span>
        ))}
        <input
          {...inputProps}
          type="text"
          role="combobox"
          autoComplete="off"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={listId}
          aria-activedescendant={open && matches.length > 0 ? optionId(listId, active) : undefined}
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setActive(0);
            setOpen(true);
          }}
          onKeyDown={onKeyDown}
          onBlur={() => setOpen(false)}
          className="h-[var(--control-h-sm)] min-w-24 flex-1 bg-transparent text-body text-fg-1"
        />
      </div>
      {open && matches.length > 0 ? (
        <Listbox
          id={listId}
          labelledBy={fieldLabelId(name)}
          options={matches}
          active={active}
          selected={new Set<string>(values)}
          multiselectable
          onPick={toggle}
        />
      ) : null}
    </div>
  );
}
