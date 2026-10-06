// @vitest-environment jsdom
// SF-06 Journal runs "Run journals" (BUILD_SPEC CLO-26; SCREENS_B §3.1, §0.3 SB-R-06; SCREENS SCR-URL-20;
// D-89 L7-3-Q-32): after a calculation succeeds, the toast's "Open run" opens SF-06:run in the calculation's
// own entity, period and book, in SCR-URL-20 order, and never carries the page search. API answers are
// contract fakes of 04 API-R-38 and API-S-Job (V-C).
import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../../app/router";
import { installMemoryStorage, renderApp, signedInMe } from "../../../test/app";
import { installGridViewport } from "../../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import { REFUSAL_REFERENCE, REFUSAL_TITLE, refusedWith } from "../../../test/refusals";

installMswServer();
installMemoryStorage();
installGridViewport();
// The dialog reads the calendar, then each calculation polls its job before the toast shows.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
});

const MAYA = signedInMe({
  permissions: ["contract.read", "config.read", "journal.run", "journal.export", "report.export"],
});

/** Per entity: the calculation job and the run its result names. */
const CALCULATIONS: Readonly<Record<string, { readonly job: string; readonly run: string }>> = {
  "AVM-US": {
    job: "5e4d3c2b-1a0f-4e9d-8c7b-6a5f4e3d2c01",
    run: "7c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e01",
  },
  "AVM-DE": {
    job: "5e4d3c2b-1a0f-4e9d-8c7b-6a5f4e3d2c02",
    run: "7c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e02",
  },
};

