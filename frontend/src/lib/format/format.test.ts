// DS-VER-03 (DESIGN_SYSTEM §13, §6.4): the format module under both tenant negative styles.
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import {
  configureFormat,
  formatCompact,
  formatDate,
  formatMoney,
  formatNumber,
  formatPercent,
  formatPeriod,
  formatRate,
  formatTimestamp,
  type NegativeStyle,
  registerCurrencies,
} from "./index";

// ISO 4217 minor units, as the API currency reference supplies them.
beforeAll(() => {
  registerCurrencies([
    { code: "USD", minor_unit: 2 },
    { code: "JPY", minor_unit: 0 },
    { code: "BHD", minor_unit: 3 },
    { code: "CLF", minor_unit: 4 },
  ]);
});

afterEach(() => {
  configureFormat({ locale: "en-US", negativeStyle: "PARENTHESES" });
});

const NBSP = "\u00A0";
const STYLES: readonly NegativeStyle[] = ["PARENTHESES", "MINUS"];

describe.each(STYLES)("DS-VER-03 worked examples (%s)", (style) => {
  const parentheses = style === "PARENTHESES";
  const options = { negativeStyle: style } as const;

  it("formats the §6.4 rows", () => {
    expect(formatMoney("1234567.8900", "USD", options)).toBe("1,234,567.89");
    expect(formatMoney("1234567.8900", "USD", { ...options, variant: "inline" })).toBe(
      `USD${NBSP}1,234,567.89`,
    );
    expect(formatMoney("1234567.8900", "USD", { variant: "csv" })).toBe("1234567.89");

    expect(formatMoney("-4000.0000", "USD", options)).toBe(
      parentheses ? "(4,000.00)" : "−4,000.00",
    );
    expect(formatMoney("-4000.0000", "USD", { ...options, variant: "inline" })).toBe(
      parentheses ? `USD${NBSP}(4,000.00)` : `USD${NBSP}−4,000.00`,
    );
    expect(formatMoney("-4000.0000", "USD", { variant: "csv" })).toBe("-4000.00");

    expect(formatMoney("0.0000", "USD", options)).toBe("0.00");
    expect(formatMoney("0.0000", "USD", { variant: "csv" })).toBe("0.00");
    expect(formatMoney("-0.0040", "USD", options)).toBe("0.00");
    expect(formatMoney("-0.0040", "USD", { ...options, variant: "kpi" })).toBe(`USD${NBSP}0.00`);
    expect(formatMoney("-0.0040", "USD", { variant: "csv" })).toBe("-0.0040");

    expect(formatMoney("150000.0000", "JPY", options)).toBe("150,000");
    expect(formatMoney("150000.0000", "JPY", { variant: "csv" })).toBe("150000");
    expect(formatMoney("12.3450", "BHD", options)).toBe("12.345");
    expect(formatMoney("12.3450", "BHD", { variant: "csv" })).toBe("12.345");

    expect(formatMoney(null, "USD", options)).toBe("—");
    expect(formatMoney(null, "USD", { variant: "csv" })).toBe("");

    expect(formatPercent("0.333333333333333333", { ...options, kind: "share" })).toBe("33.33%");
    expect(formatDate("2026-09-07")).toBe("07 Sep 2026");
    expect(formatTimestamp("2026-09-07T18:05:31Z")).toBe("07 Sep 2026 18:05 UTC");
    expect(formatTimestamp("2026-09-07T18:05:31Z", { seconds: true })).toBe(
      "07 Sep 2026 18:05:31 UTC",
    );
  });

  it("applies the tenant style through configureFormat", () => {
    configureFormat({ negativeStyle: style });

    expect(formatMoney("-4000.0000", "USD")).toBe(parentheses ? "(4,000.00)" : "−4,000.00");
  });
});

