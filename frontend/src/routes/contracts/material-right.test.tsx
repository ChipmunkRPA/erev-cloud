// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, expect, it, vi } from "vitest";

import type { Contract } from "../../lib/api/queries/contracts";
import type { Obligation } from "../../lib/api/queries/obligations";
import { registerCurrencies } from "../../lib/format";
import { renderWithApp } from "../../test/app";
import { estimateRow, versionRow } from "../../test/estimates";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { CONTRACT_ID, O1_ID, workbenchContract, workbenchObligation } from "../../test/workbench";
import { MaterialRightDrawer, MaterialRightPanel } from "./material-right";

installMswServer();
afterEach(cleanup);
const contract = (status = "DRAFT") =>
  workbenchContract({ status, head_stream_version: 7 }) as unknown as Contract;
const obligation = (status?: string) =>
  workbenchObligation({
    obligation_kind: "MATERIAL_RIGHT",
    material_right:
      status === undefined
        ? null
        : {
            option_type: "DISCOUNT_VOUCHER",
            ssp_method: "ENTERED_AMOUNT",
            status,
            status_date: null,
            expiry_date: "2026-09-12",
            incremental_discount_ratio: null,
            expected_purchase_amount: null,
            likelihood_estimate_id: null,
          },
  }) as unknown as Obligation;
const path = `/api/v1/obligations/${O1_ID}`;
async function choose(label: string, option: string) {
  fireEvent.click(await screen.findByRole("combobox", { name: label }));
  fireEvent.mouseDown(await screen.findByRole("option", { name: option }));
}

it.each([
  ["DRAFT", undefined, true, true, "Enter option terms"],
  ["ACTIVE", "OPEN", true, true, "Record option expiry"],
  ["ACTIVE", "EXPIRED", true, true, null],
  ["DRAFT", undefined, false, false, null],
  ["ACTIVE", "OPEN", false, false, null],
  ["COMPLETED", "OPEN", true, true, null],
  ["PENDING_REVIEW", undefined, true, true, null],
] as const)(
  "offers commands only for permitted %s/%s state",
  (state, status, canCreate, canExpire, action) => {
    renderWithApp(
      <MaterialRightPanel
        contract={contract(state)}
        obligation={obligation(status)}
        canCreate={canCreate}
        canExpire={canExpire}
      />,
    );
    if (action === null) expect(screen.queryByRole("button")).toBeNull();
    else expect(screen.getByRole("button", { name: action })).toBeTruthy();
  },
);

