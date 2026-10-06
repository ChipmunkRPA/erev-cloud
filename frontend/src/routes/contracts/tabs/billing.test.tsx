// @vitest-environment jsdom
// SF-03:billing Billing tab (BUILD_SPEC CTR-23; SCREENS §4.4; DESIGN_SYSTEM DS-FMT-28; D-12; 04
// API-S-ContractBalance, API-R-30): the balances table renders contract liability, contract asset and
// unbilled receivable per entity, a cell an Explain trigger where its row names the explanation (SCREENS
// §4.4 rev 1.24; 04 API-S-ContractBalance `links`, rev 1.174), zero rows under "Show zero balances", and
// never the signed `net_position` member; the invoices grid reads the billing events.
import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../../app/router";
import { installMemoryStorage, renderApp, signedInMe } from "../../../test/app";
import { installGridViewport } from "../../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";

installMswServer();
installMemoryStorage();
installGridViewport();
// The workbench reads the periods, then the contract and its obligations, before the tab renders.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
});

const MAYA = signedInMe({
  permissions: [
    "contract.read",
    "contract.create",
    "config.read",
    "event.record",
    "judgement.create",
  ],
});

const CONTRACT_ID = "4b5c6d7e-8f90-4a1b-9c2d-3e4f5a6b7c8d";
const VERSION_ID = "5c6d7e8f-90a1-4b2c-8d3e-4f5a6b7c8d9e";
const O1_ID = "6d7e8f90-a1b2-4c3d-9e4f-5a6b7c8d9e0f";
const CONTEXT = "entity=AVM-US&period=FY2026-P09&book=ASC606";
// The T-CON-09 rows of the two entities: ids of their own, which only the balance links carry.
const BALANCE_US_ID = "7e8f90a1-b2c3-4d4e-8f5a-6b7c8d9e0f1a";
const BALANCE_UK_ID = "8f90a1b2-c3d4-4e5f-9a6b-7c8d9e0f1a2b";

const AVM_US = {
  id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000001",
  code: "AVM-US",
  name: "Avenmoor US Inc.",
};
const AVM_UK = {
  id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000002",
  code: "AVM-UK",
  name: "Avenmoor UK Ltd.",
};

function money(amount: string, currency = "USD") {
  return { amount, currency };
}

const VERSION_CONTEXT = {
  as_of: "2026-09-30",
  book: "ASC606",
  contract_version_id: VERSION_ID,
  known_at: "2026-09-12T12:00:00Z",
  version_no: 5,
};

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

/** PRD §2.7 K-02 `SF-ORD-10002` (API-S-Contract). */
const CONTRACT = {
  id: CONTRACT_ID,
  external_id: "SF-ORD-10002",
  contract_no: "C-000003",
  customer: {
    id: "2b3c4d5e-6f70-4a81-9b92-a3b4c5d6e7f9",
    code: "C-02",
    name: "Northwind Freight Co. (Demo)",
  },
  contracting_entity: AVM_US,
  status: "ACTIVE",
  status_reason: null,
  on_hold: false,
  combination_group: {
    id: "3c4d5e6f-7081-4a92-8ba3-b4c5d6e7f80a",
    code: "CG-000003",
    is_singleton: true,
    member_contract_ids: [CONTRACT_ID],
  },
  inception_date: "2026-01-01",
  signature_date: null,
  payment_terms: null,
  transaction_currency: "USD",
  source_system: "SALESFORCE",
  region: null,
  channel: null,
  contract_type: null,
  document_ref: null,
  has_commercial_substance: true,
  custom_attributes: {},
  termination: null,
  memo_1: null,
  memo_2: null,
  memo_3: null,
  open_exception_count: 0,
  head_stream_version: 4,
  scope_605_35: false,
  renewal_of_contract_id: null,
  consideration_payable: [],
  noncash_consideration: [],
  payment_schedule: [],
  activation_checklist: null,
  activated_at: "2026-01-02T10:00:00Z",
  completed_at: null,
  terminated_at: null,
  voided_at: null,
  kpis: {
    transaction_price: money("240000.00"),
    billed_to_date: money("120000.00"),
    revenue_to_date: money("89753.42"),
    scheduled: money("150246.58"),
    awaiting_trigger: money("0.00"),
    rpo: money("150246.58"),
    balances: [
      {
        entity: AVM_US,
        contract_liability: money("30246.58"),
        contract_asset: money("0.00"),
        unbilled_receivable: money("0.00"),
        refund_liability: money("0.00"),
      },
    ],
  },
  kpis_ratios: { billed: "0.500000", recognized: "0.373973", pending_trigger_count: 0 },
  steps: ["CONTRACT", "OBLIGATIONS", "TRANSACTION_PRICE", "ALLOCATION", "RECOGNITION"].map(
    (step) => ({ step, state: "COMPLETE", status_code: null, detail: {} }),
  ),
  context: VERSION_CONTEXT,
  links: {
    self: `/api/v1/contracts/${CONTRACT_ID}`,
    explain_transaction_price: `/api/v1/explain/contract_version/${VERSION_ID}/transaction_price`,
  },
  created_at: "2026-01-02T10:00:00Z",
  updated_at: "2026-09-10T10:00:00Z",
};

