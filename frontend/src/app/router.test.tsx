// @vitest-environment jsdom
// SCR-IA-06 route objects (SCREENS §0.4; docs/dev-guide.md DG-FE-02): ids and handles, X:not-found
// with "Go to Home", non-matching path parameters and the design gallery gate. The guard of the
// router (docs/dev-guide.md DG-FE-03 rev 1.215; SCREENS §0.5): a control of a page that is leaving
// writes nothing.
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import {
  Link,
  Outlet,
  type RouteObject,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router";
import { afterEach, describe, expect, it } from "vitest";

import { t } from "../lib/i18n/t";
import { destinationAfterSignIn } from "../routes/auth/sign-in";
import { probeRoute, renderApp, signedInSession } from "../test/app";
import { createQueryClient } from "./providers";
import {
  appRoutes,
  buildRoutes,
  builtPaths,
  designRoutes,
  LANDING_ROUTES,
  landingRoute,
} from "./router";
import { isRouteHandle } from "./shell/AppShell";

afterEach(() => {
  cleanup();
});

const ROUTE_ID = /^(?:SF-\d{2}(?::[a-z0-9]+(?:-[a-z0-9]+)*)?|X:[a-z0-9]+(?:-[a-z0-9]+)*)$/;

const APPROVALS = probeRoute("SF-12", "/approvals", "shell.rail.approvals");
const HOME = probeRoute("SF-01", "/home", "shell.rail.home");
const USER = probeRoute("SF-14:user", "/settings/users/:membershipId", "shell.rail.settings");
const DESIGN = probeRoute("X:design", "/design", "shell.productName");

function walk(routes: readonly RouteObject[]): RouteObject[] {
  return routes.flatMap((route) => [route, ...walk(route.children ?? [])]);
}

describe("SCR-IA-06 route objects", () => {
  it("every route object has an id and a handle with sf, screen and titleKey", () => {
    const production = appRoutes(createQueryClient());
    expect(walk(production).map((route) => route.id)).toEqual([
      "X:landing",
      "SF-22",
      "SF-22:mfa-challenge",
      "SF-22:accept-invitation",
      "SF-22:password-reset",
      "SF-22:password-reset-confirm",
      "X:session",
      "SF-22:mfa-enrol",
      "SF-22:password-change",
      "SF-23:select",
      "X:shell",
      "X:route-error",
      "SF-01",
      "SF-02",
      "SF-03:new",
      "X:contract-redirect",
      "SF-03",
      "SF-03:obligation",
      "SF-03:estimates",
      "SF-03:estimate",
      "SF-03:schedules",
      "SF-03:billing",
      "SF-03:journals",
      "SF-03:modifications",
      "SF-03:history",
      "SF-03:edit",
      "SF-07",
      "SF-07:detail",
      "SF-04",
      "X:close-redirect",
      "SF-05",
      "SF-05:close-run",
      "SF-05:journal-preview",
      "SF-05:reconciliations",
      "SF-05:reconciliation",
      "SF-05:history",
      "SF-05:multi-entity",
      "SF-06",
      "SF-06:run",
      "SF-06:entries",
      "SF-06:run-lines",
      "SF-06:run-batches",
      "SF-08",
      "SF-08:report",
      "SF-08:runs",
      "SF-08:run",
      "SF-08:dashboard",
      "SF-09:audit-log",
      "SF-09:verification",
      "SF-10",
      "SF-10:new",
      "X:import-redirect",
      "SF-10:detail",
      "SF-10:templates",
      "SF-11",
      "SF-11:item",
      "SF-16",
      "SF-16:connection",
      "SF-16:sync-run",
      "SF-19:detail",
      "SF-12",
      "SF-12:submitted",
      "SF-12:all",
      "SF-12:request",
      "SF-12:delegations",
      "SF-13",
      "SF-13:revenue",
      "SF-13:control-rules",
      "SF-13:template-version",
      "SF-13:rule-set-version",
      "SF-13:accounting",
      "SF-13:accounting-version",
      "SF-13:ssp-books",
      "SF-13:ssp-book",
      "SF-13:ssp-book-version",
      "SF-13:ssp-calculator",
      "SF-13:ssp-calculator-run",
      "SF-13:account-mapping",
      "SF-13:account-mapping-version",
      "SF-15",
      "SF-15:notifications",
      "SF-15:profile",
      "SF-15:setup",
      "SF-15:entities",
      "SF-15:calendars",
      "SF-15:currencies",
      "SF-15:chart-of-accounts",
      "SF-15:customers",
      "SF-15:customer",
      "SF-15:related-party-groups",
      "SF-15:products",
      "SF-15:product",
      "SF-24:results",
      "X:trace",
      "SF-15:workspace",
      "SF-15:sandbox",
      "SF-14",
      "SF-14:roles",
      "SF-14:sod",
      "SF-14:access-reviews",
      "SF-14:security",
      "SF-14:support-access",
      "SF-14:user",
      "SF-14:access-review",
      "SF-16:developer",
      "X:not-found",
    ]);
    const withScreens = buildRoutes({
      queryClient: createQueryClient(),
      publicRoutes: [probeRoute("SF-22", "/sign-in", "shell.productName")],
      sessionRoutes: [probeRoute("SF-22:mfa-enrol", "/mfa/enrol", "shell.productName")],
      screenRoutes: [APPROVALS, USER],
      designRoutes: designRoutes("1", [DESIGN]),
    });
    for (const route of walk([...production, ...withScreens])) {
      const id = route.id ?? "";
      expect(id).toMatch(ROUTE_ID);
      const handle: unknown = route.handle;
      expect(isRouteHandle(handle)).toBe(true);
      if (isRouteHandle(handle)) {
        expect(handle.screen).toBe(id);
        expect(handle.sf).toBe(id.startsWith("X:") ? "X" : id.split(":", 1)[0]);
        expect(t(handle.titleKey)).not.toBe("");
      }
    }
  });

  it("/some/unknown/path renders Page not found; Go to Home opens the landing route", async () => {
    const { router } = renderApp("/some/unknown/path", { screenRoutes: [HOME, APPROVALS] });
    expect(await screen.findByRole("heading", { level: 1, name: "Page not found" })).toBeTruthy();
    expect(
      screen.getByText("It may have been removed from your access, or the link is incorrect."),
    ).toBeTruthy();
    await waitFor(() => {
      expect(document.title).toBe("Not found · eRev Cloud");
    });

    fireEvent.click(screen.getByRole("button", { name: "Go to Home" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Home" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/home");
  });

  it("/settings/users/not-a-uuid renders the not-found state", async () => {
    renderApp("/settings/users/not-a-uuid");
    expect(await screen.findByRole("heading", { level: 1, name: "Page not found" })).toBeTruthy();
    cleanup();

    renderApp("/settings/users/not-a-uuid", { screenRoutes: [USER] });
    expect(await screen.findByRole("heading", { level: 1, name: "Page not found" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Settings" })).toBeNull();
    await waitFor(() => {
      expect(document.title).toBe("Not found · eRev Cloud");
    });
    cleanup();

    renderApp("/settings/users/2f7c9e4a-8b1d-4c3e-9a6f-5d4b3c2a1e0f", { screenRoutes: [USER] });
    expect(await screen.findByRole("heading", { level: 1, name: "Settings" })).toBeTruthy();
  });

  it("/design is absent when the flag is unset", async () => {
    expect(designRoutes(undefined, [DESIGN])).toEqual([]);
    expect(designRoutes("0", [DESIGN])).toEqual([]);
    expect(builtPaths(appRoutes(createQueryClient())).has("/design")).toBe(false);

    renderApp("/design", { designRoutes: designRoutes(undefined, [DESIGN]) });
    expect(await screen.findByRole("heading", { level: 1, name: "Page not found" })).toBeTruthy();
    cleanup();

    renderApp("/design", { designRoutes: designRoutes("1", [DESIGN]) });
    expect(await screen.findByRole("heading", { level: 1, name: "eRev Cloud" })).toBeTruthy();
  });
});

describe("landing routes", () => {
  it("/ and sign-in land on /home; LANDING_ROUTES equals [/home] (BS-D-08)", async () => {
    expect(LANDING_ROUTES).toEqual(["/home"]);
    // The production table builds SF-01, so every landing is /home.
    expect(landingRoute(builtPaths(appRoutes(createQueryClient())))).toBe("/home");

    const { router } = renderApp("/?entity=AVM-US&period=FY2026-P09&book=ASC606", {
      screenRoutes: [HOME, APPROVALS],
    });
    expect(await screen.findByRole("heading", { level: 1, name: "Home" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/home");
    expect(router.state.location.search).toBe("?entity=AVM-US&period=FY2026-P09&book=ASC606");
    cleanup();

    // Sign-in without `next` opens `/`, which lands on /home.
    const session = signedInSession();
    expect(destinationAfterSignIn(session, null)).toBe("/");
    const signedIn = renderApp(destinationAfterSignIn(session, null), {
      session,
      screenRoutes: [HOME, APPROVALS],
    });
    expect(await screen.findByRole("heading", { level: 1, name: "Home" })).toBeTruthy();
    expect(signedIn.router.state.location.pathname).toBe("/home");
  });
});

// The ways a control writes view state, each without naming a path, and one control that names its
// path. `useNavigate` passes the id of the route the control is rendered by (`fromRouteId`), which
// is what the guard reads: a React Router that stops passing it turns these cases red.
function Controls() {
  const navigate = useNavigate();
  const [, setSearchParams] = useSearchParams();
  const { contractId } = useParams();
  return (
    <>
      <h1 tabIndex={-1}>{contractId ?? "Contracts"}</h1>
      <button
        type="button"
        onClick={() => void navigate({ search: "?f.status=is:DRAFT" }, { replace: true })}
      >
        a search object
      </button>
      <button type="button" onClick={() => void navigate("?f.status=is:DRAFT", { replace: true })}>
        a search string
      </button>
      <button
        type="button"
        onClick={() => setSearchParams({ sort: "-booked_at" }, { replace: true })}
      >
        search parameters
      </button>
      <button type="button" onClick={() => void navigate({ hash: "#totals" })}>
        a fragment
      </button>
      <Link to="?view=mine">a search link</Link>
      <button type="button" onClick={() => void navigate("/home")}>
        a path
      </button>
      <Outlet />
    </>
  );
}

const FIRST = "0b0c1d2e-3f4a-4b5c-8d6e-7f8a9b0c1d2e";
const SECOND = "1c1d2e3f-4a5b-4c6d-9e7f-8a9b0c1d2e3f";

const PATHLESS = [
  ["a search object", "?f.status=is:DRAFT"],
  ["a search string", "?f.status=is:DRAFT"],
  ["search parameters", "?sort=-booked_at"],
  ["a fragment", "#totals"],
  ["a search link", "?view=mine"],
] as const;

function control(name: string): HTMLElement {
  return screen.getByRole(name === "a search link" ? "link" : "button", { name });
}

const CONTRACTS: RouteObject = {
  id: "SF-02",
  path: "/contracts",
  handle: { sf: "SF-02", screen: "SF-02", titleKey: "contracts.list.title" },
  element: <Controls />,
};
const CONTRACT: RouteObject = {
  id: "SF-03",
  path: "/contracts/:contractId",
  handle: { sf: "SF-03", screen: "SF-03", titleKey: "contracts.list.title" },
  element: <Controls />,
  children: [
    {
      id: "SF-03:terms",
      path: "terms",
      handle: { sf: "SF-03", screen: "SF-03:terms", titleKey: "contracts.list.title" },
      element: <p>Terms</p>,
    },
    {
      id: "SF-03:history",
      path: "history",
      handle: { sf: "SF-03", screen: "SF-03:history", titleKey: "contracts.list.title" },
      element: <p>History</p>,
    },
  ],
};
const GUARDED = { screenRoutes: [HOME, CONTRACTS, CONTRACT] };

function address(router: ReturnType<typeof renderApp>["router"]): string {
  const { pathname, search, hash } = router.state.location;
  return `${pathname}${search}${hash}`;
}

async function settled(router: ReturnType<typeof renderApp>["router"]): Promise<void> {
  await waitFor(() => expect(router.state.navigation.state).toBe("idle"));
}

describe("a control of a page that is leaving writes nothing (DG-FE-03 rev 1.215)", () => {
  it.each(PATHLESS)(
    "%s pressed on the list after the router moved to a contract leaves the contract's address",
    async (name) => {
      const { router } = renderApp("/contracts?entity=AVM-US", GUARDED);
      await screen.findByRole("heading", { level: 1, name: "Contracts" });
      const pressed = control(name);

      // The router holds the new address at once; React renders the page for it a task later.
      await router.navigate(`/contracts/${FIRST}/terms?entity=AVM-DE&tab=terms`);
      expect(document.body.contains(pressed)).toBe(true);
      fireEvent.click(pressed);

      await settled(router);
      expect(address(router)).toBe(`/contracts/${FIRST}/terms?entity=AVM-DE&tab=terms`);
      expect(await screen.findByRole("heading", { level: 1, name: FIRST })).toBeTruthy();
    },
  );

  it.each(PATHLESS)("%s pressed on the page that is on screen writes", async (name, written) => {
    const { router } = renderApp("/contracts", GUARDED);
    await screen.findByRole("heading", { level: 1, name: "Contracts" });

    fireEvent.click(control(name));

    await settled(router);
    expect(address(router)).toBe(`/contracts${written}`);
  });

  it("a control that names its path is followed from a page that is leaving", async () => {
    const { router } = renderApp("/contracts", GUARDED);
    await screen.findByRole("heading", { level: 1, name: "Contracts" });
    const pressed = control("a path");

    await router.navigate(`/contracts/${FIRST}/terms`);
    expect(document.body.contains(pressed)).toBe(true);
    fireEvent.click(pressed);

    await settled(router);
    expect(address(router)).toBe("/home");
  });

  it("a control of a route that stays on screen writes after the page inside it changed", async () => {
    const { router } = renderApp(`/contracts/${FIRST}/terms`, GUARDED);
    await screen.findByText("Terms");
    const pressed = control("a search object");

    await router.navigate(`/contracts/${FIRST}/history`);
    expect(screen.queryByText("History")).toBeNull();
    fireEvent.click(pressed);

    await settled(router);
    expect(address(router)).toBe(`/contracts/${FIRST}/history?f.status=is:DRAFT`);
  });

  // Rev 1.230 (item KIT-FILTER-LEAVING-2): a page is leaving, too, while a navigation to another path
  // is on its way. The route is still matched then; a write without a path used to land on the page
  // being left and cancel the member's navigation.
  it.each(PATHLESS)(
    "%s pressed while a navigation to another page is on its way is ignored, and the member arrives",
    async (name) => {
      let arrive: () => void = () => undefined;
      const fetched = new Promise<void>((resolve) => {
        arrive = resolve;
      });
      const slow: RouteObject = {
        id: "SF-08",
        path: "/reports",
        handle: { sf: "SF-08", screen: "SF-08", titleKey: "contracts.list.title" },
        lazy: async () => {
          await fetched;
          return { Component: () => <h1 tabIndex={-1}>Reports</h1> };
        },
      };
      const { router } = renderApp("/contracts?entity=AVM-US", {
        screenRoutes: [HOME, CONTRACTS, CONTRACT, slow],
      });
      await screen.findByRole("heading", { level: 1, name: "Contracts" });
      void router.navigate("/reports?entity=AVM-US");
      await waitFor(() => expect(router.state.navigation.state).toBe("loading"));

      fireEvent.click(control(name));
      expect(address(router)).toBe("/contracts?entity=AVM-US");
      expect(router.state.navigation.location?.pathname).toBe("/reports");

      arrive();
      expect(await screen.findByRole("heading", { level: 1, name: "Reports" })).toBeTruthy();
      expect(address(router)).toBe("/reports?entity=AVM-US");
    },
  );

  it("a write while a navigation to the same path is on its way is taken", async () => {
    let finish: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      finish = resolve;
    });
    let loads = 0;
    const loading: RouteObject = {
      ...CONTRACTS,
      // The first load answers at once; the second, a filter being applied, is held.
      loader: async () => {
        loads += 1;
        if (loads === 2) {
          await held;
        }
        return null;
      },
    };
    const { router } = renderApp("/contracts", { screenRoutes: [HOME, loading, CONTRACT] });
    await screen.findByRole("heading", { level: 1, name: "Contracts" });

    fireEvent.click(control("a search object"));
    await waitFor(() => expect(router.state.navigation.state).toBe("loading"));
    expect(router.state.navigation.location?.pathname).toBe("/contracts");
    fireEvent.click(control("search parameters"));
    finish();

    await settled(router);
    expect(address(router)).toBe("/contracts?sort=-booked_at");
  });

  it("the limit: the guard knows routes, not records, so a page that stays on its route while its record changes still writes", async () => {
    const { router } = renderApp(`/contracts/${FIRST}`, GUARDED);
    await screen.findByRole("heading", { level: 1, name: FIRST });
    const pressed = control("a search object");

    await router.navigate(`/contracts/${SECOND}?tab=terms`);
    expect(screen.queryByRole("heading", { level: 1, name: SECOND })).toBeNull();
    fireEvent.click(pressed);

    await settled(router);
    expect(address(router)).toBe(`/contracts/${SECOND}?f.status=is:DRAFT`);
  });
});
