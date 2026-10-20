// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { DealRevenue } from "./DealRevenue";

afterEach(cleanup);
it("pages the chart and matrix together, retains all-period totals and resets paging when scope changes", () => {
  const rows = Array.from({ length: 25 }, (_, index) => ({
    entity_code: "US",
    period_key: `FY2026-P${String(index + 1).padStart(2, "0")}`,
    product_code: "A",
    subject_key: "L1",
    amount: { amount: "1.00", currency: "USD" },
  }));
  rows.push({
    entity_code: "US",
    period_key: "FY2026-P01",
    product_code: "B",
    subject_key: "L2",
    amount: { amount: "7.00", currency: "EUR" },
  });
  render(<DealRevenue rows={rows} />);
  fireEvent.change(screen.getByLabelText("Revenue entity and currency"), {
    target: { value: JSON.stringify(["US", "USD"]) },
  });
  expect(screen.getByRole("img").getAttribute("aria-label")).toContain("25.00");
  expect(screen.queryByText("FY2026-P25")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Next periods" }));
  expect(screen.getAllByText("FY2026-P25")).toHaveLength(2);
  expect(screen.queryByText("FY2026-P01")).toBeNull();
  expect(screen.getAllByText("25.00")).toHaveLength(2);
  fireEvent.change(screen.getByLabelText("Revenue entity and currency"), {
    target: { value: JSON.stringify(["US", "EUR"]) },
  });
  expect(screen.getAllByText("FY2026-P01")).toHaveLength(2);
  expect(screen.queryByRole("button", { name: "Next periods" })).toBeNull();
  expect(screen.getByRole("img").getAttribute("aria-label")).toContain("7.00");
});
