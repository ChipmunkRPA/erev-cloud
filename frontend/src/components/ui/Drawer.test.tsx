// @vitest-environment jsdom
// DS-CMP-09 (DESIGN_SYSTEM §7.2; APG Dialog (Modal)): the modal drawer traps focus, closing a dirty form
// asks "Discard changes?", and focus returns to the trigger; the docked variant closes with Esc.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Drawer } from "./Drawer";

afterEach(() => {
  cleanup();
});

function Harness() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Add revenue policy
      </button>
      <Drawer
        open={open}
        title="Add revenue policy"
        dirty={name !== ""}
        primaryAction={{ label: "Create policy" }}
        onClose={() => {
          setOpen(false);
          setName("");
        }}
      >
        <label>
          Name
          <input value={name} onChange={(event) => setName(event.target.value)} />
        </label>
      </Drawer>
    </>
  );
}

function openDrawer(): HTMLElement {
  const trigger = screen.getByRole("button", { name: "Add revenue policy" });
  trigger.focus();
  fireEvent.click(trigger);
  return trigger;
}

describe("DS-CMP-09", () => {
  it("the modal drawer traps focus", () => {
    render(<Harness />);
    openDrawer();
    const dialog = screen.getByRole("dialog", { name: "Add revenue policy" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    const name = screen.getByRole("textbox", { name: "Name" });
    expect(document.activeElement).toBe(name);

    const close = screen.getByRole("button", { name: "Close" });
    const create = screen.getByRole("button", { name: "Create policy" });
    create.focus();
    fireEvent.keyDown(create, { key: "Tab" });
    expect(document.activeElement).toBe(close);
    fireEvent.keyDown(close, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(create);
  });

  it("closing a dirty form opens Discard changes? and focus returns to the trigger", () => {
    render(<Harness />);
    const trigger = openDrawer();
    const name = screen.getByRole("textbox", { name: "Name" });
    fireEvent.change(name, { target: { value: "Ratable SaaS" } });

    fireEvent.keyDown(name, { key: "Escape" });
    const confirmation = screen.getByRole("alertdialog", { name: "Discard changes?" });
    const keepEditing = within(confirmation).getByRole("button", { name: "Cancel" });
    expect(document.activeElement).toBe(keepEditing);
    expect(confirmation.getAttribute("aria-modal")).toBe("true");

    fireEvent.click(keepEditing);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(screen.getByRole("dialog", { name: "Add revenue policy" })).toBeTruthy();
    expect(document.activeElement).toBe(name);

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    fireEvent.click(screen.getByRole("button", { name: "Discard changes" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("a clean form closes at once and focus returns to the trigger", () => {
    render(<Harness />);
    const trigger = openDrawer();
    fireEvent.keyDown(screen.getByRole("textbox", { name: "Name" }), { key: "Escape" });
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("a secondary action sits between Cancel and the primary action", () => {
    const save = vi.fn();
    const submit = vi.fn();
    const { rerender } = render(
      <Drawer
        open
        title="New estimate version"
        secondaryAction={{ label: "Save draft", onAction: save }}
        primaryAction={{ label: "Submit for approval", onAction: submit }}
        onClose={() => undefined}
      >
        <p>Fields</p>
      </Drawer>,
    );
    const dialog = screen.getByRole("dialog", { name: "New estimate version" });
    const names = () =>
      within(dialog)
        .getAllByRole("button")
        .map((button) => button.textContent)
        .filter((text) => text !== "");
    expect(names()).toEqual(["Cancel", "Save draft", "Submit for approval"]);
    fireEvent.click(within(dialog).getByRole("button", { name: "Save draft" }));
    expect(save).toHaveBeenCalledTimes(1);
    expect(submit).not.toHaveBeenCalled();

    // While the primary action runs, the secondary one waits with its reason.
    rerender(
      <Drawer
        open
        submitting
        title="New estimate version"
        secondaryAction={{ label: "Save draft", onAction: save }}
        primaryAction={{ label: "Submit for approval", onAction: submit }}
        onClose={() => undefined}
      >
        <p>Fields</p>
      </Drawer>,
    );
    expect(screen.getByRole("button", { name: "Save draft" }).getAttribute("aria-disabled")).toBe(
      "true",
    );
  });

  it("the docked variant is a region without trap that closes with Esc from inside", () => {
    const onClose = vi.fn();
    render(
      <Drawer open variant="docked" title="Explain" initialFocus="title" onClose={onClose}>
        <button type="button">Copy formula</button>
      </Drawer>,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    const aside = screen.getByRole("complementary", { name: "Explain" });
    expect(aside.getAttribute("aria-modal")).toBeNull();
    expect(document.activeElement).toBe(document.body);
    fireEvent.keyDown(screen.getByRole("button", { name: "Copy formula" }), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
