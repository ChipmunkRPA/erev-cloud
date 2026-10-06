// @vitest-environment jsdom
// Saved views (DESIGN_SYSTEM DS-CMP-10 "Saved views"; SCREENS SCR-URL-07, SCR-IA-07; 04 API-R-16): changing a
// filter shows the unsaved dot, Save as new view posts the screen code and config, Set as my default,
// Rename and Delete call API-R-16, and the active view id is `view=` in the URL.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import {
  createMemoryRouter,
  MemoryRouter,
  RouterProvider,
  useLocation,
  useNavigate,
} from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "../../app/providers";
import type { SavedView } from "../../lib/api/queries/saved-views";
import { apiUrl, installMswServer, server } from "../../test/msw";
import { SavedViewSelector } from "./SavedViewSelector";
import { initialColumnState, type GridColumnState } from "./types";

installMswServer();

afterEach(() => {
  cleanup();
});

const MEMBERSHIP = "0b9f7c1a-4d2e-4a8b-9c3d-5e6f7a8b9c0d";
const OTHER_MEMBERSHIP = "7a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d";

const COLUMNS: GridColumnState = initialColumnState([
  { id: "contract", header: "Contract", kind: "identifier", value: () => null },
  { id: "customer", header: "Customer", kind: "text", value: () => null },
  { id: "status", header: "Status", kind: "status", value: () => null },
]);

function view(
  id: string,
  name: string,
  membershipId: string,
  config: Record<string, unknown>,
): SavedView {
  return {
    id,
    membership_id: membershipId,
    screen_code: "SF-02",
    name,
    config,
    is_shared: membershipId !== MEMBERSHIP,
    is_favourite: false,
    created_at: "2026-09-13T09:00:00Z",
    updated_at: "2026-09-13T09:00:00Z",
    row_version: 1,
  };
}

const OWN_CONFIG = {
  columns: ["contract", "customer", "status"],
  widths: {},
  pinned: { start: ["contract"], end: [] },
  sort: null,
  filters: { status: "is:DRAFT" },
  query: "",
  currency_view: null,
};

interface Captured {
  readonly method: string;
  readonly path: string;
  readonly body: unknown;
  readonly idempotencyKey: string | null;
}

function installApi(): Captured[] {
  const captured: Captured[] = [];
  let views: SavedView[] = [
    view("v-own", "My open drafts", MEMBERSHIP, OWN_CONFIG),
    view("v-shared", "Team pipeline", OTHER_MEMBERSHIP, { sort: "-transaction_price" }),
  ];
  const record = async (request: Request) => {
    const text = await request.text();
    captured.push({
      method: request.method,
      path: new URL(request.url).pathname,
      body: text === "" ? null : (JSON.parse(text) as unknown),
      idempotencyKey: request.headers.get("Idempotency-Key"),
    });
    return text === "" ? {} : (JSON.parse(text) as Record<string, unknown>);
  };
  server.use(
    http.get(apiUrl("/api/v1/saved-views"), ({ request }) => {
      expect(new URL(request.url).searchParams.get("screen_code")).toBe("SF-02");
      return HttpResponse.json({ items: views, next_cursor: null });
    }),
    http.post(apiUrl("/api/v1/saved-views"), async ({ request }) => {
      const body = await record(request);
      const created = view(
        "v-new",
        String(body.name),
        MEMBERSHIP,
        body.config as Record<string, unknown>,
      );
      views = [...views, created];
      return HttpResponse.json(created, { status: 201 });
    }),
    http.patch(apiUrl("/api/v1/saved-views/:id"), async ({ request, params }) => {
      const body = await record(request);
      views = views.map((item) =>
        item.id === params.id ? { ...item, ...body, row_version: item.row_version + 1 } : item,
      );
      return HttpResponse.json(views.find((item) => item.id === params.id));
    }),
    http.delete(apiUrl("/api/v1/saved-views/:id"), async ({ request, params }) => {
      await record(request);
      views = views.filter((item) => item.id !== params.id);
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return captured;
}

function Probe() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <output data-testid="search">{location.search}</output>
      <button
        type="button"
        onClick={() => void navigate({ search: "?view=v-own&f.status=is:ACTIVE" })}
      >
        Change the filter
      </button>
    </>
  );
}

function renderSelector(search: string, onApplyColumns = vi.fn()) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[`/contracts${search}`]}>
        <SavedViewSelector
          screenCode="SF-02"
          membershipId={MEMBERSHIP}
          defaultLabel="All contracts"
          quickLists={[{ literal: "ON_HOLD", label: "On hold", sort: "-updated_at" }]}
          columnState={COLUMNS}
          defaultColumnState={COLUMNS}
          onApplyColumns={onApplyColumns}
          testId="SF-02-saved-view"
        />
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return onApplyColumns;
}

function currentSearch(): string {
  return screen.getByTestId("search").textContent ?? "";
}

function openMenu(): HTMLElement {
  fireEvent.click(screen.getByRole("button", { name: /^View:/ }));
  return screen.getByRole("menu", { name: "Views" });
}

