// @vitest-environment jsdom
// DS-CMP-28 (DESIGN_SYSTEM §7.0; APG Menu Button): opening, moving, type-ahead, activation and Esc; and
// the disabled item (SCREENS SCR-PERM-03; supervisor ruling R-83 (c)): announced as disabled, its reason
// reachable by keyboard and, after the DS-CMP-27 delay, by the pointer; never activated.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DotsThree } from "../icons/registry";
import { Menu, type MenuItem } from "./Menu";
import { TOOLTIP_DELAY_MS } from "./Tooltip";

afterEach(() => {
  cleanup();
});

function items(onSelect: (id: string) => void): readonly MenuItem[] {
  return [
    { id: "void", label: "Void contract", destructive: true, onSelect: () => onSelect("void") },
    { id: "csv", label: "Download CSV", onSelect: () => onSelect("csv") },
    { id: "copy", label: "Copy link", shortcut: "C", onSelect: () => onSelect("copy") },
  ];
}

describe("DS-CMP-28", () => {
  it("Enter opens and focuses the first item; Esc closes and returns focus to the trigger", () => {
    render(<Menu label="More actions" icon={DotsThree} iconOnly items={items(() => undefined)} />);
    const trigger = screen.getByRole("button", { name: "More actions" });
    expect(trigger.getAttribute("aria-haspopup")).toBe("menu");
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "Enter" });

    expect(screen.getByRole("menu", { name: "More actions" })).toBeTruthy();
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(document.activeElement).toBe(screen.getByRole("menuitem", { name: "Download CSV" }));

    fireEvent.keyDown(document.activeElement ?? trigger, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(trigger);
  });

  it("Up and Down wrap, destructive items sit last, type-ahead moves and Enter activates", () => {
    const onSelect = vi.fn();
    render(<Menu label="Export" items={items(onSelect)} />);
    const trigger = screen.getByRole("button", { name: "Export" });
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    const menu = screen.getByRole("menu");
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      "Download CSV",
      "Copy linkC",
      "Void contract",
    ]);
    expect(screen.getByRole("separator")).toBeTruthy();

    fireEvent.keyDown(menu, { key: "ArrowUp" });
    expect(document.activeElement).toBe(screen.getByRole("menuitem", { name: "Void contract" }));
    fireEvent.keyDown(menu, { key: "ArrowDown" });
    expect(document.activeElement).toBe(screen.getByRole("menuitem", { name: "Download CSV" }));
    fireEvent.keyDown(menu, { key: "End" });
    expect(document.activeElement).toBe(screen.getByRole("menuitem", { name: "Void contract" }));
    fireEvent.keyDown(menu, { key: "c" });
    expect(document.activeElement).toBe(screen.getByRole("menuitem", { name: /Copy link/ }));

    fireEvent.click(screen.getByRole("menuitem", { name: /Copy link/ }));
    expect(onSelect).toHaveBeenCalledWith("copy");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("a disabled item is announced as disabled, states its reason and does not activate", () => {
    const onSelect = vi.fn();
    const reason = "Permanently lock Aug 2026 first.";
    render(
      <Menu
        label="More close actions"
        icon={DotsThree}
        iconOnly
        items={[
          { id: "end", label: "End soft close", onSelect: () => onSelect("end") },
          {
            id: "permanent-lock",
            label: "Permanently lock",
            destructive: true,
            disabledReason: reason,
            onSelect: () => onSelect("permanent-lock"),
          },
        ]}
      />,
    );
    const trigger = screen.getByRole("button", { name: "More close actions" });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "Enter" });
    const menu = screen.getByRole("menu");
    const disabled = screen.getByRole("menuitem", { name: "Permanently lock" });
    const enabled = screen.getByRole("menuitem", { name: "End soft close" });

    // Announced as disabled and described by its reason; the enabled item carries neither.
    expect(disabled.getAttribute("aria-disabled")).toBe("true");
    const described = document.getElementById(disabled.getAttribute("aria-describedby") ?? "");
    expect(described?.getAttribute("role")).toBe("tooltip");
    expect(described?.textContent).toBe(reason);
    expect(enabled.getAttribute("aria-disabled")).toBeNull();
    expect(enabled.getAttribute("aria-describedby")).toBeNull();

    // The reason is reachable by keyboard: the arrow keys reach the item, and focus shows the tooltip.
    expect(described?.hidden).toBe(true);
    fireEvent.keyDown(menu, { key: "ArrowDown" });
    expect(document.activeElement).toBe(disabled);
    expect(described?.hidden).toBe(false);

    // It does not activate: the menu stays open and nothing is selected.
    fireEvent.click(disabled);
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole("menu")).toBe(menu);

    // Moving on hides the reason; the enabled item still activates and closes the menu.
    fireEvent.keyDown(menu, { key: "ArrowDown" });
    expect(document.activeElement).toBe(enabled);
    expect(described?.hidden).toBe(true);
    fireEvent.click(enabled);
    expect(onSelect).toHaveBeenCalledWith("end");
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("a menu whose only item is disabled opens on it and shows the reason at once", () => {
    render(
      <Menu
        label="More close actions"
        items={[
          {
            id: "permanent-lock",
            label: "Permanently lock",
            disabledReason: "Permanently lock Aug 2026 first.",
            onSelect: () => undefined,
          },
        ]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "More close actions" }));
    const item = screen.getByRole("menuitem", { name: "Permanently lock" });
    expect(document.activeElement).toBe(item);
    expect(screen.getByRole("tooltip").hidden).toBe(false);
    expect(screen.getByRole("tooltip").textContent).toBe("Permanently lock Aug 2026 first.");
  });

  it("the pointer shows the reason after the tooltip delay; leaving hides it unless the item has focus", () => {
    vi.useFakeTimers();
    try {
      render(
        <Menu
          label="More close actions"
          align="end"
          items={[
            { id: "end", label: "End soft close", onSelect: () => undefined },
            {
              id: "permanent-lock",
              label: "Permanently lock",
              destructive: true,
              disabledReason: "Permanently lock Aug 2026 first.",
              onSelect: () => undefined,
            },
          ]}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: "More close actions" }));
      const disabled = screen.getByRole("menuitem", { name: "Permanently lock" });
      const reason = document.getElementById(disabled.getAttribute("aria-describedby") ?? "");
      expect(reason?.hidden).toBe(true);

      // DS-CMP-27: 400 ms under the pointer, and a pointer that leaves sooner shows nothing.
      fireEvent.mouseEnter(disabled);
      act(() => {
        vi.advanceTimersByTime(TOOLTIP_DELAY_MS - 1);
      });
      expect(reason?.hidden).toBe(true);
      fireEvent.mouseLeave(disabled);
      act(() => {
        vi.advanceTimersByTime(TOOLTIP_DELAY_MS);
      });
      expect(reason?.hidden).toBe(true);

      fireEvent.mouseEnter(disabled);
      act(() => {
        vi.advanceTimersByTime(TOOLTIP_DELAY_MS);
      });
      expect(reason?.hidden).toBe(false);
      fireEvent.mouseLeave(disabled);
      expect(reason?.hidden).toBe(true);

      // With focus on the item the reason stays while the pointer comes and goes.
      fireEvent.keyDown(screen.getByRole("menu"), { key: "ArrowDown" });
      expect(document.activeElement).toBe(disabled);
      expect(reason?.hidden).toBe(false);
      fireEvent.mouseEnter(disabled);
      fireEvent.mouseLeave(disabled);
      expect(reason?.hidden).toBe(false);

      // Closing the menu and opening it again starts without a reason shown.
      fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
      fireEvent.click(screen.getByRole("button", { name: "More close actions" }));
      const reopened = screen.getByRole("menuitem", { name: "Permanently lock" });
      expect(document.getElementById(reopened.getAttribute("aria-describedby") ?? "")?.hidden).toBe(
        true,
      );
    } finally {
      vi.useRealTimers();
    }
  });
});
