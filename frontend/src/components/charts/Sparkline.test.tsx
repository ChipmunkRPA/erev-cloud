// @vitest-environment jsdom
// DS-CH-04 (DESIGN_SYSTEM §5.3): the sparkline is a small SVG image named with the measure, range, first
// and last values and the low and high, built without Recharts.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { formatPeriod, registerCurrencies } from "../../lib/format";
import { compareDecimal } from "./chartKit";
import { type SparkPoint, Sparkline } from "./Sparkline";
import source from "./Sparkline.tsx?raw";

beforeAll(() => {
  registerCurrencies([{ code: "USD", minor_unit: 2 }]);
});

afterEach(() => {
  cleanup();
});

const MONTHS: readonly (readonly [string, string])[] = [
  ["2025-10-01", "40000.00"],
  ["2025-11-01", "41250.00"],
  ["2025-12-01", "38500.00"],
  ["2026-01-01", "42000.00"],
  ["2026-02-01", "43100.00"],
  ["2026-03-01", "44800.00"],
  ["2026-04-01", "45500.00"],
  ["2026-05-01", "47250.00"],
  ["2026-06-01", "48000.00"],
  ["2026-07-01", "49900.00"],
  ["2026-08-01", "51000.00"],
  ["2026-09-01", "52000.00"],
];

function points(): readonly SparkPoint[] {
  return MONTHS.map(([startDate, value], index) => ({
    label: formatPeriod(`FY2026-P${String(index + 1).padStart(2, "0")}`, { startDate }),
    value,
  }));
}

describe("DS-CH-04", () => {
  it("is an SVG image named with measure, range, first, last, low and high", () => {
    render(<Sparkline measure="Recognized revenue" currency="USD" points={points()} />);
    const image = screen.getByRole("img", {
      name: "Recognized revenue, Oct 2025 to Sep 2026, from USD 40,000.00 to USD 52,000.00, low USD 38,500.00, high USD 52,000.00",
    });
    expect(image.tagName.toLowerCase()).toBe("svg");
    expect([image.getAttribute("width"), image.getAttribute("height")]).toEqual(["80", "24"]);
    expect(image.querySelector("polyline")?.getAttribute("stroke")).toBe("var(--viz-sparkline)");
    expect(image.querySelector("[data-end-dot]")?.getAttribute("fill")).toBe("var(--fg-1)");
    expect(image.querySelector("[data-zero-line]")).toBeNull();
  });

  it("uses 64 × 20 px in grid cells", () => {
    render(<Sparkline measure="Billed" currency="USD" points={points()} size="cell" />);
    const image = screen.getByRole("img");
    expect([image.getAttribute("width"), image.getAttribute("height")]).toEqual(["64", "20"]);
  });

  it("draws the zero line only when the series crosses zero", () => {
    render(
      <Sparkline
        measure="Net change"
        currency="USD"
        points={[
          { label: "Jul 2026", value: "-1200.00" },
          { label: "Aug 2026", value: "300.00" },
          { label: "Sep 2026", value: "900.00" },
        ]}
      />,
    );
    const image = screen.getByRole("img", {
      name: "Net change, Jul 2026 to Sep 2026, from USD (1,200.00) to USD 900.00, low USD (1,200.00), high USD 900.00",
    });
    expect(image.querySelector("[data-zero-line]")?.getAttribute("stroke")).toBe("var(--viz-grid)");
  });

  it("has no Recharts import", () => {
    expect(source).toContain("export function Sparkline");
    expect(source).not.toMatch(/from\s+["']recharts["']/);
    render(<Sparkline measure="Recognized revenue" currency="USD" points={points()} />);
    expect(document.querySelector("[class*='recharts']")).toBeNull();
  });

  it("chooses low and high on the digits of the decimal strings", () => {
    expect(compareDecimal("10.5", "9.75")).toBe(1);
    expect(compareDecimal("-10.5", "-9.75")).toBe(-1);
    expect(compareDecimal("0012.3400", "12.34")).toBe(0);
    expect(compareDecimal("-0.00", "0")).toBe(0);
    expect(compareDecimal("9007199254740993.01", "9007199254740993.02")).toBe(-1);
    expect(() => compareDecimal("1e3", "1")).toThrow("Not a decimal string");
  });
});
