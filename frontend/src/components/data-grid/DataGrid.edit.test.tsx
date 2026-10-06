// @vitest-environment jsdom
// Inline editing for drafts only (DESIGN_SYSTEM DS-CMP-10 "Inline editing"; D-60): editing exists only when
// the grid receives `editable`; a save shows a 12 px spinner until the API confirms; a refused or invalid
// value keeps the typed text and sets aria-invalid with the message as the description.
import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "../../app/providers";
import type { ListPage } from "../../lib/api/lists";
import { queryKey } from "../../lib/api/query-keys";
import { registerCurrencies } from "../../lib/format";
import { installGridViewport } from "../../test/layout";
import { DataGrid } from "./DataGrid";
import type { EditOutcome, GridColumn } from "./types";

installGridViewport();

interface Draft {
  readonly id: string;
  readonly line: string;
  readonly amount: string;
}

const DRAFTS: readonly Draft[] = [
  { id: "d-1", line: "Platform subscription", amount: "1000.00" },
  { id: "d-2", line: "Implementation services", amount: "2500.00" },
];

type Save = (row: Draft, value: string) => Promise<EditOutcome>;

function columns(save: Save): readonly GridColumn<Draft>[] {
  return [
    { id: "line", header: "Line", kind: "text", value: (row) => row.line },
    {
      id: "amount",
      header: "Amount",
      kind: "money",
      value: (row) => row.amount,
      currency: () => "USD",
      edit: { kind: "decimal", save },
    },
  ];
}

beforeAll(() => {
  registerCurrencies([{ code: "USD", minor_unit: 2 }]);
});

afterEach(() => {
  cleanup();
});

function renderGrid(save: Save, editable: boolean) {
  const fetchPage = vi.fn((): Promise<ListPage<Draft>> =>
    Promise.resolve({ items: DRAFTS, nextCursor: null, total: { count: 2, capped: false } }),
  );
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <DataGrid
          name="lines"
          title="Draft lines"
          countLabel={(_, formatted) => `${formatted} lines`}
          columns={columns(save)}
          source={{ queryKey: queryKey("draft-lines", "tenant"), fetchPage }}
          rowKey={(row) => row.id}
          editable={editable}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchPage;
}

async function amountCell(index: number): Promise<HTMLElement> {
  await screen.findByText("Platform subscription");
  const cell = screen
    .getByRole("grid", { name: "Draft lines" })
    .querySelectorAll<HTMLElement>("[data-column='amount']")[index + 1];
  if (cell === undefined) {
    throw new Error(`No amount cell ${String(index)}`);
  }
  fireEvent.mouseDown(cell);
  act(() => cell.focus());
  return cell;
}

describe("inline editing for drafts only", () => {
  it("editing is available only when the grid receives editable", async () => {
    const save = vi.fn<Save>(() => Promise.resolve({ ok: true }));
    renderGrid(save, false);
    const cell = await amountCell(0);

    fireEvent.keyDown(cell, { key: "Enter" });
    fireEvent.keyDown(cell, { key: "F2" });
    fireEvent.keyDown(cell, { key: "5" });
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(cell.hasAttribute("aria-readonly")).toBe(false);
    cleanup();

    renderGrid(save, true);
    const editable = await amountCell(0);
    expect(
      screen
        .getByText("Platform subscription")
        .closest("[role='gridcell']")
        ?.getAttribute("aria-readonly"),
    ).toBe("true");
    fireEvent.keyDown(editable, { key: "Enter" });
    const input = screen.getByRole("textbox", { name: "Amount" });
    expect((input as HTMLInputElement).value).toBe("1000.00");
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(document.activeElement).toBe(editable);
    expect(save).not.toHaveBeenCalled();
  });

  it("a save shows a 12 px spinner until the API confirms", async () => {
    let confirm: (outcome: EditOutcome) => void = () => undefined;
    const save = vi.fn<Save>(
      () =>
        new Promise<EditOutcome>((resolve) => {
          confirm = resolve;
        }),
    );
    const fetchPage = renderGrid(save, true);
    const cell = await amountCell(0);

    fireEvent.keyDown(cell, { key: "Enter" });
    const input = screen.getByRole("textbox", { name: "Amount" });
    fireEvent.change(input, { target: { value: "1,250.00" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(save).toHaveBeenCalledWith(DRAFTS[0], "1250.00");
    expect(cell.getAttribute("aria-busy")).toBe("true");
    expect(cell.querySelector("svg[data-spinner]")?.getAttribute("width")).toBe("12");
    expect(cell.textContent).toContain("1,250.00");

    await act(async () => {
      confirm({ ok: true });
      await Promise.resolve();
    });
    await waitFor(() => expect(cell.hasAttribute("aria-busy")).toBe(false));
    expect(cell.querySelector("svg[data-spinner]")).toBeNull();
    expect(fetchPage).toHaveBeenCalledTimes(2);
  });

  it("a validation error keeps the typed text and sets aria-invalid", async () => {
    const save = vi.fn<Save>(() =>
      Promise.resolve({ ok: false, message: "The amount is outside the SSP range." }),
    );
    renderGrid(save, true);
    const cell = await amountCell(1);

    fireEvent.keyDown(cell, { key: "F2" });
    const input = screen.getByRole("textbox", { name: "Amount" });
    fireEvent.change(input, { target: { value: "9999.00" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => expect(cell.getAttribute("aria-invalid")).toBe("true"));
    expect(cell.textContent).toContain("9999.00");
    expect(document.getElementById(cell.getAttribute("aria-describedby") ?? "")?.textContent).toBe(
      "The amount is outside the SSP range.",
    );
    expect(screen.getByRole("button", { name: "Next error" })).toBeTruthy();

    const first = await amountCell(0);
    fireEvent.keyDown(first, { key: "F2" });
    fireEvent.change(screen.getByRole("textbox", { name: "Amount" }), {
      target: { value: "12.345" },
    });
    fireEvent.keyDown(screen.getByRole("textbox", { name: "Amount" }), { key: "Enter" });
    expect(save).toHaveBeenCalledTimes(1);
    expect(first.getAttribute("aria-invalid")).toBe("true");
    expect(document.getElementById(first.getAttribute("aria-describedby") ?? "")?.textContent).toBe(
      "Enter at most 2 decimal places.",
    );
    expect(first.textContent).toContain("12.345");
  });
});
