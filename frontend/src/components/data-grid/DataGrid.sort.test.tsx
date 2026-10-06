// @vitest-environment jsdom
// SCREENS SCR-URL-09 and SCR-URL-21 (rev 1.11; DESIGN_SYSTEM DS-CMP-10): `sort` is one URL parameter. On
// a screen with more than one grid each grid applies only a key of its own, and the value is dropped as
// unrecognised only when no grid on the screen lists it. Found by the route crawl on SF-16:developer,
// where "Deliveries" dropped the key of "Webhook endpoints" beside it.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "../../app/providers";
import type { ListPage } from "../../lib/api/lists";
import { queryKey } from "../../lib/api/query-keys";
import { installGridViewport } from "../../test/layout";
import { DataGrid } from "./DataGrid";
import type { GridColumn, GridSource } from "./types";

installGridViewport();

interface Row {
  readonly id: string;
  readonly name: string;
}

const ROWS: readonly Row[] = [
  { id: "r-1", name: "https://hooks.example.test/a" },
  { id: "r-2", name: "https://hooks.example.test/b" },
];
const UNRECOGNISED = "Some filters in the link were not recognised and were removed.";

afterEach(() => {
  cleanup();
});

function Probe() {
  return <output data-testid="search">{useLocation().search}</output>;
}

function fetcher() {
  return vi.fn<GridSource<Row>["fetchPage"]>((): Promise<ListPage<Row>> =>
    Promise.resolve({ items: ROWS, nextCursor: null, total: { count: 2, capped: false } }),
  );
}

function columns(sortKey: string | undefined): readonly GridColumn<Row>[] {
  return [
    {
      id: "name",
      header: "URL",
      kind: "text",
      value: (row) => row.name,
      ...(sortKey === undefined ? {} : { sortKey }),
    },
  ];
}

function renderGrids(entry: string, second: string | undefined | null) {
  const first = fetcher();
  const other = fetcher();
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[entry]}>
        <DataGrid
          name="webhook-endpoints"
          title="Webhook endpoints"
          countLabel={(_, formatted) => `${formatted} endpoints`}
          columns={columns("url")}
          source={{ queryKey: queryKey("endpoints", "tenant"), fetchPage: first }}
          rowKey={(row) => row.id}
          rowLabel={(row) => row.name}
        />
        {second === null ? null : (
          <DataGrid
            name="webhook-deliveries"
            title="Deliveries"
            countLabel={(_, formatted) => `${formatted} deliveries`}
            columns={columns(second)}
            source={{ queryKey: queryKey("deliveries", "tenant"), fetchPage: other }}
            rowKey={(row) => row.id}
            rowLabel={(row) => row.name}
          />
        )}
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { first, other };
}

function header(grid: string): HTMLElement {
  return within(screen.getByRole("grid", { name: grid })).getByRole("columnheader", {
    name: /^URL/,
  });
}

describe("SCR-URL-09 sort on a screen with more than one grid", () => {
  it("a grid keeps its sort beside a grid that does not list the key, and that grid keeps its default order", async () => {
    const { first, other } = renderGrids("/settings/developer", undefined);
    await screen.findAllByText("https://hooks.example.test/a");

    fireEvent.click(header("Webhook endpoints"));

    await waitFor(() => {
      expect(header("Webhook endpoints").getAttribute("aria-sort")).toBe("ascending");
    });
    await waitFor(() => {
      expect(first).toHaveBeenLastCalledWith(null, "url");
    });
    expect(screen.getByTestId("search").textContent).toBe("?sort=url");
    expect(screen.queryByText(UNRECOGNISED)).toBeNull();
    // The other grid never asks for a key that is not its own.
    expect(other.mock.calls.map((call) => call[1])).toEqual([null]);
  });

  it("two grids with different keys: a link that names the key of one sorts that grid only", async () => {
    const { first, other } = renderGrids("/settings/developer?sort=-created_at", "created_at");
    await screen.findAllByText("https://hooks.example.test/a");

    await waitFor(() => {
      expect(other).toHaveBeenLastCalledWith(null, "-created_at");
    });
    expect(header("Deliveries").getAttribute("aria-sort")).toBe("descending");
    expect(header("Webhook endpoints").getAttribute("aria-sort")).toBe("none");
    expect(first.mock.calls.map((call) => call[1])).toEqual([null]);
    expect(screen.getByTestId("search").textContent).toBe("?sort=-created_at");
    expect(screen.queryByText(UNRECOGNISED)).toBeNull();
  });

  it("a key no grid on the screen lists is dropped with the SCR-URL-21 banner", async () => {
    renderGrids("/settings/developer?sort=status", "created_at");

    expect(await screen.findAllByText(UNRECOGNISED)).not.toHaveLength(0);
    await waitFor(() => {
      expect(screen.getByTestId("search").textContent).toBe("");
    });
  });

  it("a single grid still drops a key it does not list", async () => {
    renderGrids("/settings/developer?sort=status", null);

    expect(await screen.findByText(UNRECOGNISED)).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByTestId("search").textContent).toBe("");
    });
  });
});
