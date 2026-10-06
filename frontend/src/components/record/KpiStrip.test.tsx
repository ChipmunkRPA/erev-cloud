// @vitest-environment jsdom
// DS-CMP-06 (DESIGN_SYSTEM §7.2; SCREENS §4.1.4): the KPI strip is a description list of Explain
// triggers; a proportion above its reference shows the warning chip, and the secondary line states the
// proportion in text.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { formatPercent, registerCurrencies } from "../../lib/format";
import { ExplainContext } from "../explain/ExplainTrigger";
import { type Kpi, KpiStrip, ratioAboveOne } from "./KpiStrip";

beforeAll(() => {
  registerCurrencies([{ code: "USD", minor_unit: 2 }]);
});

afterEach(() => {
  cleanup();
});

const OVER = "Over transaction price";

function kpis(onExplain: (id: string) => void): readonly Kpi[] {
  return [
    {
      id: "transactionPrice",
      label: "Transaction price",
      value: "120000.00",
      currency: "USD",
      onExplain: () => onExplain("transactionPrice"),
    },
    {
      id: "billed",
      label: "Billed",
      value: "130000.00",
      currency: "USD",
      onExplain: () => onExplain("billed"),
      bar: { ratio: "1.0833", overLabel: OVER },
      secondary: `${formatPercent("1.0833")} of transaction price`,
    },
    {
      id: "recognized",
      label: "Recognized",
      value: "55440.00",
      currency: "USD",
      onExplain: () => onExplain("recognized"),
      bar: { ratio: "0.462", overLabel: OVER },
      secondary: `${formatPercent("0.462")} of transaction price`,
    },
  ];
}

function cellOf(label: string): HTMLElement {
  const cell = screen.getByText(label, { selector: "dt" }).parentElement;
  if (cell === null) {
    throw new Error(`No KPI cell for ${label}`);
  }
  return cell;
}