const OBLIGATION = {
  id: O1_ID,
  contract_id: CONTRACT_ID,
  obligation_key: "O1",
  obligation_version_id: "7e8f90a1-b2c3-4d4e-8f5a-6b7c8d9e0f1a",
  legacy_record_key: "O1",
  product: { id: "8f90a1b2-c3d4-4e5f-9a6b-7c8d9e0f1a2b", code: "AVM-SEAT-MO", name: "Seat" },
  stratification: "",
  obligation_kind: "STANDARD",
  distinctness: "distinct",
  series_increment_unit: null,
  pob_template_version: {
    id: "90a1b2c3-d4e5-4f6a-8b7c-8d9e0f1a2b3c",
    template_code: "TPL-SUB-MONTHLY",
    version_no: 1,
  },
  scope_flag: "IN_SCOPE_606",
  satisfaction_pattern: "OVER_TIME",
  over_time_criterion: "OT_A",
  recognition_method: "TIME_ELAPSED",
  ratable_convention: "DAILY",
  principal_agent: "PRINCIPAL",
  licence_nature: "NOT_APPLICABLE",
  warranty_type: "NONE",
  start_date: "2026-01-01",
  end_date: "2027-12-31",
  contracting_entity: AVM_US,
  performing_entity: AVM_US,
  currency: "USD",
  memo_1: null,
  memo_2: null,
  memo_3: null,
  account_overrides: {},
  holds: [],
  material_right: null,
  satisfaction_status: "PARTIALLY_SATISFIED",
  satisfied_date: null,
  current: {
    allocated_amount: money("240000.00"),
    allocation_adjustment: money("0.00"),
    allocation_weight: "1.000000",
    quantity: "2400",
    remaining_unit_revenue_rate: null,
    stated_price: money("240000.00"),
    unit_ssp: null,
  },
  original: {
    allocated_amount: money("240000.00"),
    quantity: "2400",
    ssp_high: null,
    ssp_in_range: null,
    ssp_low: null,
    ssp_mid: null,
    ssp_selected: "240000.00",
    stated_price: money("240000.00"),
    total_contract_price: money("240000.00"),
    total_contract_ssp: "240000.00",
    unit_revenue_rate: null,
    unit_ssp: null,
  },
  ssp: {
    book_version_id: null,
    entry_id: null,
    method: "observable",
    midpoint_discount_ratio: null,
    outside_range_point: null,
    override_approval_request_id: null,
    range_position: null,
    range_ratio: null,
    unit_list_price: null,
    version_label: null,
  },
  to_date: {
    billed: money("120000.00"),
    catch_up: money("0.00"),
    catch_up_estimate: money("0.00"),
    catch_up_modification: money("0.00"),
    catch_up_tp_change: money("0.00"),
    delivered_quantity: "0",
    pre_standard_revenue: money("0.00"),
    progress_ratio: null,
    returned_quantity: "0",
    revenue: money("89753.42"),
    ssp_delivered: "0",
  },
  remaining: {
    allocation: money("150246.58"),
    billing: money("120000.00"),
    quantity: "0",
    ssp: "0",
  },
  scheduled: money("150246.58"),
  awaiting_trigger: money("0.00"),
  ratios: { recognized: null, scheduled: null, awaiting_trigger: null },
  position: { label: "CONTRACT_LIABILITY", amount: money("30246.58") },
  netting_reclass: { amount: money("0.00"), role: null },
  context: VERSION_CONTEXT,
  links: { self: `/api/v1/obligations/${O1_ID}` },
};

