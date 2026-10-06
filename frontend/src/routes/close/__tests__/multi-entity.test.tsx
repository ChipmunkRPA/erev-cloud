// @vitest-environment jsdom
// SF-05:multi-entity (BUILD_SPEC CLO-24; SCREENS_B §1.5, §0.4 E-04, E-62; SCREENS RT-27, SCR-PERM-01,
// SCR-ST-03; 04 API-R-39 §16.8; PRD J-13.16, J-13-AC-9, WLD-P-05): close runs for several
// entities of one period. Each chosen entity closes the period of its own calendar with the context
// period's dates; "Start close runs" sends one `POST /close-runs` per entity, in the order shown, and
// each row reads its own answer — a new run, the run that had not ended, or the refusal by name. No
// period is locked. API answers are contract fakes of 04 §16.4 and §16.8.
import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../../app/router";
import { contextStorageKey } from "../../../app/shell/ContextPill";
import type { CloseRun, CloseRunStatus } from "../../../lib/api/queries/close-runs";
import { CLOSE_RUN_STEP_CODES } from "../../../lib/api/queries/close-runs";
import type { Me } from "../../../lib/api/queries/me";
import type { Book, Entity, Period, PeriodState } from "../../../lib/api/queries/tenant";
import { daysInMonth } from "../../../lib/format";
import { installMemoryStorage, renderApp, signedInMe, signedInSession } from "../../../test/app";
import { narrowColumns } from "../../../test/grid-headers";
import { installGridViewport } from "../../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import { multiEntityColumns } from "../multi-entity";

installMswServer();
installMemoryStorage();
installGridViewport();
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
});

const STAMP = "2026-01-05T09:00:00Z";
const CONTEXT = "entity=AVM-US&period=FY2026-P09&book=ASC606";
const PAGE_PATH = `/close/multi-entity?${CONTEXT}`;
const JOB_ID = "5e4d3c2b-1a0f-4e9d-8c7b-6a5f4e3d2c51";
const JP_CLOSED =
  "FY2027-P06 of AVM-JP in book ASC606 is closed. A close run needs an open period, a period in soft close or a reopened one.";

const MARCUS_ACTOR = {
  id: "6d2e9b8f-3c5a-4d7e-8f9b-8a7c6d5e4f3b",
  display_name: "Marcus Webb",
  kind: "USER" as const,
};
/** Controller: `period.close` (RT-27). */
const MARCUS: Me = signedInMe({
  user: {
    id: MARCUS_ACTOR.id,
    email: "marcus@example.test",
    display_name: MARCUS_ACTOR.display_name,
    status: "ACTIVE",
  },
  permissions: ["contract.read", "config.read", "period.close", "period.lock"],
});
/** A reader of the close without `period.close`. */
const ROBERT: Me = signedInMe({ permissions: ["contract.read", "config.read"] });

function entity(index: number, code: string, name: string, books: readonly string[]): Entity {
  const id = `0a1b2c3d-4e5f-4a6b-8c7d-00000000000${String(index)}`;
  return {
    id,
    code,
    name,
    functional_currency: "USD",
    time_zone: "UTC",
    calendar_id: "6f7a8b9c-0d1e-4f2a-8b3c-000000000001",
    parent_entity_id: null,
    country_code: null,
    tax_id: null,
    is_active: true,
    books: books.map((book, position) => ({
      id: `5e6f7a8b-9c0d-4e1f-8a2b-0000000000${String(index)}${String(position)}`,
      entity_id: id,
      book_code: book as Book["code"],
      is_enabled: true,
      first_period_id: "1c2d3e4f-5a6b-4c7d-8e9f-000000000001",
      first_period_key: "FY2026-P01",
      created_at: STAMP,
      updated_at: STAMP,
      row_version: 1,
    })),
    created_at: STAMP,
    updated_at: STAMP,
    row_version: 1,
  };
}

const ENTITIES: readonly Entity[] = [
  entity(1, "AVM-US", "Avenmoor Inc. (Demo)", ["ASC606"]),
  entity(2, "AVM-UK", "Avenmoor Ltd (Demo)", ["ASC606", "IFRS15"]),
  entity(3, "AVM-DE", "Avenmoor GmbH (Demo)", ["ASC606", "IFRS15"]),
  entity(4, "AVM-JP", "Avenmoor Media KK (Demo)", ["ASC606"]),
  // Keeps no ASC 606 book: not offered for this close.
  entity(5, "AVM-FR", "Avenmoor SAS (Demo)", ["IFRS15"]),
];

