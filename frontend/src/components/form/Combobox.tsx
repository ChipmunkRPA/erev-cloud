// Combobox (DESIGN_SYSTEM DS-CMP-21; APG Combobox with list autocomplete) for longer lists such as
// customers, products and accounts. Typing filters the list; Down and Up move; Enter picks; Esc closes,
// and a second Esc clears the value.
import { type KeyboardEvent, useEffect, useState } from "react";

import { t } from "../../lib/i18n/t";
import { cn } from "../ui/cn";
import { controlClass, type FieldControlProps, fieldLabelId } from "./Field";
import { type ListOption, Listbox, optionId } from "./Listbox";

export interface ComboboxProps<T extends string> {
  readonly control: FieldControlProps;
  readonly options: readonly ListOption<T>[];
  readonly value: T | null;
  readonly onChange: (value: T | null) => void;
  readonly invalid?: boolean;
}

export function matchOptions<T extends string>(
  options: readonly ListOption<T>[],
  text: string,
): readonly ListOption<T>[] {
  const query = text.trim().toLocaleLowerCase();
  return query === ""
    ? options
    : options.filter((option) => option.label.toLocaleLowerCase().includes(query));
}

export function Combobox<T extends string>({
  control,
  options,
  value,
  onChange,
  invalid = false,
}: ComboboxProps<T>) {
  const { name, ...inputProps } = control;
  const listId = `${control.id}-listbox`;
  const selectedLabel = options.find((option) => option.value === value)?.label ?? "";
  const [text, setText] = useState(selectedLabel);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  useEffect(() => {
    setText(selectedLabel);
  }, [selectedLabel]);

  const matches = text === selectedLabel ? options : matchOptions(options, text);
  const pick = (index: number) => {
    const option = matches[index];
    if (option !== undefined) {
      onChange(option.value);
      setText(option.label);
    }
    setOpen(false);
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
          pick(active);
        }
        return;
      case "Escape":
        event.preventDefault();
        if (open) {
          setOpen(false);
        } else if (text !== "") {
          setText("");
          onChange(null);
        }
        return;
      default:
    }
  };

  return (
    <div className="relative">
      <input type="hidden" name={name} value={value ?? ""} />
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
        onBlur={() => {
          setOpen(false);
          setText(selectedLabel);
        }}
        className={controlClass(invalid)}
      />
      {open && matches.length > 0 ? (
        <Listbox
          id={listId}
          labelledBy={fieldLabelId(name)}
          options={matches}
          active={active}
          selected={new Set(value === null ? [] : [value])}
          onPick={pick}
        />
      ) : null}
      {open && matches.length === 0 ? (
        <div
          role="status"
          className={cn(
            "absolute start-0 top-full z-[var(--z-popover)] mt-1 min-w-full rounded-lg border border-hairline bg-raised px-3 py-2 text-body-sm text-fg-3 shadow-popover",
          )}
        >
          {t("common.form.combobox.noMatches")}
        </div>
      ) : null}
    </div>
  );
}
