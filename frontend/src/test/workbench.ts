// The contract workbench world of the SF-03 tab and SF-07 tests (PRD §2.7 K-02 `SF-ORD-10002`): the
// API-S-Contract and API-S-Obligation the frame reads, and the MSW handlers of every read the frame
// issues before a tab renders. A suite adds the handlers of its own tab. (`contract.ts` beside this
// file is another thing: the date contract of mocked traffic.)
import { http, HttpResponse } from "msw";

import type { components } from "../lib/api/schema";
import { apiUrl, server } from "./msw";

export const CONTRACT_ID = "4b5c6d7e-8f90-4a1b-9c2d-3e4f5a6b7c8d";
export const VERSION_ID = "5c6d7e8f-90a1-4b2c-8d3e-4f5a6b7c8d9e";
export const O1_ID = "6d7e8f90-a1b2-4c3d-9e4f-5a6b7c8d9e0f";
export const K02 = "SF-ORD-10002";
/** SCREENS §0.12 context of the contract captures. */
export const CONTEXT = "entity=AVM-US&period=FY2026-P09&book=ASC606";

export const AVM_US = {
  id: "0a1b2c3d-4e5f-4a6b-8c7d-000000000001",
  code: "AVM-US",
  name: "Avenmoor US Inc.",
};

type Actor = components["schemas"]["ActorOut"];

export const MAYA_USER: Actor = {
  id: "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a",
  kind: "USER",
  display_name: "Maya Chen",
};
export const PRIYA_USER: Actor = {
  id: "6d2e9b8f-3c5a-4d7e-8f9b-8a7c6d5e4f3b",
  kind: "USER",
  display_name: "Priya Raman",
};
export const SYSTEM_ACTOR: Actor = { id: null, kind: "SYSTEM", display_name: "System" };

export function money(amount: string, currency = "USD") {
  return { amount, currency };
}

export const VERSION_CONTEXT = {
  as_of: "2026-09-30",
  book: "ASC606",
  contract_version_id: VERSION_ID,
  known_at: "2026-09-12T12:00:00Z",
  version_no: 5,
};

export const PERIOD = {
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

/** API-S-Contract of K-02, active, at version 5. */
export function workbenchContract(
  overrides: Readonly<Record<string, unknown>> = {},
): Record<string, unknown> {
  return {
    id: CONTRACT_ID,
    external_id: K02,
    contract_no: "CON-000003",
    customer: {
      id: "2b3c4d5e-6f70-4a81-9b92-a3b4c5d6e7f9",
      code: "C-02",
      name: "Marrowby Health Partners LLC (Demo)",
    },
    contracting_entity: AVM_US,
    status: "ACTIVE",
    status_reason: null,
    on_hold: false,
    combination_group: {
      id: "3c4d5e6f-7081-4a92-8ba3-b4c5d6e7f80a",
      code: "CG-CON-000003",
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
    head_stream_version: 5,
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
      allocation: `/api/v1/contracts/${CONTRACT_ID}/allocation`,
      balances: `/api/v1/contracts/${CONTRACT_ID}/balances`,
      events: `/api/v1/contracts/${CONTRACT_ID}/events`,
      explain_transaction_price: `/api/v1/explain/contract_version/${VERSION_ID}/transaction_price`,
      history: `/api/v1/contracts/${CONTRACT_ID}/history`,
      obligations: `/api/v1/contracts/${CONTRACT_ID}/obligations`,
      schedule: `/api/v1/contracts/${CONTRACT_ID}/schedule`,
      versions: `/api/v1/contracts/${CONTRACT_ID}/versions`,
    },
    created_at: "2026-01-02T10:00:00Z",
    updated_at: "2026-09-10T10:00:00Z",
    ...overrides,
  };
}

/** API-S-Obligation O1 of K-02: 100 seats `AVM-SEAT-MO`, 01 Jan 2026 to 31 Dec 2027. */
export function workbenchObligation(
  overrides: Readonly<Record<string, unknown>> = {},
): Record<string, unknown> {
  return {
    id: O1_ID,
    contract_id: CONTRACT_ID,
    obligation_key: "O1",
    obligation_version_id: "7e8f90a1-b2c3-4d4e-8f5a-6b7c8d9e0f1a",
    legacy_record_key: "O1",
    product: {
      id: "8f90a1b2-c3d4-4e5f-9a6b-7c8d9e0f1a2b",
      code: "AVM-SEAT-MO",
      name: "Avenmoor seat, monthly",
    },
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
      quantity: "100",
      remaining_unit_revenue_rate: null,
      stated_price: money("240000.00"),
      unit_ssp: null,
    },
    original: {
      allocated_amount: money("240000.00"),
      quantity: "100",
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
    ...overrides,
  };
}

export interface WorkbenchWorld {
  readonly contract?: Record<string, unknown>;
  readonly obligations?: readonly Record<string, unknown>[];
  /** The "Modifications <n>" tab count (`X-Erev-Total-Count` of the list read). */
  readonly modificationCount?: number;
}

/**
 * The handlers of the frame: the shell's reads, the contract, its obligations and the header's counts.
 * Tab reads registered by the suite afterwards take precedence.
 */
export function serveWorkbench(world: WorkbenchWorld = {}): void {
  const empty = () => HttpResponse.json({ items: [], next_cursor: null });
  const counted = (count: number) => () =>
    HttpResponse.json(
      { items: [], next_cursor: null },
      { headers: { "X-Erev-Total-Count": String(count) } },
    );
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
      HttpResponse.json({
        items: world.obligations ?? [workbenchObligation()],
        next_cursor: null,
      }),
    ),
    http.get(
      apiUrl(`/api/v1/contracts/${CONTRACT_ID}/modifications`),
      counted(world.modificationCount ?? 0),
    ),
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}`), () =>
      HttpResponse.json(world.contract ?? workbenchContract()),
    ),
    http.get(apiUrl("/api/v1/combination-suggestions"), empty),
    http.get(apiUrl("/api/v1/attachments"), counted(0)),
    http.get(apiUrl("/api/v1/jobs"), empty),
    http.get(apiUrl("/api/v1/approvals"), empty),
    http.get(apiUrl("/api/v1/judgements"), empty),
  );
}
