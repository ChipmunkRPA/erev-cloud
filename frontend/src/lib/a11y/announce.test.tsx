// @vitest-environment jsdom
// DS-A11Y-08 (DESIGN_SYSTEM §8): announce() speaks through the shell's polite and assertive live
// regions and drops an identical message within 1 second.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AnnouncerProvider } from "../../app/providers";
import { announce } from "./announce";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function mount(): void {
  render(
    <AnnouncerProvider>
      <p>Approvals</p>
    </AnnouncerProvider>,
  );
}

describe("DS-A11Y-08", () => {
  it("writes polite messages to role=status and assertive messages to role=alert", () => {
    mount();

    announce("12 results", "polite");
    expect(screen.getByRole("status")).toHaveProperty("textContent", "12 results");
    expect(screen.getByRole("status").getAttribute("aria-live")).toBe("polite");

    announce("Retention sweep failed. Nothing was committed.", "assertive");
    expect(screen.getByRole("alert")).toHaveProperty(
      "textContent",
      "Retention sweep failed. Nothing was committed.",
    );
    expect(screen.getByRole("alert").getAttribute("aria-live")).toBe("assertive");
    expect(screen.getByRole("status")).toHaveProperty("textContent", "12 results");
  });

  it("drops an identical message within 1 second", () => {
    const now = vi.spyOn(Date, "now");
    mount();

    now.mockReturnValue(1_000_000);
    announce("Context changed to AVM-US, Sep 2026, ASC 606", "polite");
    now.mockReturnValue(1_000_500);
    announce("Context changed to AVM-US, Sep 2026, ASC 606", "assertive");
    expect(screen.getByRole("alert")).toHaveProperty("textContent", "");

    now.mockReturnValue(1_001_600);
    announce("Context changed to AVM-US, Sep 2026, ASC 606", "assertive");
    expect(screen.getByRole("alert")).toHaveProperty(
      "textContent",
      "Context changed to AVM-US, Sep 2026, ASC 606",
    );
  });
});
