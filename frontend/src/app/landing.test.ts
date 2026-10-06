// @vitest-environment jsdom
// BS-D-08 and BS1-D-18 (PHASES; BUILD_SPEC appendix, RPS-22; SCREENS RT-07): the landing route is the
// first built candidate, else the last candidate. SF-01 is built, so `LANDING_ROUTES` is `["/home"]`;
// `/` redirects there and keeps the search string.
import { createMemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { queryKeys } from "../lib/api/query-keys";
import { probeRoute, signedInSession } from "../test/app";
import { createQueryClient } from "./providers";
import { buildRoutes, LANDING_ROUTES, landingRoute } from "./router";

/** The BS1-D-18 candidates before RPS-22 left only `/home`. */
const BEFORE_HOME = ["/home", "/contracts", "/approvals", "/settings/profile"] as const;

describe("BS-D-08 and BS1-D-18", () => {
  it("lists only /home once SF-01 is built", () => {
    expect(LANDING_ROUTES).toEqual(["/home"]);
    expect(landingRoute(new Set(["/approvals", "/home"]))).toBe("/home");
    expect(landingRoute(new Set())).toBe("/home");
  });

  it("with only /settings/profile built, the fallback candidate lands", () => {
    expect(landingRoute(new Set(["/settings/profile"]), BEFORE_HOME)).toBe("/settings/profile");
    expect(landingRoute(new Set(), BEFORE_HOME)).toBe("/settings/profile");
  });

  it("the first built candidate lands", () => {
    expect(landingRoute(new Set(["/approvals", "/settings/profile"]), BEFORE_HOME)).toBe(
      "/approvals",
    );
    expect(
      landingRoute(new Set(["/settings/profile", "/approvals", "/contracts"]), BEFORE_HOME),
    ).toBe("/contracts");
  });

  it("/ redirects to the landing route and keeps the search string", async () => {
    const queryClient = createQueryClient();
    queryClient.setQueryData(queryKeys.session(), signedInSession());
    const routes = buildRoutes({
      queryClient,
      screenRoutes: [
        probeRoute("SF-01", "/home", "shell.rail.home"),
        probeRoute("SF-12", "/approvals", "shell.rail.approvals"),
        probeRoute("SF-15:profile", "/settings/profile", "shell.rail.settings"),
      ],
    });
    const router = createMemoryRouter(routes, {
      initialEntries: ["/?entity=US01&period=FY2026-P09&book=ASC606"],
    });

    await vi.waitFor(() => {
      expect(router.state.navigation.state).toBe("idle");
      expect(router.state.location.pathname).toBe("/home");
    });
    expect(router.state.location.search).toBe("?entity=US01&period=FY2026-P09&book=ASC606");
    router.dispose();
  });
});
