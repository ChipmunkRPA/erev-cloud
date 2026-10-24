// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { registerCurrencies } from "../../lib/format";
import { emptyChange, emptyChangeLine } from "../../lib/forms/modification";
import { ChangeStep } from "./modification-change";

afterEach(cleanup);

it.each(["QUANTITY_CHANGE", "TERM_CHANGE"] as const)(
  "requires explicit %s continuation and clears the assessment after changing its date",
  (kind) => {
    registerCurrencies([{ code: "USD", minor_unit: 2 }]);
    const saved = vi.fn();
    render(
      <ChangeStep
        formId="quantity-change"
        variant={{
          kind: "general",
          initial: {
            ...emptyChange("l1", kind),
            reference: "CONTINUE-1",
            effectiveDate: "01 Oct 2026",
            lines: (kind === "TERM_CHANGE" ? ["LEASE", "O1"] : ["LEASE"]).map((key, index) => ({
              ...emptyChangeLine(String(index)),
              action: "CHANGE" as const,
              obligationKey: key,
              quantityChange: kind === "TERM_CHANGE" ? "" : "1",
              endDate: kind === "TERM_CHANGE" ? "2027-06-30" : "",
            })),
          },
        }}
        context={{
          externalId: "C1",
          currency: "USD",
          obligations: [{ key: "O1", productCode: "SERVICE", endDate: null }],
          priceOnlyObligationKeys: ["LEASE"],
          combinedUnitHosts: [{ host: "O1", members: ["O1", "LEASE"] }],
        }}
        obligationChoices={[]}
        products={[]}
        entities={[]}
        latestEvent={null}
        problem={null}
        busy={false}
        onDirty={() => {}}
        onBuilt={saved}
      />,
    );
    const form = document.getElementById("quantity-change");
    if (form === null) throw new Error("Missing change form");
    fireEvent.submit(form);
    expect(saved).not.toHaveBeenCalled();
    const confirmation = screen.getByRole("checkbox", { name: /all original members continue/ });
    fireEvent.click(confirmation);
    fireEvent.submit(form);
    expect(saved).toHaveBeenCalledWith(
      expect.objectContaining({
        questionnaire: {
          combined_reassessment: {
            O1: expect.objectContaining({
              effective_date: "2026-10-01",
              component_keys: ["O1", "LEASE"],
            }),
          },
        },
      }),
    );
    saved.mockClear();
    fireEvent.change(screen.getByRole("textbox", { name: /^Effective date/ }), {
      target: { value: "02 Oct 2026" },
    });
    expect((confirmation as HTMLInputElement).checked).toBe(false);
    fireEvent.submit(form);
    expect(saved).not.toHaveBeenCalled();
  },
);
