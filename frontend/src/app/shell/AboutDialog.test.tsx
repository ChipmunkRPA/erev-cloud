// @vitest-environment jsdom
// SF-27 (SCREENS_B §11.5; DESIGN_SYSTEM DS-BR-02, DS-BR-05; 04 API-S-Me `engine_release`): `?dialog=about`
// opens "About eRev Cloud" with the wordmark, byline, product name, engine line, licence links and
// copyright; without a release the engine line reads "Engine release unavailable"; the Help menu opens
// the dialog and Esc returns focus to it; the licence files are bundled with the web app.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Me } from "../../lib/api/queries/me";
import { renderWithApp, signedInMe } from "../../test/app";
import { AboutDialog } from "./AboutDialog";
import { HelpMenu } from "./HelpMenu";

afterEach(() => {
  cleanup();
});

function renderAbout(entry: string, me?: Me) {
  return renderWithApp(
    <>
      <HelpMenu />
      <AboutDialog />
    </>,
    { entry, me },
  );
}

describe("SF-27", () => {
  it("?dialog=about opens About eRev Cloud with the identity, engine release, licences and copyright", () => {
    renderAbout("/home?dialog=about");
    const dialog = screen.getByRole("dialog", { name: "About eRev Cloud" });
    expect(dialog.getAttribute("data-testid")).toBe("SF-27-page");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    const wordmark = within(dialog).getByRole("img", { name: "eRev" });
    expect(wordmark.getAttribute("aria-label")).toBe("eRev");
    expect(wordmark.textContent).toBe("eRev");
    expect(within(dialog).getByText("by Chipmunk Robotics")).toBeTruthy();
    expect(within(dialog).getByText("eRev Cloud")).toBeTruthy();
    const engine = within(dialog).getByTestId("SF-27-engine-release");
    expect(engine.textContent).toBe("Engine 1.0.0 · build 3f9a1c22 · schema e41");
    expect(engine.hasAttribute("data-volatile")).toBe(true);
    expect(
      within(dialog)
        .getByRole("link", { name: "PolyForm Noncommercial licence" })
        .getAttribute("href"),
    ).toBe("/licenses/LICENSE.txt");
    expect(
      within(dialog).getByRole("link", { name: "Third-party notices" }).getAttribute("href"),
    ).toBe("/licenses/NOTICE.txt");
    expect(within(dialog).getByText("Copyright (c) 2025-2026 ChipmunkRPA")).toBeTruthy();
    expect(document.activeElement).toBe(
      within(dialog).getByRole("heading", { name: "About eRev Cloud" }),
    );
  });

  it("without a release the engine line reads Engine release unavailable", () => {
    const withoutRelease = { ...signedInMe(), engine_release: null } as unknown as Me;
    renderAbout("/home?dialog=about", withoutRelease);
    expect(screen.getByTestId("SF-27-engine-release").textContent).toBe(
      "Engine release unavailable",
    );
  });

  it("the Help menu opens the dialog; Esc removes dialog=about and returns focus to Help", async () => {
    const { router } = renderAbout("/home?view=mine");
    const help = screen.getByRole("button", { name: "Help" });
    fireEvent.click(help);
    fireEvent.click(screen.getByRole("menuitem", { name: "About eRev Cloud" }));
    const dialog = await screen.findByRole("dialog", { name: "About eRev Cloud" });
    expect(new URLSearchParams(router.state.location.search).get("dialog")).toBe("about");
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "About eRev Cloud" })).toBeNull();
    });
    expect(router.state.location.search).toBe("?view=mine");
    expect(document.activeElement).toBe(help);
  });

  it("bundles the repository LICENSE and NOTICE as the dialog's static files", () => {
    const read = (path: string) =>
      readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
    expect(read("../../../public/licenses/LICENSE.txt")).toBe(read("../../../../LICENSE"));
    expect(read("../../../public/licenses/NOTICE.txt")).toBe(read("../../../../NOTICE"));
  });
});
