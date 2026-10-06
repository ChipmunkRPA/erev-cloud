// @vitest-environment jsdom
// X:route-error (SCREENS_B §12.4; PRD ERR-34, CPY-05): a throwing child renders the heading, the body
// with a reference, "Reload page", "Go to Home" and "Copy reference" inside the shell; focus moves to
// the heading, which is announced assertively once.
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { data, type RouteObject } from "react-router";
import { afterEach, beforeEach, describe, expect, it, type MockInstance, vi } from "vitest";

import { announce } from "../../lib/a11y/announce";
import { ApiProblem } from "../../lib/api/problems";
import { probeRoute, renderApp } from "../../test/app";

vi.mock("../../lib/a11y/announce", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/a11y/announce")>();
  return { ...actual, announce: vi.fn(actual.announce) };
});

let consoleError: MockInstance;

beforeEach(() => {
  // React reports the caught render error on the console; the boundary is what is under test.
  consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  consoleError.mockRestore();
  vi.mocked(announce).mockClear();
});

const REQUEST_ID = "0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d";
const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const APPROVALS = probeRoute("SF-12", "/approvals", "shell.rail.approvals");
const HOME = probeRoute("SF-01", "/home", "shell.rail.home");

function Thrower({ error }: { readonly error: unknown }): never {
  throw error;
}

function throwingRoute(error: unknown): RouteObject {
  return {
    id: "SF-12:all",
    path: "/approvals/all",
    handle: { sf: "SF-12", screen: "SF-12:all", titleKey: "shell.rail.approvals" },
    element: <Thrower error={error} />,
  };
}

describe("X:route-error", () => {
  it("a throwing child renders the error page inside the shell and announces it once", async () => {
    const { router } = renderApp("/approvals/all", {
      strict: true,
      screenRoutes: [
        HOME,
        APPROVALS,
        throwingRoute(new Error("column contract_id does not exist")),
      ],
    });

    const heading = await screen.findByRole("heading", { level: 1, name: "Something went wrong" });
    await waitFor(() => {
      expect(document.activeElement).toBe(heading);
    });
    expect(screen.getByTestId("X-banner-route-error").textContent).toMatch(
      new RegExp(
        `^Something went wrong on our side\\. The request was not completed and nothing was saved\\. Reference ${UUID}\\.$`,
      ),
    );
    expect(screen.getByTestId("X-page")).toBeTruthy();
    expect(document.body.textContent).not.toContain("contract_id");
    expect(screen.getByRole("button", { name: "Reload page" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Go to Home" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Copy reference" })).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toBe("Something went wrong");
    expect(vi.mocked(announce).mock.calls.filter((call) => call[1] === "assertive")).toEqual([
      ["Something went wrong", "assertive"],
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Go to Home" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Home" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/home");
  });

  it("an API problem shows its request id, and Copy reference copies it", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const problem = new ApiProblem({
      type: "about:blank",
      slug: null,
      title: "Internal Server Error",
      status: 500,
      detail: null,
      code: null,
      errors: [],
      requestId: REQUEST_ID,
    });
    renderApp("/approvals/all", { screenRoutes: [throwingRoute(problem)] });

    const body = await screen.findByTestId("X-banner-route-error");
    expect(body.textContent).toBe(
      `Something went wrong on our side. The request was not completed and nothing was saved. Reference ${REQUEST_ID}.`,
    );
    expect(body.hasAttribute("data-volatile")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Copy reference" }));

    expect(writeText).toHaveBeenCalledWith(REQUEST_ID);
    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toBe("Reference copied");
    });
  });

  it("a 404 route response renders the not-found state", async () => {
    renderApp("/approvals/all", {
      screenRoutes: [
        {
          ...throwingRoute(null),
          element: null,
          loader: () => {
            throw data(null, { status: 404 });
          },
        },
      ],
    });

    expect(await screen.findByRole("heading", { level: 1, name: "Page not found" })).toBeTruthy();
  });
});
