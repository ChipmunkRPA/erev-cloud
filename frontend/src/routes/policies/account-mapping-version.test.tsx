// @vitest-environment jsdom
// SF-13:account-mapping and SF-13:account-mapping-version (BUILD_SPEC RFD-25; SCREENS §11.6): the
// versions grid; the rules grid "Mapping rules"; in "Add rule", choosing `BILLING_CLEARING` makes
// "Clearing purpose" required and shows its validation message, choosing `REVENUE` hides it; the table
// "Role coverage" shows the warning chip "Not mapped" on a role without a rule and renders reserved roles
// in `--fg-3` without the chip. 04 SC-V `effective_from` and `effective_to` are instants (04 §16.14
// AccountMappingOut "datetime or null"): the grid, the chip, the lifecycle caption and the Effective from
// field show their UTC date.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import {
  type AccountMapping,
  type AccountMappingRule,
  coverageRows,
  ruleChanges,
  ruleDraftErrors,
  EMPTY_RULE_DRAFT,
} from "../../lib/api/queries/account-mappings";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, heldRead, installMswServer, problemResponse, server } from "../../test/msw";
import {
  describedBy,
  RECORD_CHANGED,
  REFUSAL_REFERENCE,
  REFUSAL_TITLE,
  refusedWith,
} from "../../test/refusals";

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

const MAYA = signedInMe({ permissions: ["config.read", "config.author"] });
const MARCUS = signedInMe({ permissions: ["config.read", "config.approve"] });

const MAYA_CHEN: AccountMapping["created_by"] = {
  id: "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a",
  kind: "USER",
  display_name: "Maya Chen",
};
const MARCUS_WEBB: AccountMapping["created_by"] = {
  id: "7e3f9b2c-4d6a-4e8b-a1c3-5d7f9b1e3a5c",
  kind: "USER",
  display_name: "Marcus Webb",
};
function mapping(
  overrides: Partial<AccountMapping> & Pick<AccountMapping, "id" | "version_no" | "status">,
): AccountMapping {
  return {
    name: "AVM-MAP-2026-01",
    notes: null,
    effective_from: "2026-01-01T12:00:00Z",
    effective_to: null,
    rule_count: 3,
    approval_request_id: null,
    pending_approval_request_id: null,
    content_sha256: null,
    impact_simulation_file_id: null,
    published_at: null,
    published_by: null,
    supersedes_version_id: null,
    created_by: MAYA_CHEN,
    row_version: 2,
    created_at: "2025-12-15T08:00:00Z",
    updated_at: "2026-01-02T08:00:00Z",
    ...overrides,
  };
}
const V1 = mapping({
  id: "a1a1a1a1-a1a1-4a1a-8a1a-a1a1a1a1a1a1",
  version_no: 1,
  status: "PUBLISHED",
  published_at: "2026-01-02T08:00:00Z",
  published_by: MARCUS_WEBB,
});
const SUPERSEDED = mapping({
  id: "a0a0a0a0-a0a0-4a0a-8a0a-a0a0a0a0a0a0",
  name: "AVM-MAP-2025-01",
  version_no: 1,
  status: "SUPERSEDED",
  effective_from: "2025-01-01T12:00:00Z",
  effective_to: "2026-01-01T12:00:00Z",
  published_at: "2024-12-20T08:00:00Z",
  published_by: MARCUS_WEBB,
});
const V2 = mapping({
  id: "a2a2a2a2-a2a2-4a2a-8a2a-a2a2a2a2a2a2",
  version_no: 2,
  status: "DRAFT",
  effective_from: "2026-10-01T12:00:00Z",
  supersedes_version_id: V1.id,
  row_version: 1,
});

const REVENUE_ACCOUNT = {
  id: "4000aaaa-0000-4000-8000-000000004000",
  code: "4000",
  name: "Revenue - product",
};
const CLEARING_ACCOUNT = {
  id: "2090aaaa-0000-4000-8000-000000002090",
  code: "2090",
  name: "Subledger clearing",
};
const COGS_ACCOUNT = {
  id: "5000aaaa-0000-4000-8000-000000005000",
  code: "5000",
  name: "Cost of revenue",
};
const ACCOUNTS = [REVENUE_ACCOUNT, CLEARING_ACCOUNT, COGS_ACCOUNT];

