// @vitest-environment jsdom
// DS-CMP-02 and REQ-UX-001 (DESIGN_SYSTEM §7.1; SCREENS SCR-IA-01): the destination catalogue, built
// routes only, the Approvals badge name, the `[` toggle persisted under erev.rail and the active item.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  CalendarDots,
  ChartBar,
  Database,
  FileText,
  GearSix,
  House,
  LockKey,
  Notebook,
  Scales,
  SealCheck,
} from "../../components/icons/registry";
import { t } from "../../lib/i18n/t";
import { installRouterRequest } from "../../test/app";
import { IconRail, type IconRailProps, RAIL_DESTINATIONS, RAIL_STORAGE_KEY } from "./IconRail";

installRouterRequest();

const ALL_BUILT: ReadonlySet<string> = new Set(RAIL_DESTINATIONS.map((d) => d.defaultRoute));

function setWidth(px: number): void {
  Object.defineProperty(window, "innerWidth", { configurable: true, writable: true, value: px });
}

// Node's own `localStorage` global can shadow the jsdom one without a backing file, so the suite
// installs an in-memory Storage (as MasterDetail.test.tsx does).
function memoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() {
      return values.size;
    },
    clear: () => {
      values.clear();
    },
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
  setWidth(1440);
});

afterEach(() => {
  cleanup();
  setWidth(1024);
});

function renderRail(entry: string, props: Partial<IconRailProps> = {}): void {
  const router = createMemoryRouter(
    [
      {
        path: "*",
        element: (
          <>
            <IconRail built={ALL_BUILT} activeScreen={null} {...props} />
            <input aria-label="Quick search" />
          </>
        ),
      },
    ],
    { initialEntries: [entry] },
  );
  render(<RouterProvider router={router} />);
}

function linkNames(): (string | null)[] {
  const nav = screen.getByRole("navigation", { name: "Primary" });
  return within(nav)
    .queryAllByRole("link")
    .map((link) => link.getAttribute("aria-label"));
}

function currentLinks(): (string | null)[] {
  return screen
    .queryAllByRole("link")
    .filter((link) => link.getAttribute("aria-current") === "page")
    .map((link) => link.getAttribute("aria-label"));
}

