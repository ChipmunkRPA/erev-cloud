// Menu (DESIGN_SYSTEM DS-CMP-28; APG Menu Button and Menu). Enter, Space or Down opens and focuses
// the first item, Up opens at the last; Up and Down wrap; Home and End; type-ahead; Enter activates;
// Esc closes and returns focus to the trigger. Destructive items sit last, after a separator. An item
// that a state makes unavailable (SCREENS SCR-PERM-03) is a disabled item: it keeps its place in the
// arrow-key order, carries `aria-disabled`, is described by a tooltip that states its reason (DS-CMP-27:
// at once while it has focus, after the hover delay under the pointer), and does not activate (the
// DS-CMP-20 disabled state, for a menu item).
import { type KeyboardEvent, useCallback, useEffect, useId, useRef, useState } from "react";

import type { Icon } from "../icons/registry";
import { Button, type ButtonSize, type ButtonVariant } from "./Button";
import { cn } from "./cn";
import { TOOLTIP_DELAY_MS } from "./Tooltip";

export interface MenuItem {
  readonly id: string;
  readonly label: string;
  readonly icon?: Icon | undefined;
  readonly shortcut?: string | undefined;
  readonly destructive?: boolean;
  /**
   * Makes the item unavailable and states why, for example "Permanently lock Aug 2026 first.". For a
   * state the record is in, never for a missing permission, which hides the item (SCR-PERM-02).
   */
  readonly disabledReason?: string | undefined;
  readonly onSelect: () => void;
}

export interface MenuProps {
  /** The trigger label; an icon-only trigger uses it as its accessible name. */
  readonly label: string;
  readonly items: readonly MenuItem[];
  readonly icon?: Icon | undefined;
  readonly iconOnly?: boolean;
  readonly variant?: ButtonVariant;
  readonly size?: ButtonSize;
  /** The menu's inline edge aligned with the trigger; "end" for triggers at the end of a bar. */
  readonly align?: "start" | "end";
}

