// @vitest-environment jsdom
// DS-CMP-11 (DESIGN_SYSTEM §7.2; APG Dialog (Modal)): a confirmation is an alertdialog focused on Cancel,
// Esc closes and returns focus unless submitting, and a form dialog focuses its first field.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Modal, type ModalVariant } from "./Modal";

afterEach(() => {
  cleanup();
});

function Harness({
  variant = "confirmation",
  submitting = false,
  onClose = () => undefined,
}: {
  readonly variant?: ModalVariant;
  readonly submitting?: boolean;
  readonly onClose?: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Lock Sep 2026
      </button>
      <Modal
        open={open}
        variant={variant}
        title="Lock Sep 2026 for US01?"
        description="Locking Sep 2026 for US01 prevents new postings to that period."
        primaryAction={{ label: "Lock period", destructive: true }}
        submitting={submitting}
        onClose={() => {
          onClose();
          setOpen(false);
        }}
      >
        {variant === "form" ? (
          <label>
            Reason
            <input />
          </label>
        ) : undefined}
      </Modal>
    </>
  );
}

function openModal(): HTMLElement {
  const trigger = screen.getByRole("button", { name: "Lock Sep 2026" });
  trigger.focus();
  fireEvent.click(trigger);
  return trigger;
}

describe("DS-CMP-11", () => {
  it("a confirmation has role alertdialog and initial focus on Cancel; Esc returns focus", () => {
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);
    const trigger = openModal();
    const dialog = screen.getByRole("alertdialog", { name: "Lock Sep 2026 for US01?" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    const description = document.getElementById(dialog.getAttribute("aria-describedby") ?? "");
    expect(description?.textContent).toBe(
      "Locking Sep 2026 for US01 prevents new postings to that period.",
    );
    const cancel = screen.getByRole("button", { name: "Cancel" });
    expect(document.activeElement).toBe(cancel);
    expect(screen.getByRole("button", { name: "Lock period" }).className).toContain(
      "bg-danger-solid",
    );

    fireEvent.keyDown(cancel, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("Esc is ignored while submitting", () => {
    const onClose = vi.fn();
    render(<Harness submitting onClose={onClose} />);
    openModal();
    const cancel = screen.getByRole("button", { name: "Cancel" });
    fireEvent.keyDown(cancel, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("alertdialog")).toBeTruthy();
    expect(cancel.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(cancel);
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Lock period" }).getAttribute("aria-busy")).toBe(
      "true",
    );
  });

  it("a form dialog focuses its first field and traps Tab", () => {
    render(<Harness variant="form" />);
    openModal();
    expect(screen.getByRole("dialog", { name: "Lock Sep 2026 for US01?" })).toBeTruthy();
    const reason = screen.getByRole("textbox", { name: "Reason" });
    expect(document.activeElement).toBe(reason);
    const action = screen.getByRole("button", { name: "Lock period" });
    action.focus();
    fireEvent.keyDown(action, { key: "Tab" });
    expect(document.activeElement).toBe(reason);
    fireEvent.keyDown(reason, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(action);
  });
});
