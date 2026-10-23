// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, expect, it, vi } from "vitest";

import type { Contract } from "../../../lib/api/queries/contracts";
import type { Obligation } from "../../../lib/api/queries/obligations";
import { renderWithApp } from "../../../test/app";
import { judgementRecord } from "../../../test/modifications";
import { apiUrl, installMswServer, server } from "../../../test/msw";
import { refusedWith } from "../../../test/refusals";
import { workbenchContract, workbenchObligation } from "../../../test/workbench";
import { LessorAssessmentDrawer } from "./lessor-assessment";

installMswServer();
afterEach(cleanup);
const contract = workbenchContract() as unknown as Contract;
const obligations = [
  workbenchObligation({ obligation_key: "SERVICE", scope_flag: "IN_SCOPE_606" }),
  workbenchObligation({ obligation_key: "LEASE", scope_flag: "LEASE_842" }),
] as unknown as Obligation[];

function select(scope: HTMLElement, name: string, value: string) {
  const trigger = within(scope).getByRole("combobox", { name });
  fireEvent.click(trigger);
  const list = document.getElementById(trigger.getAttribute("aria-controls") ?? "");
  if (!list) throw new Error("Select did not open");
  fireEvent.mouseDown(within(list).getByRole("option", { name: value }));
}

it("requires explicit assessments and retries submission without a second create", async () => {
  const created = vi.fn();
  const submitted = vi.fn();
  const closed = vi.fn();
  server.use(
    http.get(apiUrl("/api/v1/judgements"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.post(apiUrl("/api/v1/judgements"), async ({ request }) => {
      created(await request.json());
      return HttpResponse.json({ id: "assessment-1" }, { status: 201 });
    }),
    http.post(apiUrl("/api/v1/judgements/assessment-1/submit"), () => {
      submitted();
      return submitted.mock.calls.length === 1
        ? refusedWith({}, { status: 422 })
        : HttpResponse.json({ id: "assessment-1", status: "SUBMITTED" });
    }),
  );
  renderWithApp(
    <LessorAssessmentDrawer
      contract={contract}
      obligations={obligations}
      canAuthor
      onClose={closed}
    />,
  );
  const dialog = await screen.findByRole("dialog", { name: "Lease combination assessment" });
  const submit = within(dialog).getByRole("button", { name: "Submit assessment for review" });
  fireEvent.click(submit);
  expect(created).not.toHaveBeenCalled();
  await waitFor(() =>
    expect(
      within(dialog).getByRole("combobox", { name: "Nonlease component" }).matches(":disabled"),
    ).toBe(false),
  );
  select(dialog, "Nonlease component", "SERVICE");
  select(dialog, "Associated lease component", "LEASE");
  fireEvent.change(within(dialog).getByLabelText(/Underlying asset class/), {
    target: { value: "Equipment" },
  });
  fireEvent.change(within(dialog).getByLabelText(/Assessment rationale/), {
    target: { value: "Equipment predominates; timing is the same." },
  });
  const questions = [
    "Do the components have the same timing and pattern of transfer?",
    "Would the separate lease be classified as an operating lease?",
    "Do the nonlease components predominate in the combined component?",
  ];
  for (const [index, question] of questions.entries()) {
    const group = within(dialog).getByRole("group", { name: question });
    fireEvent.click(within(group).getByRole("radio", { name: index === 2 ? "No" : "Yes" }));
  }
  fireEvent.click(submit);
  await waitFor(() => expect(submitted).toHaveBeenCalledTimes(1));
  expect(closed).not.toHaveBeenCalled();
  expect(
    within(dialog)
      .getByLabelText(/Underlying asset class/)
      .matches(":disabled"),
  ).toBe(true);
  expect(created.mock.calls[0]?.[0]).toMatchObject({
    topic: "OTHER",
    subject_type: "contract",
    subject_id: contract.id,
    book: "ASC606",
    questionnaire: {
      obligation_key: "SERVICE",
      lessor_lease_obligation_key: "LEASE",
      lessor_same_transfer_pattern: true,
      lessor_operating_lease: true,
      lessor_nonlease_predominates: false,
    },
  });
  fireEvent.click(submit);
  await waitFor(() => expect(closed).toHaveBeenCalledTimes(1));
  expect(created).toHaveBeenCalledTimes(1);
  expect(submitted).toHaveBeenCalledTimes(2);
});

it("shows retained eligibility evidence without authoring controls for readers", async () => {
  server.use(
    http.get(apiUrl("/api/v1/judgements"), () =>
      HttpResponse.json({
        items: [
          judgementRecord({
            topic: "OTHER",
            status: "REVIEWED",
            rationale: "Original reviewed rationale",
            questionnaire: {
              obligation_key: "SERVICE",
              lessor_lease_obligation_key: "LEASE",
              lessor_asset_class: "Equipment",
              lessor_same_transfer_pattern: true,
              lessor_operating_lease: true,
              lessor_nonlease_predominates: false,
            },
          }),
        ],
        next_cursor: null,
      }),
    ),
  );
  renderWithApp(
    <LessorAssessmentDrawer
      contract={contract}
      obligations={[]}
      canAuthor={false}
      onClose={() => undefined}
    />,
  );
  expect(await screen.findByText("Original reviewed rationale")).not.toBeNull();
  expect(screen.queryByRole("button", { name: "Submit assessment for review" })).toBeNull();
  expect(screen.getByText("SERVICE → LEASE")).not.toBeNull();
  expect(
    screen.getByText("Do the nonlease components predominate in the combined component?: No"),
  ).not.toBeNull();
});
