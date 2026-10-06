// @vitest-environment jsdom
// SF-13:accounting and SF-13:accounting-version (BUILD_SPEC RFD-23; SCREENS §11.3): "Apply legacy-parity
// preset" opens the dialog and posts `POST /policies/presets/legacy-parity {scope: "TENANT"}`; the version
// editor's grid "Policy parameters" shows the lock "Forced by the framework" and no editable control on a
// forced row, the proposed-value control "<key>, proposed value" on the others, and "Save values" patches
// the version with `If-Match`. 04 SC-V `effective_from` and `effective_to` are instants (API-S-Policy
// "datetime or null"): the grid, the lifecycle caption and the Effective from field show their UTC date.
// A version holds the whole value set of its category (04 T-PLT-32, §16.5 rev 1.183; SCREENS §11.3):
// "New policy version" sends `basis: "DEFAULTS"` when "Start from the current published values" is
// unticked, and the Proposed column reads the default for a key the version returns to the default.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import {
  currentPublished,
  filterRows,
  formatLiteral,
  parameterRows,
  parseLiteral,
  type Policy,
  proposedValue,
  type RegistryParameter,
  valueControl,
} from "../../lib/api/queries/policies";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, heldRead, installMswServer, problemResponse, server } from "../../test/msw";
import { describedBy, REFUSAL_REFERENCE, REFUSAL_TITLE, refusedWith } from "../../test/refusals";
import { presetLabel, scopeLabel } from "./accounting";
import { testEvidence } from "./accounting-version";

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

const MAYA = signedInMe({ permissions: ["config.read", "config.author"] });
const MARCUS = signedInMe({ permissions: ["config.read", "config.approve"] });

function parameter(
  overrides: Partial<RegistryParameter> &
    Pick<RegistryParameter, "code" | "pol_id" | "description">,
): RegistryParameter {
  return {
    category: "ACCOUNTING_POLICY",
    section: "Posting and books",
    allowed_levels: ["TENANT"],
    approval_code: "CFG",
    pin: "P",
    default_asc606: "ERP",
    default_ifrs15: "ERP",
    legacy_parity_value: "ERP",
    is_forced_asc606: false,
    is_forced_ifrs15: false,
    source_ref: "POLICIES §1.2",
    value_schema: { type: "string", enum: ["ERP", "EREV"] },
    ...overrides,
  };
}
const BILLING_POSTING = parameter({
  code: "billing.posting",
  pol_id: "POL-004",
  description: "Who posts invoices to the general ledger?",
});
const JE_POSTING_MODE = parameter({
  code: "je.posting_mode",
  pol_id: "POL-005",
  description: "Does the GL receive full journal detail or summarised lines?",
  default_asc606: "GROSS",
  default_ifrs15: "GROSS",
  legacy_parity_value: "GROSS",
  value_schema: { type: "string", enum: ["GROSS", "NET"] },
});
const ROUNDING = parameter({
  code: "rounding.posting_mode",
  pol_id: "POL-001",
  description: "How are posted amounts rounded?",
  section: "Rounding",
  pin: "K",
  approval_code: "FIX",
  default_asc606: "HALF_UP",
  default_ifrs15: "HALF_UP",
  legacy_parity_value: null,
  is_forced_asc606: true,
  is_forced_ifrs15: true,
  value_schema: { type: "string", enum: ["HALF_UP"] },
});
const PLATFORM_PARAM = parameter({
  code: "platform.session_idle_minutes",
  pol_id: null,
  description: "Idle timeout",
  category: "PLATFORM",
  section: "Platform",
  default_asc606: 30,
  default_ifrs15: 30,
  legacy_parity_value: null,
  value_schema: { type: "integer" },
});

function policy(overrides: Partial<Policy> & Pick<Policy, "id" | "version_no" | "status">): Policy {
  return {
    category: "ACCOUNTING_POLICY",
    scope: "TENANT",
    entity_code: null,
    entity_id: null,
    book: null,
    preset_code: null,
    values: {},
    unset: [],
    diff_against_current: [],
    effective_from: null,
    effective_to: null,
    approval_request_id: null,
    pending_approval_request_id: null,
    content_sha256: null,
    impact_simulation: null,
    test_evidence: null,
    published_at: null,
    published_by: null,
    supersedes_version_id: null,
    created_by: {
      id: "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a",
      kind: "USER",
      display_name: "Maya Chen",
    },
    row_version: 3,
    created_at: "2026-09-10T08:00:00Z",
    updated_at: "2026-09-12T08:00:00Z",
    ...overrides,
  };
}
const MARCUS_WEBB: Policy["published_by"] = {
  id: "7e3f9b2c-4d6a-4e8b-a1c3-5d7f9b1e3a5c",
  kind: "USER",
  display_name: "Marcus Webb",
};
const PUBLISHED = policy({
  id: "b2b2b2b2-b2b2-4b2b-8b2b-b2b2b2b2b2b2",
  version_no: 2,
  status: "PUBLISHED",
  values: { "billing.posting": "ERP", "je.posting_mode": "GROSS" },
  effective_from: "2023-01-01T12:00:00Z",
  published_at: "2026-01-05T09:00:00Z",
  published_by: MARCUS_WEBB,
  preset_code: "LEGACY_PARITY",
  row_version: 6,
});
const SUPERSEDED = policy({
  id: "a1a1a1a1-a1a1-4a1a-8a1a-a1a1a1a1a1a1",
  version_no: 1,
  status: "SUPERSEDED",
  effective_from: "2022-01-01T12:00:00Z",
  effective_to: "2023-01-01T12:00:00Z",
  published_at: "2021-12-20T09:00:00Z",
  published_by: MARCUS_WEBB,
  row_version: 4,
});
const DRAFT = policy({
  id: "d3d3d3d3-d3d3-4d3d-8d3d-d3d3d3d3d3d3",
  version_no: 3,
  status: "DRAFT",
  preset_code: "LEGACY_PARITY",
  values: {
    "billing.posting": "ERP",
    "je.posting_mode": "NET",
    "rounding.posting_mode": "HALF_UP",
  },
  diff_against_current: [
    { code: "je.posting_mode", before: "GROSS", after: "NET", change: "CHANGED" },
  ],
  test_evidence: { passed: 3, total: 3 },
  supersedes_version_id: PUBLISHED.id,
});

function serve(policies: readonly Policy[]) {
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/books"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/periods"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/saved-views"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/policies"), ({ request }) =>
      HttpResponse.json(
        { items: policies, next_cursor: null },
        {
          headers:
            new URL(request.url).searchParams.get("count") === "true"
              ? { "X-Erev-Total-Count": String(policies.length) }
              : {},
        },
      ),
    ),
    http.get(apiUrl("/api/v1/policies/:policyId"), ({ params }) => {
      const found = policies.find((item) => item.id === params.policyId);
      return found === undefined
        ? problemResponse("not-found", 404, "Not found")
        : HttpResponse.json(found);
    }),
    http.get(apiUrl("/api/v1/registry/parameters"), () =>
      HttpResponse.json({
        items: [BILLING_POSTING, JE_POSTING_MODE, ROUNDING, PLATFORM_PARAM],
        next_cursor: null,
      }),
    ),
  );
}

const REQUEST_ID = "e4e4e4e4-e4e4-4e4e-8e4e-e4e4e4e4e4e4";
// PRD ERR-92 as the API words it (`registry_versions.BASIS_SUPERSEDED`), for version 4.
const BASIS_SUPERSEDED =
  "Version 4 was published after this version was submitted. Create a new version: it starts from the published values.";

/** `GET /approvals/{id}`: the request of a version Maya submitted. */
function serveRequest() {
  server.use(
    http.get(apiUrl("/api/v1/approvals/:requestId"), () =>
      HttpResponse.json({
        id: REQUEST_ID,
        preparer: { id: MAYA.user.id, display_name: "Maya Chen", kind: "USER" },
        steps: [],
      }),
    ),
  );
}