export function Menu({
  label,
  items,
  icon,
  iconOnly = false,
  variant = "secondary",
  size = "md",
  align = "start",
}: MenuProps) {
  const menuId = useId();
  const triggerId = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  // The disabled item whose reason is shown: the one with focus or under the pointer.
  const [hinted, setHinted] = useState<string | null>(null);
  const hintTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const root = useRef<HTMLSpanElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const ordered = [
    ...items.filter((item) => item.destructive !== true),
    ...items.filter((item) => item.destructive === true),
  ];
  const firstDestructive = ordered.findIndex((item) => item.destructive === true);

  const cancelHint = useCallback(() => {
    if (hintTimer.current !== null) {
      clearTimeout(hintTimer.current);
      hintTimer.current = null;
    }
  }, []);
  useEffect(() => cancelHint, [cancelHint]);

  useEffect(() => {
    if (open) {
      itemRefs.current[active]?.focus();
    }
  }, [open, active]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && root.current?.contains(event.target) !== true) {
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  const openAt = (index: number) => {
    cancelHint();
    setHinted(null);
    setActive(index);
    setOpen(true);
  };
  const close = (returnFocus: boolean) => {
    cancelHint();
    setOpen(false);
    setHinted(null);
    if (returnFocus) {
      trigger.current?.focus();
    }
  };

  const onTriggerKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "Enter" || event.key === " " || event.key === "ArrowDown") {
      event.preventDefault();
      openAt(0);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      openAt(ordered.length - 1);
    }
  };

  const onMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const count = ordered.length;
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setActive((index) => (index + 1) % count);
        return;
      case "ArrowUp":
        event.preventDefault();
        setActive((index) => (index - 1 + count) % count);
        return;
      case "Home":
        event.preventDefault();
        setActive(0);
        return;
      case "End":
        event.preventDefault();
        setActive(count - 1);
        return;
      case "Escape":
        event.preventDefault();
        event.stopPropagation();
        close(true);
        return;
      case "Tab":
        close(false);
        return;
      default:
        if (event.key.length === 1 && !event.altKey && !event.ctrlKey && !event.metaKey) {
          const key = event.key.toLocaleLowerCase();
          for (let step = 1; step <= count; step += 1) {
            const index = (active + step) % count;
            if (ordered[index]?.label.toLocaleLowerCase().startsWith(key) === true) {
              setActive(index);
              break;
            }
          }
        }
    }
  };

  return (
    <span ref={root} className="relative inline-flex">
      <Button
        ref={trigger}
        id={triggerId}
        variant={variant}
        size={size}
        icon={icon}
        aria-label={iconOnly ? label : undefined}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => (open ? close(false) : openAt(0))}
        onKeyDown={onTriggerKeyDown}
      >
        {iconOnly ? undefined : label}
      </Button>
      {open ? (
        <div
          id={menuId}
          role="menu"
          tabIndex={-1}
          aria-labelledby={triggerId}
          onKeyDown={onMenuKeyDown}
          className={cn(
            "absolute top-full z-[var(--z-popover)] mt-1 flex min-w-48 flex-col rounded-lg border border-hairline bg-raised p-1 shadow-popover",
            align === "end" ? "end-0" : "start-0",
          )}
        >
          {ordered.map((item, index) => {
            const ItemIcon = item.icon;
            return (
              <div key={item.id} className="contents">
                {index === firstDestructive && index > 0 ? (
                  <div role="separator" className="my-1 h-px bg-hairline" />
                ) : null}
                {item.disabledReason === undefined ? (
                  <button
                    ref={(element) => {
                      itemRefs.current[index] = element;
                    }}
                    type="button"
                    role="menuitem"
                    tabIndex={index === active ? 0 : -1}
                    onClick={() => {
                      close(true);
                      item.onSelect();
                    }}
                    className={cn(
                      "focus-inset flex h-[var(--row-h)] w-full items-center gap-2 rounded-sm px-2 text-start text-body-sm hover:bg-hover",
                      item.destructive === true ? "text-negative-fg" : "text-fg-1",
                    )}
                  >
                    {ItemIcon === undefined ? null : (
                      <ItemIcon aria-hidden="true" className="shrink-0" />
                    )}
                    <span className="flex-1">{item.label}</span>
                    {item.shortcut === undefined ? null : (
                      <kbd className="font-mono text-mono-sm text-fg-3">{item.shortcut}</kbd>
                    )}
                  </button>
                ) : (
                  <span className="relative flex">
                    <button
                      ref={(element) => {
                        itemRefs.current[index] = element;
                      }}
                      type="button"
                      role="menuitem"
                      aria-disabled="true"
                      aria-describedby={`${menuId}-reason-${item.id}`}
                      tabIndex={index === active ? 0 : -1}
                      onFocus={() => {
                        cancelHint();
                        setHinted(item.id);
                      }}
                      onBlur={() => {
                        cancelHint();
                        setHinted(null);
                      }}
                      onMouseEnter={() => {
                        cancelHint();
                        hintTimer.current = setTimeout(() => setHinted(item.id), TOOLTIP_DELAY_MS);
                      }}
                      onMouseLeave={(event) => {
                        cancelHint();
                        // The focused item keeps its reason: the keyboard user is still on it.
                        if (document.activeElement !== event.currentTarget) {
                          setHinted(null);
                        }
                      }}
                      className="focus-inset flex h-[var(--row-h)] w-full items-center gap-2 rounded-sm px-2 text-start text-body-sm text-fg-disabled"
                    >
                      {ItemIcon === undefined ? null : (
                        <ItemIcon aria-hidden="true" className="shrink-0" />
                      )}
                      <span className="flex-1">{item.label}</span>
                      {item.shortcut === undefined ? null : (
                        <kbd className="font-mono text-mono-sm text-fg-3">{item.shortcut}</kbd>
                      )}
                    </button>
                    <span
                      id={`${menuId}-reason-${item.id}`}
                      role="tooltip"
                      hidden={hinted !== item.id}
                      className={cn(
                        "pointer-events-none absolute top-full z-[var(--z-tooltip)] mt-1 w-max max-w-70 rounded-sm border border-hairline bg-raised px-2 py-1.5 text-caption text-fg-1 shadow-popover",
                        // On the menu's aligned edge, so a long reason grows away from the bar's end.
                        align === "end" ? "end-0" : "start-0",
                      )}
                    >
                      {item.disabledReason}
                    </span>
                  </span>
                )}
              </div>
            );
          })}
        </div>
      ) : null}
    </span>
  );
}
