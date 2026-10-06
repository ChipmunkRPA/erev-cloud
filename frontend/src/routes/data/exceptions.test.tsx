// @vitest-environment jsdom
// SF-11 Exception queue and SF-11:item (BUILD_SPEC DIN-17; SCREENS §13.3 to §13.5, §13.9; §0.4 RT-46,
// RT-47; DESIGN_SYSTEM DS-CMP-08, DS-CMP-11; 04 API-R-44, §16.14; PRD BR-DAT-04). Against the DIN-11
// contract (D-81): the blocked-dismissal line of committed input, the queue binding with the default
// Status chip and the severity sort, and the dismissal confirmation with its reason.
import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import type { ExceptionItem } from "../../lib/api/queries/exceptions";
import { installMemoryStorage, preloadScreens, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";

installMswServer();
installMemoryStorage();
installGridViewport();

// F-ADM Q21: the first test paid the exception queue's module evaluation inside its findBy window.
beforeAll(() => preloadScreens(SCREEN_ROUTES, ["SF-11"]));

afterEach(() => {
  cleanup();
});

const MAYA = signedInMe({ permissions: ["contract.read", "exception.resolve", "import.upload"] });
const UPLOAD_ID = "6a7b8c9d-0e1f-4a2b-8c3d-4e5f6a7b8c9d";
const ROW_ID = "1b2c3d4e-5f6a-4b7c-8d9e-0f1a2b3c4d5e";
const WLD_B_04 = "2c3d4e5f-6a7b-4c8d-9e0f-1a2b3c4d5e6f";
const QUARANTINE = "3d4e5f6a-7b8c-4d9e-8f0a-2b3c4d5e6f7a";
const REASON = "Replaced by the corrected import committed on the same day.";
const AVM_US = {
  id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000001",
  code: "AVM-US",
  name: "Avenmoor US Inc.",
  is_active: true,
  books: [],
};
const AVM_DE = {
  id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000002",
  code: "AVM-DE",
  name: "Avenmoor GmbH",
  is_active: true,
  books: [],
};

function item(overrides: Partial<ExceptionItem> = {}): ExceptionItem {
  return {
    id: WLD_B_04,
    exception_no: "EXC-000014",
    source: "IMPORT",
    code: "PROGRESS_OVER_DELIVERY",
    severity: "BLOCKING",
    disposition: "remediable",
    status: "OPEN",
    priority: 3,
    title: "Delivery exceeds the remaining quantity",
    message:
      "Row 5, column Quantity: BG-AVM-0004, obligation O1 (AVM-SEAT-MO): requested 13, remaining 12. (PROGRESS_OVER_DELIVERY)",
    suggestion: null,
    field: "quantity",
    business_key: "BG-AVM-0004",
    source_payload: null,
    import_upload_id: UPLOAD_ID,
    import_row_id: ROW_ID,
    sync_run_id: null,
    source_record_id: null,
    contract_id: null,
    contract_external_id: null,
    obligation_id: null,
    combination_group_id: null,
    combination_group_code: null,
    entity_id: null,
    period_id: null,
    close_run_id: null,
    journal_run_id: null,
    owner_membership_id: null,
    owner: null,
    dedupe_key: `IMPORT:PROGRESS_OVER_DELIVERY:${UPLOAD_ID}:5:quantity`,
    occurrence_count: 1,
    last_seen_at: "2026-09-12T09:30:00Z",
    resolution: null,
    resolved_at: null,
    resolved_by: null,
    waiver_approval_request_id: null,
    reprocessed_at: null,
    created_at: "2026-09-12T09:30:00Z",
    updated_at: "2026-09-12T09:30:00Z",
    row_version: 1,
    available_actions: ["ASSIGN", "REQUEST_WAIVER", "DISMISS"],
    dismiss_blocked_reason: null,
    ...overrides,
  };
}

/** An engine quarantine: committed input, so dismissal is blocked (04 §16.14). */
const ENGINE_ITEM = item({
  id: QUARANTINE,
  exception_no: "EXC-000031",
  source: "ENGINE",
  code: "ENGINE_INVARIANT_VIOLATION",
  title: "Calculation quarantined",
  message: "Contract SF-ORD-10490: the computation broke invariant T-ENG-01 and was quarantined.",
  field: null,
  business_key: null,
  import_upload_id: null,
  import_row_id: null,
  contract_id: "4e5f6a7b-8c9d-4e0f-9a1b-3c4d5e6f7a8b",
  contract_external_id: "SF-ORD-10490",
  occurrence_count: 2,
  available_actions: ["ASSIGN", "REQUEST_WAIVER"],
  dismiss_blocked_reason: "INPUT_COMMITTED",
  row_version: 3,
});

interface Served {
  readonly items: () => readonly ExceptionItem[];
  readonly searches?: string[];
  readonly commands?: {
    readonly path: string;
    readonly headers: Headers;
    readonly body: unknown;
  }[];
}

function serve({ items, searches = [], commands = [] }: Served) {
  const empty = () => HttpResponse.json({ items: [], next_cursor: null });
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), empty),
    http.get(apiUrl("/api/v1/entities"), empty),
    http.get(apiUrl("/api/v1/books"), empty),
    http.get(apiUrl("/api/v1/periods"), empty),
    http.get(apiUrl("/api/v1/contracts"), empty),
    http.get(apiUrl("/api/v1/imports"), empty),
    http.get(apiUrl("/api/v1/exceptions"), ({ request }) => {
      const url = new URL(request.url);
      searches.push(url.search);
      const statuses = url.searchParams.getAll("status");
      const listed = items().filter(
        (candidate) => statuses.length === 0 || statuses.includes(candidate.status),
      );
      return HttpResponse.json(
        {
          items: url.searchParams.get("limit") === "1" ? listed.slice(0, 1) : listed,
          next_cursor: null,
        },
        { headers: { "X-Erev-Total-Count": String(listed.length) } },
      );
    }),
    http.get(apiUrl("/api/v1/exceptions/:id"), ({ params }) => {
      const found = items().find((candidate) => candidate.id === params.id);
      return found === undefined
        ? HttpResponse.json({ title: "Not found", status: 404 }, { status: 404 })
        : HttpResponse.json(found);
    }),
    http.get(apiUrl(`/api/v1/imports/${UPLOAD_ID}`), () =>
      HttpResponse.json({
        id: UPLOAD_ID,
        import_no: "IMP-000004",
        status: "INVALID",
        file: { original_filename: "avm-us-progress-2026-09-invalid.csv" },
      }),
    ),
    http.get(apiUrl(`/api/v1/imports/${UPLOAD_ID}/rows`), () =>
      HttpResponse.json({
        items: [{ id: ROW_ID, row_number: 5, sheet_name: "avm-us-progress-2026-09-invalid.csv" }],
        next_cursor: null,
      }),
    ),
    http.post(apiUrl("/api/v1/exceptions/:id/:command"), async ({ request, params }) => {
      commands.push({
        path: `${String(params.id)}/${String(params.command)}`,
        headers: request.headers,
        body: await request.json(),
      });
      return HttpResponse.json(
        item({
          status: "DISMISSED",
          resolution: REASON,
          resolved_at: "2026-09-15T10:00:00Z",
          available_actions: [],
          row_version: 2,
        }),
      );
    }),
  );
}