describe.each(STYLES)("DS-VER-03 ties, negatives and compact forms (%s)", (style) => {
  const parentheses = style === "PARENTHESES";
  const options = { negativeStyle: style } as const;

  it("rounds ties half away from zero", () => {
    expect(formatMoney("2.345", "USD", options)).toBe("2.35");
    expect(formatMoney("-2.345", "USD", options)).toBe(parentheses ? "(2.35)" : "−2.35");
  });

  it("formats negative percent, percentage points, compact and delta forms", () => {
    expect(formatPercent("-0.04", options)).toBe(parentheses ? "(4.0%)" : "−4.0%");
    expect(formatPercent("0.125", options)).toBe("12.5%");
    expect(formatPercent("1.2", { ...options, kind: "pp" })).toBe("+1.2 pp");
    expect(formatPercent("-0.8", { ...options, kind: "pp" })).toBe(
      parentheses ? "(0.8) pp" : "−0.8 pp",
    );
    expect(formatPercent("0.0", { ...options, kind: "pp" })).toBe("0.0 pp");
    expect(formatCompact("1250000", options)).toBe("1.25M");
    expect(formatCompact("-845000", options)).toBe(parentheses ? "(845K)" : "−845K");
    expect(formatCompact("999950", options)).toBe("1M");
    expect(formatCompact("12", options)).toBe("12");
    expect(formatMoney("45000.00", "USD", { ...options, delta: true })).toBe("+45,000.00");
    expect(formatMoney("-4000.00", "USD", { ...options, delta: true })).toBe(
      parentheses ? "(4,000.00)" : "−4,000.00",
    );
    expect(formatMoney("0.00", "USD", { ...options, delta: true })).toBe("0.00");
  });

  it("keeps CLF at 4 decimals and uses de-DE separators", () => {
    expect(formatMoney("1.2346", "CLF", options)).toBe("1.2346");
    expect(formatMoney("1234567.89", "USD", { ...options, locale: "de-DE" })).toBe("1.234.567,89");
    expect(formatMoney("-1234567.89", "USD", { ...options, locale: "de-DE" })).toBe(
      parentheses ? "(1.234.567,89)" : "−1.234.567,89",
    );
  });
});

describe("DS-VER-03 time-zone independence", () => {
  it("formats a plain date without shifting in any browser time zone", () => {
    const original = process.env.TZ;
    try {
      for (const zone of ["America/Los_Angeles", "Pacific/Auckland"]) {
        process.env.TZ = zone;
        expect(formatDate("2026-09-07")).toBe("07 Sep 2026");
        expect(formatDate("2026-01-01")).toBe("01 Jan 2026");
        expect(formatTimestamp("2026-12-31T23:59:00Z")).toBe("31 Dec 2026 23:59 UTC");
      }
    } finally {
      if (original === undefined) {
        delete process.env.TZ;
      } else {
        process.env.TZ = original;
      }
    }
  });
});

describe("DS-FMT quantities, rates, counts and periods", () => {
  it("formats quantities, unit rates, FX rates and counts", () => {
    expect(formatNumber("12.0000", { kind: "quantity" })).toBe("12");
    expect(formatNumber("2.5", { kind: "quantity" })).toBe("2.5");
    expect(formatNumber("0.33333", { kind: "quantity" })).toBe("0.3333");
    expect(formatNumber(1204, { kind: "count" })).toBe("1,204");
    expect(formatRate("125", { kind: "unit", currency: "USD" })).toBe("125.00");
    expect(formatRate("0.333333333", { kind: "unit", currency: "USD" })).toBe("0.333333");
    expect(formatRate("1.08345", { kind: "fx" })).toBe("1.083450");
  });

  it("labels periods", () => {
    expect(formatPeriod("FY2026-P09", { startDate: "2026-09-01" })).toBe("Sep 2026");
    expect(formatPeriod("FY2026-P09")).toBe("FY2026 P09");
    expect(formatPeriod("FY2026-Q3")).toBe("FY2026 Q3");
    expect(formatPeriod("FY2026")).toBe("FY2026");
  });

  it("refuses unknown currencies and malformed values", () => {
    expect(() => formatMoney("1.00", "XTS")).toThrow(
      "Unknown currency XTS: register the API currency reference first",
    );
    expect(() => formatMoney("1e3", "USD")).toThrow("Not a decimal string: 1e3");
    expect(() => formatDate("2026-13-01")).toThrow("Not a business date: 2026-13-01");
    expect(() => formatNumber(1.5, { kind: "count" })).toThrow();
  });
});