describe("saved views", () => {
  it("changing a filter shows the unsaved dot and the active view id is view= in the URL", async () => {
    installApi();
    const onApplyColumns = renderSelector("?view=v-own&f.status=is:DRAFT");

    expect(await screen.findByRole("button", { name: "View: My open drafts" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Change the filter" }));
    const trigger = screen.getByRole("button", { name: "View: My open drafts, unsaved changes" });
    expect(trigger.getAttribute("data-testid")).toBe("SF-02-saved-view");

    const menu = openMenu();
    expect(
      within(within(menu).getByRole("group", { name: "Quick lists" }))
        .getAllByRole("menuitemradio")
        .map((item) => item.textContent),
    ).toEqual(["All contracts", "On hold"]);
    expect(within(menu).getByRole("group", { name: "My views" })).toBeTruthy();
    expect(
      within(menu)
        .getByRole("menuitemradio", { name: "My open drafts" })
        .getAttribute("aria-checked"),
    ).toBe("true");
    expect(document.activeElement).toBe(
      within(menu).getByRole("menuitemradio", { name: "My open drafts" }),
    );
    fireEvent.click(
      within(within(menu).getByRole("group", { name: "Shared views" })).getByRole("menuitemradio", {
        name: "Team pipeline",
      }),
    );

    expect(currentSearch()).toBe("?view=v-shared&sort=-transaction_price");
    expect(screen.getByRole("button", { name: "View: Team pipeline" })).toBeTruthy();
    expect(onApplyColumns).toHaveBeenLastCalledWith(COLUMNS);
    const shared = openMenu();
    expect(within(shared).queryByRole("menuitem", { name: "Rename" })).toBeNull();
    expect(within(shared).queryByRole("menuitem", { name: "Delete" })).toBeNull();
  });

  it("Save as new view sends POST /saved-views with screen_code and config", async () => {
    const captured = installApi();
    renderSelector("?view=v-own&f.status=is:ACTIVE");
    await screen.findByRole("button", { name: "View: My open drafts, unsaved changes" });

    fireEvent.click(within(openMenu()).getByRole("menuitem", { name: "Save as new view" }));
    const dialog = screen.getByRole("dialog", { name: "Save as new view" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save view" }));
    expect(within(dialog).getByText("Enter a name.")).toBeTruthy();
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Name/ }), {
      target: { value: "Active contracts" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save view" }));

    await waitFor(() => expect(currentSearch()).toBe("?view=v-new&f.status=is:ACTIVE"));
    expect(captured).toEqual([
      {
        method: "POST",
        path: "/api/v1/saved-views",
        body: {
          screen_code: "SF-02",
          name: "Active contracts",
          config: { ...OWN_CONFIG, filters: { status: "is:ACTIVE" } },
          is_shared: false,
          is_favourite: false,
        },
        idempotencyKey: expect.stringMatching(/^[0-9a-f-]{36}$/) as unknown as string,
      },
    ]);
    expect(await screen.findByRole("button", { name: "View: Active contracts" })).toBeTruthy();
  });

  it("Set as my default, Rename and Delete call API-R-16", async () => {
    const captured = installApi();
    renderSelector("?view=v-own&f.status=is:DRAFT");
    await screen.findByRole("button", { name: "View: My open drafts" });

    fireEvent.click(within(openMenu()).getByRole("menuitem", { name: "Set as my default" }));
    await waitFor(() => expect(captured).toHaveLength(1));
    expect(captured[0]).toMatchObject({
      method: "PATCH",
      path: "/api/v1/saved-views/v-own",
      body: { config: { ...OWN_CONFIG, is_default: true } },
    });
    await waitFor(() =>
      expect(
        within(openMenu()).getByRole("menuitemradio", { name: /My open drafts/ }).textContent,
      ).toContain("Default"),
    );
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });

    fireEvent.click(within(openMenu()).getByRole("menuitem", { name: "Rename" }));
    const rename = screen.getByRole("dialog", { name: "Rename view" });
    const input = within(rename).getByRole("textbox", { name: /^Name/ });
    expect((input as HTMLInputElement).value).toBe("My open drafts");
    fireEvent.change(input, { target: { value: "Draft contracts" } });
    fireEvent.click(within(rename).getByRole("button", { name: "Rename view" }));
    await waitFor(() => expect(captured).toHaveLength(2));
    expect(captured[1]).toMatchObject({
      method: "PATCH",
      path: "/api/v1/saved-views/v-own",
      body: { name: "Draft contracts" },
    });
    expect(await screen.findByRole("button", { name: "View: Draft contracts" })).toBeTruthy();

    fireEvent.click(within(openMenu()).getByRole("menuitem", { name: "Delete" }));
    fireEvent.click(
      within(screen.getByRole("alertdialog", { name: "Delete Draft contracts?" })).getByRole(
        "button",
        { name: "Delete view" },
      ),
    );
    await waitFor(() => expect(currentSearch()).toBe("?f.status=is:DRAFT"));
    expect(captured[2]).toMatchObject({
      method: "DELETE",
      path: "/api/v1/saved-views/v-own",
      body: null,
    });
    expect(screen.getByRole("button", { name: /^View: All contracts/ })).toBeTruthy();
  });

  // RPT-VIEWER-LATE-RUN-1, the selector on a record page (a contract's Journals tab): "Save view" and
  // "Delete" answer after an awaited command. A view belongs to the screen, not to the record, so
  // the answer is written only while the page that sent the command is the one on screen. Before,
  // the next contract's address took the first contract's search.
  describe("on a record page, an answer that arrives after the page changed", () => {
    function renderOnRecord(first: string) {
      const router = createMemoryRouter(
        [
          {
            path: "/contracts/:contractId/journals",
            element: (
              <SavedViewSelector
                screenCode="SF-02"
                membershipId={MEMBERSHIP}
                defaultLabel="All lines"
                columnState={COLUMNS}
                defaultColumnState={COLUMNS}
                onApplyColumns={vi.fn()}
              />
            ),
          },
        ],
        { initialEntries: [first] },
      );
      render(
        <QueryClientProvider client={createQueryClient()}>
          <RouterProvider router={router} />
        </QueryClientProvider>,
      );
      return router;
    }
    /** Holds the answers of one method until the test lets them go. */
    function hold(method: "post" | "delete") {
      let release: () => void = () => undefined;
      const held = new Promise<void>((resolve) => {
        release = resolve;
      });
      const seen = { sent: false, answered: false };
      const path = method === "post" ? "/api/v1/saved-views" : "/api/v1/saved-views/:id";
      server.use(
        http[method](apiUrl(path), async ({ request }) => {
          const text = await request.text();
          seen.sent = true;
          await held;
          seen.answered = true;
          if (method === "delete") {
            return new HttpResponse(null, { status: 204 });
          }
          const body = JSON.parse(text) as { name: string; config: Record<string, unknown> };
          return HttpResponse.json(view("v-new", body.name, MEMBERSHIP, body.config), {
            status: 201,
          });
        }),
      );
      return { seen, release: () => release() };
    }
    const address = (router: ReturnType<typeof createMemoryRouter>) =>
      `${router.state.location.pathname}${router.state.location.search}`;
    const SECOND = "/contracts/K-02/journals?f.status=is:DRAFT";

    it("a view saved on one contract is not written onto the next contract's address", async () => {
      installApi();
      const { seen, release } = hold("post");
      const router = renderOnRecord(
        "/contracts/K-01/journals?view=v-own&f.status=is:ACTIVE&row=17",
      );
      await screen.findByRole("button", { name: "View: My open drafts, unsaved changes" });
      fireEvent.click(within(openMenu()).getByRole("menuitem", { name: "Save as new view" }));
      const dialog = screen.getByRole("dialog", { name: "Save as new view" });
      fireEvent.change(within(dialog).getByRole("textbox", { name: /^Name/ }), {
        target: { value: "Active lines" },
      });
      fireEvent.click(within(dialog).getByRole("button", { name: "Save view" }));
      await waitFor(() => expect(seen.sent).toBe(true));

      await router.navigate(SECOND);
      release();
      await waitFor(() => expect(seen.answered).toBe(true));
      await new Promise((resolve) => setTimeout(resolve, 100));
      expect(address(router)).toBe(SECOND);
    });

    it("a view deleted on one contract does not rewrite the next contract's address", async () => {
      installApi();
      const { seen, release } = hold("delete");
      const router = renderOnRecord("/contracts/K-01/journals?view=v-own&f.status=is:DRAFT&row=17");
      await screen.findByRole("button", { name: "View: My open drafts" });
      fireEvent.click(within(openMenu()).getByRole("menuitem", { name: "Delete" }));
      fireEvent.click(
        within(screen.getByRole("alertdialog", { name: "Delete My open drafts?" })).getByRole(
          "button",
          { name: "Delete view" },
        ),
      );
      await waitFor(() => expect(seen.sent).toBe(true));

      await router.navigate(SECOND);
      release();
      await waitFor(() => expect(seen.answered).toBe(true));
      await new Promise((resolve) => setTimeout(resolve, 100));
      expect(address(router)).toBe(SECOND);
    });

    it("on the page that sent it, a saved view is chosen on the search the router holds", async () => {
      installApi();
      const { seen, release } = hold("post");
      const router = renderOnRecord("/contracts/K-01/journals?view=v-own&f.status=is:ACTIVE");
      await screen.findByRole("button", { name: "View: My open drafts, unsaved changes" });
      fireEvent.click(within(openMenu()).getByRole("menuitem", { name: "Save as new view" }));
      const dialog = screen.getByRole("dialog", { name: "Save as new view" });
      fireEvent.change(within(dialog).getByRole("textbox", { name: /^Name/ }), {
        target: { value: "Active lines" },
      });
      fireEvent.click(within(dialog).getByRole("button", { name: "Save view" }));
      await waitFor(() => expect(seen.sent).toBe(true));

      // The same contract; its search moves on while the save is unanswered.
      await router.navigate("/contracts/K-01/journals?view=v-own&f.status=is:ACTIVE&sort=-amount");
      release();
      await waitFor(() =>
        expect(address(router)).toBe(
          "/contracts/K-01/journals?view=v-new&sort=-amount&f.status=is:ACTIVE",
        ),
      );
    });
  });
});
