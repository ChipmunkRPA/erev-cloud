// @vitest-environment jsdom
// SF-15:setup Workspace setup (SCREENS_B §11.1; SCREENS §0.6 SCR-PERM-01, SCR-PERM-02 (c); item
// W-12e). The checklist reads `GET /tenant`, which answers a holder of settings.manage for all entities
// alone (04 API-C-03). A holder for one entity sent the read, was refused, and was shown a load-error
// banner with "Retry" in place of the page.
import { cleanup, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { accessDescription } from "../../test/access";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import { apiUrl, installMswServer, server } from "../../test/msw";

installMswServer();
installMemoryStorage();

afterEach(() => {
  cleanup();
});

const ENTITY = "0a1b2c3d-4e5f-4a6b-8c7d-0000000000de";

describe("SF-15:setup", () => {
  it("settings.manage for one entity alone: the page says that workspace setup covers every entity, and does not ask for the tenant", async () => {
    const asked: string[] = [];
    server.use(
      http.get(apiUrl("/api/v1/*"), ({ request }) => {
        asked.push(new URL(request.url).pathname);
      }),
      http.get(apiUrl("/api/v1/entities"), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
    renderApp("/settings/setup", {
      me: signedInMe({
        permissions: ["settings.manage"],
        permission_scopes: { "settings.manage": [ENTITY] },
      }),
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("heading", { name: "You do not have access to Workspace setup" }),
    ).toBeTruthy();
    expect(accessDescription()).toBe(
      "Workspace setup covers every entity of the workspace. Ask a workspace administrator for a role that includes managing workspace settings (settings.manage) for all entities.",
    );
    // For a member of named entities the access module reads the entities of the workspace
    // (src/lib/access.ts); a read of the tenant would have been sent before it was answered.
    await waitFor(() => {
      expect(asked).toContain("/api/v1/entities");
    });
    expect(asked.filter((path) => path === "/api/v1/tenant")).toEqual([]);
  });

  it("a member without settings.manage reads the sentence of a missing permission", async () => {
    renderApp("/settings/setup", {
      me: signedInMe({ permissions: ["contract.read"] }),
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("heading", { name: "You do not have access to Workspace setup" }),
    ).toBeTruthy();
    expect(accessDescription()).toBe(
      "Ask a workspace administrator for a role that includes managing workspace settings (settings.manage).",
    );
  });
});
