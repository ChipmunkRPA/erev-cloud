// @vitest-environment jsdom
// SF-19:detail (SCREENS_B §10.3 rev 1.20; RT-53; J-20.2 → J-20.3): the Data frame and the five-step
// stepper; `/data/migrations/:id` opens the step of the status; the Mapping step confirms through the
// rev 1.20 inputs; the Import step shows "Cutover <date> · <n> entities · <n> contracts" and "Run import"
// posts `/import` with the confirmation; a refused import (422) comes back to the mapping step with every
// finding by name; unbuilt steps are not navigable and show no region; `migration.run` gates the page.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import type { Calendar } from "../../lib/api/queries/calendars";
import type { Migration } from "../../lib/api/queries/migrations";
import type { RegistryParameter } from "../../lib/api/queries/policies";
import type { Entity } from "../../lib/api/queries/tenant";
import { accessDescription } from "../../test/access";
import { installMemoryStorage, preloadScreens, renderApp, signedInMe } from "../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";

installMswServer();
installMemoryStorage();

beforeAll(() => preloadScreens(SCREEN_ROUTES, ["SF-19:detail"]));

afterEach(() => {
  cleanup();
});

const MAYA = signedInMe({ permissions: ["contract.read", "migration.run"] });
const READER = signedInMe({ permissions: ["contract.read"] });

const MIGRATION_ID = "0f0f0f0f-0f0f-4f0f-8f0f-0f0f0f0f0f0f";
const JOB_ID = "1a1a1a1a-1a1a-4a1a-8a1a-1a1a1a1a1a1a";
const FILE_ID = "2b2b2b2b-2b2b-4b2b-8b2b-2b2b2b2b2b2b";