function entity(id: string, code: string, name: string, currency: string) {
  return {
    id,
    code,
    name,
    books: [],
    calendar_id: "3d4e5f60-7a8b-4c9d-8e0f-1a2b3c4d5e6f",
    country_code: null,
    created_at: "2026-01-01T00:00:00Z",
    functional_currency: currency,
    is_active: true,
    parent_entity_id: null,
    row_version: 1,
    tax_id: null,
    time_zone: "UTC",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

const ENTITIES = [
  entity("0a1b2c3d-4e5f-4a6b-8c7d-000000000001", "AVM-US", "Avenmoor US Inc.", "USD"),
  entity("0a1b2c3d-4e5f-4a6b-8c7d-000000000002", "AVM-DE", "Avenmoor GmbH", "EUR"),
];

const SEPTEMBER = {
  id: "1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e09",
  entity: { id: ENTITIES[0]?.id, code: "AVM-US", name: "Avenmoor US Inc." },
  book: "ASC606",
  period: {
    id: "2c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e09",
    period_key: "FY2026-P09",
    name: "Sep 2026",
    fiscal_year: 2026,
    period_no: 9,
    quarter_no: 3,
    start_date: "2026-09-01",
    end_date: "2026-09-30",
  },
  state: "open",
  is_first_open: true,
  row_version: 1,
  state_changed_at: "2026-09-01T00:00:00Z",
  close_run: null,
  current_lock: null,
  blockers: {},
};

function serve(): Record<string, unknown>[] {
  const posted: Record<string, unknown>[] = [];
  const empty = () => HttpResponse.json({ items: [], next_cursor: null });
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), empty),
    http.get(apiUrl("/api/v1/entities"), () =>
      HttpResponse.json({ items: ENTITIES, next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/books"), empty),
    http.get(apiUrl("/api/v1/currencies"), () =>
      HttpResponse.json({
        items: [
          { code: "USD", name: "US dollar", minor_unit: 2, numeric_code: "840", is_active: true },
          { code: "EUR", name: "Euro", minor_unit: 2, numeric_code: "978", is_active: true },
        ],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/jobs"), empty),
    http.get(apiUrl("/api/v1/saved-views"), empty),
    http.get(apiUrl("/api/v1/journal-runs"), empty),
    http.get(apiUrl("/api/v1/periods"), () =>
      HttpResponse.json({ items: [SEPTEMBER], next_cursor: null }),
    ),
    http.post(apiUrl("/api/v1/journal-runs"), async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      posted.push(body);
      const job = CALCULATIONS[String(body.entity_code)]?.job ?? "";
      return HttpResponse.json(
        { id: job, kind: "JOURNAL_RUN_CALCULATE", state: "QUEUED" },
        { status: 202, headers: { Location: `/api/v1/jobs/${job}` } },
      );
    }),
    http.get(apiUrl("/api/v1/jobs/:jobId"), ({ params }) => {
      const found = Object.values(CALCULATIONS).find((item) => item.job === String(params.jobId));
      return HttpResponse.json({
        id: String(params.jobId),
        kind: "JOURNAL_RUN_CALCULATE",
        state: "SUCCEEDED",
        progress: null,
        started_at: "2026-09-16T11:59:00Z",
        finished_at: "2026-09-16T11:59:30Z",
        problem: null,
        result: { href: `/api/v1/journal-runs/${found?.run ?? ""}` },
      });
    }),
    // SF-06:run after "Open run": the route and its search are asserted, not the run frame.
    http.get(apiUrl("/api/v1/journal-runs/:runId"), () =>
      problemResponse("not-found", 404, "Journal run not found"),
    ),
    http.get(apiUrl("/api/v1/journal-runs/:runId/summary"), () =>
      problemResponse("not-found", 404, "Journal run not found"),
    ),
  );
  return posted;
}

/** The "Open run" action of the toast whose message reads `message`. */
async function openRunOf(message: string): Promise<HTMLElement> {
  const text = await screen.findByText(message);
  const toast = text.closest<HTMLElement>('[role="status"]');
  if (toast === null) {
    throw new Error(`no toast for ${message}`);
  }
  return within(toast).getByRole("button", { name: "Open run" });
}

describe("SF-06 Run journals", () => {
  it("open run keeps the run context", async () => {
    const posted = serve();
    // The page search carries a filter chip that a run link must not keep.
    const { router } = renderApp(
      "/journals?entity=AVM-US&period=FY2026-P09&book=ASC606&f.state=is:draft",
      { me: MAYA, screenRoutes: SCREEN_ROUTES },
    );

    fireEvent.click(await screen.findByRole("button", { name: "Run journals" }));
    const dialog = await screen.findByRole("dialog", { name: "Run journals" });
    // A second entity in the same dialog.
    const entities = within(dialog).getByRole("combobox", { name: /^Entities/ });
    fireEvent.change(entities, { target: { value: "AVM-DE" } });
    fireEvent.mouseDown(await within(dialog).findByRole("option", { name: "AVM-DE" }));
    await waitFor(() => {
      expect(within(dialog).getByRole("combobox", { name: /^Period/ }).textContent).toContain(
        "Sep 2026",
      );
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Calculate journals" }));
    await waitFor(() => {
      expect(posted.map((body) => body.entity_code)).toEqual(["AVM-US", "AVM-DE"]);
    });
    expect(posted[0]).toMatchObject({ book: "ASC606", period_key: "FY2026-P09" });

    fireEvent.click(await openRunOf("Journals calculated for AVM-US Sep 2026."));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(
        `/journals/runs/${CALCULATIONS["AVM-US"]?.run ?? ""}`,
      );
    });
    expect(router.state.location.search).toBe("?entity=AVM-US&period=FY2026-P09&book=ASC606");

    // The second calculation's toast keeps its own entity code.
    fireEvent.click(await openRunOf("Journals calculated for AVM-DE Sep 2026."));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(
        `/journals/runs/${CALCULATIONS["AVM-DE"]?.run ?? ""}`,
      );
    });
    expect(router.state.location.search).toBe("?entity=AVM-DE&period=FY2026-P09&book=ASC606");
  });

  // SCREENS §0.6 SCR-PERM-02 (a) (rev 1.30) and SCREENS_B §3.1 (rev 1.79; item W-12, slice c): a
  // journal run is a record of one entity. The entry "Run journals" asks any entity; its form offers
  // the entities `journal.run` is held for, chooses the context entity only when it is one of them,
  // and reads the periods of the first chosen entity with `config.read` for that entity. A form with
  // no entity, or with an entity whose periods are not read, lists no period and starts nothing.
  it("the form offers the entities journal.run is held for, and reads the periods with config.read for the chosen entity", async () => {
    const germany = ENTITIES[1]?.id ?? "";
    const member = (run: "*" | string[]) =>
      signedInMe({
        permissions: MAYA.permissions,
        permission_scopes: {
          "contract.read": "*",
          "config.read": [germany],
          "journal.run": run,
          "journal.export": "*",
          "report.export": "*",
        },
      });
    const open = async (run: "*" | string[]) => {
      const posted = serve();
      const asked: (string | null)[] = [];
      server.use(
        http.get(apiUrl("/api/v1/periods"), ({ request }) => {
          asked.push(new URL(request.url).searchParams.get("entity"));
          return HttpResponse.json({ items: [SEPTEMBER], next_cursor: null });
        }),
      );
      const view = renderApp("/journals?entity=AVM-US&period=FY2026-P09&book=ASC606", {
        me: member(run),
        screenRoutes: SCREEN_ROUTES,
      });
      const entry = await screen.findByRole("button", { name: "Run journals" });
      await waitFor(() => expect(view.queryClient.isFetching()).toBe(0));
      // What the shell asked for its own context is not the form's.
      asked.length = 0;
      fireEvent.click(entry);
      const dialog = await screen.findByRole("dialog", { name: "Run journals" });
      return { view, dialog, asked, posted };
    };
    const calculate = (dialog: HTMLElement) =>
      fireEvent.click(within(dialog).getByRole("button", { name: "Calculate journals" }));
    const NO_ENTITY = "Choose at least one entity.";
    const NO_PERIOD = "Choose an open, soft-closed or reopened period.";
    const offered = async (dialog: HTMLElement) => {
      fireEvent.change(within(dialog).getByRole("combobox", { name: /^Entities/ }), {
        target: { value: "AVM" },
      });
      return (await within(dialog).findAllByRole("option")).map((option) => option.textContent);
    };

    // Hers for AVM-DE alone, in the context of AVM-US: the entry is there, AVM-US is neither chosen
    // nor offered, and its periods are not asked for.
    const scoped = await open([germany]);
    expect(within(scoped.dialog).queryByRole("button", { name: "Remove AVM-US" })).toBeNull();
    // Nothing is chosen: the period list is empty, and "Calculate journals" says what is missing
    // and starts nothing.
    const period = within(scoped.dialog).getByRole("combobox", { name: /^Period/ });
    expect(period.textContent).not.toContain("2026");
    calculate(scoped.dialog);
    expect(await within(scoped.dialog).findByText(NO_ENTITY)).toBeTruthy();
    expect(within(scoped.dialog).getByText(NO_PERIOD)).toBeTruthy();
    expect(scoped.posted).toEqual([]);
    expect(await offered(scoped.dialog)).toEqual(["AVM-DE"]);
    fireEvent.mouseDown(within(scoped.dialog).getByRole("option", { name: "AVM-DE" }));
    expect(within(scoped.dialog).getByRole("button", { name: "Remove AVM-DE" })).toBeTruthy();
    await waitFor(() => expect(scoped.asked).toEqual(["AVM-DE"]));
    await waitFor(() => expect(scoped.view.queryClient.isFetching()).toBe(0));
    expect(scoped.asked).toEqual(["AVM-DE"]);
    // With her entity chosen and its periods read, the two sentences are gone.
    await waitFor(() => expect(within(scoped.dialog).queryByText(NO_PERIOD)).toBeNull());
    expect(within(scoped.dialog).queryByText(NO_ENTITY)).toBeNull();
    expect(period.textContent).toContain("Sep 2026");
    cleanup();

    // Hers for all entities, with `config.read` for AVM-DE alone: AVM-US is chosen, both are offered,
    // and the periods of AVM-US are not asked for.
    const whole = await open("*");
    expect(within(whole.dialog).getByRole("button", { name: "Remove AVM-US" })).toBeTruthy();
    expect(await offered(whole.dialog)).toEqual(["AVM-US", "AVM-DE"]);
    await waitFor(() => expect(whole.view.queryClient.isFetching()).toBe(0));
    expect(whole.asked).toEqual([]);
    // The periods of AVM-US are not hers to read: the list stays empty, the form says so in the
    // period's own sentence and starts nothing.
    expect(
      within(whole.dialog).getByRole("combobox", { name: /^Period/ }).textContent,
    ).not.toContain("2026");
    calculate(whole.dialog);
    expect(await within(whole.dialog).findByText(NO_PERIOD)).toBeTruthy();
    expect(within(whole.dialog).queryByText(NO_ENTITY)).toBeNull();
    expect(whole.posted).toEqual([]);
  });

  it("the second entity gets no answer: the next press replays the first entity's start under its key and starts the second", async () => {
    // DG-FE-05 rev 1.156 (item W-23): one press sends one POST /journal-runs per entity. Through one
    // hook the first entity's key was forgotten when the second went out, and the next press started
    // a second journal run for the first entity.
    const posted = serve();
    const keys: Record<string, (string | null)[]> = {};
    server.use(
      http.post(apiUrl("/api/v1/journal-runs"), async ({ request }) => {
        const body = (await request.clone().json()) as { readonly entity_code: string };
        const sent = (keys[body.entity_code] ??= []);
        sent.push(request.headers.get("Idempotency-Key"));
        // The first start of AVM-DE gets no answer; every other request reaches the API.
        return body.entity_code === "AVM-DE" && sent.length === 1
          ? HttpResponse.error()
          : undefined;
      }),
    );
    renderApp("/journals?entity=AVM-US&period=FY2026-P09&book=ASC606", {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    fireEvent.click(await screen.findByRole("button", { name: "Run journals" }));
    const dialog = await screen.findByRole("dialog", { name: "Run journals" });
    fireEvent.change(within(dialog).getByRole("combobox", { name: /^Entities/ }), {
      target: { value: "AVM-DE" },
    });
    fireEvent.mouseDown(await within(dialog).findByRole("option", { name: "AVM-DE" }));
    await waitFor(() => {
      expect(within(dialog).getByRole("combobox", { name: /^Period/ }).textContent).toContain(
        "Sep 2026",
      );
    });
    const press = within(dialog).getByRole("button", { name: "Calculate journals" });

    fireEvent.click(press);
    // AVM-US is accepted and its calculation is followed; AVM-DE gets no answer and the dialog stays.
    expect(await screen.findByText("No answer came back from the server. Try again.")).toBeTruthy();
    expect(keys["AVM-US"]).toHaveLength(1);
    expect(keys["AVM-DE"]).toHaveLength(1);
    expect(posted.map((body) => body.entity_code)).toEqual(["AVM-US"]);
    expect(screen.getByRole("dialog", { name: "Run journals" })).toBeTruthy();

    await waitFor(() => {
      expect(press.getAttribute("aria-busy")).toBeNull();
    });
    fireEvent.click(press);
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Run journals" })).toBeNull();
    });
    // AVM-US went out again under its key — the API replays the run it started — and AVM-DE under
    // the key of the start that got no answer.
    expect(keys["AVM-US"]).toHaveLength(2);
    expect(keys["AVM-US"]?.[1]).toBe(keys["AVM-US"]?.[0]);
    expect(keys["AVM-DE"]).toHaveLength(2);
    expect(keys["AVM-DE"]?.[1]).toBe(keys["AVM-DE"]?.[0]);
    // Each calculation is followed once.
    expect(await screen.findAllByText("Journals calculated for AVM-US Sep 2026.")).toHaveLength(1);
    expect(await screen.findAllByText("Journals calculated for AVM-DE Sep 2026.")).toHaveLength(1);
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): "Run journals" shows no message of
  // the API at a field, so the banner says every sentence of a refusal; one that names a member was
  // shown nowhere.
  it("Run journals under a refused start says every sentence of the refusal", async () => {
    const sentence = "A journal run of this period is waiting for approval.";
    serve();
    server.use(
      http.post(apiUrl("/api/v1/journal-runs"), () => refusedWith({ period_key: sentence })),
    );
    renderApp("/journals?entity=AVM-US&period=FY2026-P09&book=ASC606", {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    fireEvent.click(await screen.findByRole("button", { name: "Run journals" }));
    const dialog = await screen.findByRole("dialog", { name: "Run journals" });
    await waitFor(() => {
      expect(within(dialog).getByRole("combobox", { name: /^Period/ }).textContent).toContain(
        "Sep 2026",
      );
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Calculate journals" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + sentence + REFUSAL_REFERENCE);
  });
});
