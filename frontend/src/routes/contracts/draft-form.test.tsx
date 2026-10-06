// @vitest-environment jsdom
// SF-03:new and SF-03:edit Draft contract form (BUILD_SPEC CTR-24; SCREENS §4.10; DESIGN_SYSTEM DS-CMP-21;
// docs/dev-guide.md DG-FE-05, DG-FE-06; 04 API-R-28, §16.1 API-S-ContractCreate): the cross-field messages
// of the lines grid, money posted as decimal strings through `parseMoneyInput`, the two commands of "Save
// and submit for activation" and where a refused activation lands, a `validation-failed` answer placed on
// a grid cell, and SF-03:edit behind its fail-closed guard (ruling R-93 (a)): the form opens only while
// the latest booking still is the draft, and `replace-draft` names the head the guard read.
import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { RouteObject } from "react-router";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { type ContractEvent, draftEditOf } from "../../lib/api/queries/contracts";
import {
  installMemoryStorage,
  preloadScreens,
  probeRoute,
  renderApp,
  signedInMe,
} from "../../test/app";
import { customer } from "../../test/customers";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";

installMswServer();
installMemoryStorage();
// The form reads its four choice lists before it renders.
configure({ asyncUtilTimeout: 5000 });

beforeAll(async () => {
  await preloadScreens(SCREEN_ROUTES, ["SF-03:new", "SF-03:edit"]);
});

afterEach(() => {
  cleanup();
});

const MAYA = signedInMe({
  permissions: ["contract.read", "contract.create", "config.read", "judgement.create"],
});
const CONTEXT = "entity=AVM-US&period=FY2026-P09&book=ASC606";
const CONTRACT_ID = "4b5c6d7e-8f90-4a1b-9c2d-3e4f5a6b7c8d";
const BOOKING_EVENT_ID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d";
const FIRST_BOOKING_EVENT_ID = "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e";

const AVM_US = {
  id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000001",
  code: "AVM-US",
  name: "Avenmoor US Inc.",
};
const AVM_DE = {
  id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000002",
  code: "AVM-DE",
  name: "Avenmoor Deutschland GmbH",
};
const PELLWORTH = customer({
  id: "c0c0c0c0-c0c0-4c0c-8c0c-c0c0c0c0c0c0",
  code: "C-01",
  name: "Pellworth Logistics Inc. (Demo)",
  country_code: "US",
});

function product(code: string, name: string) {
  return {
    id: `9f90a1b2-c3d4-4e5f-9a6b-${code
      .replace(/[^0-9a-f]/gi, "0")
      .padEnd(12, "0")
      .slice(0, 12)
      .toLowerCase()}`,
    code,
    name,
    is_active: true,
    is_bundle: false,
  };
}

const PRODUCTS = [
  product("AVM-PLAT-100", "Avenmoor Platform, 100 seats"),
  product("AVM-IMPL-PLUS", "Implementation Plus"),
];

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

function money(amount: string, currency = "USD") {
  return { amount, currency };
}

/** API-S-Contract of a draft, as `POST /contracts` and `replace-draft` answer it. */
function draftContract(overrides: Readonly<Record<string, unknown>> = {}) {
  return {
    id: CONTRACT_ID,
    external_id: "SF-ORD-30001",
    contract_no: "CON-000101",
    customer: { id: PELLWORTH.id, code: PELLWORTH.code, name: PELLWORTH.name },
    contracting_entity: AVM_US,
    status: "DRAFT",
    status_reason: null,
    on_hold: false,
    combination_group: {
      id: "3c4d5e6f-7081-4a92-8ba3-b4c5d6e7f80a",
      code: "CG-CON-000101",
      is_singleton: true,
      member_contract_ids: [CONTRACT_ID],
    },
    inception_date: "2026-10-01",
    signature_date: null,
    payment_terms: null,
    transaction_currency: "USD",
    source_system: "MANUAL_UI",
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
    head_stream_version: 1,
    scope_605_35: false,
    renewal_of_contract_id: null,
    consideration_payable: [],
    noncash_consideration: [],
    payment_schedule: [],
    activation_checklist: null,
    activated_at: null,
    completed_at: null,
    terminated_at: null,
    voided_at: null,
    kpis: null,
    kpis_ratios: { billed: null, recognized: null, pending_trigger_count: 0 },
    steps: [],
    context: null,
    links: {
      self: `/api/v1/contracts/${CONTRACT_ID}`,
      allocation: `/api/v1/contracts/${CONTRACT_ID}/allocation`,
      balances: `/api/v1/contracts/${CONTRACT_ID}/balances`,
      events: `/api/v1/contracts/${CONTRACT_ID}/events`,
      explain_transaction_price: null,
      history: `/api/v1/contracts/${CONTRACT_ID}/history`,
      obligations: `/api/v1/contracts/${CONTRACT_ID}/obligations`,
      schedule: `/api/v1/contracts/${CONTRACT_ID}/schedule`,
      versions: `/api/v1/contracts/${CONTRACT_ID}/versions`,
    },
    created_at: "2026-09-30T10:00:00Z",
    updated_at: "2026-09-30T10:00:00Z",
    ...overrides,
  };
}

