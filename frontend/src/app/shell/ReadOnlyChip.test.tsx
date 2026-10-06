// @vitest-environment jsdom
// SCR-PERM-06 (SCREENS §0.6; PRD BR-UX-04): a user whose permissions hold no command permission sees
// "Read-only access" with its tooltip; a user with a command permission does not; the chip sits in the
// top bar.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { probeRoute, renderApp, signedInMe } from "../../test/app";
import { holdsCommandPermission, ReadOnlyChip } from "./ReadOnlyChip";

afterEach(() => {
  cleanup();
});

const VIEWER = [
  "contract.read",
  "ssp.read",
  "config.read",
  "report.run",
  "report.export",
  "ai.use",
];

describe("SCR-PERM-06", () => {
  it("a user whose permissions hold no command permission sees Read-only access with its tooltip", () => {
    render(<ReadOnlyChip permissions={VIEWER} />);
    const chip = screen.getByText("Read-only access").closest("[tabindex]");
    if (!(chip instanceof HTMLElement)) {
      throw new Error("the chip is not focusable");
    }
    fireEvent.keyDown(document.body, { key: "Tab" });
    act(() => {
      chip.focus();
    });
    const tooltip = screen.getByRole("tooltip");
    expect(tooltip.textContent).toBe(
      "Your roles let you view records and run reports. Ask a workspace administrator for command permissions.",
    );
    expect(chip.getAttribute("aria-describedby")).toBe(tooltip.id);
  });

  it("a command permission hides the chip; Auditor grants are not command permissions", () => {
    render(<ReadOnlyChip permissions={["contract.read", "contract.create"]} />);
    expect(screen.queryByText("Read-only access")).toBeNull();
    expect(holdsCommandPermission(["audit.read", "evidence.export", "report.run"])).toBe(false);
    expect(holdsCommandPermission(["journal.run"])).toBe(true);
  });

  it("the top bar shows the chip for a read-only member", async () => {
    renderApp("/approvals", {
      screenRoutes: [probeRoute("SF-12", "/approvals", "shell.rail.approvals")],
      me: signedInMe({ permissions: VIEWER }),
    });
    const banner = await screen.findByRole("banner");
    expect(within(banner).getByText("Read-only access")).toBeTruthy();
  });
});
