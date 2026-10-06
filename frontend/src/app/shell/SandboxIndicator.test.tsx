// @vitest-environment jsdom
// SCR-ST-11 (SCREENS §0.7, §1.1; DESIGN_SYSTEM DS-CMP-01 item 4): a sandbox tenant shows the chip
// "Sandbox: <tenant name>", the 2 px --warning-solid top line and the global banner; production shows none.
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { probeRoute, renderApp, signedInSession } from "../../test/app";

afterEach(() => {
  cleanup();
});

const TABLES = { screenRoutes: [probeRoute("SF-12", "/approvals", "shell.rail.approvals")] };

describe("SCR-ST-11", () => {
  it("a sandbox tenant shows the chip, the 2 px --warning-solid top line and the global banner", async () => {
    renderApp("/approvals", {
      ...TABLES,
      session: signedInSession({
        active_tenant: {
          id: "7d6c5b4a-3f2e-4d1c-9b0a-8f7e6d5c4b3a",
          code: "avenmoor-sbx",
          display_name: "Avenmoor Sandbox",
          kind: "sandbox",
        },
      }),
    });
    const topBar = await screen.findByRole("banner");
    const chip = within(topBar).getByText("Sandbox: Avenmoor Sandbox");
    expect(chip.closest("[data-tone]")?.getAttribute("data-tone")).toBe("warning");
    const line = topBar.querySelector("[data-sandbox-line]");
    expect(line?.getAttribute("aria-hidden")).toBe("true");
    // h-0.5 is 2 px; the line spans the top edge of the positioned header.
    expect(line?.className.split(" ")).toEqual(
      expect.arrayContaining([
        "absolute",
        "top-0",
        "start-0",
        "end-0",
        "h-0.5",
        "bg-warning-solid",
      ]),
    );
    expect(topBar.className.split(" ")).toContain("relative");
    const banner = screen.getByRole("heading", {
      name: "Sandbox: Avenmoor Sandbox. Nothing here posts or exports.",
    });
    expect(banner.closest("[data-tone]")?.getAttribute("data-tone")).toBe("warning");
    expect(topBar.contains(banner)).toBe(false);
  });

  it("a production tenant shows no chip, line or banner", async () => {
    renderApp("/approvals", TABLES);
    const topBar = await screen.findByRole("banner");
    expect(within(topBar).queryByText(/^Sandbox:/)).toBeNull();
    expect(topBar.querySelector("[data-sandbox-line]")).toBeNull();
    expect(screen.queryByText(/Nothing here posts or exports/)).toBeNull();
  });
});
