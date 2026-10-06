// @vitest-environment jsdom
// Column chooser (DESIGN_SYSTEM DS-CMP-10 "Column chooser"; WCAG 2.2 SC 2.5.7 Dragging Movements): the buttons
// Move up and Move down reorder columns without dragging, visibility checkboxes hide columns, and Reset to
// view default restores the saved view's columns.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ColumnChooser, type ColumnLayout } from "./ColumnChooser";

const COLUMNS = [
  { id: "contract", label: "Contract" },
  { id: "customer", label: "Customer" },
  { id: "status", label: "Status" },
];

const VIEW_DEFAULT: ColumnLayout = {
  order: ["contract", "customer", "status"],
  hidden: ["status"],
};

afterEach(() => {
  cleanup();
});

function Harness({ onChange }: { readonly onChange: (layout: ColumnLayout) => void }) {
  const [layout, setLayout] = useState<ColumnLayout>({
    order: ["contract", "customer", "status"],
    hidden: [],
  });
  return (
    <ColumnChooser
      columns={COLUMNS}
      layout={layout}
      defaultLayout={VIEW_DEFAULT}
      onChange={(next) => {
        onChange(next);
        setLayout(next);
      }}
    />
  );
}

function openChooser(): HTMLElement {
  fireEvent.click(screen.getByRole("button", { name: "Columns" }));
  return screen.getByRole("dialog", { name: "Columns" });
}

function labels(dialog: HTMLElement): (string | null | undefined)[] {
  return within(dialog)
    .getAllByRole("checkbox")
    .map((checkbox) => (checkbox as HTMLInputElement).labels?.[0]?.textContent);
}

function button(dialog: HTMLElement, column: string, name: string): HTMLElement {
  return within(within(dialog).getByRole("group", { name: column })).getByRole("button", { name });
}

describe("column chooser", () => {
  it("the buttons Move up and Move down reorder columns without dragging", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const dialog = openChooser();
    expect(document.activeElement).toBe(
      within(dialog).getByRole("searchbox", { name: "Search columns" }),
    );

    fireEvent.click(button(dialog, "Customer", "Move up"));
    expect(onChange).toHaveBeenLastCalledWith({
      order: ["customer", "contract", "status"],
      hidden: [],
    });
    expect(labels(dialog)).toEqual(["Customer", "Contract", "Status"]);

    const first = button(dialog, "Customer", "Move up");
    expect(first.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(first);
    expect(onChange).toHaveBeenCalledTimes(1);

    fireEvent.click(button(dialog, "Contract", "Move down"));
    expect(labels(dialog)).toEqual(["Customer", "Status", "Contract"]);
    expect(button(dialog, "Contract", "Move down").getAttribute("aria-disabled")).toBe("true");
  });

  it("hides columns and Reset to view default restores the saved view's columns", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const dialog = openChooser();

    fireEvent.click(within(dialog).getByRole("checkbox", { name: "Customer" }));
    expect(onChange).toHaveBeenLastCalledWith({
      order: ["contract", "customer", "status"],
      hidden: ["customer"],
    });
    fireEvent.click(button(dialog, "Status", "Move up"));
    expect(labels(dialog)).toEqual(["Contract", "Status", "Customer"]);

    fireEvent.click(within(dialog).getByRole("button", { name: "Reset to view default" }));
    expect(onChange).toHaveBeenLastCalledWith(VIEW_DEFAULT);
    expect(labels(dialog)).toEqual(["Contract", "Customer", "Status"]);
    expect(
      (within(dialog).getByRole("checkbox", { name: "Status" }) as HTMLInputElement).checked,
    ).toBe(false);
    expect(
      (within(dialog).getByRole("checkbox", { name: "Customer" }) as HTMLInputElement).checked,
    ).toBe(true);

    act(() => {
      fireEvent.keyDown(dialog, { key: "Escape" });
    });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Columns" }));
  });
});
