// @vitest-environment jsdom
// SF-03 Contract workbench (BUILD_SPEC CTR-22; SCREENS §4.1.3, §4.1.3.1, §4.1.4, §4.1.11, §4.9.8; DESIGN_SYSTEM
// DS-CMP-06, DS-CMP-15, DS-CMP-17; docs/dev-guide.md DG-FE-15; 04 API-S-Contract, API-S-AllocationWalk,
// §15.2 activation-checklist-failed): the KPI strip holds six Explain triggers with the contract asset and
// unbilled receivable secondary line; the tracker states come from `steps[]` and step 4 expands the
// allocation walk; a 409 activation-checklist-failed renders one line per failed code with its fix link.
import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { computeJobsKey } from "../../lib/api/queries/contracts";
import { instantMs } from "../../lib/format";
import { installMemoryStorage, probeRoute, renderApp, signedInMe } from "../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { figureFromLink } from "./obligation-pane";
import { distinctReviewWord } from "./workbench";

installMswServer();
installMemoryStorage();
// The workbench reads the periods, then the contract and its obligations, before the frame renders.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const MAYA = signedInMe({
  permissions: [
    "contract.read",
    "contract.create",
    "config.read",
    "ssp.read",
    "event.record",
    "judgement.create",
    "adjustment.create",
  ],
});

const CONTRACT_ID = "9a8b7c6d-5e4f-4a3b-9c2d-1e0f9a8b7c6d";
const VERSION_ID = "0b1c2d3e-4f50-4a61-8b72-c3d4e5f60718";
const O1_ID = "1c2d3e4f-5061-4a72-8c83-d4e5f6071829";
const O2_ID = "2d3e4f50-6172-4a83-9d94-e5f60718293a";
const US_ID = "0a1b2c3d-4e5f-4a6b-8c7d-000000000001";
// The T-CON-09 row of the contract's balances: an id of its own, which only the balance links carry.
const BALANCE_ID = "3e4f5061-7283-4a94-8ea5-f60718293a4b";
const CONTEXT = "entity=AVM-US&period=FY2026-P09&book=ASC606";

function money(amount: string, currency = "USD") {
  return { amount, currency };
}

const AVM_US = { id: US_ID, code: "AVM-US", name: "Avenmoor US Inc." };

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

type Step = "CONTRACT" | "OBLIGATIONS" | "TRANSACTION_PRICE" | "ALLOCATION" | "RECOGNITION";

function steps(states: Readonly<Record<Step, string>>) {
  return (Object.keys(states) as Step[]).map((step) => ({
    step,
    state: states[step],
    status_code: null,
    detail: step === "RECOGNITION" ? { recognized_ratio: "0.778192", obligations: [] } : {},
  }));
}

/**
 * The Explain addresses a balance entry names (04 API-S-Contract `kpis.balances[].links`, rev 1.174):
 * the balance row and, at a cut, the period the balance was read at.
 */
function balanceLinks(period: string | null): Record<string, string | null> {
  const base = `/api/v1/explain/contract_version_balance/${BALANCE_ID}`;
  const query = period === null ? "" : `?period=${period}`;
  return {
    explain_contract_liability: `${base}/contract_liability${query}`,
    explain_contract_asset: `${base}/contract_asset${query}`,
    explain_unbilled_receivable: `${base}/unbilled_receivable${query}`,
  };
}

/** API-S-Contract `kpis` of K-01; `liability` is the contract liability of its one balance entry. */
function kpis(
  links: Readonly<Record<string, string | null>> = balanceLinks(null),
  liability = "29944.11",
): Record<string, unknown> {
  return {
    transaction_price: money("135000.00"),
    billed_to_date: money("135000.00"),
    revenue_to_date: money("105055.89"),
    scheduled: money("29944.11"),
    awaiting_trigger: money("0.00"),
    rpo: money("29944.11"),
    balances: [
      {
        entity: AVM_US,
        contract_liability: money(liability),
        contract_asset: money("0.00"),
        unbilled_receivable: money("0.00"),
        refund_liability: money("0.00"),
        links,
      },
    ],
  };
}

/** PRD §2.7 K-01 `SF-ORD-10001` at FY2026-P09 (API-S-Contract). */
function contract(overrides: Readonly<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    id: CONTRACT_ID,
    external_id: "SF-ORD-10001",
    contract_no: "C-000001",
    customer: {
      id: "2b3c4d5e-6f70-4a81-9b92-a3b4c5d6e7f8",
      code: "C-01",
      name: "Pellworth Logistics Inc. (Demo)",
    },
    contracting_entity: AVM_US,
    status: "ACTIVE",
    status_reason: null,
    on_hold: false,
    combination_group: {
      id: "3c4d5e6f-7081-4a92-8ba3-b4c5d6e7f809",
      code: "CG-000001",
      is_singleton: true,
      member_contract_ids: [CONTRACT_ID],
    },
    inception_date: "2026-01-01",
    signature_date: "2025-12-15",
    payment_terms: "Net 30",
    transaction_currency: "USD",
    source_system: "SALESFORCE",
    region: "NA",
    channel: "Direct",
    contract_type: "Subscription",
    document_ref: "OF-10001",
    has_commercial_substance: true,
    custom_attributes: {},
    termination: null,
    memo_1: null,
    memo_2: null,
    memo_3: null,
    open_exception_count: 0,
    head_stream_version: 6,
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
    kpis: kpis(),
    kpis_ratios: { billed: "1.000000", recognized: "0.778192", pending_trigger_count: 0 },
    steps: steps({
      CONTRACT: "COMPLETE",
      OBLIGATIONS: "COMPLETE",
      TRANSACTION_PRICE: "COMPLETE",
      ALLOCATION: "COMPLETE",
      RECOGNITION: "COMPLETE",
    }),
    context: {
      as_of: "2026-09-30",
      book: "ASC606",
      contract_version_id: VERSION_ID,
      known_at: "2026-09-12T12:00:00Z",
      version_no: 6,
    },
    links: {
      self: `/api/v1/contracts/${CONTRACT_ID}`,
      obligations: `/api/v1/contracts/${CONTRACT_ID}/obligations`,
      events: `/api/v1/contracts/${CONTRACT_ID}/events`,
      versions: `/api/v1/contracts/${CONTRACT_ID}/versions`,
      allocation: `/api/v1/contracts/${CONTRACT_ID}/allocation`,
      schedule: `/api/v1/contracts/${CONTRACT_ID}/schedule`,
      balances: `/api/v1/contracts/${CONTRACT_ID}/balances`,
      history: `/api/v1/contracts/${CONTRACT_ID}/history`,
      explain_transaction_price: `/api/v1/explain/contract_version/${VERSION_ID}/transaction_price`,
    },
    created_at: "2026-01-02T10:00:00Z",
    updated_at: "2026-09-10T10:00:00Z",
    ...overrides,
  };
}

function obligation(
  id: string,
  key: string,
  product: { readonly code: string; readonly name: string },
  allocated: string,
): Record<string, unknown> {
  return {
    id,
    contract_id: CONTRACT_ID,
    obligation_key: key,
    obligation_version_id: `${id.slice(0, 35)}f`,
    legacy_record_key: key,
    product: { id: `${id.slice(0, 35)}e`, ...product },
    stratification: "",
    obligation_kind: "STANDARD",
    distinctness: "distinct",
    series_increment_unit: null,
    pob_template_version: {
      id: `${id.slice(0, 35)}d`,
      template_code: "TPL-SUB-DAILY",
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
    end_date: "2026-12-31",
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
      allocated_amount: money(allocated),
      allocation_adjustment: money("0.00"),
      allocation_weight: "0.500000",
      quantity: "1",
      remaining_unit_revenue_rate: null,
      stated_price: money(allocated),
      unit_ssp: null,
    },
    original: {
      allocated_amount: money(allocated),
      quantity: "1",
      ssp_high: null,
      ssp_in_range: null,
      ssp_low: null,
      ssp_mid: null,
      ssp_selected: allocated,
      stated_price: money(allocated),
      total_contract_price: money("135000.00"),
      total_contract_ssp: "135000.00",
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
      version_label: "2026-H1",
    },
    to_date: {
      billed: money(allocated),
      catch_up: money("0.00"),
      catch_up_estimate: money("0.00"),
      catch_up_modification: money("0.00"),
      catch_up_tp_change: money("0.00"),
      delivered_quantity: "0",
      pre_standard_revenue: money("0.00"),
      progress_ratio: "0.750000",
      returned_quantity: "0",
      revenue: money("0.00"),
      ssp_delivered: "0",
    },
    remaining: {
      allocation: money("0.00"),
      billing: money("0.00"),
      quantity: "0",
      ssp: "0",
    },
    scheduled: money("0.00"),
    awaiting_trigger: money("0.00"),
    ratios: { recognized: null, scheduled: null, awaiting_trigger: null },
    position: { label: "CONTRACT_LIABILITY", amount: money("0.00") },
    netting_reclass: { amount: money("0.00"), role: null },
    context: {
      as_of: "2026-09-30",
      book: "ASC606",
      contract_version_id: VERSION_ID,
      known_at: "2026-09-12T12:00:00Z",
      version_no: 6,
    },
    links: {
      self: `/api/v1/obligations/${id}`,
      versions: `/api/v1/obligations/${id}/versions`,
      schedule: `/api/v1/obligations/${id}/schedule`,
      events: `/api/v1/obligations/${id}/events`,
      explain_revenue_to_date: `/api/v1/explain/obligation_version/${id}/revenue_cum`,
      explain_allocated_amount: `/api/v1/explain/obligation_version/${id}/allocated_amount`,
    },
  };
}

const OBLIGATIONS = [
  obligation(O1_ID, "O1", { code: "AVM-PLAT-100", name: "Platform subscription" }, "97627.12"),
  obligation(O2_ID, "O2", { code: "AVM-IMPL-PLUS", name: "Implementation plus" }, "22372.88"),
];

/** SCREENS §4.1.10 `SF-ORD-20417` allocation walk (WLD-X-23, J-03.6). */
const WALK = {
  context: {
    as_of: "2026-09-30",
    book: "ASC606",
    contract_version_id: VERSION_ID,
    known_at: "2026-09-12T12:00:00Z",
    version_no: 6,
  },
  transaction_price: money("120000.00"),
  total_ssp: "118000.00",
  lines: [
    {
      obligation_key: "O1",
      product: {
        id: "5e6f7081-92a3-4bb4-8cc5-d6e7f8091a2b",
        code: "AVM-PLAT-100",
        name: "Platform",
      },
      ssp_book_version: { id: "6f708192-a3b4-4cc5-9dd6-e7f8091a2b3c", label: "US-LIST 2026-H1" },
      ssp_method: "observable",
      ssp_entry_id: null,
      low: "85000.00",
      mid: "100000.00",
      high: "115000.00",
      stated_price: money("96000.00"),
      range_position: "INSIDE",
      outside_range_point: null,
      in_range: true,
      selected_ssp: "96000.00",
      weight: "0.813559",
      exact_quota: "97627.118644",
      rounding_residue: "0.000000",
      allocated: money("97627.12"),
      allocation_adjustment: money("1627.12"),
    },
    {
      obligation_key: "O2",
      product: { id: "708192a3-b4c5-4dd6-8ee7-f8091a2b3c4d", code: "AVM-IMPL-PLUS", name: "Impl" },
      ssp_book_version: { id: "6f708192-a3b4-4cc5-9dd6-e7f8091a2b3c", label: "US-LIST 2026-H1" },
      ssp_method: "observable",
      ssp_entry_id: null,
      low: "18000.00",
      mid: "20000.00",
      high: "22000.00",
      stated_price: money("24000.00"),
      range_position: "ABOVE",
      outside_range_point: "NEAREST_BOUND",
      in_range: false,
      selected_ssp: "22000.00",
      weight: "0.186441",
      exact_quota: "22372.881356",
      rounding_residue: "0.000000",
      allocated: money("22372.88"),
      allocation_adjustment: money("-1627.12"),
    },
  ],
  totals: { allocated: money("120000.00"), allocation_adjustment: money("0.00") },
};

const EXPLANATION = {
  calc_trace_id: "7a8b9c0d-1e2f-4a3b-8c4d-5e6f7a8b9c0d",
  engine_version: "1.0.0",
  root_node_id: "revenue_cum:CG-000001:-",
  nodes: [
    {
      id: "revenue_cum:CG-000001:-",
      measure: "revenue_cum",
      value: "105055.89",
      currency: "USD",
      formula_id: "F-REC-SUM",
      params: {},
      rounding_residue: null,
      inputs: [],
    },
  ],
  narrative: ["Recognized to date is the sum over the obligations."],
  history: [],
  context: { as_of: "2026-09-30", known_at: "2026-09-12T12:00:00Z" },
  drill: { source_rows: [] },
};

/** API-S-ContractVersion of version 6 with the build-up member `consideration_payable` as given. */
function version(payable: string): Record<string, unknown> {
  return {
    id: VERSION_ID,
    version_no: 6,
    book: "ASC606",
    known_at: "2026-09-12T12:00:00Z",
    cause_events: [],
    engine_version: "1.0.0",
    input_sha256: "a".repeat(64),
    output_sha256: "b".repeat(64),
    status_in_book: "ACTIVE",
    status_reason_in_book: null,
    transaction_price_buildup: {
      fixed: money("135000.00"),
      vc_constrained: money("0.00"),
      vc_excluded: money("0.00"),
      expected_returns: money("0.00"),
      consideration_payable: money(payable),
      financing_adjustment: money("0.00"),
      noncash: money("0.00"),
      sales_tax_excluded: money("0.00"),
      out_of_scope: money("0.00"),
      total: money("135000.00"),
    },
    total_ssp: "135000.00",
    revenue_to_date: money("105055.89"),
    billed_to_date: money("135000.00"),
    rpo: money("29944.11"),
    scheduled: money("29944.11"),
    awaiting_trigger: money("0.00"),
    modification_boundary_no: 0,
    pinned_refs: {},
    pinned_policies: {},
    obligations: [],
    balances: [],
  };
}

interface Recorded {
  readonly explain: string[];
  readonly commands: {
    readonly path: string;
    readonly ifMatch: string | null;
    readonly key: string | null;
  }[];
}