describe("SF-11 Exception queue", () => {
  it("dismiss blocked line", async () => {
    serve({ items: () => [item(), ENGINE_ITEM] });
    renderApp(`/data/exceptions/${QUARANTINE}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const pane = await screen.findByRole("region", {
      name: "Exception details: Calculation quarantined",
    });
    expect(pane.getAttribute("data-testid")).toBe("SF-11-pane-exception");
    const actions = await within(pane).findByRole("group", { name: "Actions" });
    expect(within(actions).getByRole("button", { name: "Request waiver" })).toBeTruthy();
    // SCREENS §13.5: without DISMISS the button is not rendered, not shown disabled (SCR-PERM-03).
    expect(within(pane).queryByRole("button", { name: "Dismiss exception" })).toBeNull();
    const describedBy = actions.getAttribute("aria-describedby") ?? "";
    expect(describedBy).not.toBe("");
    expect(document.getElementById(describedBy)?.textContent).toBe(
      "Dismissal applies only to input that was never committed. Request a waiver instead.",
    );
    expect(within(pane).getByText("ENGINE_INVARIANT_VIOLATION")).toBeTruthy();
    expect(within(pane).getByText("SF-ORD-10490")).toBeTruthy();
    expect(within(pane).getByText("2 occurrences · last seen 12 Sep 2026 09:30 UTC")).toBeTruthy();

    // The dismissible WLD-B-04 item renders the action and no blocked line.
    fireEvent.mouseDown(
      await within(await screen.findByRole("listbox", { name: "Exceptions" })).findByRole(
        "option",
        {
          name: /PROGRESS_OVER_DELIVERY/,
        },
      ),
    );
    const wld = await screen.findByRole("region", {
      name: "Exception details: Delivery exceeds the remaining quantity",
    });
    expect(await within(wld).findByRole("button", { name: "Dismiss exception" })).toBeTruthy();
    expect(
      within(wld).getByRole("group", { name: "Actions" }).hasAttribute("aria-describedby"),
    ).toBe(false);
    expect(within(wld).queryByText(/Request a waiver instead\./)).toBeNull();
  });

  // SCREENS §13.5 (lane API-GAPS's browser pass of SF-11): the line told the member to request a
  // waiver while no waiver was offered to them.
  it("the dismissal line names the waiver only while Request waiver is offered", async () => {
    serve({ items: () => [{ ...ENGINE_ITEM, available_actions: ["ASSIGN"] }] });
    renderApp(`/data/exceptions/${QUARANTINE}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const pane = await screen.findByRole("region", {
      name: "Exception details: Calculation quarantined",
    });
    const line = await within(pane).findByTestId("SF-11-dismiss-blocked");
    expect(line.textContent).toBe("Dismissal applies only to input that was never committed.");
    expect(within(pane).queryByRole("button", { name: "Request waiver" })).toBeNull();
    expect(within(pane).queryByText(/Request a waiver instead\./)).toBeNull();
  });

  // SCREENS §13.5 Owner (the same pass): after a refused assign the field kept showing the member
  // the API had refused, while the item still belonged to its owner.
  it("a refused assign leaves the Owner field on the item's owner and says why", async () => {
    const commands: NonNullable<Served["commands"]> = [];
    serve({ items: () => [item()], commands });
    server.use(
      http.post(apiUrl(`/api/v1/exceptions/${WLD_B_04}/assign`), async ({ request }) => {
        commands.push({
          path: `${WLD_B_04}/assign`,
          headers: request.headers,
          body: await request.json(),
        });
        return problemResponse("validation-failed", 422, "Check the highlighted fields", {
          detail: "This member cannot open the exception. Choose an owner who can read it.",
        });
      }),
    );
    renderApp(`/data/exceptions/${WLD_B_04}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const pane = await screen.findByRole("region", {
      name: "Exception details: Delivery exceeds the remaining quantity",
    });
    const owner = await within(pane).findByRole("combobox", { name: /^Owner/ });
    expect((owner as HTMLInputElement).value).toBe("Unassigned");
    fireEvent.keyDown(owner, { key: "ArrowDown" });
    fireEvent.mouseDown(await within(pane).findByRole("option", { name: "Maya Chen" }));
    // While the command is on its way the field shows the member chosen.
    expect((owner as HTMLInputElement).value).toBe("Maya Chen");

    expect(
      await within(pane).findByText(
        "This member cannot open the exception. Choose an owner who can read it.",
      ),
    ).toBeTruthy();
    expect(commands.map((command) => command.path)).toEqual([`${WLD_B_04}/assign`]);
    await waitFor(() => expect((owner as HTMLInputElement).value).toBe("Unassigned"));
  });

  it("queue binds the default status chip and the severity sort", async () => {
    const searches: string[] = [];
    serve({ items: () => [item(), ENGINE_ITEM], searches });
    const { router } = renderApp("/data/exceptions?entity=AVM-US", {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    await waitFor(() => {
      expect(router.state.location.search).toBe("?entity=AVM-US&f.status=in:OPEN,IN_PROGRESS");
    });
    expect(await screen.findByRole("heading", { level: 1, name: "Exceptions" })).toBeTruthy();
    expect(await screen.findByText("2 open")).toBeTruthy();
    const box = screen.getByTestId("SF-11-grid-exceptions");
    const list = await within(box).findByRole("listbox", { name: "Exceptions" });
    const options = within(list).getAllByRole("option");
    expect(options).toHaveLength(2);
    expect(options[0]?.getAttribute("data-testid")).toBe("SF-11-row-progress-over-delivery");
    expect(options[0]?.textContent).toContain("Delivery exceeds the remaining quantity");
    expect(options[0]?.textContent).toContain("Blocking");
    expect(options[0]?.textContent).toContain("Import");
    expect(options[1]?.textContent).toContain("Seen 2 times");
    expect(within(box).getByText("2 exceptions")).toBeTruthy();
    // The FilterBar reads the replaced URL on its next render, so the chip is awaited.
    expect(
      await screen.findByRole("button", { name: "Status is Open or In progress, edit filter" }),
    ).toBeTruthy();
    expect(
      await screen.findByText("Select an exception to see its location, message and next steps."),
    ).toBeTruthy();
    // SCREENS §13.4: the chips and the default sort reach the read; the context entity does not
    // filter the queue (L6-4-Q-24).
    expect(searches).toContain(
      "?status=OPEN&status=IN_PROGRESS&sort=severity&limit=200&count=true",
    );
    expect(searches.every((search) => !search.includes("entity="))).toBe(true);
    // No link asked for the items that hold a lock: the queue says nothing of one.
    expect(screen.queryByTestId("SF-11-banner-blocking")).toBeNull();
    expect(searches.every((search) => !search.includes("blocking="))).toBe(true);
  });

  it("blocking passes through to the read, and the queue says that it is cut down", async () => {
    // SCREENS §13.4 rev 1.37 (04 §16.14 rev 1.206): BLK-02 of the close cockpit and the close row of
    // Home open the queue with `blocking=<period id>` — the items that hold that period's lock. A list
    // cut down by a parameter nobody sees reads as "there are only these", so the queue says it.
    const PERIOD = "7c1d2e3f-4a5b-4c6d-8e7f-000000000909";
    const searches: string[] = [];
    serve({ items: () => [item(), ENGINE_ITEM], searches });
    // The newest first: a parameter of the address that "Show all exceptions" must leave alone.
    const { router } = renderApp(`/data/exceptions?blocking=${PERIOD}&sort=-created_at`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    const asked = () => new URLSearchParams(router.state.location.search);

    const banner = await screen.findByTestId("SF-11-banner-blocking");
    expect(
      within(banner).getByRole("heading", {
        name: "Showing the exceptions that hold the lock of one period.",
      }),
    ).toBeTruthy();
    // The default Status chip joins the address, and the parameter stays in it.
    await waitFor(() => {
      expect(asked().get("f.status")).toBe("in:OPEN,IN_PROGRESS");
    });
    expect(asked().get("blocking")).toBe(PERIOD);
    await waitFor(() => {
      expect(searches).toContain(
        `?status=OPEN&status=IN_PROGRESS&blocking=${PERIOD}&sort=-created_at&limit=200&count=true`,
      );
    });
    // "<n> open" in the header stays the count of every open exception: it is read without it.
    expect(searches).toContain("?status=OPEN&status=IN_PROGRESS&limit=1&count=true");
    // An item opened from the list keeps the list it came from.
    const list = await screen.findByRole("listbox", { name: "Exceptions" });
    fireEvent.mouseDown(
      await within(list).findByRole("option", { name: /PROGRESS_OVER_DELIVERY/ }),
    );
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/data/exceptions/${WLD_B_04}`);
    });
    expect(asked().get("blocking")).toBe(PERIOD);
    expect(screen.getByTestId("SF-11-banner-blocking")).toBeTruthy();

    // "Show all exceptions" drops the parameter and nothing else.
    fireEvent.click(within(banner).getByRole("button", { name: "Show all exceptions" }));
    await waitFor(() => {
      expect(asked().has("blocking")).toBe(false);
    });
    expect(asked().get("f.status")).toBe("in:OPEN,IN_PROGRESS");
    expect(asked().get("sort")).toBe("-created_at");
    expect(router.state.location.pathname).toBe(`/data/exceptions/${WLD_B_04}`);
    await waitFor(() => {
      expect(screen.queryByTestId("SF-11-banner-blocking")).toBeNull();
    });
    await waitFor(() => {
      expect(searches).toContain(
        "?status=OPEN&status=IN_PROGRESS&sort=-created_at&limit=200&count=true",
      );
    });
  });

  it("a control starts from the address the router holds, not from the search last rendered", async () => {
    // docs/dev-guide.md DG-FE-03 rule (2). The page renders an address a moment after the router takes
    // it. In a whole run under load (2026-10-02) the default Status chip was in the address and not
    // yet rendered when a control was pressed, and the control's write — made from the search last
    // rendered — took the chip out again: the one red of "blocking passes through to the read". Two
    // presses before a render are that moment made on purpose: the second must not undo the first.
    const PERIOD = "7c1d2e3f-4a5b-4c6d-8e7f-000000000909";
    const twice = (first: () => void, second: () => void) => {
      act(() => {
        first();
        second();
      });
    };
    const queue = async (search: string, items: readonly ExceptionItem[]) => {
      serve({ items: () => [...items] });
      const { router } = renderApp(`/data/exceptions?blocking=${PERIOD}&${search}`, {
        me: MAYA,
        screenRoutes: SCREEN_ROUTES,
      });
      const asked = () => new URLSearchParams(router.state.location.search);
      const banner = await screen.findByTestId("SF-11-banner-blocking");
      const showAll = within(banner).getByRole("button", { name: "Show all exceptions" });
      return { router, asked, showAll };
    };
    const listed = async (search: string) => {
      const page = await queue(search, [item(), ENGINE_ITEM]);
      await waitFor(() => {
        expect(page.asked().get("f.status")).toBe("in:OPEN,IN_PROGRESS");
      });
      const list = await screen.findByRole("listbox", { name: "Exceptions" });
      const row = await within(list).findByRole("option", { name: /PROGRESS_OVER_DELIVERY/ });
      return { ...page, row };
    };
    const sortBy = async (current: string, next: string) => {
      fireEvent.click(await screen.findByRole("button", { name: `Sort: ${current}` }));
      return screen.findByRole("menuitem", { name: next });
    };

    // "Show all exceptions", then a row: the row's page is not cut down to the lock again.
    const opened = await listed("sort=-created_at");
    twice(
      () => fireEvent.click(opened.showAll),
      () => fireEvent.mouseDown(opened.row),
    );
    await waitFor(() => {
      expect(opened.router.state.location.pathname).toBe(`/data/exceptions/${WLD_B_04}`);
    });
    expect(opened.asked().has("blocking")).toBe(false);
    expect(opened.asked().get("f.status")).toBe("in:OPEN,IN_PROGRESS");
    expect(opened.asked().get("sort")).toBe("-created_at");
    cleanup();

    // "Show all exceptions", then another order: the order's write does not bring the lock back.
    const ordered = await listed("sort=-created_at");
    const oldest = await sortBy("Newest", "Oldest");
    twice(
      () => fireEvent.click(ordered.showAll),
      () => fireEvent.click(oldest),
    );
    await waitFor(() => {
      expect(ordered.asked().get("sort")).toBe("created_at");
    });
    expect(ordered.asked().has("blocking")).toBe(false);
    expect(ordered.asked().get("f.status")).toBe("in:OPEN,IN_PROGRESS");
    cleanup();

    // Another order, then "Show all exceptions": the order chosen stays.
    const shown = await listed("sort=-created_at");
    const first = await sortBy("Newest", "Oldest");
    twice(
      () => fireEvent.click(first),
      () => fireEvent.click(shown.showAll),
    );
    await waitFor(() => {
      expect(shown.asked().has("blocking")).toBe(false);
    });
    expect(shown.asked().get("sort")).toBe("created_at");
    expect(shown.asked().get("f.status")).toBe("in:OPEN,IN_PROGRESS");
    cleanup();

    // "Show all exceptions", then "Clear filters" on an empty list under a chip: both are done.
    const cleared = await queue("f.severity=is:INFO", []);
    const clear = await within(await screen.findByTestId("SF-11-grid-exceptions")).findByRole(
      "button",
      { name: "Clear filters" },
    );
    twice(
      () => fireEvent.click(cleared.showAll),
      () => fireEvent.click(clear),
    );
    await waitFor(() => {
      expect(cleared.asked().has("f.severity")).toBe(false);
    });
    expect(cleared.asked().has("blocking")).toBe(false);
  });

  it("an empty list under blocking offers the way out that changes something", async () => {
    // Nothing holds the lock — every item was resolved, or the reader may read none of them. The
    // list is a cut-down one: "No exceptions" with "View imports" would say there are none at all.
    const PERIOD = "7c1d2e3f-4a5b-4c6d-8e7f-000000000909";
    serve({ items: () => [] });
    const { router } = renderApp(`/data/exceptions?blocking=${PERIOD}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    const asked = () => new URLSearchParams(router.state.location.search);

    expect(
      await screen.findByRole("heading", { name: "No exceptions match these filters" }),
    ).toBeTruthy();
    expect(screen.queryByTestId("SF-11-empty-exceptions")).toBeNull();
    // No chip cuts the list down as well: "Clear filters" would change nothing, so it is not offered.
    const master = screen.getByTestId("SF-11-grid-exceptions");
    expect(within(master).queryByRole("button", { name: "Clear filters" })).toBeNull();
    fireEvent.click(within(master).getByRole("button", { name: "Show all exceptions" }));
    await waitFor(() => {
      expect(asked().has("blocking")).toBe(false);
    });
    expect(await screen.findByTestId("SF-11-empty-exceptions")).toBeTruthy();
    cleanup();

    // With a chip beside it the chips are what "Clear filters" clears; the lock's list stays.
    serve({ items: () => [] });
    const chipped = renderApp(`/data/exceptions?blocking=${PERIOD}&f.severity=is:INFO`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    const after = () => new URLSearchParams(chipped.router.state.location.search);
    const cut = await screen.findByTestId("SF-11-grid-exceptions");
    expect(within(cut).queryByRole("button", { name: "Show all exceptions" })).toBeNull();
    fireEvent.click(await within(cut).findByRole("button", { name: "Clear filters" }));
    await waitFor(() => {
      expect(after().has("f.severity")).toBe(false);
    });
    expect(after().get("blocking")).toBe(PERIOD);
    expect(await within(cut).findByRole("button", { name: "Show all exceptions" })).toBeTruthy();
    expect(screen.getByTestId("SF-11-banner-blocking")).toBeTruthy();
  });

  it("dismissal confirms with a reason", async () => {
    const commands: { readonly path: string; readonly headers: Headers; readonly body: unknown }[] =
      [];
    serve({ items: () => [item()], commands });
    renderApp(`/data/exceptions/${WLD_B_04}?entity=AVM-US`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const pane = await screen.findByRole("region", {
      name: "Exception details: Delivery exceeds the remaining quantity",
    });
    expect(
      await within(pane).findByRole("link", { name: "avm-us-progress-2026-09-invalid.csv" }),
    ).toBeTruthy();
    await waitFor(() => {
      expect(
        within(pane)
          .getByRole("link", { name: "avm-us-progress-2026-09-invalid.csv" })
          .getAttribute("href"),
      ).toBe(`/data/imports/${UPLOAD_ID}/validate?entity=AVM-US&row=5`);
    });
    fireEvent.click(within(pane).getByRole("button", { name: "Dismiss exception" }));

    const dialog = await screen.findByRole("alertdialog", {
      name: "Dismiss exception PROGRESS_OVER_DELIVERY?",
    });
    expect(dialog.getAttribute("data-testid")).toBe("SF-11-dialog-dismiss");
    expect(
      within(dialog).getByText(
        "Dismissal applies only to input that was never committed. The item counts as cleared for the close gates.",
      ),
    ).toBeTruthy();
    expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: "Cancel" }));
    const danger = within(dialog).getByRole("button", { name: "Dismiss exception" });
    expect(danger.className).toContain("bg-danger-solid");

    fireEvent.click(danger);
    expect(await within(dialog).findByText("Enter at least 10 characters.")).toBeTruthy();
    expect(commands).toHaveLength(0);

    fireEvent.change(within(dialog).getByLabelText(/^Reason/), { target: { value: REASON } });
    fireEvent.click(danger);
    expect(
      await screen.findByText(
        "Dismissed PROGRESS_OVER_DELIVERY. The item counts as cleared for the close gates.",
      ),
    ).toBeTruthy();
    expect(commands.map((command) => command.path)).toEqual([`${WLD_B_04}/dismiss`]);
    expect(commands[0]?.body).toEqual({ comment: REASON });
    expect(commands[0]?.headers.get("Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/);
    expect(commands[0]?.headers.get("If-Match")).toBe('"r1"');
  });

  it("resolution and owner name their people, read with the item", async () => {
    // 04 §16.14 (rev 1.139): `resolved_by` and `owner` are API-S-Actor. Maya holds no
    // `user.manage`, so the member directory is not hers to read, and no handler serves
    // `GET /users` here.
    const resolved = {
      status: "RESOLVED",
      resolved_at: "2026-09-15T10:00:00Z",
      available_actions: [],
    } as const;
    serve({
      items: () => [
        item({
          ...resolved,
          resolution: REASON,
          resolved_by: {
            id: "9f8e7d6c-5b4a-4c3d-8e2f-1a0b9c8d7e6f",
            kind: "USER",
            display_name: "Priya Raman",
          },
          owner_membership_id: "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d",
          owner: {
            id: "8d7c6b5a-4f3e-4d2c-9b1a-0f9e8d7c6b5a",
            kind: "USER",
            display_name: "Omar Haddad",
          },
        }),
        {
          ...ENGINE_ITEM,
          ...resolved,
          resolution: "The recomputation cleared the condition.",
          resolved_by: { id: null, kind: "SYSTEM", display_name: "System" },
        },
      ],
    });
    renderApp(`/data/exceptions/${WLD_B_04}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    const pane = await screen.findByRole("region", {
      name: "Exception details: Delivery exceeds the remaining quantity",
    });
    expect(await within(pane).findByText("Resolved by")).toBeTruthy();
    expect(within(pane).getByText("Priya Raman")).toBeTruthy();
    expect(within(pane).queryByText(/^User /)).toBeNull();
    // The owner of an item Maya cannot assign is shown by name, not as "Member <id>".
    expect(within(pane).getByText("Omar Haddad")).toBeTruthy();
    expect(within(pane).queryByText(/^Member /)).toBeNull();

    cleanup();
    renderApp(`/data/exceptions/${QUARANTINE}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    const quarantined = await screen.findByRole("region", {
      name: "Exception details: Calculation quarantined",
    });
    expect(await within(quarantined).findByText("Resolved by")).toBeTruthy();
    expect(within(quarantined).getByText("System")).toBeTruthy();
  });
  // SCREENS §0.6 SCR-PERM-02 (rev 1.30; item W-12, slice c; the supervisor's ruling of 2026-10-01 on
  // the slice's special cases, case 4): a command on an exception is asked for the exception's own
  // entity, and for any entity when it has none (one raised on an import that names no entity).
  it("the commands of an exception are offered when exception.resolve is held for its entity, and for any entity when it has none", async () => {
    const theirs = item({
      id: "5f6a7b8c-9d0e-4f1a-8b2c-3d4e5f6a7b01",
      exception_no: "EXC-000041",
      title: "An exception of AVM-US",
      entity_id: AVM_US.id,
    });
    const hers = item({
      id: "5f6a7b8c-9d0e-4f1a-8b2c-3d4e5f6a7b02",
      exception_no: "EXC-000042",
      title: "An exception of AVM-DE",
      entity_id: AVM_DE.id,
    });
    const free = item({
      id: "5f6a7b8c-9d0e-4f1a-8b2c-3d4e5f6a7b03",
      exception_no: "EXC-000043",
      title: "An exception of no entity",
      entity_id: null,
    });
    const member = signedInMe({
      permissions: MAYA.permissions,
      permission_scopes: {
        "contract.read": "*",
        "exception.resolve": [AVM_DE.id],
        "import.upload": "*",
      },
    });
    const open = async (opened: ExceptionItem) => {
      cleanup();
      serve({ items: () => [theirs, hers, free] });
      renderApp(`/data/exceptions/${opened.id}`, { me: member, screenRoutes: SCREEN_ROUTES });
      const pane = await screen.findByRole("region", {
        name: `Exception details: ${opened.title}`,
      });
      // The code renders with the item, whoever reads it.
      await within(pane).findByText("PROGRESS_OVER_DELIVERY");
      return pane;
    };

    const other = await open(theirs);
    expect(within(other).queryByRole("group", { name: "Actions" })).toBeNull();
    expect(within(other).queryByRole("combobox", { name: /^Owner/ })).toBeNull();

    for (const opened of [hers, free]) {
      const pane = await open(opened);
      const actions = within(pane).getByRole("group", { name: "Actions" });
      expect(within(actions).getByRole("button", { name: "Request waiver" })).toBeTruthy();
      expect(within(actions).getByRole("button", { name: "Dismiss exception" })).toBeTruthy();
      expect(within(pane).getByRole("combobox", { name: /^Owner/ })).toBeTruthy();
    }
  });

  // SCREENS §0.6 SCR-PERM-02 (a): the periods the queue and an item's location read are those of the
  // context entity, so `config.read` is asked for it.
  it("the periods of the context entity are read with config.read for that entity", async () => {
    const dated = item({ entity_id: AVM_US.id, period_id: "2c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e09" });
    const periodRequests: string[] = [];
    const open = async (entityId: string) => {
      cleanup();
      serve({ items: () => [dated] });
      periodRequests.length = 0;
      server.use(
        http.get(apiUrl("/api/v1/entities"), () =>
          HttpResponse.json({ items: [AVM_US, AVM_DE], next_cursor: null }),
        ),
        http.get(apiUrl("/api/v1/periods"), ({ request }) => {
          periodRequests.push(new URL(request.url).search);
          return HttpResponse.json({ items: [], next_cursor: null });
        }),
      );
      const view = renderApp(`/data/exceptions/${dated.id}?entity=AVM-US&book=ASC606`, {
        me: signedInMe({
          permissions: [...MAYA.permissions, "config.read"],
          permission_scopes: {
            "contract.read": "*",
            "config.read": [entityId],
            "exception.resolve": "*",
            "import.upload": "*",
          },
        }),
        screenRoutes: SCREEN_ROUTES,
      });
      await screen.findByRole("region", { name: `Exception details: ${dated.title}` });
      return view;
    };

    const first = await open(AVM_US.id);
    await waitFor(() => expect(periodRequests.length).toBeGreaterThan(0));
    await waitFor(() => expect(first.queryClient.isFetching()).toBe(0));

    const second = await open(AVM_DE.id);
    await waitFor(() => expect(second.queryClient.isFetching()).toBe(0));
    expect(periodRequests).toEqual([]);
  });
});
