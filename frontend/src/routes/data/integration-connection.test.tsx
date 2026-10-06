// @vitest-environment jsdom
// SF-16, SF-16:connection and SF-16:sync-run (BUILD_SPEC DIN-18; SCREENS §14.1 to §14.9, §0.3 SCR-IA-02,
// §0.6 SCR-PERM-01, SCR-PERM-03, SCR-PERM-05, §0.7 SCR-ST-07; 04 API-R-45, §16.14): a test result is
// inserted as a status when the connection answered and as an alert when it did not; "Run sync" queues
// the run, shows its job and ends with the run's own result; a disabled connection says why it cannot
// sync; the list names mock adapters and shows the newest run's result; "Add connection" sends the
// reference name of the credential, never a secret, and the name is one of the workspace's own namespace
// of the secret store (T-INT-01 rev 1.108): the namespace stands before the field, the field holds the
// rest, and the API's refusal is shown on the field; the sync run page shows the control totals and the
// run's one result.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { registerCurrencies } from "../../lib/format";
import {
  type Connection,
  controlTotals,
  isMock,
  requestableKinds,
  type SyncRun,
} from "../../lib/api/queries/integrations";
import {
  installMemoryStorage,
  preloadScreens,
  renderApp,
  signedInMe,
  signedInSession,
} from "../../test/app";
import { narrowColumns } from "../../test/grid-headers";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import {
  describedBy,
  RECORD_CHANGED,
  REFUSAL_REFERENCE,
  REFUSAL_TITLE,
  refusedWith,
} from "../../test/refusals";
import { externalIdColumns, syncRunColumns, totalsText } from "./integration-connection";
import { connectionColumns, entitiesText } from "./integrations";

installMswServer();
installMemoryStorage();
installGridViewport();

beforeAll(async () => {
  registerCurrencies([{ code: "USD", minor_unit: 2 }]);
  await preloadScreens(SCREEN_ROUTES, ["SF-16", "SF-16:connection", "SF-16:sync-run"]);
});

afterEach(() => {
  cleanup();
});

const NIKHIL = signedInMe({
  permissions: ["contract.read", "config.read", "integration.manage", "audit.read"],
});
const SALESFORCE_ID = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d";
const NETSUITE_ID = "2b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const RUN_ID = "3c4d5e6f-7a8b-4c9d-8e0f-2a3b4c5d6e7f";
const OLDER_RUN_ID = "4d5e6f7a-8b9c-4d0e-9f1a-3b4c5d6e7f8a";
const JOB_ID = "5e6f7a8b-9c0d-4e1f-8a2b-4c5d6e7f8a9b";
const AVM_US = "0a1b2c3d-4e5f-4a6b-8c7d-000000000001";
const AVM_UK = "0a1b2c3d-4e5f-4a6b-8c7d-000000000002";
/** 04 T-INT-01 rev 1.108: `tenant-<tenant id>-`, the workspace of the signed-in session. */
const NAMESPACE = `tenant-${NIKHIL.memberships[0]?.tenant.id ?? ""}-`;
const SALESFORCE_SECRET = `${NAMESPACE}salesforce-client@3`;
/** A mock connection's base URL in a running stack: the API's own origin, then the mock router's path. */
const SALESFORCE_MOCK = "http://127.0.0.1:8190/api/v1/__mocks__/salesforce";
const NETSUITE_MOCK = "http://127.0.0.1:8190/api/v1/__mocks__/netsuite";

function connection(overrides: Partial<Connection> = {}): Connection {
  return {
    id: SALESFORCE_ID,
    code: "salesforce-orders",
    name: "Salesforce orders",
    adapter: "SALESFORCE",
    direction: "INBOUND",
    entity_ids: [],
    base_url: SALESFORCE_MOCK,
    config: { api_version: "v60.0" },
    secret_ref: SALESFORCE_SECRET,
    status: "ACTIVE",
    checkpoint: {},
    last_test_at: null,
    last_test_result: null,
    last_test_detail: null,
    last_sync_run: null,
    created_at: "2026-09-01T08:00:00Z",
    updated_at: "2026-09-12T09:00:00Z",
    row_version: 3,
    ...overrides,
  };
}

function syncRun(overrides: Partial<SyncRun> = {}): SyncRun {
  return {
    id: RUN_ID,
    integration_connection_id: SALESFORCE_ID,
    kind: "WEBHOOK_BATCH",
    status: "SUCCEEDED",
    job_id: JOB_ID,
    record_count: 1,
    exception_count: 0,
    source_totals: { count: 1, amount_by_currency: { USD: "120000.00" }, sha256: "a".repeat(64) },
    loaded_totals: { count: 1, amount_by_currency: { USD: "120000.00" }, sha256: "a".repeat(64) },
    checkpoint_before: { replay_id: 41 },
    checkpoint_after: { replay_id: 42 },
    problem: null,
    started_at: "2026-09-12T14:01:00Z",
    finished_at: "2026-09-12T14:01:04Z",
    duration_seconds: 4,
    created_at: "2026-09-12T14:01:00Z",
    updated_at: "2026-09-12T14:01:04Z",
    row_version: 2,
    ...overrides,
  };
}

/** API-S-Entity as the shell and the Entities cells read it. */
function entity(id: string, code: string, name: string) {
  return {
    id,
    code,
    name,
    country_code: null,
    functional_currency: "USD",
    time_zone: "UTC",
    calendar_id: "0a1b2c3d-4e5f-4a6b-8c7d-0000000000c1",
    parent_entity_id: null,
    tax_id: null,
    is_active: true,
    books: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    row_version: 1,
  };
}

function list(items: readonly unknown[], request?: Request) {
  const counting =
    request !== undefined && new URL(request.url).searchParams.get("count") === "true";
  return HttpResponse.json(
    { items, next_cursor: null },
    { headers: counting ? { "X-Erev-Total-Count": String(items.length) } : {} },
  );
}

function job(state: "QUEUED" | "SUCCEEDED") {
  return {
    id: JOB_ID,
    kind: "SYNC_RUN",
    state,
    mode: null,
    progress: { done: state === "SUCCEEDED" ? 1 : 0, total: null },
    result: null,
    problem: null,
    created_by: { id: NIKHIL.user.id, kind: "USER", display_name: NIKHIL.user.display_name },
    created_at: "2026-09-12T14:00:59Z",
    started_at: state === "QUEUED" ? null : "2026-09-12T14:01:00Z",
    finished_at: state === "SUCCEEDED" ? "2026-09-12T14:01:04Z" : null,
  };
}

interface Recorded {
  readonly method: string;
  readonly path: string;
  readonly body: unknown;
  readonly ifMatch: string | null;
  readonly idempotencyKey: string | null;
}

interface World {
  connections: Connection[];
  runs: SyncRun[];
  readonly commands: Recorded[];
  readonly runSearches: string[];
}

