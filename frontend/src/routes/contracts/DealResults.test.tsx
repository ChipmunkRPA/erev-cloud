// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import type { DealPreview } from "../../lib/api/queries/deal-previews";
import { DealResults } from "./DealResults";

afterEach(cleanup);
it("shows the saved allocation and explains revenue awaiting a trigger without inventing schedule rows", () => {
  const money = { amount: "90071992547409.01", currency: "USD" };
  const preview: DealPreview = {
    id: "preview",
    save_allowed: false,
    created_at: "2026-10-19",
    engine_release_id: "release",
    saved_contract_id: null,
    input_sha256: "input",
    result_sha256: "result",
    result: {},
    pinned_refs: {},
    proposal: { customer_name: "Buyer", entity_code: "US", start_date: "2026-11-01", lines: [] },
    presentation: [
      {
        book_code: "ASC606",
        transaction_price: money,
        total_allocated: money,
        scheduled: { amount: "0.00", currency: "USD" },
        awaiting_trigger: money,
        has_material_right: false,
        has_variable_consideration: true,
        allocations: [
          {
            subject_key: "L1",
            obligation_key: "L1",
            product_code: "PLATFORM",
            stated_price: money,
            ssp_low: null,
            ssp_mid: null,
            ssp_high: null,
            range_position: null,
            selected_ssp: "90071992547409.01",
            allocation_weight: "1",
            allocated_amount: money,
            allocation_adjustment: { amount: "0.00", currency: "USD" },
          },
        ],
        revenue_by_period: [],
      },
    ],
  };
  render(<DealResults preview={preview} />);
  expect(screen.getByText("ASC606")).toBeTruthy();
  expect(screen.getAllByText("90071992547409.01 USD").length).toBeGreaterThan(0);
  expect(screen.getByText(/No revenue is scheduled yet/)).toBeTruthy();
  expect(screen.queryByText("Inside range")).toBeNull();
  expect(screen.getByText(/Variable consideration: Yes/)).toBeTruthy();
});
