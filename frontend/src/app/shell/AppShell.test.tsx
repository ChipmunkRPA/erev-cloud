// @vitest-environment jsdom
// DS-CMP-01 (DESIGN_SYSTEM §7.1; DS-A11Y-09; DS-BR-06): the skip link is the first focusable element,
// the landmarks exist, and a route change sets the document title, focuses the page h1 and announces
// the route politely.
import { act, cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { useEffect, useState } from "react";
import type { RouteObject } from "react-router";
import { afterEach, describe, expect, it } from "vitest";

import { t } from "../../lib/i18n/t";
import { probeRoute, renderApp } from "../../test/app";

afterEach(() => {
  cleanup();
});

const FOCUSABLE =
  "a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex='-1'])";

// A page whose heading renders after its data arrives.
function LateHeading() {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => {
      setReady(true);
    }, 20);
    return () => {
      clearTimeout(timer);
    };
  }, []);
  return ready ? <h1>{t("shell.rail.reports")}</h1> : null;
}

const REPORTS: RouteObject = {
  id: "SF-08",
  path: "/reports",
  handle: { sf: "SF-08", screen: "SF-08", titleKey: "shell.rail.reports" },
  element: <LateHeading />,
};

const TABLES = {
  screenRoutes: [
    probeRoute("SF-12", "/approvals", "shell.rail.approvals"),
    probeRoute("SF-15:profile", "/settings/profile", "shell.rail.settings"),
    REPORTS,
  ],
};

describe("DS-CMP-01", () => {
  it("the skip link is the first focusable element; nav Primary and main#main exist", async () => {
    renderApp("/approvals", TABLES);
    await screen.findByRole("heading", { level: 1, name: "Approvals" });

    const first = document.querySelector(FOCUSABLE);
    expect(first?.textContent).toBe("Skip to main content");
    expect(first?.getAttribute("href")).toBe("#main");
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeTruthy();
    expect(screen.getByRole("banner")).toBeTruthy();
    const main = screen.getByRole("main");
    expect(main.id).toBe("main");

    fireEvent.click(screen.getByRole("link", { name: "Skip to main content" }));

    expect(document.activeElement).toBe(main);
  });

  it("a route change sets the title, focuses the page h1 and announces the route politely", async () => {
    const { router } = renderApp("/approvals", TABLES);
    await screen.findByRole("heading", { level: 1, name: "Approvals" });
    await waitFor(() => {
      expect(document.title).toBe("Approvals · eRev Cloud");
    });
    expect(screen.getByRole("status").textContent).toBe("");

    await act(() => router.navigate("/settings/profile"));

    const heading = await screen.findByRole("heading", { level: 1, name: "Settings" });
    await waitFor(() => {
      expect(document.activeElement).toBe(heading);
    });
    // The title is set in a passive effect after the commit (F-ADM latent-race sweep).
    await waitFor(() => {
      expect(document.title).toBe("Settings · eRev Cloud");
    });
    expect(screen.getByRole("status").textContent).toBe("Settings");
  });

  it("focus waits for a page h1 that renders after the route", async () => {
    const { router } = renderApp("/approvals", TABLES);
    await screen.findByRole("heading", { level: 1, name: "Approvals" });

    await act(() => router.navigate("/reports"));

    const heading = await screen.findByRole("heading", { level: 1, name: "Reports" });
    await waitFor(() => {
      expect(document.activeElement).toBe(heading);
    });
    expect(heading.getAttribute("tabindex")).toBe("-1");
    // The title is set in a passive effect after the commit (F-ADM latent-race sweep).
    await waitFor(() => {
      expect(document.title).toBe("Reports · eRev Cloud");
    });
  });
});
