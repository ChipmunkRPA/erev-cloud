// Segmented control (DESIGN_SYSTEM DS-CMP-31; APG Radio Group). Two to five mutually exclusive view
// options; Tab focuses the selected option, arrow keys move and select (Left and Right mirrored in
// RTL), and a disabled option states its reason in a tooltip.
import { type KeyboardEvent, useRef } from "react";

import type { Icon } from "../icons/registry";
import { cn } from "./cn";
import { Tooltip, type TooltipTriggerProps } from "./Tooltip";

export interface SegmentOption<T extends string> {
  readonly value: T;
  readonly label: string;
  readonly icon?: Icon | undefined;
  readonly disabledReason?: string | undefined;
}

export interface SegmentedControlProps<T extends string> {
  readonly label: string;
  readonly options: readonly SegmentOption<T>[];
  readonly value: T;
  readonly onChange: (value: T) => void;
}

export function SegmentedControl<T extends string>({
  label,
  options,
  value,
  onChange,
}: SegmentedControlProps<T>) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  if (options.length < 2 || options.length > 5) {
    throw new Error("A segmented control holds 2 to 5 options (DS-CMP-31)");
  }
  const selected = options.findIndex((option) => option.value === value);
  const focusable =
    selected >= 0 ? selected : options.findIndex((option) => option.disabledReason === undefined);

  const move = (from: number, step: 1 | -1) => {
    for (let offset = 1; offset <= options.length; offset += 1) {
      const index = (from + step * offset + options.length * offset) % options.length;
      const option = options[index];
      if (option !== undefined && option.disabledReason === undefined) {
        refs.current[index]?.focus();
        onChange(option.value);
        return;
      }
    }
  };

  const onKeyDown = (index: number) => (event: KeyboardEvent<HTMLButtonElement>) => {
    const rtl = event.currentTarget.closest("[dir]")?.getAttribute("dir") === "rtl";
    const forward = rtl ? "ArrowLeft" : "ArrowRight";
    const backward = rtl ? "ArrowRight" : "ArrowLeft";
    if (event.key === forward || event.key === "ArrowDown") {
      event.preventDefault();
      move(index, 1);
    } else if (event.key === backward || event.key === "ArrowUp") {
      event.preventDefault();
      move(index, -1);
    }
  };

  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-grid auto-cols-fr grid-flow-col rounded-md bg-subtle p-0.5"
    >
      {options.map((option, index) => {
        const OptionIcon = option.icon;
        const checked = index === selected;
        const unavailable = option.disabledReason !== undefined;
        const render = (trigger: TooltipTriggerProps | null) => (
          <button
            ref={(element) => {
              refs.current[index] = element;
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            aria-disabled={unavailable ? true : undefined}
            aria-describedby={trigger?.["aria-describedby"]}
            tabIndex={index === focusable ? 0 : -1}
            onClick={() => {
              if (!unavailable) {
                onChange(option.value);
              }
            }}
            onKeyDown={(event) => {
              trigger?.onKeyDown(event);
              onKeyDown(index)(event);
            }}
            onMouseEnter={trigger?.onMouseEnter}
            onMouseLeave={trigger?.onMouseLeave}
            onFocus={trigger?.onFocus}
            onBlur={trigger?.onBlur}
            className={cn(
              "inline-flex h-[var(--control-h-sm)] w-full items-center justify-center gap-1.5 rounded-sm border px-3 text-body-sm font-medium",
              checked
                ? "border-control bg-surface text-fg-1"
                : "border-transparent text-fg-2 hover:text-fg-1",
              unavailable && "text-fg-disabled",
            )}
          >
            {OptionIcon === undefined ? null : (
              <OptionIcon aria-hidden="true" className="shrink-0" />
            )}
            {option.label}
          </button>
        );
        return option.disabledReason === undefined ? (
          <span key={option.value} className="inline-flex">
            {render(null)}
          </span>
        ) : (
          <Tooltip key={option.value} content={option.disabledReason}>
            {render}
          </Tooltip>
        );
      })}
    </div>
  );
}