/** The shell's reads and the API-R-45 reads over a small world the tests change. */
function serve(world: Partial<Pick<World, "connections" | "runs">> = {}): World {
  const state: World = {
    connections: world.connections ?? [connection()],
    runs: world.runs ?? [],
    commands: [],
    runSearches: [],
  };
  const record = async (request: Request): Promise<unknown> => {
    const text = await request.text();
    const body: unknown = text === "" ? null : JSON.parse(text);
    state.commands.push({
      method: request.method,
      path: new URL(request.url).pathname,
      body,
      ifMatch: request.headers.get("If-Match"),
      idempotencyKey: request.headers.get("Idempotency-Key"),
    });
    return body;
  };
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () => list([])),
    http.get(apiUrl("/api/v1/books"), () => list([])),
    http.get(apiUrl("/api/v1/periods"), () => list([])),
    http.get(apiUrl("/api/v1/saved-views"), () => list([])),
    http.get(apiUrl("/api/v1/entities"), () =>
      list([
        entity(AVM_US, "AVM-US", "Avenmoor US Inc."),
        entity(AVM_UK, "AVM-UK", "Avenmoor UK Ltd"),
      ]),
    ),
    http.get(apiUrl("/api/v1/integrations"), ({ request }) => list(state.connections, request)),
    http.get(apiUrl("/api/v1/integrations/:id"), ({ params }) => {
      const found = state.connections.find((item) => item.id === params.id);
      return found === undefined
        ? problemResponse("not-found", 404, "Not found")
        : HttpResponse.json(found);
    }),
    http.get(apiUrl("/api/v1/sync-runs"), ({ request }) => {
      const params = new URL(request.url).searchParams;
      const search = new URLSearchParams(params);
      for (const name of ["limit", "cursor", "count"]) {
        search.delete(name);
      }
      state.runSearches.push(search.toString());
      return list(
        state.runs.filter((run) => run.integration_connection_id === params.get("connection")),
        request,
      );
    }),
    http.get(apiUrl("/api/v1/sync-runs/:id"), ({ params }) => {
      const found = state.runs.find((run) => run.id === params.id);
      return found === undefined
        ? problemResponse("not-found", 404, "Not found")
        : HttpResponse.json(found);
    }),
    http.get(apiUrl("/api/v1/external-ids"), ({ request }) => list([], request)),
    http.post(apiUrl("/api/v1/integrations"), async ({ request }) => {
      const body = (await record(request)) as Record<string, unknown>;
      const created = connection({
        ...(body as Partial<Connection>),
        id: NETSUITE_ID,
        status: "DISABLED",
        row_version: 1,
      });
      state.connections = [...state.connections, created];
      return HttpResponse.json(created, { status: 201 });
    }),
    http.patch(apiUrl("/api/v1/integrations/:id"), async ({ request, params }) => {
      const body = (await record(request)) as Partial<Connection>;
      state.connections = state.connections.map((item) =>
        item.id === params.id ? { ...item, ...body, row_version: item.row_version + 1 } : item,
      );
      return HttpResponse.json(state.connections.find((item) => item.id === params.id));
    }),
  );
  return state;
}

function open(entry: string, me = NIKHIL) {
  return renderApp(entry, { me, screenRoutes: SCREEN_ROUTES });
}

const COPY_ID = "1c1c1c1c-1c1c-4c1c-8c1c-1c1c1c1c1c1c";
/** SB-R-08: the reason line of "Add connection" in a sandbox workspace (SCREENS §14.7). */
const SANDBOX_ADD_REASON =
  "A sandbox workspace takes no inbound connection: Salesforce, Stripe and the directions Inbound and Both are not offered.";

/**
 * nikhil in a sandbox copy of the workspace. A copy keeps the ids of the rows it copies (SCREENS_B
 * §9.7 "The open workspace"): GET /me lists the source first, with the same membership id as the copy.
 */
function sandboxCopy() {
  const source = NIKHIL.memberships[0];
  if (source === undefined) {
    throw new Error("no membership");
  }
  const me = {
    ...NIKHIL,
    memberships: [
      source,
      {
        ...source,
        tenant: {
          ...source.tenant,
          id: COPY_ID,
          code: "sbx-avenmoor-rehearsal",
          display_name: "Avenmoor rehearsal",
          kind: "sandbox" as const,
          source_tenant_id: source.tenant.id,
          source_known_at: "2026-09-12T18:10:00Z",
        },
      },
    ],
  };
  const session = signedInSession({
    active_tenant: {
      id: COPY_ID,
      code: "sbx-avenmoor-rehearsal",
      display_name: "Avenmoor rehearsal",
      kind: "sandbox",
    },
  });
  return { me, session };
}