/**
 * The Explain addresses a balance row names (04 API-S-ContractBalance `links`, rev 1.174): the row and
 * the period the balances were read at.
 */
function balanceLinks(rowId: string): Record<string, string | null> {
  const base = `/api/v1/explain/contract_version_balance/${rowId}`;
  return {
    explain_contract_liability: `${base}/contract_liability?period=FY2026-P09`,
    explain_contract_asset: `${base}/contract_asset?period=FY2026-P09`,
    explain_unbilled_receivable: `${base}/unbilled_receivable?period=FY2026-P09`,
  };
}

/** One API-S-ContractBalance row; members not named are 0.00. */
function balance(
  entity: typeof AVM_US,
  figures: Readonly<Record<string, string>>,
  links: Readonly<Record<string, string | null>>,
): Record<string, unknown> {
  const members = [
    "net_position",
    "contract_liability",
    "contract_liability_current",
    "contract_asset",
    "contract_asset_current",
    "unbilled_receivable",
    "accounts_receivable",
    "refund_liability",
    "return_asset",
    "deposit_liability",
    "customer_incentive_asset",
    "consideration_payable",
    "cost_asset_carrying",
    "loss_provision",
  ];
  const txn = Object.fromEntries(members.map((name) => [name, money(figures[name] ?? "0.00")]));
  return {
    contract_id: CONTRACT_ID,
    entity,
    book: "ASC606",
    ...txn,
    functional: txn,
    links,
    context: VERSION_CONTEXT,
  };
}

// The signed `net_position` figures are distinctive, so the test can show they never render (D-12).
const BALANCES = [
  balance(
    AVM_US,
    {
      net_position: "-9876.54",
      contract_liability: "30246.58",
      contract_liability_current: "30246.58",
      accounts_receivable: "120000.00",
    },
    balanceLinks(BALANCE_US_ID),
  ),
  balance(
    AVM_UK,
    {
      net_position: "1730.00",
      contract_asset: "1250.00",
      unbilled_receivable: "480.00",
    },
    balanceLinks(BALANCE_UK_ID),
  ),
];

const INVOICE = {
  id: "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
  contract_id: CONTRACT_ID,
  stream_version: 4,
  event_type: "BILLING_RECORDED",
  schema_version: 1,
  effective_date: "2026-01-01",
  recorded_at: "2026-09-12T11:00:00Z",
  record_seq: 12,
  // 04 T-CON-05: a person's entry in the product carries `UI`.
  origin: "UI",
  is_manual: true,
  obligation_keys: ["O1"],
  payload: {
    invoice_number: "INV-US-1002",
    line_external_id: "INV-US-1002-1",
    amount: money("120000.00"),
    issue_date: "2026-01-01",
    obligation_key: "O1",
  },
  payload_sha256: "0".repeat(64),
  supersedes_event_id: null,
  approval_request_id: null,
  modification_id: null,
  estimate_version_id: null,
  manual_adjustment_id: null,
  import_upload_id: null,
  source_record_id: null,
  source_row: null,
  created_by: { id: null, kind: "USER", display_name: "maya@demo.erev" },
  computation: null,
};

interface Recorded {
  readonly reads: string[];
  readonly explain: string[];
}

