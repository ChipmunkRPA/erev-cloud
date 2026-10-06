// REQ-SEC-011 on the clipboard (05 UPL-20, THR-13; DESIGN_SYSTEM DS-CMP-10 "Copy"): the rule of the
// server's CSV and XLSX writers, applied to the text a grid copies.
import { describe, expect, it } from "vitest";

import { clipboardCell } from "./clipboard";

describe("REQ-SEC-011 clipboardCell", () => {
  it("prefixes text that begins with =, +, -, @, tab or carriage return with an apostrophe", () => {
    for (const trigger of ["=", "+", "-", "@"]) {
      expect(clipboardCell(`${trigger}SUM(A1:A9)`, "text")).toBe(`'${trigger}SUM(A1:A9)`);
      expect(clipboardCell(`${trigger}SUM(A1:A9)`, "identifier")).toBe(`'${trigger}SUM(A1:A9)`);
    }
    expect(clipboardCell("\t=1+1", "text")).toBe("' =1+1");
    expect(clipboardCell("\r=1+1", "user")).toBe("' =1+1");
  });

  it("leaves other text as it is", () => {
    expect(clipboardCell("Pellworth Logistics Inc. (Demo)", "text")).toBe(
      "Pellworth Logistics Inc. (Demo)",
    );
    expect(clipboardCell("SF-ORD-10001", "identifier")).toBe("SF-ORD-10001");
    expect(clipboardCell("a=b+c", "text")).toBe("a=b+c");
    expect(clipboardCell("", "text")).toBe("");
    expect(clipboardCell("2026-09-30", "date")).toBe("2026-09-30");
  });

  it("keeps a plain decimal of a money or number column numeric", () => {
    expect(clipboardCell("-1200.50", "money")).toBe("-1200.50");
    expect(clipboardCell("-3", "number")).toBe("-3");
    expect(clipboardCell("240000.00", "money")).toBe("240000.00");
  });

  it("treats anything else in a numeric column, and a signed number in a text column, as text", () => {
    expect(clipboardCell("=1+1", "money")).toBe("'=1+1");
    expect(clipboardCell("-1+1", "number")).toBe("'-1+1");
    expect(clipboardCell("+5", "number")).toBe("'+5");
    expect(clipboardCell("-1200.50", "text")).toBe("'-1200.50");
  });

  it("turns a tab or line break inside a cell into one space", () => {
    expect(clipboardCell("Marrowby\t=1+1\r\nnext", "text")).toBe("Marrowby =1+1 next");
    expect(clipboardCell("line one\nline two", "text")).toBe("line one line two");
  });
});
