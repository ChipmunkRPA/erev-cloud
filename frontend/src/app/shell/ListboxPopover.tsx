// Popover listbox (APG Listbox, single selection; DESIGN_SYSTEM DS-CMP-03 segment selectors and the
// SCREENS §1.3 tenant switcher). The listbox takes focus when it opens and marks the active option
// through aria-activedescendant: Up and Down move and wrap, Home and End jump, a printable key moves to
// the next option starting with it, Enter or Space selects, Esc closes and returns focus to the trigger,
// and Tab closes. A pointer press outside the boundary closes without moving focus.
import {
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

import { cn } from "../../components/ui/cn";

export interface PopoverOption {
  readonly id: string;
  readonly label: string;
  /** Consecutive options with the same group render under one group label. */
  readonly group?: string | undefined;
  /** Chips after the label; they are part of the option's accessible name. */
  readonly extra?: ReactNode;
}

export interface ListboxPopoverProps {
  readonly label: string;
  readonly options: readonly PopoverOption[];
  readonly selectedId: string | null;
  readonly onSelect: (id: string) => void;
  /** `returnFocus` is true after Esc, false after Tab or a pointer press outside. */
  readonly onClose: (returnFocus: boolean) => void;
  /** A pointer press inside this element does not close the popover, for example the trigger group. */
  readonly boundary?: RefObject<HTMLElement | null> | undefined;
  /** Content after the list, for example a link. */
  readonly footer?: ReactNode;
  readonly className?: string | undefined;
}

export function optionElementId(listId: string, index: number): string {
  return `${listId}-option-${String(index)}`;
}

interface Group {
  readonly name: string | undefined;
  readonly items: { readonly option: PopoverOption; readonly index: number }[];
}

export function ListboxPopover({
  label,
  options,
  selectedId,
  onSelect,
  onClose,
  boundary,
  footer,
  className,
}: ListboxPopoverProps) {
  const listId = useId();
  const root = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(() =>
    Math.max(
      0,
      options.findIndex((option) => option.id === selectedId),
    ),
  );
  const latestClose = useRef(onClose);
  useEffect(() => {
    latestClose.current = onClose;
  });

  useEffect(() => {
    list.current?.focus();
  }, []);

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      const container = boundary?.current ?? root.current;
      if (event.target instanceof Node && container?.contains(event.target) !== true) {
        latestClose.current(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [boundary]);

  const count = options.length;
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        if (count > 0) {
          setActive((index) => (index + 1) % count);
        }
        return;
      case "ArrowUp":
        event.preventDefault();
        if (count > 0) {
          setActive((index) => (index - 1 + count) % count);
        }
        return;
      case "Home":
        event.preventDefault();
        setActive(0);
        return;
      case "End":
        event.preventDefault();
        setActive(Math.max(count - 1, 0));
        return;
      case "Enter":
      case " ": {
        event.preventDefault();
        const option = options[active];
        if (option !== undefined) {
          onSelect(option.id);
        }
        return;
      }
      case "Escape":
        event.preventDefault();
        event.stopPropagation();
        onClose(true);
        return;
      case "Tab":
        onClose(false);
        return;
      default:
        if (event.key.length === 1 && !event.altKey && !event.ctrlKey && !event.metaKey) {
          const key = event.key.toLocaleLowerCase();
          for (let step = 1; step <= count; step += 1) {
            const index = (active + step) % count;
            if (options[index]?.label.toLocaleLowerCase().startsWith(key) === true) {
              setActive(index);
              break;
            }
          }
        }
    }
  };

  const groups: Group[] = [];
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
    readonly option: PopoverOption;
    readonly index: number;
  }) => (
    <div
      key={option.id}
      id={optionElementId(listId, index)}
      role="option"
      tabIndex={-1}
      aria-selected={option.id === selectedId}
      onMouseDown={(event) => {
        event.preventDefault();
        onSelect(option.id);
      }}
      className={cn(
        "flex h-[var(--row-h)] shrink-0 cursor-default items-center justify-between gap-3 rounded-sm px-2 text-body-sm text-fg-1",
        index === active && "bg-hover",
        option.id === selectedId && "font-medium",
      )}
    >
      <span className="truncate">{option.label}</span>
      {option.extra === undefined ? null : (
        <span className="flex shrink-0 items-center gap-1.5">{option.extra}</span>
      )}
    </div>
  );

  return (
    <div
      ref={root}
      className={cn(
        "absolute top-full z-[var(--z-popover)] mt-1 flex min-w-64 flex-col rounded-lg border border-hairline bg-raised p-1 shadow-popover",
        className,
      )}
    >
      <div
        ref={list}
        id={listId}
        role="listbox"
        tabIndex={0}
        aria-label={label}
        aria-activedescendant={count === 0 ? undefined : optionElementId(listId, active)}
        onKeyDown={onKeyDown}
        className="focus-inset flex max-h-80 flex-col overflow-y-auto rounded-md"
      >
        {groups.map((group, groupIndex) =>
          group.name === undefined ? (
            group.items.map(renderOption)
          ) : (
            <div
              key={`${group.name}-${String(groupIndex)}`}
              role="group"
              aria-labelledby={`${listId}-group-${String(groupIndex)}`}
              className="flex flex-col"
            >
              <div
                id={`${listId}-group-${String(groupIndex)}`}
                className="px-2 pb-1 pt-2 text-caption text-fg-3"
              >
                {group.name}
              </div>
              {group.items.map(renderOption)}
            </div>
          ),
        )}
      </div>
      {footer === undefined || footer === null ? null : (
        <div className="mt-1 border-t border-hairline px-2 pb-1 pt-2">{footer}</div>
      )}
    </div>
  );
}
