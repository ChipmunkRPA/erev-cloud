// Tooltip (DESIGN_SYSTEM DS-CMP-27; APG Tooltip). Opens 400 ms after pointer entry or at once on
// keyboard focus; closes on blur, pointer leave or Esc. A tooltip never holds interactive content.
// `kind="description"` references the tooltip with aria-describedby; `kind="label"` is for icon-only
// buttons whose aria-label already equals the tooltip text, so the tooltip is not referenced again.
import {
  type FocusEvent,
  type KeyboardEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

export const TOOLTIP_DELAY_MS = 400;

// The last input modality: focus after a key press opens a tooltip at once; focus after a pointer
// press waits for the hover delay. `:focus-visible` answers the same question where supported.
let keyboardModality = false;
if (typeof document !== "undefined") {
  document.addEventListener("keydown", () => (keyboardModality = true), true);
  document.addEventListener("pointerdown", () => (keyboardModality = false), true);
}

function keyboardFocused(element: Element): boolean {
  if (keyboardModality) {
    return true;
  }
  try {
    return element.matches(":focus-visible");
  } catch {
    return false;
  }
}

export interface TooltipTriggerProps {
  readonly "aria-describedby"?: string;
  readonly onMouseEnter: () => void;
  readonly onMouseLeave: () => void;
  readonly onFocus: (event: FocusEvent<HTMLElement>) => void;
  readonly onBlur: () => void;
  readonly onKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
}

export interface TooltipProps {
  readonly content: string;
  /** A keyboard hint shown in mono after the text. */
  readonly shortcut?: string | undefined;
  readonly kind?: "description" | "label";
  readonly children: (trigger: TooltipTriggerProps) => ReactNode;
}

export function Tooltip({ content, shortcut, kind = "description", children }: TooltipProps) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = useCallback(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);
  useEffect(() => clearTimer, [clearTimer]);

  const close = () => {
    clearTimer();
    setOpen(false);
  };
  const trigger: TooltipTriggerProps = {
    ...(kind === "description" ? { "aria-describedby": id } : {}),
    onMouseEnter: () => {
      clearTimer();
      timer.current = setTimeout(() => setOpen(true), TOOLTIP_DELAY_MS);
    },
    onMouseLeave: close,
    onFocus: (event) => {
      // Only keyboard focus opens at once; a pointer press waits for the hover delay.
      if (keyboardFocused(event.target)) {
        clearTimer();
        setOpen(true);
      }
    },
    onBlur: close,
    onKeyDown: (event) => {
      if (event.key === "Escape" && open) {
        event.stopPropagation();
        close();
      }
    },
  };

  return (
    <span className="relative inline-flex">
      {children(trigger)}
      <span
        id={id}
        role="tooltip"
        hidden={!open}
        className="pointer-events-none absolute start-0 top-full z-[var(--z-tooltip)] mt-1 w-max max-w-70 rounded-sm border border-hairline bg-raised px-2 py-1.5 text-caption text-fg-1 shadow-popover"
      >
        {content}
        {shortcut === undefined ? null : (
          <kbd className="ms-2 font-mono text-mono-sm text-fg-3">{shortcut}</kbd>
        )}
      </span>
    </span>
  );
}
