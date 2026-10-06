// @vitest-environment jsdom
// DS-CMP-30 (DESIGN_SYSTEM §7.5; SCREENS SCR-ST-01): the skeleton appears only after 150 ms.
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SKELETON_DELAY_MS, Skeleton } from "./Skeleton";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("DS-CMP-30", () => {
  it("the skeleton appears only after 150 ms while the region is busy at once", () => {
    vi.useFakeTimers();
    const { container } = render(<Skeleton region="contracts" shape="rows" count={6} />);
    expect(container.firstElementChild?.getAttribute("aria-busy")).toBe("true");
    expect(screen.getByText("Loading contracts").className).toContain("sr-only");
    expect(container.querySelector("[data-skeleton]")).toBeNull();

    act(() => {
      vi.advanceTimersByTime(SKELETON_DELAY_MS - 1);
    });
    expect(container.querySelector("[data-skeleton]")).toBeNull();

    act(() => {
      vi.advanceTimersByTime(1);
    });
    const blocks = container.querySelector("[data-skeleton]");
    expect(blocks?.getAttribute("aria-hidden")).toBe("true");
    expect(blocks?.children).toHaveLength(6);
  });
});
