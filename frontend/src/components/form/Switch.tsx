// Switch (DESIGN_SYSTEM DS-CMP-21 field types; APG Switch). Only for immediately applied preferences,
// never inside a form with a Save button. Native button semantics give Enter and Space; an unavailable
// switch keeps focus through aria-disabled and states its reason in a tooltip.
import { useId } from "react";

import { cn } from "../ui/cn";
import { Tooltip, type TooltipTriggerProps } from "../ui/Tooltip";

export interface SwitchProps {
  readonly label: string;
  readonly checked: boolean;
  readonly onChange: (checked: boolean) => void;
  readonly disabledReason?: string | undefined;
}

export function Switch({ label, checked, onChange, disabledReason }: SwitchProps) {
  const labelId = useId();
  const unavailable = disabledReason !== undefined;
  const render = (trigger: TooltipTriggerProps | null) => (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-labelledby={labelId}
      aria-disabled={unavailable ? true : undefined}
      aria-describedby={trigger?.["aria-describedby"]}
      onClick={() => {
        if (!unavailable) {
          onChange(!checked);
        }
      }}
      onMouseEnter={trigger?.onMouseEnter}
      onMouseLeave={trigger?.onMouseLeave}
      onFocus={trigger?.onFocus}
      onBlur={trigger?.onBlur}
      onKeyDown={trigger?.onKeyDown}
      className={cn(
        "inline-flex h-6 w-10 shrink-0 items-center rounded-full border p-0.5",
        checked
          ? "justify-end border-accent-solid bg-accent-solid"
          : "justify-start border-control bg-subtle",
      )}
    >
      <span className={cn("size-4 rounded-full", checked ? "bg-on-accent" : "bg-fg-3")} />
    </button>
  );
  return (
    <span className="inline-flex items-center gap-2">
      {unavailable ? <Tooltip content={disabledReason}>{render}</Tooltip> : render(null)}
      <span
        id={labelId}
        className={cn("text-body-sm", unavailable ? "text-fg-disabled" : "text-fg-1")}
      >
        {label}
      </span>
    </span>
  );
}