function serve(recorded: Recorded, current: Record<string, unknown> = contract()) {
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
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
      HttpResponse.json({ items: OBLIGATIONS, next_cursor: null }),
    ),
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/allocation`), () => HttpResponse.json(WALK)),
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/versions/6`), () =>
      HttpResponse.json(version("0.00")),
    ),
    // SCREENS §4.1.7: the "Modifications <n>" tab count (CTR-24).
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/modifications`), () =>
      HttpResponse.json(
        { items: [], next_cursor: null },
        { headers: { "X-Erev-Total-Count": "2" } },
      ),
    ),
    // SCREENS §8.2: the "Estimates <n>" tab count (CTR-25).
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/estimates`), () =>
      HttpResponse.json(
        { items: [], next_cursor: null },
        { headers: { "X-Erev-Total-Count": "1" } },
      ),
    ),
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}`), () => HttpResponse.json(current)),
    http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/submit-activation`), ({ request }) => {
      recorded.commands.push({
        path: new URL(request.url).pathname,
        ifMatch: request.headers.get("If-Match"),
        key: request.headers.get("Idempotency-Key"),
      });
      return problemResponse("activation-checklist-failed", 409, "Activation checklist failed", {
        detail: "The contract cannot be activated until every checklist item passes.",
        errors: [
          {
            field: null,
            rule_id: "SOURCE_REFERENCE",
            message: "No contract reference is recorded.",
          },
          {
            field: null,
            rule_id: "DISTINCT_REVIEW",
            message: "Distinct review not recorded for O2 (AVM-IMPL-PLUS).",
          },
          { field: null, rule_id: "STEP1_RECORD", message: "Step 1 review not recorded." },
        ],
      });
    }),
    http.get(apiUrl("/api/v1/combination-suggestions"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/attachments"), () =>
      HttpResponse.json(
        { items: [], next_cursor: null },
        { headers: { "X-Erev-Total-Count": "0" } },
      ),
    ),
    http.get(apiUrl("/api/v1/jobs"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/approvals"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/judgements"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/events`), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/explain/:objectType/:objectId/:measure"), ({ request }) => {
      const url = new URL(request.url);
      recorded.explain.push(`${url.pathname}${url.search}`);
      return HttpResponse.json(EXPLANATION);
    }),
  );
}

function newRecorded(): Recorded {
  return { explain: [], commands: [] };
}

describe("SF-03 contract workbench", () => {
  it("kpi strip has six explain triggers", async () => {
    const recorded = newRecorded();
    serve(recorded);
    renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const strip = await screen.findByRole("region", { name: "Key figures (USD, ASC 606)" });
    expect(strip.getAttribute("data-testid")).toBe("SF-03-kpi-strip");
    expect(
      within(strip)
        .getAllByRole("term")
        .map((term) => term.textContent),
    ).toEqual([
      "Transaction price",
      "Billed",
      "Recognized",
      "Scheduled",
      "Awaiting trigger",
      "Contract liability",
    ]);
    // Six KPI values and the two secondary figures of the sixth cell, each an Explain trigger.
    expect(
      within(strip)
        .getAllByRole("button", { name: /^Explain / })
        .map((button) => button.getAttribute("aria-label")),
    ).toEqual([
      "Explain Transaction price, USD 135,000.00",
      "Explain Billed, USD 135,000.00",
      "Explain Recognized, USD 105,055.89",
      "Explain Scheduled, USD 29,944.11",
      "Explain Awaiting trigger, USD 0.00",
      "Explain Contract liability, USD 29,944.11",
      "Explain Contract asset, USD 0.00",
      "Explain Unbilled receivable, USD 0.00",
    ]);
    const liability = screen.getByTestId("SF-03-kpi-contract-liability");
    expect(
      within(liability).getByRole("button", { name: "Explain Contract liability, USD 29,944.11" }),
    ).toBeTruthy();
    const cell = liability.closest("div");
    expect(cell?.textContent).toContain("Contract asset");
    expect(cell?.textContent).toContain("Unbilled receivable");
    expect(strip.textContent).toContain("100.0% of transaction price");
    expect(strip.textContent).toContain("77.8% of transaction price");

    // SCREENS §4.1.4 rev 1.21: Recognized is no node of the trace at the contract's level, so its cell
    // opens the list level (below) and asks the API for no contract-level explanation.
    fireEvent.click(
      within(strip).getByRole("button", { name: "Explain Recognized, USD 105,055.89" }),
    );
    const list = await screen.findByRole("complementary", { name: "Recognized to date" });
    expect(await within(list).findByRole("table", { name: "By obligation" })).toBeTruthy();
    expect(recorded.explain).toEqual([]);

    fireEvent.click(
      within(strip).getByRole("button", { name: "Explain Transaction price, USD 135,000.00" }),
    );
    await waitFor(() => {
      expect(recorded.explain).toEqual([
        `/api/v1/explain/contract_version/${VERSION_ID}/transaction_price?book=ASC606&depth=6`,
      ]);
    });
  });

  // W-17 (supervisor ruling R-76 (c), (f); SCREENS §4.1.2 and §4.1.4 rev 1.10; 04 API-C-10 rev 1.132).
  const AUGUST = {
    ...PERIOD,
    period: {
      ...PERIOD.period,
      id: "2d3e4f5a-6b7c-4d8e-9f0a-1b2c3d4e5f6a",
      period_key: "FY2026-P08",
      name: "Aug 2026",
      period_no: 8,
      start_date: "2026-08-01",
      end_date: "2026-08-31",
    },
    state: "closed",
    is_first_open: false,
  };

  function measured(
    computedAt: string | null,
    period: { readonly period_key: string; readonly end_date: string } | null,
  ): Record<string, unknown> {
    return contract({
      // The balance links name the period of the cut, as the context does.
      kpis: kpis(balanceLinks(period?.period_key ?? null)),
      context: {
        as_of: "2026-09-30",
        book: "ASC606",
        contract_version_id: VERSION_ID,
        // The read's record cut-off: later than the computation, and not what "Last computed" shows.
        known_at: "2026-09-12T12:00:00Z",
        version_no: 6,
        computed_at: computedAt,
        measured_period: period,
      },
    });
  }

  function metaOf(label: string): string | null {
    const term = screen.getAllByRole("term").find((candidate) => candidate.textContent === label);
    return term?.nextElementSibling?.textContent ?? null;
  }

  it("Last computed is the time of the computation, and the figures name no older period while they are the context period's", async () => {
    serve(
      newRecorded(),
      measured("2026-09-10T08:15:00Z", { period_key: "FY2026-P09", end_date: "2026-09-30" }),
    );
    renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    // SCREENS §4.1.4 rev 1.21: the heading names the period the figures are measured at, always.
    await screen.findByRole("region", { name: "Key figures at Sep 2026 (USD, ASC 606)" });
    expect(metaOf("Last computed")).toBe("10 Sep 2026 08:15 UTC");
    expect(metaOf("Figures as of")).toBeNull();
  });

  it("figures measured at the version's horizon, an older period than the context's, say so", async () => {
    serve(
      newRecorded(),
      measured("2026-08-20T09:00:00Z", { period_key: "FY2026-P08", end_date: "2026-08-31" }),
    );
    server.use(
      http.get(apiUrl("/api/v1/periods"), () =>
        HttpResponse.json({ items: [AUGUST, PERIOD], next_cursor: null }),
      ),
    );
    renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    await screen.findByRole("region", { name: "Key figures at Aug 2026 (USD, ASC 606)" });
    await waitFor(() => {
      expect(metaOf("Figures as of")).toContain("Aug 2026");
    });
    // DS-CMP-26 with the words of rev 1.21: the marker beside the period says what the period is, and
    // does not say that a recalculation is queued (no job need exist).
    const marker = within(screen.getByTestId("SF-03-figures-as-of")).getByRole("button", {
      name: "Measured at Aug 2026, the last period this contract was computed for.",
    });
    expect(marker.querySelector("svg")).not.toBeNull();
    expect(metaOf("Last computed")).toBe("20 Aug 2026 09:00 UTC");
  });

  it("a contract without a computation shows no Last computed", async () => {
    serve(newRecorded(), measured(null, null));
    renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    // Nothing is measured yet (`measured_period` null): the heading names no period.
    await screen.findByRole("region", { name: "Key figures (USD, ASC 606)" });
    expect(metaOf("Last computed")).toBeNull();
    expect(metaOf("Figures as of")).toBeNull();
  });

  it("the balance cell's figures are explained at the address their balance entry names", async () => {
    const recorded = newRecorded();
    serve(
      recorded,
      measured("2026-09-10T08:15:00Z", { period_key: "FY2026-P09", end_date: "2026-09-30" }),
    );
    renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const strip = await screen.findByRole("region", {
      name: "Key figures at Sep 2026 (USD, ASC 606)",
    });
    fireEvent.click(
      within(strip).getByRole("button", { name: "Explain Contract liability, USD 29,944.11" }),
    );
    await waitFor(() => {
      // SCREENS §4.1.4 rev 1.24: the id is the balance row's, which only the link carries (the route
      // answers 404 for the contract version's id), and the period is the one the link names.
      expect(recorded.explain).toEqual([
        `/api/v1/explain/contract_version_balance/${BALANCE_ID}/contract_liability?period=FY2026-P09&book=ASC606&depth=6`,
      ]);
    });
    fireEvent.click(
      within(strip).getByRole("button", { name: "Explain Contract asset, USD 0.00" }),
    );
    await waitFor(() => {
      expect(recorded.explain.at(-1)).toBe(
        `/api/v1/explain/contract_version_balance/${BALANCE_ID}/contract_asset?period=FY2026-P09&book=ASC606&depth=6`,
      );
    });
  });

  it("a balance figure whose entry names no explanation prints without a trigger", async () => {
    // A cut before the first period the version measures: the balances are 0.00, no node of the trace
    // holds them and the entry's links are null (04 API-S-Contract `kpis.balances[].links`, rev 1.174).
    const recorded = newRecorded();
    serve(
      recorded,
      contract({
        kpis: kpis(
          {
            explain_contract_liability: null,
            explain_contract_asset: null,
            explain_unbilled_receivable: null,
          },
          "0.00",
        ),
      }),
    );
    renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const strip = await screen.findByRole("region", { name: "Key figures (USD, ASC 606)" });
    // The three figures of the sixth cell are printed, and none of them opens a panel.
    const liability = screen.getByTestId("SF-03-kpi-contract-liability");
    expect(liability.textContent).toBe("0.00");
    const cell = liability.closest("div");
    expect(cell?.textContent).toContain("Contract asset0.00");
    expect(cell?.textContent).toContain("Unbilled receivable0.00");
    expect(
      within(strip)
        .getAllByRole("button", { name: /^Explain / })
        .map((button) => button.getAttribute("aria-label")),
    ).toEqual([
      "Explain Transaction price, USD 135,000.00",
      "Explain Billed, USD 135,000.00",
      "Explain Recognized, USD 105,055.89",
      "Explain Scheduled, USD 29,944.11",
      "Explain Awaiting trigger, USD 0.00",
    ]);
    expect(recorded.explain).toEqual([]);
  });

  it("an API explain link keeps the period it names", () => {
    expect(
      figureFromLink(
        `/api/v1/explain/obligation_version/${O1_ID}/revenue_cum?period=FY2026-P09`,
        "ASC606",
      ),
    ).toEqual({
      objectType: "obligation_version",
      id: O1_ID,
      measure: "revenue_cum",
      periodKey: "FY2026-P09",
      book: "ASC606",
    });
    // A link without a period names the version's node, as before.
    expect(
      figureFromLink(`/api/v1/explain/obligation_version/${O1_ID}/allocated_amount`, null),
    ).toEqual({ objectType: "obligation_version", id: O1_ID, measure: "allocated_amount" });
  });

  // W-17, the list level (supervisor ruling R-112 (h); SCREENS §4.1.4 and §6.3 rev 1.21).
  /** API-S-Obligation as main answers it (04 rev 1.132): the to-date links carry the measured period. */
  function atCut(
    item: Record<string, unknown>,
    revenue: string,
    billedLink: boolean,
  ): Record<string, unknown> {
    const id = String(item.obligation_version_id);
    return {
      ...item,
      to_date: { ...(item.to_date as Record<string, unknown>), revenue: money(revenue) },
      links: {
        ...(item.links as Record<string, unknown>),
        explain_revenue_to_date: `/api/v1/explain/obligation_version/${id}/revenue_cum?period=FY2026-P09`,
        explain_billed_to_date: billedLink
          ? `/api/v1/explain/obligation_version/${id}/billed_cum?period=FY2026-P09`
          : null,
      },
    };
  }
  const O1_VERSION = String(OBLIGATIONS[0]?.obligation_version_id);

  async function openStripAtCut(recorded: Recorded, payable = "0.00"): Promise<HTMLElement> {
    serve(
      recorded,
      measured("2026-09-10T08:15:00Z", { period_key: "FY2026-P09", end_date: "2026-09-30" }),
    );
    server.use(
      http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/obligations`), () =>
        HttpResponse.json({
          items: [
            atCut(OBLIGATIONS[0] ?? {}, "73220.34", true),
            // The API links no billing explanation for this obligation.
            atCut(OBLIGATIONS[1] ?? {}, "22372.88", false),
          ],
          next_cursor: null,
        }),
      ),
      http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/versions/6`), () =>
        HttpResponse.json(version(payable)),
      ),
    );
    renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    return screen.findByRole("region", { name: "Key figures at Sep 2026 (USD, ASC 606)" });
  }

  function listRows(panel: HTMLElement): (string | undefined)[][] {
    return within(within(panel).getByRole("table", { name: "By obligation" }))
      .getAllByRole("row")
      .map((row) =>
        Array.from(row.querySelectorAll("th, td")).map((cell) =>
          cell.textContent?.replace(/\s/g, " "),
        ),
      );
  }

  it("Recognized opens the obligations at the measured period, and an entry opens the obligation's own explanation with its period", async () => {
    const recorded = newRecorded();
    const strip = await openStripAtCut(recorded);
    fireEvent.click(
      within(strip).getByRole("button", { name: "Explain Recognized, USD 105,055.89" }),
    );

    const name = "Recognized to date · Sep 2026";
    const list = await screen.findByRole("complementary", { name });
    // The cell's value, the API's figure: the panel adds nothing up.
    expect(within(list).getByText(/^USD\s105,055\.89$/)).toBeTruthy();
    expect(within(list).getByText("SF-ORD-10001 · ASC 606 · AVM-US")).toBeTruthy();
    await within(list).findByRole("table", { name: "By obligation" });
    expect(listRows(list)).toEqual([
      ["Obligation", "Recognized to date", "Explain"],
      ["O1 · AVM-PLAT-100", "USD 73,220.34", "Explain O1"],
      ["O2 · AVM-IMPL-PLUS", "USD 22,372.88", "Explain O2"],
    ]);
    expect(within(list).queryByRole("button", { name: "Verify" })).toBeNull();
    expect(within(list).queryByRole("link", { name: "Open calculation trace" })).toBeNull();
    expect(within(list).queryByRole("button", { name: "Copy link" })).toBeNull();
    // Scheduled's sentence belongs to Scheduled, and this version has no consideration payable.
    expect(within(list).queryByText(/^Scheduled is the allocated amount/)).toBeNull();
    expect(within(list).queryByText(/net of consideration payable/)).toBeNull();
    expect(recorded.explain).toEqual([]);

    fireEvent.click(within(list).getByRole("button", { name: "Explain O1" }));
    const entry = await screen.findByRole("complementary", {
      name: "Recognized to date · O1 · Sep 2026",
    });
    expect(within(entry).getByText("SF-ORD-10001 · O1 · ASC 606 · AVM-US")).toBeTruthy();
    await waitFor(() => {
      expect(recorded.explain).toEqual([
        `/api/v1/explain/obligation_version/${O1_VERSION}/revenue_cum?period=FY2026-P09&book=ASC606&depth=6`,
      ]);
    });
    fireEvent.click(within(entry).getByRole("button", { name: `Back to ${name}` }));
    expect(await screen.findByRole("complementary", { name })).toBeTruthy();
  });

  it("Billed lists what is billed for each obligation, with a button only where the API links the billing explanation", async () => {
    const recorded = newRecorded();
    const strip = await openStripAtCut(recorded);
    fireEvent.click(within(strip).getByRole("button", { name: "Explain Billed, USD 135,000.00" }));

    const list = await screen.findByRole("complementary", { name: "Billed to date · Sep 2026" });
    expect(within(list).getByText(/^USD\s135,000\.00$/)).toBeTruthy();
    await within(list).findByRole("table", { name: "By obligation" });
    expect(listRows(list)).toEqual([
      ["Obligation", "Billed to date", "Explain"],
      ["O1 · AVM-PLAT-100", "USD 97,627.12", "Explain O1"],
      ["O2 · AVM-IMPL-PLUS", "USD 22,372.88", ""],
    ]);
    expect(within(list).queryByText(/net of consideration payable/)).toBeNull();

    fireEvent.click(within(list).getByRole("button", { name: "Explain O1" }));
    await screen.findByRole("complementary", { name: "Billed to date · O1 · Sep 2026" });
    await waitFor(() => {
      expect(recorded.explain).toEqual([
        `/api/v1/explain/obligation_version/${O1_VERSION}/billed_cum?period=FY2026-P09&book=ASC606&depth=6`,
      ]);
    });
  });

  it("Scheduled keeps its own name and value, says what Scheduled is and lists what is recognized", async () => {
    const recorded = newRecorded();
    // Consideration payable in the version: its sentence is the Recognized list's, not this one's.
    const strip = await openStripAtCut(recorded, "-500.00");
    fireEvent.click(
      within(strip).getByRole("button", { name: "Explain Scheduled, USD 29,944.11" }),
    );

    const list = await screen.findByRole("complementary", { name: "Scheduled · Sep 2026" });
    expect(within(list).getByText(/^USD\s29,944\.11$/)).toBeTruthy();
    expect(
      within(list).getByText(
        "Scheduled is the allocated amount less the amounts recognized and awaiting a trigger. The table shows what is recognized for each obligation.",
      ),
    ).toBeTruthy();
    await within(list).findByRole("table", { name: "By obligation" });
    expect(listRows(list)).toEqual([
      ["Obligation", "Recognized to date", "Explain"],
      ["O1 · AVM-PLAT-100", "USD 73,220.34", "Explain O1"],
      ["O2 · AVM-IMPL-PLUS", "USD 22,372.88", "Explain O2"],
    ]);
    expect(within(list).queryByText(/net of consideration payable/)).toBeNull();
    expect(recorded.explain).toEqual([]);
  });

  it("the Recognized list says that the contract's figure is net of consideration payable when the version has any", async () => {
    const strip = await openStripAtCut(newRecorded(), "-500.00");
    fireEvent.click(
      within(strip).getByRole("button", { name: "Explain Recognized, USD 105,055.89" }),
    );
    const list = await screen.findByRole("complementary", {
      name: "Recognized to date · Sep 2026",
    });
    expect(
      await within(list).findByText(
        "The contract's figure is net of consideration payable released to date. The amounts of the obligations are before that reduction.",
      ),
    ).toBeTruthy();
  });

  it("a header read the API refuses by name (API-C-10) is a named state with what the API says, not the load error", async () => {
    serve(newRecorded());
    server.use(
      http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}`), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          detail: "1 field needs attention.",
          errors: [
            {
              field: "as_of",
              sheet: null,
              row: null,
              rule_id: "API-C-10",
              message:
                "Contract SF-ORD-10001, obligation O2: the calculation trace of contract version 6 holds no revenue_cum node per period, so the figure at 2026-09-30 cannot be read. Nothing is answered from the version's figure at 2026-01-01.",
            },
          ],
        }),
      ),
    );
    renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const state = await screen.findByTestId("SF-03-figures-unreadable");
    expect(
      within(state).getByRole("heading", {
        name: "The figures of this contract cannot be read for Sep 2026",
      }),
    ).toBeTruthy();
    expect(state.textContent).toContain(
      "Contract SF-ORD-10001, obligation O2: the calculation trace of contract version 6 holds no revenue_cum node per period",
    );
    expect(state.textContent).toContain("Reference 0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d.");
    expect(screen.queryByText("Could not load the contract")).toBeNull();
    // No figure is shown in its place.
    expect(screen.queryByRole("region", { name: /^Key figures/ })).toBeNull();
  });

  it("the refusal under a context without a period says as of today", async () => {
    serve(newRecorded());
    server.use(
      http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}`), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          detail: "1 field needs attention.",
          errors: [
            {
              field: "as_of",
              sheet: null,
              row: null,
              rule_id: "API-C-10",
              message: "Contract SF-ORD-10001, entity AVM-US: no balance node holds the figure.",
            },
          ],
        }),
      ),
    );
    renderApp(`/contracts/${CONTRACT_ID}/obligations?entity=AVM-US&book=ASC606`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const state = await screen.findByTestId("SF-03-figures-unreadable");
    expect(
      within(state).getByRole("heading", {
        name: "The figures of this contract cannot be read as of today",
      }),
    ).toBeTruthy();
    expect(state.textContent).toContain(
      "Contract SF-ORD-10001, entity AVM-US: no balance node holds the figure.",
    );
  });

  it("tracker states from steps", async () => {
    const recorded = newRecorded();
    serve(
      recorded,
      contract({
        steps: steps({
          CONTRACT: "COMPLETE",
          OBLIGATIONS: "IN_REVIEW",
          TRANSACTION_PRICE: "NEEDS_ATTENTION",
          ALLOCATION: "BLOCKED",
          RECOGNITION: "NOT_STARTED",
        }),
      }),
    );
    const { router } = renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    // The loaded tracker, once the obligations have been read (the skeleton holds no buttons).
    await screen.findByRole("button", { name: "Step 2, Obligations, in review, 2 obligations" });
    const tracker = screen.getByRole("list", { name: "ASC 606 steps" });
    expect(screen.getByTestId("SF-03-tracker").contains(tracker)).toBe(true);
    expect(
      within(tracker)
        .getAllByRole("button")
        .map((button) => button.getAttribute("aria-label")),
    ).toEqual([
      "Step 1, Contract, complete, Stand-alone contract",
      "Step 2, Obligations, in review, 2 obligations",
      "Step 3, Transaction price, needs attention, USD 135,000.00",
      "Step 4, Allocation, blocked, No SSP for AVM-PLAT-100",
      "Step 5, Recognition, not started",
    ]);

    const step4 = screen.getByTestId("SF-03-tracker-step-4");
    expect(step4.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(step4);
    await waitFor(() => {
      expect(new URLSearchParams(router.state.location.search).get("step")).toBe("4");
    });
    // The router's state settles before the commit that renders step 4 (F-ADM Q21): await the region.
    const evidence = await screen.findByRole("region", { name: "Allocation" });
    expect(evidence.getAttribute("data-testid")).toBe("SF-03-evidence-4");
    const walk = await within(evidence).findByRole("table", { name: /^Allocation walk/ });
    expect(walk.getAttribute("data-testid")).toBe("SF-03-grid-allocation-walk");
    expect(within(walk).getByText("Allocation walk (USD)")).toBeTruthy();
    const rows = within(walk).getAllByRole("row");
    // Header, O1, O2 and the totals row.
    expect(rows).toHaveLength(4);
    const o1 = rows[1];
    const o2 = rows[2];
    const totals = rows[3];
    if (o1 === undefined || o2 === undefined || totals === undefined) {
      throw new Error("allocation walk rows missing");
    }
    expect(within(o1).getByRole("rowheader").textContent).toBe("O1");
    expect(o1.textContent).toContain("US-LIST 2026-H1 · Observable");
    expect(o1.textContent).toContain("85,000.00");
    expect(o1.textContent).toContain("Inside range");
    expect(
      within(o1).getByRole("button", { name: "Explain Allocated · O1, USD 97,627.12" }),
    ).toBeTruthy();
    expect(o2.textContent).toContain("Above range: nearest bound applied");
    expect(o2.textContent).toContain("22,372.88");
    expect(totals.textContent).toContain("Total");
    expect(totals.textContent).toContain("120,000.00");
  });

  it("the allocation step names the SSP book version once its read answers, and nothing partial before", async () => {
    const SSP_VERSION = "6f708192-a3b4-4cc5-9dd6-e7f8091a2b3c";
    const SSP_BOOK = "7081a2b3-c4d5-4ee6-8ff7-091a2b3c4d5e";
    let answer: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      answer = resolve;
    });
    serve(newRecorded());
    server.use(
      http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/obligations`), () =>
        HttpResponse.json({
          items: OBLIGATIONS.map((item) => ({
            ...item,
            ssp: {
              ...(item.ssp as object),
              book_version_id: SSP_VERSION,
              version_label: "2026-H1",
            },
          })),
          next_cursor: null,
        }),
      ),
      http.get(apiUrl(`/api/v1/ssp-book-versions/${SSP_VERSION}`), async () => {
        await held;
        return HttpResponse.json({
          id: SSP_VERSION,
          ssp_book_id: SSP_BOOK,
          legacy_version_label: "2026-H1",
        });
      }),
      http.get(apiUrl(`/api/v1/ssp-books/${SSP_BOOK}`), () =>
        HttpResponse.json({ id: SSP_BOOK, code: "US-LIST" }),
      ),
    );
    renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    // The obligations are read, the label of their SSP book version is not: the step is busy and
    // reads neither "Relative SSP" nor the version label alone (SCREENS §4.1.3 rev 1.29).
    await screen.findByRole("button", { name: /^Step 2, Obligations, complete/ });
    const waiting = screen.getByTestId("SF-03-tracker-step-4");
    expect(waiting.getAttribute("aria-label")).toBe("Step 4, Allocation, complete");
    expect(waiting.textContent).toBe("4 Allocation");
    expect(waiting.closest("li")?.getAttribute("aria-busy")).toBe("true");

    answer();
    const named = await screen.findByRole("button", {
      name: "Step 4, Allocation, complete, Relative SSP · US-LIST 2026-H1",
    });
    expect(named.textContent).toBe("4 AllocationRelative SSP · US-LIST 2026-H1");
    expect(named.closest("li")?.getAttribute("aria-busy")).toBeNull();
  });

  it("Change price opens SF-07 with the kind and the obligation, for a preparer on an active contract", async () => {
    const routes = [
      ...SCREEN_ROUTES.filter((route) => route.id === "SF-03"),
      probeRoute(
        "SF-07",
        "/contracts/:contractId/modifications/new",
        "modifications.wizard.documentTitle",
      ),
    ];
    const PREPARER = signedInMe({
      permissions: ["contract.read", "config.read", "ssp.read", "modification.create"],
    });
    const servePane = (current?: Record<string, unknown>) => {
      serve(newRecorded(), current);
      server.use(
        http.get(apiUrl(`/api/v1/obligations/${O1_ID}`), () => HttpResponse.json(OBLIGATIONS[0])),
      );
    };
    servePane();
    const { router } = renderApp(`/contracts/${CONTRACT_ID}/obligations/${O1_ID}?${CONTEXT}`, {
      me: PREPARER,
      screenRoutes: routes,
    });
    const pane = await screen.findByTestId("SF-03-pane-obligation");
    // SCREENS §5.3: "Change price" stands between "Record event" and the overflow menu.
    fireEvent.click(await within(pane).findByRole("button", { name: "Change price" }));
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/contracts/${CONTRACT_ID}/modifications/new`),
    );
    expect(router.state.location.search).toBe(`?${CONTEXT}&kind=PRICE_CHANGE&obligation=${O1_ID}`);
    cleanup();
    server.resetHandlers();

    // API-R-31 takes a modification of an active contract only, from a holder of modification.create.
    servePane(contract({ status: "COMPLETED" }));
    renderApp(`/contracts/${CONTRACT_ID}/obligations/${O1_ID}?${CONTEXT}`, {
      me: PREPARER,
      screenRoutes: routes,
    });
    const completed = await screen.findByTestId("SF-03-pane-obligation");
    await within(completed).findByRole("heading", { level: 2, name: "Platform subscription" });
    expect(within(completed).queryByRole("button", { name: "Change price" })).toBeNull();
    cleanup();
    server.resetHandlers();

    servePane();
    renderApp(`/contracts/${CONTRACT_ID}/obligations/${O1_ID}?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: routes,
    });
    const reader = await screen.findByTestId("SF-03-pane-obligation");
    await within(reader).findByRole("heading", { level: 2, name: "Platform subscription" });
    expect(within(reader).queryByRole("button", { name: "Change price" })).toBeNull();
  });

  // SCREENS §4.9.7 (rev 1.80; supervisor ruling R-126 (c), register index 308): policy overrides are
  // not in release 1.0, and "Request policy override" stands in neither menu that held it.
  it("the header's overflow of an active and of a completed contract holds no policy override: the five events, Apply hold, Edit memos, Combine with another contract, Copy link", async () => {
    for (const status of ["ACTIVE", "COMPLETED"]) {
      serve(newRecorded(), contract({ status }));
      renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}`, {
        me: MAYA,
        screenRoutes: SCREEN_ROUTES,
      });

      fireEvent.click(await screen.findByRole("button", { name: "More actions" }));
      const menu = screen.getByRole("menu", { name: "More actions" });
      expect(
        within(menu)
          .getAllByRole("menuitem")
          .map((item) => item.textContent),
      ).toEqual([
        "Record delivery",
        "Record progress",
        "Record milestone",
        "Record cost",
        "Record return",
        "Apply hold",
        "Edit memos",
        "Combine with another contract",
        "Copy link",
      ]);
      cleanup();
      server.resetHandlers();
    }
  });

  it("the obligation pane's overflow holds no policy override: Apply hold, Edit memos, Copy link", async () => {
    serve(newRecorded());
    server.use(
      http.get(apiUrl(`/api/v1/obligations/${O1_ID}`), () => HttpResponse.json(OBLIGATIONS[0])),
    );
    renderApp(`/contracts/${CONTRACT_ID}/obligations/${O1_ID}?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const pane = await screen.findByTestId("SF-03-pane-obligation");
    fireEvent.click(await within(pane).findByRole("button", { name: "More actions for O1" }));
    const menu = screen.getByRole("menu", { name: "More actions for O1" });
    expect(
      within(menu)
        .getAllByRole("menuitem")
        .map((item) => item.textContent),
    ).toEqual(["Apply hold", "Edit memos", "Copy link"]);
  });

  it("activation failure lines", async () => {
    const recorded = newRecorded();
    serve(
      recorded,
      contract({
        status: "DRAFT",
        activated_at: null,
        steps: steps({
          CONTRACT: "NEEDS_ATTENTION",
          OBLIGATIONS: "NEEDS_ATTENTION",
          TRANSACTION_PRICE: "COMPLETE",
          ALLOCATION: "COMPLETE",
          RECOGNITION: "COMPLETE",
        }),
      }),
    );
    renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const submit = await screen.findByRole("button", { name: "Submit for activation" });
    fireEvent.click(submit);
    const banner = await screen.findByTestId("SF-03-banner-header");
    expect(
      within(banner).getByRole("heading", { name: "Contract cannot be activated" }),
    ).toBeTruthy();
    expect(recorded.commands).toHaveLength(1);
    expect(recorded.commands[0]?.path).toBe(`/api/v1/contracts/${CONTRACT_ID}/submit-activation`);
    expect(recorded.commands[0]?.ifMatch).toBe('"s6"');
    expect(recorded.commands[0]?.key).toMatch(/^[0-9a-f-]{36}$/);

    const lines = within(banner).getAllByRole("listitem");
    expect(lines.map((line) => line.textContent)).toEqual([
      "No contract reference is recorded.Open documents",
      "Distinct review not recorded for O2 (AVM-IMPL-PLUS).Record distinct review",
      "Step 1 review not recorded.Record Step 1 review",
    ]);
    expect(lines.map((line) => within(line).getByRole("button").textContent)).toEqual([
      "Open documents",
      "Record distinct review",
      "Record Step 1 review",
    ]);

    fireEvent.click(within(banner).getByRole("button", { name: "Record distinct review" }));
    const drawer = await screen.findByRole("dialog", { name: "Record distinct review" });
    expect(within(drawer).getByText("O2")).toBeTruthy();
  });

  it("step 2 says Recorded for a reviewed distinct review alone, and else what the obligation's newest record waits for", async () => {
    // The checklist's DISTINCT_REVIEW asks for a REVIEWED record (PRD IMP-102): before rev 1.76 the
    // cell read "Recorded" for a record of any status, beside a line that said "not recorded".
    const review = (number: string, obligationId: string, status: string) =>
      ({
        id: `00000000-0000-4000-8000-${number.padStart(12, "0")}`,
        judgement_no: `JDG-${number.padStart(6, "0")}`,
        topic: "POB_DISTINCT_OVERRIDE",
        subject_type: "obligation",
        subject_id: obligationId,
        contract_id: CONTRACT_ID,
        status,
      }) as unknown as Parameters<typeof distinctReviewWord>[0][number];
    const word = (...statuses: readonly string[]) =>
      distinctReviewWord(
        statuses.map((status, index) => review(String(index + 1), O1_ID, status)),
        O1_ID,
      );
    expect(word()).toBe("Not recorded");
    expect(word("SUBMITTED")).toBe("Waiting for review");
    expect(word("REJECTED")).toBe("Rejected");
    expect(word("DRAFT")).toBe("Draft");
    // A reviewed record stands, whatever came before or after it.
    expect(word("REJECTED", "REVIEWED", "SUBMITTED")).toBe("Recorded");
    // The newest record that still counts says the word; a discarded or superseded one counts for
    // nothing.
    expect(word("SUBMITTED", "REJECTED")).toBe("Rejected");
    expect(word("REJECTED", "SUBMITTED", "VOIDED")).toBe("Waiting for review");
    expect(word("VOIDED", "SUPERSEDED")).toBe("Not recorded");
    // A record of another obligation says nothing of this one.
    expect(distinctReviewWord([review("9", O2_ID, "REVIEWED")], O1_ID)).toBe("Not recorded");

    const recorded = newRecorded();
    serve(recorded, contract({ status: "DRAFT", activated_at: null }));
    server.use(
      http.get(apiUrl("/api/v1/judgements"), () =>
        HttpResponse.json({
          items: [
            review("21", O1_ID, "REJECTED"),
            review("22", O1_ID, "REVIEWED"),
            review("23", O2_ID, "REJECTED"),
          ],
          next_cursor: null,
        }),
      ),
    );
    renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}&step=2`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const evidence = await screen.findByTestId("SF-03-evidence-2");
    const table = within(evidence).getByRole("table");
    await within(table).findByText("Recorded");
    expect(
      within(table)
        .getAllByRole("row")
        .slice(1)
        .map((row) => {
          const cells = within(row).getAllByRole("cell");
          return `${within(row).getByRole("rowheader").textContent ?? ""} ${cells[4]?.textContent ?? ""}`;
        }),
    ).toEqual(["O1 Recorded", "O2 Rejected"]);
  });

  it("route tabs of the built tab routes", async () => {
    const recorded = newRecorded();
    serve(recorded, contract({ status: "DRAFT", activated_at: null }));
    const { router } = renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    // SCREENS §4.1.2 tabs in order, each of a built route (XR-14), "Estimates <n>" and
    // "Modifications <n>" with their counts.
    const tabs = await screen.findByRole("navigation", { name: "SF-ORD-10001 sections" });
    await waitFor(() =>
      expect(
        within(tabs)
          .getAllByRole("link")
          .map((link) => (link.textContent ?? "").replace(/\s+/g, " ").trim()),
      ).toEqual([
        "Obligations 2",
        "Estimates 1",
        "Schedules",
        "Billing",
        "Journals",
        "Modifications 2",
        "History",
      ]),
    );
    expect(
      within(tabs)
        .getByRole("link", { name: /^History/ })
        .getAttribute("href"),
    ).toBe(`/contracts/${CONTRACT_ID}/history?${CONTEXT}`);
    // SCREENS §4.1.6: a draft offers "Edit draft" (SF-03:edit, RT-19) and keeps the context on the way.
    fireEvent.click(screen.getByRole("button", { name: "Edit draft" }));
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/contracts/${CONTRACT_ID}/edit`),
    );
    expect(router.state.location.search).toBe(`?${CONTEXT}`);
  });

  it("Edit draft is a command of a draft and of contract.create", async () => {
    serve(newRecorded());
    renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    await screen.findByRole("navigation", { name: "SF-ORD-10001 sections" });
    expect(screen.queryByRole("button", { name: "Edit draft" })).toBeNull();
    cleanup();

    serve(newRecorded(), contract({ status: "DRAFT", activated_at: null }));
    renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}`, {
      me: signedInMe({ permissions: ["contract.read", "journal.read"] }),
      screenRoutes: SCREEN_ROUTES,
    });
    await screen.findByRole("navigation", { name: "SF-ORD-10001 sections" });
    expect(screen.queryByRole("button", { name: "Edit draft" })).toBeNull();
  });
});

// SCREENS §5.6 "Events", as bound (rev 1.62): the origin of an event is told from its own members — a
// person's entry, then the import row, then the literal of `origin` (04 T-CON-05), an API client by its
// name — by the one rule column 9 of the Billing tab's invoices follows (tabs/billing.test.tsx).
describe("SF-03:obligation Events panel", () => {
  const SYSTEM = { id: null, kind: "SYSTEM", display_name: "System" };
  const PERSON = {
    id: "5a6b7c8d-9e0f-4a1b-8c2d-3e4f5a6b7c8d",
    kind: "USER",
    display_name: "Maya Chen",
  };
  const CLIENT = {
    id: "6b7c8d9e-0f1a-4b2c-9d3e-4f5a6b7c8d9e",
    kind: "API_CLIENT",
    display_name: "Billing sync",
  };

  function streamEvent(
    index: number,
    eventType: string,
    members: Readonly<Record<string, unknown>>,
  ): Record<string, unknown> {
    return {
      id: `7f8091a2-b3c4-4d5e-8f60-${String(index).padStart(12, "0")}`,
      contract_id: CONTRACT_ID,
      stream_version: index,
      event_type: eventType,
      schema_version: 1,
      effective_date: "2026-09-12",
      recorded_at: "2026-09-12T11:00:00Z",
      record_seq: 100 + index,
      is_manual: false,
      obligation_keys: ["O1"],
      payload: {},
      payload_sha256: "0".repeat(64),
      supersedes_event_id: null,
      approval_request_id: null,
      modification_id: null,
      estimate_version_id: null,
      manual_adjustment_id: null,
      import_upload_id: null,
      source_record_id: null,
      source_row: null,
      created_by: SYSTEM,
      computation: null,
      ...members,
    };
  }

  it("Origin names a person's entry, an import row and each origin literal of the API", async () => {
    serve(newRecorded());
    server.use(
      http.get(apiUrl(`/api/v1/obligations/${O1_ID}`), () => HttpResponse.json(OBLIGATIONS[0])),
      http.get(apiUrl(`/api/v1/obligations/${O1_ID}/events`), () =>
        HttpResponse.json({
          items: [
            // An event applied from a person's submission is appended as SYSTEM and stays manual (04
            // T-CON-05).
            streamEvent(1, "DELIVERY_RECORDED", { origin: "SYSTEM", is_manual: true }),
            streamEvent(2, "BILLING_RECORDED", {
              origin: "IMPORT",
              import_upload_id: "7c8d9e0f-1a2b-4c3d-8e4f-5a6b7c8d9e0f",
              source_row: {
                import_upload_id: "7c8d9e0f-1a2b-4c3d-8e4f-5a6b7c8d9e0f",
                sheet: null,
                row_number: 2,
              },
            }),
            streamEvent(3, "BILLING_RECORDED", { origin: "API", created_by: CLIENT }),
            streamEvent(4, "CONTRACT_BOOKED", { origin: "API", created_by: PERSON }),
            streamEvent(5, "CONTRACT_BOOKED", { origin: "UI", created_by: PERSON }),
            streamEvent(6, "BILLING_RECORDED", { origin: "IMPORT" }),
            streamEvent(7, "BILLING_RECORDED", { origin: "ADAPTER" }),
            streamEvent(8, "ESTIMATE_CHANGED", { origin: "SYSTEM" }),
            streamEvent(9, "OPENING_BALANCE_ESTABLISHED", { origin: "MIGRATION" }),
            // A literal 04 does not list is printed as it is: a seventh is seen, not hidden.
            streamEvent(10, "HOLD_APPLIED", { origin: "REPLAY" }),
          ],
          next_cursor: null,
        }),
      ),
    );
    renderApp(`/contracts/${CONTRACT_ID}/obligations/${O1_ID}?${CONTEXT}&pane=events`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const table = await screen.findByRole("table", { name: "Events" });
    expect(table.getAttribute("data-testid")).toBe("SF-03-grid-obligation-events");
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual(["Effective date", "Event", "Details", "Origin", "Approval", "Recorded at"]);
    const origins = within(table)
      .getAllByRole("row")
      .slice(1)
      .map((row) => row.querySelectorAll("th, td")[3]?.textContent);
    expect(origins).toEqual([
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
  });
});

// SCREENS §4.1.3 "Step 1 path", §4.1.5 banner 6, §4.1.6 and §4.9.1 (rev 1.11; supervisor rulings R-61 (f)
// and R-89; PRD SM-02; 04 §16.3): the Step 1 judgement is recorded in two steps, the review and, once it
// is reviewed, the assessment that cites it; a contract behind the not-a-contract gate then offers
// "Submit for activation".
// SCREENS §0.6 SCR-PERM-02 (rev 1.34; item W-12, slice b; supervisor ruling R-28): the workbench follows
// the contract's computation through the jobs of the workspace. A read of them that the API refuses
// shows the contract without a job and is not repeated.
describe("SF-03 contract workbench: the jobs of the workspace", () => {
  it("a refused read of the jobs shows the contract without the recalculation banner and is not sent again", async () => {
    serve(newRecorded());
    const asked: string[] = [];
    server.use(
      http.get(apiUrl("/api/v1/jobs"), ({ request }) => {
        asked.push(new URL(request.url).search);
        return problemResponse("forbidden", 403, "Permission denied");
      }),
    );
    const { queryClient } = renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    expect(await screen.findByRole("region", { name: "Key figures (USD, ASC 606)" })).toBeTruthy();
    // Settled as answered with no job: a query that has succeeded is not retried.
    await waitFor(() => {
      const read = queryClient.getQueryCache().find({ queryKey: computeJobsKey(CONTRACT_ID) });
      expect([read?.state.status, read?.state.data, read?.state.fetchFailureCount]).toEqual([
        "success",
        [],
        0,
      ]);
    });
    expect(asked).toHaveLength(1);
    expect(screen.queryByText("Permission denied")).toBeNull();
    expect(screen.queryByText(/Recalculation is queued/)).toBeNull();
  });
});

describe("SF-03 Step 1 path", () => {
  const MAYA_ACTOR = { id: MAYA.user.id, display_name: "Maya Chen", kind: "USER" } as const;
  const PRIYA_ACTOR = {
    id: "4d3c2b1a-0f9e-4d8c-9b7a-6f5e4d3c2b1a",
    display_name: "Priya Raman",
    kind: "USER",
  } as const;
  const REVIEW_ID = "1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f";
  const GATE_ID = "aa000000-0000-4000-8000-000000000001";
  const REQUEST_ID = "2d3e4f5a-6b7c-4d8e-9f0a-1b2c3d4e5f6a";

  function judgement(overrides: Readonly<Record<string, unknown>> = {}): Record<string, unknown> {
    return {
      id: REVIEW_ID,
      judgement_no: "JDG-000412",
      topic: "COLLECTIBILITY",
      subject_type: "contract",
      subject_id: CONTRACT_ID,
      contract_id: CONTRACT_ID,
      book: null,
      conclusion: "Collectibility is probable.",
      rationale: "The customer paid the deposit and its credit grade was raised to B.",
      alternatives_considered: null,
      codification_refs: ["606-10-25-1"],
      questionnaire: { credit_grade: "B", mitigation: "ADVANCE_PAYMENT" },
      status: "SUBMITTED",
      approval_request_id: REQUEST_ID,
      supersedes_id: null,
      content_sha256: "c".repeat(64),
      created_by: MAYA_ACTOR,
      reviewer: null,
      reviewed_at: null,
      created_at: "2026-09-10T15:02:00Z",
      updated_at: "2026-09-10T15:02:00Z",
      ...overrides,
    };
  }

  const REVIEWED = judgement({
    status: "REVIEWED",
    reviewer: PRIYA_ACTOR,
    reviewed_at: "2026-09-10T16:20:00Z",
    updated_at: "2026-09-10T16:20:00Z",
  });
  const GATE = judgement({
    id: GATE_ID,
    judgement_no: "JDG-000398",
    topic: "NOT_A_CONTRACT",
    conclusion: "Collectibility is not probable.",
    status: "REVIEWED",
    reviewer: PRIYA_ACTOR,
    reviewed_at: "2026-09-01T10:00:00Z",
    created_at: "2026-09-01T09:00:00Z",
    updated_at: "2026-09-01T10:00:00Z",
  });

  function assessed(book: string, record: string, probable: boolean, date: string, seq: number) {
    return {
      id: `bb000000-0000-4000-8000-00000000000${String(seq)}`,
      contract_id: CONTRACT_ID,
      event_type: "COLLECTIBILITY_ASSESSED",
      effective_date: date,
      record_seq: seq,
      recorded_at: `${date}T12:00:00Z`,
      supersedes_event_id: null,
      payload: { book, is_probable: probable, judgement_record_id: record },
    };
  }

  /**
   * The SYSTEM `EVENT_VOIDED` that `replace-draft` appends for an assessment of the booking it
   * replaces (04 §16.1 rev 1.150; ruling R-102 (c)).
   */
  function voided(target: ReturnType<typeof assessed>, seq: number) {
    return {
      id: `bb000000-0000-4000-8000-00000000000${String(seq)}`,
      contract_id: CONTRACT_ID,
      event_type: "EVENT_VOIDED",
      effective_date: target.effective_date,
      record_seq: seq,
      recorded_at: "2026-09-12T09:00:00Z",
      supersedes_event_id: target.id,
      payload: {
        reason_code: "DATA_CORRECTION",
        comment: "Step 1 assessment of a booking replaced by a corrected draft (replace-draft).",
      },
    };
  }

  interface Sent {
    readonly method: string;
    readonly path: string;
    readonly body: unknown;
    readonly ifMatch: string | null;
    readonly key: string | null;
  }

  /**
   * 04 T-CON-19 as the API applies it: a record of topic NOT_A_CONTRACT names
   * `consideration_nonrefundable` as a boolean, else 422 (the body is the API's own answer).
   */
  function questionnaireRefusal(body: unknown): Response | null {
    const record = body as {
      readonly topic?: string;
      readonly questionnaire?: Readonly<Record<string, unknown>>;
    };
    if (
      record.topic !== "NOT_A_CONTRACT" ||
      typeof record.questionnaire?.consideration_nonrefundable === "boolean"
    ) {
      return null;
    }
    return problemResponse("validation-failed", 422, "Check the highlighted fields", {
      detail: "Field required",
      code: null,
      errors: [
        {
          field: "questionnaire.consideration_nonrefundable",
          sheet: null,
          row: null,
          rule_id: "T-CON-19",
          message: "Field required",
        },
      ],
    });
  }

  /** The event types each read of the events route asked for, since the last `world()`. */
  let eventReads: string[][] = [];

  /** The world of one state of the path: the records, the assessments and the commands it records. */
  function world(
    status: "DRAFT" | "NOT_A_CONTRACT",
    records: readonly Record<string, unknown>[],
    events: readonly Record<string, unknown>[],
    refuse: (sent: Sent) => Response | null = () => null,
  ): Sent[] {
    const sent: Sent[] = [];
    eventReads = [];
    serve(
      newRecorded(),
      contract({
        status,
        activated_at: null,
        steps: steps({
          CONTRACT: "COMPLETE",
          OBLIGATIONS: "COMPLETE",
          TRANSACTION_PRICE: "COMPLETE",
          ALLOCATION: "COMPLETE",
          RECOGNITION: "COMPLETE",
        }),
      }),
    );
    const record = async (request: Request): Promise<Response | null> => {
      const item = {
        method: request.method,
        path: new URL(request.url).pathname,
        body: await request.json(),
        ifMatch: request.headers.get("If-Match"),
        key: request.headers.get("Idempotency-Key"),
      };
      sent.push(item);
      return refuse(item);
    };
    server.use(
      http.get(apiUrl("/api/v1/entities"), () =>
        HttpResponse.json({
          items: [
            {
              ...AVM_US,
              functional_currency: "USD",
              time_zone: "America/Los_Angeles",
              is_active: true,
              books: [
                { book_code: "ASC606", is_enabled: true },
                { book_code: "IFRS15", is_enabled: true },
              ],
            },
          ],
          next_cursor: null,
        }),
      ),
      http.get(apiUrl("/api/v1/judgements"), () =>
        HttpResponse.json({ items: records, next_cursor: null }),
      ),
      // 04 API-R-30: the route answers the event types it is asked for.
      http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/events`), ({ request }) => {
        const asked = new URL(request.url).searchParams.getAll("event_type");
        eventReads.push(asked);
        return HttpResponse.json({
          items: events.filter(
            (item) => asked.length === 0 || asked.includes(String(item.event_type)),
          ),
          next_cursor: null,
        });
      }),
      http.post(apiUrl("/api/v1/judgements"), async ({ request }) => {
        const refused = await record(request);
        return (
          refused ??
          questionnaireRefusal(sent.at(-1)?.body) ??
          HttpResponse.json(judgement({ status: "DRAFT" }), { status: 201 })
        );
      }),
      http.post(apiUrl(`/api/v1/judgements/${REVIEW_ID}/submit`), async ({ request }) => {
        const refused = await record(request);
        return refused ?? HttpResponse.json(judgement());
      }),
      http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/events`), async ({ request }) => {
        const refused = await record(request);
        return refused ?? HttpResponse.json({ events: [], job: null }, { status: 201 });
      }),
      http.post(
        apiUrl(`/api/v1/contracts/${CONTRACT_ID}/submit-activation`),
        async ({ request }) => {
          const refused = await record(request);
          return (
            refused ??
            HttpResponse.json(contract({ status: "PENDING_REVIEW" }), {
              headers: { "X-Erev-Approval-Request": REQUEST_ID },
            })
          );
        },
      ),
      http.get(apiUrl(`/api/v1/approvals/${REQUEST_ID}`), () =>
        HttpResponse.json({ id: REQUEST_ID, request_no: "APR-000440" }),
      ),
    );
    return sent;
  }

  function open() {
    return renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}&step=1`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
  }

  async function pathLine(): Promise<HTMLElement> {
    return screen.findByTestId("SF-03-step1-path");
  }

  async function overflow(): Promise<string[]> {
    fireEvent.click(await screen.findByRole("button", { name: "More actions" }));
    const items = within(screen.getByRole("menu", { name: "More actions" }))
      .getAllByRole("menuitem")
      .map((item) => item.textContent ?? "");
    fireEvent.keyDown(screen.getByRole("menu", { name: "More actions" }), { key: "Escape" });
    return items;
  }

  function answer(legend: RegExp, choice: "Yes" | "No"): void {
    const group = screen.getByRole("group", { name: legend });
    fireEvent.click(within(group).getByRole("radio", { name: choice }));
  }

  it("a draft without a review: Record Step 1 review creates and submits the record and appends no event", async () => {
    const sent = world("DRAFT", [], []);
    open();

    const line = await pathLine();
    expect(line.textContent).toBe("No Step 1 review is recorded.Record Step 1 review");
    expect(screen.getByTestId("SF-03-tracker-step-1").getAttribute("aria-label")).toBe(
      "Step 1, Contract, needs attention, Needs review",
    );

    fireEvent.click(within(line).getByRole("button", { name: "Record Step 1 review" }));
    const drawer = await screen.findByRole("dialog", { name: "Record Step 1 review" });
    answer(/^Approved and committed/, "Yes");
    answer(/^Rights identified/, "Yes");
    answer(/^Payment terms identified/, "Yes");
    answer(/^Collectibility probable/, "Yes");
    fireEvent.change(within(drawer).getByLabelText(/^Rationale/), {
      target: { value: "The customer paid the deposit and its credit grade was raised to B." },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Submit for review" }));

    expect(await screen.findByText("Step 1 review JDG-000412 submitted for review.")).toBeTruthy();
    expect(sent.map((item) => `${item.method} ${item.path}`)).toEqual([
      "POST /api/v1/judgements",
      `POST /api/v1/judgements/${REVIEW_ID}/submit`,
    ]);
    expect(sent[0]?.body).toMatchObject({
      topic: "COLLECTIBILITY",
      subject_type: "contract",
      subject_id: CONTRACT_ID,
    });
    // The record of a probable outcome carries no member of the NOT_A_CONTRACT questionnaire.
    const questionnaire = (sent[0]?.body as { questionnaire: Record<string, unknown> })
      .questionnaire;
    expect(Object.keys(questionnaire)).not.toContain("consideration_nonrefundable");
    expect(Object.keys(questionnaire)).not.toContain("event_c_met_on");
  });

  // DG-FE-05 rev 1.156 (item W-23): one press creates the record and submits it. When the second
  // step gets no answer, the second press must not create a second record.
  it("the submission gets no answer: the second press sends the record and its submission under the keys they had", async () => {
    let lose = true;
    const sent = world("DRAFT", [], [], (item) => {
      if (item.path.endsWith("/submit") && lose) {
        lose = false;
        return HttpResponse.error();
      }
      return null;
    });
    open();

    fireEvent.click(within(await pathLine()).getByRole("button", { name: "Record Step 1 review" }));
    const drawer = await screen.findByRole("dialog", { name: "Record Step 1 review" });
    answer(/^Approved and committed/, "Yes");
    answer(/^Rights identified/, "Yes");
    answer(/^Payment terms identified/, "Yes");
    answer(/^Collectibility probable/, "Yes");
    fireEvent.change(within(drawer).getByLabelText(/^Rationale/), {
      target: { value: "The customer paid the deposit and its credit grade was raised to B." },
    });
    const press = within(drawer).getByRole("button", { name: "Submit for review" });
    fireEvent.click(press);

    // First press: the record is created, the submission's answer is lost. The drawer says so and
    // keeps its input.
    expect(await screen.findByText("No answer came back from the server. Try again.")).toBeTruthy();
    expect(screen.getByRole("dialog", { name: "Record Step 1 review" })).toBeTruthy();
    await waitFor(() => {
      expect(press.getAttribute("aria-busy")).not.toBe("true");
    });

    fireEvent.click(press);
    expect(await screen.findByText("Step 1 review JDG-000412 submitted for review.")).toBeTruthy();
    expect(sent.map((item) => `${item.method} ${item.path}`)).toEqual([
      "POST /api/v1/judgements",
      `POST /api/v1/judgements/${REVIEW_ID}/submit`,
      "POST /api/v1/judgements",
      `POST /api/v1/judgements/${REVIEW_ID}/submit`,
    ]);
    // Second press, step 1: the same body under its old key — the API replays the record it stored
    // (the same record id), it creates no second one.
    expect(sent[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
    expect(sent[2]?.key).toBe(sent[0]?.key);
    expect(sent[2]?.body).toEqual(sent[0]?.body);
    // Step 2 under its old key, for that record.
    expect(sent[3]?.key).toBe(sent[1]?.key);
    expect(sent[1]?.key).not.toBe(sent[0]?.key);
  });

  it("a not-probable review is a record of topic NOT_A_CONTRACT with the members its questionnaire takes", async () => {
    const sent = world("DRAFT", [], []);
    open();

    fireEvent.click(within(await pathLine()).getByRole("button", { name: "Record Step 1 review" }));
    const drawer = await screen.findByRole("dialog", { name: "Record Step 1 review" });
    const nonrefundable = /^Consideration received is non-refundable \(ASC 606-10-25-7\)/;
    const transferStopped =
      /^Transfer stopped with no further obligation, since \(ASC 606-10-25-7\(c\)\)/;
    // 04 T-CON-19: the two members belong to the NOT_A_CONTRACT questionnaire only.
    expect(within(drawer).queryByRole("group", { name: nonrefundable })).toBeNull();
    answer(/^Approved and committed/, "Yes");
    answer(/^Rights identified/, "Yes");
    answer(/^Payment terms identified/, "Yes");
    answer(/^Collectibility probable/, "Yes");
    expect(within(drawer).queryByRole("group", { name: nonrefundable })).toBeNull();
    expect(within(drawer).queryByLabelText(transferStopped)).toBeNull();
    answer(/^Collectibility probable/, "No");
    expect(within(drawer).getByRole("group", { name: nonrefundable })).toBeTruthy();
    expect(within(drawer).getByLabelText(transferStopped)).toBeTruthy();
    fireEvent.change(within(drawer).getByLabelText(/^Rationale/), {
      target: { value: "The customer missed two payments and no mitigation is in place." },
    });

    // The required member is asked for before anything is sent.
    fireEvent.click(within(drawer).getByRole("button", { name: "Submit for review" }));
    const group = within(drawer).getByRole("group", { name: nonrefundable });
    expect(await within(group).findByText("Choose Yes or No.")).toBeTruthy();
    expect(sent).toEqual([]);

    answer(nonrefundable, "Yes");
    fireEvent.click(within(drawer).getByRole("button", { name: "Submit for review" }));

    await screen.findByText("Step 1 review JDG-000412 submitted for review.");
    expect(sent[0]?.body).toMatchObject({
      topic: "NOT_A_CONTRACT",
      conclusion: "Collectibility is not probable.",
      questionnaire: { consideration_nonrefundable: true, event_c_met_on: null },
    });
    expect(sent.some((item) => item.path.endsWith("/events"))).toBe(false);
  });

  it("a not-probable review sends the date of ASC 606-10-25-7(c) as a date and shows the API's refusal on the field", async () => {
    const refusal = () =>
      problemResponse("validation-failed", 422, "Check the highlighted fields", {
        detail: "The date lies after the entity's current date.",
        code: null,
        errors: [
          {
            field: "questionnaire.event_c_met_on",
            sheet: null,
            row: null,
            rule_id: "T-CON-19",
            message: "The date lies after the entity's current date.",
          },
        ],
      });
    let refuse = true;
    const sent = world("DRAFT", [], [], (item) =>
      item.path === "/api/v1/judgements" && refuse ? refusal() : null,
    );
    open();

    fireEvent.click(within(await pathLine()).getByRole("button", { name: "Record Step 1 review" }));
    const drawer = await screen.findByRole("dialog", { name: "Record Step 1 review" });
    answer(/^Approved and committed/, "Yes");
    answer(/^Rights identified/, "Yes");
    answer(/^Payment terms identified/, "Yes");
    answer(/^Collectibility probable/, "No");
    answer(/^Consideration received is non-refundable/, "No");
    const date = within(drawer).getByLabelText(
      /^Transfer stopped with no further obligation, since/,
    );
    fireEvent.change(date, { target: { value: "30 Sep 2026" } });
    fireEvent.blur(date);
    fireEvent.change(within(drawer).getByLabelText(/^Rationale/), {
      target: { value: "The customer missed two payments and no mitigation is in place." },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Submit for review" }));

    await waitFor(() => {
      expect(date.getAttribute("aria-invalid")).toBe("true");
    });
    // The refusal is said on the field it names, beside its help text.
    const described = (date.getAttribute("aria-describedby") ?? "")
      .split(" ")
      .map((id) => document.getElementById(id)?.textContent ?? "");
    expect(described).toContain("The date lies after the entity's current date.");
    expect(sent[0]?.body).toMatchObject({
      topic: "NOT_A_CONTRACT",
      questionnaire: { consideration_nonrefundable: false, event_c_met_on: "2026-09-30" },
    });

    refuse = false;
    fireEvent.click(within(drawer).getByRole("button", { name: "Submit for review" }));
    await screen.findByText("Step 1 review JDG-000412 submitted for review.");
  });

  it("a discarded Step 1 record is no record of the path: no review is recorded and the criteria name no record", async () => {
    // E-57 VOIDED (04 T-CON-19 rev 1.242): a draft that was discarded. It is neither the latest
    // Step 1 record of the path nor the record the criteria table falls back to.
    world(
      "DRAFT",
      [judgement({ status: "VOIDED", approval_request_id: null, questionnaire: null })],
      [],
    );
    open();

    const line = await pathLine();
    expect(line.textContent).toBe("No Step 1 review is recorded.Record Step 1 review");
    const criteria = await screen.findByRole("table", { name: "Criteria" });
    expect(criteria.textContent).not.toContain("JDG-000412");
    expect(within(criteria).getAllByText("Not recorded").length).toBeGreaterThan(0);
  });

  // SCREENS §4.1.3 (rev 1.66; PRD SM-10 `DRAFT` → `VOIDED`, IMP-104; 04 API-R-33 rev 1.242): the Step 1
  // review creates its record and sends it for review as two requests. A draft whose submission was
  // refused had no command once the drawer was closed, and it holds the activation.
  const DRAFT_ID = "3e4f5a6b-7c8d-4e9f-8a0b-2c3d4e5f6a7b";
  const LEFT_BEHIND = judgement({
    id: DRAFT_ID,
    judgement_no: "JDG-000413",
    status: "DRAFT",
    approval_request_id: null,
    content_sha256: null,
    created_at: "2026-09-11T09:00:00Z",
    updated_at: "2026-09-11T09:00:00Z",
  });
  const DRAFT_LINE = "Record JDG-000413 is a draft that was not sent for review.";

  /** The path's world with the records as the API lists them now, and the discards it was sent. */
  function withDiscard(records: readonly Record<string, unknown>[]) {
    world("DRAFT", [], []);
    const state = { records: [...records], discards: [] as string[] };
    server.use(
      http.get(apiUrl("/api/v1/judgements"), () =>
        HttpResponse.json({ items: state.records, next_cursor: null }),
      ),
      http.post(apiUrl(`/api/v1/judgements/${DRAFT_ID}/discard`), async ({ request }) => {
        state.discards.push(await request.text());
        state.records = state.records.map((item) =>
          item.id === DRAFT_ID ? { ...item, status: "VOIDED" } : item,
        );
        return HttpResponse.json(state.records.find((item) => item.id === DRAFT_ID));
      }),
    );
    return state;
  }

  it("a draft Step 1 record that was not sent for review is named beside the path, and Discard voids it after a confirmation", async () => {
    const state = withDiscard([LEFT_BEHIND]);
    open();

    // The draft is no step of the path: the path offers the review, and the draft is named with
    // its command.
    expect((await pathLine()).textContent).toBe(
      "No Step 1 review is recorded.Record Step 1 review",
    );
    const draft = await screen.findByTestId("SF-03-step1-draft");
    expect(draft.textContent).toBe(`${DRAFT_LINE}Discard`);
    // The criteria fall back to the draft and name its status.
    const criteria = await screen.findByRole("table", { name: "Criteria" });
    expect(within(criteria).getAllByText("Record JDG-000413 · Draft").length).toBeGreaterThan(0);

    fireEvent.click(within(draft).getByRole("button", { name: "Discard" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Discard this draft record?" });
    expect(dialog.getAttribute("data-testid")).toBe("SF-03-dialog-discard-record");
    expect(
      within(dialog).getByText(
        "Record JDG-000413 is voided: it takes no further edit and no review, and its number is not given out again.",
      ),
    ).toBeTruthy();
    expect(state.discards).toEqual([]);
    fireEvent.click(within(dialog).getByRole("button", { name: "Discard" }));

    expect(await screen.findByText("Record JDG-000413 was discarded.")).toBeTruthy();
    // The discard takes no body. The record is read again: no draft is named any more, the
    // confirmation is closed and the path stands as it was.
    expect(state.discards).toEqual([""]);
    await waitFor(() => expect(screen.queryByTestId("SF-03-step1-draft")).toBeNull());
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect((await pathLine()).textContent).toBe(
      "No Step 1 review is recorded.Record Step 1 review",
    );
    expect((await screen.findByRole("table", { name: "Criteria" })).textContent).not.toContain(
      "JDG-000413",
    );
  });

  it("the draft's line stands without a command for a member without judgement.create for the contract's entity, and on a view of an earlier known_at", async () => {
    const reader = signedInMe({ permissions: ["contract.read", "config.read"] });
    // SCREENS §0.6 SCR-PERM-02 (a): the record is one of the contract's legal entity.
    const elsewhere = signedInMe({
      permissions: ["contract.read", "config.read", "judgement.create"],
      permission_scopes: {
        "contract.read": "*",
        "config.read": "*",
        "judgement.create": ["0a1b2c3d-4e5f-4a6b-8c7d-0000000000ff"],
      },
    });
    const views: readonly (readonly [typeof MAYA, string])[] = [
      [reader, ""],
      [elsewhere, ""],
      // No command renders on a view of an earlier known_at.
      [MAYA, "&known_at=2026-09-12T12%3A00%3A00Z"],
    ];
    for (const [me, extra] of views) {
      const state = withDiscard([LEFT_BEHIND]);
      renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}&step=1${extra}`, {
        me,
        screenRoutes: SCREEN_ROUTES,
      });
      const draft = await screen.findByTestId("SF-03-step1-draft");
      expect(draft.textContent).toBe(DRAFT_LINE);
      expect(within(draft).queryByRole("button")).toBeNull();
      expect(state.discards).toEqual([]);
      cleanup();
      server.resetHandlers();
    }
  });

  it("every draft Step 1 record is named, newest first, beside the record the path stands on", async () => {
    const older = judgement({
      id: "4f5a6b7c-8d9e-4f0a-9b1c-3d4e5f6a7b8c",
      judgement_no: "JDG-000409",
      status: "DRAFT",
      approval_request_id: null,
      created_at: "2026-09-09T09:00:00Z",
    });
    withDiscard([judgement(), LEFT_BEHIND, older]);
    open();

    // The path stands on the record that waits for its review; the criteria name it in the words
    // of a record sent for review.
    expect((await pathLine()).textContent).toBe(
      "Step 1 review JDG-000412 is waiting for review by a Revenue Reviewer.View request",
    );
    const criteria = await screen.findByRole("table", { name: "Criteria" });
    expect(
      within(criteria).getAllByText("Record JDG-000412 · Waiting for review").length,
    ).toBeGreaterThan(0);
    expect(
      (await screen.findAllByTestId("SF-03-step1-draft")).map((item) => item.textContent),
    ).toEqual([
      `${DRAFT_LINE}Discard`,
      "Record JDG-000409 is a draft that was not sent for review.Discard",
    ]);
  });

  // SCREENS §4.1.3 and §4.9.8 (rev 1.74; PRD SM-10 rev 1.199, IMP-145; 04 rev 1.296): after a
  // rejection the path writes a new record, and the rejected one fails the activation checklist until
  // it is discarded. No screen offered the discard: a contract whose Step 1 review was once rejected
  // was never activated from a screen.
  describe("a judgement record the activation checklist counts", () => {
    const REJECTED_ID = "5a6b7c8d-9e0f-4a1b-8c2d-4e5f6a7b8c9d";
    const REJECTED_REQUEST_ID = "6b7c8d9e-0f1a-4b2c-9d3e-5f6a7b8c9d0e";
    // The record as the route lists it after a rejection (measured): its request stays on the row.
    const REJECTED = judgement({
      id: REJECTED_ID,
      judgement_no: "JDG-000411",
      status: "REJECTED",
      approval_request_id: REJECTED_REQUEST_ID,
      created_at: "2026-09-09T09:00:00Z",
      updated_at: "2026-09-09T11:00:00Z",
    });
    // The three statuses the checklist's item counts, as the banner's one read asks for them.
    const UNREVIEWED_READ = [["DRAFT", "SUBMITTED", "REJECTED"]];
    // The request a submission for review makes.
    const SENT_REQUEST_ID = "0f1e2d3c-4b5a-4968-8776-655443322110";
    const REJECTED_LINE =
      "Record JDG-000411 was rejected. Discard it before the contract is submitted for activation.";
    const CONSEQUENCE =
      "Record JDG-000411 is voided: it takes no further edit and no review, and its number is not given out again.";
    const checklistLine = (number: string, topic: string) =>
      `Judgement record ${number} (${topic}) was rejected. Discard it, or have its author revise it and send it for review again.`;

    /**
     * The 409 of `submit-activation` as the route answers it for the item of the judgement records
     * (measured on the API, register index 274): one line a rejected record, the item's code as
     * `rule_id`, and a detail that counts the items.
     */
    function checklistRefusal(lines: readonly string[]): Response {
      return problemResponse("activation-checklist-failed", 409, "Contract cannot be activated", {
        code: null,
        detail: "1 checklist item has not passed: JUDGEMENT_RECORDS.",
        errors: lines.map((message) => ({
          field: null,
          message,
          row: null,
          rule_id: "JUDGEMENT_RECORDS",
          sheet: null,
        })),
      });
    }

    /**
     * The path's world with the judgement list as the route filters it (04 API-R-33: `status`,
     * `topic`, `subject_type`, `subject_id`), the searches it was asked and the discards it was sent;
     * and, for register index 287, the contract's policy overrides as `GET /policy-overrides` lists
     * them for its `contract`, and the submissions for review it was sent.
     */
    function withRejected(
      records: readonly Record<string, unknown>[],
      events: readonly Record<string, unknown>[] = [],
      refuse: (sent: Sent) => Response | null = () => null,
      status: "DRAFT" | "NOT_A_CONTRACT" = "DRAFT",
    ) {
      const sent = world(status, [], events, refuse);
      const state = {
        records: [...records],
        discards: [] as string[],
        /** The statuses each read of the list asked for; none for a read that filters no status. */
        statusReads: [] as string[][],
        /** The contract's overrides; a response answers the read in their place. */
        overrides: [] as readonly Record<string, unknown>[] | Response,
        /** The contract each read of the overrides asked for. */
        overrideReads: [] as (string | null)[],
        /** The submissions for review: the record's id and the body. */
        sends: [] as string[],
        /** Answers a submission for review in the route's place. */
        refuseSend: null as (() => Response) | null,
      };
      server.use(
        http.get(apiUrl("/api/v1/policy-overrides"), ({ request }) => {
          const asked = new URL(request.url).searchParams.get("contract");
          state.overrideReads.push(asked);
          return state.overrides instanceof Response
            ? state.overrides.clone()
            : HttpResponse.json({
                items: state.overrides.filter((item) => item.contract_id === asked),
                next_cursor: null,
              });
        }),
        // The route sends a draft for review and names its request (measured on the API).
        http.post(apiUrl("/api/v1/judgements/:id/submit"), async ({ request, params }) => {
          state.sends.push(`${String(params.id)}:${await request.text()}`);
          if (state.refuseSend !== null) {
            return state.refuseSend();
          }
          state.records = state.records.map((item) =>
            item.id === params.id
              ? { ...item, status: "SUBMITTED", approval_request_id: SENT_REQUEST_ID }
              : item,
          );
          return HttpResponse.json(state.records.find((item) => item.id === params.id));
        }),
        http.get(apiUrl("/api/v1/judgements"), ({ request }) => {
          const asked = new URL(request.url).searchParams;
          state.statusReads.push(asked.getAll("status"));
          const kept = (name: string, value: unknown) =>
            asked.getAll(name).length === 0 || asked.getAll(name).includes(String(value));
          return HttpResponse.json({
            items: state.records.filter(
              (item) =>
                kept("status", item.status) &&
                kept("topic", item.topic) &&
                kept("subject_type", item.subject_type) &&
                kept("subject_id", item.subject_id),
            ),
            next_cursor: null,
          });
        }),
        http.post(apiUrl("/api/v1/judgements/:id/discard"), async ({ request, params }) => {
          state.discards.push(`${String(params.id)}:${await request.text()}`);
          state.records = state.records.map((item) =>
            item.id === params.id ? { ...item, status: "VOIDED" } : item,
          );
          return HttpResponse.json(state.records.find((item) => item.id === params.id));
        }),
      );
      return { sent, state };
    }

    it("a rejected Step 1 record is named beside the path with Discard, and the discard takes it off the contract's records", async () => {
      const { state } = withRejected([REJECTED]);
      open();

      // The path says what comes next; the record's own line says what the record still holds.
      expect((await pathLine()).textContent).toBe(
        "Step 1 review JDG-000411 was rejected. Record a new review.Record Step 1 review",
      );
      const line = await screen.findByTestId("SF-03-step1-rejected");
      // Rev 1.76: the line links the record's request, where the reviewer's reason stands.
      expect(line.textContent).toBe(`${REJECTED_LINE}View requestDiscard`);
      expect(within(line).getByRole("link", { name: "View request" }).getAttribute("href")).toBe(
        `/approvals/requests/${REJECTED_REQUEST_ID}`,
      );

      fireEvent.click(within(line).getByRole("button", { name: "Discard" }));
      const dialog = await screen.findByRole("alertdialog", {
        name: "Discard this rejected record?",
      });
      expect(dialog.getAttribute("data-testid")).toBe("SF-03-dialog-discard-record");
      expect(within(dialog).getByText(CONSEQUENCE)).toBeTruthy();
      expect(state.discards).toEqual([]);
      fireEvent.click(within(dialog).getByRole("button", { name: "Discard" }));

      expect(await screen.findByText("Record JDG-000411 was discarded.")).toBeTruthy();
      // The discard takes no body. The records are read again: the line is gone, the confirmation
      // is closed and the path stands on no record.
      expect(state.discards).toEqual([`${REJECTED_ID}:`]);
      await waitFor(() => expect(screen.queryByTestId("SF-03-step1-rejected")).toBeNull());
      await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
      expect((await pathLine()).textContent).toBe(
        "No Step 1 review is recorded.Record Step 1 review",
      );
      // The workspace's rejected records are not read while no refusal names one.
      expect(state.statusReads.filter((asked) => asked.length > 0)).toEqual([]);
    });

    it("every rejected Step 1 record is named among the drafts, newest first, also behind the record the path stands on", async () => {
      // A rejected record of another topic is none of step 1's, though its subject is the
      // contract: it has its command on the checklist's line (§4.9.8).
      const override = judgement({
        id: "8d9e0f1a-2b3c-4d4e-9f5a-7b8c9d0e1f2a",
        judgement_no: "JDG-000405",
        topic: "OTHER",
        status: "REJECTED",
        created_at: "2026-09-08T09:00:00Z",
      });
      withRejected([judgement(), LEFT_BEHIND, REJECTED, override]);
      open();

      expect((await pathLine()).textContent).toBe(
        "Step 1 review JDG-000412 is waiting for review by a Revenue Reviewer.View request",
      );
      const lines = await screen.findAllByTestId(/^SF-03-step1-(draft|rejected)$/);
      expect(lines.map((item) => item.textContent)).toEqual([
        `${DRAFT_LINE}Discard`,
        `${REJECTED_LINE}View requestDiscard`,
      ]);
    });

    it("where no activation waits for the record its line says only that it was rejected", async () => {
      // Behind the not-a-contract gate the activation waits for the record as it does on a draft.
      withRejected([REJECTED], [], () => null, "NOT_A_CONTRACT");
      open();
      expect((await screen.findByTestId("SF-03-step1-rejected")).textContent).toBe(
        `${REJECTED_LINE}View requestDiscard`,
      );
      cleanup();
      server.resetHandlers();

      withRejected([REJECTED]);
      server.use(
        http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}`), () =>
          HttpResponse.json(contract({ status: "ACTIVE" })),
        ),
      );
      open();

      const line = await screen.findByTestId("SF-03-step1-rejected");
      expect(line.textContent).toBe("Record JDG-000411 was rejected.View requestDiscard");
    });

    it("the rejected record's line stands without a command for a member without judgement.create, and on a view of an earlier known_at", async () => {
      const reader = signedInMe({ permissions: ["contract.read", "config.read"] });
      const views: readonly (readonly [typeof MAYA, string])[] = [
        [reader, ""],
        [MAYA, "&known_at=2026-09-12T12%3A00%3A00Z"],
      ];
      for (const [me, extra] of views) {
        const { state } = withRejected([REJECTED]);
        renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}&step=1${extra}`, {
          me,
          screenRoutes: SCREEN_ROUTES,
        });
        const line = await screen.findByTestId("SF-03-step1-rejected");
        // Both are the record's preparer: the request is theirs to open, and opening it commands
        // nothing.
        expect(line.textContent).toBe(`${REJECTED_LINE}View request`);
        expect(within(line).queryByRole("button")).toBeNull();
        expect(state.discards).toEqual([]);
        cleanup();
        server.resetHandlers();
      }
    });

    // The journey the API lane measured: the first review rejected, a new one reviewed and assessed,
    // and the activation refused for the rejected record.
    it("a refused activation names the rejected record, and its line carries Discard: the discard is sent and the line says so", async () => {
      const line411 = checklistLine("JDG-000411", "Collectibility");
      const { sent, state } = withRejected(
        [REVIEWED, REJECTED],
        [
          assessed("ASC606", REVIEW_ID, true, "2026-01-01", 1),
          assessed("IFRS15", REVIEW_ID, true, "2026-01-01", 2),
        ],
        (item) => (item.path.endsWith("/submit-activation") ? checklistRefusal([line411]) : null),
      );
      open();

      const path = await pathLine();
      expect(state.statusReads.filter((asked) => asked.length > 0)).toEqual([]);
      fireEvent.click(within(path).getByRole("button", { name: "Submit for activation" }));

      const banner = await screen.findByTestId("SF-03-banner-header");
      expect(
        within(banner).getByRole("heading", { name: "Contract cannot be activated" }),
      ).toBeTruthy();
      const [line] = within(banner).getAllByRole("listitem");
      if (line === undefined) {
        throw new Error("The banner lists no line");
      }
      await within(line).findByRole("button", { name: "Discard" });
      // Rev 1.76: the request first, where the reviewer's reason stands, then the command.
      expect(line.textContent).toBe(`${line411}View requestDiscard`);
      expect(within(line).getByRole("link", { name: "View request" }).getAttribute("href")).toBe(
        `/approvals/requests/${REJECTED_REQUEST_ID}`,
      );
      // One read of the workspace's records the item counts, made once the refusal named the item.
      expect(state.statusReads.filter((asked) => asked.length > 0)).toEqual(UNREVIEWED_READ);

      fireEvent.click(within(line).getByRole("button", { name: "Discard" }));
      const dialog = await screen.findByRole("alertdialog", {
        name: "Discard this rejected record?",
      });
      expect(within(dialog).getByText(CONSEQUENCE)).toBeTruthy();
      fireEvent.click(within(dialog).getByRole("button", { name: "Discard" }));

      // The banner stays as the API answered it; the line says what happened in the command's place.
      await waitFor(() =>
        expect(line.textContent).toBe(`${line411}Record JDG-000411 was discarded.`),
      );
      expect(within(banner).queryByRole("button", { name: "Discard" })).toBeNull();
      expect(state.discards).toEqual([`${REJECTED_ID}:`]);
      expect(sent.map((item) => `${item.method} ${item.path}`)).toEqual([
        `POST /api/v1/contracts/${CONTRACT_ID}/submit-activation`,
      ]);
      // The record's line beside the path is gone with it.
      await waitFor(() => expect(screen.queryByTestId("SF-03-step1-rejected")).toBeNull());
    });

    it("the checklist's line carries Discard for a rejected record of any subject, and none for a record of another contract or for a line without a number", async () => {
      // A distinct review of an obligation: no line of step 1 names it. Its topic's title is the
      // API's (`finding_title`, read in the code).
      const distinctId = "7c8d9e0f-1a2b-4c3d-8e4f-6a7b8c9d0e1f";
      const distinct = judgement({
        id: distinctId,
        judgement_no: "JDG-000409",
        topic: "POB_DISTINCT_OVERRIDE",
        subject_type: "obligation",
        subject_id: O2_ID,
        status: "REJECTED",
      });
      // A rejected record of another contract: the workspace's read answers it, and a line that
      // held its number would not make it this contract's.
      const otherContract = "0b1c2d3e-4f5a-4b6c-8d7e-9f0a1b2c3d4e";
      const elsewhere = judgement({
        id: "9e0f1a2b-3c4d-4e5f-8a6b-8c9d0e1f2a3b",
        judgement_no: "JDG-000377",
        status: "REJECTED",
        subject_id: otherContract,
        contract_id: otherContract,
      });
      const lines = [
        checklistLine("JDG-000409", "POB distinct override"),
        checklistLine("JDG-000377", "Collectibility"),
        "Judgement record required: Constraint.",
      ];
      const { state } = withRejected([REVIEWED, distinct, elsewhere], [], (item) =>
        item.path.endsWith("/submit-activation") ? checklistRefusal(lines) : null,
      );
      open();

      await pathLine();
      expect(screen.queryByTestId("SF-03-step1-rejected")).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: "Submit for activation" }));

      const banner = await screen.findByTestId("SF-03-banner-header");
      await within(banner).findByRole("button", { name: "Discard" });
      expect(
        within(banner)
          .getAllByRole("listitem")
          .map((item) => item.textContent),
      ).toEqual([`${lines[0] ?? ""}View requestDiscard`, lines[1], lines[2]]);

      fireEvent.click(within(banner).getByRole("button", { name: "Discard" }));
      const dialog = await screen.findByRole("alertdialog", {
        name: "Discard this rejected record?",
      });
      fireEvent.click(within(dialog).getByRole("button", { name: "Discard" }));
      await waitFor(() => expect(state.discards).toEqual([`${distinctId}:`]));
    });

    it("a refused activation that names no judgement record reads none of the workspace's rejected records", async () => {
      const { state } = withRejected([REVIEWED, REJECTED], [], (item) =>
        item.path.endsWith("/submit-activation")
          ? problemResponse("activation-checklist-failed", 409, "Contract cannot be activated", {
              code: null,
              detail: "1 checklist item has not passed: SOURCE_REFERENCE.",
              errors: [
                {
                  field: null,
                  message: "No contract reference is recorded.",
                  row: null,
                  rule_id: "SOURCE_REFERENCE",
                  sheet: null,
                },
              ],
            })
          : null,
      );
      open();

      await pathLine();
      fireEvent.click(screen.getByRole("button", { name: "Submit for activation" }));
      const banner = await screen.findByTestId("SF-03-banner-header");
      expect(
        within(banner)
          .getAllByRole("listitem")
          .map((item) => item.textContent),
      ).toEqual(["No contract reference is recorded.Open documents"]);
      // The pause gives a read that must not be made the time to be made.
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(state.statusReads.filter((asked) => asked.length > 0)).toEqual([]);
      // Rev 1.76: nor are the contract's overrides, which only the records' entries ask for.
      expect(state.overrideReads).toEqual([]);
    });

    it("the checklist's line of a rejected record stands without a command for a member without judgement.create", async () => {
      const line411 = checklistLine("JDG-000411", "Collectibility");
      const { state } = withRejected([REVIEWED, REJECTED], [], (item) =>
        item.path.endsWith("/submit-activation") ? checklistRefusal([line411]) : null,
      );
      renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}&step=1`, {
        me: signedInMe({ permissions: ["contract.read", "contract.create", "config.read"] }),
        screenRoutes: SCREEN_ROUTES,
      });

      fireEvent.click(await screen.findByRole("button", { name: "Submit for activation" }));
      const banner = await screen.findByTestId("SF-03-banner-header");
      await waitFor(() =>
        expect(state.statusReads.filter((asked) => asked.length > 0)).toEqual(UNREVIEWED_READ),
      );
      // The member is the record's preparer: the request is theirs to open, the discard is not.
      await within(banner).findByRole("link", { name: "View request" });
      expect(
        within(banner)
          .getAllByRole("listitem")
          .map((item) => item.textContent),
      ).toEqual([`${line411}View request`]);
      expect(within(banner).queryByRole("button", { name: "Discard" })).toBeNull();
    });

    // --- Register index 287: the records under "Judgement record required" (SCREENS §4.9.8 rev 1.76).

    // The record of a policy override as the drawer left it before rev 1.76 (measured on the API): a
    // draft of topic OTHER whose subject is the contract, never sent, so it names no request.
    const OVERRIDE_DRAFT_ID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d";
    const OVERRIDE_DRAFT = judgement({
      id: OVERRIDE_DRAFT_ID,
      judgement_no: "JDG-000405",
      topic: "OTHER",
      conclusion: "The entity is an agent for the hosting it resells.",
      status: "DRAFT",
      approval_request_id: null,
      content_sha256: null,
      created_at: "2026-09-08T09:00:00Z",
      updated_at: "2026-09-08T09:00:00Z",
    });
    // A draft its creator revised after a rejection: the API returns it to DRAFT and leaves the
    // rejected request on the row (read in `update_judgement`).
    const REVISED_REQUEST_ID = "c3d4e5f6-a7b8-4c9d-8e0f-2a3b4c5d6e7f";
    const REVISED_DRAFT = judgement({
      id: "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6f",
      judgement_no: "JDG-000407",
      topic: "OTHER",
      conclusion: "The licence is a right to use.",
      status: "DRAFT",
      approval_request_id: REVISED_REQUEST_ID,
      created_at: "2026-09-08T11:00:00Z",
      updated_at: "2026-09-08T11:00:00Z",
    });
    const PENDING_REQUEST_ID = "d4e5f6a7-b8c9-4d0e-9f1a-3b4c5d6e7f8a";
    const PENDING = judgement({
      id: "e5f6a7b8-c9d0-4e1f-8a2b-4c5d6e7f8a9b",
      judgement_no: "JDG-000406",
      topic: "OTHER",
      conclusion: "The warranty is a service.",
      status: "SUBMITTED",
      approval_request_id: PENDING_REQUEST_ID,
      created_at: "2026-09-08T10:00:00Z",
      updated_at: "2026-09-08T10:00:00Z",
    });
    const REVISED_DRAFT_ID = String(REVISED_DRAFT.id);
    const REQUIRED_OTHER = "Judgement record required: Other.";
    // SCREENS RT of SF-12:request, the screen a record's request opens on.
    const REQUEST_PATH = "/approvals/requests/:requestId";
    const LISTED = "Judgement records that are not reviewed";

    /**
     * A policy override as `GET /policy-overrides` lists it (04 API-S-PolicyOverride; measured on the
     * API, register index 287): its E-12 status and the judgement record it names.
     */
    function override(
      status: string,
      recordId: string,
      contractId: string = CONTRACT_ID,
    ): Record<string, unknown> {
      return {
        id: `0d0d0d0d-0000-4000-8000-${recordId.slice(-12)}`,
        contract_id: contractId,
        obligation_id: O1_ID,
        obligation_key: "O1",
        level: "OBLIGATION",
        policy_key: "pob.principal_or_agent",
        value: "AGENT",
        rationale: "The supplier sets the price and carries the service risk.",
        judgement_record_id: recordId,
        status,
        content_sha256: null,
        approval_request_id: null,
        approved_at: null,
        supersedes_id: null,
        created_at: "2026-09-08T09:01:00Z",
        updated_at: "2026-09-08T09:01:00Z",
        row_version: 1,
      };
    }

    /** The records the banner lists under the line, as the texts of their entries. */
    async function listed(banner: HTMLElement): Promise<(string | null)[]> {
      const list = await within(banner).findByRole("list", { name: LISTED });
      return within(list)
        .getAllByRole("listitem")
        .map((item) => item.textContent);
    }

    /** The lines of the banner's own list, without the entries of a list under one of them. */
    function bannerLines(banner: HTMLElement): HTMLElement[] {
      const [list] = within(banner).getAllByRole("list");
      if (list === undefined) {
        throw new Error("The banner has no list");
      }
      return Array.from(list.children) as HTMLElement[];
    }

    it("a refused activation that waits for a draft and a pending record lists them under its line by number: Discard on a draft, View request on a pending one", async () => {
      const otherContract = "0b1c2d3e-4f5a-4b6c-8d7e-9f0a1b2c3d4e";
      // A draft of another contract: the workspace's read answers it, and it is none of this one's.
      const elsewhere = judgement({
        id: "f6a7b8c9-d0e1-4f2a-9b3c-5d6e7f8a9b0c",
        judgement_no: "JDG-000401",
        topic: "OTHER",
        status: "DRAFT",
        approval_request_id: null,
        subject_id: otherContract,
        contract_id: otherContract,
      });
      const { sent, state } = withRejected(
        [REVIEWED, REVISED_DRAFT, PENDING, OVERRIDE_DRAFT, elsewhere],
        [
          assessed("ASC606", REVIEW_ID, true, "2026-01-01", 1),
          assessed("IFRS15", REVIEW_ID, true, "2026-01-01", 2),
        ],
        (item) =>
          item.path.endsWith("/submit-activation") ? checklistRefusal([REQUIRED_OTHER]) : null,
      );
      // No override in force or waiting for approval names a draft: one was rejected, one withdrawn,
      // and the approved override that names the same id is another contract's, which the route
      // does not list for this one. The records are free, and "Discard" is theirs.
      state.overrides = [
        override("REJECTED", OVERRIDE_DRAFT_ID),
        override("WITHDRAWN", REVISED_DRAFT_ID),
        override("APPROVED", OVERRIDE_DRAFT_ID, otherContract),
      ];
      open();

      fireEvent.click(
        within(await pathLine()).getByRole("button", { name: "Submit for activation" }),
      );
      const banner = await screen.findByTestId("SF-03-banner-header");
      const list = await within(banner).findByRole("list", { name: LISTED });
      await within(list).findAllByRole("button", { name: "Discard" });
      // Number, conclusion and the status in the words of the screens, in number order. A record
      // that names a request links it — the pending one, and the draft that still carries the
      // request of an earlier rejection; the draft that was never sent names none.
      expect(await listed(banner)).toEqual([
        "JDG-000405The entity is an agent for the hosting it resells.DraftDiscard",
        "JDG-000406The warranty is a service.Waiting for reviewView request",
        "JDG-000407The licence is a right to use.DraftView requestDiscard",
      ]);
      expect(
        within(list)
          .getAllByRole("link", { name: "View request" })
          .map((link) => link.getAttribute("href")),
      ).toEqual([
        `/approvals/requests/${PENDING_REQUEST_ID}`,
        `/approvals/requests/${REVISED_REQUEST_ID}`,
      ]);
      // The list stands under the API's line, which stays as it was answered.
      const [line] = bannerLines(banner);
      expect(line?.firstElementChild?.textContent).toBe(REQUIRED_OTHER);
      expect(line?.contains(list)).toBe(true);
      // One read of the records and one of the contract's overrides, once the refusal named the item.
      expect(state.statusReads.filter((asked) => asked.length > 0)).toEqual(UNREVIEWED_READ);
      expect(state.overrideReads).toEqual([CONTRACT_ID]);

      const [first] = within(list).getAllByRole("listitem");
      if (first === undefined) {
        throw new Error("The list names no record");
      }
      fireEvent.click(within(first).getByRole("button", { name: "Discard" }));
      const dialog = await screen.findByRole("alertdialog", { name: "Discard this draft record?" });
      fireEvent.click(within(dialog).getByRole("button", { name: "Discard" }));

      // The discarded draft stays in the list and says so; the others stand as they were.
      await waitFor(async () =>
        expect(await listed(banner)).toEqual([
          "Record JDG-000405 was discarded.",
          "JDG-000406The warranty is a service.Waiting for reviewView request",
          "JDG-000407The licence is a right to use.DraftView requestDiscard",
        ]),
      );
      expect(state.discards).toEqual([`${OVERRIDE_DRAFT_ID}:`]);
      expect(state.sends).toEqual([]);
      expect(sent.map((item) => `${item.method} ${item.path}`)).toEqual([
        `POST /api/v1/contracts/${CONTRACT_ID}/submit-activation`,
      ]);
    });

    it("a draft that an override in force or waiting for approval names is sent for review in the place of Discard, and then waits for its reviewer", async () => {
      const { state } = withRejected(
        [REVIEWED, REVISED_DRAFT, PENDING, OVERRIDE_DRAFT],
        [],
        (item) =>
          item.path.endsWith("/submit-activation") ? checklistRefusal([REQUIRED_OTHER]) : null,
      );
      // The state the drawer left before rev 1.76 (measured on the API): the override was approved
      // over a record that was never sent. Discarded, the record could never be reviewed and the
      // override would keep naming it.
      state.overrides = [
        override("APPROVED", OVERRIDE_DRAFT_ID),
        override("SUBMITTED", REVISED_DRAFT_ID),
      ];
      open();

      await pathLine();
      fireEvent.click(screen.getByRole("button", { name: "Submit for activation" }));
      const banner = await screen.findByTestId("SF-03-banner-header");
      await within(banner).findAllByRole("button", { name: "Send for review" });
      expect(await listed(banner)).toEqual([
        "JDG-000405The entity is an agent for the hosting it resells.DraftSend for review",
        "JDG-000406The warranty is a service.Waiting for reviewView request",
        "JDG-000407The licence is a right to use.DraftView requestSend for review",
      ]);
      expect(within(banner).queryByRole("button", { name: "Discard" })).toBeNull();

      const [send] = within(banner).getAllByRole("button", { name: "Send for review" });
      if (send === undefined) {
        throw new Error("No record is offered Send for review");
      }
      fireEvent.click(send);
      expect(
        await screen.findByText("Judgement record JDG-000405 was submitted for review."),
      ).toBeTruthy();
      // The request the override's drawer sent for a new record (withdrawn, rev 1.80), with its body.
      expect(state.sends).toEqual([`${OVERRIDE_DRAFT_ID}:{"comment":null}`]);
      // The records are read again: the record waits for its reviewer, and its request is linked.
      await waitFor(async () =>
        expect(await listed(banner)).toEqual([
          "JDG-000405The entity is an agent for the hosting it resells.Waiting for reviewView request",
          "JDG-000406The warranty is a service.Waiting for reviewView request",
          "JDG-000407The licence is a right to use.DraftView requestSend for review",
        ]),
      );
      expect(state.discards).toEqual([]);
    });

    it("a refused submission for review is shown under the record's line, and the record stays a draft", async () => {
      // The route's answer to a record that is no draft any more (measured on the API).
      const notSubmittable = "Only a draft judgement record can be submitted.";
      const { state } = withRejected([REVIEWED, OVERRIDE_DRAFT], [], (item) =>
        item.path.endsWith("/submit-activation") ? checklistRefusal([REQUIRED_OTHER]) : null,
      );
      state.overrides = [override("APPROVED", OVERRIDE_DRAFT_ID)];
      state.refuseSend = () =>
        problemResponse("invalid-transition", 409, "Action not available in this state", {
          code: null,
          detail: notSubmittable,
          errors: [
            { field: "status", message: notSubmittable, row: null, rule_id: "DB-03", sheet: null },
          ],
        });
      open();

      await pathLine();
      fireEvent.click(screen.getByRole("button", { name: "Submit for activation" }));
      const banner = await screen.findByTestId("SF-03-banner-header");
      fireEvent.click(await within(banner).findByRole("button", { name: "Send for review" }));

      const list = await within(banner).findByRole("list", { name: LISTED });
      const refusal = await within(list).findByRole("alert");
      expect(within(refusal).getByText(notSubmittable)).toBeTruthy();
      expect(within(list).getByRole("button", { name: "Send for review" })).toBeTruthy();
      expect(state.sends).toEqual([`${OVERRIDE_DRAFT_ID}:{"comment":null}`]);
      expect(screen.queryByText(/was submitted for review/)).toBeNull();
    });

    it("until the contract's overrides are read a draft takes no command: a read that is refused answers nothing about the record", async () => {
      const { state } = withRejected([REVIEWED, PENDING, OVERRIDE_DRAFT], [], (item) =>
        item.path.endsWith("/submit-activation") ? checklistRefusal([REQUIRED_OTHER]) : null,
      );
      // The list of the overrides is read with `config.read`: a member without it is answered 403.
      state.overrides = problemResponse("forbidden", 403, "You do not have access to this");
      open();

      await pathLine();
      fireEvent.click(screen.getByRole("button", { name: "Submit for activation" }));
      const banner = await screen.findByTestId("SF-03-banner-header");
      await waitFor(() => expect(state.overrideReads).toContain(CONTRACT_ID));
      expect(await listed(banner)).toEqual([
        "JDG-000405The entity is an agent for the hosting it resells.Draft",
        "JDG-000406The warranty is a service.Waiting for reviewView request",
      ]);
      // The pause gives a command that must not render the time to render.
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(within(banner).queryByRole("button", { name: "Discard" })).toBeNull();
      expect(within(banner).queryByRole("button", { name: "Send for review" })).toBeNull();
    });

    it("the records stand under the item's last line that names no record, once for the item, and a rejected record keeps its own line", async () => {
      const line411 = checklistLine("JDG-000411", "Collectibility");
      const lines = ["Judgement record required: Collectibility.", REQUIRED_OTHER, line411];
      withRejected([REVIEWED, LEFT_BEHIND, OVERRIDE_DRAFT, REJECTED], [], (item) =>
        item.path.endsWith("/submit-activation") ? checklistRefusal(lines) : null,
      );
      open();

      await pathLine();
      fireEvent.click(screen.getByRole("button", { name: "Submit for activation" }));
      const banner = await screen.findByTestId("SF-03-banner-header");
      await within(banner).findByRole("list", { name: LISTED });
      const under =
        `${REQUIRED_OTHER}` +
        "JDG-000405The entity is an agent for the hosting it resells.DraftDiscard" +
        "JDG-000413Collectibility is probable.DraftDiscard";
      await waitFor(() =>
        expect(bannerLines(banner).map((item) => item.textContent)).toEqual([
          lines[0],
          under,
          `${line411}View requestDiscard`,
        ]),
      );
      expect(within(banner).getAllByRole("list", { name: LISTED })).toHaveLength(1);

      // The rejected record is discarded from its line: the line says so, and the list stays where it
      // stood — a line whose record was discarded here is not taken for the line of a topic.
      const rejectedLine = bannerLines(banner)[2];
      if (rejectedLine === undefined) {
        throw new Error("The banner has no third line");
      }
      fireEvent.click(within(rejectedLine).getByRole("button", { name: "Discard" }));
      const dialog = await screen.findByRole("alertdialog", {
        name: "Discard this rejected record?",
      });
      fireEvent.click(within(dialog).getByRole("button", { name: "Discard" }));
      await waitFor(() =>
        expect(bannerLines(banner).map((item) => item.textContent)).toEqual([
          lines[0],
          under,
          `${line411}Record JDG-000411 was discarded.`,
        ]),
      );
    });

    it("a member without judgement.create reads the records under the line, and neither Discard nor Send for review", async () => {
      const { state } = withRejected(
        [REVIEWED, REVISED_DRAFT, PENDING, OVERRIDE_DRAFT],
        [],
        (item) =>
          item.path.endsWith("/submit-activation") ? checklistRefusal([REQUIRED_OTHER]) : null,
      );
      state.overrides = [override("APPROVED", REVISED_DRAFT_ID)];
      renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}&step=1`, {
        me: signedInMe({ permissions: ["contract.read", "contract.create", "config.read"] }),
        screenRoutes: SCREEN_ROUTES,
      });

      fireEvent.click(await screen.findByRole("button", { name: "Submit for activation" }));
      const banner = await screen.findByTestId("SF-03-banner-header");
      await waitFor(() => expect(state.overrideReads).toContain(CONTRACT_ID));
      // The member prepared the records: the pending one's request is theirs to open.
      expect(await listed(banner)).toEqual([
        "JDG-000405The entity is an agent for the hosting it resells.Draft",
        "JDG-000406The warranty is a service.Waiting for reviewView request",
        "JDG-000407The licence is a right to use.DraftView request",
      ]);
      // The pause gives a command that must not render the time to render.
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(within(banner).queryByRole("button")).toBeNull();
      expect(state.discards).toEqual([]);
      expect(state.sends).toEqual([]);
    });

    it("View request stands for the record's preparer and for a holder of judgement.review for the contract's entity, and for nobody else", async () => {
      // Another member prepared the records: the viewer below is nobody's preparer.
      const byPriya = (record: Record<string, unknown>) => ({ ...record, created_by: PRIYA_ACTOR });
      const line411 = checklistLine("JDG-000411", "Collectibility");
      const reads = ["contract.read", "contract.create", "config.read"];
      const reviewerFor = (entityId: string) =>
        signedInMe({
          permissions: [...reads, "judgement.review"],
          permission_scopes: {
            ...Object.fromEntries(reads.map((code): [string, "*"] => [code, "*"])),
            "judgement.review": [entityId],
          },
        });
      // Where the request screen is not built there is nowhere to go, whoever asks.
      const unbuilt = SCREEN_ROUTES.filter((route) => route.path !== REQUEST_PATH);
      const views: readonly (readonly [typeof MAYA, boolean, typeof SCREEN_ROUTES])[] = [
        [signedInMe({ permissions: reads }), false, SCREEN_ROUTES],
        [reviewerFor(US_ID), true, SCREEN_ROUTES],
        [reviewerFor("0a1b2c3d-4e5f-4a6b-8c7d-0000000000ff"), false, SCREEN_ROUTES],
        [reviewerFor(US_ID), false, unbuilt],
      ];
      for (const [me, linked, screenRoutes] of views) {
        withRejected([REVIEWED, byPriya(PENDING), byPriya(REJECTED)], [], (item) =>
          item.path.endsWith("/submit-activation")
            ? checklistRefusal([REQUIRED_OTHER, line411])
            : null,
        );
        renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}&step=1`, {
          me,
          screenRoutes,
        });

        fireEvent.click(await screen.findByRole("button", { name: "Submit for activation" }));
        const banner = await screen.findByTestId("SF-03-banner-header");
        const list = await within(banner).findByRole("list", { name: LISTED });
        const link = linked ? "View request" : "";
        await waitFor(() =>
          expect(bannerLines(banner).map((item) => item.textContent)).toEqual([
            `${REQUIRED_OTHER}JDG-000406The warranty is a service.Waiting for review${link}`,
            `${line411}${link}`,
          ]),
        );
        expect(list.textContent).toBe(
          `JDG-000406The warranty is a service.Waiting for review${link}`,
        );
        // The rejected record's line in step 1 follows the same rule.
        expect((await screen.findByTestId("SF-03-step1-rejected")).textContent).toBe(
          `${REJECTED_LINE}${link}`,
        );
        cleanup();
        server.resetHandlers();
      }
    });
  });

  it("a record that waits for review says who acts next, links the request and offers no Step 1 command", async () => {
    world("DRAFT", [judgement()], []);
    open();

    const line = await pathLine();
    expect(line.textContent).toBe(
      "Step 1 review JDG-000412 is waiting for review by a Revenue Reviewer.View request",
    );
    expect(within(line).getByRole("link", { name: "View request" }).getAttribute("href")).toBe(
      `/approvals/requests/${REQUEST_ID}`,
    );
    expect(within(line).queryByRole("button")).toBeNull();
    expect(screen.getByTestId("SF-03-tracker-step-1").getAttribute("aria-label")).toBe(
      "Step 1, Contract, in review, Review JDG-000412 waiting for review",
    );
    expect(await overflow()).toEqual(["Combine with another contract", "Copy link"]);
  });

  it("a reviewed record on a draft: Record assessment cites it for every enabled book at the inception date", async () => {
    const sent = world("DRAFT", [REVIEWED], []);
    open();

    const line = await pathLine();
    expect(line.textContent).toBe(
      "Step 1 review JDG-000412 was reviewed by Priya Raman on 10 Sep 2026 16:20 UTC. Record the assessment to continue.Record assessment",
    );
    // A new review stays beside the assessment (rev 1.72): the API may refuse the reviewed record.
    expect(await overflow()).toEqual([
      "Record assessment",
      "Record Step 1 review",
      "Combine with another contract",
      "Copy link",
    ]);

    fireEvent.click(within(line).getByRole("button", { name: "Record assessment" }));
    const drawer = await screen.findByRole("dialog", { name: "Record assessment" });
    const facts = within(drawer)
      .getAllByRole("definition")
      .map((item) => item.textContent);
    expect(facts).toEqual([
      "JDG-000412 · Reviewed by Priya Raman, 10 Sep 2026 16:20 UTC",
      "Collectibility is probable.",
      "Collectibility probable",
      "ASC 606 and IFRS 15",
      "01 Jan 2026, the inception date",
    ]);
    // A draft's assessment is dated its inception date: no date field.
    expect(within(drawer).queryByRole("textbox")).toBeNull();
    fireEvent.click(within(drawer).getByRole("button", { name: "Record assessment" }));

    expect(await screen.findByText("Assessment recorded.")).toBeTruthy();
    expect(sent).toHaveLength(1);
    expect(sent[0]?.path).toBe(`/api/v1/contracts/${CONTRACT_ID}/events`);
    expect(sent[0]?.ifMatch).toBe('"s6"');
    expect(sent[0]?.body).toEqual({
      events: ["ASC606", "IFRS15"].map((book) => ({
        event_type: "COLLECTIBILITY_ASSESSED",
        effective_date: "2026-01-01",
        payload: {
          book,
          is_probable: true,
          credit_grade: "B",
          mitigation: "ADVANCE_PAYMENT",
          judgement_record_id: REVIEW_ID,
        },
      })),
      evidence_file_ids: [],
    });
  });

  // SCREENS §4.1.3 (rev 1.72; supervisor ruling R-102 (c); 04 §16.1 rev 1.150): `replace-draft` voids
  // the assessments of the draft it replaces, and the events route lists a voided assessment like any
  // other. Read by its type alone it kept the path at its last row — "The assessment of 01 Jan 2026
  // cites Step 1 review JDG-000412. Submit the contract for activation." — while the activation
  // checklist answered "Step 1 review not recorded."
  it("a replaced draft: the voided assessments count for nothing and the path is back at its reviewed record", async () => {
    const first = assessed("ASC606", REVIEW_ID, true, "2026-01-01", 1);
    const second = assessed("IFRS15", REVIEW_ID, true, "2026-01-01", 2);
    world("DRAFT", [REVIEWED], [first, second, voided(first, 3), voided(second, 4)]);
    open();

    const line = await pathLine();
    expect(line.textContent).toBe(
      "Step 1 review JDG-000412 was reviewed by Priya Raman on 10 Sep 2026 16:20 UTC. Record the assessment to continue.Record assessment",
    );
    expect(screen.getByTestId("SF-03-tracker-step-1").getAttribute("aria-label")).toBe(
      "Step 1, Contract, needs attention, Review JDG-000412 reviewed: record the assessment",
    );
    // The voids are read with the assessments, in one read of the route.
    expect(eventReads).toEqual([["COLLECTIBILITY_ASSESSED", "EVENT_VOIDED"]]);
  });

  it("one book's assessment voided and the other's standing: the path still waits for the assessment", async () => {
    const first = assessed("ASC606", REVIEW_ID, true, "2026-01-01", 1);
    const second = assessed("IFRS15", REVIEW_ID, true, "2026-01-01", 2);
    world("DRAFT", [REVIEWED], [first, second, voided(second, 3)]);
    open();

    expect((await pathLine()).textContent).toContain("Record the assessment to continue.");
    cleanup();

    // The control: with no void both stand, and the path is at its last row.
    world("DRAFT", [REVIEWED], [first, second]);
    open();
    expect((await pathLine()).textContent).toBe(
      "The assessment of 01 Jan 2026 cites Step 1 review JDG-000412. Submit the contract for activation.Submit for activation",
    );
  });

  // SCREENS §4.1.3, §4.9.1 (rev 1.72; the supervisor's ruling of 2026-10-02 on P4, way 1): the API takes
  // an assessment only on a record reviewed at or after the time the latest standing booking was
  // written, a time no read answers. The screen compares nothing: it says the API's sentence and
  // offers a new review. Before, the path, the overflow and the fix link each opened the assessment
  // of the record the API refuses, and no screen offered a new review.
  describe("a reviewed record that the API refuses", () => {
    const OLDER = "Use a judgement record reviewed after the draft was last replaced.";
    const OFFER = "Record a new Step 1 review";

    /** The contracting entity keeps one enabled book: the assessment is one event, as measured. */
    function oneBook(): void {
      server.use(
        http.get(apiUrl("/api/v1/entities"), () =>
          HttpResponse.json({
            items: [
              {
                ...AVM_US,
                functional_currency: "USD",
                time_zone: "America/Los_Angeles",
                is_active: true,
                books: [
                  { book_code: "ASC606", is_enabled: true },
                  { book_code: "IFRS15", is_enabled: false },
                ],
              },
            ],
            next_cursor: null,
          }),
        ),
      );
    }

    /**
     * The 422 of `POST /contracts/{id}/events` as the route answered it (measured on the API, register
     * index 267 (iii), case 1): reviewed, a minute passes, the draft is replaced, the assessment cites
     * the record of before the replacement.
     */
    function olderRecord(): Response {
      return problemResponse("validation-failed", 422, "Check the highlighted fields", {
        code: null,
        detail: OLDER,
        errors: [
          {
            field: "events.0.payload.judgement_record_id",
            message: OLDER,
            row: null,
            rule_id: "REQ-POL-008",
            sheet: null,
          },
        ],
      });
    }

    it("the assessment of a record reviewed before the draft was replaced: the drawer says the API's sentence and its offer opens the review drawer in its place", async () => {
      const first = assessed("ASC606", REVIEW_ID, true, "2026-01-01", 1);
      const sent = world("DRAFT", [REVIEWED], [first, voided(first, 2)], (item) =>
        item.path.endsWith("/events") ? olderRecord() : null,
      );
      oneBook();
      open();

      // Nothing on the screen says the record is refused before the API does.
      const line = await pathLine();
      expect(line.textContent).toBe(
        "Step 1 review JDG-000412 was reviewed by Priya Raman on 10 Sep 2026 16:20 UTC. Record the assessment to continue.Record assessment",
      );
      fireEvent.click(within(line).getByRole("button", { name: "Record assessment" }));
      const drawer = await screen.findByRole("dialog", { name: "Record assessment" });
      expect(within(drawer).queryByRole("button", { name: OFFER })).toBeNull();
      fireEvent.click(within(drawer).getByRole("button", { name: "Record assessment" }));

      const banner = await within(drawer).findByRole("alert");
      expect(
        within(banner).getByRole("heading", { name: "Check the highlighted fields" }),
      ).toBeTruthy();
      expect(within(banner).getAllByText(OLDER)).toHaveLength(1);
      expect(sent.map((item) => `${item.method} ${item.path}`)).toEqual([
        `POST /api/v1/contracts/${CONTRACT_ID}/events`,
      ]);
      expect(sent[0]?.body).toEqual({
        events: [
          {
            event_type: "COLLECTIBILITY_ASSESSED",
            effective_date: "2026-01-01",
            payload: {
              book: "ASC606",
              is_probable: true,
              credit_grade: "B",
              mitigation: "ADVANCE_PAYMENT",
              judgement_record_id: REVIEW_ID,
            },
          },
        ],
        evidence_file_ids: [],
      });

      fireEvent.click(within(banner).getByRole("button", { name: OFFER }));
      const review = await screen.findByRole("dialog", { name: "Record Step 1 review" });
      // One drawer at a time (DS-CMP-09): the review drawer stands in place of the assessment's.
      expect(screen.queryByRole("dialog", { name: "Record assessment" })).toBeNull();
      expect(screen.getAllByRole("dialog")).toHaveLength(1);

      answer(/^Approved and committed/, "Yes");
      answer(/^Rights identified/, "Yes");
      answer(/^Payment terms identified/, "Yes");
      answer(/^Collectibility probable/, "Yes");
      fireEvent.change(within(review).getByLabelText(/^Rationale/), {
        target: { value: "The terms of the replaced draft were reviewed again; the grade stands." },
      });
      fireEvent.click(within(review).getByRole("button", { name: "Submit for review" }));

      expect(
        await screen.findByText("Step 1 review JDG-000412 submitted for review."),
      ).toBeTruthy();
      expect(sent.map((item) => `${item.method} ${item.path}`)).toEqual([
        `POST /api/v1/contracts/${CONTRACT_ID}/events`,
        "POST /api/v1/judgements",
        `POST /api/v1/judgements/${REVIEW_ID}/submit`,
      ]);
    });

    // DS-CMP-09, DS-A11Y-10: one drawer at a time, focus inside it, and back at the trigger on close.
    it("the review drawer opened from the offer holds the focus, and closing it returns the focus to the path's command", async () => {
      const first = assessed("ASC606", REVIEW_ID, true, "2026-01-01", 1);
      world("DRAFT", [REVIEWED], [first, voided(first, 2)], (item) =>
        item.path.endsWith("/events") ? olderRecord() : null,
      );
      oneBook();
      open();

      const command = within(await pathLine()).getByRole("button", { name: "Record assessment" });
      command.focus();
      fireEvent.click(command);
      const drawer = await screen.findByRole("dialog", { name: "Record assessment" });
      fireEvent.click(within(drawer).getByRole("button", { name: "Record assessment" }));
      const offer = await within(drawer).findByRole("button", { name: OFFER });
      offer.focus();
      fireEvent.click(offer);

      const review = await screen.findByRole("dialog", { name: "Record Step 1 review" });
      await waitFor(() => expect(review.contains(document.activeElement)).toBe(true));
      // The review opens with "Commercial substance" answered from the contract, so closing it asks.
      fireEvent.click(within(review).getByRole("button", { name: "Cancel" }));
      const confirmation = await screen.findByRole("alertdialog", { name: "Discard changes?" });
      fireEvent.click(within(confirmation).getByRole("button", { name: "Discard changes" }));

      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
      expect(screen.queryByRole("alertdialog")).toBeNull();
      expect(document.activeElement).toBe(command);
    });

    it("a record reviewed in the instant of the replacement: the screen compares no time, and the assessment the API takes is recorded", async () => {
      // Measured, case 2: the review and the booking that replaced the draft carry one instant of
      // the application's clock (`reviewed_at` 2026-09-12T12:02:00Z), and the API takes the
      // assessment (201). The booking's `recorded_at`, the database's clock, is later than the
      // review (2026-10-02T19:50:51.313897Z in the measured world, whose application clock is
      // frozen): a screen that compared it would send the member to a review the API does not ask
      // for. The stream is the one `replace-draft` leaves: the booking, its void, the new booking.
      const REPLACED_AT = "2026-10-02T19:50:51.313897Z";
      const FIRST_BOOKING_ID = "cc000000-0000-4000-8000-000000000001";
      /** A booking of the draft's stream, or — where it names an event — the void of that event. */
      const streamEvent = (seq: number, recordedAt: string, voids: string | null = null) => ({
        id: `cc000000-0000-4000-8000-00000000000${String(seq)}`,
        contract_id: CONTRACT_ID,
        event_type: voids === null ? "CONTRACT_BOOKED" : "EVENT_VOIDED",
        effective_date: "2026-01-01",
        stream_version: seq,
        record_seq: seq,
        recorded_at: recordedAt,
        supersedes_event_id: voids,
        payload: {},
      });
      const sent = world(
        "DRAFT",
        [
          judgement({
            status: "REVIEWED",
            reviewer: PRIYA_ACTOR,
            reviewed_at: "2026-09-12T12:02:00Z",
            updated_at: "2026-09-12T12:02:00Z",
          }),
        ],
        [
          streamEvent(1, "2026-10-02T19:50:48.000000Z"),
          streamEvent(2, REPLACED_AT, FIRST_BOOKING_ID),
          streamEvent(3, REPLACED_AT),
        ],
      );
      oneBook();
      open();

      const line = await pathLine();
      fireEvent.click(within(line).getByRole("button", { name: "Record assessment" }));
      const drawer = await screen.findByRole("dialog", { name: "Record assessment" });
      fireEvent.click(within(drawer).getByRole("button", { name: "Record assessment" }));

      expect(await screen.findByText("Assessment recorded.")).toBeTruthy();
      expect(screen.queryByText(OLDER)).toBeNull();
      expect(screen.queryByRole("button", { name: OFFER })).toBeNull();
      expect(sent.map((item) => `${item.method} ${item.path}`)).toEqual([
        `POST /api/v1/contracts/${CONTRACT_ID}/events`,
      ]);
      // No read asked for the bookings, by name or by asking for every type: the screen holds no
      // booking's time to compare.
      expect(eventReads.length).toBeGreaterThan(0);
      for (const asked of eventReads) {
        expect(asked.length).toBeGreaterThan(0);
        expect(asked).not.toContain("CONTRACT_BOOKED");
      }
    });

    it("the overflow of a draft keeps a new Step 1 review beside the assessment, and it opens the review drawer", async () => {
      world("DRAFT", [REVIEWED], []);
      open();
      await pathLine();

      fireEvent.click(await screen.findByRole("button", { name: "More actions" }));
      const menu = screen.getByRole("menu", { name: "More actions" });
      expect(
        within(menu)
          .getAllByRole("menuitem")
          .map((item) => item.textContent),
      ).toEqual([
        "Record assessment",
        "Record Step 1 review",
        "Combine with another contract",
        "Copy link",
      ]);
      fireEvent.click(within(menu).getByRole("menuitem", { name: "Record Step 1 review" }));

      expect(await screen.findByRole("dialog", { name: "Record Step 1 review" })).toBeTruthy();
      expect(screen.queryByRole("dialog", { name: "Record assessment" })).toBeNull();
    });
  });

  it("behind the gate the banner says since when and the command is a new Step 1 review", async () => {
    world(
      "NOT_A_CONTRACT",
      [GATE],
      [
        assessed("ASC606", GATE_ID, false, "2026-09-01", 1),
        assessed("IFRS15", GATE_ID, false, "2026-09-01", 2),
      ],
    );
    open();

    const banner = await screen.findByTestId("SF-03-banner-header");
    await within(banner).findByRole("button", { name: "Record Step 1 review" });
    expect(banner.textContent).toContain(
      "The contract criteria are not met. Receipts post to deposit liability until the criteria are met.",
    );
    expect(banner.textContent).toContain(
      "Criteria not met since 01 Sep 2026 (Step 1 review JDG-000398). Record a new Step 1 review when the criteria are met.",
    );
    // The header's primary command is the same command; "Record criteria met" is not offered yet.
    expect(screen.getAllByRole("button", { name: "Record Step 1 review" }).length).toBeGreaterThan(
      1,
    );
    expect(screen.queryByRole("button", { name: "Record criteria met" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Submit for activation" })).toBeNull();
  });

  it("behind the gate a reviewed record: Record criteria met starts at today in the entity's zone and shows the API's refusal on the date", async () => {
    // 01:30 UTC on 1 Oct 2026 is still 30 Sep in Los Angeles (05 TZ-02).
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(instantMs("2026-10-01T01:30:00Z"));
    let refusals = 1;
    const sent = world(
      "NOT_A_CONTRACT",
      [GATE, REVIEWED],
      [
        assessed("ASC606", GATE_ID, false, "2026-09-01", 1),
        assessed("IFRS15", GATE_ID, false, "2026-09-01", 2),
      ],
      (item) => {
        if (!item.path.endsWith("/events") || refusals === 0) {
          return null;
        }
        refusals -= 1;
        return problemResponse("validation-failed", 422, "1 field needs attention.", {
          errors: [
            {
              field: "events.0.effective_date",
              rule_id: "REQ-POL-008",
              message: "The assessment is dated before the latest Step 1 event of its book.",
            },
          ],
        });
      },
    );
    open();

    const banner = await screen.findByTestId("SF-03-banner-header");
    const command = await within(banner).findByRole("button", { name: "Record criteria met" });
    // The line names the command it sits beside.
    expect(banner.textContent).toContain(
      "Step 1 review JDG-000412 was reviewed by Priya Raman on 10 Sep 2026 16:20 UTC. Record criteria met to continue.",
    );
    fireEvent.click(command);
    const drawer = await screen.findByRole("dialog", { name: "Record criteria met" });
    const date = within(drawer).getByRole("textbox", { name: /^Effective date/ });
    expect((date as HTMLInputElement).value).toBe("30 Sep 2026");

    fireEvent.click(within(drawer).getByRole("button", { name: "Record criteria met" }));
    expect(
      await within(drawer).findByText(
        "The assessment is dated before the latest Step 1 event of its book.",
      ),
    ).toBeTruthy();
    expect(date.getAttribute("aria-invalid")).toBe("true");

    fireEvent.click(within(drawer).getByRole("button", { name: "Record criteria met" }));
    expect(
      await screen.findByText("Criteria met recorded. Submit the contract for activation."),
    ).toBeTruthy();
    expect(sent).toHaveLength(2);
    expect(sent[1]?.body).toMatchObject({
      events: [
        {
          event_type: "COLLECTIBILITY_ASSESSED",
          effective_date: "2026-09-30",
          payload: { book: "ASC606", is_probable: true, judgement_record_id: REVIEW_ID },
        },
        {
          event_type: "COLLECTIBILITY_ASSESSED",
          effective_date: "2026-09-30",
          payload: { book: "IFRS15", is_probable: true, judgement_record_id: REVIEW_ID },
        },
      ],
    });
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): the notice period shows no message
  // of the API, so a refusal that names it was shown nowhere; the rationale's stands at its field.
  it("Record Step 1 review: the banner lists what no field shows and leaves the rationale's message at its field", async () => {
    const unplaced = "Use a notice period of at most 3,650 days.";
    const atField = "Say which payment was received.";
    world("DRAFT", [], [], (item) =>
      item.path === "/api/v1/judgements"
        ? problemResponse("validation-failed", 422, "2 fields need attention.", {
            errors: [
              { field: "questionnaire.termination.notice_days", rule_id: null, message: unplaced },
              { field: "rationale", rule_id: null, message: atField },
            ],
          })
        : null,
    );
    open();

    fireEvent.click(within(await pathLine()).getByRole("button", { name: "Record Step 1 review" }));
    const drawer = await screen.findByRole("dialog", { name: "Record Step 1 review" });
    answer(/^Approved and committed/, "Yes");
    answer(/^Rights identified/, "Yes");
    answer(/^Payment terms identified/, "Yes");
    answer(/^Collectibility probable/, "Yes");
    const rationale = within(drawer).getByLabelText(/^Rationale/);
    fireEvent.change(rationale, {
      target: { value: "The customer paid the deposit and its credit grade was raised to B." },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Submit for review" }));

    const banner = await within(drawer).findByRole("alert");
    expect(within(banner).getByText(unplaced)).toBeTruthy();
    expect(within(banner).queryByText(atField)).toBeNull();
    expect(
      (rationale.getAttribute("aria-describedby") ?? "")
        .split(" ")
        .map((id) => document.getElementById(id)?.textContent ?? ""),
    ).toContain(atField);
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): the drawer has one field, the date.
  // A message that names another member of an event was shown nowhere.
  it("Record assessment: a refusal that names a member the drawer has no field for is listed by the banner", async () => {
    world("DRAFT", [REVIEWED], [], (item) =>
      item.path.endsWith("/events")
        ? problemResponse("validation-failed", 422, "1 field needs attention.", {
            errors: [
              {
                field: "events.0.payload.credit_grade",
                rule_id: "T-CON-19",
                message: "Use a credit grade of the entity's scale.",
              },
            ],
          })
        : null,
    );
    open();

    fireEvent.click(within(await pathLine()).getByRole("button", { name: "Record assessment" }));
    const drawer = await screen.findByRole("dialog", { name: "Record assessment" });
    fireEvent.click(within(drawer).getByRole("button", { name: "Record assessment" }));

    const banner = await within(drawer).findByRole("alert");
    expect(within(banner).getByRole("heading", { name: "1 field needs attention." })).toBeTruthy();
    expect(within(banner).getByText("Use a credit grade of the entity's scale.")).toBeTruthy();
  });

  it("a failed read of the path says so with Retry and offers no Step 1 command", async () => {
    world("NOT_A_CONTRACT", [GATE], []);
    // The read and its one automatic retry fail (`retry: 1` of the query client).
    let failures = 2;
    server.use(
      http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/events`), () => {
        if (failures > 0) {
          failures -= 1;
          return problemResponse("internal-error", 500, "Something went wrong");
        }
        return HttpResponse.json({
          items: [
            assessed("ASC606", GATE_ID, false, "2026-09-01", 1),
            assessed("IFRS15", GATE_ID, false, "2026-09-01", 2),
          ],
          next_cursor: null,
        });
      }),
    );
    open();

    const banner = await screen.findByTestId("SF-03-banner-header");
    expect(
      await within(banner).findByText("Could not load the Step 1 review and its assessments"),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Record Step 1 review" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Submit for activation" })).toBeNull();

    fireEvent.click(within(banner).getByRole("button", { name: "Retry" }));
    await within(banner).findByRole("button", { name: "Record Step 1 review" });
    expect(banner.textContent).toContain("Criteria not met since 01 Sep 2026");
  });

  it("behind the gate with the criteria-met assessment recorded: Submit for activation sends the command and names the request", async () => {
    const sent = world(
      "NOT_A_CONTRACT",
      [GATE, REVIEWED],
      [
        assessed("ASC606", GATE_ID, false, "2026-09-01", 1),
        assessed("IFRS15", GATE_ID, false, "2026-09-01", 2),
        assessed("ASC606", REVIEW_ID, true, "2026-09-10", 3),
        assessed("IFRS15", REVIEW_ID, true, "2026-09-10", 4),
      ],
    );
    open();

    const banner = await screen.findByTestId("SF-03-banner-header");
    await within(banner).findByRole("button", { name: "Submit for activation" });
    expect(banner.textContent).toContain(
      "Criteria met on 10 Sep 2026 (Step 1 review JDG-000412). Submit the contract for activation.",
    );
    expect(screen.getByTestId("SF-03-tracker-step-1").getAttribute("aria-label")).toBe(
      "Step 1, Contract, needs attention, Criteria met on 10 Sep 2026: submit for activation",
    );

    fireEvent.click(within(banner).getByRole("button", { name: "Submit for activation" }));
    expect(
      await screen.findByText(
        "Submitted for activation. Request APR-000440 is waiting for approval.",
      ),
    ).toBeTruthy();
    expect(sent.map((item) => `${item.method} ${item.path} ${item.ifMatch ?? ""}`)).toEqual([
      `POST /api/v1/contracts/${CONTRACT_ID}/submit-activation "s6"`,
    ]);
  });
});

// SCREENS §4.1.6, §4.9.4 and §5.6 (rev 1.75; lane SECFIX-ACT's item HOLD-RELEASE-READ-1 on the screens; 04
// §16.1 and §16.2 rev 1.299 `holds`, `POST /contracts/{id}/release-hold`): a contract on hold offers
// "Release hold", and the obligation pane lists the obligation's own holds with the command. Until 04
// rev 1.299 no read answered the id the command takes, and a hold applied on a screen had no exit on
// the screens. The members are as measured through the API.
describe("SF-03 Release hold", () => {
  const WHOLE_ID = "01a0ff4f-d9d6-7ee3-9a26-9a68a456e700";
  const O2_HOLD_ID = "01a0ff4f-dcc5-7ec3-8809-9afb8d18ad6f";
  const MAYA_ACTOR = { id: MAYA.user.id, display_name: "Maya Chen", kind: "USER" };
  /** A hold of the whole contract: API-S-Contract lists it, no obligation does. */
  const WHOLE = {
    id: WHOLE_ID,
    level: "contract",
    hold_type: "journal_export",
    hold_source: "MANUAL",
    reason: "Invoice dispute pending with the customer.",
    applied_by: MAYA_ACTOR,
    applied_at: "2026-09-12T12:00:00Z",
    release_refusal: null,
  };
  /** The hold of O2: that obligation lists it, the contract does not. */
  const OF_O2 = {
    ...WHOLE,
    id: O2_HOLD_ID,
    level: "obligation",
    hold_type: "recognition",
    reason: "Customer disputes O2.",
    applied_at: "2026-09-13T08:30:00Z",
  };
  const WHOLE_LABEL =
    "Journal export hold · Invoice dispute pending with the customer. · applied 12 Sep 2026 12:00 UTC";
  const O2_LABEL = "O2 · Recognition hold · Customer disputes O2. · applied 13 Sep 2026 08:30 UTC";
  const CLOSED = "A voided or terminated contract takes no hold.";

  interface Release {
    readonly body: unknown;
    readonly ifMatch: string | null;
  }

  /**
   * The frame of a contract with the holds its reads list — the contract its own, each obligation its
   * own — and the releases it was sent.
   */
  function held(
    current: Record<string, unknown>,
    ofO2: readonly Record<string, unknown>[] = [OF_O2],
  ): Release[] {
    const releases: Release[] = [];
    const [o1, o2] = OBLIGATIONS;
    const listed = [
      { ...o1, holds: [] },
      { ...o2, holds: ofO2 },
    ];
    serve(newRecorded(), current);
    server.use(
      http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/obligations`), () =>
        HttpResponse.json({ items: listed, next_cursor: null }),
      ),
      http.get(apiUrl(`/api/v1/obligations/${O1_ID}`), () => HttpResponse.json(listed[0])),
      http.get(apiUrl(`/api/v1/obligations/${O2_ID}`), () => HttpResponse.json(listed[1])),
      http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/release-hold`), async ({ request }) => {
        releases.push({ body: await request.json(), ifMatch: request.headers.get("If-Match") });
        return HttpResponse.json({ ...current, on_hold: false, holds: [] });
      }),
    );
    return releases;
  }

  async function menu(): Promise<HTMLElement> {
    fireEvent.click(await screen.findByRole("button", { name: "More actions" }));
    return screen.getByRole("menu", { name: "More actions" });
  }

  function items(of: HTMLElement): (string | null)[] {
    return within(of)
      .getAllByRole("menuitem")
      .map((item) => item.textContent);
  }

  /** The words of the options of the drawer's select "Hold". */
  function holdOptions(drawer: HTMLElement): (string | null)[] {
    const trigger = within(drawer).getByRole("combobox", { name: /^Hold/ });
    fireEvent.click(trigger);
    const list = document.getElementById(trigger.getAttribute("aria-controls") ?? "");
    if (list === null) {
      throw new Error("The select Hold has no open list");
    }
    return within(list)
      .getAllByRole("option")
      .map((item) => item.textContent);
  }

  it("a contract on hold offers Release hold behind Apply hold, and its drawer lists the contract's hold and the obligations'", async () => {
    held(contract({ on_hold: true, holds: [WHOLE] }));
    renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const actions = await menu();
    const names = items(actions);
    expect(names.slice(names.indexOf("Apply hold"), names.indexOf("Apply hold") + 2)).toEqual([
      "Apply hold",
      "Release hold",
    ]);
    fireEvent.click(within(actions).getByRole("menuitem", { name: "Release hold" }));

    const drawer = await screen.findByRole("dialog", { name: "Release hold" });
    expect(holdOptions(drawer)).toEqual([WHOLE_LABEL, O2_LABEL]);
  });

  it("Release hold stands while the contract is on hold alone, for a holder of contract.create for the contract's entity, and not on a view of an earlier known_at", async () => {
    const reads = ["contract.read", "config.read", "ssp.read"];
    const holderFor = (entityId: string) =>
      signedInMe({
        permissions: [...reads, "contract.create"],
        permission_scopes: {
          ...Object.fromEntries(reads.map((code): [string, "*"] => [code, "*"])),
          "contract.create": [entityId],
        },
      });
    const onHold = contract({ on_hold: true, holds: [WHOLE] });
    const views: readonly (readonly [Record<string, unknown>, typeof MAYA, string, boolean])[] = [
      [contract(), MAYA, "", false],
      [onHold, holderFor(US_ID), "", true],
      [onHold, holderFor("0a1b2c3d-4e5f-4a6b-8c7d-0000000000ff"), "", false],
      [onHold, MAYA, "&known_at=2026-09-12T12%3A00%3A00Z", false],
    ];
    for (const [current, me, extra, offered] of views) {
      held(current);
      renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}${extra}`, {
        me,
        screenRoutes: SCREEN_ROUTES,
      });
      expect(items(await menu()).includes("Release hold")).toBe(offered);
      cleanup();
      server.resetHandlers();
    }
  });

  it("a draft on hold and a terminated contract on hold offer Release hold too, before Copy link", async () => {
    for (const status of ["DRAFT", "TERMINATED"]) {
      held(contract({ status, activated_at: null, on_hold: true, holds: [WHOLE] }));
      renderApp(`/contracts/${CONTRACT_ID}/obligations?${CONTEXT}`, {
        me: MAYA,
        screenRoutes: SCREEN_ROUTES,
      });
      expect(items(await menu()).slice(-2)).toEqual(["Release hold", "Copy link"]);
      cleanup();
      server.resetHandlers();
    }
  });

  it("the pane lists the obligation's own holds, and Release hold opens the drawer with that hold chosen: the release is sent under the contract's head", async () => {
    const releases = held(contract({ on_hold: true, holds: [WHOLE] }));
    renderApp(`/contracts/${CONTRACT_ID}/obligations/${O2_ID}?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });

    const pane = await screen.findByTestId("SF-03-pane-obligation");
    const table = await within(pane).findByRole("table", { name: "Holds" });
    expect(table.getAttribute("data-testid")).toBe("SF-03-grid-obligation-holds");
    // The obligation's own hold: the hold of the whole contract is the contract's and is not here.
    expect(
      within(table)
        .getAllByRole("row")
        .map((row) =>
          Array.from(row.children)
            .map((cell) => cell.textContent)
            .join(" | "),
        ),
    ).toEqual([
      "Hold type | Source | Reason | Applied at | Release",
      "Recognition hold | Manual | Customer disputes O2. | 13 Sep 2026 08:30 UTC | Release hold",
    ]);
    fireEvent.click(within(table).getByRole("button", { name: "Release hold" }));

    // Two holds are options, and the one the pane named is the one chosen.
    const drawer = await screen.findByRole("dialog", { name: "Release hold" });
    expect(within(drawer).getByRole("combobox", { name: /^Hold/ }).textContent).toBe(O2_LABEL);
    fireEvent.change(within(drawer).getByLabelText(/^Comment/), {
      target: { value: "The customer accepted O2." },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Release hold" }));

    expect(await screen.findByText("Hold released on SF-ORD-10001.")).toBeTruthy();
    expect(releases).toEqual([
      { body: { hold_id: O2_HOLD_ID, comment: "The customer accepted O2." }, ifMatch: '"s6"' },
    ]);
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Release hold" })).toBeNull());
  });

  it("a hold that is not released by hand reads the API's sentence in the pane for every reader, and the column Release stands only where a row has something for it", async () => {
    const reader = signedInMe({ permissions: ["contract.read", "config.read", "ssp.read"] });
    const rows = async (): Promise<string[]> => {
      const pane = await screen.findByTestId("SF-03-pane-obligation");
      const table = await within(pane).findByRole("table", { name: "Holds" });
      expect(within(table).queryByRole("button")).toBeNull();
      return within(table)
        .getAllByRole("row")
        .map((row) =>
          Array.from(row.children)
            .map((cell) => cell.textContent)
            .join(" | "),
        );
    };

    // A terminated contract: the API says why its hold is not released — to a reader, and in the
    // command's place to a member who may release holds.
    for (const me of [reader, MAYA]) {
      held(contract({ status: "TERMINATED", on_hold: true }), [
        { ...OF_O2, release_refusal: CLOSED },
      ]);
      renderApp(`/contracts/${CONTRACT_ID}/obligations/${O2_ID}?${CONTEXT}`, {
        me,
        screenRoutes: SCREEN_ROUTES,
      });
      expect(await rows()).toEqual([
        "Hold type | Source | Reason | Applied at | Release",
        `Recognition hold | Manual | Customer disputes O2. | 13 Sep 2026 08:30 UTC | ${CLOSED}`,
      ]);
      cleanup();
      server.resetHandlers();
    }

    // A hold that is released by hand, read by a member who is not offered the release — a reader,
    // a holder of contract.create for another entity, and a holder on a view of an earlier known_at:
    // no column for it.
    const reads = ["contract.read", "config.read", "ssp.read"];
    const elsewhere = signedInMe({
      permissions: [...reads, "contract.create"],
      permission_scopes: {
        ...Object.fromEntries(reads.map((code): [string, "*"] => [code, "*"])),
        "contract.create": ["0a1b2c3d-4e5f-4a6b-8c7d-0000000000ff"],
      },
    });
    const views: readonly (readonly [typeof MAYA, string])[] = [
      [reader, ""],
      [elsewhere, ""],
      [MAYA, "&known_at=2026-09-12T12%3A00%3A00Z"],
    ];
    for (const [me, extra] of views) {
      held(contract({ on_hold: true }));
      renderApp(`/contracts/${CONTRACT_ID}/obligations/${O2_ID}?${CONTEXT}${extra}`, {
        me,
        screenRoutes: SCREEN_ROUTES,
      });
      expect(await rows()).toEqual([
        "Hold type | Source | Reason | Applied at",
        "Recognition hold | Manual | Customer disputes O2. | 13 Sep 2026 08:30 UTC",
      ]);
      cleanup();
      server.resetHandlers();
    }

    // An obligation without a hold of its own, on a contract that is on hold.
    held(contract({ on_hold: true, holds: [WHOLE] }));
    renderApp(`/contracts/${CONTRACT_ID}/obligations/${O1_ID}?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: SCREEN_ROUTES,
    });
    const pane = await screen.findByTestId("SF-03-pane-obligation");
    expect(await within(pane).findByText("No holds")).toBeTruthy();
    expect(within(pane).queryByRole("table", { name: "Holds" })).toBeNull();
  });
});
