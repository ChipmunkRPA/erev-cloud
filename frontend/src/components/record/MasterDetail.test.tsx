// @vitest-environment jsdom
// DS-CMP-08 (DESIGN_SYSTEM §7.2; APG Listbox): selection follows focus with a 150 ms debounced detail
// load, J and K move outside fields, and the resize handle is a keyboard separator whose width persists.
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { installGridViewport } from "../../test/layout";
import {
  DETAIL_DEBOUNCE_MS,
  MasterDetail,
  type MasterItem,
  VIRTUALIZE_ABOVE,
} from "./MasterDetail";

installGridViewport();

const ITEMS: readonly MasterItem[] = [
  { id: "o1", name: "Platform subscription", identifier: "POB-1" },
  { id: "o2", name: "Implementation services", identifier: "POB-2" },
  { id: "o3", name: "Support plan", identifier: "POB-3" },
];

// Node's own `localStorage` global can shadow the jsdom one without a backing file, so the suite
// installs an in-memory Storage.
function memoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() {
      return values.size;
    },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => Array.from(values.keys())[index] ?? null,
    removeItem: (key) => {
      values.delete(key);
    },
    setItem: (key, value) => {
      values.set(key, value);
    },
  };
}

beforeEach(() => {
  Object.defineProperty(window, "localStorage", { configurable: true, value: memoryStorage() });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function renderList(onSelect: (id: string) => void, selectedId: string | null = "o1") {
  return render(
    <MasterDetail
      type="obligations"
      listLabel="Obligations"
      items={ITEMS}
      selectedId={selectedId}
      onSelect={onSelect}
      toolbar={<input aria-label="Filter obligations" />}
      detailLabel="Obligation details: Platform subscription"
      noSelection="Select an obligation to see its allocation, schedule and history."
    >
      <h2>Platform subscription</h2>
      <button type="button">Edit dates</button>
    </MasterDetail>,
  );
}

function option(name: string): HTMLElement {
  return screen.getByRole("option", { name: new RegExp(`^${name}`) });
}

describe("DS-CMP-08", () => {
  it("the list has role listbox; Up and Down select with a 150 ms debounced detail load", () => {
    vi.useFakeTimers();
    const onSelect = vi.fn();
    renderList(onSelect);
    const listbox = screen.getByRole("listbox", { name: "Obligations" });
    expect(screen.getAllByRole("option").map((row) => row.getAttribute("aria-selected"))).toEqual([
      "true",
      "false",
      "false",
    ]);

    option("Platform subscription").focus();
    fireEvent.keyDown(listbox, { key: "ArrowDown" });
    expect(option("Implementation services").getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(option("Implementation services"));
    expect(onSelect).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(DETAIL_DEBOUNCE_MS - 1);
    });
    expect(onSelect).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(onSelect.mock.calls).toEqual([["o2"]]);

    // Moves inside the debounce window load only the last selection.
    fireEvent.keyDown(listbox, { key: "ArrowDown" });
    fireEvent.keyDown(listbox, { key: "ArrowUp" });
    fireEvent.keyDown(listbox, { key: "Home" });
    act(() => {
      vi.advanceTimersByTime(DETAIL_DEBOUNCE_MS);
    });
    expect(onSelect.mock.calls).toEqual([["o2"], ["o1"]]);
    expect(document.activeElement).toBe(option("Platform subscription"));
  });

  it("J and K move when focus is outside a field", () => {
    vi.useFakeTimers();
    const onSelect = vi.fn();
    renderList(onSelect);
    fireEvent.keyDown(document.body, { key: "j" });
    fireEvent.keyDown(document.body, { key: "j" });
    expect(option("Support plan").getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(document.body, { key: "k" });
    expect(option("Implementation services").getAttribute("aria-selected")).toBe("true");
    act(() => {
      vi.advanceTimersByTime(DETAIL_DEBOUNCE_MS);
    });
    expect(onSelect.mock.calls).toEqual([["o2"]]);

    const filter = screen.getByRole("textbox", { name: "Filter obligations" });
    filter.focus();
    fireEvent.keyDown(filter, { key: "j" });
    expect(option("Implementation services").getAttribute("aria-selected")).toBe("true");
  });

  it("Enter moves focus to the detail heading and Esc returns it to the selected row", () => {
    renderList(() => undefined);
    const detail = screen.getByRole("region", {
      name: "Obligation details: Platform subscription",
    });
    option("Platform subscription").focus();
    fireEvent.keyDown(option("Platform subscription"), { key: "Enter" });
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { name: "Platform subscription" }),
    );

    const edit = screen.getByRole("button", { name: "Edit dates" });
    edit.focus();
    fireEvent.keyDown(edit, { key: "Escape" });
    expect(document.activeElement).toBe(option("Platform subscription"));
    expect(detail.contains(document.activeElement)).toBe(false);
  });

  it("the resize handle is a separator moving ±16 px with Left and Right; the width persists", () => {
    const { unmount } = renderList(() => undefined);
    const handle = screen.getByRole("separator", { name: "Resize list" });
    expect(handle.getAttribute("aria-orientation")).toBe("vertical");
    expect(handle.getAttribute("aria-valuenow")).toBe("360");
    expect(handle.getAttribute("aria-valuemin")).toBe("280");
    expect(handle.getAttribute("aria-valuemax")).toBe("480");
    expect(handle.tabIndex).toBe(0);

    fireEvent.keyDown(handle, { key: "ArrowRight" });
    expect(handle.getAttribute("aria-valuenow")).toBe("376");
    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    expect(handle.getAttribute("aria-valuenow")).toBe("344");
    fireEvent.keyDown(handle, { key: "End" });
    expect(handle.getAttribute("aria-valuenow")).toBe("480");
    fireEvent.keyDown(handle, { key: "ArrowRight" });
    expect(handle.getAttribute("aria-valuenow")).toBe("480");
    fireEvent.keyDown(handle, { key: "Home" });
    fireEvent.keyDown(handle, { key: "ArrowRight" });
    expect(handle.getAttribute("aria-valuenow")).toBe("296");
    expect(window.localStorage.getItem("erev.master.obligations")).toBe("296");

    unmount();
    renderList(() => undefined);
    expect(
      screen.getByRole("separator", { name: "Resize list" }).getAttribute("aria-valuenow"),
    ).toBe("296");
  });

  it("a pointer press selects at once and dragging the handle resizes within the limits", () => {
    const onSelect = vi.fn();
    renderList(onSelect);
    fireEvent.mouseDown(option("Support plan"));
    expect(onSelect.mock.calls).toEqual([["o3"]]);
    expect(option("Support plan").getAttribute("aria-selected")).toBe("true");

    // jsdom has no PointerEvent; without one fireEvent sends a plain Event that carries no clientX.
    vi.stubGlobal("PointerEvent", MouseEvent);
    const handle = screen.getByRole("separator", { name: "Resize list" });
    fireEvent.pointerDown(handle, { clientX: 400 });
    fireEvent.pointerMove(document, { clientX: 440 });
    expect(handle.getAttribute("aria-valuenow")).toBe("400");
    fireEvent.pointerMove(document, { clientX: 1000 });
    expect(handle.getAttribute("aria-valuenow")).toBe("480");
    fireEvent.pointerUp(document);
    fireEvent.pointerMove(document, { clientX: 100 });
    expect(handle.getAttribute("aria-valuenow")).toBe("480");
  });

  it("items that name a group are listed under its caption, which each option names", () => {
    const grouped: readonly MasterItem[] = [
      { id: "e1", name: "BONUS-CB-01", mono: true, group: "Variable consideration" },
      { id: "e2", name: "REBATE-DR-01", mono: true, group: "Variable consideration" },
      { id: "e3", name: "EAC", mono: true, group: "Estimated total costs" },
    ];
    const onSelect = vi.fn();
    render(
      <MasterDetail
        type="estimates"
        listLabel="Estimated elements"
        listTestId="SF-03-grid-estimates"
        items={grouped}
        selectedId="e1"
        onSelect={onSelect}
        detailLabel="Estimated element details: BONUS-CB-01"
        noSelection="Select an estimated element."
      >
        <h2>BONUS-CB-01</h2>
      </MasterDetail>,
    );
    const list = screen.getByRole("listbox", { name: "Estimated elements" });
    expect(list.getAttribute("data-testid")).toBe("SF-03-grid-estimates");
    // One caption per run of a group; the captions are not options.
    const options = screen.getAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual([
      "BONUS-CB-01",
      "REBATE-DR-01",
      "EAC",
    ]);
    const captionOf = (option: HTMLElement) =>
      document.getElementById(option.getAttribute("aria-describedby") ?? "");
    expect(options.map((option) => captionOf(option)?.textContent)).toEqual([
      "Variable consideration",
      "Variable consideration",
      "Estimated total costs",
    ]);
    expect(captionOf(options[0] as HTMLElement)).toBe(captionOf(options[1] as HTMLElement));
    expect(list.querySelectorAll("[role='presentation']")).toHaveLength(2);
    expect(list.textContent).toBe(
      "Variable considerationBONUS-CB-01REBATE-DR-01Estimated total costsEAC",
    );
    // An identifier as the name is set in mono.
    expect(options[0]?.querySelector(".font-mono")?.textContent).toBe("BONUS-CB-01");
    // The keys move over the options, past the caption between the second and the third.
    fireEvent.keyDown(list, { key: "ArrowDown" });
    expect(document.activeElement).toBe(options[1]);
    fireEvent.keyDown(list, { key: "ArrowDown" });
    expect(document.activeElement).toBe(options[2]);
  });

  it("shows the no-selection text while nothing is selected", () => {
    renderList(() => undefined, null);
    expect(
      screen.getByText("Select an obligation to see its allocation, schedule and history."),
    ).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Platform subscription" })).toBeNull();
  });

  it("virtualizes a list of more than 100 rows and focuses a row scrolled into view", async () => {
    // jsdom has no Element.scrollTo; the stub moves scrollTop and fires the scroll event a browser fires.
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      writable: true,
      value(this: HTMLElement, options: ScrollToOptions) {
        Object.defineProperty(this, "scrollTop", { configurable: true, value: options.top ?? 0 });
        this.dispatchEvent(new Event("scroll"));
      },
    });
    const many = Array.from({ length: VIRTUALIZE_ABOVE + 50 }, (_, index) => ({
      id: `o${String(index)}`,
      name: `Obligation ${String(index + 1).padStart(3, "0")}`,
    }));
    render(
      <MasterDetail
        type="obligations"
        listLabel="Obligations"
        items={many}
        selectedId="o0"
        onSelect={() => undefined}
        detailLabel="Obligation details"
        noSelection="Select an obligation."
      />,
    );

    const options = screen.getAllByRole("option");
    expect(options.length).toBeLessThanOrEqual(40);
    expect(options[0]?.getAttribute("aria-setsize")).toBe("150");
    expect(options[0]?.getAttribute("aria-posinset")).toBe("1");
    // jsdom reports no scroll extent, and TanStack Virtual clamps scroll targets to it.
    const viewport = document.querySelector<HTMLElement>("[data-virtual-viewport]");
    Object.defineProperty(viewport, "clientHeight", { configurable: true, value: 720 });
    Object.defineProperty(viewport, "scrollHeight", { configurable: true, value: 150 * 56 });
    options[0]?.focus();
    fireEvent.keyDown(screen.getByRole("listbox", { name: "Obligations" }), { key: "End" });

    await waitFor(() => expect(document.activeElement?.getAttribute("aria-posinset")).toBe("150"));
    expect(document.activeElement?.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement?.textContent).toContain("Obligation 150");
    expect(screen.getAllByRole("option").length).toBeLessThanOrEqual(40);
    Reflect.deleteProperty(HTMLElement.prototype, "scrollTo");
  });
});
