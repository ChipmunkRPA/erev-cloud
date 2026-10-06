// Popup listbox shared by Select, Combobox, MultiSelect and PeriodInput (DESIGN_SYSTEM DS-CMP-21; APG
// Listbox with aria-activedescendant). Focus stays on the owning combobox; options are picked with the
// pointer through mousedown, which keeps that focus, and with the keyboard by the owner.
import type { ReactNode } from "react";

import { cn } from "../ui/cn";

export interface ListOption<T extends string> {
  readonly value: T;
  readonly label: string;
  /** Consecutive options with the same group render under one group label. */
  readonly group?: string | undefined;
}

export function optionId(listId: string, index: number): string {
  return `${listId}-option-${String(index)}`;
}

export interface ListboxProps<T extends string> {
  readonly id: string;
  readonly labelledBy: string;
  readonly options: readonly ListOption<T>[];
  readonly active: number;
  readonly selected: ReadonlySet<string>;
  readonly multiselectable?: boolean;
  readonly onPick: (index: number) => void;
  readonly renderExtra?: ((option: ListOption<T>) => ReactNode) | undefined;
}

interface Group<T extends string> {
  readonly name: string | undefined;
  readonly items: { readonly option: ListOption<T>; readonly index: number }[];
}

export function Listbox<T extends string>({
  id,
  labelledBy,
  options,
  active,
  selected,
  multiselectable = false,
  onPick,
  renderExtra,
}: ListboxProps<T>) {
  const groups: Group<T>[] = [];
  options.forEach((option, index) => {
    const last = groups.at(-1);
    if (last !== undefined && last.name === option.group) {
      last.items.push({ option, index });
    } else {
      groups.push({ name: option.group, items: [{ option, index }] });
    }
  });

  const renderOption = ({
    option,
    index,
  }: {
    readonly option: ListOption<T>;
    readonly index: number;
  }) => {
    const isSelected = selected.has(option.value);
    return (
      <div
        key={option.value}
        id={optionId(id, index)}
        role="option"
        tabIndex={-1}
        aria-selected={isSelected}
        onMouseDown={(event) => {
          event.preventDefault();
          onPick(index);
        }}
        className={cn(
          "flex h-[var(--row-h)] shrink-0 cursor-default items-center justify-between gap-3 rounded-sm px-2 text-body-sm text-fg-1",
          index === active && "bg-hover",
          isSelected && "font-medium",
        )}
      >
        <span className="truncate">{option.label}</span>
        {renderExtra?.(option)}
      </div>
    );
  };

  return (
    <div
      id={id}
      role="listbox"
      aria-labelledby={labelledBy}
      aria-multiselectable={multiselectable ? true : undefined}
      className="absolute start-0 top-full z-[var(--z-popover)] mt-1 flex max-h-80 min-w-full flex-col overflow-y-auto rounded-lg border border-hairline bg-raised p-1 shadow-popover"
    >
      {groups.map((group, groupIndex) =>
        group.name === undefined ? (
          group.items.map(renderOption)
        ) : (
          <div
            key={group.name}
            role="group"
            aria-labelledby={`${id}-group-${String(groupIndex)}`}
            className="flex flex-col"
          >
            <div
              id={`${id}-group-${String(groupIndex)}`}
              className="px-2 pb-1 pt-2 text-caption text-fg-3"
            >
              {group.name}
            </div>
            {group.items.map(renderOption)}
          </div>
        ),
      )}
    </div>
  );
}
