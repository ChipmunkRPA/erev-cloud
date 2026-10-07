// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, expect, it, vi } from "vitest";

import type { Contract, PolicyOverride } from "../../../lib/api/queries/contracts";
import type { Obligation } from "../../../lib/api/queries/obligations";
import { renderWithApp } from "../../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import { workbenchContract, workbenchObligation } from "../../../test/workbench";
import { PolicyOverridesDrawer } from "./policy-overrides";

installMswServer();
afterEach(cleanup);
const path = "/api/v1/policy-overrides";
const contract = workbenchContract() as unknown as Contract;
const obligation = workbenchObligation() as unknown as Obligation;
const row: PolicyOverride = {
  id: "01a0ff4f-d9d6-7ee3-9a26-9a68a456e700",
  contract_id: contract.id,
  obligation_id: obligation.id,
  obligation_key: obligation.obligation_key,
  level: "OBLIGATION",
  policy_key: "balance.right_to_consideration",
  value: "UNCONDITIONAL",
  rationale: "Payment is unconditional after delivery.",
  judgement_record_id: null,
  status: "DRAFT",
  content_sha256: null,
  approval_request_id: null,
  approved_at: null,
  supersedes_id: null,
  created_at: "2026-09-12T12:00:00Z",
  updated_at: "2026-09-12T12:00:00Z",
  row_version: 1,
};
function open(canAuthor = true) {
  const closed = vi.fn();
  renderWithApp(
    <PolicyOverridesDrawer
      contract={contract}
      obligations={[obligation]}
      canAuthor={canAuthor}
      onClose={closed}
    />,
  );
  return closed;
}
function select(label: string, option: string) {
  fireEvent.click(screen.getByRole("combobox", { name: label }));
  fireEvent.mouseDown(screen.getByRole("option", { name: option }));
}
function list(rows: PolicyOverride[]) {
  server.use(
    http.get(apiUrl(path), ({ request }) => {
      expect(new URL(request.url).searchParams.get("contract")).toBe(contract.id);
      return HttpResponse.json({ items: rows, next_cursor: null });
    }),
  );
}
it("saves a scoped balance draft, refreshes records and submits without creating again", async () => {
  const rows: PolicyOverride[] = [];
  list(rows);
  const created: unknown[] = [];
  server.use(
    http.post(apiUrl(path), async ({ request }) => {
      const body = await request.json();
      created.push(body);
      rows.push(row);
      return HttpResponse.json(row, { status: 201 });
    }),
    http.post(apiUrl(`${path}/${row.id}/submit`), () => {
      rows[0] = { ...row, status: "SUBMITTED" };
      return HttpResponse.json(rows[0]);
    }),
  );
  const closed = open();
  await screen.findByText("No policy overrides have been saved for this contract.");
  select("Obligation", `${obligation.obligation_key} · ${obligation.product.name}`);
  select("Right to consideration", "Unconditional");
  fireEvent.change(screen.getByLabelText(/Rationale/), { target: { value: row.rationale } });
  fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
  const submit = await screen.findByRole("button", { name: "Submit for approval" });
  expect(created).toEqual([
    {
      contract_id: contract.id,
      policy_key: row.policy_key,
      obligation_key: obligation.obligation_key,
      value: "UNCONDITIONAL",
      rationale: row.rationale,
    },
  ]);
  fireEvent.click(submit);
  await screen.findByText("Submitted");
  expect(created).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(closed).toHaveBeenCalledOnce();
});
it("reopens an existing draft and retries a refused submission without creating a draft", async () => {
  const rows = [row];
  list(rows);
  let submissions = 0;
  const create = vi.fn();
  server.use(
    http.post(apiUrl(path), create),
    http.post(apiUrl(`${path}/${row.id}/submit`), () => {
      submissions += 1;
      if (submissions === 1)
        return problemResponse("validation-failed", 422, "Validation failed", {
          detail: "The linked judgement is no longer reviewed.",
        });
      rows[0] = { ...row, status: "SUBMITTED" };
      return HttpResponse.json(rows[0]);
    }),
  );
  open();
  fireEvent.click(await screen.findByRole("button", { name: "Submit for approval" }));
  await screen.findByText("The linked judgement is no longer reviewed.");
  fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
  await screen.findByText("Submitted");
  expect(submissions).toBe(2);
  expect(create).not.toHaveBeenCalled();
});
it("sends a financing rate as a decimal string at contract scope", async () => {
  list([]);
  const created: unknown[] = [];
  server.use(
    http.post(apiUrl(path), async ({ request }) => {
      created.push(await request.json());
      return HttpResponse.json(row, { status: 201 });
    }),
  );
  open();
  select("Policy", "Significant financing rate");
  expect(screen.queryByRole("combobox", { name: "Obligation" })).toBeNull();
  fireEvent.change(screen.getByLabelText(/Annual rate \(decimal\)/), { target: { value: "0.06" } });
  select("Compounding", "Annual");
  fireEvent.change(screen.getByLabelText(/Rationale/), {
    target: { value: "Inception rate evidence." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
  await waitFor(() => expect(created).toHaveLength(1));
  expect(created[0]).toEqual({
    contract_id: contract.id,
    policy_key: "sfc.discount_rate_basis",
    obligation_key: null,
    value: { basis: "CUSTOMER_CREDIT_RATE", annual_rate: "0.06", compounding: "ANNUAL" },
    rationale: "Inception rate evidence.",
  });
});
it("keeps read-only users out of authoring and renders statuses and values", async () => {
  list([{ ...row, status: "APPROVED", approval_request_id: "approved-request" }]);
  open(false);
  const dialog = await screen.findByRole("dialog", { name: "Policy overrides" });
  await within(dialog).findByText("Approved");
  expect(within(dialog).getByText("Unconditional")).toBeTruthy();
  expect(
    within(dialog).getByRole("link", { name: "View approval request" }).getAttribute("href"),
  ).toBe("/approvals/requests/approved-request");
  expect(within(dialog).queryByRole("button", { name: "Save draft" })).toBeNull();
  expect(within(dialog).queryByRole("button", { name: "Submit for approval" })).toBeNull();
});
it("blocks empty required fields without a command", async () => {
  list([]);
  const create = vi.fn();
  server.use(http.post(apiUrl(path), create));
  open();
  fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
  expect(screen.getAllByText("This field is required.")).toHaveLength(2);
  expect(create).not.toHaveBeenCalled();
});
it("shows a failed list read with a usable retry", async () => {
  let reads = 0;
  server.use(
    http.get(apiUrl(path), () => {
      reads += 1;
      return reads <= 2
        ? problemResponse("forbidden", 403, "Forbidden")
        : HttpResponse.json({ items: [row], next_cursor: null });
    }),
  );
  open(false);
  await screen.findByText("Could not load saved overrides.", {}, { timeout: 4000 });
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await screen.findByText("Draft");
});
