// @vitest-environment jsdom
// DS-CMP-25 (DESIGN_SYSTEM §7.4; DS-COL-23; D-46): a proposal has a dashed edge and a hidden note that it
// is not applied; an uncited figure withholds Accept; an accepted block turns solid with the acceptor
// chip; dismissing needs a reason.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProposalBlock } from "./ProposalBlock";

afterEach(() => {
  cleanup();
});

const SOURCE = "Contract review · 07 Sep 2026 14:05 UTC";
const CITATIONS = [
  { number: 1, label: "Master services agreement, page 3", to: "/documents/d-1?page=3" },
];

function renderInRouter(node: ReactNode) {
  return render(<MemoryRouter>{node}</MemoryRouter>);
}

describe("DS-CMP-25", () => {
  it("a proposed block has a dashed edge and the hidden note", () => {
    renderInRouter(
      <ProposalBlock state="ready" source={SOURCE} citations={CITATIONS} onAccept={() => undefined}>
        <p>Term 36 months.</p>
      </ProposalBlock>,
    );
    const block = screen.getByRole("region", { name: "Proposed" });
    expect(block.getAttribute("data-edge")).toBe("dashed");
    expect(block.className).toContain("border-dashed");
    expect(block.className).toContain("border-proposal-border");
    const note = document.getElementById(block.getAttribute("aria-describedby") ?? "");
    expect(note?.textContent).toBe("AI-generated proposal. Not applied until accepted.");
    expect(note?.className).toContain("sr-only");
    expect(within(block).getByText(SOURCE)).toBeTruthy();
    expect(
      within(block).getByRole("link", { name: "Master services agreement, page 3" }),
    ).toBeTruthy();
    expect(within(block).getByRole("button", { name: "Accept" })).toBeTruthy();
  });

  it("an uncited figure shows the warning chip and no Accept", () => {
    renderInRouter(
      <ProposalBlock
        state="ready"
        source={SOURCE}
        uncitedFigure
        onAccept={() => undefined}
        onEditAndAccept={() => undefined}
      >
        <p>Transaction price USD 120,000.00.</p>
      </ProposalBlock>,
    );
    expect(screen.getByText("Uncited figure").getAttribute("data-tone")).toBe("warning");
    expect(screen.queryByRole("button", { name: "Accept" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit and accept" })).toBeNull();
  });

  it("an accepted block has a solid edge and the chip Accepted by <name>", () => {
    renderInRouter(
      <ProposalBlock
        state="accepted"
        source={SOURCE}
        acceptedBy="Dana Whitfield"
        onAccept={() => undefined}
        onDismiss={() => undefined}
      >
        <p>Term 36 months.</p>
      </ProposalBlock>,
    );
    const block = screen.getByRole("region", { name: "Proposed" });
    expect(block.getAttribute("data-edge")).toBe("solid");
    expect(block.className).not.toContain("border-dashed");
    expect(screen.getByText("Accepted by Dana Whitfield").getAttribute("data-tone")).toBe(
      "positive",
    );
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("proposals without a command offer the copy action instead of Accept", () => {
    const onCopy = vi.fn();
    renderInRouter(
      <ProposalBlock
        state="ready"
        source="Revenue Q&A · 07 Sep 2026 14:05 UTC"
        copy={{ label: "Copy answer", onCopy }}
      >
        <p>Recognized revenue for Sep 2026 is USD 55,440.00 [1].</p>
      </ProposalBlock>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Copy answer" }));
    expect(onCopy).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Accept" })).toBeNull();
  });

  it("dismissing needs a reason", () => {
    const onDismiss = vi.fn();
    renderInRouter(
      <ProposalBlock state="ready" source={SOURCE} onDismiss={onDismiss}>
        <p>Term 36 months.</p>
      </ProposalBlock>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    const dialog = screen.getByRole("dialog", { name: "Dismiss proposal" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Dismiss" }));
    expect(onDismiss).not.toHaveBeenCalled();
    expect(within(dialog).getByText("Enter at least 10 characters.")).toBeTruthy();

    fireEvent.change(within(dialog).getByRole("textbox", { name: "Reason for dismissing" }), {
      target: { value: "The term is stated in the order form." },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Dismiss" }));
    expect(onDismiss).toHaveBeenCalledWith("The term is stated in the order form.");
  });

  it("generating is busy with Cancel, and a failure states that no data changed", () => {
    const { rerender } = renderInRouter(
      <ProposalBlock state="generating" source={SOURCE} onCancel={() => undefined} />,
    );
    expect(screen.getByRole("region", { name: "Proposed" }).getAttribute("aria-busy")).toBe("true");
    expect(screen.getByRole("button", { name: "Cancel" })).toBeTruthy();
    rerender(
      <MemoryRouter>
        <ProposalBlock state="failed" source={SOURCE} />
      </MemoryRouter>,
    );
    expect(
      screen.getByText("The assistant could not produce a proposal. No data was changed."),
    ).toBeTruthy();
  });
});
