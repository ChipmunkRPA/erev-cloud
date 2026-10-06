// @vitest-environment jsdom
// SF-16:developer and REQ-PLT-033, REQ-OPS-016 (BUILD_SPEC WEB-23; SCREENS_B §9.15; 04 API-R-08,
// API-R-15; PRD ERR-24): the tab "API clients" needs `api_client.manage` and "Webhooks" needs
// `webhook.manage`; the grid "API clients" shows Name, Client id, Status, Scopes, Entity scope, Rate limit
// per minute, Expires, Last used and Secret rotated; "New API client" lists only permissions with
// `is_approval` false, defaults Expires to 365 days and Rate limit to 600, runs step-up, then opens the
// dialog "Client secret for <name>" with the one-time warning, "Show" (`aria-pressed`), "Copy" and "Done"
// reporting "Confirm that you stored the secret." until "I have stored this secret" is checked; a 422
// `scope-not-allowed` shows "API clients cannot hold approval permissions."; "Rotate secret" and
// "Revoke" state their consequences; the webhooks tab creates endpoints with the dialog "Signing secret
// for <URL>" and lists deliveries with the E-97 chips; the OpenAPI tab shows its four lines; in a sandbox
// webhook activation is `aria-disabled` with the SB-R-08 reason; "Download inventory" is not rendered.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { accessOf } from "../../lib/access";
import {
  type ApiClient,
  clientTestKey,
  defaultExpiry,
  scopeGroups,
  shortClientId,
} from "../../lib/api/queries/api-clients";
import type { Permission } from "../../lib/api/queries/roles";
import {
  acceptableWebhookUrl,
  type WebhookDelivery,
  type WebhookEndpoint,
  urlPrefix,
} from "../../lib/api/queries/webhooks";
import { accessDescription } from "../../test/access";
import {
  installMemoryStorage,
  renderApp,
  renderWithApp,
  signedInMe,
  signedInSession,
} from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { ApiProblem } from "../../lib/api/problems";
import { placeProblem } from "../../lib/api/refusals";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { developerTabs, NewApiClientDrawer, selectedPane } from "./developer";

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

const TOMAS = signedInMe({
  permissions: ["api_client.manage", "webhook.manage", "config.read"],
  user: {
    id: "7d7d7d7d-7d7d-4d7d-8d7d-7d7d7d7d7d7d",
    email: "tomas@example.test",
    display_name: "Tomás Rivera",
    status: "ACTIVE",
  },
});
const INTEGRATOR = signedInMe({ permissions: ["webhook.manage"] });

const PERMISSIONS: readonly Permission[] = [
  {
    area: "Contracts",
    code: "contract.read",
    description: "Read contracts",
    is_access_admin: false,
    is_approval: false,
    requires_mfa: false,
  },
  {
    area: "Contracts",
    code: "contract.create",
    description: "Create contracts",
    is_access_admin: false,
    is_approval: false,
    requires_mfa: false,
  },
  {
    area: "Contracts",
    code: "contract.approve",
    description: "Approve contracts",
    is_access_admin: false,
    is_approval: true,
    requires_mfa: true,
  },
  {
    area: "Data",
    code: "import.upload",
    description: "Upload imports",
    is_access_admin: false,
    is_approval: false,
    requires_mfa: false,
  },
  {
    area: "Journals",
    code: "journal.approve",
    description: "Approve journal runs",
    is_access_admin: false,
    is_approval: true,
    requires_mfa: true,
  },
];

function client(overrides: Partial<ApiClient> & Pick<ApiClient, "id" | "name">): ApiClient {
  return {
    approval_request_id: null,
    client_id: "erevc_3f09a1b2c3d4e5f6a7b8c9d0e1f2a3b4_Xq2P9sKf0LmN3aBc7dE1fG",
    created_at: "2026-09-01T08:00:00Z",
    entity_ids: [],
    expires_at: "2027-09-01T08:00:00Z",
    has_secret: true,
    is_all_entities: true,
    last_used_at: "2026-09-12T14:30:00Z",
    rate_limit_per_minute: 600,
    row_version: 1,
    scopes: ["contract.read", "contract.create"],
    secret_rotated_at: null,
    status: "ACTIVE",
    updated_at: "2026-09-01T08:00:00Z",
    ...overrides,
  };
}

const SALESFORCE = client({
  id: "a1a1a1a1-a1a1-4a1a-8a1a-a1a1a1a1a1a1",
  name: "svc-salesforce",
  scopes: ["contract.read", "contract.create", "import.upload", "masterdata.maintain"],
});
const NETSUITE = client({
  id: "b2b2b2b2-b2b2-4b2b-8b2b-b2b2b2b2b2b2",
  name: "svc-netsuite",
  client_id: "erevc_3f09a1b2c3d4e5f6a7b8c9d0e1f2a3b4_7LmQ9sKf0LmN3aBc7dE1fG",
  scopes: ["journal.export"],
  is_all_entities: false,
  entity_ids: ["e1e1e1e1-e1e1-4e1e-8e1e-e1e1e1e1e1e1", "e2e2e2e2-e2e2-4e2e-8e2e-e2e2e2e2e2e2"],
  rate_limit_per_minute: 1200,
  secret_rotated_at: "2026-09-10T09:00:00Z",
});
const METERING = client({
  id: "c3c3c3c3-c3c3-4c3c-8c3c-c3c3c3c3c3c3",
  name: "svc-metering",
  status: "REVOKED",
  last_used_at: null,
});

const ENDPOINT: WebhookEndpoint = {
  id: "d4d4d4d4-d4d4-4d4d-8d4d-d4d4d4d4d4d4",
  url: "https://hooks.example.test/erev/events",
  description: "Finance data lake",
  event_kinds: ["run.completed", "period.locked"],
  is_active: true,
  row_version: 3,
  created_at: "2026-08-20T10:00:00Z",
  updated_at: "2026-08-20T10:00:00Z",
};
const PAUSED: WebhookEndpoint = {
  id: "e5e5e5e5-e5e5-4e5e-8e5e-e5e5e5e5e5e5",
  url: "https://paused.example.test/hook",
  description: null,
  event_kinds: ["exception.raised"],
  is_active: false,
  row_version: 2,
  created_at: "2026-08-21T10:00:00Z",
  updated_at: "2026-08-21T10:00:00Z",
};

function delivery(
  overrides: Partial<WebhookDelivery> & Pick<WebhookDelivery, "id" | "status">,
): WebhookDelivery {
  return {
    abandon_at: "2026-09-20T10:00:00Z",
    attempt_count: 1,
    created_at: "2026-09-19T10:00:00Z",
    event_kind: "run.completed",
    last_error: null,
    last_response_status: 200,
    next_attempt_at: null,
    payload: { run_id: "f6f6f6f6-f6f6-4f6f-8f6f-f6f6f6f6f6f6" },
    payload_sha256: "0000000000000000000000000000000000000000000000000000000000000000",
    succeeded_at: "2026-09-19T10:00:02Z",
    webhook_endpoint_id: ENDPOINT.id,
    ...overrides,
  };
}

const DELIVERED = delivery({ id: "01010101-0101-4101-8101-010101010101", status: "SUCCEEDED" });
const FAILING = delivery({
  id: "02020202-0202-4202-8202-020202020202",
  status: "FAILED",
  event_kind: "period.locked",
  attempt_count: 3,
  last_response_status: 503,
  last_error: "upstream unavailable",
  next_attempt_at: "2026-09-19T11:00:00Z",
  succeeded_at: null,
});
const QUEUED = delivery({
  id: "03030303-0303-4303-8303-030303030303",
  status: "PENDING",
  attempt_count: 0,
  last_response_status: null,
  succeeded_at: null,
  next_attempt_at: "2026-09-19T10:05:00Z",
});

