// @vitest-environment jsdom
// SF-02 Contracts list (BUILD_SPEC CTR-21; SCREENS §3.4 quick lists and bindings, §3.5 columns, §3.6
// filters, §3.8 states; DESIGN_SYSTEM DS-FMT-28; docs/dev-guide.md DG-FE-03, DG-FE-08; 04 API-R-28,
// API-R-16): a quick list is `view=<literal>` and `quick_list=<literal>`; the grid renders the API's amount
// strings and no signed balance; chips and the context reach the API; a saved-view link restores its
// filters; a member without `contract.read` sees the access-limited state.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { NO_VALUE } from "../../lib/format";
import { installMemoryStorage, MEMBERSHIP_ID, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, server } from "../../test/msw";
import { workbenchContract } from "../../test/workbench";

installMswServer();
installMemoryStorage();
installGridViewport();

afterEach(() => {
  cleanup();
});

const MAYA = signedInMe({ permissions: ["contract.read", "contract.create", "config.read"] });

function entity(code: string, name: string) {
  return {
    id: `0a1b2c3d-4e5f-4a6b-8c7d-${code === "AVM-US" ? "000000000001" : "000000000002"}`,
    code,
    name,
    functional_currency: code === "AVM-US" ? "USD" : "GBP",
    is_active: true,
    books: [{ book_code: "ASC606", is_enabled: true }],
  };
}

const PERIOD = {
  period: {
    id: "1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f",
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
};

/** PRD §2.7 K-01 as a list item (API-S-Contract without `kpis.balances` and `links`). */
function contract(overrides: Readonly<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    id: "9a8b7c6d-5e4f-4a3b-9c2d-1e0f9a8b7c6d",
    external_id: "SF-ORD-10001",
    contract_no: "C-000001",
    customer: {
      id: "2b3c4d5e-6f70-4a81-9b92-a3b4c5d6e7f8",
      code: "C-01",
      name: "Pellworth Logistics Inc. (Demo)",
    },
    contracting_entity: { id: entity("AVM-US", "").id, code: "AVM-US", name: "Avenmoor US Inc." },
    status: "ACTIVE",
    status_reason: null,
    on_hold: false,
    combination_group: {
      id: "3c4d5e6f-7081-4a92-8ba3-b4c5d6e7f809",
      code: "CG-000001",
      is_singleton: true,
    },
    inception_date: "2026-01-01",
    signature_date: "2025-12-15",
    transaction_currency: "USD",
    source_system: "SALESFORCE",
    region: "NA",
    channel: "Direct",
    contract_type: "Subscription",
    open_exception_count: 0,
    head_stream_version: 4,
    kpis: {
      transaction_price: { amount: "135000.00", currency: "USD" },
      revenue_to_date: { amount: "105055.89", currency: "USD" },
      billed_to_date: { amount: "135000.00", currency: "USD" },
      rpo: { amount: "29944.11", currency: "USD" },
      scheduled: { amount: "29944.11", currency: "USD" },
      awaiting_trigger: { amount: "0.00", currency: "USD" },
    },
    kpis_ratios: { billed: "1.000000", recognized: "0.778192", pending_trigger_count: 0 },
    steps: [],
    context: null,
    created_at: "2026-01-02T10:00:00Z",
    updated_at: "2026-09-10T10:00:00Z",
    ...overrides,
  };
}

interface Served {
  readonly contracts?: readonly Record<string, unknown>[];
  readonly views?: readonly Record<string, unknown>[];
}

