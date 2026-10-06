// @vitest-environment jsdom
// DS-CMP-31 (DESIGN_SYSTEM §7.5; APG Radio Group): roving tabindex; arrow keys move and select.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { type SegmentOption, SegmentedControl } from "./SegmentedControl";

afterEach(() => {
  cleanup();
});

type Grain = "month" | "quarter" | "year";

const OPTIONS: readonly SegmentOption<Grain>[] = [
  { value: "month", label: "Month" },
  { value: "quarter", label: "Quarter", disabledReason: "Quarters need a fiscal calendar." },
  { value: "year", label: "Year" },
];

function Harness() {
  const [grain, setGrain] = useState<Grain>("month");
  return (
    <SegmentedControl label="Period grain" options={OPTIONS} value={grain} onChange={setGrain} />
  );
}

function tabIndexes(): string[] {
  return screen.getAllByRole("radio").map((radio) => radio.getAttribute("tabindex") ?? "");
}

describe("DS-CMP-31", () => {
  it("role radiogroup with roving tabindex; arrow keys move and select, skipping a disabled option", () => {
    render(<Harness />);
    expect(screen.getByRole("radiogroup", { name: "Period grain" })).toBeTruthy();
    const month = screen.getByRole("radio", { name: "Month" });
    expect(month.getAttribute("aria-checked")).toBe("true");
    expect(tabIndexes()).toEqual(["0", "-1", "-1"]);

    month.focus();
    fireEvent.keyDown(month, { key: "ArrowRight" });
    const year = screen.getByRole("radio", { name: "Year" });
    expect(year.getAttribute("aria-checked")).toBe("true");
    expect(document.activeElement).toBe(year);
    expect(tabIndexes()).toEqual(["-1", "-1", "0"]);

    fireEvent.keyDown(year, { key: "ArrowDown" });
    expect(screen.getByRole("radio", { name: "Month" }).getAttribute("aria-checked")).toBe("true");
    fireEvent.keyDown(document.activeElement ?? month, { key: "ArrowUp" });
    expect(document.activeElement).toBe(year);

    const quarter = screen.getByRole("radio", { name: "Quarter" });
    expect(quarter.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(quarter);
    expect(quarter.getAttribute("aria-checked")).toBe("false");
  });

  it("mirrors Left and Right in RTL", () => {
    render(
      <div dir="rtl">
        <Harness />
      </div>,
    );
    const month = screen.getByRole("radio", { name: "Month" });
    month.focus();
    fireEvent.keyDown(month, { key: "ArrowLeft" });
    expect(screen.getByRole("radio", { name: "Year" }).getAttribute("aria-checked")).toBe("true");
  });
});
