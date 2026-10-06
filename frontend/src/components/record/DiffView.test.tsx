// @vitest-environment jsdom
// DS-CMP-16 (DESIGN_SYSTEM §7.4; REQ-UX-012): the captioned field diff marks every change in text, N and
// Shift+N move between changes, Mod Enter never submits, and stale requests or viewers without approval
// rights get no decision form.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DiffView, type DiffViewProps, type FieldChange, InlineDiff } from "./DiffView";

afterEach(() => {
  cleanup();
});

const CHANGES: readonly FieldChange[] = [
  {
    id: "endDate",
    field: "End date",
    kind: "changed",
    current: "31 Dec 2026",
    proposed: "30 Jun 2027",
  },
  {
    id: "price",
    field: "Transaction price",
    kind: "changed",
    current: "1,200.00",
    proposed: "1,245.00",
    delta: "+45.00",
  },
  {
    id: "method",
    field: "SSP method",
    kind: "removed",
    current: "Adjusted market",
    proposed: null,
  },
  { id: "range", field: "SSP range", kind: "added", current: null, proposed: "15%" },
  { id: "pattern", field: "Pattern", kind: "changed", current: "Monthly even", proposed: "Daily" },
  { id: "trigger", field: "Trigger", kind: "added", current: null, proposed: "Go-live" },
  { id: "code", field: "Policy code", kind: "unchanged", current: "POL-090", proposed: "POL-090" },
];

const COMMENT = "Checked against the SSP study for FY2026.";

function renderDiff(props: Partial<DiffViewProps> = {}) {
  return render(
    <DiffView
      requestId="APR-2026-0142"
      requestType="Revenue policy change"
      status="Pending approval"
      maker="Dana Whitfield"
      submittedAt="2026-09-07T14:05:00Z"
      canApprove
      changes={CHANGES}
      onDecide={() => undefined}
      {...props}
    />,
  );
}

function table(): HTMLElement {
  return screen.getByRole("table", { name: "Proposed changes (6)" });
}

function changeRows(): HTMLElement[] {
  return Array.from(table().querySelectorAll<HTMLElement>("tbody tr"));
}

describe("DS-CMP-16", () => {
  it("the field diff table has the caption Proposed changes (6) and hides unchanged fields", () => {
    renderDiff();
    expect(table().querySelector("caption")?.textContent).toBe("Proposed changes (6)");
    expect(changeRows()).toHaveLength(6);
    fireEvent.click(screen.getByRole("switch", { name: "Show unchanged fields" }));
    expect(changeRows()).toHaveLength(7);
    expect(screen.getByRole("columnheader", { name: "Delta" })).toBeTruthy();
  });

  it("changed rows carry a marker glyph and the screen-reader prefixes", () => {
    renderDiff();
    const byField = (field: string) => {
      const row = within(table()).getByRole("rowheader", { name: field }).closest("tr");
      if (row === null) {
        throw new Error(`No row for ${field}`);
      }
      return row;
    };
    const expectations = [
      ["SSP method", "−", "Removed:"],
      ["SSP range", "+", "Added:"],
      ["End date", "~", "Changed:"],
    ] as const;
    for (const [field, glyph, prefix] of expectations) {
      const cell = byField(field).querySelector("td");
      const marker = cell?.querySelector("[aria-hidden='true']");
      expect(marker?.textContent).toBe(glyph);
      expect(within(cell as HTMLElement).getByText(prefix).className).toContain("sr-only");
    }
    expect(byField("SSP method").className).toContain("bg-diff-removed-bg");
    expect(byField("SSP range").className).toContain("bg-diff-added-bg");
  });

  it("N and Shift+N move between changes, but not while typing", () => {
    renderDiff();
    const rows = changeRows();
    fireEvent.keyDown(document.body, { key: "n" });
    expect(document.activeElement).toBe(rows[0]);
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "n" });
    expect(document.activeElement).toBe(rows[1]);
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "N", shiftKey: true });
    expect(document.activeElement).toBe(rows[0]);

    const comment = screen.getByRole("textbox", { name: "Comment (required)" });
    comment.focus();
    fireEvent.keyDown(comment, { key: "n" });
    expect(document.activeElement).toBe(comment);
  });

  it("Mod Enter in the comment does not submit; Approve does", () => {
    const onDecide = vi.fn();
    renderDiff({ onDecide });
    const comment = screen.getByRole("textbox", { name: "Comment (required)" });
    fireEvent.change(comment, { target: { value: COMMENT } });
    fireEvent.keyDown(comment, { key: "Enter", metaKey: true });
    fireEvent.keyDown(comment, { key: "Enter", ctrlKey: true });
    expect(onDecide).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(onDecide).toHaveBeenCalledWith("approve", COMMENT);
  });

  it("a decision without a valid comment shows the error and focuses the comment", () => {
    const onDecide = vi.fn();
    renderDiff({ onDecide });
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    const comment = screen.getByRole("textbox", { name: "Comment (required)" });
    expect(document.activeElement).toBe(comment);
    expect(comment.getAttribute("aria-invalid")).toBe("true");
    expect(onDecide).not.toHaveBeenCalled();
  });

  it("Reject asks for confirmation before deciding", () => {
    const onDecide = vi.fn();
    renderDiff({ onDecide });
    fireEvent.change(screen.getByRole("textbox", { name: "Comment (required)" }), {
      target: { value: COMMENT },
    });
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(onDecide).not.toHaveBeenCalled();
    const dialog = screen.getByRole("alertdialog", { name: "Reject this request?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Reject" }));
    expect(onDecide).toHaveBeenCalledWith("reject", COMMENT);
  });

  it("the stale state removes the decision form and shows the banner", () => {
    renderDiff({ status: "Stale" });
    expect(
      screen.getByText(
        "The record changed after this request was submitted. The maker must resubmit it.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Stale")).toBeTruthy();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
  });

  it("without approval rights the form is replaced by the rights statement", () => {
    renderDiff({ canApprove: false });
    expect(screen.getByText("You do not have approval rights for this request type.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
  });

  it("the maker sees the separation-of-duties notice and no decision buttons", () => {
    renderDiff({ viewerIsMaker: true });
    expect(
      screen.getByText("You submitted this request. Another approver must review it."),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
  });

  it("the inline variant states the change in text", () => {
    render(<InlineDiff field="End date" current="31 Dec 2026" proposed="30 Jun 2027" />);
    expect(
      screen.getByText("End date: 31 Dec 2026 → 30 Jun 2027").getAttribute("aria-hidden"),
    ).toBe("true");
    expect(screen.getByText("End date changed from 31 Dec 2026 to 30 Jun 2027")).toBeTruthy();
  });
});
