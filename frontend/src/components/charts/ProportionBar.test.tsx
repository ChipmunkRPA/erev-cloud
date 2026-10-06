// @vitest-environment jsdom
// DS-CH-05 (DESIGN_SYSTEM §5.3): the KPI proportion bar is aria-hidden, caps at 100% with the warning chip
// "Over <reference label>", and shows an empty track for zero or a negative ratio.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ProportionBar } from "./ProportionBar";

afterEach(() => {
  cleanup();
});

function fillOf(container: HTMLElement): HTMLElement {
  const bar = container.querySelector<HTMLElement>("[data-kpi-bar]");
  const fill = bar?.firstElementChild;
  if (bar === null || !(fill instanceof HTMLElement)) {
    throw new Error("No proportion bar");
  }
  return fill;
}

describe("DS-CH-05", () => {
  it("is aria-hidden", () => {
    const { container } = render(
      <ProportionBar ratio="0.462" overLabel="Over transaction price" />,
    );
    expect(container.querySelector("[data-kpi-bar]")?.getAttribute("aria-hidden")).toBe("true");
    expect(screen.queryByText("Over transaction price")).toBeNull();
    expect(fillOf(container).getAttribute("style")).toContain("0.462");
  });

  it("a value of 110% of the reference renders a full bar and the chip Over <reference label>", () => {
    const { container } = render(<ProportionBar ratio="1.10" overLabel="Over transaction price" />);
    expect(fillOf(container).style.inlineSize).toBe("100%");
    expect(screen.getByText("Over transaction price").getAttribute("data-tone")).toBe("warning");
  });

  it("exactly 100% is full without the chip", () => {
    const { container } = render(
      <ProportionBar ratio="1.0000" overLabel="Over transaction price" />,
    );
    expect(fillOf(container).getAttribute("style")).toContain("1.0000");
    expect(screen.queryByText("Over transaction price")).toBeNull();
  });

  it("zero or a negative value shows an empty track", () => {
    for (const ratio of ["0", "0.000", "-0.25"]) {
      const { container, unmount } = render(
        <ProportionBar ratio={ratio} overLabel="Over transaction price" />,
      );
      expect(fillOf(container).style.inlineSize).toBe("0%");
      expect(screen.queryByText("Over transaction price")).toBeNull();
      unmount();
    }
  });

  it("refuses a value that is not a decimal ratio", () => {
    expect(() => render(<ProportionBar ratio="1e2" overLabel="Over transaction price" />)).toThrow(
      "Not a ratio",
    );
  });
});
