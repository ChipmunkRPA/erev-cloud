// @vitest-environment jsdom
// DS-CMP-18 (DESIGN_SYSTEM §7.4 stepper anatomy): a named `nav` around an ordered list; the current item
// has aria-current="step", items are named with position, label and caption or state, and only completed
// steps link back.
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";

import { type Step, Stepper } from "./Stepper";

afterEach(() => {
  cleanup();
});

const STEPS: readonly Step[] = [
  {
    id: "upload",
    label: "Upload",
    state: "complete",
    caption: "1,204 rows",
    to: "/data/imports/b-7",
  },
  {
    id: "map",
    label: "Map columns",
    state: "skipped",
    caption: "Not needed: legacy template headers matched",
  },
  { id: "validate", label: "Validate", state: "error", caption: "12 errors in 9 rows" },
  { id: "review", label: "Review changes", state: "pending" },
  { id: "approval", label: "Approval", state: "pending" },
  { id: "committed", label: "Committed", state: "pending" },
];

function renderStepper() {
  return render(
    <MemoryRouter>
      <Stepper label="Import steps" steps={STEPS} currentId="validate" />
    </MemoryRouter>,
  );
}

describe("DS-CMP-18", () => {
  it("the current item has aria-current=step and no other item does", () => {
    renderStepper();
    const nav = screen.getByRole("navigation", { name: "Import steps" });
    const items = within(nav).getAllByRole("listitem");
    expect(items).toHaveLength(6);
    expect(items.map((item) => item.getAttribute("aria-current"))).toEqual([
      null,
      null,
      "step",
      null,
      null,
      null,
    ]);
  });

  it("items are named with position, label and caption, or the state without a caption", () => {
    renderStepper();
    const current = screen.getByText("Step 3 of 6, Validate, 12 errors in 9 rows");
    expect(current.closest("li")?.getAttribute("aria-current")).toBe("step");
    expect(current.className).toContain("sr-only");
    expect(screen.getByText("Step 4 of 6, Review changes, not started")).toBeTruthy();
    expect(
      screen.getByText("Step 2 of 6, Map columns, Not needed: legacy template headers matched"),
    ).toBeTruthy();
  });

  it("completed steps are links and future steps are not interactive", () => {
    renderStepper();
    const link = screen.getByRole("link", { name: "Step 1 of 6, Upload, 1,204 rows" });
    expect(link.getAttribute("href")).toBe("/data/imports/b-7");
    expect(screen.getAllByRole("link")).toHaveLength(1);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});
