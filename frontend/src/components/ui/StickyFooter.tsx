// Sticky footer with its cue (DESIGN_SYSTEM DS-CMP-16 item 6 rev 1.9, DS-CMP-18 "Footer"; DS-A11Y-03;
// DS-ELV-04). A footer that sticks to the lower edge of the region that scrolls covers what lies beneath
// it, and no shadow may mark that edge. While content lies beneath, the footer's first row is the link
// button "More below", inside the footer so that the cue itself covers nothing; it scrolls the region by
// one view less the footer. The region's `scroll-padding-block-end` is the footer's height including
// that row, whether or not the row is shown, so an element that takes focus is never under the footer.
// Whether content lies beneath is measured when the region scrolls, when the region or the footer is
// resized, and when the region's content changes.
//
// The region is the shell's `main`, whose padding is the gutter: the footer sits flush with its lower
// edge (`-bottom` and `-mb` of one gutter), so nothing of the page shows below it.
import { type ReactNode, type RefObject, useEffect, useRef, useState } from "react";

import { t } from "../../lib/i18n/t";
import { CaretDown } from "../icons/registry";
import { Button } from "./Button";
import { cn } from "./cn";

/** Content of the region ends this close to its lower edge before it counts as lying beneath. */
const BELOW_TOLERANCE_PX = 1;
/** Marks the row the cue adds to the footer. */
const CUE_ROW = "data-cue-row";

/** What the cue's row adds to the footer's height: a small control and the footer's row gap. */
function cueRowHeight(footer: HTMLElement): string {
  const gap = getComputedStyle(footer).rowGap;
  return `var(--control-h-sm) + ${/^[\d.]+px$/.test(gap) ? gap : "0px"}`;
}

/** The region a footer scrolls with: the shell's `main`. */
function regionOf(footer: HTMLElement | null): HTMLElement | null {
  return footer?.closest<HTMLElement>("main") ?? null;
}

interface Below {
  /** Content of the region lies beneath the footer. */
  readonly below: boolean;
  /** Scrolls the region by one view less the footer. */
  readonly showMore: () => void;
}

function useContentBelow(footer: RefObject<HTMLElement | null>): Below {
  const [below, setBelow] = useState(false);
  const measure = useRef<() => void>(() => undefined);
  useEffect(() => {
    const element = footer.current;
    const region = regionOf(element);
    if (element === null || region === null) {
      return undefined;
    }
    const read = () => {
      setBelow(region.scrollHeight - region.clientHeight - region.scrollTop > BELOW_TOLERANCE_PX);
      // The footer is taller by the cue's row while the cue is shown; the padding is that taller
      // height in both states, so a field that takes focus while the cue is not shown is not covered
      // the moment the cue appears.
      const height = `${String(element.offsetHeight)}px`;
      region.style.scrollPaddingBlockEnd =
        element.querySelector(`[${CUE_ROW}]`) === null
          ? `calc(${height} + ${cueRowHeight(element)})`
          : height;
    };
    measure.current = read;
    read();
    region.addEventListener("scroll", read, { passive: true });
    const boxes = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(read);
    boxes?.observe(region);
    boxes?.observe(element);
    // Rows that arrive after the first paint change no observed box when they grow a child that
    // overflows: the region is measured again whenever its content changes.
    const content = typeof MutationObserver === "undefined" ? null : new MutationObserver(read);
    content?.observe(region, { childList: true, subtree: true, characterData: true });
    return () => {
      region.removeEventListener("scroll", read);
      boxes?.disconnect();
      content?.disconnect();
      region.style.scrollPaddingBlockEnd = "";
      measure.current = () => undefined;
    };
  }, [footer]);
  const showMore = () => {
    const element = footer.current;
    const region = regionOf(element);
    if (element === null || region === null) {
      return;
    }
    region.scrollTop += Math.max(region.clientHeight - element.offsetHeight, 0);
    measure.current();
  };
  return { below, showMore };
}

export interface StickyFooterProps {
  /** The rows of the footer under the cue: a blocking line, the buttons. */
  readonly children: ReactNode;
  /** `data-testid` of the "More below" button, for example `SF-07-more-below`. */
  readonly cueTestId?: string | undefined;
  readonly className?: string | undefined;
}

export function StickyFooter({ children, cueTestId, className }: StickyFooterProps) {
  const footer = useRef<HTMLDivElement>(null);
  const { below, showMore } = useContentBelow(footer);
  return (
    <div
      ref={footer}
      className={cn(
        "sticky -bottom-[var(--gutter)] z-[var(--z-sticky)] -mb-[var(--gutter)] mt-auto flex flex-col gap-2 border-t border-hairline bg-canvas py-3",
        className,
      )}
    >
      {below ? (
        <div {...{ [CUE_ROW]: "" }} className="flex justify-center">
          <Button
            variant="link"
            size="sm"
            icon={CaretDown}
            data-testid={cueTestId}
            onClick={showMore}
          >
            {t("common.moreBelow")}
          </Button>
        </div>
      ) : null}
      {children}
    </div>
  );
}