it("sends native terms with the parent stream and idempotency key", async () => {
  const received = vi.fn();
  const close = vi.fn();
  server.use(
    http.post(apiUrl(`${path}/material-right`), async ({ request }) => {
      received(
        await request.json(),
        request.headers.get("if-match"),
        request.headers.get("idempotency-key"),
      );
      return HttpResponse.json(obligation("OPEN").material_right, { status: 201 });
    }),
  );
  renderWithApp(
    <MaterialRightDrawer
      contract={contract()}
      obligation={obligation()}
      mode="create"
      onClose={close}
    />,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Save option terms" }));
  await waitFor(() => expect(close).toHaveBeenCalledOnce());
  expect(received).toHaveBeenCalledWith(
    {
      option_type: "DISCOUNT_VOUCHER",
      ssp_method: "ENTERED_AMOUNT",
      expiry_date: null,
      is_discount_available_without_contract: false,
    },
    '"s7"',
    expect.any(String),
  );
});

it("sends exact decimal inputs and only offers applicable approved likelihoods", async () => {
  const selected = estimateRow({
    estimate_kind: "EXERCISE_LIKELIHOOD",
    element_code: "OPTION-L",
    current_version: versionRow({ version_no: 1, status: "APPROVED" }),
  });
  server.use(
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/estimates`), () =>
      HttpResponse.json({
        items: [
          selected,
          estimateRow({
            id: "foreign",
            estimate_kind: "EXERCISE_LIKELIHOOD",
            element_code: "OTHER-OBLIGATION",
            obligation_id: "other",
            current_version: selected.current_version,
          }),
          estimateRow({
            id: "draft",
            estimate_kind: "EXERCISE_LIKELIHOOD",
            element_code: "UNAPPROVED",
          }),
        ],
        next_cursor: null,
        count: 3,
      }),
    ),
  );
  const received = vi.fn();
  server.use(
    http.post(apiUrl(`${path}/material-right`), async ({ request }) => {
      received(await request.json());
      return HttpResponse.json(obligation("OPEN").material_right, { status: 201 });
    }),
  );
  renderWithApp(
    <MaterialRightDrawer
      contract={contract()}
      obligation={obligation()}
      mode="create"
      onClose={vi.fn()}
    />,
  );
  await choose("SSP method", "Discount times likelihood");
  fireEvent.change(screen.getByLabelText(/^Incremental discount ratio/), {
    target: { value: "0.500000000000000001" },
  });
  fireEvent.change(screen.getByLabelText(/^Expected purchase amount/), {
    target: { value: "100.00" },
  });
  fireEvent.click(screen.getByRole("combobox", { name: "Approved exercise-likelihood estimate" }));
  expect(await screen.findByRole("option", { name: "OPTION-L" })).toBeTruthy();
  expect(screen.queryByRole("option", { name: "OTHER-OBLIGATION" })).toBeNull();
  expect(screen.queryByRole("option", { name: "UNAPPROVED" })).toBeNull();
  fireEvent.mouseDown(screen.getByRole("option", { name: "OPTION-L" }));
  fireEvent.click(await screen.findByRole("button", { name: "Save option terms" }));
  await waitFor(() => expect(received).toHaveBeenCalledOnce());
  expect(received.mock.calls[0]?.[0]).toMatchObject({
    incremental_discount_ratio: "0.500000000000000001",
    expected_purchase_amount: { amount: "100.00", currency: "USD" },
    likelihood_estimate_id: selected.id,
  });
});

it("keeps expiry inputs on a stale-stream refusal and sends no request without a reason", async () => {
  const received = vi.fn();
  const close = vi.fn();
  server.use(
    http.post(apiUrl(`${path}/expire-material-right`), async ({ request }) => {
      received(await request.json(), request.headers.get("if-match"));
      return problemResponse("precondition-failed", 412, "Record changed");
    }),
  );
  renderWithApp(
    <MaterialRightDrawer
      contract={contract("ACTIVE")}
      obligation={obligation("OPEN")}
      mode="expire"
      onClose={close}
    />,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Record option expiry" }));
  expect(received).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText(/^Effective date/), { target: { value: "2026-09-12" } });
  fireEvent.change(screen.getByLabelText(/^Reason for expiry/), {
    target: { value: "Unused option expired." },
  });
  fireEvent.click(await screen.findByRole("button", { name: "Record option expiry" }));
  await waitFor(() => expect(received).toHaveBeenCalledOnce());
  expect(received).toHaveBeenCalledWith(
    { effective_date: "2026-09-12", comment: "Unused option expired.", evidence_file_ids: [] },
    '"s7"',
  );
  expect(close).not.toHaveBeenCalled();
  expect((screen.getByLabelText(/^Reason for expiry/) as HTMLTextAreaElement).value).toBe(
    "Unused option expired.",
  );
  expect(
    await screen.findByText("This record changed. Reload to see the latest version."),
  ).toBeTruthy();
});

it("restricts renewal-alternative terms to renewal options", async () => {
  const received = vi.fn();
  server.use(
    http.post(apiUrl(`${path}/material-right`), async ({ request }) => {
      received(await request.json());
      return HttpResponse.json(obligation("OPEN").material_right, { status: 201 });
    }),
  );
  renderWithApp(
    <MaterialRightDrawer
      contract={contract()}
      obligation={obligation()}
      mode="create"
      onClose={vi.fn()}
    />,
  );
  await choose("SSP method", "Renewal alternative");
  expect(screen.getByRole("combobox", { name: "Option type" }).textContent).toBe("Renewal option");
  fireEvent.click(screen.getByRole("button", { name: "Save option terms" }));
  await waitFor(() => expect(received).toHaveBeenCalledOnce());
  expect(received.mock.calls[0]?.[0]).toMatchObject({
    option_type: "RENEWAL_OPTION",
    ssp_method: "RENEWAL_ALTERNATIVE",
  });
  expect(received.mock.calls[0]?.[0]).not.toHaveProperty("likelihood_estimate_id");
});

it.each(["SUCCEEDED", "FAILED"])(
  "keeps queued expiry visible through %s without offering a duplicate",
  async (state) => {
    const jobId = "c6c6c6c6-c6c6-4c6c-8c6c-c6c6c6c6c6c6";
    const close = vi.fn();
    server.use(
      http.post(apiUrl(`${path}/expire-material-right`), () =>
        HttpResponse.json({}, { status: 202, headers: { Location: `/api/v1/jobs/${jobId}` } }),
      ),
      http.get(apiUrl(`/api/v1/jobs/${jobId}`), () =>
        HttpResponse.json({
          id: jobId,
          kind: "CONTRACT_COMPUTE",
          state,
          progress: { done: 1, total: 1 },
          result: null,
          problem: null,
          created_by: { kind: "SYSTEM", id: null, display_name: "System" },
          created_at: "2026-09-12T12:00:00Z",
          started_at: "2026-09-12T12:00:00Z",
          finished_at: "2026-09-12T12:00:01Z",
        }),
      ),
    );
    renderWithApp(
      <MaterialRightDrawer
        contract={contract("ACTIVE")}
        obligation={obligation("OPEN")}
        mode="expire"
        onClose={close}
      />,
    );
    fireEvent.change(await screen.findByLabelText(/^Effective date/), {
      target: { value: "2026-09-12" },
    });
    fireEvent.change(screen.getByLabelText(/^Reason for expiry/), {
      target: { value: "Unused option expired." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Record option expiry" }));
    expect(
      await screen.findByText(
        state === "SUCCEEDED"
          ? "Option computation completed."
          : "Expiry computation needs attention",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Record option expiry" })).toBeNull();
    expect(close).not.toHaveBeenCalled();
    expect(screen.queryByText(/Nothing was committed/)).toBeNull();
  },
);

it("shows stored terms and links their likelihood evidence for a read-only viewer", () => {
  registerCurrencies([{ code: "USD", minor_unit: 2 }]);
  const item = obligation("OPEN");
  if (item.material_right === null) throw new Error("Option fixture missing terms");
  item.material_right.ssp_method = "DISCOUNT_X_LIKELIHOOD";
  item.material_right.likelihood_estimate_id = "e1e1e1e1-e1e1-4e1e-8e1e-e1e1e1e1e1e1";
  item.material_right.incremental_discount_ratio = "0.5";
  item.material_right.expected_purchase_amount = "100.00";
  renderWithApp(
    <MaterialRightPanel
      contract={contract("ACTIVE")}
      obligation={item}
      canCreate={false}
      canExpire={false}
    />,
  );
  expect(screen.getByText("Discount times likelihood")).toBeTruthy();
  expect(screen.getByText("0.5")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Open likelihood estimate" }).getAttribute("href")).toBe(
    `/contracts/${CONTRACT_ID}/estimates/${item.material_right.likelihood_estimate_id}`,
  );
  expect(screen.queryByRole("button")).toBeNull();
});