function book(code: Book["code"], name: string, primary: boolean): Book {
  return {
    id: `7a8b9c0d-1e2f-4a3b-8c4d-0000000000${primary ? "01" : code === "IFRS15" ? "02" : "03"}`,
    code,
    name,
    is_enabled: true,
    is_primary: primary,
    posting_target: "GL_PRIMARY",
    created_at: STAMP,
    updated_at: STAMP,
    row_version: 1,
  };
}

const BOOKS: readonly Book[] = [
  book("ASC606", "ASC 606", true),
  book("IFRS15", "IFRS 15", false),
  book("LEGACY", "Legacy", false),
];

function periodOf(
  owner: Entity,
  key: string,
  dates: readonly [string, string],
  state: PeriodState,
): Period {
  const [, year, number] = /^FY(\d{4})-P(\d{2})$/.exec(key) ?? [];
  return {
    id: `7c1d2e3f-4a5b-4c6d-8e7f-${owner.id.slice(-4)}${key.slice(2, 6)}${key.slice(-2)}00`,
    entity: { id: owner.id, code: owner.code, name: owner.name },
    book: "ASC606",
    period: {
      id: `1c2d3e4f-5a6b-4c7d-8e9f-${owner.id.slice(-4)}${key.slice(2, 6)}${key.slice(-2)}00`,
      period_key: key,
      name: key,
      fiscal_year: Number(year),
      period_no: Number(number),
      quarter_no: Math.ceil(Number(number) / 3),
      start_date: dates[0],
      end_date: dates[1],
    },
    state,
    state_changed_at: STAMP,
    is_first_open: state === "open",
    current_lock: null,
    blockers: {
      approvals_pending: 0,
      batches_unacknowledged: 0,
      batches_unexported: 0,
      exceptions_open: 0,
      groups_dirty: 0,
      holds_open: 0,
      interface_failures: 0,
      jobs_failed: 0,
      judgements_unreviewed: 0,
      manual_adjustments_pending: 0,
      reconciliations_unsigned: 0,
      unmapped_products: 0,
    },
    close_run: null,
    row_version: 3,
  };
}

const SEPTEMBER = ["2026-09-01", "2026-09-30"] as const;
/** The first and the last day of December 2025 (the month's length from `lib/format`). */
const DECEMBER_2025 = ["2025-12-01", `2025-12-${String(daysInMonth(2025, 12))}`] as const;
const [US, UK, DE, JP] = ENTITIES as readonly [Entity, Entity, Entity, Entity];
/** WLD-P-05: the April calendar's September 2026 is FY2027-P06, and its FY2026-P09 is December 2025. */
const CALENDARS: Readonly<Record<string, readonly Period[]>> = {
  "AVM-US": [periodOf(US, "FY2026-P09", SEPTEMBER, "open")],
  "AVM-UK": [periodOf(UK, "FY2026-P09", SEPTEMBER, "open")],
  "AVM-DE": [periodOf(DE, "FY2026-P09", SEPTEMBER, "closing")],
  "AVM-JP": [
    periodOf(JP, "FY2026-P09", DECEMBER_2025, "closed"),
    periodOf(JP, "FY2027-P06", SEPTEMBER, "closed"),
  ],
};