function listResponse<T>(items: readonly T[], request: Request) {
  return HttpResponse.json(
    { items, next_cursor: null },
    {
      headers:
        new URL(request.url).searchParams.get("count") === "true"
          ? { "X-Erev-Total-Count": String(items.length) }
          : {},
    },
  );
}

function serve(options: {
  readonly clients?: readonly ApiClient[];
  readonly endpoints?: readonly WebhookEndpoint[];
  readonly deliveries?: readonly WebhookDelivery[];
}) {
  const clients = options.clients ?? [];
  const endpoints = options.endpoints ?? [];
  const deliveries = options.deliveries ?? [];
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), () =>
      HttpResponse.json({
        items: [
          {
            id: "e1e1e1e1-e1e1-4e1e-8e1e-e1e1e1e1e1e1",
            code: "DE01",
            name: "Avenmoor GmbH",
            functional_currency: "EUR",
            calendar_id: "c1c1c1c1-c1c1-4c1c-8c1c-c1c1c1c1c1c1",
            parent_entity_id: null,
            is_active: true,
            row_version: 1,
            books: [],
          },
        ],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/books"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/periods"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/saved-views"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/permissions"), () =>
      HttpResponse.json({ items: PERMISSIONS, next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/api-clients"), ({ request }) => listResponse(clients, request)),
    http.get(apiUrl("/api/v1/webhook-endpoints"), ({ request }) =>
      listResponse(endpoints, request),
    ),
    http.get(apiUrl("/api/v1/webhook-deliveries"), ({ request }) => {
      const status = new URL(request.url).searchParams.get("status");
      const items =
        status === null ? deliveries : deliveries.filter((item) => item.status === status);
      return listResponse(items, request);
    }),
  );
}

function renderDeveloper(entry = "/settings/developer", me = TOMAS, session = signedInSession()) {
  return renderApp(entry, { me, session, screenRoutes: SCREEN_ROUTES });
}

async function findGrid(testId: string, name: string) {
  return within(await screen.findByTestId(testId)).findByRole("grid", { name });
}

/** The reason line a disabled control is described by (DS-CMP-27: `aria-describedby`). */
function reasonOf(control: HTMLElement): string | null {
  const id = control.getAttribute("aria-describedby");
  return id === null ? null : (document.getElementById(id)?.textContent ?? null);
}

/** Every text a control is described by, in the order of its `aria-describedby`. */
function descriptionsOf(control: HTMLElement): readonly string[] {
  return (control.getAttribute("aria-describedby") ?? "")
    .split(" ")
    .filter((id) => id !== "")
    .map((id) => document.getElementById(id)?.textContent ?? "");
}

/** One entry of a problem's `errors[]`, as the API states a field refusal. */
function refusal(field: string, message: string) {
  return { field, sheet: null, row: null, rule_id: "EREV-PLT-033", message };
}

/** A 422 `validation-failed` as the kernel answers it: the title, the count and the field errors. */
function refused(errors: readonly ReturnType<typeof refusal>[]) {
  return problemResponse("validation-failed", 422, "Check the highlighted fields", {
    detail:
      errors.length === 1 ? "1 field needs attention." : `${errors.length} fields need attention.`,
    errors: [...errors],
  });
}

function installClipboard(): { readonly writes: string[] } {
  const writes: string[] = [];
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: {
      writeText: (text: string) => {
        writes.push(text);
        return Promise.resolve();
      },
    },
  });
  return { writes };
}

