// @vitest-environment jsdom
// DS-CMP-22 (DESIGN_SYSTEM §7.5; DS-A11Y-22): timing, roles and the Alt+T focus shortcut.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TOAST_TIMEOUT_MS, type ToastApi, ToastProvider, useToast } from "./Toast";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function setup() {
  const api: { current: ToastApi | null } = { current: null };
  function Capture() {
    api.current = useToast();
    return (
      <button type="button" className="px-2">
        Run journals
      </button>
    );
  }
  render(
    <ToastProvider>
      <Capture />
    </ToastProvider>,
  );
  const show = (...args: Parameters<ToastApi["show"]>) => {
    act(() => {
      api.current?.show(...args);
    });
  };
  return { show };
}

function advance(milliseconds: number) {
  act(() => {
    vi.advanceTimersByTime(milliseconds);
  });
}

describe("DS-CMP-22", () => {
  it("a positive toast without action dismisses after 6 seconds and pauses while hovered", () => {
    vi.useFakeTimers();
    const { show } = setup();
    show({ tone: "positive", message: "Close run CR-0012 succeeded." });
    const toast = screen.getByRole("status");
    expect(screen.getByRole("region", { name: "Messages" }).contains(toast)).toBe(true);

    advance(4_000);
    fireEvent.mouseEnter(toast);
    advance(30_000);
    expect(screen.getByText("Close run CR-0012 succeeded.")).toBeTruthy();

    fireEvent.mouseLeave(toast);
    advance(TOAST_TIMEOUT_MS - 4_000 - 1);
    expect(screen.getByText("Close run CR-0012 succeeded.")).toBeTruthy();
    advance(1);
    expect(screen.queryByText("Close run CR-0012 succeeded.")).toBeNull();
  });

  it("a negative toast stays with role alert, as does a toast with an action", () => {
    vi.useFakeTimers();
    const { show } = setup();
    show({ tone: "negative", message: "Export of journal run JR-0031 failed." });
    show({
      tone: "positive",
      message: "Journal run JR-0032 calculated.",
      action: { label: "View journal run", onAction: () => undefined },
    });
    advance(60_000);
    expect(screen.getByRole("alert").textContent).toContain(
      "Export of journal run JR-0031 failed.",
    );
    expect(screen.getByText("Journal run JR-0032 calculated.")).toBeTruthy();
  });

  it("Alt+T focuses the newest toast and Esc returns focus", () => {
    const { show } = setup();
    const origin = screen.getByRole("button", { name: "Run journals" });
    origin.focus();
    show({ tone: "warning", message: "Two batches are waiting for acknowledgement." });
    show({ tone: "negative", message: "Export of journal run JR-0031 failed." });
    expect(document.activeElement).toBe(origin);

    fireEvent.keyDown(origin, { key: "†", code: "KeyT", altKey: true });
    expect(document.activeElement).toBe(screen.getByRole("alert"));

    fireEvent.keyDown(screen.getByRole("alert"), { key: "Escape" });
    expect(document.activeElement).toBe(origin);
  });

  it("at most three toasts are visible, newest last", () => {
    const { show } = setup();
    for (const number of [1, 2, 3, 4]) {
      show({ tone: "warning", message: `Warning ${String(number)}` });
    }
    const messages = screen.getAllByRole("status").map((toast) => toast.textContent);
    expect(messages).toHaveLength(3);
    expect(messages[2]).toContain("Warning 4");
  });
});
