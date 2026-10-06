// @vitest-environment jsdom
// DS-CMP-20 (DESIGN_SYSTEM §7.0; DS-ICO-06): disabled and loading states and icon-only names.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Plus } from "../icons/registry";
import { Button } from "./Button";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("DS-CMP-20", () => {
  it("a disabled button has aria-disabled and stays focusable, with the reason as its tooltip", () => {
    const onClick = vi.fn();
    render(
      <Button
        variant="primary"
        disabledReason="You prepared this request, so another user approves it."
        onClick={onClick}
      >
        Approve
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Approve" });
    expect(button.getAttribute("aria-disabled")).toBe("true");
    expect(button.hasAttribute("disabled")).toBe(false);
    button.focus();
    expect(document.activeElement).toBe(button);
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
    const tooltip = screen.getByRole("tooltip", { hidden: true });
    expect(tooltip.textContent).toBe("You prepared this request, so another user approves it.");
    expect(button.getAttribute("aria-describedby")).toBe(tooltip.id);
  });

  it("the loading state sets aria-busy and ignores repeated presses", () => {
    const onSave = vi.fn();
    function SaveButton() {
      const [saving, setSaving] = useState(false);
      return (
        <Button
          variant="primary"
          loading={saving}
          onClick={() => {
            onSave();
            setSaving(true);
          }}
        >
          Save
        </Button>
      );
    }
    render(<SaveButton />);
    const button = screen.getByRole("button", { name: "Save" });
    fireEvent.click(button);
    expect(button.getAttribute("aria-busy")).toBe("true");
    expect(button.textContent).toBe("Save");
    fireEvent.click(button);
    fireEvent.click(button);
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it("an icon-only button without aria-label fails the render", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => render(<Button variant="ghost" icon={Plus} />)).toThrow(/needs aria-label/);
  });

  it("an icon-only button with aria-label is named and shows the label as a tooltip on focus", () => {
    render(<Button variant="ghost" icon={Plus} aria-label="Add obligation" shortcut="N" />);
    const button = screen.getByRole("button", { name: "Add obligation" });
    fireEvent.keyDown(document.body, { key: "Tab" });
    act(() => {
      button.focus();
    });
    const tooltip = screen.getByRole("tooltip");
    expect(tooltip.textContent).toBe("Add obligationN");
    expect(button.hasAttribute("aria-describedby")).toBe(false);
    fireEvent.keyDown(button, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
  });
});