describe("SF-16:developer and REQ-PLT-033, REQ-OPS-016", () => {
  it("the grid API clients shows Name, Client id, Status, Scopes, Entity scope, Rate limit per minute, Expires, Last used and Secret rotated; Rotate secret and Revoke show on active clients; Download inventory is not rendered", async () => {
    serve({ clients: [SALESFORCE, NETSUITE, METERING] });
    renderDeveloper();

    expect(
      await screen.findByRole("heading", { level: 1, name: "API clients and webhooks" }),
    ).toBeTruthy();
    const tablist = screen.getByRole("tablist", { name: "Developer sections" });
    expect(
      within(tablist)
        .getAllByRole("tab")
        .map((tab) => tab.textContent),
    ).toEqual(["API clients", "Webhooks", "OpenAPI"]);
    expect(
      within(tablist).getByRole("tab", { name: "API clients" }).getAttribute("aria-selected"),
    ).toBe("true");

    const grid = await findGrid("SF-16-grid-api-clients", "API clients");
    const headers = within(grid)
      .getAllByRole("columnheader")
      .map((header) => header.textContent?.trim() ?? "");
    for (const name of [
      "Name",
      "Client id",
      "Status",
      "Scopes",
      "Entity scope",
      "Rate limit per minute",
      "Expires",
      "Last used",
      "Secret rotated",
    ]) {
      expect(headers.some((header) => header.startsWith(name))).toBe(true);
    }
    const salesforce = await within(grid).findByTestId("SF-16-row-svc-salesforce");
    expect(within(salesforce).getByText("svc-salesforce")).toBeTruthy();
    expect(within(salesforce).getByText(shortClientId(SALESFORCE.client_id))).toBeTruthy();
    expect(shortClientId(SALESFORCE.client_id)).toBe("erevc_3f09…7dE1fG");
    expect(within(salesforce).getByText("Active")).toBeTruthy();
    expect(
      within(salesforce).getByText(
        "contract.read, contract.create, import.upload, masterdata.maintain",
      ),
    ).toBeTruthy();
    expect(within(salesforce).getByText("All entities")).toBeTruthy();
    expect(within(salesforce).getByText("600")).toBeTruthy();
    expect(within(salesforce).getByText("01 Sep 2027 08:00 UTC")).toBeTruthy();
    expect(within(salesforce).getByText("12 Sep 2026 14:30 UTC")).toBeTruthy();
    expect(within(salesforce).getByRole("button", { name: "Rotate secret" })).toBeTruthy();
    expect(within(salesforce).getByRole("button", { name: "Revoke" })).toBeTruthy();

    const netsuite = within(grid).getByTestId("SF-16-row-svc-netsuite");
    expect(within(netsuite).getByText("2 entities")).toBeTruthy();
    expect(within(netsuite).getByText("1,200")).toBeTruthy();
    expect(within(netsuite).getByText("10 Sep 2026 09:00 UTC")).toBeTruthy();

    const metering = within(grid).getByTestId("SF-16-row-svc-metering");
    expect(within(metering).getByText("Revoked")).toBeTruthy();
    expect(within(metering).queryByRole("button", { name: "Rotate secret" })).toBeNull();
    expect(within(metering).queryByRole("button", { name: "Revoke" })).toBeNull();

    // BS1-D-14: the RPT-27 inventory download arrives with the item that builds the report.
    expect(screen.queryByText("Download inventory")).toBeNull();
    // The grid count label follows the loading flag in a later commit (F-ADM latent-race sweep).
    expect(await screen.findByText("3 API clients")).toBeTruthy();
    expect(clientTestKey("Svc Metering (EU)")).toBe("svc-metering-eu");
  });

  it("a client that awaits approval reads Pending approval and a refused one Rejected; neither offers an action", async () => {
    // Ruling R-113 (e); SCREENS_B §0.4 E-103 and §9.15 (rev 1.59). The two literals reach the API with
    // lane SECFIX-APR's slice; until the schema carries them the fixtures name them as strings.
    const pending = client({
      id: "d4d4d4d4-d4d4-4d4d-8d4d-d4d4d4d4d4d5",
      name: "svc-billing",
      status: "PENDING_APPROVAL" as ApiClient["status"],
      last_used_at: null,
    });
    const rejected = client({
      id: "e5e5e5e5-e5e5-4e5e-8e5e-e5e5e5e5e5e6",
      name: "svc-crm",
      status: "REJECTED" as ApiClient["status"],
      last_used_at: null,
    });
    serve({ clients: [SALESFORCE, pending, rejected] });
    renderDeveloper();

    const grid = await findGrid("SF-16-grid-api-clients", "API clients");
    const awaiting = await within(grid).findByTestId("SF-16-row-svc-billing");
    const chip = within(awaiting).getByText("Pending approval");
    expect(chip.getAttribute("data-tone")).toBe("info");
    const refused = within(grid).getByTestId("SF-16-row-svc-crm");
    expect(within(refused).getByText("Rejected").getAttribute("data-tone")).toBe("negative");
    for (const row of [awaiting, refused]) {
      expect(within(row).queryByRole("button", { name: "Rotate secret" })).toBeNull();
      expect(within(row).queryByRole("button", { name: "Revoke" })).toBeNull();
    }
    // The active client beside them keeps its two actions.
    const active = within(grid).getByTestId("SF-16-row-svc-salesforce");
    expect(within(active).getByRole("button", { name: "Rotate secret" })).toBeTruthy();
    expect(within(active).getByRole("button", { name: "Revoke" })).toBeTruthy();
  });

  it("the API clients tab needs api_client.manage and Webhooks needs webhook.manage; a member with neither sees the access empty state", async () => {
    serve({ endpoints: [ENDPOINT] });
    renderDeveloper("/settings/developer", INTEGRATOR);

    const tablist = await screen.findByRole("tablist", { name: "Developer sections" });
    // The unreadable tab renders disabled with its reason; the first readable tab is selected.
    const clients = within(tablist).getByRole("tab", { name: "API clients" });
    expect(clients.getAttribute("aria-disabled")).toBe("true");
    expect(clients.getAttribute("aria-selected")).toBe("false");
    expect(
      within(tablist).getByRole("tab", { name: "Webhooks" }).getAttribute("aria-selected"),
    ).toBe("true");
    expect(await findGrid("SF-16-grid-webhooks", "Webhook endpoints")).toBeTruthy();
    expect(screen.queryByTestId("SF-16-grid-api-clients")).toBeNull();

    const tabs = developerTabs(accessOf(INTEGRATOR));
    expect(tabs.map((tab) => tab.disabledReason)).toEqual([
      "The API clients tab needs a role that includes managing API clients (api_client.manage).",
      undefined,
      undefined,
    ]);
    expect(selectedPane("api-clients", tabs)).toBe("webhooks");
    expect(selectedPane("openapi", tabs)).toBe("openapi");
    cleanup();

    renderDeveloper("/settings/developer", signedInMe({ permissions: ["contract.read"] }));
    expect(
      await screen.findByRole("heading", {
        name: "You do not have access to API clients and webhooks",
      }),
    ).toBeTruthy();
    expect(accessDescription()).toBe(
      "Ask a workspace administrator for a role that includes managing API clients (api_client.manage) or managing webhooks (webhook.manage).",
    );
    expect(screen.queryByRole("tablist")).toBeNull();
  });

  // W-12e: the webhooks of the workspace are read and managed by a holder of webhook.manage for all
  // entities alone. A holder for one entity was shown the tab and "New webhook endpoint" while the
  // API refused both lists and the command.
  it("webhook.manage for one entity alone: the page says that webhooks cover every entity; beside api_client.manage the Webhooks tab is unavailable with that reason, and no webhook is asked for", async () => {
    const asked: string[] = [];
    serve({ endpoints: [ENDPOINT] });
    server.use(
      http.get(apiUrl("/api/v1/*"), ({ request }) => {
        asked.push(new URL(request.url).pathname);
      }),
    );
    const scoped = { "webhook.manage": ["0a1b2c3d-4e5f-4a6b-8c7d-0000000000de"] };
    renderDeveloper(
      "/settings/developer",
      signedInMe({ permissions: ["webhook.manage"], permission_scopes: scoped }),
    );
    expect(
      await screen.findByRole("heading", {
        name: "You do not have access to API clients and webhooks",
      }),
    ).toBeTruthy();
    expect(accessDescription()).toBe(
      "Webhooks cover every entity of the workspace. Ask a workspace administrator for a role that includes managing webhooks (webhook.manage) for all entities.",
    );
    expect(screen.queryByRole("tablist")).toBeNull();
    cleanup();

    const both = signedInMe({
      permissions: ["api_client.manage", "webhook.manage"],
      permission_scopes: { "api_client.manage": "*", ...scoped },
    });
    renderDeveloper("/settings/developer?pane=webhooks", both);
    const tablist = await screen.findByRole("tablist", { name: "Developer sections" });
    const webhooks = within(tablist).getByRole("tab", { name: "Webhooks" });
    expect(webhooks.getAttribute("aria-disabled")).toBe("true");
    expect(
      within(tablist).getByRole("tab", { name: "API clients" }).getAttribute("aria-selected"),
    ).toBe("true");
    expect(developerTabs(accessOf(both)).map((tab) => tab.disabledReason)).toEqual([
      undefined,
      "The Webhooks tab needs a role that includes managing webhooks (webhook.manage) for all entities.",
      undefined,
    ]);
    expect(screen.queryByRole("button", { name: "New webhook endpoint" })).toBeNull();
    expect(asked.filter((path) => path.startsWith("/api/v1/webhook"))).toEqual([]);
  });

  it("New API client lists only non-approval permissions grouped by area, defaults Expires to 365 days and Rate limit to 600, runs step-up with the same Idempotency-Key, then opens the one-time secret dialog", async () => {
    const { writes } = installClipboard();
    const keys: (string | null)[] = [];
    const bodies: unknown[] = [];
    const verifications: unknown[] = [];
    serve({ clients: [] });
    server.use(
      http.post(apiUrl("/api/v1/api-clients"), async ({ request }) => {
        keys.push(request.headers.get("Idempotency-Key"));
        bodies.push(await request.json());
        if (keys.length === 1) {
          return problemResponse("mfa-step-up-required", 403, "Step-up required");
        }
        return HttpResponse.json(
          {
            ...SALESFORCE,
            client_secret: "erevs_Very-Secret-Value-0123456789abcdef",
          },
          { status: 201 },
        );
      }),
      http.post(apiUrl("/api/v1/session/mfa"), async ({ request }) => {
        verifications.push(await request.json());
        return HttpResponse.json({
          authenticated: true,
          user: signedInMe().user,
          active_tenant: null,
          mfa_verified_at: "2026-09-19T10:10:00Z",
          idle_expires_at: "2026-09-19T11:10:00Z",
          absolute_expires_at: "2026-09-19T20:00:00Z",
          capabilities: { identity_providers: [] },
          csrf_token: "csrf-rotated",
          recovery_codes_remaining: null,
        });
      }),
    );
    const nowMs = Date.now();
    renderDeveloper();

    const empty = await screen.findByTestId("SF-16-empty-api-clients");
    expect(within(empty).getByRole("heading", { name: "No API clients" })).toBeTruthy();
    expect(
      within(empty).getByText(
        "API clients use OAuth2 client credentials. Their scopes never include approval permissions.",
      ),
    ).toBeTruthy();
    fireEvent.click(within(empty).getByRole("button", { name: "New API client" }));

    const drawer = await screen.findByRole("dialog", { name: "New API client" });
    const form = within(drawer).getByTestId("SF-16-drawer-api-client");
    // Non-approval permissions only, grouped by area (J-23.3).
    expect(await within(form).findByRole("checkbox", { name: /^contract\.read/ })).toBeTruthy();
    expect(within(form).getByRole("checkbox", { name: /^contract\.create/ })).toBeTruthy();
    expect(within(form).getByRole("checkbox", { name: /^import\.upload/ })).toBeTruthy();
    expect(within(form).queryByRole("checkbox", { name: /^contract\.approve/ })).toBeNull();
    expect(within(form).queryByRole("checkbox", { name: /^journal\.approve/ })).toBeNull();
    expect(within(form).getByRole("group", { name: "Contracts" })).toBeTruthy();
    expect(within(form).getByRole("group", { name: "Data" })).toBeTruthy();
    expect(within(form).queryByRole("group", { name: "Journals" })).toBeNull();
    expect(scopeGroups(PERMISSIONS).map((group) => group.area)).toEqual(["Contracts", "Data"]);
    expect(
      within(form).getByText(
        "Non-approval permissions only. An approval scope is refused with ERR-24.",
      ),
    ).toBeTruthy();

    // Defaults: expiry 365 days from today, rate limit 600.
    const expires = within(form).getByRole("textbox", { name: "Expires" });
    const expected = defaultExpiry(nowMs);
    expect(expected).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(within(form).getByText("Defaults to 365 days from today.")).toBeTruthy();
    expect(expires.getAttribute("value")).not.toBe("");
    expect(
      within(form).getByRole("textbox", { name: "Rate limit per minute" }).getAttribute("value"),
    ).toBe("600");
    expect(
      within(form).getByRole("radio", { name: "All entities" }).getAttribute("checked"),
    ).not.toBeNull();

    // Validation before any request.
    fireEvent.click(within(drawer).getByRole("button", { name: "Create API client" }));
    expect(await within(form).findByText("Enter the client name.")).toBeTruthy();
    expect(within(form).getByText("Choose at least one scope.")).toBeTruthy();
    expect(bodies).toHaveLength(0);

    fireEvent.change(within(form).getByRole("textbox", { name: "Name" }), {
      target: { value: "svc-salesforce" },
    });
    fireEvent.click(within(form).getByRole("checkbox", { name: /^contract\.read/ }));
    fireEvent.click(within(form).getByRole("checkbox", { name: /^import\.upload/ }));
    fireEvent.click(within(drawer).getByRole("button", { name: "Create API client" }));

    // SCR-PERM-05: the step-up modal, then the same command is resent with the same key.
    const stepUp = await screen.findByRole("dialog", { name: "Confirm with your authenticator" });
    fireEvent.change(within(stepUp).getByRole("textbox", { name: "Authentication code" }), {
      target: { value: "246810" },
    });
    fireEvent.click(within(stepUp).getByRole("button", { name: "Confirm" }));

    const secret = await screen.findByRole("dialog", { name: "Client secret for svc-salesforce" });
    expect(secret.getAttribute("data-testid")).toBe("SF-16-dialog-client-secret");
    expect(verifications).toEqual([{ code: "246810" }]);
    expect(keys).toHaveLength(2);
    expect(keys[1]).toBe(keys[0]);
    expect(bodies[1]).toEqual({
      name: "svc-salesforce",
      scopes: ["contract.read", "import.upload"],
      is_all_entities: true,
      expires_at: `${expected}T00:00:00Z`,
      rate_limit_per_minute: 600,
    });
    expect(
      within(secret).getByText("This secret is shown once. It cannot be shown again."),
    ).toBeTruthy();
    expect(within(secret).getByText(SALESFORCE.client_id)).toBeTruthy();
    // The secret is masked and not announced until "Show" is pressed.
    expect(within(secret).queryByText("erevs_Very-Secret-Value-0123456789abcdef")).toBeNull();
    expect(within(secret).getByText("Client secret, hidden")).toBeTruthy();
    const show = within(secret).getByRole("button", { name: "Show" });
    expect(show.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(show);
    expect(show.getAttribute("aria-pressed")).toBe("true");
    expect(within(secret).getByText("erevs_Very-Secret-Value-0123456789abcdef")).toBeTruthy();
    expect(within(secret).queryByText("Client secret, hidden")).toBeNull();

    const copies = within(secret).getAllByRole("button", { name: "Copy" });
    expect(copies).toHaveLength(2);
    fireEvent.click(copies[1] as HTMLElement);
    await waitFor(() => {
      expect(writes).toEqual(["erevs_Very-Secret-Value-0123456789abcdef"]);
    });
    expect(await screen.findByText("Copied Client secret.")).toBeTruthy();

    // "Done" reports the acknowledgement until the required box is checked; Esc does not close it.
    const done = within(secret).getByRole("button", { name: "Done" });
    expect(done.getAttribute("aria-disabled")).toBe("true");
    // The reason line beside the button (the disabled-reason tooltip repeats it).
    expect(
      within(secret).getAllByText("Confirm that you stored the secret.").length,
    ).toBeGreaterThan(0);
    fireEvent.keyDown(secret, { key: "Escape" });
    expect(screen.getByRole("dialog", { name: "Client secret for svc-salesforce" })).toBeTruthy();
    const stored = within(secret).getByRole("checkbox", { name: "I have stored this secret" });
    expect(stored.getAttribute("aria-required")).toBe("true");
    fireEvent.click(stored);
    expect(within(secret).queryAllByText("Confirm that you stored the secret.")).toHaveLength(0);
    expect(
      within(secret).getByRole("button", { name: "Done" }).getAttribute("aria-disabled"),
    ).toBeNull();
    fireEvent.click(within(secret).getByRole("button", { name: "Done" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Client secret for svc-salesforce" })).toBeNull();
    });
    // The secret never appears again (REQ-PLT-033).
    expect(screen.queryByText("erevs_Very-Secret-Value-0123456789abcdef")).toBeNull();
  });

  it("a 422 scope-not-allowed shows API clients cannot hold approval permissions.", async () => {
    serve({ clients: [] });
    server.use(
      http.post(apiUrl("/api/v1/api-clients"), () =>
        problemResponse("scope-not-allowed", 422, "Scope not allowed", {
          detail: "API clients cannot hold approval permissions.",
        }),
      ),
    );
    renderDeveloper();

    fireEvent.click(
      within(await screen.findByTestId("SF-16-empty-api-clients")).getByRole("button", {
        name: "New API client",
      }),
    );
    const drawer = await screen.findByRole("dialog", { name: "New API client" });
    const form = within(drawer).getByTestId("SF-16-drawer-api-client");
    fireEvent.change(within(form).getByRole("textbox", { name: "Name" }), {
      target: { value: "svc-bad" },
    });
    fireEvent.click(await within(form).findByRole("checkbox", { name: /^contract\.read/ }));
    fireEvent.click(within(drawer).getByRole("button", { name: "Create API client" }));

    const alert = await within(drawer).findByRole("alert");
    expect(
      within(alert).getByRole("heading", { name: "API clients cannot hold approval permissions." }),
    ).toBeTruthy();
    expect(screen.getByRole("dialog", { name: "New API client" })).toBeTruthy();
  });

  it("Selected entities is unavailable with its reason, and All entities stays chosen", async () => {
    // SCREENS_B §9.15 rev 1.62: POST /api-clients refuses every entity code until item
    // API-CLIENT-ENTITY-SCOPE-1 is on main, so the screen does not offer the choice.
    const bodies: unknown[] = [];
    serve({ clients: [] });
    server.use(
      http.post(apiUrl("/api/v1/api-clients"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(
          { ...SALESFORCE, client_secret: "erevs_Very-Secret-Value-0123456789abcdef" },
          { status: 201 },
        );
      }),
    );
    renderDeveloper();
    fireEvent.click(
      within(await screen.findByTestId("SF-16-empty-api-clients")).getByRole("button", {
        name: "New API client",
      }),
    );
    const drawer = await screen.findByRole("dialog", { name: "New API client" });
    const form = within(drawer).getByTestId("SF-16-drawer-api-client");
    const all = within(form).getByRole<HTMLInputElement>("radio", { name: "All entities" });
    const selected = within(form).getByRole<HTMLInputElement>("radio", {
      name: "Selected entities",
    });
    // Unavailable, and still in the tab order so that its reason is read.
    expect(selected.getAttribute("aria-disabled")).toBe("true");
    expect(selected.disabled).toBe(false);
    expect(reasonOf(selected)).toBe("An API client covers all entities.");
    expect(within(form).getByText("An API client covers all entities.")).toBeTruthy();
    fireEvent.click(selected);
    expect(selected.checked).toBe(false);
    expect(all.checked).toBe(true);
    expect(all.getAttribute("aria-disabled")).toBeNull();
    expect(within(form).queryByRole("combobox", { name: "Entities" })).toBeNull();

    // The client is created for all entities, and the body names no entity.
    fireEvent.change(within(form).getByRole("textbox", { name: "Name" }), {
      target: { value: "svc-salesforce" },
    });
    fireEvent.click(await within(form).findByRole("checkbox", { name: /^contract\.read/ }));
    fireEvent.click(within(drawer).getByRole("button", { name: "Create API client" }));
    await screen.findByRole("dialog", { name: "Client secret for svc-salesforce" });
    expect(bodies).toHaveLength(1);
    expect(bodies[0]).toMatchObject({ is_all_entities: true });
    expect(bodies[0]).not.toHaveProperty("entity_codes");
  });

  it("a refusal's field errors show at their fields, and leave a field when its value is edited", async () => {
    // DS-CMP-21: server errors map to fields by their pointer. Before SCREENS_B rev 1.62 the banner
    // said "Check the highlighted fields" and the drawer highlighted none.
    serve({ clients: [] });
    server.use(
      http.post(apiUrl("/api/v1/api-clients"), () =>
        refused([
          refusal("name", "Use 1 to 400 characters."),
          refusal("scopes[0]", "Choose permissions from the permission catalogue."),
          refusal("entity_codes", "Choose entities that exist in this workspace."),
          refusal("expires_at", "Choose an expiry in the future."),
          refusal("rate_limit_per_minute", "Enter a whole number of at least 1."),
          // A member the drawer has no field for: the banner lists it.
          refusal("labels", "Labels are not accepted."),
        ]),
      ),
    );
    renderDeveloper();
    fireEvent.click(
      within(await screen.findByTestId("SF-16-empty-api-clients")).getByRole("button", {
        name: "New API client",
      }),
    );
    const drawer = await screen.findByRole("dialog", { name: "New API client" });
    const form = within(drawer).getByTestId("SF-16-drawer-api-client");
    const name = within(form).getByRole("textbox", { name: "Name" });
    fireEvent.change(name, { target: { value: "svc-long" } });
    fireEvent.click(await within(form).findByRole("checkbox", { name: /^contract\.read/ }));
    fireEvent.click(within(drawer).getByRole("button", { name: "Create API client" }));

    const alert = await within(drawer).findByRole("alert");
    expect(
      within(alert).getByRole("heading", { name: "Check the highlighted fields" }),
    ).toBeTruthy();
    expect(within(alert).getByText("Labels are not accepted.")).toBeTruthy();
    for (const placed of [
      "Use 1 to 400 characters.",
      "Choose permissions from the permission catalogue.",
      "Choose entities that exist in this workspace.",
      "Choose an expiry in the future.",
      "Enter a whole number of at least 1.",
    ]) {
      expect(within(alert).queryByText(placed)).toBeNull();
      expect(within(form).getByText(placed)).toBeTruthy();
    }
    // Each message is the description of its field, and the inputs are marked invalid.
    expect(name.getAttribute("aria-invalid")).toBe("true");
    expect(descriptionsOf(name)).toContain("Use 1 to 400 characters.");
    expect(descriptionsOf(within(form).getByRole("group", { name: "Scopes" }))).toContain(
      "Choose permissions from the permission catalogue.",
    );
    // No entity can be chosen, so the refusal of the entities stands at the entity scope.
    expect(descriptionsOf(within(form).getByRole("group", { name: "Entity scope" }))).toContain(
      "Choose entities that exist in this workspace.",
    );
    const expires = within(form).getByRole("textbox", { name: "Expires" });
    expect(expires.getAttribute("aria-invalid")).toBe("true");
    expect(descriptionsOf(expires)).toContain("Choose an expiry in the future.");
    const rate = within(form).getByRole("textbox", { name: "Rate limit per minute" });
    expect(rate.getAttribute("aria-invalid")).toBe("true");
    expect(descriptionsOf(rate)).toContain("Enter a whole number of at least 1.");

    // The message describes the value that was sent: it leaves the field once that value is edited.
    fireEvent.change(name, { target: { value: "svc-short" } });
    expect(within(form).queryByText("Use 1 to 400 characters.")).toBeNull();
    expect(name.getAttribute("aria-invalid")).toBeNull();
    fireEvent.change(rate, { target: { value: "900" } });
    expect(within(form).queryByText("Enter a whole number of at least 1.")).toBeNull();
    fireEvent.click(within(form).getByRole("checkbox", { name: /^import\.upload/ }));
    expect(
      within(form).queryByText("Choose permissions from the permission catalogue."),
    ).toBeNull();
    expect(within(form).getByText("Choose an expiry in the future.")).toBeTruthy();
    expect(within(form).getByText("Choose entities that exist in this workspace.")).toBeTruthy();
  });

  it("with the entity choice, Selected entities needs an entity and shows the server's refusal at Entities", async () => {
    // The drawer as it will be when API-CLIENT-ENTITY-SCOPE-1 is on main.
    const bodies: unknown[] = [];
    serve({ clients: [] });
    server.use(
      http.post(apiUrl("/api/v1/api-clients"), async ({ request }) => {
        bodies.push(await request.json());
        return refused([refusal("entity_codes", "Choose entities that exist in this workspace.")]);
      }),
    );
    renderWithApp(
      <NewApiClientDrawer entityChoice onClose={() => undefined} onCreated={() => undefined} />,
      { me: TOMAS },
    );
    const drawer = await screen.findByRole("dialog", { name: "New API client" });
    const form = within(drawer).getByTestId("SF-16-drawer-api-client");
    fireEvent.change(within(form).getByRole("textbox", { name: "Name" }), {
      target: { value: "svc-scoped" },
    });
    fireEvent.click(await within(form).findByRole("checkbox", { name: /^contract\.read/ }));
    const selected = within(form).getByRole<HTMLInputElement>("radio", {
      name: "Selected entities",
    });
    expect(selected.getAttribute("aria-disabled")).toBeNull();
    expect(within(form).queryByText("An API client covers all entities.")).toBeNull();
    fireEvent.click(selected);
    expect(selected.checked).toBe(true);
    fireEvent.click(within(drawer).getByRole("button", { name: "Create API client" }));
    expect(await within(form).findByText("Choose at least one entity.")).toBeTruthy();
    expect(bodies).toHaveLength(0);

    const entities = within(form).getByRole("combobox", { name: "Entities" });
    fireEvent.change(entities, { target: { value: "DE" } });
    fireEvent.mouseDown(await screen.findByRole("option", { name: "DE01 · Avenmoor GmbH" }));
    fireEvent.click(within(drawer).getByRole("button", { name: "Create API client" }));
    expect(
      await within(form).findByText("Choose entities that exist in this workspace."),
    ).toBeTruthy();
    expect(bodies[0]).toMatchObject({ is_all_entities: false, entity_codes: ["DE01"] });
    expect(descriptionsOf(within(form).getByRole("combobox", { name: "Entities" }))).toContain(
      "Choose entities that exist in this workspace.",
    );
    const alert = within(drawer).getByRole("alert");
    expect(within(alert).queryByText("Choose entities that exist in this workspace.")).toBeNull();
  });

  it("a problem's errors are placed by the member they name; what names no field is left for the banner", () => {
    const problem = new ApiProblem({
      type: "https://erev.dev/problems/validation-failed",
      slug: "validation-failed",
      title: "Check the highlighted fields",
      status: 422,
      detail: null,
      code: null,
      requestId: null,
      errors: [
        refusal("scopes.2", "The third scope is unknown."),
        refusal("scopes[0]", "The first scope is unknown."),
        refusal("expires_at", "Choose an expiry in the future."),
        refusal("labels", "Labels are not accepted."),
        { ...refusal("", "No field at all."), field: null },
      ],
    });
    const members = { scopes: ["scopes"], expires: ["expires_at"], name: ["name"] } as const;
    expect(placeProblem(problem, members)).toEqual({
      // The first message of a field wins; an index is no part of the member.
      fields: {
        scopes: "The third scope is unknown.",
        expires: "Choose an expiry in the future.",
        name: null,
      },
      // A further, different message of a field that shows one is the banner's, so that it is not
      // shown nowhere (docs/dev-guide.md DG-FE-06 rev 1.265; this list held "Labels are not accepted."
      // alone). A message without a field is the banner's already; it is not listed twice.
      unplaced: ["The first scope is unknown.", "Labels are not accepted."],
    });
    expect(placeProblem(null, members)).toEqual({
      fields: { scopes: null, expires: null, name: null },
      unplaced: [],
    });
  });

  it("Rotate secret states the consequence, rotates and opens the one-time dialog; Revoke states the consequence, requires a reason and posts the revocation", async () => {
    installClipboard();
    const rotations: unknown[] = [];
    const revocations: unknown[] = [];
    serve({ clients: [SALESFORCE, NETSUITE] });
    server.use(
      http.post(apiUrl(`/api/v1/api-clients/${SALESFORCE.id}/rotate-secret`), () => {
        rotations.push(true);
        return HttpResponse.json({
          ...SALESFORCE,
          secret_rotated_at: "2026-09-19T10:00:00Z",
          client_secret: "erevs_Rotated-Secret-Value-fedcba9876543210",
        });
      }),
      http.post(apiUrl(`/api/v1/api-clients/${NETSUITE.id}/revoke`), async ({ request }) => {
        revocations.push(await request.json());
        return HttpResponse.json({ ...NETSUITE, status: "REVOKED" });
      }),
    );
    renderDeveloper();

    const grid = await findGrid("SF-16-grid-api-clients", "API clients");
    const salesforce = await within(grid).findByTestId("SF-16-row-svc-salesforce");
    fireEvent.click(within(salesforce).getByRole("button", { name: "Rotate secret" }));
    const rotate = await screen.findByRole("alertdialog", {
      name: "Rotate the secret of svc-salesforce?",
    });
    expect(within(rotate).getByText("The current secret stops working immediately.")).toBeTruthy();
    fireEvent.click(within(rotate).getByRole("button", { name: "Rotate secret" }));
    const secret = await screen.findByRole("dialog", { name: "Client secret for svc-salesforce" });
    expect(rotations).toHaveLength(1);
    expect(within(secret).getByText("Client secret, hidden")).toBeTruthy();
    expect(await screen.findByText("Rotated the secret of svc-salesforce.")).toBeTruthy();
    fireEvent.click(within(secret).getByRole("checkbox", { name: "I have stored this secret" }));
    fireEvent.click(within(secret).getByRole("button", { name: "Done" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Client secret for svc-salesforce" })).toBeNull();
    });

    const netsuite = within(grid).getByTestId("SF-16-row-svc-netsuite");
    fireEvent.click(within(netsuite).getByRole("button", { name: "Revoke" }));
    const revoke = await screen.findByRole("dialog", { name: "Revoke svc-netsuite?" });
    expect(
      within(revoke).getByText("Tokens of svc-netsuite stop working immediately."),
    ).toBeTruthy();
    fireEvent.click(within(revoke).getByRole("button", { name: "Revoke API client" }));
    expect(await within(revoke).findByText(/at least 10 characters/)).toBeTruthy();
    expect(revocations).toHaveLength(0);
    fireEvent.change(within(revoke).getByRole("textbox", { name: /Reason/ }), {
      target: { value: "Integration decommissioned in September" },
    });
    fireEvent.click(within(revoke).getByRole("button", { name: "Revoke API client" }));
    expect(await screen.findByText("Revoked svc-netsuite.")).toBeTruthy();
    expect(revocations).toEqual([{ reason: "Integration decommissioned in September" }]);
  });

  it("Revoke shows the server's refusal of the reason at the reason field", async () => {
    serve({ clients: [NETSUITE] });
    server.use(
      http.post(apiUrl(`/api/v1/api-clients/${NETSUITE.id}/revoke`), () =>
        // The schema's own limit (4,000 characters) answers through the request validation.
        refused([refusal("reason", "String should have at most 4000 characters")]),
      ),
    );
    renderDeveloper();
    const grid = await findGrid("SF-16-grid-api-clients", "API clients");
    fireEvent.click(
      within(await within(grid).findByTestId("SF-16-row-svc-netsuite")).getByRole("button", {
        name: "Revoke",
      }),
    );
    const revoke = await screen.findByRole("dialog", { name: "Revoke svc-netsuite?" });
    const reason = within(revoke).getByRole("textbox", { name: /Reason/ });
    fireEvent.change(reason, { target: { value: "Integration decommissioned in September" } });
    fireEvent.click(within(revoke).getByRole("button", { name: "Revoke API client" }));
    expect(
      await within(revoke).findByText("String should have at most 4000 characters"),
    ).toBeTruthy();
    expect(reason.getAttribute("aria-invalid")).toBe("true");
    expect(descriptionsOf(reason)).toContain("String should have at most 4000 characters");
    // Edited, the field drops the message about the value that was sent.
    fireEvent.change(reason, { target: { value: "Integration decommissioned" } });
    expect(within(revoke).queryByText("String should have at most 4000 characters")).toBeNull();
  });

  it("the webhooks tab lists endpoints and deliveries with the E-97 chips, filters deliveries by status, and creates an endpoint with the dialog Signing secret for <URL>", async () => {
    installClipboard();
    const bodies: unknown[] = [];
    serve({ endpoints: [ENDPOINT, PAUSED], deliveries: [DELIVERED, FAILING, QUEUED] });
    server.use(
      http.post(apiUrl("/api/v1/webhook-endpoints"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(
          {
            id: "f7f7f7f7-f7f7-4f7f-8f7f-f7f7f7f7f7f7",
            url: "https://new.example.test/erev",
            description: null,
            event_kinds: ["import.committed"],
            is_active: true,
            row_version: 1,
            created_at: "2026-09-19T10:00:00Z",
            updated_at: "2026-09-19T10:00:00Z",
            signing_secret: "whsec_Signing-Secret-Value-0123456789",
          },
          { status: 201 },
        );
      }),
    );
    renderDeveloper("/settings/developer?pane=webhooks");

    const endpoints = await findGrid("SF-16-grid-webhooks", "Webhook endpoints");
    const headers = within(endpoints)
      .getAllByRole("columnheader")
      .map((header) => header.textContent?.trim() ?? "");
    for (const name of ["URL", "Description", "Events", "Active", "Created"]) {
      expect(headers.some((header) => header.startsWith(name))).toBe(true);
    }
    const active = await within(endpoints).findByTestId(`SF-16-row-endpoint-${ENDPOINT.id}`);
    expect(within(active).getByText("https://hooks.example.test/erev/events")).toBeTruthy();
    expect(within(active).getByText("Finance data lake")).toBeTruthy();
    expect(within(active).getByText("run.completed, period.locked")).toBeTruthy();
    expect(within(active).getByText("Yes")).toBeTruthy();
    expect(within(active).getByText("20 Aug 2026 10:00 UTC")).toBeTruthy();
    expect(within(active).getByRole("button", { name: "Deactivate" })).toBeTruthy();
    const paused = within(endpoints).getByTestId(`SF-16-row-endpoint-${PAUSED.id}`);
    expect(within(paused).getByText("No")).toBeTruthy();
    const activate = within(paused).getByRole("button", { name: "Activate" });
    expect(activate.getAttribute("aria-disabled")).toBeNull();

    const deliveries = await findGrid("SF-16-grid-webhook-deliveries", "Deliveries");
    const deliveryHeaders = within(deliveries)
      .getAllByRole("columnheader")
      .map((header) => header.textContent?.trim() ?? "");
    for (const name of [
      "Endpoint",
      "Event",
      "Status",
      "Attempts",
      "Next attempt",
      "Last response",
      "Last error",
      "Succeeded",
    ]) {
      expect(deliveryHeaders.some((header) => header.startsWith(name))).toBe(true);
    }
    const delivered = await within(deliveries).findByTestId(`SF-16-row-delivery-${DELIVERED.id}`);
    expect(within(delivered).getByText("Succeeded")).toBeTruthy();
    expect(within(delivered).getByText("https://hooks.example.test")).toBeTruthy();
    expect(within(delivered).getByText("19 Sep 2026 10:00 UTC")).toBeTruthy();
    const failing = within(deliveries).getByTestId(`SF-16-row-delivery-${FAILING.id}`);
    expect(within(failing).getByText("Failed")).toBeTruthy();
    expect(within(failing).getByText("period.locked")).toBeTruthy();
    expect(within(failing).getByText("3")).toBeTruthy();
    expect(within(failing).getByText("503")).toBeTruthy();
    expect(within(failing).getByText("upstream unavailable")).toBeTruthy();
    expect(within(failing).getByText("19 Sep 2026 11:00 UTC")).toBeTruthy();
    const queued = within(deliveries).getByTestId(`SF-16-row-delivery-${QUEUED.id}`);
    expect(within(queued).getByText("Queued")).toBeTruthy();
    expect(urlPrefix("https://hooks.example.test/erev/events")).toBe("https://hooks.example.test");
    expect(acceptableWebhookUrl("http://127.0.0.1:8190/hook")).toBe(true);
    expect(acceptableWebhookUrl("http://hooks.example.test/hook")).toBe(false);

    // New webhook endpoint: "Use an https URL." and at least one event.
    fireEvent.click(screen.getByRole("button", { name: "New webhook endpoint" }));
    const drawer = await screen.findByRole("dialog", { name: "New webhook endpoint" });
    const form = within(drawer).getByTestId("SF-16-drawer-webhook-endpoint");
    fireEvent.change(within(form).getByRole("textbox", { name: "URL" }), {
      target: { value: "http://new.example.test/erev" },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Create endpoint" }));
    expect(await within(form).findAllByText("Use an https URL.")).toHaveLength(2);
    expect(within(form).getByText("Choose at least one event.")).toBeTruthy();
    expect(bodies).toHaveLength(0);
    fireEvent.change(within(form).getByRole("textbox", { name: "URL" }), {
      target: { value: "https://new.example.test/erev" },
    });
    fireEvent.click(within(form).getByRole("checkbox", { name: "import.committed" }));
    fireEvent.click(within(drawer).getByRole("button", { name: "Create endpoint" }));

    const secret = await screen.findByRole("dialog", {
      name: "Signing secret for https://new.example.test/erev",
    });
    expect(bodies).toEqual([
      { url: "https://new.example.test/erev", event_kinds: ["import.committed"] },
    ]);
    expect(
      within(secret).getByText("This secret is shown once. It cannot be shown again."),
    ).toBeTruthy();
    expect(within(secret).getByText("Signing secret, hidden")).toBeTruthy();
    expect(within(secret).queryByText("whsec_Signing-Secret-Value-0123456789")).toBeNull();
    fireEvent.click(within(secret).getByRole("button", { name: "Show" }));
    expect(within(secret).getByText("whsec_Signing-Secret-Value-0123456789")).toBeTruthy();
    expect(within(secret).getByRole("button", { name: "Done" }).getAttribute("aria-disabled")).toBe(
      "true",
    );
    fireEvent.click(within(secret).getByRole("checkbox", { name: "I have stored this secret" }));
    fireEvent.click(within(secret).getByRole("button", { name: "Done" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /Signing secret/ })).toBeNull();
    });
  });

  it("New webhook endpoint shows the server's refusals at URL, Description and Events", async () => {
    const urlRule = "Enter an https URL, or http://127.0.0.1 or http://localhost with a path.";
    serve({ endpoints: [ENDPOINT] });
    server.use(
      http.post(apiUrl("/api/v1/webhook-endpoints"), () =>
        refused([
          refusal("url", urlRule),
          refusal("description", "A description has at most 400 characters."),
          refusal("event_kinds", "Choose one or more of run.completed, import.committed."),
        ]),
      ),
    );
    renderDeveloper("/settings/developer?pane=webhooks");
    await findGrid("SF-16-grid-webhooks", "Webhook endpoints");
    fireEvent.click(screen.getByRole("button", { name: "New webhook endpoint" }));
    const drawer = await screen.findByRole("dialog", { name: "New webhook endpoint" });
    const form = within(drawer).getByTestId("SF-16-drawer-webhook-endpoint");
    const url = within(form).getByRole("textbox", { name: "URL" });
    // Credentials in the URL pass the screen's own check and are refused by the server.
    fireEvent.change(url, { target: { value: "https://user:secret@new.example.test/erev" } });
    const description = within(form).getByRole("textbox", { name: /^Description/ });
    fireEvent.change(description, { target: { value: "Finance data lake" } });
    fireEvent.click(within(form).getByRole("checkbox", { name: "import.committed" }));
    fireEvent.click(within(drawer).getByRole("button", { name: "Create endpoint" }));

    const alert = await within(drawer).findByRole("alert");
    expect(
      within(alert).getByRole("heading", { name: "Check the highlighted fields" }),
    ).toBeTruthy();
    expect(url.getAttribute("aria-invalid")).toBe("true");
    expect(descriptionsOf(url)).toContain(urlRule);
    expect(description.getAttribute("aria-invalid")).toBe("true");
    expect(descriptionsOf(description)).toContain("A description has at most 400 characters.");
    expect(descriptionsOf(within(form).getByRole("group", { name: "Events" }))).toContain(
      "Choose one or more of run.completed, import.committed.",
    );
    expect(within(alert).queryByText(urlRule)).toBeNull();
    // Edited, a field drops the message about the value that was sent.
    fireEvent.change(description, { target: { value: "Data lake" } });
    expect(within(form).queryByText("A description has at most 400 characters.")).toBeNull();
    expect(descriptionsOf(url)).toContain(urlRule);
  });

  it("Deactivate and Activate patch is_active with If-Match; in a sandbox tenant activation is aria-disabled with the SB-R-08 reason", async () => {
    const patches: { readonly ifMatch: string | null; readonly body: unknown }[] = [];
    serve({ endpoints: [ENDPOINT, PAUSED] });
    server.use(
      http.patch(apiUrl(`/api/v1/webhook-endpoints/${ENDPOINT.id}`), async ({ request }) => {
        patches.push({ ifMatch: request.headers.get("If-Match"), body: await request.json() });
        return HttpResponse.json({ ...ENDPOINT, is_active: false, row_version: 4 });
      }),
    );
    renderDeveloper("/settings/developer?pane=webhooks");

    const endpoints = await findGrid("SF-16-grid-webhooks", "Webhook endpoints");
    const active = await within(endpoints).findByTestId(`SF-16-row-endpoint-${ENDPOINT.id}`);
    fireEvent.click(within(active).getByRole("button", { name: "Deactivate" }));
    expect(
      await screen.findByText("Deactivated https://hooks.example.test/erev/events."),
    ).toBeTruthy();
    expect(patches).toEqual([{ ifMatch: '"r3"', body: { is_active: false } }]);
    cleanup();

    serve({ endpoints: [ENDPOINT, PAUSED] });
    renderDeveloper(
      "/settings/developer?pane=webhooks",
      TOMAS,
      signedInSession({
        active_tenant: {
          id: "1c1c1c1c-1c1c-4c1c-8c1c-1c1c1c1c1c1c",
          code: "avenmoor-sbx",
          display_name: "Avenmoor sandbox",
          kind: "sandbox",
        },
      }),
    );
    const grid = await findGrid("SF-16-grid-webhooks", "Webhook endpoints");
    const paused = await within(grid).findByTestId(`SF-16-row-endpoint-${PAUSED.id}`);
    const activate = within(paused).getByRole("button", { name: "Activate" });
    expect(activate.getAttribute("aria-disabled")).toBe("true");
    fireEvent.focus(activate);
    // Within the row: the toolbar's "New webhook endpoint" carries the same reason in a sandbox.
    expect(
      await within(paused).findByText("Sandbox workspaces cannot post or export journals."),
    ).toBeTruthy();
    // Deactivation stays available in a sandbox.
    const running = within(grid).getByTestId(`SF-16-row-endpoint-${ENDPOINT.id}`);
    expect(
      within(running).getByRole("button", { name: "Deactivate" }).getAttribute("aria-disabled"),
    ).toBeNull();
  });

  it("in a sandbox tenant New webhook endpoint is aria-disabled with the SB-R-08 reason, opens no drawer and sends no command; the empty state offers no action", async () => {
    // 05 SBX-08 (security finding SF-1): an endpoint is created active, so the server answers 403
    // `sandbox-restricted` to the command; the control says so instead of offering it.
    const sandboxSession = signedInSession({
      active_tenant: {
        id: "1c1c1c1c-1c1c-4c1c-8c1c-1c1c1c1c1c1c",
        code: "avenmoor-sbx",
        display_name: "Avenmoor sandbox",
        kind: "sandbox",
      },
    });
    const created: unknown[] = [];
    serve({ endpoints: [PAUSED] });
    server.use(
      http.post(apiUrl("/api/v1/webhook-endpoints"), async ({ request }) => {
        created.push(await request.json());
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    renderDeveloper("/settings/developer?pane=webhooks", TOMAS, sandboxSession);

    const grid = await findGrid("SF-16-grid-webhooks", "Webhook endpoints");
    await within(grid).findByTestId(`SF-16-row-endpoint-${PAUSED.id}`);
    const create = screen.getByRole("button", { name: "New webhook endpoint" });
    expect(create.getAttribute("aria-disabled")).toBe("true");
    expect(reasonOf(create)).toBe("Sandbox workspaces cannot post or export journals.");
    fireEvent.click(create);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(created).toEqual([]);
    cleanup();

    // The empty state names what belongs here and offers no action in a sandbox.
    serve({});
    renderDeveloper("/settings/developer?pane=webhooks", TOMAS, sandboxSession);
    const empty = await screen.findByTestId("SF-16-empty-webhooks");
    expect(within(empty).getByRole("heading", { name: "No webhook endpoints" })).toBeTruthy();
    expect(within(empty).queryByRole("button")).toBeNull();
    const only = screen.getByRole("button", { name: "New webhook endpoint" });
    expect(only.getAttribute("aria-disabled")).toBe("true");
    expect(reasonOf(only)).toBe("Sandbox workspaces cannot post or export journals.");
    cleanup();

    // In a production tenant both controls are offered (the positive control).
    serve({});
    renderDeveloper("/settings/developer?pane=webhooks");
    const offered = await screen.findByTestId("SF-16-empty-webhooks");
    expect(
      within(offered)
        .getByRole("button", { name: "New webhook endpoint" })
        .getAttribute("aria-disabled"),
    ).toBeNull();
  });

  it("the OpenAPI tab shows the base URL, the token endpoint, the rate limit and the document link; the empty webhooks state reads No webhook endpoints", async () => {
    serve({});
    renderDeveloper("/settings/developer?pane=openapi");

    const pane = await screen.findByTestId("SF-16-pane-openapi");
    expect(within(pane).getByText(`API base URL ${window.location.origin}/api/v1`)).toBeTruthy();
    expect(
      within(pane).getByText(
        "Token endpoint POST /api/v1/oauth/token (client credentials, HTTP Basic client authentication); tokens last 60 minutes.",
      ),
    ).toBeTruthy();
    expect(
      within(pane).getByText("Rate limit: 600 requests per minute per API client (default 600)."),
    ).toBeTruthy();
    const link = within(pane).getByRole("link", { name: "Download the OpenAPI document (JSON)" });
    expect(link.getAttribute("href")).toBe("/api/v1/openapi.json");
    expect(screen.getByRole("tab", { name: "OpenAPI" }).getAttribute("aria-selected")).toBe("true");

    fireEvent.click(screen.getByRole("tab", { name: "Webhooks" }));
    const empty = await screen.findByTestId("SF-16-empty-webhooks");
    expect(within(empty).getByRole("heading", { name: "No webhook endpoints" })).toBeTruthy();
    expect(
      within(empty).getByText(
        "Endpoints receive signed notifications with resource ids only, never amounts or personal data.",
      ),
    ).toBeTruthy();
  });
});