function closeRun(
  owner: Entity,
  key: string,
  number: string,
  status: CloseRunStatus,
  step: (typeof CLOSE_RUN_STEP_CODES)[number] | null,
): CloseRun {
  const at = CLOSE_RUN_STEP_CODES.indexOf(step ?? "CUTOFF");
  return {
    id: `e2a1b3c4-0000-4000-8000-0000000${number.slice(-5)}`,
    close_run_no: number,
    entity: { id: owner.id, code: owner.code, name: owner.name },
    book: "ASC606",
    period: {
      id: "1c2d3e4f-5a6b-4c7d-8e9f-000000000009",
      period_key: key,
      name: "Sep 2026",
      start_date: SEPTEMBER[0],
      end_date: SEPTEMBER[1],
    },
    status,
    current_step_code: step,
    cutoff_known_at: "2026-09-12T14:05:00Z",
    steps: CLOSE_RUN_STEP_CODES.map((code, index) => ({
      step_code: code,
      status:
        step === null
          ? "PENDING"
          : index < at
            ? "SUCCEEDED"
            : index === at
              ? status === "PENDING"
                ? "PENDING"
                : status
              : "PENDING",
      counts: {},
      started_at: null,
      finished_at: null,
      problem: null,
    })),
    counts: {},
    job: { id: JOB_ID, state: "RUNNING", progress: { done: 0, total: null } },
    journal_run_id: null,
    created_by: MARCUS_ACTOR,
    created_at: "2026-09-12T14:05:00Z",
    started_at: "2026-09-12T14:05:00Z",
    finished_at: null,
    updated_at: "2026-09-12T14:05:00Z",
    row_version: 2,
  };
}

interface World {
  /** The close runs of an entity's September period, newest first. */
  readonly runs: Record<string, CloseRun[]>;
  readonly starts: unknown[];
  /** The `status` values of each read of the runs that have not ended. */
  readonly activeReads: string[];
}

