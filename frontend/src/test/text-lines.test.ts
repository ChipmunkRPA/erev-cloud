// The measure of a sentence's lines (./text-lines.ts) is pinned on the product's Inter file: the advance
// widths of single glyphs, the sum over a sentence, and the breaks of a box.
import { describe, expect, it } from "vitest";

import { textLines, textWidth, TOAST_LINES, TOAST_MESSAGE_BOX } from "./text-lines";

describe("text lines", () => {
  it("measures a text by the advance widths of the product's Inter file", () => {
    // Inter 4 at 2,048 units per em: "m" advances 1,794 units and "i" 496.
    expect(textWidth("m", 2048)).toBe(1794);
    expect(textWidth("i", 2048)).toBe(496);
    expect(textWidth("mi", 2048)).toBe(1794 + 496);
    expect(textWidth("", 13)).toBe(0);
    // `body-sm` is 13 px: ten of each.
    expect(textWidth("mmmmmmmmmm", 13)).toBeCloseTo(113.88, 2);
    expect(textWidth("iiiiiiiiii", 13)).toBeCloseTo(31.48, 2);
    // The characters the catalogue's sentences use beside letters and digits.
    expect(textWidth("1 · 2 – 3 … <>", 13)).toBeGreaterThan(0);
  });

  it("breaks a sentence at spaces into the lines a box holds", () => {
    expect(textLines("Batch 1 · 2 was sent again.", TOAST_MESSAGE_BOX)).toEqual([
      "Batch 1 · 2 was sent again.",
    ]);
    // The toast of SCREENS_B rev 1.71 that the two lines of a toast cut after "record the".
    const handedOver =
      "Batch 1 · 2 was handed over. Download its file, post it in the ledger and record the ERP reference.";
    expect(textLines(handedOver, TOAST_MESSAGE_BOX)).toEqual([
      "Batch 1 · 2 was handed over. Download its",
      "file, post it in the ledger and record the",
      "ERP reference.",
    ]);
    expect(textLines(handedOver, TOAST_MESSAGE_BOX).length).toBeGreaterThan(TOAST_LINES);
    // A wider box holds it in two, and no line is wider than its box.
    const wider = { fontSize: 13, width: 320 };
    const lines = textLines(handedOver, wider);
    expect(lines).toHaveLength(2);
    for (const line of lines) {
      expect(textWidth(line, wider.fontSize)).toBeLessThanOrEqual(wider.width);
    }
    // A word wider than the box stands on a line of its own: a box breaks at spaces only.
    expect(textLines("erev:avenmoor:JR-000209:1:2 differs", { fontSize: 13, width: 60 })).toEqual([
      "erev:avenmoor:JR-000209:1:2",
      "differs",
    ]);
  });

  it("names a character the latin file does not hold", () => {
    expect(() => textWidth("Ж", 13)).toThrow('the latin Inter file has no glyph for "Ж"');
  });
});