describe("DS-CMP-02 and REQ-UX-001", () => {
  it("the destination catalogue holds the ten D-02 destinations with their groups and icons", () => {
    expect(RAIL_DESTINATIONS.map((d) => [t(d.labelKey), d.group, d.sf, d.defaultRoute])).toEqual([
      ["Home", "work", "SF-01", "/home"],
      ["Contracts", "work", "SF-02", "/contracts"],
      ["Schedules", "work", "SF-04", "/schedules"],
      ["Close", "work", "SF-05", "/close"],
      ["Journals", "work", "SF-06", "/journals"],
      ["Reports", "work", "SF-08", "/reports"],
      ["Approvals", "govern", "SF-12", "/approvals"],
      ["Policies", "govern", "SF-13", "/policies"],
      ["Data", "govern", "SF-10", "/data/imports"],
      ["Settings", "bottom", "SF-15", "/settings"],
    ]);
    const icons = [
      House,
      FileText,
      CalendarDots,
      LockKey,
      Notebook,
      ChartBar,
      SealCheck,
      Scales,
      Database,
      GearSix,
    ];
    RAIL_DESTINATIONS.forEach((destination, index) => {
      expect(destination.icon).toBe(icons[index]);
    });

    renderRail("/home");

    expect(linkNames()).toEqual([
      "Home",
      "Contracts",
      "Schedules",
      "Close",
      "Journals",
      "Reports",
      "Approvals",
      "Policies",
      "Data",
      "Settings",
    ]);
    const work = screen.getByRole("list", { name: "Work" });
    expect(within(work).getAllByRole("link")).toHaveLength(6);
    const govern = screen.getByRole("list", { name: "Govern" });
    expect(
      within(govern)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["Approvals", "Policies", "Data"]);
  });

  it("only destinations whose default route is built render", () => {
    renderRail("/approvals", { built: new Set(["/approvals", "/settings", "/settings/profile"]) });

    expect(linkNames()).toEqual(["Approvals", "Settings"]);
    expect(screen.queryByRole("list", { name: "Work" })).toBeNull();
    cleanup();

    renderRail("/settings/profile", { built: new Set(["/settings/profile"]) });
    expect(linkNames()).toEqual([]);
  });

  it("the Approvals item is named 'Approvals, 4 pending' when the count is 4", () => {
    renderRail("/approvals", { approvalsPending: 4 });
    expect(screen.getByRole("link", { name: "Approvals, 4 pending" })).toBeTruthy();
    cleanup();

    renderRail("/approvals", { approvalsPending: 0 });
    expect(screen.getByRole("link", { name: "Approvals" })).toBeTruthy();
  });

  it("[ toggles the rail and persists erev.rail; a text field keeps the key", () => {
    renderRail("/home");
    const toggle = screen.getByRole("button", { name: "Collapse navigation" });
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("link", { name: "Home" }).textContent).toBe("Home");

    fireEvent.keyDown(document.body, { key: "[" });

    expect(
      screen.getByRole("button", { name: "Expand navigation" }).getAttribute("aria-expanded"),
    ).toBe("false");
    expect(screen.getByRole("link", { name: "Home" }).textContent).toBe("");
    expect(window.localStorage.getItem(RAIL_STORAGE_KEY)).toBe("collapsed");

    fireEvent.keyDown(screen.getByRole("textbox", { name: "Quick search" }), { key: "[" });
    expect(screen.getByRole("button", { name: "Expand navigation" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Expand navigation" }));
    expect(screen.getByRole("button", { name: "Collapse navigation" })).toBeTruthy();
    expect(window.localStorage.getItem(RAIL_STORAGE_KEY)).toBe("expanded");
    cleanup();

    window.localStorage.setItem(RAIL_STORAGE_KEY, "collapsed");
    renderRail("/home");
    expect(screen.getByRole("button", { name: "Expand navigation" })).toBeTruthy();
    cleanup();

    window.localStorage.clear();
    setWidth(1280);
    renderRail("/home");
    expect(screen.getByRole("button", { name: "Expand navigation" })).toBeTruthy();
  });

  it("the active item has aria-current=page", () => {
    renderRail("/settings/roles", { activeScreen: "SF-14:roles" });
    expect(currentLinks()).toEqual(["Settings"]);
    cleanup();

    renderRail("/settings/developer", { activeScreen: "SF-16:developer" });
    expect(currentLinks()).toEqual(["Settings"]);
    cleanup();

    renderRail("/data/integrations", { activeScreen: "SF-16" });
    expect(currentLinks()).toEqual(["Data"]);
    cleanup();

    renderRail("/contracts/new", { activeScreen: "SF-03:new" });
    expect(currentLinks()).toEqual(["Contracts"]);
    cleanup();

    renderRail("/help/legacy-transition", { activeScreen: "SF-26" });
    expect(currentLinks()).toEqual([]);
  });

  it("links carry the context parameters their destination uses", () => {
    renderRail("/contracts?entity=US01&period=FY2026-P09&book=ASC606&view=mine");

    expect(screen.getByRole("link", { name: "Home" }).getAttribute("href")).toBe(
      "/home?entity=US01&period=FY2026-P09&book=ASC606",
    );
    expect(screen.getByRole("link", { name: "Approvals" }).getAttribute("href")).toBe(
      "/approvals?entity=US01",
    );
    expect(screen.getByRole("link", { name: "Policies" }).getAttribute("href")).toBe("/policies");
    expect(screen.getByRole("link", { name: "Settings" }).getAttribute("href")).toBe("/settings");
  });
});