function serve(runs: Record<string, CloseRun[]> = {}): World {
  const world: World = { runs, starts: [], activeReads: [] };
  const empty = () => HttpResponse.json({ items: [], next_cursor: null });
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), empty),
    http.get(apiUrl("/api/v1/jobs"), empty),
    http.get(apiUrl("/api/v1/approvals"), empty),
    http.get(apiUrl("/api/v1/entities"), () =>
      HttpResponse.json({ items: ENTITIES, next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/books"), () => HttpResponse.json({ items: BOOKS, next_cursor: null })),
    http.get(apiUrl("/api/v1/periods"), ({ request }) => {
      const params = new URL(request.url).searchParams;
      const items =
        params.get("book") === "ASC606" ? (CALENDARS[params.get("entity") ?? ""] ?? []) : [];
      return HttpResponse.json({ items, next_cursor: null });
    }),
    http.get(apiUrl("/api/v1/close-runs"), ({ request }) => {
      const params = new URL(request.url).searchParams;
      const code = params.get("entity");
      if (code === null) {
        // The runs of the book that have not ended, in every entity.
        world.activeReads.push(params.getAll("status").join());
        const statuses = new Set(params.getAll("status"));
        const items = Object.values(world.runs)
          .flat()
          .filter((run) => statuses.has(run.status));
        return HttpResponse.json({ items, next_cursor: null });
      }
      const items = (world.runs[code] ?? []).filter(
        (run) => run.period.period_key === params.get("period"),
      );
      return HttpResponse.json({ items, next_cursor: null });
    }),
    http.get(apiUrl("/api/v1/exceptions"), ({ request }) => {
      const params = new URL(request.url).searchParams;
      // AVM-DE has two open exceptions in its September; the others none.
      const count =
        params.get("entity") === "AVM-DE" && params.get("period") === "FY2026-P09" ? "2" : "0";
      return HttpResponse.json(
        { items: [], next_cursor: null },
        { headers: { "X-Erev-Total-Count": count } },
      );
    }),
    http.get(apiUrl("/api/v1/jobs/:jobId"), () =>
      HttpResponse.json({
        id: JOB_ID,
        kind: "CLOSE_RUN",
        state: "RUNNING",
        progress: { done: 0, total: null },
        created_at: "2026-09-12T14:05:00Z",
        created_by: MARCUS_ACTOR,
        started_at: "2026-09-12T14:05:01Z",
        finished_at: null,
        problem: null,
        result: null,
      }),
    ),
    http.post(apiUrl("/api/v1/close-runs"), async ({ request }) => {
      const body = (await request.json()) as { readonly entity_code: string };
      world.starts.push(body);
      if (body.entity_code === "AVM-JP") {
        // 409 by name: the period is locked (04 §16.8).
        return problemResponse("invalid-transition", 409, "Action not available", {
          detail: JP_CLOSED,
        });
      }
      const active = world.runs[body.entity_code]?.[0];
      if (active !== undefined && (active.status === "RUNNING" || active.status === "PENDING")) {
        // 200: the run of the entity, book and period that has not ended.
        return HttpResponse.json(active);
      }
      const started = closeRun(DE, "FY2026-P09", "CLS-000035", "RUNNING", "RECOMPUTE_DIRTY");
      world.runs[body.entity_code] = [started, ...(world.runs[body.entity_code] ?? [])];
      return HttpResponse.json(
        { id: JOB_ID, kind: "CLOSE_RUN", state: "QUEUED" },
        {
          status: 202,
          headers: { Location: `/api/v1/jobs/${JOB_ID}`, "X-Erev-Close-Run-Id": started.id },
        },
      );
    }),
  );
  return world;
}

function choose(code: string) {
  const input = screen.getByRole("combobox", { name: "Entities" });
  fireEvent.change(input, { target: { value: code } });
  fireEvent.mouseDown(screen.getByRole("option", { name: new RegExp(`^${code} · `) }));
}

function rowTexts(grid: HTMLElement, code: string): Record<string, string> {
  const row = within(grid).getByTestId(`SF-05-row-${code.toLowerCase()}`);
  return Object.fromEntries(
    [...row.querySelectorAll("[data-column]")].map((cell) => [
      cell.getAttribute("data-column") ?? "",
      cell.textContent ?? "",
    ]),
  );
}

describe("SF-05:multi-entity", () => {
  it("every column of the runs grid holds its header; the six fit at 1440 px", () => {
    // DS-CMP-10, DS-AP-10 (src/test/grid-headers.ts). At 1440 px a grid as wide as the page has
    // 1,158 px beside the open rail; the columns leave a scrollbar's width of it.
    const columns = multiEntityColumns(new Set());
    expect(narrowColumns(columns)).toEqual([]);
    expect(columns.map((column) => column.header)).toEqual([
      "Entity",
      "Period",
      "Close run",
      "Status",
      "Exceptions",
      "Cockpit",
    ]);
    expect(columns.reduce((sum, column) => sum + (column.width ?? 0), 0)).toBeLessThanOrEqual(
      1158 - 14,
    );
  });

  it("starts one close run per chosen entity; each row reads its own answer", async () => {
    // AVM-UK's September run has not ended; AVM-DE has a run that failed; AVM-JP's September is locked.
    const world = serve({
      "AVM-UK": [closeRun(UK, "FY2026-P09", "CLS-000033", "RUNNING", "RELEASE_SCHEDULES")],
      "AVM-DE": [closeRun(DE, "FY2026-P09", "CLS-000032", "FAILED", "FX_REMEASUREMENT")],
    });
    renderApp(PAGE_PATH, { me: MARCUS, screenRoutes: SCREEN_ROUTES });

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Multi-entity close · Sep 2026 · ASC 606",
      }),
    ).toBeTruthy();
    expect(
      screen.getByText("Close runs start for each entity independently. No period is locked."),
    ).toBeTruthy();
    // The entity whose run has not ended is chosen when the page opens, and its row shows the run.
    const grid = await screen.findByRole("grid", { name: "Close runs" });
    expect(grid.closest('[data-testid="SF-05-grid-multi-entity"]')).not.toBeNull();
    await within(grid).findByRole("link", { name: "CLS-000033" });
    expect(world.activeReads).toEqual(["PENDING,RUNNING,BLOCKED"]);
    expect(
      within(grid)
        .getAllByRole("rowheader")
        .map((cell) => cell.textContent),
    ).toEqual(["AVM-UK"]);
    const selector = screen.getByTestId("SF-05-multi-entity-entities");
    expect(
      within(selector).getByRole("button", { name: "Remove AVM-UK · Avenmoor Ltd (Demo)" }),
    ).toBeTruthy();
    // The entities that keep the book, in code order.
    fireEvent.change(within(selector).getByRole("combobox", { name: "Entities" }), {
      target: { value: "AVM" },
    });
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual([
      "AVM-DE · Avenmoor GmbH (Demo)",
      "AVM-JP · Avenmoor Media KK (Demo)",
      "AVM-UK · Avenmoor Ltd (Demo)",
      "AVM-US · Avenmoor Inc. (Demo)",
    ]);

    choose("AVM-JP");
    choose("AVM-DE");
    // A chosen entity with a run of the period shows it before anything starts; AVM-JP has none.
    await within(grid).findByRole("link", { name: "CLS-000032" });
    expect(
      within(grid)
        .getAllByRole("rowheader")
        .map((cell) => cell.textContent),
    ).toEqual(["AVM-DE", "AVM-UK"]);
    expect(rowTexts(grid, "AVM-DE")).toMatchObject({
      period: "Sep 2026Soft close",
      run: "CLS-000032",
      status: "FailedStep 6 of 14",
      exceptions: "2",
      cockpit: "Open cockpit",
    });

    fireEvent.click(screen.getByRole("button", { name: "Start close runs" }));
    // One independent start per entity, in the order shown, each for its own calendar's period.
    await waitFor(() => {
      expect(world.starts).toEqual([
        { entity_code: "AVM-DE", book: "ASC606", period_key: "FY2026-P09" },
        { entity_code: "AVM-JP", book: "ASC606", period_key: "FY2027-P06" },
        { entity_code: "AVM-UK", book: "ASC606", period_key: "FY2026-P09" },
      ]);
    });
    // 200: the run that had not ended stays, and the page says it was not started again.
    expect(
      await screen.findByText("AVM-UK already has a running close run. It was not started again."),
    ).toBeTruthy();
    await within(grid).findByRole("link", { name: "CLS-000035" });
    expect(
      within(grid)
        .getAllByRole("rowheader")
        .map((cell) => cell.textContent),
    ).toEqual(["AVM-DE", "AVM-JP", "AVM-UK"]);
    // 202: the new run of AVM-DE.
    expect(rowTexts(grid, "AVM-DE")).toMatchObject({
      period: "Sep 2026Soft close",
      run: "CLS-000035",
      status: "RunningStep 4 of 14",
    });
    // 409: the refusal by name, in the Status cell; AVM-JP's September is its FY2027-P06.
    expect(rowTexts(grid, "AVM-JP")).toMatchObject({
      period: "Sep 2026Locked",
      run: "—No value",
      status: JP_CLOSED,
      exceptions: "0",
    });
    expect(rowTexts(grid, "AVM-UK")).toMatchObject({
      period: "Sep 2026Period open",
      run: "CLS-000033",
      status: "RunningStep 5 of 14",
    });
    // Each row opens its own entity's close run, exceptions and cockpit.
    expect(within(grid).getByRole("link", { name: "CLS-000033" }).getAttribute("href")).toBe(
      "/close/AVM-UK/ASC606/FY2026-P09/close-run?entity=AVM-UK&period=FY2026-P09&book=ASC606",
    );
    expect(
      within(grid).getByRole("link", { name: "2 open exceptions of AVM-DE" }).getAttribute("href"),
    ).toBe("/data/exceptions?entity=AVM-DE&period=FY2026-P09&f.status=in:OPEN,IN_PROGRESS");
    expect(
      within(grid).getByRole("link", { name: "Open the cockpit of AVM-JP" }).getAttribute("href"),
    ).toBe("/close/AVM-JP/ASC606/FY2027-P06?entity=AVM-JP&period=FY2027-P06&book=ASC606");
  });

  it("a start that gets no answer goes out again under the key it had, whatever the other entities answered", async () => {
    // DG-FE-05 rev 1.156 (item W-23): one press sends one start per entity. The hook keeps the key of
    // its last body alone, so the start of an entity that got no answer lost its key as soon as the
    // next entity's start went out, and a second press started that entity under a new key.
    serve();
    const keys: Record<string, (string | null)[]> = {};
    server.use(
      http.post(apiUrl("/api/v1/close-runs"), async ({ request }) => {
        const body = (await request.clone().json()) as { readonly entity_code: string };
        const sent = (keys[body.entity_code] ??= []);
        sent.push(request.headers.get("Idempotency-Key"));
        // The first start of AVM-DE gets no answer; every other request reaches the API.
        return body.entity_code === "AVM-DE" && sent.length === 1
          ? HttpResponse.error()
          : undefined;
      }),
    );
    renderApp(PAGE_PATH, { me: MARCUS, screenRoutes: SCREEN_ROUTES });
    expect(await screen.findByRole("heading", { name: "No close runs started" })).toBeTruthy();
    choose("AVM-DE");
    choose("AVM-US");
    const press = screen.getByRole("button", { name: "Start close runs" });

    fireEvent.click(press);
    expect(
      await screen.findByText(
        "The request did not reach the server. No close run was started. Try again.",
      ),
    ).toBeTruthy();
    await waitFor(() => {
      expect(keys["AVM-US"]).toHaveLength(1);
    });
    expect(keys["AVM-DE"]).toHaveLength(1);
    expect(keys["AVM-DE"]?.[0]).toMatch(/^[0-9a-f-]{36}$/);
    expect(keys["AVM-US"]?.[0]).not.toBe(keys["AVM-DE"]?.[0]);

    await waitFor(() => {
      expect(press.getAttribute("aria-busy")).toBeNull();
    });
    fireEvent.click(press);
    await waitFor(() => {
      expect(keys["AVM-DE"]).toHaveLength(2);
    });
    // The same key: had the first start reached the API, this one would be its replay.
    expect(keys["AVM-DE"]?.[1]).toBe(keys["AVM-DE"]?.[0]);
  });

  it("the period and book are the workspace's own stored context: a sandbox copy of one membership id does not open on its source's", async () => {
    // A sandbox copy keeps the ids of the rows it copies (SCREENS_B §9.7 "The open workspace").
    const source = MARCUS.memberships[0];
    if (source === undefined) {
      throw new Error("no membership");
    }
    const COPY_ID = "1c1c1c1c-1c1c-4c1c-8c1c-1c1c1c1c1c1c";
    const me: Me = {
      ...MARCUS,
      memberships: [
        source,
        {
          ...source,
          tenant: {
            ...source.tenant,
            id: COPY_ID,
            code: "sbx-avenmoor-rehearsal",
            display_name: "Avenmoor rehearsal",
            kind: "sandbox",
            source_tenant_id: source.tenant.id,
            source_known_at: "2026-09-12T18:10:00Z",
          },
        },
      ],
    };
    // What the member last chose in the SOURCE workspace: AVM-JP's FY2026-P09, December 2025.
    window.localStorage.setItem(
      contextStorageKey({ userId: MARCUS.user.id, tenantId: source.tenant.id }),
      JSON.stringify({ entity: "AVM-JP", period: "FY2026-P09", book: "ASC606" }),
    );
    serve();
    renderApp("/close/multi-entity", { me, screenRoutes: SCREEN_ROUTES });
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Multi-entity close · Dec 2025 · ASC 606",
      }),
    ).toBeTruthy();
    cleanup();

    // The copy holds no choice of its own: the defaults, the first entity's open period.
    serve();
    renderApp("/close/multi-entity", {
      me,
      session: signedInSession({
        active_tenant: {
          id: COPY_ID,
          code: "sbx-avenmoor-rehearsal",
          display_name: "Avenmoor rehearsal",
          kind: "sandbox",
        },
      }),
      screenRoutes: SCREEN_ROUTES,
    });
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Multi-entity close · Sep 2026 · ASC 606",
      }),
    ).toBeTruthy();
    window.localStorage.clear();
  });

  it("asks for an entity before it starts anything", async () => {
    const world = serve();
    renderApp(PAGE_PATH, { me: MARCUS, screenRoutes: SCREEN_ROUTES });
    // SCR-ST-03 before starting.
    expect(await screen.findByRole("heading", { name: "No close runs started" })).toBeTruthy();
    expect(
      screen.getByText(
        "Choose the entities to close for Sep 2026. Each entity's run and exceptions are recorded independently.",
      ),
    ).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "Start close runs" }));
    expect(await screen.findByText("Choose at least one entity.")).toBeTruthy();
    const input = screen.getByRole("combobox", { name: "Entities" });
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(document.activeElement).toBe(input);
    expect(world.starts).toEqual([]);
    // Choosing clears the message.
    choose("AVM-DE");
    await waitFor(() => {
      expect(screen.queryByText("Choose at least one entity.")).toBeNull();
    });
  });

  it("a chosen entity shows its newest run of the period; removing one is announced", async () => {
    serve({
      "AVM-UK": [closeRun(UK, "FY2026-P09", "CLS-000033", "SUCCEEDED", null)],
      "AVM-DE": [closeRun(DE, "FY2026-P09", "CLS-000032", "PENDING", null)],
    });
    renderApp(PAGE_PATH, { me: MARCUS, screenRoutes: SCREEN_ROUTES });
    // AVM-DE's run is queued, so AVM-DE is chosen; AVM-UK's has ended.
    const grid = await screen.findByRole("grid", { name: "Close runs" });
    await within(grid).findByRole("link", { name: "CLS-000032" });
    expect(rowTexts(grid, "AVM-DE")).toMatchObject({ run: "CLS-000032", status: "Queued" });
    expect(within(grid).queryByTestId("SF-05-row-avm-uk")).toBeNull();

    choose("AVM-UK");
    await within(grid).findByRole("link", { name: "CLS-000033" });
    expect(rowTexts(grid, "AVM-UK")).toMatchObject({ run: "CLS-000033", status: "Succeeded" });

    fireEvent.click(screen.getByRole("button", { name: "Remove AVM-UK · Avenmoor Ltd (Demo)" }));
    expect(await screen.findByText("Removed AVM-UK")).toBeTruthy();
    await waitFor(() => {
      expect(
        within(grid)
          .getAllByRole("rowheader")
          .map((cell) => cell.textContent),
      ).toEqual(["AVM-DE"]);
    });
  });

  it("without period.close the page says what is missing", async () => {
    serve();
    renderApp(PAGE_PATH, { me: ROBERT, screenRoutes: SCREEN_ROUTES });
    // SCR-PERM-01 (RT-27).
    expect(
      await screen.findByRole("heading", {
        name: "You do not have access to the multi-entity close",
      }),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Ask a workspace administrator for a role that includes running the period close.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Start close runs" })).toBeNull();
  });

  it("a legacy context names the book whose close it follows and starts nothing", async () => {
    // SCREENS_B §1.5 rev 1.42 (04 §16.8 rev 1.155, API-S-Period `follows`; supervisor rulings
    // R-112 (e) and R-114 (d)): the LEGACY book has no close of its own, so the page chosen in its
    // context offers no entity and no start — the line of the cockpit, and the way to the same page
    // in the book it follows.
    const world = serve();
    const keeper = entity(1, "AVM-US", "Avenmoor Inc. (Demo)", ["ASC606", "LEGACY"]);
    const september: Period = {
      ...periodOf(keeper, "FY2026-P09", SEPTEMBER, "open"),
      book: "LEGACY",
      follows: { book_code: "ASC606", state: "closing" },
    };
    server.use(
      http.get(apiUrl("/api/v1/entities"), () =>
        HttpResponse.json({ items: [keeper, ...ENTITIES.slice(1)], next_cursor: null }),
      ),
      http.get(apiUrl("/api/v1/periods"), ({ request }) => {
        const params = new URL(request.url).searchParams;
        const items =
          params.get("book") === "LEGACY" && params.get("entity") === "AVM-US" ? [september] : [];
        return HttpResponse.json({ items, next_cursor: null });
      }),
    );
    renderApp("/close/multi-entity?entity=AVM-US&period=FY2026-P09&book=LEGACY", {
      me: MARCUS,
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Multi-entity close · Sep 2026 · Legacy",
      }),
    ).toBeTruthy();
    const line = screen.getByTestId("SF-05-follows");
    expect(line.textContent).toContain("The legacy book follows the close of ASC 606.");
    expect(line.textContent).toContain("Sep 2026 in ASC 606:");
    expect(within(line).getByText("Soft close")).toBeTruthy();
    expect(
      within(line)
        .getByRole("link", { name: "Close several entities in ASC 606" })
        .getAttribute("href"),
    ).toBe("/close/multi-entity?entity=AVM-US&period=FY2026-P09&book=ASC606");
    expect(screen.queryByRole("combobox", { name: "Entities" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Start close runs" })).toBeNull();
    // Nothing of a close was read or sent for the book.
    expect(world.activeReads).toEqual([]);
    expect(world.starts).toEqual([]);
  });
});
