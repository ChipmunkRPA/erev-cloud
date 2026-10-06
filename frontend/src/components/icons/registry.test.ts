// DS-ICO-07 (DESIGN_SYSTEM §4.6): the registry exports exactly the icon names of the canonical map,
// every export is a Phosphor icon component, and DS-ICO-08 names the mirrored icons.
import { describe, expect, it } from "vitest";

import * as registry from "./registry";

// The DS-ICO-07 table, read row by row (left concept column, then right).
const DS_ICO_07 = [
  "MagnifyingGlass",
  "Command",
  "Bell",
  "Question",
  "Function",
  "Sparkle",
  "Buildings",
  "CalendarBlank",
  "Books",
  "Funnel",
  "Columns",
  "DownloadSimple",
  "UploadSimple",
  "ArrowsClockwise",
  "ArrowSquareOut",
  "CopySimple",
  "DotsThree",
  "X",
  "CaretRight",
  "CaretDown",
  "CaretLeft",
  "CaretUp",
  "Plus",
  "Minus",
  "Trash",
  "PencilSimple",
  "Receipt",
  "Notebook",
  "CheckCircle",
  "XCircle",
  "WarningCircle",
  "Info",
  "HourglassMedium",
  "ClockCounterClockwise",
  "PauseCircle",
  "Prohibit",
  "PencilSimpleLine",
  "LockSimple",
  "LockSimpleOpen",
  "CircleDashed",
  "CircleHalf",
  "Circle",
  "Equals",
  "ArrowUUpLeft",
  "ShieldCheck",
  "Paperclip",
  "ChatText",
  "Keyboard",
  "Sun",
  "Moon",
  "SignOut",
  "SidebarSimple",
  "TreeStructure",
  "Table",
  "ChartBar",
  "ListChecks",
];

// DS-ICO-07 defers the navigation icons to the DS-CMP-02 rail table; Notebook and ChartBar are in both.
const DS_CMP_02 = [
  "House",
  "FileText",
  "CalendarDots",
  "LockKey",
  "Notebook",
  "ChartBar",
  "SealCheck",
  "Scales",
  "Database",
  "GearSix",
];

const HELPERS = ["ICONS", "ICON_DEFAULTS", "IconContext", "MIRRORED_ICONS"];

describe("DS-ICO-07", () => {
  it("the registry exports exactly the icon names of DS-ICO-07 and DS-CMP-02", () => {
    expect(new Set(DS_ICO_07).size).toBe(56);
    const expected = [...new Set([...DS_ICO_07, ...DS_CMP_02])].sort();
    expect(expected).toHaveLength(64);
    expect(Object.keys(registry.ICONS).sort()).toEqual(expected);
    const iconExports = Object.keys(registry)
      .filter((name) => !HELPERS.includes(name))
      .sort();
    expect(iconExports).toEqual(expected);
  });

  it("every export names the Phosphor component of the same name", () => {
    const exports = registry as unknown as Record<string, unknown>;
    for (const [name, component] of Object.entries(registry.ICONS)) {
      expect(exports[name]).toBe(component);
      // Phosphor 2.1 names each component with the `Icon` suffix of its current export.
      expect(component.displayName).toBe(`${name}Icon`);
    }
  });

  it("DS-ICO-08 mirrors exactly six directional icons", () => {
    expect([...registry.MIRRORED_ICONS].sort()).toEqual([
      "ArrowSquareOut",
      "ArrowUUpLeft",
      "CaretLeft",
      "CaretRight",
      "SidebarSimple",
      "TreeStructure",
    ]);
    expect(registry.ICON_DEFAULTS).toEqual({ size: 16, weight: "regular" });
  });
});