function serve(
  recorded: Recorded,
  balances: readonly Record<string, unknown>[] = BALANCES,
  invoices: readonly Record<string, unknown>[] = [INVOICE],
) {
  const empty = () => HttpResponse.json({ items: [], next_cursor: null });
  const record = (request: Request) => {
    const url = new URL(request.url);
    recorded.reads.push(`${url.pathname}${url.search}`);
  };
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), empty),
    http.get(apiUrl("/api/v1/entities"), () =>
      HttpResponse.json({
        items: [
          {
            ...AVM_US,
            functional_currency: "USD",
            is_active: true,
            books: [{ book_code: "ASC606", is_enabled: true }],
          },
        ],
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
    http.get(apiUrl("/api/v1/currencies"), () =>
      HttpResponse.json({
        items: [
          { code: "USD", minor_unit: 2, name: "US Dollar", numeric_code: "840", is_active: true },
        ],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/obligations`), () =>
      HttpResponse.json({ items: [OBLIGATION], next_cursor: null }),
    ),
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/balances`), ({ request }) => {
      record(request);
      return HttpResponse.json({ items: balances, next_cursor: null });
    }),
    // The address the panel asks is what the test reads; the route has no figure to answer here.
    http.get(apiUrl("/api/v1/explain/:objectType/:objectId/:measure"), ({ request }) => {
      const url = new URL(request.url);
      recorded.explain.push(`${url.pathname}${url.search}`);
      return problemResponse("not-found", 404, "Not found");
    }),
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/events`), ({ request }) => {
      record(request);
      return HttpResponse.json(
        { items: invoices, next_cursor: null },
        { headers: { "X-Erev-Total-Count": String(invoices.length) } },
      );
    }),
    // SCREENS §4.1.7: the "Modifications <n>" tab count of the frame (CTR-24).
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/modifications`), () =>
      HttpResponse.json(
        { items: [], next_cursor: null },
        { headers: { "X-Erev-Total-Count": "0" } },
      ),
    ),
    // SCREENS §8.2: the "Estimates <n>" tab count of the frame (CTR-25).
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/estimates`), () =>
      HttpResponse.json(
        { items: [], next_cursor: null },
        { headers: { "X-Erev-Total-Count": "0" } },
      ),
    ),
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}`), () => HttpResponse.json(CONTRACT)),
    http.get(apiUrl("/api/v1/combination-suggestions"), empty),
    http.get(apiUrl("/api/v1/attachments"), () =>
      HttpResponse.json(
        { items: [], next_cursor: null },
        { headers: { "X-Erev-Total-Count": "0" } },
      ),
    ),
    http.get(apiUrl("/api/v1/jobs"), empty),
    http.get(apiUrl("/api/v1/approvals"), empty),
    http.get(apiUrl("/api/v1/judgements"), empty),
  );
}

function rowTexts(table: HTMLElement): string[][] {
  return within(table)
    .getAllByRole("row")
    .map((row) =>
      Array.from(row.querySelectorAll("th, td"), (cell) => (cell.textContent ?? "").trim()),
    );
}

