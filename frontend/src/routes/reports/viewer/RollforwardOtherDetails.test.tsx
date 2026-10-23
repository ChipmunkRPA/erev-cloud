// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, expect, it } from "vitest";
import type { ReportRun } from "../../../lib/api/queries/reports";
import { registerCurrencies } from "../../../lib/format";
import { RollforwardOtherDetails } from "./RollforwardOtherDetails";

afterEach(cleanup);
beforeAll(() => registerCurrencies([{ code: "USD", minor_unit: 2 }]));
function mount(control: unknown) {
  const run = { control_totals: control } as ReportRun;
  return render(
    <MemoryRouter>
      <RollforwardOtherDetails run={run} />
    </MemoryRouter>,
  );
}
it("shows original signed amounts and links to the affected close period", () => {
  mount({
    other_explanation: {
      threshold_ratio: "0.01",
      items: [
        {
          contract: "C-A",
          entity: "US",
          period: "FY2026-P09",
          book: "ASC606",
          currency: "USD",
          role: "contract_liability",
          other: "-2.00",
          closing: "100.00",
        },
      ],
    },
  });
  expect(screen.getByText("Other movements — explanation required")).toBeTruthy();
  expect(screen.getByText(/These Other movements exceed 1/)).toBeTruthy();
  const details = screen.getByText("Review 1 flagged balance").closest("details");
  if (details === null) throw new Error("Missing details");
  details.open = true;
  expect(screen.getByText(/C-A US/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "Open reconciliations" }).getAttribute("href")).toBe(
    "/close/US/ASC606/FY2026-P09/reconciliations",
  );
  expect(details.textContent).toContain("100.00");
  expect(details.textContent).toContain("2.00");
});
it("does not invent a warning for old reports or a run with no threshold breaches", () => {
  const view = mount({});
  expect(view.container.textContent).toBe("");
  view.unmount();
  const empty = mount({ other_explanation: { threshold_ratio: "0.01", items: [] } });
  expect(empty.container.textContent).toBe("");
});