describe("SF-13:accounting", () => {
  it("apply legacy-parity preset modal", async () => {
    const bodies: unknown[] = [];
    serve([PUBLISHED]);
    server.use(
      http.post(apiUrl("/api/v1/policies/presets/legacy-parity"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(DRAFT, { status: 201 });
      }),
    );
    const { router } = renderApp("/policies/accounting", { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-13-grid-policy-versions")).findByRole(
      "grid",
      { name: "Policy versions" },
    );
    const row = await within(grid).findByTestId("SF-13-row-accounting-policy-tenant-2");
    expect(
      within(row).getByRole("link", { name: "Accounting policies" }).getAttribute("href"),
    ).toBe(`/policies/accounting/${PUBLISHED.id}`);
    expect(within(row).getByText("Tenant")).toBeTruthy();
    expect(within(row).getByText("v2")).toBeTruthy();
    expect(within(row).getByText("Published")).toBeTruthy();
    expect(within(row).getByText("Legacy parity")).toBeTruthy();
    expect(within(row).getByText("01 Jan 2023")).toBeTruthy();
    expect(within(row).getByText("Maya Chen")).toBeTruthy();
    expect(within(row).getByText("Marcus Webb")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Apply legacy-parity preset" }));
    const dialog = await screen.findByRole("dialog", { name: "Apply legacy-parity preset" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create draft" }));

    expect(await screen.findByText("Created the legacy-parity draft.")).toBeTruthy();
    expect(bodies).toEqual([{ scope: "TENANT" }]);
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/policies/accounting/${DRAFT.id}`),
    );
    expect(presetLabel("INDUSTRY_SAAS")).toBe("Industry template SAAS");
    expect(scopeLabel({ scope: "BOOK", entity_code: null, book: "IFRS15" })).toBe("Book IFRS 15");
    expect(scopeLabel({ scope: "ENTITY", entity_code: "AVM-DE", book: null })).toBe(
      "Entity AVM-DE",
    );
  });

  it("the grid shows the UTC date of the effective instants and no value for an open end", async () => {
    serve([PUBLISHED, SUPERSEDED]);
    renderApp("/policies/accounting", { me: MARCUS, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-13-grid-policy-versions")).findByRole(
      "grid",
      { name: "Policy versions" },
    );
    const cell = (row: HTMLElement, column: string) =>
      row.querySelector<HTMLElement>(`[data-column="${column}"]`);
    const superseded = await within(grid).findByTestId("SF-13-row-accounting-policy-tenant-1");
    expect(cell(superseded, "effective_from")?.textContent).toBe("01 Jan 2022");
    expect(cell(superseded, "effective_to")?.textContent).toBe("01 Jan 2023");
    const published = within(grid).getByTestId("SF-13-row-accounting-policy-tenant-2");
    expect(cell(published, "effective_from")?.textContent).toBe("01 Jan 2023");
    // DS-FMT-08: an open end is the em dash with the accessible text "No value".
    const open = cell(published, "effective_to");
    expect(open === null ? null : within(open).getByText("No value")).toBeTruthy();
  });

  it.each([
    {
      name: "ticked, the draft states the published values and no basis",
      untick: false,
      body: {
        category: "ACCOUNTING_POLICY",
        scope: "TENANT",
        entity_code: null,
        book: null,
        values: { "billing.posting": "ERP", "je.posting_mode": "GROSS" },
      },
    },
    {
      name: "unticked, the values sent are the whole set: basis DEFAULTS",
      untick: true,
      body: {
        category: "ACCOUNTING_POLICY",
        scope: "TENANT",
        entity_code: null,
        book: null,
        values: {},
        basis: "DEFAULTS",
      },
    },
  ])("New policy version: $name", async ({ untick, body }) => {
    const bodies: unknown[] = [];
    serve([PUBLISHED]);
    server.use(
      http.post(apiUrl("/api/v1/policies"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(DRAFT, { status: 201 });
      }),
    );
    const { router } = renderApp("/policies/accounting", { me: MAYA, screenRoutes: SCREEN_ROUTES });

    await within(await screen.findByTestId("SF-13-grid-policy-versions")).findByTestId(
      "SF-13-row-accounting-policy-tenant-2",
    );
    fireEvent.click(screen.getByRole("button", { name: "New policy version" }));
    const drawer = await screen.findByRole("dialog", { name: "New policy version" });
    fireEvent.click(within(drawer).getByRole("combobox", { name: /^Category/ }));
    fireEvent.mouseDown(await screen.findByRole("option", { name: "Accounting policies" }));
    const start = within(drawer).getByRole("checkbox", {
      name: "Start from the current published values",
    }) as HTMLInputElement;
    expect(start.checked).toBe(true);
    if (untick) {
      fireEvent.click(start);
    }
    fireEvent.click(within(drawer).getByRole("button", { name: "Create version" }));

    expect(await screen.findByText("Created policy version v3 as a draft.")).toBeTruthy();
    expect(bodies).toEqual([body]);
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/policies/accounting/${DRAFT.id}`),
    );
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): a message that names a member no
  // field on screen sends was shown nowhere — the entity and the book are asked for their scope only,
  // and the values a draft starts from have no field. What a field shows is not said by the banner.
  it("New policy version under a refused command: the banner lists what no field on screen shows", async () => {
    const notOnScreen = "Choose the entity this version applies to.";
    const noField = "A published value names a parameter that was retired.";
    const atCategory = "A draft of this category and scope exists.";
    serve([PUBLISHED]);
    server.use(
      http.post(apiUrl("/api/v1/policies"), () =>
        refusedWith({
          entity_code: notOnScreen,
          "values.rounding.posting_mode": noField,
          category: atCategory,
        }),
      ),
    );
    renderApp("/policies/accounting", { me: MAYA, screenRoutes: SCREEN_ROUTES });
    await within(await screen.findByTestId("SF-13-grid-policy-versions")).findByTestId(
      "SF-13-row-accounting-policy-tenant-2",
    );
    fireEvent.click(screen.getByRole("button", { name: "New policy version" }));
    const drawer = await screen.findByRole("dialog", { name: "New policy version" });
    const category = within(drawer).getByRole("combobox", { name: /^Category/ });
    fireEvent.click(category);
    fireEvent.mouseDown(await screen.findByRole("option", { name: "Accounting policies" }));
    fireEvent.click(within(drawer).getByRole("button", { name: "Create version" }));

    const banner = await within(drawer).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + notOnScreen + noField + REFUSAL_REFERENCE);
    expect(describedBy(category)).toContain(atCategory);
  });

  it("Apply legacy-parity preset under a refused command: the banner lists what no field on screen shows", async () => {
    const notOnScreen = "Choose the book this preset applies to.";
    const atScope = "A legacy-parity draft of this scope exists.";
    serve([PUBLISHED]);
    server.use(
      http.post(apiUrl("/api/v1/policies/presets/legacy-parity"), () =>
        refusedWith({ book: notOnScreen, scope: atScope }),
      ),
    );
    renderApp("/policies/accounting", { me: MAYA, screenRoutes: SCREEN_ROUTES });
    await within(await screen.findByTestId("SF-13-grid-policy-versions")).findByTestId(
      "SF-13-row-accounting-policy-tenant-2",
    );
    fireEvent.click(screen.getByRole("button", { name: "Apply legacy-parity preset" }));
    const dialog = await screen.findByRole("dialog", { name: "Apply legacy-parity preset" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create draft" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + notOnScreen + REFUSAL_REFERENCE);
    expect(describedBy(within(dialog).getByRole("combobox", { name: /^Scope/ }))).toContain(
      atScope,
    );
  });

  it.each([
    {
      name: "New policy version",
      path: "/api/v1/policies",
      submit: "Create version",
      pick: true,
    },
    {
      name: "Apply legacy-parity preset",
      path: "/api/v1/policies/presets/legacy-parity",
      submit: "Create draft",
      pick: false,
    },
  ])(
    "$name refused while another version of the scope is open says why",
    async ({ name, path, submit, pick }) => {
      // PRD SM-04 as the API words it (`registry.presets.VERSION_OPEN`): the sentence sits on
      // `status`, a member neither form has a field for, and the problem carries no detail.
      const open = "Another version is open. Finish it or withdraw it first.";
      serve([PUBLISHED, DRAFT]);
      server.use(
        http.post(apiUrl(path), () =>
          problemResponse("invalid-transition", 409, "Action not available in this state", {
            errors: [{ field: "status", rule_id: "SM-04", message: open }],
          }),
        ),
      );
      renderApp("/policies/accounting", { me: MAYA, screenRoutes: SCREEN_ROUTES });

      await within(await screen.findByTestId("SF-13-grid-policy-versions")).findByTestId(
        "SF-13-row-accounting-policy-tenant-2",
      );
      fireEvent.click(screen.getByRole("button", { name }));
      const dialog = await screen.findByRole("dialog", { name });
      if (pick) {
        fireEvent.click(within(dialog).getByRole("combobox", { name: /^Category/ }));
        fireEvent.mouseDown(await screen.findByRole("option", { name: "Accounting policies" }));
      }
      fireEvent.click(within(dialog).getByRole("button", { name: submit }));

      expect(await within(dialog).findByText("Action not available in this state")).toBeTruthy();
      expect(within(dialog).getAllByText(open)).toHaveLength(1);
    },
  );

  it("an approver without config.author sees the list without authoring actions", async () => {
    serve([PUBLISHED]);
    renderApp("/policies/accounting", { me: MARCUS, screenRoutes: SCREEN_ROUTES });

    await within(await screen.findByTestId("SF-13-grid-policy-versions")).findByRole("grid", {
      name: "Policy versions",
    });
    expect(screen.queryByRole("button", { name: "Apply legacy-parity preset" })).toBeNull();
    expect(screen.queryByRole("button", { name: "New policy version" })).toBeNull();
  });
});

describe("SF-13:accounting-version", () => {
  it("forced rows show lock", async () => {
    serve([PUBLISHED, DRAFT]);
    renderApp(`/policies/accounting/${DRAFT.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Accounting policies · Tenant" }),
    ).toBeTruthy();
    // The status chip and the lifecycle step both read "Draft".
    expect(screen.getAllByText("Draft").length).toBeGreaterThan(0);
    expect(screen.getByText("v3")).toBeTruthy();
    expect(screen.getAllByText("Legacy parity").length).toBeGreaterThan(0);

    const grid = await within(await screen.findByTestId("SF-13-grid-parameters")).findByRole(
      "grid",
      { name: "Policy parameters" },
    );
    const rounding = await within(grid).findByTestId("SF-13-row-rounding-posting-mode");
    expect(within(rounding).getByRole("img", { name: "Forced by the framework" })).toBeTruthy();
    expect(
      within(rounding).queryByRole("combobox", { name: "rounding.posting_mode, proposed value" }),
    ).toBeNull();
    expect(
      within(rounding).queryByRole("textbox", { name: "rounding.posting_mode, proposed value" }),
    ).toBeNull();
    expect(within(rounding).getByText("At inception")).toBeTruthy();
    expect(within(rounding).getByText("n/a")).toBeTruthy();

    const billing = within(grid).getByTestId("SF-13-row-billing-posting");
    const proposed = within(billing).getByRole("combobox", {
      name: "billing.posting, proposed value",
    }) as HTMLSelectElement;
    expect(proposed.value).toBe("ERP");
    expect(within(billing).getByText("POL-004")).toBeTruthy();
    expect(within(billing).getByText("Per posting period")).toBeTruthy();
    // The changed row carries the neutral chip "Changed".
    const je = within(grid).getByTestId("SF-13-row-je-posting-mode");
    expect(within(je).getByText("Changed")).toBeTruthy();
    // The platform parameter belongs to another category and is not listed.
    expect(within(grid).queryByTestId("SF-13-row-platform-session-idle-minutes")).toBeNull();

    // Pure helpers.
    const rows = parameterRows(
      [BILLING_POSTING, JE_POSTING_MODE, ROUNDING, PLATFORM_PARAM],
      DRAFT,
      PUBLISHED,
    );
    expect(rows.map((row) => row.parameter.code)).toEqual([
      "billing.posting",
      "je.posting_mode",
      "rounding.posting_mode",
    ]);
    expect(rows.map((row) => row.changed)).toEqual([false, true, false]);
    expect(rows.map((row) => row.currentLevel)).toEqual(["published", "published", "default"]);
    expect(
      filterRows(rows, { q: "", section: null, changedOnly: true }).map((r) => r.parameter.code),
    ).toEqual(["je.posting_mode"]);
    expect(
      filterRows(rows, { q: "pol-001", section: null, changedOnly: false }).map(
        (r) => r.parameter.code,
      ),
    ).toEqual(["rounding.posting_mode"]);
    expect(currentPublished([PUBLISHED, DRAFT], DRAFT)?.id).toBe(PUBLISHED.id);
    expect(valueControl({ type: "integer" }).kind).toBe("number");
    expect(
      parseLiteral(
        valueControl({ type: "array", items: { type: "integer" } }),
        { type: "array", items: { type: "integer" } },
        "12, 24",
      ),
    ).toEqual([12, 24]);
    expect(formatLiteral([12, 24])).toBe("12, 24");
    expect(testEvidence(DRAFT)).toEqual({ passed: 3, total: 3 });
  });

  it("Save values patches the changed proposed values with If-Match", async () => {
    const patches: { readonly ifMatch: string | null; readonly body: unknown }[] = [];
    serve([PUBLISHED, DRAFT]);
    server.use(
      http.patch(apiUrl(`/api/v1/policies/${DRAFT.id}`), async ({ request }) => {
        patches.push({ ifMatch: request.headers.get("If-Match"), body: await request.json() });
        return HttpResponse.json({
          ...DRAFT,
          values: { ...DRAFT.values, "billing.posting": "EREV" },
          row_version: 4,
        });
      }),
    );
    renderApp(`/policies/accounting/${DRAFT.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-13-grid-parameters")).findByRole(
      "grid",
      { name: "Policy parameters" },
    );
    const billing = await within(grid).findByTestId("SF-13-row-billing-posting");
    const save = screen.getByRole("button", { name: "Save values" });
    expect(save.getAttribute("aria-disabled")).toBe("true");
    fireEvent.change(
      within(billing).getByRole("combobox", { name: "billing.posting, proposed value" }),
      {
        target: { value: "EREV" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Save values" }));

    expect(await screen.findByText("Saved Tenant v3.")).toBeTruthy();
    expect(patches).toEqual([
      {
        ifMatch: '"r3"',
        body: {
          values: {
            "billing.posting": "EREV",
            "je.posting_mode": "NET",
            "rounding.posting_mode": "HALF_UP",
          },
        },
      },
    ]);
    expect(screen.getByText("Example cases: 3 of 3 passed")).toBeTruthy();
    expect(screen.getByTestId("SF-13-pane-simulation")).toBeTruthy();
  });

  it("an emptied value returns the key to the default: Save values names it in unset", async () => {
    const window = parameter({
      code: "combination.detection_window_days",
      pol_id: "POL-030",
      description: "Within how many days are contracts of one customer combined?",
      default_asc606: 0,
      default_ifrs15: 0,
      legacy_parity_value: 0,
      value_schema: { type: "integer" },
    });
    const values = { "billing.posting": "ERP", [window.code]: 30 };
    const published = policy({ ...PUBLISHED, values });
    const draft = policy({ ...DRAFT, values, diff_against_current: [] });
    const bodies: unknown[] = [];
    serve([published, draft]);
    server.use(
      http.get(apiUrl("/api/v1/registry/parameters"), () =>
        HttpResponse.json({ items: [BILLING_POSTING, window], next_cursor: null }),
      ),
      http.patch(apiUrl(`/api/v1/policies/${draft.id}`), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({
          ...draft,
          values: { "billing.posting": "ERP" },
          unset: [window.code],
          row_version: 4,
        });
      }),
    );
    renderApp(`/policies/accounting/${draft.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-13-grid-parameters")).findByRole(
      "grid",
      { name: "Policy parameters" },
    );
    const row = await within(grid).findByTestId("SF-13-row-combination-detection-window-days");
    const input = within(row).getByRole("textbox", {
      name: "combination.detection_window_days, proposed value",
    }) as HTMLInputElement;
    expect(input.value).toBe("30");
    fireEvent.change(input, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save values" }));

    expect(await screen.findByText("Saved Tenant v3.")).toBeTruthy();
    // The published version holds the key: left out of `values` alone, the version would keep 30
    // (04 §16.5), so the editor names it in `unset`.
    expect(bodies).toEqual([{ values: { "billing.posting": "ERP" }, unset: [window.code] }]);
  });

  it("a settings version is submitted without a date; an accounting version is not", async () => {
    const close = policy({
      id: "c7c7c7c7-c7c7-4c7c-8c7c-c7c7c7c7c7c7",
      version_no: 2,
      status: "TESTED",
      category: "CLOSE",
      values: { "close.late_entry_window_days": 7 },
    });
    serve([PUBLISHED, DRAFT, close]);
    renderApp(`/policies/accounting/${close.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    expect(await screen.findByRole("heading", { level: 1, name: "Close · Tenant" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Submit" }).getAttribute("aria-disabled")).toBeNull();
    expect(
      screen.getByText(
        "Without a date the version takes effect when it is approved. Choose a date to start later.",
      ),
    ).toBeTruthy();
    cleanup();

    renderApp(`/policies/accounting/${DRAFT.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    expect(
      await screen.findByRole("heading", { level: 1, name: "Accounting policies · Tenant" }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Submit" }).getAttribute("aria-disabled")).toBe(
      "true",
    );
  });

  it("a key the version returns to the default reads its default as proposed", async () => {
    const published = policy({
      ...PUBLISHED,
      values: { "billing.posting": "ERP", "je.posting_mode": "NET" },
    });
    const returning = policy({
      id: "e4e4e4e4-e4e4-4e4e-8e4e-e4e4e4e4e4e4",
      version_no: 3,
      status: "SUBMITTED",
      values: { "billing.posting": "ERP" },
      diff_against_current: [
        { code: "je.posting_mode", before: "NET", after: null, change: "RETURNED_TO_DEFAULT" },
      ],
      supersedes_version_id: published.id,
    });
    serve([published, returning]);
    renderApp(`/policies/accounting/${returning.id}`, { me: MARCUS, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-13-grid-parameters")).findByRole(
      "grid",
      { name: "Policy parameters" },
    );
    const cell = (row: HTMLElement, column: string) =>
      row.querySelector<HTMLElement>(`[data-column="${column}"]`)?.textContent;
    // The published value is NET; the version returns the key, so the proposed value is the
    // framework default and says so. A key the version keeps reads the published value.
    const je = await within(grid).findByTestId("SF-13-row-je-posting-mode");
    expect(cell(je, "current")).toBe("NETTenant");
    expect(cell(je, "proposed")).toBe("GROSSFramework default");
    // Beside a level the value truncates as a grid text cell does, under its full text as the
    // title, and the level stays whole (the layout is checked in the browser: jsdom has none).
    // Every literal of the row carries its title (rev 1.56), so each is read in its own column.
    const inCell = (row: HTMLElement, column: string) =>
      within(row.querySelector<HTMLElement>(`[data-column="${column}"]`) as HTMLElement);
    expect(inCell(je, "current").getByTitle("NET").textContent).toBe("NET");
    expect(inCell(je, "proposed").getByTitle("GROSS").textContent).toBe("GROSS");
    expect(within(je).getByText("Changed")).toBeTruthy();
    const billing = within(grid).getByTestId("SF-13-row-billing-posting");
    expect(cell(billing, "proposed")).toBe("ERP");

    const rows = parameterRows([BILLING_POSTING, JE_POSTING_MODE, ROUNDING], returning, published);
    expect(rows.map((row) => [row.returned, proposedValue(row)])).toEqual([
      [false, "ERP"],
      [true, "GROSS"],
      [false, "HALF_UP"],
    ]);
  });

  it("a superseded version reads its own set: a key it never held is at the default, whatever is published now", async () => {
    // Version 1 held the posting alone; version 2, published since, holds the journal mode too.
    // `diff_against_current` of a version that was published is the difference IT made (04
    // §16.5): version 1 added the posting. It never held the journal mode, so its own value for
    // that key is the framework default — not the value the published version holds now.
    const now = policy({
      ...PUBLISHED,
      values: { "billing.posting": "ERP", "je.posting_mode": "NET" },
      supersedes_version_id: SUPERSEDED.id,
    });
    const earlier = policy({
      ...SUPERSEDED,
      values: { "billing.posting": "ERP" },
      diff_against_current: [
        { code: "billing.posting", before: null, after: "ERP", change: "ADDED" },
      ],
    });
    serve([now, earlier]);
    renderApp(`/policies/accounting/${earlier.id}`, { me: MARCUS, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-13-grid-parameters")).findByRole(
      "grid",
      { name: "Policy parameters" },
    );
    const cell = (row: HTMLElement, column: string) =>
      row.querySelector<HTMLElement>(`[data-column="${column}"]`)?.textContent;
    const je = await within(grid).findByTestId("SF-13-row-je-posting-mode");
    expect(cell(je, "current")).toBe("NETTenant");
    expect(cell(je, "proposed")).toBe("GROSS");
    expect(within(je).queryByText("Changed")).toBeNull();
    const billing = within(grid).getByTestId("SF-13-row-billing-posting");
    expect(cell(billing, "current")).toBe("ERPTenant");
    expect(cell(billing, "proposed")).toBe("ERP");
    expect(within(billing).getByText("Changed")).toBeTruthy();

    const whole = parameterRows([BILLING_POSTING, JE_POSTING_MODE], earlier, now);
    expect(whole.map((row) => [row.statement, row.changed, proposedValue(row)])).toEqual([
      [false, true, "ERP"],
      [false, false, "GROSS"],
    ]);
    // A statement keeps the published value for a key it does not state.
    const draft = policy({ ...DRAFT, values: {}, diff_against_current: [] });
    const stated = parameterRows([BILLING_POSTING, JE_POSTING_MODE], draft, now);
    expect(stated.map((row) => [row.statement, row.changed, proposedValue(row)])).toEqual([
      [true, false, "ERP"],
      [true, false, "NET"],
    ]);
  });

  it("a published version is read-only", async () => {
    serve([PUBLISHED]);
    renderApp(`/policies/accounting/${PUBLISHED.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-13-grid-parameters")).findByRole(
      "grid",
      { name: "Policy parameters" },
    );
    const billing = await within(grid).findByTestId("SF-13-row-billing-posting");
    expect(
      within(billing).queryByRole("combobox", { name: "billing.posting, proposed value" }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: "Save values" })).toBeNull();
    expect(
      screen.getByText(/This version is no longer a draft, so it is read-only\./),
    ).toBeTruthy();
    // The lifecycle caption and the read-only field show the UTC date of the effective instant.
    expect(screen.getByText("Effective 01 Jan 2023")).toBeTruthy();
    expect(screen.getByLabelText("Effective from").textContent).toBe("01 Jan 2023");
  });

  it("Withdraw calls the policy's own route, and its author is back on a draft", async () => {
    // PRD SM-01 and SM-04: the subject returns to Draft. `POST /policies/{id}/withdraw` answers
    // the DRAFT; `POST /approvals/{id}/withdraw` would leave the version WITHDRAWN and read-only.
    const submitted = policy({
      ...DRAFT,
      status: "SUBMITTED",
      pending_approval_request_id: REQUEST_ID,
    });
    let stored: Policy = submitted;
    const calls: string[] = [];
    serve([PUBLISHED, submitted]);
    serveRequest();
    server.use(
      http.get(apiUrl(`/api/v1/policies/${submitted.id}`), () => HttpResponse.json(stored)),
      http.post(apiUrl(`/api/v1/policies/${submitted.id}/withdraw`), async ({ request }) => {
        calls.push(`policy ${JSON.stringify(await request.json())}`);
        stored = { ...DRAFT, row_version: 5 };
        return HttpResponse.json(stored);
      }),
      http.post(apiUrl("/api/v1/approvals/:requestId/withdraw"), () => {
        calls.push("approvals");
        return HttpResponse.json({});
      }),
    );
    renderApp(`/policies/accounting/${submitted.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    fireEvent.click(await screen.findByRole("button", { name: "Withdraw" }));

    expect(await screen.findByText("Withdrew Tenant v3.")).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Save values" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Submit" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Withdraw" })).toBeNull();
    expect(calls).toEqual(["policy {}"]);
    // The pressed control left with the status: focus is on the page's heading, not nowhere.
    expect(document.activeElement).toBe(screen.getByRole("heading", { level: 1 }));
  });

  it.each([
    { status: "REJECTED" as const, notice: "Version 3 was rejected. Edit it to submit it again." },
    {
      status: "WITHDRAWN" as const,
      notice: "Version 3 was withdrawn. Edit it to submit it again.",
    },
  ])(
    "a $status version is edited again while its basis is the published version",
    async ({ status, notice }) => {
      const back = policy({ ...DRAFT, status, approval_request_id: REQUEST_ID });
      // Open versions of other keys hold nothing here: another category, and this one's entity.
      const elsewhere = [
        policy({
          id: "1a1a1a1a-1a1a-4a1a-8a1a-1a1a1a1a1a1a",
          version_no: 2,
          status: "DRAFT",
          category: "PRACTICAL_EXPEDIENT",
        }),
        policy({
          id: "2b2b2b2b-2b2b-4b2b-8b2b-2b2b2b2b2b2b",
          version_no: 1,
          status: "SUBMITTED",
          scope: "ENTITY",
          entity_code: "AVM-DE",
        }),
      ];
      let stored: Policy = back;
      const patches: { readonly ifMatch: string | null; readonly body: unknown }[] = [];
      serve([PUBLISHED, back, ...elsewhere]);
      serveRequest();
      server.use(
        http.get(apiUrl(`/api/v1/policies/${back.id}`), () => HttpResponse.json(stored)),
        http.patch(apiUrl(`/api/v1/policies/${back.id}`), async ({ request }) => {
          patches.push({ ifMatch: request.headers.get("If-Match"), body: await request.json() });
          stored = { ...DRAFT, row_version: 4 };
          return HttpResponse.json(stored);
        }),
      );
      renderApp(`/policies/accounting/${back.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

      expect(await screen.findByText(notice)).toBeTruthy();
      // ERR-09's sentence names "a new draft version", which no control of this page creates.
      expect(screen.queryByText(/Create a new draft version/)).toBeNull();
      expect(screen.queryByRole("button", { name: "Save values" })).toBeNull();
      expect(screen.getByLabelText("Effective from").tagName).toBe("OUTPUT");
      fireEvent.click(screen.getByRole("button", { name: "Edit" }));

      expect(await screen.findByText("Tenant v3 is a draft again.")).toBeTruthy();
      // The `PATCH` that reopens (04 §16.5; PRD SM-04) states nothing.
      expect(patches).toEqual([{ ifMatch: '"r3"', body: {} }]);
      expect(await screen.findByRole("button", { name: "Save values" })).toBeTruthy();
      expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
      expect(screen.queryByText(notice)).toBeNull();
      // "Edit" left with the status: focus is on the page's heading.
      expect(document.activeElement).toBe(screen.getByRole("heading", { level: 1 }));
    },
  );

  it("a refused edit says nothing once the version is a draft again", async () => {
    // Another author reopened the version first. This page's edit is refused 412, the reads come
    // back with the draft, and the page is its editor — without "Record changed" over it for the
    // life of the view, where it would also stand before a later refusal of another command.
    const rejected = policy({ ...DRAFT, status: "REJECTED", approval_request_id: REQUEST_ID });
    let stored: Policy = rejected;
    serve([PUBLISHED, rejected]);
    serveRequest();
    server.use(
      http.get(apiUrl(`/api/v1/policies/${rejected.id}`), () => HttpResponse.json(stored)),
      http.patch(apiUrl(`/api/v1/policies/${rejected.id}`), () => {
        stored = { ...DRAFT, row_version: 9 };
        return problemResponse("precondition-failed", 412, "Record changed");
      }),
    );
    renderApp(`/policies/accounting/${rejected.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));

    expect(await screen.findByRole("button", { name: "Save values" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByText("Record changed")).toBeNull();
    expect(document.querySelector('div[data-tone="negative"]')).toBeNull();
  });

  it("Edit is sent once, however often it is pressed while it is on its way", async () => {
    const rejected = policy({ ...DRAFT, status: "REJECTED", approval_request_id: REQUEST_ID });
    let stored: Policy = rejected;
    let patched = 0;
    let answer: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      answer = resolve;
    });
    serve([PUBLISHED, rejected]);
    serveRequest();
    server.use(
      http.get(apiUrl(`/api/v1/policies/${rejected.id}`), () => HttpResponse.json(stored)),
      http.patch(apiUrl(`/api/v1/policies/${rejected.id}`), async () => {
        patched += 1;
        await held;
        stored = { ...DRAFT, row_version: 4 };
        return HttpResponse.json(stored);
      }),
    );
    renderApp(`/policies/accounting/${rejected.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const edit = await screen.findByRole("button", { name: "Edit" });
    fireEvent.click(edit);
    await waitFor(() => expect(edit.getAttribute("aria-busy")).toBe("true"));
    fireEvent.click(edit);
    fireEvent.click(edit);
    answer();

    expect(await screen.findByText("Tenant v3 is a draft again.")).toBeTruthy();
    expect(patched).toBe(1);
  });

  it("Withdraw is sent once, however often it is pressed while it is on its way", async () => {
    const submitted = policy({
      ...DRAFT,
      status: "SUBMITTED",
      pending_approval_request_id: REQUEST_ID,
    });
    let stored: Policy = submitted;
    let withdrawn = 0;
    let answer: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      answer = resolve;
    });
    serve([PUBLISHED, submitted]);
    serveRequest();
    server.use(
      http.get(apiUrl(`/api/v1/policies/${submitted.id}`), () => HttpResponse.json(stored)),
      http.post(apiUrl(`/api/v1/policies/${submitted.id}/withdraw`), async () => {
        withdrawn += 1;
        await held;
        stored = { ...DRAFT, row_version: 5 };
        return HttpResponse.json(stored);
      }),
    );
    renderApp(`/policies/accounting/${submitted.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const button = await screen.findByRole("button", { name: "Withdraw" });
    fireEvent.click(button);
    await waitFor(() => expect(button.getAttribute("aria-busy")).toBe("true"));
    fireEvent.click(button);
    fireEvent.click(button);
    answer();

    expect(await screen.findByText("Withdrew Tenant v3.")).toBeTruthy();
    expect(withdrawn).toBe(1);
  });

  it("the date field an edit opened is closed again by the edit that is accepted", async () => {
    // The field is opened by a refusal for the date and belongs to that edit. When the version
    // comes back once more in the same view (here: a save refused 412 brings the reads back), it
    // shows its stored date read-only again until a refusal asks for another one.
    const refusedFor =
      "Choose the first day of a future open period: this version holds period-scoped parameters.";
    const rejected = policy({
      ...DRAFT,
      status: "REJECTED",
      approval_request_id: REQUEST_ID,
      effective_from: "2026-09-01T12:00:00Z",
    });
    let stored: Policy = rejected;
    let patches = 0;
    serve([PUBLISHED, rejected]);
    serveRequest();
    server.use(
      http.get(apiUrl(`/api/v1/policies/${rejected.id}`), () => HttpResponse.json(stored)),
      http.patch(apiUrl(`/api/v1/policies/${rejected.id}`), async ({ request }) => {
        const body = (await request.json()) as { effective_from?: string; values?: unknown };
        patches += 1;
        if (patches === 1) {
          return problemResponse("validation-failed", 422, "Check the highlighted fields", {
            errors: [{ field: "effective_from", rule_id: "T-PLT-32", message: refusedFor }],
          });
        }
        if (patches === 2) {
          stored = { ...DRAFT, effective_from: body.effective_from ?? null, row_version: 4 };
          return HttpResponse.json(stored);
        }
        // The save: someone decided the version meanwhile, and it is rejected again.
        stored = { ...rejected, effective_from: "2026-11-01T12:00:00Z", row_version: 9 };
        return problemResponse("precondition-failed", 412, "Record changed");
      }),
    );
    renderApp(`/policies/accounting/${rejected.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const field = await screen.findByRole<HTMLInputElement>("textbox", {
      name: /^Effective from/,
    });
    fireEvent.change(field, { target: { value: "01 Nov 2026" } });
    fireEvent.blur(field);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(await screen.findByText("Tenant v3 is a draft again.")).toBeTruthy();

    const mode = await screen.findByRole("combobox", { name: "je.posting_mode, proposed value" });
    fireEvent.change(mode, { target: { value: "GROSS" } });
    fireEvent.click(screen.getByRole("button", { name: "Save values" }));

    expect(await screen.findByRole("button", { name: "Edit" })).toBeTruthy();
    const again = screen.getByLabelText("Effective from");
    expect(again.tagName).toBe("OUTPUT");
    expect(again.textContent).toBe("01 Nov 2026");
  });

  it("Edit sends no date that was typed while the field was not the edit's", async () => {
    // A date typed on the draft and never saved stays in the view. The version comes back
    // rejected while the page is open (here: a save refused 412 brings the reads back): "Edit"
    // then shows the stored date read-only and must not send the other one.
    const rejected = policy({
      ...DRAFT,
      status: "REJECTED",
      approval_request_id: REQUEST_ID,
      row_version: 7,
    });
    let stored: Policy = DRAFT;
    const sent: { readonly ifMatch: string | null; readonly body: unknown }[] = [];
    serve([PUBLISHED, DRAFT]);
    serveRequest();
    server.use(
      http.get(apiUrl(`/api/v1/policies/${DRAFT.id}`), () => HttpResponse.json(stored)),
      http.patch(apiUrl(`/api/v1/policies/${DRAFT.id}`), async ({ request }) => {
        sent.push({ ifMatch: request.headers.get("If-Match"), body: await request.json() });
        if (sent.length === 1) {
          stored = rejected;
          return problemResponse("precondition-failed", 412, "Record changed");
        }
        stored = { ...DRAFT, row_version: 8 };
        return HttpResponse.json(stored);
      }),
    );
    renderApp(`/policies/accounting/${DRAFT.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const field = await screen.findByRole<HTMLInputElement>("textbox", {
      name: /^Effective from/,
    });
    fireEvent.change(field, { target: { value: "01 Nov 2026" } });
    fireEvent.blur(field);
    fireEvent.click(screen.getByRole("button", { name: "Save values" }));
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));

    expect(await screen.findByText("Tenant v3 is a draft again.")).toBeTruthy();
    expect(sent[1]).toEqual({ ifMatch: '"r7"', body: {} });
  });

  it("a reader without config.author is offered no exit of a rejected version", async () => {
    const rejected = policy({ ...DRAFT, status: "REJECTED", approval_request_id: REQUEST_ID });
    serve([PUBLISHED, rejected]);
    serveRequest();
    renderApp(`/policies/accounting/${rejected.id}`, { me: MARCUS, screenRoutes: SCREEN_ROUTES });

    await within(await screen.findByTestId("SF-13-grid-parameters")).findByRole("grid", {
      name: "Policy parameters",
    });
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByText(/was rejected/)).toBeNull();
  });

  it.each([
    { name: "a tenant version", key: { scope: "TENANT" as const }, title: "Tenant" },
    {
      name: "an entity version",
      key: { scope: "ENTITY" as const, entity_code: "AVM-DE" },
      title: "Entity AVM-DE",
    },
    {
      name: "a book version",
      key: { scope: "BOOK" as const, book: "IFRS15" as const },
      title: "Book IFRS 15",
    },
  ])(
    "once a later version was published the page says ERR-92's sentence and leads to New policy version: $name",
    async ({ key, title }) => {
      // The page knows from the versions it lists: version 4 of the scope is published, and the
      // rejected version 3 was submitted on version 2. The drawer opens on the key of the version
      // the author came from — its category, scope, entity and book — which is what it sends.
      const earlier = policy({ ...PUBLISHED, ...key, status: "SUPERSEDED" });
      const later = policy({
        ...PUBLISHED,
        ...key,
        id: "f4f4f4f4-f4f4-4f4f-8f4f-f4f4f4f4f4f4",
        version_no: 4,
        values: { "billing.posting": "EREV", "je.posting_mode": "GROSS" },
        supersedes_version_id: earlier.id,
      });
      const rejected = policy({
        ...DRAFT,
        ...key,
        status: "REJECTED",
        approval_request_id: REQUEST_ID,
      });
      const created = policy({
        ...key,
        id: "c5c5c5c5-c5c5-4c5c-8c5c-c5c5c5c5c5c5",
        version_no: 5,
        status: "DRAFT",
        values: later.values,
        supersedes_version_id: later.id,
      });
      const bodies: unknown[] = [];
      // The new draft is no version of the list before the create is answered: with an open
      // version listed the API refuses the create (PRD SM-04).
      let listed: readonly Policy[] = [later, earlier, rejected];
      serve([later, earlier, rejected, created]);
      serveRequest();
      server.use(
        http.get(apiUrl("/api/v1/policies"), () =>
          HttpResponse.json({ items: listed, next_cursor: null }),
        ),
        http.post(apiUrl("/api/v1/policies"), async ({ request }) => {
          bodies.push(await request.json());
          listed = [later, earlier, rejected, created];
          return HttpResponse.json(created, { status: 201 });
        }),
      );
      const { router } = renderApp(`/policies/accounting/${rejected.id}`, {
        me: MAYA,
        screenRoutes: SCREEN_ROUTES,
      });

      expect(
        await screen.findByRole("heading", { level: 1, name: `Accounting policies · ${title}` }),
      ).toBeTruthy();
      expect(await screen.findByText(BASIS_SUPERSEDED)).toBeTruthy();
      expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
      expect(screen.queryByText(/was rejected\. Edit it/)).toBeNull();
      // Present with the page, the notice takes no focus.
      expect(document.activeElement?.textContent).not.toBe(BASIS_SUPERSEDED);
      fireEvent.click(screen.getByRole("button", { name: "New policy version" }));

      const drawer = await screen.findByRole("dialog", { name: "New policy version" });
      expect(within(drawer).getByRole("combobox", { name: /^Category/ }).textContent).toContain(
        "Accounting policies",
      );
      fireEvent.click(within(drawer).getByRole("button", { name: "Create version" }));

      expect(await screen.findByText("Created policy version v5 as a draft.")).toBeTruthy();
      // It starts from the published values of that key, as the sentence says.
      expect(bodies).toEqual([
        {
          category: "ACCOUNTING_POLICY",
          scope: key.scope,
          entity_code: "entity_code" in key ? key.entity_code : null,
          book: "book" in key ? key.book : null,
          values: { "billing.posting": "EREV", "je.posting_mode": "GROSS" },
        },
      ]);
      await waitFor(() =>
        expect(router.state.location.pathname).toBe(`/policies/accounting/${created.id}`),
      );
    },
  );

  it("the page of one version holds nothing that was typed on the page of another", async () => {
    // The link of a version whose basis was superseded leads from one version's page to another's
    // on one route, and Back returns the same way to a version the client still holds. What the
    // author chose on the new draft and did not save is that page's alone: the version they came
    // from reads its own value again, not the unsaved one.
    const earlier = policy({ ...PUBLISHED, status: "SUPERSEDED" });
    const later = policy({
      ...PUBLISHED,
      id: "f4f4f4f4-f4f4-4f4f-8f4f-f4f4f4f4f4f4",
      version_no: 4,
      values: { "billing.posting": "EREV", "je.posting_mode": "NET" },
      supersedes_version_id: earlier.id,
    });
    const rejected = policy({ ...DRAFT, status: "REJECTED", approval_request_id: REQUEST_ID });
    const created = policy({
      id: "c5c5c5c5-c5c5-4c5c-8c5c-c5c5c5c5c5c5",
      version_no: 5,
      status: "DRAFT",
      values: later.values,
      supersedes_version_id: later.id,
    });
    // The new draft is a version of the list once the create is answered, not before.
    let listed: readonly Policy[] = [later, earlier, rejected];
    serve([later, earlier, rejected, created]);
    serveRequest();
    server.use(
      http.get(apiUrl("/api/v1/policies"), () =>
        HttpResponse.json({ items: listed, next_cursor: null }),
      ),
      http.post(apiUrl("/api/v1/policies"), () => {
        listed = [later, earlier, rejected, created];
        return HttpResponse.json(created, { status: 201 });
      }),
    );
    const { router } = renderApp(`/policies/accounting/${rejected.id}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    const proposedMode = async () => {
      const grid = await within(await screen.findByTestId("SF-13-grid-parameters")).findByRole(
        "grid",
        { name: "Policy parameters" },
      );
      const row = await within(grid).findByTestId("SF-13-row-je-posting-mode");
      return row.querySelector<HTMLElement>('[data-column="proposed"]')?.textContent;
    };

    expect(await screen.findByText(BASIS_SUPERSEDED)).toBeTruthy();
    expect(await proposedMode()).toBe("NET");
    fireEvent.click(screen.getByRole("button", { name: "New policy version" }));
    const drawer = await screen.findByRole("dialog", { name: "New policy version" });
    fireEvent.click(within(drawer).getByRole("button", { name: "Create version" }));
    const mode = await screen.findByRole<HTMLSelectElement>("combobox", {
      name: "je.posting_mode, proposed value",
    });
    fireEvent.change(mode, { target: { value: "GROSS" } });
    await waitFor(() => expect(mode.value).toBe("GROSS"));
    fireEvent.change(screen.getByRole("searchbox", { name: "Search parameters" }), {
      target: { value: "posting" },
    });

    await router.navigate(-1);

    // The version the author came from: the draft they just made is open now, and it says so.
    expect(await screen.findByRole("link", { name: "Open version 5" })).toBeTruthy();
    expect(router.state.location.pathname).toBe(`/policies/accounting/${rejected.id}`);
    expect(await proposedMode()).toBe("NET");
    expect(
      screen.getByRole<HTMLInputElement>("searchbox", { name: "Search parameters" }).value,
    ).toBe("");
  });

  it("a refusal that arrives all the same shows its sentence whole and once, and the page then leads on", async () => {
    // The versions were read before version 4 was published: the page offers "Edit", and the
    // server answers PRD ERR-92 — the sentence as the problem's detail and as the message on
    // `status`. The read of the versions that follows is held, so that the refusal is seen as
    // the page shows it before the notice takes its place.
    const earlier = policy({ ...PUBLISHED, status: "SUPERSEDED" });
    const later = policy({
      ...PUBLISHED,
      id: "f4f4f4f4-f4f4-4f4f-8f4f-f4f4f4f4f4f4",
      version_no: 4,
      supersedes_version_id: earlier.id,
    });
    const rejected = policy({ ...DRAFT, status: "REJECTED", approval_request_id: REQUEST_ID });
    let listed: readonly Policy[] = [PUBLISHED, rejected];
    let patched = 0;
    let read: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      read = resolve;
    });
    serve([PUBLISHED, rejected]);
    serveRequest();
    server.use(
      http.get(apiUrl("/api/v1/policies"), async () => {
        if (patched > 0) {
          await held;
        }
        return HttpResponse.json({ items: listed, next_cursor: null });
      }),
      http.patch(apiUrl(`/api/v1/policies/${rejected.id}`), () => {
        patched += 1;
        listed = [later, earlier, rejected];
        return problemResponse("invalid-transition", 409, "Action not available in this state", {
          detail: BASIS_SUPERSEDED,
          errors: [
            { field: "status", rule_id: "REGISTRY_BASIS_SUPERSEDED", message: BASIS_SUPERSEDED },
          ],
        });
      }),
    );
    renderApp(`/policies/accounting/${rejected.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));

    // The refusal, as it arrived: its title and its sentence, once.
    const title = await screen.findByRole("heading", {
      name: "Action not available in this state",
    });
    const refusal = title.closest<HTMLElement>('[role="alert"]') as HTMLElement;
    expect(within(refusal).getAllByText(BASIS_SUPERSEDED)).toHaveLength(1);
    expect(screen.getAllByText(BASIS_SUPERSEDED)).toHaveLength(1);
    read();

    // With the versions read again the control gives way to "New policy version", and focus is on
    // the notice that was not there before.
    expect(await screen.findByRole("button", { name: "New policy version" })).toBeTruthy();
    expect(
      screen.queryByRole("heading", { name: "Action not available in this state" }),
    ).toBeNull();
    expect(screen.getAllByText(BASIS_SUPERSEDED)).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(patched).toBe(1);
    await waitFor(() => expect(document.activeElement?.textContent).toBe(BASIS_SUPERSEDED));
  });

  it.each([
    { name: "its basis still the published version", superseded: false },
    { name: "its basis superseded", superseded: true },
  ])(
    "while another version of the scope is open the page says SM-04's sentence and leads to that version: $name",
    async ({ superseded }) => {
      // PRD SM-04 (`registry.presets.VERSION_OPEN`): the edit that reopens and a new version are
      // both refused while a version of the scope is open, and the page lists that version. It
      // says the refusal's sentence in place of either control, with the way to the version.
      const open = "Another version is open. Finish it or withdraw it first.";
      const earlier = policy({ ...PUBLISHED, status: "SUPERSEDED" });
      const later = policy({
        ...PUBLISHED,
        id: "f4f4f4f4-f4f4-4f4f-8f4f-f4f4f4f4f4f4",
        version_no: 4,
        supersedes_version_id: earlier.id,
      });
      const rejected = policy({ ...DRAFT, status: "REJECTED", approval_request_id: REQUEST_ID });
      const other = policy({
        id: "c5c5c5c5-c5c5-4c5c-8c5c-c5c5c5c5c5c5",
        version_no: 5,
        status: "TESTED",
        supersedes_version_id: superseded ? later.id : PUBLISHED.id,
      });
      serve(superseded ? [later, earlier, rejected, other] : [PUBLISHED, rejected, other]);
      serveRequest();
      renderApp(`/policies/accounting/${rejected.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

      const title = await screen.findByRole("heading", { name: open });
      const notice = title.closest<HTMLElement>("[data-tone]") as HTMLElement;
      expect(notice.getAttribute("data-tone")).toBe("info");
      expect(
        within(notice).getByRole("link", { name: "Open version 5" }).getAttribute("href"),
      ).toBe(`/policies/accounting/${other.id}`);
      expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
      expect(screen.queryByRole("button", { name: "New policy version" })).toBeNull();
      expect(screen.queryByText(/was rejected\. Edit it/)).toBeNull();
      expect(screen.queryByText(BASIS_SUPERSEDED)).toBeNull();
      // Present with the page, the notice takes no focus.
      expect(document.activeElement).not.toBe(title);
    },
  );

  it("an edit refused because a version was opened meanwhile leads to that version", async () => {
    // The page read the versions before the other draft was created: it offers "Edit", and the
    // server answers SM-04 — no detail, the sentence on `status`. With the versions read again
    // the notice takes the refusal's place, its sentence once, and focus is on it.
    const open = "Another version is open. Finish it or withdraw it first.";
    const rejected = policy({ ...DRAFT, status: "REJECTED", approval_request_id: REQUEST_ID });
    const other = policy({
      id: "c5c5c5c5-c5c5-4c5c-8c5c-c5c5c5c5c5c5",
      version_no: 4,
      status: "DRAFT",
      supersedes_version_id: PUBLISHED.id,
    });
    let listed: readonly Policy[] = [PUBLISHED, rejected];
    serve([PUBLISHED, rejected, other]);
    serveRequest();
    server.use(
      http.get(apiUrl("/api/v1/policies"), () =>
        HttpResponse.json({ items: listed, next_cursor: null }),
      ),
      http.patch(apiUrl(`/api/v1/policies/${rejected.id}`), () => {
        listed = [PUBLISHED, rejected, other];
        return problemResponse("invalid-transition", 409, "Action not available in this state", {
          errors: [{ field: "status", rule_id: "SM-04", message: open }],
        });
      }),
    );
    renderApp(`/policies/accounting/${rejected.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));

    const link = await screen.findByRole("link", { name: "Open version 4" });
    expect(link.getAttribute("href")).toBe(`/policies/accounting/${other.id}`);
    expect(screen.getAllByText(open)).toHaveLength(1);
    expect(
      screen.queryByRole("heading", { name: "Action not available in this state" }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    await waitFor(() => expect(document.activeElement?.textContent).toBe(open));
  });

  it.each([
    {
      name: "submitted, to the preparer of its request",
      status: "SUBMITTED" as const,
      preparer: true,
      sentence:
        "This version is read-only while it waits for approval. Withdraw it to change values.",
    },
    {
      name: "submitted, to another author",
      status: "SUBMITTED" as const,
      preparer: false,
      sentence: "This version is read-only while it waits for approval.",
    },
    {
      name: "approved",
      status: "APPROVED" as const,
      preparer: true,
      sentence:
        "This version is no longer a draft, so it is read-only. Create a new policy version to change values.",
    },
    {
      name: "published",
      status: "PUBLISHED" as const,
      preparer: true,
      sentence:
        "This version is no longer a draft, so it is read-only. Create a new policy version to change values.",
    },
    {
      name: "superseded",
      status: "SUPERSEDED" as const,
      preparer: true,
      sentence:
        "This version is no longer a draft, so it is read-only. Create a new policy version to change values.",
    },
  ])(
    "a policy version that cannot change names the control that changes its values: $name",
    async ({ status, preparer, sentence }) => {
      // PRD ERR-09 rev 1.190: a policy version is copied by no control, so the banner does not
      // say "Create a new draft version". It names "Withdraw" to the author who is offered it.
      const pending = status === "SUBMITTED";
      const frozen = policy({
        ...DRAFT,
        status,
        pending_approval_request_id: pending ? REQUEST_ID : null,
        approval_request_id: pending ? null : REQUEST_ID,
      });
      serve([frozen]);
      server.use(
        http.get(apiUrl("/api/v1/approvals/:requestId"), () =>
          HttpResponse.json({
            id: REQUEST_ID,
            preparer: {
              id: preparer ? MAYA.user.id : "9a9a9a9a-9a9a-4a9a-8a9a-9a9a9a9a9a9a",
              display_name: preparer ? "Maya Chen" : "Priya Raman",
              kind: "USER",
            },
            steps: [],
          }),
        ),
      );
      renderApp(`/policies/accounting/${frozen.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

      expect(await screen.findByRole("heading", { name: sentence })).toBeTruthy();
      expect(screen.queryByText(/new draft version/)).toBeNull();
      expect(screen.queryAllByRole("button", { name: "Withdraw" })).toHaveLength(
        pending && preparer ? 1 : 0,
      );
    },
  );

  it("an edit refused for the effective date opens the field, and the date goes with the next edit", async () => {
    // A save validates the date the version holds (04 §16.5): a rejected version whose date has
    // passed is not reopened as it is, and its author could not correct a read-only date.
    // `registry_versions.PERIOD_START_REQUIRED`, rule T-PLT-32.
    const refusedFor =
      "Choose the first day of a future open period: this version holds period-scoped parameters.";
    const rejected = policy({
      ...DRAFT,
      status: "REJECTED",
      approval_request_id: REQUEST_ID,
      effective_from: "2026-09-01T12:00:00Z",
    });
    let stored: Policy = rejected;
    const bodies: unknown[] = [];
    serve([PUBLISHED, rejected]);
    serveRequest();
    server.use(
      http.get(apiUrl(`/api/v1/policies/${rejected.id}`), () => HttpResponse.json(stored)),
      http.patch(apiUrl(`/api/v1/policies/${rejected.id}`), async ({ request }) => {
        const body = (await request.json()) as { effective_from?: string };
        bodies.push(body);
        if (body.effective_from === undefined) {
          return problemResponse("validation-failed", 422, "Check the highlighted fields", {
            errors: [{ field: "effective_from", rule_id: "T-PLT-32", message: refusedFor }],
          });
        }
        stored = { ...DRAFT, effective_from: body.effective_from, row_version: 4 };
        return HttpResponse.json(stored);
      }),
    );
    renderApp(`/policies/accounting/${rejected.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));

    expect(await screen.findByText(refusedFor)).toBeTruthy();
    const field = await screen.findByLabelText(/^Effective from/);
    expect(field.tagName).toBe("INPUT");
    await waitFor(() => expect(document.activeElement).toBe(field));
    fireEvent.change(field, { target: { value: "01 Nov 2026" } });
    fireEvent.blur(field);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    expect(await screen.findByText("Tenant v3 is a draft again.")).toBeTruthy();
    expect(bodies).toEqual([{}, { effective_from: "2026-11-01T12:00:00Z" }]);
    expect(await screen.findByRole("button", { name: "Save values" })).toBeTruthy();
  });

  it("in the field a refusal opened, a text that is no date is not sent as no date; an emptied field is", async () => {
    // "Edit" with a text the field cannot read would have reopened the version without its date
    // and without a word. It is sent as the edit that states nothing, so the refusal of the stored
    // date stands; the author who empties the field does choose no date.
    const refusedFor =
      "Choose the first day of a future open period: this version holds period-scoped parameters.";
    const rejected = policy({
      ...DRAFT,
      status: "REJECTED",
      approval_request_id: REQUEST_ID,
      effective_from: "2026-09-01T12:00:00Z",
    });
    let stored: Policy = rejected;
    const bodies: unknown[] = [];
    serve([PUBLISHED, rejected]);
    serveRequest();
    server.use(
      http.get(apiUrl(`/api/v1/policies/${rejected.id}`), () => HttpResponse.json(stored)),
      http.patch(apiUrl(`/api/v1/policies/${rejected.id}`), async ({ request }) => {
        const body = (await request.json()) as { effective_from?: string | null };
        bodies.push(body);
        if (body.effective_from === undefined) {
          return problemResponse("validation-failed", 422, "Check the highlighted fields", {
            errors: [{ field: "effective_from", rule_id: "T-PLT-32", message: refusedFor }],
          });
        }
        stored = { ...DRAFT, effective_from: body.effective_from, row_version: 4 };
        return HttpResponse.json(stored);
      }),
    );
    renderApp(`/policies/accounting/${rejected.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const field = await screen.findByRole<HTMLInputElement>("textbox", {
      name: /^Effective from/,
    });
    fireEvent.change(field, { target: { value: "next month" } });
    fireEvent.blur(field);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toEqual({});
    await waitFor(() => expect(descriptionsOf(field)).toContain(refusedFor));

    fireEvent.change(field, { target: { value: "" } });
    fireEvent.blur(field);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    expect(await screen.findByText("Tenant v3 is a draft again.")).toBeTruthy();
    expect(bodies[2]).toEqual({ effective_from: null });
  });

  it("a failed read of the versions is said in place of the grid", async () => {
    // The page reads the versions of the scope to know the published one. Without them a rejected
    // version has neither exit, and the grid waited behind a skeleton that never ended.
    const rejected = policy({ ...DRAFT, status: "REJECTED", approval_request_id: REQUEST_ID });
    serve([PUBLISHED, rejected]);
    serveRequest();
    server.use(
      http.get(apiUrl("/api/v1/policies"), () =>
        problemResponse(null, 500, "Internal Server Error"),
      ),
    );
    renderApp(`/policies/accounting/${rejected.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    // The read is tried twice before it is given up (the client's one retry).
    expect(
      await screen.findByText("Could not load the policy version", undefined, { timeout: 8000 }),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByTestId("SF-13-grid-parameters")).toBeNull();
  }, 15_000);

  it("a settings version that cannot be edited reads the first sentence of the help alone", async () => {
    const close = policy({
      id: "c7c7c7c7-c7c7-4c7c-8c7c-c7c7c7c7c7c7",
      version_no: 2,
      status: "PUBLISHED",
      category: "CLOSE",
      values: { "close.late_entry_window_days": 7 },
      published_at: "2026-09-12T09:00:00Z",
      published_by: MARCUS_WEBB,
    });
    serve([close]);
    renderApp(`/policies/accounting/${close.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    expect(await screen.findByRole("heading", { level: 1, name: "Close · Tenant" })).toBeTruthy();
    expect(
      screen.getByText("Without a date the version takes effect when it is approved."),
    ).toBeTruthy();
    expect(screen.queryByText(/Choose a date to start later\./)).toBeNull();
  });

  it("the help of Effective from stands under the filter row and stays the description of its field", async () => {
    // In the 160 px of its field the sentence wrapped to six lines, and with the filters on a
    // second row the grid was left one row at 1440x900 (measured in a browser, where the layout
    // is checked: jsdom has none). Here: where the help is, and that the control still names it.
    const sentence =
      "Pinned-at-inception values apply to contracts computed after publication; per-period values apply from this period.";
    serve([PUBLISHED, DRAFT]);
    renderApp(`/policies/accounting/${DRAFT.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const field = await screen.findByRole<HTMLInputElement>("textbox", {
      name: /^Effective from/,
    });
    const help = screen.getByText(sentence);
    expect(descriptionsOf(field)).toBe(sentence);
    // One row holds the four controls; the help follows the row and is no part of the date's
    // column.
    const row = help.previousElementSibling as HTMLElement;
    for (const control of [
      field,
      screen.getByRole("searchbox", { name: "Search parameters" }),
      screen.getByRole("combobox", { name: "Section" }),
      screen.getByRole("switch", { name: "Changed only" }),
    ]) {
      expect(row.contains(control)).toBe(true);
    }
    expect(row.contains(help)).toBe(false);
    // The grid keeps its floor of eight rows, and the page grows past the main region below it.
    const grid = await screen.findByTestId("SF-13-grid-parameters");
    // Each of these is needed: without the stated minimum or with a basis read from the content
    // the block is as tall as the grid's own limit; without the growth it never fills a tall page.
    expect([...(grid.parentElement?.classList ?? [])].sort()).toEqual(
      ["basis-0", "flex", "flex-col", "grow", "min-h-100", "shrink-0"].sort(),
    );
    const page = screen.getByTestId("SF-13-accounting-version-page").classList;
    expect(page.contains("min-h-full")).toBe(true);
    expect(page.contains("h-full")).toBe(false);
    // An editable proposed value that is longer than its control ends in an ellipsis.
    expect(
      screen.getByRole("combobox", { name: "je.posting_mode, proposed value" }).classList,
    ).toContain("truncate");
  });

  it("a long key shortens under its full text, and the Changed chip stays outside it", async () => {
    const long = parameter({
      code: "platform.snapshot_retention_families_for_tax_and_audit",
      pol_id: null,
      description: "Which retention families hold a snapshot?",
    });
    const draft = policy({
      ...DRAFT,
      values: { [long.code]: "EREV" },
      diff_against_current: [{ code: long.code, before: "ERP", after: "EREV", change: "CHANGED" }],
    });
    serve([PUBLISHED, draft]);
    server.use(
      http.get(apiUrl("/api/v1/registry/parameters"), () =>
        HttpResponse.json({ items: [long], next_cursor: null }),
      ),
    );
    renderApp(`/policies/accounting/${draft.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-13-grid-parameters")).findByRole(
      "grid",
      { name: "Policy parameters" },
    );
    const cell = (await within(grid).findAllByRole("row"))
      .map((row) => row.querySelector<HTMLElement>('[data-column="code"]'))
      .find((found) => found?.textContent?.includes(long.code) === true);
    const key = within(cell as HTMLElement).getByText(long.code);
    expect(key.getAttribute("title")).toBe(long.code);
    expect(key.className).toContain("truncate");
    const chip = within(cell as HTMLElement).getByText("Changed");
    expect(key.contains(chip)).toBe(false);
    // The chip's own wrapper keeps its size (the cell carries the same class and is no witness).
    const wrapper = chip.parentElement as HTMLElement;
    expect(wrapper).not.toBe(cell);
    expect(wrapper.tagName).toBe("SPAN");
    expect(wrapper.className).toBe("shrink-0");
    expect(key.parentElement).toBe(wrapper.parentElement);
  });

  it("a literal longer than its column shortens under its full text, in every value column", async () => {
    // A cell hides what does not fit: a literal it cut at its edge read as a shorter, other literal
    // (seen in a browser — "RECOGNISE_IN_PERIOD_ON_INCEPTION_BASIS" in the 144 px of a default
    // column). The layout itself is checked there; here, that each literal is the truncating
    // element and carries its full text.
    const mode = parameter({
      code: "mod.price_change_on_satisfied_performance",
      pol_id: "POL-061",
      description: "How is a price change on satisfied performance recognised?",
      pin: "K",
      default_asc606: "RECOGNISE_IN_PERIOD_ON_INCEPTION_BASIS",
      default_ifrs15: "RECOGNISE_IN_PERIOD_ON_INCEPTION_BASIS",
      legacy_parity_value: "POOL_WITH_REMAINING",
      source_ref: "POLICIES §1.9 price changes",
      value_schema: {
        type: "string",
        enum: ["RECOGNISE_IN_PERIOD_ON_INCEPTION_BASIS", "POOL_WITH_REMAINING"],
      },
    });
    const held = policy({
      ...PUBLISHED,
      values: { [mode.code]: "POOL_WITH_REMAINING", "rounding.posting_mode": "HALF_UP" },
    });
    serve([held]);
    server.use(
      http.get(apiUrl("/api/v1/registry/parameters"), () =>
        HttpResponse.json({ items: [mode, ROUNDING], next_cursor: null }),
      ),
    );
    renderApp(`/policies/accounting/${held.id}`, { me: MARCUS, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-13-grid-parameters")).findByRole(
      "grid",
      { name: "Policy parameters" },
    );
    const row = await within(grid).findByTestId(
      "SF-13-row-mod-price-change-on-satisfied-performance",
    );
    const literal = (inRow: HTMLElement, column: string, text: string) => {
      const cell = inRow.querySelector<HTMLElement>(`[data-column="${column}"]`) as HTMLElement;
      const found = within(cell).getByText(text);
      return {
        title: found.getAttribute("title"),
        truncates: found.className.includes("truncate"),
      };
    };
    const whole = (text: string) => ({ title: text, truncates: true });
    expect(literal(row, "pol_id", "POL-061")).toEqual(whole("POL-061"));
    expect(literal(row, "proposed", "POOL_WITH_REMAINING")).toEqual(whole("POOL_WITH_REMAINING"));
    expect(literal(row, "default_asc606", "RECOGNISE_IN_PERIOD_ON_INCEPTION_BASIS")).toEqual(
      whole("RECOGNISE_IN_PERIOD_ON_INCEPTION_BASIS"),
    );
    expect(literal(row, "default_ifrs15", "RECOGNISE_IN_PERIOD_ON_INCEPTION_BASIS")).toEqual(
      whole("RECOGNISE_IN_PERIOD_ON_INCEPTION_BASIS"),
    );
    expect(literal(row, "legacy_parity_value", "POOL_WITH_REMAINING")).toEqual(
      whole("POOL_WITH_REMAINING"),
    );
    expect(literal(row, "source_ref", "POLICIES §1.9 price changes")).toEqual(
      whole("POLICIES §1.9 price changes"),
    );
    // A forced value shortens beside its lock, which keeps its size.
    const forced = within(grid).getByTestId("SF-13-row-rounding-posting-mode");
    expect(literal(forced, "proposed", "HALF_UP")).toEqual(whole("HALF_UP"));
    const lock = within(forced).getByRole("img", { name: "Forced by the framework" });
    expect(lock.getAttribute("class")).toContain("shrink-0");
    expect(lock.parentElement?.className).toContain("min-w-0");
  });

  it("Save values sends the picked effective date as 12:00:00Z, and the stored instant reads back as that date", async () => {
    const patches: { readonly ifMatch: string | null; readonly body: unknown }[] = [];
    let stored: Policy = DRAFT;
    serve([PUBLISHED]);
    server.use(
      http.get(apiUrl("/api/v1/policies"), () =>
        HttpResponse.json({ items: [PUBLISHED, stored], next_cursor: null }),
      ),
      http.get(apiUrl(`/api/v1/policies/${DRAFT.id}`), () => HttpResponse.json(stored)),
      http.patch(apiUrl(`/api/v1/policies/${DRAFT.id}`), async ({ request }) => {
        const body = (await request.json()) as { readonly effective_from: string };
        patches.push({ ifMatch: request.headers.get("If-Match"), body });
        stored = { ...stored, effective_from: body.effective_from, row_version: 4 };
        return HttpResponse.json(stored);
      }),
    );
    renderApp(`/policies/accounting/${DRAFT.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const field = await screen.findByRole<HTMLInputElement>("textbox", {
      name: /^Effective from/,
    });
    expect(field.value).toBe("");
    fireEvent.change(field, { target: { value: "2026-11-01" } });
    fireEvent.blur(field);
    fireEvent.click(screen.getByRole("button", { name: "Save values" }));

    expect(await screen.findByText("Saved Tenant v3.")).toBeTruthy();
    // PolicyUpdateIn `effective_from` is date-time: an RFC 3339 UTC instant, never a date (DS-I18N-08).
    expect(patches).toEqual([
      { ifMatch: '"r3"', body: { values: DRAFT.values, effective_from: "2026-11-01T12:00:00Z" } },
    ]);
    // The round trip: the refetched instant shows the date that was picked and nothing is pending.
    expect(await screen.findByText("Effective 01 Nov 2026")).toBeTruthy();
    expect(field.value).toBe("01 Nov 2026");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Save values" }).getAttribute("aria-disabled"),
      ).toBe("true"),
    );
  });

  it("a draft edits the UTC date of its effective instant", async () => {
    const dated = { ...DRAFT, effective_from: "2026-11-01T12:00:00Z" };
    serve([PUBLISHED, dated]);
    renderApp(`/policies/accounting/${dated.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const field = await screen.findByRole("textbox", { name: /^Effective from/ });
    expect((field as HTMLInputElement).value).toBe("01 Nov 2026");
    expect(screen.getByText("Effective 01 Nov 2026")).toBeTruthy();
    // The unchanged date is not a pending change.
    expect(screen.getByRole("button", { name: "Save values" }).getAttribute("aria-disabled")).toBe(
      "true",
    );
  });

  it("Submit refused with PRD ERR-75 shows the sentence at Effective from with focus, and the banner does not repeat it", async () => {
    // PRD §5.5 ERR-75, the instant form: `detail` and `errors[].message` are the same sentence.
    const sentence =
      "This version replaces a published one. Choose an effective time that has not passed.";
    const dated: Policy = { ...DRAFT, status: "TESTED", effective_from: "2026-09-30T12:00:00Z" };
    serve([PUBLISHED, dated]);
    server.use(
      http.post(apiUrl(`/api/v1/policies/${dated.id}/submit`), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          detail: sentence,
          errors: [
            {
              field: "effective_from",
              sheet: null,
              row: null,
              rule_id: "REQ-POL-007",
              message: sentence,
            },
          ],
        }),
      ),
    );
    renderApp(`/policies/accounting/${dated.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const field = await screen.findByRole<HTMLInputElement>("textbox", {
      name: /^Effective from/,
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));

    await waitFor(() => {
      expect(descriptionsOf(field)).toContain(sentence);
    });
    expect(field.getAttribute("aria-invalid")).toBe("true");
    expect(document.activeElement).toBe(field);
    const heading = screen.getByRole("heading", { name: "Check the highlighted fields" });
    expect(heading.closest('[role="alert"]')?.textContent).not.toContain(sentence);
    expect(screen.getAllByText(sentence)).toHaveLength(1);

    // The sentence describes the date that was submitted: it leaves once another date is typed.
    fireEvent.change(field, { target: { value: "2026-11-02" } });
    expect(screen.queryByText(sentence)).toBeNull();
    expect(screen.queryByRole("heading", { name: "Check the highlighted fields" })).toBeNull();
  });

  it("a refused save shows the message on the effective date at the field and lists what no field shows in the banner", async () => {
    const periodStart =
      "Choose the first day of a future open period: this version holds period-scoped parameters.";
    const forced = "The framework fixes this value in the IFRS15 book.";
    serve([PUBLISHED, DRAFT]);
    server.use(
      http.patch(apiUrl(`/api/v1/policies/${DRAFT.id}`), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            {
              field: "effective_from",
              sheet: null,
              row: null,
              rule_id: null,
              message: periodStart,
            },
            {
              field: "values.je.posting_mode",
              sheet: null,
              row: null,
              rule_id: null,
              message: forced,
            },
          ],
        }),
      ),
    );
    renderApp(`/policies/accounting/${DRAFT.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const field = await screen.findByRole<HTMLInputElement>("textbox", {
      name: /^Effective from/,
    });
    fireEvent.change(field, { target: { value: "2026-11-15" } });
    fireEvent.blur(field);
    fireEvent.click(screen.getByRole("button", { name: "Save values" }));

    await waitFor(() => {
      expect(descriptionsOf(field)).toContain(periodStart);
    });
    expect(document.activeElement).toBe(field);
    const heading = screen.getByRole("heading", { name: "Check the highlighted fields" });
    const alert = heading.closest<HTMLElement>('[role="alert"]');
    // Before rev 1.31 the banner held the title alone and the second message was nowhere.
    expect(alert?.textContent).toContain(forced);
    expect(alert?.textContent).not.toContain(periodStart);
  });

  it("saved values clear the refusal of an earlier submission", async () => {
    const changed = "This version changed after its tests ran. Run the tests again.";
    const tested: Policy = { ...DRAFT, status: "TESTED", effective_from: "2026-11-02T12:00:00Z" };
    let stored = tested;
    serve([PUBLISHED, tested]);
    server.use(
      http.get(apiUrl(`/api/v1/policies/${tested.id}`), () => HttpResponse.json(stored)),
      http.patch(apiUrl(`/api/v1/policies/${tested.id}`), () => {
        stored = {
          ...tested,
          status: "DRAFT",
          values: { ...tested.values, "billing.posting": "EREV" },
          row_version: 4,
        };
        return HttpResponse.json(stored);
      }),
      http.post(apiUrl(`/api/v1/policies/${tested.id}/submit`), () =>
        problemResponse("invalid-transition", 409, "Action not available in this state", {
          errors: [
            { field: "status", sheet: null, row: null, rule_id: "REQ-POL-003", message: changed },
          ],
        }),
      ),
    );
    renderApp(`/policies/accounting/${tested.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-13-grid-parameters")).findByRole(
      "grid",
      { name: "Policy parameters" },
    );
    const billing = await within(grid).findByTestId("SF-13-row-billing-posting");
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(await screen.findByText(changed)).toBeTruthy();

    fireEvent.change(
      within(billing).getByRole("combobox", { name: "billing.posting, proposed value" }),
      {
        target: { value: "EREV" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Save values" }));
    expect(await screen.findByText("Saved Tenant v3.")).toBeTruthy();
    expect(screen.queryByText(changed)).toBeNull();
    expect(
      screen.queryByRole("heading", { name: "Action not available in this state" }),
    ).toBeNull();
  });

  // POLICY-VERSION-RESET-RACE-1: a save's success is known to the page only after the reads it causes,
  // and "Submit" can be sent meanwhile. Before, the success then cleared the refusal of that submission
  // as if it were the earlier one: a refused command without a word.
  it("a submission refused while the reads after Save values are on their way keeps its refusal when they arrive", async () => {
    const sentence =
      "This version replaces a published one. Choose an effective time that has not passed.";
    const dated: Policy = { ...DRAFT, status: "TESTED", effective_from: "2026-09-30T12:00:00Z" };
    const read = heldRead();
    let stored = dated;
    serve([PUBLISHED, dated]);
    server.use(
      http.get(apiUrl(`/api/v1/policies/${dated.id}`), async () => {
        await read.passed();
        return HttpResponse.json(stored);
      }),
      http.patch(apiUrl(`/api/v1/policies/${dated.id}`), () => {
        read.hold();
        stored = {
          ...dated,
          values: { ...dated.values, "billing.posting": "EREV" },
          row_version: 4,
        };
        return HttpResponse.json(stored);
      }),
      http.post(apiUrl(`/api/v1/policies/${dated.id}/submit`), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          detail: sentence,
          errors: [
            {
              field: "effective_from",
              sheet: null,
              row: null,
              rule_id: "REQ-POL-007",
              message: sentence,
            },
          ],
        }),
      ),
    );
    renderApp(`/policies/accounting/${dated.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-13-grid-parameters")).findByRole(
      "grid",
      { name: "Policy parameters" },
    );
    const billing = await within(grid).findByTestId("SF-13-row-billing-posting");
    fireEvent.change(
      within(billing).getByRole("combobox", { name: "billing.posting, proposed value" }),
      {
        target: { value: "EREV" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Save values" }));
    // The save has answered; the version the page reads again has not.
    await waitFor(() => {
      expect(read.waiting()).toBeGreaterThan(0);
    });
    expect(screen.queryByText("Saved Tenant v3.")).toBeNull();
    const field = screen.getByRole<HTMLInputElement>("textbox", { name: /^Effective from/ });
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    await waitFor(() => {
      expect(descriptionsOf(field)).toContain(sentence);
    });

    read.release();
    expect(await screen.findByText("Saved Tenant v3.")).toBeTruthy();
    // The submission was sent after the save: it is not the earlier one a saved version answers.
    expect(descriptionsOf(field)).toContain(sentence);
    expect(field.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByRole("heading", { name: "Check the highlighted fields" })).toBeTruthy();
  });
});

/** The text of the elements that describe a control: its error first, then its help. */
function descriptionsOf(element: HTMLElement): string {
  return (element.getAttribute("aria-describedby") ?? "")
    .split(" ")
    .map((id) => document.getElementById(id)?.textContent ?? "")
    .join(" | ");
}