describe("SF-03:billing balances by entity", () => {
  it("a row that names no explanation prints its balances without a trigger", async () => {
    // A read before the first period the version measures: the balances are 0.00, no node of the trace
    // holds them and the row's links are null (04 API-S-ContractBalance `links`, rev 1.174).
    const recorded: Recorded = { reads: [], explain: [] };
    serve(recorded, [
      balance(
        AVM_US,
        {},
        {
          explain_contract_liability: null,
          explain_contract_asset: null,
          explain_unbilled_receivable: null,
        },
      ),
    ]);
    renderApp(`/contracts/${CONTRACT_ID}/billing?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    fireEvent.click(await screen.findByRole("switch", { name: "Show zero balances" }));
    const table = await screen.findByRole("table", { name: "Balances by entity (USD)" });
    await waitFor(() => {
      expect(within(table).getAllByRole("row")).toHaveLength(14);
    });
    expect(rowTexts(table)[1]).toEqual(["Contract liability", "0.00"]);
    expect(within(table).queryAllByRole("button")).toEqual([]);
  }, 20_000);

  it("labelled balances per entity", async () => {
    const recorded: Recorded = { reads: [], explain: [] };
    serve(recorded);
    renderApp(`/contracts/${CONTRACT_ID}/billing?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const table = await screen.findByRole("table", { name: "Balances by entity (USD)" });
    expect(table.getAttribute("data-testid")).toBe("SF-03-grid-balances");
    expect(
      screen.getByRole("heading", { level: 2, name: "Balances by entity (USD)" }),
    ).toBeTruthy();
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["Balance", "AVM-US", "AVM-UK"]);
    // Rows that are 0.00 in every entity stay collapsed while "Show zero balances" is off.
    expect(rowTexts(table)).toEqual([
      ["Balance", "AVM-US", "AVM-UK"],
      ["Contract liability", "30,246.58", "0.00"],
      ["Contract liability, current portion", "30,246.58", "0.00"],
      ["Contract asset", "0.00", "1,250.00"],
      ["Unbilled receivable", "0.00", "480.00"],
      ["Accounts receivable", "120,000.00", "0.00"],
    ]);

    // SCREENS §4.4 rev 1.24: a cell is an Explain trigger where its row names the explanation of that
    // balance — the trigger names the balance, the entity and the labelled figure.
    const liability = within(table).getByRole("row", { name: /^Contract liability 30,246.58/ });
    expect(
      within(liability)
        .getAllByRole("button")
        .map((button) => button.getAttribute("aria-label")),
    ).toEqual([
      "Explain Contract liability · AVM-US, USD 30,246.58",
      "Explain Contract liability · AVM-UK, USD 0.00",
    ]);
    const asset = within(table).getByRole("row", { name: /^Contract asset 0.00/ });
    expect(
      within(asset).getByRole("button", { name: "Explain Contract asset · AVM-UK, USD 1,250.00" }),
    ).toBeTruthy();
    const unbilled = within(table).getByRole("row", { name: /^Unbilled receivable/ });
    expect(
      within(unbilled).getByRole("button", {
        name: "Explain Unbilled receivable · AVM-UK, USD 480.00",
      }),
    ).toBeTruthy();
    // The two rows the links do not name print their amounts without a trigger: six triggers in all.
    for (const name of [/^Contract liability, current portion/, /^Accounts receivable/]) {
      expect(within(within(table).getByRole("row", { name })).queryAllByRole("button")).toEqual([]);
    }
    expect(within(table).getAllByRole("button")).toHaveLength(6);

    // No signed `net_position` (D-12; DS-FMT-28): neither figure nor label renders, no cell is signed.
    const page = screen.getByTestId("SF-03-page");
    expect(page.textContent).not.toContain("9,876.54");
    expect(page.textContent).not.toContain("1,730.00");
    expect(page.textContent?.toLowerCase()).not.toContain("position");
    for (const cell of within(table).getAllByRole("cell")) {
      expect(cell.textContent?.trim()).not.toMatch(/^[-−+(]/);
    }

    // The zero rows appear with the switch on, still without the `net_position` figure.
    fireEvent.click(screen.getByRole("switch", { name: "Show zero balances" }));
    await waitFor(() => {
      expect(within(table).getAllByRole("row")).toHaveLength(14);
    });
    expect(rowTexts(table).map((row) => row[0])).toEqual([
      "Balance",
      "Contract liability",
      "Contract liability, current portion",
      "Contract asset",
      "Contract asset, current portion",
      "Unbilled receivable",
      "Accounts receivable",
      "Refund liability",
      "Return asset",
      "Deposit liability",
      "Customer incentive asset",
      "Consideration payable to a customer",
      "Contract cost asset",
      "Loss provision",
    ]);
    expect(page.textContent).not.toContain("9,876.54");

    // The reads: balances at the context period end in the book; the billing events newest first.
    expect(recorded.reads).toContain(
      `/api/v1/contracts/${CONTRACT_ID}/balances?book=ASC606&as_of=2026-09-30`,
    );
    const grid = await screen.findByRole("grid", { name: "Invoices and credit memos" });
    expect(await within(grid).findByRole("rowheader", { name: "INV-US-1002" })).toBeTruthy();
    expect(screen.getByTestId("SF-03-row-inv-us-1002").textContent).toContain("120,000.00");
    expect(
      recorded.reads.some((read) =>
        read.startsWith(
          `/api/v1/contracts/${CONTRACT_ID}/events?event_type=BILLING_RECORDED&event_type=CREDIT_MEMO_RECORDED&sort=-effective_date`,
        ),
      ),
    ).toBe(true);

    // The panel asks the address the row names: the id of that entity's balance row and the period of
    // the read. The contract version's id, which the cells sent before, is no balance row (404).
    fireEvent.click(
      within(table).getByRole("button", { name: "Explain Contract asset · AVM-UK, USD 1,250.00" }),
    );
    await waitFor(() => {
      expect(recorded.explain).toEqual([
        `/api/v1/explain/contract_version_balance/${BALANCE_UK_ID}/contract_asset?period=FY2026-P09&book=ASC606&depth=6`,
      ]);
    });
  }, 20_000);
});

// SCREENS §4.4 column 9, as bound (rev 1.62): the origin of an invoice is told from the event's own
// members — a person's entry, then the import row, then the literal of `origin` (04 T-CON-05), an API
// client by its name — by the one rule the Events panel of SF-03:obligation follows (workbench.test.tsx).
describe("SF-03:billing invoices and credit memos", () => {
  it("Origin names a person's entry, an import row and each origin literal of the API", async () => {
    const system = { id: null, kind: "SYSTEM", display_name: "System" };
    const person = {
      id: "5a6b7c8d-9e0f-4a1b-8c2d-3e4f5a6b7c8d",
      kind: "USER",
      display_name: "Maya Chen",
    };
    const client = {
      id: "6b7c8d9e-0f1a-4b2c-9d3e-4f5a6b7c8d9e",
      kind: "API_CLIENT",
      display_name: "Billing sync",
    };
    const invoice = (index: number, members: Readonly<Record<string, unknown>>) => {
      const number = `INV-US-20${String(index).padStart(2, "0")}`;
      return {
        ...INVOICE,
        id: `a1b2c3d4-e5f6-4a7b-8c9d-${String(index).padStart(12, "0")}`,
        stream_version: 4 + index,
        record_seq: 12 + index,
        is_manual: false,
        created_by: system,
        payload: { ...INVOICE.payload, invoice_number: number, line_external_id: `${number}-1` },
        ...members,
      };
    };
    const recorded: Recorded = { reads: [], explain: [] };
    serve(recorded, BALANCES, [
      // An event applied from a person's submission is appended as SYSTEM and stays manual (04 T-CON-05).
      invoice(1, { origin: "SYSTEM", is_manual: true }),
      invoice(2, {
        origin: "IMPORT",
        import_upload_id: "7c8d9e0f-1a2b-4c3d-8e4f-5a6b7c8d9e0f",
        source_row: {
          import_upload_id: "7c8d9e0f-1a2b-4c3d-8e4f-5a6b7c8d9e0f",
          sheet: null,
          row_number: 2,
        },
      }),
      invoice(3, { origin: "API", created_by: client }),
      invoice(4, { origin: "API", created_by: person }),
      invoice(5, { origin: "UI", created_by: person }),
      invoice(6, { origin: "IMPORT" }),
      invoice(7, { origin: "ADAPTER" }),
      invoice(8, { origin: "SYSTEM" }),
      invoice(9, { origin: "MIGRATION" }),
      // A literal 04 does not list is printed as it is: a seventh is seen, not hidden.
      invoice(10, { origin: "REPLAY" }),
    ]);
    renderApp(`/contracts/${CONTRACT_ID}/billing?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const grid = await screen.findByRole("grid", { name: "Invoices and credit memos" });
    await within(grid).findByRole("rowheader", { name: "INV-US-2001" });
    const origin = (index: number) =>
      screen
        .getByTestId(`SF-03-row-inv-us-20${String(index).padStart(2, "0")}`)
        .querySelector('[data-column="origin"]')?.textContent;
    expect(Array.from({ length: 10 }, (_, index) => origin(index + 1))).toEqual([
      "Manual",
      "Import row 2",
      "API client Billing sync",
      "API client",
      "Manual",
      "Import",
      "Integration",
      "System",
      "Migration",
      "REPLAY",
    ]);
  }, 20_000);
});
