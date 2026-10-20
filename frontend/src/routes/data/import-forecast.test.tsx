// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { ImportNew } from "./import-new";
import { correctedFileRoute } from "./import-detail";
const state = vi.hoisted(() => ({ status: "DRAFT", upload: vi.fn(), submit: vi.fn() }));
vi.mock("../../lib/access", () => ({ useAccess: () => ({ holdsAnywhere: () => true }) }));
vi.mock("../../lib/api/queries/me", () => ({ useMe: () => ({ data: {} }) }));
vi.mock("./imports", () => ({ DataPageHeader: () => null }));
vi.mock("../settings/index", () => ({ useBuiltPaths: () => new Set() }));
vi.mock("../../lib/api/commands", () => ({
  useCommand: () => ({ submit: state.submit, pending: false }),
  useCommandKeys: () => ({}),
}));
vi.mock("../../lib/api/queries/ssp-books", () => ({ uploadFile: state.upload }));
vi.mock("../../lib/api/queries/forecasts", () => ({
  FORECAST_IMPORT_TEMPLATES: new Set(["usage"]),
  fetchForecastInput: async () => ({
    id: "draft",
    code: "BUDGET",
    name: "Budget",
    version_no: 2,
    status: state.status,
  }),
}));
vi.mock("../../lib/api/queries/import-templates", () => ({
  importTemplatesKey: () => ["templates"],
  templateName: (row: { name: string }) => row.name,
  fetchImportTemplates: async () => [
    { code: "usage", name: "Usage", family: "CSV_V2", required_parameters: [] },
    { code: "contracts", name: "Contracts", family: "CSV_V2", required_parameters: [] },
  ],
}));
vi.mock("../../lib/api/queries/mapping-profiles", () => ({
  publishedProfilesKey: () => ["profiles"],
  fetchPublishedProfiles: async () => [],
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  state.status = "DRAFT";
});
function open() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={["/data/imports/new?event_set=draft"]}>
        <ImportNew />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
it("shows the selected draft and restricts import templates to forecast facts", async () => {
  open();
  expect(await screen.findByText("BUDGET — Budget · v2 · DRAFT")).toBeTruthy();
  fireEvent.click(screen.getByRole("combobox", { name: "Template" }));
  expect(await screen.findByRole("option", { name: "Usage" })).toBeTruthy();
  expect(screen.queryByRole("option", { name: "Contracts" })).toBeNull();
});
it("blocks a published target before uploading a file", async () => {
  state.status = "PUBLISHED";
  open();
  await screen.findByText("BUDGET — Budget · v2 · PUBLISHED");
  fireEvent.submit(screen.getByRole("form"));
  expect(state.upload).not.toHaveBeenCalled();
  expect(state.submit).not.toHaveBeenCalled();
});
it("preserves the assumption target and mode for corrected uploads", () => {
  const route = correctedFileRoute({
    template: { code: "usage", name: "Usage", version: 1 },
    parameters: { mode: "prospective" },
    forecast_event_set_id: "draft",
  });
  const search = new URL(route, "https://example.invalid").searchParams;
  expect(search.get("event_set")).toBe("draft");
  expect(search.get("template")).toBe("usage");
  expect(search.get("mode")).toBe("prospective");
});
it("carries the verified target into the import creation request", async () => {
  state.upload.mockResolvedValue({ id: "file" });
  state.submit.mockResolvedValue({ kind: "network-error", error: new Error("offline") });
  open();
  await screen.findByText("BUDGET — Budget · v2 · DRAFT");
  fireEvent.click(screen.getByRole("combobox", { name: "Template" }));
  fireEvent.mouseDown(await screen.findByRole("option", { name: "Usage" }));
  fireEvent.change(screen.getByTestId("SF-10-file-input"), {
    target: { files: [new File(["header\nvalue"], "usage.csv", { type: "text/csv" })] },
  });
  fireEvent.submit(screen.getByRole("form"));
  await vi.waitFor(() =>
    expect(state.submit).toHaveBeenCalledWith({
      file_id: "file",
      template_code: "usage",
      parameters: {},
      mapping_profile_id: null,
      forecast_event_set_id: "draft",
    }),
  );
});
