// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { DealPreviewPage } from "./deal-preview";

const state = vi.hoisted(() => ({ submit: vi.fn(), allowed: true }));
vi.mock("../../lib/access", () => ({
  useAccess: () => ({
    holdsAnywhere: () => state.allowed,
    holdsForEvery: (_: string, entities: { code: string }[]) => entities[0]?.code === "US",
  }),
}));
vi.mock("../../lib/api/commands", () => ({
  useCommand: () => ({ submit: state.submit, pending: false, problem: null, reset: vi.fn() }),
}));
vi.mock("../../lib/api/jobs", () => ({
  useJob: () => ({ data: undefined }),
  isTerminal: () => false,
}));
vi.mock("../../lib/api/queries/tenant", () => ({
  entitiesKey: () => ["entities"],
  fetchActiveEntities: async () => [
    { id: "us", code: "US", functional_currency: "USD" },
    { id: "de", code: "DE", functional_currency: "EUR" },
  ],
}));
vi.mock("../../lib/api/queries/contracts", () => ({
  customersKey: () => ["customers"],
  fetchCustomers: async () => [{ id: "customer-id", name: "Existing customer" }],
}));
vi.mock("../../lib/api/queries/deal-previews", () => ({
  fetchDealProducts: async () => [
    { id: "platform", code: "PLATFORM", name: "Enterprise platform" },
  ],
  fetchDealPreview: vi.fn(),
  dealHistoryKey: ["deal-previews", "tenant"],
  fetchDealPreviews: vi.fn(),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  state.allowed = true;
});
function page(path = "/contracts/deal-preview") {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={[path]}>
        <DealPreviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
it("submits exact decimal amounts in the authorized entity currency and retains fields after a network failure", async () => {
  state.submit.mockResolvedValue({ kind: "network-error" });
  page();
  await screen.findByRole("option", { name: "US · USD" });
  expect(screen.queryByRole("option", { name: "DE · EUR" })).toBeNull();
  fireEvent.change(screen.getByLabelText("Customer"), { target: { value: "Buyer" } });
  fireEvent.change(screen.getByLabelText("Entity"), { target: { value: "US" } });
  fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-11-01" } });
  fireEvent.change(screen.getByRole("combobox", { name: /Product code/ }), {
    target: { value: "Enterprise" },
  });
  fireEvent.mouseDown(
    await screen.findByRole("option", { name: "PLATFORM · Enterprise platform" }),
  );
  fireEvent.change(screen.getByLabelText("Line price USD"), { target: { value: "90000.01" } });
  fireEvent.change(screen.getByLabelText("Term in months (optional)"), { target: { value: "12" } });
  fireEvent.click(screen.getByRole("button", { name: "Run preview" }));
  await waitFor(() =>
    expect(state.submit).toHaveBeenCalledWith({
      input: {
        customer_name: "Buyer",
        entity_code: "US",
        start_date: "2026-11-01",
        lines: [
          {
            product_code: "PLATFORM",
            quantity: "1",
            term_months: 12,
            price: { amount: "90000.01", currency: "USD" },
            performing_entity_code: null,
          },
        ],
      },
    }),
  );
  await screen.findByText(/request could not be confirmed/);
  expect((screen.getByLabelText("Line price USD") as HTMLInputElement).value).toBe("90000.01");
});
it("blocks access without scenario permission", () => {
  state.allowed = false;
  page();
  expect(screen.queryByRole("button", { name: "Run preview" })).toBeNull();
});
it("reports an invalid link and permits starting again", async () => {
  page("/contracts/deal-preview?job=bad");
  expect(screen.getByText("This preview link is invalid.")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Start over" }));
  expect(await screen.findByRole("alertdialog")).toBeTruthy();
});