describe("DS-CMP-06", () => {
  it("the strip is a dl with dt labels under the caption heading", () => {
    const { container } = render(
      <KpiStrip heading="Key figures (USD, ASC 606)" kpis={kpis(() => undefined)} />,
    );
    expect(screen.getByRole("heading", { name: "Key figures (USD, ASC 606)" })).toBeTruthy();
    const list = container.querySelector("dl");
    if (list === null) {
      throw new Error("The KPI strip renders no dl");
    }
    expect(Array.from(list.querySelectorAll("dt"), (term) => term.textContent)).toEqual([
      "Transaction price",
      "Billed",
      "Recognized",
    ]);
    expect(list.querySelectorAll("dd")).toHaveLength(3);
  });

  it("each computed value is a button named Explain <label>, <currency> <value>", () => {
    const onExplain = vi.fn();
    render(<KpiStrip heading="Key figures (USD, ASC 606)" kpis={kpis(onExplain)} />);
    const recognized = screen.getByRole("button", { name: "Explain Recognized, USD 55,440.00" });
    // The heading carries the currency, so the value shows digits only.
    expect(recognized.textContent).toBe("55,440.00");
    expect(
      screen.getByRole("button", { name: "Explain Transaction price, USD 120,000.00" }),
    ).toBeTruthy();

    fireEvent.click(recognized);
    fireEvent.keyDown(recognized, { key: "e" });
    expect(onExplain.mock.calls).toEqual([["recognized"], ["recognized"]]);
  });

  // SCREENS §4.1.4, §6.3 list level (rev 1.21): a value the trace holds at no node of its own names a
  // list of the host, and its trigger opens that list, not a figure.
  it("a cell that names a list opens the host's list level, and a cell that names a figure opens the figure", () => {
    const open = vi.fn();
    const openList = vi.fn();
    render(
      <ExplainContext.Provider value={{ open, openList }}>
        <KpiStrip
          heading="Key figures at Sep 2026 (USD, ASC 606)"
          kpis={[
            {
              id: "recognized",
              label: "Recognized",
              value: "55440.00",
              currency: "USD",
              explain: { list: "recognized" },
            },
            {
              id: "awaitingTrigger",
              label: "Awaiting trigger",
              value: "0.00",
              currency: "USD",
              explain: {
                figureRef: {
                  objectType: "contract_version",
                  id: "v-1",
                  measure: "awaiting_trigger",
                },
                context: "SF-ORD-10001 · ASC 606 · AVM-US",
              },
            },
          ]}
        />
      </ExplainContext.Provider>,
    );
    const recognized = screen.getByRole("button", { name: "Explain Recognized, USD 55,440.00" });
    fireEvent.click(recognized);
    fireEvent.keyDown(recognized, { key: "E" });
    expect(openList.mock.calls).toEqual([
      ["recognized", recognized],
      ["recognized", recognized],
    ]);
    expect(open).not.toHaveBeenCalled();

    const awaiting = screen.getByRole("button", { name: "Explain Awaiting trigger, USD 0.00" });
    fireEvent.click(awaiting);
    expect(open.mock.calls).toEqual([
      [
        {
          figure: { objectType: "contract_version", id: "v-1", measure: "awaiting_trigger" },
          label: "Awaiting trigger",
          context: "SF-ORD-10001 · ASC 606 · AVM-US",
        },
        awaiting,
      ],
    ]);
    expect(openList).toHaveBeenCalledTimes(2);
  });

  it("a value above its reference shows the warning chip and states the proportion in text", () => {
    render(<KpiStrip heading="Key figures (USD, ASC 606)" kpis={kpis(() => undefined)} />);
    const billed = cellOf("Billed");
    expect(within(billed).getByText(OVER).getAttribute("data-tone")).toBe("warning");
    expect(within(billed).getByText("108.3% of transaction price")).toBeTruthy();
    const billedBar = billed.querySelector("[data-kpi-bar]");
    expect(billedBar?.getAttribute("aria-hidden")).toBe("true");
    expect((billedBar?.firstElementChild as HTMLElement | null)?.style.inlineSize).toBe("100%");

    const recognized = cellOf("Recognized");
    expect(within(recognized).queryByText(OVER)).toBeNull();
    expect(within(recognized).getByText("46.2% of transaction price")).toBeTruthy();
    expect(within(cellOf("Transaction price")).queryByText(OVER)).toBeNull();
  });

  it("ratios are compared on their digits", () => {
    expect(ratioAboveOne("0.999")).toBe(false);
    expect(ratioAboveOne("1")).toBe(false);
    expect(ratioAboveOne("1.0000")).toBe(false);
    expect(ratioAboveOne("1.0001")).toBe(true);
    expect(ratioAboveOne("01.5")).toBe(true);
    expect(ratioAboveOne("12")).toBe(true);
    expect(() => ratioAboveOne("-0.5")).toThrow("Not a non-negative ratio");
  });

  it("while loading the labels stay visible and values are skeletons", () => {
    const { container } = render(
      <KpiStrip heading="Key figures (USD, ASC 606)" kpis={kpis(() => undefined)} loading />,
    );
    expect(container.firstElementChild?.getAttribute("aria-busy")).toBe("true");
    expect(screen.getByText("Billed")).toBeTruthy();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(container.querySelectorAll("[data-skeleton]")).toHaveLength(3);
  });

  it("a text value renders as given, without number formatting", () => {
    render(
      <KpiStrip
        heading="Key figures"
        kpis={[
          { id: "checked", label: "Events checked", value: "9112", currency: "", kind: "count" },
          { id: "failure", label: "First failure", value: null, currency: "", kind: "count" },
          {
            id: "chain",
            label: "Last chain value",
            value: "1a09e4b2…7c21",
            currency: "",
            kind: "text",
            testId: "chain-value",
          },
        ]}
      />,
    );
    expect(within(cellOf("Events checked")).getByText("9,112")).toBeTruthy();
    expect(within(cellOf("First failure")).getByText("—")).toBeTruthy();
    expect(screen.getByTestId("chain-value").textContent).toBe("1a09e4b2…7c21");
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("a figure the caller formatted renders as given, in the figure style and unmasked", () => {
    render(
      <KpiStrip
        heading="Estimate figures of version 3 (USD)"
        compact
        kpis={[
          { id: "total", label: "Estimated total costs", value: "850000.00", currency: "USD" },
          {
            id: "progress",
            label: "Progress",
            value: "59.1%",
            currency: "USD",
            kind: "figure",
            testId: "progress",
          },
          { id: "rate", label: "Rate", value: null, currency: "USD", kind: "figure" },
        ]}
      />,
    );
    expect(within(cellOf("Estimated total costs")).getByText("850,000.00")).toBeTruthy();
    const progress = screen.getByTestId("progress");
    expect(progress.textContent).toBe("59.1%");
    expect(progress.className).toContain("num");
    // Unlike an identifier, a formatted figure is no volatile value: captures show it.
    expect(progress.hasAttribute("data-volatile")).toBe(false);
    expect(within(cellOf("Rate")).getByText("—")).toBeTruthy();
  });

  it("refuses more cells than the variant allows", () => {
    const many = Array.from({ length: 5 }, (_, index) => ({
      id: String(index),
      label: `Figure ${String(index)}`,
      value: "1.00",
      currency: "USD",
    }));
    expect(() => render(<KpiStrip heading="Key figures" kpis={many} compact />)).toThrow(
      "at most 4 cells",
    );
  });
});
