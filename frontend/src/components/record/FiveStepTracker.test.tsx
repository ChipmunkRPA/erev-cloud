// @vitest-environment jsdom
// DS-CMP-17 (DESIGN_SYSTEM §7.4; REQ-UX-015): `ol aria-label="ASC 606 steps"` of five segment buttons
// whose names carry the state word; one evidence region opens at a time and Esc collapses it back to its
// segment.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { FiveStepTracker, type TrackerStep } from "./FiveStepTracker";

afterEach(() => {
  cleanup();
});

function evidence(step: number) {
  return (
    <div>
      <p>{`Evidence ${String(step)}`}</p>
      <button type="button">{`Open evidence ${String(step)}`}</button>
    </div>
  );
}

const STEPS: readonly TrackerStep[] = [
  { state: "complete", status: "Combined with C-000119", evidence: evidence(1) },
  { state: "complete", status: "4 obligations · 1 material right", evidence: evidence(2) },
  { state: "complete", status: "USD 1,200,000.00", evidence: evidence(3) },
  { state: "attention", status: "Relative SSP · book v7", evidence: evidence(4) },
  { state: "notStarted", status: "No schedule yet", evidence: evidence(5) },
];

describe("DS-CMP-17", () => {
  it("the ol named ASC 606 steps holds five segment buttons named with the state word", () => {
    render(<FiveStepTracker steps={STEPS} />);
    const list = screen.getByRole("list", { name: "ASC 606 steps" });
    expect(list.tagName).toBe("OL");
    expect(within(list).getAllByRole("button")).toHaveLength(5);

    const price = screen.getByRole("button", {
      name: "Step 3, Transaction price, complete, USD 1,200,000.00",
    });
    expect(price.getAttribute("aria-expanded")).toBe("false");
    expect(price.textContent).toContain("USD 1,200,000.00");
    const allocation = screen.getByRole("button", {
      name: "Step 4, Allocation, needs attention, Relative SSP · book v7",
    });
    // The visible status line names the state unless the step is complete.
    expect(allocation.textContent).toContain("Needs attention · Relative SSP · book v7");
    expect(price.textContent).not.toContain("complete");
  });

  it("a step whose status waits for a read is busy and shows nothing of it", () => {
    const waiting = STEPS.map((step, index) =>
      index === 3 ? { ...step, state: "complete" as const, busy: true } : step,
    );
    const { rerender } = render(<FiveStepTracker steps={waiting} />);
    // The name and the visible line leave the status out; the list item says the step is busy.
    const allocation = screen.getByRole("button", { name: "Step 4, Allocation, complete" });
    expect(allocation.textContent).toBe("4 Allocation");
    expect(allocation.closest("li")?.getAttribute("aria-busy")).toBe("true");
    expect(allocation.querySelector("[data-skeleton]")).not.toBeNull();
    expect(document.querySelectorAll('[aria-busy="true"]')).toHaveLength(1);

    rerender(
      <FiveStepTracker
        steps={waiting.map((step, index) => (index === 3 ? { ...step, busy: false } : step))}
      />,
    );
    const answered = screen.getByRole("button", {
      name: "Step 4, Allocation, complete, Relative SSP · book v7",
    });
    expect(answered.textContent).toBe("4 AllocationRelative SSP · book v7");
    expect(document.querySelector('[aria-busy="true"]')).toBeNull();
    expect(document.querySelector("[data-skeleton]")).toBeNull();
  });

  it("one evidence region opens at a time", () => {
    render(<FiveStepTracker steps={STEPS} />);
    expect(screen.queryByRole("region")).toBeNull();

    const price = screen.getByRole("button", { name: /^Step 3, Transaction price/ });
    fireEvent.click(price);
    const region = screen.getByRole("region", { name: "Transaction price" });
    expect(within(region).getByText("Evidence 3")).toBeTruthy();
    expect(price.getAttribute("aria-expanded")).toBe("true");
    expect(price.getAttribute("aria-controls")).toBe(region.id);

    const allocation = screen.getByRole("button", { name: /^Step 4, Allocation/ });
    fireEvent.click(allocation);
    expect(screen.getAllByRole("region")).toHaveLength(1);
    expect(screen.getByRole("region", { name: "Allocation" })).toBeTruthy();
    expect(price.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(allocation);
    expect(screen.queryByRole("region")).toBeNull();
  });

  it("Esc collapses the open region and returns focus to its segment", () => {
    render(<FiveStepTracker steps={STEPS} />);
    const obligations = screen.getByRole("button", { name: /^Step 2, Obligations/ });
    fireEvent.click(obligations);
    const inside = screen.getByRole("button", { name: "Open evidence 2" });
    inside.focus();
    fireEvent.keyDown(inside, { key: "Escape" });
    expect(screen.queryByRole("region")).toBeNull();
    expect(document.activeElement).toBe(obligations);
    expect(obligations.getAttribute("aria-expanded")).toBe("false");
  });

  it("loading shows five skeleton segments", () => {
    const { container } = render(<FiveStepTracker steps={[]} loading />);
    expect(screen.getByRole("list", { name: "ASC 606 steps" }).getAttribute("aria-busy")).toBe(
      "true",
    );
    expect(container.querySelectorAll("[data-skeleton]")).toHaveLength(5);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});