/** The latest `CONTRACT_BOOKED` of the draft (API-S-Event), with a payment point the form does not edit. */
const BOOKING: ContractEvent = {
  id: BOOKING_EVENT_ID,
  contract_id: CONTRACT_ID,
  stream_version: 3,
  event_type: "CONTRACT_BOOKED",
  schema_version: 1,
  effective_date: "2026-10-01",
  recorded_at: "2026-09-30T10:00:00Z",
  record_seq: 40,
  origin: "UI",
  is_manual: false,
  obligation_keys: ["O1"],
  payload: {
    external_id: "SF-ORD-30001",
    customer_id: PELLWORTH.id,
    contracting_entity_code: "AVM-US",
    transaction_currency: "USD",
    inception_date: "2026-10-01",
    signature_date: "2026-09-28",
    document_ref: "MSA-30001",
    has_commercial_substance: true,
    termination: { party: "CUSTOMER", has_penalty: true, notice_days: 30 },
    payment_schedule: [{ date: "2026-10-15", amount: money("120000.00") }],
    lines: [
      {
        obligation_key: "O1",
        product_code: "AVM-PLAT-100",
        quantity: "1",
        total_price: money("120000.00"),
        start_date: "2026-10-01",
        end_date: "2027-09-30",
        scope_flag: "IN_SCOPE_606",
        account_overrides: { REVENUE: "4010" },
      },
    ],
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
  created_by: { id: null, kind: "USER", display_name: "Maya Chen" },
  prepared_by: null,
  approved_by: null,
  void_refusal: "A booking is not voided as an event. Replace the draft, or void the contract.",
  computation: null,
};

/** An event of the draft's stream at `streamVersion` (API-S-Event). */
function streamEvent(
  eventType: ContractEvent["event_type"],
  streamVersion: number,
  overrides: Partial<ContractEvent> = {},
): ContractEvent {
  return {
    ...BOOKING,
    id: `e0e0e0e0-e0e0-4e0e-8e0e-${String(streamVersion).padStart(12, "0")}`,
    event_type: eventType,
    stream_version: streamVersion,
    record_seq: 40 + streamVersion,
    obligation_keys: [],
    payload: {},
    ...overrides,
  };
}

/**
 * The stream of a draft that was replaced once (04 §16.1): the first booking, the SYSTEM event that
 * voids it and the booking in force, newest first as the events route lists them.
 */
const REPLACED_STREAM: readonly ContractEvent[] = [
  BOOKING,
  streamEvent("EVENT_VOIDED", 2, {
    origin: "SYSTEM",
    supersedes_event_id: FIRST_BOOKING_EVENT_ID,
    created_by: { id: null, kind: "SYSTEM", display_name: "System" },
  }),
  streamEvent("CONTRACT_BOOKED", 1, {
    id: FIRST_BOOKING_EVENT_ID,
    obligation_keys: ["O1"],
    payload: {
      ...BOOKING.payload,
      document_ref: "MSA-FIRST",
      lines: [
        {
          obligation_key: "O1",
          product_code: "AVM-IMPL-PLUS",
          quantity: "1",
          total_price: money("1.00"),
        },
      ],
    },
  }),
];

/** Serves `events` as the contract's stream, newest first. */
function serveStream(events: readonly ContractEvent[]): void {
  server.use(
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/events`), () =>
      HttpResponse.json({ items: events, next_cursor: null }),
    ),
  );
}

interface Sent {
  readonly path: string;
  readonly body: unknown;
  readonly ifMatch: string | null;
  readonly idempotencyKey: string | null;
}

/** The searches of the events reads of the default stream. */
let streamReads: string[] = [];

function serve(sent: Sent[]) {
  streamReads = [];
  const record = async (request: Request) => {
    sent.push({
      path: new URL(request.url).pathname,
      body: await request.json(),
      ifMatch: request.headers.get("If-Match"),
      idempotencyKey: request.headers.get("Idempotency-Key"),
    });
  };
  const empty = () => HttpResponse.json({ items: [], next_cursor: null });
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), empty),
    http.get(apiUrl("/api/v1/entities"), () =>
      HttpResponse.json({
        items: [AVM_DE, AVM_US].map((entity) => ({
          ...entity,
          functional_currency: entity.code === "AVM-US" ? "USD" : "EUR",
          is_active: true,
          books: [{ book_code: "ASC606", is_enabled: true }],
        })),
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
    http.get(apiUrl("/api/v1/tenant-currencies"), () =>
      HttpResponse.json({
        items: [
          ["EUR", "Euro", 2],
          ["JPY", "Yen", 0],
          ["USD", "US Dollar", 2],
        ].map(([code, name, unit]) => ({
          currency_code: code,
          name,
          minor_unit: unit,
          is_enabled: true,
          is_reporting_currency: code === "USD",
          row_version: 1,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        })),
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
    http.get(apiUrl("/api/v1/customers"), () =>
      HttpResponse.json({ items: [PELLWORTH], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/products"), () =>
      HttpResponse.json({ items: PRODUCTS, next_cursor: null }),
    ),
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/events`), ({ request }) => {
      streamReads.push(new URL(request.url).search);
      return HttpResponse.json({ items: REPLACED_STREAM, next_cursor: null });
    }),
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}`), () =>
      HttpResponse.json(draftContract({ head_stream_version: 3 })),
    ),
    http.post(apiUrl("/api/v1/contracts"), async ({ request }) => {
      await record(request);
      return HttpResponse.json(draftContract(), {
        status: 201,
        headers: { ETag: '"s1"' },
      });
    }),
    http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/replace-draft`), async ({ request }) => {
      await record(request);
      return HttpResponse.json(draftContract({ head_stream_version: 5 }));
    }),
    http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/submit-activation`), async ({ request }) => {
      await record(request);
      return HttpResponse.json(draftContract({ status: "ACTIVE", head_stream_version: 2 }));
    }),
  );
}

// SF-03:new and SF-03:edit as routed, and stand-ins for the screens the form opens after a save.
const ROUTES: readonly RouteObject[] = [
  ...SCREEN_ROUTES.filter((route) => route.id === "SF-03:new" || route.id === "SF-03:edit"),
  probeRoute("SF-03", "/contracts/:contractId/obligations", "contracts.workbench.documentTitle"),
  probeRoute("SF-02", "/contracts", "contracts.list.title"),
];

function renderForm(path: string) {
  return renderApp(path, { me: MAYA, screenRoutes: ROUTES });
}

function type(name: string | RegExp, value: string): HTMLElement {
  const input = screen.getByRole("textbox", { name });
  fireEvent.change(input, { target: { value } });
  return input;
}

/** The listbox a combobox controls, once it is open. */
function listOf(combobox: HTMLElement): HTMLElement {
  const list = document.getElementById(combobox.getAttribute("aria-controls") ?? "");
  if (list === null) {
    throw new Error("The combobox has no open list");
  }
  return list;
}

/** Picks an option of a `components/form/Select` by its visible label. */
function select(name: string, option: string): void {
  const trigger = screen.getByRole("combobox", { name });
  fireEvent.click(trigger);
  fireEvent.mouseDown(within(listOf(trigger)).getByRole("option", { name: option }));
}

/** Types into a combobox and picks the option the typed text leaves. */
function pick(name: string, text: string, option: string | RegExp): void {
  const input = screen.getByRole("combobox", { name });
  fireEvent.change(input, { target: { value: text } });
  fireEvent.mouseDown(within(listOf(input)).getByRole("option", { name: option }));
}

/** Chooses the option of a select cell of the lines grid by its value. */
function choose(name: string, value: string): void {
  fireEvent.change(screen.getByRole("combobox", { name }), { target: { value } });
}

async function openNewForm() {
  const rendered = renderForm(`/contracts/new?${CONTEXT}`);
  expect(await screen.findByRole("heading", { level: 1, name: "New contract" })).toBeTruthy();
  await screen.findByRole("grid", { name: "Contract lines" });
  return rendered;
}

function fillHeader(): void {
  type("External id", "SF-ORD-30001");
  pick("Customer", "Pell", /^Pellworth Logistics Inc\. \(Demo\)/);
  select("Contracting entity", "AVM-US · Avenmoor US Inc.");
  type("Inception date", "2026-10-01");
}

describe("SF-03:new draft contract form", () => {
  it("cross field messages", async () => {
    const sent: Sent[] = [];
    serve(sent);
    await openNewForm();
    fillHeader();
    expect(screen.getByTestId("SF-03-grid-lines")).toBeTruthy();

    // An end date before the start date names the start date.
    type("Start date, line 1", "2026-03-01");
    type("End date, line 1", "2026-02-01");
    // A second line that repeats the key of the first.
    fireEvent.click(screen.getByRole("button", { name: "Add line" }));
    expect(
      (screen.getByRole("textbox", { name: "Obligation key, line 2" }) as HTMLInputElement).value,
    ).toBe("O2");
    type("Obligation key, line 2", "O1");

    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));

    const grid = screen.getByRole("grid", { name: "Contract lines" });
    expect(within(grid).getByText("Enter an end date on or after 01 Mar 2026.")).toBeTruthy();
    expect(within(grid).getByText("Obligation key O1 is used twice.")).toBeTruthy();
    const endDate = screen.getByRole("textbox", { name: "End date, line 1" });
    expect(endDate.getAttribute("aria-invalid")).toBe("true");
    expect(
      document.getElementById(endDate.getAttribute("aria-describedby") ?? "")?.textContent,
    ).toBe("Enter an end date on or after 01 Mar 2026.");
    expect(
      screen.getByRole("textbox", { name: "Obligation key, line 2" }).getAttribute("aria-invalid"),
    ).toBe("true");
    // The first use of the key is not the repeated one.
    expect(
      screen.getByRole("textbox", { name: "Obligation key, line 1" }).hasAttribute("aria-invalid"),
    ).toBe(false);
    // DS-CMP-21: the summary links each message to its cell and nothing is sent.
    const summary = screen.getByRole("heading", { name: /^Fix \d+ fields to continue$/ });
    expect(document.activeElement).toBe(summary);
    expect(
      screen.getByRole("link", {
        name: "Line 1: Enter an end date on or after 01 Mar 2026.",
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Line 2: Obligation key O1 is used twice." }),
    ).toBeTruthy();
    expect(sent).toEqual([]);

    // The messages follow the correction.
    type("End date, line 1", "2026-03-01");
    type("Obligation key, line 2", "O2");
    expect(screen.queryByText("Enter an end date on or after 01 Mar 2026.")).toBeNull();
    expect(screen.queryByText("Obligation key O1 is used twice.")).toBeNull();
  });

  it("money inputs stay strings", async () => {
    const sent: Sent[] = [];
    serve(sent);
    const { router } = await openNewForm();
    fillHeader();
    // The entity's functional currency is offered as the contract currency.
    expect(screen.getByRole("combobox", { name: "Currency" }).textContent).toContain("USD");
    expect(screen.getByRole("columnheader", { name: "Total price (USD)" })).toBeTruthy();

    pick("Product, line 1", "PLAT", "AVM-PLAT-100 · Avenmoor Platform, 100 seats");
    type("Quantity, line 1", "1");
    // Typed with grouping; the blur echoes the amount of the currency's minor unit.
    const price = type("Total price, line 1", "120,000.5");
    fireEvent.blur(price);
    expect((price as HTMLInputElement).value).toBe("120,000.50");
    type("Unit price, line 1", "120,000.5");
    choose("Scope, line 1", "LEASE_842");
    type("Out-of-scope amount, line 1", "(1,250)");

    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));

    await waitFor(() => expect(sent).toHaveLength(1));
    const [create] = sent;
    expect(create?.path).toBe("/api/v1/contracts");
    expect(create?.idempotencyKey).toMatch(/^[0-9a-f-]{36}$/);
    expect(create?.body).toEqual({
      external_id: "SF-ORD-30001",
      customer_id: PELLWORTH.id,
      contracting_entity_code: "AVM-US",
      transaction_currency: "USD",
      inception_date: "2026-10-01",
      signature_date: null,
      document_ref: null,
      payment_terms: null,
      termination: null,
      has_commercial_substance: true,
      region: null,
      channel: null,
      contract_type: null,
      memo_1: null,
      memo_2: null,
      memo_3: null,
      lines: [
        {
          obligation_key: "O1",
          product_code: "AVM-PLAT-100",
          stratification: null,
          quantity: "1",
          total_price: { amount: "120000.50", currency: "USD" },
          unit_price: "120000.5",
          start_date: null,
          end_date: null,
          performing_entity_code: null,
          ssp_version_label: null,
          scope_flag: "LEASE_842",
          out_of_scope_amount: { amount: "-1250", currency: "USD" },
          memo_1: null,
          memo_2: null,
          memo_3: null,
          account_overrides: null,
          bundle_parent_obligation_key: null,
          custom_attributes: null,
          ssp_override_justification: null,
        },
      ],
      submit_for_activation: false,
      consideration_payable: [],
      noncash_consideration: [],
      payment_schedule: [],
      custom_attributes: null,
      scope_605_35: false,
      renewal_of_contract_id: null,
    });
    const line = (create?.body as { lines: { total_price: { amount: unknown } }[] }).lines[0];
    expect(typeof line?.total_price.amount).toBe("string");

    // The saved draft opens in the workbench with the context parameters.
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/contracts/${CONTRACT_ID}/obligations`),
    );
    expect(router.state.location.search).toBe(`?${CONTEXT}`);
    expect(await screen.findByText("Draft saved.")).toBeTruthy();
  });

  it("an amount with more decimals than the currency holds is refused before anything is sent", async () => {
    const sent: Sent[] = [];
    serve(sent);
    await openNewForm();
    fillHeader();
    pick("Product, line 1", "PLAT", "AVM-PLAT-100 · Avenmoor Platform, 100 seats");
    type("Quantity, line 1", "0");
    const price = type("Total price, line 1", "120000.505");
    fireEvent.blur(price);
    // DS-CMP-21: the format check runs on blur.
    expect(await screen.findByText("Enter at most 2 decimal places.")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));

    expect(screen.getByText("Enter a quantity other than 0.")).toBeTruthy();
    expect(sent).toEqual([]);
  });

  it("save and submit sends the booking, then submit-activation with the saved head", async () => {
    const sent: Sent[] = [];
    serve(sent);
    const { router } = await openNewForm();
    fillHeader();
    pick("Product, line 1", "PLAT", "AVM-PLAT-100 · Avenmoor Platform, 100 seats");
    type("Quantity, line 1", "1");
    type("Total price, line 1", "120000");

    fireEvent.click(screen.getByRole("button", { name: "Save and submit for activation" }));

    await waitFor(() => expect(sent).toHaveLength(2));
    expect(sent.map((request) => request.path)).toEqual([
      "/api/v1/contracts",
      `/api/v1/contracts/${CONTRACT_ID}/submit-activation`,
    ]);
    // The API refuses the flag in the booking (04 §16.1): activation is the second command.
    expect((sent[0]?.body as { submit_for_activation: boolean }).submit_for_activation).toBe(false);
    expect(sent[1]?.ifMatch).toBe('"s1"');
    expect(sent[1]?.body).toEqual({ comment: null });
    expect(sent[1]?.idempotencyKey).not.toBe(sent[0]?.idempotencyKey);
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/contracts/${CONTRACT_ID}/obligations`),
    );
    expect(await screen.findByText("Contract activated.")).toBeTruthy();
    expect(new URLSearchParams(router.state.location.search).has("step")).toBe(false);
  });

  it("a refused activation opens the saved draft at step 1 and says what is missing", async () => {
    const sent: Sent[] = [];
    serve(sent);
    // 04 table 15.4-I: a new manual draft has no Step 1 review yet (rulings R-89, R-93).
    server.use(
      http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/submit-activation`), () =>
        problemResponse("activation-checklist-failed", 409, "Contract cannot be activated", {
          detail: "2 checklist items have not passed: SOURCE_REFERENCE, STEP1_RECORD.",
          errors: [
            {
              field: null,
              sheet: null,
              row: null,
              rule_id: "SOURCE_REFERENCE",
              message: "No contract reference is recorded.",
            },
            {
              field: null,
              sheet: null,
              row: null,
              rule_id: "STEP1_RECORD",
              message: "Step 1 review not recorded.",
            },
          ],
        }),
      ),
    );
    const { router } = await openNewForm();
    fillHeader();
    pick("Product, line 1", "PLAT", "AVM-PLAT-100 · Avenmoor Platform, 100 seats");
    type("Quantity, line 1", "1");
    type("Total price, line 1", "120000");

    fireEvent.click(screen.getByRole("button", { name: "Save and submit for activation" }));

    // The draft is saved; the toast (two lines, DS-CMP-22) leads to the Step 1 row, which is open.
    expect(
      await screen.findByText("Draft saved. Not submitted: record the Step 1 review first."),
    ).toBeTruthy();
    expect(sent.map((request) => request.path)).toEqual(["/api/v1/contracts"]);
    expect(router.state.location.pathname).toBe(`/contracts/${CONTRACT_ID}/obligations`);
    const search = new URLSearchParams(router.state.location.search);
    expect(search.get("step")).toBe("1");
    expect(search.get("entity")).toBe("AVM-US");
    expect(search.get("period")).toBe("FY2026-P09");
    expect(search.get("book")).toBe("ASC606");
  });

  it("a refusal without a Step 1 item, or no answer, opens the saved draft as usual", async () => {
    const sent: Sent[] = [];
    serve(sent);
    server.use(
      http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/submit-activation`), () =>
        problemResponse("activation-checklist-failed", 409, "Contract cannot be activated", {
          errors: [
            {
              field: null,
              sheet: null,
              row: null,
              rule_id: "SOURCE_REFERENCE",
              message: "No contract reference is recorded.",
            },
          ],
        }),
      ),
    );
    const first = await openNewForm();
    fillHeader();
    pick("Product, line 1", "PLAT", "AVM-PLAT-100 · Avenmoor Platform, 100 seats");
    type("Quantity, line 1", "1");
    type("Total price, line 1", "120000");
    fireEvent.click(screen.getByRole("button", { name: "Save and submit for activation" }));

    // One failed item is named.
    expect(
      await screen.findByText("Draft saved. Not submitted: No contract reference is recorded."),
    ).toBeTruthy();
    expect(first.router.state.location.pathname).toBe(`/contracts/${CONTRACT_ID}/obligations`);
    expect(first.router.state.location.search).toBe(`?${CONTEXT}`);
    cleanup();

    // Several failed items are counted; "Submit for activation" on SF-03 lists them with their fixes.
    server.use(
      http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/submit-activation`), () =>
        problemResponse("activation-checklist-failed", 409, "Contract cannot be activated", {
          errors: ["SOURCE_REFERENCE", "PRODUCT_TEMPLATE_SSP"].map((code) => ({
            field: null,
            sheet: null,
            row: null,
            rule_id: code,
            message: `${code} has not passed.`,
          })),
        }),
      ),
    );
    const counted = await openNewForm();
    fillHeader();
    pick("Product, line 1", "PLAT", "AVM-PLAT-100 · Avenmoor Platform, 100 seats");
    type("Quantity, line 1", "1");
    type("Total price, line 1", "120000");
    fireEvent.click(screen.getByRole("button", { name: "Save and submit for activation" }));
    expect(
      await screen.findByText("Draft saved. Not submitted: 2 checklist items have not passed."),
    ).toBeTruthy();
    expect(counted.router.state.location.search).toBe(`?${CONTEXT}`);
    cleanup();

    // The activation command gets no answer: the draft is saved all the same, and the toast says so.
    server.use(
      http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/submit-activation`), () =>
        HttpResponse.error(),
      ),
    );
    const second = await openNewForm();
    fillHeader();
    pick("Product, line 1", "PLAT", "AVM-PLAT-100 · Avenmoor Platform, 100 seats");
    type("Quantity, line 1", "1");
    type("Total price, line 1", "120000");
    fireEvent.click(screen.getByRole("button", { name: "Save and submit for activation" }));

    expect(
      await screen.findByText("Draft saved. Not submitted: the server could not be reached."),
    ).toBeTruthy();
    expect(second.router.state.location.pathname).toBe(`/contracts/${CONTRACT_ID}/obligations`);
    expect(second.router.state.location.search).toBe(`?${CONTEXT}`);
  });

  it("a validation-failed answer lands on the field and the grid cell it names", async () => {
    const sent: Sent[] = [];
    serve(sent);
    server.use(
      http.post(apiUrl("/api/v1/contracts"), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            {
              field: "external_id",
              sheet: null,
              row: null,
              rule_id: "REQ-DAT-017",
              message: "A contract with this external id exists.",
            },
            {
              field: "lines.0.product_code",
              sheet: null,
              row: null,
              rule_id: "REQ-CON-001",
              message: "No product has this code.",
            },
          ],
        }),
      ),
    );
    const { router } = await openNewForm();
    fillHeader();
    pick("Product, line 1", "PLAT", "AVM-PLAT-100 · Avenmoor Platform, 100 seats");
    type("Quantity, line 1", "1");
    type("Total price, line 1", "120000");

    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));

    const externalId = await screen.findByRole("textbox", { name: "External id" });
    await waitFor(() => expect(externalId.getAttribute("aria-invalid")).toBe("true"));
    expect(screen.getAllByText("A contract with this external id exists.").length).toBeGreaterThan(
      0,
    );
    const cell = screen.getByRole("combobox", { name: "Product, line 1" });
    expect(cell.getAttribute("aria-invalid")).toBe("true");
    expect(document.getElementById(cell.getAttribute("aria-describedby") ?? "")?.textContent).toBe(
      "No product has this code.",
    );
    expect(screen.getByRole("link", { name: "Line 1: No product has this code." })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/contracts/new");

    // Changing the field removes the server's message for it.
    type("External id", "SF-ORD-30002");
    expect(screen.queryByText("A contract with this external id exists.")).toBeNull();
  });

  it("leaving a changed form asks before discarding it", async () => {
    serve([]);
    const { router } = await openNewForm();
    type("External id", "SF-ORD-30001");

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    const dialog = await screen.findByRole("alertdialog", { name: "Discard changes?" });
    expect(router.state.location.pathname).toBe("/contracts/new");
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard changes" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/contracts"));
  });
});

/** What SF-03:edit shows instead of the form, read from its state heading. */
async function refusedWith(title: string, description: string): Promise<void> {
  expect(await screen.findByRole("heading", { level: 2, name: title })).toBeTruthy();
  expect(screen.getByText(description)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Back to the contract" })).toBeTruthy();
  expect(screen.queryByRole("grid", { name: "Contract lines" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Save draft" })).toBeNull();
}

const CHANGED_TITLE = "Changed after it was booked";
const CHANGED_TEXT = "This draft was changed after it was booked; it cannot be edited here yet.";
const ASSESSED_TITLE = "A Step 1 assessment is recorded on this draft.";
const ASSESSED_TEXT =
  "Saving voids it: a new Step 1 review is recorded and reviewed before the contract is activated.";

/** The warning of SCREENS §4.10 (rev 1.72) above the open form, or null where the form shows none. */
function assessedWarning(): HTMLElement | null {
  const title = screen.queryByRole("heading", { level: 2, name: ASSESSED_TITLE });
  return title === null ? null : title.closest<HTMLElement>("[data-tone]");
}

/**
 * The booking that `replace-draft` appended after the SYSTEM voids of the booking before it and of the
 * assessments that stood (04 §16.1 rev 1.150, ruling R-102 (c)).
 */
const SECOND_BOOKING_EVENT_ID = "c3d4e5f6-a7b8-4c9d-8e1f-2a3b4c5d6e7f";

function rebooked(streamVersion: number): ContractEvent {
  return streamEvent("CONTRACT_BOOKED", streamVersion, {
    id: SECOND_BOOKING_EVENT_ID,
    obligation_keys: ["O1"],
    payload: BOOKING.payload,
  });
}

function voids(target: ContractEvent, streamVersion: number): ContractEvent {
  return streamEvent("EVENT_VOIDED", streamVersion, {
    origin: "SYSTEM",
    supersedes_event_id: target.id,
    created_by: { id: null, kind: "SYSTEM", display_name: "System" },
  });
}

describe("SF-03:edit draft contract form", () => {
  it("no later event: the draft opens with its latest booking and Save draft calls replace-draft with If-Match", async () => {
    const sent: Sent[] = [];
    serve(sent);
    const { router } = renderForm(`/contracts/${CONTRACT_ID}/edit?${CONTEXT}`);
    expect(await screen.findByRole("heading", { level: 1, name: "Edit draft" })).toBeTruthy();
    const key = await screen.findByRole("textbox", { name: "Obligation key, line 1" });
    expect((key as HTMLInputElement).value).toBe("O1");
    // The guard reads the whole stream, newest first, not a selection of event types.
    expect(new URLSearchParams(streamReads[0]).get("sort")).toBe("-stream_version");
    expect(new URLSearchParams(streamReads[0]).has("event_type")).toBe(false);

    // The external id, the contracting entity and the currency stay as booked (04 §16.1).
    const externalId = screen.getByRole("textbox", { name: "External id" }) as HTMLInputElement;
    expect(externalId.value).toBe("SF-ORD-30001");
    expect(externalId.readOnly).toBe(true);
    expect(
      (screen.getByRole("textbox", { name: "Contracting entity" }) as HTMLInputElement).readOnly,
    ).toBe(true);
    expect((screen.getByRole("textbox", { name: "Currency" }) as HTMLInputElement).value).toBe(
      "USD",
    );
    // The booking in force seeds the form, not the voided first booking (1.00, MSA-FIRST).
    expect(
      (screen.getByRole("textbox", { name: "Total price, line 1" }) as HTMLInputElement).value,
    ).toBe("120,000.00");
    expect(
      (screen.getByRole("textbox", { name: /^Contract reference/ }) as HTMLInputElement).value,
    ).toBe("MSA-30001");
    expect(
      (screen.getByRole("textbox", { name: "Start date, line 1" }) as HTMLInputElement).value,
    ).toBe("01 Oct 2026");
    expect((screen.getByRole("textbox", { name: /^Notice days/ }) as HTMLInputElement).value).toBe(
      "30",
    );

    type("Total price, line 1", "132,000.00");
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));

    await waitFor(() => expect(sent).toHaveLength(1));
    const [replace] = sent;
    expect(replace?.path).toBe(`/api/v1/contracts/${CONTRACT_ID}/replace-draft`);
    expect(replace?.ifMatch).toBe('"s3"');
    expect(replace?.body).toMatchObject({
      external_id: "SF-ORD-30001",
      customer_id: PELLWORTH.id,
      contracting_entity_code: "AVM-US",
      transaction_currency: "USD",
      inception_date: "2026-10-01",
      signature_date: "2026-09-28",
      document_ref: "MSA-30001",
      termination: { party: "CUSTOMER", has_penalty: true, notice_days: 30 },
      // Members the form does not edit go back as the draft holds them.
      payment_schedule: [{ date: "2026-10-15", amount: { amount: "120000.00", currency: "USD" } }],
      lines: [
        {
          obligation_key: "O1",
          product_code: "AVM-PLAT-100",
          quantity: "1",
          total_price: { amount: "132000.00", currency: "USD" },
          start_date: "2026-10-01",
          end_date: "2027-09-30",
          account_overrides: { REVENUE: "4010" },
        },
      ],
    });
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/contracts/${CONTRACT_ID}/obligations`),
    );
  });

  it("holds only: the draft opens and the save names the head the guard read", async () => {
    const sent: Sent[] = [];
    serve(sent);
    serveStream([
      streamEvent("HOLD_RELEASED", 5),
      streamEvent("HOLD_APPLIED", 4),
      ...REPLACED_STREAM,
    ]);
    // The `If-Match` of the save is the head of the stream the guard read, not the contract read's.
    server.use(
      http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}`), () =>
        HttpResponse.json(draftContract({ head_stream_version: 9 })),
      ),
    );
    renderForm(`/contracts/${CONTRACT_ID}/edit?${CONTEXT}`);
    const price = await screen.findByRole("textbox", { name: "Total price, line 1" });
    expect((price as HTMLInputElement).value).toBe("120,000.00");

    type("Total price, line 1", "132,000.00");
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));

    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0]?.path).toBe(`/api/v1/contracts/${CONTRACT_ID}/replace-draft`);
    expect(sent[0]?.ifMatch).toBe('"s5"');
  });

  it.each([
    ["a memo update", "MEMO_UPDATED"],
    ["an attribute change", "LINE_ATTRIBUTES_CHANGED"],
    ["a regroup", "REGROUPED"],
    ["any other event", "COMBINATION_CHANGED"],
  ] as const)("%s after the booking: the form does not open", async (_name, eventType) => {
    const sent: Sent[] = [];
    serve(sent);
    serveStream([streamEvent(eventType, 5), streamEvent("HOLD_APPLIED", 4), ...REPLACED_STREAM]);
    renderForm(`/contracts/${CONTRACT_ID}/edit?${CONTEXT}`);

    await refusedWith(CHANGED_TITLE, CHANGED_TEXT);
    expect(sent).toEqual([]);
  });

  // SCREENS §4.10 (rev 1.72; supervisor ruling R-102 (c); 04 §16.1 rev 1.150): the API takes the edit of
  // a draft whatever assessments its stream holds, and voids those that stand. Before, the screen kept the
  // form shut on every draft whose stream held an assessment.
  it("a standing assessment: the draft opens under the warning, and Save draft is replace-draft at the head the guard read", async () => {
    const sent: Sent[] = [];
    serve(sent);
    serveStream([
      streamEvent("COLLECTIBILITY_ASSESSED", 5),
      streamEvent("COLLECTIBILITY_ASSESSED", 4),
      ...REPLACED_STREAM,
    ]);
    renderForm(`/contracts/${CONTRACT_ID}/edit?${CONTEXT}`);

    const price = await screen.findByRole("textbox", { name: "Total price, line 1" });
    expect((price as HTMLInputElement).value).toBe("120,000.00");
    const warning = assessedWarning();
    expect(warning?.getAttribute("data-tone")).toBe("warning");
    expect(warning?.textContent).toBe(`${ASSESSED_TITLE}${ASSESSED_TEXT}`);
    // Present with the page (DS-CMP-29): a heading, not a live region.
    expect(warning?.hasAttribute("role")).toBe(false);
    expect(screen.queryByRole("heading", { name: CHANGED_TITLE })).toBeNull();

    type("Total price, line 1", "132,000.00");
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));

    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0]?.path).toBe(`/api/v1/contracts/${CONTRACT_ID}/replace-draft`);
    expect(sent[0]?.ifMatch).toBe('"s5"');
  });

  it("a voided assessment says nothing: the replaced draft opens on its new booking without the warning", async () => {
    // The stream `replace-draft` leaves behind a draft that was assessed (measured on the API): the
    // booking, its assessment, the SYSTEM voids of both and the new booking.
    const assessment = streamEvent("COLLECTIBILITY_ASSESSED", 4);
    const sent: Sent[] = [];
    serve(sent);
    serveStream([
      rebooked(7),
      voids(assessment, 6),
      voids(BOOKING, 5),
      assessment,
      ...REPLACED_STREAM,
    ]);
    renderForm(`/contracts/${CONTRACT_ID}/edit?${CONTEXT}`);

    await screen.findByRole("textbox", { name: "Total price, line 1" });
    expect(assessedWarning()).toBeNull();
    expect(screen.queryByText(ASSESSED_TEXT)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0]?.ifMatch).toBe('"s7"');
  });

  it("an assessment that stands from before the draft was replaced: the form opens under the warning", async () => {
    // A stream of before 04 §16.1 rev 1.150: the replacement voided the booking and left its
    // assessment standing. The next save voids it.
    serve([]);
    serveStream([
      rebooked(5),
      voids(BOOKING, 4),
      streamEvent("COLLECTIBILITY_ASSESSED", 3),
      { ...BOOKING, stream_version: 2 },
    ]);
    renderForm(`/contracts/${CONTRACT_ID}/edit?${CONTEXT}`);

    await screen.findByRole("textbox", { name: "Total price, line 1" });
    expect(assessedWarning()?.textContent).toBe(`${ASSESSED_TITLE}${ASSESSED_TEXT}`);
  });

  it("an assessment and another event after the booking: the form stays shut as changed", async () => {
    const sent: Sent[] = [];
    serve(sent);
    serveStream([
      streamEvent("MEMO_UPDATED", 5),
      streamEvent("COLLECTIBILITY_ASSESSED", 4),
      ...REPLACED_STREAM,
    ]);
    const { router } = renderForm(`/contracts/${CONTRACT_ID}/edit?${CONTEXT}`);

    await refusedWith(CHANGED_TITLE, CHANGED_TEXT);
    expect(screen.queryByText(ASSESSED_TITLE)).toBeNull();
    expect(sent).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Back to the contract" }));
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/contracts/${CONTRACT_ID}/obligations`),
    );
    expect(router.state.location.search).toBe(`?${CONTEXT}`);
  });

  it("a 412 keeps the typed input; Reload reads the stream again and closes on a later change", async () => {
    const sent: Sent[] = [];
    serve(sent);
    server.use(
      http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/replace-draft`), async ({ request }) => {
        sent.push({
          path: new URL(request.url).pathname,
          body: await request.json(),
          ifMatch: request.headers.get("If-Match"),
          idempotencyKey: request.headers.get("Idempotency-Key"),
        });
        return problemResponse("precondition-failed", 412, "Record changed");
      }),
    );
    renderForm(`/contracts/${CONTRACT_ID}/edit?${CONTEXT}`);
    await screen.findByRole("textbox", { name: "Total price, line 1" });
    type("Total price, line 1", "132,000.00");
    // Someone updates a memo while the form is open.
    serveStream([streamEvent("MEMO_UPDATED", 4), ...REPLACED_STREAM]);

    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));

    const reload = await screen.findByRole("button", { name: "Reload" });
    expect(sent).toHaveLength(1);
    expect(sent[0]?.ifMatch).toBe('"s3"');
    expect(screen.getByText("This record changed. Reload to see the latest version.")).toBeTruthy();
    expect(
      (screen.getByRole("textbox", { name: "Total price, line 1" }) as HTMLInputElement).value,
    ).toBe("132,000.00");

    fireEvent.click(reload);

    await refusedWith(CHANGED_TITLE, CHANGED_TEXT);
    expect(sent).toHaveLength(1);
  });

  it("a contract that is no longer a draft is not editable", async () => {
    serve([]);
    server.use(
      http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}`), () =>
        HttpResponse.json(draftContract({ status: "ACTIVE", head_stream_version: 4 })),
      ),
    );
    renderForm(`/contracts/${CONTRACT_ID}/edit?${CONTEXT}`);

    expect(await screen.findByRole("heading", { name: "Only a draft can be edited" })).toBeTruthy();
    expect(
      screen.getByText(
        "SF-ORD-30001 is Active. A contract that is no longer a draft changes through a modification.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save draft" })).toBeNull();
    // The stream of a contract that is not a draft is not read.
    expect(streamReads).toEqual([]);
  });
});

