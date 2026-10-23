// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it } from "vitest";
import type { ReportRun } from "../../../lib/api/queries/reports";
import { OpeningAttributionDetails } from "./OpeningAttributionDetails";
afterEach(cleanup);
function mount(control: unknown) {
  return render(
    <MemoryRouter>
      <OpeningAttributionDetails run={{ control_totals: control } as ReportRun} />
    </MemoryRouter>,
  );
}
it("shows retained opening reasons and original creation evidence with history navigation", () => {
  mount({
    opening_attribution_explanation: {
      items: [
        {
          subject: "C/O2",
          contract_id: "contract-1",
          basis: "CREATED_AFTER_OPENING",
          event_id: "event-1",
          effective_date: "2026-09-16",
        },
        {
          subject: "C/O1",
          contract_id: "contract-1",
          basis: "ZERO_CONSUMPTION",
          event_id: "",
          effective_date: "",
        },
      ],
    },
  });
  expect(screen.getByText("Opening attribution explanation")).toBeTruthy();
  expect(screen.getByText(/Created after the opening date/)).toBeTruthy();
  expect(screen.getByText("Creation effective date: 2026-09-16")).toBeTruthy();
  expect(screen.getByText("Original creation event: event-1")).toBeTruthy();
  expect(screen.getByText(/No positive liability consumption/)).toBeTruthy();
  expect(screen.getAllByRole("link", { hidden: true })[0]?.getAttribute("href")).toBe(
    "/contracts/contract-1/history",
  );
});
it("keeps legacy and empty reports unchanged and rejects unknown reasons", () => {
  expect(mount({}).container.textContent).toBe("");
  cleanup();
  expect(
    mount({ opening_attribution_explanation: { items: [{ basis: "INVENTED" }] } }).container
      .textContent,
  ).toBe("");
});
