// @vitest-environment jsdom
// DS-CMP-10 virtualization (DESIGN_SYSTEM §7.3 "Data loading"; docs/dev-guide.md DG-FE-07, DG-LST-06): 50,000
// rows reported by X-Erev-Total-Count render at most 120 body-row nodes, `aria-rowcount` counts the header
// row, and pages of 200 rows are requested as the viewport nears the end of the loaded rows.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { createQueryClient } from "../../app/providers";
import { fetchListPage } from "../../lib/api/lists";
import { queryKey } from "../../lib/api/query-keys";
import { apiUrl, installMswServer, server } from "../../test/msw";
import { DataGrid, ROW_HEIGHT } from "./DataGrid";
import type { GridColumn, GridSource } from "./types";

installMswServer();

interface Contract {
  readonly id: string;
  readonly external_id: string;
}

const COLUMNS: readonly GridColumn<Contract>[] = [
  {
    id: "contract",
    header: "Contract",
    kind: "identifier",
    value: (row) => row.external_id,
    href: (row) => `/contracts/${row.id}`,
  },
];

const SOURCE: GridSource<Contract> = {
  queryKey: queryKey("contracts", "tenant"),
  fetchPage: (cursor, sort) => fetchListPage<Contract>("/api/v1/contracts", { sort }, cursor),
};

const VIEWPORT_PX = 720;
const PAGE = 200;
const offsetHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "offsetHeight");

// jsdom has no layout: the grid's scroll viewport reports 720 px, everything else 0.
beforeEach(() => {
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    get(this: HTMLElement) {
      return this.getAttribute("role") === "grid" ? VIEWPORT_PX : 0;
    },
  });
});

afterEach(() => {
  cleanup();
  if (offsetHeight !== undefined) {
    Object.defineProperty(HTMLElement.prototype, "offsetHeight", offsetHeight);
  }
});

function bodyRows(grid: HTMLElement): HTMLElement[] {
  return Array.from(grid.querySelectorAll<HTMLElement>("[role='row']")).filter(
    (row) => row.getAttribute("aria-rowindex") !== "1",
  );
}

describe("DS-CMP-10 virtualization", () => {
  it("renders at most 120 body rows of 50,000 and requests pages of 200 near the end", async () => {
    const requests: URL[] = [];
    server.use(
      http.get(apiUrl("/api/v1/contracts"), ({ request }) => {
        const url = new URL(request.url);
        requests.push(url);
        const page = Number((url.searchParams.get("cursor") ?? "p0").slice(1));
        const start = page * PAGE;
        const items = Array.from({ length: PAGE }, (_, index) => ({
          id: `c-${String(start + index)}`,
          external_id: `SF-ORD-${String(start + index).padStart(5, "0")}`,
        }));
        return HttpResponse.json(
          { items, next_cursor: `p${String(page + 1)}` },
          { headers: page === 0 ? { "X-Erev-Total-Count": "50000" } : {} },
        );
      }),
    );
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter>
          <DataGrid
            name="contracts"
            title="Contracts"
            countLabel={(_, formatted) => `${formatted} contracts`}
            columns={COLUMNS}
            source={SOURCE}
            rowKey={(row) => row.id}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const grid = screen.getByRole("grid", { name: "Contracts" });
    await waitFor(() => expect(bodyRows(grid).length).toBeGreaterThan(0));
    expect(grid.getAttribute("aria-rowcount")).toBe("50001");
    expect(bodyRows(grid).length).toBeLessThanOrEqual(120);
    // The count label follows the loading flag in a later commit (F-ADM latent-race sweep).
    expect(await screen.findByText("50,000 contracts")).toBeTruthy();
    expect(requests).toHaveLength(1);
    expect(requests[0]?.searchParams.get("limit")).toBe("200");
    expect(requests[0]?.searchParams.get("count")).toBe("true");
    expect(requests[0]?.searchParams.has("cursor")).toBe(false);

    Object.defineProperty(grid, "scrollTop", {
      configurable: true,
      value: PAGE * ROW_HEIGHT.comfortable - VIEWPORT_PX,
    });
    fireEvent.scroll(grid);

    await waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[1]?.searchParams.get("cursor")).toBe("p1");
    expect(requests[1]?.searchParams.get("limit")).toBe("200");
    await waitFor(() => expect(grid.querySelector("[aria-rowindex='205']")).not.toBeNull());
    const indexes = bodyRows(grid).map((row) => Number(row.getAttribute("aria-rowindex")));
    expect(indexes.length).toBeLessThanOrEqual(120);
    expect(Math.min(...indexes)).toBeGreaterThan(150);
    expect(grid.getAttribute("aria-rowcount")).toBe("50001");
    expect(requests).toHaveLength(2);
  });
});
