// DS-I18N-04 (DESIGN_SYSTEM §9): typed money parses with the format_locale separators.
import { beforeAll, describe, expect, it } from "vitest";

import { parseMoneyInput, registerCurrencies } from "./index";

beforeAll(() => {
  registerCurrencies([
    { code: "USD", minor_unit: 2 },
    { code: "EUR", minor_unit: 2 },
  ]);
});

describe("DS-I18N-04 parseMoneyInput", () => {
  it("parses USD parentheses, U+2212 and canonical input", () => {
    expect(parseMoneyInput("(1,234.56)", "USD", { locale: "en-US" })).toEqual({
      ok: true,
      value: "-1234.56",
    });
    expect(parseMoneyInput("−1,234.56", "USD", { locale: "en-US" })).toEqual({
      ok: true,
      value: "-1234.56",
    });
    expect(parseMoneyInput(" -1234.56 ", "USD", { locale: "en-US" })).toEqual({
      ok: true,
      value: "-1234.56",
    });
    expect(parseMoneyInput("-0.00", "USD", { locale: "en-US" })).toEqual({
      ok: true,
      value: "0.00",
    });
  });

  it("parses de-DE grouping, including the ambiguous 1.234", () => {
    expect(parseMoneyInput("1.234", "EUR", { locale: "de-DE" })).toEqual({
      ok: true,
      value: "1234",
    });
    expect(parseMoneyInput("1.234,5", "EUR", { locale: "de-DE" })).toEqual({
      ok: true,
      value: "1234.5",
    });
  });

  it("rejects more decimals than the minor unit and malformed input", () => {
    expect(parseMoneyInput("12.345", "USD", { locale: "en-US" })).toEqual({
      ok: false,
      error: "too-many-decimals",
    });
    expect(parseMoneyInput("12a", "USD", { locale: "en-US" })).toEqual({
      ok: false,
      error: "invalid",
    });
    expect(parseMoneyInput("(-5)", "USD", { locale: "en-US" })).toEqual({
      ok: false,
      error: "invalid",
    });
  });
});
