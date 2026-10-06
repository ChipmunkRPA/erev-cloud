// jsdom has no layout. TanStack Virtual measures its scroll element through `offsetHeight` and renders no
// rows for a 0 px viewport, so suites give the `role="grid"` viewport and any `data-virtual-viewport`
// element a height and every other element none.
import { afterEach, beforeEach } from "vitest";

export const GRID_VIEWPORT_PX = 720;

export function installGridViewport(heightPx: number = GRID_VIEWPORT_PX): void {
  const original = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetHeight");
  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
      configurable: true,
      get(this: HTMLElement) {
        return this.getAttribute("role") === "grid" || this.hasAttribute("data-virtual-viewport")
          ? heightPx
          : 0;
      },
    });
  });
  afterEach(() => {
    if (original !== undefined) {
      Object.defineProperty(HTMLElement.prototype, "offsetHeight", original);
    }
  });
}