describe("draftEditOf, the guard of SF-03:edit (rulings R-93 (a), R-102 (c))", () => {
  const hold = streamEvent("HOLD_APPLIED", 4);

  it("opens on the booking in force with the newest stream version, whatever the order read", () => {
    const opened = draftEditOf([...REPLACED_STREAM, hold], true);
    expect(opened).toEqual({ kind: "open", booking: BOOKING, head: 4, assessed: false });
    expect(draftEditOf([BOOKING], true)).toEqual({
      kind: "open",
      booking: BOOKING,
      head: 3,
      assessed: false,
    });
  });

  it("closes when the stream was not read back to its start or holds no booking in force", () => {
    expect(draftEditOf(REPLACED_STREAM, false)).toEqual({ kind: "changed" });
    expect(draftEditOf([], true)).toEqual({ kind: "changed" });
    expect(
      draftEditOf(
        [streamEvent("EVENT_VOIDED", 4, { supersedes_event_id: BOOKING_EVENT_ID }), BOOKING],
        true,
      ),
    ).toEqual({ kind: "changed" });
  });

  it("closes on a voided later event that is no assessment: its void does not make the booking the draft again", () => {
    const memo = streamEvent("MEMO_UPDATED", 4);
    expect(draftEditOf([voids(memo, 5), memo, BOOKING], true)).toEqual({ kind: "changed" });
    // Fail-closed: the one void that keeps the draft is the void of an assessment, not any void.
    expect(draftEditOf([voids(hold, 5), hold, BOOKING], true)).toEqual({ kind: "changed" });
  });

  // Ruling R-102 (c), as measured on the API (register index 267 (iii)): `replace-draft` answers 200
  // for a draft with a standing assessment, with a voided one and with both, and voids what stands.
  describe("a Step 1 assessment does not close the form", () => {
    const first = streamEvent("COLLECTIBILITY_ASSESSED", 4);
    const second = streamEvent("COLLECTIBILITY_ASSESSED", 9);
    /** Booked, assessed, replaced: the voids of the booking and of its assessment, the new booking. */
    const replacedOnce = [rebooked(7), voids(first, 6), voids(BOOKING, 5), first, BOOKING];

    it("a standing assessment after the booking: open, and the guard says that one stands", () => {
      expect(draftEditOf([first, BOOKING], true)).toEqual({
        kind: "open",
        booking: BOOKING,
        head: 4,
        assessed: true,
      });
      // With a hold beside it, after it or before it.
      const held = { kind: "open", booking: BOOKING, head: 5, assessed: true };
      expect(draftEditOf([streamEvent("HOLD_APPLIED", 5), first, BOOKING], true)).toEqual(held);
      expect(draftEditOf([streamEvent("COLLECTIBILITY_ASSESSED", 5), hold, BOOKING], true)).toEqual(
        held,
      );
    });

    it("a voided assessment and none standing: open on the new booking, and none stands", () => {
      expect(draftEditOf(replacedOnce, true)).toEqual({
        kind: "open",
        booking: rebooked(7),
        head: 7,
        assessed: false,
      });
    });

    it("one voided and one standing: open, and one stands", () => {
      const assessedAgain = [second, streamEvent("HOLD_RELEASED", 8), ...replacedOnce];
      expect(draftEditOf(assessedAgain, true)).toEqual({
        kind: "open",
        booking: rebooked(7),
        head: 9,
        assessed: true,
      });
    });

    it("the void of an assessment after the booking keeps the draft, and what it voids does not stand", () => {
      expect(draftEditOf([voids(first, 5), first, BOOKING], true)).toEqual({
        kind: "open",
        booking: BOOKING,
        head: 5,
        assessed: false,
      });
    });

    it("an assessment that stands from before the booking in force is said too: the save voids it", () => {
      expect(draftEditOf([rebooked(6), voids(BOOKING, 5), first, BOOKING], true)).toEqual({
        kind: "open",
        booking: rebooked(6),
        head: 6,
        assessed: true,
      });
    });

    it("another event after the booking closes the form, assessment or not", () => {
      expect(draftEditOf([streamEvent("MEMO_UPDATED", 5), first, BOOKING], true)).toEqual({
        kind: "changed",
      });
      expect(draftEditOf([second, streamEvent("REGROUPED", 4), BOOKING], true)).toEqual({
        kind: "changed",
      });
      // A stream that was not read back to its start is not opened on account of an assessment.
      expect(draftEditOf([first, BOOKING], false)).toEqual({ kind: "changed" });
    });
  });
});

describe("SCR-PERM-01 on the draft form", () => {
  it("a reader without contract.create sees the access state", async () => {
    serve([]);
    renderApp(`/contracts/new?${CONTEXT}`, {
      me: signedInMe({ permissions: ["contract.read", "config.read"] }),
      screenRoutes: ROUTES,
    });

    expect(
      await screen.findByRole("heading", { name: "You do not have access to contract drafts" }),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Ask a workspace administrator for a role that includes preparing contracts.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("grid", { name: "Contract lines" })).toBeNull();
  });
});
