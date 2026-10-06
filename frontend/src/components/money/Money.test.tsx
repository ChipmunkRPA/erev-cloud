// @vitest-environment jsdom
// DS-FMT-29 (DESIGN_SYSTEM §6.3, DS-CMP-26): <Money> and <Num> speak signs as words and hide the
// parentheses and signs; a non-negative money cell under the parentheses style carries num-pos.
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { configureFormat, registerCurrencies } from "../../lib/format";
import { Money } from "./Money";
import { Num } from "./Num";

beforeAll(() => {
  registerCurrencies([{ code: "USD", minor_unit: 2 }]);
});

afterEach(() => {
  cleanup();
  configureFormat({ negativeStyle: "PARENTHESES" });
});

// The text a screen reader reads: every text node outside aria-hidden subtrees.
function spoken(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) {
    return node.textContent ?? "";
  }
  if (node instanceof Element && node.getAttribute("aria-hidden") === "true") {
    return "";
  }
  return Array.from(node.childNodes, spoken).join("");
}

function rendered(element: React.ReactElement): Element {
  const root = render(element).container.firstElementChild;
  if (root === null) {
    throw new Error("nothing rendered");
  }
  return root;
}

function name(element: Element): string {
  return spoken(element).replace(/\s+/g, " ").trim();
}

describe("DS-FMT-29", () => {
  it("names a negative inline amount USD minus 4,000.00 with the parentheses aria-hidden", () => {
    const root = rendered(<Money value="-4000.00" currency="USD" variant="inline" />);

    expect(name(root)).toBe("USD minus 4,000.00");
    const hidden = Array.from(
      root.querySelectorAll('[aria-hidden="true"]'),
      (node) => node.textContent,
    );
    expect(hidden).toEqual(["(", ")"]);
    expect(root.textContent).toBe("USD minus (4,000.00)");
  });

  it("hides the minus sign under the minus style", () => {
    configureFormat({ negativeStyle: "MINUS" });
    const root = rendered(<Money value="-4000.00" currency="USD" variant="inline" />);

    expect(name(root)).toBe("USD minus 4,000.00");
    const hidden = Array.from(
      root.querySelectorAll('[aria-hidden="true"]'),
      (node) => node.textContent,
    );
    expect(hidden).toEqual(["−"]);
    expect(root.classList.contains("num-pos")).toBe(false);
  });

  it("gives a positive cell num-pos under the parentheses style only", () => {
    const cell = rendered(<Money value="1200.00" currency="USD" />);
    expect(cell.classList.contains("num-pos")).toBe(true);
    expect(cell.classList.contains("num-money")).toBe(true);
    expect(cell.textContent).toBe("1,200.00");
    cleanup();

    configureFormat({ negativeStyle: "MINUS" });
    expect(rendered(<Money value="1200.00" currency="USD" />).classList.contains("num-pos")).toBe(
      false,
    );
  });

  it("renders no value as an em dash named No value", () => {
    const root = rendered(<Money value={null} currency="USD" />);

    expect(name(root)).toBe("No value");
    expect(root.querySelector('[aria-hidden="true"]')?.textContent).toBe("—");
  });

  it("speaks the sign of a percentage-point change", () => {
    expect(name(rendered(<Num value="1.2" kind="pp" />))).toBe("plus 1.2 pp");
    cleanup();
    expect(name(rendered(<Num value="-0.8" kind="pp" />))).toBe("minus 0.8 pp");
  });
});
