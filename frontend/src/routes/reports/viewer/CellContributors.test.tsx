// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { registerCurrencies } from "../../../lib/format";
import { CellContributors } from "./CellContributors";
const id = "00000000-0000-4000-8000-000000000001";
vi.mock("@tanstack/react-query", () => ({ useQuery: () => ({ data: {
  value: { amount: "26.67", currency: "GBP" }, other_entities: [],
  contributors: { items: [{ object_type: "opening_disclosure_contribution", id,
    measure: "revenue_from_opening", value: { amount: "26.67", currency: "GBP" }, href: "",
    source_links: [
      { label: "Original opening", href: `/trace/${id}?node=billed_cum%3AA%2FO1` },
      { label: "Member history", href: `/contracts/${id}/history` },
      { label: "Unsafe external", href: "https://example.invalid/" },
      { label: "Unsafe script", href: "javascript:alert(1)" },
    ],
  }] },
} }) }));
vi.mock("../../../components/explain/ExplainTrigger", () => ({ useExplain: () => ({ open: vi.fn() }) }));
afterEach(cleanup);
it("links original sources without a fake clickable group record or external navigation", () => {
  registerCurrencies([{ code: "GBP", minor_unit: 2 }]);
  render(<MemoryRouter><CellContributors request={{ runId: id, rowKey: "combined:group", columnKey: "revenue_from_opening", label: "Opening revenue", element: null }} onClose={vi.fn()} /></MemoryRouter>);
  expect(screen.getByRole("link", { name: "Original opening" }).getAttribute("href")).toBe(`/trace/${id}?node=billed_cum%3AA%2FO1`);
  expect(screen.getByRole("link", { name: "Member history" }).getAttribute("href")).toBe(`/contracts/${id}/history`);
  expect(screen.queryByText("Unsafe external")).toBeNull();
  expect(screen.queryByText("Unsafe script")).toBeNull();
  expect(screen.queryByRole("button", { name: "Opening-liability disclosure contribution" })).toBeNull();
});
