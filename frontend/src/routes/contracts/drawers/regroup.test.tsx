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

it("loads further target pages, excludes ineligible drafts, and submits the selected target", async () => {
  const targetId = "7e8f90a1-b2c3-4d4e-8f5a-6b7c8d9e0f1a";
  const onClose = vi.fn();
  const sent: unknown[] = [];
  server.use(
    http.get(apiUrl("/api/v1/currencies"), () =>
      HttpResponse.json({
        items: [
          { code: "USD", minor_unit: 2, name: "US Dollar", numeric_code: "840", is_active: true },
          {
            code: "GBP",
            minor_unit: 2,
            name: "Pound Sterling",
            numeric_code: "826",
            is_active: true,
          },
        ],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/contracts"), ({ request }) => {
      const cursor = new URL(request.url).searchParams.get("cursor");
      return HttpResponse.json({
        items: cursor
          ? [workbenchContract({ id: targetId, external_id: "TARGET", status: "DRAFT" })]
          : [
              contract,
              workbenchContract({ id: "active", external_id: "ACTIVE", status: "ACTIVE" }),
              workbenchContract({
                id: "foreign",
                external_id: "FOREIGN",
                status: "DRAFT",
                transaction_currency: "GBP",
              }),
            ],
        next_cursor: cursor ? null : "next",
      });
    }),
    http.post(apiUrl(`/api/v1/contracts/${contract.id}/regroup`), async ({ request }) => {
      sent.push(await request.json());
      return HttpResponse.json({ modification_ids: ["out", "in"] }, { status: 201 });
    }),
  );
  renderWithApp(<RegroupDrawer contract={contract} obligations={obligations} onClose={onClose} />);
  await fill();
  fireEvent.click(screen.getByRole("radio", { name: "Existing draft contract" }));
  fireEvent.click(await screen.findByRole("button", { name: "Load more draft contracts" }));
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: "Load more draft contracts" })).toBeNull(),
  );
  const target = screen.getByRole("combobox", { name: "Target contract" });
  fireEvent.keyDown(target, { key: "ArrowDown" });
  expect(screen.queryByRole("option", { name: "ACTIVE" })).toBeNull();
  expect(screen.queryByRole("option", { name: "FOREIGN" })).toBeNull();
  fireEvent.mouseDown(await screen.findByRole("option", { name: "TARGET" }));
  fireEvent.click(screen.getByRole("button", { name: "Move lines" }));
  await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
  expect(sent).toEqual([
    { obligation_keys: ["O1"], comment: "Separate draft order.", target_contract_id: targetId },
  ]);
});

it.each([null, "2026-09-01"])(
  "prepares an active transfer with date %s and links both modifications",
  async (effectiveDate) => {
    const active = workbenchContract({ status: "ACTIVE" }) as unknown as Contract;
    const targetId = "7e8f90a1-b2c3-4d4e-8f5a-6b7c8d9e0f1a";
    const onClose = vi.fn();
    const sent: unknown[] = [];
    server.use(
      http.get(apiUrl("/api/v1/currencies"), () =>
        HttpResponse.json({
          items: [
            { code: "USD", minor_unit: 2, name: "US Dollar", numeric_code: "840", is_active: true },
          ],
        }),
      ),
      http.get(apiUrl("/api/v1/contracts"), ({ request }) => {
        expect(new URL(request.url).searchParams.getAll("status")).toContain("ACTIVE");
        return HttpResponse.json({
          items: [
            workbenchContract({ id: targetId, external_id: "ACTIVE-TARGET", status: "ACTIVE" }),
            workbenchContract({ id: "draft", external_id: "DRAFT-TARGET", status: "DRAFT" }),
          ],
          next_cursor: null,
        });
      }),
      http.post(apiUrl(`/api/v1/contracts/${active.id}/regroup`), async ({ request }) => {
        sent.push(await request.json());
        return HttpResponse.json({ modification_ids: ["out", "in"] }, { status: 201 });
      }),
    );
    renderWithApp(<RegroupDrawer contract={active} obligations={obligations} onClose={onClose} />);
    expect(screen.queryByRole("radio", { name: "New draft contract" })).toBeNull();
    await fill();
    const target = screen.getByRole("combobox", { name: "Target contract" });
    fireEvent.keyDown(target, { key: "ArrowDown" });
    fireEvent.mouseDown(await screen.findByRole("option", { name: "ACTIVE-TARGET" }));
    expect(screen.queryByRole("option", { name: "DRAFT-TARGET" })).toBeNull();
    if (effectiveDate) {
      fireEvent.change(screen.getByLabelText(/Effective date/), { target: { value: "invalid" } });
      fireEvent.click(screen.getByRole("button", { name: "Prepare paired modifications" }));
      expect(sent).toEqual([]);
      fireEvent.change(screen.getByLabelText(/Effective date/), {
        target: { value: effectiveDate },
      });
    }
    fireEvent.click(screen.getByRole("button", { name: "Prepare paired modifications" }));
    const sourceLink = await screen.findByRole("link", { name: "Review source modification" });
    expect(sourceLink.getAttribute("href")).toBe(`/contracts/${active.id}/modifications/out`);
    expect(
      screen.getByRole("link", { name: "Review target modification" }).getAttribute("href"),
    ).toBe(`/contracts/${targetId}/modifications/in`);
    expect(sent).toEqual([
      {
        obligation_keys: ["O1"],
        target_contract_id: targetId,
        comment: "Separate draft order.",
        ...(effectiveDate ? { effective_date: effectiveDate } : {}),
      },
    ]);
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Prepare paired modifications" })).toBeNull();
  },
);
