// @vitest-environment jsdom
// X:narrow-viewport (SCREENS_B §12.4; PRD NFR-32): at 900 px `/settings/notifications` renders the
// notice with "Go to Home" and "Go to Approvals"; `/approvals` and `/sign-in` do not render it.
import { act, cleanup, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { probeRoute, renderApp } from "../../test/app";

function setWidth(px: number): void {
  Object.defineProperty(window, "innerWidth", { configurable: true, writable: true, value: px });
}

beforeEach(() => {
  setWidth(900);
});

afterEach(() => {
  cleanup();
  setWidth(1024);
});

const TABLES = {
  publicRoutes: [probeRoute("SF-22", "/sign-in", "shell.productName")],
  screenRoutes: [
    probeRoute("SF-01", "/home", "shell.rail.home"),
    probeRoute("SF-12", "/approvals", "shell.rail.approvals"),
    probeRoute("SF-15:notifications", "/settings/notifications", "shell.rail.settings"),
  ],
};

describe("X:narrow-viewport", () => {
  it("at 900 px /settings/notifications renders the notice with Go to Home and Go to Approvals", async () => {
    renderApp("/settings/notifications", TABLES);

    const notice = await screen.findByTestId("X-empty-narrow-viewport");
    expect(
      within(notice).getByRole("heading", { level: 1, name: "This screen needs a wider window" }),
    ).toBeTruthy();
    expect(
      within(notice).getByText(
        "Use a window at least 1,024 pixels wide, or open Home or Approvals, which work on smaller screens.",
      ),
    ).toBeTruthy();
    expect(within(notice).getByRole("link", { name: "Go to Home" }).getAttribute("href")).toBe(
      "/home",
    );
    expect(within(notice).getByRole("link", { name: "Go to Approvals" }).getAttribute("href")).toBe(
      "/approvals",
    );
    expect(notice.closest("main")?.id).toBe("main");
    expect(screen.queryByRole("heading", { name: "Settings" })).toBeNull();
  });

  it("/approvals and /sign-in do not render it", async () => {
    renderApp("/approvals", TABLES);
    expect(await screen.findByRole("heading", { level: 1, name: "Approvals" })).toBeTruthy();
    expect(screen.queryByTestId("X-empty-narrow-viewport")).toBeNull();
    cleanup();

    renderApp("/sign-in", TABLES);
    expect(await screen.findByRole("heading", { level: 1, name: "eRev Cloud" })).toBeTruthy();
    expect(screen.queryByTestId("X-empty-narrow-viewport")).toBeNull();
  });

  it("at 1024 px and wider the page renders, and a resize below 1024 px shows the notice", async () => {
    setWidth(1280);
    renderApp("/settings/notifications", TABLES);
    expect(await screen.findByRole("heading", { level: 1, name: "Settings" })).toBeTruthy();

    act(() => {
      setWidth(1023);
      window.dispatchEvent(new Event("resize"));
    });

    expect(await screen.findByTestId("X-empty-narrow-viewport")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Settings" })).toBeNull();
  });
});