/** The shell's reads and the screen's reads; each `GET /contracts` search is recorded. */
function serve(searches: string[], { contracts = [contract()], views = [] }: Served = {}) {
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), () =>
      HttpResponse.json({
        items: [entity("AVM-UK", "Avenmoor UK Ltd"), entity("AVM-US", "Avenmoor US Inc.")],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/books"), () =>
      HttpResponse.json({
        items: [{ code: "ASC606", name: "ASC 606", is_enabled: true, is_primary: true }],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/periods"), () =>
      HttpResponse.json({ items: [PERIOD], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/customers"), () =>
      HttpResponse.json({
        items: [{ id: "2b3c4d5e-6f70-4a81-9b92-a3b4c5d6e7f8", code: "C-01", name: "Pellworth" }],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/currencies"), () =>
      HttpResponse.json({
        items: [
          { code: "USD", minor_unit: 2, name: "US Dollar", numeric_code: "840", is_active: true },
        ],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/saved-views"), () =>
      HttpResponse.json({ items: views, next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/contracts"), ({ request }) => {
      const url = new URL(request.url);
      searches.push(url.search);
      const counting = url.searchParams.get("count") === "true";
      return HttpResponse.json(
        { items: contracts, next_cursor: null },
        { headers: counting ? { "X-Erev-Total-Count": String(contracts.length) } : {} },
      );
    }),
  );
}

/** The recorded searches without the paging parameters `limit`, `cursor` and `count`. */
function bindings(searches: readonly string[]): string[] {
  return searches.map((search) => {
    const params = new URLSearchParams(search);
    params.delete("limit");
    params.delete("cursor");
    params.delete("count");
    return params.toString();
  });
}

function grid(): HTMLElement {
  return within(screen.getByTestId("SF-02-grid-contracts")).getByRole("grid", {
    name: "Contracts",
  });
}

/** The grid once the lazy route has loaded. */
async function findGrid(): Promise<HTMLElement> {
  return within(await screen.findByTestId("SF-02-grid-contracts")).findByRole("grid", {
    name: "Contracts",
  });
}

describe("SF-02 contracts list", () => {
  it("quick list sends literal", async () => {
    const searches: string[] = [];
    serve(searches);
    const { router } = renderApp("/contracts", { me: MAYA, screenRoutes: SCREEN_ROUTES });

    expect(
      await within(await findGrid()).findByRole("rowheader", { name: "SF-ORD-10001" }),
    ).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1, name: "Contracts" })).toBeTruthy();
    // The grid count label follows the loading flag in a later commit (F-ADM latent-race sweep).
    expect(await screen.findByText("1 contract")).toBeTruthy();
    expect(bindings(searches)).toEqual(["sort=-updated_at"]);

    fireEvent.click(screen.getByRole("button", { name: "View: All contracts" }));
    const menu = screen.getByRole("menu", { name: "Views" });
    expect(
      within(within(menu).getByRole("group", { name: "Quick lists" }))
        .getAllByRole("menuitemradio")
        .map((item) => item.textContent),
    ).toEqual([
      "All contracts",
      "Recently viewed",
      "On hold",
      "Largest value",
      "Modified this period",
      "Created manually",
      "Created from integrations this period",
    ]);
    fireEvent.click(within(menu).getByRole("menuitemradio", { name: "Largest value" }));

    await waitFor(() => {
      expect(new URLSearchParams(router.state.location.search).get("view")).toBe("LARGEST_VALUE");
    });
    await waitFor(() => {
      expect(bindings(searches)).toContain("quick_list=LARGEST_VALUE&sort=-transaction_price");
    });
    expect(screen.getByRole("button", { name: "View: Largest value" })).toBeTruthy();
  });

  it("signed position never rendered", async () => {
    const searches: string[] = [];
    serve(searches, {
      contracts: [
        contract(),
        contract({
          id: "4d5e6f70-8192-4aa3-9bb4-c5d6e7f8091a",
          external_id: "BG-AVM-0020",
          status: "DRAFT",
          kpis: null,
        }),
        contract({
          id: "5e6f7081-92a3-4bb4-8cc5-d6e7f8091a2b",
          external_id: "PRJ-CB-2026-01",
          on_hold: true,
          combination_group: {
            id: "6f708192-a3b4-4cc5-9dd6-e7f8091a2b3c",
            code: "CG-000009",
            is_singleton: false,
          },
          kpis: {
            transaction_price: { amount: "9007199254740993.01", currency: "USD" },
            revenue_to_date: { amount: "600000.00", currency: "USD" },
            billed_to_date: { amount: "650000.00", currency: "USD" },
            rpo: { amount: "400000.00", currency: "USD" },
            scheduled: { amount: "0.00", currency: "USD" },
            awaiting_trigger: { amount: "0.00", currency: "USD" },
          },
        }),
      ],
    });
    renderApp("/contracts", { me: MAYA, screenRoutes: SCREEN_ROUTES });
    const rows = await within(await findGrid()).findAllByRole("rowheader");
    expect(rows.map((row) => row.textContent)).toEqual([
      "SF-ORD-10001",
      "BG-AVM-0020",
      "PRJ-CB-2026-01",
    ]);

    // SCREENS §3.5: the visible columns by default, none of them a balance or a signed position, then
    // the DS-CMP-10 row-actions column, which renders once SF-03 (RT-10) is built (BUILD_SPEC CTR-22).
    expect(
      within(grid())
        .getAllByRole("columnheader")
        .map((header) => header.textContent?.trim() ?? "")
        .filter((text) => text !== ""),
    ).toEqual([
      "Contract",
      "Customer",
      "Status",
      "Entity",
      "Inception date",
      "Currency",
      "Transaction price",
      "Recognized to date",
      "Billed to date",
      "RPO",
      "Open exceptions",
      "Actions",
    ]);

    const k01 = screen.getByTestId("SF-02-row-sf-ord-10001");
    for (const figure of ["135,000.00", "105,055.89", "29,944.11"]) {
      expect(within(k01).getAllByText(figure).length).toBeGreaterThan(0);
    }
    // A price beyond Number.MAX_SAFE_INTEGER keeps every digit: the string is never a JavaScript number.
    const k03 = screen.getByTestId("SF-02-row-prj-cb-2026-01");
    expect(within(k03).getByText("9,007,199,254,740,993.01")).toBeTruthy();
    expect(within(k03).getByText("On hold")).toBeTruthy();
    expect(within(k03).getByText("Combined")).toBeTruthy();
    // A draft without a computed version shows no value, not a zero.
    const draft = screen.getByTestId("SF-02-row-bg-avm-0020");
    expect(within(draft).getByText("Draft")).toBeTruthy();
    expect(within(draft).queryByText("0.00")).toBeNull();
    // `kpis: null` is also what a row carries whose figures the API refuses at the period (04 API-C-10,
    // rev 1.132; SCREENS §4.1.8 rev 1.21): each of the four figure columns shows the no-value sign.
    expect(
      within(draft)
        .getAllByRole("gridcell")
        .map((cell) => cell.textContent)
        .filter((text) => text === `${NO_VALUE}No value`),
    ).toHaveLength(4);

    for (const cell of within(grid()).getAllByRole("gridcell")) {
      const text = cell.textContent?.trim() ?? "";
      expect(text).not.toMatch(/^[-−+(]/);
    }
  });

  // DG-FE-05 rev 1.156 (item W-23): the bulk action commands each contract under a key of its own, and
  // the keys are the page's.
  it("a bulk command that gets no answer goes out under the same key when the action is run again", async () => {
    const LOST = "4d5e6f70-8192-4aa3-9bb4-c5d6e7f8091a";
    const DONE = "5e6f7081-92a3-4bb4-8cc5-d6e7f8091a2b";
    serve([], {
      contracts: [
        contract({ id: LOST, external_id: "BG-AVM-0020", status: "DRAFT" }),
        contract({ id: DONE, external_id: "BG-AVM-0021", status: "DRAFT" }),
      ],
    });
    const sent: { readonly id: string; readonly key: string | null }[] = [];
    let lose = true;
    server.use(
      http.post(
        apiUrl("/api/v1/contracts/:contractId/submit-activation"),
        ({ request, params }) => {
          const id = String(params.contractId);
          sent.push({ id, key: request.headers.get("Idempotency-Key") });
          if (id === LOST && lose) {
            lose = false;
            return HttpResponse.error();
          }
          return HttpResponse.json(workbenchContract({ id, status: "PENDING_REVIEW" }));
        },
      ),
    );
    renderApp("/contracts", { me: MAYA, screenRoutes: SCREEN_ROUTES });
    await within(await findGrid()).findAllByRole("rowheader");

    const run = async (title: string) => {
      // The rows stay selected after a run: select them only when they are not.
      const all = screen.getByRole("checkbox", { name: "Select loaded rows" });
      if (!(all as HTMLInputElement).checked) {
        fireEvent.click(all);
      }
      fireEvent.click(await screen.findByRole("button", { name: "Submit for activation" }));
      const result = await screen.findByRole("dialog", { name: title });
      const text = result.textContent ?? "";
      fireEvent.click(within(result).getByRole("button", { name: "Done" }));
      await waitFor(() => {
        expect(screen.queryByRole("dialog", { name: title })).toBeNull();
      });
      return text;
    };

    // First run: one contract's answer is lost, the other is submitted.
    expect(await run("Submitted 1 of 2 contracts")).toContain(
      "BG-AVM-0020The request did not reach the server.",
    );
    // Second run of the same action on the same rows.
    await run("Submitted 2 of 2 contracts");

    expect(sent.map((item) => item.id)).toEqual([LOST, DONE, LOST, DONE]);
    // The command without an answer goes out under its old key: if the API did carry it out, it
    // replays that answer and submits nothing twice.
    expect(sent[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
    expect(sent[2]?.key).toBe(sent[0]?.key);
    // The command that succeeded is a new one when the user runs it again.
    expect(sent[3]?.key).not.toBe(sent[1]?.key);
    expect(sent[1]?.key).not.toBe(sent[0]?.key);
  });

  it("chips, the context entity and book and the period end date reach GET /contracts", async () => {
    const searches: string[] = [];
    serve(searches);
    renderApp(
      "/contracts?entity=AVM-US&period=FY2026-P09&book=ASC606&f.entity=in:AVM-UK,AVM-US" +
        "&f.status=in:ACTIVE&f.on_hold=is:true&f.transaction_price=between:100000,200000",
      { me: MAYA, screenRoutes: SCREEN_ROUTES },
    );

    expect(
      await within(await findGrid()).findByRole("rowheader", { name: "SF-ORD-10001" }),
    ).toBeTruthy();
    const toolbar = screen.getByRole("toolbar", { name: "Filters" });
    expect(
      within(toolbar).getByRole("button", { name: "Status is Active, edit filter" }),
    ).toBeTruthy();
    expect(bindings(searches)).toEqual([
      "entity=AVM-UK&entity=AVM-US&status=ACTIVE&on_hold=true&value_min=100000" +
        "&value_max=200000&book=ASC606&as_of=2026-09-30&sort=-updated_at",
    ]);
  });

  it("the Status editor with one value writes f.status=is:ACTIVE and requests status=ACTIVE", async () => {
    const searches: string[] = [];
    serve(searches);
    const { router } = renderApp("/contracts", { me: MAYA, screenRoutes: SCREEN_ROUTES });
    expect(
      await within(await findGrid()).findByRole("rowheader", { name: "SF-ORD-10001" }),
    ).toBeTruthy();

    const toolbar = screen.getByRole("toolbar", { name: "Filters" });
    fireEvent.click(within(toolbar).getByRole("button", { name: "Filter" }));
    fireEvent.click(
      within(screen.getByRole("dialog", { name: "Filter" })).getByRole("button", {
        name: "Status",
      }),
    );
    const editor = screen.getByRole("dialog", { name: "Status filter" });
    fireEvent.click(within(editor).getByRole("checkbox", { name: "Active" }));
    fireEvent.click(within(editor).getByRole("button", { name: "Apply" }));

    expect(
      await within(toolbar).findByRole("button", { name: "Status is Active, edit filter" }),
    ).toBeTruthy();
    expect(new URLSearchParams(router.state.location.search).get("f.status")).toBe("is:ACTIVE");
    await waitFor(() => {
      expect(bindings(searches)).toContain("status=ACTIVE&sort=-updated_at");
    });
  });

  it("a link naming a saved view restores its filters", async () => {
    const searches: string[] = [];
    serve(searches, {
      views: [
        {
          id: "7a8b9c0d-1e2f-4a3b-8c4d-5e6f7a8b9c0d",
          membership_id: MEMBERSHIP_ID,
          screen_code: "SF-02",
          name: "Active US",
          config: {
            columns: [
              "contract",
              "customer",
              "status",
              "entity",
              "inception_date",
              "currency",
              "transaction_price",
              "revenue_to_date",
              "billed_to_date",
              "rpo",
              "open_exceptions",
            ],
            widths: {},
            pinned: { start: ["contract"], end: [] },
            sort: null,
            filters: { status: "in:ACTIVE", entity: "in:AVM-US" },
            query: "",
            currency_view: null,
          },
          is_shared: false,
          is_favourite: false,
          created_at: "2026-09-13T09:00:00Z",
          updated_at: "2026-09-13T09:00:00Z",
          row_version: 1,
        },
      ],
    });
    const { router } = renderApp("/contracts?view=7a8b9c0d-1e2f-4a3b-8c4d-5e6f7a8b9c0d", {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    await waitFor(() => {
      const params = new URLSearchParams(router.state.location.search);
      expect(params.get("f.status")).toBe("in:ACTIVE");
      expect(params.get("f.entity")).toBe("in:AVM-US");
    });
    expect(await screen.findByRole("button", { name: "View: Active US" })).toBeTruthy();
    await waitFor(() => {
      expect(bindings(searches)).toContain("entity=AVM-US&status=ACTIVE&sort=-updated_at");
    });
  });

  it("without contract.read the access-limited state renders and nothing is read", async () => {
    const searches: string[] = [];
    serve(searches);
    renderApp("/contracts", {
      me: signedInMe({ permissions: ["config.read"] }),
      screenRoutes: SCREEN_ROUTES,
    });

    expect(
      await screen.findByRole("heading", { name: "You do not have access to contracts" }),
    ).toBeTruthy();
    expect(
      screen.getByText("Ask a workspace administrator for a role that includes viewing contracts."),
    ).toBeTruthy();
    expect(searches).toEqual([]);
  });
});
