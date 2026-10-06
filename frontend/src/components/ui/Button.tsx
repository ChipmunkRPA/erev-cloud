// Button (DESIGN_SYSTEM DS-CMP-20; DS-ICO-06; DS-AP-15). A disabled button keeps focus through
// aria-disabled and states its reason in a tooltip; a loading button keeps its label, replaces the
// leading icon with the running mark, sets aria-busy and ignores repeated presses. An icon-only button
// needs aria-label and shows it as a tooltip.
import type {
  ButtonHTMLAttributes,
  FocusEvent,
  KeyboardEvent,
  MouseEvent,
  ReactNode,
  Ref,
} from "react";

import { CircleHalf, type Icon } from "../icons/registry";
import { cn } from "./cn";
import { Tooltip, type TooltipTriggerProps } from "./Tooltip";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "link";
export type ButtonSize = "md" | "sm";

export interface ButtonProps extends Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "disabled" | "type" | "children"
> {
  readonly variant?: ButtonVariant;
  readonly size?: ButtonSize;
  readonly type?: "button" | "submit" | "reset";
  readonly icon?: Icon | undefined;
  readonly trailingIcon?: Icon | undefined;
  /** A keyboard hint for the tooltip of an icon-only button. */
  readonly shortcut?: string | undefined;
  /** Makes the button unavailable; the reason is the tooltip (and, for submits, a visible line). */
  readonly disabledReason?: string | undefined;
  readonly loading?: boolean;
  readonly children?: ReactNode;
  readonly ref?: Ref<HTMLButtonElement>;
}

const VARIANT: Readonly<Record<ButtonVariant, string>> = {
  primary:
    "bg-accent-solid text-on-accent hover:bg-accent-solid-hover active:bg-accent-solid-active",
  secondary: "border border-control bg-surface text-fg-1 hover:bg-hover active:bg-active",
  ghost: "bg-transparent text-fg-2 hover:bg-hover hover:text-fg-1 active:bg-active",
  danger:
    "bg-danger-solid text-on-accent hover:bg-danger-solid-hover active:bg-danger-solid-active",
  link: "bg-transparent text-accent-fg hover:text-accent-fg-hover hover:underline",
};

const HEIGHT: Readonly<Record<ButtonSize, string>> = {
  md: "h-[var(--control-h)]",
  sm: "h-[var(--control-h-sm)]",
};

const ICON_ONLY_WIDTH: Readonly<Record<ButtonSize, string>> = {
  md: "w-[var(--control-h)]",
  sm: "w-[var(--control-h-sm)]",
};

function sizing(variant: ButtonVariant, size: ButtonSize, iconOnly: boolean): string {
  if (variant === "link") {
    return "px-0";
  }
  return cn(
    HEIGHT[size],
    iconOnly ? cn(ICON_ONLY_WIDTH[size], "px-0") : size === "md" ? "px-3" : "px-2.5",
  );
}

export function Button({
  variant = "secondary",
  size = "md",
  type = "button",
  icon: LeadingIcon,
  trailingIcon: TrailingIcon,
  shortcut,
  disabledReason,
  loading = false,
  children,
  className,
  onClick,
  onMouseEnter,
  onMouseLeave,
  onFocus,
  onBlur,
  onKeyDown,
  ref,
  ...rest
}: ButtonProps) {
  const iconOnly = children === undefined || children === null || children === false;
  const label = rest["aria-label"];
  if (iconOnly && (label === undefined || label.trim() === "")) {
    throw new Error("An icon-only Button needs aria-label (DS-CMP-20, DS-ICO-06)");
  }
  const unavailable = disabledReason !== undefined;
  const Leading = loading ? CircleHalf : LeadingIcon;

  const render = (trigger: TooltipTriggerProps | null) => (
    <button
      {...rest}
      aria-describedby={cn(rest["aria-describedby"], trigger?.["aria-describedby"]) || undefined}
      ref={ref}
      type={type}
      aria-disabled={unavailable ? true : undefined}
      aria-busy={loading ? true : undefined}
      className={cn(
        "inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-body-sm font-medium",
        sizing(variant, size, iconOnly),
        VARIANT[variant],
        unavailable && "text-fg-disabled",
        className,
      )}
      onClick={(event: MouseEvent<HTMLButtonElement>) => {
        if (unavailable || loading) {
          event.preventDefault();
          return;
        }
        onClick?.(event);
      }}
      onMouseEnter={(event: MouseEvent<HTMLButtonElement>) => {
        trigger?.onMouseEnter();
        onMouseEnter?.(event);
      }}
      onMouseLeave={(event: MouseEvent<HTMLButtonElement>) => {
        trigger?.onMouseLeave();
        onMouseLeave?.(event);
      }}
      onFocus={(event: FocusEvent<HTMLButtonElement>) => {
        trigger?.onFocus(event);
        onFocus?.(event);
      }}
      onBlur={(event: FocusEvent<HTMLButtonElement>) => {
        trigger?.onBlur();
        onBlur?.(event);
      }}
      onKeyDown={(event: KeyboardEvent<HTMLButtonElement>) => {
        trigger?.onKeyDown(event);
        onKeyDown?.(event);
      }}
    >
      {Leading === undefined ? null : <Leading aria-hidden="true" className="shrink-0" />}
      {iconOnly ? null : children}
      {TrailingIcon === undefined ? null : <TrailingIcon aria-hidden="true" className="shrink-0" />}
    </button>
  );

  const tooltip = disabledReason ?? (iconOnly ? label : undefined);
  if (tooltip === undefined) {
    return render(null);
  }
  return (
    <Tooltip content={tooltip} shortcut={shortcut} kind={unavailable ? "description" : "label"}>
      {render}
    </Tooltip>
  );
}
