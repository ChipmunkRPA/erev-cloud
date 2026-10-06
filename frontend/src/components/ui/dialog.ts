// Focus handling of modal dialogs, shared by Modal (DS-CMP-11) and the modal Drawer (DS-CMP-09); APG
// Dialog (Modal) and DS-A11Y-10: focus moves inside on open, Tab is trapped, and focus returns to the
// trigger on close.
import { type RefObject, useEffect } from "react";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

const FIELD =
  "input:not([disabled]):not([type='hidden']), select:not([disabled]), textarea:not([disabled])";

export function focusableWithin(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (element) => element.closest("[hidden], [inert]") === null,
  );
}

interface TabKey {
  readonly key: string;
  readonly shiftKey: boolean;
  preventDefault(): void;
}

/** Keeps Tab and Shift+Tab inside `root`, wrapping at either end. */
export function trapTab(event: TabKey, root: HTMLElement): void {
  if (event.key !== "Tab") {
    return;
  }
  const focusable = focusableWithin(root);
  const first = focusable[0];
  const last = focusable.at(-1);
  const current = document.activeElement;
  if (first === undefined || last === undefined) {
    event.preventDefault();
    root.focus();
  } else if (event.shiftKey && (current === first || !root.contains(current))) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (current === last || !root.contains(current))) {
    event.preventDefault();
    first.focus();
  }
}

export interface ModalFocusOptions {
  readonly panel: RefObject<HTMLElement | null>;
  /** The element focused on open; otherwise the first field, else the panel itself. */
  readonly initialFocus?: RefObject<HTMLElement | null> | undefined;
}

/** Call from a component that mounts only while its dialog is open. */
export function useModalFocus({ panel, initialFocus }: ModalFocusOptions): void {
  useEffect(() => {
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const root = panel.current;
    const target = initialFocus?.current ?? root?.querySelector<HTMLElement>(FIELD) ?? root ?? null;
    target?.focus();
    return () => {
      // Passive cleanups run after the DOM is updated: a trigger that left with an enclosing dialog
      // (a drawer closed through its discard confirmation) is skipped, and that dialog returns focus
      // to its own trigger.
      if (trigger?.isConnected === true) {
        trigger.focus();
      }
    };
  }, [panel, initialFocus]);
}
