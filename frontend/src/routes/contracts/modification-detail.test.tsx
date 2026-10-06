// @vitest-environment jsdom
// SF-07:detail Modification (BUILD_SPEC CTR-27; SCREENS §7.8 to §7.10; 04 API-R-31, API-R-07; PRD SM-03,
// BR-PLT-05): a modification that is not a draft renders read-only with its change, answers,
// treatments, the stored preview and the approval routing; the preparer of the request withdraws it
// with a comment; "Edit" voids the pending request after a confirmation and returns to step 1; a
// reader without `modification.create` sees a draft read-only. A rejected modification names its
// rejection and is revised by a holder of `modification.create` for the contract's entity (PRD SM-03
// "Revise"; 04 §16.14 rev 1.236; SCREENS rev 1.65).
import { cleanup, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { RouteObject } from "react-router";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import {
  installMemoryStorage,
  preloadScreens,
  probeRoute,
  renderApp,
  signedInMe,
} from "../../test/app";
import {
  EAC_ID,
  EAC_V2_APPROVAL_ID,
  estimateRow,
  serveEstimates,
  versionRow,
} from "../../test/estimates";
import {
  APPROVAL_ID,
  classifiedRow,
  MODIFICATION_ID,
  OTHER_SSP_VERSION_ID,
  PREVIEW,
  previewedRow,
  priceTests,
  REFERENCE,
  REJECTION_COMMENT,
  serveModification,
  serveOctoberOpen,
} from "../../test/modifications";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import {
  AVM_US,
  CONTEXT,
  CONTRACT_ID,
  K02,
  money,
  PRIYA_USER,
  serveWorkbench,
} from "../../test/workbench";

installMswServer();
installMemoryStorage();
configure({ asyncUtilTimeout: 5000 });

beforeAll(async () => {
  await preloadScreens(SCREEN_ROUTES, ["SF-07:detail"]);
});

afterEach(() => {
  cleanup();
});

const MAYA = signedInMe({
  permissions: [
    "contract.read",
    "config.read",
    "ssp.read",
    "modification.create",
    "judgement.create",
  ],
});
const DETAIL = `/contracts/${CONTRACT_ID}/modifications/${MODIFICATION_ID}`;
const VOIDED =
  "The approval request was voided because this modification changed after submission. Resubmit it.";

const ROUTES: readonly RouteObject[] = [
  ...SCREEN_ROUTES.filter((route) => route.id === "SF-07:detail"),
  probeRoute(
    "SF-03:modifications",
    "/contracts/:contractId/modifications",
    "contracts.modifications.documentTitle",
  ),
  probeRoute("SF-03:history", "/contracts/:contractId/history", "contracts.history.documentTitle"),
  probeRoute("SF-08:report", "/reports/:reportCode", "reports.report.documentTitle"),
  probeRoute("SF-02", "/contracts", "contracts.list.title"),
];

function open(me = MAYA) {
  return renderApp(`${DETAIL}?${CONTEXT}`, { me, screenRoutes: ROUTES });
}

/** The modification once it is submitted: its request waits at the first routing step. */
function submittedRow() {
  return previewedRow({
    status: "SUBMITTED",
    approval_request_id: APPROVAL_ID,
    content_sha256: "a4cb2b0cbd66".padEnd(64, "0"),
    row_version: 7,
  });
}

/** The text a sighted reader sees in each cell of a row: the visually hidden sign words are left out. */
function cellTexts(row: Element | null | undefined): string[] {
  return Array.from(row?.querySelectorAll("th, td") ?? [], (cell) => {
    const shown = cell.cloneNode(true) as HTMLElement;
    for (const hidden of shown.querySelectorAll(".sr-only")) {
      hidden.remove();
    }
    return (shown.textContent ?? "").replace(/\s+/g, " ").trim();
  });
}

describe("SF-07:detail", () => {
  it("a submitted modification is read-only with its routing, and its preparer withdraws the request with a comment", async () => {
    serveWorkbench();
    const world = serveModification(submittedRow());
    open();

    expect(
      await screen.findByRole("heading", { level: 1, name: `Modification ${REFERENCE}` }),
    ).toBeTruthy();
    const page = screen.getByTestId("SF-07-detail-page");
    expect(
      Array.from(
        screen.getByRole("navigation", { name: "Breadcrumb" }).querySelectorAll("li"),
        (item) => item.textContent?.replace("/", "").trim(),
      ),
    ).toEqual(["Contracts", K02, REFERENCE]);
    expect(within(page).getByText("Co-term · effective 16 Sep 2026")).toBeTruthy();
    // SCREENS §7.10 "Pending approval": every step complete, step 5 names the status.
    const steps = screen.getByRole("navigation", { name: "Modification steps" });
    expect(Array.from(steps.querySelectorAll("li .sr-only"), (item) => item.textContent)).toEqual([
      "Step 1 of 5, Change, complete",
      "Step 2 of 5, Questionnaire, complete",
      "Step 3 of 5, Treatment, complete",
      "Step 4 of 5, Impact preview, complete",
      "Step 5 of 5, Submit, Pending approval",
    ]);
    expect(within(steps).queryAllByRole("link")).toHaveLength(0);
    // SCREENS §7.9: the sections in order.
    expect(
      within(page)
        .getAllByRole("heading", { level: 2 })
        .map((heading) => heading.textContent),
    ).toEqual(["Change", "Answers", "Treatments", "Impact preview as submitted", "Approval"]);

    const lines = within(page).getByRole("table", { name: "Lines" });
    expect(cellTexts(within(lines).getAllByRole("row")[1])).toEqual([
      "Add",
      "O2",
      "AVM-SEAT-MO",
      "50",
      "+60,000.00",
      "16 Sep 2026",
      "31 Dec 2027",
    ]);
    const answers = screen.getByTestId("SF-07-section-answers");
    // SCREENS §7.9 (rev 1.52): under the price answer the engine's price test of the added line, as
    // the row states it (04 §16.14 rev 1.250 `price_tests`) — what a reviewer reads beside the answer.
    await waitFor(() =>
      expect(Array.from(answers.querySelectorAll("dt, dd"), (item) => item.textContent)).toEqual([
        "Are the remaining goods or services distinct from those already transferred?",
        "Yes",
        "Are the added goods or services distinct?",
        "Yes",
        "Is the added price at SSP?",
        "No",
        "60,000.00 is below the range low 69,750.00 (US-LIST 2026-H1)",
      ]),
    );
    // The table of step 3 without its controls.
    const treatments = within(page).getByRole("table", { name: "Treatment by obligation" });
    expect(within(treatments).queryByRole("combobox")).toBeNull();
    expect(within(treatments).queryByRole("checkbox")).toBeNull();
    expect(cellTexts(within(treatments).getAllByRole("row")[2]).slice(0, 3)).toEqual([
      "O2",
      "Prospective (ASC 606-10-25-13(a))",
      "Prospective (ASC 606-10-25-13(a))",
    ]);
    // The SSP basis with the range of that price test, as on step 3.
    expect(
      await within(treatments).findByText("US-LIST 2026-H1 · 69,750.00 to 85,250.00"),
    ).toBeTruthy();

    // The stored preview, the one `/submit` handed to the request.
    expect(screen.getByText("Snapshot e9ac7d5ea7aa reviewed by the approver.")).toBeTruthy();
    const strip = within(page).getByRole("region", { name: "Impact summary (USD)" });
    expect(within(strip).getByText("215,178.08")).toBeTruthy();
    expect(within(strip).getByText("Before 155,178.08")).toBeTruthy();

    // The request: one row per routing step with the permission and the status.
    const routing = await screen.findByRole("list", { name: "Approval routing" });
    expect(
      within(routing)
        .getAllByRole("listitem")
        .map((item) => item.textContent?.replace(/\s+/g, " ").trim()),
    ).toEqual([
      "Revenue review · Approve contract modificationsPending approval",
      "Controller approval · Approve contract modificationsWaiting",
    ]);
    expect(screen.getByText("APR-000434")).toBeTruthy();
    expect(screen.getByText("Submitted 16 Sep 2026 10:00 UTC")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 3, name: "Linked requests" })).toBeTruthy();

    // "Withdraw request": the route takes a comment, so the dialog asks for one.
    fireEvent.click(screen.getByRole("button", { name: "Withdraw request" }));
    const dialog = await screen.findByRole("dialog", { name: "Withdraw request" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Withdraw request" }));
    expect(await within(dialog).findByText("Enter at least 1 character.")).toBeTruthy();
    expect(world.sent("POST", "/withdraw")).toHaveLength(0);
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Comment/ }), {
      target: { value: "  The seat count was wrong.  " },
    });
    const reads = world.rowReads;
    fireEvent.click(within(dialog).getByRole("button", { name: "Withdraw request" }));

    expect(
      await screen.findByText("The request was withdrawn. The modification is a draft again."),
    ).toBeTruthy();
    expect(world.sent("POST", "/withdraw")[0]?.body).toEqual({
      comment: "The seat count was wrong.",
    });
    // The row is a draft again: the wizard. A request its preparer withdrew reads WITHDRAWN, not
    // VOIDED, so the notice of a voided request is not shown.
    expect(await screen.findByTestId("SF-07-page")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1, name: "New modification" })).toBeTruthy();
    await screen.findByRole("textbox", { name: /^Scope description/ });
    expect(screen.queryByText(VOIDED)).toBeNull();
    // The draft keeps its stored preview. `/withdraw` answers the row as `GET` does (04 §16.14 rev
    // 1.188, item MOD-ANSWER-PREVIEW-1): the preview is the answer's, and the row is not read again.
    const draftSteps = screen.getByRole("navigation", { name: "Modification steps" });
    expect(
      Array.from(draftSteps.querySelectorAll("li .sr-only"), (item) => item.textContent)[3],
    ).toBe("Step 4 of 5, Impact preview, Catch-up 0.00");
    expect(world.rowReads).toBe(reads);
  });

  it("Edit voids the pending request after a confirmation and opens step Change with the notice", async () => {
    serveWorkbench();
    const world = serveModification(submittedRow());
    const { router } = open();

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Edit this submitted modification?",
    });
    expect(
      within(dialog).getByText(
        "The pending approval request is voided and approvers are notified.",
      ),
    ).toBeTruthy();
    // Nothing is sent before the confirmation.
    expect(world.sent("PATCH", MODIFICATION_ID)).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole("button", { name: "Edit" }));

    await waitFor(() => expect(world.sent("PATCH", MODIFICATION_ID)).toHaveLength(1));
    // BR-PLT-05: the empty body changes no member; the edit itself returns the row to Draft.
    expect(world.sent("PATCH", MODIFICATION_ID)[0]?.body).toEqual({});
    expect(await screen.findByTestId("SF-07-page")).toBeTruthy();
    await waitFor(() => expect(router.state.location.search).toContain("step=change"));
    // SCREENS §7.10 "Voided request (stale)": a warning, as on an estimate version whose request the
    // API voided (the supervisor's ruling on CTR-25's J10).
    const notice = await screen.findByText(VOIDED);
    expect(notice.closest("[data-tone]")?.getAttribute("data-tone")).toBe("warning");
    await screen.findByRole("textbox", { name: /^Scope description/ });
    // Step 1 sends no command on its own.
    expect(world.sent("POST", "/classify")).toHaveLength(0);
  });

  it("a draft opened without modification.create is read-only and offers no command", async () => {
    serveWorkbench();
    const world = serveModification(classifiedRow());
    open(signedInMe({ permissions: ["contract.read"] }));

    expect(await screen.findByText("No preview was stored.")).toBeTruthy();
    const page = screen.getByTestId("SF-07-detail-page");
    expect(screen.queryByTestId("SF-07-page")).toBeNull();
    expect(screen.queryByRole("navigation", { name: "Modification steps" })).toBeNull();
    expect(within(page).getByText("No approval request was submitted.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Withdraw request" })).toBeNull();
    expect(world.requests).toEqual([]);
  });

  // PRD SM-03 "Discard draft" (item MOD-DISCARD-1): what the Modifications tab opens for a draft
  // that was discarded.
  it("a discarded modification is read-only, reads Void and offers no command", async () => {
    serveWorkbench();
    const world = serveModification(previewedRow({ status: "VOIDED", row_version: 6 }));
    open();

    expect(
      await screen.findByRole("heading", { level: 1, name: `Modification ${REFERENCE}` }),
    ).toBeTruthy();
    const page = screen.getByTestId("SF-07-detail-page");
    expect(screen.queryByTestId("SF-07-page")).toBeNull();
    expect(page.querySelector("header")?.textContent).toContain("Void");
    expect(within(page).getByText("No approval request was submitted.")).toBeTruthy();
    for (const name of ["Edit", "Withdraw request", "Discard draft"]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
    expect(world.requests).toEqual([]);
  });

  it("another preparer may edit a submitted modification and may not withdraw its request", async () => {
    serveWorkbench();
    serveModification(submittedRow());
    open(
      signedInMe({
        user: {
          id: PRIYA_USER.id ?? "",
          email: "priya@example.test",
          display_name: "Priya Raman",
          status: "ACTIVE",
        },
        permissions: ["contract.read", "modification.create", "modification.approve"],
      }),
    );

    await screen.findByRole("list", { name: "Approval routing" });
    expect(screen.getByRole("button", { name: "Edit" })).toBeTruthy();
    // PRD SM-01: only the preparer of the request closes it.
    expect(screen.queryByRole("button", { name: "Withdraw request" })).toBeNull();
  });

  it("an applied modification names its approval and links the contract versions and the register", async () => {
    serveWorkbench();
    const world = serveModification(
      previewedRow({
        status: "APPLIED",
        approval_request_id: APPROVAL_ID,
        approved_at: "2026-09-17T09:15:00Z",
        approver: PRIYA_USER,
        applied_event_id: "7f7f7f7f-7f7f-4f7f-8f7f-7f7f7f7f7f7f",
        row_version: 9,
      }),
    );
    world.approvalStatus = "APPROVED";
    open();

    const applied = await screen.findByTestId("SF-07-section-applied");
    expect(
      within(applied).getByText("Approved 17 Sep 2026 09:15 UTC by Priya Raman."),
    ).toBeTruthy();
    expect(
      within(applied).getByRole("link", { name: "Contract versions" }).getAttribute("href"),
    ).toBe(`/contracts/${CONTRACT_ID}/history?${CONTEXT}&view=versions`);
    expect(
      within(applied).getByRole("link", { name: "Modification register" }).getAttribute("href"),
    ).toBe(`/reports/modification_register?f.reference=is:${REFERENCE}`);
    // The decision of a routing step, with its comment.
    const routing = await screen.findByRole("list", { name: "Approval routing" });
    const first = within(routing).getAllByRole("listitem")[0];
    expect(first?.textContent).toContain("Priya Raman");
    expect(first?.textContent).toContain("17 Sep 2026 09:15 UTC");
    expect(first?.textContent).toContain("Agrees with the change order.");
    // No stepper and no command on a modification that is applied.
    expect(screen.queryByRole("navigation", { name: "Modification steps" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
  });

  it("a modification that does not exist, or belongs to another contract, is not found", async () => {
    serveWorkbench();
    serveModification(classifiedRow());
    server.use(
      http.get(apiUrl(`/api/v1/modifications/${MODIFICATION_ID}`), () =>
        problemResponse("not-found", 404, "Not found"),
      ),
    );
    const { router } = open();

    // SCR-ST-07.
    expect(await screen.findByRole("heading", { name: "Modification not found" })).toBeTruthy();
    expect(
      screen.getByText("It may have been removed from your access, or the link is incorrect."),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Go to Contracts" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/contracts"));
    cleanup();
    server.resetHandlers();

    serveWorkbench();
    serveModification(classifiedRow({ contract_id: "9a9a9a9a-9a9a-4a9a-8a9a-9a9a9a9a9a9a" }));
    open();
    expect(await screen.findByRole("heading", { name: "Modification not found" })).toBeTruthy();
  });

  it("the stored preview says when it was computed, and a pending request is told that the period has moved", async () => {
    // SCREENS §7.7 (rev 1.52; 04 API-S-ImpactSummary rev 1.210): the detail states both members and,
    // while the approval is still to come, that its entries will differ; it has no way to run a
    // preview, so it offers none.
    serveWorkbench();
    serveModification(submittedRow());
    serveOctoberOpen();
    open();

    const warning = await screen.findByTestId("SF-07-banner-period-moved");
    expect(
      within(warning).getByText(
        "Sep 2026 is no longer the latest open period. The entries at approval will differ from these.",
      ),
    ).toBeTruthy();
    expect(within(warning).queryByRole("button")).toBeNull();
    expect(screen.getByTestId("SF-07-journal-computed").textContent).toBe(
      "Computed 16 Sep 2026 09:40 UTC for Sep 2026: the entries the approval would post then — the change's effect with the period's amounts not posted yet.",
    );
    cleanup();

    // An applied modification: its preview is a record of what was decided, and nothing is to come.
    serveWorkbench();
    const world = serveModification(
      previewedRow({
        status: "APPLIED",
        approval_request_id: APPROVAL_ID,
        approved_at: "2026-09-17T09:15:00Z",
        approver: PRIYA_USER,
        applied_event_id: "7f7f7f7f-7f7f-4f7f-8f7f-7f7f7f7f7f7f",
        row_version: 9,
      }),
    );
    world.approvalStatus = "APPROVED";
    serveOctoberOpen();
    open();
    await screen.findByTestId("SF-07-section-applied");
    await waitFor(() =>
      expect(screen.getByTestId("SF-07-journal-computed").textContent).toContain("for Sep 2026:"),
    );
    expect(screen.queryByTestId("SF-07-banner-period-moved")).toBeNull();
  });

  it("an attested price reads with its two figures, and a named SSP version stands without the range of another", async () => {
    // 04 §16.14 rev 1.250: beside an answer of Yes the engine compared nothing; the row states the
    // price and the range all the same, and the reviewer reads both (SCREENS §7.9 rev 1.52).
    serveWorkbench();
    serveModification(
      previewedRow({
        status: "SUBMITTED",
        approval_request_id: APPROVAL_ID,
        questionnaire: { O2: { added_goods_distinct: true, priced_at_ssp: true } },
        proposed_treatments: { O2: "SEPARATE_CONTRACT" },
        chosen_treatments: { O2: "SEPARATE_CONTRACT" },
        treatment_summary: "SEPARATE_CONTRACT",
        price_tests: priceTests(true),
        row_version: 7,
      }),
    );
    open();
    const answers = await screen.findByTestId("SF-07-section-answers");
    expect(
      await within(answers).findByText(
        "Attested by the preparer as priced at the standalone selling price. Price 60,000.00; SSP 69,750.00 to 85,250.00 (US-LIST 2026-H1).",
      ),
    ).toBeTruthy();
    expect(within(answers).queryByText(/below the range/)).toBeNull();
    cleanup();

    // The preparer named another approved version for the allocation ("SSP override"). The price
    // test read the version of the modification date, so its range is not printed beside the named
    // one, and the sentence names the version it read by the engine's key.
    serveWorkbench();
    serveModification(
      previewedRow({
        status: "SUBMITTED",
        approval_request_id: APPROVAL_ID,
        ssp_basis: {
          O2: {
            ssp_book_version_id: OTHER_SSP_VERSION_ID,
            is_override: true,
            justification: "Approved after the order date.",
          },
        },
        row_version: 7,
      }),
    );
    open();
    // The table is asked for itself: the page's frame is another element while the row loads.
    const treatments = await screen.findByRole("table", { name: "Treatment by obligation" });
    expect(await within(treatments).findByText("US-LIST 2026-H2")).toBeTruthy();
    expect(within(treatments).getByText("SSP override")).toBeTruthy();
    expect(within(treatments).queryByText(/69,750\.00/)).toBeNull();
    expect(
      within(screen.getByTestId("SF-07-section-answers")).getByText(
        "60,000.00 is below the range low 69,750.00 (US-LIST v1)",
      ),
    ).toBeTruthy();
  });

  it("Linked requests lists the linked estimate versions with their requests, above the judgement records", async () => {
    // SCREENS §7.8 (rev 1.51; 04 §16.14 rev 1.210): the versions created inside the modification,
    // each approved on its own request before the submission.
    serveWorkbench();
    const estimates = serveEstimates([estimateRow()], {
      [EAC_ID]: [
        versionRow({
          version_no: 2,
          status: "APPROVED",
          effective_date: "2026-09-10",
          expected_total_amount: "820000.00",
          costs_incurred_to_date: money("420000.00"),
          progress_ratio: "0.512195",
          modification_id: MODIFICATION_ID,
          approval_request_id: EAC_V2_APPROVAL_ID,
        }),
        versionRow({
          version_no: 1,
          status: "SUPERSEDED",
          effective_date: "2026-02-01",
          expected_total_amount: "700000.00",
          costs_incurred_to_date: money("420000.00"),
          progress_ratio: "0.6",
        }),
      ],
    });
    const world = serveModification(submittedRow());
    world.estimates = estimates;
    renderApp(`${DETAIL}?${CONTEXT}`, {
      me: MAYA,
      screenRoutes: [
        ...ROUTES,
        probeRoute(
          "SF-03:estimate",
          "/contracts/:contractId/estimates/:estimateId",
          "contracts.estimates.documentTitle",
        ),
        probeRoute("SF-12:request", "/approvals/requests/:requestId", "approvals.title"),
      ],
    });

    // The frame of the loaded detail replaces the loading one: the page is read once it is there.
    expect(await screen.findByRole("heading", { level: 3, name: "Linked requests" })).toBeTruthy();
    const detail = screen.getByTestId("SF-07-detail-page");
    const table = await within(detail).findByRole("table", { name: "Linked estimate versions" });
    expect(Array.from(table.querySelectorAll("thead th"), (cell) => cell.textContent)).toEqual([
      "Element",
      "Kind",
      "Version",
      "Figure",
      "Status",
      "Request",
    ]);
    await waitFor(() =>
      expect(cellTexts(within(table).getAllByRole("row")[1])).toEqual([
        "EAC",
        "Estimated total costs",
        "2",
        "820,000.00",
        "Approved",
        "View request",
      ]),
    );
    expect(within(table).getByRole("link", { name: "EAC" }).getAttribute("href")).toBe(
      `/contracts/${CONTRACT_ID}/estimates/${EAC_ID}?${CONTEXT}`,
    );
    expect(within(table).getByRole("link", { name: "View request" }).getAttribute("href")).toBe(
      `/approvals/requests/${EAC_V2_APPROVAL_ID}?${CONTEXT}`,
    );
    // The judgement records follow under the same heading.
    expect(within(detail).getByText("No judgement record is linked.")).toBeTruthy();
  });
});

const REJECTED = `Modification ${REFERENCE} was rejected. Revise it to submit it again.`;
const REVISED =
  "This draft revises a rejected modification. Request APR-000434 stays closed; submitting makes a new one.";
const REVISE_CONSEQUENCE =
  "It returns to Draft: the proposal, the classification and the preview are made again. The rejected request stays closed; the next submission makes a new one.";
const REQUEST_HREF = `/approvals/requests/${APPROVAL_ID}?${CONTEXT}`;
// The detail with the request screen built, as the application routes it.
const WITH_REQUEST: readonly RouteObject[] = [
  ...ROUTES,
  probeRoute("SF-12:request", "/approvals/requests/:requestId", "approvals.title"),
];
const READER = signedInMe({ permissions: ["contract.read"] });

/** The modification once its request is rejected at the first routing step. */
function rejectedRow() {
  return previewedRow({
    status: "REJECTED",
    approval_request_id: APPROVAL_ID,
    content_sha256: "a4cb2b0cbd66".padEnd(64, "0"),
    row_version: 8,
  });
}

function serveRejected() {
  serveWorkbench();
  const world = serveModification(rejectedRow());
  world.approvalStatus = "REJECTED";
  return world;
}

function openWithRequest(me = MAYA) {
  return renderApp(`${DETAIL}?${CONTEXT}`, { me, screenRoutes: WITH_REQUEST });
}

/** The banner a sentence stands in. */
async function bannerOf(sentence: string): Promise<HTMLElement> {
  const banner = (await screen.findByText(sentence)).closest<HTMLElement>("[data-tone]");
  if (banner === null) {
    throw new Error(`"${sentence}" stands in no banner`);
  }
  return banner;
}

// PRD SM-03 REJECTED → DRAFT, "Revise" (04 §16.14 rev 1.236, item MOD-REJECTED-REVISE-1; SCREENS §7.9
// and §7.10, rev 1.65). Before, a rejected modification was a dead end on this screen: the chip and
// the routing, and no command.
describe("SF-07:detail, a rejected modification", () => {
  it("a rejected modification names its rejection under the header, and its holder revises it after a confirmation: an empty PATCH, then step Change", async () => {
    const world = serveRejected();
    const { router } = openWithRequest();

    const banner = await bannerOf(REJECTED);
    expect(banner.getAttribute("data-tone")).toBe("info");
    const page = screen.getByTestId("SF-07-detail-page");
    expect(page.querySelector("header")?.textContent).toContain("Rejected");
    // Under the header, above the sections.
    expect(
      within(page)
        .getAllByRole("heading", { level: 2 })
        .map((heading) => heading.textContent),
    ).toEqual([
      REJECTED,
      "Change",
      "Answers",
      "Treatments",
      "Impact preview as submitted",
      "Approval",
    ]);
    expect(within(banner).getByRole("link", { name: "View request" }).getAttribute("href")).toBe(
      REQUEST_HREF,
    );
    // The banner is the one place of "Revise". A rejected modification has no pending request to
    // edit or to withdraw, and no stepper.
    expect(screen.getAllByRole("button", { name: "Revise" })).toEqual([
      within(banner).getByRole("button", { name: "Revise" }),
    ]);
    for (const name of ["Edit", "Withdraw request"]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
    expect(screen.queryByRole("navigation", { name: "Modification steps" })).toBeNull();
    // "Approval" keeps the routing: the step the rejection was decided at, with the decision and
    // its comment, and the step behind it, which the engine skips.
    const routing = await screen.findByRole("list", { name: "Approval routing" });
    expect(
      within(routing)
        .getAllByRole("listitem")
        .map((item) => item.textContent?.replace(/\s+/g, " ").trim()),
    ).toEqual([
      `Revenue review · Approve contract modificationsRejectedPriya Raman17 Sep 2026 09:15 UTC${REJECTION_COMMENT}`,
      "Controller approval · Approve contract modificationsSkipped",
    ]);

    fireEvent.click(within(banner).getByRole("button", { name: "Revise" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Revise this modification?" });
    expect(within(dialog).getByText(REVISE_CONSEQUENCE)).toBeTruthy();
    // Nothing is sent before the confirmation.
    expect(world.requests).toEqual([]);
    fireEvent.click(within(dialog).getByRole("button", { name: "Revise" }));

    await waitFor(() => expect(world.sent("PATCH", MODIFICATION_ID)).toHaveLength(1));
    // The empty body changes no member; the edit itself returns the row to Draft.
    expect(world.sent("PATCH", MODIFICATION_ID)[0]?.body).toEqual({});
    expect(await screen.findByTestId("SF-07-page")).toBeTruthy();
    await waitFor(() => expect(router.state.location.search).toContain("step=change"));
    await screen.findByRole("textbox", { name: /^Scope description/ });
    // The wizard says where the draft comes from. The rejected request was decided: it is not
    // voided, so the warning of a voided request is not shown.
    const revised = await bannerOf(REVISED);
    expect(revised.getAttribute("data-tone")).toBe("info");
    expect(within(revised).getByRole("link", { name: "View request" }).getAttribute("href")).toBe(
      REQUEST_HREF,
    );
    expect(screen.queryByText(VOIDED)).toBeNull();
    expect(screen.queryByRole("alertdialog")).toBeNull();
    // Step 1 sends no command on its own: the one command is the edit.
    expect(world.requests.map((item) => `${item.method} ${item.path}`)).toEqual([
      `PATCH /modifications/${MODIFICATION_ID}`,
    ]);
  });

  it("Revise is offered to a holder of modification.create for the contract's entity, not to a reader nor to a holder for another entity", async () => {
    // SCREENS §0.6 SCR-PERM-02 (a): a modification is a record of the contract's legal entity, and
    // the API's edit asks the permission for that entity.
    const holderFor = (entityId: string) =>
      signedInMe({
        permissions: ["contract.read", "modification.create"],
        permission_scopes: { "contract.read": "*", "modification.create": [entityId] },
      });
    for (const me of [READER, holderFor("0a1b2c3d-4e5f-4a6b-8c7d-0000000000ff")]) {
      const world = serveRejected();
      openWithRequest(me);
      const banner = await bannerOf(REJECTED);
      // The rejection and its request are read by everyone who reads the contract.
      expect(within(banner).getByRole("link", { name: "View request" })).toBeTruthy();
      await screen.findByRole("list", { name: "Approval routing" });
      expect(screen.queryByRole("button", { name: "Revise" })).toBeNull();
      expect(world.requests).toEqual([]);
      cleanup();
    }

    serveRejected();
    openWithRequest(holderFor(AVM_US.id));
    expect(
      await within(await bannerOf(REJECTED)).findByRole("button", { name: "Revise" }),
    ).toBeTruthy();
  });

  it("a refusal of Revise is shown in the confirmation, and the modification stays as it is", async () => {
    const world = serveRejected();
    world.refuse.patch = () =>
      problemResponse("invalid-transition", 409, "Action not available in this state", {
        errors: [
          {
            field: null,
            rule_id: "SM-03",
            message: "Only a draft, submitted or rejected modification can be edited.",
          },
        ],
      });
    const { router } = openWithRequest();

    fireEvent.click(within(await bannerOf(REJECTED)).getByRole("button", { name: "Revise" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Revise this modification?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Revise" }));

    expect(
      await within(dialog).findByText(
        "Only a draft, submitted or rejected modification can be edited.",
      ),
    ).toBeTruthy();
    expect(within(dialog).getByText("Action not available in this state")).toBeTruthy();
    expect(world.sent("PATCH", MODIFICATION_ID)).toHaveLength(1);
    // The confirmation stays open over the detail; no step is opened.
    expect(screen.getByTestId("SF-07-detail-page")).toBeTruthy();
    expect(screen.queryByTestId("SF-07-page")).toBeNull();
    expect(router.state.location.search).toBe(`?${CONTEXT}`);
    // A confirmation opened again starts without the refusal of the last one.
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    fireEvent.click(within(await bannerOf(REJECTED)).getByRole("button", { name: "Revise" }));
    const again = await screen.findByRole("alertdialog", { name: "Revise this modification?" });
    expect(within(again).queryByText("Action not available in this state")).toBeNull();
  });

  it("a rejected modification offers no link to a request the reader cannot open", async () => {
    serveRejected();
    server.use(
      http.get(apiUrl(`/api/v1/approvals/${APPROVAL_ID}`), () =>
        problemResponse("not-found", 404, "Not found"),
      ),
    );
    openWithRequest();

    expect(await screen.findByText("The approval request is not visible to you.")).toBeTruthy();
    const banner = await bannerOf(REJECTED);
    expect(within(banner).queryByRole("link")).toBeNull();
    // The command does not depend on the request: the row says that it is rejected.
    expect(within(banner).getByRole("button", { name: "Revise" })).toBeTruthy();
  });
});

// SCREENS §7.10 (rev 1.65): the detail of a draft, which a reader without `modification.create` is
// shown, said nothing of the draft's earlier request; the wizard of the same draft did.
describe("SF-07:detail, a draft opened without modification.create", () => {
  function serveDraft(status: "VOIDED" | "REJECTED" | "WITHDRAWN") {
    serveWorkbench();
    const world = serveModification(classifiedRow({ approval_request_id: APPROVAL_ID }));
    world.approvalStatus = status;
    return world;
  }

  it("a draft opened without modification.create says of a voided request, and of a rejected one, what the wizard says, and nothing of a withdrawn one", async () => {
    const voided = serveDraft("VOIDED");
    openWithRequest(READER);
    const warning = await bannerOf(VOIDED);
    expect(warning.getAttribute("data-tone")).toBe("warning");
    expect(screen.getByTestId("SF-07-detail-page")).toBeTruthy();
    expect(screen.queryByTestId("SF-07-page")).toBeNull();
    expect(voided.requests).toEqual([]);
    cleanup();

    const rejected = serveDraft("REJECTED");
    openWithRequest(READER);
    const revised = await bannerOf(REVISED);
    expect(revised.getAttribute("data-tone")).toBe("info");
    expect(within(revised).getByRole("link", { name: "View request" }).getAttribute("href")).toBe(
      REQUEST_HREF,
    );
    expect(screen.getByTestId("SF-07-detail-page")).toBeTruthy();
    // The draft is revised already: there is nothing to revise, and the reader has no command.
    expect(screen.queryByRole("button", { name: "Revise" })).toBeNull();
    expect(rejected.requests).toEqual([]);
    cleanup();

    // A request its preparer withdrew reads WITHDRAWN: no banner, as on the wizard.
    serveDraft("WITHDRAWN");
    openWithRequest(READER);
    await screen.findByRole("list", { name: "Approval routing" });
    // A banner's title is a heading of the sections' level: there is none above them.
    expect(
      within(screen.getByTestId("SF-07-detail-page"))
        .getAllByRole("heading", { level: 2 })
        .map((heading) => heading.textContent),
    ).toEqual(["Change", "Answers", "Treatments", "Impact preview as submitted", "Approval"]);
  });
});

// KIT-FILTER-LEAVING-2 (dev-guide DG-FE-03 rule (3), rev 1.230): "Edit" opens step Change with this
// page's own path once its command has answered. An answer that came after the member had gone to
// another page took them back to the modification.
describe("SF-07:detail, an edit that answers after the member has left", () => {
  it("opens nothing: the member stays on the page they went to", async () => {
    serveWorkbench();
    serveModification(submittedRow());
    let answer: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      answer = resolve;
    });
    let sent = false;
    let answered = false;
    server.use(
      http.patch(apiUrl(`/api/v1/modifications/${MODIFICATION_ID}`), async () => {
        sent = true;
        await held;
        answered = true;
        return HttpResponse.json(previewedRow({ status: "DRAFT", row_version: 8 }));
      }),
    );
    const { router } = open();
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("alertdialog", {
      name: "Edit this submitted modification?",
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Edit" }));
    await waitFor(() => expect(sent).toBe(true));

    await router.navigate(`/contracts?${CONTEXT}`);
    await screen.findByRole("heading", { level: 1, name: "Contracts" });
    answer();
    await waitFor(() => expect(answered).toBe(true));
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(`${router.state.location.pathname}${router.state.location.search}`).toBe(
      `/contracts?${CONTEXT}`,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Contracts" })).toBeTruthy();
  });

  // "Revise" is the same edit, of a rejected modification (SCREENS §7.9, rev 1.65).
  it("Revise opens nothing either once the member has left", async () => {
    serveRejected();
    let answer: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      answer = resolve;
    });
    let sent = false;
    let answered = false;
    server.use(
      http.patch(apiUrl(`/api/v1/modifications/${MODIFICATION_ID}`), async () => {
        sent = true;
        await held;
        answered = true;
        return HttpResponse.json(
          previewedRow({ status: "DRAFT", approval_request_id: APPROVAL_ID, row_version: 10 }),
        );
      }),
    );
    const { router } = openWithRequest();
    fireEvent.click(within(await bannerOf(REJECTED)).getByRole("button", { name: "Revise" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Revise this modification?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Revise" }));
    await waitFor(() => expect(sent).toBe(true));

    await router.navigate(`/contracts?${CONTEXT}`);
    await screen.findByRole("heading", { level: 1, name: "Contracts" });
    answer();
    await waitFor(() => expect(answered).toBe(true));
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(`${router.state.location.pathname}${router.state.location.search}`).toBe(
      `/contracts?${CONTEXT}`,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Contracts" })).toBeTruthy();
  });
});

// SCREENS §7.9 (rev 1.77; lane QA-BE's item MOD-PREVIEW-READ-SCOPE-1 on the screens; 04 §16.10 rev 1.300
// "Who reads a stored preview"): a reader who does not hold `contract.read` for every entity of the
// contract's combination group is not shown the stored preview, and the row tells that one is
// stored. The stand-in answers as measured through the routes (register index 276).
describe("SF-07:detail, a stored preview the reader is not shown", () => {
  const TITLE = "You are not shown this preview";
  const TEXT =
    "The stored preview holds figures of legal entities outside your access. It is shown to people whose access covers every entity of the contract's combination group.";
  const SNAPSHOT = "Snapshot e9ac7d5ea7aa reviewed by the approver.";
  // DS-FMT-05: money outside a grid reads ISO code, no-break space, amount.
  const NBSP = String.fromCharCode(160);
  const NONE = "No preview was stored.";

  it("a modification whose stored preview the reader is not shown says so, with the catch-up and the snapshot, and not that none was stored", async () => {
    const reader = signedInMe({ permissions: ["contract.read"] });
    // A submitted modification, and a draft read without modification.create.
    const views = [
      [submittedRow(), MAYA],
      [previewedRow(), reader],
    ] as const;
    for (const [row, me] of views) {
      serveWorkbench();
      const world = serveModification({
        ...row,
        impact_preview: { ...PREVIEW, catch_up_total: money("-1906.79") },
        impact_summary: { catch_up_total: money("-1906.79") },
      });
      world.previewWithheld = true;
      open(me);

      const section = await screen.findByTestId("SF-07-section-preview");
      const notice = await within(section).findByTestId("SF-07-banner-preview-withheld");
      expect(within(notice).getByRole("heading", { level: 3, name: TITLE })).toBeTruthy();
      expect(notice.textContent).toBe(
        `${TITLE}${TEXT}Catch-up of this contract's obligations: USD${NBSP}(1,906.79).`,
      );
      // An info banner that stands with the page: no live region.
      expect(notice.querySelector("[data-tone]")?.getAttribute("data-tone")).toBe("info");
      expect(within(notice).queryByRole("status")).toBeNull();
      expect(within(section).getByText(SNAPSHOT)).toBeTruthy();
      expect(within(section).queryByText(NONE)).toBeNull();
      expect(within(section).queryByRole("region", { name: /^Impact summary/ })).toBeNull();
      expect(within(section).queryByRole("table")).toBeNull();
      cleanup();
      server.resetHandlers();
    }
  });

  it("a row that stores no preview still says that none was stored, and a stored preview the reader is shown stands with its tables", async () => {
    // The same reader, who would not be shown a stored preview: this row stores none.
    serveWorkbench();
    const bare = serveModification(classifiedRow());
    bare.previewWithheld = true;
    open(signedInMe({ permissions: ["contract.read"] }));
    const empty = await screen.findByTestId("SF-07-section-preview");
    expect(await within(empty).findByText(NONE)).toBeTruthy();
    expect(within(empty).queryByTestId("SF-07-banner-preview-withheld")).toBeNull();
    expect(within(empty).queryByText(SNAPSHOT)).toBeNull();
    cleanup();
    server.resetHandlers();

    // A reader the API answers the preview.
    serveWorkbench();
    serveModification(submittedRow());
    open();
    const shown = await screen.findByTestId("SF-07-section-preview");
    expect(await within(shown).findByRole("region", { name: "Impact summary (USD)" })).toBeTruthy();
    expect(within(shown).getByText(SNAPSHOT)).toBeTruthy();
    expect(within(shown).queryByTestId("SF-07-banner-preview-withheld")).toBeNull();
  });

  it("a withheld preview whose row states no catch-up shows the notice without the line", async () => {
    serveWorkbench();
    const world = serveModification({
      ...submittedRow(),
      impact_summary: { catch_up_total: null },
    });
    world.previewWithheld = true;
    open();

    const notice = await screen.findByTestId("SF-07-banner-preview-withheld");
    expect(notice.textContent).toBe(`${TITLE}${TEXT}`);
  });
});
