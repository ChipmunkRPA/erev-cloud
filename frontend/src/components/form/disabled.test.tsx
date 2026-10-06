// @vitest-environment jsdom
// DS-CMP-21 "Disabled" (DESIGN_SYSTEM §7.5: "`--bg-subtle` fill, `--fg-disabled` text"): a control a state
// of the page makes unavailable shows its value and takes no input. The select keeps its place in the
// tab order through aria-disabled, so its value can still be read; the date input offers no calendar.
// The page states the reason beside the fields (SCREENS_B §0.5 RV-04 rev 1.98: a lock is the source).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TextField } from "../../routes/contracts/drawers/common";
import { DateInput } from "./DateInput";
import { Field } from "./Field";
import { Select } from "./Select";

afterEach(() => {
  cleanup();
});

const OPTIONS = [
  { value: "CONTRACT", label: "Contract" },
  { value: "OBLIGATION", label: "Obligation" },
  { value: "PRODUCT", label: "Product" },
] as const;

function Rows({
  disabled,
  onChange,
}: {
  readonly disabled: boolean;
  readonly onChange: (value: string) => void;
}) {
  return (
    <Field name="rows" label="Rows">
      {(control) => (
        <Select
          control={control}
          options={OPTIONS}
          value="OBLIGATION"
          onChange={onChange}
          disabled={disabled}
        />
      )}
    </Field>
  );
}

describe("DS-CMP-21 Disabled", () => {
  it("a disabled select shows its value, stays in the tab order and opens for no click or key", () => {
    const onChange = vi.fn();
    render(<Rows disabled onChange={onChange} />);
    const select = screen.getByRole("combobox", { name: "Rows" });
    expect(select.getAttribute("aria-disabled")).toBe("true");
    expect(select.textContent).toBe("Obligation");
    expect(select.tabIndex).toBe(0);
    // The whole class names: every control carries `disabled:` variants of both for a native input.
    expect(select.classList.contains("bg-subtle")).toBe(true);
    expect(select.classList.contains("text-fg-disabled")).toBe(true);

    fireEvent.click(select);
    for (const key of ["ArrowDown", "ArrowUp", "Enter", " ", "Home", "End", "p"]) {
      fireEvent.keyDown(select, { key });
    }
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(select.getAttribute("aria-expanded")).toBe("false");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("the same select, enabled, opens and picks: the state is the property's alone", () => {
    const onChange = vi.fn();
    render(<Rows disabled={false} onChange={onChange} />);
    const select = screen.getByRole("combobox", { name: "Rows" });
    expect(select.getAttribute("aria-disabled")).toBeNull();
    expect(select.classList.contains("text-fg-disabled")).toBe(false);
    fireEvent.click(select);
    expect(screen.getByRole("listbox")).toBeTruthy();
    fireEvent.keyDown(select, { key: "ArrowDown" });
    fireEvent.keyDown(select, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("PRODUCT");
  });

  it("a disabled date input shows its date and offers no calendar", () => {
    const date = (disabled: boolean) => (
      <Field name="from" label="From">
        {(control) => (
          <DateInput control={control} value="01 Aug 2026" onChange={vi.fn()} disabled={disabled} />
        )}
      </Field>
    );
    const view = render(date(true));
    const input = screen.getByRole<HTMLInputElement>("textbox", { name: "From" });
    expect(input.disabled).toBe(true);
    expect(input.value).toBe("01 Aug 2026");
    expect(screen.queryByRole("button", { name: "Choose date" })).toBeNull();

    view.rerender(date(false));
    expect(screen.getByRole<HTMLInputElement>("textbox", { name: "From" }).disabled).toBe(false);
    expect(screen.getByRole("button", { name: "Choose date" })).toBeTruthy();
  });

  it("a disabled text field is the input's own disabled state", () => {
    const field = (disabled: boolean) => (
      <TextField
        name="contract"
        label="Contract"
        value="SF-ORD-10001"
        onChange={vi.fn()}
        disabled={disabled}
      />
    );
    const view = render(field(true));
    const input = screen.getByRole<HTMLInputElement>("textbox", { name: "Contract" });
    expect(input.disabled).toBe(true);
    expect(input.value).toBe("SF-ORD-10001");
    view.rerender(field(false));
    expect(screen.getByRole<HTMLInputElement>("textbox", { name: "Contract" }).disabled).toBe(
      false,
    );
  });

  it("the read-only rule of the control style names the disabled state out", () => {
    // The control style takes the border and the fill from a read-only input, and CSS counts a
    // disabled input as read-only: with the bare rule a disabled text or date field was a label with
    // no box under it (the closed world's captures of 2026-10-02). jsdom computes no such style, so
    // this holds the selector; the browser's own answer is asserted in e2e/projects/closed.spec.ts.
    render(
      <>
        <TextField name="contract" label="Contract" value="" onChange={vi.fn()} disabled />
        <Field name="from" label="From">
          {(control) => <DateInput control={control} value="" onChange={vi.fn()} disabled />}
        </Field>
      </>,
    );
    for (const name of ["Contract", "From"]) {
      const classes = screen.getByRole("textbox", { name }).className.split(/\s+/);
      expect(classes).toContain(
        "[&:is(input,textarea):read-only:not(:disabled)]:border-transparent",
      );
      expect(classes).toContain("[&:is(input,textarea):read-only:not(:disabled)]:bg-transparent");
      expect(
        classes.filter((item) => item.startsWith("[&:is(input,textarea):read-only]:")),
      ).toEqual([]);
      expect(classes).toContain("disabled:bg-subtle");
    }
  });
});