const MONTHLY: Calendar = {
  id: "ca1ca1ca-ca1c-4ca1-8ca1-ca1ca1ca1ca1",
  code: "MONTHLY",
  name: "Monthly, fiscal year starts January",
  pattern: "MONTHLY",
  fiscal_year_start_month: 1,
  week_end_day: null,
  year_end_anchor: null,
  row_version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const PEMBREY = {
  id: "e1e1e1e1-e1e1-4e1e-8e1e-e1e1e1e1e1e1",
  code: "Mock Entity 1",
  name: "Mock Entity 1",
  functional_currency: "USD",
  calendar_id: MONTHLY.id,
  time_zone: "America/New_York",
  is_active: true,
  country_code: null,
  tax_id: null,
  parent_entity_id: null,
  books: [],
  row_version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
} as unknown as Entity;

function parameter(code: string, literals: readonly string[]): RegistryParameter {
  return {
    code,
    pol_id: code === "migration.nondistinct_mapping" ? "POL-211" : "POL-212",
    category: "ACCOUNTING_POLICY",
    section: "1.13",
    description: code,
    value_schema: { type: "string", enum: [...literals] },
    allowed_levels: ["TENANT"],
    approval_code: "OVR",
    pin: "K",
    source_ref: "POLICIES",
    legacy_parity_value: literals[0],
  } as unknown as RegistryParameter;
}
const PARAMETERS = [
  parameter("migration.nondistinct_mapping", ["SINGLE_POB", "SERIES", "REVIEW_QUEUE"]),
  parameter("migration.material_right_convention", [
    "CONVERT_TO_OPTION_RECORD",
    "KEEP_QUANTITY_CONVENTION",
  ]),
];

function migration(overrides: Partial<Migration> = {}): Migration {
  return {
    id: MIGRATION_ID,
    migration_no: "MIG-000001",
    mode: "OPENING_BALANCES",
    status: "PROFILED",
    source_file_id: FILE_ID,
    source_sha256: "1f09c2aa000000000000000000000000000000000000000000000000000009ce2",
    cutover_date: null,
    import_upload_ids: [],
    job_id: null,
    problem: null,
    profile: {
      source_sha256: "1f09c2aa000000000000000000000000000000000000000000000000000009ce2",
      tables: { Contract_Live: 24, SKU_SSP: 7 },
      contract_live_rows: 24,
      contracts: 4,
      legacy_pob_rows: 16,
      sku_ssp_rows: 7,
      ssp_versions: ["2023-01-01"],
      version_tokens: [],
      selling_entities: ["Mock Entity 1", "Mock Entity 2"],
      latest_current_period: "2023-01-31",
    },
    registry_version_id: null,
    reconciliation_report_run_id: null,
    approval_request_id: null,
    sandbox_tenant_id: null,
    unexplained_count: null,
    row_version: 1,
    created_by: { id: "u1", display_name: "Maya Chen", kind: "USER" },
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    started_at: null,
    finished_at: null,
    ...overrides,
  } as unknown as Migration;
}

type FieldMappingAnswer = "ok" | "http500" | "malformed";

interface Served {
  readonly bodies: unknown[];
  current: Migration;
  fieldMapping: FieldMappingAnswer;
  fieldMappingCalls: number;
  /** When set, the field-mapping handler waits for it before answering (chronology witnesses). */
  fieldMappingHold: Promise<void> | null;
}

function serve(initial: Migration, importAnswer: "accepted" | "refused" = "accepted"): Served {
  const served: Served = {
    bodies: [],
    current: initial,
    fieldMapping: "ok",
    fieldMappingCalls: 0,
    fieldMappingHold: null,
  };
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/periods"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/saved-views"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl(`/api/v1/migrations/${MIGRATION_ID}`), () => HttpResponse.json(served.current)),
    http.get(apiUrl(`/api/v1/files/${FILE_ID}`), () =>
      HttpResponse.json({
        id: FILE_ID,
        original_filename: "ASC606-shipped-step04.db",
        media_type: "application/octet-stream",
        size_bytes: 1024,
        purpose: "MIGRATION_SOURCE",
        created_at: "2026-01-01T00:00:00Z",
        created_by: null,
        created_by_kind: "USER",
        legal_hold: false,
        retention_until: null,
        shredded_at: null,
        shred_completed_at: null,
      }),
    ),
    http.get(apiUrl("/api/v1/calendars"), () =>
      HttpResponse.json({ items: [MONTHLY], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), () =>
      HttpResponse.json({ items: [PEMBREY], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/registry/parameters"), () =>
      HttpResponse.json({ items: PARAMETERS, next_cursor: null }),
    ),
    // Synthetic legacy column names (REQ-UX-010): the real rows are API data. The answer is switchable
    // so a test can drive loading → failed after the page has loaded, then Retry → rows.
    http.get(apiUrl("/api/v1/migrations/field-mapping"), async () => {
      served.fieldMappingCalls += 1;
      if (served.fieldMappingHold !== null) {
        await served.fieldMappingHold;
      }
      if (served.fieldMapping === "http500") {
        return problemResponse(null, 500, "Internal Server Error");
      }
      if (served.fieldMapping === "malformed") {
        return HttpResponse.json({ rows: "not-a-list" });
      }
      return HttpResponse.json({
        rows: [
          {
            id: "LM-CL-01",
            legacy_column: "Legacy column 1",
            target: "contract.external_id",
            rule: "Exact text.",
          },
        ],
      });
    }),
    http.get(apiUrl(`/api/v1/jobs/${JOB_ID}`), () =>
      HttpResponse.json({
        id: JOB_ID,
        kind: "MIGRATION_IMPORT",
        state: "RUNNING",
        progress: { done: 1, total: 4 },
        started_at: "2026-01-01T00:00:10Z",
        finished_at: null,
        problem: null,
        subject_type: "migration",
        subject_id: MIGRATION_ID,
        created_at: "2026-01-01T00:00:00Z",
      }),
    ),
    http.post(apiUrl(`/api/v1/migrations/${MIGRATION_ID}/import`), async ({ request }) => {
      served.bodies.push(await request.json());
      if (importAnswer === "refused") {
        return problemResponse("validation-failed", 422, "Validation failed", {
          errors: [
            {
              field: "entity_mapping[1].time_zone",
              rule_id: "LM-CL-09",
              message: "Choose a time zone for Mock Entity 2.",
            },
          ],
        });
      }
      served.current = migration({
        status: "IMPORTING",
        job_id: JOB_ID,
        cutover_date: "2023-01-31",
      });
      return HttpResponse.json(
        {
          id: JOB_ID,
          kind: "MIGRATION_IMPORT",
          state: "QUEUED",
          progress: { done: 0, total: null },
        },
        { status: 202, headers: { Location: `/api/v1/jobs/${JOB_ID}` } },
      );
    }),
  );
  return served;
}

/** The alert whose text includes `text` (the shell keeps its own, empty alert live region). */
async function findAlertWith(text: string): Promise<HTMLElement> {
  let found: HTMLElement | undefined;
  await waitFor(() => {
    found = screen.getAllByRole("alert").find((node) => within(node).queryByText(text) !== null);
    expect(found).toBeTruthy();
  });
  if (found === undefined) {
    throw new Error(`no alert with ${text}`);
  }
  return found;
}

async function confirmMapping() {
  // The only calendar defaults; the time zone is chosen in "Entity defaults".
  const group = await screen.findByRole("group", { name: "Entity defaults" });
  const zone = within(group).getByRole("combobox", { name: /^Time zone/ });
  fireEvent.change(zone, { target: { value: "Europe/London" } });
  fireEvent.mouseDown(await screen.findByRole("option", { name: "Europe/London" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm mapping" }));
}

describe("SF-19:detail (SCREENS_B §10.3 rev 1.20)", () => {
  it("opens a PROFILED migration on the Mapping step with the frame, the meta and the stepper", async () => {
    serve(migration());
    const { router } = renderApp(`/data/migrations/${MIGRATION_ID}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    expect(
      await screen.findByRole("heading", { level: 1, name: "Migration MIG-000001" }),
    ).toBeTruthy();
    await waitFor(() => {
      expect(router.state.location.search).toBe("?step=mapping");
    });
    expect(await screen.findByText("ASC606-shipped-step04.db")).toBeTruthy();
    expect(screen.getByText("Opening balances")).toBeTruthy();
    expect(screen.getByText("Run by Maya Chen")).toBeTruthy();
    const stepper = within(screen.getByTestId("SF-19-stepper")).getByRole("navigation", {
      name: "Migration steps",
    });
    const items = within(stepper)
      .getAllByRole("listitem")
      .map((item) => item.textContent ?? "");
    expect(items).toHaveLength(5);
    expect(items[0]).toContain("Profile");
    expect(items[0]).toContain("24 rows");
    expect(items[1]).toContain("Mapping");
    expect(items[4]).toContain("not submitted");
    // Unbuilt steps are not links.
    expect(within(stepper).queryByRole("link", { name: /Profile/ })).toBeNull();
    expect(within(stepper).queryByRole("link", { name: /Reconciliation/ })).toBeNull();
    expect(within(stepper).queryByRole("link", { name: /Promotion/ })).toBeNull();
    expect(await screen.findByTestId("SF-19-step-mapping")).toBeTruthy();
    // The read-only Field mapping table renders the API rows verbatim (SCREENS_B 1.22 hook).
    const mapping = await screen.findByTestId("SF-19-grid-field-mapping");
    expect(within(mapping).getByText("Legacy column 1")).toBeTruthy();
    // POL-211 / POL-212 options come from the registry catalogue.
    expect(
      screen.getByRole("combobox", { name: /^migration\.nondistinct_mapping/ }).textContent,
    ).toContain("SINGLE_POB");
  });

  it("confirms the mapping, shows the import summary, and Run import posts /import with the confirmation", async () => {
    const served = serve(migration());
    const { router } = renderApp(`/data/migrations/${MIGRATION_ID}?step=mapping`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    await screen.findByTestId("SF-19-step-mapping");
    await confirmMapping();
    await waitFor(() => {
      expect(router.state.location.search).toBe("?step=import");
    });
    expect((await screen.findByTestId("SF-19-import-summary")).textContent).toBe(
      "Cutover 31 Jan 2023 · 2 entities · 4 contracts",
    );
    fireEvent.click(screen.getByRole("button", { name: "Run import" }));
    await waitFor(() => {
      expect(served.bodies).toHaveLength(1);
    });
    expect(served.bodies[0]).toEqual({
      mode: "OPENING_BALANCES",
      cutover_date: "2023-01-31",
      entity_mapping: [
        { legacy_name: "Mock Entity 1", entity_code: "Mock Entity 1" },
        { legacy_name: "Mock Entity 2", entity_code: "Mock Entity 2" },
      ],
      entity_defaults: { time_zone: "Europe/London" },
      batch_parameters: {
        "migration.nondistinct_mapping": "SINGLE_POB",
        "migration.material_right_convention": "KEEP_QUANTITY_CONVENTION",
      },
      create_missing_entities: true,
      create_missing_products: true,
    });
    // The accepted job shows as the DS-CMP-24 indicator of the import step.
    // The progress label is the job region's name (F-LMG confirmation (3)); no unit noun is hardcoded.
    const region = await screen.findByRole("region", {
      name: "Importing legacy database MIG-000001",
    });
    expect(
      within(region).getByRole("progressbar", { name: "Importing legacy database MIG-000001" }),
    ).toBeTruthy();
    expect(within(region).queryByText(/contracts/)).toBeNull();
  });

  it("brings a refused import back to the mapping step with the finding by name", async () => {
    serve(migration(), "refused");
    const { router } = renderApp(`/data/migrations/${MIGRATION_ID}?step=mapping`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    await screen.findByTestId("SF-19-step-mapping");
    await confirmMapping();
    await screen.findByTestId("SF-19-import-summary");
    fireEvent.click(screen.getByRole("button", { name: "Run import" }));
    await waitFor(() => {
      expect(router.state.location.search).toBe("?step=mapping");
    });
    const table = await screen.findByTestId("SF-19-grid-entity-mapping");
    expect(await within(table).findByText("Choose a time zone for Mock Entity 2.")).toBeTruthy();
    expect(
      within(screen.getByTestId("SF-19-banner-import-refused")).getByText("Validation failed"),
    ).toBeTruthy();
  });

  it("binds the confirmation to its migration (Codex 1546 R2): a cached second migration needs its own", async () => {
    const OTHER_ID = "9e9e9e9e-9e9e-4e9e-8e9e-9e9e9e9e9e9e";
    const other = migration({
      id: OTHER_ID,
      migration_no: "MIG-000002",
      profile: {
        ...(migration().profile ?? {}),
        contracts: 6,
        selling_entities: ["Mock Entity 1", "Mock Entity 3", "Mock Entity 4"],
      },
    } as Partial<Migration>);
    const served = serve(migration());
    const otherBodies: unknown[] = [];
    server.use(
      http.get(apiUrl(`/api/v1/migrations/${OTHER_ID}`), () => HttpResponse.json(other)),
      http.post(apiUrl(`/api/v1/migrations/${OTHER_ID}/import`), async ({ request }) => {
        otherBodies.push(await request.json());
        return HttpResponse.json(
          {
            id: JOB_ID,
            kind: "MIGRATION_IMPORT",
            state: "QUEUED",
            progress: { done: 0, total: null },
          },
          { status: 202, headers: { Location: `/api/v1/jobs/${JOB_ID}` } },
        );
      }),
    );
    // B is visited first so that its read is CACHED; A is then confirmed; the page moves back to B
    // without a reload and without a loading frame — the step page must not carry A's confirmation.
    const { router } = renderApp(`/data/migrations/${OTHER_ID}?step=mapping`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    expect(
      await screen.findByRole("heading", { level: 1, name: "Migration MIG-000002" }),
    ).toBeTruthy();
    await screen.findByTestId("SF-19-step-mapping");
    await router.navigate(`/data/migrations/${MIGRATION_ID}?step=mapping`);
    expect(
      await screen.findByRole("heading", { level: 1, name: "Migration MIG-000001" }),
    ).toBeTruthy();
    await screen.findByTestId("SF-19-step-mapping");
    await confirmMapping();
    expect((await screen.findByTestId("SF-19-import-summary")).textContent).toBe(
      "Cutover 31 Jan 2023 · 2 entities · 4 contracts",
    );
    await router.navigate(`/data/migrations/${OTHER_ID}?step=import`);
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/data/migrations/${OTHER_ID}`);
      expect(router.state.location.search).toBe("?step=mapping");
    });
    expect(screen.queryByTestId("SF-19-import-summary")).toBeNull();
    expect(
      await screen.findByRole("heading", { level: 1, name: "Migration MIG-000002" }),
    ).toBeTruthy();
    const table = await screen.findByTestId("SF-19-grid-entity-mapping");
    await waitFor(() => {
      expect(within(table).getAllByRole("row").slice(1)).toHaveLength(3);
    });
    expect(within(table).getByText("Mock Entity 4")).toBeTruthy();
    await confirmMapping();
    expect((await screen.findByTestId("SF-19-import-summary")).textContent).toBe(
      "Cutover 31 Jan 2023 · 3 entities · 6 contracts",
    );
    fireEvent.click(screen.getByRole("button", { name: "Run import" }));
    await waitFor(() => {
      expect(otherBodies).toHaveLength(1);
    });
    expect(served.bodies).toHaveLength(0);
    expect((otherBodies[0] as { entity_mapping: unknown[] }).entity_mapping).toEqual([
      { legacy_name: "Mock Entity 1", entity_code: "Mock Entity 1" },
      { legacy_name: "Mock Entity 3", entity_code: "Mock Entity 3" },
      { legacy_name: "Mock Entity 4", entity_code: "Mock Entity 4" },
    ]);
  });

  it("opens a FAILED batch without a profile on the Profile step with the profiling SCR-ST-12 banner", async () => {
    serve(
      migration({
        status: "FAILED",
        profile: null,
        problem: { title: "Profiling failed", detail: "Contract_Live is missing.", status: 422 },
      } as Partial<Migration>),
    );
    const { router } = renderApp(`/data/migrations/${MIGRATION_ID}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    await waitFor(() => {
      expect(router.state.location.search).toBe("?step=profile");
    });
    const region = await screen.findByTestId("SF-19-step-profile");
    expect(
      await within(region).findByText(
        "Profiling ASC606-shipped-step04.db failed. Nothing was committed.",
      ),
    ).toBeTruthy();
    expect(within(region).getByText("Contract_Live is missing.")).toBeTruthy();
    expect(screen.queryByTestId("SF-19-step-mapping")).toBeNull();
    expect(screen.queryByTestId("SF-19-step-import")).toBeNull();
  });

  it("opens a FAILED batch with a profile on the Import step with the import SCR-ST-12 banner", async () => {
    serve(migration({ status: "FAILED", job_id: null } as Partial<Migration>));
    const { router } = renderApp(`/data/migrations/${MIGRATION_ID}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    await waitFor(() => {
      expect(router.state.location.search).toBe("?step=import");
    });
    const region = await screen.findByTestId("SF-19-step-import");
    expect(
      within(region).getByText(
        "Importing legacy database MIG-000001 failed. Nothing was committed.",
      ),
    ).toBeTruthy();
    expect(screen.queryByTestId("SF-19-step-profile")).toBeNull();
  });

  it("announces a Field mapping read that fails AFTER the form has loaded as an alert, keeps the form usable, and Retry recovers (Codex 1954 / 2018)", async () => {
    const served = serve(migration());
    served.fieldMapping = "http500";
    // Hold the failure: the page starts its reads in parallel, so the chronology is proved by asserting
    // the mounted form while the field-mapping read is still pending, then releasing the failure.
    let release: () => void = () => undefined;
    served.fieldMappingHold = new Promise<void>((resolve) => {
      release = resolve;
    });
    renderApp(`/data/migrations/${MIGRATION_ID}?step=mapping`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    // The page and the Entity mapping form are loaded while the table's read is still pending: no
    // alert with the failure text, no table. The hold is released in `finally` so a failing assertion
    // here never leaves the handler pending (Codex 2052).
    let form: HTMLElement;
    try {
      form = await screen.findByTestId("SF-19-grid-entity-mapping");
      await waitFor(() => {
        expect(served.fieldMappingCalls).toBe(1);
      });
      expect(
        screen
          .getAllByRole("alert")
          .some((node) => within(node).queryByText("Could not load the field mapping") !== null),
      ).toBe(false);
      expect(screen.queryByTestId("SF-19-grid-field-mapping")).toBeNull();
    } finally {
      // Release the failure: the alert is inserted after the form loaded, into the same mounted form.
      release();
    }
    const alert = await findAlertWith("Could not load the field mapping");
    expect(within(alert).getByText("Internal Server Error")).toBeTruthy();
    expect(screen.getByTestId("SF-19-grid-entity-mapping")).toBe(form);
    expect(screen.queryByTestId("SF-19-grid-field-mapping")).toBeNull();
    // The form stays usable: Confirm mapping is still refused only by its own rule (no time zone).
    fireEvent.click(screen.getByRole("button", { name: "Confirm mapping" }));
    expect(screen.getAllByText("Choose a time zone for Mock Entity 2.").length).toBeGreaterThan(0);
    // Retry re-queries; the rows render once the read succeeds.
    served.fieldMapping = "ok";
    served.fieldMappingHold = null;
    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    const table = await screen.findByTestId("SF-19-grid-field-mapping");
    expect(within(table).getByText("Legacy column 1")).toBeTruthy();
    expect(served.fieldMappingCalls).toBe(2);
  });

  it("treats a malformed Field mapping body as a failed read, by name", async () => {
    const served = serve(migration());
    served.fieldMapping = "malformed";
    renderApp(`/data/migrations/${MIGRATION_ID}?step=mapping`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    const alert = await findAlertWith("Could not load the field mapping");
    expect(
      within(alert).getByText(
        "Unexpected field-mapping body from /api/v1/migrations/field-mapping",
      ),
    ).toBeTruthy();
    expect(screen.queryByTestId("SF-19-grid-field-mapping")).toBeNull();
  });

  it("shows the frame and the stepper but no region for a step that is not built", async () => {
    serve(migration());
    renderApp(`/data/migrations/${MIGRATION_ID}?step=profile`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    expect(await screen.findByTestId("SF-19-stepper")).toBeTruthy();
    expect(screen.queryByTestId("SF-19-step-mapping")).toBeNull();
    expect(screen.queryByTestId("SF-19-step-import")).toBeNull();
    expect(screen.queryByTestId("SF-19-step-profile")).toBeNull();
  });

  it("redirects the import step to the mapping step when nothing was confirmed on this visit", async () => {
    serve(migration());
    const { router } = renderApp(`/data/migrations/${MIGRATION_ID}?step=import`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    await waitFor(() => {
      expect(router.state.location.search).toBe("?step=mapping");
    });
  });

  // The description named the words of contract.read, "viewing contracts", to a member who holds it
  // and lacks migration.run (W-12e, found on the way).
  it("limits access without migration.run (SCR-PERM-01)", async () => {
    serve(migration());
    renderApp(`/data/migrations/${MIGRATION_ID}?step=mapping`, {
      me: READER,
      screenRoutes: SCREEN_ROUTES,
    });
    expect(
      await screen.findByRole("heading", { name: "You do not have access to migrations" }),
    ).toBeTruthy();
    expect(accessDescription()).toBe(
      "Ask a workspace administrator for a role that includes running migrations (migration.run).",
    );
    expect(screen.queryByTestId("SF-19-stepper")).toBeNull();
  });

  // W-12e (SCREENS §0.6 SCR-PERM-02 (c); 04 API-R-48 as of 716e90ea): a legacy migration is the
  // workspace's, and every route of it asks migration.run for all entities. A holder for one entity
  // was shown the frame and "Could not load the migration".
  it("migration.run for one entity alone: the page says that migrations cover every entity, and no read of the migration is sent", async () => {
    const asked: string[] = [];
    serve(migration());
    server.use(
      http.get(apiUrl("/api/v1/*"), ({ request }) => {
        asked.push(new URL(request.url).pathname);
      }),
    );
    renderApp(`/data/migrations/${MIGRATION_ID}?step=mapping`, {
      me: signedInMe({
        permissions: ["contract.read", "migration.run"],
        permission_scopes: {
          "contract.read": "*",
          "migration.run": ["0a1b2c3d-4e5f-4a6b-8c7d-0000000000de"],
        },
      }),
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("heading", { name: "You do not have access to migrations" }),
    ).toBeTruthy();
    expect(accessDescription()).toBe(
      "Migrations cover every entity of the workspace. Ask a workspace administrator for a role that includes running migrations (migration.run) for all entities.",
    );
    expect(screen.queryByTestId("SF-19-stepper")).toBeNull();
    await waitFor(() => {
      expect(asked).toContain("/api/v1/entities");
    });
    expect(asked.filter((path) => path.startsWith("/api/v1/migrations"))).toEqual([]);
  });
});
