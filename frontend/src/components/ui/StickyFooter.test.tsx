// @vitest-environment jsdom
// Sticky footer cue (DESIGN_SYSTEM DS-CMP-16 item 6 rev 1.9, DS-CMP-18; DS-A11Y-03): "More below" is
// the footer's first row while content of the scrolling region lies beneath it, scrolls one view less
// the footer, and the region's scroll padding holds the footer with the cue's row in both states.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { StickyFooter } from "./StickyFooter";

afterEach(() => {
  cleanup();
});

function renderFooter() {
  render(
    <main>
      <p>Step content</p>
      <StickyFooter cueTestId="SF-07-more-below">
        <button type="button">Next</button>
      </StickyFooter>
    </main>,
  );
  const region = screen.getByRole("main");
  const footer = screen.getByRole("button", { name: "Next" }).parentElement;
  if (footer === null) {
    throw new Error("The footer did not render");
  }
  return { region, footer };
}

/** jsdom has no layout: the boxes of the region and of the footer are given. */
function lay(region: HTMLElement, footer: HTMLElement, scrollHeight: number, clientHeight: number) {
  Object.defineProperty(region, "scrollHeight", { configurable: true, value: scrollHeight });
  Object.defineProperty(region, "clientHeight", { configurable: true, value: clientHeight });
  Object.defineProperty(region, "scrollTop", { configurable: true, writable: true, value: 0 });
  Object.defineProperty(footer, "offsetHeight", { configurable: true, value: 80 });
}

describe("StickyFooter", () => {
  it("shows no cue while nothing lies beneath, and reserves the cue's row in the scroll padding", () => {
    const { region, footer } = renderFooter();

    expect(screen.queryByRole("button", { name: "More below" })).toBeNull();
    lay(region, footer, 600, 600);
    fireEvent.scroll(region);
    expect(screen.queryByRole("button", { name: "More below" })).toBeNull();
    // DS-A11Y-03: the padding already holds the row the cue would add.
    expect(region.style.scrollPaddingBlockEnd).toBe("calc(80px + var(--control-h-sm) + 0px)");
  });

  it("More below is the first row while content lies beneath, and scrolls one view less the footer", async () => {
    const { region, footer } = renderFooter();
    // A region of 600 px that holds 1,400 px under a footer of 80 px.
    lay(region, footer, 1400, 600);
    fireEvent.scroll(region);

    const more = await screen.findByRole("button", { name: "More below" });
    expect(more.getAttribute("data-testid")).toBe("SF-07-more-below");
    // Inside the footer, above its own rows: the cue covers nothing of the page.
    expect(footer.firstElementChild?.contains(more)).toBe(true);
    await waitFor(() => expect(region.style.scrollPaddingBlockEnd).toBe("80px"));

    fireEvent.click(more);
    expect(region.scrollTop).toBe(520);
    expect(screen.getByRole("button", { name: "More below" })).toBeTruthy();
    // The second view reaches the end: 1,400 - 600 - 1,040 leaves nothing beneath.
    fireEvent.click(screen.getByRole("button", { name: "More below" }));
    expect(region.scrollTop).toBe(1040);
    await waitFor(() => expect(screen.queryByRole("button", { name: "More below" })).toBeNull());
  });

  it("measures again when the content of the region changes without a scroll or a resize", async () => {
    const { region, footer } = renderFooter();
    expect(screen.queryByRole("button", { name: "More below" })).toBeNull();

    // Rows arrive after the first paint.
    lay(region, footer, 900, 600);
    region.insertBefore(document.createElement("p"), footer);
    expect(await screen.findByRole("button", { name: "More below" })).toBeTruthy();
  });

  it("clears the scroll padding of the region when the footer leaves", () => {
    const { region, footer } = renderFooter();
    lay(region, footer, 600, 600);
    fireEvent.scroll(region);
    expect(region.style.scrollPaddingBlockEnd).not.toBe("");
    cleanup();
    expect(region.style.scrollPaddingBlockEnd).toBe("");
  });
});