describe("SF-16:connection", () => {
  it("test result inserted as status", async () => {
    const world = serve();
    let answers = 0;
    server.use(
      http.post(apiUrl(`/api/v1/integrations/${SALESFORCE_ID}/test`), () => {
        answers += 1;
        const tested =
          answers === 1
            ? connection({
                last_test_at: "2026-09-12T09:12:30Z",
                last_test_result: "SUCCESS",
                last_test_detail: "SALESFORCE reachable; 0 change(s) visible",
                row_version: 4,
              })
            : connection({
                last_test_at: "2026-09-12T09:14:05Z",
                last_test_result: "FAILURE",
                last_test_detail: "secret reference salesforce-client@3 is not resolvable",
                row_version: 5,
              });
        world.connections = [tested];
        return HttpResponse.json(tested);
      }),
    );
    open(`/data/integrations/${SALESFORCE_ID}`);

    expect(
      await screen.findByRole("heading", { level: 1, name: "Salesforce orders" }),
    ).toBeTruthy();
    // SCREENS §14.6 "Never tested".
    expect(screen.getByText("This connection has not been tested.")).toBeTruthy();
    expect(screen.queryByTestId("SF-16-banner-test")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Test connection" }));
    const succeeded = await screen.findByText("Connection succeeded · 12 Sep 2026 09:12 UTC");
    const banner = screen.getByTestId("SF-16-banner-test");
    expect(banner.contains(succeeded)).toBe(true);
    // SCREENS §14.9: a result that has just answered is inserted as a status.
    expect(within(banner).getByRole("status")).toBeTruthy();
    expect(within(banner).queryByRole("alert")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Test connection" }));
    expect(
      await screen.findByText(
        "Connection failed · 12 Sep 2026 09:14 UTC: secret reference salesforce-client@3 is not resolvable",
      ),
    ).toBeTruthy();
    // A failure is an alert.
    expect(within(screen.getByTestId("SF-16-banner-test")).getByRole("alert")).toBeTruthy();
    expect(within(screen.getByTestId("SF-16-banner-test")).queryByRole("status")).toBeNull();
  });

  it("a result read with the page is a static banner", async () => {
    serve({
      connections: [
        connection({ last_test_at: "2026-09-12T09:12:30Z", last_test_result: "SUCCESS" }),
      ],
    });
    open(`/data/integrations/${SALESFORCE_ID}`);
    const banner = await screen.findByTestId("SF-16-banner-test");
    expect(within(banner).getByText("Connection succeeded · 12 Sep 2026 09:12 UTC")).toBeTruthy();
    expect(within(banner).queryByRole("status")).toBeNull();
    expect(within(banner).queryByRole("alert")).toBeNull();
    // The chips of the header: status, adapter and the mock marker.
    const page = screen.getByTestId("SF-16-page");
    for (const chip of ["Active", "Salesforce", "Mock"]) {
      expect(within(page).getAllByText(chip).length).toBeGreaterThan(0);
    }
  });

  it("run sync queues the run, shows the job and ends with the run's result", async () => {
    const world = serve();
    let finish: (() => void) | undefined;
    const running = new Promise<void>((resolve) => {
      finish = resolve;
    });
    server.use(
      http.post(apiUrl(`/api/v1/integrations/${SALESFORCE_ID}/sync`), async ({ request }) => {
        world.commands.push({
          method: "POST",
          path: new URL(request.url).pathname,
          body: await request.json(),
          ifMatch: null,
          idempotencyKey: request.headers.get("Idempotency-Key"),
        });
        return HttpResponse.json(job("QUEUED"), {
          status: 202,
          headers: { Location: `/api/v1/jobs/${JOB_ID}`, "X-Erev-Sync-Run-Id": RUN_ID },
        });
      }),
      http.get(apiUrl("/api/v1/jobs/:jobId"), async () => {
        await running;
        const totals = {
          count: 3,
          amount_by_currency: { USD: "120000.00" },
          sha256: "c".repeat(64),
        };
        world.runs = [
          syncRun({
            kind: "INBOUND_POLL",
            record_count: 3,
            source_totals: totals,
            loaded_totals: totals,
          }),
        ];
        return HttpResponse.json(job("SUCCEEDED"));
      }),
    );
    const { router } = open(`/data/integrations/${SALESFORCE_ID}`);
    await screen.findByRole("heading", { level: 1, name: "Salesforce orders" });

    // SCREENS §14.4: the kinds of an inbound Salesforce connection.
    fireEvent.click(screen.getByRole("button", { name: "Run sync" }));
    const menu = screen.getByRole("menu", { name: "Run sync" });
    expect(
      within(menu)
        .getAllByRole("menuitem")
        .map((item) => item.textContent),
    ).toEqual(["Inbound poll", "Reconciliation sweep"]);
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Inbound poll" }));

    // SB-R-06: the job shows in place while it runs.
    expect(
      await screen.findByRole("progressbar", { name: "Syncing Salesforce orders" }),
    ).toBeTruthy();
    expect(world.commands).toHaveLength(1);
    expect(world.commands[0]?.body).toEqual({ kind: "INBOUND_POLL" });
    expect(world.commands[0]?.idempotencyKey).toMatch(/^[0-9a-f-]{36}$/);

    finish?.();
    expect(
      await screen.findByText("Sync finished: 3 records, control totals reconciled."),
    ).toBeTruthy();
    expect(screen.queryByRole("progressbar", { name: "Syncing Salesforce orders" })).toBeNull();
    // The grid reads the runs again and shows the new one.
    const runs = await within(await screen.findByTestId("SF-16-grid-sync-runs")).findByRole(
      "grid",
      {
        name: "Sync runs",
      },
    );
    // Source and loaded totals as recorded: both sides of the run.
    expect(await within(runs).findAllByText("3 records · USD 120,000.00")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "View run" }));
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(
        `/data/integrations/${SALESFORCE_ID}/sync-runs/${RUN_ID}`,
      ),
    );
  });

  it("a control total difference ends with the warning, not with a success", async () => {
    const world = serve();
    server.use(
      http.post(apiUrl(`/api/v1/integrations/${SALESFORCE_ID}/sync`), () =>
        HttpResponse.json(job("QUEUED"), {
          status: 202,
          headers: { Location: `/api/v1/jobs/${JOB_ID}`, "X-Erev-Sync-Run-Id": RUN_ID },
        }),
      ),
      http.get(apiUrl("/api/v1/jobs/:jobId"), () => {
        world.runs = [
          syncRun({
            kind: "RECONCILIATION_SWEEP",
            status: "CONTROL_TOTAL_MISMATCH",
            exception_count: 1,
            loaded_totals: { count: 0, amount_by_currency: {}, sha256: "b".repeat(64) },
          }),
        ];
        return HttpResponse.json(job("SUCCEEDED"));
      }),
    );
    open(`/data/integrations/${SALESFORCE_ID}`);
    await screen.findByRole("heading", { level: 1, name: "Salesforce orders" });
    fireEvent.click(screen.getByRole("button", { name: "Run sync" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Reconciliation sweep" }));
    expect(
      await screen.findByText(
        "Sync finished with a control total difference. Exceptions were raised.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText(/control totals reconciled/)).toBeNull();
    // The row shows the run's own result and both sides as recorded.
    const row = await screen.findByTestId(`SF-16-row-${RUN_ID}`);
    expect(within(row).getAllByText("Difference")).toHaveLength(2);
    expect(within(row).getByText("1 record · USD 120,000.00")).toBeTruthy();
    expect(within(row).getByText("0 records")).toBeTruthy();
  });

  it("a run that recorded no totals shows no result", async () => {
    // A test asks the source one question and loads nothing: there is nothing to reconcile.
    serve({
      runs: [
        syncRun({
          id: OLDER_RUN_ID,
          kind: "TEST_CONNECTION",
          record_count: 0,
          source_totals: null,
          loaded_totals: null,
        }),
        syncRun(),
      ],
    });
    open(`/data/integrations/${SALESFORCE_ID}`);
    const tested = await screen.findByTestId(`SF-16-row-${OLDER_RUN_ID}`);
    expect(within(tested).getByText("Test connection")).toBeTruthy();
    expect(within(tested).getByText("Succeeded")).toBeTruthy();
    expect(within(tested).queryByText("Reconciled")).toBeNull();
    // A run that loaded records keeps the result its status states.
    const batch = screen.getByTestId(`SF-16-row-${RUN_ID}`);
    expect(within(batch).getByText("Webhook batch")).toBeTruthy();
    expect(within(batch).getByText("Reconciled")).toBeTruthy();
  });

  it("a disabled connection says why it cannot sync, and Enable sends the row version", async () => {
    const world = serve({ connections: [connection({ status: "DISABLED" })] });
    open(`/data/integrations/${SALESFORCE_ID}`);
    await screen.findByRole("heading", { level: 1, name: "Salesforce orders" });
    // SCR-PERM-03: the state holds the command back, with its reason.
    const sync = screen.getByRole("button", { name: "Run sync" });
    expect(sync.getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByText("Enable the connection to run a sync.")).toBeTruthy();
    expect(screen.queryByRole("menu")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Enable" }));
    expect(await screen.findByText("Enabled Salesforce orders.")).toBeTruthy();
    expect(world.commands).toEqual([
      {
        method: "PATCH",
        path: `/api/v1/integrations/${SALESFORCE_ID}`,
        body: { status: "ACTIVE" },
        ifMatch: '"r3"',
        idempotencyKey: expect.stringMatching(/^[0-9a-f-]{36}$/) as string,
      },
    ]);
    expect(await screen.findByRole("button", { name: "Disable" })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Run sync" }).getAttribute("aria-disabled"),
    ).toBeNull();
  });

  it("settings show the credential's reference name and the edit drawer sends what changed", async () => {
    const world = serve({ connections: [connection({ entity_ids: [AVM_UK] })] });
    open(`/data/integrations/${SALESFORCE_ID}?pane=settings`);
    const pane = await screen.findByTestId("SF-16-pane-settings");
    expect(NAMESPACE).toMatch(/^tenant-[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}-$/);
    // The settings show the stored reference whole.
    expect(within(pane).getByText(SALESFORCE_SECRET)).toBeTruthy();
    expect(await within(pane).findByText("AVM-UK")).toBeTruthy();
    expect(within(pane).getByText("api_version = v60.0")).toBeTruthy();

    fireEvent.click(within(pane).getByRole("button", { name: "Edit connection" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit connection" });
    // The adapter, the code and the direction are fixed once a connection exists.
    expect(within(dialog).queryByRole("combobox", { name: /^Adapter/ })).toBeNull();
    // SCREENS §14.4 (rev 1.13): the workspace's namespace is fixed text before the field, and the field
    // holds the rest of the stored reference.
    const reference = within(dialog).getByRole<HTMLInputElement>("textbox", {
      name: /^Credential reference/,
    });
    expect(reference.value).toBe("salesforce-client@3");
    const described = (reference.getAttribute("aria-describedby") ?? "").split(" ");
    const fixed = document.getElementById(described[0] ?? "");
    expect(fixed?.textContent).toBe(NAMESPACE);
    expect(fixed?.querySelector("input")).toBeNull();
    expect(
      (fixed?.compareDocumentPosition(reference) ?? 0) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    // SCREENS §14.9: the help is announced with the field.
    expect(document.getElementById(described.at(-1) ?? "")?.textContent).toBe(
      "Enter the rest of the secret's name and its version number, for example netsuite-token@3. The secret itself is never stored. Leave the field empty for a connection that sends no credential.",
    );
    expect(reference.getAttribute("aria-invalid")).toBeNull();
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Name/ }), {
      target: { value: "Salesforce orders (EU)" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save connection" }));
    expect(await screen.findByText("Saved Salesforce orders (EU).")).toBeTruthy();
    expect(world.commands).toHaveLength(1);
    expect(world.commands[0]).toMatchObject({
      method: "PATCH",
      ifMatch: '"r3"',
      body: {
        name: "Salesforce orders (EU)",
        entity_ids: [AVM_UK],
        base_url: SALESFORCE_MOCK,
        secret_ref: SALESFORCE_SECRET,
        config: { api_version: "v60.0" },
      },
    });
    expect(
      await screen.findByRole("heading", { level: 1, name: "Salesforce orders (EU)" }),
    ).toBeTruthy();
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): a message that names a member the
  // drawer has no field for was shown nowhere — the edit drawer shows no direction. What a field shows
  // is not said by the banner, and after a 412 the banner says that the record changed.
  it("the edit drawer under a refused command: the banner lists what no field shows", async () => {
    const noField = "A connection with open sync runs keeps its direction.";
    const atName = "Use a name no other connection has.";
    serve({ connections: [connection({ entity_ids: [AVM_UK] })] });
    let status = 422;
    server.use(
      http.patch(apiUrl("/api/v1/integrations/:id"), () =>
        refusedWith({ direction: noField, name: atName }, { status }),
      ),
    );
    open(`/data/integrations/${SALESFORCE_ID}?pane=settings`);
    const pane = await screen.findByTestId("SF-16-pane-settings");
    fireEvent.click(within(pane).getByRole("button", { name: "Edit connection" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit connection" });
    const name = within(dialog).getByRole("textbox", { name: /^Name/ });
    fireEvent.change(name, { target: { value: "Salesforce orders (EU)" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save connection" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + noField + REFUSAL_REFERENCE);
    expect(describedBy(name)).toContain(atName);

    status = 412;
    fireEvent.click(within(dialog).getByRole("button", { name: "Save connection" }));
    expect(await within(dialog).findByRole("heading", { name: RECORD_CHANGED })).toBeTruthy();
    expect(within(dialog).queryByRole("heading", { name: REFUSAL_TITLE })).toBeNull();
  });

  it("in a sandbox copy that holds its source's membership id the screens are the copy's: its namespace, and no Enable for a ledger adapter", async () => {
    const { me, session: inCopy } = sandboxCopy();
    const ledger = connection({
      name: "NetSuite journals",
      code: "netsuite-journals",
      adapter: "NETSUITE",
      direction: "OUTBOUND",
      base_url: NETSUITE_MOCK,
      secret_ref: null,
      status: "DISABLED",
    });

    // In the source the ledger connection can be enabled.
    serve({ connections: [ledger] });
    renderApp(`/data/integrations/${SALESFORCE_ID}`, { me, screenRoutes: SCREEN_ROUTES });
    await screen.findByRole("heading", { level: 1, name: "NetSuite journals" });
    expect(screen.getByRole("button", { name: "Enable" }).getAttribute("aria-disabled")).toBeNull();
    cleanup();

    // In the copy it cannot (SB-R-08), and the page says why.
    serve({ connections: [ledger] });
    renderApp(`/data/integrations/${SALESFORCE_ID}?pane=settings`, {
      me,
      session: inCopy,
      screenRoutes: SCREEN_ROUTES,
    });
    await screen.findByRole("heading", { level: 1, name: "NetSuite journals" });
    const enable = screen.getByRole("button", { name: "Enable" });
    expect(enable.getAttribute("aria-disabled")).toBe("true");
    expect(
      document.getElementById(enable.getAttribute("aria-describedby") ?? "")?.textContent,
    ).toBe("Sandbox workspaces cannot post or export journals.");
    // The namespace of a credential reference is the copy's own, on the connection and in the list.
    const pane = await screen.findByTestId("SF-16-pane-settings");
    fireEvent.click(within(pane).getByRole("button", { name: "Edit connection" }));
    const edit = await screen.findByRole("dialog", { name: "Edit connection" });
    expect(within(edit).getByText(`tenant-${COPY_ID}-`)).toBeTruthy();
    expect(within(edit).queryByText(NAMESPACE)).toBeNull();
    cleanup();

    serve({ connections: [] });
    renderApp("/data/integrations", { me, session: inCopy, screenRoutes: SCREEN_ROUTES });
    expect(await screen.findByRole("heading", { name: "No integrations yet" })).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "Add connection" })[0] as HTMLElement);
    const add = await screen.findByRole("dialog", { name: "Add connection" });
    expect(within(add).getByText(`tenant-${COPY_ID}-`)).toBeTruthy();
    expect(within(add).queryByText(NAMESPACE)).toBeNull();
  });

  it("in a sandbox copy Test connection is held back for an adapter that calls out, and the CSV GL export is tested", async () => {
    // 05 SBX-08 rev 1.116 (item SBX-PROBE-1): the API refuses the probe of every adapter but CSV_GL
    // in a sandbox, 403 `sandbox-restricted`; the control says so instead of offering it (SB-R-08).
    const { me, session } = sandboxCopy();
    const ledger = connection({
      name: "NetSuite journals",
      code: "netsuite-journals",
      adapter: "NETSUITE",
      direction: "OUTBOUND",
      base_url: NETSUITE_MOCK,
      secret_ref: null,
      status: "DISABLED",
    });
    let probes = 0;
    serve({ connections: [ledger] });
    server.use(
      http.post(apiUrl(`/api/v1/integrations/${SALESFORCE_ID}/test`), () => {
        probes += 1;
        return problemResponse("sandbox-restricted", 403, "Not available in a sandbox", {
          detail:
            "A connection cannot be tested in a sandbox workspace: a sandbox reaches no external system (05 SBX-08).",
        });
      }),
    );
    renderApp(`/data/integrations/${SALESFORCE_ID}`, { me, session, screenRoutes: SCREEN_ROUTES });
    await screen.findByRole("heading", { level: 1, name: "NetSuite journals" });
    const held = screen.getByRole("button", { name: "Test connection" });
    expect(held.getAttribute("aria-disabled")).toBe("true");
    expect(document.getElementById(held.getAttribute("aria-describedby") ?? "")?.textContent).toBe(
      "A connection cannot be tested in a sandbox workspace: a sandbox reaches no external system.",
    );
    fireEvent.click(held);
    expect(probes).toBe(0);
    // The state of the connection is still said: it has not been tested.
    expect(screen.getByText("This connection has not been tested.")).toBeTruthy();
    cleanup();

    // The CSV GL export is a download and calls nothing: its test stays.
    const download = connection({
      name: "CSV journals",
      code: "csv-journals",
      adapter: "CSV_GL",
      direction: "OUTBOUND",
      base_url: null,
      secret_ref: null,
      status: "DISABLED",
    });
    const world = serve({ connections: [download] });
    server.use(
      http.post(apiUrl(`/api/v1/integrations/${SALESFORCE_ID}/test`), () => {
        const tested = {
          ...download,
          last_test_at: "2026-09-12T09:12:30Z",
          last_test_result: "SUCCESS" as const,
          row_version: 4,
        };
        world.connections = [tested];
        return HttpResponse.json(tested);
      }),
    );
    renderApp(`/data/integrations/${SALESFORCE_ID}`, { me, session, screenRoutes: SCREEN_ROUTES });
    await screen.findByRole("heading", { level: 1, name: "CSV journals" });
    const offered = screen.getByRole("button", { name: "Test connection" });
    expect(offered.getAttribute("aria-disabled")).toBeNull();
    fireEvent.click(offered);
    expect(await screen.findByText("Connection succeeded · 12 Sep 2026 09:12 UTC")).toBeTruthy();
  });

  it("an unknown connection is not found", async () => {
    serve({ connections: [] });
    const { router } = open(`/data/integrations/${SALESFORCE_ID}`);
    expect(await screen.findByRole("heading", { name: "Connection not found" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Go to Integrations" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/data/integrations"));
  });
});

describe("SF-16", () => {
  it("lists the connections with the mock marker and the newest run's result", async () => {
    serve({
      connections: [
        connection({
          last_test_at: "2026-09-12T09:12:30Z",
          last_test_result: "SUCCESS",
          last_sync_run: {
            id: RUN_ID,
            status: "SUCCEEDED",
            finished_at: "2026-09-12T14:01:04Z",
            result: { record_count: 1, exception_count: 0 },
          },
        }),
        connection({
          id: NETSUITE_ID,
          code: "netsuite-gl",
          name: "NetSuite GL",
          adapter: "NETSUITE",
          direction: "BOTH",
          entity_ids: [AVM_US],
          base_url: "https://erp.example.test",
          status: "DISABLED",
          last_sync_run: {
            id: OLDER_RUN_ID,
            status: "CONTROL_TOTAL_MISMATCH",
            finished_at: "2026-09-11T10:00:00Z",
            result: { record_count: 40, exception_count: 1 },
          },
        }),
      ],
    });
    open("/data/integrations");
    const grid = await within(await screen.findByTestId("SF-16-grid-connections")).findByRole(
      "grid",
      { name: "Integrations" },
    );
    expect(screen.getByRole("heading", { level: 1, name: "Integrations" })).toBeTruthy();
    expect(await screen.findByText("2 connections")).toBeTruthy();
    // SCR-IA-02: the Integrations tab renders for a holder of integration.manage.
    expect(
      within(screen.getByRole("navigation", { name: "Data sections" }))
        .getByRole("link", { name: "Integrations" })
        .getAttribute("aria-current"),
    ).toBe("page");

    const salesforce = await screen.findByTestId("SF-16-row-salesforce-orders");
    expect(
      within(salesforce).getByRole("link", { name: "Salesforce orders" }).getAttribute("href"),
    ).toBe(`/data/integrations/${SALESFORCE_ID}`);
    expect(within(salesforce).getByText("Mock")).toBeTruthy();
    expect(within(salesforce).getByText("Inbound")).toBeTruthy();
    expect(within(salesforce).getByText("All entities")).toBeTruthy();
    expect(within(salesforce).getByText("Active")).toBeTruthy();
    expect(within(salesforce).getAllByText("Succeeded")).toHaveLength(2);
    expect(within(salesforce).getByText("Reconciled")).toBeTruthy();

    const netsuite = screen.getByTestId("SF-16-row-netsuite-gl");
    expect(within(netsuite).queryByText("Mock")).toBeNull();
    expect(within(netsuite).getByText("Both")).toBeTruthy();
    expect(await within(netsuite).findByText("AVM-US")).toBeTruthy();
    expect(within(netsuite).getByText("Disabled")).toBeTruthy();
    // The newest run ended with a control total mismatch: its chip and the result read "Difference".
    expect(within(netsuite).getAllByText("Difference")).toHaveLength(2);
    expect(within(grid).queryByText(SALESFORCE_ID)).toBeNull();
  });

  it("the Mock chip reads the path of the base URL", () => {
    // SCREENS §14.3 column 2 (rev 1.13): an address in a running stack, the bare path in process.
    expect(isMock({ base_url: SALESFORCE_MOCK })).toBe(true);
    expect(isMock({ base_url: "/api/v1/__mocks__/salesforce" })).toBe(true);
    expect(isMock({ base_url: "https://erp.example.test" })).toBe(false);
    expect(isMock({ base_url: "https://erp.example.test/proxy/api/v1/__mocks__/netsuite" })).toBe(
      false,
    );
    expect(isMock({ base_url: null })).toBe(false);
  });

  it("add connection sends the reference name and opens the new connection", async () => {
    const world = serve({ connections: [] });
    let refusals = 0;
    server.use(
      http.post(apiUrl("/api/v1/session/mfa"), () =>
        HttpResponse.json({ authenticated: true, mfa_verified_at: "2026-09-12T16:00:00Z" }),
      ),
    );
    const { router } = open("/data/integrations");
    // SCREENS §14.6 empty state.
    expect(await screen.findByRole("heading", { name: "No integrations yet" })).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "Add connection" })[0] as HTMLElement);
    const dialog = await screen.findByRole("dialog", { name: "Add connection" });

    // Saving an empty form names the missing fields and sends nothing.
    fireEvent.click(within(dialog).getByRole("button", { name: "Save connection" }));
    expect(within(dialog).getAllByText("Enter a value.").length).toBeGreaterThanOrEqual(3);
    expect(world.commands).toEqual([]);

    const adapter = within(dialog).getByRole("combobox", { name: /^Adapter/ });
    fireEvent.keyDown(adapter, { key: "ArrowDown" });
    fireEvent.mouseDown(screen.getByRole("option", { name: "NetSuite" }));
    // SCREENS §14.4: NetSuite defaults to "Both".
    expect(within(dialog).getByRole("combobox", { name: /^Direction/ }).textContent).toContain(
      "Both",
    );
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Name/ }), {
      target: { value: "NetSuite GL" },
    });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Code/ }), {
      target: { value: "netsuite-gl" },
    });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Base URL/ }), {
      target: { value: NETSUITE_MOCK },
    });
    // The namespace stands before the field; what is typed is the rest of the reference.
    expect(within(dialog).getByText(NAMESPACE)).toBeTruthy();
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Credential reference/ }), {
      target: { value: "netsuite-token@3" },
    });

    // SCR-PERM-05: a step-up is asked once, then the same command is sent again.
    server.use(
      http.post(apiUrl("/api/v1/integrations"), async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        world.commands.push({
          method: "POST",
          path: "/api/v1/integrations",
          body,
          ifMatch: null,
          idempotencyKey: request.headers.get("Idempotency-Key"),
        });
        refusals += 1;
        if (refusals === 1) {
          return problemResponse("mfa-step-up-required", 403, "Confirm with your authenticator");
        }
        const created = connection({
          ...(body as Partial<Connection>),
          id: NETSUITE_ID,
          status: "DISABLED",
          row_version: 1,
        });
        world.connections = [created];
        return HttpResponse.json(created, { status: 201 });
      }),
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Save connection" }));
    const stepUp = await screen.findByRole("dialog", { name: "Confirm with your authenticator" });
    fireEvent.change(within(stepUp).getByRole("textbox", { name: /^Authentication code/ }), {
      target: { value: "123456" },
    });
    fireEvent.click(within(stepUp).getByRole("button", { name: "Confirm" }));

    expect(
      await screen.findByText("Added NetSuite GL. The connection starts disabled."),
    ).toBeTruthy();
    expect(world.commands).toHaveLength(2);
    expect(world.commands[1]?.body).toEqual({
      adapter: "NETSUITE",
      code: "netsuite-gl",
      name: "NetSuite GL",
      direction: "BOTH",
      entity_ids: [],
      base_url: NETSUITE_MOCK,
      secret_ref: `${NAMESPACE}netsuite-token@3`,
      config: {},
    });
    // The resend carries the key of the refused attempt (DG-FE-05).
    expect(world.commands[1]?.idempotencyKey).toBe(world.commands[0]?.idempotencyKey);
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/data/integrations/${NETSUITE_ID}`),
    );
  });

  it("in a sandbox copy Add connection offers the adapters and the direction a sandbox accepts, and says why", async () => {
    const optionNames = () => screen.getAllByRole("option").map((option) => option.textContent);

    // The source workspace: the five adapters, and NetSuite in both directions.
    serve({ connections: [] });
    open("/data/integrations");
    expect(await screen.findByRole("heading", { name: "No integrations yet" })).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "Add connection" })[0] as HTMLElement);
    const inSource = await screen.findByRole("dialog", { name: "Add connection" });
    fireEvent.keyDown(within(inSource).getByRole("combobox", { name: /^Adapter/ }), {
      key: "ArrowDown",
    });
    expect(optionNames()).toEqual([
      "Salesforce",
      "Stripe",
      "NetSuite",
      "QuickBooks Online",
      "CSV GL export",
    ]);
    expect(within(inSource).queryByText(SANDBOX_ADD_REASON)).toBeNull();
    cleanup();

    // The copy (SB-R-08; 05 SBX-08): POST /integrations answers 403 `sandbox-restricted` there for a
    // CRM or billing adapter and for an inbound or two-way direction, so the drawer offers neither.
    const { me, session } = sandboxCopy();
    const world = serve({ connections: [] });
    server.use(
      http.post(apiUrl("/api/v1/integrations"), async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        world.commands.push({
          method: "POST",
          path: "/api/v1/integrations",
          body,
          ifMatch: null,
          idempotencyKey: request.headers.get("Idempotency-Key"),
        });
        return HttpResponse.json(
          connection({
            ...(body as Partial<Connection>),
            id: NETSUITE_ID,
            status: "DISABLED",
            row_version: 1,
          }),
          { status: 201 },
        );
      }),
    );
    renderApp("/data/integrations", { me, session, screenRoutes: SCREEN_ROUTES });
    expect(await screen.findByRole("heading", { name: "No integrations yet" })).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "Add connection" })[0] as HTMLElement);
    const dialog = await screen.findByRole("dialog", { name: "Add connection" });
    const adapter = within(dialog).getByRole("combobox", { name: /^Adapter/ });
    // The reason is the field's help, so it is announced with the field.
    expect(
      (adapter.getAttribute("aria-describedby") ?? "")
        .split(" ")
        .map((id) => document.getElementById(id)?.textContent ?? "")
        .join(" "),
    ).toContain(SANDBOX_ADD_REASON);
    fireEvent.keyDown(adapter, { key: "ArrowDown" });
    expect(optionNames()).toEqual(["NetSuite", "QuickBooks Online", "CSV GL export"]);
    fireEvent.mouseDown(screen.getByRole("option", { name: "NetSuite" }));
    // SCREENS §14.4: NetSuite defaults to "Both" in a production workspace; a sandbox has "Outbound".
    const direction = within(dialog).getByRole("combobox", { name: /^Direction/ });
    expect(direction.textContent).toContain("Outbound");
    fireEvent.keyDown(direction, { key: "ArrowDown" });
    expect(optionNames()).toEqual(["Outbound"]);
    fireEvent.keyDown(direction, { key: "Escape" });

    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Name/ }), {
      target: { value: "NetSuite journals" },
    });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Code/ }), {
      target: { value: "netsuite-journals" },
    });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Base URL/ }), {
      target: { value: NETSUITE_MOCK },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save connection" }));
    await waitFor(() => expect(world.commands).toHaveLength(1));
    expect(world.commands[0]?.body).toMatchObject({ adapter: "NETSUITE", direction: "OUTBOUND" });
  });

  it("a reference pasted whole keeps one prefix, and the API's refusal is shown on the field", async () => {
    const world = serve({ connections: [] });
    const refusal = `Enter the name of a secret of this workspace. It begins with ${NAMESPACE} and continues after it.`;
    server.use(
      http.post(apiUrl("/api/v1/integrations"), async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        world.commands.push({
          method: "POST",
          path: "/api/v1/integrations",
          body,
          ifMatch: null,
          idempotencyKey: request.headers.get("Idempotency-Key"),
        });
        return body.secret_ref === `${NAMESPACE}stripe-webhook@2`
          ? HttpResponse.json(
              connection({ ...(body as Partial<Connection>), id: NETSUITE_ID, status: "DISABLED" }),
              { status: 201 },
            )
          : problemResponse("validation-failed", 422, "Validation failed", {
              errors: [{ field: "secret_ref", rule_id: "T-INT-01", message: refusal }],
            });
      }),
    );
    open("/data/integrations");
    expect(await screen.findByRole("heading", { name: "No integrations yet" })).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "Add connection" })[0] as HTMLElement);
    const dialog = await screen.findByRole("dialog", { name: "Add connection" });
    fireEvent.keyDown(within(dialog).getByRole("combobox", { name: /^Adapter/ }), {
      key: "ArrowDown",
    });
    fireEvent.mouseDown(screen.getByRole("option", { name: "Stripe" }));
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Name/ }), {
      target: { value: "Stripe billing" },
    });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Code/ }), {
      target: { value: "stripe-billing" },
    });
    const reference = within(dialog).getByRole<HTMLInputElement>("textbox", {
      name: /^Credential reference/,
    });

    // A version without a name: the reference the form sends is the API's to refuse, and the refusal
    // is shown on the field in the API's words.
    fireEvent.change(reference, { target: { value: "@2" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save connection" }));
    expect(await within(dialog).findByText(refusal)).toBeTruthy();
    expect(world.commands[0]?.body).toMatchObject({ secret_ref: `${NAMESPACE}@2` });
    expect(reference.getAttribute("aria-invalid")).toBe("true");
    const described = (reference.getAttribute("aria-describedby") ?? "").split(" ");
    expect(described.map((id) => document.getElementById(id)?.textContent)).toContain(refusal);

    // A reference pasted whole, as the secret store shows it, keeps one prefix.
    fireEvent.change(reference, { target: { value: ` ${NAMESPACE}stripe-webhook@2` } });
    expect(reference.value).toBe("stripe-webhook@2");
    fireEvent.click(within(dialog).getByRole("button", { name: "Save connection" }));
    expect(
      await screen.findByText("Added Stripe billing. The connection starts disabled."),
    ).toBeTruthy();
    expect(world.commands).toHaveLength(2);
    expect(world.commands[1]?.body).toMatchObject({
      secret_ref: `${NAMESPACE}stripe-webhook@2`,
    });
  });

  it("an empty credential reference sends none", async () => {
    const world = serve({ connections: [] });
    open("/data/integrations");
    expect(await screen.findByRole("heading", { name: "No integrations yet" })).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "Add connection" })[0] as HTMLElement);
    const dialog = await screen.findByRole("dialog", { name: "Add connection" });
    fireEvent.keyDown(within(dialog).getByRole("combobox", { name: /^Adapter/ }), {
      key: "ArrowDown",
    });
    fireEvent.mouseDown(screen.getByRole("option", { name: "Salesforce" }));
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Name/ }), {
      target: { value: "Salesforce mock" },
    });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Code/ }), {
      target: { value: "salesforce-mock" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save connection" }));
    expect(
      await screen.findByText("Added Salesforce mock. The connection starts disabled."),
    ).toBeTruthy();
    expect(world.commands[0]?.body).toMatchObject({ secret_ref: null });
  });

  it("a stored reference outside the namespace is shown and is sent only when the field is changed", async () => {
    const world = serve({
      connections: [connection({ secret_ref: "SALESFORCE_CLIENT_CREDENTIAL" })],
    });
    open(`/data/integrations/${SALESFORCE_ID}?pane=settings`);
    const pane = await screen.findByTestId("SF-16-pane-settings");
    fireEvent.click(within(pane).getByRole("button", { name: "Edit connection" }));
    let dialog = await screen.findByRole("dialog", { name: "Edit connection" });
    let reference = within(dialog).getByRole<HTMLInputElement>("textbox", {
      name: /^Credential reference/,
    });
    const outside =
      "The stored reference SALESFORCE_CLIENT_CREDENTIAL is outside this workspace's namespace, so the secret store does not serve it. Enter a reference of this workspace to replace it.";
    expect(reference.value).toBe("");
    expect(within(dialog).getByText(outside)).toBeTruthy();
    expect(reference.getAttribute("aria-invalid")).toBe("true");

    // Another field changes: the stored reference is not sent, so the API keeps it as it is.
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Name/ }), {
      target: { value: "Salesforce orders (EU)" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save connection" }));
    expect(await screen.findByText("Saved Salesforce orders (EU).")).toBeTruthy();
    expect(world.commands).toHaveLength(1);
    expect(world.commands[0]?.body).toEqual({
      name: "Salesforce orders (EU)",
      entity_ids: [],
      base_url: SALESFORCE_MOCK,
      config: { api_version: "v60.0" },
    });
    expect(world.connections[0]?.secret_ref).toBe("SALESFORCE_CLIENT_CREDENTIAL");

    // The field changes: the reference of the workspace replaces the stored one.
    fireEvent.click(
      within(await screen.findByTestId("SF-16-pane-settings")).getByRole("button", {
        name: "Edit connection",
      }),
    );
    dialog = await screen.findByRole("dialog", { name: "Edit connection" });
    reference = within(dialog).getByRole<HTMLInputElement>("textbox", {
      name: /^Credential reference/,
    });
    fireEvent.change(reference, { target: { value: "salesforce-client@4" } });
    expect(within(dialog).queryByText(outside)).toBeNull();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save connection" }));
    await waitFor(() => expect(world.commands).toHaveLength(2));
    expect(world.commands[1]?.body).toMatchObject({
      secret_ref: `${NAMESPACE}salesforce-client@4`,
    });
    expect(world.commands[1]?.ifMatch).toBe('"r4"');
  });

  it("without integration.manage the screens are access-limited and read nothing", async () => {
    serve();
    open("/data/integrations", signedInMe({ permissions: ["contract.read"] }));
    expect(
      await screen.findByRole("heading", { name: "You do not have access to integrations" }),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Ask a workspace administrator for a role that includes managing integrations.",
      ),
    ).toBeTruthy();
    expect(screen.queryByTestId("SF-16-grid-connections")).toBeNull();
  });
});

describe("SF-16:sync-run", () => {
  it("shows the control totals of both sides and the run's one result", async () => {
    serve({ runs: [syncRun()] });
    open(`/data/integrations/${SALESFORCE_ID}/sync-runs/${RUN_ID}`);
    expect(
      await screen.findByRole("heading", { level: 1, name: "Sync run · Salesforce orders" }),
    ).toBeTruthy();
    const totals = await screen.findByRole("table", { name: "Control totals" });
    expect(screen.getByTestId("SF-16-grid-control-totals")).toBe(totals);
    expect(
      within(totals)
        .getAllByRole("row")
        .map((row) => Array.from(row.querySelectorAll("th, td"), (cell) => cell.textContent)),
    ).toEqual([
      ["Measure", "Source", "Loaded", "Result"],
      ["Records", "1", "1", "Reconciled"],
      ["Amount (USD)", "120,000.00", "120,000.00"],
    ]);
    expect(screen.getByText("Webhook batch")).toBeTruthy();
    expect(screen.getByText("12 Sep 2026 14:01:00 UTC")).toBeTruthy();
    expect(screen.getByText("12 Sep 2026 14:01:04 UTC")).toBeTruthy();
    expect(screen.getByText("4 s")).toBeTruthy();
    expect(screen.getByText("This run raised no exceptions.")).toBeTruthy();
    // The breadcrumb leads back to the connection.
    expect(
      within(screen.getByRole("navigation", { name: "Breadcrumb" }))
        .getByRole("link", { name: "Salesforce orders" })
        .getAttribute("href"),
    ).toBe(`/data/integrations/${SALESFORCE_ID}`);
  });

  it("a failed run shows its problem and the exceptions it raised", async () => {
    serve({
      runs: [
        syncRun({
          status: "FAILED",
          exception_count: 1,
          source_totals: null,
          loaded_totals: null,
          problem: {
            type: "https://erev.dev/problems/sync-run-failed",
            title: "The sync run failed",
            status: 500,
            detail: "1 record could not be loaded.",
            instance: "urn:erev:request:0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d",
          },
        }),
      ],
    });
    server.use(
      http.get(apiUrl("/api/v1/exceptions"), ({ request }) => {
        const params = new URL(request.url).searchParams;
        expect(params.get("source")).toBe("SYNC");
        expect(params.get("sync_run_id")).toBe(RUN_ID);
        return list([
          {
            id: "6f7a8b9c-0d1e-4f2a-9b3c-5d6e7f8a9b0c",
            title: "Product SF-PROD-X99 is not mapped",
            code: "PRODUCT_UNMAPPED",
            severity: "BLOCKING",
          },
        ]);
      }),
    );
    open(`/data/integrations/${SALESFORCE_ID}/sync-runs/${RUN_ID}`);
    const problem = await screen.findByTestId("SF-16-banner-problem");
    expect(within(problem).getByRole("heading", { name: "The sync run failed" })).toBeTruthy();
    expect(within(problem).getByText("1 record could not be loaded.")).toBeTruthy();
    expect(
      within(problem).getByText("Reference 0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d."),
    ).toBeTruthy();
    expect(screen.getByText("This run recorded no control totals.")).toBeTruthy();
    expect(screen.queryByTestId("SF-16-grid-control-totals")).toBeNull();
    const exceptions = await screen.findByTestId("SF-16-grid-exceptions");
    expect(
      within(exceptions)
        .getByRole("link", { name: "Product SF-PROD-X99 is not mapped" })
        .getAttribute("href"),
    ).toBe("/data/exceptions/6f7a8b9c-0d1e-4f2a-9b3c-5d6e7f8a9b0c");
    expect(within(exceptions).getByText("PRODUCT_UNMAPPED")).toBeTruthy();
    expect(within(exceptions).getByText("Blocking")).toBeTruthy();
  });

  it("a run of another connection is not found", async () => {
    serve({ runs: [syncRun({ integration_connection_id: NETSUITE_ID })] });
    open(`/data/integrations/${SALESFORCE_ID}/sync-runs/${RUN_ID}`);
    expect(await screen.findByRole("heading", { name: "Sync run not found" })).toBeTruthy();
  });
});

describe("API-R-45 as the screens read it", () => {
  it("every column of the three grids holds its header and its instants", () => {
    expect(narrowColumns(connectionColumns(undefined))).toEqual([]);
    expect(narrowColumns(syncRunColumns("connection", true))).toEqual([]);
    expect(narrowColumns(externalIdColumns(new Set()))).toEqual([]);
  });

  it("control totals are the recorded count and the amount of each currency", () => {
    expect(controlTotals(null)).toBeNull();
    expect(
      controlTotals({ count: 2, amount_by_currency: { USD: "10.00", EUR: "5.50" }, sha256: "x" }),
    ).toEqual({
      count: 2,
      amounts: [
        { currency: "EUR", amount: "5.50" },
        { currency: "USD", amount: "10.00" },
      ],
    });
    expect(totalsText(null)).toBeNull();
    expect(totalsText({ count: 0, amounts: [] })).toBe("0 records");
    // A currency the viewer's reads did not register keeps its recorded digits.
    expect(totalsText({ count: 1, amounts: [{ currency: "XTS", amount: "7.125" }] })).toBe(
      "1 record · XTS 7.125",
    );
  });

  it("Run sync offers the kinds the API queues for the adapter and direction", () => {
    expect(requestableKinds({ adapter: "SALESFORCE", direction: "INBOUND" })).toEqual([
      "INBOUND_POLL",
      "RECONCILIATION_SWEEP",
    ]);
    expect(requestableKinds({ adapter: "STRIPE", direction: "BOTH" })).toEqual([
      "INBOUND_POLL",
      "RECONCILIATION_SWEEP",
    ]);
    expect(requestableKinds({ adapter: "STRIPE", direction: "OUTBOUND" })).toEqual([]);
    expect(requestableKinds({ adapter: "NETSUITE", direction: "BOTH" })).toEqual(["COA_SYNC"]);
    expect(requestableKinds({ adapter: "QUICKBOOKS_ONLINE", direction: "OUTBOUND" })).toEqual([]);
    expect(requestableKinds({ adapter: "CSV_GL", direction: "OUTBOUND" })).toEqual([]);
  });

  it("entities outside the viewer's scope are counted, never shown by id", () => {
    const entities = [entity(AVM_US, "AVM-US", "Avenmoor US Inc.")];
    expect(entitiesText([], entities)).toBe("All entities");
    expect(entitiesText([AVM_US], undefined)).toBeNull();
    expect(entitiesText([AVM_US], entities)).toBe("AVM-US");
    expect(entitiesText([AVM_US, AVM_UK], entities)).toBe("AVM-US and 1 other");
    expect(entitiesText([AVM_UK], entities)).toBe("1 entity outside your scope");
  });
});
