// @vitest-environment jsdom
// DS-CMP-32 (DESIGN_SYSTEM §7.5; SCREENS_B §11.2): a non-modal dialog named "Stop <n> of <total>: <title>"
// that focuses its heading and marks its target; Esc ends the tour and returns focus to the Help menu
// button; a missing anchor states that the stop is unavailable.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TourPopover } from "./TourPopover";

afterEach(() => {
  cleanup();
  document.body.replaceChildren();
});

interface TourProps {
  readonly stop?: number;
  readonly anchor: HTMLElement | null;
  readonly onEnd?: () => void;
}

function Tour({ stop = 1, anchor, onEnd = () => undefined }: TourProps) {
  const help = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button ref={help} type="button">
        Help
      </button>
      <TourPopover
        stop={stop}
        total={6}
        title="Contracts list"
        body="Every contract of the workspace, with its status and transaction price."
        anchor={anchor}
        returnFocus={help}
        onBack={() => undefined}
        onNext={() => undefined}
        onEnd={onEnd}
      />
    </>
  );
}

function target(): HTMLElement {
  const element = document.createElement("div");
  element.textContent = "Contracts";
  document.body.append(element);
  return element;
}

describe("DS-CMP-32", () => {
  it("stop 1 is a non-modal dialog named Stop 1 of 6: <title> without Back", () => {
    const anchor = target();
    render(<Tour anchor={anchor} />);
    const dialog = screen.getByRole("dialog", { name: "Stop 1 of 6: Contracts list" });
    expect(dialog.getAttribute("aria-modal")).toBeNull();
    expect(
      document.getElementById(dialog.getAttribute("aria-describedby") ?? "")?.textContent,
    ).toBe("Every contract of the workspace, with its status and transaction price.");
    expect(screen.queryByRole("button", { name: "Back" })).toBeNull();
    expect(screen.getByRole("button", { name: "Next" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "End tour" })).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Contracts list" }));
    expect(anchor.getAttribute("aria-describedby")).toBe(dialog.id);
    expect(anchor.style.outline).toContain("2px solid");
  });

  it("later stops offer Back and the last stop offers Finish", () => {
    const anchor = target();
    const { rerender } = render(<Tour anchor={anchor} stop={2} />);
    expect(screen.getByRole("button", { name: "Back" })).toBeTruthy();
    rerender(<Tour anchor={anchor} stop={6} />);
    expect(screen.getByRole("dialog", { name: "Stop 6 of 6: Contracts list" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Finish" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Next" })).toBeNull();
  });

  it("Esc ends the tour and returns focus to the Help menu button", () => {
    const anchor = target();
    const onEnd = vi.fn();
    render(<Tour anchor={anchor} onEnd={onEnd} />);
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    expect(onEnd).toHaveBeenCalledTimes(1);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Help" }));
  });

  it("the target outline and description are removed when the stop ends", () => {
    const anchor = target();
    const { unmount } = render(<Tour anchor={anchor} />);
    unmount();
    expect(anchor.getAttribute("aria-describedby")).toBeNull();
    expect(anchor.style.outline).toBe("");
  });

  it("a missing anchor shows that the stop is not available, with Next", () => {
    render(<Tour anchor={null} stop={3} />);
    expect(screen.getByText("This stop is not available in this workspace.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Next" })).toBeTruthy();
  });
});