function rule(
  id: string,
  versionId: string,
  role: AccountMappingRule["account_role"],
  account: { id: string; code: string; name: string },
  overrides: Partial<AccountMappingRule> = {},
): AccountMappingRule {
  return {
    id,
    account_mapping_version_id: versionId,
    account_role: role,
    clearing_purpose: null,
    entity_id: null,
    book_code: null,
    product_id: null,
    revenue_category: null,
    gl_account: account,
    priority: 100,
    specificity: 0,
    default_dimensions: {},
    ...overrides,
  };
}
const RULES: readonly AccountMappingRule[] = [
  rule("r1r1r1r1-0000-4000-8000-000000000001", V2.id, "REVENUE", REVENUE_ACCOUNT, {
    revenue_category: "PRODUCT",
    specificity: 2,
  }),
  rule("r2r2r2r2-0000-4000-8000-000000000002", V2.id, "BILLING_CLEARING", CLEARING_ACCOUNT, {
    clearing_purpose: "UNAPPLIED_CASH",
  }),
  rule("r3r3r3r3-0000-4000-8000-000000000003", V2.id, "COST_OF_REVENUE", COGS_ACCOUNT),
];

function serve(mappings: readonly AccountMapping[], rules: readonly AccountMappingRule[]) {
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
    http.get(apiUrl("/api/v1/products"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/gl-accounts"), () =>
      HttpResponse.json({ items: ACCOUNTS, next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/account-mappings"), ({ request }) =>
      HttpResponse.json(
        { items: mappings, next_cursor: null },
        {
          headers:
            new URL(request.url).searchParams.get("count") === "true"
              ? { "X-Erev-Total-Count": String(mappings.length) }
              : {},
        },
      ),
    ),
    http.get(apiUrl("/api/v1/account-mappings/:versionId"), ({ params }) => {
      const found = mappings.find((item) => item.id === params.versionId);
      return found === undefined
        ? problemResponse("not-found", 404, "Not found")
        : HttpResponse.json(found);
    }),
    http.get(apiUrl("/api/v1/account-mappings/:versionId/rules"), ({ params }) =>
      HttpResponse.json({
        items: rules.filter((item) => item.account_mapping_version_id === params.versionId),
        next_cursor: null,
      }),
    ),
  );
}

describe("SF-13:account-mapping", () => {
  it("lists the versions with status, dates, rules, author and approver", async () => {
    serve([V2, V1], RULES);
    renderApp("/policies/account-mapping", { me: MARCUS, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-13-grid-account-mappings")).findByRole(
      "grid",
      { name: "Account mappings" },
    );
    const row = await within(grid).findByTestId("SF-13-row-avm-map-2026-01-1");
    expect(within(row).getByRole("link", { name: "AVM-MAP-2026-01" }).getAttribute("href")).toBe(
      `/policies/account-mapping/${V1.id}`,
    );
    expect(within(row).getByText("Published")).toBeTruthy();
    expect(within(row).getByText("01 Jan 2026")).toBeTruthy();
    expect(within(row).getByText("Marcus Webb")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "New mapping version" })).toBeNull();
  });

  it("the grid shows the UTC date of the effective instants and no value for an open end", async () => {
    serve([V1, SUPERSEDED], RULES);
    renderApp("/policies/account-mapping", { me: MARCUS, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-13-grid-account-mappings")).findByRole(
      "grid",
      { name: "Account mappings" },
    );
    const cell = (row: HTMLElement, column: string) =>
      row.querySelector<HTMLElement>(`[data-column="${column}"]`);
    const superseded = await within(grid).findByTestId("SF-13-row-avm-map-2025-01-1");
    expect(cell(superseded, "effective_from")?.textContent).toBe("01 Jan 2025");
    expect(cell(superseded, "effective_to")?.textContent).toBe("01 Jan 2026");
    const published = within(grid).getByTestId("SF-13-row-avm-map-2026-01-1");
    expect(cell(published, "effective_from")?.textContent).toBe("01 Jan 2026");
    // DS-FMT-08: an open end is the em dash with the accessible text "No value".
    const open = cell(published, "effective_to");
    expect(open === null ? null : within(open).getByText("No value")).toBeTruthy();
  });
});

/** The dialog's own read: the newest published version, one row (`fetchPublishedMapping`). */
function readsPublished(request: Request): boolean {
  const query = new URL(request.url).searchParams;
  return query.get("status") === "PUBLISHED" && query.get("limit") === "1";
}

// MAP-DIALOG-UNREAD-PUBLISHED-1: "the published version is not read yet" was taken for "there is
// none". While the read was on its way the dialog said "No mapping is published yet; the draft starts
// without rules." and "Create draft" sent `source_version_id: null` — an empty draft where a copy of
// the published rules was due.
describe("SF-13:account-mapping New mapping version waits for what it copies", () => {
  const FROM_SCRATCH = "No mapping is published yet; the draft starts without rules.";
  const COPIES = "The draft copies the rules of AVM-MAP-2026-01 v1.";
  const UNREAD = "Create draft is unavailable until the published mapping loads.";

  async function openDialog(): Promise<HTMLElement> {
    fireEvent.click(await screen.findByRole("button", { name: "New mapping version" }));
    return screen.findByRole("dialog", { name: "New mapping version" });
  }

  function creations(): unknown[] {
    const bodies: unknown[] = [];
    server.use(
      http.post(apiUrl("/api/v1/account-mappings"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(V2, { status: 201 });
      }),
    );
    return bodies;
  }

  it("while the published version is on its way the dialog says so, offers no Create draft and sends nothing; then it copies", async () => {
    const read = heldRead();
    serve([V1], RULES);
    const bodies = creations();
    server.use(
      http.get(apiUrl("/api/v1/account-mappings"), async ({ request }) => {
        if (!readsPublished(request)) {
          return undefined;
        }
        await read.passed();
        return HttpResponse.json({ items: [V1], next_cursor: null });
      }),
    );
    read.hold();
    renderApp("/policies/account-mapping", { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const dialog = await openDialog();
    await waitFor(() => {
      expect(read.waiting()).toBeGreaterThan(0);
    });
    // Not read is not none: neither sentence about the rules is said yet.
    expect(within(dialog).queryByText(FROM_SCRATCH)).toBeNull();
    expect(within(dialog).queryByText(COPIES)).toBeNull();
    expect(within(dialog).getByText("Loading the published mapping.")).toBeTruthy();
    const create = within(dialog).getByRole("button", { name: "Create draft" });
    expect(create.getAttribute("aria-disabled")).toBe("true");
    const name = within(dialog).getByRole("textbox", { name: /^Name/ });
    fireEvent.change(name, { target: { value: "AVM-MAP-2026-02" } });
    fireEvent.click(create);
    const form = name.closest("form");
    expect(form).not.toBeNull();
    fireEvent.submit(form as HTMLFormElement);
    // The button says why it is unavailable (DS-CMP-20: the reason describes the control).
    expect(
      document.getElementById(create.getAttribute("aria-describedby") ?? "")?.textContent,
    ).toBe(UNREAD);
    expect(bodies).toEqual([]);

    read.release();
    expect(await within(dialog).findByText(COPIES)).toBeTruthy();
    // The button is read again: without a reason it is another element than the one described by it.
    const ready = within(dialog).getByRole("button", { name: "Create draft" });
    expect(ready.getAttribute("aria-disabled")).toBeNull();
    fireEvent.click(ready);
    await waitFor(() => {
      expect(bodies).toEqual([
        { name: "AVM-MAP-2026-02", effective_from: null, source_version_id: V1.id },
      ]);
    });
  });

  it("a workspace without a published mapping is told so once the read has answered, and its draft starts without rules", async () => {
    serve([], RULES);
    const bodies = creations();
    renderApp("/policies/account-mapping", { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const dialog = await openDialog();
    expect(await within(dialog).findByText(FROM_SCRATCH)).toBeTruthy();
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Name/ }), {
      target: { value: "AVM-MAP-2026-01" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create draft" }));
    await waitFor(() => {
      expect(bodies).toEqual([
        { name: "AVM-MAP-2026-01", effective_from: null, source_version_id: null },
      ]);
    });
  });

  it("a published version that cannot be read is said, with Retry, and nothing is created until it is read", async () => {
    let failing = true;
    serve([V1], RULES);
    const bodies = creations();
    server.use(
      http.get(apiUrl("/api/v1/account-mappings"), ({ request }) => {
        if (!readsPublished(request) || !failing) {
          return undefined;
        }
        return problemResponse("internal-error", 500, "Something went wrong");
      }),
    );
    renderApp("/policies/account-mapping", { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const dialog = await openDialog();
    expect(
      await within(dialog).findByText("The published mapping could not be loaded."),
    ).toBeTruthy();
    expect(within(dialog).queryByText(FROM_SCRATCH)).toBeNull();
    const create = within(dialog).getByRole("button", { name: "Create draft" });
    expect(create.getAttribute("aria-disabled")).toBe("true");
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Name/ }), {
      target: { value: "AVM-MAP-2026-02" },
    });
    fireEvent.click(create);
    expect(bodies).toEqual([]);

    failing = false;
    fireEvent.click(within(dialog).getByRole("button", { name: "Retry" }));
    expect(await within(dialog).findByText(COPIES)).toBeTruthy();
    expect(within(dialog).queryByText("The published mapping could not be loaded.")).toBeNull();
    fireEvent.click(within(dialog).getByRole("button", { name: "Create draft" }));
    await waitFor(() => {
      expect(bodies).toEqual([
        { name: "AVM-MAP-2026-02", effective_from: null, source_version_id: V1.id },
      ]);
    });
  });
});

describe("SF-13:account-mapping effective date (DS-I18N-08; supervisor ruling R-59)", () => {
  it("New mapping version sends the picked effective date as 12:00:00Z, and no instant without a date", async () => {
    const bodies: unknown[] = [];
    serve([V1], RULES);
    server.use(
      http.post(apiUrl("/api/v1/account-mappings"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(V2, { status: 201 });
      }),
    );
    const open = async () => {
      fireEvent.click(await screen.findByRole("button", { name: "New mapping version" }));
      const dialog = await screen.findByRole("dialog", { name: "New mapping version" });
      // The dialog has read the published version it copies (VITEST-LIVENESS-2): the body names it.
      await within(dialog).findByText("The draft copies the rules of AVM-MAP-2026-01 v1.");
      return dialog;
    };
    const view = renderApp("/policies/account-mapping", { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const dated = await open();
    fireEvent.change(within(dated).getByRole("textbox", { name: /^Name/ }), {
      target: { value: "AVM-MAP-2026-02" },
    });
    const field = within(dated).getByRole("textbox", { name: /^Effective from/ });
    fireEvent.change(field, { target: { value: "2026-10-01" } });
    fireEvent.blur(field);
    fireEvent.click(within(dated).getByRole("button", { name: "Create draft" }));
    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe(`/policies/account-mapping/${V2.id}`),
    );
    // The draft's page is on screen before the case leaves it, and the list is on screen again
    // before its button is pressed: a press lands on the page the router shows.
    await screen.findByTestId("SF-13-account-mapping-version-page");

    await view.router.navigate("/policies/account-mapping");
    await screen.findByTestId("SF-13-account-mapping-page");
    const undated = await open();
    fireEvent.change(within(undated).getByRole("textbox", { name: /^Name/ }), {
      target: { value: "AVM-MAP-2026-03" },
    });
    fireEvent.click(within(undated).getByRole("button", { name: "Create draft" }));
    await waitFor(() => expect(bodies).toHaveLength(2));

    // AccountMappingIn `effective_from` is date-time or null: an RFC 3339 UTC instant, never a date.
    expect(bodies).toEqual([
      {
        name: "AVM-MAP-2026-02",
        effective_from: "2026-10-01T12:00:00Z",
        source_version_id: V1.id,
      },
      { name: "AVM-MAP-2026-03", effective_from: null, source_version_id: V1.id },
    ]);
  });

  it("Save effective date sends 12:00:00Z of the picked date, and the stored instant reads back as that date", async () => {
    const patches: { readonly ifMatch: string | null; readonly body: unknown }[] = [];
    let stored = V2;
    serve([V1], RULES);
    server.use(
      http.get(apiUrl(`/api/v1/account-mappings/${V2.id}`), () => HttpResponse.json(stored)),
      http.patch(apiUrl(`/api/v1/account-mappings/${V2.id}`), async ({ request }) => {
        const body = (await request.json()) as { readonly effective_from: string };
        patches.push({ ifMatch: request.headers.get("If-Match"), body });
        stored = { ...stored, effective_from: body.effective_from, row_version: 2 };
        return HttpResponse.json(stored);
      }),
    );
    renderApp(`/policies/account-mapping/${V2.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const field = await screen.findByRole<HTMLInputElement>("textbox", {
      name: /^Effective from/,
    });
    expect(field.value).toBe("01 Oct 2026");
    fireEvent.change(field, { target: { value: "2026-11-01" } });
    fireEvent.blur(field);
    fireEvent.click(screen.getByRole("button", { name: "Save effective date" }));

    expect(await screen.findByText("Saved the effective date.")).toBeTruthy();
    // AccountMappingUpdateIn `effective_from` is date-time: an RFC 3339 UTC instant, never a date.
    expect(patches).toEqual([
      { ifMatch: '"r1"', body: { effective_from: "2026-11-01T12:00:00Z" } },
    ]);
    // The round trip: the refetched instant shows the date that was picked and nothing is pending.
    await waitFor(() => expect(screen.getAllByText("Effective 01 Nov 2026")).toHaveLength(2));
    expect(field.value).toBe("01 Nov 2026");
    expect(
      screen.getByRole("button", { name: "Save effective date" }).getAttribute("aria-disabled"),
    ).toBe("true");
  });
});

describe("SF-13:account-mapping-version", () => {
  it("clearing purpose required for billing clearing", async () => {
    const bodies: unknown[] = [];
    serve([V2, V1], RULES);
    server.use(
      http.post(apiUrl(`/api/v1/account-mappings/${V2.id}/rules`), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(
          rule("r9r9r9r9-0000-4000-8000-000000000009", V2.id, "REVENUE", REVENUE_ACCOUNT),
          { status: 201 },
        );
      }),
    );
    renderApp(`/policies/account-mapping/${V2.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const grid = await within(await screen.findByTestId("SF-13-grid-mapping-rules")).findByRole(
      "grid",
      { name: "Mapping rules" },
    );
    expect(await within(grid).findByText("Unapplied cash")).toBeTruthy();
    expect(within(grid).getAllByRole("row").length).toBeGreaterThanOrEqual(4);
    fireEvent.click(screen.getByRole("button", { name: "Add rule" }));

    const dialog = await screen.findByRole("dialog", { name: "Add rule" });
    fireEvent.click(within(dialog).getByRole("combobox", { name: /^Account role/ }));
    fireEvent.mouseDown(await screen.findByRole("option", { name: /^Billing clearing/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save rule" }));
    expect(
      await within(dialog).findByText("Choose a clearing purpose for billing clearing."),
    ).toBeTruthy();
    expect(bodies).toEqual([]);

    fireEvent.click(within(dialog).getByRole("combobox", { name: /^Account role/ }));
    fireEvent.mouseDown(await screen.findByRole("option", { name: /^Revenue\b/ }));
    expect(
      within(dialog).queryByText("Choose a clearing purpose for billing clearing."),
    ).toBeNull();
    const purpose = within(dialog).getByRole("combobox", { name: /^Clearing purpose/ });
    expect(purpose.getAttribute("aria-disabled")).toBe("true");
    expect(within(dialog).getByText("Only billing clearing has a clearing purpose.")).toBeTruthy();

    const account = within(dialog).getByRole("combobox", { name: /^GL account/ });
    fireEvent.change(account, { target: { value: "4000" } });
    fireEvent.mouseDown(await screen.findByRole("option", { name: "4000 Revenue - product" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save rule" }));

    expect(await screen.findByText("Added the Revenue rule.")).toBeTruthy();
    expect(bodies).toEqual([
      {
        account_role: "REVENUE",
        clearing_purpose: null,
        entity_id: null,
        book_code: null,
        product_id: null,
        revenue_category: null,
        gl_account_id: REVENUE_ACCOUNT.id,
        priority: 100,
        default_dimensions: {},
      },
    ]);
    expect(ruleDraftErrors({ ...EMPTY_RULE_DRAFT, role: "BILLING_CLEARING" })).toEqual([
      "clearingPurposeRequired",
      "glAccount",
    ]);
    expect(
      ruleDraftErrors({
        ...EMPTY_RULE_DRAFT,
        role: "REVENUE",
        clearingPurpose: "BILLING",
        glAccountId: "x",
      }),
    ).toEqual(["clearingPurposeForbidden"]);
  });

  it("the chip, the lifecycle caption and the field show the UTC date of the effective instant", async () => {
    serve([V2, V1], RULES);
    renderApp(`/policies/account-mapping/${V2.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });

    const field = await screen.findByRole("textbox", { name: /^Effective from/ });
    expect((field as HTMLInputElement).value).toBe("01 Oct 2026");
    // The record header chip and the "Published" step caption.
    expect(screen.getAllByText("Effective 01 Oct 2026")).toHaveLength(2);
    // The unchanged date is not a pending change.
    expect(
      screen.getByRole("button", { name: "Save effective date" }).getAttribute("aria-disabled"),
    ).toBe("true");
  });

  it("coverage shows not mapped", async () => {
    serve([V2, V1], RULES);
    renderApp(`/policies/account-mapping/${V2.id}?pane=coverage`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const table = await screen.findByRole("table", { name: "Role coverage" });
    expect(table.getAttribute("data-testid")).toBe("SF-13-grid-coverage");
    expect(within(table).getAllByRole("row")).toHaveLength(39);

    const revenue = within(table).getByTestId("SF-13-coverage-REVENUE");
    expect(within(revenue).getByText("Mapped · 1 rule")).toBeTruthy();
    const preStandard = within(table).getByTestId("SF-13-coverage-PRE_STANDARD_REVENUE");
    expect(within(preStandard).getByText("Not mapped")).toBeTruthy();
    expect(
      within(preStandard).getByText(
        "Postings that need this role fail with ACCOUNT_MAPPING_MISSING.",
      ),
    ).toBeTruthy();
    const unapplied = within(table).getByTestId("SF-13-coverage-BILLING_CLEARING-UNAPPLIED_CASH");
    expect(within(unapplied).getByText("Mapped · 1 rule")).toBeTruthy();
    const billing = within(table).getByTestId("SF-13-coverage-BILLING_CLEARING-BILLING");
    expect(within(billing).getByText("Not mapped")).toBeTruthy();

    const reserved = within(table).getByTestId("SF-13-coverage-RETAINED_EARNINGS");
    expect(reserved.className).toContain("text-fg-3");
    expect(within(reserved).queryByText("Not mapped")).toBeNull();
    expect(within(reserved).getByText("Reserved: no mapping allowed")).toBeTruthy();

    const rows = coverageRows(RULES);
    expect(rows).toHaveLength(38);
    expect(rows.filter((row) => row.status === "reserved").map((row) => row.role)).toEqual([
      "RETAINED_EARNINGS",
      "FINANCING_OBLIGATION",
    ]);
    expect(ruleChanges(RULES, RULES.slice(0, 2))).toEqual({ added: [RULES[2]], removed: [] });
  });
});

// docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): a message that names a member no
// field shows was shown nowhere; "Save effective date" had no banner at all, so every refusal that
// named no date was shown nowhere. What a field shows is not said by the banner.
describe("SF-13:account-mapping-version, a refused command", () => {
  const NO_FIELD = "A version that waits for approval cannot change.";

  it("Save effective date: the banner lists what the date does not show, and after a 412 that the record changed", async () => {
    const atDate = "Choose a date later than today.";
    let status = 422;
    serve([V1], RULES);
    server.use(
      http.get(apiUrl(`/api/v1/account-mappings/${V2.id}`), () => HttpResponse.json(V2)),
      http.patch(apiUrl(`/api/v1/account-mappings/${V2.id}`), () =>
        refusedWith({ status: NO_FIELD, effective_from: atDate }, { status }),
      ),
    );
    renderApp(`/policies/account-mapping/${V2.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    const field = await screen.findByRole<HTMLInputElement>("textbox", {
      name: /^Effective from/,
    });
    fireEvent.change(field, { target: { value: "2026-11-01" } });
    fireEvent.blur(field);
    fireEvent.click(screen.getByRole("button", { name: "Save effective date" }));

    const heading = await screen.findByRole("heading", { name: REFUSAL_TITLE });
    expect(heading.closest('[role="alert"]')?.textContent).toBe(
      REFUSAL_TITLE + NO_FIELD + REFUSAL_REFERENCE,
    );
    expect(describedBy(field)).toContain(atDate);

    status = 412;
    fireEvent.click(screen.getByRole("button", { name: "Save effective date" }));
    expect(await screen.findByRole("heading", { name: RECORD_CHANGED })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: REFUSAL_TITLE })).toBeNull();
  });

  it("New mapping version: the banner lists what no field shows and leaves the name's message at its field", async () => {
    const atName = "A mapping of this name exists.";
    serve([V1], RULES);
    server.use(
      http.post(apiUrl("/api/v1/account-mappings"), () =>
        refusedWith({ source_version_id: NO_FIELD, name: atName }),
      ),
    );
    renderApp("/policies/account-mapping", { me: MAYA, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(await screen.findByRole("button", { name: "New mapping version" }));
    const dialog = await screen.findByRole("dialog", { name: "New mapping version" });
    const name = within(dialog).getByRole("textbox", { name: /^Name/ });
    fireEvent.change(name, { target: { value: "FY2027 mapping" } });
    const create = within(dialog).getByRole("button", { name: "Create draft" });
    await waitFor(() => expect(create.getAttribute("aria-disabled")).toBeNull());
    fireEvent.click(create);

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + NO_FIELD + REFUSAL_REFERENCE);
    expect(describedBy(name)).toContain(atName);
  });

  it("Add rule: the banner lists what no field shows and leaves the priority's message at its field", async () => {
    const atPriority = "A rule of this role has this priority.";
    serve([V2, V1], RULES);
    server.use(
      http.post(apiUrl(`/api/v1/account-mappings/${V2.id}/rules`), () =>
        refusedWith({ book_code: NO_FIELD, priority: atPriority }),
      ),
    );
    renderApp(`/policies/account-mapping/${V2.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    await within(await screen.findByTestId("SF-13-grid-mapping-rules")).findByRole("grid", {
      name: "Mapping rules",
    });
    fireEvent.click(screen.getByRole("button", { name: "Add rule" }));
    const dialog = await screen.findByRole("dialog", { name: "Add rule" });
    fireEvent.click(within(dialog).getByRole("combobox", { name: /^Account role/ }));
    fireEvent.mouseDown(await screen.findByRole("option", { name: /^Revenue\b/ }));
    const account = within(dialog).getByRole("combobox", { name: /^GL account/ });
    fireEvent.change(account, { target: { value: "4000" } });
    fireEvent.mouseDown(await screen.findByRole("option", { name: "4000 Revenue - product" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save rule" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + NO_FIELD + REFUSAL_REFERENCE);
    expect(describedBy(within(dialog).getByLabelText(/^Priority/))).toContain(atPriority);
  });

  it("Remove rule: the pane has no field for a message, so the banner says every sentence", async () => {
    serve([V2, V1], RULES);
    server.use(
      http.delete(apiUrl(`/api/v1/account-mappings/${V2.id}/rules/:ruleId`), () =>
        refusedWith({ status: NO_FIELD }),
      ),
    );
    renderApp(`/policies/account-mapping/${V2.id}`, { me: MAYA, screenRoutes: SCREEN_ROUTES });
    const grid = await within(await screen.findByTestId("SF-13-grid-mapping-rules")).findByRole(
      "grid",
      { name: "Mapping rules" },
    );
    const [first] = await within(grid).findAllByRole("button", { name: "Remove rule" });
    fireEvent.click(first as HTMLElement);
    const pane = screen.getByTestId("SF-13-pane-rules");
    const confirm = (await within(pane).findByRole("heading", { name: /^Remove the / })).closest(
      '[data-tone="warning"]',
    );
    fireEvent.click(within(confirm as HTMLElement).getByRole("button", { name: "Remove rule" }));

    const heading = await within(pane).findByRole("heading", { name: REFUSAL_TITLE });
    expect(heading.closest('[role="alert"]')?.textContent).toBe(
      REFUSAL_TITLE + NO_FIELD + REFUSAL_REFERENCE,
    );
  });
});
