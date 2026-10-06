// @vitest-environment jsdom
// DS-CMP-07 (DESIGN_SYSTEM §7.2; APG Tabs): route tabs are links with aria-current, panel tabs activate
// automatically with the arrow keys (mirrored in RTL), and overflowing tabs move into "More".
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fittingCount, PanelTabs, type RouteTab, RouteTabs, type TabItem } from "./Tabs";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const ROUTE_TABS: readonly RouteTab[] = [
  { id: "overview", label: "Overview", to: "/contracts/c1", end: true },
  { id: "obligations", label: "Obligations", count: 12, to: "/contracts/c1/obligations" },
  {
    id: "schedule",
    label: "Schedule",
    to: "/contracts/c1/schedule",
    blockerLabel: "Unresolved blockers",
  },
  { id: "billing", label: "Billing", to: "/contracts/c1/billing" },
  { id: "history", label: "History", to: "/contracts/c1/history" },
];

function routes(path: string) {
  return (
    <MemoryRouter initialEntries={[path]}>
      <RouteTabs label="NS-SO-DE-5004 sections" tabs={ROUTE_TABS} />
      <Routes>
        <Route path="/contracts/c1/:tab?" element={null} />
      </Routes>
    </MemoryRouter>
  );
}

const PANEL_TABS: readonly TabItem[] = [
  { id: "allocation", label: "Allocation" },
  { id: "schedule", label: "Schedule" },
  { id: "events", label: "Events", count: 4 },
  { id: "history", label: "History", disabledReason: "History starts at activation." },
];

function Panels({ onChange }: { readonly onChange?: (id: string) => void }) {
  const [selected, setSelected] = useState("allocation");
  return (
    <PanelTabs
      label="Obligation sections"
      tabs={PANEL_TABS}
      selectedId={selected}
      onChange={(id) => {
        onChange?.(id);
        setSelected(id);
      }}
    >
      <p>Panel {selected}</p>
    </PanelTabs>
  );
}

describe("DS-CMP-07", () => {
  it("route tabs are links inside nav with aria-current on the active link", () => {
    render(routes("/contracts/c1/obligations"));
    const nav = screen.getByRole("navigation", { name: "NS-SO-DE-5004 sections" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((link) => link.textContent?.replace(/\s+/g, " "))).toEqual([
      "Overview",
      "Obligations 12",
      "Schedule Unresolved blockers",
      "Billing",
      "History",
    ]);
    expect(links.map((link) => link.getAttribute("aria-current"))).toEqual([
      null,
      "page",
      null,
      null,
      null,
    ]);
    expect(within(nav).getByRole("link", { name: "Obligations 12" })).toBeTruthy();

    fireEvent.click(within(nav).getByRole("link", { name: "Overview" }));
    expect(within(nav).getByRole("link", { name: "Overview" }).getAttribute("aria-current")).toBe(
      "page",
    );
    expect(
      within(nav).getByRole("link", { name: "Obligations 12" }).getAttribute("aria-current"),
    ).toBeNull();
  });

  it("panel tabs follow APG Tabs with automatic activation", () => {
    const onChange = vi.fn();
    render(<Panels onChange={onChange} />);
    const tablist = screen.getByRole("tablist", { name: "Obligation sections" });
    const allocation = within(tablist).getByRole("tab", { name: "Allocation" });
    expect(allocation.getAttribute("aria-selected")).toBe("true");
    expect(allocation.tabIndex).toBe(0);
    expect(within(tablist).getByRole("tab", { name: "Schedule" }).tabIndex).toBe(-1);
    const panel = screen.getByRole("tabpanel", { name: "Allocation" });
    expect(allocation.getAttribute("aria-controls")).toBe(panel.id);
    expect(panel.tabIndex).toBe(0);

    allocation.focus();
    fireEvent.keyDown(allocation, { key: "ArrowRight" });
    const schedule = within(tablist).getByRole("tab", { name: "Schedule" });
    expect(schedule.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(schedule);
    expect(screen.getByRole("tabpanel", { name: "Schedule" }).textContent).toBe("Panel schedule");

    // End goes to the last available tab; the disabled History tab is skipped.
    fireEvent.keyDown(schedule, { key: "End" });
    expect(document.activeElement).toBe(within(tablist).getByRole("tab", { name: "Events 4" }));
    fireEvent.keyDown(document.activeElement ?? schedule, { key: "ArrowRight" });
    expect(document.activeElement).toBe(within(tablist).getByRole("tab", { name: "Allocation" }));
    fireEvent.keyDown(document.activeElement ?? schedule, { key: "ArrowLeft" });
    expect(document.activeElement).toBe(within(tablist).getByRole("tab", { name: "Events 4" }));
    fireEvent.keyDown(document.activeElement ?? schedule, { key: "Home" });
    expect(document.activeElement).toBe(within(tablist).getByRole("tab", { name: "Allocation" }));
    expect(onChange.mock.calls).toEqual([
      ["schedule"],
      ["events"],
      ["allocation"],
      ["events"],
      ["allocation"],
    ]);

    const history = within(tablist).getByRole("tab", { name: "History" });
    expect(history.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(history);
    expect(onChange).toHaveBeenCalledTimes(5);
  });

  it("Left and Right are mirrored in RTL", () => {
    render(
      <div dir="rtl">
        <Panels />
      </div>,
    );
    const allocation = screen.getByRole("tab", { name: "Allocation" });
    allocation.focus();
    fireEvent.keyDown(allocation, { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { name: "Schedule" }).getAttribute("aria-selected")).toBe(
      "true",
    );
  });

  it("overflowing tabs move into a More menu", () => {
    // The bar is 320 px wide, each tab 100 px and the More trigger 60 px: two tabs fit beside More.
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (
      this: Element,
    ) {
      const kind = this.getAttribute("data-tab-measure");
      const width = this.hasAttribute("data-tab-bar")
        ? 320
        : kind === "more"
          ? 60
          : kind === "tab"
            ? 100
            : 0;
      return { width, height: 0, x: 0, y: 0, top: 0, left: 0, right: width, bottom: 0 } as DOMRect;
    });
    render(routes("/contracts/c1"));
    const nav = screen.getByRole("navigation", { name: "NS-SO-DE-5004 sections" });
    expect(
      within(nav)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["Overview", "Obligations 12"]);
    const more = within(nav).getByRole("button", { name: "More" });
    fireEvent.click(more);
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      "Schedule",
      "Billing",
      "History",
    ]);
    fireEvent.click(screen.getByRole("menuitem", { name: "Billing" }));
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("fits every tab when they fit, else the leading tabs beside More", () => {
    expect(fittingCount([100, 100, 100], 60, 340)).toBe(3);
    expect(fittingCount([100, 100, 100], 60, 339)).toBe(2);
    expect(fittingCount([100, 100, 100], 60, 179)).toBe(0);
  });
});
