// @vitest-environment jsdom
// DS-DEN-01 (DESIGN_SYSTEM §4.2; DS-CMP-01 item 9): selecting Density "Compact" in the user menu sets
// data-density="compact", stores erev.density and sends PATCH /me/preferences {density: "COMPACT"}; the
// menu follows the APG Menu keyboard rules.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import type { Me } from "../../lib/api/queries/me";
import { queryKeys } from "../../lib/api/query-keys";
import { installMemoryStorage, renderWithApp, signedInMe } from "../../test/app";
import { apiUrl, installMswServer, server } from "../../test/msw";
import { initials, UserMenu } from "./UserMenu";

installMswServer();
installMemoryStorage();

afterEach(() => {
  cleanup();
});

function renderMenu() {
  return renderWithApp(<UserMenu built={new Set()} homePath="/home" />);
}

describe("DS-DEN-01", () => {
  it("selecting Density Compact sets data-density, stores erev.density and sends PATCH /me/preferences", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.patch(apiUrl("/api/v1/me/preferences"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({
          preferences: { ...signedInMe().preferences, density: "COMPACT" },
        });
      }),
    );
    const { queryClient } = renderMenu();
    fireEvent.click(screen.getByRole("button", { name: "User menu for Maya Chen" }));
    const menu = screen.getByRole("menu");
    expect(
      within(menu).getByRole("menuitemradio", { name: "Comfortable" }).getAttribute("aria-checked"),
    ).toBe("true");

    fireEvent.click(within(menu).getByRole("menuitemradio", { name: "Compact" }));
    expect(document.documentElement.getAttribute("data-density")).toBe("compact");
    expect(window.localStorage.getItem("erev.density")).toBe("compact");
    await waitFor(() => {
      expect(bodies).toEqual([{ density: "COMPACT" }]);
    });
    await waitFor(() => {
      expect(queryClient.getQueryData<Me>(queryKeys.me())?.preferences.density).toBe("COMPACT");
    });
    expect(document.documentElement.getAttribute("data-density")).toBe("compact");

    fireEvent.click(screen.getByRole("button", { name: "User menu for Maya Chen" }));
    expect(
      screen.getByRole("menuitemradio", { name: "Compact" }).getAttribute("aria-checked"),
    ).toBe("true");
  });

  it("the avatar shows initials; Enter opens at the first item, Up wraps and Esc returns focus", () => {
    renderMenu();
    const avatar = screen.getByRole("button", { name: "User menu for Maya Chen" });
    expect(avatar.textContent).toBe("MC");
    expect(initials("Hannah Maria Lindqvist")).toBe("HL");
    fireEvent.keyDown(avatar, { key: "Enter" });
    const menu = screen.getByRole("menu");
    expect(within(menu).getAllByRole("group", { name: /Theme|Density/ })).toHaveLength(2);
    expect(document.activeElement).toBe(screen.getByRole("menuitemradio", { name: "System" }));
    fireEvent.keyDown(menu, { key: "ArrowUp" });
    expect(document.activeElement).toBe(screen.getByRole("menuitem", { name: "Sign out" }));
    fireEvent.keyDown(menu, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(avatar);
  });

  it("applies the theme that GET /me returns", () => {
    renderWithApp(<UserMenu built={new Set()} homePath="/home" />, {
      me: signedInMe({ preferences: { ...signedInMe().preferences, theme: "DARK" } }),
    });
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(window.localStorage.getItem("erev.theme")).toBe("dark");
  });
});
