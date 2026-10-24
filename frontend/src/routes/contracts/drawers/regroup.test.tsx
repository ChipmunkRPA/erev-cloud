// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, expect, it, vi } from "vitest";
import type { Contract } from "../../../lib/api/queries/contracts";
import type { Obligation } from "../../../lib/api/queries/obligations";
import { renderWithApp } from "../../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import { workbenchContract, workbenchObligation } from "../../../test/workbench";
import { RegroupDrawer } from "./regroup";

installMswServer();
afterEach(cleanup);
const contract = workbenchContract({ status: "DRAFT" }) as unknown as Contract;
const obligations = [workbenchObligation()] as unknown as readonly Obligation[];

async function fill() {
  const input = await screen.findByRole("combobox", { name: "Lines to move" });
  fireEvent.focus(input);
  fireEvent.keyDown(input, { key: "ArrowDown" });
  fireEvent.mouseDown(await screen.findByRole("option", { name: /O1/ }));
  fireEvent.change(screen.getByLabelText(/^Comment/), {
    target: { value: "Separate draft order." },
  });
}

it("moves selected original keys to a new draft using an idempotent command", async () => {
  const onClose = vi.fn();
  const sent: unknown[] = [];
  server.use(
    http.post(apiUrl(`/api/v1/contracts/${contract.id}/regroup`), async ({ request }) => {
      expect(request.headers.get("Idempotency-Key")).toBeTruthy();
      sent.push(await request.json());
      return HttpResponse.json({ modification_ids: ["out", "in"] }, { status: 201 });
    }),
  );
  renderWithApp(<RegroupDrawer contract={contract} obligations={obligations} onClose={onClose} />);
  fireEvent.click(screen.getByRole("button", { name: "Move lines" }));
  expect(sent).toEqual([]);
  await fill();
  fireEvent.click(screen.getByRole("button", { name: "Move lines" }));
  await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
  expect(sent).toEqual([{ obligation_keys: ["O1"], comment: "Separate draft order." }]);
});

it("keeps the selection and comment when the server refuses a now-posted contract", async () => {
  const onClose = vi.fn();
  server.use(
    http.post(apiUrl(`/api/v1/contracts/${contract.id}/regroup`), () =>
      problemResponse("invalid-transition", 409, "Action not available in this state", {
        detail: "The contract has posted.",
        errors: [
          {
            field: "status",
            message: "The contract has posted.",
            row: null,
            rule_id: "DB-03",
            sheet: null,
          },
        ],
      }),
    ),
  );
  renderWithApp(<RegroupDrawer contract={contract} obligations={obligations} onClose={onClose} />);
  await fill();
  fireEvent.click(screen.getByRole("button", { name: "Move lines" }));
  await screen.findByText("The contract has posted.");
  expect(onClose).not.toHaveBeenCalled();
  expect((screen.getByLabelText(/^Comment/) as HTMLTextAreaElement).value).toBe(
    "Separate draft order.",
  );
});
