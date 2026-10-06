// Tour step popover (DESIGN_SYSTEM DS-CMP-32; SCREENS_B §11.2). A non-modal dialog named
// "Stop <n> of <total>: <title>" on the DS-CMP-05 panel surface, beside its target or below it when there
// is no room. Opening a stop focuses the heading and announces the dialog name; nothing traps focus and
// the page stays operable. The target gets a 2 px control outline and aria-describedby the popover. Esc
// or "End tour" ends the tour and returns focus to the Help menu button.
import { type RefObject, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { announce } from "../../lib/a11y/announce";
import { formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { Button } from "../ui/Button";

export interface TourPopoverProps {
  readonly stop: number;
  readonly total: number;
  readonly title: string;
  /** At most three sentences. */
  readonly body: string;
  /** The stop's target element; null when this workspace has no such element. */
  readonly anchor: HTMLElement | null;
  /** The permission label when the viewer's roles skip this stop. */
  readonly skippedPermission?: string | undefined;
  /** The Help menu button that started the tour. */
  readonly returnFocus: RefObject<HTMLElement | null>;
  readonly onBack: () => void;
  readonly onNext: () => void;
  readonly onEnd: () => void;
}

export const TOUR_POPOVER_WIDTH = 360;
const GAP = 12;

interface Position {
  readonly top: number;
  readonly start: number;
}

function place(anchor: HTMLElement | null): Position {
  if (anchor === null) {
    return { top: GAP * 6, start: GAP * 2 };
  }
  const rect = anchor.getBoundingClientRect();
  if (rect.right + GAP + TOUR_POPOVER_WIDTH <= window.innerWidth) {
    return { top: rect.top, start: rect.right + GAP };
  }
  return { top: rect.bottom + GAP, start: Math.max(GAP, rect.left) };
}

export function TourPopover({
  stop,
  total,
  title,
  body,
  anchor,
  skippedPermission,
  returnFocus,
  onBack,
  onNext,
  onEnd,
}: TourPopoverProps) {
  const popoverId = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [position, setPosition] = useState<Position>(() => place(anchor));
  const numbers = { stop: formatNumber(stop), total: formatNumber(total) };
  const counter = t("common.tour.counter", numbers);
  const name = t("common.tour.name", { ...numbers, title });
  const last = stop === total;

  const end = () => {
    onEnd();
    returnFocus.current?.focus();
  };
  const endRef = useRef(end);
  endRef.current = end;

  useEffect(() => {
    headingRef.current?.focus();
    announce(name, "polite");
  }, [name]);

  useLayoutEffect(() => setPosition(place(anchor)), [anchor, stop]);

  useEffect(() => {
    if (anchor === null) {
      return undefined;
    }
    const previous = {
      outline: anchor.style.outline,
      outlineOffset: anchor.style.outlineOffset,
      describedBy: anchor.getAttribute("aria-describedby"),
    };
    anchor.style.outline = "2px solid var(--border-control)";
    anchor.style.outlineOffset = "2px";
    anchor.setAttribute(
      "aria-describedby",
      [previous.describedBy, popoverId].filter((id) => id !== null).join(" "),
    );
    return () => {
      anchor.style.outline = previous.outline;
      anchor.style.outlineOffset = previous.outlineOffset;
      if (previous.describedBy === null) {
        anchor.removeAttribute("aria-describedby");
      } else {
        anchor.setAttribute("aria-describedby", previous.describedBy);
      }
    };
  }, [anchor, popoverId]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        event.key === "Escape" &&
        !event.defaultPrevented &&
        document.querySelector("[aria-modal='true']") === null
      ) {
        event.preventDefault();
        endRef.current();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const message =
    skippedPermission !== undefined
      ? t("common.tour.skipped", { permission: skippedPermission })
      : anchor === null
        ? t("common.tour.missing")
        : body;

  return createPortal(
    <div
      id={popoverId}
      role="dialog"
      aria-label={name}
      aria-describedby={`${popoverId}-body`}
      className="fixed z-[var(--z-popover)] flex w-90 max-w-full flex-col gap-2 rounded-lg border border-hairline bg-raised p-[var(--panel-pad)] shadow-popover"
      style={{ insetBlockStart: position.top, insetInlineStart: position.start }}
    >
      <p className="text-caption text-fg-3">{counter}</p>
      <h2 ref={headingRef} tabIndex={-1} className="text-title-sm text-fg-1">
        {title}
      </h2>
      <p id={`${popoverId}-body`} className="text-body-sm text-fg-2">
        {message}
      </p>
      <div className="mt-2 flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={end}>
          {t("common.tour.end")}
        </Button>
        <span className="flex-1" />
        {stop > 1 ? (
          <Button variant="secondary" size="sm" onClick={onBack}>
            {t("common.tour.back")}
          </Button>
        ) : null}
        <Button variant="primary" size="sm" onClick={last ? end : onNext}>
          {last ? t("common.tour.finish") : t("common.tour.next")}
        </Button>
      </div>
    </div>,
    document.body,
  );
}
